# Token dạng opaque và tích hợp introspection khi phù hợp

## 1. Vì sao API Gateway cần hiểu opaque token?

Trong kiến trúc microservices, **Spring Cloud Gateway** thường là điểm vào chung cho ứng dụng web, mobile hoặc đối tác. Gateway dùng **route predicate** để chọn tuyến, chạy **filter chain**, biến đổi path/header và chuyển request đến dịch vụ phù hợp. Trước khi chuyển một request chứa dữ liệu cá nhân, đơn hàng hay thanh toán, hệ thống cần xác định **ai đang gọi** và **người gọi có quyền làm gì**.

Một cách phổ biến là client gửi **OAuth 2.0 access token** qua header:

```http
GET /api/catalog/products/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer 7f8e...opaque-value...
```

Nếu access token là **opaque token**, Gateway không thể chỉ đọc chuỗi token rồi tự biết `sub`, `scope`, thời hạn hay trạng thái bị thu hồi. Thay vào đó, resource server thường phải hỏi **Authorization Server** qua một **introspection endpoint**.

Tích hợp này phù hợp khi nhà cung cấp danh tính (IdP) phát hành **reference/opaque access token**, hoặc yêu cầu resource server kiểm tra trạng thái token qua một nguồn tập trung. Nó cũng làm xuất hiện các câu hỏi quan trọng: kiểm tra ở tầng nào, xử lý lỗi IdP ra sao, bao lâu có thể dùng cache, cách chuyển danh tính đến backend và chi phí của mỗi request.

Bài thuộc chương **Xác thực và phân quyền** của module **SPRING_CLOUD_GATEWAY**. Bạn sẽ học:

1. Phân biệt **access token opaque** và **JWT access token**.
2. Hiểu OAuth 2.0 **Token Introspection (RFC 7662)** và trường `active`.
3. Cấu hình **Spring Security Reactive OAuth2 Resource Server** trong Gateway Server WebFlux.
4. Áp dụng **scope/authority**, giải thích lỗi **401/403** và vị trí của security filter so với Gateway filter.
5. Đánh giá trade-off giữa kiểm tra trực tuyến, cache, thu hồi token, TLS và độ sẵn sàng của IdP.
6. Kiểm thử đúng luồng xác thực trong một API Gateway có route, rewrite path, rate limiting, circuit breaker và quan sát request.

> **Phạm vi:** ví dụ dùng **Spring Cloud Gateway Server WebFlux**, **Spring Security Reactive** và **OAuth2 Resource Server**. Cấu hình route minh họa cả namespace Gateway WebFlux mới (`spring.cloud.gateway.server.webflux`) và kiểu phổ biến ở nhánh 4.x (`spring.cloud.gateway`). Security API và property có thể thay đổi theo phiên bản Spring Boot/Spring Security; cần chọn các phiên bản tương thích và kiểm chứng bằng kiểm thử tích hợp.

## 2. Authentication, authorization và vai trò của token

**Authentication (xác thực)** trả lời: người gọi hoặc ứng dụng nào đứng sau request? **Authorization (phân quyền)** trả lời: danh tính đó được phép truy cập tài nguyên hoặc thực hiện hành động nào?

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Bearer access token | Client chứng minh quyền truy cập bằng cách sở hữu một bí mật | `Authorization: Bearer <token>` |
| Authentication | Token còn hợp lệ và đại diện cho principal nào? | `sub=user-42`, `active=true` |
| Scope/authority | Token được cấp những quyền tổng quát nào? | `catalog.read`, `gateway.admin` |
| Authorization theo route | API Gateway có cho phép truy cập endpoint này? | GET catalog cần `SCOPE_catalog.read` |
| Authorization nghiệp vụ | Người dùng có sở hữu đơn hàng 42 không? | Order service kiểm tra chủ sở hữu |
| Service-to-service authorization | Service gọi backend được phép dùng chức năng nào? | Client credentials và audience phù hợp |

Một token có `active=true` **không đồng nghĩa được phép truy cập mọi endpoint**. Gateway phải đánh giá scope/authority hoặc một policy tương ứng. Ngược lại, việc có scope `orders.read` chưa chứng minh user được đọc **mọi đơn hàng**; quyền sở hữu tài nguyên nên được kiểm tra ở microservice.

**Bearer token là bí mật**: ai có token còn hiệu lực có thể sử dụng nó trong phạm vi được cấp, nếu không có ràng buộc bổ sung như sender-constrained token. Vì vậy, phải truyền qua TLS, tránh log và bảo vệ token ở client.

## 3. Opaque token so với JWT access token

### 3.1. Khác biệt bản chất

**Opaque token** là giá trị mà resource server **không thể tự suy ra và xác minh nội dung có thẩm quyền** chỉ bằng cách đọc chuỗi token. Giá trị này thường là định danh ngẫu nhiên tham chiếu đến trạng thái do Authorization Server quản lý.

**JWT** có cấu trúc các phần được mã hóa và có thể chứa claims; resource server có thể kiểm tra chữ ký, issuer, audience, thời hạn và các điều kiện khác **ngay tại chỗ** nếu có cấu hình khóa/xác thực phù hợp.

| Tiêu chí | Opaque token + introspection | JWT + xác minh cục bộ |
| --- | --- | --- |
| Thông tin nằm trong token phía client | Thường không tự đọc được | Có claims có thể giải mã, nhưng **không tự động đáng tin** |
| Cách xác minh điển hình | Gọi IdP introspection endpoint | Kiểm tra chữ ký/JWK, issuer, audience, `exp`, `nbf` |
| Thu hồi token | IdP có thể báo `active=false` khi được hỏi lại | Thường cần TTL ngắn, denylist hoặc cơ chế khác nếu muốn thu hồi trước hạn |
| Độ trễ | Có thể thêm một lượt network cho lần introspection | Thường thấp hơn nếu xác minh trong tiến trình |
| Phụ thuộc IdP khi xử lý request | Cao hơn nếu không có cache | Có thể thấp hơn khi đã có JWK hợp lệ trong cache |
| Rủi ro khi cache | Dùng trạng thái `active` cũ sau khi token bị thu hồi | JWK/claims có thể cũ đến khi hết hạn hoặc refresh |
| Dữ liệu đưa vào client | Thường hạn chế lộ claims | JWT có thể để lộ claims cho ai đọc được token, dù có chữ ký |
| Vận hành | Cần endpoint, client credentials, HTTPS, timeout | Cần quản lý khóa, rotation, issuer/audience, thuật toán |

**Không đánh giá tính an toàn chỉ theo hình dạng chuỗi token.** JWT chỉ an toàn khi resource server xác minh chữ ký, thuật toán được phép, claims và nguồn phát hành; một opaque token chỉ an toàn khi introspection endpoint và policy tin cậy được cấu hình đúng.

Ngoài ra, **introspection không bắt buộc chỉ áp dụng cho token có hình dạng opaque**: một Authorization Server có thể hỗ trợ introspect cả một số token dạng JWT. Lựa chọn phương thức xác minh dựa vào hợp đồng với IdP và chính sách bảo mật, không chỉ đếm dấu chấm trong chuỗi token.

### 3.2. Khi nào opaque token phù hợp?

Nên cân nhắc opaque token và introspection khi:

- IdP **chủ đích phát hành opaque access token** và có endpoint introspection chuẩn.
- Resource server cần kiểm tra tình trạng token **đã bị thu hồi** tương đối nhanh, trong giới hạn chính sách cache và thời gian IdP cập nhật.
- Tổ chức muốn quản lý metadata/ủy quyền tại Authorization Server thay vì phát toàn bộ claims cho client.
- Các resource server có kênh kết nối đáng tin với IdP và chấp nhận chi phí latency/availability.
- Hệ thống đã có vận hành introspection, client credentials và cơ chế giám sát phù hợp.

Không nhất thiết chọn introspection khi đã có JWT tự xác minh được, yêu cầu latency cực thấp, IdP có giới hạn băng thông nghiêm ngặt hoặc Gateway hoạt động trong môi trường thường xuyên mất kết nối với IdP. Trong những trường hợp đó, cần so sánh SLO và rủi ro thu hồi token để chọn giải pháp phù hợp.

## 4. OAuth 2.0 Token Introspection theo RFC 7662

### 4.1. Ai gọi endpoint introspection?

Một luồng tiêu biểu có bốn thành phần:

1. **Client**: nhận access token từ Authorization Server theo OAuth 2.0 flow phù hợp.
2. **Spring Cloud Gateway**: đóng vai trò **Resource Server**, nhận request kèm bearer token.
3. **Authorization Server / IdP**: phát hành token và cung cấp **introspection endpoint**.
4. **Upstream microservice**: xử lý nghiệp vụ sau khi Gateway xác thực/phân quyền.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Gateway + Spring Security
    participant I as Authorization Server / Introspection
    participant S as catalog-service
    C->>G: GET /api/catalog/products/42 + Bearer token
    G->>I: POST /introspect (token + client authentication)
    I-->>G: active=true + scope/sub/exp (nếu có)
    Note over G: Xác thực token và kiểm tra scope catalog.read
    G->>S: Chuyển request đã được phép qua Gateway route
    S-->>G: Response nghiệp vụ
    G-->>C: HTTP response
```

Sơ đồ mô tả một request **cần introspection**. Trong một hệ thống có cache được cấu hình, Gateway có thể trả kết quả đã xác minh từ cache thay vì gọi IdP mọi lần; độ mới của kết quả phụ thuộc TTL và cơ chế invalidation.

> **Điểm quan trọng:** introspection được thực hiện bởi **Spring Security Resource Server**. Một route predicate như `Path=/api/catalog/**` hoặc Gateway filter `AddRequestHeader` **không tự xác thực** bearer token.

### 4.2. Request introspection minh họa

Theo RFC 7662, endpoint thường nhận **HTTP POST** với body `application/x-www-form-urlencoded`, chứa tham số `token`. `token_type_hint` là tham số **gợi ý tùy chọn**. Endpoint cần xác thực bên gọi introspection bằng cơ chế IdP chấp nhận, ví dụ client credentials qua HTTP Basic.

```http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <client-credentials-encoded>
Content-Type: application/x-www-form-urlencoded

token=<url-encoded-access-token>&token_type_hint=access_token
```

Đoạn trên là **HTTP message minh họa**, không phải request sử dụng thông tin đăng nhập thật. Bearer token của client và mật khẩu của **introspection client** là hai loại bí mật khác nhau.

Ví dụ response **token còn hiệu lực**:

```json
{
  "active": true,
  "client_id": "web-client",
  "sub": "user-42",
  "scope": "catalog.read orders.read",
  "token_type": "Bearer",
  "iss": "https://identity.example.test",
  "aud": ["gateway-api"],
  "exp": 1900000000
}
```

Ví dụ response khi token không tồn tại, hết hạn hoặc đã bị thu hồi:

```json
{
  "active": false
}
```

Theo thông lệ RFC 7662, một token không còn hoạt động có thể được trả bằng **HTTP 200 + `active:false`**. Đó **không phải HTTP 401 của Gateway**. Gateway sẽ đánh giá kết quả introspection và từ chối request của client theo chính sách xác thực.

**Không phải trường nào cũng bắt buộc có mặt.** Ngoài `active`, IdP có thể cung cấp hoặc bỏ qua `sub`, `scope`, `client_id`, `aud`, `iss`, `exp`, `iat` và metadata khác. Cần thỏa thuận schema introspection thực tế với nhà cung cấp danh tính, không mặc định mọi response giống ví dụ.

### 4.3. Introspection endpoint và tài khoản xác thực của Gateway

Thông thường Gateway cần:

| Thông tin | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Introspection URI | HTTPS endpoint để hỏi trạng thái token | `https://identity.example.test/oauth2/introspect` |
| Client ID | Định danh của resource server khi gọi introspection | `gateway-resource-server` |
| Client secret | Bí mật xác thực Gateway với IdP | Lấy từ secret store |
| Access token của client | Token cần kiểm tra | Từ header `Authorization: Bearer ...` |
| Metadata trả về | `active`, `scope`, `sub` và claims khác | Kết quả IdP cấp cho Gateway |

Không dùng **client secret của frontend public client** làm mật khẩu introspection. Gateway thường là confidential client/resource server có credential riêng, quyền introspection tối thiểu và khả năng rotation.

Đường đến introspection endpoint cần HTTPS có xác minh chứng chỉ. Nếu IdP dùng mTLS, private CA hoặc một cơ chế xác thực client khác, phải cấu hình HTTP client phù hợp. Không nên chọn HTTP plaintext hoặc tắt certificate validation chỉ để làm kết nối chạy được.

## 5. Cấu hình OAuth2 Resource Server cho Spring Cloud Gateway Server WebFlux

### 5.1. Dependency cần có

Ứng dụng Gateway cần bộ dependency **Spring Security** và **OAuth2 Resource Server** hỗ trợ reactive stack. Với Spring Boot và dependency management phù hợp, một khai báo thường dùng trong Maven là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Gateway WebFlux cần các starter/dependency tương thích Spring Boot và Spring Cloud release train. Không thêm `spring-boot-starter-web` chỉ để viết Security config: nó là stack Servlet và có thể gây cấu hình web application type không mong muốn khi dự án vốn dùng reactive Gateway.

Một Resource Server **không bắt buộc** có chức năng OAuth2 Login. Nó xác minh bearer token trên request đến; việc phát hành access token hoặc hiển thị form đăng nhập do hệ thống danh tính/client phụ trách.

### 5.2. application.yml: khai báo opaque token introspection

Cấu hình Spring Boot Security chính:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${IDP_INTROSPECTION_URI}
          client-id: ${IDP_INTROSPECTION_CLIENT_ID}
          client-secret: ${IDP_INTROSPECTION_CLIENT_SECRET}
```

Lưu ý:

- Khóa là **`opaquetoken`**, không phải cấu hình `jwt.jwk-set-uri`.
- `introspection-uri` là endpoint của IdP, **không phải route URI đến catalog-service**.
- `client-id` và `client-secret` là credential Gateway dùng khi **gọi introspection**, không phải JWT/cookie của người dùng.
- Dùng placeholder không có fallback để môi trường thiếu secret/URI không âm thầm chuyển sang tài khoản hoặc IdP thử nghiệm.
- Đây là **Spring Security/Spring Boot configuration**, không phụ thuộc prefix `spring.cloud.gateway.routes` hay `spring.cloud.gateway.server.webflux.routes`.

Trong deployment, cung cấp biến từ secret manager hoặc cơ chế cấp bí mật được bảo vệ:

```bash
export IDP_INTROSPECTION_URI=https://identity.example.test/oauth2/introspect
# IDP_INTROSPECTION_CLIENT_ID và IDP_INTROSPECTION_CLIENT_SECRET
# phải được cấp bằng kênh bí mật của nền tảng, không ghi giá trị thật vào script.
export SPRING_PROFILES_ACTIVE=staging
java -jar target/api-gateway.jar
```

Tất cả tên miền và JAR là ví dụ. Trong production, cấu hình client ID/secret nên được kiểm soát quyền, không log toàn bộ `Environment` hoặc in qua Actuator công khai.

### 5.3. Cấu hình tuyến Gateway, không nhầm route và security policy

Ví dụ route catalog với namespace **Server WebFlux mới**:

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
                - Path=/api/catalog/**
              filters:
                - StripPrefix=1
```

Trên nhánh Gateway **Server WebFlux 4.x**, vị trí route thường là:

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-api
          uri: http://localhost:8081
          predicates:
            - Path=/api/catalog/**
          filters:
            - StripPrefix=1
```

Hai route YAML ở trên là **các lựa chọn theo phiên bản**, không cần khai báo đồng thời. Route chọn mọi request khớp `/api/catalog/**`; **route không tự yêu cầu token**. Chính sách SecurityWebFilterChain ở mục tiếp theo mới quyết định method/path nào được truy cập.

Ví dụ client `GET /api/catalog/products/42` sẽ qua Gateway và chuyển thành `GET /catalog/products/42` sau `StripPrefix=1`. Kiểm tra phân quyền ở Gateway cần được thiết kế cho **path client gửi ban đầu**, không mặc định dùng path đã rewrite.

## 6. Reactive SecurityWebFilterChain: xác thực và kiểm tra scope

### 6.1. Cấu hình Java cho API chỉ sử dụng bearer token

Một cấu hình minh họa:

```java
package example.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            // Chỉ phù hợp khi API stateless dùng Bearer token,
            // không dùng cookie/session làm credential cho browser.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)

            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/actuator/health", "/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/catalog/**")
                    .hasAuthority("SCOPE_catalog.read")
                .pathMatchers(HttpMethod.POST, "/api/catalog/**")
                    .hasAuthority("SCOPE_catalog.write")
                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_gateway.admin")
                .anyExchange().denyAll()
            )

            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(Customizer.withDefaults()))

            .build();
    }
}
```

Diễn giải:

1. `@EnableWebFluxSecurity` kích hoạt cấu hình Security reactive cho WebFlux.
2. `authorizeExchange` áp dụng quyền theo HTTP method và **URL Gateway nhận từ client**.
3. `GET /api/catalog/**` cần authority `SCOPE_catalog.read`; `POST` cần `SCOPE_catalog.write`.
4. `/api/admin/**` cần `SCOPE_gateway.admin`.
5. `anyExchange().denyAll()` đóng những endpoint chưa được chủ động cho phép. Một sản phẩm có route khác cần thêm matcher/policy tương ứng; không giữ nguyên đoạn này rồi kỳ vọng các route khác tự được truy cập.
6. `oauth2ResourceServer(...opaqueToken(...))` bật việc dùng introspection cho bearer token.
7. `csrf(...disable)` chỉ an toàn như lựa chọn **có điều kiện** cho API stateless không dựa vào cookie/session browser làm credential. Nếu sản phẩm kết hợp login qua cookie hoặc form/session, hãy thiết kế CSRF riêng, không sao chép lệnh disable một cách máy móc.

**CORS preflight:** với client trình duyệt, cần cấu hình CORS hợp lệ và cho phép xử lý `OPTIONS` preflight ở đúng tầng WebFlux/Spring Security. Matcher `denyAll` ở trên **không phải cấu hình CORS hoàn chỉnh**; có thể cần CORS integration hoặc matcher preflight được bảo vệ phù hợp theo kiến trúc.

### 6.2. Scope được ánh xạ sang authority ra sao?

Với cấu hình Resource Server OAuth2 opaque token mặc định của Spring Security, thông tin scope từ introspection thường được chuyển thành authorities có tiền tố `SCOPE_`.

Ví dụ introspection trả:

```json
{
  "active": true,
  "sub": "user-42",
  "scope": "catalog.read catalog.write"
}
```

Sau khi xác thực, principal thường có:

```text
SCOPE_catalog.read
SCOPE_catalog.write
```

Do đó `.hasAuthority("SCOPE_catalog.read")` khớp GET catalog, còn một token chỉ có `catalog.read` sẽ **không** qua được kiểm tra `SCOPE_gateway.admin`.

Mỗi IdP có thể biểu diễn quyền khác nhau: `scope`, `scp`, `roles`, `groups` hoặc metadata tùy biến. **Không tự suy luận tất cả đều được Spring ánh xạ thành authority mặc định.** Nếu quyền nằm ở custom claim, phải có converter/introspector phù hợp và test riêng, tránh vô tình cấp quyền admin từ dữ liệu không được chuẩn hóa.

### 6.3. Xác thực thành công không thay thế kiểm tra claims theo API

Một introspection response có `active=true` và scope rộng chưa chắc đủ:

- **Audience:** access token có được cấp cho API/Gateway này hay không?
- **Issuer:** thông tin đến từ IdP được phép hay không?
- **Client ID:** token thuộc đúng ứng dụng/nhóm client đã được phê duyệt hay chưa?
- **Expiration:** IdP còn công nhận token, cache có vượt `exp` hay không?
- **Tenant/organization:** token có thuộc tenant được phép hay không?
- **Token binding/sender constraint:** nếu dùng mTLS/DPoP, có kiểm tra đúng ràng buộc không?

Việc xác minh các trường này phụ thuộc hợp đồng IdP. `active=true` **không nên được xem là thay thế mọi ràng buộc audience/issuer của ứng dụng**. Nếu cần các kiểm tra bổ sung, có thể trang trí một bean `ReactiveOpaqueTokenIntrospector` rồi xác thực claims và chuyển đổi authority theo chính sách. Khi tự khai báo bean này, cần hiểu nó có thể **thay thế auto-configuration** từ properties và phải cung cấp một delegate introspector đúng phiên bản.

Không tự tạo quyền từ header `X-Role` hay `X-Scopes` do client gửi.

## 7. Gateway security filter và Gateway filter chain là hai tầng khác nhau

Spring Security reactive vận hành qua **`SecurityWebFilterChain`** thuộc chuỗi **WebFilter** của Spring WebFlux. Trong khi đó, `GatewayFilter` và `GlobalFilter` được Gateway gom và sắp xếp **sau khi route được chọn**.

```mermaid
flowchart TD
    C["Client + Bearer token"] --> W["Spring WebFlux SecurityWebFilterChain"]
    W --> A{"Token active và scope phù hợp?"}
    A -->|"Không có/không hợp lệ"| U["401 Unauthorized"]
    A -->|"Đã xác thực, thiếu quyền"| F["403 Forbidden"]
    A -->|"Hợp lệ, đủ quyền"| R["Gateway route predicates"]
    R --> G["GlobalFilter + GatewayFilter"]
    G --> P["StripPrefix / headers / load balancing"]
    P --> S["Upstream microservice"]
    S --> C
    U --> C
    F --> C
```

Đây là mô hình để hiểu trách nhiệm; thứ tự chi tiết của tất cả filter và cơ chế xử lý lỗi phụ thuộc cấu hình. Với request không khớp route sau khi vượt security, Gateway có thể trả 404.

**Hệ quả quan trọng:**

- Route `Path=/api/catalog/**` có thể khớp về mặt định tuyến nhưng request chưa chắc được phép đến route nếu Spring Security chặn trước.
- `RewritePath` hoặc `StripPrefix` sửa đường dẫn **trong Gateway chain**; policy bảo mật nên được xác định cho URL public ban đầu và không dựa vào việc path sau rewrite sẽ tự được kiểm tra lại.
- `RequestRateLimiter` ở Gateway filter chain có thể chạy sau xác thực; nếu rate limit theo user, dùng **principal đã xác thực** làm key, không tin header `X-User-Id` client tự gửi.
- `CircuitBreaker`/`Retry` của route upstream không mặc định bao bọc lệnh gọi introspection vì đó là công việc ở security layer và có HTTP client riêng.
- `GlobalFilter` áp dụng cho route chain, nhưng không bảo đảm nhìn thấy mọi response 401/403 do SecurityWebFilterChain trả **trước khi Gateway định tuyến**.

## 8. HTTP 401, 403, 200 và lỗi introspection

| Tình huống | Kết quả thường thấy ở Gateway | Cách hiểu |
| --- | --- | --- |
| Không gửi Bearer token cho endpoint cần auth | **401 Unauthorized** | Chưa xác thực |
| Token giả, hết hạn hoặc `active=false` | **401 Unauthorized** | Xác thực thất bại |
| Token `active=true`, thiếu scope `catalog.read` | **403 Forbidden** | Có danh tính nhưng không đủ quyền |
| Token đúng scope, Gateway route có upstream khỏe | Status do upstream trả, có thể 200/404/5xx | Gateway đã qua security, chưa chắc nghiệp vụ thành công |
| IdP trả 200 với `active=false` tại introspection | Gateway thường trả 401 cho client | 200 là **status của cuộc gọi Gateway → IdP** |
| Introspection endpoint yêu cầu credential khác | Có thể phát sinh 401/403 ở cuộc gọi nội bộ tới IdP | Không nhầm với 401/403 của client |
| IdP timeout/không khả dụng | Yêu cầu được bảo vệ phải **không được cho qua theo mặc định** | HTTP status cuối có thể tùy error handling; không giả định luôn 401 |
| Không có Gateway route sau khi qua security | Thường 404 | Khác với thiếu authority |

**`401` khác `403`:** 401 thường cần xác thực lại hoặc token hợp lệ; 403 thường đòi quyền cao hơn và không được sửa chỉ bằng cách gửi lại cùng token. Trong OAuth2, `WWW-Authenticate: Bearer` có thể chứa mã lỗi như `invalid_token` hoặc `insufficient_scope`; việc phơi bày chi tiết phải theo chính sách bảo mật.

### 8.1. Fail closed khi IdP không phản hồi

Một quyết định vận hành thiết yếu:

> Khi Gateway không thể chứng minh token hợp lệ, **không chuyển request tới endpoint được bảo vệ chỉ vì introspection endpoint đang lỗi**.

Đừng viết fallback kiểu “IdP timeout → cho qua tạm”. Nếu cần độ sẵn sàng cao, dùng IdP được triển khai HA, timeout hợp lý, cache kết quả được quản lý rõ ràng hoặc thiết kế token validation khác theo yêu cầu sản phẩm.

Một lỗi mạng đến IdP có thể trở thành response 5xx tùy chain xử lý thay vì 401; điều quan trọng về an toàn là **không coi token chưa xác minh là người dùng đã đăng nhập**. Cần kiểm thử nhánh lỗi để kiểm tra không có đường bypass auth.

### 8.2. Tách lỗi authentication khỏi lỗi upstream

Khi nhận 503 hoặc timeout, cần hỏi:

1. Gateway đã gọi introspection hay chưa?
2. IdP trả `active=false`, từ chối client authentication hay không trả lời?
3. SecurityWebFilterChain đã cho qua chưa?
4. Route `lb://` có instance không?
5. Upstream trả 5xx hay HTTP client Gateway lỗi mạng/TLS?

Không dùng một bảng log duy nhất “Gateway 5xx” để kết luận microservice hỏng. Tracing và metrics nên tách lệnh gọi introspection, lựa chọn route, kết nối upstream và xử lý response.

## 9. Độ trễ, caching và tính mới của trạng thái token

### 9.1. Chi phí kiểm tra trực tuyến

Nếu một Gateway xử lý 500 request/giây, và **mỗi request được bảo vệ đều thực hiện một introspection mới**, IdP có thể phải phục vụ gần **500 introspection/giây** chỉ từ Gateway đó. Nhiều Gateway replica có thể nhân tải lên đáng kể.

Độ trễ mỗi request khi không cache có thể gồm:

```text
Thời gian request tổng
  ≈ network client -> Gateway
  + thời gian Gateway -> IdP introspection
  + chính sách Security
  + route/filter/LoadBalancer
  + thời gian Gateway -> upstream
  + xử lý backend và response
```

Đây là phép phân rã khái niệm, không phải công thức cộng cố định trong mọi trường hợp vì nhiều bước bất đồng bộ và có thể trùng lấp phần việc. Quan trọng là **introspection ảnh hưởng latency và availability của toàn request**.

Spring Security resource server không nên được mặc định xem là có cache kết quả introspection theo một TTL phù hợp với nghiệp vụ của bạn. Nếu muốn cache, phải kiểm tra hành vi phiên bản hoặc thiết kế tầng cache tường minh.

### 9.2. Trade-off giữa cache và token revocation

| Phương án | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Không cache | Thông tin `active` tương đối mới theo IdP | Tăng latency, tải IdP, phụ thuộc mạng |
| Cache ngắn có TTL được kiểm soát | Giảm số lần gọi introspection | Token bị thu hồi vẫn có thể dùng trong thời gian cache |
| Cache dài | Tiết kiệm nhiều lần gọi | Tăng khoảng trễ phản ánh revocation, rủi ro bảo mật |
| JWT xác minh cục bộ | Có thể giảm phụ thuộc IdP mỗi request | Cần chiến lược expiration/revocation/rotation riêng |

**Không có cache là “thu hồi tức thì tuyệt đối”.** IdP có thể có replication delay, hoặc token đã được xác minh ngay trước khi bị thu hồi. Caching làm khoảng trễ này rõ ràng hơn.

Nếu dùng cache introspection:

- Không giữ kết quả `active` vượt `exp` của token nếu có; TTL cần được tính theo thời hạn token và độ mới policy chấp nhận được.
- Cache có giới hạn dung lượng, tránh bị tấn công bằng token ngẫu nhiên số lượng lớn.
- Hạn chế cache kết quả lỗi mạng như thể là `active=false`; phân biệt **token inactive** với **IdP không phản hồi**.
- Không log nguyên chuỗi token dùng làm cache key. Token vẫn là bí mật kể cả khi chỉ được giữ trong memory.
- Đặt khả năng invalidation/eviction nếu IdP hoặc hệ thống quản trị có cơ chế phát sự kiện thu hồi.
- Kiểm thử revocation, logout, khóa user, đổi quyền và thực tế cache hết hạn.

### 9.3. Timeout, concurrency và circuit breaker của introspection

Để một IdP chậm không làm nghẽn Gateway:

1. Đặt timeout kết nối/đọc phù hợp với SLO.
2. Giới hạn số cuộc gọi đồng thời đến IdP và kiểm soát hàng đợi.
3. Dùng connection pooling hợp lý, theo dõi DNS/TLS.
4. Nếu thêm circuit breaker, áp dụng **fail closed**; không trả authentication thành công giả.
5. Không retry vô hạn khi IdP lỗi; retry có kiểm soát và xét loại lỗi, tránh khuếch đại outage.
6. Thiết kế IdP HA và cảnh báo sớm khi tỷ lệ introspection error/latency tăng.

Cấu hình `spring.cloud.gateway...httpclient.response-timeout` thường điều khiển HTTP client **định tuyến upstream**, **không nhất thiết** điều khiển HTTP client mà Spring Security introspector dùng để gọi IdP. Khi cần proxy đầu ra, custom truststore hoặc timeout cho introspection, phải cấu hình đúng **client của introspector**, không mặc nhiên chỉ chỉnh các thuộc tính Netty routing.

## 10. Bảo mật đường truyền, bí mật và proxy đầu ra

### 10.1. Bảo vệ cả hai hướng

Một request dùng opaque bearer token có thể đi qua hai chặng rất nhạy cảm:

```mermaid
flowchart LR
    C["Client"] -->|"HTTPS + Bearer"| G["Gateway / Resource Server"]
    G -->|"HTTPS + client auth + token"| I["IdP introspection"]
    G -->|"HTTP(S) backend theo policy"| B["Microservice"]
```

**Client → Gateway** phải có TLS phù hợp; **Gateway → IdP** phải có TLS và xác minh certificate/hostname; **Gateway → upstream** cũng cần cơ chế mã hóa tin cậy theo chính sách hệ thống.

Nếu IdP yêu cầu truy cập qua **egress proxy doanh nghiệp**, không được giả định property `httpclient.proxy` của Gateway routing tự cấu hình HTTP client introspection. Đây là hai luồng outbound có thể sử dụng client khác nhau. Chẩn đoán DNS/CONNECT/TLS theo đúng HTTP client đang lỗi.

### 10.2. Không làm lộ access token hoặc client secret

- Không lưu access token thật hoặc introspection client secret vào `application.yml` đã commit Git.
- Dùng secret manager/Kubernetes Secret/volume mount và quyền truy cập tối thiểu.
- Không log header `Authorization`, `Proxy-Authorization`, `Cookie` hoặc body của request introspection.
- Tránh bật HTTP wiretap đầy đủ trên production nếu không có redaction.
- Không đặt token trong URL/query; URL thường xuất hiện trong access log, history, trace.
- Không trả nguyên payload introspection chứa thông tin nhận dạng nội bộ về client browser.
- Xoay vòng client secret và chứng chỉ; xác nhận tiến trình có cần restart/reload để lấy giá trị mới.

Access token chỉ nên được chia sẻ với resource server đúng **audience**. Nếu Gateway có nhiệm vụ chuyển bearer token đến upstream, backend vẫn phải xác minh token hoặc sử dụng một cơ chế trust được bảo vệ thích hợp. **Gateway xác thực thành công không mặc định khiến mọi service phía sau an toàn** nếu có đường truy cập bypass Gateway.

## 11. Principal, metadata và chuyển thông tin đến microservice

### 11.1. Có nên gửi tiếp bearer token đến backend?

Có hai mô hình phổ biến:

| Mô hình | Lợi ích | Trách nhiệm |
| --- | --- | --- |
| Gateway xác thực, backend cũng kiểm tra bearer token | Defense in depth, backend có thể kiểm tra quyền nghiệp vụ | Backend phải hiểu token và IdP, xử lý audience/scope phù hợp |
| Gateway xác thực rồi chuyển identity metadata đã kiểm soát | Backend giảm việc lặp introspection, giảm coupling | Bảo vệ network, xóa header giả mạo từ client, xác thực provenance của metadata |

Mô hình thứ hai **không nên** chỉ đơn giản chép `X-User-Id` do client gửi. Nếu dùng header danh tính giữa Gateway và service, Gateway phải **xóa/ghi đè input không tin cậy**, lấy danh tính từ **principal đã xác thực** và bảo vệ kết nối nội bộ bằng mạng, mTLS hoặc cơ chế ký xác nhận thích hợp.

Với các nghiệp vụ nhạy cảm, service vẫn nên kiểm tra quyền trên tài nguyên, trạng thái tenant, ownership và logic nghiệp vụ.

### 11.2. TokenRelay không phải đồng nghĩa với introspection

Spring Cloud Gateway có thể hỗ trợ **`TokenRelay`** trong kịch bản Gateway đóng vai trò OAuth2 client và chuyển access token của authorized client. Điều đó **không phải yêu cầu bắt buộc** để thực hiện opaque token introspection ở Gateway.

Một request inbound đã có `Authorization: Bearer ...` có thể được chuyển tiếp tùy filter/header policy; điều cần quan tâm là **backend có được phép nhận chính token đó hay không**, audience và ranh giới tin cậy. Đừng thêm TokenRelay chỉ vì thấy từ “token” rồi vô tình đổi token hoặc lộ credential không đúng API đích.

### 11.3. Scope tuyến khác quyền sở hữu dữ liệu

Ví dụ token user A có `catalog.read` và `orders.read`. Gateway có thể cho A gọi `GET /api/orders/42` theo scope, nhưng service phải xác nhận order 42 thuộc về A hoặc A có quyền quản trị tương ứng. **Gateway không nên cố truy vấn mọi bảng nghiệp vụ chỉ để quyết định ownership**.

Lựa chọn phân lớp giúp Gateway tập trung vào xác thực, chính sách chung, định tuyến, rate limiting, circuit breaker, retry, TLS và quan sát request; microservice chịu trách nhiệm quyết định nghiệp vụ cụ thể.

## 12. Kiểm thử bằng mock IdP và curl

### 12.1. Chuẩn bị môi trường thử nghiệm

Một môi trường test có thể có:

- Gateway: `http://localhost:8080` (chỉ cho phát triển trong mạng tin cậy).
- Mock introspection endpoint: `http://localhost:9000/oauth2/introspect` (chỉ local; production dùng HTTPS).
- Catalog service: `http://localhost:8081` trả nội dung khi gọi `GET /catalog/products/42`.
- Chính sách SecurityWebFilterChain như mục 6.

Mock introspection nên mô phỏng **xác thực Gateway** bằng client ID/secret, phương thức POST và các response có `active:true/false`; không chỉ trả `active:true` cho mọi token. Hạn chế mock lộ ra public network, và tuyệt đối không mang credential production vào môi trường test.

Khi kết nối từ container, `localhost` chỉ container hiện tại; phải dùng hostname/network phù hợp nếu mock IdP nằm ở container khác.

### 12.2. Các request kiểm thử

```bash
# 1) Không token: route GET catalog yêu cầu xác thực.
curl -i http://localhost:8080/api/catalog/products/42

# 2) Token thử nghiệm hợp lệ, có scope catalog.read.
curl -i \
  -H "Authorization: Bearer demo-token-catalog-read" \
  http://localhost:8080/api/catalog/products/42

# 3) Token thử nghiệm bị thu hồi hoặc không tồn tại.
curl -i \
  -H "Authorization: Bearer demo-revoked-token" \
  http://localhost:8080/api/catalog/products/42

# 4) Token thử nghiệm còn active nhưng không có scope catalog.read.
curl -i \
  -H "Authorization: Bearer demo-token-orders-read" \
  http://localhost:8080/api/catalog/products/42
```

Các chuỗi `demo-...` là **token giả định của mock IdP**, không phải access token thật. Với credential thực, cân nhắc shell history, process listing và log; không chia sẻ nguyên header Bearer trong bug report.

### 12.3. Ma trận kiểm thử hành vi

| Ca | Introspection response | Policy cần kiểm tra | Kỳ vọng |
| --- | --- | --- | --- |
| T1 | Không có token | GET catalog cần scope | 401, không gọi upstream |
| T2 | `active=false` | Không được xác thực | 401, không gọi upstream |
| T3 | `active=true`, scope `orders.read` | Thiếu `catalog.read` | 403, không gọi upstream |
| T4 | `active=true`, scope `catalog.read` | Đủ quyền GET catalog | Gateway gọi catalog-service |
| T5 | `active=true`, scope `catalog.write` | POST catalog | Được phép đi tiếp theo route/policy |
| T6 | Token hợp lệ nhưng `aud` sai | Có kiểm tra audience bổ sung | Từ chối theo policy |
| T7 | IdP không trả lời | Fail closed | Không cho phép truy cập upstream; status theo error handling |
| T8 | IdP trả 401 vì introspection client secret sai | Lỗi giữa Gateway và IdP | Không cho qua; điều tra secret/config |
| T9 | Token hợp lệ nhưng route `/unknown` không tồn tại | `denyAll` cuối chain | Bị từ chối theo security policy; nếu được permit thì có thể 404 |
| T10 | Token có `orders.read` nhưng truy cập order người khác | Backend kiểm tra ownership | 403/404 theo chính sách service |

**Bằng chứng quan trọng** không chỉ là status: hãy ghi nhận **số lần mock IdP được gọi**, **số lần upstream nhận request**, route ID và `sub` đã được làm sạch. Request bị 401/403 ở Security layer phải không tới upstream.

### 12.4. Kiểm thử performance và revocation

Thêm những thử nghiệm sau:

1. Gửi nhiều request với cùng token; đếm introspection calls để biết cache thực tế có hay không.
2. Thu hồi token ở mock/IdP, gọi lại; đo thời gian tối đa trước khi Gateway từ chối.
3. Cho introspection endpoint phản hồi chậm, ngắt kết nối hoặc trả 5xx; xác minh timeout và **không fail open**.
4. Gửi nhiều token ngẫu nhiên để xem có gây tải bất thường lên IdP/cache hay không.
5. Kiểm tra cách Gateway xử lý bearer token hết hạn nhưng upstream vẫn khỏe.
6. Kiểm tra preflight CORS từ browser và đường xử lý `OPTIONS` nếu frontend khác origin.
7. Nếu dùng load balancing/circuit breaker cho upstream, xác minh lỗi IdP được đo **riêng** với lỗi backend.
8. Nếu có proxy egress hoặc private CA, thử đúng HTTP client introspection thay vì chỉ kiểm thử kết nối Netty routing.

## 13. Những lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Mọi request đều 401 | Token không active, Authorization header không đến Gateway, introspection credentials sai | Phân biệt response IdP và Gateway; kiểm tra cấu hình, log đã redact |
| Introspection trả `active:true` nhưng Gateway 403 | Scope không khớp `SCOPE_...` hoặc policy từ chối | Kiểm tra claims và granted authorities |
| Chỉ `GET` được, `POST` lỗi | Policy yêu cầu scope `catalog.write`; hoặc CSRF đang bật phù hợp loại client | Kiểm tra method matcher, CSRF và chính sách auth |
| Bật `jwt` mà token là opaque | Resource Server đang dùng cơ chế JWT decoder thay vì introspection | Chọn đúng `opaquetoken` và DSL |
| Token ở browser bị lộ trong Network/log | Logging/wiretap quá chi tiết hoặc token trong URL | Gỡ log, rotate token và sửa client |
| Gateway hoạt động local nhưng prod timeout khi xác thực | IdP DNS, egress proxy, TLS/trust hoặc firewall | Kiểm tra đường Gateway → IdP, không chỉ Gateway → upstream |
| HTTP 503 khi IdP ngắt kết nối | Auth server outage hoặc handler mapping cho lỗi nội bộ | Fail closed, timeout/HA/monitoring |
| IdP trả HTTP 401/403 cho introspection | Sai client authentication hoặc không được quyền introspect | Kiểm tra client ID/secret, policy IdP |
| Scope có trong IdP nhưng authority không có | Claim format khác, converter mặc định không hỗ trợ | Kiểm tra principal và custom introspector/converter |
| Token bị revoke nhưng một số Gateway vẫn cho qua | Cache TTL, propagation delay, session hoặc khác nguồn kiểm tra | Kiểm tra cache và tất cả Gateway replicas |
| Gateway cho phép API nhưng service trả 403 | Service kiểm tra ownership/audience/role riêng | Xem chính sách nghiệp vụ và token forwarding |
| Route 404 dù token hợp lệ | Route predicate sai, namespace route sai hoặc upstream 404 | Tách route match và response upstream |
| Kết nối HTTPS IdP lỗi cert | CA, hostname/SNI, proxy TLS inspection, mTLS | Sửa trust/identity; không bật insecure trust |
| Dùng `AddRequestHeader=X-User-Id` từ input client | Client có thể giả mạo danh tính | Lấy giá trị từ authenticated principal hoặc backend tự xác minh |
| Latency Gateway tăng mạnh | Nhiều introspection calls, IdP chậm hoặc pool cạn | Đo từng chặng, thiết kế cache/HA/limits có kiểm soát |

## 14. Bài tập tình huống: Catalog và Orders qua cùng Gateway

**Bối cảnh:** một Gateway phục vụ hai API:

| Public API | Upstream | Quyền tối thiểu |
| --- | --- | --- |
| GET `/api/catalog/**` | `catalog-service` | `catalog.read` |
| POST `/api/catalog/**` | `catalog-service` | `catalog.write` |
| GET `/api/orders/**` | `order-service` | `orders.read` |

IdP cấp **opaque access token**, cung cấp `active`, `sub`, `scope`, `aud` và `exp` qua introspection. Một số token có thể bị thu hồi ngay khi user khóa tài khoản.

Yêu cầu thiết kế:

1. Cấu hình SecurityWebFilterChain để cấp quyền theo **method + path**, mặc định từ chối endpoint không được khai báo.
2. Bật opaque token introspection với URI/credential lấy từ deployment secrets.
3. Đảm bảo `aud` hợp lệ cho API phù hợp nếu đây là điều kiện hợp đồng với IdP.
4. Khi `active:false` hoặc token thiếu scope, Gateway không gửi request đến upstream.
5. Bổ sung Gateway routes đến service với `StripPrefix=1`.
6. Rate limit theo subject đã xác thực, tránh dùng header client tự khai báo.
7. Cho IdP timeout để quan sát fail-closed; không fallback thành anonymous có quyền.
8. Kiểm tra token revoke sau khi đã introspect thành công, đặc biệt nếu có cache.
9. Xác định backend có kiểm tra Bearer token độc lập hay dùng identity assertion được bảo vệ.
10. Ghi metrics riêng cho 401, 403, lỗi IdP, lỗi upstream, thời gian introspection và số request bị rate limit.

Ví dụ thêm một matcher vào SecurityWebFilterChain ở mục 6:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Trong code thật, đặt matcher này **trước `anyExchange().denyAll()`**, cùng nhóm với matcher catalog. Đừng thêm matcher bên ngoài DSL hoặc sau quy tắc tổng quát đã bao phủ mọi exchange.

### Checklist trước production

- [ ] Gateway đang dùng **Server WebFlux** và đúng phiên bản Security Resource Server.
- [ ] `opaquetoken.introspection-uri` trỏ đúng HTTPS IdP, có hostname/CA tin cậy.
- [ ] Gateway có client credentials riêng, cấp quyền introspection tối thiểu và được bảo vệ.
- [ ] SecurityWebFilterChain quy định rõ scope theo method/path, default deny khi phù hợp.
- [ ] Token `active:false`, sai audience/issuer, hết hạn hoặc bị revoke bị xử lý đúng theo policy.
- [ ] Resource Server không nhầm HTTP 200 introspection với HTTP 200 của client.
- [ ] Đã kiểm tra phân biệt 401 và 403, kể cả preflight/browser CORS.
- [ ] Fail-closed khi IdP timeout hoặc 5xx; không có bypass tự tạo.
- [ ] Cache TTL, max size và cách thu hồi token được review theo SLO bảo mật.
- [ ] Không dùng token/client secret trong log, trace, URL hoặc Git.
- [ ] Egress proxy/TLS/timeout của **introspection HTTP client** được kiểm tra riêng.
- [ ] Rate limit và audit dùng danh tính đã được xác minh.
- [ ] Upstream kiểm soát ownership/tenant và không bị bypass Gateway tùy tiện.
- [ ] Retry/circuit breaker chỉ áp dụng có kiểm soát; không retry vô hạn khi IdP lỗi.
- [ ] Có metrics/alerts khi introspection error, 401/403 và p95/p99 latency tăng.

## 15. Tổng kết và tài liệu tham khảo

**Opaque access token** thường không tự mang thông tin để API Gateway xác minh cục bộ. **Introspection theo RFC 7662** cho phép Spring Security Reactive Resource Server hỏi IdP xem token có `active` không và nhận metadata như `scope`, `sub`, `aud` hoặc `exp` khi được cung cấp.

Trong **Spring Cloud Gateway Server WebFlux**, cấu hình `spring.security.oauth2.resourceserver.opaquetoken` và `SecurityWebFilterChain` chịu trách nhiệm xác thực/phân quyền. **Route predicates và Gateway filters** vẫn phục vụ định tuyến, path/header rewriting, discovery, rate limiting hoặc độ bền hệ thống; chúng không tự thay thế một chính sách OAuth2 đúng đắn.

Opaque token có lợi khi cần trạng thái tập trung và thu hồi token, nhưng đổi lại là **chi phí mạng, độ trễ và phụ thuộc vào IdP**. Cần kết hợp HTTPS, credentials an toàn, audience/scope validation, cache TTL có chủ đích, fail-closed, kiểm tra quyền nghiệp vụ ở service và observability để vận hành Gateway an toàn.

Tài liệu để đối chiếu theo phiên bản:

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).
- [Spring Security Reactive — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html).
- [Spring Security Reactive — Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html).
- [Spring Cloud Gateway Server WebFlux — Gateway Filters](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories.html).
