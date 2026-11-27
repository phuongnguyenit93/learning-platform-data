# Spring Data REST ObjectMapper and the Entity–Link Mapping Mechanism

## 1. Objective

Spring Data REST uses Jackson to read and write JSON, while adding a hypermedia mechanism to represent entities and associations as REST resources. These two parts are closely related but have distinct responsibilities:

- **Jackson ObjectMapper** converts between JSON and Java objects: reading properties, converting data types, formatting dates and times, and applying serializers/deserializers and Jackson annotations.
- **Spring Data REST** uses repository and persistent entity metadata to generate resources, collections, associations, and HAL links. Associations in a response can be represented by rel and href instead of nesting the entire Java object.

Therefore, the JSON representation of an entity is determined by both Jackson mapping and Spring Data REST resource/hypermedia rules. When customizing, you need to decide whether you want to change how a value is serialized or how the API exposes a relationship.

## 2. What Does ObjectMapper Do?

Jackson ObjectMapper is the central component for serializing objects into JSON and deserializing JSON into objects. In a Spring application, ObjectMapper is typically configured with modules supporting data types, naming strategies, and formatting rules.

Example entity:

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String fullName;

        private LocalDate registeredOn;

        private BigDecimal creditLimit;

        // getters and setters
    }

When a Customer is returned as JSON, Jackson converts the Java values into the corresponding JSON. An illustrative representation:

    {
      "fullName": "An Nguyen",
      "registeredOn": "2026-11-11",
      "creditLimit": 2500000
    }

This is only the JSON data portion of the entity. Spring Data REST can wrap that data in a resource representation and add HAL links such as _links.self, a link to profile, or links to associations.

ObjectMapper also handles the JSON request body when a client sends POST, PUT, or PATCH. The fact that JSON can be converted into a Java object does not itself determine whether a repository method is exported, whether an association is exposed, or whether the caller has access permissions.

## 3. HAL and the Entity-to-Link Mapping Mechanism

Suppose Customer has an association to Address:

    @Entity
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        private String fullName;

        @ManyToOne
        private Address address;
    }

    @Entity
    public class Address {

        @Id
        @GeneratedValue
        private Long id;

        private String street;
        private String city;
    }

When Spring Data REST exports the association, the Customer response can look like:

    {
      "fullName": "An Nguyen",
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers/42"
        },
        "address": {
          "href": "http://localhost:8080/customers/42/address"
        }
      }
    }

Instead of serializing the entire Address nested inside Customer, the API exposes a link with the relation address. The client follows that link's href to read the association resource.

With HAL, two important structures are:

- _links: hypermedia relations and their corresponding URIs.
- _embedded: resources embedded in the representation, commonly used in collection responses.

Collection example:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers"
        }
      },
      "_embedded": {
        "customers": [
          {
            "fullName": "An Nguyen",
            "_links": {
              "self": {
                "href": "http://localhost:8080/customers/42"
              },
              "address": {
                "href": "http://localhost:8080/customers/42/address"
              }
            }
          }
        ]
      }
    }

Actual relation names and paths depend on repository and association configuration. Clients should read the rel/href returned by the server rather than inferring URLs from class names or IDs.

## 4. Spring Data REST Adds Mapping for Persistent Entities

Spring Data REST registers Jackson components and resource assembly infrastructure to understand persistent entity metadata. In current versions, the specialized Jackson module is commonly known as `PersistentEntityJackson2Module`.

This module and resource infrastructure work with metadata such as:

- Entity types and persistent properties.
- Associations between persistent entities.
- Which repositories are exported.
- Collection resource rel and item resource rel.
- Association paths and rels exposed in HAL.

As a result, Spring Data REST can produce representations with links for associations and resolve resources based on repository metadata.

You should not replace Spring Data REST's default ObjectMapper with a newly constructed standalone ObjectMapper. Doing so can strip away modules, mixins, serializers, or configurations that the framework registered to produce HAL and handle persistent entities.

If you need to customize JSON, use Spring Data REST's extension point to add configuration onto the ObjectMapper that the framework is using.

## 5. Customizing ObjectMapper with RepositoryRestConfigurer

You can implement RepositoryRestConfigurer and override the configureJacksonObjectMapper callback:

    import com.fasterxml.jackson.annotation.JsonInclude;
    import com.fasterxml.jackson.databind.ObjectMapper;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

    @Configuration
    public class RepositoryRestConfig
            implements RepositoryRestConfigurer {

        @Override
        public void configureJacksonObjectMapper(
                ObjectMapper objectMapper) {

            objectMapper.setSerializationInclusion(
                JsonInclude.Include.NON_NULL
            );
        }
    }

The example above instructs Jackson to omit properties with null values during serialization. Inspect the actual output because changing the inclusion policy can affect the JSON contract of many resources.

You can additionally configure a naming strategy, date format, or serializer for specific data types. Only change rules that the API genuinely needs; a global change can affect every repository resource served by this ObjectMapper.

Callback signatures and configuration APIs should be checked against the Spring Data REST version the project uses. Do not copy configuration from another version if the current dependency does not provide the same extension point.

## 6. Using Jackson Annotations for Properties

Jackson annotations can control how a property appears in JSON.

Example of renaming a property:

    public class Customer {

        @JsonProperty("displayName")
        private String fullName;
    }

JSON can use the key displayName instead of the Java name fullName.

You can format dates:

    public class Customer {

        @JsonFormat(
            shape = JsonFormat.Shape.STRING,
            pattern = "yyyy-MM-dd"
        )
        private LocalDate registeredOn;
    }

You can mark a property not to be serialized/deserialized in the usual Jackson way:

    @JsonIgnore
    private String internalNote;

These annotations affect JSON mapping. They do not replace repository or association export configuration. In particular, when an annotation is placed on an association property, inspect the actual HAL output to confirm that the desired links are still exposed according to the application's configuration.

Do not use @JsonIgnore as an authorization mechanism. Hiding a property from JSON does not protect endpoints or data in other APIs.

## 7. Adding a Serializer for Custom Data Types

When you need to format a value object, you can register a serializer via a Jackson module. Example Money type:

    public class Money {

        private final BigDecimal amount;
        private final String currency;

        public Money(BigDecimal amount, String currency) {
            this.amount = amount;
            this.currency = currency;
        }

        public BigDecimal getAmount() {
            return amount;
        }

        public String getCurrency() {
            return currency;
        }
    }

Serializer:

    public class MoneySerializer
            extends JsonSerializer<Money> {

        @Override
        public void serialize(
                Money value,
                JsonGenerator generator,
                SerializerProvider serializers)
                throws IOException {

            generator.writeStartObject();
            generator.writeNumberField(
                "amount",
                value.getAmount()
            );
            generator.writeStringField(
                "currency",
                value.getCurrency()
            );
            generator.writeEndObject();
        }
    }

Registering the module in the callback:

    @Override
    public void configureJacksonObjectMapper(
            ObjectMapper objectMapper) {

        SimpleModule module = new SimpleModule();
        module.addSerializer(
            Money.class,
            new MoneySerializer()
        );

        objectMapper.registerModule(module);
    }

The corresponding Jackson imports are required for JsonSerializer, JsonGenerator, SerializerProvider, SimpleModule, and IOException.

This example only changes how the Money type is converted to JSON. It does not change how Spring Data REST generates links for Customer or Address.

When adding serializers/deserializers, you should limit them to value types or a specific type. Registering a custom serializer for an entire aggregate root such as Customer can bypass persistent entity processing and prevent HAL links from being generated as expected.

## 8. Distinguishing JSON Mapping from Association Mapping

The following two things are often confused:

**Mapping a JSON property**

For example, fullName is renamed to displayName, or LocalDate is serialized with the pattern yyyy-MM-dd. This is the responsibility of Jackson annotations, serializers, or deserializers.

**Mapping an association to a link**

For example, the Customer.address property is exported as the HAL relation address with an href. This is the responsibility of Spring Data REST based on persistent association metadata and resource configuration.

You can customize the association rel/path with @RestResource:

    @ManyToOne
    @RestResource(
        path = "billing-address",
        rel = "billingAddress"
    )
    private Address address;

In the example, the Java property remains address, while the HAL relation is billingAddress and the association path is billing-address.

Do not use Jackson @JsonProperty as a substitute for @RestResource(rel = ...) when the goal is to rename an association link. The two annotations control two different parts of the representation.

## 9. Sending JSON Data and Updating Associations

When creating or updating an entity, the JSON body typically carries the entity's data properties:

    POST /customers
    Content-Type: application/json
    Accept: application/hal+json

    {
      "fullName": "An Nguyen",
      "registeredOn": "2026-11-11"
    }

Jackson reads the JSON and converts fields into Java values according to the configured mapping. Spring Data REST then continues processing the request through the repository and persistence rules.

Exported associations usually have their own endpoints. A common way to attach an existing resource to an association is to send the URI of the related resource to the association link using the text/uri-list media type.

Illustrative example of attaching Address to Customer:

    PUT /customers/42/address
    Content-Type: text/uri-list

    http://localhost:8080/addresses/7

For collection associations, adding a link typically uses POST to the association resource:

    POST /customers/42/orders
    Content-Type: text/uri-list

    http://localhost:8080/orders/1001

The URLs above are illustrative based on the chosen paths; in a real application, use the association href and item link exposed by the server. The exact operation also depends on the association type and Spring Data REST configuration.

Do not assume that sending an entire nested Address JSON object inside Customer is always the standard way to link two existing resources. When working with association resources, follow hypermedia links and use the request format supported by the association endpoint.

## 10. Configuring Repository and Association Resources

@RepositoryRestResource customizes how a repository is exposed:

    @RepositoryRestResource(
        collectionResourceRel = "customers",
        path = "customers"
    )
    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {
    }

@RestResource customizes an association or query method:

    @ManyToOne
    @RestResource(
        rel = "billingAddress",
        path = "billing-address"
    )
    private Address address;

These configurations affect the relation/path in resources. They are different from Jackson naming strategies, @JsonProperty, or serializers.

If a repository or association is not exported, the corresponding link may not appear. Check exported, the repository detection strategy, and REST configuration before concluding that ObjectMapper is serializing incorrectly.

## 11. Reading and Inspecting JSON/HAL Responses

You can inspect the API root or a resource using curl:

    curl -i \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers/42

Check:

1. Status code and Content-Type.
2. Whether JSON properties have the expected names and formats.
3. Whether _links.self points to the current resource.
4. Whether association rels appear in _links.
5. Whether the association href can be called and returns the expected resource type.
6. If it is a collection, whether _embedded and pagination metadata are correct.

Example when inspecting an association:

    curl -i \
      -H "Accept: application/hal+json" \
      http://localhost:8080/customers/42/address

This is an illustrative URL. You should obtain the href from the HAL response to inspect, rather than manually constructing paths.

When JSON fields are correct but links are missing, check association export and persistent metadata. When links are correct but a JSON value is formatted incorrectly, check ObjectMapper, Jackson modules, and annotations on that data type.

## 12. Common Mistakes

**Creating a new ObjectMapper and replacing Spring Data REST's mapper**

The new mapper may lack modules or settings that the framework needs to serialize persistent entities and HAL. Use the configureJacksonObjectMapper callback to add configuration onto the existing mapper.

**Using @JsonProperty to change an association rel**

@JsonProperty renames a JSON property; @RestResource(rel = ...) controls the relation name of an association. Choose the annotation based on which part of the representation you want to change.

**Custom serializer causing HAL links to disappear**

A serializer for an aggregate root can override Spring Data REST's resource processing path. Limit serializers to value types or specific types and inspect _links after configuring.

**Confusing a nested JSON object with an association resource**

Nesting an entity in JSON does not automatically mean Spring Data REST will create an association link or bind to an existing resource. For exported associations, use the appropriate links and request format of the association endpoint.

**Using annotations to protect data**

JsonIgnore or omitting a field from serialization does not replace authentication and authorization. Protect endpoints and repository operations with security configuration.

**Making global changes without checking the contract**

A global null inclusion policy, naming strategy, or date format can change the JSON of many resources. Inspect affected responses after configuring.

## 13. Hands-On Exercises

With Customer having fullName, registeredOn, and an Address association:

1. Call GET on the Customer resource with Accept: application/hal+json.
2. Identify the JSON properties and association links in _links.
3. Add @JsonProperty to a property and observe the JSON key change.
4. Add @JsonFormat to LocalDate and observe the date format.
5. Use RepositoryRestConfigurer.configureJacksonObjectMapper to apply a serialization policy.
6. Customize the association using @RestResource(rel = ..., path = ...).
7. Compare the effect of Jackson annotations against association metadata.
8. Call the association href and confirm the response is the related resource.
9. If registering a custom serializer for a value object, confirm that Customer's HAL links are still present.

Self-check questions:

- Which conversion steps is ObjectMapper responsible for?
- Why does Spring Data REST need persistent entity metadata to create association links?
- How do @JsonProperty and @RestResource(rel = ...) differ?
- Why should you add modules to the existing ObjectMapper instead of replacing the default mapper?
- When should you use a custom serializer for a value object?
- Why are exported associations typically manipulated through association resources?

## 14. Key Takeaways

- Jackson ObjectMapper reads and writes JSON, handling data types, formatting, and custom serializers/deserializers.
- Spring Data REST uses persistent entity metadata and hypermedia infrastructure to build resources and association links.
- HAL typically represents links in _links and embedded resources in _embedded.
- RepositoryRestConfigurer.configureJacksonObjectMapper is the extension point for customizing Spring Data REST's ObjectMapper.
- @JsonProperty and @JsonFormat affect JSON properties; @RestResource affects association/query resource rels and paths.
- Avoid replacing the default mapper or overriding aggregate root serializers without understanding the impact on HAL.
- Use association hrefs and the appropriate request format to link resources.
- JSON mapping does not replace repository export configuration or authorization.

## References

- Spring Data REST Reference — Configuring Jackson ObjectMapper: https://docs.spring.io/spring-data/rest/reference/
- Spring Data REST Reference — Association resources: https://docs.spring.io/spring-data/rest/reference/
- Spring Data REST API — RepositoryRestConfigurer: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html
- Jackson Databind documentation: https://github.com/FasterXML/jackson-databind
