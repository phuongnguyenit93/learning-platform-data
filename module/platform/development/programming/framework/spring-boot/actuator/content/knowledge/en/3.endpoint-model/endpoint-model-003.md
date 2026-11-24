# Classifying Read, Write, and Delete Operations on Endpoints

An Actuator endpoint can report the current state, change a setting, or remove management data. These are different operations even though they belong to the same management capability and can share part of a path.

In Spring Boot's endpoint model, the three commonly used annotations are `@ReadOperation`, `@WriteOperation`, and `@DeleteOperation`. This lesson helps you choose the right operation type, understand HTTP mapping, and verify behavior with a small endpoint that stores data only in memory.

The examples use Spring Boot 3.3, with the experiment pinned at 3.3.5. Writes and deletes in the experiment affect only simulated data in the learning process.

## 1. An Endpoint Is a Capability, an Operation Is an Action

An **endpoint** is an identifiable management point, such as `health`, `loggers`, or a custom endpoint. An **operation** is an action that the endpoint provides.

An endpoint is not required to have all three types. Only declare the operations that make sense for that capability. An endpoint can also have multiple read operations with different paths.

`@Endpoint` defines a model that can be adapted for exposure technologies such as HTTP or JMX. Therefore, the three operation types are declared at the model level before being mapped to a specific protocol. See [Endpoint — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/annotation/Endpoint.html).

### 1.1. Questions to Choose the Operation Type

| Type | Main question | Example intent |
| --- | --- | --- |
| Read — `@ReadOperation` | What information needs to be retrieved without intentionally changing the managed state? | View a current setting |
| Write — `@WriteOperation` | What change needs to be applied or what management command needs to be executed? | Set a configuration value |
| Delete — `@DeleteOperation` | What data within the management scope needs to be removed or invalidated? | Delete a simulated value or clear a cache |

"Write" does not only mean inserting a new database row. A management command that changes state can also belong to this type.

"Delete" does not mean deleting a Java class, deleting an endpoint bean, or removing the entire management capability. The method body determines which target is removed.

### 1.2. One Path Can Serve Multiple Operations

With the simulated endpoint `labstate` and a key `theme`:

```text
GET    /actuator/labstate/theme  → read value
POST   /actuator/labstate/theme  → set value
DELETE /actuator/labstate/theme  → delete value
```

Same URL does not mean same request: the HTTP method is a key part of selecting the operation.

## 2. Default Mapping Over HTTP

For a web endpoint based on operation annotations:

| Annotation | HTTP method |
| --- | --- |
| `@ReadOperation` | `GET` |
| `@WriteOperation` | `POST` |
| `@DeleteOperation` | `DELETE` |

This is the mapping described by Spring Boot in [Web Endpoint Request Predicates](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.web.request-predicates).

In particular, `@WriteOperation` does not automatically map to `PUT` or `PATCH` just because the Java method is named `update`. The method name expresses intent in code; the annotation and parameters select the operation, path, and input.

### 2.1. Do Not Replace with Regular Controller Annotations

The `@Endpoint` model uses Actuator operation annotations. If you are writing an HTTP controller with `@RestController`, that is a different mapping mechanism.

Do not attach `@PostMapping` to an operation and assume it will change the Actuator mapping. When you need to design a full business HTTP API, choose the appropriate controller model instead of forcing every API into a management endpoint.

### 2.2. When Using JMX

Over JMX, operations are exposed through the MBean mechanism, not by sending `GET` or `POST`. HTTP and JMX exposure are also configured separately.

See [Spring Boot 3.3 — Monitoring and Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html). The method table above only describes how operations are adapted over HTTP; it does not turn an operation into a URL-only concept.

## 3. Choose the Type by Effect, Not Just by Name

### 3.1. Read: Return State Information

A read operation should be designed to retrieve information, not to let callers accidentally trigger a significant management change.

For example, a method named `status` that deletes records after returning a result still has a mutating effect. Renaming it to "read status" does not make it an appropriate read operation.

Reading can still consume CPU, I/O, or produce technical logs. What must be distinguished is the state-changing intent requested by the caller. HTTP safe methods and idempotency semantics are explained in [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2).

### 3.2. Write: Set Values or Execute Commands

A write operation can set a preference, apply configuration, or request a management action.

Built-in example: the `loggers` endpoint uses `POST` to set log levels. Even clearing a logger's configured level is performed in this API via a `POST` request with appropriate data. See [Actuator Loggers REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

That shows you cannot see the word "clear" or "delete" in a description and automatically switch every API to `DELETE`. You must follow the designed contract of the endpoint.

The `shutdown` endpoint also accepts a management command via `POST`, rather than a typical record update. See [Actuator Shutdown REST API 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html). The hands-on exercise does not enable or call this endpoint.

### 3.3. Delete: Remove Data Within a Defined Scope

With the simulated endpoint, deleting can remove a value from an in-memory map. With a cache, the goal might be to clear temporarily cached data.

For example, `CachesEndpoint` has read operations for cache information and `@DeleteOperation` operations to evict caches. See [CachesEndpoint — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/cache/CachesEndpoint.html).

You should clearly state the scope: deleting a single key, a single cache, or all data belonging to the endpoint. Do not use the same vague description for actions with different scopes.

## 4. Operation Path and Input

By default, the HTTP path is formed from the base path, endpoint ID, and path selector parameters.

In the experiment:

```text
base path: /actuator
endpoint id: labstate
selector name: theme
→ /actuator/labstate/theme
```

### 4.1. @Selector Picks a Target on the Path

The parameter `@Selector String name` captures the corresponding path segment. With the URL above, `name` receives `theme`.

`@Selector` does not query a database or check whether the key exists. Your method decides how to use that value.

If there are only operations with a selector, do not assume the root path `/actuator/labstate` also has a read operation. To have an operation at the root path, there must be a matching operation method.

### 4.2. Write Parameters and JSON

With the method:

```text
@WriteOperation
public Map<String, String> write(@Selector String name, String value)
```

This is a signature snippet, not a standalone program. `name` comes from the path, while the request below supplies `value` via JSON:

```json
{
  "value": "dark"
}
```

Operation parameters are required by default. Java needs to retain parameter names via the `-parameters` compiler option so the mapping mechanism has the required information. Inputs in the technology-neutral endpoint model use appropriate simple types; do not assume you can put an arbitrary DTO in parameters as in an HTTP controller. See [Receiving Input](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.input).

If you want optional parameters or custom type conversion, you must design the corresponding contract. This lesson keeps `value` as a required string to focus on observing the three operation types.

### 4.3. Annotations Do Not Write Business Logic for You

`@WriteOperation` does not automatically save data. `@DeleteOperation` does not automatically remove an entry from a map. Annotations help the infrastructure recognize the operation; the Java method body remains responsible for mutations, validation, and scope of effect.

When exposing an operation to operational tools, clearly document the target, input, and expected output so callers do not have to guess.

## 5. Default Response Status Codes of Web Operations

For a standard operation without custom response handling:

| Operation type | With return value | Without return value |
| --- | --- | --- |
| Read | 200 | 404 |
| Write | 200 | 204 |
| Delete | 200 | 204 |

Thus, a delete method that returns a value can produce a `200` response; do not assume every `DELETE` must return `204`.

These codes describe default operation response rules. Specialized endpoints or web extensions may have different contracts. For example, `WebEndpointResponse` helps extensions provide specific HTTP details. See [WebEndpointResponse — API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/web/WebEndpointResponse.html).

If a required parameter is missing or input cannot be converted, the infrastructure can return `400` before invoking the operation body. We will verify the missing `value` case in the example below.

Do not read HTTP status codes in isolation: `404` can come from an unmapped path or from a read operation that returns no data. You need to compare the URL, method, and Java method body.

## 6. Complete Experiment with In-Memory State

We create a `labstate` endpoint holding a key–value map. It has three operations all using the path selector `name`.

The experiment does not use a database, does not change real configuration, and does not clear caches of other applications. The goal is to clearly see which request invokes which operation and how state changes.

### 6.1. Project Setup

Use JDK 17 or later with a compatible Gradle version. Create a new directory, with `settings.gradle`:

```groovy
rootProject.name = 'actuator-operation-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs.add('-parameters')
}

tasks.register('copyDemoLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

The BOM pins versions for reproducibility. In projects using the Spring Boot Gradle Plugin, retaining parameter names is built in; this small Java project declares the option explicitly.

### 6.2. Startup Class

Create `src/main/java/lab/operations/OperationDemo.java`:

```java
package lab.operations;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OperationDemo {
    public static void main(String[] args) {
        SpringApplication.run(OperationDemo.class, args);
    }
}
```

### 6.3. Endpoint with Three Operations

Create `src/main/java/lab/operations/LabStateEndpoint.java`:

```java
package lab.operations;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.actuate.endpoint.annotation.DeleteOperation;
import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.Selector;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "labstate")
public class LabStateEndpoint {
    private final Map<String, String> values = new ConcurrentHashMap<>();

    @ReadOperation
    public Map<String, String> read(@Selector String name) {
        String value = values.get(name);
        return value == null ? null : Map.of("name", name, "value", value);
    }

    @WriteOperation
    public Map<String, String> write(@Selector String name, String value) {
        values.put(name, value);
        return Map.of("name", name, "value", value);
    }

    @DeleteOperation
    public void delete(@Selector String name) {
        values.remove(name);
    }
}
```

Points to connect with the concepts:

- `@Component` registers the class as a bean via application component scanning.
- `@Endpoint(id = "labstate")` identifies the management capability.
- `@Selector` places the target key into the path.
- The read operation retrieves the value without calling `put` or `remove`.
- The write operation sets the value and returns the newly stored data.
- The delete operation removes the value and returns `void`.
- `ConcurrentHashMap` supports individual map operations under concurrency; it does not turn the entire read–write–delete sequence into a transaction.

The data belongs only to the current process. Restarting loses the map. If multiple instances of the application run, each process has its own map; this example does not describe a shared configuration store.

### 6.4. Compile and Run

At the test project root, using PowerShell:

```powershell
gradle copyDemoLibraries
javac -parameters -encoding UTF-8 -cp "lib/*" -d out src/main/java/lab/operations/OperationDemo.java src/main/java/lab/operations/LabStateEndpoint.java
java -cp "out;lib/*" lab.operations.OperationDemo --server.address=127.0.0.1 --server.port=8080 "--management.endpoints.web.exposure.include=health,labstate"
```

If you have a Gradle Wrapper, use the appropriate wrapper instead of the `gradle` command. On Linux/macOS, the classpath separator in the run command uses `:`:

```bash
java -cp "out:lib/*" lab.operations.OperationDemo --server.address=127.0.0.1 --server.port=8080 --management.endpoints.web.exposure.include=health,labstate
```

The test application listens only on the local machine. If port 8080 is already in use, pick a free port and update the call commands consistently.

The project does not add Spring Security. When testing in an application that already has security, appropriate permissions and protections are required. Exposing an endpoint in the `include` list alone does not grant access to everyone.

The application keeps the process running to serve HTTP; the console prints logs that vary per run, not a fixed stdout. Open a second terminal to run the next steps.

## 7. Tracking a Key Through Read, Write, and Delete

Use the key `theme`. All values in this section are test data.

### 7.1. Read Before Data Exists

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator/labstate/theme"
```

Result in the experiment: **404**.

Here the URL has a read operation, yet `values.get("theme")` has no value yet. The method returns `null`, so the read response is `404`. You must not use this code alone to conclude the endpoint is not registered.

### 7.2. Write Value dark

Pipe JSON into `curl.exe`'s stdin to preserve quotes in PowerShell:

```powershell
'{"value":"dark"}' | curl.exe -i -X POST "http://127.0.0.1:8080/actuator/labstate/theme" -H "Content-Type: application/json" --data-binary "@-"
```

Result: **200**, with data shaped like:

```json
{
  "name": "theme",
  "value": "dark"
}
```

Field order and whitespace in JSON are not part of a Java map's contract. Compare field values, not the entire response as a formatted string.

The same `name` comes from the URL, while `value` comes from JSON. The body of `write` executes `put`; the annotation does not perform the storage itself.

### 7.3. Read Again

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator/labstate/theme"
```

Result: **200**, `value` equals `dark`. This is evidence that the write operation changed the state used by the read operation.

### 7.4. Write the Same Key Again with Value light

```powershell
'{"value":"light"}' | curl.exe -i -X POST "http://127.0.0.1:8080/actuator/labstate/theme" -H "Content-Type: application/json" --data-binary "@-"
```

Result: **200**, `value` equals `light`. A subsequent GET also sees `light`.

Because the example uses `Map.put`, writing to the same key replaces the old value. Do not deduce that every `@WriteOperation` has this replacement semantics: another operation may execute an entirely different command.

### 7.5. Delete the Key

```powershell
curl.exe -i -X DELETE "http://127.0.0.1:8080/actuator/labstate/theme"
```

Result: **204**, with no body. The `delete` method called `remove` and returned `void`.

Call GET again:

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator/labstate/theme"
```

Result: **404**, because the data is gone. The endpoint and its read method still exist.

### 7.6. Repeat DELETE

```powershell
curl.exe -i -X DELETE "http://127.0.0.1:8080/actuator/labstate/theme"
```

In this implementation, you still receive **204**. `remove` had nothing to remove, yet the method neither produced an error nor returned different information.

This helps distinguish post-operation state from whether the item existed beforehand. You must not say a `204` response by itself proves the key existed and was just deleted.

Continue testing error requests in section 8 before stopping the application.

## 8. Mismatched or Missing-Data Requests

### 8.1. Using PUT by Mistake

While the application is still running, try requesting the same path using PUT:

```powershell
'{"value":"dark"}' | curl.exe -i -X PUT "http://127.0.0.1:8080/actuator/labstate/theme" -H "Content-Type: application/json" --data-binary "@-"
```

In the Servlet experiment without extra security, the result is **405 Method Not Allowed**. `@WriteOperation` created a POST operation, not a PUT operation.

Renaming the Java method from `write` to `update` does not change the HTTP method.

### 8.2. Missing Required value

To have a clear test state, set `theme=light` again using the POST command in section 7.4, then send:

```powershell
'{}' | curl.exe -i -X POST "http://127.0.0.1:8080/actuator/labstate/theme" -H "Content-Type: application/json" --data-binary "@-"
```

Result: **400 Bad Request**. The operation requires `value`, yet the JSON did not provide it.

In the test run, a GET after the failed request still returned `light`. This is evidence that the valid write branch did not execute with this missing input.

Distinguish input mapping errors from business validation inside the method. If you need length limits or allowed value sets, you must implement them yourself rather than expecting operation annotations to infer them.

### 8.3. Calling the Root Path Without an Operation

```powershell
curl.exe -i "http://127.0.0.1:8080/actuator/labstate"
```

Result in the experiment: **404**. All three methods in the class have a selector, so operations are served at paths that include `name`.

A root path with an endpoint ID does not mean there is always a GET operation listing all data.

### 8.4. Summary of Executed Checks

The following checks were run sequentially against the same process, starting with an empty map:

| Step | Request | Status code | State / condition verified |
| --- | --- | --- | --- |
| 1 | GET before write | 404 | Key does not exist yet |
| 2 | POST `dark` | 200 | Returned value is `dark` |
| 3 | GET | 200 | Reads `dark` |
| 4 | POST `light` | 200 | Returned value is `light` |
| 5 | GET | 200 | Reads `light` |
| 6 | PUT same path | 405 | No PUT operation exists |
| 7 | POST missing `value` | 400 | Required input insufficient |
| 8 | GET after failed request | 200 | Value is still `light` |
| 9 | DELETE | 204 | Empty body |
| 10 | GET after delete | 404 | Value is gone |
| 11 | DELETE again | 204 | Result per current `void` implementation |
| 12 | GET root path | 404 | No read operation at that path |

The table describes one verification pass of the test app in the order above, not a promise that every Actuator endpoint will return the same codes. In other environments, read the actual response alongside its conditions and policies. Stop the test process with `Ctrl+C` when finished.

## 9. Operation Types, Access Control, and CSRF

Classifying operations helps describe their effects. It does not determine who is allowed to call them.

A read operation can return sensitive data; a write operation can alter how the application behaves. You must choose exposure scope and permissions based on actual content rather than assuming GET is always public.

### 9.1. Exposing an Endpoint Does Not Mean Read-Only

The list:

```text
management.endpoints.web.exposure.include=health,labstate
```

selects which endpoints are exposed over the web. In the sample class, `labstate` contains read, write, and delete operations. This list does not mean GET-only.

If the requirement is observation only, design an endpoint with only the needed read operations or apply appropriate access policies to mutating operations. Do not infer permissions just from an endpoint appearing on the discovery page.

### 9.2. Why Does GET Succeed While POST/DELETE Return 403?

With Spring Security, state-changing methods may be subject to CSRF protection in addition to authentication and authorization. Missing required protection tokens can cause requests to be blocked before reaching the operation.

This is what to check when GET works while POST/DELETE fail. It does not prove `@WriteOperation` or `@DeleteOperation` mapped incorrectly. See [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html).

Follow your application's security mechanisms. Do not disable the entire protection layer just to match the status codes of an experiment without Spring Security.

### 9.3. Information to Record When Investigating Access Errors

Record the URL, HTTP method, content type, status code, and post-request state. In secured applications, also check identity/permissions and corresponding CSRF requirements without putting secrets into learning notes.

That makes it possible to separate wrong method, bad input, missing data, and policy blocks.

## 10. Limits to Understand When Designing Operations

### 10.1. Annotations Describe the Contract, Not Prevent Wrong Side Effects

Java still allows a `@ReadOperation` method to call state-mutating code. Therefore, you need to read the method body and verify behavior, not just trust the annotation name.

In the example, the read body only fetches the value. If you add `values.remove(name)` to it, you have changed the operation's meaning and need to redesign it.

### 10.2. Writing the Same Value Does Not Represent All POST Commands

Putting the same value into a map twice leaves the same final state. However, another POST command might enqueue more work, send additional requests, or trigger actions multiple times.

Do not automatically retry every management command just because the previous attempt timed out. The command may have already executed while the response failed to reach the caller. The contract should clarify idempotency and how to confirm the outcome when that matters.

### 10.3. Repeated Deletes Do Not Have to Return the Same Status Code

In the example, `delete` returns `void`, so both calls return `204`. Another design might report specifically when data does not exist.

When evaluating repeated effects, examine the managed state after the operation as well as the response contract. Do not treat the response code of this custom endpoint as a rule for every API.

### 10.4. In-Memory Changes Are Not Durable Changes

The map does not write to a file or database. A `200` from POST only confirms that execution in the sample process returned a result; it does not prove data was durably saved or replicated elsewhere.

Similarly, a map delete operation does not model all recovery, auditing, or transaction requirements of a real system. That is the intentional scope of the experiment to learn operation classification.

## 11. Self-Check on Classification

### Scenario A: Viewing the Number of Pending Jobs

The goal is only to read the current count without altering the queue.

**Classification:** a read operation is the natural choice. Ensure the body truly only observes as contracted and control access if the data is sensitive.

### Scenario B: Requesting a Setting Reload

The goal is to trigger an action that changes active state.

**Classification:** a write operation may be appropriate. When adapted over HTTP in the standard model, the operation uses POST; do not assume it must use PUT just because the description says "update".

### Scenario C: Removing a Test Value

The goal is to remove a specific key in the map.

**Classification:** a delete operation fits the sample design. The endpoint does not vanish; only the data targeted by the body is removed.

### Scenario D: Method Named readAndReset

The method both returns information and resets state.

**Analysis:** there is a mutating effect that must be made explicit. Do not annotate with `@ReadOperation` just because the method returns data. You can separate a read operation and a reset command, or design a management command with a clear contract.

### Practice Exercise

Pick a real management capability and document:

1. Which data or state belongs to the management scope?
2. Which operations are needed, and which ones should not exist?
3. What annotation and HTTP method does each operation have?
4. Does input come from the path, query parameters, or body?
5. Upon success, what are the expected state and response?
6. How do you distinguish bad input, missing data, and insufficient permissions?

You understand classification when you can explain the **intent, mapping, and actual effect** of each operation, and verify them with requests and before–after state.
