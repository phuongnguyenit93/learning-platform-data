# Expose-Headers để client đọc ETag, Location và metadata

> **Module:** `INTEGRATION_API_REST` — chương **API trên trình duyệt**. Bài học thiết kế hợp đồng REST cho JavaScript `fetch()` khi frontend và API ở **khác origin**: dùng `Access-Control-Expose-Headers` để đọc `ETag`, `Location`, metadata phân trang, giới hạn tốc độ và truy vết; tích hợp Java/Spring, kiểm tra điều kiện HTTP, bảo mật và kiểm thử thực tế.

## 1. Vấn đề: DevTools thấy header, `fetch()` trả `null`

Ứng dụng tại `https://app.example.test` tạo đơn qua API `https://api.example.test`:

~~~http
POST /v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Accept: application/json

{"productId":"p_17","quantity":2}
~~~

API trả:

~~~http
HTTP/1.1 201 Created
Access-Control-Allow-Origin: https://app.example.test
Location: /v1/orders/ord_42
ETag: "ord_42-v1"
Content-Type: application/json

{"id":"ord_42","quantity":2,"status":"DRAFT"}
~~~

Frontend đọc JSON được nhưng:

~~~javascript
const response = await fetch(
  "https://api.example.test/v1/orders",
  { /* method, headers, body, token ... */ }
);
console.log(response.status);                 // 201
console.log(response.headers.get("Location")); // null
console.log(response.headers.get("ETag"));     // null
~~~

**Hai header vẫn có thể nằm trong Network panel và trong HTTP response thật.** JavaScript chạy ở origin khác chỉ nhìn thấy tập header mà Fetch/CORS cho phép đọc. `Access-Control-Allow-Origin` cho phép browser chia sẻ **response** với frontend, nhưng **không tự mở quyền đọc mọi response header**.

Giải pháp là công bố rõ các tên header cần đọc:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: ETag, Location, X-Request-Id
~~~

Sau đó `response.headers.get("ETag")` có thể trả `"ord_42-v1"` và `get("Location")` trả `/v1/orders/ord_42` nếu các header thực sự có mặt. **Expose-Headers chỉ làm header nhìn thấy được; nó không tạo ra header thiếu, cũng không cấp quyền truy cập tài nguyên.**

**Mục tiêu:** phân biệt header response CORS-safelisted và header cần expose, hiểu preflight/credentials, dùng `ETag`/`If-Match` và `Location` đúng HTTP, cấu hình Spring Boot và viết kiểm thử chứng minh JavaScript đọc được metadata an toàn.

## 2. Ba tầng khác nhau: HTTP, CORS và mã JavaScript

~~~mermaid
sequenceDiagram
    participant JS as Browser JS (app.example.test)
    participant B as Fetch/CORS enforcement
    participant API as REST API (api.example.test)
    JS->>B: fetch POST JSON + Authorization
    B->>API: OPTIONS preflight
    API-->>B: Allow-Origin / Methods / Headers
    B->>API: POST /v1/orders
    API-->>B: 201 + Location + ETag + Expose-Headers
    B-->>JS: Response, chỉ header được phép đọc
    JS->>JS: headers.get("ETag"), headers.get("Location")
~~~

Ba điều kiện độc lập:

1. **HTTP server thực sự gửi header** `ETag`, `Location` hoặc `Link` trong response của endpoint.
2. **CORS cho phép đọc response** bằng `Access-Control-Allow-Origin` (và `Access-Control-Allow-Credentials` nếu `credentials: "include"`).
3. **Header không thuộc danh sách mặc định** phải được liệt kê trong `Access-Control-Expose-Headers` để JavaScript đọc qua `Headers.get()`.

Nếu điều kiện 2 sai, `fetch` thường thất bại ở mức CORS/network và JavaScript **không nhận Response bình thường để đọc**. Nếu điều kiện 2 đúng nhưng điều kiện 3 thiếu, response/status/body có thể đọc được, còn `headers.get("ETag")` trả `null`.

CORS là cơ chế **browser thực thi**. Java `HttpClient`, curl hoặc service-to-service client có thể đọc header trực tiếp mà không cần `Expose-Headers`. Ngược lại, `Access-Control-Expose-Headers` **không bảo vệ API khỏi curl**: mọi request vẫn cần authentication, authorization và kiểm tenant/owner trên server.

### 2.1. Các response header đã được expose mặc định

Đối với CORS response thành công, Fetch có một số **CORS-safelisted response header names**:

| Đọc được mặc định | Ví dụ |
|---|---|
| `Cache-Control` | `private, no-cache` |
| `Content-Language` | `vi` |
| `Content-Length` | `431` (nếu response có header này) |
| `Content-Type` | `application/json` |
| `Expires` | HTTP-date |
| `Last-Modified` | HTTP-date |
| `Pragma` | `no-cache` |

**Không thuộc danh sách mặc định:** `ETag`, `Location`, `Link`, `Content-Disposition`, `Retry-After`, `WWW-Authenticate`, `X-Request-Id` và các header quota/RateLimit của ứng dụng. Muốn đọc chúng qua JS cross-origin, hãy expose tên cụ thể **và bảo đảm header đó tồn tại**.

Tên header **không phân biệt chữ hoa/chữ thường**: `headers.get("etag")` và `headers.get("ETag")` tương đương. Giá trị `null` có thể do header không gửi, bị proxy gỡ, hoặc bị CORS che; không suy đoán chỉ từ `null`.

### 2.2. Header không thể đọc chỉ bằng expose

`Set-Cookie` là **forbidden response-header name** trong Fetch: JavaScript không thể đọc nó từ `Response.headers`, kể cả khi viết `Access-Control-Expose-Headers: Set-Cookie`. Cookie cần được quản lý theo cơ chế cookie của trình duyệt, với `HttpOnly`, `Secure` và `SameSite` phù hợp; không đổi sang trả raw session token trong custom response header chỉ để JavaScript đọc được.

Tương tự, `Access-Control-Expose-Headers` không làm lộ `Location` của **một redirect trung gian** khi `fetch` tự động follow, và cũng không phá được chế độ `opaque`/`opaqueredirect`. Những trường hợp đó có chính sách Fetch riêng (mục 8).

## 3. Chọn header nào để expose theo hợp đồng REST?

| Header | Có ích cho browser client | Điều kiện an toàn |
|---|---|---|
| `ETag` | Revalidation, optimistic concurrency với `If-Match` | Validator đúng representation, không dùng làm ID bí mật |
| `Location` | Sau `201 Created` để biết URI resource, hoặc `202` cho operation monitor | URI do server kiểm soát; không copy credential sang đích khác |
| `Link` | Phân trang cursor, liên kết `rel="next"`/`rel="prev"` | URI không mang token, quan hệ link được tài liệu hóa |
| `Retry-After` | Điều tiết sau `429`/`503` hoặc polling có hướng dẫn | Browser tự quyết định retry có ngân sách |
| `X-Request-Id` / `Trace-Id` | Báo lỗi, liên hệ support | ID đã được kiểm soát; không chứa bí mật/PII |
| `Content-Disposition` | Tên file tải về gợi ý | Sanitize tên file; không tin metadata làm path ghi file |
| `RateLimit-Limit`, `RateLimit-Remaining` | Hiển thị quota theo contract ứng dụng | Chỉ expose quota đúng chủ thể; không coi là căn cứ cấp quyền |

**Expose ít nhất cần thiết.** Metadata cũng có thể nhạy cảm: số lần gọi còn lại, operation identifier, `Link` mang cursor hoặc phiên bản resource có thể tiết lộ mô hình nội bộ. Không tự động expose mọi custom header chỉ vì chúng có trong response server.

### 3.1. Ví dụ `201 Created`: `Location` và `ETag`

~~~http
HTTP/1.1 201 Created
Location: /v1/orders/ord_42
ETag: "ord_42-v1"
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Location, ETag, X-Request-Id
Content-Type: application/json
Cache-Control: private, no-store

{"id":"ord_42","status":"DRAFT","quantity":2}
~~~

`Location` của `201` **chỉ URI tài nguyên vừa tạo**, không phải chỉ dẫn chuyển hướng như `302`/`303`. `ETag` có thể định danh phiên bản representation mới được tạo; nó **không phải** một mã xác thực hoặc khóa duy nhất để bypass quyền.

### 3.2. Ví dụ GET và cập nhật có điều kiện

~~~http
GET /v1/orders/ord_42 HTTP/1.1
Origin: https://app.example.test
Authorization: Bearer <access-token>
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: ETag
ETag: "ord_42-v1"
Content-Type: application/json

{"id":"ord_42","status":"DRAFT","deliveryNote":"Giao buổi tối"}
~~~

Client lưu **nguyên giá trị ETag bao gồm dấu nháy**; khi cập nhật:

~~~http
PATCH /v1/orders/ord_42 HTTP/1.1
Origin: https://app.example.test
Authorization: Bearer <access-token>
Content-Type: application/merge-patch+json
If-Match: "ord_42-v1"

{"deliveryNote":"Giao sau 19 giờ"}
~~~

Nếu representation hiện tại đã đổi, server trả `412 Precondition Failed` và không ghi đè; nếu endpoint bắt buộc precondition nhưng thiếu, có thể trả `428 Precondition Required`. `If-Match` dùng **strong comparison**: ETag dạng `W/"..."` (weak) không thích hợp để chứng minh match cho conditional write. ETag cũng không thay quyền ghi hoặc kiểm tenant trong service.

### 3.3. `Link`, `Retry-After` và phân trang

~~~http
HTTP/1.1 200 OK
Link: </v1/orders?limit=20&cursor=next_1>; rel="next"
Access-Control-Expose-Headers: Link, ETag
ETag: "orders-page-1"
Content-Type: application/json

{"items":[{"id":"ord_42"}]}
~~~

`response.headers.get("Link")` trả chuỗi header, **không tự parse `rel` hoặc cursor**. Client cần parser đúng cú pháp Link header hoặc dùng JSON links đã thống nhất. Cursor có thể mang thông tin theo tenant và thời hạn; không viết token/secret vào URI. Khi API trả `429` với `Retry-After: 5`, expose header đó nếu ứng dụng browser cần đọc để quyết định thời gian retry.

## 4. `Expose-Headers` khác `Allow-Headers` và các CORS header khác thế nào?

| Header CORS | Hướng và chức năng |
|---|---|
| `Access-Control-Allow-Origin` | **Response:** frontend origin nào được đọc response |
| `Access-Control-Allow-Credentials` | **Response:** có cho browser chia sẻ response khi request ở `credentials: "include"` không |
| `Access-Control-Allow-Methods` | **Preflight response:** method nào được phép trong yêu cầu cross-origin tiếp theo |
| `Access-Control-Allow-Headers` | **Preflight response:** request header nào frontend được gửi, ví dụ `If-Match` |
| `Access-Control-Expose-Headers` | **Actual response:** response header nào JavaScript được đọc, ví dụ `ETag` |
| `Access-Control-Max-Age` | **Preflight response:** cho cache kết quả preflight bao lâu theo giới hạn browser |
| `Vary: Origin` | **HTTP caching:** phân biệt các response thay đổi theo request `Origin` |

**Đây là hai hướng dữ liệu khác nhau:** muốn **gửi** `If-Match` thì khai trong `Access-Control-Allow-Headers`; muốn **đọc** `ETag` thì khai trong `Access-Control-Expose-Headers`. Thêm `ETag` vào Allow-Headers không giúp `response.headers.get("ETag")`.

### 4.1. Ví dụ preflight và actual response

Với `POST application/json` và `Authorization` do frontend gửi, browser thường thực hiện preflight:

~~~http
OPTIONS /v1/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Server có thể trả:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, HEAD, POST, PATCH, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, If-Match, If-None-Match
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

Sau preflight thành công, browser mới gửi POST thực tế và nhận `201` với:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: ETag, Location, Link, X-Request-Id
~~~

**Không cần chờ preflight để expose header:** GET đơn giản không có header tùy biến có thể không preflight, nhưng vẫn cần `Access-Control-Expose-Headers` trên response nếu frontend muốn đọc `ETag`. Thông thường đặt Expose-Headers ở **actual response**, không trông chờ khai báo nó chỉ trong preflight.

Khi frontend gửi `PATCH` với `If-Match` hoặc `If-None-Match`, các header này cũng không thuộc danh sách request header CORS-safelisted; browser sẽ preflight trừ khi có cache preflight hợp lệ. Server phải cho phép cả method `PATCH` lẫn những request header theo contract.

### 4.2. `Access-Control-Expose-Headers: *` có bẫy

~~~http
Access-Control-Expose-Headers: *
~~~

Theo quy tắc Fetch, `*` có nghĩa wildcard **chỉ đối với request không có credentials mode `include`**. Với `fetch(..., {credentials:"include"})`, nó được hiểu như **tên header literal `*`**, chứ không expose mọi header.

Vì vậy **ưu tiên danh sách tường minh**:

~~~http
Access-Control-Expose-Headers: ETag, Location, Link, Retry-After, X-Request-Id
~~~

Danh sách cố định giúp audit trường nào đáng công bố, nhất quán với OpenAPI và tránh lỗi khi ứng dụng chuyển từ Bearer-only sang session cookie. Ngay cả wildcard hợp lệ cũng **không** làm `Set-Cookie` đọc được qua JS.

### 4.3. Cookie/session và `credentials: "include"`

Với một app dùng cookie cho request cross-origin, cần đồng thời:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: ETag, Location
~~~

Browser dùng `fetch(url, {credentials:"include"})` để gửi cookie phù hợp. `Access-Control-Allow-Origin: *` **không hợp lệ khi dùng credential mode include**. Các cookie cross-site có thể cần `SameSite=None; Secure`, nhưng chính sách chặn third-party cookies của browser vẫn có thể ngăn gửi cookie; `Expose-Headers` không thay các quy tắc đó.

Với session/cookie, phải có **CSRF protection** cho thao tác thay đổi state, kể cả đã cấu hình CORS. CORS **không phải authentication, authorization hoặc biện pháp chống CSRF toàn diện**. Bearer token do JS thêm thủ công sẽ gây preflight do `Authorization`, và cần kiểm audience/scope trên server; không lưu token dễ bị XSS vào storage không phù hợp.

## 5. Java/Spring Boot: cấu hình CORS ở một nơi đáng tin

Ví dụ Spring Boot 3.x, Spring MVC/Spring Security 6, Java 17: API chỉ nhận Bearer token ở `https://api.example.test` từ frontend `https://app.example.test`. Chọn origin cụ thể, allowed methods/headers đúng API, và expose đúng metadata cần đọc.

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableMethodSecurity
class ApiSecurityConfiguration {
    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.test"));
        cors.setAllowedMethods(List.of(
            "GET", "HEAD", "POST", "PATCH", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "If-Match",
            "If-None-Match", "Idempotency-Key"));
        cors.setExposedHeaders(List.of(
            "ETag", "Location", "Link", "Retry-After",
            "X-Request-Id", "Content-Disposition"));
        cors.setMaxAge(600L);
        // Ví dụ chỉ dùng Bearer; không bật allowCredentials.

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/v1/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/v1/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Cảnh báo:** chỉ vô hiệu CSRF ở đây vì giả định API **stateless, chỉ nhận Bearer ở Authorization**, không dùng cookie/session để xác thực browser. Nếu hệ thống nhận cookie auth, giữ/cấu hình CSRF và `setAllowCredentials(true)` với allowed origins tường minh; không áp dụng máy móc cấu hình trên. OAuth2 Resource Server còn cần cấu hình issuer/JWK validation và kiểm audience phù hợp, không chỉ `.authenticated()`.

Spring Security sử dụng cấu hình CORS để xử lý preflight **trước** bước xác thực trong filter chain. Preflight thường không có Bearer token; nếu bị security trả 401 trước CORS, browser có thể báo lỗi CORS thay vì tiến tới request thực. Không đặt wildcard `allowedOrigins` khi bật credentials, không phản chiếu mọi `Origin` nhận được như một allowlist, và không để gateway thêm cấu hình CORS mâu thuẫn với Spring.

Với Spring WebFlux, có thể cấu hình CORS qua `CorsWebFilter`/`WebFluxConfigurer` hoặc Spring Security reactive integration tương ứng; không dùng nguyên `SecurityFilterChain` servlet MVC cho ứng dụng reactive `SecurityWebFilterChain`. Hợp đồng header HTTP vẫn giống nhau.

### 5.1. Controller gửi header nghiệp vụ; CORS layer expose header

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import java.net.URI;
import org.springframework.http.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

record NewOrder(@NotBlank String productId, @Min(1) int quantity) {}
record OrderView(String id, String status, int quantity, long version) {}

@RestController
@RequestMapping("/v1/orders")
class OrderController {
    private final OrderService orders;
    OrderController(OrderService orders) {
        this.orders = orders;
    }

    @PostMapping(consumes = "application/json",
                 produces = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    ResponseEntity<OrderView> create(@Valid @RequestBody NewOrder input) {
        OrderView created = orders.createAuthorizedForCaller(input);
        return ResponseEntity.created(
                URI.create("/v1/orders/" + created.id()))
            .eTag(etag(created))
            .cacheControl(CacheControl.noStore())
            .body(created);
    }

    @GetMapping(path = "/{id}", produces = "application/json")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    ResponseEntity<OrderView> get(@PathVariable String id) {
        OrderView found = orders.readAuthorizedForCaller(id);
        return ResponseEntity.ok()
            .eTag(etag(found))
            .cacheControl(CacheControl.noStore())
            .body(found);
    }

    private static String etag(OrderView view) {
        return "\"order-" + view.id() + "-v"
            + view.version() + "\"";
    }
}

interface OrderService {
    OrderView createAuthorizedForCaller(NewOrder request);
    OrderView readAuthorizedForCaller(String id);
}
~~~

Controller xác định `Location` và `ETag` của **resource đã được phép truy cập**. CORS filter thêm `Access-Control-Expose-Headers`; controller không cần tự đặt nó ở từng method. `OrderService` là abstraction phải hiện thực với kiểm principal/tenant, validate số lượng và transaction. `@PreAuthorize` chỉ hoạt động khi method security được bật và **không thay kiểm object-level authorization**.

Đây là example về expose header, không phải triển khai `PATCH` hoàn chỉnh: cần endpoint riêng kiểm `If-Match` với strong ETag và xử lý đồng thời an toàn ở database. ETag cũng phải nhất quán với representation thực sự mà API trả; tránh tạo ETag không phản ánh thay đổi nội dung khi dùng nó làm cơ chế chống lost update.

### 5.2. Đừng quên response lỗi và hạ tầng trung gian

Nếu client cần đọc `Retry-After` khi bị `429`, `X-Request-Id` khi `500`, hoặc `WWW-Authenticate` khi `401`, response lỗi cũng cần CORS hợp lệ và Expose-Headers phù hợp. Kiểm tra cả những lỗi do **Spring Security filter, reverse proxy, gateway, CDN** phát ra: một response không qua ứng dụng Spring có thể không mang CORS headers. Không trả thông tin nhạy cảm trong `WWW-Authenticate`/metadata; chỉ expose khi có nhu cầu cụ thể.

Với nhiều origin được chọn động từ danh sách tin cậy, phản hồi cần `Vary: Origin` (và preflight cần phân biệt request method/headers nếu cache liên quan). Tránh để CDN cache response của tenant A rồi trả cho tenant B; `Cache-Control` và cache key theo quyền quan trọng hơn việc chỉ có `Vary`.

## 6. Frontend `fetch()`: đọc `Location`, `ETag` và cập nhật an toàn

Ví dụ này dùng Bearer token lấy từ cơ chế đăng nhập đáng tin, được giữ trong bộ nhớ ứng dụng. Request dùng `credentials:"omit"` để không gửi cookie browser, đúng mô hình Bearer-only ở mục 5:

~~~javascript
const API = new URL("https://api.example.test");

async function createOrder(token, input) {
  const response = await fetch(new URL("/v1/orders", API), {
    method: "POST",
    mode: "cors",
    credentials: "omit",
    redirect: "error",
    headers: {
      "Authorization": "Bearer " + token,
      "Content-Type": "application/json",
      "Accept": "application/json"
    },
    body: JSON.stringify(input)
  });

  if (response.status !== 201) {
    throw new Error("Create failed: HTTP " + response.status);
  }

  const location = response.headers.get("Location");
  const etag = response.headers.get("ETag");
  if (!location || !etag) {
    throw new Error("API contract: missing/unexposed metadata");
  }

  const resource = new URL(location, response.url);
  if (resource.origin !== API.origin) {
    throw new Error("Unexpected Location origin");
  }
  const order = await response.json();
  return {order, resource, etag};
}

async function changeDeliveryNote(token, resource, etag, note) {
  if (resource.origin !== API.origin) {
    throw new Error("Untrusted resource URL");
  }
  if (etag.startsWith("W/")) {
    throw new Error("Strong ETag required for If-Match");
  }
  const response = await fetch(resource, {
    method: "PATCH",
    mode: "cors",
    credentials: "omit",
    redirect: "error",
    headers: {
      "Authorization": "Bearer " + token,
      "Content-Type": "application/merge-patch+json",
      "If-Match": etag
    },
    body: JSON.stringify({deliveryNote: note})
  });
  if (response.status === 412) {
    throw new Error("Order changed; reload and reconcile");
  }
  if (!response.ok) {
    throw new Error("Update failed: HTTP " + response.status);
  }
  return {
    order: await response.json(),
    etag: response.headers.get("ETag")
  };
}
~~~

**Điểm cần nhớ:** giá trị ETag có thể gồm dấu nháy; đừng tước dấu nháy rồi gửi `If-Match` sai cú pháp. Client cần xử lý 412 bằng tải lại dữ liệu và giải quyết conflict; không retry PATCH liên tục bằng cách bỏ precondition. `redirect:"error"` ngăn tự follow redirect không mong đợi trong luồng ghi, nhưng không thay validation URL khi client dùng `Location` để tạo request mới.

Trong ví dụ, `Location` được resolve tương đối theo `response.url`, không ghép chuỗi bằng tay. Nếu API thật trả URI hợp lệ ở origin khác (như upload session hoặc signed download), cần **policy riêng**: không mặc nhiên chuyển Bearer token hoặc cookie của API sang origin khác.

## 7. Conditional requests, `304` và lưu đệm: hiểu giới hạn của ETag

`ETag` là HTTP validator của một representation. Expose nó giúp frontend dùng **hai nhóm tính năng khác nhau**:

1. **Đọc lại có điều kiện** bằng `If-None-Match` cho GET/HEAD, tránh gửi lại nội dung không đổi khi cache/revalidation phù hợp.
2. **Ghi có điều kiện** bằng `If-Match` trên PUT/PATCH/DELETE, tránh lost update khi nhiều client cùng sửa.

Ví dụ request đọc có điều kiện:

~~~http
GET /v1/orders/ord_42 HTTP/1.1
Origin: https://app.example.test
Authorization: Bearer <access-token>
If-None-Match: "ord_42-v1"
~~~

Nếu không thay đổi, server có thể trả:

~~~http
HTTP/1.1 304 Not Modified
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: ETag
ETag: "ord_42-v1"
Cache-Control: private, no-cache
~~~

`304` **không có body representation**. Trong một số luồng dùng cache của trình duyệt, browser có thể revalidate bằng 304 ở tầng mạng nhưng trả cho `fetch()` response đã ghép từ cache với status hiển thị là 200. Vì vậy không viết client luôn chờ thấy `304` để biết cache hoạt động; kiểm hành vi thực và cache policy. Ngoài ra, `Cache-Control: no-store` (như ví dụ bảo mật ở mục 5) ngăn lưu cache, nhưng vẫn có thể dùng ETag cho **optimistic concurrency**.

Nếu frontend tự gửi `If-None-Match`/`If-Match`, những request headers đó cần được cho phép qua CORS preflight. Expose ETag không đồng nghĩa tự cho phép gửi precondition. Cả `GET` lẫn `PATCH` vẫn phải kiểm object-level authorization; validator không phải capability cấp quyền.

### 7.1. ETag cho dữ liệu cá nhân

Tránh đặt `userId`, email hoặc token vào ETag. Với representation khác nhau theo quyền, không dùng chung một ETag sai phạm vi; cache được chia sẻ cần xác định khóa cache và `Cache-Control` đúng. `Vary: Origin` chỉ nói response CORS khác theo origin, **không** bảo vệ dữ liệu giữa hai user cùng origin frontend.

### 7.2. `HEAD` hữu ích cho metadata

`HEAD /v1/orders/ord_42` có thể trả `ETag`, `Last-Modified` và những header phù hợp mà không có body. Với cross-origin, `ETag` vẫn cần expose. Server không nên tự dùng GET tạo body lớn chỉ để frontend đọc một header nếu có endpoint HEAD hoặc metadata API hiệu quả.

## 8. `Location` của redirect không phải `Location` của `201`

Đây là lỗi thiết kế client phổ biến:

| Kết quả | Ý nghĩa đối với browser |
|---|---|
| `201 Created` + `Location` | Response tạo resource; JS đọc được Location **nếu expose** |
| `202 Accepted` + `Location` | Có thể chỉ URI operation monitor; client poll theo contract |
| `302 Found` / `303 See Other` / `307` / `308` | **Redirect**; Fetch quyết định có follow theo `redirect` mode |
| `fetch(..., {redirect:"follow"})` | Thường nhận **response cuối**; không tự thấy Location của hop trung gian |
| `fetch(..., {redirect:"manual"})` cross-origin | Có thể nhận `opaqueredirect`: status 0, headers không đọc được |

`Access-Control-Expose-Headers: Location` **không mở khóa Location của redirect trung gian** nếu browser đã follow hoặc đã tạo filtered response `opaqueredirect`. Không dùng `redirect:"manual"` như thủ thuật vượt chính sách CORS.

Nếu backend muốn frontend nhận URI resource, hãy trả **201/202 cùng Location trên response cuối được phép đọc**, hoặc body chứa link có contract rõ. Với redirect tới CDN/signed URL, phải áp chính sách origin và credential riêng; không tự gửi Bearer token của API sang URI mới. URI Location không đáng tin chỉ vì nó do response trả về nếu gateway hoặc server có thể bị cấu hình sai.

## 9. Bảo mật và vận hành: expose metadata không có nghĩa mở quyền

- **Allowlist origin, không phản chiếu vô điều kiện:** chỉ chấp nhận frontend được phép; với credential mode include, origin phải cụ thể và `Access-Control-Allow-Credentials: true`. Không dùng `*` tùy tiện để “sửa CORS”.
- **Phân quyền ở server:** `GET`/`POST`/`PATCH` phải xác minh principal, scope, tenant và object; CORS chỉ quản lý browser đọc response. Chặn BOLA/IDOR ngay cả khi metadata có trong header.
- **Bảo vệ response/header:** không đưa refresh token, mật khẩu, private key, signed URL dài hạn vào `Location`/`Link`/custom headers. Header cũng xuất hiện trong log/proxy/tracing.
- **Cache:** response riêng tư nên có `Cache-Control: private`/`no-store` phù hợp; proxy/CDN cần tránh cache lẫn tenant. `Vary: Origin` khi CORS response thay đổi theo Origin.
- **Preflight không phải login:** `OPTIONS` thường không mang Bearer. Xử lý CORS trước auth nhưng chỉ cho method/header đúng hợp đồng; request thực vẫn được xác thực.
- **Lỗi và rate limit:** với `401/403/429/503`, đừng để gateway/exception handler trả response thiếu CORS khiến browser chỉ thấy “CORS error”; expose `Retry-After`/`X-Request-Id` khi an toàn và hữu ích.
- **Cookie và CSRF:** `Access-Control-Expose-Headers` không cho đọc `Set-Cookie`; cross-site session cookie có thể bị chính sách browser chặn, và cookie-auth mutations vẫn cần CSRF protection.
- **Thông tin hiệu năng:** nếu cần đọc chi tiết Resource Timing từ cross-origin, đó còn liên quan `Timing-Allow-Origin`, **không** được giải quyết chỉ bằng Expose-Headers.

Mục tiêu là có **metadata vừa đủ phục vụ nghiệp vụ**. Không nên expose “tất cả header” hoặc vô hiệu CORS khi frontend gặp `null`; hãy sửa đúng tầng và kiểm tra với một trình duyệt thực.

## 10. OpenAPI 3.1: tài liệu hóa header mà client phụ thuộc

OpenAPI mô tả response headers trong `responses.*.headers`; `Access-Control-Expose-Headers` là **cấu hình cross-origin ở runtime**, không tự phát sinh chỉ nhờ khai báo schema. Ví dụ:

~~~yaml
openapi: 3.1.0
info: {title: Orders API, version: 1.0.0}
paths:
  /v1/orders:
    post:
      summary: Tạo đơn hàng
      security: [{bearerAuth: []}]
      requestBody:
        required: true
        content:
          application/json:
            schema: {$ref: '#/components/schemas/NewOrder'}
      responses:
        '201':
          description: Tạo thành công
          headers:
            Location:
              required: true
              schema: {type: string, format: uri-reference}
            ETag:
              description: Strong entity tag của representation mới
              schema: {type: string}
            X-Request-Id:
              schema: {type: string}
        '400': {description: Body không hợp lệ}
        '401': {description: Chưa xác thực}
        '403': {description: Thiếu quyền}
  /v1/orders/{id}:
    get:
      security: [{bearerAuth: []}]
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string}
      responses:
        '200':
          description: Đơn hàng
          headers:
            ETag:
              schema: {type: string}
        '304': {description: Không đổi khi có If-None-Match}
        '404': {description: Không tìm thấy hoặc không công bố}
    patch:
      summary: Sửa đơn khi If-Match hợp lệ
      security: [{bearerAuth: []}]
      parameters:
        - in: path
          name: id
          required: true
          schema: {type: string}
        - in: header
          name: If-Match
          required: true
          schema: {type: string}
      requestBody:
        required: true
        content:
          application/merge-patch+json:
            schema: {type: object}
      responses:
        '200':
          description: Cập nhật thành công
          headers:
            ETag:
              schema: {type: string}
        '412': {description: ETag không còn khớp}
        '428': {description: Thiếu precondition}
components:
  securitySchemes:
    bearerAuth: {type: http, scheme: bearer}
  schemas:
    NewOrder:
      type: object
      required: [productId, quantity]
      properties:
        productId: {type: string}
        quantity: {type: integer, minimum: 1}
~~~

**Cần đồng bộ ba nơi:** Spring controller phát `Location/ETag`; Spring CORS config expose chúng; OpenAPI công bố client có thể trông đợi chúng ở response nào. Nếu API cung cấp `Link`/`Retry-After` thì khai báo ở response tương ứng. Tài liệu nên ghi frontend origins được hỗ trợ và cách xử lý credential/preflight, nhưng đừng coi OpenAPI là một CORS enforcement engine.

## 11. Kiểm thử: server gửi đúng chưa đủ, browser phải đọc được

Kiểm thử ở **hai tầng**:

- **Spring MockMvc/integration test:** xác minh CORS config nhận đúng `Origin`, preflight, actual response có `ETag`/`Location` và `Access-Control-Expose-Headers`.
- **Browser E2E:** mở frontend ở origin khác, gọi `fetch()` thật, kiểm `headers.get(...)`. Một test HTTP thuần không mô phỏng hoàn toàn **filtered response headers** của browser.

### 11.1. Ví dụ kiểm tra preflight và actual response bằng MockMvc

~~~java
// Trong @SpringBootTest + @AutoConfigureMockMvc;
// import static MockMvcRequestBuilders.*;
// import static MockMvcResultMatchers.*;
// import static SecurityMockMvcRequestPostProcessors.jwt;
// import static org.hamcrest.Matchers.containsString;
// Fixture OrderService trả đơn ord_42 có version 1.

mockMvc.perform(options("/v1/orders")
        .header("Origin", "https://app.example.test")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers",
            "authorization,content-type"))
    .andExpect(status().is2xxSuccessful())
    .andExpect(header().string(
        "Access-Control-Allow-Origin", "https://app.example.test"))
    .andExpect(header().string(
        "Access-Control-Allow-Headers",
        containsString("authorization")));

mockMvc.perform(get("/v1/orders/ord_42")
        .header("Origin", "https://app.example.test")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk())
    .andExpect(header().exists("ETag"))
    .andExpect(header().string(
        "Access-Control-Expose-Headers", containsString("ETag")))
    .andExpect(header().string(
        "Access-Control-Allow-Origin", "https://app.example.test"));
~~~

Khi test `POST 201`, assert cả `Location`, `ETag` và expose list chứa hai tên này. Khi test PATCH với `If-Match`, assert preflight cho phép `PATCH` và `If-Match`. Nếu test slice không nạp đúng `SecurityFilterChain`/CORS source, test có thể sai dù production config đúng; cần ít nhất một test với cấu hình thực.

Test **origin không được phép**: gửi `Origin: https://untrusted.example` và xác nhận không có `Access-Control-Allow-Origin` cho origin đó; HTTP status của preflight tùy runtime, không được dựa vào việc server trả 403 như cơ chế authentication. Test Bearer thiếu/không đủ scope để bảo đảm browser vẫn nhận response lỗi có CORS header đúng, nhưng không lộ dữ liệu riêng tư.

### 11.2. Kiểm tra quyền đọc header thật trong trình duyệt

Ví dụ đoạn kiểm tra chạy trong trang test tại `https://app.example.test` (token thử nghiệm, không dùng credential thật):

~~~javascript
const r = await fetch("https://api.example.test/v1/orders/ord_42", {
  mode: "cors",
  credentials: "omit",
  headers: {
    "Authorization": "Bearer " + testAccessToken,
    "Accept": "application/json"
  }
});

console.assert(r.type === "cors");
console.assert(r.status === 200);
console.assert(r.headers.get("Content-Type") !== null);
console.assert(r.headers.get("ETag") !== null);
console.assert(r.headers.get("Set-Cookie") === null);
~~~

Chạy test tương tự khi **bỏ ETag khỏi Expose-Headers** (trên mock server response) nhưng vẫn trả ETag thật: JS phải thấy `null` cho ETag, dù DevTools Network cho thấy header có mặt. Khi bỏ `Access-Control-Allow-Origin` hoặc dùng origin không được cho phép, `fetch` có thể **reject** thay vì trả một response với `status=403` cho JS. Đó là khác biệt quan trọng giữa kiểm thử ở browser và việc chỉ xem raw HTTP.

### 11.3. Ma trận kiểm thử tối thiểu

| Tình huống | Điều cần xác minh |
|---|---|
| `201` có `Location`/`ETag` và expose đúng | Browser đọc được cả hai |
| `200 GET` có ETag nhưng quên expose | JS nhận `null` cho ETag |
| `200` chỉ cần `Content-Type` | JS đọc được mà không cần expose |
| `OPTIONS` với `Authorization`/`Content-Type` | Allow-Origin/Methods/Headers đúng |
| `PATCH` gửi `If-Match` | Preflight cho header, 412 khi stale |
| Origin ngoài allowlist | CORS không cho frontend đọc response |
| `credentials:"include"` và `Expose-Headers: *` | Không coi wildcard là danh sách mọi header |
| `Set-Cookie` xuất hiện trong raw response | `headers.get("Set-Cookie")` vẫn `null` |
| `429 Retry-After` hoặc `500 X-Request-Id` | Header được expose nếu response và contract yêu cầu |
| `302`/`303` auto-follow | Không giả định đọc được Location của hop trung gian |
| `redirect:"manual"` cross-origin | Không vượt được `opaqueredirect` |
| Proxy/CDN thay đổi `Origin`/cache | Không trộn metadata hoặc dữ liệu giữa caller |

Các test quan trọng nhất nên chạy bằng **browser thật** ít nhất trên hai origin khác nhau; có thể dùng Playwright hoặc framework E2E tương đương. Không dùng `mode:"no-cors"` để “sửa” lỗi: Fetch sẽ cho một **opaque response**, thường không đọc được status/header/body như API cần.

## 12. Chẩn đoán lỗi phổ biến

| Triệu chứng | Kiểm tra theo thứ tự |
|---|---|
| Network panel có ETag, JS nhận `null` | Response có `Access-Control-Expose-Headers: ETag` không? CORS thực sự thành công không? |
| `fetch()` reject do CORS | `Origin` có được allow? Có preflight `OPTIONS`? `Authorization`/`If-Match` có trong Allow-Headers không? |
| 401 ở preflight | CORS filter có chạy trước authentication không? Preflight thường không mang token |
| Có `Allow-Headers: ETag` nhưng JS vẫn đọc không được | Đang nhầm **request** header với **response** header; cần Expose-Headers |
| Dùng `Expose-Headers: *` vẫn không đọc được | `credentials:"include"` làm wildcard trở thành tên literal; liệt kê tên cụ thể |
| POST 201 đọc được body, không thấy Location | Controller/gateway có gửi `Location` không? Nếu có, expose nó; phân biệt với redirect |
| Gặp `response.type="opaqueredirect"` | Không thể đọc redirect Location bằng expose; thay giao thức/redirect mode phù hợp |
| ETag từ cache không đúng kỳ vọng | Kiểm `no-store/no-cache`, revalidation và khác biệt representation theo user |
| Response lỗi chỉ báo “CORS error” | Proxy/Security/exception path có thêm CORS headers như response thành công không? |
| Java HttpClient đọc ETag được, browser không | Khác biệt do browser Fetch/CORS filter, không phải server không gửi ETag |

Khi debug, so sánh **request Origin**, raw response header, preflight (nếu có), response cuối cùng sau redirect và kết quả `Response.headers` của JS. Không sửa bừa bằng `Access-Control-Allow-Origin: *` hay tắt bảo mật.

## 13. Bài thực hành: quản lý đơn và phân trang từ frontend

**Bối cảnh:** frontend `https://portal.example.test` dùng token Bearer gọi `https://orders.example.test`. API có `POST /v1/orders` trả 201 + Location/ETag, `GET /v1/orders/{id}` trả 200 + ETag, `PATCH` dùng If-Match, `GET /v1/orders` trả Link để phân trang, và `429` có Retry-After. Frontend thấy các header trong DevTools nhưng `headers.get(...)` trả null.

**Nhiệm vụ:**

1. Viết HTTP response `201` với `Access-Control-Allow-Origin` và `Access-Control-Expose-Headers` đủ để đọc Location/ETag; giữ Content-Type và Location đúng REST.
2. Viết `OPTIONS` preflight cho POST JSON có Authorization và PATCH có If-Match; giải thích tại sao `If-Match` nằm ở Allow-Headers còn `ETag` ở Expose-Headers.
3. Cấu hình Spring MVC `CorsConfigurationSource` chỉ cho `https://portal.example.test`, cho phép đúng methods/headers và expose `ETag, Location, Link, Retry-After`.
4. Viết `fetch()` tạo đơn, resolve Location tương đối, lưu ETag nguyên chuỗi và PATCH có `If-Match`. Xử lý 412 bằng tải lại dữ liệu, **không** bỏ precondition.
5. Bổ sung `GET` phân trang dùng Link; nếu Link chứa cursor riêng tư, chỉ phát cho caller có quyền.
6. Thiết kế browser test xác nhận header đọc được khi expose, bị che khi không expose, và không thể đọc `Set-Cookie`.
7. Mở rộng cho session-cookie authentication: mô tả `credentials:"include"`, Allow-Credentials, origin cụ thể, CSRF và giới hạn `Expose-Headers: *`.
8. Viết test cho 429/500 xuất phát từ proxy, để frontend vẫn nhận được metadata cần thiết mà không lộ nội dung nhạy cảm.

**Gợi ý tự kiểm:** không dùng wildcard để né kiểm quyền; không nhầm 201 Location với 302 redirect; không coi ETag là token; không chỉ test raw HTTP mà bỏ qua filtered headers của browser.

## 14. Tổng kết

- `Access-Control-Expose-Headers` **cho JavaScript cross-origin đọc thêm response headers** ngoài nhóm CORS-safelisted; nó không sinh ETag/Location và không cho gửi request headers.
- `Access-Control-Allow-Headers` xử lý `Authorization`, `If-Match` và request headers ở preflight; `Access-Control-Allow-Origin` và credential policy quyết định browser có đọc được response hay không.
- `ETag` phục vụ conditional GET/If-Match; `Location` trên 201/202 chỉ URI tài nguyên/operation, **không phải redirect tự động**.
- Dùng **allowlist origin** và expose tên header cụ thể; `*` không hoạt động như wildcard với `credentials:"include"`, còn `Set-Cookie` luôn bị Fetch che khỏi `Response.headers`.
- Đồng bộ **Spring controller, CORS/security config, OpenAPI, MockMvc và browser E2E**; bảo vệ tenant, cache, signed URLs và error metadata ở mọi tầng.

Một API REST hữu ích cho frontend không chỉ có JSON body đúng: nó còn phải công bố **metadata HTTP đúng chỗ, đúng quyền và đọc được theo quy tắc Fetch/CORS**, sau đó chứng minh hành vi ấy trong trình duyệt thật.
