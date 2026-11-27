# Converting Path Variables, Query Parameters, and Request Bodies

## Objective

In Spring Data REST, an exported repository can automatically provide endpoints for reading, creating, updating, and searching entities. Each HTTP request brings data into the application in one of three common ways:

- **Path variables** in the URL, usually identifying the entity to access.
- **Query parameters** after the question mark in the URL, usually passing search criteria, pagination, or sorting.
- **Request bodies** containing JSON data, usually used when creating or updating an entity.

Spring Data REST works with Spring MVC and Jackson to convert received values into the Java types required by the repository and domain model. Understanding each conversion path helps handle data types properly, configure search endpoints, and diagnose request errors.

## 1. Overall processing flow

For example, a repository managing `people` resources can provide these requests:

| Request | Primary input data | Purpose |
|---|---|---|
| GET /people/42 | Path variable **42** | Find entity with ID 42 |
| GET /people/search/by-last-name?lastName=Nguyen | Query parameter **lastName** | Search entities by last name |
| GET /people?page=0&size=20&sort=lastName,asc | Query parameters **page**, **size**, **sort** | Read a paginated and sorted list |
| POST /people | JSON in request body | Create entity |
| PATCH /people/42 | Path variable and JSON body | Partially update entity |

The processing flow can be pictured as follows:

1. Spring MVC receives the HTTP request and selects the Spring Data REST endpoint corresponding to the repository.
2. Values in the URL are parsed into path variables and query parameters. String values are converted into appropriate Java types via Spring's conversion and binding mechanisms.
3. If the request has a body, an `HttpMessageConverter` reads its content. For JSON, Jackson deserializes JSON into the entity or corresponding data type.
4. Spring Data REST invokes the repository operation, handles links between resources, and runs extension steps configured in the application.
5. The result is converted into an HTTP response. With default configuration, the resource is typically represented as HAL JSON.

These three data sources pass through different mechanisms. Path variables and query parameters mainly use Spring's `ConversionService`; JSON bodies mainly use Jackson via HTTP message converters.

## 2. Path variables: identifying resources via URL

For an exported repository, Spring Data REST typically creates a collection endpoint and an item endpoint. The item endpoint has the form:

~~~http
GET /people/{id}
~~~

The **{id}** part is a path variable. When receiving the request:

~~~http
GET /people/42
~~~

Spring Data REST extracts the string **42**, converts it into the repository's ID type, and uses that ID to look up the entity. If the repository declares its ID as `Long`, the value must be convertible to `Long`. If the repository uses `UUID` or another ID type, conversion must match that type.

Example repository:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

Common scenarios:

- Valid ID and entity exists: the endpoint returns the corresponding resource.
- ID has a format that cannot be converted to the ID type: the request typically fails at the binding/conversion step and returns 400.
- Valid ID conversion, but no corresponding entity exists: the resource is not found and typically returns 404.

Do not take the ID from the body to override the ID in the URL when updating an item. The URL identifies the target resource; the body supplies the resource's values.

## 3. Query parameters: searching, pagination, and sorting

### 3.1. Parameters of repository search methods

Spring Data REST can export repository query methods under the `search` path. Use `@Param` to define the public query parameter name:

~~~java
@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "by-last-name")
    List<Person> findByLastName(@Param("lastName") String value);

    @RestResource(path = "created-after", rel = "created-after")
    List<Person> findByCreatedAtAfter(@Param("from") LocalDate from);
}
~~~

Corresponding requests:

~~~http
GET /people/search/by-last-name?lastName=Nguyen
GET /people/search/created-after?from=2026-01-01
~~~

Spring Data REST reads the query parameter value, converts it to the method parameter's type, and invokes the query method. In the example above:

- **lastName** is passed into a parameter of type `String`.
- **from** is converted into `LocalDate` before calling the method.
- Public query parameter names are determined by `@Param`, and do not have to match the variable names inside the method.

If the data type is a date, number, enum, or custom domain type, the string in the URL must be in a format the corresponding converter understands. A malformed value can cause the request to fail with a 400 error.

### 3.2. Pagination and sorting

Spring Data REST supports standard query parameters for repositories returning pageable lists:

~~~http
GET /people?page=0&size=20&sort=lastName,asc
~~~

- **page**: zero-based page number.
- **size**: number of items requested per page.
- **sort**: property name and sort direction, for example **lastName,asc** or **createdAt,desc**.

Multiple sort criteria can be passed by repeating the parameter:

~~~http
GET /people?sort=lastName,asc&sort=createdAt,desc
~~~

Application configuration can change the default page size, maximum page size limit, and sort handling. Therefore, clients should explicitly send page, size, and sort when predictable results are needed.

### 3.3. URL encoding

Query parameters are data in the URL, so special characters must be URL-encoded. For example, spaces, `&`, `+`, or Vietnamese characters must be properly encoded so the server receives the intended value. `&` separates parameters; if it is part of a value, it must be encoded.

## 4. Request body: converting JSON into an entity

When creating or updating a resource, clients typically send data in the request body. Example creating a person:

~~~http
POST /people
Content-Type: application/json
Accept: application/hal+json

{
  "firstName": "An",
  "lastName": "Nguyen",
  "birthDate": "1998-06-12"
}
~~~

Basic processing steps:

1. The HTTP message converter receives the body according to `Content-Type`.
2. For JSON, Jackson reads the JSON and deserializes properties into the corresponding Java types.
3. Spring Data REST passes the entity to the appropriate repository operation.
4. The response returns the HTTP status and resource representation; on creation, the response typically includes a `Location` header pointing to the newly created resource's URI.

JSON property names must match how Jackson maps entity properties. Dates, times, enums, numbers, and nested objects must be formatted compatibly with Jackson configuration and Java types.

### 4.1. Relationships between entities

In Spring Data REST, associations are represented via resource links. When writing an association, clients typically send the URI of the related resource under the association property name, for example:

~~~http
POST /orders
Content-Type: application/json

{
  "description": "First order",
  "customer": "http://localhost:8080/customers/1"
}
~~~

The URI identifies the existing customer entity that the order should reference. Exact endpoints, association names, and representations depend on the domain model and repository export configuration. Use the URIs provided by the server in HAL responses to reference related resources.

### 4.2. PUT and PATCH

Spring Data REST supports updating an item via the resource's URI:

~~~http
PUT /people/42
Content-Type: application/json
~~~

`PUT` replaces the resource's representation; clients should send all fields that must be preserved according to the API contract.

~~~http
PATCH /people/42
Content-Type: application/json

{
  "lastName": "Tran"
}
~~~

`PATCH` performs a partial update of the resource. Send only the fields that need to change. How `null` values, omitted fields, and specific media types are interpreted depends on the patch mechanism and the application's version/configuration; clients should follow the server's API contract.

## 5. Customizing data type conversion

### 5.1. Path variables and query parameters

Spring's `ConversionService` handles many conversions from URL strings to Java types. Spring already provides converters for common types such as numbers, booleans, enums, and supported date/time types.

If the API uses a custom type, you can register a `Converter<String, T>` via `RepositoryRestConfigurer`:

~~~java
public record TrackingCode(String value) {
}

@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureConversionService(
            ConfigurableConversionService conversionService) {
        conversionService.addConverter(
            String.class,
            TrackingCode.class,
            TrackingCode::new
        );
    }
}
~~~

Converters should validate and reject invalid strings according to domain rules. Conversion errors should be clearly surfaced so clients know which parameter has an invalid format.

### 5.2. JSON request body

JSON bodies are deserialized by Jackson via HTTP message converters. Converters in `ConversionService` do not automatically replace Jackson deserializers for every property in JSON.

To customize how JSON is read, you can use Jackson mechanisms such as:

- `@JsonCreator` and `@JsonProperty` to define how an object is constructed from JSON.
- `@JsonDeserialize` to specify a custom deserializer for a type needing special handling.
- Jackson modules to register serializers/deserializers for a group of types.
- Configuring the `ObjectMapper` used by Spring Data REST when global JSON rules need changing.

Choose the mechanism based on the data source: URL values need appropriate converters/binding; JSON values need appropriate Jackson mapping.

## 6. Distinguishing common errors

| Symptom | Step where it may occur | What to check |
|---|---|---|
| Malformed ID in URL | Converting path variable to ID type | Check the ID type and the ID format sent by the client |
| Item not found | Repository lookup after ID conversion | Check whether the ID exists and the endpoint is right |
| Invalid date/number query parameter | Binding and conversion of query parameter | Check `@Param` name, value format, and converter |
| Search endpoint does not exist | Exporting repository/search method | Check repository, `@RestResource`, and export configuration |
| Invalid JSON syntax or type mismatch | Jackson deserializing request body | Check JSON, property names, and Java types |
| Unsupported Content-Type | HTTP message converter | Send a Content-Type supported by the endpoint |
| Association not bound properly | Mapping association in body | Check association name and related resource URI |

Exact HTTP status codes also depend on the endpoint, exception handlers, and application configuration. When debugging, determine whether the failure happened while reading the URL, converting types, deserializing the body, or executing the repository operation.

## 7. Checklist when building a client

- Use the exact URI and ID type exported by the repository.
- Send query parameters matching the names declared with `@Param`.
- URL-encode query parameter values before appending them to the URL.
- Send page, size, and sort according to the API's conventions when pagination is needed.
- Set `Content-Type` matching the request body format.
- Send JSON with property names and value types compatible with the entity/Jackson.
- Use resource URIs provided by the server when writing associations.
- Choose `POST` to create, `PUT` to replace the representation, and `PATCH` for partial updates.
- Inspect the response status, `Location` header, and error payload to identify which processing step failed.

## 8. Conclusion

Path variables identify resources and typically need to be converted to the repository's ID type. Query parameters pass search criteria or pagination/sorting options and are bound to search method parameters. Request bodies carry entity data as JSON and are deserialized by Jackson. When custom data types are needed, configure Spring's `ConversionService` for URL data and Jackson for JSON data. Distinguishing these three mechanisms clearly makes Spring Data REST endpoints easier to use and troubleshoot.