# Mechanism for Highlighting Text Segments Matching a Query

Highlighting in Elasticsearch is a mechanism for returning text segments that contain parts matching a search query. Instead of only displaying the raw title or description, the application can present a few excerpts and highlight relevant words or phrases using tags such as `<em>...</em>`.

For example, the user searches for “wireless mouse” and the document has the description:

~~~text
A compact wireless mouse with a rechargeable battery.
~~~

The search result may return the fragment:

~~~html
A compact <em>wireless</em> <em>mouse</em> with a rechargeable battery.
~~~

Highlighting helps users understand why a result appeared and quickly spot the relevant content. In Spring Data Elasticsearch, highlight data is usually read from the `SearchHit` metadata, separate from the domain object and `_source`.

Keep in mind that highlighting only creates excerpts for the response. It does not change the stored document content, does not decide on its own whether a document matches, and does not replace the relevance score.

## 1. How Does Highlighting Work?

A search request consists of a query and a highlight section. Elasticsearch first identifies the documents that match the query. For each hit to be returned, the highlighter finds relevant text regions and creates fragments with pre-tags/post-tags wrapping the highlighted parts.

~~~text
Search request
    |
    +--> Query
    |      |
    |      v
    |   Find matching documents
    |      |
    |      v
    |   Compute _score / sort
    |
    +--> Highlight configuration
           |
           v
       Read or analyze text
           |
           v
       Create fragments
           |
           v
       Add pre_tags / post_tags
           |
           v
Search response: hits + highlight metadata
~~~

Example request:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 150,
        "number_of_fragments": 3,
        "pre_tags": ["<mark>"],
        "post_tags": ["</mark>"]
      }
    }
  }
}
~~~

Elasticsearch returns the documents in `hits` and the highlighted segments in the `highlight` property of each hit. The original content in `_source` remains unchanged.

## 2. Highlighting Is Not a Query and Does Not Affect Score

The query decides which documents are returned. Highlighting only creates excerpts for those hits.

Example:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": "wireless mouse"
    }
  },
  "highlight": {
    "fields": {
      "description": {}
    }
  }
}
~~~

If the highlight section is removed, the same query still returns the same set of documents and the scoring calculation remains essentially unchanged. The response simply lacks the highlighted fragments.

Several consequences:

- Highlighting does not turn a non-matching document into a matching one.
- Highlighting does not replace `match`, `term`, `bool`, or other queries.
- Highlighting does not automatically sort documents by the number of keyword occurrences.
- Highlighting does not update `_source` or rewrite the document.
- A valid hit may have no highlight fragments, depending on the field, query, and highlighter.

If you need to boost the rank of documents containing keywords in `title`, adjust the query/boost. If you need to display the matching text, use highlight. These are two separate responsibilities.

## 3. Declaring Fields to Highlight

Highlighting only applies to fields specified in `highlight.fields`. For example, highlighting only `title` and `description`:

~~~http
POST /products/_search
{
  "query": {
    "multi_match": {
      "query": "wireless mouse",
      "fields": ["title^3", "description"]
    }
  },
  "highlight": {
    "fields": {
      "title": {},
      "description": {}
    }
  }
}
~~~

If only `title` is declared, Elasticsearch does not automatically generate fragments for `description`. Conversely, a field to be highlighted must have content and a mapping type suitable for the highlighter.

Each field can be configured differently:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": "wireless mouse"
    }
  },
  "highlight": {
    "fields": {
      "title": {
        "number_of_fragments": 0
      },
      "description": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Here `title` requests the entire field instead of small fragments; `description` returns at most two short segments. The `number_of_fragments: 0` option means returning the entire field, so caution is needed with long text.

If a field is not in the query but you still want to highlight it based on the query, the behavior may depend on the highlighter and the `require_field_match` setting. By default, only fields matching the query are usually highlighted. Only disable this restriction when you clearly understand the impact and do so intentionally.

## 4. What Is a Fragment?

A text field can be thousands of characters long. Instead of returning the entire content, the highlighter splits or selects a number of relevant text segments, called fragments.

Commonly used parameters:

| Parameter | Meaning |
|---|---|
| fragment_size | Target length of a fragment |
| number_of_fragments | Maximum number of fragments to return |
| no_match_size | Number of characters from the beginning of the field to return if no matching fragment is found |
| order | How fragments are ordered, e.g., by score |
| pre_tags | Tag or string placed before the matched part |
| post_tags | Tag or string placed after the matched part |

Example:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 100,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

The highlighter tries to select relevant segments around the matching region. `fragment_size` is a target size rather than a guarantee that every fragment has that exact character count. Segment splitting also depends on word boundaries, sentence boundaries, and the highlighter.

### 4.1. Returning the Entire Field

If you want to retrieve the entire field content in the highlight section, set `number_of_fragments` to 0:

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

This can be useful for short fields. For long descriptions or large documents, the response can bloat and increase bandwidth, memory, and rendering time.

If no fragments are produced and `number_of_fragments` is non-zero, the highlight result may be an empty list or the field may not appear, depending on the query/highlighter. You can use `no_match_size` if you want to get an opening segment of the field even when there is no matching region.

### 4.2. no_match_size

`no_match_size` requests returning an opening segment of the field when the highlighter cannot find a matching segment. Example:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "title": "elasticsearch"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "number_of_fragments": 1,
        "no_match_size": 80
      }
    }
  }
}
~~~

This option is useful when `title` matches the query but the application still wants to display an opening excerpt of `content`. Keep in mind that a no-match segment is not proof that `content` contains the keyword; it is only a fallback text segment.

## 5. Pre-tags and Post-tags

`pre_tags` and `post_tags` are strings added before/after the matching region. HTML tags can be used:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "description": "wireless mouse"
    }
  },
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "description": {}
    }
  }
}
~~~

The response may contain:

~~~json
{
  "highlight": {
    "description": [
      "A compact <mark>wireless</mark> <mark>mouse</mark> for travel."
    ]
  }
}
~~~

Custom tags can be used for multiple field types or multiple application types:

~~~json
{
  "highlight": {
    "pre_tags": ["<strong class=\"search-hit\">"],
    "post_tags": ["</strong>"],
    "fields": {
      "title": {},
      "description": {}
    }
  }
}
~~~

Tags are just strings in the response. The frontend is responsible for safe rendering. Do not concatenate fragments directly into HTML using mechanisms that bypass escaping without handling untrusted content.

### 5.1. Encoder

Elasticsearch has an `encoder` option, such as `html`, to encode text content before adding highlight tags in supported highlighters. This helps handle special HTML characters in the original text.

Example:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring"
    }
  },
  "highlight": {
    "encoder": "html",
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "content": {}
    }
  }
}
~~~

Check the support of your highlighter and API version in use. Even with an encoder, the frontend must still follow the application's safe rendering policy. Do not assume a fragment is trusted HTML just because Elasticsearch added tags.

## 6. Elasticsearch Highlighter Types

Elasticsearch has three common highlighters:

- unified
- plain
- fvh (Fast Vector Highlighter)

If `type` is not specified, Elasticsearch usually uses the unified highlighter.

| Highlighter | Characteristics | Common Mapping Requirements |
|---|---|---|
| unified | Default highlighter, supports many query types and can use postings offsets, term vectors, or reanalyze source | Does not require special configuration for every field |
| plain | Builds a small in-memory index structure to find matching segments | Does not require separate term vector configuration |
| fvh | Leverages term vectors to highlight quickly and supports matched fields | Field needs `term_vector` with positions and offsets |

Choose a highlighter based on mapping, field size, query, and performance requirements. Not all highlighters support the exact same options.

### 6.1. Unified Highlighter

Unified is the default highlighter in modern Elasticsearch. It splits text into fragments and scores fragments against the query to select relevant parts.

It can be specified explicitly:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 150,
        "number_of_fragments": 3,
        "order": "score"
      }
    }
  }
}
~~~

Unified can obtain offsets from postings, term vectors, or reanalyze `_source` depending on the mapping. For regular text fields, unified can usually be used without changing the mapping. When optimization on large fields is needed, consider `index_options` or `term_vector` per Elasticsearch documentation and measure on real data.

### 6.2. Plain Highlighter

The plain highlighter creates a small in-memory index per field and document being highlighted, then re-runs the query to find matching regions. This supports many queries but can consume significant CPU and memory when the number of hits or field size is large.

Example:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "plain",
        "fragment_size": 120
      }
    }
  }
}
~~~

The plain highlighter suits some simple cases, but should not be chosen just because its name sounds straightforward. If the application highlights a large number of documents, measure its cost and compare against unified/FVH.

### 6.3. Fast Vector Highlighter (fvh)

FVH uses term vectors stored in the index to locate term positions. The field needs a `term_vector` mapping with positions and offsets, typically declared as:

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

Query:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "fvh",
        "fragment_size": 150,
        "number_of_fragments": 3
      }
    }
  }
}
~~~

FVH can be suitable for large text fields or advanced highlighting requirements. In return, storing term vectors increases index size and indexing/storage cost. The mapping must be configured before indexing data; changing an existing mapping usually requires creating a new index and reindexing.

### 6.4. Postings Offsets

The unified highlighter can also leverage offsets stored in postings. The mapping can be configured as:

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

Offsets help the highlighter locate matching text without having to reanalyze the entire source in some cases. However, it increases index data size. Weigh write/storage cost against query-time highlighting cost.

## 7. require_field_match

`require_field_match` controls whether the highlighter only highlights fields that were directly queried. The default is usually `true`.

Example of querying on `title` while wanting to highlight `description` as well:

~~~http
POST /products/_search
{
  "query": {
    "match": {
      "title": "wireless mouse"
    }
  },
  "highlight": {
    "require_field_match": false,
    "fields": {
      "title": {},
      "description": {}
    }
  }
}
~~~

When `false`, the highlighter can attempt to highlight query terms on requested fields even if those fields were not directly queried. Results depend on the mapping, analyzer, and highlighter.

Do not disable `require_field_match` just to "highlight everything". With multiple fields using different analyzers, the same query string can be processed differently. Configure specific fields and verify the results.

## 8. matched_fields and Multi-fields

Content can be indexed across multiple fields with different analysis. Example:

~~~json
{
  "mappings": {
    "properties": {
      "content": {
        "type": "text",
        "analyzer": "standard",
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

The application can query on `content.english` to leverage stemming while wanting to highlight on the original `content`. `matched_fields` allows the highlighter to combine match information from related fields to highlight the display field.

Illustrative example:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content.english": "running"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "matched_fields": ["content", "content.english"]
      }
    }
  }
}
~~~

`matched_fields` requires fields representing the same underlying content or having a compatible multi-field relationship. Do not use it to combine unrelated text fields. Support and specific conditions differ between unified and FVH; check the documentation for your deployed Elasticsearch version.

## 9. Fragment Boundaries and Boundary Scanner

The highlighter needs to decide where a fragment starts and ends. Several options help control how segments are cut:

- boundary_scanner: how fragment boundaries are found, e.g., by character, word, or sentence depending on the highlighter.
- boundary_chars: set of characters treated as boundaries.
- boundary_max_scan: maximum number of characters to scan around the cut position.
- boundary_scanner_locale: locale used when determining word/sentence boundaries where supported.

Example configuration:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "type": "unified",
        "fragment_size": 180,
        "number_of_fragments": 2,
        "boundary_scanner": "sentence",
        "boundary_scanner_locale": "vi-VN"
      }
    }
  }
}
~~~

Locale names and actual splitting behavior depend on the highlighter/version. For Vietnamese text, test on data with punctuation, line breaks, and long sentences to see if fragments feel natural. There is no single `fragment_size` suitable for every language and UI.

## 10. Ordering Fragments

When `number_of_fragments` is greater than 1, you can choose how fragments are ordered. For example, `order: score` requests higher-scoring fragments to come first:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data elasticsearch"
    }
  },
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

If ordering by score is not selected, fragments generally follow their order of appearance in the text. Choose based on need:

- By position: suitable when you want readers to follow content in sequence.
- By score: suitable when you want the highest-matching segment to appear first.

Fragment order does not change document order in search hits. To sort documents, use a separate query `sort`.

## 11. Highlighting Phrases and Complex Queries

The highlighter attempts to reflect the terms/phrases matched by the query. With `match_phrase`, phrases can be highlighted according to positions. With `bool`, `nested`, `synonym`, `fuzzy`, or complex queries, highlight results may differ from expectations because each highlighter supports and interprets queries in its own way.

Example:

~~~http
POST /articles/_search
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
        "fragment_size": 160
      }
    }
  }
}
~~~

`slop` allows some flexibility in token distance/position according to phrase query semantics. The highlighter may mark the individual terms of the phrase; it does not necessarily wrap the entire phrase in a single tag.

For queries with synonyms or multiple `bool` clauses, test the actual response. Do not treat fragment counts or exact tagging style as an immutable display API across Elasticsearch versions.

## 12. Highlighting on Nested Fields

If a document contains nested objects, the query may use a `nested` query and highlighting may need corresponding configuration to extract text segments inside nested hits.

Example mapping:

~~~json
{
  "mappings": {
    "properties": {
      "comments": {
        "type": "nested",
        "properties": {
          "message": {
            "type": "text"
          }
        }
      }
    }
  }
}
~~~

Query:

~~~http
POST /posts/_search
{
  "query": {
    "nested": {
      "path": "comments",
      "query": {
        "match": {
          "comments.message": "elasticsearch"
        }
      },
      "inner_hits": {
        "highlight": {
          "fields": {
            "comments.message": {}
          }
        }
      }
    }
  }
}
~~~

With nested data, highlights may reside in `inner_hits` instead of the parent document-level highlight section. Spring Data needs to read inner hit metadata using the corresponding API. If the application only reads highlights on the parent `SearchHit`, it may miss fragments located inside nested hits.

This is a case where you should carefully verify the API of your Spring Data Elasticsearch version and write integration tests with actual nested documents.

## 13. Highlight Response from Elasticsearch

A hit can contain both `_source` and `highlight`:

~~~json
{
  "hits": {
    "hits": [
      {
        "_index": "articles",
        "_id": "A-1001",
        "_score": 4.2,
        "_source": {
          "title": "Spring Data Elasticsearch",
          "content": "Learn how Spring Data integrates with Elasticsearch."
        },
        "highlight": {
          "title": [
            "<mark>Spring Data Elasticsearch</mark>"
          ],
          "content": [
            "Learn how <mark>Spring Data</mark> integrates with <mark>Elasticsearch</mark>."
          ]
        }
      }
    ]
  }
}
~~~

`highlight` is a map keyed by field name. Each field usually has a list of string fragments. A field can have multiple fragments, so never assume there is always only one string.

A highlight fragment is text that has had tags added by the highlighter. It is not a new domain object field and does not reside inside `_source`.

## 14. Integrating Highlighting with Spring Data Elasticsearch

Spring Data Elasticsearch provides abstractions to configure highlighting and access fragments through `SearchHit`.

Common types in Spring Data Elasticsearch 5.x:

~~~java
import org.springframework.data.elasticsearch.core.query.Highlight;
import org.springframework.data.elasticsearch.core.query.HighlightField;
import org.springframework.data.elasticsearch.core.query.HighlightParameters;
import org.springframework.data.elasticsearch.core.query.HighlightQuery;
~~~

An illustrative configuration:

~~~java
HighlightField contentField = new HighlightField("content");

HighlightParameters parameters = HighlightParameters.builder()
    .withPreTags("<mark>")
    .withPostTags("</mark>")
    .withFragmentSize(150)
    .withNumberOfFragments(3)
    .build();

Highlight highlight = new Highlight(
    parameters,
    List.of(contentField)
);

HighlightQuery highlightQuery = new HighlightQuery(
    highlight,
    Article.class
);
~~~

Then attach to `NativeQuery`:

~~~java
NativeQuery nativeQuery = NativeQuery.builder()
    .withQuery(textQuery)
    .withHighlightQuery(highlightQuery)
    .build();

SearchHits<Article> hits =
    operations.search(nativeQuery, Article.class);
~~~

This is the typical API shape in Spring Data Elasticsearch 5.x. Constructors, builder methods, pre/post tag types, and packages may differ by minor version. Verify against the Javadoc/IDE of the dependency in your project before using verbatim.

If the project uses an older-generation Spring Data Elasticsearch API, the highlight configuration classes or how they attach to a query may differ. Do not mix query types from `RestHighLevelClient` and the Elasticsearch Java API Client in the same builder.

### 14.1. Reading Fragments from SearchHit

After running the search:

~~~java
for (SearchHit<Article> hit : hits) {
    Article article = hit.getContent();

    List<String> fragments =
        hit.getHighlightField("content");

    System.out.println(article.getTitle());

    for (String fragment : fragments) {
        System.out.println(fragment);
    }
}
~~~

`SearchHit` holds the content and metadata of each hit. `getHighlightField("content")` returns the list of fragments for that field according to the Spring Data API.

You can retrieve the entire map:

~~~java
Map<String, List<String>> highlightFields =
    hit.getHighlightFields();
~~~

If the field was not highlighted or has no fragments, the list may be empty. Handle this case rather than calling `get(0)` directly.

### 14.2. Creating a DTO with Highlights

An API response can contain the title, ID, and excerpts:

~~~java
public record ArticleSearchResult(
    String id,
    String title,
    float score,
    List<String> contentFragments
) {
}
~~~

Map from `SearchHit`:

~~~java
List<ArticleSearchResult> results =
    hits.getSearchHits().stream()
        .map(hit -> new ArticleSearchResult(
            hit.getId(),
            hit.getContent().getTitle(),
            hit.getScore(),
            hit.getHighlightField("content")
        ))
        .toList();
~~~

Do not stuff highlight fragments into the entity's `content` property. `_source` remains the original content; fragments are only a representation for search results.

## 15. Highlighting in Repository or ElasticsearchOperations?

Repositories are a suitable abstraction for stable queries and simple methods. With highlighting, queries often need finer-grained configuration such as fields, fragment size, tags, highlighter type, and options.

`ElasticsearchOperations` with `NativeQuery` is usually more flexible when you need to:

- Choose highlight fields per request.
- Customize fragment size or number of fragments.
- Combine highlighting with `multi_match`/`bool` queries.
- Read score and highlight metadata simultaneously.
- Use advanced Query DSL.

Some versions may support highlighting in repository queries via `@Query` or other configurations, but do not assume every derived method can enable highlighting. Check the API of your project's version.

If an endpoint has a fixed highlight configuration, you can encapsulate the query in a service or repository fragment to avoid repeating builder code.

## 16. Highlighting and Multi-fields

A field can have multi-fields:

~~~json
{
  "mappings": {
    "properties": {
      "title": {
        "type": "text",
        "fields": {
          "keyword": {
            "type": "keyword"
          },
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

The application can query `title.english` to use stemming while wanting to display fragments from the original `title`. `matched_fields` or corresponding highlight configuration can combine related fields, depending on highlighter support.

Do not highlight `title.keyword` if the goal is natural-language text segments; `keyword` is usually a single unanalyzed token rather than analyzed text. Highlight the `text` field containing the display content.

## 17. Highlighting and Source Filtering

Highlight fragments are metadata in the response. Source filtering controls which parts of `_source` are returned. The two features can be used together:

~~~http
POST /articles/_search
{
  "_source": ["title", "author"],
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "fields": {
      "content": {
        "fragment_size": 150,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

The response may contain only `title` and `author` in `_source`, while still containing `content` fragments in `highlight`.

This is useful when `content` is long and the API only needs to display an excerpt. However, if the service needs the original `content` to build a DTO, the source filter must keep that field or the service must rely on the fragments.

Do not confuse source filtering with highlighting. One selects which source fields are returned; the other generates marked-up text segments.

## 18. Safety When Rendering Highlights on the Frontend

Highlighting often uses HTML tags like `<em>` or `<mark>`. Original content in Elasticsearch may contain user-entered characters, such as:

~~~text
< script >, quotes, URLs, or HTML snippets
~~~

If the frontend inserts fragments into the DOM via raw HTML rendering without a safety policy, content can cause XSS depending on how the highlighter/encoder and data are handled.

Principles:

- Choose fixed `pre_tags`/`post_tags` controlled by the server.
- Do not take arbitrary tags from client requests.
- Configure an appropriate `encoder` and verify behavior on real data.
- Use safe rendering mechanisms on the frontend.
- If the frontend must render highlight HTML, allow only expected markup and sanitize according to application policy.
- Do not assume fragments from Elasticsearch are always trustworthy.
- Do not use fragments as HTML content with execution privileges.

You can replace HTML tags with custom text markers and render via frontend components if the application architecture wants to avoid raw HTML. What matters is distinguishing original text from server-added markers.

## 19. Performance and Mapping Choices

Highlighting can increase search cost because Elasticsearch must locate and build fragments for each returned hit. Contributing factors:

- Number of highlighted hits.
- Number of highlighted fields.
- Length of the source field.
- Number of fragments and fragment size.
- Highlighter type.
- Analyzer and query complexity.
- Whether postings offsets or term vectors can be used versus having to reanalyze source.

Ways to keep it under control:

- Only highlight fields that are actually displayed.
- Limit the number of hits and fragments.
- Choose a `fragment_size` suitable for the UI.
- Avoid returning entire long fields if only snippets are needed.
- Benchmark `unified`/`plain`/FVH on representative data.
- Only add term vectors or postings offsets when the benefit justifies the index cost.
- Do not enable highlighting on every endpoint if unnecessary.
- Keep a clear relationship between the query and highlighted fields.

### 19.1. Choosing a Highlighter Based on Needs

| Scenario | Selection Guidance |
|---|---|
| Starting with regular text fields | Default unified |
| Need simple configuration and moderate data | Unified or plain after measuring |
| Large fields, frequent highlighting, want to leverage term vectors | Evaluate FVH and `term_vector` `positions_offsets` |
| Want unified to use already-indexed offsets | Evaluate `index_options` `offsets` |
| Only need short snippets | Small `fragment_size` and limited `number_of_fragments` |
| Need the entire field | `number_of_fragments: 0`, only when content size is controlled |

There is no single best highlighter for every situation. Decisions should be based on query, mapping, index size, latency, and actual hit counts.

## 20. Common Pitfalls

| Symptom | Possible Cause | How to Check |
|---|---|---|
| Search has hits but no highlights | Field not declared, field has no match, or query/highlighter incompatible | Check `highlight.fields`, mapping, and raw response |
| Highlight field is empty | No matching fragment or `no_match_size` not configured | Check query and use `no_match_size` if a fallback snippet is needed |
| Synonyms/stemming not highlighted properly | Analyzer or `matched_fields` mismatch | Check analyzer, mapping, and highlighter |
| FVH reports mapping error | Field lacks term vectors with positions/offsets | Configure `term_vector` and reindex |
| Fragments cut mid-sentence | `fragment_size`/boundary scanner unsuitable | Adjust `fragment_size`, `boundary_scanner`, and locale |
| Only one field highlighted | Only that field declared in `highlight.fields` | Add the fields needed for display |
| Field not in query is not highlighted | `require_field_match` defaults to `true` | Consider `false` if semantics allow and test carefully |
| DTO has no highlights | Extracted content and discarded `SearchHit` metadata | Keep `SearchHit`/`SearchHits` until the DTO mapping layer |
| Nested highlights missing | Highlights reside in `inner_hits` | Read inner hit metadata |
| Response too large | Too many fields/fragments or `number_of_fragments = 0` on long fields | Limit fields, hit count, and fragments |
| HTML renders incorrectly or has XSS risk | Tags/encoder/rendering out of sync | Check encoder and frontend sanitization |
| Mapping changed but highlighting unchanged | Old index has not been reindexed | Check actual mapping/index and indexed data |

## 21. Testing Highlighting

Use integration tests with real Elasticsearch or Testcontainers to verify highlight responses. Mocking `SearchHit` cannot test the actual highlighter.

Example scenario:

1. Create an index with a `text` field `content`.
2. Save a document containing the target search phrase.
3. Refresh the index so the Search API sees the document.
4. Send a `match` query with highlight config.
5. Verify the hit exists.
6. Verify the highlight map contains the `content` field.
7. Verify the fragment has the expected pre-tag/post-tag.
8. Verify documents without matching content follow the proper fallback behavior.

Illustrative REST request:

~~~http
POST /articles/_search
{
  "query": {
    "match": {
      "content": "spring data"
    }
  },
  "highlight": {
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
    "fields": {
      "content": {
        "fragment_size": 120,
        "number_of_fragments": 2
      }
    }
  }
}
~~~

Assertions at the Spring Data layer:

~~~java
SearchHits<Article> hits =
    operations.search(nativeQuery, Article.class);

assertThat(hits.getTotalHits()).isGreaterThan(0);

SearchHit<Article> first = hits.getSearchHit(0);

List<String> fragments =
    first.getHighlightField("content");

assertThat(fragments).isNotEmpty();
assertThat(fragments.get(0)).contains("<mark>");
assertThat(fragments.get(0)).contains("</mark>");
~~~

This is an illustrative example; `NativeQuery` setup and test fixtures must match your API version. If using another highlighter or encoder, adjust assertions to match the actual response.

Additional test cases to add:

- Missing or null field.
- Query not matching the highlighted field.
- Multiple fragments.
- Text with Vietnamese diacritics and punctuation.
- Content containing HTML characters.
- Multi-field/`matched_fields`.
- Nested inner hits if the application uses nested mappings.
- Source filtering combined with highlighting.

## 22. Debugging Workflow When Highlights Are Wrong

When the response has no fragments or highlights incorrectly, check in order:

1. Confirm the query returns the expected documents.
2. Check that field names in `highlight.fields` match the mapping.
3. Read the mapping to confirm the field is `text`/`keyword` and which analyzer is used.
4. Call the Analyze API to inspect generated tokens.
5. Try the `unified` highlighter with minimal configuration.
6. Check `require_field_match` and `matched_fields`.
7. If using FVH, confirm `term_vector` has positions and offsets.
8. If using postings offsets, check `index_options`.
9. Check source filtering and nested `inner_hits`.
10. Inspect the raw Search response to distinguish Elasticsearch issues from `SearchHit`/DTO mapping issues.

Mappings and highlighters can differ across indices if an alias points to multiple indices. If searching across a multi-index alias, ensure highlighted fields have compatible mappings.

## 23. Quick Reference Table

| Need | Configuration |
|---|---|
| Highlight a text field | `highlight.fields` |
| Highlight tags | `pre_tags` / `post_tags` |
| Limit excerpt length | `fragment_size` |
| Limit excerpt count | `number_of_fragments` |
| Return entire field | `number_of_fragments: 0` |
| Fallback excerpt when no match | `no_match_size` |
| Relevant fragments first | `order: score` |
| Select highlighter | `type: unified / plain / fvh` |
| Use term vectors | `term_vector: with_positions_offsets` for FVH |
| Use postings offsets | `index_options: offsets` for unified when appropriate |
| Highlight field outside query | `require_field_match: false` if appropriate |
| Combine multi-fields | `matched_fields` as supported by highlighter |
| Read fragments in Spring Data | `SearchHit.getHighlightField(name)` |
| Keep score and metadata | `SearchHit<T>` / `SearchHits<T>` |
| Highlight nested results | `inner_hits` highlight and read inner hit metadata |

Highlighting makes search results easier to understand by returning fragments with query-matching text marked up. Choose appropriate fields, fragment sizes, fragment counts, and highlighters; start with `unified`, and only add term vectors or postings offsets when measured optimizations are needed. In Spring Data Elasticsearch, retain `SearchHit`/`SearchHits` to read highlight metadata, map fragments into dedicated DTOs, and render safely on the frontend.
