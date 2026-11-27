# Consul Reports Critical Due to Wrong Health Check Path, Port, or Permissions

Consul can register a service successfully yet still mark the instance as critical. These are two separate things: registration creates a service record in the catalog, while health checks periodically evaluate whether the instance meets operational requirements. When an HTTP check calls the wrong path, wrong port, an unreachable address, or is rejected by the endpoint due to permissions, Consul keeps the record while its health status transitions to critical.

This article focuses on services using HTTP health checks, especially when Spring Boot/Spring Cloud Consul applications run in Docker Compose or Kubernetes. You must test from the exact network location where the Consul Agent performs the check before modifying registration or security settings.

## Distinguishing Service Registration from Health Checks

The Consul Agent receives a service configuration, registers both the service and its check into the agent/catalog, and then executes the check periodically. For HTTP checks, the agent sends requests to the configured URL. Outcomes are typically interpreted as follows:

| Check result | Typical status | Meaning |
|---|---|---|
| HTTP returns 2xx | passing | Health endpoint responded successfully |
| HTTP returns non-2xx | critical | Endpoint failed passing criteria |
| Hostname fails to resolve | critical | DNS or network namespace cannot resolve address |
| Connection refused / timeout | critical | Wrong port, process not listening, or network blocked |
| HTTP 401/403 | critical | Check lacks credentials or sufficient permissions |
| TLS handshake/certificate error | critical | Invalid scheme, CA, hostname, or certificate |

Successful service registration does not imply a passing health check. Conversely, a check may exist while the service registration was deregistered or is no longer managed by the agent. During investigation, inspect both the service record and the check record.

Basic flow:

    Consul Agent receives service definition
        -> Registers service and check
        -> Agent runs HTTP health check on interval
        -> Checks DNS, TCP, TLS, and HTTP
        -> 2xx: passing; error: critical
        -> Health API filters passing instances
        -> Fix URL, port, network, or permissions and re-check

Consul does not automatically fix paths or open ports for your application. The check remains critical until the next check succeeds or the configuration is updated.

## Ordered Diagnostic Runbook

1. Identify the exact failing service ID and check ID in critical state.
2. Read the check reason and output from the Agent API or Consul UI.
3. Extract the actual check URL: scheme, hostname/IP, port, path, method, and headers.
4. Send the exact same request from the Consul Agent's network namespace.
5. Compare the check URL against the application's server port, context path, and management/Actuator port.
6. Check TLS, redirects, authentication, ACLs, and network policies.
7. Fix one root cause at a time, wait for the next interval, and confirm the check turns passing.
8. Re-check the Health API both with and without the `passing=1` filter.

Do not conclude from a `curl` command run on a developer laptop. The Consul Agent is the component issuing the check; an address reachable from a laptop yet unreachable from the agent's container/pod will remain critical.

## 1. Reading Check ID, Status, and Output

Start in the Consul UI: open the service, select the instance, and inspect the health checks section. Record the check ID, status, last update time, and output message. The output usually indicates whether the failure is DNS, connectivity, HTTP status, TLS, or timeout.

You can query checks managed by the local agent:

    curl -s http://127.0.0.1:8500/v1/agent/checks

Or list services managed by that agent:

    curl -s http://127.0.0.1:8500/v1/agent/services

The `/v1/agent/*` APIs return the local state of that agent. If calling a Consul Server from another machine, ensure you are inspecting the right agent that registered the instance.

With ACLs enabled, API requests require a token with appropriate permissions. Do not put tokens into command lines or shell history when sharing logs; prefer environment variables/secret stores and redact tokens in outputs.

## 2. Checking Wrong HTTP Paths

The health check must call the exact endpoint exposed by the application. With Spring Boot Actuator, the default path is usually `/actuator/health`, though it can be altered by:

- `management.endpoints.web.base-path` changing the Actuator prefix.
- `management.endpoints.web.path-mapping` changing the health endpoint path.
- `server.servlet.context-path` adding a context path for the servlet application.
- `management.server.port` placing management endpoints on a separate port.
- A gateway or reverse proxy adding/stripping prefixes, whereas the Consul Agent usually calls the service address directly without passing through the Gateway.

For example, if the app uses context path `/inventory` and Actuator base path `/manage`, the endpoint may be `/inventory/manage/health` instead of `/actuator/health`. If the management server uses port 9091, the URL must use that port.

Spring Boot configuration example:

    server:
      port: 8080

    management:
      server:
        port: 9091
      endpoints:
        web:
          base-path: /manage
          exposure:
            include: health,info

In the configuration above, the management server's health endpoint typically looks like `http://<host>:9091/manage/health`. If the application also configures a dedicated context path for the management server or does not split the management port, the URL will differ. Do not automatically prepend `server.servlet.context-path` to the URL when the management server runs separately; verify the actual path from mapping logs or by calling directly from the same environment.

### Choosing the Right Health Endpoint

With Spring Boot, you can use `/actuator/health` or the readiness endpoint when health probes are enabled, such as `/actuator/health/readiness`. Readiness fits well when you want Consul to treat an instance as ready for traffic only after startup finishes and essential dependencies are ready.

Do not use liveness as the sole condition for receiving traffic if liveness only verifies the process is alive. Likewise, do not include non-essential dependencies in readiness such that the service gets pulled from the registry whenever a minor secondary component glitches.

Ensure the endpoint is exposed over HTTP. Creating an Actuator bean or adding a dependency is not enough if the endpoint is unexposed or the management server binds only to loopback.

## 3. Checking Service Port and Health Check Port

A common mistake is registering the service on port 8080 while the health endpoint runs on management port 9091. If the check hits port 8080, requests may hit the wrong application or receive 404. If the service registers port 9091 while business APIs listen on 8080, consumers call the wrong port.

Distinguish three values:

| Value | Used for | Example |
|---|---|---|
| Service port | Port consumers use to call service APIs | 8080 |
| Health check port | Port Consul Agent uses to call the check endpoint | 9091 |
| Published host port | Port on the host mapped into the container | 18080 or 19091 |

The health check URL can specify its own port, independent of the service port in the catalog. Example where the service listens for APIs on 8080 while management health runs on 9091:

    service {
      name = "inventory-service"
      id   = "inventory-node-1"
      address = "inventory-service"
      port = 8080

      check {
        id       = "inventory-http-health"
        name     = "Inventory readiness"
        http     = "http://inventory-service:9091/actuator/health/readiness"
        method   = "GET"
        interval = "10s"
        timeout  = "2s"
      }
    }

This is an illustrative service definition for a Consul Agent. The hostname `inventory-service` is valid only if the Consul Agent can resolve that name from its own network. If the agent runs in a separate container on a different network, use an address reachable by the agent.

### Do Not Confuse Host Port with Container Port

In Docker Compose, if `18080:8080` is declared, other containers on the same network typically call `inventory-service:8080`, not `inventory-service:18080`. Host port 18080 is for clients going through the Docker host.

If the Consul Agent runs on the host, it may need to call `localhost:18080`. If the Consul Agent runs in a container on the same network as the app, it should call the service DNS and container port. If the agent is in a container on a different network, attach the appropriate network or use a routable advertised address.

## 4. Checking Address and Network from the Consul Agent's Perspective

The Consul Agent is what executes the HTTP check. From the agent itself, verify:

- Does the DNS hostname resolve?
- Are the IP and port routable?
- Is the process listening on an interface reachable from the agent?
- Is a network policy, firewall, or security group blocking traffic?
- Do the agent and service share the appropriate network namespace or bridge network?

For example, with Docker Compose, if the Consul container is named `consul-agent` and the service is `inventory-service`, ensure both belong to the same network:

    services:
      consul-agent:
        image: hashicorp/consul:1.20
        networks:
          - backend

      inventory-service:
        image: example/inventory-service:1.0
        networks:
          - backend
        expose:
          - "8080"
          - "9091"

    networks:
      backend:

`expose` is not a firewall rule and does not substitute for network membership. What matters is that the Consul Agent can connect to the listening port of the application.

Test from the agent container (if the image has `curl` and DNS tools):

    docker compose exec consul-agent sh
    getent hosts inventory-service
    curl -v --connect-timeout 2 http://inventory-service:9091/actuator/health/readiness

If the Consul image lacks `curl`, attach a debug container to the same network to test the path; preserve the exact DNS/network view of the agent. Testing from a laptop or from the application's own container cannot replace this step.

With Kubernetes, the Consul Agent may run as a sidecar/DaemonSet or another topology. Run test commands from the exact agent pod/container; determine whether the check uses Pod IP, Service DNS, or localhost. `localhost` inside an independent container refers to that container itself; inside a sidecar sharing a pod network namespace, `localhost` can reach ports of the app container in the same pod.

### Checking the Bind Address

An application bound to `127.0.0.1` accepts only loopback connections. If the Consul Agent sits in another container/pod, requests to the container IP will fail even though `curl localhost` succeeds inside the app container.

For services that must receive network connections, configure Spring Boot to listen on the right interface, typically `0.0.0.0` inside containers. Then advertise a service address reachable by consumers and a check URL reachable by the agent. Never register `localhost` as the service address when consumers live elsewhere.

## 5. Checking HTTP Status, Method, and Timeout

Consul HTTP checks generally treat 2xx responses as passing. Responses with 3xx, 4xx, or 5xx that do not satisfy passing conditions make the check critical; redirects may behave differently depending on follow-redirect settings and redirect limits. For simpler diagnostics, point the check directly at the final health endpoint rather than a redirecting endpoint.

Check:

- The method matches the endpoint, typically `GET` for Actuator health.
- The URL does not point to a business endpoint requiring parameters or a request body.
- The endpoint does not return 401/403 due to Spring Security.
- The endpoint does not return 404 due to a wrong base path or unexposed endpoint.
- The endpoint does not return 503 when readiness is not met or a required dependency is unavailable.
- Check timeout is long enough for normal responses yet short enough not to mask a hung service.

Example check configuration with timeout and interval:

    check {
      id       = "inventory-readiness"
      name     = "Inventory readiness"
      http     = "http://inventory-service:9091/actuator/health/readiness"
      method   = "GET"
      interval = "15s"
      timeout  = "3s"
    }

A 15-second interval and 3-second timeout are illustrative only. Choose values based on startup time, p95/p99 latency of the health endpoint, and failure detection requirements. Too short a timeout causes false critical states under load; too long a timeout delays real failure detection.

## 6. Checking Authentication, Spring Security, and Consul ACLs

A health endpoint may return `401 Unauthorized` or `403 Forbidden` if Spring Security protects Actuator. The Consul Agent does not log in using a user session. Choose a clear policy:

1. Expose only a minimal readiness endpoint on the internal network and permit the agent to reach that endpoint.
2. Or configure the HTTP check to send an appropriate auth header while managing the secret via a secret store and restricting read access.

Example Spring Security permitting only the readiness endpoint; actual matchers must match your app's paths and context path:

    http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/actuator/health/readiness").permitAll()
        .requestMatchers("/actuator/**").hasRole("OPS")
        .anyRequest().authenticated()
    );

Permit only the minimal health endpoint, never open all of `/actuator/**`. Verify `management.endpoints.web.exposure.include` exposes the corresponding endpoint and the management server is not bound to an interface unreachable by the agent.

### Sending Headers with an HTTP Check

Consul HTTP checks support declaring headers sent with the request. If the endpoint requires a token, configure headers using the syntax of your service definition/Consul version. Illustrative HCL example:

    check {
      id       = "inventory-authenticated-health"
      name     = "Inventory authenticated readiness"
      http     = "http://inventory-service:9091/actuator/health/readiness"
      method   = "GET"
      interval = "15s"
      timeout  = "3s"
      header = {
        Authorization = ["Bearer HEALTH_CHECK_TOKEN"]
      }
    }

The header structure in HCL is a map from header name to list of values; when submitting via the JSON API, use the corresponding API schema. Check the schema of your deployed Consul version before applying. Never store real tokens directly in config files committed to Git. Prefer templating/secret injection, tight file permissions, and credential rotation.

### Distinguishing Consul ACLs from Application HTTP Endpoint Permissions

There are two independent permission layers:

- Consul ACLs: control who can call the Consul Agent/Server API, register services, read the catalog, or modify registry settings.
- HTTP health endpoint auth: controls whether the Consul Agent is permitted to call the application's `/actuator/health/...` endpoint.

A token with `service:write` permission to register a service is not automatically a valid credential for calling the application's Actuator endpoint. Conversely, an application bearer token does not grant read/write access to the Consul catalog.

With ACLs enabled, verify agent/service registration uses a token with appropriate `service:write` permissions per Consul policy; consumers need appropriate service/node read permissions for lookup. If the agent checks an endpoint with its own authentication, provide a dedicated header/token for that check. Never use a master/management token for all workloads.

## 7. Checking TLS and HTTPS Health Checks

If the check URL uses `https://`, the Consul Agent must trust the CA that issued the certificate and the hostname in the URL must match the certificate's SAN. Common errors:

- Using `https://` while the application only listens on HTTP.
- Using a hostname absent from the certificate SAN.
- Agent missing the internal CA or trust bundle.
- Expired certificate or incomplete chain.
- Setting skip-verify so the check passes while bypassing server identity verification.

HTTPS check example:

    check {
      id       = "inventory-https-health"
      name     = "Inventory HTTPS readiness"
      http     = "https://inventory.internal:9443/actuator/health/readiness"
      method   = "GET"
      interval = "15s"
      timeout  = "3s"
      tls_skip_verify = false
    }

Ensure the Consul Agent is configured with the proper CA/trust store. Only disable TLS verification temporarily for isolated diagnostics; never leave `tls_skip_verify = true` as a long-term production setting.

## 8. Spring Cloud Consul Discovery Configuration

With Spring Cloud Consul, the client can auto-register the service and create an HTTP health check based on discovery properties. Example:

    spring:
      application:
        name: inventory-service
      cloud:
        consul:
          host: consul-agent
          port: 8500
          discovery:
            enabled: true
            register: true
            service-name: inventory-service
            health-check-path: /actuator/health/readiness
            health-check-interval: 15s

`health-check-path` is the relative path Spring Cloud Consul uses to build the check URL. The instance host, port, and advertised address must match where the Consul Agent sends checks. If the app uses a separate management port, also configure the health-check URL/port using the properties supported by your release train, or declare the check separately via a Consul service definition.

Spring Cloud Consul properties can vary by version. Check `spring-configuration-metadata.json` and the reference guide for your release train, especially when using `management.server.port`, HTTPS, health check headers, or custom addresses.

Do not confuse `spring.cloud.consul.port` (the Consul Agent API port the client connects to) with the HTTP port of the registered application. These two ports serve two distinct flows.

## 9. Sample Service Definition with Consul Agent

When you need to control the check URL independently of application configuration, you can register the service using a definition file:

    service {
      name = "inventory-service"
      id   = "inventory-node-1"
      address = "inventory-service"
      port = 8080
      tags = ["api", "internal"]

      check {
        id       = "inventory-readiness"
        name     = "Inventory readiness"
        http     = "http://inventory-service:9091/actuator/health/readiness"
        method   = "GET"
        interval = "15s"
        timeout  = "3s"
      }
    }

In this example, consumers call service port 8080 while the Consul Agent calls the readiness endpoint on port 9091. The `inventory-service` address must resolve from the agent. If the service runs on the host, use a host address/port reachable by the agent; if running in the same Compose network, use service DNS and container ports.

Do not register the same service from both Spring Cloud Consul and a service definition file without a clear ID management plan. The two mechanisms may create two distinct service/check records or overwrite by ID; designate a single registration owner per instance.

## 10. Inspecting with the Consul API and CLI

### Agent API

View services and checks on the local agent:

    curl -s http://127.0.0.1:8500/v1/agent/services
    curl -s http://127.0.0.1:8500/v1/agent/checks

### Health API

View all instances of a service:

    curl -s http://consul-server:8500/v1/health/service/inventory-service

Fetch passing instances only:

    curl -s "http://consul-server:8500/v1/health/service/inventory-service?passing=1"

If the service appears in unfiltered output yet disappears when `passing=1` is added, inspect the status of each check to see which check is critical. The Health API gives the catalog/health view; the Agent API helps retrieve check output on a specific node.

### Consul CLI

    consul catalog services
    consul health checks inventory-service
    consul members

Run these commands in an environment with the Consul CLI and appropriate endpoint/token. When multiple datacenters/namespaces/partitions exist, verify you are querying the right scope.

## 11. Distinguishing HTTP Checks from TCP and TTL Checks

Choose the check type based on what you want to verify:

| Check type | What does it verify? | Limitations |
|---|---|---|
| HTTP | HTTP endpoint returns the expected status | Can turn critical due to path, auth, TLS, or app errors |
| TCP | A connection can be opened to host/port | Does not prove APIs or internal dependencies are healthy |
| TTL | Agent receives heartbeat/pass before TTL | Requires the app or helper process to send timely updates |
| Script | Custom check command succeeds | Requires execution permissions and managing script-on-agent risks |

Do not switch an HTTP check to a TCP check just to make the dashboard green if the goal is verifying API readiness. A TCP check can pass while the endpoint returns 500. Conversely, an HTTP check may turn critical because an auth-protected endpoint lacks credentials even though the process is healthy; fixing permissions/headers is more accurate than changing check types.

## 12. Deregistering After Prolonged Critical State

Consul supports auto-deregistering a service after its check stays critical continuously for a configured duration, typically via `deregister_critical_service_after` on the service check. Example:

    check {
      id                                 = "inventory-readiness"
      name                               = "Inventory readiness"
      http                               = "http://inventory-service:9091/actuator/health/readiness"
      interval                           = "15s"
      timeout                            = "3s"
      deregister_critical_service_after = "5m"
    }

Only use this feature when you want services that stay critical for an extended period removed from the catalog. It does not fix the root cause of the check failure and does not replace application restart/recovery mechanisms. Pick a duration long enough to avoid premature deregistration during brief network blips; verify the service re-registers once the process recovers.

## 13. Symptom and Remediation Table

| Output / Symptom | Possible cause | How to fix |
|---|---|---|
| 404 Not Found | Wrong path, context path, or Actuator base path | Call the actual endpoint; check management mapping |
| 401 Unauthorized | Health endpoint requires authentication | Permit internal readiness endpoint or configure check headers/token |
| 403 Forbidden | Spring Security, proxy, or policy denies access | Check matchers/roles/ACLs and request headers |
| connection refused | Wrong port or process not listening | Cross-check service port and health port; check bind address |
| i/o timeout | Firewall/network policy, slow endpoint, or too-short timeout | Test from agent, check route and measure latency; tune timeout reasonably |
| no such host | Agent cannot resolve hostname | Check network membership, DNS, and service alias |
| TLS/certificate error | Wrong CA, SAN, expiry, or scheme | Install proper CA, use cert-matching hostname, and check chain |
| Check passes in app container, critical in Consul | Tested from wrong network namespace | Run exact request from Consul Agent or debug container on same network |
| Catalog has service, `passing=1` returns empty | Check is critical or warning depending on filter | Read each check output and fix root cause |
| Critical persists, then service disappears | Configured critical deregistration timeout | Check `deregister_critical_service_after` and registration lifecycle |

## 14. Practical Recovery Workflow Example

Suppose the Consul UI reports `inventory-service` as critical with output saying HTTP GET to `http://inventory-service:9091/actuator/health/readiness` returned 404.

1. Open the Agent API to confirm the exact check ID and URL the agent executes.
2. Run `curl -i` from the Consul Agent container to that exact URL.
3. Try calling `/actuator/health` and `/actuator/health/readiness` to see which endpoint is actually exposed.
4. Check whether `management.endpoints.web.exposure.include` contains `health`, health probes are enabled, and context/base paths were altered.
5. Update `health-check-path` or the service definition to the right path.
6. Wait at least one health-check interval, then re-read the Agent API and Health API.
7. Confirm the instance appears in `passing=1` queries and consumers call the right advertised service address.

Another example: output is 401. In that case, path and port may be right; the issue is Spring Security. Permit only the readiness endpoint on the backend network or add a check header managed via secrets. After fixing, confirm the check passes and other management endpoints remain protected.

Do not delete and re-register the service as a first step. If the check definition is wrong, re-registering with the same configuration recreates the critical state and erases useful diagnostic clues.

## Implementation Checklist

1. Record service ID, check ID, URL, and critical output from the exact Consul Agent.
2. Check the path against context path, Actuator base path, and management port.
3. Distinguish service port, health-check port, and published host port.
4. Call the exact URL from the Consul Agent's network namespace.
5. Ensure the app binds to an interface reachable by the agent and DNS resolves.
6. Confirm HTTP method, 2xx status, timeout, and redirect behavior.
7. Check Spring Security and HTTP headers if the endpoint requires authentication.
8. Separate Consul ACL tokens from application endpoint credentials.
9. For HTTPS, check CA, certificate SAN, and TLS chain; never disable verify long term.
10. Have only one registration manager per instance or coordinate IDs explicitly.
11. Pick interval, timeout, and critical deregistration delay aligned with SLOs.
12. Confirm the check is passing and the instance appears in the Health API with `passing=1`.

## Conclusion

Consul reporting critical usually means the Agent cannot complete the configured health check, even though the service may already be registered. Read the check output and test the exact URL from the Agent's own network; verify path, context path, service/management ports, DNS, bind address, HTTP status, TLS, and endpoint permissions. Keep Consul ACLs separate from application authentication, then re-verify via both the Agent API and Health API. Only conclude the health check path is restored once the check turns passing and the instance appears in `passing=1` queries.
