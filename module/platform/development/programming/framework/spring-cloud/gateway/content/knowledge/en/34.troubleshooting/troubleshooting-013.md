# New Route Not Taking Effect After Changes or Refresh

In the **Troubleshooting** chapter, this lesson explains how to handle the scenario where a **Spring Cloud Gateway** route has been updated in configuration or a service discovery source, yet requests still follow the old behavior. Gateway is the entry point of a microservices system: each route combines a target URI, route predicates, and a filter chain to decide which requests are forwarded, to which service, and how they are transformed. Thus, a change only takes effect once the new configuration reaches the right instance and the active route list has been updated.

## Symptoms and Scope to Check

Common symptoms:

- The new route does not appear in Gateway's route list.
- The route appears, yet requests still match an old route or return 404.
- One instance uses the new route while another instance still uses the old route.
- Calling the refresh endpoint returned success, yet routing behavior did not change.
- A route using `lb://...` is loaded, yet requests return 503 because no target service instance is found.

Before taking action, record the `route id`, target URI, predicates, expected filters, active profile, and instance handling the request. Identify the route declaration source: startup config file, Spring Cloud Config, DiscoveryClient, or a dynamic route repository. How you update depends on that source.

## Understand Route Update Layers Properly

A route flows through three related layers:

1. **Configuration source**: YAML file, Config Server, service registry, or dynamic route store holding the intended definition.
2. **Route definition**: Gateway reads definitions from configured `RouteDefinitionLocator` instances. Multiple sources can combine, such as routes declared in properties and routes generated from DiscoveryClient.
3. **Active running route**: Gateway compiles definitions into routes with instantiated predicates and filters, after which `CachingRouteLocator` may cache the result to serve requests.

Changing the first layer does not guarantee the next two update automatically. For example, editing `application.yml` on disk or inside a running container normally does not make Spring Boot reload the file. Likewise, refreshing the Environment and refreshing the route cache are two operations with different purposes. Gateway publishes `RefreshRoutesEvent` to request rebuilding the route list; Gateway's refresh endpoint triggers this route-cache rebuild.

## Inspect the Route Definition Before Refreshing

Example route declared in `application.yml`:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: orders-api
          uri: lb://orders-service
          predicates:
            - Path=/api/orders/**
          filters:
            - StripPrefix=1
```

With this config, request `/api/orders/42` routes to `orders-service` through the load balancer; filter `StripPrefix=1` removes `/api` before forwarding. When editing URIs, predicates, or filters, verify the exact config file, profile, and property names used by the running instance. A file updated in a repository is not guaranteed to be the active config source inside the process.

If the app exposes the Gateway Actuator endpoint, you can inspect routes directly from the instance under investigation. Example management endpoint config:

```yaml
management:
  endpoint:
    gateway:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,gateway
```

Once enabled and exposed, call:

```bash
# List routes currently published by Gateway
curl -s http://localhost:8080/actuator/gateway/routes

# View details of a single route by id
curl -s http://localhost:8080/actuator/gateway/routes/orders-api
```

Endpoint names, access permissions, and exposure syntax may vary by Spring Boot/Spring Cloud Gateway version. Only expose management endpoints on a trusted management network protected by proper authentication and authorization; never expose them to the public Internet.

When reading the output, compare `id`, URI, predicates, and filters against your intended config. If the route is absent, focus on the definition source, profile, config loading, and instance. If the route is present yet requests still miss the right branch, check predicates, route order, and filters next.

## Refresh Workflow by Configuration Source

### 1. Routes Statically Declared in application.yml

If routes are loaded only from startup configuration, editing a file on disk does not automatically update the running process's Environment. Deploy the new configuration via the application's release mechanism, typically a restart or rolling restart of instances. Once instances start, verify routes via Actuator.

Do not rely on the cache refresh endpoint alone expecting Gateway to re-read an arbitrary file on disk. That endpoint refreshes routes from the current locator sources; it is not a file watcher.

### 2. Configuration Loaded from Spring Cloud Config

When using Spring Cloud Config and Spring Cloud Context, refresh the Environment first to pull new values from Config Server. If the refresh endpoint is exposed under controlled access, call:

```bash
curl -i -X POST http://localhost:8080/actuator/refresh
```

Then re-read routes with `GET /actuator/gateway/routes`. Spring Cloud Gateway can emit a route-refresh event upon receiving a refresh-scope event. If routes still do not reflect the desired config, trigger Gateway's route cache refresh directly:

```bash
curl -i -X POST http://localhost:8080/actuator/gateway/refresh
```

The two endpoints do not replace one another: `/actuator/refresh` refreshes Environment configuration in Spring Cloud Context apps; `/actuator/gateway/refresh` tells Gateway to rebuild its route cache from its configured definition locators. Both take effect only when enabled, exposed, and invoked against the intended instance. If using Spring Cloud Bus, confirm the refresh event reached every target instance.

### 3. Routes Generated from DiscoveryClient

With service discovery configured, Gateway can auto-generate routes from the service registry. Verify the service registered with the right name, status, and namespace; verify DiscoveryClient sees the new registration; then confirm Gateway updated its route list. Registry updates can depend on polling intervals or event mechanisms of the discovery implementation in use.

If the route exists yet `lb://service-name` returns 503, inspect the instance list and Spring Cloud LoadBalancer integration. That is usually a target-instance resolution or selection failure, not proof that the route cache failed to refresh.

### 4. Routes Stored in a Dynamic Repository

If using `RouteDefinitionRepository` or a custom route management mechanism, first confirm the update wrote the new definition into the exact repository Gateway reads. Then publish `RefreshRoutesEvent` or invoke Gateway's refresh endpoint to rebuild active routes. With in-memory repositories, data exists only on a single instance; updating instance A does not automatically sync to instance B.

## Checking Multiple Running Instances

In Kubernetes or behind a load balancer, requests can hit different pods across calls. One successful refresh on pod A does not prove pods B and C received the new config. Inspect each pod via internal management ports or port-forwarding, and compare route IDs, URIs, and predicates across every instance.

If only some pods are stale, check rollout status, mounted ConfigMaps/Secrets, environment variables, active profiles, and container image tags per pod. Updating a ConfigMap does not guarantee Spring Boot processes reload configuration. Choose one consistent cluster-wide mechanism: rolling restarts for static configs, or distributed refreshes via Spring Cloud Bus / your orchestration mechanism. Verify outcomes on every instance after dispatching the event.

## Separating Refresh Failures from Route-Matching Failures

Once the route appears in Actuator yet requests still fail, check in order:

- **Predicates**: does the request match the exact path, HTTP method, Host, headers, query, and scheme required by the route? For example, `Path=/api/orders/**` does not match `/orders/42`.
- **Route order**: did a higher-priority route match the request earlier? Check `order` and overlapping predicates.
- **Filter chain**: did `StripPrefix`, `RewritePath`, `SetPath`, `AddRequestHeader`, or custom filters transform the request as expected?
- **Target URI**: does `http://...` point to the right host/port? For `lb://...`, are the service name and instance list valid?
- **Upstream response**: distinguish a 404 due to Gateway finding no route from a 404 returned by the downstream service. Use logs and traces to confirm whether the request was forwarded.

Detailed logging can be enabled temporarily in test environments or during an investigation window:

```yaml
logging:
  level:
    org.springframework.cloud.gateway: DEBUG
    org.springframework.cloud.gateway.route: DEBUG
```

Correlate request arrival timestamps, selected routes, applied filters, and upstream URIs. Disable DEBUG logging once finished, as verbose logs inflate log volume and can expose operational details.

## Quick Isolation Table

| Observation | Priority Causes to Check | Resolution |
|---|---|---|
| New route missing from Actuator | Wrong profile/property, un-updated config source, locator has not read new definition | Check config source and instance; refresh Environment or redeploy config from the right source |
| Route still shows old URI or predicate | Environment or route cache not refreshed | Refresh config source first, then inspect and refresh route cache |
| Only some pods have the new route | Refresh ran on only one instance or config drift across pods | Inspect each pod; use distributed refresh or rolling restart |
| New route appears in Actuator yet requests return 404 | Predicate mismatch, another route matched, or upstream returned 404 | Check path/host/method, route order, filters, and upstream logs |
| `lb://...` route appears in Actuator yet returns 503 | No healthy instances available or LoadBalancer/discovery failed to resolve service | Check service registry, service name, and instance status |
| Refresh succeeded yet route unchanged | Cache refreshed against stale definition source, or wrong instance called | Check route source, Environment, and each pod before refreshing again |

## Confirming Completion and Rollback

Consider the incident resolved only when:

1. The config source or repository holds the exact new definition.
2. The route endpoint on every traffic-serving instance displays the expected URI, predicates, and filters.
3. Test requests match the intended route, reach the right upstream, and produce the expected transformed path/headers.
4. Cluster instances share identical route state; logs no longer show requests hitting old configs.

If the change introduces regressions, restore the prior definition in the exact config source, redeploy or refresh via that source's mechanism, and re-verify routes on every instance. Record the route ID, config source, affected instances, and refresh/rollout steps taken so future investigations can reproduce them.

## Key Takeaway

When a new route has not taken effect, pinpoint whether the new data has reached the config source, route definitions, and active running routes. Refresh the Environment when the config source changes; refresh the route cache when Gateway must rebuild its route list; and verify every instance before concluding. Inspecting layer by layer prevents mistaking config-loading failures for predicate, filter, service discovery, or upstream bugs.
