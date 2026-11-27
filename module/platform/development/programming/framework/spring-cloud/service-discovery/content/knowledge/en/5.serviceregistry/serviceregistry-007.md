# Controlling Status via the Actuator serviceregistry Endpoint

In a microservice architecture, an instance may still be running normally yet need to temporarily stop accepting requests for maintenance, a new deployment, or incident mitigation. Spring Cloud Commons provides the ServiceRegistry abstraction and an Actuator endpoint with ID serviceregistry to read or update the registration status of the current instance.

This endpoint creates a status-control channel at the registry level. It does not stop the application process, does not wait for in-flight requests to finish on its own, and does not replace health checks. To use it safely, you must understand the statuses supported by the registry, how clients filter instances, and the system's cache refresh timing.

## 1. ServiceRegistry and Registration

Spring Cloud Commons defines ServiceRegistry as an abstraction so application components can interact with a registry without calling Eureka-, Consul-, or ZooKeeper-specific APIs directly. Registration represents the registration details of an instance, such as service ID, instance ID, host, port, and metadata.

The core operations of ServiceRegistry include:

| Operation | Meaning |
|---|---|
| register | Registers the instance in the registry |
| deregister | Deregisters the instance from the registry |
| setStatus | Changes the status of the current registration |
| getStatus | Reads the status of the current registration |
| close | Releases resources managed by the implementation |

Each provider has its own implementation, such as EurekaServiceRegistry or ConsulServiceRegistry. Thus, ServiceRegistry standardizes how calls are made, without forcing every registry to use the same set of status values or store status the same way.

Normally, Spring Cloud automatically registers the instance on application startup if a corresponding discovery implementation is on the classpath. Auto-registration can be disabled via configuration:

    spring:
      cloud:
        service-registry:
          auto-registration:
            enabled: false

Another option is using @EnableDiscoveryClient(autoRegister = false). When auto-registration is disabled, the application needs its own registration workflow if it still wants to appear in the registry. Events such as InstancePreRegisteredEvent and InstanceRegisteredEvent tied to the auto-registration flow will not be published when auto-registration is disabled.

## 2. The serviceregistry Actuator Endpoint

Spring Cloud Commons provides an Actuator endpoint with ID serviceregistry. The endpoint relies on the ServiceRegistry and Registration beans in the Spring Application Context.

With Spring Boot's default management base path of /actuator, the default HTTP URL is:

    /actuator/serviceregistry

The endpoint supports two main operations:

- GET reads the current registration status.
- POST sends a new status so the ServiceRegistry implementation updates the registration.

The POST request must contain a JSON body with a status field. For example:

    {
      "status": "OUT_OF_SERVICE"
    }

The OUT_OF_SERVICE value in the example is just one commonly seen status; valid values must follow the registry in use. Do not copy Eureka's list of statuses and send them to Consul or another provider without checking that provider's documentation first.

This endpoint requires a ServiceRegistry implementation and a Registration bean in the application context. Without a matching registration, the endpoint cannot control a specific instance. Furthermore, the endpoint must be exposed over HTTP for clients to call it.

## 3. Exposing the Endpoint in Spring Boot

Spring Boot does not expose all Actuator endpoints over HTTP by default. Add serviceregistry to the list of exposed endpoints in application.yml:

    management:
      endpoints:
        web:
          exposure:
            include: health,info,serviceregistry

If the application already has an exposure list, append serviceregistry to the existing list rather than overwriting other required endpoints. The endpoint ID is a single word serviceregistry; the default path uses the same name.

You can customize the base path:

    management:
      endpoints:
        web:
          base-path: /manage
          exposure:
            include: health,serviceregistry

The URL then becomes /manage/serviceregistry. If the management server runs on a separate port, target the management port:

    server:
      port: 8080

    management:
      server:
        port: 8081
      endpoints:
        web:
          exposure:
            include: health,serviceregistry

In the example above, business requests use port 8080, while management endpoints use port 8081. Access to the management port should be controlled separately because POST can alter whether the instance receives traffic.

## 4. Reading Current Status with GET

Before changing status, read the current status to verify the target instance and record its initial value.

Example using curl:

    curl -i http://localhost:8080/actuator/serviceregistry

An illustrative response:

    HTTP/1.1 200
    Content-Type: application/vnd.spring-boot.actuator.v3+json

    {
      "status": "UP"
    }

The exact response payload depends on the ServiceRegistry implementation and Spring Cloud version. Some providers or versions may return additional status fields. Treat the actual response from your application as the source of truth rather than assuming every provider returns the same structure.

If you receive 404, check common causes:

- No discovery starter or ServiceRegistry bean is present in the application context.
- The Registration bean was not created or the service is not registered.
- The serviceregistry endpoint has not been exposed.
- The management base path, port, or path mapping differs from the requested URL.
- The endpoint is disabled or hidden by security configuration.

If you receive 401 or 403, the request reached the security layer without appropriate permissions. Check authentication, authorization, and CSRF policies.

## 5. Changing Status with POST

To put the instance into maintenance state, send a POST with a JSON body:

    curl -i -X POST http://localhost:8080/actuator/serviceregistry \
      -H "Content-Type: application/json" \
      -d "{\"status\":\"OUT_OF_SERVICE\"}"

To bring the instance back into service, send a status appropriate for the provider, for example with Eureka:

    curl -i -X POST http://localhost:8080/actuator/serviceregistry \
      -H "Content-Type: application/json" \
      -d "{\"status\":\"UP\"}"

POST invokes ServiceRegistry.setStatus(registration, status). The endpoint does not interpret the business meaning of the status string itself; the provider implementation determines how it is applied and which values are accepted. Sending an invalid value may cause the provider to throw an exception or return an error response.

After POST, call GET again to verify the status returned by the provider. To confirm the instance has actually been removed from the traffic flow, also inspect the registry and lookup results from clients or LoadBalancer.

## 6. Registry-Dependent Statuses

### Eureka

Eureka supports common instance statuses:

| Status | Meaning |
|---|---|
| UP | Instance is serving traffic |
| DOWN | Instance is unhealthy or unable to serve traffic |
| OUT_OF_SERVICE | Instance has been intentionally taken out of service |
| UNKNOWN | Status is undetermined |

By default, a Eureka client primarily uses heartbeats to indicate the instance is alive. Without health check integration enabled, the application's Actuator health status is not automatically propagated to Eureka; after registration succeeds, the instance can remain advertised as UP even if the health endpoint reports another status.

To propagate application health status to Eureka, configure in application.yml:

    eureka:
      client:
        healthcheck:
          enabled: true

When health check integration is enabled, the application's current health status can affect its instance status in Eureka. Therefore, distinguish manual updates via serviceregistry from statuses produced by HealthCheckHandler. Automated status updates can interact with manual operations; test behavior in the version you run.

Eureka excludes instances not in UP status from default client discovery results. This is helpful for planned maintenance: the instance still keeps its registration on the server but is not treated as ready to serve traffic.

Spring Cloud Netflix also includes pause and resume endpoints. When enabled, pause puts a Eureka instance into OUT_OF_SERVICE; resume removes the status override so the instance returns to the status reported by the application after the next heartbeat. These are separate lifecycle mechanisms, not aliases for the serviceregistry endpoint.

### Consul

Consul manages service status via health checks and agent operational states. Spring Cloud Consul typically registers an HTTP health check calling /actuator/health. If the check fails, the instance may transition to critical in Consul.

Do not conflate the status of the serviceregistry endpoint with health check status. A health check reflects the result of checking the endpoint; maintenance state is a control signal for the instance. A Consul implementation may map setStatus to the service's maintenance mode. Accepted statuses and what getStatus returns depend on the Spring Cloud Consul version. Verify against the running implementation before automating operations.

Example Consul health check configuration independent of the serviceregistry endpoint:

    spring:
      cloud:
        consul:
          discovery:
            register: true
            register-health-check: true
            health-check-path: /actuator/health
            health-check-interval: 10s

Putting an instance into maintenance mode does not mean the health endpoint has turned DOWN. Conversely, a health check turning critical does not necessarily mean an administrator actively placed the instance into maintenance mode. Observe both check status and service status in Consul.

### ZooKeeper

Spring Cloud Zookeeper also implements ServiceRegistry. Spring Cloud documentation describes setting OUT_OF_SERVICE using instance metadata; Spring Cloud LoadBalancer can filter out instances with a status other than UP. However, this filtering behavior depends on the service instance list supplier in use. Do not assume every ZooKeeper client or recipe applies identical filtering.

## 7. Procedure for Draining an Instance out of Traffic for Maintenance

A maintenance procedure should account for the registry, client caches, and in-flight requests. Example for a provider supporting OUT_OF_SERVICE:

1. **Identify the exact instance:** confirm host, port, instance ID, and application name to avoid altering the wrong instance.
2. **Read current status:** call GET /actuator/serviceregistry and record the response.
3. **Take the instance out of service:** POST status OUT_OF_SERVICE if supported by the provider.
4. **Verify in the registry:** inspect the registry UI or API to confirm the status updated.
5. **Wait for client updates:** discovery clients commonly maintain caches or refresh intervals; check the instance list from the consumer side before stopping the process.
6. **Drain requests:** wait for in-flight requests to finish according to the application, gateway, or deployment platform mechanism.
7. **Perform maintenance:** upgrade, restart, or change instance configuration.
8. **Bring the instance back:** POST UP per provider convention, then verify registry status, health checks, and ability to handle requests.

There is no fixed wait time applicable to every system. How long clients take to notice the new status depends on the registry, discovery cache, refresh intervals, and LoadBalancer. Seeing POST succeed does not prove all consumers have stopped sending requests to the instance.

If you need to shut down an instance permanently, deregister is a different operation from setStatus. OUT_OF_SERVICE preserves the registration while marking the instance ineligible for traffic; deregister removes the registration from the registry. Stopping the process is also a separate action and should occur after draining finishes.

## 8. Distinguishing serviceregistry, health, and deregister

These three mechanisms answer three different questions:

| Mechanism | Purpose | Example |
|---|---|---|
| Actuator health | Is the application healthy or ready? | GET /actuator/health |
| Actuator serviceregistry | What is the current registration status and what should it change to? | GET/POST /actuator/serviceregistry |
| ServiceRegistry.deregister | Removes the registration from the registry | Deregisters the instance at end of lifecycle |

For example, an application may report health UP while its registration is OUT_OF_SERVICE because of maintenance. This is a valid state: the process is alive, yet an administrator deliberately prevents consumers from selecting the instance.

Conversely, if health is DOWN while registration remains UP, consumers may keep receiving the instance depending on how the registry and discovery client handle health. Enable and configure appropriate health integration, and verify actual behavior.

Do not use POST serviceregistry as a substitute for fixing a health indicator. If the application is genuinely unhealthy, address the root cause. If the application is healthy but needs maintenance, use the maintenance status supported by the provider.

## 9. Securing the Status Control Endpoint

POST serviceregistry can directly impact system availability. An unauthorized caller could mark healthy instances OUT_OF_SERVICE or restore an unready instance. Therefore, the endpoint must be protected like any administrative API.

Principles to apply:

- Expose serviceregistry only when there is a real operational need.
- Place management endpoints on an internal network or a controlled management port.
- Use HTTPS when requests traverse untrusted networks.
- Require authentication and dedicated authorization for status-changing operations.
- Restrict POST permissions to appropriate operational roles; read-only observers may only need GET.
- If Spring Security enables CSRF protection, configure management clients to send CSRF tokens or establish narrow, intentional exceptions for machine-to-machine APIs.
- Log the actor, instance ID, old status, new status, timestamp, and operation outcome.
- Never place credentials in shell history, shared scripts, or repositories.

Exposing an endpoint in management.endpoints.web.exposure.include only makes it reachable over HTTP; that setting does not confer security on its own. Check authentication, authorization, network policies, and TLS as well.

## 10. Troubleshooting Common Errors

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| GET serviceregistry returns 404 | Endpoint not exposed or missing Registration bean | Check discovery dependencies, registration, and exposure |
| POST returns 404 | Wrong management base path or endpoint ID | Confirm actual URL and use path serviceregistry |
| POST returns 400 | Malformed JSON or missing status field | Send JSON with a string status field |
| POST returns 500 | Provider rejected status or cannot reach registry | Read application logs and registry client logs |
| GET returns unexpected status | Provider-specific status mapping | Inspect ServiceRegistry implementation and registry UI/API |
| POST succeeds but consumers still call instance | Cache not refreshed yet or provider does not exclude instance | Check registry, DiscoveryClient cache, and LoadBalancer supplier |
| Instance automatically flips back to UP | Health integration or heartbeat overwrote status | Check Eureka HealthCheckHandler, heartbeats, and provider mechanism |
| Instance still does not serve after POST UP | Health check still critical, app not ready, or network endpoint error | Check health, readiness, network, and registry checks |

When investigating, check along the chain: Actuator response, status in the registry, instance list received by consumers, and whether live requests still hit the instance. These four observations pinpoint whether the issue lies in the management endpoint, provider, discovery cache, or service invocation layer.

## 11. Conclusion

Actuator serviceregistry is the administrative interface for the current registration status via Spring Cloud Commons' ServiceRegistry abstraction. GET reads the status; POST with JSON containing a status field requests the provider to update it. Valid values and their semantics depend on the registry, so never assume Eureka, Consul, and ZooKeeper share the same conventions.

During planned maintenance, read the current status, transition the instance out of service, verify the registry and consumers have updated, drain in-flight requests, and only then stop the process. After maintenance, restore the status, verify health, and confirm the instance returns to discovery results. Protect management endpoints with authorization, TLS, and audit logging to prevent unintended status changes.

## References

- [Spring Cloud Commons — ServiceRegistry and Service Registry Actuator Endpoint](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Cloud Netflix — Eureka Health Checks and Pause/Resume](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Cloud Consul — Service Discovery and Health Check](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Zookeeper — Service Registry and Instance Status](https://docs.spring.io/spring-cloud-zookeeper/reference/service-registry.html)
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
