# 18.9. Phản hồi 403 và phân biệt thiếu quyền với token không hợp lệ

## 1. Bối cảnh: REST Client đã có access token nhưng API vẫn từ chối

Trong Spring Security OAuth 2.0/OIDC Client, sau khi người dùng đăng nhập qua OpenID Provider, ứng dụng Servlet có thể lưu một <code>OAuth2AuthorizedClient</code> và dùng access token của nó để gọi một REST API được bảo vệ.

Một tình huống thường gặp:

1. Người dùng đăng nhập thành công qua OIDC.
2. Spring Security đã tạo <code>Authentication</code> và lưu authorized client.
3. Backend lấy access token qua <code>OAuth2AuthorizedClientManager</code> hoặc <code>@RegisteredOAuth2AuthorizedClient</code>.
4. <code>RestClient</code> gửi request tới Resource Server với header <code>Authorization: Bearer ...</code>.
5. REST API trả **HTTP 403 Forbidden**.

Câu hỏi là: **403 có nghĩa access token hết hạn hoặc không hợp lệ, hay token hợp lệ nhưng không đủ quyền?**

Đây là hai loại sự cố khác nhau và cần cách xử lý khác nhau:

- Nếu token không hợp lệ/hết hạn, Client có thể cần refresh, xin lại token hoặc bắt đầu authorization flow mới.
- Nếu token hợp lệ nhưng thiếu scope, role, permission hoặc quyền với đối tượng dữ liệu, việc refresh cùng token với cùng quyền **không tự khắc phục được**.
- Nếu 403 đến từ CSRF filter, reverse proxy, WAF hoặc chính backend ứng dụng, không nên quy nó thành lỗi của access token từ OpenID Provider.

> **Thông điệp chính:** Với OAuth 2.0 Bearer Token, tín hiệu chuẩn quan trọng là **HTTP status + <code>WWW-Authenticate</code> challenge + ngữ cảnh endpoint**. Không kết luận “token không hợp lệ” chỉ từ HTTP 403.

Bài này giải thích cách phân biệt và xử lý response từ REST API khi **Spring Security OAuth2 Client trên Servlet** là bên gọi. Để hiểu chính xác nguyên nhân, bài cũng xem Resource Server bên nhận token thường quyết định 401/403 như thế nào.

## 2. Phân biệt authentication và authorization

Hai câu hỏi bảo mật liên quan nhưng độc lập:

**Authentication — Xác thực:** Request có mang credential hợp lệ, có thể xác định chủ thể đang gọi hay không?

**Authorization — Phân quyền:** Chủ thể đã xác thực có được phép thực hiện hành động trên tài nguyên cụ thể hay không?

Ví dụ:

~~~text
GET /api/reports/2026
Authorization: Bearer <access-token>
~~~

Resource Server có thể xử lý:

~~~mermaid
flowchart TD
    A["REST request tới Resource Server"] --> B{"Có Bearer credential phù hợp?"}
    B -->|Không| U["401: cần xác thực / cung cấp credential"]
    B -->|Có| C{"Token có xác minh được không?"}
    C -->|Không: expired, revoked, wrong issuer...| V["401: invalid_token theo Bearer semantics"]
    C -->|Có| D{"Scope, role, policy, ownership có đủ?"}
    D -->|Không| F["403: không được phép"]
    D -->|Có| S["2xx: request được xử lý"]
~~~

Sơ đồ là **mô hình chuẩn điển hình**, không phải cam kết mọi API sẽ luôn trả đúng mã đó. Một gateway có thể trả 403 trước khi request đến Resource Server, một API có thể trả 404 để che giấu tài nguyên không được phép, và một provider triển khai riêng có thể trả JSON lỗi không theo RFC 6750.

### 2.1. Bảng ngữ nghĩa quan trọng

| Tình huống | HTTP thường gặp | Chỉ dấu thêm | Hướng xử lý ở OAuth2 Client |
|---|---|---|---|
| Thiếu Bearer token | **401** | <code>WWW-Authenticate: Bearer ...</code> | Kiểm tra gửi Authorization header và authorized client |
| Access token hết hạn | **401** | <code>error="invalid_token"</code> | Xem khả năng refresh hoặc authorize lại |
| Token bị thu hồi | **401** | Có thể là <code>invalid_token</code> | Không retry vô hạn; lấy token hợp lệ theo grant/policy |
| Sai issuer, audience hoặc chữ ký | **401** | Thường <code>invalid_token</code> | Sửa ClientRegistration/token audience/Resource Server config |
| Token hợp lệ nhưng thiếu scope | **403** | <code>error="insufficient_scope"</code>, có thể có <code>scope="..."</code> | Điều tra quyền đã cấp; có thể cần authorization/consent mới |
| Token hợp lệ, đủ scope nhưng không có role nghiệp vụ | **403** | Có thể không có Bearer error code | Kiểm tra role/authority/permission, không refresh mù |
| Token hợp lệ, user không sở hữu tài nguyên | **403** hoặc **404** | Business policy/ownership | Kiểm tra quyền truy cập object; giữ nguyên chặn truy cập |
| CSRF bị từ chối trong chính ứng dụng web | **403** | Không nhất thiết liên quan <code>WWW-Authenticate</code> | Kiểm tra request method, CSRF token, SecurityFilterChain |
| WAF/API gateway chặn yêu cầu | **403** | Header/body đặc thù gateway | Điều tra gateway/policy mạng |

**Không nên dùng quy tắc “401 = token hết hạn, 403 = thiếu scope” như một công thức tuyệt đối.** Quy tắc đúng hơn là sử dụng ngữ nghĩa của HTTP, Bearer challenge và nguồn phát sinh lỗi.

## 3. RFC 6750 và WWW-Authenticate: nguồn tín hiệu đáng đọc

Theo RFC 6750 về sử dụng Bearer Token, Resource Server có thể dùng header <code>WWW-Authenticate</code> để báo cho Client biết cơ chế xác thực và lỗi liên quan.

### 3.1. Token không hợp lệ: invalid_token

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api", error="invalid_token", error_description="The access token expired"
Cache-Control: no-store
~~~

<code>invalid_token</code> bao gồm các trường hợp token **hết hạn**, **bị thu hồi**, **không hợp lệ về cấu trúc** hoặc không được Resource Server chấp nhận. Không thể từ riêng <code>invalid_token</code> kết luận nguyên nhân chắc chắn là <code>exp</code>.

Một ví dụ khác:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api", error="invalid_token"
~~~

Resource Server không bắt buộc tiết lộ chi tiết nhạy cảm về lý do từ chối. Client phải tôn trọng thông tin nó nhận được, không tự bịa một nguyên nhân cụ thể.

### 3.2. Token hợp lệ nhưng thiếu quyền: insufficient_scope

Ví dụ:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="reports-api", error="insufficient_scope", scope="reports.write"
~~~

Ý nghĩa:

- Resource Server đã nhận một credential Bearer nhưng quyền nó đại diện **không đủ cho thao tác**.
- <code>scope="reports.write"</code> mô tả scope Resource Server yêu cầu hoặc gợi ý theo cơ chế Bearer.
- Client không được xem chuỗi scope đó như một mệnh lệnh để tự động xin mọi quyền mà API đề xuất.

Trong RFC 6750, <code>insufficient_scope</code> dùng HTTP **403**; tham số <code>scope</code> trên challenge là tùy chọn. Resource Server có thể không tiết lộ scope cần thiết nếu chính sách không cho phép.

### 3.3. Thiếu credential

Ví dụ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="reports-api"
~~~

Ở trường hợp request **không hề có authentication information**, RFC 6750 lưu ý server không nên thêm error code mô tả token sai vì thực chất chưa có token để đánh giá.

Do đó <code>401</code> không nhất thiết đồng nghĩa <code>invalid_token</code>: có thể Client quên gửi header, HTTP client interceptor chưa được gắn, hoặc request đến nhầm endpoint cần authentication khác.

### 3.4. Bearer request sai cách: invalid_request

Ví dụ sử dụng token sai cú pháp hoặc gửi token theo nhiều phương thức cùng lúc có thể dẫn tới:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

Đây là **lỗi request mang Bearer token tới Resource Server**, khác với <code>invalid_request</code> mà Token Endpoint có thể trả trong OAuth2 token response. Phải xét endpoint đang gọi là Token Endpoint hay Resource Server.

### 3.5. So sánh ba mã lỗi Bearer cốt lõi

| Mã Bearer error | HTTP thường theo RFC 6750 | Ý nghĩa |
|---|---|---|
| <code>invalid_request</code> | **400** | Request Bearer sai cú pháp/phương thức |
| <code>invalid_token</code> | **401** | Token được cung cấp không được chấp nhận |
| <code>insufficient_scope</code> | **403** | Token không cung cấp quyền cần thiết |

**Các mã này khác với lỗi của Token Endpoint** như <code>invalid_grant</code> hoặc <code>invalid_client</code>. Token Endpoint cấp/refresh token; Resource Server xác minh Bearer token dùng gọi API.

## 4. Đọc chính xác WWW-Authenticate

Các ví dụ trong tài liệu thường hiển thị một challenge:

~~~http
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

Trong HTTP thực tế, header có thể:

- Có nhiều <code>WWW-Authenticate</code> field hoặc nhiều challenge.
- Chứa các tham số có/không có dấu ngoặc kép theo syntax cho phép.
- Có khoảng trắng không cố định.
- Chứa <code>error_description</code> với dấu phẩy hoặc ký tự cần được quoted.
- Có scheme khác bên cạnh Bearer, ví dụ Basic.

Vì vậy **không nên tự parse challenge bằng <code>split(",")</code> hoặc <code>contains("invalid_token")</code> rồi dùng kết quả như quyết định bảo mật**. Nếu cần phân loại chính xác theo challenge, nên dùng parser đúng HTTP authentication grammar hoặc cơ chế hỗ trợ của thư viện/HTTP client đang sử dụng.

Trong lớp chẩn đoán:

1. Đọc **tất cả** header <code>WWW-Authenticate</code> có liên quan.
2. Phân biệt scheme <code>Bearer</code> với Basic hoặc scheme riêng.
3. Đọc tham số <code>error</code> trong đúng Bearer challenge.
4. Giữ HTTP status để kiểm tra ý nghĩa kết hợp.
5. Không phản chiếu <code>error_description</code>, <code>error_uri</code> hoặc toàn bộ header thô cho frontend.

**Lưu ý:** Header đến từ Resource Server/gateway vẫn là dữ liệu đầu vào của hệ thống bên ngoài. Không cho header đó quyết định trực tiếp thay đổi privilege, scopes hoặc redirect URL.

## 5. HTTP 403 không phải lúc nào cũng là insufficient_scope

HTTP status 403 có nghĩa server đã hiểu request nhưng **từ chối thực hiện**. Lý do không bắt buộc thuộc OAuth 2.0.

### 5.1. Thiếu scope

Ví dụ Client có:

~~~text
granted scopes: reports.read
request:        POST /reports/approve
required scope: reports.approve
~~~

Resource Server có thể trả:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.approve"
~~~

Nếu access token còn hạn và hợp lệ, refresh token grant thông thường **không tự nâng scope được cấp**. Muốn quyền mới, ứng dụng có thể cần quy trình cấp quyền/consent mới với những scope hợp lệ, được người dùng và Authorization Server cho phép, hoặc người quản trị phải cấp permission theo chính sách.

### 5.2. Thiếu role/authority nghiệp vụ

Ví dụ access token đã có <code>reports.read</code>, nhưng user không có role <code>FINANCE_REVIEWER</code> để xem báo cáo tài chính.

Resource Server có thể từ chối 403 mà **không** gắn <code>insufficient_scope</code>. Lúc này cần kiểm tra:

- Role/permission từ hệ thống ủy quyền nội bộ.
- Cách chuyển role/claim thành <code>GrantedAuthority</code>.
- Chính sách ABAC/RBAC, tenant, phòng ban, dữ liệu được phép xem.
- Việc quyền mới có hiệu lực ngay hay cần cập nhật session/entitlement cache.

Đừng tự chuyển 403 này thành <code>invalid_token</code>.

### 5.3. Thiếu quyền trên một đối tượng cụ thể

Ví dụ người dùng có role <code>REPORT_VIEWER</code> nhưng chỉ được xem report của chi nhánh A. Request xem report thuộc chi nhánh B có thể bị 403.

Một số API cố ý trả **404** để không tiết lộ tài nguyên tồn tại. Đây là lựa chọn authorization của API; Client không nên dùng 403/404 làm cơ chế thăm dò dữ liệu ngoài quyền.

### 5.4. CSRF trong chính ứng dụng Servlet

Nếu Spring MVC có session-based authentication và CSRF protection, một request POST/PUT/DELETE thiếu CSRF token hợp lệ có thể bị Spring Security chặn bằng 403 **trước khi bất kỳ REST Client nào gọi downstream API**.

Ví dụ:

~~~text
Browser --POST /payments--> Spring MVC + CSRF Filter
                              |
                              +-- 403 do CSRF

Browser --GET /reports--> Spring MVC --RestClient--> Resource Server
                                              |
                                              +-- 403 do policy API
~~~

Hai HTTP 403 có cùng status nhưng **nguồn phát sinh khác nhau**. Không giải quyết CSRF bằng cách refresh access token. Cũng không tắt CSRF toàn cục chỉ vì muốn tránh một response 403 nếu ứng dụng đang dùng session/cookie.

### 5.5. Gateway, reverse proxy, WAF và chính sách mạng

API gateway có thể trả 403 vì:

- IP/region hoặc network policy.
- API key/service identity sai.
- Rate limit hoặc quota được gateway thể hiện bằng mã 403.
- WAF đánh dấu request đáng ngờ.
- Đường dẫn/tenant route không được phép.

Nhiều response loại này không có <code>WWW-Authenticate: Bearer ...</code>, hoặc có header riêng của gateway. Phân loại cần biết **request đã đến Resource Server hay bị chặn ở tầng trước**.

### 5.6. CORS và browser

<code>RestClient</code> trong Spring Boot chạy **server-side**, không chịu CORS enforcement của browser khi backend gọi API. CORS phát sinh khi **browser trực tiếp** gọi domain khác hoặc ở gateway xử lý preflight.

Nếu browser báo “CORS error”, cần xác định request thực tế:

- Browser → backend Servlet: có thể liên quan CORS/CSRF ở backend.
- Backend <code>RestClient</code> → API: là HTTP server-to-server; chẩn đoán bằng status/header/response trực tiếp.

Không cấu hình CORS rộng hơn chỉ để xử lý một 403 từ backend REST Client.

## 6. Dòng xử lý trên Servlet OAuth2 Client

Để tránh lẫn trách nhiệm, hãy tách hai hệ thống:

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant WEB as Spring MVC / OAuth2 Client
    participant M as Authorized Client Manager
    participant RS as Resource Server

    B->>WEB: GET /my/reports
    WEB->>M: authorize hoặc load authorized client cho principal hiện tại
    M-->>WEB: Access token phù hợp
    WEB->>RS: GET /api/reports + Authorization: Bearer ...
    alt Token bị từ chối
        RS-->>WEB: 401 + Bearer invalid_token
        WEB->>WEB: Phân loại authentication failure
        WEB-->>B: Thông báo/recovery theo policy
    else Token hợp lệ nhưng thiếu quyền
        RS-->>WEB: 403 + Bearer insufficient_scope hoặc policy 403
        WEB->>WEB: Phân loại authorization failure
        WEB-->>B: 403 hoặc lỗi nghiệp vụ phù hợp
    else Request hợp lệ và đủ quyền
        RS-->>WEB: 200 dữ liệu
        WEB-->>B: 200 kết quả ứng dụng
    end
~~~

**OIDC Login thành công không chứng minh API được phép truy cập.** ID Token xác nhận danh tính cho Client; access token được cấp cho resource/scope riêng. Backend phải sử dụng đúng token và Resource Server phải tự kiểm tra credential cũng như quyền.

### 6.1. Những dữ liệu cần quan sát

Để tìm nguyên nhân:

- <code>registrationId</code> của authorized client.
- <code>principalName</code> của người dùng hiện tại (ghi theo chính sách riêng tư).
- Token expiry; có/không có refresh token (không in token value).
- Scope được cấp trong <code>OAuth2AccessToken.getScopes()</code>.
- HTTP method, API path đã chuẩn hóa và status.
- Giá trị <code>error</code> trong Bearer challenge nếu parse được.
- Correlation ID giữa backend, gateway và Resource Server.

Không coi scopes trong ClientRegistration là **scopes đã được cấp**: Client có thể yêu cầu nhiều scope nhưng Authorization Server cấp ít hơn. Để biết granted scope theo authorized client, đọc access token metadata do OAuth2 Client nhận được.

## 7. Spring Security Resource Server thường trả 401 và 403 ra sao?

Mặc dù bài tập trung vào Servlet OAuth2 **Client**, hiểu hành vi Resource Server giúp chẩn đoán chính xác.

### 7.1. Resource Server xác minh Bearer token

Với Spring Security Resource Server dùng JWT:

~~~java
package example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/reports/write/**")
                    .hasAuthority("SCOPE_reports.write")
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Để minh họa đầy đủ, Resource Server còn cần dependency và cấu hình issuer:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/company
~~~

Code dùng Spring Boot 3/Spring Security 6; endpoint, issuer và scope là ví dụ. Trong production còn phải quyết định **audience validation**, algorithm/key trust, tenant isolation và authorization chính xác. Cấu hình <code>issuer-uri</code> cơ bản không mặc nhiên xác minh audience của mọi API; nếu API yêu cầu audience cụ thể, cần cấu hình validator phù hợp.

Với JWT Resource Server mặc định, các scope thường được chuyển thành authorities có prefix <code>SCOPE_</code>. Do đó:

~~~java
.hasAuthority("SCOPE_reports.write")
~~~

khác với:

~~~java
.hasRole("REPORTS_ADMIN")
~~~

Role nghiệp vụ và scope là hai cơ chế authorization khác nhau. Nếu API dùng custom converter để map claim hoặc dùng opaque token introspection, authorities thực tế có thể khác; không tự giả định mọi token có cấu trúc JWT hoặc mọi provider dùng claim <code>scope</code> giống nhau.

### 7.2. Token không hợp lệ

Nếu chữ ký, issuer, expiry hoặc những điều kiện token validation được cấu hình không đạt, Resource Server không tạo authentication hợp lệ; response thường là 401 với Bearer authentication entry point.

Nếu user chưa được xác thực hợp lệ, API không nên tạo 403 <code>insufficient_scope</code> chỉ để che giấu việc token không thể xác minh.

### 7.3. Token hợp lệ nhưng thiếu SCOPE

Nếu JWT hợp lệ có <code>scope="reports.read"</code> nhưng yêu cầu ghi cần <code>SCOPE_reports.write</code>, Resource Server có thể trả 403. Với cấu hình Bearer authorization failure thông thường, Spring Security có thể thêm <code>WWW-Authenticate</code> với <code>error="insufficient_scope"</code>.

Không dựa vào việc response luôn chứa <code>scope="reports.write"</code>: header scope gợi ý là tùy chọn, phụ thuộc configuration/version/implementation của Resource Server.

### 7.4. Controller/domain service cũng có thể quyết định 403

Ví dụ kiểm tra quyền sở hữu:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Report readReport(String reportId, Authentication authentication) {
    // Domain service còn phải kiểm tra report này thuộc tenant nào,
    // user có quyền xem object cụ thể hay không.
    return reportService.readAuthorized(reportId, authentication);
}
~~~

Snippet mô tả lớp authorization thứ hai. Thực tế cần bật <code>@EnableMethodSecurity</code> và để domain service kiểm tra quyền đối tượng trước khi trả dữ liệu. **Scope cho phép loại hành động**, nhưng thường chưa đủ để chứng minh quyền trên từng report.

## 8. Cấu hình OAuth2 Client dùng RestClient trong Servlet

Ví dụ backend Servlet đăng nhập OIDC, sau đó gọi Reports API.

### 8.1. Dependencies và registration

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: reports-web
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company

app:
  reports:
    base-url: https://api.example.org
~~~

<code>reports.read</code> chỉ là scope minh họa, phải được Authorization Server cấp cho đúng API. Access token được cấp cho một UserInfo endpoint có thể không dùng được cho Reports API vì **audience** khác.

Secret thật phải nằm trong biến môi trường/secret manager. Cấu hình không bảo đảm API tự động chấp nhận token: Resource Server vẫn xác minh issuer, audience, scope và policy của nó.

### 8.2. SecurityFilterChain cho web login

~~~java
package example.web;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Trong kiến trúc này:

- <code>oauth2Login()</code> thực hiện Authorization Code Flow và OIDC authentication.
- <code>oauth2Client()</code> hỗ trợ OAuth2 Client trong Servlet context khi ứng dụng dùng authorized client gọi API.
- Authentication của browser được giữ theo security context/session phù hợp.
- Access token dùng gọi REST API được lưu trong authorized client storage theo registration/principal.

Đừng tắt CSRF chỉ vì ứng dụng có OAuth2 Client; đối với form/session-based web app, CSRF và Bearer token ở API là những lớp bảo vệ khác nhau.

## 9. Ví dụ Java: gọi API và phân loại 401/403

Để tập trung vào phản hồi HTTP, ví dụ sử dụng <code>RestClient</code> với access token đã được Spring Security resolve. Với Spring Framework 6.1+ (ví dụ Spring Boot 3.2+), <code>RestClient</code> hỗ trợ gọi HTTP đồng bộ.

### 9.1. Exception nghiệp vụ không lộ upstream body

Định nghĩa nhóm lỗi mà ứng dụng cần phân biệt:

~~~java
package example.reports;

public enum ReportsApiFailureKind {
    UPSTREAM_AUTHENTICATION_REJECTED,
    UPSTREAM_ACCESS_DENIED,
    UPSTREAM_UNAVAILABLE
}
~~~

~~~java
package example.reports;

public final class ReportsApiException extends RuntimeException {

    private final ReportsApiFailureKind kind;
    private final int upstreamStatus;

    public ReportsApiException(
            ReportsApiFailureKind kind,
            int upstreamStatus,
            Throwable cause) {
        super("Reports API call failed", cause);
        this.kind = kind;
        this.upstreamStatus = upstreamStatus;
    }

    public ReportsApiFailureKind kind() {
        return kind;
    }

    public int upstreamStatus() {
        return upstreamStatus;
    }
}
~~~

Ứng dụng **không đưa raw body của API hoặc Bearer token vào exception message**. Throwable gốc vẫn có thể chứa chi tiết HTTP, nên cần cấu hình logging phù hợp và không tự serialize exception/stack trace ra browser.

### 9.2. ReportsApiClient sử dụng RestClient

~~~java
package example.reports;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.client.ResourceAccessException;

@Service
public class ReportsApiClient {

    private final RestClient restClient;

    public ReportsApiClient(
            RestClient.Builder builder,
            @Value("${app.reports.base-url}") String baseUrl) {
        this.restClient = builder.baseUrl(baseUrl).build();
    }

    public String readReports(OAuth2AuthorizedClient authorizedClient) {
        String accessToken =
            authorizedClient.getAccessToken().getTokenValue();

        try {
            return restClient.get()
                .uri("/v1/reports")
                .headers(headers -> headers.setBearerAuth(accessToken))
                .retrieve()
                .body(String.class);

        } catch (HttpClientErrorException.Unauthorized ex) {
            // HTTP 401: Resource Server không chấp nhận xác thực.
            // Chưa được kết luận chắc chắn do hết hạn.
            throw new ReportsApiException(
                ReportsApiFailureKind.UPSTREAM_AUTHENTICATION_REJECTED,
                ex.getStatusCode().value(),
                ex);

        } catch (HttpClientErrorException.Forbidden ex) {
            // HTTP 403: thường là thiếu quyền hoặc policy từ chối.
            // Không tự refresh hoặc xin scope mới.
            throw new ReportsApiException(
                ReportsApiFailureKind.UPSTREAM_ACCESS_DENIED,
                ex.getStatusCode().value(),
                ex);

        } catch (RestClientResponseException ex) {
            // Các HTTP lỗi khác, như 429/502/503, cần policy riêng.
            throw new ReportsApiException(
                ReportsApiFailureKind.UPSTREAM_UNAVAILABLE,
                ex.getStatusCode().value(),
                ex);

        } catch (ResourceAccessException ex) {
            // Timeout, kết nối bị reset, DNS/TLS... có thể không có HTTP status.
            throw new ReportsApiException(
                ReportsApiFailureKind.UPSTREAM_UNAVAILABLE,
                0,
                ex);
        }
    }
}
~~~

Ví dụ minh họa bước phân loại **status ở tầng HTTP**; nó chưa đọc Bearer challenge để phân biệt chi tiết <code>invalid_token</code>, <code>insufficient_scope</code> hoặc 403 từ gateway. Những trường hợp cần quyết định tinh vi hơn phải bổ sung parser/chính sách đã được kiểm chứng.

Với HTTP status 0, nghĩa là **không nhận được response HTTP hợp lệ**, không phải API đã trả HTTP 0.

Ví dụ trả <code>String</code> để đơn giản, không nên đưa raw response chứa dữ liệu nhạy cảm ra log; production thường dùng DTO được kiểm tra schema và kích thước. RestClient cần được cấu hình connect/read timeout phù hợp.

### 9.3. Controller có authorized client của user hiện tại

~~~java
package example.reports;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {

    private final ReportsApiClient reportsApiClient;

    public ReportsController(ReportsApiClient reportsApiClient) {
        this.reportsApiClient = reportsApiClient;
    }

    @GetMapping("/my/reports")
    public String reports(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient) {

        return reportsApiClient.readReports(authorizedClient);
    }
}
~~~

<code>@RegisteredOAuth2AuthorizedClient("company")</code> resolve authorized client theo registration và principal/request hiện tại. Nếu không có authorized client hoặc không thể authorize, cần xử lý lỗi tại web/security boundary; không lấy token của user khác làm fallback.

Tầng controller không được tự coi 403 của Reports API là “người dùng bị logout”. API từ chối một quyền cụ thể không nhất thiết làm mất hiệu lực OIDC session của ứng dụng.

### 9.4. Chuyển lỗi về browser theo hợp đồng của ứng dụng

~~~java
package example.reports;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ReportsApiExceptionHandler {

    public record ErrorResponse(String code, String message) {}

    @ExceptionHandler(ReportsApiException.class)
    ResponseEntity<ErrorResponse> handle(ReportsApiException exception) {
        return switch (exception.kind()) {
            case UPSTREAM_AUTHENTICATION_REJECTED ->
                ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(new ErrorResponse(
                        "reports_upstream_auth_failed",
                        "Không thể xác thực với dịch vụ báo cáo"));

            case UPSTREAM_ACCESS_DENIED ->
                ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(new ErrorResponse(
                        "reports_access_denied",
                        "Bạn không có quyền xem dữ liệu này"));

            case UPSTREAM_UNAVAILABLE ->
                ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                    .body(new ErrorResponse(
                        "reports_upstream_unavailable",
                        "Dịch vụ báo cáo tạm thời không khả dụng"));
        };
    }
}
~~~

Đây là **một phương án mapping**, không phải quy tắc bắt buộc của mọi API gateway/BFF:

- Backend đã xác thực user tại ứng dụng nhưng không thể xác thực với upstream có thể trả **502** nếu đó là lỗi tích hợp hạ tầng. Không tự trả 401 cho browser rồi buộc user nhập lại mật khẩu.
- Nếu upstream 403 thực sự là quyền **của người dùng hiện tại**, ứng dụng có thể trả **403** theo API contract.
- Nếu 403 là lỗi **service credential của backend** hoặc cấu hình gateway, trả 403 với thông điệp “Bạn không có quyền” sẽ sai; nên phân loại thành lỗi upstream/integration trước khi map.
- Không chuyển toàn bộ <code>WWW-Authenticate</code> của upstream hoặc exception stack trace trực tiếp sang browser.

Trong ứng dụng thật, cần thêm handling an toàn cho các lỗi connection/TLS, response JSON sai schema và telemetry. Ví dụ trên chỉ tập trung vào phân biệt authentication/authorization.

## 10. Quan sát challenge trong RestClient exception

Đối với lỗi 401/403, <code>RestClientResponseException</code> cho phép đọc HTTP response headers, ví dụ:

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.web.client.RestClientResponseException;

HttpHeaders responseHeaders = exception.getResponseHeaders();
if (responseHeaders != null) {
    var challenges =
        responseHeaders.get(HttpHeaders.WWW_AUTHENTICATE);

    // Các challenge này cần được parse theo HTTP authentication grammar
    // nếu muốn biết Bearer error="invalid_token"/"insufficient_scope".
}
~~~

<code>exception</code> ở đây là một <code>RestClientResponseException</code> nhận được từ RestClient. <code>challenges</code> có thể là <code>null</code> hoặc danh sách rỗng.

Trong thực tế:

~~~text
401 + Bearer invalid_token
    → Xác thực access token bị từ chối

403 + Bearer insufficient_scope
    → Resource Server yêu cầu quyền/scope mà token chưa có

403 + không có Bearer challenge
    → Kiểm tra business policy, gateway, WAF, app route, CSRF...
~~~

Đừng hiển thị raw <code>error_description</code> cho user hoặc dùng <code>error_uri</code> từ header để tạo redirect chưa kiểm tra; đây là dữ liệu điều khiển bởi upstream.

## 11. Khi nào nên refresh hoặc xin token mới?

Đây là quyết định dễ gây lỗi nhất nếu chỉ dựa trên HTTP status.

### 11.1. Trường hợp 401 invalid_token

Nếu Resource Server đáng tin trả 401 với Bearer <code>invalid_token</code>:

1. Kiểm tra API đích có đúng audience/issuer và token có phải được cấp cho API đó không.
2. Kiểm tra token đã hết hạn hoặc bị thu hồi hay chưa.
3. Xác định authorized client còn refresh token hoặc grant có cơ chế xin token mới không.
4. Sử dụng authorized-client manager/provider và storage phù hợp để lấy **token hiện hành**.
5. Chỉ retry request API nếu an toàn và chính sách cho phép; giới hạn số lần.

Đừng giả định cứ gọi <code>manager.authorize()</code> lần nữa sẽ có token khác: manager có thể trả lại authorized client cũ nếu access token chưa đủ gần expiry. Nếu API đã từ chối token mặc dù metadata còn hạn, cần đánh giá **token invalidation** và failure handler của OAuth2 Client integration.

### 11.2. Trường hợp 403 insufficient_scope

Không nên tự động refresh token với cùng refresh token rồi retry nhiều lần. Refresh token grant thường cấp access token tiếp tục phạm vi được phép; nó không tự nâng quyền chỉ vì API đích yêu cầu thêm scope.

Hướng xử lý:

- Kiểm tra scope ClientRegistration đã **yêu cầu**.
- Kiểm tra scope token response thực sự **được cấp**.
- Kiểm tra Resource Server yêu cầu scope nào cho HTTP method/path đang gọi.
- Xác minh user/client có đủ entitlement tại Authorization Server/domain service.
- Nếu sản phẩm hỗ trợ, triển khai **authorization/consent mới** để xin quyền bổ sung theo chính sách.
- Nếu user không được phép, trả lỗi từ chối truy cập rõ ràng; không tìm cách bỏ qua Resource Server.

Nếu user chỉ có quyền đọc, yêu cầu <code>reports.write</code> từ header không tự biến họ thành người được phép ghi.

### 11.3. Trường hợp 403 không có chỉ dấu OAuth

Không được tự xóa authorized client hoặc logout user. Điều tra gateway, CSRF, endpoint, tenant, role và business policy.

Nếu bản thân proxy/BFF đang gọi API bằng **client credentials token** và upstream từ chối vì service thiếu quyền, người dùng cuối không thể giải quyết bằng đăng nhập lại OIDC.

### 11.4. Ma trận retry

| Tình huống | Refresh/reauthorize? | Retry API tự động? |
|---|---|---|
| 401 Bearer <code>invalid_token</code> do expiry, có grant phù hợp | Có thể | Chỉ khi có token mới, request an toàn và số lần giới hạn |
| 401 token sai audience/issuer | Sửa registration/token acquisition | Không retry mù với token cũ |
| 401 không có Bearer challenge, có thể bị gateway chặn | Điều tra nguồn lỗi | Không tự xóa token |
| 403 Bearer <code>insufficient_scope</code> | Có thể cần cấp scope mới/consent theo policy | Không tự retry cùng token |
| 403 thiếu role hoặc quyền object | Không giải quyết bằng refresh | Không retry như lỗi tạm thời |
| 403 CSRF của ứng dụng web | Sửa request CSRF/session | Không liên quan refresh OAuth |
| 403 WAF/gateway | Điều tra gateway/network policy | Không tự xin token rộng hơn |
| 429/503 từ API | Không nhất thiết liên quan token | Bounded retry/backoff nếu request idempotent |

### 11.5. Thận trọng với các request thay đổi trạng thái

Với GET idempotent, một lần retry sau khi lấy token khác có thể chấp nhận được. Nhưng với POST tạo hóa đơn, chuyển tiền hoặc thay đổi dữ liệu, backend có thể đã xử lý một phần trước khi Client thấy timeout.

Không retry vô hạn hoặc tự retry POST mà không có cơ chế idempotency/transaction correlation. Refresh token và retry business request là hai vấn đề riêng.

## 12. OAuth2AuthorizedClientManager và xử lý authorized client thất bại

Spring Security có:

- <code>OAuth2AuthorizedClientManager</code> để điều phối authorize/refresh.
- <code>OAuth2AuthorizedClientService</code> hoặc <code>OAuth2AuthorizedClientRepository</code> để lưu trạng thái.
- <code>OAuth2AuthorizationFailureHandler</code> làm điểm mở rộng xử lý authorization failure theo cấu hình.
- Những HTTP integration cho phép gắn Bearer token và chuyển thông tin Resource Server failure tới failure handler ở các phiên bản tương ứng.

Điểm cần hiểu:

> **Manager chỉ biết token nào đang được cấp/lưu. Nếu bạn gọi RestClient thủ công và không nối response 401/403 vào cơ chế failure handling, manager không thể tự biết downstream API vừa từ chối token.**

Khi dùng một HTTP integration tích hợp sẵn của Spring Security, có thể cấu hình behavior khi Resource Server trả invalid token. Nhưng phải kiểm tra API của **đúng phiên bản Spring Security** đang chạy, vì các class/hook và mặc định có thay đổi qua các bản.

### 12.1. Failure handler không nên xóa token vì mọi 403

Giả sử user có token hợp lệ với scope <code>reports.read</code>. API từ chối POST bằng 403 <code>insufficient_scope</code>. Nếu Client xóa authorized client mỗi khi thấy 403, nó có thể tạo vòng lặp:

~~~text
403 insufficient_scope
    → xóa authorized client
    → user đăng nhập lại / token mới có cùng scope reports.read
    → POST lại
    → 403 insufficient_scope
    → lặp...
~~~

Vấn đề là **thiếu quyền**, không phải token bị lỗi cấu trúc. Cách đúng là đối chiếu scope/role/policy và xử lý quyền bổ sung theo hợp đồng.

### 12.2. Vì sao không xóa không điều kiện sau 401?

Trên môi trường nhiều instance:

~~~text
Instance A dùng access token A0, API trả 401
Instance B refresh và lưu authorized client mới A1/R1
Instance A thấy lỗi, gọi removeAuthorizedClient không điều kiện
~~~

Nếu A xóa theo registration/principal mà không kiểm tra phiên bản, nó có thể xóa **token mới vừa lưu của B**. Trong hệ thống dùng refresh token rotation, lỗi này có thể làm mất refresh token mới và buộc user đăng nhập lại.

Với storage chia sẻ, cần xem xét:

- Conditional delete hoặc compare-and-set theo version token state.
- Load lại authorized client mới nhất trước khi remove/retry.
- Xử lý invalid-token failure đồng bộ với refresh coordinator.
- Giới hạn reauthorize/retry và không dùng token cũ đã bị từ chối.

Không chỉ dùng một static lock ở JVM rồi xem như đã giải quyết tất cả race giữa nhiều replica.

### 12.3. Không biến 403 thành 401 trong Resource Server

Một số developer muốn luôn trả 401 khi truy cập bị từ chối để browser tự đăng nhập lại. Nếu token đã hợp lệ và người dùng thiếu quyền, trả 401 sai ngữ nghĩa và có thể tạo login loop.

Với Resource Server:

- Authentication thất bại hoặc không có credential hợp lệ → 401 theo Bearer semantics.
- Authentication thành công nhưng authorization không đạt → 403.

Nếu custom entry point/access denied handler, cần bảo toàn hai trường hợp này và không tiết lộ dữ liệu nhạy cảm trong response.

## 13. Scope được yêu cầu khác scope được cấp

Trong ClientRegistration:

~~~yaml
scope:
  - openid
  - profile
  - reports.read
  - reports.write
~~~

Đây là **danh sách Client muốn yêu cầu**, không chứng minh Authorization Server đã cấp đủ cho từng người dùng.

Sau khi token exchange, <code>OAuth2AccessToken.getScopes()</code> mới là một nguồn metadata về **scope được trả trong token response** (tùy hành vi provider/implementation). Ví dụ:

~~~java
Set<String> grantedScopes =
    authorizedClient.getAccessToken().getScopes();

boolean mayHaveReadScope = grantedScopes.contains("reports.read");
boolean mayHaveWriteScope = grantedScopes.contains("reports.write");
~~~

Không dùng biến <code>mayHaveWriteScope</code> làm quyết định authorization cuối cùng của API. Resource Server vẫn phải xác minh token và chính sách quyền cho từng request.

Lưu ý thêm:

- Một access token JWT có claim <code>scope</code>/<code>scp</code> theo định dạng provider.
- Một opaque token có thể cần introspection tại Resource Server.
- Provider có thể trả granted scopes theo token response hoặc quy tắc riêng.
- Scope có thể chỉ là một lớp điều kiện; role, tenant, ABAC hoặc ownership cũng ảnh hưởng 403.

### 13.1. User đã OIDC Login nhưng không có access token đúng API

Nếu <code>scope: [openid, profile]</code> dành cho đăng nhập, access token có thể chỉ phù hợp gọi UserInfo Endpoint. Gửi nó tới Reports API có thể bị 401 vì audience sai hoặc 403 vì không đủ quyền.

Việc nhận ID Token thành công **không làm access token tự có quyền truy cập mọi API**. Cần ClientRegistration/resource authorization phù hợp với hệ thống IdP/API.

### 13.2. Role nội bộ thay đổi sau login

Nếu ứng dụng hoặc Resource Server cache roles tại thời điểm đăng nhập, một người vừa được cấp quyền có thể vẫn thấy 403, hoặc người vừa bị thu hồi quyền cần được chặn ngay theo policy.

Đây là vấn đề synchronization/cache authorization. Refresh access token có thể hoặc không cập nhật claim quyền tùy Authorization Server; không xem refresh như một cách cưỡng bức đồng bộ role đáng tin cậy trong mọi hệ thống.

## 14. REST Client trực tiếp và Spring OAuth2 Client interceptor

Có hai cách chung để gửi Bearer token:

**Cách 1 — Tự lấy authorized client và set Bearer header.**

~~~java
headers.setBearerAuth(
    authorizedClient.getAccessToken().getTokenValue());
~~~

Cách này dễ thấy rõ HTTP boundary nhưng ứng dụng phải chịu trách nhiệm xử lý 401/403 và refresh/retry phù hợp.

**Cách 2 — Dùng HTTP client integration của Spring Security.**

Ở các bản Spring Security hỗ trợ, ví dụ Spring Security 6.4+, có <code>OAuth2ClientHttpRequestInterceptor</code> cho <code>RestClient</code>. Interceptor có thể dùng authorized client manager để chèn access token theo registration/principal resolver phù hợp, và cho phép tích hợp failure handling khi Resource Server từ chối token.

Không nên copy code cấu hình interceptor từ phiên bản Spring Security khác mà chưa kiểm tra API. Ngoài ra:

- Chọn registration ID tin cậy, không lấy từ query parameter tùy ý.
- Dùng Authentication hiện tại hoặc principal tổng hợp phù hợp grant.
- Xác định behavior của failure handler cho <code>invalid_token</code>.
- Không chuyển <code>insufficient_scope</code> thành “xin token mới không giới hạn”.
- Không retry POST/PUT tự động nếu không có bảo đảm idempotency.

Điều quan trọng không phải interceptor nào “thông minh” hơn, mà là **có một vị trí nhất quán để áp dụng token lifecycle, authentication failure và authorization failure**.

## 15. Phân biệt lỗi từ ba boundary HTTP

Trong ứng dụng Servlet làm Backend For Frontend (BFF), cùng một HTTP status 403 có thể xuất hiện ở ba nơi:

~~~mermaid
flowchart LR
    B["Browser"] --> APP["Spring MVC / SecurityFilterChain"]
    APP --> CLIENT["RestClient + authorized client"]
    CLIENT --> G["API Gateway"]
    G --> RS["Resource Server"]
    APP --> A["403 tại web app: role/CSRF"]
    G --> GW["403 tại gateway: WAF/network/API key"]
    RS --> R["403 tại Resource Server: scope/policy/object"]
~~~

### 15.1. Browser → web app

Nếu browser nhận 403 trực tiếp từ Spring MVC, cần xác định request có được phép vào controller không:

- CSRF filter có từ chối trước controller?
- <code>authorizeHttpRequests</code> hoặc <code>@PreAuthorize</code> có từ chối?
- SecurityFilterChain nào xử lý request?
- Session/principal có còn hợp lệ?

Không chẩn đoán bằng cách xem token tới downstream nếu request chưa bao giờ được gọi đến đó.

### 15.2. Web app → gateway

Nếu RestClient nhận 403, cần biết có reverse proxy/gateway trước Resource Server hay không. Có thể kiểm tra correlation ID và log an toàn của gateway, không tự động gửi lại access token nhiều lần.

### 15.3. Gateway → Resource Server

Nếu Resource Server tạo response, kiểm tra Bearer challenge, token validation, scope-to-authority mapping và business authorization. Giữ tách biệt mã lỗi nội bộ của API với error code chuẩn OAuth 2.0.

### 15.4. Cẩn trọng với exception mapping

Một HTTP 403 upstream có thể được backend map thành 502 vì **service integration failure**, hoặc thành 403 vì **người dùng thiếu quyền**. Điều này phụ thuộc API contract và nguồn credential, không nên áp dụng mapping cứng cho mọi route.

Giữ mã lỗi ứng dụng có thể hỗ trợ như <code>reports_access_denied</code> hay <code>upstream_auth_failed</code> giúp frontend xử lý đúng mà không cần nhận toàn bộ dữ liệu nội bộ từ upstream.

## 16. Các kịch bản cụ thể

### 16.1. Access token hết hạn

~~~http
GET /v1/reports HTTP/1.1
Authorization: Bearer ACCESS_TOKEN_PLACEHOLDER
~~~

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token", error_description="expired"
~~~

Diễn giải: Token không còn được API chấp nhận. Nếu authorized client có refresh token hợp lệ và manager được cấu hình refresh, có thể xin token mới. Không kết luận chỉ từ một thông điệp description rằng mọi provider đều có cùng semantics.

### 16.2. Token còn hạn nhưng scope chỉ đọc

~~~http
POST /v1/reports/approve HTTP/1.1
Authorization: Bearer READ_ONLY_TOKEN
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.approve"
~~~

Diễn giải: Người dùng/Client thiếu quyền được yêu cầu. Refresh cùng grant/scope không giải quyết được; cần xem chính sách cấp quyền và authorization flow.

### 16.3. Token hợp lệ, user ngoài tenant

~~~json
{
  "error": "tenant_access_denied",
  "message": "Resource is outside your tenant"
}
~~~

Response HTTP 403 trên là **lỗi nghiệp vụ do API định nghĩa**, không phải mã chuẩn <code>insufficient_scope</code>. Client phải xử lý theo API contract, không chỉ kiểm tra OAuth scope.

### 16.4. Token hợp lệ nhưng bị WAF chặn

~~~http
HTTP/1.1 403 Forbidden
Content-Type: text/html
X-Request-Id: gateway-request-placeholder

<html><body>Request denied</body></html>
~~~

Không parse HTML để tự kết luận Bearer token sai. Điều tra chính sách WAF/gateway, đường dẫn và request ID an toàn.

### 16.5. 403 do CSRF tại web app

~~~text
Browser POST /profile/update
    → Spring Security CSRF filter
    → Thiếu CSRF token
    → 403
~~~

Không cần gọi Token Endpoint hoặc refresh OAuth2AuthorizedClient. Cần sửa client/browser request CSRF tương ứng với cơ chế session.

### 16.6. 401 vì token sai audience

~~~text
Access token được cấp cho UserInfo/API A
REST Client gửi tới Reports API B
Reports API B từ chối token
~~~

Nếu Resource Server kiểm tra audience, API có thể trả 401 Bearer <code>invalid_token</code>. Việc refresh để lấy một token cùng audience cũ **không sửa được** sai cấu hình. Cần ClientRegistration/resource authorization đúng.

## 17. Sai lầm thường gặp khi xử lý 403

| Sai lầm | Vì sao có vấn đề | Cách làm phù hợp |
|---|---|---|
| Thấy 403 là xóa authorized client | Token có thể còn hợp lệ nhưng thiếu role/scope | Phân loại Bearer challenge và policy |
| Thấy 403 là cho user login lại | Đăng nhập lại không tự tạo quyền mới | Kiểm tra authorization/entitlement |
| Tự thêm scope từ header vào request | API không được tự quyết định privilege escalation | Dùng authorization/consent theo chính sách tin cậy |
| Coi mọi 401 là token hết hạn | Có thể sai audience, issuer, không gửi header hoặc gateway auth | Đọc challenge và xác minh registration |
| Coi mọi 403 là insufficient_scope | Có thể CSRF, WAF, role hoặc object ownership | Xác định boundary tạo lỗi |
| Chỉ kiểm tra scope được yêu cầu trong YAML | Scope được cấp có thể ít hơn | Kiểm tra granted scopes và API policy |
| Coi access token có scope là đủ quyền với mọi object | Role/tenant/ownership có thể từ chối | Authorization nghiệp vụ tại Resource Server |
| Retry POST vô hạn sau refresh | Dễ tạo thao tác trùng | Bounded retry và idempotency khi cần |
| Gửi raw Bearer error_description cho frontend | Có thể lộ dữ liệu hoặc gây log injection | Mã lỗi ứng dụng và thông điệp an toàn |
| Tắt CSRF để “sửa 403” của web app | Làm suy yếu session security | Sửa CSRF token/request hoặc cấu hình có chủ đích |
| Gửi ID Token thay access token | ID Token không dành cho Resource Server theo OAuth2 bearer usage | Dùng access token đúng audience |
| Tự decode JWT rồi tin quyền, bỏ signature validation | Không đáng tin khi chưa xác minh | Để Resource Server validate đầy đủ |
| Xóa state token không điều kiện trong multi-instance | Có thể xóa token mới của node khác | Conditional delete/version hoặc coordinator |
| Không đọc HTTP status/header thực | Không biết lỗi từ gateway hay Resource Server | Log status và correlation ID an toàn |

## 18. Quy trình chẩn đoán 403 theo từng bước

Khi <code>RestClient</code> nhận 403:

1. **Xác định đúng request.** HTTP method, API path, registration ID, hệ thống đích, thời điểm, correlation ID.
2. **Xác định nguồn phản hồi.** 403 do browser-facing web app, gateway/WAF hay Resource Server?
3. **Đọc HTTP status và các <code>WWW-Authenticate</code> challenges.** Có Bearer scheme không? Có <code>insufficient_scope</code> không?
4. **Kiểm tra loại credential.** User access token từ Authorization Code hay service token từ Client Credentials? Có đúng API/audience không?
5. **Đối chiếu quyền đã cấp.** Scopes trong authorized client/token response và scope/policy của API.
6. **Đối chiếu role/entitlement/tenant/object ownership.** Không chỉ tập trung vào scopes.
7. **Kiểm tra session và CSRF** nếu 403 được tạo tại chính Servlet app.
8. **Kiểm tra gateway logs** nếu status không có dấu hiệu Bearer và gateway có policy riêng.
9. **Quyết định recovery.** 403 thiếu quyền → trả thông báo quyền hoặc authorization flow hợp lệ; 401 invalid token → token lifecycle; gateway lỗi → vận hành.
10. **Không log token/secret.** Chỉ ghi metadata đã làm sạch.

Sơ đồ quyết định:

~~~text
Nhận HTTP 403
  |
  +-- 403 ở chính Servlet app?
  |       |
  |       +-- Có: kiểm tra SecurityFilterChain, CSRF, method security
  |
  +-- 403 từ downstream API?
          |
          +-- WWW-Authenticate có Bearer insufficient_scope?
          |       |
          |       +-- Có: thiếu scope → điều tra quyền/consent
          |
          +-- Không có Bearer challenge?
                  |
                  +-- API business 403? → role, tenant, object ownership
                  |
                  +-- Gateway/WAF 403? → network/gateway policy
                  |
                  +-- Không xác định? → giữ lỗi an toàn, điều tra thêm
~~~

Nếu nhận **401** thay vì 403, xét nhánh Bearer <code>invalid_token</code> hoặc thiếu authentication. Không nhầm nó với <code>invalid_grant</code> trả từ **Token Endpoint** khi refresh.

## 19. Giám sát lỗi trong production

Để tránh vòng lặp refresh/đăng nhập và phát hiện vấn đề phân quyền, nên theo dõi:

| Metric hoặc log field | Mục đích |
|---|---|
| <code>registrationId</code> | Biết Client/provider tương ứng |
| <code>upstreamService</code> | Phân biệt Reports API, Billing API, gateway |
| <code>httpMethod</code> và route template | Biết endpoint/operation mà không log URL chứa dữ liệu nhạy cảm |
| <code>upstreamStatus</code> | Quan sát 401/403/429/5xx |
| <code>bearerErrorCode</code> đã allowlist | Phân biệt invalid_token, insufficient_scope |
| <code>grantedScopeCategory</code> | Nhìn quyền ở mức tổng hợp nếu chính sách cho phép |
| <code>tokenRefreshAttempted</code> | Phát hiện refresh loop |
| <code>reauthorizationRequired</code> | Theo dõi yêu cầu login/consent lại |
| <code>correlationId</code> | Truy vết qua backend/gateway/API |

Không đưa access token, refresh token, client secret, authorization code, state, nonce, raw ID Token hoặc header <code>Authorization</code> vào log/metric.

Đặc biệt, **không dùng raw <code>error_description</code> làm metric label** vì vừa có thể chứa thông tin nhạy cảm vừa tạo cardinality không giới hạn.

### 19.1. Cảnh báo vòng lặp

Một dấu hiệu bug phổ biến:

~~~text
GET API → 403 insufficient_scope
OAuth2 Client → xóa token
Browser → login
GET API → 403 insufficient_scope
Browser → login
...
~~~

Đây là sự cố phân quyền chứ không phải logout/refresh. Metric số lần login lại và 403 liên tiếp theo registration/route có thể giúp tìm nguyên nhân.

## 20. Bài tập và tình huống thực hành

### Bài 1 — Phân biệt hai response

Response A:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Response B:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

**Câu hỏi:** Hai response khác nhau ở đâu?

**Đáp án:** A cho thấy Bearer token không được chấp nhận; cần đánh giá token lifecycle, audience/issuer, expiry và khả năng refresh. B cho thấy token không đáp ứng quyền/scope mà API yêu cầu; refresh cùng quyền không tự làm token đủ scope.

### Bài 2 — 403 dù đăng nhập OIDC thành công

Người dùng đã login OIDC thành công và <code>OidcUser.getIdToken()</code> hợp lệ, nhưng Reports API trả 403.

**Câu hỏi:** Có thể kết luận ID Token sai không?

**Đáp án:** Không. ID Token phục vụ xác thực danh tính với OIDC Client. Reports API sử dụng access token và authorization riêng. Cần kiểm tra scope, audience, role, tenant, object ownership và nguồn 403.

### Bài 3 — Refresh có sửa được thiếu scope?

Token được cấp <code>reports.read</code> và API yêu cầu <code>reports.approve</code>. Backend có refresh token.

**Câu hỏi:** Có nên refresh liên tục không?

**Đáp án:** Không. Refresh token grant không tự tạo quyền mới. Cần xét lại registration, consent, policy của OP và quyền nghiệp vụ; chỉ xin thêm scope qua flow hợp lệ nếu user/Client được phép.

### Bài 4 — Header vắng mặt

API trả:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: text/html

<html><body>Denied by gateway</body></html>
~~~

**Câu hỏi:** Có đủ bằng chứng về <code>insufficient_scope</code> không?

**Đáp án:** Không. Đây có thể là gateway/WAF policy. Điều tra request path, route, network policy và log gateway; không tự xóa token hoặc yêu cầu user login lại.

### Bài 5 — CSRF

Browser gửi POST tới ứng dụng Servlet dùng session, request bị 403 trước khi controller chạy.

**Câu hỏi:** Điều tra OAuth2AuthorizedClient có phải bước đầu tiên không?

**Đáp án:** Không. Cần xác định SecurityFilterChain, CSRF filter và request có CSRF token đúng không. Đây có thể là 403 tại web app, chưa có RestClient call tới API.

### Bài 6 — Wrong audience

Backend lấy token có audience <code>userinfo-api</code> rồi gửi sang <code>billing-api</code>. API trả 401 <code>invalid_token</code>.

**Câu hỏi:** Có nên refresh chính token đó để dùng lại không?

**Đáp án:** Không nếu token mới vẫn dành cho audience cũ. Cần thay đổi ClientRegistration/token acquisition để nhận token đúng audience, scope và API contract.

### Bài 7 — Phân quyền object

Token có <code>reports.read</code>, user có role REPORT_VIEWER, nhưng report thuộc tenant khác.

**Câu hỏi:** Resource Server có thể trả 403 không?

**Đáp án:** Có. Scope/role không thay thế điều kiện tenant và ownership. Một số API có thể dùng 404 để tránh tiết lộ tài nguyên, tùy hợp đồng.

### Bài 8 — Multi-instance và cleanup

Node A nhận 401 dùng token cũ A0. Cùng lúc node B refresh và lưu A1/R1. Node A muốn gọi <code>removeAuthorizedClient</code>.

**Câu hỏi:** Nguy cơ gì?

**Đáp án:** Xóa không điều kiện theo registration/principal có thể xóa cả A1/R1. Nên đọc lại state, dùng conditional delete/versioning và phối hợp với refresh workflow.

### Bài 9 — Thiết kế REST Client xử lý lỗi

Hãy thiết kế một service có:

1. Spring Security OAuth2 Client registration dùng Authorization Code Flow.
2. Authorized client đúng principal và granted scopes.
3. RestClient gửi Bearer access token đúng Resource Server.
4. Phân loại HTTP 401 và 403, đọc Bearer challenge khi có.
5. Không refresh tự động khi <code>insufficient_scope</code>.
6. Chỉ retry <code>invalid_token</code> nếu có khả năng nhận token mới và request an toàn.
7. Phân biệt 403 từ CSRF/web app với 403 downstream.
8. Trả mã lỗi ứng dụng an toàn cho frontend.
9. Không log raw token, credentials hay upstream error description.

### Bài 10 — Kiểm tra kỳ vọng status

Điền status phù hợp theo RFC 6750 cho các trường hợp Bearer:

| Trường hợp | Đáp án |
|---|---|
| Không cung cấp Bearer credential cho tài nguyên cần xác thực | 401 và Bearer challenge |
| Token Bearer bị từ chối vì không hợp lệ | 401 <code>invalid_token</code> |
| Token có hiệu lực nhưng thiếu scope được yêu cầu | 403 <code>insufficient_scope</code> |
| Request Bearer sai định dạng | 400 <code>invalid_request</code> theo trường hợp |

Lưu ý bài tập áp dụng cho **Bearer semantics chuẩn**, không phủ nhận việc gateway/business API có thể có response riêng.

## 21. Ghi nhớ

- **HTTP 401** thường chỉ vấn đề **authentication**; với Bearer token, <code>invalid_token</code> là tín hiệu token không được Resource Server chấp nhận.
- **HTTP 403** thường chỉ vấn đề **authorization**; <code>insufficient_scope</code> theo RFC 6750 là trường hợp token không đủ scope. Nhưng 403 không mặc định có nghĩa thiếu scope.
- Hãy đọc <code>WWW-Authenticate</code> cùng HTTP status và xác định **nguồn phát sinh**: Servlet app, gateway hay Resource Server.
- **OIDC Login thành công không tự cấp quyền gọi API**. ID Token chứng minh danh tính cho Client; access token phải đúng audience/scope và Resource Server còn kiểm tra policy nghiệp vụ.
- **Refresh token không phải cơ chế tự nâng quyền.** Đối với 403 thiếu quyền, điều tra scopes được cấp, role, tenant, ownership và quy trình consent/authorization hợp lệ.
- <code>RestClient</code> tự gắn Bearer header có thể cần error handling thủ công. Khi dùng OAuth2 Client HTTP integration, kiểm tra failure handler của đúng Spring Security version.
- Không xóa authorized client hoặc ép user đăng nhập lại chỉ vì mọi lỗi 403; không biến CSRF/gateway/business policy 403 thành lỗi token.
- Khi retry sau 401, cần token mới thực sự phù hợp, bounded retry, idempotency và điều phối token state trên nhiều instance.
- Không log access token, refresh token, Client secret hoặc raw upstream error. Trả thông điệp frontend an toàn, giữ thông tin chẩn đoán theo chính sách.

### Tài liệu tham khảo

- **RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage**, mục 3: <code>WWW-Authenticate</code>, <code>invalid_request</code>, <code>invalid_token</code> và <code>insufficient_scope</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework**: phân biệt Authorization Server/Token Endpoint, Resource Server, access token và scopes.
- **Spring Security Reference — OAuth2 Client (Servlet):** <code>OAuth2AuthorizedClient</code>, <code>OAuth2AuthorizedClientManager</code>, <code>@RegisteredOAuth2AuthorizedClient</code> và REST HTTP client integration.
- **Spring Security Reference — OAuth2 Resource Server:** Bearer Token Authentication, JWT/opaque validation, authority mapping và handling lỗi authorization.
- **Spring Security Reference — Servlet Authorization và CSRF Protection:** <code>SecurityFilterChain</code>, <code>authorizeHttpRequests</code>, method security và CSRF.
- **Spring Framework Reference — REST Clients:** <code>RestClient</code>, response status handling và <code>RestClientResponseException</code>.
- **OpenID Connect Core 1.0:** ID Token, OIDC Login, UserInfo và quan hệ với OAuth2 Authorization Code Flow.
