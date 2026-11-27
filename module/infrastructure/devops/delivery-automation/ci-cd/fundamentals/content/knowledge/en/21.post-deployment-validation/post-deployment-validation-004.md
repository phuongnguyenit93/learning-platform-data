# Verifying Connectivity, Configuration, and Dependencies in the Target Environment

A deployment may succeed operationally yet the application still cannot serve users. Containers are running, the update command returned success, and the controller reported rollout completion, yet the application may fail to resolve DNS, fail to connect to the database, lack runtime configuration, use the wrong TLS certificate, or lack permission to call a dependent service.

Therefore, right after deployment you must verify inside the target environment that the application can start, read configuration, authenticate its identity, and communicate with required dependencies. **Post-deployment validation** is the set of post-deploy checks verifying actual state, not merely confirming that the pipeline sent a deploy command.

These checks must run from the application's actual network, identity, and runtime context. A `curl` command succeeding on a CI runner does not prove production pods can reach the same endpoint; the two environments may differ in DNS, routes, firewalls, proxies, trust stores, secrets, and service accounts.

## 1. Distinguishing Successful Deployment from a Ready Application

There are several distinct milestones in a release:

- **Deployment command succeeded:** the deployment tool accepted the request or finished the command.
- **Workload started:** the process or container started.
- **Readiness passed:** the instance qualifies to receive traffic under the application's criteria.
- **Dependency checks passed:** essential connections and services can be used.
- **Smoke test passed:** a few representative business flows work correctly.
- **Release verified:** the system meets observation conditions over the defined time window.

Do not collapse all these milestones into a single success status. For example, Kubernetes may create enough pods, yet the pods are not Ready because they cannot connect to the database. Or pods are Ready, yet the external payment API returns errors when executing a test transaction.

A deployment record should store results per check group, timestamps, environment, artifact digest, and verified configuration. That helps distinguish deploy failures, startup failures, connectivity failures, and business-logic failures.

## 2. Checking from the Right Target Environment

Checks must reflect the workload's actual conditions:

- Run from the same network segment, namespace, subnet, or runtime environment.
- Use the same DNS resolver and proxy configuration the application uses.
- Use the same service identity or workload identity.
- Read the same secret references and trust store provisioned to the workload.
- Call the environment's actual hostname, port, protocol, and endpoint.
- Respect NetworkPolicies, firewalls, security groups, service mesh, and egress rules.

If a smoke test runs from a runner outside the cluster, it may only verify external ingress. It cannot check the path from a pod to a database or broker. Combine external checks with internal checks from a pod or a diagnostic job sharing the same network policy and appropriate identity.

Do not grant broad production permissions to a diagnostic job just to test connectivity. If a separate job is needed, grant only the required read or health-endpoint call permissions, and restrict its namespace and runtime duration.

## 3. Checking DNS and Network Reachability

A dependency may be healthy while the application still cannot reach it due to wrong DNS, routing, or firewall rules.

### DNS

Verify that the configured hostname resolves to the expected address in the target environment. Common mistakes:

- A staging hostname accidentally used in production.
- Wrong in-cluster service name or namespace.
- Private DNS zone not linked to the VPC/VNet.
- Resolver cache holding stale addresses after an endpoint change.
- Search domains causing short hostnames to resolve differently than expected.

Example checks from an environment sharing the same DNS context:

```bash
getent hosts db.production.internal
nslookup payments-api.production.internal
```

These commands are illustrative; the runtime image needs the corresponding tools or an approved diagnostic image. Do not install ad-hoc tools into running production containers just to debug.

### TCP, Routing, and Ports

After DNS resolves, check TCP connectivity to the dependency port. A successful TCP connection only proves the network path and listener can complete a handshake; it does not prove TLS, authentication, or application protocols work.

```bash
nc -vz db.production.internal 5432
nc -vz broker.production.internal 9092
```

If it times out, inspect routes, firewalls, security groups, NetworkPolicies, egress proxies, and listener status. If connection is refused, the endpoint may be reachable but no process is listening on the port or the service is not ready yet.

Do not open firewalls broadly just to turn checks green. Identify the specific source identity/network and destination port, and open only the required flow.

## 4. Checking TLS, Certificates, and Protocols

A successful TCP connection can still fail during the TLS handshake. Common causes:

- Expired or not-yet-valid certificate.
- Hostname not matching Subject Alternative Name.
- Container missing a required CA certificate.
- Incompatible TLS version or cipher suite.
- Certificate chain missing an intermediate certificate.
- mTLS requiring a client certificate while the workload has none or uses the wrong one.
- Proxy or service mesh altering the connection path.

You can check the handshake and certificate from an appropriate environment:

```bash
openssl s_client \
  -connect payments-api.production.internal:443 \
  -servername payments-api.production.internal \
  -verify_return_error
```

SNI must match the service hostname. This command is a diagnostic tool; also verify the trust store, client certificate, and actual application configuration. Never disable certificate verification or fall back to unencrypted HTTP just to make a smoke test pass.

After TLS, verify the right protocol and endpoint. For example, an HTTPS health endpoint might return 200 while a business endpoint requires a different OAuth scope. Therefore, distinguish:

- Network connectivity.
- TLS and server identity verification.
- Client/service identity authentication.
- Authorization by resource and action.
- Application behavior at the target endpoint.

## 5. Verifying Runtime Configuration

Applications typically receive configuration from environment variables, mounted files, config services, command-line arguments, or secret managers. A deployment may run with missing or wrong configuration while the process still starts.

Configurations to verify:

- Environment name and region.
- Hostname, port, protocol, and base URL of dependencies.
- Database name/schema and connection pool settings.
- Timeouts, retries, connection limits, and circuit breakers.
- Feature flags or rollout mode.
- Queues/topics, buckets/containers, and namespaces.
- Log level, tracing endpoint, and metric exporter.
- Required values, data types, bounds, and cross-field relationships.

### Validating Configuration at Startup

Failing fast on required configuration catches discrepancies early. For example, a Java application using Spring Boot can validate properties:

```java
@Validated
@ConfigurationProperties(prefix = "payments")
public record PaymentsProperties(
    @NotBlank String baseUrl,
    @NotNull Duration connectTimeout,
    @NotNull Duration readTimeout
) {}
```

This is a conceptual example; enable configuration properties scanning and declare validation dependencies matching your project's Spring Boot version. Beyond checking presence, validate that URLs have valid schemes/hosts, timeouts are positive, and related fields are consistent.

Do not dump the entire configuration to logs for debugging. You can log config names, sources, versions, and validation status; mask or omit passwords, tokens, private keys, connection strings containing credentials, and personal data.

### Checking Configuration Source and Version

For traceability, store the revision or digest of the config bundle, manifest, Helm chart, and infrastructure definition. If configuration is fetched from a config service, record the version or snapshot ID. Do not record only the environment name, because configuration changes over time.

Secrets should only be referenced by name/version or secret manager identity. Never copy secret values into deployment records, test reports, or logs.

## 6. Checking Secret References and Runtime Identity

An application may start even with an invalid secret reference, only to fail on the first database or API call. Verify:

- Workload identity or service account is properly attached.
- Role/policy permits reading the exact secret reference.
- Secret exists in the right environment and version.
- Credentials are neither expired nor revoked.
- Certificates/private keys have valid formats and file permissions.
- Tokens have the right audience, issuer, and scope for the target service.
- Rotation processes do not leave instances holding stale credentials too long.

Do not print secrets to prove they were mounted. You can verify existence, version metadata, or execute a safe authenticated operation against the dependency using the real credential in memory. When checks fail, log error codes and sanitized secret reference IDs without writing values.

An external check job cannot fully verify a pod's runtime identity if the job uses a different identity. For workload identity, test from the workload itself or an equivalently configured diagnostic workload.

## 7. Checking Dependencies and Readiness Order

Applications may depend on databases, caches, message brokers, object storage, identity providers, internal APIs, and external services. Not every dependency must be ready for the process to start, but essential dependencies must work before the application accepts traffic for the corresponding features.

| Dependency | Appropriate check | What to verify |
|---|---|---|
| Database | Connect, authenticate, lightweight query | Right host/schema, required privileges, compatible migration |
| Cache | Connect and controlled read/write test | Endpoint, TLS, auth, and namespace |
| Message broker | Connect metadata or check topic/queue | Broker reachable, publish/consume permissions, and topic name |
| Object storage | Read metadata or operate on a dedicated test object | Bucket/container, region, role, and policy |
| Internal API | Health/contract endpoint | DNS, TLS, auth scope, and API version |
| External API | Check endpoint or safe request | Egress, proxy, TLS, credentials, and quota |
| Identity provider | Discovery/JWKS or token validation test | Issuer, audience, key rotation, and clock |

Do not use operations with side effects on real data to check dependencies. If a write test is needed, use a dedicated namespace, table, queue, or object name with explicit cleanup. Avoid creating real transactions, sending emails, or charging payments in smoke tests.

### Dependency Readiness

A dependent service may be starting up or under maintenance. The application needs timeouts, bounded retries, and appropriate degraded behavior. Do not retry indefinitely, which can hang rollouts or pile load onto a failing dependency.

Dependency checks should verify both connectivity and minimum operational permissions. A successful database connection where the user lacks permission to read the required schema is still a configuration error.

## 8. Distinguishing Startup, Liveness, and Readiness Probes

In Kubernetes, the three probe types serve different purposes:

- **Startup probe:** gives the application time to start up; until this probe succeeds, liveness and readiness are not executed.
- **Liveness probe:** determines whether the process needs to be restarted. Do not make liveness depend on every external service, because a transient database outage could cause all pods to restart repeatedly.
- **Readiness probe:** determines whether the instance should receive traffic yet. It can reflect dependencies essential for serving requests.

Example:

```yaml
startupProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 5
  failureThreshold: 30

livenessProbe:
  httpGet:
    path: /actuator/health/liveness
    port: 8080
  periodSeconds: 10
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /actuator/health/readiness
    port: 8080
  periodSeconds: 5
  failureThreshold: 3
```

These endpoints are Spring Boot Actuator examples; configure exposure and health groups appropriately. Do not assume all endpoints are enabled by default. Do not expose admin endpoints or dependency details to the Internet.

Readiness should reflect the ability to accept traffic, while avoiding dependence on optional services. If an analytics system is temporarily down while the orders API still works, you may not want to mark all pods NotReady. Liveness should focus on process health; restarts cannot fix network or dependency credential errors.

## 9. Post-Deployment Smoke Tests

A smoke test is a brief suite verifying critical flows work after deploy. It does not replace full integration or end-to-end tests.

A good smoke test:

- Uses representative yet safe endpoints and data.
- Verifies response codes, schemas, and key business conditions.
- Verifies the application can read essential dependencies.
- Has explicit timeouts and bounded retries.
- Produces no irreversible side effects.
- Runs with an identity and network path close to real users or workloads.
- Stores results alongside deployment ID, artifact digest, and config revision.

Example:

```bash
curl --fail --silent --show-error \
  --connect-timeout 3 \
  --max-time 10 \
  https://orders.production.example.com/health/ready

curl --fail --silent --show-error \
  --connect-timeout 3 \
  --max-time 10 \
  https://orders.production.example.com/api/version
```

Endpoints and hostnames are placeholders. Health endpoints should return appropriate statuses, and version endpoints should provide non-sensitive information such as release ID or short commit. Do not return environment variables, secrets, internal host lists, or configuration details on public endpoints.

For business flows, you can use a test account and isolated data, such as creating and canceling a test order in a sandbox. If safe cleanup is not possible, use read-only endpoints or purpose-built synthetic transactions.

## 10. Checking Environment Configuration and Drift

Development, staging, and production can differ in hostnames, certificates, regions, identities, quotas, and network policies. Therefore, verify the target's actual configuration rather than merely confirming a config file exists.

Common mistakes:

- Production accidentally using staging URLs or credentials.
- ConfigMap/secret references pointing to a different namespace.
- Chart values or overlays mismatching the environment.
- Feature flags enabled outside the planned cohort.
- Resource limits set too low, causing restarts under load.
- Proxies or CA bundles differing from the build environment.
- NetworkPolicies blocking a new dependency.

Compare desired configuration against observed configuration after deployment. If manual changes exist, records must capture the drift and its source. Do not overwrite drift automatically without knowing whether the change was intentional; per policy, block rollout, alert, or require review.

## 11. Checking Version Compatibility and Migrations

A successful database connection does not prove the application can use the schema properly. After deployment, verify:

- Required migrations ran and are at the right version.
- The database user has the minimum required privileges.
- The new application is compatible with the current schema.
- Consumers/producers read and write compatible message formats.
- API dependencies are on supported versions.
- Cache keys or serialization formats do not conflict between old and new versions.

With rolling deployments, old and new versions may run concurrently. Database migrations and message contracts should support the coexistence period. Use expand-and-contract to add structures first, deploy compatible code, migrate data, and only drop old structures after the rollback window closes.

Never run destructive migrations automatically inside a smoke test step. Migrations need their own job, permissions, records, and recovery plan.

## 12. Monitoring After Smoke Tests Pass

Smoke tests only check a few points at one moment. Bugs can surface when real traffic rises, caches are cold, background workers run, or batch jobs start.

During the post-deploy observation window, monitor:

- Error rate and request success rate.
- p50/p95/p99 latency of critical endpoints.
- CPU, memory, thread pools, connection pools, and restart counts.
- Database connections, query latency, and migration errors.
- Broker lag, consumer errors, and retry/dead-letter counts.
- External API timeouts, rate limits, and authentication failures.
- Business metrics such as order creation rate, payment success, or event processing.

Compare against pre-deploy baselines and defined thresholds. A single metric may not suffice; combine technical and business signals. If errors exceed thresholds during a canary, stop increasing traffic or trigger rollback per policy.

## 13. Automating Validation in the Pipeline

A post-deployment validation sequence may include:

1. Wait for the rollout controller to report converged state.
2. Verify deployment ID, release ID, and artifact digest on the workload.
3. Check DNS, network, TLS, and runtime identity from the target environment.
4. Verify required configuration and config bundle version.
5. Check essential dependencies via safe health/diagnostic operations.
6. Run read-only smoke tests or synthetic transactions.
7. Monitor metrics over an observation window.
8. Record results, reports, and deployment status.
9. If mandatory checks fail, halt rollout or recover per policy.

Conceptual workflow example:

```yaml
jobs:
  deploy_staging:
    steps:
      - name: Deploy approved digest
        run: ./scripts/deploy-by-digest.sh

      - name: Wait for rollout
        run: ./scripts/wait-for-rollout.sh

      - name: Validate target connectivity and configuration
        run: ./scripts/validate-runtime.sh

      - name: Run smoke tests
        run: ./scripts/smoke-test.sh

      - name: Publish deployment evidence
        if: always()
        run: ./scripts/publish-deployment-evidence.sh
```

These scripts are placeholders and must be implemented for your platform and environment. The publish-evidence step can run after failure to preserve logs, but must never turn a failed deploy into success. Summary jobs must distinguish pass, fail, skipped, and cancelled.

Validation should use an overall timeout and bounded retries with backoff. If a dependency is not ready within the allowed time, record the exact dependency, endpoint tested, error type, and attempt count; avoid infinite retries.

## 14. Handling Validation Failures

Not every failure requires a full rollback. Classify by scope and impact:

| Finding | Reference action |
|---|---|
| Wrong DNS/route/TLS for an essential dependency | Halt rollout; check network/config and roll back if the new version caused the error |
| Missing required configuration | Do not accept traffic; fix config or restore previous revision |
| Invalid secret reference | Keep workload out of traffic, fix identity/secret mapping, and re-verify |
| Optional dependency unavailable | Run in degraded mode if designed; alert and monitor |
| Readiness not met | Do not shift traffic; keep old instances if rollout strategy supports it |
| Business smoke test fails | Halt traffic expansion, investigate, and roll back/roll forward by severity |
| Poor metrics after canary | Halt rollout or shift traffic back to stable version |

Before rolling back, check database, message, and configuration compatibility. If the error stems from network or secret mapping outside the artifact, rollback may not fix the root cause. You may need to restore configuration or policies first. The deployment record should link the failure to the remediation action and subsequent verification result.

## 15. Protecting Information in Health Checks and Diagnostics

Health endpoints and logs can accidentally leak internal information. Return only the level of status needed by the caller:

- Public endpoints can return overall status.
- Dependency details should be protected by appropriate network controls or authorization.
- Never return connection strings, tokens, certificate private keys, environment variables, or personal data.
- Never log credentials, Authorization headers, or sensitive query strings.
- Use correlation IDs and standardized dependency names for investigation.
- Rate-limit diagnostic checks to avoid overloading dependencies.

If deep debugging is required, use access-controlled logs with retention limits; never expose actuator/env/config endpoints publicly in production.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Checking only that the deploy command exits 0 | Application may not be ready | Check rollout, readiness, and smoke tests |
| Testing connectivity from CI runner instead of target | Results do not reflect app DNS/network/identity | Run from runtime context or equivalent diagnostic job |
| Checking only TCP port | Misses TLS, auth, permissions, and protocol | Verify the entire handshake and required operations |
| Printing full config for debugging | May expose secrets | Log version, key names, and masked status |
| Making liveness depend on every external service | Dependency failure causes mass restarts | Separate liveness and readiness |
| Smoke test creates real data without cleanup | Causes side effects or pollutes production data | Use synthetic data and controlled cleanup |
| Infinite retries when dependency fails | Rollout hangs and load increases | Overall timeout, bounded retries, and backoff |
| Checking only once right after deploy | Misses failures when traffic increases | Use an observation window and monitor metrics |
| Rolling back while ignoring migrations/config | Old version incompatible or bug persists | Check schema and restore config alongside release context |

## 17. Target Environment Verification Checklist

- [ ] Tested from the right network, namespace, DNS, and workload identity.
- [ ] DNS resolves expected hostnames and routes to intended endpoints.
- [ ] TCP ports, firewalls, NetworkPolicies, and egress rules allow required flows.
- [ ] TLS certificates, hostnames, CA chains, SNI, and mTLS are valid.
- [ ] Runtime config has all required values, right environment, and right revision.
- [ ] Secret references exist, identity has least-privilege access, and credentials are valid.
- [ ] Databases, caches, brokers, object storage, and essential APIs are usable.
- [ ] Startup, liveness, and readiness probes have distinct purposes and appropriate configs.
- [ ] Rollout is complete and observed artifact digest matches desired digest.
- [ ] Smoke tests verify critical flows without unintended side effects.
- [ ] Metrics/logs/traces are monitored during the observation window.
- [ ] Deployment record stores config revision, dependency results, evidence, and final status.
- [ ] Timeouts, bounded retries, failure actions, and recovery plans are defined.
- [ ] Health endpoints and diagnostics do not expose secrets or internal details.

Verifying connectivity, configuration, and dependencies in the target environment confirms that the application can actually operate after deploy. When validation runs in the right runtime context, verifies from DNS/TLS through identity and dependencies, and confirms via smoke tests plus telemetry, the team gains reliable evidence to continue the rollout or halt and recover in time.
