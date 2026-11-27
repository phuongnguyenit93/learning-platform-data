# Reading Actual Query DSL and Recognizing Criteria Limits

Spring Data Elasticsearch provides **Criteria** and **CriteriaQuery** to build queries in Java. This API lets you express common conditions such as exact matching, price ranges, statuses, categories, and text search without assembling JSON manually. However, Criteria is an abstraction layer over the Elasticsearch Query DSL. To understand the exact query being executed, you need to know which query type each condition maps to, how mappings and analyzers affect results, and when Criteria lacks the expressiveness required.

This article uses the **products** index with fields SKU, name, category, status, price, and creation date. We will translate Criteria expressions into equivalent Query DSL, read bool/range/term/match structures, verify queries against Elasticsearch, and choose explicit query approaches when requirements go beyond Criteria's scope.

## 1. Criteria and Query DSL Sit at Two Different Layers

Elasticsearch accepts queries as JSON following Query DSL. For example, a query filtering products by category and status:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

Spring Data Elasticsearch lets you describe a similar condition in Java:

~~~java
Criteria criteria = Criteria.where("category").is("accessories")
        .and("status").is("ACTIVE");

Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

Where:

- **Criteria** describes conditions on data fields.
- **CriteriaQuery** wraps Criteria into a Query object that Spring Data can execute.
- **ElasticsearchOperations.search(...)** sends the query to Elasticsearch and maps results into Product.
- Elasticsearch executes Query DSL against the index's mapping and data.

You can think of Criteria as the application-layer syntax, while Query DSL is the query language Elasticsearch actually understands. When debugging, read the query type and its logic rather than looking only at Java method names.

The actual JSON sent may include extra wrapper layers such as **bool**, **must**, **should**, or pagination options. Exact structural details depend on the Spring Data Elasticsearch version. Thus, JSON snippets in this article illustrate equivalent query logic; they are not a guarantee that the serializer always emits the exact same key order or wrapper structure.

## 2. Mapping Determines How to Read Query DSL

Before reading a query, know the field's data type. The exact same search expression can yield very different results depending on whether a field is mapped as **text** or **keyword**.

Example mapping:

~~~json
{
  "properties": {
    "sku": {
      "type": "keyword"
    },
    "name": {
      "type": "text",
      "analyzer": "standard",
      "fields": {
        "raw": {
          "type": "keyword"
        }
      }
    },
    "category": {
      "type": "keyword"
    },
    "status": {
      "type": "keyword"
    },
    "price": {
      "type": "double"
    },
    "createdAt": {
      "type": "date"
    }
  }
}
~~~

Meaning of the field types:

- **keyword** keeps values intact, suited for exact filtering, sorting, and aggregations.
- **text** is split into tokens by an analyzer, suited for full-text search.
- **double**, **long**, **integer**, and numeric types support numeric comparisons and ranges.
- **date** supports timestamp and date-range queries.
- Multi-field **name.raw** lets the same product name be full-text searched on **name** and matched intact on **name.raw**.

An important rule: **a term query does not analyze the query string like a match query**. If **name** is text, its value was converted into tokens by an analyzer at index time. Running a term query with the raw string such as "Mechanical Keyboard" may not match as expected. For full-text search, typically use match on **name**; for intact whole-string matching, use term on **name.raw**.

## 3. From Criteria.is() to Term Query

Criteria **is(value)** generally expresses a single-value equality condition. For keyword fields, it is logically equivalent to a **term query**.

Java:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE");
Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

Equivalent Query DSL:

~~~json
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Reading the JSON:

- **term** is the query type.
- **status** is the field being matched.
- **ACTIVE** is the value to match exactly.

Use **is()** for fields such as status, category, sku, or identifiers when they are mapped as keyword.

If you need to match an intact product name, use the keyword multi-field:

~~~java
Criteria criteria = Criteria.where("name.raw")
        .is("Mechanical Keyboard");
~~~

Equivalent Query DSL:

~~~json
{
  "query": {
    "term": {
      "name.raw": "Mechanical Keyboard"
    }
  }
}
~~~

Do not assume **is()** on a text field means full-text search. Verify the mapping type before selecting a Criteria method.

## 4. From Criteria.in() to Terms Query

When a field can take one of several values, use **in(...)**:

~~~java
Criteria criteria = Criteria.where("category")
        .in("accessories", "storage");

Query query = new CriteriaQuery(criteria);
~~~

Equivalent Query DSL:

~~~json
{
  "query": {
    "terms": {
      "category": [
        "accessories",
        "storage"
      ]
    }
  }
}
~~~

**terms** matches if the field value equals one of the supplied values. This is the right representation for categories, statuses, or code sets requiring exact filtering.

With large value lists, consider request size and Elasticsearch's terms limit. Do not pass tens of thousands of values in a single query if a better data model or filtering workflow exists.

## 5. From Criteria.between() and Comparison Operators to Range Query

Numeric and date comparison conditions are typically translated into a **range query**.

Example price from 20 to 100:

~~~java
Criteria criteria = Criteria.where("price").between(20.0, 100.0);
Query query = new CriteriaQuery(criteria);
~~~

Equivalent Query DSL:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gte": 20.0,
        "lte": 100.0
      }
    }
  }
}
~~~

Common operators:

| Criteria | Range DSL | Meaning |
|---|---|---|
| **greaterThan(value)** | **gt** | Greater than |
| **greaterThanEqual(value)** | **gte** | Greater than or equal to |
| **lessThan(value)** | **lt** | Less than |
| **lessThanEqual(value)** | **lte** | Less than or equal to |
| **between(from, to)** | Usually **gte** and **lte** | Within range, inclusive on both ends |

Example fetching only products priced greater than 50:

~~~java
Criteria criteria = Criteria.where("price").greaterThan(50.0);
~~~

Query DSL:

~~~json
{
  "query": {
    "range": {
      "price": {
        "gt": 50.0
      }
    }
  }
}
~~~

Date conditions can be combined as well:

~~~java
Instant cutoff = Instant.parse("2026-01-01T00:00:00Z");

Criteria criteria = Criteria.where("createdAt").lessThan(cutoff);
Query query = new CriteriaQuery(criteria);
~~~

Equivalent Query DSL:

~~~json
{
  "query": {
    "range": {
      "createdAt": {
        "lt": "2026-01-01T00:00:00Z"
      }
    }
  }
}
~~~

For range queries to work properly, fields must be mapped to an appropriate numeric or date type. If prices or dates are stored as text, comparisons may lack numeric or chronological meaning.

## 6. From Criteria.matches() to Match Query

For text fields, **matches(...)** expresses full-text search. The corresponding Query DSL is **match**:

~~~java
Criteria criteria = Criteria.where("name")
        .matches("wireless keyboard");

Query query = new CriteriaQuery(criteria);
~~~

Equivalent Query DSL:

~~~json
{
  "query": {
    "match": {
      "name": {
        "query": "wireless keyboard"
      }
    }
  }
}
~~~

A match query analyzes the query text using the field's configured analyzer, then finds matching tokens in the inverted index.

If the analyzer splits the phrase into two tokens **wireless** and **keyboard**, the default query may match documents containing either token depending on the operator. To require all tokens to be present, Query DSL can set **operator: "and"**:

~~~json
{
  "query": {
    "match": {
      "name": {
        "query": "wireless keyboard",
        "operator": "and"
      }
    }
  }
}
~~~

Some Criteria versions offer methods like **matchesAll(...)** to require matching all tokens. Check your project version's API and inspect the actual sent query; if you need explicit operator or match options, use NativeQuery or StringQuery.

### Match Is Not Like Term

| Aspect | match | term |
|---|---|---|
| Analyzes query string | Yes, uses the field analyzer or search analyzer | No |
| Typical field type | text | keyword |
| Full-text search | Suitable | Not its primary purpose |
| Intact value matching | Not guaranteed | Suitable |
| Affected by analyzer | Yes | Data was analyzed at index time |

When reading DSL, seeing **match** versus **term** immediately tells you Elasticsearch handles the query string differently.

## 7. From Criteria.startsWith() to Prefix Query

When finding values starting with a prefix, Criteria can use **startsWith(...)**:

~~~java
Criteria criteria = Criteria.where("sku").startsWith("KB-");
Query query = new CriteriaQuery(criteria);
~~~

Equivalent Query DSL:

~~~json
{
  "query": {
    "prefix": {
      "sku": {
        "value": "KB-"
      }
    }
  }
}
~~~

A prefix query finds terms beginning with the specified string. It usually fits codes or keyword fields. On analyzed text fields, the prefix applies to indexed terms, not necessarily the original displayed string.

If the requirement is partial-text autocomplete, consider **search_as_you_type** or an analyzer using **edge_ngram** instead of running prefix queries indiscriminately over a large text field.

## 8. Criteria.contains() and Wildcard Query

Criteria can provide string searches such as **contains(...)** or **endsWith(...)**. They are usually represented by a wildcard query.

Example finding SKUs containing **100**:

~~~java
Criteria criteria = Criteria.where("sku").contains("100");
Query query = new CriteriaQuery(criteria);
~~~

Logically equivalent Query DSL:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*100*"
      }
    }
  }
}
~~~

Wildcard **\*** represents zero or more characters. With the pattern **\*100\***, Elasticsearch must find terms containing 100 at any position.

Wildcards starting with **\*** are generally more expensive than prefix queries because they cannot efficiently leverage the term dictionary structure. Do not use contains/wildcards on high-cardinality fields or large indices without evaluating the cost.

In addition, wildcards operate on indexed terms. They do not automatically perform linguistic analysis like a match query. Check analyzers and field types to avoid false expectations.

## 9. Reading AND, OR, and NOT Logic in Bool Queries

When combining multiple Criteria, Spring Data must express logic using Boolean clauses in Query DSL.

### AND: Must Satisfy Multiple Conditions

Java:

~~~java
Criteria criteria = Criteria.where("category").is("accessories")
        .and("status").is("ACTIVE");

Query query = new CriteriaQuery(criteria);
~~~

Logically equivalent Query DSL:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

Documents must satisfy both conditions. In DSL, **must** holds mandatory clauses that can also contribute to score.

If conditions are only for filtering and do not need relevance scoring, Elasticsearch provides **filter**:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        }
      ]
    }
  }
}
~~~

CriteriaQuery can express combined conditions, yet it does not always give full control over placing individual clauses into **must** versus **filter**. If optimizing scoring and filter context is an important requirement, use NativeQuery or StringQuery to specify it explicitly.

### OR: Only Needs to Satisfy One Condition

Query DSL uses **should** to express OR:

~~~json
{
  "query": {
    "bool": {
      "should": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "term": {
            "status": "PENDING"
          }
        }
      ],
      "minimum_should_match": 1
    }
  }
}
~~~

**minimum_should_match: 1** requires at least one should clause to match. When reading a bool query, do not just look at the should list; check minimum_should_match and any accompanying must/filter clauses because they determine the actual logic.

Criteria offers ways to combine **or(...)** in supported versions. Illustrative expression:

~~~java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .or("status").is("PENDING");

Query query = new CriteriaQuery(criteria);
~~~

Inspect the actual DSL if the query has multiple nested branches, as the generated bool structure may differ from hand-written JSON key by key.

### NOT: Excluding Conditions

Query DSL uses **must_not** to exclude documents matching a condition:

~~~json
{
  "query": {
    "bool": {
      "must_not": [
        {
          "term": {
            "status": "DELETED"
          }
        }
      ]
    }
  }
}
~~~

Criteria can use negation methods such as **isNot(...)** or negation constructs supported by your version. For complex NOT logic, inspect the generated query to avoid accidentally negating an entire group of conditions.

## 10. A Multi-Condition CriteriaQuery Example

Suppose you need products in the accessories category that are ACTIVE and priced between 20 and 100:

~~~java
Criteria criteria = Criteria.where("category").is("accessories")
        .and("status").is("ACTIVE")
        .and("price").between(20.0, 100.0);

Query query = new CriteriaQuery(criteria);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Logically equivalent Query DSL:

~~~json
{
  "query": {
    "bool": {
      "must": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20.0,
              "lte": 100.0
            }
          }
        }
      ]
    }
  }
}
~~~

Reading the query step by step:

1. **bool** combines multiple conditions.
2. **term category** restricts the category.
3. **term status** restricts the status.
4. **range price** restricts the price.
5. Documents must satisfy all mandatory clauses.

If this is a catalog filter query that does not need relevance scoring, filter context in DSL can be used to avoid scoring filter conditions. That is a practical reason to switch to NativeQuery or StringQuery when deep control is needed.

## 11. Criteria Is Not a Complete Copy of Query DSL

Criteria suits common conditions, yet Elasticsearch Query DSL has many specialized features. A compact abstraction does not necessarily expose every option of every query type.

Cases where Criteria may be insufficient or inconvenient:

| Need | Why Criteria can be limiting | Approach |
|---|---|---|
| Nested query | Needs nested path and inner query inside nested documents | NativeQuery or StringQuery |
| Script query or script score | Needs script, params, and score context | NativeQuery/Elasticsearch Java API Client |
| Function score | Needs multiple scoring functions and weights | NativeQuery |
| Query_string with full search syntax | Needs control over query string, fields, default operator, and flags | StringQuery or NativeQuery |
| Fuzzy query with advanced options | Needs control over fuzziness, prefix length, max expansions | NativeQuery |
| Geo queries | Needs geometries, distances, relations, or shapes | NativeQuery or client API |
| Parent/child and join queries | Needs join relationships and specialized context | NativeQuery |
| Rescore and rank features | Advanced search-request-level features | NativeQuery/client API |
| Complex aggregations | Needs building aggregation trees, buckets, metrics, and pipelines | NativeQuery or client API |
| Highlight, suggest, collapse | Extra search options beyond basic filtering | Advanced Query API |
| Point in time, search_after, and scroll | Needs managing pagination state and cursors | Search API supported by version |

This is not a ban on using Criteria for all of the items above. Specific support may expand across versions. The rule of thumb is: when a requirement needs a Query DSL option that Criteria does not express clearly, use an explicit query API rather than chaining multiple Criteria to emulate it.

## 12. Nested Query: An Example of an Important Limitation

Suppose Product holds a list of variants, each with a color and size. If the mapping declares **variants** as **nested**, queries must use a nested query to keep conditions scoped to the same nested element.

Mapping:

~~~json
{
  "properties": {
    "variants": {
      "type": "nested",
      "properties": {
        "color": {
          "type": "keyword"
        },
        "size": {
          "type": "keyword"
        }
      }
    }
  }
}
~~~

Requirement: find products with a single variant that is both black and size M.

Query DSL:

~~~json
{
  "query": {
    "nested": {
      "path": "variants",
      "query": {
        "bool": {
          "filter": [
            {
              "term": {
                "variants.color": "black"
              }
            },
            {
              "term": {
                "variants.size": "M"
              }
            }
          ]
        }
      }
    }
  }
}
~~~

If you merely write Criteria conditions on **variants.color** and **variants.size** without constructing a proper nested query, Elasticsearch may fail to evaluate both conditions against the same nested object. This can produce wrong results on documents with multiple variants.

Use StringQuery to pass explicit DSL:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
  "nested": {
    "path": "variants",
    "query": {
      "bool": {
        "filter": [
          { "term": { "variants.color": "black" } },
          { "term": { "variants.size": "M" } }
        ]
      }
    }
  }
}
""";

Query query = new StringQuery(dsl);

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

The example uses a Java text block, available in Java 15 and later. For older Java versions, build the JSON string or use the NativeQuery builder.

## 13. Using StringQuery When You Want to Write Query DSL Directly

**StringQuery** lets you pass the JSON body of a query into Spring Data Elasticsearch. This is a readable option when you want to keep the exact DSL without constructing every object via the Java API Client.

Example filtering category, status, and price:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
  "bool": {
    "filter": [
      { "term": { "category": "accessories" } },
      { "term": { "status": "ACTIVE" } },
      {
        "range": {
          "price": {
            "gte": 20,
            "lte": 100
          }
        }
      }
    ]
  }
}
""";

Query query = new StringQuery(dsl);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

In StringQuery, the JSON string is the query section sent to Elasticsearch; Spring Data manages the search request and maps results. Do not confuse the query contents with the full request body wrapped in an outer **query** key if the constructor API expects only the query object itself.

Advantages of StringQuery:

- Preserves the exact Query DSL designed by the team.
- Easy to compare directly with requests in Elasticsearch Dev Tools.
- Fits nested queries or structurally complex queries.
- Avoids forcing every DSL feature through a limited Java abstraction.

The drawback is that JSON is written as a string, so syntax errors or wrong field names are only caught when testing or executing the query. If content is built from user input, never concatenate JSON strings arbitrarily. Safely serialize parameters with a JSON library or use the NativeQuery builder.

## 14. Using NativeQuery When Typed DSL Is Needed

In Spring Data Elasticsearch 5.x, **NativeQuery** lets you build queries using the Elasticsearch Java API Client. This fits when you need richer Query DSL than Criteria provides while still constructing queries in Java with typed builders.

Illustrative example:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import co.elastic.clients.elasticsearch._types.FieldValue;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.bool(b -> b
                .filter(f -> f.term(t -> t
                        .field("category")
                        .value(FieldValue.of("accessories"))))
                .filter(f -> f.term(t -> t
                        .field("status")
                        .value(FieldValue.of("ACTIVE"))))
                .filter(f -> f.range(r -> r
                        .number(n -> n
                                .field("price")
                                .gte(20.0)
                                .lte(100.0))))
        ))
        .build();

SearchHits<Product> hits =
        operations.search(query, Product.class);
~~~

This snippet illustrates the Elasticsearch Java API Client builder integrated in Spring Data Elasticsearch 5.x. Builder signatures and value representations can vary across Elasticsearch Java Client versions; use the dependency managed by Spring Boot and verify the exact API in your project.

You can choose:

- **CriteriaQuery** for common, simple, and readable conditions.
- **StringQuery** when you want to pass explicit JSON DSL, especially for nested or complex queries.
- **NativeQuery** when you want typed Java builders and advanced Query DSL features.

You do not need NativeQuery for every query. A simple filter query is often easier to read when written with Criteria.

## 15. Reading the Actual Query DSL Sent to Elasticsearch

When debugging, what needs verification is the actual request sent, not just how Criteria looks in source code.

You can follow these steps:

1. Create a simple Criteria query and identify the target index.
2. Enable HTTP request logging or tracing for the Elasticsearch Java Client/transport in use at a level suited for development.
3. Send the query from the application.
4. Inspect the request body and identify **query**, **bool**, **term**, **match**, **range**, or other clauses.
5. Compare against the index mapping and the equivalent query in Dev Tools.
6. Disable verbose tracing after inspection because request logs may contain business data or sensitive information.

Logger names and how wire logging is enabled vary by client/transport and Spring Data Elasticsearch version. Do not copy a logger category from another version without checking the corresponding documentation. Also avoid logging credentials, personal data, or full document sources in production.

Points to note when reading requests:

- Query DSL may be wrapped inside **bool** even when Criteria has only one condition.
- Spring Data may add pagination, sorting, source filtering, or other options.
- JSON field order does not affect query meaning.
- The same logic can be expressed by multiple equivalent DSL structures.
- Do not compare JSON strings byte-for-byte; compare query types, fields, values, and bool logic.

## 16. Verifying Queries with Elasticsearch APIs

After reading the DSL, you can use Elasticsearch APIs to confirm syntax and why documents match or do not match.

### Validate Query

The **_validate/query** endpoint checks whether a query is valid:

~~~http
POST /products/_validate/query?explain=true
{
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

The **explain=true** parameter asks Elasticsearch to explain the query after parsing. This API is helpful for catching invalid query syntax or structure; it does not prove existing data will return the desired results.

### Explain Why a Document Matches

Use **_explain** with a document ID:

~~~http
GET /products/_explain/p-1001
{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

Elasticsearch returns details showing whether the document matches the query and how its score is computed. This is useful when a specific document is missing from results.

### Profile Query

You can add **profile: true** to a search request to see execution details:

~~~http
GET /products/_search
{
  "profile": true,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 100
            }
          }
        }
      ]
    }
  }
}
~~~

Profiling is useful when analyzing performance, though profiling itself adds overhead. Enable it only when investigating issues and do not enable it across all production requests.

## 17. Checking the Analyzer When a Match Query Gives Unexpected Results

When a query uses **match**, the analyzer directly affects tokens of both the query text and the indexed content.

Example checking the analyzer:

~~~http
POST /products/_analyze
{
  "field": "name",
  "text": "Wireless Mechanical Keyboard"
}
~~~

Elasticsearch returns the list of tokens produced by analysis. Compare these tokens with the query Criteria generated and the terms stored in the index.

If **term** is used on a text field, the query string is not analyzed. For example:

~~~json
{
  "query": {
    "term": {
      "name": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

may not match because the index split the name into separate tokens. Switch to match:

~~~json
{
  "query": {
    "match": {
      "name": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

Or use a keyword subfield when intact matching is needed:

~~~json
{
  "query": {
    "term": {
      "name.raw": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

This is an important reason to inspect both Query DSL and mappings. Looking solely at Criteria methods without knowing field types can lead to misdiagnosis.

## 18. Performance Limits to Recognize

A syntactically valid query is not necessarily performant. Some query types require caution:

**Leading wildcards.** Patterns like **\*keyboard** or **\*100\*** may have to examine many terms. Use only when data volume and index scale permit.

**Fuzzy queries.** Fuzzy matching handles typos but can expand the number of terms evaluated. Limit fuzziness, prefix length, and max expansions as needed.

**Query_string.** Query string syntax is powerful, yet users can inject special operators. Explicitly decide whether users are allowed to write DSL syntax and sanitize inputs accordingly.

**Nested queries.** Require proper nested mappings and can be more expensive than regular field queries. Use only when the data model truly needs to preserve relationships among child objects.

**Script queries.** Flexible but potentially resource-heavy. If conditions can be expressed with term/range or data can be pre-normalized, consider a simpler approach.

**Bool queries with too many branches.** A query with hundreds or thousands of clauses increases parsing and execution cost. Consider terms queries, pre-filtering, or revising the data model.

When optimizing, inspect query profiles, mappings, shard counts, field cardinality, and data distribution. Do not optimize based solely on JSON length.

## 19. Common Pitfalls When Reading Criteria and Query DSL

| Symptom | Possible cause | How to check or fix |
|---|---|---|
| is() cannot find text content | `is` typically expresses term matching, while the field was analyzed | Use `matches`/`match` or a keyword subfield |
| matches() returns too many results | Default match may match any one of multiple tokens | Check the operator and consider AND or `match_phrase` |
| between() does not behave as expected | Field is mapped as text or value has wrong type | Check mapping and use proper numeric/date types |
| OR returns more documents than expected | `should`/`minimum_should_match` does not match intended logic | Read the entire bool query and set `minimum_should_match` |
| Nested conditions match wrong objects | Using standard field paths instead of a nested query | Check nested mapping and use nested DSL |
| contains() is slow | Wildcard has a leading wildcard across many terms | Use prefix, n-gram, or a dedicated search field |
| Criteria cannot express the query | Query needs nested, script, geo, or advanced options | Switch to NativeQuery/StringQuery |
| JSON in StringQuery fails | Syntax error in JSON string or query object wrapped improperly | Validate query and check what the constructor expects |
| Results differ from Dev Tools | Application uses a different index, alias, analyzer, or pagination | Compare the entire request and target index |
| Valid query returns zero hits | Value does not match data or analyzer creates different tokens | Use `_analyze`, `_explain`, and inspect sample documents |

## 20. Workflow for Reading and Choosing Criteria

When working with a Spring Data Elasticsearch query, follow this sequence:

1. **Identify the target index.** Check entity metadata, `IndexCoordinates`, or the alias the service uses.
2. **Read the mapping.** Determine whether field types are text, keyword, numeric, date, or nested.
3. **Read Criteria.** Note each condition, AND/OR connectors, and negations.
4. **Infer Query DSL.** Identify whether each condition is term, terms, match, range, prefix, wildcard, or bool.
5. **Check context.** Determine whether clauses sit in must, filter, should, or must_not and whether they affect scoring.
6. **Inspect the actual request.** Enable appropriate tracing in development if you need to confirm the sent structure.
7. **Validate and test data.** Use `_validate/query`, `_analyze`, `_explain`, or Dev Tools queries.
8. **Assess performance.** Check profiles when queries are slow and weigh wildcard, fuzzy, nested, or script costs.
9. **Choose the abstraction.** Keep Criteria for standard conditions; use StringQuery or NativeQuery when advanced DSL control is required.

Criteria helps build concise, readable Java queries, especially for basic term, range, and match conditions. However, Criteria is no substitute for knowing Query DSL. To understand results, read mappings, know which query type each Java condition translates into, and inspect the actual bool logic. When queries need nested objects, scripts, custom scoring, or specialized features, use NativeQuery or StringQuery to describe Elasticsearch requirements accurately.
