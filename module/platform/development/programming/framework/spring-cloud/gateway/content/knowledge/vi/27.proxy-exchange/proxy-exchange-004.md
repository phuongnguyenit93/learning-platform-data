# Chuyển tiếp GET, POST và các HTTP method khác với ProxyExchange trong Spring Cloud Gateway

Trong kiến trúc microservices, đôi khi ứng dụng cần **chuyển một HTTP request tới service khác từ ngay trong controller**, thay vì xây dựng một Gateway Server có route definitions và GatewayFilter chain riêng. Ví dụ, một ứng dụng BFF (Backend for Frontend) muốn nhận `GET /bff/catalog/42` rồi gọi `catalog-service`; hoặc một controller trung gian cần chuyển `POST /bff/orders` sang order service sau khi áp dụng kiểm tra nghiệp vụ.

**Spring Cloud Gateway Proxy Exchange** cung cấp đối tượng `ProxyExchange<T>` để controller trong **Spring MVC** hoặc **Spring WebFlux** thực hiện những trao đổi HTTP downstream đơn giản qua các phương thức tương ứng với **GET, POST, PUT, PATCH, DELETE** và, ở những API được hỗ trợ, **HEAD, OPTIONS**. Bài học thuộc chương **Proxy Exchange** của module **SPRING_CLOUD_GATEWAY**, tập trung vào **chuyển tiếp GET, POST và các HTTP method khác** với đường dẫn, query, request body, headers, response status và các giới hạn bảo mật được quản lý rõ ràng.

Bối cảnh rộng hơn của Spring Cloud Gateway bao gồm route predicate, filter chain, biến đổi path/header, service discovery, xác thực, rate limiting, circuit breaker, retry, TLS và quan sát request. Tuy nhiên, một điểm quan trọng phải ghi nhớ: **Proxy Exchange là một biến thể kiến trúc riêng, không phải Gateway Server WebFlux/Server MVC route engine được thu nhỏ vào một controller**. Các phần tiếp theo chỉ rõ thành phần nào cần tích hợp riêng để không mặc định các filter hoặc cấu hình của Gateway Server sẽ được áp dụng.

> **Phạm vi phiên bản:** Ví dụ dựa trên dòng Spring Cloud Gateway có các artifact `spring-cloud-gateway-proxyexchange-webmvc` và `spring-cloud-gateway-proxyexchange-webflux`, được tài liệu hóa trong các dòng 4.3/5.0. Ở các bản cũ, artifact có thể mang tên `spring-cloud-gateway-mvc` hoặc `spring-cloud-gateway-webflux`. Hãy chọn một cặp **Spring Boot + Spring Cloud release train** tương thích. Các API method và cơ chế tùy biến body/header cần được kiểm tra với Javadoc đúng phiên bản trước khi phát hành. URI trong ví dụ là localhost của **môi trường lab**, không phải một open proxy dành cho Internet.

## 1. Proxy Exchange khác Gateway Server ở điểm nào?

Spring Cloud Gateway có hai kiểu sử dụng chính:

| Tiêu chí | **Proxy Exchange** | **Gateway Server WebFlux / Server MVC** |
|---|---|---|
| Cách khai báo | `@RestController` / `@RequestMapping` + tham số `ProxyExchange<T>` | Route definitions hoặc Java route DSL |
| Điều kiện chọn request | Spring MVC/WebFlux handler mapping, annotations | Gateway route predicates |
| Gửi request downstream | Gọi `proxy.uri(...).get()/post()/...` trong controller | Routing handler/filter do Gateway Server điều phối |
| Biến đổi request | Mã controller và API `ProxyExchange` | GatewayFilter/HandlerFilterFunctions |
| Bảo mật | Spring Security của web stack và logic controller | Security tương ứng cộng Gateway route/filter policy |
| Rate limiting, Retry, CircuitBreaker | Cần thiết kế/tích hợp tại controller, client hoặc middleware | Có built-in factories/integration tùy Server stack |
| Phù hợp | BFF, endpoint proxy chọn lọc, logic gắn với controller | API Gateway nhiều routes, policies nhất quán, routing quy mô lớn |
| Điểm cần tránh | Dễ tự tạo open proxy hoặc body buffering | Dễ nhầm route filter order và cấu hình gateway |

Tài liệu chính thức của **Proxy Exchange** nêu rõ đây là **một phong cách Gateway thay thế**; hướng dẫn Gateway Server không tự động áp dụng nguyên xi.

### Luồng xử lý cơ bản

~~~mermaid
sequenceDiagram
    participant C as Client
    participant W as Spring MVC/WebFlux + Security
    participant P as Controller với ProxyExchange
    participant B as Backend microservice
    C->>W: GET /bff/catalog/42
    W->>W: Handler mapping + authentication
    W->>P: Inject ProxyExchange
    P->>P: Chọn URI backend từ allowlist
    P->>B: proxy.uri(target).get()
    B-->>P: 200 + JSON + headers
    P-->>W: ResponseEntity
    W-->>C: 200 + JSON
~~~

**ProxyExchange không tự quyết định đường dẫn nào được public.** Đó là trách nhiệm của annotation như `@GetMapping`, `@PostMapping`, `@RequestMapping(method=...)`, cùng Spring Security và kiểm tra nghiệp vụ.

## 2. Chọn đúng dependency và web stack

Các artifact dành riêng cho Proxy Exchange trong các dòng hiện đại:

~~~groovy
// Chỉ chọn MỘT trong hai loại runtime dưới đây.
// Version do Spring Cloud BOM phù hợp quản lý.

// Ứng dụng Spring MVC / Servlet:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-gateway-proxyexchange-webmvc'
}

// HOẶC ứng dụng Spring WebFlux / reactive:
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-gateway-proxyexchange-webflux'
}
~~~

Đây là **hai phương án build độc lập**, không phải file Gradle để copy cả hai nhóm `dependencies` vào một ứng dụng. Nếu dự án đang dùng bản cũ, kiểm tra bảng đổi tên artifact giữa release trains trước khi copy tọa độ.

| Trường hợp | Import lớp | Return type controller phổ biến |
|---|---|---|
| **MVC** | `org.springframework.cloud.gateway.mvc.ProxyExchange` | `ResponseEntity<?>` |
| **WebFlux** | `org.springframework.cloud.gateway.webflux.ProxyExchange` | `Mono<ResponseEntity<?>>` |

Với MVC, request chạy trên servlet stack; với WebFlux, handler trả một reactive publisher. **Không gọi `block()` để biến `Mono` thành giá trị đồng bộ trong event loop** và không import `ProxyExchange` của một stack vào stack kia.

### Không nhầm dependency

- `spring-cloud-starter-gateway-server-webflux` dành cho **Gateway Server WebFlux**, không phải tên chuẩn thay thế cho `proxyexchange-webflux`.
- `spring-cloud-starter-gateway-server-webmvc` dành cho **Gateway Server Web MVC**, không đồng nghĩa controller `ProxyExchange` đã được cấu hình cùng hành vi.
- Các tên artifact cũ `spring-cloud-gateway-mvc` / `spring-cloud-gateway-webflux` có thể xuất hiện ở code cũ; đừng trộn hai dòng release chỉ vì package import giống nhau.
- Không ép version Spring Framework/HTTP client khác với BOM để một phương thức Java “compile được”.

## 3. Đối tượng ProxyExchange được tạo và sử dụng như thế nào?

Trong một controller, Spring tạo/cung cấp `ProxyExchange<T>` làm **tham số của handler method**, nhờ argument resolver được đăng ký qua module tương ứng.

Ví dụ tối thiểu MVC theo tài liệu:

~~~java
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PingProxyController {

    @GetMapping("/bff/ping")
    ResponseEntity<?> ping(ProxyExchange<byte[]> proxy) throws Exception {
        return proxy.uri("http://localhost:9090/ping").get();
    }
}
~~~

Luồng:

1. `@GetMapping("/bff/ping")` match incoming **GET**.
2. Spring inject một `ProxyExchange<byte[]>` vào phương thức controller.
3. `uri(...)` chọn URI **downstream**.
4. `get()` thực hiện một HTTP GET downstream.
5. `ResponseEntity<?>` đóng gói status, headers và body trả về.

**`ProxyExchange<T>` dùng kiểu generic `T` của representation/response body**, không phải một cách khai báo HTTP method hay đảm bảo body được stream. Sử dụng `byte[]` để minh họa response raw bytes, nhưng phải giới hạn response size/concurrency trong production.

### Chuỗi gọi có thể cấu hình trước khi gửi

~~~text
Incoming request
    -> Spring handler + method mapping
    -> ProxyExchange argument
    -> uri(trustedTarget)
    -> (optional) body(requestBody)
    -> (optional) header(name, value)
    -> get() / post() / put() / patch() / delete() / head() / options()
    -> ResponseEntity downstream
    -> ResponseEntity client
~~~

Các bước trên minh họa **ý nghĩa API**. Nếu có header filtering hoặc response mapper, chúng phụ thuộc API phiên bản và được trình bày trong phần sau.

## 4. GET: chuyển tiếp request không có body

Tình huống: client gọi `GET /bff/catalog/42`; controller chuyển thành `GET http://localhost:9090/catalog/items/42`.

~~~java
package example.bff;

import java.net.URI;

import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogProxyController {

    private static final URI CATALOG_ORIGIN =
        URI.create("http://localhost:9090");

    @GetMapping("/bff/catalog/{id}")
    public ResponseEntity<?> getItem(
            @PathVariable long id,
            ProxyExchange<byte[]> proxy) throws Exception {

        String target = CATALOG_ORIGIN.resolve(
            "/catalog/items/" + id).toString();

        return proxy.uri(target).get();
    }
}
~~~

**Vì sao dùng `long id`?** `@PathVariable long` chỉ cho phép một kiểu định danh số hữu hạn, giảm nguy cơ chèn slash, query hoặc URI scheme qua biến path. Với định danh chuỗi, phải có quy tắc charset/length và encode **từng path segment**, không nối raw user input vào một URI.

### Test hai hop

~~~bash
# Gọi thẳng backend (đối chứng):
curl -i "http://localhost:9090/catalog/items/42"

# Gọi qua controller Proxy Exchange:
curl -i "http://localhost:8080/bff/catalog/42"
~~~

Kiểm tra **method, path, status, body, content type** ở backend và client. Đừng chỉ nhìn HTTP 200; controller vẫn có thể trả 200 từ một handler khác nếu mapping bị trùng.

### GET với query parameters

ProxyExchange có tiện ích `path(...)` để lấy suffix từ incoming request, nhưng **không nên mặc định việc ghép path đã tự giữ nguyên, chuẩn hóa và encode mọi query parameter**. Khi cần forward query, xây URI đích từ dữ liệu đã validate bằng `UriComponentsBuilder`.

~~~java
import java.net.URI;
import org.springframework.web.util.UriComponentsBuilder;
import org.springframework.web.bind.annotation.RequestParam;

@GetMapping("/bff/search")
public ResponseEntity<?> search(
        @RequestParam(defaultValue = "vi") String lang,
        @RequestParam(defaultValue = "1") int page,
        ProxyExchange<byte[]> proxy) throws Exception {

    if (!lang.equals("vi") && !lang.equals("en")) {
        throw new IllegalArgumentException("Unsupported language");
    }
    if (page < 1 || page > 100) {
        throw new IllegalArgumentException("Invalid page");
    }

    String target = UriComponentsBuilder
        .fromUri(URI.create("http://localhost:9090"))
        .path("/catalog/search")
        .queryParam("lang", lang)
        .queryParam("page", page)
        .build()
        .encode()
        .toUriString();

    return proxy.uri(target).get();
}
~~~

Đoạn trên minh họa phần **method của controller**. Với input ngoài range, ứng dụng nên có `@ControllerAdvice` chuyển validation errors thành HTTP 400 thay vì mặc định lộ exception detail. Nếu backend cần query có giá trị lặp hoặc thứ tự quan trọng, phải có contract riêng thay vì tự parse thành một Map làm mất thông tin.

## 5. POST: chuyển request có body sang backend

`POST` thường mang JSON tạo một resource. Với ProxyExchange MVC, bạn có thể đọc body ở handler rồi đặt body cho request downstream bằng `proxy.body(...)`.

~~~java
import org.springframework.cloud.gateway.mvc.ProxyExchange;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
    path = "/bff/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> createOrder(
        @RequestBody byte[] body,
        ProxyExchange<byte[]> proxy) throws Exception {

    if (body.length > 64 * 1024) {
        return ResponseEntity.status(413).build();
    }

    return proxy
        .uri("http://localhost:9091/orders")
        .body(body)
        .post();
}
~~~

**Lưu ý về snippet:** Đoạn trên là một **handler method** đặt bên trong `@RestController`; phần import/controller class đã được trình bày ở phần 4. `@RequestBody byte[]` biểu diễn raw bytes để tránh biến đổi JSON ngoài ý muốn. Tuy nhiên, **nó vẫn materialize toàn bộ request body trong bộ nhớ controller**; kiểm tra `body.length` sau khi đọc **không chặn được tất cả chi phí memory/DoS lúc đọc**. Cần giới hạn request size ở ingress/web server và codec/body resolver trước khi đọc.

### Không phải mọi POST đều nên proxy nguyên xi

| Kiểu POST | Mục tiêu | Lưu ý |
|---|---|---|
| Tạo order JSON nhỏ | BFF chuyển sang orders backend | Idempotency key, validation và authorization |
| Upload multipart lớn | Chuyển file/từng part | Không tự assume `byte[]` xử lý streaming/multipart hiệu quả |
| Thanh toán | Thực hiện side effect nhạy cảm | Không retry tùy tiện; chống duplicate charge |
| Callback/webhook | Nhận chữ ký trên raw body | Không đổi bytes/header trước xác minh chữ ký |
| POST tạo tác vụ dài | Async job | Cân nhắc 202 Accepted + polling thay vì chờ lâu |

**`proxy.body(body).post()` không tự validate JSON schema, ownership hay rate limit**. Những việc đó vẫn là trách nhiệm của Spring web layer và backend.

### Trường hợp body đã được decode thành DTO

Có thể truyền một object làm body theo API `body(Object)`, nhưng khi ấy quá trình serialization có thể **thay bytes** so với payload gốc. Điều này quan trọng với HMAC/webhook signature, canonical JSON, content length và charset. Dùng DTO khi chủ đích là **chuyển đổi nội dung**, và kiểm thử Content-Type/encoding/status thay vì coi đó là byte-transparent proxy.

## 6. PUT và PATCH: khác nhau về hợp đồng cập nhật

Theo HTTP semantics, **PUT** thường biểu diễn việc tạo/thay thế trạng thái resource đích theo representation gửi đi, với tính chất *idempotent* nếu backend thực thi đúng. **PATCH** biểu diễn một tập thay đổi, **không mặc định idempotent**.

### PUT một resource

~~~java
import org.springframework.web.bind.annotation.PutMapping;

@PutMapping(
    path = "/bff/items/{id}",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<?> replaceItem(
        @PathVariable long id,
        @RequestBody byte[] body,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .body(body)
        .put();
}
~~~

### PATCH một resource

~~~java
import org.springframework.web.bind.annotation.PatchMapping;

@PatchMapping(
    path = "/bff/items/{id}",
    consumes = "application/merge-patch+json")
public ResponseEntity<?> patchItem(
        @PathVariable long id,
        @RequestBody byte[] patch,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .body(patch)
        .patch();
}
~~~

Đây là hai **handler methods** minh họa để đặt trong `@RestController`. Các URI mẫu được cố định theo allowlist; không nhận target host từ client.

| Tiêu chí | PUT | PATCH |
|---|---|---|
| Mục đích | Đặt representation/trạng thái mong muốn | Thực hiện các thay đổi riêng phần |
| Body | Representation tài nguyên | Patch document theo media type |
| Content-Type ví dụ | `application/json` | `application/merge-patch+json` hoặc `application/json-patch+json` |
| Idempotency | Theo semantics HTTP: idempotent | Phụ thuộc loại patch và operation |
| Retry ở Gateway/BFF | Chỉ khi backend thực sự bảo toàn semantics | Thường cần idempotency key hoặc logic tránh lặp |
| Concurrent updates | Cần ETag/version khi phù hợp | Càng quan trọng với thao tác cộng/trừ/append |

**Đừng biến PATCH thành PUT chỉ để tránh thiếu API ở một phiên bản.** Nếu runtime thật không hỗ trợ `patch()` hoặc HTTP client chưa hỗ trợ method đó đúng, phải chọn phiên bản/transport phù hợp và viết integration test cho method thực tế.

## 7. DELETE: không có body không nghĩa là không nguy hiểm

Một controller có thể chuyển DELETE bằng `delete()`:

~~~java
import org.springframework.web.bind.annotation.DeleteMapping;

@DeleteMapping("/bff/items/{id}")
public ResponseEntity<?> deleteItem(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .delete();
}
~~~

**Điểm kiểm soát quan trọng:**

- Phải xác thực và phân quyền user trên **resource ID cụ thể**; annotation `@DeleteMapping` chỉ chọn method, không xác minh quyền xóa.
- Một response `204 No Content` phải được chuyển thành response **không có body**; tránh serializer tự thêm JSON không mong muốn.
- Trường hợp resource đã xóa có thể trả 404/204 tùy backend contract; không ép mọi response về 200.
- Semantics DELETE là idempotent về **trạng thái đích**, nhưng status phản hồi giữa lần đầu và lần sau có thể khác.
- Cần audit và idempotency/concurrency policy nếu xóa kéo theo side effect bên ngoài (email, thanh toán, workflow).

Ở những API ProxyExchange thông dụng, `delete()` không có tham số body. **Đừng giả định DELETE có body sẽ được forward nguyên vẹn**, vì HTTP client/server/proxy có thể xử lý body của DELETE khác nhau. Nếu bắt buộc có body, cần kiểm chứng API và downstream contract cụ thể.

## 8. HEAD và OPTIONS: method hỗ trợ nhưng semantics đặc biệt

Các API ProxyExchange MVC được tài liệu hóa có `head()` và `options()`. Cần kiểm tra Javadoc của **module/phiên bản thực tế**, nhất là khi dùng WebFlux API ở một dòng khác.

### HEAD

HEAD tương tự GET về metadata, nhưng response **không được chứa response body**.

~~~java
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;

@RequestMapping(path = "/bff/items/{id}", method = RequestMethod.HEAD)
public ResponseEntity<?> headItem(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .head();
}
~~~

Kiểm tra `Content-Length`, `ETag`, `Last-Modified` và những response headers khác **theo contract backend**. Không dùng `get()` rồi tự trả body để giả lập HEAD nếu framework/proxy có phương thức HEAD hỗ trợ.

### OPTIONS

OPTIONS cho biết capabilities/communication options của target resource, thường có header `Allow` trong một số response. Nhưng **CORS preflight của browser** cũng dùng OPTIONS, với headers `Origin` và `Access-Control-Request-*`; việc có `proxy.options()` **không làm tự động có CORS policy đúng**.

~~~java
@RequestMapping(path = "/bff/items/{id}", method = RequestMethod.OPTIONS)
public ResponseEntity<?> optionsItem(
        @PathVariable long id,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/items/" + id)
        .options();
}
~~~

**Cảnh báo thực tế:** Servlet/Spring Security/CORS filter có thể xử lý OPTIONS *trước khi* request đến controller. Do đó ở production, không nhất thiết có một controller proxy OPTIONS. Nếu định forward OPTIONS, hãy quyết định rõ trách nhiệm giữa BFF, ingress và backend, sau đó test browser preflight thay vì chỉ dùng một lệnh cURL OPTIONS không có Origin.

### Method không có helper hoặc method mở rộng

`TRACE`, `CONNECT`, HTTP extension methods hoặc WebSocket upgrade **không được tự coi là có phương thức `proxy.trace()` hay `proxy.connect()`**. Nếu cần proxy chuyên dụng cho những protocol ấy, hãy dùng một component/client/gateway hỗ trợ đúng protocol, hoặc trả 405/501 theo policy. Không cố đổi chúng thành GET/POST vì có thể phá HTTP semantics hoặc mở lỗ hổng.

## 9. So sánh các method trong một bảng thao tác

| Incoming method | Controller annotation | ProxyExchange call | Body cần kiểm tra | Status phổ biến cần giữ nguyên |
|---|---|---|---|---|
| GET | `@GetMapping` | `.get()` | Thường không có | 200, 304, 404, 5xx |
| POST | `@PostMapping` | `.body(body).post()` | Có thể lớn/nhạy cảm | 200, 201, 202, 400, 409 |
| PUT | `@PutMapping` | `.body(body).put()` | Representation của resource | 200, 201, 204, 409, 412 |
| PATCH | `@PatchMapping` | `.body(body).patch()` | Patch document | 200, 204, 409, 412, 422 |
| DELETE | `@DeleteMapping` | `.delete()` | Thường không có; không giả định replay | 200, 202, 204, 404 |
| HEAD | `@RequestMapping(HEAD)` | `.head()` khi hỗ trợ | Không có response body | 200, 304, 404, 5xx |
| OPTIONS | `@RequestMapping(OPTIONS)` | `.options()` khi hỗ trợ | Thường không có | 200, 204, 405 |
| TRACE/CONNECT | Không expose tùy tiện | Không giả định có helper | Đặc thù protocol | Thường bị hạn chế |

**Bảng là định hướng về HTTP contract**, không cam kết framework tự gán status theo từng method. Backend trả status nào phải được kiểm tra, và BFF chỉ đổi status khi có **hợp đồng chuyển đổi rõ ràng**.

### Nếu nhiều method cùng dùng chung một target

Có thể dùng `@RequestMapping(path=..., method={...})` để match nhiều methods, sau đó dispatch bằng `switch`/`if` đến những helper được hỗ trợ. Tuy nhiên, đừng gom tất cả methods vào một controller khi policy auth/validation/body size khác nhau. **Handler tách theo method** thường dễ test và ngăn vô tình chuyển DELETE qua GET.

## 10. WebFlux: cùng ý tưởng nhưng trả Mono<ResponseEntity<?>>

Trong ứng dụng dùng `spring-cloud-gateway-proxyexchange-webflux`, import và return type khác:

~~~java
package example.bff.reactive;

import java.net.URI;

import org.springframework.cloud.gateway.webflux.ProxyExchange;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveCatalogProxyController {

    private static final URI CATALOG =
        URI.create("http://localhost:9090");

    @GetMapping("/bff/catalog/{id}")
    public Mono<ResponseEntity<?>> getItem(
            @PathVariable long id,
            ProxyExchange<byte[]> proxy) throws Exception {

        return proxy
            .uri(CATALOG.resolve("/catalog/items/" + id).toString())
            .get();
    }
}
~~~

**Không dùng cùng lúc hai controller MVC/WebFlux có mapping trùng** trong một ứng dụng. Chọn stack rõ ràng.

Ví dụ POST WebFlux:

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;

@PostMapping(
    path = "/bff/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<ResponseEntity<?>> createOrder(
        @RequestBody byte[] body,
        ProxyExchange<byte[]> proxy) throws Exception {

    if (body.length > 64 * 1024) {
        return Mono.just(ResponseEntity.status(413).build());
    }

    return proxy.uri("http://localhost:9091/orders")
        .body(body)
        .post();
}
~~~

Đoạn này là method minh họa trong controller WebFlux. `@RequestBody byte[]` vẫn **gom request body** trong bộ nhớ trước khi gọi `post()`; viết kiểu reactive không biến đoạn code thành **streaming upload**. Nếu cần proxy file lớn, SSE, WebSocket hoặc full duplex, hãy đánh giá **Gateway Server WebFlux**/routing chuyên dụng và giới hạn body ở mọi tầng.

### Không tự subscribe hoặc block

~~~java
// Không nên viết trong controller WebFlux:
proxy.uri(target).get().subscribe(...);

// Cũng không nên block event-loop để lấy ResponseEntity:
ResponseEntity<?> response = proxy.uri(target).get().block();
~~~

Publisher do controller trả về phải được **framework subscribe và quản lý lifecycle**. Nếu cần thêm xử lý, compose bằng `map`/`flatMap`/`onErrorResume` phù hợp; tránh swallow lỗi thật hoặc lộ nguyên stack trace cho client.

## 11. Đường dẫn và query: đừng xây URI bằng chuỗi chưa kiểm tra

Một pattern tiện dùng là lấy suffix của request:

~~~java
@GetMapping("/bff/files/**")
public ResponseEntity<?> fileProxy(
        ProxyExchange<byte[]> proxy) throws Exception {

    String tail = proxy.path("/bff/files/");
    return proxy.uri("http://localhost:9092/files/" + tail).get();
}
~~~

Ví dụ minh họa tiện ích `proxy.path(...)` có trong tài liệu. **Không xem đây là giải pháp chống SSRF/path traversal hoàn chỉnh.** Nếu suffix do client kiểm soát được ghép trực tiếp thành URI, có thể có những trường hợp encoding/`?`/`#`/`..`, slash lặp, percent-encoded slash hoặc URL normalization làm Gateway và backend hiểu khác nhau.

### Quy trình an toàn hơn

1. Chỉ lựa chọn từ **origin/target đã được duyệt**.
2. Sử dụng path variables có kiểu dữ liệu/regex rõ ràng (ví dụ `long id`).
3. Với một path segment chuỗi, validate charset, độ dài, rồi encode đúng **từng segment**.
4. Với query params, dùng `UriComponentsBuilder` và preserve repeated values khi nghiệp vụ yêu cầu.
5. Test những URI có Unicode, whitespace, `%2F`, `..`, `?`, `#`, query trùng.
6. Kiểm tra backend thực nhận request path/query nào.
7. Không cho một param như `targetUrl`, `host`, `callback` quyết định URI outbound khi chưa có allowlist.

### Tránh open proxy/SSRF

Không nên:

~~~java
// PHẢN VÍ DỤ: biến controller thành open proxy có nguy cơ SSRF.
@GetMapping("/bff/proxy")
ResponseEntity<?> unsafe(
        @RequestParam String url,
        ProxyExchange<byte[]> proxy) throws Exception {
    return proxy.uri(url).get();
}
~~~

Đầu vào `url` có thể bị thay bằng `http://127.0.0.1/...`, host metadata hoặc endpoint nội bộ không được phép. **Không dùng ví dụ này trong ứng dụng thật.**

Thay vào đó, dùng lựa chọn mã đích:

~~~java
@GetMapping("/bff/public-info")
ResponseEntity<?> safe(
        @RequestParam String source,
        ProxyExchange<byte[]> proxy) throws Exception {

    String target = switch (source) {
        case "catalog" -> "http://localhost:9090/catalog/public-info";
        case "articles" -> "http://localhost:9093/articles/public-info";
        default -> null;
    };

    if (target == null) {
        return ResponseEntity.badRequest().build();
    }
    return proxy.uri(target).get();
}
~~~

Snippet `switch` này dùng cú pháp Java hiện đại; target URIs **được server định nghĩa**, không đến từ chuỗi tự do của client. Với production cần bổ sung quyền chọn target, TLS, egress controls, rate limit và SSRF defense-in-depth.

## 12. Request headers: nhạy cảm, skipped và forwarded

Ở các dòng Proxy Exchange được tài liệu hóa, có các loại header đặc biệt:

- **Sensitive headers:** theo mặc định phổ biến gồm `Cookie` và `Authorization`, **không được tự động đưa vào downstream request**.
- **Skipped headers:** theo tài liệu các dòng mới gồm `Content-Length` và `Host`, vì gửi nguyên chúng có thể sai khi body/host của request downstream khác request incoming.
- **Proxy/forwarding headers:** hỗ trợ các header kiểu `X-Forwarded-*`; phải kiểm tra nguồn tin cậy và hành vi append/rewrite đúng phiên bản.

Ví dụ khi chuyển POST từ BFF:

~~~http
POST /bff/orders HTTP/1.1
Host: bff.example.test
Authorization: Bearer client-token
Cookie: SESSION=client-session
Content-Type: application/json
Content-Length: 25

{"itemId":42,"qty":1}
~~~

Downstream request **không nên được giả định giống hệt byte-for-byte**. Client HTTP mà ProxyExchange dùng có thể tạo `Host` mới và tính lại framing; `Authorization`/`Cookie` có thể bị bỏ theo sensitive policy.

### Vì sao Authorization/Cookie thường bị bỏ?

Một client token có thể có audience chỉ dành cho BFF, không dành cho backend. Chuyển nguyên token/cookie sang service khác có thể:

- Lộ credentials qua trust boundary.
- Làm backend chấp nhận bearer token không đúng audience.
- Vô tình chia sẻ session cookie không dành cho downstream host.
- Khi debug, đưa token vào log/trace của nhiều service hơn cần thiết.

Nếu backend thật sự cần xác thực BFF, hãy thiết kế **service-to-service authentication**, mTLS, token exchange hoặc downstream token riêng phù hợp audience. **Không tắt sensitive filtering cho toàn ứng dụng chỉ để một testcase chạy qua.**

### Set header theo hợp đồng

~~~java
return proxy
    .uri("http://localhost:9090/catalog/items/42")
    .header("X-Edge-Request-Id", "lab-correlation-123")
    .get();
~~~

`header(name, value...)` thiết lập một header cho **downstream call**. Giá trị trong lab là hằng số, nhưng trong production correlation ID nên do một nguồn đáng tin tạo/chuẩn hóa, không lấy raw user input. Tránh thêm header định danh như `X-Authenticated-User` hoặc `X-Tenant-Id` nếu backend chưa có trust contract.

### Hop-by-hop headers

Những headers như `Connection`, `Keep-Alive`, `Proxy-Authenticate`, `Proxy-Authorization`, `TE`, `Trailer`, `Transfer-Encoding`, `Upgrade` và các tên được liệt kê bởi `Connection` có semantics **mỗi hop**. Một HTTP proxy đúng phải không phát lại tùy tiện những giá trị không còn phù hợp.

Không mặc định tất cả trường hợp đặc biệt đều được ProxyExchange tự xử lý hoàn hảo theo mọi version/protocol. Nếu tự sao chép `HttpHeaders` hoặc response mapper, hãy loại những headers không nên đi xuyên hop và test raw HTTP.

## 13. Response status/body/headers: bảo toàn hợp đồng downstream

`ProxyExchange.get()` và các method tương ứng trả về một `ResponseEntity` trong MVC hoặc `Mono<ResponseEntity>` trong WebFlux. Dựa trên body/status/headers của downstream, controller có thể **trả nguyên** hoặc **chủ động biến đổi**.

| Downstream trả | BFF nên cân nhắc |
|---|---|
| `200 OK` + JSON | Trả đúng content type và body |
| `201 Created` + `Location` | Giữ ý nghĩa resource mới, kiểm tra Location có thể tiết lộ host nội bộ |
| `202 Accepted` | Giữ semantic tác vụ async |
| `204 No Content` | Không thêm body |
| `304 Not Modified` | Không phát body; xử lý validator đúng |
| `400/422` | Lỗi input; không tự biến thành 500 |
| `401/403` | Không trả 200/fallback thành công làm mất ý nghĩa bảo mật |
| `404` | Giữ nghĩa resource không tồn tại theo API contract |
| `409/412` | Trạng thái conflict/concurrency; không retry mù quáng |
| `429` + `Retry-After` | Tôn trọng quota và chỉ thị chờ theo contract |
| `502/503/504` | Phân biệt downstream lỗi và lỗi chính HTTP client |

**Không phải mọi non-2xx do downstream trả đều là Java exception.** Cơ chế HTTP client và cách ProxyExchange map status có thể ảnh hưởng, nên phải test thực tế các mã 4xx/5xx thay vì suy từ một đường GET 200.

### Response mapper khi cần sửa header

Tài liệu Proxy Exchange cung cấp overload cho các HTTP verb nhận một **mapper** chuyển đổi `ResponseEntity` downstream thành `ResponseEntity` trả client.

Ví dụ ý tưởng (phù hợp với MVC API có `get(Function<...>)`):

~~~java
@GetMapping("/bff/public/42")
public ResponseEntity<?> publicItem(
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9090/catalog/items/42")
        .get(response -> {
            // Ví dụ: chặn đưa header triển khai nội bộ ra client.
            org.springframework.http.HttpHeaders outgoing =
                new org.springframework.http.HttpHeaders();

            outgoing.putAll(response.getHeaders());
            outgoing.remove("X-Internal-Backend-Node");

            return new ResponseEntity<>(
                response.getBody(),
                outgoing,
                response.getStatusCode());
        });
}
~~~

**Đoạn này chỉ là mẫu response mapping**. Phải xem HTTP hop-by-hop headers, `Set-Cookie`, `Location`, CORS, `Content-Length`, `ETag`, `Content-Encoding` và các headers phụ thuộc body trước khi chuyển tiếp. Nếu sửa body, phải xét lại mọi metadata liên quan.

Không tự thêm `Cache-Control: public` cho response có dữ liệu tenant hoặc chứa thông tin cá nhân. Chức năng response mapping **không thay thế response cache correctness**.

## 14. MVC forward() khác HTTP proxy đến backend

Ở **Proxy Exchange MVC**, tài liệu còn mô tả phương thức `forward(String)` để **forward đến handler nội bộ trong cùng ứng dụng**.

~~~java
@GetMapping("/bff/local")
public String localForward(
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy.forward("/internal/handler");
}
~~~

**Lưu ý:** Return type/behavior chính xác của `forward(...)` phụ thuộc API MVC phiên bản và cách Spring MVC xử lý forward view/dispatcher. Ví dụ trên minh họa ý nghĩa **forward nội bộ**, không phải outbound HTTP call và **không nên copy khi chưa đối chiếu Javadoc**. Không mặc định WebFlux Proxy Exchange có cùng phương thức `forward`.

| Hành vi | `proxy.uri(...).get()` | `proxy.forward(...)` MVC |
|---|---|---|
| Đi qua network tới service khác | Có, nếu URI ở server khác | Không; forward nội bộ tới handler |
| Có downstream HTTP status/body riêng | Có | Theo handler trong ứng dụng |
| Cần egress/TLS policy | Có | Không qua outbound hop, nhưng cần kiểm soát handler/path |
| Rủi ro | SSRF, lộ headers, timeout/downstream errors | Vượt handler/management path nếu forward sai |

Không cho user quyết định freely path forward vào `/actuator` hoặc endpoint nội bộ có quyền cao. Forward là công cụ điều phối trong app, **không phải cơ chế cấp quyền**.

## 15. Body, streaming, multipart và giới hạn kích thước

Đối với ProxyExchange, dùng `byte[]` làm body và response có ưu điểm đơn giản nhưng tạo **chi phí bộ nhớ** đáng kể:

- `@RequestBody byte[]` giữ payload trong bộ nhớ khi handler nhận request.
- `ProxyExchange<byte[]>` có thể giữ response body dưới dạng byte array.
- Nhiều requests đồng thời có thể nhân bộ nhớ theo kích thước body và response.
- Nếu backend phản hồi stream dài/SSE, mô hình `ResponseEntity<byte[]>` không phù hợp cho **unbounded stream**.
- Với multipart, việc decode/encode lại có thể thay `boundary` và `Content-Length`.

### Tác động đến upload file

| Upload | Gợi ý |
|---|---|
| JSON nhỏ, giới hạn 64 KiB | ProxyExchange với body đã validate có thể hợp lý |
| File 100 MiB hoặc nhiều GiB | Cân nhắc Gateway Server streaming hoặc upload service chuyên dụng |
| Multipart nhiều part | Kiểm thử boundary, temp storage và body converter |
| File có chữ ký/checksum | Không sửa raw bytes trước khi kiểm chứng |
| Upload resumable | Dùng API có part IDs, offsets, checksums, idempotency |

Không tăng toàn bộ codec buffer/Servlet multipart limits vô hạn để “khắc phục ProxyExchange”. Nếu cần streaming end-to-end với backpressure, một full Gateway Server phù hợp hơn BFF controller nhận toàn bộ byte arrays.

### Download Range/206

Client có thể gửi `Range: bytes=0-1023`, backend trả `206 Partial Content` và `Content-Range`. Khi ProxyExchange thực hiện GET, cần xác minh incoming Range header có được chuyển sang downstream theo policy không, và response có giữ status, body length, `ETag`/`Content-Range` đúng không.

**Không tự ghép nhiều ranges hoặc đổi bytes rồi giữ `Content-Range` cũ.** Nếu BFF cần download file lớn, `byte[]` có thể làm memory tăng tương ứng; ưu tiên thiết kế download streaming rõ ràng.

## 16. Retry, CircuitBreaker, RateLimiter và service discovery trong Proxy Exchange

Vì đây là **controller-style proxy**, không mặc định những factory `Retry`, `RequestRateLimiter`, `CircuitBreaker` hoặc route predicates của **Gateway Server** sẽ chạy chỉ vì chúng có trên classpath.

### Những lớp bảo vệ phải thiết kế riêng

| Nhu cầu | Cách tiếp cận ở Proxy Exchange |
|---|---|
| Authentication | Spring Security MVC/WebFlux tương ứng |
| Authorization | Kiểm tra principal/scopes/resource ownership trước outbound call |
| Rate limit | Servlet/WebFlux filter, middleware, backend limit hoặc component điều phối phù hợp |
| Retry | HTTP client/retry policy có bounded attempts + backoff + deadline |
| Circuit breaker | Resilience4j/Spring Cloud CircuitBreaker hoặc client wrapper được tích hợp đúng stack |
| Service discovery | Client resolver/load balancer/service catalog do ứng dụng sử dụng; không giả định `ProxyExchange.uri("lb://...")` được hỗ trợ như Gateway Server |
| TLS | HTTPS client trust store/certificate validation + mTLS nếu cần |
| Observability | Micrometer/tracing spans theo controller, target service, status và latency |
| Response cache | Policy cache riêng; tránh shared-cache dữ liệu user |

### Không giả định `lb://` hoạt động ở ProxyExchange

Trong Gateway Server, URI `lb://service-id` có ý nghĩa đặc biệt qua load-balancer filter chain. ProxyExchange thường nhận URI mà HTTP client của module sẽ gọi. **Đừng tự thay**:

~~~java
proxy.uri("lb://catalog-service/catalog/items/42").get();
~~~

rồi kỳ vọng Gateway Server LoadBalancer filter sẽ xử lý nó. Nếu cần service discovery, sử dụng cơ chế URI resolution/client integration được **tài liệu hóa cho đúng phiên bản Proxy Exchange**, hoặc giải quyết đích được phép ở application layer. Tránh tự ghép hostname từ request client.

### Retry có thể lặp side effect

Một POST thanh toán có thể được backend **xử lý thành công** nhưng response mất trên đường về; retry từ BFF sẽ gửi lại một POST. Do đó:

- Không retry POST/PATCH mù quáng.
- Thiết kế idempotency key được **backend thực thi**.
- Giới hạn attempts, backoff, per-attempt timeout và **overall deadline**.
- Đừng retry 401/403 hoặc lỗi đầu vào 400/422 như outage.
- Khi có `429`/`Retry-After`, tuân theo quota policy.
- Nếu client của BFF đã có retry và backend SDK cũng có retry, tổng outbound attempts có thể nhiều hơn dự tính.

### Circuit breaker và lỗi

Một circuit breaker bảo vệ call đến downstream có thể tạo fallback JSON. **Không biến mọi lỗi backend thành 200**; với API cần failure semantics, trả 503/504 hoặc mã contract thích hợp. Nếu response đã commit (streaming), không thể luôn chuyển thành JSON fallback mới.

## 17. Bảo mật: không biến BFF thành open proxy

Controller proxy có quyền gửi HTTP request từ máy chủ BFF. Nếu caller tự quyết định target URL, một endpoint public có thể trở thành **SSRF entrypoint**.

~~~mermaid
flowchart TD
    U["Client"] --> A["Spring Security + input validation"]
    A --> D{"Target code được duyệt?"}
    D -->|Không| R["400/403 + audit"]
    D -->|Có| M["Mapping server-side → URI"]
    M --> E["Network egress + DNS/TLS policy"]
    E --> B["Downstream service"]
    B --> C["Response mapper + header safety"]
    C --> U
    X["Raw url/host từ client"] -.->|"Không được dùng trực tiếp"| M
~~~

### Chính sách tối thiểu

1. **Chỉ định origins/targets từ cấu hình đã duyệt**, không để caller truyền URI tự do.
2. **Validate mọi path/query segment** và kiểm soát URL encoding; không ghép raw path/query tùy ý.
3. **Chặn đích nội bộ nhạy cảm** bằng egress firewall/NetworkPolicy, không chỉ kiểm tra chuỗi hostname.
4. Với HTTPS, **không tắt TLS certificate/hostname verification**; nếu cần client identity, dùng mTLS đúng hợp đồng.
5. Không tự forward `Authorization`/`Cookie` qua trust boundary khi không cần. Dùng service identity nếu backend cần.
6. Không tin `X-Forwarded-For`, `Host`, `X-Authenticated-User`, `X-Tenant-Id` từ client làm bằng chứng xác thực.
7. Dùng **Spring Security** kiểm tra quyền truy cập controller và resource trước outbound call.
8. Giới hạn body size, response size, timeout, connection pool và số calls đồng thời.
9. Không log raw tokens, cookies, request body nhạy cảm, query chứa PII hoặc exception messages trong metrics labels.
10. Đặc biệt với `POST`, `PUT`, `PATCH`, `DELETE`, kiểm tra **CSRF** nếu ứng dụng sử dụng cookie-authenticated browser sessions; không tắt CSRF bừa bãi.
11. Nếu hỗ trợ CORS, chỉ cho origins/headers/methods đã duyệt; OPTIONS preflight không phải là một lời gọi nghiệp vụ cần forward tùy tiện.
12. Bảo đảm backend vẫn kiểm tra authorization của tài nguyên; BFF không thay thế toàn bộ bảo vệ downstream.

**ProxyExchange.header(...) không phải authentication.** Thêm header do BFF tạo chỉ có ý nghĩa tin cậy khi backend đã xác thực đúng caller/service identity.

## 18. Lab: tạo backend echo để nhìn method, path, body và headers

Để kiểm chứng từng HTTP method, một backend lab tại `http://localhost:9091` có thể trả response mang method, path và một số metadata **không nhạy cảm**.

Ví dụ một controller Spring MVC dành riêng cho **backend thử nghiệm**, không phải ProxyExchange:

~~~java
package example.backend.lab;

import java.util.Map;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestMethod;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MethodEchoController {

    @RequestMapping(
        path = "/lab/echo",
        method = {
            RequestMethod.GET,
            RequestMethod.POST,
            RequestMethod.PUT,
            RequestMethod.PATCH,
            RequestMethod.DELETE
        })
    public ResponseEntity<Map<String, Object>> echo(
            jakarta.servlet.http.HttpServletRequest request,
            @RequestBody(required = false) byte[] body) {

        return ResponseEntity.ok(Map.of(
            "method", request.getMethod(),
            "path", request.getRequestURI(),
            "bytes", body == null ? 0 : body.length
        ));
    }
}
~~~

Backend không echo token/cookie/user data. Với `HEAD`/`OPTIONS`, nên bổ sung endpoint riêng hoặc dùng mock HTTP server hỗ trợ chính xác semantics; controller echo ở trên cố ý chỉ cho năm methods thường gặp.

### Route ProxyExchange tương ứng trong BFF

Với backend `/lab/echo`, tạo controller riêng theo một bộ quy tắc cho từng method, hoặc minh họa bằng handler cho POST:

~~~java
@PostMapping("/bff/lab/echo")
public ResponseEntity<?> proxyLabPost(
        @RequestBody byte[] body,
        ProxyExchange<byte[]> proxy) throws Exception {

    return proxy
        .uri("http://localhost:9091/lab/echo")
        .body(body)
        .post();
}
~~~

Các handler method GET/PUT/PATCH/DELETE tương tự như phần 4–7, chỉ thay URI target bằng `http://localhost:9091/lab/echo`.

### Bước 1 — GET

~~~bash
curl -i "http://localhost:8080/bff/lab/echo"
~~~

Kỳ vọng backend ghi nhận `method=GET`, `path=/lab/echo` nếu BFF có handler GET tương ứng.

### Bước 2 — POST JSON nhỏ

~~~bash
curl -i -X POST \
  -H "Content-Type: application/json" \
  --data-binary '{"itemId":42,"qty":1}' \
  "http://localhost:8080/bff/lab/echo"
~~~

Backend phải thấy `method=POST` và `bytes` khớp raw payload đã nhận. Nếu bytes khác, kiểm tra body conversion, charset, Content-Encoding và serialization.

### Bước 3 — PUT

~~~bash
curl -i -X PUT \
  -H "Content-Type: application/json" \
  --data-binary '{"name":"new-title"}' \
  "http://localhost:8080/bff/lab/echo"
~~~

### Bước 4 — PATCH

~~~bash
curl -i -X PATCH \
  -H "Content-Type: application/merge-patch+json" \
  --data-binary '{"name":"updated"}' \
  "http://localhost:8080/bff/lab/echo"
~~~

### Bước 5 — DELETE

~~~bash
curl -i -X DELETE \
  "http://localhost:8080/bff/lab/echo"
~~~

Với DELETE, kỳ vọng không có body nếu không gửi. Không thử trên tài nguyên production thật; endpoint lab phải không thực hiện xóa dữ liệu nhạy cảm.

### Bước 6 — HEAD và OPTIONS

~~~bash
curl -I "http://localhost:8080/bff/items/42"

curl -i -X OPTIONS \
  "http://localhost:8080/bff/items/42"

# CORS preflight khác OPTIONS thông thường:
curl -i -X OPTIONS \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  "http://localhost:8080/bff/orders"
~~~

Đối chiếu body rỗng của HEAD, header `Allow` nếu có và CORS policy thực tế. HTTP status có thể do Spring Security/Servlet CORS xử lý trước controller; hãy ghi **thành phần nào trả response**, không kết luận mỗi OPTIONS đều được proxy.

### Bước 7 — Không cho raw target URL

~~~bash
# Chỉ thực hiện nếu BFF có endpoint lab nhận targetCode (không phải raw url).
curl -i "http://localhost:8080/bff/public-info?source=unknown"
~~~

Kỳ vọng code được reject; không đưa địa chỉ loopback/metadata thật vào một open-proxy endpoint để thử trên production.

## 19. Ma trận kiểm thử end-to-end

| Case | Kỳ vọng chính | Kiểm tra phụ |
|---|---|---|
| GET item tồn tại | Downstream GET, status/body đúng | Query, Content-Type, ETag |
| GET item không tồn tại | 404 theo contract | Không tự biến thành 200 |
| GET query lặp | Giữ semantics đã định | Không mất tham số/encode sai |
| POST JSON nhỏ | Downstream POST đúng bytes | Content-Type/length, authorization |
| POST malformed JSON | 400/422 theo policy | Không lộ stack trace |
| POST không idempotent bị timeout | Không retry mù quáng | Idempotency/deduplication |
| PUT replace resource | Downstream PUT | ETag/If-Match, concurrency |
| PATCH document | Downstream PATCH | Media type, partial update correctness |
| DELETE authorized | Downstream DELETE | 204 không body, audit |
| DELETE unauthenticated | 401/403 trước outbound | Backend không bị gọi |
| HEAD | Không response body | Headers/ETag đúng |
| OPTIONS preflight | CORS trả đúng policy | Không bypass security |
| 201 + Location | Không lộ internal hostname | Preserve/normalize Location theo contract |
| 429 + Retry-After | Không retry storm | Quota policy |
| Downstream 5xx | Error semantics đúng | Timeout/circuit breaker/fallback |
| Incoming Authorization/Cookie | Không vô tình forward | Sensitive header policy |
| Host/Content-Length | Framing đúng downstream | Không copy header sai |
| Large body/response | Giới hạn có hiệu lực | Memory, concurrency, timeout |
| URL tự nhập từ client | Không tạo open proxy | SSRF/egress controls |
| TLS certificate sai | Kết nối bị từ chối an toàn | Không bật trust-all |
| Nhiều BFF nodes | Behavior consistent | Metrics/traces/rollout |

**Không đo “proxy đúng” chỉ bằng HTTP 200.** Với method có side effects, phải kiểm tra **backend thực nhận method nào và side effect xảy ra đúng một lần**.

## 20. Troubleshooting những lỗi hay gặp

| Triệu chứng | Nguyên nhân đáng kiểm tra | Hướng xử lý |
|---|---|---|
| Không inject được `ProxyExchange` | Sai module MVC/WebFlux hoặc auto-configuration | Đối chiếu artifact/stack và argument resolver |
| Compile không tìm thấy package | Import lớp khác phiên bản | Dùng package đúng module: `gateway.mvc` hoặc `gateway.webflux` |
| GET 404 trước khi đến backend | `@GetMapping` không match | Kiểm tra URL, context path, security |
| Backend trả 404 dù controller match | URI/path downstream sai | Kiểm tra `uri(...)`, path variables, query |
| POST backend nhận body rỗng | Không gọi `body(...)` hoặc body resolver đã consume/transform | Test byte count, media type, handler signatures |
| POST có body nhưng Content-Length sai | Đã đổi bytes nhưng cố forward header cũ | Không copy hop-specific framing |
| PUT/PATCH báo 405 | Backend không support method; mapping proxy hoặc HTTP client sai | Kiểm tra cả hai hops |
| DELETE trả 200 thay 204 | Controller/serializer sửa response | Bảo toàn status/body contract |
| HEAD có body | Handler/proxy response mapping không đúng HEAD semantics | Dùng `head()` nếu được hỗ trợ và test |
| OPTIONS bị 401/403 | CORS/Security chặn preflight | Thiết kế CORS policy đúng trước controller |
| User login thành công nhưng backend 401 | Sensitive Authorization không tự forward | Dùng service identity/token exchange, không nới toàn cục |
| Cookie không tới backend | Sensitive header policy | Đánh giá trust boundary; không giả định đây là lỗi |
| Backend thấy Host của BFF sai | Tự copy Host hoặc proxy routing sai | Để HTTP client tạo Host phù hợp target |
| Query/encoding bị sai | Nối raw URI, double encoding, repeated param lost | Dùng UriComponentsBuilder và contract tests |
| Dùng `lb://` không hoạt động | Nhầm Gateway Server LB filter với ProxyExchange client | Dùng resolver/client được hỗ trợ |
| Open proxy bị phát hiện | Controller nhận raw `url`/`host` | Chuyển sang server-side allowlist + egress ACL |
| 503 tăng sau khi thêm retry | Retry storm, deadline thiếu | Giảm attempts, backoff và circuit breaker |
| Multipart/streaming tốn memory | `byte[]` body + response aggregation | Chọn streaming architecture |
| Trace không liên kết downstream | Chưa tích hợp tracing vào HTTP client | Kiểm tra instrumentation và propagation |
| Chỉ node này lỗi | Khác BOM/version/config/target trust | So sánh deployment và source of config |

### Quy trình kiểm tra theo 6 lớp

1. **Controller mapping:** request có đến đúng `@GetMapping`/`@PostMapping` không?
2. **ProxyExchange injection:** đúng MVC/WebFlux module và argument resolver chưa?
3. **Target URI:** `proxy.uri(...)` có phải đích được duyệt, path/query/encoding đúng không?
4. **Request forwarding:** HTTP method, body bytes và headers đến backend có đúng contract không?
5. **Downstream response:** status, body, headers, exception/timeout mapping có bị sửa không?
6. **Cross-cutting policies:** authentication, rate limit, retry, circuit breaker, TLS và observability có được tích hợp riêng, đo được không?

Đừng “sửa nhanh” bằng cách cho mọi handler nhận `RequestMethod.values()`, chấp nhận raw URL hay forward tất cả Authorization/Cookie; các cách đó có thể tạo bypass bảo mật.

## 21. Checklist trước khi đưa vào production

- [ ] Tôi phân biệt **Proxy Exchange** với **Gateway Server WebFlux/Server MVC**.
- [ ] Tôi chọn đúng artifact `proxyexchange-webmvc` hoặc `proxyexchange-webflux` theo web stack.
- [ ] Tôi hiểu `ProxyExchange<byte[]>` là tham số controller, không phải một route predicate.
- [ ] Tôi dùng `get()` cho GET và giữ query/path semantics.
- [ ] Tôi dùng `body(body).post()` cho POST khi có payload và giới hạn body từ trước.
- [ ] Tôi phân biệt PUT replace và PATCH partial update; test Content-Type/ETag/concurrency.
- [ ] Tôi giữ DELETE đúng quyền tài nguyên và status 204/404 theo contract.
- [ ] Tôi biết HEAD phải không có response body và OPTIONS/CORS preflight có trách nhiệm khác nhau.
- [ ] Tôi không giả định TRACE/CONNECT/WebSocket có ProxyExchange helper tương đương.
- [ ] Tôi không nhầm MVC `ResponseEntity` với WebFlux `Mono<ResponseEntity>` hoặc dùng `block()` trong event-loop.
- [ ] Tôi không cho client tự chọn target URL; mọi URI đến từ allowlist/mapping server-side.
- [ ] Tôi validate/encode path segments, query values, repeated parameters và host trust.
- [ ] Tôi biết default sensitive headers gồm Cookie và Authorization ở những bản được tài liệu hóa.
- [ ] Tôi hiểu skipped headers như Host/Content-Length có thể không được forward vì framing thay đổi.
- [ ] Tôi xử lý hop-by-hop headers và không copy mù quáng mọi HTTP header.
- [ ] Tôi kiểm tra `201 Location`, `204`, `304`, `429 Retry-After` và 4xx/5xx downstream.
- [ ] Tôi không dùng response mapper để vô tình lộ backend headers hoặc làm sai Content-Length/ETag.
- [ ] Tôi không coi `proxy.forward()` MVC là remote HTTP proxy hoặc cho caller forward vào admin handler.
- [ ] Tôi không dùng `byte[]` để proxy file lớn/SSE/unbounded streams nếu chưa chứng minh memory bounded.
- [ ] Tôi áp Spring Security, authorization theo tài nguyên, CSRF/CORS theo loại client.
- [ ] Tôi thiết kế rate limit, circuit breaker, retry và service discovery **riêng cho Proxy Exchange**, không chờ Gateway Server factories tự chạy.
- [ ] Tôi có timeout per-attempt/overall deadline, idempotency cho POST/PATCH và điều kiện retry chặt.
- [ ] Tôi bảo vệ TLS, DNS/egress, không tắt certificate validation.
- [ ] Tôi theo dõi incoming requests, outbound attempts, backend latency/status, P95/P99 và correlation IDs.
- [ ] Tôi đã chạy test GET/POST/PUT/PATCH/DELETE/HEAD/OPTIONS qua BFF và backend echo.
- [ ] Tôi đã thử negative tests: unauthorized, missing target, malformed body, partial download, open proxy, retry storm.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway — Proxy Exchange Gateway with Spring Web MVC or WebFlux](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-proxy-exchange.html) — artifact, cách inject `ProxyExchange`, ví dụ MVC/WebFlux, path, headers, response mapper.
- [Spring Cloud Gateway 4.3 — Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-proxy-exchange.html) — đối chiếu hành vi của một release train cụ thể.
- [Spring Cloud Gateway 5.0 — Proxy Exchange](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-proxy-exchange.html) — so sánh nâng cấp phiên bản.
- [Spring Cloud Gateway — Project](https://spring.io/projects/spring-cloud-gateway) — cách chọn release train/BOM phù hợp.
- [Spring Framework — Spring MVC Controller Methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html) — `@RequestMapping`, `@RequestBody`, `ResponseEntity`.
- [Spring Framework — WebFlux Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html) — `Mono<ResponseEntity<?>>` và reactive handlers.
- [Spring Security — Servlet](https://docs.spring.io/spring-security/reference/servlet/index.html) — xác thực và phân quyền MVC.
- [Spring Security — Reactive](https://docs.spring.io/spring-security/reference/reactive/index.html) — xác thực và phân quyền WebFlux.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS, status codes, representation và hop-specific fields.
- [OWASP — SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) — URI allowlist, DNS, egress và ranh giới tin cậy.

**Ghi nhớ:** **ProxyExchange** giúp một controller **Spring MVC hoặc WebFlux** chủ động gọi downstream qua `get()`, `body(...).post()`, `put()`, `patch()`, `delete()` và các HTTP methods được hỗ trợ khác. Muốn chuyển tiếp đúng, phải **giữ method, path/query, payload, response status/headers theo hợp đồng**; đồng thời xác thực quyền caller, chặn arbitrary target URI/SSRF, kiểm soát sensitive/hop-by-hop headers, giới hạn bộ nhớ và retry. **Proxy Exchange là công cụ controller-style proxy, không phải đường tắt để có toàn bộ route/filter policies của Gateway Server.**
