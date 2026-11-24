# Thêm header và ánh xạ ResponseEntity trả về

## 1. Vì sao Proxy Exchange cần kiểm soát cả hai chiều HTTP?

Trong kiến trúc microservices, **Spring Cloud Gateway** giúp xây cổng vào chung: định tuyến request qua predicate, phối hợp filter chain, biến đổi path/header, khám phá dịch vụ, bảo vệ bằng authentication/authorization, rate limiting, circuit breaker, retry, TLS và theo dõi lưu lượng. Với một số tác vụ cần viết **logic proxy ngay trong controller**, Spring Cloud Gateway còn có biến thể **Proxy Exchange**, cho phép sử dụng đối tượng `ProxyExchange<T>` làm tham số của handler.

Giả sử client gọi `GET /api/catalog/items/42`; controller muốn gọi `GET https://catalog.internal.example/items/42`, thêm header xác định **nguồn gọi nội bộ đáng tin**, nhận phản hồi Catalog rồi bổ sung một header cho client. Có hai bước độc lập:

1. **Request outbound:** Xây URL, chọn method và **thiết lập header gửi tới Catalog**.
2. **Response inbound → outbound:** Nhận `ResponseEntity<T>` từ Catalog, **ánh xạ status, headers và body** sang `ResponseEntity<S>` sẽ trả cho client.

Nếu gộp hai hướng này, bạn có thể thêm header nhầm phía, làm rò JWT, chuyển cookie của backend sang browser, làm mất `Content-Type`, ghi sai `Content-Length` hoặc biến HTTP 503 thành 200 mà không nhận ra.

~~~mermaid
flowchart LR
    C["Client"] -->|"Request headers / body"| H["MVC hoặc WebFlux controller"]
    H -->|"ProxyExchange.header(...) / uri(...) / get(...)"| B["Catalog backend"]
    B -->|"HTTP status, headers, body"| M["ResponseEntity mapper"]
    M -->|"Final status, safe headers, body"| C
~~~

**Chủ đề:** “Thêm header và ánh xạ ResponseEntity trả về”, thuộc chương **Proxy Exchange**. Bài tập trung vào cách sử dụng `ProxyExchange` có chủ đích, không nhầm với cấu hình route/filter của **Gateway Server WebFlux** hoặc **Gateway Server Web MVC**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu đúng **hướng đi** của header khi gọi `proxy.header(...)` và khi sửa `ResponseEntity`.
2. Dùng `ProxyExchange<byte[]>`, `.uri(...)`, `.get(...)` cùng overload mapper `Function<ResponseEntity<T>, ResponseEntity<S>>`.
3. Giữ hoặc thay đổi có kiểm soát **HTTP status, Content-Type, Cache-Control, ETag, Location, Set-Cookie và body**.
4. Phân biệt `HttpHeaders.add`, `set`, `put` và quy tắc header nhiều giá trị.
5. Hiểu mặc định **sensitive headers** như `Authorization`, `Cookie` và **skipped headers** như `Host`, `Content-Length` theo phiên bản.
6. Chọn chính sách **allowlist header**, loại hop-by-hop headers, không để client điều khiển upstream hoặc egress token.
7. Giải thích sự khác nhau của **Proxy Exchange MVC** trả `ResponseEntity` và **Proxy Exchange WebFlux** trả `Mono<ResponseEntity>`.
8. Viết backend stub và HTTP integration tests chứng minh **backend đã nhận header nào** và **client đã nhận response nào**.
9. Xử lý lỗi transport, HTTP 4xx/5xx, response body lớn/streaming, redirect và caching đúng hợp đồng.

> **Giới hạn phiên bản:** Ví dụ chính sử dụng **Proxy Exchange MVC** thuộc các dòng Spring Cloud Gateway có `org.springframework.cloud.gateway.mvc.ProxyExchange`. Artifact đã đổi tên qua những release; nếu dùng WebFlux, thay dependency, package/API và kiểu trả về đúng phiên bản. Không tự áp cấu hình GlobalFilter hoặc GatewayFilterFactory của Gateway Server lên Proxy Exchange.

## 2. Proxy Exchange là một biến thể khác Gateway Server

Spring Cloud Gateway phân biệt hai phong cách triển khai:

| Đặc điểm | Gateway **Proxy Exchange** | Gateway **Server** |
| --- | --- | --- |
| Điểm khai báo | `@GetMapping`, `@PostMapping` và các controller/handler có `ProxyExchange` | Route definitions, route predicates, filter factories/DSL |
| Nhiệm vụ chính | Tạo một số HTTP proxy endpoints với logic ứng dụng trực tiếp | Cổng định tuyến đầy đủ và chính sách hạ tầng chung |
| Web MVC | `ProxyExchange<T>` trong controller MVC, trả `ResponseEntity<T>` | Server Web MVC dựa trên WebMvc.fn và filter chain riêng |
| WebFlux | `ProxyExchange<T>` trong controller reactive, trả `Mono<ResponseEntity<T>>` | Server WebFlux với `ServerWebExchange`, `GatewayFilter`, `Mono<Void>` |
| Thêm header request | `proxy.header(...)` hoặc `proxy.headers(...)` | Các route filters như `AddRequestHeader` theo biến thể |
| Ánh xạ response | Mapper truyền vào `get/post/put/...` hoặc tạo `ResponseEntity` sau call | Route response filters/hạ tầng HTTP riêng |
| Bộ phận xử lý policy | Spring MVC/WebFlux, Spring Security và code controller tự thiết kế | Gateway route predicates/filters cộng Spring Security |

**Không phải** cài Proxy Exchange là toàn bộ bộ lọc `Retry`, `CircuitBreaker`, `TokenRelay` và `RequestRateLimiter` của Gateway Server tự xuất hiện trong controller. Muốn các chính sách đó, phải chọn đúng biến thể, dependency và tích hợp phù hợp, hoặc dùng Gateway Server khi bài toán thiên về định tuyến hạ tầng. **Không nên viết lại một full-featured Gateway Server chỉ bằng các controller ProxyExchange**.

### Hai HTTP hops và hai bộ header

~~~text
Hop 1: Client -> Proxy Exchange application
    Request headers của client
       |
       v
    Controller/Spring Security quyết định dữ liệu tin cậy
       |
       v
Hop 2: Proxy Exchange -> Upstream service
    Request headers đã được chọn/sửa cho upstream
       |
       v
    Upstream response: status + headers + body
       |
       v
    Controller mapper tạo ResponseEntity trả client
       |
       v
Hop 1: Proxy Exchange application -> Client
    Response headers của client-facing response
~~~

Header `X-Gateway-Source` đặt trên request outbound **không phải** một header response. Ngược lại, header `X-Proxy-Handled` thêm vào `ResponseEntity` trả về **không tự động gửi lên backend**. Khi debug, luôn hỏi: **“Ai nhận header này?”**

## 3. Dependency và kiểu trả về MVC so với WebFlux

Các dòng Spring Cloud Gateway mới có artifact chuyên biệt:

~~~xml
<!-- Proxy Exchange MVC: chọn đúng version qua Spring Cloud BOM. -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
</dependency>
~~~

~~~xml
<!-- Chỉ dùng khi ứng dụng là Proxy Exchange WebFlux. -->
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-gateway-proxyexchange-webflux</artifactId>
</dependency>
~~~

Ở các dòng trước thời điểm đổi tên artifact, những tên như `spring-cloud-gateway-mvc` hoặc `spring-cloud-gateway-webflux` từng được dùng cho **Proxy Exchange**. Ngày nay cần phân biệt rõ các artifact `proxyexchange-...` với `server-...`; Spring Cloud BOM phải tương thích Spring Boot của dự án.

### 3.1. MVC: trả ResponseEntity trực tiếp

~~~java
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SimpleMvcProxyController {

    @GetMapping("/demo/image")
    ResponseEntity<byte[]> image(ProxyExchange<byte[]> proxy) throws Exception {
        return proxy.uri("http://127.0.0.1:9001/images/logo.png").get();
    }
}
~~~

Đây là ví dụ **chỉ dành cho môi trường lab**, giả định backend 9001 có ảnh. Controller Servlet/MVC có thể gọi HTTP client theo hướng blocking; cần connect/response timeouts và connection pool theo khả năng triển khai.

### 3.2. WebFlux: trả Mono<ResponseEntity<?>>

~~~java
import org.springframework.cloud.gateway.webflux.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class SimpleReactiveProxyController {

    @GetMapping("/demo/image")
    Mono<ResponseEntity<byte[]>> image(ProxyExchange<byte[]> proxy) {
        return proxy.uri("http://127.0.0.1:9001/images/logo.png").get();
    }
}
~~~

**Chỉ sử dụng một trong hai ví dụ theo stack thật.** Package `webflux.ProxyExchange` và method signatures có thể đổi theo release; kiểm tra Javadoc của dependency đã khóa. Không gọi `block()` hoặc `subscribe()` trong WebFlux controller để lấy `ResponseEntity` vì phá vòng đời reactive/cancellation.

### 3.3. Generic T nói gì?

Trong `ProxyExchange<T>`, **`T` là kiểu response body** do HTTP client/converters materialize. Ví dụ:

| `T` | Phù hợp | Rủi ro |
| --- | --- | --- |
| `byte[]` | Chuyển byte JSON, ảnh hoặc tệp nhỏ mà không parse nghiệp vụ | Có thể phải giữ toàn body trong memory |
| `String` | Text response được biết trước charset | Có thể đổi byte/encoding hoặc xử lý nhầm binary |
| DTO | Cần đọc/chỉnh trường JSON có schema | Chỉ xử lý content-type/JSON phù hợp; có nguy cơ mất trường không khai báo |
| `Object` hoặc `?` | Demo passthrough/generic response | Message converters và conversion phải được kiểm chứng |

Nếu response là **video, tệp lớn, SSE/NDJSON hoặc stream dài hạn**, đừng mặc định `ProxyExchange<byte[]>` là cơ chế streaming hiệu quả. Cần xác minh buffering, connection lifetime, backpressure và công cụ proxy thích hợp.

## 4. ResponseEntity gồm những gì?

`ResponseEntity<T>` của Spring là một đối tượng gồm ba phần:

~~~text
ResponseEntity<T>
   |
   +-- HttpStatusCode: 200, 201, 204, 301, 304, 404, 503...
   |
   +-- HttpHeaders:
   |     Content-Type
   |     Cache-Control
   |     ETag
   |     Set-Cookie
   |     Location
   |     Vary
   |     ...
   |
   +-- T body: byte[], String, DTO hoặc null
~~~

| API | Ý nghĩa |
| --- | --- |
| `response.getStatusCode()` | Status upstream mà HTTP client nhận và ProxyExchange chuyển thành ResponseEntity |
| `response.getHeaders()` | Tập headers upstream, có thể nhiều giá trị trên cùng một tên |
| `response.getBody()` | Body đã được chuyển sang kiểu `T` theo converter |
| `ResponseEntity.status(status)` | Bắt đầu dựng một response mới với status chỉ định |
| `ResponseEntity.headers(headers)` | Đưa tập headers đã lựa chọn vào response mới |
| `ResponseEntity.body(value)` | Đặt body phù hợp kiểu dữ liệu |
| `new ResponseEntity<>(body, headers, status)` | Tạo response với ba thành phần một cách tường minh |

**Mục tiêu mapper không phải luôn đổi status**; đa số proxy nên **giữ status nguyên gốc** và chỉ điều chỉnh headers/body theo chính sách. Khi upstream trả 404 hợp lệ thì client nên nhận 404, không phải 200 với body lỗi. Một upstream 503 không tự biến thành 200 chỉ vì mapper hoàn tất bình thường.

### 4.1. ResponseEntity không phải HTTP response đã commit

Trong controller, `ResponseEntity` là **mô tả phản hồi** mà Spring MVC/WebFlux sẽ chuyển thành HTTP status/headers/body. Khi request/response đã bắt đầu streaming ra socket, header/status có thể đã commit; không thể quay lại sửa. Mapper của ProxyExchange thường xử lý **trước khi controller trả response**, nhưng không bảo đảm việc trả `ResponseEntity` có nghĩa tất cả byte đã đến client.

### 4.2. Mapper có thể đổi kiểu T thành S

Overload `get(Function<ResponseEntity<T>, ResponseEntity<S>>)` cho phép nhận một upstream response kiểu `T` rồi tạo response kiểu `S`. Ví dụ, khi upstream trả text JSON, ứng dụng có thể chuyển thành DTO hoặc một error model đã chuẩn hóa nếu contract yêu cầu.

Không chuyển byte[] sang JSON DTO chỉ để thêm header: thao tác deserialize/serialize lại có thể đổi charset, field ordering, precision, unknown fields và `Content-Length`. Nếu chỉ cần header, hãy **giữ body bytes**.

## 5. Phân biệt header cho upstream và header cho client

Đây là điểm quan trọng nhất của bài:

| Muốn thực hiện | Điểm thao tác phù hợp | Ai nhận kết quả? |
| --- | --- | --- |
| Thêm `X-Gateway-Source` vào lời gọi Catalog | `proxy.header("X-Gateway-Source", "catalog-edge")` | **Catalog backend** |
| Đặt nhiều headers outbound có chọn lọc | `proxy.headers(HttpHeaders)` | **Catalog backend** |
| Chặn forward `Cookie`/`Authorization` | Sensitive-header policy trên ProxyExchange + xác thực/phân quyền riêng | Backend **không nhận** credential đó |
| Thêm `X-Proxy-Handled` khi trả client | Mapper tạo `ResponseEntity` mới, gọi `headers.set(...)` | **Client** |
| Giữ upstream `ETag` cho client | Mapper sao chép header hợp lệ | **Client** |
| Đổi upstream HTTP status thành fallback status | Mapper/error policy có điều kiện | **Client**, không làm thay đổi backend result đã xảy ra |

Ví dụ đầu tiên:

~~~java
return proxy
        .uri("http://127.0.0.1:9001/catalog/items/42")
        .header("X-Gateway-Source", "catalog-edge")
        .get();
~~~

Theo Javadoc API của `ProxyExchange`, `header(String, String...)` **thiết lập header cho downstream call** (nghĩa là **request tới backend**). Dù một số tài liệu mô tả ngắn gọn “headers to downstream response”, cách chắc chắn để thêm **response header gửi client** là dùng mapper `ResponseEntity` và kiểm tra bằng hai phía của HTTP test.

Ví dụ thứ hai:

~~~java
return proxy
        .uri("http://127.0.0.1:9001/catalog/items/42")
        .get(upstream -> ResponseEntity
                .status(upstream.getStatusCode())
                .headers(upstream.getHeaders())
                .header("X-Proxy-Handled", "catalog-edge")
                .body(upstream.getBody()));
~~~

Mẫu thứ hai minh họa cách dùng mapper; **chưa an toàn cho mọi backend** vì sao chép nguyên upstream headers. Ở phần tiếp theo, ta viết bản có **response header allowlist** và tránh sao chép hop-by-hop/secret headers. `.header(...)` ở **ResponseEntity builder** là header gửi client, **khác** `.header(...)` ở **ProxyExchange**.

## 6. Ví dụ MVC hoàn chỉnh: thêm request header và ánh xạ ResponseEntity

Thiết kế một API **chỉ đọc**:

- Client gọi `GET /api/catalog/items/{id}`.
- Controller chỉ chấp nhận `id` gồm chữ, số, gạch nối/gạch dưới; không nhận URI hoặc host do client tự chỉ định.
- Backend URL được cấp từ **configuration đáng tin**, không ghép trực tiếp từ header `Host` của client.
- Outbound request được thêm `X-Gateway-Source: catalog-edge`.
- Client response giữ nguyên status và body bytes của Catalog trong phạm vi policy, chỉ forward một **allowlist response headers**.
- Response thêm `X-Proxy-Handled: catalog-edge`.
- Không sao chép `Set-Cookie`, `Location` hay hop-by-hop headers tùy ý; redirect phải có policy riêng.

Ví dụ Java cho **Proxy Exchange MVC**, tương thích về mô hình với artifact `proxyexchange-webmvc`:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/catalog")
public final class CatalogProxyController {

    private final String backendBaseUrl;

    public CatalogProxyController(
            @Value("${catalog.backend-base-url}") String backendBaseUrl
    ) {
        // Trong production: validate scheme, host và port ở startup.
        this.backendBaseUrl = backendBaseUrl;
    }

    @GetMapping("/items/{id}")
    public ResponseEntity<byte[]> getItem(
            @PathVariable String id,
            ProxyExchange<byte[]> proxy
    ) throws Exception {
        if (!id.matches("[A-Za-z0-9_-]{1,40}")) {
            return ResponseEntity.badRequest().build();
        }

        String target = backendBaseUrl + "/catalog/items/" + id;

        return proxy.uri(target)
                .header("X-Gateway-Source", "catalog-edge")
                .header(HttpHeaders.ACCEPT_ENCODING, "identity")
                .get(this::mapCatalogResponse);
    }

    private ResponseEntity<byte[]> mapCatalogResponse(
            ResponseEntity<byte[]> upstream
    ) {
        // Không forward redirect nội bộ khi chưa có policy Location.
        if (upstream.getStatusCode().is3xxRedirection()) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY).build();
        }

        // Policy đơn giản của lab: chỉ xử lý response không nén.
        String encoding = upstream.getHeaders()
                .getFirst(HttpHeaders.CONTENT_ENCODING);
        if (encoding != null && !encoding.equalsIgnoreCase("identity")) {
            return ResponseEntity.status(HttpStatus.BAD_GATEWAY).build();
        }

        HttpHeaders safe = new HttpHeaders();
        copyValues(upstream.getHeaders(), safe, HttpHeaders.CONTENT_TYPE);
        copyValues(upstream.getHeaders(), safe, HttpHeaders.CACHE_CONTROL);
        copyValues(upstream.getHeaders(), safe, HttpHeaders.ETAG);
        copyValues(upstream.getHeaders(), safe, HttpHeaders.LAST_MODIFIED);
        copyValues(upstream.getHeaders(), safe, HttpHeaders.VARY);

        // Header này thuộc response gửi client, không phải request tới backend.
        safe.set("X-Proxy-Handled", "catalog-edge");

        // Body không bị sửa; không sao chép Content-Length từ upstream.
        return new ResponseEntity<>(
                upstream.getBody(),
                safe,
                upstream.getStatusCode()
        );
    }

    private static void copyValues(
            HttpHeaders source,
            HttpHeaders target,
            String name
    ) {
        List<String> values = source.get(name);
        if (values != null && !values.isEmpty()) {
            target.put(name, new ArrayList<>(values));
        }
    }
}
~~~

Cấu hình ví dụ cho **môi trường lab**, không dùng URI do client tự gửi:

~~~yaml
server:
  port: 8080

catalog:
  backend-base-url: http://127.0.0.1:9001
~~~

### 6.1. Vì sao mã trên dùng allowlist response header?

Giả sử Catalog trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "item-42-v3"
Cache-Control: public, max-age=60
Connection: keep-alive
Set-Cookie: INTERNAL_SESSION=abc; HttpOnly
X-Internal-Cluster: blue

{"id":"42","name":"Keyboard"}
~~~

Mapper đang minh họa chỉ giữ `Content-Type`, `ETag`, `Cache-Control` và những header allowlist khác; **không trả** `Connection`, `Set-Cookie` hoặc `X-Internal-Cluster` tới client. Client còn nhận thêm:

~~~http
X-Proxy-Handled: catalog-edge
~~~

**Bắt buộc kiểm tra thực tế:** Message converter/HTTP client có thể xử lý header/body hoặc decompression theo cách riêng; trong một số cấu hình, response `Content-Length` có thể được tính lại bởi framework. Không coi ví dụ JSON ASCII trên là bằng chứng mọi response binary/streaming sẽ được chuyển byte-for-byte.

### 6.2. Status cuối vẫn là status upstream

Với mapper trên:

| Upstream | Response cho client | Giải thích |
| --- | --- | --- |
| 200 + JSON | 200 + JSON | Không đổi kết quả thành công |
| 404 + JSON error | 404 + JSON error | Không biến lỗi tài nguyên không tồn tại thành 200 |
| 503 + JSON error | 503 + JSON error | Không che outage |
| 204 No Content | 204, không body | Giữ semantics không có body |
| 304 Not Modified | 304, không body | ETag/Last-Modified/Vary được phép nếu backend đúng |
| 302 + `Location` nội bộ | 502 trong **policy minh họa** | Không phát redirect nội bộ khi thiếu rule rewrite/allowlist |

Bảng giả định backend 4xx/5xx được ProxyExchange/client chuyển thành `ResponseEntity` trong phiên bản đang dùng. Một số HTTP client/converter có thể **ném exception cho một số response hoặc transport failures**; kiểm thử riêng thay vì xem bảng là bảo đảm tuyệt đối.

### 6.3. Vì sao không dùng `headers(upstream.getHeaders())`?

Nhiều header có thể là dữ liệu nhạy cảm hoặc chỉ có nghĩa cho hop backend → Gateway:

- `Set-Cookie` có thể tạo cookie sai domain/path hoặc đưa session backend lên browser.
- `Location` có thể dẫn tới host nội bộ, host không đáng tin hoặc redirect bất ngờ.
- `Connection`, `Transfer-Encoding`, `Keep-Alive` thuộc hop-by-hop.
- `Content-Length` có thể sai nếu body được decode/re-encode hoặc không gửi theo cùng transport.
- `Server`, `Via`, `X-Internal-*` có thể lộ topology/metadata.
- Header bảo mật như `Access-Control-Allow-Origin`, `Strict-Transport-Security` hoặc CSP phải có **một owner chính sách** ở đúng HTTP boundary.

Allowlist trong ví dụ **chỉ phù hợp với API đọc Catalog**. Với tải xuống tệp, video, range requests, redirects có chủ đích hoặc browser session, bạn phải thiết kế danh sách header khác và kiểm thử đầy đủ thay vì copy nguyên allowlist trên.

## 7. Hiểu đúng HttpHeaders: add, set, put và nhiều giá trị

Một response HTTP có thể chứa nhiều giá trị cho cùng header, chẳng hạn `Vary`, `Cache-Control` hoặc đặc biệt `Set-Cookie`. Spring `HttpHeaders` hỗ trợ cấu trúc tương tự `MultiValueMap<String, String>`.

| Thao tác | Kết quả | Khi nào nên dùng |
| --- | --- | --- |
| `headers.add("Vary", "Accept-Language")` | **Thêm** một giá trị, có thể vẫn còn giá trị cũ | Muốn tăng tập giá trị sau khi hiểu semantics |
| `headers.set("X-Proxy-Handled", "catalog-edge")` | **Thay** danh sách giá trị bằng một giá trị | Header do Gateway sở hữu |
| `headers.put(name, List.of(...))` | Đặt toàn bộ list giá trị của header | Copy một header đa trị có chủ đích |
| `headers.get(name)` | Trả `List<String>` hoặc null | Cần giữ mọi giá trị |
| `headers.getFirst(name)` | Lấy giá trị đầu | Chỉ thích hợp khi hợp đồng cho phép một giá trị |
| `headers.remove(name)` | Loại một header | Redact hoặc bỏ header transport |

Ví dụ tạo response header mà không đổi status/body:

~~~java
private static ResponseEntity<byte[]> withMarker(
        ResponseEntity<byte[]> upstream
) {
    HttpHeaders copy = new HttpHeaders();
    upstream.getHeaders().forEach((name, values) ->
            copy.put(name, new ArrayList<>(values)));

    copy.set("X-Proxy-Handled", "catalog-edge");
    return new ResponseEntity<>(
            upstream.getBody(),
            copy,
            upstream.getStatusCode()
    );
}
~~~

Đoạn này minh họa **copy thay vì mutate đối tượng upstream** nhưng **chưa phải policy bảo mật**, vì đang copy *tất cả* response headers. Trong production, kết hợp phép copy với allowlist/hop-by-hop cleanup như phần 6. Các danh sách giá trị được tạo mới để tránh vô tình chia sẻ mutable list với response gốc.

### 7.1. Không ghi đè nhầm header đa trị

Ví dụ:

~~~java
HttpHeaders headers = new HttpHeaders();
headers.add(HttpHeaders.VARY, "Accept-Encoding");
headers.add(HttpHeaders.VARY, "Accept-Language");

// Thao tác này thay mất hai giá trị trước:
headers.set(HttpHeaders.VARY, "Origin");
~~~

Nếu mục đích là giữ `Vary` của upstream và thêm một dimension cho downstream caches, cần hợp nhất giá trị và tránh duplicate/hành vi không chuẩn. Với `Set-Cookie`, **không** nối nhiều cookies bằng dấu phẩy như một header list thông thường; phải tôn trọng semantics riêng và các thuộc tính `Domain`, `Path`, `Secure`, `HttpOnly`, `SameSite`.

### 7.2. Header case-insensitivity

Theo HTTP, tên header **không phân biệt hoa/thường**: `X-Request-Id` và `x-request-id` là cùng tên về ngữ nghĩa. Spring `HttpHeaders` cung cấp API thích hợp để xử lý điều đó. Không dùng một `HashMap<String, String>` tự viết với so sánh phân biệt chữ hoa để lọc credentials/hop-by-hop headers.

### 7.3. Không đặt newline/control characters vào header

Header values đến từ client hoặc backend có thể chứa dữ liệu không tin cậy. Nếu bạn lấy một chuỗi raw từ query rồi set thành response header, cần kiểm tra độ dài và ký tự điều khiển. Tránh HTTP response splitting/CRLF injection, không cho người dùng tự quyết định tên header hoặc giá trị `Location` mà không kiểm soát.

## 8. Header outbound: khi nào dùng header(...) và headers(...)?

Một request client có thể tới:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Host: api.example.test
Accept: application/json
X-Gateway-Source: attacker
Authorization: Bearer <client-token>
Cookie: SESSION=<session-id>
~~~

Gateway muốn gửi đến Catalog:

~~~http
GET /catalog/items/42 HTTP/1.1
Host: catalog.internal.example
Accept: application/json
X-Gateway-Source: catalog-edge
~~~

Để đặt một header nội bộ có giá trị **do ứng dụng kiểm soát**:

~~~java
proxy.uri(targetUri)
        .header("X-Gateway-Source", "catalog-edge")
        .get();
~~~

Để gửi nhiều headers outbound có chủ đích:

~~~java
HttpHeaders additional = new HttpHeaders();
additional.set("X-Gateway-Source", "catalog-edge");
additional.set("X-Request-Class", "public-read");

return proxy.uri(targetUri)
        .headers(additional)
        .get();
~~~

Theo Javadoc của `ProxyExchange`, `header(...)` và `headers(...)` thiết lập **headers cho downstream request**; `headers(...)` có thể bổ sung/ghi đè headers inbound theo implementation. **Đừng nhầm với `ResponseEntity.headers(...)`**, vốn dùng cho response trả client.

### 8.1. Vì sao không sao chép Authorization từ client?

Các dòng ProxyExchange có danh sách **sensitive headers mặc định**, thường gồm `Cookie` và `Authorization` — chúng không được forward tự động tới backend. Đây là một **hàng rào hữu ích** khi proxy tới những service không cần session người dùng, nhưng không thay thế security review:

1. Backend có thể yêu cầu một token được cấp **cho backend đó** với audience/scope đúng.
2. Có thể cần token exchange/TokenRelay có điều kiện, nhưng không được bỏ mặc định chặn sensitive headers chỉ để “làm backend hết 401”.
3. Nếu thay đổi `proxy.sensitive(...)`, phải xác định API đang **thay thế danh sách** hay bổ sung nó theo phiên bản, và đảm bảo `authorization`/`cookie` vẫn bị chặn khi cần.
4. Không gửi refresh token/ID token tới resource server; không chuyển token client tới domain vendor khác với audience dự định.
5. Backend tự xác thực và phân quyền: một header `X-Gateway-Source` không có chữ ký/identity không phải cơ chế authorization.

### 8.2. “Skipped” headers khác “sensitive” headers

Tài liệu mới của Proxy Exchange phân biệt:

| Nhóm | Ví dụ thường gặp | Vì sao |
| --- | --- | --- |
| **Sensitive inbound headers** | `Authorization`, `Cookie` | Tránh rò credential qua request outbound |
| **Skipped request headers** | `Host`, `Content-Length` | Hop đến backend có host/transport/body encoding khác |
| **Proxy-related headers** | `X-Forwarded-*`, `Forwarded` | Cần xác định chuỗi proxy tin cậy |
| **Request application headers** | `Accept`, `X-Gateway-Source` | Chỉ forward khi backend cần và hợp đồng cho phép |

**Mặc định chính xác có thể thay đổi theo release và auto-configuration.** Thêm `Content-Length` do client gửi vào backend bằng tay có thể khiến body framing sai nếu HTTP client thay đổi body/transfer encoding. Tương tự, không ép `Host` của public Gateway lên kết nối tới backend nội bộ.

### 8.3. Forwarded headers không phải bằng chứng danh tính

Nếu ProxyExchange chạy sau ingress đáng tin, nó có thể cần forwarding metadata để backend biết public scheme/host. Nhưng header do browser tự gửi như `X-Forwarded-Host: attacker.example` **không được tự tin cậy**. Cấu hình trusted proxies/edge normalization theo phiên bản và cấm lấy `X-Forwarded-Host` làm backend target trực tiếp.

## 9. Ánh xạ ResponseEntity bằng Function: đúng thứ tự, đúng kiểu

Overload của các HTTP methods trong ProxyExchange cho phép mapper:

~~~java
// Chữ ký mang tính mô hình của MVC ProxyExchange:
<S> ResponseEntity<S> get(
        Function<ResponseEntity<T>, ResponseEntity<S>> mapper);
~~~

Với WebFlux ProxyExchange, kết quả được đặt trong một `Mono`:

~~~java
// Mô hình WebFlux: publisher trả ResponseEntity đã được map.
Mono<ResponseEntity<S>> response = proxy.get(mapper);
~~~

Mapper nhận response **do HTTP call đã tạo ra**; nó không phải filter chạy trước request, không có nhiệm vụ cấp quyền và không được phép phát một outbound call mới mà không hiểu side effects.

### 9.1. Ba lựa chọn khi ánh xạ

| Lựa chọn | Thực hiện | Khi phù hợp |
| --- | --- | --- |
| **Pass-through chọn lọc** | Giữ status/body, chỉ chuyển headers được phép | Catalog GET, metadata, binary nhỏ |
| **Response enrichment** | Giữ status/body, thêm header do Gateway sở hữu | `X-Proxy-Handled`, cache metadata nội bộ |
| **Response transformation** | Parse/chỉnh body/status có chủ đích | API adapter có hợp đồng riêng và schema ổn định |

Ví dụ mapper giữ nguyên kết quả:

~~~java
return proxy.uri(target)
        .get(response -> new ResponseEntity<>(
                response.getBody(),
                approvedResponseHeaders(response.getHeaders()),
                response.getStatusCode()
        ));
~~~

Ở đây `approvedResponseHeaders` là hàm **tự định nghĩa** của ứng dụng. Không có `ResponseEntity` mapper “magically safe”; chính logic của bạn phải xác định header nào cần forward.

### 9.2. Mapper đổi kiểu T → S

Giả sử upstream cung cấp response kiểu DTO `LegacyProduct`, client lại cần `CatalogProduct`. Mô hình:

~~~java
// Ví dụ phác thảo: LegacyProduct/CatalogProduct do ứng dụng định nghĩa.
return proxy.uri(target)
        .get(upstream -> {
            if (!upstream.getStatusCode().is2xxSuccessful()) {
                // Error body của LegacyProduct không thể tự coi là DTO đúng.
                return mapErrorResponse(upstream);
            }

            CatalogProduct mapped = adapt(upstream.getBody());
            return ResponseEntity.status(upstream.getStatusCode())
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(mapped);
        });
~~~

Đoạn trên là **pseudocode về pattern**, không phải file tự biên dịch: `LegacyProduct`, `CatalogProduct`, `adapt` và `mapErrorResponse` cần được ứng dụng triển khai. Khi đổi body phải kiểm soát status, body null, JSON converter, charset, caching validators (`ETag`) và `Content-Length`. Với tài nguyên cá nhân hoặc giao dịch, không biến lỗi auth hoặc upstream 503 thành thành công giả.

### 9.3. Không biến mọi status thành 200

~~~java
// CHỐNG MẪU: 404/500/503 của backend cũng thành 200.
return proxy.uri(target)
        .get(upstream -> ResponseEntity.ok(upstream.getBody()));
~~~

Nếu backend trả body `{"error":"NOT_FOUND"}` cùng HTTP 404, client có thể nhận HTTP 200 trong phản mẫu trên, làm sai cache, retry policy, monitoring, SLO và logic phía frontend.

### 9.4. Không lấy status cuối làm bằng chứng proxy thành công

Một HTTP 200 do fallback tự tạo không chứng minh backend đã có kết quả đúng, và HTTP 503 do proxy trả có thể là **backend 503** hoặc **gateway transport error**. Cần log/metric riêng cho `upstreamStatus`, `finalStatus`, `outcome` và thời gian, không ghi raw tokens/body.

## 10. Content-Type, Content-Length và Content-Encoding khi ánh xạ body

Khi mapper **không sửa body bytes**, việc giữ `Content-Type` của backend thường hợp lý nếu backend đáng tin và response contract chuẩn. Nhưng một số headers thuộc **phương thức truyền tải** hoặc gắn với chính bytes của body, không phải thuộc tính có thể tùy ý sao chép.

| Header | Khi giữ nguyên body bytes | Khi body được biến đổi |
| --- | --- | --- |
| `Content-Type` | Giữ nếu contract/charset đúng | Đổi sang media type + charset của body mới |
| `Content-Length` | Có thể để framework tính; không tự lấy length cũ nếu không chắc | Bỏ giá trị cũ; tính/để framework tính lại |
| `Content-Encoding` | Giữ **chỉ nếu** bytes thật vẫn cùng encoding | Xóa/cập nhật nếu đã decompress/recompress |
| `ETag` | Giữ nếu representation được giữ nguyên | Phải tính lại hoặc bỏ validator cũ |
| `Last-Modified` | Chỉ giữ nếu semantics của representation không đổi | Đánh giá lại |
| `Vary` | Giữ các dimensions ảnh hưởng representation | Bổ sung dimensions mới nếu response khác theo request |
| `Content-Range` | Chỉ giữ nếu truyền đúng range bytes | Không gửi như cũ nếu body đã thay |
| `Cache-Control` | Theo policy của nguồn và API contract | Phải khớp tính nhạy cảm/mới cũ của body mới |

### 10.1. Đổi body nhưng giữ ETag cũ là lỗi logic

~~~text
Backend:
  ETag: "product-42-v5"
  Body: {"sku":"42","price":1000}

Gateway adapter:
  Body: {"id":"42","priceText":"1.000 VND"}
  ETag: "product-42-v5"     <-- phải xem lại
~~~

Nếu ETag upstream là validator cho representation cũ, dùng nó với representation đã biến đổi có thể làm cache/conditional GET trả kết quả không hợp đồng. Trong một số trường hợp có thể xây validator mới dựa trên version của dữ liệu và phép biến đổi ổn định; trong trường hợp khác, bỏ ETag sẽ an toàn hơn.

### 10.2. Charset và Unicode

Ví dụ body JSON chứa tiếng Việt. Nếu chuyển `byte[]` sang `String` rồi encode lại với charset mặc định JVM, có thể làm hỏng UTF-8 hoặc Content-Length. Dùng message converters/charset đúng hợp đồng. **Byte length không bằng số ký tự Java**; không đặt `Content-Length` bằng `string.length()`.

### 10.3. Body rỗng

HTTP 204, 304 hoặc HEAD không được xử lý như JSON `{}` bắt buộc. `ResponseEntity` có thể có body null; nếu mapper tự chèn body ở những status không cho phép, container có thể bỏ body hoặc client/parsers hiểu sai. Dùng response semantics chuẩn và kiểm thử bằng HTTP client.

### 10.4. Khi response được nén

Trong ví dụ Catalog, controller đặt `Accept-Encoding: identity` cho request outbound và **từ chối response còn gắn Content-Encoding khác identity** để policy allowlist không vô tình gửi byte nén mà thiếu header mô tả encoding.

Trong hệ thống thật có thể hỗ trợ gzip/br và streaming, nhưng phải xác định **backend trả bytes gì**, HTTP client có tự decompress không, và response mapper có giữ/đổi `Content-Encoding`, `Vary: Accept-Encoding` cùng `Content-Length` nhất quán không. **Không gỡ Content-Encoding một cách mù quáng khi body vẫn đang nén.**

## 11. Redirect và Location: không làm lộ host nội bộ

Một backend trả:

~~~http
HTTP/1.1 302 Found
Location: http://catalog.internal.example/admin/export
~~~

Nếu mapper sao chép nguyên `Location` ra response public, browser có thể bị hướng tới hostname/path nội bộ hoặc một host không đáng tin. Đây có thể là rò thông tin topology, **open redirect** hoặc tạo luồng xác thực sai.

### Ba lựa chọn chính sách

| Chính sách | Tình huống | Điều cần kiểm tra |
| --- | --- | --- |
| **Chặn redirect** | Proxy cho API JSON không cho phép redirect | Trả lỗi có kiểm soát, không xuất Location nội bộ |
| **Rewrite Location có allowlist** | Backend redirect nội bộ tới một public path hợp lệ | So sánh scheme/host/port/path, loại userinfo, normalize URI đúng |
| **Cho redirect đến host được phê duyệt** | OAuth login hoặc CDN redirect do thiết kế | Chỉ chấp nhận host/destination đã biết, kiểm soát token/cookie |

Controller Catalog ở phần 6 cố ý **chặn 3xx và trả 502** vì contract GET Catalog là JSON trực tiếp. Đây không phải policy phổ quát: endpoint OAuth callback, link tải xuống hoặc API có redirect được thiết kế phải có cơ chế riêng.

### Tránh ghép Location bằng string không kiểm tra

Không làm:

~~~java
// CHỐNG MẪU: giá trị host đến từ client, có thể dẫn tới redirect tùy ý.
String redirect = request.getHeader("X-Forwarded-Host") + "/login";
return ResponseEntity.status(302)
        .header(HttpHeaders.LOCATION, redirect)
        .build();
~~~

Header `X-Forwarded-Host` chỉ đáng tin khi ingress/edge đã kiểm soát nguồn proxy. Dùng public base URL được cấu hình hoặc origin allowlist thay vì tin header bất kỳ do Internet client gửi. Với redirect sau authentication, phải bảo vệ `state`, `nonce` và callback URI theo chuẩn OIDC/OAuth của ứng dụng.

### HTTP client có thể tự follow redirect

Không phải mọi HTTP client đều trả 302 cho mapper; một số có thể theo redirect **trước** khi trả `ResponseEntity`. Vì vậy chỉ chặn 3xx trong mapper **không đủ** để bảo đảm client HTTP đã không kết nối tới host thứ ba. Cần cấu hình **redirect policy và egress allowlist ở HTTP client**, kiểm tra behavior thực của phiên bản và giám sát đích kết nối.

## 12. Set-Cookie, session và các response headers nhạy cảm

Khi proxy tới một service, `Set-Cookie` không phải header có thể copy vô điều kiện:

~~~http
Set-Cookie: INTERNAL_SESSION=abc; Path=/; HttpOnly; SameSite=Lax
~~~

Nếu backend đặt cookie cho domain/path của nó, rồi Gateway forward về client với cùng chính sách, browser có thể lưu cookie dưới một context không dự kiến. Nguy hiểm hơn, nếu Gateway trả cookie chứa thông tin phiên backend hoặc biến bearer token thành cookie không có protection phù hợp, nó có thể làm mở rộng phạm vi credential.

### Quy tắc chọn lọc

1. **Catalog public:** thông thường **không forward Set-Cookie** từ backend nếu API không sử dụng session.
2. **Authentication endpoint:** nếu response yêu cầu cookie, xác định cookie nào được phép, domain/path, `Secure`, `HttpOnly`, `SameSite` và độ dài TTL/rotation; không chỉ đổi tên header.
3. **Nhiều Set-Cookie:** giữ chúng dưới dạng các header fields độc lập; không tự nối bằng dấu phẩy hoặc lấy `getFirst` rồi làm mất cookie khác.
4. **Proxy Exchange sensitive request headers** (`Cookie`, `Authorization` mặc định thường bị chặn) **khác** với chính sách forward `Set-Cookie` của response.
5. **Cache-Control:** response cá nhân hoặc token-bearing thường cần `private, no-store` theo contract; không dùng cache công khai cho session data.

Một allowlist chỉ cho phép `Content-Type` và `Cache-Control` có thể phù hợp cho API catalog đơn giản nhưng **không** phù hợp nếu một endpoint đăng nhập cần đặt cookie hợp pháp. Thiết kế từng nhóm endpoint theo quyền và loại dữ liệu.

### HSTS, CORS và response security headers

`Strict-Transport-Security` là chính sách của **origin public HTTPS**, không tự động lấy một giá trị từ backend HTTP nội bộ rồi copy. Tương tự, `Access-Control-Allow-Origin` không được mù quáng lấy từ backend khi Gateway là origin public; cần cấu hình CORS rõ theo danh sách origins và credentials policy. `Content-Security-Policy`, `X-Content-Type-Options` và `Referrer-Policy` phải có owner hạ tầng/ứng dụng được xác định.

**Không đặt duplicate headers mâu thuẫn** ở controller, Spring Security, Servlet filter và ingress; cần test final response tại client sau tất cả các tầng.

## 13. Hop-by-hop headers: vì sao không thể chuyển tất cả?

Một proxy HTTP tạo **hai hops**. Một số headers là cơ chế điều khiển **kết nối ở hop hiện tại**, nên không được đưa sang hop còn lại như entity metadata.

### Danh sách thường phải kiểm soát

| Header | Ý nghĩa / rủi ro |
| --- | --- |
| `Connection` | Liệt kê hop-by-hop option và điều khiển kết nối hiện tại |
| `Keep-Alive` | Tham số keep-alive của hop; không phải policy của cả chuỗi |
| `Transfer-Encoding` | Cách truyền bytes trên kết nối hiện tại |
| `TE` | Transfer-coding/trailer semantics |
| `Trailer` | Trailer metadata của message framing |
| `Upgrade` | Nâng cấp protocol như WebSocket; cần xử lý riêng |
| `Proxy-Authenticate` / `Proxy-Authorization` | Xác thực proxy ở hop, không phải access token ứng dụng |

Theo quy tắc HTTP, **ngoài những tên cố định**, giá trị `Connection` có thể liệt kê thêm **các header cụ thể phải được bỏ** khi chuyển tiếp. Ví dụ:

~~~http
Connection: keep-alive, X-Debug-Transport
X-Debug-Transport: socket-123
~~~

Proxy phải hiểu `X-Debug-Transport` ở đây thuộc connection hiện tại; **chỉ chặn danh sách tên cố định chưa đủ** nếu bạn định copy hàng loạt. Với allowlist nhỏ trong phần 6, bạn không cần sao chép bất kỳ header lạ nào, giúp giảm nguy cơ.

### Một hàm lọc tổng quát phải xét Connection tokens

~~~java
// Pseudocode cho response sanitizer tổng quát:
Set<String> hopByHop = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
hopByHop.addAll(Set.of(
        "Connection", "Keep-Alive", "Transfer-Encoding",
        "TE", "Trailer", "Upgrade",
        "Proxy-Authenticate", "Proxy-Authorization"));

List<String> connectionValues =
        upstream.getHeaders().get(HttpHeaders.CONNECTION);
if (connectionValues != null) {
    for (String connectionValue : connectionValues) {
        for (String token : connectionValue.split(",")) {
            hopByHop.add(token.trim());
        }
    }
}

// Chỉ copy nếu !hopByHop.contains(name)
// Vẫn cần kiểm tra secrets, cache, Location và Content-Length.
~~~

Đoạn này là **phác thảo**, giả định import `Set`, `List` và `TreeSet`. Nó minh họa cách phân tích header `Connection`, không phải một sanitizer production đầy đủ: cần xử lý giá trị không hợp lệ, giới hạn số headers/tokens, protocol HTTP/2 (không cho nhiều hop-by-hop fields), trailer, compression và những response đặc biệt.

### HTTP/2 và streaming

HTTP/2 cấm một số connection-specific fields vốn có ở HTTP/1.1. Khi proxy đổi protocol giữa client, Gateway và upstream, việc copy nguyên `Connection`/`Transfer-Encoding` có thể làm request/response bị từ chối hoặc gây lỗi framing. Để HTTP server và HTTP client quản lý transport, chỉ truyền các headers có ngữ nghĩa end-to-end theo contract.

## 14. Status 4xx/5xx, lỗi transport và fallback phải tách biệt

Một backend có thể **trả một HTTP response hợp lệ với status 503**, hoặc kết nối có thể **thất bại trước khi có response**. Đây là hai loại tình huống khác nhau:

~~~mermaid
flowchart TD
    Call["ProxyExchange.get(mapper)"] --> D{"HTTP call có response?"}
    D -->|Có| R["ResponseEntity: status/headers/body"]
    R --> M["Mapper: bảo toàn/biến đổi có chủ đích"]
    D -->|Không| E["Transport exception: DNS/TCP/TLS/timeout..."]
    E --> P["Exception handler / fault policy"]
    P --> F["502/503/504 theo contract"]
    M --> C["Response gửi client"]
    F --> C
~~~

| Trường hợp | Hướng xử lý thông thường | Điều không nên làm |
| --- | --- | --- |
| Backend trả 404 do item không tồn tại | Giữ 404 và error body phù hợp | Đổi thành 200 mặc định |
| Backend trả 400 do client input | Giữ 400 nếu thực sự do client | Retry vô hạn, rồi gọi đó là backend outage |
| Backend trả 401/403 | Xác định authentication/authorization boundary | Đổi thành 200 hoặc lộ WWW-Authenticate nội bộ không cần |
| Backend trả 429 | Có thể giữ 429, kiểm soát Retry-After | Retry ngay bất chấp quota |
| Backend trả 500/503 | Thường giữ status với body/header an toàn; fallback có chính sách | Nuốt lỗi rồi trả dữ liệu sai |
| TCP connect refused | Error handler 502/503 theo hợp đồng | Để exception message chứa host/token lộ ra client |
| Response timeout | Có thể là 504 nếu contract phù hợp | Giả định backend chưa xử lý side effect |
| TLS certificate/hostname lỗi | Fail closed, alert và sửa trust | Tắt certificate verification để “thử lại” |

### 14.1. Một handler hẹp cho lỗi I/O của ProxyExchange MVC

Trong những dòng Proxy Exchange MVC sử dụng Spring REST client, lỗi I/O có thể được bọc trong `ResourceAccessException`. Một lớp xử lý minh họa:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.ResourceAccessException;

@RestControllerAdvice(assignableTypes = CatalogProxyController.class)
class CatalogProxyErrorAdvice {

    @ExceptionHandler(ResourceAccessException.class)
    ResponseEntity<Map<String, String>> upstreamIoUnavailable() {
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .cacheControl(CacheControl.noStore())
                .body(Map.of(
                        "code", "CATALOG_UPSTREAM_IO_FAILURE",
                        "message", "Dịch vụ danh mục tạm thời không khả dụng"
                ));
    }
}
~~~

Ví dụ không ghi raw exception message hoặc địa chỉ backend ra client. Nó **không cố bắt mọi RuntimeException**, không bảo đảm nhận được mọi exception từ tất cả HTTP clients/versions và không dùng để thay Spring Security 401/403.

### 14.2. Lỗi đã commit response

Với body ngắn dưới dạng `byte[]`, mapper thường diễn ra trước khi MVC trả body cho client. Nhưng với streaming hoặc response đã ghi một phần, khi backend hỏng bạn **không thể thay HTTP 200 thành 503 JSON trong cùng kết nối**. Phải hủy/đóng stream theo protocol và để client có cơ chế retry/resume phù hợp.

### 14.3. Retry/circuit breaker không tự có trong ProxyExchange

Proxy Exchange là utility cho **controller-based HTTP call**. Một route ProxyExchange không tự nhận toàn bộ `Retry GatewayFilter` hoặc `CircuitBreaker GatewayFilter` của Gateway Server. Nếu ứng dụng thêm retry ở HTTP client/service, giới hạn attempts, áp deadline, idempotency và quan sát sự khuếch đại tải. Không tự retry POST tạo đơn/thanh toán khi backend có thể đã commit mà response bị mất.

## 15. Header caching, ETag, Vary và conditional GET

API Catalog thường dùng cache để giảm tải upstream. Tuy nhiên Gateway đóng vai trò proxy/adapter nên phải biết **representation nào được cache**.

### 15.1. Ví dụ conditional request

Lần đầu client gọi:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Accept: application/json
~~~

Backend trả:

~~~http
HTTP/1.1 200 OK
ETag: "item-42-v3"
Cache-Control: public, max-age=60
Content-Type: application/json

{"id":"42","name":"Keyboard"}
~~~

Khi client gọi lần sau:

~~~http
GET /api/catalog/items/42 HTTP/1.1
If-None-Match: "item-42-v3"
~~~

Nếu `If-None-Match` được chuyển tiếp đúng và backend xác nhận representation chưa đổi, backend có thể trả `304 Not Modified` không body. Mapper cần giữ status 304 và validator phù hợp, không tự chuyển thành 200 kèm JSON rỗng.

**Không mặc định ProxyExchange luôn forward mọi conditional header**. Hãy kiểm tra các headers mặc định bị chặn, request adapters và backend counter. Đồng thời, nếu mapper thay JSON, upstream ETag có thể không còn đại diện đúng cho response client nhìn thấy.

### 15.2. Vary là một phần của cache key

Ví dụ backend tạo response khác theo `Accept-Language` hoặc `Accept-Encoding`:

~~~http
Vary: Accept-Language, Accept-Encoding
~~~

Nếu Gateway bỏ `Vary` nhưng vẫn giữ `Cache-Control: public`, shared cache có thể trả một ngôn ngữ hoặc encoding cho nhầm client. Ngược lại, đặt `Vary: Authorization` cho dữ liệu nhạy cảm không tự bảo đảm an toàn; nhiều API cá nhân vẫn cần `Cache-Control: private, no-store` theo hợp đồng.

### 15.3. 304/204/HEAD và body null

| Phương thức/status | Quy tắc |
| --- | --- |
| GET 200 | Body tương ứng Content-Type và Content-Encoding |
| GET 304 | Không gửi message body; giữ validator và cache headers hợp lệ |
| 204 No Content | Không gắn body tùy ý; response không có representation payload |
| HEAD | Trả metadata tương ứng GET theo contract nhưng **không có response body** |
| GET 206 Partial Content | Giữ byte range, Content-Range và Content-Length khớp phần body thật |

Ví dụ `CatalogProxyController` ở phần 6 chỉ khai báo GET, không phải một proxy tệp có hỗ trợ Range/HEAD đầy đủ. Khi mở rộng, test các phương thức và conditional headers thay vì suy diễn từ thành công với GET bình thường.

## 16. Lựa chọn trả lỗi hay giữ response upstream

Một proxy có thể có hai loại error model:

1. **Upstream đã trả HTTP response**: ví dụ 404/429/503 cùng headers và error body.
2. **Proxy không có HTTP response**: ví dụ DNS lỗi, TCP refused, TLS trust failure, socket bị reset hoặc hết deadline.

### 16.1. Giữ status hay chuyển sang mã khác?

| Nguồn lỗi | Chính sách mẫu | Chú ý |
| --- | --- | --- |
| Client gửi ID sai format | Controller trả 400, không gọi upstream | Error body không lộ input raw không cần |
| Backend báo item không tồn tại | Giữ 404 | Không cache lỗi vô thời hạn nếu contract không cho |
| Backend rate limited | Giữ 429 hoặc policy đã định | `Retry-After` cần xử lý riêng nếu muốn forward |
| Backend unavailable và trả 503 | Giữ 503 trong ví dụ | Error body/headers phải được lọc |
| TCP connection refused | Controller advice trả 502 trong ví dụ | Khác 503 mà backend chủ động trả |
| TLS certificate invalid | Kết nối thất bại, alert vận hành | Không tắt certificate verification |
| Không thể nhận response đúng deadline | Có thể 504 theo hợp đồng | Không tự khẳng định backend chưa có side effect |

Nếu `get(mapper)` ném exception với 4xx/5xx ở một client implementation cụ thể, cần cấu hình error handling của HTTP client hoặc giải quyết ở lớp exception. Đừng dùng `catch(Exception ex)` rồi trả 200 `"OK"`.

### 16.2. Retry-After có cần forward?

Backend có thể trả `Retry-After: 10` trên HTTP 429/503. Allowlist ở phần 6 **không chuyển header này**; đó là chính sách tối giản của lab. Nếu API của bạn yêu cầu client retry có hướng dẫn, thêm `Retry-After` vào allowlist **sau khi validate giá trị và hiểu nguồn gốc**, và cân nhắc deadline, rate limiting/overall retry budget.

Không tự gán `Retry-After: 30` chỉ vì circuit breaker chờ 30 giây trước khi thăm dò; đó không phải bảo đảm backend phục hồi sau 30 giây.

### 16.3. Fallback không được tạo thành công giả

Ví dụ user đang đặt đơn:

~~~text
POST order -> backend commit -> response connection reset
ProxyExchange không nhận được response
~~~

Hệ thống **không thể kết luận** đơn hàng chưa được tạo. Nếu Gateway tự retry POST mà backend không có idempotency key/deduplication, đơn có thể bị tạo hai lần. Nếu Gateway thay bằng 201 mặc định, client lại hiểu sai giao dịch. Cần operation ID, idempotency contract và tra cứu trạng thái đáng tin, không giải quyết bằng một mapper chỉ nhìn HTTP status.

## 17. Security: header propagation không phải authorization

Proxy Exchange thường nằm trong một MVC/WebFlux controller có business logic. Vì vậy mọi header thêm hoặc bỏ có thể tác động tới **trust boundary**:

~~~mermaid
flowchart TD
    C["Internet client"] --> S["Spring Security: authenticate/authorize"]
    S --> CTR["ProxyExchange controller"]
    CTR --> P["Outbound header policy"]
    P --> D["Approved upstream destination"]
    D --> B["Backend validates audience / permissions"]
    B --> R["ResponseEntity mapper: allowlist"]
    R --> C
~~~

### 17.1. Không chuyển token sang đích không cần nó

Mặc định sensitive headers của ProxyExchange thường chặn `Authorization` và `Cookie` từ request inbound. Để một service nghiệp vụ nhận token:

- Phải biết **service audience** và scope được phép.
- Chỉ dùng access token của resource server hoặc token exchange có chủ đích, không gửi ID token/refresh token.
- Upstream phải qua TLS và hostname/certificate verification, có thể mTLS khi phù hợp.
- Backend phải tự xác minh chữ ký, audience, quyền sở hữu tài nguyên và tenant.
- Không cho client tự đặt `targetUrl` hoặc `serviceId` làm destination.

**Không thay mặc định `proxy.sensitive()` bằng danh sách rỗng chỉ để vượt lỗi 401.** Điều đó có thể khiến phiên người dùng đi tới backend/vendor không dự định.

### 17.2. Header do Gateway đặt không tự là bí mật

`X-Gateway-Source: catalog-edge` hữu ích để chẩn đoán nhưng một client HTTP khác có thể giả header này khi gọi trực tiếp backend nếu backend public. Nếu backend chỉ tin request từ Gateway, phải có **network segmentation, service identity, TLS/mTLS hoặc chứng thực hợp lệ**, không chỉ so sánh một chuỗi header tĩnh.

### 17.3. CORS và Authorization

CORS là chính sách của browser; nó **không cấp quyền gọi API**. Nếu ProxyExchange controller cho public frontend ở origin khác, cấu hình CORS ở Spring MVC/WebFlux/Security phù hợp và thử OPTIONS preflight. Không phản chiếu mọi Origin và đặt `Access-Control-Allow-Credentials: true` vô điều kiện.

Spring Security của MVC sử dụng `SecurityFilterChain`/Servlet `HttpSecurity`; WebFlux sử dụng `SecurityWebFilterChain`/`ServerHttpSecurity`. **Không dùng nhầm security chain chỉ vì cả hai biến thể cùng hỗ trợ ProxyExchange**.

### 17.4. Client-provided headers có thể gây SSRF hoặc open redirect

Các nguồn không đáng tin gồm `Host`, `X-Forwarded-Host`, `Forwarded`, query `url=`, redirect target và các headers gợi ý upstream. Nếu dùng chúng để dựng `proxy.uri(...)`, người dùng có thể chuyển HTTP client tới metadata service, localhost/admin endpoint hoặc hệ thống ngoài, đồng thời kéo theo credentials/tracing headers.

**Thiết kế an toàn hơn:** URI backend là cấu hình đáng tin, path parameters được validate/encode đúng, HTTP client giới hạn scheme/host/port và egress policy chặn private destinations không được phê duyệt. Redirect following phải nằm dưới chính sách tương tự.

## 18. ProxyExchange và tải lớn: đừng mặc định byte[] là streaming

`ProxyExchange<byte[]>` tiện để giữ payload bytes mà không hiểu JSON schema, nhưng có thể phải materialize một response lớn trong memory trước khi tạo `ResponseEntity`.

Giả sử 200 requests đồng thời, mỗi backend trả body 4 MiB:

\[
200 \times 4\ \text{MiB} = 800\ \text{MiB}
\]

Con số là **dung lượng một bản body/request theo phép tính lý thuyết**, chưa cộng object overhead, TLS buffers, outbound client buffers và bản copy trong mapper/converter. Với tải thực, bộ nhớ cao hơn hoặc thấp hơn tùy streaming/buffering implementation.

### 18.1. Những trường hợp cần giải pháp riêng

| Workload | Rủi ro khi dùng mapper `ResponseEntity<byte[]>` |
| --- | --- |
| 1 KB JSON | Thường phù hợp, dễ bảo toàn status/header |
| 20 MB JSON/ảnh | Body buffer và GC/memory tăng |
| 2 GB download | Không nên tự gom thành `byte[]` |
| SSE/NDJSON | Stream dài, data phải đi theo luồng, mapper có thể không phù hợp |
| Multipart upload | Body replay/copy có thể gây lỗi và tăng memory |
| Video/range requests | Cần chính xác Content-Range, Accept-Ranges, 206, cache validators |
| WebSocket upgrade | Không phải HTTP GET/ResponseEntity ngắn; cần hỗ trợ upgrade chuyên biệt |

Tùy stack, dùng công cụ streaming/Servlet async/WebFlux data buffers hoặc **Gateway Server** nếu mục tiêu là proxy traffic lớn/đa dạng với nhiều policies hạ tầng. Đừng tự giữ stream trong `List<byte[]>` hoặc `ByteArrayOutputStream` không giới hạn để “dễ sửa response header”.

### 18.2. Resource limits và timeout

Proxy Exchange MVC có thể dùng HTTP client blocking hoặc client abstractions phù hợp phiên bản, nên cần connection pooling, connect timeout, response/read timeout và giới hạn concurrent requests. WebFlux cần quan tâm subscriber cancellation và data buffer lifetime. **Thời gian hoàn tất `get()` không tự bao phủ deadline của toàn bộ user operation** nếu còn network/serialization/streaming ở các tầng khác.

### 18.3. Response đã commit không thể tạo lại

Khi client đã nhận HTTP 200 cùng vài kilobytes body, không thể phát một response HTTP 503 mới trên **cùng message**. Nếu upstream disconnect giữa stream, phải kết thúc/đóng transport theo protocol, ghi telemetry và cho client retry/resume ở tầng ứng dụng khi cần; không nối JSON error vào giữa file hoặc SSE frame.

## 19. Backend stub: quan sát header thật và tạo nhiều response

Một cách kiểm thử đáng tin là dựng backend giả lập **độc lập với ứng dụng Proxy Exchange**, chỉ dùng trong lab. Nó phải trả những headers mà mapper được kỳ vọng **giữ** và những headers mà mapper được kỳ vọng **loại**.

Ứng dụng stub ở cổng `9001`:

~~~java
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogStubController {

    private final AtomicInteger requests = new AtomicInteger();

    @GetMapping("/catalog/items/{id}")
    public ResponseEntity<byte[]> getItem(
            @PathVariable String id,
            @RequestHeader(
                    name = "X-Gateway-Source", required = false
            ) String gatewaySource,
            @RequestHeader(
                    name = HttpHeaders.AUTHORIZATION, required = false
            ) String authorization,
            @RequestHeader(
                    name = HttpHeaders.COOKIE, required = false
            ) String cookie
    ) {
        requests.incrementAndGet();

        if ("missing".equals(id)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(bytes("{\"error\":\"NOT_FOUND\"}"));
        }
        if ("busy".equals(id)) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(bytes("{\"error\":\"UPSTREAM_BUSY\"}"));
        }
        if ("empty".equals(id)) {
            return ResponseEntity.noContent().build();
        }
        if ("redirect".equals(id)) {
            return ResponseEntity.status(HttpStatus.FOUND)
                    .location(URI.create(
                            "http://catalog.internal.example/admin"))
                    .build();
        }

        String body = "{\"id\":\"" + id + "\""
                + ",\"seenGatewaySource\":\"" + gatewaySource + "\""
                + ",\"sawAuthorization\":" + (authorization != null)
                + ",\"sawCookie\":" + (cookie != null)
                + "}";

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .eTag("\"catalog-item-v1\"")
                .header(HttpHeaders.CACHE_CONTROL, "public, max-age=60")
                .header(HttpHeaders.SET_COOKIE,
                        "INTERNAL_SESSION=fake; HttpOnly")
                .header("X-Internal-Node", "node-blue")
                .body(bytes(body));
    }

    private static byte[] bytes(String text) {
        return text.getBytes(StandardCharsets.UTF_8);
    }

    int callCount() {
        return requests.get();
    }
}
~~~

**Đây là backend test, không phải code sản phẩm.** Nó cố tình trả cookie nội bộ giả và header topology để kiểm tra gateway có lọc đúng không; chỉ dùng thông tin test, **không bao giờ echo token/secret thật**. `callCount()` là accessor cho test harness cùng process, không được expose thành public endpoint. Nếu test chạy Gateway và stub ở hai process, cần đọc counter bằng giao diện test riêng có phân quyền hoặc dùng tool HTTP stub hỗ trợ request journal.

### Các phản hồi từ stub

| URL backend | Status | Nội dung nổi bật |
| --- | ---: | --- |
| `/catalog/items/42` | 200 | JSON, ETag, Cache-Control, Set-Cookie, X-Internal-Node |
| `/catalog/items/missing` | 404 | JSON lỗi hợp lệ |
| `/catalog/items/busy` | 503 | JSON báo backend bận |
| `/catalog/items/empty` | 204 | Không body |
| `/catalog/items/redirect` | 302 | Location trỏ host nội bộ giả |

### Request/header policy được kiểm chứng thế nào?

Controller ở phần 6 đặt `X-Gateway-Source: catalog-edge` và lọc `Authorization`/`Cookie` theo mặc định ProxyExchange đang được sử dụng. Khi client cố gửi:

~~~http
GET /api/catalog/items/42 HTTP/1.1
X-Gateway-Source: attacker
Authorization: Bearer fake-demo-token
Cookie: SESSION=fake-demo
~~~

Backend stub nên thấy `seenGatewaySource=catalog-edge`, `sawAuthorization=false`, `sawCookie=false`, **nếu phiên bản/runtime đang dùng giữ đúng policy mặc định**. Nếu khác, đó là tín hiệu cần kiểm tra config/header propagation, không nên vội ép test pass bằng cách tin header do client khai.

## 20. HTTP integration test: nhìn cả phía backend lẫn client

Với Proxy Exchange **MVC**, một HTTP test thực đi qua Servlet container và outbound HTTP client sẽ có giá trị hơn việc chỉ unit test mapper. Ví dụ dùng JDK 17+ `HttpClient`, JUnit 5 và Spring Boot:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "catalog.backend-base-url=http://127.0.0.1:9001")
class CatalogProxyIntegrationTest {

    @LocalServerPort
    int port;

    private final HttpClient http = HttpClient.newHttpClient();

    private HttpResponse<String> call(String itemId) throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port
                        + "/api/catalog/items/" + itemId))
                // Các headers chỉ để test chống spoof và sensitive forwarding.
                .header("X-Gateway-Source", "attacker")
                .header("Authorization", "Bearer fake-demo-token")
                .header("Cookie", "SESSION=fake-demo")
                .GET()
                .build();

        return http.send(request, HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void addsOutboundHeaderAndFiltersResponseHeaders() throws Exception {
        HttpResponse<String> result = call("42");

        assertEquals(200, result.statusCode());
        assertTrue(result.body().contains(
                "\"seenGatewaySource\":\"catalog-edge\""));
        assertTrue(result.body().contains("\"sawAuthorization\":false"));
        assertTrue(result.body().contains("\"sawCookie\":false"));

        assertEquals("catalog-edge",
                result.headers().firstValue("X-Proxy-Handled").orElse(""));
        assertFalse(result.headers().firstValue("Set-Cookie").isPresent());
        assertFalse(result.headers()
                .firstValue("X-Internal-Node").isPresent());
        assertTrue(result.headers().firstValue("ETag").isPresent());
    }

    @Test
    void keepsNotFoundAndServiceUnavailableStatuses() throws Exception {
        assertEquals(404, call("missing").statusCode());
        assertEquals(503, call("busy").statusCode());
    }

    @Test
    void doesNotExposeInternalRedirect() throws Exception {
        HttpResponse<String> result = call("redirect");
        assertEquals(502, result.statusCode());
        assertFalse(result.headers().firstValue("Location").isPresent());
    }
}
~~~

**Test minh họa, chưa được chạy trong bài này.** Để chạy cần:

1. Một ứng dụng **Proxy Exchange MVC** chạy RANDOM_PORT với `CatalogProxyController`.
2. Backend stub **riêng** đang nghe đúng cổng 9001.
3. Dependency Spring Boot Test, JUnit 5 và Java HTTP Client của JDK tương ứng.
4. Test routing **không có Security FilterChain chặn anonymous/fake token**, hoặc một cơ chế test authentication có chủ đích. Khi Spring Security thật được bật, token giả `fake-demo-token` có thể bị từ chối trước controller; test security nên là một test khác.
5. Cấu hình HTTP client/ProxyExchange của phiên bản cho phép mapper nhận HTTP 404/503 như response; nếu một client version phát exception, integration setup phải thể hiện đúng policy đã thiết kế.
6. **Tắt tự động follow redirect ở outbound HTTP client trong lab** trước khi yêu cầu test `doesNotExposeInternalRedirect` trả 502. Nếu HTTP client tự follow redirect thì mapper có thể không nhìn thấy status 302; phải xử lý/chặn redirect ở transport và destination egress policy.

Trong CI tốt hơn nên khởi động stub trên **port động** và inject backend URL từ runtime test resources, tránh phụ thuộc cổng 9001 trống hoặc chạy hai tests song song ảnh hưởng nhau.

### Vì sao cần cả stub request journal?

Một assertion về body `seenGatewaySource` có giá trị nhưng chưa chứng minh đầy đủ:

- Hệ thống có thể gửi **hai** outbound attempts do HTTP client/SDK retry.
- Header `Authorization` có thể bị gửi ở một attempt khác.
- Route có thể bị redirect tới một host khác trước khi nhận response cuối.
- Một token thật có thể lọt vào logging dù backend cuối không nhận nó.

Vì vậy integration harness nên ghi **số outbound requests, method/path, host đích, header names được chấp nhận và outcome**, không lưu raw secrets. Test một request thường mong đợi đúng một outbound call khi không cấu hình retry và redirect.

## 21. Ma trận kiểm thử header và ResponseEntity đầy đủ

| Test | Setup | Kỳ vọng |
| --- | --- | --- |
| A. Thêm header outbound | Client gửi `X-Gateway-Source: attacker` | Backend thấy giá trị tin cậy `catalog-edge` |
| B. Nhạy cảm: Authorization | Client gửi token test | Backend không nhận khi policy chặn mặc định |
| C. Nhạy cảm: Cookie | Client gửi cookie test | Backend không nhận khi policy chặn mặc định |
| D. Thêm response header | Backend 200 | Client có `X-Proxy-Handled: catalog-edge` |
| E. Strip internal response header | Backend trả `X-Internal-Node` | Client không nhận |
| F. Strip Set-Cookie | Backend trả cookie giả | Client không nhận |
| G. Keep status 404 | Backend item missing | Client 404, body lỗi được giữ đúng contract |
| H. Keep status 503 | Backend busy | Client 503, không đổi thành 200 |
| I. No content | Backend 204 | Client 204, không body tự tạo |
| J. ETag/Cache-Control | Backend có validators | Client nhận headers allowlist đúng |
| K. Redirect | Backend 302 Location nội bộ | Proxy không lộ Location; policy mẫu trả 502 |
| L. Compression | Backend trả gzip dù đã yêu cầu identity | Không gửi bytes nén như JSON không nén |
| M. Multi-value headers | Backend trả nhiều Vary values | Giữ danh sách giá trị được phép |
| N. Hop-by-hop | Backend trả Connection/Transfer-Encoding | Không copy như entity header |
| O. Invalid item ID | ID chứa ký tự không hợp lệ | Controller 400, **không gọi upstream** |
| P. Transport failure | Backend tắt hoặc TCP reset | Controller advice lỗi có kiểm soát; không lộ URL/token |
| Q. TLS error | Chứng chỉ backend không hợp lệ | Kết nối thất bại, không bỏ verification |
| R. Large body | Response vài chục MiB | Không OOM, phân tích buffering; có limit |
| S. SSE partial response | Stream dừng giữa chừng | Không cố đổi status sau commit |
| T. Concurrent requests | Nhiều requests đồng thời | Không lẫn headers/body giữa hai người dùng |
| U. Security | JWT thiếu quyền | Bị từ chối ở security layer trước outbound |
| V. Retry budget | Backend lỗi liên tục | Không phát outbound attempts vượt policy |

Đừng chỉ kiểm tra response cuối vì **một 200 không cho biết backend đã nhận header nào**; cũng đừng chỉ kiểm tra backend vì **một outbound request đúng không chứng minh client response an toàn**. Hai phía phải có assertions riêng.

### Kiểm thử mapper thuần, không cần socket

Để test chính sách header, có thể tách phương thức `mapCatalogResponse` sang một **class/bean package-private** rồi gọi trực tiếp với `ResponseEntity<byte[]>` giả. Assertions cần kiểm tra status, headers được giữ/bỏ, body reference/bytes và các trường hợp 204/302/503. Unit test này chạy nhanh nhưng **không thay** HTTP integration test về header forwarding thực.

## 22. Chẩn đoán lỗi thêm header và ánh xạ ResponseEntity

Một proxy lỗi có thể biểu hiện dưới dạng **backend không nhận header**, **client không nhận header**, hoặc **HTTP status/body sai**. Hãy phân biệt nguyên nhân bằng cách xác định **hop nào thiếu dữ liệu**.

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client không thấy `X-Gateway-Source` | Header được thêm vào `ProxyExchange` outbound request, không phải response | Dùng `ResponseEntity` mapper để thêm response header |
| Backend không thấy `X-Proxy-Handled` | Header được thêm vào response cuối, không phải outbound request | Dùng `proxy.header(...)` khi cần backend nhận |
| Backend thấy header spoofed từ client | Outbound header policy không override/không chạy | Kiểm tra `proxy.header` và backend stub request journal |
| Backend không nhận Authorization | ProxyExchange chặn sensitive headers mặc định | Xem lại trust boundary và token audience; không mở hàng loạt |
| Backend nhận token không dự kiến | Sensitive policy bị đổi hoặc tự forward headers | Đóng egress, sửa policy, điều tra log/traces và rotate token nếu lộ |
| Client thấy `Set-Cookie` nội bộ | Mapper copy mọi response headers | Dùng allowlist/đổi cookie policy theo contract |
| Client nhận 302 trỏ host nội bộ | `Location` được forward thiếu kiểm tra | Chặn/rewrite allowlist, cấu hình HTTP client redirect policy |
| Proxy trả 200 thay vì backend 404 | Mapper dùng `ResponseEntity.ok(...)` | Giữ `upstream.getStatusCode()` nếu không có contract đổi mã |
| Response 204 có body JSON | Mapper tự chèn payload vào no-content status | Trả body null/không body cho 204/304/HEAD |
| Response mất `Content-Type` | Header không nằm trong allowlist hoặc body đổi kiểu | Giữ/đặt media type hợp lệ |
| Body gzip bị hiển thị lỗi | Body bytes và `Content-Encoding` không đồng bộ | Xử lý compression nhất quán; test Accept-Encoding |
| Browser cache trả sai ngôn ngữ | `Vary` bị bỏ khi giữ public cache policy | Chuyển đúng Vary hoặc thay cache policy |
| Browser không cập nhật sau JSON transform | Giữ ETag của representation cũ | Tính ETag mới hoặc bỏ validator |
| Content-Length không khớp | Copy length cũ sau body rewrite | Bỏ header cũ, để framework tính lại |
| Header nhiều giá trị bị mất | Dùng `getFirst` hoặc `set` thay toàn bộ | Dùng `get` + copy list có chủ đích |
| 401/403 trước ProxyExchange | Spring Security Servlet/WebFlux đã từ chối | Kiểm tra security chain, token/audience, không đổ lỗi cho mapper |
| 502 nhưng backend không nhận request | DNS/TCP/TLS/redirect/egress xảy ra trước HTTP handler backend | Xem transport exception, certificate và destination policy |
| Timeout làm client chờ lâu | Không có timeout/pool budget phù hợp | Thiết lập deadline và giới hạn outbound resources |
| Response mapper không chạy khi backend lỗi | HTTP client ném exception trước khi tạo ResponseEntity | Bổ sung fault handler hẹp, test theo implementation |
| Mapper chạy nhiều lần trên một operation | Client/HTTP client retry hoặc reactive resubscription | Đo attempts, không phát sinh side effect trong mapper |
| Memory tăng khi tải file | `byte[]` materialize body quá lớn | Streaming/bounded buffering hoặc Gateway Server phù hợp |
| Cookie bị lộ trong log | Logging raw HttpHeaders/exception/URI | Log allowlist metadata, xóa/rotate secrets theo sự cố |

### Quy trình điều tra 8 bước

1. **Route/controller match:** `@GetMapping` có được chọn không, hay request bị 404/405 trước ProxyExchange?
2. **Security:** Spring Security có trả 401/403 trước handler không?
3. **Destination:** `proxy.uri(...)` do config hay client điều khiển? Scheme/host/port có hợp lệ và được cho phép?
4. **Outbound headers:** backend stub thấy tên/giá trị header gì? `Authorization`/`Cookie` có bị chặn đúng?
5. **Upstream outcome:** có một HTTP response hợp lệ, hay lỗi DNS/connect/TLS/timeout?
6. **Mapper:** có được gọi không? Nó copy header nào, có giữ `getStatusCode()` và `getBody()` không?
7. **Client response:** status, headers và body thực trên socket có đúng không? Ingress/CDN có sửa thêm không?
8. **Cross-cutting:** retry, caching, CORS, compression, response commit và logging có gây thay đổi ngoài dự kiến?

**Không bật dump toàn HTTP exchange** để chẩn đoán. Dùng backend stub ghi header names/metadata an toàn, trace ID chuẩn và correlation giữa inbound/outbound calls.

## 23. Vận hành: telemetry, giới hạn tải và chính sách thay đổi

Một ProxyExchange controller có thể trông đơn giản, nhưng vẫn là một **HTTP proxy có ảnh hưởng bảo mật**. Bản production cần tối thiểu:

| Mục tiêu | Tín hiệu/kiểm soát |
| --- | --- |
| Đo inbound HTTP | Method, template path, status, latency |
| Đo outbound HTTP | Service đích được allowlist, status, timeout, TLS/connect errors |
| Đo attempts | Phân biệt client request với retry/redirect attempts |
| Giới hạn concurrency | HTTP client connection pool, Servlet threads/WebFlux resource |
| Giới hạn body | Maximum payload size, timeout, streaming policy |
| Đo fallback | Phân biệt backend 503 với gateway-created 502/503 |
| Bảo mật | Sensitive-header stripping, TLS/mTLS, destination validation |
| Response contract | Status/Content-Type/Cache-Control/ETag/Location/Set-Cookie policies |
| Observability hygiene | Không log JWT, Cookie, raw URL query, body cá nhân |
| Release safety | Regression tests với 2xx, 3xx, 4xx, 5xx, timeout, compression |

### 23.1. Hai đơn vị đo khác nhau

Giả sử 1.000 inbound requests tới controller, HTTP client retry 10% requests một lần. Khi ấy:

~~~text
Inbound ProxyExchange controller requests = 1.000
Outbound HTTP attempts                   = 1.100
Backend successful responses             = tùy kết quả từng attempt
Final client responses                   = 1.000 (nếu tất cả kết thúc)
~~~

Với một retry policy có giới hạn, số attempts có thể lớn hơn inbound requests; với circuit breaker fail fast, nhiều inbound requests có thể không phát outbound call. Vì vậy **không suy ngược số lần backend được gọi từ HTTP status cuối**.

### 23.2. Lưu ý với Spring Cloud LoadBalancer/service discovery

ProxyExchange không mặc nhiên giải quyết service discovery như một `lb://` route của Gateway Server trong mọi implementation. Nếu muốn chọn instance qua discovery, cần sử dụng integration/bộ HTTP client tương thích, nguồn ServiceInstance đáng tin và chính sách service identity/egress. Không lấy một service ID từ query/header client rồi cho phép truy cập bất kỳ registered service nào.

### 23.3. Thay đổi header policy phải được review

Một thay đổi tưởng nhỏ như thêm:

~~~java
proxy.header(HttpHeaders.AUTHORIZATION, bearerToken);
~~~

có thể làm backend nhận credential trước đây bị chặn. Nếu `bearerToken` đến từ request client, đây là thay đổi **trust boundary** và cần review về audience, scope, destination, TLS, logs và timeout. Cũng vậy, mở phép copy `Set-Cookie` vào response có thể thay đổi browser session hoặc cấu hình CORS.

**Không xem thay đổi header chỉ là thay đổi format.** Bất kỳ header nào ảnh hưởng identity, caching, redirect, cookies hay transport đều có thể làm thay đổi quyền truy cập và tính đúng đắn của API.

### 23.4. Canary/rollback

Khi deploy mapper mới:

1. Đo tỷ lệ 2xx/4xx/5xx và latency trước thay đổi.
2. Có regression tests với token giả, cookie giả, redirects và error bodies.
3. Canary một tập traffic có kiểm soát; theo dõi lỗi decode JSON, CORS, caching.
4. So sánh `X-Proxy-Handled` và những headers allowlist trên response client.
5. Xác minh backend **không nhận thêm credentials** ngoài contract.
6. Có rollback nếu mapper trả status hoặc headers khác policy.

Trên nhiều ứng dụng/replicas, version của mapper có thể không đồng bộ trong lúc rollout; gắn deployment revision ở telemetry **không chứa secrets** để phân biệt.

## 24. Bài thực hành: thêm header và ánh xạ response an toàn

**Bối cảnh:** Bạn xây một proxy controller cho Catalog. Backend trả JSON đơn giản nhưng còn kèm `Set-Cookie` và `X-Internal-Node` mà client không cần. Cần thêm header `X-Gateway-Source` **chỉ vào request outbound** và header `X-Proxy-Handled` **chỉ vào response client**.

### Phần A — Chuẩn bị

1. Chọn đúng **Proxy Exchange MVC** hoặc **Proxy Exchange WebFlux**, dùng artifact/version theo Spring Cloud BOM.
2. Dựng Catalog stub từ phần 19 tại port 9001 trên lab hoặc cổng động của test harness.
3. Cấu hình backend base URL tin cậy; không lấy URL từ client.
4. Tạo `CatalogProxyController` như phần 6, với phương thức GET và item ID được validate.
5. Đảm bảo lab có request body/response size limits, connect/read timeouts và TLS policy phù hợp với mục tiêu test.

### Phần B — Hai hướng header

1. Gửi `GET /api/catalog/items/42` với `X-Gateway-Source: attacker` từ client.
2. Xác nhận backend nhận `X-Gateway-Source: catalog-edge` do controller đặt.
3. Gửi một header `Authorization: Bearer fake-demo-token` và cookie test trong môi trường **không có dữ liệu thật**.
4. Xác minh backend không nhận hai credentials theo sensitive policy đang dùng.
5. Xác minh client nhận `X-Proxy-Handled: catalog-edge` và **không nhận** `Set-Cookie`/`X-Internal-Node` từ stub.
6. Xác minh body trả client có cùng ID và UTF-8 hợp lệ.

### Phần C — Response mapping

| Bài kiểm tra | Thao tác | Kỳ vọng |
| --- | --- | --- |
| 200 | Gọi ID `42` | Status 200, Content-Type JSON, marker header |
| 404 | Gọi ID `missing` | Status 404 không bị đổi thành 200 |
| 503 | Gọi ID `busy` | Status 503 đúng hợp đồng |
| 204 | Gọi ID `empty` | Body không bị tự thêm |
| 302 | Gọi ID `redirect` | Không lộ internal Location; policy ví dụ trả 502 |
| ETag | Backend gửi ETag | Client nhận validator khi representation không đổi |
| Cache-Control | Backend gửi cache policy | Client nhận header được allowlist khi dữ liệu public |
| Compression | Stub cố trả encoded body | Không gửi body nén mà thiếu Content-Encoding |
| Response header count | Backend có nhiều Vary values | Không mất/nhân sai các values |
| Unknown header | Backend gửi `X-Internal-Node` | Client không nhận |

### Phần D — Làm một phản mẫu rồi sửa

Trong lab **cô lập**:

1. Tạm thay mapper bằng `ResponseEntity.ok(upstream.getBody())`.
2. Gọi ID `missing` hoặc `busy`, xác minh status bị biến sai.
3. Khôi phục mapper giữ `upstream.getStatusCode()`.
4. Tạm copy toàn bộ headers `.headers(upstream.getHeaders())`, xem cookie và header nội bộ có thể lọt ra client.
5. Khôi phục **response allowlist**, đồng thời giữ Content-Type/ETag/Vary phù hợp.
6. Thử đổi body JSON nhưng không bỏ ETag/Content-Length cũ và giải thích hậu quả; **không** đưa phản mẫu vào production.
7. Kiểm chứng behavior bằng HTTP client thay vì chỉ xem unit test mapper.

### Phần E — Bảo mật và vận hành

1. Bật Spring Security phù hợp MVC/WebFlux; kiểm tra anonymous, token hợp lệ, token thiếu quyền.
2. Không cho client đặt upstream URI/Host, không tắt TLS hostname verification.
3. Cấu hình timeout/budget, không retry POST không có idempotency.
4. Dùng request journal của backend stub để kiểm tra outbound attempts không tăng ngoài policy.
5. Quan sát log/tracing không chứa JWT, Cookie, full URI query hoặc response body cá nhân.
6. Với payload lớn/streaming, đánh giá một phương án stream phù hợp thay vì `byte[]` không giới hạn.
7. Ghi lại cấu hình HTTP client redirect policy: mapper chặn 302 chỉ có ý nghĩa khi client không tự theo redirect tới host không tin.

### Phiếu kết quả thực hành

| Hạng mục | Bằng chứng cần nộp |
| --- | --- |
| Dependency | Artifact `proxyexchange-webmvc` hoặc `proxyexchange-webflux` đúng BOM |
| Route/controller | `@GetMapping` và URI backend từ config tin cậy |
| Outbound header | Request journal ghi đúng `X-Gateway-Source` |
| Sensitive headers | Không có Authorization/Cookie gửi tới backend |
| Response mapper | Status/body đúng, marker header được thêm |
| Redaction | Không có Set-Cookie/X-Internal-Node/Location nội bộ lộ ra |
| Caching | Content-Type/ETag/Vary/Cache-Control nhất quán |
| Faults | Kết quả 404/503/302/timeout theo contract |
| Security | Anonymous/user/ops đúng quyền, không bypass |
| Performance | Có giới hạn body, timeout, concurrency phù hợp |

**Tiêu chí đạt:** Người học giải thích chính xác **header nào được gửi đến backend**, **header nào được trả cho client**, dùng mapper mà không đánh mất status/body, có allowlist tránh lộ credentials/metadata và kiểm chứng bằng hai phía của HTTP exchange.

## 25. Tổng kết

- **Proxy Exchange** cho phép một controller Spring MVC/WebFlux trực tiếp gọi backend qua `ProxyExchange<T>` và nhận `ResponseEntity<T>`. Đây là một biến thể **khác Gateway Server**.
- **`proxy.header(...)` và `proxy.headers(...)`** dùng để thiết lập **headers của request outbound tới backend**, theo API/Javadoc. Chúng không tự thêm header vào response client.
- **`proxy.get(mapper)`** và các overload HTTP method tương ứng nhận một `Function<ResponseEntity<T>, ResponseEntity<S>>`, cho phép tạo response **status, headers, body** phù hợp contract.
- **Không đổi status 404/429/503 thành 200** chỉ để có “kết quả thành công”. Giữ mã upstream khi có nghĩa, và tách lỗi transport không có ResponseEntity.
- **Copy response headers có chọn lọc:** `Content-Type`, `ETag`, `Vary`, `Cache-Control` có thể cần giữ; `Set-Cookie`, `Location`, hop-by-hop headers, `Content-Length` và metadata nội bộ cần policy riêng.
- **Mặc định sensitive request headers** như `Authorization`/`Cookie` thường không được forward; đừng vô hiệu hóa hàng rào này nếu chưa xác định token audience và đích tin cậy.
- **ResponseEntity không tự xử lý mọi dạng streaming/binary/redirect/cache**. Khi đổi body, cân nhắc Content-Encoding, validators, header multi-values, response commit và bộ nhớ.
- **Đọc từ hai phía:** backend stub chứng minh outbound header/method/path; HTTP client chứng minh client status/headers/body. Test 200, 204, 302, 404, 503, TLS, timeout, token, compression và body lớn.
- **Version compatibility quan trọng:** artifact, package và phương thức API của Proxy Exchange MVC/WebFlux phải khớp Spring Boot/Spring Cloud BOM; không copy route filters của Gateway Server vào controller ProxyExchange.

Khi thêm header hoặc ánh xạ response trong **SPRING_CLOUD_GATEWAY Proxy Exchange**, hãy luôn xác định **đúng HTTP hop, đúng quyền sở hữu header và đúng hợp đồng ResponseEntity**. Một proxy an toàn không chỉ gửi request đến đúng đích mà còn trả **đúng trạng thái, đúng body, đúng những headers được phép** cho client.

### Tài liệu tham khảo

- **Spring Cloud Gateway — Proxy Exchange Gateway with Spring Web MVC or WebFlux:** https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-proxy-exchange.html
- **Javadoc ProxyExchange MVC (ví dụ API 4.1.x):** https://javadoc.io/static/org.springframework.cloud/spring-cloud-gateway-mvc/4.1.4/org/springframework/cloud/gateway/mvc/ProxyExchange.html
- **Spring Cloud Gateway — Overview Server và Proxy Exchange:** https://docs.spring.io/spring-cloud-gateway/reference/intro.html

> **Khi đối chiếu tài liệu:** Mô tả prose trong một số trang hướng dẫn cũ có thể chưa phân biệt rõ “downstream call” và “downstream response”. Để xác định hướng đi của `header(...)`, đối chiếu **Javadoc, source/API của phiên bản đang chạy** và kiểm thử HTTP ở cả upstream lẫn client.
