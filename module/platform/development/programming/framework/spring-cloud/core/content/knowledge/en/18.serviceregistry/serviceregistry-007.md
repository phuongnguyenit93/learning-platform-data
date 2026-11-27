# The serviceregistry Endpoint and the Registration Bean Requirement

This lesson belongs to the **ServiceRegistry** chapter of the **SPRING_CLOUD_CORE** module. Spring Cloud Commons provides the `ServiceRegistry` abstraction to register, deregister, and update the status of a service instance in the registry. Spring Cloud Actuator also provides the `/serviceregistry` endpoint to read or change the status of the current registration.

This endpoint has an important requirement: the Spring `ApplicationContext` must contain a bean implementing `Registration`. `Registration` is a marker interface describing a registration under the shared contract; each discovery provider supplies its own concrete type. Therefore, the endpoint needs a registration compatible with the running provider's `ServiceRegistry`; simply having a `ServiceRegistry` bean or only adding the Actuator dependency is not enough.

This lesson focuses on the endpoint, bean requirements, enabling HTTP exposure, GET/POST operations, provider-defined statuses, auto-registration, and testing.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Explain the roles of `ServiceRegistry` and `Registration` in Spring Cloud Commons.
2. Distinguish a registration object from a service registry implementation.
3. State the prerequisite for the `/serviceregistry` endpoint to work: a matching `Registration` bean in the `ApplicationContext`.
4. Enable and expose the endpoint through Spring Boot Actuator.
5. Use GET to read the current registration status.
6. Use POST with a JSON `status` field to update the status.
7. Choose valid status values according to the active discovery provider.
8. Distinguish status updates from register, deregister, and application shutdown.
9. Understand the relationship between the `Registration` bean and startup auto-registration.
10. Verify the endpoint, beans, provider, and registry state in integration tests.
11. Protect status-changing operations with authentication, authorization, and network policies.

## 2. ServiceRegistry and Registration Have Two Different Roles

Spring Cloud Commons defines shared abstractions so applications do not have to call each registry's proprietary API in most service management logic.

### 2.1. ServiceRegistry

`ServiceRegistry` is the contract for the component that communicates with the registry. It provides registration management operations, typically:

- `register(Registration)`: registers a service instance.
- `deregister(Registration)`: deregisters a service instance.
- `setStatus(Registration, status)`: asks the provider to update status.
- `getStatus(Registration)`: reads status as supported by the provider.
- `close()`: closes implementation resources when needed.

Exact method behavior and status semantics depend on the implementation. One registry may map statuses to its own state model, while another provider has a different set of values or update mechanism.

### 2.2. Registration

`Registration` is a marker interface representing the registration data of an instance. It does not perform network communication itself and is not a standalone registry client.

A registration typically describes information such as:

- Service ID or application name.
- Instance ID.
- Host and port.
- URI or secure flag.
- Instance metadata.
- Provider-specific details needed for registration.

Actual fields are defined by the implementation. Do not assume every `Registration` shares the same getters, structure, or construction pattern.

### 2.3. Relationship Between the Two Components

~~~mermaid
flowchart LR
    APP["Spring ApplicationContext"] --> REGISTRATION["Registration bean"]
    REGISTRATION --> ENDPOINT["/actuator/serviceregistry"]
    ENDPOINT --> REGISTRY["Provider ServiceRegistry"]
    REGISTRY --> ADAPTER["Eureka / Consul / Zookeeper adapter"]
    ADAPTER --> BACKEND["Remote service registry"]
~~~

The endpoint obtains the current `Registration` from the `ApplicationContext` and uses the `ServiceRegistry` implementation to read or update status. Both components must belong to the same compatible provider.

Examples of provider-specific pairs mentioned by Spring Cloud Commons:

| Registration implementation | ServiceRegistry implementation |
| --- | --- |
| `EurekaRegistration` | `EurekaServiceRegistry` |
| `ConsulRegistration` | `ConsulServiceRegistry` |
| `ZookeeperRegistration` | `ZookeeperServiceRegistry` |

Do not create a custom class that merely implements `Registration` and expect every provider to register it. Since `Registration` is a marker interface, providers expect the concrete type understood by their implementation.

## 3. How Does the serviceregistry Endpoint Work?

Spring Cloud Commons provides an Actuator endpoint with ID `serviceregistry`. With Spring Boot's default HTTP management base path, the URL is typically:

~~~text
/actuator/serviceregistry
~~~

The actual path can change if the application customizes `management.endpoints.web.base-path` or runs the management server on a separate port.

### 3.1. GET Reads Status

Send a GET request to the endpoint to read the status of the current `Registration`:

~~~bash
curl --request GET \
  http://localhost:8080/actuator/serviceregistry
~~~

The endpoint returns the current status as represented by the provider. Exact response formatting can vary across versions and implementations, so do not hardcode a single JSON response schema across all registries.

### 3.2. POST Updates Status

Send a POST request to the same endpoint with a JSON body containing the `status` field:

~~~bash
curl --request POST \
  --header "Content-Type: application/json" \
  --data '{"status":"OUT_OF_SERVICE"}' \
  http://localhost:8080/actuator/serviceregistry
~~~

The endpoint specifically requires the `status` field. The passed value must belong to the set of statuses supported by the `ServiceRegistry` provider. For example, Eureka typically supports:

- `UP`
- `DOWN`
- `OUT_OF_SERVICE`
- `UNKNOWN`

These values are Eureka examples, not a universal enum across all providers. Consult your concrete implementation's documentation before sending POST requests.

### 3.3. Meaning of the POST Operation

POST asks `ServiceRegistry` to update the status of the current `Registration`. It is not equivalent to:

- Registering a new instance.
- Deregistering the instance.
- Stopping the JVM or shutting down the HTTP server.
- Directly changing the status of all replicas.
- Guaranteeing that every discovery client immediately evicts the instance from its cache.

The registry and consumers may have their own synchronization/caching mechanisms. After changing status, verify the state in the registry and consumer behavior.

## 4. Mandatory Requirement: Registration Bean in ApplicationContext

### 4.1. Why Does the Endpoint Need a Registration Bean?

The endpoint needs to know which registration represents the running instance in order to read or update its status. Spring Cloud Commons explicitly specifies that the endpoint relies on a `Registration` bean in the Spring `ApplicationContext`.

Therefore, distinguish the following cases:

| Bean/Dependency | Sufficient to satisfy endpoint requirement? | Reason |
| --- | --- | --- |
| `spring-boot-starter-actuator` | No. | Only provides the Actuator infrastructure. |
| `ServiceRegistry` | Not enough. | The registry implementation knows how to call the provider, but the endpoint also needs a concrete registration. |
| Compatible `Registration` | The condition required by the endpoint documentation. | Represents the instance whose status the endpoint reads/updates. |
| Both `Registration` and matching `ServiceRegistry` provider | Required configuration in a typical registry-backed application. | The endpoint has both the registration and the implementation to interact with the registry. |

An application may have a provider dependency yet lack a `Registration` bean because auto-configuration was excluded, the provider is disabled, or the application configured things differently. In that case, the endpoint may not be created or may not work as expected.

### 4.2. Where Does Registration Usually Come From?

In Eureka, Consul, or Zookeeper integrations, starter/provider auto-configuration usually creates the registration object alongside the registry management beans. The application does not need to create the marker bean manually if the provider already supplies the right bean.

Examples of concrete types:

~~~java
// Illustrative provider-specific types:
EurekaRegistration
ConsulRegistration
ZookeeperRegistration
~~~

These classes belong to their respective modules/providers. Do not import a provider class if the application does not use that provider.

### 4.3. Checking Beans at Startup

You can verify the relevant beans in an integration test or during debugging:

~~~java
@Autowired
ApplicationContext applicationContext;

@Test
void registrationBeanExists() {
    assertThat(
        applicationContext.getBeansOfType(Registration.class)
    ).isNotEmpty();
}

@Test
void serviceRegistryBeanExists() {
    assertThat(
        applicationContext.getBeansOfType(ServiceRegistry.class)
    ).isNotEmpty();
}
~~~

These two checks confirm the context contains beans of the common types. They do not prove the provider connected successfully or that the instance has been registered. You must also inspect status in the actual registry.

If multiple registration beans or multiple providers exist in the same context, identify exactly which bean the endpoint/provider uses. Do not treat a non-empty map as proof that the endpoint will pick the intended registration.

## 5. Enabling Actuator and Exposing the Endpoint

### 5.1. Dependencies

The application needs Actuator and a discovery provider with the corresponding `ServiceRegistry`/`Registration` integration. Example Actuator dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Add the provider starter matching the registry your application uses, such as Eureka, Consul, or Zookeeper. The provider dependency must be compatible with your project's Spring Boot and Spring Cloud release train.

### 5.2. Exposing the Endpoint over HTTP

Spring Boot does not expose all Actuator endpoints over HTTP by default. Add ID `serviceregistry` to the exposure list:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,serviceregistry
~~~

If the project already has an include list, append this ID to the existing list to keep other required endpoints exposed.

Do not use `include: "*"` just to try out the endpoint in production. Exposure makes the endpoint reachable over HTTP; access must still be controlled via Spring Security and network policy.

### 5.3. Management Port and Base Path

If the application configures a separate management port:

~~~yaml
management:
  server:
    port: 9090
  endpoints:
    web:
      base-path: /manage
      exposure:
        include: health,serviceregistry
~~~

The URL will use the configured management port and base path, for example:

~~~text
http://localhost:9090/manage/serviceregistry
~~~

Do not assume the endpoint is always on the application port or prefixed with `/actuator`. Read the actual management configuration.

## 6. Auto-registration and the Registration Bean

The `ServiceRegistry` provider usually registers the application instance automatically at startup. Spring Cloud Commons lets you disable this behavior via configuration:

~~~yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
~~~

Or via annotation in configurations that use it:

~~~java
@EnableDiscoveryClient(autoRegister = false)
~~~

In modern Spring Cloud, `@EnableDiscoveryClient` is no longer required merely to activate discovery when provider auto-configuration is on the classpath; however, the annotation's auto-register attribute may still appear in legacy-compatible configurations. Properties are usually easier to manage per profile/deployment.

### 6.1. Disabling Auto-registration Does Not Disable Discovery

These three actions are distinct:

| Action | Meaning |
| --- | --- |
| Disabling auto-registration | Application does not register its instance automatically under the default lifecycle. |
| Disabling discovery | Application does not use the discovery client according to the corresponding config. |
| Disabling `serviceregistry` endpoint exposure | HTTP endpoint is not exposed; does not alter registrations in the registry. |

When `spring.cloud.service-registry.auto-registration.enabled=false`, the auto-registration events `InstancePreRegisteredEvent` and `InstanceRegisteredEvent` are not published by the automatic lifecycle. This does not by itself tell you whether a `Registration` bean still exists in the context; check the provider configuration and actual beans.

### 6.2. The Endpoint Needs the Current Registration, Not Just Auto-register Intent

If auto-registration is disabled, do not assume the endpoint still has a valid registration simply because a `ServiceRegistry` bean exists. Verify:

1. Whether the provider creates a `Registration` bean.
2. Which instance that `Registration` describes.
3. Whether the instance has been registered manually or via another lifecycle.
4. Whether the provider accepts `setStatus` operations on the current registration.

If the application uses a manual registration flow, manage the registration lifecycle yourself and ensure the endpoint is wired to the right registration.

## 7. Registering and Deregistering with ServiceRegistry

Spring Cloud Commons lets applications manage registrations through the `ServiceRegistry` abstraction. General example:

~~~java
public class RegistryCoordinator<R extends Registration> {

    private final ServiceRegistry<R> serviceRegistry;

    public RegistryCoordinator(ServiceRegistry<R> serviceRegistry) {
        this.serviceRegistry = serviceRegistry;
    }

    public void register(R registration) {
        serviceRegistry.register(registration);
    }

    public void deregister(R registration) {
        serviceRegistry.deregister(registration);
    }
}
~~~

The generic type `R` must be the `Registration` implementation supported by the corresponding `ServiceRegistry`. For instance, `EurekaServiceRegistry` requires the Eureka registration type expected by the provider.

An application can disable auto-registration and call `register`/`deregister` in a custom workflow, such as an event handler, admin workflow, or custom endpoint. Ensure operations have appropriate retry safety and error handling when the registry is unavailable.

### 7.1. Do Not Confuse register with setStatus

| Method | Purpose |
| --- | --- |
| `register(registration)` | Creates/updates an instance registration per provider semantics. |
| `deregister(registration)` | Deregisters the instance. |
| `setStatus(registration, status)` | Changes the status of the identified registration. |
| `getStatus(registration)` | Reads the registration status per the provider. |

The `/serviceregistry` endpoint focuses on the status of the current `Registration`. It is not a general-purpose API for creating multiple service registrations or deregistering arbitrary services.

## 8. Auto-registration Events

Spring Cloud Commons publishes two key events:

- `InstancePreRegisteredEvent`: published before the instance is registered.
- `InstanceRegisteredEvent`: published after the instance is registered.

Applications can use `ApplicationListener` to record audits, update auxiliary metadata, or execute logic required before/after registration.

Example listener:

~~~java
@Component
public class RegistrationEvents
        implements ApplicationListener<InstanceRegisteredEvent<?>> {

    @Override
    public void onApplicationEvent(InstanceRegisteredEvent<?> event) {
        // Record that the provider completed the auto-registration step.
        // Do not log credentials or sensitive registration details.
    }
}
~~~

Generic event signatures and imports can vary by release train; verify the API for your exact version. Auto-registration events are not published when `spring.cloud.service-registry.auto-registration.enabled=false`.

Do not treat the post-registration event as proof that all consumers already see the instance. The registry may take time to synchronize and clients may cache results.

## 9. Changing Status with the Endpoint

### 9.1. Checking Current Status

~~~bash
curl --request GET \
  http://localhost:8080/actuator/serviceregistry
~~~

Read the response and note the current status before changing it. Response representation depends on provider/version; rely only on the status field returned by the endpoint.

### 9.2. Taking an Instance Out of Service

Example with a provider supporting `OUT_OF_SERVICE`:

~~~bash
curl --request POST \
  --header "Content-Type: application/json" \
  --data '{"status":"OUT_OF_SERVICE"}' \
  http://localhost:8080/actuator/serviceregistry
~~~

The typical intent is temporarily marking an instance so it should not receive new traffic according to registry semantics. Consumers and load balancers only react properly if the provider translates this status into information clients understand and refresh promptly.

### 9.3. Bringing an Instance Back

Example with a provider supporting `UP`:

~~~bash
curl --request POST \
  --header "Content-Type: application/json" \
  --data '{"status":"UP"}' \
  http://localhost:8080/actuator/serviceregistry
~~~

Then issue a GET again and verify the status in the registry. Do not send `UP` merely because the process is running; first confirm the application meets conditions to accept traffic.

### 9.4. Eureka Example

Eureka commonly supports `UP`, `DOWN`, `OUT_OF_SERVICE`, and `UNKNOWN`. Different statuses carry different operational meanings:

| Status | General meaning |
| --- | --- |
| `UP` | Instance is marked ready according to Eureka status. |
| `DOWN` | Instance is marked inactive. |
| `OUT_OF_SERVICE` | Instance is taken out of normal serving status. |
| `UNKNOWN` | Status is unknown according to Eureka. |

These are Eureka-specific examples. Consul, Zookeeper, and other providers may have completely different status strings, mappings, or behaviors. Do not send these values to another provider unless its documentation supports them.

## 10. Status Does Not Replace Health Checks and Readiness

Service registry status and application health are related signals but not identical.

- The health endpoint reports the state of the application or components checked by health contributors.
- Readiness indicates whether the instance is ready to accept traffic under platform policy.
- Registration status is the state written to the registry via the `ServiceRegistry` provider.
- Discovery clients and load balancers read registry data using their own mechanisms.

Changing status does not stop the HTTP server, close database connections, shut down schedulers, or block all internal requests. To drain traffic safely, coordinate readiness, registry status, load balancer behavior, and graceful shutdown.

A drain workflow might include:

1. Mark the instance not to accept new traffic via readiness/registry mechanisms.
2. Wait for consumers or load balancers to update.
3. Wait for in-flight requests and transactions to finish.
4. Stop listeners/background workers in order.
5. Remove the registration when required by shutdown workflow.
6. Stop the process.

The exact order depends on the orchestrator, provider, and deployment policy.

## 11. Securing the serviceregistry Endpoint

POST changes an instance's status in the registry. If unauthorized users can call the endpoint, they can take instances out of service or alter status in ways that disrupt routing.

Required safeguards:

1. Expose `serviceregistry` only when there is a clear operational need.
2. Protect the endpoint with Spring Security authentication and administrative roles/authorities.
3. Restrict access using a management network, firewall, or network policy.
4. Use TLS whenever requests traverse a network.
5. Audit the actor, timestamp, instance, and before/after status.
6. Do not log tokens, credentials, or sensitive `Registration` details.
7. Monitor unusual POST requests and rapid repeated status flips.
8. Validate statuses against provider rules; do not allow arbitrary values from admin UIs.
9. Use proper approval/automation workflows if changes could reduce cluster capacity.
10. Do not expose all Actuator endpoints publicly just to open one endpoint.

Minimal exposure example:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,serviceregistry
~~~

Exposure only determines whether the endpoint is reachable over HTTP. It does not replace authorization. Configure the security chain so only authorized operator principals can GET/POST, and check CSRF policies consistent with how the application protects administrative endpoints.

## 12. Testing the Registration Bean and Endpoint

### 12.1. Testing the Bean Prerequisite

Start the `ApplicationContext` with an appropriate test discovery provider and verify the `Registration` bean:

~~~java
@Test
void applicationContextContainsRegistration() {
    assertThat(applicationContext.getBeansOfType(Registration.class))
        .isNotEmpty();
}
~~~

If the test does not use a registry-backed provider, do not assume a `Registration` bean exists. Use intentional test configuration/provider fixtures to verify the endpoint.

### 12.2. Testing the ServiceRegistry Implementation

~~~java
@Test
void serviceRegistryImplementationIsAvailable() {
    assertThat(applicationContext.getBeansOfType(ServiceRegistry.class))
        .isNotEmpty();
}
~~~

Bean existence does not prove the registry server is reachable. Write a dedicated integration test to verify network/provider interaction.

### 12.3. Testing HTTP GET

With the Actuator endpoint exposed in the test context, call `GET /actuator/serviceregistry` and verify a successful response with the expected status for your provider fixture.

Do not assert a single universal JSON schema if implementations return different responses. Assert the specific fields confirmed for the endpoint/version under test.

### 12.4. Testing HTTP POST

Send a body with the `status` field:

~~~json
{
  "status": "OUT_OF_SERVICE"
}
~~~

After POST:

1. Verify the response status code per endpoint/version.
2. Call GET on the endpoint again.
3. Verify `ServiceRegistry` received the status update command.
4. Read the status from a provider test double or registry test instance.
5. Verify that an unsupported status is handled with an implementation error.

### 12.5. Testing Missing Registration

Create a test context that has `ServiceRegistry` without a matching `Registration` bean. Verify the endpoint cannot operate like the complete setup. Depending on auto-configuration and version, the endpoint may not be created or may be unavailable; check actual behavior rather than asserting a hardcoded HTTP error code.

## 13. Testing and Troubleshooting Matrix

| ID | Scenario | Verification target |
| --- | --- | --- |
| SR1 | Provider creates `Registration` bean and `ServiceRegistry` bean. | Endpoint is configured with the current registration. |
| SR2 | Actuator present without `Registration` bean. | Endpoint does not meet prerequisite. |
| SR3 | GET endpoint. | Status is read according to provider. |
| SR4 | POST valid status. | Provider receives the status update request. |
| SR5 | POST invalid status. | Provider rejects or reports an error per implementation. |
| SR6 | Auto-registration enabled. | Instance registration lifecycle runs per provider. |
| SR7 | Auto-registration disabled. | No auto-registration events; verify `Registration` bean and manual flow separately. |
| SR8 | Endpoint not exposed. | HTTP route unreachable even if beans exist. |
| SR9 | Principal lacks POST permission. | Security rejects status change. |
| SR10 | Registry unreachable. | Provider error is observed and handled gracefully. |
| SR11 | POST OUT_OF_SERVICE. | Verify registry and consumer/load balancer behavior. |
| SR12 | POST UP. | Instance only resumes traffic when readiness/registry conditions align. |

### 13.1. Common Errors

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `/actuator/serviceregistry` returns 404. | Endpoint not exposed, Actuator missing, or endpoint not created. | Check dependencies, exposure, and `Registration` bean condition. |
| `ServiceRegistry` exists but endpoint does not work. | Missing matching `Registration` bean. | Inspect beans of type `Registration.class` and provider auto-configuration. |
| No `Registration` bean present. | Provider starter missing, auto-configuration excluded, or manual registration used. | Check provider config and create registration per provider contract if needed. |
| POST reports invalid status. | Status not in the provider's supported value set. | Read provider documentation and use a valid value. |
| GET returns unexpected status. | Registry holds its own status, different registration, or unsynced update. | Check registration instance, provider API, and registry backend. |
| POST succeeds yet consumers still call instance. | Consumer cache, load balancer, or registry propagation has not updated. | Check provider semantics, refresh interval, and consumer instance lists. |
| Disabling auto-registration keeps app out of registry. | No automatic registration lifecycle and no manual registration yet. | Build a clear register/deregister workflow. |
| Endpoint allows GET but POST returns 403. | Security/CSRF policy disallows write operations. | Grant appropriate operator permissions while keeping safe policies. |
| POST updates status yet app receives direct requests. | Registry status does not stop the process or HTTP listener. | Combine readiness, load balancer, traffic draining, and graceful shutdown. |
| Multiple providers coexist. | Ambiguous `Registration` bean or incompatible service registry. | Identify the intended provider/registration and verify bean wiring. |

## 14. Completion Checklist

- [ ] Can explain the role of `ServiceRegistry`.
- [ ] Can explain that `Registration` is a marker interface.
- [ ] Can distinguish the `Registration` bean from the `ServiceRegistry` implementation.
- [ ] Know the endpoint ID is `serviceregistry` and the default URL is `/actuator/serviceregistry`.
- [ ] Understand the endpoint requires a `Registration` bean in `ApplicationContext`.
- [ ] Know the `Registration` implementation must be compatible with the provider.
- [ ] Expose the endpoint via `management.endpoints.web.exposure.include`.
- [ ] Use GET to read status.
- [ ] Use POST JSON with the `status` field to change status.
- [ ] Check valid status values in provider documentation.
- [ ] Distinguish `setStatus` from `register` and `deregister`.
- [ ] Understand default auto-registration and how to disable it via property.
- [ ] Know the two events `InstancePreRegisteredEvent` and `InstanceRegisteredEvent`.
- [ ] Do not infer that disabling auto-registration removes the `Registration` bean.
- [ ] Distinguish registry status from health, readiness, and graceful shutdown.
- [ ] Have tests for `Registration` bean, `ServiceRegistry`, GET, POST, and missing-bean cases.
- [ ] Secure the endpoint with authentication, authorization, TLS, network policies, and auditing.

**Official documentation to cross-check against your project version:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `ServiceRegistry`, `Registration`, auto-registration events, and the Service Registry Actuator endpoint.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): `ServiceRegistry` auto-registration properties.
- [ServiceRegistryEndpoint Javadoc](https://www.javadoc.io/doc/org.springframework.cloud/spring-cloud-commons/latest/org/springframework/cloud/client/serviceregistry/endpoint/ServiceRegistryEndpoint.html): endpoint API for reading and updating status.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint availability, HTTP exposure, and Actuator security.

Statuses, registration types, and synchronization mechanisms depend on the discovery provider. Inspect the actual implementation, verify the `Registration` bean in `ApplicationContext`, and test GET/POST in a staging environment before enabling the endpoint in production.
