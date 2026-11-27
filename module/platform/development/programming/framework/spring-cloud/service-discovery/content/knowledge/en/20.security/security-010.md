# Avoiding Credential Exposure in URLs, Logs, and Metadata

In a Spring Cloud Service Discovery system, applications frequently need to connect to Eureka, Consul, and internal services. These connections may require passwords, API keys, bearer tokens, or Consul ACL tokens. Placing credentials directly in URLs, logging full headers, or storing secrets in service metadata can cause them to be copied into proxies, dashboards, traces, registries, and other consumers.

The secure principle is to transmit credentials only via proper authentication mechanisms, store secrets in a secret management source, restrict read permissions, and never write secrets to logs or metadata. This lesson focuses on the three easiest leak vectors—URLs, logs, and metadata—while covering configuration, observability, rotation, and incident response when a credential is exposed.

## 1. Where Can Credentials Leak?

A credential does not exist solely in source code. It can traverse many components during a request or service registration flow:

```mermaid
flowchart TD
    SECRET[Secret source / Secret Manager]
    APP[Spring Boot application]
    URL[URL / query string]
    HEADER[Authorization header]
    LOG[Application and access logs]
    PROXY[Proxy / gateway / load balancer]
    TRACE[APM / trace / error report]
    REG[Consul / Eureka registry]
    META[Service metadata and tags]

    SECRET --> APP
    APP --> URL
    APP --> HEADER
    URL --> LOG
    URL --> PROXY
    URL --> TRACE
    HEADER --> LOG
    HEADER --> PROXY
    HEADER --> TRACE
    APP --> META
    META --> REG
    REG --> TRACE
```

Common leak paths:

- Query strings recorded in access logs, reverse proxies, CDNs, APMs, or testing tool histories.
- URLs formatted as `https://user:password@host` appearing in exceptions, dumped configurations, or connection logs.
- HTTP wire logging capturing `Authorization`, `Cookie`, `X-Consul-Token`, or request/response bodies.
- Service metadata and tags displayed in the Consul UI, Eureka Dashboard, or registry API, and then read by many consumers.
- Actuator `env`, `configprops`, heap dumps, thread dumps, or debug pages exposing configuration values.
- Trace baggage, span tags, metric labels, or error reports carrying sensitive query parameters or headers.
- Credentials committed to Git, baked into Docker images, manifests, `.env` files, or shell commands.

TLS protects data in transit, yet it does not prevent secrets from appearing in logs, traces, dashboards, or configuration files. Therefore, transport encryption must be paired with sensitive-data controls.

## 2. Never Put Credentials in URLs

### 2.1. Avoid Userinfo in URLs

Do not use URLs containing usernames/passwords:

```text
https://service-user:SuperSecret123@eureka.internal.example/eureka/
```

The `service-user:SuperSecret123@` part is userinfo. The URL can be stored verbatim in configuration, exceptions, logs, or monitoring tools. When copying the URL for diagnostics, credentials can also be accidentally shared with others.

Keep the URL containing only scheme, host, port, and path:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:https://eureka.internal.example/eureka/}
```

Handle authentication using a mechanism supported by your Eureka client version and infrastructure, such as TLS/mTLS or separately configured HTTP authentication. Some Eureka integrations accept Basic credentials in URL userinfo; if a legacy system forces this pattern, retrieve the value from a secret source, lock down logging, and plan a migration to an approach that does not embed secrets in URLs.

### 2.2. Avoid Tokens in Query Strings or Paths

Do not pass tokens in these forms:

```text
https://consul.internal/v1/catalog/services?token=SECRET_TOKEN
https://api.internal/services/SECRET_TOKEN/status
```

Query strings and paths are routinely recorded in access logs and telemetry. A URL can be saved in browser history, proxy caches, monitoring events, or exception reports.

With the Consul HTTP API, pass the ACL token via the `X-Consul-Token` header:

```bash
curl \
  -H "X-Consul-Token: ${CONSUL_HTTP_TOKEN}" \
  "https://consul.internal.example/v1/catalog/services"
```

With APIs supporting OAuth2, pass the access token in the header:

```http
GET /api/orders HTTP/1.1
Host: order.internal.example
Authorization: Bearer <access-token>
```

Headers are also sensitive data and can be captured by wire logs. Use headers only when clients, proxies, and observability systems are configured not to log authentication values.

### 2.3. Never Send Credentials in URLs Even Over HTTPS

HTTPS encrypts requests on the wire, yet the URL can still be logged at the client endpoint, reverse proxy, gateway, server access logs, APM, or debugging tools. If a token is in the query string, every component authorized to read the URL can see the token once TLS is terminated.

If an API supports tokens only via query strings, consider modifying the API or placing a gateway adapter capable of validating headers and forwarding securely. Treat query tokens strictly as a risk-assessed exception using short-lived, narrowly scoped tokens and redaction across the entire path.

## 3. Keep Credentials Out of Source Code and Committed Configuration

Never write passwords, ACL tokens, API keys, or private keys directly in `application.yml`:

```yaml
# Unsafe: secret is in a configuration file that may be committed.
spring:
  cloud:
    consul:
      token: "consul-production-secret"
```

Instead, reference a property supplied from a secure environment:

```yaml
spring:
  cloud:
    consul:
      host: ${CONSUL_HOST:localhost}
      port: ${CONSUL_PORT:8500}
      token: ${CONSUL_HTTP_TOKEN}

payment:
  api:
    base-url: ${PAYMENT_API_URL:https://payment.internal.example}
    token: ${PAYMENT_API_TOKEN}
```

Placeholders only separate the secret value from committed files. Secrets must still be delivered securely to the process and never printed to logs. With Spring Cloud Consul, verify property names and token configuration for the exact starter version in use.

### 3.1. Use a Secret Manager or Secret Management Platform

Common secret sources include:

- Cloud provider secret managers or systems like HashiCorp Vault.
- Kubernetes Secrets protected by RBAC and encryption at rest, or synced from a secret manager via an external-secrets controller.
- Secret files mounted read-only into containers.
- Environment variables supplied by the deployment platform, when appropriate for your threat model and operational tooling.

Never bake secrets into Docker images or write secrets into manifests stored in Git. Restrict who has permission to `exec` into Pods, read environments, read mounted files, or inspect runtime configuration.

### 3.2. Use Config Trees for Secrets Mounted as Files

Spring Boot supports importing config-tree configuration. For example, a secret mounted at `/run/secrets/payment.api.token`:

```yaml
spring:
  config:
    import: "optional:configtree:/run/secrets/"
```

Filenames inside the config tree directory map to property names; the file `payment.api.token` supplies the property `payment.api.token`. The application can inject that property like any other config source without writing values into `application.yml`.

Mount paths and file permissions must be restricted to the user running the application. Never print secret file contents in startup logs or diagnostic endpoints.

## 4. Passing Credentials via Headers in Spring

Example using `WebClient` with a bearer token loaded from externalized configuration:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class PaymentClientConfiguration {

    @Bean
    WebClient paymentWebClient(
            WebClient.Builder builder,
            @Value("${payment.api.base-url}") String baseUrl,
            @Value("${payment.api.token}") String token) {
        return builder
                .baseUrl(baseUrl)
                .defaultHeaders(headers -> headers.setBearerAuth(token))
                .build();
    }
}
```

The URL contains only the service address. The token is sent in the `Authorization` header when the client calls the API. In larger applications, use Spring Security OAuth2 Client to obtain and refresh access tokens rather than holding a static bearer token long-term.

Never log the `WebClient` object, header collections, request specifications, or configuration beans if they might contain tokens. When enabling HTTP wiretap for debugging, verify whether the library logs headers/bodies and enable it only in test environments with dummy data.

### 4.1. Calling the Consul HTTP API

Example using Consul's dedicated header:

```bash
curl \
  -H "X-Consul-Token: ${CONSUL_HTTP_TOKEN}" \
  -H "Accept: application/json" \
  "https://consul.internal.example/v1/health/service/order-service?passing"
```

The token does not appear in the URL. Ensure shell history, process inspection, CI logs, and proxies do not record header values. Avoid using `curl -v` or `--trace` in production terminals/CI because those flags can print request headers.

### 4.2. Connecting to Eureka

Keep `defaultZone` free of credentials:

```yaml
eureka:
  client:
    service-url:
      defaultZone: ${EUREKA_SERVER_URL:https://eureka.internal.example/eureka/}
```

Authentication for Eureka depends on the client version, HTTP transport, and endpoint protection infrastructure. Prefer TLS/mTLS or supported, separately configured authentication mechanisms. If forced to use HTTP Basic via URL userinfo on a legacy client, treat that URL as a secret: never log it, never expose it in Actuator, pull it from a secret manager, and plan a replacement.

## 5. Never Put Secrets in Service Metadata, Tags, or Instance IDs

Eureka and Consul metadata are designed to describe instances, not to store credentials. Metadata can be returned in discovery responses, displayed in dashboards, replicated across registry peers, or read by consumers.

Example of safe metadata:

```yaml
eureka:
  instance:
    metadata-map:
      zone: zone-a
      version: v2
      runtime: kubernetes
```

Unsafe example:

```yaml
eureka:
  instance:
    metadata-map:
      api-token: "secret-token-value"
      database-password: "db-password"
      consul-acl-token: "consul-token-value"
```

With Consul, tags and metadata can also be read via the Catalog/Health API. Never put secrets into `tags`, `meta`, service names, node names, instance IDs, or check output.

Use metadata for non-sensitive values useful for discovery or operations:

- `zone`, `region`, `cluster`, `namespace`.
- `version`, `build`, `protocol`.
- Functional groups or capabilities containing no confidential information.

Never use metadata to pass tokens between providers and consumers. If a consumer needs credentials to call a provider, provision separate credentials via a secret manager or workload identity; discovery provides only addresses and routing information.

## 6. Safe Logging: Record What Is Needed for Diagnostics, Omit Auth Data

Logs are valuable for incident investigation, yet they should never capture entire requests/responses. A safe log entry typically needs only service name, route template, status code, duration, trace ID, and a non-sensitive correlation identifier.

Recommended log example:

```java
log.info(
    "Dependency call service={} method={} route={} status={} durationMs={} traceId={}",
    "payment-service",
    "POST",
    "/payments",
    statusCode,
    durationMs,
    traceId
);
```

Avoid logging directly:

```java
// Unsafe: may contain query tokens, userinfo, or sensitive data.
log.info("Request URL: {}", request.getRequestURL());
log.debug("Headers: {}", requestHeaders);
log.debug("Request body: {}", requestBody);
```

`request.getRequestURL()` does not necessarily include the query string in the Servlet API, yet URLs or paths can still carry sensitive data. Do not rely on a single getter API to guarantee sanitized data; log application-controlled route templates and exclude queries/bodies by default.

### 6.1. Fields Requiring Redaction

When headers or configurations must be logged for diagnostics, apply allowlists and redaction at the logger/collector. Fields that routinely require masking include:

| Field | Handling |
| --- | --- |
| `Authorization` | Never log the value; if needed, log only the scheme such as `Bearer` or `Basic`. |
| `Proxy-Authorization` | Mask completely. |
| `X-Consul-Token` | Mask completely. |
| `Cookie`, `Set-Cookie` | Mask completely or omit from logs. |
| `access_token`, `refresh_token`, `id_token` | Never log query/body values. |
| `api_key`, `api-key`, `client_secret`, `password` | Mask completely. |
| Private keys, certificate material, secret file contents | Never log. |

Redaction should be enforced across multiple layers: application, reverse proxy/API gateway, log collector, and APM. A single regex filter cannot guarantee masking every spelling, encoding, or field name; prefer not collecting sensitive data in the first place.

### 6.2. Restricting HTTP Wire Logging

In production:

- Never enable debug/wiretap logging of full requests and responses without verified redaction.
- Never log all headers or bodies merely to troubleshoot connectivity issues.
- Never include tokens in exception messages or custom error responses.
- Never dump `Environment`, `ConfigurationProperties`, HTTP client configs, or bean graphs to logs.
- When debugging is needed, use request IDs, statuses, durations, route templates, and sanitized error details.

### 6.3. Protecting Logs and Traces After Writing

Even redacted logs can still contain internal hostnames, service topology, or customer identifiers. Restrict read permissions, retention periods, export capabilities, and log query access. Trace baggage/span attributes need the same policy; never put tokens or sensitive headers into baggage because they can propagate across many services.

## 7. Protecting Diagnostic Endpoints and Runtime Configuration

Spring Boot Actuator provides endpoints for observing configuration and state. Endpoints such as `env`, `configprops`, `heapdump`, `threaddump`, or `loggers` can expose internal information if overly exposed or over-permissioned.

Expose only required endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
```

If `env`, `configprops`, or other admin endpoints are needed in an internal environment, protect them with authentication/authorization, network policies, and least privilege. Spring Boot includes sanitization mechanisms for certain sensitive values, but do not treat that as a reason to open config endpoints to public networks. Verify sanitization and endpoint exposure behavior for your exact version.

Never put secrets into error responses, startup banners, health details, metric labels, or logs when the application fails to resolve a placeholder. Configuration errors should name the missing property without printing secret values.

## 8. Credential Lifecycle Management

Secure credentials must be issued, scoped, rotated, and revoked under a defined process:

1. **Per-workload issuance:** each service or environment gets its own token; never share an admin token system-wide.
2. **Least privilege:** tokens only grant permissions to read required services/health or register the exact needed service; never grant admin rights if an application only performs discovery.
3. **Appropriate lifetimes:** prefer short-lived tokens or workload identity where supported.
4. **Centralized storage:** use a protected secret manager or secret store; never commit to Git, images, or artifacts.
5. **Rotation:** issue new credentials, update workloads, verify requests succeed, and then revoke old credentials.
6. **Auditing:** track who issues, reads, modifies, and revokes credentials.
7. **Decommission revocation:** delete tokens for decommissioned instances or pipelines.

With Consul ACLs, create tokens bound to task-appropriate policies. Consumers that only read catalog/health should never use tokens with write or admin rights. Providers registering services need permissions scoped strictly to their respective service/node under the designed ACL model.

With Eureka, protect the server with TLS and an authentication mechanism suited to the client/server versions. Do not treat Eureka's lack of a Consul-style ACL model as an excuse to leave the registry open publicly; enforce network controls and client identities.

## 9. Incident Response When Credentials Are Exposed

If a token appears in a URL, log, metadata, trace, or repository, treat that credential as compromised. Removing the string from one file does not invalidate the old credential.

Response procedure:

1. Identify the credential type, affected services/tenants, permission scope, and potential exposure window.
2. Issue a replacement token/credential with least privilege.
3. Update the secret source and redeploy or refresh workloads using the credential.
4. Verify legitimate requests succeed with the new credential.
5. Revoke the old credential once necessary consumers have switched over; if risk is high, revoke immediately and accept controlled disruption.
6. Inspect audit logs for anomalous access during the window when the credential may have been exposed.
7. Restrict access to logs/traces containing the secret and handle copies and retention per organizational incident response procedures.
8. Purge the secret from source/config history if required, while still rotating/revoking since Git history and copies may persist.
9. Find the root cause: URL logging, wiretap, metadata, debug endpoints, CI output, or secret injection.

Never paste exposed tokens into tickets, chats, or shell commands asking others to check them. When reporting, state only the credential type, affected system, timestamp, and non-sensitive reference IDs.

## 10. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Token appears in access logs | Token placed in query string or path | Move to header; configure proxies not to log queries unnecessarily; rotate exposed token. |
| Password appears in Eureka URL in exceptions | URL uses `user:password@host` userinfo | Use credential-free URLs and a separate auth mechanism; redact logs during transition. |
| Consul token appears in shell/CI logs | Used `curl -v`, `--trace`, or echoed environment variables | Pass token via header with verbose tracing disabled; apply secret masking and process/log controls. |
| Token appears in Eureka/Consul metadata | Metadata used as a credential transport channel | Remove sensitive metadata, rotate token, and provision secrets via a secret manager. |
| Actuator displays properties with secrets | Exposed `env`/`configprops` or inadequate sanitization config | Narrow endpoint exposure, secure access permissions, and verify sanitization. |
| APM trace captures Authorization header | Instrumentation collects headers or baggage unfiltered | Disable sensitive header capture and configure agent denylists/allowlists. |
| Secret still works after removal from YAML | Credential was never revoked; value remains in Git history or runtime | Rotate/revoke the credential and update all affected workloads. |
| Log redaction misses field name variants | Relied on simple regex or incomplete casing | Use allowlist logging, normalize keys, and test multiple encodings/casings. |

## 11. Pre-Deployment Security Checklist

- URLs contain no userinfo, passwords, API keys, or tokens in queries/paths.
- Tokens are transmitted via headers or supported identity mechanisms; connections use appropriate TLS/mTLS.
- Secrets are retrieved from a secret manager, protected Kubernetes Secret, or config tree; never baked into source/images.
- Consul ACL tokens have least-privilege policies and are separated per workload.
- Eureka endpoints are network-restricted and have appropriate authentication/TLS.
- Service metadata, tags, instance IDs, and health output contain no secrets.
- Application logs, access logs, proxy logs, wire logs, and APMs do not capture sensitive headers/bodies.
- Configuration and administrative Actuator endpoints are not publicly exposed.
- Logs/traces have controlled read access and retention.
- Procedures exist for rotation, revocation, auditing, and handling exposed credentials.

## 12. Key Takeaways

- Never place credentials in URL userinfo, query strings, or paths; URLs are routinely copied into logs, proxies, traces, and debugging tools.
- Use the `Authorization` header or dedicated headers such as `X-Consul-Token`, combined with TLS and redaction.
- Placeholders in `application.yml` only reference secrets; actual secrets must come from a securely managed source.
- Service metadata, tags, and instance IDs are readable by the registry/consumers; never use them as a secret store.
- Log by allowlist: route template, status, duration, and trace ID; never log raw URLs, headers, bodies, or full configurations.
- Protect Actuator and log/APM systems; never rely solely on default sanitization.
- When a credential is exposed, rotate/revoke first, then handle log/source copies and audit investigations.

## References

- [OWASP: Information Exposure Through Query Strings in URL](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url)
- [OWASP: Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html)
- [OWASP: Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Spring Boot: Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot: Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
- [Consul: ACL Tokens](https://developer.hashicorp.com/consul/docs/security/acl)
