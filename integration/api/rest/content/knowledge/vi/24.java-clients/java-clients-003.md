# Xây dựng URI, mã hóa path và query đúng ngữ cảnh

## 1. Một dấu `/` hoặc `&` có thể đổi nghĩa request

Client Java gọi:

~~~http
GET /api/v1/files/{fileId}?q={searchTerm}&tag={tag} HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

Dữ liệu: `fileId="ACME/2026"`, `searchTerm="C++ & Hà Nội"`, `tag="c#java"`. Nối `baseUrl + "/files/" + fileId + "?q=" + searchTerm` khiến slash thành **path separator**, ampersand thành **query separator**, dấu `#` thành **fragment**; khoảng trắng và Unicode cũng chưa được mã hóa. Kết quả có thể gọi sai resource, sai bộ lọc, sai chữ ký, thậm chí vượt ranh giới bảo mật.

Trong chương **Client Java** của module **INTEGRATION_API_REST**, bài này hướng dẫn phân biệt **path segment/query value**, percent-encoding UTF-8 và cách dùng Java `URI`, Spring `UriComponentsBuilder`, `RestClient`/`WebClient`; liên hệ resource/URI, HTTP, cache, idempotency, OpenAPI, authorization và kiểm thử.

**Kết quả cần đạt:** tạo URI đúng cấu trúc, encode dữ liệu đúng một lần, bảo vệ base host/credentials, kiểm thử các ký tự `/+&#=%` và Unicode.

> **Quy tắc:** Dựng **cấu trúc URI trước**, đưa user data vào **template variables**, strict-encode theo ngữ cảnh. Không ghép chuỗi đã encode của một thành phần vào thành phần khác.

## 2. Cấu trúc URI và percent-encoding

Theo **RFC 3986**:

~~~text
https://api.example.test:8443/api/files/123?q=java&tag=rest#section
|___|   |________________| |____________| |____________| |_____|
scheme       authority          path          query      fragment
~~~

**Path** có segments phân tách bằng `/`; **query** theo convention `name=value` phân tách bằng `&`; **fragment** sau `#` không được gửi tới HTTP origin. Scheme/authority quyết định **đích gọi**, không cho user kiểm soát nếu client được thiết kế cho một service cố định.

**Unreserved:** `A-Z a-z 0-9 - . _ ~`. **Reserved:** `:/?#[]@!$&'()*+,;=`. Ký tự reserved có thể là **cú pháp** hoặc **dữ liệu**, tùy vị trí. Percent-encoding là `%HH` trên từng byte, với Unicode dùng **UTF-8**:

~~~text
"Hà"       → H%C3%A0
"A/B"      → A%2FB (nếu là một path segment)
"C++"      → C%2B%2B (query value)
"a&b"      → a%26b
"c#java"   → c%23java
"100%"     → 100%25
~~~

Không áp quy tắc “encode mọi dấu `/`” cho toàn URI: **slash cấu trúc cần giữ**, slash **trong một ID** mới cần biểu diễn như data.

## 3. Path segment, encoded slash và traversal

~~~text
/api/files/ACME/2026       # Hai path segments: ACME và 2026
/api/files/ACME%2F2026     # Một segment chứa dữ liệu "ACME/2026"
~~~

Với template `/api/files/{fileId}`, `fileId` là một **giá trị opaque**, không phải chuỗi path tự do. Encode slash thành `%2F` đúng ở phía URI builder, **nhưng server/proxy/Servlet container/Spring Security firewall có thể chặn hoặc decode encoded slash**, nên không mặc định cách này hoạt động end-to-end. Tốt hơn: dùng ID **UUID, ULID, base64url không padding** hoặc thay đổi contract với business ID chứa slash.

Dot segments `.`, `..`, encoded dot `%2e`, slash `%2f`, backslash (U+005C) và double decoding có thể bị gateway/backend hiểu khác nhau. **Encoding không thay thế validation, canonicalization hay authorization**; server truy cập filesystem phải chặn path traversal sau khi giải mã và kiểm tra đường dẫn thực.

## 4. Query value, dấu `+` và `URLEncoder`

Để truyền `q="C++ & Hà Nội"`:

~~~http
GET /api/search?q=C%2B%2B%20%26%20H%C3%A0%20N%E1%BB%99i HTTP/1.1
Host: api.example.test
~~~

Dấu `?` mở query, `#` mở fragment; nhiều frameworks dùng `&` và `=` để tách query parameters. **Dấu cộng `+` không đồng nghĩa space trong URI nói chung**, nhưng ở **HTML form** và nhiều query parsers, `+` được hiểu là space. Vì vậy literal plus trong query value nên thành **`%2B`**.

~~~java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
String s = URLEncoder.encode("C++ & Hà Nội", StandardCharsets.UTF_8);
// "C%2B%2B+%26+H%C3%A0+N%E1%BB%99i"
~~~

`URLEncoder` thiết kế cho **`application/x-www-form-urlencoded`**, trong đó dấu cách thành **`+`**; nó không biết ranh giới path segment. So sánh:

| Raw value | Strict URI variable | HTML form |
|---|---|---|
| `a b` | `a%20b` | `a+b` |
| `a+b` | `a%2Bb` | `a%2Bb` |
| `a/b` trong segment | `a%2Fb` | `a%2Fb` nhưng không có ngữ cảnh routing |
| `a&b` | `a%26b` | `a%26b` |

Query parameters có thể lặp: `?tag=java&tag=spring`; `?q=` (**có giá trị rỗng**) khác việc **không có `q`**. `?filter=a%3Db%26c` chứa một giá trị `a=b&c`. Hợp đồng quyết định thứ tự, duplicate names và khi nào trường có thể bỏ qua. `URI.getQuery()` percent-decode nhưng không tự áp `URLDecoder` form semantics cho `+`.

## 5. Spring `UriComponentsBuilder`: encode biến dữ liệu theo ngữ cảnh

Một mẫu an toàn cho URI có base cố định là **đặt placeholders**, sau đó gọi **`encode()` trên builder trước `buildAndExpand`**:

~~~java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.springframework.web.util.UriComponentsBuilder;

String base = "https://api.example.test";
String fileId = "ACME/2026";
String searchTerm = "C++ & Hà Nội";

URI uri = UriComponentsBuilder.fromUriString(base)
    .pathSegment("api", "v1", "files", "{fileId}")
    .queryParam("q", "{query}")
    .queryParam("tag", "{tag1}", "{tag2}")
    .encode(StandardCharsets.UTF_8)
    .buildAndExpand(Map.of(
        "fileId", fileId,
        "query", searchTerm,
        "tag1", "a+b",
        "tag2", "c#java"))
    .toUri();

System.out.println(uri.toASCIIString());
~~~

Kết quả kỳ vọng:

~~~text
https://api.example.test/api/v1/files/ACME%2F2026?q=C%2B%2B%20%26%20H%C3%A0%20N%E1%BB%99i&tag=a%2Bb&tag=c%23java
~~~

`pathSegment` thể hiện **ranh giới segment**; `queryParam` thể hiện **tên và giá trị**; placeholders `{...}` cho biết chỗ nào là **dữ liệu cần được strict-encode**. `encode(StandardCharsets.UTF_8)` trước `buildAndExpand` khiến URI variable chứa reserved characters (`/`, `+`, `&`, `#`...) được encode phù hợp thay vì giữ ý nghĩa cú pháp.

### Vì sao thứ tự `encode()` có ý nghĩa?

Không tự coi hai biểu thức sau tương đương:

~~~java
// Khuyên dùng khi giá trị biến có thể chứa reserved characters:
builder.encode().buildAndExpand(values).toUri();

// Cẩn thận: encode sau expand có thể đối xử khác với reserved chars
// trong biến đã trở thành một phần URI components:
builder.buildAndExpand(values).encode().toUri();
~~~

Ở Spring URI builder, `UriComponentsBuilder.encode()` encode template trước và **strict-encode URI variables khi expand**; còn `UriComponents.encode()` trên components đã expand có quy tắc riêng và **có thể giữ một số reserved characters**. Cách viết thứ hai dễ khiến `/` trong một value không được đối xử như dữ liệu nếu dùng sai context.

**Tránh trộn raw và pre-encoded input.** Nếu client đưa `fileId = "ACME%2F2026"` vào biến **raw**, phần `%` sẽ lại được encode thành `%25`: URI có thể trở thành `ACME%252F2026`. Đây là **double encoding** khi ý định ban đầu là truyền ID `ACME/2026`. Quy định rõ boundary: application nhận **giá trị decoded/raw**, builder encode **một lần**.

## 6. `path()`, `pathSegment()` và `URI.resolve()`

`path("/api/v1/orders/{id}")` mô tả **template path có separators chủ ý**; `pathSegment("api","v1","orders","{id}")` nêu rõ từng segment. Đừng đưa `"api/v1/orders"` thành **một segment** hoặc đưa một raw ID chứa slash vào `path(...)` như cấu trúc URI.

`java.net.URI.resolve` tuân relative-reference resolution, **không phải path join tổng quát**:

~~~java
import java.net.URI;
URI a = URI.create("https://api.example.test/api/v1");
URI b = URI.create("https://api.example.test/api/v1/");
a.resolve("orders");  // https://api.example.test/api/orders
b.resolve("orders");  // https://api.example.test/api/v1/orders
b.resolve("/orders"); // https://api.example.test/orders
~~~

Base không có dấu `/` cuối coi segment cuối là tên file bị thay; reference bắt đầu bằng `/` thay toàn bộ path. Đừng `resolve(userInput)` tùy ý: input absolute URI có thể đổi host, `../` có thể đổi path.

## 7. Java `URI`: raw/decoded và constructor

~~~java
import java.net.URI;
URI u = URI.create(
    "https://api.example.test/files/ACME%2F2026?q=C%2B%2B");
u.getRawPath();   // "/files/ACME%2F2026"
u.getPath();      // "/files/ACME/2026" (đã percent-decode)
u.getRawQuery();  // "q=C%2B%2B"
u.getQuery();     // "q=C++"
u.getFragment();  // null
~~~

**`getPath()` không giữ ranh giới các segment sau percent-decoding.** Khi ký HMAC theo request-target, cần dùng raw representation và canonicalization theo hợp đồng. `URI.create("https://api.example.test/search?q=a b")` ném `IllegalArgumentException`: nó không sửa dấu cách. Constructor nhiều thành phần có thể encode component nhưng **không biết slash trong path là dữ liệu hay separator**:

~~~java
new URI("https", "api.example.test",
    "/files/ACME/2026", "q=a+b", null);
// Slash trong ID vẫn là path separator.
~~~

Nếu đã có `URI` đáng tin và đúng encoding, truyền trực tiếp cho HTTP client. Với `UriComponentsBuilder.fromUri(existing)`, `build(true)` chỉ dùng khi components **đã encoded**; đừng trộn raw variables và encoded text rồi bỏ qua boundary.

## 8. Cấu hình Spring `DefaultUriBuilderFactory` cho HTTP client

`RestClient` và `WebClient` dùng `UriBuilderFactory` để tạo URI từ template. Khi các quy tắc encoding quan trọng, hãy cấu hình rõ:

~~~java
import java.net.URI;
import java.util.Map;
import org.springframework.web.util.DefaultUriBuilderFactory;

DefaultUriBuilderFactory factory =
    new DefaultUriBuilderFactory("https://api.example.test");
factory.setEncodingMode(
    DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

URI uri = factory.uriString("/api/v1/files/{fileId}")
    .queryParam("q", "{query}")
    .build(Map.of("fileId", "ACME/2026",
                  "query", "C++ & Hà Nội"));
~~~

`TEMPLATE_AND_VALUES` encode template và **strict-encode variable values**, phù hợp với nguyên tắc “dữ liệu không được tự thành cú pháp”. Các mode khác như `VALUES_ONLY`, `URI_COMPONENT`, `NONE` có khác biệt; không đổi mode tùy hứng trong hệ thống có nhiều clients, vì URI của cùng input có thể thay đổi.

**Version note:** Spring Framework/Spring Boot đã có thay đổi về defaults ở một số thời kỳ; với code quan trọng, **cấu hình mode tường minh và dùng test** thay vì dựa vào mặc định hay ví dụ trên mạng của phiên bản khác.

### `RestClient` (đồng bộ)

~~~java
import java.net.URI;
import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.DefaultUriBuilderFactory;

record FileView(String id, String name) {}

DefaultUriBuilderFactory factory =
    new DefaultUriBuilderFactory("https://api.example.test");
factory.setEncodingMode(
    DefaultUriBuilderFactory.EncodingMode.TEMPLATE_AND_VALUES);

RestClient client = RestClient.builder()
    .uriBuilderFactory(factory)
    .build();

FileView body = client.get()
    .uri(builder -> builder
        .pathSegment("api", "v1", "files", "{id}")
        .queryParam("q", "{q}")
        .build(Map.of("id", "ACME/2026",
                      "q", "C++ & Hà Nội")))
    .accept(MediaType.APPLICATION_JSON)
    .retrieve()
    .body(FileView.class);
~~~

`RestClient` có ở **Spring Framework 6.1+** và thường được sử dụng với Spring Boot 3.2+ (tùy version/dependencies). `retrieve()` có cơ chế xử lý lỗi HTTP; code thật cần timeouts, authentication, retry budget và mapping Problem Details theo contract. Ví dụ không gọi mạng trong bài học và không giả định server chấp nhận `%2F` trong path.

### `WebClient` (reactive)

~~~java
import reactor.core.publisher.Mono;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
    .uriBuilderFactory(factory)
    .build();

Mono<FileView> result = webClient.get()
    .uri(builder -> builder
        .path("/api/v1/files/{id}")
        .queryParam("q", "{q}")
        .build(Map.of("id", "ACME/2026",
                      "q", "C++ & Hà Nội")))
    .retrieve()
    .bodyToMono(FileView.class);
~~~

`WebClient` không tự “làm URL an toàn hơn” chỉ vì nó reactive; URI factory vẫn quyết định encoding. Nếu dùng `path(...)` với template variable, nên test URI output tương tự như `pathSegment(...)`. Tránh gọi `.block()` trên event-loop trong ứng dụng reactive; không dùng việc dựng URI để quyết định concurrency, retry hay authorization.

## 9. Java 11+ `HttpClient`: transport không thay URI semantics

~~~java
import java.net.URI;
import java.net.http.*;
import java.time.Duration;

HttpClient transport = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();

URI uri = URI.create("https://api.example.test/api/v1/files/123");
// Trong thực tế, thay URI mẫu bằng URI đã dựng/kiểm tra ở mục 5.
HttpRequest request = HttpRequest.newBuilder(uri)
    .timeout(Duration.ofSeconds(5))
    .header("Accept", "application/json")
    .GET().build();
HttpResponse<String> response = transport.send(
    request, HttpResponse.BodyHandlers.ofString());
~~~

Transport gửi URI mà ứng dụng đã tạo, **không sửa lại segment/query semantics**. Timeouts, TLS, auth, redirects và status/error mapping là chính sách độc lập. `Redirect.NEVER` giúp tránh vô tình forward credentials hoặc đổi method/host trên redirect không tin cậy.

## 10. Double encoding, double decoding và normalization

| Giá trị input đưa vào strict encoder | Kết quả segment | Giải thích |
|---|---|---|
| Raw `"ACME/2026"` | `ACME%2F2026` | Slash là dữ liệu |
| Already-encoded `"ACME%2F2026"` | `ACME%252F2026` | **Sai** nếu intent là `ACME/2026` |
| Raw literal `"ACME%2F2026"` | `ACME%252F2026` | **Đúng** nếu ID thực chứa ký tự `%` |

**Double decoding nguy hiểm:** `%252F` sau lần decode đầu thành `%2F`, sau lần hai thành `/`. Nếu gateway authorize theo lần decode thứ nhất nhưng backend route theo lần thứ hai, chúng có thể nhận diện **khác resource**.

Không sửa bằng `String.replace(" ", "%20")`, không dùng `URLDecoder` form semantics cho URI path và không coi `URI.normalize()` là kiểm tra quyền/SSRF. Nếu ký HMAC, thống nhất raw URI canonicalization và số lần decode. **Chỉ encode một lần tại boundary có cấu trúc đã được xác định.**

## 11. Bảo mật khi xây dựng URI ở Java client

**Encoding đúng không đồng nghĩa URI an toàn.** Tách hai loại input:

1. **Base URI của dịch vụ:** do cấu hình đáng tin cậy, chẳng hạn `https://api.partner.example.test`.
2. **URI variables/query values:** dữ liệu ứng dụng hoặc người dùng, chỉ được đi vào vị trí đã thiết kế.

Không cho client gửi toàn bộ `url` rồi chuyển thẳng cho `RestClient.get().uri(url)` trong một service chỉ có nhiệm vụ gọi một backend. Đó là **SSRF risk**: host nội bộ, cloud metadata endpoint, DNS rebinding hoặc open redirects có thể làm request thoát sang đích không mong muốn.

### Các biện pháp phòng vệ

- **Scheme/host allowlist:** HTTPS, host/port được phép; từ chối userinfo, fragment và scheme lạ; không lấy `Host` từ client request làm địa chỉ gọi ra.
- **Network egress policy:** kiểm soát truy cập tới IP private/link-local/metadata ở tầng mạng/proxy; allowlist tên host đơn thuần chưa chống DNS rebinding.
- **Redirect policy:** tắt hoặc tự kiểm tra host/scheme cho mỗi redirect; không forward bearer/API key sang authority khác.
- **Path ID whitelist:** UUID/ULID/base64url, độ dài, ký tự hợp lệ; không trộn raw file path vào URI template.
- **Query policy:** giới hạn số tham số, độ dài, sort/filter fields, page size; không để payload quá dài gây request 414 hoặc log phình to.
- **Credentials/PII:** không nhét token, mật khẩu, địa chỉ email hoặc dữ liệu nhạy cảm vào query nếu có thể tránh; URL có thể nằm trong logs, browser history, analytics và cache keys.
- **Observability:** log route template và error category; nếu cần log URI thật, **redact** thông tin nhạy cảm và hạn chế quyền truy cập.
- **TLS/timeouts:** verify certificate, đặt connection/read deadlines, quản lý auth; percent-encoding không giải quyết những việc này.

Ví dụ kiểm tra host là **phòng tuyến phụ** sau khi build, không thay egress policy:

~~~java
import java.net.URI;

static URI requireTrustedApi(URI uri) {
    if (!"https".equalsIgnoreCase(uri.getScheme())
            || !"api.example.test".equalsIgnoreCase(uri.getHost())
            || uri.getPort() != -1
            || uri.getRawUserInfo() != null
            || uri.getRawFragment() != null) {
        throw new IllegalArgumentException("Untrusted API target");
    }
    return uri;
}
~~~

Trong ví dụ trên, `getPort() == -1` chỉ chấp nhận **không chỉ định port tường minh**; nếu ứng dụng cần HTTPS ở port 443 hoặc cổng khác, phải công bố và allowlist cụ thể. Tránh logic “host chứa chuỗi `example.test`” vì `api.example.test.evil.test` sẽ vượt qua kiểm tra chuỗi ngây thơ.

## 12. HTTP semantics, cache, phân trang và idempotency

Việc encode URI ảnh hưởng trực tiếp tới resource/URI và hợp đồng REST:

| Chủ đề | Hệ quả khi URI dựng sai |
|---|---|
| **GET collection** | `?status=PAID&sort=...` có thể bị tách/nhầm, trả dữ liệu ngoài filter |
| **Pagination** | Cursor chứa `+`, `/`, `=` bị giải mã khác; trang sau sai hoặc token mất hiệu lực |
| **Caching/ETag** | Cache key theo URI khác nhau; encoding/canonicalization không nhất quán gây miss hoặc cache poisoning nếu các tầng xem cùng một URI khác nhau |
| **HMAC/request signing** | Hai bên ký raw request-target khác bytes (`%20` so với `+`, `%2F` so với `/`) nên chữ ký không khớp |
| **POST/idempotency** | URI/tenant/resource sai có thể đưa side effect vào đối tượng khác; URI encoding không tự đảm bảo idempotency |
| **OpenAPI contract** | Client gửi array query khác `style/explode` hoặc path variable bị chia segment |

### Cursor và query parameter lặp

Nếu `after` là **opaque cursor**, xây:

~~~java
URI next = UriComponentsBuilder
    .fromUriString("https://api.example.test")
    .path("/api/orders")
    .queryParam("limit", "{limit}")
    .queryParam("after", "{cursor}")
    .encode(StandardCharsets.UTF_8)
    .buildAndExpand(Map.of(
        "limit", 20,
        "cursor", "eyJ2IjoxLC4rLz0="))
    .toUri();
~~~

Cursor `eyJ2IjoxLC4rLz0=` chứa ký tự có thể ảnh hưởng query parsing; strict encoding biểu diễn dữ liệu an toàn. **Không tự `URLDecoder.decode(cursor)` hai lần**. Server phải xác minh signature/scope/expiry và quyền resource; base64url chỉ làm token dễ đặt trong URI, không phải security.

Một **query array** có thể thể hiện dạng:

~~~text
?tag=java&tag=spring
~~~

Trong OpenAPI 3.1, `style: form` và `explode: true` cho array query parameter thường biểu diễn dạng nhiều cặp cùng tên. Nếu API chọn `?tag=java,spring` thì contract serialization phải khác. **Mỗi bên phải khớp thực tế**, không đoán từ tên parameter.

### Hạn chế URL dài

Không có giới hạn độ dài URI chung áp dụng đồng nhất cho mọi HTTP gateway, browser, server. Request rất dài có thể gặp **414 URI Too Long**, hoặc bị giới hạn trước đó bởi proxy. Đối với truy vấn lớn phức tạp, nên cân nhắc **POST một resource tìm kiếm/job** theo hợp đồng (nếu có ý nghĩa và không lạm dụng GET body) hoặc rút gọn filter, thay vì cố nhồi hàng nghìn điều kiện vào query.

## 13. Kiểm thử URI trước khi gọi mạng

URI builder là **logic thuần** nên có thể kiểm thử nhanh mà không cần máy chủ chạy. Ví dụ **JUnit 5**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.web.util.UriComponentsBuilder;

class UriEncodingTest {
    @Test
    void pathAndQueryVariablesAreEncodedByContext() {
        URI uri = UriComponentsBuilder
            .fromUriString("https://api.example.test")
            .pathSegment("api", "v1", "files", "{id}")
            .queryParam("q", "{q}")
            .queryParam("tag", "{t1}", "{t2}")
            .encode(StandardCharsets.UTF_8)
            .buildAndExpand(Map.of(
                "id", "ACME/2026",
                "q", "C++ & Hà Nội",
                "t1", "a+b",
                "t2", "c#java"))
            .toUri();

        assertEquals("/api/v1/files/ACME%2F2026", uri.getRawPath());
        assertEquals(
            "q=C%2B%2B%20%26%20H%C3%A0%20N%E1%BB%99i"
            + "&tag=a%2Bb&tag=c%23java",
            uri.getRawQuery());
        assertNull(uri.getRawFragment());
        assertEquals("https", uri.getScheme());
        assertEquals("api.example.test", uri.getHost());
    }

    @Test
    void rawPercentIsEncodedExactlyOnceAsData() {
        URI uri = UriComponentsBuilder
            .fromUriString("https://api.example.test")
            .pathSegment("files", "{id}")
            .encode()
            .buildAndExpand(Map.of("id", "ACME%2F2026"))
            .toUri();

        // Input là raw literal "%" nên nhận "%25".
        assertEquals("/files/ACME%252F2026", uri.getRawPath());
    }

    @Test
    void urlEncoderUsesFormSemanticsNotPathSemantics() {
        assertEquals("a+b", java.net.URLEncoder.encode(
            "a b", StandardCharsets.UTF_8));
        assertEquals("a%2Bb", java.net.URLEncoder.encode(
            "a+b", StandardCharsets.UTF_8));
    }
}
~~~

Test trên kiểm chứng **URI serialization**, chưa kiểm chứng server/proxy chấp nhận encoded slash hoặc query parameters lặp. Cần thêm **integration test qua đúng proxy/gateway** để xác nhận route và parser như dự kiến.

### Ma trận test boundary

| Input/tình huống | Kỳ vọng |
|---|---|
| ID `a/b` trong **một segment** | `a%2Fb` hoặc bị policy từ chối ID này trước khi gọi |
| ID chứa literal `%2F` | `%252F`; không tự decode |
| Query `C++ & Hà Nội` | `C%2B%2B%20%26%20H%C3%A0%20N%E1%BB%99i` |
| Query `c#java` | `c%23java`, fragment vẫn null |
| Query `a=b&c` | `a%3Db%26c`, không thành hai params |
| Query có `a b` | URI variable ra `a%20b` theo encoding policy |
| `tag` lặp | Backend nhận đúng số lượng và thứ tự values theo hợp đồng |
| Missing vs empty query | Hai trường hợp được biểu diễn/phân biệt đúng |
| Unicode nhiều byte/emoji | UTF-8 percent-encoded, round-trip đúng |
| `../`, `%2e%2e`, `%2f`, `%5c` | Client ID policy và gateway traversal checks không bị qua mặt |
| User cho full absolute URL | Host/scheme/port allowlist chặn SSRF |
| HTTP redirect sang host khác | Không forward bearer token |
| Query quá dài/cursor sai | Bị từ chối theo policy, không gửi request không giới hạn |
| V1/v2 path và chữ ký HMAC | Canonical URI/signature không bị thay khi nâng client |

### Test transport với Spring

Với `RestClient`, có thể dùng **`MockRestServiceServer`** của Spring Test để assert URL request thực sự được gửi, method và headers, mà không gọi mạng. Với `WebClient`, dùng mock `ExchangeFunction` hoặc mock HTTP server thích hợp. Mọi test cần kiểm tra **URI cuối cùng của HTTP client**, không chỉ kết quả của helper builder trong một đường code khác.

Tách kiểm thử:

- **Unit:** builder/encoder theo RFC, ký tự boundary.
- **Contract:** URI theo OpenAPI `style/explode`, query arrays, path/template và lỗi status.
- **Integration:** gateway thực, encoded slash policies, authentication, redirects, cache, 400/414/429/503.
- **Security:** DNS/host restrictions, forged redirect, ID validation, không log secrets, encoded traversal/double decode.

## 14. OpenAPI 3.1: công bố serialization cho Java client

Ví dụ mô tả resource có ID path và query có thể lặp:

~~~yaml
openapi: 3.1.0
info: {title: Files API, version: 1.0.0}
servers:
  - url: https://api.example.test
paths:
  /api/v1/files/{fileId}:
    get:
      summary: Tra cứu tài liệu theo ID và bộ lọc
      security:
        - BearerAuth: []
      parameters:
        - name: fileId
          in: path
          required: true
          description: >
            Opaque ID; khuyến nghị chỉ dùng ký tự unreserved,
            không chấp nhận raw slash trên production gateway.
          schema: {type: string, minLength: 1}
        - name: q
          in: query
          required: false
          style: form
          explode: true
          schema: {type: string}
        - name: tag
          in: query
          required: false
          style: form
          explode: true
          description: Có thể lặp tag=java&tag=spring
          schema:
            type: array
            items: {type: string}
      responses:
        '200':
          description: Tài liệu phù hợp
          content:
            application/json:
              schema:
                type: object
                required: [id, name]
                properties:
                  id: {type: string}
                  name: {type: string}
        '400': {description: URI/query không hợp lệ}
        '401': {description: Cần xác thực}
        '403': {description: Không có quyền}
        '404': {description: Không tìm thấy resource}
        '414': {description: Request target quá dài}
components:
  securitySchemes:
    BearerAuth: {type: http, scheme: bearer, bearerFormat: JWT}
~~~

**Giới hạn hợp đồng:** OpenAPI mô tả parameter serialization và schema, nhưng **không tự bảo đảm URI builder hoặc gateway xử lý encoded slash nhất quán**. Nếu ID thực tế có thể chứa slash, phải khảo sát đường proxy/Servlet/Firewall; tốt hơn là chọn định dạng ID URL-safe thay vì để client tự đoán.

## 15. Bài tập: client tìm kiếm đơn hàng và tải tệp

Một dịch vụ Java gọi:

~~~text
GET https://orders.example.test/api/v2/orders/{orderId}?q={q}&tag={tag}&tag={tag}
~~~

Cho:

- `orderId = "VN/2026/009"` (một mã nghiệp vụ, không phải ba segment).
- `q = "đơn hàng C++ & Java"`.
- `tag1 = "đã trả"`, `tag2 = "a=b#c"`.
- Có một endpoint `POST /api/v2/orders/{orderId}/retry` yêu cầu Bearer authentication.
- Trên đường đi có gateway mặc định chặn encoded slash; một đối tác đề xuất thay bằng `URLEncoder.encode(orderId)` rồi nối chuỗi URL.

**Yêu cầu:**

1. Cho biết vì sao nối chuỗi URL raw sai với từng giá trị.
2. Dùng Spring URI builder để tạo URI có hai `tag`; giải thích encode một lần.
3. Nếu gateway chặn `%2F`, đề xuất thay đổi contract thay vì bypass firewall.
4. Nêu khác biệt giữa `URLEncoder` và strict encoding của query/path.
5. Thiết kế ít nhất năm tests và biện pháp bảo vệ token khi gặp redirect.
6. Với POST retry, vì sao encode URI đúng vẫn chưa đủ để đảm bảo idempotency?

### Gợi ý lời giải

**1.** `/` trong ID bị tách segment; dấu cách/Unicode cần UTF-8; `+` phải `%2B`; `&` trong q thành separator nếu nối thẳng; `#` trong tag thành fragment; `=` trong tag có thể bị parser hiểu sai.

**2.** Ví dụ:

~~~java
URI uri = UriComponentsBuilder
    .fromUriString("https://orders.example.test")
    .pathSegment("api", "v2", "orders", "{id}")
    .queryParam("q", "{q}")
    .queryParam("tag", "{t1}", "{t2}")
    .encode(StandardCharsets.UTF_8)
    .buildAndExpand(Map.of(
        "id", "VN/2026/009",
        "q", "đơn hàng C++ & Java",
        "t1", "đã trả",
        "t2", "a=b#c"))
    .toUri();
~~~

**3.** Không nới firewall chỉ để chấp nhận encoded slash nếu không có thiết kế bảo mật. Dùng **opaque ID URL-safe** để thay đại diện cho mã nghiệp vụ, hoặc tìm bằng query parameter `businessCode` đã encode đúng, có authorization và URI/hợp đồng riêng.

**4.** `URLEncoder` dùng form encoding (`space → +`), không biết đây là một path segment hay một query value. Template builder strict-encode reserved chars của **variable values** dựa trên vị trí và build đúng URI structure.

**5.** Test raw ID `/`, query `&/=# +`, Unicode, repeated tag, raw percent/double encoding, gateway encoded slash, host allowlist và redirect. Không auto-follow sang host khác cùng Bearer token; kiểm tra authority và egress theo policy.

**6.** POST retry có side effect; phải sử dụng **Idempotency-Key** theo scope/contract, kiểm tra kết quả của attempt trước, có retry budget và dedupe ở server. URI encoding không ngăn hai POST có cùng intent tạo hai tác động.

## 16. Checklist client Java production

- [ ] Dùng base URL đáng tin, không nhận absolute URL/host tùy ý từ request.
- [ ] Định nghĩa URI template bằng `pathSegment` hoặc `path` có chủ ý; mọi ID/query value đi qua URI variables.
- [ ] Strict-encode biến **trước expand** (`UriComponentsBuilder.encode().buildAndExpand` hoặc `TEMPLATE_AND_VALUES`).
- [ ] Không dùng `URLEncoder` cho path hoặc coi `+` luôn là dấu cách trong mọi URI component.
- [ ] Không chuyển giá trị already-encoded qua encoder raw lần hai; biết rõ boundary và `getRawPath/getRawQuery`.
- [ ] Query arrays, empty/missing params và cursor serialization đúng OpenAPI.
- [ ] Không giả định encoded slash được mọi proxy/Servlet/Firewall chấp nhận; ưu tiên opaque ID URL-safe.
- [ ] Path traversal/encoded dot/backslash được kiểm soát bằng validation và authorization, không chỉ percent encoding.
- [ ] Bảo vệ credentials, redirects, SSRF/egress, query length và logging dữ liệu nhạy cảm.
- [ ] Kiểm soát method/status/retry, idempotency, paging, cache và signing theo URI thực sự gửi.
- [ ] Test unit URI builder, HTTP client request, OpenAPI serialization và gateway integration với dữ liệu Unicode/reserved chars.

**Kết luận:** URI đúng không phải là “thay dấu cách bằng `%20`”. Nó là kết quả của **một cây cấu trúc đúng** — scheme, authority, path segments, query name/value — rồi **strict-encode dữ liệu trong đúng vị trí**. Với Java/Spring, cách làm bền vững là URI templates + variables, cấu hình encoding rõ ràng, không encode hai lần và kiểm thử qua cả client lẫn gateway. Đây là nền tảng để các REST APIs xử lý đúng resource, filter, bảo mật, cache và retry.

### Tài liệu nền

- **RFC 3986 — URI Generic Syntax:** components, reserved/unreserved, percent-encoding và resolution.
- **RFC 3987 — Internationalized Resource Identifiers:** Unicode/IRI và biểu diễn URI khi cần.
- **RFC 9110 — HTTP Semantics:** request target, methods, 414, redirects và HTTP caching liên quan.
- **RFC 8288 — Web Linking; OpenAPI 3.1:** query arrays, path parameters, serialization.
- **Java SE API:** `java.net.URI`, `URLEncoder`, `URLDecoder`, `java.net.http.HttpClient`.
- **Spring Framework Reference:** `UriComponentsBuilder`, `DefaultUriBuilderFactory`, `RestClient`, `WebClient` và HTTP client testing.
