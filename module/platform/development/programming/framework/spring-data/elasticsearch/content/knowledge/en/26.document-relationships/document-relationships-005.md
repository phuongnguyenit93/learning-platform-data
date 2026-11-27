# Join Field for Parent-Child Modeling When Appropriate

Elasticsearch supports parent-child relationships between documents in the same index through the `join` field type. One parent document can be linked to many child documents; each child document belongs to one parent document. The relationship is stored in the `join` field, and Elasticsearch uses routing to ensure parents and children reside on the same shard.

A `join` field is useful when parent and child data need to be stored, updated, or queried independently. For example, a question with many answers; a product with continuously added reviews; or an article with many comments. When updating a child document, the application does not have to rewrite the entire parent document as is typically required with a `nested` array.

However, parent-child has higher query and operational costs than flat documents or `nested` in many cases. Use it only when there is a genuine need for independence between parent and child, and `has_child`/`has_parent` queries are a core part of the business logic. If the relationship is simple, child data is usually read together with the parent, and updates happen together, `nested` or denormalization is usually easier to operate.

## 1. Parent-child model in Elasticsearch

An index can declare a `join` field to define relationships between relation names. For example:

```text
question
   |
   +---- answer
   +---- answer
   +---- answer
```

Here:

- `question` is the parent relation name.
- `answer` is the child relation name.
- One `question` document can have many `answer` documents.
- Each `answer` document has only one parent.
- Parent and child documents are separate documents within the same index.

A `join` field does not create a relational table like in a relational database. It stores relationship metadata inside documents and provides specialized queries to find parents by children or children by parents.

### Example data

A question and its answers can be represented as follows:

```json
{
  "_id": "q-100",
  "title": "What is Spring Data Elasticsearch?",
  "relation": "question"
}
```

```json
{
  "_id": "a-201",
  "text": "This is the module integrating Spring Data with Elasticsearch.",
  "relation": {
    "name": "answer",
    "parent": "q-100"
  }
}
```

```json
{
  "_id": "a-202",
  "text": "It provides repositories and ElasticsearchOperations.",
  "relation": {
    "name": "answer",
    "parent": "q-100"
  }
}
```

The parent document stores the relation as the parent name. The child document stores both the child relation name and the parent's ID.

## 2. When should you choose a Join field?

Parent-child fits when the following conditions hold for your data model:

- Child documents have their own lifecycle and are frequently added, updated, or deleted independently.
- A parent can have a large or growing number of children over time.
- You want to avoid rewriting the entire parent document on every child change.
- The application needs to query parents based on child conditions (`has_child`).
- The application needs to query children based on parent conditions (`has_parent`).
- Parent and child data can be routed to the same shard.

Examples:

| Model | Why parent-child might be considered |
|---|---|
| Question – answer | Answers are added and moderated independently; need to find questions with accepted answers |
| Product – review | Reviews are continuously added; need to find products with qualifying reviews |
| Article – comment | Comments have their own lifecycle and can become very numerous |
| Account – activity event | Events are written independently; need to find accounts by event type |

Do not choose a `join` field simply because data has a parent-child relationship in the business domain. Relationships in a business model do not necessarily have to be modeled using Elasticsearch's `join` field.

## 3. Comparing Join field with Nested and Denormalization

These three common approaches to representing related data have different trade-offs.

| Criterion | Join field (parent-child) | Nested | Denormalization |
|---|---|---|---|
| Storage | Parent and child are separate documents | Child objects live inside the parent document | Copy needed fields into documents |
| Updating children | Can update independently | Usually requires updating parent document containing nested objects | Update related copies if consistency is required |
| Relationship queries | `has_child`, `has_parent`, `parent_id` | `nested` query | Direct queries on copied fields |
| One parent with many children | Yes | Yes | Can be represented depending on design |
| Query cost | Join queries are more expensive than regular queries | Has nested overhead, usually suitable for single-document queries | Usually lowest when querying directly |
| Routing | Parent and child must share the same shard | No relationship routing needed | No relationship routing needed |
| Best suited for | Independent children needing relational joins | Children read with parent needing per-object field correlation | Prioritizing read speed, accepting data duplication |

### Choose Nested when

- The number of child objects is moderate.
- Child objects are usually read together with the parent document.
- You need to guarantee conditions match on the same child object.
- Updating the parent document together with its child objects is acceptable.

### Choose Denormalization when

- Queries need high speed and simplicity.
- Only a few parent/child attributes need to be copied for filtering or display.
- Updates and synchronization of duplicated data can be managed.

### Choose Join field when

- Children have independent lifecycles and update frequencies.
- The number of children can be large.
- You need to find parents by children or vice versa.
- The development team accepts join query costs and routing rules.

## 4. Declaring a Join field mapping in Elasticsearch

A `join` field is declared in the index mapping:

```http
PUT /qa-index
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "title": {
        "type": "text"
      },
      "text": {
        "type": "text"
      },
      "relation": {
        "type": "join",
        "relations": {
          "question": "answer"
        }
      }
    }
  }
}
```

The field name `relation` is the name of the join field. In the `relations` map, the key `question` is the parent relation and the value `answer` is the child relation.

You can declare multiple relationships in the same `join` field:

```json
{
  "properties": {
    "relation": {
      "type": "join",
      "relations": {
        "question": ["answer", "comment"],
        "article": "comment"
      }
    }
  }
}
```

In this example, `question` can be the parent of `answer` and `comment`; `article` can also be the parent of `comment`. Relation names are labels in the mapping, not index names or Java class names.

An index can have only one `join` field mapping. If multiple relationship types are needed, model all relations within that single `join` field or consider separate indexes if the relationship structures are independent.

## 5. Declaring a Join field in Spring Data Elasticsearch

Spring Data Elasticsearch supports join mappings via `FieldType.Join`, `@JoinTypeRelations`, `@JoinTypeRelation`, and the `JoinField<T>` type.

Example of a shared document class for both parent and child:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.annotations.Routing;
import org.springframework.data.elasticsearch.core.mapping.JoinField;

@Document(indexName = "qa-index")
public class QaDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String text;

    @Field(type = FieldType.Join)
    @JoinTypeRelations(
        relations = {
            @JoinTypeRelation(parent = "question", children = {"answer"})
        }
    )
    private JoinField<String> relation;

    @Routing
    private String routing;

    // Constructors, getters and setters
}
```

`JoinField<String>` holds the relation name and the parent ID for child documents. For parent documents, no parent ID is required. `@JoinTypeRelations` defines the relationships Spring Data uses when generating the mapping. `@Routing` marks the Java property used as the routing value for index/search operations as supported by Spring Data.

Some Spring Data versions have minor differences in packages or mapping APIs. Use the annotations and `JoinField` class from your project's exact dependency version.

## 6. Creating a parent document

A parent document has a relation name matching the parent name declared in the mapping:

```java
QaDocument question = new QaDocument();
question.setId("q-100");
question.setTitle("What is Spring Data Elasticsearch?");
question.setText("A question about integrating Spring Data with Elasticsearch.");
question.setRelation(new JoinField<>("question", null));
question.setRouting("q-100");
```

For a parent, routing is typically set to the parent's own ID. Elasticsearch defaults to using `_id` as routing when none is specified, but setting it explicitly makes the model clearer and ensures children use the exact same value.

Saving the document:

```java
QaDocument savedQuestion = operations.save(question);
```

Or using a repository extending `ElasticsearchRepository<QaDocument, String>`:

```java
qaRepository.save(question);
```

Parent and child must reside in the same index. A `join` field does not link documents across two different indexes.

## 7. Creating child documents and routing

A child document declares relation name `answer` and parent ID `q-100`:

```java
QaDocument answer = new QaDocument();
answer.setId("a-201");
answer.setTitle("First answer");
answer.setText("Spring Data provides repository and template APIs.");
answer.setRelation(new JoinField<>("answer", "q-100"));
answer.setRouting("q-100");

operations.save(answer);
```

Two critical pieces of information:

- `new JoinField<>("answer", "q-100")` declares the child relation and the parent's ID.
- `routing = "q-100"` tells Elasticsearch to place the child on the same shard as the parent.

**Routing is mandatory when indexing children.** If a child is sent to a different shard than its parent, Elasticsearch cannot resolve the parent-child relationship properly and may return an error that the parent does not exist on that shard.

Index the parent before indexing its children. When indexing in batches, ensure parents already exist before their corresponding children and that every child uses the parent ID as its routing value.

### Creating multiple children

```java
List<QaDocument> answers = List.of(
    createAnswer("a-201", "q-100", "Answer A"),
    createAnswer("a-202", "q-100", "Answer B"),
    createAnswer("a-203", "q-100", "Answer C")
);

qaRepository.saveAll(answers);
```

`createAnswer` must always set both the `JoinField` parent ID and the routing value. Never set only the relation and omit routing.

## 8. Reading parent and child documents

You can read a parent by ID like a normal document, using the proper index and routing if the request requires explicit routing:

```http
GET /qa-index/_doc/q-100?routing=q-100
```

Reading a child:

```http
GET /qa-index/_doc/a-201?routing=q-100
```

Because the child is routed by the parent ID, getting a child requires the corresponding routing. Without knowing the routing, a get-by-ID request may fail to find the document because it queries only the shard computed from default routing.

In Spring Data, you can configure routing on the entity using `@Routing` or use operation APIs that support routing. When reading a child document, set the routing value to the parent ID.

## 9. Finding parents by child conditions: `has_child`

The `has_child` query returns parent documents that have at least one child document matching the inner query.

For example, finding questions that have at least one answer containing the term `repository`:

```http
POST /qa-index/_search
Content-Type: application/json

{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "text": "repository"
        }
      },
      "score_mode": "none"
    }
  }
}
```

`type` is the child relation name declared in the mapping, not the Java class name. `query` is the condition applied to children. Results are parent documents.

### `score_mode`

`has_child` can combine matching child scores into the parent's score. Common modes include:

| Value | Meaning |
|---|---|
| `none` | Do not use child scores to compute parent score |
| `avg` | Average score of matching children |
| `max` | Highest score |
| `min` | Lowest score |
| `sum` | Sum of scores of matching children |

If you only need to filter parents with qualifying children, `none` is usually sufficient. If answer relevance affects question ranking, choose an appropriate mode and evaluate scores.

## 10. Finding children by parent conditions: `has_parent`

The `has_parent` query returns child documents whose parent matches the condition.

For example, finding answers belonging to questions whose title contains `Spring Data`:

```http
POST /qa-index/_search
Content-Type: application/json

{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "match": {
          "title": "Spring Data"
        }
      },
      "score": false
    }
  }
}
```

`parent_type` is the parent relation name. `score: false` means the parent's score is not propagated to the child's score. If children should be ranked by their parent's relevance, enable scoring and verify the results.

## 11. Fetching children for a specific parent: `parent_id`

If you already know the parent ID and want to retrieve children belonging to that parent, use the `parent_id` query:

```http
POST /qa-index/_search?routing=q-100
Content-Type: application/json

{
  "query": {
    "parent_id": {
      "type": "answer",
      "id": "q-100"
    }
  }
}
```

The query returns documents of child relation `answer` whose parent ID is `q-100`. The `routing` parameter restricts the request to the shard holding the parent and children, avoiding searching unrelated shards when the parent ID is known.

`parent_id` is more appropriate than `has_child` when you only need the children of a specific parent. `has_child` fits when searching for parents based on complex child criteria.

## 12. Using Join queries in Spring Data `NativeQuery`

Spring Data Elasticsearch can build join queries using `NativeQuery` and the Elasticsearch Java API Client.

Example `has_child`:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.hasChild(h -> h
        .type("answer")
        .query(childQuery -> childQuery.match(m -> m
            .field("text")
            .query("repository")
        ))
        .scoreMode(co.elastic.clients.elasticsearch._types.query_dsl.ChildScoreMode.None)
    ))
    .build();
```

Example `has_parent`:

```java
Query query = NativeQuery.builder()
    .withQuery(q -> q.hasParent(h -> h
        .parentType("question")
        .query(parentQuery -> parentQuery.match(m -> m
            .field("title")
            .query("Spring Data")
        ))
        .score(false)
    ))
    .build();
```

Enum and builder names can differ slightly across Elasticsearch Java API Client versions. Both examples show how the query is expressed; use the exact packages and enum types managed by your project's Spring Data version. You can validate logic directly with REST Query DSL before translating to Java builders.

To execute the query, use `ElasticsearchOperations.search(...)` or a corresponding custom repository method. When routing is known, pass routing via API/query metadata or `@Routing` to target the shard.

## 13. Routing and the same-shard rule

Parent-child only works when parent and child reside on the same shard. Elasticsearch does not perform joins across different shards.

Common rule:

```text
Parent ID: q-100
Parent routing: q-100
Child ID: a-201
Child routing: q-100
Child relation parent: q-100
```

The child's routing value must be the parent's ID. This guarantees both documents hash to the same shard.

### What happens if routing is omitted?

If a child is indexed without proper routing, Elasticsearch may compute the shard from the child's `_id`, sending the child to a different shard from the parent. The relationship then becomes invalid and operations may return errors. For parents, default ID-based routing usually matches the parent ID, but setting routing explicitly on both parent and child keeps code consistent.

### Routing in Spring Data

`@Routing` marks the property holding the routing value. For children, set this property to the parent ID. For parents, typically set it to the parent's own ID.

If a single repository handles both parents and children, do not assume a single static default routing for all entities. Ensure every document is constructed with the right routing value before calling `save`/`saveAll`.

## 14. Multi-level relationships for a parent

A `join` field supports defining multi-level relationships, for example:

```text
company
   |
   +---- department
             |
             +---- employee
```

Illustrative mapping:

```json
{
  "properties": {
    "relation": {
      "type": "join",
      "relations": {
        "company": "department",
        "department": "employee"
      }
    }
  }
}
```

When indexing an `employee`, routing must still use the root parent's ID (`company`) according to multi-level routing rules, not just the immediate `department` ID. This is very easy to misconfigure when there are multiple tiers.

Although Elasticsearch supports multiple levels, avoid building deep relationship trees if simpler modeling is possible. Every join level makes queries more complex and expensive. Parent-child should usually stay at a single parent-child level.

## 15. Updating and deleting child documents

One benefit of parent-child is that children can be updated independently:

```http
PUT /qa-index/_doc/a-201?routing=q-100
Content-Type: application/json

{
  "title": "Edited answer",
  "text": "New answer content.",
  "relation": {
    "name": "answer",
    "parent": "q-100"
  }
}
```

The parent document does not need to be rewritten when only child content changes. When updating, you must still send the right routing and retain the proper relation.

Deleting a child:

```http
DELETE /qa-index/_doc/a-201?routing=q-100
```

When deleting a parent, do not assume Elasticsearch automatically cascade-deletes all children. If business rules require deleting the entire tree, the application must explicitly find/delete children using routing or an appropriate `delete_by_query`, then delete the parent. Design deletion order and retries carefully to avoid leaving orphaned child documents.

### Changing a child's parent

A child belongs to one parent. If moving a child to a different parent, update both the join relation and the routing to the new parent. Because routing determines the shard, this change may require reindexing the document with the new routing rather than just updating the `relation` field.

## 16. Bulk indexing parents and children

For large data loads, you can use the Bulk API to index parents and children. However, you must ensure parents exist before children are indexed and each child carries the right routing.

Logical ordering example:

```text
1. Index question q-100, routing q-100
2. Index answer a-201, routing q-100, parent q-100
3. Index answer a-202, routing q-100, parent q-100
```

The Bulk API is not an atomic transaction. If a parent action fails while child actions are still sent, children can fail because the parent is missing on the shard. Inspect per-item results and mark a batch successful only when all required relationships have been created properly.

With many parents, you can partition batches by parent to preserve ordering and routing. If a pipeline runs in parallel, children of the same parent must still use the same routing value.

## 17. Performance and operational costs

Parent-child queries are generally more expensive than direct field queries. `join` fields use global ordinals to map relationships between parents and children; building or updating global ordinals can impact refresh time and memory usage.

Points to consider:

- `has_child` can be expensive, especially with many children or queries matching many children.
- `has_parent` also incurs join overhead and should be evaluated on realistic data.
- A parent with a huge number of children can create shard skew when routing by parent ID.
- Documents sharing a parent are concentrated on one shard, so one massive parent can unbalance shards.
- Refreshes can trigger rebuilding/updating global ordinals, affecting latency.
- Deeper join trees make queries increasingly complex.
- Do not run many heavy join queries concurrently without measuring resource impact.

### Global ordinals

`join` fields commonly use global ordinals to execute join queries more efficiently. You can configure `eager_global_ordinals` on a `join` field if you want ordinals built during refresh instead of waiting for the first query. This can reduce latency on the first query after a refresh at the cost of slower refreshes and higher memory usage.

Example mapping:

```json
{
  "properties": {
    "relation": {
      "type": "join",
      "eager_global_ordinals": true,
      "relations": {
        "question": "answer"
      }
    }
  }
}
```

Do not enable eager global ordinals out of habit. Measure post-refresh latency, refresh frequency, and heap memory to decide.

## 18. Routing can cause shard imbalance

Because all children of a parent must live on the same shard, a parent with millions of children can make its shard significantly heavier than other shards. This is a structural trade-off of parent-child.

Before choosing a `join` field, estimate:

- Number of parents.
- Average and maximum number of children per parent.
- Child indexing/update frequency.
- Number of index shards.
- Document sizes and data growth rate.

If a single parent can have an extreme number of children, you may need to partition data across indexes or use a more suitable denormalized model. You cannot spread children of the same parent across multiple shards while keeping standard join-field relationships.

## 19. A Join field is not a cross-index relationship

A `join` field only defines parent-child relationships between documents within the same index. It does not join across:

- Two different Elasticsearch indexes.
- Elasticsearch and a relational database.
- Two Elasticsearch clusters.

If parent and child live in different indexes, use application-side joins, denormalization, enrichment, or another pipeline. You cannot declare a `join` field in one index to reference a parent in another index.

## 20. Integration in a Spring service

A service should be responsible for consistently constructing relations and routing. For example:

```java
import org.springframework.data.elasticsearch.core.ElasticsearchOperations;
import org.springframework.stereotype.Service;

@Service
public class QaService {

    private final ElasticsearchOperations operations;

    public QaService(ElasticsearchOperations operations) {
        this.operations = operations;
    }

    public void createQuestion(String id, String title, String text) {
        QaDocument question = new QaDocument();
        question.setId(id);
        question.setTitle(title);
        question.setText(text);
        question.setRelation(new JoinField<>("question", null));
        question.setRouting(id);

        operations.save(question);
    }

    public void addAnswer(String answerId, String questionId, String text) {
        QaDocument answer = new QaDocument();
        answer.setId(answerId);
        answer.setText(text);
        answer.setRelation(new JoinField<>("answer", questionId));
        answer.setRouting(questionId);

        operations.save(answer);
    }
}
```

This service centralizes two rules: parents use relation `question`, children use relation `answer` with the parent ID, and routing for both is based on the parent ID. In a real system, verify the parent exists before adding an answer and handle indexing failures.

## 21. Verifying mappings and data

Check mapping:

```http
GET /qa-index/_mapping
```

Check parent document:

```http
GET /qa-index/_doc/q-100?routing=q-100
```

Check child:

```http
GET /qa-index/_doc/a-201?routing=q-100
```

Test parent/child query:

```http
POST /qa-index/_search
Content-Type: application/json

{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "term": {
          "status": "ACCEPTED"
        }
      }
    }
  }
}
```

When a query returns no results, check in order:

1. Does the mapping have a `join` field with the right relation names?
2. Does the parent document already exist?
3. Does the child have the right relation name and parent ID?
4. Was the child indexed with routing equal to the parent ID?
5. Does the query use the right relation name in `type`/`parent_type`?
6. Does the queried field have an appropriate mapping and expected values in documents?
7. Has the index been refreshed so search can see the data?

## 22. Testing parent-child

Integration tests should run against a compatible Elasticsearch instance with a real `join` mapping created. Mock repositories do not test routing or server-side join behavior.

Scenarios to test:

- Creating a parent and reading it back with routing.
- Creating a child with the proper parent ID and routing.
- Creating a child with wrong routing to verify the failure is caught.
- `has_child` returns the right parent when a child matches.
- `has_parent` returns the right children when the parent matches.
- `parent_id` returns the exact children of a given parent.
- Updating a child does not alter the parent's `_source`.
- Deleting a child uses the right routing.
- Parent deletion workflow handles children according to business rules.
- Bulk indexing handles per-item errors and parent/child ordering.
- Parents with widely varying child counts to observe shard distribution.

For example, REST-level `has_child` logic can be translated into `NativeQuery` and verified by checking returned parent IDs. Use fixtures with at least two parents, each having children in different states, to confirm the query does not return the wrong parent.

## 23. Common mistakes

### Forgetting routing when indexing children

Children can be routed to a different shard from the parent. Always set routing to the parent ID and inspect actual requests.

### Using class names instead of relation names

`type` in `has_child` / `parent_type` in `has_parent` is the relation name in the join mapping—such as `answer` or `question`—not necessarily `AnswerDocument` or `Question`.

### Setting the wrong parent ID in JoinField

Children must hold the parent's exact ID. Routing and `JoinField.parent` must reference the same parent.

### Indexing children before the parent

The parent should exist on the target shard when creating children. Index the parent first, then index children.

### Mapping is not `join`

A `keyword` field holding the string `"question"` does not replace a `join` field mapping. You must declare `type: join` and `relations`.

### Trying to join across two indexes

`join` fields do not support cross-index relationships. Use application-side joins or denormalization.

### Treating a Join field like Nested

Nested objects live inside the parent document; parent-child uses independent documents in the same index. Querying, updating, and routing differ.

### Not controlling child count per parent

Routing funnels all children of a parent onto one shard. An overly large parent can cause skew and limit distribution.

### Assuming deleting a parent auto-cascades

The application must implement an explicit child deletion workflow if business rules require deleting the entire tree.

## 24. Decision and implementation workflow

Before using a `join` field, follow these steps:

1. Determine whether parent and child genuinely have independent lifecycles.
2. Compare against `nested` and denormalization based on read/write workloads.
3. Estimate children per parent and the risk of shard skew.
4. Design relation names and the `join` field mapping in the same index.
5. Create the entity with `JoinField` and a routing property.
6. Index parents with stable routing, then index children with `JoinField.parent` and routing equal to the parent ID.
7. Use `has_child`, `has_parent`, or `parent_id` according to query direction.
8. Manage updates, deletes, bulk operations, and retries.
9. Monitor join query latency, global ordinals, heap, and shard distribution.
10. Test correct/incorrect routing and independent parent-child operations.

## 25. Conclusion

A `join` field enables representing parent-child relationships between separate documents in the same Elasticsearch index. The mapping defines relation names; parent documents store the parent relation name; child documents store the child relation name along with the parent ID. Parent and child must reside on the same shard, so a child's routing must equal the parent's ID.

In Spring Data Elasticsearch, you can declare this using `FieldType.Join`, `@JoinTypeRelations`, and `JoinField<T>`, while using `@Routing` to store the routing value. `has_child` finds parents by child conditions, `has_parent` finds children by parent conditions, and `parent_id` fetches children of a specific parent. Parent-child fits when children need independent updates and the application genuinely needs relational queries; if data is typically read together, `nested` or denormalization is usually simpler and more efficient. Account for join query costs, global ordinals, routing, shard skew, and deletion/sync workflows before selecting this model.

## References

- [Elasticsearch – Parent-join field](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/parent-join)
- [Elasticsearch – Has child query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-has-child-query)
- [Elasticsearch – Has parent query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-has-parent-query)
- [Elasticsearch – Parent ID query](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-dsl-parent-id-query)
- [Spring Data Elasticsearch – Object mapping](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/object-mapping.html)
- [Spring Data Elasticsearch – `JoinField` API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/mapping/JoinField.html)
