# Callback Scope Across Repository, Template, and Direct SQL

## 1. Why understand callback scope?

Spring Data Relational R2DBC provides callbacks to intervene in the lifecycle of mapped objects. For example, an application can normalize data before saving, populate audit information, or adjust an entity after reading from the database.

The key point to understand is that callbacks are not SQL filters running for every statement in the application. Callbacks are tied to specific points in Spring Data's entity mapping pipeline.

An R2DBC application often has multiple data access paths:

- Repositories such as ReactiveCrudRepository or R2dbcRepository.
- Templates such as R2dbcEntityTemplate.
- Direct SQL via DatabaseClient.
- Direct R2DBC SPI via Connection, Statement, and Result.
- Custom queries declared with @Query or repository fragments.

These paths participate in the entity lifecycle to different degrees. If a rule is placed only in a callback while another write flow uses direct SQL, that rule may not execute.

For example, an application uses BeforeConvertCallback to uppercase an order code. A repository save may pass through this callback. However, an UPDATE statement written directly with DatabaseClient will not automatically run the callback simply because it updates the same orders table.

This lesson explains which callbacks run at each stage, which APIs go through entity mapping, and how to design when an application combines Repository, Template, and direct SQL.

## 2. What is an entity callback?

An entity callback is a Spring Data extension point that lets an application participate at a specific moment in an entity's lifecycle.

In Spring Data R2DBC, supported store-specific callbacks include:

| Callback | Timing | Purpose |
|---|---|---|
| BeforeConvertCallback | Before the entity is converted into an OutboundRow | Normalize or populate persistent data before mapping |
| BeforeSaveCallback | After the entity has been converted into an OutboundRow, before writing | Adjust the data row to be saved |
| AfterSaveCallback | After saving the entity | Adjust the entity returned after the save operation |
| AfterConvertCallback | After reading and converting a Row into an entity | Adjust the newly materialized entity |
| AuditingEntityCallback | During the BeforeConvert phase | Automatically populate created/modified auditing fields |

R2DBC callbacks return a Publisher, typically implemented with Mono. Thus, callbacks participate in the reactive pipeline and do not need to manually subscribe.

Callbacks are bound to a domain type via a generic type parameter. For example, BeforeConvertCallback<Order> applies to Order. Spring Data uses this type to select callbacks matching the entity being processed.

### 2.1. Callbacks are not listeners for every SQL statement

Callbacks are invoked where Spring Data performs entity mapping. They are not global interceptors for every SQL statement sent to the database.

A callback can be invoked when an entity passes through the mapping lifecycle, but is not invoked merely because:

- A SQL statement touches the corresponding table.
- An UPDATE statement modifies a column of the entity.
- A SELECT statement returns data shaped like the entity.
- An operation runs on the same ConnectionFactory.
- A method resides on a repository interface yet executes custom SQL itself.

Identify the API performing the operation and whether that API passes through the entity lifecycle.

## 3. Callback lifecycle when writing an entity

For an entity save operation through the mapping infrastructure, the conceptual flow is typically:

~~~text
Input entity
     |
     v
BeforeConvertCallback
     |
     v
Convert entity to OutboundRow
     |
     v
BeforeSaveCallback
     |
     v
Execute INSERT or UPDATE
     |
     v
AfterSaveCallback
     |
     v
Entity is returned
~~~

Each callback has a distinct responsibility. Choosing the right point is important, especially when entities are immutable or when you need to change the actual data written to the database.

### 3.1. BeforeConvertCallback

BeforeConvertCallback runs before Spring Data converts the entity into an OutboundRow. This is generally the right place to:

- Normalize persistent fields.
- Populate default values before writing.
- Compute a persistent field from the entity's data.
- Assign application-managed business codes.
- Prepare data that a converter will transform into columns.

Example:

~~~java
import org.reactivestreams.Publisher;
import org.springframework.data.r2dbc.mapping.event.BeforeConvertCallback;
import org.springframework.data.relational.core.sql.SqlIdentifier;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class NormalizeOrderCodeCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Publisher<Order> onBeforeConvert(
            Order order,
            SqlIdentifier table) {

        if (order.getCode() != null) {
            order.setCode(order.getCode().trim().toUpperCase());
        }

        return Mono.just(order);
    }
}
~~~

The callback receives the entity and table name as a SqlIdentifier. It returns a Publisher emitting the entity to be converted and saved.

If using immutable entities, create and return a new instance instead of mutating the current instance:

~~~java
return Mono.just(order.withCode(
    order.code().trim().toUpperCase()
));
~~~

The withCode method in the example assumes the domain type provides an appropriate copy API. How new instances are created depends on the entity design.

### 3.2. BeforeSaveCallback

BeforeSaveCallback runs after the entity has been converted into an OutboundRow and before the write statement executes.

The callback receives three arguments:

- The entity being saved.
- The OutboundRow containing the mapped values.
- The SqlIdentifier representing the table name.

A common point of confusion: if the callback mutates a persistent field on the entity, that change is not automatically reflected in the already-created OutboundRow. Per the callback contract, OutboundRow itself is the data used for writing. Therefore:

- To modify a persistent field of the entity before mapping, use BeforeConvertCallback.
- To adjust column values directly after mapping, modify OutboundRow in BeforeSaveCallback.
- Only modify transient fields on the entity in BeforeSaveCallback if you need to adjust the returned object.

Callback structure example:

~~~java
@Component
public class OrderBeforeSaveCallback
        implements BeforeSaveCallback<Order> {

    @Override
    public Publisher<Order> onBeforeSave(
            Order order,
            OutboundRow row,
            SqlIdentifier table) {

        // You can adjust column values directly in row here.
        // Changing a persistent field on order now does not update row.

        return Mono.just(order);
    }
}
~~~

Do not put persistent-field normalization logic in BeforeSaveCallback and expect entity mutations to be saved. Choose BeforeConvertCallback or update OutboundRow intentionally.

### 3.3. AfterSaveCallback

AfterSaveCallback runs after the save operation completes. The callback can adjust the entity returned by the publisher.

Appropriate use cases:

- Populating information needed only on the returned object.
- Creating transient values for the calling layer.
- Normalizing the response representation after saving.
- Recording observational data without changing already-written data.

AfterSaveCallback is not an opportunity to edit a persistent field and expect Spring Data to automatically emit another UPDATE. SQL has already executed before this callback runs.

If persistent data in the database needs changing, perform the change before mapping/writing or issue an explicit separate write operation.

## 4. Callback lifecycle when reading an entity

When Spring Data reads a row and converts it into an entity, the supported read callback is AfterConvertCallback.

Conceptual flow:

~~~text
SELECT
  |
  v
Database returns Row
  |
  v
Spring Data converter creates entity
  |
  v
AfterConvertCallback
  |
  v
Entity is emitted to subscriber
~~~

AfterConvertCallback is suitable when adjusting an object after mapping, for example:

- Computing a transient property.
- Normalizing the in-memory data representation.
- Populating local information derivable from the newly read entity.
- Applying a simple presentation transformation.

Example:

~~~java
@Component
public class OrderAfterConvertCallback
        implements AfterConvertCallback<Order> {

    @Override
    public Publisher<Order> onAfterConvert(
            Order order,
            SqlIdentifier table) {

        order.setDisplayStatus(
            order.getStatus().toDisplayText()
        );

        return Mono.just(order);
    }
}
~~~

Assuming displayStatus is a transient property, the callback can populate that value for the application layer to use.

AfterConvertCallback only modifies the entity in memory. It does not write the new value back to the database. If a value must be persisted, change it on the write path or perform a separate update operation.

Also do not use AfterConvertCallback as the sole place to enforce a security rule or critical business invariant. Some custom SQL paths may not pass through this callback. Mandatory rules must be enforced at the service/domain layer and, where appropriate, with database constraints.

## 5. Registering callbacks in the Spring ApplicationContext

Spring Data discovers callbacks registered as beans in the ApplicationContext. You can use @Component or declare a @Bean.

Example:

~~~java
@Configuration
public class OrderCallbackConfiguration {

    @Bean
    BeforeConvertCallback<Order> normalizeOrderCode() {
        return (order, table) -> {
            order.setCode(order.getCode().trim().toUpperCase());
            return Mono.just(order);
        };
    }
}
~~~

A dedicated callback class is usually easier to read and manage than a lambda when a project has many callbacks or needs generic entity-type filtering.

The @Component examples in earlier sections are another way to register callbacks. You do not need to create a new callback manager for each repository.

### 5.1. Callbacks are filtered by entity type

Declaring:

~~~java
BeforeConvertCallback<Order>
~~~

means this callback is for Order. It does not automatically apply to Customer or Product.

If a callback class implements multiple interfaces for the same domain type, Spring Data can invoke them at their respective stages:

~~~java
@Component
public class OrderLifecycleCallbacks
        implements BeforeConvertCallback<Order>,
                   AfterConvertCallback<Order> {

    @Override
    public Publisher<Order> onBeforeConvert(
            Order order,
            SqlIdentifier table) {
        return Mono.just(order);
    }

    @Override
    public Publisher<Order> onAfterConvert(
            Order order,
            SqlIdentifier table) {
        return Mono.just(order);
    }
}
~~~

Keeping each callback focused on a single responsibility avoids hard-to-trace side effects.

### 5.2. Callback execution order

If multiple callbacks apply to the same entity type and the same stage, Spring Data invokes them sequentially. The result of an earlier callback is passed to the next callback.

Order can be specified using:

- The @Order annotation.
- The Ordered interface.

Lower order values execute first. Callbacks without an explicit order default to lowest precedence and typically run after explicitly ordered callbacks.

Example:

~~~java
@Component
@Order(50)
public class NormalizeOrderCallback
        implements BeforeConvertCallback<Order> {
    // ...
}
~~~

Spring Data R2DBC includes AuditingEntityCallback with an order of 100. If a custom callback must normalize data before auditing, you can assign an order smaller than 100. If different behavior is needed, design the order based on actual dependencies and test it.

### 5.3. Reactive callbacks must return a Publisher properly

R2DBC callbacks are reactive callbacks. Do not call subscribe() inside a callback and do not block to wait for a result.

Inappropriate:

~~~java
@Override
public Publisher<Order> onBeforeConvert(
        Order order,
        SqlIdentifier table) {

    legacyClient.validate(order).block();

    return Mono.just(order);
}
~~~

This blocks the thread processing the pipeline. If a callback needs an asynchronous operation, compose the publisher:

~~~java
@Override
public Publisher<Order> onBeforeConvert(
        Order order,
        SqlIdentifier table) {

    return validationClient.validate(order)
        .thenReturn(order);
}
~~~

If validationClient only has a blocking API, wrap the call with fromCallable and boundedElastic following proper blocking-isolation principles. However, think carefully before calling external services inside a callback because it increases latency and adds side effects to every entity mapping path.

## 6. Callback scope with Repository

Spring Data R2DBC repositories are built on top of R2dbcEntityOperations and Spring Data's mapping infrastructure. Therefore, standard entity operations through repositories can use lifecycle callbacks.

Example:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

When calling:

~~~java
Mono<Order> saved = orderRepository.save(order);
Mono<Order> loaded = orderRepository.findById(orderId);
~~~

CRUD entity operations pass through the mapping lifecycle:

- Saving an entity: before-convert, before-save, and after-save callbacks apply according to the workflow.
- Reading an entity: AfterConvertCallback can be invoked after the entity is constructed from the data row.
- Operations execute when the publisher is subscribed to, not merely when the method is called.

### 6.1. save and insert/update

Repository save takes an entity and lets Spring Data determine insert or update via new-entity detection.

With this entity save path, before-convert and before-save callbacks can intervene on mapped data. AfterSaveCallback runs after the save operation.

Callbacks do not replace new-entity detection rules, @Id, or @Version. For example, BeforeConvertCallback can normalize data, but should not attempt to reimplement the full persistence lifecycle or manually increment a version managed by Spring Data.

### 6.2. findById and reading entities

When a repository materializes an entity from the database, AfterConvertCallback is the hook to adjust the entity after mapping.

If a method returns a DTO projection or a result type other than the domain entity, do not assume the original entity's callbacks will be invoked in the same way. Identify the actual return type and mapping path being used.

### 6.3. Derived queries and @Query must be distinguished

Not every method on a repository interface follows the same execution path.

- CRUD methods provided by the repository generally go through the entity persistence infrastructure.
- Query methods may use query derivation or declared queries.
- @Query executes application-supplied SQL; the return type and how data is materialized affect mapping.
- DTO projections from @Query may be mapped directly from the SELECT structure and DTO type, not necessarily through the domain entity.

In particular, an @Query UPDATE does not construct an input entity to run BeforeConvertCallback or BeforeSaveCallback. Being declared on a repository interface does not turn it into a save(entity) operation.

For SELECT queries returning a domain entity, verify read callbacks in your exact Spring Data R2DBC version and project return type if logic depends on AfterConvertCallback. Do not place a mandatory business rule in a callback and assume every query method executes it.

### 6.4. delete and deleteById

The documented store-specific entity callbacks in Spring Data R2DBC include BeforeConvert, BeforeSave, AfterSave, AfterConvert, and auditing. This list does not provide a corresponding BeforeDeleteCallback/AfterDeleteCallback pair like some other Spring Data modules.

Therefore, do not assume delete(entity) or deleteById(id) will automatically trigger a standard R2DBC delete callback.

If deletion needs auditing, perform it in the service/use case before or after the delete operation, use an outbox/audit table in the same transaction when atomicity is needed, or use an appropriate database mechanism. Check the exact API of the Spring Data version you are using.

## 7. Callback scope with R2dbcEntityTemplate

R2dbcEntityTemplate is Spring Data R2DBC's mapping-aware abstraction. It performs entity operations and uses the mapping context/converters to convert between entities and relational data.

Entity-oriented template operations typically go through the corresponding lifecycle callbacks:

~~~java
Mono<Order> inserted = template.insert(Order.class)
    .using(order);

Mono<Order> selected = template.selectOne(
    Query.query(Criteria.where("id").is(orderId)),
    Order.class
);
~~~

In the example, the template knows the Order type and performs mapping. Therefore, before-convert/save callbacks or after-convert callbacks on read can participate in the operation's lifecycle.

### 7.1. Entity-oriented insert/update

When the template receives an entity to insert or update, Spring Data has an entity to convert into an OutboundRow. This path fits BeforeConvertCallback and BeforeSaveCallback.

Conceptual example:

~~~java
return template.insert(Order.class)
    .using(order);
~~~

Callbacks are triggered during publisher execution, not at publisher construction time.

### 7.2. Select and AfterConvertCallback

When the template selects a domain entity, data rows are converted into entities. AfterConvertCallback is the post-mapping hook.

~~~java
return template.select(Order.class)
    .matching(Query.query(Criteria.where("status").is("PAID")))
    .all();
~~~

If the result is Flux<Order>, read callbacks can apply to each entity materialized via the mapping mechanism.

If the template only returns scalar values, projections, or another read type not managed under that entity lifecycle, do not assume all entity callbacks are invoked.

### 7.3. Update(Query, Update) is not like save(entity)

The template also provides APIs operating with Query and Update. For example, an application can update a single column without loading the entity:

~~~java
return template.update(Order.class)
    .matching(Query.query(Criteria.where("id").is(orderId)))
    .apply(Update.update("status", "PAID"));
~~~

This path directly specifies the condition and update values. No complete entity is passed in to run BeforeConvertCallback or BeforeSaveCallback the way save(entity) does.

If Query/Update updates are a valid write path in the application, put required rules into service/domain logic before calling the template or express them in SQL/constraints. Do not rely on entity callbacks to guard every such update.

### 7.4. Template may use DatabaseClient underneath

R2dbcEntityTemplate uses DatabaseClient and converters to perform mapping-aware operations. However, sharing DatabaseClient underneath does not mean every DatabaseClient call is automatically elevated to an entity lifecycle operation.

The template knows the entity type and necessary metadata. Direct DatabaseClient SQL only knows the SQL string, bind parameters, and how the application maps Rows. This is the core difference in callback scope.

## 8. Callback scope with DatabaseClient and direct SQL

DatabaseClient is a lower-level SQL API. It manages connections, executes statements, and lets the application map results. It does not infer that an arbitrary Java class is an entity requiring all Spring Data Relational lifecycle callbacks.

Example:

~~~java
return databaseClient.sql("""
        UPDATE orders
        SET status = :status
        WHERE id = :id
        """)
    .bind("status", "PAID")
    .bind("id", orderId)
    .fetch()
    .rowsUpdated();
~~~

The SQL above updates the orders table. Yet DatabaseClient does not receive an Order entity to convert into an OutboundRow. Therefore:

- There is no entity to run BeforeConvertCallback.
- There is no entity OutboundRow built by the entity converter to run BeforeSaveCallback.
- There is no loaded entity result to run AfterConvertCallback.
- There is no entity lifecycle AfterSaveCallback for this SQL operation.

Even when the SQL uses the exact same table and column names as the Order entity, callbacks do not run automatically.

### 8.1. Mapping Row to an entity in DatabaseClient also does not automatically trigger the full lifecycle

Example:

~~~java
return databaseClient.sql("""
        SELECT id, status
        FROM orders
        WHERE id = :id
        """)
    .bind("id", orderId)
    .map((row, metadata) -> new Order(
        row.get("id", Long.class),
        row.get("status", String.class)
    ))
    .one();
~~~

The map function constructs Order directly from Row. This is application-written mapping. DatabaseClient does not automatically invoke AfterConvertCallback merely because the return type is Order.

If you want to reuse callback logic, call shared domain/helper logic or explicitly invoke ReactiveEntityCallbacks. Do not duplicate normalization rules across multiple mappers.

### 8.2. Direct R2DBC SPI also does not invoke entity callbacks automatically

If code uses Connection.createStatement(), Statement.execute(), and Result.map(), the application is working directly with the R2DBC SPI.

These APIs have no awareness of callback beans. They simply execute operations according to the R2DBC driver contract.

If a direct SQL path must adhere to rules such as code normalization, audit logging, or default generation, call a shared domain service before creating the Statement or design appropriate database constraints/triggers.

### 8.3. SQL scripts, stored procedures, and batch jobs

Statements in migrations, admin scripts, stored procedures, or batch jobs outside Spring Data also do not pass through the application's entity callbacks.

When a system has multiple writers, do not rely solely on callbacks to protect data correctness. Rules that must apply to all writers should live at a scope matching all writers:

- Domain/service layer for application business behavior.
- Database constraints for data invariants.
- Triggers when the rule truly belongs in the database and every writer must obey it.
- Outbox/audit tables for change tracking requiring atomicity.
- Shared conventions for batch jobs and integrations.

## 9. Scope comparison table

| Access path | Has entity mapping lifecycle? | Things to note |
|---|---|---|
| Repository save(entity) | Yes | Goes through entity conversion and save callbacks |
| Repository findById/findAll | Yes when materializing domain entity | AfterConvert applies to entities loaded via mapping path |
| Repository deleteById | No delete callback in standard R2DBC callback set | Use service/audit/outbox if delete hooks are needed |
| Repository @Query SELECT | Depends on result type and query mapping path | Do not infer solely from the method being on a repository |
| Repository @Query UPDATE/DELETE | No entity save lifecycle merely because it is a repository method | Custom SQL must enforce required rules itself |
| R2dbcEntityTemplate insert/update entity | Yes | Uses callbacks per entity lifecycle |
| R2dbcEntityTemplate select entity | Yes when materializing entity | AfterConvert can adjust entity after mapping |
| R2dbcEntityTemplate update(Query, Update) | Not like save(entity) | Typically no input entity to run BeforeConvert/BeforeSave |
| DatabaseClient.sql(...) | Not automatically | SQL and Row mapping are controlled by the application |
| Direct R2DBC Connection/Statement | Not automatically | Operates at SPI level, bypassing entity callback registry |
| SQL scripts or stored procedures | No | Spring Data callbacks do not cover external writers |

The table above describes principles by access-path category. For specialized query methods or APIs, verify the call path of your exact Spring Data R2DBC version and actual return type, especially when a callback is business-critical.

## 10. What to use callbacks for and what not to use them for

Callbacks fit small, uniform transformations directly tied to an entity's lifecycle:

- Normalizing fields before saving.
- Setting default metadata.
- Generating audit information.
- Computing transient values after reading.
- Adjusting OutboundRow right before writing.

Callbacks should not become the home for all business logic:

- Do not orchestrate complex multi-repository flows.
- Do not call payment systems or send emails as unrollbackable side effects.
- Do not replace mandatory validation across all write paths.
- Do not replace transactions.
- Do not assume callbacks cover direct SQL.
- Do not run secondary queries per entity where it can cause N+1.
- Do not use AfterSave expecting an automatic extra write.

If logic is a core business rule, put it in the domain/service layer and call it from every relevant use case. Callbacks can invoke small shared logic, but should not be the only place enforcing rules that direct SQL or batch writers must also obey.

## 11. Callbacks are not transaction boundaries

Callbacks execute during entity processing, but a callback itself does not open an independent transaction.

If the repository or template operation is inside a reactive transaction, callbacks execute as part of that reactive pipeline. A callback error can fail the write/read pipeline and cause the transaction manager to roll back.

However, a callback that makes an HTTP call, sends an email, or writes a file is not automatically rolled back when an R2DBC transaction rolls back.

Example to avoid:

~~~java
@Override
public Publisher<Order> onBeforeConvert(
        Order order,
        SqlIdentifier table) {

    return paymentClient.charge(order.getPayment())
        .thenReturn(order);
}
~~~

If payment succeeds yet the subsequent INSERT/UPDATE fails, database rollback cannot refund the charge. Callbacks also make any entity save path trigger unpredictable external side effects.

Keep callbacks light and focused on mapping. For side effects that must coordinate with the database, consider a transactional outbox or saga.

## 12. Callbacks and auditing

Spring Data R2DBC uses AuditingEntityCallback to populate auditing fields before an entity is converted for saving.

Entity example:

~~~java
@Table("orders")
public class Order {

    @Id
    private Long id;

    private String status;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedBy
    private String modifiedBy;
}
~~~

Enabling auditing:

~~~java
@Configuration
@EnableR2dbcAuditing
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
    }
}
~~~

The ReactiveAuditorAware example retrieves the user from the reactive security context. How the auditor is actually resolved depends on the application's authentication setup.

Auditing is a built-in Spring Data callback. It still follows entity mapping scope. A direct SQL UPDATE via DatabaseClient does not automatically run AuditingEntityCallback. If a direct SQL path needs to update updated_at or modified_by, bind those values in SQL or use an appropriate database mechanism.

## 13. Callbacks and domain events are two different mechanisms

Spring Data has multiple extension mechanisms; do not confuse EntityCallback with domain events or application events.

| Mechanism | Purpose |
|---|---|
| EntityCallback | Intervene sequentially in a specific mapping/lifecycle stage |
| Application event | Notify of an event within the ApplicationContext |
| Domain event | Represent a business event emitted by an aggregate |
| Transactional outbox | Persist events durably in the same transaction for post-commit processing |

EntityCallback fits normalizing or adjusting an entity. Domain events fit expressing what happened in the business domain. An outbox fits reliably delivering events to external systems.

Do not use AfterSaveCallback to assume an event was successfully sent to a broker or an email was delivered. When post-commit reliability is required, design an outbox or an appropriate guaranteed event-publishing mechanism.

## 14. Sharing logic across Repository, Template, and direct SQL

If the same rule must apply across multiple access paths, decouple the rule from the callback.

For example, normalizing order codes:

~~~java
public final class OrderCodePolicy {

    private OrderCodePolicy() {
    }

    public static String normalize(String code) {
        if (code == null || code.isBlank()) {
            throw new IllegalArgumentException("Order code is required");
        }

        return code.trim().toUpperCase();
    }
}
~~~

The callback can use the policy:

~~~java
@Component
public class OrderCodeCallback
        implements BeforeConvertCallback<Order> {

    @Override
    public Publisher<Order> onBeforeConvert(
            Order order,
            SqlIdentifier table) {

        order.setCode(OrderCodePolicy.normalize(order.getCode()));
        return Mono.just(order);
    }
}
~~~

The service uses the same policy before executing direct SQL:

~~~java
public Mono<Integer> updateOrderCode(
        Long orderId,
        String requestedCode) {

    String normalized = OrderCodePolicy.normalize(requestedCode);

    return databaseClient.sql("""
            UPDATE orders
            SET code = :code
            WHERE id = :id
            """)
        .bind("code", normalized)
        .bind("id", orderId)
        .fetch()
        .rowsUpdated();
}
~~~

This way:

- Repository save can run the callback.
- Template entity operations can run the callback.
- Direct SQL invokes the policy explicitly.
- The normalization rule is defined in only one place.

If data must always remain normalized even with external writers outside the application, consider adding a CHECK constraint or an appropriate database normalization mechanism. A service policy cannot protect a script that bypasses the service completely.

## 15. Testing callback scope

Do not only test that a callback runs when calling one repository method. Test the actual access paths your application uses.

### 15.1. Testing callbacks on repository save

You can use an integration test with an R2DBC database:

~~~java
@Test
void shouldNormalizeCodeWhenSavingThroughRepository() {
    Order order = new Order();
    order.setCode("  ab-123  ");

    StepVerifier.create(orderRepository.save(order))
        .assertNext(saved ->
            assertThat(saved.getCode()).isEqualTo("AB-123")
        )
        .verifyComplete();
}
~~~

This test verifies the before-convert callback applies on the repository save path and the normalized value is persisted per the mapping.

### 15.2. Testing callbacks on template

Perform insert/select through R2dbcEntityTemplate and verify corresponding callbacks run. This helps catch cases where a template bean was configured with a different mapping context or callback registry.

### 15.3. Testing direct SQL

If using DatabaseClient for an operation, write tests verifying the rule is invoked explicitly in the service/DAO. Do not write tests assuming entity callbacks run automatically on DatabaseClient.

For example, use a pure Java policy and verify the value bound into SQL. If a callback was the only mechanism performing normalization, direct SQL tests will expose the scope gap.

### 15.4. Testing callback order

If multiple callbacks exist, test their order with a simple trace or by checking the transformed output. Especially when both auditing and custom callbacks modify an entity, confirm @Order produces the intended sequence.

### 15.5. Testing errors and reactive behavior

Also verify:

- When the callback emits Mono.error, the mapping operation fails.
- The callback does not subscribe manually.
- The callback does not block the event loop.
- The callback returns a new entity if the domain object is immutable.
- The callback does not cause duplicate side effects when the publisher is subscribed multiple times.
- The callback does not issue secondary queries causing N+1.

## 16. Common mistakes

| Misconception | Consequence | Correct understanding |
|---|---|---|
| Thinking every SQL statement runs entity callbacks | Data via DatabaseClient may skip normalization/auditing | Callbacks are tied to the entity mapping lifecycle |
| Thinking every method in a Repository has the same callbacks | @Query, projections, and modifying queries follow different paths | Identify the query kind and return type |
| Editing a persistent field in BeforeSaveCallback | OutboundRow was built beforehand so written value does not change | Edit the entity in BeforeConvert or edit OutboundRow |
| Using AfterSave to edit already-written data | Modifying returned entity does not automatically run UPDATE | Modify before writing or invoke a separate write operation |
| Using AfterConvert to enforce invariants | Direct SQL may skip the callback | Enforce in domain/service and database |
| Assuming R2dbcEntityTemplate and DatabaseClient are identical | DatabaseClient lacks template's entity lifecycle context | Template knows entity metadata; DatabaseClient handles SQL |
| Using callbacks to send emails or process payments | Side effects do not roll back with the database | Use outbox/saga or post-commit processing |
| Using synchronous callbacks on reactive paths | Can block reactive threads | Use R2DBC reactive callbacks |
| Subscribing manually inside a callback | Creates execution outside the operation's lifecycle | Return a Publisher to Spring Data |
| Assuming a standard R2DBC BeforeDeleteCallback exists | May rely on an unsupported hook | Use service, audit/outbox, or database mechanisms |
| Thinking a callback runs once when the method is called | Publishers can be subscribed multiple times | Callbacks run per execution/subscription of the operation |
| Not checking other SQL paths | Rules apply only to one writer | Check all writers or push invariants into the database |

## 17. Decision workflow for where to place logic

When adding logic to the entity lifecycle, ask:

1. Is the logic truly an entity transformation before or after mapping?
2. If modifying a persistent field, should it happen before building OutboundRow or directly on OutboundRow?
3. Does the logic need to run when reading entities, or only when writing?
4. Do all write paths go through a Repository or entity-oriented Template?
5. Does the application use @Query, DatabaseClient, R2DBC SPI, scripts, or batch writers?
6. Must the rule apply to every writer?
7. If the callback emits an error, how must the database operation and transaction respond?
8. Does the logic have side effects outside the database?
9. Could the callback be invoked again due to retries or new subscriptions?
10. Can the rule be extracted into a shared domain/service policy?

You can choose as follows:

| Type of logic | Appropriate location |
|---|---|
| Normalizing persistent fields before saving through mapping | BeforeConvertCallback |
| Adjusting column values after the entity is mapped | BeforeSaveCallback and OutboundRow |
| Adding transient data to the entity after saving | AfterSaveCallback |
| Computing transient fields after reading an entity | AfterConvertCallback |
| Enforcing mandatory business rules across all use cases | Domain/service layer |
| Protecting data invariants against all writers | Database constraints or appropriate database mechanisms |
| Auditing delete operations | Service/outbox/database mechanism |
| Sending messages after commit | Transactional outbox |
| Direct SQL needing the same normalization rule | Shared policy invoked explicitly |

## 18. Self-check exercises

### Exercise 1: Choosing a callback

You want to trim and uppercase the code field before saving the Order entity. Which callback should you use?

Hint: BeforeConvertCallback, because it runs before the entity is converted into an OutboundRow.

### Exercise 2: Modifying OutboundRow

You want to write an additional column value after the entity has been converted. Which callback should you use?

Hint: BeforeSaveCallback, because this callback receives OutboundRow. Merely changing a persistent property on the entity at this stage does not automatically change the mapped values.

### Exercise 3: Direct SQL

A DAO uses DatabaseClient to UPDATE the orders table. Will BeforeConvertCallback<Order> run automatically?

Hint: No. DatabaseClient executes direct SQL and does not automatically run entity lifecycle callbacks. Call policy/service logic explicitly or express the rule in the database.

### Exercise 4: AfterConvert

You want to compute displayStatus as a transient field after reading Order. Which callback should you use?

Hint: AfterConvertCallback. The value exists only on the returned entity and is not automatically written to the database.

### Exercise 5: Repository @Query

An @Query UPDATE method is defined in OrderRepository. Can you conclude BeforeSaveCallback will run because the method belongs to a repository?

Hint: No. @Query UPDATE is custom SQL, not save(entity). Required rules must be enforced in the service or SQL.

### Exercise 6: Sending email

You want to send an email after an order is saved. Should you call the email client directly inside AfterSaveCallback?

Hint: Do not rely on callbacks for side effects requiring reliability. The transaction may roll back on a subsequent error and the email cannot roll back automatically. Use an outbox to send after commit.

### Exercise 7: Deleting entities

You need to record an audit before deletion. Can you rely on a standard Spring Data R2DBC BeforeDeleteCallback?

Hint: The documented store-specific R2DBC callback set does not provide a corresponding delete callback pair. Perform auditing in the service/use case or use an outbox/trigger as required.

### Exercise 8: Callbacks and transactions

BeforeConvertCallback emits an error when saving Order inside a reactive transaction. What happens?

Hint: The save publisher emits an error. The transaction manager can roll back the transaction according to configured rollback rules. Callbacks do not open separate transactions themselves.

## 19. Key takeaways

- EntityCallback is a hook in Spring Data's entity mapping pipeline, not an interceptor for all SQL.
- Spring Data R2DBC supports BeforeConvertCallback, BeforeSaveCallback, AfterSaveCallback, AfterConvertCallback, and AuditingEntityCallback.
- BeforeConvertCallback is suited for modifying persistent fields before building OutboundRow.
- BeforeSaveCallback runs after mapping; to change write data, edit OutboundRow rather than only mutating persistent fields on the entity.
- AfterSaveCallback adjusts the entity returned after saving without triggering another write automatically.
- AfterConvertCallback adjusts the entity in memory after reading without updating the database.
- Callbacks are registered as beans in the ApplicationContext, selected by entity type, and can be ordered with @Order or Ordered.
- R2DBC callbacks are reactive; return a Publisher and do not manually subscribe or block.
- Repository CRUD and entity-oriented R2dbcEntityTemplate operations go through the corresponding mapping lifecycle.
- @Query, projections, Query/Update updates, and direct SQL must be distinguished by execution path; do not infer callback scope from the repository name alone.
- DatabaseClient and R2DBC SPI do not automatically run entity callbacks when executing direct SQL or mapping Rows manually.
- Do not assume the standard R2DBC callback set includes BeforeDeleteCallback/AfterDeleteCallback.
- Callbacks are not transaction boundaries and do not make non-database side effects rollbackable.
- If a rule must apply across all write paths, extract it into a domain/service policy or protect it with database constraints/mechanisms.
- Test repositories, templates, and direct SQL separately to confirm actual runtime scope.

When designing callbacks in Spring Data Relational R2DBC, place logic at the exact mapping stage it needs to affect and understand which access paths go through that stage. Repositories and entity-oriented Templates provide the entity lifecycle; DatabaseClient and direct SQL simply execute application-provided statements. Separating shared business rules from callbacks helps every write path maintain consistent behavior.
