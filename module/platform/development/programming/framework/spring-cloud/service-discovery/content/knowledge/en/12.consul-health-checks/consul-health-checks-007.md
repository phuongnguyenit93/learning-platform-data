# Deregistering Long-Failing Instances and Cleaning Up Stale Records

In a microservices system, an instance can stop unexpectedly because a host shuts down, a container is deleted, a process is killed, or an application server loses connectivity. If termination finishes before a deregister command can be sent, the service record may remain in the Consul Catalog. Health checks help Consul detect that the instance is no longer healthy; the health-check-critical-timeout property enables automatic service deregistration if a check stays in critical state for too long.

This mechanism cleans up prolonged failing registrations, but it does not replace proper application lifecycle termination. You must distinguish deregistering on the local agent from deleting a record directly from the catalog, while also identifying which component owns and might re-register the service.

## 1. Why Do Stale Service Records Appear?

Spring Cloud Consul registers the service with a Consul Agent. The Agent retains the service and health check metadata on the node, then syncs state to the Consul Catalog for consumers to query.

Under default settings, Spring Cloud Consul creates an HTTP health check calling the /actuator/health endpoint roughly every 10 seconds. When the check fails, Consul marks the instance critical. The record can remain in the catalog even when the instance is no longer serving requests.

Common scenarios include:

- The JVM process receives kill -9 or the container is removed before Spring runs its shutdown hook.
- The host running the application loses power or is terminated.
- A network partition prevents the Consul Agent from calling the health endpoint.
- The Consul Agent remains running while the application has stopped.
- The service was registered via a config file or API, and the file or registration persists after the application is removed.
- An orchestrator such as Nomad or Kubernetes still manages the workload and keeps re-registering the service.
- An operator deletes the service from the catalog, but the local agent still holds the registration and syncs it back.

A critical record does not mean the service has been deleted. Critical is a health state; deregistration is the operation that removes the registration and its attached checks.

## 2. Distinguishing Health Check, Critical Timeout, and Deregistration

The following three parameters serve distinct roles:

| Property | Purpose | Example |
|---|---|---|
| health-check-interval | Interval between Consul endpoint checks | 10s |
| health-check-timeout | Maximum wait time for one health endpoint call | 3s |
| health-check-critical-timeout | Duration a service may stay critical before automatic deregistration | 30m |

Do not confuse health-check-timeout with health-check-critical-timeout. An HTTP request may time out after 3 seconds, whereas the service is only automatically deregistered if the check remains critical for the full configured 30 minutes.

Health checks answer whether an instance is healthy. Critical timeout answers how long to retain a failing registration before deleting it. This window must be long enough to tolerate recoverable disruptions such as application restarts, brief upgrades, or temporary network interruptions.

## 3. Consul's DeregisterCriticalServiceAfter Mechanism

Consul supports the DeregisterCriticalServiceAfter field in service-attached health check configurations. When a check remains critical longer than the configured duration, Consul automatically deregisters the service and all checks associated with it.

Spring Cloud Consul exposes the property:

    spring:
      cloud:
        consul:
          discovery:
            health-check-critical-timeout: 30m

This property maps to Consul's DeregisterCriticalServiceAfter. No default value is set in Spring Cloud Consul; when left unset, the application does not ask Consul to automatically deregister via critical timeout through this property.

Important Consul details:

- DeregisterCriticalServiceAfter has been available since Consul 0.7; confirm your running Consul version supports this field.
- The minimum timeout is 1 minute.
- The critical-service cleanup reaper runs on a 30-second cycle, so actual deregistration can occur slightly later than the configured timeout.
- The service and its attached health checks are removed from registration; the Consul node itself is not automatically deleted just because a service is deregistered.
- The timeout should be significantly longer than any recoverable service outage window.

For example, setting 30 minutes means Consul keeps the service in the catalog while its check is critical during that window. If the check returns to passing before the timeout elapses, the automatic deregistration condition is no longer met.

## 4. Configuring Spring Cloud Consul

Example Spring Boot service configuration using Actuator:

    spring:
      application:
        name: inventory-service
      cloud:
        consul:
          host: consul-agent.internal
          port: 8500
          discovery:
            enabled: true
            register: true
            register-health-check: true
            health-check-path: /actuator/health
            health-check-interval: 10s
            health-check-timeout: 3s
            health-check-critical-timeout: 30m

In this example:

- The service is registered under the name inventory-service.
- The Consul Agent calls /actuator/health every 10 seconds.
- Each health endpoint call has a 3-second wait limit.
- If the health check remains critical for the configured duration, Consul automatically deregisters the service and its attached checks.

Ensure the health endpoint is genuinely exposed, reachable from the Consul Agent, and returns appropriate HTTP status codes. If the endpoint returns 401, 403, 404, or 503 due to misconfiguration, Consul may mark the service critical even while the JVM process is running.

The health check must be attached to the service. If an independent node-level check is registered, that check does not represent a specific service and cannot be used to automatically clean up a service registration as intended.

## 5. How to Choose a Critical Timeout

Do not pick a timeout merely out of a desire to clear records quickly. Determine the maximum outage duration the system allows before treating an instance as unrecoverable.

Illustrative example thresholds:

| Service Type | Illustrative Timeout | Rationale |
|---|---:|---|
| Short-lived, easily recreated worker | 5–10 minutes | Can be cleaned up quickly once a job or container ends |
| Standard internal API | 15–30 minutes | Allows restarts, deployments, and brief network disruptions |
| Critical stateful service | 30–60 minutes or per policy | Avoids deleting registrations during longer yet recoverable incidents |

The thresholds above are discussion examples only. Base your decision on startup time, maintenance windows, autoscaling behavior, service criticality, and actual recovery procedures.

A timeout that is too short can delete registrations of recovering instances. A timeout that is too long leaves critical records around for an extended time, cluttering catalog visibility and increasing the risk of consumers or operational tools reading stale data if health status is not filtered.

## 6. Using Health Filtering Before Deregistration

You do not have to wait for the critical timeout to stop consumers from selecting failing instances. Spring Cloud Consul provides the query-passing property:

    spring:
      cloud:
        consul:
          discovery:
            query-passing: true

When query-passing is enabled, Spring Cloud Consul requests Consul to return only instances with passing checks during health service queries. Critical instances will not appear in the list used by consumers, even while their registrations remain in the catalog.

Distinguish clearly:

| Status | Registration in Catalog | Discovery Result When query-passing=true |
|---|---|---|
| passing | Present | Returned |
| warning | Present | Not returned |
| critical | Present until deregistered or recovered | Not returned |
| Deregistered | Removed | No longer returned |

Health filtering removes failing instances from traffic routing much faster. Critical timeout handles cleaning up registrations after prolonged failure. The two mechanisms complement each other.

## 7. Normal Deregistration on Application Shutdown

Automatic deregistration after a critical timeout is a fallback for abnormal instance termination. When an application stops gracefully, Spring Cloud Consul should send a deregister request during shutdown.

Spring Cloud Consul includes lifecycle auto-registration. When a service is registered by the application, the lifecycle handles registration and deregistration alongside the application lifecycle. The spring.cloud.consul.discovery.deregister property controls deregistration when the lifecycle stops; current default settings enable this behavior.

Example keeping lifecycle and deregister active:

    spring:
      cloud:
        consul:
          discovery:
            register: true
            deregister: true
            lifecycle:
              enabled: true

Stop the application via a graceful shutdown procedure so Spring has time to execute callbacks and send the request to Consul. If a container is force-killed, a host loses power, or the Consul Agent is unreachable, the deregister call may fail to reach Consul. Critical timeout remains necessary as a backup safety net.

Do not disable deregister in production unless an alternative mechanism exists to clean up registrations during normal shutdown.

## 8. Distinguishing the Local Agent and the Consul Catalog

This is the most critical point when handling leftover records.

Consul maintains two views:

- **Local Agent:** services and checks managed by the agent on a single node.
- **Catalog:** service and node data published by the Consul cluster system-wide.

Information in the two places can temporarily diverge when the cluster lacks a leader or is mid-sync. Agents run an anti-entropy mechanism to re-sync within a few seconds in most cases.

Inspection APIs:

    GET /v1/agent/services
    GET /v1/agent/checks
    GET /v1/catalog/services
    GET /v1/catalog/service/inventory-service

If the service still appears in /v1/agent/services, the local agent still manages that registration. If the service appears only in the catalog and not on the corresponding agent, it may be a stale record requiring inspection and cleanup at the catalog level.

Do not delete from the catalog before identifying which agent owns the service. If the agent still holds the registration, it can sync and re-register the service after catalog deletion.

## 9. Deregistering a Service Still Present on a Local Agent

If the service is still registered on a Consul Agent, deregister it through the exact agent that created the registration.

Using the CLI:

    consul services deregister -id inventory-service-8080

Or using the Agent HTTP API:

    curl --request PUT \
      http://127.0.0.1:8500/v1/agent/service/deregister/inventory-service-8080

Replace inventory-service-8080 with the actual ServiceID. ServiceID is the instance identifier on the agent, not necessarily equal to the service name inventory-service.

The agent removes the service along with its associated checks and syncs the change to the Consul Catalog. This API deletes only registrations managed by the local agent receiving the request.

The ACL permission required for agent service deregistration is service:write. If using a token, pass it via the X-Consul-Token header and never write real tokens into documentation, shell history, or logs.

## 10. Handling Records Remaining Only in the Catalog

If the host or Consul Agent is completely gone and the registration no longer exists on an agent, you may need to remove the record directly from the Consul Catalog.

First, retrieve node, datacenter, and ServiceID details:

    GET /v1/catalog/service/inventory-service

A result may contain:

    {
      "Node": "worker-03",
      "Datacenter": "dc1",
      "ServiceName": "inventory-service",
      "ServiceID": "inventory-service-8080",
      "ServiceAddress": "10.0.2.15",
      "ServicePort": 8080
    }

After verifying the exact record to delete, send a PUT to the Catalog API:

    curl --request PUT \
      --header "X-Consul-Token: $CONSUL_HTTP_TOKEN" \
      --header "Content-Type: application/json" \
      --data '{
        "Datacenter": "dc1",
        "Node": "worker-03",
        "ServiceID": "inventory-service-8080"
      }' \
      http://127.0.0.1:8500/v1/catalog/deregister

The Catalog API requires node:write and service:write. This is a low-level API for modifying the catalog directly; HashiCorp documentation recommends using the Agent API whenever the local agent still exists because the Agent API is simpler and backed by anti-entropy.

Never send a payload containing only Node if the goal is to delete a single service. When only Node is provided, Consul can delete the node along with all of its services and checks. To remove an individual instance, supply the exact Datacenter, Node, and ServiceID.

## 11. Handling Services Managed by Config Files or Orchestrators

Some services are not registered directly by Spring Cloud, but declared in Consul Agent configuration files or managed by an orchestrator.

**Services declared via Consul config files**

- Locate the service definition file in the agent's config directory.
- Delete or edit the service definition in the file.
- Run consul reload or reload the agent per operational procedure.
- Verify the service no longer appears in /v1/agent/services or the Catalog.

If you only call the deregister API while the config file remains, the agent may re-register the service upon reload or restart.

**Services managed by an orchestrator**

If Nomad, Kubernetes, an operator, or a deployment agent manages the service, update the workload or configuration at the owning source. If you only delete the record from Consul, the orchestrator can recreate the registration while the workload still exists or gets reconciled.

The rule is to remove the registration at the source that creates and maintains it. The Consul Catalog is a synchronized projection from those sources; manually editing the catalog does not always change desired workload state.

## 12. Why Does a Service Reappear After Deregistration?

If a service disappears and then comes back, check these causes:

1. **Local agent still holds the registration:** catalog was cleared without deregistering on the agent.
2. **Application is still running:** Spring Cloud Consul or another process continues registering the service.
3. **Config file still exists:** the agent reloads the service definition on reload or restart.
4. **Orchestrator reconciliation:** Nomad, Kubernetes, or an operator re-registers the service from workload state.
5. **Wrong ServiceID:** deleted the wrong instance or passed service name instead of specific ID.
6. **Multiple agents:** the service is registered on another node while only one node was checked.
7. **Multiple datacenters or namespaces:** queries or delete calls target the wrong scope.

When investigating, compare /v1/agent/services with /v1/catalog/service/{serviceName}, inspect Node and Datacenter, and trace the source owning the registration. Do not repeat catalog deletions before addressing the root cause of re-registration.

## 13. Safe Cleanup Procedure for Stale Records

Apply this procedure when a prolonged critical instance is detected:

1. **Identify the instance:** retrieve service name, ServiceID, Node, Datacenter, address, and port from the Consul Catalog.
2. **Confirm status:** inspect health check ID, critical status, output, and update timestamp.
3. **Identify the owner:** check the local agent, config files, Spring Boot process, and orchestrator.
4. **Prevent re-registration:** stop the workload or update the config source if the service is no longer in use.
5. **Choose the right deregister path:** use the Agent API if the local agent still owns the registration; use the Catalog API if only a catalog record remains and the old agent is gone.
6. **Verify:** check agent services, agent checks, catalog service, and health service queries.
7. **Check consumers:** confirm DiscoveryClient or LoadBalancer no longer receives the old instance once caches refresh.
8. **Monitor:** observe the catalog for a period to confirm the registration does not reappear.

Even if a service was automatically deregistered due to critical timeout, still verify the source of truth and agent state. A service disappearing from the catalog does not prove the old process stopped or that an orchestrator will not recreate the workload.

## 14. Security and Access Control for Deletion Operations

Deregistration modifies system state and can disrupt traffic. Apply these safeguards:

- Grant only service:write for agent deregistration and node:write plus service:write for catalog deregistration where genuinely needed.
- Use narrowly scoped ACL tokens rather than full admin tokens for periodic cleanup scripts.
- Log ServiceID, Node, Datacenter, operator, reason, and operation outcome.
- Verify the target instance before deleting; do not rely solely on service name since one service can have multiple instances.
- Never delete a node when targeting only a single service instance.
- Protect the Consul HTTP API with a management network, TLS, and ACLs.
- Check namespace or partition if using Consul Enterprise to avoid operating on the wrong scope.

For automated workflows, verify critical duration, registration source, and workload state before calling deletion APIs. Never bulk-delete based solely on a point-in-time critical status.

## 15. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Service is critical but does not auto-deregister | health-check-critical-timeout not configured or Consul version lacks support | Check service check configuration and Consul version |
| Timeout elapsed yet service remains | Consul reaps on a 30-second cycle or check has not stayed continuously critical long enough | Check check state and wait one more cleanup cycle |
| Service removed too early | Critical timeout shorter than real recovery time | Increase timeout and review the health endpoint |
| Agent API returns Unknown service ID | Called wrong agent or used service name instead of ServiceID | Check /v1/agent/services on the right node |
| Catalog API deletion fails | Missing ACL, wrong Node, Datacenter, or ServiceID | Verify payload and node:write/service:write privileges |
| Service reappears | Agent, config file, or orchestrator still registers it | Remove at the registration's owning source |
| Consumer still sees old instance | Discovery or LoadBalancer cache has not refreshed | Check query-passing and cache refresh intervals |
| Node remains after service deregistration | Service deregistration does not remove nodes | Only remove a node after it is decommissioned and holds no valid services/checks |

When Consul Agent and Catalog disagree, inspect agent logs and leader/anti-entropy status. Short-lived discrepancies can occur during synchronization; if persistent, check ACLs, agent-server connectivity, and the registration source.

## 16. Summary

Spring Cloud Consul supports automatic deregistration of long-failing services via the health-check-critical-timeout property, mapped to Consul's DeregisterCriticalServiceAfter. When a service-attached check stays critical beyond the configured duration, Consul removes the service and its associated checks. The cleanup task runs periodically, so actual removal may occur slightly after the timeout.

When cleaning up stale records, determine whether the service resides on a local agent or only in the catalog. Use the Agent API to remove registrations managed by an agent; use the Catalog API for orphaned catalog records when the originating agent no longer exists. If the service is managed by config files or an orchestrator, update the registration source to prevent the service from reappearing.

Combining graceful shutdown, health checks, critical timeout, query-passing, and controlled catalog cleanup keeps the registry accurately reflecting instances capable of serving traffic.

## References

- [Spring Cloud Consul — Service Discovery](https://docs.spring.io/spring-cloud-consul/reference/discovery.html)
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html)
- [Consul — Health Check Configuration Reference](https://developer.hashicorp.com/consul/docs/reference/service/health-check)
- [Consul — Check Agent HTTP API](https://developer.hashicorp.com/consul/api-docs/agent/check)
- [Consul — Service Agent HTTP API](https://developer.hashicorp.com/consul/api-docs/agent/service)
- [Consul — Catalog HTTP API](https://developer.hashicorp.com/consul/api-docs/catalog)
- [Consul — Services Deregister Command](https://developer.hashicorp.com/consul/commands/services/deregister)
