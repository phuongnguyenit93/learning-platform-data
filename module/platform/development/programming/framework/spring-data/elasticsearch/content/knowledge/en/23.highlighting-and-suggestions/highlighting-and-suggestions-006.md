# Displaying Highlights Safely When Content Contains HTML

Elasticsearch highlighting helps the UI point out the text that matches a query. However, a fragment returned by Elasticsearch can contain both original document content and highlight tags inserted by the highlighter. If the original content includes HTML entered by users or pulled from external sources, that fragment must be treated as untrusted data.

A common mistake is taking the highlight string and rendering it directly via the frontend's HTML injection mechanism. This can turn malicious tags or attributes inside indexed content into executable code in the browser. The fact that Elasticsearch produced the fragment does not mean the fragment has been sanitized for web display.

The safe approach is to keep content as text, distinguish matched parts using a structured data model, and let the UI create highlight elements through a safe rendering API. If the contract strictly requires returning HTML, the server must escape the original content and generate only fixed highlight tags after splitting the highlighted segments.

## 1. Understanding How Highlight Data Is Constructed

### 1.1. A Highlight Fragment Contains Both Content and Highlight Tags

Suppose a document has a description field:

~~~html
<p>Compact wireless keyboard for travel</p>
~~~

The user searches for the word keyboard. Elasticsearch may return a fragment like:

~~~html
Compact wireless <em>keyboard</em> for travel
~~~

The em tag in the example is added by the highlighter according to the pre-tags and post-tags configuration. The rest of the text comes from the indexed document content.

These two data sources have different trust levels:

- Highlight tags configured by the application can be controlled.
- Fragment content taken from the document may contain HTML, scripts, attributes, or characters controlled by users.

Therefore, the entire string cannot be treated as safe HTML just because some tags were added by the highlighter.

### 1.2. Original Content Can Contain Malicious Markup

For example, a document stores the content:

~~~html
Wireless keyboard
<img src=x onerror="alert('xss')">
<script>alert('xss')</script>
~~~

If the highlighter returns a fragment containing this content, rendering the fragment directly can create stored cross-site scripting (stored XSS). The payload was stored in the document, and then appears when another user searches and opens the results page.

Data sources can include:

- User-entered content.
- HTML scraped from external web pages.
- Content imported from a CMS.
- Product descriptions from partners.
- Comments or documents synced from other systems.
- Legacy data indexed before sanitization rules existed.

Even if current forms validate input, old data or synced data can still contain unwanted markup.

### 1.3. Highlighting Is Not a Sanitization Feature

The highlighter's job is to locate and mark segments matching the query. It is not an HTML sanitizer and does not guarantee removal of JavaScript, event handlers, dangerous URLs, or disallowed tags.

The pre-tags/post-tags options only specify strings used to mark matched segments. They do not sanitize document content placed between the markers.

Never use the fact that Elasticsearch returned a fragment as proof that the string can be rendered safely.

## 2. Safe Processing Flow

### 2.1. Keeping a Boundary Between Data and Markup

An appropriate processing flow:

~~~mermaid
flowchart TD
    A[Document content from index] --> B[Elasticsearch highlighter]
    B --> C[Highlight fragment with markers]
    C --> D[Parse trusted marker boundaries]
    D --> E[Plain text segments]
    E --> F[API response with text and highlighted flag]
    F --> G[Frontend renders text nodes]
    G --> H[Frontend creates fixed mark element]
~~~

The backend parses the fragment into text segments and a highlighted status flag. The frontend receives plain text data and builds display nodes through the framework.

In this flow, content from the document is always treated as text. Only the application decides to create mark elements.

### 2.2. Do Not Return Raw Highlight HTML to the Client

A DTO should not contain a highlightHtml field taken directly from Elasticsearch and instruct the frontend to render it via innerHTML, dangerouslySetInnerHTML, or v-html.

Instead, return:

~~~json
{
  "descriptionSegments": [
    {
      "text": "Compact wireless ",
      "highlighted": false
    },
    {
      "text": "keyboard",
      "highlighted": true
    },
    {
      "text": " for travel",
      "highlighted": false
    }
  ]
}
~~~

The client simply loops through the segments:

- highlighted false: render a normal text node.
- highlighted true: render a text node inside a fixed highlight component or element.

No arbitrary HTML snippets from the document are executed.

### 2.3. Choosing a Unified Response Format

If the API handles multiple content types, define shared segment types:

~~~java
public record TextSegment(
    String text,
    boolean highlighted
) {
}

public record HighlightedField(
    String field,
    List<TextSegment> segments
) {
}
~~~

Result DTO:

~~~java
public record SearchResultItem(
    String id,
    String title,
    List<HighlightedField> highlights
) {
}
~~~

This structure makes it clear that text is data and highlighted is purely a presentation flag. The client does not have to parse HTML or guess which tags the server generated.

## 3. Configuring the Highlighter in Elasticsearch

### 3.1. Using Fixed Pre-tags and Post-tags

In Query DSL, the highlighter is typically configured as follows:

~~~json
{
  "query": {
    "match": {
      "description": "wireless keyboard"
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

The example above illustrates a full Elasticsearch request, including query and highlight. With Spring Data StringQuery, remember that StringQuery usually represents the query clause; the highlight section is attached via the appropriate API of your Spring Data Elasticsearch version or a native search request.

Pre/post tags should be fixed values configured by the server. Do not take them directly from user query parameters.

### 3.2. Spring Data Elasticsearch Example

With NativeQuery, highlighting can be configured through the Elasticsearch Java API Client builder. Exact syntax depends on the Spring Data Elasticsearch and client versions:

~~~java
Query query = NativeQuery.builder()
    .withQuery(q -> q.match(m -> m
        .field("description")
        .query(keyword)
    ))
    .withHighlightQuery(h -> h.fields(
        "description",
        field -> field
            .preTags("<mark>")
            .postTags("</mark>")
    ))
    .build();

SearchHits<ProductDocument> hits =
    operations.search(query, ProductDocument.class);
~~~

This is an API-oriented example. Overload names, builder types, and where pre/post tags are configured may differ between versions. Use the API of the actual dependency in your project.

### 3.3. Reading Fragments from SearchHit

Spring Data provides highlight fields on each hit:

~~~java
for (SearchHit<ProductDocument> hit : hits) {
    List<String> fragments =
        hit.getHighlightField("description");

    // Convert fragments into a safe structure before returning the DTO.
}
~~~

A field can have multiple fragments. Do not assume the list has only one element or that fragments always exist.

If the field has no matching content, the query did not request highlighting, or the highlighter produced no fragments, the list may be empty.

### 3.4. Limiting Fields and Fragments

Only request highlighting for fields used by the UI. You can limit fragment count and fragment size using appropriate highlighter options.

This helps:

- Reduce response size.
- Avoid creating overly long fragments.
- Reduce highlight processing cost.
- Limit unnecessary content sent to the client.

Highlighting should not be enabled on every field in every endpoint just because the feature is available.

## 4. Preferred Approach: Custom Markers and Structured Segments

### 4.1. Why Not Use HTML Tags as Markers?

If the highlighter inserts em and the backend tries to parse HTML to preserve every em tag, original content might also contain user-entered em tags. The backend then struggles to distinguish which tags were created by the highlighter and which came from the document.

A cleaner direction is to use non-HTML markers, for example:

~~~text
__HL_START_7F31A9__
__HL_END_7F31A9__
~~~

The highlighter inserts these two markers around matched segments. The backend then splits the string by the markers, treats everything between markers as plain text, and returns segments.

Markers should be generated on the server with a sufficiently long random nonce per request or execution, never taken from the client. This reduces the chance that source content accidentally or intentionally contains an identical marker. The backend also needs to verify that markers appear in valid pairs and order; if the structure is invalid, fall back to plain-text display instead of guessing markup.

### 4.2. Example Fragment with Markers

Suppose the highlighter returns:

~~~text
Compact wireless __HL_START_7F31A9__keyboard__HL_END_7F31A9__ for travel
~~~

The backend can parse this into:

~~~json
[
  {
    "text": "Compact wireless ",
    "highlighted": false
  },
  {
    "text": "keyboard",
    "highlighted": true
  },
  {
    "text": " for travel",
    "highlighted": false
  }
]
~~~

The content is not parsed as HTML. If the original document contains img onerror, that string remains merely a text value inside a segment.

### 4.3. Generating Markers per Request

Java example using a random token:

~~~java
import java.security.SecureRandom;
import java.util.HexFormat;

public final class HighlightMarkers {

    private static final SecureRandom RANDOM = new SecureRandom();

    private final String start;
    private final String end;

    private HighlightMarkers(String token) {
        this.start = "__HL_START_" + token + "__";
        this.end = "__HL_END_" + token + "__";
    }

    public static HighlightMarkers create() {
        byte[] bytes = new byte[16];
        RANDOM.nextBytes(bytes);

        String token = HexFormat.of().formatHex(bytes);
        return new HighlightMarkers(token);
    }

    public String start() {
        return start;
    }

    public String end() {
        return end;
    }
}
~~~

A 128-bit token makes markers unlikely to collide with natural content. When markers are needed in a highlighter request, pass them via the request's pre/post tags configuration. Do not hardcode predictable markers in public assets.

If the system cannot configure per-request markers, you can use a hard-to-collide fixed marker and check for collisions against normalized data. However, per-request random markers provide a stronger boundary.

### 4.4. Parsing Fragments into Segments

Simple parser example for a non-nested marker pair:

~~~java
public List<TextSegment> parseSegments(
        String fragment,
        String start,
        String end) {

    List<TextSegment> segments = new ArrayList<>();
    int position = 0;

    while (position < fragment.length()) {
        int startIndex = fragment.indexOf(start, position);

        if (startIndex < 0) {
            addPlainText(segments, fragment.substring(position));
            break;
        }

        if (startIndex > position) {
            addPlainText(
                segments,
                fragment.substring(position, startIndex)
            );
        }

        int textStart = startIndex + start.length();
        int endIndex = fragment.indexOf(end, textStart);

        if (endIndex < 0) {
            // Incomplete marker: do not generate markup from the remainder.
            addPlainText(segments, fragment.substring(startIndex));
            break;
        }

        String highlightedText =
            fragment.substring(textStart, endIndex);

        if (!highlightedText.isEmpty()) {
            segments.add(new TextSegment(highlightedText, true));
        }

        position = endIndex + end.length();
    }

    return List.copyOf(segments);
}

private void addPlainText(
        List<TextSegment> segments,
        String text) {

    if (!text.isEmpty()) {
        segments.add(new TextSegment(text, false));
    }
}
~~~

This is an illustrative parser for non-nested markers. A production implementation should additionally validate:

- Start/end markers are properly paired and not nested.
- The number of markers does not exceed a reasonable limit.
- Fragments do not exceed a length limit.
- Markers are not missing or appearing out of order.
- When the parser encounters malformed data, fall back to plain text.
- Markers are generated per request and not controlled by the client.

Do not use this parser for general HTML processing. It only recognizes markers configured by the application.

### 4.5. Handling Content Containing Markers

Random markers make collision probability very low, yet structural validation should not be skipped. If source content happens to contain the exact marker, the parser could segment text incorrectly.

You can choose a new nonce when a marker is detected in the original content if the application can inspect it, or treat fragments with malformed marker structure as plain text. Do not attempt to fix a fragment by stripping unmatched markers.

## 5. Rendering Structured Segments on the Frontend

### 5.1. React

With React, render text via JSX and create a fixed element for highlighted segments:

~~~jsx
function HighlightedText({ segments }) {
  return (
    <>
      {segments.map((segment, index) =>
        segment.highlighted
          ? <mark key={index}>{segment.text}</mark>
          : <span key={index}>{segment.text}</span>
      )}
    </>
  );
}
~~~

React escapes text children by default. The segment.text value is displayed as text, not interpreted as HTML.

Do not replace this with dangerouslySetInnerHTML using raw fragments from Elasticsearch.

### 5.2. Vue

With Vue, use interpolation and conditional elements:

~~~vue
<template>
  <span>
    <template v-for="(segment, index) in segments" :key="index">
      <mark v-if="segment.highlighted">{{ segment.text }}</mark>
      <span v-else>{{ segment.text }}</span>
    </template>
  </span>
</template>
~~~

Vue's interpolation escapes text content. Avoid v-html="fragment" with unsanitized fragments.

### 5.3. JavaScript DOM API

If the UI uses plain JavaScript, create text nodes and elements:

~~~javascript
function appendSegments(container, segments) {
  for (const segment of segments) {
    if (segment.highlighted) {
      const mark = document.createElement("mark");
      mark.textContent = segment.text;
      container.appendChild(mark);
    } else {
      container.appendChild(
        document.createTextNode(segment.text)
      );
    }
  }
}
~~~

Use textContent or createTextNode so content is always treated as text. Do not concatenate segment.text into innerHTML.

### 5.4. Why Are Text Nodes Safer Than HTML Strings?

Browsers distinguish text nodes from markup:

- Text nodes display characters such as <, >, and quotation marks literally as content.
- HTML strings are interpreted by the parser into elements, attributes, and content.
- Event handlers in attributes or script tags can execute when inserted into the DOM.

Therefore, when you only need to bold/color part of the text, structured segments are a far better model than sending arbitrary HTML over the API.

## 6. If Returning HTML Is Mandatory

Some legacy systems require an HTML fragment field because multiple clients consume it. In that case, the server must build the HTML itself from parsed segments.

### 6.1. Escape Text Before Wrapping with Tags

Workflow:

1. Parse the fragment into segments using trusted markers.
2. Escape every text segment for the HTML text context.
3. Wrap highlighted segments yourself with a fixed tag such as mark.
4. Do not retain any tags or attributes from the original content.
5. Only return the HTML string constructed by the server from processed parts.

Conceptual example:

~~~java
String toSafeHtml(List<TextSegment> segments) {
    StringBuilder html = new StringBuilder();

    for (TextSegment segment : segments) {
        String escaped = Encode.forHtml(segment.text());

        if (segment.highlighted()) {
            html.append("<mark>")
                .append(escaped)
                .append("</mark>");
        } else {
            html.append(escaped);
        }
    }

    return html.toString();
}
~~~

Encode.forHtml is an example API from OWASP Java Encoder. Use an encoding library suited to your project, but choose the exact encoder for the HTML text context.

The output contains only server-created mark tags. Content like img onerror is escaped into display characters rather than becoming an element.

### 6.2. Do Not Use HTML Escaping for Every Context

HTML encoding depends on insertion position:

| Context | Handling |
|---|---|
| Text content between tags | HTML text encoding |
| Attribute value | Attribute encoding |
| JavaScript string | JavaScript encoding or avoid direct embedding |
| URL | Validate scheme/host and URL-encode appropriate components |
| CSS value | Avoid placing untrusted data in CSS; if unavoidable, use appropriate encoder |

A string escaped for HTML text is not automatically safe when placed inside an attribute, JavaScript, or a URL.

It is best not to place highlight content in those contexts. When displaying content, use text nodes.

### 6.3. Do Not Trust Overly Permissive Sanitizer Configurations

If formatted HTML must be accepted, use a sanitizer with a minimal allowlist of tags and attributes. For example, allow only a few text tags like strong, em, mark, p, br and strip:

- script, iframe, object, embed.
- Event handlers such as onclick, onerror.
- Dangerous URL schemes such as javascript:.
- Unnecessary attributes or namespaces.
- Arbitrary CSS unless explicitly required.

Sanitizers must be configured and kept up to date using a trusted library. Do not write your own sanitizer using regex.

However, a sanitizer only keeps allowlisted tags; it cannot tell which em tags were created by the highlighter and which came from original content. If you only want to mark matched parts accurately, custom markers and structured segments remain easier to control.

### 6.4. Jsoup Safelist

If the product genuinely needs to preserve a subset of formatted HTML, consider Jsoup with a strict Safelist:

~~~java
String safeHtml = Jsoup.clean(
    untrustedHtml,
    Safelist.basic()
);
~~~

This is only an API example. Safelist.basic() allows several common markup tags and may be broader than what a highlight field needs. Build a custom Safelist keeping only the tags and attributes the product needs, and test against real payloads.

Do not use Safelist.relaxed() or a broader allowlist just to preserve input HTML without assessing the risk.

## 7. Indexed HTML Content and Analyzers

### 7.1. Deciding Whether to Index HTML or Cleaned Text

If a data field is HTML, determine the search objective:

- Search inside visible text after stripping markup.
- Search inside attribute or metadata content as well.
- Preserve raw HTML for re-rendering.
- Search only titles/headings or a specific content region.

For ordinary text search, it is usually best to index extracted text or text cleaned per business rules. Original HTML can be stored in an appropriate place to be rendered through a separate sanitization pipeline.

### 7.2. HTML Strip Char Filter

Elasticsearch has an HTML strip char filter to remove HTML tags before analyzing text. For example, an analyzer mapping can use the html_strip char filter.

Conceptual configuration:

~~~json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "html_text": {
          "type": "custom",
          "char_filter": ["html_strip"],
          "tokenizer": "standard",
          "filter": ["lowercase"]
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "description": {
        "type": "text",
        "analyzer": "html_text"
      }
    }
  }
}
~~~

This helps the analyzer ignore tags when generating terms. It is not an HTML sanitizer for returned content and does not replace encoding when rendering in the UI.

### 7.3. Storing Original Source and Searchable Content Separately

One model can use two fields or two data sources:

- Original content for display after sanitization.
- Normalized plain text for searching and highlighting.

Both copies must stay synchronized when updating documents. When highlights are generated from a clean text field, fragments are usually easier to process, yet must still be treated as untrusted text data.

Do not assume html_strip removes all dangerous content from _source. Analyzers only affect the indexing/search pipeline.

### 7.4. Do Not Use the Highlighter as an HTML Renderer

The highlighter does not reconstruct a safe DOM. It builds text fragments based on indexed content and markers. Therefore, do not use fragments to reconstruct full HTML pages or preserve original HTML structure.

If rich text needs to be rendered, pass content through a dedicated rendering/sanitization pipeline, while highlighting acts purely as a text-marking signal.

## 8. Highlighter Types and Display Considerations

Elasticsearch has multiple highlighters, such as unified, plain, and postings. Each has its own way of creating fragments and data requirements.

Regardless of which type is chosen, security principles stay the same:

- Fragments can contain source content.
- Pre/post tags do not sanitize content.
- Fragments can be cut at different boundaries depending on the highlighter.
- A result can have multiple fragments.
- Original HTML content can appear inside fragments.
- Text must be handled safely before reaching the browser.

Do not rely on a particular highlighter typically returning plain text as an excuse to skip escaping. Mappings, data, and indexing strategies can change over time.

## 9. Testing XSS and Highlight Correctness

### 9.1. Creating Fixtures with HTML Payloads

Test data should include both normal content and payloads:

~~~html
Wireless keyboard for travel
<img src=x onerror="alert(1)">
<script>alert(2)</script>
<a href="javascript:alert(3)">click</a>
<em>user supplied emphasis</em>
~~~

Run queries to produce fragments where highlights appear before, between, and after payloads.

### 9.2. Verifying Structured Segments

Unit tests for the parser should confirm:

- Original text is preserved.
- Only segments between markers are marked.
- No leftover markers appear in the response.
- Unpaired markers cause the parser to fall back safely.
- Fragments without markers are returned as a single plain-text segment.
- Multiple marker pairs are handled according to defined rules.
- HTML payloads remain inside the text property.

Expected example: the string img src=x onerror="alert(1)" appears verbatim in segment.text, and is not turned into an element.

### 9.3. Verifying HTML Output If the API Must Return HTML

If the server generates HTML from segments, check:

- script in the input becomes escaped text.
- onerror, onclick do not appear as active attributes.
- javascript: URLs are not created.
- Only server-generated mark tags exist.
- Double quotes, single quotes, ampersands, and Unicode characters are preserved properly.
- Fragments with malformed markers do not produce unexpected markup.

Tests should not merely search for the string script in the output; inspect the parsed DOM to ensure no active scripts or event handlers exist.

### 9.4. Testing in the Browser

Integration/E2E tests can:

1. Create a document containing an XSS payload.
2. Index the document into Elasticsearch.
3. Call the search endpoint.
4. Open the results page in a test browser.
5. Verify content renders as text.
6. Verify no event handlers or scripts execute.
7. Verify matched parts are still highlighted properly.
8. Test multiple fragments and unusual HTML content.

Do not test only the JSON API. A DTO can be safe in the backend while the frontend still misuses innerHTML.

### 9.5. Checking Libraries and Dependencies

If using a sanitizer, keep dependencies up to date and monitor security advisories. Do not use outdated HTML parsing libraries or hand-written regexes to sanitize markup.

## 10. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Script executes when opening results page | Raw highlight fragment rendered with innerHTML | Return structured segments and render text nodes |
| img onerror renders as an image | Source content interpreted as HTML | Escape text or sanitize with an allowlist |
| User-entered em tags are also kept | Backend only allowlists tags without distinguishing origin | Use custom markers for the highlighter |
| Highlights disappear after escaping | Escaped the whole fragment including markers | Parse markers first, then encode each text segment |
| JSON contains lt mark gt but client does not highlight | Double encoding or API returning already-escaped text | Choose a single layer responsible for encoding |
| Markers appear in results | Parser does not handle unpaired or malformed markers | Validate marker pairs and fall back to plain text |
| Content with quotes breaks HTML | Manual HTML string concatenation | Use context-appropriate encoder or DOM text nodes |
| Sanitizer strips the highlights too | Allowlist does not include tags or sanitize pipeline order is wrong | Parse markers into segments then create mark elements |
| Highlight differs from displayed content | Search field and display field are out of sync | Identify the text source and mapping used for highlighting |
| Fragments too long or heavy response | No limits on fragments/fields | Limit fragment count and size |
| XSS only occurs with imported data | Legacy/external data bypassed current validation | Treat all indexed content as untrusted |

## 11. Recommended Implementation Workflow

A practical implementation flow:

1. Identify which fields need highlighting and whether field content may contain HTML.
2. Configure the highlighter with server-controlled markers.
3. Read fragments from SearchHit.
4. Validate markers and parse into text segments.
5. If markers are malformed or missing, fall back to plain text.
6. Return a DTO with text and highlighted flags, not raw HTML.
7. Frontend renders text via interpolation/JSX/text nodes and creates fixed mark elements.
8. If returning HTML is mandatory, escape each segment before the server wraps tags itself.
9. Add tests for XSS payloads, special characters, Unicode, and malformed markers.
10. Run E2E tests to verify the browser does not execute content from documents.
11. Limit fields, fragments, and response size.
12. Monitor highlighter/mapping changes and re-test when upgrading Elasticsearch versions.

If a system already has an API returning raw highlight HTML, gradually migrate to structured segments and update clients before removing the old field. Do not maintain two rendering paths in parallel without clearly defining which field is permitted.

## 12. Key Takeaways

- Highlight fragments contain both highlighter-generated markers and document content; the entire fragment must be treated as untrusted.
- Elasticsearch highlighting is not an HTML sanitizer.
- Do not render raw fragments with innerHTML, dangerouslySetInnerHTML, or v-html.
- The preferred approach is custom markers, parsing into structured segments, then rendering text nodes and fixed mark elements.
- Markers should be server-generated, hard to guess, pair-validated, and fall back to plain text when malformed.
- If returning HTML is mandatory, escape each text segment for the proper context and create only fixed highlight tags yourself.
- Sanitizers must use minimal allowlists; regex is not an HTML sanitizer.
- The html_strip char filter helps process text during indexing, but does not sanitize content returned to the browser.
- Highlighting can produce multiple fragments and consume resources; request only needed fields and cap counts.
- Test XSS payloads across the parser, API response, and browser.
- All user-supplied or externally sourced content must be treated as untrusted, even after being stored in Elasticsearch.

By maintaining a clear boundary between text and markup, applications can still highlight keywords in search results without turning indexed HTML content into executable browser code.
