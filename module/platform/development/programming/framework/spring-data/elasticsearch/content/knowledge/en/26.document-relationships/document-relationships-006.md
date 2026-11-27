# @JoinTypeRelations, JoinField, and Mapping

Spring Data Elasticsearch supports Elasticsearch parent-child relationships via a `join` field. The two primary Java-side building blocks are:

- **@JoinTypeRelations**: declares the relationship schema—which document types are parents and which document types are their children.
- **JoinField<ID>**: represents a specific document's role in the relationship—the document's relation name and its parent's ID if the document is a child.

This pair of annotations and types helps Spring Data generate a `join`-typed mapping and convert relationship values when reading/writing documents. It does not create ORM-style object associations like JPA. Parents and children remain independent documents in the same index; Elasticsearch maintains the link via the `join` field and routing.

## 1. Parent-child in Elasticsearch

Suppose a forum has questions and answers. A single question can have many answers:

~~~text
Question Q-100
    ├── Answer A-101
    ├── Answer A-102
    └── Answer A-103
~~~

Each item can be stored as a separate document in the same index:

| Document ID | Relation name | Parent ID |
| --- | --- | --- |
| Q-100 | question | None |
| A-101 | answer | Q-100 |
| A-102 | answer | Q-100 |
| A-103 | answer | Q-100 |

The parent document carries the parent relation name. Child documents carry the child relation name along with the parent's ID.

A `join` field is a special Elasticsearch mapping used to describe document types and relationships between them. It enables queries such as `has_child`, `has_parent`, and `parent_id` to find documents by relationship.

Parent-child is not like foreign keys or JOINs in a relational database:

- Documents are still indexed and updated independently.
- Relationships exist only within the scope of a single index.
- Parent and child must reside on the same shard.
- Elasticsearch does not automatically load an entire object graph like an ORM.
- Every join query incurs extra processing overhead compared to querying denormalized documents.

Therefore, choose `join` only when parents and children must be updated independently and a parent can have a large number of children. If data changes infrequently and parent info can be copied into children, denormalization is usually simpler and faster.

## 2. @JoinTypeRelations declares the relationship schema

Spring Data Elasticsearch uses `@JoinTypeRelations` on a `JoinField` property to declare parent-child pairs.

For example, a question can have answers and comments:

~~~java
@JoinTypeRelations(
    relations = {
        @JoinTypeRelation(
            parent = "question",
            children = {"answer", "comment"}
        )
    }
)
private JoinField<String> relation;
~~~

Where:

- `parent = "question"`: relation name of the parent document.
- `children = {"answer", "comment"}`: relations allowed to be direct children of `question`.
- `relation`: Java property name holding the join value for each document.

You can declare multiple relationships in the same annotation. For example, an answer can have votes:

~~~java
@JoinTypeRelations(
    relations = {
        @JoinTypeRelation(
            parent = "question",
            children = {"answer", "comment"}
        ),
        @JoinTypeRelation(
            parent = "answer",
            children = "vote"
        )
    }
)
private JoinField<String> relation;
~~~

Relationship diagram:

~~~text
question
   ├── answer
   │      └── vote
   └── comment
~~~

Relation names are logical names in the Elasticsearch mapping and do not have to match Java class names. In this example, multiple document kinds can be represented by the same Java entity and distinguished by the `relation` value.

### 2.1. Declaration rules

A single `@JoinTypeRelations` annotation can contain multiple `@JoinTypeRelation` entries. Each `@JoinTypeRelation` defines one parent and one or more child types.

| Attribute | Meaning |
| --- | --- |
| `parent` | Relation name of the parent document. |
| `children` | One or more relation names allowed as direct children of the parent. |
| `relations` | Array of `@JoinTypeRelation` definitions placed inside `@JoinTypeRelations`. |

A child has only one parent in the join model. A parent can have many child documents and multiple distinct child types.

Relation names in the annotation must match the names passed into `JoinField` when creating documents. If the mapping declares child `answer` but code creates `JoinField` with name `response`, Elasticsearch cannot treat `response` as a declared child type.

## 3. JoinField represents each document's relationship

`JoinField` is a Spring Data Elasticsearch type:

~~~java
org.springframework.data.elasticsearch.core.join.JoinField<ID>
~~~

The generic `ID` parameter must match the type of the entity's `@Id` property.

For example, if the entity uses:

~~~java
@Id
private String id;
~~~

then the relationship property should be:

~~~java
private JoinField<String> relation;
~~~

If the ID is `Long`, use `JoinField<Long>`. Do not declare `JoinField<Object>` or use a different ID type from the entity ID because Spring Data needs to convert the parent ID using the matching type.

Common `JoinField` constructors:

~~~java
new JoinField<>("question")
new JoinField<>("answer", parentId)
~~~

The constructor taking only the relation name is used for parent documents. The constructor taking both relation name and parent ID is used for child documents.

| Java value | Meaning | Join data in `_source` |
| --- | --- | --- |
| `new JoinField<>("question")` | Document is a `question` parent. | `"question"` or corresponding relation object. |
| `new JoinField<>("answer", "Q-100")` | Document is an `answer` child of `Q-100`. | `{"name":"answer","parent":"Q-100"}` |
| `new JoinField<>("comment", "Q-100")` | Document is a `comment` child of `Q-100`. | `{"name":"comment","parent":"Q-100"}` |

`JoinField` does not hold a list of child IDs. When creating a parent, only the relation name is needed. Each child holds its own parent ID.

## 4. Declaring a Spring Data Elasticsearch entity

Example index `statements` containing questions, answers, and comments, all sharing a single entity class:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.core.join.JoinField;

@Document(indexName = "statements")
public class Statement {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String text;

    @JoinTypeRelations(
        relations = {
            @JoinTypeRelation(
                parent = "question",
                children = {"answer", "comment"}
            )
        }
    )
    private JoinField<String> relation;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getText() {
        return text;
    }

    public void setText(String text) {
        this.text = text;
    }

    public JoinField<String> getRelation() {
        return relation;
    }

    public void setRelation(JoinField<String> relation) {
        this.relation = relation;
    }
}
~~~

Points to note:

- `@Document` specifies the index containing the documents.
- `@Id` specifies each document's ID.
- `@JoinTypeRelations` sits on the `JoinField` property.
- `JoinField` generic `String` matches the `String` ID type.
- You do not need a Java property like `List<Answer>` to declare the relationship. Join mapping is defined by the annotation.

Do not place `@JoinTypeRelations` on the class or on an ordinary text field. This annotation describes the mapping for the `JoinField` property.

## 5. Generated Elasticsearch mapping

From the entity above, Spring Data Elasticsearch generates the corresponding `join` mapping. The key part looks like:

~~~json
{
  "mappings": {
    "properties": {
      "text": {
        "type": "text"
      },
      "relation": {
        "type": "join",
        "eager_global_ordinals": true,
        "relations": {
          "question": ["answer", "comment"]
        }
      }
    }
  }
}
~~~

The field name `relation` in the mapping comes from the Java property name unless customized with appropriate mapping configuration. In this example, the `relation` property becomes a field of type `join`. The property annotated with `@Id` serves as the document's ID metadata (Elasticsearch `_id`), not a regular field under `properties` in the mapping.

Key takeaways:

- `type: join` marks the relationship field.
- `relations` defines parent-child types.
- `eager_global_ordinals` is typically enabled in join mappings generated by Spring Data.
- The `join` field is a single mapping field for the index's relationship schema.

If creating the mapping manually via JSON, the `relations` structure must match the annotation and relation names used in `JoinField`. Avoid letting the JSON mapping and annotation describe two different schemas.

### 5.1. One join field mapping per index

Elasticsearch allows only one `join` field mapping per index. That `join` field can define multiple relationships, but you cannot create multiple independent `join` fields to model unrelated relationship trees in the same index.

If an index requires multiple relationship types, design them within the same `relations` map or consider splitting indexes / denormalizing data.

### 5.2. Extending the relationship schema

You can declare multiple child types for the same parent:

~~~java
@JoinTypeRelations(
    relations = {
        @JoinTypeRelation(
            parent = "product",
            children = {"offer", "review", "question"}
        )
    }
)
private JoinField<String> relation;
~~~

Diagram:

~~~text
product
  ├── offer
  ├── review
  └── question
~~~

If you need to add a new relationship to an existing `join` field, Elasticsearch supports adding relations. However, ensure code, mappings, and data are updated in sync; check the mapping API and your cluster version before deploying changes.

## 6. Creating and saving parent documents

A parent document is created with its relation name and no parent ID:

~~~java
Statement question = new Statement();
question.setText("How is the weather?");
question.setRelation(new JoinField<>("question"));

Statement savedQuestion = repository.save(question);
~~~

Spring Data serializes `JoinField` into the join value in the document. For a parent, Elasticsearch allows the shorthand representation using just the relation name:

~~~json
{
  "text": "How is the weather?",
  "relation": "question"
}
~~~

You can set the ID yourself before calling `save` if the application requires stable IDs. If the ID is generated by Elasticsearch/Spring Data or assigned during save, use the actual saved parent's ID when creating children.

## 7. Creating and saving child documents

A child needs two pieces of information:

1. The child's relation name declared in `@JoinTypeRelations`.
2. The parent document's ID.

Example creating an answer for the question just saved:

~~~java
Statement answer = new Statement();
answer.setText("Sunny");
answer.setRelation(
    new JoinField<>("answer", savedQuestion.getId())
);

Statement savedAnswer = repository.save(answer);
~~~

The child document is represented in `_source` as:

~~~json
{
  "text": "Sunny",
  "relation": {
    "name": "answer",
    "parent": "question-id"
  }
}
~~~

where `question-id` is the actual ID of `savedQuestion`.

One parent can have multiple children:

~~~java
Statement firstAnswer = new Statement();
firstAnswer.setText("Sunny");
firstAnswer.setRelation(
    new JoinField<>("answer", savedQuestion.getId())
);
repository.save(firstAnswer);

Statement secondAnswer = new Statement();
secondAnswer.setText("Rainy");
secondAnswer.setRelation(
    new JoinField<>("answer", savedQuestion.getId())
);
repository.save(secondAnswer);
~~~

Each child is an independent document. Saving a child does not automatically add it to a collection inside the parent entity.

## 8. Routing: parent and child must share the same shard

This is a mandatory rule of Elasticsearch parent-child: parent and child must reside on the same shard. Elasticsearch uses the routing value to determine a document's shard.

If a parent is indexed with ID `Q-100`, its children must use routing value `Q-100`. Otherwise, Elasticsearch may store the parent and child on two different shards and the relationship will not work properly.

For single-level relationships, Spring Data Elasticsearch automatically uses the `parent` value in `JoinField` as routing when saving a child.

For example:

~~~java
Statement answer = new Statement();
answer.setText("Sunny");
answer.setRelation(new JoinField<>("answer", questionId));

repository.save(answer);
~~~

In this case, the parent ID is used as the routing value for the child.

### 8.1. Routing with multiple levels

Suppose the schema has three tiers:

~~~text
question Q-100
    └── answer A-101
            └── vote V-201
~~~

The `vote`'s `JoinField` must hold its direct parent's ID, which is `answer` `A-101`:

~~~java
new JoinField<>("vote", answerId)
~~~

However, the `vote`'s routing must be the ID of the top-level ancestor—`question` `Q-100`—so that question, answer, and vote all live on the same shard.

Do not use `answerId` as the `vote`'s routing in a multi-level example. The parent ID in `JoinField` and the routing value can differ:

| Value | Vote |
| --- | --- |
| `JoinField` name | `vote` |
| `JoinField` parent | `A-101` |
| Routing | `Q-100` |

Spring Data automatically picks up `JoinField`'s `parent` property as the right routing for single-level relationships. For multi-level trees, you must declare custom routing to use the root ancestor's ID.

### 8.2. Declaring @Routing

Spring Data Elasticsearch supports `@Routing` on the entity to specify the property holding the routing value:

~~~java
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

    @JoinTypeRelations(
        relations = {
            @JoinTypeRelation(parent = "question", children = {"answer", "comment"}),
            @JoinTypeRelation(parent = "answer", children = "vote")
        }
    )
    private JoinField<String> relation;

    // getters and setters
}
~~~

When `@Routing` takes a property name string like `"routing"`, Spring Data reads the value from the `routing` property to send as the request's routing.

Multi-level data can be created as follows:

~~~java
Statement question = new Statement();
question.setText("How is the weather?");
question.setRelation(new JoinField<>("question"));
question.setRouting(null);

Statement savedQuestion = repository.save(question);

Statement answer = new Statement();
answer.setText("Sunny");
answer.setRelation(new JoinField<>("answer", savedQuestion.getId()));
answer.setRouting(savedQuestion.getId());

Statement savedAnswer = repository.save(answer);

Statement vote = new Statement();
vote.setText("+1 for the sun");
vote.setRelation(new JoinField<>("vote", savedAnswer.getId()));
vote.setRouting(savedQuestion.getId());

repository.save(vote);
~~~

This illustrates routing data. In a real application, standardize how both parents and children are routed from the start. For a root parent, routing defaults to the document's ID; children use that same ID value. For `vote`, routing stays the question's ID even though `JoinField`'s parent is the answer's ID.

When custom routing is declared, every get, update, or delete operation must use the same routing value used when indexing the document.

### 8.3. Getting or deleting a document with routing

When operating by ID without passing an entity, supply the corresponding routing:

~~~java
import org.springframework.data.elasticsearch.core.routing.RoutingResolver;

String childId = "A-101";
String routingValue = "Q-100";

Statement answer = operations
    .withRouting(RoutingResolver.just(routingValue))
    .get(childId, Statement.class);

operations
    .withRouting(RoutingResolver.just(routingValue))
    .delete(childId);
~~~

API names can vary across Spring Data Elasticsearch versions. The rule stays constant: get, update, and delete must route to the exact shard holding the document.

## 9. Querying parent-child

Spring Data Elasticsearch does not provide derived repository methods that automatically infer join queries from method names. You must use native queries or custom repository implementations.

Elasticsearch supports the main relationship queries:

| Query | Purpose |
| --- | --- |
| `has_child` | Finds parent documents whose children match a query. |
| `has_parent` | Finds child documents whose parent matches a query. |
| `parent_id` | Finds child documents by their parent's ID. |

### 9.1. has_child

Find questions that have at least one answer containing the word `Sunny`:

~~~json
{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "text": "Sunny"
        }
      }
    }
  }
}
~~~

`has_child` runs the inner query against the declared child type. The result consists of parent documents of matching children.

### 9.2. has_parent

Find answers whose parent `question` contains the phrase `How is the weather`:

~~~json
{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "match": {
          "text": "How is the weather"
        }
      }
    }
  }
}
~~~

The result consists of child documents belonging to parents that match the query.

### 9.3. parent_id

If you already know the parent ID and want to fetch its children:

~~~json
{
  "query": {
    "parent_id": {
      "type": "answer",
      "id": "Q-100"
    }
  }
}
~~~

where `type` is the child relation name and `id` is the parent's ID. This query is useful when you only need direct children of a known parent.

### 9.4. NativeQuery in Spring Data

You can construct a `has_child` query using the Elasticsearch Java API Client and attach it to `NativeQuery`:

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.ChildScoreMode;
import co.elastic.clients.elasticsearch._types.query_dsl.Query;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

Query hasSunnyAnswer = Query.of(q -> q.hasChild(h -> h
    .type("answer")
    .query(child -> child.match(m -> m
        .field("text")
        .query("Sunny")))
    .scoreMode(ChildScoreMode.None)
));

NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(hasSunnyAnswer)
    .build();

SearchHits<Statement> hits =
    operations.search(nativeQuery, Statement.class);
~~~

In this example:

- `type("answer")` specifies the child relation to search.
- `query(...)` is the condition executed on `answer` documents.
- `scoreMode` controls how child scores affect the parent.
- `ElasticsearchOperations` executes the `NativeQuery`.

If your application uses an older Spring Data Elasticsearch version with the High Level REST Client, native query construction differs. Use the API matching the client managed by your Spring Data version.

## 10. Join field in responses

When searching, Elasticsearch returns the `join` field alongside the document. A parent can look like:

~~~json
{
  "_id": "Q-100",
  "_source": {
    "text": "How is the weather?",
    "relation": "question"
  }
}
~~~

A child can look like:

~~~json
{
  "_id": "A-101",
  "_routing": "Q-100",
  "_source": {
    "text": "Sunny",
    "relation": {
      "name": "answer",
      "parent": "Q-100"
    }
  }
}
~~~

A `join` field does not merge two documents into one nested object. When reading results via `SearchHits<Statement>`, each hit is a separate `Statement`. If the application wants to return a `Question` together with a list of `Answer`s, it must group the documents itself or run appropriate queries and combine results at the service layer.

## 11. Limitations of parent-child mapping

Elasticsearch imposes important limitations:

1. Each index can have only one `join` field mapping.
2. Parent and child must reside on the same shard.
3. Each child has only one parent.
4. Each parent can have many children.
5. A child can only be added to a document acting as a parent in the relation schema.
6. Relationships cannot span two different indexes.
7. Join queries and join aggregations have noticeably higher overhead than standard field queries.

A single document can simultaneously be a child to an upper tier and a parent to a lower document type, like `answer` in the `question → answer → vote` example.

## 12. Global ordinals cost

`join` fields use global ordinals to support relationship queries. Global ordinals are built per shard and must be updated whenever a shard changes.

In `join` mappings, `eager_global_ordinals` is often enabled. This means global ordinals are built during refresh, avoiding latency spikes on the first join query after data changes. In return, refreshes can take longer.

Consider setting `eager_global_ordinals = false` if:

- The index receives frequent writes.
- Join queries are rarely executed.
- The cost of building ordinals on the first join query after refresh is acceptable.

Manual mapping example:

~~~json
{
  "mappings": {
    "properties": {
      "relation": {
        "type": "join",
        "relations": {
          "question": ["answer", "comment"]
        },
        "eager_global_ordinals": false
      }
    }
  }
}
~~~

Do not disable eager loading just to shorten refresh times if join queries are the primary access path. Benchmark write latency, refresh latency, and query latency together.

## 13. Parent-child or denormalization?

`join` mapping should not be used to replace every relationship from a relational database.

| Criterion | Parent-child join | Denormalization |
| --- | --- | --- |
| Storing parent and child | Independent documents in the same index. | Can embed children or copy parent fields into documents. |
| Updating children independently | Yes. | Can update child documents independently if split, though duplicated data needs syncing. |
| Querying by relationship | `has_child`, `has_parent`, `parent_id`. | Direct queries on copied/embedded fields. |
| Query cost | Higher due to joins and global ordinals. | Usually simpler and faster. |
| Best suited for | One parent with very many children needing independent updates. | Read-heavy data, relatively stable structure, acceptable data duplication. |

For instance, a product with thousands of offers is a candidate for parent-child if offers must be updated independently. If each product has only a few reviews mostly read together, embedding or copying data may be a better fit.

## 14. Common errors when mapping JoinField

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Spring Data does not create a `join` mapping | Property is not typed as `JoinField` or missing `@JoinTypeRelations`. | Check the field type and place the annotation on the proper property. |
| Undefined relation error | Name passed to `JoinField` is absent from `children` in the annotation. | Align relation names between mapping and code. |
| Child cannot find parent | Parent and child are on different shards due to wrong routing. | Use the root parent's routing value consistently. |
| Child saved, but `has_child` returns no parent | Query uses wrong child type or parent ID/routing is incorrect. | Inspect mapping, `_source`, and query `type`. |
| Cannot fetch child via `get(id)` | Request lacks the routing used during indexing. | Use `withRouting` or an appropriate routing resolver. |
| `JoinField` generic fails conversion | Generic type differs from `@Id` type. | Use the same ID type, e.g., `JoinField<String>` with `@Id String`. |
| Multi-level tree fails to work | Using direct parent ID as routing instead of root ancestor. | Keep direct parent ID in `JoinField` and route by top-level ancestor ID. |
| Slow refresh after heavy writes | Global ordinals for the join field must be rebuilt. | Measure `eager_global_ordinals` and consider alternative data models. |
| Derived repository queries don't support join | Join queries require native queries. | Use `NativeQuery` and a custom repository implementation. |

## 15. Relationship mapping implementation workflow

When designing parent-child in Spring Data Elasticsearch, follow this sequence:

1. Identify parent types and child types from business requirements.
2. Verify whether the relationship genuinely needs independent parent/child updates.
3. Declare one `JoinField` property on the entity.
4. Declare `@JoinTypeRelations` with all parents and children.
5. Ensure `JoinField`'s generic type matches `@Id`'s type.
6. Create the mapping and verify the field has `type: join` and proper `relations`.
7. When saving a parent, use `JoinField` with the parent relation name.
8. When saving a child, use `JoinField` with the child name and direct parent ID.
9. Ensure routing keeps the parent and entire lineage on the same shard.
10. For multi-level trees, route deep children using the root ancestor's ID.
11. Use `NativeQuery` for `has_child`, `has_parent`, or `parent_id`.
12. Measure global ordinals and join query costs with near-production data.

## 16. References

- [Spring Data Elasticsearch — Join-Type implementation](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/join-types.html)
- [Spring Data Elasticsearch — Routing values](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/routing.html)
- [Spring Data Elasticsearch — JoinField API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/core/join/JoinField.html)
- [Spring Data Elasticsearch — JoinTypeRelations API](https://docs.spring.io/spring-data/elasticsearch/reference/api/java/org/springframework/data/elasticsearch/annotations/JoinTypeRelations.html)
- [Elasticsearch — Join field type](https://www.elastic.co/docs/reference/elasticsearch/mapping-reference/parent-join)

`@JoinTypeRelations` describes the permitted parent-child types in the mapping; `JoinField` identifies each document's role and parent ID. Spring Data translates them into an Elasticsearch `join` field and supports parent-based routing for single-level relationships. With multiple levels, you must route by the root ancestor. Join queries require native queries and incur global ordinals overhead, so use parent-child only when the benefit of independent updates is genuinely needed.
