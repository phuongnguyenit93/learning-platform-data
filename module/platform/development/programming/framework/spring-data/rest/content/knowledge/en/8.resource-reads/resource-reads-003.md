# Single Resource GET and the findById Method

## Objectives

In Spring Data REST, a `GET` request to an item URI is used to read a single resource by the repository's identifier. For example, `GET /people/42` asks the server to find the entity with ID `42` and return that entity's representation.

At the repository layer, this operation relies on the `findById(ID id)` method inherited from `CrudRepository` or `JpaRepository`. Spring Data REST extracts the ID from the path, converts it to the Java ID type, and invokes the repository's item lookup mechanism. Understanding the relationship between the URI, ID type, and `findById` helps handle found, not-found, and malformed ID cases properly.

## 1. Collection resources and item resources

Suppose we have a Person entity and repository:

~~~java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    // constructors, getters, setters
}
~~~

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Spring Data REST exports the repository as a collection resource and item resources:

| URI | Meaning |
|---|---|
| `GET /people` | Read the people collection |
| `GET /people/42` | Read the item with ID 42 |
| `GET /people/57` | Read the item with ID 57 |

If the application sets a base path with `spring.data.rest.base-path=/api`, the corresponding URIs will be `/api/people`, `/api/people/42`, and `/api/people/57`.

A collection request typically goes through a list-reading operation on the repository, such as `findAll(Pageable)` or a variant supported by the repository. An item request requires a specific identifier and goes through an entity lookup by ID.

## 2. Processing flow of a single-resource GET

Given the request:

~~~http
GET /people/42
Accept: application/hal+json
~~~

High-level processing flow:

1. `RepositoryRestHandlerMapping` recognizes that the path `/people/42` belongs to the repository exported as `people`.
2. Spring Data REST determines the repository's ID type. In this example, the ID type is `Long`.
3. The value `42` extracted from the path is converted from a string to `Long` using Spring's conversion mechanism.
4. Spring Data REST invokes the item lookup operation via the repository invoker. For a standard CRUD repository, this operation uses `findById(42L)`.
5. If the entity is found, Spring Data REST builds the resource representation and returns an HTTP response. If no entity exists, the request is handled as a non-existent resource.

This path is a read operation. It does not call `save()` and does not create a new entity.

## 3. findById() in the repository

`CrudRepository` declares the method:

~~~java
Optional<T> findById(ID id);
~~~

Where:

- `T` is the entity type, such as `Person`.
- `ID` is the identifier type declared as the second generic parameter of the repository, such as `Long`.
- The result is `Optional<T>` to represent the presence or absence of an entity with that ID.

Example:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

It can be called from a service or regular Java code:

~~~java
Optional<Person> result = personRepository.findById(42L);

result.ifPresent(person -> {
    System.out.println(person.getFirstName());
});
~~~

Or handling the not-found case:

~~~java
Person person = personRepository.findById(42L)
    .orElseThrow(() -> new PersonNotFoundException(42L));
~~~

Spring Data REST performs the item lookup for HTTP GET. You do not need to write a custom Controller just to call `findById` if the repository's default item endpoint meets your needs.

### 3.1. findById is a reserved method for the identifier

The name `findById` is a reserved CRUD repository method: its parameter is the entity's actual identifier, as declared with `@Id`. It is not simply a derived query method inferred from an arbitrary property named `id`.

For example, an entity has a primary key named `personKey` while also having a business property named `id`:

~~~java
@Entity
public class Person {

    @Id
    private Long personKey;

    private String id;
    private String name;
}
~~~

Repository:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    Optional<Person> findPersonById(String id);
}
~~~

The two methods have different meanings:

- `findById(Long id)` is the reserved CRUD method, searching by the primary key `personKey`.
- `findPersonById(String id)` is a query method parsed by property name, searching by the business property `id`.

The descriptive token `Person` between `find` and `By` helps avoid colliding with the reserved CRUD method name. When reading or designing a repository, inspect the field annotated with `@Id` rather than assuming the primary key from field names alone.

### 3.2. The ID type must match the repository

The ID type is declared in the repository generics:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {
}
~~~

For this repository, Spring Data REST needs to convert the URL ID segment to `UUID`. A request might look like:

~~~http
GET /orders/9f7c2a8e-3d2a-4a6c-9f1e-7c9b6a1d1234
~~~

Do not declare a repository with a `Long` ID if the entity actually uses `UUID`, or write a service calling `findById` with an incompatible type. If using a custom ID type, an appropriate converter is required so Spring can convert the URL value to that Java type.

## 4. Request and response when the resource is found

Suppose the database has a Person with ID 42:

~~~http
GET /people/42
Accept: application/hal+json
~~~

A successful response typically has status `200 OK` and a HAL JSON representation, for example:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/42"
    }
  }
}
~~~

The actual fields depend on the entity, Jackson configuration, projections, and exported associations. The `_links.self` section informs the client of the canonical URI of the item. The HAL representation may also provide association links for the client to navigate to related resources.

The client can send `Accept: application/hal+json` to request the HAL JSON format. If the client requests a media type not supported by the endpoint, the server may return an unsupported format error.

## 5. When the ID does not exist or is malformed

Two situations should be distinguished:

### 5.1. Valid ID but no entity exists

For example, the ID is a valid number, but the database has no corresponding Person:

~~~http
GET /people/999999
Accept: application/hal+json
~~~

The repository returns `Optional.empty()`. Spring Data REST handles the non-existent item and typically returns:

~~~http
HTTP/1.1 404 Not Found
~~~

This is the normal result for a not-found lookup. You should not return HTTP 200 with an empty object if the requested URI represents a specific item that does not exist.

### 5.2. ID cannot be converted to the identifier type

For a repository with a `Long` ID type, the following request does not contain a valid ID:

~~~http
GET /people/abc
~~~

Spring cannot convert the string `abc` to `Long`. The error occurs before the repository can look up the entity; the request typically returns HTTP 400 Bad Request.

If the ID is a `UUID`, an improperly formatted UUID string encounters a similar conversion error. When debugging, determine whether the failure happens during path conversion or during the repository lookup.

## 6. Distinguishing findById from other read operations

| Method or request | Purpose | Result |
|---|---|---|
| `GET /people` | Read a collection | Multiple entities, possibly paginated |
| `GET /people/42` | Read a single item by ID | One resource or 404 |
| `findById(42L)` | Repository lookup by identifier | `Optional<Person>` |
| `findAll()` | Repository lookup of all entities | `Iterable<Person>` |
| `findByLastName("Nguyen")` | Query method by property | Entities matching the condition |

`findById` is a lookup by primary key. If you need to search by email, name, business code, or compound criteria, declare a suitable query method or custom query instead of trying to use `findById`.

Example:

~~~java
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    Optional<Person> findByEmail(String email);

    List<Person> findByLastNameOrderByFirstNameAsc(String lastName);
}
~~~

If a query method is exported by Spring Data REST, it usually appears under `/people/search/**`. That is a separate search resource, not the `/people/{id}` item resource.

## 7. Projections and item representations

A found entity can be represented through a projection if the application has declared the projection and registered it for the repository. Clients can request a projection using a query parameter:

~~~http
GET /people/42?projection=personSummary
Accept: application/hal+json
~~~

Projection example:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

A projection changes which properties are included in the representation; it does not change the semantics of lookup by ID. The server still looks up the same item 42, then constructs the representation according to the requested projection. If the projection is not registered or the projection name is invalid, the client should not assume the response will contain the exact expected set of fields.

## 8. Customizing how items are looked up

Normally, keep the default `findById` for the item resource. If the domain needs a separate URI to look up by business key, you can create a dedicated query method and export it as a search resource:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-employee-code", rel = "by-employee-code")
    Optional<Person> findByEmployeeCode(
        @Param("code") String employeeCode);
}
~~~

Client calls:

~~~http
GET /people/search/by-employee-code?code=EMP-0042
~~~

This keeps the semantics clear:

- `/people/42` looks up by the resource identifier.
- `/people/search/by-employee-code?code=EMP-0042` looks up by the business key.

If you want the item URI itself to use a business key instead of the primary key, you must configure an entity lookup strategy appropriate for your Spring Data REST version and ensure identifiers, HAL links, converters, and repository lookups remain consistent. This is a routing/lookup strategy change; do not simply rename a path variable or write a `findById` query method expecting the default endpoint to understand the business key automatically.

## 9. Testing item GET

You can use MockMvc to test the item endpoint. The example below is an integration test skeleton; add repository configuration and test data appropriate to your application:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PersonItemResourceTests {

    @Autowired
    MockMvc mvc;

    @Test
    void getExistingPersonReturnsHalResource() throws Exception {
        mvc.perform(get("/people/42")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.firstName").value("An"))
            .andExpect(jsonPath("$._links.self.href")
                .value(org.hamcrest.Matchers.endsWith("/people/42")));
    }

    @Test
    void getUnknownPersonReturnsNotFound() throws Exception {
        mvc.perform(get("/people/999999")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isNotFound());
    }

    @Test
    void invalidLongIdentifierReturnsBadRequest() throws Exception {
        mvc.perform(get("/people/abc")
                .accept(MediaTypes.HAL_JSON))
            .andExpect(status().isBadRequest());
    }
}
~~~

In real tests:

- Create fixtures with known IDs or read the URI from a POST response instead of relying on auto-generated IDs.
- Use a test database or repository mock appropriate for the test type.
- Assert both the status and the required content/links.
- Verify that requests with malformed IDs and non-existent IDs follow the two distinct error paths.
- If projections are enabled, test representations both with and without the projection query parameter.

## 10. Common errors and troubleshooting

| Symptom | Possible cause | How to check |
|---|---|---|
| Item GET returns 404 | ID does not exist in repository or path is incorrect | Check ID, collection path, and base path |
| Item GET returns 400 | Path ID cannot be converted to the ID type | Check generic ID type and URL format |
| findById queries the wrong field | Confusing the identifier with a property named `id` | Check `@Id` and reserved method semantics |
| Repository declares wrong generic ID | ID type does not match entity | Check `JpaRepository<Person, Long>` and `@Id` type |
| Response is missing expected fields | Projection, Jackson visibility, or serialization configuration | Check projections and representation settings |
| Client cannot navigate to item | Incorrect self URI or base path | Check `_links.self.href` and base path |
| Trying to look up by business code using findById | Business key is not the identifier | Create a dedicated query method or configure an appropriate entity lookup |

## 11. Checklist for using single-resource GET

- Identify the exact collection path exported by the repository.
- Check the Spring Data REST base path.
- Verify the ID type in the repository generics and the `@Id` property.
- Send the identifier in the correct format in the path.
- Use `findById` for primary keys; use dedicated query methods for business keys.
- Handle `Optional.empty()` as not found when writing services.
- Verify status 200, 404, and 400 for each respective scenario.
- Read `_links.self` to use the server-provided resource URI.
- If using projections, verify the projection name and returned representation.

## Conclusion

`GET /people/{id}` reads a single item by the repository's identifier. Spring Data REST extracts the ID from the path, converts it to the Java type, and invokes the corresponding lookup operation, typically `findById(ID)`. `findById` is a reserved CRUD method for the primary key; if you need to look up by a business property named `id` or another code, use a query method with a non-conflicting name. A valid ID that does not exist typically returns 404, while a malformed ID typically returns 400. The final representation can be HAL JSON and is affected by projections and serialization configuration.

## References

- Spring Data Commons – CrudRepository API: https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/repository/CrudRepository.html
- Spring Data REST – Repository resources: https://docs.spring.io/spring-data/rest/reference/repository-resources.html
- Spring Data REST – Projections and excerpts: https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html
- Spring Data JPA – Query methods: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
