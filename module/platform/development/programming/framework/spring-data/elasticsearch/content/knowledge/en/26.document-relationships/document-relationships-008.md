# `@Routing`, `RoutingResolver`, and Reading/Writing Parent-Child Data

In Elasticsearch, routing determines which shard a document is sent to during index, get, update, or delete operations. This is critical when an index has multiple shards and the application needs to access documents via a stable routing key rather than relying solely on `_id`.

Routing is especially important for parent-child relationships. Elasticsearch uses a `join` field to represent parent and child documents within the same index, but related documents must reside on the same shard. Therefore, child documents must be indexed with the exact same routing value used by the root parent; in default setups, this value is typically the root parent's ID.

Spring Data Elasticsearch supports routing through three main mechanisms:

- `@Routing`: declares routing at the entity level, reading the value from a property or SpEL expression.
- `RoutingResolver`: provides custom routing logic for entities or requests without an entity.
- `JoinField` with `@JoinTypeRelations`: represents the relation type and parent ID in a `join` field; Spring Data can automatically infer routing from the parent in single-level relationships.

Understanding these mechanisms ensures `save`, `get`, `update`, `delete`, and parent-child queries hit the right shard, avoiding situations where documents can be written but cannot be read back.

## 1. What is routing in Elasticsearch?

An Elasticsearch index is divided into primary shards. When indexing a document, Elasticsearch must decide the target shard. By default, the shard is chosen from the document's `_id`. If the request specifies a routing value, Elasticsearch uses that routing value instead of `_id` to compute the shard.

For example:

```http
PUT /orders/_doc/O-100?routing=customer-42
Content-Type: application/json

{
  "order_id": "O-100",
  "customer_id": "customer-42",
  "status": "PAID"
}
```

Document `O-100` is routed using `customer-42`. When reading or deleting this document by ID, the request needs the same routing value:

```http
GET /orders/_doc/O-100?routing=customer-42
```

If routing is omitted, Elasticsearch may look on the shard computed from ID `O-100`, while the document actually lives on the shard computed from `customer-42`. The result can be a 404 even though the document exists.

### 1.1. Routing is not the ID

The two concepts serve different purposes:

| Value | Role |
|---|---|
| `_id` | Unique identifier of the document within the index. |
| `routing` | Value used to choose the shard holding the document. |
| Parent ID | Identifier of the parent document in a `join` relationship. |

In single-level parent-child, routing is usually equal to the parent ID. However, routing does not always have to equal `_id` or parent ID; an application can use a tenant ID, customer ID, or another key as long as all related documents are routed consistently.

### 1.2. Why is custom routing needed?

Custom routing is useful when:

- Documents for the same tenant should live on the same shard.
- Orders for the same customer are typically read together.
- Parent and child must share a shard for joins to work.
- The application regularly queries by a known partition key and wants to limit the shards searched.

Routing can reduce fan-out when requests include the appropriate routing value. However, routing does not automatically create isolated data partitions, does not replace authorization, and can cause load skew if one routing key grows too large.

## 2. Declaring `@Routing` in Spring Data Elasticsearch

`@Routing` is a class/entity-level annotation. The annotation's value tells Spring Data how to obtain the routing value for operations on that entity.

Example entity with a `routing` property:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.Routing;

@Document(indexName = "orders")
@Routing("routing")
public class OrderDocument {

    @Id
    private String id;

    @Field(name = "customer_id", type = FieldType.Keyword)
    private String customerId;

    @Field(type = FieldType.Keyword)
    private String status;

    @Field(type = FieldType.Keyword)
    private String routing;

    // constructors, getters, setters
}
```

In this example, `@Routing("routing")` means the property named `routing` is used as the routing value. This value is read from the entity when Spring Data performs entity-based operations.

Example saving a document:

```java
OrderDocument order = new OrderDocument();
order.setId("O-100");
order.setCustomerId("customer-42");
order.setStatus("PAID");
order.setRouting("customer-42");

orderRepository.save(order);
```

Spring Data uses `customer-42` as routing when saving the document. When the entity is read back with its `routing` property intact, subsequent entity-based operations can continue using that same value.

### 2.1. The annotation does not go on the property

A common mistake is placing `@Routing` directly on the `routing` field. The annotation goes on the class and takes the property name as its parameter:

```java
@Document(indexName = "orders")
@Routing("routing")
class OrderDocument {
    @Id String id;
    String routing;
}
```

The `routing` property must still exist on the entity and be populated with the right value before writing.

### 2.2. Using SpEL to compute routing

If routing must be derived from multiple properties, you can declare a SpEL expression:

```java
@Document(indexName = "orders")
@Routing("@orderRouting.getRouting(#entity)")
public class OrderDocument {
    // fields and accessors
}
```

The `orderRouting` bean needs a method taking the entity and returning the routing value:

```java
import org.springframework.stereotype.Component;

@Component("orderRouting")
public class OrderRouting {

    public String getRouting(Object entity) {
        if (entity instanceof OrderDocument order) {
            return order.getCustomerId();
        }
        return null;
    }
}
```

In SpEL, `#entity` refers to the entity being processed. The method must return a `String` routing value or `null` if no routing applies.

SpEL fits when routing rules can be expressed concisely from the entity. When logic is complex, depends on request context, or needs to vary per operations instance, `RoutingResolver` is usually clearer.

## 3. What is `RoutingResolver`?

`RoutingResolver` is a Spring Data Elasticsearch interface for determining routing values. It supports two scenarios:

- With an entity: `getRouting(bean)` extracts routing from the object being saved/read.
- Without an entity: `getRouting()` returns a default routing value for ID-only operations or queries without an entity.

The interface also provides factory method `RoutingResolver.just(value)` to build a resolver that always returns a fixed value.

Package:

```java
import org.springframework.data.elasticsearch.core.routing.RoutingResolver;
```

### 3.1. Fixed routing with `RoutingResolver.just`

When the routing value is known ahead of time, use the provided resolver:

```java
String orderId = "O-100";
String customerRouting = "customer-42";

OrderDocument order = operations
        .withRouting(RoutingResolver.just(customerRouting))
        .get(orderId, OrderDocument.class);
```

To delete a document by ID:

```java
operations
        .withRouting(RoutingResolver.just(customerRouting))
        .delete(orderId);
```

`withRouting(...)` returns an operations instance configured with that routing. You can reuse it across operations needing the same routing:

```java
ElasticsearchOperations customerOperations =
        operations.withRouting(RoutingResolver.just(customerRouting));

OrderDocument order = customerOperations.get(orderId, OrderDocument.class);
customerOperations.delete(orderId);
```

This is especially important for `get(ID)` and `delete(ID)`: the request only has an ID, so Spring Data has no entity from which to read a routing property. The application must supply routing via a resolver or appropriate API.

### 3.2. Creating a custom resolver

If different entities have different routing rules, you can implement `RoutingResolver`:

```java
import org.springframework.data.elasticsearch.core.routing.RoutingResolver;

public class TenantRoutingResolver implements RoutingResolver {

    @Override
    public String getRouting() {
        // Used when there is no entity to inspect.
        return null;
    }

    @Override
    public <T> String getRouting(T bean) {
        if (bean instanceof OrderDocument order) {
            return order.getCustomerId();
        }

        if (bean instanceof CustomerDocument customer) {
            return customer.getTenantId();
        }

        return null;
    }
}
```

Applying the resolver:

```java
RoutingResolver resolver = new TenantRoutingResolver();
ElasticsearchOperations tenantOperations = operations.withRouting(resolver);

tenantOperations.save(order);
```

`withRouting` creates an `ElasticsearchOperations` instance with the custom resolver. The resolver can return routing based on entity type, tenant, customer, or another business rule.

Do not base a resolver on unauthenticated request input. If routing relates to a tenant, obtain the tenant ID from a trusted server-side security context or source.

### 3.3. Comparing `@Routing`, SpEL, and `RoutingResolver`

| Mechanism | How it works | When it fits |
|---|---|---|
| `@Routing("routing")` | Reads value from the specified property. | Entity already has an explicit routing field. |
| `@Routing("@bean.method(#entity)")` | Uses SpEL to call a bean to compute routing. | Short rules based on entity fields. |
| `RoutingResolver` | Customizes routing lookup for an operations instance. | Complex logic or routing that varies by execution flow. |
| `RoutingResolver.just(value)` | Always returns one fixed routing value. | `get(ID)`, `delete(ID)`, or queries with known routing. |

Choose one clear routing source per operation flow. When both an annotation and a custom resolver are present, understand that the resolver attached to the operations instance governs the routing that instance uses.

## 4. Parent-child relationships in Elasticsearch

Elasticsearch is not a relational database. Parent-child relationships are represented using the `join` mapping type, where parent and child are separate documents inside the same index.

Forum example:

- `question` is a parent document.
- `answer` is a child document of `question`.
- `comment` is also a child document of `question`.
- `vote` is a child document of `answer`.

```text
question Q1
   |
   +---- answer A1
   |        |
   |        +---- vote V1
   |        +---- vote V2
   |
   +---- answer A2
   |
   +---- comment C1
```

Parent-child joins carry several important constraints:

- Parent and child must reside in the same index.
- Related documents must reside on the same shard.
- Each child document has one parent according to the declared join relationship.
- Relationships are described by a single `join` field in the mapping.
- Elasticsearch does not provide automatic cascade updates/deletes like a relational ORM.

Parent-child fits when parent and child documents need independent updates or child counts are large, but it should not be used merely to mimic every data relationship. Join queries cost more than regular field queries; if data is frequently read in a fixed structure, denormalization or `nested` mapping may be more suitable.

## 5. Declaring join mapping with `@JoinTypeRelations`

Spring Data Elasticsearch supports join mappings via `JoinField` and `@JoinTypeRelations`.

Example entity shared across `question`, `answer`, `comment`, and `vote`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.annotations.Routing;
import org.springframework.data.elasticsearch.core.join.JoinField;

@Document(indexName = "statements")
@Routing("routing")
public class Statement {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String text;

    @Field(type = FieldType.Keyword)
    private String routing;

    @JoinTypeRelations(relations = {
            @JoinTypeRelation(parent = "question", children = {"answer", "comment"}),
            @JoinTypeRelation(parent = "answer", children = "vote")
    })
    private JoinField<String> relation;

    // constructors, getters, setters
}
```

In this example:

- `@JoinTypeRelations` declares the graph of relationship types.
- `question` can have `answer` and `comment`.
- `answer` can have `vote`.
- `JoinField<String>` stores the relation name and parent ID.
- The generic type `String` must match the `@Id` property's type.
- `@Routing("routing")` declares that the `routing` property provides the routing value when the entity needs custom routing.

Spring Data can generate the corresponding `join` mapping when creating the index:

```json
{
  "properties": {
    "relation": {
      "type": "join",
      "relations": {
        "question": ["answer", "comment"],
        "answer": "vote"
      }
    },
    "routing": {
      "type": "keyword"
    }
  }
}
```

Only one `join` field may be declared per index. You can define multiple relations inside that field, but do not create multiple independent `join` fields to model separate relationships in the same index.

## 6. `JoinField` represents parent and child

`JoinField<ID>` has two commonly used constructor forms:

```java
new JoinField<>("question")
new JoinField<>("answer", questionId)
```

- For a parent/root document, pass only the relation name.
- For a child document, pass the relation name and the parent's ID.

Example:

```java
Statement question = new Statement();
question.setId("Q-100");
question.setText("How is the weather?");
question.setRelation(new JoinField<>("question"));

Statement answer = new Statement();
answer.setId("A-101");
answer.setText("Sunny");
answer.setRelation(new JoinField<>("answer", question.getId()));
```

Parent and child documents are two independent documents. `JoinField` does not hold the entire parent object and does not automatically store children in an array inside the parent.

When Elasticsearch serializes the `join` field, the parent document can be represented as:

```json
{
  "id": "Q-100",
  "text": "How is the weather?",
  "relation": "question"
}
```

Child document:

```json
{
  "id": "A-101",
  "text": "Sunny",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  }
}
```

The JSON above shows the semantics of the `join` field; when working through Spring Data, let the converter handle `JoinField` rather than constructing raw JSON `_source` manually unless necessary.

## 7. Save the parent first, then save children

Example saving a question and two answers:

```java
Statement savedQuestion = repository.save(
        createStatement("How is the weather?", new JoinField<>("question"))
);

Statement sunnyAnswer = repository.save(
        createStatement("Sunny", new JoinField<>("answer", savedQuestion.getId()))
);

Statement rainyAnswer = repository.save(
        createStatement("Rainy", new JoinField<>("answer", savedQuestion.getId()))
);
```

Save the parent first so you have the ID and routing needed for children. In a real application, ensure the parent ID is generated and known before constructing each child's `JoinField`.

### 7.1. Automatic routing for single-level relationships

When using a join type, Spring Data Elasticsearch automatically uses the `parent` property of `JoinField` as the routing value in single-level parent-child relationships.

For example, an `answer` child with parent `Q-100` defaults to routing `Q-100`. That sends parent and child to the same shard.

This holds for single-level relationships:

```text
question Q-100 (root)
    |
    +---- answer A-101 (routing = Q-100)
    +---- answer A-102 (routing = Q-100)
```

When a child's direct parent is the root, the parent ID is also the routing value to use.

### 7.2. Multi-level relationships must route to the root parent

With a multi-level relationship:

```text
question Q-100
    |
    +---- answer A-101
              |
              +---- vote V-201
```

The `vote`'s direct parent is `answer` `A-101`, yet all three documents must reside on the same shard. Therefore, the `vote`'s routing must be the routing value of root `question` `Q-100`, not `answer` `A-101`'s ID. In this default example, the root question's routing value is its ID `Q-100`.

Example:

```java
Statement vote = new Statement();
vote.setId("V-201");
vote.setText("+1 for the answer");
vote.setRouting(savedQuestion.getId());
vote.setRelation(new JoinField<>("vote", sunnyAnswer.getId()));

repository.save(vote);
```

Here:

- `JoinField` stores the direct parent `A-101`.
- `routing` stores the root parent `Q-100`.

This is a crucial distinction: parent ID in `JoinField` describes the logical relationship, whereas `routing` determines the shard. In multi-level trees, these two values are not necessarily the same. If the root parent was saved with custom routing different from its ID, descendants must use that exact custom routing; do not blindly assume routing equals the root ID.

## 8. `@Routing` and `RoutingResolver` in parent-child

An entity can use `@Routing("routing")` to read routing from a property. In the `question`/`answer`/`vote` example:

- Root `question` can use its own ID as routing when needed.
- Single-level `answer` can take parent ID from `JoinField` via default join routing.
- Multi-level `vote` must explicitly be assigned the root question's routing.

Entity builder example:

```java
private Statement newQuestion(String id, String text) {
    Statement statement = new Statement();
    statement.setId(id);
    statement.setText(text);
    statement.setRelation(new JoinField<>("question"));
    statement.setRouting(id);
    return statement;
}

private Statement newAnswer(String id, String text, Statement question) {
    Statement statement = new Statement();
    statement.setId(id);
    statement.setText(text);
    statement.setRelation(new JoinField<>("answer", question.getId()));
    statement.setRouting(question.getId());
    return statement;
}

private Statement newVote(String id, String text,
                          Statement answer, Statement rootQuestion) {
    Statement statement = new Statement();
    statement.setId(id);
    statement.setText(text);
    statement.setRelation(new JoinField<>("vote", answer.getId()));
    statement.setRouting(rootQuestion.getId());
    return statement;
}
```

For single-level relationships, Spring Data can infer routing from `JoinField`'s parent. If the entity declares its own routing property/SpEL, ensure the value is supplied wherever explicit routing is needed, especially for multi-level relationships.

### 8.1. Resolver for multi-level relationship trees

If multiple child types share a rule for resolving the root parent, you can centralize the logic in a resolver:

```java
public class StatementRoutingResolver implements RoutingResolver {

    @Override
    public String getRouting() {
        return null;
    }

    @Override
    public <T> String getRouting(T bean) {
        if (bean instanceof Statement statement) {
            return statement.getRouting();
        }
        return null;
    }
}
```

Then use it:

```java
ElasticsearchOperations statementOperations =
        operations.withRouting(new StatementRoutingResolver());

statementOperations.save(vote);
```

This resolver assumes the service has already set the right root `routing` on the entity. If a resolver had to query a repository to look up the root parent, weigh the cost and avoid creating loops between `save` operations and routing resolution.

## 9. Reading documents by ID when routing is used

When a document is saved with routing, the same routing value must be supplied for ID-based `get`/`delete` operations.

Example fetching vote `V-201` stored with routing `Q-100`:

```java
String voteId = "V-201";
String rootRouting = "Q-100";

Statement vote = operations
        .withRouting(RoutingResolver.just(rootRouting))
        .get(voteId, Statement.class);
```

If you call:

```java
Statement vote = operations.get("V-201", Statement.class);
```

without providing routing, the request may search the wrong shard and fail to find the document.

### 9.1. Reading parents and children

For `question` `Q-100`, routing is typically `Q-100`:

```java
Statement question = operations
        .withRouting(RoutingResolver.just("Q-100"))
        .get("Q-100", Statement.class);
```

For `answer` `A-101`, routing is still `Q-100`:

```java
Statement answer = operations
        .withRouting(RoutingResolver.just("Q-100"))
        .get("A-101", Statement.class);
```

For `vote` `V-201`, routing is also `Q-100`:

```java
Statement vote = operations
        .withRouting(RoutingResolver.just("Q-100"))
        .get("V-201", Statement.class);
```

Within a relationship tree, all documents under the same root share the same routing. Persisting the root routing or having a way to derive it from the ID is part of data modeling.

### 9.2. Deleting documents by ID

Deleting a child also requires routing:

```java
operations
        .withRouting(RoutingResolver.just("Q-100"))
        .delete("V-201");
```

When deleting by entity, Spring Data can read routing from the entity's metadata/property. When deleting by bare ID, there is no entity from which to derive routing, so `RoutingResolver.just(...)` or an appropriate resolver is required.

## 10. Updating parent-child documents

When updating an entity via `save`, preserve both the join relation and the routing value:

```java
Statement answer = operations
        .withRouting(RoutingResolver.just("Q-100"))
        .get("A-101", Statement.class);

answer.setText("Updated answer text");
answer.setRouting("Q-100");

repository.save(answer);
```

In a real application, if the repository shares the same mapping/routing configuration, you can also call `save` via an operations instance configured with the resolver:

```java
statementOperations.save(answer);
```

Guidelines when updating:

- Do not accidentally turn a child's `JoinField` into a parent or alter the parent ID.
- Do not drop root routing when converting an entity to a DTO and reconstructing it.
- Do not arbitrarily change routing values between updates.
- Treat changing a routing key as moving a document across shards, not a normal field update.

If using `UpdateQuery` or ID-based updates, pass routing into the corresponding request. Method/builder names can differ across Spring Data Elasticsearch versions; verify your project's API version and ensure update requests carry the same routing used during indexing.

### 10.1. Changing a routing value is not just editing a property

Routing determines which shard stores the document. If you change `routing` from `Q-100` to `Q-200`, merely overwriting the property in `_source` does not move the document from the old shard to the new shard.

Migration typically requires:

1. Read the document using the old routing.
2. Index the document into the same index with the new routing (and matching ID).
3. Confirm the new document was written successfully.
4. Delete the old copy using its ID and old routing.
5. Update any related references/checkpoints.

For parent-child, changing the root routing affects the entire relationship tree. All related documents must be migrated together while keeping join parent IDs consistent. Never change root routing without a full-tree migration plan.

## 11. Searching parent-child using `has_child` and `has_parent`

Spring Data Elasticsearch supports join mappings and persistence via `JoinField`. However, to query relationships, you must use native queries via `NativeQuery`/custom repositories; derived repository query methods do not automatically express full parent-child joins.

Two key queries:

- `has_child`: returns parent documents when a child document matches the query.
- `has_parent`: returns child documents when the parent document matches the query.

### 11.1. `has_child`

Example finding questions with at least one answer containing the word `sunny`:

```json
GET /statements/_search
{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "text": "sunny"
        }
      },
      "score_mode": "none"
    }
  }
}
```

The query runs against child type `answer`. If a matching answer exists, the corresponding parent document is returned.

### 11.2. `has_parent`

Example finding answers belonging to questions whose status is `OPEN`:

```json
GET /statements/_search
{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "term": {
          "status": "OPEN"
        }
      },
      "score": false
    }
  }
}
```

The query runs against parent type `question`. When the parent matches the condition, the corresponding child documents are returned.

### 11.3. Using the Java API Client DSL with `NativeQuery`

In Spring Data Elasticsearch 5.x+, you can build native queries using the Elasticsearch Java API Client:

```java
import co.elastic.clients.elasticsearch._types.ChildScoreMode;
import co.elastic.clients.elasticsearch._types.FieldValue;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Query hasSunnyAnswer = Query.of(q -> q
        .hasChild(hc -> hc
                .type("answer")
                .query(childQuery -> childQuery
                        .match(m -> m
                                .field("text")
                                .query("sunny")
                        )
                )
                .scoreMode(ChildScoreMode.None)
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(hasSunnyAnswer)
        .build();

SearchHits<Statement> hits = operations.search(query, Statement.class);
```

`ChildScoreMode.None` means child scores are not used to compute the parent's score. Other modes such as `Avg`, `Max`, `Min`, or `Sum` can be chosen depending on ranking goals and API client version.

### 11.4. Finding children by parent condition

Example:

```java
Query childrenOfOpenQuestions = Query.of(q -> q
        .hasParent(hp -> hp
                .parentType("question")
                .query(parentQuery -> parentQuery
                        .term(t -> t
                                .field("status")
                                .value(FieldValue.of("OPEN"))
                        )
                )
                .score(false)
        )
);

NativeQuery query = NativeQuery.builder()
        .withQuery(childrenOfOpenQuestions)
        .build();

SearchHits<Statement> answers = operations.search(query, Statement.class);
```

`has_parent` returns child documents. If you want to fetch children by an already-known parent ID, you can use `parent_id` instead of `has_parent`:

```json
GET /statements/_search
{
  "query": {
    "parent_id": {
      "type": "answer",
      "id": "Q-100"
    }
  }
}
```

`parent_id` is useful when the parent ID is known and you want children of a specific type.

## 12. Routing for parent-child searches

When searching across an entire index, Elasticsearch may fan queries out to multiple shards. If the routing value is known, you can restrict the request to the relevant shard using a routing parameter or a routing-configured operations instance.

Example finding answers belonging to question `Q-100`:

```java
ElasticsearchOperations questionOperations =
        operations.withRouting(RoutingResolver.just("Q-100"));

SearchHits<Statement> answers = questionOperations.search(
        query,
        Statement.class
);
```

Routing lets the query target only the shard holding that relationship tree, provided all documents in the tree were indexed with the same routing. If routed incorrectly, the query may miss documents even when the `has_child` or `has_parent` condition itself is valid.

If a query needs to find parents across the entire index without knowing routing beforehand, do not force an arbitrary routing value. Let it search the appropriate shards; correctness depends on proper mapping and accurate routing when children were indexed.

## 13. Retrieving matching child documents with `inner_hits`

`has_child` normally returns parent documents. If the UI also needs to show the child documents that caused a parent to match, configure `inner_hits` in the query.

Query DSL example:

```json
GET /statements/_search
{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "text": "sunny"
        }
      },
      "inner_hits": {
        "name": "matching_answers",
        "size": 5
      }
    }
  }
}
```

The response includes the parent hit and an `inner_hits.matching_answers` section containing the child answers matching the query. `inner_hits` is helpful when displaying relationships in a single response, though it enlarges responses and increases processing overhead. Cap the inner hit count and enable it only when needed.

## 14. Reading, writing, and deleting via Repository or `ElasticsearchOperations`?

Repositories suit basic CRUD when entities carry clear routing and methods do not need separate routing arguments. `ElasticsearchOperations` is helpful when you need explicit control over routing, native queries, or ID-only operations.

| Operation | Repository | `ElasticsearchOperations` |
|---|---|---|
| Save parent/child entity with routing metadata | `save(entity)` | `save(entity)` |
| Read by ID with fixed routing | ID-only repository methods may lack a route parameter. | `withRouting(RoutingResolver.just(route)).get(id, Type.class)` |
| Delete by entity | `delete(entity)` | `delete(entity)` |
| Delete by ID with routing | Not all repository methods accept routing. | `withRouting(...).delete(id)` |
| `has_child`/`has_parent` queries | Requires custom repository implementation. | `NativeQuery` + `search(...)` |
| Custom resolver | Usually configured via custom operations or service layer. | `withRouting(resolver)` |

For parent-child, place relationship handling in a service or custom repository to guarantee parent IDs, root routing, and join types stay consistent.

## 15. No ORM-style cascade delete/update

A `join` field only stores relationship metadata. Elasticsearch does not enforce foreign key constraints or JPA-style cascade deletes.

For example, deleting question `Q-100` does not automatically delete its answers and comments like an ORM cascade. The application must design a deletion workflow:

1. Determine the tree's root routing.
2. Locate or identify the related child documents.
3. Delete children using the right routing.
4. Delete the root parent.
5. Verify no orphaned documents remain per business rules.

For multi-level trees, delete in order or use `delete_by_query` with appropriate filters and accurate routing. If deletion can be retried, design it to be idempotent so re-running it does not corrupt state.

Similarly, updating a parent does not automatically update its children. If children duplicate some parent fields for fast searching, the application must update those copies itself or use a denormalization sync strategy.

## 16. Common pitfalls with routing and parent-child

| Symptom | Possible cause | Fix |
|---|---|---|
| Save succeeds, but `get(id)` returns `null`/404 | Document was indexed with routing, but `get` omitted the same routing. | Use `withRouting(RoutingResolver.just(value))` for ID-only `get`. |
| Child cannot find parent | Child was indexed with routing targeting a different shard from parent. | Ensure child uses root parent routing. |
| Single-level works, three-level fails | Default routing from `JoinField`'s direct parent is not the root routing. | Assign the root ancestor's routing to multi-level descendants. |
| `@Routing` fails to pick up value | Property name in annotation is wrong or property was left unset. | Check `@Routing("propertyName")` and entity value. |
| SpEL returns null routing | Bean name, method, or `#entity` expression is wrong. | Verify the registered bean and that the method returns `String`/`null`. |
| Custom resolver works for `save` but not ID-only `get` | Resolver only implements `getRouting(bean)`, and ID-only calls have no bean. | Implement `getRouting()` properly or use `RoutingResolver.just(value)`. |
| Join search returns no results | Wrong join type, parent ID, index, or routing. | Inspect mapping, `JoinField`, routing, and Query DSL. |
| `has_child` returns more parents than expected | Child query is too broad or join type is wrong. | Check child `type` and query conditions. |
| Parent deleted, but children still exist | Elasticsearch does not auto-cascade deletes. | Build an explicit full-tree deletion workflow. |
| Parent-child queries are slow | Join queries are expensive, many children, or poor shard distribution. | Limit join queries, optimize routing, or consider denormalization/nested. |
| One shard becomes hot | Routing key has low cardinality or one tenant/parent has huge volume. | Evaluate routing distribution and adjust shard/partition design. |
| Cannot change routing just by updating a field | Routing determines the shard, not just a field in `_source`. | Reindex the document with the new routing, then delete the old copy. |

## 17. Performance and limits of parent-child

Parent-child lets parents and children be stored independently, but join queries must coordinate data within shards and can be more expensive than ordinary queries.

Principles to follow:

- Use parent-child when children have independent update lifecycles or child counts are too large for nested documents.
- Keep relationships within the same index and same shard.
- Choose routing keys with balanced distribution to avoid hot shards.
- Avoid creating many join levels if storing the root ID directly in documents works.
- Limit `has_child`/`has_parent` queries and benchmark performance on realistic data.
- Use bounded `inner_hits` when fetching children; avoid loading unnecessary child data.
- Consider storing a few parent fields on children if queries need them frequently and sync costs are acceptable.
- If queries mainly read parents alongside small child lists, `nested` mapping or denormalization may be simpler.

Elasticsearch warns that `has_child` queries can be slow and degrade when matching children point to many different parents. Avoid using join queries by default on every listing screen.

### 17.1. Tenant-based routing can skew shards

If every document for a tenant uses `tenantId` as routing, all of that tenant's documents concentrate on a single shard. This can reduce fan-out for tenant queries, yet a large tenant can create a hot shard.

If one tenant has massive data volume, consider composite routing keys, partitioning by tenant and data type, or dedicated index strategies. No single routing key fits every workload; measure actual document distribution and query traffic.

### 17.2. Routing is not a security mechanism

Knowing a routing value does not mean a user is authorized to read that data. Routing only directs requests to a shard. The application must still enforce tenant/user authorization and configure Elasticsearch security appropriately.

## 18. Testing routing and join types

Test against a real Elasticsearch instance or Testcontainers with the `join` mapping created. Mock repositories cannot verify that documents land on the same shard or that join queries return the right parents/children.

An integration test scenario:

1. Create the `statements` index with `join` mapping.
2. Save question `Q-100`.
3. Save answer `A-101` with parent `Q-100`.
4. Save vote `V-201` with direct parent `A-101` but root routing `Q-100`.
5. Refresh the index.
6. Read each document by ID with routing `Q-100`.
7. Attempt reading a child without routing and confirm it is not found as expected for the index.
8. Run `has_child` to find the question with matching answers.
9. Run `has_parent` to find children belonging to matching questions.
10. Delete a child with routing and confirm the document is gone.
11. Delete the root and verify the separate child cleanup workflow.

Assertions should check:

- Parent/child `_id`.
- `relation` value and parent ID.
- Actual document routing.
- `get`/`delete` outcomes with proper routing.
- Join query results.
- Behavior when a parent or child is missing.

Do not use `Thread.sleep` to wait for documents to become searchable. In tests, explicitly refresh the index after indexing related documents.

## 19. Workflow for designing parent-child read/write operations

1. **Define the model:** choose parent/child types and identify the root parent.
2. **Declare mapping:** use `@JoinTypeRelations` and one `JoinField<ID>` property.
3. **Declare routing:** choose a property via `@Routing`, SpEL, or `RoutingResolver`.
4. **Create parents:** index root documents and determine their ID/routing.
5. **Create children:** use `new JoinField<>(childType, parentId)` and the root parent's routing.
6. **Create descendants:** for multiple levels, keep using the root ancestor's routing while `JoinField` holds the direct parent.
7. **Read by ID:** pass the proper routing via an operations resolver when no entity is present.
8. **Update/delete:** keep the original route and relation; if changing routes, migrate the entire tree.
9. **Query relationships:** use `has_child`, `has_parent`, or `parent_id` via `NativeQuery`/custom repositories.
10. **Test:** verify routing, join queries, cleanup, and performance against real Elasticsearch.

## 20. Key points to remember

- Routing decides the shard; `_id` identifies the document; parent ID describes the join relationship.
- When a document is saved with routing, ID-based `get`/`delete` needs the same routing value.
- `@Routing` is a class-level annotation specifying a property or SpEL expression used for routing.
- `RoutingResolver` provides `getRouting()` for entity-less operations, `getRouting(bean)` for entities, and `just(value)` for fixed routing.
- `operations.withRouting(resolver)` returns an `ElasticsearchOperations` instance with custom routing.
- Parent-child uses a `join` field and separate documents within the same index.
- `JoinField<ID>` holds the relation name and parent ID; its generic ID must match `@Id`'s type.
- `@JoinTypeRelations` declares allowed parent/child types.
- Parent and child must reside on the same shard; Spring Data infers parent routing for single-level relationships.
- For multi-level relationships, descendants must route to the root parent while `JoinField` holds the direct parent.
- `has_child` returns parents when children match; `has_parent` returns children when parents match; `parent_id` finds children by parent ID.
- Parent-child has no automatic cascade delete/update; the application must manage full-tree lifecycles.
- Join queries have overhead; consider `nested` or denormalization if better suited to your workload.
- Routing is not an authorization mechanism, and routing keys can cause hot shards if unevenly distributed.

`@Routing`, `RoutingResolver`, and `JoinField` work together to ensure parent-child documents are written to the right shard and read back using the same routing value. Keep routing distinct from parent ID, always preserve root routing for multi-level relationships, and build a service responsible for keeping save, read, update, delete, and relationship queries consistent.

## References

- [Spring Data Elasticsearch — Join-Type implementation](https://docs.spring.io/spring-data/elasticsearch/docs/5.1.7/reference/html/#elasticsearch.join-types)
- [Spring Data Elasticsearch — Routing values](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/routing.html)
- [Spring Data Elasticsearch — `RoutingResolver` API](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.x/api/org/springframework/data/elasticsearch/core/routing/RoutingResolver.html)
- [Spring Data Elasticsearch — `JoinField` API](https://docs.spring.io/spring-data/elasticsearch/docs/5.1.x/api/org/springframework/data/elasticsearch/core/join/JoinField.html)
- [Elasticsearch — Parent-join field](https://www.elastic.co/guide/en/elasticsearch/reference/current/parent-join.html)
- [Elasticsearch — `has_child` query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-has-child-query.html)
- [Elasticsearch — `has_parent` query](https://www.elastic.co/guide/en/elasticsearch/reference/current/query-dsl-has-parent-query.html)
