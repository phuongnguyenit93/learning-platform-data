# Testing tenant isolation and client registration and management permissions

A multi-tenant Authorization Server must ensure each tenant can manage only clients and data within its own scope. A missing authorization check in an admin API, a repository query lacking a tenant filter, or a cache using the wrong key can expose client configurations, allow altering redirect URIs, or expand scopes for another tenant.

Spring Authorization Server provides the `RegisteredClient`, `RegisteredClientRepository`, authorization, and consent models. It does not natively provide a tenant model or a complete client management workflow. The application must build the tenant context, map administrative permissions, persist client ownership relationships, and protect admin endpoints. Therefore, tests must cover APIs, services, databases, and the OAuth 2.0/OIDC flows that consume registered clients.

This lab builds a permission matrix, seeds data for two tenants, tests cross-tenant access, tests client registration and updates, and verifies that authorization/token flows cannot use another tenant's client. The examples provide an integration framework for applications; adapt endpoints, principals, and repositories to your actual architecture.

## 1. Objectives and threat model

Suppose a shared Authorization Server serves two tenants:

- `tenant-a` manages clients `portal-a` and `orders-a`.
- `tenant-b` manages clients `portal-b` and `orders-b`.
- `platform-admin` has system-wide administrative permissions.
- `tenant-admin` manages only its assigned tenant.
- `tenant-viewer` has read-only access to configurations within its assigned tenant.

Assets to protect include client details, hashed client secrets, redirect URIs, scopes, grant types, client authentication methods, token settings, authorizations, consents, and audit history. Behaviors to detect include:

- Tenant A reading, updating, deleting, or disabling Tenant B's client.
- Tenant A registering a client under Tenant B or assigning itself to another tenant.
- A tenant viewer performing administrative mutations.
- Unauthenticated callers invoking admin APIs.
- Tenant A's client resolving to Tenant B's client at the authorization/token endpoint.
- Caches, audits, background jobs, or bulk operations accidentally mixing data across tenants.
- Clients registered with redirect URIs, scopes, grant types, or authentication methods exceeding policy.

The goal is to test **permission on the action** and **permission on the specific target object**. Verifying only that the caller holds the `TENANT_ADMIN` role is insufficient; the server must also verify that the principal's tenant is authorized to manage the target client.

## 2. Permission matrix to test

A reference matrix:

| Action | Unauthenticated | Tenant viewer | Tenant admin (same tenant) | Platform admin |
|---|---:|---:|---:|---:|
| List clients in tenant | 401 | Allowed | Allowed | Allowed |
| View client details in tenant | 401 | Allowed | Allowed | Allowed |
| Create client in tenant | 401 | 403 | Allowed | Allowed |
| Update client configuration | 401 | 403 | Allowed | Allowed |
| Rotate client secret | 401 | 403 | Per special permission | Allowed |
| Disable or delete client | 401 | 403 | Per policy | Allowed |
| Manage another tenant's client | 401 | 403/404 | 403/404 | Allowed with audit |
| Modify global policy | 401 | 403 | 403 | Allowed |

`401 Unauthorized` indicates no authenticated identity is present; `403 Forbidden` indicates authenticated but lacking permission. For detail endpoints, the system may return `404 Not Found` when the tenant does not own the object to avoid disclosing the client's existence. Choose a consistent policy and verify both status and response body so client names, tenants, or statuses are never inadvertently leaked.

High-risk operations such as viewing client secrets, rotating credentials, changing sensitive redirect URIs, or granting privileged scopes may require dedicated permissions, step-up authentication, or dual approval. Never assume every `TENANT_ADMIN` is permitted to perform all operations.

## 3. Designing a trustworthy tenant context

The tenant context must originate from an identity authenticated and mapped by the server. For example, a principal may hold the subject, tenant ID, and authorities:

```java
public record TenantPrincipal(
        String subject,
        String tenantId) {
}
```

In practice, `tenantId` may be mapped from a verified Identity Provider claim, from database-stored membership, or from an authenticated administrative session. Validate issuer, audience, signature, token expiration, and membership status before trusting a tenant claim.

Never use a `tenantId` submitted by the caller in a JSON body, query string, or arbitrary header as the basis for authorization. If an API uses path `/admin/tenants/{tenantId}/clients`, the path value only identifies the requested target; the service must still compare it against the principal's tenant or verify platform admin permissions.

For platform admins, cross-tenant operations must explicitly specify the target tenant and be audited. For tenant admins, the target tenant must match the granted tenant. Never self-escalate permissions if the principal lacks a tenant ID or membership is no longer active.

### 3.1. Enforcing checks across multiple layers

Apply controls across the following layers:

1. **HTTP security:** require authentication and appropriate roles for admin endpoint groups.
2. **Method/service authorization:** verify permissions for the specific tenant and action.
3. **Data access:** query ownership and data scoped by the authenticated tenant; never skip checks by trusting a request-supplied ID.
4. **OAuth protocol resolution:** ensure clients are resolved within the proper issuer/tenant according to your deployment model.
5. **Side effects:** ensure audits, caches, events, jobs, and bulk operations preserve the right tenant context.

Protecting only the controller allows another job or service to call the repository directly and bypass rules. Configuration-mutating operations should pass through a domain service responsible for checking permissions and tenant ownership.

## 4. Considerations for RegisteredClientRepository and client identifiers

Spring Authorization Server's `RegisteredClientRepository` provides lookup methods by `client_id`, such as `findByClientId(String clientId)`. This interface does not accept `tenant_id` as a lookup parameter. Therefore, with a single Authorization Server and a shared issuer, the simple and safe choice is to keep `client_id` unique across the entire issuer and store client-to-tenant ownership separately.

Example extended data model:

```text
registered_client
  id (primary key)
  client_id (unique within issuer)
  ... RegisteredClient fields ...

registered_client_tenant
  registered_client_id (primary key, foreign key)
  tenant_id (foreign key)
  created_at
```

The ownership table is an application extension, not a default schema generated automatically by Spring Authorization Server. Foreign-key and unique constraints must guarantee a client belongs to its intended scope. When creating a client, save the Registered Client and ownership record in the same transaction.

If multiple tenants must reuse the same `client_id`, you must partition issuers or implement custom tenant resolution consistently across the authorization endpoint, token endpoint, introspection, revocation, and every path looking up Registered Clients. Merely adding `tenant_id` to a table while continuing to call tenant-unaware `findByClientId` is not enough. Two clients with the same ID under a shared issuer can cause confusion when Spring Authorization Server resolves clients from OAuth protocol requests.

With a single global issuer model, test the unique `client_id` constraint and verify protocol lookups cannot return another tenant's client due to ID collisions. With a per-tenant issuer/Authorization Server model, test issuer discovery, JWKS, client registration, and token validation per issuer.

## 5. Preparing the test application

Seed two tenants and at least two clients per tenant in the test database. Use the test environment's real `RegisteredClientRepository` alongside the application-managed ownership table. Data should include varied grant types, scopes, and client authentication methods to test configuration validation as well.

Example data:

| Tenant | Client ID | Type | Scopes |
|---|---|---|---|
| `tenant-a` | `portal-a` | Public client | `openid`, `profile` |
| `tenant-a` | `orders-a` | Confidential client | `orders.read` |
| `tenant-b` | `portal-b` | Public client | `openid`, `profile` |
| `tenant-b` | `orders-b` | Confidential client | `orders.read`, `orders.write` |

For public clients, verify there is no client secret and that the authorization code flow requires PKCE per policy. For confidential clients, secrets must be encoded before storage; admin API responses must never return stored secrets or hashes. If a client uses `private_key_jwt` or mTLS, expose only the public key reference or necessary certificate metadata.

Separate admin endpoints from authorization/token endpoints. Example admin endpoints:

```text
GET    /admin/tenants/{tenantId}/clients
GET    /admin/tenants/{tenantId}/clients/{clientId}
POST   /admin/tenants/{tenantId}/clients
PATCH  /admin/tenants/{tenantId}/clients/{clientId}
POST   /admin/tenants/{tenantId}/clients/{clientId}/rotate-secret
POST   /admin/tenants/{tenantId}/clients/{clientId}/disable
DELETE /admin/tenants/{tenantId}/clients/{clientId}
```

These are illustrative application endpoints, not built-in default admin endpoints of Spring Authorization Server.

## 6. Protecting admin endpoints

You can enable method security and enforce role rules at the HTTP layer. Abbreviated example:

```java
@Configuration
@EnableMethodSecurity
class AdminSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/admin/**")
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/admin/**")
                            .hasAnyRole("PLATFORM_ADMIN", "TENANT_ADMIN", "TENANT_VIEWER")
                        .requestMatchers(HttpMethod.POST, "/admin/**")
                            .hasAnyRole("PLATFORM_ADMIN", "TENANT_ADMIN")
                        .requestMatchers(HttpMethod.PATCH, "/admin/**")
                            .hasAnyRole("PLATFORM_ADMIN", "TENANT_ADMIN")
                        .requestMatchers(HttpMethod.DELETE, "/admin/**")
                            .hasRole("PLATFORM_ADMIN")
                        .anyRequest().authenticated())
                .build();
    }
}
```

This is only the coarse role layer. The service must still verify the specific tenant, secret rotation rights, and other special permissions. Order the admin filter chain properly so its matcher does not shadow the Authorization Server filter chain. If the admin API uses browser cookies/sessions, keep CSRF protection enabled and test CSRF tokens. Consider stateless/alternative CSRF handling only when authenticating via bearer tokens not automatically sent by browsers; never disable CSRF application-wide just to make API tests easier.

Example method authorization for reads and writes:

```java
@PreAuthorize("hasRole('PLATFORM_ADMIN') or " +
        "(hasAnyRole('TENANT_ADMIN', 'TENANT_VIEWER') and " +
        "@tenantAccess.canRead(authentication, #tenantId))")
public ClientView getClient(String tenantId, String clientId) {
    // Read client after verifying ownership.
}

@PreAuthorize("hasRole('PLATFORM_ADMIN') or " +
        "(hasRole('TENANT_ADMIN') and " +
        "@tenantAccess.canManage(authentication, #tenantId))")
public ClientView updateClient(String tenantId, String clientId,
                               UpdateClientCommand command) {
    // Update via domain service and record audit.
}
```

`tenantAccess` is an application-built bean. Expressions reference parameter name `#tenantId`; ensure your build preserves parameter names or uses annotations supporting parameter name binding for your Spring version. Do not treat annotations as a replacement for ownership checks at the query layer.

## 7. Testing with Spring Boot and MockMvc

Integration tests should run with the real security filter chain, services, and a test database. You can use Testcontainers with the same database engine as production to verify constraints, transactions, and tenant queries. Use test principals with explicit tenants rather than generic roles alone.

Example helper to construct Authentication:

```java
private RequestPostProcessor asPrincipal(String tenantId, String role) {
    TenantPrincipal principal = new TenantPrincipal(
            "admin-" + tenantId, tenantId);
    Authentication authentication = new UsernamePasswordAuthenticationToken(
            principal,
            null,
            List.of(new SimpleGrantedAuthority("ROLE_" + role)));

    return SecurityMockMvcRequestPostProcessors.authentication(authentication);
}
```

This helper assumes the application uses `TenantPrincipal` as its principal. If the real principal is a `Jwt`, `UserDetails`, or another type, construct the test Authentication matching the active resolver. Never mock the tenant context in a way that bypasses the production code under test.

### 7.1. Tenant A cannot read Tenant B's client

```java
@SpringBootTest
@AutoConfigureMockMvc
class ClientTenantIsolationIT {

    @Autowired
    MockMvc mockMvc;

    @Test
    void tenantAdminCannotReadAnotherTenantsClient() throws Exception {
        mockMvc.perform(get(
                        "/admin/tenants/{tenantId}/clients/{clientId}",
                        "tenant-b", "orders-b")
                .with(asPrincipal("tenant-a", "TENANT_ADMIN")))
            .andExpect(status().isNotFound());
    }
}
```

The example chooses `404` to conceal the existence of cross-tenant clients. If your API chooses `403`, adjust the assertion accordingly and verify the response contains no data belonging to client B. The test must run with client `orders-b` already existing; if the client does not exist to begin with, the test fails to prove tenant control.

### 7.2. Tenant A cannot update or delete Tenant B's client

```java
@Test
void tenantAdminCannotUpdateAnotherTenantsClient() throws Exception {
    String body = """
            {
              "clientName": "Compromised name",
              "scopes": ["orders.read", "orders.write"]
            }
            """;

    mockMvc.perform(patch(
                    "/admin/tenants/{tenantId}/clients/{clientId}",
                    "tenant-b", "orders-b")
            .with(asPrincipal("tenant-a", "TENANT_ADMIN"))
            .contentType(MediaType.APPLICATION_JSON)
            .content(body))
        .andExpect(status().isNotFound());

    mockMvc.perform(delete(
                    "/admin/tenants/{tenantId}/clients/{clientId}",
                    "tenant-b", "orders-b")
            .with(asPrincipal("tenant-a", "TENANT_ADMIN")))
        .andExpect(status().isNotFound());
}
```

After the requests, query the database to verify that `orders-b`'s `clientName`, scopes, status, and ownership remain unchanged. Also inspect audit/outbox logs: there must be no successful `CLIENT_UPDATED` or `CLIENT_DELETED` event created by Tenant A's actor. If denial events are recorded, they must contain only safe metadata.

### 7.3. Viewer cannot register or manage clients

```java
@Test
void viewerCannotRegisterClient() throws Exception {
    String body = """
            {
              "clientName": "New portal",
              "grantTypes": ["authorization_code"],
              "redirectUris": ["https://portal.example.test/callback"],
              "scopes": ["openid", "profile"]
            }
            """;

    mockMvc.perform(post("/admin/tenants/{tenantId}/clients", "tenant-a")
            .with(asPrincipal("tenant-a", "TENANT_VIEWER"))
            .contentType(MediaType.APPLICATION_JSON)
            .content(body))
        .andExpect(status().isForbidden());
}
```

Verify the database has no new client and no new ownership record. Repeat similarly for PATCH, disable, rotate-secret, and DELETE. A viewer may be allowed to view secret-redacted configurations, but must never view credentials or alter policies.

### 7.4. Tenant cannot spoof another tenant in the request body

```java
@Test
void tenantAdminCannotCreateClientForAnotherTenant() throws Exception {
    String body = """
            {
              "tenantId": "tenant-b",
              "clientName": "Injected client",
              "grantTypes": ["client_credentials"],
              "scopes": ["orders.read"]
            }
            """;

    mockMvc.perform(post("/admin/tenants/{tenantId}/clients", "tenant-b")
            .with(asPrincipal("tenant-a", "TENANT_ADMIN"))
            .contentType(MediaType.APPLICATION_JSON)
            .content(body))
        .andExpect(status().isNotFound());
}
```

The request uses both path and body to target `tenant-b`, while the principal belongs to `tenant-a`; the API returns `404` per the policy of hiding cross-tenant objects. If the API actively rejects a client-supplied `tenantId` field, it may return `400` before ownership checks. If the DTO ignores that field, the tenant must still be derived from the verified principal and path. In all cases, inspect the database to ensure no client belonging to Tenant B was created.

### 7.5. Platform admin can manage other tenants

```java
@Test
void platformAdminCanReadAnotherTenantsClient() throws Exception {
    mockMvc.perform(get(
                    "/admin/tenants/{tenantId}/clients/{clientId}",
                    "tenant-b", "orders-b")
            .with(asPrincipal("platform", "PLATFORM_ADMIN")))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.clientId").value("orders-b"))
        .andExpect(jsonPath("$.tenantId").value("tenant-b"));
}
```

Cross-tenant actions by a platform admin must audit the actor, target tenant, client ID, action, outcome, and reason per policy. Tests should confirm the audit record is written in the same transaction or via the outbox as designed.

## 8. Testing client registration rules

A tenant admin having permission to create clients does not mean they may create any arbitrary configuration. Test domain validation independently from role checks.

### 8.1. Redirect URI controls

- Allow redirect URIs only according to approved domain lists or rules.
- Reject wildcard hosts, insecure schemes, and URIs with anomalous user-info.
- Do not accept another tenant's redirect URI if policy requires domain partitioning.
- Match URIs strictly in authorization requests; never use arbitrary prefix matching.
- For native apps, apply dedicated redirect URI rules conforming to standards and platforms.

Include positive tests for valid URIs and negative tests for lookalike hosts, disallowed subdomains, `http` outside localhost, unexpected paths, and URIs with encoded characters attempting to bypass validation.

### 8.2. Scope and grant type controls

Tenant admins may assign only scopes within the tenant's allowlist or granted to the actor. Never allow a client to self-declare `admin`, `system`, `billing.write`, or internal scopes without approval. Grant types must match the client type: public clients typically use authorization code with PKCE; client credentials are reserved for confidential clients with appropriate client authentication.

Test:

- Valid scopes are persisted properly.
- Scopes outside the tenant or exceeding actor permissions are rejected.
- Public clients are not issued a client secret.
- Public clients require PKCE per policy.
- Confidential clients must have a valid client authentication method.
- Grant types disallowed for the tenant or client type are rejected.
- Token TTLs, refresh token reuse, and consent settings do not exceed maximum/minimum policy bounds.

### 8.3. Protecting client secrets and credentials

When creating a confidential client, secrets should be generated server-side or via a controlled credential-issuance workflow. Store secrets encoded with an appropriate `PasswordEncoder`; creation responses reveal the secret once only if the product requires it. GET/list/update APIs must never return secrets, hashes, or private keys.

Inspect response bodies, logs, and audit snapshots to guarantee no credentials appear. For `private_key_jwt`, store the public JWKS URL or public key metadata. For mTLS, store certificate identity/fingerprint per design. Never store a client's private key inside `RegisteredClient`.

## 9. Testing ownership in services and the database

MockMvc verifies HTTP security but is insufficient to catch database queries missing a tenant filter. Test domain services and repositories directly.

### 9.1. Services must verify both tenant and target object

A reference service flow:

```java
public RegisteredClient requireManagedClient(
        Authentication authentication,
        String requestedTenantId,
        String clientId) {

    boolean platformAdmin = authentication.getAuthorities().stream()
            .anyMatch(a -> a.getAuthority().equals("ROLE_PLATFORM_ADMIN"));

    TenantPrincipal principal = (TenantPrincipal) authentication.getPrincipal();

    if (!platformAdmin && !principal.tenantId().equals(requestedTenantId)) {
        throw new AccessDeniedException("Tenant access denied");
    }

    RegisteredClient client = registeredClientRepository.findByClientId(clientId);
    if (client == null) {
        throw new ClientNotFoundException();
    }

    ClientTenantOwnership ownership = ownershipRepository
            .findByRegisteredClientId(client.getId())
            .orElseThrow(ClientNotFoundException::new);

    if (!platformAdmin && !ownership.tenantId().equals(principal.tenantId())) {
        throw new ClientNotFoundException();
    }

    return client;
}
```

This is an illustrative example; handle principal types safely, check role/authority per action, and use consistent exception mapping. Even for platform admins, still verify that `requestedTenantId` exists and record an audit entry. Never allow callers to pass `platformAdmin=true` or `tenantId` in the body to alter the outcome.

### 9.2. Testing transactions during client registration

Create the Registered Client and ownership record within the same transaction. If saving ownership fails, the Registered Client must roll back as well. If a client ID already exists, the operation must fail without overwriting a client belonging to another tenant.

Database tests should verify:

- `client_id` is unique within a shared issuer scope.
- A Registered Client has only valid ownership according to the chosen tenant model.
- An ownership record cannot be created pointing to a nonexistent client.
- Tenant ownership cannot be changed through a routine client PATCH.
- Deleting a client and ownership obeys the same transaction and retention/audit policies.
- Concurrent updates do not lose ownership or overwrite newer configurations.

### 9.3. Testing query isolation

Seed data for tenants A and B, then query per tenant. Compare all returned IDs against the expected dataset. Test query variants: paginated lists, client-name searches, status filters, bulk exports, counts, autocomplete, and audit endpoints. Even a secondary endpoint forgetting a tenant filter can cause data leakage.

If the database supports row-level security, add database policy tests as an extra defense layer. Never use row-level security as a substitute for actor and tenant authentication in the application; transactions must set the tenant context accurately and reset it safely before returning connections to the pool.

## 10. Testing OAuth 2.0/OIDC flows

Client administration must align with how the Authorization Server resolves Registered Clients in protocol flows. Passing admin API tests while the token endpoint resolves the wrong client remains a critical flaw.

For every client of tenants A and B, test:

- Authorization requests accept only redirect URIs registered for that exact client.
- A client cannot swap `client_id` in requests to use another tenant's configuration.
- The token endpoint accepts only the registered client authentication method.
- Issued grant types and scopes stay within the client configuration and tenant policy.
- A disabled client cannot initiate new flows or obtain new tokens per policy.
- Consents and authorizations are never read or used across tenants.
- The Resource Server verifies issuer, audience, scopes, and tenant claims from trusted sources.

For the authorization code flow, send a request as client A while substituting client B's redirect URI; the server must reject it. Attempt swapping `client_id` from `portal-a` to `portal-b` during token exchange; a code issued to client A cannot be exchanged by client B. For client credentials, using client B's secret with client A's `client_id` must fail.

If each tenant has a dedicated issuer, verify that tokens from issuer A are rejected by Tenant B's Resource Server, even when subject or client names match. If a shared issuer includes a tenant claim, that claim must be issued by the Authorization Server and validated by the Resource Server per policy; never trust tenant IDs from API request inputs.

## 11. Testing caches, audits, and background jobs

Tenant isolation can break outside the request/response path:

- Caching clients by `client_id` without including tenant or issuer in the cache key when architecture requires partitioning.
- Background jobs fetching a global client list and acting under the wrong tenant.
- Messages/events missing a tenant ID or trusting a tenant ID from an untrusted payload.
- Audit records logging the wrong tenant or audit search endpoints failing to filter by permissions.
- Export files containing clients from multiple tenants sent to a single tenant's admin.
- Metrics/logs tagged with the wrong tenant, masking anomalous activity.

Test caches by reading client B via a valid platform admin context, then invoking the same code path as tenant A and confirming the cache does not return B's data. Test cache invalidation after a client is disabled or changes state. If caching per issuer, the issuer must be part of the cache key.

For event-driven workflows, verify consumers validate tenant ownership from trusted data before processing. Never treat a message broker payload as proof of authorization. For audits, inspect actor, tenant, target, outcome, and redacted before/after snapshots; tenant admins may query audits only within their own tenant.

## 12. Minimum security test suite

| ID | Test case | Expected outcome |
|---|---|---|
| TEN-01 | Anonymous caller invokes admin API | 401 |
| TEN-02 | Viewer reads same-tenant client | 200, no secret |
| TEN-03 | Viewer creates/updates/deletes client | 403, database unchanged |
| TEN-04 | Tenant admin reads same-tenant client | 200 |
| TEN-05 | Tenant admin reads another tenant's client | 403 or 404 per policy, no data leaked |
| TEN-06 | Tenant admin updates/deletes another tenant's client | Rejected, no side effects |
| TEN-07 | Tenant admin sends spoofed tenant ID in body/header | Rejected or ignored; ownership remains intact |
| TEN-08 | Platform admin manages another tenant | Allowed per policy and audited |
| CLI-01 | Create client with valid scopes/grants | Persisted under right tenant |
| CLI-02 | Create client with ungranted privileged scope | 400/403 per policy |
| CLI-03 | Redirect URI outside allowlist | Rejected |
| CLI-04 | Duplicate client ID within same issuer | Rejected, no overwrite |
| CLI-05 | Ownership save fails after saving client | Entire transaction rolls back |
| CLI-06 | Public client sends secret or omits PKCE | Rejected per policy |
| OAU-01 | Use client A with client B's redirect URI | Authorization request rejected |
| OAU-02 | Exchange client A's authorization code as client B | Token endpoint rejects |
| OAU-03 | Use client B's secret with client A's ID | Client authentication fails |
| OAU-04 | Disabled client requests new token | Rejected per policy |
| DAT-01 | List/search/export clients | Only authorized tenant's data returned |
| DAT-02 | Cache warmed by platform admin then read by tenant admin | No cross-tenant data leakage |
| DAT-03 | Query another tenant's audit logs | Rejected or returns 404 |
| DAT-04 | Background job processes event lacking valid tenant | Performs no changes |

## 13. Acceptance criteria and bug reporting

A security test case must verify more than HTTP status:

- **No data leakage:** responses contain no unauthorized client names, redirect URIs, scopes, secrets, or tenant metadata.
- **No side effects:** databases, caches, messages, audits, and client states are not modified improperly.
- **Proper auditing:** allowed actions are recorded; rejected actions may be recorded per policy without sensitive payloads.
- **No bypass paths:** services, repositories, jobs, and protocol endpoints all enforce the same tenant rules.
- **Repeatability:** test fixtures create deterministic data and clean up safely without depending on production data.

When reporting a flaw, include endpoint/operation, role, actor's tenant, target's tenant, seed data, credential-scrubbed request, response, before/after database state, and correlation ID. Never attach real client secrets, access tokens, or cookies.

## 14. Common design flaws

| Flaw | Consequence | Fix |
|---|---|---|
| Checking only role `TENANT_ADMIN` | Tenant A admin can manipulate Tenant B's objects | Verify tenant ownership on every object |
| Trusting `tenantId` in request body | Caller self-assigns target tenant | Derive tenant from authenticated principal and validate path |
| Filtering tenants only in UI | API can be called directly to read other tenants | Enforce at server/service/repository layers |
| Using `findByClientId` while allowing duplicate IDs across tenants in same issuer | Protocol can resolve the wrong client | Use globally unique client IDs or separated issuer/repository resolvers |
| Writing Registered Client and ownership in separate transactions | Orphaned clients or broken ownership | Use a single transaction and constraints |
| Cache key missing issuer/tenant | One tenant's data served to another tenant | Design cache keys along identity boundaries |
| Testing only controllers with mocked repositories | Misses query, constraint, and transaction bugs | Integration tests with a real test-environment database |
| Returning client secrets in responses | Credentials exposed via API/logs | Reveal once on creation; never return in GET/list |
| Skipping OAuth flow tests | Admin API works while token endpoint resolves wrong client | Test authorization, token, consent, and resource access across tenants |

## Conclusion

Testing tenant isolation must prove that an actor reads and modifies only objects within their granted scope. Combine role authorization with tenant ownership, protect both admin APIs and OAuth flows using `RegisteredClient`, and inspect databases, caches, audits, and background jobs for leakage paths. With a shared issuer, `client_id` must be unique per issuer because the standard repository looks up by client ID; if duplicate identifiers across tenants are required, design issuer partitioning or custom resolution throughout the protocol. A solid test suite confirms both that unauthorized requests are rejected and that no data or side effects cross tenant boundaries.
