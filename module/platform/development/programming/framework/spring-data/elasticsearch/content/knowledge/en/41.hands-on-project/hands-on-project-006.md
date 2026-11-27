# Modeling Product Attributes with Nested Queries

A product often has multiple attributes, variants, or selling options. For example, a shirt has combinations of color and size; a laptop has multiple RAM/SSD configurations; a product is offered by multiple sellers with distinct prices and stock counts. When values relate to one another, the Elasticsearch mapping must preserve that relationship so queries do not accidentally mix fields from different elements.

Elasticsearch provides two key object types:

- Regular object: child fields are flattened at index time. Suitable when querying fields individually without needing to preserve relationships across elements in an array of objects.
- Nested: each object element is indexed as a separate nested Lucene document linked to its parent. A nested query ensures multiple conditions are evaluated against the same object element.

When products have variants, nested is usually right if users ask for a specific combination like "black, size L, in stock." With a regular object mapping, Elasticsearch can match black on the first variant and size L on the second variant, even though no single variant satisfies both conditions.

This lesson walks through document design, Spring Data Elasticsearch mappings, nested queries, inner_hits, sorting, and aggregations, as well as performance cost, testing, and common pitfalls.

## 1. The Product Attribute Problem

Suppose a product has multiple variants:

    {
      "productId": "shirt-100",
      "name": "Classic Shirt",
      "brand": "Northwind",
      "variants": [
        {
          "sku": "shirt-100-black-m",
          "color": "black",
          "size": "M",
          "price": 29.9,
          "stock": 0
        },
        {
          "sku": "shirt-100-blue-l",
          "color": "blue",
          "size": "L",
          "price": 31.9,
          "stock": 12
        }
      ]
    }

A user searches for a product with a variant that is black, size L, and in stock. With the data above, no such variant exists:

- The first variant has color=black, but size=M and stock=0.
- The second variant has size=L and stock=12, but color=blue.

If the query checks each field independently without preserving their correlation, the product will be returned erroneously.

## 2. Regular Objects Flatten Arrays of Objects

If variants is mapped as a regular object, Elasticsearch indexes field values as independent sets. Conceptually, the document looks like:

    variants.color = ["black", "blue"]
    variants.size  = ["M", "L"]
    variants.stock = [0, 12]

The link between black and M, and between blue and L, is lost for query correlation purposes.

Query:

    GET products/_search
    {
      "query": {
        "bool": {
          "filter": [
            { "term": { "variants.color": "black" } },
            { "term": { "variants.size": "L" } },
            { "range": { "variants.stock": { "gt": 0 } } }
          ]
        }
      }
    }

This can match the document even though no single variant satisfies all three conditions. Each filter can be satisfied by a different array element.

This is the classic object-array correlation bug. Whenever business logic requires conditions to hold on the same variant, use nested.

## 3. Nested Preserves Relationships Between Objects

When a field is mapped as nested, every element in the array is indexed as its own separate nested document associated with the parent document.

Example mapping:

    PUT products
    {
      "mappings": {
        "properties": {
          "productId": {
            "type": "keyword"
          },
          "name": {
            "type": "text"
          },
          "brand": {
            "type": "keyword"
          },
          "variants": {
            "type": "nested",
            "properties": {
              "sku": {
                "type": "keyword"
              },
              "color": {
                "type": "keyword"
              },
              "size": {
                "type": "keyword"
              },
              "price": {
                "type": "double"
              },
              "stock": {
                "type": "integer"
              }
            }
          }
        }
      }
    }

A nested query evaluates against nested documents at the specified path and returns parent documents that have at least one matching nested object.

## 4. Nested Query for a Single Variant

Querying for black, size L, and in stock:

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "variants",
          "query": {
            "bool": {
              "filter": [
                { "term": { "variants.color": "black" } },
                { "term": { "variants.size": "L" } },
                { "range": { "variants.stock": { "gt": 0 } } }
              ]
            }
          }
        }
      }
    }

Because all conditions are inside the same nested query, they must be satisfied by the same element of variants. For the sample document, the product will not match.

Only if we add the variant:

    {
      "sku": "shirt-100-black-l",
      "color": "black",
      "size": "L",
      "price": 32.9,
      "stock": 5
    }

will the product match.

## 5. Multiple Nested Queries Mean Elements Can Differ

If the query contains two separate nested clauses:

    {
      "bool": {
        "filter": [
          {
            "nested": {
              "path": "variants",
              "query": {
                "term": {
                  "variants.color": "black"
                }
              }
            }
          },
          {
            "nested": {
              "path": "variants",
              "query": {
                "term": {
                  "variants.size": "L"
                }
              }
            }
          }
        ]
      }
    }

The two nested clauses can be satisfied by two different variants. That is right only if business rules merely ask for a product that has at least one black variant and at least one size-L variant, even if they are not the same variant.

If business rules require one variant to be both black and size L, put both conditions inside the same nested query.

## 6. When to Use Object, Nested, or Flattened?

| Type | Preserves object-array correlation? | Suitable cases |
|---|---|---|
| object | No | Child fields queried independently |
| nested | Yes | Fields of the same element must match together |
| flattened | Does not preserve object correlation | Maps with many dynamic keys, mostly exact lookups |

Do not convert every object into nested. Nested carries higher indexing, storage, and query overhead because every nested element creates an internal Lucene document.

Use nested when attribute correlation is part of the business semantics. If you only filter on independent values, regular objects are simpler and lighter.

Flattened is useful for maps with dynamic keys and many variable attributes, but it does not replace nested when correlation across fields within the same object is required.

## 7. Modeling Dynamic Key/Value Attributes

Some catalogs have attributes that vary by category:

    {
      "productId": "laptop-100",
      "attributes": [
        {
          "name": "ramGb",
          "valueKeyword": "16",
          "valueNumber": 16
        },
        {
          "name": "storageType",
          "valueKeyword": "SSD"
        },
        {
          "name": "color",
          "valueKeyword": "silver"
        }
      ]
    }

If you need to guarantee name and value belong to the same attribute entry, map attributes as nested:

    "attributes": {
      "type": "nested",
      "properties": {
        "name": {
          "type": "keyword"
        },
        "valueKeyword": {
          "type": "keyword"
        },
        "valueNumber": {
          "type": "double"
        }
      }
    }

Querying for laptops with 16 GB RAM:

    {
      "nested": {
        "path": "attributes",
        "query": {
          "bool": {
            "filter": [
              { "term": { "attributes.name": "ramGb" } },
              { "term": { "attributes.valueNumber": 16 } }
            ]
          }
        }
      }
    }

When values span multiple types, never store everything as text and attempt range queries on strings. Use typed fields such as valueNumber, valueDate, valueBoolean, or domain-specific attribute models.

## 8. Combining Variants and Attributes Models

A product can have variants, each with its own attributes:

    {
      "productId": "laptop-200",
      "variants": [
        {
          "sku": "lap-200-silver-16",
          "attributes": [
            { "name": "color", "valueKeyword": "silver" },
            { "name": "ramGb", "valueNumber": 16 }
          ],
          "price": 1200,
          "stock": 8
        }
      ]
    }

The mapping can use nested at both levels:

    "variants": {
      "type": "nested",
      "properties": {
        "sku": { "type": "keyword" },
        "price": { "type": "double" },
        "stock": { "type": "integer" },
        "attributes": {
          "type": "nested",
          "properties": {
            "name": { "type": "keyword" },
            "valueKeyword": { "type": "keyword" },
            "valueNumber": { "type": "double" }
          }
        }
      }
    }

Multi-level nested queries must specify the path at each level. This is powerful but adds cost and complexity. Use it only when correlation must be preserved at both levels.

## 9. Mapping with Spring Data Elasticsearch

An entity can declare a nested field using FieldType.Nested:

    @Document(indexName = "products")
    public class Product {

        @Id
        private String productId;

        @Field(type = FieldType.Text)
        private String name;

        @Field(type = FieldType.Keyword)
        private String brand;

        @Field(type = FieldType.Nested)
        private List<ProductVariant> variants;
    }

    public class ProductVariant {

        @Field(type = FieldType.Keyword)
        private String sku;

        @Field(type = FieldType.Keyword)
        private String color;

        @Field(type = FieldType.Keyword)
        private String size;

        @Field(type = FieldType.Double)
        private Double price;

        @Field(type = FieldType.Integer)
        private Integer stock;
    }

Enum names and annotation attributes depend on the Spring Data Elasticsearch version. You can manage mappings via JSON or index templates if advanced settings are needed. What matters is that the actual Elasticsearch mapping declares variants as nested; simply declaring a Java List does not guarantee nested semantics if the underlying index mapping is wrong.

## 10. Creating the Index and Verifying the Mapping

In a Spring Data application, you can use IndexOperations to check or create the index from entity metadata:

    IndexOperations indexOps =
        operations.indexOps(Product.class);

    if (!indexOps.exists()) {
        indexOps.create();
        indexOps.putMapping();
    }

Method names and mapping creation behavior depend on version. In real deployments, mappings are usually managed via migrations or index templates rather than ad-hoc creation on application startup.

Inspect the mapping from Elasticsearch:

    GET products/_mapping

Confirm:

- variants has type nested.
- color and size are keyword if used in term filters.
- price is numeric if used for ranges/sorting.
- stock is an appropriate integer/long.
- Field names in queries match the mapping.

If the mapping was previously created with variants as a regular object, changing annotations alone will not turn the old index into nested. Create a new index and reindex the data.

## 11. NativeQuery with Nested Queries

Spring Data Elasticsearch supports NativeQuery to express Elasticsearch Query DSL. A general example:

    NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q
            .nested(n -> n
                .path("variants")
                .query(nq -> nq
                    .bool(b -> b
                        .filter(f -> f
                            .term(t -> t
                                .field("variants.color")
                                .value("black")
                            )
                        )
                        .filter(f -> f
                            .term(t -> t
                                .field("variants.size")
                                .value("L")
                            )
                        )
                        .filter(f -> f
                            .range(r -> r
                                .number(nr -> nr
                                    .field("variants.stock")
                                    .gt(0.0)
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

This illustrates the Java API Client builder style used in modern Spring Data releases. Builder signatures, numeric range types, and imports can vary by version. If the IDE rejects a builder call, check the client API managed by Spring Data and write the query using that exact version.

The essential requirement is that the emitted Query DSL uses nested path variants with all three filters inside that sub-query.

## 12. Criteria API and Nested Semantics

The Criteria API can be handy for simple queries, but do not assume that writing:

    Criteria.where("variants.color").is("black")
        .and("variants.size").is("L")

will automatically produce a nested query with the correlation behavior you expect.

Nested mapping and nested querying are related but separate concerns. The query itself must emit proper nested DSL. For complex queries, NativeQuery or the Java API Client usually gives clearer control over semantics.

Verify the actual emitted request in integration tests or redacted request logs. Never conclude semantics are right solely because Java code compiles.

## 13. Combining Nested Queries with Parent Filters

Products usually have parent-level fields like brand, category, tenant, and status alongside nested variant fields like color, size, price, and stock.

A query can combine both:

    GET products/_search
    {
      "query": {
        "bool": {
          "filter": [
            { "term": { "brand": "Northwind" } },
            { "term": { "category": "shirts" } },
            { "term": { "status": "ACTIVE" } },
            {
              "nested": {
                "path": "variants",
                "query": {
                  "bool": {
                    "filter": [
                      { "term": { "variants.color": "black" } },
                      { "term": { "variants.size": "L" } },
                      { "range": { "variants.stock": { "gt": 0 } } }
                    ]
                  }
                }
              }
            }
          ]
        }
      }
    }

Parent filters determine eligible products. The nested filter checks whether at least one variant satisfies the attribute combination.

## 14. Nested Queries with Multiple OR Choices

Suppose a user accepts black or blue, as long as size is L and stock is available:

    {
      "nested": {
        "path": "variants",
        "query": {
          "bool": {
            "filter": [
              {
                "terms": {
                  "variants.color": ["black", "blue"]
                }
              },
              { "term": { "variants.size": "L" } },
              { "range": { "variants.stock": { "gt": 0 } } }
            ]
          }
        }
      }
    }

A terms query applies OR across values of the same field. Filters in bool.filter combine with AND. All conditions are still evaluated on the same nested object.

If OR logic is needed across multiple complex condition groups, use bool.should and set minimum_should_match explicitly.

## 15. Nested Queries and score_mode

A nested query can compute the parent's score from the scores of matching nested documents. score_mode controls how they combine:

- avg: average score of matching nested documents.
- max: highest score.
- min: lowest score.
- sum: sum of scores.
- none: do not propagate nested scores to the parent.

For attribute filtering on products, usually use filter context or score_mode none because matching a variant determines eligibility rather than relevance ranking.

If a nested query appears in should to influence ranking, choose score_mode based on business meaning and measure its effect.

## 16. Retrieving Matching Variants with inner_hits

By default, a nested query returns the parent product. If the UI needs to know which variants matched, use inner_hits:

    GET products/_search
    {
      "query": {
        "nested": {
          "path": "variants",
          "query": {
            "bool": {
              "filter": [
                { "term": { "variants.color": "black" } },
                { "term": { "variants.size": "L" } },
                { "range": { "variants.stock": { "gt": 0 } } }
              ]
            }
          },
          "inner_hits": {
            "name": "matching_variants",
            "size": 5
          }
        }
      }
    }

The response includes an inner_hits section containing the matching nested documents, giving the application the SKU, price, and stock of matching variants.

inner_hits is useful for:

- Displaying matching variants.
- Explaining why a product was returned.
- Grabbing a specific SKU for add-to-cart actions.
- Avoiding loading all variants and re-filtering them in Java.

Cap inner_hits size. If a parent has thousands of nested children, returning all of them inflates responses and memory usage.

## 17. Reading inner_hits in Spring Data

Spring Data SearchHit can expose inner hits depending on version and mapping approach. Java API Client response structures carry an innerHits map keyed by the assigned name.

When integrating:

- Check the return type exposed by SearchHit.
- Read inner hits by the key matching_variants.
- Map nested sources into ProductVariant DTOs.
- Do not assume the parent's content has been trimmed to only matching nested objects.

The parent Product usually still contains all variants in its source. inner_hits is a separate result section for nested matches.

If only matching variants are needed, map inner_hits into the response DTO and omit the full variants array.

## 18. Nested Sort

A product has multiple variant prices. If you want to sort products by the lowest price among in-stock variants, use a nested sort with a filter.

Example:

    GET products/_search
    {
      "sort": [
        {
          "variants.price": {
            "order": "asc",
            "mode": "min",
            "nested": {
              "path": "variants",
              "filter": {
                "range": {
                  "variants.stock": {
                    "gt": 0
                  }
                }
              }
            }
          }
        }
      ],
      "query": {
        "match_all": {}
      }
    }

A nested sort requires path and may include a filter so only eligible variants are considered. Without the filter, a product might be sorted by an out-of-stock variant with a lower price.

Modes such as min, max, avg, sum, or median may be supported depending on field type and API. Pick the mode matching business semantics.

## 19. Combining Nested Sort with Nested Queries

If the query requires in-stock variants but the sort omits a matching nested filter, the sort may evaluate a different set of nested values than the query matched depending on configuration.

To ensure sorting considers the exact same eligible variants, replicate the relevant eligibility conditions in the nested sort filter:

- stock > 0.
- status = ACTIVE.
- color/size if sorting only over selected variants.

Never assume nested sort automatically inherits conditions from the nested query. Inspect both the DSL and actual results.

## 20. Nested Aggregations

To count variants by color, use a nested aggregation to enter the nested documents scope:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "variants_scope": {
          "nested": {
            "path": "variants"
          },
          "aggs": {
            "by_color": {
              "terms": {
                "field": "variants.color"
              }
            }
          }
        }
      }
    }

A nested aggregation counts nested documents, not parent products. A single product with multiple variants of the same color contributes multiple bucket documents.

To return to the parent scope and count distinct products, use a reverse_nested aggregation.

## 21. Reverse Nested Aggregations

Example counting how many products have variants of each color:

    GET products/_search
    {
      "size": 0,
      "aggs": {
        "variants_scope": {
          "nested": {
            "path": "variants"
          },
          "aggs": {
            "by_color": {
              "terms": {
                "field": "variants.color"
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

Inside each color bucket:

- doc_count of the bucket is the number of nested variant documents.
- parent_products.doc_count is the number of associated parent products.

Those two numbers differ whenever one product has multiple variants of the same color.

## 22. Nested Queries with must_not

Negating a nested query requires extra care.

To find products that have no red variants, place the nested query inside bool.must_not at the parent level:

    GET products/_search
    {
      "query": {
        "bool": {
          "must_not": [
            {
              "nested": {
                "path": "variants",
                "query": {
                  "term": {
                    "variants.color": "red"
                  }
                }
              }
            }
          ]
        }
      }
    }

This excludes the parent if at least one red nested variant exists.

Putting must_not inside the nested query instead asks for a nested variant that is not red; the parent can still match via another variant. That is not equivalent to "parent has no red variants at all."

Always write tests for negation and empty nested arrays.

## 23. Nested Queries and Missing/Null Values

A nested field may:

- Not exist.
- Be an empty array.
- Contain objects missing a child field.
- Have a null child field.
- Contain empty string values.

These cases are not necessarily equivalent in Elasticsearch. An exists query checks whether a field has indexed values, not merely whether the key is present in JSON.

Example finding variants that have a stock field:

    {
      "nested": {
        "path": "variants",
        "query": {
          "exists": {
            "field": "variants.stock"
          }
        }
      }
    }

If business rules treat missing stock as 0, normalize the data before indexing or represent the state explicitly. Do not rely on null semantics as a substitute for business defaults.

## 24. Nested Queries and Access Control Filters

Some systems enforce ACLs at the variant, offer, or inventory-source level. In those cases, a nested filter is required to keep principal, permission, and variant correlated.

Example:

    "offers": [
      {
        "sellerId": "seller-a",
        "region": "VN",
        "status": "ACTIVE",
        "price": 100
      },
      {
        "sellerId": "seller-b",
        "region": "SG",
        "status": "ACTIVE",
        "price": 90
      }
    ]

If you need an offer in region VN provided by seller A, both conditions must live inside the same nested query on path offers. Putting region and seller in two separate nested clauses can match two different offers.

Security filters must always be constructed from a trusted principal and backend policy. Never allow clients to pass arbitrary seller/tenant filters to bypass access control.

## 25. Combining Nested Queries with Vector Search

A product may store a vector on the parent while nested variants carry filterable attributes. For semantic queries, you can combine kNN retrieval with a nested variant filter, depending on the Elasticsearch version and API.

Conceptual example:

    {
      "knn": {
        "field": "embedding",
        "query_vector": [ ... ],
        "k": 20,
        "num_candidates": 200,
        "filter": {
          "nested": {
            "path": "variants",
            "query": {
              "bool": {
                "filter": [
                  { "term": { "variants.color": "black" } },
                  { "term": { "variants.size": "L" } },
                  { "range": { "variants.stock": { "gt": 0 } } }
                ]
              }
            }
          }
        }
      }
    }

This illustrates the structure. Support for nested filters inside kNN, nested vector fields, and filter placement depends on the Elasticsearch version and API. Consult the server reference and test real requests.

If vectors live inside nested objects instead of the parent, queries must use appropriate nested kNN semantics. Do not assume querying a vector field on the parent automatically searches vectors inside nested children.

## 26. Multi-Level Nested

When a nested object contains another nested object, queries must nest the nested paths:

    {
      "nested": {
        "path": "variants",
        "query": {
          "nested": {
            "path": "variants.attributes",
            "query": {
              "bool": {
                "filter": [
                  { "term": { "variants.attributes.name": "color" } },
                  { "term": { "variants.attributes.valueKeyword": "black" } }
                ]
              }
            }
          }
        }
      }
    }

Child nested paths are evaluated within the context of the parent nested path. Deep structures make queries harder to read and can add considerable overhead.

If only a few fixed attributes exist, direct fields on the variant are usually simpler than dynamic nested attributes.

## 27. Nested Limits and Costs

Nested creates additional internal Lucene documents. One parent with 50 nested children produces far more Lucene documents than the count of product records alone.

Costs:

- Increased index size.
- Higher CPU cost for indexing and updates.
- Queries must join nested children back to parents.
- Nested aggregations do extra work.
- Inner hits enlarge responses.
- Segment merges and recovery must process nested docs.

Elasticsearch configures limits on the number of nested fields and nested objects per document. Setting names and defaults can vary by version. Check your cluster's active limits before indexing documents with very large nested arrays.

Never use nested for an array with tens of thousands of elements without benchmarking. If storing large histories or huge child collections, consider splitting children into a separate index linked by ID.

## 28. Updating Nested Objects

Nested documents are bound to their parent. Updating a single nested child generally requires Elasticsearch to reindex the parent document along with its nested structure as part of the document update.

If a product has thousands of variants and only one variant's stock changes frequently, updating the parent repeatedly can become expensive.

Modeling alternatives:

- Nested: fits when query correlation is required and child counts are moderate.
- Separate child documents/index: fits when children update independently and counts are large, at the cost of more complex queries/joins.
- Denormalized product projections: fits when event-driven projection updates are acceptable.

Choose based on update frequency, child counts, query patterns, and consistency requirements.

## 29. Partial Updates and Nested Arrays

Partially updating a single field in a nested child is not as simple as updating a relational row by child ID because nested children do not have independent document IDs in standard document APIs.

Options:

- Read the parent, update the nested list, and reindex the parent.
- Use a scripted update on the parent source to modify the matching element, if logic and performance are acceptable.
- Split children into separate documents if independent updates are essential.

Scripted updates must handle missing children, duplicate keys, and concurrent updates. For frequent updates, benchmark thoroughly and use optimistic concurrency control.

## 30. Idempotency When Syncing Nested Data

When syncing products from a database, events may be delivered multiple times. Use stable parent IDs and stable variant keys:

    productId = "shirt-100"
    variant.sku = "shirt-100-black-l"

Consumers should build projections deterministically from the source of truth instead of appending a nested item on every incoming event. Blindly appending creates duplicate variants on redelivery.

When modifying variants:

- Rebuild the list from the current source state when appropriate.
- Or apply idempotent updates/scripts keyed by SKU.
- Track source version to ignore stale events.
- Handle deletes/tombstones for discontinued variants.

## 31. Nested Mappings and Dynamic Attributes

If categories have thousands of distinct attribute names, mapping a separate field for every name causes mapping explosion.

A nested key/value model avoids creating dynamic fields for each attribute:

    attributes:
      - name: ramGb
        valueNumber: 16
      - name: color
        valueKeyword: silver

However, nested still creates a nested document per attribute entry. If attribute counts are huge or correlation is unnecessary, flattened may be more economical.

Use typed value fields so range queries work with proper types. Using a single generic text value field makes numeric sorting and range semantics difficult to control.

## 32. Nested Queries Across Multiple Indices

An alias can point to multiple index versions. If one index maps variants as nested while another maps variants as a regular object or lacks the field, queries may error or return inconsistent results.

Before querying nested across an alias:

- Inspect mappings of every index.
- Keep nested paths compatible.
- Use ignore_unmapped where supported by the API.
- Never use ignore_unmapped to hide an incomplete mapping migration.
- Switch the alias only after validating the new index.

Nested mappings cannot be changed arbitrarily in place; you normally need a new index and reindexing.

## 33. Nested Queries with Sorting and Pagination

When sorting by nested price, pagination needs stable ordering. If multiple products share the same price, add a tie-breaker such as productId to keep page ordering deterministic.

Example:

    "sort": [
      {
        "variants.price": {
          "order": "asc",
          "mode": "min",
          "nested": {
            "path": "variants",
            "filter": {
              "range": {
                "variants.stock": {
                  "gt": 0
                }
              }
            }
          }
        }
      },
      {
        "productId": {
          "order": "asc"
        }
      }
    ]

For deep pagination, consider PIT and search_after instead of large from/size values. Sort values must remain consistent across pages.

## 34. Testing Against Object-Flattening False Positives

A critical integration test should seed two variants where neither satisfies all conditions:

    Product product = product(
        variant("black", "M", 0),
        variant("blue", "L", 12)
    );

After indexing and refreshing, a query for black + L + stock > 0 must not return the product.

Then add a variant with black + L + stock 5, reindex, and verify the query returns the product.

This test proves nested semantics actually work. Checking that the JSON mapping shows type nested is not enough; verify query behavior on data engineered to trigger false positives.

## 35. Testing inner_hits

Create a product with multiple variants where only one matches. Run the nested query with inner_hits and verify:

- The parent product is returned.
- inner_hits contains only the matching variant.
- SKU, color, size, and stock are accurate.
- Non-matching variants do not appear in inner_hits.
- The response DTO does not accidentally leak the full nested source if not desired.

If using Spring Data SearchHit, verify how your version exposes the inner-hit map and performs conversion.

## 36. Testing Nested Sort

Create two products:

- Product A has an in-stock variant priced at 120 and an out-of-stock variant priced at 50.
- Product B has an in-stock variant priced at 90.

When sorting by lowest price among in-stock variants, Product B must rank before Product A. If the sort omits the nested filter, Product A would rank first because of its out-of-stock 50 variant.

This test confirms the nested sort filter enforces business eligibility.

## 37. Testing Nested Aggregations

Create one product with multiple variants of the same color and another product with a variant of that color. Verify:

- Nested bucket count reflects the number of variants.
- Reverse nested count reflects the number of parent products.
- A product with multiple variants of the same color is not counted as multiple products when using the parent count.

This catches a common dashboard bug where "products by color" accidentally displays nested variant counts.

## 38. Testing with Spring Data Elasticsearch

An integration test can use ElasticsearchOperations:

    @Test
    void nestedQueryMatchesOneVariantAsAWhole() {
        Product product = new Product();
        product.setProductId("shirt-test-1");
        product.setName("Classic Shirt");
        product.setVariants(List.of(
            variant("black", "M", 0),
            variant("blue", "L", 12)
        ));

        operations.save(product);
        operations.indexOps(Product.class).refresh();

        NativeQuery query = buildBlackLargeInStockQuery();

        SearchHits<Product> hits =
            operations.search(query, Product.class);

        assertThat(hits.getSearchHits())
            .extracting(hit -> hit.getId())
            .doesNotContain("shirt-test-1");
    }

This is an illustrative example. Query builders and refresh APIs depend on the Spring Data version. Tests must run against an actual index mapping where variants is mapped as nested.

## 39. Testing Mappings and Index Lifecycle

Test setup should create the index with the right mapping. If reusing an existing index from a previous run that had an object mapping, new annotations will not fix the mapping.

A clean lifecycle:

1. Create a fresh test index.
2. Apply the mapping.
3. Index fixtures.
4. Refresh before searching.
5. Run nested queries, sorts, and aggregations.
6. Assert results.
7. Delete the test index.

Never delete shared indices across test suites or developer environments. Use an isolated index name per test run.

## 40. Common Pitfalls

### Using Object Arrays When Correlation Is Required

Fields from different elements can combine into false matches. Use nested queries when conditions must belong to the same object.

### Writing Separate Nested Queries When the Same Variant Must Match

Separate nested clauses can match different elements. Put conditions for the same variant inside one nested query.

### Assuming a Java List Automatically Creates a Nested Mapping

A List in the entity does not guarantee nested mapping. Verify the actual Elasticsearch mapping.

### Changing Annotations While Reusing an Old Index

Old mappings do not change from object to nested automatically. Create a new index and reindex.

### Using Nested for Every Object

Nested increases Lucene document counts and query overhead. Use it only when correlation must be preserved.

### Querying Child Fields Without a Nested Path

Regular term queries do not substitute for nested queries. Use a nested query with the right path.

### Sorting by a Nested Field Without a Nested Filter

Sorting may pick ineligible variants, such as out-of-stock ones. Add a nested sort filter.

### Reading Nested Aggregation doc_count as Product Count

doc_count in nested scope counts nested documents. Use reverse_nested to return to parent scope.

### Placing must_not at the Wrong Level

must_not inside nested finds nested children that do not match, which does not mean the parent has no matching child. Put the nested query inside parent bool.must_not to exclude the parent.

### Unbounded inner_hits

Responses can grow huge. Set size and project only needed fields.

### Oversized Nested Arrays

Indexing, querying, and updating become costly. Consider a separate child index or an alternative model.

### Updating Nested Children Like Relational Rows

Nested children lack independent document lifecycles. Update the parent or split into a child index when independent updates are needed.

### Mapping Explosion from Dynamic Attributes

Avoid creating a separate field for every attribute name when keys vary freely. Use a typed key/value model or flattened when suitable.

### Skipping False-Positive Tests

Simple datasets may hide correlation bugs. Build fixtures with two nested objects splitting the conditions across them.

## 41. Workflow for Designing Product Nested Queries

When designing a catalog:

1. List fields at product level and variant level.
2. Identify which conditions must hold on the same variant.
3. Choose object or nested according to correlation semantics.
4. Define field types for keyword, numeric, date, and boolean.
5. Create the mapping and verify it on a real index.
6. Write nested queries for combined conditions.
7. Use inner_hits when matching variants must be returned.
8. Use nested sort with matching filters.
9. Use nested and reverse_nested aggregations at the right scope.
10. Evaluate nested document counts and update rates.
11. Write integration tests for false positives, sorting, aggregations, and must_not.
12. Reindex into a new versioned index when mappings change.

## Conclusion

Nested is the right choice whenever fields within the same object array must be evaluated together as a unit. For products with variants, nested queries ensure color, size, price, and stock belong to the same variant, whereas regular objects flatten values and create false positives. In Spring Data Elasticsearch, FieldType.Nested declarations must match the actual mapping and queries must emit proper nested DSL. Put conditions that must match the same element inside one nested query; use multiple separate nested clauses only when different elements may satisfy each condition.

Nested queries combine cleanly with parent filters, inner_hits, nested sorting, and nested aggregations. Use reverse_nested when counting parent products, nested sort filters to ignore ineligible variants, and parent-level must_not to exclude products with any offending nested child. Because nested increases Lucene document counts and indexing/update overhead, use it only when correlation is required. Test with fixtures specifically designed to split conditions across variants to catch false positives, and benchmark queries, sorts, aggregations, and updates on realistic data.
