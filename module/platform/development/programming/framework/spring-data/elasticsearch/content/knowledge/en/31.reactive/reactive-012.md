# Reactive Callbacks, ReactiveAuditorAware, and Enabling Reactive Auditing

Spring Data Elasticsearch provides reactive APIs powered by Reactor. When writing an entity via a reactive repository or ReactiveElasticsearchOperations, data flows through a Publisher pipeline rather than being processed synchronously at the method call.

Within this flow, reactive entity callbacks let you normalize an entity before Spring Data converts it into a Document. Reactive auditing populates metadata such as creation timestamp, modification timestamp, and actor. ReactiveAuditorAware supplies the current actor as a Mono, fitting how reactive Spring Security stores the security context in Reactor Context.

These three concepts are related yet have distinct responsibilities:

- Reactive callbacks hook into the entity lifecycle, such as normalizing SKU codes before conversion.
- ReactiveAuditorAware supplies the current actor so auditing can populate CreatedBy/LastModifiedBy fields.
- Enabling reactive auditing registers the auditing infrastructure so CreatedDate, LastModifiedDate, CreatedBy, and LastModifiedBy annotations are handled along the reactive write path.

This lesson covers the execution flow, implementing callbacks and auditors, configuring auditing, using them with reactive repositories/templates, Reactor Context limits, testing, and common pitfalls.

## 1. Reactive Write Lifecycle

With imperative APIs, a save call typically runs synchronously and returns the entity or result directly. With reactive APIs, calls normally return Mono or Flux. Work runs only when the publisher is subscribed to.

High-level entity write flow:

~~~text
Reactive repository / ReactiveElasticsearchOperations
                    |
                    v
              Publisher<Entity>
                    |
                    v
          Reactive entity callbacks
                    |
                    v
          ReactiveBeforeConvertCallback
                    |
                    v
             Mapping converter
                    |
                    v
             Document / JSON
                    |
                    v
              Elasticsearch
                    |
                    v
             Mono<Entity>
~~~

ReactiveBeforeConvertCallback executes before the entity is converted into a Document. The callback receives the entity and IndexCoordinates, and returns a Publisher emitting the next entity.

Reactive auditing is also integrated via callbacks. When auditing is enabled, the auditing callback reads the current timestamp and auditor and updates the entity's auditing fields according to mapping metadata.

Key point: reactivity does not mean everything automatically runs in parallel. Reactor coordinates execution via Publishers, subscriptions, schedulers, and backpressure. Callbacks must return a publisher honoring the contract and never break the flow with blocking operations.

## 2. Distinguishing Imperative and Reactive Callbacks

Both callbacks have similar shapes, yet their return types differ:

~~~java
// Imperative callback: returns entity directly.
public interface BeforeConvertCallback<T> extends EntityCallback<T> {
    T onBeforeConvert(T entity, IndexCoordinates index);
}

// Reactive callback: returns a Publisher.
public interface ReactiveBeforeConvertCallback<T> extends EntityCallback<T> {
    Publisher<T> onBeforeConvert(T entity, IndexCoordinates index);
}
~~~

In Spring Data Elasticsearch, reactive callbacks typically reside in the Elasticsearch module's mapping event package. Confirm exact imports and signatures in the Javadoc for your dependency version.

Differences:

| Imperative callback | Reactive callback |
|---|---|
| Returns T directly | Returns Publisher<T> |
| Executes synchronously | Executes upon subscription |
| Typically used with ElasticsearchOperations | Used with ReactiveElasticsearchOperations |
| Cannot read Reactor Context | Can read Reactor Context |
| Cannot compose async via Mono/Flux | Can compose Mono/Flux |

Do not implement an imperative callback and expect the reactive template to invoke it. Likewise, do not register the same logic in both places without reason, or normalization may run twice.

## 3. What Does ReactiveBeforeConvertCallback Do?

This callback suits lightweight transformations prior to converting an entity into a Document, such as:

- Trimming technical codes.
- Normalizing SKUs to uppercase with Locale.ROOT.
- Normalizing whitespace in names.
- Normalizing empty strings per schema rules.
- Computing simple derived fields from data already on the entity.

Callbacks should not be responsible for:

- Authorizing access permissions.
- Enforcing business invariants requiring broad context.
- Calling external APIs per entity.
- Sending emails or messages with side effects.
- Orchestrating multi-step transactions.
- Replacing auditing or custom converters.

If a transformation is pure and lightweight, a callback fits well. If I/O or business decisions are needed, perform them in the service before persistence.

## 4. Implementing a Reactive Callback

Suppose we have a Product entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @Field(type = FieldType.Text)
    private String name;

    public Product() {
    }

    // getters and setters
}
~~~

Callback normalizing SKU and name:

~~~java
import java.util.Locale;

import org.reactivestreams.Publisher;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.mapping.event.ReactiveBeforeConvertCallback;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class ProductNormalizationCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        return Mono.fromSupplier(() -> {
            if (product.getSku() != null) {
                product.setSku(
                    product.getSku().trim().toUpperCase(Locale.ROOT)
                );
            }

            if (product.getName() != null) {
                product.setName(product.getName().trim());
            }

            return product;
        });
    }
}
~~~

Mono.fromSupplier defers normalization until subscription and converts any exception thrown in the supplier into a Mono error signal.

Because the callback is a Spring bean, Spring Data's entity callback infrastructure discovers it automatically. Do not invoke the callback manually in a service if the framework already invokes it, or the transformation will run twice.

Package names or interfaces may differ in older releases. Check your actual Spring Data Elasticsearch dependency to confirm the ReactiveBeforeConvertCallback import.

### 4.1. Why Use Mono.fromSupplier?

You may see code written as:

~~~java
return Mono.just(normalize(product));
~~~

This invokes normalize immediately when the callback method is called, prior to Mono subscription. If normalize throws an exception, the error is thrown synchronously at publisher assembly time.

With:

~~~java
return Mono.fromSupplier(() -> normalize(product));
~~~

the computation runs when the subscriber requests data. This is much more natural for synchronous transformations inside reactive callbacks.

If the transformation already returns a Mono from a reactive source, compose that publisher directly rather than wrapping it in Mono.just.

### 4.2. Immutable Entities

For immutable entities or records, the callback must return a new instance:

~~~java
public record Product(
    String id,
    String sku,
    String name
) {
}
~~~

~~~java
@Component
public class ImmutableProductCallback
        implements ReactiveBeforeConvertCallback<Product> {

    @Override
    public Publisher<Product> onBeforeConvert(
            Product product,
            IndexCoordinates index) {

        return Mono.fromSupplier(() -> new Product(
            product.id(),
            product.sku() == null
                ? null
                : product.sku().trim().toUpperCase(Locale.ROOT),
            product.name() == null
                ? null
                : product.name().trim()
        ));
    }
}
~~~

The emitted value becomes the entity passed to the subsequent conversion step. Never construct a new instance and then return the original object.

Spring Data must be able to materialize immutable entities according to the constructor/record binding of your version. Callbacks do not replace constructor mapping configuration.

## 5. Callback Registration and Ordering

Typically, callbacks are registered as Spring beans via @Component or @Bean:

~~~java
@Component
public class ProductNormalizationCallback
        implements ReactiveBeforeConvertCallback<Product> {
    // implementation
}
~~~

You do not need to build a custom callback registry in your service when Spring Data already configures entity callback infrastructure.

If multiple callbacks process the same entity, specify ordering when steps depend on one another. Spring entity callbacks support ordering through Spring ordering mechanisms such as @Order or Ordered in supporting versions.

~~~java
@Component
@Order(10)
public class ProductTrimCallback
        implements ReactiveBeforeConvertCallback<Product> {
    // trim product name
}
~~~

~~~java
@Component
@Order(20)
public class ProductDerivedNameCallback
        implements ReactiveBeforeConvertCallback<Product> {
    // build a normalized search name from the trimmed name
}
~~~

Lower order values usually take higher precedence in Spring's ordering model. Verify ordering behavior on your framework version and write tests asserting the final outcome. Never rely on accidental bean discovery order.

If two callbacks write to the same field, designate a single clear owner or merge tightly coupled steps into one callback.

## 6. Do Not Block or Subscribe Manually Inside Callbacks

Reactive callbacks must return a Publisher for the framework to compose into the write pipeline. Never call block, subscribe, or wait on a Future inside a callback.

Example to avoid:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product product,
        IndexCoordinates index) {

    String category = categoryService.findCategory(product.getSku()).block();

    product.setCategory(category);
    return Mono.just(product);
}
~~~

This code blocks a reactive thread waiting on I/O. It defeats reactive execution, risks starvation, and makes write flows hard to manage.

Also avoid:

~~~java
someMono.subscribe();
return Mono.just(product);
~~~

Manual subscribe creates a detached execution flow. Spring Data loses visibility into when that task finishes or fails.

If asynchronous I/O is genuinely required, compose it into the returned publisher:

~~~java
@Override
public Publisher<Product> onBeforeConvert(
        Product product,
        IndexCoordinates index) {

    return categoryService.findCategory(product.getSku())
        .map(category -> {
            product.setCategory(category);
            return product;
        });
}
~~~

Still, weigh external service calls inside callbacks carefully. If a callback runs per entity in a bulk operation, it can trigger a surge of extra requests, increase latency, and complicate retries. Usually, enrichment belongs in the application service or a dedicated ingestion stage where it is easier to control.

## 7. Errors in Reactive Callbacks

If a callback returns a Publisher that emits an error, that error propagates through the reactive write chain and can fail the save operation.

Example:

~~~java
return Mono.fromSupplier(() -> {
    if (product.getSku() == null) {
        throw new IllegalArgumentException("SKU is required");
    }

    product.setSku(product.getSku().trim().toUpperCase(Locale.ROOT));
    return product;
});
~~~

Application services can map errors at the API boundary:

~~~java
return repository.save(product)
    .onErrorMap(
        IllegalArgumentException.class,
        ex -> new InvalidProductException(ex.getMessage(), ex)
    );
~~~

Never swallow errors inside a callback and return an invalid entity. If an error represents a business rule, validating before persistence is usually better so error codes and messages are explicit.

Do not log the entire entity when a callback fails; entities may contain personal data or sensitive details. Log correlation IDs and minimal technical context instead.

## 8. Reactor Context and Per-Request Data

In reactive applications, per-request metadata usually travels via Reactor Context. It does not depend on a request remaining on the same thread.

This is especially important with reactive Spring Security. The security context is stored in Reactor Context and accessed via ReactiveSecurityContextHolder.

Never use ThreadLocal-based SecurityContextHolder to read the principal inside a reactive callback. When a publisher switches schedulers or resumes on another thread, ThreadLocal may lack the right authentication.

Key guidelines:

- Read request info via reactive context APIs.
- Never store the current principal in a field on a singleton callback bean.
- Never use static variables to hold the current user.
- Never assume thread names identify users.
- Keep actor data scoped to the current subscription.

## 9. What Is ReactiveAuditorAware?

Spring Data Commons defines ReactiveAuditorAware<T> to provide the current auditor reactively.

The contract generally looks like:

~~~java
public interface ReactiveAuditorAware<T> {
    Mono<T> getCurrentAuditor();
}
~~~

T is the actor's type, such as String, UUID, or an application UserId type.

Unlike imperative AuditorAware returning Optional<T>, ReactiveAuditorAware returns Mono<T>. The Mono may:

- Emit an auditor.
- Complete empty if no auditor is present.
- Emit an error if the auditor cannot be determined.

Auditing infrastructure uses this result to populate @CreatedBy and @LastModifiedBy fields.

The interface lives in Spring Data Commons, typically org.springframework.data.domain.ReactiveAuditorAware. Verify the Spring Data Commons dependency paired with your Spring Data Elasticsearch release.

## 10. Implementing an Auditor from Reactive Spring Security

Example for an application using Spring Security WebFlux to store the current username:

~~~java
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class SpringSecurityAuditorAware
        implements ReactiveAuditorAware<String> {

    @Override
    public Mono<String> getCurrentAuditor() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .filter(name -> name != null && !name.isBlank())
            .filter(name -> !"anonymousUser".equals(name));
    }
}
~~~

If there is no SecurityContext or the user is unauthenticated, the publisher completes empty. Auditing then has no actor to write into CreatedBy/LastModifiedBy.

Principal name is a simple choice. In real systems, an immutable user ID can be used instead of a mutable username. If auditor fields store UUIDs, declare ReactiveAuditorAware<UUID> and resolve the principal to its ID.

Never take the actor from a client-supplied field in the request body. The actor must originate from the security context or a trusted system-created execution context.

### 10.1. Without Spring Security

If the application does not use Spring Security, you can still implement ReactiveAuditorAware using Reactor Context or a dedicated context propagation mechanism.

Example reading an actor key written into Context by the service layer:

~~~java
@Component
public class ContextAuditorAware
        implements ReactiveAuditorAware<String> {

    public static final String ACTOR_CONTEXT_KEY = "auditActor";

    @Override
    public Mono<String> getCurrentAuditor() {
        return Mono.deferContextual(context ->
            Mono.justOrEmpty(context.getOrEmpty(ACTOR_CONTEXT_KEY))
                .cast(String.class)
        );
    }
}
~~~

Service attaching the actor to the subscription:

~~~java
return repository.save(product)
    .contextWrite(context ->
        context.put(ContextAuditorAware.ACTOR_CONTEXT_KEY, actorId)
    );
~~~

This is an illustrative example. Only authenticated and trusted layers that verified the actor may set this key. Never accept an actor directly from untrusted payloads.

### 10.2. Batch Flows and System Users

Background import jobs may have no logged-in human user. The application can supply an explicit system actor, such as system:catalog-import.

Never automatically assign unauthenticated HTTP requests to a system user. That would log anonymous requests as legitimate internal operations.

Separate the cases:

- User requests: actor comes from authentication.
- System jobs: explicitly configured service account actor.
- No actor: return Mono.empty if policy allows null/absent auditor fields.
- Mandatory actor required: reject or emit an error per application contract.

## 11. Enabling Reactive Auditing

For Spring Data to populate auditing metadata automatically, enable reactive auditing using the annotation matching your module and version.

Configuration example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.config.EnableReactiveElasticsearchAuditing;

@Configuration
@EnableReactiveElasticsearchAuditing
public class ReactiveElasticsearchAuditingConfiguration {
}
~~~

Register a single ReactiveAuditorAware bean:

~~~java
@Bean
ReactiveAuditorAware<String> auditorAware() {
    return new SpringSecurityAuditorAware();
}
~~~

If SpringSecurityAuditorAware already carries @Component, do not create a second bean of the same type. Avoid registering multiple indistinguishable auditor beans, as auditing infrastructure may fail to resolve which one to use.

Some Spring Data Elasticsearch versions use different annotation names or configurations. Check the EnableReactiveElasticsearchAuditing API in your dependency. Do not use imperative EnableElasticsearchAuditing instead of the reactive annotation when your version provides dedicated reactive auditing configuration.

### 11.1. What the Annotation Activates

When reactive auditing is enabled, Spring Data registers auditing infrastructure/callbacks to:

- Set created date when an entity is created.
- Set last modified date when an entity is saved or updated.
- Set created by if an auditor is available.
- Set last modified by if an auditor is available.

Auditing operates within Spring Data's reactive entity lifecycle. If the application sends raw JSON via the Elasticsearch Java API Client, REST client, or Bulk API directly, entity auditing annotations will not run automatically.

### 11.2. No Need to Call the Auditor Manually

Do not call auditorAware.getCurrentAuditor() in every service to manually populate createdBy when auditing infrastructure is already enabled and entities flow through the reactive persistence path.

Letting the framework manage lifecycle prevents divergent rules across services. If a job needs a specific actor, place the actor into Reactor Context or configure the execution context before saving.

## 12. Declaring Auditing Fields on Entities

Product example:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String sku;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdAt;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedAt;

    @CreatedBy
    @Field(type = FieldType.Keyword)
    private String createdBy;

    @LastModifiedBy
    @Field(type = FieldType.Keyword)
    private String lastModifiedBy;

    // constructors, getters and setters
}
~~~

Auditing annotations come from Spring Data Commons:

- @CreatedDate: creation timestamp.
- @LastModifiedDate: latest modification timestamp.
- @CreatedBy: creating actor.
- @LastModifiedBy: latest modifying actor.

Date fields should use an appropriate temporal type like Instant. Elasticsearch mappings must match the date field; actor fields are typically keyword when exact filtering is needed.

### 12.1. Created vs. LastModified

Example when a new entity is saved:

~~~text
createdAt       = timestamp T1
lastModifiedAt  = timestamp T1 or per modifyOnCreate setting
createdBy       = alice
lastModifiedBy  = alice
~~~

When the entity is saved again at timestamp T2:

~~~text
createdAt       = preserves T1
lastModifiedAt  = updated to T2
createdBy       = preserves alice
lastModifiedBy  = current actor at T2
~~~

Auditing metadata records creation and latest modification only. It is not a full history of every change. If a complete audit trail is needed, maintain an event log or separate history model.

### 12.2. modifyOnCreate and setDates

Auditing configuration in supporting versions allows adjusting whether dates are set and modified metadata is populated on creation via attributes such as setDates or modifyOnCreate.

Do not assume defaults without verifying your version. If your API expects specific behavior, configure it explicitly and write tests covering both inserts and updates.

### 12.3. Empty Auditor

If ReactiveAuditorAware returns Mono.empty(), auditing has no actor to assign. That does not necessarily fail the save operation. Date fields can still be populated independently when date auditing is enabled.

If business policy mandates that every document has createdBy, validate the actor in the application service or configure required auditor handling. Do not assume annotations automatically reject saves when no principal exists.

## 13. Reactive Repositories and ReactiveElasticsearchOperations

A reactive repository can be declared as:

~~~java
import org.springframework.data.elasticsearch.repository.ReactiveElasticsearchRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveElasticsearchRepository<Product, String> {

    Flux<Product> findByCategory(String category);

    Mono<Product> findBySku(String sku);
}
~~~

Saving an entity:

~~~java
Mono<Product> saveResult = productRepository.save(product);
~~~

ReactiveElasticsearchOperations also provides reactive APIs:

~~~java
Mono<Product> saveResult =
    reactiveOperations.save(product);
~~~

Method names/overloads and generic signatures depend on version. The key is using the reactive template/repository rather than invoking imperative Operations and wrapping results in Mono.

Saving multiple entities:

~~~java
Flux<Product> saved =
    productRepository.saveAll(products);
~~~

Verify callback/auditing coverage on the exact write path your application uses, especially for bulk operations. Never assume every API named save or bulk invokes callbacks identically.

## 14. Reactor Context and Spring Security

In reactive applications, the security context travels with the subscription. Service example:

~~~java
public Mono<Product> createProduct(Product product) {
    return productRepository.save(product);
}
~~~

When a request passes through Spring Security WebFlux, the authentication context resides in Reactor Context and ReactiveAuditorAware can read it.

There is no need to pass username through every method parameter if the application uses security context properly. However, if an operation executes on an independent scheduler or background job, ensure context propagates along the reactive chain or an actor is explicitly set.

### 14.1. Context Is Not ThreadLocal

A reactive flow can run across multiple threads. For instance, a publisher starts on an event-loop thread, hops schedulers for some work, and resumes on another thread.

ThreadLocal is unreliable for carrying the actor across these hops. Reactor Context binds to the subscriber and is preserved across reactive operators according to propagation rules.

When using blocking libraries or custom schedulers, understand how context propagates. Never read the principal inside a callback via imperative SecurityContextHolder assuming it will always be present.

### 14.2. Scoping Context Properly

Example:

~~~java
return productRepository.save(product)
    .contextWrite(context ->
        context.put("auditActor", "batch-importer")
    );
~~~

Context belongs solely to that subscription. Never store the actor in a singleton bean's field, as concurrent requests would overwrite each other's data.

## 15. Reactive Auditing and Custom Callbacks Coexisting

An application can have both a ReactiveBeforeConvertCallback normalizing SKUs and reactive auditing recording created/modified metadata.

The two mechanisms address different concerns:

- Custom callbacks transform domain data according to normalization rules.
- Auditing callbacks populate timestamp and actor metadata.

If both modify the entity, execution order may matter. For example, a custom callback should not overwrite createdAt after auditing sets it. Apply ordering when needed and verify on your actual Spring Data version.

Do not implement ReactiveAuditorAware by mutating the entity directly. The auditor provider only returns the actor; auditing infrastructure writes the actor into auditing fields.

## 16. Immutable Entities and Auditing

For immutable entities, auditing infrastructure must create a new instance or use an appropriate persistent property accessor to update auditing fields.

Example record with auditing fields:

~~~java
public record Product(
    @Id String id,
    String sku,
    @CreatedDate Instant createdAt,
    @LastModifiedDate Instant lastModifiedAt,
    @CreatedBy String createdBy,
    @LastModifiedBy String lastModifiedBy
) {
}
~~~

Constructor/record support and auditing field updates depend on the Spring Data version and mapping metadata. For immutable entities, verify constructor parameter names, persistence creator, and auditing property accessors work properly.

Integration tests should re-read the document after insert and update to verify auditing metadata was actually persisted, not just inspect the in-memory object.

## 17. Distinguishing Reactive Auditing from Audit History

Auditing annotations track current state metadata:

- Who created the document?
- When was the document created?
- Who modified it most recently?
- When was it most recently modified?

They do not automatically store:

- Old and new values for every field.
- The reason for a change.
- The complete list of past editors.
- Approval or state-transition events.
- An immutable ledger for compliance audits.

If full history is required, emit dedicated domain events/audit events, append to a history index, or use an event store. Never overwrite LastModifiedBy expecting to trace every historical editor.

## 18. Write Paths That Bypass Reactive Callbacks

Reactive callbacks apply only to operations routed through Spring Data's reactive entity callback infrastructure.

| Write path | Reactive callback/auditing |
|---|---|
| ReactiveElasticsearchRepository.save(entity) | Standard entity-oriented reactive path |
| ReactiveElasticsearchOperations.save(entity) | Standard entity-oriented reactive path |
| Reactive repository saveAll | Verify callback coverage on your actual version/path |
| Raw Elasticsearch Java API Client | Bypasses Spring Data callbacks |
| REST/Bulk API with raw JSON | Bypasses Spring Data callbacks |
| Update request with raw partial Document | Do not assume entity callbacks run |
| Elasticsearch Reindex API | Does not invoke Java reactive callbacks |

If the same index is written by both a reactive service and a raw JSON importer, placing normalization solely in ReactiveBeforeConvertCallback will yield inconsistent data. Use a shared mapper, ingest pipeline, or clear conventions across all producers.

## 19. Testing Reactive Callbacks

Use StepVerifier to test the Publisher instead of calling block in callback tests.

~~~java
@Test
void shouldNormalizeProductBeforeConvert() {
    Product product = new Product();
    product.setSku(" sku-1001 ");
    product.setName("  Wireless Mouse  ");

    StepVerifier.create(
        callback.onBeforeConvert(
            product,
            IndexCoordinates.of("products")
        )
    )
    .assertNext(result -> {
        assertThat(result.getSku()).isEqualTo("SKU-1001");
        assertThat(result.getName()).isEqualTo("Wireless Mouse");
    })
    .verifyComplete();
}
~~~

Unit tests verify the transformation itself. They do not prove Spring registered the callback bean or that reactive repository saves actually invoke it.

### 19.1. Testing ReactiveAuditorAware

You can test the case with no security context:

~~~java
StepVerifier.create(auditorAware.getCurrentAuditor())
    .verifyComplete();
~~~

Testing with authentication in Reactor Context:

~~~java
Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        "alice",
        "n/a",
        List.of(new SimpleGrantedAuthority("ROLE_USER"))
    );

StepVerifier.create(
    auditorAware.getCurrentAuditor()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(authentication)
        )
)
.expectNext("alice")
.verifyComplete();
~~~

This example requires the Spring Security WebFlux dependency and matching imports. Never test with imperative SecurityContextHolder, as that is not the reactive security context source.

### 19.2. Integration Testing Auditing

Using an Elasticsearch test instance or Testcontainers, enable reactive auditing in the Spring context and save via the matching reactive repository/template.

~~~java
StepVerifier.create(productRepository.save(product))
    .assertNext(saved -> {
        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getLastModifiedAt()).isNotNull();
        assertThat(saved.getCreatedBy()).isEqualTo("alice");
    })
    .verifyComplete();
~~~

Then re-read the document to confirm the source stored in Elasticsearch contains the expected metadata.

Verify:

- Inserts populate created date and created by.
- Updates preserve created metadata and update last modified metadata.
- Absent auditor behavior matches policy.
- Batch jobs record the designated system actor.
- Normalization callbacks and auditing work together.
- Raw client paths are not assumed to run auditing automatically.
- Errors in ReactiveAuditorAware propagate cleanly through the save chain.

### 19.3. Testing Deterministic Timestamps

If tests require exact timestamps, check how your auditing version supports configuring a DateTimeProvider or clock/time provider. A fixed provider can be used in tests instead of comparing against imprecise system clocks.

Never add sleeps to wait for timestamps to advance. Use a test provider or assert appropriate temporal relationships.

## 20. Backpressure, Concurrency, and Performance

Reactive callbacks execute inside the write pipeline, so callback duration directly affects publisher completion latency.

Key guidelines:

- Keep transformations CPU-lightweight.
- Avoid unnecessary I/O.
- Never call block.
- Never subscribe manually.
- Never store request-specific state in singleton callbacks.
- Keep callbacks stateless whenever possible.
- Measure latency and throughput of save/saveAll.
- For asynchronous enrichment, enforce timeouts and concurrency caps at the appropriate layer.
- Never fire an external service request per entity during bulk writes without evaluating load.

Reactivity does not make expensive operations free. A callback invoking a slow service for every entity can stall the entire import stream and accumulate many pending publishers.

## 21. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| Reactive callback does not run | Registered imperative callback or write path bypasses reactive mapping | Use ReactiveBeforeConvertCallback and the right reactive template |
| Callback runs yet data is unchanged | Did not return the normalized instance | Return a Publisher emitting the new/updated entity |
| Mono errors before subscription | Used Mono.just(normalize()) with throwing logic | Use Mono.fromSupplier or Mono.defer |
| Reactive thread gets blocked | Called block, Future.get, or synchronous I/O | Compose Publishers and use non-blocking APIs |
| Auditor is always empty | Missing security context or context not propagated | Check ReactiveSecurityContextHolder/Reactor Context |
| Auditor reads the wrong user | Used ThreadLocal/imperative SecurityContextHolder | Use ReactiveSecurityContextHolder |
| CreatedBy is not populated | Reactive auditing not enabled or auditor returns Mono.empty | Enable the right annotation and check provider |
| LastModifiedDate never updates | Write path bypasses auditing or wrong field mapping | Test reactive save path and annotations |
| Auditing works in reactive saves yet not raw bulk | Raw client skips Spring Data callbacks | Use pipeline/mapper or populate metadata before writing |
| Ambiguous auditor beans | Multiple indistinguishable ReactiveAuditorAware beans | Register a single clear bean or configure reference |
| Batch job actor recorded as anonymous | Job lacks security context | Set explicit system actor in Reactor Context |
| Callback mutates shared entity | Mutation causes races or side effects | Create a new instance or request-scoped object |
| Auditing overwrites callback | Ordering or shared field conflict | Assign clear ownership and test callback order |
| Records miss auditing fields | Incompatible constructor/persistent accessor | Verify immutable mapping and version support |
| Test misses new document | Index not refreshed yet or read too early via Search API | Use proper test setup/refresh policy |

## 22. Workflow for Enabling Reactive Auditing in an Application

When implementing:

1. Confirm the application uses reactive Spring Data Elasticsearch rather than wrapping imperative APIs in Mono.
2. Verify Spring Data Elasticsearch and Spring Data Commons versions.
3. Declare auditing fields with CreatedDate, LastModifiedDate, CreatedBy, and LastModifiedBy.
4. Create ReactiveAuditorAware<T> returning Mono<T>.
5. If using Spring Security WebFlux, read the principal via ReactiveSecurityContextHolder.
6. For batch jobs, pass a system actor through a trusted context.
7. Enable reactive auditing using the configuration annotation matching your version.
8. Register custom reactive callbacks if entities need normalization before conversion.
9. Verify ordering when both custom callbacks and auditing modify entities.
10. Use reactive repositories or ReactiveElasticsearchOperations.
11. Check whether raw client/bulk paths bypass callbacks.
12. Write unit tests with StepVerifier and integration tests against Elasticsearch.
13. Monitor errors and write-pipeline latency.

Do not use reactive auditing to replace audit history or business authorization. It only records creation/modification metadata on entities along supported persistence paths.

## 23. Quick Reference Table

| Need | Component |
|---|---|
| Normalize entity before conversion in reactive flow | ReactiveBeforeConvertCallback<T> |
| Return entity from reactive callback | Publisher<T>, typically Mono<T> |
| Synchronous normalization deferred until subscription | Mono.fromSupplier |
| Get current actor in reactive flow | ReactiveAuditorAware<T> |
| Get Spring Security WebFlux principal | ReactiveSecurityContextHolder |
| Read actor from custom Reactor Context | Mono.deferContextual |
| Record creation timestamp | @CreatedDate |
| Record modification timestamp | @LastModifiedDate |
| Record creator | @CreatedBy |
| Record last modifier | @LastModifiedBy |
| Enable reactive auditing | @EnableReactiveElasticsearchAuditing if supported by version |
| Save via reactive repository | ReactiveElasticsearchRepository |
| Save via reactive template | ReactiveElasticsearchOperations |
| Test publishers | StepVerifier |
| Record full change history | Dedicated domain audit events/history |
| Write via raw client | Normalize/audit in application or ingest pipeline |

Reactive callbacks and reactive auditing integrate entity normalization and creation/modification metadata cleanly into the Spring Data Elasticsearch lifecycle. ReactiveBeforeConvertCallback returns a Publisher so Spring Data composes transformations into the write chain; ReactiveAuditorAware returns a Mono providing the actor from Reactor Context or reactive Spring Security; reactive auditing configuration activates populating auditing fields. Avoid manual blocking or subscribing, keep callbacks lightweight and idempotent, distinguish latest-modification metadata from full audit history, and test the exact reactive repository/template paths your application uses.
