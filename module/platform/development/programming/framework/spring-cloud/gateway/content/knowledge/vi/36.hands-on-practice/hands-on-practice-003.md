# Chuẩn hóa đường dẫn, header và mã lỗi cho API phía sau

## 1. Mục tiêu bài thực hành

Một API Gateway thường nhận URL và headers theo hợp đồng public, trong khi các microservices phía sau có thể dùng path, header nội bộ và cách biểu diễn lỗi khác nhau. Nếu không có quy ước chung, client phải biết từng service dùng URL nào, header nào đáng tin và phải đọc error body ra sao. Điều đó làm API khó thay đổi và dễ phát sinh lỗi bảo mật.

Trong bài thực hành này, ta xây dựng một Gateway đứng trước Catalog service. Gateway chuẩn hóa:

1. **Đường dẫn:** client gọi `/api/catalog/v1/items/42`; Catalog service nhận `/v1/items/42`.
2. **Request headers:** loại bỏ identity headers do client tự khai báo, chuyển tiếp correlation ID đã kiểm tra và thêm metadata nội bộ do Gateway kiểm soát.
3. **Response headers:** áp dụng chính sách response nhất quán, tránh header trùng và giảm rò rỉ thông tin server.
4. **Mã lỗi:** downstream trả một error contract ổn định dựa trên RFC 9457 Problem Details; Gateway fallback cũng trả cùng cấu trúc khi upstream không khả dụng.
5. **Kiểm chứng:** dùng curl để xác nhận path, headers, status code, body và hành vi khi backend lỗi.

### Kết quả mong đợi

Client chỉ cần biết public contract:

```http
GET /api/catalog/v1/items/42?lang=vi
X-Correlation-Id: lab-request-42
```

Gateway chuyển request tới backend:

```http
GET /v1/items/42?lang=vi
X-Correlation-Id: lab-request-42
X-API-Contract: catalog-v1
```

Client không thể giả mạo identity qua `X-User-Id` hoặc `X-User-Role`; Gateway xóa các headers đó trước khi chuyển tiếp. Nếu sản phẩm không tồn tại, client nhận HTTP 404 và một mã máy đọc được như `PRODUCT_NOT_FOUND`. Nếu Catalog service không khả dụng, Gateway fallback trả HTTP 503 với `CATALOG_UNAVAILABLE`.

### Phạm vi kỹ thuật

- Spring Cloud Gateway Server WebFlux 5.0.x.
- Spring Boot 4.x và Spring Framework WebFlux.
- Java 17+ (hoặc phiên bản Java mà BOM Spring Boot của project yêu cầu).
- Một Catalog service HTTP chạy ở cổng local 8081.
- Gateway chạy ở cổng local 8080.

Tên service, host và dữ liệu trong lab là ví dụ. Nếu ứng dụng dùng Spring Cloud Gateway Server Web MVC, các filter/security APIs khác với WebFlux; không copy các lớp `GlobalFilter` và `ServerWebExchange` sang MVC.

## 2. Phác thảo hợp đồng public và internal

### 2.1. Mapping đường dẫn

| Public API | Internal API | Ý nghĩa |
|---|---|---|
| `GET /api/catalog/v1/items/{id}` | `GET /v1/items/{id}` | Đọc một sản phẩm |
| `GET /api/catalog/v1/items/{id}?lang=vi` | `GET /v1/items/{id}?lang=vi` | Query string được giữ nguyên |
| `GET /api/catalog/v1/items/999` | `GET /v1/items/999` | Backend trả Problem Details 404 |

Client không cần biết Catalog service có context path `/v1` hay đổi hostname. Gateway sở hữu public prefix `/api/catalog`; backend sở hữu path nội bộ của nó.

Một nguyên tắc quan trọng: **chỉ rewrite một lần tại ranh giới Gateway**. Không để Gateway strip prefix, BFF lại strip lần nữa và backend tự đoán path. Ghi rõ input path và output path trong route contract.

### 2.2. Header contract

| Header | Ai tạo/được tin? | Chính sách trong bài |
|---|---|---|
| `X-Correlation-Id` | Client có thể gửi; Gateway kiểm tra định dạng | Giữ nếu hợp lệ, nếu không tạo UUID mới; gửi tới backend và trả về response |
| `X-User-Id` | Không tin giá trị do public client tự gửi | Xóa trước khi proxy; identity phải lấy từ JWT/principal đã xác thực |
| `X-User-Role` | Không tin giá trị do public client tự gửi | Xóa trước khi proxy; downstream tự xác minh quyền |
| `Authorization` | Credential theo security contract | Chuyển tiếp/relay chỉ khi policy yêu cầu; không log hoặc sửa tùy tiện |
| `X-API-Contract` | Gateway tạo | Đặt thành `catalog-v1` để backend biết contract/hop public đã chọn |
| `Forwarded`, `X-Forwarded-*` | Chỉ tin từ proxy/ingress được cấu hình | Không tin header do Internet client tự gửi; giới hạn trusted proxies ở hạ tầng |
| `Cache-Control` | Gateway hoặc backend theo response policy | API cá nhân hóa trong lab được đặt `no-store` |

Header là metadata, không phải cơ chế xác thực. Xóa `X-User-Id` không thay việc kiểm tra JWT; thêm `X-API-Contract` cũng không chứng minh caller được quyền truy cập dữ liệu.

### 2.3. Error contract

Các API phía sau dùng cùng cấu trúc Problem Details:

```json
{
  "type": "https://api.example.test/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "The requested product does not exist.",
  "code": "PRODUCT_NOT_FOUND",
  "correlationId": "lab-request-42"
}
```

Problem Details có các member chuẩn như `type`, `title`, `status`, `detail` và `instance` (tùy chọn theo response); các field mở rộng như `code` và `correlationId` được bổ sung theo hợp đồng API. Response dùng media type `application/problem+json`.

HTTP status và error code giải quyết hai việc khác nhau:

- HTTP status giúp client, proxy và cache hiểu loại kết quả.
- `code` giúp client xử lý nghiệp vụ ổn định mà không phải phân tích câu `detail`.

Không dùng exception class name, hostname nội bộ, stack trace hoặc message database làm mã lỗi public.

## 3. Chuẩn hóa path bằng RewritePath

### 3.1. Tạo route Catalog

Trong Gateway Server WebFlux 5.0, route properties nằm dưới namespace `spring.cloud.gateway.server.webflux`. Cấu hình local:

```yaml
server:
  port: 8080

spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/v1/items/**
                - Method=GET
              filters:
                - RewritePath=/api/catalog/(?<remaining>.*), /$\{remaining}
```

Với request `/api/catalog/v1/items/42?lang=vi`, regex của `RewritePath` bắt phần còn lại là `v1/items/42`, rồi đổi path thành `/v1/items/42`. Query string `?lang=vi` vẫn được giữ. Backend ở `localhost:8081` nhận request.

### 3.2. Vì sao cần escape replacement trong YAML?

Gateway dùng biểu thức thay thế regex. Trong cấu hình YAML, dạng `/$\{remaining}` được dùng để tránh Spring property placeholder xử lý nhầm chuỗi property placeholder dạng dollar-brace trước khi filter nhận regex replacement. Khi viết Java DSL, cú pháp replacement có thể khác cách escape trong YAML.

### 3.3. Khi nào dùng StripPrefix, khi nào dùng RewritePath?

| Filter | Khi phù hợp | Ví dụ |
|---|---|---|
| `StripPrefix=2` | Chỉ cần bỏ N path segments đầu | `/api/catalog/v1/items/42` → `/v1/items/42` |
| `PrefixPath=/internal` | Backend cần thêm một prefix cố định | `/items/42` → `/internal/items/42` |
| `SetPath=/v1/items/{id}` | Path đích có cấu trúc đơn giản và tham số đã capture | Đổi path theo template |
| `RewritePath` | Cần regex, đổi prefix hoặc giữ phần path còn lại | `/api/catalog/**` → `/**` |

Chọn filter dễ đọc nhất cho quy tắc đang có. Không chồng nhiều rewrite filters nếu một filter đã diễn tả được mapping.

### 3.4. Các tình huống path cần kiểm thử

- Có slash cuối: `/api/catalog/v1/items/42/`.
- Có query string: `/api/catalog/v1/items/42?lang=vi&page=2`.
- Thiếu phần path sau prefix: `/api/catalog/`.
- Prefix gần giống nhưng không hợp lệ: `/api/catalogue/v1/items/42`.
- Path chứa percent-encoded segment hoặc encoded slash.
- Path có dấu chấm/segment bất thường hoặc nhiều slash liên tiếp.

Không tự decode `%2F`, chuẩn hóa dấu slash hoặc xóa `..` bằng chuỗi thay thế tùy tiện. Path normalization phải thống nhất giữa ingress, Gateway và backend để tránh path traversal, route bypass hoặc hai tầng hiểu cùng một URL theo cách khác nhau. Với encoded slash/ambiguous paths, chọn chính sách reject rõ ràng và kiểm thử trên đúng HTTP server/proxy stack.

## 4. Chuẩn hóa request headers

### 4.1. Xóa identity headers không đáng tin

Public client có thể gửi bất kỳ header tùy chỉnh nào:

```http
GET /api/catalog/v1/items/42 HTTP/1.1
Host: api.example.test
X-User-Id: administrator
X-User-Role: SUPER_ADMIN
```

Nếu backend tin trực tiếp hai header này, client có thể tự nhận quyền của người khác. Route phải xóa chúng:

```yaml
filters:
  - RemoveRequestHeader=X-User-Id
  - RemoveRequestHeader=X-User-Role
```

Nếu hệ thống cần user context, xác thực JWT/OAuth2 ở Gateway và dùng principal/token relay hoặc token exchange theo security contract. Downstream vẫn phải xác minh chữ ký, issuer, audience, scope và quyền theo resource/tenant. Không thay xác thực bằng một header do Gateway tự thêm nhưng không có integrity protection.

### 4.2. Đặt metadata nội bộ do Gateway sở hữu

Ví dụ:

```yaml
filters:
  - SetRequestHeader=X-API-Contract, catalog-v1
```

`SetRequestHeader` ghi đè giá trị client gửi (nếu có), trong khi `AddRequestHeader` có thể tạo thêm một giá trị. Với header cần đúng một giá trị chuẩn, ưu tiên `SetRequestHeader`.

Không dùng header metadata này làm bí mật hoặc quyền truy cập. Nếu downstream cần xác minh request đến từ Gateway, hãy dùng mTLS, workload identity hoặc token có audience phù hợp.

### 4.3. Không tùy tiện sửa Authorization và forwarded headers

- Không xóa `Authorization` nếu downstream cần tự xác thực bearer token và chưa có cơ chế thay thế.
- Không log token, cookie hoặc API key.
- Không tin `X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto` từ client Internet.
- Chỉ nhận forwarded metadata từ ingress/proxy nằm trong trust boundary và cấu hình trusted proxy ở tầng phù hợp.
- Không tự chuyển tiếp các hop-by-hop headers như `Connection`, `Keep-Alive`, `Transfer-Encoding` hoặc `Upgrade` bằng filter header thông thường; proxy HTTP xử lý chúng theo semantics của transport.

Nếu ingress và Gateway cùng thêm `X-Forwarded-*`, kiểm tra chuỗi proxy và thứ tự tin cậy. Một địa chỉ client sai có thể làm sai IP-based rate limiting, audit và access control.

### 4.4. Correlation ID: kiểm tra, tạo và trả lại

Gateway nên có một ID để nối access logs, backend logs và trace. Dùng một `GlobalFilter` cho các request đã match route:

```java
package com.example.gateway.filter;

import java.util.UUID;
import java.util.regex.Pattern;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@Component
public class CorrelationIdGlobalFilter implements GlobalFilter, Ordered {

    public static final String HEADER = "X-Correlation-Id";
    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9._-]{1,64}");

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            GatewayFilterChain chain) {

        String supplied = exchange.getRequest()
            .getHeaders().getFirst(HEADER);

        String correlationId =
            supplied != null && SAFE_ID.matcher(supplied).matches()
                ? supplied
                : UUID.randomUUID().toString();

        ServerHttpRequest request = exchange.getRequest().mutate()
            .headers(headers -> headers.set(HEADER, correlationId))
            .build();

        ServerWebExchange mutated = exchange.mutate()
            .request(request)
            .build();

        mutated.getResponse().beforeCommit(() -> {
            mutated.getResponse().getHeaders()
                .set(HEADER, correlationId);
            return Mono.empty();
        });

        return chain.filter(mutated);
    }
}
```

**Giải thích:**

1. Chỉ giữ correlation ID có 1–64 ký tự trong allowlist ASCII; giá trị khác được thay bằng UUID.
2. `headers.set(...)` bảo đảm downstream nhận đúng một giá trị, kể cả client gửi header lặp.
3. `beforeCommit` thêm cùng ID vào response trước khi headers được gửi.
4. ID chỉ phục vụ correlation; không dùng làm authentication, authorization hoặc tenant identity.
5. `GlobalFilter` chỉ chạy sau khi Gateway đã chọn route. Request không match route có thể không đi qua filter này; nếu cần correlation ID cho mọi request, kể cả 404 trước routing, hãy đặt logic ở WebFlux `WebFilter` hoặc ingress layer.

Nếu Micrometer Tracing đã tạo trace/span IDs, tiếp tục dùng W3C Trace Context cho distributed tracing. `X-Correlation-Id` là ID nghiệp vụ/điều tra bổ sung, không thay `traceparent`.

## 5. Chuẩn hóa response headers

### 5.1. Đặt header theo API policy

Với API chứa dữ liệu theo user/tenant, lab đặt:

```yaml
filters:
  - SetResponseHeader=Cache-Control, no-store
  - SetResponseHeader=X-Content-Type-Options, nosniff
  - RemoveResponseHeader=Server
  - RemoveResponseHeader=X-Powered-By
```

- `Cache-Control: no-store` ngăn cache lưu response cá nhân hóa theo policy của bài. Public catalog data có thể có cache policy khác; không áp dụng `no-store` cho mọi route nếu làm giảm hiệu năng không cần thiết.
- `X-Content-Type-Options: nosniff` giúp browser không tự đoán MIME type.
- `Server` và `X-Powered-By` được bỏ để giảm thông tin stack trong response; đây chỉ là vệ sinh metadata, không thay hardening.

`SetResponseHeader` đặt giá trị chuẩn, còn `AddResponseHeader` có thể thêm một giá trị nữa. Với header đơn trị như `Cache-Control` trong policy này, tránh add nhiều bản.

### 5.2. CORS chỉ có một nơi sở hữu

Nếu Gateway và Catalog cùng cấu hình CORS, response có thể chứa hai `Access-Control-Allow-Origin` hoặc hai `Access-Control-Allow-Credentials`. Chọn một tầng làm owner của CORS. Nếu bắt buộc phải deduplicate header do legacy backend:

```yaml
filters:
  - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin RETAIN_FIRST
```

Chính sách `RETAIN_FIRST` chỉ là cách xử lý header trùng; nó không sửa một allow-origin sai hoặc hợp thức hóa wildcard với credentials. Cấu hình origin allowlist, credentials và preflight phải được kiểm tra riêng.

### 5.3. Không ghi đè header bảo mật của backend một cách mù quáng

Trước khi `SetResponseHeader`, xác định header thuộc trách nhiệm của Gateway hay service:

- Gateway có thể sở hữu `Cache-Control` ở public API boundary.
- Service sở hữu `ETag`, `Last-Modified` và semantics cache theo resource nếu Gateway không thay đổi representation.
- CORS cần một owner duy nhất.
- `Content-Type`, `Content-Length`, `Content-Encoding` và headers liên quan body không nên bị sửa bằng một filter tổng quát nếu body không được biến đổi tương ứng.
- Không xóa `WWW-Authenticate` nếu client cần challenge để xác thực.

Khi thay đổi body response, phải xem xét content length, encoding, streaming, range headers và signature; bài thực hành này không biến đổi response body của API thành công.

## 6. Chuẩn hóa mã lỗi bằng Problem Details

### 6.1. Vì sao cần error code ổn định?

Giả sử Catalog trả:

```json
{"error":"item missing","message":"No row for id 999"}
```

Pricing trả:

```json
{"status":"NOT_FOUND","description":"offer absent"}
```

Inventory trả:

```json
{"errorCode":"404-INV","detail":"No inventory record"}
```

Client phải hiểu ba schema khác nhau và có thể bị phụ thuộc vào câu chữ. Thay vào đó, mỗi service nên ánh xạ lỗi domain sang một contract chung, ví dụ:

```json
{
  "type": "https://api.example.test/problems/product-not-found",
  "title": "Product not found",
  "status": 404,
  "detail": "The requested product does not exist.",
  "code": "PRODUCT_NOT_FOUND",
  "correlationId": "lab-request-42"
}
```

### 6.2. Bảng mã lỗi mẫu

| HTTP | Error code | Ý nghĩa | Client nên làm gì |
|---:|---|---|---|
| 400 | `INVALID_REQUEST` | Query/body/path không hợp lệ | Sửa input |
| 401 | `AUTHENTICATION_REQUIRED` | Chưa xác thực hoặc token không hợp lệ | Đăng nhập/làm mới token theo flow |
| 403 | `ACCESS_DENIED` | Đã xác thực nhưng không có quyền | Không retry; kiểm tra quyền |
| 404 | `PRODUCT_NOT_FOUND` | Resource không tồn tại | Hiển thị not found |
| 409 | `RESOURCE_CONFLICT` | Xung đột trạng thái nghiệp vụ | Làm mới trạng thái hoặc xử lý conflict |
| 422 | `VALIDATION_FAILED` | Dữ liệu hợp lệ về cú pháp nhưng vi phạm rule | Sửa dữ liệu theo field errors |
| 429 | `RATE_LIMITED` | Vượt quota | Tôn trọng `Retry-After` nếu có |
| 502 | `UPSTREAM_BAD_RESPONSE` | Gateway nhận response không hợp lệ từ upstream | Retry có giới hạn nếu request idempotent |
| 503 | `UPSTREAM_UNAVAILABLE` | Dependency không phục vụ | Backoff; kiểm tra status |
| 504 | `UPSTREAM_TIMEOUT` | Quá deadline | Retry có giới hạn nếu an toàn |
| 500 | `INTERNAL_ERROR` | Lỗi không dự kiến | Gửi correlation ID cho support |

Mã lỗi là một phần của API contract; giữ ổn định qua các bản release. Không dùng `detail` làm khóa logic vì câu chữ có thể được chỉnh sửa hoặc dịch.

### 6.3. Domain exception ở Catalog service

Định nghĩa exception nghiệp vụ:

```java
package com.example.catalog.error;

public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(long productId) {
        super("Product " + productId + " does not exist");
    }
}
```

Controller minh họa:

```java
package com.example.catalog.api;

import com.example.catalog.error.ProductNotFoundException;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CatalogController {

    @GetMapping("/v1/items/{id}")
    public Item getItem(@PathVariable("id") long id) {
        if (id == 999) {
            throw new ProductNotFoundException(id);
        }
        return new Item(id, "Wireless Headphones");
    }

    public record Item(long id, String name) {}
}
```

Điều kiện `id == 999` chỉ tạo một case deterministic cho lab. Trong ứng dụng thật, repository/service layer sẽ ném exception khi không tìm thấy resource.

### 6.4. Ánh xạ exception sang ProblemDetail

Trong Catalog WebFlux service:

```java
package com.example.catalog.error;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ServerWebExchange;

@RestControllerAdvice
public class CatalogProblemHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> productNotFound(
            ProductNotFoundException exception,
            ServerWebExchange exchange) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "The requested product does not exist.");

        problem.setType(URI.create(
            "https://api.example.test/problems/product-not-found"));
        problem.setTitle("Product not found");
        problem.setProperty("code", "PRODUCT_NOT_FOUND");

        String correlationId = exchange.getRequest()
            .getHeaders().getFirst("X-Correlation-Id");
        if (correlationId != null) {
            problem.setProperty("correlationId", correlationId);
        }

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
```

**Lưu ý:** đây là handler cho một domain exception cụ thể. Các lỗi validation, authentication và lỗi hệ thống cần handler/mapping tương ứng. Không tạo một `@ExceptionHandler(Exception.class)` trả toàn bộ exception message ra client; nếu cần catch-all, log exception nội bộ có kiểm soát và trả `INTERNAL_ERROR` generic.

### 6.5. Gateway không nên tự viết lại mọi upstream error body

Gateway proxy thông thường giữ status và body của upstream. Đây là behavior có lợi khi backend đã tuân thủ Problem Details. Không nên viết một global body rewrite để biến mọi 4xx/5xx thành một schema mới vì:

- Có thể làm mất error code domain mà client cần.
- Có thể làm sai `Content-Length`, `Content-Encoding`, `Content-Type`.
- Body streaming hoặc response lớn có thể bị buffer ngoài dự kiến.
- Các lỗi 404 nghiệp vụ không giống lỗi 404 do route không match.

Chuẩn hóa error contract tại từng service hoặc một BFF/adapter sở hữu contract public. Gateway chỉ tạo fallback có mã lỗi rõ ràng cho lỗi hạ tầng mà nó trực tiếp xử lý.
## 7. Fallback có cấu trúc khi upstream không khả dụng

### 7.1. Thêm CircuitBreaker cho route

Để Gateway trả lỗi ổn định khi Catalog timeout/không kết nối được, thêm Spring Cloud CircuitBreaker Reactor Resilience4j dependency. Ví dụ route:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/v1/items/**
                - Method=GET
              filters:
                - RewritePath=/api/catalog/(?<remaining>.*), /$\{remaining}
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-User-Role
                - SetRequestHeader=X-API-Contract, catalog-v1
                - name: CircuitBreaker
                  args:
                    name: catalogCircuit
                    fallbackUri: forward:/_internal/fallback/catalog
                    statusCodes:
                      - "500"
                      - "502"
                      - "503"
                      - "504"
```

`statusCodes` cho biết những HTTP status từ upstream được tính là failure của circuit breaker. Timeout/connection errors cũng có thể đi vào fallback. Tuning sliding window, minimum calls, wait duration và permitted calls in half-open state phải dựa trên traffic/latency thực; không copy một threshold mặc định cho mọi service.

### 7.2. Handler fallback trả ProblemDetail

Trong Gateway app:

```java
package com.example.gateway.fallback;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

@RestController
public class GatewayFallbackController {

    @RequestMapping("/_internal/fallback/catalog")
    public ResponseEntity<ProblemDetail> catalogUnavailable(
            ServerWebExchange exchange) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.SERVICE_UNAVAILABLE,
            "Catalog service is temporarily unavailable.");
        problem.setType(URI.create(
            "https://api.example.test/problems/upstream-unavailable"));
        problem.setTitle("Upstream service unavailable");
        problem.setProperty("code", "CATALOG_UNAVAILABLE");

        String correlationId = exchange.getRequest()
            .getHeaders().getFirst("X-Correlation-Id");
        if (correlationId != null) {
            problem.setProperty("correlationId", correlationId);
        }

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
            .contentType(MediaType.APPLICATION_PROBLEM_JSON)
            .body(problem);
    }
}
```

Đường dẫn `/_internal/fallback/catalog` là handler nội bộ được gọi bằng `forward:`. Trong production, cấu hình Spring Security để client không gọi trực tiếp path này (deny direct requests), đồng thời test rằng internal forward vẫn hoạt động. Không coi một URL khó đoán là biện pháp bảo mật.

Fallback này đại diện cho **toàn upstream Catalog không khả dụng**, nên trả 503. Nó không phải fallback cho sản phẩm không tồn tại; 404 `PRODUCT_NOT_FOUND` vẫn do Catalog service trả về và Gateway proxy nguyên response.

### 7.3. Phân biệt ba nguồn tạo lỗi

| Nguồn | Ví dụ | Error contract |
|---|---|---|
| Domain service | Catalog không tìm thấy item | 404 `PRODUCT_NOT_FOUND` |
| Gateway resilience | Catalog không kết nối/timeout hoặc trả 5xx bị breaker bắt | 503 `CATALOG_UNAVAILABLE` |
| Gateway routing | Không có route nào match URL | Gateway 404 mặc định hoặc custom error handler riêng |

Không gộp lỗi route không tồn tại thành `PRODUCT_NOT_FOUND`; một lỗi là public URL không được cấu hình, lỗi kia là resource domain không tồn tại. Nếu cần mọi lỗi do Gateway tự sinh (404 no route, 429 limiter, 401/403 security) đều theo Problem Details, phải chuẩn hóa ở đúng error boundary tương ứng; fallback của một route không bắt được mọi lỗi trước khi route được chọn.

## 8. Cấu hình hoàn chỉnh cho Gateway lab

Ghép route, request/response headers và fallback:

```yaml
server:
  port: 8080

spring:
  application:
    name: edge-gateway
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-api
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/v1/items/**
                - Method=GET
              filters:
                - RewritePath=/api/catalog/(?<remaining>.*), /$\{remaining}
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-User-Role
                - SetRequestHeader=X-API-Contract, catalog-v1
                - SetResponseHeader=Cache-Control, no-store
                - SetResponseHeader=X-Content-Type-Options, nosniff
                - RemoveResponseHeader=Server
                - RemoveResponseHeader=X-Powered-By
                - name: CircuitBreaker
                  args:
                    name: catalogCircuit
                    fallbackUri: forward:/_internal/fallback/catalog
                    statusCodes:
                      - "500"
                      - "502"
                      - "503"
                      - "504"
```

Với service discovery, thay `uri: http://localhost:8081` bằng `uri: lb://catalog-service` và thêm Spring Cloud LoadBalancer cùng discovery client tương ứng. Không dùng `lb://` nếu chưa cấu hình cơ chế tìm instance.

Trong project thật, giữ các filters ở một route contract được review; nếu nhiều route cần cùng chính sách, có thể chuyển phần chung thành `default-filters` hoặc custom filter. Không tạo `default-filters` áp dụng rộng nếu một số route có semantics cache/header khác.

## 9. Chạy lab và kiểm tra bằng curl

### 9.1. Khởi động hai ứng dụng

Chạy Catalog service ở cổng `8081`, Gateway ở cổng `8080`. Đảm bảo Gateway có:

- Spring Cloud Gateway Server WebFlux starter.
- Spring Cloud CircuitBreaker Reactor Resilience4j nếu dùng fallback.
- Các version được quản lý bởi Spring Boot/Spring Cloud BOM tương thích.

Ví dụ Maven dependencies cho Gateway (BOM quản lý version):

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

Catalog service lab chỉ cần `spring-boot-starter-webflux` cho controller reactive; thêm Spring Security nếu backend tự xác thực bearer token. Không pin version riêng lẻ khi project đã dùng Spring Boot/Spring Cloud BOM tương thích.

Hai security starters trong ví dụ Gateway phục vụ phần cấu hình OAuth2 ở mục 10. Nếu chỉ chạy lab local không có identity provider, có thể chưa thêm hai dependency này và chưa đăng ký `GatewaySecurityConfiguration`; bật chúng khi đã cấu hình issuer/JWK test.

Ví dụ `application.yml` của Catalog service:

```yaml
server:
  port: 8081
spring:
  application:
    name: catalog-service
```

Catalog service cần WebFlux starter và controller/exception handler ở mục 6. Trong môi trường lab, có thể bỏ authentication để tập trung kiểm tra rewrite/header/error contract; production cần cấu hình authentication và authorization thật.

### 9.2. Request thành công: kiểm tra path, query và headers

```bash
curl -i \
  -H "X-Correlation-Id: lab-request-42" \
  -H "X-User-Id: administrator" \
  -H "X-User-Role: SUPER_ADMIN" \
  "http://localhost:8080/api/catalog/v1/items/42?lang=vi"
```

Kết quả cần kiểm tra:

- Backend log path `/v1/items/42`, không phải `/api/catalog/v1/items/42`.
- Backend nhận query `lang=vi`.
- Backend nhận `X-Correlation-Id: lab-request-42`.
- Backend không nhận `X-User-Id` và `X-User-Role`.
- Backend nhận `X-API-Contract: catalog-v1`.
- Response có `X-Correlation-Id`, `Cache-Control: no-store` và `X-Content-Type-Options: nosniff`.

Nếu request path không rewrite, kiểm tra route predicate, regex capture group và escape replacement. Nếu backend nhận identity header giả, kiểm tra route có đúng `RemoveRequestHeader` và có route khác match trước không.

### 9.3. Correlation ID không hợp lệ

```bash
curl -i \
  -H "X-Correlation-Id: bad value with spaces" \
  "http://localhost:8080/api/catalog/v1/items/42"
```

Gateway phải tạo một UUID mới; response và backend log dùng cùng ID mới. Đừng assert một UUID cố định; chỉ kiểm tra header có mặt, đúng định dạng và khớp giữa log/request/response.

### 9.4. Domain error: sản phẩm không tồn tại

```bash
curl -i \
  -H "X-Correlation-Id: lab-not-found-999" \
  "http://localhost:8080/api/catalog/v1/items/999"
```

Kết quả mong đợi:

- HTTP 404.
- `Content-Type: application/problem+json`.
- Body có `type`, `title`, `status=404`, `code=PRODUCT_NOT_FOUND`.
- `correlationId` khớp `lab-not-found-999`.
- Gateway không đổi 404 thành 503.

### 9.5. Upstream unavailable: kiểm tra fallback

Trong môi trường local được phép, dừng Catalog service hoặc làm cho upstream connection thất bại rồi gửi:

```bash
curl -i \
  -H "X-Correlation-Id: lab-catalog-down" \
  "http://localhost:8080/api/catalog/v1/items/42"
```

Khi CircuitBreaker mở hoặc bắt được lỗi connection/timeout, response fallback mong đợi là HTTP 503, `Content-Type: application/problem+json`, `code=CATALOG_UNAVAILABLE` và cùng correlation ID. Việc breaker mở có thể cần đủ số calls/threshold theo cấu hình; không giả định một request lỗi duy nhất luôn mở circuit.

### 9.6. Public path không match

```bash
curl -i "http://localhost:8080/api/catalogue/v1/items/42"
```

Request này không match `/api/catalog/**`; Gateway có thể trả 404 mặc định. Đây là lỗi routing, không phải `PRODUCT_NOT_FOUND`. Nếu hệ thống muốn error body thống nhất cho no-route, triển khai một error boundary riêng và kiểm thử nó độc lập.

### 9.7. Gọi trực tiếp backend

```bash
curl -i \
  -H "X-Correlation-Id: direct-backend-test" \
  -H "X-User-Id: administrator" \
  "http://localhost:8081/v1/items/42"
```

Request trực tiếp này **bỏ qua Gateway**, vì vậy có thể không có các header đã chuẩn hóa. Trong production, backend cần network policy và service authentication để chỉ workload được phép gọi; không dựa vào việc client “được hướng dẫn” đi qua Gateway.

## 10. Bảo vệ fallback và xác minh security boundary

### 10.1. Chặn client gọi trực tiếp fallback handler

Fallback controller có URL nội bộ trên cùng HTTP listener. Nếu ứng dụng public không chặn path này, client có thể tự gọi endpoint fallback dù không có upstream failure. Đặt rule deny cho path nội bộ trước các rule rộng:

```java
package com.example.gateway.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class GatewaySecurityConfiguration {

    @Bean
    @Order(0)
    SecurityWebFilterChain gatewayApiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/_internal/fallback/**").denyAll()
                .pathMatchers("/api/catalog/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Issuer/JWK validation cần được cấu hình trong ứng dụng, ví dụ:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/platform
```

`identity.example.test` chỉ là hostname minh họa. Với production, dùng issuer thật, kiểm tra audience và mapping scopes/roles theo identity provider. Nếu Gateway đã có `SecurityWebFilterChain`, tích hợp rule deny vào chain hiện có thay vì tạo thêm chain chồng lấn không có matcher rõ ràng.

Request đi vào `/api/catalog/**` được xác thực trước; khi CircuitBreaker forward nội bộ tới fallback handler, cùng exchange được xử lý trong flow hiện tại. Hãy integration-test cả hai trường hợp: client gọi trực tiếp `/_internal/fallback/catalog` bị từ chối, còn request `/api/catalog/...` đi qua fallback trả 503 đúng contract.

### 10.2. Header identity không phải là principal

Trong lab, `X-User-Id` và `X-User-Role` bị xóa để chứng minh Gateway không tin headers public. Khi bật OAuth2:

- Gateway xác minh JWT theo issuer/JWK và các validation cần thiết.
- Route authorization quyết định caller có scope đọc Catalog hay không.
- Nếu downstream cần identity, dùng token relay/token exchange hoặc service identity có audience phù hợp.
- Downstream vẫn xác minh token và quyền resource/tenant.

Không thêm `SetRequestHeader=X-User-Role, ADMIN` để chuyển quyền cho backend. Một header do Gateway đặt không tự có chữ ký hay chứng minh user đã được cấp role.

### 10.3. Giới hạn phạm vi header spoofing

Không chỉ `X-User-Id` và `X-User-Role` mới có thể bị giả mạo. Hãy lập inventory cho headers mà downstream đang tin:

| Header nhóm | Ví dụ | Cách xử lý |
|---|---|---|
| Identity | `X-User-Id`, `X-Role`, `X-Tenant-Id` | Strip từ public input; tái tạo từ identity đã xác thực nếu contract yêu cầu |
| Client IP | `X-Forwarded-For`, `Forwarded` | Tin đúng proxy chain; không lấy raw header client làm IP |
| Internal routing | `X-Internal-Service`, `X-Region` | Chỉ do trusted infrastructure tạo; kiểm soát allowlist |
| Correlation | `X-Correlation-Id` | Validate charset/length; không dùng làm quyền |
| Content metadata | `Content-Type`, `Accept`, `Content-Encoding` | Kiểm tra theo endpoint/body; không sửa tùy tiện |
| Credential | `Authorization`, cookies, API keys | Chỉ chuyển theo security contract; redact logs |

Không strip hàng loạt mọi `X-*` headers nếu ứng dụng cần các header hợp lệ như correlation, idempotency hoặc tracing. Chính sách phải dựa trên inventory và ownership.

## 11. Ma trận kiểm thử end-to-end

Các test dưới đây dùng local Gateway và Catalog mock/service. Kết quả là tiêu chí chấp nhận cho lab; chưa phải kết quả đã chạy trên một project cụ thể.

| ID | Request/điều kiện | Kết quả cần xác nhận |
|---|---|---|
| T01 | `GET /api/catalog/v1/items/42` | Backend nhận `/v1/items/42` |
| T02 | Request có `?lang=vi&page=2` | Query string được giữ nguyên |
| T03 | `GET /api/catalogue/v1/items/42` | Không match route Catalog |
| T04 | `GET /api/catalog/` | Không tạo path backend ngoài contract; trả lỗi route/backend phù hợp |
| T05 | Path có slash cuối | Hành vi trailing slash được ghi rõ và nhất quán |
| T06 | Path có `%2F` | Reject hoặc xử lý theo policy đã định; không bypass route |
| T07 | Client gửi `X-User-Id: administrator` | Backend không nhận header này |
| T08 | Client gửi `X-User-Role: SUPER_ADMIN` | Backend không nhận header này |
| T09 | Client gửi `X-API-Contract: attacker` | Backend nhận giá trị Gateway đặt `catalog-v1` |
| T10 | Client gửi correlation ID hợp lệ | Request và response dùng cùng ID |
| T11 | Client gửi correlation ID có khoảng trắng/ký tự lạ | Gateway thay bằng UUID an toàn |
| T12 | Client gửi correlation ID lặp | Backend chỉ nhận một giá trị chuẩn |
| T13 | Response bình thường | Có `X-Correlation-Id` và header policy đã chọn |
| T14 | Catalog ném `ProductNotFoundException` | HTTP 404, `application/problem+json`, `PRODUCT_NOT_FOUND` |
| T15 | Catalog trả HTTP 500 | CircuitBreaker xử lý theo `statusCodes`; fallback 503 khi policy kích hoạt |
| T16 | Catalog connection refused | Fallback Problem Details `CATALOG_UNAVAILABLE` |
| T17 | Circuit đã OPEN | Request không gọi backend; trả fallback ổn định |
| T18 | Client gọi trực tiếp fallback path | Bị Spring Security từ chối |
| T19 | Public path không match route | 404 routing được phân biệt với domain 404 |
| T20 | Backend trả CORS headers trùng | CORS owner/dedupe policy hoạt động đúng |
| T21 | API cá nhân hóa trả response | `Cache-Control: no-store` theo route policy |
| T22 | Response có `Server`/`X-Powered-By` | Headers được remove nếu policy yêu cầu |
| T23 | Downstream cần bearer token | `Authorization` được relay đúng security contract, không bị xóa ngoài ý muốn |
| T24 | Request qua trusted ingress | Forwarded metadata phản ánh proxy chain đã cấu hình |
| T25 | Request trực tiếp tới backend từ untrusted network | Bị network/service authentication policy từ chối |
| T26 | Gửi POST tới path chỉ cho phép GET | Không match route GET; không rewrite sang endpoint khác |
| T27 | Catalog 404 | Không bị CircuitBreaker đổi thành `CATALOG_UNAVAILABLE` |
| T28 | Fallback response | Có status 503, `code`, `type`, correlation ID và không có stack trace |
| T29 | Request không có route nhưng có correlation requirement toàn ứng dụng | WebFilter/ingress xử lý correlation vì GlobalFilter không chạy trước route selection |
| T30 | Gateway và backend cùng cấu hình CORS | Chỉ một tầng sở hữu CORS hoặc headers được deduplicated theo policy |

### 11.1. Kiểm thử status và body bằng curl

Đối với domain 404:

```bash
curl -sS -D - \
  -H "X-Correlation-Id: lab-not-found-999" \
  "http://localhost:8080/api/catalog/v1/items/999"
```

Kiểm tra status 404, media type Problem Details và body chứa `PRODUCT_NOT_FOUND`. Không chỉ kiểm tra `detail`, vì câu mô tả có thể đổi theo ngôn ngữ.

Đối với fallback:

```bash
curl -sS -D - \
  -H "X-Correlation-Id: lab-catalog-down" \
  "http://localhost:8080/api/catalog/v1/items/42"
```

Kiểm tra 503 và `CATALOG_UNAVAILABLE`. Nếu circuit chưa đủ threshold để OPEN, request vẫn có thể chỉ phản ánh lỗi upstream theo cấu hình; hãy phân biệt fallback của một call với circuit state.

### 11.2. Kiểm thử header spoofing

Gửi một request với cả header hợp lệ và header giả:

```bash
curl -i \
  -H "X-Correlation-Id: lab-header-check" \
  -H "X-User-Id: root" \
  -H "X-User-Role: ADMIN" \
  -H "X-API-Contract: forged" \
  "http://localhost:8080/api/catalog/v1/items/42"
```

Ở backend, quan sát headers nhận được:

- `X-Correlation-Id` bằng `lab-header-check`.
- Không có `X-User-Id` và `X-User-Role`.
- `X-API-Contract` bằng `catalog-v1`.

Đừng kết luận an toàn chỉ từ response body của Catalog nếu backend không echo headers. Dùng log debug đã redact hoặc một endpoint echo chỉ tồn tại trong profile lab và không public production.

## 12. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xác minh/khắc phục |
|---|---|---|
| Gateway trả 404 dù Catalog đang chạy | Path predicate không match | Kiểm tra prefix, slash và route ID |
| Backend nhận nguyên /api/catalog/... | Rewrite filter không được áp dụng hoặc route khác match | Kiểm tra route predicates/order và regex |
| Backend nhận /items/42 thay vì /v1/items/42 | Strip/rewrite quá nhiều | Chỉ dùng một path transformation |
| Backend nhận path / | Request chỉ có prefix hoặc capture group rỗng | Reject path thiếu phần resource theo contract |
| Query string bị mất | Custom path/body handler tự dựng URI sai | Kiểm tra rewrite filter; không dựng URI mới nếu không cần |
| Regex không thay capture group | Replacement escaping hoặc named group sai | Kiểm tra named group remaining và escape dollar-brace trong YAML |
| Client giả X-User-Role nhưng backend vẫn thấy | Thiếu RemoveRequestHeader, route khác match hoặc header được thêm lại | Kiểm tra combined filter chain và proxy trước/sau Gateway |
| Backend mất Authorization | Filter hoặc security config xóa token | Chỉ strip nếu downstream có cơ chế identity thay thế |
| Backend nhận hai correlation IDs | Dùng Add thay Set, hoặc proxy thêm header khác | Dùng headers.set và kiểm tra mọi tầng |
| Correlation ID không có trên 404 no-route | GlobalFilter chưa chạy vì chưa có route | Dùng WebFilter hoặc ingress cho mọi request |
| Correlation ID không xuất hiện trong response lỗi | Error handler chạy ngoài filter path hoặc response đã commit | Test từng error boundary; thêm ID ở WebFilter/ProblemDetail handler |
| Gateway fallback path bị client gọi trực tiếp | Chưa deny path nội bộ | Thêm Spring Security rule và test direct call |
| Backend 404 bị đổi thành 503 | CircuitBreaker statusCodes cấu hình sai hoặc fallback quá rộng | Chỉ chọn các status thực sự là upstream failure |
| Backend 500 vẫn trả thẳng 500 | Chưa thêm status vào breaker hoặc filter/dependency chưa hoạt động | Kiểm dependency CircuitBreaker, route config và breaker events |
| Một request lỗi chưa kích hoạt fallback do circuit | Circuit threshold/minimum calls chưa đạt | Phân biệt fallback-on-call và OPEN state |
| application/problem+json bị đổi thành application/json | Handler/codec/content negotiation không đặt đúng content type | Đặt MediaType.APPLICATION_PROBLEM_JSON |
| Body lỗi có stack trace | Catch-all handler trả raw exception | Trả detail generic và log exception nội bộ |
| Client parse lỗi bằng text thất bại sau đổi ngôn ngữ | Client phụ thuộc detail | Dùng code ổn định để xử lý |
| CORS báo duplicate allow-origin | Gateway và backend cùng sở hữu CORS | Chọn một owner hoặc dedupe sau khi review policy |
| Browser cache giữ response riêng tư | Cache policy không phù hợp | Đặt Cache-Control theo resource/identity; không áp no-store đại trà |
| Server vẫn xuất hiện | Proxy/ingress thêm header sau Gateway | Kiểm tra response qua từng hop; remove ở edge cuối cùng |
| Client IP sai | Tin forwarded header từ nguồn không tin cậy | Cấu hình trusted proxy chain và network boundary |
| Direct backend request vẫn thành công từ Internet | Backend public hoặc firewall mở | Private service/network policy và service auth |
| CircuitBreaker fallback không tìm được handler | Sai forward path hoặc handler không được component-scan | Kiểm package scan và mapping URL |
| Security deny fallback cũng chặn internal forward | Security chain/dispatch behavior khác dự kiến | Integration-test forward trên version thực tế; thiết kế fallback handler/route nội bộ phù hợp |

## 13. Checklist trước khi đưa chuẩn hóa vào production

### 13.1. Path contract

- [ ] Có bảng public path → internal path cho từng route.
- [ ] Chỉ một tầng sở hữu rewrite.
- [ ] Query parameters được giữ hoặc chuyển đổi theo hợp đồng.
- [ ] Route predicates không match prefix gần giống ngoài ý muốn.
- [ ] Có policy cho trailing slash, encoded slash, duplicate slash và dot segments.
- [ ] Không rewrite path theo dữ liệu header do client tự khai báo.
- [ ] Route order và route ID được review để tránh route rộng che route cụ thể.

### 13.2. Request/response headers

- [ ] Inventory các identity headers mà backend đang tin.
- [ ] Strip client-supplied identity headers trước khi proxy.
- [ ] Authorization chỉ relay theo security contract và audience/scope phù hợp.
- [ ] Correlation ID có giới hạn length/charset và được đặt bằng set.
- [ ] Correlation ID không được dùng làm quyền hoặc tenant identity.
- [ ] Forwarded headers chỉ tin từ proxy/ingress trong trust boundary.
- [ ] Response headers có một owner rõ ràng cho CORS, cache và security policy.
- [ ] Không sửa Content-Length/Encoding/Type nếu body không được biến đổi tương ứng.
- [ ] Không log tokens, cookies, API keys hoặc body nhạy cảm.

### 13.3. Error contract

- [ ] Error responses dùng application/problem+json theo RFC 9457.
- [ ] Có type, title, status, detail phù hợp; instance nếu contract yêu cầu.
- [ ] Có error code ổn định cho client.
- [ ] Domain 404 khác routing 404 và upstream unavailable.
- [ ] Không trả raw exception, hostname nội bộ hoặc stack trace.
- [ ] Gateway fallback chỉ bắt lỗi đã định nghĩa, không che lỗi nghiệp vụ.
- [ ] CircuitBreaker statusCodes chỉ gồm upstream statuses được xem là failure.
- [ ] Direct access tới fallback handler bị chặn.

### 13.4. Vận hành

- [ ] Có metrics theo route/status và circuit breaker state.
- [ ] Log có correlation ID để nối Gateway với backend.
- [ ] Distributed tracing dùng trace context; không thay bằng correlation ID tự chế.
- [ ] Có test cho route match, rewrite, header spoofing, Problem Details và fallback.
- [ ] Backend không public trực tiếp hoặc có service authentication/network policy.
- [ ] Version Spring Boot/Spring Cloud được quản lý bởi BOM tương thích.
- [ ] Có rollback nếu rewrite/header contract làm client cũ lỗi.

## 14. Bài tập và câu hỏi tự kiểm tra

**Bài 1 — Path mapping.** Client gọi /api/catalog/v1/items/42; backend chỉ nhận /v1/items/42. Viết route predicate và RewritePath phù hợp.

**Bài 2 — StripPrefix.** Khi nào StripPrefix=2 dễ đọc hơn RewritePath? Nêu một trường hợp regex phù hợp hơn.

**Bài 3 — Query string.** Vì sao rewrite path thông thường không nên làm mất ?lang=vi&page=2?

**Bài 4 — Prefix collision.** Vì sao /api/catalogue/... không được match route /api/catalog/**? Bạn sẽ test điều đó thế nào?

**Bài 5 — Encoded slash.** Rủi ro khi ingress, Gateway và backend decode %2F khác nhau là gì?

**Bài 6 — Header spoofing.** Vì sao X-User-Role: ADMIN do client gửi không thể dùng làm authorization?

**Bài 7 — Remove vs Set.** Phân biệt RemoveRequestHeader, SetRequestHeader và AddRequestHeader.

**Bài 8 — Authorization.** Vì sao không xóa Authorization trên mọi route theo một default filter?

**Bài 9 — Correlation ID.** Vì sao cần validate length/charset của ID do client gửi? Vì sao ID không phải identity?

**Bài 10 — GlobalFilter.** Vì sao GlobalFilter có thể không chạy khi Gateway không tìm thấy route?

**Bài 11 — WebFilter.** Khi nào dùng WebFilter thay cho GlobalFilter để tạo correlation ID?

**Bài 12 — Forwarded headers.** Vì sao không tin X-Forwarded-For trực tiếp từ Internet client?

**Bài 13 — Response headers.** Vì sao SetResponseHeader thích hợp hơn AddResponseHeader cho header cần một giá trị chuẩn?

**Bài 14 — CORS.** Gateway và backend cùng thêm Access-Control-Allow-Origin có thể gây vấn đề gì? Cách xử lý?

**Bài 15 — Cache.** Vì sao Cache-Control: no-store không nhất thiết phù hợp cho mọi public catalog response?

**Bài 16 — Problem Details.** Phân biệt HTTP status với error code trong body.

**Bài 17 — Domain 404.** Vì sao PRODUCT_NOT_FOUND không nên bị đổi thành CATALOG_UNAVAILABLE?

**Bài 18 — Fallback.** Khi nào CircuitBreaker route nên trả CATALOG_UNAVAILABLE? Vì sao fallback không thay domain error handler?

**Bài 19 — No-route.** Vì sao fallback route không chuẩn hóa được 404 trước khi Gateway chọn route?

**Bài 20 — Security.** Vì sao endpoint fallback nội bộ cần deny direct access dù URL bắt đầu bằng /_internal/?

**Bài 21 — Body rewrite.** Nêu ba rủi ro khi Gateway global filter buffer và viết lại mọi upstream error body.

**Bài 22 — Observability.** Correlation ID và W3C trace context khác nhau thế nào?

**Bài 23 — Service-to-service.** Nếu backend cần user identity, nên dùng header tùy chỉnh hay token relay/token exchange? Điều kiện nào phải kiểm tra?

**Bài 24 — Production test.** Nêu các lớp cần xác minh ngoài một curl tới localhost: ingress, network, direct backend, identity và mọi instance.

### Gợi ý đáp án

1. Path=/api/catalog/v1/items/** và RewritePath=/api/catalog/(?<remaining>.*), /$\{remaining}; kiểm tra backend nhận /v1/items/42.
2. StripPrefix=2 khi chỉ bỏ hai segment; RewritePath khi cần regex hoặc thay đổi cấu trúc prefix phức tạp.
3. Query là một phần request target mà backend có thể cần cho locale/pagination/filter; mất query làm thay đổi semantics.
4. Prefix route phải khớp path contract chính xác; gửi request /api/catalogue/... và xác nhận không tới Catalog backend.
5. Có thể tạo path traversal hoặc bypass authorization nếu các tầng diễn giải URL khác nhau; định nghĩa reject/normalize policy và test end-to-end.
6. Client có thể tự đặt header; authorization phải dựa trên principal/token đã xác minh và resource policy.
7. Remove xóa header; Set ghi đè để còn một giá trị; Add thêm giá trị và có thể tạo header lặp.
8. Một số downstream cần tự xác minh bearer token; xóa token sẽ phá auth hoặc thúc đẩy team dùng header không an toàn.
9. Giới hạn giúp ngăn header quá dài/giá trị bất thường và log injection; correlation chỉ nối log, không chứng minh danh tính hay quyền.
10. GlobalFilter chạy sau route selection, nên request no-route chưa đi qua filter chain của route.
11. Khi cần correlation ID cho mọi request kể cả no-route/404 trước routing, dùng WebFilter hoặc ingress.
12. Client có thể giả IP; chỉ tin giá trị được proxy trong trust boundary ghi thêm theo cấu hình.
13. Set thay thế giá trị cũ; Add có thể tạo nhiều values khiến client/server diễn giải khác nhau.
14. Có thể trả header trùng làm browser từ chối CORS; chọn một tầng owner hoặc dedupe sau khi xác minh policy.
15. Public catalog data có thể cache an toàn với ETag/TTL; no-store có thể làm giảm cache hit và tăng tải.
16. HTTP status diễn tả loại response ở transport; error code là định danh ổn định cho logic client.
17. 404 là kết quả domain có chủ đích; 503 là dependency không khả dụng. Gộp hai lỗi làm client retry sai hoặc hiển thị sai.
18. Khi upstream timeout/connection error hoặc 5xx đã chọn là failure; domain 404 vẫn đi qua như response nghiệp vụ.
19. CircuitBreaker filter chỉ có sau route match; no-route xảy ra trước khi filter đó chạy.
20. URL nội bộ vẫn là HTTP handler trên listener; nếu không deny, client có thể tự gọi và nhận fallback response.
21. Có thể mất error code domain, làm sai content-length/encoding/content-type, buffer response lớn/streaming và tăng memory.
22. Correlation ID là ID ứng dụng để nối logs; trace context mang trace/span relationship theo chuẩn W3C và instrumentation.
23. Dùng service identity hoặc token relay/token exchange theo audience/scope; downstream phải validate token và resource permissions.
24. Kiểm tra ingress/public path, network policy/firewall, direct backend access, JWT/service identity, route config và mọi Gateway instance.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Server WebFlux 5.0 — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/how-it-works.html) — route matching, filter chain và request proxying.
- [Spring Cloud Gateway Server WebFlux 5.0 — GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/gatewayfilter-factories.html) — RewritePath, request/response header filters và CircuitBreaker.
- [Spring Framework — Web on Reactive Stack](https://docs.spring.io/spring-framework/reference/web/webflux.html) — WebFlux, WebFilter, ServerWebExchange và reactive handlers.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/web/webflux/ann-rest-exceptions.html) — ProblemDetail, ErrorResponse và exception advice.
- [Spring Security — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — SecurityWebFilterChain và request authorization.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html) — issuer/JWK validation và JWT authorities.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html) — standard error representation và extension members.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — traceparent và propagation giữa services.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html) — request target, status codes và header semantics.

