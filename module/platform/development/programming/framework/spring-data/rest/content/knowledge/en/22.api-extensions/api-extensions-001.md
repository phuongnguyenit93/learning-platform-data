# Choosing an Extension Point: Configurer, Processor, Listener, or Controller

## Objectives

Spring Data REST automatically publishes Spring Data repositories as REST APIs. When an API needs to change the default behavior, you can extend it at several different layers: global configuration, returned representations, repository operation lifecycle, or HTTP endpoints.

Choosing the right extension point keeps customization in the component responsible for it. For example, adding a link to JSON does not require rewriting a controller; validating data before the REST exporter saves an entity does not require creating a new endpoint; and a multi-step business workflow may require a dedicated controller.

This lesson focuses on four primary options:

1. `RepositoryRestConfigurer`: configures how Spring Data REST behaves.
2. `RepresentationModelProcessor`: adds links or hypermedia content to a representation.
3. Repository REST events/listeners: handles events in the create, save, delete, and link-change lifecycle.
4. `@RepositoryRestController`: builds or replaces a handler for an endpoint within the Spring Data REST URI space.

## 1. Start by Identifying the Type of Change

Before writing code, identify what needs to change:

| Requirement | Extension Point to Consider |
|---|---|
| Change base path, repository exposure rules, page limits, CORS, or type conversion | `RepositoryRestConfigurer` and `RepositoryRestConfiguration` |
| Add links, navigation links, or hypermedia information to an existing response | `RepresentationModelProcessor` |
| Validate, normalize, audit, or react to create/save/delete operations via REST | Repository REST event handler or listener |
| Add an endpoint, handle a custom request, aggregate data, or replace a response handler | `@RepositoryRestController` |
| Change how data is queried or accessed | Repository query method or custom repository fragment |

The `@RepositoryRestResource` and `@RestResource` annotations are also useful declarative configuration tools. They are well suited for changing a path, relation name, projection, or disabling exposure of a repository/method. When dynamic logic or a custom HTTP flow is needed, choose the corresponding extension point above.

## 2. Global Configuration with RepositoryRestConfigurer

Use `RepositoryRestConfigurer` when you want to change the general configuration of the REST exporter. This interface provides callbacks to customize `RepositoryRestConfiguration` and other integration components.

With Spring Boot, Spring Data REST auto-configuration is enabled when the application has the appropriate starter. You only need to register a `RepositoryRestConfigurer` bean; you do not need to manually import the Spring Data REST MVC configuration in a standard Spring Boot application.

Example of changing the base path, page size limits, and CORS configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;
import org.springframework.data.rest.core.config.RepositoryRestConfiguration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;

@Configuration
public class RestApiConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.setBasePath("/api");
        config.setDefaultPageSize(25);
        config.setMaxPageSize(100);

        cors.addMapping("/**")
                .allowedOrigins("https://client.example")
                .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE");
    }
}
~~~

After this configuration, repository resources are served under the `/api` base path. Clients can request up to 100 items per page; the default page has 25 items. The allowed origin and HTTP methods in the example are illustrative values only and must be replaced with your application's policy.

Other configuration areas supported by `RepositoryRestConfigurer` include:

- **Repository exposure:** set `RepositoryDetectionStrategy`, control exported HTTP methods, and configure exposure rules per domain type.
- **Conversion:** register converters to convert request parameter values or data types.
- **HTTP message conversion:** add or customize `HttpMessageConverter`.
- **Jackson:** configure mappers/modules, serializers, and deserializers for representations.
- **Validation:** register validators with `ValidatingRepositoryEventListener`.
- **Exception handling:** customize the `ExceptionHandlerExceptionResolver` used by the REST exporter.

For example, if you need to add a validator that runs before creating or saving an entity, you can configure the listener in the same configurer:

~~~java
@Override
public void configureValidatingRepositoryEventListener(
        ValidatingRepositoryEventListener listener) {

    listener.addValidator("beforeCreate", personValidator);
    listener.addValidator("beforeSave", personValidator);
}
~~~

The event names `beforeCreate` and `beforeSave` bind the validator to the two corresponding lifecycle points of the REST exporter.

For basic options already available in Spring Boot properties, prefer configuring them with `spring.data.rest.*`. Use `RepositoryRestConfigurer` when you need callbacks, conditional configuration, or Java bean integration. Avoid registering multiple configurers that modify the same property without controlling their ordering and final outcome.

## 3. Enriching Hypermedia with RepresentationModelProcessor

Use `RepresentationModelProcessor` when the default response already has the right data, but needs additional links so clients can continue navigating or perform a related action.

Spring Data REST integrates with Spring HATEOAS. `RepresentationModelProcessor<EntityModel<T>>` beans are detected by the exporter when building representations for entities of type `T`.

Example of adding a link to a documentation page for a Person:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.Link;
import org.springframework.hateoas.server.RepresentationModelProcessor;

@Configuration
public class PersonRepresentationConfiguration {

    @Bean
    RepresentationModelProcessor<EntityModel<Person>> personProcessor() {
        return model -> {
            model.add(Link.of("/docs/people").withRel("documentation"));
            return model;
        };
    }
}
~~~

When Spring Data REST serializes a `Person` entity, the processor is invoked with `EntityModel<Person>`. A link with relation `documentation` is added to the HAL representation under `_links`.

Example of the links section in the response:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42"
    },
    "documentation": {
      "href": "/docs/people"
    }
  },
  "firstName": "An",
  "lastName": "Nguyen"
}
~~~

In a real application, you should build links using Spring HATEOAS `linkTo(...)`, `methodOn(...)`, or the corresponding link APIs instead of hardcoding the host, port, or base path. Mapping-based link construction ensures the application works properly when running behind a reverse proxy or when the base path changes.

A processor is well suited for tasks such as:

- Adding links to related resources or documentation.
- Adding action links when an entity satisfies a condition.
- Adding presentation metadata that clients need to continue navigating.
- Standardizing links for a type of representation.

The processor runs during representation assembly. Do not use it to save entities, perform side effects, check access permissions, or replace business rules. If you need to modify persisted data, use a service, repository, or an appropriate lifecycle hook.

If you need to change the entire JSON structure rather than just adding hypermedia, consider a custom Jackson serializer/deserializer or converter. This is a deeper change: a custom converter must preserve how Spring Data REST handles links to repository resources.

## 4. Handling Lifecycle with Repository REST Events and Listeners

Spring Data REST emits events when the REST exporter interacts with entities. There are two common ways to listen to them.

### 4.1. Annotated Event Handler

Use `@RepositoryEventHandler` to declare a handler by domain type. Annotations on methods specify when the handler is invoked.

Example of validating data before create/save and recording after save:

~~~java
import org.springframework.data.rest.core.annotation.HandleAfterSave;
import org.springframework.data.rest.core.annotation.HandleBeforeCreate;
import org.springframework.data.rest.core.annotation.HandleBeforeSave;
import org.springframework.data.rest.core.annotation.RepositoryEventHandler;
import org.springframework.stereotype.Component;

@Component
@RepositoryEventHandler(Person.class)
public class PersonEventHandler {

    @HandleBeforeCreate
    public void beforeCreate(Person person) {
        validatePerson(person);
    }

    @HandleBeforeSave
    public void beforeSave(Person person) {
        validatePerson(person);
    }

    @HandleAfterSave
    public void afterSave(Person person) {
        // Record the save operation or update auxiliary state.
    }

    private void validatePerson(Person person) {
        if (person.getFirstName() == null
                || person.getFirstName().isBlank()) {
            throw new IllegalArgumentException("firstName is required");
        }
    }
}
~~~

`@RepositoryEventHandler(Person.class)` restricts the handler to the Person entity type. If no class is passed, the entity type is inferred from the first parameter of the annotated methods.

The events published by the REST exporter include:

| Event | Timing |
|---|---|
| `BeforeCreateEvent` | Before creating a new entity |
| `AfterCreateEvent` | After creating an entity |
| `BeforeSaveEvent` | Before saving/updating an entity |
| `AfterSaveEvent` | After saving/updating an entity |
| `BeforeLinkSaveEvent` | Before saving a link change |
| `AfterLinkSaveEvent` | After saving a link change |
| `BeforeDeleteEvent` | Before deleting an entity |
| `AfterDeleteEvent` | After deleting an entity |

The commonly used corresponding annotations are `@HandleBeforeCreate`, `@HandleAfterCreate`, `@HandleBeforeSave`, `@HandleAfterSave`, `@HandleBeforeLinkSave`, `@HandleAfterLinkSave`, `@HandleBeforeDelete`, and `@HandleAfterDelete`.

### 4.2. AbstractRepositoryEventListener

If you want to centrally handle multiple entity types or override callbacks by event, you can extend `AbstractRepositoryEventListener`:

~~~java
import org.springframework.data.rest.core.event.AbstractRepositoryEventListener;
import org.springframework.stereotype.Component;

@Component
public class AuditRepositoryEventListener
        extends AbstractRepositoryEventListener<Object> {

    @Override
    protected void onBeforeSave(Object entity) {
        // Validate or prepare data before saving.
    }

    @Override
    protected void onAfterDelete(Object entity) {
        // Record the deleted entity.
    }
}
~~~

This approach can receive multiple entity types; the listener needs to check the type itself if the logic applies only to specific domain types. For handlers targeting a specific entity, an annotated event handler is usually clearer and more type-safe.

### 4.3. Limitations of REST Events

The events above belong to the Spring Data REST exporter pipeline. Do not assume that every `repository.save(...)` call from a service, batch job, or internal code emits the same REST events.

Spring application events are processed synchronously by default. Therefore, a long-running handler can delay the request; exceptions thrown inside a handler can also affect the outcome of the operation being processed.

Use before-events for validation or normalization tailored to the REST flow. For invariants that must hold across every data write path, place the rules in the domain/service layer or shared validation. For sending messages to external systems that must be guaranteed after commit, use a transaction-bound event mechanism or an appropriate transactional outbox; do not treat `@HandleAfterSave` as a guarantee that the transaction has committed successfully.

## 5. Adding Endpoints or Replacing Responses with a Controller

Use `@RepositoryRestController` when you need a custom endpoint bound to a repository's URI space or need to replace the handler for a specific resource.

Example of adding an endpoint that aggregates active Persons:

~~~java
import java.util.List;

import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;

@RepositoryRestController
public class PersonSearchController {

    private final PersonRepository repository;

    public PersonSearchController(PersonRepository repository) {
        this.repository = repository;
    }

    @GetMapping("/people/search/active-summary")
    public ResponseEntity<CollectionModel<EntityModel<Person>>> activeSummary() {
        List<EntityModel<Person>> people = repository.findByActiveTrue()
                .stream()
                .map(EntityModel::of)
                .toList();

        return ResponseEntity.ok(CollectionModel.of(people));
    }
}
~~~

In the example, `/people/search/active-summary` is a custom endpoint located under the Spring Data REST base path. The repository provides the data; the controller performs the aggregation and returns a `CollectionModel` containing `EntityModel` items.

When returning a collection, use `CollectionModel<T>`; when returning a single resource, use `EntityModel<T>` or `RepresentationModel<T>`. If clients need hypermedia navigation, add a self link and item links using Spring HATEOAS or `RepositoryEntityLinks`.

### 5.1. RepositoryRestController or BasePathAwareController?

The two annotations serve different scopes:

- **`@RepositoryRestController`:** used for handlers tied to a repository's URI space. The controller integrates with Spring Data REST configuration, message converters, exception handling, and certain exporter behaviors. Request mappings are handled only when they match the URI space used by exported repositories.
- **`@BasePathAwareController`:** used for custom endpoints located under the base path that are not tied to a specific repository, such as a shared resource or MVC view.

If you use a regular `@Controller` or `@RestController`, the handler sits outside the Spring Data REST integration scope. In that case, do not assume it automatically inherits the same message converters, exception handling, CORS, or base path mapping as repository endpoints.

Define custom routes so they do not conflict with collection, item, or search resources already generated by the exporter. Verify the actual URLs after applying the base path and repository mappings.

## 6. Distinguishing Controllers from Processors and Event Handlers

These three extension points can work with the same domain type, but their timing and responsibilities differ:

| Criterion | RepresentationModelProcessor | REST Event Handler/Listener | RepositoryRestController |
|---|---|---|---|
| Timing | When building the returned representation | During the REST operation lifecycle | When handling an HTTP request matching the mapping |
| Primary input | Representation model | Entity and event | Request, parameters, repository/service |
| Output | Representation enriched with links/metadata | Validation, audit, or event-driven side effects | Custom HTTP response |
| Creates its own endpoint? | No | No | Yes |
| Should be used for | Enriching hypermedia | Pre/post-operation processing | Custom REST flows or custom responses |

For example, when a client calls `GET /people/42`:

1. The repository fetches Person.
2. Spring Data REST builds the representation.
3. The processor can add a `documentation` link to the response.
4. The response is serialized and sent to the client.

When a client calls `POST /people`:

1. The REST exporter converts the request body into an entity.
2. `BeforeCreateEvent` is emitted and a handler can validate the data.
3. The repository saves the entity.
4. `AfterCreateEvent` is emitted.
5. The REST exporter creates the response; the corresponding processor can add links.

When business logic requires a `POST /people/{id}/activate` endpoint with its own workflow, a controller can accept the request, invoke a service to process it, and return an appropriate representation.

## 7. Scenario-Based Examples for Choosing an Extension Point

**Scenario A — All repositories must use the `/api` base path and a maximum page limit of 100.**

Use `RepositoryRestConfigurer` or Spring Boot properties. This is REST exporter configuration, not logic specific to Person.

**Scenario B — Every Person response must include a link to documentation.**

Use `RepresentationModelProcessor<EntityModel<Person>>`. The processor only adds a link to the existing representation.

**Scenario C — Disallow creating a Person without a name via REST and record an entry after saving.**

Use `@RepositoryEventHandler(Person.class)` with `@HandleBeforeCreate` and `@HandleAfterSave`. If the same rule must apply to batch jobs or services, move core validation down to the domain/service layer.

**Scenario D — Need an endpoint aggregating multiple repositories or handling a complex activation workflow.**

Use `@RepositoryRestController` if the endpoint belongs to a repository's URI space; use `@BasePathAwareController` if the endpoint only needs to sit under the base path. Place business logic in a service so the controller only coordinates HTTP.

**Scenario E — Need to change how a domain property maps to JSON.**

Consider a Jackson serializer/deserializer or converter through a configurer. Processors should only be used to modify the representation model/hypermedia; they are not the primary tool for controlling serialization of every field.

## 8. Common Pitfalls When Extending Spring Data REST

| Symptom | Causes to Check |
|---|---|
| Configurer has no effect | Bean is not component-scanned or not registered in ApplicationContext; check auto-configuration and configurer ordering. |
| Configuration changes apply to only some repositories | Rules are scoped to specific domain types or repository exposure; check configuration scope. |
| Processor is not invoked | Check the `EntityModel<T>` generic type, entity class, and bean registration. |
| Links appear with wrong host or base path URI | Links are hardcoded; use Spring HATEOAS link builder or `RepositoryEntityLinks`. |
| Event handler does not run | Bean is not registered, missing `@RepositoryEventHandler`, method annotation does not match the event, or operation bypasses the REST exporter. |
| Handler receives the wrong entity type | Check the first parameter of the handler method and `@RepositoryEventHandler(DomainType.class)`. |
| Event handler slows down requests | Time-consuming synchronous logic; move long-running work to an appropriate background mechanism and manage transactions. |
| Custom controller returns JSON without HAL links | Response is not wrapped in `EntityModel`/`CollectionModel` or required links are not added. |
| Controller is not invoked | Check controller annotation, base path, request mapping, and conflicts with exported repository URIs. |
| Endpoint runs without expected Spring Data REST integration | Check whether `@RepositoryRestController`, `@BasePathAwareController`, or a regular MVC controller is being used. |

## Key Takeaways

Choose an extension point by responsibility: **Configurer** changes exporter configuration; **RepresentationModelProcessor** enriches hypermedia representations; **event handler/listener** reacts to the REST operation lifecycle; **Controller** creates custom endpoints or responses. Place core business validation in the domain/service layer so all call paths comply. When deeply customizing serialization, preserve Spring Data REST's link conversion mechanism or intentionally replace it completely with an understanding of the impact.

## References

- [Spring Data REST — Getting Started and Configuration](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Spring Data REST — RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Data REST — Customizing the JSON Output](https://docs.spring.io/spring-data/rest/reference/customizing/customizing-json-output.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Data REST — Overriding Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
