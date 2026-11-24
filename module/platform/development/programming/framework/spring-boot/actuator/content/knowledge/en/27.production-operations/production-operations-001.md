# Defining the Minimum Endpoint Set per Environment and Operational Role

## 1. Starting from the Operational Decisions to Be Made

A running service needs to answer different questions: whether it should receive more requests, whether it needs to be restarted, which version was just deployed, and how resources are changing. Spring Boot Actuator provides management endpoints to support those tasks. Operators must choose what their service actually needs.

A **minimum endpoint set** is a set sufficient to perform the identified tasks, with the smallest necessary data scope and operational permissions. It does not mean a fixed list applied to every application.

For example, an order service running on Kubernetes and scraped by Prometheus may permanently need:

- Two paths for checking liveness and readiness to receive requests.
- One path for exporting metrics for the scraper.
- Selected version information, if the deployment verification process requires it.

Meanwhile, a batch processing program without an HTTP server can push metrics out and use the platform's execution results. That program does not need to add an HTTP server just to have the same endpoint set.

This article uses configuration properties from **Spring Boot 3.3.x**. The matrices below are **illustrative design options** that need to be adjusted according to actual tasks, infrastructure, and data.

## 2. Distinguishing the Four Layers of an Access Decision

In Spring Boot 3.3, `enabled` determines whether an endpoint is turned on; `exposure` determines exposure over HTTP/JMX. By default, only `health` is exposed; `exclude` takes precedence over `include`. These two layers do not yet decide what a caller is allowed to do. [Spring Boot 3.3 endpoint rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing)

A management request can be viewed as passing through four gates:

```text
Does the endpoint exist and meet initialization conditions?
        ↓
Is it exposed on the protocol in use?
        ↓
Can the caller reach the port/path?
        ↓
Is the identity permitted to use that method and data?
```

For example, allowing `prometheus` in the HTTP exposure list does not automatically create an account for Prometheus. Allowing an account to read an endpoint also does not automatically open a network route from where the scraper is located.

Each layer should be recorded with a separate decision:

| Layer | Question to answer |
| --- | --- |
| Availability | Are the required libraries, configuration, and resources present? |
| Exposure | Which endpoints are opened over HTTP, and which over JMX? |
| Network connectivity | From where are connections allowed, through which port, and via a proxy? |
| Authorization and data | Who may call which method, and what data may they see? |

Endpoint names, paths, HTTP methods, and response detail levels are different factors. A policy stating only "the operations team may use Actuator" is still too broad to implement and verify.

## 3. Listing Needs Before Listing Endpoints

For each need, answer six questions:

1. **Who or which system uses it?**
2. **What decision does the data help make?**
3. **Is it needed permanently or only during incident investigation?**
4. **Read-only or does it change state?**
5. **What scope is the data allowed to leave?**
6. **Who is responsible for reviewing and revoking permissions?**

A decision record might look like this:

| Need | Consumer | Frequency | Expected fulfillment |
| --- | --- | --- | --- |
| Stop sending requests to unready instances | Orchestrator | Continuous | Readiness health group |
| Identify instances that need restarting | Orchestrator | Continuous | Liveness health group |
| Track latency and memory over time | Metrics collector | Periodic | Prometheus or the metrics export mechanism in use |
| Confirm the right release | Deployer | Post-deployment | Selected release metadata |
| Find the cause of thread contention | On-call responder | During incidents | Collect thread dump under temporary permission |
| Increase logging for a package to investigate | Authorized change operator | During incidents | Scoped operation with a rollback plan |

If dashboards already answer questions about memory, the support team may only need permission to view the dashboards. They do not necessarily need an additional account to call endpoints directly.

If an endpoint is not tied to a specific user, decision, or process, do not put it in the permanent set yet.

## 4. Matrix by Environment

Assume the illustrative service has HTTP, runs on Kubernetes in staging/production, and uses Prometheus for metrics collection.

| Capability | Local machine, mock data | Shared test environment | Staging | Permanent production |
| --- | --- | --- | --- | --- |
| Basic health | Yes | Yes, limited information | Yes | Yes if there is a consumer |
| Liveness/readiness | When testing deployment flow | When testing orchestrator | Yes, same as production | Yes for the orchestrator |
| `info` | When needed | Selected metadata | When deployment flow needs it | When deployment flow needs it |
| `prometheus` | When testing the collector | When a collector is present | Yes under this assumption | Yes under this assumption |
| `metrics` | Can open to explore | Open per testing needs | Per investigation needs | Not in this permanent set |
| `loggers` | Can use | Separate read/write permissions | Test controlled remediation flow | Only open temporarily when needed |
| `env`, `configprops`, `beans`, `mappings` | Pick specific endpoints to learn/investigate | Do not open broadly to everyone | Scoped investigation only | Not permanently open |
| `threaddump`, `heapdump`, `logfile` | Per test case | Grant permission on request | Per investigation procedure | Per remediation and file management procedure |
| `shutdown` | Only while testing that feature | Not needed for this design | No | No |

There are three points to explain when reviewing the matrix:

**Shared test environments still have permission boundaries.** A business-testing account does not automatically have application management permissions. If copied real data is used, the data must be evaluated according to its actual sensitivity level.

**Staging should prove the production policy works.** If staging opens every endpoint while production closes most of them, a successful test run in staging does not prove the collector and probes still work in production.

**A local machine is a trusted boundary only when connectivity and data match assumptions.** Running the dev profile on a shared host or forwarding ports externally changes that assumption.

### Choosing the Right Metrics Export Path

`metrics` is for inspecting existing measurements, not an API to scrape as a production metrics store. [REST API metrics](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html)

`prometheus` exports in a format for Prometheus scraping. [REST API Prometheus](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/prometheus.html)

This endpoint requires `micrometer-registry-prometheus`. If the system uses another metrics export mechanism, re-evaluate the need to expose it. [Spring Boot metrics system configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html)

Example of adding the dependency in a Gradle project whose versions are managed by Spring Boot:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

This is an addition for an existing Spring Boot project, not a standalone `build.gradle`. Only include this registry when the collection architecture actually uses it.

## 5. Matrix by Role: Read Permissions Also Need Scope

In the illustrative design, the following roles are granted independently; permissions do not automatically imply one another:

| Role | Recommended permanent permission | What must not be inferred from the role |
| --- | --- | --- |
| External client | No management permissions | Must not view metrics, internal metadata, or dumps |
| Orchestrator | GET on exact probe paths | Must not view all health components |
| Metrics collector | GET `/actuator/prometheus` | Must not read `env`, dumps, or change logs |
| Support staff | View dashboards and approved metadata | Must not by default call every endpoint |
| On-call responder | Detailed health permission; investigation permissions added when needed | Does not automatically have state-changing permissions |
| Remediation operator | Specific, time-bound state-changing permissions | Does not have management permissions across all applications and environments |
| Deployment account | Check version and serving status per procedure | Does not need `shutdown` permission just for having deployment permission |

The role names in the table represent an organizational model, not roles automatically created by Spring Boot.

Write permissions specifically enough to be testable:

```text
Environment: production
Identity: metrics collector for the order service
Network source: approved collector deployment zone
Destination: management port 9001
Path: /actuator/prometheus
Method: GET
State-changing permission: no
Owner: platform team
Review trigger: when collection architecture or network permissions change
```

Do not share identities between automated collectors and on-call responders. When an identity is revoked, the blast radius is clearer and access history is also easier to explain.

### Separating Reads from State Changes

The `loggers` endpoint supports GET to read and POST to change log levels. [REST API loggers](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/loggers.html)

Therefore, allowing the path is not enough: permission to "view log levels" and permission to "change log levels" must be two separate decisions. A log-level change procedure should record:

- Specific package/logger and level before the change.
- Purpose, executor, and expiration time.
- Limits on collection duration, volume, and data that may appear.
- How to restore and how to confirm restoration.

For example, raising DEBUG for 10 minutes on a payment processing package is completely different from enabling TRACE for the entire application for many hours. Same endpoint, different impact scope.

## 6. Configuring Allowlists by Profile

The files below are **illustrative configurations to merge into an existing Spring Boot 3.3 application**, containing neither an authentication layer nor network policies. Deploy to shared environments only after implementing and testing the permission matrix from section 5.

### 6.1. Common Configuration Enabling Only Health

`application.yml`:

```yaml
spring:
  jmx:
    enabled: false

management:
  endpoints:
    enabled-by-default: false
    web:
      exposure:
        include: [health]
      discovery:
        enabled: false
    jmx:
      exposure:
        exclude: "*"
  endpoint:
    health:
      enabled: true
      show-details: never
      show-components: never
```

This approach enables each endpoint as needed. The `include` list uses **endpoint IDs**, not URLs. [Enabling and exposing endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)

JMX has its own policy. `spring.jmx.enabled` only governs JMX management provided by Spring; JVM and other library JMX configurations still need to be reviewed if present. [Management over JMX](https://docs.spring.io/spring-boot/3.3/reference/actuator/jmx.html)

Disabling discovery is only an option to reduce the link listing page. Permission verification must still call the paths directly, not just inspect `/actuator`.

### 6.2. Local Machine: Opening Only the Tools in Use

`application-dev.yml`:

```yaml
management:
  server:
    port: 9001
    address: 127.0.0.1
  endpoints:
    web:
      exposure:
        include: [health, info, metrics, loggers]
  endpoint:
    info:
      enabled: true
    metrics:
      enabled: true
    loggers:
      enabled: true
    health:
      show-details: always
      show-components: always
```

Example for a local machine with mock data. A dedicated management port can bind to loopback via `management.server.address`; a dedicated management address requires a different port from the application port. [Management port and address](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html#actuator.monitoring.customizing-management-server-address)

If `env` is needed for investigation, add that specific endpoint and evaluate the returned data. Do not switch to opening everything just to save a few lines of configuration.

### 6.3. Production: Health, Metrics, and Metadata If Needed

`application-prod.yml`:

```yaml
server:
  port: 8080

management:
  server:
    port: 9001
  endpoints:
    web:
      exposure:
        include: [health, prometheus, info]
  endpoint:
    health:
      show-details: when-authorized
      show-components: when-authorized
      roles: [OPS_HEALTH]
      probes:
        enabled: true
        add-additional-paths: true
      group:
        liveness:
          show-details: never
          show-components: never
        readiness:
          show-details: never
          show-components: never
    prometheus:
      enabled: true
    info:
      enabled: true
```

This configuration inherits the common file: other endpoints remain disabled by default. If `info` is not needed, remove it from both the exposure list and the endpoint enablement section.

In the example, `info` is only used when the deployment team has curated the data from `InfoContributor`s. [Application info structure](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/info.html)

Do not put internal host paths, connection configurations, or user identification information into release metadata.

Permission to view health details and permission to reach the path are two separate decisions; `health.roles` does not grant access to other endpoints. [Health response information](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/health.html), [health properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/index.html#appendix.application-properties.actuator)

Network configuration must ensure port 9001 only accepts approved sources. **Changing the port does not create a trust boundary.** If Prometheus runs in another pod, binding the management port to `127.0.0.1` will not match that connectivity pattern.

For staging, use the same endpoint set and permission rules as production, but use staging's identities, collection targets, and network configuration. Do not simultaneously activate the dev profile during a production policy verification run.

## 7. Minimum Health Must Match the Action Behind It

Liveness answers the question of whether it is alive; readiness answers whether it should continue receiving requests. Kubernetes handles failed probes according to the probe type and configured thresholds. [Kubernetes probe mechanism](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

With Spring Boot, health groups have the paths `/actuator/health/liveness` and `/actuator/health/readiness`. Enabling additional paths creates `/livez` and `/readyz` on the application port. [Spring Boot health probes](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes)

In a design with a separate management port, choosing to probe on the application port ensures checks pass through where real requests arrive. Even so, a successful probe response still does not prove every business function works properly.

The following snippet goes inside a `containers[]` element of a Kubernetes manifest; this is not a complete deployment manifest:

```yaml
ports:
  - name: http
    containerPort: 8080
  - name: management
    containerPort: 9001

startupProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 24

livenessProbe:
  httpGet:
    path: /livez
    port: http
  periodSeconds: 10
  timeoutSeconds: 2
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /readyz
    port: http
  periodSeconds: 5
  timeoutSeconds: 2
  failureThreshold: 3
```

The numbers are only a starting point for testing; startup time and load characteristics need to be measured. A startup probe delays liveness/readiness until the startup check succeeds. [Startup probe behavior](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/)

For kubelet to use the example, the probe paths must allow how kubelet actually calls them. At the same time, public routes must not automatically forward management or probe paths externally.

Consider a shared database outage:

- If restarting the application does not fix the database, using that outage as a reason to restart every instance can make recovery harder.
- For readiness, decide whether the application can still serve useful functions or has a fallback mechanism.
- Keep aggregate health for observation and alerting when needed; do not bind the same health check to every operational action.

Including dependencies in readiness needs to be decided per service. Liveness should not depend on external systems. [Spring Boot health group scope](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes.external-state)

## 8. Implementing Authorization Without Expanding Scope Beyond Expectations

The endpoint list in YAML is an input to the authorization policy, not a complete authorization result.

For Servlet applications, `EndpointRequest` provides matchers by endpoint. [EndpointRequest API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html)

When declaring a `SecurityFilterChain` yourself, you must ensure both management paths and the rest of the application are protected; do not continue relying on automatic Actuator security configuration. [Actuator security](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

When translating the permission matrix into actual configuration, verify:

1. The GET rule for probes covers only the approved paths.
2. The collector identity can call only the metrics export point.
3. Detailed health viewers are mapped to the right role.
4. Read permissions do not accidentally allow POST/DELETE.
5. Everything outside the allowlist is handled with an appropriate deny rule.
6. Business API rules remain verified after the change.

These points are implementation requirements of the design, not Java code to copy directly. WebFlux applications need the corresponding reactive security mechanism; do not reuse Servlet configuration as-is.

Do not treat a single 403 response on a write operation as the sole proof of proper authorization. You need to know exactly which layer denied it and still verify permissions when other valid conditions are met.

## 9. Verifying from Effective Configuration to Real Requests

### 9.1. Checking What Configuration Is Actually Running

Review active profiles, environment variables, startup arguments, and external configuration files. In particular, check whether any source expands the endpoint list or alters sensitive properties.

Do not prove production configuration merely by reading `application-prod.yml`. Evidence must be tied to the actual build and startup method.

### 9.2. Creating Test Cases for Both Granted and Denied Permissions

| Test case | Acceptance criteria |
| --- | --- |
| Kubelet calls readiness | Correct readiness status; no details exposed |
| Collector uses valid identity | Reads metrics, correct format |
| Collector identity calls `env` | Cannot read data |
| User with detailed health permission | Sees only information within approved scope |
| Regular user calls management endpoint | Not granted permissions outside the matrix |
| Unapproved network source calls port 9001 | Cannot connect per network policy |
| Calling `loggers`, `heapdump`, `shutdown` in permanent production | Cannot perform operation or retrieve data |
| Calling via public address and directly inside internal network | Both routes comply with their respective policies |

The illustrative commands below are for a machine running the application, with an actual `curl`/`curl.exe` and ports matching the configuration:

```bash
curl --include --max-time 3 http://127.0.0.1:8080/readyz
curl --include --max-time 3 http://127.0.0.1:9001/actuator/health
curl --include --max-time 3 http://127.0.0.1:9001/actuator/env
```

Run additionally from the locations of kubelet, the collector, and an unauthorized source. A successful call from localhost only proves one network route.

For health showing only status, when the group is UP, the body may be:

```json
{"status":"UP"}
```

Do not hardcode response length, every header, or metric values as expected outcomes. Check the meaning of the response against the configuration and application state.

For requests that must be blocked, the result may be 401, 403, 404, or a connection error depending on the handling layer. A single 404 does not prove the endpoint is disabled: it could be the wrong path, wrong port, or handled by a proxy. Cross-check the effective configuration, network route, and identity used for testing.

### 9.3. Checking Responses and Usage Cost

After checking status codes, continue checking:

- Does health expose hostnames, components, or connection information outside policy?
- Does release metadata contain unnecessary internal data?
- Do metric labels contain user identifiers, order IDs, or secrets?
- Is the probe/scrape frequency appropriate for the processing cost?
- Are old tools still using accounts or paths that should be restricted?

Only reduce the endpoint set after knowing who is using them. Closing an undocumented endpoint that monitoring is still using can create an alerting blind spot.

## 10. Diagnostic Endpoints: Open with a Time Limit and Close with Evidence

For endpoints not in the permanent set, prepare a procedure before an incident occurs:

1. Record symptoms and investigation questions; choose the tool that answers those questions.
2. Specify the application instance, endpoint, method, and time limit.
3. Choose the operator, network source, and where data is stored.
4. Assess collection cost; limit call count or size when appropriate.
5. Execute on the right environment and record changes.
6. Restore configuration, revoke permissions, and verify the path is closed.
7. Handle collected files according to retention and access policies.

For example: when investigating a hung instance, you can collect data using internal JVM tools instead of opening another HTTP endpoint. If choosing an endpoint, still limit who can retrieve the data and how results are stored.

With heap dumps or logs, assume files may contain sensitive data until evaluated. Permission to create files, download files, and read files afterward all need to be reviewed.

Do not end the procedure with "issue resolved." The outcome needs to indicate which endpoint was closed, which permission was revoked, which log level was restored, and where investigation files are stored per policy.

## 11. Practice: Choose the Minimum Set and Explain Each Choice

**Scenario:** An order service has three instances on Kubernetes. Prometheus scrapes metrics. The support team has dashboard viewing permissions. The deployment team needs to verify the version after each release.

Produce three deliverables:

1. An endpoint matrix for local machine, shared test, staging, and production.
2. A matrix of identity × path × method × data level.
3. A checklist for granted permissions, denied permissions, and closing permissions after an incident.

**A reasonable option for permanent production:**

- Use `health` to provide the selected probes; probe responses contain only the information needed for the decision.
- Enable `prometheus` because the problem includes a Prometheus scraper.
- Enable `info` if that is the chosen way to verify the version, with approved content.
- The support team uses dashboards; they are not automatically granted Actuator permissions.
- Deep diagnostics and log-level changes follow a temporary permission-granting procedure.

**Variants to explain for yourself:**

- If metrics are exported through another system and there is no Prometheus scrape, is the `prometheus` endpoint still needed?
- If the deployment platform already provides reliable version metadata, is `info` still needed?
- If a feature can still operate when the cache fails, what are the consequences of putting the cache into readiness?
- If a new endpoint is opened in staging without a production need, how will you test the mechanism for closing it?

A good outcome is when every endpoint has a reason to exist, a consumer, permission limits, and verification test cases. When needs change, you can pinpoint exactly which decision needs to be reconsidered.
