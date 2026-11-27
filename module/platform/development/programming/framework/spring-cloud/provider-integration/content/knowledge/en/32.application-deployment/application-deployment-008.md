# Canary Deployments, Connectivity Checks, and Rolling Back Integration Changes

A cloud integration change can break an application even when the source code compiles and unit tests pass. The new version might target the wrong region, lack IAM/RBAC permissions, point to a different queue or bucket, fail to resolve a private endpoint, or change message handling in a way that duplicates data. Therefore, deployment requires a trial rollout in a controlled environment, verification using the workload's actual identity and network path, post-traffic monitoring, and a prepared rollback plan.

In the `SPRING_CLOUD_PROVIDER_INTEGRATION` module, this lesson guides you through rolling out Spring Boot changes integrated with managed services on AWS, Azure, and Google Cloud. The focus is on verifying real behavior, catching failures early, limiting blast radius, and restoring a stable version when needed.

## Objectives

After this lesson, you will be able to:

- Plan a trial deployment for changes to endpoints, identities, storage, messaging, or cloud configuration.
- Verify connectivity, authentication, permissions, and business behavior from the actual runtime environment.
- Choose rolling, canary, or blue-green strategies aligned with the risk level.
- Monitor health checks, logs, metrics, and traces to decide whether to continue or halt a rollout.
- Roll back applications and configuration safely, including changes involving schemas or messages.
- Distinguish software rollback from restoring cloud data and resources.

## 1. Why Trial Deployments Are Necessary

Unit tests usually run against mocks or faked dependencies. They verify application logic, not whether a workload inside a VPC, VNet, or VPC network can reach managed services. Integration tests may run in a development environment, yet still differ from production in DNS, routing, firewalls, workload identity, quotas, region, and resource policies.

An integration change can affect multiple layers:

| Change Type | Deployment Risk | Evidence to Verify |
|---|---|---|
| Endpoint or region | Calls wrong resource, wrong DNS, TLS mismatch | Hostname, region, resolved DNS IP, certificate, and target resource |
| IAM, RBAC, or workload identity | Application starts, but requests are denied | Runtime identity and minimal permitted operations |
| Storage | Reads work, but writes, encryption, or object access fail | Upload, metadata/content read-back, permissions, and encryption |
| Messaging | Publish/consume fails, messages duplicate, or go to dead-letter queue | Send, receive, ack, retry, ordering, and DLQ |
| Database | Wrong connection, incompatible migration, pool exhaustion | Connectivity, verification query, migration, and latency |
| Secret or configuration | Missing secret, wrong version, or sensitive leak | Secret fetch via runtime identity and version check |
| Spring Cloud/SDK library | Changes in retry, timeout, serialization, or endpoint behavior | Compatibility testing and real request metrics |

Trial deployments confirm both infrastructure configuration and application behavior before exposing changes to broad traffic. The test environment should mirror production in topology, DNS, identity, and service versions, while using isolated data and resources.

## 2. Preparing Before Rollout

### 2.1. Recording the Current Baseline

Before deploying, record:

- Currently running application version and image digest or artifact version.
- Relevant configuration version, secret references, and feature flags.
- Region, project/subscription/account, resource names, and endpoints used by the application.
- Runtime identity, roles, and critical permissions.
- Replica count, traffic rate, error rate, latency, queue backlog, and dead-letter count.
- Relevant database schema or message contract versions.
- Existing active alerts to distinguish pre-existing issues from new regressions.

Use an immutable, tested artifact. Avoid rebuilding an image under the same tag during rollout because that tag can resolve to different contents across nodes. Record the image digest so the exact stable version can be redeployed.

### 2.2. Checking Configuration Compatibility

Separate configuration per environment using environment variables, ConfigMaps, secret managers, or platform configuration mechanisms. Values to check typically include:

- Region and resource names: queue, topic, bucket, container, database, or subscription.
- Endpoint URL and private/public mode.
- Timeouts, retries, connection pools, and concurrency limits.
- Workload identity, managed identity, or service account.
- Active secret references and versions.
- Feature flags governing the new integration path.

You can use Spring Boot externalized configuration to supply per-environment values:

```yaml
# application.yml
app:
  cloud:
    region: ${APP_CLOUD_REGION}
    orders-queue: ${ORDERS_QUEUE_NAME}
    connect-timeout: 2s
    read-timeout: 5s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Never place access keys, client secrets, or secret contents directly in committed configuration files. Expose only the needed actuator endpoints and restrict access per operational policy.

### 2.3. Preparing Resources and Permissions Before the Application

If the new version needs a new queue, topic, bucket, secret, or permissions, create and verify them before shifting traffic. Favor backward-compatible changes:

1. Create new resources or expand schemas.
2. Grant least-privilege permissions to the new version's identity.
3. Verify DNS, routes, firewalls, and private endpoints.
4. Deploy the application able to work with both old and new structures if needed.
5. Shift traffic or enable feature flags.
6. Delete old resources only after a stabilization window and once confirmed no version still uses them.

Never delete old queues, subscriptions, buckets, secret versions, or database columns in the same rollout if the older application might still need them for rollback.

## 3. Verifying from the Actual Runtime Environment

A check from a laptop or CI runner is no substitute for testing from the Pod, VM, container, or serverless instance actually running the application. The two environments may use different DNS resolvers, routes, firewalls, proxies, certificate stores, and identities.

Test in the following order:

### 3.1. DNS and Network Path

Verify the hostname resolves properly inside the runtime environment:

```bash
getent hosts <service-hostname>
```

If the container lacks `getent`, use an available DNS tool such as `nslookup` or `dig`. When using private endpoints, cross-check the returned IP address against the expected network and endpoint.

Next, verify TCP and TLS on the service's actual port:

```bash
nc -vz <service-hostname> 443

openssl s_client \
  -connect <service-hostname>:443 \
  -servername <service-hostname>
```

Port 443 is only an example for HTTPS APIs. Databases, caches, or other protocols may use different ports. Keep the hostname in the TLS handshake to test SNI and certificates. Never switch to calling by IP or disable certificate verification to work around errors.

### 3.2. Identity and Permissions

A successful TCP connection does not prove the identity has permission to operate. Verify the application uses the exact workload identity:

- AWS: verify the IAM role or workload identity mechanism attached to the workload; verify permissions on the exact resource ARN and region.
- Azure: verify the selected managed identity or service principal; verify role assignments at the exact subscription, resource group, or resource scope.
- Google Cloud: verify the service account or Workload Identity Federation; verify IAM bindings on the exact project and resource.

Run checks using the runtime identity itself. Avoid testing with an engineer's personal credentials in place of the workload, as doing so can mask deployment authorization bugs.

### 3.3. Testing the Minimal Business Operation

After DNS, TCP, TLS, and identity pass, perform a small, observable, and cleanable operation. Choose a test matching the integration:

| Integration | Suggested Check | What to Confirm |
|---|---|---|
| Object storage | Write a test object under a dedicated prefix, read it back, then delete it | Right bucket/container, write/read/delete permissions, encryption, and metadata |
| Queue | Send a message with a test correlation ID, receive, and ack | Right queue, serialization, publish/consume permissions, and ack |
| Pub/sub | Publish a test event to a test topic, confirm subscriber receives it | Topic, subscription, permissions, and delivery |
| Database | Open a connection and execute a read-only check query | Endpoint, TLS, identity, schema, and connection pool |
| Secret manager | Read a test secret or permitted version | Read permission, version, format, and refresh mechanism |
| Internal API | Call a test endpoint or read-only query | DNS, TLS, token, timeout, and response contract |

Never send fake data into a production queue if consumers might process it like real orders or transactions. Use isolated test resources, recognizable correlation IDs, and clear cleanup steps. If testing in production is unavoidable, pick a read-only check or a dedicated test path designed to produce zero business side effects.

### 3.4. Running Smoke Tests with the Same Deployment Configuration

Smoke tests should run in a temporary job or Pod using the same image, network policy, and workload identity as the application. The check should report clear results per dependency, such as DNS passed, TLS passed, authentication passed, and read-only check passed.

For example, a probe interface can be implemented per provider:

```java
// CloudIntegrationProbe.java
public interface CloudIntegrationProbe {
    ProbeResult verify();
}
```

```java
// ProbeResult.java
public record ProbeResult(
        boolean reachable,
        boolean authorized,
        String dependency
) {
    public boolean successful() {
        return reachable && authorized;
    }
}
```

The smoke test job invokes the matching adapter and exits with a non-zero exit code if verification fails. Never print tokens, secrets, connection strings, or sensitive payloads to output. For each provider, the adapter should invoke a lightweight, least-privilege API with no unnecessary side effects.

## 4. Spring Boot Health Checks and Readiness

Spring Boot Actuator provides health endpoints for platforms to inspect application state. When probes are enabled, Spring Boot exposes separate health groups for liveness and readiness:

- **Liveness** answers whether the application is healthy enough to keep running or needs a restart.
- **Readiness** answers whether the instance is ready to accept traffic.

Example configuration:

```yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info
```

Endpoints commonly used in Kubernetes are:

- `/actuator/health/liveness`
- `/actuator/health/readiness`

Liveness should not depend directly on external cloud services. If a queue or database temporarily drops connectivity, continuously restarting every Pod can worsen the outage. Readiness can include mandatory dependencies if the application genuinely cannot serve requests when that dependency fails; checks must use short timeouts and avoid generating heavy load.

A custom health indicator can describe integration status:

```java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("cloudIntegration")
class CloudIntegrationHealthIndicator implements HealthIndicator {

    private final CloudIntegrationProbe probe;

    CloudIntegrationHealthIndicator(CloudIntegrationProbe probe) {
        this.probe = probe;
    }

    @Override
    public Health health() {
        ProbeResult result = probe.verify();

        if (result.successful()) {
            return Health.up()
                    .withDetail("dependency", result.dependency())
                    .build();
        }

        return Health.down()
                .withDetail("dependency", result.dependency())
                .withDetail("reason", "integration check failed")
                .build();
    }
}
```

A health indicator should be added to the readiness group only when that dependency truly determines serving capability. Health group configuration can specify which components participate:

```yaml
management:
  endpoint:
    health:
      group:
        readiness:
          include: readinessState,cloudIntegration
```

In production, consider short-lived caching or background checks so every kubelet health poll does not trigger a new call to a managed service. Never expose exception details, internal hostnames, or sensitive resource names on public endpoints.

## 5. Choosing a Deployment Strategy

No single strategy fits every change. Choose based on risk level, traffic-splitting capability, startup time, and data compatibility.

| Strategy | How It Works | Advantages | Considerations |
|---|---|---|---|
| Rolling update | Replaces instances in batches | Easy to adopt, reduces downtime | Old and new versions run concurrently; requires config and message compatibility |
| Canary | Shifts a small percentage of traffic to the new version | Catches bugs with limited blast radius | Needs routing and solid metrics for comparison |
| Blue-green | Stands up a parallel environment then switches traffic | Fast cutover and clear switch-back path | Resource-intensive; must handle sessions, queue consumers, and shared data |
| Feature flag | Deploys code but enables features by cohort | Decouples code release from activation timing | Requires flag lifecycle management and stale code cleanup |

### 5.1. Rolling Update

A rolling update replaces instances one batch at a time while others keep serving. On Kubernetes, a baseline configuration limits how many Pods can be unavailable during updates:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      containers:
        - name: app
          image: registry.example/order-service@sha256:<image-digest>
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health
              port: 8080
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
```

This is an illustrative configuration; tune replica counts, probe timings, and resources per application. `startupProbe` gives the application time to boot before `livenessProbe` evaluates it prematurely. `readinessProbe` prevents unready Pods from receiving traffic.

A rolling update does not automatically create percentage-based canary routing. To cap traffic per version, you need an ingress controller, service mesh, or deployment platform supporting traffic splitting.

### 5.2. Canary

Canary deploys the new version to a small slice of requests or users. For instance, route 5% of traffic to the new version, observe across a window covering normal business cycles, then advance to 25%, 50%, and 100% if metrics stay healthy.

Do not monitor HTTP 5xx alone. For managed integrations, also watch:

- Error rate per dependency and operation type.
- Timeouts, retries, and throttled requests.
- Message publish/consume failures, backlog depth, and dead-letter counts.
- Storage operation failures and completion times.
- Connection pool utilization, thread pools, and memory.
- p95/p99 latency for requests calling cloud services.

Compare the canary cohort against the stable version over the same time window. If the new cohort exhibits unusual error spikes, stop increasing traffic and shift back to the previous version.

### 5.3. Blue-Green

Blue-green maintains two equivalent environments. Blue serves active traffic; green runs the new version and is verified ahead of cutover. Once smoke tests, health checks, and metrics pass, the router switches traffic to green.

Keep blue warm during an observation window so traffic can switch back quickly. However, blue and green often share the same database or queue. If the new version writes data in a schema or message format the old version cannot read, switching traffic back will not guarantee a clean rollback. Data compatibility must be designed before deployment.

## 6. Post-Deployment Monitoring

Once Pods or instances become Ready, continue observing through a stabilization window. The health endpoint is only one signal; an application can return HTTP 200 on health while publishing to the wrong topic or failing on real payloads.

### 6.1. Three Observability Signals

- **Metrics:** request success rates, latency, retries, throttling, queue lag, dead-letter counts, connection counts, and per-dependency error rates.
- **Logs:** record operation, resource alias, outcome, error category, and correlation ID; strip credentials, tokens, and sensitive payloads.
- **Traces:** follow a request from the application API through SDK/clients to managed services. Propagate trace context or correlation IDs across messages where supported.

Tag metrics with application version, environment, provider, region, and dependency to compare before and after rollout. Avoid high-cardinality user IDs or resource IDs as metric labels.

### 6.2. Defining Decision Thresholds

Establish continue, pause, and rollback criteria upfront. For example:

| Signal | Continue When | Halt Rollout When |
|---|---|---|
| Readiness | New replicas stay steadily Ready | Pods repeatedly become NotReady or restart |
| HTTP error rate | No significant rise over baseline | 5xx exceeds agreed threshold |
| Dependency errors | No new permission or connection errors | Unusual spike in timeouts, 401/403, or throttling |
| Messaging | Backlog and DLQ within limits | Messages go unacked or DLQ grows rapidly |
| Latency | p95/p99 close to baseline | Latency breaches SLO or climbs steadily |
| Resources | CPU, memory, and connection pools stable | Pool exhaustion, OOM, or saturation |

Exact thresholds must be grounded in your system's SLOs and baselines. Never apply a single universal number across all applications. Also distinguish outages in a shared dependency from regressions introduced solely by the new version.

### 6.3. Observing Rollouts on Kubernetes

```bash
kubectl rollout status deployment/order-service
kubectl get pods -l app=order-service
kubectl describe deployment order-service
kubectl logs deployment/order-service --since=10m
```

`rollout status` reports only the Deployment controller's rollout state. It does not prove business integrations work properly. Combine it with smoke tests and dependency metrics before declaring a release complete.

## 7. Rollback Procedure

Rollback restores traffic and the application to a known-good stable version. Determine upfront who is authorized to halt a rollout, which artifact represents the prior version, which configurations must be restored, and which resources must be retained.

General workflow:

1. **Stop expanding the rollout.** Halt canary percentage increases or pause the pipeline.
2. **Drain or shift traffic back.** Route traffic to the stable version via router, deployment controller, or blue-green switch.
3. **Redeploy the old artifact.** Use the previously recorded image digest or artifact version.
4. **Restore compatible configuration.** Verify endpoints, region, secret references, feature flags, and timeouts for the older version.
5. **Preserve shared resources.** Never delete queues, topics, buckets, subscriptions, schemas, or secret versions until confirming no consumer/producer relies on them.
6. **Re-verify integration.** Run health checks, smoke tests, verify identity, and monitor metrics after traffic returns.
7. **Capture root cause and evidence.** Record release ID, correlation IDs, timestamps, sanitized logs, and relevant metrics.

On Kubernetes, you can run:

```bash
kubectl rollout history deployment/order-service
kubectl rollout undo deployment/order-service
kubectl rollout status deployment/order-service
```

`rollout undo` reverts the Deployment revision using Kubernetes history. It does not revert ConfigMaps, Secrets, IAM policies, DNS records, database schemas, or cloud resources modified outside the Deployment. Those components require their own restoration procedures.

### 7.1. Rollback by Change Type

| Changed Component | How to Handle on Rollback | Risks to Avoid |
|---|---|---|
| Application image | Redeploy prior stable digest | Reusing a mutable tag that was overwritten |
| Feature flag | Disable flag or revert to prior value | Flags out of sync across instances |
| Endpoint/region | Restore verified configuration | Old version incompatible with new endpoint |
| IAM/RBAC | Restore minimal permissions needed by old version | Revoking permissions while old instances still run |
| Secret reference | Point back to an active, permitted version | Deleting or disabling old version too soon |
| Routes, DNS, firewalls | Revert changes per network plan | Breaking connectivity for other workloads sharing the network |
| Database schema | Keep schema backward-compatible; use forward migrations if needed | Running destructive migrations trying to revert |
| Queue/topic/subscription | Retain resources and check backlog/consumers | Deleting messages or subscriptions holding unprocessed data |

## 8. Data and Message Migrations Need Backward Compatibility

One common reason rollbacks fail is that the new version wrote data the older version cannot read.

For databases, apply the expand-and-contract workflow:

1. **Expand:** add new columns, tables, or indexes without breaking the older application.
2. **Deploy compatible code:** the new version reads both old and new structures; dual-write in controlled phases if needed.
3. **Migrate:** backfill data in batches that are safely resumable and rerunnable.
4. **Verify:** cross-check row counts, integrity, and read/write behavior.
5. **Contract:** drop old columns or structures only after the old version is retired and the rollback window closes.

For messages, add new fields as optional or with sensible defaults. Consumers should ignore unknown fields when the contract allows; producers should not drop legacy fields while older consumers remain active. When changing serialization, verify compatibility across concurrently running producer and consumer versions.

Retries can cause a message to be processed multiple times. Handlers must be idempotent or enforce deduplication via message ID/business key. Rollback does not automatically undo emails, payments, webhooks, or executed side effects. Such operations require controlled compensating actions and separate auditing.

## 9. Applying Across AWS, Azure, and Google Cloud

Rollout and rollback principles are universal, while tooling, identities, and observability signals vary by platform.

| Platform | Common Deployment Mechanisms | What to Verify |
|---|---|---|
| AWS | Rolling on EKS/ECS; blue-green or traffic shifting via CodeDeploy/Lambda depending on workload | IAM role, VPC endpoints, region, CloudWatch metrics, queue backlog, and target health |
| Azure | Rolling/canary on AKS; deployment slots and swap on App Service | Managed identity, Private Endpoint, role assignments, Application Insights, and Service Bus metrics |
| Google Cloud | Rolling/canary on GKE; traffic splitting across Cloud Run revisions | Service account/Workload Identity, PSC or Private Google Access, Cloud Monitoring, and Pub/Sub metrics |

On AWS, with SQS or SNS, verify exact queue/topic ARNs, policies, and dead-letter configurations. With S3, verify bucket, prefix, encryption, and object permissions. When deploying Lambda or ECS with traffic shifting, retain the restorable version and configuration throughout the observation window.

On Azure, with Service Bus or Storage, verify namespace/account, entity or container, managed identity, and role assignment scope. With App Service deployment slots, verify both slot-specific settings and connection configurations before swapping.

On Google Cloud, with Pub/Sub or Cloud Storage, verify project, topic/subscription or bucket, service account, and IAM bindings. With Cloud Run revisions, traffic splitting supports canary rollouts; with GKE, use an ingress or progressive delivery controller to manage traffic splits.

Regardless of tooling, inspect both version-bound configuration and shared configuration outside the workload. Reverting an application revision does not automatically undo changes to IAM, DNS, secret managers, or data resources.

## 10. Example Release Workflow for a Queue Integration Change

Suppose a new version of `order-service` migrates from an old queue configuration to a new queue and uses workload identity to send messages.

**Preparation phase**

- Provision the new queue in staging and production.
- Grant send permissions to the application's identity on the new queue; retain old permissions during transition.
- Configure DNS, endpoints, and routes if the queue uses private connectivity.
- Verify message schemas and confirm current consumers can parse the new format.
- Record the image digest, old queue name, new queue name, and feature flag.

**Trial deployment phase**

- Deploy the new version to staging using the same identity and network mechanisms as production.
- Run a smoke test sending a message with a correlation ID to a test queue.
- Confirm the consumer receives, processes, and acks the message; verify retries and DLQ.
- Monitor latency, publish/consume errors, and backlog.
- Deploy one canary replica or a small traffic slice in production once staging passes.

**Expansion phase**

- Increase traffic step by step after each observation window.
- Confirm new messages land in the right queue and consumers process steadily.
- Once all producers and consumers use the new queue, retain the old queue through the defined rollback window.
- After the rollback window closes and no messages remain, revoke permissions and delete the old resource via the infrastructure change workflow.

**If rollback is required**

- Disable the feature flag or shift traffic back to the previous version.
- Restore the old queue configuration and redeploy the stable artifact.
- Keep the new queue to inspect its backlog and drain already-published messages; never delete the queue to hide errors.
- Reconcile messages by correlation ID to prevent duplicate processing.
- Revoke permissions and clean up resources only after confirming no workloads still rely on them.

## 11. Pre- and Post-Deployment Checklist

### Pre-Deployment

- [ ] Artifact has an immutable version or digest and has passed appropriate tests.
- [ ] Current stable version, configuration, secret references, and feature flags are recorded.
- [ ] Endpoints, region, project/subscription, and resource names are verified.
- [ ] Workload identity holds least-privilege permissions on target resources.
- [ ] DNS, routes, firewalls, TLS, and private endpoints are verified from the runtime.
- [ ] Database schemas and messages are compatible with currently running older versions.
- [ ] Safe smoke tests, isolated test data, and cleanup procedures are ready.
- [ ] Metrics, logs, traces, and rollout halt thresholds are configured.
- [ ] Rollback commands or procedures are verified in an appropriate environment.

### Post-Deployment

- [ ] Readiness is stable with no abnormal restarts.
- [ ] Smoke tests confirm real operations against managed services.
- [ ] No unexpected identity, DNS, TLS, or endpoint errors occur.
- [ ] Error rate, latency, retries, throttling, and backlog stay within limits.
- [ ] Messages are neither lost nor unexpectedly duplicated.
- [ ] Active version, configuration, and resources in use are recorded.
- [ ] Legacy resources, permissions, and schemas are cleaned up only after the rollback window expires.

## Conclusion

Deploying integration changes requires verifying from the actual runtime environment, using the right identity, and executing the smallest observable business operation. Rolling, canary, and blue-green strategies contain risk while shifting traffic; health checks, metrics, logs, and traces provide the evidence to proceed or halt. A solid rollback plan must restore both artifacts and configuration while keeping shared data, messages, and resources in a compatible state. Across AWS, Azure, and Google Cloud, prepare and verify these steps before expanding a rollout to the entire workload.
