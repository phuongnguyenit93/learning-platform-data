# Normalizing Feed Entries into Message Payloads in Spring Integration

## 1. Problem: Keeping Downstream Systems Decoupled from ROME

An engineering news aggregator pulls RSS and Atom feeds from multiple providers. With the Feed inbound channel adapter, Spring Integration emits each news item as a `Message<SyndEntry>`. During prototyping, a handler might immediately call `entry.getTitle()` and `entry.getLink()`. Once the pipeline connects to a database, HTTP gateway, JMS, AMQP, Kafka, or another application, passing raw `SyndEntry` instances creates tight coupling:

- Consumers must know the **ROME** library and types like `SyndContent`, `SyndLink`, `SyndCategory`, and `Date`.
- RSS may omit `guid`/`pubDate`; Atom uses `id`/`updated`/`published` and multiple `link rel` attributes.
- An entry may carry HTML, unexpected URIs, unnormalized Unicode characters, or mutable collections.
- `MessageHeaders.ID` and `MessageHeaders.TIMESTAMP` are not the article's ID or publication date.
- Replays after restarts generate new messages for the same article; downstream code needs a stable identity to deduplicate.
- Serializing a ROME object onto a broker ties consumers to the Java classpath, library version, and serialization policy.

The solution is placing a **Transformer** downstream of Feed inbound: convert `SyndEntry` into a **well-contracted business payload**, such as `ArticleNotice` or `FeedArticleEvent`, before sending it onto shared `MessageChannel` paths.

```text
RSS/Atom (HTTP)
   -> FeedEntryMessageSource
   -> Message<SyndEntry>                 (ROME library data)
   -> Validate + Normalize Transformer
   -> Message<ArticleNotice>             (application contract)
   -> MessageChannel
   -> DB / JMS / AMQP / Kafka / HTTP
```

The **"Normalizing Feed Entries into Message Payloads"** lesson belongs to the **Adapter Feed** chapter of the `SPRING_INTEGRATION_ADAPTERS` module. The module covers inbound/outbound adapters, gateways, pollers, `MessageChannel`, file/SFTP/HTTP/JMS/AMQP/Kafka/database integrations, message contracts, error handling, and connection lifecycles. This lesson focuses on **payload design and transformation**, not replacing the Feed adapter's polling or time-filtering mechanics.

After this lesson, you will be able to:

1. Explain the initial Feed inbound payload and why a ROME-independent DTO should be used.
2. Define a contract for `sourceKey, entryId, publishedAt, updatedAt, title, canonicalUrl, categories, summary` with explicit null policies.
3. Normalize dates to `Instant`, validate GUID/Atom IDs, select the right Atom `alternate link`, and constrain untrusted data.
4. Write an immutable Java 17 `record` along with a unit-testable mapper.
5. Use the Java DSL `.transform(SyndEntry.class, mapper::map)` to produce `Message<ArticleNotice>`.
6. Distinguish payload transformation from header enrichment, header propagation, and message UUIDs.
7. Handle invalid entries via error/quarantine paths without losing track of them after source watermarks advance.
8. Design JSON contracts, versioning/idempotency, RSS/Atom tests, and production operations.

## 2. Transformation Point in the Architecture

```mermaid
flowchart TD
    A["RSS / Atom Publisher"] --> B["Poller + FeedEntryMessageSource"]
    W["MetadataStore: published-date watermark"] <--> B
    B --> M["Message<SyndEntry>"]
    M --> H["Header Enricher: trusted sourceKey"]
    H --> T["Transformer: SyndEntry -> ArticleNotice"]
    T --> E["Message<ArticleNotice>"]
    E --> C["MessageChannel / Router"]
    C --> D["Transactional DB / idempotent service"]
    C --> K["Broker / HTTP adapter"]
    T -- "Validation error" --> Q["Error / durable quarantine"]
```

| Component | Input | Output | Key Consideration |
|---|---|---|---|
| `FeedEntryMessageSource` | RSS or Atom URL/`Resource` | Each `receive()` may return one `Message<SyndEntry>` | Has an internal queue and date watermark |
| `Header Enricher` | `Message<SyndEntry>` | Message with same payload and custom headers | Attach `sourceKey` from trusted configuration |
| `Transformer` | `SyndEntry` | `ArticleNotice` | Validate/normalize without unexpected DB writes |
| `MessageChannel` | `Message<ArticleNotice>` | Forwards to next endpoint | Does not provide durable storage by itself |
| `MessageHandler` | DTO + headers | DB record / outbound side effect | Idempotency and transactions belong here |
| Feed `MetadataStore` | `metadataKey` | Source watermark | Not a database acknowledgment |

Spring Integration **6.5** uses ROME and emits one `SyndEntry` per message payload; a single feed document containing multiple entries still produces **multiple messages**. `maxMessagesPerPoll` throttles messages per turn—not DTO field counts or XML entry counts.

### 2.1. Do Not Confuse Payload and Headers

A message before transformation:

```text
payload: SyndEntry
  uri             = tag:example.org,2026:release-41
  title           = API 4.1 released
  publishedDate   = Date(...)
  updatedDate     = Date(...)
  links           = List<SyndLink>

headers:
  id              = framework-generated UUID
  timestamp       = message creation time
  feedSourceKey   = partner-releases (if added by app)
```

After transformation:

```text
payload: ArticleNotice
  schemaVersion   = 1
  sourceKey       = partner-releases
  entryId         = tag:example.org,2026:release-41
  publishedAt     = Instant UTC
  updatedAt       = Instant UTC
  canonicalUrl    = https://feeds.example.org/releases/41
  categories      = List<String>

headers:
  id              = new message UUID per framework rules
  timestamp       = message creation time
  feedSourceKey   = partner-releases
  feedEntryId     = ... (if enriched)
```

The primary article contract should reside in the **payload**, since the payload is persisted to the DB and sent across systems. Headers should carry **small, trusted context** for routing, correlation, and tracing. Do not assume RSS/Atom fields automatically become `feed_*` headers.

## 3. Mapping Table from RSS/Atom to Canonical Payload

ROME exposes entries through `com.rometools.rome.feed.synd.SyndEntry`. The getters below apply to the ROME 2.x line and may return null or empty collections depending on the source.

| Source Field | ROME Getter | Proposed DTO Field | Rule |
|---|---|---|---|
| App-configured source | Not from entry | `sourceKey` | From approved source registry |
| RSS `guid` / Atom `id` | `getUri()` | `entryId` | Preserve exact identity; never auto-lowercase |
| RSS `title` / Atom `title` | `getTitle()` | `title` | Validate, normalize Unicode/whitespace carefully |
| RSS `link` / Atom `link rel=alternate` | `getLink()` / `getLinks()` | `canonicalUrl` | Pick link by `rel`/`type`, validate syntax |
| RSS `pubDate` / Atom `published` | `getPublishedDate()` | `publishedAt` | `Date -> Instant`; may be null |
| Atom `updated` / equivalent | `getUpdatedDate()` | `updatedAt` | `Date -> Instant`; may be null on some sources |
| RSS `description` / Atom `summary` | `getDescription()` | `summaryRaw` + `summaryType` | **Untrusted** content, may contain HTML |
| Atom content / RSS content module | `getContents()` | Optional as needed | Keep only if contract requires; bound size |
| RSS/Atom author | `getAuthor()` / `getAuthors()` | `author` | Optional; never derive user permissions from it |
| RSS/Atom category | `getCategories()` | `categories: List<String>` | Filter nulls, normalize, cap element count |
| Enclosure/media | `getEnclosures()` | Separate attachment DTO if needed | Never auto-fetch external URL resources |
| App receipt timestamp | `Clock.instant()` | `receivedAt` | Never masquerade as `published` or `updated` |
| Target schema version | Config/contract constant | `schemaVersion` | Lets consumers evolve independently |

### 3.1. RSS Items and Atom Entries Are Not Identical

RSS 2.0 example:

```xml
<item>
  <guid isPermaLink="false">release-41</guid>
  <title>API 4.1 released</title>
  <link>https://feeds.example.org/releases/41</link>
  <pubDate>Mon, 23 Nov 2026 02:00:00 GMT</pubDate>
  <description><![CDATA[<p>Release summary</p>]]></description>
  <category>release</category>
</item>
```

Atom 1.0:

```xml
<entry xmlns="http://www.w3.org/2005/Atom">
  <id>tag:example.org,2026:release-41</id>
  <title>API 4.1 released</title>
  <updated>2026-11-23T03:00:00Z</updated>
  <published>2026-11-23T02:00:00Z</published>
  <link rel="alternate" type="text/html"
        href="https://feeds.example.org/releases/41"/>
  <link rel="enclosure" type="application/pdf"
        href="https://cdn.example.org/files/41.pdf"/>
  <summary type="html">&lt;p&gt;Release summary&lt;/p&gt;</summary>
</entry>
```

In Atom 1.0, `updated` is required on valid entries; `published` is optional. In RSS, an item may lack GUID or `pubDate`. ROME may parse the XML cleanly yet still yield null for `SyndEntry.getUri()`/`getPublishedDate()`.

### 3.2. Policy for Entries Missing an ID

Recommended durable key:

```text
articleIdentity = (sourceKey, entryId)
```

For Atom IDs like `tag:...` or `urn:...`, they are **not HTTP URLs to fetch**. For RSS, `guid` may have `isPermaLink="false"`. Never attempt to pass `getUri()` into `new URL(...)`.

If ID is missing:

1. Prefer having the publisher fix the feed to supply a stable GUID/Atom ID.
2. If an RSS publisher guarantees **immutable article URLs**, you may fall back to `link` with an explicit version policy and URL validation.
3. If stable identity cannot be established, route the entry to quarantine/review; never use `title` or message UUID as the key.

**Caution:** depending on `FeedEntryMessageSource`'s watermark algorithm, an entry missing a date might never be emitted. The transformer only processes **entries that became messages**; it cannot rescue items already skipped by the source.

## 4. Normalization Rules Must Be Explicit and Testable

### 4.1. Distinguishing Normalization from Altering Source Meaning

| Data | Should Do | Should Not Do Arbitrarily |
|---|---|---|
| `sourceKey` | Use app-configured, namespaced alias | Infer tenant/permissions from RSS title |
| `entryId` | Check null, length, invalid characters | Lowercase, strip accents, silently hash, alter GUID parts |
| `title` | Trim, Unicode NFC, collapse whitespace, bound length | Use as ID, strip meaningful characters |
| `publishedAt/updatedAt` | Convert to UTC `Instant`, keep null if contract allows | Replace missing `published` with message timestamp and claim it was published |
| `canonicalUrl` | Pick valid `alternate` HTML link, check scheme/host | Auto-fetch links or follow redirects to "verify" without an allowlist |
| `categories` | Drop null/blank, trim, deduplicate, cap count | Use source strings as arbitrary bean/channel names |
| `summaryRaw` | Cap size, retain type, mark untrusted | Inject directly into HTML UI or headers/baggage |
| `receivedAt` | Read from app `Clock` for deterministic tests | Include in idempotency keys or content checksums |

### 4.2. Do Not Collapse Three Clocks into One

```text
publishedAt = 2026-11-20T10:00:00Z   (publisher posted)
updatedAt   = 2026-11-23T03:00:00Z   (publisher edited)
receivedAt  = 2026-11-23T07:35:20Z   (system ingested)
```

These three timestamps answer three different questions. To measure ingestion SLA, compare `receivedAt` against the agreed source timestamp. To sync revisions, use `updatedAt`/revisions. To filter articles "posted this month", use `publishedAt`.

Never use `MessageHeaders.TIMESTAMP` as the article date: it records **message instance** creation time and changes across transforms and replays.

### 4.3. Canonical Link in Atom

An Atom entry can include multiple links:

```xml
<link rel="alternate" type="text/html"
      href="https://feeds.example.org/articles/41"/>
<link rel="self" type="application/atom+xml"
      href="https://feeds.example.org/entries/41.atom"/>
<link rel="enclosure" type="application/pdf"
      href="https://cdn.example.org/docs/41.pdf" length="120000"/>
```

Select `rel=alternate` with `type=text/html` when targeting the human-readable article URL—never take the first link or an `enclosure`. In Atom, `rel` may be omitted and defaults to `alternate` per RFC 4287; check `type`/`hreflang` when multiple languages exist. For RSS, `getLink()` is usually convenient.

Checking URI syntax with `java.net.URI` **is not** complete SSRF protection. It only verifies syntax/scheme/host. If the system later fetches `canonicalUrl`, enforce DNS/IP checks, redirect controls, host allowlists, and outbound network policies.

### 4.4. Summary and HTML Content

`SyndContent.getValue()` may contain plain text, HTML, or XHTML depending on `type` and source. A DTO field named `summaryRaw` is an **untrusted string**, not sanitized HTML. If consumers need plain text, extract and sanitize with a vetted HTML parser/sanitizer—never use regexes to strip HTML tags as an XSS defense.

Never attach long HTML or ROME objects to message headers and push them onto Kafka/JMS. Headers should hold small scalars; payload/DB contracts should define content rules and UI rendering safeguards separately.

## 5. Canonical Payload Contract: Immutable Java Record

**`ArticleNotice.java`** (placed in your practice project when implementing):

```java
import java.time.Instant;
import java.util.List;

public record ArticleNotice(
        String schemaVersion,
        String sourceKey,
        String entryId,
        String title,
        String canonicalUrl,
        Instant publishedAt,
        Instant updatedAt,
        Instant receivedAt,
        String author,
        String summaryRaw,
        String summaryType,
        List<String> categories) {

    public ArticleNotice {
        // Do not retain a reference to a mutable List from ROME.
        categories = List.copyOf(
                categories == null ? List.of() : categories);
    }
}
```

### 5.1. Why Use a Record?

- Holds pure data fields with no adapter polling or session logic.
- `String`, `Instant`, and `List<String>` form a much cleaner JSON contract than `SyndEntry`'s complex ROME object graph.
- `record` provides shallow immutability; `List.copyOf` prevents external list mutation.
- Mapper unit tests do not require booting a Spring context or making HTTP calls.
- Provides an explicit place for `schemaVersion` and compatibility rules.

Note: Java record immutability **does not** make its contents trustworthy. `summaryRaw` and `canonicalUrl` remain publisher-supplied inputs requiring validation/sanitization where consumed.

### 5.2. Should You Also Keep Raw Input?

Never embed raw `SyndEntry` inside the DTO "for convenience later", as that defeats library decoupling. If raw auditing is needed:

```text
ArticleNotice (canonical payload for downstream)
  + sourceKey
  + entryId
  + optional rawSnapshotRef (ID pointing to secure object store)
```

Only retain raw XML when justified by explicit purpose, retention, encryption, and access policies. `SyndEntry.getWireEntry()` is no substitute for durable raw HTTP snapshots.

## 6. Writing a Java Mapper with Validation and Null Handling

To keep code clean and testable, the mapper takes **one `SyndEntry`** and returns one `ArticleNotice`. Never call databases, Kafka, or HTTP inside the mapper, and do not construct `Message` objects manually if you only need to transform the payload.

**`ArticleNoticeMapper.java`:**

```java
import java.net.URI;
import java.net.URISyntaxException;
import java.text.Normalizer;
import java.time.Clock;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Objects;

import com.rometools.rome.feed.synd.SyndCategory;
import com.rometools.rome.feed.synd.SyndContent;
import com.rometools.rome.feed.synd.SyndEntry;
import com.rometools.rome.feed.synd.SyndLink;

public final class ArticleNoticeMapper {
    private static final String VERSION = "1";
    private static final int MAX_ID_LENGTH = 768;
    private static final int MAX_TITLE_LENGTH = 1024;
    private static final int MAX_SUMMARY_LENGTH = 16_384;

    private final String sourceKey;
    private final Clock clock;

    public ArticleNoticeMapper(String sourceKey, Clock clock) {
        if (sourceKey == null
                || !sourceKey.matches("[a-z0-9][a-z0-9-]{0,63}")) {
            throw new IllegalArgumentException(
                    "sourceKey must be a configured alias");
        }
        this.sourceKey = sourceKey;
        this.clock = Objects.requireNonNull(clock, "clock");
    }

    public ArticleNotice map(SyndEntry entry) {
        Objects.requireNonNull(entry, "entry");

        String id = requireStableId(entry.getUri());
        String title = normalizeTitle(entry.getTitle());
        String url = validateArticleUrl(selectAlternateHtmlUrl(entry));

        Date published = entry.getPublishedDate();
        Date updated = entry.getUpdatedDate();
        Instant publishedAt = published == null
                ? null : published.toInstant();
        Instant updatedAt = updated == null
                ? null : updated.toInstant();

        SyndContent summary = entry.getDescription();
        String rawSummary = summary == null ? null : summary.getValue();
        if (rawSummary != null
                && rawSummary.length() > MAX_SUMMARY_LENGTH) {
            throw new IllegalArgumentException(
                    "Feed entry summary exceeds size limit");
        }

        List<SyndCategory> original = entry.getCategories();
        List<String> categories = original == null
                ? List.of()
                : original.stream()
                    .filter(Objects::nonNull)
                    .map(SyndCategory::getName)
                    .filter(Objects::nonNull)
                    .map(String::strip)
                    .filter(s -> !s.isBlank())
                    .distinct()
                    .limit(32)
                    .toList();

        return new ArticleNotice(
                VERSION,
                sourceKey,
                id,
                title,
                url,
                publishedAt,
                updatedAt,
                clock.instant(),
                optionalTrim(entry.getAuthor(), 512),
                rawSummary,
                summary == null ? null : summary.getType(),
                categories);
    }

    private static String requireStableId(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException(
                    "Entry has no stable GUID/Atom ID");
        }
        if (!id.equals(id.strip()) || id.length() > MAX_ID_LENGTH) {
            throw new IllegalArgumentException(
                    "Entry ID has leading/trailing whitespace or is too long");
        }
        // Do not lowercase, strip accents, or alter original ID.
        return id;
    }

    private static String normalizeTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException(
                    "Entry is missing title per business contract");
        }
        String normalized = Normalizer.normalize(
                title.strip(), Normalizer.Form.NFC)
                .replaceAll("\\s+", " ");
        if (normalized.length() > MAX_TITLE_LENGTH) {
            throw new IllegalArgumentException("Title is too long");
        }
        return normalized;
    }

    private static String optionalTrim(String value, int maxLength) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String result = value.strip();
        if (result.length() > maxLength) {
            throw new IllegalArgumentException(
                    "Optional metadata exceeds size policy");
        }
        return result;
    }

    private static String selectAlternateHtmlUrl(SyndEntry entry) {
        List<SyndLink> links = entry.getLinks();
        if (links != null) {
            for (SyndLink link : links) {
                if (link == null) {
                    continue;
                }
                String rel = link.getRel();
                String type = link.getType();
                boolean alternate = rel == null || rel.isBlank()
                        || "alternate".equalsIgnoreCase(rel);
                boolean html = type == null || type.isBlank()
                        || "text/html".equalsIgnoreCase(type);
                if (alternate && html && link.getHref() != null
                        && !link.getHref().isBlank()) {
                    return link.getHref();
                }
            }
        }
        // RSS normally uses the item's link.
        return entry.getLink();
    }

    private static String validateArticleUrl(String raw) {
        if (raw == null || raw.isBlank()) {
            return null; // canonicalUrl is optional in this demo.
        }
        if (raw.length() > 2048) {
            throw new IllegalArgumentException("Article URL is too long");
        }
        try {
            URI uri = new URI(raw.strip());
            String scheme = uri.getScheme();
            if (scheme == null
                    || (!"https".equalsIgnoreCase(scheme)
                        && !"http".equalsIgnoreCase(scheme))
                    || uri.getHost() == null
                    || uri.getUserInfo() != null) {
                throw new IllegalArgumentException(
                        "Article URL is not a valid HTTP/HTTPS URL");
            }
            // Syntax check only; DO NOT make HTTP calls here.
            return uri.normalize().toASCIIString();
        }
        catch (URISyntaxException ex) {
            throw new IllegalArgumentException(
                    "Article URL could not be parsed", ex);
        }
    }
}
```

### 6.1. What the Mapper Intentionally Does Not Do

- **Does not** invoke `HttpClient`/`RestClient` on `getLink()` or enclosures. URL syntax validation alone does not stop SSRF if fetched later; any fetch step must enforce allowlists and DNS/redirect rules.
- **Does not** treat `summaryRaw` as sanitized HTML. If plain text is needed, build a `ContentSanitizer` using a trusted HTML parser to convert/escape per context; never strip tags with regex.
- **Does not** fall back `publishedAt = receivedAt`: that fabricates history. Keep null so consumers can decide explicitly.
- **Does not** lowercase or Unicode-normalize `entryId`: altering identity can merge distinct articles.
- **Does not** write to a database inside the mapper: mappers must stay pure/side-effect-free for safe retries and unit testing.
- **Does not** put `receivedAt` in idempotency keys: it changes across retries.
- **Does not** merge `updatedAt` into `publishedAt` or assume every source supplies revisions.

In practice, a contract may prefer **quarantine** over throwing `IllegalArgumentException`. The example intentionally fails fast to demonstrate validation and error paths; later sections explain returning a classified outcome so one bad entry does not make the whole polling task look like an infrastructure failure.

### 6.2. Note on Unicode Normalization

Unicode can represent certain characters either as precomposed characters or base characters plus combining marks. NFC makes titles display and search more consistently, yet **must not be applied silently** to RSS GUIDs/Atom IDs unless the publisher specifies such canonicalization. Overly aggressive normalization (NFKC, lowercasing everything, stripping diacritics) can erase distinctions between valid IDs or meaningful titles.

### 6.3. Scope of the Example

The mapper above only checks **length in Java `char` units**; brokers and databases also enforce limits in **UTF-8 bytes**, JSON payload size, and HTTP headers. Production must validate serialized message size, link/enclosure counts, content types, Unicode edge cases, and per-source quotas. `maxMessagesPerPoll` does not bound the size of the incoming XML document.

## 7. Java DSL: Transforming `SyndEntry` into `ArticleNotice`

The example uses **Spring Boot 3.x + compatible Spring Integration 6.5.x** and Java 17. Use dependency management/BOM so Spring Integration modules align on one release line.

### 7.1. Dependencies and Configuration

**`build.gradle`:**

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-integration'
    implementation 'org.springframework.integration:spring-integration-feed'
}
```

**`application.yml`:**

```yaml
demo:
  feed:
    url: ${FEED_URL:https://feeds.example.org/releases.rss}
    source-key: ${FEED_SOURCE_KEY:partner-releases}
    metadata-key: ${FEED_METADATA_KEY:feeds:partner-releases:v1}
    poll-delay-ms: ${FEED_POLL_DELAY_MS:30000}
    max-messages-per-poll: ${FEED_MAX_PER_POLL:10}
    connect-timeout-ms: ${FEED_CONNECT_TIMEOUT_MS:5000}
    read-timeout-ms: ${FEED_READ_TIMEOUT_MS:10000}
```

`feeds.example.org` URLs are examples, not guaranteed live public feeds. Use a mock HTTP server or fixture in labs. Production must only call approved feed URLs and never accept unvalidated user-supplied URLs.

### 7.2. Spring Configuration

**`NormalizedFeedConfig.java`:**

```java
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.MalformedURLException;
import java.time.Clock;

import com.rometools.rome.feed.synd.SyndEntry;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.integration.dsl.Pollers;
import org.springframework.integration.feed.dsl.Feed;
import org.springframework.integration.metadata.MetadataStore;
import org.springframework.integration.metadata.SimpleMetadataStore;

@Configuration
@EnableIntegration
public class NormalizedFeedConfig {

    @Bean
    Clock feedClock() {
        return Clock.systemUTC();
    }

    @Bean
    ArticleNoticeMapper articleNoticeMapper(
            @Value("${demo.feed.source-key}") String sourceKey,
            Clock feedClock) {
        return new ArticleNoticeMapper(sourceKey, feedClock);
    }

    @Bean("normalizedFeedMetadataStore")
    MetadataStore normalizedFeedMetadataStore() {
        return new SimpleMetadataStore(); // Lab only.
    }

    @Bean("normalizedFeedResource")
    Resource normalizedFeedResource(
            @Value("${demo.feed.url}") String url,
            @Value("${demo.feed.connect-timeout-ms}") int connectMs,
            @Value("${demo.feed.read-timeout-ms}") int readMs)
            throws MalformedURLException {

        return new UrlResource(url) {
            @Override
            protected void customizeConnection(HttpURLConnection connection)
                    throws IOException {
                super.customizeConnection(connection);
                connection.setConnectTimeout(connectMs);
                connection.setReadTimeout(readMs);
                connection.setRequestProperty(
                        "Accept",
                        "application/rss+xml, application/atom+xml, " +
                        "application/xml;q=0.9");
            }
        };
    }

    @Bean
    IntegrationFlow normalizedFeedInbound(
            @Qualifier("normalizedFeedResource") Resource resource,
            @Qualifier("normalizedFeedMetadataStore") MetadataStore store,
            ArticleNoticeMapper mapper,
            @Value("${demo.feed.source-key}") String sourceKey,
            @Value("${demo.feed.metadata-key}") String metadataKey,
            @Value("${demo.feed.poll-delay-ms}") long delayMs,
            @Value("${demo.feed.max-messages-per-poll}") int maxPerPoll) {

        if (delayMs <= 0 || maxPerPoll <= 0) {
            throw new IllegalArgumentException(
                    "Feed poll delay and max messages must be positive");
        }

        return IntegrationFlow
                .from(Feed.inboundAdapter(resource, metadataKey)
                            .metadataStore(store),
                    endpoint -> endpoint.id("normalizedFeedInbound")
                            .poller(Pollers.fixedDelay(delayMs)
                                    .maxMessagesPerPoll(maxPerPoll)
                                    .errorChannel("feedNormalizationErrors")))
                .enrichHeaders(h -> h
                        .header("feedSourceKey", sourceKey))
                .transform(SyndEntry.class, mapper::map)
                .enrichHeaders(h -> h
                        .headerExpression(
                                "feedEntryId", "payload.entryId"))
                .channel("articleNoticeChannel")
                .get();
    }

    @Bean
    IntegrationFlow articleNoticeConsumer() {
        return IntegrationFlow.from("articleNoticeChannel")
                .handle(message -> {
                    ArticleNotice notice =
                            (ArticleNotice) message.getPayload();
                    System.out.printf(
                            "source=%s, article=%s, title=%s%n",
                            notice.sourceKey(), notice.entryId(),
                            notice.title());
                    // Production: call transactional/idempotent service.
                })
                .get();
    }

    @Bean
    IntegrationFlow feedNormalizationErrorFlow() {
        return IntegrationFlow.from("feedNormalizationErrors")
                .handle(message -> {
                    Throwable error = (Throwable) message.getPayload();
                    System.err.println("Feed error type: " +
                            error.getClass().getSimpleName());
                    // Production: classify HTTP/parser/mapper/DB,
                    // quarantine or retry per policy.
                })
                .get();
    }
}
```

The code uses `ArticleNotice` and `ArticleNoticeMapper` from sections 5–6. When copying into your practice project, place them in an appropriate package; `com.rometools.rome.feed.synd.SyndEntry` is imported here because the DSL references `SyndEntry.class`.

### 7.3. Step-by-Step Java DSL Breakdown

1. `Feed.inboundAdapter(resource, metadataKey)` creates the RSS/Atom source emitting individual `Message<SyndEntry>` instances.
2. `.metadataStore(store)` holds the source's **published-date watermark**, not a DB ledger.
3. `.poller(...)` governs schedule and message caps. An HTTP response with 50 items does not mean `maxMessagesPerPoll(10)` only downloads 10 items.
4. `.enrichHeaders(...feedSourceKey...)` attaches the **trusted** source key from configuration—never infer tenant IDs from publisher-supplied titles or URLs.
5. `.transform(SyndEntry.class, mapper::map)` invokes the mapper with the **payload**, returning `ArticleNotice`. Spring Integration builds the outbound message for the new payload.
6. `.enrichHeaders(...feedEntryId...)` reads `payload.entryId` on the record via SpEL to add a convenient routing/logging header.
7. `.channel("articleNoticeChannel")` decouples the source/transformer from downstream consumers.
8. `feedNormalizationErrors` receives errors raised in the **scheduled polling task**. Errors in an asynchronous consumer may need a dedicated error path.

### 7.4. Behavior When the Transformer Throws an Exception

If `mapper.map(entry)` throws `IllegalArgumentException` due to an invalid ID, title, or URL, **no `ArticleNotice` is produced** for that message. In a synchronous flow, the exception routes to the poller's error channel, yet:

- Do not treat a **single entry's** data defect as an HTTP/ROME failure of the entire feed.
- Do not assume the source will re-emit the failed entry, because the watermark may have already advanced.
- Do not merely log the exception and consider it durably quarantined.
- Do not endlessly retry the same invalid entry.

For critical sources, add an **accept/reject classification branch** right after receiving `SyndEntry` and persist rejected entries to durable quarantine (see section 11) before skipping—never let an exception lose track of an entry.

## 8. Header Propagation and Message Boundaries

### 8.1. Does a Payload Transformer Keep Custom Headers?

Spring Integration message-transforming endpoints typically transform the payload and **propagate eligible headers** to the output message. Example:

```text
Input Message<SyndEntry>
    headers.feedSourceKey = partner-releases
    headers.id = UUID-A
          |
        transform
          v
Output Message<ArticleNotice>
    headers.feedSourceKey = partner-releases
    headers.id = UUID-B (newly created by framework)
```

Custom `feedSourceKey` carries forward to subsequent endpoints unless modified by header filters/mappers. However, `MessageHeaders.ID` and `TIMESTAMP` are **read-only per-message-instance headers** that may be regenerated whenever a message changes. Never use them as article keys.

### 8.2. Transformer Returning a Full `Message` Directly

If you manually build a new `Message<ArticleNotice>`:

```java
import org.springframework.messaging.Message;
import org.springframework.integration.support.MessageBuilder;

Message<ArticleNotice> transformWholeMessage(
        Message<SyndEntry> input,
        ArticleNoticeMapper mapper) {

    ArticleNotice notice = mapper.map(input.getPayload());
    return MessageBuilder.withPayload(notice)
            .copyHeaders(input.getHeaders())
            .build();
}
```

You must explicitly preserve/copy needed headers instead of dropping `sourceKey` or correlation IDs. At the same time, never blindly forward every header across **trust boundaries**: `replyChannel`, `errorChannel`, internal trace state, non-serializable objects, authorization tokens, and sensitive headers may be unsafe to expose over Kafka/JMS/HTTP.

### 8.3. Headers for Routing, Payload for Business Data

Example:

```text
payload.entryId           = tag:example.org,2026:release-41
payload.sourceKey         = partner-releases
payload.updatedAt         = 2026-11-23T03:00:00Z

headers.feedSourceKey     = partner-releases
headers.feedEntryId       = tag:example.org,2026:release-41
headers.id                = message UUID, not entry ID
```

The payload holds the **authoritative contract**. Headers `feedSourceKey`/`feedEntryId` are small copies for convenient routing and tracing, not a second source of truth to mutate independently. In production, verify consistency if messages cross multiple systems or external actors could tamper with headers.

### 8.4. When Sending to Outbound Adapters

| Target | Recommended Payload | What to Govern |
|---|---|---|
| Database | DTO with source+entry ID and version/date | Unique constraints, UPSERT, transactions |
| Kafka | Explicit JSON/Avro/Protobuf schema | Stable record key, serializer, and header mapper |
| JMS/AMQP | Versioned DTO/JSON | Compatible header types, redelivery, and DLQ |
| HTTP outbound gateway | JSON object | `Content-Type`, HTTP timeouts, auth, idempotency key |
| File/SFTP | JSON lines or schema-bound batch files | Atomic write/rename, replays, duplicates |

Never assume every outbound adapter preserves all Spring headers or serializes Java `record`/`Instant` out of the box. For JSON, verify Jackson Java Time support and timestamp/null/schema-version conventions in the wire contract.

## 9. Identity, Revisions, and Idempotency After Normalization

### 9.1. Three Distinct Keys

Do not conflate these concepts:

```text
sourceKey        = partner-releases
entryId          = tag:example.org,2026:release-41
articleKey       = (sourceKey, entryId)
revisionKey      = updatedAt / publisher revision / contentHash
messageId        = new UUID generated by Spring Messaging
```

| Key | Purpose | Characteristics |
|---|---|---|
| `articleKey` | One article within a source's namespace | Remains stable when article is edited |
| `revisionKey` | Distinguishes revisions | Advances or changes when content changes |
| `messageId` | Identifies a message instance | Changes across transforms or retries |
| `metadataKey` | Feed source watermark namespace | Not an article ID |
| Kafka record key / idempotency header | Outbound routing and deduplication | Built by app from stable identity/version |

Example of the same ID emitted twice:

```text
10:00  id=release-41, published=T1, updated=T1, hash=A -> NEW
10:30  id=release-41, published=T1, updated=T1, hash=A -> SAME_VERSION
11:00  id=release-41, published=T1, updated=T2, hash=B -> UPDATED
11:30  id=release-41, published=T1, updated=T1, hash=A -> STALE_VERSION
12:00  id=release-41, published=T1, updated=T2, hash=C -> CONFLICT
```

If the rule is simply **notify once per article**, `articleKey` suffices to suppress duplicate notifications. If the app must update articles after publisher edits, track revisions/hashes and define explicit update rules.

### 9.2. Content Hashes Must Define Exact Inputs

A content checksum helps when publishers do not guarantee `updatedAt` changes. You must specify:

- Which fields are hashed? For instance: title, canonical URL, normalized body, categories.
- How are hashed fields ordered and UTF-8 encoded?
- Are `receivedAt`, message ID, poll timestamps, and telemetry excluded?
- Does HTML differing only in whitespace count as a revision?
- If a publisher changes only an enclosure/media file, is that a new revision?

Illustrative example computing a checksum over **two selected fields**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

String contentHash(ArticleNotice notice) {
    String canonical = notice.title() + "\n"
            + (notice.summaryRaw() == null
                    ? "" : notice.summaryRaw());
    try {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(canonical.getBytes(StandardCharsets.UTF_8));
        return HexFormat.of().formatHex(digest);
    }
    catch (NoSuchAlgorithmException ex) {
        throw new IllegalStateException("SHA-256 unavailable", ex);
    }
}
```

This is an **example policy**, not a universal hash valid for every publisher. It omits `canonicalUrl`, `categories`, enclosures, and dates, so changes exclusively in those fields will go undetected. Pick fields per business requirements, version your hash function, and test determinism.

### 9.3. Database Unique Key Protects Final Outcomes

PostgreSQL example:

```sql
CREATE TABLE feed_article (
    source_key       VARCHAR(128) NOT NULL,
    entry_id         VARCHAR(768) NOT NULL,
    schema_version   VARCHAR(16) NOT NULL,
    title            VARCHAR(1024) NOT NULL,
    canonical_url    VARCHAR(2048),
    published_at     TIMESTAMPTZ,
    updated_at       TIMESTAMPTZ,
    content_sha256   CHAR(64) NOT NULL,
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_key, entry_id)
);
```

When receiving the DTO:

1. Validate `schemaVersion` and required fields.
2. Look up/upsert by `(source_key, entry_id)` **atomically in a transaction**.
3. If no row exists, insert the initial record.
4. If checksum/revision matches, skip duplicate.
5. If a newer valid revision arrives, update or append to a history table.
6. If checksum differs with the same timestamp, apply a conflict policy—never overwrite silently.
7. If publishing events to Kafka/JMS/HTTP, write a **transactional outbox** record in the same DB transaction so delivery workers send afterward.

Never execute two independent steps "SELECT if absent → INSERT" without a unique constraint: two pods can both see "absent" and insert duplicate rows.

### 9.4. Feed Watermark Is Not an Article Ledger

Spring Integration **6.5** docs describe `FeedEntryMessageSource` reducing re-emission using a **published-date watermark** stored in `MetadataStore` under `metadataKey`. Once the source skips an entry with an older `publishedDate`, neither the mapper nor downstream idempotency **ever sees that entry**.

Two scenarios to watch:

- Publisher adds a **late-arriving** new article whose `entryId` is new yet `publishedAt` is older than the watermark.
- Publisher edits an existing article, keeping `publishedAt` unchanged while updating `updatedAt` or summary.

A clean transformer cannot fix **the source not emitting a message**. To catch such cases, add snapshot reconciliation, a history API, or an updated-time cursor feeding through **the same mapper + DB ledger** to compare IDs and revisions.

## 10. JSON Contracts and Schema Evolution Across Service Boundaries

### 10.1. Example JSON for `ArticleNotice`

```json
{
  "schemaVersion": "1",
  "sourceKey": "partner-releases",
  "entryId": "tag:example.org,2026:release-41",
  "title": "API 4.1 released",
  "canonicalUrl": "https://feeds.example.org/releases/41",
  "publishedAt": "2026-11-23T02:00:00Z",
  "updatedAt": "2026-11-23T03:00:00Z",
  "receivedAt": "2026-11-23T03:01:15Z",
  "author": null,
  "summaryRaw": "<p>Release summary</p>",
  "summaryType": "html",
  "categories": ["release", "api"]
}
```

These values are examples. This JSON is **not** automatically produced by `FeedEntryMessageSource`: the application performs mapping and serialization. `summaryRaw` still contains external HTML and must not be rendered raw in a UI.

### 10.2. Wire Data Types

| Java Type | Recommended JSON | Notes |
|---|---|---|
| `Instant` | ISO-8601 UTC string | Standardize on `Z` zone; avoid ambiguous local times |
| `List<String>` | JSON array | Clarify whether ordering is contractually significant |
| `String canonicalUrl` | String or null | Never trigger automatic HTTP fetches |
| `String schemaVersion` | Fixed version string | Consumers must validate supported versions |
| `String summaryRaw` | String or null | Untrusted HTML; requires escaping/sanitization |
| `String entryId` | Exact source ID | Never substitute message UUID |

With Jackson, enable Java Time support so `Instant` serializes as ISO-8601 rather than assuming any default serializer produces the JSON above. Example:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

String json = mapper.writeValueAsString(articleNotice);
```

This requires compatible Jackson Databind and `jackson-datatype-jsr310`. `articleNotice` is an existing DTO variable in the method/lab. Keep Jackson at the serialization boundary—never let `ArticleNoticeMapper` call DBs or brokers directly.

### 10.3. Compatibility When DTO Schemas Evolve

| Change | Impact Level |
|---|---|
| Adding an optional field with a clear default | Usually easier to keep backward-compatible |
| Changing `publishedAt` from String to epoch number | Breaks consumers parsing ISO-8601 |
| Renaming `entryId` to `guid` | Breaks data keys and deduplication |
| Changing `sourceKey` or ID normalization rules | Can cause DB to treat every article as a new identity |
| Replacing raw HTML with sanitized HTML without renaming field | Can mislead consumers about trust level |
| Changing `summaryType` semantics | Requires a new schema version and contract tests |

An explicit `schemaVersion` tells consumers how to interpret payloads. If using Schema Registry/Avro/Protobuf, declare optionality, field evolution, and compatibility rules in the schema registry itself. Do not treat a Java `record` as a cross-language wire schema.

### 10.4. Do Not Abuse Spring Message Headers

When publishing to Kafka/JMS/AMQP, map only truly necessary headers:

```text
feedSourceKey = partner-releases
feedEntryId   = tag:example.org,2026:release-41
schemaVersion = 1
```

These are application-designed custom headers. Never send raw `replyChannel`, `errorChannel`, `SyndContent` objects, oversized HTML, or credential tokens across a broker. Adapters apply distinct header mappers and serializers; test on the actual target protocol.

## 11. Handling Mapping Errors: Fail-Fast or Classified Outcomes?

### 11.1. Fail-Fast Is a Starting Point, Not Always a Production Policy

The mapper in section 6 throws `IllegalArgumentException` on missing IDs, missing titles, bad URLs, or oversized summaries. With a synchronous `DirectChannel` inside the polling task, this exception routes to the poller's error channel.

However, a single entry's defect is **not necessarily** an HTTP failure or document-wide parse failure. Simply logging and dropping it leaves the source watermark advanced so the entry will not re-emit. Infinitely retrying the same broken entry also achieves nothing until the publisher fixes it.

Separate outcomes clearly:

| Outcome | Action |
|---|---|
| `NORMALIZED` | Route `ArticleNotice` to business channel |
| `MISSING_ID` | Durable quarantine or ask source to supply GUID |
| `INVALID_TITLE` | Quarantine / investigate source contract |
| `INVALID_URL` | Quarantine or set `canonicalUrl=null` if policy permits |
| `OVERSIZED_CONTENT` | Enforce cap, quarantine, do not log raw content |
| `UNSUPPORTED_FEED_FORMAT` | Document-level error; no entry to transform |
| `BUSINESS_DB_FAILURE` | Transaction/retry; do not classify as mapper error |

### 11.2. `MappingOutcome` Pattern for Parsed Entries

An alternative to throwing exceptions directly is turning every entry into a **typed result**:

```java
public sealed interface MappingOutcome
        permits MappingOutcome.Accepted, MappingOutcome.Rejected {

    record Accepted(ArticleNotice notice)
            implements MappingOutcome {
    }

    record Rejected(
            String sourceKey,
            String rawEntryId,
            String errorCode)
            implements MappingOutcome {
    }
}
```

A classifier wrapping the mapper:

```java
import com.rometools.rome.feed.synd.SyndEntry;

public final class FeedEntryClassifier {
    private final ArticleNoticeMapper mapper;
    private final String sourceKey;

    public FeedEntryClassifier(
            ArticleNoticeMapper mapper, String sourceKey) {
        this.mapper = mapper;
        this.sourceKey = sourceKey;
    }

    public MappingOutcome classify(SyndEntry entry) {
        try {
            return new MappingOutcome.Accepted(mapper.map(entry));
        }
        catch (IllegalArgumentException ex) {
            // Do not embed raw exception/body inside the message.
            return new MappingOutcome.Rejected(
                    sourceKey, entry.getUri(), "INVALID_ENTRY");
        }
    }
}
```

You can then use a Transformer returning `MappingOutcome` and a router splitting across two channels. This is an **alternative** to `.transform(... mapper::map)` in the main flow—do not run both simultaneously:

```java
// Alternative DSL snippet downstream of Feed inbound, with classifier injected:
.transform(SyndEntry.class, classifier::classify)
.route(MappingOutcome.class,
        result -> result instanceof MappingOutcome.Accepted
                ? "acceptedMappingChannel"
                : "rejectedMappingChannel")
```

The accepted channel extracts `MappingOutcome.Accepted.notice()` to pass `ArticleNotice` into the DB writer; the rejected channel **durably persists** `MappingOutcome.Rejected` alongside any snapshot/entry reference. Returning a single generic `"INVALID_ENTRY"` code is insufficient in production: classify granular error codes, bound lengths, and protect source evidence.

**Do not confuse `MappingOutcome.Rejected` with a Spring Integration `ErrorMessage`.** It is a business DTO used to **route an already-parsed message**, while the error channel continues handling task/handler exceptions.

### 11.3. Quarantine Needs Durable Data and Lifecycle

For a rejected entry:

```text
sourceKey      = partner-releases
rawEntryId     = null
failureStage   = NORMALIZE
errorCode      = MISSING_STABLE_ID
snapshotRef    = optional encrypted object-store reference
firstSeenAt    = UTC
attemptCount   = 1
status         = OPEN
```

If you need **raw XML** to re-parse after a publisher fix, capture snapshots via a dedicated HTTP fetch layer. The Feed adapter does not guarantee `SyndEntry` retains the complete raw HTTP body or source headers.

Quarantine stores need access control, retention, size caps, auditing, re-validation on replay, and DB idempotency. Never blindly replay untrusted HTML/URLs straight into notifications.

### 11.4. Parse Errors Happen Before the Mapper

A truncated RSS document, mis-encoded XML, or an HTML login page causes ROME to fail **before any `SyndEntry` exists**. `MappingOutcome` and entry filters never see this failure. Use the poller error channel, HTTP instrumentation, and separate document-level quarantine where needed.

For HTTP `304 Not Modified` in conditional polling, never pass an empty body to ROME; inspect status in the HTTP client ahead of parsing. For `429`/`503`, apply backoff/quota policies rather than retrying the transformer.

## 12. Unit-Testing the Mapper with `SyndEntryImpl`

You do not need a Spring `ApplicationContext` to test pure mapper rules. ROME supplies `SyndEntryImpl`, `SyndLinkImpl`, `SyndContentImpl`, etc., to build test fixtures directly.

### 12.1. Testing IDs, Dates, Titles, and `Clock`

JUnit 5 example:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Date;

import com.rometools.rome.feed.synd.SyndEntry;
import com.rometools.rome.feed.synd.SyndEntryImpl;
import org.junit.jupiter.api.Test;

class ArticleNoticeMapperTest {

    private final Instant receivedAt =
            Instant.parse("2026-11-23T06:00:00Z");
    private final ArticleNoticeMapper mapper =
            new ArticleNoticeMapper(
                    "partner-releases",
                    Clock.fixed(receivedAt, ZoneOffset.UTC));

    @Test
    void mapsDatesAndStableIdentity() {
        SyndEntry entry = new SyndEntryImpl();
        entry.setUri("tag:example.org,2026:release-41");
        entry.setTitle("  API  4.1   released ");
        entry.setPublishedDate(Date.from(
                Instant.parse("2026-11-23T02:00:00Z")));
        entry.setUpdatedDate(Date.from(
                Instant.parse("2026-11-23T03:00:00Z")));

        ArticleNotice result = mapper.map(entry);

        assertEquals("1", result.schemaVersion());
        assertEquals("partner-releases", result.sourceKey());
        assertEquals("tag:example.org,2026:release-41",
                result.entryId());
        assertEquals("API 4.1 released", result.title());
        assertEquals(Instant.parse("2026-11-23T02:00:00Z"),
                result.publishedAt());
        assertEquals(Instant.parse("2026-11-23T03:00:00Z"),
                result.updatedAt());
        assertEquals(receivedAt, result.receivedAt());
    }

    @Test
    void rejectsMissingIdentity() {
        SyndEntry entry = new SyndEntryImpl();
        entry.setTitle("No GUID");

        assertThrows(IllegalArgumentException.class,
                () -> mapper.map(entry));
    }
}
```

When applying in a project, include compatible test dependencies such as `spring-boot-starter-test`; do not run builds or create test files on the learner's behalf while authoring Knowledge content.

### 12.2. Testing Multi-Link Atom Entries

```java
import java.util.List;
import com.rometools.rome.feed.synd.SyndEntryImpl;
import com.rometools.rome.feed.synd.SyndLinkImpl;

SyndEntryImpl entry = new SyndEntryImpl();
entry.setUri("tag:example.org,2026:release-41");
entry.setTitle("Release 4.1");

SyndLinkImpl enclosure = new SyndLinkImpl();
enclosure.setRel("enclosure");
enclosure.setType("application/pdf");
enclosure.setHref("https://cdn.example.org/41.pdf");

SyndLinkImpl alternate = new SyndLinkImpl();
alternate.setRel("alternate");
alternate.setType("text/html");
alternate.setHref("https://feeds.example.org/releases/41");

entry.setLinks(List.of(enclosure, alternate));
ArticleNotice notice = mapper.map(entry);

// Expected: canonicalUrl of alternate HTML,
// NOT the enclosure PDF.
```

Here `mapper` refers to the `ArticleNoticeMapper` instance created in the test above. Prefer concrete assertions over console printing; in hands-on exercises, add cases for `rel=self`, differing `hreflang`, null `type`, and disallowed URLs.

### 12.3. Key Unit Test Matrix

| Case | Input | Expected Outcome |
|---|---|---|
| Plain string RSS GUID | `release-41` | Identity preserved |
| Atom ID as URN/tag | `tag:...` | Does not require HTTP scheme |
| Entry missing ID | `uri=null` | Rejected/quarantined per policy |
| Title with extra whitespace and combining Unicode | `"  API   4.1 "` | NFC and whitespace normalized |
| Null `published` | `publishedDate=null` | DTO retains null |
| Null `updated` | `updatedDate=null` | DTO retains null |
| Multi-link Atom | `alternate`/`self`/`enclosure` | Selects `alternate` HTML |
| Canonical URL with `javascript:` | Non-HTTP(S) URI | Rejected |
| Canonical URL with userinfo | `https://user:pass@host` | Rejected |
| Categories with null/blank/duplicates | ROME list | Normalized and deduplicated |
| Oversized summary | Exceeds policy | Rejected/quarantined |
| Fixed `receivedAt` | `Clock.fixed` | Deterministic test output |
| Same ID mapped twice | Different poll times | `articleKey` remains identical |
| Same ID with different `updated` | Revision | Version policy governs outcome |

## 13. Integration Flow Testing with RSS/Atom Fixtures

### 13.1. Offline RSS Fixture

Place `sample-feed.xml` in `src/test/resources` **in your practice project**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Integration Lab</title>
    <link>https://feeds.example.org/</link>
    <description>Sample announcements</description>
    <item>
      <guid isPermaLink="false">release-41</guid>
      <title>Release 4.1</title>
      <pubDate>Mon, 23 Nov 2026 02:00:00 GMT</pubDate>
      <link>https://feeds.example.org/releases/41</link>
    </item>
    <item>
      <guid isPermaLink="false">release-42</guid>
      <title>Release 4.2</title>
      <pubDate>Mon, 23 Nov 2026 03:00:00 GMT</pubDate>
      <link>https://feeds.example.org/releases/42</link>
    </item>
  </channel>
</rss>
```

The Java DSL source in a lab can replace the URL `Resource`:

```java
import org.springframework.core.io.ClassPathResource;
import org.springframework.integration.feed.dsl.Feed;

var feedSpec = Feed.inboundAdapter(
        new ClassPathResource("sample-feed.xml"),
        "feeds:lab:normalized:v1");
```

Use an **isolated `SimpleMetadataStore` per test case**, or reset keys intentionally in the test setup. Reusing stale watermarks can cause "zero messages" due to prior test state rather than the mapper.

### 13.2. End-to-End Flow Verification

A solid integration test checks:

1. Feed adapter reads the RSS/Atom fixture with ROME.
2. `Message<SyndEntry>` receives `feedSourceKey` from configuration.
3. Transformer emits `Message<ArticleNotice>`.
4. Test handler receives **two** DTOs for the two new GUIDs (assuming empty initial metadata and source emission).
5. Assert `schemaVersion`, `sourceKey`, `entryId`, `title`, `Instant` fields, and `canonicalUrl`.
6. Assert application-added headers without assuming the Feed adapter creates `feedEntryId` by itself.
7. Re-poll the same fixture to observe watermark behavior without treating that test as an end-to-end exactly-once proof.

To test HTTP status codes, timeouts, `429`, or malformed XML, use a mock HTTP server instead of `ClassPathResource`. To test duplicate commits, use a database with unique constraints.

### 13.3. Testing Header Transformations

Construct a synthetic `Message<SyndEntry>` with headers:

```text
feedSourceKey = partner-releases
correlationKey = partner-releases|release-41
```

Pass it through the transformer and verify **allowlisted** headers arrive at the consumer. Also confirm message UUIDs may change and must not serve as article IDs. If a transformer builds a full `Message`, verify `copyHeaders(...)` is invoked properly.

## 14. Operations, Security, and Resource Limits

### 14.1. Metrics to Track

| Suggested Metric | Meaning |
|---|---|
| `feed_source_emitted_total` | How many `SyndEntry` items did the source emit? |
| `feed_transform_success_total` | How many DTOs succeeded? |
| `feed_transform_rejected_total{reason}` | How many entries failed validation? |
| `feed_title_missing_total` | Is the source omitting titles? |
| `feed_identity_missing_total` | Rate of items missing GUID/Atom ID |
| `feed_invalid_url_total` | URLs violating policy |
| `feed_payload_serialized_bytes` | Outbound DTO/JSON size |
| `feed_business_insert_total` | New articles committed |
| `feed_business_update_total` | Revisions ingested |
| `feed_business_duplicate_total` | Unchanged entries skipped |
| `feed_quarantine_open_total` | Entries awaiting quarantine review |
| `feed_outbox_pending_total` | Notifications committed yet unsent |
| `feed_transform_duration_ms` | Mapper processing latency |

These are **suggested metrics**, not all built-in Spring Integration metrics. Prefer low-cardinality labels like source alias, reason enum, and version; never put entry IDs, raw URLs, titles, or ETags into metric labels.

### 14.2. Controlled Logging

```text
event=feed_article_normalized
sourceKey=partner-releases
entryIdHash=9e41...ab21
schemaVersion=1
publishedAt=2026-11-23T02:00:00Z
updatedAt=2026-11-23T03:00:00Z
result=SUCCESS
```

Never log `summaryRaw`, raw XML, HTTP credentials, URLs with tokens, or sensitive HTML content. When tracing, use hashed/aliased IDs and request correlation per application data-retention rules.

### 14.3. External Payload Data Is Untrusted

| Risk | Mitigation |
|---|---|
| XSS from summary/title | Escape/sanitize per rendering context |
| SSRF from link/enclosure | Never fetch in mapper; enforce allowlist + redirect/DNS checks on fetch |
| Oversized XML/body | Cap HTTP responses and parser limits, not just DTO sizes |
| Excessive categories/links | Cap collection sizes; guard heap usage |
| XML external entity / DTD | Harden parser settings; never enable external entities casually |
| Header injection | Validate scalars before copying to HTTP headers |
| Oversized broker messages | Monitor serialized JSON bytes, quotas, and DLQs |
| PII/secrets in payloads | Classify, encrypt, enforce retention, restrict logs |
| Identity spoofing | Take `sourceKey` from trusted registry, never from external titles/links |

A syntactically valid `URI` does not mean the host is safe to request. An HTML fragment parsed by ROME does not mean it is safe to display.

### 14.4. Backpressure and Performance

Pure mappers are fast, though HTML parsing or hashing huge bodies consumes CPU. When DB handlers are slow:

- Set an appropriate `maxMessagesPerPoll` to limit message bursts, keeping in mind ROME may already have parsed the full XML.
- Cap source HTTP response sizes ahead of ROME for large external feeds.
- You can decouple inbound and downstream via a broker/durable queue for backpressure, provided serialization, retries, and idempotency are protected.
- With async consumers, handler errors no longer stay inside the polling error channel.
- Never place raw `SyndEntry` instances onto long-lived queues when a compact, stable DTO schema works instead.

### 14.5. Runbook When Normalization Fails Repeatedly

1. Check `sourceKey`, RSS/Atom format, ROME version, and source emission counts.
2. Distinguish HTTP/parse errors (no message created) from mapper validation errors (`SyndEntry` exists).
3. For null IDs, verify whether the publisher omitted GUIDs or the source mapped fields unexpectedly.
4. For oversized titles/summaries, check size policies and faulty upstream data—never truncate important content silently.
5. For multi-link Atom entries, inspect `rel`/`type`/`hreflang`; never try to fetch non-HTTP URIs.
6. Check watermarks and backlogs; never wipe all metadata just because one entry failed.
7. Use quarantine/snapshots/historical APIs for targeted replays.
8. Verify the DB ledger, outbox, and notification state to avoid duplicate side effects.

## 15. Scenario-Based Hands-on Labs

### Lab A — Minimal RSS to `ArticleNotice`

1. Create an RSS fixture with two items having GUID, title, `pubDate`, and link.
2. Parse via `Feed.inboundAdapter(...)`.
3. Attach `.transform(SyndEntry.class, mapper::map)`.
4. Verify the transformed payload is an `ArticleNotice` with accurate ID, title, and `Instant`.
5. Compare with the original `SyndEntry` payload.

**Result:** understand transformation at the adapter-to-domain boundary.

### Lab B — Multi-Link Atom

1. Create an Atom entry with `alternate` (`text/html`), `self` (`application/atom+xml`), and `enclosure` (PDF) links.
2. Run the mapper from section 6 and log `canonicalUrl`.
3. Reorder the links to verify the enclosure is never chosen by mistake.
4. Test missing `rel` or non-HTML `type` and verify policy fallbacks.
5. Never fetch those URLs inside mapper tests.

**Result:** canonical URL selection follows explicit rules, not the first link element.

### Lab C — Nullable Dates and UTC

1. Create an RSS item missing `pubDate` yet retaining GUID/title.
2. Run the mapper and observe `publishedAt=null` if the source emits the entry.
3. Create an Atom entry with only `updated` and no `published`.
4. Verify `updatedAt` and `publishedAt` in the DTO.
5. Use `Clock.fixed` so `receivedAt` stays deterministic across test runs.

**Result:** the three timestamps cannot be merged arbitrarily.

### Lab D — Missing or Altered IDs

1. Create an RSS item lacking a GUID.
2. Observe the mapper failing fast and hitting error handling.
3. Test the `MappingOutcome.Rejected` classifier routing to quarantine.
4. For a publisher with immutable links, implement an explicit **link-fallback ID policy** and test for collisions.
5. Compare preserving `id` as-is vs. auto-lowercasing to see collision risks.

**Result:** distinguish raw publisher identity from contracted application keys.

### Lab E — Unicode, Titles, and Categories

1. Create a title containing repeated whitespace and decomposed Unicode.
2. Verify `normalizeTitle` applies NFC and whitespace normalization as expected.
3. Add `SyndCategory` items with null, blank, and duplicate names.
4. Assert the resulting category list is deduplicated and capped at 32 items.
5. Ensure arbitrary categories are never used to route to unauthorized beans.

**Result:** normalizing display fields differs from normalizing identity.

### Lab F — HTML Summaries and Payload Size

1. Create a `SyndContent` containing `<script>...` HTML in an isolated lab.
2. Verify the mapper neither renders nor logs raw HTML.
3. Confirm `summaryRaw` remains marked untrusted in the DTO.
4. Pass a summary exceeding 16,384 characters and verify policy rejection.
5. For downstream UIs, use a vetted HTML sanitizer/escaper—never regex-based XSS filtering.

**Result:** parsing and normalizing do not automatically make external content safe.

### Lab G — Header Propagation

1. Send a message carrying `feedSourceKey` and correlation context.
2. Transform the payload to `ArticleNotice`.
3. Verify required custom headers survive to the downstream consumer.
4. Compare message UUIDs before and after.
5. Test a transformer returning a custom full `Message` without copying headers, then fix it with `copyHeaders`.

**Result:** payload identity and message headers follow separate lifecycles.

### Lab H — Publishing JSON to a Broker

1. Serialize `ArticleNotice` with Jackson and `JavaTimeModule`.
2. Inspect ISO-8601 UTC formatting, nulls, and the `categories` array.
3. Configure a Kafka/JMS test adapter mapping only allowlisted custom headers.
4. Set a stable record key derived from `source + entryId`.
5. Confirm the downstream deserializer requires no ROME classes on its classpath.

**Result:** DTOs and wire schemas decouple consumers from the Feed adapter.

### Lab I — Versioning, Retries, and Duplicates

1. Ingest an article with ID `A` and checksum `v1`.
2. Replay `A` with the same checksum; verify the DB skips it.
3. Change `updatedAt` or summary to produce `v2` and apply your version policy.
4. Replay stale `v1` after `v2` and verify it never overwrites backward.
5. Test identical `updatedAt` with a differing hash and record a conflict.

**Result:** ID deduplication and revision updates are two distinct rules.

### Lab J — Restarts and Watermarks

1. Poll a fixture with `SimpleMetadataStore`.
2. Restart the application context and observe the source re-emitting entries.
3. Verify the DB unique key still prevents creating duplicate rows.
4. Swap in a persistent store in the lab environment.
5. Observe how changing `metadataKey` makes the source see old entries as new again.

**Result:** source metadata is not a business acknowledgment.

### Lab K — Late-Arriving or Edited Articles

1. Advance the source watermark to T3.
2. Have the publisher add a new entry ID with an older `published=T2`.
3. Edit an older Atom entry keeping `published` fixed while updating `updated=T4`.
4. Observe cases where the source emits no message for the mapper.
5. Feed entries from a snapshot/historical API through the same mapper and version-aware DB UPSERT.

**Result:** a transformer cannot replace complete source ingestion.

### Lab L — Error Channel and Quarantine

1. Pass an entry with a `javascript:` URL into the mapper.
2. Observe the transformation failure in a synchronous flow.
3. Switch to `MappingOutcome` so data defects are not misclassified as HTTP errors.
4. Save durable quarantine records with source ID, reason, and snapshot reference.
5. Fix the policy/source, replay with auditing, and verify DB idempotency.

**Result:** never let a mapping failure lose track of an article.

### Self-Check Questions

1. Does Feed inbound 6.5 emit `Message<SyndEntry>` or `Message<SyndFeed>` per entry?
2. Why shouldn't raw ROME objects be sent over Kafka/JMS?
3. Is `entry.getUri()` always an HTTP URL?
4. How do `publishedAt`, `updatedAt`, and `receivedAt` differ?
5. When Atom has multiple links, why shouldn't you blindly pick the first link?
6. Why shouldn't GUID/Atom IDs be lowercased automatically?
7. Can `MessageHeaders.ID` serve as an idempotency key?
8. When is `getDescription().getValue()` safe to render as HTML?
9. How does a transformer returning a DTO payload differ from returning a full `Message`?
10. Why is `List.copyOf` helpful inside the `record`?
11. How does `schemaVersion` help manage contract evolution?
12. When the mapper fails, is the source guaranteed to re-emit the entry on the next poll?
13. Why is snapshot reconciliation needed for older published dates?
14. Should a content hash include `receivedAt`?
15. If the DB committed and the broker timed out, which step should retry?

## 16. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| RSS/Atom Feed adapter emits standard JSON payloads | Default payload per entry is a ROME `SyndEntry` |
| One HTTP response equals one message | One RSS/Atom XML can produce many `Message<SyndEntry>` messages |
| Renaming fields alone is complete normalization | You need rules for nulls, identity, time, links, security, and versioning |
| Atom ID is always a fetchable article URL | Atom ID may be a URN or `tag:` identifier |
| Every RSS item has a valid GUID and `pubDate` | Either may be missing or unstable |
| `updatedAt` equals `publishedAt` | Articles can be revised after publication |
| `MessageHeaders.TIMESTAMP` is the publication date | It is the message creation timestamp |
| Using message UUID as article ID stops duplicates | New UUIDs appear on retries and restarts |
| Lowercase or normalize GUIDs the same way as titles | Can cause identity collisions |
| The first Atom link is always the canonical HTML page | Must inspect `rel`, `type`, and `hreflang` |
| A parseable `URI` is safe to HTTP GET | Still requires DNS, redirect, host, and network policies |
| HTML parsed by ROME is safe to render immediately | Remains untrusted data requiring escaping/sanitization |
| A Java record caps serialized payload size | Measure serialized bytes and enforce broker/HTTP quotas |
| A DTO wrapping `SyndEntry` is still decoupled from ROME | Remains tied to the ROME classpath and mutable object graph |
| Feed adapter auto-creates headers for every field | Custom headers must be enriched explicitly |
| Payload transforms must always construct `MessageBuilder` manually | Returning the payload directly is simpler and safer |
| Transforms keep the same message UUID across all steps | Framework may regenerate ID/timestamp when messages mutate |
| Any default JSON serializer understands `Instant` | Verify Java Time support and formatting |
| `schemaVersion` is the application version | It is the data contract version |
| Source watermark proves the DB committed | Source metadata is not a business transaction |
| Mappers can recover entries skipped by the source | Transformers only see entries that were emitted |
| Every mapping error should retry immediately | Invalid data needs quarantine and remediation |
| DB unique keys catch all revisions automatically | You need a version/hash policy and conditional UPSERT |
| DB commit guarantees broker delivery succeeded | Use an outbox and idempotency for at-least-once delivery |

## 17. References

- [Spring Integration 6.5 — Feed Adapter](https://docs.spring.io/spring-integration/reference/6.5/feed.html): `Feed.inboundAdapter`, ROME, `Message<SyndEntry>`, queue, and watermark.
- [Spring Integration 6.5 — Transformer](https://docs.spring.io/spring-integration/reference/6.5/transformer.html): message-to-message/payload transformers, Java DSL, and JSON transformers.
- [Spring Integration 6.5 — Message](https://docs.spring.io/spring-integration/reference/6.5/message.html): payloads, headers, read-only ID/timestamp, and message lifecycle.
- [Spring Integration 6.5 — Header Enricher](https://docs.spring.io/spring-integration/reference/6.5/content-enrichment.html): `.enrichHeaders(...)`, static values, and SpEL expressions.
- [Spring Integration 6.5 — Java DSL API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html): `transform(Class, GenericTransformer)` and endpoint DSLs.
- [ROME SyndEntry API](https://javadoc.io/static/com.rometools/rome/2.1.0/com/rometools/rome/feed/synd/SyndEntry.html): URI, title, dates, links, categories, contents, enclosures.
- [ROME SyndLink API](https://javadoc.io/static/com.rometools/rome/2.1.0/com/rometools/rome/feed/synd/SyndLink.html): `getHref`, `getRel`, `getType`, `getHreflang`.
- [Spring Integration 6.5 — Metadata Store](https://docs.spring.io/spring-integration/reference/6.5/meta-data-store.html): source state and restart limitations.
- [RFC 4287 — Atom Syndication Format](https://www.rfc-editor.org/rfc/rfc4287): `atom:id`, `updated`, `published`, `link rel`, and entry semantics.
- [ROME project](https://rometools.github.io/rome/): RSS/Atom parsers and syndication model.

**Key takeaway:** Feed inbound brings external data into Spring Integration as **`Message<SyndEntry>`**. Normalization should convert `SyndEntry` into an **immutable DTO payload with an explicit schema**: `sourceKey + entryId` for identity, separate `published`/`updated`/`received` timestamps, links chosen by `rel`/`type`, content always treated as untrusted, and categories/optional fields constrained carefully. Transformers do not replace source watermarks or DB idempotency; pair them with validation/quarantine, JSON contracts, unique keys/versioning, durable recovery, and outboxes when passing data to downstream adapters.
