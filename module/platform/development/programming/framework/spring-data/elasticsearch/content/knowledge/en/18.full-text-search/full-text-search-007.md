# Prefix, Wildcard, Regexp, and Query Cost

Elasticsearch provides **prefix**, **wildcard**, and **regexp** queries to find documents based on a portion of an indexed term. They are useful when users search product codes by prefix, enter a partial string, or need character pattern matching. However, these are term-level queries: Elasticsearch matches directly against terms in the inverted index rather than analyzing the query string with an analyzer like a **match query**.

The three query types offer different levels of flexibility and cost. Prefix finds terms starting with a fixed string; wildcard allows wildcard characters; regexp expresses patterns using Lucene regular expression syntax. The broader the pattern—especially with leading wildcards or many alternation branches—the more terms Elasticsearch may have to inspect, consuming more CPU, memory, and search time.

This lesson uses the **products** index with fields **sku**, **name**, **category**, and **description**. We will examine how to choose mappings, read each query's syntax, evaluate cost, and select the right approach in Spring Data Elasticsearch.

## 1. Term-Level Queries vs. Full-Text Queries

Before choosing prefix, wildcard, or regexp, distinguish term-level queries from full-text queries.

A **full-text query**, such as **match**, analyzes query content using the field's analyzer and searches for matching tokens. This suits natural text like product names or descriptions.

A **term-level query** matches directly against indexed terms. It does not run an analyzer on the query string. Prefix, wildcard, and regexp belong to this group.

| Query type | Analyzes query string via analyzer? | Purpose |
|---|---|---|
| **match** | Yes | Full-text search |
| **match_phrase** | Yes | Phrase search by token order |
| **term** | No | Exact single-term match |
| **prefix** | No | Find terms starting with a prefix |
| **wildcard** | No | Find terms matching a wildcard pattern |
| **regexp** | No | Find terms matching a regular expression |

For example, the **name** field has the standard analyzer. The content **"Wireless Mechanical Keyboard"** can be analyzed into individual terms such as **wireless**, **mechanical**, and **keyboard**. A prefix query on the name field operates on those generated terms, not as a prefix over the entire original display string.

If the goal is to find product names starting with the entire phrase **"Wireless Me"**, running a prefix query directly on the text field may not deliver the intended behavior. When you need prefix matching on the whole string, consider a separate keyword field, the `search_as_you_type` field type, or a field designed specifically for autocomplete.

## 2. Choosing the Right Mapping Before Querying

Prefix, wildcard, and regexp queries operate on terms in the index. Therefore, the mapping type determines which strings can be matched.

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
          "type": "keyword",
          "normalizer": "lowercase_normalizer"
        }
      }
    },
    "category": {
      "type": "keyword"
    },
    "description": {
      "type": "text",
      "analyzer": "standard"
    }
  }
}
~~~

If using a normalizer, declare it in the index settings:

~~~json
{
  "analysis": {
    "normalizer": {
      "lowercase_normalizer": {
        "type": "custom",
        "filter": [
          "lowercase"
        ]
      }
    }
  }
}
~~~

In the example:

- **sku** is keyword, keeping the code as one intact term.
- **name** is text, split into tokens by the analyzer for full-text search.
- **name.raw** is a keyword multi-field, keeping the name as a single term normalized to lowercase.
- **category** is keyword, suited for exact filtering.
- **description** is text, suited for match queries.

Use **sku** for prefix/wildcard/regexp on product codes. Use **name.raw** if you need pattern matching on the entire name as one string. Use **name** for full-text search. Never select a field solely by property name; inspect the index's actual mapping.

Normalizers apply only to keyword fields. If a normalizer lowercases characters, the term stored in the index is also in normalized form. Term-level queries must follow the same normalization; some queries support a **case_insensitive** option depending on the Elasticsearch version, but you should not rely on that option as a substitute for clean mapping design.

## 3. Prefix Query: Finding Terms Starting with a String

A **prefix query** finds terms whose beginning matches a specified string. For example, finding SKUs starting with **KB-**:

~~~http
POST /products/_search
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

If the index contains SKUs such as:

- KB-1001
- KB-1002
- KB-PRO-01
- MS-2001

then the query above matches terms starting with **KB-**.

A shorthand syntax can also be written:

~~~json
{
  "query": {
    "prefix": {
      "sku": "KB-"
    }
  }
}
~~~

The object form lets you add options such as **case_insensitive** or **rewrite** if supported by your version.

### Prefix on a text field

Suppose the **name** field is analyzed into terms **wireless**, **mechanical**, **keyboard**. The query:

~~~json
{
  "query": {
    "prefix": {
      "name": {
        "value": "key"
      }
    }
  }
}
~~~

can match the term **keyboard**. It does not mean the displayed product name must start with **key**. Prefix is applied to each indexed term.

If you want to find names starting with a user-entered string, consider a keyword multi-field or an autocomplete mapping. For instance, with **name.raw**, prefix applies to the whole normalized name as a single term. For long names, keep any **ignore_above** limit configured on the keyword subfield in mind.

### When should you use prefix?

Prefix is appropriate when:

- Users type the first few characters of an SKU code.
- Filtering by structured codes, region codes, category codes, or patterned identifiers.
- Autocompleting by term prefix.
- The search pattern has a fixed prefix and does not require flexible pattern syntax.

Prefix can often be optimized better than a leading wildcard because Elasticsearch knows the starting portion of the term to look up. Still, cost depends on the number of matching terms, index structure, mapping, and Elasticsearch version. A prefix on a high-cardinality field or a very short prefix can still match many results and consume significant resources.

## 4. Optimizing Prefix with `index_prefixes`

If the application frequently searches prefixes on a text field, the mapping can enable **index_prefixes** to index prefixes according to configuration.

Example:

~~~json
{
  "properties": {
    "name": {
      "type": "text",
      "index_prefixes": {
        "min_chars": 2,
        "max_chars": 10
      }
    }
  }
}
~~~

Elasticsearch creates an additional term structure to serve prefix queries within the configured length range. This can help prefix queries run more efficiently in suitable cases.

Considerations:

- **min_chars** and **max_chars** should reflect common prefix lengths.
- Indexing prefixes increases index size.
- Prefixes shorter than min_chars or longer than max_chars may not receive the same optimization benefit.
- Changing mappings to add index_prefixes typically requires creating a new index and reindexing data.

Do not enable index_prefixes on every field. Use it only when there is a clear prefix requirement and you have evaluated the trade-off between indexing/storage cost and search performance.

## 5. Wildcard Query: Using Wildcard Characters

A **wildcard query** expresses term patterns with two special characters:

- **\*** matches zero or more characters.
- **?** matches exactly one character.

Example finding SKUs starting with KB- and having any remainder:

~~~http
POST /products/_search
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "KB-*"
      }
    }
  }
}
~~~

Example finding codes starting with K, followed by B, then any single character, then 100:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "KB?100"
      }
    }
  }
}
~~~

Wildcard patterns operate on a single term. They do not analyze keywords like a match query. Therefore, use a keyword field or a field specifically designed for the desired term structure.

### Leading wildcard

Patterns starting with **\*** or **?** are usually more expensive:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*100"
      }
    }
  }
}
~~~

Elasticsearch does not know the beginning of the term in advance, so it must inspect many candidate terms. Pattern **\*100** finds every term ending in 100; pattern **\*100\*** finds every term containing 100 anywhere.

Be especially cautious with:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*"
      }
    }
  }
}
~~~

This pattern can match nearly every term having a value in that field and behaves like an extremely broad query. If you only need to check whether a field exists, use an **exists query** instead of wildcard **\***.

### Escaping special characters

If your data contains literal **\*** or **?** characters, escape them according to query syntax and JSON rules. Distinguish wildcard characters in a pattern from literal characters in data. When building queries from user input, escape safely rather than concatenating pattern strings arbitrarily.

### When should you use wildcard?

Wildcard fits simple patterns with prefixes, suffixes, or a few unfixed character positions. If the pattern is purely a prefix, prefer a prefix query. If a pattern starts with a wildcard or contains multiple wildcards, measure performance on production-like data before deploying.

## 6. Regexp Query: Matching Terms by Regular Expression

A **regexp query** finds terms matching a regular expression written in Lucene syntax. This is not full PCRE/Java regex syntax. Elasticsearch uses an automaton to execute expressions; familiar regex features such as backreferences or lookarounds are not supported the same way as in Java/PCRE.

Example finding SKUs starting with KB- followed by one or more digits:

~~~http
POST /products/_search
{
  "query": {
    "regexp": {
      "sku": {
        "value": "KB-[0-9]+"
      }
    }
  }
}
~~~

Common operators in Lucene regexp syntax:

| Syntax | General meaning |
|---|---|
| **.** | Any single character |
| **?** | Zero or one repetition of the preceding expression |
| **\*** | Zero or more repetitions of the preceding expression |
| **+** | One or more repetitions |
| **[abc]** | One character from the set a, b, or c |
| **[0-9]** | One digit from 0 to 9 |
| **(foo\|bar)** | Either branch foo or bar |
| **@** | Any string in Lucene regexp syntax |
| **#** | Empty language in Lucene regexp syntax |

Specific syntax may support additional operators and escaping rules. Consult the regexp query documentation for your running Elasticsearch version before using complex patterns.

### Regexp matches the entire term

A regexp query in Elasticsearch matches the entire indexed term. Example:

~~~json
{
  "query": {
    "regexp": {
      "sku": {
        "value": "KB-[0-9]+"
      }
    }
  }
}
~~~

This pattern matches a term starting with KB- followed by one or more digits. It does not automatically search for a substring in the middle of a term. If arbitrary leading or trailing text must be allowed, express it explicitly with appropriate operators, such as **.*KB-[0-9]+.***, though such broad patterns can be very expensive.

Do not add **^** and **$** out of habit from Java regex to anchor the full term; regexp query semantics already match the whole term. Anchors from other regex engines should not be applied mechanically to Lucene regexp.

### Regexp and automaton complexity

An expression with many alternation branches, nested repetitions, or wide wildcard sections can produce a complex automaton. Elasticsearch bounds complexity via **max_determinized_states**. If an expression exceeds the limit, the request can be rejected to prevent excessive resource consumption.

Example configuring the limit in a query:

~~~json
{
  "query": {
    "regexp": {
      "sku": {
        "value": "KB-(10|20|30)-[0-9]+",
        "max_determinized_states": 10000
      }
    }
  }
}
~~~

Do not increase **max_determinized_states** arbitrarily just to get an overly complex expression accepted. Simplify the pattern, narrow the search scope, or normalize data before indexing.

## 7. Comparing prefix, wildcard, and regexp

| Criterion | Prefix | Wildcard | Regexp |
|---|---|---|---|
| Expressiveness | Fixed prefix | Patterns with * and ? | Regular expression patterns |
| Flexibility | Low | Medium | High |
| Typical cost | Usually lower when prefix is selective | Increases with leading wildcards and broad patterns | Depends on automaton complexity and term count |
| Uses analyzer on query string | No | No | No |
| Common field types | keyword or suitable text terms | keyword or specialized fields | keyword or specialized fields |
| Typical use case | SKUs starting with KB- | Codes with flexible character patterns | Complex structured code rules |
| Risks | Too-short prefix matches too many terms | Broad patterns, especially leading * | Complex patterns, expensive determinization |

Selection rules:

1. If you only need prefix matching, use **prefix**.
2. If you need one or a few wildcards, consider **wildcard**.
3. If a complex pattern is genuinely needed, use **regexp** with limits and testing.
4. If searching natural text, use **match** rather than simulating it with wildcard or regexp.
5. For autocomplete, evaluate **search_as_you_type**, **edge_ngram**, or **index_prefixes** before running broad wildcards over text.

## 8. Where Does Query Cost Come From?

Prefix, wildcard, and regexp are term-level queries. To execute them, Elasticsearch must locate matching terms in each shard's term dictionary structure and collect documents containing those terms.

Cost depends on several factors:

- Number of unique terms in the field.
- Number of terms matching the pattern.
- Pattern length and structure.
- Whether a fixed prefix exists.
- Whether a leading wildcard is present.
- Number of shards and segments to inspect.
- Mappings, normalizers, and configured index optimizations.
- Whether results also require scoring, sorting, aggregations, or highlighting.

A short query syntax is not necessarily cheap. For example, **\*a\*** is short yet can match huge numbers of terms. Conversely, a long regexp with a fixed prefix and selective term set can be less expensive than a very broad wildcard.

### Leading wildcards expand the term search space

Compare:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "KB-10*"
      }
    }
  }
}
~~~

against:

~~~json
{
  "query": {
    "wildcard": {
      "sku": {
        "value": "*10*"
      }
    }
  }
}
~~~

The first pattern has the fixed prefix **KB-10**, allowing Elasticsearch to narrow the range of terms to inspect. The second lacks a fixed prefix and may have to scan a much larger term range.

If the business frequently needs substring search, consider changing the index design rather than relying on leading wildcards on an ordinary keyword field.

## 9. Query Rewrite and Scoring

Prefix, wildcard, and regexp queries can be rewritten into an execution plan based on matching terms. The **rewrite** property controls which rewrite strategy Elasticsearch uses. Some strategies build a Boolean query from expanded terms, while others use constant scoring or approaches suited to large term counts.

Example:

~~~json
{
  "query": {
    "prefix": {
      "sku": {
        "value": "KB-10",
        "rewrite": "constant_score"
      }
    }
  }
}
~~~

Specific rewrite methods and default values can vary across Elasticsearch versions. Do not tweak rewrite based on guesswork. If the query is only filtering codes, scoring is usually unnecessary; place the query in **bool.filter** to express filtering intent.

Example:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "prefix": {
            "sku": {
              "value": "KB-10"
            }
          }
        }
      ]
    }
  }
}
~~~

Filter context does not calculate relevance scores for the prefix condition. This fits when the goal is purely to filter documents by code.

## 10. The `allow_expensive_queries` Setting

Elasticsearch provides the **search.allow_expensive_queries** setting to control certain potentially costly queries. When disabled, queries classified as expensive can be rejected.

Wildcard and regexp commonly fall into the group requiring attention. Prefix queries may also be treated as expensive in certain cases, especially when mappings lack dedicated optimizations; newer versions and optimizations may change specific behavior.

Do not rely on a blanket assumption that every prefix is always allowed when expensive queries are disabled. Check your Elasticsearch version documentation and test the query on a real index under active settings.

You can inspect cluster/index configuration via permitted APIs. If a request is rejected with a message related to expensive queries:

- Identify the exact query type rejected.
- Check the **search.allow_expensive_queries** setting.
- Check whether the mapping has **index_prefixes** or an appropriate field type.
- Consider replacing the query with prefix or a pre-indexed autocomplete field.
- Re-enable expensive queries only after evaluating impact and when operational policy permits.

Do not enable expensive queries cluster-wide just to make one search screen work without bounding inputs and load testing.

## 11. Replacing Broad Wildcards with Suitable Index Design

If the product frequently needs substring search, consider the **wildcard** field type. This field type is designed for content with long strings or wildcard/regexp queries, depending on the data model and Elasticsearch version.

Example mapping:

~~~json
{
  "properties": {
    "log_message": {
      "type": "wildcard"
    }
  }
}
~~~

The wildcard field type fits log messages or long strings where the application needs character pattern matching. It differs in storage and execution from ordinary keyword fields, so measure write cost, index size, and query performance.

For short, structured SKU codes commonly searched by prefix, **keyword** paired with prefix queries is usually simpler. You do not need a wildcard field for every field.

### Using edge_ngram for autocomplete

If users type character by character to search product names, prefixes can be indexed using **edge_ngram**.

Example settings:

~~~json
{
  "analysis": {
    "tokenizer": {
      "name_edge_tokenizer": {
        "type": "edge_ngram",
        "min_gram": 2,
        "max_gram": 15,
        "token_chars": [
          "letter",
          "digit"
        ]
      }
    },
    "analyzer": {
      "name_autocomplete_index": {
        "type": "custom",
        "tokenizer": "name_edge_tokenizer",
        "filter": [
          "lowercase"
        ]
      },
      "name_autocomplete_search": {
        "type": "custom",
        "tokenizer": "standard",
        "filter": [
          "lowercase"
        ]
      }
    }
  }
}
~~~

Mapping:

~~~json
{
  "properties": {
    "name_suggest": {
      "type": "text",
      "analyzer": "name_autocomplete_index",
      "search_analyzer": "name_autocomplete_search"
    }
  }
}
~~~

When indexing **Wireless Keyboard**, edge_ngram can generate prefixes such as **wi**, **wir**, **wire**, ... for each token. The search analyzer uses the standard tokenizer to analyze user input.

This trades query-time cost for index-time and storage cost: the index holds more terms, while autocomplete queries become simpler and faster. Choose min_gram/max_gram based on real typing behavior; do not set max_gram unnecessarily large.

## 12. Combining prefix, wildcard, or regexp with a bool Query

These queries can be combined with other filters in a bool query.

Example finding SKUs starting with KB-, keeping only ACTIVE products priced 50 and up:

~~~http
POST /products/_search
{
  "query": {
    "bool": {
      "filter": [
        {
          "prefix": {
            "sku": {
              "value": "KB-"
            }
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
              "gte": 50
            }
          }
        }
      ]
    }
  }
}
~~~

Example filtering codes with wildcard:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "wildcard": {
            "sku": {
              "value": "KB-*-BLK"
            }
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

Example filtering codes with regexp:

~~~json
{
  "query": {
    "bool": {
      "filter": [
        {
          "regexp": {
            "sku": {
              "value": "KB-[0-9]{4}"
            }
          }
        },
        {
          "term": {
            "category": "accessories"
          }
        }
      ]
    }
  }
}
~~~

The examples above place conditions in **filter** because they narrow the document set rather than ranking relevance. If the query also needs content-based scoring, separate the full-text part into must while keeping code/status conditions in filter.

## 13. Using These Queries in Spring Data Elasticsearch

Spring Data Elasticsearch offers multiple ways to build queries. For simple term-level queries, Criteria can be used if your API version supports the corresponding operation. When exact JSON control is needed, **StringQuery** or **NativeQuery** is usually clearer.

### Using StringQuery

StringQuery accepts a query DSL string. Prefix example:

~~~java
import org.springframework.data.elasticsearch.core.query.Query;
import org.springframework.data.elasticsearch.core.query.StringQuery;

String dsl = """
{
  "prefix": {
    "sku": {
      "value": "KB-"
    }
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

Wildcard example:

~~~java
String dsl = """
{
  "wildcard": {
    "sku": {
      "value": "KB-*-BLK"
    }
  }
}
""";

Query query = new StringQuery(dsl);
~~~

Regexp example:

~~~java
String dsl = """
{
  "regexp": {
    "sku": {
      "value": "KB-[0-9]{4}"
    }
  }
}
""";

Query query = new StringQuery(dsl);
~~~

The JSON strings above contain only the query clause. Spring Data embeds them into the search request at execution time. Do not pass an entire request body containing **from**, **size**, and **query** to the StringQuery constructor when it expects just the query clause.

When building patterns from user input, validate length, wildcards, and syntax. Never concatenate arbitrary input directly into JSON query strings. Use typed builders or serializers to prevent JSON errors and restrict overly broad patterns.

### Using NativeQuery

In Spring Data Elasticsearch 5.x, NativeQuery lets you use the Elasticsearch Java API Client builder. Prefix example:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.prefix(p -> p
                .field("sku")
                .value("KB-")))
        .build();

SearchHits<Product> hits = operations.search(
        query,
        Product.class,
        IndexCoordinates.of("products")
);
~~~

Wildcard example:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.wildcard(w -> w
                .field("sku")
                .value("KB-*-BLK")))
        .build();
~~~

Regexp example:

~~~java
NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.regexp(r -> r
                .field("sku")
                .value("KB-[0-9]{4}")))
        .build();
~~~

These builders illustrate expressing Query DSL via the Java API Client. Package names, value types, overloads, and options such as case_insensitive/rewrite depend on the Spring Data Elasticsearch and Elasticsearch Java API Client versions. Use the dependencies managed by Spring Boot and verify compilation against your project version.

### Using Criteria when appropriate

The Criteria API offers operations such as **startsWith**, **contains**, or matching predicates depending on the version. They can express some prefix/wildcard cases without writing JSON. However, do not assume every Criteria method generates the exact query or options you want.

When cost, rewrite, case-insensitivity, or query structure matters, use StringQuery/NativeQuery to specify the DSL explicitly. Then inspect the actual request sent to Elasticsearch.

## 14. Bounding Inputs to Avoid Overly Broad Queries

If users can enter wildcards or regexps directly, the application should enforce input validation rules. A search endpoint should not allow arbitrary user-supplied patterns, especially on large indices or under heavy concurrency.

Some safeguards:

- Limit pattern length.
- Require a minimum prefix length, such as at least 2 or 3 characters depending on the data.
- Reject leading wildcards if the business does not need substring search.
- Limit OR branches and regexp complexity.
- Allow only valid characters for SKUs.
- Use appropriate timeouts at the search request level.
- Paginate and cap page size.
- Rate limit search endpoints.
- Monitor slow query rate and rejected request counts.
- Do not let users arbitrarily control the full Query DSL when they only need simple search.

Example preliminary SKU prefix check in a service:

~~~java
public String validateSkuPrefix(String prefix) {
    if (prefix == null || prefix.length() < 3 || prefix.length() > 20) {
        throw new IllegalArgumentException("Prefix must be between 3 and 20 characters");
    }

    if (!prefix.matches("[A-Za-z0-9-]+")) {
        throw new IllegalArgumentException("Prefix contains invalid characters");
    }

    return prefix;
}
~~~

This is application-layer input validation, not a replacement for Elasticsearch validation. Actual rules should reflect the system's SKU format. If valid SKUs include other characters, adjust the allowlist.

For regexp, provide fixed business templates instead of letting users submit arbitrary regexes. For example, the user chooses a code type and enters digits; the service constructs a controlled pattern.

## 15. Measuring Query Performance

You cannot determine query cost from the query name alone. Measure on an index whose term distribution resembles production data.

Testing steps:

1. Create a dataset representative of term volume and cardinality.
2. Run prefix, wildcard, and regexp with realistic patterns.
3. Compare fixed-prefix patterns against leading wildcards.
4. Check hit counts, latency, and node resource usage.
5. Use profile when locating expensive execution parts.
6. Test with shard counts and mappings close to deployment.
7. Measure write latency and index size as well if adding index_prefixes, edge_ngram, or wildcard fields.

You can enable **profile** in a request to inspect execution details:

~~~http
POST /products/_search
{
  "profile": true,
  "query": {
    "wildcard": {
      "sku": {
        "value": "*100*"
      }
    }
  }
}
~~~

Profile adds overhead to the request and typically produces large responses. Use it only during investigation, not by default on production traffic.

Monitor Elasticsearch slow logs to catch queries exceeding time thresholds. Combine application metrics such as response time, request volume, and used patterns to identify endpoints or pattern types causing load.

## 16. Common Pitfalls

| Symptom | Possible cause | How to resolve |
|---|---|---|
| Prefix fails to find display strings starting with prefix | Query runs against text field terms rather than the full string | Use a keyword subfield or a suitable autocomplete field |
| Prefix is unexpectedly case-sensitive | Indexed terms have different casing than query | Use a normalizer or case-insensitive option if supported |
| Wildcard query is slow | Pattern has a leading wildcard or matches too many terms | Prefer prefix, restrict patterns, or adjust mapping |
| Regexp is rejected | Pattern produces an overly complex automaton or exceeds limit | Simplify expression and check max_determinized_states |
| Query is rejected as expensive | Cluster disables search.allow_expensive_queries or query lacks optimization | Inspect settings and redesign query/index |
| Java regex errors in Elasticsearch | Lucene regexp syntax differs from Java/PCRE | Convert pattern to Lucene syntax and consult docs |
| Cannot search substrings with prefix | Prefix only matches the start of a term | Use wildcard or design n-gram/wildcard field if truly needed |
| Wildcard * returns too many results | Pattern is overly broad | Use exists query if merely checking field presence |
| Mapping changed but query acts the same | Existing index has not been recreated/reindexed | Create a new index and reindex if mapping must change |
| Query is syntactically valid but returns zero hits | Wrong field, analyzer, normalizer, or data lacks matching terms | Inspect mapping, use _analyze on text fields, and check actual terms |

## 17. Process for Choosing a Query in Applications

When building partial-string search, you can apply this process:

1. **Define the goal.** Is the user searching prefixes, suffixes, substrings, or code patterns?
2. **Inspect the mapping.** Is the field text, keyword, or wildcard? Are there normalizers or multi-fields?
3. **Choose the narrowest query.** Prefix for prefixes; wildcard for simple character patterns; regexp when complex pattern rules are needed.
4. **Evaluate the analyzer.** Term-level queries do not analyze the query string; ensure terms and inputs are normalized compatibly.
5. **Bound inputs.** Block overly broad patterns, unnecessary leading wildcards, and complex regexps.
6. **Consider index optimizations.** Use index_prefixes, edge_ngram, search_as_you_type, or wildcard fields matching the exact requirement.
7. **Measure performance.** Use representative data, slow logs, and profile when needed.
8. **Check cluster settings.** Verify search.allow_expensive_queries and related limits.
9. **Integrate Spring Data.** Use Criteria if expressive enough; use StringQuery or NativeQuery when DSL control is needed.
10. **Verify actual requests.** Confirm fields, patterns, rewrite, and options sent are accurate.

Prefix, wildcard, and regexp can all search partial terms, but flexibility comes with cost. Prefix should be evaluated first when users search by prefix. Wildcard fits simple character patterns while avoiding broad leading wildcards. Regexp should be used only when pattern rules are genuinely necessary, with complexity limits enforced. When search needs are recurring and predictable, mapping designs like index_prefixes, edge_ngram, or wildcard fields usually control cost much better than sending arbitrary expanded queries.
