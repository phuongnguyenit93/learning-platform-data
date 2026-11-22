# 23.6. Session phân tán và đồng bộ authorized client giữa các instance

## 1. Bài toán: đăng nhập ở instance A, request tiếp theo đến instance B

Một ứng dụng Spring Security OAuth 2.0/OIDC Client chạy ổn định trên máy phát triển với một tiến trình. Người dùng đăng nhập qua OpenID Provider, Spring Security lưu trạng thái đăng nhập và access token; sau đó backend gọi API thay mặt người dùng.

Khi triển khai production, nhóm vận hành nhân số replica:

~~~text
                  Load Balancer
                 /             \
           Instance A       Instance B
           Spring Boot      Spring Boot
~~~

Một kịch bản lỗi điển hình:

1. Browser bắt đầu OIDC Login trên **instance A**.
2. A tạo authorization request, lưu <code>state</code> trong session của A và redirect sang OpenID Provider.
3. Provider xác thực người dùng và redirect callback về ứng dụng.
4. Load balancer chuyển callback sang **instance B**.
5. B không tìm được authorization request/session mà A đã lưu, nên từ chối callback.

Nếu sticky session làm callback luôn về A, login có thể thành công. Nhưng một vấn đề khác xuất hiện:

1. A lưu authorized client gồm access token và refresh token sau login.
2. Browser gọi <code>GET /reports</code> và load balancer chuyển sang B.
3. B khôi phục được session đăng nhập nhưng **không tìm thấy authorized client** vì token chỉ nằm trong memory của A.
4. Ứng dụng trả lỗi, khởi động authorization flow mới hoặc không gọi được Reports API.

Một vấn đề thứ ba nguy hiểm hơn:

1. A và B cùng đọc một refresh token <code>R0</code> từ kho dùng chung.
2. Access token gần hết hạn, cả hai cùng gửi refresh request tới Token Endpoint.
3. A nhận access token <code>A1</code> và refresh token mới <code>R1</code>.
4. B dùng lại <code>R0</code> và có thể nhận <code>invalid_grant</code> hoặc kích hoạt refresh-token reuse detection.
5. Nếu failure handler của B xóa bản ghi không điều kiện, B có thể xóa cả <code>R1</code> vừa được A lưu.

Ba vấn đề có liên quan nhưng **không được sửa bằng cùng một cấu hình duy nhất**:

- **Session phân tán**: nhiều instance đọc được trạng thái HTTP session và SecurityContext.
- **Authorized-client persistence**: nhiều instance truy cập được đúng access/refresh token của từng ClientRegistration và principal.
- **Điều phối refresh đồng thời**: không để nhiều instance cùng tiêu thụ một refresh token cũ hoặc ghi đè trạng thái token mới.

> **Luận điểm chính:** Chia sẻ HTTP session không tự động bảo đảm token được lưu trong shared authorized-client service; dùng chung database chứa token cũng không tự động ngăn refresh race. Cần xác định đúng từng kho trạng thái, phạm vi chia sẻ và cơ chế cập nhật.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt Web/HTTP session, SecurityContext, OAuth2 authorization request, OAuth2AuthorizedClient và refresh token.
2. Giải thích vì sao callback OIDC có thể lỗi khi request đi qua nhiều replica.
3. Triển khai Spring Session với Redis để chia sẻ phiên Servlet, đồng thời hiểu hướng cấu hình tương ứng trong Reactive WebFlux.
4. Sử dụng <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code> và storage tập trung đúng mục đích.
5. Nhận biết giới hạn của <code>InMemoryOAuth2AuthorizedClientService</code>, <code>HttpSessionOAuth2AuthorizedClientRepository</code> và JDBC/Redis storage.
6. Chọn đúng <code>OAuth2AuthorizedClientManager</code> cho request Servlet/WebFlux và background jobs.
7. Thiết kế điều phối refresh theo authorized-client key bằng lock, đọc lại trạng thái và conditional update/delete.
8. Xử lý logout, revoke token, session expiry, scale-out, failover và ranh giới tenant an toàn.
9. Kiểm thử hành vi qua nhiều node mà không cần log access/refresh token thật.

## 3. Bốn loại dữ liệu thường bị đánh đồng

Trong một OIDC Login ứng dụng web, cần phân biệt **ít nhất bốn trạng thái**.

| Trạng thái | Dữ liệu điển hình | Được tạo lúc nào? | Thành phần Spring Security |
|---|---|---|---|
| **Authorization request tạm thời** | <code>state</code>, redirect URI, PKCE attributes, nonce/correlation data | Khi bắt đầu redirect tới OP | <code>OAuth2AuthorizationRequestRepository</code> / reactive counterpart |
| **HTTP session và SecurityContext** | Session ID, <code>Authentication</code>, <code>OidcUser</code>/principal, authorities | Sau hoặc trong quá trình login | <code>HttpSession</code> / <code>WebSession</code>, SecurityContext repository |
| **Authorized client** | ClientRegistration, principalName, access token, refresh token tùy chọn | Sau token exchange/refresh | <code>OAuth2AuthorizedClientRepository</code> / <code>OAuth2AuthorizedClientService</code> |
| **Trạng thái quyền tại OP/API** | Consent, token revocation, user account, role, entitlement | Do Authorization Server/Resource Server quản lý | **Không thuộc local HTTP session của Client** |

### 3.1. Authorization request khác authorized client

Trước callback:

~~~text
GET /oauth2/authorization/company
    → state, nonce, PKCE verifier ...
    → lưu authorization request
    → redirect browser đến OP
~~~

Sau callback thành công:

~~~text
GET /login/oauth2/code/company?code=...&state=...
    → kiểm tra state và correlation
    → trao đổi code tại Token Endpoint
    → nhận access token / ID Token / refresh token (nếu có)
    → tạo Authentication và OAuth2AuthorizedClient
~~~

Không dùng authorization-request repository để lưu refresh token lâu dài. Ngược lại, không thể dùng một access token đã lưu để **bỏ qua kiểm tra <code>state</code>** của callback mới.

### 3.2. SecurityContext khác access token

<code>SecurityContext</code> trả lời: “User nào đã đăng nhập vào ứng dụng hiện tại?”

<code>OAuth2AuthorizedClient</code> trả lời: “ClientRegistration nào đã được cấp token cho principal nào?”

Hai đối tượng không thay thế nhau:

~~~text
SecurityContext:
    Authentication = user-123, đã xác thực tại portal

OAuth2AuthorizedClient:
    registrationId = company
    principalName  = user-123
    accessToken    = A0
    refreshToken   = R0 (nếu được OP cấp)
~~~

Một user có thể vẫn đăng nhập ở portal dù access token đã hết hạn. Ngược lại, access token còn hạn không chứng minh browser session hiện tại vẫn hợp lệ.

### 3.3. Browser không cần giữ refresh token của confidential backend Client

Trong kiến trúc Backend For Frontend (BFF) với confidential OAuth2/OIDC Client, browser thường chỉ giữ **session cookie**. Backend giữ access/refresh token ở server-side storage. Không đặt refresh token vào cookie tự tạo, localStorage hoặc HTML response chỉ vì muốn các replica đọc cùng token.

Nếu ứng dụng là SPA public Client thực hiện OAuth2 ở browser, thiết kế khác và cần mô hình bảo vệ token riêng; không áp dụng máy móc ví dụ BFF trong bài.

## 4. Sơ đồ luồng OIDC Login qua hai instance

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant LB as Load Balancer
    participant A as Instance A
    participant B as Instance B
    participant Sessions as Shared Session Store
    participant OP as OpenID Provider
    participant Tokens as Shared Authorized Client Store

    Browser->>LB: GET /oauth2/authorization/company
    LB->>A: Route tới A
    A->>Sessions: Save authorization request + state
    A-->>Browser: 302 Authorization Endpoint
    Browser->>OP: Authorization request
    OP-->>Browser: 302 callback code + state
    Browser->>LB: GET /login/oauth2/code/company
    LB->>B: Route tới B
    B->>Sessions: Load authorization request và Web/HTTP session
    Sessions-->>B: Original state/PKCE/nonce
    B->>OP: Token exchange
    OP-->>B: Access token, ID Token (+ refresh token)
    B->>Sessions: Save authenticated SecurityContext
    B->>Tokens: Save OAuth2AuthorizedClient
    B-->>Browser: Redirect sau login + session cookie
    Browser->>LB: GET /reports
    LB->>A: Route tới A
    A->>Sessions: Restore Authentication
    A->>Tokens: Load authorized client theo registration/principal
    Tokens-->>A: Token hiện hành
    A-->>Browser: Nội dung đã được phép truy cập
~~~

Sơ đồ giả định Spring Session và authorized-client storage được cấu hình để tất cả instance thấy trạng thái tương thích. Chi tiết repository phụ thuộc Servlet/Reactive stack và cách tích hợp cụ thể.

Nếu chỉ có shared session nhưng token vẫn ở một <code>InMemoryOAuth2AuthorizedClientService</code> cục bộ, request sau login có thể không lấy được token. Nếu chỉ có shared token store nhưng session/correlation cục bộ, callback từ OP vẫn có thể lỗi.

## 5. Sticky session có đủ không?

**Session affinity**, thường gọi là sticky session, khiến load balancer ưu tiên chuyển request của cùng browser tới một instance.

Ví dụ:

~~~text
Browser 1 → luôn tới A
Browser 2 → luôn tới B
~~~

Đây có thể là giải pháp tạm thời cho những hệ thống chưa chia sẻ session, nhưng có giới hạn:

| Tình huống | Sticky session giúp được không? |
|---|---|
| Browser nhiều request liên tiếp, A còn sống | Có thể duy trì local session |
| A bị crash/redeploy | Không; state local có thể mất |
| Load balancer thay đổi affinity | Có thể mất correlation |
| Scheduler/service khác cần authorized client | Không giải quyết |
| A và B cùng dùng shared refresh token | Không bảo vệ concurrency |
| Muốn tăng tính sẵn sàng khi scale/restart | Không thay thế persistent session/token store |

**Sticky session là chiến lược định tuyến, không phải cơ chế đồng bộ dữ liệu.** Khi yêu cầu high availability và rolling deployment, dùng shared session store và storage đúng cho token thường dễ bảo đảm hành vi hơn, nhưng vẫn cần thiết kế failure/recovery.

## 6. Spring Session: chia sẻ HTTP session giữa các node

Spring Session thay thế/cung cấp abstraction quản lý HTTP session để có thể lưu session bên ngoài một JVM, ví dụ Redis.

Trong ứng dụng **Servlet**, Spring Session tích hợp với <code>HttpSession</code>. Trong **Reactive WebFlux**, Spring Session có integration với <code>WebSession</code>. Cả hai có thể sử dụng Redis nhưng không dùng cùng API repository để viết code.

### 6.1. Spring Session giải quyết vấn đề gì?

~~~text
Không chia sẻ:

Instance A memory session = S123
Instance B memory session = (không tồn tại S123)

Chia sẻ qua Redis:

Instance A ──┐
             ├── Redis session namespace ── session S123
Instance B ──┘
~~~

Khi browser gửi session cookie, instance nhận request có thể truy vấn session store để khôi phục dữ liệu cần thiết.

**Lưu ý:** Redis session không tự xác minh OAuth2 state hoặc ID Token. Spring Security vẫn phải xử lý tương ứng, và cookie/session configuration phải đúng.

### 6.2. Cần có những thành phần nào?

Đối với Servlet Spring Boot, một hệ thống thường cần:

- <code>spring-boot-starter-web</code>.
- <code>spring-boot-starter-security</code>.
- <code>spring-boot-starter-oauth2-client</code>.
- <code>spring-session-data-redis</code> và Redis client/configuration tương ứng.
- Một Redis endpoint được bảo vệ bằng authentication/TLS/network policy.

Spring Boot có thể tự cấu hình Spring Session dựa trên dependencies/properties. Nếu tự thêm <code>@EnableRedisHttpSession</code> hoặc các cấu hình session thủ công, cần hiểu chúng có thể thay đổi/ghi đè auto-configuration; không bổ sung annotation chỉ để “chắc chắn” khi ứng dụng đã chạy đúng.

### 6.3. Dependencies minh họa

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Chú ý các phiên bản Spring Boot, Spring Session và Spring Security phải tương thích. Tốt nhất sử dụng dependency management của Spring Boot thay vì tự gán nhiều version thủ công.

### 6.4. application.yml cho Redis sessions

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      password: ${REDIS_PASSWORD:}

  session:
    timeout: 30m
    redis:
      namespace: portal:sessions

server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax
~~~

Đây là cấu hình **Servlet ví dụ**. Tên properties có thể thay đổi giữa major versions; áp dụng theo tài liệu Spring Boot/Spring Session của phiên bản đang triển khai.

Giải thích:

- <code>spring.data.redis.*</code> mô tả kết nối Redis.
- <code>spring.session.timeout</code> là session idle timeout theo cấu hình.
- <code>spring.session.redis.namespace</code> phân vùng session keys theo ứng dụng/môi trường.
- Cookie <code>HttpOnly</code> giúp hạn chế JavaScript đọc session cookie.
- <code>Secure</code> đòi HTTPS từ góc nhìn browser, phù hợp production.
- <code>SameSite=Lax</code> thường phù hợp top-level cross-site **GET** callback OIDC; nếu dùng <code>response_mode=form_post</code> hoặc kiến trúc SSO khác, phải kiểm tra tương tác SameSite/cookie trên trình duyệt và chính sách CSRF.

Không dùng mật khẩu Redis ví dụ trong source. Production phải dùng TLS và Redis credentials/ACL/network isolation phù hợp; nếu ứng dụng nằm sau proxy TLS, cần cấu hình secure cookie và forwarded headers từ proxy được tin cậy.

### 6.5. Session timeout khác access token expiry

Ví dụ:

~~~text
HTTP session timeout = 30 phút idle
Access token lifetime = 10 phút
Refresh token lifetime = tùy OP policy
~~~

Trong phút thứ 15, user có thể còn session nhưng access token đã hết hạn. Manager có thể refresh nếu có refresh token hợp lệ. Ngược lại, khi user mất session, điều đó không đồng nghĩa access token trong storage đã tự bị thu hồi tại OP.

Không cho rằng cứ tăng session timeout là giải quyết token refresh failure.

## 7. Lưu authorized client: service và repository khác nhau

Trong **Spring Security Servlet**, hai abstraction thường gặp:

- <code>OAuth2AuthorizedClientService</code>: load/save/remove theo ClientRegistration ID và principal name.
- <code>OAuth2AuthorizedClientRepository</code>: load/save/remove trong ngữ cảnh <code>Authentication</code>, <code>HttpServletRequest</code> và <code>HttpServletResponse</code>.

Một repository web có thể dựa vào service hoặc HTTP session tùy implementation:

| Implementation | Nơi lưu/tra cứu điển hình | Cần lưu ý khi scale-out |
|---|---|---|
| <code>HttpSessionOAuth2AuthorizedClientRepository</code> | HTTP session | Cần session store dùng chung nếu request roaming |
| <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code> | Delegate đến <code>OAuth2AuthorizedClientService</code> cho principal đã xác thực, có fallback cho trường hợp chưa xác thực theo cấu hình | Shared HTTP session **không bảo đảm** service bên dưới cũng shared |
| <code>InMemoryOAuth2AuthorizedClientService</code> | Memory một instance | Restart/scale-out có thể mất hoặc phân mảnh token |
| <code>JdbcOAuth2AuthorizedClientService</code> | Bảng database theo schema Spring Security tương ứng | Có thể chia sẻ token, nhưng không tự lock refresh cross-node |
| Custom service/repository | Redis/database/token vault theo thiết kế | Cần lưu toàn bộ trạng thái token và thực hiện concurrency/security rõ |

### 7.1. Mặc định không có nghĩa luôn giống nhau

Spring Boot/Spring Security có thể cung cấp bean mặc định tùy dependencies, cấu hình và phiên bản. Không nên suy luận:

~~~text
Đã bật Spring Session Redis
⇒ tất cả OAuth2AuthorizedClient đều tự động ở Redis
~~~

Nếu ứng dụng dùng <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code> delegate đến một <code>InMemoryOAuth2AuthorizedClientService</code>, token của user authenticated vẫn có thể nằm trong memory của node hiện tại.

Ngược lại, nếu ứng dụng chủ động dùng <code>HttpSessionOAuth2AuthorizedClientRepository</code> và Spring Session thật sự chia sẻ HTTP session, token lưu trong session đó có thể theo session tới node khác. Đổi repository hoặc security configuration có thể thay đổi nhận định này.

**Cần kiểm tra bean wiring thực tế**, không chỉ đọc tên dependencies.

### 7.2. Vì sao cần dùng cặp registration/principal?

Một authorized client thường được xác định bởi:

~~~text
(clientRegistrationId, principalName)
~~~

Ví dụ:

~~~text
(company, user-123)
(company, user-456)
(partner-api, user-123)
~~~

Đây là **ba authorized clients khác nhau**. Không lưu token trong một biến singleton theo registration ID duy nhất vì user A có thể ghi đè token user B.

Với multi-tenant hoặc multi-issuer, principal name phải có namespace tin cậy. Một <code>sub=123</code> từ issuer A và <code>sub=123</code> từ issuer B không mặc nhiên là cùng tài khoản.

### 7.3. Không đồng nhất OIDC subject và email

OIDC sử dụng cặp <code>(iss, sub)</code> làm định danh ổn định trong bối cảnh issuer. Email có thể thay đổi, thiếu hoặc chưa được xác minh.

Nếu ứng dụng tùy biến principal name thành email mà không có chính sách liên kết tài khoản an toàn, hai users/issuers có thể bị ghép sai authorized client. Cần xác thực và đặt khóa nội bộ đúng khi thiết kế storage dùng chung.

## 8. Ví dụ Spring Boot Servlet: Spring Session Redis + JDBC authorized clients

Một triển khai đơn giản để phân tách rõ trách nhiệm:

~~~text
Redis:
    HttpSession, SecurityContext, authorization request state/PKCE

PostgreSQL:
    OAuth2AuthorizedClient của authenticated principals
    access token + refresh token (theo cấu hình service)

Authorization Server:
    quyền cấp token, session OP, token revocation/rotation
~~~

**Lưu ý:** Không bắt buộc phải dùng Redis + PostgreSQL trong mọi hệ thống. Đây là một kiến trúc tham khảo. Có thể dùng một token vault hoặc store khác nếu đáp ứng persistence, concurrency và security.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

### 8.2. Cấu hình Redis, JDBC và OIDC registration

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:localhost}
      port: ${REDIS_PORT:6379}
      password: ${REDIS_PASSWORD:}

  session:
    timeout: 30m
    redis:
      namespace: portal:sessions

  datasource:
    url: ${JDBC_URL}
    username: ${JDBC_USERNAME}
    password: ${JDBC_PASSWORD}

  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_CLIENT_SECRET}
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
~~~

Tất cả endpoint, Client ID và scope chỉ là ví dụ. JDBC/Redis credentials và client secret phải được lấy từ secret management phù hợp. Database connection và Redis connection production phải được bảo vệ bằng TLS/ACL/network policy.

### 8.3. Cấu hình SecurityFilterChain

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
~~~

<code>oauth2Login()</code> xử lý Authorization Code/OIDC Login và lưu Authentication phù hợp. <code>oauth2Client()</code> hỗ trợ OAuth2 Client trong Servlet khi ứng dụng dùng authorized client gọi API.

Đây là cấu hình browser có session; **không tắt CSRF cho toàn ứng dụng** chỉ vì một số downstream API sử dụng Bearer token.

### 8.4. Cấu hình OAuth2AuthorizedClientService dùng JDBC

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
        JdbcOperations jdbcOperations,
        ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcOperations, registrations);
    }

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
        OAuth2AuthorizedClientService authorizedClientService) {

        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
            authorizedClientService);
    }
}
~~~

Ý nghĩa:

1. Service thao tác authorized client theo registration/principal trong JDBC.
2. Repository dành cho web có thể load/save/remove thông qua service với principal đã xác thực.
3. Spring Security OAuth2 Login/Client cần thực sự được **wiring tới repository bean này**; kiểm tra version và bean auto-configuration khi có nhiều repository/manager.
4. Spring Session lưu phiên HTTP trong Redis thông qua cấu hình riêng, không phải qua <code>JdbcOAuth2AuthorizedClientService</code>.

**Bắt buộc chuẩn bị schema JDBC** phù hợp với <code>JdbcOAuth2AuthorizedClientService</code> của phiên bản Spring Security đã chọn. Không chỉ tạo bean rồi giả định thư viện tự tạo bảng ở mọi môi trường. Trong production, áp dụng migrations có kiểm soát, backup, quyền database tối thiểu và kiểm tra bảo vệ dữ liệu token.

### 8.5. Một controller chỉ trả metadata an toàn

~~~java
package example.web;

import java.util.Map;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthorizedClientInfoController {

    @GetMapping("/my/oauth2-client")
    public Map<String, Object> info(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient client) {

        return Map.of(
            "registrationId",
            client.getClientRegistration().getRegistrationId(),
            "principalName",
            client.getPrincipalName(),
            "hasRefreshToken",
            client.getRefreshToken() != null,
            "hasAccessToken",
            client.getAccessToken() != null
        );
    }
}
~~~

Ví dụ này để quan sát authorized client được resolve trên node nào, **không trả token value**. Trong production, principalName có thể là thông tin nhạy cảm; nên cân nhắc chỉ trả một định danh do hệ thống được phép công bố hoặc giữ endpoint debug này nội bộ.

Với API không cần lộ thông tin lưu token, không tạo endpoint này. Khi không có authorized client, cần xử lý theo flow/exception policy, không fallback sang token của một user khác.

### 8.6. Điều gì xảy ra khi A restart?

Nếu Redis và PostgreSQL vẫn hoạt động:

- Browser có thể tiếp tục dùng session cookie trỏ tới session lưu ở Redis.
- Instance B có thể khôi phục SecurityContext nếu serialization và SecurityFilterChain tương thích.
- Authorized client có thể được load từ JDBC theo principal/registration.
- Token còn hạn có thể được dùng; token cần refresh đi qua manager/provider phù hợp.

Tuy vậy **khả năng đọc được state không chứng minh refresh concurrency đã an toàn**. Nếu A và B đồng thời refresh token, database chia sẻ chưa đủ chống race.

## 9. So sánh ba mô hình lưu authorized client

### 9.1. Token trong Web/HTTP session

~~~text
Browser session cookie
    ↓
Shared Spring Session
    └── Authorized client state (nếu repository lưu trong session)
~~~

Ưu điểm:

- Token gắn với vòng đời phiên browser.
- Có thể đơn giản khi ứng dụng chỉ có browser login và không cần service token sau logout.
- Chia sẻ session store có thể giúp token theo browser qua nhiều node.

Giới hạn:

- Session hết hạn sẽ làm mất authorized client cùng session.
- Nếu một user có nhiều browser sessions, có thể có token state tách theo session, tùy repository.
- Session serialization chứa token nhạy cảm; Redis/backup/observability phải được bảo vệ tương ứng.
- Không mặc định cho service/background job tra cứu token ngoài session.
- Refresh race vẫn có thể xảy ra nếu hai request cùng session trên hai node.

### 9.2. Token trong OAuth2AuthorizedClientService dùng chung

~~~text
Browser A / Browser B
       ↓
Authenticated principal + registrationId
       ↓
Shared OAuth2AuthorizedClientService
       ↓
Token record
~~~

Ưu điểm:

- Có thể tái sử dụng token giữa requests/sessions theo principal.
- Token persistence tách biệt session timeout.
- Có thể quản lý cleanup, encryption, rotation và audit ở lớp riêng.

Giới hạn:

- Token có thể còn trong DB sau khi browser logout nếu không có policy cleanup.
- Nếu hai sessions của cùng principal lưu/refresh một record, cần xử lý concurrent updates.
- Có nguy cơ lẫn issuer/tenant nếu principal key thiết kế sai.
- Quyền truy cập DB chứa token trở thành tài sản bảo mật có giá trị cao.

### 9.3. Token trong memory của từng instance

~~~text
A: (company,user-123) -> A0/R0
B: (company,user-123) -> không có
~~~

Ưu điểm: rất đơn giản cho local/demo/single-instance.

Giới hạn: không bền qua restart, không đồng bộ qua replicas, dễ tạo flow authorize lại. Với confidential service dùng client credentials, việc xin token mới sau restart có thể chấp nhận được; nhưng không nên áp dụng lập luận đó cho **refresh token đại diện End-User** khi provider rotation và consent policy phức tạp.

## 10. Chọn OAuth2AuthorizedClientManager đúng ngữ cảnh

Manager phối hợp ClientRegistration, authorized-client repository/service và grant providers. Nó không phải database và không phải load balancer.

### 10.1. Servlet browser request

<code>DefaultOAuth2AuthorizedClientManager</code> thường dùng:

~~~java
new DefaultOAuth2AuthorizedClientManager(
    clientRegistrationRepository,
    authorizedClientRepository);
~~~

Repository có ngữ cảnh <code>HttpServletRequest</code> và <code>HttpServletResponse</code>. Nó phù hợp HTTP request Servlet đã có Authentication và session.

Ví dụ manager có refresh provider:

~~~java
@Bean
OAuth2AuthorizedClientManager webAuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientRepository repository) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

    var manager =
        new DefaultOAuth2AuthorizedClientManager(registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Đây là **ví dụ bean tùy chọn**; nếu dự án đã có manager được auto-configure, không tự khai báo thêm không cần thiết. Khi có nhiều manager, dùng bean name/<code>@Qualifier</code> rõ ràng.

### 10.2. Background job hoặc scheduled worker

<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> dùng service thay vì Servlet request:

~~~java
@Bean("jobAuthorizedClientManager")
OAuth2AuthorizedClientManager jobAuthorizedClientManager(
    ClientRegistrationRepository registrations,
    OAuth2AuthorizedClientService service) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

    var manager =
        new AuthorizedClientServiceOAuth2AuthorizedClientManager(
            registrations, service);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

Các đoạn cấu hình ở mục 10 là code mẫu rút gọn. Trong một class thực tế, cần import các class tương ứng từ <code>org.springframework.security.oauth2.client.*</code>, <code>org.springframework.security.oauth2.client.registration.*</code>, <code>org.springframework.security.oauth2.client.web.*</code> và <code>org.springframework.context.annotation.*</code>.

Job client credentials **không phải** OIDC End-User Login. Dùng principal tổng hợp ổn định để chia storage theo workload:

~~~java
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("reports-worker")
    .principal("reports-worker-runtime")
    .build();
~~~

Nếu job cần **refresh token của user đã ủy quyền**, bài toán authorization/lifecycle phức tạp hơn. Không tự lấy refresh token từ DB chỉ bằng một user ID do caller khai báo; phải có policy cho việc thực hiện delegated operation và token storage isolation.

### 10.3. Manager không tự phối hợp refresh trong cluster

<code>refreshToken()</code> giúp manager **biết cách refresh**. Nó không bảo đảm chỉ một replica gửi request tới Token Endpoint tại cùng thời điểm.

Nếu token store và manager dùng chung nhiều instance, cần thêm điều phối hoặc storage concurrency control theo đặc tính OP.

## 11. Refresh token rotation và cuộc đua giữa hai node

Khi access token gần hết hạn:

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Instance A
    participant B as Instance B
    participant DB as Shared Token Store
    participant OP as Token Endpoint

    A->>DB: load(company,user-123)
    DB-->>A: A0, R0, version=7
    B->>DB: load(company,user-123)
    DB-->>B: A0, R0, version=7
    A->>OP: refresh_token=R0
    OP-->>A: A1 + R1
    B->>OP: refresh_token=R0
    OP-->>B: invalid_grant / reuse detection
    A->>DB: save A1, R1, version=8
    B->>DB: failure handler xóa record?
    Note over DB: B có thể xóa nhầm version=8 nếu delete không điều kiện
~~~

Nếu OP bật **refresh token rotation**, việc sử dụng lại R0 có thể khiến token family bị vô hiệu hóa theo policy. Không phải mọi OP xử lý reuse giống nhau: có provider grace period, có provider nghiêm ngặt, có provider không rotation.

Hệ thống không nên dựa vào “ở staging chưa thấy <code>invalid_grant</code>” để kết luận dùng chung refresh token mà không khóa là an toàn.

### 11.1. Chia sẻ dữ liệu không tương đương serialize thao tác

JDBC/Redis giúp A và B **đọc cùng một token**, nhưng chưa chắc ngăn chúng **cùng đọc R0 rồi cùng gửi refresh**.

~~~text
Shared store = cùng nhìn thấy dữ liệu
Distributed coordination = hạn chế cùng sửa/cùng tiêu thụ một state
~~~

Hai chức năng khác nhau; cần thiết kế cả hai khi dùng refresh-token rotation.

### 11.2. Vì sao không chỉ dùng synchronized?

~~~java
public synchronized OAuth2AuthorizedClient refresh(...) { ... }
~~~

<code>synchronized</code> chỉ bảo vệ threads trong **một JVM**. Nó không phối hợp A và B trên hai máy/container.

Tương tự, dùng một <code>ConcurrentHashMap</code> local để lưu lock cũng không bảo vệ request của các replicas khác.

### 11.3. Khóa theo authorized-client key

Lock nên dựa trên:

~~~text
registrationId + trustedPrincipalKey
~~~

Ví dụ:

~~~text
oauth2:refresh:company:hash-principal-123
~~~

Không dùng một lock global cho mọi user; user A không nên bị chặn refresh vì user B đang chờ OP.

Nếu môi trường multi-tenant, khóa phải có namespace issuer/tenant phù hợp. Không dùng raw email hoặc user-supplied string làm lock key khi có rủi ro lộ PII hoặc gây collision.

## 12. Thuật toán điều phối refresh an toàn hơn

Một quy trình thực tế thường có **double-check sau lock**.

~~~text
authorizeOrRefresh(registrationId, trustedPrincipal):
    key = stableAuthorizedClientKey(registrationId, trustedPrincipal)

    current = tokenStore.load(key)
    if current có access token còn dùng được:
        return current

    acquire distributed lock(key) với timeout/lease
    try:
        latest = tokenStore.load(key)  // BẮT BUỘC đọc lại

        if latest đã được node khác cập nhật và token còn hợp lệ:
            return latest

        if latest không có refresh token thích hợp:
            require reauthorization / grant khác theo policy

        response = Token Endpoint.refresh(latest.refreshToken)

        commit nguyên cặp access/refresh token mới
        với version/fencing check nếu cần

        return authorized client đã commit
    finally:
        release lock chỉ khi còn sở hữu lock
~~~

Đây là **pseudocode kiến trúc**, không phải API tự có của <code>OAuth2AuthorizedClientManager</code>.

### 12.1. Vì sao phải load lại sau lock?

Giả sử:

~~~text
T0: A đọc R0, B đọc R0
T1: A lấy lock; B chờ
T2: A refresh R0, lưu R1, release lock
T3: B lấy lock
~~~

Nếu B tiếp tục dùng **snapshot R0 từ T0**, lock đã không giải quyết gì. B phải đọc latest state tại T3; nếu A1 còn dùng được, **không gọi Token Endpoint** lần nữa.

### 12.2. Nếu không lấy được lock?

Không nên “bỏ qua lock để cho nhanh” rồi tự refresh R0. Có thể:

- Chờ ngắn với timeout giới hạn và đọc lại store.
- Nếu access token cũ còn đủ hạn theo safety margin, dùng nó theo policy.
- Trả lỗi tạm thời cho internal API hoặc trì hoãn background job.
- Theo dõi lock contention để tìm root cause.

Không tạo vòng lặp vô hạn hoặc block request threads quá lâu.

### 12.3. Ownership và lease

Distributed lock nên có:

1. **Owner token** xác định một lượt giữ lock.
2. **Lease/TTL** tránh lock tồn tại vĩnh viễn nếu node crash.
3. **Release atomic có kiểm tra owner**, không xóa lock của owner mới.
4. Thời gian chờ và timeout rõ ràng.
5. Nếu yêu cầu rất chặt, **fencing** tại storage để từ chối stale writer khi lease đã đổi chủ.

Ví dụ nguy hiểm: A giữ lock 10 giây, bị pause 15 giây; B lấy lock mới. Khi A tỉnh lại rồi xóa lock không điều kiện, nó có thể xóa lock của B.

### 12.4. Fencing giải quyết ghi muộn, không “undo” request đã tới OP

Nếu A có fencing sequence 41, sau đó B có sequence 42, storage có thể từ chối write của A với sequence 41.

Điều này bảo vệ **kho token** khỏi stale write. Nhưng nếu A đã gửi R0 tới OP rồi, fencing ở database **không thể đảo ngược việc R0 đã bị tiêu thụ**.

Do đó cần coordination trước token request, cộng conditional save/delete sau request.

## 13. Optimistic concurrency: CAS/version trên token record

Để ngăn lost update, một custom token store có thể giữ cột <code>version</code>:

~~~text
registration_id | principal_name | access | refresh | version
company         | user-123       | A0     | R0      | 7
~~~

Sau khi refresh nhận A1/R1:

~~~sql
UPDATE oauth2_authorized_client_state
SET access_token_ciphertext = :new_access_token,
    refresh_token_ciphertext = :new_refresh_token,
    access_expires_at = :new_access_expires_at,
    version = version + 1
WHERE registration_id = :registration_id
  AND principal_name = :principal_name
  AND version = :expected_version;
~~~

Nếu affected rows bằng **1**, write từ version mong đợi thành công. Nếu bằng **0**, có thể record đã đổi version hoặc bị xóa bởi node khác; writer không được bỏ điều kiện version để cưỡng ép ghi.

### 13.1. Phải lưu access/refresh token nhất quán

Nếu OP đã phát <code>A1/R1</code>, không cập nhật access token và refresh token thành hai giao dịch riêng:

~~~text
UPDATE access_token = A1
COMMIT
-- node khác có thể đọc A1 + R0 ở đây
UPDATE refresh_token = R1
COMMIT
~~~

Hãy lưu toàn bộ authorized-client state liên quan trong **một cập nhật atomic**. Nếu response không trả refresh token mới, xử lý bảo tồn refresh token cũ theo hợp đồng response/client; nếu response trả R1, phải thay R0 đúng lúc.

### 13.2. CAS chỉ bảo vệ database

CAS **không** ngăn A và B đồng thời gửi R0 nếu cả hai đã đọc state trước khi gọi OP. Vì vậy:

~~~text
Lock/single-flight trước Token Endpoint → tránh duplicate refresh
CAS/version tại storage          → tránh stale update/delete
~~~

### 13.3. JDBC service mặc định không đồng nghĩa versioned storage

Không giả định <code>JdbcOAuth2AuthorizedClientService</code> mặc định cung cấp <code>version</code>, conditional update/delete hoặc distributed lock theo mô hình trên.

Nếu cần các bảo đảm đó, có thể phải:

- Mở rộng storage schema/DAO tương thích phiên bản.
- Viết wrapper/custom <code>OAuth2AuthorizedClientService</code>.
- Cấu hình success/failure handlers chỉ ghi/xóa có điều kiện.
- Dùng single-writer token service hoặc coordinator thống nhất cho mọi code path.

**Không sửa schema mặc định rồi kỳ vọng framework tự dùng cột mới** khi chưa có code tương ứng.

## 14. Nguy cơ failure handler xóa nhầm bản token mới

Một số manager/provider có cơ chế loại bỏ authorized client sau lỗi <code>invalid_grant</code>. Trong nhiều replica, cần xem thứ tự:

~~~text
A: refresh R0 thành công và lưu A1/R1, version=8
B: refresh R0 thất bại invalid_grant
B: removeAuthorizedClient(company, user-123)
~~~

Nếu B xóa không điều kiện theo registration/principal, version 8 vừa lưu của A có thể bị mất.

Một policy an toàn hơn:

~~~text
if refresh thất bại với invalid_grant:
    latest = tokenStore.load(key)

    if latest.version != version đã dùng bởi lượt refresh thất bại:
        không xóa bản mới hơn
        phân loại lại tình huống
    else:
        compareAndRemove(key, expectedVersion)
        đánh dấu cần reauthorization nếu phù hợp
~~~

Với SQL khái niệm:

~~~sql
DELETE FROM oauth2_authorized_client_state
WHERE registration_id = :registration_id
  AND principal_name = :principal_name
  AND version = :expected_version;
~~~

Hành vi <code>invalid_grant</code> còn phụ thuộc OP. Nếu OP đã phát hiện R0 reuse và thu hồi toàn bộ token family, bản mới A1/R1 có thể cũng bị ảnh hưởng. **Không kết luận R1 chắc chắn vẫn hợp lệ chỉ vì lưu ở version 8**.

### 14.1. Không xóa token ở mọi lỗi mạng

Phân biệt:

| Lỗi | Điều có thể suy luận | Hướng xử lý |
|---|---|---|
| <code>invalid_grant</code> | Grant/refresh token bị từ chối | Kiểm tra rotation, revocation, reauthorization |
| <code>invalid_client</code> | Client credentials/authentication không hợp lệ | Kiểm tra registration/secret/key rotation |
| HTTP 429 Token Endpoint | Rate limit | Backoff/jitter có giới hạn, giảm token request |
| HTTP 502/503 | AS/gateway tạm thời lỗi | Retry có kiểm soát, không xóa bừa |
| Timeout sau khi gửi refresh | Không biết OP đã tiêu thụ R0 chưa | Không retry R0 vô hạn |
| CAS conflict | Có concurrent state modification | Đọc lại và đánh giá version mới |
| Lock timeout | Node khác có thể đang refresh | Chờ/reload hoặc trả lỗi tạm thời |

Timeout sau khi OP đã phát R1 nhưng response bị mất là trường hợp **kết quả không xác định**. Không có distributed transaction tiêu chuẩn giữa Token Endpoint và database local để bảo đảm “exactly once refresh” trong mọi tình huống.

## 15. Logout, session expiry và token revocation

Một hệ thống distributed phải quy định rõ vòng đời của cả **session** và **authorized client**.

### 15.1. Các thao tác không tương đương

~~~text
Logout browser session
    != Xóa OAuth2AuthorizedClient trong local store
    != Thu hồi access/refresh token tại Authorization Server
    != Đăng xuất SSO session tại OpenID Provider
~~~

Tùy sản phẩm, logout có thể cần một hoặc nhiều bước.

| Thao tác | Ảnh hưởng |
|---|---|
| Invalidate HTTP session | Browser không tiếp tục dùng session cũ tại portal |
| Remove authorized client | Local service/repository không còn token record theo key |
| Token revocation (RFC 7009) | Yêu cầu AS thu hồi token nếu endpoint/profile được hỗ trợ |
| OIDC RP-Initiated Logout | Điều hướng/thông báo OP logout theo cấu hình và policy |
| Domain account disable | Chặn quyền nghiệp vụ, cần được các API/Client áp dụng |

Không coi việc xóa Redis session là đảm bảo **refresh token đã bị thu hồi ở OP**.

### 15.2. Xóa record theo principal cần cân nhắc nhiều sessions

Nếu <code>OAuth2AuthorizedClientService</code> lưu một record theo <code>(registrationId, principalName)</code>, nhiều sessions của cùng user có thể chia sẻ record.

Khi user logout khỏi một browser:

- **Xóa record ngay** có thể khiến phiên khác của cùng user mất authorized client.
- **Không xóa** có thể để lại token tại backend sau khi mọi session đã kết thúc.

Không có lựa chọn đúng cho mọi sản phẩm. Cần quyết định token scope là **per session**, **per principal**, **per device** hay **per authorization grant**, rồi chọn storage key/cleanup policy tương ứng.

Nếu cần tách per-device/per-session, đừng đổi principal name tùy tiện mà không đánh giá các API/repository kỳ vọng và cơ chế liên kết danh tính.

### 15.3. Concurrent logout và refresh

Nếu một node logout và revoke token trong khi node khác refresh:

~~~text
Node A: logout → xóa record
Node B: refresh R0 → lưu lại A1/R1
~~~

Nếu không có phối hợp, record có thể **xuất hiện lại sau logout**. Một kiến trúc cần xử lý tình huống này có thể dùng:

- Tombstone/revocation generation hoặc trạng thái disabled của authorization.
- CAS/fencing kết hợp policy “không save sau logout generation mới”.
- Single writer cho authorized-client state.
- Cleanup/revocation idempotent và audit.

Chỉ dựa vào một <code>DELETE</code> đơn lẻ mà không kiểm soát writer khác có thể chưa đủ khi quyền thu hồi tức thì là yêu cầu bảo mật.

## 16. Mô hình Reactive WebFlux

Trong **WebFlux**, cần dùng các abstraction reactive:

| Servlet | Reactive WebFlux |
|---|---|
| <code>HttpSession</code> | <code>WebSession</code> |
| <code>HttpSecurity</code> | <code>ServerHttpSecurity</code> |
| <code>SecurityFilterChain</code> | <code>SecurityWebFilterChain</code> |
| <code>HttpSessionOAuth2AuthorizationRequestRepository</code> | <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code> |
| <code>OAuth2AuthorizedClientRepository</code> | <code>ServerOAuth2AuthorizedClientRepository</code> |
| <code>OAuth2AuthorizedClientService</code> | <code>ReactiveOAuth2AuthorizedClientService</code> |
| <code>DefaultOAuth2AuthorizedClientManager</code> | <code>DefaultReactiveOAuth2AuthorizedClientManager</code> |
| <code>RestClient</code> hoặc Servlet HTTP integration | <code>WebClient</code> với reactive integration |

### 16.1. Spring Session cho WebSession

Spring Session có Redis integration cho reactive <code>WebSession</code>. Với dự án WebFlux, cần các dependencies/auto-configuration tương ứng, ví dụ:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
~~~

Các dependencies thực tế phụ thuộc Spring Boot version và Redis client hiện có; không bắt buộc thêm cả synchronous và reactive Redis starters nếu dự án chỉ cần một stack.

Với Spring Session Reactive, <code>WebSession</code> có thể được lưu tập trung để callback OIDC qua các node có thể tìm lại state/correlation. Nhưng authorized-client repository/service vẫn phải được cấu hình và kiểm tra riêng.

### 16.2. Reactive authorized-client storage

Các abstraction:

~~~text
ServerOAuth2AuthorizedClientRepository
    ↕
ReactiveOAuth2AuthorizedClientService
    ↕
Reactive-compatible persistent store
~~~

Một số repository có thể lưu authorized client trong WebSession; một số delegate cho service theo principal. **Không dùng JDBC blocking trực tiếp trên Netty event-loop** rồi bọc <code>Mono.just(...)</code> để gọi đó là reactive.

Nếu phải tích hợp driver blocking, cần cô lập trên scheduler phù hợp, quản lý pool và đo latency; hoặc dùng implementation non-blocking nếu kiến trúc cho phép.

### 16.3. Reactivity không giải quyết distributed refresh race

Hai <code>Mono</code> chạy trên A và B vẫn có thể đọc cùng R0 và cùng gửi token request. Không block event-loop, không subscribe thủ công, nhưng **vẫn cần distributed coordination** nếu provider rotation nghiêm ngặt.

Không nhầm reactive concurrency control trong một pipeline với transaction/lock trên toàn cluster.

## 17. Session cookie và callback qua proxy/load balancer

Khi chuyển sang distributed sessions, nhiều lỗi thực ra đến từ **cookie/proxy**, không phải Redis.

### 17.1. Callback không tìm được state

Biểu hiện:

~~~text
GET /oauth2/authorization/company → redirect OP thành công
GET /login/oauth2/code/company → state missing/mismatch
~~~

Nguyên nhân có thể:

- Browser không gửi cookie trở lại callback.
- Cookie Domain/Path hoặc SameSite/Secure không phù hợp.
- Proxy làm sai scheme/host khi xây redirect URI.
- Session chưa được ghi/replicate đúng cách.
- Callback tới node khác nhưng session store không shared.
- Browser có nhiều authorization flows cạnh tranh trong cùng session.
- Session timeout trong lúc user ở OP.

Không sửa bằng cách bỏ <code>state</code>, <code>nonce</code> hoặc PKCE validation. Những cơ chế này bảo vệ OAuth2/OIDC Login khỏi callback injection/replay và code interception.

### 17.2. SameSite và response_mode

Với callback top-level GET, cookie <code>SameSite=Lax</code> thường tương thích. Nếu OP trả callback bằng cross-site form POST (<code>response_mode=form_post</code>), hành vi gửi cookie có thể khác. Khi cần <code>SameSite=None</code>, browser hiện đại thường yêu cầu <code>Secure</code>; thiết kế CSRF/session policy cần được xem xét đầy đủ.

Không đổi cookie SameSite thành <code>None</code> toàn hệ thống mà không đánh giá cross-site cookie risks và chính sách bảo vệ route thay đổi trạng thái.

### 17.3. Trusted forwarded headers

Khi ứng dụng thật chạy HTTPS ở public load balancer nhưng tới Spring Boot bằng HTTP nội bộ:

~~~text
Browser: https://portal.example.org
Proxy → app: http://app:8080
~~~

Nếu cấu hình forwarded headers không đúng, Spring có thể xây:

~~~text
redirect_uri=http://app:8080/login/oauth2/code/company
~~~

thay vì public callback URI hợp lệ.

Chỉ chấp nhận <code>Forwarded</code>/<code>X-Forwarded-*</code> từ **proxy tin cậy**, không từ caller tùy ý. Có thể cần cấu hình <code>server.forward-headers-strategy</code> và quy tắc ở proxy theo môi trường/version.

## 18. Serialization và triển khai rolling upgrade

Khi session nằm ở Redis, dữ liệu session có thể được serialize. Với Spring Security, SecurityContext/Authentication/OIDC principal có thể chứa nhiều class/phụ thuộc không đơn giản.

Điều cần đánh giá:

- Serializer nào đang được sử dụng (JDK serializer, JSON serializer hay cấu hình khác).
- Có module/type metadata cần thiết cho Spring Security objects không.
- Có bật polymorphic deserialization tùy tiện hay không; chỉ deserialize từ store được kiểm soát.
- Các phiên bản code A/B trong rolling deployment có đọc được session object của nhau không.
- Khi thay đổi class name/serialization schema, session cũ có còn tương thích không.
- Tránh lưu object tự định nghĩa khó serialize hoặc chứa các thành phần không nên chia sẻ vào session.

Một kịch bản lỗi:

~~~text
Node A (version v1) lưu SecurityContext vào Redis
Node B (version v2) đọc session
    → deserialization error do class/serializer không tương thích
~~~

Đây là vấn đề **session serialization compatibility**, không phải OIDC Token Endpoint từ chối code.

### 18.1. Không coi Redis là vùng an toàn tuyệt đối

Redis có thể chứa session IDs, SecurityContext và thậm chí token nếu repository lưu theo session. Bảo vệ:

- Redis ACL/user/password hoặc cơ chế cloud IAM phù hợp.
- TLS từ ứng dụng đến Redis.
- Network segmentation, không expose Redis ra Internet.
- Backup/snapshot và encryption-at-rest nếu cần.
- Namespace riêng theo môi trường/ứng dụng.
- Giới hạn người/quy trình có quyền xem keys và value.
- Kiểm soát eviction/TTL/replication và failover.

Không ghi raw session ID vào log chung; session ID là credential của browser trong mô hình cookie-based session.

### 18.2. Eviction và TTL

Khi Redis đạt memory pressure hoặc có eviction policy, session có thể bị xóa sớm hơn expected timeout. Browser sau đó mất login state dù cookie còn tồn tại.

Theo dõi eviction, key expiration và Redis availability. Không dùng Redis cache dành cho dữ liệu có thể bỏ bất cứ lúc nào làm session store quan trọng mà không đánh giá persistence/failure policy.

## 19. Một số quyết định kiến trúc cho production

### 19.1. Session và token có cần cùng datastore?

Không bắt buộc. Ví dụ:

~~~text
Session: Redis
Authorized client: PostgreSQL
Secrets/keys: KMS hoặc secret manager
Authorization Server: OP chuyên trách
~~~

Ưu điểm: điều chỉnh TTL, storage encryption, backup và concurrency riêng theo tính chất từng loại dữ liệu.

Nhược điểm: thêm thành phần và yêu cầu xử lý consistency giữa session và authorized-client state.

Một thiết kế dùng chung Redis cho cả session và token cũng có thể đúng nếu implementation và security phù hợp, nhưng **không tự có transaction chung với Authorization Server**.

### 19.2. Chọn per-session hay per-principal?

| Mô hình | Hợp khi | Cần xem |
|---|---|---|
| Per-session | Token chỉ dùng trong phiên browser và không cần tồn tại lâu sau logout | Nhiều browser sessions, token duplication, session expiry |
| Per-principal | User có thể dùng cùng authorized client trong nhiều sessions/instances | Logout một session, token sharing, token isolation |
| Per-device | Cần thu hồi riêng từng thiết bị hoặc session | Thêm key dimension, quản lý consent và lifecycle |
| Per-service | Client credentials của backend workload | Principal tổng hợp ổn định, scopes/audience và secret rotation |

Mặc định của một <code>OAuth2AuthorizedClientService</code> không nhất thiết phù hợp khi sản phẩm cần per-device revocation. Nếu thêm key dimension, phải thiết kế custom service/repository phù hợp, không thay đổi ngẫu nhiên principalName để né constraint.

### 19.3. Những vấn đề cần chốt trước rollout

- **Ownership:** Ai được phép đọc/ghi authorized clients?
- **Key:** Identity key có phân biệt issuer, tenant và device khi cần không?
- **Persistence:** Token có tồn tại sau restart/session expiry không?
- **Concurrency:** Có single-flight refresh và conditional update/delete cho rotation không?
- **Revocation:** Khi logout/disconnect account, token còn hiệu lực ở OP bao lâu?
- **Retention:** Khi nào xóa record mồ côi?
- **Availability:** Nếu Redis/DB outage, hệ thống trả lỗi gì?
- **Security:** Token/session values có được bảo vệ at rest, in transit và trong backup/logs không?
- **Compatibility:** Rolling deploy có đọc được session/token schema cũ không?

## 20. Nhiều instance không đồng nghĩa nhiều scheduler chạy đúng một lần

Nếu ứng dụng có <code>@Scheduled</code>:

~~~text
Instance A: job 02:00
Instance B: job 02:00
Instance C: job 02:00
~~~

Spring Session, JDBC authorized-client store và <code>OAuth2AuthorizedClientManager</code> **không tự ngăn ba job cùng chạy**.

Phải tách:

1. **Distributed job coordination**: chỉ một worker chạy một công việc nghiệp vụ khi yêu cầu.
2. **Token refresh coordination**: không để hai workers cùng tiêu thụ một refresh token.
3. **Idempotent business logic**: nếu request đã gửi nhưng response bị timeout, retry không gây thao tác trùng.

Một job dùng client credentials có thể xin token mới khi hết hạn. Nhưng một job được ủy quyền bởi user dùng refresh token cần bảo đảm principal/consent isolation, revocation và refresh token rotation theo policy.

## 21. Bảo mật khi nhiều node cùng truy cập authorized client

### 21.1. Authorized-client service là một kho credential

Access token và đặc biệt refresh token là credential nhạy cảm. Một node bị chiếm quyền và có khả năng đọc toàn bộ token store có thể ảnh hưởng nhiều người dùng hơn so với chỉ có access token của một session đơn lẻ.

Biện pháp:

- Quyền DB/Redis tối thiểu cho từng service.
- Bảo vệ kết nối bằng TLS và phân đoạn mạng.
- Encryption-at-rest, key rotation và backup protection.
- Không ghi raw access/refresh token vào logs, metrics hoặc exception messages.
- Giới hạn access đến dữ liệu theo tenant hoặc service boundary.
- Cân nhắc envelope encryption/column encryption nếu threat model yêu cầu.
- Chính sách cấp/xóa token theo quyền đã được kiểm tra.

### 21.2. Không cho browser chỉ định principal key

Sai:

~~~java
String principal = request.getParameter("userId");
OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest.withClientRegistrationId("company")
        .principal(principal)
        .build();
~~~

Browser có thể thử userId của người khác. Nếu token store dùng key đó, kết quả là nguy cơ lấy nhầm/đánh cắp authorized client.

Với browser login, principal phải lấy từ <code>Authentication</code> đã được Spring Security xác thực. Với service job, dùng principal tổng hợp **do backend kiểm soát**.

### 21.3. Phân biệt security domain của từng ClientRegistration

Hai registration khác nhau có thể trỏ tới hai issuer hoặc cùng issuer với client IDs khác nhau. Không dùng token từ registration A cho API B nếu audience/scope không phù hợp.

Trong multi-tenant, một subject string từ issuer A không mặc nhiên là cùng người với subject string từ issuer B. Thiết kế principal namespace dựa trên trusted issuer/tenant mapping, không dựa vào email chưa xác minh.

### 21.4. Không refresh để tự nâng quyền

HTTP 401 Bearer <code>invalid_token</code> có thể liên quan token lifecycle; HTTP 403 Bearer <code>insufficient_scope</code> thường là thiếu quyền. Refresh cùng grant/scope không tự cấp scope mới. Khi có 403, phân loại authorization policy chứ không tạo vòng lặp refresh/login.

## 22. Quan sát và chẩn đoán sự cố

### 22.1. Metrics hữu ích

| Metric hoặc trường log | Mục đích |
|---|---|
| <code>session_restore_success</code> | Tỷ lệ khôi phục session sau khi route sang node khác |
| <code>oauth2_callback_state_mismatch</code> | Phát hiện vấn đề session/correlation |
| <code>authorized_client_lookup_miss</code> | Tìm token thất bại dù user có session |
| <code>authorized_client_refresh_attempt</code> | Số lần gửi refresh token request |
| <code>authorized_client_refresh_invalid_grant</code> | Theo dõi rotation/reuse/revocation |
| <code>refresh_lock_wait_ms</code> | Mức tranh chấp khi cùng key refresh |
| <code>refresh_cas_conflict_total</code> | Stale write bị từ chối |
| <code>token_storage_latency_ms</code> | Độ trễ DB/Redis |
| <code>redis_session_evictions</code> | Session bị xóa do memory pressure |
| <code>api_401_403_by_service</code> | Phân biệt invalid token và thiếu quyền |

Không dùng raw token, session cookie, client secret, principalName chưa làm sạch hoặc HTTP Authorization header làm metric labels.

### 22.2. Log định danh request an toàn

Ví dụ:

~~~text
instance=portal-b
route=/reports
registrationId=company
principalKeyHash=...
sessionRestored=true
authorizedClientFound=true
tokenRefreshOutcome=skipped_valid_token
upstreamStatus=200
correlationId=...
~~~

Không in:

~~~text
JSESSIONID=...
Authorization: Bearer ...
refresh_token=...
code_verifier=...
OIDC ID Token=...
~~~

### 22.3. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Callback chỉ thành công khi về A | Session/authorization request cục bộ | Spring Session, cookie, LB routing |
| <code>invalid_state</code> sau scale-out | Không thấy request gốc, mất cookie hoặc nhiều login cùng session | Kiểm tra state repository/TTL/proxy |
| User đã login nhưng B không tìm được token | Token nằm trong <code>InMemoryOAuth2AuthorizedClientService</code> của A | Kiểm tra repository/service wiring |
| User bị logout sau rolling deploy | Session serialization không tương thích hoặc Redis evictions | Kiểm tra serializer, version, TTL |
| Node A restart thì mọi user mất login | Không có shared session store hoặc Redis không sẵn sàng | Kiểm tra session configuration/HA |
| HTTP 401 từ API sau khi chuyển node | Token không tìm được, hết hạn hoặc sai audience | Kiểm tra registration/principal, token lifecycle |
| HTTP 403 từ API | Thiếu scope/role/tenant policy | Không tự động xóa token |
| <code>invalid_grant</code> khi scale 2→5 replicas | Có thể concurrent refresh R0 | Lock, reread, CAS, OP rotation policy |
| DB token bị ghi về version cũ | Stale writer/lost update | Conditional update/versioning |
| Logout rồi token record xuất hiện lại | Writer refresh lưu sau cleanup | Revocation generation/tombstone/coordination |
| Token Endpoint bị gọi liên tục | Không lưu refresh result, principal đổi, token short TTL | Success handler, storage, clock skew |
| Scheduler chạy trùng | <code>@Scheduled</code> trên mỗi node | Distributed scheduler/idempotency |
| Session trong Redis nhưng authorized client vẫn local | Repository delegate InMemory service | Đổi service/repository đúng |
| Redis báo lỗi deserialize | Class/session schema thay đổi | Kiểm tra rollout serializer/version |
| Login loop | Cookie blocked, chain matcher/callback hoặc auth state không được lưu | Cookie, SecurityFilterChain, callback state |

### 22.4. Quy trình khoanh vùng

~~~text
Callback OIDC thất bại khi đi qua instance khác?
    |
    +-- Có → kiểm tra cookie + session store + state repository
    |
    v
SecurityContext/Authentication có khôi phục được?
    |
    +-- Không → session serializer/TTL/Redis/proxy
    |
    v
Authorized client có tìm thấy đúng registration/principal?
    |
    +-- Không → repository/service/token storage/tenant key
    |
    v
Access token còn dùng được hay cần refresh?
    |
    +-- Cần refresh → có single-flight + reread + CAS/atomic save?
    |
    v
Token Endpoint chấp nhận refresh?
    |
    +-- invalid_grant → kiểm tra rotation/race/revocation
    |
    v
Resource Server chấp nhận audience/scope/permission?
    |
    +-- 401 → token validation/lifecycle
    |
    +-- 403 → authorization policy
    |
    v
Ứng dụng trả kết quả nghiệp vụ đúng
~~~

## 23. Kiểm thử trên hai instance

Để xác minh đúng bài toán distributed, **unit test một instance không đủ**. Có thể xây integration environment có hai Spring Boot instances, Redis session store và JDBC authorized-client store; OP/API dùng môi trường thử nghiệm được kiểm soát.

### 23.1. Kịch bản callback chéo node

1. Gửi <code>/oauth2/authorization/company</code> tới instance A.
2. Giữ cookie của browser.
3. Hoàn tất authentication tại OP thử nghiệm.
4. Chuyển callback <code>/login/oauth2/code/company</code> tới instance B.
5. Xác nhận B đọc được authorization request từ session store và kiểm tra state hợp lệ.
6. Đảm bảo ID Token validation vẫn hoạt động; không cho phép state sai.

### 23.2. Kịch bản authorized client roaming

1. Login ở A, authorized client được lưu tại shared store.
2. Gửi request API qua B với cùng session cookie.
3. B khôi phục Authentication.
4. B tìm đúng authorized client theo registration/principal.
5. Không có token của user khác trong request.
6. Browser không nhận raw access/refresh token.

### 23.3. Kịch bản restart/failover

1. Login thành công trên A.
2. Dừng A.
3. Gửi request tới B.
4. Kiểm tra session và token state được đọc lại từ store.
5. Kiểm tra policy nếu Redis/DB outage: ứng dụng fail an toàn, không bỏ qua authentication.

### 23.4. Kịch bản refresh token rotation

1. Chuẩn bị authorized client có access token sắp hết hạn và refresh token R0.
2. Cho A và B đồng thời yêu cầu access token của cùng authorized client.
3. Xác nhận coordinator khiến chỉ một lượt refresh hữu hiệu gửi R0, nếu đó là invariant thiết kế.
4. Đảm bảo node chờ đọc lại token mới.
5. Kiểm tra access/refresh token được lưu atomic.
6. Giả lập lock lease hết hạn, stale write/CAS conflict và failure handler xóa token.
7. Đảm bảo không xóa nhầm version mới chỉ vì lỗi trên version cũ.

### 23.5. Kịch bản quyền và logout

1. User logout khỏi một browser, xác minh session không còn được sử dụng.
2. Kiểm tra authorized client được giữ/xóa theo **policy đã công bố**.
3. Nếu có token revocation, kiểm tra AS phản hồi và backend không tiếp tục dùng token bị thu hồi.
4. Thử logout cạnh tranh refresh để không tái tạo token state sau khi quyền đã bị thu hồi.
5. Nếu sản phẩm hỗ trợ nhiều thiết bị, kiểm tra logout một thiết bị không vô tình xóa session/authorization của thiết bị khác ngoài thiết kế.

Những kịch bản này chỉ mô tả yêu cầu kiểm thử; bài không thay cho kiểm thử integration với Authorization Server thật hoặc phiên bản Spring Security cụ thể.

## 24. Bài tập và câu hỏi vận dụng

### Bài 1 — Spring Session đã đủ chưa?

Hệ thống có Redis shared sessions, nhưng Spring Security vẫn dùng <code>InMemoryOAuth2AuthorizedClientService</code> cho authenticated principal.

**Câu hỏi:** Instance B có chắc đọc được authorized client của user đã login ở A không?

**Đáp án:** Không. Cần kiểm tra actual repository/service wiring. Redis chia sẻ session không làm một in-memory authorized-client service trên A tự động chuyển sang Redis.

### Bài 2 — Callback sai state

Browser khởi tạo login ở A, OP redirect callback tới B và B không tìm được state gốc.

**Câu hỏi:** Có nên bỏ kiểm tra state để login thành công?

**Đáp án:** Không. Cần sửa session/cookie/proxy/authorization-request storage. <code>state</code> là cơ chế correlation và bảo vệ OAuth2 callback.

### Bài 3 — Sticky session và failover

Nhóm vận hành đặt sticky session, đăng nhập đã chạy. Khi A restart, user bị logout.

**Câu hỏi:** Vì sao?

**Đáp án:** Sticky session chỉ định tuyến request, không chia sẻ state local qua restart. Dùng shared session store, backup/failover và serializer tương thích nếu yêu cầu tiếp tục phiên.

### Bài 4 — Token dùng chung nhưng refresh race

A và B cùng tải R0 từ JDBC rồi cùng gọi OP. A nhận R1, B nhận <code>invalid_grant</code>.

**Câu hỏi:** JDBC shared store đã giải quyết concurrency chưa?

**Đáp án:** Chưa. Cần single-flight theo key trước refresh, đọc lại sau lock, atomic token update và conditional save/delete khi áp dụng.

### Bài 5 — Bỏ điều kiện version sau CAS conflict

B cố cập nhật token với <code>WHERE version=7</code> nhưng không có hàng nào được cập nhật vì A đã lưu version 8.

**Câu hỏi:** Có nên update không điều kiện cho chắc?

**Đáp án:** Không. Làm vậy tạo lost update. B phải đọc lại state và xử lý token đã có hoặc quyết định recovery theo policy.

### Bài 6 — Logout một trong hai browser sessions

User đăng nhập trên laptop và điện thoại. Cả hai sessions dùng một authorized-client record keyed by principal.

**Câu hỏi:** Nếu logout laptop thì có nên xóa record?

**Đáp án:** Tùy policy. Xóa sẽ ảnh hưởng điện thoại; giữ lại có thể khiến token tồn tại sau logout một phiên. Cần chọn rõ per-session/per-principal/per-device design và cleanup tương ứng.

### Bài 7 — Session hết hạn, refresh token còn

Browser session đã hết hạn nhưng JDBC token store còn refresh token.

**Câu hỏi:** Client có thể bỏ qua đăng nhập và coi user đã authenticated không?

**Đáp án:** Không mặc định. Refresh token phục vụ OAuth2 authorization/delegation, không tự thay thế Authentication của phiên browser hiện tại; cần flow đăng nhập/authorization theo chính sách.

### Bài 8 — Session store outage

Redis mất kết nối, instance không đọc được SecurityContext.

**Câu hỏi:** Có nên tạm chấp nhận mọi request đã có cookie để giữ availability?

**Đáp án:** Không. Cookie không chứng minh user được authenticated nếu backend không thể xác minh/khôi phục session theo mô hình đã chọn. Cần fail an toàn và xử lý sự cố.

### Bài 9 — Reactive storage

Một ứng dụng WebFlux dùng <code>Mono.just(jdbcService.loadAuthorizedClient(...))</code> trên Netty event-loop.

**Câu hỏi:** Có phải storage đã non-blocking?

**Đáp án:** Không. JDBC call chạy blocking trước/đang khi tạo Mono. Cần reactive driver/storage phù hợp hoặc cô lập blocking I/O có kiểm soát trên scheduler thích hợp.

### Bài 10 — Thiết kế một hệ thống hai replica

Hãy phác thảo:

1. Hai Spring Boot OAuth2/OIDC Client instances phía sau load balancer.
2. Shared Spring Session Redis cho SecurityContext và authorization-request state.
3. Shared authorized-client service phù hợp với policy per-session/per-principal.
4. Registration/principal keys có namespace issuer/tenant.
5. Coordinator per-key cho refresh token rotation.
6. Atomic save của access/refresh token và conditional delete theo version.
7. Logout/revocation policy khi user có nhiều thiết bị.
8. Protected Redis/database và không log credential.
9. Plan rolling deployment, serializer compatibility, session TTL và failover.
10. Integration tests cho callback đi qua A/B và concurrent refresh.

Giải thích điều gì xảy ra khi **A crash trước Token Endpoint**, **A crash sau OP refresh nhưng trước DB save**, và **A crash sau DB save nhưng trước release lock**.

## 25. Tổng kết

- **HTTP session**, **OAuth2 authorization request**, **SecurityContext** và **OAuth2AuthorizedClient** là các trạng thái khác nhau; cần xác định rõ repository và vòng đời.
- **Spring Session + Redis** có thể giúp Servlet <code>HttpSession</code> hoặc WebFlux <code>WebSession</code> được chia sẻ giữa replicas, hỗ trợ callback OIDC đi qua load balancer.
- **Authorized client** có thể nằm trong session hoặc <code>OAuth2AuthorizedClientService</code>. Không giả định bật Spring Session làm mọi in-memory token store tự động shared.
- Với authenticated principals, <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code> có thể delegate đến service; <code>JdbcOAuth2AuthorizedClientService</code> là một lựa chọn shared persistence, nhưng không mặc định có distributed refresh lock/CAS.
- Chọn **web manager** cho HTTP request và **service manager** cho background job; đúng manager không thay thế storage và concurrency policy.
- Khi OP bật **refresh token rotation**, nhiều instance cùng dùng R0 có thể gây <code>invalid_grant</code> và reuse detection. Cần single-flight theo key, đọc lại sau lock, atomic save token pair và conditional update/delete khi phù hợp.
- Sticky session **không thay thế** shared session/persistent token store; distributed sessions cũng không thay thế distributed job scheduling.
- Session logout, xóa local authorized client, OP token revocation và OIDC SSO logout **không tương đương**.
- Trong multi-tenant/multi-issuer, principal key phải được tạo từ identity tin cậy và có namespace phù hợp; không cho browser chọn key token.
- Bảo vệ Redis/DB/token store, cookie, private secrets, backups và TLS; không log session ID, access/refresh token, authorization code, PKCE verifier hoặc raw ID Token.
- Để xác minh scale-out, cần kiểm thử **callback chéo node, roaming authorized client, restart/failover và concurrent refresh**, không chỉ kiểm tra login thành công trên một máy.

### Tài liệu tham khảo

- **Spring Session Reference — Spring Session with Redis:** chia sẻ HTTP session, WebSession và cấu hình session store.
- **Spring Security Reference — OAuth2 Login (Servlet):** authorization request repository, callback và lưu Authentication.
- **Spring Security Reference — OAuth2 Client:** <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code> và <code>OAuth2AuthorizedClientManager</code>.
- **Spring Security Java API:** <code>HttpSessionOAuth2AuthorizedClientRepository</code>, <code>AuthenticatedPrincipalOAuth2AuthorizedClientRepository</code>, <code>JdbcOAuth2AuthorizedClientService</code>.
- **Spring Security Reference — Reactive OAuth2 Client:** <code>ServerOAuth2AuthorizedClientRepository</code>, <code>ReactiveOAuth2AuthorizedClientService</code> và <code>DefaultReactiveOAuth2AuthorizedClientManager</code>.
- **Spring Security Reference — Session Management, CSRF Protection và Logout:** phân biệt browser session, authorization và cleanup.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, Access Token và Refresh Token Grant.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ Authorization Code Flow.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token tại Authorization Server.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh token rotation, replay protection và OAuth security.
- **OpenID Connect Core 1.0:** OIDC Authorization Code Flow, ID Token, state/nonce và UserInfo.
- **Tài liệu Authorization Server cụ thể:** token lifetime, refresh rotation, reuse-detection policy, consent/reauthorization và revocation semantics; cần kiểm chứng theo provider được tích hợp.
