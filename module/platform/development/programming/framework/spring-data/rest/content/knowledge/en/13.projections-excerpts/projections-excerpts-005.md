# Nested Projections and Changing How Relationships Are Displayed in Spring Data REST

## 1. What problem do nested projections solve?

Spring Data REST exports resources from repositories in HAL format. An entity with a relationship property can be represented differently depending on whether the related entity has its own repository:

- If `Person` has an `address` property and `Address` has its own repository, the default Person resource typically provides a `_links.address` link so clients can navigate to `/people/{id}/address`.
- If `Address` does not have its own repository, Address fields may be embedded directly inside the representation of Person.
- Projections allow selecting the set of returned properties and changing how relationships appear in the representation. A projection with a getter for a relationship can inline the relationship data; the client may still receive the relationship link for navigation.

Projections are a data presentation layer for REST responses. They do not change JPA relationship mappings, do not create extra repositories or endpoints, and do not modify stored data. Use projections when different clients or screens need different views over the same aggregate.

Example domain model:

```java
@Entity
public class Person {
    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    @OneToOne
    private Address address;

    // getters/setters
}

@Entity
public class Address {
    @Id
    @GeneratedValue
    private Long id;

    private String street;
    private String city;
    private String country;

    // getters/setters
}
```

Repositories exported by Spring Data REST:

```java
public interface PersonRepository extends CrudRepository<Person, Long> {
}

public interface AddressRepository extends CrudRepository<Address, Long> {
}
```

When a repository exists for Address, the default response of `GET /people/1` may contain Person data and a link to Address:

```json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "_links": {
    "self": { "href": "http://localhost:8080/people/1" },
    "address": { "href": "http://localhost:8080/people/1/address" }
  }
}
```

The client needs an extra GET request to the `address` link if it wants to display the address. If many screens always need the city and country, a nested projection can bring those exact fields into the Person response.

## 2. Defining a projection for nested relationships

Spring Data REST uses interfaces annotated with `@Projection`. Getters define the exported properties. For nested relationships, a getter's return type can be another projection interface. Spring Data Commons supports recursive projections: the relationship property is retrieved from the target object and wrapped in the corresponding projection proxy.

The following example includes only `city` and `country` of Address in Person, omitting `street`:

```java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "addressSummary", types = Address.class)
public interface AddressSummary {
    String getCity();
    String getCountry();
}

@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {
    String getFirstName();
    String getLastName();

    AddressSummary getAddress();
}
```

Place the projection interfaces in the same package as their respective domain types or in a sub-package so Spring Data REST discovers them automatically. In the example above, `AddressSummary` should reside in a package scanned for Address and `PersonWithAddress` in a package scanned for Person. If your package layout differs, you can register projections manually using `RepositoryRestConfiguration.getProjectionConfiguration().addProjection(...)`. A projection interface must carry `@Projection`.

The name used in the URL is the annotation's `name` value, not the Java interface name. For example:

```http
GET /people/1?projection=personWithAddress
```

The representation might look like this:

```json
{
  "firstName": "Frodo",
  "lastName": "Baggins",
  "address": {
    "city": "Hobbiton",
    "country": "The Shire"
  },
  "_links": {
    "self": { "href": "http://localhost:8080/people/1{?projection}" },
    "address": { "href": "http://localhost:8080/people/1/address" }
  }
}
```

Points to remember:

- `AddressSummary getAddress()` selects the projection for the Address object at the nested level; no new endpoint is needed.
- Getters not declared in the projection will not be exported in the data portion of that projection.
- The `_links.address` link remains useful for clients to navigate to the standalone Address resource. Inline data and links can coexist.
- If the relationship is a collection, you can declare a getter returning a collection of projections matching the relationship elements, and then verify the actual representation with an integration test.
- The projection name is an API contract. Renaming it can break clients calling `?projection=...`.

## 3. Selecting a projection per request

When multiple representations are needed, you can declare multiple projections for the same domain type:

```java
@Projection(name = "personNames", types = Person.class)
public interface PersonNames {
    String getFirstName();
    String getLastName();
}

@Projection(name = "personWithAddress", types = Person.class)
public interface PersonWithAddress {
    String getFirstName();
    String getLastName();
    AddressSummary getAddress();
}
```

Clients select the desired representation using the query parameter:

```bash
# Fetch names only
curl -i "http://localhost:8080/people/1?projection=personNames"

# Fetch names along with selected address fields
curl -i "http://localhost:8080/people/1?projection=personWithAddress"
```

The query parameter value must match `@Projection(name = "...")` exactly. If `projection` is omitted, Spring Data REST uses the default representation, unless the collection resource has an excerpt projection configured.

Projections can be found in ALPS metadata. Follow the `profile` link at the root resource and inspect the ALPS document for the resource, such as `/alps/people`. The descriptor for the GET transition lists projection names and the properties each projection exports. This is a useful way for clients to discover supported representations without guessing names.

## 4. Using excerptProjection to change the collection default

An excerpt is a projection automatically applied when an item resource is embedded in a collection or related resource. You can set a default excerpt on the repository:

```java
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(excerptProjection = PersonWithAddress.class)
public interface PersonRepository extends CrudRepository<Person, Long> {
}
```

With this configuration, Person entries in a collection response such as `GET /people` can carry the inline Address according to the chosen projection. The link to Address can still be retained in `_links`.

Distinguish between the two ways of applying projections:

| Approach | Scope |
| --- | --- |
| `?projection=personWithAddress` | Explicitly selects a projection for a resource request, such as a single item GET. |
| `excerptProjection = PersonWithAddress.class` | Selects the default excerpt when Person is embedded in a collection or related resource. |

An excerpt projection **does not automatically apply to a single-item resource GET**. Therefore, if `GET /people` displays Address inline while `GET /people/1` only has an Address link, that is expected behavior. To apply the projection on the item, send `GET /people/1?projection=personWithAddress`.

Adding an excerpt projection to a repository can change the default response that existing clients rely on. Before deploying, check clients depending on the old JSON structure and treat this change as an API contract change.

## 5. Customizing relationship data and computed data

A projection interface only declares getters for the fields to export. You can combine regular getters with nested relationship getters:

```java
@Projection(name = "personCard", types = Person.class)
public interface PersonCard {
    String getFirstName();
    String getLastName();
    AddressSummary getAddress();
}
```

If a virtual field computed from multiple properties is needed, Spring Data supports `@Value` with SpEL:

```java
@Projection(name = "personLabel", types = Person.class)
public interface PersonLabel {
    @Value("#{target.firstName + ' ' + target.lastName}")
    String getDisplayName();
}
```

Projections using `@Value` are open projections because the expression can access properties of the target. Spring Data cannot optimize queries based on a fixed set of properties as it does with closed projections. For simple calculations based only on other getters of the projection, you can use a default method:

```java
@Projection(name = "personLabel", types = Person.class)
public interface PersonLabel {
    String getFirstName();
    String getLastName();

    default String getDisplayName() {
        return getFirstName() + " " + getLastName();
    }
}
```

For cases that only require selecting existing properties, prefer closed projections with getters matching aggregate properties. Spring Data Commons DTO/class-based projections do not support nested projections; when you need to shape relationships deeply via proxies, use interface-based projections.

## 6. Limitations and caveats when changing relationship display

**A projection is not a fetch plan.** Having a relationship getter in a projection can cause the application to access the association during serialization. With JPA, consider lazy loading, SQL query count, and the risk of N+1 queries when returning large collections. Closed projections may help Spring Data optimize certain queries depending on the store module; do not assume every association is fetched in a single SQL query. Measure query counts and inspect the data loading plan with your store.

**Do not use projections as your sole security mechanism.** Spring Data REST warns that a projection can expose even properties annotated with `@JsonIgnore` in the response if the projection declares a matching getter. Therefore, review every exported projection, especially fields like passwords, tokens, secrets, personal information, or internal attributes. Access must be protected through domain design, serialization settings, and proper authorization; do not assume `@JsonIgnore` always hides data from every projection.

**Keep links when clients need navigation.** Inlining relationship data does not mean removing HAL links. Links let clients access related resources independently, while inline data reduces extra requests for frequently used fields.

**Check for null and cardinality.** A relationship may be null or an empty collection. Test cases with a relationship, without a relationship, and with multiple elements. Do not assume every entity has an Address.

**Do not confuse projections with mapping changes.** If you need to change cardinality, cascade, owning side, foreign key, or how a relationship is persisted, modify the domain mapping and appropriate migration. Projections only control the REST representation.

## 7. Troubleshooting workflow when nested projections do not work

1. **Check the URL and projection name.** Call the right resource and use the `name` value in `@Projection`, such as `?projection=personWithAddress`; the Java interface name does not determine the query parameter.
2. **Check projection discovery.** Confirm the interface has `@Projection`, the right `types`, sits in the entity's package or a sub-package, or is manually registered via `ProjectionConfiguration`.
3. **Check getters and return types.** Getter names must match domain object properties. For nested projections, the return type must be a projection interface for the corresponding relationship type. Check spelling of `getAddress()`, the Address type, and child getters such as `getCity()`.
4. **Check repositories and associations.** Confirm the right resources are exported, relationships are mapped correctly, and the association has data. If Address has its own repository, the default representation is usually a link; if it has no repository, data may already be embedded by default.
5. **Distinguish item projection from excerpt.** If only `excerptProjection` is configured, check the collection or related resource response. For an item GET, add the `projection` query parameter.
6. **Inspect the HAL response.** Check inline data at the relationship property and links in `_links`. Do not test the response body merely by searching for an arbitrary string; use specific JSON paths.
7. **Check lazy loading and serialization.** If relationship getters cause errors or too many queries, check transactions, fetch strategies, SQL logs, and null data. Do not try to fix N+1 issues just by adding more getters to the projection.
8. **Check compatibility changes.** If you just added `excerptProjection`, compare collection responses before and after, and check API consumers.

Common symptoms:

| Symptom | Causes to check |
| --- | --- |
| `?projection=...` does not recognize the name | Wrong `name` value, missing `@Projection`, wrong package scan, or missing manual registration. |
| Address remains just a link | Request did not select the projection, relationship getter is missing in the projection, or return type is not a suitable nested projection. |
| Collection has Address inline but item GET does not | Using an excerpt projection; this difference is by design. Select the projection explicitly on the item. |
| Address is missing or null | Relationship is not assigned, data is absent, getter does not match property, or mapping is incorrect. |
| Response contains overly sensitive fields | Review projection getters; projections can expose even `@JsonIgnore` fields. |
| Large collection executes many SQL queries | Check lazy loading, N+1, and fetch plan; do not assume nested projections optimize queries. |
| Clients break after adding an excerpt | Default collection representation changed; check API contract compatibility. |

## 8. Integration testing with MockMvc

You should verify both nested data and HAL links. The example below assumes the application configures `PersonWithAddress`, has a Person fixture with an Address, and exposes `/people`:

```java
@SpringBootTest
@AutoConfigureMockMvc
class PersonProjectionIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void rendersOnlySelectedNestedAddressFields() throws Exception {
        long personId = /* ID of the saved Person fixture */;

        mockMvc.perform(get("/people/{id}", personId)
                .param("projection", "personWithAddress"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.firstName").value("Frodo"))
            .andExpect(jsonPath("$.address.city").value("Hobbiton"))
            .andExpect(jsonPath("$.address.country").value("The Shire"))
            .andExpect(jsonPath("$.address.street").doesNotExist())
            .andExpect(jsonPath("$._links.address.href").exists());
    }
}
```

Test collection excerpts separately:

```java
@Test
void appliesExcerptProjectionToCollectionEntries() throws Exception {
    mockMvc.perform(get("/people"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._embedded.people[0].address.city")
            .value("Hobbiton"));
}
```

If you need to confirm that the excerpt does not automatically apply to an item resource, test an item GET without the query parameter and compare it with an item GET with `?projection=personWithAddress`. Prepare deterministic fixture data; do not rely on hardcoded test database IDs.

Pre-deployment testing checklist:

- Projection is selected using the exact `@Projection(name = ...)` name.
- Parent entity fields are exported accurately.
- Nested projections export only declared relationship fields.
- Relationship links in `_links` remain present if clients need navigation.
- Collections use the excerpt as configured.
- Item GETs only use excerpts when explicitly applied; test the projection query parameter.
- Null relationships, empty collections, and multi-element cases are tested.
- No unintended sensitive data is exposed.
- Measure SQL/query counts when serializing nested associations to catch N+1 issues.
- Check existing collection responses to detect breaking changes from default excerpts.

## 9. Official documentation

- [Spring Data REST — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): how to declare `@Projection`, select projections via query parameters, discovery, excerpts, and inline associations.
- [Spring Data Commons — Projections](https://docs.spring.io/spring-data/rest/reference/data-commons/repositories/projections.html): interface-based, recursive/nested, closed/open, and DTO projections.
- [Spring Data REST API — @Projection](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/Projection.html): annotation, projection name, and attached domain types.
- [Spring Data REST API — @RepositoryRestResource](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/core/annotation/RepositoryRestResource.html): the `excerptProjection` attribute of repository resources.
- [Spring Data REST — Metadata and ALPS](https://docs.spring.io/spring-data/rest/reference/metadata.html): discovering projections and descriptors via profile/ALPS.
