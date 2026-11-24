# 401/403 và TokenRelay không gửi access token mong đợi

## 1. Bối cảnh: request đã tới Gateway nhưng backend vẫn từ chối

Một client gọi API qua **Spring Cloud Gateway (SCG)** và nhận HTTP **401 Unauthorized** hoặc **403 Forbidden**. Nhóm phát triển kiểm tra token ở phía client thấy có vẻ hợp lệ, route đã match, nhưng Catalog/Orders backend vẫn báo không có access token, token sai audience hoặc thiếu scope. Một số trường hợp response 401/403 được tạo ngay tại Gateway; những trường hợp khác được **upstream backend trả về rồi Gateway chuyển lại client**.

Đây là nhóm lỗi dễ chẩn đoán nhầm vì cùng một status code có thể phát sinh ở nhiều ranh giới:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Spring Cloud Gateway
    participant IDP as OAuth2 Authorization Server
    participant B as Catalog / Orders
    C->>G: HTTP request + optional Bearer token
    Note over G: Spring Security authenticates / authorizes
    G->>IDP: Obtain / refresh access token (when OAuth2 Client needs one)
    IDP-->>G: Access token
    G->>B: Proxied request + Authorization: Bearer ...
    B-->>G: 200, 401 or 403
    G-->>C: Final response
~~~

Một request có thể thất bại ở **inbound authentication**, **Gateway authorization**, **OAuth2 client token acquisition**, **TokenRelay**, **outbound HTTP transport** hoặc **authorization tại backend**. Vì thế chỉ nhìn status 401/403 ở browser/Postman chưa đủ để kết luận token bị mất ở đâu.

Bài **“401/403 và TokenRelay không gửi access token mong đợi”** thuộc chương **Chẩn đoán sự cố** của module **SPRING_CLOUD_GATEWAY**. Mục tiêu là xác định chính xác token nào phải đi qua hop nào, Gateway lấy token từ nguồn nào, backend mong đợi audience/scope gì và response được tạo ở tầng nào.

### Sau bài học, bạn có thể

1. Phân biệt **401** với **403**, đồng thời xác định status đến từ Gateway hay upstream.
2. Phân biệt ba vai trò Spring Security: **OAuth2 Client**, **OAuth2 Login** và **OAuth2 Resource Server**.
3. Giải thích `TokenRelay` không phải cơ chế sao chép tùy ý mọi header `Authorization`.
4. Cấu hình `TokenRelay` **không có clientRegistrationId** để relay authorized client gắn với user đã đăng nhập OAuth2.
5. Cấu hình `TokenRelay=catalog-client` để Gateway lấy service access token theo registration phù hợp, ví dụ **client_credentials**.
6. Hiểu vì sao inbound JWT được Resource Server xác minh chưa chắc đã là `OAuth2AuthorizedClient` mà TokenRelay có thể tìm thấy.
7. Kiểm tra OAuth2 registration, authorized client repository/service, principal, session, token expiry, issuer, audience và scopes.
8. Phát hiện filter/header nào đã xóa, ghi đè hoặc không chuyển tiếp token.
9. Kiểm thử bằng backend stub, đo số request và xác nhận upstream có `Authorization` mà không ghi token thật vào logs.
10. Xây runbook xử lý 401/403, tránh token forwarding sai trust boundary và khôi phục dịch vụ an toàn.

> **Phạm vi chính:** Ví dụ dùng **Spring Cloud Gateway Server WebFlux** và Spring Security reactive. Gateway Server Web MVC chạy trên Servlet/Spring MVC và có HTTP client/filter configuration khác; không chép `SecurityWebFilterChain`, `WebFilter` hoặc reactive APIs vào ứng dụng MVC. Tên property và dependency cần đối chiếu với Spring Boot/Spring Cloud BOM thực tế.

## 2. Phân biệt 401 và 403 trước khi kiểm tra TokenRelay

Theo HTTP semantics, hai status mô tả hai tình huống khác nhau:

| Status | Ý nghĩa thường gặp | Câu hỏi cần trả lời |
| --- | --- | --- |
| **401 Unauthorized** | Request thiếu credentials hợp lệ hoặc credentials không được chấp nhận; server thường gửi `WWW-Authenticate` challenge | Token có tồn tại, đúng chữ ký/issuer/audience và còn hạn không? |
| **403 Forbidden** | Server hiểu request nhưng từ chối thực hiện theo quyền/policy | Principal đã xác thực nhưng có thiếu scope/role/tenant/resource permission không? |

Tên “Unauthorized” của 401 dễ gây hiểu nhầm; có thể hiểu đơn giản là **chưa có danh tính được chấp nhận cho request**. 403 thường có nghĩa **đã xác định danh tính nhưng không đủ quyền**, dù ứng dụng thực tế có thể dùng status theo policy riêng.

### 2.1. Một request có thể nhận 401 từ hai nơi

**401 tại Gateway**:

- Client không gửi Bearer token trong khi route yêu cầu authentication.
- Token hết hạn, sai chữ ký, sai issuer, sai audience hoặc không được decoder tin cậy.
- Session OAuth2 login không tồn tại hoặc authorized client/token không còn hợp lệ.
- Gateway không có token phù hợp để gọi token endpoint theo registration.

**401 tại upstream**:

- Gateway gửi request nhưng không có header `Authorization`.
- Header có token sai audience hoặc issuer đối với Catalog.
- Token đã hết hạn, chữ ký sai hoặc backend không trust issuer/JWKS.
- Gateway relay nhầm ID token, refresh token hoặc một token không dành cho API backend.

### 2.2. Một request có thể nhận 403 từ nhiều policy

- Spring Security tại Gateway xác thực thành công nhưng authority không đủ.
- CSRF protection từ chối request state-changing thiếu CSRF token.
- Backend nhận token hợp lệ nhưng thiếu scope như `catalog.read`.
- Backend kiểm tra tenant/ownership và từ chối tài nguyên.
- Policy WAF/API gateway/authorization proxy phía trước SCG trả 403.

**Đừng tắt CSRF, mở `permitAll()` hoặc cấp thêm `ROLE_ADMIN` chỉ để làm biến mất 403** trước khi xác định policy nào đã tạo response.

### 2.3. Status code không chỉ ra nguồn response

Một HTTP 401 từ upstream có thể được SCG chuyển nguyên status về client. Vì vậy client thấy 401 **không chứng minh Spring Security Gateway đã chặn request**. Cần đối chiếu:

- Gateway inbound request count và authentication/authorization outcome.
- Gateway route ID và outbound attempt count.
- Backend request count và backend authorization logs đã redact.
- Upstream HTTP status/exception và final client status.
- Trace/correlation ID được truyền qua các hop.

Nếu backend request count bằng 0, lỗi có thể đã xảy ra trước khi gọi backend. Nếu backend nhận request và trả 401/403, hãy kiểm tra **token thực sự đến backend và policy của backend**.

## 3. Bốn vai trò OAuth2 thường bị trộn lẫn

Spring Security hỗ trợ nhiều vai trò OAuth2. `TokenRelay` cần hiểu **Gateway đang đóng vai nào**.

| Vai trò | Thành phần Spring Security | Nhiệm vụ | Token/đối tượng quan trọng |
| --- | --- | --- | --- |
| **OAuth2 Client** | OAuth2 Client support | Gateway gọi token endpoint hoặc dùng authorized client để truy cập resource server | `ClientRegistration`, `OAuth2AuthorizedClient`, access token |
| **OAuth2 Login** | `oauth2Login()` | Người dùng đăng nhập qua Authorization Code flow | `OAuth2AuthenticationToken` và authorized client gắn với user |
| **OAuth2 Resource Server** | `oauth2ResourceServer()` | Gateway xác minh Bearer token client gửi vào | `JwtAuthenticationToken` hoặc opaque-token authentication |
| **Authorization Server / IdP** | Hệ thống cấp token bên ngoài | Xác thực client/user và phát access/refresh tokens | Token endpoint, issuer, JWKS, scopes, audience policy |

### 3.1. OAuth2 Client khác Resource Server

Khi Gateway được cấu hình **Resource Server**, nó có thể đọc `Authorization: Bearer <token>`, xác minh JWT và đặt một `Authentication` vào security context. Việc đó chứng minh **token inbound được Gateway chấp nhận** theo validator đang cấu hình.

Nhưng điều này **không tự tạo một `OAuth2AuthorizedClient`** được lưu theo `ClientRegistration` để OAuth2 Client/TokenRelay lấy lại. Hai cơ chế có mục đích khác nhau:

- Resource Server kiểm tra token được gửi đến.
- OAuth2 Client quản lý registration, authorization grant, authorized client và token dùng khi gọi downstream.

Do đó, tình huống “Gateway nhận JWT hợp lệ nhưng TokenRelay không tìm được access token” có thể xuất hiện nếu chỉ cấu hình Resource Server rồi kỳ vọng `TokenRelay` tự sao chép Bearer header vào upstream.

### 3.2. ID token không phải access token

Trong OpenID Connect:

- **ID token** mô tả authentication event và danh tính user cho client/OIDC relying party.
- **Access token** được cấp để gọi resource server/API theo audience/scope.
- **Refresh token** dùng lấy access token mới, không phải credentials gửi đến API backend.

`TokenRelay` chuyển **OAuth2 access token** phù hợp theo authorized client. Không forward ID token hoặc refresh token sang Catalog/Orders như một cách sửa 401.

### 3.3. Access token cần đúng resource server

Một JWT hợp lệ về chữ ký vẫn có thể bị Orders từ chối nếu:

- `iss` không nằm trong trust configuration của Orders.
- `aud` không chứa audience mà Orders yêu cầu.
- `exp` đã qua hoặc `nbf` chưa đến (xem clock skew).
- `scope`/`scp` thiếu quyền.
- `azp`, client identity hoặc tenant claims không đáp ứng policy.
- Token là ID token hoặc token dành cho một API khác.

**Token hợp lệ ở Gateway không có nghĩa token hợp lệ ở mọi backend.** Mỗi resource server cần xác minh issuer, audience, signature, thời hạn và authorization theo contract của chính nó.

## 4. TokenRelay thực sự làm gì?

`TokenRelay` là một **Gateway filter factory** trong Spring Cloud Gateway, dùng OAuth2 Client support để lấy access token của một `OAuth2AuthorizedClient` và đưa token đó vào request gửi tới upstream theo dạng:

~~~http
Authorization: Bearer <access-token>
~~~

Nó có hai cách dùng quan trọng:

| Cấu hình route | Token được chọn | Tình huống điển hình |
| --- | --- | --- |
| `TokenRelay` | Authorized client gắn với user hiện đang authenticated qua OAuth2 login | Delegation theo user đã đăng nhập |
| `TokenRelay=catalog-client` | Authorized client theo `ClientRegistration` có ID `catalog-client` | Gateway lấy service token, thường dùng `client_credentials` |

**Không được suy diễn rằng `TokenRelay` luôn relay bất kỳ Bearer token nào đang nằm trong request header.** Đặc biệt, một inbound `JwtAuthenticationToken` từ Resource Server không mặc nhiên tương đương `OAuth2AuthenticationToken` có authorized client đã được lưu.

### 4.1. TokenRelay không có registration ID

Khi dùng:

~~~yaml
filters:
  - TokenRelay
~~~

Gateway sử dụng **user đã được OAuth2 login** và authorized client tương ứng với registration của người dùng để relay access token. Luồng điển hình:

1. User được chuyển tới IdP qua OAuth2 Authorization Code flow.
2. Sau callback, Spring Security tạo authentication cho user và authorized client chứa access token.
3. User gọi route cần truy cập downstream.
4. TokenRelay lấy access token từ authorized client gắn với authentication hiện tại.
5. Gateway gửi request tới backend với Bearer access token.

Nếu ứng dụng chỉ xác minh Bearer JWT inbound bằng Resource Server, không có OAuth2 login/authorized-client state tương ứng, filter không tự suy ra token để relay.

### 4.2. TokenRelay có registration ID

Khi dùng:

~~~yaml
filters:
  - TokenRelay=catalog-client
~~~

Gateway chỉ rõ **ClientRegistration ID** cần dùng. OAuth2 Client manager sử dụng registration và principal/context phù hợp để authorize hoặc lấy authorized client, rồi cung cấp access token cho outbound request.

Với registration có grant type `client_credentials`, Gateway lấy token đại diện cho **service/client application**. Backend thường nhìn thấy danh tính service, không phải user cuối. Đây là lựa chọn phù hợp khi backend chỉ cần biết gateway service nào đang gọi.

### 4.3. Ba mô hình token propagation

~~~mermaid
flowchart TD
    A["Inbound request"] --> B{"Gateway nhận kiểu identity nào?"}
    B -->|"OAuth2 login user"| C["OAuth2AuthenticationToken"]
    C --> D["TokenRelay không registration ID"]
    D --> U["Upstream với user access token"]
    B -->|"Gateway gọi bằng service identity"| E["ClientRegistration: client_credentials"]
    E --> F["TokenRelay=registrationId"]
    F --> V["Upstream với service access token"]
    B -->|"Inbound Bearer JWT / Resource Server"| G["JwtAuthenticationToken"]
    G --> H["TokenRelay không tự là raw header copy"]
    H --> I["Thiết kế pass-through có kiểm soát hoặc token exchange"]
    I --> W["Upstream với token dành đúng audience"]
~~~

| Mô hình | Backend thấy ai? | Khi nào phù hợp? |
| --- | --- | --- |
| User token relay | User/client identity theo access token | Backend cần quyền theo từng user và IdP cấp token đúng audience |
| Service token relay | Gateway service/client | Backend chỉ cần xác thực service caller, quyền service được giới hạn |
| Token exchange / on-behalf-of | User delegation qua token mới dành cho downstream | Cần giữ user context nhưng token inbound không có audience/scope phù hợp |

**Không dùng service token thay user token rồi cho rằng backend vẫn biết user nào đã gọi.** Nếu nghiệp vụ cần tenant, ownership và audit theo user, thiết kế delegation/token exchange hoặc một context đã được xác thực, có integrity protection và trust boundary rõ.

## 5. Phụ thuộc cần có cho Gateway WebFlux

`TokenRelay` cần OAuth2 Client support trong classpath. Với một ứng dụng **Spring Cloud Gateway Server WebFlux** sử dụng Maven, các dependency điển hình là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <!-- Chỉ thêm nếu Gateway xác minh inbound Bearer JWT. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
~~~

Tên starter Gateway thay đổi giữa các thế hệ Spring Cloud Gateway. Với dòng cũ, bạn có thể gặp `spring-cloud-starter-gateway` thay cho starter Server WebFlux mới. **Không thêm đồng thời nhiều Gateway server variants hoặc Web MVC/WebFlux starters tùy tiện**; chọn đúng stack và BOM được hỗ trợ.

Với Gradle, dependency coordinates tương tự:

~~~groovy
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Resource Server starter là **tùy chọn theo inbound security model**; nếu Gateway chỉ OAuth2 Login hoặc dùng service client credentials cho route, nhu cầu dependency có thể khác. Không thêm Resource Server chỉ vì đang cấu hình TokenRelay.

### 5.1. Kiểm tra dependency tree

Trong dự án thực, xác minh:

- OAuth2 Client classes được resolve từ Spring Security version do Boot BOM quản lý.
- Gateway Server WebFlux filter factory `TokenRelay` có trong runtime.
- Không có xung đột giữa Spring Boot và Spring Cloud release train.
- Nếu dùng Web MVC, dependency và TokenRelay support của **Gateway Server MVC release** phải được kiểm tra riêng.

Một route YAML có `TokenRelay` nhưng OAuth2 Client dependency không được nạp có thể khiến filter factory không khả dụng khi khởi động hoặc route không hoạt động như kỳ vọng. Đừng xử lý bằng cách tự copy Authorization header trước khi xác định dependency/runtime đúng.

## 6. Cấu hình TokenRelay theo OAuth2 Login: relay token của user

Mô hình đầu tiên phù hợp khi user **đăng nhập qua OAuth2/OIDC tại Gateway** và backend cần access token gắn với user đó.

### 6.1. OAuth2 Client registration cho Authorization Code

Ví dụ YAML:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-idp
            client-id: ${GATEWAY_OAUTH_CLIENT_ID}
            client-secret: ${GATEWAY_OAUTH_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - catalog.read
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.test/issuer
~~~

Các giá trị client ID, client secret, issuer và redirect URI là **placeholder cho môi trường test**. Client secret phải được lấy từ secret manager/secret injection được phê duyệt; không commit vào Git hoặc ghi ra log.

### 6.2. Spring Security WebFlux cho login và OAuth2 Client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OAuthLoginSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/oauth2/**", "/login/**")
                            .permitAll()
                        .pathMatchers("/api/catalog/**")
                            .authenticated()
                        .anyExchange().denyAll())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

Đây là mô hình **browser/session-based login**. Không disable CSRF một cách máy móc; session cookie có thể được browser tự gửi và cần CSRF protection phù hợp. Cần cấu hình redirect URI chính xác, trusted forwarded headers nếu sau reverse proxy, cookie Secure/HttpOnly/SameSite và session lifetime theo policy.

### 6.3. Route dùng TokenRelay không có registration ID

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-user-token
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=2
                - TokenRelay
~~~

Trong ví dụ, user đã đăng nhập OAuth2 và authorized client của registration `corporate-login` được lưu theo user. `TokenRelay` lấy **access token của authorized client hiện tại** để gọi Catalog.

**Không chỉ cấu hình route là đủ.** Nếu user chưa login, session không còn, authorized client không tồn tại, token hết hạn/không refresh được hoặc registration không đúng, Gateway không có token phù hợp để relay. Kết quả cụ thể phụ thuộc exception handling/security entry point/filter path; hãy kiểm tra logs đã redact và test trên đúng version.

### 6.4. User token relay cần session/authorized-client persistence

Với nhiều Gateway replicas:

- User có thể login ở Pod A nhưng request sau được load balancer đưa tới Pod B.
- Nếu session/authorized-client state chỉ lưu trong memory của Pod A, Pod B có thể không tìm thấy authentication hoặc token.
- Sticky sessions có thể giảm hiện tượng trong một số môi trường nhưng không thay thế HA/session design.
- Dùng shared session store như Spring Session phù hợp nếu ứng dụng cần login session giữa replicas; xác định authorized client được lưu ở repository/service nào và cách replicate/persist.
- Khi logout, revoke hoặc hết hạn session, token cũ không nên tiếp tục được dùng theo policy.

Không log session ID hoặc authorized-client access token để điều tra lỗi này.

## 7. Cấu hình TokenRelay theo client_credentials: service token

Mô hình thứ hai phù hợp khi Gateway gọi Catalog **với danh tính của chính Gateway service**. Client inbound có thể được xác thực bằng JWT, API key hoặc một cơ chế khác; downstream access token được lấy từ OAuth2 Client registration.

### 7.1. ClientRegistration cho Catalog

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          catalog-client:
            provider: internal-idp
            client-id: ${CATALOG_CLIENT_ID}
            client-secret: ${CATALOG_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - catalog.read
        provider:
          internal-idp:
            token-uri: https://idp.example.test/oauth2/token
~~~

Registration ID chính xác là **`catalog-client`**. Nó phải trùng với tham số trong route filter `TokenRelay=catalog-client`. Nếu ID khác một ký tự, Gateway có thể không tìm thấy registration. Scope `catalog.read` chỉ là ví dụ; authorization server và Catalog phải thống nhất tên scope/claim và cách map authority.

### 7.2. Route lấy service access token

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-service-token
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=2
                - TokenRelay=catalog-client
~~~

Khi request match route, filter dùng registration `catalog-client` để có authorized client/access token rồi gửi Bearer token tới Catalog. **Token này đại diện Gateway service**, không phải user cuối.

### 7.3. Gateway vẫn phải xác thực inbound user nếu API private

Nếu client gửi JWT và Gateway cần xác minh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ResourceServerAndClientSecurityConfiguration {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/catalog/**")
                            .hasAuthority("SCOPE_catalog.proxy")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                .oauth2Client(Customizer.withDefaults())
                // Ví dụ dành cho stateless Bearer-only API.
                // Nếu dùng cookie/session authentication, đánh giá CSRF riêng.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

Trong mô hình này có **hai token và hai quyết định quyền**:

1. Inbound token: client → Gateway, xác minh issuer/audience/scope `catalog.proxy`.
2. Service token: Gateway → Catalog, lấy theo `catalog-client`, scope `catalog.read`.

Gateway không relay nguyên inbound JWT chỉ vì nó đã xác thực token đó. Backend nhìn thấy service identity; nếu cần user identity, phải có token exchange/on-behalf-of hoặc một thiết kế delegation khác được IdP/backend hỗ trợ.

### 7.4. Client credentials có lifecycle khác authorization code

- Client credentials không yêu cầu browser login của user.
- Authorized client/token thường gắn với principal đại diện client/service trong OAuth2 client manager.
- Access token có thể được cache/reuse và lấy mới khi hết hạn theo manager/provider support.
- Mỗi Gateway replica có thể có token cache riêng; scale replicas có thể tăng token endpoint calls khi cold start.
- Client secret, token endpoint availability, clock skew và token expiry đều có thể gây lỗi.
- Không tự lấy token mới **cho mỗi request** bằng một HTTP call tự viết nếu OAuth2 Client manager đã quản lý authorized client lifecycle.

## 8. Inbound Bearer JWT và TokenRelay: trường hợp dễ nhầm nhất

Một cấu hình Resource Server có thể xác minh JWT:

~~~java
http.oauth2ResourceServer(resourceServer ->
        resourceServer.jwt(Customizer.withDefaults()));
~~~

Sau đó request đi vào với:

~~~http
GET /api/catalog/items/42 HTTP/1.1
Authorization: Bearer <client-access-token>
~~~

Gateway tạo authentication trong security context (thường là `JwtAuthenticationToken`). Nhưng **đó không tự động là OAuth2 Login authorized client**.

### 8.1. Vì sao TokenRelay không tự gửi token inbound?

`TokenRelay` là OAuth2 Client filter, nó tra authorized client theo **registration/principal context** mà OAuth2 Client manager sử dụng. Một Resource Server thường chỉ xác thực inbound bearer token, không tự tạo `ClientRegistration`/`OAuth2AuthorizedClient` tương ứng với token ấy.

Do đó:

| Gateway inbound setup | `TokenRelay` không registration ID |
| --- | --- |
| OAuth2 Login + user authorized client đã lưu | Có thể relay access token của user |
| Chỉ Resource Server + `JwtAuthenticationToken` | **Không mặc định là raw inbound token passthrough** |
| Resource Server + OAuth2 Client `client_credentials` registration | Dùng registration rõ ràng với `TokenRelay=...` để gửi service token |
| Token exchange/OBO đã tích hợp | Relay token downstream đã được cấp theo flow đó, theo integration cụ thể |

### 8.2. Nếu backend cần chính inbound user token thì chọn mô hình nào?

Có ba hướng cần đánh giá:

1. **IdP cấp access token có audience dành cho downstream** và kiến trúc có cơ chế pass-through Bearer được kiểm soát. Khi đó phải bảo đảm token thực sự có audience/scope phù hợp, Gateway không mở forwarding tới backend tùy ý và backend tự xác minh.
2. **OAuth2 Token Exchange / On-Behalf-Of (OBO)**: Gateway đổi inbound token lấy token mới có audience/scope cho backend, nếu IdP hỗ trợ grant/policy này.
3. **OAuth2 Login + authorized client**: khi user đăng nhập tại Gateway và access token của registration đã được lưu, dùng TokenRelay không registration ID.

**Không tự viết filter copy mọi `Authorization` header sang mọi URI upstream** chỉ để làm 401 biến mất. Cách đó có thể làm rò token tới service không được phép nhận, bỏ qua audience boundaries hoặc tạo SSRF/token exfiltration.

### 8.3. Không thay user token bằng client credentials mà quên ownership

Service token thường cho backend biết “Gateway service được phép gọi Catalog”. Nó **không chứng minh** user A có quyền đọc item của tenant B. Nếu Gateway thay user token bằng service token, backend cần một cơ chế user context đáng tin (token exchange, signed delegation context hoặc authorization call có bảo vệ) và vẫn kiểm tra ownership. Không dùng một header `X-User-Id` tùy ý làm bằng chứng.

## 9. Chẩn đoán ClientRegistration và OAuth2AuthorizedClient

Khi `TokenRelay` không gửi access token, hãy kiểm tra **registration → manager → authorized client → principal → filter → outbound request** theo thứ tự. Không bắt đầu bằng việc sửa JWT decoder của backend nếu Gateway chưa từng gửi request tới backend.

### 9.1. Registration ID phải trùng chính xác

Đối chiếu ba vị trí:

| Nơi | Ví dụ |
| --- | --- |
| YAML registration | `spring.security.oauth2.client.registration.catalog-client` |
| Route filter | `TokenRelay=catalog-client` |
| Token request/log metadata | registration ID `catalog-client` |

Các lỗi thường gặp:

- Đặt tên registration là `catalog-service` nhưng route dùng `catalog-client`.
- Có `client-id` nhưng không có `provider` hợp lệ/không tìm thấy issuer hoặc token URI.
- Grant type là `authorization_code` trong khi route chạy machine-to-machine và không có user login.
- Grant type là `client_credentials` nhưng client secret, authentication method hoặc scope không khớp IdP.
- Chỉ cấu hình `spring.security.oauth2.resourceserver.jwt.issuer-uri`, nhưng không có OAuth2 Client registration.
- Profile production không nạp cùng cấu hình OAuth2 Client như profile local.

### 9.2. Kiểm tra authorized client có được tạo/lưu không

`OAuth2AuthorizedClient` chứa thông tin như `ClientRegistration`, principal name và access token. Với OAuth2 Login, nó gắn với user đã được authorize; với client credentials, nó gắn với principal/client context theo cách manager sử dụng.

Hãy xác minh:

1. OAuth2 login callback đã hoàn tất thành công chưa?
2. Đúng `registrationId` có tồn tại trong `ReactiveClientRegistrationRepository` không?
3. Có authorized client được lưu trong `ServerOAuth2AuthorizedClientRepository` hoặc `ReactiveOAuth2AuthorizedClientService` đang dùng không?
4. Principal hiện tại có đúng tên/kiểu và đúng context mà authorized client được lưu theo không?
5. Token còn hạn hay manager có khả năng refresh/re-authorize không?
6. Pod hiện tại có thể đọc session/authorized-client state đã tạo ở Pod khác không?
7. Có custom manager/repository nào được khai báo và vô tình thay thế cấu hình mặc định không?

Không dump toàn bộ authorized client object vì nó chứa access token/refresh token. Chỉ log registration ID, loại grant, principal identifier đã pseudonymize, token expiry timestamp (nếu policy cho phép) và outcome.

### 9.3. Token endpoint và grant type

Với `client_credentials`, kiểm tra:

- Gateway kết nối được token endpoint qua DNS/TCP/TLS không?
- Client authentication method được IdP yêu cầu là `client_secret_basic`, `client_secret_post`, `private_key_jwt` hay phương thức khác?
- Client có được cấp scope đã yêu cầu không?
- Token response có `access_token`, `token_type` và `expires_in` hợp lệ không?
- Clock của Gateway/IdP có lệch làm token bị coi là chưa hợp lệ/hết hạn không?
- Token endpoint rate limit/availability có làm manager không lấy được token mới không?

Không gửi client secret trực tiếp vào URL/query string hoặc debug log. Nếu token endpoint trả `invalid_client`, lỗi nằm ở OAuth2 client authentication; nếu trả `invalid_scope`/`unauthorized_client`, kiểm tra grant/scope/client policy trước.

### 9.4. Client credentials và principal context

Trong một số ứng dụng, custom `ReactiveOAuth2AuthorizedClientManager` được cấu hình để authorize client theo principal hiện tại. Nếu code tự tạo manager nhưng không hỗ trợ `clientCredentials()` provider, `TokenRelay=catalog-client` có thể không lấy được token dù registration tồn tại.

Khi custom manager, kiểm tra:

- Provider chain có grant type tương ứng (`clientCredentials`, `authorizationCode`, `refreshToken`) không?
- Authorized client repository/service phù hợp với flow đang dùng không?
- Manager có nhận principal ổn định/đúng context không?
- Có lưu authorized client và xử lý hết hạn/refresh đúng không?
- Custom manager có bị tạo hai bean cùng loại hoặc bị auto-configuration thay thế không?

**Không tự viết token cache bằng một static field** để né lỗi manager. Nó có thể giữ token hết hạn, trộn client identities giữa tenants, không xử lý concurrency và không hỗ trợ rotation/revocation.

## 10. Filter chain: token đã lấy được nhưng bị mất trên đường outbound

Ngay cả khi OAuth2 Client lấy token thành công, một Gateway filter khác có thể làm mất hoặc ghi đè header trước khi HTTP request được gửi.

### 10.1. Kiểm tra từng chặng

~~~mermaid
flowchart TD
    A["Inbound Authorization (optional)"] --> B["Spring Security authentication"]
    B --> C["Route predicate selects route"]
    C --> D["TokenRelay obtains authorized client"]
    D --> E["GatewayFilter chain mutates outbound request"]
    E --> F["HTTP client sends request"]
    F --> G["Backend receives Authorization"]
~~~

| Điểm | Câu hỏi |
| --- | --- |
| Inbound request | Client có gửi credential nếu route yêu cầu không? |
| Spring Security | Principal có authenticated và đúng loại không? |
| Route | Request có match route chứa TokenRelay không? |
| OAuth2 Client | Registration/authorized client có được tìm thấy và authorize không? |
| Gateway filters | Filter khác có xóa hoặc thay `Authorization` không? |
| HTTP client | Có custom client/request transformer xóa header không? |
| Edge/service mesh | Proxy sau SCG có strip `Authorization` không? |
| Backend | Request tới đúng service/port và middleware đọc đúng header không? |

### 10.2. Những filter dễ xung đột

| Cấu hình | Rủi ro |
| --- | --- |
| `RemoveRequestHeader=Authorization` | Có thể xóa Bearer header sau khi TokenRelay đã thêm, tùy thứ tự filter thực tế |
| `SetRequestHeader=Authorization,...` | Có thể ghi đè token do TokenRelay cung cấp bằng giá trị khác |
| `AddRequestHeader=Authorization,...` | Có thể tạo nhiều giá trị Authorization hoặc header không hợp lệ |
| Custom `GlobalFilter` xóa headers | Có thể áp dụng cho nhiều routes, không riêng route cần token |
| Edge proxy/service mesh strip auth header | Token bị mất sau khi Gateway đã gửi đúng |
| Backend adapter đọc nhầm header/forwarded auth | Token có thể tới Pod nhưng không tới middleware cần nó |

**Không đặt `RemoveRequestHeader=Authorization` trên cùng route với `TokenRelay` nếu mục tiêu là giữ access token outbound.** Nếu muốn bỏ inbound token và dùng service token, hãy thiết kế rõ bước relay/overwrite, kiểm tra filter ordering của đúng version và chứng minh bằng HTTP stub. Đừng giả định thứ tự chỉ từ cách các dòng YAML được viết.

### 10.3. SetRequestHeader và AddRequestHeader không tương đương

- `SetRequestHeader` thay thế giá trị header bằng giá trị được chỉ định.
- `AddRequestHeader` thêm một giá trị header; nó không phải lựa chọn mặc định để thay Bearer token.
- `RemoveRequestHeader` loại bỏ header khỏi outbound request.

Với access token, **để TokenRelay sở hữu việc đặt Authorization**. Không đưa token tĩnh vào YAML, không tự ghép `Bearer <configured-token>` vào route config và không tạo một token giả để kiểm tra production.

### 10.4. Không log Authorization để chứng minh token đã relay

Có thể xác minh header tới backend mà không ghi token:

- Backend stub chỉ ghi `authorizationPresent=true/false`.
- Ghi scheme là `Bearer` nhưng redact credential.
- Nếu cần đối chiếu token trong lab, dùng token giả và hash fingerprint một chiều có kiểm soát; không log raw token.
- Ghi `routeId`, `registrationId`, `upstreamService`, response status và correlation ID.
- Tắt wiretap/header logging sau khi hoàn tất thí nghiệm.

## 11. Phân biệt lỗi inbound với lỗi upstream bằng request counters

Để không nhầm 401/403 của Gateway với 401/403 từ Catalog, hãy đặt counters ở **cả hai phía**.

| Quan sát | Kết luận có khả năng | Bước kế tiếp |
| --- | --- | --- |
| Gateway inbound count tăng, backend count = 0, status 401 | Authentication/token validation tại Gateway hoặc request chưa qua route | Kiểm tra Security entry point và sanitized auth failure |
| Gateway inbound count tăng, backend count = 0, status 403 | Gateway authorization/CSRF/policy chặn | Kiểm tra authority, matcher, CSRF |
| Backend count tăng, `Authorization` không có | TokenRelay không chạy/không lấy được token hoặc header bị strip | Kiểm tra route, manager, filter chain và edge |
| Backend count tăng, Bearer có nhưng backend 401 | Token sai/expired/issuer/audience hoặc backend không trust | Xác minh claims/policy bằng test tooling an toàn |
| Backend count tăng, Bearer có và backend 403 | Token được chấp nhận nhưng scope/role/tenant/ownership thiếu | Kiểm tra authorization policy tại backend |
| Backend count = 0, Gateway status 503 | Có thể token endpoint/route/filter/transport lỗi trước upstream | Phân biệt OAuth2 client exception với Catalog connectivity |
| Token endpoint count tăng liên tục | Authorized client không cache/reuse hoặc principal/manager thay đổi | Kiểm tra repository, principal key và expiry |
| Một số replica gửi token, replica khác không | Session/token cache/config drift | Kiểm tra per-Pod registration, session store, profile |

**Backend count bằng 0 không luôn đồng nghĩa Security chặn**: route có thể không match, DNS/connection failure xảy ra trước khi HTTP request tới backend hoặc TokenRelay thất bại. Cần kết hợp Gateway route outcome và exception type.

### 11.1. Trường hợp upstream trả 401 nhưng Gateway log không có auth failure

Đây là dấu hiệu mạnh cho thấy Gateway đã qua inbound security, nhưng backend không chấp nhận credentials. Kiểm tra:

1. Backend có nhận request không?
2. Header Authorization có hiện diện không (chỉ log boolean/scheme)?
3. Token là user token hay service token?
4. `iss`, `aud`, `exp`, `nbf`, scopes/claims có đáp ứng backend không?
5. Backend có lấy JWKS từ đúng issuer và cache/refresh key mới không?
6. Clock skew giữa IdP/Gateway/backend có hợp lý không?

### 11.2. Trường hợp Gateway trả 403 trước upstream

Nếu backend counter bằng 0, xem:

- `.hasAuthority("SCOPE_catalog.read")` có khớp cách Resource Server map scopes thành authorities không?
- Token có `scope` hay `scp` claim và converter có map đúng prefix `SCOPE_` không?
- Security matcher có bao phủ đúng path sau khi ingress rewrite chưa?
- CSRF có chặn POST/PUT/PATCH/DELETE vì cookie/session authentication không?
- Có authorization rule khác ở `SecurityWebFilterChain` hoặc method security không?

Không sửa bằng cách chuyển toàn bộ routes sang `permitAll()`. Hãy tạo test cho từng role/scope và xác minh backend không nhận request bị từ chối.

## 12. Issuer, audience, scopes và claim mapping

TokenRelay chỉ chuyển access token theo authorized client; **nó không tự biến token thành token mà backend mong đợi**. Hãy xác định contract giữa IdP và từng resource server.

### 12.1. Bảng claims cần đối chiếu

| Claim/thuộc tính | Câu hỏi | Lỗi có thể gặp |
| --- | --- | --- |
| `iss` | Issuer có đúng URL/trust configuration? | Backend không tin token |
| `aud` | Token dành cho API Catalog hay Gateway? | Gateway nhận nhưng Catalog trả 401 |
| `exp` | Token còn hạn? | Token expired |
| `nbf` | Token đã tới thời điểm hiệu lực? | Token not yet valid |
| `scope` / `scp` | Có quyền cần thiết? | 403 insufficient scope |
| `sub` | Subject là user hay service principal? | Ownership/audit sai |
| `client_id` / `azp` | Client nào được cấp token? | Client policy không cho phép |
| tenant/roles | Claims có đúng tenant/role mapping? | 403 theo business authorization |
| `kid` | Signing key có còn trong JWKS? | Signature verification failure khi key rotation |

### 12.2. Ví dụ audience mismatch

Giả sử inbound token:

~~~json
{
  "iss": "https://idp.example.test/issuer",
  "aud": ["gateway-api"],
  "scope": "catalog.proxy",
  "sub": "user-42",
  "exp": 1893456000
}
~~~

Gateway có thể chấp nhận token vì audience `gateway-api` và scope `catalog.proxy`. Nhưng Catalog yêu cầu audience `catalog-api` và scope `catalog.read`. **Relay nguyên token này tới Catalog không tự làm audience đổi thành `catalog-api`**; backend từ chối là đúng.

Giải pháp có thể là:

- IdP cấp token có nhiều audiences phù hợp nếu policy cho phép và backend chấp nhận.
- Dùng OAuth2 Token Exchange/OBO để đổi token theo audience/resource và scope Catalog.
- Dùng service credentials nếu backend chỉ cần xác thực Gateway service và user authorization được xử lý theo cơ chế riêng.

Không sửa claim `aud` trong JWT bằng cách decode rồi encode lại ở Gateway. Chữ ký sẽ không hợp lệ; Gateway không phải authorization server.

### 12.3. Scope và authority không đồng nghĩa tên role

Spring Security Resource Server thường map scope thành authority có prefix `SCOPE_` (ví dụ `catalog.read` thành `SCOPE_catalog.read`), còn roles có thể dùng `ROLE_`. Backend khác có thể đọc `scp`, `roles` hoặc custom claims. Kiểm tra **JWT converter và authorization mapping** ở từng resource server, không chỉ nhìn scope trong token.

### 12.4. Opaque tokens

Nếu IdP phát opaque access token, Resource Server có thể dùng introspection endpoint để xác minh. TokenRelay vẫn có thể relay access token của authorized client, nhưng backend phải hỗ trợ cùng token format/introspection hoặc trust policy tương ứng. Không giả định mọi Bearer token đều là JWT có thể decode offline.

### 12.5. Clock skew và key rotation

Token hợp lệ có thể bị từ chối nếu đồng hồ Gateway/backend/IdP lệch nhiều. JWKS rotation có thể tạo khoảng thời gian backend chưa tải signing key mới. Kiểm tra NTP/clock sync, token `kid`, JWKS cache/refresh và lỗi signature đã redact; không tăng clock skew vô hạn hoặc bỏ signature verification.

## 13. Cấu hình token relay có chủ đích: ví dụ đầy đủ

### 13.1. Mô hình A: user OAuth2 login

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-idp
            client-id: ${GATEWAY_OAUTH_CLIENT_ID}
            client-secret: ${GATEWAY_OAUTH_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - catalog.read
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.test/issuer

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-user-token
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=2
                - TokenRelay
~~~

**Hợp đồng:** user login tại Gateway, authorized client gắn với user, downstream nhận user access token. Cần session/authorized client persistence phù hợp nhiều replicas và backend phải chấp nhận token audience/scope đó.

### 13.2. Mô hình B: inbound JWT + outbound service token

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/issuer
      client:
        registration:
          catalog-client:
            provider: internal-idp
            client-id: ${CATALOG_CLIENT_ID}
            client-secret: ${CATALOG_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - catalog.read
        provider:
          internal-idp:
            token-uri: https://idp.example.test/oauth2/token

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-service-token
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=2
                - TokenRelay=catalog-client
~~~

Security configuration phải yêu cầu inbound scope thích hợp và enable OAuth2 Client support. Đây là **hai credentials khác nhau**: inbound JWT của user và outbound service access token. Catalog sẽ authorize service identity; nếu cần quyền theo user, phải bổ sung delegation context/token exchange đã được thiết kế.

### 13.3. Không trộn hai mô hình mà không xác định precedence

Nếu route vừa có user session, vừa có inbound JWT, vừa có `TokenRelay=catalog-client`, hãy quyết định backend cần:

- user access token;
- service access token;
- token exchange theo user; hoặc
- không cần token.

Không để việc có session cookie ngẫu nhiên quyết định token gửi xuống backend. Mỗi route cần một **token policy rõ ràng**, test được và được security review.

## 14. Spring Cloud Gateway Web MVC: khác biệt cần ghi nhớ

Gateway Server Web MVC dựa trên Servlet/Spring MVC và có filter/request lifecycle khác WebFlux:

| Gateway Server WebFlux | Gateway Server Web MVC |
| --- | --- |
| Reactive `SecurityWebFilterChain` | Servlet `SecurityFilterChain` |
| `ServerWebExchange`, `WebFilter`, `Mono` | `HttpServletRequest`, Servlet Filter, MVC/WebMvc.fn |
| Reactive OAuth2 Client repository/manager APIs | OAuth2 Client Servlet APIs/repository/manager tương ứng |
| Reactor Netty HTTP client trong cấu hình phổ biến | HTTP client/request factory của MVC stack |
| GatewayFilter/GlobalFilter reactive chain | MVC before/handler/after filters theo Gateway Server MVC release |

Không dùng `ServerOAuth2AuthorizedClientRepository` hoặc `ReactiveOAuth2AuthorizedClientManager` trong Servlet code chỉ vì tên TokenRelay giống nhau. Kiểm tra **TokenRelay support, starter, registration properties và filter API của đúng Gateway Server MVC version**. Nếu một tính năng/route filter chưa được hỗ trợ ở MVC release đang dùng, không giả định có thể kích hoạt bằng cách thêm YAML WebFlux.

## 15. Khi nào cần custom ReactiveOAuth2AuthorizedClientManager?

Trong một số phiên bản/cấu hình, auto-configuration có thể cung cấp manager phù hợp. Nếu ứng dụng **tự khai báo manager**, hãy xác minh provider chain hỗ trợ đúng grant mà route cần. Một manager chỉ có `authorizationCode()` sẽ không authorize registration `client_credentials`.

### 15.1. Ví dụ manager dành cho client credentials

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class OAuth2ClientManagerConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Đây là ví dụ cho **một manager chỉ cần client credentials** trong reactive web application. Nó không phải cấu hình bắt buộc cho mọi SCG release; trước khi thêm bean, kiểm tra manager auto-config hiện tại và API documentation tương ứng. Nếu cùng ứng dụng còn cần authorization code/refresh token, provider chain phải bao gồm các grant cần thiết, và repository/session phải phù hợp với từng flow.

### 15.2. Không ghi đè manager mà quên grant provider khác

Một lỗi cấu hình thường gặp:

1. Ban đầu manager hỗ trợ authorization code và refresh token cho user login.
2. Developer thêm bean manager mới chỉ có `clientCredentials()`.
3. `TokenRelay` không registration ID của user không còn lấy/refresh authorized client như trước.
4. Một số routes chạy được, routes user-specific bắt đầu lỗi.

Khi thêm custom manager, viết test cho **mọi loại registration** đang sử dụng và xác minh provider chain, principal context, authorized-client repository/service. Không dựa vào một route service-token để kết luận tất cả user-token routes vẫn hoạt động.

### 15.3. Repository và service có vai trò khác nhau

- `ServerOAuth2AuthorizedClientRepository` lưu/đọc authorized client trong context của reactive web request (thường gắn session/user).
- `ReactiveOAuth2AuthorizedClientService` cung cấp persistence/service abstraction cho authorized clients theo registration/principal.
- `DefaultReactiveOAuth2AuthorizedClientManager` dùng repository theo web exchange.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` phù hợp với các ứng dụng/service context dùng authorized-client service, tùy integration.

Chọn loại manager/repository theo **user session hay machine client**, không chỉ theo tên class. Một service-to-service token cache dùng principal key không ổn định có thể xin token liên tục; một user-session repository không chia sẻ giữa replicas có thể gây lỗi ngẫu nhiên.

## 16. Thứ tự filter và session persistence

### 16.1. Security WebFilterChain và GatewayFilter chain là hai pipeline khác nhau

Spring Security WebFlux bảo vệ inbound request ở tầng WebFilter. Sau khi request qua security và Gateway route được chọn, Gateway filter chain thực thi các route/global filters, bao gồm TokenRelay.

~~~mermaid
flowchart TD
    A["HTTP inbound request"] --> B["WebFlux WebFilter chain"]
    B --> C{"Authenticated / authorized?"}
    C -->|No| D["401 / 403 response"]
    C -->|Yes| E["Route predicate matching"]
    E --> F["Route GatewayFilter chain"]
    F --> G["TokenRelay / path / header filters"]
    G --> H["Outbound HTTP client"]
    H --> I["Backend authorization"]
~~~

Một request bị Spring Security chặn **không đi tới TokenRelay route filter**. Vì vậy không có outbound Authorization header trong trường hợp đó là hành vi đúng; không phải lỗi TokenRelay.

### 16.2. Filter order và header mutation

Gateway kết hợp default filters, route filters và global filters theo cơ chế ordering của framework. Không giả định rằng thứ tự chạy luôn chính xác bằng thứ tự dòng YAML sau khi các filters được wrap/sort.

Để chẩn đoán:

1. Xác định route ID thật sự được match.
2. Kiểm tra route filters sau khi cấu hình được bind.
3. Tìm custom GlobalFilter/route filters có mutate Authorization.
4. Trong test, kiểm tra header tại **backend stub**, không chỉ kiểm tra exchange trước TokenRelay.
5. Thử bỏ tạm filter gây nghi ngờ trong test profile và so sánh, không xóa policy production để “thử nhanh”.

### 16.3. SaveSession và OAuth2 Login

Khi OAuth2 Login lưu authentication/authorized client vào WebSession, cần hiểu session được persist lúc nào và qua hạ tầng nào. Một số luồng/ứng dụng dùng Gateway filter `SaveSession` để buộc lưu WebSession trước khi chuyển tiếp request, nhưng **không phải mọi route TokenRelay đều bắt buộc thêm SaveSession**. Chỉ sử dụng khi session lifecycle/deployment model yêu cầu và có integration test chứng minh.

Nếu Gateway chạy nhiều replicas:

- Dùng session store dùng chung khi browser login state cần truy cập từ mọi Pod.
- Kiểm tra cookie domain/path/Secure/SameSite và forwarded scheme khi ở sau TLS-terminating proxy.
- Đảm bảo session/authorized client persistence không làm mất authorized client khi request đổi Pod.
- Kiểm tra rolling deployment không xóa session/authorized client ngoài policy.

### 16.4. Không trộn browser login và machine API một cách ngẫu nhiên

Browser dùng session cookie và OAuth2 Login; machine client thường gửi Bearer token và Resource Server xác minh. Có thể hỗ trợ cả hai, nhưng cần **security matchers và CSRF policy riêng**. Không bật login session cho tất cả API rồi nghĩ TokenRelay sẽ tự relay Bearer token của mọi machine client.

## 17. Kiểm thử TokenRelay bằng HTTP backend stub

Unit test cho route predicate không đủ để chứng minh token tới upstream. Một integration test nên có **token endpoint test double**, **Gateway HTTP listener thật** và **backend stub**.

### 17.1. Sơ đồ test

~~~mermaid
flowchart LR
    T["JUnit / HTTP client"] --> G["Gateway RANDOM_PORT"]
    G -->|client_credentials| IDP["Token endpoint stub"]
    IDP -->|fake access token| G
    G -->|Authorization: Bearer fake-token| B["Catalog HTTP stub"]
    B --> J["Request journal: tokenPresent, route, count"]
~~~

Trong test, dùng access token giả như `test-service-access-token`, không dùng token của người dùng thật hoặc môi trường production. Token endpoint stub trả response OAuth2 theo định dạng chuẩn, ví dụ:

~~~json
{
  "access_token": "test-service-access-token",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "catalog.read"
}
~~~

Backend stub chỉ ghi:

~~~text
requestCount=1
authorizationPresent=true
authorizationScheme=Bearer
resolvedPrincipal=service-catalog-client (test metadata)
~~~

Không ghi giá trị access token ra console hoặc test report. Nếu cần assertion chính xác, test có thể so sánh với token giả **trong bộ nhớ** và không in giá trị khi assertion fail.

### 17.2. Những điều integration test cần xác minh

1. Gateway khởi động và route chứa `TokenRelay=catalog-client` được nạp.
2. OAuth2 Client registration có đúng ID và grant type.
3. Token endpoint stub được gọi khi cần authorized client mới.
4. Backend stub nhận đúng một request cho một inbound request trong test không retry.
5. Header `Authorization` có scheme Bearer và credential chính là token giả từ token endpoint.
6. Backend stub nhận đúng path/query sau `StripPrefix`.
7. Client nhận response status/body theo contract.
8. Lần gọi kế tiếp khi token còn hạn có thể reuse authorized client; test token endpoint call count theo manager/cache policy của version.
9. Khi token endpoint trả `invalid_client` hoặc timeout, Gateway không gọi Catalog bằng token giả/credential rỗng.
10. Khi backend trả 401/403, response được quan sát như upstream response, không nhầm với inbound authentication failure.

### 17.3. Negative tests

| Test | Setup | Assertion |
| --- | --- | --- |
| Registration không tồn tại | Route dùng `catalog-clinet` (sai ID) | Startup/filter/authorization failure rõ; backend HITS=0 |
| OAuth2 Client dependency thiếu | Test context không có OAuth2 Client support | App/filter không khởi động hoặc route không dùng được; không che lỗi |
| Token endpoint `invalid_client` | Client ID/secret test sai | Backend HITS=0, lỗi token acquisition được ghi nhận đã redact |
| Token endpoint `invalid_scope` | Scope không được phép | Backend HITS=0 |
| Token endpoint timeout | Stub không phản hồi trong deadline | Request fail hữu hạn, không treo vô hạn |
| Authorized client hết hạn | Token expiry đã qua | Manager refresh/re-authorize theo grant, hoặc trả lỗi đúng |
| Inbound JWT thiếu scope | Resource Server + `client_credentials` | Gateway 403, backend HITS=0 |
| Upstream không có Authorization | Thêm test filter cố ý strip header | Test phát hiện `authorizationPresent=false` |
| Upstream trả 401 | Stub trả 401 sau khi nhận request | Backend HITS=1, status provenance là upstream |
| Upstream trả 403 | Stub trả 403 | Backend HITS=1, không tự cấp thêm scope |

### 17.4. Test user-token relay khác service-token relay

Với OAuth2 Login:

- Dựng test authorization server hoặc dùng Spring Security test support để tạo authentication/authorized client phù hợp.
- Xác minh authorized client gắn với principal đúng.
- Gửi request qua session test và assert backend nhận user access token giả.
- Kiểm tra session hết hạn/mất authorized client và multi-replica persistence.

Với Resource Server + `client_credentials`:

- Gửi inbound JWT test hợp lệ vào Gateway.
- Gateway xác minh scope inbound.
- TokenRelay lấy **service token giả** từ token endpoint stub.
- Backend nhận service token; test ghi rõ nó không phải inbound JWT.

Không dùng một test chỉ kiểm tra status 200 để kết luận hai flow này tương đương.

## 18. Runbook chẩn đoán 401/403 và TokenRelay

Đi theo thứ tự dưới đây giúp khoanh vùng lỗi nhanh mà không cần dump token.

### Bước 1 — Xác định status được tạo ở tầng nào

Ghi lại:

- Timestamp, route ID, correlation/trace ID.
- Method/path đã loại bỏ query nhạy cảm.
- Client nhận status nào và `WWW-Authenticate` có giá trị gì.
- Gateway có route match không, outbound attempt count bao nhiêu.
- Backend có nhận request không, status do backend trả là gì.

Nếu có 401/403 trước route, không có lý do để TokenRelay chạy. Nếu backend nhận request rồi trả 401/403, tập trung vào outbound credentials và backend authorization.

### Bước 2 — Xác định Gateway dùng OAuth2 flow nào

Hỏi rõ:

1. Inbound request dùng session OAuth2 Login hay Bearer JWT Resource Server?
2. Downstream cần user token, service token hay token exchange?
3. Route dùng `TokenRelay` hay `TokenRelay=<registrationId>`?
4. Registration có đúng grant type không?

Đây là bước quan trọng nhất. Nếu câu trả lời là **Resource Server nhận JWT, backend cần chính token đó**, đừng mong TokenRelay no-arg tự sao chép raw inbound header.

### Bước 3 — Kiểm tra dependency và configuration

- OAuth2 Client starter có trong runtime classpath không?
- Route filter factory TokenRelay có được nhận diện không?
- `spring.security.oauth2.client.registration.<id>` có được nạp ở profile đang chạy không?
- Registration ID trong route có trùng tuyệt đối không?
- Token endpoint URI/issuer/client authentication method/grant/scopes đúng không?
- Có custom `ReactiveOAuth2AuthorizedClientManager` thiếu provider không?
- Namespace route đúng Gateway Server WebFlux version không?

### Bước 4 — Kiểm tra principal và authorized client

- Với OAuth2 Login: user đã đăng nhập và session có còn không?
- Authorized client có được lưu theo đúng principal/registration không?
- Với client credentials: manager có authorize grant này và dùng principal context ổn định không?
- Với nhiều replicas: Pod hiện tại có session/authorized-client state cần thiết không?
- Token có expired, revoked hoặc không refresh được không?

### Bước 5 — Xác minh outbound header tại backend stub

Không kiểm tra bằng cách dump raw token. Backend stub chỉ cần xác nhận:

~~~text
authorizationPresent=true
authorizationScheme=Bearer
tokenAudienceExpected=true (test token only)
routeId=catalog-service-token
~~~

Nếu `authorizationPresent=false`, kiểm tra TokenRelay có chạy và header có bị filter/edge strip không. Nếu header có nhưng backend 401, chuyển sang issuer/audience/expiry/JWKS. Nếu backend 403, kiểm tra scopes/roles/tenant/ownership.

### Bước 6 — Khôi phục theo nguyên nhân

| Nguyên nhân | Khôi phục phù hợp |
| --- | --- |
| Sai registration ID | Sửa route registration reference, test route startup |
| Thiếu OAuth2 Client dependency | Bổ sung đúng starter/BOM, kiểm tra filter factory |
| Client credentials grant/provider thiếu | Cấu hình manager/provider phù hợp, test token endpoint |
| Token endpoint unavailable | Kiểm tra DNS/TLS/network/IdP health; retry token acquisition có deadline |
| Authorized client/session mất | Khôi phục shared session/persistence và kiểm tra replicas |
| Header bị xóa sau TokenRelay | Sửa filter ownership/order và regression test backend stub |
| Audience/scope không khớp | Cấp token đúng resource/scope hoặc dùng token exchange/service identity |
| Backend JWKS stale | Khôi phục JWKS refresh/key rotation theo policy |
| Backend thiếu user ownership context | Thiết kế delegation/token exchange; không thêm header user giả |

**Không khôi phục bằng cách tắt JWT validation, cho tất cả routes `permitAll()`, bỏ audience check hoặc ghi token thật vào log.** Những thay đổi đó có thể biến sự cố khả dụng thành lỗ hổng xác thực.

## 19. Bảng triệu chứng → nguyên nhân → kiểm tra

| Triệu chứng | Nguyên nhân có thể | Kiểm tra ưu tiên |
| --- | --- | --- |
| Client nhận 401, backend HITS=0 | Gateway authentication thất bại | Resource Server decoder, session, `WWW-Authenticate` |
| Client nhận 403, backend HITS=0 | Gateway authorization/CSRF | Authority matcher, scope mapping, CSRF |
| Gateway 200 ở health nhưng route Catalog 401 | Health không yêu cầu auth; route private khác | Security rules và inbound token |
| Gateway nhận JWT hợp lệ nhưng backend không có Authorization | Resource Server không tạo OAuth2AuthorizedClient; TokenRelay không đúng flow | Principal type, registration và relay mode |
| `TokenRelay` không registration ID không relay token | Không có OAuth2 Login authorized client/session | `OAuth2AuthenticationToken`, authorized client repository |
| `TokenRelay=catalog-client` không relay | Registration ID sai hoặc manager không authorize | ClientRegistration, provider chain, token endpoint |
| Lỗi “client registration not found” | Route dùng sai ID hoặc profile thiếu registration | So sánh route filter và config runtime |
| Lỗi không có authorized client | Principal/registration association không tồn tại | Repository/service, principal name, session |
| Token endpoint trả `invalid_client` | Client ID/secret/auth method sai | IdP client config và secret injection |
| Token endpoint trả `invalid_scope` | Scope không được cấp/không hợp lệ | Registration scopes và IdP grant policy |
| Token endpoint timeout | DNS/TLS/IdP/network/connection timeout | Token endpoint transport metrics |
| Backend nhận request nhưng không có Authorization | TokenRelay không chạy hoặc header bị strip | Route match, filter order, edge/service mesh |
| Backend nhận hai Authorization values | `AddRequestHeader` hoặc custom filter append | Outbound header journal, thay bằng một owner |
| Backend 401 với Bearer có mặt | Expired/wrong issuer/audience/signature/JWKS | Claims đã redact, backend decoder, clock |
| Backend 403 với Bearer có mặt | Thiếu scope/role/tenant/resource permission | Authorization mapping/backend ownership |
| Token hợp lệ ở Gateway nhưng sai ở Catalog | Audience chỉ dành cho Gateway | `aud`, token exchange/OBO hoặc service token |
| Service token hoạt động nhưng user ownership sai | Backend chỉ thấy Gateway service principal | Delegation context/token exchange |
| Login hoạt động ở một Pod, Pod khác 401 | Session/authorized client chỉ lưu local | Shared session store, cookie, replica routing |
| Lỗi xuất hiện sau token expiry | Refresh/client credentials re-authorize không chạy | Manager provider, expiry, token endpoint |
| Lỗi sau IdP key rotation | Backend JWKS cache/refresh chậm | `kid`, JWKS refresh, signature error |
| Một route có token, route khác không | TokenRelay thiếu ở route thứ hai hoặc khác security flow | Route ID/filter list |
| Sau khi thêm RemoveRequestHeader thì 401 | Filter xóa Authorization outbound | Filter chain ordering và backend stub |
| Chỉ lỗi qua ingress, direct test chạy | Proxy strip header, forwarded scheme/session cookie | Edge config, trusted proxy, cookie attributes |
| Browser báo lỗi nhưng curl hoạt động | CORS preflight/credentials/SameSite | OPTIONS, CORS allow headers, cookie policy |
| Gateway trả 503 khi TokenRelay lấy token | Token endpoint/client manager exception được map thành error | Token endpoint outcome và Gateway exception |
| Backend không có HITS nhưng Gateway log route match | OAuth2 authorize/token acquisition hoặc outbound connect fail | Manager exception, DNS/TCP/TLS, outbound metrics |
| Backend HITS tăng nhiều lần cho một request | Retry nhiều tầng hoặc client retry | Attempts per inbound request, idempotency |
| Log không thấy Authorization nên nghĩ token mất | Logging policy redact header (đúng) | Backend boolean/scheme metric, không bật raw header logs |

## 20. Lệnh kiểm tra và quan sát an toàn

### 20.1. Gọi route có inbound Bearer token

~~~bash
# Chạy trong môi trường test; ACCESS_TOKEN phải được cấp qua secret-safe mechanism.
curl --silent --show-error -D - -o /dev/null \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  'https://gateway.lab.example.test/api/catalog/items/42'
~~~

Lệnh này chỉ in response headers/status, không in body; tuy vậy shell expansion và process environment vẫn phải được quản lý theo policy. Không dán production token vào chat, source code, CI output hoặc shell history. Dùng test token có audience/scope được cấp riêng.

### 20.2. Kiểm tra thiếu token và token sai scope

~~~bash
# Anonymous request: kỳ vọng 401 nếu route yêu cầu authentication.
curl --silent --show-error -D - -o /dev/null \
  'https://gateway.lab.example.test/api/catalog/private'

# Token test hợp lệ về chữ ký nhưng thiếu scope: kỳ vọng 403 theo policy.
curl --silent --show-error -D - -o /dev/null \
  -H "Authorization: Bearer ${READ_ONLY_TOKEN}" \
  'https://gateway.lab.example.test/api/orders'
~~~

Status kỳ vọng phụ thuộc security rules thật; đây là **lệnh kiểm tra**, không phải kết quả đã chạy. Nếu route không yêu cầu authentication hoặc backend tự tạo status, kết quả có thể khác; cần backend counter/trace để xác định tầng.

### 20.3. Kiểm tra TokenRelay service token bằng stub

Trong lab có backend stub được giới hạn network, gửi một GET qua Gateway và kiểm tra journal:

~~~text
routeId=catalog-service-token
inboundAuthenticated=true
oauth2RegistrationId=catalog-client
outboundAuthorizationPresent=true
outboundAuthorizationScheme=Bearer
backendRequestCount=1
~~~

Các giá trị trên là **metadata giả định**, không phải output thực. Không in raw `outboundAuthorization` vào terminal. Nếu backend không có token, xem TokenRelay manager/filter chain; nếu có token nhưng 401, xác minh claims/resource-server policy.

### 20.4. Logs và Actuator

- Dùng correlation ID và route ID để nối log giữa Gateway/upstream.
- Chỉ tăng log level OAuth2 Client/Spring Security trong **môi trường test hoặc thời gian ngắn được phê duyệt**, sau khi xác minh redaction.
- Không bật Netty wiretap/header dump ở production để đọc token.
- Chỉ expose health/metrics/route diagnostics cần thiết; bảo vệ Gateway Actuator bằng authentication và network isolation.
- Nếu dùng route listing endpoint của Actuator, nó có thể lộ URI/backend topology/filter configuration; không public endpoint đó.
- Metric labels chỉ dùng route ID, registration ID, upstream service và outcome hữu hạn; không dùng user ID, raw URL/query hoặc JWT.

### 20.5. Không nhầm token endpoint lỗi với backend lỗi

OAuth2 Client có thể gọi IdP **trước khi** gọi Catalog. Khi token endpoint timeout hoặc trả `invalid_client`, Catalog HITS có thể bằng 0. Đừng tăng timeout Catalog hoặc sửa backend JWT decoder trong trường hợp này. Theo dõi riêng:

- Token endpoint request count/status/duration.
- OAuth2 client authorization success/failure.
- Gateway outbound Catalog attempts.
- Catalog inbound count/status.

Đây là bốn nguồn bằng chứng khác nhau.

## 21. Phân tích một sự cố mẫu từ đầu đến cuối

### Tình huống

Một API private Catalog bắt đầu trả 401 sau khi đội vận hành đổi Gateway sang:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog
              uri: https://catalog.internal.example:8443
              predicates:
                - Path=/api/catalog/**
              filters:
                - StripPrefix=2
                - TokenRelay
~~~

Client gửi Bearer JWT hợp lệ. Spring Security Gateway xác minh JWT thành công, route ID `catalog` được chọn, nhưng Catalog log:

~~~text
401 invalid_token: missing bearer credentials
~~~

### Quan sát ban đầu

| Tầng | Bằng chứng giả định |
| --- | --- |
| Client → Gateway | Bearer JWT có mặt, Gateway trả status 401 |
| Spring Security inbound | JWT signature/issuer/audience gateway-api hợp lệ |
| Gateway route | Route `catalog` match |
| Gateway outbound | HTTP attempt có xảy ra |
| Catalog | HITS=1, không có Authorization header |

Vì backend HITS=1 và inbound Security đã thành công, lỗi **không phải Gateway từ chối JWT**. Token đã không được chuyển tiếp.

### Phân tích nguyên nhân

Route đang dùng `TokenRelay` không có registration ID. Nhóm giả định filter này sẽ copy raw inbound Bearer JWT. Nhưng Gateway được cấu hình **Resource Server**, không có OAuth2 Login/authorized client tương ứng với user. TokenRelay không có authorized client để relay.

### Chọn giải pháp theo yêu cầu backend

**Trường hợp A — Catalog chỉ cần xác thực Gateway service:**

1. Thêm OAuth2 Client registration `catalog-client` với grant `client_credentials`.
2. Cấu hình `TokenRelay=catalog-client`.
3. Giữ inbound Resource Server scope `catalog.proxy`.
4. Cấp cho service client scope `catalog.read`.
5. Catalog xác thực service identity và thực hiện policy user/tenant qua cơ chế delegation riêng nếu nghiệp vụ cần.

**Trường hợp B — Catalog phải biết user cuối:**

1. Kiểm tra token inbound có audience/scope dành cho Catalog không.
2. Nếu không, IdP phải hỗ trợ Token Exchange/OBO hoặc một flow delegation khác.
3. Gateway lấy downstream token có audience/scope Catalog.
4. Catalog xác minh downstream token và kiểm tra resource ownership.

Không chọn client credentials rồi thêm `X-User-Id` từ request để thay user authorization.

### Kết quả sau khi sửa (kỳ vọng trong lab)

~~~text
Gateway inbound authenticated=true
Gateway routeId=catalog
oauth2RegistrationId=catalog-client
tokenAcquisition=success
Catalog authorizationPresent=true
Catalog authorizationScheme=Bearer
Catalog response=200
~~~

Các dòng trên là **kết quả mục tiêu minh họa**, không phải log từ một ứng dụng đã chạy. Trong production, ghi metadata đã redact, không in token.

## 22. Ma trận kiểm thử trước khi sửa lỗi hoặc triển khai TokenRelay

| ID | Kịch bản | Bằng chứng cần có |
| --- | --- | --- |
| A01 | Anonymous gọi route yêu cầu auth | 401/deny theo contract, backend HITS=0 |
| A02 | JWT sai chữ ký | Gateway từ chối, backend HITS=0 |
| A03 | JWT sai issuer | Gateway từ chối, backend HITS=0 |
| A04 | JWT sai audience Gateway | Gateway từ chối, backend HITS=0 |
| A05 | JWT hết hạn | Gateway từ chối hoặc refresh theo flow đã thiết kế |
| A06 | JWT đúng issuer/audience nhưng thiếu scope | 403 tại Gateway, backend HITS=0 |
| A07 | User OAuth2 Login có authorized client | TokenRelay no-arg gửi user access token |
| A08 | User chưa login | Redirect/login challenge hoặc lỗi theo policy; không gửi token rỗng |
| A09 | Session hết hạn | Không dùng authorized client cũ trái policy |
| A10 | Authorized client không tồn tại | Filter/manager failure rõ; backend HITS=0 |
| A11 | ClientRegistration ID sai | Không lấy được token; backend HITS=0 |
| A12 | Client credentials token endpoint thành công | Backend nhận service Bearer token |
| A13 | Token endpoint invalid_client | Backend HITS=0 |
| A14 | Token endpoint invalid_scope | Backend HITS=0 |
| A15 | Token endpoint timeout | Request dừng trong deadline |
| A16 | Client secret rotation | Token acquisition phục hồi với secret mới |
| A17 | Access token hết hạn | Manager re-authorize/refresh theo grant |
| A18 | Custom manager thiếu provider | Test phát hiện flow tương ứng không hoạt động |
| A19 | Route filter RemoveRequestHeader xóa Authorization | Backend journal phát hiện header vắng |
| A20 | Custom GlobalFilter strip Authorization | Regression test phát hiện header bị mất |
| A21 | Edge/service mesh strip Authorization | E2E phát hiện khác biệt trước/sau proxy |
| A22 | Backend trả 401 vì audience sai | Gateway outbound token có mặt; backend policy từ chối |
| A23 | Backend trả 403 vì thiếu scope | Token hợp lệ, authorization từ chối |
| A24 | Backend kiểm tra tenant/ownership | User không sở hữu resource nhận 403 |
| A25 | User token relay qua hai Gateway replicas | Session/authorized client tồn tại ở cả hai Pod |
| A26 | Client credentials qua nhiều replicas | Token manager/cache hoạt động, không gọi IdP quá mức |
| A27 | Token key rotation/JWKS refresh | Không bỏ signature verification |
| A28 | Retry khi backend 401/403 | Không retry vô hạn hoặc đổi identity |
| A29 | Response 401 từ backend | Client status/provenance được phân biệt với Gateway 401 |
| A30 | Logs/traces/metrics | Không lộ token, secret, cookie hoặc PII |

### Cách tổ chức test

- **Unit/security tests:** authentication, authorization, scope mapping và CSRF.
- **OAuth2 client tests:** registration, grant provider, token endpoint response/error, authorized-client persistence.
- **Gateway HTTP integration tests:** route filter, TokenRelay, path/header và backend stub.
- **E2E qua edge/mesh:** header forwarding, TLS/mTLS, cookies, sessions và status provenance.
- **Multi-replica tests:** shared session, token cache, rolling restart và configuration drift.

Không coi một WebTestClient với mock authentication là bằng chứng token endpoint hoặc outbound HTTP thực sự đã chạy. Dùng **HTTP test double có request journal** khi cần chứng minh TokenRelay gửi credentials tới backend.

## 23. Bài thực hành: điều tra TokenRelay không gửi token

**Bối cảnh:** Gateway Server WebFlux nhận inbound JWT có scope `catalog.proxy`. Catalog yêu cầu access token có audience `catalog-api` và scope `catalog.read`. Route đang dùng `TokenRelay` không có registration ID; backend trả 401 vì không có Bearer header.

### Phần A — Dựng môi trường test

1. Tạo một Gateway Server WebFlux application với Spring Boot/Spring Cloud BOM tương thích.
2. Thêm OAuth2 Client starter; thêm Resource Server starter nếu cần xác minh inbound JWT.
3. Dựng token endpoint stub trả access token giả có scope `catalog.read`.
4. Dựng Catalog HTTP stub ghi `authorizationPresent`, `authorizationScheme`, request count, method/path/query; không lưu raw token.
5. Cấu hình Gateway chạy trên port ngẫu nhiên và inject URI của token stub/backend stub qua test properties.
6. Chỉ dùng token giả và test keys; không gọi IdP hoặc backend production.

### Phần B — Tái hiện lỗi

1. Cấu hình Gateway chỉ là Resource Server nhận JWT inbound.
2. Để route dùng `TokenRelay` không registration ID.
3. Gửi một JWT test hợp lệ cho audience `gateway-api`.
4. Xác minh Gateway security chấp nhận và route match.
5. Kiểm tra Catalog stub: request có tới nhưng Authorization header vắng theo setup tái hiện.
6. Ghi lại status cuối và backend counter; không log token.

### Phần C — Chọn mô hình service token

1. Thêm registration `catalog-client` với `client_credentials`, client secret giả và scope `catalog.read`.
2. Cấu hình route thành `TokenRelay=catalog-client`.
3. Bảo đảm Security WebFilterChain vẫn yêu cầu inbound scope `catalog.proxy`.
4. Gửi cùng inbound JWT test.
5. Xác minh token endpoint stub được gọi và Catalog stub nhận Bearer token giả.
6. Xác minh token được reuse theo lifecycle/expiry policy và không gọi token endpoint vô hạn.
7. Cho token endpoint trả `invalid_client`; Catalog HITS phải bằng 0.

### Phần D — Thử mô hình user delegation

1. Giữ một route test riêng dùng OAuth2 Login Authorization Code.
2. Tạo user test và authorized client có access token giả dành cho Catalog.
3. Dùng TokenRelay không registration ID.
4. Xác minh backend nhận token gắn với user test, không phải service token.
5. Xóa/expire session và kiểm tra hành vi khi authorized client không còn.
6. Chạy qua hai Gateway replicas với session store phù hợp, kiểm tra Pod B đọc được state của Pod A.

### Phần E — Tìm filter làm mất header

1. Thêm test route filter `RemoveRequestHeader=Authorization` trong sandbox.
2. Gửi request và quan sát backend stub báo `authorizationPresent=false`.
3. Thử custom `SetRequestHeader` hoặc `AddRequestHeader` và ghi nhận behavior/duplicate values.
4. Bỏ filter xung đột, chỉ để TokenRelay quản lý outbound Authorization.
5. Lặp test và chứng minh backend nhận đúng Bearer scheme.
6. Không bật raw header logging hoặc wiretap chứa credentials.

### Phần F — Phân loại status

1. Anonymous inbound → kiểm tra 401/entry point và backend HITS=0.
2. Authenticated nhưng thiếu scope inbound → kiểm tra 403 và backend HITS=0.
3. Inbound hợp lệ, token endpoint lỗi → kiểm tra token acquisition failure, backend HITS=0.
4. Inbound hợp lệ, outbound token sai audience → backend nhận token và trả 401.
5. Outbound token đúng audience nhưng thiếu scope → backend trả 403.
6. Outbound token đúng nhưng user không sở hữu resource → backend trả 403 theo ownership policy.

### Phiếu nghiệm thu

| Hạng mục | Bằng chứng |
| --- | --- |
| OAuth2 roles | Giải thích Resource Server khác OAuth2 Client/Login |
| Token source | Xác định user token, service token hoặc token exchange |
| Registration | Đúng ID, provider, grant, client auth method và scopes |
| Authorized client | Principal/repository/session đúng |
| Filter chain | Không có filter xóa/ghi đè Authorization ngoài ý muốn |
| Backend | Có Bearer header, đúng issuer/audience/scope, không log raw token |
| Status | Phân biệt 401/403 của Gateway và upstream |
| Security | Không bypass auth, không dùng header giả làm identity |
| Multi-replica | Session/token lifecycle ổn định |
| Recovery | Có runbook và negative tests |

**Tiêu chí đạt:** Người học chứng minh được **TokenRelay lấy token từ đúng nguồn, gửi token phù hợp tới đúng backend, và phân biệt được lỗi xác thực inbound với lỗi token/authorization ở upstream**.

## 24. Những phản mẫu cần tránh

| Phản mẫu | Vì sao sai/rủi ro | Thay bằng |
| --- | --- | --- |
| Thấy 401 là sửa JWT decoder ngay | 401 có thể do backend hoặc token endpoint | Xác định response provenance bằng counters/traces |
| Thấy 403 là thêm `ROLE_ADMIN` | Có thể che lỗi scope/tenant/ownership | Kiểm tra policy tạo 403 và test authority cụ thể |
| Chỉ bật Resource Server rồi dùng TokenRelay no-arg | Inbound JWT không tự là OAuth2AuthorizedClient | Chọn service token, user OAuth2 client hoặc token exchange |
| Cho rằng TokenRelay copy mọi inbound Authorization | TokenRelay lấy token qua OAuth2 Client manager/authorized client | Xác định nguồn token và registration |
| Dùng ID token làm Bearer access token | Sai mục đích/audience | Dùng access token dành cho resource server |
| Forward refresh token tới backend | Lộ credentials có quyền lấy token mới | Chỉ gửi access token phù hợp |
| Dùng client_credentials rồi tin backend biết user | Backend chỉ thấy service principal | Token exchange/delegation + ownership checks |
| Dùng `AddRequestHeader=Authorization` | Có thể tạo duplicate Authorization | Để TokenRelay quản lý một Bearer header |
| Đặt `RemoveRequestHeader=Authorization` sau TokenRelay | Xóa token outbound | Xác minh filter ordering và bỏ filter xung đột |
| Hardcode Bearer token trong YAML | Lộ secret, token hết hạn, không rotation | OAuth2 Client registration/secret manager |
| Tự viết static token cache | Concurrency, expiry, principal mix-up, rotation lỗi | Authorized client manager/repository/service |
| Bỏ audience verification ở backend | Token của API khác có thể được chấp nhận | Cấp đúng audience hoặc token exchange |
| Thêm scope mọi quyền để sửa 403 | Vi phạm least privilege | Cấp scope tối thiểu theo route/resource |
| Tắt CSRF cho browser session | Tạo lỗ hổng CSRF | Phân biệt cookie/session và Bearer-only API |
| `permitAll()` toàn bộ route | Bỏ kiểm soát authentication/authorization | Matcher theo route/method/scope |
| Copy raw Authorization sang mọi upstream | Token exfiltration và confused deputy | Allowlist upstream, audience policy, token exchange |
| Log raw token để debug | Rò access/refresh credentials | Backend boolean/scheme, redacted metadata |
| Tin X-User-Id do client gửi | Giả mạo principal/tenant | Identity từ token đã xác minh hoặc signed delegation |
| Thấy backend HITS=0 là kết luận Security chặn | Có thể route miss, token endpoint fail, DNS/TCP fail | Route outcome + OAuth2 manager + transport metrics |
| Thấy status 401 là kết luận TokenRelay không chạy | Backend có thể trả 401 dù token có mặt | Kiểm tra Authorization presence và backend validation |
| Dùng mock JWT test để khẳng định signature/issuer đúng | Mock authentication bỏ qua decoder thật | Signed test JWT qua HTTP integration test |
| Chỉ test một Gateway Pod | Không phát hiện session/config drift | Multi-replica tests và per-Pod metrics |
| Bật wiretap/header dump production | Có thể log token/cookie/PII | Instrumentation an toàn, test stub, temporary approved logs |

## 25. Checklist trước khi merge thay đổi OAuth2/TokenRelay

~~~text
[ ] Đã xác định Gateway Server WebFlux hay Web MVC.
[ ] Spring Boot/Spring Cloud BOM và OAuth2 Client starter tương thích.
[ ] Đã xác định inbound flow: OAuth2 Login hay Resource Server.
[ ] Đã xác định downstream identity: user token, service token hay token exchange.
[ ] TokenRelay no-arg chỉ dùng khi authorized client của user đã tồn tại.
[ ] TokenRelay=registrationId trùng ClientRegistration ID chính xác.
[ ] Registration có provider, token URI/issuer, grant type và scopes đúng.
[ ] Custom OAuth2AuthorizedClientManager hỗ trợ grant cần thiết.
[ ] Authorized-client repository/service và principal context đúng.
[ ] Session/authorized client persistence hoạt động giữa các replicas nếu cần.
[ ] Access token có issuer, audience, expiry và scopes đúng cho backend.
[ ] ID token/refresh token không bị gửi tới resource server.
[ ] Backend vẫn xác thực token và kiểm tra tenant/resource ownership.
[ ] Không có filter xóa/ghi đè/append Authorization ngoài ý muốn.
[ ] Backend stub chứng minh Authorization present và scheme Bearer.
[ ] Không log raw token, secret, cookie, session ID hoặc PII.
[ ] Có tests cho 401/403 inbound và upstream, token endpoint errors.
[ ] Có tests cho token expiry, refresh/re-authorize và secret rotation.
[ ] Có tests cho filter ordering, edge header stripping và multi-replica.
[ ] Actuator/route diagnostics được bảo vệ.
[ ] Retry có giới hạn, không lặp thao tác side effect thiếu idempotency.
[ ] Có runbook xác định status provenance và recovery path.
~~~

## 26. Tổng kết

- **401 và 403 không cùng một nguyên nhân.** 401 thường liên quan credentials không được chấp nhận; 403 thường là principal đã xác thực nhưng không đủ quyền. Cả Gateway, edge proxy và upstream backend đều có thể tạo status này, vì vậy phải xác định **response provenance**.
- **OAuth2 Client, OAuth2 Login và OAuth2 Resource Server là các vai trò khác nhau.** Resource Server xác minh inbound Bearer token; OAuth2 Client quản lý registration/authorized client/token cho outbound call; OAuth2 Login tạo session và authorized client gắn với user.
- **TokenRelay là OAuth2 Client Gateway filter**, không phải raw Authorization header copier. Dạng không có registration ID dùng authorized client gắn với user đã OAuth2 login; dạng `TokenRelay=registrationId` dùng registration được chỉ định, thường phù hợp client credentials.
- **Inbound JWT hợp lệ không tự tạo OAuth2AuthorizedClient.** Nếu Gateway chỉ là Resource Server, TokenRelay no-arg không mặc nhiên relay token inbound. Hãy chọn user OAuth2 login, service token, token exchange/OBO hoặc pass-through được thiết kế và bảo vệ rõ ràng.
- **Service token khác user token.** `client_credentials` đại diện Gateway service; backend không tự biết user/tenant cuối. Nếu cần user-level authorization, cần delegation/token exchange hoặc một context được xác thực, và backend vẫn kiểm tra ownership.
- **Token đúng phải dành cho đúng resource server.** Issuer, audience, expiration, not-before, signing key và scopes/roles phải đáp ứng policy của Catalog/Orders. Token được Gateway chấp nhận chưa chắc được backend chấp nhận.
- **Authorized client lifecycle quan trọng.** Registration ID, principal, manager provider chain, repository/service, token expiry/refresh, session persistence và replica behavior đều có thể khiến TokenRelay không lấy được token.
- **Filter chain có thể làm mất token.** `RemoveRequestHeader`, `SetRequestHeader`, `AddRequestHeader`, GlobalFilter, edge proxy hoặc service mesh có thể strip/overwrite Authorization. Chứng minh header tới backend bằng stub an toàn, không log raw token.
- **Kiểm thử phải có hai phía.** Security tests chứng minh 401/403 inbound; OAuth2 client tests chứng minh token acquisition; HTTP integration tests chứng minh outbound Bearer header và backend response. Không chỉ assert status 200.
- **Khôi phục an toàn giữ nguyên trust boundary.** Không tắt signature/audience validation, không mở `permitAll()`, không forward refresh token, không hardcode access token và không dùng header client gửi làm principal.

Một hệ thống **SPRING_CLOUD_GATEWAY** hoạt động đúng với TokenRelay phải trả lời được bốn câu hỏi: **ai đã được xác thực ở inbound, Gateway lấy access token từ đâu, backend nào được phép nhận token đó và backend có quyền gì khi nhận token?** Khi bốn câu trả lời rõ ràng và có test chứng minh, lỗi 401/403 sẽ được khoanh vùng đúng tầng mà không cần hạ thấp bảo mật.

### Tài liệu tham khảo để đối chiếu phiên bản

- **Spring Cloud Gateway Reference — TokenRelay GatewayFilter:** https://docs.spring.io/spring-cloud-gateway/reference/
- **Spring Security OAuth2 Client:** https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- **Spring Security Reactive OAuth2 Resource Server:** https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security OAuth2 Login:** https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- **HTTP Semantics, RFC 9110** (401/403, WWW-Authenticate): https://www.rfc-editor.org/rfc/rfc9110
- **OAuth 2.0 Bearer Token Usage, RFC 6750:** https://www.rfc-editor.org/rfc/rfc6750
- **OAuth 2.0 Token Exchange, RFC 8693:** https://www.rfc-editor.org/rfc/rfc8693

Đối chiếu **Spring Boot, Spring Cloud Gateway, Spring Security và IdP versions** đang chạy trước khi chép property/API. Các YAML/Java trong bài là ví dụ WebFlux để học và kiểm thử; bài chưa thay cho integration test trên hệ thống thật hoặc vòng Content QA chuyên môn STEP 6.
