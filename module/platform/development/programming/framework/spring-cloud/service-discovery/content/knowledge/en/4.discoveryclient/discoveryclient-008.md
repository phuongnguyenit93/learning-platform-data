# Empty Lists, Non-Existent Services, and Query Errors

## Objectives

After this lesson, you can:

- Explain the meaning of an empty instance list when calling `DiscoveryClient`.
- Distinguish a service ID absent from the registry, a known service with no instances yet, and a registry connection error.
- Diagnose common causes stemming from configuration, registration lifecycle, caching, and networking.
- Handle discovery results safely without confusing query failures with having no instances.
- Design appropriate retries, fallbacks, logs, and metrics for service-calling applications.

## 1. The DiscoveryClient contract

`DiscoveryClient` is Spring Cloud's abstraction for querying instances by service ID. The two commonly used methods are:

- `getInstances(String serviceId)`: returns the list of `ServiceInstance` objects the client currently knows for that service ID.
- `getServices()`: returns the list of service IDs the client currently knows in the registry.

When there are no instances for a service ID, the standard representation returned by `getInstances` is an empty list. This is a valid result, does not by itself prove the registry is broken, and does not necessarily raise an exception.

Three outcomes must be distinguished:

| Outcome | Meaning | Appropriate action |
| --- | --- | --- |
| List with instances | Client found one or more endpoints in current discovery data. | Select an endpoint using an appropriate load-balancing mechanism and proceed with the call. |
| Empty list | Currently no instances are returned for that service ID. | Check service ID, registration status, registry cache, and startup timing. |
| Exception thrown | The discovery query encountered an error in the implementation or connection layer. | Record the error, classify the cause, and apply bounded error handling. |

`DiscoveryClient` does not mandate a single exception type across all implementations. Eureka, Consul, Kubernetes, or custom implementations may report errors via different runtime exception types. Therefore, calling code should preserve the root cause and avoid depending on a specific exception type unless the abstraction guarantees it.

`ServiceRegistry` primarily serves registration, deregistration, and instance status update operations. It relates to the registration lifecycle; querying instance lists belongs to `DiscoveryClient`.

## 2. Distinguishing a non-existent service from a service with no instances yet

An empty list can appear in many situations:

- The service ID has never been registered.
- The service ID is misspelled or differs in naming convention between caller and provider.
- The service-providing application has not started yet or has not finished registering.
- All instances have deregistered, been evicted from the registry, or are currently unpublished.
- The client has not fetched the registry yet, or configuration disables registry fetching.
- The client's registry cache has not updated yet after a service just registered or changed.
- Client and server see different states while the network or synchronization is interrupted.

You can use `getServices()` to assist diagnosis:

~~~~java
List<String> serviceIds = discoveryClient.getServices();
boolean serviceKnown = serviceIds.contains(serviceId);

List<ServiceInstance> instances =
        discoveryClient.getInstances(serviceId);
~~~~

If the service ID appears in `getServices()` but `getInstances(serviceId)` is empty, the current registry view knows the service name but returned no instances for that query. If the service ID is absent from the list, that name has not appeared in the registry view visible to the client yet.

This is only diagnostic information. The two calls above are not an atomic transaction; the registry can change between the two reads. The service ID list may also come from a local cache, so do not conclude that the service definitely does not exist on any node or at any time.

### Checking the service ID

The service ID must be consistent between provider and caller. With Spring Boot, the value typically originates from `spring.application.name`. Check:

- The name in default configuration and active profiles.
- Environment variables overriding configuration, for example `SPRING_APPLICATION_NAME`.
- The service name used in code calling `getInstances`.
- Case-normalization rules of the active registry implementation.

Do not rely on whether a registry displays names in uppercase or lowercase on a dashboard to infer string comparison rules across all implementations. Use a consistent service ID and inspect the exact value the client receives.

## 3. Why can getInstances return an empty list?

### Service has not registered yet

If the service-providing application has not started, cannot connect to the registry, or has registration disabled in configuration, the registry will have no instances to return. With Eureka Client, check the server URL, registration status, and startup logs. With Consul, check the agent/server, service registration, and health state.

### Registry not fetched yet or cache not updated

An application may register itself without downloading other services' lists if registry fetching is disabled. Depending on the implementation, discovery data may be cached and refreshed periodically. Therefore, a newly started service might not appear immediately in another client's query results.

Do not use a fixed sleep interval as a guarantee that the registry has synchronized. Observe logs, refresh configuration, and registry state for the active implementation.

### No available instances remain

Instances may have deregistered on shutdown, been marked unhealthy, or been removed from the registry after heartbeat/lease expiration. Health check and eviction mechanisms can introduce delay. The registry reflects discovery status, not an instantaneous measurement of every business function of an instance.

### Service ID mismatch

Wrong names, wrong profiles, stray whitespace, or naming convention differences can prevent queries from matching. Log the resolved service ID after configuration loads, and use constants or centralized configuration for important service names.

## 4. Distinguishing empty results from query errors

Empty lists and exceptions must be handled separately.

| Situation | Common signs | Investigation direction |
| --- | --- | --- |
| Service ID not in registry view | Returns empty list; ID may be absent from `getServices()`. | Check service name, registration, and profile. |
| Service known but no instances yet | ID appears in service list; instance list is empty. | Check readiness, health checks, deregistration, and synchronization. |
| Registry unreachable | May raise timeouts, connection errors, or runtime exceptions depending on implementation. | Check DNS, network, ports, TLS, authentication, and server status. |
| Wrong endpoint configuration | Hostname resolution error, failed connection, or querying the wrong environment. | Check registry URL and environment-specific configuration. |
| Implementation-side error | Exception while reading or converting discovery data. | Capture stack trace, library version, and root cause. |

Some clients may continue using cached data during temporary registry disconnection; other implementations may fail immediately. Never assume every connection error turns into an empty list. Conversely, never assume the registry is broken just because one service ID returns an empty list.

## 5. Writing code that handles results explicitly

Example service wrapper that validates input, preserves the distinction between empty lists and query errors, and retains the root cause:

~~~~java
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceLookup {

    private static final Logger log =
            LoggerFactory.getLogger(ServiceLookup.class);

    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        if (serviceId == null || serviceId.trim().isEmpty()) {
            throw new IllegalArgumentException("serviceId must not be blank");
        }

        try {
            List<ServiceInstance> instances =
                    discoveryClient.getInstances(serviceId);

            if (instances.isEmpty()) {
                log.info("No instances currently discovered for serviceId={}",
                        serviceId);
            }

            return instances;
        } catch (RuntimeException ex) {
            log.warn("Discovery query failed for serviceId={}", serviceId, ex);
            throw new IllegalStateException(
                    "Unable to query discovery for serviceId=" + serviceId, ex);
        }
    }
}
~~~~

Here, an empty list is returned as a handleable business result. Exceptions are logged and rethrown with the root cause preserved. In a real application, a domain-specific exception can be used instead of `IllegalStateException` so callers can classify failures more clearly.

Do not write code that catches every exception and returns `Collections.emptyList()`. That turns connection failures, authentication errors, or programming bugs into a false signal that the service has no instances. When that happens, it becomes very difficult to distinguish a genuinely unregistered service from a failing registry.

### Do not pick the first element as load balancing

Do not use `instances.get(0)` as a load-balancing algorithm. List order does not guarantee load distribution, health, or locality. When calling by service ID, integrate Spring Cloud LoadBalancer with the corresponding HTTP client so instance selection is managed according to configuration and the chosen strategy.

If selecting instances manually for a special requirement, explicitly define the strategy, handle empty lists, exclude unsuitable endpoints, and refresh the list when the registry changes.

## 6. Diagnostic flow when no instances are found

~~~~mermaid
flowchart TD
    A[Receive serviceId] --> B{Is serviceId valid?}
    B -->|No| C[Report input configuration error]
    B -->|Yes| D[Call DiscoveryClient]
    D --> E{Did query throw exception?}
    E -->|Yes| F[Check registry, network, TLS, auth]
    E -->|No| G{Does list have instances?}
    G -->|Yes| H[Pass to LoadBalancer / caller]
    G -->|No| I[Read getServices and check registry view]
    I --> J{Is Service ID in view?}
    J -->|No| K[Check name, registration, fetch, and environment]
    J -->|Yes| L[Check readiness, health, cache, and deregistration]
~~~~

Follow these steps in order:

1. **Verify input:** log the service ID after configuration loads; check for null, empty, whitespace, and wrong names.
2. **Check service list:** read `getServices()` to see which service IDs the client currently sees.
3. **Check instance list:** call `getInstances(serviceId)` and record the instance count.
4. **Check provider side:** verify the application has started, registered under the right service ID, and is in a ready state.
5. **Check registry:** verify the client connects to the right server/agent, has fetched data, and is not blocked by authentication or TLS.
6. **Check timing:** inspect registration timestamps, heartbeats, health checks, deregistration, and cache refresh intervals.
7. **Check network:** test DNS resolution and connectivity to the endpoint from the exact environment running the caller.

The registry dashboard or CLI helps cross-check server-side state. However, dashboard results do not replace inspecting the registry view that the caller application itself is using.

## 7. Retries, timeouts, and fallbacks

Not every case where no instance is found should be retried.

- **Wrong service ID or service not yet deployed:** this is usually a configuration error or long-lived state. Continuous retries only add load and log noise.
- **Application starting up:** bounded retries with short backoff may be applied if the deployment process allows delayed service registration.
- **Temporary registry disconnection:** use finite timeouts and bounded retries with backoff and jitter. Combine with a circuit breaker if appropriate to prevent all requests from piling onto a failing registry.
- **No healthy instances:** return a meaningful error to the caller, use a designed fallback, or enqueue work if business rules permit.

Retries should live at one clearly responsible layer. If the HTTP client, gateway, and service mesh all retry independently, actual request counts can grow exponentially. Set an overall request deadline and limit total attempts.

A fallback must not pretend a request succeeded. If returning cached data, define the acceptable TTL and staleness bounds. If rejecting the request, return an error status matching the API contract and provide information so the caller can retry later.

## 8. Logs, metrics, and alerts

To detect discovery incidents early, monitor:

- Lookup counts by service ID and outcome: found, empty, error.
- Discovery query latency and exception rate.
- Number of instances returned per service ID.
- Requests failed because no instance could be selected.
- Connection status to Eureka/Consul or the active discovery source.
- Time from provider registration until callers see the instance.

Logs should include service ID, outcome, environment, timestamp, and root exception on failure. Avoid logging usernames, passwords, tokens, or sensitive information. For metrics, use a stable service ID as a label; avoid full URLs, random instance IDs, or unbounded input values because they create high cardinality.

Distinguish "no instances available" alerts from "cannot query registry" alerts. The two events have different causes and remediation steps.

## 9. Testing edge cases

| Test scenario | Result to verify |
| --- | --- |
| Query valid service ID with two instances | Returns two instances and caller picks target via load balancer. |
| Query non-existent service ID | Receives empty list; does not treat it as an exception by default. |
| Provider has not started yet | Caller handles no-instance state without crashing or retrying infinitely. |
| Provider deregisters or is marked unhealthy | Instance count in registry view decreases according to refresh cycle. |
| Registry is disconnected | System records query error or follows expected cache behavior per implementation; does not silently turn error into empty list. |
| Wrong service ID due to profile config | Logs indicate the actual queried name and help locate the misconfiguration. |
| Registry recovers after interruption | Client refreshes registry and finds instances after synchronization. |

## Key takeaways

- `getInstances(serviceId)` normally returns an empty list when no instances currently exist; this is a valid result.
- `getServices()` helps diagnose whether a service ID is in the registry view, though it is not absolute proof of system-wide state.
- Non-existent service ID, service with no instances yet, and registry query error are three cases that must be distinguished.
- Do not catch exceptions and convert them into an empty list; preserve the cause for diagnostics.
- Do not use the first element of the list as a load-balancing algorithm.
- Retries must have limits, timeouts, and backoff; do not retry indefinitely for a wrong service ID or long-term missing instances.
- Track empty results and errors separately to operate discovery accurately.
