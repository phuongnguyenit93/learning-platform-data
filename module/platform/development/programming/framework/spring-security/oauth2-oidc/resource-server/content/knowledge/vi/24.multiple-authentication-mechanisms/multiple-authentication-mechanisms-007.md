# Nhiều filter chain cho API, trình duyệt và các endpoint riêng

Một ứng dụng Spring Boot có thể đồng thời phục vụ **REST API cho mobile/service client**, **giao diện web cho người dùng đăng nhập bằng OpenID Connect (OIDC)**, **health checks cho hệ thống giám sát** và **webhook của đối tác**. Những request này không nhất thiết dùng chung một cơ chế xác thực:

- REST API thường nhận **OAuth 2.0 Bearer access token** và hoạt động **stateless**.
- Giao diện web truyền thống thường dùng **OAuth2 Login/OIDC**, phiên đăng nhập và cookie phiên.
- Health/liveness endpoint có thể cần phản hồi không đòi access token.
- Webhook có thể cần **chữ ký HMAC** hoặc mTLS, không phải JWT của người dùng.
- API nội bộ có thể có yêu cầu riêng về client credentials, issuer, audience hoặc mTLS.

Trong **Spring Security Servlet**, có thể tạo **nhiều bean `SecurityFilterChain`** với matcher và thứ tự riêng. Spring Security sẽ chọn **chain đầu tiên khớp request**, sau đó áp dụng các filter và quy tắc phân quyền **của chính chain đó**.

Đây là công cụ mạnh để tách cơ chế xác thực, nhưng cũng là nguồn lỗi dễ bỏ sót: matcher quá rộng có thể nuốt request của chain khác; matcher quá hẹp có thể bỏ lỡ callback OIDC; một route không khớp bất kỳ chain nào có nguy cơ **không được Spring Security bảo vệ**.

Bài học giải thích kiến trúc nhiều chain trong **Spring Security OAuth 2.0/OIDC Resource Server**, cách phân biệt **`securityMatcher` với `requestMatchers`**, cấu hình tách **API JWT**, **trình duyệt OAuth2 Login**, **endpoint đặc biệt** và **fallback deny-all**, sau đó kiểm thử phản hồi thực tế bằng MockMvc.

## 1. Khi nào cần nhiều SecurityFilterChain?

Giả sử ứng dụng Orders có các tuyến:

| Đường dẫn | Caller | Phương thức xác thực mong muốn | Cách quản lý trạng thái |
| --- | --- | --- | --- |
| `GET /api/orders/123` | Mobile app, service-to-service | JWT access token, kiểm tra scope và quyền đối tượng | Stateless |
| `POST /api/orders` | OAuth2 client gọi REST API | JWT access token với `orders.write` | Stateless |
| `GET /app/orders` | Người dùng mở trình duyệt | OAuth2 Login/OIDC, session cookie sau đăng nhập | Session khi cần |
| `GET /login` | Browser chưa đăng nhập | Trang đăng nhập hoặc redirect sang OIDC Provider | Browser flow |
| `GET /oauth2/authorization/corporate` | Browser bắt đầu OIDC flow | OAuth2 authorization request | Browser flow |
| `GET /login/oauth2/code/corporate` | OIDC Provider redirect về | Authorization Code callback | Browser flow |
| `GET /status/live` | Load balancer/orchestrator | Public theo chính sách health | Không cần session |
| `POST /hooks/payments` | Payment provider | Chữ ký webhook hoặc mTLS | Không dùng browser session |
| `/internal/**` | Service nội bộ | mTLS, JWT client credentials hoặc phương án riêng | Theo hợp đồng nội bộ |

Nếu đặt mọi thứ vào một chain rồi bật đồng thời `oauth2ResourceServer()`, `oauth2Login()` và một endpoint `permitAll()`, ứng dụng có thể chạy, nhưng behavior sẽ khó dự đoán hơn:

- Browser chưa đăng nhập có thể nhận **401 Bearer challenge** thay vì **302 redirect** đến login.
- API client có thể bị **302 redirect tới trang HTML**, không phù hợp REST contract.
- Một Bearer token hỏng gửi tới endpoint public vẫn có thể bị filter xác thực và trả 401.
- Cookie/session và chính sách **CSRF** có thể bị trộn với các route Bearer-only.
- Webhook được `permitAll` nhưng thiếu bước xác thực chữ ký có thể bị giả mạo.

**Nhiều chain giúp cô lập cơ chế**, không phải tạo nhiều tầng bảo vệ tự động chồng lên nhau. Mỗi request thường đi qua **một chain được chọn**, không phải tất cả chain.

## 2. FilterChainProxy chọn chain như thế nào?

Spring Security đăng ký một servlet filter trung tâm, thông thường là **`DelegatingFilterProxy`** chuyển tới **`FilterChainProxy`**. Bên trong `FilterChainProxy` có một danh sách `SecurityFilterChain` theo thứ tự.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["DelegatingFilterProxy → FilterChainProxy"]
    B --> C{"Chain 1: /status/live hoặc /status/ready?"}
    C -- "Có" --> D["Status chain: public GET, không bật Bearer"]
    C -- "Không" --> E{"Chain 2: /api/**?"}
    E -- "Có" --> F["API chain: JWT Resource Server + stateless"]
    E -- "Không" --> G{"Chain 3: app/login/oauth2/assets?"}
    G -- "Có" --> H["Browser chain: OAuth2 Login/OIDC + session + CSRF"]
    G -- "Không" --> I["Fallback chain: denyAll"]
    D --> J["Servlet / Controller nếu filter cho phép"]
    F --> J
    H --> J
    I --> K["Từ chối request"]
~~~

### Ba quy tắc quan trọng

1. **Ưu tiên chain khớp đầu tiên.** Chỉ khi một chain **không khớp** thì Spring Security mới xét chain tiếp theo.
2. **Không có fallback giữa các chain sau khi đã khớp.** Nếu API chain khớp `/api/orders/123` rồi trả 401/403, request **không được thử lại** bằng browser chain.
3. **Nếu không chain nào khớp, request có thể nằm ngoài bảo vệ của Spring Security** (trừ các thành phần khác). Vì vậy nên có một chain cuối cùng không đặt `securityMatcher`, áp dụng `denyAll` hoặc chính sách bao phủ được kiểm soát.

**`@Order` thấp hơn được xét trước.** Ví dụ `@Order(1)` ưu tiên hơn `@Order(10)`. Đặt fallback không giới hạn matcher ở đầu sẽ làm tất cả chain phía sau không bao giờ được chọn.

### Sơ đồ một request thực tế

~~~text
GET /api/orders/123
  |
  +-- statusChain.securityMatcher: NO
  |
  +-- apiChain.securityMatcher("/api/**"): YES
  |      |
  |      +-- BearerTokenAuthenticationFilter
  |      +-- JWT validation
  |      +-- scope authorization
  |      +-- controller/service hoặc lỗi 401/403
  |
  X-- browserChain KHÔNG được xét tiếp
  X-- fallbackChain KHÔNG được xét tiếp
~~~

**Chọn chain là quyết định ở tầng HTTP request.** Nó không tự kiểm tra issuer, signature hoặc nội dung `scope` của JWT; các bước đó thuộc authentication trong chain đã chọn.

## 3. Phân biệt securityMatcher và requestMatchers

Hai tên API gần giống nhưng đóng vai trò khác nhau.

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().denyAll());
~~~

**`securityMatcher("/api/**")`** quyết định **toàn bộ SecurityFilterChain có được áp dụng** cho request hay không.

**`requestMatchers(...)`** bên trong `authorizeHttpRequests` quyết định **quyền truy cập của request sau khi chain đó đã được chọn**.

| Khái niệm | Hỏi điều gì? | Khi không khớp |
| --- | --- | --- |
| `http.securityMatcher(...)` | “Request có đi vào chain này không?” | Spring Security thử chain kế tiếp |
| `auth.requestMatchers(...)` | “Trong chain này, rule nào áp dụng?” | Thử rule tiếp theo **trong cùng chain** |
| `auth.anyRequest()` | “Các request còn lại **đã được chain này chọn** được xử lý thế nào?” | Không có bước chuyển sang chain khác |
| `@Order` | “Chain nào được thử trước?” | Xác định ưu tiên của danh sách chain |

### Ví dụ lỗi thường gặp

~~~java
// Dễ sai khi tưởng requestMatchers dùng để lựa chọn chain.
@Bean
@Order(1)
SecurityFilterChain overlyBroad(HttpSecurity http) throws Exception {
    return http
        // Không có securityMatcher => chain mặc định áp dụng mọi request.
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").authenticated()
            .anyRequest().permitAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Chain này **có thể khớp mọi request** vì không đặt `securityMatcher`, khiến các chain browser/health `@Order` thấp ưu tiên hơn không bao giờ được chọn. `.anyRequest().permitAll()` vẫn có thể để Bearer filter xử lý token sai trước khi authorization.

Cách khắc phục là thiết kế **matcher của chain** rõ ràng và đặt **fallback cuối cùng**, không chỉ thêm `requestMatchers` vào một chain bao trùm.

### Chú ý kiểu matcher và path thực tế

Các matcher có thể dựa vào path, HTTP method, servlet path, dispatcher type hoặc lớp matcher chuyên dụng. Với nhiều servlet, context path, reverse proxy, rewrite hoặc Spring MVC path matching, cần kiểm tra **đường dẫn thực sự Spring Security nhìn thấy**. Không tự giả định URL ngoài gateway và servlet path bên trong là giống nhau.

Đặc biệt, đường dẫn `/api` không nhất thiết được bảo vệ theo đúng ý định chỉ vì đã cấu hình `/api/**`. Nếu API có route root `/api`, hãy kiểm tra matcher và thêm path tường minh khi cần.

## 4. Kiến trúc khuyến nghị cho một ứng dụng hỗn hợp

Một phân tách dễ hiểu:

~~~text
Order application (Servlet)
|
|-- statusChain @Order(1)
|     /status/live, /status/ready
|     GET public, không bearer, không OIDC login
|
|-- apiChain @Order(2)
|     /api/**
|     OAuth 2.0 Resource Server JWT
|     stateless, không redirect tới login
|     scope + business authorization
|
|-- browserChain @Order(3)
|     /app, /app/**, /assets/**
|     /login, /login/**, /oauth2/**, /logout
|     OAuth2 Login/OIDC + session, CSRF
|
|-- fallbackChain @Order(100)
      Mọi request còn lại
      denyAll (không mở endpoint ngoài ý muốn)
~~~

Ví dụ dùng **Spring Security Servlet (Spring Boot 3.x / Spring Security 6.x theo API thường gặp)**. Nếu dự án chạy **Spring WebFlux**, cần sử dụng `SecurityWebFilterChain`, `ServerHttpSecurity` và reactive components thay vì sao chép nguyên `HttpSecurity`.

Để tránh trùng code, ta định nghĩa một class `SecurityConfiguration` có bốn bean. Các đoạn cấu hình bên dưới là phần thuộc cùng class; hãy đưa imports và cấu hình client registration phù hợp vào project.

## 5. Chain riêng cho endpoint trạng thái

Health/liveness đôi khi phải trả lời khi chưa có OAuth2 token. Một chain riêng cho các đường dẫn **hẹp** giúp chúng không bị Bearer filter của API hoặc form/OIDC login xử lý.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(1)
SecurityFilterChain statusChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/status/live", "/status/ready")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                HttpMethod.GET, "/status/live", "/status/ready")
                .permitAll()
            .anyRequest().denyAll())
        .build();
}
~~~

Ví dụ này **chỉ công khai hai GET endpoint trạng thái**. Nó không bật `oauth2ResourceServer()` và không bật `oauth2Login()` trong status chain, nên một Bearer token sai được gửi tới `/status/live` **không bị chính Bearer filter của API chain xử lý**.

Các endpoint phải được ứng dụng thực sự ánh xạ đến controller/handler. Một chain cho phép request không tự tạo ra endpoint; nếu route không tồn tại, response có thể là 404.

### Đừng công khai toàn bộ Actuator

Một lỗi nguy hiểm là:

~~~java
// KHÔNG NÊN chỉ để mở health:
.securityMatcher("/actuator/**")
.authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
~~~

Nó có thể vô tình công khai metrics, environment, config properties, loggers, heapdump hoặc các actuator endpoints khác nếu được expose.

Nếu sử dụng Spring Boot Actuator, có thể dùng matcher chuyên dụng như `EndpointRequest` để nhắm **đúng health endpoint**, tùy version và management port. Endpoint health cũng cần kiểm soát mức chi tiết công bố; `show-details=always` trên public health có thể làm lộ cấu hình nội bộ.

**Lưu ý management port:** nếu Actuator được chuyển sang cổng/management context riêng, các chain ở application context có thể không kiểm soát endpoint như bạn nghĩ. Cần kiểm tra cấu hình security **thực sự áp dụng trên management context/port đó**.

### Liveness khác readiness

- **Liveness:** thường chỉ cho biết process còn sống, không nhất thiết cần kiểm tra mọi dependency.
- **Readiness:** cho biết instance có sẵn sàng nhận traffic; có thể phản ánh dependency.

Công khai thông tin tối thiểu cần thiết. Health endpoint không nên trả access token, client secret, connection URL nhạy cảm hoặc dữ liệu tenant.

## 6. Chain REST API: Resource Server JWT, stateless

REST API nhận Bearer access token, không đăng nhập qua browser redirect. Chain API nên giới hạn matcher `/api/**`, dùng OAuth2 Resource Server và kiểm tra scope rõ ràng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(2)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .cors(Customizer.withDefaults())
        .csrf(csrf -> csrf.disable())
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .requestCache(cache -> cache.disable())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                .hasAuthority("SCOPE_orders.delete")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

Các lựa chọn có chủ đích:

1. `securityMatcher("/api/**")` giới hạn filter JWT vào API routes.
2. `sessionCreationPolicy(STATELESS)` tránh dùng HTTP session để nhận diện API caller.
3. Tắt `requestCache` tránh lưu request API rồi redirect sau login.
4. `oauth2ResourceServer().jwt()` xác thực JWT Bearer access token.
5. `hasAuthority("SCOPE_orders.read")` tương ứng với scope `orders.read` được `JwtGrantedAuthoritiesConverter` mặc định ánh xạ trong cấu hình thông dụng.
6. `anyRequest().denyAll()` từ chối phương thức/route API không được liệt kê, thay vì cho mọi token đã xác thực dùng tất cả endpoint.

### JWT chưa hợp lệ thì không được tạo quyền

Payload:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

chỉ là dữ liệu mô tả. Resource Server phải xác minh **chữ ký, issuer, hạn token, audience và token type/profile phù hợp** trước khi dùng claims để ánh xạ authorities.

Một cấu hình application:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

`issuer-uri` thường giúp cấu hình decoder/JWKS và kiểm tra issuer. **Đừng giả định audience `orders-api` tự được kiểm tra chỉ nhờ issuer-uri ở mọi phiên bản/configuration.** API cần validator audience/profile được cấu hình theo hợp đồng Authorization Server.

**Không dùng OIDC ID token của browser làm API access token.** ID token phục vụ client xác định danh tính người dùng đăng nhập; JWT Resource Server phải chỉ chấp nhận access token được phát hành **dành cho Orders API**.

### Vì sao tắt CSRF ở API phải có điều kiện?

`csrf(csrf -> csrf.disable())` trong ví dụ giả định API chỉ được xác thực bằng **Bearer token do client chủ động đưa vào Authorization header**, không dùng cookie tự động đính kèm để xác thực API.

Nếu API chấp nhận **session cookie, Basic Auth hoặc credential browser tự gửi** ở một đường đi nào đó, kết luận “stateless nghĩa là không cần CSRF” có thể sai. Phải đánh giá rủi ro CSRF theo cơ chế credential **thực sự** được chấp nhận, không chỉ theo tên route.

Với API dùng OAuth2 Resource Server, token sai/thất bại authentication thường trả **401 Bearer challenge**, không phải redirect đến trang login OIDC. Token hợp lệ nhưng thiếu scope thường nhận **403**, theo entry point/denied handler và contract.

## 7. Chain trình duyệt: OAuth2 Login/OIDC và phiên đăng nhập

Đường dẫn browser cần một policy khác API: user có thể bắt đầu chưa đăng nhập, được redirect tới Authorization Server để **Authorization Code + OIDC login**, rồi quay lại ứng dụng qua callback.

Các đường dẫn mặc định thường gặp:

~~~text
/login                              -- trang login (mặc định/tùy chỉnh)
/oauth2/authorization/corporate     -- bắt đầu OAuth2 authorization
/login/oauth2/code/corporate        -- callback nhận authorization code
/app                                -- trang ứng dụng
/app/**                             -- các trang authenticated
/assets/**                          -- CSS/JS/images tĩnh
/logout                             -- logout của ứng dụng
~~~

Một browser chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(3)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher(
            "/app", "/app/**",
            "/assets/**",
            "/login", "/login/**",
            "/oauth2/**",
            "/logout")
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(
                "/assets/**",
                "/login",
                "/oauth2/authorization/**",
                "/login/oauth2/code/**")
                .permitAll()
            .anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults())
        .logout(Customizer.withDefaults())
        .build();
}
~~~

Điểm khác với API:

- Không bật `oauth2ResourceServer().jwt()` trong browser chain của ví dụ.
- `oauth2Login()` hỗ trợ redirect và xử lý Authorization Code/OIDC login.
- Session có thể cần thiết để giữ thông tin login/security context và trạng thái OAuth2 authorization request.
- **CSRF để mặc định được bật** cho browser chain; không copy `csrf.disable()` từ API.
- Một request browser chưa đăng nhập đến `/app/orders` thường nhận redirect tới login flow, không nhận Bearer token challenge.
- Static assets cần được cho phép thích hợp, nhưng không mở dữ liệu nhạy cảm chỉ vì nó có đuôi tệp tĩnh.

### Vì sao cần đưa callback vào browser chain?

OIDC Provider redirect browser về một đường dẫn như:

~~~http
GET /login/oauth2/code/corporate?code=...&state=... HTTP/1.1
Host: shop.example.com
~~~

Nếu `securityMatcher` chỉ khớp `/app/**` mà bỏ qua `/login/oauth2/code/**`, request callback sẽ bị fallback chain xử lý, **không đến được OAuth2 login filter** cần thiết để hoàn tất authorization code flow. Kết quả có thể là 403/404, vòng lặp login hoặc lỗi state.

Tương tự, route bắt đầu login `/oauth2/authorization/{registrationId}` phải nằm trong chain cài đặt OAuth2 authorization request redirect filter.

### OIDC client registration

Maven dependencies thường dùng:

~~~xml
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
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Và cấu hình đăng ký client:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: shop-web
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corporate:
            issuer-uri: https://auth.example.com/realms/shop
~~~

`openid` trong scope làm flow theo OIDC khi provider hỗ trợ. Ứng dụng cần cấu hình redirect URI hợp lệ tại Authorization Server và lưu `client-secret` bằng secret manager/environment, **không ghi secret thật trong source control**.

Thông thường OAuth2 login giữ **authorization request/state** và bảo vệ luồng redirect. Không “đơn giản hóa” bằng cách tắt state validation hoặc cho client tự chọn redirect URL bất kỳ. Với reverse proxy, cần cấu hình forwarded headers/base URL tin cậy để redirect URI không bị sai host/scheme.

### Browser principal khác JWT Resource Server principal

Sau OIDC login, Authentication của browser thường là `OAuth2AuthenticationToken` và principal có thể là **`OidcUser`**.

Trong JWT Resource Server, Authentication thường là `JwtAuthenticationToken` và principal là **`Jwt`**.

| Nội dung | Browser OAuth2 Login/OIDC | REST API JWT Resource Server |
| --- | --- | --- |
| Chứng thực ban đầu | Authorization Code/OIDC redirect | Bearer access token |
| Principal thông dụng | `OidcUser` | `Jwt` |
| Authentication thông dụng | `OAuth2AuthenticationToken` | `JwtAuthenticationToken` |
| Lưu trạng thái | Session/cookie khi cần | Stateless |
| Khi chưa đăng nhập | Redirect tới login | 401 Bearer challenge |
| Chống CSRF | Cần khi sử dụng browser cookie/session | Đánh giá theo cơ chế credential thực tế; Bearer-only có thể vô hiệu |
| Dữ liệu quyền | Authorities của OAuth2 login và mapping tùy chỉnh | `SCOPE_...` từ access token, theo converter |
| Mục đích ID token | Xác thực người dùng với OIDC client | **Không** thay access token để gọi API |

Không ép kiểu `Jwt` từ browser principal, và không coi `OidcUser` là Authentication có thể dùng làm access token cho API chỉ vì cả hai thuộc Spring Security.

## 8. Fallback chain: chặn endpoint chưa được phân loại

Chain cuối nên bao phủ mọi request còn lại:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(100)
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    return http
        // Không có securityMatcher: fallback cho mọi path còn lại.
        .authorizeHttpRequests(auth -> auth
            .anyRequest().denyAll())
        .build();
}
~~~

**Tại sao cần?** Khi có custom `SecurityFilterChain` bean, không nên giả định Spring Boot vẫn tự thêm một default chain bảo vệ phần còn lại. Một endpoint mới như `/internal/admin/export` có thể được controller tạo nhưng **không khớp các matcher API/browser/status**.

Nếu có fallback `denyAll`, request đó bị từ chối thay vì vô tình trở thành public. Nếu không có fallback, request có thể đi qua servlet filter của ứng dụng mà **không được Spring Security bảo vệ**.

### Fallback không nên đứng trước những chain khác

Nếu:

~~~java
@Order(1)
SecurityFilterChain fallbackChain(HttpSecurity http) {
    // Không securityMatcher -> match mọi request.
}
~~~

thì nó có thể **nuốt toàn bộ các request**, khiến các chain được đánh thứ tự lớn hơn không bao giờ chạy. Tốt nhất đặt fallback ở cuối với thứ tự được quản lý rõ ràng và có test regression.

### Fallback denyAll có thể ảnh hưởng lỗi 404

Một route chưa tồn tại, ví dụ `/unexpected`, có thể nhận **403/401 hoặc response denial** trước khi tới MVC, thay vì 404. Đây là đánh đổi có chủ đích. Nếu API yêu cầu 404 cho unknown route, hãy thiết kế error policy riêng mà **không làm lộ endpoint bảo vệ** hoặc bỏ ngỏ toàn bộ path chưa match.

## 9. Bảng dự đoán chain cho từng request

Với bốn chain ở trên:

| Request | Chain được chọn | Behavior thường gặp |
| --- | --- | --- |
| GET `/status/live` không token | Status | Vào status handler nếu tồn tại |
| GET `/status/live` có Bearer token sai | Status | Token không được API Bearer filter kiểm tra ở chain này |
| POST `/status/live` | Status | Bị từ chối vì chỉ GET được permit |
| GET `/api/orders/123` không token | API | 401 và Bearer challenge |
| GET `/api/orders/123` JWT sai chữ ký | API | 401/invalid token |
| GET `/api/orders/123` JWT có scope đọc | API | Vào controller, còn object authorization |
| POST `/api/orders` JWT thiếu scope ghi | API | Thường 403 |
| GET `/app/orders` không session | Browser | Redirect login |
| GET `/app/orders` có session OIDC hợp lệ | Browser | Có thể vào controller |
| GET `/oauth2/authorization/corporate` | Browser | Bắt đầu authorization redirect |
| GET `/login/oauth2/code/corporate` | Browser | OAuth2 Login xử lý callback |
| POST `/logout` với CSRF hợp lệ và session | Browser | Logout theo cấu hình |
| GET `/foo` | Fallback | Từ chối |
| POST `/hooks/payments` khi chưa có chain webhook | Fallback | Từ chối |

Các status chính xác còn phụ thuộc custom handlers, CSRF, controller mapping và security configuration. Bảng mô tả **mong muốn của kiến trúc ví dụ**, không phải cam kết HTTP cho mọi trường hợp.

**Không có cơ chế “chain status cho qua rồi chain API tiếp tục”.** Mỗi hàng có đúng một chain được chọn theo thứ tự.

## 10. Endpoint webhook nên dùng chain riêng, không chỉ permitAll

Webhook thường dùng **chữ ký HMAC** do provider phát hành thay vì JWT Bearer. Một POST:

~~~http
POST /hooks/payments HTTP/1.1
Host: shop.example.com
Content-Type: application/json
X-Webhook-Timestamp: 1763164800
X-Webhook-Signature: <provider-signature>

{"event":"payment.completed","orderId":"123"}
~~~

Nếu chỉ cấu hình:

~~~java
.requestMatchers("/hooks/**").permitAll()
~~~

mà controller tin mọi JSON body, attacker có thể giả mạo payment notification.

Một thiết kế tách biệt:

~~~text
Webhook chain /hooks/**
    |
    +-- Chỉ cho phương thức mà provider cho phép
    +-- Xác minh HMAC/mTLS trên request thật
    +-- Kiểm tra timestamp, nonce/replay và provider identity
    +-- Tạo Authentication/authorization context đáng tin
    +-- Controller xử lý event theo idempotency key
~~~

Sơ đồ code mang tính **khung tích hợp**, không phải verifier HMAC hoàn chỉnh:

~~~java
@Bean
@Order(1)
SecurityFilterChain webhookChain(
        HttpSecurity http,
        WebhookSignatureAuthenticationFilter signatureFilter)
        throws Exception {

    return http
        .securityMatcher("/hooks/payments/**")
        .csrf(csrf -> csrf.disable())
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.POST, "/hooks/payments/**")
                .authenticated()
            .anyRequest().denyAll())
        .addFilterBefore(
            signatureFilter, UsernamePasswordAuthenticationFilter.class)
        .build();
}
~~~

`WebhookSignatureAuthenticationFilter` là **lớp tùy chỉnh do ứng dụng tự viết**, không tồn tại mặc định trong Spring Security. Nó phải **kiểm tra chữ ký và chống replay trước khi tạo Authentication**; nếu verifier chưa được triển khai thì **không** được đưa khung code này vào production và giả định route đã được bảo vệ.

Để ví dụ áp dụng đúng, cần:

- Match chính xác webhook route thực (ví dụ `/hooks/payments` và `/hooks/payments/**` nếu cả hai tồn tại).
- Đọc **raw request body bytes** đúng theo scheme provider; không parse rồi serialize lại JSON trước khi HMAC nếu provider ký raw body.
- Dùng secret riêng của provider, so sánh MAC bằng **constant-time comparison**, kiểm tra timestamp và chống replay.
- Không thực thi side effect trước khi xác thực signature.
- Tránh đọc InputStream trước controller mà không có request wrapper phù hợp nếu handler cũng cần body.
- Bảo đảm filter **không bị đăng ký hai lần** ở servlet container và ở Spring Security chain khi là Spring bean/filter.
- Kiểm tra tenant/account mapping và idempotency cho các event lặp.
- Chỉ vô hiệu CSRF ở chain webhook **không dùng browser cookies**, không tắt CSRF cho browser chain.

Nếu chain webhook dùng `@Order(1)` như khung trên, phải sắp xếp lại thứ tự các bean hoặc dùng một dải thứ tự rõ ràng, nhưng vì matcher không chồng lấn với status/API/browser nên priority ít nhạy hơn. **Fallback vẫn phải cuối cùng**.

### Cảnh báo đăng ký Filter dưới dạng bean

Trong Spring Boot, một `Filter` vừa là Spring bean vừa được thêm bằng `http.addFilterBefore(...)` có thể bị container tự đăng ký **ngoài Spring Security**. Khi đó verifier có thể chạy hai lần hoặc chạy trên route ngoài ý muốn. Cần bảo đảm chỉ đăng ký theo cơ chế dự định (ví dụ điều chỉnh `FilterRegistrationBean` cho servlet registration nếu cần). Không coi `@Order` của servlet Filter và `@Order` của SecurityFilterChain là cùng một thứ.

## 11. API nội bộ: mTLS, client credentials và issuer riêng

Không phải mọi endpoint nội bộ đều nên dùng cùng JWT policy với API công khai. Ví dụ `/internal/jobs/**` có thể đòi:

- mTLS với certificate của service được tin cậy.
- OAuth 2.0 Client Credentials access token dành riêng cho internal API.
- Issuer/audience riêng, scope như `jobs.execute`.
- Network policy ở ingress/mesh **cùng với** application authorization.

Nếu dùng một chain riêng:

~~~text
internalChain.securityMatcher("/internal/**")
    |
    +-- Xác minh caller/service identity từ nguồn tin cậy
    +-- Kiểm tra audience/resource + scope
    +-- Authorization từng hành động
    +-- Deny mọi request không đáp ứng
~~~

**Đừng suy luận “request đến từ private subnet thì đã authenticated”.** IP address hoặc header mTLS do proxy ghi chỉ đáng tin khi proxy/ingress được cấu hình chống giả mạo, đường kết nối được kiểm soát và ứng dụng không chấp nhận client tự đặt header đó.

Với OAuth2 Client Credentials, principal có thể đại diện **machine client**, không phải người dùng sở hữu order. Business policy phải phân biệt service identity và human identity; không tự đặt `ownerUserId = client_id`.

### Khi nào một chain là chưa đủ?

Một chain có thể cần nhiều cách xác thực cho **cùng URL** (ví dụ hỗ trợ JWT issuer A/B, hoặc JWT và opaque token theo hợp đồng). Chỉ tạo hai `SecurityFilterChain` với **cùng `securityMatcher("/api/**")`** sẽ không khiến Spring Security “thử JWT rồi nếu lỗi thì thử opaque”:

~~~text
apiJwtChain: securityMatcher("/api/**")    @Order(1)
apiOpaqueChain: securityMatcher("/api/**") @Order(2)

Mọi request /api/** khớp chain đầu.
Chain thứ hai không phải fallback authentication.
~~~

Khi cần chọn **AuthenticationManager theo token/issuer** trong cùng route, hãy dùng cấu trúc authentication manager resolver hoặc cơ chế xác thực được thiết kế rõ ràng, kiểm tra issuer theo allowlist và không tin claims chưa được xác minh để cấp quyền.

**Chain phân vùng theo HTTP request matcher**, còn **authentication strategy** phải xác thực token. Đó là hai quyết định khác nhau.

## 12. CORS: tách preflight khỏi authentication

Giả sử browser frontend ở `https://app.example.com` gọi REST API ở `https://api.example.com` bằng:

~~~http
GET /api/orders/123 HTTP/1.1
Origin: https://app.example.com
Authorization: Bearer <access-token>
~~~

Trình duyệt có thể gửi **CORS preflight**:

~~~http
OPTIONS /api/orders/123 HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thường **không chứa Bearer token**. Nếu chain API bắt buộc mọi request phải có token **trước khi CORS xử lý**, trình duyệt có thể không gửi request GET thật.

Ví dụ `CorsConfigurationSource`:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "DELETE"));
    cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
    cors.setMaxAge(1800L);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cors);
    return source;
}
~~~

API chain đã bật `.cors(Customizer.withDefaults())` ở mục 6. CORS chỉ điều khiển **trình duyệt có được đọc/gửi cross-origin request theo policy**; nó **không phải authentication**. Non-browser client vẫn có thể gửi request trực tiếp. Không dùng `Origin` header làm bằng chứng danh tính hoặc tenant.

Nếu dùng credential cookies giữa các origin, cần cấu hình `allowCredentials` và danh sách origins cụ thể, xử lý SameSite/CSRF phù hợp; tránh wildcard origin với credentials.

### permitAll(OPTIONS) không tự thay thế CORS

Chỉ thêm:

~~~java
.requestMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
~~~

không tự tạo các response headers `Access-Control-Allow-Origin`, `Access-Control-Allow-Methods` hoặc `Access-Control-Allow-Headers`. Preflight phải được **CORS processor** xử lý theo chính sách.

## 13. CSRF, cookie và session: không sao chép chính sách giữa chain

Điểm khác biệt quan trọng giữa API và browser:

| Mục | API Bearer-only | Browser OIDC login + session |
| --- | --- | --- |
| Credential | Authorization: Bearer access token | Cookie session sau login |
| Yêu cầu stateful session | Thường không | Thường có |
| SessionCreationPolicy | `STATELESS` | `IF_REQUIRED` hoặc policy browser tương đương |
| CSRF | Có thể disable khi chỉ nhận Bearer token không tự gửi | **Giữ bảo vệ CSRF** cho form/state-changing requests |
| Request cache/redirect login | Thường disable | Có thể cần để trở lại URL ban đầu sau login |
| Khi thiếu credentials | Bearer 401 | Thường redirect login |
| Logout | Token revocation do OAuth2/AS policy, không chỉ xóa cookie | Xóa session/cookie và có thể OIDC RP-initiated logout |

**SessionCreationPolicy.STATELESS không tự biến một ứng dụng có cookie credentials thành không có rủi ro CSRF.** Xét cơ chế xác thực được chấp nhận **trong chain đó** và cách browser gửi credentials.

### Browser logout không đồng nghĩa thu hồi access token

Khi user logout khỏi giao diện:

- HTTP session local có thể bị invalidate.
- OIDC Provider session có thể vẫn còn nếu ứng dụng không hỗ trợ hoặc không gọi logout của provider.
- Một access token đã được cấp cho API có thể vẫn còn hiệu lực đến `exp` hoặc tới khi bị revoke theo chính sách của Authorization Server.

Đừng nhầm **local session logout**, **OIDC logout** và **OAuth2 token revocation** là cùng một hành động.

### Browser cookie không tự xác thực ở API JWT chain

Trong ví dụ, browser dùng session để đăng nhập `/app/**`, còn `/api/**` dùng Bearer JWT stateless:

~~~text
GET /app/orders
  Cookie: JSESSIONID=...
  -> browserChain -> OIDC user / session

GET /api/orders/123
  Cookie: JSESSIONID=... nhưng không có Bearer
  -> apiChain -> không có JWT Authentication
  -> thường 401 Bearer challenge
~~~

**Đây là hành vi tách biệt có chủ đích.** Nếu kiến trúc muốn browser dùng session để gọi API, cần một thiết kế rõ ràng khác, ví dụ:

- **BFF (Backend for Frontend):** browser gọi session-backed endpoints trong browser chain; server gọi downstream API bằng **access token phù hợp**.
- Một chain riêng cho UI backend endpoints có session authentication và CSRF.
- Một OAuth2 client dùng authorized client/access token để gọi downstream API theo user/client delegation.

**Không gửi OIDC ID token làm access token cho Resource Server** chỉ để tránh xử lý phiên đăng nhập; audience và token purpose khác nhau.

## 14. OAuth2 Client và Resource Server có thể cùng trong một ứng dụng

Một ứng dụng có thể vừa:

1. Là **OIDC Client** để đăng nhập user qua browser.
2. Là **Resource Server** để xác thực Bearer access token đến REST API.
3. Là **OAuth2 Client** để gọi một API downstream bằng access token được cấp.

Nhưng trách nhiệm khác nhau:

~~~text
Browser                    Order application
    |                           |
    |  OIDC login               | OAuth2 Client
    +-------------------------->|--- Authorization Code ---> AS
    |                           |
    | session cookie            |
    +-------------------------->| browserChain
                                |
Mobile / service client         |
    | Bearer access token       |
    +-------------------------->| apiChain / Resource Server
                                |
                                +-- Bearer token for downstream API
                                    (đúng audience/scope/delegation)
~~~

`spring-boot-starter-oauth2-client` và `spring-boot-starter-oauth2-resource-server` có thể cùng tồn tại, nhưng **chain nào bật cơ chế nào** phải được chỉ định tường minh.

Một số OIDC providers cấp cả ID token và access token. Spring Security OAuth2 Login dùng ID token để xác lập identity cho client; access token có thể dùng gọi API **nếu** nó được cấp đúng resource/audience và phù hợp hợp đồng. Không phải access token của mọi OIDC login đều có thể dùng gọi Orders API.

## 15. Phản hồi lỗi cần khác nhau giữa API và trình duyệt

Khi request thiếu xác thực:

~~~text
GET /api/orders/123
  -> apiChain
  -> JWT Resource Server yêu cầu Bearer
  -> 401 + WWW-Authenticate: Bearer

GET /app/orders
  -> browserChain
  -> OAuth2 login redirect
  -> 302 Location: /login hoặc authorization endpoint
~~~

Một HTTP response ví dụ cho API:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

JWT không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

JWT hợp lệ nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Đây là các dạng response thường gặp theo **RFC 6750**, không phải một định dạng header byte-for-byte bắt buộc ở mọi handler/phiên bản. Một request không có token có thể nhận Bearer challenge **không kèm mã lỗi**; handler tùy chỉnh có thể thêm `realm`, `error_description`, response body.

### Không để API trả redirect HTML khi client cần JSON

Nếu mobile client nhận 302 tới trang OIDC login, nó có thể theo redirect và nhận HTML, trong khi ứng dụng đang chờ JSON. Điều này thường là dấu hiệu **nhầm chain hoặc cấu hình chung authentication entry point**.

Ngược lại, browser trực tiếp mở `/app/orders` mà nhận 401 Bearer thì trải nghiệm OIDC login sẽ không hoạt động đúng nếu UI dự kiến redirect.

**Endpoint path, chain matcher, entry point và mechanism trong chain phải tạo thành một hợp đồng nhất quán.**

## 16. Nhiều chain không tự tạo ranh giới dữ liệu/tenant

API JWT hợp lệ có `SCOPE_orders.read` không nghĩa được đọc order của mọi user. OIDC browser login thành công cũng không nghĩa user được sửa mọi tài nguyên.

Chính sách đối tượng vẫn cần áp dụng:

~~~text
Authentication:
  Ai gọi? JWT/OIDC session/client identity đã xác minh?
          |
          v
Function authorization:
  Được gọi chức năng đọc/sửa/export không?
          |
          v
Business authorization:
  Order thuộc tenant nào?
  User/client có active membership phù hợp?
  Có owner/manager/share/assignment đúng quyền và còn hiệu lực?
          |
          v
Repository query được scope theo tenant và quan hệ
          |
          v
Chỉ trả dữ liệu được phép
~~~

`@EnableMethodSecurity` và `@PreAuthorize` có thể bổ sung bảo vệ cho service được cả browser controller và API controller gọi. Tuy nhiên:

- Quyền từ JWT (`SCOPE_...`) khác với authorities của `OidcUser`; rule chung phải hiểu cả hai hoặc dùng abstraction policy thống nhất.
- Method security thường dùng proxy; **self-invocation** có thể bỏ qua interceptor.
- Business policy phải xác minh relationship của tài nguyên, không chỉ Authentication có `isAuthenticated()`.
- Client Credentials token đại diện machine client; không giả định `sub` luôn là human owner.

**Chain phân tách authentication mechanism; service/repository phân tách quyền dữ liệu.** Không được dùng multi-chain như một lý do bỏ object-level authorization.

## 17. Trường hợp public endpoint có Bearer token sai

Đây là điểm dễ gây hiểu nhầm nhất giữa `securityMatcher` và `permitAll`.

### Public route nằm trong cùng API chain

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public-info").permitAll()
        .anyRequest().authenticated())
    .oauth2ResourceServer(oauth2 ->
        oauth2.jwt(Customizer.withDefaults()));
~~~

Hành vi có thể là:

| Request | Kết quả thường gặp |
| --- | --- |
| `GET /api/public-info` không token | Được `permitAll` |
| `GET /api/public-info` với JWT hợp lệ | Có thể được `permitAll` |
| `GET /api/public-info` với JWT sai/hết hạn | **Có thể trả 401 trước khi xét `permitAll`** |

Lý do: Bearer filter được cài trong **toàn bộ API chain**, không chỉ những requestMatchers yêu cầu authentication.

### Public route có chain riêng không bật Bearer filter

`/status/live` ở ví dụ thuộc chain status, không cài Bearer filter. Vì thế JWT sai trong header không bị **filter JWT của API chain** phân tích khi request match status chain.

Nếu yêu cầu sản phẩm là “public endpoint phải thành công ngay cả khi client gửi token hỏng”, sử dụng **securityMatcher/chain riêng** có thể phù hợp hơn việc chỉ thêm `permitAll`.

Ngược lại, không nên dùng cách này để bỏ qua token invalid trên route thực sự cần xác thực.

## 18. Dùng MockMvc để xác nhận chain nào thực sự chạy

Multi-chain là cấu hình **filter-level**, nên test phải đi qua `FilterChainProxy` và đúng application context. Test chỉ gọi controller method không kiểm tra việc chọn chain.

Với Spring Boot, có thể dùng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class MultipleSecurityChainsTest {
    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder jwtDecoder;
}
~~~

Trong những dòng Spring Test mới hơn (ví dụ Spring Framework 6.2+), `@MockitoBean` thay `JwtDecoder` để tạo các nhánh JWT chủ động. Ở Spring Boot cũ hơn, có thể dùng `@MockBean` theo version. **Không dùng annotation chưa có trong dependency đang chạy.**

### Ví dụ test API và status

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class MultipleSecurityChainsTest {

    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder jwtDecoder;

    @Test
    void publicStatusDoesNotInvokeJwtDecoder() throws Exception {
        // Giả sử đã có handler GET /status/live trả HTTP 200.
        mvc.perform(get("/status/live")
                .header(HttpHeaders.AUTHORIZATION, "Bearer broken-token"))
            .andExpect(status().isOk());

        verifyNoInteractions(jwtDecoder);
    }

    @Test
    void apiWithoutBearerGets401() throws Exception {
        mvc.perform(get("/api/orders/123"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE, startsWith("Bearer")));
    }

    @Test
    void apiWithInvalidJwtGets401() throws Exception {
        when(jwtDecoder.decode("broken-token"))
            .thenThrow(new BadJwtException("Bad JWT"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "Bearer broken-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("invalid_token")));
    }

    @Test
    void jwtWithoutReadScopeGets403() throws Exception {
        when(jwtDecoder.decode("token-without-scope"))
            .thenReturn(fakeJwt("token-without-scope", "profile.read"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "Bearer token-without-scope"))
            .andExpect(status().isForbidden());
    }

    private static Jwt fakeJwt(String token, String scope) {
        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(issued)
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .claim("aud", List.of("orders-api"))
            .claim("scope", scope)
            .build();
    }
}
~~~

Test này xác nhận **HTTP request → filter selection → JWT provider/authorization → response** trong context đã nạp các chain. Nó **không kiểm tra chữ ký thật**, vì `JwtDecoder` bị mock. Helper `fakeJwt(...)` cũng không tạo JWS hợp lệ; cần test riêng với `NimbusJwtDecoder`, khóa/JWKS và validators thật để xác minh signature, issuer, audience, thời hạn.

### Test browser chưa đăng nhập

Với browser chain mặc định và một OIDC client registration test hợp lệ:

~~~java
mvc.perform(get("/app/orders"))
    .andExpect(status().is3xxRedirection())
    .andExpect(header().string(
        HttpHeaders.LOCATION, containsString("/login")));
~~~

Kỳ vọng `/login` phù hợp khi ứng dụng dùng login page mặc định. Với custom entry point hoặc redirect thẳng tới authorization endpoint, kiểm tra **đích redirect đã cấu hình**, không áp cứng `/login`.

### Test callback OIDC không bị fallback chặn

Không nên tự giả định `GET /login/oauth2/code/corporate?code=test` sẽ thành công: callback hợp lệ cần `state`, authorization request đã lưu, token endpoint và các điều kiện xác thực OIDC. Có thể kiểm tra matcher/chain bằng test cấu hình riêng, rồi dùng **OIDC test provider/stub** cho flow authorization code hoàn chỉnh.

Test chỉ assert callback trả 302 thay vì 403 không đủ chứng minh an toàn của OIDC login. Cần kiểm tra state, nonce, issuer, ID token validation và redirect URI đúng.

## 19. Ma trận kiểm thử nhiều chain

| Tình huống | Kỳ vọng cần xác nhận |
| --- | --- |
| GET status không token | Không cần login/Bearer, vào handler |
| GET status có Bearer hỏng | Không bị API Bearer filter kiểm tra |
| POST vào status chỉ dành cho GET | Bị từ chối |
| GET API không token | 401 Bearer challenge, không redirect login |
| GET API JWT không hợp lệ | 401 `invalid_token` nếu handler chuẩn |
| GET API JWT hợp lệ thiếu scope | 403 |
| GET API JWT đủ scope | Vào controller và tiếp tục object authorization |
| GET browser page không session | Redirect login/OIDC |
| GET browser page có session OIDC hợp lệ | Được phép theo policy browser |
| POST browser không có CSRF token | Bị chặn khi CSRF được bật và có áp dụng |
| GET OAuth2 authorization start | Đi qua browser chain, bắt đầu redirect |
| OIDC callback với state/nonce hợp lệ | Đi qua OAuth2 login filter và hoàn tất flow test |
| Browser session cookie gửi tới API không Bearer | Không tự nhận là JWT authentication |
| CORS preflight API | Được xử lý theo CORS policy, không buộc Bearer token |
| POST webhook không có chữ ký | Phải bị từ chối bởi webhook verification |
| GET route không thuộc mọi matcher cụ thể | Fallback denyAll |
| API route mới chưa có rule scope | `apiChain.anyRequest().denyAll()` từ chối |
| Hai chain có matcher chồng lấn | Chain có thứ tự trước thắng, không chạy chain thứ hai |
| Request có path sau reverse proxy rewrite | Chain chọn theo path thực sự tại Servlet |

Khi test, kiểm tra **HTTP status, `Location` khi redirect, `WWW-Authenticate` cho Bearer**, và side effect nghiệp vụ không xảy ra khi request bị từ chối. `@WithMockUser` hoặc `jwt()` trong Spring Security Test có thể tạo Authentication giả làm thay đổi kết quả; không dùng chúng trong test “không token”.

### Vì sao không dùng standaloneSetup để chứng minh multiple chains?

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new OrdersController())
    .build();
~~~

Cách này hợp lý để test controller, nhưng **không tự nạp các SecurityFilterChain thực**. Dùng `@SpringBootTest @AutoConfigureMockMvc` hoặc `webAppContextSetup(context).apply(springSecurity())` khi mục tiêu là filter selection và authentication response.

## 20. Chẩn đoán khi request đi nhầm chain

| Triệu chứng | Nguyên nhân có thể |
| --- | --- |
| `GET /app/orders` trả 401 Bearer thay vì 302 | API chain match quá rộng, OAuth2 Login không được chọn hoặc entry point sai |
| `GET /api/orders` trả redirect HTML | Browser/form login chain match trước API chain hoặc cấu hình chung entry point |
| `/login/oauth2/code/corporate` trả 403 | Browser chain không chứa callback, fallback thắng hoặc CSRF/filter policy sai |
| `/oauth2/authorization/corporate` không redirect | Không đi vào chain có OAuth2 authorization filter hoặc registration sai |
| Public status có token sai trả 401 | Status route nằm trong chain có Bearer filter, thay vì chain public riêng |
| API route mới bị truy cập không cần token | Không chain nào match; thiếu fallback hoặc có chain quá rộng permitAll |
| POST browser luôn 403 | CSRF token thiếu/sai hoặc authorization khác, không mặc định là thiếu OAuth scope |
| CORS preflight bị 401 | CORS xử lý sai thứ tự hoặc chain yêu cầu Bearer trước khi cho preflight |
| Logout thành công nhưng access token vẫn gọi API được | Logout session không đồng nghĩa revoke access token |
| Cookie browser không đủ cho `/api/**` | API chain stateless chỉ nhận JWT Bearer |
| Chỉ một chain hoạt động dù đã khai báo nhiều bean | `@Order`/`securityMatcher` sai; chain không giới hạn matcher ở trước |

Để quan sát chain, có thể bật debug logger **có kiểm soát**:

~~~yaml
logging:
  level:
    org.springframework.security.web.FilterChainProxy: DEBUG
~~~

Tùy phiên bản, log có thể cho biết chain/filter đang bảo vệ request. **Không bật TRACE tràn lan ở production** nếu log có nguy cơ chứa header Bearer, session ID, thông tin nhạy cảm hoặc dữ liệu cá nhân. Dùng request ID và path đã chuẩn hóa để điều tra; không log raw access token.

### Phân biệt ba vấn đề khác nhau

~~~text
Request chưa vào đúng chain?
    -> kiểm tra securityMatcher, @Order, path thực tế

Vào đúng chain nhưng xác thực sai?
    -> kiểm tra Bearer/OIDC/Webhook mechanism, issuer, keys, callbacks

Xác thực đúng nhưng quyền sai?
    -> kiểm tra scope/authorities, method security, tenant/owner policy
~~~

Đừng sửa lỗi **chain selection** bằng cách tắt kiểm tra JWT; cũng đừng sửa lỗi **missing scope** bằng cách mở `permitAll` cho toàn API.

## 21. Những hiểu nhầm thường gặp

**“Khai báo nhiều SecurityFilterChain thì request đi qua tất cả.”**  
Không. `FilterChainProxy` chọn chain đầu tiên khớp. Không có cơ chế chồng nhiều security chains theo thứ tự mặc định.

**“requestMatchers('/api/**') đủ để API chain chỉ xử lý API.”**  
Không. `requestMatchers` trong `authorizeHttpRequests` chỉ áp dụng **sau khi chain được chọn**. Cần `http.securityMatcher(...)` để giới hạn chain.

**“Một chain denyAll ở đầu là an toàn vì mọi request đều bị chặn.”**  
Nó có thể chặn cả login callback/health và làm các chain khác không bao giờ chạy. Fallback phải đứng **cuối**.

**“Có permitAll('/status/live') là không bao giờ chạy JWT decoder.”**  
Không nếu status nằm trong chain có Bearer filter và client gửi token sai. Chain riêng không bật Bearer mới tách rõ behavior.

**“API stateless vẫn có thể dùng browser session cookie một cách mặc định.”**  
Không. API Resource Server chain trong ví dụ chỉ xác thực Bearer; session browser thuộc chain khác. Nếu muốn BFF/session API, phải thiết kế riêng.

**“OIDC Login nghĩa là browser có access token dùng được cho mọi API.”**  
Không. ID token không phải access token; access token phải có audience, scope và mục đích đúng.

**“Tắt CSRF cho API thì nên tắt cho browser.”**  
Không. Browser session/cookie cần CSRF theo cơ chế tự động gửi credential; các chain có mô hình khác nhau.

**“Webhook không có token thì permitAll là đúng.”**  
Không. Webhook phải được xác thực bằng chữ ký/mTLS hoặc cơ chế đã thỏa thuận; permitAll không tự kiểm tra HMAC.

**“Một issuer khác có JWT cùng sub thì đó là cùng người.”**  
Không. Danh tính JWT phải gắn với issuer tin cậy; dùng `(iss, sub)` và mapping nội bộ khi cần.

**“Mỗi issuer một chain cùng matcher /api/** là Spring tự fallback.”**  
Không. Chain đầu tiên sẽ được chọn; dùng resolver/manager phù hợp nếu cùng path hỗ trợ nhiều nguồn.

**“Một token có SCOPE_orders.read thì đủ để đọc order bất kỳ.”**  
Không. Owner/tenant/share là object-level authorization riêng.

**“Không có securityMatcher thì Spring tự hiểu chain chỉ dành cho rule đã khai báo.”**  
Không. Chain không giới hạn matcher thường **khớp mọi request**, làm thay đổi thứ tự và phạm vi bảo vệ.

## 22. Quy trình thiết kế nhiều chain an toàn

1. **Lập bản đồ route:** API, browser, OIDC endpoints, health, webhook, internal và fallback; kiểm tra cả callback/logout/static assets.
2. **Chọn authentication mechanism theo caller:** Bearer JWT/opaque cho API, OAuth2 Login cho browser, HMAC/mTLS cho webhook hoặc service theo hợp đồng.
3. **Đặt securityMatcher hẹp và đầy đủ:** đừng quên root path, context/servlet path, path rewrite và OIDC callbacks.
4. **Đặt @Order có chủ đích:** các chain đặc biệt trước, fallback không giới hạn matcher ở cuối; giải quyết mọi trường hợp overlap.
5. **Định nghĩa per-chain policy:** API stateless/no login redirect, browser session/CSRF, health tối thiểu, webhook signature verification.
6. **Áp dụng authorization rule:** scope/role cho chức năng và object-level policy trong service/repository.
7. **Chặn route chưa khai báo:** `anyRequest().denyAll()` ở API chain khi phù hợp, cùng fallback chain cuối.
8. **Giữ ranh giới token:** OIDC ID token dùng đăng nhập client, OAuth2 access token dùng cho Resource Server theo audience/scope.
9. **Cấu hình CORS và CSRF đúng:** preflight không mang Bearer, browser session không bị tắt CSRF vô tình.
10. **Test từng chain qua FilterChainProxy:** không token, token sai, scope thiếu, login redirect, callback, logout, public, webhook và unknown route.
11. **Kiểm tra vận hành:** log chain selection an toàn, metrics 401/403/302, redirect loops, issuer outage và lỗi config.
12. **Kiểm tra trust boundaries:** gateway/forwarded headers, mTLS, nhiều issuer và principal mapping; không tin header/client-controlled identity.

**Điểm cần nhớ:** Nhiều `SecurityFilterChain` cho phép một ứng dụng Spring Security phục vụ **REST API Bearer**, **trình duyệt OIDC Login** và **các endpoint đặc biệt** với chính sách khác nhau. Nhưng Spring Security **chọn chain khớp đầu tiên, không chạy chồng mọi chain**. Thiết kế đúng phải **phân biệt `securityMatcher` với `requestMatchers`, sắp thứ tự `@Order`, bao phủ OIDC callbacks, giữ API stateless và browser CSRF/session, xác thực webhook riêng, có fallback deny-all và kiểm thử HTTP qua filter chain thực**.
