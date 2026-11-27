# Registration Limits, Client Approval, and Preventing SSRF from Metadata URLs

## 1. Why Does Dynamic Client Registration Need Control Policies?

In an **OAuth 2.0/OpenID Connect Authorization Server** system using **Spring Security, Spring Authorization Server, and Spring Boot**, Dynamic Client Registration (DCR) lets clients or developers submit metadata to register OAuth/OIDC clients without an administrator manually creating each record.

This capability is useful when there are many applications, many tenants, partner ecosystems, or clients provisioned via automated lifecycles. Yet every registration issues an identity and security configuration for an application that can request tokens, ask for permissions, and route users through authorization flows.

If the registration endpoint is left too open, an attacker can:

- Create a client spoofing a legitimate application's name/logo to trick users during consent.
- Request grant types, scopes, or authentication methods beyond their actual need.
- Register attacker-controlled redirect URIs to receive authorization responses.
- Register a `jwks_uri` pointing to internal services to trigger SSRF when the AS fetches keys.
- Put malicious URLs into `logo_uri`, `policy_uri`, `tos_uri`, or `client_uri` to deceive users; if the AS fetches content to display/scan, those URLs can also cause SSRF.
- Register server-to-server callbacks such as `backchannel_logout_uri` pointing into the internal network if the deployment supports that feature.
- Create large volumes of junk clients to fill the database, raise costs, and cause denial of service.

Therefore, DCR must simultaneously control **who can register, what clients are permitted to declare, which metadata is trusted, and where the Authorization Server is allowed to make network requests**.

In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, the goal is to learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server. This lesson belongs to the **Dynamic Client Registration** chapter, focusing on registration limits, approval workflows, and preventing SSRF from metadata URLs.

### Learning Outcomes

After this lesson, you will be able to:

1. Distinguish open registration, protected registration, initial access tokens, and software statements.
2. Design a client approval workflow prior to granting registration permissions.
3. Constrain redirect URIs, grant types, token endpoint authentication methods, and scopes.
4. Configure DCR in Spring Authorization Server 1.5.x, understanding that the endpoint is disabled by default and the roles of `client.create`/`client.read`.
5. Keep default validators and replace only the scope validator with an allowlist.
6. Identify metadata fields that can cause the AS to initiate outbound requests.
7. Design SSRF defenses at registration-time, fetch-time, and network egress.
8. Test approvals, quotas, metadata validation, DNS rebinding, redirect bypasses, and credential lifecycles.

**Example scope:** Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.5.8 on the Servlet stack. DCR APIs are illustrated per 1.5.8 documentation/Javadoc; verify against your project's actual version before deploying.

## 2. Components and Terminology

### 2.1. Client Registration Request and Client Registration Response

DCR under RFC 7591/OIDC Dynamic Client Registration 1.0 uses JSON metadata:

- **Registration Request:** client submits desired details such as `redirect_uris`, `grant_types`, `response_types`, `token_endpoint_auth_method`, `scope`, `client_name`, and `jwks_uri`.
- **Registration Response:** OP issues `client_id`, optionally `client_secret`, and returns accepted metadata.
- **Initial Access Token:** access token issued by the OP to a developer/client to authorize calling the Registration Endpoint when the deployment uses protected registration.
- **Registration Access Token:** bearer token issued by the OP after registration, used to access the client's own Client Configuration Endpoint.
- **Software Statement:** JWT signed/MACed by an OP-trusted issuer carrying attested metadata.

`initial_access_token` and `registration_access_token` serve different purposes. The initial token authorizes **creating a registration**; the registration access token authorizes **managing an already-created registration** per the endpoint capabilities implemented by the OP. Never mix these two tokens.

### 2.2. Open Registration and Protected Registration

| Model | Who can call the endpoint? | When is it suitable? | Main Risks |
| --- | --- | --- | --- |
| Open registration | Requests without an initial access token | Public ecosystems needing self-service onboarding with strong abuse controls | Client spam, spoofed metadata, resource exhaustion |
| Protected registration | Developer/client must hold a valid initial access token | Internal systems, partners, B2B, or where approval is required | Managing token issuance, leaks, and overly broad permissions |
| Registration via portal | User submits application to a portal; portal issues initial token after policy/review | Enterprises requiring approvals, audits, and ownership controls | Requires workflows and binding approvals to the exact payload |

RFC 7591 defines the initial access token as an optional mechanism; when an OP restricts which parties may register, using an initial access token is necessary. The RFC does not define enterprise approval workflows. Approval portals, contract checks, domain ownership verification, and internal policies are each OP's own implementation.

### 2.3. Self-Declared Metadata Does Not Equal Verified Identity

Unless protected by a software statement signed by an OP-trusted authority, the OP must treat client metadata as **self-asserted**. For example:

- `client_name: "Corporate Payroll"` does not prove the client belongs to that company.
- `logo_uri` pointing to an official logo does not prove the registrant owns the brand.
- `software_id` and `software_version` are publisher-declared data and do not self-authenticate the software.
- `client_uri` sharing a domain with redirect URIs is a review signal, not proof of domain ownership.

A signed software statement provides attestation value only when the OP verifies its signature, issuer, expiration, audience/intended recipient, claims, and trust policy. If the statement is valid and accepted by the issuer, metadata in the statement must take precedence over conflicting JSON values per RFC rules. Even so, a signature does not automatically prove every detail about the deployment instance or the request sender.

## 3. Defining Registration Policy Before Enabling the Endpoint

### 3.1. Not Every Application Needs DCR

Spring Authorization Server **disables the OIDC Client Registration Endpoint by default** because many deployments do not need self-registering clients. When the number of clients is small and changes are infrequent, an administrative workflow over `RegisteredClientRepository` can be simpler and easier to control.

Enable DCR only when there is a specific use case such as:

- A developer portal creating clients for partners after approval.
- Tenants managing multiple independent applications.
- A plugin/integration ecosystem needing self-service onboarding.
- A platform provisioning clients per environment or workload lifecycle.

If enabling the endpoint, design authentication, authorization, rate limiting, metadata policies, persistence, auditing, and incident response upfront.

### 3.2. Client Classification

| Client Type | Common Grants | Authentication Method | Factors to Consider |
| --- | --- | --- | --- |
| Server-side web application | `authorization_code`, optionally `refresh_token` | `client_secret_basic`, `private_key_jwt`, or mTLS | HTTPS redirect URI, secret/key rotation, PKCE where appropriate |
| Browser-based SPA | `authorization_code` + PKCE | `none` | Public client, no client secret issued, strict redirect URIs |
| Native application | `authorization_code` + PKCE | `none` or profile-specific method | Loopback/custom scheme per platform policy, no embedded shared secret |
| Machine-to-machine | `client_credentials` | `private_key_jwt`, mTLS, or policy-approved secret | Narrow scopes, clear owner, key lifecycle |
| Client needing signed request objects | Per actual flow | Typically `private_key_jwt` or key-based method | Trusted JWK Set, safe `jwks_uri` and outbound fetching |

Do not accept every grant type and authentication method just because the library supports them. Build allowlists by client type and business purpose; reject invalid or policy-disallowed grant combinations.

### 3.3. Metadata Decision Table

| Metadata | Recommended Policy |
| --- | --- |
| `redirect_uris` | Required for redirect-based flows; HTTPS in production web; exact allowlist; no wildcards |
| `post_logout_redirect_uris` | Registered separately; never auto-copied from `redirect_uris` |
| `grant_types` | Allowlist by client type; grant only truly needed grants |
| `response_types` | Matches grant/flow; avoid implicit in new designs |
| `token_endpoint_auth_method` | Allowlist; public clients use `none`, confidential clients require a suitable method |
| `scope` | Grant only scopes supported by OP and approved for the client |
| `jwks_uri` | HTTPS, SSRF policy, fetch-time egress enforcement, and JWK schema validation |
| `jwks` | If accepted, validate JWK set; disallow private/symmetric key material |
| `client_name`, `logo_uri`, `client_uri`, `policy_uri`, `tos_uri` | Treat as self-declared data; encode on display and warn about third-party sources |
| `software_id`, `software_version` | Cross-check inventory/attestation if needed against impersonation or duplicates |
| `sector_identifier_uri`, `request_uris`, `backchannel_logout_uri` | Enable only when features are needed; apply corresponding SSRF/egress policies |

### 3.4. Quantity and Size Limits

A policy can define:

- New registrations per developer/tenant/registrar per hour/day.
- Total active clients per tenant and per issuer.
- Maximum redirect URIs, grant types, response types, scopes, and metadata extensions per client.
- Maximum sizes for JSON requests, software statements, JWK Sets, and individual URLs.
- Lifetimes for temporary or inactive clients.
- Failed registration attempt thresholds and cooldowns upon signs of abuse.
- Concurrency caps for metadata fetching and logo scanning tasks.

Rate limiting by IP alone is insufficient: NAT/proxies can put many developers behind one IP, while botnets can rotate IPs. Combine principal/registrar, tenant, software identity, IP/network reputation, and overall quotas.

## 4. Client Approval Workflow

### 4.1. Approval Is Not a Built-In State in RFC 7591

DCR describes the protocol for submitting metadata and receiving client details. It does not define `PENDING`, `APPROVED`, or `REJECTED` states or an approval admin UI. Spring Authorization Server provides the endpoint and providers to process registration, yet does not ship a complete business approval workflow out of the box.

For deployments requiring approval, place a review step prior to granting permission to call the Registration Endpoint:

1. Developer submits an application via an authenticated portal.
2. The system stores proposed metadata and owner identity in a pending state.
3. A policy engine checks application type, domain, redirect URIs, grants, scopes, auth methods, JWKs, and metadata URLs.
4. An approver reviews details, proof of ownership, and risk.
5. Only after approval does the system issue an initial access token or perform registration on the developer's behalf.
6. The OP saves the registration and returns `client_id` and credentials per client type.
7. The system logs an audit event and notifies the outcome.

### 4.2. Binding Approvals to the Exact Approved Metadata

A common design flaw is approving application A and then issuing an initial access token usable for any payload. The token holder could alter `redirect_uris`, `grant_types`, `scope`, or `jwks_uri` after approval.

An approval should be bound to:

- Tenant/organization and responsible owner.
- Client type, environment, and use case.
- List of redirect/post-logout URIs.
- Grant types, response types, and token endpoint authentication method.
- Permitted scopes.
- Reviewed JWK or `jwks_uri`.
- Validated metadata/callback URLs.
- Payload version or digest of the canonical approved metadata.
- Expiration, usage count, and the registrar permitted to use the approval.

At registration time, the server must ensure the final payload matches the approved content. You can have the portal perform registration from the approved record, or add a validator/gate checking the payload digest before the provider saves the client. Issuing an initial token alone does not bind the token to specific metadata.

### 4.3. Suggested States and Transitions

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> NEEDS_CHANGES: Changes requested
    NEEDS_CHANGES --> PENDING: Developer updates
    PENDING --> REJECTED: Rejected
    PENDING --> APPROVED: Review passed
    APPROVED --> TOKEN_ISSUED: Registration permission issued
    TOKEN_ISSUED --> REGISTERED: Registration succeeded
    TOKEN_ISSUED --> EXPIRED: Expired / unused
    REGISTERED --> SUSPENDED: Incident or violation
    REGISTERED --> DEPROVISIONED: Client revoked
    SUSPENDED --> REGISTERED: Restored after review
    SUSPENDED --> DEPROVISIONED: Permanently revoked
    REJECTED --> [*]
    EXPIRED --> [*]
    DEPROVISIONED --> [*]
```

The states in the diagram belong to the deployment's approval service. Do not treat these as states natively provided by OIDC or `RegisteredClient`.

### 4.4. Approver Checklist

Reviewers should answer:

- Who owns the application and who is operationally responsible?
- Do domains/redirect URIs belong to the organization or a contracted vendor?
- Is the client public or confidential? Is a secret declared for an SPA/native app?
- Do grant types fit the use case? Are any disallowed grants requested?
- Are scopes broader than needed? Are there admin privileges or sensitive data scopes?
- Does the token endpoint auth method match the client's ability to protect credentials?
- Is the JWK valid, public-key-only, using allowed algorithms, and with a clear key owner?
- Could metadata URLs/callbacks cause the OP to call the internal network?
- Is there a `software_id`/software statement to verify the publisher?
- Are review expiration dates, owner, contacts, and a deprovisioning plan defined?

## 5. Dynamic Client Registration in Spring Authorization Server

### 5.1. Endpoint Is Disabled by Default

Spring Authorization Server 1.5.8 provides the OIDC Client Registration Endpoint, defaulting to:

```text
POST /connect/register
GET  <registration_client_uri returned in the registration response>
```

The Registration Endpoint path can be changed via `AuthorizationServerSettings.oidcClientRegistrationEndpoint(...)`. Client Read must use the exact `registration_client_uri` returned by the OP; never infer the path or append `client_id` to a URL yourself. The endpoint handles Client Registration and Client Read. **DCR is disabled by default**; enable it in the OIDC configurer of the Authorization Server Security Filter Chain.

This is an OAuth2 protected resource: requests must carry a bearer access token. Spring Security Resource Server support is configured for the endpoint, yet a `JwtDecoder` bean is required to verify the access token.

### 5.2. Configuring the Endpoint and Preserving Default Validators

Endpoint configuration example:

```java
import java.util.List;
import java.util.Set;
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationProvider;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationValidator;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class DynamicClientRegistrationSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server -> server
                .oidc(oidc -> oidc
                    .clientRegistrationEndpoint(endpoint ->
                        endpoint.authenticationProviders(
                                registrationPolicy())))
            )
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    private static Consumer<List<AuthenticationProvider>> registrationPolicy() {
        Set<String> allowedScopes = Set.of("openid", "profile", "email");

        return providers -> providers.forEach(provider -> {
            if (provider instanceof OidcClientRegistrationAuthenticationProvider registration) {
                registration.setAuthenticationValidator(
                    OidcClientRegistrationAuthenticationValidator
                        .DEFAULT_REDIRECT_URI_VALIDATOR
                        .andThen(OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
                        .andThen(OidcClientRegistrationAuthenticationValidator
                            .DEFAULT_JWK_SET_URI_VALIDATOR)
                        .andThen(scopeAllowlist(allowedScopes))
                );
            }
        });
    }

    private static Consumer<OidcClientRegistrationAuthenticationContext>
            scopeAllowlist(Set<String> allowedScopes) {

        return context -> {
            OidcClientRegistrationAuthenticationToken request =
                    context.getAuthentication();
            OidcClientRegistration registration = request.getClientRegistration();

            // Client Read request does not contain a new registration payload.
            if (registration == null) {
                return;
            }

            List<String> requestedScopes = registration.getScopes();
            if (requestedScopes != null
                    && !allowedScopes.containsAll(requestedScopes)) {
                throw new OAuth2AuthenticationException(
                    new OAuth2Error("invalid_client_metadata",
                        "One or more requested scopes are not permitted", null));
            }
        };
    }
}
```

This is a scope-allowlist policy example. Add rules for grant types, response types, authentication methods, and redirect URIs suited to the client type. Other Authorization Server imports and beans (issuer, signing JWK, client repository, authorization service, login chain) must still be configured in the application.

Spring Authorization Server requires a `JwtDecoder` bean to verify bearer access tokens calling the DCR endpoint. If the AS's access tokens are JWTs signed by the AS's own JWK Set, you can configure a decoder against the trusted issuer:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder registrationAccessTokenDecoder() {
    String issuer = "https://auth.example.com";
    NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(issuer + "/oauth2/jwks")
            .build();
    decoder.setJwtValidator(JwtValidators.createDefaultWithIssuer(issuer));
    return decoder;
}
```

This is an example for JWT access tokens. If the system uses another token format, choose a decoder/introspection strategy matching your implementation and endpoint version; never disable signature/issuer validation just to make DCR work.

The example decoder checks issuer and default timestamps. If your deployment issues a dedicated audience for the DCR endpoint, add a corresponding audience validator; never verify only the signature while skipping issuer/audience policies.

### 5.3. Understanding the Four Default Validators

In Spring Authorization Server 1.5.8, `OidcClientRegistrationAuthenticationValidator` provides dedicated validators for key metadata:

| Validator | Default Behavior |
| --- | --- |
| `DEFAULT_REDIRECT_URI_VALIDATOR` | Rejects URIs with fragments, missing schemes, or unsafe schemes like `javascript`, `data`, `vbscript` |
| `DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR` | Applies the same rules as redirect URI |
| `DEFAULT_JWK_SET_URI_VALIDATOR` | Rejects `jwks_uri` not using HTTPS |
| `DEFAULT_SCOPE_VALIDATOR` | Rejects requests with non-empty scopes |

The `jwks_uri` validator checks only the HTTPS scheme. It is **not an SSRF firewall**: an HTTPS URL can still resolve to a private IP, loopback, or cloud metadata endpoint.

Two `SIMPLE_*_VALIDATOR` groups preserve legacy compatibility behavior:

- `SIMPLE_JWK_SET_URI_VALIDATOR` performs no `jwks_uri` validation.
- `SIMPLE_SCOPE_VALIDATOR` accepts any scope.
- The SIMPLE redirect validators check only for fragments, so they can accept URIs enabling open redirects or XSS depending on context.

Do not use SIMPLE validators as a quick fix for compatibility errors. If you need to accept scopes, replace only the scope validator with an allowlist as shown in the example; keep the default validators for redirects and `jwks_uri`.

### 5.4. Provisioning the Registrar Client and Initial Access Token

The Spring guide uses a pre-registered registrar client with `client_credentials` and the `client.create` scope; read permissions may also be granted per policy:

```java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient registrar = RegisteredClient.withId("registrar-internal-id")
        .clientId("developer-portal-registrar")
        .clientSecret(encodedRegistrarSecret)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("client.create")
        .scope("client.read")
        .build();
```

`encodedRegistrarSecret` must be encoded with the encoder used by the Authorization Server; sample secrets must never be committed to source control.

In the Spring 1.5.8 guide, the initial access token used to create a client must have **only a single scope**: `client.create`. After successful registration, this token is single-use and invalidated. Do not issue registrar tokens carrying extra business API scopes or other administrative permissions.

Example token request:

```http
POST /oauth2/token HTTP/1.1
Authorization: Basic BASE64_REGISTRAR_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=client.create
```

If using an approval portal, issue the token only after the submission is approved and bind the final payload to the approved contents. Spring's initial access token is permission to call the registration endpoint; by itself it does not encapsulate the enterprise's entire approval decision.

### 5.5. Registering and Reading a Client

Registration request:

```http
POST /connect/register HTTP/1.1
Authorization: Bearer INITIAL_ACCESS_TOKEN
Content-Type: application/json
Accept: application/json

{
  "client_name": "Orders Portal",
  "grant_types": ["authorization_code"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "client_secret_basic",
  "redirect_uris": ["https://orders.example.com/login/oauth2/code/oidc"],
  "scope": "openid profile"
}
```

The response contains the registered metadata and management details such as `client_id`, `registration_access_token`, and `registration_client_uri`; confidential clients may receive `client_secret`. The client must store credentials securely immediately upon receipt.

The registrar may be granted `client.read` when the deployment permits the registrar to perform Client Read. In the per-client management flow of the Spring 1.5.8 guide, Client Read uses `registration_access_token` as a bearer token at the `registration_client_uri` returned after registration. Both permissions must be managed according to the chosen flow; never use the `client.create` initial access token to read registrations. A registration access token is a long-lived credential that can allow reading registration details; if full RFC 7592 management endpoints are implemented, the credential may allow updating/deleting the registration. Never put this token in logs, public browser storage, URLs, or tickets.

Per the 1.5.8 Protocol Endpoints documentation, Client Read requests require a bearer access token with the `client.read` scope; the guide demonstrates reading back the newly created registration using the `registration_access_token` and `registration_client_uri` pair. A registrar can be granted `client.read` to execute protected reads per deployment configuration.

**Version boundary:** Spring Authorization Server 1.5.8 documentation describes Client Registration and Client Read. RFC 7592 also defines Client Update and Client Delete; do not assume the default endpoint of every Spring version implements full PUT/DELETE. If that lifecycle is needed, verify API support for your version or build a separate management workflow with equal protection.

### 5.6. Custom Metadata Requires Converters

The Spring guide illustrates custom metadata such as `logo_uri` and `contacts` by configuring:

- `OidcClientRegistrationAuthenticationProvider.setRegisteredClientConverter(...)`.
- `OidcClientRegistrationAuthenticationProvider.setClientRegistrationConverter(...)`.
- `OidcClientConfigurationAuthenticationProvider.setClientRegistrationConverter(...)`.

This matters whenever metadata extensions need to be persisted and returned via Client Read. Do not assume every metadata field in OIDC Registration 1.0 automatically maps into `RegisteredClient`. Support only fields with explicit schemas, validation, persistence, readback, and security policies.

## 6. How Can SSRF Arise from Metadata URLs?

### 6.1. What Is SSRF in the Context of an Authorization Server?

Server-Side Request Forgery (SSRF) occurs when an attacker controls the URL or network destination to which a server component makes an HTTP request. In DCR, registering clients can place URLs inside metadata. If the AS or a background worker fetches that URL, the server can be abused to access:

- Loopback addresses such as `127.0.0.1`, `::1`, or localhost services.
- Private IPv4 ranges such as `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`.
- IPv6 unique-local/link-local, IPv4-mapped IPv6 addresses, or NAT64 ranges that map to blocked addresses.
- Cloud/container metadata endpoints, service discovery, internal admin APIs, database proxies, or control planes.
- Services reachable only from the Authorization Server's backend network.

Impact depends on the AS's network privileges: leaking internal data, accessing credential metadata, calling internal APIs, or exhausting resources via slow/huge responses.

### 6.2. Classifying Metadata URLs by Behavior

Not every metadata URL automatically causes SSRF. Risk arises when a component **dereferences the URL server-side** or sends requests to it:

| Metadata/Feature | Potential Behavior | Risk |
| --- | --- | --- |
| `jwks_uri` | AS fetches JWK Set when verifying client/request signatures or handling related flows | SSRF, DNS rebinding, malicious/oversized JWK responses |
| `sector_identifier_uri` | OIDC OP fetches JSON array at registration time to verify redirect URIs | SSRF right inside the registration request |
| `request_uri` / `request_uris` | Authorization Server fetches Request Object when processing authorization requests | SSRF at authorize time |
| `backchannel_logout_uri` | OP sends HTTP POST Logout Token to RP | Outbound callback SSRF on logout |
| `logo_uri` | OP downloads logo for display/scanning or browser loads image | Server-side SSRF if proxied/downloaded; phishing/privacy if browser loads |
| `client_uri`, `tos_uri`, `policy_uri` | OP displays links to users; may fetch/scan if deployment implements that | Phishing/malicious content; SSRF if server fetches |

`jwks_uri` is standard metadata in RFC 7591. OIDC Dynamic Client Registration 1.0 also defines `sector_identifier_uri`; OIDC Core defines `request_uri` and Authorization Server fetching of Request Objects. Back-Channel Logout defines the OP sending POST to `backchannel_logout_uri`. If implementing these features, control outbound destinations right where requests originate.

Per OIDC Registration, `sector_identifier_uri` uses HTTPS and references a JSON array containing registered redirect URIs; the OP must fetch and verify this array at registration time. Per OIDC Core, `request_uri` must use HTTPS unless the Request Object is signed in a way the AS can verify; the AS fetches the Request Object when handling an authorization request if no valid cache exists.

`backchannel_logout_uri` must not contain fragments and SHOULD use HTTPS; OIDC allows HTTP in certain confidential client cases if permitted by the OP. Protocol scheme rules do not replace SSRF policies: an HTTPS endpoint can still point to a private IP or internal service.

### 6.3. Distinguishing Server-Side Fetch from Browser-Side Load

If the Authorization Server only renders `logo_uri` as an image for the browser to load itself, the image request is made by the user's browser, not directly as SSRF from the server. However, phishing, tracking, and malicious content risks remain.

If the AS downloads the logo to resize, cache, malware-scan, or proxy it, that request originates from the server and becomes an SSRF surface. Similarly, if the AS fetches `policy_uri` for link checking, never use a default HTTP client to fetch arbitrary URLs freely.

RFC 7591 warns that metadata URLs displayed to End-Users can be used to lure clicks onto malicious content; the spec recommends checking host/scheme relationships with redirect URIs and warning about third-party origins. Implementing that recommendation by fetching content must be paired with an SSRF-safe fetcher.

### 6.4. Why Checking HTTPS Is Not Enough

URLs such as:

```text
https://169.254.169.254/latest/meta-data/
https://127.0.0.1:8443/admin
https://internal-service.corp.example/secrets
```

can still use the HTTPS scheme. Likewise, an apparently public hostname can return private addresses upon DNS resolution or change DNS answers between validation and connection.

Spring Authorization Server 1.5.8 includes `DEFAULT_JWK_SET_URI_VALIDATOR` to reject `jwks_uri` values not using HTTPS. This validator does not enforce full DNS/IP/port/redirect/egress policies. Therefore, configuring the default validator is necessary but insufficient to claim SSRF protection.

## 7. Designing SSRF-Safe Metadata Fetching

### 7.1. Prefer Host Allowlists When the Use Case Allows

If the organization only permits clients from known publishers/partners, host allowlisting is straightforward to enforce:

- Permit only FQDNs belonging to verified publisher/partner domains.
- Permit only HTTPS and defined ports (typically 443).
- Reject URLs containing user-info, fragments, or disallowed schemes.
- Reject IP literals unless there is a specific requirement.
- Do not automatically allow all subdomains via wildcards unless all DNS/delegation is controlled.
- Apply separate allowlists per metadata type; `jwks_uri` and `backchannel_logout_uri` have different trust models.

Domain allowlisting does not replace IP address checking. An allowlisted domain can still be misconfigured in DNS or hijacked.

### 7.2. Validating DNS and Destination IPs

If the business must support arbitrary Internet URLs:

1. Parse URLs with a standard URI library; reject empty hostnames, user-info, unusual schemes, and disallowed ports.
2. Resolve all A and AAAA records using a controlled resolver.
3. Normalize IPv4-mapped IPv6/NAT64 addresses and inspect every returned address.
4. Reject loopback, private, link-local, unique-local, multicast, unspecified, reserved, carrier-grade NAT, metadata IPs, and any non-public-unicast range per policy.
5. Connect directly to the verified IP (pin the DNS result for the request), while preserving the original hostname for HTTP Host, TLS SNI, and certificate validation.
6. If DNS changes, re-run validation for subsequent requests.

Do not resolve DNS to check it and then let the HTTP client resolve again when connecting. That is a time-of-check/time-of-use gap exploitable via DNS rebinding. Check every A/AAAA result; do not accept a host simply because one address is valid if other addresses point to internal networks.

### 7.3. Handling Redirects

Disable automatic HTTP redirect following in the metadata fetcher. A public URL can return `302 Location: http://169.254.169.254/` and send the HTTP client into the internal network.

If the business truly requires redirects:

- Cap the hop count very tightly.
- Parse and re-run full scheme/host/port/DNS/IP validation on every `Location`.
- Never forward Authorization headers, cookies, client credentials, or custom headers to a new origin.
- Disallow redirecting to different schemes or out-of-policy ports.
- Detect loops and reject abnormal URL chains.

### 7.4. HTTP and Content Limits

A metadata fetcher should constrain:

- Connect timeout, response timeout, and total processing duration.
- Maximum response bytes and JSON/JWK Set size.
- Number of JWKs, individual key sizes, and JSON nesting depth.
- Expected `Content-Type`; e.g., a JWK Set must be valid JSON.
- Concurrent connections, queue size, and rate per client/host.
- Retry counts and backoff; never retry infinitely.

TLS certificate verification must remain enabled. Never disable hostname verification to "help a partner endpoint." Never parse arbitrary HTML/XML when an endpoint is expected to return only JSON; if content scanning is required, run it in an isolated worker with resource limits.

### 7.5. Network Egress Is a Mandatory Defense Layer

Applications should run in a network segment allowed to reach only necessary outbound destinations. Firewalls, Kubernetes NetworkPolicy, service mesh egress gateways, or outbound-controlling proxies should:

- Default-deny private/internal ranges and cloud metadata services.
- Block loopback/link-local/multicast and unnecessary management endpoints.
- Open only policy-approved DNS resolvers and Internet destinations.
- Isolate metadata fetch worker egress away from the core AS network.
- Log destination host/IP, policy decision, and request ID without logging tokens/secrets.

Application validation and network egress controls complement each other. A parser bug, DNS rebinding, or redirect bypass must not open arbitrary paths into the control plane.

### 7.6. Interfaces for Policy and Fetcher

Separate URL validation policy from provider code for testability:

```java
import java.net.URL;

public interface ClientMetadataUrlPolicy {

    // Only validate whether the URL is permitted for this metadata type.
    // Do not fetch the URL inside synchronous validation methods.
    void validateJwksUri(URL uri);

    void validateSectorIdentifierUri(URL uri);
}

public interface SafeClientMetadataFetcher {

    // Implementations must pin verified DNS/IP, disable automatic redirects,
    // enforce timeouts/size limits, and respect egress policies.
    byte[] fetchJwkSet(URL uri);

    byte[] fetchSectorIdentifierDocument(URL uri);
}
```

The interfaces above describe responsibility boundaries, not a complete SSRF-safe HTTP client. Actual implementations must integrate the DNS resolver, HTTP client, TLS, redirect policy, and network egress controls described above.

## 8. Adding URL Validation to the Spring Provider

### 8.1. Checking Metadata URLs in the Registration Context

```java
import java.net.URL;
import java.util.function.Consumer;

import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationContext;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcClientRegistrationAuthenticationToken;
import org.springframework.security.oauth2.server.authorization.oidc.OidcClientRegistration;

private static Consumer<OidcClientRegistrationAuthenticationContext>
        metadataUrlValidator(ClientMetadataUrlPolicy policy) {

    return context -> {
        OidcClientRegistrationAuthenticationToken request =
                context.getAuthentication();
        OidcClientRegistration registration =
                request.getClientRegistration();

        // Client Read does not send new registration metadata.
        if (registration == null) {
            return;
        }

        URL jwksUri = registration.getJwkSetUrl();
        if (jwksUri != null) {
            policy.validateJwksUri(jwksUri);
        }

        URL sectorUri = registration.getClaimAsURL("sector_identifier_uri");
        if (sectorUri != null) {
            policy.validateSectorIdentifierUri(sectorUri);
        }
    };
}
```

Add the validator to the chain configured on `OidcClientRegistrationAuthenticationProvider`:

```java
OidcClientRegistrationAuthenticationValidator
    .DEFAULT_REDIRECT_URI_VALIDATOR
    .andThen(OidcClientRegistrationAuthenticationValidator
        .DEFAULT_POST_LOGOUT_REDIRECT_URI_VALIDATOR)
    .andThen(OidcClientRegistrationAuthenticationValidator
        .DEFAULT_JWK_SET_URI_VALIDATOR)
    .andThen(scopeAllowlist(allowedScopes))
    .andThen(metadataUrlValidator(metadataUrlPolicy))
```

This adds URL and scope policy validation. It does not fetch the JWK Set or sector document directly inside the validator. If reading `sector_identifier_uri` contents per OIDC Registration is required, use `SafeClientMetadataFetcher` with full SSRF protections and verify the JSON array contains the registered redirect URIs.

### 8.2. Re-Validating at Fetch Time

Do not check URLs only once at registration time. DNS records, redirect responses, domain ownership, and endpoint contents can change later. Every time the AS fetches a JWK Set or Request Object, apply the fetch policy at connection time.

For `backchannel_logout_uri`, check the destination both at registration time and when dispatching logout requests. Registration-time approval does not guarantee a domain will always point to the same IP throughout the client's lifecycle.

### 8.3. Restricting URL Extensions

If enabling custom metadata such as `sector_identifier_uri`, `request_uris`, or `backchannel_logout_uri`, determine:

- Which converter parses/stores/returns that metadata.
- Which component will execute the outbound request.
- Fetch timing and caching conditions.
- Permitted HTTP methods, headers, and payloads.
- Egress identity/network privileges of the fetching component.
- How to disable the metadata or suspend the client if the URL changes or violates policy.

Do not add a URL field to `RegisteredClient` just because a converter can store it. Support metadata only when there is a real consumer and matching security controls.

## 9. Protecting Registration Credentials and Client Lifecycle

### 9.1. Initial Access Token

An initial access token is the credential used to call the Registration Endpoint. In the Spring guide, the token used to create a client carries only the `client.create` scope and is single-use. For protected registration:

- Issue tokens through an authenticated developer portal or an out-of-band workflow.
- Use short lifetimes, high entropy, single-use semantics, and registrar restrictions.
- Never write tokens into application logs, analytics, URLs, or tickets.
- Revoke tokens when submissions are rejected, expired, or suspected compromised.
- Never issue `client.create` tokens to every logged-in user.

If approval must bind to a payload, associate the initial token with an approval record or payload digest on the server. A bearer token carrying only `client.create` without metadata binding allows the token holder to alter the request body before registering.

### 9.2. Registration Access Token

`registration_access_token` is a bearer credential bound to the created registration. Depending on the management endpoints implemented by the OP, the holder can read or modify client configuration. Therefore:

- Return the token only over HTTPS and only once in the registration response.
- Store it on the client in a secret manager/secure storage, never in public browser local storage.
- Never place the token in `registration_client_uri` or query strings.
- Redact `Authorization` headers in reverse proxies, APM, tracing, and error reports.
- Support rotating/revoking per RFC 7592 if management endpoints are implemented.
- When deprovisioning a client, invalidate its associated registration access token as well.

Client secret and registration access token are two distinct credentials. Client secret is used at the Token Endpoint per authentication method; registration access token is used at the Client Configuration Endpoint.

### 9.3. Client Read, Update, and Delete

RFC 7592 defines Client Read, Client Update, and Client Delete operations via the Client Configuration Endpoint. The registration access token is the bearer token protecting those operations.

Spring Authorization Server 1.5.8 guides Registration and Client Read. When Update/Delete are needed, confirm support for your exact version or implement a separate management API/portal. A management API must:

- Verify the registration token belongs to the right client.
- Prevent clients from changing `client_id`.
- Re-validate new metadata with the same policies as initial registration.
- Prevent self-escalation of grants, scopes, redirect URIs, or authentication methods beyond approval.
- Rotate registration tokens/secrets per policy and invalidate old tokens on schedule.
- Audit all metadata changes and deprovisioning events.

### 9.4. Software Statement

If the deployment accepts `software_statement`, it must:

1. Trust only issuers configured in the trust store.
2. Verify signatures with permitted algorithms/keys.
3. Validate `iss`, `aud`, `exp`, `nbf`, `jti`, and replay policies.
4. Verify metadata in the statement matches the product, software version, redirect URIs, and client type approved by the publisher.
5. When both the JSON request and the statement declare a metadata field, apply OIDC DCR precedence rules.
6. Never treat self-signed statements or statements signed by untrusted issuers as proof of identity.

A software statement does not replace the initial access token in protected registration. A token granting permission to call the endpoint and a statement attesting metadata are two separate mechanisms.

## 10. Restricting Metadata and Client Policies

### 10.1. Redirect URIs Need Dedicated Policy

Spring's default validator rejects fragments, missing schemes, and unsafe schemes; however, syntactically valid URIs do not prove the client owns the domain. For redirect-based flows:

- Require registering each exact URI; disallow wildcards.
- Production web callbacks use HTTPS.
- Allow localhost HTTP only in development environments per policy.
- Native apps use custom schemes/loopbacks per profile and app-binding proof.
- Disallow URIs containing user-info or fragments.
- Verify domain ownership via DNS challenges, HTTPS challenges, or vendor review when needed.
- At the Authorization Endpoint, compare the request `redirect_uri` against registered URIs per protocol rules.

Do not let clients register redirect URIs pointing to an open redirector on an otherwise valid domain. A valid host does not guarantee the callback path does not forward to another host.

### 10.2. Grant Types and Response Types

Choose allowlists by client type. Examples:

| Client type | Suggested Allowlist |
| --- | --- |
| Server-side web | `authorization_code`; `refresh_token` if proper rotation/reuse detection exists |
| SPA/native public | `authorization_code` with PKCE; never issue client secrets |
| Machine-to-machine | `client_credentials` with narrow scopes and strong client authentication |
| Legacy client | Keep only required grants during a time-bounded migration window |

Disallow implicit or resource owner password credentials in new designs. Do not grant grant types incompatible with the client model simply because a request can declare them.

### 10.3. Scopes Are What the Client May Request, Not User Consent

Scopes in registration metadata describe the set of scopes the client intends to use. They do not self-grant permissions to the client or replace user consent. When an authorization request arrives:

- Scopes must be within the set the client is permitted to use.
- Scopes must be within the set supported by the OP.
- User/tenant policies and consent still govern actual granted permissions.
- Privileged scopes need separate approval and an owner.
- Never accept arbitrary scopes simply because the client declared them.

In Spring Authorization Server 1.5.8, `DEFAULT_SCOPE_VALIDATOR` rejects any registration request with a non-empty scope. If your application needs to declare scopes in DCR, use a custom allowlist validator like the example in section 5.2; do not swap in `SIMPLE_SCOPE_VALIDATOR` to accept everything.

### 10.4. JWK Set and Client Authentication

If a client uses `jwks_uri`:

- Accept HTTPS only and enforce SSRF-safe URL policies.
- JWK Sets must contain public keys only; reject private/symmetric key material.
- Accept only signing algorithms in the allowlist.
- Cap document size, key count, and individual key size.
- Disallow `jwks_uri` and `jwks` appearing together in the same registration.
- Cache per bounded-TTL policy; have a key rotation strategy and fetch-failure handling.

If the deployment accepts inline `jwks`, the data still needs schema/algorithm validation; unlike URL references, it cannot automatically refresh keys.

### 10.5. Metadata Displayed to End-Users

Fields `client_name`, `logo_uri`, `client_uri`, `tos_uri`, and `policy_uri` are client-supplied data unless attested. When rendering consent pages:

- Escape HTML and attributes; never inject raw metadata into markup.
- Use CSP and content isolation for third-party images/links.
- Display a warning label noting that name/logo/links are publisher-declared.
- Consider an interstitial warning before opening untrusted policy/terms links.
- If proxying/downloading logos, use a safe fetcher and restrict content types/sizes.
- Never treat a logo host matching a redirect URI host as proof of publisher identity.

### 10.6. Metadata Extensions Must Have Schemas and Lifecycles

For every custom field, define:

- JSON type, length, format, and required/optional status.
- Who may submit it and who may read it.
- Whether it can be modified post-registration.
- Whether it triggers outbound requests.
- Whether it is displayed to End-Users.
- Whether it requires consent/approval.
- How to migrate, version, and deprecate it.

Never store raw JSON requests as uncontrolled metadata and feed them straight into consent pages or authorization logic. Store only allowlisted and validated fields.

## 11. Testing DCR, Approval, and SSRF

### 11.1. Test Matrix

| ID | Scenario | Expected Result |
| --- | --- | --- |
| D01 | Call Registration Endpoint when DCR is disabled | Endpoint does not process registration |
| D02 | Request missing bearer access token | Authentication rejected |
| D03 | Registrar token has exact `client.create` scope | Can create registration per policy |
| D04 | Token has `client.create` plus other scopes | Rejected per requirement that token carry only `client.create` |
| D05 | Reuse initial access token after successful registration | Rejected because token was consumed |
| D06 | Token lacks `client.create` scope | Rejected |
| D07 | Client Read using valid credential | Returns only the registration that credential is authorized to read |
| D08 | `redirect_uris` contains fragment | Rejected by default validator |
| D09 | `redirect_uris` uses `javascript`/`data` scheme | Rejected by default validator |
| D10 | `redirect_uris` is valid HTTPS but domain lacks ownership proof | Approval/domain policy requests proof or rejects |
| D11 | Request declares scopes inside allowlist | Scope validator allows |
| D12 | Request declares scopes outside allowlist | Rejected with `invalid_client_metadata` |
| D13 | Request declares HTTP `jwks_uri` | Rejected by default validator |
| D14 | Request declares HTTPS `jwks_uri` pointing to loopback/private IP | Rejected by SSRF policy |
| D15 | Hostname resolves to both public and private IPs | Entire host rejected |
| D16 | DNS changes from public to private after validation | Blocked by fetch-time DNS pinning/egress policy |
| D17 | Public URL redirects to link-local metadata IP | Redirect disabled or next hop rejected by policy |
| D18 | URL uses IPv4-mapped IPv6 pointing to private IPv4 | Normalized and rejected |
| D19 | URL uses NAT64 representing metadata IP | Normalized/rejected by policy |
| D20 | `jwks_uri` returns HTML instead of JWK Set JSON | Fetcher rejects content type/schema |
| D21 | JWK Set too large or has too many keys | Blocked by byte/key limits |
| D22 | JWK Set contains private/symmetric key material | Rejected |
| D23 | `sector_identifier_uri` returns JSON that is not a redirect URI array | Registration fails |
| D24 | `sector_identifier_uri` omits some registered redirect URIs | Registration fails |
| D25 | `logo_uri` contains malicious HTML/script content | Never rendered as raw HTML; scanned/proxied per policy |
| D26 | `policy_uri` points to phishing page | Shows third-party source warning and interstitial |
| D27 | `backchannel_logout_uri` points to internal address | Rejected by registration or dispatch policy |
| D28 | Metadata extension unsupported by converters | Rejected or dropped per schema; never silently trusted |
| D29 | Software statement signed by untrusted issuer | Rejected |
| D30 | Software statement expired/wrong audience/invalid signature | Rejected |
| D31 | JSON metadata conflicts with valid software statement | Statement precedence applied per OIDC DCR |
| D32 | Approved submission whose payload was altered | Payload digest/gate detects and rejects |
| D33 | Approval token expired or already used | Cannot create registration |
| D34 | Developer exceeds registration quota | Rate limit/quota rejects and logs audit |
| D35 | Registrar lacks permission for target tenant | Rejected |
| D36 | Client secret/registration token appears in logs | Security test catches redaction failure |
| D37 | Suspended/deprovisioned client still presents credentials | Rejected at authentication/policy layer |
| D38 | Registration access token leaked | Can revoke/rotate and audit the event |
| D39 | Metadata URL times out or returns error | Fails closed; never uses invalid cached data |
| D40 | Outbound fetch exceeds concurrency/response limit | Blocked by queue/rate/size guard |

### 11.2. Testing Through the HTTP Filter Chain

Validator unit tests are necessary but insufficient. Integration tests should:

1. Start a test Authorization Server with DCR enabled and a test registrar.
2. Obtain an access token with the policy-compliant `client.create` scope.
3. Send POST registration through the real HTTP filter chain.
4. Verify the response, `client_id`, registration access token, and persisted data.
5. Call Client Read with valid credentials.
6. Send requests with out-of-allowlist scopes, bad redirect URIs, and bad `jwks_uri` values.
7. Inspect status/error responses and confirm no unintended registration exists in the repository.
8. Confirm the initial access token cannot be used a second time.

For SSRF, use a controllable test DNS resolver/HTTP server to simulate public-to-private rebinding, redirect chains, IPv6, timeouts, and oversized responses. Never test by calling real production cloud metadata endpoints.

### 11.3. Testing Approval Races and Idempotency

Approval workflows require concurrency tests:

- Two requests using the same approval token create at most one registration.
- Two requests with the same digest do not exceed instance quotas if software policy allows only one instance.
- If an approval is revoked before registration commits, the request must fail.
- Payload tampering between review and submission must be detected.
- Two admins approving simultaneously must not create inconsistent state.
- Retries due to network timeouts must not create unintended duplicate clients.

Use transactions/unique constraints/atomic consumption for approval tokens and registration digests. Do not rely on single-node in-memory state checks.

## 12. Operations and Incident Response

### 12.1. Metrics and Auditing

Track at a minimum:

- Registration successes/failures by registrar, tenant, client type, and error code.
- Counts of pending/approved/rejected/expired registrations.
- Rejection rates for scopes/grants/auth methods.
- Requests exceeding rate limits/quotas.
- Outbound metadata fetch latency, timeouts, response sizes, redirect attempts, and SSRF policy rejections.
- DNS/IP policy results, egress firewall denials, and JWK Set parse failures.
- Credential issuance/rotation/revocation and client suspensions/deprovisioning.

Audit events should record actor, tenant, approval ID, client ID, metadata digest, policy version, decision, timestamp, and reason. Never store raw bearer tokens, client secrets, or JWK private key contents.

### 12.2. When an SSRF Attempt Is Detected

1. Reject the policy-violating registration/fetch.
2. Record hostname, resolved IPs, redirect chain, metadata type, and registrar identity.
3. Suspend the approval/registrar if there are signs of intentional abuse.
4. Inspect outbound firewall/proxy logs to see if the AS connected to any internal addresses.
5. If credentials/tokens may have been exposed, revoke related initial access tokens, registration access tokens, or client credentials.
6. Inspect JWK caches, authorization events, and any accessed internal services.
7. Update domain/IP deny policies and regression tests.

Never put full URLs containing token queries or credentials into public incident tickets. Redact user-info, query secrets, and headers before preserving evidence.

### 12.3. Suspending and Deprovisioning Clients

`RegisteredClient` describes a registered client; approval state and operational status may require a separate store. When a client is suspended:

- Issue no new tokens to the client.
- Block the client at the client authentication/authorization policy layer.
- Handle refresh tokens/authorization grants per incident policy.
- Stop outbound callbacks and unnecessary metadata fetches.
- Revoke the registration access token and credentials if compromised.
- Retain audit records per retention policy.

When deprovisioning, delete/disable the registration per your management mechanism, invalidate caches across all AS instances, and ensure old registration tokens can no longer read or modify the deleted registration.

## 13. Pre-Production Checklist

**Registration access**

- [ ] DCR enabled only when there is a clear use case and owner.
- [ ] Protected registration uses registrar identity and narrowly scoped initial access tokens.
- [ ] `client.create` tokens have TTL/one-time use/quotas and are bound to approval payloads.
- [ ] Client Read/management tokens are bearer secrets, protected, and rotatable/revocable.
- [ ] Rate limits and quotas enforced per tenant/registrar/client type.

**Metadata policy**

- [ ] Redirect URIs are validated for scheme/fragment and backed by domain ownership policy where needed.
- [ ] Grant types, response types, auth methods, and scopes have allowlists.
- [ ] DCR scopes do not use the permissive SIMPLE validator.
- [ ] `jwks_uri` is HTTPS-only and has an SSRF-safe fetch policy.
- [ ] `jwks`/`jwks_uri` do not appear together; JWK Sets contain public keys only.
- [ ] Custom metadata has schemas, converters, persistence, readback, and an owner.
- [ ] Software statements are trusted only after verifying issuer/signature/claims.

**SSRF defense**

- [ ] All metadata URLs with server-side fetchers are cataloged.
- [ ] DNS A/AAAA records are checked; private/reserved/loopback/link-local/metadata IPs are blocked.
- [ ] DNS results are pinned to the connection; no TOCTOU gap.
- [ ] Automatic redirects are disabled or every hop is re-validated.
- [ ] TLS hostname verification, timeouts, byte limits, content type checks, and concurrency limits are enabled.
- [ ] Egress firewall is deny-by-default and metadata fetch workers are isolated.
- [ ] Backchannel callbacks are validated at both registration-time and dispatch-time.

**Approval and operations**

- [ ] Approval state lives in an audited, transactional workflow.
- [ ] Payload digests are re-verified at registration time.
- [ ] Procedures exist for suspension, credential rotation, deprovisioning, and cache invalidation.
- [ ] Log redaction prevents leaking bearer tokens, client secrets, or private keys.
- [ ] Integration tests and SSRF regression tests cover every metadata fetch path.

## 14. References

- [RFC 7591 — OAuth 2.0 Dynamic Client Registration Protocol](https://www.rfc-editor.org/rfc/rfc7591.html): client metadata, initial access tokens, software statements, and security considerations.
- [RFC 7592 — OAuth 2.0 Dynamic Client Registration Management Protocol](https://www.rfc-editor.org/rfc/rfc7592.html): Client Read/Update/Delete and registration access tokens.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): OIDC metadata, `sector_identifier_uri`, and validation.
- [OpenID Connect Core 1.0 — Request Objects](https://openid.net/specs/openid-connect-core-1_0.html#RequestObjects): `request_uri` and Authorization Server fetching of Request Objects.
- [OpenID Connect Back-Channel Logout 1.0](https://openid.net/specs/openid-connect-backchannel-1_0.html): `backchannel_logout_uri` and server-to-server logout requests.
- [Spring Authorization Server 1.5.8 — How-to: Register a client dynamically](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-dynamic-client-registration.html): enabling the endpoint, initial access tokens, registering, and reading clients.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): `OidcClientRegistrationEndpointConfigurer`, providers, converters, and endpoint security.
- [Spring Authorization Server 1.5.8 API — OidcClientRegistrationAuthenticationValidator](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/oidc/authentication/OidcClientRegistrationAuthenticationValidator.html): DEFAULT and SIMPLE validators for redirect URIs, post-logout URIs, JWK Set URIs, and scopes.
- [OWASP Server-Side Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html): allowlists, DNS rebinding, redirect handling, private IP ranges, and egress defenses.

**Conclusion:** Dynamic Client Registration is a mechanism for issuing client identities and security configurations, not merely a JSON-writing API. Restrict who can register, bind approvals to exact approved metadata, allowlist grants/scopes/redirect URIs, protect registration credentials, and control every outbound request that may arise from metadata URLs. In Spring Authorization Server 1.5.8, the endpoint is disabled by default; the default validators provide a necessary baseline, yet `jwks_uri` only checks HTTPS, so SSRF defense still requires DNS/IP validation, redirect control, and network egress defense at fetch time.
