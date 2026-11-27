# Controlling Property Names with @JsonProperty and Naming Strategies

## Objectives

In Java, property names typically use camelCase, whereas a JSON API may require snake_case, kebab-case, or another public name. Jackson lets you control JSON field names using the `@JsonProperty` annotation and property naming strategies.

For example, a Java model has the property `firstName` while the API needs JSON:

    {
      "first_name": "An"
    }

There are two main approaches:

- Use `@JsonProperty("first_name")` when a single property needs a specific JSON name.
- Use a naming strategy such as `SNAKE_CASE` when you want to consistently convert many properties.

In Spring Data REST, Jackson also participates in serializing and deserializing domain objects in HTTP representations. Therefore, JSON names can differ from Java names, while resource URLs, HAL relations, and database column names are separate concepts.

## 1. Distinguishing Java Names, JSON Names, and Database Names

A property can have different names at different layers:

| Layer | Example | Controlled by |
|---|---|---|
| Java property | firstName | Field name, getter/setter, or record component |
| JSON property | first_name | Jackson annotation or naming strategy |
| Database column | first_name | JPA mapping such as @Column |
| REST resource path | /people/1001 | Spring Data REST repository mapping |
| HAL relation | people | Spring Data REST relation configuration |

Renaming JSON with `@JsonProperty` does not automatically rename the Java field, database column, collection URL, or HAL relation.

Example:

    @Entity
    public class Person {

        @Id
        private Long id;

        @Column(name = "first_name")
        @JsonProperty("first_name")
        private String firstName;
    }

Here:

- Java uses `firstName`.
- JSON uses `first_name`.
- The database column is also `first_name` because of `@Column`.
- The two annotations have separate responsibilities; if you remove `@Column`, Jackson can still output the JSON key `first_name`, while the database column name does not necessarily change.

## 2. Renaming a Property with @JsonProperty

`@JsonProperty` belongs to Jackson annotations:

    import com.fasterxml.jackson.annotation.JsonProperty;

The annotation can be placed on a field, getter, setter, or constructor/creator parameter depending on how Jackson accesses the object.

### 2.1. Placing the Annotation on a Field

    public class Person {

        @JsonProperty("first_name")
        private String firstName;

        @JsonProperty("last_name")
        private String lastName;
    }

When serializing, Jackson uses the specified names:

    {
      "first_name": "An",
      "last_name": "Nguyen"
    }

When deserializing, Jackson can also read those keys to assign values to the corresponding properties, according to the class's access mode and configuration.

### 2.2. Placing the Annotation on a Getter

If the application uses getters as the JSON access point:

    public class Person {

        private String firstName;

        @JsonProperty("first_name")
        public String getFirstName() {
            return firstName;
        }

        public void setFirstName(String firstName) {
            this.firstName = firstName;
        }
    }

The public name of the property in JSON is `first_name`. Jackson can merge the getter and setter into the same logical property.

### 2.3. Placing the Annotation on a Setter

You can place the annotation on a setter to specify the JSON input name:

    public class Person {

        private String firstName;

        public String getFirstName() {
            return firstName;
        }

        @JsonProperty("first_name")
        public void setFirstName(String firstName) {
            this.firstName = firstName;
        }
    }

When the annotation is placed in multiple locations on the same logical property, use the same JSON name and avoid creating conflicting declarations. Jackson has rules for merging metadata from fields, getters, setters, and creators; the exact result also depends on visibility and ObjectMapper configuration.

### 2.4. Naming Constructor or Creator Parameters

For immutable objects, you can declare the JSON name on a creator parameter:

    public class Person {

        private final String firstName;

        @JsonCreator
        public Person(
                @JsonProperty("first_name") String firstName) {
            this.firstName = firstName;
        }

        public String getFirstName() {
            return firstName;
        }
    }

This tells Jackson which JSON key is used to construct the object. For Java records and other immutable types, how constructors/components are detected also depends on the Jackson version and module configuration in use.

## 3. Access Modes of @JsonProperty

`@JsonProperty` has an `access` attribute to control JSON read and write directions.

| Access mode | Serialize object to JSON | Deserialize JSON to object |
|---|---|---|
| AUTO | Per Jackson's default rules | Per Jackson's default rules |
| READ_ONLY | Can output the property | Does not accept input values for the property |
| WRITE_ONLY | Does not output the property | Can accept input values |
| READ_WRITE | Read and write in both directions | Read and write in both directions |

Example allowing a password to be received on create requests without returning it in responses:

    public class RegistrationRequest {

        private String username;

        @JsonProperty(
            value = "password",
            access = JsonProperty.Access.WRITE_ONLY
        )
        private String password;
    }

Example outputting only a server-managed value:

    public class PersonResponse {

        @JsonProperty(
            value = "internal_code",
            access = JsonProperty.Access.READ_ONLY
        )
        private String internalCode;
    }

Do not use WRITE_ONLY as a complete data protection mechanism. You still need to control authorization, logging, validation, and how sensitive data is stored.

## 4. Using a Naming Strategy for an Entire Model

If many properties need conversion from camelCase to snake_case, there is no need to annotate every field with `@JsonProperty`. Use Jackson's `PropertyNamingStrategies`:

    import com.fasterxml.jackson.databind.PropertyNamingStrategies;
    import com.fasterxml.jackson.databind.annotation.JsonNaming;

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public class Person {

        private String firstName;
        private String lastName;
        private Instant createdAt;
    }

Illustrative JSON:

    {
      "first_name": "An",
      "last_name": "Nguyen",
      "created_at": "2026-11-11T10:00:00Z"
    }

`@JsonNaming` applies the naming strategy to the annotated class. Other classes are not automatically renamed just because one class uses this annotation.

### 4.1. Commonly Used Naming Strategies

Jackson provides common strategies:

| Strategy | Java property | Illustrative JSON name |
|---|---|---|
| LOWER_CAMEL_CASE | firstName | firstName |
| SNAKE_CASE | firstName | first_name |
| KEBAB_CASE | firstName | first-name |
| UPPER_CAMEL_CASE | firstName | FirstName |
| LOWER_CASE | firstName | firstname |
| UPPER_SNAKE_CASE | firstName | FIRST_NAME |

Actual results with abbreviations, digits, or acronyms can depend on Jackson's algorithm. Test edge-case names such as `URLValue`, `userID`, or `address2Line` if they appear in your model.

### 4.2. Applying a Strategy Per Class

You can use different strategies for different DTOs:

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public class PersonResponse {
        private String firstName;
        private String createdAt;
    }

    @JsonNaming(PropertyNamingStrategies.LowerCamelCaseStrategy.class)
    public class LegacyResponse {
        private String firstName;
        private String createdAt;
    }

This is useful when an API must maintain multiple different JSON contracts. However, keep the naming convention consistent within any single representation so it is easy for clients to consume.

## 5. Configuring an Application-Wide Naming Strategy

If the entire API needs a shared rule, you can configure ObjectMapper or the Jackson configuration managed by Spring Boot.

### 5.1. Spring Boot Application Property

With Spring Boot using Jackson 2, you can set in application.properties:

    spring.jackson.property-naming-strategy=SNAKE_CASE

Or YAML:

    spring:
      jackson:
        property-naming-strategy: SNAKE_CASE

This setting applies to the ObjectMapper that Spring Boot auto-configures. It can affect many endpoints and DTOs across the application, so check APIs that rely on legacy JSON names before enabling it globally.

A fully qualified strategy class name can also be used if the configuration needs to directly reference an application-provided implementation.

### 5.2. Configuring ObjectMapper Directly

If the application manages ObjectMapper itself, you can set the strategy:

    ObjectMapper mapper = new ObjectMapper();
    mapper.setPropertyNamingStrategy(
        PropertyNamingStrategies.SNAKE_CASE
    );

Note that Spring Data REST uses the Jackson converter configured in Spring MVC. Creating a separate ObjectMapper without registering it on the HTTP message converter will not change Spring Data REST's JSON responses.

### 5.3. Customizing the Jackson Builder in Spring Boot

You can customize the builder that Spring Boot uses to create ObjectMapper:

    @Configuration
    public class JacksonConfiguration {

        @Bean
        Jackson2ObjectMapperBuilderCustomizer namingCustomizer() {
            return builder ->
                builder.propertyNamingStrategy(
                    PropertyNamingStrategies.SNAKE_CASE
                );
        }
    }

This approach fits when you want to add configuration to the Boot-managed ObjectMapper. Builder APIs and integration names can vary across Spring Boot/Jackson generations; use the types matching your project's dependency versions.

Do not declare a new ObjectMapper bean if you only need to change one setting without understanding the other auto-configurations being applied. A self-created bean can alter default modules, serializers, deserializers, or converters.

## 6. Precedence Between @JsonProperty and Naming Strategies

A naming strategy is the default rule for transforming property names. `@JsonProperty` provides an explicit JSON name for a specific property.

Example:

    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public class Person {

        private String firstName;

        @JsonProperty("displayName")
        private String publicName;
    }

Illustrative representation:

    {
      "first_name": "An",
      "displayName": "An Nguyen"
    }

The `firstName` property follows the general naming strategy. The `publicName` property uses the explicit name `displayName` declared via the annotation.

Guidelines for usage:

- Naming strategy when many properties follow a uniform convention.
- @JsonProperty when a public name needs to stay unchanged, differ from the convention, or form part of an API contract.
- @JsonAlias when you want to additionally accept a legacy input name during a compatibility window without changing the output name.

Example alias for legacy input:

    public class Person {

        @JsonProperty("first_name")
        @JsonAlias("firstName")
        private String firstName;
    }

When deserializing, the API can accept both `first_name` and the alias `firstName`; when serializing, the public property name remains `first_name`. Clearly define which aliases need to be supported and for how long to avoid maintaining unnecessary multiple contracts.

## 7. @JsonProperty and Spring Data REST

Spring Data REST uses Spring MVC message converters and Jackson to produce JSON representations for domain objects. Therefore, naming strategies and property annotations can change field names in resource bodies.

Example repository:

    @RepositoryRestResource(path = "people")
    public interface PersonRepository
            extends JpaRepository<Person, Long> {
    }

Domain type:

    @Entity
    @JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
    public class Person {

        @Id
        private Long id;

        private String firstName;
        private String lastName;
    }

Request to read an item:

    GET /people/1001
    Accept: application/hal+json

The entity portion embedded in the response can use `first_name` and `last_name`, while the URL remains `/people/1001`.

Distinguish the parts of HAL:

- `_links` contains hypermedia links.
- `_embedded` contains representations of related resources or collections.
- Entity fields reside in the representation serialized by Jackson.
- Relation names such as `people` are configured separately by Spring Data REST.

Framework-defined HAL keys have their own contract. Do not assume changing a naming strategy will rename `_links`, `_embedded`, relations, or URLs. Inspect actual HAL responses from the Spring Data REST version you are using.

### 7.1. Impact on Write Request Bodies

POST, PUT, and PATCH send JSON bodies for Jackson to deserialize into the corresponding object or representation. If the server switches to snake_case, clients must send keys matching the contract:

    {
      "first_name": "An",
      "last_name": "Nguyen"
    }

If a client still sends `firstName`, the property may not be bound under the current configuration unless the API has an alias or compatibility setting.

Before changing a naming strategy globally, check both responses and request bodies. A change visible only in responses can still break clients sending POST/PUT/PATCH with legacy names.

### 7.2. Projections and DTOs

Projections or DTOs can define a separate representation. Annotations on DTOs/projections and ObjectMapper's naming strategy can affect how fields are serialized.

If an API uses projections, excerpts, or custom controllers, inspect the exact representation returned by the endpoint. Do not assume every endpoint uses the same class or the same set of properties.

## 8. Precautions When Renaming JSON Properties

### 8.1. Do Not Change the Contract Without Checking Clients

JSON names are part of the API contract. Changing `firstName` to `first_name` can break existing clients reading responses or sending requests.

If a convention migration is needed:

1. List endpoints and clients using the old field.
2. Determine the required compatibility period.
3. Optionally use aliases to accept legacy input during the transition.
4. Update API documentation and schemas.
5. Test serialization and deserialization before releasing.

### 8.2. Avoid Duplicate Property Names

Two different Java properties should not map to the same JSON name. Example:

    @JsonProperty("name")
    private String firstName;

    @JsonProperty("name")
    private String lastName;

This configuration creates a logical property conflict and can cause Jackson to throw errors or behave unexpectedly. Ensure every JSON property has a single clear data source.

### 8.3. Fields, Getters, and Setters Must Be Consistent

If a field, getter, and setter declare different names, Jackson can merge them based on visibility and annotation introspection. Avoid placing conflicting annotations on the same logical property.

If different names are needed for input and output, consider a custom serializer/deserializer or separate DTOs rather than creating confusing metadata on the entity.

### 8.4. Do Not Use @JsonProperty for Access Control

Renaming or hiding a field in JSON is not authorization. If clients must not read or modify a property, use DTOs, appropriate access modes, validation, and application-layer security rules.

## 9. Testing Serialization and Deserialization

Test both directions because property names affect both responses and requests.

### 9.1. Unit Testing with ObjectMapper

Example:

    ObjectMapper mapper = new ObjectMapper();

    Person person = new Person();
    person.setFirstName("An");

    String json = mapper.writeValueAsString(person);

    assertThat(json).contains(""first_name":"An"");

    Person restored = mapper.readValue(
        "{"first_name":"An"}",
        Person.class
    );

    assertThat(restored.getFirstName()).isEqualTo("An");

If using Spring Boot customizers or modules, inject the actual ObjectMapper from the application context to test the real runtime configuration.

### 9.2. Spring Data REST Integration Tests

Use MockMvc or HTTP tests to verify the real representation:

    mockMvc.perform(get("/people/1001")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$._embedded").doesNotExist());

For item representations, inspect the entity's JSON keys directly according to the actual response shape. Example:

    mockMvc.perform(get("/people/1001")
            .accept(MediaTypes.HAL_JSON))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.first_name").value("An"));

JSONPath expressions depend on item representation and media type. Use the actual response to choose the right JSONPath; the example above illustrates a field at the root.

### 9.3. Test Case Suite to Cover

- Serializing properties with @JsonProperty.
- Deserializing the same JSON name.
- Naming strategy applied per class or across ObjectMapper.
- Explicit @JsonProperty when a naming strategy is active.
- @JsonAlias for legacy input names if used.
- READ_ONLY and WRITE_ONLY.
- Getter/setter or constructor/record binding.
- POST/PUT/PATCH via Spring Data REST.
- HAL links and embedded entity fields.
- Existing clients using the old JSON contract.

## 10. Checklist for Choosing a Naming Approach

1. Determine whether the JSON contract needs camelCase, snake_case, or another convention.
2. Use @JsonProperty for properties with special public names.
3. Use @JsonNaming when only one class needs a distinct convention.
4. Use Spring Boot Jackson configuration when the entire application needs the same naming strategy.
5. Use @JsonAlias to support legacy input during a transition period.
6. Use access modes or DTOs to control which fields can be read/written.
7. Distinguish JSON properties from Java properties, database columns, REST paths, and HAL relations.
8. Test both serialization and deserialization.
9. Test HAL responses and POST/PUT/PATCH requests.
10. Check existing clients before changing the API contract.

## References

- [Jackson Annotations — JsonProperty](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.html)
- [Jackson Annotations — JsonAlias](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonAlias.html)
- [Jackson Databind — PropertyNamingStrategies](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/PropertyNamingStrategies.html)
- [Jackson Databind — JsonNaming](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-databind/latest/com/fasterxml/jackson/databind/annotation/JsonNaming.html)
- [Spring Boot — Customize the Jackson ObjectMapper](https://docs.spring.io/spring-boot/reference/features/json.html)
- [Spring Data REST — Configuring the REST representation](https://docs.spring.io/spring-data/rest/reference/representations.html)
