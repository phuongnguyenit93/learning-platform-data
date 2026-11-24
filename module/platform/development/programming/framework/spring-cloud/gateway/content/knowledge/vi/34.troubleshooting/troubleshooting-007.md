# Preflight thất bại hoặc header CORS xuất hiện nhiều lần

## 1. Khi trình duyệt báo lỗi CORS, Gateway cần được kiểm tra ở đâu?

**SPRING_CLOUD_GATEWAY** đứng giữa frontend và các microservices: nhận request, chọn route bằng predicate, chạy filter chain, biến đổi path/header, xác thực, giới hạn lưu lượng, áp dụng circuit breaker/retry, thiết lập TLS và proxy tới backend. Khi frontend chạy ở một origin khác Gateway, trình duyệt áp dụng **Cross-Origin Resource Sharing (CORS)**. Một cấu hình sai có thể khiến API vẫn hoạt động với `curl` hoặc Postman nhưng JavaScript trên trình duyệt không đọc được response.

Hai triệu chứng thường gặp trong vận hành là:

- **Preflight thất bại:** trình duyệt gửi `OPTIONS` trước request thật, nhưng nhận 401/403/404/405 hoặc response thiếu CORS headers.
- **CORS response headers bị lặp:** response có hai hoặc nhiều `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`, hoặc giá trị không thống nhất giữa Gateway, backend, Spring Security và reverse proxy.

```mermaid
sequenceDiagram
    participant B as Browser
    participant G as Spring Cloud Gateway
    participant S as Spring Security
    participant U as Upstream service
    B->>G: OPTIONS /api/orders<br/>Origin + Access-Control-Request-Method
    G->>S: WebFlux Security chain
    alt Security chặn trước CORS
        S-->>B: 401/403, thiếu CORS headers
    else CORS được xử lý đúng
        S->>G: Cho preflight đi tiếp
        G-->>B: 200/204 + Access-Control-Allow-*
        B->>G: POST /api/orders + Origin
        G->>U: Proxy request
        U-->>G: 201 + CORS headers (có thể bị lặp)
        G-->>B: 201 + response headers
    end
```

**Điểm quan trọng:** CORS là cơ chế mà **trình duyệt** dùng để quyết định JavaScript có được phép đọc cross-origin response hay không. CORS không thay authentication, authorization, CSRF protection hoặc rate limiting. Một request vẫn có thể tới backend và gây side effect dù browser sau đó báo lỗi CORS vì không đọc được response.

### Mục tiêu bài học

Sau bài này, bạn có thể:

1. Phân biệt preflight request `OPTIONS` với actual request `GET/POST/PUT/DELETE`.
2. Đọc ba headers chính của preflight: `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
3. Sửa trường hợp route có `Method=GET,POST` khiến `OPTIONS` không match bằng global CORS và `add-to-simple-url-handler-mapping`.
4. Xác định Spring Security có từ chối preflight trước khi CORS handler của Gateway xử lý hay không.
5. Cấu hình allowlist origin/method/header/credentials đúng nguyên tắc.
6. Tìm nguồn tạo response CORS headers trùng và chọn một lớp chịu trách nhiệm phát header.
7. Dùng `DedupeResponseHeader` đúng phạm vi khi cần loại giá trị trùng, không dùng nó để che hai chính sách CORS mâu thuẫn.
8. Dùng `curl`, browser DevTools, Gateway logs, backend logs và `WebTestClient` để khoanh vùng.
9. Viết test cho preflight hợp lệ/bị từ chối, actual response và trường hợp header bị lặp.
10. Thiết kế CORS an toàn khi có cookies/credentials, nhiều Gateway replicas, ingress và backend tự cấu hình CORS.

> **Phạm vi phiên bản:** Ví dụ hướng tới **Spring Cloud Gateway Server WebFlux 4.3.x**, **Spring Cloud 2025.0.x**, **Spring Boot 3.5.x**, **Spring Framework 6.2.x** và Java 17+. Bài sử dụng namespace cấu hình dành cho Gateway Server WebFlux. Gateway Server Web MVC dùng Servlet stack và cách tích hợp Security khác; không chép nguyên các cấu hình reactive sang MVC. Hãy đối chiếu configuration metadata của đúng patch version trước khi rollout.

## 2. CORS và preflight hoạt động thế nào?

### 2.1. Origin được xác định bởi scheme, host và port

Một origin gồm ba thành phần:

```text
origin = scheme + host + port
```

Ví dụ:

| URL | Origin |
| --- | --- |
| `https://app.example.com` | `https://app.example.com` |
| `http://app.example.com` | `http://app.example.com` |
| `https://app.example.com:8443` | `https://app.example.com:8443` |
| `https://admin.example.com` | `https://admin.example.com` |

Bốn giá trị trên không cùng origin. Chuyển HTTP sang HTTPS, đổi subdomain hoặc đổi port đều tạo origin khác. Origin **không có path**; cấu hình `https://app.example.com/dashboard` là sai định dạng origin vì đã kèm path.

Một số môi trường phát triển dùng `http://localhost:5173`, còn frontend production chạy `https://app.example.com`. Hãy khai báo đúng từng origin cần thiết; đừng cho rằng `localhost`, domain production và domain preview là một origin.

### 2.2. Khi nào browser gửi preflight?

Trình duyệt thường gửi preflight khi request cross-origin không thuộc nhóm **CORS-safelisted requests**. Ví dụ:

- Dùng method `PUT`, `PATCH`, `DELETE`.
- Dùng `Content-Type: application/json` (không thuộc các MIME types safelisted).
- Gửi header `Authorization`, `X-Request-Id` hoặc custom headers khác.
- Một số request có header/content-type không nằm trong danh sách được phép gửi mà không preflight.

Không phải mọi cross-origin request đều có preflight. Một số **simple requests** có thể gửi thẳng actual request, nhưng response thực tế vẫn phải có CORS headers hợp lệ để JavaScript được đọc nội dung.

Preflight là một HTTP request riêng:

```http
OPTIONS /api/orders/42 HTTP/1.1
Host: gateway.example.com
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization,content-type,x-request-id
```

Nó có ba thông tin cần đọc:

| Header | Ý nghĩa |
| --- | --- |
| `Origin` | Origin của trang JavaScript đang chạy. |
| `Access-Control-Request-Method` | Method mà browser muốn gửi ở **actual request** (ví dụ `PATCH`). |
| `Access-Control-Request-Headers` | Những request headers mà actual request muốn sử dụng. |

Gateway/CORS handler phải trả response cho phép origin, method và headers phù hợp. Ví dụ:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PATCH
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-Id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
```

Status thành công có thể là 200 hoặc 204 tùy handler; điều cần xác minh là **CORS headers hợp lệ** và request được xử lý đúng. Browser chỉ gửi actual request sau khi preflight được chấp nhận.

### 2.3. Preflight không phải request nghiệp vụ

Preflight thường **không gửi cookies hoặc bearer token của actual request**. Đừng yêu cầu nó phải xác thực như một request `PATCH /api/orders/42` rồi trả 401 chỉ vì không có session cookie. Thay vào đó:

- CORS layer xác minh `Origin`, requested method và requested headers.
- Security policy cho phép preflight được xử lý.
- Actual request vẫn phải xác thực JWT/session và kiểm tra quyền đầy đủ.
- Backend không được coi một preflight thành công là bằng chứng người dùng đã đăng nhập.

Cho phép `OPTIONS` qua CORS/security **không mở quyền gọi API thật**. Nó chỉ cho phép browser kiểm tra trước rằng request dự kiến có thể được gửi.

### 2.4. CORS không phải firewall

Một request bằng `curl` không bị browser áp dụng CORS. Nếu server thiếu `Access-Control-Allow-Origin`, `curl` vẫn có thể gửi request và đọc response. Vì vậy:

- `curl` thành công không chứng minh CORS đúng.
- Browser báo CORS không chứng minh backend chưa xử lý request.
- Không dùng CORS để thay authentication, authorization hoặc CSRF.
- Không dùng `Access-Control-Allow-Origin: *` như cách chữa mọi lỗi; cấu hình origin phải phù hợp với dữ liệu và credentials.

## 3. Nguyên nhân số 1: `OPTIONS` không match route predicate

### 3.1. Route chỉ nhận GET/POST nhưng preflight dùng OPTIONS

Một route phổ biến:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders_api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST,PATCH
              filters:
                - StripPrefix=1
```

Actual request `PATCH /api/orders/42` có thể match route. Nhưng browser preflight gửi:

```http
OPTIONS /api/orders/42
Origin: https://app.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization,content-type
```

`Method=GET,POST,PATCH` **không match OPTIONS**. Nếu Gateway chỉ áp CORS khi request đã match route, preflight có thể rơi vào route miss/404 và browser báo CORS error. Đây là lý do một API hoạt động với Postman nhưng hỏng khi gọi từ frontend.

**Không cần thêm OPTIONS vào predicate của mọi business route một cách máy móc.** CORS preflight không phải actual business operation; Gateway có cơ chế global CORS cho URL handler xử lý các request không match route predicate.

### 3.2. Dùng global CORS và `add-to-simple-url-handler-mapping`

Với Gateway Server WebFlux 4.3, configuration metadata có các thuộc tính:

- `spring.cloud.gateway.server.webflux.globalcors.cors-configurations`
- `spring.cloud.gateway.server.webflux.globalcors.add-to-simple-url-handler-mapping`

Ví dụ cấu hình global CORS cho API:

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
                  - https://app.example.com
                  - https://admin.example.com
                allowedMethods:
                  - GET
                  - POST
                  - PATCH
                  - DELETE
                allowedHeaders:
                  - Authorization
                  - Content-Type
                  - X-Request-Id
                exposedHeaders:
                  - X-Request-Id
                allowCredentials: true
                maxAge: 3600
```

`add-to-simple-url-handler-mapping: true` hữu ích khi CORS preflight **không được xử lý bởi route predicate**, ví dụ route chỉ match `GET` nhưng preflight dùng `OPTIONS`. Gateway thêm global CORS configuration vào simple URL handler mapping để xử lý CORS requests không được một route predicate nhận.

**Phân biệt hai trường hợp:**

- Nếu route chỉ có `Path=/api/**` và không lọc method, `OPTIONS` có thể match route; route/global CORS cần được kiểm tra theo cấu hình đang dùng.
- Nếu route có `Method=GET,POST` hoặc predicate khác loại preflight, bật simple URL handler mapping là một cách hỗ trợ preflight không match route.

### 3.3. Cẩn thận với prefix cấu hình giữa các starter

Tài liệu CORS của Gateway 4.3 minh họa global CORS bằng prefix tương thích `spring.cloud.gateway.globalcors`; configuration properties 4.3.5 cũng liệt kê các thuộc tính WebFlux riêng dưới `spring.cloud.gateway.server.webflux.globalcors`. Bài này dùng **starter Gateway Server WebFlux** và prefix `server.webflux` trong ví dụ.

Không khai báo cả hai prefix cùng lúc chỉ để “thử xem cái nào chạy”. Hãy xác nhận:

1. Project đang dùng `spring-cloud-starter-gateway-server-webflux` hay starter Gateway cũ.
2. Configuration metadata/IDE completion của đúng Gateway patch version.
3. Cấu hình active sau khi bind (nếu có actuator config properties, chỉ expose trên management interface được bảo vệ).
4. HTTP preflight thực tế trả đúng CORS headers.

Nếu cấu hình đang dùng legacy starter và tài liệu của release train chỉ định `spring.cloud.gateway.globalcors`, dùng prefix legacy đó nhất quán. **Không suy ra prefix từ một snippet trên Internet mà bỏ qua dependency đang chạy.**

### 3.4. Route-level CORS metadata

Có thể khai báo CORS ngay trên route bằng metadata:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders_api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST,PATCH
              metadata:
                cors:
                  allowedOrigins:
                    - https://app.example.com
                  allowedMethods:
                    - GET
                    - POST
                    - PATCH
                  allowedHeaders:
                    - Authorization
                    - Content-Type
                    - X-Request-Id
                  allowCredentials: true
                  maxAge: 3600
```

Route metadata phù hợp khi mỗi route có policy riêng. Nhưng nếu preflight không match route vì `Method`, **không giả định metadata của route tự giải quyết được route miss**. Khi đó global CORS + `add-to-simple-url-handler-mapping` thường phù hợp hơn. Hãy test cả preflight và actual request qua route thật.

## 4. Nguyên nhân số 2: Spring Security từ chối preflight trước CORS

### 4.1. Vì sao browser nhận 401/403 dù API thật có JWT?

Spring Security WebFlux chạy trong **WebFilter chain**, trước khi request tới handler mapping của Gateway. Trong khi đó, global CORS của Gateway được áp dụng tại tầng handler mapping. Nếu Security yêu cầu mọi request phải authenticated, preflight `OPTIONS` không có cookie/session của actual request có thể bị chặn **trước khi Gateway CORS handler nhìn thấy nó**.

Luồng lỗi:

```text
Browser OPTIONS
    |
    v
Spring Security WebFilter
    |
    +--> anyExchange().authenticated()
             |
             +--> không có session cookie / bearer token
                       |
                       +--> 401/403
                                |
                                +--> Gateway global CORS chưa xử lý
```

Đây là nguyên nhân phổ biến khi:

- Gateway có global CORS nhưng frontend vẫn báo CORS.
- Request `OPTIONS` trả 401/403, trong khi gọi GET bằng Postman có token lại thành công.
- Backend không có request tương ứng vì preflight đã bị chặn trước route.
- Thử thêm `OPTIONS` vào `Method` predicate không giải quyết được 401 từ Security.

### 4.2. Tích hợp CORS vào Spring Security reactive chain

Khi ứng dụng có Spring Security, hãy để CORS được xử lý **trước bước authentication/authorization** bằng tích hợp CORS reactive của Security. Ví dụ dưới đây dùng một nguồn cấu hình CORS duy nhất cho Security:

```java
package com.example.gateway;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(List.of(
                "https://app.example.com",
                "https://admin.example.com"));

        // Methods của actual request mà browser xin phép.
        cors.setAllowedMethods(List.of(
                "GET", "POST", "PATCH", "DELETE"));

        cors.setAllowedHeaders(List.of(
                "Authorization",
                "Content-Type",
                "X-Request-Id"));

        cors.setExposedHeaders(List.of("X-Request-Id"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(3600L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .cors(Customizer.withDefaults())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                HttpMethod.OPTIONS, "/api/**")
                        .permitAll()
                        .anyExchange()
                        .authenticated())
                .build();
    }
}
```

**Import quan trọng:** `UrlBasedCorsConfigurationSource` trong ví dụ là class reactive:

```java
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
```

Không import nhầm class Servlet `org.springframework.web.cors.UrlBasedCorsConfigurationSource` vào Gateway Server WebFlux.

Giải thích:

- `.cors(Customizer.withDefaults())` bật CORS integration của Spring Security và dùng `CorsConfigurationSource` reactive đã khai báo.
- `OPTIONS /api/**` được phép qua authorization rules. CORS processor vẫn kiểm tra origin/method/header; `permitAll` không có nghĩa cho phép mọi origin.
- Actual request vẫn phải authenticated nhờ `.anyExchange().authenticated()`.
- `allowedMethods` là các method browser muốn gửi thực sự; ví dụ preflight `OPTIONS` có `Access-Control-Request-Method: PATCH`, nên policy cần cho phép `PATCH`.
- `allowCredentials(true)` chỉ bật việc browser có thể dùng credentials theo CORS; nó **không xác thực** người dùng.

### 4.3. Chọn một nơi làm chủ CORS

Một ứng dụng có thể có nhiều CORS mechanisms:

- Spring Security reactive CORS integration.
- Spring Cloud Gateway global CORS.
- `CorsWebFilter` tự khai báo.
- CORS ở ingress/reverse proxy.
- CORS tại backend hoặc controller `@CrossOrigin`.

Nếu nhiều lớp đều tự thêm `Access-Control-Allow-Origin`, header có thể bị lặp. Hãy quyết định **một lớp authoritative** cho public API:

| Kiến trúc | Hướng xử lý |
| --- | --- |
| Gateway không dùng Spring Security | Có thể dùng Gateway global CORS, bật simple URL handler mapping khi cần. |
| Gateway có Spring Security | Ưu tiên Security CORS integration để preflight được xử lý trước authorization. |
| Ingress đã là CORS owner | Đảm bảo Gateway/backend không tự thêm cùng headers; test cả response qua ingress. |
| Backend tự quản CORS | Gateway không nên thêm policy khác nếu không có lý do rõ; kiểm tra duplicate/conflicting headers. |
| Cần CORS policy khác nhau theo route | Thiết kế policy có chủ đích, test cách kết hợp global và route-level metadata. |

**Không bật đồng thời** Security CORS, một `CorsWebFilter` độc lập và Gateway global CORS với ba danh sách origin khác nhau rồi hy vọng browser tự chọn đúng. Nếu cần phối hợp, cấu hình phải nhất quán và kiểm tra response cuối cùng trên HTTP thật.

### 4.4. `OPTIONS permitAll` không thay thế CORS validation

Cấu hình:

```java
.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()
```

có thể cho phép mọi OPTIONS qua authorization nhưng **không tự sinh CORS headers**. Nếu thiếu CORS processor hoặc origin không hợp lệ, browser vẫn từ chối. Cũng không nên cho phép mọi method/endpoint mà không hiểu phạm vi: chỉ cho phép preflight trên API path cần hỗ trợ.

Đừng sửa thành `.anyExchange().permitAll()` chỉ để browser hết báo lỗi. Hãy xác minh response của preflight và actual request riêng biệt.

## 5. Nguyên nhân số 3: origin, method, header hoặc credentials không khớp

### 5.1. Origin phải khớp chính xác

Các cấu hình sau thường bị sai:

| Cấu hình | Lỗi |
| --- | --- |
| `allowedOrigins: https://app.example.com/` | Origin không có trailing slash. |
| `allowedOrigins: http://app.example.com` | Frontend thực tế dùng HTTPS. |
| `allowedOrigins: https://app.example.com:3000` | Port khác origin browser gửi. |
| `allowedOrigins: https://*.example.com` | `allowedOrigins` không phải wildcard pattern tùy ý. |
| `allowedOrigins: "*"` cùng `allowCredentials: true` | Wildcard origin không được phép với credentialed CORS. |
| Chỉ allow `https://app.example.com` | Frontend preview chạy ở `https://preview.example.com` chưa được cấp phép. |

Nếu thật sự cần pattern, Spring Framework có `allowedOriginPatterns`; khi match pattern, response có thể phản chiếu origin cụ thể thay vì trả ký tự wildcard. Ưu tiên **danh sách origin hữu hạn** nếu có thể, đặc biệt khi cho phép credentials.

### 5.2. Method của actual request phải được cho phép

Ví dụ browser gửi:

```http
Access-Control-Request-Method: PATCH
```

Nếu CORS policy chỉ có `GET,POST`, preflight sẽ bị từ chối dù route Gateway đã có `Method=PATCH`. Có hai lớp method riêng:

1. **Gateway route predicate:** route có chấp nhận actual HTTP method không?
2. **CORS allowedMethods:** browser có được phép gửi actual method cross-origin không?

Cả hai phải phù hợp. Cho phép CORS `PATCH` không tự tạo route PATCH; ngược lại route PATCH match cũng không tự cho phép origin cross-origin.

### 5.3. Header yêu cầu phải nằm trong allowlist

Một request có:

```http
Access-Control-Request-Headers: authorization,content-type,x-request-id
```

cần CORS policy cho phép các header đó. Header names không phân biệt hoa/thường theo HTTP, nhưng khi debug cần đối chiếu **đúng tên**:

| Header browser xin gửi | Cấu hình cần kiểm tra |
| --- | --- |
| `authorization` | `allowedHeaders: Authorization` |
| `content-type` | `allowedHeaders: Content-Type` |
| `x-request-id` | `allowedHeaders: X-Request-Id` |
| `x-tenant-id` | Chỉ cho phép nếu API contract thực sự cần và nguồn identity được xác minh. |

Không thêm `allowedHeaders: "*"` chỉ để xóa lỗi mà chưa đánh giá rủi ro. Header như `X-Internal-User`, `X-Admin` hoặc `X-Forwarded-For` có thể có ý nghĩa bảo mật ở backend; việc cho browser gửi chúng không khiến chúng trở nên đáng tin.

### 5.4. Credentials và wildcard origin

Nếu frontend dùng cookies hoặc credentialed fetch:

```javascript
fetch("https://gateway.example.com/api/profile", {
  method: "GET",
  credentials: "include"
});
```

server cần phản hồi với:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
```

**Không được** dùng:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Với `allowCredentials: true`, dùng exact `allowedOrigins` hoặc pattern được thiết kế kỹ. Ngoài CORS, cookie còn phụ thuộc `SameSite`, `Secure`, domain/path và chính sách third-party cookie của browser. CORS đúng không bảo đảm browser sẽ gửi cookie nếu cookie attributes không phù hợp.

### 5.5. `Access-Control-Expose-Headers` khác `Access-Control-Allow-Headers`

Hai cấu hình thường bị nhầm:

- `allowedHeaders`: browser **được gửi** headers nào trong request.
- `exposedHeaders`: JavaScript **được đọc** headers nào trong response ngoài các safelisted response headers.

Ví dụ nếu frontend cần đọc `X-Request-Id` từ response, cấu hình:

```yaml
exposedHeaders:
  - X-Request-Id
```

Thêm `X-Request-Id` vào `allowedHeaders` không thay cho `exposedHeaders` nếu vấn đề là JavaScript không đọc được response header.

### 5.6. Preflight cache có thể giữ policy cũ

`Access-Control-Max-Age` cho browser biết thời gian cache kết quả preflight. Sau khi đổi origin/method/header policy, browser có thể tiếp tục dùng preflight result đã cache cho đến khi hết hạn hoặc cache được xóa.

Khi debug:

- Dùng cửa sổ ẩn danh hoặc xóa browser cache để loại trừ kết quả cũ.
- Kiểm tra response `Access-Control-Max-Age`.
- Không đặt max-age quá dài nếu policy thay đổi thường xuyên.
- Không kết luận config mới chưa được áp dụng chỉ từ một browser session còn cache.

### 5.7. `Vary: Origin` và reverse proxy cache

Khi server trả `Access-Control-Allow-Origin` dựa trên request origin, response có thể khác nhau giữa các origins. Shared cache/CDN cần biết response phụ thuộc vào `Origin`. Kiểm tra header:

```http
Vary: Origin
```

Nếu cache lưu response của `https://app.example.com` rồi phục vụ cho `https://admin.example.com` mà không phân biệt origin, CORS response có thể sai hoặc dữ liệu bị lộ nếu cache policy cũng sai. Đừng tự xóa `Vary` khi đang điều tra; hãy xem CDN/ingress cache key và cache-control.

## 6. Nguyên nhân số 4: CORS response headers bị thêm nhiều lần

### 6.1. Vì sao header trùng xuất hiện?

Tình huống phổ biến là **nhiều tầng cùng nghĩ mình là CORS owner**:

```text
Browser
  |
  v
CDN / Ingress       -> adds Access-Control-Allow-Origin
  |
  v
Spring Cloud Gateway -> adds Access-Control-Allow-Origin
  |
  v
Backend service     -> @CrossOrigin adds Access-Control-Allow-Origin
  |
  v
Response returns through all layers
```

Ví dụ response cuối:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Credentials: true
```

Hoặc xấu hơn, các lớp trả hai origin khác nhau:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Origin: https://admin.example.com
```

Browser thường từ chối response khi `Access-Control-Allow-Origin` có nhiều giá trị hoặc giá trị không phải một origin hợp lệ (hoặc `*` theo điều kiện phù hợp). **Không được nối hai origin bằng dấu phẩy** để thay cho việc chọn origin hợp lệ.

### 6.2. Xác định lớp nào thêm header

Kiểm tra lần lượt:

1. **Backend trực tiếp:** gọi backend bằng `curl` với `Origin`, xem nó đã trả CORS headers chưa.
2. **Gateway:** gọi cùng request qua Gateway và so sánh response.
3. **Ingress/CDN:** gọi qua public domain và so với Gateway service nội bộ.
4. **Spring Security:** kiểm tra có `CorsConfigurationSource`/CORS integration thêm headers không.
5. **Controller:** tìm `@CrossOrigin`, `CorsWebFilter`, `WebFluxConfigurer` hoặc code set response headers.
6. **Gateway filters:** kiểm tra `AddResponseHeader`, `SetResponseHeader`, `DedupeResponseHeader`, global/default filters.
7. **Proxy middleware:** kiểm tra ingress annotations/config như `add_header`, response header policies hoặc CDN rules.

Dùng `curl -i` hoặc `curl -D - -o /dev/null` để xem tất cả response headers. Một response nhìn trong browser console có thể đã bị browser gộp/hiển thị khác cách server gửi; cần kiểm tra wire response qua từng tầng.

### 6.3. `DedupeResponseHeader` trong Gateway

Spring Cloud Gateway Server WebFlux có `DedupeResponseHeader` GatewayFilter Factory để loại giá trị response header trùng khi **Gateway CORS logic và downstream cùng thêm một header**.

Ví dụ:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders_api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin
```

Có thể khai báo strategy tường minh:

```yaml
filters:
  - name: DedupeResponseHeader
    args:
      name: Access-Control-Allow-Credentials Access-Control-Allow-Origin
      strategy: RETAIN_UNIQUE
```

Các strategy được hỗ trợ:

| Strategy | Ý nghĩa |
| --- | --- |
| `RETAIN_FIRST` | Giữ giá trị xuất hiện đầu tiên (mặc định). |
| `RETAIN_LAST` | Giữ giá trị xuất hiện cuối cùng. |
| `RETAIN_UNIQUE` | Giữ các giá trị duy nhất, loại các giá trị trùng nhau. |

**Chỉ dùng dedupe như lớp phòng vệ khi các giá trị lặp thực chất giống nhau và policy đã thống nhất.** Nếu Gateway trả `https://app.example.com` còn backend trả `https://admin.example.com`, chọn `RETAIN_FIRST` hoặc `RETAIN_LAST` sẽ che giấu xung đột chính sách chứ không sửa nguyên nhân. Hãy chọn một owner và loại cấu hình CORS thừa.

### 6.4. Giới hạn của route-level dedupe

`DedupeResponseHeader` là **GatewayFilter gắn vào route**. Do đó:

- Nó áp dụng với response đi qua route có filter đó.
- Nó không tự sửa header bị CDN/ingress thêm **sau khi Gateway trả response**.
- Nếu preflight được xử lý tại simple URL handler mapping mà không đi qua route Gateway, đừng giả định route-level dedupe sẽ xử lý response preflight đó.
- Nó không sửa cấu hình origin sai, không xác thực origin và không thay thế CORS policy.

Nếu header lặp trên preflight, ưu tiên xử lý nguồn CORS trước route (Security CORS/Gateway handler) và loại lớp khác cùng phát header. Nếu lặp trên actual response đi qua route, có thể dùng dedupe sau khi đã xác định nguyên nhân và xác nhận các giá trị trùng nhau.

### 6.5. Không phải mọi response header lặp đều giống nhau

Một số headers như `Vary` có thể chứa nhiều tokens và có ngữ nghĩa danh sách. `Access-Control-Allow-Origin` lại phải là **một origin cụ thể hoặc wildcard phù hợp**, không phải danh sách nhiều origins. Khi debug, đừng áp `DedupeResponseHeader` cho tất cả headers hoặc gộp bừa thành một chuỗi. Chỉ xử lý đúng các header CORS đang bị trùng và đúng contract của chúng.

## 7. Quy trình chẩn đoán theo HTTP thay vì đoán từ console

### 7.1. Bước 1 — xác nhận browser thực sự gửi gì

Mở Developer Tools → **Network**, bật Preserve log, tái hiện thao tác và tìm request `OPTIONS` ngay trước request API. Ghi lại:

- Request URL, method và status.
- Request headers `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`.
- Response headers `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods`, `Access-Control-Allow-Headers`, `Access-Control-Allow-Credentials`, `Access-Control-Max-Age`, `Vary`.
- Có bao nhiêu response header lines cho `Access-Control-Allow-Origin` và `Access-Control-Allow-Credentials`.
- Request actual có được browser gửi sau preflight không?

Không kết luận từ dòng console chung chung `CORS policy: No 'Access-Control-Allow-Origin' header`. Hãy xác định request nào thiếu header: OPTIONS, actual response hay redirect/error response.

### 7.2. Bước 2 — tái hiện preflight bằng curl

Ví dụ browser muốn gửi PATCH với Authorization và Content-Type:

```bash
curl -i -X OPTIONS \
  "https://gateway.example.com/api/orders/42" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
```

Kết quả mong đợi có dạng:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PATCH,DELETE
Access-Control-Allow-Headers: Authorization,Content-Type,X-Request-Id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 3600
Vary: Origin
```

Status có thể khác theo handler, nhưng nếu response là 401/403/404/405 hoặc thiếu các CORS headers cần thiết thì tiếp tục xác định tầng đã tạo response. Với CORS policy có credentials, `Access-Control-Allow-Origin` phải phản ánh một origin cụ thể, không phải `*`.

### 7.3. Bước 3 — thử origin không được phép

```bash
curl -i -X OPTIONS \
  "https://gateway.example.com/api/orders/42" \
  -H "Origin: https://untrusted.example.net" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization,content-type"
```

Origin không được phép phải bị từ chối theo policy, thường là 403 hoặc response không có CORS allow headers. **Không được** trả `Access-Control-Allow-Origin: https://untrusted.example.net` chỉ vì client gửi Origin đó. Server không được phản chiếu bất kỳ origin nào nếu chưa kiểm tra allowlist.

### 7.4. Bước 4 — so sánh actual request

```bash
curl -i -X PATCH \
  "https://gateway.example.com/api/orders/42" \
  -H "Origin: https://app.example.com" \
  -H "Authorization: Bearer REDACTED_FOR_EXAMPLE" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: cors-debug-001" \
  --data '{"status":"confirmed"}'
```

Lệnh trên minh họa HTTP actual request; dùng token giả trong tài liệu và token hợp lệ trong môi trường được phép. **curl không thực thi browser CORS policy**. Nó có thể trả 200/401/500 dù browser sẽ chặn JavaScript đọc response. Mục đích là xem Gateway/backend có xử lý request và response headers nào được gửi.

### 7.5. Bước 5 — gọi backend trực tiếp để khoanh vùng

Trong môi trường lab hoặc mạng nội bộ được phép, gọi cùng endpoint backend với cùng `Origin`:

```bash
curl -i \
  "http://127.0.0.1:9001/orders/42" \
  -H "Origin: https://app.example.com"
```

So sánh:

| Backend trực tiếp | Qua Gateway | Khả năng |
| --- | --- | --- |
| Không có CORS headers | Có một bộ hợp lệ | Gateway đang là CORS owner. |
| Có một bộ | Có hai bộ giống nhau | Gateway/ingress đang thêm lần nữa. |
| Có một origin | Có origin khác hoặc hai origins | Gateway/ingress/security config xung đột. |
| 200 | 404/405 cho OPTIONS | Route predicate/handler mapping cần kiểm tra. |
| 200 | 401/403 cho OPTIONS | Security WebFilter chain hoặc auth proxy chặn trước. |
| 200 | Browser báo CORS dù curl qua Gateway có headers | Kiểm tra browser origin thật, redirect, cache, CDN và response thực cuối. |

Không expose backend trực tiếp ra Internet chỉ để debug. Thực hiện so sánh qua một network path được kiểm soát.

### 7.6. Bước 6 — xác định redirect hoặc error response

CORS có thể hoạt động ở preflight nhưng actual request chuyển hướng:

- HTTP → HTTPS redirect.
- Gateway route trả 302/307 tới login endpoint.
- Backend redirect tới domain khác.
- Authentication gateway trả error response không có CORS headers.
- Upstream timeout/502/503 được sinh ở Gateway.

Browser cũng áp CORS đối với response/redirect chain. Kiểm tra **từng hop** và host cuối, không chỉ request URL ban đầu. Tránh dùng redirect sang origin khác cho API nếu không có lý do; thiết kế auth flow và CORS rõ ràng.

### 7.7. Bước 7 — kiểm tra cấu hình đang chạy

Nếu YAML đã sửa nhưng hành vi không đổi:

1. Xác nhận app đang đọc đúng `application.yml`/profile.
2. Xác nhận prefix đúng với starter/version (Server WebFlux hay legacy Gateway starter).
3. Kiểm tra config override từ environment variables, Config Server, Helm values hoặc command-line args.
4. Xác nhận route/CORS config được load trên **mọi Gateway replica**.
5. Kiểm tra ingress/CDN đang gọi đúng service và không cache response cũ.
6. Restart/refresh theo cơ chế triển khai nếu cấu hình không hot reload.
7. Gửi preflight lại với origin/method/header đúng thực tế.

Không bật public `/actuator/env` để điều tra nhanh. Nếu dùng Actuator `configprops`, chỉ expose trên management network được bảo vệ và không làm lộ secrets.

## 8. Lab: một Gateway CORS owner với route chỉ nhận GET/POST/PATCH

### 8.1. Mô hình

Lab minh họa tình huống:

- Gateway Server WebFlux listen `:8080`.
- Backend demo listen `:9001`.
- Route `/api/orders/**` chỉ match `GET,POST,PATCH`.
- Preflight `OPTIONS` không match route vì Method predicate.
- Gateway global CORS cho phép `https://app.example.com`.
- `add-to-simple-url-handler-mapping: true` cho preflight.
- Backend demo **không tự thêm CORS headers**, để chỉ có một CORS owner.

```text
Browser / curl
    |
    | OPTIONS /api/orders/42
    | Origin + Access-Control-Request-Method: PATCH
    v
Gateway :8080
    |
    +--> global CORS simple URL mapping
    |      |
    |      +--> trả preflight response
    |           (không proxy OPTIONS tới backend)
    |
    +--> PATCH /api/orders/42
             |
             v
         Route Method=PATCH
             |
             v
         Backend :9001
```

Đây là lab loopback; không có authentication hoặc TLS. Không expose các cổng demo ra Internet, không dùng dữ liệu thật.

### 8.2. Route và CORS configuration

Trong project Spring Boot Gateway Server WebFlux 4.3, phần liên quan của `application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

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
                  - https://app.example.com
                allowedMethods:
                  - GET
                  - POST
                  - PATCH
                allowedHeaders:
                  - Authorization
                  - Content-Type
                  - X-Request-Id
                exposedHeaders:
                  - X-Request-Id
                allowCredentials: true
                maxAge: 600

          routes:
            - id: orders_api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
                - Method=GET,POST,PATCH
              filters:
                - StripPrefix=1
```

Trong ví dụ, global CORS policy áp dụng cho path pattern `[/**]`; trong production có thể thu hẹp thành `[/api/**]` hoặc pattern thích hợp. Dùng exact origin, methods và headers cần thiết. `maxAge: 600` tương đương 10 phút để lab dễ quan sát thay đổi; không phải giá trị bắt buộc.

**Nếu project có Spring Security**, không copy nguyên lab này rồi cho rằng global handler mapping luôn được chạy trước Security. Áp dụng Security CORS integration ở mục 4 và chọn một CORS owner nhất quán.

### 8.3. Backend demo không thêm CORS

Tạo một HTTP server tối giản trong thư mục riêng:

```java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public class OrdersBackend {

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 9001), 0);

        server.createContext("/", exchange -> {
            String response = "method="
                    + exchange.getRequestMethod()
                    + "\npath="
                    + exchange.getRequestURI().getRawPath()
                    + "\n";

            byte[] body = response.getBytes(StandardCharsets.UTF_8);

            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");

            // Backend cố ý không tự set Access-Control-Allow-*.
            exchange.sendResponseHeaders(200, body.length);

            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
        System.out.println(
                "OrdersBackend listening at 127.0.0.1:9001");
    }
}
```

Khởi chạy backend bằng JDK:

```bash
java OrdersBackend.java
```

Khởi chạy Gateway trong terminal khác:

```bash
mvn spring-boot:run
```

Các lệnh là hướng dẫn cho người học chạy trong project lab riêng, không phải bước worker chạy build repository bài giảng.

### 8.4. Gửi preflight tới Gateway

```bash
curl -i -X OPTIONS \
  "http://127.0.0.1:8080/api/orders/42" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
```

Kết quả cần kiểm tra:

- Có `Access-Control-Allow-Origin: https://app.example.com`.
- `Access-Control-Allow-Methods` cho phép `PATCH`.
- `Access-Control-Allow-Headers` bao gồm Authorization, Content-Type và X-Request-Id.
- `Access-Control-Allow-Credentials: true` nếu cấu hình credentialed CORS.
- Backend **không cần nhận OPTIONS** nếu Gateway đã xử lý preflight tại simple URL handler mapping.

Nếu response là 404, kiểm tra global CORS binding/prefix và `add-to-simple-url-handler-mapping`. Nếu là 401/403, kiểm tra Security/ingress trước. Nếu response thành công nhưng thiếu CORS headers, kiểm tra origin/path mapping và active configuration.

### 8.5. Gửi actual PATCH

```bash
curl -i -X PATCH \
  "http://127.0.0.1:8080/api/orders/42" \
  -H "Origin: https://app.example.com" \
  -H "Authorization: Bearer demo-token" \
  -H "Content-Type: application/json" \
  -H "X-Request-Id: lab-001" \
  --data '{"status":"confirmed"}'
```

Lab backend không xác thực token hoặc xử lý JSON nghiệp vụ; header token chỉ minh họa request CORS có Authorization. Trong production, actual request vẫn cần security chain và backend authorization. Quan sát response có một bộ CORS headers hợp lệ.

### 8.6. Thử origin bị từ chối

```bash
curl -i -X OPTIONS \
  "http://127.0.0.1:8080/api/orders/42" \
  -H "Origin: https://untrusted.example.net" \
  -H "Access-Control-Request-Method: PATCH" \
  -H "Access-Control-Request-Headers: authorization"
```

Origin ngoài allowlist không được nhận `Access-Control-Allow-Origin` tương ứng. Không sửa cấu hình thành wildcard chỉ để lệnh curl trả header.

## 9. Integration tests với WebTestClient

### 9.1. Test preflight hợp lệ

Trong project có Gateway app, cấu hình CORS và route/backend test:

```java
package com.example.gateway;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class GatewayCorsIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void allowedPreflightReceivesCorsHeaders() {
        client.options()
                .uri("/api/orders/42")
                .headers(headers -> {
                    headers.setOrigin("https://app.example.com");
                    headers.setAccessControlRequestMethod(
                            HttpMethod.PATCH);
                    headers.setAccessControlRequestHeaders(List.of(
                            "Authorization",
                            "Content-Type",
                            "X-Request-Id"));
                })
                .exchange()
                .expectStatus().is2xxSuccessful()
                .expectHeader().valueEquals(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                        "https://app.example.com")
                .expectHeader().value(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS,
                        value -> assertThat(value).contains("PATCH"));
    }

    @Test
    void disallowedOriginDoesNotReceiveAllowOrigin() {
        client.options()
                .uri("/api/orders/42")
                .headers(headers -> {
                    headers.setOrigin(
                            "https://untrusted.example.net");
                    headers.setAccessControlRequestMethod(
                            HttpMethod.PATCH);
                })
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().doesNotExist(
                        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
```

Test đầu kiểm tra preflight được xử lý **dù route chỉ match GET/POST/PATCH**. Test thứ hai kiểm tra origin không được phép không nhận allow-origin header. Nếu ứng dụng có Security CORS integration, hãy dùng cùng source/configuration thực tế và cung cấp security test setup phù hợp; không tắt security chỉ để test CORS xanh.

### 9.2. Test header không bị lặp

Sau khi cấu hình một CORS owner (hoặc dedupe response route đúng trường hợp), thêm assertion vào test actual response:

```java
client.patch()
        .uri("/api/orders/42")
        .header(HttpHeaders.ORIGIN, "https://app.example.com")
        .header(HttpHeaders.CONTENT_TYPE, "application/json")
        .bodyValue("{\"status\":\"confirmed\"}")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                "https://app.example.com");
```

`valueEquals` giúp xác minh giá trị cuối của header đúng một origin mong đợi trong response được WebTestClient quan sát. Nếu test fail, gọi trực tiếp backend và gọi qua Gateway để xác định lớp thêm giá trị trùng. **Không sửa test thành chấp nhận hai origins** chỉ để CI xanh. Snippet giả định lab không bật authentication; nếu có Spring Security, cung cấp test authentication hợp lệ cho actual PATCH thay vì nới lỏng security rules.

### 9.3. Những điều test cần tách riêng

| Test | Câu hỏi được trả lời |
| --- | --- |
| Unit test CORS configuration | Allowlist có đúng origin/method/header/credentials không? |
| Gateway integration preflight | `OPTIONS` được xử lý khi route predicate không match method không? |
| Security integration test | CORS được xử lý trước auth và actual request vẫn cần authentication không? |
| Backend contract test | Backend có tự thêm CORS headers hay không? |
| End-to-end qua ingress/CDN | Response cuối có header lặp hoặc bị proxy sửa không? |
| Browser test | Browser thực sự chấp nhận preflight và cho JavaScript đọc response không? |

Một `WebTestClient` test trên Gateway local không kiểm tra được header bị CDN/ingress thêm sau đó. Khi lỗi chỉ xảy ra trên domain public, cần kiểm tra **toàn bộ public request path**.

## 10. Bảng chẩn đoán nhanh theo triệu chứng

| Triệu chứng quan sát | Nguyên nhân có khả năng | Kiểm tra đầu tiên |
| --- | --- | --- |
| OPTIONS trả 404 | `OPTIONS` không match `Method` predicate; không có simple URL CORS mapping. | Xem route `Method`, global CORS và `add-to-simple-url-handler-mapping`. |
| OPTIONS trả 405 | Handler/proxy không hỗ trợ method hoặc controller mapping từ chối. | So response tại Gateway và ingress; xác minh CORS handler được gọi. |
| OPTIONS trả 401 | Security yêu cầu authentication trước CORS. | Bật Security CORS integration, kiểm tra `CorsConfigurationSource`. |
| OPTIONS trả 403 | Origin/method/header không nằm allowlist hoặc Security policy từ chối. | Đọc `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`. |
| OPTIONS 2xx nhưng thiếu ACAO | Không có CORS config khớp path/origin; sai prefix hoặc profile. | Kiểm tra config active và `Access-Control-Allow-Origin`. |
| OPTIONS 2xx có ACAO nhưng browser vẫn chặn | Method/header/credentials sai hoặc header bị lặp. | Kiểm tra toàn bộ `Access-Control-Allow-*` và response header lines. |
| Browser báo `No Access-Control-Allow-Origin` với GET | Actual response/error/redirect không có ACAO. | Kiểm tra actual response, không chỉ preflight. |
| POST/PATCH backend đã xử lý nhưng browser báo CORS | Actual request được gửi, response thiếu/sai CORS header. | Kiểm tra side effect/backend logs và response path. |
| ACAO xuất hiện hai lần giống nhau | Gateway và backend/ingress cùng thêm. | Gọi trực tiếp backend, sau đó qua Gateway để xác định lớp đầu tiên lặp. |
| ACAO có hai origin khác nhau | Hai CORS policies mâu thuẫn. | Chọn một CORS owner; sửa policy nguồn, không chỉ dedupe. |
| ACAC xuất hiện nhiều lần | Security/Gateway/backend cùng thêm credentials header. | So cấu hình credentials ở từng lớp. |
| Browser không gửi cookie dù preflight thành công | Cookie `SameSite`/`Secure`/domain hoặc browser third-party cookie policy. | Kiểm tra cookie attributes và fetch credentials mode. |
| JavaScript không đọc được `X-Request-Id` | Header chưa được expose. | Thêm `exposedHeaders: X-Request-Id`. |
| Browser vẫn dùng policy cũ sau deploy | Preflight result còn trong browser cache. | Kiểm tra `Access-Control-Max-Age`, thử private window. |
| Chỉ lỗi qua domain public, gọi service nội bộ đúng | Ingress/CDN thêm/xóa header, cache hoặc redirect. | So header tại Gateway service và public edge. |
| Lỗi xuất hiện sau khi thêm `@CrossOrigin` | Backend trở thành CORS owner thứ hai. | Bỏ một nguồn cấu hình hoặc dùng dedupe có chủ đích. |
| CORS lỗi chỉ ở một route | Route metadata, Path predicate, filter order hoặc method riêng. | So route definition và kiểm tra route overlap. |
| OPTIONS vào backend thay vì được Gateway trả lời | Global CORS handler chưa áp dụng hoặc preflight được route proxy. | Xem `add-to-simple-url-handler-mapping` và CORS ownership. |
| Actual response có `Vary` bị mất | Proxy/CDN rewrite headers hoặc cache policy. | Kiểm tra response qua từng hop và cache configuration. |

### 10.1. Decision tree

```mermaid
flowchart TD
    A["Browser báo CORS"] --> B{"Có OPTIONS preflight?"}
    B -->|"Có"| C{"OPTIONS status?"}
    B -->|"Không"| H["Kiểm tra actual response"]
    C -->|"404/405"| D["Route Method / simple URL mapping"]
    C -->|"401"| E["Spring Security CORS trước auth"]
    C -->|"403"| F["Origin / requested method / headers"]
    C -->|"2xx"| G["Kiểm tra allow-* headers và duplicates"]
    H --> I{"ACAO có đúng một origin?"}
    I -->|"Không có"| J["Actual error/redirect/backend CORS"]
    I -->|"Lặp hoặc khác nhau"| K["Gateway + backend + ingress cùng thêm"]
    I -->|"Có"| L["Credentials / exposed headers / browser cache"]
```

## 11. Những cách sửa sai thường gặp

| Cách sửa tạm | Vì sao không nên |
| --- | --- |
| Đặt `allowedOrigins: "*"` cho mọi API | Mở cross-origin cho mọi website; không hợp lệ cùng credentialed CORS. |
| Đặt `allowCredentials: true` vì browser báo thiếu cookie | CORS không tự làm cookie được gửi; còn phụ thuộc SameSite/Secure và auth policy. |
| Thêm `OPTIONS` vào mọi route `Method` | Có thể không giải quyết Security 401 và làm route predicates phức tạp. |
| Cho phép mọi `OPTIONS /**` và mọi request khác | Mở rộng authorization ngoài nhu cầu preflight. |
| `.anyExchange().permitAll()` | Vô hiệu hóa bảo vệ endpoint thật để chữa lỗi browser. |
| Tắt Spring Security CORS mà không có CORS handler khác | Preflight có thể không được xử lý trước authentication. |
| Bật thêm một `CorsWebFilter` vì thiếu header | Có thể tạo response headers trùng với Gateway/Security. |
| Dùng `DedupeResponseHeader` để chọn một trong hai origin khác nhau | Che giấu xung đột policy; không xác định origin nào được phép. |
| Thêm CORS headers bằng `AddResponseHeader` trên mọi route | Không xác minh Origin, method, headers; có thể phản chiếu/chia sẻ sai policy. |
| Chỉ kiểm tra preflight, bỏ qua actual response | Actual response hoặc error/redirect vẫn có thể thiếu CORS headers. |
| Chỉ thử bằng Postman/curl | Các công cụ này không thực thi browser CORS enforcement. |
| Cho rằng browser báo CORS nghĩa backend chưa chạy | Actual request có thể đã được xử lý và side effect đã xảy ra. |
| Xóa `Vary: Origin` để giảm header | Có thể làm cache phục vụ CORS response sai origin. |
| Log Authorization/cookie để debug | Tạo rủi ro lộ credentials; chỉ log request ID, route, status và lý do đã redact. |

## 12. Observability: ghi nhận đúng tín hiệu mà không lộ dữ liệu

### 12.1. Các trường log hữu ích

Khi điều tra, log có cấu trúc có thể gồm:

```text
routeId=orders_api
method=OPTIONS
path=/api/orders/42
originClass=allowed
corsDecision=PRE_FLIGHT_ACCEPTED
status=200
requestId=cors-debug-001
```

Với request bị từ chối:

```text
routeId=orders_api
method=OPTIONS
path=/api/orders/42
originClass=not-allowed
corsDecision=REJECT
status=403
requestId=cors-debug-002
```

Chỉ ghi Origin theo allowlist/class hoặc giá trị đã được kiểm soát; tránh ghi toàn bộ headers. **Không log Authorization, Cookie, session IDs hoặc request body** chỉ để tìm lỗi CORS.

### 12.2. Metrics nên tách theo decision và route

Có thể theo dõi:

- Số preflight theo route ID và kết quả allow/reject.
- Số 401/403/404/405 trên OPTIONS.
- Số response có header CORS thiếu hoặc duplicate theo kiểm tra ở tầng test/edge.
- Số actual requests và 4xx/5xx theo route.
- Latency preflight/actual request.
- Route/config version trên mỗi Gateway replica.
- Cache/CDN hit ratio khi policy thay đổi theo Origin.

Không dùng raw Origin, user ID hoặc request ID làm metric tag có cardinality không giới hạn. Dùng route ID, status class, decision và origin class có tập giá trị hữu hạn. Với lỗi header trùng, metric/cảnh báo nên chỉ rõ **lớp quan sát** (Gateway, ingress hay backend), không gom thành một con số không có nguồn.

### 12.3. So sánh qua từng network hop

Một quy trình vận hành có thể lưu các snapshot đã redact:

| Hop | Request/response cần so |
| --- | --- |
| Backend direct | Backend tự phát CORS headers nào? |
| Gateway service | Gateway có thêm/loại headers nào? |
| Ingress/internal load balancer | Có rewrite/append headers không? |
| Public CDN/WAF | Có thêm CORS policy, cache response hoặc redirect không? |
| Browser | Preflight result cache và actual response cuối cùng là gì? |

Chỉ so sánh những header liên quan; không dump toàn bộ response có thể chứa cookie/token. Nếu chỉ có lỗi ở public edge, sửa Gateway config có thể không có tác dụng vì header được thêm sau Gateway.

## 13. Ma trận kiểm thử hồi quy

| ID | Tình huống | Kết quả mong đợi | Tầng kiểm tra |
| --- | --- | --- | --- |
| C01 | OPTIONS, origin được phép, method PATCH | Preflight 2xx và ACAO đúng một origin. | Gateway integration. |
| C02 | OPTIONS, origin ngoài allowlist | Reject, không trả ACAO cho origin đó. | Gateway/Security integration. |
| C03 | OPTIONS, requested method không được phép | Reject. | CORS processor. |
| C04 | OPTIONS, requested header ngoài allowlist | Reject. | CORS processor. |
| C05 | Route có `Method=GET,POST,PATCH`, OPTIONS | Simple URL CORS handler xử lý preflight. | Gateway integration. |
| C06 | Security bật, OPTIONS không có cookie/token | CORS được xử lý trước auth; không trả 401 chỉ vì thiếu session. | Spring Security integration. |
| C07 | Actual PATCH không có token | Authentication vẫn từ chối. | Security integration. |
| C08 | Actual PATCH có token hợp lệ | Route và backend xử lý theo quyền. | HTTP integration. |
| C09 | Credentials bật với origin cụ thể | ACAO là origin cụ thể, ACAC là true. | HTTP integration/browser. |
| C10 | Credentials bật với allowedOrigins wildcard | Cấu hình bị từ chối hoặc không được phép theo Spring CORS policy. | Config validation. |
| C11 | Backend và Gateway cùng thêm cùng ACAO | Response cuối chỉ còn giá trị hợp lệ duy nhất sau khi chọn owner/dedupe. | Gateway integration. |
| C12 | Backend và Gateway trả hai origins khác nhau | Test phát hiện conflict; không coi dedupe là policy fix. | Gateway integration. |
| C13 | Preflight không match route và được xử lý ở simple mapping | Route-level dedupe không bị giả định chạy; CORS owner xử lý header. | Gateway integration. |
| C14 | `X-Request-Id` trong response | JS được đọc khi header nằm trong exposedHeaders. | Browser E2E. |
| C15 | Preflight cache còn hiệu lực sau deploy | Test private window/clear cache để xác minh policy mới. | Browser E2E. |
| C16 | Response qua CDN/ingress | Không thêm ACAO/ACAC trùng sau Gateway. | Edge integration. |
| C17 | Redirect/error response | CORS headers và redirect target phù hợp policy. | End-to-end. |
| C18 | Nhiều Gateway replicas | CORS policy đồng nhất trên mọi replica. | Deployment/staging. |

**Không đánh dấu C01–C18 đều PASS chỉ vì một unit test cấu hình.** CORS browser enforcement, Security filter order và header do CDN/ingress thêm cần kiểm thử ở đúng tầng.

## 14. Checklist trước khi phát hành

### Preflight và route matching

- [ ] Đã xem request `OPTIONS` thật trong Browser DevTools.
- [ ] `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` được ghi nhận chính xác.
- [ ] Route `Method` predicates được kiểm tra; hiểu vì sao OPTIONS không match.
- [ ] Global CORS được cấu hình đúng prefix của starter/version.
- [ ] `add-to-simple-url-handler-mapping: true` khi preflight không match route và cần simple URL handler.
- [ ] Route-level CORS metadata không bị kỳ vọng xử lý route miss.

### Security và CORS policy

- [ ] Nếu có Spring Security, CORS được xử lý trước authentication.
- [ ] OPTIONS chỉ được permit trong phạm vi API cần preflight.
- [ ] Actual requests vẫn yêu cầu authentication/authorization như hợp đồng.
- [ ] Exact allowed origins được cấu hình; không dùng wildcard cùng credentials.
- [ ] Allowed methods khớp actual method browser muốn gửi.
- [ ] Allowed headers khớp request headers cần thiết.
- [ ] Exposed headers chỉ gồm response headers frontend cần đọc.
- [ ] Cookie `SameSite`/`Secure` và credentials mode đã được kiểm tra.
- [ ] Không dùng CORS thay CSRF/authentication/authorization.

### Duplicate response headers

- [ ] Chỉ định một CORS owner chính cho public API.
- [ ] Đã so sánh backend direct, Gateway, ingress và public CDN.
- [ ] Không còn nhiều `Access-Control-Allow-Origin` hoặc `Access-Control-Allow-Credentials` xung đột.
- [ ] `DedupeResponseHeader` chỉ dùng cho giá trị trùng, đúng route response scope.
- [ ] Preflight được kiểm tra riêng vì có thể không đi qua route GatewayFilter.
- [ ] `Vary: Origin` và CDN cache key được giữ đúng.

### Test và vận hành

- [ ] Có `curl` preflight hợp lệ và origin bị từ chối.
- [ ] Có integration test bằng `WebTestClient` cho OPTIONS/actual request.
- [ ] Có test actual request không đủ quyền vẫn bị chặn.
- [ ] Có browser E2E test qua ingress/public domain.
- [ ] Logs không chứa token, cookie, session ID hoặc body.
- [ ] Metrics tách CORS decisions, status và route ID.
- [ ] Cấu hình active nhất quán trên mọi Gateway replica.
- [ ] Có rollback và cache invalidation plan khi đổi CORS policy.

## 15. Câu hỏi tự kiểm tra

**1. Preflight request là gì?**

Đó là request `OPTIONS` mà browser gửi trước một số cross-origin requests để hỏi server có cho phép origin, method và headers của actual request hay không.

**2. Vì sao route `Method=GET,POST` có thể khiến preflight bị 404?**

Vì preflight dùng method `OPTIONS`, không match predicate. Global CORS với `add-to-simple-url-handler-mapping: true` có thể xử lý request không match route predicate.

**3. Vì sao Spring Security có thể trả 401 trước khi Gateway CORS xử lý?**

Security WebFilter chain chạy trước handler mapping. Preflight thường không có cookie/session của actual request, nên cần CORS integration trước authentication.

**4. `OPTIONS permitAll` có tự tạo CORS headers không?**

Không. Nó chỉ cho phép authorization layer không chặn OPTIONS; cần CORS processor hợp lệ để kiểm tra origin/method/header và tạo response headers.

**5. Nếu actual request dùng PATCH, CORS allowedMethods cần gì?**

Phải cho phép **PATCH**, vì `Access-Control-Request-Method` mô tả actual method browser muốn gửi. OPTIONS là method của preflight transport, không thay cho actual method.

**6. Vì sao `allowedOrigins: "*"` không dùng được cùng `allowCredentials: true`?**

Credentialed CORS yêu cầu origin cụ thể hoặc origin pattern phù hợp; wildcard origin không được phép trong cấu hình allowedOrigins với credentials.

**7. `allowedHeaders` và `exposedHeaders` khác nhau thế nào?**

`allowedHeaders` kiểm soát headers browser được gửi; `exposedHeaders` cho JavaScript đọc headers từ response.

**8. Vì sao response có hai `Access-Control-Allow-Origin` có thể bị browser từ chối?**

Header này phải biểu diễn một origin hợp lệ (hoặc wildcard trong điều kiện cho phép), không phải nhiều origins. Hai lớp cùng thêm header có thể khiến response không hợp lệ.

**9. Khi nào dùng `DedupeResponseHeader`?**

Khi Gateway và downstream thêm **cùng một giá trị** và cần loại giá trị lặp trên response đi qua route. Nó không sửa hai CORS policies mâu thuẫn hoặc headers do CDN thêm sau Gateway.

**10. Vì sao curl thành công không chứng minh browser CORS hoạt động?**

curl không thực thi browser CORS policy. Browser kiểm tra preflight và response headers trước khi cho JavaScript đọc response.

**11. Nếu browser báo CORS sau POST, backend có thể đã xử lý POST không?**

Có. Actual request có thể đã tới backend và tạo side effect; chỉ response không thỏa CORS khiến JavaScript không đọc được.

**12. CORS có thay authentication hoặc CSRF protection không?**

Không. CORS là browser access policy; server vẫn phải xác thực, phân quyền và áp dụng CSRF protection phù hợp.

## Kết luận

**Preflight thất bại hoặc header CORS xuất hiện nhiều lần** thường bắt nguồn từ cấu hình không thống nhất giữa route predicates, Spring Security, Gateway CORS, backend và ingress/CDN. Khi route chỉ nhận `GET/POST/PATCH`, preflight `OPTIONS` có thể không match; Gateway Server WebFlux 4.3 hỗ trợ `globalcors.add-to-simple-url-handler-mapping` để xử lý CORS cho request không được route predicate nhận. Nếu Spring Security chạy trước, cần tích hợp CORS reactive trước authentication để preflight không bị từ chối chỉ vì thiếu session/token.

Khi response có nhiều `Access-Control-Allow-Origin` hoặc `Access-Control-Allow-Credentials`, hãy tìm **lớp nào đang thêm header** và chọn một CORS owner. `DedupeResponseHeader` hữu ích với các giá trị trùng trên response đi qua route, nhưng không thay thế việc sửa các policy xung đột và không tự xử lý preflight ngoài route chain. Kết hợp Browser DevTools, `curl`, `WebTestClient`, backend comparison và edge tests để xác minh cả **preflight lẫn actual request**. Giữ CORS policy hữu hạn, không dùng nó thay authentication/authorization, và bảo đảm header cuối cùng đúng trên toàn bộ đường đi từ browser tới microservices.

### Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Server WebFlux 4.3 — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/cors-configuration.html)
- [Spring Cloud Gateway Server WebFlux 4.3 — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/4.3/configprops.html)
- [Spring Cloud Gateway Server WebFlux 4.3 — DedupeResponseHeader Filter Factory](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/deduperesponseheader-factory.html)
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — CorsConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
- [Spring Framework 6.2 — DefaultCorsProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/cors/reactive/DefaultCorsProcessor.html)
- [Spring Security 6.5 — CORS Integration for Reactive Applications](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — Reactive Web Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [MDN — CORS Guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
- [MDN — Preflight Request](https://developer.mozilla.org/en-US/docs/Glossary/Preflight_request)





