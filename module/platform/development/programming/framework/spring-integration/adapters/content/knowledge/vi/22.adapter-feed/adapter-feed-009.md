# Chuẩn hóa entry thành message payload trong Spring Integration

## 1. Bài toán: không để các hệ thống sau phụ thuộc trực tiếp vào ROME

Ứng dụng tổng hợp bản tin kỹ thuật lấy RSS và Atom từ nhiều nhà cung cấp. Với Feed inbound channel adapter, Spring Integration phát mỗi mục tin dưới dạng `Message<SyndEntry>`. Trong lúc thử nghiệm, một handler có thể gọi ngay `entry.getTitle()` và `entry.getLink()`. Nhưng khi pipeline kết nối database, HTTP gateway, JMS, AMQP, Kafka hoặc một ứng dụng khác, việc truyền nguyên `SyndEntry` sẽ tạo nhiều ràng buộc:

- Hệ thống nhận phải biết thư viện **ROME** và các kiểu `SyndContent`, `SyndLink`, `SyndCategory`, `Date`.
- RSS có thể thiếu `guid/pubDate`; Atom dùng `id/updated/published` và nhiều `link rel` khác nhau.
- Một entry có thể chứa HTML, URI ngoài ý muốn, ký tự Unicode chưa chuẩn hoặc collections có thể thay đổi.
- `MessageHeaders.ID` và `MessageHeaders.TIMESTAMP` không phải ID/ngày công bố của bài viết.
- Phát lại sau restart tạo message mới cho cùng một bài; mã downstream phải có identity ổn định để deduplicate.
- Serializing một ROME object sang broker khiến consumer phụ thuộc Java classpath, phiên bản thư viện và chính sách serialization.

Giải pháp là đặt một **Transformer** sau Feed inbound: chuyển `SyndEntry` thành một **payload nghiệp vụ rõ hợp đồng**, ví dụ `ArticleNotice` hoặc `FeedArticleEvent`, rồi mới gửi vào `MessageChannel` chung.

```text
RSS/Atom (HTTP)
   -> FeedEntryMessageSource
   -> Message<SyndEntry>                 (dữ liệu thư viện ROME)
   -> Validate + Normalize Transformer
   -> Message<ArticleNotice>             (hợp đồng của ứng dụng)
   -> MessageChannel
   -> DB / JMS / AMQP / Kafka / HTTP
```

Bài **“Chuẩn hóa entry thành message payload”** nằm trong chương **Adapter Feed** của module `SPRING_INTEGRATION_ADAPTERS`. Module nghiên cứu inbound/outbound adapter, gateway, poller, `MessageChannel`, tích hợp file/SFTP/HTTP/JMS/AMQP/Kafka/database, hợp đồng message, xử lý lỗi và vòng đời kết nối. Điểm tập trung của bài này là **thiết kế và chuyển đổi payload**, không phải thay thế tính năng polling hoặc bộ lọc thời gian của Feed adapter.

Sau bài học, bạn có thể:

1. Giải thích payload ban đầu của Feed inbound và lý do dùng một DTO độc lập với ROME.
2. Lập hợp đồng `sourceKey, entryId, publishedAt, updatedAt, title, canonicalUrl, categories, summary` có chính sách null rõ ràng.
3. Chuẩn hóa ngày sang `Instant`, kiểm tra GUID/Atom ID, chọn đúng Atom `alternate link` và giới hạn dữ liệu không tin cậy.
4. Viết Java 17 `record` bất biến cùng một mapper có thể unit-test.
5. Dùng Java DSL `.transform(SyndEntry.class, mapper::map)` để tạo `Message<ArticleNotice>`.
6. Phân biệt payload transformation với header enrichment, header propagation và message UUID.
7. Xử lý entry không hợp lệ qua error/quarantine, tránh bỏ sót sau source watermark.
8. Thiết kế hợp đồng JSON, version/idempotency, kiểm thử RSS/Atom và vận hành production.

## 2. Điểm chuyển đổi trong kiến trúc

```mermaid
flowchart TD
    A["Publisher RSS / Atom"] --> B["Poller + FeedEntryMessageSource"]
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

| Thành phần | Input | Output | Điều cần nhớ |
|---|---|---|---|
| `FeedEntryMessageSource` | URL/`Resource` RSS hoặc Atom | Mỗi lần `receive()` có thể trả một `Message<SyndEntry>` | Nguồn có queue nội bộ và watermark ngày |
| `Header Enricher` | `Message<SyndEntry>` | Message cùng payload và custom headers | Nên gắn source key từ cấu hình đáng tin |
| `Transformer` | `SyndEntry` | `ArticleNotice` | Kiểm tra/chuẩn hóa, không ghi DB ngoài ý muốn |
| `MessageChannel` | `Message<ArticleNotice>` | Chuyển tới endpoint kế tiếp | Không tự tạo durable storage |
| `MessageHandler` | DTO + headers | DB record / outbound side effect | Idempotency và transaction ở đây |
| `MetadataStore` của Feed | `metadataKey` | Watermark source | Không phải acknowledgment database |

Spring Integration **6.5** dùng ROME và phát từng `SyndEntry` trong payload; một tài liệu feed có nhiều entry vẫn có thể tạo **nhiều message**. `maxMessagesPerPoll` điều tiết số message mỗi lượt, không phải số trường của DTO hay số entry trong XML.

### 2.1. Đừng nhầm payload và headers

Một message trước transform:

```text
payload: SyndEntry
  uri             = tag:example.org,2026:release-41
  title           = API 4.1 released
  publishedDate   = Date(...)
  updatedDate     = Date(...)
  links           = List<SyndLink>

headers:
  id              = UUID do Spring tạo
  timestamp       = thời điểm message được tạo
  feedSourceKey   = partner-releases (nếu ứng dụng thêm)
```

Sau transform:

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
  id              = UUID message mới theo quy tắc framework
  timestamp       = thời điểm message được tạo
  feedSourceKey   = partner-releases
  feedEntryId     = ... (nếu được enrich)
```

Hợp đồng chính về bài viết nên nằm trong **payload**, vì payload được dùng ở DB và các hệ thống khác. Header có thể chứa **context nhỏ và đáng tin** để routing, correlation và tracing. Không coi các trường RSS/Atom tự động trở thành header tên `feed_*`.

## 3. Bảng ánh xạ RSS/Atom sang payload chuẩn

ROME thể hiện các entry qua `com.rometools.rome.feed.synd.SyndEntry`. Các getter dưới đây được dùng trong nhánh ROME 2.x và có thể trả null hoặc collection rỗng tùy nguồn.

| Trường nguồn | ROME getter | Trường DTO đề xuất | Quy tắc |
|---|---|---|---|
| Source cấu hình ứng dụng | Không lấy từ entry | `sourceKey` | Lấy từ source registry đã duyệt |
| RSS `guid` / Atom `id` | `getUri()` | `entryId` | Giữ identity ổn định; không tự lower-case |
| RSS `title` / Atom `title` | `getTitle()` | `title` | Validate, chuẩn hóa Unicode/whitespace có kiểm soát |
| RSS `link` / Atom `link rel=alternate` | `getLink()` / `getLinks()` | `canonicalUrl` | Chọn link đúng rel/type, validate cú pháp |
| RSS `pubDate` / Atom `published` | `getPublishedDate()` | `publishedAt` | `Date -> Instant`; có thể null |
| Atom `updated` / metadata tương ứng | `getUpdatedDate()` | `updatedAt` | `Date -> Instant`; có thể null từ một số nguồn |
| RSS `description` / Atom `summary` | `getDescription()` | `summaryRaw` + `summaryType` | Nội dung **chưa tin cậy**, có thể là HTML |
| Atom content / RSS content module | `getContents()` | Tùy nhu cầu | Chỉ giữ nếu hợp đồng cần; giới hạn size |
| RSS/Atom author | `getAuthor()` / `getAuthors()` | `author` | Optional; không suy ra user quyền hạn |
| RSS category / Atom category | `getCategories()` | `categories: List<String>` | Loại null, chuẩn hóa, giới hạn số phần tử |
| Enclosure/media | `getEnclosures()` | DTO attachment riêng nếu cần | Không tự fetch tài nguyên từ URL ngoài |
| Thời điểm ứng dụng nhận | `Clock.instant()` | `receivedAt` | Không giả làm published/updated |
| Phiên bản schema đích | Hằng cấu hình/contract | `schemaVersion` | Cho phép consumer evolve độc lập |

### 3.1. RSS item và Atom entry không hoàn toàn tương đương

RSS 2.0 ví dụ:

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

Trong Atom 1.0, `updated` là thành phần bắt buộc của entry hợp lệ; `published` là tùy chọn. Trong RSS, một item có thể thiếu GUID hoặc pubDate. ROME có thể parse được XML nhưng `SyndEntry.getUri()`/`getPublishedDate()` vẫn null.

### 3.2. Chính sách cho entry thiếu ID

Khóa bền vững đề xuất:

```text
articleIdentity = (sourceKey, entryId)
```

Với Atom ID có dạng `tag:...` hay `urn:...`, đó **không phải HTTP URL cần fetch**. Với RSS `guid` có thể không phải permalink. Không cố chuyển `getUri()` sang `new URL(...)`.

Nếu thiếu ID:

1. Ưu tiên publisher sửa feed để cung cấp GUID/Atom ID ổn định.
2. Nếu một publisher RSS có hợp đồng **URL bài viết bất biến**, có thể dùng link làm fallback nhưng phải version policy rõ và validate URL.
3. Nếu không chứng minh được identity ổn định, đưa entry vào quarantine/review; đừng lấy title hoặc UUID của message làm key.

**Cẩn thận:** tùy thuật toán watermark của `FeedEntryMessageSource`, một entry thiếu ngày có thể không được phát. Transformer chỉ xử lý **những entry đã thành message**; nó không cứu dữ liệu đã bị source bỏ qua.

## 4. Quy tắc chuẩn hóa phải công khai và có thể kiểm thử

### 4.1. Phân biệt normalize và sửa nội dung gốc

| Dữ liệu | Nên làm | Không nên tự ý làm |
|---|---|---|
| `sourceKey` | Dùng alias do ứng dụng cấu hình, có namespace | Đọc tenant/quyền từ RSS title |
| `entryId` | Kiểm tra null, độ dài, ký tự bất hợp lệ | Lower-case, bỏ dấu, hash thầm lặng, đổi phần GUID |
| `title` | Trim, Unicode NFC, rút gọn whitespace, giới hạn length | Dùng làm ID, xóa ngẫu nhiên ký tự có nghĩa |
| `publishedAt/updatedAt` | Đưa về `Instant` UTC, giữ null khi hợp đồng cho phép | Thay missing `published` bằng timestamp message rồi ghi là published |
| `canonicalUrl` | Chọn `alternate` HTML hợp lệ, kiểm tra scheme/host | Tự tải link hoặc theo redirect để “xác thực” khi chưa có allowlist |
| `categories` | Bỏ null/blank, trim, distinct, giới hạn số category | Dùng dữ liệu nguồn làm tên bean/channel tùy ý |
| `summaryRaw` | Giới hạn kích thước, giữ type, phân loại untrusted | Chèn thẳng vào HTML UI hoặc header/baggage |
| `receivedAt` | Lấy từ `Clock` ứng dụng để test ổn định | Đưa vào idempotency key hoặc content checksum |

### 4.2. Không gộp ba đồng hồ làm một

```text
publishedAt = 2026-11-20T10:00:00Z   (publisher đăng)
updatedAt   = 2026-11-23T03:00:00Z   (publisher sửa)
receivedAt  = 2026-11-23T07:35:20Z   (hệ thống nhận)
```

Ba mốc trên trả lời ba câu hỏi khác nhau. Khi tính SLA ingestion, dùng receivedAt so với mốc nguồn đã chọn theo thỏa thuận. Khi đồng bộ bản sửa, dùng updatedAt/revision. Khi lọc bài “được đăng trong tháng”, dùng publishedAt.

Không dùng `MessageHeaders.TIMESTAMP` làm ngày bài: header này là thời điểm tạo **message instance**, có thể thay đổi khi transform/replay.

### 4.3. Canonical link của Atom

Một Atom entry có thể có nhiều link:

```xml
<link rel="alternate" type="text/html"
      href="https://feeds.example.org/articles/41"/>
<link rel="self" type="application/atom+xml"
      href="https://feeds.example.org/entries/41.atom"/>
<link rel="enclosure" type="application/pdf"
      href="https://cdn.example.org/docs/41.pdf" length="120000"/>
```

Chọn đúng `rel=alternate` với `type=text/html` khi mục tiêu là URL hiển thị bài; không lấy link đầu tiên hoặc enclosure. Với Atom, `rel` có thể thiếu và mặc định ngữ nghĩa là alternate theo RFC 4287; ứng dụng vẫn cần xét `type`/`hreflang` nếu có nhiều ngôn ngữ. Với RSS, `getLink()` thường là link tiện dụng.

Kiểm tra URI bằng `java.net.URI` **không phải** cơ chế SSRF hoàn chỉnh. Nó chỉ kiểm tra cú pháp/scheme/host. Nếu hệ thống cần tự fetch nội dung qua canonicalUrl, phải kiểm soát DNS/IP, redirect, host allowlist và mạng outbound riêng.

### 4.4. Summary và nội dung HTML

`SyndContent.getValue()` có thể là plain text, HTML hoặc XHTML tùy type và nguồn. Một DTO có tên `summaryRaw` là **untrusted string**, không phải HTML đã sanitize. Nếu consumer chỉ cần plain text, nên trích xuất và sanitize bằng một thư viện/processor được review riêng; không dùng regex xóa thẻ HTML làm cơ chế chống XSS.

Không gắn HTML dài hoặc ROME objects vào headers rồi chuyển thẳng sang Kafka/JMS. Header nên giữ các scalar nhỏ; payload/DB có hợp đồng content rõ và quy tắc render riêng.

## 5. Hợp đồng payload chuẩn: Java record bất biến

**`ArticleNotice.java`** (đặt trong project thực hành khi áp dụng):

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
        // Không giữ tham chiếu tới List có thể bị thay đổi từ ROME.
        categories = List.copyOf(
                categories == null ? List.of() : categories);
    }
}
```

### 5.1. Tại sao nên dùng record?

- Dữ liệu chỉ có các trường, không có logic polling hoặc session của adapter.
- Các kiểu `String`, `Instant`, `List<String>` dễ làm hợp đồng JSON hơn `SyndEntry` với graph ROME phức tạp.
- `record` giúp payload bất biến ở mức thành phần; `List.copyOf` phòng trường hợp collection bên ngoài bị sửa.
- Test mapper không cần khởi động Spring context hay gọi HTTP.
- Có chỗ để đặt `schemaVersion` và định nghĩa compatibility.

Lưu ý: bất biến Java record **không tự** bảo đảm nội dung được tin cậy. `summaryRaw` và canonicalUrl vẫn là dữ liệu do publisher cung cấp; chúng cần validation/sanitize theo nơi sử dụng.

### 5.2. Cần giữ cả raw input không?

Không nên giữ nguyên `SyndEntry` bên trong DTO để “tiện sau này”, vì điều đó phá mục tiêu độc lập thư viện. Nếu cần audit nguyên bản:

```text
ArticleNotice (payload chuẩn cho downstream)
  + sourceKey
  + entryId
  + optional rawSnapshotRef (ID tới object store an toàn)
```

Raw XML chỉ nên lưu riêng khi có mục đích, retention, encryption và quyền đọc cụ thể. Một `SyndEntry.getWireEntry()` không phải cơ chế thay thế durable raw snapshot HTTP.

## 6. Viết mapper Java có validation và null handling

Để dễ hiểu và test, mapper chỉ nhận **một `SyndEntry`** rồi trả một `ArticleNotice`. Không gọi database, Kafka hoặc HTTP bên trong mapper; không tạo `Message` thủ công nếu chỉ cần thay payload.

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
                    "sourceKey phải là alias đã được cấu hình");
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
                    "Feed entry summary vượt giới hạn size");
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
                    "Entry không có GUID/Atom ID ổn định");
        }
        if (!id.equals(id.strip()) || id.length() > MAX_ID_LENGTH) {
            throw new IllegalArgumentException(
                    "Entry ID có whitespace biên hoặc quá dài");
        }
        // Không lowercase, không bỏ dấu, không thay ID gốc.
        return id;
    }

    private static String normalizeTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException(
                    "Entry thiếu title theo business contract");
        }
        String normalized = Normalizer.normalize(
                title.strip(), Normalizer.Form.NFC)
                .replaceAll("\\s+", " ");
        if (normalized.length() > MAX_TITLE_LENGTH) {
            throw new IllegalArgumentException("Title quá dài");
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
                    "Optional metadata vượt size policy");
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
        // RSS thông thường sử dụng link của item.
        return entry.getLink();
    }

    private static String validateArticleUrl(String raw) {
        if (raw == null || raw.isBlank()) {
            return null; // canonicalUrl là optional trong demo.
        }
        if (raw.length() > 2048) {
            throw new IllegalArgumentException("Article URL quá dài");
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
                        "Article URL không thuộc HTTP/HTTPS URL hợp lệ");
            }
            // Chỉ kiểm tra cú pháp; KHÔNG gọi HTTP tại đây.
            return uri.normalize().toASCIIString();
        }
        catch (URISyntaxException ex) {
            throw new IllegalArgumentException(
                    "Article URL không parse được", ex);
        }
    }
}
```

### 6.1. Những gì mapper cố ý không làm

- **Không** gọi `HttpClient/RestClient` tới `getLink()` hoặc enclosure. URL syntax validation không chặn hết SSRF nếu sau này có bước fetch; bước fetch phải có allowlist/DNS/redirect policy riêng.
- **Không** coi `summaryRaw` là HTML đã được sanitize. Nếu cần plain text, tạo một `ContentSanitizer` dùng parser HTML đáng tin để convert/escape theo context; không dùng regex xóa tag.
- **Không** fallback `publishedAt = receivedAt`: điều đó làm giả lịch sử. Null được giữ để consumer quyết định.
- **Không** tự lower-case hoặc Unicode-normalize `entryId`: thay đổi identity có thể gom nhầm hai bài khác nhau.
- **Không** ghi database trong mapper: mapper phải thuần/độc lập với side effect, thuận lợi để retry và unit-test.
- **Không** dùng `receivedAt` trong idempotency key: nó thay đổi theo lần retry.
- **Không** gộp `updatedAt` vào `publishedAt` hay suy mọi nguồn đều cung cấp bản sửa.

Trong thực tế, một hợp đồng có thể chọn **quarantine** thay vì ném `IllegalArgumentException`. Ví dụ trên cố ý fail-fast để minh họa validation và đường error handling; phần sau mô tả khi nào nên trả một kết quả phân loại để không làm cả polling task xử lý lỗi như lỗi hạ tầng.

### 6.2. Lưu ý về chuẩn hóa Unicode

Unicode có thể biểu diễn một số chữ theo dạng ký tự dựng sẵn hoặc ký tự cơ sở kết hợp dấu. NFC giúp tiêu đề hiển thị/tìm kiếm nhất quán hơn, nhưng **không được áp dụng ngầm** cho RSS GUID/Atom ID nếu publisher chưa định nghĩa cách so sánh. Normalization quá mạnh (NFKC, lowercase toàn bộ, xóa dấu) có thể làm mất phân biệt giữa các identity hoặc title có ý nghĩa.

### 6.3. Giới hạn ví dụ

Mapper ở trên chỉ kiểm tra **độ dài tính bằng ký tự Java**; broker/database còn có giới hạn theo **UTF-8 bytes**, payload JSON và HTTP headers. Production phải kiểm tra kích thước message serialized, số link/enclosure, content type, Unicode và quota cho từng nguồn. Giới hạn `maxMessagesPerPoll` không kiểm soát độ lớn XML ban đầu.

## 7. Java DSL: chuyển `SyndEntry` thành `ArticleNotice`

Ví dụ sử dụng **Spring Boot 3.x + Spring Integration 6.5.x tương thích** và Java 17. Dùng dependency management/BOM để đảm bảo các module Spring Integration cùng một dòng.

### 7.1. Dependency và cấu hình

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

Các URL `feeds.example.org` là ví dụ, không khẳng định có feed công khai ở đó. Lab dùng mock HTTP server/fixture. Production chỉ gọi feed URL đã được duyệt, không chấp nhận một URL chưa kiểm soát từ người dùng.

### 7.2. Spring configuration

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
        return new SimpleMetadataStore(); // Chỉ cho lab.
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
                    "Feed poll delay và max messages phải dương");
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
                    // Production: gọi service transactional/idempotent.
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
                    // Production: phân loại HTTP/parser/mapper/DB,
                    // quarantine hoặc retry theo policy.
                })
                .get();
    }
}
```

Đoạn code trên sử dụng hai class `ArticleNotice` và `ArticleNoticeMapper` của phần 5–6. Khi copy vào project thực hành, đặt chúng trong package phù hợp; import `com.rometools.rome.feed.synd.SyndEntry` đã được khai báo trong cấu hình vì DSL sử dụng `SyndEntry.class`.

### 7.3. Giải thích Java DSL theo thứ tự

1. `Feed.inboundAdapter(resource, metadataKey)` tạo source RSS/Atom, phát từng `Message<SyndEntry>`.
2. `.metadataStore(store)` giữ **watermark theo ngày xuất bản** của source, không phải DB ledger.
3. `.poller(...)` quyết định lịch và giới hạn message. Một HTTP response chứa 50 bài không có nghĩa `maxMessagesPerPoll(10)` tải chỉ 10 bài.
4. `.enrichHeaders(...feedSourceKey...)` gắn mã nguồn **tin cậy** từ cấu hình. Không lấy tenant ID từ title/URL bài viết do publisher gửi.
5. `.transform(SyndEntry.class, mapper::map)` gọi mapper với **payload**, trả về `ArticleNotice`. Spring Integration tạo message đầu ra cho payload mới.
6. `.enrichHeaders(...feedEntryId...)` đọc `payload.entryId` của record bằng SpEL để tạo custom header tiện routing/log.
7. `.channel("articleNoticeChannel")` là điểm tách giữa nguồn/transformer và consumer.
8. `feedNormalizationErrors` nhận lỗi phát sinh trong **scheduled polling task**. Lỗi bên một consumer chạy bất đồng bộ có thể cần error path riêng.

### 7.4. Hành vi khi transformer ném exception

Nếu `mapper.map(entry)` ném `IllegalArgumentException` vì ID, title hoặc URL không hợp lệ, **không có `ArticleNotice` mới** từ message đó. Trong flow đồng bộ, lỗi có thể đi tới error channel của poller, nhưng:

- Không coi lỗi dữ liệu của **một entry** là lỗi HTTP/ROME của toàn bộ feed.
- Không mặc định rằng source sẽ phát lại entry bị fail vì watermark có thể đã tiến.
- Không ghi exception rồi coi đã quarantine bền vững.
- Không loop retry cùng một entry invalid vô hạn.

Với nguồn quan trọng, xây một **nhánh phân loại thành công/thất bại** ngay sau khi nhận `SyndEntry` và lưu durable quarantine (xem phần 11) trước khi bỏ qua; không để một exception làm mất dấu entry.

## 8. Header propagation và ranh giới Message

### 8.1. Payload transformer có giữ custom headers không?

Spring Integration message-transforming endpoint thông thường chuyển payload và **propagate headers** phù hợp sang message đầu ra. Ví dụ:

```text
Input Message<SyndEntry>
    headers.feedSourceKey = partner-releases
    headers.id = UUID-A
          |
        transform
          v
Output Message<ArticleNotice>
    headers.feedSourceKey = partner-releases
    headers.id = UUID-B (framework tạo mới)
```

Custom `feedSourceKey` được giữ cho các endpoint kế tiếp trong flow khi không có header filter/mapper làm thay đổi nó. Nhưng `MessageHeaders.ID` và `TIMESTAMP` là **read-only, dành cho message instance**, có thể được tạo lại khi message thay đổi. Không dùng chúng làm khóa bài viết.

### 8.2. Transformer tự trả full Message

Nếu bạn tự tạo một `Message<ArticleNotice>` mới:

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

Phải kiểm tra/copy header cần thiết thay vì bỏ quên source key hoặc correlation ID. Tuy nhiên, không sao chép mọi header khi gửi ra **ranh giới trust**: `replyChannel`, `errorChannel`, trace nội bộ, object không serializable, authorization và header chứa dữ liệu nhạy cảm có thể không phù hợp để mang qua Kafka/JMS/HTTP.

### 8.3. Header dùng cho routing, payload dùng cho nghiệp vụ

Ví dụ:

```text
payload.entryId           = tag:example.org,2026:release-41
payload.sourceKey         = partner-releases
payload.updatedAt         = 2026-11-23T03:00:00Z

headers.feedSourceKey     = partner-releases
headers.feedEntryId       = tag:example.org,2026:release-41
headers.id                = UUID message, không phải entry ID
```

Payload chứa **contract chính thức**. Header `feedSourceKey`/`feedEntryId` là bản sao nhỏ để router/tracing dùng thuận tiện, không phải nguồn sự thật thứ hai được thay đổi độc lập. Trong production nên kiểm tra consistency nếu message đi qua nhiều hệ thống hoặc bên ngoài có thể sửa headers.

### 8.4. Khi dùng outbound adapter

| Đích | Payload đề xuất | Điều cần kiểm soát |
|---|---|---|
| Database | DTO với source+entry ID, version/date | Unique constraint, UPSERT, transaction |
| Kafka | JSON/Avro/Protobuf schema rõ | Record key ổn định, serializer và header mapper |
| JMS/AMQP | DTO/JSON có version | Header types tương thích, redelivery và DLQ |
| HTTP outbound gateway | JSON object | Content-Type, HTTP timeout, auth, idempotency key |
| File/SFTP | JSON lines hoặc file batch theo schema | Atomic write/rename, replay, duplicate |

Không mặc định rằng mọi outbound adapter tự giữ nguyên tất cả headers của Spring hoặc tự biết serialize `record`/`Instant`. Với JSON, cần kiểm tra Jackson Java Time support và quy ước timestamp, null, schema version trong hợp đồng wire.

## 9. Identity, revision và idempotency sau khi chuẩn hóa

### 9.1. Ba loại khóa khác nhau

Đừng gộp các khái niệm sau:

```text
sourceKey        = partner-releases
entryId          = tag:example.org,2026:release-41
articleKey       = (sourceKey, entryId)
revisionKey      = updatedAt / publisher revision / contentHash
messageId        = UUID mới do Spring Messaging tạo
```

| Khóa | Mục đích | Đặc điểm |
|---|---|---|
| `articleKey` | Một bài trong namespace của nguồn | Ổn định khi bài được sửa |
| `revisionKey` | Phân biệt bản sửa | Có thể tăng hoặc đổi khi nội dung thay đổi |
| `messageId` | Định danh message instance | Có thể đổi sau transform hoặc retry |
| `metadataKey` | Namespace watermark của Feed source | Không phải ID bài viết |
| Kafka record key / idempotency header | Định tuyến và dedup khi gửi ra ngoài | Do ứng dụng xây từ identity/version ổn định |

Ví dụ cùng ID được xuất bản hai lần:

```text
10:00  id=release-41, published=T1, updated=T1, hash=A -> NEW
10:30  id=release-41, published=T1, updated=T1, hash=A -> SAME_VERSION
11:00  id=release-41, published=T1, updated=T2, hash=B -> UPDATED
11:30  id=release-41, published=T1, updated=T1, hash=A -> STALE_VERSION
12:00  id=release-41, published=T1, updated=T2, hash=C -> CONFLICT
```

Nếu chính sách chỉ **thông báo một lần cho mỗi bài**, `articleKey` đủ để tránh thông báo trùng. Nếu ứng dụng cần cập nhật bài sau khi publisher sửa, phải theo dõi revision/hash và chọn quy tắc update.

### 9.2. Content hash phải xác định rõ dữ liệu đầu vào

Content checksum có thể dùng khi publisher không bảo đảm `updatedAt` thay đổi. Nhưng cần quy định:

- Băm trường nào? Ví dụ title, canonical URL, body đã normalize, categories.
- Các trường dùng để băm được xếp thứ tự và mã hóa UTF-8 ra sao?
- Có loại trừ `receivedAt`, message ID, timestamp poll và dữ liệu telemetry không?
- HTML khác whitespace nhưng cùng nội dung có xem là bản sửa không?
- Nếu publisher chỉ đổi enclosure/media, có phải revision mới không?

Ví dụ minh họa cách tạo checksum trên **hai trường đã được lựa chọn**:

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
        throw new IllegalStateException("SHA-256 không khả dụng", ex);
    }
}
```

Đây là một **chính sách ví dụ**, không phải hash độc nhất đúng cho mọi publisher. Nó không tính canonicalUrl, categories, enclosure và date, nên sẽ không phát hiện thay đổi chỉ ở các trường ấy. Chọn nội dung theo nghiệp vụ, định nghĩa phiên bản hàm hash và test tính ổn định.

### 9.3. Database unique key bảo vệ kết quả cuối

Ví dụ PostgreSQL:

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

Khi nhận DTO:

1. Kiểm tra `schemaVersion` và các trường required.
2. Lookup/upsert theo `(source_key, entry_id)` **bằng thao tác atomic/transaction**.
3. Nếu chưa có row, insert bản đầu.
4. Nếu cùng checksum/revision, skip duplicate.
5. Nếu revision hợp lệ mới hơn, update hoặc ghi bảng history.
6. Nếu checksum khác nhưng timestamp trùng, áp dụng conflict policy; không overwrite âm thầm.
7. Nếu cần gửi sự kiện Kafka/JMS/HTTP, ghi **transactional outbox** trong cùng DB transaction, để delivery worker gửi sau.

Đừng dùng hai lệnh độc lập “SELECT thấy chưa có → INSERT” mà không có unique constraint: hai pod có thể cùng nhìn thấy “chưa có” rồi tạo dữ liệu trùng.

### 9.4. Feed watermark không phải ledger bài viết

Tài liệu Spring Integration **6.5** mô tả `FeedEntryMessageSource` giảm phát lại entry cũ bằng **published-date watermark** lưu trong `MetadataStore` theo `metadataKey`. Khi source đã quyết định không phát một entry có `publishedDate` cũ, mapper/downstream idempotency **không nhìn thấy entry đó**.

Hai tình huống cần lưu ý:

- Publisher bổ sung bài mới **đến muộn**, `entryId` mới nhưng `publishedAt` cũ hơn watermark.
- Publisher sửa bài đã tồn tại, giữ `publishedAt` nhưng đổi `updatedAt` hoặc summary.

Transformer chính xác không giải quyết được việc **source không phát message**. Nếu cần bắt những trường hợp này, bổ sung snapshot reconciliation/API lịch sử/cursor theo updated time rồi đưa qua **cùng mapper + DB ledger** để so ID/revision.

## 10. Hợp đồng JSON và schema evolution khi qua ranh giới dịch vụ

### 10.1. JSON ví dụ của `ArticleNotice`

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

Các giá trị chỉ là ví dụ. JSON này **không phải** kết quả tự động của `FeedEntryMessageSource`: ứng dụng phải thực hiện mapping và serialization. `summaryRaw` còn chứa HTML ngoài nguồn, không được render thẳng lên UI.

### 10.2. Kiểu dữ liệu trên wire

| Java type | JSON được khuyến nghị | Lưu ý |
|---|---|---|
| `Instant` | ISO-8601 UTC string | Quy ước zone `Z`, không dùng giờ local mơ hồ |
| `List<String>` | JSON array | Thứ tự có ý nghĩa theo hợp đồng hay không? |
| `String canonicalUrl` | String hoặc null | Không biến thành HTTP fetch tự động |
| `String schemaVersion` | String version cố định | Consumer phải kiểm tra các phiên bản được hỗ trợ |
| `String summaryRaw` | String hoặc null | HTML không tin cậy; yêu cầu escaping/sanitization |
| `String entryId` | Exact source ID | Không tự thay theo UUID message |

Với Jackson, cấu hình hỗ trợ Java Time để ghi `Instant` ở dạng ISO-8601; đừng mặc định một serializer bất kỳ sẽ ghi đúng như JSON trên. Ví dụ:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

ObjectMapper mapper = new ObjectMapper()
        .registerModule(new JavaTimeModule())
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

String json = mapper.writeValueAsString(articleNotice);
```

Đoạn này yêu cầu Jackson Databind và module `jackson-datatype-jsr310` tương thích. `articleNotice` là biến DTO có sẵn trong phương thức/lab. Đưa Jackson vào ranh giới serialization, không để `ArticleNoticeMapper` gọi trực tiếp vào DB hoặc broker.

### 10.3. Tương thích khi DTO đổi schema

| Thay đổi | Mức độ ảnh hưởng |
|---|---|
| Thêm trường optional có default rõ | Thường dễ tương thích ngược hơn |
| Đổi `publishedAt` từ String sang epoch number | Có thể phá consumer đang parse ISO-8601 |
| Đổi tên `entryId` sang `guid` | Có thể phá khóa dữ liệu và dedup |
| Thay nguồn `sourceKey` hoặc cách normalize ID | Có thể khiến DB coi toàn bộ bài là identity khác |
| Đưa HTML đã sanitize thay cho raw mà không đổi tên field | Có thể làm consumer hiểu sai trust level |
| Đổi ý nghĩa `summaryType` | Cần schema version mới/contract test |

Một `schemaVersion` rõ ràng giúp consumer biết cách diễn giải. Nếu dùng Schema Registry/Avro/Protobuf, nên mô tả optionality, field evolution và compatibility ngay tại hệ thống quản lý schema. Không dựa vào Java `record` như một wire schema đủ an toàn cho mọi ngôn ngữ.

### 10.4. Không lạm dụng Spring message headers

Khi gửi qua Kafka/JMS/AMQP, chỉ map các header thực sự cần:

```text
feedSourceKey = partner-releases
feedEntryId   = tag:example.org,2026:release-41
schemaVersion = 1
```

Chúng là custom headers do ứng dụng thiết kế. Không đưa nguyên `replyChannel`, `errorChannel`, object `SyndContent`, nội dung HTML quá lớn hoặc token credential qua broker. Các adapter có quy tắc header mapper/serializer riêng; cần test trên protocol đích.

## 11. Xử lý mapping error: fail-fast hay phân loại thành kết quả?

### 11.1. Fail-fast là điểm khởi đầu, không phải luôn là production policy

Mapper ở phần 6 ném `IllegalArgumentException` khi thiếu ID, thiếu title, URL sai hoặc summary quá lớn. Với `DirectChannel` đồng bộ trong polling task, exception này có thể được đưa vào poller error channel.

Tuy nhiên, lỗi một entry **không nhất thiết** là lỗi HTTP hoặc lỗi parse cả tài liệu. Nếu chỉ log rồi bỏ, watermark nguồn có thể đã tiến và entry không được phát lại. Retry vô hạn cùng entry lỗi cũng không giúp khi publisher chưa sửa.

Nên tách:

| Kết quả | Hành động |
|---|---|
| `NORMALIZED` | Đưa `ArticleNotice` sang business channel |
| `MISSING_ID` | Durable quarantine hoặc nguồn yêu cầu sửa GUID |
| `INVALID_TITLE` | Quarantine/điều tra hợp đồng source |
| `INVALID_URL` | Quarantine/đặt canonicalUrl=null nếu policy cho phép |
| `OVERSIZED_CONTENT` | Giới hạn, quarantine, không log raw content |
| `UNSUPPORTED_FEED_FORMAT` | Document-level error; không có entry để transform |
| `BUSINESS_DB_FAILURE` | Transaction/retry, không coi là lỗi mapper |

### 11.2. Mẫu MappingOutcome cho entry đã parse

Một thiết kế thay cho việc ném lỗi trực tiếp là biến mọi entry thành **một kết quả có kiểu**:

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

Một classifier dùng mapper:

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
            // Không ghi nguyên exception/raw body vào message.
            return new MappingOutcome.Rejected(
                    sourceKey, entry.getUri(), "INVALID_ENTRY");
        }
    }
}
```

Sau đó có thể dùng Transformer trả `MappingOutcome` và router rẽ hai channel. Đây là **một phương án thay thế** cho `.transform(... mapper::map)` trong flow chính, không chạy cả hai cùng lúc:

```java
// Phần DSL thay thế sau Feed inbound, với classifier được inject:
.transform(SyndEntry.class, classifier::classify)
.route(MappingOutcome.class,
        result -> result instanceof MappingOutcome.Accepted
                ? "acceptedMappingChannel"
                : "rejectedMappingChannel")
```

Channel accepted cần lấy `MappingOutcome.Accepted.notice()` rồi chuyển thành `ArticleNotice` trước khi ghi DB; channel rejected cần **lưu bền** `MappingOutcome.Rejected` cùng tham chiếu snapshot/entry nếu có. Chỉ trả lỗi dạng `"INVALID_ENTRY"` không đủ để vận hành đầy đủ: thực tế nên phân loại error code chi tiết, giới hạn và bảo vệ bằng chứng nguồn.

**Không coi `MappingOutcome.Rejected` là một `ErrorMessage` của Spring Integration.** Đây là DTO nghiệp vụ dùng để **route một message đã parse**, còn error channel vẫn phục vụ exception của task/handler.

### 11.3. Quarantine cần dữ liệu và vòng đời bền

Đối với entry không đạt:

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

Nếu cần **raw XML** để reparse sau khi sửa publisher, lưu snapshot qua một HTTP fetch layer riêng. Feed adapter không cam kết `SyndEntry` chứa đầy đủ HTTP body gốc hay mọi header nguồn.

Quarantine phải có quyền truy cập, retention, limit, audit, revalidation khi replay và DB idempotency. Đừng replay mù raw HTML/URL kém tin cậy rồi gửi notification ngay.

### 11.4. Parse lỗi xảy ra trước mapper

Một RSS document bị cắt, XML sai encoding hoặc server trả HTML login có thể khiến ROME thất bại **trước khi có `SyndEntry`**. `MappingOutcome`/entry filter không thấy được lỗi này. Dùng poller error channel, HTTP instrumentation và document-level quarantine riêng nếu yêu cầu.

Đối với `304 Not Modified` của conditional HTTP, không đưa body rỗng vào ROME; phải có HTTP client điều khiển status trước parse. Với `429/503`, dùng backoff/quota policy, không chỉ retry transformer.

## 12. Unit test mapper bằng `SyndEntryImpl`

Không cần chạy một Spring ApplicationContext cho các quy tắc thuần của mapper. ROME cung cấp `SyndEntryImpl`, `SyndLinkImpl`, `SyndContentImpl`,... để dựng fixture trực tiếp.

### 12.1. Kiểm thử ID, ngày, title và `Clock`

Ví dụ JUnit 5:

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

Khi áp dụng vào dự án, thêm dependency test tương thích, ví dụ `spring-boot-starter-test`; không dùng một bài viết Knowledge để chạy build hoặc tạo file test thay cho người học.

### 12.2. Kiểm thử Atom nhiều link

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

// Kỳ vọng: canonicalUrl của alternate HTML,
// KHÔNG phải enclosure PDF.
```

Ở đoạn này, `mapper` là biến `ArticleNoticeMapper` đã được tạo ở test phía trên. Ưu tiên test bằng assertion cụ thể thay vì chỉ print; trong bài thực hành bổ sung trường `rel=self`, `hreflang` khác nhau, type null và URL bị cấm.

### 12.3. Ma trận unit test quan trọng

| Case | Input | Kỳ vọng |
|---|---|---|
| RSS GUID có dạng chuỗi thường | `release-41` | Giữ identity |
| Atom ID là URN/tag | `tag:...` | Không yêu cầu HTTP scheme |
| Entry thiếu ID | `uri=null` | Reject/quarantine theo policy |
| Title có whitespace và Unicode kết hợp | `"  API   4.1 "` | Normalize NFC và whitespace |
| Published null | `publishedDate=null` | DTO giữ null |
| Updated null | `updatedDate=null` | DTO giữ null |
| Atom nhiều link | `alternate/self/enclosure` | Chọn alternate HTML |
| Canonical URL dùng `javascript:` | URI không phải HTTP(S) | Reject |
| Canonical URL có userinfo | `https://user:pass@host` | Reject |
| Categories có null/blank/trùng | List từ ROME | Chuẩn hóa, distinct |
| Summary rất lớn | Vượt policy | Reject/quarantine |
| ReceivedAt cố định | `Clock.fixed` | Test deterministic |
| Cùng ID qua hai lần map | Ngày poll khác | articleKey vẫn giống |
| Bài cùng ID nhưng updated khác | Bản sửa | Revision policy quyết định |

## 13. Kiểm thử integration flow với RSS/Atom fixture

### 13.1. Fixture RSS không cần Internet

Đặt `sample-feed.xml` vào `src/test/resources` **trong dự án thực hành**:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Integration Lab</title>
    <link>https://feeds.example.org/</link>
    <description>Thông báo ví dụ</description>
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

Java DSL source trong lab có thể thay URL Resource:

```java
import org.springframework.core.io.ClassPathResource;
import org.springframework.integration.feed.dsl.Feed;

var feedSpec = Feed.inboundAdapter(
        new ClassPathResource("sample-feed.xml"),
        "feeds:lab:normalized:v1");
```

Các test nên dùng `SimpleMetadataStore` **riêng cho mỗi case**, hoặc reset key một cách có chủ đích trong môi trường test. Nếu tái sử dụng watermark cũ, trường hợp “không có message” có thể do state test trước chứ không do mapper.

### 13.2. Kiểm tra luồng end-to-end

Một integration test hữu ích:

1. Feed adapter đọc fixture RSS/Atom bằng ROME.
2. `Message<SyndEntry>` được gắn `feedSourceKey` từ cấu hình.
3. Transformer tạo `Message<ArticleNotice>`.
4. Handler test nhận **hai** DTO cho hai GUID mới (trong điều kiện metadata ban đầu trống và chính sách nguồn phát chúng).
5. Assert `schemaVersion/sourceKey/entryId/title/Instant/canonicalUrl`.
6. Kiểm tra headers mà application thêm, không giả định Feed adapter tự tạo `feedEntryId`.
7. Poll lại cùng fixture để hiểu watermark, nhưng không dùng bài test đó làm bảo đảm end-to-end exactly-once.

Để kiểm tra HTTP status, timeout, 429 hoặc XML malformed, dùng mock HTTP server thay vì `ClassPathResource`. Để kiểm tra duplicate commit, dùng database với unique constraint.

### 13.3. Kiểm thử biến đổi header

Sử dụng một `Message<SyndEntry>` tự dựng có header:

```text
feedSourceKey = partner-releases
correlationKey = partner-releases|release-41
```

Đưa vào transformer và kiểm tra các header **được phép** vẫn có ở consumer. Đồng thời xác nhận message UUID có thể thay đổi và không được dùng làm ID bài. Nếu transformer tự tạo full `Message`, kiểm tra đã `copyHeaders(...)` hay chưa.

## 14. Vận hành, bảo mật và giới hạn tài nguyên

### 14.1. Các metric nên đo

| Metric gợi ý | Ý nghĩa |
|---|---|
| `feed_source_emitted_total` | Source phát bao nhiêu `SyndEntry`? |
| `feed_transform_success_total` | Bao nhiêu DTO tạo thành công? |
| `feed_transform_rejected_total{reason}` | Bao nhiêu entry bị validation reject? |
| `feed_title_missing_total` | Nguồn có thiếu title không? |
| `feed_identity_missing_total` | Tỷ lệ item thiếu GUID/Atom ID |
| `feed_invalid_url_total` | URL không qua policy |
| `feed_payload_serialized_bytes` | Kích thước DTO/JSON khi xuất |
| `feed_business_insert_total` | Bài mới được commit |
| `feed_business_update_total` | Bản sửa được nhập |
| `feed_business_duplicate_total` | Entry không đổi bị bỏ qua |
| `feed_quarantine_open_total` | Entry cần xử lý/quarantine |
| `feed_outbox_pending_total` | Notification đã commit nhưng chưa gửi |
| `feed_transform_duration_ms` | Chi phí xử lý mapper |

Đây là **metric do bài đề xuất**, không phải tất cả được Spring Integration tự phát. Ưu tiên label ít giá trị như source alias, reason enum và version; không dùng entry ID, raw URL, title hoặc ETag làm metric labels.

### 14.2. Log có kiểm soát

```text
event=feed_article_normalized
sourceKey=partner-releases
entryIdHash=9e41...ab21
schemaVersion=1
publishedAt=2026-11-23T02:00:00Z
updatedAt=2026-11-23T03:00:00Z
result=SUCCESS
```

Không log `summaryRaw`, raw XML, HTTP credential, URL có token hay content HTML nhạy cảm. Nếu cần trace, dùng hash/alias của ID và request correlation theo quy tắc lưu trữ dữ liệu của ứng dụng.

### 14.3. Payload dữ liệu ngoài là untrusted

| Rủi ro | Cách giảm |
|---|---|
| XSS từ summary/title | Escape/sanitize theo context hiển thị |
| SSRF từ link/enclosure | Không fetch trong mapper; allowlist + kiểm tra redirect/DNS khi fetch |
| Oversized XML/body | Giới hạn HTTP response và parser, không chỉ DTO size |
| Quá nhiều categories/links | Giới hạn số phần tử, kiểm soát heap |
| XML external entity / DTD | Cấu hình parser an toàn, không bật external entity tùy ý |
| Header injection | Validate các scalar trước khi đưa ra HTTP headers |
| Broker message quá lớn | Đo JSON serialized bytes, quota/DLQ |
| PII/secret trong payload | Phân loại, mã hóa, retention, hạn chế log |
| Identity spoofing | sourceKey từ registry tin cậy, không từ title/link ngoài |

Một URL syntax hợp lệ không đồng nghĩa host an toàn để request. Một HTML fragment ROME parse được không đồng nghĩa an toàn để hiển thị.

### 14.4. Backpressure và hiệu năng

Mapper thuần thường xử lý nhanh, nhưng parse HTML hoặc tính hash body lớn có thể tốn CPU. Nếu handler lưu DB chậm:

- Dùng `maxMessagesPerPoll` phù hợp để hạn chế burst message, nhưng biết rằng XML có thể đã được ROME parse toàn bộ.
- Giới hạn source HTTP response size trước ROME khi nguồn ngoài lớn.
- Có thể tách inbound và downstream qua broker/durable queue để tạo backpressure, song phải bảo vệ serialization/retry/idempotency.
- Với consumer bất đồng bộ, lỗi của handler không còn nằm chắc trong polling error channel.
- Không đặt raw `SyndEntry` vào queue dài hạn nếu schema đích có thể chuyển sang DTO nhỏ/ổn định.

### 14.5. Runbook khi normalization fail liên tục

1. Kiểm tra source key, RSS/Atom format, phiên bản ROME và số message được source phát.
2. Phân biệt HTTP/parse error (chưa có message) với mapper validation error (đã có `SyndEntry`).
3. Với ID null, xác minh publisher thật sự thiếu GUID hoặc source không ánh xạ theo mong đợi.
4. Với title/summary quá dài, kiểm tra policy size và nguồn bị lỗi, không cắt âm thầm dữ liệu quan trọng.
5. Với Atom nhiều links, kiểm tra rel/type/hreflang; với URI không phải HTTP, không cố fetch.
6. Kiểm tra watermark và backlog; đừng reset toàn bộ metadata chỉ vì một entry fail.
7. Dùng quarantine/snapshot/historical API để replay có mục tiêu.
8. Xác minh DB ledger, outbox và notification state để tránh side effect trùng.

## 15. Bài thực hành theo tình huống

### Lab A — RSS sang `ArticleNotice` tối thiểu

1. Tạo RSS fixture có hai item, mỗi item có GUID/title/pubDate/link.
2. Parse bằng `Feed.inboundAdapter(...)`.
3. Gắn `.transform(SyndEntry.class, mapper::map)`.
4. Kiểm tra payload sau transform có kiểu `ArticleNotice` và đúng ID/title/Instant.
5. So sánh với payload ban đầu `SyndEntry`.

**Kết quả:** hiểu transformation tại ranh giới adapter và domain.

### Lab B — Atom nhiều link

1. Tạo Atom entry có link `alternate text/html`, `self application/atom+xml` và `enclosure PDF`.
2. Dùng mapper phần 6, ghi `canonicalUrl`.
3. Thử đổi thứ tự link để chắc chắn không lấy nhầm enclosure.
4. Thử `rel` thiếu hoặc `type` khác HTML; kiểm tra fallback theo policy.
5. Không tự tải các URL trong test mapper.

**Kết quả:** canonical URL là lựa chọn có quy tắc, không phải phần tử link đầu tiên.

### Lab C — Ngày nullable và UTC

1. Tạo RSS item thiếu pubDate, nhưng còn GUID/title.
2. Thử mapper, quan sát `publishedAt=null` nếu source phát entry.
3. Tạo Atom entry chỉ có updated, không có published.
4. Xác minh `updatedAt`/`publishedAt` trong DTO.
5. Dùng `Clock.fixed` để nhận cùng `receivedAt` trong mọi lần chạy test.

**Kết quả:** ba loại thời gian không thể gộp tùy tiện.

### Lab D — ID thiếu hoặc bị biến đổi

1. Tạo RSS item thiếu GUID.
2. Xem mapper fail-fast và đường error handling.
3. Thử classifier `MappingOutcome.Rejected` để đưa vào quarantine.
4. Với publisher có link bất biến, viết một **policy fallback ID riêng** và test collision.
5. So sánh việc giữ nguyên `id` với lowercase tự động; kiểm tra nguy cơ gom nhầm.

**Kết quả:** phải phân biệt identity gốc và khóa ứng dụng đã có contract.

### Lab E — Unicode, title và category

1. Tạo title chứa whitespace lặp và Unicode tổ hợp.
2. Kiểm tra `normalizeTitle` xử lý NFC/whitespace như mong muốn.
3. Tạo `SyndCategory` có name null/blank/trùng.
4. Assert list categories đã distinct và giới hạn 32 mục.
5. Đảm bảo không dùng category tùy ý để route tới bean không được phép.

**Kết quả:** normalize trường hiển thị khác với normalize identity.

### Lab F — Summary HTML và payload size

1. Tạo `SyndContent` với HTML `<script>...` trong lab cô lập.
2. Đảm bảo mapper không render, không log HTML raw.
3. Kiểm tra `summaryRaw` vẫn là dữ liệu untrusted ở DTO.
4. Cho summary vượt 16.384 ký tự, xác minh bị reject theo policy.
5. Với downstream UI, dùng HTML sanitizer/escape được review, không sử dụng regex làm XSS defense.

**Kết quả:** parse và normalize không tự biến nội dung ngoài nguồn thành nội dung an toàn.

### Lab G — Header propagation

1. Đưa vào một message có `feedSourceKey` và correlation context.
2. Transform payload sang `ArticleNotice`.
3. Kiểm tra custom header cần thiết còn ở consumer sau transform.
4. So sánh message UUID trước và sau.
5. Thử transformer tự tạo full Message không copy headers, rồi sửa bằng `copyHeaders`.

**Kết quả:** payload identity và message headers có vòng đời khác nhau.

### Lab H — Xuất JSON sang broker

1. Serialize `ArticleNotice` bằng Jackson có JavaTimeModule.
2. Kiểm tra ISO-8601 UTC, null và mảng categories.
3. Tạo Kafka/JMS test adapter, map một số custom headers đã whitelist.
4. Dùng record key ổn định dựa trên source+entry ID.
5. Deserializer phía nhận không cần ROME classpath.

**Kết quả:** DTO và wire schema làm giảm coupling với Feed adapter.

### Lab I — Versioning, retry và duplicate

1. Import một bài ID A, checksum v1.
2. Replay A cùng checksum, DB phải skip.
3. Đổi `updatedAt` hoặc summary để có v2, áp dụng version policy.
4. Replay v1 cũ sau v2, không overwrite ngược.
5. Cho cùng updatedAt nhưng hash khác; ghi nhận conflict.

**Kết quả:** chống trùng theo ID và cập nhật bài theo revision là hai quy tắc khác nhau.

### Lab J — Restart và watermark

1. Dùng `SimpleMetadataStore` để poll fixture.
2. Restart application context, quan sát nguồn có thể phát lại entry.
3. DB unique key vẫn phải ngăn tạo thêm record cùng bài.
4. Thay store bền vững ở môi trường lab.
5. Kiểm tra thay `metadataKey` có thể làm source thấy lại entry cũ.

**Kết quả:** source metadata không phải business acknowledgment.

### Lab K — Bài đến muộn hoặc được sửa

1. Để watermark source tiến đến T3.
2. Publisher thêm entry ID mới với published T2 cũ hơn.
3. Sửa một Atom entry cũ, giữ published nhưng updated T4.
4. Quan sát source có thể không tạo message để mapper xử lý.
5. Từ snapshot/historical API, đưa từng entry qua mapper rồi DB UPSERT version-aware.

**Kết quả:** transformer không thay thế cơ chế lấy dữ liệu nguồn đầy đủ.

### Lab L — Error channel và quarantine

1. Cho mapper gặp một entry có URL `javascript:`.
2. Quan sát lỗi khi transform trong flow đồng bộ.
3. Thử nhánh `MappingOutcome` để không phân loại lỗi dữ liệu thành HTTP error.
4. Lưu quarantine bền, có source ID, reason và snapshot reference.
5. Sửa policy/nguồn, replay có audit và kiểm tra DB idempotency.

**Kết quả:** không để một mapping error khiến bài bị mất dấu.

### Câu hỏi tự kiểm tra

1. Feed inbound 6.5 tạo `Message<SyndEntry>` hay `Message<SyndFeed>` theo mỗi entry?
2. Vì sao không nên đưa nguyên ROME object qua Kafka/JMS?
3. `entry.getUri()` có luôn là HTTP URL không?
4. `publishedAt`, `updatedAt` và `receivedAt` khác nhau thế nào?
5. Khi Atom có nhiều link, vì sao không lấy link đầu tiên?
6. Vì sao không nên lowercase GUID/Atom ID một cách tự động?
7. `MessageHeaders.ID` có làm idempotency key được không?
8. Khi nào `getDescription().getValue()` an toàn để render HTML?
9. Transformer trả payload DTO khác gì tự trả full `Message`?
10. Vì sao `List.copyOf` hữu ích trong record?
11. `schemaVersion` giúp xử lý thay đổi contract ra sao?
12. Khi mapper fail, source có chắc phát lại entry ở lần poll sau không?
13. Vì sao snapshot reconciliation cần thiết với bài published cũ?
14. Content hash có nên chứa `receivedAt` không?
15. Nếu DB đã commit nhưng broker timeout, nên retry khâu nào?

## 16. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| RSS/Atom Feed adapter đã phát payload JSON chuẩn | Payload mặc định mỗi entry là `SyndEntry` từ ROME |
| Mỗi HTTP response tương đương một message | Một RSS/Atom XML có thể sinh nhiều `Message<SyndEntry>` |
| Chỉ đổi tên field đã là chuẩn hóa đầy đủ | Cần quy tắc null/identity/time/link/security/version |
| Atom ID luôn là URL bài có thể fetch | Atom ID có thể là URN/tag identifier |
| Mọi RSS item đều có GUID/pubDate | Có thể thiếu hoặc không ổn định |
| `updatedAt` là `publishedAt` | Một bài có thể được sửa sau xuất bản |
| `MessageHeaders.TIMESTAMP` chính là ngày xuất bản | Đó là thời điểm tạo message |
| Dùng message UUID làm ID bài sẽ chống trùng | UUID mới có thể xuất hiện sau retry/restart |
| Lowercase hoặc normalize GUID giống normalize title | Có thể làm va chạm identity |
| Atom link đầu tiên luôn là canonical HTML | Phải xét `rel/type/hreflang` |
| `URI` parse được là URL an toàn để HTTP GET | Còn cần DNS/redirect/host/network policy |
| ROME parse được HTML nên có thể render ngay | Vẫn là dữ liệu untrusted, cần escape/sanitize |
| Java record tự giới hạn serialized payload | Phải đo bytes và quota ở broker/HTTP |
| DTO chứa `SyndEntry` thì vẫn độc lập ROME | Vẫn phụ thuộc classpath và mutable graph |
| Header được Feed adapter tự tạo cho mọi field | Cần enrich custom headers tường minh |
| Payload transform phải luôn tự dựng `MessageBuilder` | Trả payload trực tiếp thường đơn giản và an toàn hơn |
| Transform giữ nguyên message UUID qua mọi bước | ID/timestamp có thể thay đổi khi message mutate |
| JSON serializer mặc định nào cũng hiểu `Instant` | Cần kiểm tra Java Time support/format |
| `schemaVersion` giống phiên bản ứng dụng | Nó là phiên bản hợp đồng dữ liệu |
| Source watermark chứng minh DB đã commit | Metadata source không phải business transaction |
| Mapper có thể nhận entry bị source bỏ qua | Transformer chỉ thấy entry được phát |
| Mọi mapping error đều nên retry ngay | Invalid data cần quarantine/remediation |
| DB unique key loại được mọi bản sửa | Cần version/hash policy và UPSERT có điều kiện |
| Gửi broker thành công được bảo đảm nhờ DB commit | Cần outbox/idempotency khi delivery có thể lặp |

## 17. Tài liệu tham khảo

- [Spring Integration 6.5 — Feed Adapter](https://docs.spring.io/spring-integration/reference/6.5/feed.html): `Feed.inboundAdapter`, ROME, `Message<SyndEntry>`, queue và watermark.
- [Spring Integration 6.5 — Transformer](https://docs.spring.io/spring-integration/reference/6.5/transformer.html): message-to-message/payload transformer, Java DSL và JSON transformers.
- [Spring Integration 6.5 — Message](https://docs.spring.io/spring-integration/reference/6.5/message.html): payload, headers, read-only ID/timestamp, lifecycle của message.
- [Spring Integration 6.5 — Header Enricher](https://docs.spring.io/spring-integration/reference/6.5/content-enrichment.html): `.enrichHeaders(...)`, static values và SpEL expressions.
- [Spring Integration 6.5 — Java DSL API](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/BaseIntegrationFlowDefinition.html): `transform(Class, GenericTransformer)` và các endpoint DSL.
- [ROME SyndEntry API](https://javadoc.io/static/com.rometools/rome/2.1.0/com/rometools/rome/feed/synd/SyndEntry.html): URI/title/dates/links/categories/contents/enclosures.
- [ROME SyndLink API](https://javadoc.io/static/com.rometools/rome/2.1.0/com/rometools/rome/feed/synd/SyndLink.html): `getHref/getRel/getType/getHreflang`.
- [Spring Integration 6.5 — Metadata Store](https://docs.spring.io/spring-integration/reference/6.5/meta-data-store.html): state nguồn và hạn chế restart.
- [RFC 4287 — Atom Syndication Format](https://www.rfc-editor.org/rfc/rfc4287): `atom:id`, `updated`, `published`, `link rel` và feed entry semantics.
- [ROME project](https://rometools.github.io/rome/): RSS/Atom parser và mô hình syndication.

**Ghi nhớ:** Feed inbound đưa dữ liệu ngoài vào Spring Integration dưới dạng **`Message<SyndEntry>`**. Bước chuẩn hóa nên biến `SyndEntry` thành **DTO payload bất biến có schema rõ ràng**: `sourceKey + entryId` cho identity, published/updated/received là những mốc thời gian riêng, link chọn theo rel/type, content luôn là untrusted, và categories/fields optional được xử lý có kiểm soát. Transformer không thay thế source watermark hay DB idempotency; phải kết hợp validation/quarantine, hợp đồng JSON, unique key/version, durable recovery và outbox khi đưa dữ liệu sang các adapter downstream.
