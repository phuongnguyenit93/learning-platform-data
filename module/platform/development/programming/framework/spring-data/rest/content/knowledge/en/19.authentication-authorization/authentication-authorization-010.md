# Protecting Sensitive Fields Across JSON, Projections, and Association Links in Spring Data REST

## Objective

Spring Data REST can automatically export entities as JSON/HAL resources. This accelerates API creation, but it also means properties in your domain model can become part of the HTTP contract unless controlled.

Data protection must be applied across multiple layers:

1. **Serialization:** deciding which fields are allowed to appear in JSON.
2. **Deserialization:** deciding which fields clients are allowed to send and modify.
3. **Projections and excerpts:** controlling optional representations clients can request.
4. **Association links:** controlling data and operations exposed via relationship URIs.
5. **Authorization:** deciding who may read, create, update, or delete each resource.

Do not treat `@JsonIgnore`, projections, or hiding a link as a complete authorization mechanism. A field hidden in the default representation may reappear through a projection; an endpoint without a link in HAL can still be called directly if the route remains exported and lacks proper authorization.

## 1. Identifying sensitive data in the domain model

For example, a User entity often contains data that needs protection:

~~~java
@Entity
public class User {

    @Id
    @GeneratedValue
    private Long id;

    @Column(nullable = false, unique = true)
    private String username;

    private String displayName;

    @JsonIgnore
    private String passwordHash;

    @JsonIgnore
    private String resetToken;

    @JsonIgnore
    private String internalNote;

    @ElementCollection
    private Set<String> roles = new HashSet<>();

    // getters and setters
}
~~~

Fields to review before exporting:

- Passwords, password hashes, API keys, access tokens, refresh tokens, and reset tokens.
- System integration secrets, private keys, or credential material.
- Internal notes, risk control flags, operational data, and audit metadata.
- Personal information such as phone numbers, private emails, addresses, or birth dates if not meant to be public in the API.
- Tenant IDs, owner IDs, roles, and permissions if clients must not modify them directly.
- Technical fields such as moderation status, payment status, or internal flags.

Build an allowlist of fields to expose for each use case. Never assume every field on an entity is safe merely because the current UI does not display it.

## 2. Using @JsonIgnore to exclude fields from default JSON

Jackson's `@JsonIgnore` prevents a property from being serialized in the standard representation:

~~~java
@Entity
public class User {

    @Id
    private Long id;

    private String username;

    @JsonIgnore
    private String passwordHash;
}
~~~

Spring Data REST honors `@JsonIgnore` on fields or corresponding getters when building the default representation. Example response without passwordHash:

~~~json
{
  "id": 12,
  "username": "lan",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/users/12"
    }
  }
}
~~~

You can use `@JsonIgnoreProperties` when ignoring multiple properties at the class level:

~~~java
@JsonIgnoreProperties({
    "passwordHash",
    "resetToken",
    "internalNote"
})
@Entity
public class User {
    // ...
}
~~~

However, `@JsonIgnore` is only a JSON mapping rule. It does not:

- Authenticate the caller.
- Check whether the user is permitted to read the entity.
- Protect a custom controller using a different DTO or ObjectMapper.
- Stop a projection from explicitly declaring a getter for the hidden property.
- Automatically prevent mass assignment or field modification across all write paths.

Therefore, use annotations to trim default serialization, and separately control projections, input binding, and authorization.

## 3. Projections can expose fields hidden by @JsonIgnore

This is a particular risk in Spring Data REST. Projections define a representation through interface getters. A projection can declare a getter for a field that the entity marked `@JsonIgnore`.

Example entity:

~~~java
@Entity
public class User {

    @Id
    private Long id;

    private String username;

    @JsonIgnore
    private String passwordHash;
}
~~~

Unsafe projection:

~~~java
@Projection(name = "userSecrets", types = User.class)
public interface UserSecretsProjection {

    String getUsername();

    String getPasswordHash();
}
~~~

If the projection is registered and a client calls:

~~~http
GET /api/users/12?projection=userSecrets
Accept: application/hal+json
~~~

then the getter on the projection can bring passwordHash back into the response, bypassing the intent of hiding the field with `@JsonIgnore`.

Spring Data REST cannot automatically classify which data is business-sensitive. Auditing getters and nested projections is the development team's responsibility.

**Rule:** never declare getters for secrets in any public projection, even projections intended only for internal use. If a projection can be selected by a client over HTTP or appears in ALPS metadata, treat it as part of the public API.

A safe projection should declare only fields permitted to be read:

~~~java
@Projection(name = "userSummary", types = User.class)
public interface UserSummary {

    String getUsername();

    String getDisplayName();
}
~~~

Place projection interfaces in the same package or a sub-package of the domain type for Spring Data REST discovery, or register them manually. Register only audited projections.

## 4. Controlling excerptProjection

An excerpt is a projection automatically applied when Spring Data REST embeds item resources inside collections or related resources.

Example:

~~~java
@RepositoryRestResource(
    path = "users",
    excerptProjection = UserSummary.class
)
public interface UserRepository
        extends JpaRepository<User, Long> {
}
~~~

When querying the collection, each embedded User uses the UserSummary projection. This helps constrain default list payloads.

However, an excerpt is not authorization:

- It does not decide which users can read the collection.
- It does not prevent clients from reading the item resource directly.
- It does not stop clients from requesting another exported projection.
- It does not protect association endpoints.
- It does not guarantee sensitive fields stay absent in custom controllers.

An excerpt also does not automatically apply to standalone item resources. Clients can request a specific projection via query parameter if that projection is exposed.

Before configuring an excerpt, review both automatically applied projections and projections clients can explicitly request.

## 5. Nested projections and related data

Projections can include related objects in the response. For example, User has a Profile:

~~~java
@Projection(name = "userProfile", types = User.class)
public interface UserProfileView {

    String getUsername();

    ProfileSummary getProfile();
}

@Projection(name = "profileSummary", types = Profile.class)
public interface ProfileSummary {

    String getDisplayName();

    String getPublicBio();
}
~~~

Nested projections help include only required fields from Profile in the response. However, if Profile contains private addresses, birth dates, payment info, or internal data, do not add getters for those fields merely for client convenience.

With an excerpt containing nested associations, related data can be embedded directly inside collection responses. A sensitive field can surface through multiple paths:

- The User item resource.
- A User projection.
- A User excerpt.
- A nested Profile projection.
- The Profile association resource.
- An independently exported Profile repository.

Inspect every accessible representation path, not just one sample response.

## 6. JSON annotations for read and write access

Jackson supports `@JsonProperty(access = ...)` to control the serialization/deserialization direction of a property.

~~~java
public class AccountRequest {

    @JsonProperty(access = JsonProperty.Access.READ_ONLY)
    private String accountNumber;

    @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
    private String newPassword;
}
~~~

Two main modes:

| Access mode | Response JSON | Request JSON |
| --- | --- | --- |
| READ_ONLY | Can serialize | Ignored during deserialization |
| WRITE_ONLY | Not serialized | Can deserialize |
| READ_WRITE | Serialized and deserialized | Serialized and deserialized |
| AUTO | Per default visibility | Per default visibility |

For example, clients can send newPassword in requests while the server never returns that field in responses. Even so, passwords should be handled in a command DTO and hashed with PasswordEncoder; never store raw passwords directly on entities or in logs.

With Spring Data REST, test annotations against your application's actual ObjectMapper/exporter. Projections and custom serializers can alter representations. Do not use access modes as a per-user authorization mechanism.

For fields like role, ownerId, tenantId, balance, or payment status, marking them READ_ONLY is still insufficient if another endpoint can write them. Prefer DTO/command allowlists and service-level business validation.

## 7. DTOs and command models to control input

JPA entities often contain more fields than a client is permitted to change. If Spring Data REST binds request JSON directly onto entities, exporting a repository can expose more writable properties than intended.

For example, clients should not freely submit:

~~~json
{
  "username": "lan",
  "roles": ["ROLE_ADMIN"],
  "tenantId": 999,
  "enabled": true
}
~~~

if business rules only allow updating displayName.

For sensitive operations, create a DTO containing only permitted fields:

~~~java
public record UpdateProfileRequest(
        @NotBlank String displayName,
        @Size(max = 300) String publicBio
) {}
~~~

Service applying an allowlist:

~~~java
@Service
public class ProfileService {

    private final UserRepository users;

    public ProfileService(UserRepository users) {
        this.users = users;
    }

    @Transactional
    public void updateProfile(
            Long userId,
            UpdateProfileRequest request) {

        User user = users.findById(userId).orElseThrow();

        user.setDisplayName(request.displayName());
        user.setPublicBio(request.publicBio());
    }
}
~~~

Do not copy entire request maps onto entities with reflection or BeanUtils when requests can contain fields clients are forbidden to alter. Assign each field via an explicit allowlist.

Spring Data REST can continue serving simple repositories/resources. For sensitive operations requiring DTOs, owner/tenant authorization, or multi-step workflows, custom controllers/services generally give clearer contract control.

## 8. Protecting repositories with Spring Security method security

Hiding fields in JSON does not replace authorization. An unauthorized user can still invoke endpoints directly if the repository resource is unprotected.

Spring Data REST supports Spring Security method-level security. Enable method security:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Spring Boot Starter Security does not automatically enable method-level authorization. You must enable `@EnableMethodSecurity` if using `@PreAuthorize` or `@PostAuthorize`.

Example protecting a repository:

~~~java
@RepositoryRestResource(path = "orders")
@PreAuthorize("hasAuthority('orders:read')")
public interface OrderRepository
        extends JpaRepository<Order, Long> {

    @PreAuthorize("hasAuthority('orders:read')")
    @Override
    Optional<Order> findById(Long id);

    @PreAuthorize("hasAuthority('orders:write')")
    @Override
    <S extends Order> S save(S entity);

    @PreAuthorize("hasAuthority('orders:delete')")
    @Override
    void deleteById(Long id);

    @PreAuthorize("hasAuthority('orders:delete')")
    @Override
    void delete(Order entity);

    @PreAuthorize("hasAuthority('orders:delete')")
    @Override
    void deleteAll(Iterable<? extends Order> entities);

    @PreAuthorize("hasAuthority('orders:delete')")
    @Override
    void deleteAll();
}
~~~

The authorities in the example are application-defined permission names. You can use roles such as `hasRole('ADMIN')` if your system organizes permissions by role.

Spring Data REST notes that repository-level annotations and method-level annotations **do not automatically combine**. A method-level annotation overrides the repository-level annotation. If a method needs both a general read permission and a special permission, combine both conditions in the same expression, for example:

~~~java
@PreAuthorize(
    "hasAuthority('orders:read') and hasAuthority('orders:delete')"
)
@Override
void deleteById(Long id);
~~~

`CrudRepository` has multiple delete variants. Protecting `deleteById` while omitting `delete(entity)`, `deleteAll(iterable)`, or `deleteAll()` leaves remaining paths open. Review every method HTTP requests or exporters invoke.

Also protect search query methods and methods reading sensitive data. Do not restrict only POST/PUT/PATCH/DELETE.

## 9. Per-object and per-tenant authorization

Role-based access is only the first step. Many applications must check whether the user has permission on that specific entity.

Example service allowing only the owner or support staff to read an Order:

~~~java
@Service
public class OrderQueryService {

    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize(
        "@orderAccess.canRead(#orderId, authentication)"
    )
    @Transactional(readOnly = true)
    public OrderView getOrder(Long orderId) {
        Order order = orders.findById(orderId).orElseThrow();

        return new OrderView(
                order.getId(),
                order.getOrderNumber(),
                order.getStatus());
    }
}
~~~

Policy bean:

~~~java
@Component("orderAccess")
public class OrderAccess {

    public boolean canRead(
            Long orderId,
            Authentication authentication) {
        // Check owner, tenant, support permissions, and state.
        return true; // Replace with real policy.
    }
}
~~~

`true` in the example is only a placeholder; production code must query and enforce real permissions. Never use a client-submitted username or tenantId as proof of permission. Obtain identity from Authentication and verify ownership on the server.

If using the default Spring Data REST exporter, protect the repository methods invoked by the exporter. For complex per-object policies, custom services/controllers can be easier to govern because methods take explicit IDs and principals and return DTOs.

Never rely on the client not seeing a link or not knowing an ID. IDs can be guessed or leaked via logs, exports, URLs, or other resources. Every request must be authorized independently.

## 10. Association links are not a data protection mechanism

Spring Data REST represents associations using HAL links, for example:

~~~json
{
  "username": "lan",
  "_links": {
    "self": {
      "href": "https://api.example.com/users/12"
    },
    "profile": {
      "href": "https://api.example.com/users/12/profile"
    }
  }
}
~~~

Links merely help clients discover URIs. They do not prove the caller is allowed to read or modify the target resource.

If a profile contains private data:

- Protect the Profile item endpoint.
- Protect the association resource from User to Profile.
- Protect the Profile repository if exported independently.
- Enforce authorization on GET, PUT, POST, and DELETE association operations per business rules.
- Never place private data into excerpts or nested projections just to reduce request counts.

Hiding an association link in a response does not automatically block clients from calling a known URI. Conversely, displaying a link does not mean every user is authorized to follow it.

## 11. Hiding repositories, methods, or associations from the REST API

You can avoid exporting a repository:

~~~java
@RepositoryRestResource(exported = false)
public interface InternalAuditRepository
        extends JpaRepository<AuditRecord, Long> {
}
~~~

You can avoid exporting a query method:

~~~java
@RestResource(exported = false)
Optional<User> findByPasswordResetToken(String token);
~~~

You can avoid exporting an association:

~~~java
@ManyToOne
@RestResource(exported = false)
private InternalProfile internalProfile;
~~~

These configurations help shrink the API surface:

- `@RepositoryRestResource(exported = false)`: the repository is not exposed as REST resources.
- `@RestResource(exported = false)` on a method: the method is not exposed.
- `@RestResource(exported = false)` on an association: the association sub-resource/link is not exposed.

However, not exporting is not authorization. Other services or controllers can still access the data; if other routes exist, those routes need their own security. When a repository is still used internally, this annotation does not replace service-layer permission controls.

## 12. Protecting write operations and preventing mass assignment

A response that omits sensitive fields can still accept requests that overwrite those fields. For instance, if a client sends:

~~~http
PATCH /api/users/12
Content-Type: application/merge-patch+json
~~~

~~~json
{
  "roles": ["ROLE_ADMIN"],
  "enabled": true
}
~~~

then hiding fields in GET does not automatically stop Spring Data REST from binding the request onto the entity. Input must also be controlled.

Measures:

1. Do not export repositories directly when entities contain many sensitive writable fields.
2. Use DTO/command endpoints with an allowlist of updatable fields.
3. Use `@JsonProperty(access = READ_ONLY)` or appropriate Jackson configuration for properties clients must not write, and test it.
4. Place authorization on repository/service methods.
5. Check owner, tenant, role, and business state on the server.
6. Do not let clients alter `@Version`, IDs, audit fields, or administrative privileges unless business rules allow it.
7. Use validation and database constraints as additional defensive layers.

For passwords, provide a dedicated password-change endpoint: verify the current password or valid token, enforce policy, encode with `PasswordEncoder`, save the hash, and never return hashes to the client.

## 13. Protecting query methods and search resources

Spring Data REST can export query methods under `/search`. These methods can leak data even when item endpoints are partially protected.

Example:

~~~java
@RestResource(path = "by-email", rel = "byEmail")
@PreAuthorize("hasAuthority('users:lookup')")
Optional<User> findByEmail(@Param("email") String email);
~~~

Check:

- Does the query method return sensitive fields via the default representation or projections?
- Can search parameters be abused to enumerate emails, phone numbers, or identifiers?
- Is the caller permitted to search across all tenants or only their own tenant?
- Should results be capped, rate-limited, or audited?
- Are search endpoints protected at least as strictly as item/collection endpoints?

If account lookups by email or reset token are needed, a custom endpoint/service with explicit policies, rate limiting, and minimal responses is generally safer than exporting a generic query method.

## 14. Combining HTTP security with method security

Method security protects annotated method calls. Spring Security also recommends a request-level rule covering remaining routes, because unannotated methods are not automatically protected.

Skeleton configuration example:

~~~java
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

The example requires authentication for /api and denies remaining routes; production systems must choose an authentication mechanism suited to their real architecture such as OAuth2 Resource Server/JWT, sessions, or HTTP Basic.

Request-level security protects routes broadly; method-level security adds conditions on repositories, services, method parameters, or return values. Both layers must be tested.

CORS does not replace authorization. Allowing a browser origin to send requests does not prove a user has permission to access data.

## 15. Testing that sensitive fields are not exposed

Do not check only HTTP status codes. Verify the response body does not contain sensitive field names, secret values, or private related data.

Example:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class UserExposureTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(authorities = "users:read")
    void userResponseDoesNotExposePasswordHash() throws Exception {
        mockMvc.perform(get("/api/users/12")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").exists())
            .andExpect(jsonPath("$.passwordHash").doesNotExist())
            .andExpect(jsonPath("$.resetToken").doesNotExist());
    }
}
~~~

Testing published projections:

~~~java
@Test
@WithMockUser(authorities = "users:read")
void publicProjectionDoesNotExposeSecrets() throws Exception {
    mockMvc.perform(get("/api/users/12")
            .param("projection", "userSummary")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.username").exists())
        .andExpect(jsonPath("$.passwordHash").doesNotExist());
}
~~~

Testing denied roles:

~~~java
@Test
@WithMockUser(authorities = "users:read")
void userWithoutDeleteAuthorityCannotDelete() throws Exception {
    mockMvc.perform(delete("/api/users/12"))
        .andExpect(status().isForbidden());
}
~~~

If unauthenticated, the status is typically 401 depending on the authentication entry point; if authenticated without sufficient permissions, typically 403. Real configurations may customize error responses.

Tests should cover:

- Default item and collection representations.
- Every projection and excerpt.
- Nested projections and association links.
- Search resources and query methods.
- Direct GETs on association URIs.
- PUT/PATCH/POST/DELETE on associations.
- Whether forbidden fields in request bodies can be mutated.
- That users from other tenants/owners cannot access resources.
- That both repository methods and custom controllers enforce authorization.

## 16. Reviewing the data surface before release

A useful review process:

1. List all exported entities/repositories.
2. Classify fields as public, internal, confidential, or secret.
3. Inspect Jackson annotations on fields/getters.
4. List every projection, excerpt, and nested projection.
5. Inspect association links and target repositories.
6. Inspect query methods and search parameters.
7. Audit writable fields, mass assignment, and DTOs.
8. Audit request-level and method-level authorization.
9. Test with users across different roles, owners, and tenants.
10. Inspect actual responses, logs, and ALPS/JSON Schema metadata to ensure unintended contracts are not exposed.

ALPS metadata can list projection names and field descriptors. Metadata is not an entity's secret content, yet internal projection or relation names can still disclose API structure. Register only projections and resources clients are permitted to discover.

## 17. Common pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| passwordHash is absent in default GET but appears with projection | Projection has a getter for a @JsonIgnore field | Audit every projection and nested projection; remove sensitive getters |
| Association link is hidden yet clients still access the URI | Links are not an authorization mechanism | Protect target endpoint/resource and association methods |
| Regular users can modify roles | Request binder accepts fields outside UI intent | Use DTO allowlists, read-only binding, and service policies |
| Only DELETE by ID is blocked while deleteAll still runs | Not all CRUD methods are protected | Override and protect every exported delete variant |
| Repository-level rule does not apply as expected on a method | Method annotation overrides class/interface annotation | Write combined conditions inside the method expression if both are needed |
| Search endpoint leaks emails or tokens | Query method is exported without authorization | Protect the method, limit results, and use dedicated endpoints |
| Excerpt leaks private related data | Nested projection inlines associations | Expose only necessary fields and audit nested projections |
| Custom endpoint still leaks fields despite @JsonIgnore on entity | Controller uses a different DTO/ObjectMapper/serializer | Inspect custom representations and write response tests |
| CORS is configured properly yet unauthorized users still access the API | CORS is not authorization | Use Spring Security request and method security |
| @PreAuthorize exists yet other routes stay public | Only annotated methods are protected | Add a catch-all request rule and audit all routes |

## 18. Design principles

- Design representations using allowlists rather than exporting entire entities and trying to hide fields one by one.
- Never allow secrets or credential hashes to appear in any projection, excerpt, or nested projection.
- Use DTO/command models for sensitive operations and fields whose write permissions vary by user.
- Protect collections, items, searches, associations, and custom controllers with proper authorization.
- Never treat hidden links, renamed relations, or unpredictable UUIDs as security.
- Enforce owner/tenant permissions on the server for every request.
- Protect all CRUD methods used by the exporter, including bulk delete variants.
- Use tests to verify sensitive data stays absent and unauthorized requests are rejected.
- Re-audit projections/associations whenever the domain model gains new fields or relationships.

## References

- [Spring Data REST 5.1.2 — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): projections, excerpts, nested associations, and warnings that projections can re-expose `@JsonIgnore` fields.
- [Spring Data REST 5.1.2 — Security](https://docs.spring.io/spring-data/rest/reference/security.html): securing repositories with `@PreAuthorize`, `@Secured`, method-level security, and notes that method annotations override repository-level annotations.
- [Spring Data REST 5.1.2 — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, association, and search resources along with exported HTTP methods.
- [Spring Security 7.1 — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, `@PostAuthorize`, parameter/return-object authorization, and testing method security.
- [Spring Framework — Jackson JSON](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/jackson.html): Jackson serialization views in Spring MVC; if using custom controllers, control response views separately.
