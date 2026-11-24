# Mapping Operations to HTTP Methods and Response Status Codes

## 1. From Java Method to HTTP Contract

When writing an Actuator endpoint, you declare **operations** using annotations. When the endpoint is exposed over the web, Spring Boot builds request mappings based on the endpoint identifier, operation type, path selector parameters, and supported data types.

A Java method named `update` does not automatically become PUT. A method named `delete` does not automatically become DELETE either. **The operation annotation determines the operation type**, from which Actuator selects the corresponding HTTP method.

Three parts of the contract must be distinguished:

| Part | Question to Answer |
| --- | --- |
| Request routing | Which path is called, and using which HTTP method? |
| Input intake | Is the value in the path, query, or JSON body? Can it be converted to the Java type? |
| Response generation | Which status code is returned? Is there a body? How is the body represented? |

This lesson uses Spring Boot 3.3.x and Java 21 examples. Status codes are described assuming the endpoint is registered, enabled, exposed over HTTP, and the request is allowed to reach the handler layer. A security filter or proxy may terminate the request earlier.

## 2. Operation-to-HTTP-Method Mapping Table

| Annotation on Method | Operation Type | Primary HTTP Method When Exposed Over Web |
| --- | --- | --- |
| `@ReadOperation` | Read information | GET |
| `@WriteOperation` | Modify state or perform a management action | POST |
| `@DeleteOperation` | Delete or remove managed state/resources | DELETE |

This is the Actuator web endpoint convention in [Spring Boot 3.3: Operation HTTP Methods](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.request-predicates.http-method).

Implications to remember:

- Do not turn `@WriteOperation` into PUT by naming the method `put`.
- `@WriteOperation` does not automatically create PATCH either.
- Method names help code readers understand intent, but they are not URL segments appended automatically.
- The same path can have GET, POST, and DELETE if the corresponding operations are declared.
- Two read methods on the same path are not automatically distinguished solely by Java name or return object type. Duplicate mappings must be avoided.

The `produces` attribute on annotations such as `@WriteOperation` describes the response content type; it is not an attribute for choosing the HTTP method. See the [WriteOperation contract](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/WriteOperation.html).

If you need an HTTP contract that does not fit Actuator's operation model, choose a web-specific extension point or an API controller suited to the feature's purpose, rather than inferring extra capabilities from method names.

## 3. Paths and Inputs Both Participate in Mapping

Suppose an endpoint has `id = "flags"`, using the default base path `/actuator`:

| Illustrative Declaration | Path and Method |
| --- | --- |
| `@ReadOperation snapshot()` | GET /actuator/flags |
| `@ReadOperation find(@Selector String name)` | GET /actuator/flags/{name} |
| `@WriteOperation put(String name, boolean enabled)` | POST /actuator/flags |
| `@WriteOperation update(@Selector String name, boolean enabled)` | POST /actuator/flags/{name} |
| `@DeleteOperation delete(@Selector String name)` | DELETE /actuator/flags/{name} |

The declarations in the table omit return types to focus on mapping. Full code is in section 6.

`@Selector` turns a parameter into a part of the path. Other input parameters can be taken from query parameters or top-level properties of the JSON body according to the operation mechanism. For example, a POST with body:

```json
{"name":"blue","enabled":true}
```

can supply the two arguments `String name` and `boolean enabled`. You do not need and should not blindly copy `@RequestBody` from controllers into this operation method.

To map based on Java parameter names, you must compile with `-parameters`. For technology-neutral inputs between HTTP/JMX, supported operation parameter types must be followed; a complex input DTO is not processed identically to Spring MVC controller body binding.

Meanwhile, **the return object can be a data structure to be serialized into JSON**. Do not confuse input type restrictions with not being allowed to return records or result objects.

Changing the base path, management port, or context path can make the actual URL differ from the example. Changing the URL does not change the GET/POST/DELETE rules of operations.

## 4. Default Response Status Code Rules

When an operation completes normally and does not explicitly specify a custom web response, Actuator examines the operation type and whether it returns a value:

| Operation | Has Return Value | No Return Value |
| --- | --- | --- |
| Read | 200 OK | 404 Not Found |
| Write | 200 OK | 204 No Content |
| Delete | 200 OK | 204 No Content |

These rules are stated in [Spring Boot 3.3: Web Endpoint Response Status](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.response-status).

### 4.1. “No Value” Differs from “Empty Value”

The following cases need to be clearly separated:

| Java Value | Is There a Value to Return? | Meaning for Default Rules |
| --- | --- | --- |
| `null` | No | Read → 404; Write/Delete → 204 |
| `void` method | No | Produces no result object |
| `false` | Yes | Does not automatically become 404 or 204 |
| `0` | Yes | Does not automatically become 404 or 204 |
| Empty Map or empty List | Yes | Can return 200 with a collection-wise empty body |
| Record containing `enabled=false` | Yes | Still has a result object to return |

With GET returning an empty map, the body can be `{}` and the status is still 200. With GET returning `null`, the default behavior is 404; it is not 200 with the JSON literal `null`.

Similarly, declaring a read method as `void` is not the usual way to make GET return 204. If a custom status-code contract is needed, express it using an appropriate web response mechanism.

### 4.2. HTTP Status Does Not Automatically Inspect Object Contents

If a write operation returns an object such as:

```json
{"success":false,"reason":"not-ready"}
```

then “having a result object” still triggers the default status code 200. Actuator does not inspect the `success` field to choose 409 or 503.

Other cases are not automatically inferred either:

- A POST that creates data does not automatically become 201 Created.
- A method that starts a background job does not automatically become 202 Accepted.
- A DELETE that does not find data does not automatically become 404 if the method only returns `null`; Delete's default in that case is 204.
- 204 indicates the response has no body; it does not prove data was persisted durably or a background job finished.

The operation contract must be designed clearly first; the status code expresses that contract rather than replacing implementation.

## 5. Errors That Can Occur Before the Operation Is Invoked

An operation with the right annotations is not guaranteed to run. The request must still match the mapping and provide valid inputs.

| Code | Typical Scenario in an Example Without a Security Layer |
| --- | --- |
| 400 Bad Request | Missing required parameter or cannot convert to the required Java type |
| 404 Not Found | No available path; or Read returned `null` after being invoked |
| 405 Method Not Allowed | Path has a mapping but no operation for the HTTP method being used |
| 406 Not Acceptable | Requested response format does not match `produces` capabilities |
| 415 Unsupported Media Type | Request body Content-Type does not match an operation accepting a body |

The same 404 code can appear at **two different stages**:

```text
No exposed endpoint / path mismatch
    -> operation not invoked -> 404

Matches GET, invokes read operation, result is null
    -> operation invoked -> default 404 for Read
```

Conversely, when a required parameter is missing or type conversion fails, the operation is not invoked and the response is 400. Do not place side effects in a step you hope “will run before parameter checks”.

In an application with Spring Security, 401 or 403 can occur before the operation layer; CSRF can also cause POST/DELETE requests to be rejected. Adding `@WriteOperation` does not bypass those rules.

Exceptions thrown inside operation logic are a separate matter from parameter conversion errors. Do not assume every `IllegalArgumentException` thrown by application code becomes 400, or that every `null` represents an internal error.

To trace how results are adapted in Spring MVC, you can view [Spring Boot 3.3.0 endpoint mapping code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/endpoint/web/servlet/AbstractWebMvcEndpointHandlerMapping.java).

## 6. Complete Example: Reading, Writing, and Deleting Simulated Flags

The example uses an in-memory map to observe the HTTP contract. It does not affect real operational configuration, does not persist data across restarts, and does not synchronize across multiple application instances.

### 6.1. Structure and Build

Create a standalone Gradle project:

```text
operation-mapping-demo/
├── build.gradle
└── src/main/
    ├── java/example/operationmapping/OperationMappingApplication.java
    └── resources/application.properties
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.0'
    )
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.compilerArgs.add('-parameters')
}
```

Use Gradle 8.5 and JDK 21 for the example. If using a wrapper, invoke the project's corresponding wrapper command. This is a standalone sample project, not a requirement to replace the build configuration of an existing module.

### 6.2. Java Code

File `src/main/java/example/operationmapping/OperationMappingApplication.java`:

```java
package example.operationmapping;

import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.endpoint.annotation.DeleteOperation;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.boot.actuate.endpoint.web.WebEndpointResponse;
import org.springframework.boot.actuate.endpoint.web.annotation.EndpointWebExtension;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class OperationMappingApplication {
    public static void main(String[] args) {
        SpringApplication.run(OperationMappingApplication.class, args);
    }

    @Bean
    FlagsEndpoint flagsEndpoint() {
        return new FlagsEndpoint();
    }

    @Bean
    @ConditionalOnProperty(
            name = "demo.strict-delete", havingValue = "true")
    FlagsWebExtension flagsWebExtension(FlagsEndpoint endpoint) {
        return new FlagsWebExtension(endpoint);
    }

    public record FlagView(String name, boolean enabled) {
    }

    @Endpoint(id = "flags")
    public static class FlagsEndpoint {
        private final Map<String, Boolean> flags = new ConcurrentHashMap<>();

        public FlagsEndpoint() {
            flags.put("demo", false);
        }

        @ReadOperation
        public Map<String, Boolean> snapshot() {
            return new TreeMap<>(flags);
        }

        @ReadOperation
        public FlagView find(@Selector String name) {
            Boolean value = flags.get(name);
            return value == null ? null : new FlagView(name, value);
        }

        @WriteOperation
        public FlagView put(String name, boolean enabled) {
            flags.put(name, enabled);
            return new FlagView(name, enabled);
        }

        @WriteOperation
        public void update(@Selector String name, boolean enabled) {
            flags.put(name, enabled);
        }

        @DeleteOperation
        public FlagView delete(@Selector String name) {
            Boolean value = flags.remove(name);
            return value == null ? null : new FlagView(name, value);
        }
    }

    @EndpointWebExtension(endpoint = FlagsEndpoint.class)
    public static class FlagsWebExtension {
        private final FlagsEndpoint endpoint;

        public FlagsWebExtension(FlagsEndpoint endpoint) {
            this.endpoint = endpoint;
        }

        @DeleteOperation
        public WebEndpointResponse<FlagView> delete(@Selector String name) {
            FlagView removed = endpoint.delete(name);
            return removed == null
                    ? new WebEndpointResponse<>(404)
                    : new WebEndpointResponse<>(removed, 200);
        }
    }
}
```

In default mode, the `FlagsWebExtension` bean is not created yet because `demo.strict-delete=true` is not enabled. Thus, we observe the default codes of the operations before enabling the customization in section 8.

Some details of the sample:

- The map initially contains `demo=false`.
- `snapshot()` always returns a map, even when the map has no remaining elements.
- `find()` returns `null` when the requested name is absent.
- `put()` writes the value and returns `FlagView`, so POST defaults to 200.
- `update()` writes the value but is declared `void`, so POST defaults to 204.
- Both write operations in the sample can add or replace a name. They do not check “must already exist”.
- `delete()` returns the removed object if found; a subsequent delete returns `null`.

The method name `put()` was chosen to describe putting a value into the map. It is still POST because it is annotated with `@WriteOperation`.

### 6.3. Exposure Configuration

File `src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,flags
demo.strict-delete=false
```

The sample listens only on loopback and has no Spring Security dependency to separate learning mapping from authentication configuration. In a real system, management state-changing operations need appropriate protection.

Run from the project directory:

```shell
gradle bootRun
```

If Gradle Wrapper is present on Windows:

```powershell
.\gradlew.bat bootRun
```

## 7. Practicing Observing Status Codes and Bodies

The steps below start from a freshly started application with unaltered data. The JSON shown is the response body; headers containing timestamps or server information are not assumed to be fixed.

### 7.1. GET with a Result and GET with No Result

Call in PowerShell:

```powershell
curl.exe -sS http://127.0.0.1:8080/actuator/flags
```

Body:

```json
{"demo":false}
```

GET `/actuator/flags/demo` returns 200 with:

```json
{"name":"demo","enabled":false}
```

The value `false` does not mean “no result”. `find()` returned a valid `FlagView`.

Test a non-existent name:

```powershell
curl.exe -sS -o NUL -w "%{http_code}" http://127.0.0.1:8080/actuator/flags/missing
```

Status code result:

```text
404
```

In this case, the mapping matched and `find()` returned `null`. The response does not have a JSON `null` body.

### 7.2. POST with a Return Value

Use PowerShell to send the JSON body, avoiding confusion with how shells pass quotes to external programs:

```powershell
$r = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8080/actuator/flags' -ContentType 'application/json' -Body '{"name":"blue","enabled":true}'
$r.StatusCode
$r.Content
```

Result:

```text
200
{"name":"blue","enabled":true}
```

Even though `blue` is a newly added name in the map, the code is still 200 under the default rule for a Write with a return value. “Creating” in code does not automatically turn it into 201.

### 7.3. POST Without a Return Value

```powershell
$r = Invoke-WebRequest -Method Post -Uri 'http://127.0.0.1:8080/actuator/flags/demo' -ContentType 'application/json' -Body '{"enabled":true}'
$r.StatusCode
$r.Content.Length
```

Result:

```text
204
0
```

`name` comes from the path selector, while `enabled` comes from the JSON body. The `update()` method mutated the map but did not return a result object.

Then GET `/actuator/flags/demo` returns 200 with:

```json
{"name":"demo","enabled":true}
```

Do not attempt to parse a 204 body as JSON. If the caller needs to know the new result in the write response itself, design the operation to return appropriate data rather than guessing at an absent body.

### 7.4. DELETE with Data and Repeated DELETE

After the update step above, the first DELETE:

```powershell
$r = Invoke-WebRequest -Method Delete -Uri 'http://127.0.0.1:8080/actuator/flags/demo'
$r.StatusCode
$r.Content
```

Result:

```text
200
{"name":"demo","enabled":true}
```

The second DELETE:

```powershell
curl.exe -sS -o NUL -w "%{http_code}" -X DELETE http://127.0.0.1:8080/actuator/flags/demo
```

Result:

```text
204
```

The first time `delete()` returned the deleted object; the next time it returned `null`. The default code for a Delete with no value is 204, even though the name is no longer in the map. This is the contract of the sample, not a conclusion that every DELETE API in every system must return 204 when data does not exist.

If you also delete `blue`, GET `/actuator/flags` returns 200 with body:

```json
{}
```

An empty map is still a return value, distinct from `null`.

### 7.5. Request Error Matrix

With the sample application, web extension disabled and no security layer added:

| Request | Expected Result | Reason |
| --- | --- | --- |
| POST /actuator/flags/demo, JSON `{}` | 400 | Missing required `enabled` |
| POST /actuator/flags/demo, JSON `{"enabled":"not-a-boolean"}` | 400 | Cannot convert to boolean |
| PUT /actuator/flags/demo | 405 | Write operation is mapped to POST |
| POST /actuator/flags/demo with Content-Type text/plain | 415 | Incompatible with operation accepting JSON body |
| GET /actuator/flags/demo with Accept text/plain | 406 | Incompatible with operation's response media type |

The 405/406/415 errors in the table are determined at the request-handling layer before invoking the corresponding method; they do not depend on whether `demo` is still in the map or has been deleted.

If testing with `Invoke-WebRequest`, remember PowerShell may throw errors when receiving 4xx responses. That does not mean the Java operation threw the corresponding exception. You can use an HTTP tool that displays status/body or inspect the response directly in a test.

## 8. Explicitly Specifying Status Codes with WebEndpointResponse

Suppose the endpoint requirement is: “DELETING a non-existent name must return 404”. Simply returning `null` from Delete does not meet that requirement, because the default rule is 204.

`WebEndpointResponse<T>` represents a body and an explicit HTTP status code. According to [Spring Boot 3.3's WebEndpointResponse contract](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html), this is the return type for web-specific information, typically in an `@EndpointWebExtension`.

The sample already includes the extension:

```java
@DeleteOperation
public WebEndpointResponse<FlagView> delete(@Selector String name) {
    FlagView removed = endpoint.delete(name);
    return removed == null
            ? new WebEndpointResponse<>(404)
            : new WebEndpointResponse<>(removed, 200);
}
```

This is an excerpt of `FlagsWebExtension` in the complete code, not a standalone method to insert into `FlagsEndpoint`.

`@EndpointWebExtension(endpoint = FlagsEndpoint.class)` links the extension to the original endpoint. The extension adds or replaces the corresponding operation at the web layer; it does not change the endpoint ID to the extension class name. See [EndpointWebExtension](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/annotation/EndpointWebExtension.html).

To observe it, change the configuration and restart:

```properties
demo.strict-delete=true
```

The application is reinitialized so the initial map reverts to `demo=false`. Results:

| Sequential Operation | When strict-delete Is Enabled |
| --- | --- |
| DELETE /actuator/flags/missing | 404, no body |
| DELETE /actuator/flags/demo first time | 200, body is the removed FlagView |
| DELETE /actuator/flags/demo next time | 404, no body |

The deciding factor is not “the `WebEndpointResponse` object is non-null so it must be 200”. The web adapter recognizes this response type and uses the specified status code. This is an explicit contract, different from default inference based on the operation's value.

Choosing an extension also maintains separation of responsibilities: the base endpoint expresses operations and results, and the extension handles HTTP-specific presentation. If the endpoint is exposed over JMX, JMX invocation and results do not have these HTTP 200/404 status codes.

Do not blindly apply every familiar controller return type to Actuator. When you need to control an operation's HTTP status code, use a mechanism supported by Actuator and verify it on the web stack in use.

## 9. How to Read a Response Error by Stage

A useful diagnostic sequence:

1. **Availability:** is the endpoint a bean, enabled, and exposed on the right protocol? Are you using the right port/base path?
2. **Security:** was the request blocked by authentication, authorization, or CSRF before reaching the operation?
3. **Mapping:** do the path and HTTP method match?
4. **Content types:** do the body `Content-Type` and response `Accept` match?
5. **Input:** are required parameters present and convertible?
6. **Execution:** did the operation run, mutate state, and what result did it return?
7. **Response adaptation:** is the default status or `WebEndpointResponse` being used?

For example, to explain a 404, determine whether it occurred because no mapping was found, because Read returned `null`, or because an extension explicitly returned 404. Simply seeing the word `flags` in the URL is not enough to conclude.

Similarly, a 405 is not fixed by renaming the Java method; you need to call the right HTTP method or redesign the API type. A 400 due to missing `enabled` is not fixed by changing the return type to `void`; the input needs to be fixed.

The adapter's behavior is the bridge between the operation and HTTP. It does not replace business rules, transactions, concurrency handling, or operation execution permissions in the application.

## 10. Reinforcement Exercises

1. Change `update()` from `void` to returning `FlagView`. Keep `@WriteOperation`. Predict the HTTP method, status code, and body after the change.
2. Make `find()` return an object representing “no data” instead of `null`. Explain why the default HTTP status can change even though the path did not change.
3. Change `snapshot()` to return an empty map in all cases. Compare with returning `null`.
4. Keep `put()` but send PUT from the caller. Identify which component needs to change for the request to be compatible with the current operation.
5. Toggle `demo.strict-delete` on and off, then delete the same name twice. Explain the difference between the default status and the extension-specified status.
6. Write tests for missing parameters, invalid boolean type, wrong HTTP method, wrong Content-Type, and unsupported Accept. Check both the response status and the map state after the request.

When explaining an outcome, state all of: annotation, path, input, Java return value, and the class producing the HTTP status code. That cross-check helps distinguish mapping errors from operation outcomes and custom response policies.
