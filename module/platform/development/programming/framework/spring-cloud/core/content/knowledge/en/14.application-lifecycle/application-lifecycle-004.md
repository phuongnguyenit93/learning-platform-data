# The env Endpoint with POST Operations and Property Rebinding

This lesson belongs to the **Application Lifecycle** chapter of the **SPRING_CLOUD_CORE** module. Spring Boot Actuator provides the `/actuator/env` endpoint for inspecting the `Environment`. When integrated with Spring Cloud Context, this endpoint can also accept **POST** requests to update a property in the running Environment. Spring Cloud publishes an `EnvironmentChangeEvent` for the changed keys; standard listeners use this event to rebind `@ConfigurationProperties` beans and update `logging.level.*` logger levels.

This is a runtime administrative operation, not a mechanism for persisting configuration long-term. The value is written into the current process's Environment; it does not automatically edit YAML files, Config Server, ConfigMaps, or OS environment variables. When the process restarts, temporary changes may be lost if the persistent configuration source has not been updated.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of the Actuator `env` endpoint and the conditions required for it to be available over HTTP.
2. Enable POST operations using `management.endpoint.env.post.enabled`.
3. Restrict which properties are allowed to be updated using `management.endpoint.env.post.valid-keys-regex`.
4. Send a JSON request to modify a property in the running Environment.
5. Explain the roles of `EnvironmentManager` and `EnvironmentChangeEvent`.
6. Distinguish between Environment updates, `@ConfigurationProperties` rebinding, and `@RefreshScope` refreshing.
7. Verify new values in the Environment, bound beans, and business behavior.
8. Identify limitations with `@Value` snapshots, constructor-bound configuration, and stateful beans.
9. Protect the endpoint against unauthorized access, updates to keys outside the allowlist, and sensitive data exposure.
10. Design an update workflow with auditing, rollback, and multi-instance synchronization.

## 2. Where Does the env Endpoint Fit in the Application Lifecycle?

### 2.1. Environment Is the Source for Looking Up Effective Configuration

Spring's `Environment` aggregates multiple `PropertySource` entries such as configuration files, environment variables, JVM system properties, command-line arguments, and integrated configuration sources. When code calls:

~~~java
String mode = environment.getProperty("app.routing.mode");
~~~

Spring looks up sources in precedence order. The value returned is the effective value at lookup time.

The Actuator `env` endpoint allows inspecting property sources and Environment values. When Spring Cloud Context provides the POST operation, a new value can be added to a high-precedence property source in the running Environment. Subsequent lookups can receive the newly updated value.

### 2.2. POST Processing Flow

~~~mermaid
sequenceDiagram
    participant Operator as Operator / automation
    participant Actuator as POST /actuator/env
    participant Manager as EnvironmentManager
    participant Env as Environment
    participant Event as EnvironmentChangeEvent
    participant Rebind as ConfigurationPropertiesRebinder
    participant Logger as LoggingRebinder
    Operator->>Actuator: JSON {name, value}
    Actuator->>Manager: setProperty(name, value)
    Manager->>Env: Write to high-precedence property source
    Manager->>Event: Publish changed key
    Event->>Rebind: Rebind @ConfigurationProperties
    Event->>Logger: Update logging.level.*
    Actuator-->>Operator: Operation result
~~~

This flow has distinct layers:

1. Actuator receives the request and checks that the operation is enabled, exposed, and authorized.
2. EnvironmentManager writes the property into the process's Environment.
3. Spring Cloud publishes an event describing the changed keys.
4. The ConfigurationProperties rebinder updates supported configuration beans.
5. The Logging rebinder applies keys under `logging.level.*`.
6. The application continues running with the new configuration state according to each bean's capabilities.

Not every singleton in the application is recreated. Rebinding is also not synonymous with refreshing the entire ApplicationContext.

## 3. Distinguishing the env Endpoint from Other Management Endpoints

| Endpoint | Primary role | Typical impact |
| --- | --- | --- |
| `GET /actuator/env` | Inspect the Environment and property sources. | Read-only; sensitive values are typically sanitized. |
| `POST /actuator/env` | Add/update a property in the running Environment. | Publishes EnvironmentChangeEvent; rebinds configuration properties and updates logging levels. |
| `POST /actuator/refresh` | Run the Spring Cloud Context refresh workflow. | Reloads configuration via the refresher mechanism and invalidates `@RefreshScope` target caches. |
| `POST /actuator/restart` | Close and restart the ApplicationContext if the capability is enabled. | Performs a lifecycle restart; not an operation to update a single property. |

Key points to remember:

- `env POST` updates the Environment and triggers rebinding.
- `refresh` additionally handles the lifecycle of refresh-scoped beans.
- `restart` affects the ApplicationContext.
- All three endpoints must be governed as administrative operations, with appropriate access controls and auditing.

If a bean requires recreating its target via `@RefreshScope`, POSTing to `/actuator/env` alone is not enough to clear the target cache. Use the corresponding refresh workflow when designing for that requirement and verify the configuration source still holds the expected value after the refresher runs.

## 4. Prerequisites for Enabling POST /actuator/env

Three conditions must be distinguished: whether the endpoint exists, whether it is exposed over HTTP, and whether the write operation is enabled.

### 4.1. Dependencies

The application needs Spring Boot Actuator and a Spring Cloud Context version compatible with the active Spring Boot release train. For Maven projects, starters are normally declared according to the chosen BOM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter</artifactId>
</dependency>
~~~

This is a minimal role-based dependency example. Your project may already bring in Spring Cloud Context via another starter/integration; check the dependency tree and BOM rather than adding duplicate dependencies.

### 4.2. Enabling the POST Operation

Property to enable the write operation:

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
~~~

Without enabling this property, merely exposing the `env` endpoint does not mean the POST operation is available.

### 4.3. Exposing the Endpoint Over HTTP

Spring Boot exposes only the health endpoint over HTTP by default. To call `/actuator/env` over HTTP, add the `env` endpoint ID to the exposure list:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,env
~~~

If the application already has an exposure list, append `env` to the existing list. Do not replace it with `*` merely for testing convenience, as that can open up many other administrative endpoints.

### 4.4. Setting an Allowlist for Permitted Keys

Current Spring Cloud Commons supports a regex restricting which property keys POST is allowed to write:

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(app\.runtime\.(mode|timeout)|logging\.level\.com\.example\.[A-Za-z0-9_.]+)$'
~~~

The example regex permits only:

- `app.runtime.mode`.
- `app.runtime.timeout`.
- Log keys starting with `logging.level.com.example.` followed by a valid logger name portion.

The `^` and `$` anchors bind the expression to the entire key. Dots are escaped to match literal dots in property names. YAML uses single quotes to preserve regex backslashes verbatim.

Build the allowlist around specific property groups. Avoid broad regexes like `.*`, `app\..*`, or allowing arbitrary keys prefixed with `spring.`, `management.`, or `spring.datasource.`. Those groups can alter infrastructure behavior, security, or application lifecycle.

### 4.5. A Complete Lab Configuration

~~~yaml
management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(app\.runtime\.(mode|timeout)|logging\.level\.com\.example\.[A-Za-z0-9_.]+)$'
      show-values: when-authorized
      roles: OPS_ADMIN
  endpoints:
    web:
      exposure:
        include: health,info,env
~~~

This configuration illustrates:
- POST is enabled.
- Only keys matching the allowlist are permitted to be updated.
- The env endpoint is exposed over HTTP.
- Values returned via the env endpoint are displayed only according to the configured authorization policy.

Corresponding security configuration is needed so only users with administrative roles can perform the operation. `show-values` controls displaying values in responses; it does not replace authentication/authorization and is not an allowlist mechanism for POST.

## 5. Security Advisory: CVE-2026-59284

Spring published advisory **CVE-2026-59284 – Spring Cloud Commons no allow list for writable env actuator endpoint** on 2026-08-20. The issue is that affected versions lack an allowlist for property keys when the writable `/actuator/env` endpoint is enabled.

Affected version ranges listed in the advisory:

| Spring Cloud Commons line | Affected versions |
| --- | --- |
| 5.0.x | 5.0.0 to 5.0.2 |
| 4.3.x | 4.3.0 to 4.3.3 |
| 4.0.x to 4.2.x | 4.0.0 to 4.2.6 |
| 3.1.x | 3.1.10 and earlier |

Fixed versions noted in the advisory:

| Line | Fixed version |
| --- | --- |
| 5.0.x | 5.0.3 (OSS) |
| 4.3.x | 4.3.4 (Enterprise Support) |
| 4.2.x | 4.2.7 (Enterprise Support) |
| 3.1.x | 3.1.11 (Enterprise Support) |

For applications with POST `/actuator/env` enabled:

1. Upgrade Spring Cloud Commons to the patched version matching your project's support policy.
2. Configure `management.endpoint.env.post.valid-keys-regex` with a narrow allowlist.
3. Never expose the env endpoint to public networks.
4. Enforce authentication and authorization for write operations.
5. Monitor audit logs and property updates.
6. Test that keys outside the allowlist are rejected.

Do not enable the write operation on an affected version and rely on a firewall or a custom proxy-layer regex to substitute for the library patch. Check the actual Spring Cloud BOM because a starter's version is not necessarily identical to the Spring Cloud Commons version.

## 6. Sending a POST Request

### 6.1. JSON Body

Actuator accepts the property name and new value via a JSON body:

~~~json
{
  "name": "app.runtime.mode",
  "value": "safe"
}
~~~

`name` is the key in the Environment. `value` is the string value received by the endpoint; the application's Binder/conversion service converts it to the target type when rebinding configuration properties.

### 6.2. Calling with curl

Example executed in a lab environment configured with authentication:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"app.runtime.mode","value":"safe"}' \
  http://localhost:8080/actuator/env
~~~

Replace credentials with your environment's secure secret mechanism. Do not commit passwords into scripts, store them in shared shell history, or print credentials into logs.

If the system uses tokens instead of HTTP Basic, pass the token in the Authorization header according to your security configuration. If Spring Security enables CSRF protection for this endpoint, the client must send a valid CSRF token; do not disable CSRF application-wide just to get a lab request working.

### 6.3. Changing Another Property

Example updating timeout:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"app.runtime.timeout","value":"1500ms"}' \
  http://localhost:8080/actuator/env
~~~

This key is accepted only if the allowlist regex permits `app.runtime.timeout`.

### 6.4. Updating Logging Levels

Example enabling DEBUG for a package:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"logging.level.com.example.orders","value":"DEBUG"}' \
  http://localhost:8080/actuator/env
~~~

Spring Cloud Context handles `logging.level.*` keys to update logger levels. This is a way to adjust runtime logging verbosity without editing configuration files or restarting the process.

Do not enable DEBUG broadly in production without evaluating log volume, sensitive data exposure, and storage costs.

### 6.5. HTTP Responses

POST is a write operation. A successful response may be `204 No Content` when the operation returns no body; depending on version and implementation, check the actual status code rather than relying on a specific response body.

Common errors:

- `404`: endpoint does not exist or is not exposed.
- `405`: write operation is not enabled or HTTP method is unsupported.
- `400`: request body is missing required fields, has an invalid data type, or the key was rejected by validation.
- `401`: unauthenticated.
- `403`: principal lacks authorization or was rejected by CSRF/security policy.
- `5xx`: error while updating the Environment or rebinding beans.

Exact status codes depend on version, security configuration, and the error raised. Inspect the response body and server logs in a controlled environment.

## 7. EnvironmentManager and EnvironmentChangeEvent

### 7.1. What Does EnvironmentManager Do?

Spring Cloud Context provides `EnvironmentManager` as the entry point for performing local updates on the running application's Environment.

Conceptually, the `setProperty(name, value)` operation:

1. Places the key/value into a high-precedence property source in the current Environment.
2. Enables subsequent lookups to observe the new value.
3. Publishes an event reporting the changed keys for listeners to handle.

These changes are **local and volatile**. They do not write back to YAML files, Config Server, or external configuration sources. If the process restarts, values added by EnvironmentManager may be lost.

### 7.2. EnvironmentChangeEvent Carries the Changed Keys List

`EnvironmentChangeEvent` contains the set of keys that changed. Standard Spring Cloud listeners use this event to:

- Rebind supported `@ConfigurationProperties` beans in the context.
- Update logger levels for `logging.level.*` keys.

An application can add custom listeners if a custom component needs to react to specific keys. Listeners should filter for specific keys, validate new values, and handle errors gracefully.

### 7.3. Not Every Bean Updates Automatically

| Component | Behavior after env POST |
| --- | --- |
| `Environment.getProperty(key)` | Subsequent lookups can observe the new value. |
| Mutable `@ConfigurationProperties` | Rebound via EnvironmentChangeEvent if the bean is in a supported category. |
| `logging.level.*` | Logging rebinder updates the corresponding log level. |
| Singleton with `@Value` injected in constructor/field | Usually keeps the old snapshot; does not re-inject automatically. |
| Constructor-bound `@ConfigurationProperties` / Java record | Not rebound directly via the standard mechanism. |
| `@RefreshScope` bean | env POST does not automatically invalidate the bean's target cache. |
| Custom bean not listening to events | Does not automatically know the property changed. |

Therefore, after a successful POST, inspect both the Environment and the actual beans. Seeing the new value at `/actuator/env` alone does not prove every component is using that value.

## 8. Rebinding @ConfigurationProperties

### 8.1. Mutable Configuration Bean Example

Configuration:

~~~yaml
app:
  runtime:
    mode: standard
    timeout: 800ms
~~~

Mutable bean:

~~~java
@ConfigurationProperties(prefix = "app.runtime")
public class RuntimeProperties {

    private String mode;
    private Duration timeout;

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Register via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties(RuntimeProperties.class)`. The bean can be injected into a service:

~~~java
@Service
public class RoutingService {

    private final RuntimeProperties properties;

    public RoutingService(RuntimeProperties properties) {
        this.properties = properties;
    }

    public String currentMode() {
        return properties.getMode();
    }
}
~~~

When POSTing `app.runtime.mode=safe`, Spring Cloud publishes the event and the rebinder updates the mutable bean. Calling `currentMode()` after rebinding finishes can return `safe`.

### 8.2. Conversion and Validation

Values sent via POST are typically strings. The Binder converts them to the target property types, for example:

- `1500ms` to `Duration`.
- `true` to `boolean`.
- `5` to `int`.
- `ROUND_ROBIN` to an enum if a matching enum constant exists.

If using `@Validated` and Bean Validation, the new configuration must satisfy all constraints. A malformed value or constraint violation can cause rebinding to fail. Check for rebinding errors and inspect application state; do not assume a successful POST response means every bean received the new value cleanly.

### 8.3. Rebinding Is Not an Atomic Transaction Across the Application

Rebinding updates configuration beans through Spring Cloud's mechanism. If a bean has multiple related fields, another thread may read the object while updates are in progress. Consider:

- Using an immutable snapshot if multiple values must remain mutually consistent.
- Updating only properties with clear runtime semantics.
- Avoiding POSTing multiple interdependent keys in separate requests if business rules require them to change simultaneously.
- Maintaining a configuration version/revision to check state.
- Testing behavior under load while properties are updated.

If a group of states must switch as one unit, consider a refresh-scoped target or rolling out instances on a new revision.

## 9. Relationship to @Value and @RefreshScope

### 9.1. @Value Does Not Re-Inject Automatically

Singleton example:

~~~java
@Component
public class GreetingService {

    private final String greeting;

    public GreetingService(@Value("${app.runtime.greeting}") String greeting) {
        this.greeting = greeting;
    }

    public String greeting() {
        return greeting;
    }
}
~~~

`greeting` is injected when the bean is created. POST `/actuator/env` can make Environment return the new value, but it does not invoke this singleton's constructor again. If the bean must use the new value, design a dynamic lookup or an appropriate bean recreation mechanism.

### 9.2. @RefreshScope Is a Different Mechanism

Beans annotated with `@RefreshScope` are accessed through a scoped proxy. The target cache is invalidated during the refresh workflow; the next invocation creates a new target.

POST `/actuator/env` focuses on Environment updates and rebinding. It is not an operation that clears the `RefreshScope` cache. The `/actuator/refresh` endpoint executes Spring Cloud's refresh workflow, including reloading configuration via the refresher and invalidating refresh-scoped targets.

If combining the two mechanisms, define the ordering of source updates, Environment updates, and target invalidation. Do not invoke refresh mechanically if reloading from Config Server could overwrite a value you just updated locally.

### 9.3. Constructor-Bound Configuration

Java records or constructor-bound classes are instantiated from values at binding time. They are not rebound directly by Spring Cloud Context's standard mechanism. If runtime updates are required, choose a mutable configuration bean, a properly designed refresh-scoped snapshot, or a restart/rollout.

## 10. Verifying After an Update

### 10.1. Checking the Environment

You can read a specific key:

~~~bash
curl --user ops-user:REPLACE_WITH_SECRET \
  http://localhost:8080/actuator/env/app.runtime.mode
~~~

The env endpoint may sanitize sensitive values. Do not change global sanitization policies just to view secrets in responses.

### 10.2. Checking Configuration Properties

`/actuator/configprops` provides a summary of `@ConfigurationProperties` beans. Use this endpoint in protected environments to verify that bound beans received the new values.

Do not expose the configprops endpoint publicly by default. Responses can contain sensitive data or internal structural details; retain sanitization and access controls.

### 10.3. Verifying Business Behavior

Ideally, in addition to checking management endpoints, invoke a safe business API to confirm the new value actually produces the expected effect.

For example:
- The new routing mode is used.
- The new timeout applies to subsequent requests.
- The logger emits DEBUG only in the selected package.
- Mutable beans return the new value after rebinding.

Do not create a debug endpoint returning the entire Environment for production. Observe only the necessary non-sensitive keys.

### 10.4. Recording Revisions

In operational environments, each update should record:

- The permitted property key changed.
- The related configuration revision or ticket.
- The user/automation that initiated the request.
- The instance that received the request.
- Timestamp and outcome.
- Before/after values masked if needed.
- Verification results for beans and business behavior.

Never log passwords, tokens, private keys, or secrets in audit logs.

## 11. Each Instance Has Its Own Environment

POST `/actuator/env` updates only the Environment of the instance that receives the request. In a system with multiple replicas, other instances do not automatically receive this value.

Example with three instances:

| Instance | Received POST? | Value after operation |
| --- | --- | --- |
| `orders-1` | Yes | `safe` |
| `orders-2` | No | May still be `standard` |
| `orders-3` | No | May still be `standard` |

To synchronize multiple instances, an intentional distribution mechanism is required:

- Write configuration to a persistent source such as Config Server or a configuration management system.
- Use Spring Cloud Bus to broadcast refresh events when appropriate.
- Use orchestration/automation to invoke the management endpoint on each instance under a controlled workflow.
- Use a rolling deployment if the change requires a uniform revision or restarting resources.

Spring Cloud Config Client does not continuously poll by default to detect Environment changes. Never treat a successful POST on a single replica as proof that the entire cluster updated.

## 12. Controlled Operational Workflow

A suitable workflow for runtime changes:

1. Identify the allowed key and the purpose of the change.
2. Verify the key matches the allowlist regex.
3. Validate the new value against data types and constraints.
4. Record the audit request and revision.
5. Send POST to the target instance.
6. Check the response and server logs.
7. Re-read the Environment and configuration properties.
8. Call a safe business flow to verify behavior.
9. If there are multiple instances, roll out the change to remaining replicas or use a broadcast mechanism.
10. Monitor errors and latency after the change.
11. If results are incorrect, restore the previous value using an allowlist-permitted operation.
12. Update the persistent configuration source if the change must survive restarts.

Do not let direct POST operations become the long-term source of truth. Update the standard configuration management system so the next deployment does not overwrite runtime values backward.

## 13. Practice Exercise: Changing Mode and Timeout

### 13.1. Preparation

Create a Spring Boot application with:

- Spring Boot Actuator.
- Compatible Spring Cloud Context.
- Mutable `@ConfigurationProperties` bean `RuntimeProperties`.
- A lab business endpoint reading `mode` and `timeout`.
- A security policy allowing only administrative roles to access actuator.
- An allowlist regex permitting only the two runtime keys for the lab.

Configuration:

~~~yaml
app:
  runtime:
    mode: standard
    timeout: 800ms

management:
  endpoint:
    env:
      post:
        enabled: true
        valid-keys-regex: '^(app\.runtime\.(mode|timeout))$'
      show-values: when-authorized
      roles: OPS_ADMIN
  endpoints:
    web:
      exposure:
        include: health,env,configprops
~~~

This is a lab configuration. Production requires dedicated review of the security chain, network policies, auditing, and endpoint exposure.

### 13.2. Testing Mode Update

Send:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"app.runtime.mode","value":"safe"}' \
  http://localhost:8080/actuator/env
~~~

Then:

1. Read `app.runtime.mode` from the Environment.
2. Inspect the RuntimeProperties bean.
3. Call the lab business endpoint.
4. Confirm the new mode is active.

### 13.3. Testing Timeout Update

Send:

~~~bash
curl --request POST \
  --user ops-user:REPLACE_WITH_SECRET \
  --header "Content-Type: application/json" \
  --data '{"name":"app.runtime.timeout","value":"1500ms"}' \
  http://localhost:8080/actuator/env
~~~

Check the Environment, bean, and timeout behavior. If a service already created a client/connection pool capturing the timeout in its constructor, rebinding RuntimeProperties does not automatically reconfigure that resource. Evaluate the lifecycle of the bean consuming the timeout.

### 13.4. Testing a Key Outside the Allowlist

Send a disallowed key, for example:

~~~json
{
  "name": "spring.datasource.url",
  "value": "jdbc:postgresql://other-host:5432/orders"
}
~~~

Expected result: the request is rejected because the key does not match the allowlist. Verify that the Environment and DataSource did not change.

### 13.5. Testing an Unauthorized Principal

Send the same request using a principal without the `OPS_ADMIN` role. It must be rejected by the security policy. Inspect audit logs and verify no property was updated.

## 14. Test Matrix

| ID | Scenario | Outcome to verify |
| --- | --- | --- |
| E1 | POST with valid key and valid value. | Environment receives the new value. |
| E2 | POST key outside allowlist. | Request is rejected; value remains unchanged. |
| E3 | POST missing `name` or `value`. | Request fails validation/input check; no unexpected changes. |
| E4 | POST value with wrong type for property. | Rebind/conversion reports error; observe bean and app state. |
| E5 | POST mutable `@ConfigurationProperties`. | Bean is rebound after EnvironmentChangeEvent. |
| E6 | POST property injected via `@Value` into singleton. | Singleton snapshot does not change automatically. |
| E7 | POST property used by `@RefreshScope` target. | Environment changes; target cache is not automatically invalidated by env POST alone. |
| E8 | POST valid `logging.level.*` key. | Logger level changes to the new configuration. |
| E9 | GET env/configprops after POST. | Updated value is observable, with sanitization. |
| E10 | Call POST with insufficient permissions. | Rejected; Environment unchanged. |
| E11 | POST to one replica in a cluster. | Only that replica is updated. |
| E12 | Restart process after POST. | Volatile change disappears if not saved to persistent source. |
| E13 | Using Spring Cloud Commons version affected by CVE. | Writable env is not enabled; upgrade to patched version before use. |
| E14 | Rebind multiple related keys under load. | Check intermediate states and business consistency. |

## 15. Common Pitfalls and Troubleshooting

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `POST /actuator/env` returns 404. | Actuator missing, endpoint unavailable, or not exposed over HTTP. | Check dependencies and `management.endpoints.web.exposure.include`. |
| GET env works but POST does not. | Write operation is not enabled. | Check `management.endpoint.env.post.enabled=true` and Spring Cloud version. |
| POST is rejected even though endpoint is enabled. | Key does not match `valid-keys-regex` or security rejected it. | Check regex, principal, roles, and CSRF policy. |
| Environment has new value but bean is stale. | Bean is not mutable `@ConfigurationProperties` or event/rebind did not complete. | Check bean type, events, and configprops. |
| `@Value` singleton still returns old value. | Value was snapshotted when bean was created. | Use dynamic lookup or design an appropriate refresh scope. |
| Refresh-scoped bean keeps old target. | env POST does not invalidate refresh scope cache. | Run a dedicated refresh workflow if the target needs recreation. |
| New timeout value does not affect client. | Client snapshotted timeout at initialization. | Evaluate client lifecycle and recreate resource safely. |
| POST succeeds but value disappears after restart. | EnvironmentManager stores local/volatile changes. | Update the persistent configuration source. |
| Replicas have different values. | Only one instance received the POST. | Use broadcast/rollout or controlled calls to each instance. |
| Endpoint exposes sensitive values. | Improper exposure, show-values, or security settings. | Keep sanitization, restrict roles, network, and endpoint exposure. |
| POST causes unintended configuration changes. | Allowlist regex is too broad or permits infrastructure keys. | Narrow regex, apply security patches, and audit permitted keys. |
| Rebinding causes errors or inconsistent state. | Invalid values, mutable beans, or interdependent keys. | Validate upfront, update via snapshots/rollout, and monitor rebinder errors. |

## 16. Completion Checklist

- [ ] Can explain the role of `/actuator/env`.
- [ ] Distinguish endpoint availability, HTTP exposure, and write operations.
- [ ] Enabled `management.endpoint.env.post.enabled`.
- [ ] Exposed the env endpoint in the HTTP exposure list.
- [ ] Configured `management.endpoint.env.post.valid-keys-regex` with a narrow allowlist.
- [ ] Know the JSON body format containing `name` and `value`.
- [ ] Can send POST requests using an authenticated administrative client.
- [ ] Can explain that EnvironmentManager stores local/volatile changes.
- [ ] Understand that EnvironmentChangeEvent triggers rebinding of configuration properties and logging levels.
- [ ] Distinguish mutable configuration properties, `@Value` snapshots, and constructor-bound config.
- [ ] Distinguish env POST from refresh scope and restart.
- [ ] Can verify Environment and beans after an update.
- [ ] Know that POSTing one instance does not synchronize other replicas.
- [ ] Upgraded Spring Cloud Commons to a version patched for CVE-2026-59284 before enabling writable env.
- [ ] Have authentication, authorization, CSRF policy, network restrictions, and auditing in place.
- [ ] Have a rollback plan and update the persistent configuration source.

**Official documentation to verify against your project version:**

- [Spring Cloud Commons – Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Environment Changes, rebinding, and POST `/actuator/env` operations.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): management properties of Spring Cloud Context.
- [Spring Security Advisory CVE-2026-59284](https://spring.io/security/cve-2026-59284/): affected versions, fixed versions, and allowlist requirements for the writable env endpoint.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint availability, exposure, security, JSON input, and response semantics.

Always cross-check against your application's Spring Boot/Spring Cloud release train. A POST operation modifies only the running process's Environment; all decisions around rebinding, bean refreshing, updating persistent sources, and cluster synchronization must be verified separately.
