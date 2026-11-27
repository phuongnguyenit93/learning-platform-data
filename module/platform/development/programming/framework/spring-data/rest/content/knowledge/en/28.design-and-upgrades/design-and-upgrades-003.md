# Managing Field Name, Path, Rel, and Projection Changes in Spring Data REST

## Objectives

A Spring Data REST API has many names appearing together in the HTTP contract while serving different roles:

- **Java property name:** field/getter name in an entity or projection.
- **Database column name:** physical name in the schema, which may differ from the Java name.
- **JSON field name:** key that clients read or send in the request body.
- **Path:** URL segment used to access a collection, item, association, or query method.
- **HAL relation (rel):** relation name in `_links`, helping clients understand what resource type a link points to.
- **Projection name:** name clients pass in the `projection` query parameter.

Changing one name does not necessarily require changing all the others. However, if clients depend on the old name, a change can break requests or prevent clients from finding expected links/fields.

This lesson explains how to classify changes, preserve compatibility during transitions, configure path/rel/projection settings, apply versioning strategies, and test API contracts before removing old names.

## 1. Distinguishing Name Types in the API Contract

Example entity:

~~~java
@Entity
@Table(name = "person")
public class Person {

    @Id
    private Long id;

    @Column(name = "display_name")
    private String displayName;

    private String familyName;
}
~~~

The JSON representation might be:

~~~json
{
  "displayName": "Lan",
  "familyName": "Nguyen"
}
~~~

The names here have different meanings:

| Layer | Example Name | Where Used |
| --- | --- | --- |
| Java property | `displayName` | Entity, getter, repository query derivation |
| Database column | `display_name` | Schema and SQL |
| JSON property | `displayName` | Request/response body |
| Collection path | `/people` | Collection URL |
| Item path | `/people/42` | Single entity URL |
| Collection rel | `people` | Key in `_links` |
| Query method path | `by-family-name` | Search endpoint URL |
| Query method rel | `byFamilyName` | Key in search links |
| Projection name | `personSummary` | `?projection=personSummary` |

Do not accidentally treat Java class names or database column names as the HTTP contract. Intentionally define public names so internal implementation changes have less impact on clients.

## 2. Evaluating Whether a Change Is Additive or Breaking

Before renaming, identify which clients use the current contract and which category the change falls into.

| Change | Compatibility Risk |
| --- | --- |
| Add optional JSON field | Usually additive, though strict-schema clients may reject it |
| Remove or rename JSON field | Breaking for clients reading/sending the old name |
| Add new collection path | Additive if the old path continues to work |
| Change collection path | Breaking for clients hardcoding the old URL |
| Change HAL rel | Breaking for clients looking up links by the old rel |
| Change search path or rel | Breaking for clients calling the old query resource or looking up the old rel |
| Change projection name | Breaking for clients sending `?projection=oldName` |
| Change default excerpt | Potentially breaking because embedded representation changes |
| Change data type or nullability | Potentially breaking even if the field name stays the same |
| Change field ordering/business meaning | Semantically breaking even if JSON still parses |

Do not judge compatibility solely by whether an endpoint still returns HTTP 200. A client may receive 200 yet no longer find the field or relation it requires.

A change is considered safer when old clients continue to work during a transition period with a clear upgrade window.

## 3. Renaming a Java Property While Keeping the Database Column

Suppose older code used:

~~~java
private String name;
~~~

Newer code wants to use `displayName`, while the database still keeps the `display_name` column or an existing legacy column.

Use `@Column(name = ...)` to decouple the Java name from the physical column name:

~~~java
@Entity
@Table(name = "person")
public class Person {

    @Id
    private Long id;

    @Column(name = "name")
    private String displayName;
}
~~~

The entity can rename the Java property to `displayName` without renaming the database column. Repository query derivation, getters, projections, and JSON mappings may need to be updated to match the new Java property.

This does not automatically preserve the old JSON field. If clients send `name` and responses return `name`, separate JSON compatibility configuration is required.

Decoupling schema migration from API migration avoids having to change database columns and client contracts in the same release.

## 4. Keeping JSON Names Stable with @JsonProperty

If you want to rename a Java property while preserving the public JSON name, you can use Jackson's `@JsonProperty`:

~~~java
@Entity
public class Person {

    @Id
    private Long id;

    @JsonProperty("name")
    private String displayName;
}
~~~

When serialized, the property can continue to appear under the key `name`, even though the Java name is `displayName`.

This is useful when refactoring internal code without changing the API contract. Verify which field/getter the annotation is placed on and check Jackson visibility settings for the entity in the Spring Data REST configuration.

If you want to change the JSON name from `name` to `displayName`, simply changing `@JsonProperty` to the new name will break old clients expecting the field. A transition strategy is required in that case.

## 5. Accepting Legacy JSON Names with @JsonAlias

Jackson's `@JsonAlias` allows the deserializer to accept additional legacy names when reading requests:

~~~java
@Entity
public class Person {

    @Id
    private Long id;

    @JsonProperty("displayName")
    @JsonAlias("name")
    private String displayName;
}
~~~

Meaning:

- Response serialization uses the primary name `displayName`.
- Request deserialization can accept both `displayName` and the alias `name`.
- `@JsonAlias` does not cause responses to emit both keys simultaneously.

For example, an old client sends:

~~~json
{
  "name": "Lan"
}
~~~

and a new client sends:

~~~json
{
  "displayName": "Lan"
}
~~~

Both can bind to the same property if Jackson and Spring Data REST are configured to honor that annotation.

**Important limitation:** aliases only assist with reading input. If old clients still need the `name` key in responses, `@JsonAlias` does not meet that requirement. To return both old and new names during a transition period, use an explicitly designed representation/DTO or custom serializer; avoid creating two Java properties that write to the same field and cause conflicts.

For PUT, PATCH, and JSON Merge Patch operations, test both keys and the behavior when a payload sends both old and new names simultaneously. Do not allow two different values to overwrite the same property without a clear precedence rule.

## 6. Changing Collection Paths with @RepositoryRestResource

Spring Data REST lets you customize a repository's path:

~~~java
@RepositoryRestResource(path = "persons")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

The collection resource has the path `/persons`; item resources have the form `/persons/{id}`.

If the path was previously `/people`, changing it to `/persons` will break old URLs unless a compatibility route exists.

Distinguish path from relation:

~~~java
@RepositoryRestResource(
    path = "persons",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Here:

- `path = "persons"`: URL path used to invoke the collection.
- `collectionResourceRel = "people"`: relation name used in HAL links to the collection.

The two values can differ. HATEOAS clients should look up the appropriate relation and follow `href`, rather than constructing paths from the relation name.

Changing the path does not automatically rename the entity, database table, or Java repository. It only changes the URI mapping published by the exporter.

## 7. Keeping Old Paths During a Transition Period

If many clients are calling the old path, do not delete it immediately upon releasing the new path.

A possible roadmap:

1. Publish the new path.
2. Maintain the old path via a compatibility route or gateway rewrite.
3. Log requests to the old path to see which clients still use it.
4. Announce the end-of-support date.
5. Migrate clients to the new links provided by HAL.
6. Remove the old path only after the support window expires and legacy traffic drops to an acceptable level.

For GET, redirects may be an option if clients handle redirects and hypermedia responses properly. For PUT/PATCH/DELETE or requests with bodies, choose a method-and-body-preserving redirect status (such as 307 or 308) and verify client, proxy, and authentication behavior. Do not blindly use 301/302 for write requests because some clients may change the method to GET.

Another option is having an API gateway rewrite the old path to the new path. When using a gateway, also check:

- The rewritten request path.
- The `Location` header when POST creates a resource.
- HAL `self`, `next`, `prev`, and association hrefs.
- ETag/Last-Modified and cache keys.
- Authentication, CORS, and logging.

If the gateway only rewrites requests while responses still emit new-path links, old clients may still work if they follow links; clients hardcoding the old path will need updating.

## 8. Changing Collection Rel Without Changing Path

A HAL relation describes the meaning of a link, whereas the path is the access address.

Example:

~~~java
@RepositoryRestResource(
    path = "persons",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

The HAL root may contain:

~~~json
{
  "_links": {
    "people": {
      "href": "https://api.example.com/api/persons"
    }
  }
}
~~~

If `collectionResourceRel` is changed from `people` to `persons`, the URL may remain the same, but clients looking for the `people` key will no longer find the link under the old name.

Hypermedia reduces URL coupling, yet clients still have to know the relation name they need. Therefore, changing a rel is also a contract change if clients rely on the old rel.

Spring Data REST allows only a single `collectionResourceRel` value on the repository annotation. Do not assume declaring two names in the same attribute will generate two relation aliases. If you need to maintain the old rel, add a compatibility link via a custom representation/processor or custom controller, and test the actual links in the HAL response.

Keeping relations stable is usually the best option when only the URL path needs to change. If there is no business reason to change the rel, preserving the old rel reduces how many clients must update.

## 9. Changing Query Method Paths and Rels

Query methods are exposed using `@RestResource`. Example:

~~~java
@RestResource(
    path = "by-family-name",
    rel = "byFamilyName"
)
List<Person> findByFamilyNameIgnoreCase(
        @Param("familyName") String familyName);
~~~

Three names to distinguish:

| Component | Example | Role |
| --- | --- | --- |
| Java method | `findByFamilyNameIgnoreCase` | Repository method name |
| Search path | `by-family-name` | Query endpoint URL |
| Search rel | `byFamilyName` | Key in search resource `_links` |

If you want to change the URL while keeping the rel, change only `path`. If you want to change the rel while keeping the URL, change only `rel`. Do not change both at once without a clear reason and client migration plan.

Example keeping the old path while renaming the Java method:

~~~java
@RestResource(
    path = "by-last-name",
    rel = "byFamilyName"
)
List<Person> findByFamilyNameIgnoreCase(
        @Param("familyName") String familyName);
~~~

Clients continue calling the old path; the search resource publishes the new relation. If clients look up links using the old rel, a relation alias period is needed.

Also check business query parameter names such as `familyName`. Renaming a Java parameter or `@Param` can change the query URL; this is a different part of the contract from path/rel.

## 10. Changing Projection Names

Projections are published with `@Projection(name = ...)`:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getDisplayName();

    String getFamilyName();
}
~~~

Clients select a projection using:

~~~http
GET /api/persons/42?projection=personSummary
Accept: application/hal+json
~~~

If renamed to `personCard`, clients sending `projection=personSummary` may stop working if the old projection is deleted or not detected.

You can keep the old name as an alias by retaining the old projection interface and adding a new interface:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getDisplayName();

    String getFamilyName();
}
~~~

~~~java
@Projection(name = "personCard", types = Person.class)
public interface PersonCard {

    String getDisplayName();

    String getFamilyName();
}
~~~

Two projections can provide the same set of fields under two different public names. Both must be discovered or registered by Spring Data REST.

Do not just rename the Java interface and assume clients will still work. The public identifier is the value in `@Projection(name = "...")`, not necessarily the class name.

## 11. Changing excerptProjection Is Changing the Default Representation

A repository can configure an excerpt:

~~~java
@RepositoryRestResource(
    path = "persons",
    excerptProjection = PersonSummary.class
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

The excerpt is applied when items are embedded in collections or related resources. If the excerpt changes from PersonSummary to PersonDetails, embedded items may include additional fields, nested associations, or larger payloads.

If clients rely on an old field in the collection response, changing the excerpt can break clients even though the item endpoint still returns the full representation.

Before changing an excerpt:

- Compare the collection JSON/HAL before and after.
- Confirm old fields still exist if clients need them.
- Check whether nested projections open additional associations or sensitive data.
- Measure payload size and query counts because a new excerpt may increase lazy loading.
- Consider keeping the old projection for explicit client selection.
- Clearly announce changes if the embedded contract is no longer compatible.

An excerpt is the default configuration for embedded representations; it is not an alias for a projection name and does not automatically apply to single item resources.

## 12. Field Renames Affect Query Methods and Projections

When renaming a Java property from `lastName` to `familyName`, the following places may need updates:

- Derived queries: `findByLastName` to `findByFamilyName`.
- Sorting: `sort=lastName,asc` to `sort=familyName,asc`.
- Projection getters: `getLastName()` to `getFamilyName()`.
- JSON properties if not stabilized with `@JsonProperty`.
- Validation, specifications, Querydsl bindings, and custom mappers.
- Tests, documentation, and client-generated code.

JSON names and query property names do not have to be identical. For example, JSON can keep `family_name` while the repository property remains `familyName`. However, Spring Data REST sorting/searching typically relies on domain property paths by framework convention; do not assume a changed JSON name automatically renames query parameters.

If you need to keep an old query URL during transition, you can retain the old query method or create an alias method with a different `@RestResource(path = "...", rel = "...")` delegating to the same service/query implementation. Avoid maintaining two independent query implementations that return different results.

## 13. Versioning When Compatibility Cannot Be Preserved

If a change is genuinely breaking, consider versioning rather than silently altering a contract currently in use.

Example:

~~~text
/api/v1/persons
/api/v2/persons
~~~

A common approach is setting the Spring Data REST base path per version:

~~~properties
spring.data.rest.base-path=/api/v1
~~~

However, `spring.data.rest.base-path` is a setting for the exporter within a single ApplicationContext. Do not assume that declaring two base path values in the same `RepositoryRestConfiguration` will cause one application to automatically export two independent versions of repository resources simultaneously.

If v1 and v2 must run in parallel, architectural options may include:

- Two deployments/application contexts with different base path configurations.
- An API gateway routing versions to the corresponding deployment.
- Custom controllers/DTOs for the new version while the old repository exporter continues serving v1.
- A dedicated API façade controlling representations and mappings for each version.

Choose an implementation approach matching the degree of difference between the two contracts and operational capabilities. Do not create two repository exporters managing the same entity in the same context without clearly defining mapping, handler ordering, and transaction behavior.

Media-type or header-based versioning can also be designed at the API layer, but Spring Data REST does not automatically turn one repository into multiple independent representation versions simply by adding arbitrary headers. Explicit content negotiation/controller configuration and thorough testing are required.

## 14. The Expand-and-Contract Process

A safe strategy is to expand the contract first, migrate clients, and only then remove old names.

### Phase 1: Expand

- Add new fields or projections.
- Add new routes/query methods if needed.
- Keep old paths, rels, projections, and fields.
- If renaming input fields, accept both old and new names via aliases or compatibility endpoints.
- Update documentation and link discovery.

### Phase 2: Migrate Clients

- Switch clients to the new fields, paths, rels, and projections.
- Prefer following HAL `href`s rather than hardcoding URLs.
- Monitor traffic on old endpoints/parameters.
- Add deprecation notices where appropriate.
- Test supported client versions.

### Phase 3: Contract

- Verify that old clients have migrated or reached end-of-support.
- Remove legacy field aliases, projections, paths, or rels.
- Update contract tests and documentation.
- Monitor 404s, 400s, and requests containing old names after release.

Do not delete old names simply because the new client works in a test environment. Base decisions on telemetry and actual client support policies.

## 15. Announcing Deprecation and End-of-Support Dates

When an old path or representation will be removed, notify clients sufficiently early.

Standard HTTP response headers can be used according to API policy:

~~~http
Deprecation: @1798761600
Sunset: Wed, 01 Dec 2027 00:00:00 GMT
Link: <https://docs.example.com/migrations/persons-v2>; rel="deprecation"
~~~

The example above only illustrates formatting; dates must be replaced with actual release schedules. The `Deprecation` header is defined in RFC 9745; `Sunset` in RFC 8594. Clients do not always automatically act on these headers, so migration documentation and direct communication with integrating teams are still necessary.

You can emit metrics/logs counting requests to old routes, but do not include raw user data or tokens in logs. Use route names or low-cardinality tags for tracking.

## 16. Contract Testing for Fields, Paths, Rels, and Projections

Contract tests need to verify multiple aspects.

### Testing Collection Path and Rel

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonApiContractTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rootPublishesPeopleCollectionRelation() throws Exception {
        mockMvc.perform(get("/api")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$._links.people.href")
                    .value(containsString("/api/persons")));
    }
}
~~~

The test confirms the `people` relation points to `/api/persons`. If either changes, update the assertion according to the intended contract.

### Testing JSON Properties

~~~java
@Test
void personRepresentationUsesStableJsonPropertyName()
        throws Exception {

    mockMvc.perform(get("/api/persons/{id}", 42)
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").exists())
        .andExpect(jsonPath("$.name").doesNotExist());
}
~~~

### Testing Projection Names

~~~java
@Test
void newProjectionNameIsAvailable() throws Exception {
    mockMvc.perform(get("/api/persons/{id}", 42)
            .param("projection", "personCard")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.displayName").exists());
}
~~~

### Testing Search Rel/Path

~~~java
@Test
void searchResourcePublishesNewFinderRelation() throws Exception {
    mockMvc.perform(get("/api/persons/search")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._links.byFamilyName.href").exists());
}
~~~

In addition to new tests, keep compatibility tests for old names during the migration period:

- Old paths are still served or redirected properly.
- Old rels are still published if the contract requires aliases.
- Old projections can still be selected.
- Request bodies using legacy JSON aliases still bind properly.
- Responses do not accidentally leak sensitive fields.
- ETag, Location, association links, and paging links use the new paths properly.

## 17. Checking ALPS and Link Discovery After Contract Changes

Spring Data REST provides profile/ALPS metadata via the `profile` link. Metadata can describe domain properties, search descriptors, and projection descriptors.

After changing a field, search path/rel, or projection name:

1. Call the API root and check the `profile` link.
2. Follow the domain resource's profile link.
3. Check field descriptors and projection names.
4. Call the search resource and check query method relations.
5. Call collections/items and check `self`, association, and paging links.
6. Compare metadata with the documentation clients are using.

ALPS aids metadata discovery but does not replace OpenAPI/contract documentation if the application needs full descriptions of request schemas, response schemas, authorization, and error semantics.

## 18. Caching, ETags, and URLs After Path Changes

Changing a path or query parameter can produce a new request URI. HTTP cache keys are based at a minimum on the method and target URI; therefore, responses from the old path and new path are not automatically the same cache entry.

After migration:

- Do not transfer ETags from the old path to the new path unless the server confirms they share the same validator.
- Invalidate cache entries for old paths/rels/queries when data or representations change.
- Check `Location`, `self`, `next`, `prev`, and association hrefs.
- Check whether gateway rewrites alter the URI used for caching.
- Check canonical URLs and redirects to avoid duplicate caches or redirect loops.

A new path may return the same entity, but that does not mean an old ETag is valid for the new URI. Let the server issue validators for the exact resource URI.

## 19. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Java property renamed but database query fails | Derived query or mapping still uses old name | Update method/property path and keep column via @Column if needed |
| JSON response loses old field | @JsonProperty renamed without compatibility plan | Use input aliases or DTO/custom representation to keep old output |
| @JsonAlias does not keep old field in response | Alias only affects deserialization | Use DTO/serializer if both keys must be returned |
| Collection URL changed but client cannot find link | Path and rel confused as one | Check path and collectionResourceRel separately |
| HATEOAS client fails after changing rel | Client looks up relation by old name | Keep rel or emit compatibility link during transition |
| Search endpoint stops working | @RestResource path or rel changed | Maintain finder alias and inspect search resource |
| Old projection not selected | @Projection(name) changed or old interface deleted | Keep projection alias for legacy clients |
| Collection embedded items change fields | excerptProjection changed | Verify excerpt contract and version/migration |
| Gateway rewrites yet Location is still wrong | Response links generated from different URI/mapping | Check forwarded headers, base path, and response links |
| v1/v2 do not coexist as expected | One RepositoryRestConfiguration has only one base path | Split deployments/contexts or use a custom API façade |
| Old ETag sent to new URL | Cache/validator keyed only by entity ID | Key validators by URI/representation key |
| Old client fails despite 200 status | Important field or relation disappeared | Write contract tests for fields/rels/projections, not just status |

## 20. Change Management Workflow

1. Inventory current JSON fields, paths, rels, search paths, and projection names.
2. Identify which clients use each name and how they locate resources.
3. Classify changes as additive or breaking.
4. Separate Java/database renames from JSON renames.
5. If changing JSON fields, define response and request alias policies separately.
6. If changing paths, keep old routes or provide suitable redirect/gateway mappings.
7. If changing rels, maintain compatibility links or preserve old relations during transition.
8. If changing projections, preserve old projection names for active clients.
9. If changing excerpts, compare embedded representations and payloads.
10. Consider a new API version when compatibility cannot be preserved.
11. Update HAL/ALPS, documentation, and contract tests.
12. Monitor legacy traffic before removing aliases.
13. After migration, verify caching, ETags, Location, and association links.

## References

- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html): customizing repository paths, collection relations, and resource mappings.
- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): projection names, excerpt projections, and representations of embedded resources.
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, search resources, and HAL links.
- [Spring Data REST — ALPS metadata](https://docs.spring.io/spring-data/rest/reference/alps.html): profile descriptors, properties, search resources, and projection metadata.
- [Jackson — JsonProperty](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.html) and [JsonAlias](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonAlias.html): public JSON names and deserialization aliases.
- [RFC 9745 — The Deprecation HTTP Response Header Field](https://www.rfc-editor.org/rfc/rfc9745.html): signaling deprecation to API clients.
- [RFC 8594 — The Sunset HTTP Header Field](https://www.rfc-editor.org/rfc/rfc8594.html): announcing when a resource is expected to become unavailable.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): redirect semantics, Location, and method-preserving redirects.