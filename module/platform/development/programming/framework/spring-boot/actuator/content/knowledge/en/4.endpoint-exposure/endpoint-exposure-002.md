# Choosing Default-Enabled Mode or Enabling Only Specified Endpoints

## 1. The Problem to Solve

An application with Actuator does not necessarily need every management capability. Suppose the operations team only needs health checks, version information, and metrics reading. Then a decision is needed: keep the default-enabled policy and disable each unused endpoint, or disable by default and explicitly declare each endpoint allowed to be enabled?

This article uses **Spring Boot 3.3.x**, with reference documentation at 3.3.13. The YAML snippets are configurations for an application that already has Actuator; the HTTP commands in the hands-on section have specific runtime conditions. When upgrading Spring Boot, read the documentation for the exact version before keeping the properties unchanged.

### Three Related Concepts

- **Endpoint enablement:** decides whether an endpoint is allowed to participate in the auto-configuration mechanism.
- **Endpoint exposure:** selects endpoints to be provided over HTTP or JMX.
- **Authentication and authorization:** decides who is allowed to make requests to an exposed endpoint.

In Spring Boot 3.3, an endpoint is available for use when it is enabled and exposed; built-in endpoints must also satisfy their auto-configuration conditions. Therefore, simply setting `enabled: true` is not enough to guarantee a URL can be called. The default in this branch enables built-in endpoints except `shutdown`, while exposing only `health` over HTTP and JMX. [Spring Boot 3.3 Endpoint Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.enabling).

For example, the name `metrics` in the exposure list is the **endpoint ID**, whereas `/actuator/metrics` is the HTTP path under the default path configuration. Do not put an HTTP path into a property that expects an ID. [Actuator URL Conventions](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/index.html#urls).

## 2. How Enable/Disable Values Are Selected

There are two configuration levels:

| Scope | Property | Question answered |
| --- | --- | --- |
| Global default | `management.endpoints.enabled-by-default` | If an endpoint has no individual setting, should it be allowed to be enabled? |
| Per endpoint | `management.endpoint.<id>.enabled` | Is the endpoint with this ID enabled or disabled? |

Pay attention to spelling: the global level uses **plural `endpoints`**, while the individual level uses **singular `endpoint`**. A valid example is `management.endpoint.health.enabled=true`. [Actuator 3.3 Property Catalog](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

In Spring Boot 3.3.13 auto-configuration condition code, the selection order is:

1. If `management.endpoint.<id>.enabled` is present, use that individual value.
2. If no individual value is present but `management.endpoints.enabled-by-default` is set, use the global value.
3. If neither is set, use the default declared by the endpoint itself.

The following table expresses the result of the **enable/disable policy**, without yet considering exposure or library conditions:

| Global value | Individual endpoint value | Enable/disable result |
| --- | --- | --- |
| `false` | Unset | Disabled |
| `false` | `true` | Enabled |
| `true` | `false` | Disabled |
| `true` | Unset | Enabled |
| Unset | Unset | Per the endpoint's own default |

A takeaway to remember: **leaving the global value unset differs from explicitly setting the global value to `true`**. This follows directly from the processing order in [`OnAvailableEndpointCondition` in 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/endpoint/condition/OnAvailableEndpointCondition.java).

## 3. First Approach: Keep Defaults, Disable Unneeded Endpoints

This approach is often called **opt-out (enabled by default, then exclude)**. The following configuration leaves the global default unset, preserves each endpoint's own default, and explicitly disables `env` and `beans`:

```yaml
management:
  endpoint:
    env:
      enabled: false
    beans:
      enabled: false
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
```

Read the configuration via two independent questions:

- For `env`, `beans`: there is an individual decision to disable them.
- For HTTP: the selected list consists of `health`, `info`, and `metrics`.

This example expresses the intent: "keep Actuator's standard behavior, remove two specific capabilities, and provide three endpoints for operations." It fits when a team wants to rely on the framework's defaults while managing exceptions individually.

### Case of Explicitly Setting `enabled-by-default: true`

If you want to impose a global default of enabled, important exceptions must be written explicitly:

```yaml
management:
  endpoints:
    enabled-by-default: true
    web:
      exposure:
        include:
          - health
          - info
          - metrics
  endpoint:
    shutdown:
      enabled: false
    env:
      enabled: false
    beans:
      enabled: false
```

In the 3.3 property table, `shutdown` has its own default of `false`. However, per the order in section 2, an explicitly set global value of `true` is evaluated before that individual default. Therefore, this example explicitly disables `shutdown`, avoiding the misconception that its default exception always wins. [Default of `shutdown` Property](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator).

The two ways of writing in this section express two different intents: the first respects each endpoint's individual default; the second imposes a global default and re-declares exceptions. When reviewing configurations, read that intent before counting YAML lines.

## 4. Second Approach: Disable by Default, Enable Only Specified Endpoints

This approach is called **opt-in (enable only when declared)**. Set the global default to `false`, then enable each needed ID:

```yaml
management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include:
          - health
          - info
          - metrics
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
    metrics:
      enabled: true
```

The same policy can be written using `application.properties`:

```properties
management.endpoints.enabled-by-default=false
management.endpoint.health.enabled=true
management.endpoint.info.enabled=true
management.endpoint.metrics.enabled=true
management.endpoints.web.exposure.include=health,info,metrics
```

Use one consistent format for real configuration. If one place uses YAML and another uses properties, configuration source ordering must also be considered rather than treating them as two independently editable copies.

For the opt-in example:

| Endpoint | Enable/disable decision | Included in HTTP list |
| --- | --- | --- |
| `health` | Individually enabled | Yes |
| `info` | Individually enabled | Yes |
| `metrics` | Individually enabled | Yes |
| `loggers` | Per global default: disabled | No |
| `shutdown` | Per global default: disabled | No |

The enabled list is part of the operational contract: "this application intentionally supports the three selected capabilities." When `loggers` is needed later, the person editing must answer both questions: should it be enabled, and should it be provided over HTTP?

Example addition in **the same configuration tree**, after deciding `loggers` is needed:

```properties
management.endpoint.loggers.enabled=true
management.endpoints.web.exposure.include=health,info,metrics,loggers
```

These are two value changes in the existing configuration; do not create another duplicate `management:` YAML block at the same level.

`loggers` has both read and log-level modification capabilities. Therefore, the decision to include it in the operational contract must examine the allowed operations, rather than merely testing a successful GET request. [`loggers` 3.3 API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html).

## 5. Choosing a Policy Based on Operational Needs

| Criterion | Keep defaults, then disable individually | Disable by default, then enable individually |
| --- | --- | --- |
| How intent is expressed | Accept defaults, manage exceptions | Explicitly list each needed capability |
| When adding management needs | Check whether the endpoint is individually disabled | Add an individual enablement decision |
| Question when upgrading versions/adding libraries | Did defaults or available endpoints change? | Does the individually enabled list meet the new need? |
| Maintenance cost | Fewer lines when using many capabilities | Clear list, but requires deliberate updates |
| Suitable situations | Experimental environments or systems actively following framework defaults | Services with a strictly controlled management list |

These are design criteria for the examples in this lesson, not a rule that every production environment must use the same configuration. For instance:

- An experimental application exploring multiple diagnostic tools may use opt-out, with a controlled HTTP list.
- A payment service that only permits health checks and metrics collection may use opt-in so the intent is immediately visible in configuration.
- A team that only wants to stop providing `info` over HTTP while keeping it over JMX should adjust per-protocol exposure; do not use endpoint disabling as if it only affects HTTP.

To choose, start from the endpoint consumers and their tasks: the orchestrator needs `health`, on-call operators need which data, how does the monitoring tool collect metrics? Then write down the enabled endpoint list and the exposure list for each protocol.

If you choose opt-in, remember to include `health` in the enabled list when the deployment platform calls it. Tightening control while accidentally losing the health check path is still an operational failure.

## 6. Hands-on: Changing One Condition at a Time

### 6.1. Conditions of the Test Exercise

Use a Spring Boot **3.3.x** application, Java 17 or higher; Java 21 is suitable. The application has two dependencies whose versions are managed by Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

This is a dependency snippet in a Spring Boot project that already has its plugins and main class set up, not an entire `build.gradle`. The lab does not require writing any business controller.

To make the results table easy to observe, assume the test application:

- Runs directly on `localhost:8080`, using the default `/actuator` base path.
- Has no Spring Security or proxy altering responses.
- Has no other configuration source overriding the properties being tested.
- Uses standard starter configuration, with no custom endpoint sharing the same ID.

If a real system has authentication, use valid credentials and also verify authorization rules; do not disable protection mechanisms just to match the test table.

### 6.2. Starting from the Opt-in Configuration

Put the YAML configuration from section 4 into `src/main/resources/application.yml`, restart the application, and run:

```powershell
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/actuator/health
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/actuator/info
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/actuator/metrics
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/actuator/loggers
```

Each line is a separate command run in PowerShell on Windows. `-o NUL` discards the body and `-w` prints the HTTP code; the commands do not append a newline automatically. Assuming health is `UP`, the expected results in order are:

| URL | Expected HTTP code | What is verified |
| --- | --- | --- |
| `/actuator/health` | `200` | Individually enabled and exposed |
| `/actuator/info` | `200` | Individually enabled and exposed |
| `/actuator/metrics` | `200` | Individually enabled and exposed |
| `/actuator/loggers` | `404` | Not part of the test's enable/exposure policy |

To view the body of `health`:

```powershell
curl.exe -s http://localhost:8080/actuator/health
```

If the aggregated status is `UP` and details are not disclosed, the commonly seen JSON response is:

```json
{"status":"UP"}
```

This is the expected result under the conditions above, not a guarantee that every application is healthy. Body structure and detail visibility depend on health configuration. [`health` API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html).

`info` may return `{}` if there is no contributed information. HTTP 200 with an empty object still differs from the path not existing; to have version details, the corresponding data must be provided. [`info` API and Contributors](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html).

### 6.3. Proving Enablement and Exposure Are Two Conditions

Perform each scenario starting from the configuration in section 4 and restart after each change:

| Scenario | Change | Expected result for `GET /actuator/metrics` |
| --- | --- | --- |
| A | Unchanged | `200` |
| B | Remove individual `metrics.enabled: true`, keep `metrics` in `include` | `404`: global default is disabled |
| C | Restore individual enablement, remove `metrics` from `include` | `404`: not exposed over HTTP |
| D | Restore individual enablement and `include`, add `exclude: metrics` under `web.exposure` | `404`: exclude list wins over include list |
| E | Remove the exclusion change from D, keep individual enablement and `include` | `200` |

These scenarios are deductions applying configuration rules to the described test environment. The same 404 code can stem from two different decisions; therefore, looking at the response code alone is not enough to know which configuration is wrong.

An additional distinction: disabling the `metrics` endpoint changes that Actuator query capability. You cannot conclude from it that all Micrometer metric recording or exporting has been turned off; registries and metric export configurations have their own mechanisms. [Metrics Mechanism in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

## 7. Common Mistakes and How to Find the Cause

### Configuring Only the Exposure List

```properties
management.endpoints.enabled-by-default=false
management.endpoints.web.exposure.include=health,metrics
```

The author wants to use `health` and `metrics` but has not declared individual enablement. The fix for that intent:

```properties
management.endpoint.health.enabled=true
management.endpoint.metrics.enabled=true
```

### Confusing Configuration Levels

- Wrong: `management.endpoints.health.enabled=true`.
- Right: `management.endpoint.health.enabled=true`.
- For the HTTP list, use `management.endpoints.web.exposure.include`.

When there are many similar settings, check the full property path instead of only searching for the word `enabled`.

### Using a Wildcard and Assuming It Enables Everything

`management.endpoints.web.exposure.include=*` is an exposure selection. If the global default is disabled and there is no individual enablement, the wildcard does not replace enablement decisions. In YAML, if the wildcard is truly needed, write `include: "*"` with quotes.

An easily inspected configuration usually explicitly lists the IDs serving current needs; there is no need to use a wildcard just to save a few lines.

### Configuration in the File Differs from the Effective Value

The application may receive properties from profile-specific files, environment variables, or command-line arguments. Therefore, when the YAML file looks right but behavior differs from expectations, check the active profiles and overriding sources for the same key.

For example, a command-line argument setting `--management.endpoint.metrics.enabled=false` can override the enabled value in the config file. Distinguish **precedence among sources for the same key** from **precedence of an individual value over the global value in section 2**. These are two different resolution steps. [Spring Boot 3.3 Configuration Source Order](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### Misreading HTTP Codes or Changing Configuration Without Applying It

For a typical application, endpoint configuration is applied at startup and requires restarting after editing the file; do not assume Actuator reloads these values automatically.

If an issue occurs, check in order:

1. Are the right application, port, and path running?
2. Which libraries or supporting components does the endpoint need, and are they present?
3. What is the effective enable/disable value?
4. Is the ID selected and not excluded on the right protocol?
5. Does the request pass through authentication, authorization, or a proxy?

`401` or `403` usually directs the check toward protection mechanisms. `404` requires examining paths and endpoint conditions. In a customized system, a single HTTP code is not enough to prove exactly one cause.

## 8. Self-checking Your Own Decisions

**Scenario 1:** A service only needs `health` and `metrics`; the team wants every other endpoint to require an individual proposal.

Choose opt-in: set the global default to `false`, individually enable the two IDs, and list both IDs in HTTP exposure. Then test both the allowed URLs and a URL outside the list.

**Scenario 2:** An application is using opt-in and needs to add `info`. Is a change that only adds `info` to `web.exposure.include` complete?

Not yet. You must also add the decision `management.endpoint.info.enabled=true`; then verify the path and response data.

**Scenario 3:** A team says "keep Spring Boot defaults" yet adds `enabled-by-default: true`. Can that be considered a change that merely makes configuration clearer?

It should not be. The selection order in 3.3 lets this global value override an endpoint's own default. Remove the global value if the intent is to keep per-endpoint defaults, or explicitly declare the exceptions to disable.

**Scenario 4:** `metrics` returns 404 after switching to opt-in. Should you immediately change the exposure list to `"*"`?

Check individual enablement first, then the include and exclude lists. Changing one condition at a time will pinpoint the cause and keep the configuration intent readable.
