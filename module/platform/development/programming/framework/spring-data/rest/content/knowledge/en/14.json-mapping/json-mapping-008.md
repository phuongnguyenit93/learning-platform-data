# Mapping Interfaces or Abstract Classes to Implementation Types

In a domain model, a property may be declared using an **interface** or **abstract class** to reduce coupling to a concrete implementation. When Spring Data REST receives JSON and asks Jackson to construct an object, Jackson needs to know which concrete class to instantiate. If it only knows the declared type is an interface or abstract class, Jackson cannot create an instance on its own.

Spring Data REST recommends solving this by registering a type mapping in a Jackson **Module**. When an interface has a single default implementation, **SimpleAbstractTypeResolver** lets you explicitly declare which abstract type maps to which concrete implementation type.

## Objectives

After this lesson, you will be able to:

- Understand why Jackson cannot directly instantiate interfaces or abstract classes.
- Register interface/abstract class mappings to implementations using **SimpleAbstractTypeResolver**.
- Configure the Jackson ObjectMapper that Spring Data REST actually uses.
- Choose among fixed mappings, **@JsonDeserialize** annotations, and polymorphic type mapping.
- Distinguish JSON mapping from JPA persistence mapping and how Spring Data REST represents associations.
- Test POST/PUT/PATCH requests after configuring.

## 1. The Problem When Properties Use an Interface

Suppose a domain model has a contract describing processing options:

~~~java
public interface TaskOption {
    String getName();
    String getValue();
}
~~~

Concrete implementation:

~~~java
@Entity
public class TaskOptionEntity implements TaskOption {

    @Id
    @GeneratedValue
    private Long id;

    private String name;
    private String value;

    protected TaskOptionEntity() {
    }

    public TaskOptionEntity(String name, String value) {
        this.name = name;
        this.value = value;
    }

    @Override
    public String getName() {
        return name;
    }

    @Override
    public String getValue() {
        return value;
    }
}
~~~

Parent entity declaring a collection using the interface:

~~~java
@Entity
public class WorkItem {

    @Id
    @GeneratedValue
    private Long id;

    private String title;

    @OneToMany(
        targetEntity = TaskOptionEntity.class,
        cascade = CascadeType.ALL,
        orphanRemoval = true
    )
    private List<TaskOption> options = new ArrayList<>();
}
~~~

Declaring the interface keeps domain code dependent on the TaskOption contract. The chosen implementation is TaskOptionEntity.

When Jackson reads JSON to create a new WorkItem, it encounters a property declared as List<TaskOption>. Jackson knows elements must conform to the TaskOption interface, but an interface is not an instantiable class. Without additional information, deserialization fails with an error indicating it cannot instantiate an abstract type.

Spring Data REST describes this exact scenario in its **Abstract Class Registration** section: an entity with an interface-typed collection property can be serialized, but when POSTing new data, Jackson does not know which implementation to instantiate. You must supply the type mapping via annotations or a Jackson Module.

> Because the example includes a JPA relationship, the concrete implementation must still satisfy JPA mapping rules. The targetEntity attribute in the example specifies the entity class for persistence relationships; it does not replace Jackson deserialization configuration.

## 2. Using SimpleAbstractTypeResolver

Jackson provides **SimpleAbstractTypeResolver** to map an abstract type to a concrete subtype.

For the example above, the mapping to register is:

~~~java
new SimpleAbstractTypeResolver()
    .addMapping(TaskOption.class, TaskOptionEntity.class);
~~~

Meaning:

- When Jackson needs to deserialize a value declared as TaskOption, the resolver selects TaskOptionEntity.
- TaskOptionEntity must implement TaskOption or extend the mapped abstract type.
- Jackson continues using normal binding rules to assign JSON properties onto the implementation.
- No discriminator field is needed in JSON when there is only one fixed implementation for that interface.

This resolver only handles selecting a concrete type for an abstract type. It does not define JSON field names, persist entities in the database, or replace constructors, setters, creators, or validation required by the implementation.

## 3. Registering the Jackson Module with Spring Data REST

Spring Data REST uses a specially configured ObjectMapper to handle domain objects and persistent entities. Therefore, register the type mapping on the ObjectMapper used by the exporter.

In Spring Data REST 5.1, you can override **configureJacksonObjectMapper** on **RepositoryRestConfigurer** and add a module:

~~~java
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.stereotype.Component;

import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.cfg.MapperBuilder;
import tools.jackson.databind.module.SimpleAbstractTypeResolver;
import tools.jackson.databind.module.SimpleModule;

@Component
public class RestJacksonConfiguration
        implements RepositoryRestConfigurer {

    @Override
    public void configureJacksonObjectMapper(
            MapperBuilder<? extends ObjectMapper,
                    ? extends MapperBuilder<?, ?>> mapperBuilder) {

        mapperBuilder.addModule(new SimpleModule("DomainAbstractTypes") {

            @Override
            public void setupModule(SetupContext context) {
                super.setupModule(context);

                context.addAbstractTypeResolver(
                    new SimpleAbstractTypeResolver()
                        .addMapping(
                            TaskOption.class,
                            TaskOptionEntity.class
                        )
                );
            }
        });
    }
}
~~~

Key parts:

1. **RepositoryRestConfigurer** is the extension point for customizing Spring Data REST configuration.
2. **configureJacksonObjectMapper** receives the MapperBuilder used by the exporter to construct ObjectMapper.
3. **mapperBuilder.addModule(…)** registers the custom module on that mapper.
4. **setupModule(…)** is invoked when the module is installed.
5. **context.addAbstractTypeResolver(…)** adds the resolver into Jackson.
6. **addMapping(TaskOption.class, TaskOptionEntity.class)** declares the implementation for the interface.

In Jackson 3, SetupContext belongs to the JacksonModule type hierarchy; the override example above uses the SetupContext name inherited inside SimpleModule. Calling super.setupModule(context) preserves SimpleModule's internal registration before adding the resolver.

### Note on Jackson Versions

Spring Data REST 5.1 uses the Jackson 3 API, so packages in the example start with **tools.jackson**. Older Spring Data REST versions typically use Jackson 2 with the **com.fasterxml.jackson** package and corresponding Module API.

With Jackson 2, registering the resolver follows the same idea:

~~~java
public class MyCustomModule extends SimpleModule {

    public MyCustomModule() {
        super("MyCustomModule");
    }

    @Override
    public void setupModule(SetupContext context) {
        super.setupModule(context);

        context.addAbstractTypeResolver(
            new SimpleAbstractTypeResolver()
                .addMapping(
                    TaskOption.class,
                    TaskOptionEntity.class
                )
        );
    }
}
~~~

In applications using Jackson 2, the module can be declared as a Spring bean in the ApplicationContext so the Spring Data REST exporter automatically detects and registers it. In current versions, the explicit and direct approach is configuring the module via configureJacksonObjectMapper as shown above.

Do not mix Jackson 2 and Jackson 3 packages in the same module. Use the exact namespaces, APIs, and versions managed by Spring Boot/Spring Data REST in your application's dependency tree.

## 4. Example Request Through Spring Data REST

Suppose a repository exposes WorkItem:

~~~java
@RepositoryRestResource(path = "work-items")
public interface WorkItemRepository
        extends JpaRepository<WorkItem, Long> {
}
~~~

When a client creates a new WorkItem, an illustrative request can be:

~~~http
POST /work-items
Content-Type: application/json
Accept: application/hal+json

{
  "title": "Import customer data",
  "options": [
    {
      "name": "format",
      "value": "csv"
    },
    {
      "name": "delimiter",
      "value": ","
    }
  ]
}
~~~

During deserialization, Jackson sees a collection with element type TaskOption. The registered resolver selects TaskOptionEntity to construct each element. The name and value properties are bound onto the corresponding instances.

If the request succeeds, the response depends on representation, association mapping, repository configuration, and whether Spring Data REST exposes the related entity. Do not assume every JPA association is returned as a nested object; Spring Data REST typically represents managed entities via links and association resources per the exporter's contract.

You can inspect the new item resource with GET and follow the HAL links returned by the server. If the application uses association endpoints to attach existing entities, use entity URIs per the association contract rather than sending embedded JSON objects expecting the resolver to handle all persistence relationships on its own.

## 5. Fixed Mapping with @JsonDeserialize

Beyond Jackson Modules, you can declare the implementation directly using the **@JsonDeserialize** annotation.

For a single interface-typed property:

~~~java
public class WorkItemRequest {

    @JsonDeserialize(as = TaskOptionImpl.class)
    private TaskOption option;
}
~~~

For collections or arrays, use **contentAs** to specify the element type:

~~~java
public class WorkItemRequest {

    @JsonDeserialize(contentAs = TaskOptionImpl.class)
    private List<TaskOption> options;
}
~~~

For maps, you can use **contentAs** to specify the value type and **keyAs** to specify the key type when needed.

Comparing the approaches:

| Approach | Scope | When Appropriate |
| --- | --- | --- |
| @JsonDeserialize(as = ...) | A single annotated property or type | The implementation only needs to apply at one specific site |
| @JsonDeserialize(contentAs = ...) | Elements of a collection/array or values of a map | The container's declared element/value type is abstract/interface |
| SimpleAbstractTypeResolver | Centralized abstract type mapping in a Jackson Module | Multiple properties share the same implementation |
| Custom JsonDeserializer | Full control over object creation and JSON reading | Complex object construction logic, validation, or custom mapping is needed |

Property annotations have local scope and are easy to read at the declaration site. A module fits better when you want centralized configuration on Spring Data REST's ObjectMapper, especially when the same interface is used across multiple entities or properties.

@JsonDeserialize(as = ...) requires the implementation to be a compatible subtype of the declared type. If using is also specified, the directly specified custom deserializer takes precedence over the as attribute.

## 6. When Multiple Implementations Exist

Mapping with SimpleAbstractTypeResolver works when an abstract type has a single fixed default implementation.

If an interface has multiple implementations and JSON must select the type per request, a fixed mapping is not enough. Example:

~~~java
public interface PaymentMethod {
    String getReference();
}

public class CardPayment implements PaymentMethod {
    private String reference;
    private String lastFourDigits;
}

public class BankTransfer implements PaymentMethod {
    private String reference;
    private String bankCode;
}
~~~

Clients can send different kinds of PaymentMethod. In this case, polymorphic type handling is required, typically using **@JsonTypeInfo** together with **@JsonSubTypes**:

~~~java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(
        value = CardPayment.class,
        name = "card"
    ),
    @JsonSubTypes.Type(
        value = BankTransfer.class,
        name = "bank-transfer"
    )
})
public interface PaymentMethod {
}
~~~

JSON includes a discriminator to indicate the type:

~~~json
{
  "kind": "card",
  "reference": "PAY-1001",
  "lastFourDigits": "4242"
}
~~~

Or:

~~~json
{
  "kind": "bank-transfer",
  "reference": "PAY-1002",
  "bankCode": "ABC"
}
~~~

Jackson reads the kind field and selects the registered subtype. Logical type names like card and bank-transfer are more stable than putting fully qualified Java class names in payloads.

Do not use polymorphic type metadata without strict controls. Allow only known, application-approved subtypes. Avoid configurations where clients can arbitrarily specify class names to be loaded or instantiated; selecting implementations from untrusted data must enforce an explicit allowlist.

## 7. Distinguishing Three Mapping Mechanisms

These mechanisms are related but solve different problems:

| Mechanism | Question Solved |
| --- | --- |
| SimpleAbstractTypeResolver | For this interface/abstract type, which default implementation should Jackson instantiate? |
| @JsonDeserialize | Which concrete type or custom deserializer should this property or type use? |
| @JsonTypeInfo + @JsonSubTypes | When multiple subtypes exist, how does JSON indicate which subtype each object belongs to? |
| JPA targetEntity | Which entity class does the persistence provider use for a relationship declared with an abstract type? |
| Spring Data repository metadata | Which entities and repositories are managed/exposed as REST resources? |

Jackson configuration does not automatically change JPA mappings. Conversely, declaring targetEntity in JPA does not automatically tell Jackson how to deserialize JSON.

If the same property participates in both JSON binding and persistence mapping, both layers must agree on valid subtypes. If the implementation is a managed entity, verify constructors, IDs, owning side, cascades, orphan removal, and entity lifecycle per actual persistence mappings.

## 8. When Do You Need a Custom Serializer or Deserializer?

Abstract type mapping only solves choosing which class to instantiate. It is insufficient if JSON has a different structure from Java properties or requires special logic.

Consider a custom deserializer when:

- JSON uses a structure completely different from the object model.
- A single JSON value must be converted into multiple fields or child objects.
- A reference needs to be looked up via a repository/service.
- A discriminator or state must be validated before creating the implementation.
- Instantiation depends on request context or other data.
- Multiple legacy payload shapes must be supported during an API transition.

Spring Data REST lets you register serializers and deserializers in a Jackson Module via SetupContext. The module can add SimpleSerializers and SimpleDeserializers or custom implementations.

Example registration structure:

~~~java
@Override
public void setupModule(SetupContext context) {
    super.setupModule(context);

    SimpleSerializers serializers = new SimpleSerializers();
    SimpleDeserializers deserializers = new SimpleDeserializers();

    serializers.addSerializer(
        TaskOptionEntity.class,
        new TaskOptionSerializer()
    );

    deserializers.addDeserializer(
        TaskOption.class,
        new TaskOptionDeserializer()
    );

    context.addSerializers(serializers);
    context.addDeserializers(deserializers);
}
~~~

Exact class names and serializer/deserializer signatures must follow the Jackson version in use. With Jackson 3, serializer/deserializer APIs have changed from Jackson 2; do not copy imports or class signatures verbatim from Jackson 2 examples into a Jackson 3 project.

If a custom deserializer needs to call a repository or service, avoid creating circular dependencies between the Jackson Module and Spring Data REST. Consider moving lookup logic into an application service or accepting a request DTO and processing it in the service layer after deserialization.

## 9. Common Errors

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Cannot construct instance of interface or abstract class | Jackson lacks an implementation mapping | Register SimpleAbstractTypeResolver, @JsonDeserialize, or polymorphic type metadata |
| Mapping is declared but has no effect in Spring Data REST | Module was registered on a different ObjectMapper than the one the exporter uses | Configure via RepositoryRestConfigurer.configureJacksonObjectMapper or the version-appropriate module bean mechanism |
| Abstract type is mapped but fails with invalid subtype error | Implementation does not implement/extend the declared type | Check subtype relationships and generic types |
| Collection still fails to deserialize | Property-level mapping does not apply to collection elements or generic type is wrong | Use contentAs or a resolver for the exact abstract element type |
| JSON fields are not populated | Implementation lacks appropriate setters, constructor/creator, or property visibility | Check JavaBean accessors, constructors, and Jackson settings |
| POST creates the object, but persistence fails | Jackson mapping succeeds, but entity mapping, owning side, or constraints are invalid | Check JPA targetEntity, ID, cascade, transaction, and validation |
| Multiple implementations exist, yet the same class is always created | A fixed mapping was registered for the abstract type | Use @JsonTypeInfo/@JsonSubTypes or a custom deserializer to select subtypes |
| JSON contains unexpected class names | Polymorphic type selection is configured too broadly | Use logical type names and a subtype allowlist |
| API returns representations unlike nested JSON objects | Spring Data REST is representing managed entities via association links | Follow HAL links and use association resources per the REST contract |

## 10. Implementation and Verification Workflow

1. Identify which properties in the domain model are declared using interfaces or abstract classes.
2. Identify the concrete implementations permitted by the persistence layer.
3. Decide between a single fixed implementation or multiple discriminated subtypes.
4. For a fixed implementation, register the mapping with SimpleAbstractTypeResolver or the @JsonDeserialize annotation.
5. Add the module to the ObjectMapper used by the Spring Data REST exporter.
6. Verify packages/APIs against the Jackson and Spring Data REST versions in your dependency tree.
7. Send POST with JSON containing the interface property and confirm Jackson instantiates the right implementation.
8. Send PUT/PATCH if the application supports updating that representation and confirm binding works.
9. Re-read the item resource, association links, and persisted data to verify saved state.
10. Test invalid payloads, disallowed subtypes, and uninstantiable implementations.
11. If multiple subtypes exist, test missing, invalid, or non-allowlisted discriminators.

A focused test for the resolver can test the corresponding ObjectMapper directly:

~~~java
assertThat(objectMapper.readValue(
        """
        {"name":"format","value":"csv"}
        """,
        TaskOption.class
    ))
    .isInstanceOf(TaskOptionEntity.class);
~~~

This is an illustrative test for Jackson mapping. In addition to mapper tests, write integration tests through Spring Data REST endpoints because the exporter uses an ObjectMapper configured with specialized serializers for PersistentEntity and associations.

## 11. Quick Checklist

- [ ] Identified the interface or abstract type Jackson needs to deserialize.
- [ ] Implementation is a valid subtype and instantiable.
- [ ] Decided between fixed mapping and polymorphic mapping.
- [ ] SimpleAbstractTypeResolver is registered on the right Spring Data REST ObjectMapper.
- [ ] Or @JsonDeserialize is placed properly on the type/property/container content.
- [ ] Did not mix Jackson 2 and Jackson 3 packages/APIs.
- [ ] JPA targetEntity and Jackson implementation mapping are aligned.
- [ ] Associations are verified against HAL links and actual REST contracts.
- [ ] Subtypes are allowlisted if JSON carries a discriminator.
- [ ] Tested POST/PUT/PATCH and persistence with integration tests.

## 12. Key Takeaways

When Jackson encounters an interface- or abstract-class-typed property, it needs to know the concrete implementation to instantiate the object. In Spring Data REST, the centralized configuration approach is registering a Jackson Module on the exporter's ObjectMapper:

~~~java
context.addAbstractTypeResolver(
    new SimpleAbstractTypeResolver()
        .addMapping(TaskOption.class, TaskOptionEntity.class)
);
~~~

Use **SimpleAbstractTypeResolver** when an abstract type has one default implementation. Use **@JsonDeserialize** when only one property needs a specific concrete type. If JSON can represent multiple implementations, use **@JsonTypeInfo** and **@JsonSubTypes** or a custom deserializer with an allowlist of permitted subtypes.

Jackson mapping only solves converting JSON into objects. Persistence mapping, association exposure, validation, and access control still must be configured at their respective layers.

## References

- Spring Data REST Reference — Domain Object Representations, Abstract Class Registration: https://docs.spring.io/spring-data/rest/reference/representations.html
- Spring Data REST Reference — Adding Custom Serializers and Deserializers to Jackson's ObjectMapper: https://docs.spring.io/spring-data/rest/reference/customizing/custom-jackson-deserialization.html
- Spring Data REST API — RepositoryRestConfigurer.configureJacksonObjectMapper: https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html
- Jackson Databind — SimpleAbstractTypeResolver: https://javadoc.io/doc/tools.jackson.core/jackson-databind/latest/tools.jackson.databind/module/SimpleAbstractTypeResolver.html
- Jackson Databind — JsonDeserialize: https://javadoc.io/doc/tools.jackson.core/jackson-databind/latest/tools.jackson.databind/annotation/JsonDeserialize.html
- Jackson Annotations — JsonTypeInfo and JsonSubTypes: https://github.com/FasterXML/jackson-annotations
