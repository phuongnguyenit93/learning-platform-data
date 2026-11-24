# Kiểm tra URI đích và tránh tạo open proxy trong controller

Một API Gateway cần có khả năng chuyển request tới microservice phía sau mà vẫn giữ đúng ranh giới bảo mật. Với **Spring Cloud Gateway Proxy Exchange**, ta có thể đưa tham số `ProxyExchange<byte[]>` trực tiếp vào một controller Spring Web MVC hoặc WebFlux rồi gọi `proxy.uri(...).get()`, `post()` hoặc các phương thức HTTP khác. Sự thuận tiện này cũng mang đến một rủi ro đặc biệt nghiêm trọng: nếu URL đích được lấy trực tiếp từ người dùng, controller có thể trở thành **open proxy**, tạo điều kiện cho **Server-Side Request Forgery (SSRF)**.

Ví dụ, một endpoint `GET /api/proxy?url=...` có vẻ hữu ích để thử các backend. Nhưng nếu controller không giới hạn destination, người ngoài có thể khiến Gateway gửi request tới địa chỉ mà họ không thể truy cập trực tiếp: dịch vụ quản trị nội bộ, API metadata của cloud, loopback hoặc một hệ thống khác. Nếu controller còn vô tình chuyển tiếp cookie, access token hoặc các header định danh, sự cố có thể chuyển từ lỗi định tuyến thành **rò rỉ credentials và vượt ranh giới phân quyền**.

Bài thuộc chương **Proxy Exchange** của module **SPRING_CLOUD_GATEWAY**. Trong bối cảnh xây dựng API Gateway bằng route predicates, filter chain, biến đổi đường dẫn/header, service discovery, xác thực, rate limiting, circuit breaker, retry, TLS và quan sát request, **kiểm soát URI đích** là một ranh giới bắt buộc khi dùng controller để proxy.

**Mục tiêu học tập:**

1. Phân biệt **Gateway Server** và **Proxy Exchange**, cùng API Web MVC/WebFlux tương ứng.
2. Nhận biết **open proxy**, SSRF, confused deputy và các đường vượt kiểm tra URI thông dụng.
3. Thiết kế nguyên tắc **client chỉ được chọn dữ liệu nghiệp vụ; server quyết định scheme/host/port**.
4. Xây URI an toàn từ **base URL cố định**, path segments hợp lệ và query parameters được allowlist.
5. Kiểm tra chính sách đích đến với URL động đặc biệt: redirect, DNS rebinding, IP thực, TLS/SNI và egress.
6. Bảo vệ `Authorization`, `Cookie`, `Host`, `Forwarded` và các hop-by-hop headers.
7. Viết controller MVC/WebFlux minh họa, kiểm thử trường hợp bị từ chối mà **không gửi outbound request**.
8. Kết hợp authentication, authorization, timeout, retry, circuit breaker và observability để vận hành an toàn.

> **Phạm vi phiên bản:** Bài dùng **Spring Cloud Gateway Proxy Exchange**, có hai artifact `spring-cloud-gateway-proxyexchange-webmvc` và `spring-cloud-gateway-proxyexchange-webflux` theo tài liệu Gateway 4.3/5.x. Đây là *một phong cách gateway thay thế* sử dụng controller có annotation, **không phải** Gateway Server Web MVC hoặc Server WebFlux với route predicate/filter chain tự động. Những filter/configuration của Gateway Server không mặc nhiên bảo vệ mọi `ProxyExchange` controller; phải triển khai chính sách tương ứng trong controller, Spring Security, HTTP client và mạng.

## 1. Proxy Exchange làm gì?

Tài liệu Spring Cloud Gateway mô tả `ProxyExchange` như một đối tượng tiện ích dùng trong **regular Spring web handler**:

```java
// Mẫu khái niệm theo tài liệu chính thức (MVC).
@GetMapping("/test")
public ResponseEntity<?> proxy(ProxyExchange<byte[]> proxy) {
    return proxy.uri("https://backend.example/api/image/png").get();
}
```

Với **WebFlux**, phương thức controller thường trả:

```java
// Mẫu khái niệm (WebFlux), không phải servlet controller.
@GetMapping("/test")
public Mono<ResponseEntity<?>> proxy(ProxyExchange<byte[]> proxy) {
    return proxy.uri("https://backend.example/api/image/png").get();
}
```

`uri(...)` **chọn đích outbound** và `get()` **thực hiện HTTP GET** tới đích đó. Bản thân `ProxyExchange` không thể biết URL này có thuộc một backend mà chủ hệ thống cho phép hay không.

### Hai artifact đúng

```xml
<!-- Dành cho Spring Web MVC / Servlet -->
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-gateway-proxyexchange-webmvc</artifactId>
</dependency>

<!-- Hoặc, không dùng đồng thời chỉ vì tên đều là Gateway:
     Dành cho Spring WebFlux / Reactive -->
<dependency>
  <groupId>org.springframework.cloud</groupId>
  <artifactId>spring-cloud-gateway-proxyexchange-webflux</artifactId>
</dependency>
```

Chọn dependency theo stack Spring Boot và **BOM Spring Cloud tương thích**. Ở các bản cũ, bạn có thể gặp tên artifact `spring-cloud-gateway-mvc`/`spring-cloud-gateway-webflux`; tài liệu hiện hành dùng tên `proxyexchange-*`.

### Phân biệt với Gateway Server

| Câu hỏi | Gateway **Proxy Exchange** | Gateway **Server Web MVC/WebFlux** |
| --- | --- | --- |
| Route được quyết định ở đâu? | Annotation/controller và logic ứng dụng | Route definition + predicate/handler mapping |
| URL upstream do ai đặt? | Code gọi `proxy.uri(...)` | Route URI, filter chain, load balancing |
| Lập trình HTTP | Controller `@GetMapping`, `@PostMapping` | Filters/RouterFunctions tùy sản phẩm |
| API chính | `ProxyExchange<T>` | `GatewayFilter`/`GlobalFilter` hoặc `HandlerFilterFunction` |
| Kiểm soát destination | Controller phải giữ policy chặt | Route source/control plane cũng cần bảo vệ |
| Hỗ trợ `forward()` nội bộ | Bản **MVC** có hỗ trợ | Cơ chế forward riêng tùy Gateway Server |
| Tự được hưởng Retry/RateLimiter của Gateway Server? | **Không mặc định** | Có thể cấu hình theo route và filter có sẵn |
| Dùng khi nào? | Một số endpoint BFF/proxy tùy chỉnh, mapping nghiệp vụ cụ thể | Cổng vào chung với nhiều routes/policies |

**Điểm mấu chốt:** Một controller dùng `ProxyExchange` không trở thành gateway an toàn chỉ vì ứng dụng có chữ “gateway” trong dependency. Nó vẫn là một HTTP client chạy với quyền mạng của server.

## 2. Open proxy và SSRF: liên quan nhưng không đồng nghĩa

**Open proxy** là endpoint cho phép người dùng khiến máy chủ chuyển request tới **đích tùy ý**, thường không yêu cầu quyền hoặc không có giới hạn hợp lý.

**SSRF** là hành vi làm server gửi request tới địa chỉ không được phép bằng cách điều khiển tham số như URL, host, path, redirect hoặc DNS. SSRF có thể xảy ra dù endpoint không phải một open proxy hoàn chỉnh.

```mermaid
flowchart LR
    A["Client không tin cậy"] -->|"url do client chọn"| G["Controller + ProxyExchange"]
    G -->|"HTTP client của Gateway"| P["Một đích tùy ý"]
    P --> I["API nội bộ"]
    P --> M["Cloud metadata / token service"]
    P --> E["Hệ thống bên ngoài"]
    I --> G
    M --> G
    E --> G
    G -->|"Response bị proxy trả về"| A
```

Hậu quả có thể bao gồm:

- Truy cập tài nguyên trên **loopback** (`127.0.0.1`/`::1`) hoặc mạng nội bộ không mở cho Internet.
- Tác động các endpoint quản trị hoặc metadata service cấp credentials.
- Quét cổng, nhận diện dịch vụ bằng status/latency, dù không đọc được toàn bộ body.
- Dùng địa chỉ IP của Gateway để vượt network allowlist ở dịch vụ khác.
- Chuyển tiếp nhầm `Authorization` hoặc cookie của user/Gateway tới một host do attacker kiểm soát.
- Proxy trả HTTP response chứa thông tin cấu hình/PII cho người gọi không có quyền.

Một controller có **domain allowlist sai** vẫn có thể SSRF thông qua redirect hoặc DNS rebinding. Vì vậy cần nhiều lớp bảo vệ, không chỉ một phép `String.startsWith(...)`.

## 3. Anti-pattern rõ nhất: nhận URL rồi gọi proxy.uri()

Không viết endpoint công khai như sau:

```java
// KHÔNG AN TOÀN — chỉ dùng để nhận diện lỗ hổng.
@GetMapping("/api/proxy")
public ResponseEntity<?> unsafe(
        @RequestParam String url,
        ProxyExchange<byte[]> proxy) {

    return proxy.uri(url).get();
}
```

Trong ví dụ này, client quyết định **scheme, host, port, path và query**. Chính server sẽ gửi outbound request đến URL đã chọn.

```text
GET /api/proxy?url=https://catalog.example/items/42

Nếu thiếu kiểm soát, cùng API cũng có thể bị dẫn tới:
  localhost / loopback
  một service quản trị nằm trong private network
  một metadata endpoint trong cloud
  một host bên ngoài do attacker quản lý
```

**Không cần** triển khai một HTTP CONNECT proxy mới tạo ra open proxy. Chỉ một `GET` controller có khả năng trả response từ địa chỉ tùy ý đã đủ làm Gateway thành cầu nối không đáng tin.

### Các biến thể cũng nguy hiểm

```java
// KHÔNG AN TOÀN: thay URL bằng host do client chọn.
proxy.uri("https://" + request.getParameter("host")
    + "/v1/items/42").get();

// KHÔNG AN TOÀN: tin một header client tự đặt.
proxy.uri(request.getHeader("X-Target-Url")).get();

// KHÔNG AN TOÀN: "base URL" nhưng path có thể bị xử lý lại thành URI.
proxy.uri(baseUri.resolve(untrustedSuffix).toString()).get();
```

Với `URI.resolve(...)`, suffix bắt đầu bằng `//` là **network-path reference**, có thể thay authority; suffix có `../` có thể vượt đường dẫn gốc. Đây là lý do **không** coi “đã nối với base URI” là đã khóa được host/path.

**Cách sửa tốt nhất:** **Không cho client đưa URL/host**. Cho client đưa một **mã tài nguyên**, một **bí danh dịch vụ** hoặc một tập query parameters nhỏ đã validate, rồi server tự dựng đích cố định.

## 4. Thiết kế ranh giới tin cậy trước khi viết code

Xác định rõ những dữ liệu đến từ đâu:

| Đầu vào | Mức tin cậy | Dùng cho gì? |
| --- | --- | --- |
| `@PathVariable sku` | Không tin cậy | Chỉ là **mã sản phẩm** sau validation |
| `@RequestParam locale` | Không tin cậy | Chỉ nhận `vi`/`en` theo allowlist |
| `@RequestHeader Host` | Không tin cậy | Không dùng quyết định backend |
| `X-Forwarded-Host` / `Forwarded` | Không tin nếu chưa qua trusted proxy chain | Không được dùng tạo `proxy.uri` |
| `@RequestParam url` | Không tin cậy | **Không chấp nhận** như destination |
| Tenant/user ID từ JWT đã verify | Ngữ cảnh đã xác thực nhưng vẫn cần policy | Kiểm tra quyền; không tùy ý tạo hostname |
| URI cố định trong config có kiểm soát | Tin theo deployment pipeline | Chọn backend, nhưng vẫn cần network/TLS guard |
| Service registry nội bộ | Tin có điều kiện | Phải giới hạn service IDs/instances được phép |
| Backend trả `Location` redirect | Không tự tin | Không tự follow sang đích ngoài allowlist |
| DNS response | Tin có điều kiện | Phải xét IP thực và thời điểm kết nối |

**Nguyên tắc ưu tiên:**

1. **Client gửi ý định nghiệp vụ**, không gửi thông tin định tuyến mạng.
2. **Server ánh xạ** ý định đó sang một destination đã biết.
3. **URI builder** encode riêng từng path segment/query value.
4. **HTTP client** được cấu hình không tự theo redirect ngoài chính sách.
5. **Network egress** chỉ cho những đích đã phê duyệt.
6. **Backend** vẫn kiểm tra authorization trên tài nguyên, không tin Gateway vô điều kiện.

## 5. Mô hình đích cố định: client chỉ truyền SKU

Một endpoint chuyên biệt có thể nhận:

```http
GET /api/catalog/items/sku-42?locale=vi HTTP/1.1
Host: api.example.com
```

Nhưng outbound request do **server** tạo là:

```http
GET /v1/items/sku-42?locale=vi HTTP/1.1
Host: catalog.internal.example:8443
```

Không có tham số `url`, `scheme`, `host`, `port` hay `redirect` trong public contract.

```mermaid
flowchart TD
    R["GET /api/catalog/items/{sku}?locale=vi"] --> V["Validate SKU + locale"]
    V --> T{"Dữ liệu hợp lệ?"}
    T -- "Không" --> X["400 Bad Request<br/>không outbound"]
    T -- "Có" --> B["Dùng base URI từ config tin cậy"]
    B --> U["Append pathSegment + queryParam<br/>encode"]
    U --> N["ProxyExchange.uri(target).get()"]
    N --> P["catalog-service đã phê duyệt"]
```

Ví dụ **Spring Web MVC** dưới đây sử dụng `ProxyExchange` đúng theo controller style, tránh lấy đích từ client.

## 6. Java MVC controller: URI do server tự quyết định

Ví dụ có các giả định:

- `CATALOG_BASE` là cấu hình do operator kiểm soát; ở đây viết cố định để làm rõ trust boundary.
- Backend phục vụ `GET /v1/items/{sku}`.
- SKU chỉ gồm chữ, số và dấu gạch ngang, dài 1–40 ký tự.
- Locale chỉ nhận `vi` hoặc `en`; không cho query keys khác đi downstream.
- Controller chỉ hỗ trợ GET, không phải proxy mọi methods.

```java
package example.gateway.proxy;

import java.net.URI;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;

@RestController
public class CatalogProxyController {

    // Trong production: lấy từ typed configuration được deploy/review,
    // không lấy từ query/header do client truyền.
    private static final URI CATALOG_BASE =
        URI.create("https://catalog.internal.example:8443");

    private static final Pattern SAFE_SKU =
        Pattern.compile("[A-Za-z0-9-]{1,40}");

    private static final Set<String> LOCALES =
        Set.of("vi", "en");

    @GetMapping("/api/catalog/items/{sku}")
    public ResponseEntity<?> findItem(
            @PathVariable String sku,
            @RequestParam(defaultValue = "vi") String locale,
            ProxyExchange<byte[]> proxy) {

        if (!SAFE_SKU.matcher(sku).matches()
                || !LOCALES.contains(locale)) {
            return ResponseEntity.badRequest().build();
        }

        URI target = UriComponentsBuilder
            .fromUri(CATALOG_BASE)
            .pathSegment("v1", "items", sku)
            .queryParam("locale", locale)
            .build()
            .encode()
            .toUri();

        // URL không phụ thuộc Host/X-Forwarded-Host hay "url" của client.
        return proxy.uri(target.toASCIIString()).get();
    }
}
```

### Những điểm kiểm soát có chủ đích

- `@PathVariable sku` là **một mã nghiệp vụ**, không phải path tùy ý.
- `SAFE_SKU` loại dấu `/`, `\`, `:`, `?`, `#`, `%`, khoảng trắng và các ký tự điều khiển trong giá trị SKU sau khi Spring binding.
- `UriComponentsBuilder.pathSegment(...)` biểu diễn rõ path segments cần gửi và encode theo URI semantics.
- `CATALOG_BASE` không lấy từ request, cho phép cấu hình đích trong deployment process.
- `locale` theo allowlist; controller **không** tự copy toàn bộ raw query string sang backend.
- API chỉ GET và không có `@RequestMapping("/**")` bắt tất cả verbs.

**Giới hạn của snippet:** Đây là **mẫu chọn đích**, chưa phải toàn bộ cấu hình production: vẫn cần SecurityFilterChain, network egress, TLS verification, timeout, response header policy và HTTP redirect policy. Regex SKU đủ cho mô hình mã sản phẩm đơn giản; với tài nguyên có Unicode/segments phức tạp, hãy xây parser/URI builder chuyên biệt và test double encoding.

### Đọc base URI từ configuration

Với production, không hard-code môi trường dev/prod vào source. Có thể dùng:

```yaml
app:
  upstreams:
    catalog:
      base-uri: https://catalog.internal.example:8443
```

Sau đó bind bằng `@ConfigurationProperties` kiểu URI, kiểm tra **ngay lúc khởi động**: scheme, host, port và path prefix phải khớp allowlist của môi trường. Quan trọng: **operator thay đổi base-uri là thay đổi bảo mật**, cần review/audit như code, không để một public admin endpoint sửa tùy ý.

Không dùng `@Value("${app.upstreams.catalog.base-uri}")` để lấy một giá trị client có thể cập nhật thông qua dữ liệu nghiệp vụ.

## 7. WebFlux controller: cùng policy, khác return type

Proxy Exchange có biến thể WebFlux cho một `@RestController` bình thường. Ở đây **không** dùng `GlobalFilter`/`ServerWebExchange` của Gateway Server; controller vẫn quyết định URI một cách tường minh.

```java
// Mẫu WebFlux: import ProxyExchange từ artifact proxyexchange-webflux
// của Spring Cloud Gateway tương ứng với release train.
@RestController
class CatalogProxyWebFluxController {

    private static final URI CATALOG =
        URI.create("https://catalog.internal.example:8443");

    private static final Pattern SKU =
        Pattern.compile("[A-Za-z0-9-]{1,40}");

    @GetMapping("/api/catalog/items/{sku}")
    Mono<ResponseEntity<?>> find(
            @PathVariable String sku,
            ProxyExchange<byte[]> proxy) {

        if (!SKU.matcher(sku).matches()) {
            return Mono.just(ResponseEntity.badRequest().build());
        }

        URI target = UriComponentsBuilder.fromUri(CATALOG)
            .pathSegment("v1", "items", sku)
            .build()
            .encode()
            .toUri();

        return proxy.uri(target.toASCIIString()).get();
    }
}
```

**Khác biệt MVC/WebFlux:**

- MVC `get()` trả `ResponseEntity<?>`.
- WebFlux `get()` trả `Mono<ResponseEntity<?>>`.
- WebFlux không nên gọi `block()` để validate DNS hoặc HTTP trong event loop.
- Cùng một chính sách URL phải dùng ở **cả hai stacks**; đổi sang reactive không tự làm SSRF biến mất.
- Kiểm tra import `ProxyExchange`/API chính xác theo artifact đã chọn; không trộn `org.springframework.cloud.gateway.mvc.ProxyExchange` của MVC vào WebFlux controller.

Đừng đổi một controller thành WebFlux chỉ vì muốn thêm Spring Cloud Gateway Server WebFlux filters. Đây là hai phong cách chạy khác nhau và cần đánh giá dependency/auto-configuration riêng.

## 8. Nhiều upstreams: dùng alias, không nhận host

Một ứng dụng BFF có thể gọi vài backend, chẳng hạn `catalog` và `inventory`. Thay vì:

```http
GET /api/fetch?host=inventory.internal.example&path=...
```

cho client chọn một alias có giới hạn, còn server ánh xạ từ alias sang URI cấu hình **không thể thay bởi request**:

```java
private static final Map<String, URI> TARGETS = Map.of(
    "catalog", URI.create("https://catalog.internal.example:8443"),
    "inventory", URI.create("https://inventory.internal.example:8443")
);

// Chỉ chọn từ danh sách server quản trị.
URI base = TARGETS.get(alias);
if (base == null) {
    return ResponseEntity.badRequest().build();
}

// Sau đó áp dụng path mẫu riêng cho alias, KHÔNG lấy raw URL.
```

Đây là **mảnh triển khai** cho controller MVC; cần imports `Map`, `URI` và response handling khi đưa vào lớp hoàn chỉnh.

**Tại sao alias hữu ích?**

1. Client không biết/truyền hostname nội bộ.
2. Mỗi alias có thể có **path/method allowlist khác nhau**.
3. Mỗi backend có HTTP client/TLS/timeout/credential policy riêng.
4. Dễ áp dụng **RBAC**: user được xem catalog không mặc định được gọi inventory admin.
5. Dễ lập metrics theo alias với cardinality hữu hạn.
6. Khi hostname thay đổi qua deploy/discovery, public contract không đổi.

Tuy nhiên, alias **không tự là quyền truy cập**. Một client gửi `alias=inventory` phải được authorization theo business use case và resource; không dùng một map chung để mở mọi endpoint admin của inventory.

## 9. Kiểm tra URI đầy đủ: chỉ là lớp phụ, không phải phương án ưu tiên

Có trường hợp hệ thống thật sự phải nhận một URL từ **quản trị viên đáng tin** (ví dụ đăng ký một webhook destination). Khi đó cần validation nghiêm ngặt, nhưng nên cô lập chức năng khỏi public BFF proxy.

### Checklist cấp URI

| Thành phần | Kiểm tra cần có |
| --- | --- |
| Scheme | Chỉ `https` hoặc scheme đã được policy cho phép; từ chối `file`, `ftp`, `gopher`, `jar`, custom schemes |
| Host | Tên miền **exact allowlist** hoặc alias cố định; không dùng `contains`/`endsWith` sai |
| Port | Một trong các port cụ thể, ví dụ `443` hoặc `8443` |
| Userinfo | Từ chối URI có `user:pass@host` |
| Fragment | Từ chối; nó không phải phần HTTP request gửi tới server |
| Opaque URI | Từ chối nếu không phải hierarchical HTTP(S) URI |
| Path | Mẫu/segments được phép, không chấp nhận toàn bộ path tùy ý |
| Query | Chỉ các key/value đã định nghĩa, với size/length limit |
| Redirect | Không tự follow hoặc **revalidate từng hop** |
| DNS/IP | IP đích thực tế được phép, chống rebinding và TOCTOU |
| TLS | Kiểm tra hostname, certificate, SNI và không tắt verification |
| Egress | NetworkPolicy/firewall chặn đích không được cấp phép |
| Headers | Không gửi secret hoặc identity headers tới đích không tin |

**Thứ tự ưu tiên:** Nếu có thể, thay vì kiểm tra một URL do client nhập, chỉ nhận **host/service alias đã allowlist** và tự xây URL từ scheme, port, path đã cố định. OWASP nhấn mạnh **không nên nhận URL đầy đủ từ user** vì rất khó kiểm chứng parser/canonicalization.

### Ví dụ một lớp kiểm tra URI cấp ứng dụng

```java
import java.net.URI;
import java.util.Locale;
import java.util.Set;

final class TrustedDestinationPolicy {

    private static final Set<String> ALLOWED_HOSTS =
        Set.of("catalog.internal.example",
               "inventory.internal.example");

    static URI validateAdministrativeUri(URI uri) {
        if (uri == null || !uri.isAbsolute() || uri.isOpaque()) {
            throw new IllegalArgumentException("Invalid URI");
        }

        String scheme = uri.getScheme();
        String host = uri.getHost();

        if (!"https".equalsIgnoreCase(scheme)
                || host == null
                || !ALLOWED_HOSTS.contains(
                    host.toLowerCase(Locale.ROOT))
                || uri.getPort() != 8443
                || uri.getRawUserInfo() != null
                || uri.getRawFragment() != null) {
            throw new IllegalArgumentException("Destination denied");
        }

        return uri;
    }
}
```

**Cảnh báo ngay tại code:** Hàm trên mới kiểm tra **scheme/host/port/userinfo/fragment**, **chưa** kiểm tra path/query, redirects, DNS peer IP và HTTP client behavior. Nó **không phải SSRF firewall hoàn chỉnh**. Trong ứng dụng thật, phải thêm policy path/query và egress enforcement; đơn giản hơn là không cho user đưa URI.

Không trả lại nguyên URI không hợp lệ trong error message công khai — nó có thể chứa credentials hoặc thông tin nội bộ.

## 10. Các phép kiểm tra chuỗi dễ bị vượt qua

Những cách này **không** phải allowlist đích đáng tin cậy:

```java
// ANTI-PATTERN: chuỗi được chọn có thể chỉ bắt đầu bằng host cho phép
if (url.startsWith("https://catalog.internal.example")) {
    proxy.uri(url).get();
}

// ANTI-PATTERN: từ khóa nằm ở đâu cũng được
if (url.contains("catalog.internal.example")) {
    proxy.uri(url).get();
}

// ANTI-PATTERN: chỉ block localhost/127.0.0.1 dạng chữ
if (!url.contains("localhost")) {
    proxy.uri(url).get();
}
```

Những nhóm đầu vào rủi ro cần test ở tầng parser/policy:

- URL có **userinfo**: phần trước `@` không phải host cuối cùng.
- Host trùng tiền tố: `catalog.internal.example.attacker.invalid`.
- Host có dấu chấm cuối, chữ hoa/chữ thường, IDN/Punycode khác quy ước.
- IPv4 biến thể, IPv6 literal, IPv4-mapped IPv6 hoặc NAT64.
- Ký tự `%` và double encoding làm parser ở hai tầng hiểu khác nhau.
- Chuỗi có `\` hoặc ký tự điều khiển khiến các URL parsers diễn giải không thống nhất.
- Redirect từ host hợp lệ sang host không hợp lệ.
- DNS trả địa chỉ hợp lệ khi kiểm tra nhưng trả IP khác khi kết nối.

**Không giải quyết vấn đề bằng một regex URL khổng lồ.** Hãy để `URI`/URI builder parse, kiểm tra từng thành phần theo allowlist, rồi **enforce destination thực tế tại network connection**.

## 11. URI parsing và canonicalization: xem đúng authority

Một URL theo cấu trúc thường có:

```text
scheme://userinfo@host:port/path?query#fragment
        └──────── authority ────────┘
```

Với Java `URI`:

| API | Ý nghĩa |
| --- | --- |
| `getScheme()` | `https` hay scheme khác |
| `getHost()` | Host parser nhận diện, có thể null khi URI không hợp lệ/khó diễn giải |
| `getPort()` | Port explicit, hoặc -1 nếu không ghi |
| `getRawUserInfo()` | Dữ liệu userinfo trước host |
| `getRawPath()` | Path chưa decode |
| `getRawQuery()` | Query chưa decode |
| `getRawFragment()` | Fragment |
| `isOpaque()` | Phân biệt opaque URI với hierarchical HTTP URI |
| `normalize()` | Chuẩn hóa một số `.`/`..` path segments; **không** thay validation bảo mật |

**Phân biệt port -1:** Nếu chính sách chấp nhận HTTPS mặc định, `getPort() == -1` có thể được hiểu là 443 trong một số HTTP clients. Quy định nhất quán: hoặc bắt buộc explicit port, hoặc chuẩn hóa port theo scheme **trước khi so sánh**. Ví dụ ở mục 9 **cố ý yêu cầu 8443**.

### Vì sao IDN và DNS là một vấn đề khác?

Tên miền Unicode có thể chuyển sang Punycode. Nếu hệ thống cho phép domain nhiều ngôn ngữ, cần chính sách chuẩn hóa `IDN.toASCII()`/hostname validation và so sánh với allowlist chuẩn hóa. Không tự chấp nhận mọi domain chỉ vì nó “trông giống” một host hợp lệ.

Ngay cả khi `URI.getHost()` khớp danh sách, địa chỉ IP sau DNS lookup có thể bị attacker kiểm soát nếu DNS/domain không thuộc hệ thống tin cậy. Vì vậy chỉ kiểm tra host text là **chưa đủ** cho các kết nối tới domain bên ngoài.

## 12. Path traversal và việc dùng ProxyExchange.path()

Tài liệu Proxy Exchange có hàm tiện ích `proxy.path("/proxy/path/")` để lấy phần đường dẫn còn lại của request rồi nối tới backend. Nó hữu ích nhưng tạo rủi ro nếu ta coi phần trailing path là **đã được tin cậy**.

Ví dụ trong tài liệu:

```java
@GetMapping("/proxy/path/**")
public ResponseEntity<?> proxyPath(ProxyExchange<byte[]> proxy) {
    String path = proxy.path("/proxy/path/");
    return proxy.uri(home.toString() + "/foos/" + path).get();
}
```

Đoạn trên minh họa **cách sử dụng API**, không phải một chính sách chống SSRF/path traversal đầy đủ. Với một hệ thống cho phép `/**`, attacker có thể cung cấp path chứa các dạng dot-segment, slash mã hóa hoặc tham số đặc biệt.

### Nguy cơ khác nhau

1. **Host escape:** URI có thể đổi host nếu code dùng `URI.resolve(...)` sai với phần user-controlled.
2. **Path escape:** Dù host vẫn cố định, path có thể truy cập endpoint admin trên **cùng backend**, vượt phạm vi `/foos/**` mong muốn.
3. **Double decoding:** Gateway/backend/proxy có thể decode `%2F` hoặc `%2E` nhiều lần, diễn giải path khác nhau.
4. **Parameter pollution:** Query gốc có thể được ghép/forward ngoài allowlist.

**Giải pháp ưu tiên:** mapping tài nguyên cụ thể:

```java
@GetMapping("/api/catalog/items/{sku}")
public ResponseEntity<?> item(
        @PathVariable String sku,
        ProxyExchange<byte[]> proxy) {

    if (!sku.matches("[A-Za-z0-9-]{1,40}")) {
        return ResponseEntity.badRequest().build();
    }

    URI dest = UriComponentsBuilder
        .fromUri(URI.create("https://catalog.internal.example:8443"))
        .pathSegment("v1", "items", sku)
        .build().encode().toUri();

    return proxy.uri(dest.toASCIIString()).get();
}
```

Nếu thật sự phải hỗ trợ paths nhiều segments, chia thành **từng segment được validate/encode**; không dùng nguyên một suffix để `resolve`/nối chuỗi, và đặt deny-by-default cho endpoint admin trên backend. Cần test đường dẫn sau khi được **Servlet container, Spring MVC, proxy và backend** decode/normalize.

## 13. Query parameters: chỉ sao chép những gì API cần

Tránh:

```java
// ANTI-PATTERN: tự ghép raw query string không qua allowlist.
String target = BASE + "/search?" + request.getQueryString();
return proxy.uri(target).get();
```

Raw query có thể chứa:

- Tham số `redirect`, `callback`, `url`, `next` khiến backend thực hiện redirect hoặc outbound call khác.
- `admin=true` hoặc `includeSecrets=true` có nghĩa đặc biệt ở backend nhưng public API không định cho phép.
- Trùng tham số `role=user&role=admin` gây khác biệt do parser lấy giá trị đầu/cuối.
- Query quá dài làm tăng tải logging/upstream hoặc chứa credentials.
- Encoded `&`/`=` làm đổi cách parse khi nối chuỗi/double decode.

### Cách xây query có kiểm soát

```java
@GetMapping("/api/catalog/search")
public ResponseEntity<?> search(
        @RequestParam(defaultValue = "1") int page,
        @RequestParam(defaultValue = "20") int size,
        ProxyExchange<byte[]> proxy) {

    if (page < 1 || page > 1000 || size < 1 || size > 100) {
        return ResponseEntity.badRequest().build();
    }

    URI dest = UriComponentsBuilder
        .fromUri(URI.create(
            "https://catalog.internal.example:8443"))
        .pathSegment("v1", "search")
        .queryParam("page", page)
        .queryParam("size", size)
        .build()
        .encode()
        .toUri();

    return proxy.uri(dest.toASCIIString()).get();
}
```

Nếu client gửi thêm `?url=...`, code trên **không lấy nó làm destination**. Tuy nhiên API nên có chính sách rõ ràng với unknown query parameters (bỏ qua hoặc từ chối) và kiểm thử bằng requests thực.

**Không sao chép headers như `X-Original-URL` hoặc `X-Rewrite-URL` vào quá trình dựng URI**, trừ khi đó là dữ liệu từ thành phần tin cậy theo một hợp đồng bảo mật đã thiết kế.

## 14. Redirect: host ban đầu an toàn vẫn có thể dẫn sang host xấu

Giả sử target ban đầu được allowlist:

```text
https://catalog.internal.example:8443/v1/items/sku-42
```

Backend trả:

```http
HTTP/1.1 302 Found
Location: https://unapproved.example.invalid/collect
```

Nếu HTTP client chạy trong `ProxyExchange` **tự follow redirect**, outbound call tiếp theo có thể tới host khác **mà controller không bao giờ kiểm tra**.

Theo OWASP, nên **tắt tự động theo redirect** cho một HTTP client thực hiện SSRF-sensitive operations, hoặc **validate lại toàn bộ policy** trên **từng hop** trước khi kết nối.

### Kiểm soát bắt buộc

1. Xác định HTTP client/transport thực sự được ProxyExchange MVC/WebFlux sử dụng ở version của bạn.
2. Tắt **automatic redirects** khi thiết kế endpoint fixed destination; không bật follow redirects toàn cục tùy tiện.
3. Nếu nghiệp vụ thật sự cần follow, giới hạn số hops và áp dụng **scheme, hostname, port, path, DNS/IP, TLS** cho từng hop.
4. Không gửi `Authorization`/`Cookie` của host A sang host B chỉ vì nhận được `Location`.
5. Kiểm tra response `Location` trước khi trả cho client nếu response có thể khiến browser tự chuyển sang một domain không được phê duyệt.
6. Test cả `301`/`302`/`303`/`307`/`308`; riêng 307/308 có thể giữ HTTP method/body và nguy hiểm với POST.
7. Không biến redirect loop thành DoS bằng số hops không giới hạn.

**Quan trọng:** Tài liệu ProxyExchange không cho một bảo đảm chung rằng mọi HTTP client ở mọi version đều **tự động không follow redirects**. Phải xác minh cấu hình transport, không mặc định dựa vào behavior của một client khác.

## 15. DNS rebinding, TOCTOU và destination IP thực

Lớp kiểm tra Java thường chạy như sau:

```text
T1: validate host "approved.example" -> allow
T2: HTTP client tự resolve DNS
T3: HTTP client connect tới IP mới
```

Nếu DNS response tại T1 và T2 khác nhau, attacker có thể khiến ứng dụng kiểm tra một IP hợp lệ rồi kết nối vào **loopback/private/link-local**. Đây là **DNS rebinding** và **time-of-check to time-of-use** (TOCTOU).

```mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway controller
    participant D as DNS
    participant H as HTTP client
    participant I as Đích không được phép

    C->>G: Yêu cầu tới alias/URL
    G->>D: Kiểm tra DNS sơ bộ
    D-->>G: IP hợp lệ ở thời điểm T1
    G->>H: Gửi target hostname
    H->>D: Resolve lại ở T2
    D-->>H: IP khác
    H->>I: Connect nếu không có network guard
    Note over G,I: Allowlist chỉ ở T1 chưa đủ
```

**Cách phòng thủ nhiều lớp:**

- Ưu tiên dùng **host/service do tổ chức kiểm soát**, không đưa domain tùy ý vào HTTP client.
- Nếu nhận dynamic domains từ trusted admin, kiểm tra domain/IP address policy, cả **A và AAAA**.
- Không dùng denylist chỉ liệt kê `127.0.0.1`; phải xét **IPv4, IPv6, IP-mapped**, link-local, metadata endpoints và mạng nhạy cảm theo môi trường.
- **Ràng buộc kết nối vào IP đã được validate** ở tầng HTTP client/network khi chức năng thật sự cần external URLs, giữ original hostname cho TLS certificate verification, SNI và `Host` theo chuẩn.
- Không để một DNS lookup **không được kiểm tra lại** xảy ra sau validation.
- Áp policy cho **mọi retry/redirect/failover attempt**, không chỉ attempt đầu.
- Dùng **egress firewall, Kubernetes NetworkPolicy, service mesh policy hoặc proxy egress** theo allowlist, để lỗi code không mở toàn bộ mạng nội bộ.

### Không chặn mọi IP riêng theo cách máy móc

Một microservice nội bộ hợp lệ có thể nằm ở `10.x.x.x` hoặc `172.16–31.x.x`; yêu cầu “block mọi private IP” sẽ phá ứng dụng. Chính sách đúng là **chỉ cho những network/service identities cụ thể mà workload được phép gọi**, không cho client chọn toàn bộ mạng riêng.

**Đừng tắt hostname verification để kết nối trực tiếp IP**. Nếu client cần pin resolved IP, phải cấu hình HTTP client để vẫn xác thực certificate theo hostname gốc và sử dụng SNI đúng; đây là cấu hình cần kiểm thử với phiên bản client thực tế.

## 16. Service discovery và dynamic routes không thay URI validation

Có những ứng dụng Proxy Exchange cần gọi service theo alias/discovery. Nhưng:

- `serviceId` vẫn phải thuộc **allowlist do server quản trị**.
- Registry/ServiceInstanceListSupplier không đồng nghĩa mọi instance đều được phép nhận token hoặc dữ liệu tenant.
- Không nhận `serviceId` tùy ý từ query để gọi bất kỳ service nào trong cluster.
- Cần giới hạn namespace, zone, port và instance metadata theo trust boundary.
- Nếu discovery source bị sửa độc hại, proxy có thể kết nối tới một instance trái phép; policy mạng/identity giúp giảm tác động.

```text
Cho phép:
  "catalog"  -> service identity catalog-service
  "inventory"-> service identity inventory-service

Không cho:
  client truyền bất kỳ service ID trong registry,
  client truyền Pod IP:port,
  client điều khiển scheme/authority qua headers.
```

Khi dùng Gateway Server, một URI `lb://catalog-service` do operator khai báo được phân giải trong filter chain. Với **ProxyExchange**, không tự giả định `proxy.uri("lb://...")` có đầy đủ behavior của Gateway Server; đó là controller utility và transport hỗ trợ theo artifact/version. Khi cần service discovery, thiết kế/kiểm thử cơ chế chọn URI riêng hoặc cân nhắc Gateway Server route chuẩn.

## 17. Header mặc định của ProxyExchange không phải chính sách bảo mật toàn diện

Tài liệu chính thức cho biết `ProxyExchange` có hỗ trợ xử lý:

- **Sensitive headers:** mặc định **`cookie`** và **`authorization`**, không được forward tới downstream theo behavior mặc định.
- **Skipped headers:** mặc định **`content-length`** và **`host`**, không copy nguyên khi gửi outbound.
- **Proxy/forwarded headers:** các header `x-forwarded-*` được xử lý theo cơ chế riêng.
- Các phương thức cho phép thêm header/ánh xạ response.

Điều này **giúp giảm rủi ro mặc định**, nhưng không đồng nghĩa mọi header trong request đều an toàn để forward hay mọi ứng dụng đều giữ default configuration.

### Bảng chính sách header

| Header | Chính sách đề xuất |
| --- | --- |
| `Authorization` | Không chuyển tiếp mặc định; nếu cần TokenRelay/manual token thì chỉ gửi đến backend đã phê duyệt với audience/scope phù hợp |
| `Cookie` | Không forward cookie trình duyệt cho upstream không có quyền; tránh lộ session |
| `Host` | HTTP client tự tạo đúng authority; không dùng raw Host client làm target |
| `Content-Length` | Để HTTP client tính lại khi body thay đổi; tránh framing lỗi |
| `Connection`, `Transfer-Encoding`, `TE`, `Upgrade` | Hop-by-hop; không chuyển tiếp mù quáng |
| `Proxy-Authorization` | Không copy credential của proxy |
| `Forwarded`, `X-Forwarded-*` | Chỉ tin các proxy đã xác minh; sanitize/rewrite theo topology |
| `X-User-Id`, `X-Tenant-Id`, `X-Roles` | Không tin giá trị client tự đặt; tạo lại sau xác thực nếu backend contract cần |
| `X-Request-Id` / trace context | Chuẩn hóa, giới hạn chiều dài, không dùng làm auth |
| `Origin` | Dùng cho CORS/browser policy; không phải một nguồn identity đáng tin |
| `Accept` / `Content-Type` | Forward có kiểm soát theo API; đặt đúng types và limits |

**Không mở rộng `sensitive headers` theo hướng cho phép `Authorization` đi vào mọi upstream**. Một access token chỉ có ý nghĩa trong một trust boundary/audience nhất định. Nếu bắt buộc pass token, đưa quyết định vào policy riêng và test cả tình huống request redirect.

### Header spoofing ở trust boundary

Client có thể tự đặt:

```http
X-Forwarded-Host: admin.internal.example
X-Forwarded-Proto: https
X-User-Id: superuser
```

Không có gì bảo đảm các giá trị đó do ingress đáng tin tạo ra. Vì vậy, **không dùng chúng để dựng URI outbound hoặc cấp quyền**. Tại trusted edge, cần loại bỏ giá trị client tự đặt và chỉ tạo lại bằng thông tin đã được kiểm chứng; nếu nhiều proxy, định nghĩa rõ chain và parser.

## 18. Response cũng có thể trở thành kênh rò rỉ

Giới hạn outbound destination mới giải quyết **một nửa** vấn đề. Nếu một backend đáng tin trả dữ liệu nhạy cảm và controller trả nguyên response cho caller chưa đủ quyền, Gateway vẫn là đường rò rỉ.

Kiểm tra:

- **Status/body:** chỉ proxy những tài nguyên caller được phép đọc.
- **`Location`:** response redirect tới host ngoài policy có thể chuyển browser sang trang phishing hoặc lộ token trong URL.
- **`Set-Cookie`:** cookie của backend có Domain/Path/SameSite/Secure không phù hợp với domain Gateway.
- **`WWW-Authenticate`:** có thể tiết lộ issuer/realm/service topology; thiết kế error contract.
- **CORS headers:** không cho upstream tùy ý mở `Access-Control-Allow-Origin: *` cho API có credentials.
- **Cache headers:** `Cache-Control: no-store` khi response có PII/token, tránh cache lẫn tenants.
- **Content-Type:** không phản chiếu HTML/JavaScript không tin cậy tại cùng origin nếu API contract chỉ cần JSON.
- **Server/trace/internal headers:** không trả stack trace, hostname, internal path hay credentials.
- **Content length/encoding:** khi transform body, tính lại framing; không copy nguyên `Content-Length` sai.

Tài liệu ProxyExchange có khả năng truyền **response mapper** vào `get()` và các verbs khác để biến đổi `ResponseEntity` trước khi trả client. Đây là vị trí có thể áp dụng **response header allowlist/sanitization** theo API, bên cạnh security ở backend.

**Đừng** chỉ thêm response header `X-Proxy-Safe: true` rồi coi là đã chặn SSRF. Sự an toàn phụ thuộc vào outbound destination, HTTP client và quyền đọc dữ liệu, không phải một dấu hiệu do ứng dụng tự đặt.

## 19. Authentication, authorization và tenant isolation

Một controller proxy thường chạy với quyền mạng rộng hơn client. Đây là mô hình **confused deputy**: server có quyền gọi backend, nhưng phải kiểm tra client có quyền **yêu cầu server thực hiện call đó** không.

```mermaid
flowchart TD
    U["User / client"] --> A["Spring Security<br/>verify token/session"]
    A --> B{"Được phép dùng endpoint + resource?"}
    B -- "Không" --> X["401 / 403, không proxy"]
    B -- "Có" --> C["Validate alias/SKU/query"]
    C --> D["Build allowlisted URI"]
    D --> E["Outbound credential policy"]
    E --> F["Backend validate resource authorization"]
```

### Tách ba loại quyền

1. **Quyền gọi endpoint public:** user được truy cập `/api/catalog/items/**`?
2. **Quyền đọc resource:** user/tenant có được xem SKU/dữ liệu tương ứng?
3. **Quyền Gateway gọi upstream:** controller có được dùng service identity/credential của backend đó?

Một user có `ROLE_VIEWER` không được tự thay host thành `billing-admin.internal`, ngay cả nếu `billing-admin` là host nằm trong private network cùng tổ chức.

### Access token và ProxyExchange

Mặc định ProxyExchange không forward `Authorization`/`Cookie` theo chính sách sensitive headers được tài liệu nêu. Nếu backend cần identity:

- Dùng mô hình **OAuth2 TokenRelay/token exchange** phù hợp ở tầng Security, không tự bỏ mọi hạn chế headers.
- Chỉ gửi token tới backend trust domain và audience được phê duyệt.
- Nếu dùng service-to-service token, backend vẫn cần thông tin user/tenant có xác thực và kiểm tra quyền tương ứng.
- Không trộn cookie session của Gateway với access token của backend.
- Không tin `X-Tenant` do client tự chọn nếu không ràng với principal đã xác thực.

**TokenRelay của Gateway Server filter không mặc định chạy trên một ProxyExchange controller.** Nếu dùng cả hai sản phẩm trong cùng ứng dụng, phải biết luồng nào đi qua filter chain nào.

## 20. HTTP methods, request body, streaming và giới hạn tài nguyên

Một open proxy có thể bị lợi dụng không chỉ để GET. Nếu controller cho phép arbitrary verbs và body:

- `POST` có thể kích hoạt tác vụ ghi ở hệ thống quản trị nội bộ.
- `PUT`/`PATCH` có thể sửa resource trái phép.
- `DELETE` có thể xóa dữ liệu.
- Multipart upload/large body có thể tiêu thụ bộ nhớ.
- Streaming vô hạn làm chiếm connection/thread/buffer.
- Retry lên request ghi có thể nhân side effects.

**Chọn mapping hẹp:**

```java
// Nên tạo endpoint đọc rõ ràng:
@GetMapping("/api/catalog/items/{sku}")

// Không chọn cách này khi chưa có policy mạng/nghiệp vụ riêng:
@RequestMapping(value = "/proxy/**", method = {
    RequestMethod.GET, RequestMethod.POST,
    RequestMethod.PUT, RequestMethod.DELETE
})
```

### Giới hạn cần đặt

| Loại tài nguyên | Giới hạn |
| --- | --- |
| Request body | Kích thước tối đa theo endpoint, content type allowlist |
| Response body | Dung lượng tối đa/stream policy; không buffer vô hạn |
| HTTP client | Connect/read/response timeout, connection pool, max connections |
| Redirect | Tắt follow hoặc giới hạn hop + validate lại |
| Retry | Chỉ transient errors, method idempotent, số attempts nhỏ |
| Concurrency | Thread pool/connection pool/backpressure phù hợp |
| Rate limit | Theo user/tenant/alias, không cho abuse gateway network |
| URI | Path/query length, số segments, ký tự hợp lệ |
| Logging | Giới hạn body, headers, token redaction |
| Egress | Destination network/service allowlist |

Với MVC, các cuộc gọi HTTP blocking có thể giữ Servlet worker threads; với WebFlux, tránh các thao tác blocking trên event loop. ProxyExchange là tiện ích HTTP; không tự đảm bảo một response lớn được streaming với memory usage bằng 0. Đo và test transport thực tế.

## 21. Timeout, Retry và CircuitBreaker không thay thế URI policy

Một số đội cố “bảo vệ” open proxy bằng cách đặt timeout 1 giây. Điều đó không chặn SSRF — một endpoint metadata/local thường phản hồi chỉ trong vài mili giây.

**Phân biệt chức năng:**

| Cơ chế | Giúp điều gì? | Không giúp điều gì? |
| --- | --- | --- |
| URI allowlist | Giới hạn đích được phép | Không tự chặn DNS rebinding/redirect |
| Egress NetworkPolicy | Chặn kết nối đến network bị cấm | Không kiểm tra user có quyền xem dữ liệu |
| Connect/response timeout | Giới hạn chờ khi upstream chậm | Không cấm gửi request tới đích sai |
| Retry | Khôi phục lỗi tạm thời | Có thể nhân số SSRF attempts nếu policy sai |
| CircuitBreaker | Giảm calls khi dependency lỗi kéo dài | Không xác định host có được phép không |
| RateLimiter | Giảm số requests do client gửi | Không biến URL bất kỳ thành an toàn |
| TLS verification | Xác minh kết nối tới hostname được chỉ định | Không xác định hostname đó có đúng business policy |
| Authentication | Xác minh caller | Caller đã login vẫn có thể lạm dụng URL do họ chọn |
| Observability | Phát hiện hoạt động lạ | Không chặn request đầu tiên |

Nếu áp dụng retry:

- **Validate destination trước mọi attempt** khi đích có thể thay đổi.
- Nếu có redirect/failover/re-resolve DNS, enforce policy tại **connection**.
- Không cho retry `POST`/`DELETE` tùy tiện.
- Đặt end-to-end deadline và budget, tránh SSRF làm Gateway kiệt thread/connections.
- CircuitBreaker/Retry của Gateway Server không tự bọc `ProxyExchange`; dùng các HTTP client controls và resilience integration thực tế có trong controller.

## 22. Lab local: proxy một backend cố định thay vì nhận URL tùy ý

Môi trường minh họa:

- Controller `ProxyExchange` chạy ở `http://localhost:8080`.
- Backend test hợp lệ ở `http://127.0.0.1:18081`.
- Backend có `GET /v1/items/{sku}`, trả JSON marker.
- Controller chỉ cho GET `/api/catalog/items/{sku}`.

**Trong lab**, base URI có thể cố định là loopback:

```java
private static final URI TEST_BACKEND =
    URI.create("http://127.0.0.1:18081");
```

**Tại sao đây không mâu thuẫn với SSRF guidance?** Loopback ở đây là **đích cố định được operator cấu hình** để thử nghiệm trên máy cá nhân; client không thể chọn port/host. Trong production, loại bỏ loopback test và dùng service identity/URI được phê duyệt.

Backend stub:

```java
package example.backend;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogStubController {

    @GetMapping("/v1/items/{sku}")
    public Map<String, String> item(@PathVariable String sku) {
        return Map.of(
            "sku", sku,
            "servedBy", "catalog-test-backend");
    }
}
```

Phải chạy **backend stub ở port 18081** trong ứng dụng khác; controller ProxyExchange chạy port 8080. Đây là mảnh code minh họa, không tự khởi động hai Spring Boot processes trong một file.

### Gọi request hợp lệ

```bash
curl -i \
  "http://localhost:8080/api/catalog/items/sku-42"
```

Kỳ vọng: response do catalog stub trả, chứa `"servedBy":"catalog-test-backend"`. Nếu nhận 404, kiểm tra context path, request mapping, base URI, network và classpath ProxyExchange trước khi mở rộng quyền route.

### Gửi dữ liệu SKU không hợp lệ

```bash
# Khoảng trắng sẽ được URL-encode bởi curl, sau đó binding/validation xử lý.
curl -i \
  "http://localhost:8080/api/catalog/items/bad%20sku"
```

Kỳ vọng: controller trả **400** (hoặc Servlet/router có thể chặn URL không hợp lệ trước controller tùy setting). **Không có outbound request** tới backend stub.

### Thêm query URL “đánh lừa” nhưng không được dùng làm target

```bash
curl -i \
  "http://localhost:8080/api/catalog/items/sku-42?url=http%3A%2F%2F127.0.0.1%3A18082%2Fadmin"
```

Controller mẫu không bind query `url`, nên destination vẫn là backend 18081 và path `/v1/items/sku-42`. Nếu muốn API strict, có thể chủ động trả 400 cho query không được khai báo; điều quan trọng là **không có outbound tới 18082**.

**Chỉ dùng môi trường lab thuộc quyền kiểm soát**, không thử gọi metadata/internal endpoints thật của một hệ thống production để kiểm tra bảo mật.

## 23. Test tự động: chứng minh không có outbound khi input bị từ chối

Unit test một hàm trả boolean “URL hợp lệ” chưa đủ. Cần test cả **controller**, **argument resolver** và **HTTP client thực tế** để xác minh request sai không tạo outbound.

### Test matrix

| Đầu vào | Kết quả cần có | Outbound kỳ vọng |
| --- | --- | --- |
| SKU `sku-42` | Thành công | 1 request tới catalog cho phép |
| SKU có khoảng trắng | 400 | **0** |
| SKU có dấu `/`/dot-segments | 400/404 ở HTTP mapping, theo cấu hình | **0** |
| SKU quá 40 ký tự | 400 | **0** |
| Query `url=http://...` | Bỏ qua hoặc 400 | Không gọi URI trong query |
| Header `X-Target-Url` | Bỏ qua | Không ảnh hưởng đích |
| Header `Host: arbitrary.invalid` | Host không được dùng làm target | Không đổi URI outbound |
| Header `X-Forwarded-Host` giả | Bỏ qua/normalize | Không ảnh hưởng đích |
| Alias không biết | 400/404 | **0** |
| Path được encode hai lần | Không vượt path policy | **0** nếu không hợp lệ |
| Response 302 từ backend | Không tự gọi host ngoài allowlist | Chỉ request tới backend hợp lệ |
| DNS đổi peer IP | Kết nối bị chặn ở client/egress policy | Không có kết nối tới IP cấm |
| Backend timeout | Status lỗi có kiểm soát | Không retry vô hạn |
| User thiếu quyền | 401/403 | **0** |
| Response chứa `Set-Cookie`/`Location` bất thường | Sanitized theo contract | Không rò ra client ngoài dự kiến |

### Ví dụ unit test policy URI

```java
import java.net.URI;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class TrustedDestinationPolicyTest {

    @Test
    void rejectsDifferentHost() {
        URI uri = URI.create(
            "https://unapproved.example.invalid:8443/v1/items/sku-42");

        assertThrows(IllegalArgumentException.class,
            () -> TrustedDestinationPolicy
                .validateAdministrativeUri(uri));
    }

    @Test
    void rejectsUserInfo() {
        URI uri = URI.create(
            "https://user:secret@catalog.internal.example:8443/items");

        assertThrows(IllegalArgumentException.class,
            () -> TrustedDestinationPolicy
                .validateAdministrativeUri(uri));
    }

    @Test
    void rejectsWrongPort() {
        URI uri = URI.create(
            "https://catalog.internal.example:9443/items");

        assertThrows(IllegalArgumentException.class,
            () -> TrustedDestinationPolicy
                .validateAdministrativeUri(uri));
    }

    @Test
    void rejectsNonHttpScheme() {
        URI uri = URI.create(
            "file:///etc/hosts");

        assertThrows(IllegalArgumentException.class,
            () -> TrustedDestinationPolicy
                .validateAdministrativeUri(uri));
    }
}
```

**Test policy này chưa kiểm tra outbound transport.** Phải bổ sung integration tests với mock HTTP server hoặc một backend stub thuộc quyền kiểm soát để xác nhận:

- Host/port thực sự được kết nối.
- Không follow redirect sai.
- Headers nhạy cảm không bị chuyển tiếp.
- Không có request thứ hai khi bị từ chối.
- Không đổi destination sau DNS/retry.
- Không trả response body không có quyền.

Không cần chạy request thật tới cloud metadata endpoint; dùng stub/deny rules kiểm thử tại local network.

## 24. Integration test với MVC và WebFlux

### Spring Web MVC

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP test client hoặc `MockMvc`:

1. Dựng backend stub có recording request count và các headers.
2. Gọi controller với SKU hợp lệ, kiểm tra nhận JSON từ backend.
3. Gọi SKU sai, xác minh `400` và backend counter không tăng.
4. Gửi `Host` và `X-Forwarded-Host` giả, xác minh backend address không đổi.
5. Gửi `Authorization: Bearer test-only`, kiểm tra outbound **không tự forward** theo sensitive policy mặc định.
6. Cho backend trả `302 Location` tới một test-only blocked server, xác minh blocked server counter không tăng.
7. Bật Spring Security trong integration context, kiểm thử caller thiếu quyền không tạo outbound request.
8. Kiểm tra response headers/`Set-Cookie` theo contract trước khi trả client.

`MockMvc` test controller mapping/validation, nhưng request proxy vẫn có thể tạo HTTP call thật tùy cấu hình `ProxyExchangeArgumentResolver`. Đừng kỳ vọng một pure unit test với `MockMvc` tự ngăn outbound; cần HTTP client giả hoặc stub an toàn.

### Spring WebFlux

Dùng `WebTestClient` và backend HTTP stub:

- Test thiếu/đủ authentication.
- Test format SKU + query encode.
- Test concurrent requests và backpressure nếu proxy xử lý body lớn.
- Không dùng `block()` trong controller; chỉ block trong **test code** nếu framework cho phép.
- Nếu có DNS/IP validation bất đồng bộ, kiểm tra thread starvation/cancellation và timeout.

Cả hai stacks phải có **bằng chứng ở network layer** rằng URI đích không thể bị điều khiển bằng query, header hoặc path.

## 25. Egress security: chặn bằng hạ tầng khi code sai

Một gateway có quyền truy cập mạng rộng thường là vị trí nhạy cảm. Dù controller dùng URI cố định, network controls vẫn nên chặn kết nối ngoài các backend được phê duyệt.

```mermaid
flowchart LR
    G["ProxyExchange workload"] --> E["Egress policy / proxy"]
    E -->|"Allow service identity + port"| C["catalog-service"]
    E -->|"Allow service identity + port"| I["inventory-service"]
    E -.->|"Deny"| M["Cloud metadata endpoints"]
    E -.->|"Deny"| A["Arbitrary private admin APIs"]
    E -.->|"Deny"| X["Internet host không phê duyệt"]
```

### Các lớp bảo vệ

| Lớp | Kiểm soát |
| --- | --- |
| Application | Fixed destinations, path/query validation, per-user authorization |
| HTTP client | Redirect policy, TLS verification, timeouts, HTTP method control |
| DNS / service discovery | Trusted resolvers, namespace restrictions, kiểm tra peer IP nếu dynamic |
| Kubernetes/VM network | Egress allowlist tới service subnet/ports, chặn metadata |
| Service mesh | Service identity, mTLS, external service registration |
| Cloud environment | Metadata service hardening, egress security group/firewall |
| Monitoring | Cảnh báo DNS/egress denies, unusual host/port, 4xx/5xx |

**Kubernetes NetworkPolicy thường thao tác theo IP/labels và behavior phụ thuộc CNI**; không tự cho rằng một FQDN allowlist hoạt động trong mọi cluster. Nếu policy dựa FQDN, cần egress gateway/CNI hỗ trợ và test sự thay đổi DNS. Với service nội bộ, cân nhắc identity-based routing/service mesh.

Không cấp outbound toàn Internet cho workload ProxyExchange nếu nghiệp vụ chỉ cần gọi hai microservices nội bộ.

## 26. Observability và điều tra an toàn

Mục tiêu là phát hiện **route/destination bất thường** mà không rò dữ liệu nhạy cảm vào logs.

| Tín hiệu | Nên ghi | Không nên ghi |
| --- | --- | --- |
| Public endpoint | Template `/api/catalog/items/{sku}` | URL có query chứa token |
| Route/alias | `catalog`, `inventory` | Host do client tự nhập chưa validate như metric label |
| Destination | Service ID/host đã phê duyệt ở mức được phép | Raw URI có credentials/query |
| HTTP method | GET/POST theo contract | Request body chứa PII |
| Upstream status | 2xx/4xx/5xx và type of failure | Raw backend error chứa secrets |
| Duration | p50/p95/p99, connect timeout | Raw tokens/cookies |
| Rejected reason | `invalid_sku`, `blocked_target`, `unauthorized` | Payload URL nguyên văn độc hại |
| DNS/egress denied | Số lượng và resource type | Full internal network map ra public response |
| Redirect denied | Hop count, destination category | `Location` có credentials |
| Correlation ID | Chuẩn hóa, chiều dài giới hạn | ID do client chèn quá dài/log injection |

**Metrics labels** nên có cardinality thấp: endpoint template, alias hữu hạn, status, error class. Không dùng mọi hostname, raw user ID hoặc toàn bộ URL làm labels gây memory pressure và lộ PII.

### Alert gợi ý

- Tăng bất thường `blocked_target`/`invalid_path` từ một client.
- Nhiều kết nối bị egress deny tới network không cho phép.
- Số HTTP redirects tăng so với baseline.
- Kết nối tới upstream không nằm trong danh sách service IDs phê duyệt.
- 401/403 tăng ở backend do token bị relay sai audience.
- Timeout/5xx tăng khi có scan-like traffic.
- Proxy controller QPS cao hơn business API thông thường.

Đừng tự động chặn toàn bộ user chỉ vì một lỗi input đơn lẻ; kết hợp rate limits, authentication và điều tra với bằng chứng phù hợp.

## 27. Troubleshooting: lỗi URI và bảo mật thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Client chỉ cần SKU nhưng controller nhận URL | Thiết kế API quá tổng quát | Đổi contract sang resource ID/alias |
| `startsWith` cho phép host lạ | So sánh chuỗi thay vì URI components | Parse và exact allowlist; tốt hơn server-fixed URI |
| Request có Host giả lại đổi destination | Dùng raw `Host`/`X-Forwarded-Host` để build URI | Bỏ input này khỏi target selection |
| URL hợp lệ nhưng sau redirect tới host khác | HTTP client auto-follow | Tắt follow/revalidate hop |
| DNS host đúng nhưng peer IP sai | DNS rebinding/TOCTOU | Enforce connection-time policy + egress |
| Path `../` vào admin endpoint cùng backend | Nối/resolve suffix tùy ý | Path segments allowlist, chuẩn hóa nhất quán |
| Double-encoded path vượt validator | Validation sau 1 lần decode, backend decode lần nữa | Test end-to-end parser pipeline, reject ambiguity |
| `URI.getHost()` null | URI malformed/Unicode/authority mơ hồ | Fail closed, không fallback sang raw string |
| IPv6 hoặc IP-mapped lọt qua denylist | Chỉ check IPv4 text | Dùng policy IP/network chuẩn hóa cả IPv4/IPv6 |
| Body nhạy cảm bị trả cho caller | Thiếu resource authorization | Kiểm tra tenant/resource ở Gateway và backend |
| Proxy gửi cookie/token sang host khác | Sensitive header policy bị nới, redirect | Không forward mặc định, audience + destination check |
| Backend không nhận Host mong muốn | ProxyExchange bỏ Host theo default | Để HTTP client tạo đúng Host/SNI; không copy host client |
| Body lỗi khi POST/multipart | Chuyển body/framing không phù hợp | Chọn HTTP client codec/body limit, không mở proxy tùy ý |
| MVC controller trả Mono lạ | Trộn MVC và WebFlux artifacts | Chọn đúng stack/artifact/API |
| Gateway Server filters không chạy | ProxyExchange controller không đi qua Gateway Server chain | Dùng Servlet/WebFlux security, controller policies riêng |
| Dùng `lb://` nhưng không có route resolution | Giả định ProxyExchange như Gateway Server | Thiết kế/kiểm thử discovery integration hoặc dùng Server flavor |
| TLS handshake error | Sai certificate/SNI/truststore | Sửa trust; không tắt hostname verification |
| Proxy bị chậm dù timeout nhỏ | DNS/pool/redirect/retry có clocks riêng | Đặt deadline + connect/read/pool timeout |
| Gateway hết threads | Nhiều MVC calls/blocking/streaming | Rate/concurrency limits, pool tuning |
| 404 khi SKU hợp lệ | Path builder/backend mapping sai | So sánh outbound path trong stub/log đã redacted |
| Headers `X-Forwarded-*` sai | Trusted proxy chain không chuẩn | Normalize ở edge; không tin client |
| Metric cardinality tăng vọt | Ghi raw URI/hostname/SKU làm label | Dùng route template/alias bounded |
| Sai port trong URI config | Default port không khớp backend | Kiểm tra port explicit/effective config |

### Quy trình tìm nguyên nhân

1. **Lấy public contract:** Client có quyền chọn gì? Có field URL/host không?
2. **Xác minh stack:** ProxyExchange MVC hay WebFlux, package/dependency nào?
3. **Trace target construction:** scheme/host/port đến từ **trusted config** hay request?
4. **Validate path/query:** Có nối raw suffix/query không? Có normalize/double decode?
5. **Quan sát outbound:** Destination thực, redirect hops, DNS-resolved peer IP, SNI/TLS?
6. **Kiểm tra headers:** Authorization/Cookie/Host/Forwarded có bị relay ngoài ý muốn không?
7. **Kiểm tra Security:** Caller có quyền đọc resource/tenant không?
8. **Kiểm tra egress:** Traffic tới admin/metadata networks có bị chặn không?
9. **Test denial:** Input sai có tạo **0 outbound requests** không?
10. **Quyết định sửa:** Ưu tiên thu hẹp API contract, không vá từng payload trong một denylist.

## 28. Bài tập củng cố

### Bài tập 1 — Chỉ ra lỗ hổng

```java
@GetMapping("/fetch")
ResponseEntity<?> fetch(@RequestParam String url,
                        ProxyExchange<byte[]> proxy) {
    return proxy.uri(url).get();
}
```

**Hỏi:** Đâu là ranh giới tin cậy bị vượt?

**Đáp án:** Người dùng chọn URI outbound, trong khi HTTP request xuất phát từ server có quyền mạng nội bộ. Đó là open proxy và điểm vào SSRF.

### Bài tập 2 — Kiểm tra `startsWith`

Controller chỉ cho URL có `startsWith("https://catalog.internal.example")`.

**Hỏi:** Có đủ không?

**Đáp án:** Không. So sánh chuỗi không xác định host thực. Cần tránh URL người dùng, hoặc parse các thành phần URI, so sánh exact allowlist và enforce destination thực tế.

### Bài tập 3 — URI.resolve

```java
URI base = URI.create("https://catalog.internal.example/v1/");
URI dest = base.resolve(userSuppliedSuffix);
```

**Hỏi:** Tại sao cách này không đảm bảo host/path?

**Đáp án:** Suffix có thể là absolute URI hoặc network-path reference, và path có thể chứa dot-segments. Nên dựng URI từ **path segments cố định/đã validate**.

### Bài tập 4 — Header Authorization

Gateway nhận token Bearer từ browser, cần gọi backend inventory.

**Hỏi:** Có nên tự tắt cơ chế sensitive headers để chuyển token cho mọi request?

**Đáp án:** Không. Chỉ forward/token-exchange theo identity, audience, scopes, destination đã phê duyệt và backend authorization. Default ProxyExchange cố ý không forward một số header nhạy cảm.

### Bài tập 5 — Redirect

Host `catalog.internal.example` đã allowlist, nhưng backend trả 302 tới unapproved host.

**Hỏi:** Sau kiểm tra host ban đầu là đủ chưa?

**Đáp án:** Chưa. Tắt auto-follow hoặc validate lại mọi hop, đồng thời chặn bằng egress policy.

### Bài tập 6 — DNS rebind

Validator DNS trả IP cho phép; HTTP client tự resolve lại và nhận IP private khác.

**Hỏi:** Cần làm gì?

**Đáp án:** Enforce kết nối tới IP đã validate, không cho unchecked re-resolution, giữ TLS/SNI theo hostname gốc và dùng network egress allowlist.

### Bài tập 7 — Nhiều upstreams

Client cần chọn catalog hoặc inventory. Bạn có thể cho `?host=...` hay nên dùng `?service=catalog`?

**Đáp án:** Dùng alias `catalog`/`inventory` với server-side mapping, và route-specific authorization; không cho caller quyết định hostname/port.

### Bài tập 8 — Query passthrough

Controller copy nguyên `request.getQueryString()` vào backend.

**Hỏi:** Rủi ro gì?

**Đáp án:** Backend có thể hiểu các tham số admin/redirect ngoài hợp đồng public, trùng tham số hoặc encoded separators. Chỉ build query parameters được allowlist.

### Bài tập 9 — Xác minh test

Unit test cho `TargetPolicy` đã pass, nhưng không có test HTTP client.

**Hỏi:** Đã chứng minh không SSRF chưa?

**Đáp án:** Chưa. Cần integration test với backend/blocked-server stub để chắc chắn không tạo outbound tới host sai, bao gồm redirect và DNS/IP enforcement.

### Bài tập 10 — ProxyExchange hay Gateway Server?

Ứng dụng cần định tuyến hàng trăm routes và quản lý rate limit/circuit breaker/retry theo định nghĩa route.

**Hỏi:** Có nên tự viết một `@RequestMapping("/**")` kết hợp `ProxyExchange`?

**Đáp án:** Thường không. Gateway Server flavor có route predicates/filter factories phù hợp hơn; dùng ProxyExchange khi cần một vài controller endpoints có logic nghiệp vụ rõ ràng.

## 29. Checklist triển khai ProxyExchange an toàn

- [ ] Xác định đúng **Gateway Proxy Exchange** và artifact MVC/WebFlux theo release train.
- [ ] Không giả định ProxyExchange tự được bảo vệ bởi Gateway Server route filters.
- [ ] Không nhận `url`/`uri`/`host`/`port` từ client để đưa thẳng vào `proxy.uri(...)`.
- [ ] Dùng **fixed destination hoặc alias allowlist** do server quản trị.
- [ ] Chỉ nhận resource ID/path variables có format/length rõ; không dùng raw `/**` suffix nếu không có policy.
- [ ] Dựng URL bằng URI builder, tách path segments và queryParams; encode đúng một lần.
- [ ] Không dùng `String.startsWith`, `contains`, denylist localhost đơn giản để xác thực host.
- [ ] Nếu cần nhận URL từ trusted admin, validate scheme/host/port/userinfo/path/query/fragment và audit.
- [ ] Kiểm tra cả IPv4, IPv6, mapped addresses và DNS rebinding khi target có thể thay đổi.
- [ ] Enforce **egress allowlist** ở network/HTTP client, không chỉ tại một hàm validate.
- [ ] Không follow redirect ngoài policy; test mọi 3xx cần thiết.
- [ ] Giữ TLS certificate/hostname/SNI verification; dùng mTLS khi backend yêu cầu.
- [ ] Giữ mặc định không forward sensitive headers `Authorization` và `Cookie` trừ khi có policy cụ thể.
- [ ] Không dùng client `Host`/`Forwarded`/`X-Forwarded-*` làm source URI hoặc identity.
- [ ] Kiểm soát HTTP methods: GET/POST/PUT/DELETE riêng theo business contract.
- [ ] Đặt request/response size, timeout, connection pool, concurrency và rate limits.
- [ ] Không retry POST/DELETE tùy ý; có idempotency nếu backend có side effects.
- [ ] Xác minh authentication và authorization theo principal/tenant/resource trước khi proxy.
- [ ] Không relay token sai audience/scope hoặc sang host không phê duyệt.
- [ ] Kiểm soát response headers `Location`, `Set-Cookie`, CORS, cache và error details.
- [ ] Thử đầu vào encoded path, dot-segments, query pollution, URI userinfo và host spoof.
- [ ] Test redirect + DNS peer policy ở transport, không chỉ unit test URI parser.
- [ ] Mọi request bị từ chối phải tạo **0 outbound request**.
- [ ] Quan sát destination alias/route template thay vì raw URL, token hay user ID.
- [ ] Kiểm tra behavior ở nhiều Gateway replicas, khi DNS/cache/network thay đổi.
- [ ] Bảo vệ configuration/control-plane thay destination bằng RBAC, review và audit.
- [ ] Có runbook egress deny, SSRF alert, rollback config và khắc phục lộ credentials.
- [ ] Nếu logic proxy trở nên quá tổng quát, cân nhắc **Gateway Server** với route definitions và filter policies rõ ràng.

## Kết luận

**`ProxyExchange`** là tiện ích gọn để một controller Spring Web MVC hoặc WebFlux gửi HTTP request tới downstream. Chính vì controller gọi `proxy.uri(...)` trực tiếp nên **quyền chọn destination là trách nhiệm của code ứng dụng**. Nếu cho client cung cấp URL/host/port tùy ý, Gateway dễ trở thành open proxy và tạo đường vào SSRF, kể cả khi đã bật xác thực, timeout hay rate limiting.

Thiết kế an toàn nhất là **server tự quyết định scheme, host và port**, còn client chỉ cung cấp dữ liệu nghiệp vụ có giới hạn. Hãy dùng alias/URI cố định, `pathSegment`/`queryParam`, exact allowlist, bảo vệ headers và authorization, đồng thời áp chính sách tại **HTTP client, DNS/TLS và network egress**. Với những trường hợp buộc nhận URL từ nguồn tin cậy, phải tính đến redirect, DNS rebinding/TOCTOU, canonicalization và mọi attempts.

Chỉ xác nhận endpoint proxy an toàn khi có **integration tests cho thấy input sai không tạo outbound request**, response không rò credentials và policy vẫn có hiệu lực khi backend redirect, DNS thay đổi hoặc service discovery cập nhật. Đây là nền tảng để xây dựng một API Gateway cho microservices có định tuyến, xác thực, TLS và observability vừa linh hoạt vừa kiểm soát được rủi ro.

## Tài liệu tham khảo

- [Spring Cloud Gateway — Proxy Exchange Gateway with Spring Web MVC or WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-proxy-exchange.html)
- [Spring Cloud Gateway 4.3 — Proxy Exchange MVC/WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-proxy-exchange.html)
- [Spring Cloud Gateway — Tổng quan Server vs Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/intro.html)
- [Spring Cloud 2025.0 — Module artifact và prefix migration](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes)
- [OWASP Cheat Sheet — Server Side Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [OWASP Cheat Sheet — Authorization](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
- [OWASP Cheat Sheet — REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html)
- [Spring Framework — UriComponentsBuilder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-uri-building.html)
- [Spring Security — Servlet OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security — Reactive OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html)
- [Spring Framework — Spring MVC Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [Spring Framework — Spring WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html)
