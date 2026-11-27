# Has Parent, Has Child, and the Same-Shard Requirement

Elasticsearch typically stores data as independent documents. When two document types have a parent-child relationship—such as a question with many answers or a department with many employees—you can model the relationship using a **join field**. Based on this mapping, Elasticsearch provides `has_parent` and `has_child` queries to find documents based on conditions on related documents.

A mandatory requirement of the parent-child model is that parent and child documents must reside on **the same shard of the same index**. Elasticsearch enforces this through routing: when indexing parents and children, the application must pass the same routing value, typically the parent's ID. If routing is omitted or different values are used, the two documents can be distributed to different shards and the relationship will not work properly.

Parent-child fits when both document types need independent updates and a parent can have many children. It carries higher query and management overhead than flat documents or `nested`, so use it only when the data lifecycle truly requires independent relationships.

## 1. Parent-child relationship model

For example, a forum has:

- One `question` document representing a question.
- Multiple `answer` documents representing answers belonging to that question.

A question can have many answers:

~~~text
Question Q-100
   |
   +---- Answer A-1
   |
   +---- Answer A-2
   |
   +---- Answer A-3
~~~

In Elasticsearch, parent and child remain two separate documents. They are not stored inside a single nested JSON object like `nested` objects. The `join` field stores the relationship type and the parent's ID on the child document.

Example data:

~~~json
{
  "_id": "Q-100",
  "question": "How does routing work?",
  "relation": "question"
}
~~~

~~~json
{
  "_id": "A-1",
  "answer": "Routing keeps related documents on one shard.",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  }
}
~~~

The parent document stores the relation name as a string. The child document stores an object with `name` set to the child relation name and `parent` set to the parent document's ID.

## 2. Join field mapping

Elasticsearch uses a field of type `join` to declare relationships. The mapping must define valid relations before indexing data:

~~~http
PUT /forum
Content-Type: application/json

{
  "mappings": {
    "properties": {
      "relation": {
        "type": "join",
        "relations": {
          "question": "answer"
        }
      },
      "question": {
        "type": "text"
      },
      "answer": {
        "type": "text"
      },
      "createdAt": {
        "type": "date"
      }
    }
  }
}
~~~

Here `question` is the parent relation and `answer` is the child relation. The relation name is a logical name in the `join` field; it does not have to match content field names or Java class names.

An index can have only one `join` field. That `join` field can describe multiple parent-child pairs, but all relationships must be declared within that single field.

### 2.1. One parent, many children

The `"question": "answer"` relation allows one `question` document to have many `answer` documents. Each `answer` belongs to exactly one `question` parent.

- A parent can have 0, 1, or many children.
- Each child has exactly one parent within the declared relationship.
- Parent and child are independent documents with their own IDs.
- Relationships are defined by the `join` field, not by placing an arbitrary JSON field named `parentId`.

You can also store a business field like `questionId` for display or integration convenience, but that field does not replace the `join` field and routing.

### 2.2. Multi-level relationships

A `join` field supports multiple relationship levels, such as `question → answer → comment`:

~~~json
{
  "relations": {
    "question": {
      "answer": "comment"
    }
  }
}
~~~

In this model, `question` is the parent of `answer` and `answer` is the parent of `comment`. All documents in a relationship chain must still be routed to the same shard using the root ancestor's routing. Multiple join levels complicate queries and management; avoid overusing deep hierarchies because join costs increase.

## 3. Why must parent and child be on the same shard?

Elasticsearch divides an index into multiple primary shards. Each shard is an independent partition, and `join` field resolution happens within a shard's scope. Elasticsearch does not perform cross-shard parent-child joins.

If the parent sits on shard 1 while a child sits on shard 3, the shard holding the child cannot use the join relationship to locate a parent on another shard. Therefore, sharing the same index is not enough; the two documents must also be routed to the exact same shard.

### 3.1. Routing determines the shard

When indexing a document, Elasticsearch uses its ID or routing value to select the target shard. If no routing is supplied, the document ID is normally used as the routing input. Because parent and child have different IDs, by default they can land on different shards.

To keep the relationship intact:

~~~text
parent Q-100: routing = Q-100
child  A-1:   routing = Q-100
child  A-2:   routing = Q-100
child  A-3:   routing = Q-100
~~~

All documents in the same relationship share routing value `Q-100`. Elasticsearch accordingly places them on the same shard.

### 3.2. Routing parents and children

When indexing the parent, pass routing equal to the parent's ID:

~~~http
PUT /forum/_doc/Q-100?routing=Q-100
Content-Type: application/json

{
  "question": "How does routing work?",
  "relation": "question",
  "createdAt": "2026-11-13T08:00:00Z"
}
~~~

When indexing a child, pass the exact same parent routing value:

~~~http
PUT /forum/_doc/A-1?routing=Q-100
Content-Type: application/json

{
  "answer": "Routing keeps related documents on one shard.",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  },
  "createdAt": "2026-11-13T08:10:00Z"
}
~~~

Another child for the same parent:

~~~http
PUT /forum/_doc/A-2?routing=Q-100
Content-Type: application/json

{
  "answer": "The child must use the same routing value as its parent.",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  },
  "createdAt": "2026-11-13T08:15:00Z"
}
~~~

Notice there are two separate values:

- `relation.parent` records the parent's ID in the `join` field.
- The URL parameter `routing` determines the shard.

In this example, both happen to be `Q-100`, but they serve different roles. Writing `parent` in the JSON while omitting `routing` does not guarantee the child lands on the same shard as the parent.

### 3.3. Same index with different routing is still wrong

The following example is unsafe:

~~~http
PUT /forum/_doc/A-1?routing=A-1
Content-Type: application/json

{
  "answer": "This child may be routed to a different shard.",
  "relation": {
    "name": "answer",
    "parent": "Q-100"
  }
}
~~~

The child uses routing `A-1`, whereas the parent uses `Q-100`. Two different routing values can map to different shards. Elasticsearch requires the child's routing to match the parent's routing for joins to work.

Do not rely on two documents happening to land on the same shard under default routing. Always pass routing explicitly for every parent and child index operation.

## 4. The has_child query

`has_child` finds parent documents based on conditions over their child documents. For example, finding questions that have at least one answer containing the keyword `routing`:

~~~http
GET /forum/_search
Content-Type: application/json

{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "answer": "routing"
        }
      }
    }
  }
}
~~~

The result contains `question` documents that have at least one `answer` child matching the `match` query. It returns parent documents; if you also need the matching child content, you can use `inner_hits`.

### 4.1. has_child with count constraints

You can constrain the number of matching children using `min_children` and `max_children`:

~~~json
{
  "query": {
    "has_child": {
      "type": "answer",
      "min_children": 2,
      "max_children": 10,
      "query": {
        "term": {
          "approved": true
        }
      }
    }
  }
}
~~~

The query selects parents with at least 2 and at most 10 approved `answer` children. Without these parameters, a parent only needs at least one matching child.

### 4.2. has_child and score_mode

If the child query produces a relevance score, `score_mode` defines how matching child scores are aggregated into the parent's score:

| Value | Meaning |
|---|---|
| `none` | Do not include child scores in the parent score |
| `min` | Use the lowest score among matching children |
| `max` | Use the highest score |
| `sum` | Sum child scores |
| `avg` | Take the average of child scores |

Example:

~~~json
{
  "query": {
    "has_child": {
      "type": "answer",
      "score_mode": "max",
      "query": {
        "match": {
          "answer": "Elasticsearch routing"
        }
      }
    }
  }
}
~~~

The parent is scored according to its highest-scoring matching child. If you only need to filter parents with matching children and do not want child scores affecting ranking, use `score_mode: "none"`.

### 4.3. inner_hits to retrieve matching children

`has_child` can use `inner_hits` to return the children that matched the query as well:

~~~json
{
  "query": {
    "has_child": {
      "type": "answer",
      "query": {
        "match": {
          "answer": "routing"
        }
      },
      "inner_hits": {
        "name": "matching_answers",
        "size": 5
      }
    }
  }
}
~~~

The main hits are parents. Inside each parent hit, `inner_hits` can return up to 5 answers matching the query. This is useful for a question page that wants to display relevant answers directly beneath each question.

## 5. The has_parent query

`has_parent` works in the reverse direction: finding child documents based on conditions on their parent document.

For example, finding answers belonging to questions whose `category` is `spring`:

~~~http
GET /forum/_search
Content-Type: application/json

{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "term": {
          "category": "spring"
        }
      }
    }
  }
}
~~~

The result contains `answer` documents whose `question` parent satisfies the `category` condition. The condition inside `has_parent` is evaluated on the parent, while the returned documents are children.

### 5.1. has_parent and score

By default, the parent's score is not necessarily propagated to children. You can set `score: true` if you want the parent's score to influence child scores:

~~~json
{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "score": true,
      "query": {
        "match": {
          "question": "Spring Data Elasticsearch"
        }
      }
    }
  }
}
~~~

Enable `score` when the parent's relevance matters to child ranking. If the parent is only used as a filter condition, there is no need to propagate scores.

### 5.2. inner_hits to inspect the parent

You can request `inner_hits` to retrieve the matching parent:

~~~json
{
  "query": {
    "has_parent": {
      "parent_type": "question",
      "query": {
        "term": {
          "category": "spring"
        }
      },
      "inner_hits": {
        "name": "parent_question",
        "size": 1
      }
    }
  }
}
~~~

The main hits are answers; `inner_hits` retrieves the corresponding parent question. This is useful when an API result displays an answer alongside details of the original question.

## 6. The parent_id query when the parent is known

If you already know the parent's ID and simply want to find children belonging to that parent, use the `parent_id` query:

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

The query returns children with relation type `answer` and parent ID `Q-100`. This is more direct than `has_child` when no complex search condition on child content is needed to identify the parent.

When you know the parent ID and have the routing value, pass routing on the search request to limit the search to the shard holding the relationship:

~~~http
GET /forum/_search?routing=Q-100
Content-Type: application/json

{
  "query": {
    "parent_id": {
      "type": "answer",
      "id": "Q-100"
    }
  }
}
~~~

Passing routing at search time is a shard-scope optimization when the application knows the routing value. It does not replace storing parents and children with proper routing in the first place.

## 7. Updating and deleting parent-child documents

Because parent and child are separate documents, they can be updated independently. However, write operations must supply the right routing value.

### 7.1. Updating a child

~~~http
POST /forum/_update/A-1?routing=Q-100
Content-Type: application/json

{
  "doc": {
    "answer": "Updated answer about routing."
  }
}
~~~

Routing is still the parent's ID, not the child's ID. If you update a child without routing, Elasticsearch may look on the wrong shard and report that the document does not exist even though the child is actually in the index.

### 7.2. Deleting a child

~~~http
DELETE /forum/_doc/A-1?routing=Q-100
~~~

Deleting a child also requires the parent's routing. Store the routing key in application data or have a way to determine it before updating/deleting.

### 7.3. Deleting a parent

Deleting a parent must not be assumed to automatically delete all children. The application needs to define a lifecycle policy:

- Delete all children first, then delete the parent.
- Use `delete_by_query` by relation/parent ID with appropriate routing, then delete the parent.
- Retain children as historical records and update the parent's business status instead.

Do not rely on an assumption of cascade delete. Design an explicit deletion workflow and test it against your running Elasticsearch version.

### 7.4. Bulk indexing

When using the Bulk API, routing must be specified on each document's action metadata:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"index":{"_index":"forum","_id":"Q-100","routing":"Q-100"}}
{"question":"How does routing work?","relation":"question"}
{"index":{"_index":"forum","_id":"A-1","routing":"Q-100"}}
{"answer":"Routing keeps related documents on one shard.","relation":{"name":"answer","parent":"Q-100"}}
~~~

If a child's action metadata omits routing or uses a different routing value, the bulk request may still be accepted, but the parent-child relationship will not be formed properly. Always check each item's result in the bulk response, not just the overall HTTP status.

## 8. Data model and same-shard constraints

A parent-child relationship must keep three elements consistent:

1. The `join` field mapping defines the proper parent and child relations.
2. The child join value holds the exact parent ID.
3. Parent and child share the same routing so they reside on the same shard.

Example table:

| Document | ID | Join field | Routing |
|---|---|---|---|
| Parent question | `Q-100` | `"question"` | `Q-100` |
| Child answer 1 | `A-1` | `{"name":"answer","parent":"Q-100"}` | `Q-100` |
| Child answer 2 | `A-2` | `{"name":"answer","parent":"Q-100"}` | `Q-100` |
| Child answer 3 | `A-3` | `{"name":"answer","parent":"Q-100"}` | `Q-100` |

If a parent uses custom routing different from its ID, children must use that exact custom routing value. The core rule is identical routing across the parent and all descendants in the relationship; using the parent ID as routing is a common and easy-to-manage convention.

Avoid creating children before the parent if the application has not yet guaranteed valid routing and relationships. The write flow typically creates the parent first, then creates children. If events arrive asynchronously, handle the case where the parent does not exist yet and retry or queue the child.

## 9. Integrating parent-child with Spring Data Elasticsearch

Spring Data Elasticsearch supports join fields via `JoinField<T>`, relationship mapping annotations, and routing metadata. Package names or API details may vary across release trains, so consult your project dependency's Javadoc.

### 9.1. Declaring JoinField

Example model for questions and answers:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelation;
import org.springframework.data.elasticsearch.annotations.JoinTypeRelations;
import org.springframework.data.elasticsearch.annotations.Routing;
import org.springframework.data.elasticsearch.core.mapping.JoinField;

@Document(indexName = "forum")
public class ForumDocument {

    @Id
    private String id;

    @Field(type = FieldType.Join)
    @JoinTypeRelations(
            relations = {
                    @JoinTypeRelation(
                            parent = "question",
                            children = {"answer"}
                    )
            }
    )
    private JoinField<String> relation;

    @Routing
    private String routing;

    @Field(type = FieldType.Text)
    private String question;

    @Field(type = FieldType.Text)
    private String answer;

    // constructors, getters and setters
}
~~~

`JoinField<String>` holds the relation name and parent ID if the document is a child. `@JoinTypeRelations` declares the valid relation types. `@Routing` marks the property holding the routing value that Spring Data should use when sending index/search/update operations.

For the parent:

~~~java
ForumDocument question = new ForumDocument();
question.setId("Q-100");
question.setQuestion("How does routing work?");
question.setRelation(new JoinField<>("question", null));
question.setRouting("Q-100");
~~~

For the child:

~~~java
ForumDocument answer = new ForumDocument();
answer.setId("A-1");
answer.setAnswer("Parent and child must share one shard.");
answer.setRelation(new JoinField<>("answer", "Q-100"));
answer.setRouting("Q-100");
~~~

Both entities have different IDs and content, yet share the same routing. The child relation references the parent ID inside `JoinField`.

### 9.2. Saving entities

Once the entity is configured with join field and routing metadata, you can use `ElasticsearchOperations` or a repository to save according to your version's API:

~~~java
operations.save(question);
operations.save(answer);
~~~

This example assumes the Spring Data mapping context recognizes the `@Routing` property and extracts the routing value from the entity. Verify the actual outgoing requests or confirm documents land on the same shard before deploying. If your version does not automatically apply routing for a specific operation, pass routing explicitly via the client's index/query API.

Do not merely set `JoinField` and assume Spring Data always infers routing from the parent ID. `JoinField` describes the relationship; routing is separate metadata that must be set explicitly.

### 9.3. Querying with NativeQuery

`has_child`, `has_parent`, and `parent_id` queries belong to Elasticsearch Query DSL. With Spring Data Elasticsearch, you can use `NativeQuery` and the Elasticsearch Java Client to construct them:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.hasChild(hc -> hc
                .type("answer")
                .query(childQuery)
                .scoreMode(ChildScoreMode.Max)
        ))
        .build();

SearchHits<ForumDocument> hits =
        operations.search(query, ForumDocument.class);
~~~

This snippet illustrates the builder structure. Enum names, packages, and overloads for `hasChild`, `hasParent`, and `parentId` depend on the Elasticsearch Java Client version. You can use JSON DSL in `@Query` for fixed structures; for dynamic queries or `inner_hits`, `NativeQuery` is typically more flexible.

## 10. Routing in Spring Data and Elasticsearch Java Client

Routing is part of the parent-child data contract. The application should have a single consistent rule for determining routing values:

- Parent: routing value equal to the parent ID or chosen routing key.
- Child: use the parent's routing key.
- Update/delete child: reuse the parent's routing key.
- Search for a specific parent: pass routing to restrict shards.

If using Spring Data's `@Routing` annotation, ensure the routing property is populated before calling `save`. If operations use the Elasticsearch Java Client directly, set routing in the corresponding request options/builders.

Do not let each service construct routing with ad-hoc rules. A helper or domain method can return the routing key so all write, update, and delete paths use it consistently.

## 11. Performance and cost of parent-child

Parent-child joins let you update children independently without rewriting the entire parent, at a cost:

- Join queries must coordinate relationship data within shards.
- `has_child` and `has_parent` can be significantly more resource-intensive than regular `term`/`range` queries.
- `join` fields use global ordinals; building or updating ordinals can impact refresh cost and memory.
- A parent with a very large number of children can make score aggregation or `inner_hits` queries heavy.
- Parent-based routing can create unbalanced shard distribution if a single parent has too many children.

Therefore, parent-child is not a default replacement for nested objects. Use it only when the benefits of independent updates or parent-child cardinality outweigh join overhead.

### 11.1. Avoiding hot parents

If one parent has millions of children, every document in that relationship must reside on the same shard. Such a parent can create a hotspot: one shard absorbs most of the data and read/write traffic for that relationship.

Estimate the maximum number of children per parent and parent distribution across shards. If your data has a few massive parents, consider alternatives such as denormalization, index splitting, or business partitioning.

### 11.2. Comparing with nested and denormalization

| Model | Storage | Pros | Costs/limits |
|---|---|---|---|
| Standard embedded object | Single document with objects/arrays | Simple | Does not guarantee same-element correlation when querying arrays of objects |
| Nested | Child objects indexed as nested documents inside the same root | Accurate querying per child object without joining two root documents | Updating a nested object usually requires reindexing the root document |
| Parent-child | Parent and child are separate documents, `join` field | Independent child updates, one parent with many children | Same shard required, join queries are expensive |
| Denormalization | Copy queryable data into documents | Simple and fast queries | Must synchronize duplicated data |

If child data is small, always read with the parent, and updated together, `nested` is usually better. If you need fast queries and can accept copying a few parent fields into children, denormalization can be simpler. Parent-child is useful when children are numerous, change independently, and relationships genuinely need bidirectional queries.

## 12. Changing mappings and migrating data

A `join` field must be declared in the mapping before indexing documents. You cannot arbitrarily turn a normal field into a `join` field on an existing populated index and expect relationships to materialize automatically.

If you need to add or modify a parent-child model:

1. Create a new index with the complete `join` mapping.
2. Determine the parent ID and routing key for each document.
3. Index parents using the chosen routing keys.
4. Index children with the same routing keys and `join` values holding parent IDs.
5. Verify parents and children share shards and relationship queries work.
6. Reindex/migrate data in controlled batches.
7. Switch the alias to the new index once data is ready.

When reindexing parent-child data, preserve both the `join` field and routing. If a script or pipeline only copies `_source` without preserving routing metadata, documents can be routed to the wrong shards and relationships will break.

## 13. Common mistakes

### 13.1. Writing parent ID without routing

A child's `join` field holds the right parent ID, yet the child can still end up on another shard if routing is omitted. Always set child routing equal to the parent's routing.

### 13.2. Routing children by the child's own ID

Default routing by child ID can send children to different shards. Use the parent's routing key for all children.

### 13.3. Thinking the same index is enough

Parent and child must share both the same index and the same shard. Same index on different shards still cannot join.

### 13.4. Updating or deleting without routing

The operation may look on the wrong shard and report document not found. Store the routing key or recompute it before updating/deleting.

### 13.5. Confusing relation name with field name

In `has_child`, `type` is the child relation name declared in the join mapping, not the name of a text field on the child.

### 13.6. Using has_parent when parents are wanted as results

`has_parent` returns child documents matching a parent condition. `has_child` returns parent documents having matching children. Choose according to which document type you want returned.

### 13.7. Expecting cascade delete

Deleting a parent must not be assumed to delete all children automatically. Design explicit child and parent deletion workflows.

### 13.8. Using parent-child for every relationship

Join queries are costly and routing can cause hotspots. Compare with `nested` and denormalization before choosing.

## 14. Testing same-shard relationships

An integration test should verify mapping, routing, and queries together:

1. Create an index with a `question → answer` `join` field relation.
2. Index parent `Q-100` with routing `Q-100`.
3. Index child `A-1` with parent `Q-100` and routing `Q-100`.
4. Refresh the index or wait appropriately for search visibility in the test.
5. Run `has_child` and verify the parent is returned.
6. Run `has_parent` and verify the child is returned.
7. Run `parent_id` with the known parent ID.
8. Update the child with parent routing and verify the change.
9. Test a child with wrong routing to observe that the operation fails to form a valid relationship or queries do not find it as expected.
10. Inspect per-item responses when using the Bulk API.

You can check a document's shard via the explain API or shard-level search in test environments, but most importantly verify that routing is applied consistently across all operations. Do not rely on a small test where parent and child happen by coincidence to land on the same shard under default routing.

## 15. Parent-child design workflow

When considering this model:

1. Identify the two document types and the one-parent-many-children relationship.
2. Confirm children need to be updated independently of the parent.
3. Compare against `nested` and denormalization.
4. Design a `join` field and declare the relation mapping.
5. Choose a stable routing key; typically the parent's ID.
6. Ensure parent, all children, and descendants use the exact same routing value.
7. Store the routing key in the domain model or derive it from the relationship.
8. Use `has_child`, `has_parent`, or `parent_id` according to the document type to retrieve.
9. Design updates/deletes/reindexing to preserve routing.
10. Evaluate join costs, global ordinals, and parent distribution across shards.
11. Test with realistic data and representative child counts.

## 16. Conclusion

`has_child` finds parents based on child conditions; `has_parent` finds children based on parent conditions. The `join` field declares the relationship type and parent ID on child documents. Parents and children remain independent documents within the same index.

The non-negotiable technical requirement is that parent and child must reside on the same shard. Pass the same routing value when indexing the parent and every child; the common convention is routing by the parent's ID. `relation.parent` in the `join` field records the parent ID, whereas the `routing` parameter determines the shard; the two values can match, but they serve two distinct roles.

In Spring Data Elasticsearch, `JoinField`, `@JoinTypeRelations`, and `@Routing` help represent relationship and routing metadata. Check your actual version and verify routing is transmitted properly during save/update/delete operations. Parent-child is helpful when children need an independent lifecycle, but you must weigh join costs, global ordinals, and shard hotspots and compare against `nested` or denormalization before adopting it.
