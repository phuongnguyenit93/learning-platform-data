# Testing Projections, Excerpts, and Sensitive Data

## Goal

Spring Data REST can represent the same entity in multiple JSON shapes using projections. Projections let you select which properties appear in a representation, create display names, or nest projections for associations. An excerpt projection is a projection configured as the default summary shape when an entity appears inside a collection representation.

These mechanisms are helpful when an API needs to return less data for lists, provide multiple views for different client types, or avoid sending unnecessary properties. However, projections and excerpts are representation-shaping mechanisms; they do not create authorization rules and do not protect sensitive data across all endpoints.

This lesson explains how to declare and select projections, configure excerpts, verify actual responses, and establish safe boundaries for sensitive data.

## 1. What Is a Projection?

A projection is an interface describing the set of properties Spring Data REST uses to build a representation. Instead of serializing the entire domain object with its default representation, Spring Data REST builds a view based on the accessors declared in the projection.

Example entity:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String firstName;
    private String lastName;
    private String email;
    private String phoneNumber;

    // getters and setters
}
~~~

Projection showing only names:

~~~java
@Projection(name = "personName", types = Person.class)
public interface PersonName {

    String getFirstName();

    String getLastName();
}
~~~

When a client selects a projection, the representation focuses on the declared properties. Spring Data REST may still include necessary HAL links for navigating to resources.

Projections are commonly used when:

- Lists only need a few concise fields.
- Detail screens need a different set of fields than list screens.
- Clients need a computed property or display name.
- Associations need a condensed representation.
- The API wants to avoid transmitting unnecessary fields in a specific response.

Projections do not alter entity structure or database schema. They define a view over the entity when constructing a representation.

## 2. Declaring and Discovering Projections

A projection is declared using the `@Projection` annotation:

~~~java
@Projection(name = "personName", types = Person.class)
public interface PersonName {

    String getFirstName();

    String getLastName();
}
~~~

Key points to remember:

- `name` is the public name used in the `projection` query parameter.
- `types` specifies the domain types to which the projection applies.
- A projection is an interface; Spring Data creates a proxy to supply the accessors.
- Getters determine which properties or nested views appear.

Spring Data REST discovers projections by package convention. Place projections in the same package as the domain type or a subpackage of that package so the repository exporter can find them.

Example structure:

~~~text
com.example.people
├── Person.java
├── PersonRepository.java
└── projection
    ├── PersonName.java
    └── PersonDetail.java
~~~

If a projection does not appear in the API, check the interface's package, projection name, and domain type in `@Projection`. Do not confuse the Java interface name with the `name` value: clients use the `name` value in URLs.

## 3. Selecting a Projection via Query Parameter

A projection can be requested using the `projection` query parameter.

Example fetching a collection:

~~~http
GET /people?projection=personName
Accept: application/hal+json
~~~

Example fetching an item:

~~~http
GET /people/42?projection=personName
Accept: application/hal+json
~~~

Spring Data REST uses the registered projection name to generate the corresponding representation. HAL links can still appear alongside the projection's fields.

If `projection` is omitted, the endpoint uses the resource's default representation, unless the collection resource has an excerpt projection configured.

The projection name in the URL is distinct from the repository path and Java interface name. For instance, `PersonName` is the interface name, whereas `personName` is the public name in `@Projection`.

Clients should only rely on projection names treated as part of the API contract. When renaming a projection, update clients and API documentation accordingly.

## 4. Configuring an Excerpt Projection for Collections

An excerpt projection is a projection that Spring Data REST automatically uses as the summary representation for entities inside a collection representation when declared on the repository.

Example:

~~~java
@Projection(name = "personExcerpt", types = Person.class)
public interface PersonExcerpt {

    String getFirstName();

    String getLastName();
}
~~~

Repository configuration:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

When a client calls:

~~~http
GET /people
Accept: application/hal+json
~~~

People in the collection representation will use the configured excerpt projection. This keeps lists limited to summary fields instead of full detailed data.

An excerpt projection does not automatically change the item resource representation. For instance, `GET /people/42` still uses the default representation if the client does not select a projection. If an item needs a specific view, request the projection explicitly:

~~~http
GET /people/42?projection=personExcerpt
~~~

This is an important distinction when auditing sensitive data: configuring an excerpt for a collection does not mean every access path for that entity uses the same set of fields.

## 5. Default Projection vs. Excerpt Projection Differences

| Mechanism | How selected | Typical scope |
|---|---|---|
| Default representation | No query parameter passed | Item resources and collections without an excerpt |
| Explicit projection | `?projection=personName` | Client selects a registered view |
| Excerpt projection | `excerptProjection = PersonExcerpt.class` on repository | Automatically condenses entities inside collection representations |

A repository can declare an excerpt projection and still allow clients to select another projection via query parameter. An excerpt is the default choice for collections; explicit projections allow clients to request another published view.

Verify each separately:

- Collection resources.
- Item resources.
- Collections returned from search resources.
- Entities appearing inside associations.
- Explicitly selected projections.

Do not assume every response type applies excerpts identically. Representation behavior also depends on resource type and Spring Data REST version; integration tests confirm the actual API contract.

## 6. Multiple Projections for Different Needs

A domain type can have multiple projections:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

~~~java
@Projection(name = "personContact", types = Person.class)
public interface PersonContact {

    String getFirstName();

    String getLastName();

    String getEmail();

    String getPhoneNumber();
}
~~~

Clients can select:

~~~http
GET /people/42?projection=personSummary
GET /people/42?projection=personContact
~~~

The summary view fits list screens or user pickers. The contact view fits features needing email and phone number.

Avoid creating a single projection containing all properties and reusing it everywhere just to reduce interface counts. Separate views keep the API contract clear about the exact data needed for each use case.

Also treat projections as public APIs: adding a getter to a projection in use can start exposing new data in responses consumed by clients.

## 7. Nested Projections and Associations

A projection can declare a view for an association instead of serializing the entire related object.

Domain example:

~~~java
@Entity
public class Address {

    @Id
    @GeneratedValue
    private Long id;

    private String city;
    private String district;
    private String street;
}
~~~

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;

    @ManyToOne
    private Address address;
}
~~~

Projection for address:

~~~java
@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {

    String getCity();

    String getDistrict();
}
~~~

The Person projection can declare an accessor returning the association's projection:

~~~java
@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {

    String getFirstName();

    AddressSummary getAddress();
}
~~~

The representation when selecting `personWithAddress` can include city and district of the address via the nested view. Other fields like street are not requested by this projection.

Nested projections are helpful when the API needs a unified representation structure and wants to avoid forcing clients to call multiple association endpoints just to display a few fields. However, if associations are large or lazy-loaded, consider query counts and data fetching strategy. Projections shape JSON but do not guarantee optimal SQL query counts in all cases.

Do not expose sensitive associations in a projection simply because an accessor exists. Every nested projection is also part of the API contract and needs to be audited like a top-level projection.

## 8. Computed Properties in Projections

Projections can define computed properties via Spring Expression Language using `@Value`.

Example:

~~~java
@Projection(name = "personDisplay", types = Person.class)
public interface PersonDisplay {

    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();

    String getEmail();
}
~~~

The client receives `displayName` built from firstName and lastName. Computed properties work well for presentation values that do not need separate database storage.

For complex expressions, multiple service calls, or mutable business logic, move the logic into a DTO assembler or custom controller/service. Keep SpEL simple so projections stay easy to understand and do not turn representations into hard-to-control business logic execution sites.

Check null handling in expressions. For example, concatenating strings with null fields can produce unexpected outputs; write appropriate expressions or use a dedicated display-value helper method.

## 9. Projections Are Not Authorization

Projections decide which fields appear in a specific representation. They do not decide whether a user has permission to read an entity or perform an operation.

For example:

- Users can choose another projection if that projection is published.
- Item resources may use the default representation instead of the excerpt.
- Search resources or associations may have their own representations.
- A custom endpoint might return data via another path.
- Projections do not prevent repository methods from returning sensitive entities or fields.

Therefore, do not use projections as your sole security boundary. Use Spring Security for authentication and authorization at the request, method, or object level. For data only specific user groups may read, enforce server-side access control before returning data.

If two user groups require two different data levels, create endpoints or service methods with explicit authorization returning role-specific DTOs. Never assume naming a projection obscurely protects data.

## 10. Protecting Sensitive Fields on Entities

Example of Person having a password hash and internal token:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String email;

    @JsonIgnore
    private String passwordHash;

    @JsonIgnore
    private String internalAccessToken;
}
~~~

`@JsonIgnore` instructs Jackson to ignore the property during both serialization and deserialization under default annotation behavior. This is suitable when a field does not belong in the public JSON contract at all.

If clients are allowed to send a value on create or update while the server must never return that value, consider:

~~~java
@JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
private String password;
~~~

`WRITE_ONLY` lets Jackson accept the property when deserializing requests without serializing it into responses. Process and hash passwords in a service before saving; never store plaintext passwords.

Never expose password hashes, reset tokens, API keys, refresh tokens, or internal secrets as display fields in projections. If a field must be accepted in requests yet withheld from responses, test both read and write directions.

## 11. Verifying Projections Do Not Leak Sensitive Data

A projection could accidentally include a getter for a sensitive field:

~~~java
// Do not use for public APIs if passwordHash is sensitive data.
@Projection(name = "personUnsafe", types = Person.class)
public interface PersonUnsafe {

    String getEmail();

    String getPasswordHash();
}
~~~

Treat every projection as a list of published fields. When reviewing a projection change, check:

- Do direct getters return sensitive fields?
- Do nested projections traverse into sensitive associations?
- Does SpEL access properties or beans returning sensitive data?
- Does an excerpt projection add fields beyond summary needs?
- Does the default representation accidentally expose sensitive fields?
- Do search resources and custom controllers serialize the same entity through another path?

If security requirements are strict, use DTOs with explicit allow-lists of fields or custom response models. Do not rely on an existing projection happening to omit a sensitive field; a new projection could accidentally bring that field back.

## 12. Projections Do Not Replace Write Request Models

Projections primarily shape read representations. They are not a full request schema deciding which fields clients may modify.

For instance, if a client sends JSON containing `role`, `accountStatus`, or `isAdmin`, omitting those fields from read projections does not automatically stop them from being deserialized or updated by write endpoints.

For server-managed fields:

- Use separate DTOs/request models if you need strict input allow-lists.
- Do not let clients directly set roles, owners, approval statuses, or audit timestamps.
- Populate server-managed fields inside services/event handlers.
- Use validation and authorization on update operations.
- Test request bodies containing out-of-contract fields.

If strict control over both read and write models is required, custom controllers/services with separate DTOs are usually clearer than relying solely on entity projections.

## 13. Testing Representations with MockMvc

Test actual JSON for collections, items, explicit projections, and excerpt projections.

Repository example:

~~~java
@RepositoryRestResource(
    path = "people",
    excerptProjection = PersonExcerpt.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Testing collection using excerpt:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonProjectionTests {

    @Autowired
    MockMvc mvc;

    @Test
    void collectionUsesConfiguredExcerpt() throws Exception {
        mvc.perform(get("/people")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._embedded.people[0].firstName")
                .exists())
            .andExpect(jsonPath("$._embedded.people[0].passwordHash")
                .doesNotExist());
    }
}
~~~

Testing explicit projection:

~~~java
@Test
void explicitProjectionReturnsSelectedFields() throws Exception {
    mvc.perform(get("/people/42")
            .param("projection", "personName")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.firstName").exists())
        .andExpect(jsonPath("$.lastName").exists())
        .andExpect(jsonPath("$.passwordHash").doesNotExist());
}
~~~

Testing default item representation:

~~~java
@Test
void defaultItemRepresentationDoesNotExposeSecrets() throws Exception {
    mvc.perform(get("/people/42")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.passwordHash").doesNotExist())
        .andExpect(jsonPath("$.internalAccessToken").doesNotExist());
}
~~~

These are test skeletons; create Person fixtures with appropriate IDs, ensure the collection has at least one item, and adjust JSON paths to match the actual collection resource name.

Add tests for:

- Projections are discovered and selectable by name.
- Excerpts apply only to the expected representations.
- Item resources without a projection do not accidentally leak secrets.
- Search results and association representations do not expose sensitive fields.
- Nested projections return only selected fields.
- New projections do not add passwords, tokens, or internal properties.
- Write requests cannot modify server-managed fields.
- Unauthorized users cannot access endpoints even if they know a projection name.

## 14. Checking Sensitive Data Outside the JSON Body

Inspecting JSON responses is necessary but not sufficient. Some fields may surface elsewhere:

- HAL links or URIs might contain internal identifiers.
- Error responses might leak exception messages or input values.
- Logs might record passwords, tokens, or request bodies.
- Search endpoints might return entities using a different projection.
- Export endpoints or custom controllers might serialize the same entity with different settings.
- Association endpoints might expose unexpected nested objects.

Do not include secrets in URIs, links, exception messages, or logs. Use controlled logging and mask sensitive data. If a response needs a public identifier, separate it from internal secrets or tokens.

When auditing an API, look for sensitive fields across the entire JSON response and headers, not just the root object.

## 15. Common Pitfalls

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Projection not recognized | Interface is outside domain package or wrong types/name | Place projection in same package or subpackage and check @Projection |
| projection query parameter does not work | Using Java interface name instead of projection name | Use exact `name` value from @Projection |
| Collection still returns many fields | Repository has not configured excerptProjection | Declare excerptProjection on @RepositoryRestResource |
| Item resource still uses default representation | Excerpts do not automatically apply to items | Pass projection explicitly when needed |
| Projection leaks passwordHash | Sensitive getter declared in projection | Remove getter and protect field at serialization boundary |
| @JsonIgnore not enforced across all response paths | Search/custom endpoints use different representations | Test item, collection, search, association, and custom controllers |
| Nested projection returns too much data | Association getter uses full domain type | Use nested projection with minimal field set |
| Projection treated as access control | Confusing representation with authorization | Protect resources/methods/objects with Spring Security |
| Client can modify hidden fields | Read projection is not a request allow-list | Use DTOs/request models, validation, and server-managed fields |
| JSON body hides secrets but logs contain them | Requests/exceptions logged verbatim | Mask or strip sensitive data from logs |
| List response triggers too many queries | Lazy-loading nested associations or projection accessing many relations | Inspect SQL, fetch plans, and query strategies |

## 16. Checklist for Auditing Projections, Excerpts, and Secrets

- Declare projections with `@Projection(name, types)`.
- Place interfaces in the domain type's package or a subpackage.
- Use the exact projection name in the query parameter.
- Configure `excerptProjection` for collections needing a default summary shape.
- Test collection, item, search result, and association representations separately.
- Do not assume excerpts automatically apply to item resources.
- Audit getters, nested projections, and SpEL for sensitive field access.
- Use `@JsonIgnore` for fields outside the JSON contract and `WRITE_ONLY` when only accepting input.
- Never return password hashes, tokens, API keys, or secrets via projections.
- Use DTOs/request models and server-side validation to restrict writable fields.
- Use Spring Security to control who can read resources; projections are not authorization.
- Test JSON bodies, response headers, error responses, and logs.
- Check query counts when projections access nested associations.

## Conclusion

Projections allow Spring Data REST to produce multiple representations from the same entity; excerpt projections provide a default summary shape for entities in collection resources. You can select projections via query parameters or configure excerpts on repositories. Distinguish collections from items because excerpts do not automatically alter an item's default representation. More importantly, projections only control how data is presented in a response; they do not replace authentication, authorization, or request validation. Protect secrets at serialization boundaries, separate read projections from write DTOs when strict allow-lists are needed, and test every response path that can expose an entity.

## References

- Spring Data REST – Projections and Excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
- Spring Data REST – Projection API: https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/ProjectionDefinitionConfiguration.html
- Spring Data Commons – Projection and interface-based projection concepts: https://docs.spring.io/spring-data/commons/reference/repositories/projections.html
- Jackson – JsonProperty.Access and JsonIgnore annotations: https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.Access.html
