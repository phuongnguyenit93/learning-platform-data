# Observing Capabilities via features and Registration Status via serviceregistry

> **Chapter:** Observability  
> **Module:** SPRING_CLOUD_CORE

A Spring Cloud application can have many capabilities loaded from different modules: service discovery, load balancing, circuit breakers, service registry, or custom integrations. During operations, knowing that a dependency is in the build file is not enough to confirm the capability was created in the ApplicationContext. Likewise, knowing the application has a discovery bean does not tell you whether the current instance is seen by the registry as UP or OUT_OF_SERVICE.

Spring Cloud Commons provides two complementary Actuator endpoints:

- **`/actuator/features`** shows which features are declared by modules and which ones are recognized as enabled.
- **`/actuator/serviceregistry`** reads the status of the current Registration and allows requesting the provider to update that status.

The first endpoint helps observe the application's capabilities; the second helps observe and control the registration status of the application's own instance. Neither endpoint replaces health/readiness, nor do they provide a complete list of every service in the registry. This lesson explains how to read, combine, and secure those two observability perspectives in **SPRING_CLOUD_CORE**.

## 1. Two Distinct Operational Questions

When a service is not called by clients or a feature does not work, separate two questions:

1. Has the application created the required capability in the ApplicationContext?
2. What status does the current instance currently have in the service registry?

For example, an application may have created `DiscoveryClient` and `LoadBalancerClient` beans, yet its instance is marked `OUT_OF_SERVICE` in Eureka. Conversely, the application may be seen as `UP` by the registry while lacking a LoadBalancer bean because a dependency or auto-configuration was not enabled.

| Scenario | Useful Endpoint | What to Verify |
| --- | --- | --- |
| Unclear which discovery client was created | `features` | Abstract feature DiscoveryClient and implementation class |
| Want to confirm LoadBalancer is in context | `features` | Whether LoadBalancerClient feature is recognized as enabled |
| Instance registered yet receiving no traffic | `serviceregistry` | Current registration status and provider semantics |
| Want to temporarily pull instance out of traffic | `serviceregistry` | Whether the provider supports statuses like OUT_OF_SERVICE |
| Unclear if app is ready for requests | `health` or readiness | Health contributors and readiness state |

Features shows which capabilities are declared and recognized in the context. ServiceRegistry shows the status of a specific registration. Health/readiness reflects serving status according to health contributors and deployment policies.

## 2. The Features Actuator Endpoint

Spring Cloud Commons provides an endpoint with ID `features`. With Actuator using the default base path, the HTTP URL is:

~~~http
GET /actuator/features
~~~

The endpoint returns two main groups:

- `enabled`: features declared and recognized as active.
- `disabled`: names of declared abstract features for which no matching bean was found in the ApplicationContext.

An entry in `enabled` has metadata such as:

| Field | Meaning |
| --- | --- |
| `name` | Feature name; for abstract features it is the contract name, for named features it is the declared name |
| `type` | Fully qualified name of the implementation or representative class |
| `version` | Package implementation version if metadata is available |
| `vendor` | Package implementation vendor if metadata is available |

Illustrative response example:

~~~json
{
  "enabled": [
    {
      "name": "DiscoveryClient",
      "type": "com.example.discovery.ConsulDiscoveryClient",
      "version": "4.2.0",
      "vendor": "Example"
    },
    {
      "name": "Partner API",
      "type": "com.example.partner.PartnerApiClient",
      "version": "1.3.0",
      "vendor": "Example"
    }
  ],
  "disabled": [
    "LoadBalancerClient"
  ]
}
~~~

Version and vendor values are illustrative data only. If a package does not provide Implementation-Version or Implementation-Vendor in its manifest, the corresponding fields may be null.

### 2.1. Abstract Features

An abstract feature represents a typed contract, typically an interface or abstract class. For example, Spring Cloud Commons may declare:

- `DiscoveryClient`
- `LoadBalancerClient`
- `LockService`

Feature providers declare contracts through `HasFeatures` beans. The Features Endpoint searches for beans matching the contract type in the ApplicationContext:

- If a bean exists, the endpoint puts the feature in `enabled` and uses the bean's actual class to populate metadata.
- If no bean exists, the endpoint puts the contract's simple name into `disabled`.

Example of a module declaring two contracts:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.client.loadbalancer.LoadBalancerClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class DiscoveryFeatureConfiguration {

    @Bean
    HasFeatures discoveryFeatures() {
        return HasFeatures.abstractFeatures(
                DiscoveryClient.class,
                LoadBalancerClient.class);
    }
}
~~~

If the context has a DiscoveryClient but no LoadBalancerClient, the endpoint can report DiscoveryClient in enabled and LoadBalancerClient in disabled. That helps identify which capability has not been created.

### 2.2. Named Features

Named features are for capabilities lacking a common interface/abstract class to look up beans by contract. Examples could be an API Gateway, Circuit Breaker, Spring Cloud Bus, or an internal client.

A named feature is declared with a name and a representative class:

~~~java
import org.springframework.cloud.client.actuator.HasFeatures;
import org.springframework.cloud.client.actuator.NamedFeature;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PartnerFeatureConfiguration {

    @Bean
    HasFeatures partnerFeature(PartnerApiClient client) {
        return HasFeatures.namedFeatures(
                new NamedFeature("Partner API", PartnerApiClient.class));
    }
}
~~~

Named features are recorded based on declarations in `HasFeatures`. The endpoint does not check partner API health itself and does not ping remote systems. Therefore, place the feature-declaring bean inside the same conditional configuration as the real capability, or depend on the implementation bean as shown above.

### 2.3. Features Is Not a Dependency Tree

The endpoint does not scan every JAR to produce an exhaustive list of all libraries on the classpath. Modules or applications must declare features using `HasFeatures`. Consequently:

- A dependency may exist on the classpath yet not appear if no feature is declared.
- An abstract feature may appear in disabled if the contract is declared yet no implementation bean exists.
- A named feature appearing in enabled because it was declared does not mean the remote system is healthy.
- Version/vendor reflect package metadata of the feature class, not a BOM or SBOM report for the entire application.

Do not use the Features Endpoint as the sole tool for checking licenses, CVEs, dependency convergence, or Spring Boot/Spring Cloud compatibility.

## 3. The Service Registry Actuator Endpoint

Spring Cloud Commons provides an endpoint with ID `serviceregistry`. With the default base path:

~~~http
GET /actuator/serviceregistry
~~~

This endpoint relies on a `Registration` bean in the Spring ApplicationContext. When a current registration exists, GET returns the status that the `ServiceRegistry` implementation provides for that registration.

Illustrative response example with a provider that has a string status:

~~~json
"UP"
~~~

If the endpoint has no Registration to query, the endpoint implementation may return HTTP 404 with the message `no registration found`. This is a sign to inspect the registration bean and discovery provider, not proof that all services in the registry are gone.

### 3.1. Registration and ServiceRegistry

`Registration` is a marker interface representing an instance's metadata. A registration typically contains information such as service ID, host, port, secure flag, instance ID, and provider-specific metadata.

`ServiceRegistry` is the abstraction performing operations with registrations. Core operations include:

~~~java
public interface ServiceRegistry<R extends Registration> {

    void register(R registration);

    void deregister(R registration);

    void close();

    void setStatus(R registration, String status);

    <T> T getStatus(R registration);
}
~~~

This is the general shape of the contract; exact generic signatures and nullability may vary by release. Implementations such as Eureka, Consul, or Zookeeper provide their own Registration and ServiceRegistry types.

The ServiceRegistry Endpoint does not query the full list of instances across all services. It retrieves the current registration integrated with the application and calls `getStatus(registration)` to read the status.

### 3.2. GET: Reading Registration Status

Example:

~~~bash
curl http://localhost:8080/actuator/serviceregistry
~~~

The result depends on the provider. Some implementations return a string status, while others may return a different structure or value. Consult your provider's documentation to interpret it accurately.

GET only reads the status of the current registration. It does not prove:

- All instances of the service are healthy.
- Clients across every network can reach the instance.
- The instance has passed readiness probes.
- Business dependencies like databases or message brokers are working.
- The registry has propagated the new status to all clients.

### 3.3. POST: Requesting a Status Change

The endpoint supports POST to the same URL with a JSON body containing a `status` field:

~~~bash
curl -X POST   -H "Content-Type: application/json"   -d '{"status":"OUT_OF_SERVICE"}'   http://localhost:8080/actuator/serviceregistry
~~~

POST invokes `ServiceRegistry.setStatus(registration, status)` for the current registration. Valid values and their meanings are determined by the provider.

For example, Eureka supports common statuses:

- `UP`
- `DOWN`
- `OUT_OF_SERVICE`
- `UNKNOWN`

Do not assume these statuses are supported by every provider or have the same effect. Before automating POST operations, read your specific implementation's documentation and test in an environment that does not impact production traffic.

### 3.4. POST Is Not Register or Deregister

Changing status and changing registration lifecycle are distinct operations:

| Operation | Conceptual API | Meaning |
| --- | --- | --- |
| Register instance | `ServiceRegistry.register(registration)` | Publish registration to the registry |
| Deregister instance | `ServiceRegistry.deregister(registration)` | Remove registration from the registry |
| Read status | `ServiceRegistry.getStatus(registration)` | Retrieve current status |
| Change status | `ServiceRegistry.setStatus(registration, status)` | Request the provider to update status |

POST to `/actuator/serviceregistry` performs the status-change operation. It does not create a new registration by itself and is not equivalent to deregister. If the goal is to remove the instance completely, use the provider's lifecycle or appropriate deregistration API.

## 4. How Do the Two Endpoints Complement Each Other?

You can view them as two different layers of observation:

~~~mermaid
flowchart TB
    A["Spring ApplicationContext"]
    A --> B["HasFeatures beans"]
    B --> C["/actuator/features"]
    C --> D["Capability enabled / disabled"]
    A --> E["Registration bean"]
    E --> F["ServiceRegistry implementation"]
    F --> G["/actuator/serviceregistry"]
    G --> H["Status of current registration"]
    D --> I["Cross-check configuration and capabilities"]
    H --> J["Cross-check instance status in registry"]
~~~

Example for `order-service`:

- Features reports `DiscoveryClient` enabled: the application has a discovery bean.
- Features reports `LoadBalancerClient` disabled: the context lacks a declared load-balancer contract bean.
- ServiceRegistry reports `OUT_OF_SERVICE`: the provider currently views this instance's registration as out of service.
- Health reports DOWN: one or more health contributors failed their checks.

Four outputs speak to four different aspects. You cannot infer that LoadBalancer being disabled is the sole cause of the instance being OUT_OF_SERVICE; registry status may have been updated by the provider, an administrative action, or another operational process.

## 5. Configuring Actuator to Expose Both Endpoints

The application needs Spring Boot Actuator and Spring Cloud Commons along with the appropriate integrations.

Actuator dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Expose both endpoints over HTTP:

~~~yaml
spring:
  cloud:
    features:
      enabled: true

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - features
          - serviceregistry
~~~

The two configurations serve different purposes:

- `spring.cloud.features.enabled` controls creation of the Features Endpoint; it does not toggle capabilities like DiscoveryClient or LoadBalancer.
- `management.endpoints.web.exposure.include` controls which endpoints are accessible over HTTP.
- `serviceregistry` requires a service registry integration and a corresponding Registration bean to read status.

In Spring Boot, only `health` is exposed over HTTP by default. Having the Actuator dependency does not mean other endpoints are automatically opened. If the application changes `management.endpoints.web.base-path` or uses a separate management port, the actual URLs change too.

Example changing the base path:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

Then the endpoints will be under `/manage/features` and `/manage/serviceregistry`. You can check Actuator's discovery index page or management configuration to confirm the actual URLs.

### 5.1. When an Endpoint Does Not Appear

If GET returns 404, check in order:

1. Is Spring Boot Actuator on the runtime classpath?
2. Do Spring Cloud Commons and the discovery/registry provider have the right dependencies?
3. Is the endpoint enabled and permitted for access?
4. Does `management.endpoints.web.exposure.include` contain the needed endpoint?
5. Are base path and management port correct?
6. For `serviceregistry`, does the context have a matching Registration bean?
7. Did the provider create a ServiceRegistry implementation and wire it with the current Registration?

Do not conclude a capability is disabled just because the endpoint is not exposed over HTTP. Exposure is the management access layer; feature beans may still exist inside the context.

## 6. Auto-Registration and Status via serviceregistry

By default, many ServiceRegistry integrations automatically register the running instance. Auto-registration can be controlled with the common property:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: true
~~~

You can disable auto-registration with:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Or use `@EnableDiscoveryClient(autoRegister = false)` in application configuration if your version and provider support this approach.

Distinguish three concepts:

- Auto-registration controls whether the integration registers the instance automatically during lifecycle.
- The Registration bean is the instance metadata used by the provider.
- The ServiceRegistry Endpoint reads or updates the status of the current registration.

Do not assume disabling auto-registration always removes the Registration bean or always causes the endpoint to return 404. That depends on the provider and configuration. Check actual beans, behavior, and documentation for your release.

### 6.1. Events Before and After Registration

Spring Cloud Commons defines events related to auto-registration, typically including:

- `InstancePreRegisteredEvent`: published before registering the instance.
- `InstanceRegisteredEvent`: published after registration is performed.

Applications can use listeners for logging, adding observability, or coordinating startup steps. These auto-registration events are not published when `spring.cloud.service-registry.auto-registration.enabled` is set to `false`.

Do not use registration event listeners as a substitute for the GET status endpoint: events describe a single moment in the lifecycle, whereas the endpoint reads the status returned by the provider at query time.

## 7. Interpreting Status by Provider

`ServiceRegistry` intentionally leaves status as a string or implementation-defined type. This lets the abstraction work across many registries, but it also means statuses do not share completely uniform semantics.

### 7.1. Eureka

Eureka typically uses statuses such as:

| Status | General Meaning |
| --- | --- |
| `UP` | Instance is marked active |
| `DOWN` | Instance is marked inactive |
| `OUT_OF_SERVICE` | Instance is marked not serving traffic |
| `UNKNOWN` | Status undetermined |

Example taking an instance out of service:

~~~bash
curl -X POST   -H "Content-Type: application/json"   -d '{"status":"OUT_OF_SERVICE"}'   http://localhost:8080/actuator/serviceregistry
~~~

Whether clients stop selecting the instance also depends on how Eureka Server, discovery clients, and load-balancing integrations handle status. Check the actual instance list from a client after making the change.

### 7.2. Zookeeper

Spring Cloud Zookeeper has its own ServiceRegistry implementation. Zookeeper documentation describes `OUT_OF_SERVICE` being represented via metadata and filtered out of the instance list by Zookeeper LoadBalancer's service-instance supplier. This detail belongs to the Zookeeper integration; it does not apply automatically to other registries.

### 7.3. Consul and Other Providers

Each provider has its own way of representing health/status, registration, leases, heartbeats, and instance filtering. Do not send a status string simply because it is valid in Eureka and expect Consul or Zookeeper to interpret it identically.

Before changing status, check:

- Does the provider support that status?
- Is status stored in the registry or only locally in the client?
- Does the discovery client filter instances by status?
- Is the change synchronized to other clients, and how long does it take?
- Will the status be overwritten by the next health check or heartbeat?
- What is the procedure to restore UP status?

## 8. Operational Scenario: Taking an Instance Out of Traffic

Suppose a `catalog-service` instance needs maintenance:

1. Check `/actuator/features` to confirm relevant capabilities are still created.
2. Check `/actuator/serviceregistry` to record the current status.
3. Verify the provider supports `OUT_OF_SERVICE` and that the status is filtered by the load balancer.
4. Send a POST status update per the provider's contract.
5. Call GET again to confirm the status returned by the provider.
6. From another client, verify whether the instance is still in the selectable list.
7. Wait for in-flight requests to finish according to the application's drain policy.
8. Perform maintenance.
9. Send the restore status if required by the provider, then re-verify from the registry and clients.

Example update command:

~~~bash
curl -X POST   -H "Content-Type: application/json"   -d '{"status":"OUT_OF_SERVICE"}'   http://localhost:8080/actuator/serviceregistry
~~~

Then read back:

~~~bash
curl http://localhost:8080/actuator/serviceregistry
~~~

Do not rely solely on a successful POST response. Confirm via GET, registry state, and client-side behavior. A provider may accept the request yet incur propagation delay before clients observe the change.

## 9. Combining with Health and Readiness

Features and ServiceRegistry do not replace the health endpoint:

| Endpoint | Question Answered | Does Not Prove |
| --- | --- | --- |
| `/actuator/features` | Which capabilities are declared and enabled? | Remote services are healthy or beans handle requests successfully |
| `/actuator/serviceregistry` | What status does the current registration have? | All application dependencies are healthy |
| `/actuator/health` | What status do health contributors report? | The instance is properly distributed by the registry to all clients |
| `/actuator/health/readiness` (when readiness group is enabled) | Is the application ready to accept traffic per the readiness group? | All other services are working |

An application may have features enabled yet health DOWN. Registration may be UP while readiness is not yet satisfied. Conversely, internal readiness may pass while the registry has not updated status due to latency or connectivity errors.

With Kubernetes or orchestration platforms, continue using liveness/readiness probes per deployment policy. Do not use a single registry status string as the sole probe.

## 10. Securing Endpoints and Controlling POST Operations

`features` and `serviceregistry` expose internal information. In particular, `serviceregistry` has a write operation that can alter instance status and affect client endpoint selection.

Recommendations:

- Only expose both endpoints on a management network or dedicated management port.
- Use Spring Security or an equivalent authentication mechanism.
- Grant GET permission to operations teams needing observability.
- Restrict POST `serviceregistry` to teams responsible for traffic control.
- Do not expose all Actuator endpoints with wildcards without appropriate network and permission controls.
- Record audit logs for POST callers, old/new statuses, and change timestamps.
- Do not leave credentials in shared scripts or command history.
- Test status restoration procedures to avoid instances unintentionally remaining OUT_OF_SERVICE.

Example configuration exposing only the two needed endpoints:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,features,serviceregistry
~~~

Exposure only makes endpoints reachable over HTTP; it does not replace authentication and authorization. If the application has a custom SecurityFilterChain, explicitly configure read and write permissions for each endpoint.

## 11. Testing Both Endpoints

Test feature inventory and registration status separately because they have different dependencies and semantics.

### 11.1. Testing the Features Endpoint

With Spring MVC test support, you can verify the endpoint is exposed and returns the expected structure:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "management.endpoints.web.exposure.include=health,features,serviceregistry"
})
@AutoConfigureMockMvc
class FeaturesEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsFeatureInventory() throws Exception {
        mockMvc.perform(get("/actuator/features"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.enabled").isArray())
                .andExpect(jsonPath("$.disabled").isArray());
    }
}
~~~

This test verifies endpoint structure. You can add assertions for specific features if the test context declares `HasFeatures` beans and corresponding implementations. Do not depend on element ordering in lists.

### 11.2. Testing the ServiceRegistry Endpoint

This test needs a test provider or suitable registration fixture. When the context has a Registration bean:

~~~java
@Test
void readsCurrentRegistrationStatus() throws Exception {
    mockMvc.perform(get("/actuator/serviceregistry"))
            .andExpect(status().isOk());
}
~~~

If the context has no Registration bean, the endpoint may return 404 `no registration found`. This is a branch worth testing if the application can run in an unregistered mode.

### 11.3. Testing POST per Provider

An integration test can send a provider-supported status:

~~~java
import org.springframework.http.MediaType;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void updatesRegistrationStatus() throws Exception {
    mockMvc.perform(post("/actuator/serviceregistry")
            .contentType(MediaType.APPLICATION_JSON)
            .content("{\"status\":\"OUT_OF_SERVICE\"}"))
            .andExpect(status().is2xxSuccessful());

    mockMvc.perform(get("/actuator/serviceregistry"))
            .andExpect(status().isOk());
}
~~~

This is a test skeleton, not a guarantee that every provider accepts `OUT_OF_SERVICE`. Real tests must use valid status values for the provider, then verify state through provider APIs or discovery/load-balancing behavior. If you need to test provider errors, add an invalid-status test and verify how exceptions map to HTTP responses in your version.

### 11.4. Testing Access Permissions

Add security tests to verify:

- Unauthorized callers cannot read endpoint data per policy.
- Read-only callers cannot POST status updates.
- Operators with operational roles are permitted to POST.
- Audit logs record status-change operations.

Do not use a successful status test as proof of security policy.

## 12. Common Mistakes and How to Avoid Them

1. **Confusing features with health:** an enabled feature only confirms the capability was recognized in the context.
2. **Confusing serviceregistry with a service list:** the endpoint reads the current registration, not every service in the registry.
3. **GET serviceregistry returning 404:** check the Registration bean and provider integration.
4. **features showing disabled entries:** check HasFeatures declarations and corresponding bean contracts.
5. **Named features always showing enabled:** put HasFeatures beans inside conditional configurations alongside the real capability.
6. **POSTing unsupported statuses:** check the provider's list of supported statuses.
7. **POST succeeding yet clients still calling the instance:** check status filtering semantics, propagation delay, and discovery client/load balancer caches.
8. **Using POST to deregister:** POST only calls setStatus; use lifecycle or deregister APIs when removing a registration.
9. **Disabling auto-registration and assuming the endpoint disappears:** check the actual Registration bean.
10. **Exposing endpoints publicly:** restrict to management networks and access controls.
11. **Using status as readiness:** check readiness groups and dedicated health contributors.
12. **Lacking a recovery procedure:** define the restore status and verify after maintenance.

## 13. Observation and Troubleshooting Workflow

When a service is not called as expected, follow this sequence:

1. Call `/actuator/features` to view declared capabilities and enabled/disabled status.
2. If an abstract feature appears in disabled, check dependencies, auto-configuration, profiles, and bean contracts.
3. Call `/actuator/serviceregistry` to read the current registration's status.
4. If the endpoint returns 404, check the Registration bean and provider integration.
5. Cross-check the status against the provider's supported statuses.
6. Check application health/readiness and logs.
7. If status needs changing, use POST with a JSON body and appropriate operational permissions.
8. Call GET again to verify the provider returns the new status.
9. Check from a client to confirm discovery/load balancing reflects the change.
10. Document the recovery status and rollback procedure.

Do not stop investigating at a single endpoint. Combine feature inventory, registration status, health/readiness, logs, and client-side observation for a complete picture.

## 14. Key Takeaways

`/actuator/features` answers which capabilities are declared by modules and recognized as enabled in the ApplicationContext. `/actuator/serviceregistry` reads the status of the current Registration and allows requesting the provider to update status via POST with the JSON field `status`. Valid statuses and their impact on discovery depend on the active ServiceRegistry implementation.

Features does not prove remote services are healthy; ServiceRegistry does not list the entire registry, and POSTing status is not registering or deregistering. Combine both endpoints with health/readiness, verify client-side behavior, and tightly guard write permissions to observe and operate services in **SPRING_CLOUD_CORE**.

## References

- [Spring Cloud Commons — Common Abstractions, Enabled Features and Service Registry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)
- [Spring Cloud Zookeeper — Service Registry and Instance Status](https://docs.spring.io/spring-cloud-zookeeper/reference/service-registry.html)
- [Spring Boot Actuator — Endpoints, Exposure and Security](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
