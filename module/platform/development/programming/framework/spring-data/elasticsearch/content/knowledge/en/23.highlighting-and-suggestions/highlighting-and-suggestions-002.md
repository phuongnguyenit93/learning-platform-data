# Configuring Highlighting with Query or Repository Annotations

Highlighting in Elasticsearch helps emphasize the text matching a query in search results. Instead of returning only documents and relevance scores, Elasticsearch can additionally return text segments (highlight fragments) wrapped with opening and closing tags around the matched parts.

Spring Data Elasticsearch supports configuring highlighting in two ways:

- **Via Query**: build the highlight configuration using classes in the `org.springframework.data.elasticsearch.core.query.highlight` package, wrap it in `HighlightQuery`, and attach it to a `CriteriaQuery` or `NativeQuery`.
- **Via Repository annotations**: place `@Highlight` on a repository method, declare fields to highlight with `@HighlightField`, and customize with `@HighlightParameters`.

Both approaches use Elasticsearch's highlighting mechanism. Highlight results are returned in the metadata of `SearchHit<T>`, so return `SearchHit` or `SearchHits` if the application needs to read the highlighted text segments.

## 1. How Does Highlighting Work?

Suppose a document has a product name:

`Wireless Mechanical Keyboard for Office`

The user searches for the keywords:

`mechanical keyboard`

The search query can use `match` on the `name` field. When highlighting is enabled for this field, Elasticsearch returns an additional fragment:

~~~json
{
  "_index": "products",
  "_id": "P-1001",
  "_score": 2.4,
  "_source": {
    "name": "Wireless Mechanical Keyboard for Office"
  },
  "highlight": {
    "name": [
      "Wireless <mark>Mechanical</mark> <mark>Keyboard</mark> for Office"
    ]
  }
}
~~~

In this example:

- `_source.name` is the original data of the document.
- `highlight.name` is the fragment content generated for the search result.
- `<mark>` and `</mark>` are the tags wrapping the matched parts.
- Highlighting does not write changes back to the document and does not modify values in `_source`.

~~~mermaid
flowchart TD
    A["User enters keywords"] --> B["Match query on field"]
    B --> C["Elasticsearch finds documents"]
    C --> D["Highlight configuration for fields"]
    D --> E["Generate fragments and highlight tags"]
    E --> F["Search response"]
    F --> G["Spring Data SearchHit / SearchHits"]
~~~

Highlighting is supplementary metadata for search results. It does not replace the query, does not alter how documents are indexed, and does not decide on its own which documents are returned.

## 2. Preparing the Entity and Mapping

Example entity:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String status;

    // Constructors, getters and setters
}
~~~

In this example:

- `name` and `description` are text fields, suitable for full-text search and highlighting.
- `status` is a keyword, typically used for exact filtering.
- Highlighting is generally most useful on analyzable text fields.

A query must actually search content related to a field for highlighting to produce useful content. If a query only filters `status = PUBLISHED`, Elasticsearch has no search terms in `name` to highlight. Highlighting can be configured for the field, but the result still depends on the query and the highlighter's ability to produce fragments.

## 3. Common Highlight Parameters

Elasticsearch supports various options to control how fragments are generated.

| Parameter | Meaning |
|---|---|
| `pre_tags` | Tag or string placed before the matched part |
| `post_tags` | Tag or string placed after the matched part |
| `fragment_size` | Target length of each fragment |
| `number_of_fragments` | Maximum number of fragments per field |
| `no_match_size` | Number of characters that may be returned when the field has no matching segment |
| `require_field_match` | Requires the query to match the highlighted field itself |
| `type` | Highlighter type, e.g., `unified`, `plain`, `fvh` |
| `order` | How fragments are ordered, e.g., by relevance score |
| `encoder` | How fragment content is encoded |
| `highlight_query` | Dedicated query used to determine highlighted content |

A few notes:

- `number_of_fragments = 0` requests returning the entire field content instead of splitting into fragments.
- `fragment_size` is a target size, not a hard limit for every language or sentence boundary.
- `no_match_size` only provides a portion of content when there is no match; it does not turn a non-matching result into a search match.
- `require_field_match = true` is the common default. If set to `false`, the highlighter may use the query to highlight a field even if that field did not directly match under default rules.
- A field can return multiple fragments, so the result is typically a list of strings rather than a single string.

## 4. Configuring Highlighting via Query

With Spring Data Elasticsearch 5.4, highlighting can be constructed using classes in these packages:

- `org.springframework.data.elasticsearch.core.query.highlight.Highlight`
- `org.springframework.data.elasticsearch.core.query.highlight.HighlightField`
- `org.springframework.data.elasticsearch.core.query.highlight.HighlightParameters`
- `org.springframework.data.elasticsearch.core.query.highlight.HighlightFieldParameters`
- `org.springframework.data.elasticsearch.core.query.HighlightQuery`

`Highlight` holds the common configuration and the list of fields to highlight. `HighlightQuery` pairs that configuration with the entity type so Spring Data maps property names.

### 4.1. Creating Common Highlight Parameters

~~~java
import org.springframework.data.elasticsearch.core.query.highlight.HighlightParameters;

HighlightParameters highlightParameters =
        new HighlightParameters.HighlightParametersBuilder()
                .withPreTags("<mark>")
                .withPostTags("</mark>")
                .withFragmentSize(150)
                .withNumberOfFragments(3)
                .withNoMatchSize(0)
                .withRequireFieldMatch(true)
                .build();
~~~

In this example:

- `withPreTags("<mark>")` sets the opening tag before matched segments.
- `withPostTags("</mark>")` sets the closing tag after matched segments.
- `withFragmentSize(150)` sets the target fragment size.
- `withNumberOfFragments(3)` requests up to three fragments per field.
- `withNoMatchSize(0)` does not request an excerpt when a field has no matching segment.
- `withRequireFieldMatch(true)` requires the query to match the highlighted field.

`HighlightParameters.HighlightParametersBuilder` is the builder for the Spring Data configuration model. It is distinct from the `@HighlightParameters` annotation used in repositories.

### 4.2. Declaring Fields to Highlight

~~~java
import java.util.List;

import org.springframework.data.elasticsearch.core.query.highlight.Highlight;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightField;

Highlight highlight = new Highlight(
        highlightParameters,
        List.of(
                new HighlightField("name"),
                new HighlightField("description")
        )
);
~~~

Here, both `name` and `description` are requested to be highlighted with the common configuration.

Per-field configuration can be set using `HighlightFieldParameters`:

~~~java
import org.springframework.data.elasticsearch.core.query.highlight.HighlightFieldParameters;

HighlightFieldParameters nameParameters =
        new HighlightFieldParameters.HighlightFieldParametersBuilder()
                .withFragmentSize(100)
                .withNumberOfFragments(2)
                .build();

Highlight highlight = new Highlight(
        highlightParameters,
        List.of(
                new HighlightField("name", nameParameters),
                new HighlightField("description")
        )
);
~~~

In this example, the `name` field has its own fragment configuration. The `description` field uses the common configuration from `Highlight`.

### 4.3. Creating HighlightQuery and Attaching to NativeQuery

~~~java
import co.elastic.clients.elasticsearch._types.query_dsl.Query;

import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.HighlightQuery;

Query elasticsearchQuery = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("mechanical keyboard")
        )
);

HighlightQuery highlightQuery =
        new HighlightQuery(highlight, ProductDocument.class);

NativeQuery nativeQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withHighlightQuery(highlightQuery)
        .build();
~~~

Steps:

1. Create the query DSL using the Elasticsearch Java API Client.
2. Create `Highlight` with common settings and fields.
3. Create `HighlightQuery` from `Highlight` and the entity class.
4. Attach `HighlightQuery` to `NativeQuery` via `withHighlightQuery(...)`.
5. Execute via `ElasticsearchOperations.search(...)`.

`NativeQueryBuilder` extends `BaseQueryBuilder`, so `withHighlightQuery(...)` can be used alongside query, sort, and pageable options.

### 4.4. Using CriteriaQuery Also Works

Highlighting is not limited to `NativeQuery`. `HighlightQuery` belongs to Spring Data's Query abstraction, so it can be attached to other queries that support this configuration.

~~~java
import org.springframework.data.elasticsearch.core.query.Criteria;
import org.springframework.data.elasticsearch.core.query.CriteriaQuery;

Criteria criteria = new Criteria("name").matches("mechanical keyboard");

CriteriaQuery criteriaQuery = new CriteriaQuery(criteria);
criteriaQuery.setHighlightQuery(
        new HighlightQuery(highlight, ProductDocument.class)
);
~~~

This approach fits when search conditions are simple and already expressed with the Criteria API. If the query is complex, has multiple bool clauses, or requires the Elasticsearch Java Client DSL, `NativeQuery` is usually more flexible.

## 5. Executing and Reading Highlights via SearchHit

After creating the query, execute it with `ElasticsearchOperations`:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ProductDocument> hits =
        operations.search(nativeQuery, ProductDocument.class);

for (SearchHit<ProductDocument> hit : hits) {
    ProductDocument product = hit.getContent();

    List<String> nameFragments =
            hit.getHighlightField("name");

    List<String> descriptionFragments =
            hit.getHighlightField("description");

    System.out.println(product.getName());
    System.out.println(nameFragments);
    System.out.println(descriptionFragments);
}
~~~

Key APIs:

| API | Result |
|---|---|
| `SearchHit.getContent()` | Converted entity |
| `SearchHit.getHighlightField("name")` | List of fragments for the `name` field |
| `SearchHit.getHighlightFields()` | Map from field name to list of fragments |
| `SearchHits.getSearchHits()` | List of `SearchHit` |
| `SearchHits.getTotalHits()` | Total result count per response |

`getHighlightField(field)` returns the list of fragments for the specified field. If there are no fragments, the list may be empty. `getHighlightFields()` returns a map of fields that have highlight data.

Example reading the entire map:

~~~java
for (SearchHit<ProductDocument> hit : hits) {
    Map<String, List<String>> highlighted =
            hit.getHighlightFields();

    highlighted.forEach((field, fragments) -> {
        System.out.println("Field: " + field);
        fragments.forEach(System.out::println);
    });
}
~~~

Never assume fragments are always present. A document may be returned because of a filter condition, while the field requested for highlighting contains no matching terms; in that case, the fragment list can be empty.

## 6. Configuring Highlighting via Repository Annotations

Spring Data Elasticsearch provides annotations to declare highlighting directly on repository methods:

- `@Highlight`: marks the method as needing highlighting and lists the fields.
- `@HighlightField`: identifies a field to highlight.
- `@HighlightParameters`: configures global or per-field highlight parameters.

Example entity:

~~~java
@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    // ...
}
~~~

Repository:

~~~java
import org.springframework.data.elasticsearch.annotations.Highlight;
import org.springframework.data.elasticsearch.annotations.HighlightField;
import org.springframework.data.elasticsearch.annotations.HighlightParameters;
import org.springframework.data.elasticsearch.core.SearchHits;
import org.springframework.data.elasticsearch.repository.ElasticsearchRepository;

public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    @Highlight(
        fields = {
            @HighlightField(name = "name"),
            @HighlightField(name = "description")
        },
        parameters = @HighlightParameters(
            preTags = {"<mark>"},
            postTags = {"</mark>"},
            fragmentSize = 150,
            numberOfFragments = 3,
            requireFieldMatch = true
        )
    )
    SearchHits<ProductDocument> findByNameOrDescription(
            String name,
            String description
    );
}
~~~

When called:

~~~java
SearchHits<ProductDocument> hits =
        productRepository.findByNameOrDescription(
                "mechanical keyboard",
                "mechanical keyboard"
        );
~~~

Spring Data generates the repository query from the method name and applies the highlight configuration from the annotations.

Using `SearchHits<ProductDocument>` preserves each hit's metadata, including highlight fields. You can use `List<SearchHit<ProductDocument>>` if it fits your repository API and application return types. If returning only `List<ProductDocument>`, the application no longer has the `SearchHit` wrapper to read highlight metadata directly.

### 6.1. Highlighting with Repository Methods Using @Query

`@Query` can be combined with `@Highlight` when you want to define a specific Query DSL:

~~~java
import org.springframework.data.elasticsearch.annotations.Query;

@Query("{\"bool\":{\"should\":["
        + "{\"match\":{\"name\":\"?0\"}},"
        + "{\"match\":{\"description\":\"?0\"}}"
        + "],\"minimum_should_match\":1}}")
@Highlight(
    fields = {
        @HighlightField(name = "name"),
        @HighlightField(name = "description")
    },
    parameters = @HighlightParameters(
        preTags = {"<mark>"},
        postTags = {"</mark>"},
        fragmentSize = 120,
        numberOfFragments = 2
    )
)
SearchHits<ProductDocument> searchText(String text);
~~~

In this example:

- `@Query` defines search conditions across both fields.
- `minimum_should_match: 1` requires at least one matching branch.
- `@Highlight` requests highlights for `name` and `description`.
- Parameter `?0` is replaced by the method's first argument.

The field name in `@HighlightField` must be the entity property name, not necessarily the physical field name in the Elasticsearch mapping. Spring Data uses entity metadata to map properties. This matters if a Java property has `@Field(name = "...")` or a custom naming strategy.

## 7. Global and Per-Field Customization

There are two configuration levels:

- **Highlight level**: applies to the entire highlight request, such as opening/closing tags, encoder, or highlighter type.
- **Field level**: applies individually to each field, such as fragment size, number of fragments, matched fields, or fragment offset.

Annotation example:

~~~java
@Highlight(
    parameters = @HighlightParameters(
        preTags = {"<strong>"},
        postTags = {"</strong>"},
        encoder = "html",
        numberOfFragments = 3,
        fragmentSize = 160
    ),
    fields = {
        @HighlightField(
            name = "name",
            parameters = @HighlightParameters(
                fragmentSize = 100,
                numberOfFragments = 2
            )
        ),
        @HighlightField(name = "description")
    }
)
SearchHits<ProductDocument> searchByText(String text);
~~~

The `name` field has its own parameters, while `description` uses the common parameters. Which exact configuration takes effect depends on how Spring Data translates annotations into the highlight request; when exact behavior is needed, inspect the generated request and Elasticsearch response in a test environment.

With the Query API, the equivalent configuration can use `HighlightParameters` and `HighlightFieldParameters` builders:

~~~java
HighlightParameters common = new HighlightParameters.HighlightParametersBuilder()
        .withPreTags("<strong>")
        .withPostTags("</strong>")
        .withEncoder("html")
        .withFragmentSize(160)
        .withNumberOfFragments(3)
        .build();

HighlightFieldParameters nameOptions =
        new HighlightFieldParameters.HighlightFieldParametersBuilder()
                .withFragmentSize(100)
                .withNumberOfFragments(2)
                .build();

Highlight highlight = new Highlight(
        common,
        List.of(
                new HighlightField("name", nameOptions),
                new HighlightField("description")
        )
);
~~~

The builders provide additional options such as:

- `withBoundaryScanner(...)` and `withBoundaryScannerLocale(...)`: control how fragment boundaries are determined.
- `withBoundaryChars(...)` and `withBoundaryMaxScan(...)`: configure characters and scan range for boundaries.
- `withOrder("score")`: sort fragments by relevance score when supported.
- `withNoMatchSize(...)`: retrieve a portion of content when no matching fragment exists.
- `withRequireFieldMatch(false)`: change the rule requiring the query to match the field.
- `withHighlightQuery(...)`: supply a dedicated query for the highlighter.
- `withMatchedFields(...)`: combine related fields in a highlight field configuration.

You do not need to enable all parameters. Only configure what the UI actually needs, because many fragments and complex highlighter settings can increase search cost.

## 8. Choosing the Highlighter Type

Elasticsearch has multiple highlighter types. Spring Data lets you pass the type via the `type` parameter.

| Highlighter | Characteristics | When to Consider |
|---|---|---|
| `unified` | Default highlighter, supports many field and query types | First choice for most cases |
| `plain` | Based on a per-document text analyzer engine | When specific plain highlighter behavior is required |
| `fvh` | Fast Vector Highlighter, exploits term vectors | When data and mapping are designed for FVH |

Example configuring `unified`:

~~~java
HighlightParameters parameters =
        new HighlightParameters.HighlightParametersBuilder()
                .withType("unified")
                .withPreTags("<mark>")
                .withPostTags("</mark>")
                .withFragmentSize(150)
                .withNumberOfFragments(2)
                .build();
~~~

Unified is usually a reasonable choice to start with. Only switch to another highlighter once you understand the mapping requirements and have measured performance on real data.

### Mapping Requirements for FVH

Fast Vector Highlighter requires suitable term vectors, typically `term_vector: with_positions_offsets`:

~~~json
{
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "term_vector": "with_positions_offsets"
      }
    }
  }
}
~~~

Configuring term vectors increases index size. Do not enable it just to have highlighting; choose the default highlighter first and measure actual needs.

Some highlighters can leverage offsets stored in postings or term vectors. Capabilities and limits depend on field type, mapping, and query. Consult the Elasticsearch documentation for the running cluster version before modifying mappings.

## 9. Highlighting with Multi-fields and matched_fields

A text field can have multi-fields, for example:

~~~json
{
  "mappings": {
    "properties": {
      "name": {
        "type": "text",
        "fields": {
          "english": {
            "type": "text",
            "analyzer": "english"
          }
        }
      }
    }
  }
}
~~~

The application can search across the main field or analyzed subfields. When match information from multiple related fields needs to be combined for highlighting, Elasticsearch supports `matched_fields` subject to highlighter compatibility conditions.

In Spring Data, `matchedFields` can be configured for a highlight field:

~~~java
HighlightFieldParameters parameters =
        new HighlightFieldParameters.HighlightFieldParametersBuilder()
                .withMatchedFields("name", "name.english")
                .withFragmentSize(150)
                .withNumberOfFragments(2)
                .build();

HighlightField nameField =
        new HighlightField("name", parameters);
~~~

Use `matchedFields` when the fields are different representations of the same content and matches need to be merged to produce fragments. Do not put unrelated fields into the same group because the highlighted snippet could be misleading.

## 10. Using highlightQuery When Custom Highlight Rules Are Needed

Normally the highlighter uses the main query to determine which terms to highlight. If you need to highlight according to a separate query, `highlightQuery` can be configured.

For example, the main query might combine full-text with filters, while highlighting only uses the product name match. Spring Data supports `highlightQuery` in `HighlightParameters`:

~~~java
Query highlightOnlyName = Query.of(q -> q
        .match(m -> m
                .field("name")
                .query("mechanical keyboard")
        )
);

HighlightParameters parameters =
        new HighlightParameters.HighlightParametersBuilder()
                .withPreTags("<mark>")
                .withPostTags("</mark>")
                .withHighlightQuery(highlightOnlyName)
                .build();
~~~

A separate query controls how the highlighter determines which segments to mark. However, it does not alter the main query used to select documents. If the highlight query does not match the field content, the fragment result may be empty.

## 11. Highlighting Is Not Sanitized Content

Fragments often contain HTML tags or strings configured by the application. If fragments are inserted directly into HTML without processing, original document content may contain malicious markup.

For example, data might contain:

~~~text
Wireless Keyboard <script>alert(1)</script>
~~~

If the application displays highlights by trusting the entire fragment, it can create a cross-site scripting (XSS) vulnerability.

A few principles:

- Consider `encoder = "html"` to encode field content during highlighting.
- Use highlight tags controlled by the application, such as `<mark>`.
- Do not let users arbitrarily pass `pre_tags` or `post_tags`.
- If the frontend must render markup, allow only allowlisted highlight tags.
- Do not use raw HTML rendering operations on unverified fragments.

Example configuring the encoder in an annotation:

~~~java
@Highlight(
    fields = {
        @HighlightField(name = "description")
    },
    parameters = @HighlightParameters(
        preTags = {"<mark>"},
        postTags = {"</mark>"},
        encoder = "html"
    )
)
SearchHits<ProductDocument> searchDescription(String text);
~~~

The encoder helps encode fragment content according to highlighter configuration, but the application still needs to control how output is rendered and should not treat search data as trusted.

## 12. When Are Highlight Fragments Missing?

There are several reasons a document is returned while the highlight map lacks the expected field:

1. The query does not match the highlighted field.
2. The field is not requested in the highlight configuration.
3. The field does not support the highlighter due to mapping or data type.
4. Query analyzer and field analyzer produce incompatible tokens.
5. `require_field_match` is enabled and the query only matched another field.
6. The field has no content or the content is too short/cannot form a fragment.
7. The highlighter type requires term vectors/offsets that the mapping does not provide.
8. `_source` or field configuration does not suit how the highlighter retrieves content.

When debugging, check in order:

- Does the actual query match the field?
- Is the field mapping `text`, `keyword`, or another type?
- Does the highlight request contain the right field path?
- Does the highlighter type require special mapping?
- Does the raw response contain the `highlight` property?
- Does Spring Data map the highlight field into `SearchHit` as expected?

You can use Elasticsearch Dev Tools to send the query with `highlight` directly and inspect the response before checking Spring Data's conversion layer.

## 13. Distinguishing Highlighting from Source Filtering

Highlighting and source filtering solve two different needs:

| Feature | Purpose |
|---|---|
| Highlight | Return fragments with matched parts marked up |
| Source filtering | Reduce the fields in `_source` that are returned |
| Stored fields | Return fields stored separately in the index per mapping |

Example query with source filtering returning only `name`:

~~~java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.FetchSourceFilter;

NativeQuery sourceFilteredQuery = NativeQuery.builder()
        .withQuery(elasticsearchQuery)
        .withSourceFilter(
                new FetchSourceFilter(
                        new String[] {"name"},
                        new String[] {}
                )
        )
        .withHighlightQuery(highlightQuery)
        .build();
~~~

Highlighting for `description` is separate metadata. If source filtering excludes `description`, the application may still receive highlight fragments for that field under some configurations, but it will not have the full source content of the field to display. Decide clearly which source fields and which highlight fields the response needs.

Do not use highlighting as a replacement for source filtering or vice versa.

## 14. Comparing Configuration via Query vs. Repository Annotations

| Criterion | Query / HighlightQuery | Repository annotation |
|---|---|---|
| Where declared | In query-building code | On repository method |
| Main API | `Highlight`, `HighlightField`, `HighlightParameters`, `HighlightQuery` | `@Highlight`, `@HighlightField`, `@HighlightParameters` |
| Search conditions | `CriteriaQuery` or `NativeQuery` | Derived query or `@Query` |
| Flexibility | High, can vary per request | Fixed configuration per method |
| When to use | Dynamic queries, service needs to control highlights | Repository method with stable search behavior |
| Reading results | `SearchHit.getHighlightField(...)` | `SearchHit.getHighlightField(...)` |

Choose Query configuration when a service has multiple search modes or needs to vary fields/fragments per request. Choose annotations when a repository method has a fixed query and highlight configuration that is easy to read right where it is declared.

There is no need to combine both approaches for the same request without a clear reason. Keep a single source of configuration to avoid confusion during debugging.

## 15. Common Pitfalls

### Using Index Field Names Instead of Property Names in @HighlightField

Spring Data Javadoc specifies `@HighlightField.name` as the entity property name. If the Java property is `productName` while the mapped field is named `name`, the repository annotation must reference the property according to Spring Data rules rather than guessing the physical name.

### Returning Only the Entity and Losing Metadata

Highlights are stored in `SearchHit`, and do not automatically become entity properties. Use `SearchHits<T>` or `SearchHit<T>` when you need to read fragments.

### Filter-Only Queries Expected to Highlight Keywords

Filters like `term(status)` do not provide text keywords to highlight. A suitable query on the field or a dedicated highlight query is needed.

### Confusing Fragments with the Entire Field

A long field may return multiple short segments. If the entire field is desired, configure `numberOfFragments = 0` and weigh response size.

### Configuring Too Many Fragments

Many fragments across many fields can bloat responses and increase processing cost. Limit fields, fragment counts, and sizes to suit the UI.

### Choosing FVH Without Configuring Term Vectors

Fast Vector Highlighter needs mapping support for suitable term vectors. If not present, use `unified` or update the mapping/reindex as planned.

### Using Unsafe HTML Tags

Fragments can contain user data. Control pre/post tags, encoder, and rendering to prevent XSS.

### Treating Highlights as Absolute Proof of Relevance

Highlighting only shows the content chosen by the highlighter to mark up per the query. It is not a score, does not replace `_score`, and does not guarantee every relevant part is displayed.

## 16. Implementation Workflow

When adding highlighting to search functionality:

1. Identify the text fields that need emphasizing.
2. Verify the mapping and analyzer of each field.
3. Determine whether the query actually matches those fields.
4. Choose configuration via `HighlightQuery` or `@Highlight` annotation.
5. Set `preTags`, `postTags`, `fragmentSize`, and `numberOfFragments` according to UI needs.
6. Use `SearchHit<T>` or `SearchHits<T>` to retain highlight metadata.
7. Test both cases with fragments and without fragments.
8. If using multi-fields, determine whether `matchedFields` is needed.
9. Choose highlighter type based on mapping and measure performance.
10. Control the encoder and how the frontend renders fragments.
11. Inspect the actual Elasticsearch response when errors occur.
12. Limit field count and fragment count to avoid oversized responses.

## References

- [Spring Data Elasticsearch 5.4.8 — Repository methods and @Highlight](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/reference/html/#elasticsearch.repositories.annotations)
- [Spring Data Elasticsearch 5.4.8 — Highlight annotation](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/annotations/Highlight.html)
- [Spring Data Elasticsearch 5.4.8 — HighlightParameters annotation](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/annotations/HighlightParameters.html)
- [Spring Data Elasticsearch 5.4.8 — NativeQueryBuilder](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/client/elc/NativeQueryBuilder.html)
- [Spring Data Elasticsearch 5.4.8 — SearchHit](https://docs.spring.io/spring-data/elasticsearch/docs/5.4.8/api/org/springframework/data/elasticsearch/core/SearchHit.html)
- [Elasticsearch — Highlighting search results](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html)

## Conclusion

Spring Data Elasticsearch supports highlighting in two ways. With the Query API, build `Highlight` and `HighlightField`, combine them into `HighlightQuery`, and attach it to `NativeQuery` or `CriteriaQuery`. With Repositories, place `@Highlight` on a method, list fields with `@HighlightField`, and configure them with `@HighlightParameters`. Results reside in `SearchHit<T>` metadata, readable via `getHighlightField(...)` or `getHighlightFields()`. Choose fields with suitable mappings, set sensible fragment limits, and ensure HTML safety before displaying results to users.
