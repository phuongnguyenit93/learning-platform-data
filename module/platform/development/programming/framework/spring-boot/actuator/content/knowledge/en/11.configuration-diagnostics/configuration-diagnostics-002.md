# Looking Up a Specific Property and Understanding Masked Values

## 1. Starting from a configuration question

Suppose an application calls an external service using the property `demo.client.timeout`. The configuration file specifies `2s`, but the deployment environment might override it to `5s`. To diagnose, you need to know whether the property exists in the running process, which source currently takes precedence, and whether the response permits viewing the value.

Spring Boot Actuator provides a route for looking up a single property:

```http
GET /actuator/env/demo.client.timeout
```

This is a way to observe the application's `Environment`. Useful information includes the effective source, the sources that also declare the property, and the origin location when that source can provide it. The API is documented at [Spring Boot 3.3 Environment endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html#_retrieving_a_single_property).

Three questions should be answered separately:

1. **Has the property been found?** The property may not have been loaded, may have the wrong name, or may reside in a different profile.
2. **Which source is effective?** A value from startup arguments can override configuration in a file.
3. **To what extent can the value be viewed?** The data may exist and be actively used even though the response only shows `******`.

Example:

```json
{
  "property": {
    "source": "commandLineArgs",
    "value": "******"
  }
}
```

This is an excerpt from the response. It shows that the effective value comes from `commandLineArgs` and that the returned value has been masked. You cannot conclude from this body alone whether the real value is `2s`, `5s`, empty, or a literal string of six asterisks.

In Spring Boot 3.3, the default policy masks all values on the `env` endpoint, even a property whose name does not suggest a secret. Therefore, seeing masking on `demo.client.timeout` can be completely normal behavior.

## 2. Reading the response by source and precedence

A single-property lookup response may contain the following components:

| Component | How to use during diagnostics |
| --- | --- |
| `property.source` | Name of the source providing the property's effective value |
| `property.value` | Value permitted to be returned; may have been masked |
| `activeProfiles` | Currently active profiles |
| `defaultProfiles` | Declared default profiles |
| `propertySources` | Configuration sources in precedence order |
| `propertySources[i].name` | Name of a source |
| `propertySources[i].property.value` | Value of the property in that specific source, if present; may also be masked |
| `propertySources[i].property.origin` | Origin if available, such as the resource and position within the file |

The index `i` in the table is positional notation, not part of the property name. Do not hardcode an array index in diagnostic tools: sources can shift when changing startup methods, adding external configuration, or enabling profiles.

A source appearing in the list without a `property` section means that source does not provide the property being looked up in this response. It does not indicate that the entire source is empty.

### Effective source and overridden sources

In a simple scenario:

```text
commandLineArgs:
    demo.client.timeout = 5s

application.properties:
    demo.client.timeout = 2s
```

Spring Boot prioritizes command-line arguments over file configuration in this case. When no higher-precedence source provides the property, the value read from `Environment` is `5s`. The file still contains `2s`, but editing that value alone will not necessarily change the result of a startup with overriding arguments.

The order of configuration sources defined by Spring Boot is presented in [Externalized Configuration 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html). For a specific process, use the actual response for comparison; avoid guessing solely from the file open in the editor.

If every `value` is `******`, you can still identify the **selected source** via `property.source` and see **which sources also declare the key** via `propertySources`. However, you cannot infer whether the masked values are identical or different.

`origin` helps locate where to check, though not every source has a detailed origin. Source names and paths can vary between running from an IDE, JAR, container, or externally mounted configuration.

## 3. Runnable example with Spring Boot 3.3 and Java 21

The following example is a local lab application using only dummy data and an ordinary timeout property. It requires JDK 21 and Gradle wrapper 8.5 included in the lab directory. The first build needs access to plugin and dependency repositories if the machine has no local cache yet.

Minimal structure:

```text
env-lookup-demo/
  settings.gradle
  build.gradle
  gradlew
  gradlew.bat
  gradle/wrapper/...
  src/main/java/com/example/envlookup/EnvLookupApplication.java
  src/main/resources/application.properties
```

The wrapper files are the standard Gradle wrapper. If using an application that already has the wrapper and corresponding starters, you can place the sample class and configuration within that application's scope.

### 3.1. Build configuration and main class

`settings.gradle`:

```groovy
rootProject.name = 'env-lookup-demo'
```

`build.gradle`, Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

group = 'com.example'
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

Version `3.3.0` is pinned so the example is reproducible within the Spring Boot 3.3 line; when working with a specific project, follow the version chosen and verified by that project.

`src/main/java/com/example/envlookup/EnvLookupApplication.java`:

```java
package com.example.envlookup;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EnvLookupApplication {
    public static void main(String[] args) {
        SpringApplication.run(EnvLookupApplication.class, args);
    }
}
```

This class starts the Spring Boot application; it requires the classpath of the dependencies in the build. Do not run the file with standalone `javac` while omitting the Spring libraries.

### 3.2. Application configuration

`src/main/resources/application.properties`:

```properties
server.address=127.0.0.1
demo.client.timeout=2s
management.endpoints.web.exposure.include=health,env
management.endpoint.env.show-values=never
```

`server.address=127.0.0.1` restricts the lab's listening address to the local machine. Spring Security is not added in the example, so the endpoint has no login step provided by the application. Do not expose this lab configuration on a public address.

`exposure.include=health,env` exposes only the endpoints needed for observation over HTTP. If the project has disabled `env` in another configuration layer, you must also cross-check the endpoint's enabled state. Exposure, caller authentication, and permission to view values are separate control layers.

Explicitly keep `management.endpoint.env.show-values=never` so the lab exhibits predictable behavior when observed. This property configures the output data; it does not change the `demo.client.timeout` value used by the application.

### 3.3. Build and create an override scenario

From the application directory, run in PowerShell:

```powershell
.\gradlew.bat clean bootJar
java -jar build/libs/env-lookup-demo-1.0.0.jar --demo.client.timeout=5s
```

Keep the process running and open another terminal to perform the lookup:

```powershell
curl.exe --fail --silent --show-error 'http://127.0.0.1:8080/actuator/env/demo.client.timeout'
```

This lesson uses port `8080` and the default `/actuator` path. If the port, context path, management base path, or proxy route has been changed, use the URL corresponding to the actual process.

Extract the two required fields instead of pasting the entire JSON into a report:

```powershell
$result = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/env/demo.client.timeout'
$result.property.source
$result.property.value
```

With the sample configuration and startup arguments, the two lines of output are:

```text
commandLineArgs
******
```

This pair confirms that the effective source is command-line arguments and that the response is masking the value. Application code can still read `5s` from `Environment`; masking belongs solely to the diagnostic representation returned.

To see which file sources also declare the key, filter entries that have `property`:

```powershell
$result.propertySources |
    Where-Object { $null -ne $_.property } |
    ForEach-Object {
        [pscustomobject]@{
            Source = $_.name
            Value = $_.property.value
            Origin = $_.property.origin
        }
    }
```

The resource name and line position depend on packaging. Do not copy an `origin` from another run and treat it as evidence for the process currently under inspection.

### 3.4. Verify precedence reasoning

Stop the sample process, then run the same JAR without passing the overriding property:

```powershell
java -jar build/libs/env-lookup-demo-1.0.0.jar
```

In a lab environment with no other overriding source, `property.source` will switch to the configuration source from `application.properties`. `property.value` remains `******` because the masking policy has not changed. Do not use the similarity of the two masked markers to conclude that the real value did not change.

If the source does not switch as expected, check for other configuration in that process's environment: leftover IDE arguments, environment variables, JVM properties, or external configuration. The lab does not require printing every value from those sources.

## 4. What exactly does "masked" mean?

Value masking (sanitization) replaces the value in observation results with a publishable representation. It helps limit sensitive data in responses, does not encrypt properties in memory, and does not null out configuration used by beans.

With the `never` policy, the response for a found key can help confirm the source name and origin without revealing the value's contents. The API implementation belongs to [EnvironmentEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/env/EnvironmentEndpoint.html); masked value handling uses the [Sanitizer](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/endpoint/Sanitizer.html) mechanism.

From `******`, you cannot infer:

- The length of the real value.
- Whether the value is valid from a business standpoint.
- Whether the value equals a default or has been overridden to a different value.
- Whether the key name matched any secret-name list.
- Whether the caller had login permissions or permission to view unmasked values.

The mask could coincide with a real string intentionally configured by a user. When you need to distinguish, rely on policy and controlled application checks; do not guess from six characters in JSON.

### Three value-viewing policies

Configured per endpoint via `management.endpoint.env.show-values`:

| Policy | Behavior when the request is already permitted to reach the endpoint |
| --- | --- |
| `never` | Always mask values |
| `when-authorized` | Show unmasked values only to callers meeting the authorization criteria |
| `always` | Allow all callers who can reach the endpoint to view unmasked values |

A custom `SanitizingFunction` can still mask a value even when the policy permits showing unmasked values. Therefore, successful login does not guarantee every field will be displayed verbatim.

Spring Boot 3.3 rules are described in [Sanitize Sensitive Values](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.sanitization). For HTTP, `when-authorized` checks the authenticated identity and configured roles; if no role is specified, an authenticated identity may qualify to view unmasked values.

Only when there is an appropriate requirement and management channel might a configuration look like:

```yaml
management:
  endpoint:
    env:
      show-values: when-authorized
      roles: ENV_DIAGNOSTICS
```

This illustrates the policy, not a mandatory step of the lab. If the application uses `application.properties` as in the example above, the equivalent representation is:

```properties
management.endpoint.env.show-values=when-authorized
management.endpoint.env.roles=ENV_DIAGNOSTICS
```

Choose one consistent configuration format and verify the effective value. Do not add multiple files simultaneously just to test properties and then forget which settings take precedence over one another.

Configuring `roles` does not create users, grant roles, or protect the HTTP route by itself. Roles must be mapped properly in the security mechanism in use. A Spring Security or gateway layer can block requests before Actuator performs its view-permission check.

`always` grants broad visibility to every request that reaches the endpoint, even when the URL is assumed hard to guess. Do not switch to `always` just to remove masks during routine diagnostics.

### Permission matrix: distinguishing endpoint access from value visibility

Suppose the HTTP route already allows a caller to reach the endpoint and `when-authorized` is configured with role `ENV_DIAGNOSTICS`:

| Caller state at Actuator | Normal value, not masked by a custom function |
| --- | --- |
| No authenticated identity | `******` |
| Authenticated but missing the required role | `******` |
| Authenticated and holding the required role | Unmasked value |

If the HTTP security layer has already rejected the request with `401` or `403`, the caller never reaches this data-reading step. Conversely, `200` with masked values does not prove the caller has permission to view unmasked values.

The JMX branch has different authorization rules from HTTP; do not use observations made over JMX to infer what an HTTP caller will see. This lab examines HTTP.

## 5. Looking up a single key narrows observation

When investigating only `demo.client.timeout`, calling the route for that exact key reduces the amount of data to read and process. There is no need to fetch all of `/actuator/env` and scan visually.

However, exposing the `env` endpoint over HTTP usually also makes the full-environment route available. Calling only one key on the client side does not create an allowlist of readable properties on the server side. If per-key restrictions are needed, restrictions must be designed at the appropriate management layer and the accessible routes verified.

Even when values are masked, responses can still contain source names, profiles, and resource paths. Those details can reveal deployment structure or paths containing usernames. Share only the evidence necessary for the issue being handled.

A short report might read:

```text
Property: demo.client.timeout
Process: local lab application, port 8080
Effective source: commandLineArgs
Value in response: masked per the never policy
Other source also declaring it: application.properties
Conclusion: check startup arguments before editing the file
```

This report does not claim an actual value that has not been observed through an authorized channel. For real secrets, never put secret contents into tickets, chat, screenshots, or URLs to prove they were found.

## 6. Distinguishing a missing property, masking, and failed access

| Observation | Investigation direction |
| --- | --- |
| `200`, has `property` and `value="******"` | Property was found; check source and masking policy |
| `200`, unmasked value visible | Check viewing policy, roles, and whether you are observing the right environment |
| `404` when looking up a key | Key may be absent; must also rule out wrong URL, disabled/unexposed endpoint, or proxy error |
| `401/403` | Check authentication/authorization layer; do not infer whether the key exists from this error |
| `5xx` or connection failure | Investigate processing errors, network/port, and controlled logs; insufficient evidence about the property |

In the example already running the endpoint properly, look up a key that is definitely not declared:

```powershell
curl.exe --silent --output NUL --write-out '%{http_code}' 'http://127.0.0.1:8080/actuator/env/demo.no-such-property'
```

The expected status code is `404`. To interpret the result accurately, compare it against a request to a sample key known to exist on the same process; a single route failure is not enough to prove the key itself is missing.

### Right key name and right process

Use the property name following the application's convention, such as `demo.client.timeout`. When the source is an environment variable, the physical name may use uppercase and underscores; check both the source name and Spring Boot's configuration mapping rules.

Do not equate every `Environment` lookup with the full `@ConfigurationProperties` binding mechanism. If you suspect differences in naming, data type, or default value for a bean, perform targeted checks at that bean's configuration boundary. For example, the string `5s` still needs to be converted and used according to the type defined by the application.

`env` reflects the configuration environment observed at the time of the call. A bean that captured a value at startup may retain that value; the endpoint does not prove that all beans, libraries, or connections have received a dynamic change. Cross-checking actual runtime behavior is then the question to answer.

In multi-replica systems, ensure you are querying the right replica or clearly record which replica was called. Two processes can receive different configurations even when running the same JAR version.

## 7. Repeatable diagnostic workflow

1. **Confirm property name and process.** Record the port/base path, environment, and replica to inspect.
2. **Look up a single key.** Observe the HTTP status code first, then parse the JSON if present.
3. **Read the effective source.** Use `property.source` to locate the configuration layer to cross-check.
4. **Read all sources providing the key.** Use `propertySources` and `origin` when available to identify overridden sources.
5. **Interpret masking according to policy.** Do not conclude the real value or an incorrect password solely from `******`.
6. **Inspect inputs at the selected source.** For startup arguments, check allowed launch/deployment settings; for files, check the process's actual resource/profile.
7. **Observe unmasked values only with proper need and permission.** Prefer evidence without secrets; confirm business behavior with targeted verification.
8. **Re-verify after changes.** Restart or use an update mechanism supported by the application; do not assume editing a file updates running beans.

Do not log the entire `Environment` or call `System.getenv()` and print every value to bypass masking. Doing so creates another data exposure channel, whereas the issue to solve may simply be an overriding argument.

## 8. Lab self-check

With the process running using `--demo.client.timeout=5s` and the `never` policy, perform the following small check:

```powershell
$result = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/env/demo.client.timeout'

if ($result.property.source -ne 'commandLineArgs') {
    throw 'Effective source does not match expected'
}

if ($result.property.value -ne '******') {
    throw 'Value has not been masked per lab contract'
}

foreach ($source in $result.propertySources) {
    if ($null -ne $source.property -and $source.property.value -ne '******') {
        throw 'A source returned an unmasked value'
    }
}

'PASS'
```

Output when conditions hold:

```text
PASS
```

This check verifies the source and masked representation; it does not read the real value for comparison. It also does not replace access control checks for the deployment environment.

Continue with these scenarios:

- Remove the overriding argument, rerun, and explain why the source changes while the masking looks identical.
- Look up a nonexistent key and compare with the sample key known to exist.
- List what can still be learned when all values are masked and what lacks evidence.
- In a test environment with security enabled, test an unauthenticated user, a user missing the role, and a user with the role per the project's policy; use dummy data only.
- If a custom sanitizing function is used, confirm that the value it protects remains masked even when a user is authorized to view other values.

The skill to build is finding the process's exact configuration source and accurately interpreting the limits of the response. Once you distinguish key presence, endpoint access permission, and value-viewing permission, masking becomes explainable information during diagnostics.
