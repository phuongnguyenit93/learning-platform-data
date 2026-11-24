# Precedence Order Between Exclude, Include, and Enabled State

## 1. Understanding the Three Decisions Before Reading Configuration

Suppose an application has the `metrics` endpoint. You added it to the HTTP exposure list, yet requests still do not reach the endpoint. Perhaps the endpoint is disabled, or it is simultaneously in the exclude list. To find the exact cause, three decisions must be distinguished:

| Component | Meaning | Scope |
| --- | --- | --- |
| `enabled` | Allows enabling the endpoint | By endpoint ID |
| `include` | Selects endpoints to expose | Per protocol: HTTP or JMX |
| `exclude` | Excludes endpoints from the exposed set | Per protocol: HTTP or JMX |

This article applies to **Spring Boot 3.3.x**, referencing documentation 3.3.13. In this branch, an endpoint must be enabled and exposed to be available over the corresponding protocol; built-in endpoints also depend on auto-configuration conditions. [Endpoint Availability Condition](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

Two core rules:

1. **`enabled=false` blocks the endpoint; putting the ID in `include` does not re-enable it.**
2. **Within the same protocol, `exclude` beats `include`, even when `include` uses `"*"`.** [Spring Boot 3.3 Endpoint Exposure Rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

Therefore, these should be understood as combined conditions. An allow list does not automatically erase a disable or exclude decision.

## 2. Placing Each Property in the Right Spot

Example with ID `metrics`:

```properties
management.endpoint.metrics.enabled=true
management.endpoints.web.exposure.include=health,metrics
management.endpoints.web.exposure.exclude=metrics
```

The configuration is saying:

- Allow enabling `metrics`.
- Select `health`, `metrics` for HTTP.
- Simultaneously exclude `metrics` from HTTP.

Policy result: `metrics` is excluded from HTTP exposure.

Note the property names: `management.endpoint.<id>.enabled` uses **singular `endpoint`**; `management.endpoints.web.exposure.*` uses **plural `endpoints`**. The lists contain IDs like `metrics`, not URLs like `/actuator/metrics`. Under default paths, this ID corresponds to that URL. [Actuator Property Catalog](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

The corresponding JMX properties are:

```properties
management.endpoints.jmx.exposure.include=health,metrics
management.endpoints.jmx.exposure.exclude=metrics
```

Do not use editing the HTTP list to infer that the JMX list also changes.

## 3. Combined Model and Complete Truth Table

For an endpoint and **one protocol under consideration**, let:

- `E`: the effective enable/disable state of the endpoint.
- `I`: whether the ID is selected by the effective `include` list, directly or via `"*"`.
- `X`: whether the ID is excluded by the effective `exclude` list, directly or via `"*"`.

Mnemonic model for the three conditions:

```text
AllowedByPolicy = E AND I AND NOT X
```

This is an explanatory expression, not Java code or the entire endpoint discovery algorithm. It assumes the endpoint supports the protocol under consideration; to actually invoke it also requires supporting libraries/components, protocol infrastructure, paths, and appropriate access permissions.

| E: enabled | I: selected | X: excluded | Passes all three conditions? | Reason |
| --- | --- | --- | --- | --- |
| No | No | No | No | Disabled, and also not selected |
| No | No | Yes | No | Disabled and excluded |
| No | Yes | No | No | `include` does not enable the endpoint |
| No | Yes | Yes | No | Disabled and excluded |
| Yes | No | No | No | Enabled, but not yet exposed on this protocol |
| Yes | No | Yes | No | Not selected, and also excluded |
| Yes | Yes | No | Yes | Satisfies all three conditions |
| Yes | Yes | Yes | No | `exclude` beats `include` |

The table helps answer two common misconceptions:

- "Enabled" does not automatically mean "has an HTTP path."
- "Not excluded" does not automatically mean "selected."

In 3.3 default configuration, the HTTP exposure list selects only `health`. Thus another endpoint does not automatically get HTTP just because you did not write `exclude`. [Default Values of Exposure Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

### How Is the Value of E Determined First?

When analyzing a configuration, obtain the effective value in order:

1. `management.endpoint.<id>.enabled` if set.
2. If there is no individual value, use `management.endpoints.enabled-by-default` if set.
3. If neither is present, use the endpoint's own default.

For example, if the global default is `false` yet `management.endpoint.metrics.enabled=true`, then E for `metrics` is `true`. However, it still must pass I and X. The order for determining E is shown in [Spring Boot 3.3.13 availability condition code](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java).

## 4. Reading Four Configurations That Easily Cause Confusion

The examples below are **independent** configurations; do not merge all `management:` blocks into the same file.

### 4.1. Appearing in Both Include and Exclude

```yaml
management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include:
          - health
          - metrics
        exclude:
          - metrics
```

For HTTP of `metrics`: E=true, I=true, X=true. The result is not exposed.

If the requirement is "allow viewing metrics over HTTP," the change needed in this example is to remove `metrics` from `exclude`. Adding `metrics` to `include` again does not resolve the conflict.

### 4.2. Disabled Yet Still in Include

```yaml
management:
  endpoint:
    metrics:
      enabled: false
  endpoints:
    web:
      exposure:
        include:
          - health
          - metrics
```

For `metrics`: E=false, I=true, X=false. The result is still not provided. If the endpoint is needed, the enable/disable decision must be changed; the exposure list does not replace that decision.

For built-in endpoints auto-configured by Spring Boot, availability state is also used to decide whether to create the related components. Do not treat `enabled=false` merely as an authorization rule for HTTP clients. [Enabled and Exposure Checking Mechanism](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/ConditionalOnAvailableEndpoint.html).

### 4.3. Include Uses Wildcard, Exclude Selects One ID

```yaml
management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include: "*"
        exclude:
          - metrics
```

`metrics` is still excluded from HTTP. The label "select all" does not mean ignoring exclusion decisions.

This is an example to observe the rule, not a recommended endpoint list for every application. When deploying, choose the exposed set according to specific management needs.

### 4.4. Exclude Uses Wildcard, Include Selects One ID

```yaml
management:
  endpoint:
    metrics:
      enabled: true
  endpoints:
    web:
      exposure:
        include:
          - metrics
        exclude: "*"
```

The configuration excludes all endpoints from HTTP, even `metrics` which was individually enabled and selected. There is no "allow exception" by writing a more specific ID in `include`. To stop all HTTP exposure, Spring Boot supports this exact `web.exposure.exclude=*` setting. [Disabling HTTP Exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.disabling-http-endpoints).

In YAML, quotes must be placed around the `"*"` character; do not write `include: *` or `exclude: *`.

## 5. Excluding from HTTP Differs from Disabling the Endpoint

Suppose the operations team wants `metrics` to appear only over JMX, while HTTP serves only `health`. The following example demonstrates the difference between the two protocols:

```yaml
spring:
  jmx:
    enabled: true

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include:
          - health
          - metrics
        exclude:
          - metrics
    jmx:
      exposure:
        include:
          - metrics
  endpoint:
    health:
      enabled: true
    metrics:
      enabled: true
```

Read each protocol separately:

| Protocol | E of metrics | I | X | Policy result |
| --- | --- | --- | --- | --- |
| HTTP | true | true | true | Excluded |
| JMX | true | true | false | Selected for exposure |

In the example, listing `metrics` in both HTTP include and exclude is meant to clarify the conflict rule. When not demonstrating it, you can simply list `health` in the HTTP list.

`spring.jmx.enabled=true` enables Spring-managed JMX; by default this feature is not enabled. The JMX list does not automatically enable a remote JMX port. With the default domain, a JMX tool can connect locally to the JVM and find endpoint MBeans in the `org.springframework.boot` domain. [Management via JMX in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html).

If `management.endpoint.metrics.enabled` is changed to `false`, the endpoint no longer passes condition E on either protocol. This is the practical difference to consider when the requirement is "hide from HTTP" versus "completely disable the built-in endpoint."

## 6. Testing HTTP with One Change at a Time

### Preparation

Use a Spring Boot 3.3.x application that has a main class, `spring-boot-starter-web`, and `spring-boot-starter-actuator`, running on Java 17 or higher. The test assumes:

- The application listens on `localhost:8080`, and the default management path is `/actuator`.
- There is no Spring Security, proxy, custom endpoint, or other configuration source altering the results.
- HTTP is enabled and the components required for `metrics` are provided by the starters.

If a real application already has authentication, test with an authorized account instead of removing protection mechanisms. The codes below are **expected results under the test assumptions**, not results run on every project.

### Initial Configuration

Use the following content in `src/main/resources/application.yml` of the test application:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include:
          - health
          - metrics
  endpoint:
    health:
      enabled: true
    metrics:
      enabled: true
```

Start the application using the project's normal launch method, then run the following command in PowerShell on Windows:

```powershell
curl.exe --silent --output NUL --write-out "%{http_code}\n" "http://localhost:8080/actuator/metrics"
```

With the initial configuration, expected stdout is strictly one line:

```text
200
```

The command discards the body and prints only the HTTP status code and a newline. When you need to inspect data:

```powershell
curl.exe --silent "http://localhost:8080/actuator/metrics"
```

A successful body contains the `names` field listing the currently available metric names; the specific list depends on the application, so do not use a fixed list to judge whether the endpoint is right or wrong. [Metrics 3.3 API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

### Sequence of Changes to Verify

After each row in the table, restart the application and run the HTTP-code-only command again:

| Run | Change from the immediately preceding state | E / I / X of metrics over HTTP | Expected stdout |
| --- | --- | --- | --- |
| A | Keep initial configuration | true / true / false | `200` |
| B | Add `exclude: metrics` under `management.endpoints.web.exposure` | true / true / true | `404` |
| C | Remove the newly added `exclude` property | true / true / false | `200` |
| D | Change `management.endpoint.metrics.enabled` to `false` | false / true / false | `404` |
| E | Change individual enablement back to `true`, remove `metrics` from `include` | true / false / false | `404` |
| F | Add `metrics` back to `include` | true / true / false | `200` |

Each stdout code in the table has a trailing newline as requested by the curl command. You do not need to modify controllers or write Java code to verify this configuration rule.

Key observation from the test: B, D, and E can all produce 404, yet their causes differ. What needs fixing is, respectively, the exclude decision, the enable/disable state, or the selected set.

## 7. Two Types of Precedence That Should Not Be Mixed

The rule that `exclude` beats `include` applies once the **effective values** of each property are known. However, the application also has a step that determines those values from configuration sources.

Example:

- The config file sets `management.endpoint.metrics.enabled=true`.
- At launch, a command-line argument sets `--management.endpoint.metrics.enabled=false`.

With Spring Boot's default command-line argument mechanism, the command-line value can override the value in the file. E after resolving configuration sources is false, and only then are exposure conditions applied. [Configuration Source Order and Command-Line Arguments](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

Separate three questions:

1. **Configuration source:** what is the final value of each key?
2. **Endpoint enablement:** does the individual value, global default, or endpoint default determine E?
3. **Per-protocol exposure:** is the ID selected and not excluded?

Do not reason "`include` is at the end of the file, so it beats `exclude`." Those are two different keys, each with its own role. Changing the presentation order of the two keys within the same valid configuration does not invert the exclusion rule.

## 8. Troubleshooting Without Arbitrarily Expanding Exposure

When an endpoint does not return expected data, write down a line consisting of **ID, protocol, E, I, X**. For example:

```text
metrics | HTTP | E=true | I=true | X=true
```

This line shows that the exclusion policy is blocking it. It helps avoid changing another property just because you also see the word `metrics`.

Then check conditions outside the model:

- **Path and port:** if base path is `/manage`, you must call `/manage/metrics`; if the management port differs from the application port, use the right port. [HTTP Management Path and Port](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html).
- **Endpoint creation conditions:** some endpoints need specific dependencies or beans. E=true does not create missing libraries.
- **Protection mechanisms:** an exposed endpoint may still require authentication and authorization. A 401/403 code must be read alongside security configuration; a filter may also handle the request before path lookup. [Securing Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).
- **Configuration applied:** after editing a file, restart a typical application; do not assume the endpoint changes state immediately.

Avoid three unfounded fixes: adding a duplicate ID to `include`, changing to `include: "*"` without checking `exclude`, or disabling authentication to fix an endpoint that is actually not enabled.

## 9. Scenario-Based Self-assessment

**Question 1.** `enabled=true`, `include=metrics`, `exclude=*`. Is `metrics` exposed over the protocol under consideration?

**Answer:** No. The wildcard in the exclude list matches `metrics`; an individual selection creates no exception.

**Question 2.** `enabled=false`, `include=*`, no exclusions. Is there an HTTP endpoint?

**Answer:** It does not pass the enable/disable condition. Selecting exposure does not re-enable an endpoint.

**Question 3.** `enabled=true`, HTTP excludes `metrics`, JMX selects `metrics` and does not exclude it. Does HTTP failing to reach it prove the endpoint is completely disabled?

**Answer:** No. Check JMX separately along with its infrastructure conditions; HTTP exclusion belongs only to HTTP scope.

**Question 4.** To remove `metrics` from HTTP while keeping it over JMX, which property should be changed?

**Answer:** Edit the HTTP exposure policy, while keeping the enablement decision and the required JMX configuration. If you disable the endpoint individually, you change the shared E condition as well.

**Question 5.** The three cases "disabled", "not in include", and "excluded" can all lead to 404 in the lab. What else must be recorded besides the HTTP code?

**Answer:** Effective E/I/X values for the exact ID and protocol, along with path/port and security conditions. With those facts, configuration changes have a solid basis.
