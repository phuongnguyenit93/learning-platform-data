# Like, StartingWith, EndingWith, and Containing

Spring Data Elasticsearch lets you declare search methods based on repository method names. For string properties, keywords such as Like, StartingWith, EndingWith, and Containing describe different forms of text matching. They make queries concise to write, but they do not mean Elasticsearch is executing a SQL LIKE statement.

To use them properly, you need to understand three things: which Elasticsearch query type Spring Data translates the method keyword into; how that query operates on indexed terms; and whether the field is text or keyword. These differences directly affect results, case sensitivity, and performance.

## 1. Query derivation from method names

### 1.1. How does Spring Data read method names?

When a repository declares a method without an implementation, Spring Data parses the method name to determine:

- The entity and property to query.
- Filtering conditions.
- The requested matching mode.
- Combined conditions using And or Or.
- Sorting or pagination information if present.

Example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByNameStartingWith(String prefix);

    List<ProductDocument> findByNameEndingWith(String suffix);

    List<ProductDocument> findByNameContaining(String fragment);

    List<ProductDocument> findByNameLike(String pattern);
}
~~~

Spring Data generates implementations for these methods according to the query derivation rules supported by your project's Spring Data Elasticsearch version.

Property names in the method are normally Java property names. If the entity has:

~~~java
@Field(name = "product_name", type = FieldType.Keyword)
private String name;
~~~

the method still uses findByNameStartingWith. Spring Data inspects metadata to map property name to the Elasticsearch field product_name.

### 1.2. Four keywords describing four search intents

Suppose the data contains the names:

~~~text
Wireless Keyboard
Keyboard Cover
Mechanical Keyboard
Keyboard Wireless Adapter
~~~

With search string key, the four search intents differ:

| Keyword | Meaning on a String property | Illustration |
|---|---|---|
| StartingWith | Value or term starts with the input string | key... |
| EndingWith | Value or term ends with the input string | ...key |
| Containing | Value or term contains the input string | ...key... |
| Like | Pattern match per the version's query creator semantics | Depends on pattern and mapping |

StartingWith works well when users enter the beginning of a product name or code. EndingWith fits when suffixes are meaningful. Containing fits when users may enter a middle fragment. Like is meant for pattern queries when the implementation's pattern syntax matches your requirements.

Do not assume the four keywords are interchangeable. They can generate different query types with different execution costs.

### 1.3. Like is not SQL LIKE

In SQL, LIKE commonly uses wildcards % for multiple characters and _ for a single character. Elasticsearch does not have a SQL LIKE operator equivalent in standard Query DSL.

Spring Data Elasticsearch translates methods into Elasticsearch queries according to the rules of the version in use. Depending on the operator, the query may use prefix, wildcard, or another pattern query form. Therefore:

- Do not assume %abc% carries the same meaning as in SQL.
- Do not assume the _ character is always interpreted like SQL.
- Do not assume a Like method automatically analyzes text like a match query.
- Do not guess the exact JSON DSL sent solely from the method name.

When a specific pattern syntax is required, check the documentation for your exact version and inspect the actual generated query. When precise control over wildcard, regexp, or query string is needed, use @Query or ElasticsearchOperations.

## 2. StartingWith: prefix search

### 2.1. Meaning

StartingWith is used when searching for values or terms that start with the passed string.

~~~java
List<ProductDocument> findByNameStartingWith(String prefix);
~~~

Invocation:

~~~java
List<ProductDocument> products =
    productRepository.findByNameStartingWith("Wire");
~~~

With product names stored as whole-string keywords, the intent is to find names starting with Wire, such as Wireless Keyboard and Wireless Adapter.

At the Elasticsearch layer, prefix search typically corresponds to a prefix query. A prefix query checks whether terms in the inverted index start with the specified string.

### 2.2. Prefix queries operate on indexed terms

A prefix query is not simply running startsWith on the entire raw JSON string. It operates against terms in the inverted index.

If the field is keyword, the entire value is typically indexed as a single term. For example:

~~~json
{
  "name": "Wireless Keyboard"
}
~~~

With a keyword field, the term can be the whole string Wireless Keyboard. Prefix Wire can match that term.

If the field is text using the standard analyzer, the string above is typically split into terms such as:

~~~text
wireless
keyboard
~~~

Then prefix wire can match the term wireless. However, prefix wireless key is not the prefix of any single term because the text was split into two terms.

Therefore, determine clearly whether the application wants prefixes across the entire value or prefixes on individual tokens. Those two requirements may call for different mappings.

### 2.3. Use cases

StartingWith is commonly suitable for:

- Suggesting names as the user types.
- Searching product codes by leading prefix.
- Looking up usernames or identifiers with prefix conventions.
- Finding organization or category names starting with the entered string.

For type-ahead suggestions, limit result counts and return only the fields needed for display. If data volume is large and autocomplete requirements are complex, consider edge n-grams or a completion suggester instead of firing prefix queries on every keystroke.

## 3. EndingWith: suffix search

### 3.1. Meaning

EndingWith is used when the target string appears at the end of a value or term.

~~~java
List<ProductDocument> findByNameEndingWith(String suffix);
~~~

Example call:

~~~java
List<ProductDocument> products =
    productRepository.findByNameEndingWith("Pro");
~~~

The intent is to find values ending with Pro. The Elasticsearch query type commonly used for this requirement is a wildcard with a leading wildcard character, such as the conceptual pattern *Pro.

### 3.2. Suffixes are typically costlier than prefixes

A prefix query can leverage the term dictionary structure to narrow down the range of terms starting with a string. A wildcard query with a leading wildcard character is harder to bound in the term dictionary and may have to inspect many terms.

Therefore, suffix search can consume significant resources on large indexes or high-cardinality fields.

Do not use EndingWith on every field simply because the method is easy to write. Assess term counts, query frequency, string lengths, and load limits. For frequent suffix searches over large datasets, you may need to design a reversed-string field or a dedicated index structure to turn the suffix problem into a prefix problem.

### 3.3. Reversed-field example

One strategy is storing an additional reversed value:

| Original value | Reversed value |
|---|---|
| Wireless | sseleriW |
| Keyboard | draobyeK |
| Adapter | retpadA |

When a user searches for suffix less, the application reverses the string to ssel and runs a prefix search on the reversed field.

This approach requires consistent case normalization, proper Unicode handling, and maintaining the auxiliary field on writes. It is not created automatically by EndingWith alone; it is a separate mapping/ingestion design. Use it only when performance measurements justify the benefit.

## 4. Containing: searching for a string anywhere

### 4.1. Meaning

Containing on a String property expresses the intent to find a substring appearing somewhere in the value.

~~~java
List<ProductDocument> findByNameContaining(String fragment);
~~~

Example:

~~~java
List<ProductDocument> products =
    productRepository.findByNameContaining("less");
~~~

With original value Wireless Keyboard, the string less appears in the middle of the word Wireless.

One way to represent substring intent at the wildcard layer is a pattern like *less*. Wildcard characters on both ends allow content before and after the fragment.

### 4.2. Containing on text is not the same as whole-sentence substring

This is a very important distinction. If the name field has type text, the analyzer may split:

~~~text
Wireless Keyboard
~~~

into two terms:

~~~text
wireless
keyboard
~~~

Wildcard queries are applied to indexed terms. They can find a fragment inside a single term such as less in wireless, but cannot find a substring spanning across two terms such as ss key if that string does not exist within an individual term.

If the requirement is substring matching across the entire original value, store the value as keyword or in a dedicated field. If the requirement is searching content by words/meaning, full-text queries such as match are usually more appropriate.

### 4.3. When should Containing be used?

Containing fits moderate-sized datasets, clear substring requirements, and moderate query rates. Examples:

- Finding a code segment inside a reference code.
- Finding a short name fragment on a keyword field.
- Finding a character sequence inside a structured value.
- Internal data lookups at small scale with measured performance.

For searching long content, prefer analyzers and full-text queries rather than turning every search into a wildcard. Users typically want to search by words or phrases rather than needing mid-token substrings.

## 5. Like: pattern-based querying

### 5.1. Intent of Like

The method name findByNameLike expresses pattern-based querying. However, pattern syntax and the generated query type depend on your project's Spring Data Elasticsearch implementation version.

Example declaration:

~~~java
List<ProductDocument> findByNameLike(String pattern);
~~~

Do not assume the passed pattern uses SQL syntax. Nor should you automatically add wildcard characters into the argument before knowing whether the query creator already adds pattern wrapping. If the method adds wildcards under its own semantics and the application also supplies wildcards, the resulting pattern may differ from intent.

The safe approach is writing integration tests for critical patterns and inspecting the actual generated query. If patterns must support advanced syntax, write explicit Query DSL.

### 5.2. Distinguishing wildcard and regexp

Elasticsearch supports multiple pattern query types:

- **Wildcard query** supports * for any sequence of characters and ? for a single character.
- **Regexp query** supports regular expressions using Lucene syntax.
- **Query string** has its own syntax, including operators and special characters.

These syntaxes are not equivalent. Wildcards are not regex; a . character in wildcard does not carry the same meaning as a dot in regex. Query string also has its own escaping rules.

When search requirements need a specific pattern syntax, choose the right query type and escape inputs according to that syntax. Never concatenate untrusted input directly into JSON queries or query strings.

## 6. Mapping determines results

### 6.1. Keyword fields

A keyword field keeps a value as a single term and is suited for exact matching, sorting, aggregations, or pattern matching across the full value.

Example:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Keyword)
    private String name;
}
~~~

With a keyword field, pattern queries can act on the entire name as one term. This is often the right choice when the application needs prefix, suffix, or substring search over entire short name strings.

However, keyword fields are subject to Lucene term length limits and are not a solution for all long content. For long text, use text and design auxiliary fields as needed.

### 6.2. Text fields

Text fields are processed by an analyzer. Example:

~~~java
@Field(type = FieldType.Text, analyzer = "standard")
private String description;
~~~

The analyzer may lowercase, tokenize, remove stop words, or stem terms. Prefix/wildcard queries operate on indexed terms, so results are no longer equivalent to operating on the original raw string.

A string Wireless Keyboard may become two terms. A substring within one term can be found; a substring crossing spaces or token boundaries cannot.

### 6.3. Using multi-fields for multiple needs

A property may need both full-text search and exact/pattern search. You can declare a multi-field:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text, analyzer = "standard"),
    otherFields = {
        @InnerField(suffix = "raw", type = FieldType.Keyword)
    }
)
private String name;
~~~

Then:

- name serves full-text search.
- name.raw preserves the entire value as keyword for exact matching, sorting, or pattern search.

Query derivation typically references Java properties, so if you need to query a specific subfield, you may need to use Query DSL targeting field name.raw rather than assuming method names can express arbitrary multi-field paths.

### 6.4. Normalizers and case sensitivity

Keyword fields preserve case by default. Therefore, pattern wire may not match the term Wireless Keyboard when casing differs.

You can configure a normalizer on a keyword field, such as lowercase:

~~~json
{
  "settings": {
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "name": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
~~~

A normalizer processes the entire keyword value according to configured rules prior to indexing. Pattern queries still need to be sent in a form compatible with normalized terms; do not assume every query type automatically runs the same normalizer as a match query.

Some Elasticsearch versions support a case-insensitive option on certain queries. That capability depends on version and query API; verify before relying on it. Consistent normalization at write time and query time is usually more predictable.

## 7. Complete repository example

### 7.1. Declaring name-search methods

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByNameStartingWith(String prefix);

    List<ProductDocument> findByNameEndingWith(String suffix);

    List<ProductDocument> findByNameContaining(String fragment);

    List<ProductDocument> findByNameLike(String pattern);
}
~~~

These methods illustrate naming patterns. Before using them in a project, verify supported operators and actual Query DSL against your exact Spring Data Elasticsearch version.

### 7.2. Limiting results

Do not return unbounded results when users enter a very short string. You can use Pageable if the method and version support it:

~~~java
Page<ProductDocument> findByNameStartingWith(
    String prefix,
    Pageable pageable
);
~~~

Invocation:

~~~java
Pageable pageable = PageRequest.of(0, 10);

Page<ProductDocument> page =
    productRepository.findByNameStartingWith("Wire", pageable);
~~~

Limit page sizes, validate input length, and apply rate limiting to autocomplete endpoints. A single-character input can match huge numbers of terms and generate expensive queries.

### 7.3. Combining with other conditions

You can combine a category filter with a name query if query derivation supports it:

~~~java
List<ProductDocument> findByCategoryAndNameStartingWith(
    String category,
    String prefix
);
~~~

Method names use Java properties. The category condition should typically apply to a keyword field; name must have a mapping matching the expected prefix semantics.

If you need multiple branches, boosting, or optional conditions, consider @Query or ElasticsearchOperations so the query is expressed clearly.

## 8. When query derivation is not enough: writing explicit queries

### 8.1. Prefix query with @Query

When you want to be certain the query type is prefix, you can declare a JSON query:

~~~java
@Query("""
{
  "prefix": {
    "name.raw": {
      "value": "?0"
    }
  }
}
""")
List<ProductDocument> searchNamePrefix(String prefix);
~~~

This example assumes the index has a keyword multi-field name.raw. Verify annotation placeholder syntax against your Spring Data Elasticsearch version.

### 8.2. Wildcard query for substrings

Wildcard example:

~~~java
@Query("""
{
  "wildcard": {
    "name.raw": {
      "value": "*?0*"
    }
  }
}
""")
List<ProductDocument> searchNameContaining(String fragment);
~~~

This example illustrates Query DSL and placeholders. When using dynamic input, ensure special characters are handled according to wildcard syntax and cannot alter query intent. If exact escaping or complex patterns are needed, construct queries via API instead of manual string assembly.

Wildcards with a leading * can be expensive. Avoid using them on large indexes without measuring performance and evaluating n-gram designs.

### 8.3. Prefix, wildcard, and match differ

| Query | Purpose | Input analysis |
|---|---|---|
| prefix | Terms starting with a string | Does not act like a full-text analyzer |
| wildcard | Pattern with wildcards over terms | Not equivalent to match analyzer |
| match | Search text content after analyzing query | Uses analyzer |
| match_phrase | Search token sequence with positional ordering | Uses analyzer |

If a user enters wireless keyboard to search for content containing those two words, match or match_phrase is usually more suitable than wildcard *wireless keyboard*. If a user enters wire to autocomplete a term, a prefix query is more appropriate.

## 9. Performance and limits of pattern queries

### 9.1. Prefixes are usually easier to optimize than leading wildcards

Prefix queries constrain terms by their leading characters and can generally leverage the term dictionary structure better. Wildcards like *fragment or *fragment* have leading wildcards, widening the term space to inspect.

You cannot assume every prefix query is always cheap or every wildcard query is always slow. Performance depends on term count, pattern selectivity, index size, caching, shards, and cluster load.

### 9.2. Expensive queries

Elasticsearch provides the search.allow_expensive_queries setting. When expensive queries are disabled, certain wildcard, regexp, or pattern queries may be rejected depending on query type and version.

Therefore, a query that works locally might not be allowed in production. Check cluster policies and test under production-like settings.

Do not re-enable expensive queries merely to make a method run without evaluating cluster impact. Instead, consider changing indexing design or query type.

### 9.3. N-grams and edge n-grams

If substring or autocomplete queries occur at high frequency, you can index additional n-gram tokens:

- **Edge n-grams** generate prefixes from the start of tokens, fitting autocomplete.
- **N-grams** generate contiguous character slices inside tokens, fitting substring search.

For example, the word keyboard can produce edge n-grams like k, ke, key, keyb... with appropriate min/max gram limits.

This increases index size and indexing time, but query-time execution is typically simpler than scanning wildcards over many terms. Choose min_gram/max_gram based on user input lengths and Elasticsearch limits.

### 9.4. Using the wildcard field type when appropriate

Elasticsearch offers the wildcard field type for pattern searches on long strings or high-cardinality fields tailored to that field type's characteristics. It uses different storage and processing than keyword/text.

Do not convert all fields to the wildcard type. Read the Elasticsearch version documentation, evaluate your workload, and benchmark before choosing it. This field type does not replace analyzers for full-text search.

## 10. Protecting queries and inputs

### 10.1. Validating user input

Pattern queries can contain syntax control characters such as *, ?, backslashes, or other special characters depending on query type. If users are allowed to enter free-form patterns, define clearly whether they are permitted to use wildcards or only literal substrings.

Common safeguards include:

- Limiting search string length.
- Stripping or escaping special characters according to query type.
- Rejecting patterns consisting solely of wildcards.
- Enforcing limits on page size and result count.
- Rate-limiting autocomplete/search endpoints.
- Never concatenating raw input into query strings or JSON without escaping.
- Monitoring timeouts and rejected requests.

Escaping rules for wildcard, regexp, and query string differ. Do not use one generic escape function across all query types.

### 10.2. Preventing input from turning into an unintended broad query

If an endpoint is meant to search literal substrings, a user entering * should not accidentally ask to match every term. Likewise, a regex can express an overly broad pattern and cause heavy load.

Distinguish two product modes clearly:

- **Literal search**: the user enters plain text, and the application builds and escapes the query properly.
- **Advanced pattern search**: the user is permitted to enter wildcard/regex syntax with clear limits and documentation.

Do not mix the two modes without an explicit contract.

## 11. Testing actual behavior

### 11.1. Creating sample data

A small set of documents helps verify whether queries match as expected:

~~~json
[
  { "id": "1", "name": "Wireless Keyboard" },
  { "id": "2", "name": "Keyboard Cover" },
  { "id": "3", "name": "Mechanical Keyboard" },
  { "id": "4", "name": "Wireless Adapter" },
  { "id": "5", "name": "Keychain" }
]
~~~

Test cases:

| Method/intent | Input | What to verify |
|---|---|---|
| StartingWith | Wire | Does it match terms or values starting with Wire according to mapping? |
| EndingWith | board | Does it match the expected suffix? |
| Containing | less | Does it match the substring within terms? |
| Like | Test pattern | Under which syntax is the pattern interpreted in the current version? |

Do not test only a single match. Include data with mixed casing, diacritics, punctuation, whitespace, wildcard characters, and multiple tokens.

### 11.2. Inspecting mappings and tokens

Use the mapping API to see whether a field is actually text or keyword:

~~~http
GET /products/_mapping
~~~

If the field is text, inspect the analyzer:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Wireless Keyboard"
}
~~~

The Analyze API shows the generated tokens, explaining why a prefix or wildcard matches part of a token rather than the entire string.

### 11.3. Verifying queries generated by Spring Data

For query derivation, enable appropriate logging for Spring Data Elasticsearch/client in the test environment and observe the DSL requests. Exact logger configuration depends on the client and application version.

An integration test should verify:

1. Repository method initializes cleanly.
2. The actual query sent to Elasticsearch.
3. The returned set of IDs matches the sample data.
4. Case sensitivity matches requirements.
5. Pagination limits result counts.
6. Patterns containing special characters are handled properly.
7. Queries do not produce abnormal load or timeouts on realistic data.

Unit tests that merely mock the repository cannot verify query derivation or Elasticsearch semantics. Integration tests with a compatible Elasticsearch instance are needed.

## 12. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| StartingWith does not match expected start of name | Text field was tokenized or analyzer altered data | Inspect mapping, analyzer, and actual terms |
| EndingWith is very slow | Query requires a leading wildcard | Measure load; consider a reversed field or different structure |
| Containing fails to match across spaces | Query operates on individual terms, not full raw string | Use a keyword field for full-value substrings or match query for word search |
| Like ignores % characters | SQL wildcards are not Elasticsearch's default syntax | Check query creator and use the right Query DSL type |
| Searching wire misses Wireless | Case mismatch or different term normalization | Use a suitable normalizer/analyzer and inspect the query |
| Text query returns more results than expected | Analyzer splits or normalizes tokens | Check _analyze, use a keyword subfield if exact matching is needed |
| Pattern query is rejected | Cluster blocks expensive queries or input is invalid | Check cluster policy, query type, and pattern |
| Input * returns too many results | Wildcard was interpreted as pattern syntax | Escape literal input or restrict patterns |
| Query method fails to be created | Operator/property unsupported in version | Check method parser and switch to @Query if needed |

## 13. Choosing the right tool for the requirement

| User requirement | Recommended approach |
|---|---|
| Type start of name for suggestions | Prefix query or edge n-gram/completion |
| Find names ending with a fragment | Wildcard suffix, reversed field if high frequency |
| Find substring in short names | Keyword + wildcard, or n-gram under high workload |
| Find words in descriptions | Match query with appropriate analyzer |
| Find exact full phrase | Match phrase |
| Search pattern with wildcard syntax | Wildcard query with input control |
| Search regex pattern | Regexp query with pattern limits |
| Exact match on full value | Keyword field and term query |

Do not pick a method just because its name sounds close to the business requirement. Identify whether users want to search by whole value, analyzed terms, prefixes/suffixes, or character patterns. Then choose the matching mapping and query.

## 14. Key takeaways

- StartingWith expresses prefix search; EndingWith expresses suffix search; Containing searches for an inner fragment; Like performs pattern matching per query creator semantics.
- These keywords do not mean Elasticsearch runs SQL LIKE.
- Prefix/wildcard queries operate on indexed terms; text analyzers can split a string into multiple terms.
- Keyword fields fit patterns over entire short values; text fields fit full-text search.
- Case sensitivity depends on how terms are indexed/normalized and on query type.
- Leading wildcards are generally costlier than prefixes; large-scale substring search may need n-grams.
- Query derivation is convenient for simple conditions; use @Query or ElasticsearchOperations when DSL control is needed.
- Always verify supported operators and actual queries on your exact Spring Data Elasticsearch version.
- Test against a real Elasticsearch instance or test container to verify results, mappings, and performance.

Understanding the relationship between method names, Query DSL, and mappings lets you pick the right name-search strategy, explain why a query returns or misses documents, and avoid turning a simple autocomplete feature into an expensive index-wide wildcard scan.
