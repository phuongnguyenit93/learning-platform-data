# @Highlight, @HighlightField, and Related Parameters

On a search page, users often want to know why a result appeared and where the keyword matched. Elasticsearch can return text segments with matched parts marked up using **highlight**. For example, for the keyword “wireless keyboard”, the result might contain the segment “A compact <em>wireless</em> <em>keyboard</em> for travel”.

In Spring Data Elasticsearch, a repository method can declare highlighting requirements with **@Highlight**. The **@HighlightField** annotation specifies which fields need fragments generated, while **@HighlightParameters** configures how fragments are produced and presented, such as highlight tags, segment size, fragment count, ordering, and encoder.

Highlighting is metadata on search results. It does not modify the stored document content and does not change the conditions that determine which documents match the query. To use fragments in the service or API layer, retain the **SearchHit<T>** or **SearchHits<T>** wrapper instead of extracting only the entity content.

## 1. What Problem Does Highlighting Solve?

Suppose a product entity has a name and a description:

~~~java
@Document(indexName = "products")
public class Product {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Text)
    private String description;

    @Field(type = FieldType.Keyword)
    private String category;

    // getters and setters
}
~~~

The user searches for the keyword `wireless keyboard`. The query can search across both name and description. Elasticsearch returns matching documents, but with only the entity content, the UI would have to decide on its own which excerpt to display. Performing substring matching in Java does not necessarily reproduce how the analyzer tokenized and matched the query.

Highlighting lets Elasticsearch generate fragments based on the query and indexed content. For example, the response might contain:

~~~json
{
  "_id": "p-100",
  "_source": {
    "name": "Compact keyboard",
    "description": "A wireless keyboard designed for travel."
  },
  "highlight": {
    "name": [
      "Compact <mark>keyboard</mark>"
    ],
    "description": [
      "A <mark>wireless</mark> <mark>keyboard</mark> designed for travel."
    ]
  }
}
~~~

In this example:

- _source still holds the original content of the document.
- highlight contains the generated segments for each field.
- <mark> is the highlight tag configured by the request.
- A field can return multiple fragments.

Highlighting is useful for search results pages, content suggestions, documentation lookup pages, and interfaces that need to show users where keywords appear.

## 2. Declaring @Highlight on a Repository Method

@Highlight is placed on a repository method that needs to return highlighted results. Inside, fields lists the fields to highlight:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {

    @Query("""
        {
          "multi_match": {
            "query": "?0",
            "fields": ["name^3", "description"]
          }
        }
        """)
    @Highlight(fields = {
        @HighlightField(name = "name"),
        @HighlightField(name = "description")
    })
    SearchHits<Product> searchWithHighlight(String keyword);
}
~~~

The method above has two separate parts:

- @Query determines which documents match the keyword.
- @Highlight requests Elasticsearch to generate fragments for name and description.

name^3 is a boost in the full-text query. It affects the relevance score, whereas which fields are highlighted is decided by @HighlightField.

The field name in @HighlightField must correspond to the Elasticsearch field being queried/highlighted. If the entity uses a Java name different from the mapped field name, declare the exact index field name according to the mapping and Spring Data's conversion behavior.

### Multiple Fields Can Be Highlighted

A method can request multiple fields:

~~~java
@Highlight(fields = {
    @HighlightField(name = "name"),
    @HighlightField(name = "description"),
    @HighlightField(name = "brand")
})
SearchHits<Product> searchCatalogText(String keyword);
~~~

Each field can have its own configuration. This is useful when a product name only needs one short fragment, while a description needs multiple segments so users can read the context.

## 3. @HighlightField and @HighlightParameters

@HighlightField describes a field to be highlighted. Its most important attribute is name; the parameters attribute lets you set configuration specific to that field.

Example:

~~~java
@Highlight(fields = {
    @HighlightField(
        name = "name",
        parameters = @HighlightParameters(
            preTags = {"<mark>"},
            postTags = {"</mark>"},
            numberOfFragments = 0
        )
    ),
    @HighlightField(
        name = "description",
        parameters = @HighlightParameters(
            preTags = {"<em>"},
            postTags = {"</em>"},
            fragmentSize = 160,
            numberOfFragments = 3,
            order = "score"
        )
    )
})
SearchHits<Product> searchWithFieldOptions(String keyword);
~~~

In this example:

- The name field returns the entire field instead of splitting into multiple fragments.
- The description field returns at most three fragments, each with a target size of 160 characters.
- Fragments for description are ordered by score.
- The two fields use different highlight tags.

The specific options supported by the annotations depend on the Spring Data Elasticsearch version. When upgrading versions, check the Highlight, HighlightField, and HighlightParameters APIs of the release train in use.

### Common Parameters for All Fields

Some versions provide parameters at the @Highlight level to set defaults for fields:

~~~java
@Highlight(
    parameters = @HighlightParameters(
        preTags = {"<mark>"},
        postTags = {"</mark>"},
        fragmentSize = 120,
        numberOfFragments = 2
    ),
    fields = {
        @HighlightField(name = "name"),
        @HighlightField(name = "description")
    }
)
SearchHits<Product> searchWithDefaultHighlight(String keyword);
~~~

Field-level configuration allows per-content tuning. Common configuration avoids repeating the same parameter set. If both levels are configured, check the precedence/override rules in your specific Spring Data Elasticsearch version.

## 4. Commonly Used Highlight Parameters

Elasticsearch Highlighter parameters control how fragments are created. Common attributes in @HighlightParameters include:

| Parameter | Role | When to Care |
|---|---|---|
| preTags | Tag or string placed before matched parts | Want to mark keywords with mark, em, or custom styles |
| postTags | Tag or string placed after matched parts | Close the corresponding highlight |
| fragmentSize | Target size of each fragment | Long fields need short excerpts displayed |
| numberOfFragments | Maximum number of fragments to return | Limit response length |
| order | Fragment ordering, often with a score option | Want the most relevant segment to appear first |
| encoder | How fragment content is encoded | Prevent text content from being interpreted as HTML |
| requireFieldMatch | Whether the query must match the highlighted field itself | Multi-field queries or complex field structures |
| type | Highlighter type | Choose unified, plain, or fvh based on mapping/use case |
| noMatchSize | Number of leading characters returned when a field has no matching fragment | Want a fallback snippet |
| boundaryScanner | How fragment boundaries are found | Want to split on sentence or word instead of character position |
| boundaryMaxScan | Boundary search range | Tune boundary scanning near fragments |
| boundaryScannerLocale | Locale for boundary scanner | Language affects how boundaries are detected |
| maxAnalyzedOffset | Limit on analyzed offset for certain highlight types | Very long fields and resource limits |

Not every parameter is present in every annotation version. Java names may use camelCase like numberOfFragments, while the underlying Query DSL uses snake_case like number_of_fragments.

### preTags and postTags

These two parameters determine the markup around matched words/phrases:

~~~java
@HighlightField(
    name = "description",
    parameters = @HighlightParameters(
        preTags = {"<mark class=\"hit\">"},
        postTags = {"</mark>"}
    )
)
~~~

One or multiple tags can be used depending on the API. When multiple tags are configured, Elasticsearch can cycle through them across fragments. Use matching open/close pairs and agree on a consistent contract with the frontend.

Tags only affect the returned fragment strings. They are not saved back to _source.

### fragmentSize

fragmentSize specifies the target size of an excerpt. For long descriptions, short fragments keep the response compact and easy for the UI to present.

~~~java
@HighlightField(
    name = "description",
    parameters = @HighlightParameters(
        fragmentSize = 180,
        numberOfFragments = 2
    )
)
~~~

Fragment size is measured in characters/text units of the highlighter, not exact word count. The highlighter may adjust boundaries to keep excerpts readable.

### numberOfFragments

numberOfFragments limits the number of fragments returned for a field:

- Positive value: returns at most the specified number of fragments.
- Value 0: requests returning the entire field content instead of splitting into fragments.
- Default/unset value: Elasticsearch applies the highlighter's default.

When using 0, fragmentSize no longer applies as it does when splitting segments. Do not return an entire long field just to highlight a few words, because the payload can become very large.

### order

If there are multiple fragments, order = "score" requests sorting fragments by relevance. This puts segments with more matching content or higher scores first.

If sorting by score is not requested, fragments may be returned in content order. Choose the ordering based on how the UI will display snippets.

### encoder

encoder controls text encoding within the fragment. Depending on the highlighter and version, common values are default or html.

If _source content may contain HTML characters, consider the encoder and frontend rendering approach. The HTML encoder encodes content characters like < and > in the fragment while preserving the configured highlight tags. Verify behavior against actual responses and never assume every fragment string is safe to inject directly into the DOM.

## 5. requireFieldMatch and the Relationship Between Query and Highlighted Fields

By default, the highlighter usually requires the highlighted field to be associated with a field in the query. The requireFieldMatch parameter controls this behavior.

Example query searching on name and description:

~~~json
{
  "multi_match": {
    "query": "wireless keyboard",
    "fields": ["name", "description"]
  }
}
~~~

When highlighting both fields, each field can produce fragments if that field's content matches the query.

If requireFieldMatch is set to false, the highlighter can apply the query more broadly when generating highlights for the field. This is useful in some complex queries, but can also produce hard-to-explain fragments if the field did not actually participate in the search the way a reader expects.

Do not turn off requireFieldMatch as a blanket fix for empty fragments. First check the field name, mapping, analyzer, and query structure.

## 6. Highlighter Types

Elasticsearch has several highlighters. The type parameter lets you choose the type if your annotation version supports it.

### Unified Highlighter

unified is the common default choice in Elasticsearch. It supports many query types and can build fragments from field content in a way that fits most use cases.

This is usually a good starting point when the application has no special speed or fragment-style requirements.

### Plain Highlighter

plain uses a per-document in-memory content analysis mechanism to generate highlights. It can fit some simple queries, but can be more expensive when fields are long or document counts are large.

Do not choose plain simply because its name sounds simple. Measure on real data and workloads.

### Fast Vector Highlighter (fvh)

fvh can leverage term vectors containing position and offset information. To use it, the field mapping must be configured with suitable term vectors, such as storing positions and offsets.

Configuring term vectors increases index size. Only enable it when the highlighting use case needs the benefits of this highlighter and you have evaluated storage/indexing costs.

### Choosing a Highlighter by Mapping

| Type | Characteristics | Things to Note |
|---|---|---|
| unified | General-purpose choice, supports many queries | Usually the right starting point |
| plain | Processes document content to create fragments | Monitor cost on long fields/many hits |
| fvh | Uses term vectors to support highlighting | Mapping must store required term vectors |

Particular highlighters may support different query types or parameters. Not every option behaves identically across all highlighters.

## 7. How Does Mapping Affect Highlighting?

Highlighting is not a feature where simply enabling an annotation makes every field work identically. Elasticsearch needs a way to retrieve content and appropriate term/offset information to build fragments.

Factors to check:

- Whether the field is mapped and indexed.
- Whether the field is text, keyword, or another data type.
- Whether the index-time analyzer and query analyzer produce expected tokens.
- Whether _source is stored and contains the field.
- Whether the mapping configures suitable term vectors or offsets if choosing a highlighter that depends on them.
- Whether the field is too long, affecting analysis limits or resource limits.

Example full-text field:

~~~java
@Field(type = FieldType.Text, analyzer = "standard")
private String description;
~~~

If description is mapped as keyword, the highlighter may handle the content differently than an analyzed text field. Choose mappings based on search, sort, and filter functionality, not solely on wanting to highlight.

### Multi-field

A property can have a text field and a keyword subfield:

~~~java
@MultiField(
    mainField = @Field(type = FieldType.Text),
    otherFields = {
        @InnerField(suffix = "keyword", type = FieldType.Keyword)
    }
)
private String name;
~~~

Then:

- Search name content with match on name.
- Filter or sort exactly on name.keyword if the mapping has that subfield.

Full-text queries usually use name; exact filters or sorts can use name.keyword. If you want to highlight search content, usually highlight the text field that participated in the query. Do not assume highlighting a keyword subfield will produce snippets like a text field.

### Very Long Fields

For long content such as articles, logs, or documents, highlighting may need to analyze a large volume of text. Limit:

- Number of fragments.
- Fragment size.
- Number of hits per page.
- Number of fields to highlight.

If Elasticsearch reports an analysis limit or empty fragments on long fields, check the max_analyzed_offset parameter if supported by the highlighter and version, along with corresponding cluster settings. Do not mechanically raise limits if response sizes and processing costs are already too high.

## 8. Reading Highlights from SearchHit and SearchHits

Repository results should retain metadata if the service needs fragments. With return type SearchHits<Product>:

~~~java
SearchHits<Product> results =
    productRepository.searchWithHighlight("wireless keyboard");

for (SearchHit<Product> hit : results.getSearchHits()) {
    Product product = hit.getContent();

    Map<String, List<String>> highlightFields =
        hit.getHighlightFields();

    List<String> nameFragments =
        highlightFields.get("name");

    List<String> descriptionFragments =
        highlightFields.get("description");
}
~~~

SearchHit<T> holds the entity content and metadata of a single hit. getHighlightFields() returns a map whose keys are field names and values are fragment lists.

A field may have no key in the map if the highlighter did not return fragments for that field. A field can also have multiple fragments. Therefore, code should handle null or empty lists.

Example of safely retrieving fragments:

~~~java
List<String> snippets =
    hit.getHighlightFields()
        .getOrDefault("description", List.of());
~~~

Do not assume every hit has fragments for every declared field. A document may match the query via name while description contains no matching terms.

### Why Keep SearchHits Instead of List<Product>?

If a repository returns List<Product>, the caller usually only receives the entity content. Highlight metadata for each hit may no longer be accessible through that result type.

When fragments are needed, prefer a return type that preserves search hit metadata, such as SearchHits<Product> or a page type supporting search hits in your version. Check the return types supported by Spring Data Elasticsearch for repository methods in your specific release train.

## 9. Converting Highlights to DTOs for the API

An API generally should not force the frontend to understand Spring Data's SearchHit directly. The service can convert the entity and fragments into a DTO:

~~~java
public record ProductSearchItem(
    String id,
    String name,
    List<String> nameHighlights,
    List<String> descriptionHighlights
) {}
~~~

Mapper:

~~~java
private ProductSearchItem toSearchItem(SearchHit<Product> hit) {
    Product product = hit.getContent();
    Map<String, List<String>> highlights =
        hit.getHighlightFields();

    return new ProductSearchItem(
        hit.getId(),
        product.getName(),
        highlights.getOrDefault("name", List.of()),
        highlights.getOrDefault("description", List.of())
    );
}
~~~

Service:

~~~java
public List<ProductSearchItem> search(String keyword) {
    SearchHits<Product> hits =
        productRepository.searchWithHighlight(keyword);

    return hits.getSearchHits().stream()
        .map(this::toSearchItem)
        .toList();
}
~~~

This keeps the API contract stable and exposes only the fragments the UI needs. If total hit count or score is needed, create a separate search-level response DTO.

### Do Not Replace Entity Content with Highlights

Highlights are snippets for presentation. Do not assign fragments back to product.description, because a fragment may only be a partial excerpt, contain highlight tags, and not be the full original text.

Keep two separate fields:

- description: document content converted from _source.
- descriptionHighlights: excerpts generated by the highlighter.

## 10. Handling HTML and Untrusted Content

Highlights typically return strings with markup tags like em or mark. This is part of the response, yet the original content may be supplied by users or external sources.

Do not assume every fragment is safe to render with innerHTML. Establish clear conventions:

1. Choose fixed highlight tags configured by the server.
2. Use a suitable encoder if content may contain markup.
3. On the frontend, allow only the necessary highlight tags.
4. Escape or sanitize untrusted content according to application policy.
5. Do not let users pass arbitrary preTags/postTags and inject them directly into HTML.

If the frontend needs to render tagged fragments, use a component or sanitizer that allows only prescribed tags, such as mark or em, and strips unnecessary attributes.

If the API wants to return plain text, convert fragments into a custom structure containing text segments and a matched flag instead of returning HTML strings. This avoids relying on the frontend to interpret markup.

## 11. Empty or Missing Fragments

There are several reasons getHighlightFields() can be empty:

- The query did not match the field requested for highlighting.
- @HighlightField.name does not match the field name in the index.
- The field has no indexed content or lacks data in _source when the highlighter needs that source.
- Query analyzer and field analyzer produce different tokens than expected.
- Query type or highlighter type does not support the specific query structure.
- The field exceeds analysis limits.
- The repository method does not preserve metadata in the return type used by the caller.

### Check in Order

1. Run the query in Elasticsearch Dev Tools and add the equivalent highlight section.
2. Confirm the field in the request exists in the mapping.
3. Verify the actual document has field content.
4. Inspect the analyzer with the Analyze API if tokens are unexpected.
5. Check the highlighter type and parameters.
6. Ensure the repository method returns a type that preserves SearchHit metadata.
7. Read getHighlightFields() on a specific hit.

Do not immediately switch requireFieldMatch to false when fragments are empty. First determine whether the query actually matches that field.

### noMatchSize

Some configurations allow noMatchSize to return an opening segment of the field even when no matching fragment exists. This can ensure the UI always has a fallback snippet, but that segment is not highlighted content.

If used, distinguish keyword-matching fragments from non-matching preview segments. The UI should not present a preview segment as though it proves the query matched that field.

## 12. Combining Highlighting with @Query and Derived Queries

@Highlight can be placed on repository methods alongside compatible query methods.

Example with @Query:

~~~java
@Query("""
    {
      "multi_match": {
        "query": "?0",
        "fields": ["name^3", "description"]
      }
    }
    """)
@Highlight(fields = {
    @HighlightField(
        name = "name",
        parameters = @HighlightParameters(
            preTags = {"<mark>"},
            postTags = {"</mark>"},
            numberOfFragments = 0
        )
    ),
    @HighlightField(
        name = "description",
        parameters = @HighlightParameters(
            preTags = {"<em>"},
            postTags = {"</em>"},
            fragmentSize = 180,
            numberOfFragments = 2
        )
    )
})
SearchHits<Product> searchCatalogText(String keyword);
~~~

The query determines the document set and scores. The highlight annotation determines the fields and how fragments are created.

With derived queries, highlighting can be declared on the method if query derivation and the return type are supported by your Spring Data Elasticsearch version. However, when you need multi-field full-text search, boosts, or complex bool structures, @Query usually expresses the query more clearly.

## 13. When Is ElasticsearchOperations Needed?

Annotations are convenient when a repository method has a fixed query structure. When highlighting needs to vary based on runtime input, use ElasticsearchOperations and the appropriate query builder.

Cases that typically need the programmatic approach:

- The list of highlighted fields changes based on search mode.
- Pre/post tags or fragment policies change by use case.
- The main query and highlight query need separate control.
- Highlighting must be combined with many dynamic filters, nested queries, or aggregations.
- Complex highlighter types and parameters must be chosen per version/API.
- SearchHits must be retained alongside other metadata such as score, sort values, and total hits.

In Spring Data Elasticsearch, the query API provides abstractions to represent highlight requests; class names and how highlights attach to NativeQuery vary by release train. When using Operations, check Highlight, HighlightField, HighlightParameters, HighlightQuery, and the corresponding builders in your installed dependency. Avoid manually concatenating highlight JSON into a query string.

Whether using repository annotations or Operations, results should still be processed via SearchHit<T> if the service needs fragments.

## 14. Common Pitfalls When Configuring Highlighting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| No highlight map | Query does not match field or annotation declares wrong field | Check query and mapping |
| Only one field has fragments | Only that field actually contains matching tokens | Check each field's content and the query |
| Fragments are too long | Large fragmentSize or numberOfFragments = 0 | Reduce fragment size and count |
| Fragments not ordered by relevance | Order by score not configured | Consider order = score |
| Highlight tags displayed as plain text | Frontend escapes the entire fragment | Agree on fragment rendering contract |
| Original content replaced by snippet | Mapper assigns highlight to entity property | Separate content and highlight DTOs |
| HTML in content causes rendering risk | Fragments injected directly into the DOM | Use encoder/sanitizer and tag allowlist |
| Wrong highlighted field | Used Java property name while index field has a different name | Compare mapping and actual field names |
| fvh fails to produce fragments as expected | Mapping lacks suitable term vectors | Configure term vectors or choose unified |
| Empty fragments on long fields | Analyzed offset limit or highlighter option | Check field length and limits |
| Cannot read highlights in service | Repository returns plain entities only | Return SearchHits<T> or a type preserving SearchHit<T> |

## 15. Testing Highlighting

Highlighting depends on Elasticsearch executing the query and mapping, so integration tests are more valuable than merely checking that annotations exist.

A test should:

1. Create an index with text mappings for the searchable fields.
2. Index documents whose keywords appear in one or more fields.
3. Call the repository method annotated with @Highlight.
4. Retrieve SearchHit<T> from the results.
5. Check the keys of getHighlightFields().
6. Verify fragments contain the configured opening/closing tags.
7. Verify non-matching fields may have no fragments.
8. Check fragment count and the numberOfFragments = 0 case.
9. Verify entity content remains the original text.
10. Verify the mapper builds a DTO separating snippets and content.

Skeleton:

~~~java
@DataElasticsearchTest
class ProductHighlightRepositoryTests {

    @Autowired
    private ProductRepository repository;

    @Test
    void returnsHighlightFragmentsForMatchingFields() {
        // Index a Product whose name and description contain the keyword.
        // Call searchWithHighlight("wireless keyboard").
        // Get the first SearchHit<Product>.
        // Verify highlightFields contains key "name"/"description".
        // Verify fragments contain configured highlight tags.
        // Verify product.getDescription() is still the original content.
    }
}
~~~

This is an illustrative skeleton; test annotations, index setup, and data creation depend on the project's Spring Boot/Spring Data Elasticsearch version. Use an Elasticsearch version compatible with the application to test the real highlighter.

## 16. Checklist When Using @Highlight

- [ ] @Highlight is placed on the right repository method.
- [ ] Each @HighlightField.name points to a field present in the mapping.
- [ ] Field mapping and analyzer match the query.
- [ ] The query can actually match the fields to be highlighted.
- [ ] preTags and postTags form a valid markup pair.
- [ ] fragmentSize suits the content length.
- [ ] numberOfFragments bounds the response as needed.
- [ ] numberOfFragments = 0 is used only when the entire field is truly needed.
- [ ] order = score is enabled when the most relevant fragments are needed first.
- [ ] requireFieldMatch is kept according to desired semantics.
- [ ] Highlighter type matches mapping; fvh has required term vectors.
- [ ] Long fields are controlled with limits and fragment counts.
- [ ] Repository return type preserves SearchHit metadata.
- [ ] Service separates highlight fragments from entity content.
- [ ] Frontend renders fragments with a safe HTML policy.
- [ ] Integration tests verify fragments against real Elasticsearch.

@Highlight declares highlighting requirements for a repository method, @HighlightField selects the fields to generate fragments for, and @HighlightParameters controls how excerpts are created. By keeping results as SearchHits<T>, the service can read SearchHit.getHighlightFields() and map fragments into a DTO for the UI. Choose parameters based on mapping, analyzer, and display experience; highlighting is purely presentation metadata on search results, while document content remains the original data.
