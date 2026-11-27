# Fragment Size, Fragment Count, Highlight Tags, and Text Source

Highlighting helps a search interface show users the text matching their query directly within each result. Elasticsearch can extract one or more text segments around matching tokens, insert highlight tags before and after the matched parts, and return those segments in the highlight field of each hit.

When designing highlighting, four decisions must be made:

- **Text source:** where does the highlighter get the field content from, and is the field stored in _source or as a stored field?
- **Fragment size:** roughly how many characters at most should each segment be?
- **Fragment count:** at most how many segments should be returned per field for a single hit?
- **Tags:** which tags mark the matched parts, and is HTML encoding needed?

These settings affect response payload size, display experience, processing cost, and safety when rendering content in a browser.

## 1. How Does Highlighting Work?

A search request can contain a query to find documents and a highlight section to ask Elasticsearch to extract matching segments from selected fields. The query decides which documents are returned; the highlighter decides which text parts of a field are included in the excerpt.

Example document:

~~~json
{
  "title": "Spring Data Elasticsearch",
  "content": "Spring Data Elasticsearch integrates Spring applications with Elasticsearch. It provides repositories and operations for search."
}
~~~

When searching for the phrase Spring Data, the request can ask to highlight the title and content fields. A hit may contain:

~~~json
{
  "_index": "articles",
  "_id": "article-1",
  "_source": {
    "title": "Spring Data Elasticsearch",
    "content": "Spring Data Elasticsearch integrates Spring applications with Elasticsearch. It provides repositories and operations for search."
  },
  "highlight": {
    "title": [
      "<em>Spring</em> <em>Data</em> Elasticsearch"
    ],
    "content": [
      "<em>Spring</em> <em>Data</em> Elasticsearch integrates Spring applications with Elasticsearch."
    ]
  }
}
~~~

Highlight fragments reside in the highlight object, separate from _source. The highlighter does not modify stored documents and does not replace original values in _source. Applications typically use _source to display full content and highlight to display marked-up previews.

## 2. Declaring Fields to Highlight

Highlighting is usually used on text fields with suitable mappings, especially text. Example:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "analyzer": "standard"
      },
      "content": {
        "type": "text",
        "analyzer": "standard"
      },
      "status": {
        "type": "keyword"
      }
    }
  }
}
~~~

The title and content fields are analyzed into tokens for querying and highlighting. The status field is usually used for filtering, not content requiring excerpts.

Search API example:

~~~http
GET /articles/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {}
    }
  }
}
~~~

When per-field parameters are not specified, Elasticsearch uses the highlighter's defaults. Common options can be declared at the highlight level and overridden per field as needed.

## 3. fragment_size: Size of Each Segment

fragment_size sets the target size of each fragment in characters, not word count or byte count. The highlighter tries to select a segment around the matched part so there is enough context for the reader to understand the result.

Example limiting fragments to around 120 characters:

~~~json
{
  "highlight": {
    "fragment_size": 120,
    "fields": {
      "content": {}
    }
  }
}
~~~

The default size is usually 100 characters. Actual fragment length may differ from the configured number because the highlighter must respect word/sentence boundaries, matching token positions, and boundary selection rules.

### 3.1. Choosing Fragment Size for the UI

| Purpose | Suggested Starting Size |
| --- | ---: |
| Short preview in result list | 80–120 characters |
| Snippet with enough context on search page | 150–250 characters |
| Longer excerpt for content-reading screens | 250–400 characters or more depending on content |

The ranges above are only starting points for experimentation. Measure with actual word lengths, language, and field lengths. Too small a value can cut off context; too large a value bloats the response and makes result lists harder to scan quickly.

### 3.2. Fragment Size Is Not a Field Length Limit

fragment_size does not truncate or alter stored content. It only controls the excerpts returned in the response. The document still keeps the entire field value in _source if source is enabled.

Fields shorter than fragment size may be returned nearly in full. For long fields, the highlighter chooses segments containing matched parts and can adjust boundaries to avoid cutting mid-word or mid-sentence.

## 4. number_of_fragments: Number of Segments per Field

number_of_fragments specifies the maximum number of fragments the highlighter returns for a field within a single hit.

Example fetching at most three segments from the content field:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 160,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

By default, the highlighter usually returns at most 5 fragments per field. If a document has many matching regions, the number of returned segments is capped by the configured value. If there are only one or two matching regions, the response may contain fewer than the maximum.

### 4.1. Per-Field Fragment Counts

Different fields can be requested with different sizes and segment counts:

~~~json
{
  "highlight": {
    "fields": {
      "title": {
        "fragment_size": 80,
        "number_of_fragments": 1
      },
      "content": {
        "fragment_size": 180,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

In this example, the title only needs one short segment, while content can return up to three segments. This is a useful way to optimize payload size according to each field's role.

### 4.2. number_of_fragments: 0: Returning the Entire Field

When number_of_fragments is set to 0, Elasticsearch does not split the field into short fragments and instead returns the entire field content in a single fragment. In this case, fragment_size is ignored.

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "number_of_fragments": 0
      }
    }
  }
}
~~~

This mode fits when a field is short and the UI needs the entire highlighted content. For long fields, the response can become very large. If only a preview is needed, use a finite fragment count.

## 5. No Matching Fragments and no_match_size

Sometimes a document is returned because the query matched another field, while the field requested for highlighting contains no matching tokens. In that case, the highlighter may return no fragments for that field.

no_match_size lets you return an opening segment of the field even when no match is found in the highlighted field:

~~~json
{
  "highlight": {
    "fields": {
      "title": {
        "number_of_fragments": 1,
        "no_match_size": 80
      }
    }
  }
}
~~~

no_match_size is the length of the leading segment retrieved when there is no match in that field; the default is 0, meaning no fallback segment is returned. It does not generate highlight tags for non-matching words.

For example, a query searches in content while requesting highlights for title as well. If title does not contain the query term, no_match_size can help the UI still have a title preview. However, clearly distinguish untagged preview segments from segments containing actual matches.

## 6. pre_tags and post_tags: Highlight Tags

pre_tags specifies the string inserted before a matched part; post_tags specifies the string inserted after a matched part.

Example using mark tags:

~~~json
{
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "content": {}
    }
  }
}
~~~

The returned fragment might be:

~~~text
<mark>Spring</mark> <mark>Data</mark> Elasticsearch
~~~

Custom CSS classes can be used:

~~~json
{
  "highlight": {
    "pre_tags": ["<span class=\"search-hit\">"],
    "post_tags": ["</span>"],
    "fields": {
      "content": {}
    }
  }
}
~~~

and CSS:

~~~css
.search-hit {
    background: #fff2a8;
    font-weight: 600;
}
~~~

### 6.1. Multiple Tag Pairs

Elasticsearch allows passing multiple pre_tags and post_tags. The highlighter can cycle through the tag pairs depending on matches or the highlighter implementation. This can help distinguish multiple match types, though the UI should use a single consistent tag set unless there is a clear design requirement.

### 6.2. Tags Are Not Safe Content

Highlight fragments are usually returned as strings containing tags. If rendered directly via innerHTML or equivalent mechanisms, original document content may contain unsafe markup or HTML strings.

Do not treat a fragment as trusted HTML simply because the highlight tags were configured by the application. Encode or sanitize the original text portion per frontend policy; allow only expected highlight tags. You can use encoder: html to instruct the highlighter to HTML-encode fragment content while preserving highlight tags. Verify the actual response before rendering.

## 7. encoder: Handling HTML in Source Text

encoder determines how the highlighter encodes fragment content:

| Value | Meaning |
| --- | --- |
| default | Does not encode HTML in source content. This is the default. |
| html | Encodes HTML special characters in source content before returning fragments. |

Example:

~~~json
{
  "highlight": {
    "encoder": "html",
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "content": {
        "fragment_size": 150,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

If source contains script strings or HTML markup, the html encoder causes it to be returned as escaped text, reducing the risk of markup execution when displayed. Even so, the application must still use safe rendering and check allowed tags. Never combine fragments with arbitrary HTML from user sources.

## 8. Choosing Highlighter Type

Elasticsearch supports multiple highlighters. If type is not specified, the unified highlighter is typically used by default.

| Type | Characteristics | Conditions and Use Cases |
| --- | --- | --- |
| unified | Default highlighter, supports many query types and selects fragments by relevance. | General choice for most applications. |
| plain | Uses a small in-memory index to reanalyze text and identify matches. | Suitable for small fields; can be costlier for large fields or many hits. |
| fvh | Fast Vector Highlighter using term vectors. | Needs `term_vector: with_positions_offsets` mapping; can fit when highlighting many fragments on large fields. |
| postings | Uses offsets stored in postings. | Needs `index_options: offsets` on the field. |

Example specifying unified:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 180,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

Do not choose fvh or postings just because their names imply high performance. They require corresponding mapping configurations and carry trade-offs in index size, indexing speed, memory, and query handling capabilities. Benchmark on representative data.

### 8.1. Unified Highlighter

Unified is a sensible default choice for most cases. It can use offsets from postings, term vectors, or reanalyze text depending on mapping and availability.

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 200,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

### 8.2. Fast Vector Highlighter

FVH requires term vectors with positions and offsets. Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "term_vector": "with_positions_offsets"
      }
    }
  }
}
~~~

Highlight query:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "type": "fvh",
        "fragment_size": 200,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

Term vectors increase index size and document indexing cost. Only enable them if a highlighting use case requires it and you have measured the benefit.

### 8.3. Postings Highlighter

The postings highlighter requires offsets stored in postings:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "index_options": "offsets"
      }
    }
  }
}
~~~

Highlight request:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "type": "postings",
        "fragment_size": 180,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Postings offsets can increase inverted index size. Weigh highlighting speed against storage cost.

## 9. Choosing Fragment Boundaries

The highlighter tries to select fragments around matches so the text is readable. boundary_scanner controls how boundaries are determined:

| Value | How Boundaries Are Selected |
| --- | --- |
| chars | Uses configured boundary characters. |
| sentence | Tries to split along sentence boundaries. |
| word | Tries to split along word boundaries. |

Example preferring sentence boundaries:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 220,
        "number_of_fragments": 2,
        "boundary_scanner": "sentence",
        "boundary_scanner_locale": "vi-VN"
      }
    }
  }
}
~~~

boundary_scanner_locale lets you specify the locale when the highlighter needs language-aware boundary detection. Results still depend on the text, tokenizer, and highlighter implementation; test with Vietnamese sentences containing punctuation, abbreviations, and parentheses.

With boundary_scanner: chars, you can declare boundary_chars and boundary_max_scan to control boundary characters and scan range. An example configuration:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "boundary_scanner": "chars",
        "boundary_chars": ".,!?;: \t\n",
        "boundary_max_scan": 30,
        "fragment_size": 160
      }
    }
  }
}
~~~

Boundary options can differ by highlighter type; not every parameter is supported identically by all implementations.

## 10. Ordering Fragments with order

A field can have multiple matching fragments. order determines how segments are sorted:

- score: sorts fragments by relevance; usually the right choice for search previews.
- none: keeps text position order instead of sorting by score.

Example:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 150,
        "number_of_fragments": 3,
        "order": "score"
      }
    }
  }
}
~~~

If the UI wants to show the first excerpt in natural reading order, order: none may fit better. If you want the most relevant excerpt first, use score.

## 11. require_field_match and highlight_query

### 11.1. require_field_match

By default require_field_match is true: a highlighted field must have a match corresponding to the query. If set to false, the highlighter can highlight a field even if the main query did not directly target that field, depending on query structure and highlighter capability.

Example:

~~~json
{
  "highlight": {
    "require_field_match": false,
    "fields": {
      "title": {},
      "content": {}
    }
  }
}
~~~

Do not set false just to “highlight more”. It can cause fields to be highlighted under unintended conditions. If you need a separate query for highlighting, consider highlight_query.

### 11.2. highlight_query

highlight_query lets you specify a separate query dedicated to deciding which text gets marked. It is useful when the document-finding query is more complex than what should be highlighted, for example when the main query has many filter clauses or uses synonyms/fuzziness.

Example where the main query finds documents with match and a status filter, while highlighting uses a phrase query:

~~~json
{
  "query": {
    "bool": {
      "must": [
        { "match": { "content": "spring data elasticsearch" } }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  },
  "highlight": {
    "fields": {
      "content": {}
    },
    "highlight_query": {
      "match_phrase": {
        "content": {
          "query": "spring data elasticsearch",
          "slop": 1
        }
      }
    }
  }
}
~~~

highlight_query only controls highlighting; it does not replace the main query and does not determine which documents are returned. If the highlight query does not match the field, there may be no fragments even though the document was found by the main query.

## 12. Multi-field and matched_fields

A property can be indexed across multiple fields, such as content of type text and content.english with another analyzer. If a query searches a subfield while wanting to highlight from the main field, matched_fields can be used where supported by the highlighter.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
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

Highlight example:

~~~json
{
  "highlight": {
    "fields": {
      "content": {
        "matched_fields": ["content", "content.english"],
        "type": "unified"
      }
    }
  }
}
~~~

matched_fields combines match information from multiple related fields to highlight on the target field. Usage and limitations depend on the highlighter type; FVH has specific requirements. Do not apply it mechanically to fields that do not share content or token structure.

## 13. Text Source: _source, Stored Fields, and Term Vectors

The highlighter needs access to text content to build fragments. In typical applications, _source holds the original text and is commonly used to supply content for highlighting.

Points to understand:

- _source holds the JSON values of the document; the highlighter can use it to fetch text to highlight when the mapping and highlighter allow it.
- Stored fields store an individual field separately when the mapping sets store: true; they may be necessary in designs that do not use _source for that field.
- Term vectors hold tokens and position/offset metadata; FVH requires term vectors with positions and offsets.
- Postings offsets store offsets in the inverted index and are used by the postings highlighter.

Do not conflate these mechanisms. Term vectors or postings offsets supply token/offset information; they are not copies of the original JSON. Stored fields supply individual field values. _source holds the document structure and is usually required to materialize entities.

### 13.1. When _source Is Disabled

When an index disables _source, the highlighter may no longer have a text source to construct fragments in the usual way. Highlighting capability then depends on whether the field is stored separately or has the necessary information from term vectors/highlighter type.

Do not disable _source just to save storage if the application needs highlighting, reindexing, or entity hydration. Verify the exact combination of mapping and highlighter on your Elasticsearch version before deploying an index without source.

### 13.2. Stored Fields

If you need to retrieve field content independently from _source, you can declare store: true for the field and request stored fields. However, enabling store does not automatically make every highlighter work with every configuration. The highlighter still needs token information, offsets, and content compatible with its implementation.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "store": true
      }
    }
  }
}
~~~

When using source filtering, stored fields, or docvalue fields alongside highlighting, inspect the response: highlights live in a separate object, while original data is returned according to the corresponding option.

## 14. Analysis Limits and Long Fields

For very long fields, the highlighter may need to analyze a lot of text to find fragments. Elasticsearch has protective limits such as index.highlight.max_analyzed_offset and related request parameters in supported versions.

If text exceeds the analysis limit, the highlighter may process only the beginning or return an error depending on configuration and version. Do not raise limits unconditionally because analyzing large texts can spike CPU and memory.

For very long content such as articles, documents, or logs:

- Limit the number of hits to highlight using page size.
- Only highlight fields that truly need previews.
- Keep number_of_fragments small.
- Use a fragment size suited to the UI.
- Evaluate highlighter type and offsets/term vectors mappings via benchmarks.
- If the use case is searching inside extremely long documents, consider storing content sections as suitably structured documents/chunks.

## 15. Highlighting in Spring Data Elasticsearch

Spring Data Elasticsearch lets you configure highlighting through HighlightQuery and attach it to a query executed by ElasticsearchOperations or repository queries.

Example domain object:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "articles")
public class ArticleDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String title;

    @Field(type = FieldType.Text)
    private String content;

    // Constructors, getters and setters
}
~~~

With modern Spring Data Elasticsearch versions, you can build highlight metadata and attach it to NativeQuery. Exact APIs for Highlight, HighlightField, HighlightParameters, and HighlightQuery depend on the Spring Data version in use; the general structure is as follows:

~~~java
import java.util.List;
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.HighlightQuery;
import org.springframework.data.elasticsearch.core.query.highlight.Highlight;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightField;
import org.springframework.data.elasticsearch.core.query.highlight.HighlightParameters;

HighlightParameters parameters = HighlightParameters.builder()
        .withPreTags("<mark>")
        .withPostTags("</mark>")
        .withFragmentSize(180)
        .withNumberOfFragments(3)
        .build();

Highlight highlight = new Highlight(
        parameters,
        List.of(
                new HighlightField("title"),
                new HighlightField("content")
        )
);

HighlightQuery highlightQuery = new HighlightQuery(
        highlight, ArticleDocument.class);

NativeQuery query = NativeQuery.builder()
        .withQuery(q -> q.match(m -> m
                .field("content")
                .query("spring data")))
        .withHighlightQuery(highlightQuery)
        .build();
~~~

The snippet illustrates declaring two highlight fields, tags, and fragment size/count. Compare constructors and builder methods against the API of your project's Spring Data Elasticsearch version; if signatures differ, keep the configuration intent and use the corresponding types from your dependency.

### 15.1. Reading Highlights from SearchHit

When executing the query:

~~~java
import org.springframework.data.elasticsearch.core.SearchHit;
import org.springframework.data.elasticsearch.core.SearchHits;

SearchHits<ArticleDocument> hits =
        operations.search(query, ArticleDocument.class);

for (SearchHit<ArticleDocument> hit : hits) {
    ArticleDocument article = hit.getContent();

    List<String> titleFragments = hit.getHighlightField("title");
    List<String> contentFragments = hit.getHighlightField("content");
}
~~~

getContent() returns the domain object converted from source per the query configuration. getHighlightField("content") returns the list of fragments for that field. A field may have no highlight results, so the application needs to handle empty lists or nulls according to its API version.

Highlight fragments are auxiliary display content. Do not overwrite article.getContent() with fragments because a fragment may only hold part of the text and contains added tags.

### 15.2. Returning Highlights via DTOs

An API should generally convert results into a dedicated DTO instead of exposing the entire SearchHit externally:

~~~java
public record ArticleSearchResult(
        String id,
        String title,
        List<String> titleHighlights,
        List<String> contentHighlights) {
}

ArticleSearchResult toResult(SearchHit<ArticleDocument> hit) {
    ArticleDocument article = hit.getContent();

    return new ArticleSearchResult(
            hit.getId(),
            article.getTitle(),
            hit.getHighlightField("title"),
            hit.getHighlightField("content"));
}
~~~

The UI can use title as the original content and titleHighlights as the snippet. Agree clearly on whether fragments are HTML-encoded or plain-text strings with tags; do not leave the frontend guessing.

## 16. Combining Highlighting with Queries, Filters, and Pagination

Highlighting only applies to hits returned by the query. Therefore, limit the number of hits via page size and request only the fields needed for display.

Example request:

~~~http
GET /articles/_search
Content-Type: application/json

{
  "from": 0,
  "size": 10,
  "query": {
    "bool": {
      "must": [
        { "match": { "content": "spring data elasticsearch" } }
      ],
      "filter": [
        { "term": { "status": "PUBLISHED" } }
      ]
    }
  },
  "_source": ["title", "summary"],
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "encoder": "html",
    "fields": {
      "title": {
        "fragment_size": 100,
        "number_of_fragments": 1
      },
      "content": {
        "fragment_size": 180,
        "number_of_fragments": 2,
        "order": "score"
      }
    }
  }
}
~~~

In this example, only 10 hits are fetched, _source returns only title and summary, and highlight returns one title fragment and up to two content fragments. Source filtering does not mean highlight results are dropped; highlights are a separate section of the hit.

## 17. Highlighting for Phrase Queries and Multi-term Queries

The highlighter relies on the query to decide which tokens to mark. For complex queries such as phrase, fuzzy, prefix, wildcard, or synonym queries, highlighting capabilities can vary by highlighter type.

Phrase query example:

~~~json
{
  "query": {
    "match_phrase": {
      "content": {
        "query": "spring data elasticsearch",
        "slop": 1
      }
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 180,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

With multi-term queries, the highlighter must determine the matching terms to mark. The unified highlighter supports many query types and is usually the first choice. If a query uses multiple branches, synonym graphs, or custom analyzers, inspect actual fragments to verify the highlighted parts match expectations.

## 18. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| No highlights in hit | Field not requested, no match in field, or incompatible query. | Check highlight.fields, field name, query, and require_field_match. |
| Fragments too short or lacking context | Small fragment_size or unsuitable boundary. | Increase size and choose an appropriate boundary scanner. |
| Response too large | Too many hits, large fragment size, or high fragment count. | Reduce page size, field count, number_of_fragments, and fragment size. |
| Only one segment returned despite multiple matches | number_of_fragments limits the segment count. | Increase fragment count or set 0 if the entire field is genuinely needed. |
| No segment returned when field has no match | no_match_size defaults to 0. | Set no_match_size if a leading-field preview is desired. |
| Tags do not appear | pre_tags/post_tags not configured or highlighter found no matching tokens. | Check query, analyzer, and tags in the request. |
| Source HTML content rendered as markup | Default encoder does not HTML-encode. | Use encoder: html and render safely on the frontend. |
| FVH reports missing term vectors | Mapping lacks term_vector: with_positions_offsets. | Create the proper mapping and reindex documents. |
| Postings highlighter does not work | Field does not store index_options: offsets. | Configure offsets on a new index and reindex. |
| Highlight has no source text | _source is disabled or field is not stored as needed by highlighter. | Check text source, stored fields, and highlighter type. |
| Spring Data getContent() missing data | Request only fetches highlight/stored/docvalue fields or source filtering excluded needed fields. | Keep source fields required to build the entity or map results separately. |

## 19. Highlight Design Workflow for an Endpoint

When implementing highlighting, determine:

1. Which fields actually need highlighting: title, summary, content, or others?
2. Do the fields have text mappings and analyzers matching the query?
3. Does the UI need short previews or the entire field?
4. Choose fragment_size and number_of_fragments based on UI layout and response size.
5. Choose pre_tags/post_tags and decide on HTML encoding.
6. If there is no match in a field, is no_match_size needed to return a preview?
7. Should fragments be ordered by score or by text order?
8. Which highlighter type fits: unified, plain, fvh, or postings?
9. Do _source, stored fields, term vectors, or postings offsets provide the needed content/metadata?
10. Are there complex queries needing highlight_query, matched_fields, or require_field_match?
11. Limit the number of hits and highlighted fields to control cost.
12. Verify actual responses and how the frontend renders tags on content containing HTML.

## 20. References

- [Elasticsearch — Highlighting](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html)
- [Elasticsearch — Unified highlighter](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html#unified-highlighter)
- [Elasticsearch — Fast vector highlighter](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html#fast-vector-highlighter)
- [Elasticsearch — Postings highlighter](https://www.elastic.co/guide/en/elasticsearch/reference/current/highlighting.html#postings-highlighter)
- [Elasticsearch — Term vectors](https://www.elastic.co/guide/en/elasticsearch/reference/current/term-vector.html)
- [Spring Data Elasticsearch — Search result types and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)

fragment_size controls the target size of each snippet; number_of_fragments caps the number of snippets per field and 0 requests returning the entire field in a single fragment. pre_tags/post_tags mark matched parts, while encoder controls HTML encoding of source text. Highlights are returned in a separate section of the hit; Spring Data Elasticsearch provides HighlightQuery and SearchHit to configure and read fragments in the application.
