# Xử lý đường dẫn mã hóa, path traversal và chuẩn hóa không nhất quán trong Spring Cloud Gateway

Trong kiến trúc microservices, request có thể đi qua **CDN/WAF → ingress → Spring Security → Spring Cloud Gateway route predicate/filter chain → HTTP client → backend**. Các tầng này có thể phân tích, giải mã và chuẩn hóa URL theo quy tắc khác nhau. Một tầng nhìn `%2F` như dữ liệu thuộc path segment, tầng khác biến nó thành dấu `/` phân cách; `%2e%2e` có thể trở thành `..`; dấu chấm phẩy, slash kép, backslash hoặc Unicode cũng có thể đổi nghĩa trên đường đi.

Bài thuộc chương **Gia cố bảo mật** của module **SPRING_CLOUD_GATEWAY**, tập trung vào **xử lý đường dẫn mã hóa, path traversal và chuẩn hóa không nhất quán**. Chủ đề này liên quan trực tiếp tới route predicate, filter chain, biến đổi path/header, xác thực, rate limiting, circuit breaker, retry, TLS, service discovery và observability: nếu các thành phần dùng **khác representation của cùng URL**, một request được xem là public ở Gateway có thể trỏ tới resource đặc quyền trên backend.

**Mục tiêu:**

1. Phân biệt **request-target, raw path, decoded path, normalized path, URI template variables** và effective downstream path.
2. Nhận diện encoded slash, encoded dot segments, double encoding, backslash, semicolon, duplicate slash, Unicode normalization và các giới hạn parser.
3. Hiểu vì sao **Path predicate match không đồng nghĩa authorization**.
4. Thiết kế **strict grammar và reject ambiguous inputs**, tránh decode/normalize nhiều lần.
5. Kiểm thử ở **ingress, Gateway và backend**, không chỉ một filter test.
6. Vận dụng WebFlux filter/Java URI builder, phân biệt Servlet Web MVC/ProxyExchange và xây checklist triển khai.

> **Phạm vi:** Ví dụ code tập trung vào **Gateway Server WebFlux**. Server Web MVC dùng Servlet/WebMvc.fn, ProxyExchange dùng controller-style proxy. Cách xử lý encoded slash/semicolon/invalid UTF-8 phụ thuộc HTTP server, framework, ingress và phiên bản. Không gán một mặc định cố định cho mọi runtime. Các URL lạ là **test cases phòng thủ trong môi trường được cho phép**.

## 1. Rủi ro cốt lõi: kiểm đường dẫn A nhưng thực thi đường dẫn B

Giả sử Gateway có `/api/public/**` và `/api/admin/**`. Public route cho anonymous traffic; admin route đòi `SCOPE_admin`. Backend còn có endpoint nội bộ không được public.

~~~mermaid
flowchart LR
    C["Client request-target"] --> W["CDN / WAF"]
    W --> I["Ingress / proxy"]
    I --> S["Spring Security"]
    S --> R["Gateway predicates"]
    R --> F["StripPrefix / RewritePath"]
    F --> B["Backend router + authorization"]
    B --> D["Protected resource"]
~~~

Một mismatch cần phòng chống:

1. Ingress cho phép request theo **raw path prefix**.
2. Một hop phía sau decode `%2e%2e` thành `..` rồi xử lý dot-segments.
3. Security matcher hoặc Gateway filter chọn route theo representation khác.
4. Backend cuối cùng thấy path thuộc namespace đặc quyền.
5. Nếu backend bỏ object-level authorization vì tin Gateway đã kiểm, dữ liệu có thể bị lộ.

**Đây là threat model, không phải khẳng định mọi product tự biến đổi như trên.** Cần test chính stack/version thật.

**Bất biến bảo mật:** Không được để normalize, decode, rewrite hoặc proxy làm caller có quyền với **resource cuối cùng** mà họ không được phép truy cập.

## 2. Cấu trúc URI: path khác query và fragment

~~~text
https://api.example.test/api/items/A%2FB?lang=vi&sort=asc#section
|_____scheme______| |__authority__| |_____path_____| |____query____| fragment
~~~

| Thành phần | Ví dụ | Điểm cần quan tâm |
|---|---|---|
| Scheme | `https` | TLS/forwarded scheme |
| Authority/Host | `api.example.test` | Virtual host, SNI, proxy trust |
| **Raw path** | `/api/items/A%2FB` | Percent-encoded representation |
| Segments | `api`, `items`, `A%2FB` trước khi đổi cấu trúc | Slash là dấu phân cách |
| Decoded segment | `A/B` nếu decode `%2F` | Có thể chứa reserved character |
| Normalized path | Dạng sau áp quy tắc `.`/`..` và separators | Có thể trỏ resource khác |
| Query | `lang=vi&sort=asc` | Không là path, có thể chứa PII |
| Fragment | `#section` | Thường được xử lý ở client, không gửi trong HTTP request-target |

Trong HTTP thông thường, fragment không phải thứ client gửi tới origin server; **đừng dùng fragment làm authorization rule**.

### Raw path trong Spring không phải raw bytes từ client

Trong WebFlux, `exchange.getRequest().getURI().getRawPath()` trả raw path của **URI object mà Java đã nhận**. Nó **không chứng minh** request line từ client có cùng bytes: CDN, ingress hoặc Netty parser có thể đã reject, decode, normalize trước đó.

Nếu cần so các hops, dùng edge/Gateway/backend telemetry có giới hạn quyền và dữ liệu đã được che nhạy cảm.

## 3. Percent-encoding và reserved characters

Percent-encoding biểu diễn một octet qua `%HH`. Những cases quan trọng:

| Input | Sau decode tương ứng | Rủi ro |
|---|---|---|
| `%2F` hoặc `%2f` | `/` | Thêm path separator |
| `%5C` | Backslash | Một số backend/filesystem coi là separator |
| `%2E` | `.` | Tạo dot segments |
| `%3B` | `;` | Matrix/path params |
| `%3F` | `?` | Nhầm ranh giới path/query nếu decode sai |
| `%23` | `#` | Nhầm fragment delimiter |
| `%25` | `%` | Double encoding |
| `%00` | NUL | Parser/logging/native handling mismatch |
| `%20` | Space | URI encoding/normalization khác |
| `%2B` | `+` | Dễ lẫn form encoding |

Theo RFC 3986, **unreserved** gồm chữ/số, `-`, `.`, `_`, `~`; nhiều ký tự như `/`, `?`, `#`, `;`, `:`, `@` là **reserved** có thể đổi cấu trúc URL khi bị decode sớm.

`%2f` và `%2F` biểu diễn cùng byte; không viết filter chỉ cấm một dạng chữ hoa. Invalid sequences như `%ZZ` và incomplete `%2` phải có policy reject ở điểm nhận phù hợp.

### Không dùng URLDecoder như một path sanitizer

`java.net.URLDecoder` dành cho `application/x-www-form-urlencoded`, có semantics `+` thành space. Không dùng để giải mã toàn raw URI path rồi xác nhận an toàn:

~~~java
// PHẢN VÍ DỤ: tự decode raw path rồi coi là đã sạch.
String decoded = java.net.URLDecoder.decode(
    clientSuppliedPath,
    java.nio.charset.StandardCharsets.UTF_8);
~~~

Dùng validation theo **domain identifier**, URI/path segment builder phù hợp và authorize resource cuối cùng.

## 4. Double encoding và nguy cơ giải mã lặp

~~~text
Raw:           /api/items/A%252FB
Decode lần 1:  /api/items/A%2FB
Decode lần 2:  /api/items/A/B

Raw:           /api/public/%252e%252e/admin
Decode lần 1:  /api/public/%2e%2e/admin
Decode lần 2:  /api/public/../admin
~~~

Rủi ro thường nảy sinh ở ba tình huống:

- WAF chỉ decode một lần; backend nhận path rồi tự decode thêm.
- Framework đã decode `@PathVariable`, nhưng code gọi `URLDecoder` lần hai.
- Filter tạo outbound URI bằng raw/decoded string, HTTP client hoặc proxy sau đó re-encode/normalize.

**Không decode cho đến khi không còn dấu %**. Cách đó có thể đổi nghĩa path qua mỗi lần lặp. Với API không cần percent-encoded paths, reject ngay `%` là policy dễ kiểm chứng hơn; với API cần encoding, phải định nghĩa rõ **một lần decode và canonical representation**.

## 5. Dot-segments, traversal và URI.normalize()

Các variants cần kiểm ở perimeter và backend:

~~~text
/api/public/../admin/config
/api/public/%2e%2e/admin/config
/api/public/.%2e/admin/config
/api/public/%2e./admin/config
/api/public/%252e%252e/admin/config
/api/public/..%2fadmin/config
/api/public/%2e%2e%2fadmin/config
~~~

Một server có thể reject trước khi Gateway route match; một tầng khác giữ nguyên rồi chuyển tiếp; backend có thể decode tiếp. **Không suy hành vi cụ thể mà không thử đúng version.**

`java.net.URI.normalize()` không phải giải pháp bảo mật toàn năng: nó không xác thực quyền resource, không kiểm symlink/filesystem containment, không tự giải mã các dạng encoded dot theo mọi parser, và không biết path đã bị Gateway `RewritePath` chuyển thành gì.

**Normalize khác sanitize.** Với path grammar không cho phép dot segments, hãy **reject** thay vì cố biến mọi chuỗi thành một URL khác.

## 6. Encoded slash và backslash: một ID hay hai segments?

`/api/items/A%2FB` có thể được hiểu là ID `A/B` nằm trong một segment, hoặc thành hai segments `A` và `B`. `%5C` có thể mang semantics separator ở một số backend/filesystem, nhất là khi ứng dụng tương tác với đường dẫn Windows.

| Loại ID | Hợp đồng nên dùng |
|---|---|
| Số nguyên | `[0-9]+` với giới hạn độ dài |
| UUID | Parse/validate UUID canonical |
| Slug ASCII | `[A-Za-z0-9_-]+` |
| Object key chứa slash | Opaque ID hoặc body/query theo contract; test encoding |
| Client-supplied file path | Tránh; map server-side ID → file |
| Unicode slug | UTF-8 hợp lệ và normalization rõ |

**Đừng tự thay backslash thành slash để sửa input**, vì cách đó có thể làm path chuyển sang resource khác.

## 7. Double slash, trailing slash và chữ hoa/chữ thường

~~~text
/api/admin/config
/api//admin/config
//api/admin/config
/api/admin/config/
/API/admin/config
/api/admin//config
/api/admin/.//config
~~~

Những đường dẫn trên **không tự tương đương**. Một ingress có thể gộp double slash; Security/route matcher có thể xử lý trailing slash khác backend; resource IDs có thể case-sensitive.

- Không cần duplicate slash → reject nó ở điểm tin cậy thích hợp.
- Nếu trailing slash hợp lệ, test **cùng policy authorization** cho cả hai dạng.
- Không tự lowercase toàn path.
- Không thêm redirects 301/308 tùy tiện cho requests có body/side effects.
- Xác minh cả **path trước rewrite** lẫn **effective backend path**.

## 8. Semicolon, matrix parameters và encoded semicolon

~~~text
/api/items/42;color=red
/api/items/42;role=admin
/api/items/42%3Brole%3Dadmin
/api/items/42;v=1/details
~~~

Dấu chấm phẩy có thể được dùng để biểu diễn **matrix/path parameters**. Một framework có thể loại thông tin `;...` khi match path, framework khác lại giữ nó trong biến resource ID.

Nếu không hỗ trợ matrix variables, chính sách dễ kiểm soát là reject **literal `;` và encoded `%3B`**. Nếu cần hỗ trợ, phải kiểm đủ **ingress parser → Gateway route/security matcher → backend router → authorization**. Không dùng một rule chỉ cấm chuỗi `";role=admin"` và cho rằng đã ngăn toàn bộ bypass.

## 9. Unicode normalization, UTF-8 và ký tự nhìn giống nhau

- NFC/NFD: chữ có dấu có thể có nhiều sequences code points.
- Compatibility forms như fullwidth characters.
- Homoglyphs từ bảng chữ cái khác nhau.
- Unicode case folding khác ASCII lowercasing.
- Invalid/overlong UTF-8 có thể bị reject hoặc thay thế khác nhau bởi parsers.

Nếu business **chỉ cần UUID/số**, dùng ASCII grammar, không mở encoded Unicode path. Nếu thực sự cần Unicode slugs:

1. Định nghĩa UTF-8 hợp lệ duy nhất.
2. Chọn normalization form theo domain (thường cân nhắc NFC).
3. Chuẩn hóa tại **một điểm xác định**.
4. Cùng canonical ID được sử dụng cho storage lookup và authorization.
5. Test NFC/NFD, Unicode percent-encoding và malformed bytes.
6. Không áp NFKC nếu chưa đánh giá collisions và business semantics.

Unicode normalization **không thay thế resource-level authorization**.

## 10. Forwarded headers, Host và protocol translation

Các nguồn khác path có thể làm thay đổi effective routing:

| Giá trị | Rủi ro |
|---|---|
| `Host` / HTTP/2 `:authority` | Virtual host selection/SNI |
| `Forwarded`, `X-Forwarded-Proto` | Scheme/host giả mạo |
| `X-Forwarded-Prefix` | Public base path và internal path khác |
| `X-Original-URL`, `X-Rewrite-URL` | Extension headers ảnh hưởng path trong vài proxies |
| `Location` redirect | Client resolve URI mới |
| HTTP/2 → HTTP/1.1 | `:path`/request-target translation |

Chỉ tin forwarded headers do **trusted ingress/proxy** tạo và overwrite; không để client tự chọn backend host/tenant qua những headers này.

HTTP request smuggling liên quan framing HTTP (Content-Length/Transfer-Encoding) và là một lớp vấn đề khác. Nó có thể kết hợp path confusion nhưng không được giải quyết chỉ bằng path regex.

## 11. Biểu diễn path trong Gateway Server WebFlux

Spring Cloud Gateway Server WebFlux có các biểu diễn path ở nhiều thời điểm:

- `exchange.getRequest().getURI().getRawPath()`: raw path của URI object hiện tại.
- `exchange.getRequest().getPath()`: `RequestPath` do Spring WebFlux cung cấp, có phân tách segments.
- Kết quả `Path` route predicate và URI template variables: dữ liệu từ route matching.
- `StripPrefix`, `RewritePath`, `SetPath`, `PrefixPath`: biến đổi path trước downstream routing.
- Target URI/exchange attributes trong Gateway routing: giá trị có thể thay đổi trong filter lifecycle.

**Không coi các giá trị này là một string giống nhau**. Security kiểm path ở một giai đoạn; Gateway rewrite ở giai đoạn khác; backend tiếp tục phân tích URI thực được gửi đến.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant I as Ingress
    participant S as Security WebFilter
    participant R as Gateway Path predicate
    participant F as Path filters
    participant B as Backend authorization
    C->>I: Raw request-target
    I->>S: Parsed / perhaps normalized path
    S->>S: Authentication & authorization
    S->>R: Route match
    R->>F: StripPrefix / RewritePath / SetPath
    F->>B: Effective downstream path
    B->>B: Final resource authorization
    Note over S,B: Quyền phải được giữ nguyên qua mọi biến đổi path
~~~

### PathPattern và segment boundaries

Spring Framework cung cấp các path parsing/matching abstractions giúp biểu diễn segments theo cấu trúc. Tuy nhiên, **không vì thế mà mặc định Netty, ingress, Servlet và backend router sẽ luôn diễn giải encoded slash như nhau**. Muốn đảm bảo, hãy test end-to-end theo phiên bản và cấu hình thực tế.

## 12. StripPrefix và RewritePath có thể đổi không gian tên bảo mật

Ví dụ Gateway Server WebFlux ở những dòng cấu hình namespace mới:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-public
              uri: http://catalog.internal:8080
              predicates:
                - Path=/public/catalog/**
              filters:
                - StripPrefix=1
~~~

Với `GET /public/catalog/items/42`, `StripPrefix=1` tạo outbound path `/catalog/items/42` theo contract bình thường.

**Vấn đề:** Nếu backend có `/catalog/admin/**` mà không có object-level authorization, một public route rộng có thể vô tình expose nó. Nếu kèm inconsistent normalization, rủi ro lớn hơn.

| Thiết lập | Rủi ro |
|---|---|
| `Path=/**` | Catch-all có thể public nhiều endpoints backend |
| `StripPrefix` trên route rộng | Path mới không còn prefix đã được Security kiểm |
| `RewritePath` regex capture rộng | Capture chứa encoded delimiter/dot |
| `SetPath` dùng template vars | User input có thể thành outbound path |
| `PrefixPath` cùng ingress rewrite | Double-prefix, security matcher mismatch |
| Dynamic routes không kiểm duyệt | Tạo URI/path vào backend nội bộ |

Hãy lưu **bảng expected incoming path → matched route → outgoing path → backend operation** cho các routes nhạy cảm, kể cả encoded variants.

## 13. Xây URI outbound an toàn bằng path segments

Phản ví dụ:

~~~java
// Không nên: raw slug có thể chứa "/", "..", "%2F" hoặc "?..."
String target = "https://catalog.internal/items/" + clientSuppliedSlug;
~~~

Với slug API chỉ cho ASCII chữ/số, underscore và hyphen:

~~~java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;

static URI itemUri(String slug) {
    if (slug == null || !slug.matches("[A-Za-z0-9_-]{1,64}")) {
        throw new IllegalArgumentException("invalid slug");
    }

    return UriComponentsBuilder
        .fromUriString("https://catalog.internal")
        .pathSegment("items", slug)
        .build()
        .encode()
        .toUri();
}
~~~

URI builder giúp phân tách **path segments** thay vì nối raw strings, còn validation đảm bảo slug hợp domain. **Không tự xem URI builder là authorization**; backend vẫn phải verify resource owner/tenant, và phải giữ origin allowlist.

Với UUID, số hoặc Unicode IDs, hãy định nghĩa grammar tương ứng. Với raw URL nhận từ client, không dùng `proxy.uri(rawUrl)` hoặc đặt scheme/host từ input tự do: ngoài path bypass còn có nguy cơ SSRF.

## 14. Chính sách “reject ambiguous” tại trust boundary

Với API paths đơn giản, **chấp nhận một ngôn ngữ path nhỏ, rõ ràng** thường dễ đánh giá hơn việc cố “sửa” path thành canonical form.

Có thể reject theo hợp đồng:

- `%` trong raw path nếu API không dùng encoded paths;
- `.`/`..` hoặc các variants encoded;
- `//`, raw backslash, `%2F` và `%5C`;
- `;` và `%3B` nếu không hỗ trợ matrix variables;
- Invalid percent escapes, invalid UTF-8/NUL;
- Path dài vượt giới hạn, quá nhiều segments;
- Unicode IDs nếu domain chỉ chấp nhận ASCII.

**Không áp toàn cục policy này cho một API đang hỗ trợ percent-encoded Unicode hoặc file names có dots** mà không có migration plan. Nếu business cần các ký tự ấy, xây chính sách parse/decode đúng một lần và so canonical values ở mọi ranh giới.

**Reject khác normalize:** Với representation mơ hồ, 400 Bad Request thường dễ chứng minh bảo mật hơn silent rewrite sang path khác.

## 15. WebFlux WebFilter minh họa strict raw-path grammar

Giả sử một Gateway lab chỉ chấp nhận paths `/`, `/api/orders/42`, `/api/items/item_01`, `/actuator/health`. Mọi segment chỉ gồm ASCII letters/digits/underscore/hyphen, không có encoded characters hoặc dấu chấm.

~~~java
package example.gateway.security;

import java.util.regex.Pattern;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public final class StrictRawPathWebFilter implements WebFilter {

    // "/" hoặc một chuỗi path segments ASCII với "/" duy nhất giữa chúng.
    private static final Pattern SAFE_RAW_PATH =
        Pattern.compile("^(?:/|/[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*/?)$");

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        String rawPath = exchange.getRequest().getURI().getRawPath();

        if (rawPath == null
                || rawPath.length() > 2048
                || !SAFE_RAW_PATH.matcher(rawPath).matches()) {

            exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
            return exchange.getResponse().setComplete();
        }

        return chain.filter(exchange);
    }
}
~~~

**Giới hạn quan trọng của ví dụ:**

- Filter **không decode và không rewrite**; nó chỉ reject hoặc cho chain đi tiếp.
- Regex cấm `%`, dots, semicolons, raw backslashes, double slash và Unicode **nếu chúng còn xuất hiện trong representation mà filter nhìn thấy**.
- Ingress hoặc HTTP server decoder có thể xử lý URL **trước WebFilter**; Java filter không phải lớp phòng thủ duy nhất.
- `@Order(Ordered.HIGHEST_PRECEDENCE)` là ý định filter chạy sớm, cần verify thứ tự thực với Spring Security.
- Nó không kiểm query, Host, authentication/authorization, body và backend resources.
- Nó sẽ reject những path hợp lệ như `/favicon.ico`, `/.well-known/**` hoặc Unicode slugs; chỉ dùng cho một API grammar như giả định.
- Nếu Actuator chạy trên management port/server riêng, WebFilter ở application port **không tự bảo vệ Actuator**.

Đây là **policy minh họa**, không phải canonicalizer phổ quát cho mọi Spring Cloud Gateway app.

## 16. Unit test StrictRawPathWebFilter

Dùng Spring MockWebExchange và Reactor Test để chứng minh không gọi downstream chain:

~~~java
package example.gateway.security;

import java.net.URI;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.*;

class StrictRawPathWebFilterTest {
    private final StrictRawPathWebFilter filter =
        new StrictRawPathWebFilter();

    @Test
    void acceptsSimplePathAndInvokesNext() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/api/orders/42"));
        AtomicBoolean nextCalled = new AtomicBoolean();
        WebFilterChain next = ex -> {
            nextCalled.set(true);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, next))
            .verifyComplete();

        assertTrue(nextCalled.get());
    }

    @Test
    void rejectsEncodedTraversalBeforeNext() {
        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get(
                URI.create("/api/%2e%2e/admin")));
        AtomicBoolean nextCalled = new AtomicBoolean();
        WebFilterChain next = ex -> {
            nextCalled.set(true);
            return Mono.empty();
        };

        StepVerifier.create(filter.filter(exchange, next))
            .verifyComplete();

        assertFalse(nextCalled.get());
        assertEquals(HttpStatus.BAD_REQUEST,
            exchange.getResponse().getStatusCode());
    }
}
~~~

**Unit test không chứng minh Netty/ingress parser sẽ giữ y nguyên encoded path**. Cần integration tests qua HTTP server và ingress.

### Input tương ứng với regex ở ví dụ

| Raw path | Kỳ vọng khi WebFilter thực sự thấy chuỗi này |
|---|---|
| `/api/orders/42` | Allow |
| `/api/orders/42/` | Allow trailing slash |
| `/api//orders/42` | Reject |
| `//` | Reject (root không được có slash kép) |
| `/api/../admin` | Reject |
| `/api/%2e%2e/admin` | Reject |
| `/api/%252e%252e/admin` | Reject |
| `/api/%2Fadmin` | Reject |
| `/api/%5cadmin` | Reject |
| `/api/orders;v=1` | Reject |
| `/api/café` | Reject cho ASCII policy |
| `/favicon.ico` | Reject, phải có grammar khác nếu cần |

Không chỉ test HTTP 400: phải chứng minh **backend không có side effect và protected resource không bị gọi**.

## 17. Spring Security WebFlux kiểm quyền theo path và identity

Gateway Server WebFlux thường dùng `SecurityWebFilterChain`. Với API **stateless Bearer JWT** minh họa:

~~~java
package example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class GatewaySecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http) {

        return http
            // Chỉ minh họa cho API bearer stateless; CSRF khác nếu dùng cookies.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health").permitAll()
                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_admin")
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Để chạy code trên cần Spring Security OAuth2 Resource Server/JWT dependencies, issuer/JWK decoder, audience/scopes và test thực tế; copy class **không đồng nghĩa production security đã được cấu hình đầy đủ**.

### Bốn giới hạn phải nhớ

1. `pathMatchers` kiểm path **ở thời điểm Security xử lý**, không nhất thiết là path sau Gateway rewrite.
2. Spring Security không tự biết backend sẽ ánh xạ path tới **resource/tenant nào**.
3. Cấu hình `permitAll` cho public route không được dùng để bỏ **backend object-level authorization**.
4. CSRF chỉ tắt khi API thực sự dùng mô hình stateless bearer phù hợp; browser cookie sessions phải có CSRF protection.

Nếu user A và B đều có JWT hợp lệ, backend vẫn phải kiểm họ có quyền đối với **object cụ thể** hay không.

## 18. Gateway Server Web MVC và ProxyExchange có điểm khác

| Khía cạnh | Server WebFlux | Server Web MVC | ProxyExchange MVC/WebFlux |
|---|---|---|---|
| Request API | `ServerWebExchange` / `ServerHttpRequest` | Servlet request / WebMvc.fn `ServerRequest` | Controller/request API theo stack |
| Security | `SecurityWebFilterChain` | `SecurityFilterChain` | Theo MVC hoặc WebFlux |
| Path predicates | Gateway WebFlux factories | `GatewayRequestPredicates` MVC | Controller mappings, không tự có route engine |
| Filters | Reactive `GatewayFilter` / `GlobalFilter` / `WebFilter` | Servlet/MVC handler filters | Controller logic và stack-specific filters |
| Raw path observable | URI object `getRawPath()` | Servlet `getRequestURI()` theo container | Phụ thuộc web stack |
| URL decoder | Reactor Netty/WebFlux behavior | Servlet container/framework behavior | Client+server của ứng dụng |
| Rewrite | Gateway WebFlux filters | Gateway MVC before/handler filters | App URI builder/ProxyExchange |

**Không đem WebFlux `WebFilter` và `Mono` nguyên sang Server MVC**, cũng không coi `HttpServletRequest.getRequestURI()` là raw TCP request line. Servlet containers có thể reject/normalize trước app.

Với ProxyExchange, không xây outbound URI bằng `proxy.uri(rawUrlFromClient)`: đó còn là nguy cơ open proxy/SSRF. Dùng origin allowlist và URI-safe path segment builder.

## 19. Backend filesystem: path traversal không dừng tại HTTP routing

Phản ví dụ:

~~~java
// PHẢN VÍ DỤ: không nối raw clientPath thành đường dẫn đọc file.
Path file = Path.of("/srv/documents", clientPath);
byte[] content = Files.readAllBytes(file);
~~~

Một giá trị có `..` hoặc separator có thể thoát thư mục dự định; symlink còn có thể dẫn ra ngoài dù chuỗi trông hợp lệ.

### Chiến lược an toàn hơn

1. Ưu tiên **opaque ID/UUID** → backend tra metadata để tìm storage key.
2. Kiểm resource owner/tenant/scope trên **ID cuối cùng**.
3. Nếu bắt buộc dùng filesystem path, validate grammar trước, resolve/normalize với `java.nio.file.Path`.
4. Kiểm containment bằng `Path.startsWith(Path)`, **không bằng so sánh string prefix**: `/srv/doc` không bao trùm `/srv/doc-secret`.
5. Kiểm `toRealPath()` và symlink escapes cho files đã tồn tại, theo policy.
6. Với tạo/ghi file, xem xét race/TOCTOU, API file access an toàn (ví dụ `SecureDirectoryStream` nếu được hỗ trợ).
7. Archive extraction còn cần chống `zip-slip`/symlink traversal theo từng entry.
8. Tránh log full internal filesystem paths/credentials ra response.

**`Path.normalize()` một mình không giải quyết symlink, race, quyền sở hữu tài nguyên hoặc path đã bị decode sai ở HTTP layer**.

## 20. Ingress/CDN/WAF: xác định đúng nơi parse path

Một deployment thật có thể có:

~~~text
Client
  → CDN/WAF
  → NGINX/Envoy/Ingress
  → Gateway Server WebFlux / Web MVC
  → HTTP client / service discovery
  → Backend ingress/router
  → Backend controller/storage
~~~

Mỗi hop có thể **reject, giữ nguyên hoặc canonicalize** raw URI. Trong NGINX, `$request_uri` và `$uri` có semantics khác nhau; `proxy_pass`, rewrites, trailing slash và version/config còn ảnh hưởng path được gửi downstream. **Không copy một cấu hình NGINX ngẫu nhiên mà không biết request URI thực backend nhận**.

| Câu hỏi | Chính sách cần có |
|---|---|
| Cho encoded slash không? | Reject nếu ID grammar không cần |
| Cho encoded dot/double encode không? | Thường reject theo strict contract |
| Duplicate slash có bị gộp không? | Thống nhất reject hoặc có canonicalization contract |
| Semicolon path có dùng không? | Reject nếu unsupported |
| Unicode path có cần không? | UTF-8 + normalization form rõ |
| Authorization đánh giá trên cái gì? | Final effective resource + trusted identity |
| Khi reject? | 400 cho malformed/ambiguous, 403/404 theo auth policy |
| Tầng nào được log raw URI? | Security diagnostics hạn chế quyền/retention |
| Ai sở hữu path grammar? | API contract review và ingress/Gateway/backend owners |
| Khi nâng phiên bản proxy? | Regression trên chính production-like chain |

**Không chọn “normalize ở mọi hop”**. Nếu không thể thống nhất parsers, reject ambiguous input sớm và enforce authorization tại backend.

## 21. Phân biệt 400, 401, 403, 404 và 414

Khi một request path bị từ chối, status phản ánh **tầng nào** và **lý do gì**.

| Trường hợp | Status thường phù hợp | Ghi chú |
|---|---|---|
| Percent escape không hợp lệ, path grammar mơ hồ | **400 Bad Request** | Parser/ingress có thể reject trước Gateway |
| Path chứa encoded separator/dot bị policy cấm | **400 Bad Request** | Không cố normalize thành path khác |
| Chưa xác thực | **401 Unauthorized** | Theo authentication scheme |
| Đã xác thực nhưng không có quyền | **403 Forbidden** hoặc 404 concealment theo policy | Cần backend resource authorization |
| Không có route/handler nào match | **404 Not Found** | Khác với thiếu quyền |
| Request-target quá dài | **414 URI Too Long** nếu layer áp | Không nhầm 414 với 413 body size |
| Header quá lớn | **431 Request Header Fields Too Large** nếu áp | Không phải lỗi path |

**Không tự mặc định mỗi request `%2e%2e` sẽ trả 400 ở mọi tầng**: một parser có thể chặn trước app, một security rule có thể trả 403, còn route miss có thể trả 404. Bất biến phải chứng minh là **không truy cập được resource không có quyền**.

## 22. Kiểm thử phải quan sát hai phía của proxy

Một bài test an toàn cần ghi nhận:

1. URL/raw path load generator đã **cố gửi**;
2. Ingress nhận/forward gì;
3. Gateway Security/Path predicate có match không;
4. Có filter `StripPrefix`/`RewritePath`/`SetPath` không;
5. **Backend thật sự nhận method, request-target, URI và query gì**;
6. Backend đã thực hiện **authorization và side effect** nào;
7. Client nhận status/body/headers gì.

**Chỉ assert status 400/404 của client là chưa đủ**. Một request có thể đã tới backend và gây side effect trước khi response cuối là lỗi. Test phải xác minh **backend privileged request counter bằng 0** đối với input không được phép.

### Backend echo chỉ dành cho lab

Ví dụ backend Servlet MVC phát metadata không nhạy cảm:

~~~java
package example.backend.lab;

import java.util.Map;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PathEchoController {

    @GetMapping("/lab/path")
    public Map<String, String> echo(HttpServletRequest request) {
        return Map.of(
            "method", request.getMethod(),
            "requestUri", request.getRequestURI(),
            "servletPath", request.getServletPath());
    }
}
~~~

`getRequestURI()` và `getServletPath()` phản ánh **cách Servlet container đã xử lý request**, không nhất thiết raw TCP bytes ban đầu. Không public endpoint debug này trong production vì có thể lộ topology hoặc URI nhạy cảm.

Trong lab Gateway, nên có mock backend **request journal** (ví dụ WireMock/MockWebServer) để xác nhận path/outbound calls, không chỉ nhìn response text.

## 23. cURL: các đường dẫn cần thử với `--path-as-is`

Một số clients có thể chuẩn hóa literal `/../` trước khi gửi. Với cURL, `--path-as-is` giúp hạn chế việc client tự loại dot-segments trong path của request mà nó tạo.

### Baseline

~~~bash
curl -i --path-as-is \
  'http://localhost:8080/api/orders/42'
~~~

### Bộ negative tests trong lab

~~~bash
# Dot segment
curl -i --path-as-is \
  'http://localhost:8080/api/public/../admin/config'

# Percent-encoded dot segment
curl -i --path-as-is \
  'http://localhost:8080/api/public/%2e%2e/admin/config'

# Double-encoded dot segment
curl -i --path-as-is \
  'http://localhost:8080/api/public/%252e%252e/admin/config'

# Encoded slash
curl -i --path-as-is \
  'http://localhost:8080/api/items/A%2FB'

# Encoded backslash
curl -i --path-as-is \
  'http://localhost:8080/api/items/A%5CB'

# Duplicate slash
curl -i --path-as-is \
  'http://localhost:8080/api//admin/config'

# Semicolon path param
curl -i --path-as-is \
  'http://localhost:8080/api/items/42;v=1'

# Mixed-case escaped dots
curl -i --path-as-is \
  'http://localhost:8080/api/%2e%2E/admin/config'
~~~

Chạy **chỉ trên môi trường được phép**. `--path-as-is` không cam kết mọi bytes HTTP request-line hoàn toàn giống input string, vì HTTP library, proxy, TLS hoặc protocol translation vẫn có thể tác động. Nếu cần chứng minh octet-level behavior, dùng HTTP tracing/capture hợp lệ ở lab.

**Quan trọng:** Không đưa private tokens/real user IDs vào request samples, logs hoặc test dashboard.

## 24. Ma trận kiểm thử: kết quả an toàn quan trọng hơn status tuyệt đối

| Input (raw path ở đầu đường đi) | Expected strict grammar | Protected backend calls | Giải thích |
|---|---|---:|---|
| `/api/orders/42` | Allow nếu authenticated | Theo authorization | Baseline |
| `/api/orders/42/` | Theo contract | Không tăng quyền | Trailing slash |
| `/api/orders/../admin` | Reject | **0** | Raw traversal |
| `/api/%2e%2e/admin` | Reject | **0** | Encoded dots |
| `/api/%252e%252e/admin` | Reject | **0** | Double encoding |
| `/api/%2Fadmin` | Reject | **0** | Encoded slash |
| `/api/%5Cadmin` | Reject | **0** | Encoded backslash |
| `/api//admin` | Reject | **0** | Duplicate slash |
| `/api/items;role=admin/42` | Reject nếu unsupported | **0** | Matrix param |
| `/api/%00/admin` | Reject/parser reject | **0** | NUL |
| `/api/%ZZ/admin` | Reject/parser reject | **0** | Invalid escape |
| `/api/café` | Reject với ASCII-only | **0** | Unicode input |
| `/API/admin` | Deny/no route theo grammar | **0 nếu không có quyền** | Case sensitivity |
| `/api/admin/config` thiếu scope | 403/404 theo policy | **0** hoặc backend deny | Authorization |
| `/api/admin/config` scope admin | Allow | Chỉ resource hợp lệ | Positive security |

Bảng phản ánh **API strict grammar minh họa** ở phần 15. Với API có Unicode/encoded slug hợp lệ, expected status khác, nhưng **không được có privilege escalation**.

### Test không chỉ ở Gateway

- Security deny phải xảy ra trước protected business operation.
- Backend không được bỏ authorization dù HTTP path có vẻ “đã qua Gateway”.
- Unit tests xác minh custom WebFilter không gọi chain khi reject.
- HTTP integration tests xác minh ingress/HTTP server parser, Gateway và backend đều an toàn.
- Test cả HTTP/1.1 và HTTP/2 nếu production hỗ trợ hai protocol.
- Test request có/không token, token thiếu scope, cross-tenant resource và header spoofing.

## 25. Integration test: Gateway → mock backend → privileged journal

Một setup end-to-end nên gồm:

~~~text
Gateway:
  - SpringBootTest RANDOM_PORT
  - Strict path policy bật theo cấu hình test
  - Spring Security auth rules
  - Public route và protected route

Mock backend:
  - /catalog/items/42 trả 200 + marker công khai
  - /admin/config trả 200 + marker giả lập "PRIVATE_TEST_ONLY"
  - Journal đếm request và ghi path ở backend

Test case:
  1. Gửi path variant bằng client HTTP có khả năng giữ request-target.
  2. Assert response không lộ "PRIVATE_TEST_ONLY".
  3. Assert mock backend không nhận request tới /admin/config.
  4. Assert policy status theo parser/ingress đã chọn.
  5. Assert negative case không có resource side effect.
  6. Assert request hợp lệ tới đúng backend path và nhận status hợp đồng.
~~~

**StepVerifier + MockServerWebExchange không thay thế test trên Netty/ingress thật.** Một unit test có thể set URI chứa encoded bytes trực tiếp vào mock, trong khi Netty hoặc ingress có thể reject/decode/normalize trước khi request tới filter.

### Khi thay Spring Boot/Gateway/Netty/Ingress version

Chạy lại **cùng regression matrix** và so:

- Phần trăm 400/403/404;
- Backend requests cuối cùng;
- Raw/canonical path ở từng hop;
- Trạng thái authorization;
- False positives với legitimate Unicode/encoded identifiers;
- Dynamic routes/rewrite config revisions.

Không approve rollout nếu chỉ thấy “nhiều request bị chặn hơn”; có thể đồng thời gây outage cho client hợp lệ mà không xử lý root cause.

## 26. File download, object IDs và quyền truy cập

Giả sử endpoint:

~~~text
GET /api/files/{documentId}
~~~

Một thiết kế phòng thủ:

1. `documentId` là opaque UUID hoặc integer với grammar chặt.
2. Gateway/Spring Security xác thực request.
3. Backend tra ID → storage key theo metadata **server-side**.
4. Backend kiểm **object owner, tenant, scope và trạng thái quyền**.
5. Storage API trả object được phép, không ghép raw URI path thành filesystem path.
6. Download headers như `Content-Disposition`/`Content-Type` được escape/validate theo contract.
7. Không log filesystem path thật hoặc user secrets trong telemetry.

Nếu phải dùng file paths, `Path.normalize()` và `Path.startsWith(Path)` chỉ là một phần của phòng thủ; **symlink và race/TOCTOU** vẫn cần giải pháp filesystem-level. Với archive extraction, kiểm từng entry để chống zip-slip và symlink escapes.

**Gateway không thể xác thực mọi quan hệ sở hữu tài liệu.** Backend phải từ chối cross-tenant access ngay cả khi path đi qua public route được phép.

## 27. Dynamic routes, rate limiting, retry và fallback không thay path security

### Dynamic routes

Khi Gateway đọc routes từ Config Server/DB/registry hoặc cung cấp route mutation API:

- Chỉ principal đáng tin được tạo/sửa `Path`, `RewritePath`, `SetPath`, `StripPrefix` và target URI.
- Review route `Path=/**` và patterns chồng lấn.
- Không để tenant tự trỏ route tới admin/metadata/internal targets.
- Kiểm changes bằng GitOps/review và route revision audit.
- Reconcile route config giữa nhiều Gateway instances.
- Khi nâng phiên bản filter factory, test effective downstream path.

### RequestRateLimiter

RateLimiter không phải URL validator. `KeyResolver` không nên dùng raw user path làm identity key vì encoded variants có thể tạo keys khác nhau. Chọn verified identity + stable policy ID và giữ metric labels hữu hạn.

### Retry

Retry không làm request an toàn hơn; nó có thể replay **cùng outbound path đã bị biến đổi**. Một POST có side effects còn có nguy cơ lặp nghiệp vụ. Kiểm idempotency/deadline/attempts riêng.

### Circuit breaker/fallback

Fallback có thể lấy cached data khi backend lỗi, nhưng **không được bỏ authorization hoặc lộ dữ liệu user A cho user B**. Không dùng fallback 200 để che dấu một route đã trỏ sai resource. Fallback headers chứa thông tin exception cũng phải được kiểm dữ liệu được phép chuyển tiếp.

## 28. Observability: tìm mismatch mà không ghi lộ credentials

Trong sự cố, phải biết **hop nào thấy path nào**, nhưng raw URI hoặc query có thể mang tài liệu/user IDs, bearer tokens hoặc PII.

| Trường | Ghi log/metric thế nào |
|---|---|
| Gateway route ID | Cho phép nếu finite và được review |
| HTTP method/status | Cho phép |
| Correlation/trace ID | Logs/traces, không làm Prometheus label |
| Reject reason | Enum hữu hạn: `invalid_escape`, `ambiguous_path`... |
| Canonical route template | `/api/items/{id}` thay vì raw URL |
| Raw path | Chỉ security diagnostics có RBAC/redaction/retention |
| Query / Authorization / Cookie | Không log nguyên văn |
| Downstream host/path nội bộ | Hạn chế trong admin logs |
| User/tenant ID | Không gắn vào metrics labels |
| Raw exception messages | Không forward client hoặc đưa vào nhãn metrics |

Ví dụ custom counter **đề xuất**, không phải Gateway built-in:

~~~text
gateway_path_rejections_total{
  reason="ambiguous_separator",
  route_class="public_api"
}
~~~

`reason` và `route_class` phải thuộc **tập giá trị cố định**. Raw path mỗi request sẽ tạo cardinality cực cao và có thể làm rò thông tin trong Prometheus.

Nếu edge chặn trước Gateway, Gateway metric **không thể đếm** request đó; kết hợp ingress/WAF metrics với Gateway HTTP/Gateway route metrics.

## 29. Incident runbook cho path normalization mismatch

Khi nhận báo cáo nghi path bypass:

1. **Giới hạn ảnh hưởng:** xác định route, backend, methods, auth policy và thời gian.
2. **Xem route revision:** `Path`/`RewritePath`/`StripPrefix`/`SetPath` có thay đổi không?
3. **Xem proxy chain:** ingress/HTTP/2 translation/forwarded prefix có thay đổi?
4. **Đối chiếu representations:** raw path trong controlled logs và effective downstream path.
5. **Kiểm backend logs/journal:** protected resource có thực sự được truy cập không?
6. **Đánh giá credentials/tenants:** có unauthorized object reads hoặc writes không?
7. **Chặn nguồn mơ hồ:** reject tại edge/Gateway theo grammar; kiểm backend auth ngay.
8. **Tạo regression tests:** raw/double-encoded slash/dot, semicolon, Unicode, invalid UTF-8, route rewrites.
9. **Canary/rollback:** theo dõi 400/403/404, false positives, legitimate client traffic và backend privileged access.
10. **Postmortem:** ghi rõ hop chịu trách nhiệm canonicalization và bổ sung contract vào architecture review.

**Không chỉ chặn một payload cụ thể bằng regex** rồi kết luận an toàn. Cần thay bất biến: một caller không thể thay resource bằng encoding variants.

## 30. Troubleshooting theo triệu chứng

| Triệu chứng | Giả thuyết | Điều phải kiểm |
|---|---|---|
| Raw `..` bị chặn nhưng `%2e%2e` tới backend | Decode ở hop sau | Kiểm raw vs decoded ở từng hop |
| `%252F` vượt filter | Double decoding | Reject ambiguous/repeated decoding |
| `%2F` trả 400 nhưng `%2f` lại match | Case-sensitive check không đúng | Hex case tests |
| Security cho public nhưng backend admin | Rewrite/prefix mapping | Final outbound path + backend auth |
| Gateway 404 nhưng backend đã gọi | Proxy/error/redirect behavior | Backend request journal |
| `/api//items` vẫn được route | Proxy collapse separators | Ingress config và matching |
| Semicolon mất giữa Gateway/backend | Matrix param stripping | Parser behavior/version |
| Unicode slug trỏ object khác | NFC/NFD/case folding | Canonical ID và DB lookup |
| Windows file backend đọc ngoài base | Backslash/symlink | Real path containment |
| `getRawPath` không thấy percent escapes | Ingress đã normalize | Edge policy/tracing |
| WebFlux filter không chạy ở MVC | Sai web stack | Servlet filter/HandlerFilter |
| RewritePath regex làm đổi encoding | YAML escaping/URI processing | Test outbound bytes/path |
| 400 tăng sau deploy hardening | Legitimate encoded slugs | API grammar migration |
| Gateway route 200 nhưng backend private | Backend thiếu object-level auth | Deny-by-default ở resource |
| Một Gateway node khác node còn lại | Config/version/ingress drift | Route revision, release metadata |
| Metrics cardinality tăng | Raw paths làm tags | Stable route template |
| Raw token lộ logs | Raw request-target logging | Redact/rotate/restrict |
| Ingress 403 nhưng Gateway không log | Edge reject trước app | Ingress WAF/access logs |
| Actuator bị expose qua catch-all rewrite | Management/routing policy lỗi | Tách port, restrict endpoints |

### Sáu câu hỏi khoanh vùng

1. Request dừng ở **hop nào**?
2. Mỗi hop **nhìn representation path nào**?
3. Tầng nào decode, normalize, re-encode, rewrite hoặc redirect?
4. Spring Security **authorize gì**, backend cuối **thực thi gì**?
5. Backend privileged request counter/side effects có thật bằng 0?
6. Regression có bao phủ variants và không chặn nhầm API hợp lệ?

Đừng “sửa nhanh” bằng cách bật `permitAll`, tắt TLS, mở Actuator, cho phép encoded slash trên mọi server hoặc chỉ thêm một rule chặn `../`.

## 31. Checklist gia cố production

### Path grammar và parser

- [ ] Đã định nghĩa path grammar từng nhóm API: charset, encoding, separators, max length.
- [ ] Raw path/decoded path/normalized path được phân biệt rõ trong design.
- [ ] Có policy rõ cho `%2F`, `%5C`, `%2e`, `%25`, `..` và `//`.
- [ ] Không tự decode lặp hoặc dùng `URLDecoder` trên toàn raw path.
- [ ] Invalid UTF-8, malformed escapes, NUL/control chars bị reject theo policy.
- [ ] Semicolon/matrix params được hỗ trợ có chủ đích hoặc reject.
- [ ] Unicode normalization thống nhất khi business cần, object IDs canonical.
- [ ] Trailing slash/case sensitivity không tạo authorization bypass.
- [ ] Không silently normalize request mơ hồ thành privileged path.

### Gateway và backend authorization

- [ ] Đã chọn đúng Gateway variant WebFlux/MVC/ProxyExchange.
- [ ] Security chain phù hợp stack và **deny by default**.
- [ ] `Path` predicate chỉ chọn route; backend vẫn authorize resource cuối.
- [ ] Mỗi `StripPrefix`/`RewritePath`/`SetPath` có expected outbound path tests.
- [ ] Catch-all/dynamic routes không expose admin/actuator/internal endpoints.
- [ ] Forwarded headers chỉ được tin qua proxy đã kiểm soát.
- [ ] Outbound URI dùng allowlist/builder, không nối raw host/path từ client.
- [ ] File/object API dùng opaque IDs/authorization và filesystem containment nếu có.
- [ ] Rate limiter/retry/fallback không được coi thay thế kiểm path hoặc quyền.

### End-to-end regression và vận hành

- [ ] Ingress/CDN/WAF và backend proxy có normalization contract được kiểm.
- [ ] Tests có encoded slash/dot/double encoding/semicolon/slash kép/Unicode/invalid escapes.
- [ ] Kiểm cả HTTP/1.1 và HTTP/2 nếu production hỗ trợ.
- [ ] Negative tests chứng minh **0 protected backend calls** khi reject.
- [ ] Kiểm không lộ dữ liệu cross-tenant, không có side effect bị cấm.
- [ ] Đã test qua network path production-like, không chỉ MockServerWebExchange.
- [ ] Sau mỗi lần nâng Gateway/Netty/Servlet/ingress version chạy lại matrix.
- [ ] Logging dùng redaction/RBAC/retention cho raw path diagnostics.
- [ ] Metrics dùng reject reason code và route template, không raw URL labels.
- [ ] Có runbook, route revision audit và rollback plan.

## 32. Bài tập thực hành

**Bài 1 — Raw và decoded:** Vẽ data flow cho `/api/items/A%2FB` qua client, ingress, Spring Security, Gateway route, backend. Xác định representation nào được mỗi hop dùng để quyết định quyền.

**Bài 2 — Double encoding:** Với `/api/public/%252e%252e/admin`, viết biểu diễn sau 0/1/2 lần decode. Giải thích vì sao “decode đến khi hết dấu %” là anti-pattern.

**Bài 3 — Route rewrite:** Gateway `Path=/public/catalog/**` kết hợp `StripPrefix=1`. Tạo bảng public URLs → backend URLs, xác định namespace admin có nguy cơ bị expose và bổ sung policy backend.

**Bài 4 — WebFilter:** Viết thêm các unit tests cho `StrictRawPathWebFilter`: `%2F`/`%2f`, `%5c`, `;`, `//`, `%ZZ` và Unicode. Tại sao một số malformed URL có thể bị HTTP server reject trước khi test vào Java filter?

**Bài 5 — Authorization:** Dùng JWT không có scope admin gọi path variants; assert Gateway/ingress deny và backend privileged counter = 0. Thêm test token hợp lệ của tenant A truy cập document tenant B.

**Bài 6 — MVC migration:** Phân tích khi chuyển Gateway WebFlux sang Server Web MVC: khác ở Servlet parser, filter APIs, SecurityFilterChain và route predicates như thế nào? Đề xuất regression matrix.

**Bài 7 — File service:** Thiết kế opaque document IDs và storage lookup không dùng raw file path, chống symlink escape, zip-slip và check-then-open race.

**Bài 8 — Rollout:** Sau khi nâng ingress version, một số Unicode slugs hợp lệ bị 400. Thiết kế cách đo false positives mà không mở lại encoded traversal bypass.

## Tài liệu tham khảo

- [RFC 3986 — Uniform Resource Identifier: Generic Syntax](https://www.rfc-editor.org/rfc/rfc3986) — percent-encoding, reserved/unreserved, dot-segments và normalization.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — HTTP resource semantics và response status.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112) — request-target và HTTP message parsing.
- [RFC 3987 — Internationalized Resource Identifiers](https://www.rfc-editor.org/rfc/rfc3987) — Unicode/IRI considerations.
- [OWASP — Path Traversal](https://owasp.org/www-community/attacks/Path_Traversal) — directory traversal, encoded variants và defensive approaches.
- [OWASP — Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html) — allowlist grammar và validation.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) — deny by default, object-level authorization.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — trusted outbound URI và egress controls.
- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — Gateway Server WebFlux/MVC, Path predicates, StripPrefix, RewritePath, SetPath và phiên bản.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — request path abstractions và WebFilter.
- [Spring Security — Reactive](https://docs.spring.io/spring-security/reference/reactive/index.html) — `SecurityWebFilterChain`, path-based authorization và resource server.
- [Spring Security — Servlet](https://docs.spring.io/spring-security/reference/servlet/index.html) — Servlet `SecurityFilterChain`.
- [NGINX — Core Variables](https://nginx.org/en/docs/http/ngx_http_core_module.html#variables) — `$request_uri` và `$uri`, cần phối hợp với proxy_pass/rewrite config.
- [Unicode Standard Annex #15](https://unicode.org/reports/tr15/) — Unicode normalization forms.

**Ghi nhớ:** **Path traversal không chỉ là literal `../`**. Rủi ro xuất hiện khi ingress, Gateway, Security, path filters và backend **giải mã `%HH`, xử lý `..`/`//`, encoded slash/backslash, semicolon, Unicode và rewrites theo quy tắc không nhất quán**. Hãy thiết kế **path grammar rõ, reject ambiguous inputs, không decode lặp**, và bắt buộc **backend authorize resource cuối cùng** sau mọi biến đổi. Unit tests cho Java filter là cần thiết nhưng chưa đủ: phải test nguyên tuyến, khẳng định **không một request không được phép nào chạm tài nguyên đặc quyền**, đồng thời ghi log/metrics an toàn không lộ dữ liệu.


