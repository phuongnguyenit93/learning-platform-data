# Bảo vệ REST API bằng Microsoft Entra access token

Một ứng dụng Spring Boot triển khai trên **Azure App Service**, **Azure Container Apps** hoặc **Azure Kubernetes Service (AKS)** có REST API quản lý đơn hàng. Frontend đăng nhập bằng tài khoản doanh nghiệp qua **Microsoft Entra ID** rồi gửi request đến `GET /api/orders`. Nếu backend chỉ kiểm tra xem header `Authorization` có chứa một chuỗi bắt đầu bằng `Bearer` hay không, kẻ tấn công có thể tự gửi chuỗi giả và đọc dữ liệu. Nếu backend chỉ giải mã nội dung JWT mà không kiểm tra chữ ký, issuer, audience và quyền, token dành cho dịch vụ khác cũng có thể bị sử dụng sai mục đích.

**Bảo vệ REST API bằng Microsoft Entra access token** nghĩa là Spring Boot đóng vai trò **OAuth 2.0 Resource Server**: tiếp nhận access token, xác minh token được phát hành bởi hệ thống danh tính tin cậy **cho đúng API**, kiểm tra thời hạn và các claims bắt buộc, sau đó thực thi **authorization** theo scope, app role và quyền sở hữu dữ liệu. Một token hợp lệ về mặt mật mã **không tự động cho phép** người gọi đọc mọi tài nguyên.

Bài thuộc chương **Spring Boot trên Azure** của module **CLOUD_PROVIDERS_AZURE**, gắn với hành trình học Azure từ subscription, resource group, Microsoft Entra ID, mạng ảo, compute, storage tới triển khai, giám sát, bảo vệ và kiểm soát chi phí. Ví dụ sử dụng **Java 17+, Spring Boot 3.x, Spring Security 6 và OAuth2 Resource Server**. Tên property, dependency, API và khả năng token authentication cần được kiểm tra theo phiên bản thực tế; không lưu secret hoặc access token thật trong source code, log hay bài thực hành.

> **Phạm vi:** bài tập trung vào **Microsoft Entra ID workforce tenant** và **JWT access token cho API do tổ chức đăng ký**. Microsoft Entra External ID, B2C legacy, token đặc thù của Microsoft Graph, token tùy loại tenant và những endpoint có cấu hình claims khác có thể yêu cầu cơ chế xác thực riêng. Không giả định mọi access token đều có thể được frontend tự giải mã hoặc đều có cùng tập claims.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **OAuth 2.0**, **OpenID Connect**, **access token**, **ID token** và **refresh token**.
2. Mô tả quy trình đăng ký **API app registration**, khai báo **delegated scopes** và **application app roles** trong Microsoft Entra ID.
3. Giải thích **Authorization Code + PKCE**, **client credentials** và trường hợp dùng **On-Behalf-Of (OBO)**.
4. Cấu hình Spring Boot thành **OAuth2 Resource Server** để validate chữ ký JWT qua OpenID Connect/JWKS.
5. Kiểm tra chính xác **issuer (`iss`), audience (`aud`), expiration (`exp`), not-before (`nbf`), tenant (`tid`)** và các claims liên quan.
6. Ánh xạ `scp` thành quyền `SCOPE_*`, `roles` thành quyền `ROLE_*` và dùng method security.
7. Phân biệt **401 Unauthorized** với **403 Forbidden** và thiết kế API authorization theo từng endpoint.
8. Áp dụng **tenant isolation** và kiểm tra ownership ở tầng dữ liệu, không chỉ dựa vào một scope chung.
9. Viết test cho token hợp lệ, sai audience/issuer, hết hạn, thiếu scope/role và truy cập chéo tenant.
10. Triển khai có kiểm soát trên Azure, bảo vệ secret, quan sát lỗi bảo mật và xây runbook sự cố.

## 2. Mô hình bảo mật: ai cấp token, ai kiểm tra?

~~~mermaid
sequenceDiagram
  participant U as Người dùng
  participant C as Frontend / Client
  participant E as Microsoft Entra ID
  participant A as Spring Boot REST API
  participant D as Database
  U->>C: Chọn đăng nhập
  C->>E: OAuth Authorization Code + PKCE
  E-->>C: Access token cho API đã được cho phép
  C->>A: GET /api/orders + Authorization Bearer
  A->>E: Lấy OpenID metadata/JWKS khi cần
  E-->>A: Public signing keys / metadata
  A->>A: Verify signature, issuer, audience, time
  A->>A: Check scope/role và tenant
  A->>D: Query dữ liệu theo identity và quyền
  D-->>A: Các đơn hàng được phép
  A-->>C: 200 với dữ liệu đã lọc
~~~

Các vai trò:

| Vai trò | Trong ví dụ | Trách nhiệm |
|---|---|---|
| **Resource Owner** | Người dùng doanh nghiệp | Cho phép client truy cập trong phạm vi phù hợp |
| **Client** | SPA/mobile/backend | Yêu cầu access token và gọi API |
| **Authorization Server** | Microsoft Entra ID | Xác thực principal, cấp token sau policy/consent |
| **Resource Server** | Spring Boot REST API | Validate token và quyết định quyền truy cập dữ liệu |
| **Downstream resource** | Azure SQL/Cosmos DB/Graph | Có authentication/authorization riêng |

**Spring Boot API không nên tin kết quả “frontend đã đăng nhập”.** Mỗi request mang token phải được resource server xác minh theo policy; frontend không phải boundary đáng tin cậy.

### JWT signature verification thường không cần gọi Entra cho từng request

Với JWT access token được API chấp nhận, resource server thường tải **public keys từ JWKS endpoint**, cache keys theo HTTP/SDK behavior và tự xác minh chữ ký. Nó không cần gọi Entra ID để introspect mỗi token. Tuy nhiên:

- Có network/metadata dependency lúc khởi động hoặc key refresh.
- Phải xử lý key rotation và cache hợp lý.
- JWT verification offline không tự cung cấp thu hồi token tức thời.
- Một số token không phải JWT hoặc API dạng khác cần cơ chế xác minh khác.

## 3. OAuth 2.0 khác OpenID Connect ở đâu?

**OAuth 2.0** chủ yếu là khung ủy quyền: một client nhận **access token** để gọi resource/API trong phạm vi được cấp. **OpenID Connect (OIDC)** mở rộng OAuth để xác thực danh tính người dùng với **ID token** và identity claims.

| Token | Đối tượng sử dụng | Mục đích |
|---|---|---|
| **Access token** | Resource server/API mà token ghi ở `aud` | Cho phép gọi API với scopes/roles cụ thể |
| **ID token** | **Client application** có client ID là audience | Cho client biết việc đăng nhập/người dùng đã được xác thực |
| **Refresh token** | OAuth client được phép giữ token | Xin access token mới theo session/policy |
| **Client credentials access token** | API downstream | Gọi API dưới danh tính ứng dụng, không đại diện user |

Sai lầm nghiêm trọng: **API nhận ID token làm Bearer token**. ID token thường có `aud` của frontend/client, không phải audience của REST API. API phải yêu cầu **access token dành riêng cho chính nó**, không đổi mục đích ID token chỉ vì payload có `name` hoặc `email`.

### ID token không chứng minh quyền gọi API

Người dùng đăng nhập thành công chỉ nói rằng họ được Entra xác thực theo luồng client. Họ vẫn có thể:

- Không được cấp delegated scope cho API.
- Không có app role cần thiết.
- Không thuộc tenant được phép.
- Không có quyền xem bản ghi cụ thể trong database.
- Đang ở tình huống bị chính sách tổ chức từ chối truy cập.

**Authentication** trả lời “principal là ai”; **authorization** trả lời “principal có được phép thực hiện hành động này đối với resource này không”.

## 4. Ba luồng nhận access token quan trọng

| Luồng | Khi nào dùng | Có user? | Quyền thường thấy |
|---|---|---|---|
| **Authorization Code + PKCE** | SPA/mobile/native app đăng nhập user | Có | Delegated scopes trong `scp` |
| **Client Credentials** | Daemon/job/service-to-service | Không | Application permissions/app roles trong `roles` |
| **On-Behalf-Of (OBO)** | API A cần gọi API B thay mặt user | Có | Delegated permissions dành cho API B |

### Authorization Code + PKCE

Client đăng nhập qua browser/redirect, bảo vệ authorization code bằng **PKCE**, rồi yêu cầu access token có scope của API, ví dụ `api://<API_APP_ID>/Orders.Read`. Với SPA, không nhúng client secret vì SPA là public client. Dùng MSAL hoặc OAuth/OIDC client library được hỗ trợ thay vì tự ghép token endpoints.

### Client Credentials

Background job lấy access token với **application identity** đã được quản trị; thông thường dùng scope `api://<API_APP_ID>/.default` và quyền ứng dụng đã được quản trị viên cấp consent/assignment. Token app-only **không có người dùng** để đặt thuộc tính `currentUserEmail`.

### On-Behalf-Of

Nếu Java API A đã nhận access token dành cho **A** rồi phải gọi API B thay mặt user, không gửi thẳng token `aud=A` sang B. API A dùng **OBO flow** để xin token mới `aud=B` với delegated permissions phù hợp. Với API gọi Microsoft Graph, cần Graph access token thay vì token của API A.

## 5. Microsoft Entra app registrations: API và client

Có thể phân tách thành **hai app registrations** để boundary rõ ràng.

### A. Đăng ký REST API

Trong tenant được cấp quyền:

1. Vào Microsoft Entra admin center, mục **App registrations**.
2. Tạo ứng dụng, ví dụ `orders-api-dev`.
3. Ghi lại **Application (client) ID** của API và **Directory (tenant) ID**. Đây là identifiers, không phải secrets.
4. Chọn **Supported account types** phù hợp (bài lab dùng **single tenant**).
5. Mở **Expose an API**, cấu hình **Application ID URI**, ví dụ `api://<API_APP_ID>`.
6. Định nghĩa delegated scopes như `Orders.Read`, `Orders.Write`; ghi rõ ai có thể consent và mô tả.
7. Nếu cần service-to-service, tạo **App roles** dành cho applications, ví dụ `Orders.Read.All` hoặc `Jobs.Run`; quản lý value/allowed member types.
8. Cấu hình token version mong muốn và claims phù hợp app manifest/schema, đặc biệt khi dùng v2 issuer.
9. Thiết lập owners, publisher, enterprise app settings và chính sách cấp quyền.
10. Ghi tài liệu về audience kỳ vọng, issuer tenant, scopes, roles và owner.

**Scope và role là quyền logic bạn định nghĩa**; chỉ tạo tên không tự bảo đảm người dùng/app đã được cấp quyền. Cần client request scopes và consent, hoặc app-role assignment/admin consent tùy tình huống.

### B. Đăng ký frontend/consumer client

1. Tạo app registration riêng, ví dụ `orders-spa-dev`.
2. Chọn loại client và redirect URI đúng nền tảng.
3. Với SPA, sử dụng **authorization code + PKCE** và MSAL; không cấp client secret cho JavaScript chạy trong browser.
4. Trong **API permissions**, thêm delegated permission `Orders.Read`/`Orders.Write` do API đã expose.
5. Thực hiện user/admin consent theo tenant policy.
6. Cấu hình client dùng authority tenant cụ thể và scope đầy đủ.
7. Đảm bảo frontend gọi API kèm **access token**, không phải ID token.

### C. Service client

Đối với daemon app, cần application permission/app role tương ứng được gán và được cấp consent/assignment đúng. Không giả định client credentials request có `scp`; token app-only thường thể hiện role trong `roles`. Có trường hợp access token app-only không mang role khi API/resource cho phép kiểu authorization theo ACL; nếu API của bạn yêu cầu roles, **phải từ chối token không có role** thay vì coi sự vắng mặt là quyền hợp lệ.

### Tại sao có Application ID URI?

Scope string thường có dạng `api://<API_APP_ID>/Orders.Read`, nhưng access token `aud` không nhất thiết là nguyên chuỗi scope. Trong nhiều cấu hình v2 access token, audience là **client ID của API**; trong một số token/version/API config có thể là **Application ID URI**. Chọn giá trị audience theo **token contract và cấu hình API thực tế**, không lấy scope đầy đủ làm `aud`.

## 6. Access token v1/v2 và việc chọn issuer

Microsoft Entra có các định dạng access token **v1.0** và **v2.0**. Phiên bản access token phụ thuộc đáng kể vào cấu hình **resource/API app** nhận token, không chỉ việc client sử dụng `/oauth2/v2.0/authorize`.

| Token format | Ví dụ issuer thường gặp | Điều kiện |
|---|---|---|
| v2.0 | `https://login.microsoftonline.com/<TENANT_ID>/v2.0` | API cấu hình chấp nhận v2 access tokens |
| v1.0 | `https://sts.windows.net/<TENANT_ID>/` | API/resource đang sử dụng v1 token format |

Bài lab dùng **v2, single tenant** và issuer `https://login.microsoftonline.com/<TENANT_ID>/v2.0`. Nếu token thực có `ver=1.0`, issuer và audience sẽ khác expectations v2: **đừng tắt issuer validation để “cho qua”**. Kiểm tra app registration setting liên quan `requestedAccessTokenVersion`/định dạng token và xin lại token phù hợp.

### Không dùng `/common` làm issuer cố định cho mọi token

`/common` hoặc `/organizations` là authority dành cho quá trình đăng nhập của nhiều tenant trong những tình huống được hỗ trợ. Access token thường có **issuer gắn tenant cụ thể**, nên không dùng URL `/common` làm expected `iss` một cách mù quáng. Đối với multi-tenant API cần resolver/allowlist tin cậy theo issuer và tenant thực tế, không biến tất cả issuers hợp lệ về mặt chữ ký thành tenants được quyền truy cập.

## 7. Giải thích các JWT claims thiết yếu

JWT thường có ba phần: `header.payload.signature`, được mã hóa theo Base64url. Có thể **decode** hai phần đầu để quan sát, nhưng decode **không phải verify**.

Ví dụ payload **minh họa, không phải token thật**:

~~~json
{
  "ver": "2.0",
  "iss": "https://login.microsoftonline.com/<TENANT_ID>/v2.0",
  "aud": "<API_APP_CLIENT_ID>",
  "tid": "<TENANT_ID>",
  "oid": "<USER_OBJECT_ID>",
  "sub": "<PAIRWISE_SUBJECT>",
  "azp": "<CLIENT_APP_ID>",
  "scp": "Orders.Read Orders.Write",
  "iat": 1795160000,
  "nbf": 1795160000,
  "exp": 1795163600
}
~~~

| Claim | Diễn giải | Kiểm tra/ứng dụng |
|---|---|---|
| `iss` | Issuer | Khớp issuer tenant/phiên bản tin cậy |
| `aud` | Audience | Phải chứa đúng định danh resource/API được cấu hình |
| `exp` | Hết hạn | Từ chối token quá hạn theo clock skew policy |
| `nbf` | Có hiệu lực từ | Từ chối token chưa đến hiệu lực |
| `iat` | Thời điểm phát hành | Hữu ích cho telemetry/policy, không phải quyền |
| `ver` | Phiên bản định dạng token | Chọn issuer/claim mappings đúng |
| `tid` | Tenant ID | Hỗ trợ tenant allowlist và data partition |
| `oid` | Object ID của principal trong tenant | Identity key thích hợp cho nhiều truy vấn dữ liệu |
| `sub` | Subject/pairwise identifier | Không giả định bằng email hay `oid` |
| `scp` | Delegated scopes, chuỗi cách bằng space | Ánh xạ `SCOPE_Orders.Read` |
| `roles` | App roles hoặc quyền được gán | Ánh xạ `ROLE_Jobs.Run` |
| `azp` | Authorized party/client app ID (thường v2) | Client allowlist khi chính sách yêu cầu |
| `appid` | Client app ID ở một số v1 tokens | Không mặc định xuất hiện ở v2 |
| `groups` | Groups nếu phát hành vào token | Có giới hạn kích thước/group overage |

### Các claims **không** nên làm khóa phân quyền bền vững

`name`, `preferred_username` và `email` có thể đổi, thiếu hoặc không đảm bảo unique. **Không dùng email làm primary authorization key** trong hệ multi-tenant. Nếu có user identity, sử dụng cặp `(tid, oid)` theo hợp đồng danh tính; dữ liệu thực vẫn phải có authorization logic riêng.

### Không tin claims trước khi verify

Bất kỳ ai cũng có thể tạo JSON `{"roles":["Admin"]}` rồi Base64url-encode thành payload. Chỉ sau khi signature, issuer, audience, time và thuật toán được xác minh từ trusted keys, claims mới có giá trị để áp dụng chính sách.

## 8. Chuỗi bảo vệ một request phải đầy đủ

~~~mermaid
flowchart TD
  R["HTTP Authorization: Bearer token"] --> F{"Có token hợp lệ dạng Bearer?"}
  F -->|Không| E401["401"]
  F -->|Có| S{"Signature / alg / trusted JWKS?"}
  S -->|Không| E401
  S -->|Có| I{"iss + aud + exp/nbf phù hợp?"}
  I -->|Không| E401
  I -->|Có| P{"Có scope/role bắt buộc?"}
  P -->|Không| E403["403"]
  P -->|Có| O{"Đúng tenant + record ownership?"}
  O -->|Không| E403
  O -->|Có| OK["200/201 với dữ liệu đúng quyền"]
~~~

Đối với endpoints cần nhiều mức quyền, có thể áp dụng kiểm tra:

1. Token hợp lệ **cho chính API**.
2. Client/tenant có thuộc allowlist không (khi có policy).
3. Principal có required scope/app role không.
4. Principal có quyền với resource ID cụ thể không.
5. Truy vấn DB đã giới hạn theo tenant/owner chưa.
6. Dữ liệu trả về có những field phải được che hoặc lọc theo role không.
7. Việc ghi/xóa dữ liệu có cần kiểm soát concurrency, audit và approval không.

**Không dừng ở bước 1.** Một token hợp lệ với `Orders.Read` vẫn không phải giấy phép đọc tất cả đơn hàng của mọi khách hàng.

## 9. Khởi tạo Spring Boot Resource Server

Ví dụ dùng **Java 17+, Spring Boot 3.x** và Spring Security 6. Với Maven `spring-boot-starter-parent` hoặc dependency management phù hợp:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
  </dependency>
</dependencies>
~~~

Resource Server JWT validation cần các Spring Security OAuth2/Jose modules; **Spring Boot resource-server starter** là cách phổ biến để kéo dependencies tương ứng theo BOM. Không tự trộn phiên bản Spring Security 5 và 6. Nếu sử dụng WebFlux thay MVC, API cấu hình security sẽ khác (`SecurityWebFilterChain`, `ServerHttpSecurity`).

### API resource server không yêu cầu login redirect

Backend nhận HTTP API requests bằng access tokens; nó **không cần render trang Microsoft login** cho mỗi request. Spring Security `oauth2ResourceServer().jwt()` là phần xác thực JWT. Spring OAuth2 Client và login sessions chỉ dùng khi **chính ứng dụng cũng đóng vai trò OAuth client**.

## 10. Cấu hình issuer và audience

Với tenant single-tenant và access token **v2**:

~~~yaml
# application.yml - cấu hình minh họa, secrets không hard-code
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.microsoftonline.com/${ENTRA_TENANT_ID}/v2.0
          audiences:
            - ${ENTRA_API_AUDIENCE}

management:
  endpoints:
    web:
      exposure:
        include: health,info
~~~

Đặt environment variables ở nơi ứng dụng chạy:

~~~text
ENTRA_TENANT_ID=<TENANT_GUID>
ENTRA_API_AUDIENCE=<EXPECTED_ACCESS_TOKEN_AUD_CLAIM>
~~~

**Property `spring.security.oauth2.resourceserver.jwt.audiences` được hỗ trợ trong các dòng Spring Boot hiện đại phù hợp; hãy kiểm tra đúng phiên bản BOM đang dùng.** Nếu phiên bản của bạn không hỗ trợ property đó, triển khai **explicit audience validator** thay vì bỏ qua audience check.

### Ba giá trị dễ bị nhầm

- **Tenant ID:** xác định issuer tenant.
- **API Application (client) ID:** định danh API app registration.
- **Application ID URI/scope:** `api://<API_APP_ID>/Orders.Read` là scope yêu cầu của client, **không phải mặc nhiên là giá trị `aud`**.

Phải xác nhận expected audience từ cấu hình resource/API token contract và một token **đã được phát hành hợp lệ** trong lab; không chấp nhận cả mọi audiences chỉ vì thấy token đổi định dạng.

### Cơ chế Spring làm gì?

Khi được cấu hình đúng, Spring Resource Server có thể dùng OpenID Provider metadata/JWKS của issuer để kiểm tra chữ ký và các token validators (issuer/thời hạn). **Audience phải được kiểm tra rõ bằng property hoặc validator**, không giả định chỉ có `issuer-uri` đã khóa đúng API.

## 11. Spring SecurityFilterChain theo nguyên tắc deny by default

Cấu hình ví dụ cho REST API:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter converter
    ) throws Exception {

        http
            .csrf(csrf -> csrf.disable()) // Chỉ cho bearer-only/stateless API; xem phần CSRF.
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_Orders.Read")
                .requestMatchers(HttpMethod.POST, "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_Orders.Write")
                .requestMatchers("/api/internal/jobs/**")
                    .hasAuthority("ROLE_Jobs.Run")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(converter))
            );

        return http.build();
    }
}
~~~

### Tại sao khai báo như vậy?

- `STATELESS`: không dựa vào HTTP session để ghi nhớ user.
- `GET /api/orders/**`: yêu cầu delegated `Orders.Read`.
- `POST /api/orders/**`: yêu cầu delegated `Orders.Write`.
- `/api/internal/jobs/**`: yêu cầu app role `Jobs.Run`.
 - `anyRequest().denyAll()`: mọi route/method chưa khai báo bị từ chối, tránh vô tình cho một API mới truy cập chỉ vì người gọi đã đăng nhập.
- `actuator/health`: chỉ public endpoint health tối thiểu; giữ những actuator endpoints khác bị bảo vệ.
- `oauth2ResourceServer(jwt)`: xác minh Bearer token, không tự tin header.
- `@EnableMethodSecurity`: cho phép dùng `@PreAuthorize` ở service/controller.

**Cẩn trọng:** rule về path/method phụ thuộc routing thực tế. Nếu thêm `PATCH`, `PUT`, `DELETE` hoặc endpoint mới, phải khai báo policy cụ thể và thêm security tests; mặc định `denyAll()` giúp tránh lỗ hổng do quên phân quyền. Endpoint trả 404/403 trong test còn phụ thuộc Spring MVC routing và filter ordering; không coi một quy tắc path là kiểm tra ownership thay cho tầng dữ liệu.

## 12. Chuyển `scp` và `roles` thành Spring authorities

Spring Security Resource Server thường nhận diện `scope` hoặc `scp` và ánh xạ thành authority có prefix `SCOPE_`. Để có kết quả rõ ràng với Entra `roles` và custom policy, định nghĩa converter:

~~~java
package com.example.orders.security;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Configuration
public class JwtAuthorityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtGrantedAuthoritiesConverter scopes = new JwtGrantedAuthoritiesConverter();
        scopes.setAuthoritiesClaimName("scp");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter((Jwt jwt) -> {
            List<GrantedAuthority> result = new ArrayList<>();

            Collection<GrantedAuthority> scopeAuthorities = scopes.convert(jwt);
            if (scopeAuthorities != null) {
                result.addAll(scopeAuthorities);
            }

            List<String> roles = jwt.getClaimAsStringList("roles");
            if (roles != null) {
                for (String role : roles) {
                    result.add(new SimpleGrantedAuthority("ROLE_" + role));
                }
            }
            return result;
        });
        return converter;
    }
}
~~~

Ví dụ mapping:

~~~text
JWT: "scp": "Orders.Read Orders.Write"
  -> SCOPE_Orders.Read
  -> SCOPE_Orders.Write

JWT: "roles": ["Jobs.Run", "Orders.Read.All"]
  -> ROLE_Jobs.Run
  -> ROLE_Orders.Read.All
~~~

### Scope và role không đồng nghĩa

- **Delegated `scp`**: permissions trong ngữ cảnh người dùng/caller; cần kiểm tra **người dùng sở hữu record nào**.
- **Application `roles`**: thường dùng service-to-service; không có user context.
- **Roles có thể xuất hiện trong token của user** nếu app-role assignment cho user/group, nên không kết luận `roles` luôn là app-only mà bỏ mọi kiểm tra khác.
- API dành cho daemon có thể yêu cầu **app role + authorized client/service principal allowlist**, không chỉ bất kỳ token có tên role trùng.

### Không dùng `hasRole("...")` tùy tiện khi prefix đã khác

Spring `hasRole("Admin")` thường tìm authority `ROLE_Admin`. Nếu bạn map `scp` thành `SCOPE_Orders.Read` thì kiểm tra `hasAuthority("SCOPE_Orders.Read")`. Tên phải nhất quán từ app registration tới code và tests.

## 13. API controller: delegated scope và danh tính người gọi

Ví dụ một endpoint chỉ dành cho user-delegated token có `Orders.Read`:

~~~java
package com.example.orders.api;

import java.util.List;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrdersController {

    private final OrderReader orderReader;

    public OrdersController(OrderReader orderReader) {
        this.orderReader = orderReader;
    }

    @GetMapping
    @PreAuthorize("hasAuthority('SCOPE_Orders.Read')")
    public List<OrderDto> myOrders(@AuthenticationPrincipal Jwt jwt) {
        String tenantId = jwt.getClaimAsString("tid");
        String objectId = jwt.getClaimAsString("oid");

        if (tenantId == null || objectId == null) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Required principal claims missing");
        }

        return orderReader.findForOwner(tenantId, objectId);
    }

    // OrderReader và OrderDto là abstractions nghiệp vụ
    // được hiện thực bằng repository/service trong ứng dụng.
}
~~~

**Không tin `tenantId` hoặc `userId` do client truyền vào URL để quyết định owner**. Service query theo `(tid, oid)` từ JWT đã verify và điều kiện sở hữu dữ liệu ở database.

Ví dụ giao diện nghiệp vụ:

~~~java
public interface OrderReader {
    java.util.List<OrderDto> findForOwner(
        String tenantId, String userObjectId);
}
~~~

Một truy vấn SQL đúng có thể là:

~~~sql
SELECT OrderId, Status, TotalMinor
FROM dbo.Orders
WHERE TenantId = :tenantId
  AND OwnerObjectId = :userObjectId;
~~~

`:tenantId`/`:userObjectId` là **parameters** cần binding bằng prepared statements hoặc data access framework; **không** nối raw claims trực tiếp vào SQL text. Tầng repository cũng phải enforce tenancy/ownership ngay cả khi controller đã kiểm tra.

## 14. Bảo vệ theo resource và tenant, không chỉ endpoint

Giả sử `Orders.Read` hợp lệ nhưng user A gọi `GET /api/orders/999`, trong đó đơn 999 thuộc user B. Token vẫn hợp lệ, nhưng nếu server thực hiện `findById(999)` và trả dữ liệu, đó là **Broken Object Level Authorization (BOLA/IDOR)**.

### Sai

~~~java
// Pseudocode anti-pattern:
Order order = repository.findById(requestedId);
return order;
~~~

### Đúng về mặt cấu trúc

~~~java
// Pseudocode:
Order order = repository
    .findByIdAndTenantIdAndOwnerObjectId(
        requestedId,
        validatedJwtTenantId,
        validatedJwtObjectId
    )
    .orElseThrow(NotFoundException::new);
~~~

Có thể trả **404** thay vì **403** cho resource không thuộc quyền nếu policy muốn tránh tiết lộ sự tồn tại của ID; lựa chọn phải nhất quán và không che lỗi authentication.

### Multi-tenant key

Một cặp `(tid, oid)` thường phù hợp để nhận diện user Entra trong tenant. `oid` một mình không đủ làm identity key cho hệ thống multi-tenant. Nếu cho phép B2B guest accounts, đối tượng guest có thể có `oid` khác trong resource tenant; cần xác định canonical business identity và mapping theo chính sách.

### Scopes và record-level permissions

`SCOPE_Orders.Read` trả lời “client/user có delegated permission đọc Orders API”; nó **không trả lời** “người dùng có được xem đơn hàng của tenant khác không”. Quyền ở DB, policy service hoặc authorization evaluator vẫn bắt buộc.

## 15. Bảo vệ service-to-service bằng application roles

Một job chạy trên Azure Functions/AKS muốn gọi endpoint nội bộ `POST /api/internal/jobs/reconcile`. Nó sử dụng **application identity** và access token với `roles` phù hợp, không có user delegated context.

Ví dụ principal claim:

~~~json
{
  "ver": "2.0",
  "iss": "https://login.microsoftonline.com/<TENANT_ID>/v2.0",
  "aud": "<API_APP_CLIENT_ID>",
  "tid": "<TENANT_ID>",
  "azp": "<DAEMON_APP_CLIENT_ID>",
  "roles": ["Jobs.Run"],
  "exp": 1795163600
}
~~~

**Đây là payload minh họa, không phải access token có chữ ký.**

### Quy tắc policy

- Chỉ chấp nhận client đã được phép gọi API (đối chiếu `azp`/`appid` theo token format hoặc service principal identity khác được xác minh).
- Yêu cầu `ROLE_Jobs.Run`.
- Không cho endpoint service-to-service mặc nhiên dùng scope người dùng nếu không có lý do.
- Giới hạn quyền sửa dữ liệu theo tenant/workspace/resource.
- Có audit theo client identity, operation ID và resource.
- Dùng idempotency key và rate limit cho thao tác thay đổi dữ liệu.
- Không cho một daemon app `Jobs.Run` tự có quyền quản trị mọi Azure resource.
- Nếu policy yêu cầu **chỉ token app-only**, thiết kế thêm kiểm tra nhận diện application token theo các claims thực sự được Entra phát hành (ví dụ `idtyp=app` khi đã cấu hình và được hỗ trợ), cùng app-role assignment và client allowlist; sự vắng mặt của `scp` một mình không chứng minh đó là token app-only.

### App-only token không có nghĩa mọi daemon đáng tin

Token có chữ ký đúng nhưng chứa role không được endpoint yêu cầu hoặc issuer/audience sai vẫn phải từ chối. Nếu application assignment/consent bị thu hồi nhưng token cũ chưa hết hạn, cần xét chính sách token lifetime/revocation.

## 16. 401 và 403: ý nghĩa HTTP chính xác

| Tình huống | Kết quả thông thường | Giải thích |
|---|---|---|
| Không có Bearer token trên endpoint bảo vệ | **401** | Chưa được xác thực |
| Token bị sửa chữ ký | **401** | Invalid authentication token |
| Token hết hạn/chưa có hiệu lực | **401** | Token không hợp lệ về thời gian |
| Sai issuer hoặc audience | **401** | Token không dành cho API tin cậy |
| Token hợp lệ nhưng thiếu `Orders.Read` | **403** | Có identity nhưng thiếu quyền |
| User có scope, truy cập record của người khác | **403/404** tùy policy | Object-level authorization |
| Rate limit/quota bị vượt | **429** | Không phải lỗi xác thực |
| API lỗi không liên quan security | **5xx** | Không đổi mọi lỗi thành 401 |

Trong OAuth2 Bearer Resource Server, `WWW-Authenticate: Bearer ...` có thể cung cấp error metadata thích hợp theo chuẩn. Không đưa claims, token hoặc internal key details vào error response.

Ví dụ body an toàn:

~~~json
{
  "type": "about:blank",
  "title": "Forbidden",
  "status": 403,
  "detail": "Insufficient permission",
  "requestId": "req-illustration-001"
}
~~~

Spring Security có default authentication entry point/access denied handling; nếu bạn customize error body, **đừng trả 200 cho request bị chặn** và không làm mất Bearer challenge semantics khi cần.

## 17. Audience validator tùy chỉnh khi Boot property không hỗ trợ

Nếu project dùng một dòng Spring Boot không có property `jwt.audiences`, **đừng xóa bước kiểm tra audience**. Có thể cấu hình `JwtDecoder` với issuer và audience validators.

Ví dụ Java dùng `NimbusJwtDecoder`. JWKS URL phải được lấy từ **OpenID metadata của đúng tenant/issuer**, không tin URL do JWT header `jku` tự khai báo:

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.*;
import org.springframework.security.oauth2.jwt.*;

@Configuration
public class JwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer-uri}") String issuer,
            @Value("${app.security.audience}") String audience,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> correctAudience = token ->
            token.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Access token audience is not this API",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, correctAudience
            )
        );
        return decoder;
    }
}
~~~

Cấu hình các giá trị:

~~~yaml
app:
  security:
    issuer-uri: https://login.microsoftonline.com/${ENTRA_TENANT_ID}/v2.0
    audience: ${ENTRA_API_AUDIENCE}
    jwk-set-uri: https://login.microsoftonline.com/${ENTRA_TENANT_ID}/discovery/v2.0/keys
~~~

### Lựa chọn **một** chiến lược nhất quán

- Dùng Spring Boot property `issuer-uri` + `audiences` **nếu framework version hỗ trợ**; hoặc
- Khai báo custom `JwtDecoder` bean với explicit issuer/time/audience validators và trusted JWKS.

Không vô tình tạo hai cấu hình chồng lấn rồi tưởng property mặc định vẫn được áp dụng nếu custom decoder đã thay thế auto-configuration. Với custom decoder, phải rà soát đầy đủ validators, JWS algorithms, key rotation, time skew và supported issuer metadata.

## 18. JWT signature và key rotation

Entra ID ký JWT bằng private signing key; API dùng **public key** lấy từ JWKS endpoint được công bố qua OIDC metadata của issuer.

### Quy trình xác minh

1. Nhận JWT dạng Bearer.
2. Kiểm tra cấu trúc/JWS algorithm theo decoder trusted configuration.
3. Tìm signing key theo `kid` trong JWKS metadata **của issuer được tin cậy**.
4. Verify cryptographic signature.
5. Validate `iss`, `aud`, `exp`, `nbf` và những policy claims khác.
6. Convert authorities và thực hiện access-control.

### Key rollover

Microsoft Entra có thể thêm signing keys mới. Resource server cần dùng SDK/library hỗ trợ JWKS refresh theo policy. Tránh:

- Hard-code **một** PEM public key vĩnh viễn.
- Tự tải arbitrary JWK URL lấy từ JWT header của người gọi.
- Tắt signature validation khi `kid` chưa có trong cache.
- Restart mọi pods liên tục để sửa refresh problem mà không kiểm tra network/metadata.
- Log raw JWT để debug key mismatch.

### Network tác động authentication

Nếu Azure Container Apps/AKS chỉ có private egress và firewall chặn OpenID metadata/JWKS, resource server có thể lỗi khi khởi động hoặc khi cần refresh keys. Phải cho phép outbound tới đúng Entra endpoints theo security policy, cân nhắc proxy/TLS trust và health checks; **không chuyển sang “accept unsigned token” làm fallback**.

## 19. Clock skew, expiration, revocation và session

Access token thường có thời hạn hữu hạn, nhưng **không giả định luôn là 60 phút**. Token lifetime tùy policy và loại token. JWT validators cần kiểm tra `exp`, `nbf` và clock skew theo cấu hình/library.

### Clock synchronization

- Đồng bộ thời gian trên pods/VMs.
- Sai đồng hồ có thể làm token vừa phát hành bị xem là “not yet valid” hoặc token hết hạn bị chấp nhận sai.
- Clock skew chỉ nên nhỏ và theo tiêu chuẩn; không mở rộng hàng giờ để “sửa” lỗi đồng hồ.

### Token revocation

Một JWT được xác minh offline có thể tiếp tục hợp lệ đến `exp` dù quyền hoặc session thay đổi, trừ khi triển khai thêm chính sách/service capabilities phù hợp. **Không cam kết vô hiệu hóa ngay mọi token chỉ vì user logout hoặc bị disable**.

Với nghiệp vụ rủi ro cao:

- Áp dụng short lifetime theo cơ chế danh tính hỗ trợ.
- Kiểm tra trạng thái user/tenant/entitlement ở backend khi cần.
- Xem Conditional Access/Continuous Access Evaluation nếu đúng resource/client/support context.
- Có audit/anomaly detection, token theft response và nguyên tắc least privilege.
- Không dùng refresh token làm Bearer cho API.

### Refresh token ở đâu?

Thường do OAuth client/MSAL quản lý theo loại client và security policy; Resource Server **không cần nhận refresh token** chỉ để xác thực API request.

## 20. CORS, CSRF và browser security

Ba khái niệm dễ bị nhầm:

- **CORS:** trình duyệt quyết định JavaScript ở origin nào được đọc response từ API. CORS **không thay authorization** và không cản client ngoài browser gọi API.
- **CSRF:** tấn công dựa vào authentication state được browser tự động gửi (thường cookie/session).
- **Bearer token trong Authorization header:** frontend chủ động gắn token; đối với API chỉ sử dụng Bearer và không có auth cookie, có thể vô hiệu CSRF theo thiết kế. Nhưng nếu có session/cookies hoặc dùng OAuth login flow trong cùng ứng dụng, phải đánh giá lại.

### Chính sách CORS đúng phạm vi

~~~java
// Ví dụ fragment; dùng trong cấu hình Spring Security phù hợp.
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    cors.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

Nếu API cần CORS, bật `http.cors(...)` trong SecurityFilterChain theo đúng Spring Security version và đăng ký bean như trên. Cấu hình trên là fragment, không phải class Java standalone.

**Không cấu hình `allowedOrigins("*")` kết hợp credentials để “cho dễ”**. Ngay cả origin được cho phép cũng **phải** có valid access token và đúng scope/role.

## 21. Lấy token từ frontend một cách an toàn

Frontend nên dùng MSAL/OIDC library tương thích với loại ứng dụng. Mô hình:

~~~text
Frontend public client registration:
  authority: tenant-specific trusted authority
  clientId: frontend client ID
  redirectUri: registered URI
  requested scopes:
    api://<API_APP_ID>/Orders.Read

Flow:
  redirect/login with authorization code + PKCE
  acquireTokenSilent when supported
  interactive authorization if required
  call API with Authorization: Bearer <access_token>
~~~

**Không đưa access token vào query string, referrer, localStorage theo thói quen** khi có nguy cơ XSS hoặc leaked logs. Cần đánh giá cache strategy/token storage theo hướng dẫn thư viện và threat model; mọi SPA vẫn phải phòng XSS, CSP, dependency vulnerabilities và malicious browser extensions.

### Không lấy Graph token để gọi custom API

Token có audience **Microsoft Graph** dành cho Graph. Dù user có quyền `User.Read` trên Graph, backend Orders API phải **từ chối** token đó vì `aud` sai. Muốn gọi Orders API, client cần scope Orders API.

### Client ID không phải secret

App client ID và tenant ID là identifiers. Chúng cần chính xác nhưng không đủ làm chứng chỉ cho phép. Không coi việc biết client ID là chứng minh client đáng tin. Confidential clients cần credentials/identity và app consent theo flow.

## 22. Service-to-service với managed identity

Một service chạy trên Azure có thể dùng **managed identity** hoặc workload identity để nhận token thay vì lưu client secret dài hạn, nếu resource provider/API và quyền đã được cấu hình phù hợp.

### Các bước logic

1. Bật managed identity/workload identity cho compute/service.
2. Xác định **service principal identity** đại diện cho service.
3. Gán **app role** của API cho identity đó bằng quy trình Entra/Graph phù hợp.
4. Client xin token với resource scope `api://<API_APP_ID>/.default` theo khả năng credential/provider.
5. API validate issuer/audience và yêu cầu `ROLE_Jobs.Run`.
6. Ngoài role, kiểm tra allowlist caller identity và resource-level authorization khi cần.

Ví dụ Java với **Azure Identity** (minh họa backend worker, không chạy ở frontend):

~~~java
import com.azure.core.credential.AccessToken;
import com.azure.core.credential.TokenRequestContext;
import com.azure.core.credential.TokenCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.time.Duration;

public final class TokenForWorker {
    public static AccessToken acquire(String apiAppId) {
        TokenCredential credential =
            new DefaultAzureCredentialBuilder().build();

        TokenRequestContext context = new TokenRequestContext()
            .addScopes("api://" + apiAppId + "/.default");

        AccessToken token = credential.getToken(context)
            .block(Duration.ofSeconds(20));

        if (token == null) {
            throw new IllegalStateException("Could not obtain access token");
        }
        return token;
    }
}
~~~

**Giới hạn:** snippet dùng `block()` nên chỉ hợp cho luồng **blocking worker**, không đặt vào Reactor event-loop. Production nên **reuse credential**, sử dụng SDK/client auth integration phù hợp, xử lý 401/403 và caching/expiry bằng thư viện. Không gọi `System.out.println(token.getToken())`. Identity/app-role assignment và compatibility của custom API với managed identity cần được kiểm tra trước khi chạy.

Để chạy ví dụ này, thêm dependency **`com.azure:azure-identity`** và quản lý phiên bản tương thích bằng **Azure SDK BOM** hoặc dependency management đã được phê duyệt; Maven starters của Spring Security Resource Server ở phần trước không tự cung cấp Azure Identity SDK. Với confidential clients cần chứng thư hoặc secret, ưu tiên **managed identity/federation/certificate** theo threat model; nếu còn dùng secret, giữ trong **Azure Key Vault**, phân quyền đọc tối thiểu, theo dõi rotation và tuyệt đối không commit vào Git hay in token vào logs.

## 23. On-Behalf-Of (OBO) khi API gọi dịch vụ khác

Giả sử frontend gửi token với `aud=Orders API` và delegated `Orders.Read`. Orders API cần truy vấn thông tin người dùng ở **Microsoft Graph**:

~~~mermaid
sequenceDiagram
  participant C as Frontend
  participant A as Orders API
  participant E as Entra ID
  participant G as Microsoft Graph
  C->>A: Bearer token aud=Orders API
  A->>A: Validate and authorize
  A->>E: OBO exchange with delegated Graph scopes
  E-->>A: New access token aud=Graph
  A->>G: Authorization Bearer Graph token
  G-->>A: Graph response
  A-->>C: Filtered API response
~~~

Không forward token ban đầu thẳng tới Graph. OBO cần client configuration, delegated permissions/consent và confidential client authentication tương ứng; dùng MSAL Java hoặc thư viện được hỗ trợ thay vì tự gửi assertion tùy tiện.

### OBO khác managed identity

- **OBO:** gọi downstream **thay mặt user** với delegated permissions.
- **Managed identity:** service gọi downstream **bằng danh tính ứng dụng**, không có user-delegated context.

Chọn theo nghiệp vụ: đọc dữ liệu “của người dùng hiện tại” thường cần user delegation và permission check; tác vụ hệ thống không có user có thể dùng managed identity/app role.

## 24. Client allowlist và tenant restriction

Có những API muốn chỉ cho một số frontend/service clients được gọi, ngay cả khi token có scope được cấp.

- Với v2 access token, claim `azp` có thể biểu thị authorized client app.
- Với v1 access token, có thể gặp `appid`.
- Giá trị và presence phải được đọc theo token/version contract.
- Cần **issuer/audience/signature verification trước**, rồi mới dùng client claim trong policy.
- **Client allowlist** là lớp bổ sung, không thay scopes, roles hoặc record-level auth.
- Không dựa vào HTTP header tự khai `X-Client-Id` để chứng minh client.

### Multi-tenant API

Nếu hỗ trợ nhiều Entra tenants:

1. Liệt kê tenants được phép hoặc quy trình tenant onboarding/approval.
2. Chọn JWT validation resolver theo **trusted issuers**, không chấp nhận tùy ý tenant người gọi.
3. Validate `iss` và `tid` tương ứng từng tenant.
4. Giữ audience là API được đăng ký và quyền phù hợp.
5. Tách data theo tenant và kiểm tra ownership.
6. Cân nhắc B2B guests và tenant home/resource contexts.
7. Thêm tests về issuer confusion/cross-tenant replay.

**Không dùng `JwtDecoder` đơn giản chỉ kiểm tra signing key của một shared endpoint rồi bỏ issuer tenant check**. Multi-tenant validation cần thiết kế rõ, không sửa single-tenant issuer thành `/common` cho mọi trường hợp.

## 25. App roles, groups và group overage

Microsoft Entra có thể gửi claims `groups` trong một số cấu hình, nhưng JWT có giới hạn kích thước. Khi user thuộc nhiều nhóm, token có thể không chứa toàn bộ group IDs mà thể hiện **group overage indication** (ví dụ `hasgroups` hoặc claims mapping).

### Nguy cơ

Nếu API chỉ tìm `groups` array và mặc định không có array là không có nhóm, user thuộc quá nhiều nhóm có thể bị từ chối nhầm; nguy hiểm hơn nếu code **default allow** khi thiếu `groups` thì tạo lỗ hổng.

### Khuyến nghị

- Với API authorization, cân nhắc **app roles** được quản lý để tránh phụ thuộc một danh sách groups quá lớn trong token.
- Nếu cần group-based policy, xử lý overage theo docs/Graph query được ủy quyền và có caching policy.
- Không gọi Graph bằng access token của Orders API nếu audience không phải Graph.
- Không giả định có email, preferred username, groups hay roles trong mọi token.
- Ghi rõ source of truth của membership và độ trễ khi quyền thay đổi.

## 26. Test bảo mật: đừng chỉ test HTTP 200

Một bảng test tối thiểu:

| Test | Token/điều kiện | Kỳ vọng |
|---|---|---|
| Không có Authorization | Không token | 401 |
| Header không đúng Bearer | Chuỗi bất kỳ | 401 |
| Chữ ký sai | JWT tự sửa payload | 401 |
| Hết hạn | `exp` quá khứ | 401 |
| Chưa có hiệu lực | `nbf` tương lai | 401 |
| Issuer tenant khác | `iss` không tin cậy | 401 |
| Token Graph | `aud` là Graph | 401 |
| ID token frontend | `aud` là frontend client | 401 |
| Delegated chỉ `Orders.Read` | GET Orders | Cho phép nếu đúng owner |
| Delegated chỉ `Orders.Read` | POST Orders | 403 |
| App-only `Jobs.Run` | Internal job route | Cho phép khi client/tenant policy phù hợp |
| App-only không role | Internal job route | 403 |
| User A đọc Order B | Scope hợp lệ, owner sai | 403/404 theo policy |
| Tenant A truy cập Tenant B | JWT hợp lệ, data boundary sai | Từ chối |
| Health endpoint | Không token | Chỉ thông tin health tối thiểu |
| Unknown route | Token hợp lệ nhưng không được allow | 404/403 tùy routing/policy |

### Kiểm thử trực tiếp với MockMvc

Nếu dùng `spring-security-test`, mock JWT có thể dùng để test **authorization**:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void getOrdersRequiresReadAuthority() throws Exception {
        mvc.perform(get("/api/orders").with(jwt()
                .jwt(token -> token
                    .claim("tid", "tenant-test")
                    .claim("oid", "user-test"))
                .authorities(new SimpleGrantedAuthority("SCOPE_Orders.Read"))))
            .andExpect(status().isOk());
    }

    @Test
    void getOrdersWithoutRequiredAuthorityIsForbidden() throws Exception {
        mvc.perform(get("/api/orders").with(jwt()
                .authorities(new SimpleGrantedAuthority("SCOPE_Other.Read"))))
            .andExpect(status().isForbidden());
    }
}
~~~

**Đây là test minh họa:** cần cung cấp bean/repository `OrderReader` (mock hoặc test database) và dependency `spring-security-test` phù hợp. Mặc định `jwt()` trong MockMvc **bỏ qua kiểm tra chữ ký và JwtDecoder thực**; tự gán authorities cũng **bỏ qua converter production**. Vì vậy **không dùng test trên làm bằng chứng** issuer/audience/signature đã được xác minh.

### Integration tests phải kiểm tra JwtDecoder thật

Dùng test issuer/JWKS server với key ký **cục bộ, kiểm soát được**, cấu hình audience/issuer tương ứng rồi gửi JWT ký đúng/sai để kiểm tra 401/403. Không lấy private signing key của Entra, không cố giả lập Azure production token. Test boundaries:

- Wrong `iss`, `aud`, `exp`, `nbf`, unsupported algorithm.
- Key ID không thuộc trusted JWKS.
- Scope/role converter và method security.
- Token dạng v1 bị từ chối khi API chỉ hỗ trợ v2.
- Tenant/owner access ở repository.
- Fail closed khi JWKS unavailable và không có valid cached keys.

## 27. Manual test bằng cURL/Postman trong lab

Khi đã có **access token hợp lệ dành cho Orders API** do client được phép nhận qua MSAL/OAuth flow:

~~~bash
API_URL="https://orders-api.example.com"
# ACCESS_TOKEN: đặt trong môi trường bảo mật, không echo/log vào shell history.
curl --fail-with-body \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Accept: application/json" \
  "${API_URL}/api/orders"
~~~

**Không** đưa token vào URL, log requests hoặc chụp màn hình gửi ngoài kênh có quyền. Trên hệ thống cURL cũ có thể không hỗ trợ `--fail-with-body`; dùng `-i` hoặc cách ghi status an toàn khác.

### Cách lấy token để test

- Client user: MSAL + Authorization Code PKCE hoặc Postman OAuth2 flow với redirect URI và API scope được đăng ký.
- Client app-only: confidential client flow với `.default` và app role assignment đã được phê duyệt.
- Azure workload: managed/workload identity theo cấu hình và permission grant.

Nếu bạn chỉ có ID token hoặc Graph access token, **không ép API chấp nhận**. Sửa việc yêu cầu token ở client registration/permissions, không sửa API để bỏ audience validation.

### Bản ghi thử nghiệm

~~~text
Test case: delegated user with Orders.Read
Issuer tenant: <TENANT_ID>
Expected audience: <API_AUDIENCE>
Requested scope: api://<API_APP_ID>/Orders.Read
HTTP result: 200
Returned rows: only own tenant/owner
Token value: NEVER LOGGED
RequestId: lab-test-001
~~~

## 28. API Management và gateway có thay thế resource server không?

Azure API Management (APIM), Application Gateway hoặc ingress có thể làm **TLS termination, gateway authentication, rate limiting, logging, routing và security policy**. Với APIM, có thể cấu hình policy xác minh JWT theo issuer/audience và claims khi tính năng/version hỗ trợ.

Nhưng vẫn phải xác định trust boundary:

- Nếu backend **trực tiếp reachable**, việc chỉ validate token ở APIM dễ bị bypass.
- Nếu gateway truyền identity headers, backend phải chỉ tin headers khi request đến từ gateway **được bảo vệ và chứng thực**, tránh header spoofing.
- Nếu backend cũng là resource server, nó có thể verify token lần nữa để defence in depth.
- Gateway xác minh token không tự kiểm tra ownership của `orderId` trong database.
- Chính sách rate limit không thay quyền API scopes/roles.

### Kiến trúc tham khảo

~~~mermaid
flowchart LR
  B["Browser / Mobile"] --> APIM["APIM: TLS, JWT, rate limit"]
  APIM --> API["Spring Boot Resource Server"]
  API --> AUTH["Scope/role + tenant/owner checks"]
  AUTH --> DB["Azure SQL / Cosmos DB"]
  API --> MON["Azure Monitor / App Insights"]
  APIM --> MON
~~~

Tùy yêu cầu, có thể chọn gateway validation + backend independent JWT verification; không buộc mọi request đều phải gọi Entra trong runtime khi JWT keys được cache đúng.

## 29. Triển khai Spring Boot Resource Server trên Azure

Các lựa chọn phổ biến:

- **Azure App Service:** chạy Java app theo runtime/plan và cấu hình app settings, networking.
- **Azure Container Apps:** chạy container có managed identity, ingress, secrets, revisions.
- **AKS:** pods, Kubernetes service/ingress, workload identity và network policies.

Bất kể nơi chạy:

1. Cấp đúng `ENTRA_TENANT_ID` và `ENTRA_API_AUDIENCE` qua configuration.
2. Chỉ nhận HTTPS/TLS với endpoint thực tế và gateway.
3. Cho phép egress phù hợp đến Entra OIDC metadata/JWKS endpoints.
4. Cấu hình ingress/public/private access theo policy.
5. Dùng network/private endpoints cho Storage/SQL nếu API cần dữ liệu nội bộ.
6. Gắn managed identity/workload identity cho **downstream Azure resource**, không mặc nhiên dùng identity đó để “bỏ qua” client Bearer token.
7. Không lưu token/secret trong container image, Dockerfile, ConfigMap công khai hoặc Git.
8. Đặt liveness/readiness probes phù hợp và giới hạn health detail.
9. Thiết lập auto-scaling/rate limiting/quota phù hợp.
10. Cấu hình logging/tracing/budgets và runbook khi identity provider/JWKS gặp lỗi.

### Trường hợp App Service Easy Auth

Azure App Service Authentication/Authorization (“Easy Auth”) có thể hỗ trợ xác thực ở platform layer, nhưng nếu ứng dụng đã dùng Spring Security Resource Server thì phải thiết kế rõ **nơi token được validate, audience nào được chấp nhận và request identity đi qua proxy thế nào**. Không mặc định Easy Auth và Spring Security tự “cộng quyền” đúng nếu cấu hình khác nhau.

## 30. Observability và Azure Monitor

Một API bảo mật cần theo dõi không chỉ độ trễ mà cả lý do bị từ chối.

| Metric/log | Ý nghĩa |
|---|---|
| Request count theo route/method/status | 401/403/429/5xx và traffic |
| Authentication failures theo nhóm | Missing token, bad signature, wrong issuer/audience, expired |
| Authorization denials | Thiếu scope/role, tenant/owner mismatch |
| OIDC/JWKS refresh failures | Hệ thống có vấn đề tải/trust signing keys |
| Spring Security filter latency | AuthN/AuthZ cost |
| Downstream DB latency/403 | Dữ liệu/identity issue |
| Token acquire failures của client | Consent/credential/managed identity |
| Suspicious bursts | Token replay, brute force, unexpected client identity |
| JWT decoder/cache behavior | Key rotation và availability |
| p95/p99 latency, 5xx, availability | SLO/UX |
| App/container/ingress network | TLS, proxy, DNS, egress |
| Audit events | Role/permission/app registration changes |

### Log an toàn

~~~json
{
  "timeUtc": "2026-11-20T12:00:00Z",
  "requestId": "req-example-001",
  "route": "GET /api/orders",
  "status": 403,
  "reasonCategory": "missing_scope",
  "tenantKey": "tenant-hash",
  "clientKey": "client-hash",
  "latencyMs": 12
}
~~~

Không log raw JWT/access token, Authorization header, refresh token, signature, full claims chứa PII hoặc bí mật. `oid`/`tid` là identifiers cần áp dụng privacy/log access policy; có thể hash/pseudonymize khi phù hợp.

### Alert có hành động

- Tỷ lệ 401/403 tăng sau deployment/app registration change.
- Nhiều 401 do key refresh/issuer mismatch xảy ra đồng thời.
- Bùng nổ 403 do role assignments/consent bị mất.
- Access requests từ tenant/client IDs không nằm trong allowlist.
- API 5xx/p95 tăng sau khi bật network restriction.
- Role/app permission changes ở Entra audit logs bất thường.
- DB queries chéo tenant hoặc owner mismatch nếu có security audit events.
- Chi phí logging tăng do ghi mỗi denial với payload quá lớn.

**Không biến mọi 401 thành PagerDuty incident**: token hết hạn hoặc user chưa có quyền có thể là tình huống bình thường. Cảnh báo theo rate, baseline, affected tenants và user impact.

## 31. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| 401 dù frontend đăng nhập | Gửi ID token thay access token | Kiểm tra token type/aud ở môi trường lab |
| 401 với Graph token | `aud` không phải API | Client request API scope đúng |
| 401 issuer mismatch | Token v1/v2 không khớp, sai tenant | `iss`, `ver`, tenant/API registration |
| 401 sau rotate key | JWKS cache/egress/metadata vấn đề | JWKS refresh, DNS/proxy/TLS |
| 401 token expired | `exp`, local clock drift | Sync time, MSAL silent acquisition |
| 401 signature invalid | Token bị sửa hoặc key không tin | Không bỏ signature validation |
| 403 thiếu authority | Scope/role không có hoặc converter sai | `scp`, `roles`, SCOPE_/ROLE_ |
| 403 app-only dù có token | App role assignment/admin consent chưa đúng | Entra Enterprise app roles/token claims |
| 403 user có scope nhưng không thấy đơn | Owner/tenant permission | Repository filter và dữ liệu user |
| User A đọc được đơn B | BOLA/IDOR | Kiểm tra owner ở database |
| CORS preflight lỗi | Origin/method/headers config | CORS + Spring filter ordering |
| 403 cho POST từ browser | CSRF/session cookie lẫn Bearer | Xem session/security architecture |
| Local chạy, Azure thất bại | JWKS egress DNS/proxy/issuer config | Container/VM network và env vars |
| 403 Azure SQL/Storage downstream | API token và Azure data-plane role khác | Managed identity/RBAC/ACL |
| Client credentials token thiếu `scp` | App-only dùng `roles` | Policy endpoint/service registration |
| JWT nhiều groups nhưng claim thiếu | Group overage | App roles hoặc supported Graph lookup |
| Multi-tenant user bị từ chối | Tenant allowlist/issuer resolver | Onboarding và guest identity rules |
| 401 mọi request sau deployment | Wrong audience env var | Redeploy correct setting, regression test |

### Không chữa lỗi bằng cách

- Tắt issuer/audience check.
- Chấp nhận cả Graph token và ID token.
- Gắn `permitAll()` cho API tạm thời rồi quên khôi phục.
- Cấp toàn bộ người dùng role Admin.
- Dùng `TrustAll` SSL hoặc bỏ TLS verification.
- Log token để hỏi người khác debug.
- Bỏ qua BOLA vì frontend “đã ẩn” đơn hàng của user khác.

## 32. Threat modeling: các lỗi bảo mật hay gặp

### Token substitution

Kẻ tấn công dùng một token **có chữ ký hợp lệ nhưng dành cho resource khác**. Phòng vệ: **audience validation**.

### Issuer/tenant confusion

Token đến từ tenant không được API tin cậy. Phòng vệ: exact trusted issuer(s), tenant allowlist và onboarding policy; không tin `tid` từ token chưa verify.

### Overbroad authorization

User chỉ cần xem đơn của mình nhưng API gán `SCOPE_Orders.Read` thành quyền đọc mọi đơn. Phòng vệ: ownership và business permissions trong service/repository.

### Scope-role confusion

API định nghĩa app role cho daemon nhưng dùng một rule `authenticated()` hoặc đọc nhầm user role. Phòng vệ: endpoint-specific scopes/app roles, principal type/caller policy.

### Token leakage

Token trong query strings, local logs, client telemetry hoặc crash dumps. Phòng vệ: TLS, redaction, secret storage, short lifetime và audit.

### Algorithm/key confusion

Tự viết JWT verifier nhận `alg=none` hoặc JWK URL do attacker chọn. Phòng vệ: dùng Spring Security/Nimbus JWT decoder trusted configuration, không tự code crypto.

### Replay

Bearer token bị lấy cắp và sử dụng trước khi hết hạn. Phòng vệ: bảo vệ token, TLS, device/Conditional Access controls khi hỗ trợ, API rate/anomaly detection và risk-based authorization; JWT Bearer thông thường không tự có proof-of-possession.

### Consent/permission misconfiguration

Admin consent application permission quá rộng hoặc app-role assignment sai. Phòng vệ: review API permissions, owners, approval workflows và least privilege.

### Open redirect/CORS misconfiguration

Client redirect URIs quá rộng, frontend XSS hoặc CORS “*”. Phòng vệ: exact redirects, PKCE, CSP, input validation, CORS allowlist.

## 33. Chi phí và vận hành

Entra token validation bằng JWT có thể thực hiện local nên không phải gọi Entra cho mỗi HTTP request. Nhưng tổng chi phí vẫn gồm:

- Compute của Spring Boot App Service/Container Apps/AKS.
- API Management/Application Gateway/WAF nếu dùng.
- Network egress/proxy/private networking.
- Database/Storage queries theo người gọi được phép.
- Azure Monitor/Application Insights/Log Analytics ingestion/retention.
- CI/CD security tests, scanning và vận hành certificate/identity.
- Phát sinh chi phí do retries, token acquisition errors, nhiều 401/403 hoặc traffic abuse.
- Licenses/Entra governance features tùy chính sách và gói tổ chức.

### Tối ưu không đánh đổi bảo mật

- Dùng resource-server JWT validation/JWKS caching thay introspect theo request nếu phù hợp.
- Reuse HTTP clients/credentials cho downstream.
- Bảo vệ API bằng ingress/rate limits, phân biệt authentication error với backend overload.
- Log tổng hợp 401/403 theo route/cause, tránh mọi raw claims.
- Giới hạn public health endpoint và detailed diagnostics.
- Thiết lập budget và cost tags cho environments.
- Không tắt JWT checks để giảm latency.
- Dùng staging để benchmark p95 trước rollout.

## 34. Case study: Orders API và worker reconcile

### Bối cảnh

Doanh nghiệp dùng Vue/React frontend, Spring Boot REST API trên Azure Container Apps, Azure SQL lưu Orders và một Azure Function chạy lịch đối soát. Yêu cầu:

- User chỉ xem đơn của chính mình.
- User được phép sửa đơn khi có `Orders.Write` và business rule.
- Daemon reconcile được gọi một endpoint nội bộ mà không giả làm user.
- Token của Microsoft Graph không được dùng với Orders API.
- Mỗi request có audit metadata nhưng không log token/PII.
- API phục vụ nhiều tenant đã onboard, không chấp nhận tenant tùy ý.

### Thiết kế

~~~mermaid
flowchart LR
  SPA["Frontend + MSAL PKCE"] --> ENTRA["Microsoft Entra ID"]
  ENTRA -->|Access token aud=Orders API| SPA
  SPA --> API["Spring Boot Resource Server"]
  FUNC["Function / Managed Identity"] -->|App-only token + Jobs.Run| API
  API --> V["JWT verify: signature/iss/aud/time"]
  V --> P["SCOPE_/ROLE_ + tenant/owner policy"]
  P --> SQL["Azure SQL: TenantId + OwnerObjectId"]
  API --> OBS["Azure Monitor + App Insights"]
~~~

### Chính sách cụ thể

- Frontend lấy `api://<API_APP_ID>/Orders.Read`; POST cần `Orders.Write`.
- API config exact issuer v2 và expected audience.
- Controller nhận `Jwt` đã verify, service query `TenantId` và `OwnerObjectId`.
- Function dùng managed identity đã được gán app role `Jobs.Run`.
- Internal endpoint yêu cầu `ROLE_Jobs.Run` và authorized caller.
- APIM/ingress áp dụng TLS/rate limits, backend vẫn thực hiện authorization.
- Health endpoint công khai tối thiểu, mọi debug/actuator khác được bảo vệ.
- Metrics theo route/status/reason category và identity đã pseudonymize.

### Thử sự cố

1. Frontend vô tình gửi ID token: API trả 401 vì sai audience.
2. Chạy daemon chưa gán app role: API trả 403.
3. Token `Orders.Read` gọi POST: API trả 403.
4. User A sửa URL thành order của B: service trả 404/403.
5. API pod không truy cập JWKS khi signing key rotate: authentication lỗi, alert egress/JWKS, **không** disable signature check.
6. Application permission vô tình được cấp rộng: security review thu hồi quyền, kiểm tra tokens còn hiệu lực và audit calls.

## 35. Bài thực hành: bảo vệ Spring Boot REST API

> **An toàn:** chỉ thao tác trên Entra tenant, app registrations và Azure resources lab được phê duyệt. Thay đổi scopes/roles/consent của ứng dụng production có thể làm gián đoạn nhiều consumers. Không dùng token thật trong ví dụ Markdown, repo, issue tracker hay log.

### Phần A — Đăng ký Entra

1. Xác nhận tenant lab và quyền tạo app registrations.
2. Tạo `orders-api-dev`, ghi API app client ID/tenant ID.
3. Expose API với Application ID URI phù hợp.
4. Tạo delegated scopes `Orders.Read` và `Orders.Write`.
5. Tạo app role `Jobs.Run` cho application client.
6. Tạo `orders-spa-dev`, cấu hình redirect URI/PKCE đúng.
7. Gán delegated API permissions và consent theo policy.
8. Nếu lab cho phép, tạo service identity/daemon có app role và quyền phù hợp.
9. Xác nhận API chấp nhận v2 access tokens và expected issuer.
10. Ghi lại expected audience theo resource token contract.

### Phần B — Spring Boot

1. Tạo project Java 17+ với starters web, security, oauth2-resource-server, actuator.
2. Cấu hình `issuer-uri` và `audiences` từ environment variables.
3. Thêm `SecurityFilterChain`, deny-by-default rules cho GET/POST/internal jobs.
4. Thêm converter `scp`/`roles` thành authorities.
5. Thêm `@EnableMethodSecurity` và `@PreAuthorize`.
6. Viết controller trả dữ liệu theo `tid`/`oid` từ validated JWT.
7. Viết repository test có tenant/owner filters.
8. Giới hạn actuator health và không expose sensitive endpoints.
9. Nếu dùng SPA, cấu hình CORS allowlist.
10. Chạy test không token, scope sai và record ownership sai.

### Phần C — End-to-end token tests

1. Dùng client MSAL/PKCE lab để xin access token đúng API scope.
2. Kiểm tra issuer/audience/time trong token đã được cấp bằng công cụ an toàn; không gửi token ra site ngoài tổ chức.
3. Gọi GET Orders với token đúng → 200 và chỉ dữ liệu của user.
4. Gọi POST với chỉ `Orders.Read` → 403.
5. Thử ID token/Graph access token → 401.
6. Thử token hết hạn/sai chữ ký trong integration test với local key → 401.
7. Thử app-only token không app role → 403.
8. Thử app-only có `Jobs.Run` và đúng caller allowlist → endpoint internal được phép.
9. Thử tenant B truy cập dữ liệu tenant A → từ chối.
10. Xác minh không có token/PII trong request logs hoặc traces.

### Phần D — Triển khai và vận hành

1. Chọn Azure App Service/Container Apps/AKS lab.
2. Cấp configuration từ environment/secret store, không hard-code identifiers khác môi trường.
3. Kiểm tra TLS/ingress/private network và egress metadata/JWKS.
4. Gắn managed identity cho downstream Storage/SQL nếu workload cần.
5. Bật Azure Monitor/App Insights và security metrics redacted.
6. Thiết kế alert khi 401/403 tăng bất thường hoặc JWKS refresh fail.
7. Test CORS/CSRF behavior với frontend thật.
8. Thiết lập CI/CD test với signed local JWT fixture.
9. Chạy security review: permissions, consent, RBAC, tenant isolation.
10. Dọn resources lab đúng quyền, lưu lại lessons learned và runbook.

## 36. Câu hỏi tự kiểm tra

**Câu 1.** OAuth2 access token khác OIDC ID token ở mục đích và audience thế nào?

**Câu 2.** Vì sao Spring Boot API không được tin việc frontend đã đăng nhập?

**Câu 3.** Azure app registration của API và SPA có nên tách riêng không, và vì sao?

**Câu 4.** Delegated scope và application app role khác nhau thế nào?

**Câu 5.** Vì sao client credentials token thường không có `scp` và không đại diện user?

**Câu 6.** Token được cấp qua `/oauth2/v2.0` có luôn là access token v2 không?

**Câu 7.** Issuer và audience cần kiểm tra điều gì? Có thể bỏ audience khi issuer đúng không?

**Câu 8.** Vì sao token Microsoft Graph hoặc ID token không được dùng gọi Orders API?

**Câu 9.** `iss`, `tid`, `oid` và `sub` khác nhau ra sao?

**Câu 10.** `name`/`email` có phù hợp làm khóa ownership lâu dài không?

**Câu 11.** Chỉ decode JWT có xác minh chữ ký được không?

**Câu 12.** Resource Server lấy public signing keys từ đâu và xử lý key rotation thế nào?

**Câu 13.** Vì sao không tin URL `jku` do token tự khai báo?

**Câu 14.** `issuer-uri` có tự bảo đảm audience check trong mọi Spring Boot version không?

**Câu 15.** `scp` và `roles` được Spring Security chuyển thành authorities như thế nào?

**Câu 16.** `hasAuthority("SCOPE_Orders.Read")` khác `hasRole("Orders.Read")` thế nào?

**Câu 17.** Một token có `Orders.Read` có đủ cho phép đọc mọi OrderId không? Vì sao?

**Câu 18.** Cặp `(tid, oid)` có vai trò gì trong multi-tenant owner policy?

**Câu 19.** 401 khác 403; khi nào BOLA có thể trả 404?

**Câu 20.** CSRF có thể được tắt trong điều kiện nào, và CORS có thay auth không?

**Câu 21.** Tại sao không nên đưa bearer token vào URL hoặc request logs?

**Câu 22.** Managed identity của worker có tự được API chấp nhận khi chưa có app role assignment không?

**Câu 23.** Khi Orders API cần gọi Graph thay user, vì sao phải OBO thay vì forward token?

**Câu 24.** Vì sao `/common` không nên là expected issuer cố định cho mọi multi-tenant token?

**Câu 25.** Spring Security MockMvc `jwt()` có chứng minh signature/audience/issuer validation không?

**Câu 26.** Một JWT đã verify offline có tự bị vô hiệu ngay khi user logout không?

**Câu 27.** Vì sao group overage cần được xử lý có chủ đích?

**Câu 28.** APIM validate JWT có tự thay kiểm tra ownership ở database không?

**Câu 29.** Những metrics nào giúp phân biệt issuer mismatch với thiếu API scope?

**Câu 30.** Điều gì nên làm khi 401 tăng đột biến sau key rotation thay vì tắt security?

**Tiêu chí hoàn thành:** người học giải thích đúng OAuth2/OIDC và token purpose, cấu hình API/client app registrations, triển khai Spring Resource Server xác minh issuer/audience/signature/lifetime, map scopes/app roles, enforce tenant/owner authorization, có test negative và kế hoạch logging/monitoring/incident response.

## Kết luận

**Bảo vệ REST API bằng Microsoft Entra access token** không phải chỉ kiểm tra xem request có header `Authorization: Bearer`. Một Spring Boot API đúng nghĩa **OAuth2 Resource Server** phải xác minh **chữ ký, issuer, audience và thời hạn** của access token, sau đó cấp phép theo **delegated scopes, application roles, tenant/client restrictions và ownership của dữ liệu**. JWT hợp lệ chỉ chứng minh token phù hợp với những điều kiện đã kiểm tra, không thay thế authorization nghiệp vụ.

Khi triển khai trên Azure App Service, Container Apps hoặc AKS, cần kết hợp **Entra app registration/consent, Spring Security 6, managed identity, HTTPS/private networking, trusted JWKS refresh, 401/403 tests, chống BOLA, token redaction, Azure Monitor và cost controls**. Có thể bắt đầu từ single-tenant API nhỏ rồi mở rộng sang multi-tenant hoặc OBO theo yêu cầu, nhưng không bỏ các validation bắt buộc chỉ để request dễ được chấp nhận.

