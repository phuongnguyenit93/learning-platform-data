# Do Not Expose Sensitive Endpoints Publicly in Spring Boot

Keeping sensitive endpoints non-public is the principle of configuring Spring Boot Actuator so that endpoints capable of revealing internal data or modifying application state are unreachable from public networks. Endpoints such as `env`, `configprops`, `heapdump`, `threaddump`, `beans`, `mappings`, `loggers`, and `shutdown` can be helpful to operators investigating incidents, yet they significantly enlarge the attack surface if broadly exposed.

In the **SPRING_BOOT_OBSERVABILITY** module, Actuator supports health checks, metrics, and administrative operations. This lesson belongs to the **Actuator and Management** chapter, focusing on classifying sensitive endpoints, allowlist exposure, disabling unneeded endpoints, isolating the management network, authentication/authorization, controlling health details, testing, and incident response.

## 1. Why Keep Sensitive Endpoints Non-Public?

Actuator endpoints can return internal data or execute operations affecting runtime behavior. If sensitive endpoints are exposed via public ingress, attackers can gather reconnaissance data, discover misconfigured secrets, download in-memory data, or alter application behavior.

Common risks:
- Leaking configuration, hostnames, internal endpoints, and environment details.
- Leaking credentials if secret redaction is incomplete.
- Leaking the object graph, tokens, or personal data via a heap dump.
- Leaking stack traces, thread names, and request contexts via a thread dump.
- Changing log levels to increase the likelihood of capturing sensitive data.
- Stopping the application if the shutdown endpoint is enabled and exposed.
- Exposing API mappings, the bean graph, and dependency structure.

Not exposing sensitive endpoints publicly does not mean operators can never use them. Access should flow through a management network and controlled administrative permissions.

## 2. Classifying Endpoints by Sensitivity

| Endpoint | Data/Impact | Recommended Policy |
| --- | --- | --- |
| health | Application/dependency status | May be narrowly exposed; restrict details |
| info | Service/build info | Publish only selected fields |
| prometheus | Internal metrics | Trusted scrapers/networks only |
| metrics | Measurements and tags | Operators/monitoring |
| loggers | Read and change log levels | Authorized operators only |
| env | Environment/property sources | Non-public; typically unexposed |
| configprops | Bound configuration | Non-public; typically unexposed |
| heapdump | Heap snapshot that may contain secrets/PII | Special diagnostic procedure only |
| threaddump | Stack traces and runtime context | Operators only |
| beans | Bean list and internal structure | Non-public |
| mappings | Request mappings/API surface | Non-public |
| conditions | Auto-configuration details | Internal diagnostics only |
| shutdown | Stops application context | Disable unless a special use case exists |

Actual sensitivity depends on the data returned by the endpoint, redaction configuration, Spring Boot version, and environment. Inspect actual responses rather than relying solely on endpoint names.

## 3. Use an Allowlist Instead of Wildcard Exposure

Web exposure configuration should list required endpoints explicitly:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - prometheus
```

This configuration illustrates an allowlist. The `prometheus` endpoint requires the corresponding registry; if monitoring does not use that endpoint, omit it from the list.

Avoid production configurations that use a wildcard `include` and then attempt to `exclude` individual sensitive endpoints. During Spring Boot upgrades, new endpoints can appear and be accidentally published through the wildcard.

### 3.1. Exclude as a Supplementary Layer

You can use `exclude` to block specific endpoints even with a broader `include`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude:
          - env
          - configprops
          - heapdump
          - threaddump
          - beans
          - mappings
          - shutdown
```

This example is for lab environments or explaining precedence. For production, an explicit `include` allowlist is easier to govern.

### 3.2. Quote Wildcards in YAML

The `*` character must be quoted so YAML does not interpret it as an alias indicator:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Do not use wildcards on public-facing applications without justification and additional controls.

## 4. Disabling Unneeded Endpoints

Exposure decides which endpoints are published over a transport. Enablement decides whether an endpoint is enabled inside the application context. Endpoints that are not needed should be disabled when your version and endpoint support the property.

Example disabling shutdown:

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
```

Apply the same principle to other endpoints via `management.endpoint.<id>.enabled` when supported by the endpoint/version. Check the configuration metadata for your Spring Boot version.

Do not assume disabling one endpoint automatically protects other related endpoints. Review enablement, web exposure, and JMX exposure separately.

## 5. Separating the Management Port from the Application Port

You can use a dedicated management port to isolate administrative traffic:

```yaml
management:
  server:
    port: 9001
  endpoints:
    web:
      base-path: /manage
      exposure:
        include:
          - health
          - prometheus
```

A separate port isolates the administrative listener from application traffic, but does not create a security boundary by itself. If a container publishes port 9001 to the internet or an ingress routes to that port, the endpoint remains public.

Combine these measures:
- Publish the management port only inside internal networks.
- Do not configure public ingress to the management service.
- Use firewalls/security groups/network policies.
- Bind to an appropriate interface if supported by the environment.
- Allow access only from monitoring/operator networks.
- Inspect service mesh and reverse proxy routing.

## 6. Authentication and Authorization

Management endpoints must verify callers. Authentication establishes identity; authorization decides which endpoints a caller may invoke and which actions they may perform.

Example role separation by purpose:
- Health probe: read only minimal status.
- Prometheus scraper: scrape metrics only.
- Operator: read metrics/loggers and optionally change log levels if granted.
- Administrator: access sensitive diagnostic endpoints under a dedicated procedure.

Do not use one broad role for every endpoint merely for convenience. In particular, read-only endpoints can still disclose critical information.

### 6.1. Do Not Treat Internal Networks as Sufficient

Network isolation reduces reachability but does not replace authorization. A compromised internal workload or misconfiguration can open unintended access paths. Combine network policies, authentication, and least-privilege permissions.

### 6.2. CSRF and State-Changing Endpoints

Endpoints supporting POST operations such as `loggers` or `shutdown` must be accounted for in security policies. Do not disable CSRF globally across the application just to call an Actuator endpoint. Configure security chains per management path/port and real client type.

## 7. Health Endpoint Should Not Leak Dependency Details

Health is usually required by load balancers and orchestrators. However, detailed responses can reveal databases, brokers, disks, and dependency statuses.

Example restricting details:

```yaml
management:
  endpoint:
    health:
      show-details: never
      show-components: never
```

Depending on the Spring Boot version, `show-details`/`show-components` values and access rules may differ. If operators need details, use `when-authorized` together with an appropriate authorization policy.

### 7.1. Health Groups for Probes

Kubernetes liveness/readiness can use dedicated health groups. Expose only needed paths and avoid returning dependency details to public callers.

Liveness should reflect whether the process can continue running. Readiness can reflect whether the instance can accept traffic. Do not include dependency outages in liveness if doing so could cause a restart loop.

## 8. Env and Configprops

The `env` and `configprops` endpoints can reveal property sources, bound configuration, and application metadata. Even though Spring Boot has sanitization mechanisms for some sensitive keys, do not assume default redaction guarantees every secret is masked.

Secrets can appear under uncommon property names or inside custom objects. Therefore:
- Do not expose `env`/`configprops` publicly.
- Disable them if there is no use case.
- If operators need them, allow access only over the management network with a dedicated role.
- Verify sanitization with custom property names.
- Never put passwords/tokens into a custom info endpoint.
- Do not rely on property names containing the word "password" to protect all types of secrets.

Example disabling endpoints:

```yaml
management:
  endpoint:
    env:
      enabled: false
    configprops:
      enabled: false
```

Exact configuration depends on the endpoint and Spring Boot version; also verify they are not exposed over JMX.

## 9. Heapdump and Threaddump

A heap dump can contain the entire object graph at capture time, including tokens, credentials, session data, and user data still in memory. Dump files can also be very large and put pressure on disk and CPU.

A thread dump can expose class names, stack traces, thread names, internal endpoints, and request contexts. This is useful diagnostic data, but requires narrow access permissions.

Safe procedure:
1. Generate dumps only for a specific incident/use case.
2. Use authenticated internal management access.
3. Store dumps in access-restricted, encrypted storage.
4. Never attach dumps to public tickets/chats.
5. Set short retention and delete per policy.
6. Audit who generated/downloaded the dump and when.

Normally there is no need to expose `heapdump`/`threaddump` over public web exposure.

## 10. Loggers and Shutdown Endpoints

The `loggers` endpoint can alter log levels at runtime. Broadly enabling DEBUG/TRACE can increase log volume, leak data, and inflate ingestion costs. Grant access only to operators, time-box changes, and audit actions.

The `shutdown` endpoint directly affects availability. Without a clear administrative requirement, keep it disabled and unexposed.

```yaml
management:
  endpoint:
    shutdown:
      enabled: false
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
```

If the `shutdown` endpoint is used in a specialized system, require authentication, authorization, network isolation, auditing, and an operational confirmation workflow.

## 11. JMX Must Also Be Controlled

Hiding an endpoint from the web does not mean it disappears from JMX. JMX exposure has its own policy:

```yaml
management:
  endpoints:
    jmx:
      exposure:
        include:
          - health
          - metrics
        exclude:
          - env
          - configprops
          - heapdump
          - shutdown
```

If remote JMX access is not needed, disable or refrain from opening remote JMX listeners per runtime policy. Remote JMX requires authentication, TLS, and network restrictions; never expose JMX ports publicly.

## 12. Reverse Proxy, Ingress, and Service Mesh

Management endpoints can become unexpectedly public through a reverse proxy or ingress even when the application does not directly publish the port.

Check:
- Whether ingress rules route `/actuator` or `/manage`.
- Whether reverse proxies forward all paths.
- Whether a service mesh gateway routes the management port.
- Whether a Kubernetes Service exposes the management port to a broad network.
- Whether load balancer health checks use an endpoint exposing details.
- Whether CDN/WAF/caches store management responses.

Do not rely solely on URL paths to judge whether an endpoint is public. Verify network paths from outside and from the operator network.

## 13. Environment-Specific Configuration

You can start with a safe baseline and add only needed endpoints per profile.

application.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      show-details: never
      show-components: never
  endpoint:
    shutdown:
      enabled: false
```

application-local.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - metrics
          - loggers
```

application-prod.yml:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - prometheus
  endpoint:
    health:
      show-details: when-authorized
```

In YAML, merge identical keys within the same document to avoid duplicate-key parsing issues. For instance, the baseline above should place `shutdown` under the same `endpoint` mapping as `health`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
  endpoint:
    health:
      show-details: never
      show-components: never
    shutdown:
      enabled: false
```

Profiles only control configuration. Network isolation and security policies must still be enforced independently in deployment.

## 14. Testing That Sensitive Endpoints Are Not Public

Tests should verify endpoints are unreachable from the public web and only accessible to appropriate callers over protected management paths.

Example integration test verifying the `env` endpoint is not exposed:

```java
@SpringBootTest
@AutoConfigureMockMvc
class SensitiveActuatorExposureTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void envEndpointIsNotExposed() throws Exception {
        mockMvc.perform(get("/actuator/env"))
                .andExpect(status().isNotFound());
    }
}
```

Actual status may be 404, 401, or 403 depending on security/routing configuration. Tests should verify the desired security contract rather than depending on an unguaranteed status code.

### 14.1. Testing Authorization

Create tests with callers lacking the operator role and verify they cannot read sensitive endpoints or call `loggers` POST. Test that operators can access only the endpoints they are authorized for.

### 14.2. Testing the Network Boundary

In-process integration tests do not prove ingress/networking blocks public traffic. Inspect deployment manifests, ingress rules, and service ports, and probe from the corresponding network boundaries in staging.

## 15. Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `env` endpoint still reachable | Still in `include` or exposed over JMX | Check web/JMX exposure |
| Endpoint returns 401/403 | Authentication/authorization blocking access | Check caller identity and role |
| Sensitive endpoint public via ingress | Broad reverse proxy route | Inspect ingress/proxy/service |
| Heapdump still downloadable | Endpoint enabled and exposed on another transport | Check enablement, web, and JMX |
| Health response leaks dependencies | `show-details`/`show-components` too broad | Restrict details per policy |
| Prometheus cannot scrape | Network policy or auth blocks scraper | Check scraper identity and path |
| Loggers POST does not work | Endpoint unexposed or missing permission | Check exposure and authorization |
| Shutdown still available | Endpoint not disabled | Check `management.endpoint.shutdown.enabled` |
| JMX exposes endpoints though web is hidden | JMX exposure/remote listener still open | Check JMX config and runtime |
| Safe locally but public in prod | Profile/deployment overrides or different ingress | Check effective config and network |
| Secret appears in `env`/`configprops` | Sanitization misses custom key | Stop exposing; fix secret handling and policy |
| New endpoint appears after upgrade | Wildcard `include` auto-exposes it | Switch to allowlist and review upgrade |

### Investigation Procedure

1. Identify all management ports, base paths, and transports.
2. Check endpoint enabled state.
3. Check web exposure include/exclude.
4. Check JMX exposure and remote JMX listeners.
5. Check authentication/authorization per endpoint.
6. Check ingress, reverse proxies, service mesh, and firewalls.
7. Inspect response payloads for secrets or dependency details.
8. Check profiles and property source precedence.
9. Add tests ensuring sensitive endpoints cannot be reached from public-facing paths.
10. Re-verify from the network boundary after deployment.

## 16. Hands-On: Locking Down Sensitive Endpoints

The goal is to build an Actuator configuration publishing only needed health and metrics while locking down diagnostic endpoints.

### Preparation

- Spring Boot application with Actuator.
- Prometheus registry if scraping is needed.
- Spring Security.
- Local and production-like profiles.
- MockMvc/WebTestClient and a staging environment for network verification.

### Step 1 — List needed endpoints

Document endpoints serving health probes, scrapers, and operators. Do not add an endpoint just because it exists.

### Step 2 — Use an allowlist

Configure `include` with only `health` and `prometheus` if needed. Do not use wildcards in production.

### Step 3 — Disable dangerous endpoints

Disable `shutdown` and endpoints with no use case. Check property support for your version.

### Step 4 — Restrict health details

Set `show-details`/`show-components` appropriately. Confirm public callers receive only minimal status.

### Step 5 — Isolate the management network

Use a separate management port or service if required by architecture. Do not route the management port through public ingress.

### Step 6 — Set up security roles

Grant distinct permissions for probes, scrapers, and operators. Verify unauthorized callers cannot read sensitive endpoints.

### Step 7 — Check JMX

Verify endpoints are not unexpectedly exposed via JMX. Disable remote JMX if unneeded.

### Step 8 — Check ingress/proxy

Audit every route to `/actuator` and the management base path. Probe from external networks to confirm endpoints are not public.

### Step 9 — Automated testing

Add integration tests for hidden endpoints and authorization. Test the management port separately if the application uses a dedicated listener.

### Step 10 — Operational documentation

Record the list of allowed endpoints, owners, caller roles, and the temporary access procedure for heap/thread dumps during incidents.

### Acceptance Checklist

| Item to Prove | Expected Outcome |
| --- | --- |
| Endpoint inventory | Know which endpoints are needed and which are sensitive |
| Allowlist | No wildcard exposure in production |
| Enablement | Endpoints without a use case are disabled |
| Web/JMX | Both transports controlled independently |
| Network | Management port is not public |
| Authentication | Callers are identified |
| Authorization | Permissions scoped by endpoint/role |
| Health | No component details leaked outside policy |
| Heap/thread dump | Accessible only via special procedure |
| Loggers/shutdown | Restricted permissions; shutdown disabled if unneeded |
| Ingress | No public route to management paths |
| Testing | Exposure, auth, and network boundary tests exist |

## 17. Principles to Remember

1. **Do not make sensitive endpoints public.** `env`, `configprops`, `heapdump`, `threaddump`, `beans`, `mappings`, and `shutdown` require privileged admin permissions or should remain unexposed.
2. **Prefer an allowlist.** Wildcard `include` can expose new endpoints after upgrades.
3. **Distinguish enabled, exposure, and authorization.** Control all three layers.
4. **Web and JMX are independent transports.** Hiding from HTTP does not guarantee JMX is closed.
5. **A separate management port does not create a security boundary by itself.** Network policies, ingress restrictions, and authentication are still required.
6. **Restrict health details.** Probes should receive only necessary data.
7. **Protect heapdump/threaddump.** Dumps can contain in-memory data and require retention/access policies.
8. **Restrict loggers and shutdown.** `loggers` can alter runtime behavior; `shutdown` can stop the service.
9. **Inspect proxies/ingress/service mesh.** Endpoints can become public through indirect network paths.
10. **Test from the actual network boundary.** Unit tests do not prove public ingress blocks the endpoint.

Keeping sensitive endpoints non-public keeps Actuator valuable for monitoring and operators without broadening access to internal data. By using allowlists, disabling unneeded endpoints, isolating the management network, enforcing role-based authorization, and checking both ingress and JMX, Spring Boot can deliver production observability with a tightly controlled management surface.
