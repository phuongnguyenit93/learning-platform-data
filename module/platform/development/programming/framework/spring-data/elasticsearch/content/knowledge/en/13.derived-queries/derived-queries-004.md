# In, NotIn, and Differences Between keyword and text Types

In Spring Data Elasticsearch, the derived query keywords In and NotIn allow filtering documents by a set of values. For example, you can find products belonging to one of several categories or exclude products in certain statuses.

A key detail to understand well is that In and NotIn are commonly translated into Elasticsearch terms queries. A terms query matches indexed terms; it does not behave like whole-string comparison in Java or SQL in all cases. Results therefore depend directly on the field's mapping:

- With a keyword field, each value is typically indexed as a single intact value. In is close to checking whether the field is in the value set.
- With a text field, content is split into tokens by an analyzer. In may match an individual token rather than the full sentence or original string.

Understanding this difference helps you avoid using In on a text field when the real goal is comparing full names, and helps you choose the right query when full-text search is needed.

## 1. Meaning of In and NotIn

In a Spring Data Elasticsearch repository, you can declare methods such as:

~~~java
import java.util.Collection;
import java.util.List;

import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategoryIn(Collection<String> categories);

    List<Product> findByCategoryNotIn(Collection<String> categories);
}
~~~

Spring Data parses the method name to identify the entity property, operator, and parameter type. In the example:

- findByCategoryIn finds documents whose category matches at least one value in the collection.
- findByCategoryNotIn finds documents that do not match any value in the collection.

Logically, if the passed value set is A, In corresponds to the condition that the field value belongs to A. NotIn corresponds to the condition that the field value does not belong to A.

This resembles SQL's IN operator, but remember that Elasticsearch queries indexed documents and can have multi-valued fields, missing fields, or analyzed text fields. Those cases produce results different from thinking in terms of a single-valued SQL column.

## 2. In is commonly implemented using a terms query

Elasticsearch provides the terms query to find documents where a field matches at least one of the supplied values.

REST API example:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "terms": {
      "category": ["books", "electronics", "home"]
    }
  }
}
~~~

This query matches documents whose category is books, electronics, or home. You can think of a terms query as an OR across term values on the same field.

When using the repository method findByCategoryIn, Spring Data Elasticsearch may generate a corresponding terms query. Implementation details and the exact query generated can vary across release trains, so when you need to confirm exact behavior in your version, inspect actual requests or enable appropriate logging.

A terms query is a term-level query. It is not the same as a match query:

| Query | How search values are processed | Purpose |
|---|---|---|
| terms | Matches the supplied terms | Check whether a field matches one of several values |
| term | Matches a single term | Find an exact value or exact token |
| match | Analyzes the search string with the field's analyzer | Full-text search |
| match_phrase | Analyzes text and checks phrase token order and positions | Phrase search |

Therefore, choosing In versus a full-text search method must be based on the field's data type and semantics.

## 3. Keyword: suitable for In and NotIn on intact values

Keyword fields are designed for data requiring exact matching, such as:

- Product codes.
- Customer IDs.
- Order statuses.
- Category names.
- Country codes.
- Labels or tags.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "category": {
        "type": "keyword"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

With this mapping, the document:

~~~json
{
  "category": "electronics",
  "status": "active"
}
~~~

is indexed with the corresponding keyword values. The repository method:

~~~java
List<Product> findByCategoryIn(Collection<String> categories);
~~~

with categories containing books and electronics will return products whose category equals one of those two values.

Similarly:

~~~java
List<Product> findByStatusNotIn(Collection<String> statuses);
~~~

with statuses containing archived and deleted will exclude documents whose status matches either value.

### 3.1. Keyword is exact matching, not substring search

Suppose the category field has value electronics. An In query with electronics can match; querying with lectro or electronic does not match just because it is part of the string.

Likewise, without a normalizer, keyword is typically case-sensitive:

~~~text
Indexed value: Electronics
Query value:   electronics
Result:        does not match by exact term
~~~

If business logic requires case-insensitive matching, normalize data before writing or configure a normalizer on the keyword field. Ensure write-time and query-time normalization are consistent.

### 3.2. Keyword with a normalizer

Example settings and mapping declaring a lowercase normalizer:

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
      "category": {
        "type": "keyword",
        "normalizer": "lowercase_normalizer"
      }
    }
  }
}
~~~

Category values are then normalized according to the normalizer. Term-level queries on a keyword field with a normalizer are processed by Elasticsearch using the field's normalizer rules, enabling case-insensitive matching in this scenario.

Normalizers must be declared when creating the appropriate mapping. If an existing index already has a keyword field without a normalizer, adding an annotation in Java alone will not modify the existing mapping.

## 4. Text: In does not mean comparing the entire string

Text fields are designed for full-text search. At index time, an analyzer processes the string into tokens. For example, with the standard analyzer, the text:

~~~text
Wireless Mechanical Keyboard
~~~

may be analyzed into the terms:

~~~text
wireless
mechanical
keyboard
~~~

A terms query does not run the analyzer like a match query. It compares the passed terms against terms already in the inverted index.

Suppose the entity is:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    // other fields
}
~~~

And a document has name Wireless Mechanical Keyboard. The method:

~~~java
List<Product> findByNameIn(Collection<String> names);
~~~

should not be interpreted as finding products whose entire name equals one of the input strings as in standard string comparison. If the argument contains Wireless Mechanical Keyboard, a terms query may fail to find it because the indexed terms are individual tokens rather than the full string.

If the argument contains wireless, the query can match because that is an indexed term. Depending on the analyzer, casing and punctuation in the source data may have been normalized or split into different tokens.

### 4.1. Illustrating the difference

Suppose a document has name:

~~~text
Wireless Mechanical Keyboard
~~~

And the analyzer produces the three tokens above:

| Value passed to In | Possible result | Reason |
|---|---|---|
| wireless | Matches | Matches an indexed term |
| keyboard | Matches | Matches an indexed term |
| wireless, keyboard | Matches | At least one term in the list matches |
| Wireless Mechanical Keyboard | Does not match via standard terms | The entire phrase is not a single indexed term |
| mechanical mouse | Does not match just because of mechanical | Terms query treats this string as one intact term, without splitting it into two words |

This table assumes the analyzer generates lowercase tokens as in the example. Real analyzers may behave differently, so verify with the _analyze API and index mapping.

### 4.2. When full-text search on text is needed

If the requirement is finding names or descriptions containing user-entered words or phrases, use match, match_phrase, or multi_match instead of In.

Match query example:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "Wireless Mechanical Keyboard"
    }
  }
}
~~~

Elasticsearch analyzes the search string with the appropriate analyzer and matches the tokens. If you need an ordered phrase match, use match_phrase:

~~~json
{
  "query": {
    "match_phrase": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Choose the query type by requirement:

- Set of codes/statuses/categories: terms query on keyword.
- Keywords in content: match or multi_match on text.
- Phrases requiring word order: match_phrase on text.
- Full names requiring intact comparison: use a keyword sub-field.

## 5. Combining text and keyword with multi-fields

A text field often needs both full-text search and intact matching. Elasticsearch supports multi-fields to index the same value in multiple ways.

Mapping:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          }
        }
      }
    }
  }
}
~~~

Then:

- name serves match and match_phrase.
- name.keyword serves terms, sorting, aggregations, and exact full-string matching.

Example document:

~~~json
{
  "name": "Wireless Mechanical Keyboard"
}
~~~

Full-text search on name:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "mechanical keyboard"
    }
  }
}
~~~

Searching by a list of full names on name.keyword:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "terms": {
      "name.keyword": [
        "Wireless Mechanical Keyboard",
        "Compact Keyboard"
      ]
    }
  }
}
~~~

If the entity only has the property name, a derived method findByNameIn normally queries the field mapped from property name, not automatically switching to sub-field name.keyword. When you need to query a sub-field, declare an explicit query or design metadata/properties supported by your Spring Data version.

## 6. Using @Query when specifying a sub-field

Spring Data Elasticsearch supports @Query to declare an Elasticsearch JSON query on a repository method. For example, if you want to search full names via name.keyword:

~~~java
import java.util.Collection;
import java.util.List;

import org.springframework.data.elasticsearch.annotations.Query;

public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("{\"terms\":{\"name.keyword\":?0}}")
    List<Product> findByExactNames(Collection<String> names);
}
~~~

Parameter ?0 is replaced by the first method argument according to Spring Data Elasticsearch's binding mechanism. Verify collection binding syntax in your exact project version; if more complex query control is needed, you can build a NativeQuery or query object using APIs supported by that version.

Do not declare a derived method on property name and assume Spring Data knows you intended to query name.keyword. Property paths in repositories start from the Java model; sub-fields are Elasticsearch mapping details.

## 7. NotIn and exclusion semantics

NotIn excludes documents whose field matches any value in the excluded set. Example:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "must_not": [
        {
          "terms": {
            "status": ["deleted", "archived"]
          }
        }
      ]
    }
  }
}
~~~

This query retrieves documents not matching status deleted or archived.

### 7.1. Missing fields may still be returned

In Elasticsearch, bool must_not excludes documents that match the inner query. A document lacking the status field does not match the terms query, so it may still appear in NotIn results.

This may differ from expectations shaped by a SQL column containing NULL. If the requirement is to return only documents where status exists and is outside the excluded set, add an exists condition:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "bool": {
      "filter": [
        {
          "exists": {
            "field": "status"
          }
        }
      ],
      "must_not": [
        {
          "terms": {
            "status": ["deleted", "archived"]
          }
        }
      ]
    }
  }
}
~~~

Determine clearly whether business logic wants to retain documents missing the field. Do not assume NotIn automatically excludes missing values.

### 7.2. Multi-valued fields

Elasticsearch allows a field to contain multiple values of the same type without declaring a separate array type. Example:

~~~json
{
  "tags": ["sale", "office", "wireless"]
}
~~~

With a terms query on tags, a document matches if it has at least one value present in the supplied list. With NotIn, a document is excluded if any of its field values overlaps the excluded set.

Examples:

| Document tags | In list | In | NotIn list | NotIn |
|---|---|---|---|---|
| sale, office | office, home | Yes | blocked, deleted | Yes |
| wireless, gaming | office, home | No | gaming, deleted | No |
| sale | sale | Yes | sale | No |
| no tags | sale | No | sale | Possibly yes |

The missing-field case still depends on exists conditions and how the application constructs queries.

## 8. Combining In with other conditions

Query methods can combine In with other conditions using And or Or if method naming and parameter types align.

Example:

~~~java
List<Product> findByCategoryInAndStatus(
        Collection<String> categories,
        String status
);
~~~

Meaning: category must belong to the passed list and status must match the supplied value.

Another example:

~~~java
List<Product> findByCategoryInAndPriceLessThan(
        Collection<String> categories,
        BigDecimal maxPrice
);
~~~

This method filters products belonging to the selected categories with a price below the threshold.

If pagination is needed, you can use Pageable in repository method signatures supported by Spring Data Elasticsearch:

~~~java
Page<Product> findByCategoryIn(
        Collection<String> categories,
        Pageable pageable
);
~~~

Combining operators, pagination, and return types should be checked against the specific Spring Data Elasticsearch version. For complex queries, multiple bool branches, or conditions on sub-fields, explicit queries are usually easier to control.

## 9. In and NotIn on other field types

In does not apply only to String. It can be used with numeric, boolean, date, or other fields when mappings and conversions align.

Examples:

~~~java
List<Product> findByPriceIn(Collection<BigDecimal> prices);

List<Product> findByAvailableIn(Collection<Boolean> values);

List<Order> findByStatusIn(Collection<OrderStatus> statuses);
~~~

For numeric fields, a terms query matches indexed numeric values. For booleans, it matches true or false. For dates, values must be converted according to the mapping format and temporal types supported by Spring Data.

For enums, check how the enum is converted to stored data. If stored as the enum name such as PAID, the query must provide the corresponding value. If a custom converter stores a code such as P, the repository must apply conversion consistent with how data was written.

## 10. Cases to avoid

### 10.1. Using In to search keywords inside a paragraph

If a field is text, In is usually not the right choice for finding sentences or phrases. Use match or match_phrase. If the goal is whole-string comparison, use a keyword sub-field.

### 10.2. Using keyword when natural content search is needed

Keyword fields do not tokenize words automatically. A terms query on keyword only matches values normalized per mapping. If a user types a word from the middle of a product name, terms over the entire keyword string will not find it.

### 10.3. Assuming In is case-insensitive

Keyword fields normally preserve case differences by default. A normalizer or input normalization is required if business logic demands case-insensitivity.

### 10.4. Passing collections that are too large

Terms queries have a limit on the number of terms allowed per request. The default is typically 65,536 terms, though it can depend on version and index settings. Huge lists also make requests heavy and increase query cost.

If input lists are large, consider controlled batching, terms lookup when suitable, or changing the data/query model. Do not raise the limit without measuring memory and cluster load impact.

### 10.5. Failing to handle empty lists

An empty list does not carry the same business meaning in every application. A terms query with an empty list returns no results; a negated query may match nearly all documents depending on how the query is constructed. Check for empty collections directly in the service layer and explicitly decide whether to return an empty list, omit the filter, or reject the request.

Do not let empty-query behavior implicitly define business logic.

### 10.6. Confusing Java fields with Elasticsearch fields

If Java property name maps to product_name, or a query needs sub-field product_name.keyword, verify the exact field path sent to Elasticsearch. Derived method names rely on Java properties; explicit queries must use field names from the mapping.

## 11. Inspecting actual analyzers and mappings

When In on text yields confusing results, read the mapping:

~~~http
GET /products/_mapping/field/name
~~~

Then use the Analyze API to see how text is split into terms:

~~~http
POST /products/_analyze
Content-Type: application/json

{
  "field": "name",
  "text": "Wireless Mechanical Keyboard"
}
~~~

The response returns the tokens and their positions produced by the field's analyzer. Use that information to determine what values a terms query can match.

For keyword fields, check the mapping and normalizer. Do not infer from Java annotations alone if the index has existed for a while or was created by another template/migration.

To investigate queries generated by a repository, enable appropriate client logging or inspect actual requests during tests. Logging configuration depends on the client and Spring Data Elasticsearch version.

## 12. Comprehensive example: filtering products by category and name

Suppose an application needs two behaviors:

1. Filter products belonging to one of several categories.
2. Search products by keywords in the name.

Entity:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Keyword)
    private String status;

    // constructors, getters and setters
}
~~~

Repository:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    List<Product> findByCategoryIn(Collection<String> categories);

    List<Product> findByStatusNotIn(Collection<String> statuses);
}
~~~

With category as keyword, the In method is appropriate for filtering by a list of categories. With status as keyword, NotIn is appropriate for excluding statuses.

To search names by keywords, use a full-text query:

~~~java
@Query("{\"match\":{\"name\":?0}}")
List<Product> searchByNameText(String text);
~~~

To match full names against a list, the mapping should include a keyword multi-field and use an explicit query:

~~~java
@Query("{\"terms\":{\"name.keyword\":?0}}")
List<Product> findByExactNames(Collection<String> names);
~~~

Each requirement uses the right query type:

| Requirement | Field | Appropriate query |
|---|---|---|
| Filter categories in list | category (keyword) | In / terms |
| Exclude statuses in list | status (keyword) | NotIn / bool must_not terms |
| Search words in name | name (text) | match |
| Search phrase in name | name (text) | match_phrase |
| Match intact names in list | name.keyword | terms |

## 13. Version compatibility notes

Spring Data Elasticsearch evolves across Spring Data release trains and Elasticsearch client versions. Query derivation, supported operators, return types, @Query binding, and explicit query APIs can vary across versions.

When applying to a project:

- Check your Spring Data Elasticsearch and Elasticsearch server/client versions.
- Confirm In and NotIn operators are supported for the repository/query type in use.
- Inspect the real mapping rather than relying solely on annotations.
- Observe the outgoing JSON query if you need to verify how Spring Data implements an operator.
- Write integration tests covering keyword fields, text fields, and documents with missing fields.

Examples in this guide illustrate common usage. Cross-check API signatures and query bindings against your actual version before copying prototypes into production code.

## 14. Conclusion

In and NotIn provide a convenient way to filter documents by a set of values in repository methods. For keyword fields, they fit codes, statuses, categories, and values requiring intact matching. For text fields, be careful because a terms query matches indexed tokens rather than analyzing the entire search string like a match query.

When content search is needed, use match or match_phrase. When matching full names or strings against a list, use a keyword field or multi-field and query the exact path. For NotIn, remember to define how missing fields are handled; for large or empty collections, handle them explicitly at the application layer.

Choosing operators according to mapping and data semantics makes query results predictable and prevents confusing value filtering with full-text search.
