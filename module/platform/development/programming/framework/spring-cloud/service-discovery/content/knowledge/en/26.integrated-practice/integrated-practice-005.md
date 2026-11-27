# Failing a Eureka Peer and Verifying Client Discovery Continues

Eureka can run multiple server peers to increase registry availability. When one peer stops working, the remaining peers can continue serving clients as long as they remain reachable and already hold the necessary registry data. However, peer replication, client registry fetch, and the Spring Cloud LoadBalancer cache are separate mechanisms with their own latencies. Therefore, you cannot conclude failover succeeded merely because the surviving peer's Eureka Dashboard is up or because a single request happened to return HTTP 200.

This practice sets up a two-peer Eureka cluster, registers a provider and a consumer, intentionally stops one peer in an isolated environment, and then verifies that the client continues discovering and calling the service through the remaining peer. Finally, you restore the failed peer and check that the registry converges again.

This content belongs to module SPRING_CLOUD_SERVICE_DISCOVERY: finding instances by service name with DiscoveryClient, maintaining registration/heartbeats, reading the registry, and selecting instances via Spring Cloud LoadBalancer. The focus is on verifying both the control plane (registry/replication) and the data plane (requests to the provider).

## 1. Objectives and PASS Criteria

After this practice, you must be able to demonstrate:

- Two Eureka Server peers can communicate and exchange registry data.
- The provider registers into the cluster and the instance appears across peers.
- The consumer is configured with multiple Eureka URLs and fetches the registry successfully.
- When stopping one peer, the remaining peer still responds to the registry API.
- The consumer continues returning the instance via DiscoveryClient and business requests continue succeeding.
- The provider can continue renewing or registering new instances through the healthy peer.
- When the failed peer is restored, both sides of the registry converge again.
- Tests distinguish between data in the server registry, the Eureka Client local cache, and the Spring Cloud LoadBalancer cache.

PASS Criteria:

1. The remaining peer remains reachable over HTTP(S) and serves the registry API.
2. The active registry contains the provider instance with the exact service ID and instance ID.
3. The consumer continues seeing the instance via DiscoveryClient within the configured timeout.
4. Requests via service ID/LoadBalancer continue succeeding and reaching the right provider.
5. No prolonged discovery errors exceeding acceptable thresholds; brief errors during failover are recorded and measured.
6. The restored peer receives registry data again after replication/sync time.
7. No duplicate registrations or stale instances beyond the designed convergence window.

## 2. Two-Peer Lab Architecture

Use two Eureka Servers:

- Peer 1: hostname eureka-peer-1, port 8761.
- Peer 2: hostname eureka-peer-2, port 8761.
- Provider: service ID payment-service, unique instance ID.
- Consumer: order-service, looking up payment-service.

~~~mermaid
flowchart TB
    P[Payment provider] -->|Register / renew| E1[Eureka peer 1]
    P -->|Register / renew| E2[Eureka peer 2]
    E1 <-->|Peer replication| E2
    C[Order consumer] -->|Fetch registry| E1
    C -->|Failover / fetch| E2
    C -->|Load-balanced request| P
    T[Test runner] -->|Stop / restore peer 1| E1
    T -->|Check registry API| E2
~~~

This is a logical diagram. Which URL the client sends a request to first and when it switches to the next URL depends on the Eureka Client implementation, configuration, and connection state. Peer replication is asynchronous; the two servers may temporarily hold different registry views.

Do not use a single Eureka Server and create two DNS aliases pointing to the same process. The two peers must be two independent processes/servers with separate network identities and lifecycles.

## 3. Configuring Eureka Peer 1 and Peer 2

Each peer must have its own hostname and declare the URL of the other peer. In the lab environment, both servers can use the same port 8761 because they run in separate containers/hosts.

Each server needs the spring-cloud-starter-netflix-eureka-server dependency and Eureka Server enabled:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(EurekaServerApplication.class, args);
    }
}
~~~

Provider and consumer need spring-cloud-starter-netflix-eureka-client. Manage dependencies using a Spring Cloud BOM compatible with your project's Spring Boot version; do not mix release trains arbitrarily.

### 3.1. Configuring Peer 1

~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  instance:
    hostname: eureka-peer-1
    prefer-ip-address: false
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-peer-2:8761/eureka/
~~~

### 3.2. Configuring Peer 2

~~~yaml
server:
  port: 8761

spring:
  application:
    name: eureka-server

eureka:
  instance:
    hostname: eureka-peer-2
    prefer-ip-address: false
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-peer-1:8761/eureka/
~~~

Peer 1 and Peer 2 register with and fetch the registry from each other. Setting register-with-eureka: true and fetch-registry: true enables a server peer to exchange data with the other peer. If a peer is configured strictly as a standalone server with fetch/register disabled, it will not form a peer topology like this lab.

Both hostnames must resolve from the opposing peer's container/host. If running Docker Compose, place services on the same network to use service names. If running Kubernetes, use stable DNS per peer, such as StatefulSet ordinals via a headless Service or a separate Service per peer.

### 3.3. Configuring Provider and Consumer Clients

The provider needs to register and fetch the registry; the consumer only needs to fetch if it does not need to register itself:

~~~yaml
eureka:
  client:
    register-with-eureka: true
    fetch-registry: true
    registry-fetch-interval-seconds: 5
    service-url:
      defaultZone: http://eureka-peer-1:8761/eureka/,http://eureka-peer-2:8761/eureka/
  instance:
    prefer-ip-address: true
    instance-id: "payment-service:${HOSTNAME}:${server.port}"
~~~

For a lookup-only consumer:

~~~yaml
spring:
  application:
    name: order-service

eureka:
  client:
    register-with-eureka: false
    fetch-registry: true
    registry-fetch-interval-seconds: 5
    service-url:
      defaultZone: http://eureka-peer-1:8761/eureka/,http://eureka-peer-2:8761/eureka/
~~~

A fetch interval of 5 seconds is only used to observe faster in the lab. In production, choose the interval based on client count, registry load, and convergence SLA. Do not reduce the interval across the board without measuring request rate and Eureka cluster capacity.

In YAML, the key defaultZone has an uppercase Z per Eureka service URL configuration. If using environment variables or profiles, verify actual property binding in the application context.

### 3.4. Instance Addresses Must Be Reachable

Peer replication only resolves registry data. The consumer must also be able to call the provider address registered by the instance. In a Docker network, the provider should advertise a DNS alias/hostname reachable by the consumer; in Kubernetes, choose Service DNS or Pod endpoints according to your load balancing model.

Do not advertise localhost, 127.0.0.1, or 0.0.0.0 to clients on other containers/hosts. If the registry has a record but requests time out, verify the advertised host and port before concluding peer failover failed.

## 4. Starting the Lab and Checking the Baseline

Start peer 1 and peer 2 in the same network. You can use Docker Compose with two containers from the same Eureka Server image using different profiles/configs. Each peer must expose client port 8761 on the internal network.

After starting, check peer endpoints:

~~~bash
curl -fsS http://eureka-peer-1:8761/actuator/health
curl -fsS http://eureka-peer-2:8761/actuator/health
~~~

If Actuator health is not exposed yet, you can check the Eureka API:

~~~bash
curl -i -H "Accept: application/json" \
  http://eureka-peer-1:8761/eureka/apps

curl -i -H "Accept: application/json" \
  http://eureka-peer-2:8761/eureka/apps
~~~

A successful HTTP response only proves the endpoint answers; it does not prove peer replication or client failover. Next, start the provider and wait for the registration to appear.

### 4.1. Verifying Peer Replication

After the provider registers, read the service from both peers:

~~~bash
curl -fsS -H "Accept: application/json" \
  http://eureka-peer-1:8761/eureka/apps/PAYMENT-SERVICE

curl -fsS -H "Accept: application/json" \
  http://eureka-peer-2:8761/eureka/apps/PAYMENT-SERVICE
~~~

Compare:

- Application name.
- Instance ID.
- Advertised hostname/IP.
- Port.
- Status, typically UP when the provider is healthy.
- Metadata/version if configured.

Peer replication does not necessarily complete immediately when one server acknowledges registration. Use polling with a timeout to wait until both peers see the exact instance. If only the peer receiving the registration request has the record, check peer URLs, DNS, firewall, and replication logs.

## 5. Verifying the Consumer Before Fault Injection

The consumer should use DiscoveryClient to observe its local registry view:

~~~java
import java.util.List;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class PaymentDiscoveryProbe {

    private final DiscoveryClient discoveryClient;

    public PaymentDiscoveryProbe(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findPaymentInstances() {
        return discoveryClient.getInstances("payment-service");
    }
}
~~~

Verify the consumer sees the expected instance:

~~~java
await()
    .atMost(Duration.ofSeconds(40))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() -> {
        assertThat(discoveryClient.getInstances("payment-service"))
            .anySatisfy(instance -> {
                assertThat(instance.getInstanceId()).isEqualTo(expectedInstanceId);
                assertThat(instance.getHost()).isNotBlank();
                assertThat(instance.getPort()).isPositive();
            });
    });
~~~

Put the read operation inside the lambda so each poll fetches the latest state. Do not fetch the list beforehand and assert on an old snapshot. The timeout must accommodate the Eureka fetch interval, server sync, and startup.

If using Spring Cloud LoadBalancer, create a client annotated with @LoadBalanced and send requests by service ID. Example with RestTemplate:

~~~java
@Bean
@LoadBalanced
RestTemplate paymentRestTemplate(RestTemplateBuilder builder) {
    return builder.build();
}
~~~

Request:

~~~java
String body = paymentRestTemplate.getForObject(
    "http://payment-service/test/identity",
    String.class
);
~~~

Record the response and instance ID/version to know which provider handled the request.

## 6. Failing Exactly One Eureka Peer

Only perform fault injection in a lab or isolated test environment. Never stop a production peer without a change plan, an owner, and rollback criteria.

You can stop peer 1 with Docker:

~~~bash
docker stop eureka-peer-1
~~~

Or in Kubernetes, delete only peer 1's Pod so the StatefulSet/Deployment manages its lifecycle:

~~~bash
kubectl delete pod eureka-peer-0 -n platform
~~~

Pod names are illustrative; substitute the Pod corresponding to peer 1 in your lab. Do not scale the entire Eureka cluster to 0 and do not delete both peers at once.

After stopping peer 1, verify:

- Peer 1 no longer responds to health/API checks.
- Peer 2 still responds to /actuator/health or /eureka/apps.
- Both provider and consumer still have peer 2 in their defaultZone list.
- Client logs record connection errors to peer 1 and proceed to try the remaining endpoint per the client's retry/failover behavior.
- No DNS/load balancer rule accidentally points both peer hostnames to the same instance.

Check peer 2:

~~~bash
curl -fsS http://eureka-peer-2:8761/actuator/health
curl -fsS -H "Accept: application/json" \
  http://eureka-peer-2:8761/eureka/apps/PAYMENT-SERVICE
~~~

If peer 2 lacks the service record, the client may keep running off a stale local cache, but that does not prove the surviving registry holds the necessary data. Fix peer replication/baseline before concluding HA works.

## 7. Verifying Client Discovery Continues

After peer 1 stops working, verify across three separate layers.

### 7.1. Surviving Registry Still Holds Data

Peer 2 must return the service record with the exact instance ID. To prove the Eureka registration path still works while peer 1 is down, start a second provider with a new instance ID and verify peer 2 receives the record.

Example new instance:

~~~text
serviceId: payment-service
instanceId: payment-service:payment-02:8080
status: UP
~~~

Do not reuse the first provider's instance ID because two processes could overwrite the registration or make test results ambiguous.

### 7.2. Consumer DiscoveryClient Still Returns the Instance

Wait for the consumer local registry cache to see the instance:

~~~java
await()
    .alias("consumer continues to discover payment-service")
    .atMost(Duration.ofSeconds(40))
    .pollInterval(Duration.ofMillis(250))
    .untilAsserted(() -> {
        List<ServiceInstance> instances =
            consumerDiscoveryClient.getInstances("payment-service");

        assertThat(instances).isNotEmpty();
        assertThat(instances).anySatisfy(instance ->
            assertThat(instance.getInstanceId()).isEqualTo(expectedInstanceId)
        );
    });
~~~

This condition proves the consumer discovery view contains the instance. It does not yet prove data-plane requests succeed; the next step is required.

### 7.3. Requests via LoadBalancer Continue Succeeding

Send multiple requests via the service ID and record results:

~~~java
for (int i = 0; i < 100; i++) {
    String response = paymentRestTemplate.getForObject(
        "http://payment-service/test/identity",
        String.class
    );
    assertThat(response).contains("payment-service");
}
~~~

In real tests, the response should include the instance ID and version. Collect counts of successful requests, timeouts, connection refused errors, and 5xx errors. Some requests might briefly fail during the failover window while the client tries peer URLs or refreshes the registry; evaluate against predefined timeouts/SLOs rather than relying on a single request.

If the consumer can call the provider while unable to query the registry during peer failure, the consumer may be relying on its local registry cache. That still helps availability for existing requests, but does not prove it can see new instances registered after the peer failed. Therefore, test both new provider registration and consumer discovery refresh.

## 8. Distinguishing Peer Failover, Registry Cache, and Data-Plane Availability

Three distinct situations:

| Situation | What It Proves | What It Does Not Prove |
|---|---|---|
| Peer 2 API still responds | One registry node is still alive. | Consumer switched to peer 2 or has the latest data. |
| Consumer DiscoveryClient still returns instance | Local registry view still holds service data. | Surviving registry accepts new registrations or provider endpoint is still reachable. |
| Request via LoadBalancer succeeds | Consumer chose an endpoint and reached the provider. | Peer replication has converged or cached data is not stale. |
| Peer 2 accepts a new provider while peer 1 is down | Registration path still works through the surviving peer. | Peer 1 has synced after recovery. |
| Peer 1 and Peer 2 hold identical records after recovery | Registry has converged at check time. | No replication bugs remain under any load/network condition. |

Do not collapse assertions into a single check if your goal is to isolate failover causes. Testing each layer separately pinpoints whether an error lies in peer replication, client URL failover, client cache, or the network endpoint.

## 9. Understanding Cache Behavior and Convergence Time

Eureka Client normally maintains a local registry cache and periodically fetches the registry. Spring Cloud LoadBalancer can separately cache the ServiceInstance list. When a peer goes down:

- The consumer can keep using its local registry cache while one registry URL is unreachable.
- The client may need to try the remaining peer URL before a fetch succeeds.
- The registry fetch interval affects when the consumer sees new registrations.
- The LoadBalancer cache may keep holding the list previously retrieved from DiscoveryClient.
- If all peers are unreachable, the client may continue using old data but cannot guarantee receiving new registrations.

In the lab, you can set a short registry-fetch-interval-seconds for faster observation. In production, measure p95/p99 time from peer failure to the next successful fetch via the surviving peer and from new registration to consumer visibility.

Do not disable self-preservation just to speed up eviction tests. Eureka self-preservation is designed to prevent mass instance removal when heartbeats drop abnormally; it does not replace peer failover. During a network partition, stale records may persist longer than expected. Understand these semantics when setting assertions for stopped instances.

## 10. Restoring the Failed Peer

Restart peer 1:

Docker:

~~~bash
docker start eureka-peer-1
~~~

Kubernetes StatefulSet:

~~~bash
kubectl get pods -n platform -w
kubectl describe pod eureka-peer-0 -n platform
~~~

Wait for peer 1 to become ready and verify the API:

~~~bash
curl -fsS http://eureka-peer-1:8761/actuator/health
curl -fsS -H "Accept: application/json" \
  http://eureka-peer-1:8761/eureka/apps/PAYMENT-SERVICE
~~~

Then wait for peer 1 to receive registrations back from peer 2. Compare instance ID, host, port, and status on both peers. Data may take time to sync; do not assert that both responses match identically the exact instant the peer opens its port.

If peer 1 starts up but does not receive registry updates, check:

- Can peer 1 resolve and connect to peer 2?
- Do both peers have the correct service URLs configured without accidentally pointing to themselves?
- Do security groups/firewalls allow peer-to-peer traffic?
- Are clocks, TLS certificates, and authentication valid?
- Do peer replication logs show Connection refused, timeout, 401/403, or TLS errors?
- Are there conflicting instance IDs/service names?

## 11. Automating Assertions with Awaitility

Instead of using Thread.sleep, wait for registry and consumer conditions to converge.

Example helper waiting for an instance:

~~~java
static void awaitInstance(
        DiscoveryClient discoveryClient,
        String serviceId,
        String instanceId) {

    await()
        .alias("instance " + instanceId + " appears in " + serviceId)
        .atMost(Duration.ofSeconds(40))
        .pollInterval(Duration.ofMillis(250))
        .untilAsserted(() -> {
            assertThat(discoveryClient.getInstances(serviceId))
                .anySatisfy(instance ->
                    assertThat(instance.getInstanceId()).isEqualTo(instanceId)
                );
        });
}
~~~

To wait for a peer API to contain a record, you can use RestClient/RestTemplate or WebTestClient to call /eureka/apps/{APP} and parse JSON. Place the API call inside the lambda so every poll executes a fresh read.

For the peer-down state, do not wait for "peer 1 responds" inside the same condition as "peer 2 is active." Assert that peer 1 is unreachable within a short timeout, assert peer 2 is reachable, and only then wait on consumer discovery and requests. This prevents tests from hanging on the failed endpoint.

## 12. Additional Fault Injection

After the single-peer stop scenario, you can extend the lab with controlled faults:

| Scenario | How to Inject Fault in Lab | What to Observe |
|---|---|---|
| Peer 1 process stops | Stop container or delete the exact Pod. | Client switches to peer 2, cache keeps serving. |
| Peer 1 port blocked | Block TCP from provider/consumer to peer 1. | Difference between process down and network partition. |
| Peer 1 DNS failure | Temporarily alter DNS/alias in test network. | UnknownHost, retries, and URL failover. |
| Peer 1 slow | Throttle network latency in test environment. | Request timeout, retry/backoff, and peer switchover time. |
| New provider registers while peer 1 is down | Start second provider with a different instance ID. | Peer 2 accepts registration and consumer fetches it. |
| Peer 1 recovers | Restart peer 1. | Replication catch-up and registry convergence. |
| Both peers down simultaneously | Stop both in a private lab. | How long client serves from old cache; new registrations cannot persist. |

Do not perform fault injection in production just to complete a lesson. Network partition scenarios can cause split views or stale registrations that are hard to recover from without operational procedures.

## 13. Observation Matrix and PASS/FAIL Criteria

| Check | PASS | FAIL |
|---|---|---|
| Peer 2 health/API | Responds normally after peer 1 goes down. | Peer 2 unreachable or API errors. |
| Provider record | Peer 2 holds exact service ID/instance ID. | Record missing or wrong host/port. |
| Consumer registry view | DiscoveryClient still returns valid instances. | Empty list persists beyond timeout. |
| Load-balanced request | Requests continue succeeding within SLO. | Timeouts/5xx exceed set threshold. |
| New registration | New provider registers through surviving peer. | Cannot create new record despite healthy peer 2. |
| Peer recovery | Peer 1 returns and receives registry state. | Peer 1 fails to sync or holds stale data long-term. |
| Cache convergence | Consumer sees new record and new status within target time. | Client keeps using stale registry past SLA. |
| Resource cleanup | Lab stops cleanly with no leftover test instances. | Registrations/test processes remain and pollute next run. |

Save timestamps for each milestone: peer stopped, peer 2 confirmed healthy, provider renewed/registered, consumer fetch succeeded, first request after failover, and peer 1 recovery. From these milestones you can calculate failover and convergence times rather than merely recording "test pass."

## 14. Troubleshooting

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Peer 2 lacks record after peer 1 goes down | Peer replication not working or provider registered only with unreachable peer. | Check peer URLs, DNS, network, and replication logs before fault injection. |
| Peer 2 has record but consumer does not see it | Consumer fetch cache not refreshed or only peer 1 configured. | Check defaultZone, fetch interval, client logs, and LoadBalancer cache. |
| Consumer sees instance but request times out | Advertised host/port unreachable. | Check instance metadata and call URI directly from consumer network. |
| Client logs repeated connection errors to peer 1 | Client still retrying failed URL on retry schedule. | Verify peer 2 URL is configured, DNS, and timeouts; measure failover time. |
| Peer 1 starts but fails to converge | Wrong peer URL, peer replication blocked, or config mismatch. | Check peer-to-peer connectivity, hostname, TLS/auth, and server logs. |
| Stale record persists | Lease/self-preservation/eviction not yet converged. | Distinguish graceful deregistration from crash; do not disable self-preservation arbitrarily. |
| New provider fails to register while one peer is down | Client did not fail over URL, surviving peer unreachable, or auth/TLS error. | Check register logs, registry URL list, ACLs, and certificates. |
| Flaky tests | Fixed sleeps used, duplicate service IDs, or timeout shorter than fetch interval. | Use Awaitility, unique IDs, and configuration-aligned timeouts. |

## 15. Cleaning Up the Lab

After finishing:

- Restore the stopped peer and confirm the cluster is healthy.
- Stop test providers/consumers via lifecycle so clients deregister.
- Remove test containers/networks or namespaces.
- Verify no test instance IDs remain in Eureka.
- Collect logs and metrics before deleting if analysis is needed.
- Do not leave ports, credentials, or test registries exposed outside the lab environment.

If running on Kubernetes, use a dedicated namespace for the lab and delete the namespace after confirming required data has been saved.

## 16. Conclusion

One failed Eureka peer does not necessarily halt all service discovery, provided the surviving peer is reachable, holds the registry data, and providers/consumers are configured to use it. However, peer replication, client fetch caches, and LoadBalancer caches converge asynchronously. Clients can continue serving from local cache for a period, but cannot receive new registrations if every peer becomes unreachable.

To prove HA, verify each layer independently: surviving peer, registry record, provider registration/renewal, consumer DiscoveryClient, requests via LoadBalancer, and peer recovery. Fail exactly one peer in an isolated environment, measure failover duration using timestamps/Awaitility, and retain self-preservation along with default safeguards unless there is an explicit testing reason.

## References

- Spring Cloud Netflix — Eureka Server and Client: https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html
- Netflix Eureka — Peer Awareness and Replication: https://github.com/Netflix/eureka/wiki
- Spring Cloud Commons — DiscoveryClient: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Awaitility — Usage: https://github.com/awaitility/awaitility/wiki/Usage
