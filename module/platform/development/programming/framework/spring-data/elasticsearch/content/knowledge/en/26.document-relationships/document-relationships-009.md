# Comparing Embedded, Nested, Parent-Child, and Application-Level Linking

When an Elasticsearch document has related data, the application must choose how to represent that relationship. For example, a product has multiple variants and multiple sellers; a question has multiple answers; an article has an author and many comments; an order has multiple line items. Such data can be stored together in one document, stored as nested objects, organized in a parent-child relationship, or kept separate and linked at the application layer.

No single model fits every scenario. How you store data affects:

- Query accuracy when multiple related attributes must match on the same element.
- Indexing, update, delete, and search costs.
- Query, aggregation, and sorting capabilities over related data.
- Document size and internal Lucene document count.
- How data is synchronized and how consistency is handled.
- Complexity of Spring Data Elasticsearch code.

The four main options:

1. **Embedded object:** embed related data inside the document as a regular object or array of objects.
2. **Nested:** store each object element in a `nested` structure so Elasticsearch preserves relationships between fields within the same element.
3. **Parent-child:** store parent and child as separate documents in the same index, connected by a `join` field.
4. **Application-level linking:** store reference IDs, query separate documents, and join results in a service or repository.

To choose well, start from how data is read and updated, then consider Elasticsearch's limits and Spring Data's mapping capabilities.

## 1. The relationship problem in a document database

Suppose a product has multiple offers:

    {
      "productId": "p-100",
      "name": "Mechanical Keyboard",
      "offers": [
        {
          "seller": "Store A",
          "price": 120,
          "available": true
        },
        {
          "seller": "Store B",
          "price": 95,
          "available": false
        }
      ]
    }

A user wants to find products with an offer that has both `seller` equal to `Store A` and `price` under 100. If `offers` is stored as a standard object array, Elasticsearch can split the values into independent lists during indexing. A query combining `seller` and `price` can accidentally match the first offer's `seller` with the second offer's `price`.

This example shows where relationships between fields matter. If business logic requires conditions to hold simultaneously on a single element, choose a model that preserves element boundaries—usually `nested`.

Conversely, if the application only needs to find products by any seller and does not need `seller` and `price` to belong to the same offer, an object array can be simpler and less expensive.

## 2. What is an embedded object?

An embedded object is an object stored directly inside the parent document. In Elasticsearch mappings, `object` is the default type for an object property when no other type is specified.

Example:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text"
          },
          "manufacturer": {
            "properties": {
              "name": {
                "type": "keyword"
              },
              "country": {
                "type": "keyword"
              }
            }
          }
        }
      }
    }

Document:

    {
      "name": "Keyboard K8",
      "manufacturer": {
        "name": "Keychron",
        "country": "China"
      }
    }

Embedded objects fit when child data:

- Has a lifecycle tightly bound to the parent document.
- Is usually read together with the parent document.
- Does not need to be queried independently as a separate entity.
- Does not require preserving complex relationships across multiple objects in an array.
- Has a relatively stable size that does not grow without bound.

A major benefit is that the application can retrieve all required data in a single search without joins or extra repository calls.

## 3. Standard object arrays and the loss of field relationships

Suppose a mapping has an `offers` array:

    PUT products
    {
      "mappings": {
        "properties": {
          "offers": {
            "properties": {
              "seller": {
                "type": "keyword"
              },
              "price": {
                "type": "double"
              },
              "available": {
                "type": "boolean"
              }
            }
          }
        }
      }
    }

Document:

    {
      "offers": [
        {
          "seller": "Store A",
          "price": 120,
          "available": true
        },
        {
          "seller": "Store B",
          "price": 95,
          "available": false
        }
      ]
    }

Elasticsearch indexes the object array's values in a way that loses boundaries between individual objects. Conceptually, the fields can be viewed as:

    offers.seller = [ "Store A", "Store B" ]
    offers.price = [ 120, 95 ]
    offers.available = [ true, false ]

If you query:

    GET products/_search
    {
      "query": {
        "bool": {
          "must": [
            {
              "term": {
                "offers.seller": "Store A"
              }
            },
            {
              "range": {
                "offers.price": {
                  "lt": 100
                }
              }
            }
          ]
        }
      }
    }

The document can match because `Store A` exists in one offer and price `95` exists in another offer. Yet no offer is both from `Store A` and priced under 100.

This is a false positive caused by the application needing same-element correlation while a regular object array does not preserve that correlation at index time.

### When an object array is still appropriate

An object array is not always wrong. It works well when:

- You only need to know whether a value appears in any element.
- You do not need to combine multiple conditions on the same child object.
- Each field is queried independently.
- You want to avoid the overhead of nested documents.

For example, finding products with any offer from `Store A` can use a `term` query on `offers.seller` if no other attribute of that same offer needs to be constrained.

## 4. Spring Data mapping for embedded objects

Spring Data Elasticsearch maps Java objects to `object` fields. You can declare the type explicitly with `FieldType.Object`:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;

        @Field(type = FieldType.Object)
        private Manufacturer manufacturer;
    }

    public class Manufacturer {

        private String name;
        private String country;
    }

For a list of objects:

    @Field(type = FieldType.Object)
    private List<Offer> offers;

    public class Offer {

        private String seller;
        private Double price;
        private Boolean available;
    }

Spring Data's mapping metadata helps create appropriate mappings when the application initializes indexes via `IndexOperations`. If a mapping needs analyzers, normalizers, dynamic templates, or advanced Elasticsearch properties, you can manage the mapping via JSON mapping files or index templates.

Declaring Java classes alone does not solve the loss of correlation across objects in an array. If the field is mapped as `object`, Elasticsearch still applies the object-array semantics described above.

## 5. What is Nested?

`nested` is a specialized Elasticsearch object type. Each nested element is indexed as a separate Lucene document while remaining attached to the parent document. This lets Elasticsearch preserve relationships between fields within the same nested object.

Mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "name": {
            "type": "text"
          },
          "offers": {
            "type": "nested",
            "properties": {
              "seller": {
                "type": "keyword"
              },
              "price": {
                "type": "double"
              },
              "available": {
                "type": "boolean"
              }
            }
          }
        }
      }
    }

The document keeps the same JSON structure:

    {
      "name": "Keyboard K8",
      "offers": [
        {
          "seller": "Store A",
          "price": 120,
          "available": true
        },
        {
          "seller": "Store B",
          "price": 95,
          "available": false
        }
      ]
    }

The difference lies in the mapping and indexing mechanics. `nested` preserves individual element boundaries, so queries can require `seller` and `price` to match on the same offer.

`nested` is not a general-purpose join between two entities. It is a way to represent child objects inside a parent document that can be queried independently along a nested path while still being read and updated together with the parent document.

## 6. Nested queries keep conditions within the same element

To find products that have an offer both from `Store A` and priced under 100:

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "offers",
          "query": {
            "bool": {
              "must": [
                {
                  "term": {
                    "offers.seller": "Store A"
                  }
                },
                {
                  "range": {
                    "offers.price": {
                      "lt": 100
                    }
                  }
                }
              ]
            }
          }
        }
      }
    }

The `nested` query evaluates the conditions inside path `offers` against the same nested document. With the example data, the document does not match because `Store A`'s offer is priced at 120.

If you change the seller condition to `Store B`, the document matches because `Store B`'s offer is priced at 95.

### The nested path must be exact

`path` is the nested field's name in the mapping. If nested objects are nested inside one another, queries must use the proper path and may require nested queries nested inside one another matching the mapping structure.

You cannot run a `nested` query on a field mapped as a regular `object`. Elasticsearch requires mapping type `nested` to create and query nested Lucene documents.

## 7. Nested in Spring Data Elasticsearch

You can map a nested field using `FieldType.Nested`:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;

        @Field(type = FieldType.Nested)
        private List<Offer> offers;
    }

    public class Offer {

        private String seller;
        private Double price;
        private Boolean available;
    }

This annotation tells Spring Data that `offers` should be mapped as `nested` rather than regular `object`.

Some projects manage index mappings via external templates or JSON rather than generating mappings from entities. In that case, ensure the actual mapping on the cluster has type `nested`. Changing the annotation alone without recreating the mapping of an existing index will not automatically convert `object` to `nested`.

When switching an existing field from `object` to `nested`, you typically need to create a new index and reindex data because a field's mapping type cannot be changed in place this way.

## 8. Nested queries with NativeQuery

Modern Spring Data Elasticsearch can build nested queries using `NativeQuery` and the Elasticsearch Java API Client:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .nested(n -> n
                .path("offers")
                .query(nq -> nq
                    .bool(b -> b
                        .must(m -> m
                            .term(t -> t
                                .field("offers.seller")
                                .value(FieldValue.of("Store B"))
                            )
                        )
                        .must(m -> m
                            .range(r -> r
                                .number(num -> num
                                    .field("offers.price")
                                    .lt(100.0)
                                )
                            )
                        )
                    )
                )
            )
        )
        .build();

    SearchHits<Product> hits =
        operations.search(query, Product.class);

This example uses:

    import co.elastic.clients.elasticsearch._types.FieldValue;
    import org.springframework.data.elasticsearch.client.elc.NativeQuery;

Overload names and range builder types depend on your Elasticsearch Java API Client version. The key point is that both `seller` and `price` conditions sit inside the same `nested` query with path `offers`.

If you split the `seller` term and `price` range into two separate `nested` queries, each query can match a different `offers` element. When the requirement is for the same offer to satisfy all conditions, place them inside the same `nested` query and `bool`.

## 9. inner_hits: retrieving matching nested elements

By default, a `nested` query returns the parent document. If the UI needs to know exactly which offer matched, use `inner_hits`:

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "offers",
          "query": {
            "bool": {
              "must": [
                {
                  "term": {
                    "offers.seller": "Store B"
                  }
                },
                {
                  "range": {
                    "offers.price": {
                      "lt": 100
                    }
                  }
                }
              ]
            }
          },
          "inner_hits": {
            "name": "matching_offers",
            "size": 5
          }
        }
      }
    }

`inner_hits` returns matching nested documents under each parent hit. It is helpful when displaying the exact offer, comment, or variant that caused a product to match.

Limit `inner_hits` `size`. If each parent has many nested objects and requests return many inner hits, response sizes can grow substantially.

Spring Data can expose inner hits in `SearchHit` metadata according to your version's API. For detailed handling, inspect the `SearchHit` type and the inner hits structure of the Elasticsearch Java API Client.

## 10. Nested aggregations

When computing statistics over nested objects, use a `nested` aggregation to enter the nested path:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "offers": {
          "nested": {
            "path": "offers"
          },
          "aggs": {
            "average_offer_price": {
              "avg": {
                "field": "offers.price"
              }
            },
            "by_seller": {
              "terms": {
                "field": "offers.seller"
              }
            }
          }
        }
      }
    }

A `nested` aggregation shifts aggregation scope from parent documents to nested documents. Thus `doc_count` inside a nested bucket counts nested objects, not parent products.

To step back up to parent document scope, use a `reverse_nested` aggregation:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "offers": {
          "nested": {
            "path": "offers"
          },
          "aggs": {
            "by_seller": {
              "terms": {
                "field": "offers.seller"
              },
              "aggs": {
                "parent_products": {
                  "reverse_nested": {}
                }
              }
            }
          }
        }
      }
    }

`parent_products` counts parent documents that have matching nested objects. Clearly distinguish nested object counts from parent document counts when presenting statistics.

## 11. Nested sort

You can sort parent documents by the lowest price among nested offers:

    GET products/_search
    {
      "sort": [
        {
          "offers.price": {
            "order": "asc",
            "mode": "min",
            "nested": {
              "path": "offers"
            }
          }
        }
      ]
    }

A nested sort requires specifying the nested `path`. You can add a `filter` inside the nested sort if only qualifying offers should count—for instance, considering only prices of in-stock offers.

Standard Spring Data `Sort` does not express all nested sort options. For nested paths, filters, or complex modes, use the Elasticsearch Java API Client's native `SortOptions` and attach them to `NativeQuery`.

## 12. Costs and limits of nested

`nested` preserves accurate correlations, but comes with costs:

- Each nested object is indexed as a separate Lucene document in addition to the parent document.
- A document with many nested objects increases the Lucene document count.
- Updating part of a nested array usually requires reindexing the parent document together with its nested data.
- Nested queries, nested aggregations, and nested sorts are more complex than flat-field queries.
- The number of nested fields and nested objects is capped by Elasticsearch configuration limits.

If a product has a few dozen variants and frequently needs multi-field conditions on the same variant, `nested` can fit well. If a document has tens of thousands of nested objects and those objects change continuously, consider a different model.

Do not use `nested` solely because the JSON contains an array of objects. Use `nested` when preserving relationships between fields within the same element is an actual query requirement.

## 13. What is Parent-child?

Parent-child is a relationship between separate documents in the same Elasticsearch index. The mapping uses field type `join` to define relation names between parent and child types.

For example, a question with many answers:

    PUT qa
    {
      "mappings": {
        "properties": {
          "relation": {
            "type": "join",
            "relations": {
              "question": "answer"
            }
          },
          "title": {
            "type": "text"
          },
          "body": {
            "type": "text"
          }
        }
      }
    }

Parent document:

    PUT qa/_doc/q-1
    {
      "title": "How does nested query work?",
      "relation": "question"
    }

Child document:

    PUT qa/_doc/a-1?routing=q-1
    {
      "body": "A nested query scopes matching to one nested object.",
      "relation": {
        "name": "answer",
        "parent": "q-1"
      }
    }

Parent and child are separate documents with separate IDs, yet they must reside on the same shard. Therefore, when indexing a child, routing usually must use the parent's ID. Querying and deleting children also require proper routing so Elasticsearch hits the right shard.

A `join` field is not a general-purpose foreign key like in a relational database. It only supports parent-child relationships within the same index and carries join overhead at query time.

## 14. When does Parent-child fit?

Parent-child is useful when:

- Parent and child have relatively independent update lifecycles.
- A parent can have very many children.
- You need to query children independently or find parents based on child conditions.
- You want to avoid reindexing the entire parent whenever a child is added or edited.
- You need to keep parent and child as separate documents while still joining inside Elasticsearch.

Examples:

- A question with very many answers.
- An article with frequently added comments.
- A product with many independent reviews.
- An account with many events or child records updated individually.

Parent-child is not the default choice for every one-to-many relationship. Join queries cost considerably more than regular queries; if children are always read with the parent and updated infrequently, embedded or `nested` is usually simpler.

## 15. Routing and the same shard

Parent and child must reside on the same shard for Elasticsearch to execute joins. When indexing a child, routing must resolve to the same shard as the parent. Commonly, the parent ID is used as routing:

    PUT qa/_doc/a-2?routing=q-1
    {
      "body": "Another answer",
      "relation": {
        "name": "answer",
        "parent": "q-1"
      }
    }

If routing is forgotten, the child can be written to a different shard and the relationship will not work properly. Similarly, getting or deleting a child requires matching routing.

When using custom routing, maintain the exact same rule across all write and read paths. You can enforce required routing in the mapping or at the application layer to reduce the risk of omitting routing.

Having many children for a parent does not mean children are spread freely across the cluster. They concentrate on the parent's shard, which can cause imbalance if one parent has an enormous number of children.

## 16. has_child and has_parent queries

`has_child` finds parent documents based on conditions over their children:

    GET qa/_search
    {
      "query": {
        "has_child": {
          "type": "answer",
          "query": {
            "match": {
              "body": "nested query"
            }
          }
        }
      }
    }

The query returns `question` documents that have at least one `answer` matching `nested query`.

`has_parent` works in reverse: finding child documents based on conditions on their parent:

    GET qa/_search
    {
      "query": {
        "has_parent": {
          "parent_type": "question",
          "query": {
            "match": {
              "title": "nested query"
            }
          }
        }
      }
    }

The query returns `answer` documents belonging to `question`s with matching titles.

You can configure `score_mode` on `has_child` to decide how child scores affect the parent. With `has_parent`, you can configure whether the parent's score propagates to children as supported by the API. If you only need existence matching, there is no need to enable join scoring.

## 17. Parent-child in Spring Data Elasticsearch

Spring Data Elasticsearch supports `join` field mapping through dedicated join types and annotations, though exact signatures depend on the Spring Data version. Ensure the final mapping on the index has a field of type `join` and the proper relations per Elasticsearch's structure.

A JSON mapping example is the clearest reference for the structure:

    {
      "properties": {
        "relation": {
          "type": "join",
          "relations": {
            "question": "answer"
          }
        }
      }
    }

In the Java model, represent the join value containing the relation name and the parent ID for children. Spring Data provides the `JoinField` abstraction and `JoinType`/`JoinField` annotations in supported versions. Check your project dependency's actual API to declare properties, field names, relations, and parent values accurately.

Do not use a plain `String parentId` and expect Spring Data to turn it into a join relation automatically if the mapping is not configured. A `join` field has its own structure, and child documents require both parent ID and routing.

When writing parents and children with `ElasticsearchOperations` or a repository, verify that the final request carries the proper routing. If a repository abstraction does not expose routing for a specific use case, use `IndexQuery` or a Java API Client request with explicit routing.

## 18. NativeQuery for has_child and has_parent

Example `has_child` using the Elasticsearch Java API Client builder:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .hasChild(h -> h
                .type("answer")
                .query(childQuery -> childQuery
                    .match(m -> m
                        .field("body")
                        .query("nested query")
                    )
                )
                .scoreMode(ChildScoreMode.Max)
            )
        )
        .build();

Example `has_parent`:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .hasParent(h -> h
                .parentType("question")
                .query(parentQuery -> parentQuery
                    .match(m -> m
                        .field("title")
                        .query("nested query")
                    )
                )
                .score(true)
            )
        )
        .build();

The `ChildScoreMode` enum name and builder methods may vary across Java API Client versions. Inspect the generated API in your project's dependencies. These examples illustrate the structure: `has_child` specifies the child relation type; `has_parent` specifies the parent type and corresponding query.

Join queries require a valid `join` field mapping. Writing a `NativeQuery` alone without the proper `join` mapping and routing will not establish a parent-child relationship.

## 19. Costs and limits of parent-child

Parent-child allows updating documents independently, at the cost of join queries:

- `has_child` and `has_parent` are more expensive than standard queries.
- Joins execute within shard boundaries; routing affects data distribution.
- Many children for one parent concentrate on the same shard and can create hotspots.
- `join` fields add metadata and relationship management overhead.
- Parent-child relationships are only supported within the same index.
- A document can have only one parent in a given join relationship.
- `join` mappings can describe multi-level hierarchies, but deep trees make queries and operations more complex.

If an application frequently queries children and then displays parents, benchmark join queries against realistic data and shard counts. Do not choose parent-child merely to avoid updating a large document if join queries will run on almost every request.

## 20. What is application-level linking?

Another option is storing entities in separate indexes and keeping reference IDs in documents. Elasticsearch does not perform automatic joins across two indexes; the application service orchestrates queries and merges data.

Example:

Index `products`:

    {
      "productId": "p-100",
      "name": "Keyboard K8",
      "manufacturerId": "m-10"
    }

Index `manufacturers`:

    {
      "manufacturerId": "m-10",
      "name": "Keychron",
      "country": "China"
    }

When displaying a product alongside its manufacturer, the service:

1. Fetches the product.
2. Extracts `manufacturerId` from the result.
3. Fetches the manufacturer by ID.
4. Combines the data into a response DTO.

You can use repository `findById` or `findAllById` to load referenced data. When there are multiple IDs, batch them into a single multi-get or `terms` query instead of issuing one request per product.

### No automatic joins across indexes

Elasticsearch does not provide general-purpose joins between two indexes like SQL joins. A `manufacturerId` field on `product` is purely reference data. The application must look up the matching `manufacturer` document itself.

If you need to filter products by the manufacturer's `country`, you can:

- Denormalize `country` onto `product` for a single-pass query.
- Query `manufacturers` first to get IDs, then query `products` with `terms`.
- Use an external relational data store as the primary query source.
- Redesign documents to hold the data needed together for searching.

Each option has trade-offs in latency, consistency, and index size.

## 21. Application-level linking with a two-step query

Suppose you need to find products belonging to manufacturers in `China`:

Step 1, find manufacturer IDs:

    GET manufacturers/_search
    {
      "_source": false,
      "query": {
        "term": {
          "country": "China"
        }
      },
      "fields": [
        "manufacturerId"
      ],
      "size": 1000
    }

Step 2, find products by the ID list:

    GET products/_search
    {
      "query": {
        "terms": {
          "manufacturerId": [
            "m-10",
            "m-12",
            "m-18"
          ]
        }
      }
    }

In the application, IDs from step 1 are passed into the `terms` query in step 2. Cap the ID count and handle empty lists. If the number of matching manufacturers is large, the two-step approach can create a huge `terms` query and increase latency.

If you need to paginate or sort products by a manufacturer attribute, explicitly design which step owns pagination. Fetching a large batch of manufacturer IDs and then querying products does not automatically produce a globally sorted join.

## 22. Denormalization: copying data for fast search

Instead of joining on every request, the application can copy needed fields into the product document:

    {
      "productId": "p-100",
      "name": "Keyboard K8",
      "manufacturerId": "m-10",
      "manufacturerName": "Keychron",
      "manufacturerCountry": "China"
    }

Now you can find products by `manufacturerCountry` in a single query:

    GET products/_search
    {
      "query": {
        "term": {
          "manufacturerCountry": "China"
        }
      }
    }

Denormalization usually fits search engines well because it optimizes the read path: documents already contain the data queries need.

The downside is that when a manufacturer changes its name or country, many product documents may need updating. The application needs a sync mechanism:

- Update synchronously in the service if affected documents are few and suitable.
- Emit events when a manufacturer changes and update affected products.
- Use an outbox or message queue so events aren't lost.
- Accept eventual consistency with a defined lag window.
- Run backfill jobs when stale data needs repair.

There is no need to copy the entire manufacturer into every product. Only denormalize fields genuinely used for searching, filtering, sorting, or frequent display.

## 23. Comparing the four modeling approaches

| Criterion | Embedded object | Nested | Parent-child | Application-level linking |
|---|---|---|---|---|
| Data storage | Same parent document | Same parent document, nested Lucene docs | Separate documents, same index | Separate documents, often across different indexes |
| Preserves field relationships within one array element | No | Yes | Yes, per child document | Yes, within each referenced document |
| Related queries | Query object fields | `nested` query | `has_child`/`has_parent` | Multiple queries merged in service |
| Updating child data | Usually reindexes parent | Usually reindexes parent and nested data | Can update child independently | Updates related document independently |
| Joining parent and child | No join needed | `nested` query by path | Intra-shard join query | Application merges data |
| Very large child volume | Not ideal if unbounded | Requires caution | May be better suited | May be better suited |
| Query complexity | Low | Medium | Higher | Depends on service |
| Consistency | Single document write | Single document write | Multiple documents, requires relationship management | Multiple documents/indexes, requires sync |
| Best suited for | Simple child attributes | Object arrays needing correlation | Independent children needing intra-index joins | Independent entities, multi-source data, or app-controlled assembly |

## 24. Choosing a model by access pattern

Instead of starting from whether data has a one-to-many relationship, start from the most important queries.

### Reading parent with all children

If almost every read fetches the parent along with its children and child count is not huge, embedded objects are usually the simplest choice. If multiple conditions must match on the same element of an object array, choose `nested`.

### Finding parents by child attributes

If children are sub-objects in the same document and need multi-field same-element conditions, a `nested` query fits. If children are separate documents with independent lifecycles needing intra-index joins, consider parent-child.

### Updating children frequently and independently

Parent-child or application-level references can avoid reindexing the entire parent when one child changes. However, weigh join costs or the number of requests the application must execute.

### Querying across multiple data types or indexes

Application-level linking is more flexible because parent and child can reside in different indexes or come from external systems. If queries frequently filter/sort by referenced fields, denormalize those fields into the search document.

### Unbounded child data

Do not embed a list that can grow forever into a parent document. Large documents drive up update costs and can hit size or nested-object limits. Splitting children into separate documents is usually a better fit.

## 25. Update and delete lifecycles

The relationship model directly affects how the application updates data.

| Operation | Embedded/object | Nested | Parent-child | Application-level linking |
|---|---|---|---|---|
| Add child | Update/reindex parent | Update/reindex parent | Index child separately | Index referenced document separately |
| Edit child | Update parent | Update parent | Update child | Update child |
| Delete child | Update parent | Update parent | Delete child with routing | Delete child document |
| Delete parent | Delete single document | Delete parent and nested data together | Requires policy to delete related children | Requires handling references/orphans |
| Sync multiple copies | No, if data lives only in parent | No, if data lives only in parent | Manage relationships and routing | Manage events, backfills, or eventual consistency |

With parent-child, deleting a parent should not be assumed to automatically delete all children in every scenario. Design an explicit deletion operation using parent/routing queries or an appropriate cleanup workflow.

With application-level references, when deleting a manufacturer, products might retain a `manufacturerId` that no longer exists. Choose a policy: delete products, keep references for audit, mark the manufacturer inactive, or update denormalized data.

## 26. Consistency and transactions

Elasticsearch is not a relational database with multi-document transactions equivalent to SQL. When updating parents and children separately, or updating source data alongside denormalized copies, there can be a window where data is not yet synchronized.

Common strategies:

- **Single document:** embed data read together so it updates in a single write.
- **Eventual consistency:** emit events and update related documents afterward.
- **Outbox pattern:** write changes and events to a transactional data store, then publish events to update Elasticsearch.
- **Versions or timestamps:** keep source version info to detect stale copies.
- **Idempotent updates:** process duplicate events without producing invalid state.
- **Reconciliation jobs:** periodically compare source and index to repair drift.

If the application requires strong transactional consistency across multiple entities, consider keeping the system of record in a relational database or transactional store, with Elasticsearch serving search projections updated from that source.

## 27. Routing and data distribution

Routing is especially important for parent-child because parent and child must share a shard. For application-level references across separate indexes, there is no intra-shard join requirement, though you can still route by tenant or business key to optimize queries.

Custom routing carries benefits and risks:

- Queries with routing can reduce the number of shards searched.
- A very large tenant or parent can create a shard hotspot.
- Routing must be supplied consistently on index, get, update, and delete.
- If an alias points to multiple indexes, ensure routing semantics are compatible across all indexes.

Do not pick routing based on a single example query. Examine data distribution, tenant sizes, child counts per parent, and concurrency.

## 28. Security and tenant isolation

Relationship models do not provide authorization on their own. If a parent document belongs to tenant A, child or embedded data must also be queried within that tenant's scope.

Some principles:

- Apply tenant filters on both parent queries and independent child queries.
- Never trust a client-supplied parent ID to bypass permission checks.
- For parent-child, verify routing and parent relations from trusted data.
- For application-level references, authorize both the referencing document and the target document.
- If `tenantId` is denormalized, update it synchronously when relationships change.
- Verify `inner_hits` and aggregations do not leak data from other tenants.

A `nested` query returning parent documents can include nested `inner_hits`. Ensure filters apply at the right scope and `inner_hits` never exposes unauthorized data.

## 29. Spring Data code pattern for application-level references

Example `Product` entity storing `manufacturerId`:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String id;

        private String name;
        private String manufacturerId;
    }

`Manufacturer` entity:

    @Document(indexName = "manufacturers")
    public class Manufacturer {

        @Id
        private String id;

        private String name;
        private String country;
    }

Service combining the data:

    @Service
    public class ProductCatalogService {

        private final ProductRepository productRepository;
        private final ManufacturerRepository manufacturerRepository;

        public ProductCatalogService(
                ProductRepository productRepository,
                ManufacturerRepository manufacturerRepository) {
            this.productRepository = productRepository;
            this.manufacturerRepository = manufacturerRepository;
        }

        public ProductView getProduct(String productId) {
            Product product = productRepository.findById(productId)
                .orElseThrow();

            Manufacturer manufacturer =
                manufacturerRepository.findById(product.getManufacturerId())
                    .orElse(null);

            return new ProductView(product, manufacturer);
        }
    }

This is straightforward for a single product. When fetching many products, do not call `findById` for each manufacturer because that causes N+1 requests. Collect unique IDs and use `findAllById` or an appropriate multi-get:

    List<Product> products = productRepository.findAllById(productIds);

    Set<String> manufacturerIds = products.stream()
        .map(Product::getManufacturerId)
        .filter(Objects::nonNull)
        .collect(Collectors.toSet());

    Map<String, Manufacturer> manufacturers =
        StreamSupport.stream(
            manufacturerRepository.findAllById(manufacturerIds).spliterator(),
            false
        ).collect(Collectors.toMap(
            Manufacturer::getId,
            Function.identity()
        ));

The service then pairs each product with its matching manufacturer. Repository return types and multi-get optimizations depend on the interface used, but the rule is batching reference lookups rather than fetching one document at a time.

## 30. Choosing when filtering by related data is needed

A pivotal decision is whether the application needs to find parents by child attributes or referenced entity attributes.

| Need | Usually suitable model |
|---|---|
| Filter by a simple field inside an embedded object | `Object` |
| Filter multiple fields that must belong to the same array element | `Nested` |
| Find parents whose children match conditions | Parent-child or `nested` depending on data lifecycle |
| Find children whose parent matches conditions | Parent-child |
| Filter products by manufacturer's country | Denormalize `country` or two-step query |
| Display manufacturer when reading a product | Application-level reference or denormalization |
| Children change independently and frequently | Parent-child or application-level reference |
| Relationships span multiple indexes/systems | Application-level reference |

If a related attribute appears frequently in filters, sorts, or relevance scoring, denormalizing that field into the search document can greatly simplify queries.

## 31. Common mistakes

### Using an object array when same-element conditions are required

Standard object arrays do not preserve relationships between individual element fields at index time. If `seller` and `price` must belong to the same offer, use a `nested` query on a `nested` mapping.

### Thinking nested is an independent document

Nested objects are indexed separately at the Lucene level, yet still belong to the parent document. They do not have independent lifecycles and IDs like parent-child child documents.

### Running a nested query on an object mapping

`nested` queries only work on fields mapped with type `nested`. Switching requires creating a new index and reindexing data when the field was previously `object`.

### Forgetting the nested path

Nested queries, aggregations, and sorts require the right `path`. A dotted field name does not automatically turn a query into a `nested` query.

### Splitting conditions across multiple nested queries when the same element is needed

Two separate `nested` queries can match two different nested objects. Place conditions that must hold simultaneously inside the same `nested` query.

### Using nested for very large, frequently updated lists

Nested objects live inside the parent document; updating one element typically requires reindexing the parent document. For numerous independent children, consider parent-child or application-level references.

### Using parent-child for every one-to-many relationship

Join queries carry overhead and routing complexity. If children are always read with the parent, embedded or `nested` is usually simpler.

### Forgetting child routing

Parent and child must share the same shard. Index children using parent-ID routing and keep the same rule for `get`, `update`, and `delete`.

### Expecting a join field to link two indexes

A `join` field only supports parent-child relationships within the same index. Cross-index links require denormalization or application-level lookups.

### Creating N+1 requests when resolving references

When loading multiple parents, collect IDs and batch-lookup referenced documents. Avoid calling a repository once per document.

### Denormalizing without a synchronization mechanism

When source data changes, copies in the index can go stale. You need events, an outbox, backfills, or reconciliation jobs.

### Assuming Elasticsearch has multi-document transactions

Writing parents, children, and denormalized copies involves separate operations. Design retries, idempotency, and eventual consistency where needed.

## 32. Workflow for selecting a relationship model

You can follow this process when designing documents:

1. Determine whether child data is always read alongside the parent.
2. Determine whether query conditions must match on the same array element.
3. If per-element field correlation is unnecessary in an object array, use `object`.
4. If per-element correlation is needed and child data is tightly tied to the parent, use `nested`.
5. If children are separate documents updated independently and need intra-index joins, evaluate parent-child.
6. If data spans multiple indexes/systems or the app wants full control over assembly, use application-level references.
7. If queries/filters/sorts frequently need a referenced field, consider denormalizing the needed fields.
8. Evaluate child counts, update frequency, document sizes, and shard distribution.
9. Design routing, cleanup, synchronization, and orphan handling.
10. Write representative queries and benchmark on near-production data.

## Conclusion

Embedded objects fit simple child data read together with the parent without needing multi-field correlation per array element. `nested` preserves individual child object boundaries—enabling accurate `nested` queries, aggregations, sorts, and `inner_hits`—though nested data remains tied to the parent document and raises indexing/update costs. Parent-child stores parents and children as separate documents in the same index, supporting independent updates and join queries, while requiring same-shard routing and higher query costs. Application-level linking uses reference IDs with batched lookups and service-layer assembly, offering flexibility across multiple indexes while requiring the service to manage request counts and consistency.

In Spring Data Elasticsearch, `object` and `nested` are typically represented with `FieldType.Object` and `FieldType.Nested`; parent-child requires a `join` field mapping along with relation/parent values and accurate routing; application-level references are usually ID fields paired with repository or `ElasticsearchOperations` lookups. Choose based on access patterns, update frequency, child counts, and query needs. When related data is frequently used for filtering or sorting, denormalizing the necessary fields can make searching much simpler, provided the application has a clear synchronization process.
