# Protecting APIs by Role and Resource Ownership in Spring Data REST

A secure API must answer two questions on every request: is the caller allowed to perform this action, and are they allowed to operate on the specific resource targeted? Role-based access control (RBAC) addresses the first question. Ownership or per-object authorization checks address the second.

In Spring Data REST, a repository can automatically become collection, item, search, and association resources. Consequently, securing a single URL or controller is not enough: the same entity can be accessed through multiple paths and HTTP methods. Design authorization across the request layer, repository/service layer, and data queries; then test with accounts holding different roles and ownership.

## 1. Roles and Ownership Address Two Distinct Risks

| Control Type | Question | Example |
|---|---|---|
| Role/capability | Is the user allowed to invoke this function? | Only ADMIN can delete documents; USER can read documents |
| Resource-level permission | Does the user have permission for this specific record? | Alice can only read or edit documents owned by Alice |
| Data/tenant scope | Does the resource belong to the tenant or group the user belongs to? | Members of tenant A cannot view tenant B's data |
| Relationship permission | Can the user link, unlink, or read linked resources? | Only the project owner may add members to the project |

If `GET /documents/{id}` only checks for the USER role, any USER can swap IDs to read another user's document. This is Broken Object Level Authorization (BOLA), also commonly known as IDOR. Neither sequential IDs nor UUIDs substitute for authorization checks. Every endpoint accepting an ID or object reference from a path, query, header, body, or HAL link must enforce permissions on that specific object.

A sample permission matrix:

| Action | USER (Owner) | USER (Non-Owner) | ADMIN |
|---|---:|---:|---:|
| Read item | Allow | Deny | Allow |
| List own resources | Allow | Only own data | Allow per policy |
| Create resource | Allow, server assigns owner | Not applicable | Allow |
| Update resource | Allow editable fields | Deny | Allow |
| Delete resource | Per policy, e.g. deny | Deny | Allow |
| Change owner/tenant | Deny | Deny | Dedicated admin workflow only |

This is an example only. Explicitly define read, create, update, delete, share, and relationship management permissions for each resource type; never infer that read permission implies edit or delete permission.

## 2. Defense in Depth Across Layers

A common layered structure:

1. **Request authorization:** Spring Security authenticates requests and restricts routes requiring specific roles or authentication.
2. **Method authorization:** `@PreAuthorize` protects repository/service methods; expressions can inspect roles, parameters, principals, and entity permissions.
3. **Query scope:** queries return only records the user is permitted to see, such as filtering by owner or tenant derived from Authentication.
4. **Domain invariants:** owner, tenant, and sensitive fields are assigned or verified on the server; clients cannot transfer ownership themselves.
5. **Testing and auditing:** test both valid requests and malicious attempts to tamper with IDs, owners, relations, or query parameters.

Request authorization blocks unauthorized route groups early. Method authorization protects business logic when the same service is called from REST, background jobs, or other flows. Query scoping reduces data exposure risks in collection/search endpoints and avoids loading entire tables only to filter afterward.

Never rely on hard-to-guess URLs as access control. Never trust `ownerId`, `tenantId`, roles, or usernames supplied in JSON. Trusted identity must come from the verified `Authentication`/principal.

## 3. Configuring Spring Security for HTTP Requests

The Spring Boot Security starter does not enable method security automatically. You must declare `@EnableMethodSecurity` for `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`.

The example below assumes Spring Data REST uses base path `/api`. Adjust matchers to match your application's actual base path and routes:

```java
@Configuration
@EnableMethodSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .build();
    }
}
```

With default role configuration, `hasRole("ADMIN")` checks for authority `ROLE_ADMIN`; `hasRole("USER")` checks for `ROLE_USER`. If using granular permission strings, use `hasAuthority("document:read")` or `hasAuthority("document:write")` for exact authority matching. Do not manually prepend `ROLE_` when calling `hasRole`.

Matchers must be ordered from most specific to most general. The fallback rule should require `authenticated` or `denyAll` so newly added routes are not accidentally exposed publicly. Request matchers only check route/capability access; they do not automatically verify that the caller owns the ID in the URL.

If your application uses JWT/resource server, HTTP Basic, or form login, configure the authentication mechanism suited to your environment. For token-based APIs, return 401/403 per your published JSON contract; do not force API clients to deal with unexpected HTML redirects.

Do not disable CSRF blindly. For browsers using cookies/sessions, keep CSRF protection enabled for state-changing requests. If the API uses stateless bearer tokens, evaluate CSRF settings based on whether browsers automatically attach credentials and your actual authentication architecture. CORS only governs which browser origins may send requests; CORS is not authorization and does not replace ownership checks.

## 4. Enabling Method Security and Protecting Exported Repositories

Spring Data REST supports Spring Security method security at both the repository interface level and individual method level. You can place `@PreAuthorize` on the repository or on methods. According to Spring Data REST documentation, method-level annotations override repository-level annotations; the two expressions do not combine automatically. Therefore, when overriding a method, write the complete required condition in the new expression.

Example using default-deny and selectively opening specific methods. Assumes entity `Document` has an `owner.username` relationship, UUID primary keys, and the repository is exported at `/api/documents`:

```java
@RepositoryRestResource(path = "documents")
@PreAuthorize("denyAll")
public interface DocumentRepository
        extends JpaRepository<Document, UUID> {

    @Override
    @PreAuthorize("hasRole('ADMIN') or " +
        "(hasRole('USER') and " +
        "@documentAuthorization.isOwner(#id, authentication.name))")
    Optional<Document> findById(@P("id") UUID id);

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    Page<Document> findAll(Pageable pageable);

    @RestResource(path = "by-owner", rel = "by-owner")
    @PreAuthorize("hasRole('ADMIN') or " +
        "(hasRole('USER') and #username == authentication.name)")
    Page<Document> findByOwner_Username(
        @Param("username") String username,
        Pageable pageable
    );

    @RestResource(exported = false)
    @PreAuthorize("hasAnyRole('USER', 'ADMIN')")
    @Override
    <S extends Document> S save(@P("document") S document);

    @RestResource(exported = false)
    @PreAuthorize("hasAnyRole('USER', 'ADMIN')")
    boolean existsByIdAndOwner_Username(
        @Param("id") UUID id,
        @Param("username") String username
    );

    @Override
    @PreAuthorize("hasRole('ADMIN')")
    void deleteById(@P("id") UUID id);
}
```

In this example:

- `@PreAuthorize("denyAll")` on the repository blocks any method not explicitly opened. `findAll(Pageable)` is restricted to ADMIN; USER queries via owner-scoped search.
- `findById` permits ADMIN or a USER who owns that specific ID.
- Search `/api/documents/search/by-owner?username=alice` only lets Alice view Alice's data; ADMIN can view any username. Never accept a client-supplied username without an authorization check verifying it.
- `save` is hidden from Spring Data REST using `@RestResource(exported = false)`, while remaining callable internally from secured services. `existsByIdAndOwner_Username` is also not exported; it exists solely to support ownership checks.
- Any other methods without dedicated annotations remain blocked by `denyAll`. To expose additional APIs, add explicit rules for each method.

`@P` from `org.springframework.security.access.method.P` and Spring Data's `@Param` bind parameter names for SpEL expressions such as `#id` and `#username`. Standard Java parameter names can work if compiled with `-parameters`, but explicit annotations keep interfaces readable and independent of compiler flags.

Example ownership-checking bean:

```java
@Component("documentAuthorization")
@RequiredArgsConstructor
public class DocumentAuthorization {

    private final DocumentRepository documents;

    public boolean isOwner(UUID id, String username) {
        return documents.existsByIdAndOwner_Username(id, username);
    }
}
```

The property name `Owner_Username` traverses the `owner.username` relationship in a Spring Data derived query. Adjust it to match your real entity field names. `existsByIdAndOwner_Username` is marked `exported = false` so the authorization helper does not become a public search endpoint.

This example opens item reads and owner-scoped queries, and lets ADMIN read the collection and delete by ID. Undeclared methods remain blocked. Whenever adding `saveAll`, `delete`, `deleteAll`, `deleteAllById`, batch operations, or custom modifying queries, explicitly decide permissions for every method. Never assume only one write/delete path exists. Methods inherited from `CrudRepository`/`JpaRepository` vary by Spring Data version; inspect the interfaces your application uses and lock down every unauthorized mutation path.

## 5. Checking Ownership in Services and Securing Writes

For complex business logic, enforce ownership in the service layer and have controllers call the service. If Spring Data REST still directly exports the repository, REST requests can invoke the repository proxy without passing through your service. In that case, either secure the repository methods directly or hide their export and expose custom endpoints.

Example service allowing only the owner or ADMIN to update the title:

```java
@Service
@RequiredArgsConstructor
public class DocumentService {

    private final DocumentRepository documents;
    private final UserRepository users;

    @Transactional
    @PreAuthorize("hasRole('ADMIN') or " +
        "(hasRole('USER') and " +
        "@documentAuthorization.isOwner(#id, authentication.name))")
    public Document update(
            @P("id") UUID id,
            UpdateDocumentRequest request) {

        Document document = documents.findById(id)
            .orElseThrow(() -> new EntityNotFoundException());

        document.setTitle(request.title());
        // DTO does not contain ownerId or tenantId.
        return documents.save(document);
    }

    @Transactional
    @PreAuthorize("hasRole('USER')")
    public Document create(
            CreateDocumentRequest request,
            Authentication authentication) {

        Document document = new Document();
        document.setTitle(request.title());
        document.setOwner(
            users.findByUsername(authentication.getName())
                .orElseThrow(() -> new EntityNotFoundException())
        );
        return documents.save(document);
    }
}
```

In this example, repository `save` is an internal method hidden from REST and callable only by authorized roles. Write endpoints should be implemented with `@RepositoryRestController` if they belong under the Spring Data REST base path, or with `@RestController` on a separate route. Controllers accept only DTOs containing fields clients are permitted to change and then delegate to the service.

Key principles for write operations:

- **Create:** the server obtains the user/tenant from Authentication and assigns ownership itself. Ignore or reject client-sent `ownerId`/`tenantId`.
- **Update/PATCH:** load or query the record within the caller's scope; verify ownership before mutating. DTOs must contain only editable fields rather than binding directly to the entire entity.
- **Immutable owner/tenant:** disallow changing owner or tenant via PATCH/PUT. Ownership transfer should be a separate use case with administrative privileges and auditing.
- **Delete:** verify role and ownership on the target record; do not rely solely on URL-level role checks.
- **Bulk:** verify permissions for each ID or scope queries by tenant/owner; a multi-ID request must never leak or delete out-of-scope resources.
- **Associations:** when linking/unlinking relations via HAL links, check permissions on both the parent resource and the linked resource.

Spring Data REST provides `BeforeCreate`, `BeforeSave`, `BeforeLinkSave`, `BeforeLinkDelete`, and related events. `@RepositoryEventHandler` with `@HandleBeforeCreate`/`@HandleBeforeSave` can assign owner from the principal or prevent owner changes. Event handlers enforce invariants for operations going through the REST exporter; method/service authorization is still required because services may be invoked outside the REST event pipeline.

If using `@PostAuthorize` to inspect returned objects, remember the method has already executed and data may have been loaded before access is denied. For large collections, avoid `@PostFilter` loading entire lists only to filter them in memory. Prefer database queries already scoped by owner/tenant. `@PostAuthorize` suits certain post-return item checks; `@PreAuthorize` or scoped queries are clearer when blocking access upfront.

## 6. Securing Every Access Path to a Resource

An entity can be reached through multiple resources in Spring Data REST. Inventory and verify every path below:

| Access Path | What to Check |
|---|---|
| API root and collections | Which links/rels are published; whether GET collection filters by owner/tenant or restricts to ADMIN |
| Item resource | Whether GET, PUT, PATCH, DELETE check both ID and owner |
| Search resource | Whether each query method enforces role and owner conditions; prevent changing username/tenant to read others' data |
| Association resource | Whether GET association, PUT/PATCH link, DELETE link check permissions on both sides |
| Custom controller | Whether it shares the same service/policy; avoid routes bypassing repository security |
| Batch/import/jobs | Whether permissions are checked in services; system jobs have explicit identity and scope |
| Projections/excerpts | Do not leak sensitive fields; projections are not an authorization mechanism |
| HAL links | Presence of a link does not imply permission; requests following links must still enforce authorization |

Never treat hiding links in HAL, projections, or UI as security. Clients can craft URLs manually and send requests directly. Enforcement must happen on the server at execution time.

If you want to avoid revealing whether a resource exists, an application can choose to return 404 both when a record does not exist and when the caller lacks access. If distinguishing existing-but-forbidden resources is preferred, return 403. Choose one consistent policy across the API and ensure response differences do not inadvertently leak information.

## 7. Matrix-Based Authorization Testing

Tests should include at least two distinct USERs (Alice and Bob), an ADMIN, and unauthenticated requests. Create two resources with different owners; use Alice's ID to test requests as Alice, Bob, and ADMIN.

Example with MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class DocumentAuthorizationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void ownerCanReadDocument() throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId)
                .accept("application/hal+json"))
            .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "bob", roles = "USER")
    void anotherUserCannotReadDocument() throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId)
                .accept("application/hal+json"))
            .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanReadDocument() throws Exception {
        mvc.perform(get("/api/documents/{id}", aliceDocumentId)
                .accept("application/hal+json"))
            .andExpect(status().isOk());
    }
}
```

The IDs in the example are fixtures prepared beforehand by the test. If the application adopts a policy of hiding unauthorized resources, Bob's assertion should expect 404 instead of 403.

The test suite should cover:

- Anonymous calls to private APIs: 401 or the published authentication challenge response.
- USER calling ADMIN-only functionality: 403.
- Alice reading/updating/deleting Alice's own resources per policy: expected success.
- Bob using Alice's ID with GET, PUT, PATCH, and DELETE: rejected.
- Bob altering `username`, `ownerId`, `tenantId`, or nested relations in queries/bodies: cannot escalate access.
- USER querying collections/search: receives only records within their own scope.
- ADMIN operating on resources per administrative permissions.
- Requests attempting to modify owner/tenant are rejected or those fields are not bound.
- Association links cannot bind resources belonging to another tenant.
- Batch requests mixing valid and out-of-scope IDs produce well-defined outcomes without unintended partial execution.
- Projections and error responses do not expose sensitive fields.

Use `@WithMockUser(username = "alice", roles = "USER")` to run method/service tests. With MockMvc, you can also pass `with(user("alice").roles("USER"))` per request. When CSRF is enabled, POST/PUT/PATCH/DELETE test requests need a valid token such as `with(csrf())`. If tests send real HTTP requests to a live `RANDOM_PORT` server, requests execute on a separate thread; `@WithMockUser` on the test thread does not automatically propagate Authentication to the server. Send real test credentials/tokens over HTTP in that setup.

A test calling a service directly only proves service-level method security. A MockMvc test proves the filter chain, route mapping, and method security work together over HTTP. Include both for critical flows.

## 8. Common Security Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| USER reads another USER's resource | Only checked authenticated or role, missing owner check | Add object-level checks in method/service or scoped queries |
| Collection GET returns everyone's data | `findAll` is unrestricted; only item endpoint was secured | Block general `findAll` and expose queries/services scoped to the caller |
| Search query crosses tenant boundaries | Client passes arbitrary owner/tenant and server trusts it directly | Compare against principal or derive tenant from Authentication in service |
| Added `@PreAuthorize` has no effect | `@EnableMethodSecurity` missing, bean not Spring-managed, or internal self-invocation | Enable method security; call through Spring proxy; verify with integration tests |
| Method override drops class-level roles | Method-level annotation overrides class-level rather than merging | Repeat the complete condition in the method annotation |
| One delete path still works | Only `deleteById` was secured while `delete`, `deleteAll`, or bulk/custom queries remain open | Default-deny and explicitly permit each mutation signature in the active repository interfaces |
| Owner gets overwritten via PATCH | DTO/entity binding accepts owner field from client | Use allowlisted DTOs; set owner server-side; enforce in BeforeSave and services |
| Internal search helper exposed as REST endpoint | Internal derived query published by exporter | Add `@RestResource(exported = false)` to the helper |
| Association endpoint bypasses permissions | Permissions checked only on parent or item route | Check both parent and target permissions on link reads and edits |
| Service tests pass but REST remains open | Repository exporter invokes repository directly, bypassing service | Secure repository methods or hide export and route through controller/service |
| Tests use `@WithMockUser` but live server returns 401 | SecurityContext only exists on the test thread | Send Basic/Bearer credentials in HTTP requests to the live server |
| API returns 500 instead of 403 | `AccessDeniedException` mishandled or custom exception handler interferes | Check filter chain and exception translation; assert real HTTP status via MockMvc |

## 9. Implementation Checklist

- [ ] Defined a role × resource × action matrix for each entity type.
- [ ] All private requests require authentication and routes follow deny-by-default authorization.
- [ ] Method security is enabled with `@EnableMethodSecurity`.
- [ ] Repository/service methods verify permissions on the specific target resource.
- [ ] Collection and search queries are scoped by owner/tenant derived from the principal.
- [ ] Inherited CRUD, bulk, and custom modifying methods are inventoried; unpermitted methods remain blocked.
- [ ] Create assigns owner/tenant server-side; update prevents clients from changing owner/tenant.
- [ ] Associations, search, projections, custom controllers, and batch endpoints are all checked.
- [ ] Authorization never relies on UUIDs, obscure URLs, hidden links, or UI hiding.
- [ ] Cross-user tests cover Alice/Bob/ADMIN and anonymous calls for GET, POST, PUT, PATCH, DELETE, search, and associations.
- [ ] Tests verify both HTTP status codes and returned payloads, confirming no out-of-scope data leakage.
- [ ] CORS, CSRF, authentication, and 401/403 responses match the real client model.
- [ ] Logs/audits record principal, action, resource ID, and outcome without logging tokens or secrets.

## 10. Official Documentation

- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html) — examples of `@PreAuthorize`/`@Secured` directly on repositories and enabling method security.
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html) — `BeforeCreate`, `BeforeSave`, `BeforeLinkSave`, `BeforeLinkDelete`, and `@RepositoryEventHandler`.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) — request matchers, roles/authorities, and fallback rules.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html) — `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, `@PostFilter`, custom authorization beans, and SpEL parameters.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html) — `AuthorizationManager` and decision architecture.
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html) — `@WithMockUser`, `@WithUserDetails`, and testing method authorization.
- [Spring Security — MockMvc Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/) — integrating Spring Security with MockMvc.
- [Spring Security — Running a Test as a User in MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html) — `user()` request post-processor and mock users.
- [Spring Security — Testing with CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) — adding CSRF tokens for state-changing requests.
- [OWASP API Security Top 10: API1 Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/) — risks when APIs accept IDs without verifying object-level permissions.
- [OWASP Web Security Testing Guide: API BOLA](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/12-API_Testing/02-API_Broken_Object_Level_Authorization/) — methodology for testing ID tampering and authorization across endpoints.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html) — core principles for securing REST APIs.