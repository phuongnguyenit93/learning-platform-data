# Kiểm thử CORS, preflight, JWT, session và TokenRelay

## Mục tiêu bài học

Trong chương **Kiểm thử** của module **Spring Cloud Gateway**, bài này xây dựng chiến lược kiểm thử bảo mật **end-to-end** cho cổng vào microservices. Bốn yếu tố thường xuất hiện cùng một request nhưng phải được kiểm chứng **độc lập và theo thứ tự**:

1. **CORS và preflight:** browser có được phép gọi API từ origin khác? `OPTIONS` đi qua lớp nào và nhận những response headers nào?
2. **JWT:** token có hợp lệ về chữ ký, issuer, audience và thời hạn không? Principal có đủ authority để đi qua Gateway không?
3. **Session:** người dùng OAuth2 Login có phiên đăng nhập hợp lệ? Cookie/session/CSRF và logout được xử lý ra sao?
4. **`TokenRelay`:** Gateway lấy **OAuth2 access token** của người dùng/authorized client rồi đưa vào **outbound `Authorization` header** gửi downstream đúng cách chưa?

Các cơ chế này phục vụ mục đích khác nhau: **CORS không phải authentication**, **authentication không phải authorization**, **session cookie không phải access token downstream**, và **`TokenRelay` không tự kiểm tra quyền tài nguyên ở backend**.

Sau bài học, bạn có thể:

- Thiết kế ma trận kiểm thử cho **origin được phép/bị từ chối**, `OPTIONS` preflight, actual requests và `Access-Control-Allow-Credentials`.
- Phân biệt CORS `allowedMethods`/`allowedHeaders` với route `Method` predicate.
- Viết `WebTestClient` tests cho HTTP/CORS và dùng backend stub để xác minh route, header và body thực.
- Dùng `mockJwt()` để test scope/authority, nhưng biết vì sao nó **không kiểm chứng chữ ký, JWKS, `iss`, `aud` hay `exp`**.
- Kiểm thử JWT thật bằng test issuer/JWKS, token lỗi, hết hạn, sai audience và key rotation.
- Dùng `mockOAuth2Login()`, `mockOidcLogin()`, `mockOAuth2Client()` ở đúng test scope, không nhầm chúng với một OAuth2 authorization-code flow thực.
- Kiểm thử `WebSession`, `SESSION` cookie, SameSite/Secure/HttpOnly, CSRF, logout, timeout và nhiều Gateway replicas.
- Xác minh `TokenRelay` chuyển **đúng access token, đúng registration/audience**, không gửi ID token hoặc cookie browser thay thế.
- Chẩn đoán chính xác `401`/`403`/`404`, lỗi preflight, redirect tới IdP, backend 401, session store và token forwarding.
- Thiết lập logging an toàn để **không ghi JWT, cookie, refresh token, client secret hoặc OAuth2 authorization code** vào báo cáo kiểm thử.

> **Phạm vi:** Spring Cloud Gateway **Server WebFlux**, Spring Security WebFlux (`SecurityWebFilterChain`, `ServerHttpSecurity`) và các cơ chế Gateway route/filter chain. Gateway Server Web MVC, Servlet `HttpSecurity` và `MockMvc` dùng API khác, không sao chép các đoạn test reactive sang MVC. Ví dụ cấu hình chính dùng namespace hiện hành `spring.cloud.gateway.server.webflux.*`; các release cũ thường dùng `spring.cloud.gateway.*`. Luôn căn theo release train Spring Boot/Spring Cloud Gateway/Spring Security thực tế.

## 1. Một request đi qua nhiều ranh giới

Hệ thống minh họa có hai loại client:

- **SPA:** frontend `https://app.example.com` gọi API `https://api.example.com/api/orders/**` với bearer JWT.
- **BFF / OAuth2 Login:** browser giữ session cookie của Gateway; Gateway dùng `TokenRelay` để gửi access token từ OAuth2 authorized client tới Order Service.

```mermaid
flowchart LR
    SPA["SPA / Browser<br/>https://app.example.com"]
    O["Gateway<br/>CORS + Security WebFilters"]
    RT["Gateway route predicates<br/>Path / Method"]
    FR["GatewayFilter chain<br/>TokenRelay / rewrite"]
    API["Order Service<br/>JWT authz + business checks"]
    IDP["OAuth2 / OIDC IdP"]
    SES["WebSession / authorized-client store"]
    SPA -->|"OPTIONS + GET /api/orders"| O
    IDP <-->|"Authorization Code / JWKS"| O
    O <--> SES
    O --> RT --> FR -->|"Bearer access token nếu được relay"| API
```

Với một cross-origin request dùng `Authorization`, browser thường làm:

```text
1. OPTIONS /api/orders/42  (preflight)
2. Gateway trả CORS policy hợp lệ
3. GET /api/orders/42 + Origin + Authorization: Bearer ...
4. Spring Security xác minh token và scopes
5. Gateway chọn route và xử lý filters
6. Backend nhận HTTP request
7. Gateway trả response với CORS headers phù hợp
8. Browser quyết định có cho JavaScript đọc response hay không
```

Nếu bước (2) không đáp ứng CORS, browser **không gửi actual GET theo luồng preflight đó**. Nếu (4) lỗi, backend có thể **không được gọi**. Nếu (7) thiếu `Access-Control-Allow-Origin`, backend có thể đã trả 200 nhưng JavaScript **không đọc được response**.

### 1.1. Đừng gộp tất cả vào một assertion `200 OK`

| Lớp | Câu hỏi kiểm thử | Assertion đại diện |
| --- | --- | --- |
| Route predicate | Gateway chọn route đúng? | Backend stub nhận đúng method/path |
| CORS preflight | Browser được phép gửi actual request? | OPTIONS response có ACAO/ACAM/ACAH thích hợp |
| Authentication | Credential hợp lệ? | Invalid/absent token không vượt security |
| Authorization | Principal có quyền? | Thiếu scope trả 403, backend không nhận request |
| Session | Login duy trì và thu hồi đúng? | Cookie/session qua request kế tiếp, logout hết hiệu lực |
| TokenRelay | Access token có được chuyển đúng? | Upstream nhận **đúng** `Authorization: Bearer ...` |
| Backend authorization | Service có kiểm tra scope/audience/owner? | Token thiếu quyền tài nguyên bị backend từ chối |
| CORS actual response | Browser có đọc response được? | GET response có ACAO đúng origin |
| Observability | Có đủ bằng chứng mà không lộ secrets? | Logs chỉ có route/status/trace ID |

Kiểm thử bảo mật phải bao gồm **happy path** lẫn **negative path**. Một test trả 200 có thể bỏ qua điều kiện route, giả JWT hoặc không kiểm tra token gửi downstream.

## 2. Hai mô hình authentication cần tách trong test

### 2.1. Mô hình A — Resource Server nhận bearer JWT

```text
SPA hoặc native client
    → Authorization: Bearer <JWT>
    → Gateway xác minh JWT
    → Route /api/orders/**
    → Backend (xác minh authorization theo hợp đồng)
```

Gateway là OAuth2 **Resource Server**: nó cần kiểm tra token được gửi vào. Token có thể được forward qua một cơ chế được thiết kế riêng, nhưng điều đó **khác** với việc một OAuth2 **Client** có authorized client/session và dùng `TokenRelay`.

### 2.2. Mô hình B — OAuth2 Login + session + TokenRelay

```text
Browser
    → /oauth2/authorization/portal
    → IdP Authorization Code + OIDC
    → Gateway tạo authenticated WebSession
    → Browser gửi session cookie
    → Gateway lấy OAuth2AuthorizedClient
    → TokenRelay thêm access token vào outbound request
    → Backend Resource Server kiểm tra access token
```

Hai mô hình có thể cùng tồn tại trong một ứng dụng, nhưng khi thử nghiệm phải **nêu rõ request đi qua security chain nào**. Đừng nghĩ cookie session và bearer JWT là hai cách viết tương đương của một credential.

| Khái niệm | Mục đích | Vị trí thường thấy |
| --- | --- | --- |
| JWT access token | Xác thực/ủy quyền API theo audience, scope | Header `Authorization` |
| ID token OIDC | Chứng minh sự kiện login với OAuth2 client | Trong OAuth2/OIDC login context |
| Refresh token | Gia hạn authorized client access token theo policy | Server-side authorized-client store |
| Session ID cookie | Tham chiếu tới WebSession/login state | Header `Cookie` từ browser |
| CSRF token | Chống thao tác state-changing từ browser không được phép | Header/form token trong session-based flow |
| CORS origin | Điều kiện để browser cho phép JS đọc response | `Origin`, `Access-Control-Allow-Origin` |

**Không thay access token bằng ID token** khi gửi xuống Order Service. Backend cần access token có **audience và scope phù hợp**, không phải bằng chứng người dùng đã login vào Gateway.

## 3. Chiến lược test theo tầng

Thay vì một bài test có IdP, Redis, TLS, Gateway, discovery và năm microservices cùng khởi động, chia test thành những tầng có mục đích rõ:

| Tầng | Công cụ | Có kiểm chứng thật điều gì? | Không chứng minh điều gì? |
| --- | --- | --- | --- |
| **Unit authz** | `WebTestClient` + `mockJwt()` | Rules path/scope/role với principal giả | Chữ ký JWT/JWKS |
| **Unit OAuth2** | `mockOAuth2Login()`, `mockOAuth2Client()` | Security context/authorized client logic | Browser redirect/callback/cookie thật |
| **Gateway integration** | Spring Boot random port + HTTP stub | Route, filters, CORS, header forwarding | Full IdP flow nếu đã mock login |
| **JWT validation** | JWT thật + test key/JWKS server | Signature, `iss`, `aud`, `exp`, `nbf`, algorithms | Backend ownership trừ khi test thêm |
| **OAuth2 authorization-code E2E** | Test IdP/OIDC + browser/HTTP client | Redirect, `state`, callback, session/cookie | Production IdP availability |
| **Distributed integration** | 2+ Gateway replicas + session store | Cookie/session consistency, authorized client persistence | Production scale capacity tuyệt đối |
| **Browser E2E** | Browser automation | CORS policy thực, credentials/cookies, redirect behavior | Các trường hợp crypto/JWKS nếu không chủ ý test |

**Nguyên tắc:** mỗi bài test phải ghi rõ **thành phần nào là real, thành phần nào đã mock**. Nếu dùng `mockJwt`, kết luận phải là *authorization rules đúng đối với principal giả*, không phải *JWT validation production đã được kiểm chứng*.

### 3.1. Phụ thuộc thử nghiệm

Ví dụ Maven cho một ứng dụng Spring Boot WebFlux:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Dependency production tùy profile có thể gồm:

```text
spring-cloud-starter-gateway-server-webflux
spring-boot-starter-security
spring-boot-starter-oauth2-resource-server  (JWT API)
spring-boot-starter-oauth2-client           (OAuth2 Login / TokenRelay)
```

Chọn BOM Spring Cloud tương thích với Spring Boot. Tên starter/version mới có thể khác bản cũ. Test HTTP backend dùng một thư viện stub như **MockWebServer**, **WireMock** hoặc một test HTTP server riêng; giữ backend thực tế ngoài port Gateway.

### 3.2. Đặt tên cho fixtures

Nên đặt tên dữ liệu test có chủ đích:

```text
ALLOWED_ORIGIN       = https://app.example.com
DENIED_ORIGIN        = https://attacker.example
API_BASE             = http://localhost:<gateway-random-port>
UPSTREAM_STUB        = http://localhost:<stub-random-port>
TEST_JWT_VALID       = token ký với test key (KHÔNG phải production key)
TEST_SESSION         = session state từ test login
TEST_ACCESS_TOKEN    = FAKE_ACCESS_TOKEN_FOR_STUB
```

**Không** dùng token/session thật, client secret của môi trường staging có khách hàng hoặc access token sao chép từ browser DevTools để viết assertions. Dữ liệu thử nghiệm phải được tạo trong test process hoặc dùng các credentials giả không có hiệu lực.

## 4. CORS: Origin, actual request và preflight

**Origin** được xác định bởi **scheme + host + port**:

```text
https://app.example.com
https://app.example.com:8443
http://app.example.com
```

là ba origins khác nhau. `/path` và query string **không thuộc Origin**.

Browser thường gửi:

```http
OPTIONS /api/orders/42 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization,content-type
```

Các headers cần kiểm tra ở response preflight:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization,content-type
Access-Control-Max-Age: 600
Vary: Origin
```

Nội dung và thứ tự danh sách headers có thể khác theo implementation; **không assert thứ tự chuỗi** nếu semantic là tập giá trị. Preflight được phép có response 200/204 tùy cấu hình/framework, nên chọn assertion theo contract thay vì cố ép mọi môi trường vào một status duy nhất.

### 4.1. CORS không phải authorization

CORS là **quy tắc browser thực thi** khi một trang web cố đọc response cross-origin. Một `curl` hoặc backend HTTP client không bị browser same-origin policy ràng buộc:

```bash
curl -i \
  -H "Origin: https://attacker.example" \
  "https://api.example.com/api/orders/42"
```

Nếu server trả 200 nhưng không có `Access-Control-Allow-Origin`, browser có thể chặn JavaScript đọc response; **không có nghĩa API đã từ chối request ở tầng authentication**.

Do đó:

- CORS không ngăn direct API access.
- CORS không thay JWT validation, role/scope checks hoặc backend authorization.
- CORS không thay CSRF protection khi browser tự gửi cookie.
- Không lấy `Origin` header làm bằng chứng user/tenant identity.

### 4.2. Một bài test CORS cần hai request

**Preflight** và **actual GET** là hai giao dịch riêng:

```text
OPTIONS: xác minh method/headers/origin được phép
GET:     xác minh auth, route, backend và CORS response header
```

Chỉ test `OPTIONS` thành công **không chứng minh actual GET có ACAO**. Ngược lại, chỉ test GET thành công trong `WebTestClient` **không bảo đảm browser có thể gửi GET với custom Authorization header**, vì browser phải vượt preflight trước.

## 5. CORS global và route metadata trong Gateway

Spring Cloud Gateway Server WebFlux cho phép cấu hình CORS ở mức **global** hoặc **từng route**. Cần tách rõ chính sách demo; đừng bật hai policy chồng nhau không kiểm soát.

### 5.1. Ví dụ global CORS cho bài integration test

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          globalcors:
            add-to-simple-url-handler-mapping: true
            cors-configurations:
              '[/**]':
                allowedOrigins:
                  - "https://app.example.com"
                allowedMethods:
                  - GET
                  - POST
                allowedHeaders:
                  - Authorization
                  - Content-Type
                  - X-Request-Id
                exposedHeaders:
                  - X-Trace-Id
                allowCredentials: true
                maxAge: 600
          routes:
            - id: orders
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
```

Giải thích:

- `allowedOrigins` chứa **origin chính xác**; không có dấu slash path.
- `allowedMethods` mô tả **những methods mà CORS cho phép browser dùng**, khác route `Method` predicate.
- `allowedHeaders` mô tả request headers được browser gửi trong actual request.
- `exposedHeaders` cho browser JS đọc thêm các **response headers** không thuộc tập response headers mặc định có thể đọc.
- `allowCredentials: true` cho phép credentialed cross-origin response theo chính sách; **không tự tạo hoặc kiểm chứng cookie/JWT**.
- `maxAge` là thời gian browser có thể cache kết quả preflight, không phải cache JWT/session.
- `add-to-simple-url-handler-mapping: true` hữu ích khi `Method=GET` khiến OPTIONS **không match route predicate**. Nó giúp global CORS handler xử lý preflight tương ứng.

**Quan trọng:** ví dụ ở `localhost:9001` là backend stub cho test; không phù hợp production khi port đó không tồn tại trên Gateway pod. Thay bằng test server port thực qua cấu hình động của test.

### 5.2. Khi cấu hình CORS theo route

Thay thế chính sách global thích hợp bằng `metadata.cors` cho route tương ứng:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              metadata:
                cors:
                  allowedOrigins:
                    - https://app.example.com
                  allowedMethods:
                    - GET
                  allowedHeaders:
                    - Authorization
                  allowCredentials: true
                  maxAge: 300
```

**Đây là biến thể thay cho global config phía trên**, không copy cả hai vào một ứng dụng thử nghiệm rồi mặc định Spring sẽ chọn policy mong muốn. Với CORS metadata theo route, nếu route còn có `Method=GET`, OPTIONS có thể không chọn được route; khi đó cần thiết kế global fallback/handler mapping hoặc security CORS integration phù hợp.

### 5.3. CORS kết hợp Spring Security

Spring Security WebFlux được thực thi **trước** Gateway route filtering ở nhiều đường xử lý. Preflight thường **không chứa cookie/session/Authorization giống actual request**. Nếu Security từ chối OPTIONS trước khi CORS handler xử lý, browser sẽ thấy lỗi CORS dù JWT dùng cho actual GET vẫn hợp lệ.

Vì vậy:

- CORS cần được xử lý **trước authentication gate** đối với preflight.
- Có thể dùng `CorsWebFilter`/Security CORS integration phù hợp hoặc cho OPTIONS qua một security rule **có phạm vi rõ** để Gateway global CORS xử lý.
- Không coi `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` là giải pháp toàn bộ; nó chỉ ảnh hưởng authorization, **không tự phát ACAO/ACAM/ACAH**.
- Không để hai CORS owners (Gateway, Spring Security, ingress, backend) cùng phát nhiều `Access-Control-Allow-Origin` values.
- Dù OPTIONS được phép, **actual GET/POST vẫn phải được auth/authz bình thường**.

Lựa chọn thứ tự CORS/Security là một quyết định cấu hình cần **integration test trên framework version thật**, không chỉ unit test một filter rời.

## 6. Kiểm thử preflight bằng WebTestClient

Ví dụ dưới đây giả định Gateway chạy trên một random port, có profile CORS như mục 5.1 và `WebTestClient` **gửi HTTP thật** đến listener của Gateway.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class GatewayCorsHttpIT {

    @LocalServerPort
    int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }

    @Test
    void allowedPreflightContainsCorsPolicy() {
        client().options()
            .uri("/api/orders/42")
            .header(HttpHeaders.ORIGIN, "https://app.example.com")
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "GET"
            )
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type"
            )
            .exchange()
            .expectStatus().is2xxSuccessful()
            .expectHeader()
                .valueEquals(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.com"
                )
            .expectHeader()
                .exists(HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS)
            .expectHeader()
                .exists(HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }
}
```

**Lưu ý:** đoạn code là một **test fixture**; cần các dependencies, test profile và bean security/CORS đã phối hợp đúng. Import `@LocalServerPort` có thể đổi vị trí ở Spring Boot dòng mới, kiểm tra theo dependency. `@Autowired` trong imports ở đây không cần dùng, có thể bỏ khi đưa vào project.

Test này kiểm tra **HTTP preflight thực**. Nó không giả mạo security context bằng `mockJwt()`, vì browser preflight bình thường không được đồng nhất với actual JWT request.

### 6.1. Chứng minh preflight không gọi backend

Kết hợp backend stub và đếm số requests:

```text
Given:
  Stub receivedRequests = 0

When:
  OPTIONS /api/orders/42
  Origin: https://app.example.com
  Access-Control-Request-Method: GET

Then:
  Gateway returns valid CORS response
  Stub receivedRequests = 0
```

Điều này quan trọng: CORS preflight thường là **quyết định của gateway/web layer**, không cần gửi đến Order Service. Nếu OPTIONS bị forward ngoài ý muốn, backend có thể trả 401/404/405 và browser ngừng gửi actual request.

### 6.2. Negative preflight: origin sai

```java
@Test
void deniedOriginMustNotBeAuthorizedByCors() {
    client().options()
        .uri("/api/orders/42")
        .header(HttpHeaders.ORIGIN, "https://attacker.example")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
            "GET"
        )
        .exchange()
        .expectHeader()
            .doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
}
```

Tùy CORS/Security implementation, request có thể trả 403 hoặc một non-2xx khác. **Assertion bất biến** là browser không được nhận CORS policy cho phép origin bị cấm. Nếu response vẫn có `Access-Control-Allow-Origin: *` từ ingress/backend, bài test trên phải fail để bạn tìm **CORS owner sai**.

### 6.3. Negative preflight: method/header không được phép

Thử:

```http
OPTIONS /api/orders/42
Origin: https://app.example.com
Access-Control-Request-Method: DELETE
Access-Control-Request-Headers: authorization
```

và:

```http
OPTIONS /api/orders/42
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-unapproved-admin-header
```

Kỳ vọng: preflight không được **duyệt method/header bị cấm**. Một response 200 không có `Access-Control-Allow-Methods: DELETE` cũng không cho phép browser gửi DELETE theo nghĩa CORS. Kiểm tra status, headers và không có call tới backend.

### 6.4. `Method=GET` không match OPTIONS

Đây là bẫy phổ biến:

```yaml
predicates:
  - Path=/api/orders/**
  - Method=GET
```

Trong preflight:

```http
OPTIONS /api/orders/42
Access-Control-Request-Method: GET
```

**HTTP method thực là OPTIONS**; `Access-Control-Request-Method: GET` chỉ là thông báo browser định làm gì tiếp theo. Vì vậy `Method=GET` predicate **không match OPTIONS**.

Nếu route không được chọn, `metadata.cors` của route đó có thể không được dùng. Global CORS `add-to-simple-url-handler-mapping: true` là một hướng xử lý được tài liệu Gateway Server WebFlux mô tả. Test phải chứng minh **preflight đi đúng handler và trả headers**, không chỉ rằng `GET` route đang tồn tại.

## 7. Actual cross-origin request sau preflight

Một GET thật từ browser:

```http
GET /api/orders/42 HTTP/1.1
Origin: https://app.example.com
Authorization: Bearer <jwt-access-token>
```

Response thành công có thể là:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"id":"42","state":"PAID"}
```

Thực tế `Access-Control-Allow-Credentials: true` cần cho **credentialed CORS** (ví dụ browser `credentials: 'include'`), nhưng việc request có hoặc không cookie/JWT cũng phụ thuộc browser API/client configuration. Không suy từ header response này rằng Gateway đã xác thực ai.

### 7.1. CORS headers trên response lỗi

Thử cùng `Origin` cho các tình huống:

| Actual request | Response kỳ vọng về auth | CORS policy kỳ vọng |
| --- | --- | --- |
| GET không bearer | 401 (API resource server profile) | Browser được phép đọc status lỗi nếu origin hợp lệ |
| GET JWT sai chữ ký | 401 | Không mở CORS cho origin cấm |
| GET JWT đúng nhưng thiếu scope | 403 | ACAO cho origin hợp lệ theo policy |
| GET JWT hợp lệ | 200 từ backend stub | ACAO đúng origin |
| GET từ origin cấm | Auth có thể vẫn chạy | Không có ACAO cho origin cấm |
| GET backend trả 503 | 503/fallback theo route | CORS headers không bị mất do error handling |

Một API có thể trả **401 đúng** nhưng frontend chỉ nhìn thấy **“CORS error”** nếu header ACAO bị thiếu trên error response. Vì vậy cần test những nhánh phát sinh lỗi **trước và sau Gateway route chain**: Spring Security, RateLimiter, CircuitBreaker, backend và exception handler.

### 7.2. Không nhầm `allowedHeaders` với `exposedHeaders`

`allowedHeaders` trả lời:

> Browser được gửi **request header** `Authorization` trong actual request không?

`exposedHeaders` trả lời:

> JavaScript được đọc **response header** `X-Trace-Id` không?

Không thể sửa preflight bị từ chối `Authorization` bằng cách chỉ thêm `Authorization` vào `exposedHeaders`. Đây là hai hướng hoàn toàn khác nhau.

### 7.3. Vary và cache

CORS response theo origin cần phù hợp caching semantics. Nếu proxy/CDN cache cùng một response cho nhiều origins mà không tôn trọng `Vary: Origin` hoặc variation theo preflight method/headers khi phù hợp, có thể gây response sai policy.

Test:

```text
Origin A → ACAO A
Origin B → ACAO B (nếu được phép)
Origin C → không có ACAO nếu bị cấm
```

Với API có dữ liệu theo user, cũng cần `Cache-Control`/private cache policy. `Vary: Origin` **không tự ngăn cache nhầm theo authenticated user**.

## 8. Credentialed CORS: cookie, JWT và wildcard

Browser có thể gửi credentialed cross-origin request:

```javascript
fetch("https://api.example.com/api/orders/42", {
  method: "GET",
  credentials: "include"
});
```

Với session cookie thuộc domain/Path/SameSite phù hợp, browser có thể tự kèm `Cookie`. Khi dùng `allowCredentials: true`, response không được dùng wildcard `Access-Control-Allow-Origin: *` cho credentialed browser read.

### 8.1. Test wildcard không được bypass

Trường hợp cần phát hiện:

```yaml
allowedOrigins:
  - "*"
allowCredentials: true
```

Đây là cấu hình không hợp lệ/không an toàn cho credentialed CORS; Spring Framework có thể từ chối hoặc không cho phép tổ hợp này tùy cách bind/config. Test phải xác nhận **không** có wildcard origin cùng credential allowance cho các requests nhạy cảm.

`allowedOriginPatterns` có thể được dùng trong một số trường hợp có wildcard patterns, nhưng pattern phải được review; ví dụ quá rộng cho tất cả subdomains có thể vô tình tin một tenant-controlled subdomain. Dùng exact origin allowlist khi số origin nhỏ.

### 8.2. SameSite/Secure/HttpOnly là chính sách cookie, không phải CORS

Test các thuộc tính:

```http
Set-Cookie: SESSION=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=None
```

Chỉ dùng `SameSite=None` khi thực sự cần **cross-site cookies**, cùng với `Secure` theo browser requirements. Ứng dụng cùng-site có thể chọn `Lax`/`Strict` khi phù hợp. Trình duyệt có thể có chính sách hạn chế **third-party cookies** ngay cả khi `SameSite=None; Secure`.

Test phải bao gồm browser thật hoặc browser automation nếu hành vi phụ thuộc cookie policy. `WebTestClient` **không thực thi same-origin policy hay third-party cookie restrictions của browser**.

### 8.3. CORS không thay CSRF

Khi browser dùng cookie session tự gửi, một website khác có thể cố khởi tạo request state-changing. CORS quyết định JS có được đọc response, **không tự chứng minh request không thể gây tác động**.

Với POST/PUT/PATCH/DELETE dùng session cookie, test:

- Không có CSRF token → bị chặn theo policy.
- CSRF token sai → bị chặn.
- CSRF token hợp lệ → request được phép **nếu còn đủ authentication và authorization**.
- `Origin` sai → CORS policy không cho browser đọc response, nhưng bảo vệ CSRF vẫn phải riêng.

Không tắt CSRF cho mọi route chỉ để khiến một bài test CORS POST qua được.

## 9. JWT Resource Server: cấu hình mẫu cho kiểm thử

Với API nhận bearer JWT, Spring Security WebFlux có thể sử dụng `ReactiveJwtDecoder` để kiểm tra chữ ký và claims.

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer
```

Trong production, `issuer-uri` phải là nhà phát hành token đáng tin. Nếu backend yêu cầu một audience cụ thể, cần cấu hình **audience validation** phù hợp phiên bản Spring Boot hoặc một validator tùy chỉnh; không giả định kiểm tra issuer là đã kiểm tra audience.

### 9.1. `SecurityWebFilterChain` minh họa cho API JWT

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ApiJwtSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Đây là **khung security riêng cho resource-server test profile**; chưa bao gồm toàn bộ CORS/CSRF, health, actuator và multi-chain policies. Phải bổ sung CORS handling cho OPTIONS ở lớp thích hợp như mục 5.3; nếu không, `.anyExchange().authenticated()` có thể chặn preflight.

Spring Security thường ánh xạ JWT scope thành authority có prefix `SCOPE_`, nhưng các claim converters có thể được tùy chỉnh. Test phải kiểm tra **authority hiệu lực** chứ không chỉ nhìn raw JWT `scope` string.

### 9.2. Khi nào nhận 401, khi nào nhận 403?

| Trường hợp | Kỳ vọng điển hình | Ý nghĩa |
| --- | --- | --- |
| Không bearer token trên API cần login | **401** | Chưa authentication |
| Bearer token sai/malformed/hết hạn | **401** | Authentication thất bại |
| JWT chữ ký hợp lệ nhưng thiếu `orders.read` | **403** | Authentication thành công, authorization không đủ |
| JWT đúng scope nhưng sai object ownership | **403 hoặc 404 theo contract backend** | Backend resource authorization |
| JWT đúng scope và quyền | 200/2xx theo backend | Không chứng minh CORS nếu thiếu Origin tests |
| Session-only browser bị gửi tới bearer-only route | 401 hoặc redirect tùy security chain | Cần xác định thiết kế |

Status cụ thể có thể thay theo authentication entry point/error handler; test dựa trên contract có chủ đích, không coi 401/403/302 là hoán đổi tùy tiện.

## 10. `mockJwt()`: kiểm thử quyền, không kiểm thử mật mã

Spring Security cung cấp `SecurityMockServerConfigurers.mockJwt()` cho **`WebTestClient` gắn với Spring WebFlux application context**.

### 10.1. Ví dụ kiểm tra scope

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

class JwtAuthorizationRulesTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void readerScopeAllowsRead() {
        client()
            .mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("user-42"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.read"
                )))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void missingScopeIsForbidden() {
        client()
            .mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_profile.read"
                )))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Đây là mẫu test logic**, cần `@SpringBootTest` hoặc một test context tương đương, bean security/route và upstream stub trả 200 để `readerScopeAllowsRead()` hoàn tất. `ApplicationContext` phải được inject bởi test framework; class trên không tự chạy khi chỉ copy nguyên mà không có test configuration.

Điểm quan trọng của `mockJwt()`:

- Nó tạo authentication/principal kiểu JWT trong security context.
- Test có thể chỉ định authorities và claims.
- Nó **không cần** một JWT raw được ký số.
- Nó **không gọi** JWKS/issuer để xác minh chữ ký.
- Nó không tự mô phỏng browser preflight, OAuth2 login callback hay authorized-client persistence.

**Vì thế:** `mockJwt()` là đúng cho **authorization behavior**, nhưng **không được dùng làm bằng chứng JWT decoder đang kiểm tra `exp`, `iss`, `aud`, thuật toán ký hoặc key rotation đúng**.

### 10.2. Đừng nhầm `.claim("scope", ...)` với authority

Nếu chỉ viết:

```java
.jwt(jwt -> jwt.claim("scope", "orders.read"))
```

thì kết quả authorization còn phụ thuộc cách test JWT mutator và authority converter tạo `GrantedAuthority`. Để bài test tường minh, có thể dùng:

```java
.authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")
)
```

Sau đó viết **test riêng** cho converter ánh xạ `scope`/`scp`/roles để tránh trộn hai câu hỏi: *claim được parse ra sao* và *quy tắc quyền có đúng không*.

### 10.3. `mockJwt()` không đi qua socket HTTP thật

`WebTestClient.bindToApplicationContext(context)` với `springSecurity()` gắn một **mock exchange**. Nếu cần test **real HTTP listener** và JWT decoder, dùng:

```java
WebTestClient.bindToServer()
    .baseUrl("http://localhost:" + gatewayPort)
    .build();
```

và gửi bearer token **được ký bởi test issuer/key**, không dùng `mockJwt()`. Điều này cũng giúp test proxy headers, TLS termination ở integration environment và actual CORS response.

## 11. Test JWT thật: chữ ký, issuer, audience và thời hạn

Thiết kế một **test authorization server/JWKS endpoint** chỉ dùng test keys, hoặc khởi tạo `ReactiveJwtDecoder` với test public key. Kiểm thử token thật cần ít nhất:

| Case | Token | Kỳ vọng |
| --- | --- | --- |
| Hợp lệ | Signature OK, `iss` đúng, `aud` đúng, `exp` tương lai, scope đủ | Cho qua Gateway |
| Sai signature | Ký bằng key không được trust | 401 |
| `alg=none`/algorithm không được phép | Header khai báo thuật toán không được chấp nhận | 401 |
| Sai issuer | `iss` khác issuer được cấu hình | 401 |
| Sai audience | `aud` không chứa API được phép | 401 nếu audience validator được bật |
| Hết hạn | `exp` trong quá khứ | 401 |
| Chưa hiệu lực | `nbf` trong tương lai | 401 |
| Thiếu scope | Token hợp lệ nhưng không có `orders.read` | 403 |
| Key rotation | Token ký bằng key mới được JWKS xuất bản | Theo policy refresh/trust |
| Token revocation | Token bị thu hồi trước `exp` | Phụ thuộc introspection/revocation strategy |

Không tạo JWT giả bằng cách chỉ base64 JSON rồi gọi nó là access token hợp lệ. Cần test cryptographic verification thực với test key.

### 11.1. Test bằng real HTTP

Khung:

```java
WebTestClient http = WebTestClient.bindToServer()
    .baseUrl("http://localhost:" + gatewayPort)
    .build();

http.get()
    .uri("/api/orders/42")
    .headers(headers -> headers.setBearerAuth(
        signedTestJwtWithOrdersReadScope
    ))
    .exchange()
    .expectStatus().isOk();

http.get()
    .uri("/api/orders/42")
    .headers(headers -> headers.setBearerAuth(
        signedTestJwtWithWrongAudience
    ))
    .exchange()
    .expectStatus().isUnauthorized();
```

Đây là **test scaffold**; hai biến token được tạo bằng test JWT builder/encoder và test IdP. Không đưa production private key/refresh token/client secret vào test repository.

### 11.2. Chú ý audience validation

Chỉ khai báo:

```yaml
issuer-uri: https://identity.example.test/issuer
```

không tự chứng minh API đã kiểm tra `aud` theo yêu cầu ứng dụng. Với Spring Boot version hỗ trợ, có thể dùng property audience validation; hoặc viết `OAuth2TokenValidator<Jwt>` để yêu cầu chính xác audience.

**Test âm tính cho sai audience là bắt buộc** khi Gateway/Order Service quyết định quyền dựa vào access token dành cho API cụ thể. Một token hợp lệ dành cho service khác không được coi là hợp lệ mọi nơi.

### 11.3. Clock skew và test time

`exp` và `nbf` phụ thuộc đồng hồ của issuer/resource server. Test nên dùng thời điểm cố định hoặc configurable clock/validator khi framework cho phép:

- Hết hạn vượt quá allowed clock skew → phải bị từ chối.
- Chưa hiệu lực vượt quá skew → phải bị từ chối.
- Biên giới gần `exp` → xử lý theo policy chính xác.
- Hệ thống phân tán có time synchronization.

Không tăng clock skew quá lớn để “làm hết lỗi” nếu việc đó cho phép token hết hạn dùng thêm lâu ngoài chính sách.

## 12. Session WebFlux và OAuth2 Login

Với OAuth2 Login, Gateway có thể dùng **`WebSession`** duy trì trạng thái người dùng sau authorization-code callback. Browser lưu **session cookie** tham chiếu tới state phía server. `TokenRelay` có thể lấy `OAuth2AuthorizedClient` tương ứng với authenticated principal.

```mermaid
sequenceDiagram
    participant B as Browser
    participant G as Gateway WebFlux
    participant IDP as OIDC Provider
    participant S as Session / Authorized Client Store
    participant U as Backend
    B->>G: GET /oauth2/authorization/portal
    G-->>B: 302 tới IdP, state/PKCE theo client config
    B->>IDP: Login + user consent
    IDP-->>B: Redirect với authorization code
    B->>G: GET /login/oauth2/code/portal?code=...&state=...
    G->>IDP: Token request server-to-server
    IDP-->>G: Access token (+ ID token / refresh token nếu có)
    G->>S: Lưu authenticated session + authorized client
    G-->>B: Set-Cookie: SESSION=...; redirect
    B->>G: GET /bff/orders + Cookie: SESSION=...
    G->>S: Đọc session và authorized client
    G->>U: GET /orders + Authorization: Bearer access-token
    U-->>G: 200 hoặc 401/403
    G-->>B: Response
```

Sơ đồ là mô hình logic; chi tiết callback, authorization request repository, PKCE, token refresh và lưu trữ tùy phiên bản và identity provider.

### 12.1. Đừng dùng `mockOAuth2Login()` để tuyên bố cookie thật hoạt động

Spring Security test:

```java
client.mutateWith(mockOAuth2Login())
    .get()
    .uri("/bff/orders")
    .exchange();
```

tạo một OAuth2 authentication giả trong mock exchange và các test fixtures liên quan. Nó hữu ích khi test route authorization và principal binding, nhưng **không** chứng minh:

- Browser thật đã nhận và gửi session cookie.
- Authorization code callback, `state` và PKCE hợp lệ.
- Cookie mang `Secure`, `HttpOnly`, `SameSite`, Domain/Path đúng.
- Session được lưu/đọc lại sau restart hoặc đổi Gateway replica.
- Refresh token được lưu an toàn và sử dụng đúng policy.

Những khía cạnh đó cần **HTTP/browser integration test** với IdP và session store thật/test-double phù hợp.

### 12.2. Các case session cần kiểm thử

| Case | Điều cần chứng minh |
| --- | --- |
| Chưa đăng nhập | `/bff/**` redirect tới login hoặc trả 401 theo API contract |
| Login thành công | Gateway lập session, browser giữ cookie hợp lệ |
| Request kế tiếp | Cookie dẫn đến authenticated session cùng principal |
| Cookie bị sửa | Không chiếm được session hoặc mạo danh người khác |
| Session hết hạn | Không truy cập protected API bằng cookie cũ |
| Logout | Session bị invalidate, authorized client/token lifecycle theo policy |
| Session fixation | Session ID không thể bị attacker cố định qua login flow |
| CSRF | State-changing cookie requests cần token hợp lệ |
| Cookie flags | `Secure`, `HttpOnly`, `SameSite`, Path/Domain phù hợp |
| Cross-site browser | Browser thực sự gửi cookie theo policy, không chỉ WebTestClient |
| Multi-replica | Login ở pod A, request tới pod B vẫn đọc được session nếu yêu cầu |
| Restart | Session/authorized client tồn tại hoặc hết hiệu lực theo contract |

### 12.3. Session cookie không phải access token

Một request:

```http
GET /bff/orders HTTP/1.1
Cookie: SESSION=<opaque-session-id>
```

không có nghĩa downstream nên nhận:

```http
Authorization: Bearer <opaque-session-id>
```

`TokenRelay` cần tìm đúng **OAuth2 access token** trong authorized-client context. Không copy `SESSION` cookie thành bearer token, không forward raw browser cookie nếu backend không thuộc cùng session boundary.

## 13. `mockOAuth2Login()`, `mockOidcLogin()` và `mockOAuth2Client()`

### 13.1. Khi kiểm tra OAuth2 principal và quyền

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;

client.mutateWith(
    mockOAuth2Login()
        .authorities(
            new SimpleGrantedAuthority("ROLE_USER")
        )
)
.get()
.uri("/bff/orders")
.exchange()
.expectStatus().isOk();
```

Mẫu này cần test context và backend stub nếu route proxy tới upstream; mục tiêu là kiểm tra **security rules với OAuth2 login principal**.

Với OIDC user cần kiểm tra ID-token claims hoặc principal type, dùng `mockOidcLogin()`. Dù vậy `mockOidcLogin()` **không chứng minh OIDC provider đã ký ID token thật hoặc callback được verify đúng**.

### 13.2. Khi kiểm tra authorized client

Test support có:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Client;

client.mutateWith(
    mockOAuth2Client("portal")
)
.get()
.uri("/bff/orders")
.exchange();
```

Nó có thể thiết lập một `OAuth2AuthorizedClient` giả ở repository mock cho request. Có thể chỉnh token và client registration qua mutator theo Spring Security test API.

**Quan trọng:** có `mockOAuth2Client("portal")` trong mock exchange **không tự bảo đảm** TokenRelay chọn token đó trong một hệ thống đã cấu hình custom `ReactiveOAuth2AuthorizedClientService` hoặc authorization manager khác. Hãy kiểm chứng `Authorization` header ở backend stub và điều chỉnh test fixture sao cho phù hợp với actual lookup path của filter.

### 13.3. Test tránh kết luận quá mức

| Test utility | Chứng minh được | Chưa chứng minh |
| --- | --- | --- |
| `mockJwt()` | JWT principal/authorities cho authz | Signature/claims validation thật |
| `mockOAuth2Login()` | Logged-in OAuth2 principal giả | Real code flow, cookie persistence |
| `mockOidcLogin()` | OIDC principal/claims giả | Real OIDC issuer/ID token verification |
| `mockOAuth2Client()` | Authorized-client lookup ở fixture mock | Downstream TokenRelay token đúng trong deployment thật |
| `csrf()` | Rule CSRF phản hồi token hợp lệ | Browser cookie delivery và origin policy |

Không dùng các mock test helpers làm thay thế một **authorization-code flow chạy qua HTTP/browser** khi kiểm thử cookie/session/TokenRelay end-to-end.

## 14. `TokenRelay`: kiểm thử token thật sự được chuyển cho upstream

Tài liệu Spring Cloud Gateway Server WebFlux mô tả `TokenRelay` là `GatewayFilter` lấy **OAuth2 access token** của authenticated user/authorized client và đặt vào outbound request header.

### 14.1. Cấu hình route dành cho session/OAuth2 client

Một route riêng trong **BFF test profile**:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-bff
              uri: http://localhost:9001
              predicates:
                - Path=/bff/orders/**
              filters:
                - StripPrefix=1
                - TokenRelay=
```

`TokenRelay=` không tham số được tài liệu dùng cho **access token gắn với user đã OAuth2 login**. Nếu chỉ định:

```yaml
filters:
  - TokenRelay=portal
```

thì filter chọn authorized client theo `clientRegistrationId` tương ứng. Tên registration `portal` phải tồn tại trong `spring.security.oauth2.client.registration.*` và có authorized-client state hợp lệ.

**Không tự suy:** cứ thêm filter là Gateway sẽ login người dùng, lấy token hoặc refresh token thành công ở mọi request. Cần OAuth2 client dependency, `ReactiveClientRegistrationRepository`, authorized-client infrastructure và phiên đăng nhập hợp lệ.

### 14.2. Dependency và store

Để dùng TokenRelay ở Gateway Server WebFlux, thường cần:

```text
spring-boot-starter-oauth2-client
spring.security.oauth2.client.registration.portal.*
spring.security.oauth2.client.provider.portal.*
```

Trong tài liệu Gateway, `TokenRelayGatewayFilterFactory` chỉ được tạo khi các properties OAuth2 client tạo được **`ReactiveClientRegistrationRepository`**. Tài liệu cũng lưu ý implementation mặc định của `ReactiveOAuth2AuthorizedClientService` có thể sử dụng **in-memory store**; nếu yêu cầu nhiều pods/restart và lưu token bền vững, phải thiết kế repository phù hợp.

### 14.3. Kiểm tra chính xác header ở backend

Test với một **backend stub** (không phải backend production) đã nhận request:

```http
GET /orders/42 HTTP/1.1
Host: localhost:9001
Authorization: Bearer FAKE_TEST_ACCESS_TOKEN
```

Assertions bắt buộc:

1. `Authorization` có đúng **một bearer value** theo contract.
2. Bearer value đúng **access token của authorized client** được chọn.
3. Không thay bằng OIDC ID token.
4. Không rò `SESSION` cookie của Gateway vào backend nếu backend không dùng chung session.
5. Không dùng inbound `Authorization` do client tự đặt để override token relay trái policy.
6. Route `StripPrefix` tạo đúng path.
7. Backend resource server kiểm tra **audience/scope/owner** của token, không chỉ token tồn tại.
8. Nếu token thiếu/hết hạn/refresh thất bại, request không âm thầm được gửi bằng credential sai.

**Đây là bài kiểm tra token forwarding**, khác với bài test `mockJwt` chỉ kiểm tra user đã có authorities gì trong Gateway.

### 14.4. Khi không có access token?

Các ca âm tính nên có:

```text
Anonymous user
Expired session
Logged-in principal nhưng thiếu OAuth2AuthorizedClient
Sai clientRegistrationId
Authorized client có access token hết hạn
Refresh token không hợp lệ
Token audience sai với backend
OAuth2 client store không khả dụng
```

Kết quả cụ thể có thể là redirect login, 401/403, error response hoặc từ chối relay tùy cấu hình. Nhưng **không được fallback sang một client bearer token tùy ý hoặc credential của user khác**. Backend stub và logs an toàn phải chứng minh điều đó.

### 14.5. Bearer JWT của Resource Server khác OAuth2 login token

Khi incoming request là:

```http
Authorization: Bearer <jwt>
```

Spring Security resource server có thể tạo `JwtAuthenticationToken`. Tuy nhiên, cơ chế `TokenRelay` gắn với **OAuth2 Client/authorized client** không được giả định sẽ forward raw JWT trong mọi cấu hình chỉ vì Authentication hiện tại chứa JWT. Tài liệu mô tả cả client/resource-server use cases, nhưng việc lấy token cụ thể phụ thuộc phiên bản/filter/registration và security context.

Nếu yêu cầu **JWT passthrough** từ public client xuống backend, hãy thiết kế và kiểm thử riêng policy relay/forward và token audience. Không đánh đồng OAuth2 login `TokenRelay` với một filter generic sao chép `Authorization`.

## 15. Kiểm thử TokenRelay với authorized client giả và HTTP stub

Một kế hoạch test ở tầng application context:

```text
Given:
  User đã OAuth2 login theo mock principal
  Authorized client "portal" có access token = FAKE_ACCESS_A
  Route /bff/orders/** có TokenRelay
  Backend stub lắng nghe /orders/**

When:
  GET /bff/orders/42

Then:
  Backend nhận GET /orders/42
  Backend Authorization = Bearer FAKE_ACCESS_A
  Backend không nhận Cookie SESSION từ browser
  Gateway trả body/status mong đợi
```

Khung `WebTestClient`:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Client;

// webTestClient: bindToApplicationContext + apply(springSecurity())
// backendStub: HTTP server tại route URI test được inject đúng.
webTestClient
    .mutateWith(mockOAuth2Login())
    .mutateWith(mockOAuth2Client("portal"))
    .get()
    .uri("/bff/orders/42")
    .exchange()
    .expectStatus().isOk();

// Assert thêm ở backendStub:
// path "/orders/42", Authorization bearer access token từ fixture.
```

Đây là **test scaffold**, không phải suite hoàn chỉnh: cần tạo `ClientRegistration`, đăng ký test authorized-client repository theo phiên bản và giải quyết lookup path của `TokenRelay`. `mockOAuth2Client()` có default token test; nếu assertion cần đúng token, **đặt test access token rõ ràng** qua API test builder và backend stub.

### 15.1. Mẫu thêm access token vào fixture

```java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

OAuth2AccessToken accessToken = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "FAKE_ACCESS_TOKEN_FOR_STUB",
    Instant.now().minusSeconds(10),
    Instant.now().plusSeconds(300),
    Set.of("orders.read")
);

// Với mockOAuth2Client("portal"):
//   .accessToken(accessToken)
// rồi assert backend nhận đúng bearer token này.
```

Token giả ở đây chỉ nên dùng trong **stub HTTP test**. Một backend Resource Server kiểm tra JWT chữ ký thực sẽ từ chối `"FAKE_ACCESS_TOKEN_FOR_STUB"`; đó không phải lỗi TokenRelay. Vì vậy tách:

- **Relay test:** so outbound header với token fixture.
- **JWT signature test:** dùng JWT được ký bởi test issuer và backend/resource server test thật.
- **OAuth2 code flow test:** dùng test IdP và browser/session/callback thật.

### 15.2. Test không gửi nhầm ID token

OIDC login có thể mang:

```text
id_token:     OIDC identity assertion cho Gateway client
access_token: OAuth2 token dùng để gọi resource API
```

Backend stub phải nhận **access token**, không phải ID token. Đây là một lỗi thường gặp khi developer tự viết header relay từ authenticated principal.

### 15.3. Test không ghi secrets

Trong assertion thất bại, đừng in toàn bộ `RecordedRequest` hoặc HTTP headers ra CI logs nếu request có token thật. Nên dùng token **giả** hoặc kiểm tra:

```text
hasAuthorizationHeader = true
isBearerScheme          = true
matchesExpectedTestToken = true
```

nhưng khi assertion fail, không dump giá trị nhạy cảm. Production observability chỉ cần kết quả token relay (`present`, `missing`, `rejected`) và trace ID, không cần token value.

## 16. Kiểm thử OAuth2 Authorization Code và session thật

Để xác minh callback, cookie và state, dùng một **OIDC test provider** hoặc mock authorization server có endpoints thực:

```text
/.well-known/openid-configuration
/authorize
/token
/jwks
```

Sử dụng **test client registration**, redirect URI và signing keys do test sở hữu. Không gửi browser test qua một production identity provider nếu không có yêu cầu/ủy quyền riêng.

### 16.1. Các bước E2E cần chứng minh

1. Browser chưa có session vào `/bff/orders/42`.
2. Gateway redirect đến `/oauth2/authorization/portal` hoặc identity provider theo flow.
3. Authorization request có `state` khó đoán và các tham số theo contract; PKCE nếu client yêu cầu/hỗ trợ.
4. IdP test trả authorization code và state đúng.
5. Gateway trao đổi code ở token endpoint với client authentication phù hợp.
6. Gateway xác minh `state`, issuer, OIDC ID-token claims và nonce khi áp dụng.
7. Gateway lập authenticated session, phát cookie đúng security flags.
8. Browser gửi cookie ở request `/bff/orders/42` kế tiếp.
9. Gateway tìm authorized client và `TokenRelay` gửi access token tới backend.
10. Logout/invalidate session làm request tiếp theo không được authenticated.

**Các bước 3–6 không được xem là đã pass chỉ vì `mockOAuth2Login()` tạo principal.** Cần thực sự chạy authentication protocol qua HTTP.

### 16.2. Cookie attributes

Ví dụ response mong đợi (tùy deployment):

```http
Set-Cookie: SESSION=<opaque>; Path=/; HttpOnly; Secure; SameSite=Lax
```

Test:

- Cookie không chứa access token/refresh token raw.
- `HttpOnly` khi JS không cần đọc session ID.
- `Secure` cho HTTPS production.
- `SameSite` phù hợp với login callback và cross-site needs.
- Domain/Path không mở cookie sang nhiều host không cần.
- Session fixation mitigation khi login.
- Không lưu credentials trong browser localStorage chỉ để bù lỗi session.

**Lưu ý:** một số OAuth2 redirect/callback và deployment cross-site có yêu cầu SameSite đặc thù. Đừng ép `Strict`/`None` theo một mẫu cứng; phải test trên browser/IdP topology thật.

### 16.3. Session store với nhiều Gateway replicas

Nếu Gateway chạy nhiều pods:

```text
Browser ── cookie ──▶ Gateway A: login
Browser ── cookie ──▶ Gateway B: /bff/orders/42
```

thì cần xác minh cả **WebSession state** lẫn **OAuth2AuthorizedClient state** có thể được đọc ở pod B khi mô hình yêu cầu. Một in-memory repository trên pod A **không** tự chia sẻ sang B, dù hai pods dùng cùng Redis cho một loại state khác.

Test:

- Login qua A rồi gọi B với cùng cookie.
- Restart A và gọi B.
- Session expiry/revocation đồng nhất.
- OAuth2 client access/refresh tokens được bảo vệ/encrypt theo chính sách.
- Session store unavailable thì hệ thống fail theo policy, không tự gán user khác.

## 17. CSRF với session: không trộn với JWT stateless tests

Nếu **BFF session cookie** được browser tự gửi, state-changing routes như:

```http
POST /bff/orders
Cookie: SESSION=...
```

cần một CSRF strategy tương ứng. Spring Security reactive test có:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

client.mutateWith(mockOAuth2Login())
    .mutateWith(csrf())
    .post()
    .uri("/bff/orders")
    .exchange();
```

`csrf()` cấp một test CSRF token hợp lệ trong **mock WebTestClient context**; chưa kiểm tra browser có lấy/đưa CSRF token đúng cách qua cookie/header hay không.

### 17.1. Negative CSRF tests

| Request | Authentication | CSRF token | Kỳ vọng |
| --- | --- | --- | --- |
| GET `/bff/orders` | Cookie session hợp lệ | Không | Được xử lý theo read policy |
| POST `/bff/orders` | Cookie session hợp lệ | Không | Từ chối nếu CSRF protection áp dụng |
| POST `/bff/orders` | Cookie session hợp lệ | Sai | Từ chối |
| POST `/bff/orders` | Cookie session hợp lệ | Đúng | Được đánh giá tiếp theo authz/business rule |
| POST `/bff/orders` | Không login | Đúng | Không trở thành authenticated chỉ vì có CSRF |
| Cross-origin POST | Cookie và Origin khác | Tùy | Phải tuân cả CORS, CSRF và authz |

Với **bearer-only API** không dựa vào credential browser tự gửi, threat model CSRF khác. Có thể tách security chains/profiles để xử lý phù hợp, nhưng **không dùng `csrf.disable()` toàn Gateway** như bước chữa tất cả test 403.

## 18. Một bộ integration tests cần backend stub

Một lỗi phổ biến là test:

```java
client.get().uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
```

nhưng **không có upstream stub**, hoặc backend trả 200 cho mọi route. Như vậy bạn không biết path sau `StripPrefix`, outbound auth header hay URI thực sự được gửi.

### 18.1. Thiết kế stub

Một HTTP stub (MockWebServer/WireMock) nên ghi:

```text
method
path
request headers (trong bộ nhớ test, không in secret)
body (chỉ synthetic)
number of requests
response status/body được test kiểm soát
```

Nên có fixtures:

```text
GET /orders/42 → 200 {"id":"42"}
GET /orders/99 → 403 (backend denies object)
GET /orders/503 → 503
POST /orders → 201
```

### 18.2. Dynamic route URI theo random backend port

Khi backend stub chạy random port, đưa URI vào Spring test context bằng **dynamic properties**, không hard-code `localhost:9001`:

```java
// Pseudocode test setup:
// 1. Start backend HTTP stub trước khi Spring context bind properties.
// 2. Lấy backendBaseUrl = "http://127.0.0.1:<random-port>".
// 3. @DynamicPropertySource đăng ký URI của route orders tương ứng.
// 4. @SpringBootTest(RANDOM_PORT) khởi động Gateway.
// 5. WebTestClient.bindToServer() gọi Gateway local port.
// 6. Assert backend stub nhận request chính xác.
```

Property route dùng trong cấu hình mẫu có thể là:

```text
spring.cloud.gateway.server.webflux.routes[0].uri
```

Chỉ áp dụng đúng khi test profile thực sự có route ở index 0 và Spring Boot binder nhận override này. Với nhiều routes, có thể inject placeholder URI trong test YAML hoặc cấu hình `RouteLocator` test bean. Đừng đưa cú pháp property index vào production mà không hiểu route order/config merge.

### 18.3. Test auth failure không gọi backend

Ví dụ case:

```text
Given:
  Stub request count = 0

When:
  GET /api/orders/42, không bearer token

Then:
  Gateway responds 401
  Stub request count = 0
```

Tương tự, JWT hợp lệ nhưng thiếu `orders.read` → 403 và **không có outbound request**. Nếu backend vẫn bị gọi, security filter chain có thể sai matcher hoặc route bypass.

### 18.4. Test TokenRelay đúng chặng

Với BFF:

```text
Client → Gateway:
  Cookie: SESSION=<opaque>

Gateway → Backend:
  Authorization: Bearer <access token>
```

Test cả:

- Không forward `SESSION` cookie ngoài chủ đích.
- Không log access token trong wiretap/headers debug.
- Header được ghi đè đúng nếu client cố gửi một fake `Authorization`.
- Backend trả 401 khi access token audience/scope sai.
- Session expired/authorized client missing không được dùng token cũ từ request khác.

### 18.5. Test cơ chế retry không làm lộ hoặc nhân bản token

Retry có thể tạo nhiều outbound attempts. Nếu route TokenRelay được đặt trong filter chain có retry, cần biết request được re-execute ra sao và token nào được dùng trên mỗi attempt.

Với POST, phải có **idempotency key** và backend deduplication; test:

```text
One inbound POST
→ Gateway attempts 1..N theo policy
→ Backend xử lý nghiệp vụ đúng một lần
```

Không dùng Retry vô hạn hoặc phát hành token mới mỗi attempt mà không kiểm soát. Một số lỗi auth 401 không nên được retry như lỗi mạng 502.

## 19. Ma trận kiểm thử tổng hợp

| # | Nhóm | Dữ liệu thử | Assertion chính |
| --- | --- | --- | --- |
| 1 | Preflight | Origin cho phép, GET, Authorization | 2xx và ACAO/ACAM/ACAH đúng |
| 2 | Preflight | Origin bị cấm | Không có ACAO cho origin sai |
| 3 | Preflight | Method DELETE không được phép | Không cấp phép DELETE |
| 4 | Preflight | Header `X-Admin-Override` | Không cấp phép header không cho phép |
| 5 | Preflight | Route `Method=GET`, request OPTIONS | Global fallback/handler hoạt động |
| 6 | Preflight | OPTIONS có cookie giả | CORS không cần credential user để quyết định |
| 7 | Preflight | OPTIONS lặp | Cache headers `maxAge` theo policy |
| 8 | CORS actual | GET từ allowed origin | ACAO đúng origin |
| 9 | CORS actual | GET từ denied origin | Không phát ACAO sai |
| 10 | CORS actual | Backend 503 | Error path giữ policy phù hợp |
| 11 | CORS actual | Security 401 | Browser được phép đọc error response nếu origin hợp lệ |
| 12 | CORS | `allowCredentials=true` | Không có ACAO wildcard trái phép |
| 13 | CORS | Exposed `X-Trace-Id` | Browser được đọc header đúng |
| 14 | CORS | `Authorization` request header | AllowedHeaders đúng; không nhầm ExposedHeaders |
| 15 | JWT | Không bearer | 401, backend không nhận request |
| 16 | JWT | Malformed token | 401 |
| 17 | JWT | Sai signature/alg | 401 |
| 18 | JWT | Sai issuer | 401 |
| 19 | JWT | Sai audience | 401 nếu validator cấu hình bắt buộc |
| 20 | JWT | `exp` quá hạn | 401 |
| 21 | JWT | `nbf` tương lai | 401 |
| 22 | JWT | Đúng token, thiếu scope | 403, không gọi backend |
| 23 | JWT | Đúng scope | Backend nhận path/request phù hợp |
| 24 | JWT | Scope converter tùy chỉnh | `GrantedAuthority` đúng |
| 25 | Session | Login redirect/callback | State/nonce/PKCE và token exchange đúng |
| 26 | Session | Cookie sau login | Secure/HttpOnly/SameSite/Path đúng |
| 27 | Session | Cookie request kế tiếp | Authenticated principal khôi phục |
| 28 | Session | Cookie giả/hết hạn | Không được truy cập |
| 29 | Session | Logout | Session và quyền BFF bị thu hồi |
| 30 | Session | POST thiếu CSRF | Từ chối nếu session CSRF áp dụng |
| 31 | Session | POST CSRF hợp lệ | Qua tiếp authorization/business checks |
| 32 | Session | Pod A login → Pod B request | Session và authorized client không bị thất lạc |
| 33 | TokenRelay | OAuth2 authorized client hợp lệ | Backend nhận đúng access token |
| 34 | TokenRelay | Không authorized client | Không relay credential của user khác |
| 35 | TokenRelay | Sai registration ID | Không lấy token sai registration |
| 36 | TokenRelay | Token hết hạn | Refresh/error theo policy, không dùng stale token |
| 37 | TokenRelay | OIDC ID token và access token khác nhau | Relay access token, không relay ID token |
| 38 | TokenRelay | Client cố giả Authorization | Không override token relay trái policy |
| 39 | TokenRelay | Backend không tin audience | Backend 401 và error handling đúng |
| 40 | Privacy | Synthetic tokens trong request | Logs/traces không lưu tokens |
| 41 | Routing | CORS/JWT pass, `StripPrefix=1` | Backend nhận đúng path |
| 42 | Resilience | CircuitBreaker open | Không có outbound request, CORS/error đúng |
| 43 | Resilience | Retry sau 503 | Đếm attempts, idempotency được bảo vệ |
| 44 | Network | CORS qua ingress/TLS | Không có duplicate ACAO/proxy header bypass |

### 19.1. Ưu tiên theo rủi ro

Nếu đội ngũ chưa thể tự động hóa 44 ca, ưu tiên tối thiểu:

1. Preflight `OPTIONS` allowed origin/method/header **thành công**.
2. Preflight bị từ chối với **origin và method sai**.
3. Actual GET với CORS header trên **200, 401 và 403**.
4. JWT **thiếu, sai signature, sai issuer/audience, hết hạn, thiếu scope**.
5. Session **login, cookie, CSRF, logout**.
6. TokenRelay đúng access token đến **backend stub**, không rò cookie.
7. Multi-replica session/authorized-client state nếu production có nhiều pods.
8. Logs và traces không chứa bearer/cookie/client secrets.

Đây là bộ regression nền để phát hiện lỗi thường gây CORS failures hoặc security bypass.

## 20. Chẩn đoán lỗi theo triệu chứng

### 20.1. Browser báo CORS nhưng curl nhận 200

Nguyên nhân:

- Browser chờ OPTIONS preflight, curl đã gọi GET trực tiếp.
- Response GET thiếu ACAO hoặc không expose header cần đọc.
- Origin/port/scheme sai.
- Gateway/Security/ingress tạo CORS headers không đồng nhất.

**Cách xử lý:** tái hiện chính xác OPTIONS có `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` rồi actual GET có Origin. Xem Network tab browser để phân biệt request nào fail.

### 20.2. OPTIONS trả 401

Khả năng: Spring Security bắt preflight như request API cần bearer trước khi CORS xử lý. Cũng có thể request không được nhận dạng là preflight do thiếu headers.

**Cách xử lý:** xác minh CORS handler chạy trước authentication hoặc OPTIONS được qua security chain thích hợp; test route `Method=GET` không match OPTIONS. **Không** làm actual GET public chỉ để sửa OPTIONS.

### 20.3. OPTIONS trả 404 dù GET match

Khả năng: route có `Method=GET`, preflight HTTP method là OPTIONS, route metadata không áp dụng.

**Cách xử lý:** dùng global CORS `add-to-simple-url-handler-mapping: true` hoặc giải pháp CORS mapping tương ứng, test đúng route path.

### 20.4. Preflight 200 nhưng GET 401

Đây **có thể là hành vi đúng**: CORS cho browser gửi GET, còn JWT authentication kiểm tra token riêng.

Kiểm tra actual Authorization header, JWT decoder errors và audience/scope. Không hiểu preflight cho phép method là đã cho phép user dùng dữ liệu.

### 20.5. GET trả 403 dù JWT hợp lệ

Khả năng:

- JWT thiếu authority `SCOPE_orders.read`.
- `scope` claim được map sai.
- Backend kiểm tra object ownership/tenant.
- CSRF đang áp dụng trên một state-changing session request.

**Cách xử lý:** xác định 403 sinh ở **Gateway hay backend**, kiểm tra effective authorities bằng metadata an toàn (không in token) và security filters.

### 20.6. `mockJwt()` pass nhưng JWT thật bị 401

Điều này không mâu thuẫn. `mockJwt` bypass cryptographic decoding. Real decoder có thể từ chối:

```text
signature / kid / JWKS
iss / aud / exp / nbf
algorithm
issuer discovery/network
```

**Cách xử lý:** thêm JWT validation integration tests với ký số test key/JWKS.

### 20.7. OAuth2 Login test pass nhưng browser không giữ session

`mockOAuth2Login` không test cookie thực. Có thể có:

- Wrong Domain/Path/SameSite/Secure.
- Third-party cookie restrictions.
- Redirect host/proto sai do trusted proxy headers.
- Session store in-memory hoặc nhiều Gateway pods.

**Cách xử lý:** chạy browser E2E qua ingress HTTPS đúng topology, kiểm tra Set-Cookie/callback/state, không log session ID thật.

### 20.8. OAuth2 callback bị 403/invalid state

Khả năng:

- State/correlation cookie hoặc WebSession không được gửi lại.
- Session affinity/store không nhất quán.
- Wrong external redirect URI/scheme/host.
- State expired/replayed; PKCE hoặc OIDC nonce mismatch.

**Cách xử lý:** test real authorization code flow với test IdP và nhiều replicas nếu production dùng cluster. Không bỏ `state` validation để “cho login chạy”.

### 20.9. TokenRelay filter không được tạo

Khả năng: thiếu OAuth2 Client dependency, registration config không tạo `ReactiveClientRegistrationRepository`, sai Gateway edition/namespace, hoặc filter name không được nhận dạng.

**Cách xử lý:** kiểm tra bean/route runtime, dependencies và docs đúng version. Không tự tạo `Authorization` hard-code trong route YAML.

### 20.10. Gateway authenticated nhưng backend trả 401

Khả năng:

- Authorized client không có access token.
- Gateway không áp TokenRelay trên route được chọn.
- Backend nhận token sai audience, issuer hoặc hết hạn.
- TokenRelay lấy token của registration khác.
- Request chỉ có session cookie nhưng không có OAuth2 authorized client.

**Cách xử lý:** backend stub xác minh **header presence và test token identity**, kiểm tra backend JWT validation riêng. Không copy session cookie hoặc ID token làm bearer.

### 20.11. TokenRelay test pass trên một pod, fail trên pod khác

Khả năng: in-memory `ReactiveOAuth2AuthorizedClientService` hoặc `WebSession` state không chia sẻ.

**Cách xử lý:** kiểm thử multi-pod session/authorized-client persistence và connection to store; thiết kế fail policy khi store lỗi, kiểm soát refresh token secrets.

### 20.12. CORS 200 nhưng browser báo credential error

Khả năng:

- `Access-Control-Allow-Origin: *` khi `credentials: include`.
- Thiếu `Access-Control-Allow-Credentials: true`.
- Browser không gửi cookie do SameSite/Secure/third-party policy.
- Multiple ACAO headers từ nhiều tầng.

**Cách xử lý:** kiểm tra actual headers và browser cookie policy; đừng chỉ xem status 200 hoặc đọc cookie trong `WebTestClient`.

## 21. Bảo vệ dữ liệu kiểm thử và quan sát

Các test CORS/JWT/session/TokenRelay rất dễ tạo **logs có bí mật** nếu in request/response headers nguyên bản.

### 21.1. Những dữ liệu không được log

```text
Authorization: Bearer ...
Cookie: SESSION=...
Set-Cookie: SESSION=...
Refresh token
ID token / Access token raw
OAuth2 authorization code
Client secret
?code=...&state=...&access_token=...
```

Ngay cả khi dùng backend stub, tránh in toàn bộ recorded request khi assertion thất bại. Chỉ log:

```text
routeId=orders-bff
authenticated=true
relayTokenPresent=true
relayTokenMatchedTestFixture=true
status=200
traceId=<synthetic-trace-id>
```

### 21.2. Test với synthetic markers

Dùng:

```text
FAKE_ACCESS_TOKEN_FOR_STUB
FAKE_SESSION_ID
FAKE_REFRESH_TOKEN
FAKE_CLIENT_SECRET
```

Sau test, có thể kiểm tra **test-specific log sink** không xuất hiện những markers trong structured operational logs. Nhưng không suy từ một logger sạch rằng Netty wiretap, ingress, APM hoặc CI system đã sạch; kiểm soát tất cả collectors theo phạm vi triển khai.

### 21.3. Không bật wiretap DEBUG trên traffic thật

`httpclient/httpserver.wiretap` có thể ghi HTTP payload trước/sau biến đổi, cả token và cookie. Nếu cần debug, dùng synthetic traffic trong namespace cô lập và tắt sau khi thu đủ bằng chứng. TLS bảo vệ đường truyền, **không bảo vệ bản ghi raw trong application logs**.

### 21.4. Tránh test flaky vì thời gian và môi trường

- Dùng random ports và test backend stub độc lập.
- Đặt deadline/timeout hữu hạn, tránh `Thread.sleep()` cố định.
- Dùng deterministic JWT time/test clock hoặc giới hạn clock skew có chủ đích.
- Mỗi test có riêng session/authorized client, không chia state giữa test methods.
- Không phụ thuộc DNS/IdP bên ngoài khi đang chạy CI unit/integration.
- Không lưu session cookie/token vào shared static fixture có thể rò giữa tests.
- Không giả định test execution order khi dùng cùng một backend stub queue.

## 22. Quy trình thực hành đề xuất

### Bài tập 1 — Kiểm thử preflight với route `Method=GET`

1. Khai báo route `Path=/api/orders/**`, `Method=GET`.
2. Bật global CORS có exact origin và `add-to-simple-url-handler-mapping: true`.
3. Gửi OPTIONS từ allowed origin với requested method GET, header authorization.
4. Assert CORS headers, không có backend call.
5. Gửi requested method DELETE, assert không được cấp phép.
6. Tắt `add-to-simple-url-handler-mapping` trên test profile và quan sát behavior; giải thích **vì sao `Method=GET` không match OPTIONS**.

### Bài tập 2 — Phân quyền JWT

1. Dùng `mockJwt` tạo `SCOPE_orders.read`, test GET thành công.
2. Dùng `mockJwt` tạo `SCOPE_profile.read`, test GET bị 403.
3. Không mock authentication, test GET bị 401.
4. Tạo JWT thật ký bằng test key, test issuer/audience/expiry đúng.
5. Tạo JWT sai `aud`/signature, test 401.
6. So sánh kết luận của mock test với validation test.

### Bài tập 3 — Session và CSRF

1. Dùng `mockOAuth2Login` kiểm tra security rule `/bff/**`.
2. Test POST thiếu `csrf()` bị từ chối theo session profile.
3. Test POST có `csrf()` được đánh giá tiếp.
4. Chạy test IdP OAuth2 flow thật, kiểm tra `state`, cookie, logout.
5. Gọi lại với cookie hết hạn và qua pod thứ hai.

### Bài tập 4 — TokenRelay

1. Khai báo route `/bff/orders/**` có `TokenRelay`.
2. Chuẩn bị authorized client `portal` với access token giả.
3. Backend stub kiểm tra bearer header và path.
4. Thử principal thiếu authorized client, sai `clientRegistrationId`, token hết hạn.
5. Thử OIDC login fixture có ID token khác access token, xác nhận chỉ access token đi downstream.
6. Kiểm tra kết quả với backend Resource Server thật sử dụng JWT test issuer.

### Bài tập 5 — Browser cross-origin end-to-end

1. Khởi động SPA test ở `https://app.example.test`.
2. Chạy API Gateway test ở `https://api.example.test`.
3. Thử `fetch` với Authorization header và preflight.
4. Thử session cookie với `credentials: 'include'` theo SameSite policy.
5. Thử origin không được phép và xem browser console/Network.
6. Test response lỗi 401/403/503 vẫn có CORS policy phù hợp.

## 23. Câu hỏi tự luyện có đáp án

1. **CORS preflight có cần bearer JWT giống actual GET không?**  
   Không nên thiết kế preflight phụ thuộc credential của actual request. CORS processing cần hoạt động trước auth gate theo policy.

2. **`Access-Control-Request-Method: GET` có làm HTTP method của OPTIONS trở thành GET không?**  
   Không. Method thực vẫn là OPTIONS; route `Method=GET` không match OPTIONS.

3. **GET trả 200 trong curl nhưng browser báo CORS có mâu thuẫn không?**  
   Không. Browser còn thực thi preflight và kiểm tra CORS response headers.

4. **`allowCredentials: true` có làm cookie tự được tạo không?**  
   Không. Nó chỉ tham gia CORS policy; cookie/session/browser policy là lớp khác.

5. **Có thể dùng `allowedOrigins: '*'` với credentialed browser requests không?**  
   Không theo credentialed CORS policy hợp lệ; phải trả origin cụ thể được phép.

6. **`mockJwt()` có xác minh RSA signature không?**  
   Không. Nó thiết lập authentication giả phục vụ kiểm thử authorization.

7. **JWT đúng chữ ký nhưng sai `aud` có nên được chấp nhận không?**  
   Không nếu API yêu cầu audience đó; phải cấu hình audience validator và test âm tính.

8. **JWT thiếu scope trả 401 hay 403?**  
   Thường 403 khi authentication thành công nhưng authorization không đủ.

9. **`mockOAuth2Login()` có chứng minh cookie `Secure` và session Redis hoạt động không?**  
   Không. Cần real HTTP/browser và distributed integration test.

10. **Session ID cookie có phải OAuth2 access token không?**  
    Không. Session ID tham chiếu state, còn access token dùng cho resource API theo audience/scope.

11. **`TokenRelay` có nên gửi ID token xuống Order Service không?**  
    Không. Resource server cần access token theo contract.

12. **Backend trả 401 dù Gateway đã login nghĩa là lỗi CORS không?**  
    Không nhất thiết. Có thể thiếu relay, sai audience hoặc backend không trust access token.

13. **Nếu `TokenRelay` hoạt động ở pod A nhưng fail ở pod B, nên kiểm tra gì?**  
    WebSession và ReactiveOAuth2AuthorizedClientService persistence, routing/session affinity nếu có.

14. **Vì sao phải test CORS trên 401/403?**  
    Browser cần CORS headers phù hợp để frontend đọc response lỗi; request có thể bị chặn trước route chain.

15. **`Access-Control-Allow-Headers` với `Authorization` giúp JS đọc `X-Trace-Id` không?**  
    Không. Đọc response header cần `Access-Control-Expose-Headers`.

16. **CSRF có được thay bằng CORS không?**  
    Không. CSRF bảo vệ thao tác khi browser tự gửi credentials; CORS kiểm soát JS đọc cross-origin response.

17. **`mockOAuth2Client()` có chứng minh TokenRelay chọn đúng registration không?**  
    Chưa. Phải assert outbound Authorization ở backend stub và authorized-client lookup đúng.

18. **Vì sao không log JWT khi test fail?**  
    JWT/refresh token/session ID có thể là credential. Dùng synthetic tokens và assertions không in raw values.

19. **Một preflight 200 có chứng minh backend đã nhận GET chưa?**  
    Không. Preflight là request riêng; actual GET vẫn phải được gửi và đi qua auth/routing.

20. **Có nên bật `permitAll` cho mọi OPTIONS không?**  
    Không mặc định. Phải có CORS policy và security scope rõ, xử lý preflight ở đúng lớp.

## 24. Checklist trước khi đưa vào CI/CD

- [ ] Đang dùng đúng **Spring Cloud Gateway Server WebFlux**, không nhầm Web MVC/Servlet?
- [ ] Namespace `spring.cloud.gateway.server.webflux.*` hoặc legacy đã xác minh theo version?
- [ ] Tách test **resource-server JWT** và **OAuth2 Login/session BFF** thành profiles hoặc chains rõ?
- [ ] Có CORS owner rõ ràng, không phát trùng ACAO từ Gateway/Security/ingress/backend?
- [ ] Preflight OPTIONS allowed origin/method/headers hoạt động và không cần JWT?
- [ ] Test `Method=GET` predicate không match OPTIONS; global fallback đúng?
- [ ] Test actual request từ allowed/denied origins, kể cả 401/403/503?
- [ ] Với credentialed CORS, ACAO là exact allowed origin, không phải `*`?
- [ ] `allowedHeaders` và `exposedHeaders` được test đúng hướng?
- [ ] Test CORS response caching, `Vary`, browser cookie restrictions?
- [ ] JWT có tests thiếu token, signature, issuer, audience, expiry, nbf, algorithms?
- [ ] Test scope converter/authority mapping, phân biệt 401 và 403?
- [ ] `mockJwt` tests không được ghi nhãn là crypto validation tests?
- [ ] Session tests có cookie flags, login, CSRF, logout, expiry và fixation?
- [ ] Có test auth-code callback/state/PKCE/nonce nếu dùng OAuth2/OIDC Login?
- [ ] WebSession và OAuth2 authorized client được thử trên nhiều replicas nếu có cluster?
- [ ] TokenRelay route được match đúng và backend stub nhận đúng access token?
- [ ] Không forward ID token/session cookie hoặc credential user khác ngoài policy?
- [ ] Missing/expired authorized client được xử lý an toàn, không silent fallback?
- [ ] Backend vẫn kiểm tra JWT audience, scopes và object/tenant ownership?
- [ ] Synthetic tokens/test keys; không lưu client secrets hoặc JWT production trong CI?
- [ ] Không in raw `Authorization`, `Cookie`, `Set-Cookie`, OAuth2 code hoặc refresh token ra logs?
- [ ] Backend stub ghi đúng path/method/headers/count mà không expose secrets?
- [ ] Test chạy deterministic, random ports, hữu hạn timeout và tách state từng test?
- [ ] Có browser E2E qua TLS/ingress cho CORS/cookie redirects khi cần?
- [ ] Có ma trận regression cho Retry/CircuitBreaker/security errors và CORS headers?

## 25. Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Server WebFlux — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/cors-configuration.html): CORS global/route metadata và `add-to-simple-url-handler-mapping`.
- [Spring Cloud Gateway Server WebFlux — TokenRelay GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html): OAuth2 access token relay, `clientRegistrationId`, authorized-client store.
- [Spring Cloud Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): namespace và thuộc tính theo Gateway release train.
- [Spring Security WebFlux — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt`, `mockOAuth2Login`, `mockOidcLogin`, `mockOAuth2Client`.
- [Spring Security WebFlux — Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `WebTestClient.mutateWith(csrf())`.
- [Spring Security WebFlux — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): JWT decoder, issuer, signature, scopes/authorities và validation.
- [Spring Security — CORS Integration](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): CORS cần được xử lý trước Spring Security.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): mock-context và server-bound tests.

## Tổng kết

Kiểm thử **CORS, preflight, JWT, session và TokenRelay** phải phản ánh đúng những ranh giới khác nhau trong **Spring Cloud Gateway Server WebFlux**. **Preflight OPTIONS** kiểm tra quyền truy cập cross-origin của browser, **không phải JWT authentication**; `Method=GET` route predicate không match OPTIONS dù `Access-Control-Request-Method: GET`. **JWT tests** phải tách kiểm tra authorization bằng `mockJwt()` với kiểm tra chữ ký/issuer/audience/expiry bằng token thật và test JWKS. **Session/OAuth2 Login tests** phải tách mock principal với real browser cookie, callback, CSRF, logout và persistence nhiều Gateway replicas. **`TokenRelay` tests** phải dùng upstream stub để chứng minh Gateway thực sự gửi **đúng OAuth2 access token**, không nhầm ID token hay session cookie.

Một suite có giá trị không chỉ assert `200 OK`: nó kiểm tra **OPTIONS và actual response headers**, **401/403 đúng nguồn**, **không có upstream call khi bị chặn**, **đúng path và Authorization header tới backend**, **session lifecycle**, và **không rò credentials trong test logs**. Kết hợp test theo tầng, dữ liệu giả, browser E2E có chọn lọc và ma trận negative cases sẽ giúp Gateway định tuyến, xác thực, giới hạn quyền và chuyển token cho microservices an toàn, có thể kiểm chứng trong CI/CD.
