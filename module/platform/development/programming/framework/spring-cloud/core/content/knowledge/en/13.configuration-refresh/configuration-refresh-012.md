# Verifying Actual Values Before and After Refresh

A refresh operation is only meaningful when the application actually uses the new configuration. In Spring Cloud, seeing the new value in Config Server or calling the refresh endpoint successfully is not enough to conclude that a running request is already using the new value. You must verify layer by layer: **configuration source**, **process Environment**, **bound or created beans**, and **actual behavior of the configuration-consuming component**.

This lesson presents a repeatable verification workflow before and after refresh. The running example is `order-service` switching `catalog-service`'s endpoint from an old revision to a new revision. We will identify what to observe at each layer, which API/Actuator endpoints to use, how to test, and how to troubleshoot when layers disagree.

## 1. What Needs to Be Proven?

Suppose the initial configuration has:

```yaml
catalog:
  api:
    base-url: https://catalog-v1.internal
    timeout: 2s
    revision: catalog-config-17
```

After updating the configuration source:

```yaml
catalog:
  api:
    base-url: https://catalog-v2.internal
    timeout: 3s
    revision: catalog-config-18
```

The goal is not merely proving revision 18 was saved. You must prove the process loaded that revision, beans use the corresponding values, and subsequent requests actually go to the v2 endpoint.

| Layer | Question to answer | Suitable evidence |
| --- | --- | --- |
| Configuration source | Has the new revision been saved, and which revision is the source serving? | Commit ID, label/version, Config Server response, or source metadata |
| Environment | What is the effective property in the current JVM? | `Environment.getProperty`, PropertySource/origin, or Actuator `env` |
| Configuration bean | Which values does the `@ConfigurationProperties` object hold? | Reading the bean via getters or Actuator `configprops` |
| Consuming bean/resource | Has the client/policy been rebound or recreated? | Safe values from the bean, generation ID, lifecycle logs |
| Actual behavior | Which endpoint/revision do post-refresh requests use? | Request logs at target service, mock server, traces, or metrics with safe labels |

Do not infer one layer from evidence at another layer. For example, Config Server returning the new revision does not prove every replica loaded it; Environment returning the new URL does not prove the HTTP client was recreated.

## 2. Establishing a Non-Sensitive Marker

To observe refreshes, include a non-secret revision identifier in configuration. Example:

```yaml
catalog:
  api:
    base-url: https://catalog-v1.internal
    timeout: 2s
    revision: catalog-config-17
```

The `catalog.api.revision` property is an observation/testing label that helps reconcile state across layers. It does not replace Git or Config Server versions; it is simply a marker released alongside the configuration set.

Do not use API keys, passwords, tokens, or secrets as markers. Such values must never be written into logs, traces, metric labels, or diagnostic endpoints.

A good configuration set can include:
- `revision`: a non-sensitive configuration release identifier.
- `base-url`: target endpoint.
- `timeout`: an observable operational value.
- A few non-sensitive feature flags to verify binding.

## 3. Checking the Configuration Source Before Refresh

When using Spring Cloud Config, first confirm Config Server is serving the right application, profile, and label/revision. Remember Config Server may read from Git, the filesystem, or another backend; commit state and server response state are two separate pieces of evidence.

Source verification steps:

1. Identify the application name, profile, and label requested by the client.
2. Check the revision/commit deployed in the backend.
3. Query Config Server with the exact same application/profile/label as the client.
4. Cross-check `catalog.api.revision`, `base-url`, and `timeout` in the response.
5. Record the timestamp, revision, and environment under check.

For example, with a Config Server using default endpoints, the request looks like:

```text
GET http://config-server:8888/order-service/prod
```

The actual path may vary by context path, profile, label, and how the server is secured. When calling the endpoint, do not put credentials into terminal history or shared logs.

**Passing evidence:** the source returns `catalog-config-18` with the v2 endpoint. If Config Server still returns revision 17, resolve backend, label, cache, or repository refresh issues before inspecting the client.

## 4. Checking the Environment in Each Process

After the client runs its loading/refresh mechanism, read the effective value from the `Environment` of the specific instance being verified.

Example of a diagnostic component returning only non-sensitive properties:

```java
import java.time.Duration;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class CatalogEnvironmentSnapshot {
    private final Environment environment;

    public CatalogEnvironmentSnapshot(Environment environment) {
        this.environment = environment;
    }

    public Snapshot current() {
        return new Snapshot(
                environment.getProperty("catalog.api.revision"),
                environment.getProperty("catalog.api.base-url"),
                environment.getProperty(
                        "catalog.api.timeout", Duration.class)
        );
    }

    public record Snapshot(
            String revision,
            String baseUrl,
            Duration timeout
    ) {}
}
```

This example uses modern Java; if the project does not yet support records, substitute a standard DTO class. Expose snapshots only over secured management channels, or use them in controlled tests/internal logs.

Before refresh, the snapshot is expected to show revision 17, URL v1, and a 2-second timeout. After the Environment is updated, the snapshot must show revision 18, URL v2, and a 3-second timeout.

### 4.1. Effective Values Depend on PropertySource Precedence

If Config Client loaded revision 18 while a higher-precedence PropertySource still declares URL v1, `Environment.getProperty` can continue returning URL v1. In that case, Config Server did not fail to update; a local override source may be winning.

When investigating root cause, check:
- Active profiles.
- Environment variables and JVM system properties.
- Command-line arguments.
- Local/external configuration files.
- PropertySources from Config Client.
- Source ordering and key origin.

Do not look solely at YAML file contents. Read the **effective** value from the instance's Environment.

## 5. Checking the @ConfigurationProperties Bean

A new Environment does not mean the configuration bean has updated. Create a typed configuration bean and read it directly to confirm.

```java
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "catalog.api")
public class CatalogApiProperties {
    private String baseUrl;
    private Duration timeout = Duration.ofSeconds(2);
    private String revision;

    public String getBaseUrl() {
        return baseUrl;
    }

    public void setBaseUrl(String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public String getRevision() {
        return revision;
    }

    public void setRevision(String revision) {
        this.revision = revision;
    }
}
```

Register the bean via `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(CatalogApiProperties.class)` on a configuration class.

Component to inspect the bean:

```java
import org.springframework.stereotype.Component;

@Component
public class CatalogPropertiesSnapshot {
    private final CatalogApiProperties properties;

    public CatalogPropertiesSnapshot(CatalogApiProperties properties) {
        this.properties = properties;
    }

    public CatalogApiProperties getProperties() {
        return properties;
    }
}
```

In production, return a DTO snapshot with selected fields instead of exposing the configuration object directly, especially when a property group may contain credentials or secrets.

### 5.1. Rebinding the Configuration Bean

In applications integrating Spring Cloud Context, Environment changes can publish `EnvironmentChangeEvent`; the rebinder mechanism can rebind managed `@ConfigurationProperties` beans according to version rules. Exact behavior depends on the release train, bean registration style, and active configuration.

Do not conclude rebinding succeeded just because the event was published. Read the bean's getters directly after refresh. If Environment has new values while the bean retains old values, inspect the rebinder, registration, scope, and bean type.

### 5.2. Distinguishing Mutable and Immutable Beans

A JavaBean configuration class with setters can be rebound by the appropriate rebinder mechanism. Constructor-bound objects/records and other bean styles may behave differently depending on the Spring Boot/Spring Cloud version. When runtime updates are needed, explicitly verify whether your integration supports rebinding that object style; if not, consider recreating the bean via refresh scope or using a dedicated update mechanism.

## 6. Checking the Bean/Resource Actually Consuming Configuration

An HTTP client may be constructed once with a URL and timeout at initialization time. Even when Environment and `CatalogApiProperties` are updated, the client can still hold the old endpoint.

Example target built from properties:

```java
import java.time.Duration;

public class CatalogHttpClient {
    private final String baseUrl;
    private final Duration timeout;
    private final String configRevision;
    private final String generationId;

    public CatalogHttpClient(
            String baseUrl,
            Duration timeout,
            String configRevision,
            String generationId) {
        this.baseUrl = baseUrl;
        this.timeout = timeout;
        this.configRevision = configRevision;
        this.generationId = generationId;
    }

    public String baseUrl() {
        return baseUrl;
    }

    public Duration timeout() {
        return timeout;
    }

    public String configRevision() {
        return configRevision;
    }

    public String generationId() {
        return generationId;
    }

    public String fetchCatalog() {
        // Execute HTTP request with current baseUrl and timeout.
        return "request via " + baseUrl + " at " + configRevision;
    }
}
```

If this bean is an ordinary singleton, its factory method does not rerun just because Environment changed. Determine whether the client is:
- Reconfigured via the library's own runtime API.
- Rebound if the bean itself can accept new configuration.
- Recreated via `@RefreshScope`.
- Or restarted/redeployed if the resource does not support safe runtime changes.

### 6.1. Checking the Target Through the Proxy

For refresh-scoped beans, consumers hold a scoped proxy. You can add a non-sensitive generation ID to the target to verify the target was recreated:

```java
import java.time.Duration;
import java.util.UUID;

import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    @RefreshScope
    CatalogHttpClient catalogHttpClient(CatalogApiProperties properties) {
        return new CatalogHttpClient(
                properties.getBaseUrl(),
                properties.getTimeout(),
                properties.getRevision(),
                UUID.randomUUID().toString()
        );
    }
}
```

To verify the new target, you can add a `generationId` created in the factory method or a per-context counter. Calling through the proxy before refresh records generation A. After refresh, the next call through the proxy must yield generation B different from A and revision 18.

Generation IDs are only for observability; do not use them as business keys or distributed request identifiers.

## 7. Checking Actual Request Behavior

Environment values, bean properties, and targets can all be right while requests still fail due to DNS, network, TLS, authentication, or the target service. Final proof must come from actual runtime behavior.

Ways to verify:

- Use a mock HTTP server in integration tests and verify requests hit the new base URL/route.
- Emit safe logs on the target service with request ID, instance ID, and non-sensitive config revision.
- Use distributed traces to see the post-refresh destination host/service instance.
- Measure request success/error and latency metrics before and after.
- Use a side-effect-free verification endpoint rather than testing with real payment or write operations.

Do not log full Authorization headers, cookies, tokens, or sensitive payloads. If logging endpoints, strip query parameters that may contain tokens or personal data.

### 7.1. An In-Flight Request May Still Use the Old Target

Refresh scope does not switch an already-executing invocation to a new target mid-flight. Requests that have started can finish with the old target; subsequent requests through the proxy resolve the current target.

Therefore, when verifying, distinguish:
- Requests sent before the refresh timestamp.
- Requests in flight at the moment of invalidation.
- Requests started after the new target was created.

Use correlation IDs and timestamps to avoid false conclusions when logs from multiple requests interleave.

## 8. Before-Refresh and After-Refresh Workflow

Capture the pre-refresh snapshot using the exact same criteria you will check after refresh.

| Check | Before refresh | Expected after refresh |
| --- | --- | --- |
| Config Server/source revision | `catalog-config-17` | `catalog-config-18` |
| Environment revision | `catalog-config-17` | `catalog-config-18` |
| Environment base URL | `catalog-v1.internal` | `catalog-v2.internal` |
| Environment timeout | 2s | 3s |
| Properties bean | v1 / 2s | v2 / 3s |
| Client target revision | v1 | v2 |
| Target generation | A | B, different from A |
| Actual request | to v1 endpoint | new requests to v2 endpoint |
| Health/metrics | baseline | no abnormal error increase |

A verification sequence can follow these steps:

1. Select a specific instance and record its instance ID.
2. Record the revision from the configuration source.
3. Capture the Environment and properties bean snapshots.
4. Send a probe request and record the target generation/actual destination.
5. Update the source to the new revision.
6. Instruct Config Client/`ContextRefresher` to reload via your active mechanism.
7. Re-read the Environment.
8. Re-read the `@ConfigurationProperties` bean.
9. Refresh the target if the client uses refresh scope.
10. Send a new request through the proxy and verify destination/generation.
11. Repeat across remaining replicas.
12. Reconcile errors, latency, and final revisions.

If any step fails, hold off on declaring "refresh complete" and pinpoint which layer is out of sync.

## 9. Observing with Spring Boot Actuator

Actuator can assist in inspecting Environment and configuration properties at runtime. Commonly used endpoints include:

| Endpoint | Useful information | Limitations |
| --- | --- | --- |
| `/actuator/env` | Environment and PropertySources; can query a specific property | Sensitive values are masked per config; does not prove beans rebound |
| `/actuator/configprops` | `@ConfigurationProperties` beans and bound values | Does not prove downstream clients/resources use the values |
| `/actuator/refresh` | In supported Spring Cloud integrations, triggers refresh | Endpoint alone is not proof of request behavior; depends on version/config |
| `/actuator/health` | Health/readiness status per configured indicators | Health UP does not prove the new revision was applied |

Endpoints must be exposed intentionally. With Actuator, expose only what is needed via `management.endpoints.web.exposure.include` and restrict access with Spring Security/network policies.

Environment/configuration values can contain sensitive information. Keep default masking or an appropriate `show-values` policy; do not enable displaying all values in production merely for debugging. Do not expose the refresh endpoint publicly because it can alter runtime behavior.

### 9.1. Reading Environment and configprops Properly

If `/actuator/env/catalog.api.base-url` shows the v2 URL, that is evidence the instance's Environment reports the v2 value. Next, check `/actuator/configprops` or the bean's getters to confirm the configuration object.

If the two endpoints report different results, check:
- Property source precedence.
- Whether the bean is registered as configuration properties.
- Whether the bean is rebound under the active mechanism.
- Whether the endpoints are reading the same application context/instance.

### 9.2. The Refresh Endpoint Is Not an End-to-End Test

A successful response from the refresh endpoint only confirms the endpoint processed the request per its implementation. It does not automatically prove Config Server had the new revision, every bean updated, new targets were created, or requests reached the new endpoint.

Use it as a trigger step, then run checks/reads at each layer.

## 10. Automated Testing Layer by Layer

Good tests isolate responsibilities so you know where failures originate.

| Test | Setup | Assertion |
| --- | --- | --- |
| Source integration test | Test Config Server/backend containing revision 18 | Client receives right revision/response |
| Environment test | Load revision 17 PropertySource, then replace with revision 18 | `Environment.getProperty` returns revision 18 |
| Binding test | `@ConfigurationProperties` bean is rebound | Getters return new URL/timeout |
| RefreshScope test | Create target A, invalidate, call again via proxy | Target B is created with different generation |
| HTTP integration test | Use v1/v2 mock servers | Post-refresh requests hit mock server v2 |
| Multi-instance test | Two or more app instances | Each instance reports the same revision after receiving trigger |

### 10.1. Testing Environment with a Mutable MapPropertySource

This example tests only Environment and does not replace a Config Client integration test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

class CatalogEnvironmentTest {

    @Test
    void readsNewValueAfterSourceChanges() {
        Map<String, Object> values = new ConcurrentHashMap<>();
        values.put("catalog.api.revision", "catalog-config-17");

        StandardEnvironment environment = new StandardEnvironment();
        environment.getPropertySources().addFirst(
                new MapPropertySource("testCatalog", values)
        );

        assertThat(environment.getProperty("catalog.api.revision"))
                .isEqualTo("catalog-config-17");

        values.put("catalog.api.revision", "catalog-config-18");

        assertThat(environment.getProperty("catalog.api.revision"))
                .isEqualTo("catalog-config-18");
    }
}
```

A mutable map illustrates subsequent lookups seeing new values. In production, Config Client may replace PropertySources or rebuild the Environment structure via its own mechanism; do not use shared map mutation as a substitute refresh solution.

### 10.2. Testing Bean Target Generation

A refresh scope test should:
1. Call the bean through its proxy and record the first generation.
2. Change configuration in the test source.
3. Update/rebind configuration data per the integration under test.
4. Invoke `refresh("catalogHttpClient")` or the corresponding refresh mechanism.
5. Call the proxy again.
6. Assert the new generation differs from the old generation and the target revision is the new revision.

If you only invoke refresh scope without updating Environment/properties first, the test can create a new target that still uses old values. This is a useful test to prove the two operations are independent.

### 10.3. HTTP Tests to Verify the Actual Endpoint

Using mock servers can confirm post-refresh requests go to server v2. A scenario:
- Mock server v1 returns marker `server-v1`.
- Mock server v2 returns marker `server-v2`.
- Initialize target with URL v1 and send a request.
- Update property to URL v2.
- Run the rebind/refresh workflow.
- Send a new request through the proxy.
- Assert the response comes from mock server v2.

Do not assert only that the bean field equals v2; assert the request was actually received by mock server v2. That is evidence at the consumer layer.

## 11. Verifying Across Multiple Replicas

Each replica has its own Environment and beans. Therefore, record state per instance ID rather than collapsing into a single service-wide result.

Example tracking table:

| Instance | Environment revision | Properties revision | Client target revision | Request smoke test |
| --- | --- | --- | --- | --- |
| order-7f8a | 18 | 18 | 18 | v2 PASS |
| order-91bc | 18 | 18 | 17 | v1 FAIL |
| order-a2de | 18 | 18 | 18 | v2 PASS |

In this example, instance `order-91bc` updated its Environment and properties bean, yet the client target still uses revision 17. This indicates the target was not invalidated, the consumer holds an old reference, or the client was created elsewhere.

You can use Spring Cloud Bus or orchestration to send triggers to multiple instances, yet you must check each instance received and applied the new revision. Publishing an event does not prove all consumers processed it successfully.

## 12. Rollback and Recovery When Refresh Is Uneven

If a new revision causes errors, you need a path back to a known-good revision. The rollback workflow must also verify all layers:
1. Restore the configuration source to the previous revision.
2. Confirm Config Server serves the rollback revision.
3. Instruct clients to reload.
4. Confirm each instance's Environment.
5. Rebind or refresh targets.
6. Send a probe request and confirm the old endpoint works.
7. Record any instance that failed to roll back.

Do not just revert the file in Git and consider rollback complete. An instance can still retain the PropertySource or old target from the bad revision. If safe refresh is not possible, execute a planned rolling restart/redeploy.

## 13. Common Errors and Diagnostics

| Symptom | Likely failing layer | Diagnostic direction |
| --- | --- | --- |
| Config Server still returns old revision | Source/backend | Check commit, label, cache, and application/profile |
| Config Server returns new revision, yet Environment is old | Config loading/client | Check refresh trigger, Config Client, connectivity, and PropertySources |
| Environment is new, yet properties bean is old | Binding/rebinder | Check configuration properties registration and rebinding |
| Properties bean is new, yet client target is old | Bean/resource | Check refresh scope, proxy, and target references |
| Target revision is new, yet requests still hit old host | Consumer behavior/network | Check other clients, DNS, proxies, connection pools, and request logs |
| Some replicas old, some replicas new | Trigger distribution | Check events/bus, individual instance IDs, and revisions |
| Refresh endpoint succeeds, yet nothing changed | Wrong expected layer or unchanged source | Re-read source, Environment, bean, and target in order |
| First request after refresh fails | Lazy target creation | Check target creation errors, required properties, and new endpoint connectivity |
| Actuator shows masked values | Security policy | Use non-sensitive snapshots or internal tests; do not expose secrets in production |

An effective rule is finding **the first point where the value diverges from the expected revision**. If source is right but Environment is wrong, do not debug the HTTP client first. If Environment and bean are right but target is wrong, focus on lifecycle/rebinding. If all values are right yet requests fail, investigate the network and destination service.

## 14. Verification Checklist Before Declaring Refresh Successful

- [ ] Correct application, profile, label, and instance identified.
- [ ] Configuration source serves the new revision.
- [ ] Instance Environment holds the new effective values.
- [ ] PropertySource precedence does not override desired values.
- [ ] `@ConfigurationProperties` beans have been rebound or recreated.
- [ ] Consuming beans/resources use the new revision.
- [ ] New requests take the real path to the right endpoint/instance.
- [ ] Old targets released resources where required.
- [ ] All replicas report the expected revision.
- [ ] Post-refresh health, error rates, and latency remain within bounds.
- [ ] Rollback capability exists if a step fails.
- [ ] No secrets appear in logs, traces, metrics, or snapshots.

This checklist supports operations and reviews; it does not replace automated tests or organizational deployment approval policies.

## Key Takeaways

To prove a refresh took effect, verify from source to consumer behavior: **revision at source → effective values in Environment → configuration object → target/client → actual request**. Each layer requires its own evidence. `ContextRefresher`, `EnvironmentChangeEvent`, rebinders, and `RefreshScope` support the update steps, yet do not replace re-reading values, checking every replica, and sending verification requests. Only conclude refresh succeeded once the instance applied the right revision and the component actually handling requests uses the new configuration.
