# 1.3. Use case đăng nhập liên kết và gọi API thay mặt người dùng

## 1. Bài toán thực tế

Giả sử một công ty có **Employee Portal** để nhân viên xem hồ sơ, đơn nghỉ phép và đơn hàng được phân quyền. Công ty đã có hệ thống quản lý danh tính tập trung (Identity Provider, viết tắt **IdP**). Người dùng muốn:

1. Mở Employee Portal và chọn **Đăng nhập với tài khoản công ty** mà không cần tạo mật khẩu riêng cho Portal.
2. Sau khi đăng nhập, xem tên và thông tin tài khoản của mình trên Portal.
3. Chọn **Đơn hàng của tôi**. Portal gọi **Orders API** để lấy dữ liệu đúng với nhân viên hiện tại, theo quyền mà người đó đã được cấp.

Trong Spring Security, đây là một tình huống kết hợp hai khả năng có liên quan nhưng phục vụ hai mục đích khác nhau:

- **OpenID Connect (OIDC) login** xác thực người dùng và cho Portal biết người đăng nhập là ai.
- **OAuth 2.0 Client** cho phép Portal có và sử dụng **access token** để gọi Orders API **thay mặt người dùng đã đăng nhập**.

Ví dụ, nhân viên An được phép đọc đơn hàng của chính mình. Khi An mở màn hình đơn hàng, Portal không dùng quyền quản trị chung của ứng dụng để truy cập toàn bộ dữ liệu; Portal gửi access token đại diện cho phiên ủy quyền của An. Orders API xác minh token, quyền đọc và danh tính người dùng trước khi trả kết quả.

### Kết quả cần hiểu

Sau bài học, người đọc cần giải thích được ai đăng nhập ở đâu, token nào phục vụ việc gì, Spring Security lưu trạng thái đăng nhập và access token như thế nào, và cách một ứng dụng web gọi API dưới danh nghĩa người dùng mà không đưa bí mật của OAuth Client ra trình duyệt.

## 2. Các vai trò trong kiến trúc

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| **End User / Resource Owner** | Người đăng nhập và là chủ thể của dữ liệu, quyền truy cập | Nhân viên An |
| **Browser** | Hiển thị giao diện, đi theo chuyển hướng đăng nhập, giữ session cookie của Portal | Trình duyệt của An |
| **OAuth 2.0 Client / Relying Party** | Ứng dụng đưa người dùng đến IdP, xử lý callback, lưu authorized client và gọi API | Spring Boot Employee Portal |
| **OpenID Provider / Authorization Server** | Xác thực người dùng, cấp mã ủy quyền và token theo chính sách | IdP công ty |
| **Resource Server** | API nhận access token, xác minh token và thực thi quyền truy cập | Spring Security Orders API |

Một IdP có thể đồng thời là **OpenID Provider** (hỗ trợ OIDC) và **Authorization Server** (hỗ trợ OAuth 2.0). Trong tình huống này Portal đóng **hai vai trò cùng lúc**: bên dựa vào danh tính OIDC để đăng nhập và OAuth Client sử dụng quyền đã được cấp để truy cập tài nguyên.

Khái niệm **đăng nhập liên kết** (federated login) có nghĩa ứng dụng dựa vào một nhà cung cấp danh tính được tin cậy, thay vì tự thu thập mật khẩu. Khi cùng một IdP phục vụ nhiều ứng dụng, người dùng có thể có trải nghiệm SSO: đã đăng nhập ở IdP thì đăng nhập ứng dụng tiếp theo thường không cần nhập lại mật khẩu, tùy chính sách phiên và xác thực bổ sung.

## 3. Phân biệt xác thực, ủy quyền và các token

| Khái niệm | Trả lời câu hỏi | Bên sử dụng chính |
|---|---|---|
| **OIDC ID Token** | Người dùng đã được xác thực là ai, vào lúc nào, bởi IdP nào? | **Portal (OIDC Client)** |
| **OAuth 2.0 Access Token** | Client được phép gọi tài nguyên nào, với quyền nào, trong thời hạn nào? | **Orders API (Resource Server)** |
| **Refresh Token** (nếu được cấp) | Client có thể xin access token mới mà không cần đưa người dùng đăng nhập lại không? | **Portal**, dùng với token endpoint |
| **Portal session cookie** | Trình duyệt đang gắn với phiên đăng nhập nào của Portal? | **Portal**, khi nhận yêu cầu từ browser |
| **Authorization Code** | Mã ngắn hạn, dùng một lần để đổi token ở token endpoint | **Portal**, tại bước callback |

**ID Token không phải access token.** ID Token có các claim OIDC như **iss** (issuer), **sub** (định danh ổn định trong phạm vi issuer), **aud** (đối tượng nhận ID Token, thường là client ID), **exp** và có thể chứa thông tin hồ sơ. Portal xác minh ID Token khi đăng nhập; không gửi ID Token đến Orders API để thay access token.

**Access token là bằng chứng cấp quyền cho API.** Token có thể là JWT hoặc opaque token, tùy IdP. API cần xác minh hiệu lực và phạm vi sử dụng: chữ ký hoặc introspection phù hợp, issuer, thời gian, **audience** dành cho API, cùng scope/authority và các quy tắc nghiệp vụ.

**Scope và audience không đồng nghĩa:**

- Scope, ví dụ **orders.read**, mô tả loại thao tác được cấp phép.
- Audience, ví dụ **orders-api**, xác định API dự kiến nhận access token. Một token có **orders.read** nhưng dành cho API khác vẫn không nên được Orders API chấp nhận.
- Quyền nghiệp vụ, ví dụ “An chỉ được xem đơn hàng của An”, vẫn phải được thực thi ở API bằng dữ liệu và danh tính tin cậy; chỉ có scope **orders.read** chưa đủ.

OAuth 2.0 hỗ trợ cấp quyền; OIDC bổ sung lớp xác thực danh tính. Có thể dùng OAuth 2.0 mà không đăng nhập OIDC, nhưng việc một ứng dụng web muốn **đăng nhập người dùng** nên dựa trên cơ chế xác thực rõ ràng như OIDC, không suy ra danh tính chỉ vì nhận được access token.

## 4. Luồng tổng thể: Authorization Code + OIDC + gọi API

Luồng phù hợp với ứng dụng web Spring Boot giữ session phía server là **Authorization Code Flow**. Có thể bổ sung **PKCE** để ràng buộc mã ủy quyền với request đã khởi tạo, kể cả khi client có secret.

~~~mermaid
sequenceDiagram
    actor User as Nhân viên
    participant Browser as Browser
    participant Portal as Spring Boot Portal (OAuth2 Client)
    participant IdP as OIDC Provider / Authorization Server
    participant API as Orders API (Resource Server)

    User->>Browser: Chọn Đăng nhập công ty
    Browser->>Portal: GET /oauth2/authorization/company
    Portal-->>Browser: 302 đến authorization endpoint (state, nonce, PKCE)
    Browser->>IdP: Authorization request
    IdP->>User: Xác thực và xin đồng ý nếu cần
    IdP-->>Browser: 302 về callback ?code=...&state=...
    Browser->>Portal: GET /login/oauth2/code/company
    Portal->>IdP: POST /token (code, xác thực client, PKCE verifier)
    IdP-->>Portal: ID Token + Access Token (+ Refresh Token)
    Portal->>Portal: Xác minh ID Token; tạo SecurityContext và lưu authorized client
    Portal-->>Browser: Session cookie, chuyển về trang đăng nhập thành công
    Browser->>Portal: GET /bff/orders + session cookie
    Portal->>Portal: Lấy authorized client của người đang đăng nhập
    Portal->>API: GET /api/orders + Authorization: Bearer access_token
    API->>API: Xác minh token, audience, scope và quyền dữ liệu
    API-->>Portal: Đơn hàng của người dùng
    Portal-->>Browser: JSON / giao diện đơn hàng
~~~

Các bước đáng chú ý:

1. **Khởi động đăng nhập:** Spring Security mặc định cung cấp URL **/oauth2/authorization/{registrationId}**; trong ví dụ **registrationId** là **company**.
2. **Chuyển hướng đến IdP:** Request dùng **response_type=code**, **client_id**, **redirect_uri**, các scope như **openid profile email orders.read**, **state**, cùng thông tin OIDC/PKCE khi được cấu hình. **state** giúp liên kết callback với request khởi tạo, chống tấn công CSRF vào luồng ủy quyền. **nonce** ràng buộc ID Token với lần xác thực OIDC; **PKCE** ràng buộc authorization code với client đã khởi tạo giao dịch.
3. **Xác thực tập trung:** Người dùng nhập thông tin xác thực tại IdP; Portal không nhìn thấy mật khẩu. IdP có thể áp dụng MFA, SSO, điều kiện truy cập và consent tùy tổ chức.
4. **Callback:** IdP chuyển hướng browser về URL đã đăng ký với một **authorization code** ngắn hạn và **state**. Spring Security kiểm tra trạng thái request trước khi đổi code.
5. **Đổi code lấy token:** Portal gửi yêu cầu **server-to-server** đến token endpoint, sử dụng cơ chế xác thực client đã đăng ký và **code_verifier** khi áp dụng PKCE. ID Token được xác minh theo yêu cầu OIDC, gồm chữ ký, issuer, audience, thời hạn và nonce khi có.
6. **Tạo phiên đăng nhập:** Spring Security tạo **Authentication**, thường với principal kiểu **OidcUser**, rồi lưu vào **SecurityContext** gắn với HTTP session. Đồng thời, **OAuth2AuthorizedClient** liên kết client registration, người dùng và các token đã nhận.
7. **Người dùng mở dữ liệu:** Browser gọi Portal bằng session cookie. Portal xác định người dùng từ SecurityContext, tìm access token tương ứng và gọi Orders API qua HTTPS với **Authorization: Bearer ...**.
8. **API kiểm soát truy cập:** API kiểm tra token rồi áp dụng quyền **orders.read** và kiểm tra đơn hàng có thuộc người dùng hay không. Trình duyệt chỉ nhận dữ liệu ứng dụng cần hiển thị.

Không có yêu cầu OAuth 2.0 nào buộc access token phải được đưa vào JavaScript ở browser. Với mô hình **Backend for Frontend (BFF)** hoặc ứng dụng MVC dùng session, Portal giữ token phía server và browser chỉ gửi session cookie.

## 5. Minh họa triển khai với Spring Boot và Spring Security

Ví dụ dưới đây dùng **Java 17+**, cú pháp cấu hình Spring Security hiện đại trên Spring Boot 3 / Spring Security 6. Nó minh họa trách nhiệm của từng ứng dụng; các URL, client ID, scope và audience là giá trị giả định, cần được cấu hình tương ứng ở IdP thực tế.

### 5.1. Cấu hình IdP trước khi chạy ứng dụng

Tạo một OAuth/OIDC client **portal-web** tại IdP, với:

- Loại client: **confidential web client** vì Portal xử lý token phía server, có khả năng giữ client secret.
- Authorization grant: **authorization_code**; nên bật/hỗ trợ **PKCE S256**.
- Redirect URI đăng ký: **http://localhost:8080/login/oauth2/code/company** cho môi trường phát triển. Ở production dùng HTTPS và tên miền chính xác.
- Scope OIDC **openid** và những scope thực sự cần dùng, ví dụ **profile**, **email**, **orders.read**.
- Access token dành cho **Orders API**, với audience phù hợp (ví dụ **orders-api**). Cách thiết lập audience tùy IdP.

Client secret không được nhúng vào mã nguồn, HTML hoặc JavaScript. Các tùy chọn **offline_access**, refresh token, consent, logout endpoint hay cách thêm audience khác nhau giữa các nhà cung cấp, không nên mặc định nhà cung cấp nào cũng hỗ trợ.

### 5.2. Ứng dụng Portal: OIDC login và OAuth2 Client

Các dependency Gradle cốt lõi:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-webflux' // dùng WebClient
}
~~~

Tệp **application.yml** của Portal:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          company:
            issuer-uri: https://sso.example.test/realms/acme

orders:
  api-base-url: http://localhost:8081
~~~

Thuộc tính **issuer-uri** cho phép Spring Security tải metadata OIDC/OAuth từ discovery endpoint khi IdP hỗ trợ. Cần thay địa chỉ ví dụ bằng issuer chính xác của IdP. Nếu ứng dụng đặt sau reverse proxy, bảo đảm cơ chế forwarded headers và giá trị **{baseUrl}** tạo ra redirect URI HTTPS đúng với đăng ký.

**SecurityFilterChain** bảo vệ các trang cần đăng nhập:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class PortalSecurityConfig {

    @Bean
    SecurityFilterChain portalSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

**oauth2Login()** xử lý chuyển hướng, callback và tạo phiên xác thực OIDC. **oauth2Client()** bổ sung cơ chế quản lý authorized client để ứng dụng gọi tài nguyên được bảo vệ. Cấu hình này giữ nguyên CSRF protection mặc định cho các yêu cầu thay đổi trạng thái.

Ví dụ controller vừa đọc danh tính từ OIDC principal, vừa lấy access token của chính người dùng đang đăng nhập để gọi API:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@RestController
class PortalController {

    private final WebClient ordersApi;

    PortalController(WebClient.Builder webClientBuilder,
                     @Value("${orders.api-base-url}") String baseUrl) {
        this.ordersApi = webClientBuilder.baseUrl(baseUrl).build();
    }

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        // sub lấy từ danh tính đã được IdP xác thực.
        return Map.of("sub", user.getSubject());
    }

    @GetMapping("/bff/orders")
    List<OrderView> myOrders(
        @RegisteredOAuth2AuthorizedClient("company")
        OAuth2AuthorizedClient authorizedClient
    ) {
        String accessToken = authorizedClient.getAccessToken().getTokenValue();

        return ordersApi.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .bodyToFlux(OrderView.class)
            .collectList()
            .block();
    }

    record OrderView(String id, String title) {}
}
~~~

Điểm cốt lõi nằm ở **@RegisteredOAuth2AuthorizedClient("company")**: Spring Security tìm authorized client gắn với registration **company** và principal hiện tại, thay vì dùng token cố định của cả hệ thống. Khi có cấu hình provider hỗ trợ refresh và IdP cấp refresh token, cơ chế quản lý authorized client có thể xin access token mới khi cần; không được giả định refresh token luôn tồn tại.

Ví dụ chủ động gắn header **Bearer** để làm rõ đường đi của access token. Với ứng dụng có nhiều lệnh gọi API, cũng có thể cấu hình **ServletOAuth2AuthorizedClientExchangeFilterFunction** cho WebClient để tự chọn authorized client và gắn token, nhưng cần xác định rõ registration/principal cho từng request, tránh vô tình gửi token đến API không liên quan.

### 5.3. Ứng dụng Orders API: Resource Server

Orders API là ứng dụng độc lập và **không cần thực hiện OIDC login** để xử lý request mang bearer token. Nó cần dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Ví dụ cấu hình API dùng access token dạng **JWT**:

~~~yaml
server:
  port: 8081

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://sso.example.test/realms/acme

security:
  expected-audience: orders-api
~~~

Một SecurityFilterChain cho API thuần bearer token, không dùng cookie hoặc form:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain ordersApiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Chỉ tắt CSRF trong ví dụ API này** vì đây là Resource Server stateless, chỉ nhận bearer token qua header và không dùng cookie để xác thực. Không sao chép việc tắt CSRF sang Portal dùng session cookie. Spring Security thường chuyển scope của JWT thành authority có tiền tố **SCOPE_**, vì vậy scope **orders.read** tương ứng **SCOPE_orders.read** ở kiểm tra endpoint.

Ngoài xác minh chữ ký, issuer và hạn token, API phải kiểm tra **audience** phù hợp. Cấu hình **issuer-uri** tự nó không thay thế phép kiểm tra audience theo hợp đồng giữa API và Authorization Server. Ví dụ validator cho JWT:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtDecoders;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtAudienceConfig {

    @Bean
    JwtDecoder jwtDecoder(
        @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
        String issuer,
        @Value("${security.expected-audience}")
        String expectedAudience
    ) {
        NimbusJwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(expectedAudience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", "Unexpected audience", null));

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator));
        return decoder;
    }
}
~~~

API xác định chủ thể từ token **đã được xác minh**, không tin một tham số như **?userId=an** do trình duyệt tự truyền:

~~~java
import java.util.List;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersController {

    @GetMapping("/api/orders")
    List<Map<String, String>> myOrders(@AuthenticationPrincipal Jwt jwt) {
        String ownerSubject = jwt.getSubject();

        // Minh họa: khi triển khai thật, truy vấn DB theo ownerSubject
        // và kiểm tra thêm chính sách quyền theo từng bản ghi.
        return List.of(Map.of(
            "id", "ORD-101",
            "title", "Đơn hàng minh họa của " + ownerSubject
        ));
    }
}
~~~

Trong production, API thường ánh xạ cặp **(issuer, subject)** sang tài khoản nội bộ và truy vấn các bản ghi người đó được quyền đọc. Không dùng một claim tên hoặc email chưa được chuẩn hóa để làm khóa phân quyền nếu hệ thống chưa có chính sách rõ ràng. Nếu IdP cấp **opaque access token**, Resource Server cần dùng **introspection** thay cho JWT decoder.

## 6. Một request nhìn từ browser, Portal và API

### 6.1. Browser khởi động đăng nhập

~~~http
GET /oauth2/authorization/company HTTP/1.1
Host: localhost:8080
~~~

Spring Security trả **302** dẫn đến authorization endpoint của IdP; sau khi đăng nhập IdP gọi callback đã đăng ký. Browser nhận cookie phiên của Portal (ví dụ **JSESSIONID**, cấu hình thêm **Secure**, **HttpOnly**, **SameSite** phù hợp với HTTPS và luồng redirect).

### 6.2. Browser truy cập dữ liệu ứng dụng

~~~http
GET /bff/orders HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=<gia-tri-phien>
~~~

Browser **không cần nhận access token**. Portal dùng session xác định user, tìm authorized client rồi gọi API:

~~~http
GET /api/orders HTTP/1.1
Host: localhost:8081
Authorization: Bearer <access-token-hop-le-cho-orders-api>
~~~

API thành công có thể trả:

~~~json
[
  { "id": "ORD-101", "title": "Đơn hàng minh họa" }
]
~~~

Đây là **hai quan hệ tin cậy tách biệt**: browser chứng minh phiên với Portal bằng cookie; Portal chứng minh quyền truy cập API bằng access token. Session cookie không dùng như bearer token của Orders API, và access token không nên bị đưa vào URL, log, hoặc response HTML.

## 7. Khi nào sử dụng mô hình này?

| Tình huống | Vì sao phù hợp |
|---|---|
| **Cổng nhân viên dùng tài khoản công ty** | Tận dụng IdP, SSO, MFA và vòng đời quản lý tài khoản tập trung |
| **Portal gọi API đơn hàng, lịch làm việc, tài liệu của từng người** | Mỗi request mang quyền đã cấp cho người dùng thay vì quyền hệ thống chung |
| **BFF cho web frontend** | Giữ client secret và access/refresh token phía server; frontend chỉ cần cookie phiên |
| **Một Portal gọi nhiều API** | Có thể quản lý scope/audience/token riêng cho từng API; tránh dùng nhầm token giữa các tài nguyên |

Mô hình này khác **client_credentials**: client_credentials đại diện cho chính ứng dụng, không đại diện cho An. Nếu tác vụ chạy nền cần quyền của ứng dụng thì client_credentials có thể hợp lý; nếu cần biết dữ liệu và quyền của người dùng đã đăng nhập, phải chọn mô hình ủy quyền phù hợp với người dùng đó.

Ngoài ra, OAuth 2.0 **Token Exchange / On-Behalf-Of** là một cách riêng khi một API trung gian cần nhận token đầu vào và đổi lấy token mới cho API khác. Không mặc định mọi hệ thống đều hỗ trợ token exchange; đối với ví dụ Portal giữ authorized client, Portal gọi trực tiếp Orders API bằng access token được cấp cho API đó.

## 8. Vòng đời phiên, token và logout

**Phiên đăng nhập của Portal** và **thời hạn access token** có thể khác nhau. Phiên cookie còn hiệu lực không bảo đảm access token cũng còn hiệu lực. Khi access token hết hạn:

- Nếu IdP cấp refresh token và client được cấu hình hỗ trợ refresh, Spring Security có thể dùng refresh token để lấy access token mới; token mới phải được lưu lại trong authorized client repository/service.
- Nếu không có quyền hoặc không thể refresh, người dùng có thể cần thực hiện lại authorization flow. Ứng dụng nên xử lý lỗi này bằng điều hướng đăng nhập hoặc thông báo rõ ràng, không lặp request vô hạn.
- Nếu quyền bị thu hồi, token có thể bị từ chối tùy chính sách token, introspection, thời hạn hiệu lực và cơ chế thu hồi của IdP. Không suy ra mọi JWT sẽ bị vô hiệu ngay khi người dùng logout.

**Đăng xuất** có thể gồm nhiều việc riêng: hủy session Portal, xóa token/authorized client của Portal, và tùy IdP thực hiện **OIDC RP-Initiated Logout** để kết thúc phiên đăng nhập tập trung. Chỉ xóa cookie Portal không nhất thiết đăng xuất IdP; chỉ logout IdP cũng không tự động thu hồi mọi access token đã cấp. Thiết kế logout cần theo chính sách sản phẩm và khả năng hỗ trợ của IdP.

Mặc định cơ chế lưu authorized client có thể phù hợp với môi trường phát triển nhưng không tự bảo đảm dữ liệu bền vững trên nhiều instance. Khi triển khai nhiều node hoặc cần quản lý phiên/thu hồi token, lựa chọn repository/service lưu trữ phù hợp, bảo vệ token khi lưu, kiểm soát quyền truy cập và thời gian sống.

## 9. Các giới hạn tin cậy và điểm bảo mật quan trọng

1. **Luôn dùng HTTPS** cho các endpoint trong production; đăng ký redirect URI chính xác. Không dùng wildcard redirect URI tùy tiện.
2. **Bảo vệ authorization flow:** kiểm tra **state**, dùng **nonce** đúng với OIDC, và ưu tiên **PKCE S256**. Spring Security xử lý nhiều phần của luồng; nếu tùy biến resolver/filter, phải bảo toàn các kiểm tra này.
3. **Giữ bí mật phía server:** client secret, access token và refresh token không xuất hiện trong source frontend, URL, analytics hoặc application log. Secret nên được nạp qua secret manager hoặc môi trường an toàn.
4. **Bảo vệ cookie và chống CSRF:** Portal dùng session cookie cần **Secure**, **HttpOnly**, **SameSite** theo luồng triển khai; giữ CSRF protection cho các thao tác thay đổi trạng thái. CORS và CSRF giải quyết các vấn đề khác nhau.
5. **Không nhầm token:** dùng ID Token cho xác thực ở Client; access token cho Resource Server; không dùng refresh token để gọi API; không gửi access token cho host ngoài audience dự kiến.
6. **API tự chịu trách nhiệm phân quyền:** kiểm tra token, audience, scope và quyền theo đối tượng tài nguyên. Không tin user ID, role hay scope do browser tự gửi ngoài token đã xác minh.
7. **Giới hạn quyền:** chỉ yêu cầu những scope cần dùng; nếu cần API khác, xác định audience/scope và cơ chế lấy token tương ứng. Token do người dùng cấp không mặc nhiên có quyền đọc mọi dữ liệu.
8. **Xử lý lỗi an toàn:** API trả **401 Unauthorized** với token thiếu/không hợp lệ, **403 Forbidden** khi token hợp lệ nhưng thiếu quyền; Portal không hiển thị token hoặc thông tin nhạy cảm trong thông báo lỗi.

Một lưu ý đối với **SSO**: khả năng đăng nhập không cần nhập lại mật khẩu phụ thuộc phiên của IdP, chính sách MFA, prompt/login_hint/max_age và tình trạng tài khoản. Tích hợp OIDC không có nghĩa mọi lần login sẽ tự động bỏ qua xác thực.

## 10. Cách tự kiểm chứng luồng

Sau khi IdP được cấu hình và hai ứng dụng chạy với issuer/token hợp lệ, có thể kiểm tra theo kịch bản:

| Thao tác | Kết quả mong đợi |
|---|---|
| Mở **/bff/orders** khi chưa đăng nhập | Portal đưa browser đến luồng OIDC login |
| Đăng nhập ở IdP và quay về Portal | Portal có phiên hợp lệ; **/me** trả về **sub** của người dùng |
| Gọi **/bff/orders** sau khi đăng nhập | Portal gọi Orders API với access token của authorized client hiện tại và hiển thị dữ liệu |
| Gọi trực tiếp **/api/orders** không có bearer token | Resource Server trả **401** |
| Gọi API bằng token hợp lệ nhưng thiếu **orders.read** | Resource Server trả **403** |
| Gọi API bằng token không có audience **orders-api** | Resource Server từ chối token, thông thường **401** |
| Đăng nhập bằng người dùng khác | API truy xuất dữ liệu theo danh tính người đó; không nhận user ID do Portal/browser tự gán |
| Access token hết hạn | Refresh hoặc yêu cầu authorize lại theo khả năng IdP và cấu hình client |

Các kiểm thử trên phụ thuộc cách IdP phát hành token, vì vậy cần quan sát **issuer**, **scope**, **audience** và thời hạn bằng công cụ quản trị an toàn hoặc cơ chế debug đã che thông tin nhạy cảm; không sao chép bearer token thực vào log hay tài liệu công khai.

## 11. Những nhầm lẫn thường gặp

**“Đăng nhập thành công nghĩa là gọi được mọi API.”** Không đúng. OIDC authentication chỉ xác nhận phiên đăng nhập ở Portal. Quyền dùng API còn tùy access token, audience, scope, chính sách người dùng và kiểm tra nghiệp vụ tại Resource Server.

**“Có ID Token rồi thì gửi ID Token đến API.”** Không đúng. ID Token được cấp cho OIDC Client; API cần access token phù hợp với chính API đó.

**“Truyền userId trong query là đủ để gọi thay mặt người dùng.”** Không đúng. User ID do client tự chọn có thể bị sửa. API phải lấy định danh đã được xác minh từ access token hoặc kết quả introspection, sau đó kiểm tra quyền với dữ liệu.

**“Dùng client_credentials là gọi API thay người dùng.”** Không đúng trong ngữ cảnh này. Grant đó cấp token đại diện cho client/application, không mang ngữ nghĩa user đã đăng nhập.

**“Spring Security tự cấp quyền đến từng đơn hàng.”** Không đúng. Spring Security cung cấp nền tảng xác thực và kiểm tra authority; API vẫn phải kiểm tra quyền sở hữu, tenant, trạng thái dữ liệu và quy tắc nghiệp vụ.

**“Một bearer token dùng được cho tất cả microservice.”** Không nên giả định. Token chỉ được gửi đến tài nguyên mà authorization server cấp quyền và audience cho phép. Nếu cần gọi API khác, thiết kế scope, audience và cơ chế ủy quyền phù hợp.

## 12. Tổng kết kiến trúc

Trong use case này, **OIDC** cho phép Portal đăng nhập liên kết và tạo **SecurityContext** của nhân viên. **OAuth 2.0 Client** quản lý authorization code flow và **OAuth2AuthorizedClient** chứa access token để Portal gọi **Orders API**. **Spring Security Resource Server** bảo vệ API bằng xác minh access token, scope, audience và quyền truy cập dữ liệu.

Điểm phân định trách nhiệm là: **IdP xác thực và cấp token; Portal duy trì phiên người dùng và thực hiện lời gọi được ủy quyền; API quyết định tài nguyên nào được trả về.** Giữ sự phân định này giúp tránh nhầm ID Token với access token, tránh dùng đặc quyền ứng dụng thay cho quyền người dùng, và xây dựng được cả đăng nhập liên kết lẫn gọi API thay mặt người dùng theo mô hình rõ ràng.
