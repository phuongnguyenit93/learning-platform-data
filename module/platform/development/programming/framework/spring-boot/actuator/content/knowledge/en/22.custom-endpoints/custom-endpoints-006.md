# Receiving Query Parameters or Request Bodies and Controlling Required Parameters

An Actuator operation can receive inputs from the URL's query string or properties in a JSON body. However, “having parameters in the Java signature” does not describe the whole contract: you need to know which names are used to bind data, which fields are required, which are allowed to be omitted, when type conversion occurs, and which parts must be validated by business logic.

This lesson uses Spring Boot 3.3.x, Spring MVC, and Java 21. The example is an endpoint that previews inputs for a job request: it returns the received values and defaults, helping observe parameter binding without executing real work.

## 1. Understanding the Input Path

```text
HTTP Request
  → match operation by path and HTTP method
  → read query parameters and/or JSON body
  → look up values by Java parameter names
  → check required parameters and convert types
  → invoke operation method
  → application code enforces business rules
  → build response
```

There are three separate questions:

1. **Is there an input under the required name?** For example, the operation needs `count`, but the body only has `amount`.
2. **Can the value be converted to the Java type?** For example, `"many"` cannot be converted to `int`.
3. **Is the value valid for the business domain?** For example, `-1` converts to `int`, but may not be an allowed job count.

Required parameters address presence, not all business validation. Input reception and type conversion are described in the [Spring Boot 3.3 custom endpoint documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.implementing-custom.input).

When exposed over JMX, operations receive arguments from MBean invocations without a query string or HTTP body. Thus, an `@Endpoint` signature is designed around Actuator's contract rather than defaulting to MVC controller signatures.

## 2. Naming Rules and Top-Level Data

### Query Parameters Are Matched Against Parameter Names

Example signature:

```java
@ReadOperation
public Map<String, Object> read(String name, @Nullable Integer limit)
```

This is an abbreviated signature; the complete class is in section 4. Request:

```http
GET /actuator/jobpreview?name=build&limit=3
```

supplies `name="build"` and the `limit` value is converted to integer `3`. You do not need to add `@RequestParam` to get this input binding.

The name `name` is not a path segment in this example. To take a value from the path, Actuator provides `@Selector`; that is a different input source, not a reason to append `/build` to the URL in use.

### JSON Is Matched from Top-Level Properties

With the signature:

```java
@WriteOperation
public Map<String, Object> write(String name, int count, @Nullable Boolean dryRun)
```

a matching body is:

```json
{
  "name": "build",
  "count": 2,
  "dryRun": false
}
```

The three top-level properties correspond to the three parameters. There is no need to wrap them inside a `request` object. The following body has a different structure:

```json
{
  "request": {
    "name": "build",
    "count": 2
  }
}
```

In this example, it does not supply the top-level `name` and `count` values required by the operation, so it is rejected for missing parameters.

Do not change the signature into a single complex DTO parameter and assume Actuator will process it like `@RequestBody` in a controller. Operation inputs use supported simple types; outputs can still be objects or `Map` to emit JSON.

### Preserving Parameter Names During Compilation

Actuator needs actual parameter name metadata. Java code implementing operations must be compiled with `-parameters`; the Spring Boot Gradle plugin and Maven configurations using `spring-boot-starter-parent` support this.

If invoking `javac` manually, the flag needed is `-parameters`. If using a custom build, verify the configuration of the exact compilation task and running classes. Variable names visible in source code or an IDE do not guarantee metadata is present in the class file.

Renaming `count` to `amount` can change the input name bound to the operation. Treat parameter names as part of the endpoint contract, not merely a detail for cleaner code.

## 3. Required, Optional, and Default Values

An operation parameter is required by default. To allow omission, this Java example uses `org.springframework.lang.Nullable`.

| Declaration | When Input Is Missing | Key Takeaway |
| --- | --- | --- |
| `String name` | Rejected | Reference types do not make a parameter optional by themselves |
| `Integer limit` | Rejected | Using a wrapper is not enough to allow omission |
| `int count` | Rejected | Not automatically filled with `0` when the request omits the field |
| `@Nullable Integer limit` | Can receive `null` | Application code chooses the default |
| `@Nullable Boolean dryRun` | Can receive `null` | Must preserve an explicit `false` sent by the caller |

If `null` can be received, use a reference type such as `Integer` or `Boolean`, not primitive `int` or `boolean`, to represent that state.

`@Nullable` does not supply a default value automatically. For example:

```java
int effectiveLimit = limit == null ? 10 : limit;
boolean effectiveDryRun = dryRun == null ? true : dryRun;
```

These are two expressions from the complete example, showing that defaults are an application choice. The value `false` is preserved; it is not treated as missing and replaced with `true`.

Do not infer that `Optional<T>` or `@RequestParam(defaultValue = "...")` will automatically deliver the full behavior of MVC controllers. For operations here, the optional contract is expressed explicitly with `@Nullable` and default handling.

## 4. Complete Practice Project

### 4.1. Build Configuration and Endpoint

Prepare a standalone Gradle project with a compatible Wrapper, such as Gradle 8.5, and JDK 21.

`settings.gradle`:

```groovy
rootProject.name = 'actuator-input-demo'
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

`3.3.0` is the reproducibility baseline of the example; in an existing project, use the managed 3.3.x version set. The BOM above is imported using Gradle's `platform` mechanism.

Create `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    jobpreview:
      enabled: true
  endpoints:
    web:
      exposure:
        include: jobpreview
```

This configuration exposes only the practice endpoint locally. If Spring Security is added, requests must also pass the application's protection policy; authentication/authorization errors must be distinguished from parameter-binding errors.

### 4.2. Startup Class

Create `src/main/java/demo/InputApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InputApplication {
    public static void main(String[] args) {
        SpringApplication.run(InputApplication.class, args);
    }
}
```

### 4.3. Endpoint Receiving Inputs

Create `src/main/java/demo/JobPreviewEndpoint.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.actuate.endpoint.annotation.Endpoint;
import org.springframework.boot.actuate.endpoint.annotation.ReadOperation;
import org.springframework.boot.actuate.endpoint.annotation.WriteOperation;
import org.springframework.lang.Nullable;
import org.springframework.stereotype.Component;

@Component
@Endpoint(id = "jobpreview")
public class JobPreviewEndpoint {
    @ReadOperation
    public Map<String, Object> read(String name, @Nullable Integer limit) {
        int effectiveLimit = limit == null ? 10 : limit;
        return Map.of("name", name, "limit", effectiveLimit);
    }

    @WriteOperation
    public Map<String, Object> write(
            String name, int count, @Nullable Boolean dryRun) {
        boolean effectiveDryRun = dryRun == null ? true : dryRun;
        return Map.of("name", name, "count", count, "dryRun", effectiveDryRun);
    }
}
```

In this class:

- GET requires `name`; `limit` is optional and defaults to `10`.
- POST requires `name` and `count`; `dryRun` is optional and defaults to `true`.
- Each operation only creates a preview from the input data. There is no persistence or job execution.
- The code intentionally omits rules such as requiring non-blank names or positive counts, so the difference between parameter binding and business validation can be clearly observed.

Output uses `Map`, so JSON property order may vary. When comparing results, compare field names and values rather than relying on character ordering of properties.

### 4.4. Startup

On Linux/macOS:

```bash
./gradlew bootRun
```

On PowerShell/Windows:

```powershell
.\gradlew.bat bootRun
```

You can stop the `bootRun` process, package with `./gradlew bootJar` or `.\gradlew.bat bootJar`, and run:

```bash
java -jar build/libs/actuator-input-demo-1.0.0.jar
```

Startup logs vary by environment. The following examples focus on the operation's status and JSON response.

## 5. Sending Query Parameters

The `curl` commands in this lesson use Bash syntax.

### Providing Required Parameter, Omitting Optional Parameter

```bash
curl -i -H "Accept: application/json" "http://localhost:8080/actuator/jobpreview?name=build"
```

Result is `200 OK` with payload:

```json
{"name":"build","limit":10}
```

`limit=10` comes from the default expression in the `read` method, not inferred automatically by Actuator.

### Providing the Optional Parameter

```bash
curl -i -H "Accept: application/json" "http://localhost:8080/actuator/jobpreview?name=build&limit=3"
```

Result `200`:

```json
{"name":"build","limit":3}
```

Query parameters travel through the URL as text; Actuator converts `"3"` to `Integer`.

### Encoding Values with Spaces or Special Characters

```bash
curl -i --get -H "Accept: application/json" --data-urlencode "name=nightly build" --data-urlencode "limit=3" http://localhost:8080/actuator/jobpreview
```

Response payload contains `name="nightly build"`. Use proper URL encoding instead of concatenating values containing `&`, `+`, spaces, or special characters directly into a query string and expecting them to keep their meaning.

### Missing or Wrong Type

```bash
curl -i http://localhost:8080/actuator/jobpreview
curl -i "http://localhost:8080/actuator/jobpreview?name=build&limit=many"
```

Both cases receive `400 Bad Request`, but for different reasons:

- The first case is missing `name`, a required parameter.
- The second case provides `limit`, but `"many"` cannot be converted to an integer.

Optional does not mean ignoring wrong-type values. `@Nullable Integer limit` allows omission, not arbitrary strings.

## 6. Sending a JSON Body

### Supplying Required Fields

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name":"build","count":2}' http://localhost:8080/actuator/jobpreview
```

Result `200` with payload:

```json
{"name":"build","count":2,"dryRun":true}
```

### Preserving an Explicit false Value

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name":"build","count":2,"dryRun":false}' http://localhost:8080/actuator/jobpreview
```

Response payload has `dryRun=false`. Checking strictly for `null` when choosing the default preserves the caller's explicit choice.

### Distinguishing Content-Type and Accept

- `Content-Type: application/json` describes the format of the incoming body.
- `Accept: application/json` describes the response format the caller wants to receive.

Adding `Accept` does not turn a `text/plain` body into valid JSON for the operation. In this example, sending JSON with content type `text/plain` receives `415 Unsupported Media Type`; malformed JSON with JSON content type receives `400`.

When there are multiple operations or different configurations, inspect the mapping predicates and actual response. Do not lump all request errors into “missing parameter”.

### Calling from PowerShell

You can use PowerShell cmdlets to avoid quoting differences when passing JSON to native programs:

```powershell
$previewUri = 'http://localhost:8080/actuator/jobpreview'

Invoke-RestMethod -Method Get -Uri "$($previewUri)?name=build&limit=3"

$previewBody = @{
    name = 'build'
    count = 2
    dryRun = $false
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri $previewUri -ContentType 'application/json' -Body $previewBody
```

Results are parsed into PowerShell objects, so the display format differs from raw JSON strings. HTTP 4xx cases may appear as cmdlet errors, not a sign that the application stopped.


## 7. Distinguishing Missing, null, Empty, 0, and false

The results below apply to this lesson's endpoint, with the remaining required parameters supplied properly.

| Sent Value | Result in Example | What It Proves |
| --- | --- | --- |
| Missing `name` | `400` | Required parameter was not supplied |
| JSON `"name": null` | `400` | `null` does not satisfy a required parameter |
| `name=` in query or JSON `"name": ""` | `200`, keeps empty string | Required does not mean non-empty |
| Name with only spaces | `200`, keeps spaces | Required does not automatically check `isBlank()` |
| Missing `count` | `400` | `int` does not default to `0` when missing |
| JSON `"count": null` | `400` | Null cannot be used for required `count` |
| JSON `"count": 0` | `200`, `count=0` | Has a numeric value; no positive rule yet |
| JSON `"count": -1` | `200`, `count=-1` | Negative numbers still convert to `int` |
| JSON `"count": "2"` | `200`, `count=2` | Type conversion accepts numeric strings in this case |
| JSON `"count": "many"` | `400` | Cannot convert to integer |
| JSON `"count": 2147483648` | `400` | Value exceeds `int` range |
| Missing `dryRun` or JSON `"dryRun": null` | `200`, `dryRun=true` | Application code applies default on null |
| JSON `"dryRun": false` | `200`, `dryRun=false` | False is an explicit value, not missing |
| JSON `"dryRun": "maybe"` | `400` | Optional parameters still must be type-convertible |

Two short requests to test yourself:

```bash
curl -i -X POST -H "Content-Type: application/json" -d '{"name":"","count":0,"dryRun":false}' http://localhost:8080/actuator/jobpreview
curl -i -X POST -H "Content-Type: application/json" -d '{"name":"build","count":null}' http://localhost:8080/actuator/jobpreview
```

The first request is accepted at the example's parameter-binding layer. The second is rejected because `count` cannot accept null under the current contract.

### Do Not Use Required Parameters to Replace Business Validation

If the business contract requires non-blank names and counts greater than zero, you must also check `name.isBlank()` and bounds on `count` before doing work. Having an input, being type-convertible, and being permitted to execute are distinct conditions.

Similarly, `limit` needs an upper bound if used later to read large datasets. Successfully converting a huge number to `Integer` does not prove it fits system capacity.

Do not assume adding `@Valid`, `@NotBlank`, or `@Min` to the signature is enough to get full MVC controller validation behavior. If using Bean Validation, there must be a mechanism invoking the validator and verification that it actually runs.

### Nullable Does Not Always Preserve Original Intent

In this example, omitting `dryRun` completely and sending `"dryRun": null` both pass `null` to the method, which then chooses `true`.

If an API needs to distinguish “omitted means keep existing” from “null means reset”, a single null value in this signature cannot express both intents automatically. Design a contract that expresses intent clearly and test those cases separately.

## 8. Wrong Names, Nested Structures, and Unused Parameters

### Parameter Names Must Match Exactly

Sending `amount` instead of `count` does not create an alias for the Java parameter. Without a `count` value, the request is still missing a required parameter.

Misspelling an optional field is even easier to miss. Request:

```json
{
  "name": "build",
  "count": 2,
  "dryrun": false
}
```

uses `dryrun` instead of `dryRun`. With the Spring MVC/Boot 3.3.0 handler in the example, this mismatched field is not bound to `dryRun`; the method receives null and returns the default `true`.

That means a request can receive `200` without carrying the meaning the caller thought they sent. Do not use “no HTTP error” as the sole proof that every field was used.

### Nested JSON Is Not Flattened Automatically

The body `{"request":{"name":"build","count":2}}` is not equivalent to `{"name":"build","count":2}`. The first structure lacks the top-level fields required by the current signature.

If a complex structured input model and strict JSON schema contract are needed, choose an appropriate design rather than assuming MVC DTO binding applies to technology-neutral operations.

### Type Conversion Is Not Strict JSON Schema Validation

The example accepted both JSON number `2` and JSON string `"2"` for `count`. This is the result of converting to the target type, not a guarantee that the body must use one specific JSON type.

When stricter input formats are needed, specify and check them. For custom Actuator conversions, you can use a converter with the `@EndpointConverter` mechanism; do not treat a converter as a replacement for all input validation rules.

## 9. When Query and JSON Contain the Same Name

Do not design callers to send the same parameter in both places and rely on guesses about precedence.

With the Spring MVC example on Boot 3.3.0, the following case binds the query value:

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" -d '{"name":"body","count":2}' "http://localhost:8080/actuator/jobpreview?name=query&count=9"
```

Response payload is:

```json
{"name":"query","count":9,"dryRun":true}
```

This is the behavior of the stated handler, not a rule to extrapolate across every web stack, version, or custom handler. A better usage contract picks a clear source for each parameter and avoids supplying conflicting values.

The example's POST can also receive values from query parameters. When testing, keep the content type compatible with the operation's mapping predicates:

```bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/json" "http://localhost:8080/actuator/jobpreview?name=query&count=4&dryRun=false"
```

In this lesson's Spring MVC configuration, this request returns `200` with `name=query`, `count=4`, `dryRun=false`. Even so, choosing JSON bodies for POST inputs in examples keeps the contract easier to read and test.

## 10. Diagnosing and Testing at the Right Layer

| Symptom | Layer to Check First |
| --- | --- |
| `400` due to missing input | Parameter names, top-level JSON properties, `@Nullable` marker, and null values |
| `400` due to invalid value | Target type, whether value is convertible, numeric type bounds |
| `400` with truncated or malformed JSON | JSON parser, before entering the operation method |
| `415` | Request Content-Type and consumes predicates |
| `404` | Path, endpoint ID, enablement, and exposure |
| `401` or `403` | Request protection configuration, before blaming parameters |
| Parameter name error during endpoint discovery | Compilation metadata, especially `-parameters` |
| Request succeeds but uses unexpected default | Optional field name, case sensitivity, and query/body source |
| Exception from operation body | Application logic and error mapping, not just required/type conversion |

When a required parameter is missing or cannot be converted to the needed type, Actuator rejects the request before invoking the operation. Conversely, a business exception thrown by the method itself does not automatically become the same kind of parameter conversion error. If you want `400` responses for business rules, implement appropriate error representation/mapping at the web layer and verify it; do not assume every `IllegalArgumentException` becomes `400`.

A direct Java test call:

```java
new JobPreviewEndpoint().write("build", 2, null);
```

only checks how the method picks defaults and builds results. It does not test query extraction, JSON parsing, missing-field detection, or HTTP status selection. To verify the request-handling contract, test through the web handler, such as MockMvc with an Actuator-enabled application context, or against a running application.

Categories of cases to include when testing this endpoint:

1. Complete query, query missing required fields, and query with wrong types.
2. Complete JSON, JSON missing fields, and JSON null.
3. Optional values omitted and explicitly sent.
4. `false`/`0`, empty strings, and whitespace-only strings.
5. Misspelled field names, improper nesting, and malformed JSON.
6. Wrong Content-Type and conflicting inputs if the system could encounter them.

Assert JSON by data values, not property order. For framework errors, check only the parts of the contract that truly matter rather than copying entire error bodies that may change across configurations.

## 11. Self-Check Your Ability to Explain

### Exercise 1: Do Wrappers Make Parameters Optional?

Change `@Nullable Integer limit` to `Integer limit`, recompile, and GET with only `name`.

Result to explain: the request is missing `limit`. A Java variable's ability to hold null does not mean the operation contract allows omitting the parameter.

### Exercise 2: Does the Default Replace false?

Keep the code unchanged; successively omit `dryRun`, send null, and send false.

Result: the first two cases use `true`; the last keeps `false`. Point to the default-selection expression in the method rather than attributing that behavior to the annotation.

### Exercise 3: Why Doesn't count=-1 Fail Type Conversion?

Send `count=-1` and `count="many"`.

Result: negative numbers are valid `int` values at the example's type-conversion layer; the string `"many"` is not. Then design a business rule requiring positive counts, along with a clear error response.

### Exercise 4: Catching Silent Errors in Optional Fields

Send `dryrun=false` then `dryRun=false`, keeping other fields valid.

Compare the response payloads to see that a successful request does not guarantee field names matched. When renaming parameters in code, review callers and contract tests too.

### Exercise 5: Choosing One Clear Input Source

Create two equivalent requests: one POST using only JSON and one POST using only query parameters under the lesson's configuration. Then create a request with conflicting values in both places.

Explain the actual result, then define endpoint usage guidelines so callers do not depend on that conflict.
