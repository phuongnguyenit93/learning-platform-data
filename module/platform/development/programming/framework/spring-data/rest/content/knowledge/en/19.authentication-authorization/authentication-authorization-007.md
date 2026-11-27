# Authorizing Read, Create, Update, Delete, and Association Operations

## Objective

After this lesson, you will be able to:

- Distinguish read, create, update, and delete permissions for resources in Spring Data REST.
- Map each HTTP method to its corresponding permission.
- Protect association endpoints when adding, replacing, or removing links between two resources.
- Combine URL/HTTP-method rules with permission checks at the repository or service layer.
- Verify both operational permissions and data ownership to prevent users from modifying or deleting another user's resources.

## 1. Where does authorization happen?

Spring Data REST automatically publishes repositories as REST endpoints. For example, `PersonRepository` can expose the collection endpoint `/people`, item endpoint `/people/{id}`, and association endpoints such as `/people/{id}/addresses`.

Publishing an endpoint does not mean every user is allowed to call it. Two questions must be separated:

- **Authentication:** Who is the caller?
- **Authorization:** Which operations on which resources is that caller allowed to perform?

Spring Security is typically the primary control layer for incoming requests. Rules by HTTP method and path can be configured in `SecurityFilterChain`. When deeper checks are required—such as allowing only the owner to edit a record—you can add method security at the repository or service layer.

A complete policy usually has multiple layers:

1. Is the request allowed to use that HTTP method on this endpoint?
2. Does the user hold the required authority?
3. Does the user have permission on that specific record or related resource?
4. Does the repository actually expose that operation?

## 2. Mapping CRUD to HTTP methods

For a `/people` collection endpoint, common operations map as follows:

| Business operation | HTTP method | Example endpoint | Common permission |
|---|---|---|---|
| Read list | `GET` | `/people` | `people:read` |
| Read detail | `GET` | `/people/42` | `people:read` |
| Create new | `POST` | `/people` | `people:create` |
| Replace/update | `PUT` | `/people/42` | `people:update` |
| Partial update | `PATCH` | `/people/42` | `people:update` |
| Delete | `DELETE` | `/people/42` | `people:delete` |

These authority names are illustrative. Applications may use different naming conventions, but must stay consistent between where authorities are issued and where they are checked.

Key distinctions:

- `GET` is normally read-only. If a user may view the list but must not see certain records, endpoint-level checks alone are insufficient; filter data per user or check per-resource permissions.
- `POST` on a collection normally creates a new resource.
- `PUT` normally replaces resource state; `PATCH` normally performs a partial update.
- `DELETE` on an item endpoint normally deletes that resource.
- Operations on association endpoints can also use `POST`, `PUT`, or `DELETE`, but their semantics modify the link rather than necessarily creating or deleting the target record.

Spring Data REST only processes methods permitted by the repository and exposure configuration. An HTTP method disabled at the exposure layer will not become available merely because the user holds a matching authority.

## 3. Protecting endpoints by HTTP method with Spring Security

The example below illustrates a policy for the `people` resource. Authorities such as `people:read` and `people:create` are permission strings the application must grant to users or tokens.

~~~java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                // Read collections, items, and association resources.
                .requestMatchers(HttpMethod.GET, "/people", "/people/**")
                    .hasAuthority("people:read")

                // Association modification permissions: placed before general CRUD rules.
                .requestMatchers(HttpMethod.POST, "/people/*/addresses")
                    .hasAuthority("people:link")
                .requestMatchers(HttpMethod.PUT, "/people/*/address")
                    .hasAuthority("people:link")
                .requestMatchers(
                    HttpMethod.DELETE,
                    "/people/*/addresses/**",
                    "/people/*/address"
                ).hasAuthority("people:unlink")

                // CRUD on the Person resource itself.
                .requestMatchers(HttpMethod.POST, "/people")
                    .hasAuthority("people:create")
                .requestMatchers(HttpMethod.PUT, "/people/**")
                    .hasAuthority("people:update")
                .requestMatchers(HttpMethod.PATCH, "/people/**")
                    .hasAuthority("people:update")
                .requestMatchers(HttpMethod.DELETE, "/people/**")
                    .hasAuthority("people:delete")

                .anyRequest().denyAll()
            )
            .build();
    }
}
~~~

In this example:

- Users with `people:read` can read resources.
- Users with `people:create` can create a `Person`.
- Users with `people:update` can edit a `Person`.
- Users with `people:delete` can delete a `Person`.
- Users with `people:link` can add or set address links.
- Users with `people:unlink` can remove address links.

Association rules are placed before general CRUD rules so link-modification requests receive their dedicated authority checks. If a broader rule matches first, requests may be evaluated against a wider permission than intended.

The paths `/people/*/addresses` and `/people/*/address` are examples only. Replace them with the actual association paths exposed by Spring Data REST in your application. Path names typically depend on resource names and association `rel`s; collection associations and single-value associations can have different structures.

`hasAuthority("people:read")` matches the exact authority string. If using `hasRole("ADMIN")`, Spring Security checks the `ROLE_ADMIN` authority by default. Do not mix conventions without understanding how authorities are granted.

`anyRequest().denyAll()` is a strict default choice for an example with an explicit allowlist of endpoints. In real applications, add other valid endpoints such as login, health checks, or public resources according to system policy.

## 4. Authorization on association resources

Spring Data REST can expose an association as its own endpoint. For example, a `Person` has many `Address` entities:

- `GET /people/42/addresses`: read addresses currently linked to person 42.
- `POST /people/42/addresses`: add an address to the collection association.
- `DELETE /people/42/addresses/9`: remove address 9 from person 42's association.

For a single-value association, such as one primary address per person:

- `GET /people/42/address`: read the currently linked address.
- `PUT /people/42/address`: set or replace the linked address.
- `DELETE /people/42/address`: remove the current link if the association supports this operation.

A request adding an address to a collection association may look like:

~~~http
POST /people/42/addresses
Content-Type: text/uri-list

http://localhost:8080/addresses/9
~~~

This request sends the URI of the target resource. It asks Spring Data REST to add a link between `Person` 42 and `Address` 9. Its primary meaning is **linking two resources**, not creating a new `Address` 9 record.

To replace a person's primary address, the request may be:

~~~http
PUT /people/42/address
Content-Type: text/uri-list

http://localhost:8080/addresses/12
~~~

To remove an element from a collection association:

~~~http
DELETE /people/42/addresses/9
~~~

When designing permissions, decide these questions separately:

- Who can view links?
- Who can add links?
- Who can replace a single-value link?
- Who can remove links?
- May a user link to any target resource or only target resources they are permitted to access?

Someone allowed to edit `Person` details is not necessarily allowed to modify address relationships. Likewise, permission to remove a link does not equate to permission to delete the linked `Address` record. Clearly separate unlinking from deleting resources.

## 5. Adding method security at the repository or service layer

URL and HTTP-method rules distinguish `POST`, `PUT`, `PATCH`, and `DELETE`. For conditions tied to specific data, enable method security:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

You can then protect repository methods with `@PreAuthorize`:

~~~java
@RepositoryRestResource
public interface PersonRepository extends JpaRepository<Person, Long> {

    @Override
    @PreAuthorize("hasAuthority('people:read')")
    Page<Person> findAll(Pageable pageable);

    @Override
    @PreAuthorize("@personAccess.canSave(authentication, #p0)")
    <S extends Person> S save(S entity);

    @Override
    @PreAuthorize("@personAccess.canDelete(authentication, #p0)")
    void deleteById(Long id);
}
~~~

`personAccess` is an application-implemented bean. `canSave` can distinguish creation from update based on the entity's ID: an entity without an ID requires create permission; an existing entity requires update permission and ownership verification. `canDelete` checks delete permission and permission on the specific record. These checks supplement request matchers; requests still must satisfy both layers.

Do not assume every internal method invoked by the framework goes through an arbitrary application service. When using Spring Data REST, place checks at the point actually invoked in the repository flow, or use custom repository methods/event handlers suited to your design. Some update/delete flows may need to read the record before executing; design appropriate internal read permissions and test real requests to avoid accidentally blocking valid operations.

## 6. Checking permissions per resource

The `people:update` permission only answers whether a user can edit the `Person` resource type. It does not prove the user can edit every `Person`.

For example, a system might enforce:

- Users can only edit `Person` records they own.
- Administrators can edit any `Person`.
- Users can only link addresses they have permission to read or manage.

You can invoke a permission-checking bean inside a `@PreAuthorize` expression:

~~~java
@PreAuthorize(
    "hasAuthority('people:update') and " +
    "@personAccess.canUpdate(authentication, #personId)"
)
public Person updatePerson(Long personId, UpdatePersonCommand command) {
    // Load existing record, apply valid changes, and save.
}
~~~

This is an example for a service operation invoked by the application. If the REST endpoint is published directly by Spring Data REST from the repository, place the same rule on the repository method or appropriate extension point; an annotation on a service does not automatically protect a repository bypassed by direct REST calls.

The permission-checking bean must inspect the stored record, its owner, and the current principal's permissions. For update operations, do not trust an `owner` field submitted by the client: clients can modify the payload to claim ownership. Compare against persisted data and apply a separate owner-change policy.

Similarly, before adding an association, verify both sides:

1. The user is allowed to modify associations on the source resource.
2. The target resource exists and the user is allowed to link to it.
3. Linking does not violate business rules, such as linking an address belonging to another tenant.

When restricting returned data, prefer queries already scoped by principal/tenant. Filtering results only after querying can skew counts and pagination metadata, and risks leaking information through `totalElements` or navigation links.

## 7. Disabling methods is not authorization

Spring Data REST provides exposure configuration to restrict HTTP methods published for a repository or association. This is an API surface control mechanism:

- If the system forbids deleting via REST, publishing the `DELETE` operation can be disabled.
- If the operation remains published, Spring Security decides which callers are allowed to invoke it.
- Disabling a method does not replace permission checks in services or other call paths within the application.

In other words, exposure answers "Does the API offer this operation?", whereas authorization answers "Is the current caller allowed to invoke this operation?". Both layers serve distinct purposes and can be used together.

## 8. Key points to check during implementation

- **Matcher order:** specific association rules must precede broader CRUD rules if both could match.
- **HTTP methods:** test `GET`, `POST`, `PUT`, `PATCH`, and `DELETE` separately; do not rely on a single write permission if business rules require separation.
- **Actual paths:** confirm collection, item, and association endpoints from HAL links or the application's API documentation.
- **Resource permissions:** check ownership, tenant, and permissions on target resources; do not rely solely on generic roles.
- **Associations:** confirm link add/remove operations do not inadvertently create or delete target records.
- **CSRF:** if the application authenticates via browser sessions/cookies, keep CSRF protection enabled for state-changing requests. For stateless bearer-token APIs, configure CSRF based on the actual authentication model and risk profile; do not disable it merely because endpoints are REST.
- **Error responses:** unauthenticated requests normally receive `401 Unauthorized`; authenticated users lacking permissions normally receive `403 Forbidden`. Do not let error responses leak sensitive data.

A minimal test matrix should include a read-only user, a create/update user, a user allowed to delete, and a user with no permissions. Test both main resources and association resources, including cases accessing data owned by another user.

## 9. Self-check exercises

A system defines the permissions `people:read`, `people:create`, `people:update`, `people:delete`, `people:link`, and `people:unlink`.

1. A user with only `people:read` calls `POST /people`. What is the expected result?
2. A user with `people:update` calls `DELETE /people/42`. Is it allowed?
3. A user with permission to edit `Person` but without `people:link` calls `POST /people/42/addresses`. Can the link be added?
4. Does `DELETE /people/42/addresses/9` necessarily delete the `Address` record with ID 9?
5. Why check permissions on the target resource before creating a link?

**Answers:**

1. Denied because `people:create` is missing.
2. Denied if the delete policy requires `people:delete`.
3. Denied because association operations have their own permission.
4. No. That is an unlinking operation; deleting the target record is a separate operation.
5. To prevent users from creating links to data outside their permitted scope, such as a resource belonging to another tenant.

## Key takeaways

- Use HTTP methods to differentiate read, create, update, and delete permissions.
- Association resources need dedicated policies for reading, adding, replacing, and removing links.
- Use Spring Security request matchers for method/URL rules and method security for conditions tied to repositories, services, or specific data.
- Check permissions on both source and target resources when modifying links.
- Exposure determines whether an operation is published; authorization determines who may invoke it.

References:

- [Spring Data REST — Security](https://docs.spring.io/spring-data/rest/reference/security.html)
- [Spring Data REST — Association Resources](https://docs.spring.io/spring-data/rest/reference/associations.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
