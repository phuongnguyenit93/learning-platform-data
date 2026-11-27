# Runbook for UNAVAILABLE spikes

This runbook guides incident response when the gRPC `UNAVAILABLE` status rate spikes abnormally in a Spring gRPC system. `UNAVAILABLE` is canonical status code 14, typically indicating an RPC could not complete because a service or transport is temporarily unavailable. However, this status alone does not prove the server is down: it may be returned explicitly by the server, triggered by client connection failures, caused by a load balancer picking a bad endpoint, DNS/TLS/HTTP2 issues, or an unready server-side dependency.

During an incident, the goal is to determine blast radius, separate application errors from connectivity errors, restore serving capacity without triggering a retry storm, and verify error rates and latency return to baseline. Use method name, status, endpoint, timestamp, and trace/request IDs to isolate the issue; never log tokens or sensitive payloads.

## 1. Detect and confirm the incident

Trigger this runbook when one or more signals breach defined thresholds:
- The rate of RPCs ending in `UNAVAILABLE` rises rapidly above baseline.
- Successful request counts drop while incoming traffic remains steady.
- Clients log connection failures, channels enter `TRANSIENT_FAILURE`, or RPCs time out.
- Multiple service consumers report errors to the same provider or deployment region simultaneously.
- Alerts fire concurrently for pod restarts, readiness failures, shrinking endpoint counts, DNS, or load balancers.

Before acting, confirm this is a rate increase rather than a pure absolute-count increase from higher traffic. Compare across method, service, client application, zone/cluster, server instance, and release version.

Minimum data checklist to collect:

| Signal | Question |
| --- | --- |
| Request rate | Did traffic spike or concentrate on one consumer? |
| Error rate by status | Did UNAVAILABLE rise alone or did all statuses rise together? |
| Method | Is one RPC affected or every method on the service? |
| Client/service version | Did errors begin after a specific client or server rollout? |
| Endpoint/zone | Is only one pod, node, zone, or the entire provider affected? |
| Latency and deadline | Is UNAVAILABLE rising alongside DEADLINE_EXCEEDED or failing immediately on connect? |
| Server health | Are pod readiness, restarts, CPU, memory, GC, or queues abnormal? |
| Dependencies | Are databases, HTTP services, brokers, or DNS failing? |

Do not lump `UNAVAILABLE` together with `DEADLINE_EXCEEDED`. `UNAVAILABLE` generally indicates the service or transport cannot serve the call; `DEADLINE_EXCEEDED` indicates the call's time budget ran out. Both can rise together during overload, yet each must be analyzed separately.

## 2. Distinguish server-returned statuses from transport errors

`UNAVAILABLE` can originate from two main paths:

1. **Server returns `UNAVAILABLE`:** a handler or exception mapper deliberately closes the RPC with `Status.UNAVAILABLE`, e.g., a dependency is temporarily down or the service is shedding traffic.
2. **Client/runtime generates `UNAVAILABLE`:** the client fails to establish or sustain the RPC due to connection refused, unreachable endpoint, connection reset, proxy/HTTP2 failure, or the server vanishing mid-call.

Catching status on the client:

~~~java
try {
    return orderStub.getOrder(request);
} catch (StatusRuntimeException error) {
    Status status = Status.fromThrowable(error);

    if (status.getCode() == Status.Code.UNAVAILABLE) {
        metrics.incrementUnavailable("GetOrder");
        log.warn("gRPC call unavailable: method={}, description={}",
                "GetOrder", status.getDescription());
    }

    throw error;
}
~~~

This is a client-side classification example. In production, avoid logging every exception at `ERROR` with full stack traces when error rates are high; that creates a log storm. Use counters, sampling, and aggregated window logs. Descriptions are not stable error codes; correlate client transport logs, server logs, and infrastructure telemetry.

If server logs show the handler received the request and deliberately returned `UNAVAILABLE`, investigate status mapping and dependencies. If there is no trace of the request on the server, prioritize checking DNS, endpoint discovery, networking, TLS, proxies, and listeners. Still, missing server logs are not absolute proof, since logs can drop or requests can be blocked before interceptors.

## 3. Determine the blast radius

Start by comparing these dimensions:

- **One method:** inspect that method's logic or dedicated dependency.
- **Every method on one service:** inspect the listener, service registration, instance health, and shared dependencies.
- **Multiple providers at once:** inspect networking, DNS, service mesh, nodes, load balancers, or shared infrastructure.
- **One client version:** inspect channel config, resolvers, credentials, retry policies, and client rollout.
- **One zone/region:** inspect endpoint health, routing, firewalls, certificates, and network paths in that zone.
- **A few instances:** inspect specific pods/nodes, readiness, resource pressure, and connection distribution.

Use error rates by method and endpoint rather than overall status totals alone. If one backend receives most traffic and fails more often, load balancing may be failing to eject bad endpoints or health signals may not reflect RPC readiness.

A quick isolation matrix:

| Observation | Priority direction |
| --- | --- |
| Only one method, one service | Handler, status mapping, or dedicated dependency |
| All methods on one instance | Instance, listener, resources, or deployment |
| All instances of one provider | Rollout, config, shared dependency, or service registration |
| Multiple providers via same gateway | Gateway, mesh, DNS, network, or certificates |
| Only one consumer | Client channel, credentials, resolver, or traffic pattern |
| Only one zone | Routing, endpoint health, network, and zonal capacity |

## 4. Inspect client channels and name resolution

gRPC Java `ManagedChannel` manages connections and selects subchannels via resolvers and load balancing policies. Checking channel state clarifies whether calls are connecting or failing repeatedly:

- `IDLE`: the channel has not needed a connection or returned to idle.
- `CONNECTING`: establishing a connection.
- `READY`: a connection is ready from the channel's perspective.
- `TRANSIENT_FAILURE`: connectivity is currently unusable; the runtime continues backoff/reconnect.
- `SHUTDOWN`: the channel is closed and cannot accept new calls.

Channel state does not replace service health checks. `READY` does not prove every method or dependency is healthy; `TRANSIENT_FAILURE` may affect only one subchannel on a multi-endpoint channel.

Client-side checklist:
- Does the target URI have the right scheme/authority and DNS name?
- Does the resolver return current endpoint addresses?
- Is the load balancing policy configured properly for the target?
- Is the channel being shut down early or recreated repeatedly?
- Is the client creating a new channel per request, causing connection churn?
- Do TLS authority, trust roots, and certificate SANs match the hostname?
- Have call credentials expired or failed to refresh?
- Is the deadline too short relative to connection time and actual load?

Never create a new `ManagedChannel` per RPC. Reuse channels across the application lifecycle and derive stubs with call options. Channel churn inflates handshakes, DNS lookups, and server pressure.

If using a DNS resolver, test resolution from the client's actual runtime/container. A DNS query from a laptop does not prove production pods resolve the same records. Inspect TTLs, caches, search domains, and endpoint updates after rollouts.

## 5. Inspect DNS, load balancer, and HTTP/2 path

`UNAVAILABLE` across multiple methods or clients usually calls for inspecting the network path:

1. Does DNS resolve the service name properly and return ready endpoints?
2. Do Kubernetes `Service`/`EndpointSlice` or the service registry list healthy endpoints?
3. Is the load balancer routing traffic to terminating or unready pods?
4. Do proxies/service mesh support HTTP/2 end-to-end with proper gRPC upstream settings?
5. Have firewalls, `NetworkPolicy`, security groups, or routing tables changed?
6. Are there abnormal connection resets, `GOAWAY`, `RST_STREAM`, or idle timeouts?
7. Did a gateway apply new connection/stream limits or rate limits?

Example Kubernetes commands to inspect services and endpoints:

~~~bash
kubectl get svc -n <namespace>
kubectl get endpointslices -n <namespace> -l kubernetes.io/service-name=<service>
kubectl get pods -n <namespace> -o wide
kubectl describe svc <service> -n <namespace>
~~~

Use `grpcurl` from an environment sharing the client's network path:

~~~bash
grpcurl -vv -plaintext \
  -import-path src/main/proto \
  -proto shop/order/v1/order_service.proto \
  -d '{"orderId":"order-123"}' \
  <grpc-host>:<grpc-port> \
  shop.order.v1.OrderService/GetOrder
~~~

This example uses plaintext and proto source files for illustration; in TLS environments, omit `-plaintext` and configure CA/client certificates per security policy. Never pass bearer tokens or secrets directly into shell history. If `grpcurl` fails to connect, record resolver/transport errors and compare from the consumer pod, a same-namespace pod, and another vantage point.

If a gateway sits between client and server, test a direct path to the service in an authorized environment as well. Comparing results isolates whether the fault lies in the gateway or provider. Never bypass security boundaries in production for a "quick test."

## 6. Inspect the Spring gRPC server and instance health

On the provider side, check:

- Are pods/containers running and ready?
- Did the Spring application context finish starting?
- Did the gRPC listener bind to the right port/address?
- Are service beans registered, or is the method returning `UNAVAILABLE` from application logic?
- Are there pod restarts, `OOMKilled` events, liveness failures, or continuous rollouts?
- Are CPU throttling, heap pressure, GC pauses, thread-pool/worker queues, or file descriptors climbing?
- Are connection counts, concurrent streams, or inbound message sizes exceeding limits?
- Does graceful shutdown drain traffic before pods terminate?

Sample diagnostic commands:

~~~bash
kubectl get pods -n <namespace> -l app=<provider>
kubectl describe pod <pod> -n <namespace>
kubectl logs <pod> -n <namespace> --since=15m
kubectl get events -n <namespace> --sort-by=.lastTimestamp
~~~

Correlate failure onset with deployments, config changes, secret/certificate rotations, and node events. If only new pods fail, compare image digests, environment variables, mounted secrets, service ports, and readiness behavior between old and new pods.

Readiness must reflect the gRPC server's ability to accept traffic. A green HTTP health endpoint does not necessarily prove the gRPC listener is bound or critical dependencies are ready. If using the gRPC Health Checking Protocol, inspect the service's health status and how load balancers/clients consume that signal.

## 7. Check server-side overload and dependencies

A server may return `UNAVAILABLE` when it can no longer accept or process work. Look for:

- Sustained high CPU or throttling.
- Heap near limit, long GC pauses, rising allocation rates.
- Full worker/executor queues, thread starvation, or exhausted connection pools.
- Database connection timeouts, pool exhaustion, or lock contention.
- Downstream HTTP services returning 5xx, timing out, or refusing connections.
- Disconnected message brokers, caches, or service discovery.
- Inbound messages/metadata exceeding limits or excessive concurrent streams.

Separate provider-emitted `UNAVAILABLE` from client-transport `UNAVAILABLE` by comparing per-method server metrics and logs. If the handler ran and an exception mapper returned `UNAVAILABLE`, trace the specific dependency/exception. If the server never saw the call, return to the network/endpoint path.

Never increase thread pools or connection pools blindly. Raising concurrency when a database is already overloaded lengthens queues and amplifies the outage. Identify the bottleneck first, then tune concurrency, pool sizes, or rate limits within actual resource bounds.

## 8. Control retry storms and keep operations safe

`UNAVAILABLE` often reflects a transient issue, yet retrying is not always safe. Retry policies must cap attempts, use exponential backoff with jitter, and obey the overall deadline budget. If all clients retry simultaneously, a recovering provider gets crushed under a surge of load.

Principles:
- Retry only methods/operations verified to be retry-safe or idempotent.
- Keep the exact same idempotency key across retries for the same business intent.
- Bound max attempts and total retry duration within the deadline.
- Use exponential backoff with jitter; never retry in an immediate tight loop.
- Cap concurrent calls and client-side queues.
- Avoid configuring retries at multiple layers simultaneously without accounting for total attempts.
- Never retry `PERMISSION_DENIED`, `INVALID_ARGUMENT`, or non-transient errors.
- For streaming RPCs, define resume cursors and duplicate handling before reconnecting.

Example service config policy bounding retries on an idempotent method:

~~~json
{
  "methodConfig": [{
    "name": [{
      "service": "shop.order.v1.OrderService",
      "method": "GetOrder"
    }],
    "retryPolicy": {
      "maxAttempts": 3,
      "initialBackoff": "0.2s",
      "maxBackoff": "2s",
      "backoffMultiplier": 2,
      "retryableStatusCodes": ["UNAVAILABLE"]
    }
  }]
}
~~~

This illustrates gRPC service config structure; how service config is supplied to `ManagedChannel` depends on the resolver and application client setup. Do not enable this policy for `CreateOrder` unless the server guarantees idempotency. Retry policies never replace deadlines, bulkheads, rate limits, or circuit breakers.

If the provider is overloaded, temporarily reduce retry attempts or disable retries on load-inducing methods; throttle ingress/concurrency and restore capacity before ramping traffic back up. Never use wait-for-ready or infinite retries to mask an unavailable service.

## 9. Mitigations by root cause

Choose mitigations backed by evidence:

| Confirmed cause | Priority mitigation | What to avoid |
| --- | --- | --- |
| New rollout failing on all new pods | Pause rollout or roll back to known-good version | Restarting the whole fleet before diagnosing |
| A few unhealthy pods | Remove pods from traffic, restore readiness, or replace pods | Putting unready pods back into the load balancer |
| Provider capacity shortage | Scale carefully, reduce ingress/concurrency, protect dependencies | Raising concurrency unboundedly |
| Broken DNS/service discovery | Restore records/registry and verify caches/TTLs | Mass-changing targets without verification |
| Gateway/proxy HTTP/2 failure | Roll back gateway config or fix upstream protocol/timeouts | Bypassing gateway/security controls in production |
| Certificate/TLS failure | Restore certificate chain, SANs, trust bundle, or rotation config | Disabling TLS verification |
| Dependency failure | Fail fast with proper status, trip circuit breaker, recover dependency | Hammering a dead dependency with retries |
| Retry storm | Reduce attempts, increase backoff/jitter, rate limit | Increasing retries to "compensate" for errors |
| Misconfigured client | Roll back config or ship controlled client fix | Creating a new channel per request |

If rolling back, verify schema compatibility, database migrations, and any data written by the newer version. If scaling out, verify dependencies have enough capacity for additional instances. Every mitigation needs an owner, timestamp, expected recovery signal, and rollback criteria.

## 10. Verify recovery and close the incident

After applying mitigations, do not stop at checking that pods are `Running`. Verify from actual consumer paths:

1. Request success rates recover by service/method.
2. `UNAVAILABLE` rate returns to baseline over a sufficient observation window.
3. `DEADLINE_EXCEEDED` and p95/p99 latency show no abnormal spikes.
4. Endpoint counts and readiness remain stable with no pod restarts or connection churn.
5. Client channels reconnect cleanly with no prolonged `TRANSIENT_FAILURE`.
6. Dependency pools/queues, CPU, memory, and GC return to operating thresholds.
7. Retry attempts per logical request return to normal levels.
8. Synthetic RPCs or canaries succeed from critical zones.
9. No duplicate side effects occurred from client retries during the incident.

Close the incident only once errors stay steady across an appropriate observation window and key consumers confirm recovery. Document start/end timestamps, blast radius, confirmed or hypothesized root cause, mitigations, version/config changes, and preventive follow-ups.

## 11. Evidence to preserve for post-incident review

Collect:
- Error rates and request rates by method/status/client version/zone.
- Redacted client-side descriptions, channel states, and transport errors.
- Server logs correlated by request ID/trace ID and exception mappings.
- Pod restarts, deployment events, readiness, resource metrics, and endpoint history.
- DNS resolution data, load balancer/proxy logs, and TLS certificate timelines.
- Dependency latency/error rates, pool utilization, and queue depths.
- Retry attempts, deadline distributions, and logical requests vs. physical attempts.

Never store tokens, authorization headers, private keys, personal payloads, or secrets in incident notes. If the root cause remains unconfirmed, state hypotheses and missing evidence clearly; never conclude "server down" solely from `UNAVAILABLE`.

## 12. Operational checklist

- [ ] Confirm `UNAVAILABLE` spike by rate, method, and scope.
- [ ] Distinguish server-returned statuses from client/transport failures.
- [ ] Compare across client version, provider version, pod, and zone.
- [ ] Inspect channel state, DNS resolver, and endpoint selection.
- [ ] Inspect load balancer, proxy, HTTP/2, firewall, and TLS.
- [ ] Inspect Spring gRPC listener, readiness, restarts, and service registration.
- [ ] Inspect CPU, memory, GC, queues, thread/connection pools, and dependencies.
- [ ] Bound retries via attempts, backoff, jitter, and deadline budgets.
- [ ] Protect non-idempotent operations with idempotency keys before retrying.
- [ ] Apply evidence-based mitigations with rollback criteria.
- [ ] Verify recovery of success rates, latency, retry rates, and dependency health.
- [ ] Save redacted evidence and document root cause/unknowns.

**Self-check**

**Q1.** Does `UNAVAILABLE` always mean the server process stopped?

*Answer:* No. The server can return `UNAVAILABLE` intentionally, and the client runtime can also generate it when connections, endpoints, proxies, or HTTP/2 transports become unusable.

**Q2.** Why must `UNAVAILABLE` be separated from `DEADLINE_EXCEEDED`?

*Answer:* `UNAVAILABLE` indicates serving or connectivity unavailability; `DEADLINE_EXCEEDED` means the call exceeded its allowed time budget. Both can spike together, yet each requires different diagnostics.

**Q3.** When is it safe to retry `UNAVAILABLE`?

*Answer:* When the operation is retry-safe or idempotent, deadline budget remains, retries are bounded, and backoff/jitter are applied. For write operations, preserve the idempotency key across attempts.

**Q4.** Why should you not increase retry attempts when a provider is overloaded?

*Answer:* Retries generate extra physical requests on top of the same logical traffic, overloading queues and dependencies further. Instead, shed ingress/concurrency, restore capacity, and curb retry storms.

**Q5.** When can an incident be closed?

*Answer:* When success rates and `UNAVAILABLE` return to baseline across a sufficient observation window, latency/retry/dependency health stabilize, and real consumer paths are verified.

An effective `UNAVAILABLE` runbook starts by determining whether the status came from the server or the transport, narrows scope by method, client, endpoint, and zone, restores endpoints/servers/dependencies based on evidence, curbs retries to prevent load amplification, and closes only after consumer paths and reliability metrics stabilize.
