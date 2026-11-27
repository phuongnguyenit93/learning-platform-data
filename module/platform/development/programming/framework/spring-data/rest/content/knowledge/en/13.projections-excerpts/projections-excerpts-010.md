# Projections Can Expose Data Hidden with `@JsonIgnore`

## Objectives

`@JsonIgnore` can exclude a property from an entity's default JSON representation. However, Spring Data REST projections create a different representation based on the accessors declared in a projection interface. If a projection actively declares a getter for a sensitive property, that property can reappear in the projection response even though the entity is annotated with `@JsonIgnore`.

Therefore, do not use `@JsonIgnore` as a security boundary. Treat every projection, excerpt projection, and nested projection as a separate part of the API contract that must be controlled individually.

## Default representation and projections

Suppose a `User` entity contains a username and an internal secret value:

    @Entity
    public class User {
        @Id
        private Long id;

        private String username;

        @JsonIgnore
        private String apiKeyHash;

        // getters and setters
    }

When serializing the entity with the default representation, Jackson omits `apiKeyHash` according to the annotation configuration. The response may contain only `id` and `username`.

Projections let you define a different view of the entity. Spring Data REST creates a projection proxy based on the accessors exposed by the interface:

    @Projection(name = "userSummary", types = User.class)
    public interface UserSummary {
        Long getId();
        String getUsername();
    }

Clients can request a registered projection:

    GET /api/users?projection=userSummary
    GET /api/users/42?projection=userSummary

The response contains only the properties exposed by the `UserSummary` projection.

## Why might `@JsonIgnore` fail to protect a projection?

`@JsonIgnore` affects how Jackson handles properties in the representation provided directly by the entity. A projection is a separate view: the projection interface declares which properties to read from the target object. When a projection declares an accessor for a property excluded from the default representation, that accessor can cause the property to appear in the projection's JSON.

The following example creates a data exposure risk:

    @Projection(name = "userWithKey", types = User.class)
    public interface UserWithKey {
        Long getId();
        String getUsername();
        String getApiKeyHash();
    }

Clients can call:

    GET /api/users?projection=userWithKey

The `UserWithKey` projection exposes the `getApiKeyHash()` getter. Therefore, never assume that `@JsonIgnore` on an entity will automatically exclude a property from every projection. If this projection is registered and the endpoint allows using it, the sensitive value can be serialized in that representation.

Key takeaway: `@JsonIgnore` protects the default representation according to Jackson rules; it is not an authorization policy and does not replace safe projection design.

## Excerpt projections must also be controlled

Spring Data REST can apply an excerpt projection to items in a collection. You can specify an excerpt projection on the repository:

    @RepositoryRestResource(excerptProjection = UserExcerpt.class)
    public interface UserRepository
            extends JpaRepository<User, Long> {
    }

An excerpt projection is used to represent items in a collection or corresponding embedded contexts. If the excerpt interface contains a getter for `apiKeyHash`, that data can be exposed as soon as a client reads the collection, even without requesting a named projection via query parameter.

Therefore, inspect both projections requested explicitly with `?projection=...` and excerpt projections applied automatically. Never put secret fields into an excerpt just because a collection response needs extra information.

## Nested projections and derived properties

A projection can reference another projection to represent nested associations. An inner projection can also expose sensitive properties of a related entity:

    @Projection(name = "userView", types = User.class)
    public interface UserView {
        String getUsername();
        DepartmentView getDepartment();
    }

    @Projection(name = "departmentView", types = Department.class)
    public interface DepartmentView {
        String getName();
        String getInternalBudgetCode();
    }

When auditing exposure, trace the entire projection graph, including associations and nested projections. Checking only direct getters on the root projection can miss data introduced through nested projections.

Projections using `@Value` or SpEL must also be reviewed. A computed getter can return sensitive data even when that property name does not exist directly on the entity. Inspect the values accessed by expressions, not only accessor names.

## How to design safe projections

1. **Default to an allowlist:** only declare getters for fields that genuinely need to be exposed to clients. Do not create catch-all projections containing every entity property.
2. **Separate public and internal data:** create dedicated projections for public use cases; never include tokens, passwords, hashes, sensitive identifiers, or internal operational fields.
3. **Keep excerpts minimal:** excerpt projections often appear automatically in collections, so include only fields safe for broad exposure.
4. **Control nested projections:** review association projections and derived getters that could open a path to sensitive data.
5. **Restrict access permissions:** use Spring Security and endpoint/service-level authorization when data is intended only for certain users. Do not treat the projection name or a client knowing the query parameter as a protection mechanism.
6. **Use dedicated DTOs or controllers when contextual authorization is required:** if two user groups are allowed to see two different sets of fields, build controlled representations at the service/controller layer and enforce authorization before returning data.

Example of a public projection exposing only necessary fields:

    @Projection(name = "publicUser", types = User.class)
    public interface PublicUser {
        Long getId();
        String getUsername();
    }

Do not declare `getApiKeyHash()` in `PublicUser`. Omitting the getter from the projection is the direct way to keep that property out of this view.

## Checking whether data is exposed

Inspect every representation that the application actually publishes:

1. Call the default item and collection endpoints; confirm properties annotated with `@JsonIgnore` do not appear.
2. Call item and collection endpoints with every registered projection via `?projection=...`.
3. Inspect excerpt projections configured on repositories.
4. Inspect nested projections, associations, and getters using SpEL.
5. Test with low-privilege accounts and high-privilege accounts to confirm authorization is enforced properly.
6. Write integration tests verifying the response body contains neither the property name nor the secret value, rather than checking only status `200 OK`.

Example tests should verify both default representations and projections:

    mockMvc.perform(get("/api/users/42"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.apiKeyHash").doesNotExist());

    mockMvc.perform(get("/api/users/42")
            .param("projection", "publicUser"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.apiKeyHash").doesNotExist());

Adjust JSON paths according to your application's media type and HAL response structure. If a property sits inside `_embedded` or a nested object, inspect the corresponding JSON path. Use realistic dummy secret values in tests to catch cases where data is emitted under a different name.

## When sensitive data must be protected

- Annotate with `@JsonIgnore` to exclude properties from the default representation when appropriate.
- Never declare sensitive properties in any public projection, excerpt projection, or nested projection.
- If certain users must be allowed to view the data, enforce authorization on the server and return representations based on the caller's permissions.
- Consider not exposing repositories directly for entities containing secrets; use DTOs or custom endpoints to explicitly control returned data.
- Inspect responses after adding a new projection or changing `excerptProjection`, as that modifies the API data surface.

`@JsonIgnore` does not guarantee data is absent from every representation produced by Spring Data REST. Each projection is a distinct display contract; expose only safe fields and protect data with server-side authorization.