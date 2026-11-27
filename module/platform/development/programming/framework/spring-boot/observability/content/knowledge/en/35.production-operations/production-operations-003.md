# Managing Exporter Secrets

In production, Spring Boot typically sends traces, metrics, or logs to an OpenTelemetry Collector or an observability backend. Exporters may need a bearer token, API key, credentials, client certificate, or private key to connect. These values are operational secrets: if leaked, an attacker could inject forged telemetry, read telemetry data, exhaust quota, or abuse a service's permissions to reach other systems.

Managing exporter secrets is part of observability design. Applications must obtain credentials from a controlled source, grant only the permissions required by the telemetry flow, protect transport connections, support rotation, and avoid leaking secrets into logs, traces, metrics, or source repositories. These principles apply across Micrometer Observation, Micrometer Tracing, Micrometer registries, and OpenTelemetry exporters in Spring Boot.

## 1. Identify Which Secrets Exporters Use

Before configuring anything, list every telemetry connection and its corresponding credentials. Not every exporter needs a secret. For example, Prometheus often scrapes an internal metrics endpoint, which may be protected at the network or reverse-proxy layer. An OTLP exporter sending data to a Collector or backend may require a token or mTLS.

| Data Flow | Possible Secret Needed | Purpose |
| --- | --- | --- |
| Spring Boot → OTLP Collector (traces) | Bearer token, API key, or client certificate/private key | Authenticates the application when sending traces |
| Spring Boot → OTLP Collector (metrics) | Dedicated token or API key | Scopes metrics ingest permissions per service or environment |
| Collector → observability backend | Backend credential, token, or private key | Authenticates the Collector when forwarding telemetry |
| Exporter using HTTP Basic | Username and password | Authenticates against endpoints supporting Basic Authentication |
| mTLS connection | Client certificate and private key | Mutual authentication between client and server |
| Standard TLS connection | CA trust material if using an internal CA | Verifies server identity; CA certificates are typically not secrets, while private keys are |

Endpoint URLs and service names are normally configuration, not secrets. However, never embed tokens or passwords in a URL query string or URL user-info because URLs can appear in logs, exceptions, dashboards, or configuration history. Clearly distinguish server certificates/public CA certificates from private keys: public certificates may need broader distribution, whereas private keys must be guarded as secrets.

Document where each secret is used, who owns it, its issuing source, permissions, expiration date, and rotation procedure. If applications only send telemetry to an internal Collector, backend credentials for the Collector should normally stay on the Collector. Applications then only need permission to send data to the Collector under the network and authentication policies between those two components.

## 2. Design the Secret Provisioning Flow

A secret management flow should have clearly separated components:

```text
Secret Manager / Vault / Kubernetes Secret
                 |
          workload identity
          or mount mechanism
                 |
                 v
        Spring Boot application
                 |
        OTLP over TLS / mTLS
                 |
                 v
          OTLP Collector
                 |
       dedicated backend credential
                 |
                 v
       Observability backend
```

Secrets are created and stored in a secret management system. Workloads receive the appropriate secret at runtime via identity, volume mounts, or platform-supported integration mechanisms. Spring Boot reads the configuration at startup, and the exporter uses that credential to transmit telemetry. The Collector can hold the backend-side credential so backend secrets do not have to be distributed to every application.

Prefer the following order when supported by your platform:

1. **Workload identity or short-lived credentials:** the application proves its identity via a service account, OIDC, or equivalent mechanism to obtain short-lived tokens. This reduces the need to distribute static API keys.
2. **Centralized secret manager:** store credentials in Vault or a cloud secret manager, restricting read access by workload and environment.
3. **Orchestrator-mounted secrets:** such as Kubernetes Secrets or a CSI Secret Store, with RBAC and encryption at rest configured properly.
4. **Runtime-injected environment variables:** usable when the platform lacks better mechanisms, provided process inspection, dumps, and diagnostic output are controlled.

Never store secrets directly in `application.yml`, `application-prod.yml`, committed Helm values, Dockerfiles, image layers, `.env` files pushed to Git, or build arguments. Never pass tokens on the command line where they risk appearing in process lists, shell history, or pipeline logs.

## 3. Configure Spring Boot to Read External Secrets

Spring Boot supports externalized configuration. You can use placeholders to inject values from the environment or a platform-provided property source into exporter configuration. The example below illustrates OTLP traces and metrics with two independent credentials:

```yaml
management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT}
      headers:
        Authorization: ${OTLP_TRACES_AUTHORIZATION}
    metrics:
      export:
        url: ${OTLP_METRICS_ENDPOINT}
        headers:
          Authorization: ${OTLP_METRICS_AUTHORIZATION}
```

These properties apply to the corresponding Spring Boot and Micrometer OTLP configuration. Declare only the tracing or metrics sections the application actually uses; verify dependencies, Spring Boot version, and active exporters to ensure the properties bind. Header names and authentication schemes depend on the receiving telemetry system. If the backend expects `X-API-Key` or another header, configure the agreed-upon protocol. For bearer authentication, `OTLP_TRACES_AUTHORIZATION` or `OTLP_METRICS_AUTHORIZATION` must include both the `Bearer` prefix and the token in the format the backend expects; do not store only the bare token unless the exporter adds the prefix itself.

In the example, `OTLP_TRACES_AUTHORIZATION` and `OTLP_METRICS_AUTHORIZATION` must be supplied at runtime. Do not define empty default values for mandatory production credentials. When a secret is missing, the application should fail fast or stay unready rather than silently sending unauthenticated telemetry and breaking production observability.

### Using environment variables

The platform can inject `OTLP_TRACES_ENDPOINT`, `OTLP_TRACES_AUTHORIZATION`, `OTLP_METRICS_ENDPOINT`, and `OTLP_METRICS_AUTHORIZATION` into the container. Endpoints are routine configuration; token-bearing variables must come from a secret store and be masked in deployment logs.

Environment variables are convenient, but they can surface in certain process inspections, crash dumps, diagnostic bundles, or admin interfaces. Inject them only into the containers that need them, restrict who has exec/inspect permissions, and avoid printing the entire environment in logs. For workloads with many secrets or strict controls, consider mounting secrets as files.

### Using config trees with file-mounted secrets

Spring Boot supports `configtree:` to load files in a directory as properties. For example, the platform mounts secrets under `/run/secrets/` with matching filenames:

```text
/run/secrets/
├── OTLP_TRACES_AUTHORIZATION
└── OTLP_METRICS_AUTHORIZATION
```

Declare the import and placeholders in the application configuration:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"

management:
  otlp:
    tracing:
      endpoint: ${OTLP_TRACES_ENDPOINT}
      headers:
        Authorization: ${OTLP_TRACES_AUTHORIZATION}
    metrics:
      export:
        url: ${OTLP_METRICS_ENDPOINT}
        headers:
          Authorization: ${OTLP_METRICS_AUTHORIZATION}
```

Files in a config tree supply property values keyed by filename. Mount the volume read-only if the platform supports it, and restrict file permissions and directory access. Do not bake secret contents into the image. If using `optional:configtree:` for local environments, ensure the production profile still requires the secrets and performs appropriate startup checks.

`configtree:` is only how Spring Boot reads configuration; it does not create a secret store, encrypt volumes, or control who can read files. Those responsibilities belong to the secret manager and deployment platform.

## 4. Limit Credential Permissions and Scope

Exporter credentials should have the minimum permissions needed to send telemetry to the target tenant, project, or endpoint. If the backend supports it, create separate tokens per service, environment, and signal. A production `checkout` token should never be shared with experimental apps or unrelated services.

Principles to apply:

- Grant only ingest/write permissions to exporters if the application does not need to read or administer telemetry data.
- Separate credentials across production, staging, and development; never use production secrets on developer machines or in CI tests.
- Separate trace and metric tokens when the backend supports per-signal permissions; this makes revocation and incident investigation more precise.
- Restrict secret read access by service account, namespace, workload identity, or secret manager policy.
- Restrict who can create, read, update, and revoke secrets. Permission to deploy an application does not implicitly require permission to read secret values.
- Set expiration on tokens and certificates; prefer short-lived or revocable credentials.
- Track who reads or modifies secrets through platform audit logs.

Kubernetes Secrets are not automatically secure just because their values are Base64-encoded. Base64 is an encoding format, not security encryption. Enable encryption at rest for Secret data in etcd according to cluster configuration, restrict RBAC, avoid broad `get/list/watch` permissions, and control node access as well as backups. When using an external secrets operator or CSI driver, audit both controller permissions and pod mount permissions.

If multiple applications send telemetry through a shared Collector, consider authenticating each workload on the app-to-collector leg and using a separate credential on the collector-to-backend leg. Placing a broadly scoped backend token inside every application expands the blast radius if a single pod is compromised.

## 5. Protect the Exporter Transport Path

Secrets can be exposed if sent over unprotected connections. Use HTTPS/TLS for OTLP over HTTP or configure TLS appropriate for the active transport. Never disable hostname verification or certificate chain validation in production as a workaround for temporary certificate errors.

With mTLS, the application holds a client private key and client certificate; the Collector or backend verifies the certificate against a trust policy. The private key must be mounted or provisioned from a secret store with restricted read permissions. Certificates need expiration dates, renewal procedures, and the ability to roll out new certificates before old ones expire. CA certificates used to verify servers generally do not need secrecy, but must be distributed from a trusted source.

Additional network-layer controls:

- Allow applications to connect only to the required collector hostname, port, and endpoint.
- Do not expose OTLP receivers to the Internet without a clear need and appropriate protections.
- Use NetworkPolicies, firewalls, or security groups to restrict telemetry senders.
- Separate internal and external endpoints; do not share credentials across different trust boundaries.
- Verify DNS, proxies, and certificate chains during deployment to avoid sending data to spoofed endpoints.

If using a Collector as an intermediary, secure both the Collector's receivers and exporters. Moving credentials from applications to the Collector only helps if the Collector itself is hardened, least-privileged, and backed by proper secret management.

## 6. Rotate Secrets Without Interrupting Telemetry

Rotation must be planned before a token or certificate expires. A sound procedure supports an overlap window where both old and new credentials are valid so applications can switch safely.

Typical token rotation workflow:

1. **Create a new credential:** generate a new token with the same required scope, an expiration date, and a clear owner. If supported by the backend, configure an overlap window with the old token.
2. **Update the secret store:** write the new value into the secret manager or Kubernetes Secret. Preserve the audit trail and secret version, and never copy tokens into tickets or chat.
3. **Roll out to workloads:** update the mount or environment on the target deployment. For Spring Boot reading config at startup, run a rolling restart or a verified refresh mechanism.
4. **Verify export:** confirm applications are ready, exporters have no authentication errors, the Collector receives data, and the backend displays fresh telemetry.
5. **Revoke the old credential:** revoke only after all affected workloads have moved to the new credential and the overlap period has ended.
6. **Record the outcome:** log the rotation timestamp, secret version, updated workloads, verification result, and revocation time; never record the secret value.

Do not assume that updating a secret file or environment variable automatically updates a running exporter. Environment variables are set at process creation; Spring Boot configuration and HTTP clients/exporters may be read or initialized once. Use hot reload only when the secret provider integration, refresh mechanism, and exporter all support live credential updates. If unverified, a rolling restart is the clearer and safer approach.

For certificates, track expiration dates and deploy new certificates before current ones expire. If the private key changes, update the certificate/key pair together and verify the trust chain. Do not wait until handshakes fail before starting renewal.

### Example transition sequence

```text
Token A is active
        |
Create Token B; A and B are both valid
        |
Update secret store to B
        |
Rolling restart pods
        |
Verify export succeeds with B
        |
Revoke Token A
```

If verification fails, you can revert configuration to the previous secret version during the overlap window, investigate the root cause, and retry. Once the old credential has been revoked, rolling back is not just reverting a config file; a new valid credential must be issued under an emergency procedure.

## 7. Troubleshooting Authentication and Export Issues

When an exporter fails to deliver data, classify the error before rotating secrets. DNS errors, TLS errors, timeouts, wrong endpoints, or an overloaded collector can look like authentication failures from a dashboard perspective.

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| HTTP 401 | Token missing, expired, wrong, or not sent | Check secret version, header name, expiration, and property binding; do not print the token value |
| HTTP 403 | Token valid but lacks permissions or targets wrong tenant/project | Check scope, policy, and destination endpoint |
| TLS handshake failure | Expired certificate, wrong hostname, missing CA, or mismatched private key | Check expiration, SANs, trust chain, and certificate/key pair |
| Connection refused or timeout | Collector not listening, network policy, DNS, or wrong endpoint | Check service discovery, port, routes, firewall, and Collector status |
| Export succeeds but backend shows no data | Wrong tenant, wrong signal endpoint, filter, or Collector pipeline | Check receiver, processor, exporter, routing, and backend query |
| Errors spike after rotation | Some pods still use the old secret or the new secret was mounted incorrectly | Check deployed secret version per pod and rollout status |

A helpful diagnostic sequence:

1. Identify the affected signal: traces, metrics, or logs; one service or many; one zone or the entire environment.
2. Compare when errors started against recent deployments, secret changes, certificate changes, or Collector configuration updates.
3. Inspect exporter and Collector state: failed export counts, queues, retries, dropped telemetry, and receiver/exporter status if metrics exist.
4. Classify the HTTP status or transport error. Check endpoint and TLS before changing credentials.
5. Verify workloads are using the right secret version and the credential has write access to the right tenant.
6. Verify the backend received data using a query scoped to a specific time window and service.

Do not enable debug logging in a way that logs full request headers. Never paste Authorization headers, API keys, certificate private keys, or secret values into issues, logs, screenshots, or support commands. If you need to confirm a header is configured, record presence and credential type rather than its contents.

## 8. Prevent Secret Leakage Through Telemetry and Operational Tools

Exporter secrets can leak in many places beyond configuration files. Control common leak vectors:

- **Git and code review:** commit only placeholders and variable names; enable secret scanning in repositories and pipelines. If a secret is found in a commit, revoke or rotate it immediately even if the commit is removed from the current branch.
- **CI/CD:** pull secrets from a secret store or workload identity in jobs; mask values in logs; restrict who can view logs and artifacts. Never print tokens to debug output or build caches.
- **Container images:** do not use Dockerfile `ARG`/`ENV` to bake in credentials; do not copy `.env` or secret files into image layers. Use runtime secret mounts or platform identity mechanisms.
- **Logs and exceptions:** never log headers, configuration objects holding credentials, or the entire environment. Check application, HTTP client, proxy, and Collector logs alike.
- **Actuator and management endpoints:** restrict access to `/actuator/env`, `/actuator/configprops`, and similar management endpoints; enforce authentication, network boundaries, and exposure policies. Do not rely on framework value masking as a substitute for access control.
- **Heap dumps and diagnostic bundles:** treat dumps, support bundles, and container snapshots as sensitive data because they can contain configuration objects or credential strings in memory.
- **Traces, baggage, and metric tags:** never place tokens, passwords, private keys, or credentials into span attributes, baggage, resource attributes, or metric tags. Baggage can propagate to other services and widen the leak radius.
- **Tickets and support channels:** reference only secret names, versions, fingerprints, or approved IDs; never share secret values in chat, email, or screenshots.

Secrets can still leak even when exporters are functioning normally. Therefore, combine secret scanning, audit logs, least-privilege access, and revocation procedures; checking export status alone is not enough.

## 9. Monitor Exporter Lifecycle and Health

Do not monitor only whether a secret exists. Track operational indicators to know that credentials remain valid and telemetry keeps reaching its destination:

- Successful/failed export counts and error rates per exporter or signal.
- Receiving endpoint HTTP status codes, especially 401 and 403, if the exporter/Collector exposes such metrics.
- Queue size, retries, dropped data, batch size, and export latency.
- Token or certificate expiration timestamps via safe secret-manager metadata; without reading or logging secret values.
- Time elapsed from creating a new secret version until all workloads adopt it.
- Count of workloads still using soon-to-expire credentials or older versions.

Set alerts far enough ahead of credential expiration so teams can rotate during business hours and resolve rollout issues. Authentication failure alerts should be separated from network timeouts and backend outages so operators take the right action.

Do not create metric tags from tokens, arbitrary secret versions, user IDs, or request IDs. If version tracking is needed, use a bounded label or controlled deployment state, never the secret value. Avoid building dashboards or logs containing sensitive data merely to assist rotation.

## 10. Responding When an Exporter Secret Is Exposed

When credential exposure is suspected, prioritize blocking continued use and scoping the impact:

1. Identify the secret name, version, credential type, granted permissions, and workloads using it. Do not redistribute the secret value to verify.
2. Create a replacement credential with least privilege if the system allows overlap; roll it out to legitimate workloads.
3. Revoke or disable the compromised credential. For active exploitation risks, execute emergency revocation under incident response procedures even if export is temporarily interrupted.
4. Inspect audit logs across the secret manager, telemetry backend, Collector, identity provider, and deployment platform for suspicious activity.
5. Assess what data or systems the credential could access. If the token only had ingest rights, check for forged telemetry or quota exhaustion; if it had read rights, assess data exposure risk.
6. Verify all workloads have moved to the new credential, the old secret is no longer mounted, and exporters are working again.
7. Identify the leak vector, close it, and update relevant policies, pipelines, or access controls.

Removing a secret from Git history, logs, or artifacts does not make a leaked credential safe. Revocation/rotation is mandatory; cleaning copies only reduces further exposure.

## 11. Exporter Secret Management Checklist

- [ ] Listed every exporter, endpoint, signal, and credential required by each flow.
- [ ] Credentials are stored in a secret manager or platform runtime secret mechanism.
- [ ] No real secrets appear in Git, application YAML, Dockerfiles, images, build arguments, or CI logs.
- [ ] Spring Boot obtains secrets through placeholders, config trees, or controlled identity mechanisms.
- [ ] Credentials follow least privilege and are separated by environment and service where appropriate.
- [ ] Exporter connections use TLS; mTLS private keys are protected and certificates have renewal schedules.
- [ ] Secrets are mounted with restricted permissions; Kubernetes Secrets have encryption at rest and proper RBAC if used.
- [ ] Rotation procedures include overlap, verified rolling restart/refresh, verification steps, and old-credential revocation.
- [ ] Alerts exist for authentication failures, export failures, and upcoming credential expiration.
- [ ] Actuator, diagnostic endpoints, heap dumps, and logs are protected from unauthorized access.
- [ ] Secrets are never placed in spans, baggage, resource attributes, metric tags, tickets, or screenshots.
- [ ] An incident response procedure exists to revoke exposed credentials and verify all workloads.

Good exporter secret management keeps telemetry flowing safely throughout the application lifecycle. With Spring Boot, externalized configuration only solves getting values into the application; real security also depends on provisioning sources, identity, read permissions, TLS, rotation, log hygiene, and revocation capability. Treat exporter credentials as production assets with clear ownership, lifetimes, audit trails, and operational procedures.
