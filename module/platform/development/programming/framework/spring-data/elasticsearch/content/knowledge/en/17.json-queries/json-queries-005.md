# Distinguishing a Query Clause from a Full Search Request

When searching in Elasticsearch, it is essential to distinguish a **query clause** from a **full search request**. A query clause describes the conditions that determine which documents match—such as searching for a keyword in a name, filtering by status, or restricting price to a range. A search request wraps that clause and adds options that control search execution, such as pagination, sorting, highlighting, aggregations, timeouts, and result count.

This distinction matters when using Spring Data Elasticsearch. **CriteriaQuery**, **StringQuery**, and **NativeQuery** construct the query portion in different ways; a Spring Data **Query** object can also carry search settings such as pageable and sort. When Elasticsearch receives the request, those pieces are assembled into a complete search request. Never pass an entire search request JSON into an API that expects only a query clause.

This article uses the **products** index and the fields **name**, **category**, **status**, and **price**. We will read the JSON structure from the inside out, separate the query part from sibling options, and examine how those parts are represented in Spring Data Elasticsearch.

## 1. What Is a Query Clause?

A query clause is a Query DSL object describing document matching conditions. A query clause can be **match**, **term**, **range**, **bool**, **nested**, **prefix**, or many other types.

For example, the following clause finds documents whose name matches the phrase **wireless keyboard**:

~~~json
{
  "match": {
    "name": "wireless keyboard"
  }
}
~~~

This is a query clause. It describes how to match documents by the **name** field, without specifying:

- How many results to retrieve.
- Which offset to start from.
- Which field to sort by.
- Whether to return highlights.
- Whether to compute aggregations.
- Whether to set an execution time limit.

Multiple clauses can be combined using a **bool query**:

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": "wireless keyboard"
        }
      }
    ],
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
~~~

This bool clause requires the product name to match a full-text search while being in the accessories category, having status ACTIVE, and having a price from 20 to 100. It is still only the search criteria portion.

## 2. What Is a Full Search Request?

A search request is the request sent to the Elasticsearch Search API. Its body typically contains a **query** property alongside other search options at the same level.

Complete request example:

~~~http
POST /products/_search
{
  "from": 0,
  "size": 20,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless keyboard"
          }
        }
      ],
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
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ],
  "_source": [
    "name",
    "category",
    "price"
  ],
  "highlight": {
    "fields": {
      "name": {}
    }
  },
  "track_total_hits": true,
  "timeout": "2s"
}
~~~

In this request:

- **query** holds the Query DSL clause that decides which documents match.
- **from** and **size** specify the starting offset and requested number of results.
- **sort** defines the ordering of results.
- **_source** restricts which source fields are returned.
- **highlight** instructs Elasticsearch to return highlighted text fragments.
- **track_total_hits** controls accurate total hit counting.
- **timeout** sets a time limit for the search operation.

These properties are siblings in the search request body. They are not child properties of the **bool** or **match** clause.

You can visualize the structure as follows:

~~~text
Search request
|
+-- from / size
|
+-- query
|   |
|   +-- bool
|       |
|       +-- must
|       +-- filter
|       +-- should
|       +-- must_not
|
+-- sort
+-- _source
+-- highlight
+-- aggregations
+-- track_total_hits
+-- timeout
~~~

The search request is the outer frame controlling the entire search call. The query clause is one component sitting inside that frame.

## 3. Direct Comparison of the Two JSON Structures

**Query clause only:**

~~~json
{
  "bool": {
    "filter": [
      {
        "term": {
          "category": "accessories"
        }
      }
    ]
  }
}
~~~

**Full search request body:**

~~~json
{
  "from": 0,
  "size": 10,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": "asc"
    }
  ]
}
~~~

The difference lies in the outer wrapper:

- A query clause starts with a query type such as **bool**, **match**, **term**, or **range**.
- A search request body can contain **query** along with many other search properties.
- Inside the request body, the query clause is nested as the value of the **query** key.

If an API expects a query clause and you pass the entire search request body, the nesting becomes invalid. Conversely, sending a bare query clause to a search endpoint whose request body requires a **query** property will cause Elasticsearch to reject it or misinterpret the structure.

## 4. Endpoints and Query String Parameters Also Belong to the Request

In addition to the JSON body, a search request includes an HTTP method, endpoint, and query string parameters.

Example:

~~~http
POST /products/_search?allow_partial_search_results=false&preference=search-ui
{
  "query": {
    "match": {
      "name": "keyboard"
    }
  },
  "size": 10
}
~~~

Three parts can be distinguished:

| Component | Example | Role |
|---|---|---|
| HTTP method and endpoint | POST /products/_search | Selects the Search API and target index |
| URL query parameters | allow_partial_search_results, preference | Controls endpoint-level request behavior |
| JSON request body | query, size, sort | Describes search conditions and options in the body |

Some options can be passed via URL or body depending on the API and Elasticsearch version. Not every parameter can go in both places. Consult the Search API reference for your cluster version when using a specific parameter.

The index name in the endpoint may be a physical index, multiple indices, or an alias. When an alias is used, Elasticsearch routes the request according to the alias configuration at execution time.

## 5. Query DSL Can Nest Multiple Levels Deep

A query clause can contain other query clauses. For instance, **bool** holds **must**, **filter**, **should**, and **must_not**; each list in turn holds queries such as term, match, or range.

~~~json
{
  "bool": {
    "must": [
      {
        "match": {
          "name": {
            "query": "mechanical keyboard",
            "operator": "and"
          }
        }
      }
    ],
    "filter": [
      {
        "term": {
          "status": "ACTIVE"
        }
      },
      {
        "range": {
          "price": {
            "gte": 50,
            "lte": 150
          }
        }
      }
    ],
    "must_not": [
      {
        "term": {
          "category": "discontinued"
        }
      }
    ]
  }
}
~~~

This is still a single query clause despite multiple nesting levels. The **must**, **filter**, and **must_not** keys belong to the internal structure of the bool query, not search-request-level options.

Distinguish them clearly:

- **bool.filter** filters documents in filter context; clauses inside filter do not contribute to the relevance score.
- **bool.must** is a mandatory condition and can contribute to the score.
- **bool.should** expresses optional/boosted conditions or OR conditions depending on context and **minimum_should_match**.
- **bool.must_not** excludes documents matching the specified condition.

These components determine which documents match and how relevance scores are computed. They stay inside the scope of the query clause.

## 6. Common Properties at the Search Request Level

A search request can include many properties besides **query**. Several commonly used ones:

| Property | Purpose | Is It a Query Clause? |
|---|---|---|
| **from** | Skips the first N hits when paginating | No |
| **size** | Maximum number of hits to return | No |
| **sort** | Sorts the results | No |
| **_source** | Selects or excludes source fields to return | No |
| **highlight** | Generates highlighted text snippets | No |
| **aggs** or **aggregations** | Computes statistics, buckets, and data summaries | No |
| **post_filter** | Filters hits after aggregations have been computed | No; it is a separate request-level query |
| **track_total_hits** | Controls how total hits are counted | No |
| **timeout** | Limits search execution time | No |
| **min_score** | Excludes hits with a score below a threshold | No |
| **collapse** | Collapses results by a field | No |
| **suggest** | Generates autocomplete/suggestion results | No |
| **rescore** | Re-scores a subset of results | No |
| **search_after** | Continues pagination using sort values | No |
| **pit** | Uses a point in time to keep a consistent data view during pagination | No |
| **runtime_mappings** | Declares runtime fields for the request | No |
| **script_fields** | Computes extra fields in results | No |
| **profile** | Collects query execution profiling info | No |

Each property has a distinct role and cannot substitute for another. For example, **size** does not limit how many documents Elasticsearch evaluates during search; it limits how many hits are returned in the response. **min_score** filters by score, whereas **post_filter** filters by a query condition after aggregations are calculated.

## 7. Distinguishing query and post_filter

Both **query** and **post_filter** can hold a query clause, but they apply at different stages.

- **query** determines the document set used for both search hits and aggregations.
- **post_filter** filters the hit list after aggregations have already been computed; it does not alter the document set used by aggregations.

For example, a catalog page wants to display product counts per category across all matching results, while the product list itself shows only the accessories category:

~~~http
POST /products/_search
{
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  },
  "post_filter": {
    "term": {
      "category": "accessories"
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

In this example:

1. **query** selects all ACTIVE products.
2. **aggs.categories** counts and groups products by category within the ACTIVE set.
3. **post_filter** keeps only hits in the accessories category for the returned hit list.
4. Aggregations can still show other categories because post_filter does not retroactively filter aggregations.

If you put the category condition inside **query** instead of post_filter, aggregations will also compute solely over products in the accessories category. Therefore, where you place a condition changes the meaning of the results.

Do not use post_filter in place of ordinary filtering. If a condition must restrict both hits and aggregations, place it inside query or bool.filter.

## 8. Aggregations Belong to the Search Request, Not the Query Clause

Aggregations compute statistics or group data. Example counting products per category:

~~~json
{
  "aggs": {
    "products_by_category": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

This is the aggregation section of the search request. It does not decide whether documents match the query. If the request omits **query**, Elasticsearch can aggregate across all documents within the targeted indices according to Search API defaults.

Combining query and aggregation:

~~~http
POST /products/_search
{
  "size": 0,
  "query": {
    "range": {
      "price": {
        "gte": 20,
        "lte": 200
      }
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      },
      "aggs": {
        "average_price": {
          "avg": {
            "field": "price"
          }
        }
      }
    }
  }
}
~~~

In this request:

- **query** selects only products priced between 20 and 200.
- **size: 0** returns no hit list, yet aggregations are still calculated.
- **aggs.categories** groups documents by category.
- **average_price** calculates the average price for each bucket.

This clearly demonstrates how a search request can perform multiple tasks in a single call: filtering documents, paginating or suppressing hits, computing aggregations, and returning metadata.

## 9. Pagination and Sorting Are Request Options

The query clause determines matching documents. **from**, **size**, and **sort** control which slice of results is returned.

~~~http
POST /products/_search
{
  "from": 20,
  "size": 10,
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    },
    {
      "sku": {
        "order": "asc"
      }
    }
  ]
}
~~~

This request:

- Finds products in the accessories category.
- Sorts by price ascending.
- Breaks price ties by sorting on SKU ascending.
- Skips the first 20 hits and returns up to the next 10 hits.

**from** and **size** do not alter query criteria. They only control the returned window of results.

On large datasets, deep pagination with from/size can be expensive because Elasticsearch must process prior hits on every shard. When paging deeply, consider **search_after** combined with a deterministic sort or **point in time** as required by your application.

Example of search_after in a request:

~~~http
POST /products/_search
{
  "size": 10,
  "query": {
    "term": {
      "category": "accessories"
    }
  },
  "sort": [
    {
      "price": "asc"
    },
    {
      "sku": "asc"
    }
  ],
  "search_after": [
    89.5,
    "KB-1001"
  ]
}
~~~

search_after values must be taken from the **sort values** of the last hit on the previous page. Do not guess cursor values. Sort order must be deterministic with a suitable tie-breaker to prevent skipped or duplicate hits while paging.

## 10. Source Filtering Is Not a Document Filter Condition

**_source** decides which fields from the original JSON document are returned. It does not decide whether a document matches the query.

Example:

~~~http
POST /products/_search
{
  "_source": [
    "name",
    "price"
  ],
  "query": {
    "term": {
      "status": "ACTIVE"
    }
  }
}
~~~

Elasticsearch still finds documents with status ACTIVE, but the response contains only the source fields name and price. The status field may be absent from the returned source even though it was used for filtering.

Distinguish them:

- **query/filter** selects documents.
- **_source** selects which source content is returned.
- **fields** or **docvalue_fields** can request field values differently depending on data types and the API.

If you only need to reduce response size, source filtering is the right tool. Never move search criteria into _source because the two properties solve completely different problems.

## 11. Spring Data Elasticsearch: Which Part Does CriteriaQuery Represent?

In Spring Data Elasticsearch, **Criteria** describes search conditions and **CriteriaQuery** wraps those conditions into a **Query** object.

Example:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.mapping.IndexCoordinates;

Criteria criteria = Criteria.where("category").is("accessories")
        .and("status").is("ACTIVE")
        .and("price").between(20.0, 100.0);

CriteriaQuery query = new CriteriaQuery(criteria);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Here:

- **criteria** holds conditions on category, status, and price.
- **CriteriaQuery** is the Spring Data query object.
- **operations.search(...)** executes the search against the products index.
- **SearchHits<Product>** contains hits along with result metadata.

CriteriaQuery mainly builds the criteria portion. A Spring Data Query object can also carry common settings such as pageable, sort, or source filtering depending on the API. Those settings are translated into the corresponding sections of the search request.

Example adding pagination:

~~~java
Criteria criteria = Criteria.where("category").is("accessories");

CriteriaQuery query = new CriteriaQuery(criteria);
query.setPageable(PageRequest.of(0, 20));

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

**PageRequest** supplies page number and page size. Spring Data translates this into the pagination options of the search request, usually corresponding to **from** and **size**.

Method names and how pageable/sort are attached can vary across versions. Check the API for your project's version.

Key takeaway: **CriteriaQuery is not a complete Search API JSON body**. It is a Spring Data query object that holds search conditions and certain query options supported by Spring Data.

## 12. StringQuery Accepts a Query Clause, Not a Full Request Body

**StringQuery** lets you pass JSON Query DSL as a string. Its content is typically the query clause that Spring Data places in the **query** section of the search request.

Example:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
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
""";

Query query = new StringQuery(dsl);

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

The JSON string starts with **bool** because it describes a query clause.

Do not pass an entire body like the following into a constructor expecting query JSON:

~~~json
{
  "from": 0,
  "size": 20,
  "query": {
    "bool": {
      "filter": [
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": "asc"
    }
  ]
}
~~~

The body above is a full search request. If an API expects a query clause, passing the whole body creates an invalid structure because Spring Data may wrap that string a second time under the **query** key.

When you need both query conditions and pagination/sorting, use the corresponding properties on the Spring Data Query object when supported. When advanced request options not represented by the Query abstraction are needed, use NativeQuery or the appropriate Elasticsearch Java API Client API.

## 13. NativeQuery and Options Outside the Query Clause

In Spring Data Elasticsearch 5.x, **NativeQuery** lets you build queries with the Elasticsearch Java API Client. It also supports many search options at the Query abstraction level, depending on the version.

Example building only a query condition and pagination:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.SearchHits;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("name")
                .query("wireless keyboard")))
        .withPageable(PageRequest.of(0, 20))
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

In this example:

- **withQuery(...)** constructs the query clause.
- **withPageable(...)** adds pagination information.
- **operations.search(...)** executes the request and returns SearchHits.

NativeQuery can also express sorting, aggregations, highlighting, and other features depending on the Spring Data Elasticsearch and Elasticsearch Java API Client versions. Consult the relevant documentation rather than assuming every Search API field has identical builder methods.

If you need a feature not yet supported by the Query abstraction, you can use the Elasticsearch Java API Client directly to build a **SearchRequest** and invoke the client. This provides lower-level request control while coupling application code more tightly to the client version.

## 14. Mapping Spring Data Abstractions to Search Requests

| Spring Data Abstraction | Main Part It Represents | Is It a Full Search API Request? |
|---|---|---|
| **Criteria** | Field conditions and logical combinations | No |
| **CriteriaQuery** | Criteria wrapped as a Query, optionally with common settings | No |
| **StringQuery** | JSON Query DSL as a string | No |
| **NativeQuery** | Java client builder Query DSL and supported search options | Not inherently |
| **Query** | Common Spring Data query contract holding query, pageable, sort, and other options | Not a raw SearchRequest |
| Elasticsearch Java API Client **SearchRequest** | Client-level search request | Close to the complete request |
| HTTP POST /{index}/_search | Endpoint, URL parameters, and Search API body | The actual request sent to the cluster |

Importantly, do not equate the Spring Data **Query** class name with all of Query DSL or an entire Elasticsearch SearchRequest. They are abstractions at different layers.

## 15. An Example from Business Requirements to Full Request

Suppose a product listing screen requires:

- Only ACTIVE products.
- Name matching the keyword **keyboard**.
- Price between 20 and 150.
- Sorted by price ascending.
- Returning 10 results on the second page.
- Returning only name, category, and price.
- Highlighting the keyword in name.
- Counting products per category.

The corresponding search request:

~~~http
POST /products/_search
{
  "from": 10,
  "size": 10,
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "keyboard"
          }
        }
      ],
      "filter": [
        {
          "term": {
            "status": "ACTIVE"
          }
        },
        {
          "range": {
            "price": {
              "gte": 20,
              "lte": 150
            }
          }
        }
      ]
    }
  },
  "sort": [
    {
      "price": {
        "order": "asc"
      }
    }
  ],
  "_source": [
    "name",
    "category",
    "price"
  ],
  "highlight": {
    "fields": {
      "name": {}
    }
  },
  "aggs": {
    "categories": {
      "terms": {
        "field": "category"
      }
    }
  }
}
~~~

The request can be divided into two groups:

**Document selection criteria**

- match name.
- term status.
- range price.
- bool combining must and filter.

**Request options and extensions**

- from and size.
- sort.
- _source.
- highlight.
- aggs.

This separation makes debugging easier. If documents fail to appear, check the query and mapping first. If the right documents match but order or count is wrong, check sort, from, and size. If highlights or aggregations are missing, check the corresponding request-level properties.

## 16. Reading Responses Also Requires Separating Hits from Metadata

A search response does not contain only a list of documents. It also contains metadata about total hits, execution time, shards, and aggregations.

Condensed response example:

~~~json
{
  "took": 8,
  "timed_out": false,
  "_shards": {
    "total": 1,
    "successful": 1,
    "skipped": 0,
    "failed": 0
  },
  "hits": {
    "total": {
      "value": 42,
      "relation": "eq"
    },
    "max_score": 1.2,
    "hits": [
      {
        "_index": "products",
        "_id": "p-1001",
        "_score": 1.2,
        "_source": {
          "name": "Wireless Keyboard",
          "category": "accessories",
          "price": 89.5
        },
        "highlight": {
          "name": [
            "Wireless <em>Keyboard</em>"
          ]
        }
      }
    ]
  },
  "aggregations": {
    "categories": {
      "buckets": []
    }
  }
}
~~~

Key components:

- **took** is the time Elasticsearch spent executing the request.
- **timed_out** indicates whether the request timed out.
- **_shards** reports processing status across shards.
- **hits.total** describes total matching results and the relation of that count.
- **hits.hits** holds the returned documents.
- **_score** is the relevance score if the query performs scoring.
- **_source** holds the requested source fields.
- **highlight** contains highlighted text fragments.
- **aggregations** holds statistical results.

In Spring Data Elasticsearch, **SearchHits<T>** and **SearchHit<T>** give access to hits alongside metadata. Aggregations can be retrieved from query results via the aggregation API of your version.

Do not confuse **hits.total** with the actual number of elements in the **hits.hits** array. A request might ask for only 10 results while the total matching hit count is 42.

## 17. Common Mistakes When Confusing Query Clauses with Search Requests

| Symptom | Possible Cause | Resolution |
|---|---|---|
| StringQuery throws a JSON error or invalid query error | Passing the entire search request body where only a query clause is expected | Pass only the query object matching the constructor |
| Search does not limit result count as expected | Putting size inside bool or match | Set size at the search request level or use Pageable |
| Sort has no effect | Putting sort inside the query clause | Use sort at the request level or via Query sort APIs |
| Aggregations do not appear | Only building Criteria without configuring aggregations | Use NativeQuery or an API supporting aggregations |
| Aggregations count more documents than the hit list | Condition placed inside post_filter | Put shared conditions inside query if aggregations must also be filtered |
| Source is missing fields | _source filtering requests only a subset of data | Check the list of selected source fields |
| Highlight does not appear | Highlight not configured at the request level or unsuitable field | Add highlight and verify mapping |
| Incorrect pagination | Confusing page number with from or size | Check how Pageable translates and note that page indices are 0-based |
| Query is valid yet request still fails | Wrong endpoint, URL parameter, or access permissions | Check the entire HTTP request and cluster response |
| Response total hits exceed returned hits | size caps the number of hits in the response | Compare hits.total with hits.hits.length |

When debugging, pinpoint where the fault lies: query clause structure, request options, endpoint/URL parameters, mapping, or data. Do not modify Criteria when the real issue is request-level size or sort.

## 18. Workflow for Reading a Search Request

When inspecting search JSON from Dev Tools, logs, or code, read it in order:

1. **Check the endpoint.** Identify the index or alias, API invoked, and URL parameters.
2. **Locate the query key.** This holds the main Query DSL clause.
3. **Read the query from the inside out.** Start with match, term, range, and nested, then see how bool combines them.
4. **Read the context.** Distinguish must, filter, should, and must_not.
5. **Read sibling properties.** Inspect from, size, sort, _source, highlight, aggs, post_filter, timeout, and other options.
6. **Read the response.** Separate hits, total result count, score, highlight, aggregations, and shard status.
7. **Cross-reference with Spring Data.** Identify which parts came from Criteria and which from Pageable/Sort or NativeQuery options.
8. **Check mappings.** Confirm query types match field types and analyzers.
9. **Verify behavior.** Use an equivalent request in Dev Tools, _validate/query, _explain, or profile as needed.

Do not compare two requests solely by JSON key order. Compare structure and meaning: are the query clauses equivalent, is pagination identical, is sorting identical, and are aggregations/filters placed at the right level?

## 19. Design Principles When Using Spring Data Elasticsearch

- Use **CriteriaQuery** for simple, common conditions easily expressed with Criteria.
- Use **Pageable** and **Sort** for pagination and sorting when supported by the Query abstraction.
- Use **StringQuery** when you need to pass a JSON query clause directly.
- Use **NativeQuery** when you need advanced Query DSL or search options not conveniently expressed with Criteria.
- Use the Elasticsearch Java API Client directly when you need low-level SearchRequest control and Spring Data APIs lack a needed option.
- Never place **from**, **size**, **sort**, **aggs**, or **highlight** inside a bool query.
- Never pass a full search request body into StringQuery if the constructor expects only a query clause.
- Place conditions in **query** or **post_filter** according to the intended aggregation semantics.
- Check the endpoint, index/alias, and URL parameters when a request behaves unexpectedly.
- Read both request and response to separate query errors from search-option errors.

A complete search request comprises the endpoint, URL parameters, and search body. Inside the body, **query** holds the Query DSL clause that determines matching documents; properties like **from**, **size**, **sort**, **_source**, **highlight**, **aggs**, and **timeout** govern execution and result presentation. In Spring Data Elasticsearch, CriteriaQuery and StringQuery primarily build the query part, while the Query abstraction can carry several general options. When full control over the request is needed, choose NativeQuery or the Elasticsearch Java API Client compatible with your project version.
