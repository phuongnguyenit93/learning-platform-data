# Protecting Credentials When Calling Configuration Sources or Registries

## 1. Why Must Config Server and Registry Credentials Be Protected Separately?

A Spring Cloud application often has to authenticate with multiple external systems starting right at startup:

- **Config Server** supplies configuration by application, profile, and label.
- **Service Registry** such as Eureka or Consul allows instance registration and discovery of other services.
- **Config backends** such as Git or Vault are used by Config Server itself to retrieve configuration data.
- **Secret managers** such as Vault issue tokens, passwords, or certificates to applications and integrations.

These connections belong to distinct trust boundaries. An application's credentials for reading Config Server are not the credentials Config Server uses to read Git/Vault. A token for reading Consul KV does not necessarily need permissions to register services or deregister instances.

Using a single shared account across all services, storing passwords in application.yml, embedding tokens in URLs, or placing credentials in service metadata means a single secret leak can expand access across multiple systems. Secrets can also be copied into logs, images, build artifacts, shell history, or monitoring systems.

This lesson belongs to the **Security** chapter of **SPRING_CLOUD_CORE**. Its goal is designing credential provisioning for Config Client and Discovery Client, separating permissions across call flows, supplying secrets outside artifacts, securing TLS channels, scoping access per application, and verifying credential rotation/revocation.

## 2. Distinguishing Authentication Flows

Before configuring anything, determine precisely who calls whom and which component owns which credentials.

| Flow | Calling Component | Receiving Component | Common Credentials |
| --- | --- | --- | --- |
| Fetch configuration | Config Client | Config Server | HTTP Basic, OAuth2 Bearer, client certificate |
| Locate Config Server via discovery | Config Client | Eureka/Consul | Eureka Basic/mTLS or Consul ACL token |
| Register and query services | Discovery Client | Service Registry | Consul ACL token, Eureka Basic/mTLS |
| Read key-values from Consul | Consul Config Client | Consul KV API | Consul Config ACL token |
| Read secrets from Vault | Spring Cloud Vault | Vault | Kubernetes auth, AppRole, cloud IAM, or Vault token |
| Fetch backend data | Config Server | Git, Vault, or other backend | Credentials reserved solely for Config Server |

Keep two principles in mind:

1. Credentials for each flow hold only the permissions needed for that flow.
2. Credentials must be available from a trusted source before the application needs to use them.

Specifically, Config Client must have credentials before sending its first request to Config Server. You cannot expect Config Server to return the password needed for Config Client to log into Config Server itself. Credentials used to establish the initial connection must come from the local environment, mounted secrets, workload identity, or an independent bootstrap trust source.

## 3. Never Store Secrets in Source Code or Images

Never commit the following values to a repository:

```yaml
spring:
  cloud:
    config:
      username: config-client
      password: real-password
    consul:
      discovery:
        acl-token: real-consul-token

eureka:
  client:
    serviceUrl:
      defaultZone: https://user:real-password@eureka.internal/eureka/
```

Do not place credentials in Dockerfile ENV instructions, build arguments, committed .env files, startup scripts, command-line arguments, or logged URLs. Removing a secret from a file in a later commit does not remove it from Git history or previously published artifacts.

Instead, keep only non-sensitive settings in configuration files, such as hostname, port, scheme, and property names. Secret values are supplied at runtime via one of these sources:

- Environment variables injected by the deployment platform.
- Secret files mounted read-only into the container.
- Spring Cloud Vault or an equivalent secret manager.
- Workload identities or machine identities issued by Kubernetes/cloud platforms.
- Certificate/keystores mounted from a secret volume.

Environment variables are convenient but not always the safest place for secrets: values can surface in process environments, diagnostic tools, or platform metadata. For strictly protected secrets, configuration trees from mounted secrets or secret managers are usually easier to control.

## 4. Using Spring Boot Configuration Trees for Mounted Secrets

Spring Boot supports the configtree: prefix to turn filenames in a directory into property names and file contents into property values. Kubernetes Secrets and Docker Secrets can be mounted as such files.

Example /run/secrets/ volume containing files:

```text
/run/secrets/
  spring.cloud.config.username
  spring.cloud.config.password
  spring.cloud.consul.config.acl-token
  spring.cloud.consul.discovery.acl-token
```

Filenames containing dots map directly to the corresponding properties. application.yml only needs to declare the location and non-secret endpoints:

```yaml
spring:
  config:
    import: "configtree:/run/secrets/"
  cloud:
    config:
      uri: https://config.internal.example
    consul:
      scheme: https
      host: consul.internal.example
      port: 8501
```

After importing, Spring Environment contains spring.cloud.config.username, spring.cloud.config.password, spring.cloud.consul.config.acl-token, and spring.cloud.consul.discovery.acl-token. Spring Cloud binding reads those values like ordinary properties.

If the secret directory must exist in production, omit the optional: prefix. When the volume is unmounted or required configuration is missing, the application should fail at startup rather than silently running unprotected. Use optional:configtree: only in environments where the secret volume may legitimately be absent and continuing startup is an intentional decision.

Restrict read permissions on directories and files to the user running the application. Mount volumes read-only, never copy secrets into image layers, never log file contents, and never include mounted files in unprotected backup artifacts.

### 4.1. Using Environment Variables When the Platform Manages Secret Lifecycles Well

If the platform securely injects environment variables and restricts read access, placeholders can be used:

```yaml
spring:
  cloud:
    config:
      uri: https://config.internal.example
      username: ${CONFIG_SERVER_USERNAME}
      password: ${CONFIG_SERVER_PASSWORD}
```

For Consul:

```yaml
spring:
  cloud:
    consul:
      config:
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
      discovery:
        acl-token: ${CONSUL_DISCOVERY_ACL_TOKEN}
```

Never specify a sample password or shared token as a default value. When a required credential is absent, an unresolved placeholder causes startup to fail early. Control read access to the environment and avoid dumping the full process environment during diagnostics.

## 5. Authenticating Config Client to Config Server with HTTP Basic

Spring Cloud Config Client supports HTTP Basic. You can configure the URI, username, and password separately:

```yaml
spring:
  config:
    import: "configserver:"
  cloud:
    config:
      uri: https://config.internal.example
      username: ${CONFIG_SERVER_USERNAME}
      password: ${CONFIG_SERVER_PASSWORD}
```

spring.cloud.config.username and spring.cloud.config.password are used to build authentication credentials for requests. These properties can originate from environment variables or a previously loaded configuration tree.

Spring Cloud Config also supports userinfo in URIs, yet URLs can end up in access logs, proxy logs, exceptions, tracing spans, or diagnostic dumps. Prefer separating credentials from URLs whenever the client/version supports dedicated properties. If you must use a URL with userinfo due to integration constraints, redact URLs everywhere logs may be written and restrict read access to configuration.

For mandatory Config Data imports in production, omit the optional: prefix. When Config Server is unreachable or credentials are invalid, startup must fail so the application does not run on defaults missing mandatory values. optional:configserver: is appropriate only when the application can continue operating safely without remote configuration.

### 5.1. OAuth2 Bearer Tokens

Config Server can be protected with OAuth2 Resource Server and JWT Bearer tokens. However, Config Client does not automatically fetch OAuth2 tokens merely because Config Server requires Bearer authentication.

The application needs a mechanism to acquire tokens from the authorization server—such as an OAuth2 Client using client_credentials—and attach the token to Config Server requests. You can use a custom request client/RestTemplate or header properties supported by your release's integration model.

Example when a token is pre-provisioned by a secret manager:

```yaml
spring:
  cloud:
    config:
      uri: https://config.internal.example
      headers:
        Authorization: "Bearer ${CONFIG_SERVER_ACCESS_TOKEN}"
```

This is a static token injected at startup. If using short-lived tokens that need automatic renewal, integrate an OAuth2 client manager or custom request client capable of fetching and refreshing tokens; never assume a static Bearer string in configuration rotates itself.

Never log the Authorization header in HTTP wire logs. Tokens require audience, scope, and expiry tailored to Config Server. Never use a single broad-scoped access token across multiple unrelated APIs.

If multiple Config Server URLs are configured, check per-endpoint authentication limitations in your version. Current Config Client documentation supports distinct HTTP Basic credentials per Config Server only when userinfo is embedded in each URL of `spring.cloud.config.uri`; other auth mechanisms do not share the same per-server capability. Avoid assuming a single username/password pair will be matched appropriately across all URLs in a list.

## 6. Protecting Config Server per Application

Simply requiring users to log in is insufficient if every authenticated client can read every application's configuration. Config Server serves resources under paths of the form:

`/{application}/{profile}/{label}`

If one service can change {application} in the URL and read another service's configuration, secrets leak across services.

Config Server should enforce an authorization policy so a principal can read only its own application's configuration. For example, principal/JWT claim inventory-service may access /inventory-service/** only; requests to /payment-service/** must be rejected.

You can implement this policy using Spring Security's SecurityFilterChain or RequestMatcher. General pattern:

```java
import org.springframework.security.authorization.AuthorizationDecision;

.authorizeHttpRequests(authorize -> authorize
    .requestMatchers("/actuator/health").permitAll()
    .requestMatchers("/{application}/**").access((authentication, context) -> {
        String requestedApplication =
                context.getVariables().get("application");
        String principal = authentication.get().getName();

        return new AuthorizationDecision(
                principal.equals(requestedApplication)
        );
    })
    .anyRequest().authenticated()
)
```

This snippet illustrates the authorization portion; place it inside a complete SecurityFilterChain and verify matchers against your system's context path and URL rules. With JWTs, compare the application ID against a claim issued by a trusted issuer—never read an arbitrary service name from a client-supplied header.

Credentials should represent per-workload identities. If inventory-service is compromised, its identity must only read inventory-service configuration, never secrets belonging to payment-service, user-service, or Config Server.

## 7. TLS and Mutual TLS for Config Server

HTTP Basic only encrypts passwords when transmitted over TLS. Never transmit credentials or sensitive configuration over plain HTTP on untrusted networks.

In production:

- Use HTTPS for Config Server.
- Verify the server's hostname and certificate chain.
- Configure a truststore if the server uses an internal CA.
- Use mutual TLS (mTLS) when workloads must authenticate via client certificates.
- Store private keys and keystore passwords in a secret volume or secret manager.
- Maintain a process to renew and replace certificates before expiration.

Example Config Client using a client certificate:

```yaml
spring:
  cloud:
    config:
      uri: https://config.internal.example
      tls:
        enabled: true
        key-store: /run/secrets/config-client.p12
        key-store-type: PKCS12
        key-store-password: ${CONFIG_CLIENT_KEYSTORE_PASSWORD}
        key-password: ${CONFIG_CLIENT_KEY_PASSWORD}
        trust-store: /run/secrets/config-server-truststore.p12
        trust-store-type: PKCS12
        trust-store-password: ${CONFIG_TRUSTSTORE_PASSWORD}
```

Property names and TLS configuration details depend on the Spring Cloud Config Client version. Check the reference documentation for your release train before applying. Never disable certificate verification to work around CA errors; install the proper CA into the truststore or fix the certificate hostname/SAN.

TLS protects the transport channel and authenticates peers by certificate. It does not replace authorization: a client certificate must still map to a principal with appropriate configuration read permissions.

## 8. Protecting Consul ACL Tokens for Config and Discovery

Spring Cloud Consul provides two separate properties for tokens:

- spring.cloud.consul.config.acl-token is used for reading configuration from Consul KV.
- spring.cloud.consul.discovery.acl-token is used for service discovery and discovery-related operations.

Example:

```yaml
spring:
  cloud:
    consul:
      scheme: https
      host: consul.internal.example
      port: 8501
      config:
        acl-token: ${CONSUL_CONFIG_ACL_TOKEN}
      discovery:
        acl-token: ${CONSUL_DISCOVERY_ACL_TOKEN}
```

Do not default to a single all-powerful token covering KV, catalog, service registration, and admin operations. Create separate policies:

| Identity | Required Permissions |
| --- | --- |
| Config reader | Read only the KV prefixes needed by the application |
| Discovery reader | Query only required catalog/service health data |
| Service registrar | Register, update, and deregister only services belonging to permitted workloads |
| Consul operator | Administrative rights; never granted to regular applications |

Separating config and discovery tokens lets you revoke one permission without necessarily breaking the other flow. If an application only looks up services and does not register itself, its identity should not have catalog write permissions.

The Consul property appendix documents spring.cloud.consul.config.acl-token and spring.cloud.consul.discovery.acl-token. Check property metadata for your exact Spring Cloud Consul version, as property names and binding details can change across releases.

### 8.1. Avoid Placing Tokens in Service Metadata

Service registry metadata should hold non-sensitive routing or capability details such as zone, version, protocol, or tags. Never place ACL tokens, passwords, private keys, or bearer tokens in metadata readable by other consumers.

Consul ACLs govern registry read/write permissions. If metadata leaks, any embedded token can be copied and used outside the original workload. Keep tokens in a secret manager and inject them only into authorized clients.

## 9. Authenticating Eureka with Basic Auth or mTLS

Spring Cloud Netflix Eureka Client supports HTTP Basic when the eureka.client.serviceUrl.defaultZone URL contains userinfo. Example configuration shape:

```yaml
eureka:
  client:
    serviceUrl:
      defaultZone: https://${EUREKA_USERNAME}:${EUREKA_PASSWORD}@eureka.internal.example/eureka/
```

Username/password values must be injected from a secret source. Eureka requires this URL format for Basic Auth in the built-in client integration; consequently, control logs, registry metadata, exceptions, and Actuator outputs so the URL is never printed externally.

For more advanced authentication needs, Spring Cloud Netflix lets you configure DiscoveryClientOptionalArgs and ClientFilter. When Eureka requires client certificates, TLS configuration can use a keystore and truststore:

```yaml
eureka:
  client:
    tls:
      enabled: true
      key-store: /run/secrets/eureka-client.p12
      key-store-type: PKCS12
      key-store-password: ${EUREKA_KEYSTORE_PASSWORD}
      key-password: ${EUREKA_KEY_PASSWORD}
      trust-store: /run/secrets/eureka-truststore.p12
      trust-store-type: PKCS12
      trust-store-password: ${EUREKA_TRUSTSTORE_PASSWORD}
```

Eureka has a limitation: it does not support distinct Basic Auth credentials per server URL; only the first credential set found is used. When connecting to multiple Eureka servers with different identities, never assume each URL automatically receives independent credentials.

### 9.1. Discovery-First Config Server and Credentials in Metadata

When Config Client uses discovery to locate Config Server, Config Server can register user, password, and configPath in Eureka metadata so clients know how to access the protected endpoint.

While convenient, this mechanism turns the registry into credential storage. Any client permitted to read metadata can potentially read those credentials. If you must use it:

- Restrict registry read access strictly to authorized workloads.
- Use read-only configuration credentials, never an admin account.
- Protect registry access channels with TLS/mTLS.
- Never log metadata maps or discovery responses.
- Rotate credentials and verify old metadata is replaced.
- Consider alternative auth mechanisms that do not distribute passwords via metadata if supported by your integration/version.

Never use service metadata as a general-purpose secret store.

## 10. Using Vault to Provision Workload Credentials

Spring Cloud Vault can retrieve secrets and provide authentication for applications. Machine authentication options are far preferable to embedding a static Vault root token in application.yml.

### 10.1. Kubernetes Authentication

When applications run in Kubernetes, Vault can authenticate using the Service Account Token mounted in the pod. Spring Cloud Vault configuration:

```yaml
spring:
  config:
    import: "vault://"
  cloud:
    vault:
      uri: https://vault.internal.example
      authentication: KUBERNETES
      kubernetes:
        role: inventory-config-reader
```

A Vault role should be bound to a specific Kubernetes service account and namespace. Policies should permit reading only the secret paths that workload requires. Never share a single Kubernetes service account across all microservices if they need different secret permissions.

### 10.2. AppRole

AppRole is designed for machine authentication. It uses a Role ID and Secret ID; the Secret ID must be protected like any credential. When using AppRole, issue Secret IDs with TTL/usage limits, consider response wrapping, and never commit them to source control.

Minimal configuration shape example:

```yaml
spring:
  cloud:
    vault:
      authentication: APPROLE
      app-role:
        role-id: ${VAULT_ROLE_ID}
        secret-id: ${VAULT_SECRET_ID}
```

If Vault Agent Auto-Auth or workload identity is available, evaluate that option so the application avoids managing long-lived static tokens. Vault tokens need explicit TTL, renewal, and revocation policies.

### 10.3. Distinguishing Config Server's Vault Token from Config Client's

When Config Server uses Vault as its backend, credentials for Config Server to access Vault belong to Config Server. Config Clients only need credentials to call Config Server. Never distribute Vault root tokens or Config Server backend tokens to every microservice.

Credentials for Config Server to access Vault must be configured in Config Server's own runtime environment using Vault's backend authentication mechanism. Keep backend credentials server-side and scope its policy strictly to the secret paths Config Server needs to read.

## 11. Least-Privilege Authorization

A well-designed credential carries only the minimum permissions required for a workload to perform its task.

| Component | Recommended Permissions | Permissions to Avoid |
| --- | --- | --- |
| inventory-service Config Client | Read inventory's own config path/profile | Read secrets of all applications |
| Consul discovery reader | Read required catalog/service health | Write policies, create tokens, administer agents |
| Consul service registrar | Register/deregister services for its own workload | Administer the entire catalog |
| Eureka client | Register and query registry per server policy | Use Eureka admin account |
| Config Server | Read configured repository/config backend | Use unrestricted Git/Vault admin credentials |
| Vault workload role | Read secret paths granted to the service | Read entire secret engines or revoke other workloads' tokens |

Separate identities by service and by environment. inventory-service-dev should not share credentials with inventory-service-prod. Accounts for developers, CI pipelines, Config Server, and runtime workloads should also be distinct.

If a service is compromised, the blast radius of leaked credentials must remain confined to the data and operations that service truly needs.

## 12. Handling Credentials at Startup and During Configuration Refresh

Spring Boot Config Data loads configuration early during startup. Credentials for calling Config Server, Consul Config, or Vault must already be available from a local/bootstrap source before remote property sources are fetched.

Never store spring.cloud.config.password solely inside the configuration repository served by Config Server itself. The application cannot yet log in to retrieve that value.

For refreshable configuration:

- Do not assume all credentials refresh automatically simply because an EnvironmentChangeEvent is emitted.
- Verify whether the integration supports token updates, session renewal, or HTTP client rebuilding.
- Once a credential is revoked, verify old clients are discarded and new connections use the new credential.
- For certificates/keystores, establish a controlled reload or restart process depending on HTTP client capabilities.
- Avoid refreshing many workloads simultaneously if doing so causes a request spike against Config Server, Vault, or the registry.

For bootstrap credentials, rotation may require an application rollout or a bootstrap client capable of refreshing credentials. Test the entire lifecycle rather than only changing values in the secret store.

## 13. Preventing Credential Leaks via Logs, Traces, or Actuator

A secret might stay out of config files yet still leak through logs and telemetry.

Common leak sources:

- URIs with userinfo, e.g., https://user:password@host.
- HTTP Authorization headers or Consul ACL token headers.
- Dumping the entire Environment, ConfigurationProperties, or configuration objects.
- HTTP client wire logging or debug logging of registry/config client libraries.
- Exceptions containing request URIs, headers, or response bodies.
- Eureka metadata maps containing username and password.
- Actuator env, configprops, beans, or custom diagnostic endpoints.
- Trace/span attributes automatically populated from URLs or request headers.

Operational rules:

1. Never log passwords, tokens, private keys, certificate private material, or Authorization headers.
2. Redact userinfo from URLs before logging.
3. Never enable wire-level logging in production without verified secret masking filters.
4. Restrict access permissions and network exposure of Actuator management endpoints.
5. Never attach secrets to metric labels or trace tags; those values are often retained long-term and accessible to many teams.
6. When debugging, log status codes, hosts, correlation IDs, and error types; never log request headers or secrets.
7. Set log/trace retention and access controls according to system sensitivity.

Actuator env and configprops can assist in diagnosing property binding, yet should not be broadly exposed. Even with framework sanitization, verify value display settings and restrict access to management endpoints.

## 14. Timeouts, Retries, and Fail-Fast on Authentication Failure

Authentication failures differ from network outages:

- 401 Unauthorized typically indicates missing or invalid credentials.
- 403 Forbidden typically indicates an authenticated principal lacking permission.
- Timeouts or connection refused may indicate network/server issues.
- TLS handshake/certificate errors may indicate trust chain, hostname, or client certificate problems.

Do not retry indefinitely on bad credentials. Continuous retries generate unnecessary load and hinder incident detection. For Config Client, choose fail-fast when remote config is mandatory; use bounded retry/backoff for appropriate transient errors.

If configuration from Config Server is mandatory for safe operation, never use optional:configserver: to mask authentication or connection errors. If remote config is genuinely optional, explicitly verify defaults are safe and log a warning when the remote source fails to load.

Never treat a 401 from one Config Server as a reason to spray the same credentials across other URLs. When multiple Config Servers exist, every endpoint must belong to the same trust boundary or have a clearly designed per-endpoint credential policy.

## 15. Testing Credential Security

Tests must not only confirm valid requests succeed. They must also verify invalid credentials are rejected and never appear in output.

| Scenario | Expected Outcome |
| --- | --- |
| Config Server receives valid Basic credentials over HTTPS | Config Client retrieves property source |
| Config Server receives wrong password | Request rejected; startup fails if remote config is mandatory |
| Principal inventory requests payment config | Server returns 403 or denies per policy |
| Consul Config token only has read access to granted prefix | Permitted prefix succeeds; other prefixes rejected |
| Discovery token only has catalog read access | Lookups work; registration attempts rejected |
| Eureka client lacks client certificate when mTLS is required | TLS handshake fails |
| Secret file is not mounted | Startup fails if configtree is a mandatory source |
| Credentials are rotated | New requests use new credentials; old credentials revoked on schedule |
| Debug logging enabled in tests | No passwords, tokens, or Authorization headers in logs |
| Unauthorized user calls Actuator diagnostic endpoint | Request rejected |

Use mock servers or test containers to verify status codes and request headers. Secrets in tests must be synthetic values; never copy production credentials into test fixtures, shared CI variables, or log snapshots.

## 16. Common Troubleshooting Scenarios

| Symptom | Possible Cause | How to Investigate |
| --- | --- | --- |
| Config Client receives 401 | Wrong username/password, expired token, or missing Authorization header | Check secret source and auth type; do not print credential values |
| Config Client receives 403 | Principal lacks permission to read application/profile/label | Check server authorization policy and principal mapping |
| Config Client receives no properties from server | Missing config import, server unavailable, or import marked optional | Check spring.config.import, redacted startup logs, and fail-fast policy |
| Secret property is null | Config tree unmounted, wrong filename, or wrong import path | Check filenames/paths and volume read permissions |
| Consul KV reads succeed but discovery fails | Different config and discovery tokens or ACL policy lacks catalog rights | Check both ACL tokens/properties independently |
| Eureka returns 401 despite correct URL | Improperly encoded credentials, URL parsing issue, or client using different credentials | Check defaultZone, secret binding, and URL redaction |
| Eureka mTLS handshake fails | Incorrect client keystore, truststore, password, or certificate chain | Check certificate validity, SAN, CA, and keystore format |
| Credentials leaked in logs | URL userinfo, headers, or wire logging not redacted | Disable sensitive logging, add redaction, and rotate exposed secret |
| Config Server returns another service's config | Authorization authenticates only without restricting {application} | Add per-application authorization policy |
| Updated secret store but client still uses old token | Client/session/connection does not reload credentials automatically | Check token renewal, client lifecycle, and rollout workflow |

## 17. Secure Implementation Workflow

1. Inventory all connection flows: Config Server, registry, Config backend, and Vault.
2. Assign distinct identities per application and per environment.
3. Grant read/register permissions strictly by function, separating Config ACLs and Discovery ACLs.
4. Select an appropriate machine authentication mechanism: Basic over TLS, OAuth2, mTLS, Consul ACL, or Vault workload identity.
5. Remove secrets from source code, images, and build artifacts.
6. Mount secrets via configuration trees or use a secret manager/runtime identity.
7. Supply bootstrap credentials prior to Config Data imports.
8. Enable TLS and verify certificates; never disable certificate checks to bypass errors.
9. Protect Config Server by application path and restrict registry metadata read access.
10. Redact sensitive URLs, headers, and properties from logs, traces, and Actuator.
11. Test 401, 403, TLS failures, missing secrets, rotation, and revocation.
12. Monitor expiration and establish rotation workflows before credentials expire.
13. Revoke old credentials after confirming all workloads have switched to the new ones.

## 18. Quick Self-Check Questions

1. Why must credentials for calling Config Server be available before Config Client loads remote configuration?
2. How do Config Client credentials differ from the credentials Config Server uses to access Git or Vault?
3. Why should passwords never be stored in URIs or in application.yml packaged inside an image?
4. How does configtree: map filenames and file contents into properties?
5. When should the optional: prefix be omitted from spring.config.import?
6. How does a Consul Config ACL token differ in purpose from a Discovery ACL token?
7. How does Eureka support Basic Auth and mTLS? What is the per-server credential limitation?
8. Why does Config Client not automatically obtain OAuth2 tokens simply by enabling Resource Server on Config Server?
9. Why must Config Server restrict access by {application} rather than merely requiring authentication?
10. Why should tokens or passwords never be placed into service registry metadata?
11. What must be tested during credential rotation and revocation?

## 19. Official References

- [Spring Cloud Config Client](https://docs.spring.io/spring-cloud-config/reference/client.html) — HTTP Basic, OAuth headers/custom clients, TLS, Config Data imports, discovery-first lookup, and Config Client credentials.
- [Spring Cloud Config — Security](https://docs.spring.io/spring-cloud-config/reference/server/security.html) — HTTP Basic, OAuth2/JWT, per-application access control, and TLS/HTTPS.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — environment variables, configuration trees, configtree:, and property placeholders.
- [Spring Cloud Consul — Common Application Properties](https://docs.spring.io/spring-cloud-consul/reference/appendix.html) — spring.cloud.consul.config.acl-token, spring.cloud.consul.discovery.acl-token, and TLS properties.
- [Spring Cloud Netflix — Eureka Client Authentication](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html) — Basic authentication, DiscoveryClientOptionalArgs, client certificates, and truststores.
- [Spring Cloud Vault — Authentication Methods](https://docs.spring.io/spring-cloud-vault/reference/authentication.html) — Token, AppRole, Kubernetes, and cloud workload authentication.
- [Spring Vault — Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html) — token lifecycle, AppRole, and Kubernetes authentication abstractions.

*This document focuses on client credentials when calling configuration sources and registries. Issue distinct identities per workload, inject secrets at runtime from trusted sources, protect TLS channels, and test rejection, rotation, and revocation of credentials.*
