# Detecting New Documents and Its Impact on Audit Fields

In Spring Data Elasticsearch, whether an entity is treated as **new** or **existing** directly affects auditing. When saving an entity, auditing may populate the creator and creation timestamp, while updating the modifier and modification timestamp. If Spring Data misidentifies the entity's state, fields such as `createdAt`, `createdBy`, `lastModifiedAt`, and `lastModifiedBy` may fail to reflect real business history.

New/existing state is typically determined from entity metadata on the Spring Data side, such as the ID, version property, or the `Persistable.isNew()` contract. It is not simply a query checking whether the document currently exists in Elasticsearch. In particular, an entity with a pre-assigned ID may be treated as existing unless an appropriate detection mechanism is configured.

For auditing to be reliable, you must design new-entity detection, ID and version assignment, audit field declarations, current-user providers, callback ordering, and rules protecting creation fields from being overwritten together.

## 1. What Does Auditing Record?

Auditing automatically records who created or modified an entity and when the operation took place. In Spring Data, common annotations include:

| Annotation | Meaning |
|---|---|
| `@CreatedDate` | Timestamp when the entity was created |
| `@CreatedBy` | User or process that created the entity |
| `@LastModifiedDate` | Timestamp when the entity was last modified |
| `@LastModifiedBy` | User or process that last modified the entity |

Example product:

~~~text
id: product-42
name: Keyboard
createdAt: 2026-11-13T08:00:00Z
createdBy: account-17
lastModifiedAt: 2026-11-13T08:00:00Z
lastModifiedBy: account-17
~~~

When another user updates the product:

~~~text
id: product-42
name: Mechanical Keyboard
createdAt: 2026-11-13T08:00:00Z
createdBy: account-17
lastModifiedAt: 2026-11-13T09:30:00Z
lastModifiedBy: account-29
~~~

Normally, creation fields reflect initial creation and remain preserved on updates; last-modified fields reflect the latest modification. On initial creation, last-modified fields are also typically populated depending on auditing configuration. Audit fields are business metadata and should not be freely accepted from client requests, as callers could forge history.

## 2. Enabling Auditing in Spring Data Elasticsearch

Spring Data Elasticsearch integrates Spring Data Commons auditing. It can be enabled with `@EnableElasticsearchAuditing` in application configuration.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.elasticsearch.repository.config.EnableElasticsearchAuditing;

import java.time.temporal.TemporalAccessor;
import java.util.Optional;

@Configuration
@EnableElasticsearchAuditing
public class ElasticsearchAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }
}
~~~

This example returns `system` to illustrate a system process. In real applications, `AuditorAware` typically reads the user ID from the security context, request context, or batch job metadata.

If only creation/modification timestamps are needed, auditing can operate without a specific auditor. To populate `@CreatedBy` and `@LastModifiedBy`, provide an appropriate auditor source.

### 2.1. Retrieving the Auditor from the Current User

A realistic implementation can read the principal from Spring Security:

~~~java
@Bean
AuditorAware<String> auditorAware() {
    return () -> {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null || !authentication.isAuthenticated()) {
            return Optional.empty();
        }

        return Optional.of(authentication.getName());
    };
}
~~~

This is an illustrative example; applications must handle anonymous principals, service accounts, and non-HTTP flows. Avoid returning display names if the system needs a stable identifier. Using a user ID or service account ID keeps audits reconcilable long-term.

### 2.2. Configuring DateTimeProvider

If you need to control the time source, configure `DateTimeProvider`. This is useful when testing with a fixed clock or when the system enforces custom time rules.

~~~java
@Bean
Clock auditClock() {
    return Clock.systemUTC();
}

@Bean
DateTimeProvider dateTimeProvider(Clock auditClock) {
    return () -> Optional.<TemporalAccessor>of(Instant.now(auditClock));
}
~~~

Then reference the provider in your auditing configuration according to the API of your release train. Depending on version, the returned temporal type and configuration attribute names may vary; verify `DateTimeProvider` signatures in your actual dependency.

Using UTC for timestamps generally prevents timezone ambiguity. When displaying to users, convert to the target timezone in the presentation layer.

## 3. Declaring Audit Fields on an Entity

An entity can declare audit fields with annotations:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Version
    private Long version;

    private String name;

    @CreatedDate
    @Field(type = FieldType.Date)
    private Instant createdAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedDate
    @Field(type = FieldType.Date)
    private Instant lastModifiedAt;

    @LastModifiedBy
    private String lastModifiedBy;

    // constructors, getters and setters
}
~~~

`@CreatedDate` and `@LastModifiedDate` mark timestamp fields. `@CreatedBy` and `@LastModifiedBy` mark auditor fields. `@Version` is separate versioning metadata that can also participate in new-entity detection.

Entities do not have to include all four audit fields. Choose only what the business requires. For example, a reference data index might need only a created date, while an admin-managed domain needs both created/modified users and timestamps.

### 3.1. Data Types for Timestamp Fields

Common Java types include `Instant`, `LocalDateTime`, or other temporal types supported by Spring Data. For data representing a global point in time, `Instant` is usually easiest to handle because it carries no local timezone ambiguity.

Timestamp fields require matching mappings, usually `date`. Verify the generated mapping and actual serialized format. Do not store audit timestamps as arbitrary strings if the application needs sorting, range queries, or date aggregations.

### 3.2. Audit Fields Should Be Server-Managed

DTOs receiving create/update requests should not allow clients to dictate `createdAt`, `createdBy`, `lastModifiedAt`, `lastModifiedBy`, or `version`. Separating input DTOs from persistence entities prevents client payloads from overwriting server-managed metadata. When mapping DTOs to entities, copy only permitted business fields.

## 4. How Does Spring Data Detect a New Entity?

Spring Data needs to know whether an entity is being persisted for the first time or was previously saved. This information is used across multiple parts of the persistence lifecycle, including auditing.

Typical new-entity detection strategies rely on:

1. The version field, if the entity has an appropriate version property.
2. If there is no version property, inspecting the identifier.
3. If the entity implements `Persistable`, `isNew()` can provide a custom decision.

Exact rules depend on property types and mapping metadata in your Spring Data version. Therefore, check the strategy applying to your specific entity rather than guessing solely from whether the ID has a value.

### 4.1. Based on ID

For an entity without a version property and not implementing `Persistable`, a `null` ID usually indicates a new entity:

~~~java
Product product = new Product();
product.setId(null);
product.setName("Keyboard");
~~~

Spring Data can treat this entity as new because the ID is unset. This is the simple case when the persistence layer generates the ID or assigns it after entity creation.

Conversely, if the ID already has a value:

~~~java
Product product = new Product();
product.setId("product-42");
product.setName("Keyboard");
~~~

the entity may be treated as existing if there is no version field or custom mechanism proving it is new. This can happen even if that document ID has never been indexed into Elasticsearch.

**An assigned ID does not mean the document exists in the index**, yet the default ID-based strategy may still treat the entity as existing.

### 4.2. Based on the Version Property

When an entity has a version property, Spring Data can use its value to detect state. With a nullable object version like `Long`, a `null` version usually signifies a new entity; a non-null version signifies an entity already saved with a current version.

Example:

~~~java
Product product = new Product();
product.setId("product-42"); // Pre-assigned ID
product.setVersion(null);    // Not yet saved with a version
product.setName("Keyboard");
~~~

In this model, a `null` version lets Spring Data recognize the entity as new even though the ID was pre-assigned. After saving succeeds, the persistence layer populates or updates the version according to Elasticsearch's versioning mechanism.

Use a nullable wrapper type like `Long` when `null` must represent the unsaved state. Primitive types like `long` cannot hold `null`; Spring Data has specific rules for primitive defaults, though wrappers express newness more clearly.

### 4.3. Version Both Detects State and Supports Optimistic Locking

`@Version` is not just a new/existing flag. It also participates in concurrent update control. When saving an existing entity with a stale version, Elasticsearch can detect a version conflict instead of silently overwriting a newer update.

Therefore:

- Do not arbitrarily set an existing entity's version to `null` to trick auditing into treating it as new.
- Do not trust version values sent from client requests.
- When reading an entity, keep the version returned by the persistence layer.
- When updating, use the latest entity/version or handle conflicts per business rules.

Using version for new-entity detection only makes sense when the version lifecycle is managed consistently.

## 5. When IDs Are Assigned Before Saving

Many applications require stable IDs prior to writing—for example, IDs from another business system, service-generated UUIDs, product codes, or external import data.

In such cases, relying solely on ID for new-entity detection leads to wrong auditing. Two common options to consider:

1. Use a nullable version property to distinguish unversioned entities from already-saved entities.
2. Implement `Persistable<ID>` to provide the new state according to application rules.

Avoid performing an existence query for every entity just to decide created vs. modified when lifecycle metadata can solve it. That approach adds network round-trips, invites race conditions, and still requires concurrency handling.

## 6. Customizing New State with Persistable

Spring Data Commons provides the `Persistable<ID>` interface with two primary methods: `getId()` returning the identifier and `isNew()` indicating whether the entity is new.

When an entity implements `Persistable`, the application can define newness itself. This is useful when IDs are pre-assigned before the entity is saved.

~~~java
import org.springframework.data.domain.Persistable;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Transient;
import org.springframework.data.elasticsearch.annotations.Document;

@Document(indexName = "products")
public class Product implements Persistable<String> {

    @Id
    private String id;

    @Transient
    private boolean newEntity = true;

    private String name;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
~~~

`newEntity` is marked `@Transient` so it does not become a stored field in Elasticsearch. After saving succeeds, the application must transition the entity's state to persisted. This transition must align with how Spring Data returns entities and your application's object lifecycle.

Service example:

~~~java
Product saved = operations.save(product);
saved.markPersisted();
~~~

This illustrates the state contract; in real applications, make sure the returned object is the one carried forward and that this flag is not lost when entities are copied or reconstructed. For immutable entities or frequently rebuilt aggregates, a version property is often easier to manage.

### 6.1. Why Must the New Flag Stay Synchronized with the Lifecycle?

If the flag remains `true` after saving, the next save may again be treated as a creation and creation fields may be reset. If the flag switches to `false` before the write succeeds, a retry may be treated as an update even though the document was never created.

Transition the state after persistence succeeds and ensure it stays consistent across reloads, retries, and entity reconstruction flows.

## 7. How Does a New Entity Affect Auditing?

The auditing handler inspects newness to decide whether to populate creation fields. Conceptually:

~~~text
Entity submitted to persistence
             |
             v
       Determine isNew
             |
        +----+----+
        |         |
       true      false
        |         |
        v         v
  Populate      Preserve
  created       created
  metadata      metadata
        |         |
        +----+----+
             |
             v
     Update modified
     metadata per config
             |
             v
     Convert entity to
       Elasticsearch
             |
             v
          Index
~~~

Normally expected outcome:

| State | Created fields | Last-modified fields |
|---|---|---|
| New entity | Populated | Populated per auditing config |
| Existing entity | Preserved | Updated |
| No-op or unchanged | Should not be altered unintentionally | Depends on whether a save actually executes |

If a new entity is misidentified as existing, auditing may skip populating creation fields. If an existing entity is misidentified as new, creation fields may be overwritten with a new timestamp or creator.

## 8. Callbacks in the Entity Save Lifecycle

Spring Data Elasticsearch provides Entity Callbacks to run logic at different points while converting and saving documents.

| Callback | Timing | Use Case |
|---|---|---|
| `BeforeConvertCallback` | Before the entity is converted into a Document | Normalize entity, populate values to serialize |
| `BeforeSaveCallback` | After conversion, before writing Document | Adjust or inspect the Document to be saved |
| `AfterSaveCallback` | After write succeeds | Log, emit signals, or post-save work |
| `AfterConvertCallback` | After reading and converting Document to entity | Enrich data after loading |

Auditing typically runs prior to converting the entity into a `Document`, so audit fields are included in the persisted payload.

### 8.1. BeforeConvertCallback

This callback receives the entity and index coordinates. If you need to alter the entity before serialization, this is usually the right checkpoint:

~~~java
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;
import org.springframework.data.elasticsearch.core.event.BeforeConvertCallback;
import org.springframework.stereotype.Component;

@Component
public class ProductBeforeConvertCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product entity,
            IndexCoordinates index
    ) {
        entity.normalizeName();
        return entity;
    }
}
~~~

Example normalizing product name. The callback must return the entity to be converted. If changing fields that must be persisted, do so before conversion so the converter writes the new values into `Document`.

### 8.2. BeforeSaveCallback

This callback runs after conversion, receiving both the entity and `Document`. Use it when you need to adjust document contents after the converter has built them:

~~~java
@Component
public class ProductBeforeSaveCallback
        implements BeforeSaveCallback<Product> {

    @Override
    public Product onBeforeSave(
            Product entity,
            Document document,
            IndexCoordinates index
    ) {
        document.put("schemaRevision", 3);
        return entity;
    }
}
~~~

Here `schemaRevision` is added directly to `Document`. Modifying `Document` in this callback does not necessarily update the in-memory entity object. To update audit fields on the entity so values reflect in both the returned object and the `Document`, perform the update before conversion.

### 8.3. AfterSaveCallback

`AfterSaveCallback` runs after the write operation completes. It can be used to log or publish events:

~~~java
@Component
public class ProductAfterSaveCallback
        implements AfterSaveCallback<Product> {

    @Override
    public Product onAfterSave(
            Product entity,
            IndexCoordinates index
    ) {
        auditLog.recordSaved(entity.getId(), index.getIndexName());
        return entity;
    }
}
~~~

Do not use `AfterSave` to populate `createdAt` or `lastModifiedAt` if those values must be persisted in the document just written. When this callback executes, the write has already completed; mutating the entity now does not automatically trigger another save.

### 8.4. Callbacks Do Not Replace Auditing

You could write a custom callback to populate audit fields, but if the auditing infrastructure is enabled, avoid creating another mechanism writing the same fields without clear precedence rules.

For instance, a custom `BeforeConvertCallback` setting `createdAt` after the auditing callback can overwrite the timestamp auditing just set. Callback ordering therefore matters. When multiple callbacks modify a field, define order via Spring's ordering mechanism and test the final output.

## 9. Callback Order and Impact on Audit Fields

A typical save flow can be visualized as follows:

~~~text
Repository / ElasticsearchOperations.save(entity)
                       |
                       v
             BeforeConvert callbacks
                       |
                       v
              Convert entity
                       |
                       v
               BeforeSave callbacks
                       |
                       v
             Write document to index
                       |
                       v
                AfterSave callbacks
                       |
                       v
                Return saved entity
~~~

The auditing callback is one callback in this lifecycle. When the entity is treated as new, auditing populates creation metadata; when existing, it preserves creation metadata and updates modification metadata per configuration.

If using custom callbacks:

- Do not clear or overwrite audit fields unintentionally.
- Declare explicit ordering if multiple callbacks mutate the same entity.
- Avoid issuing nested saves inside callbacks, as they can create loops or redundant writes.
- Do not emit "saved" business events from `BeforeSave`; emit only after the write succeeds.
- If a callback returns a new instance, ensure audit fields and version are preserved.

## 10. modifyOnCreate and Last-Modified Fields

Auditing configuration offers the `modifyOnCreate` option. Under the typical default configuration, last-modified fields are also populated when a new entity is created. If `modifyOnCreate = false`, auditing may only update modified fields when an entity already exists.

Business meaning:

- If a newly created record should have `lastModifiedAt` equal to `createdAt`, keep modify-on-create enabled.
- If "modified" specifically means an edit occurred after creation, disable modify-on-create.

Align semantics across engineering and reporting teams. If dashboards assume every document has `lastModifiedAt`, disabling modify-on-create can leave new records without a value.

## 11. Are Created Fields Overwritten on Update?

By auditing semantics, creation fields represent initial creation and should remain unchanged when updating an existing entity. Modification fields are updated with the current timestamp and auditor.

Example:

~~~json
{
  "name": "Keyboard",
  "createdAt": "2026-11-13T08:00:00Z",
  "createdBy": "user-17",
  "lastModifiedAt": "2026-11-13T08:00:00Z",
  "lastModifiedBy": "user-17"
}
~~~

~~~json
{
  "name": "Mechanical Keyboard",
  "createdAt": "2026-11-13T08:00:00Z",
  "createdBy": "user-17",
  "lastModifiedAt": "2026-11-13T09:30:00Z",
  "lastModifiedBy": "user-29"
}
~~~

If an update request constructs a fresh entity with only the ID and `name`, leaving created fields empty, the outcome depends on how the entity is identified and how the save/index executes. Do not blindly map created fields to `null` and expect auditing to restore previous values automatically.

For updates, the safe pattern is usually loading the existing entity, modifying business fields, and saving it back—or using an update API with explicit rules preserving audit fields. If the application accepts a detached entity with a pre-assigned ID, ensure new/existing detection works properly and created fields are not wiped.

## 12. Assigned IDs and Auditing Mistakes

Consider an entity with an application-assigned ID:

~~~java
Product product = new Product();
product.setId("SKU-2026-001");
product.setName("Keyboard");

operations.save(product);
~~~

If the entity has no version property and does not implement `Persistable`, an ID-based strategy may see a non-null ID and classify it as an existing entity. Creation fields might then be skipped while last-modified fields are updated as if it were an edit.

This does not mean the document actually exists in Elasticsearch. It simply reflects how Spring Data infers entity state.

### 12.1. Fixing with Version

Declare a nullable version:

~~~java
@Id
private String id;

@Version
private Long version;
~~~

On creation, leave `version` null. After reading a saved document, preserve the version Spring Data returned. Never reset version to `null` on an existing entity just to force auditing to treat it as new.

### 12.2. Fixing with Persistable

If business logic has its own concept of newness, implement `Persistable` and manage the `isNew` flag across the lifecycle. This fits when IDs are pre-assigned and versioning does not suit the data model.

### 12.3. Do Not Use In-Memory ID to Conclude Document Existence

An ID can be generated at the application layer before any write happens. Conversely, an ID may exist in the index while the current detached entity lacks a version. Distinguish three related but non-identical states: an ID has been generated, the document has been persisted, and Spring Data classifies the entity as new vs. existing.

## 13. save, index, and Other Write APIs

In Spring Data Elasticsearch, repositories or `ElasticsearchOperations.save(...)` are abstractions that apply Spring Data mapping and entity callbacks through the lifecycle.

If calling the low-level Elasticsearch Java Client or REST API directly, the application assumes responsibility for field serialization, populating created/modified metadata, passing version/concurrency tokens, and applying ID/state rules. Do not expect Spring Data callbacks or auditing to run automatically on low-level client writes.

### 13.1. save with an Existing ID

An Elasticsearch index operation writes a document by ID. If the ID does not exist, it can create the document; if the ID already exists, it can replace the document per index semantics. That storage writes work as an upsert does not mean auditing automatically knows whether it is a creation or an update.

Auditing relies on the entity state determined by Spring Data. Therefore, ensure new-entity detection matches how your application generates IDs.

### 13.2. Update API and Scripts

Elasticsearch-level partial updates or scripted updates can modify documents without running auditing entity callbacks. When using these APIs, manage modified fields explicitly inside the script/params or route the operation through a callback-supported abstraction.

Example update script changing only `name`:

~~~json
{
  "script": {
    "source": "ctx._source.name = params.name",
    "params": {
      "name": "Mechanical Keyboard"
    }
  }
}
~~~

This script does not automatically update `lastModifiedAt` or `lastModifiedBy`. To keep audit metadata consistent, include them explicitly in the script or use an application-managed update mechanism.

### 13.3. Bulk Operations

The Bulk API and Spring Data bulk abstractions may follow different mapping paths than single-entity saves. Do not assume auditing callbacks run for every item across all versions and overloads.

When using bulk indexing for data requiring auditing:

- Verify which callbacks run in your API/version.
- If callbacks do not run, prepare audit fields before constructing bulk requests.
- Set created fields and modified fields according to each item's new/existing state.
- Inspect per-item responses and handle retries.

## 14. Auditing in Data Imports and Synchronization

Imports often carry IDs assigned by external sources. This is a common place for create vs. update confusion.

For instance, a batch might contain brand-new records with source-assigned IDs, existing records needing content updates, or records with IDs where the source does not know whether the document already exists.

The application must define semantics:

| Scenario | Typical Audit Rule |
|---|---|
| New creation from external source | Populate created and modified using import timestamp/user |
| Updating an existing document | Preserve created, update modified |
| Re-syncing identical data with no changes | Consider skipping the write to avoid unnecessary `modifiedAt` bumps |
| Overwriting the entire document | Ensure created fields are preserved if business rules require |
| Historical import with original timestamps | Decide explicitly whether to keep source timestamps or record import time; do not mix meanings |

If preserving original creation times from an external system is needed, design a separate field or an explicit authoritative import rule. Do not let auditing overwrite historical timestamps that business rules require preserving.

## 15. No-Ops and Last-Modified Fields

A save operation may be dispatched even when business fields did not change. Depending on the API and update mechanism, auditing may still produce a fresh modified timestamp because the lifecycle treats it as a save.

If `lastModifiedAt` should only change when data actually changes:

1. Compare new values with current values.
2. If there is no difference, skip the write.
3. If there is a difference, update the entity and let auditing populate modified fields.

With update scripts, you can mark a no-op when nothing changed:

~~~painless
if (ctx._source.status == params.status) {
    ctx.op = 'noop';
} else {
    ctx._source.status = params.status;
    ctx._source.lastModifiedAt = params.modifiedAt;
    ctx._source.lastModifiedBy = params.modifiedBy;
}
~~~

In this case, the script owns updating modified metadata because the operation bypasses regular auditing callbacks. If the system uses both repository `save` and scripted updates, use a single timestamp and actor convention so the two write paths do not diverge.

## 16. Callback Order and Multiple Callbacks Modifying the Same Entity

An application can have multiple callbacks: normalization callbacks, slug-generation callbacks, auditing callbacks, and callbacks adding tenant or schema metadata.

If a later callback modifies a field auditing just populated, the final value can differ from expectations. Use Spring's supported ordering mechanism to declare execution order and test the post-save result.

~~~java
@Component
@Order(100)
public class NormalizeProductCallback
        implements BeforeConvertCallback<Product> {

    @Override
    public Product onBeforeConvert(
            Product product,
            IndexCoordinates index
    ) {
        product.setName(product.getName().trim());
        return product;
    }
}
~~~

Specific numeric orders should be chosen relative to the auditing callback registered in your application version. Do not assume every callback shares the numbers in the example. If a callback only alters business fields, placing it before auditing keeps the lifecycle intuitive; if a callback needs to read assigned audit fields, it must run after auditing.

## 17. Testing New State and Audit Fields

Test auditing with both auto-generated IDs and pre-assigned IDs.

### 17.1. Testing Creation

Preconditions: entity is classified as new, `AuditorAware` returns user A, and clock returns timestamp T1.

Expectations:

- `createdAt = T1`.
- `createdBy = user A`.
- `lastModifiedAt` matches modify-on-create configuration.
- `lastModifiedBy` matches modify-on-create configuration.
- Version is set after persistence per the versioning mechanism.

### 17.2. Testing Updates

Load the saved entity with its current version, switch auditor to user B, advance the clock to timestamp T2, modify business fields, and save.

Expectations:

- `createdAt` remains T1.
- `createdBy` remains user A.
- `lastModifiedAt = T2`.
- `lastModifiedBy = user B`.
- Version increments or updates per the versioning mechanism.

### 17.3. Testing Assigned IDs

Create an entity with a pre-assigned ID and `null` version. Verify the entity is treated as new and creation fields are populated. After saving, read the entity back and verify the subsequent save is treated as an update.

If using `Persistable`, test both that `isNew` flips to `false` after a successful save and stays valid when a write fails.

### 17.4. Testing Entities with Non-Null IDs That Do Not Exist Yet

This catches a classic mistake:

1. Generate a deterministic ID.
2. Confirm the document does not exist in the index.
3. Instantiate the entity with that ID.
4. Check new-entity detection.
5. Save and verify creation fields are populated.

If the entity is treated as existing merely because its ID is non-null, configure versioning or `Persistable` per your design.

## 18. Edge Case Matrix

| Case | Risk | What to Verify |
|---|---|---|
| Null ID, no version | Usually new | Creation fields populated |
| Pre-assigned ID, null version | Easy to misclassify without version strategy | Entity treated as new |
| Non-null ID, no version | May be treated as existing | Choose `Persistable` or another strategy if ID is new |
| Non-null version | Existing | Creation fields preserved |
| Version set to null on existing entity | May be treated as new | Do not lose current version |
| Client sends `createdAt` | Forgery risk | DTO prevents overwriting |
| `AuditorAware` returns `Optional.empty` | `By` fields receive no new value | Handle system actor or intentionally allow null |
| Custom callback edits audit field | Can overwrite auditing | Explicit callback ordering |
| Update via low-level client | Callbacks do not run automatically | Script/client updates modified fields explicitly |
| Bulk write | Callback behavior depends on API/version | Check audit fields on each item |
| Save with unchanged data | `ModifiedAt` may change despite unchanged content | Define no-op semantics |
| Write fails | Must not mark entity persisted prematurely | Retries still detect state accurately |

## 19. Process for Designing Reliable Auditing

When adding auditing to an entity:

1. Determine whether IDs are assigned by Elasticsearch, the application, or an external system.
2. Choose an appropriate new-entity detection strategy: ID, version, or `Persistable`.
3. If IDs are pre-assigned, never assume an entity is existing simply because its ID is non-null.
4. Declare created/modified fields with appropriate data types and mappings.
5. Enable `@EnableElasticsearchAuditing`.
6. Provide `AuditorAware` if `createdBy`/`lastModifiedBy` are required.
7. Configure `DateTimeProvider` if time-source control is needed.
8. Verify which callbacks are invoked on save, bulk, and low-level client paths.
9. Ensure created fields are preserved across updates.
10. Ensure modified fields update according to business semantics.
11. Control callback ordering when multiple callbacks modify the same entity.
12. Test inserts, updates, assigned IDs, retries, no-ops, and version conflicts.

## 20. Conclusion

Auditing depends on whether Spring Data classifies an entity as new or existing. When an entity is new, auditing populates creation metadata; when existing, creation fields should be preserved and modification fields updated per configuration. Detection typically relies on a version property, ID, or the `Persistable.isNew()` contract.

Entities with pre-assigned IDs require special care: a non-null ID does not prove a document exists, yet the default ID-based strategy may treat the entity as existing. Use a nullable version or `Persistable` when you need to clearly represent a new entity with an assigned ID. Never reset an existing entity's version to null to force auditing down the creation branch.

In Spring Data Elasticsearch, `@EnableElasticsearchAuditing`, `AuditorAware`, created/modified annotations, and entity callbacks work together to populate metadata during the save lifecycle. `BeforeConvertCallback` suits entity modifications before serialization; `BeforeSaveCallback` works on the `Document` after conversion; `AfterSaveCallback` fits post-save tasks. Direct client writes or certain bulk paths may bypass the callback lifecycle, so verify your actual APIs and manage audit fields explicitly when needed.

Test new entities, persisted entities, assigned IDs, versioning, callback ordering, retries, and no-op updates separately. Only when new/existing state is determined accurately will created and last-modified fields reliably reflect document history.
