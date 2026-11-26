# Phạm vi áp dụng chính sách trên từng security chain

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Phạm vi:** Thiết kế, triển khai và kiểm thử phạm vi bảo vệ HTTP/trình duyệt của Spring Security: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session, xác thực và phân quyền. Bài học bao quát **Servlet/Spring MVC** lẫn **Reactive/WebFlux** với nhiều security chain.  
> **Định hướng phiên bản:** Lambda DSL ở Spring Security 6.5/7.x; luôn kiểm tra phiên bản thực tế, cách matcher diễn giải path và các API theo dòng Spring Boot đã resolve.

## 1. Vì sao phải hiểu phạm vi của từng chain?

Một dịch vụ có API cho SPA/mobile và trang quản trị chạy trong browser:

- `/api/**` sử dụng OAuth2 Resource Server/Bearer JWT; không dựa vào cookie session.
- `/admin/**` sử dụng form login, cookie/session và CSRF token.
- `/public/**` công khai nhưng vẫn cần security headers.
- `/login`, `/logout` và `/error` phục vụ luồng web.

Nếu lập trình viên chỉ tạo một chain `securityMatcher("/api/**")` rồi đặt `anyRequest().authenticated()`, điều đó **không có nghĩa** toàn ứng dụng cần đăng nhập. `/admin/**` nằm ngoài chain ấy; nếu không có chain khác phù hợp, Spring Security không bảo vệ request đó.

Ngược lại, một API chain có `csrf.disable()` nhưng matcher quá rộng có thể “nuốt” request browser trước khi browser chain được xét. Lúc ấy không chỉ CSRF mà cả CORS, CSP, HSTS, authentication mechanism và session behavior cũng bị áp nhầm.

**Nguyên tắc:** Security chain xác định tập filter/web-filter được chạy trên request, không chỉ một nhóm URL authorization. Spring Security chọn **chain phù hợp đầu tiên**, không cộng gộp các chain lại.

### Kết quả học tập

1. Phân biệt rõ chain matcher và rule matcher.
2. Dự đoán chain qua `@Order` và xử lý ranh giới của `/api/**`.
3. Cấu hình riêng CSRF/CORS/CSP/HSTS/session trên từng chain theo threat model.
4. Tạo fallback chain và bảo vệ login/logout, public assets, endpoints quản trị.
5. Viết cấu hình Servlet và Reactive đúng interface.
6. Kiểm thử đường vào đúng chain, request bị từ chối và hành vi bảo vệ ở HTTPS/proxy.

## 2. Quy trình chọn chain và chọn quyền

```text
HTTP request /api/admin/report
        |
        v
Container / ingress / URL normalization
        |
        v
FilterChainProxy (Servlet) hoặc WebFilterChainProxy (Reactive)
        |
        +-- @Order(1): Chain API securityMatcher("/api/**") ?
        |      Có -> chỉ chạy filter của API chain
        |             -> CORS API, CSRF API, Bearer JWT, headers API
        |             -> authorize /api/admin/** -> SCOPE_admin
        |
        +-- Nếu không match:
        +-- @Order(2): Browser chain (match mọi URL còn lại)
               -> CSRF browser, form login, session, headers browser
               -> authorize /admin/** -> ROLE_ADMIN
               -> public URL -> permitAll
               -> URL khác -> authenticated

Nếu không chain nào match: request không được Spring Security
bảo vệ bằng những filters của các chain đó.
```

**Hai lần khớp khác nhau:**

| Cấp lựa chọn | Servlet | Reactive | Điều được quyết định |
| --- | --- | --- | --- |
| **Chọn chain** | `HttpSecurity.securityMatcher(...)` | `ServerHttpSecurity.securityMatcher(ServerWebExchangeMatcher)` | Toàn bộ cơ chế security của chain có tham gia không |
| **Chọn rule quyền trong chain** | `authorizeHttpRequests(a -> a.requestMatchers(...))` | `authorizeExchange(a -> a.pathMatchers(...))` | Cấp/từ chối quyền truy cập |
| **Rule còn lại** | `anyRequest()` | `anyExchange()` | Chỉ áp cho request đã vào chain |
| **Thứ tự chain** | `@Order` | `@Order` | Chain được xét trước |
| **Thứ tự rule** | Theo thứ tự khai báo | Theo thứ tự khai báo | Rule phù hợp đầu tiên quyết định |

Ví dụ Servlet:

```java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/public/**").permitAll()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
```

`anyRequest().authenticated()` trong ví dụ chỉ áp dụng các request **đã match `/api/**`**. Nó không bảo vệ `/admin/report` ở ngoài `/api/**`.

### Thế nào là “first match wins”?

Nếu Chain A có `@Order(1)` và `securityMatcher("/**")`, nó nhận tất cả request trước Chain B `@Order(2)` dù B có matcher `/api/**` cụ thể hơn. Spring Security **không tự chọn chain có pattern cụ thể nhất**. Phải đặt chain hẹp trước fallback chain rộng.

Thứ tự rule trong `authorizeHttpRequests` cũng có nghĩa: `requestMatchers("/**").permitAll()` đặt trước `requestMatchers("/admin/**").hasRole("ADMIN")` làm rule admin không còn hiệu lực theo ý định.

## 3. Nhận diện phạm vi thật của từng lớp phòng vệ

| Bảo vệ | Thường được cấu hình ở đâu? | Phạm vi thực sự |
| --- | --- | --- |
| Authorization HTTP | `authorizeHttpRequests`/`authorizeExchange` | Các rule trong **chain đã chọn** |
| Form login, HTTP Basic, Resource Server | `formLogin`, `httpBasic`, `oauth2ResourceServer` | Authentication filters trong chain |
| CSRF | `csrf(...)` và CSRF request matcher | Chain được chọn, rồi matcher method/exception của CSRF |
| CORS | `cors(...)` cùng `CorsConfigurationSource` | Chain được chọn và URL/origin/method của CORS source |
| Security headers | `headers(...)` | Response đi qua chain có header writer |
| CSP | `headers(...contentSecurityPolicy...)` | Response của chain được cấu hình; không phải mặc định toàn ứng dụng |
| HSTS | Header writer hoặc reverse proxy | Header xuất hiện ở response HTTPS; browser áp chính sách theo **host** |
| Session/security context | `sessionManagement`, context repository | Cấu hình chain + session infrastructure của container/web stack |
| Login/logout URLs | Các filter của `formLogin`/`logout` | Chỉ hoạt động nếu request URL vào chain cung cấp endpoint |
| Strict HTTP firewall | `FilterChainProxy`/`WebFilterChainProxy` | Thường ở mức pipeline bảo mật trước rule, không phải URL authorization |
| Servlet `web.ignoring()` | `WebSecurityCustomizer` | Request bỏ qua Spring Security filters |
| Method security | `@EnableMethodSecurity` và method annotations | Quyết định khi gọi method, không thay CSRF/headers/chain |
| CDN/ingress/TLS | Hạ tầng triển khai | Ngoài Spring Security filter chain |

Không nên gọi mọi cơ chế “global”. Một request chỉ vào API chain sẽ **không tự nhận CSP của browser chain**. Ngược lại, HTTP firewall hay ingress không trở thành per-chain chỉ vì nó bảo vệ URL.

### `permitAll()` không phải `web.ignoring()`

`permitAll()` bỏ qua yêu cầu authorization nhưng request vẫn đi qua Spring Security chain và có thể được xử lý bởi CSRF, CORS và header writers tương ứng. `web.ignoring()` của Servlet bỏ qua cả Security filter chain; nếu Spring Security vốn ghi `X-Content-Type-Options`, CSP hoặc HSTS cho asset, các header đó có thể không còn. Với public assets, ưu tiên `permitAll()` khi cần bảo vệ ở mức headers.

## 4. Phân tích yêu cầu: API Bearer và browser cookie

Trước khi tách chain, viết một bảng hợp đồng bảo mật:

| Nhóm endpoint | Auth | Quyền | CSRF | CORS | Session/headers |
| --- | --- | --- | --- | --- | --- |
| GET `/api/public/**` | Không bắt buộc | `permitAll` chỉ cho GET | Theo API threat model | SPA origin | API response policy |
| `/api/admin/**` | Bearer JWT | `SCOPE_admin` | Không yêu cầu nếu **Bearer-only thật sự** | SPA origin | Stateless |
| `/api/**` còn lại | Bearer JWT | Authenticated | Như trên | SPA origin | Stateless |
| `/public/**` | Có thể ẩn danh | `permitAll` | POST vẫn có CSRF nếu cookie/session | Browser origin | Browser CSP và headers |
| `/admin/**` | Form login | `ROLE_ADMIN` | Bật | Browser origin | Cookie/session |
| `/login` và `/logout` | Form login/session | Theo flow | Bật cho các POST phù hợp | Browser origin | Login/logout trong browser chain |
| URL còn lại | Browser hoặc client phù hợp | Authenticated/deny rõ ràng | Theo fallback | Theo fallback | Không lọt khỏi Security |

**Điều kiện:** Việc tắt CSRF trong API chain ở bài này chỉ hợp lý khi API **không dựa vào credential tự động gắn bởi trình duyệt** (session cookie hoặc HTTP Basic trình duyệt tự gửi). Không suy từ chữ REST hoặc JWT rằng toàn bộ ứng dụng đều miễn CSRF. Nếu API vẫn chấp nhận cookie, giữ CSRF hoặc phân luồng authentication theo thiết kế có kiểm thử.

## 5. Servlet: tạo hai `SecurityFilterChain` với phạm vi độc lập

Ví dụ Spring MVC/Servlet dưới đây có hai chain: API Bearer JWT với `STATELESS`, browser form login có CSRF. Để chạy production cần `spring-security-oauth2-resource-server`, JWT decoder/issuer cấu hình đúng, các controller và nguồn user cho form login.

### 5.1. Cấu hình chain theo Lambda DSL

```java
package com.example.security.servlet;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfigurationSource;

@Configuration
@EnableWebSecurity
public class ServletMultiChainSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain api(
            HttpSecurity http,
            @Qualifier("apiCorsSource") CorsConfigurationSource apiCors)
            throws Exception {

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(a -> a
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
                .anyRequest().authenticated()
            )
            .cors(cors -> cors.configurationSource(apiCors))
            // CHỈ dành cho API Bearer-only, không auth cookie/browser:
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browser(
            HttpSecurity http,
            @Qualifier("browserCorsSource") CorsConfigurationSource browserCors)
            throws Exception {

        http
            // Không có securityMatcher -> fallback cho mọi URL còn lại
            .authorizeHttpRequests(a -> a
                .requestMatchers("/", "/login", "/error", "/public/**")
                    .permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .cors(cors -> cors.configurationSource(browserCors))
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

**Sáu điều cần ghi nhớ:**

1. API chain chỉ match `/api/**`; `/admin/**` và `/login` được browser fallback nhận.
2. `@Order(1)` được xét trước `@Order(2)`. Fallback không có matcher hẹp.
3. `SCOPE_admin` của JWT khác `ROLE_ADMIN` của browser form. Hai authentication mechanisms không tự kết hợp.
4. `csrf.disable()` có phạm vi chain API; browser chain vẫn yêu cầu CSRF token cho unsafe methods.
5. `SessionCreationPolicy.STATELESS` chỉ áp trên API chain và không tự biến toàn bộ ứng dụng thành stateless.
6. CORS, CSP, login/logout và session được cấu hình riêng. API chain không kế thừa browser CSP.

Không đưa `csrf.disable()` vào browser chain chỉ để xử lý POST 403. Hãy xem token, cookie, login/logout và CSRF request handler của đúng phiên bản.

### 5.2. Hai nguồn CORS, chỉ định tường minh theo chain

Với nhiều `CorsConfigurationSource`, Spring Security có thể không biết phải chọn nguồn nào. Mỗi chain nên nhận đúng source bằng `cors.configurationSource(...)`. Ví dụ **Servlet**:

```java
package com.example.security.servlet;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletCorsSources {

    @Bean("apiCorsSource")
    UrlBasedCorsConfigurationSource apiCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://spa.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean("browserCorsSource")
    UrlBasedCorsConfigurationSource browserCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://web.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN")
        );
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }
}
```

Ở đây `UrlBasedCorsConfigurationSource` thuộc package `org.springframework.web.cors`, **không phải** package reactive. API preflight chỉ nhận origin `https://spa.example.com`; browser preflight, nếu có, dùng `https://web.example.com`. Source browser đăng ký `/**` không “lan” vào API chain, vì chính API chain dùng source riêng.

`allowCredentials(false)` không làm JWT mất hiệu lực trên non-browser clients; Bearer token vẫn được Resource Server xác minh. Với browser gửi header `Authorization`, origin phải được phép và preflight `Access-Control-Allow-Headers` cần hỗ trợ `Authorization`.

### 5.3. Tình huống ba chain: API, admin riêng và fallback

Nếu `/admin/**` cần authentication entry point/CSP khác phần web còn lại, có thể tạo một chain riêng:

```text
@Order(1)  /api/**       Bearer-only API
@Order(2)  /admin/**     Admin form/session, CSRF, CSP chặt
@Order(3)  fallback     Public + web còn lại
```

Nhưng lúc này cần quyết định **login/logout URL thuộc chain nào**. `/login` ở ngoài `/admin/**` nên form login filter trong admin chain không tự xử lý `POST /login`. Có thể đặt form login tại `/admin/login` và tự cung cấp GET login page, hoặc duy trì flow login ở fallback có thiết kế session/authentication rõ ràng. Việc tách thêm chain phải tạo **lợi ích bảo mật đủ lớn** để bù phức tạp về URL, CORS, CSRF và session.

## 6. Dự đoán chain cho các request cụ thể

Với hai chain ở mục 5:

| Request | Chain | Kỳ vọng về bảo mật |
| --- | --- | --- |
| GET `/api/public/ping`, không JWT | API | GET public được phép, vẫn chịu CORS/headers API |
| POST `/api/public/ping`, không JWT | API | Rule GET public không áp; cần auth theo `anyRequest` |
| GET `/api/orders`, không JWT | API | Thường 401 với Bearer entry point |
| GET `/api/admin/report`, scope thiếu | API | Thường 403 |
| GET `/api/admin/report`, `SCOPE_admin` | API | Qua authorization, tùy handler |
| POST `/api/orders`, JWT hợp lệ | API | Theo threat model không cần CSRF, vẫn cần auth/quyền |
| GET `/public/help`, không login | Browser | Public, vẫn có security headers của browser |
| GET `/admin/report`, USER | Browser | 403 vì thiếu `ROLE_ADMIN` |
| POST `/orders`, user login, thiếu token | Browser | 403 do CSRF |
| POST `/orders`, user login, token đúng | Browser | Qua CSRF; quyền và handler xét tiếp |
| GET `/login` | Browser | Form login endpoint/template |
| POST `/login`, thiếu token | Browser | Bị CSRF từ chối |
| POST `/logout`, có token hợp lệ | Browser | Logout filter xử lý |
| GET `/unknown`, không login | Browser | Không bị lọt khỏi Spring Security |

Status cuối cùng có thể là 200, 201, 204, 302, 401, 403 hoặc 404 tùy endpoint, entry point và authentication state. **Không chỉ kiểm tra HTTP status**; nên kiểm tra selected chain, quyền, headers và CSRF riêng để biết vì sao request được cho phép hoặc bị từ chối.

## 7. Phạm vi chính sách khi dùng `permitAll`, `denyAll` và fallback

### `permitAll` cho public asset

`permitAll()` chỉ cho qua bước authorization. CSRF tiếp tục kiểm tra unsafe methods nếu chain yêu cầu; các security headers mặc định hoặc CSP tùy chỉnh vẫn có thể được ghi. Vì vậy `GET /public/logo.svg` công khai không đồng nghĩa “bypass tất cả bảo vệ”.

### `denyAll` tại fallback

Một hệ thống API-only có thể đặt fallback `anyRequest().denyAll()` để từ chối mọi route ngoài danh sách đã biết. Khi có browser form login, fallback cần cho phép chính xác `/login`, `/error` và những URL thực sự cần thiết trước `denyAll`, nếu không flow bị khóa. `denyAll` có hiệu lực **chỉ khi request vào fallback chain**.

### HTTP method và thứ tự

`requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()` chỉ mở GET. `POST` cùng URL đi đến rule tiếp theo, nhưng vẫn chịu CSRF hoặc xác thực tùy chain. Đừng đặt `requestMatchers("/**").permitAll()` trước các rule admin rồi kỳ vọng rule cụ thể được ưu tiên tự động.

### Chain hẹp phải có fallback

Chỉ có `securityMatcher("/api/**")` mà không có chain nào khác có thể để `/admin/**`, `/login` và `/actuator/**` không được Spring Security bảo vệ. Khi tự tạo custom chain, **không trông chờ Spring Boot luôn sinh fallback security chain**. Hãy kiểm tra cả application context/management context, nhất là khi Actuator chạy cổng riêng.

## 8. Reactive/WebFlux: phạm vi tương đương, API khác Servlet

WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và `ServerWebExchangeMatcher`. Có thể xây cùng mô hình API Bearer + browser fallback nhưng **không tái sử dụng** các bean Servlet.

### 8.1. Hai `SecurityWebFilterChain` riêng biệt

```java
package com.example.security.reactive;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class ReactiveMultiChainSecurity {

    @Bean
    @Order(1)
    SecurityWebFilterChain api(
            ServerHttpSecurity http,
            @Qualifier("apiCorsSource") CorsConfigurationSource apiCors) {

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**")
            )
            .authorizeExchange(a -> a
                .pathMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .pathMatchers("/api/admin/**").hasAuthority("SCOPE_admin")
                .anyExchange().authenticated()
            )
            .cors(cors -> cors.configurationSource(apiCors))
            .csrf(csrf -> csrf.disable())
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain browser(
            ServerHttpSecurity http,
            @Qualifier("browserCorsSource") CorsConfigurationSource browserCors) {

        return http
            .authorizeExchange(a -> a
                .pathMatchers("/", "/login", "/error", "/public/**")
                    .permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .cors(cors -> cors.configurationSource(browserCors))
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

- `ServerWebExchangeMatchers.pathMatchers` chọn **chain**, còn `pathMatchers` bên trong `authorizeExchange` quyết định **authorization**.
- `NoOpServerSecurityContextRepository` thể hiện ý định không lưu SecurityContext vào WebSession cho API Bearer. Nó không cấm các component khác sử dụng `WebSession`.
- Form login Reactive có cơ chế `WebSession` và `ServerSecurityContextRepository` của WebFlux, không phải `HttpSession`.
- CSRF Reactive dùng `CsrfWebFilter` và `ServerCsrfTokenRepository`. Với browser session cần lưu/lấy token và xử lý token lifecycle theo phiên bản.
- Test `mockJwt()` không thay việc tích hợp JWT decoder/issuer thực trong production.

### 8.2. Hai CORS source riêng của WebFlux

```java
package com.example.security.reactive;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsSources {

    @Bean("apiCorsSource")
    UrlBasedCorsConfigurationSource apiCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://spa.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean("browserCorsSource")
    UrlBasedCorsConfigurationSource browserCorsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://web.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN")
        );
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }
}
```

`UrlBasedCorsConfigurationSource` của WebFlux thuộc `org.springframework.web.cors.reactive`; loại Servlet thuộc `org.springframework.web.cors`. Chúng trùng tên nhưng không thay thế nhau. Những ví dụ Servlet và Reactive trong bài **phải chạy ở hai ứng dụng độc lập**, không đăng ký mọi bean vào cùng một context rồi kỳ vọng hai stacks xử lý request song song.

## 9. CSRF là một lớp chọn request *bên trong chain*

### 9.1. CSRF và authorization khác nhau

Một endpoint `POST /public/feedback` dùng form không yêu cầu đăng nhập vẫn có thể phải gửi CSRF token nếu nó nằm trong browser chain với CSRF bật. `permitAll()` không thay đổi yêu cầu CSRF.

Ở chain API Bearer-only, ví dụ dùng `csrf(csrf -> csrf.disable())`. Nếu API vẫn nhận session cookie/credential browser tự gửi, đây có thể là lỗ hổng; phải thiết kế lại thay vì sao chép ngoại lệ. Không kết luận “đó là REST API nên không cần CSRF”.

### 9.2. Ba lựa chọn khác nhau

**Giữ CSRF mặc định ở browser:**

```java
http.csrf(Customizer.withDefaults());
```

**Bỏ qua đúng một webhook Servlet được xác thực bằng chữ ký độc lập:**

```java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhooks/signed")
);
```

**Tắt ở chain Bearer-only đã được đánh giá:**

```java
http
    .securityMatcher("/api/**")
    .csrf(csrf -> csrf.disable());
```

Đây là **ba phương án thiết kế độc lập**, không đặt cả ba liên tiếp trong một chain. Webhook phải kiểm tra chữ ký/HMAC, timestamp và chống replay; miễn CSRF không có nghĩa cho phép anonymous thực thi tùy ý.

Ngoài chain matcher còn có **CSRF request matcher**. Với CSRF mặc định, HTTP methods an toàn như GET, HEAD, OPTIONS, TRACE không yêu cầu token; POST/PUT/PATCH/DELETE thường cần token. Một POST có user hợp lệ có thể bị 403 do CSRF, không phải do role.

```text
POST /orders
   |
   v
Chọn Browser chain
   |
   v
CSRF filter có được cài ở chain không?
   |
   v
Request matcher của CSRF yêu cầu token?
   |
   +-- Có: token thiếu/sai -> 403
   |        token hợp lệ -> tiếp tục authentication/authorization
   |
   +-- Không: tiếp tục các bước khác
```

Spring Security 6+ sử dụng deferred token và bảo vệ BREACH, vì vậy SPA cookie/session cần đúng cơ chế nhận token, nhất là sau login/logout. Cấu hình CSRF phải được kiểm thử theo phiên bản và client thực tế, không chỉ dựa vào việc `csrf(Customizer.withDefaults())` có xuất hiện trong code.

## 10. CORS theo chain: phải tính tới preflight

### 10.1. Bảng origin và phạm vi

| Request | Chain | Origin | Quyết định CORS dự kiến |
| --- | --- | --- | --- |
| OPTIONS `/api/orders` | API | `https://spa.example.com` | Được xét theo API allowlist |
| OPTIONS `/api/orders` | API | `https://web.example.com` | Không tự được phép vì browser chain cho phép origin này |
| OPTIONS `/admin/report` | Browser | `https://web.example.com` | Theo browser allowlist |
| OPTIONS `/admin/report` | Browser | `https://spa.example.com` | Không tự có quyền credentialed CORS |
| GET `/public/help` không `Origin` | Browser | Không có | Không cần `Access-Control-Allow-Origin` vô điều kiện |

CORS là chính sách do browser thực thi; client `curl`/mobile không bị giới hạn bởi trình duyệt CORS. Server vẫn phải xác thực và phân quyền mọi request nhạy cảm.

### 10.2. OPTIONS dễ rơi ngoài chain

Preflight thường không có session cookie:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://spa.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

Cần để CORS được xử lý trước authentication phù hợp. Nếu chain chỉ chọn method POST (thay vì chọn path `/api/**` không giới hạn method), preflight OPTIONS có thể rơi sang chain khác và không nhận CORS source của API.

Đừng dùng `requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()` như cách thay thế toàn bộ cấu hình CORS. Browser vẫn cần allow-origin, allow-methods, allow-headers và credentials policy tương ứng.

### 10.3. CORS ngoài chain

CORS còn có thể được xử lý ở Spring MVC, WebFlux router, một Servlet `CorsFilter`/Reactive `CorsWebFilter` global hoặc reverse proxy. Nếu nhiều lớp cùng ghi header, response có thể có giá trị `Access-Control-Allow-Origin` trùng lặp, cache sai theo `Origin` hoặc policy trái ngược. Hãy xác định một nguồn policy đáng tin và kiểm thử qua đường HTTP public.

Khi CORS response thay đổi theo Origin, cần quan sát `Vary` phù hợp để cache không chia sẻ nhầm response giữa origin khác nhau. `allowCredentials=true` không được kết hợp với wildcard `*` trong `Access-Control-Allow-Origin`.

## 11. Security headers, CSP và HSTS theo chain

### 11.1. CSP và các header writer

Spring Security quản lý những security headers mặc định như cache control, `X-Content-Type-Options: nosniff`, frame options và HSTS trên HTTPS (tùy phiên bản/cấu hình). **CSP không được Spring Security thêm mặc định**; ứng dụng tự đưa ra policy.

| Response | Chain | CSP ví dụ |
| --- | --- | --- |
| GET `/api/public/ping` | API | `default-src 'none'; frame-ancestors 'none'` |
| GET `/api/admin/report` | API | Cùng API CSP |
| GET `/public/help` | Browser | `default-src 'self'; object-src 'none'; frame-ancestors 'none'` |
| GET `/admin/report` | Browser | Cùng browser CSP |
| Asset do CDN phục vụ riêng | Không qua Spring Security app | Cần policy ở CDN/edge nếu cần |
| Servlet URL `web.ignoring()` | Bỏ qua Spring Security | Không nhận headers do Spring Security viết |

Với SPA do CDN phục vụ, CSP `connect-src` trên response **trang HTML** cần cho phép API origin nếu giao diện gọi API khác origin. CSP gắn vào response JSON của API không thay thế CSP của trang HTML do CDN cung cấp.

### 11.2. HSTS: cấu hình theo chain nhưng browser nhớ theo host

HSTS `Strict-Transport-Security` được đưa vào **HTTPS response** theo cấu hình bảo vệ. Tuy nhiên, sau khi được browser ghi nhớ, HSTS áp dụng ở **mức hostname** (và có thể mọi subdomain), không phải chỉ riêng `/api/**` hay `/admin/**`.

Điều này tạo một yêu cầu vận hành: nếu API và browser cùng hostname, tránh cấu hình max-age/includeSubDomains khác nhau giữa các chain. Có thể quản lý HSTS tập trung tại edge hoặc đảm bảo policy nhất quán trên các chain; phải kiểm tra HTTPS public khi TLS terminate ở proxy.

Không bật `includeSubDomains` hoặc `preload` tùy tiện. HSTS trên `http://localhost:8080` không xuất hiện không chứng minh sản phẩm public HTTPS thiếu HSTS.

### 11.3. Header mất khi chain không match

Một response có `X-Content-Type-Options` không đủ chứng minh authorization đúng, vì proxy cũng có thể thêm header. Ngược lại, nếu một URL không nhận CSP mong đợi, có thể request vào **chain khác**, bị `web.ignoring()` hoặc được CDN phục vụ trực tiếp. Dùng kết hợp request log, role tests và đối chiếu response để chẩn đoán.

## 12. Session, login/logout và authentication entry points

### 12.1. Stateful và stateless

Ở Servlet, API chain có thể chọn `SessionCreationPolicy.STATELESS` để Spring Security không sử dụng `HttpSession` cho SecurityContext; browser chain dùng `HttpSession` để duy trì form login. Ở Reactive, API chain có thể chọn `NoOpServerSecurityContextRepository`, còn browser dùng `WebSession`.

Không tự cho rằng `STATELESS` sẽ cấm mọi code trong ứng dụng tạo session/cookie. Session store, cookie `Secure`/`HttpOnly`/`SameSite`, timeout và session fixation còn phụ thuộc hạ tầng container, Spring Session, WebSession và cấu hình khác.

### 12.2. Filter-provided endpoints phải thuộc matcher

Giả sử chain chỉ match `/secured/**` nhưng bật form login mặc định ở `/login`. `POST /login` có thể không được filter chain đó xử lý; URL có thể 404 hoặc đi vào chain khác mà không có login filter.

Một ví dụ Servlet dùng login URL thuộc chain:

```java
http
    .securityMatcher("/secured/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/secured/login").permitAll()
        .anyRequest().authenticated()
    )
    .formLogin(form -> form
        .loginPage("/secured/login")
        .loginProcessingUrl("/secured/login")
        .permitAll()
    )
    .logout(logout -> logout
        .logoutUrl("/secured/logout")
    );
```

Khi tự chọn `loginPage`, ứng dụng phải cung cấp **GET `/secured/login`** bằng controller/template; form login filter vẫn xử lý POST theo `loginProcessingUrl`. Browser request POST login/logout cần CSRF phù hợp. Không tự coi filter endpoints là global đối với tất cả chain.

### 12.3. Status khác nhau không phải nhất thiết là lỗi

| Loại chain | Chưa đăng nhập, gọi private URL | User đã xác thực nhưng thiếu quyền |
| --- | --- | --- |
| Resource Server Bearer | Thường 401 + Bearer challenge | Thường 403 |
| HTTP Basic | Thường 401 + Basic challenge | Thường 403 |
| Form login | Thường 302 chuyển đến trang login | Thường 403 |

Entry point/exception handler/`Accept` header có thể làm response khác ví dụ. Một test chỉ assert “mọi anonymous trả 401” dễ đánh giá sai browser chain hoạt động đúng bằng redirect login.

## 13. Không nhầm cơ chế toàn pipeline với cấu hình của chain

### HTTP firewall

Servlet `StrictHttpFirewall` thường xử lý request bất thường trong `FilterChainProxy` trước khi authorization matcher được xét. Reactive `StrictServerWebExchangeFirewall` là cơ chế tương ứng riêng cho WebFlux. Khi nhận `RequestRejectedException` hoặc response 400 do path sai chuẩn, không suy rằng rule role đã được áp đúng — có thể request bị chặn trước bước phân quyền.

### Method security

`@PreAuthorize` và method security chỉ kiểm tra một lời gọi method đã được bảo vệ; chúng không thay thế CSRF, CORS, headers, session hay việc mọi URL nhạy cảm đi vào đúng HTTP chain. Có thể dùng như defense in depth nhưng không dùng làm lý do chấp nhận chain bị bỏ sót.

### Management context

Spring Boot Actuator ở management port riêng có thể hoạt động trong application context khác. Fallback chain trên application port không tự chứng minh management port đã an toàn. Kiểm tra exposure, auth và network policy trên cổng management thật.

### Path mapping, servlet context và reverse proxy

Security matcher thường xét URL mà backend nhận **sau** ingress rewrite. Nếu public `/portal/api/orders` được proxy đổi thành backend `/api/orders`, thiết kế chain cần dựa trên path thực được matcher nhìn thấy. Spring Security 7 Servlet dùng `PathPatternRequestMatcher` cho string patterns và loại bỏ context path khỏi phần matcher; Security 6.x có thể chọn MVC/Ant matcher tùy cấu hình. Kiểm thử bằng HTTP public lẫn integration test backend.

Những URL cần thử gồm `/api`, `/api/`, `/api-v2/orders`, `/admin/report/`, duplicate slash, encoded slash, semicolon, path traversal, `ERROR`/`FORWARD` dispatch khi phù hợp. Không nới firewall để sửa bypass khi chưa biết proxy/container/router xử lý path ra sao.

## 14. Kiểm thử Servlet: chứng minh đúng chain, không chỉ HTTP status

Mỗi test nên chứng minh hai điều:

1. Request thuộc **đúng chain** theo URL và `@Order`.
2. Chính sách **đúng cho chain đó** thực sự được áp dụng: auth, CSRF, CORS, CSP, session.

Giả sử `MockMvc mvc` đã gắn Spring Security filter chain; ứng dụng có controller `GET /api/admin/report`, `GET /admin/report`, `GET /api/public/ping`, `GET /public/help`, `POST /api/orders` và `POST /orders`. Những endpoint hợp lệ trả HTTP 200 trong môi trường test.

### 14.1. Authorization API và browser khác nhau

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void servletAuthorizationDependsOnSelectedChain() throws Exception {
    mvc.perform(get("/api/admin/report").with(jwt()
            .authorities(new SimpleGrantedAuthority("SCOPE_read"))))
        .andExpect(status().isForbidden());

    mvc.perform(get("/api/admin/report").with(jwt()
            .authorities(new SimpleGrantedAuthority("SCOPE_admin"))))
        .andExpect(status().isOk());

    mvc.perform(get("/admin/report").with(user("viewer").roles("USER")))
        .andExpect(status().isForbidden());

    mvc.perform(get("/admin/report").with(user("admin").roles("ADMIN")))
        .andExpect(status().isOk());

    mvc.perform(get("/api/public/ping"))
        .andExpect(status().isOk());
}
```

`jwt()` của `spring-security-test` tạo ngữ cảnh JWT cho test, **không** chứng minh JWT issuer, signature, audience, expiration và production decoder đang đúng. Cần thêm các test tích hợp JWT thật hoặc cấu hình test decoder chuyên biệt. Nếu controller không tồn tại, 404 không chứng minh authorization đúng.

### 14.2. CSRF bị tắt ở API chain nhưng bật ở browser

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void servletBrowserRequiresCsrfWhileBearerApiDoesNot() throws Exception {
    // API Bearer-only: request không có CSRF token nhưng có JWT mock hợp lệ.
    mvc.perform(post("/api/orders").with(jwt()))
        .andExpect(status().isOk());

    // Browser chain: đã có user nhưng thiếu CSRF token.
    mvc.perform(post("/orders").with(user("viewer")))
        .andExpect(status().isForbidden());

    mvc.perform(post("/orders")
            .with(user("viewer"))
            .with(csrf()))
        .andExpect(status().isOk());
}
```

Giả định endpoint cho phép người dùng trong fixture và trả 200 khi hợp lệ. Nếu trả 201/204, chỉnh expected status; đừng tắt CSRF để cho test qua. Thêm test `with(csrf().useInvalidToken())` để bảo đảm token sai vẫn bị chặn.

### 14.3. CSP và CORS phải phân biệt chain

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

@Test
void servletResponseUsesChainSpecificCsp() throws Exception {
    mvc.perform(get("/api/public/ping"))
        .andExpect(header().string("Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'"));

    mvc.perform(get("/public/help"))
        .andExpect(header().string("Content-Security-Policy",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'"));
}

@Test
void servletCorsOriginDoesNotLeakAcrossChains() throws Exception {
    mvc.perform(options("/api/orders")
            .header("Origin", "https://spa.example.com")
            .header("Access-Control-Request-Method", "POST"))
        .andExpect(header().string(
            "Access-Control-Allow-Origin", "https://spa.example.com"));

    mvc.perform(options("/api/orders")
            .header("Origin", "https://web.example.com")
            .header("Access-Control-Request-Method", "POST"))
        .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
}
```

Một origin bị CORS từ chối có thể nhận 403; điều quan trọng là **không được cấp quyền CORS cho origin lạ**. Đừng bắt buộc negative test phải trả một status duy nhất khi policy/exception handler có thể thay đổi. Phải gắn `springSecurity()` nếu khởi tạo `MockMvc` thủ công; test chỉ gọi controller mà bỏ security filters có thể báo kết quả sai.

### 14.4. Ranh giới `/api` và nhiều phiên bản matcher

Tối thiểu kiểm tra:

- `/api`, `/api/`, `/api/orders`.
- `/api-v2/orders`, `/admin/report` và `/unknown`.
- `/admin/report/`, `/ADMIN/report`.
- GET/POST/OPTIONS trên cùng path.
- Request public path và backend path khác nhau sau proxy rewrite.

Không suy từ chuỗi `/api/**` rằng `/api-v2/**` được bảo vệ bởi API chain. Với `/api` và `/api/`, phải xác minh matcher cụ thể và controller routing của phiên bản đã resolve. Một request 404 vì handler không match **chưa chứng minh** URL đã qua đúng security chain.

## 15. Kiểm thử Reactive: cùng contract, dùng `WebTestClient`

Với `WebTestClient client` bind vào `ApplicationContext` và áp dụng `springSecurity()`, có thể kiểm tra cùng bộ hợp đồng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void reactiveApiAndBrowserUseDifferentPolicies() {
    client.mutateWith(mockJwt()
            .authorities(new SimpleGrantedAuthority("SCOPE_read")))
        .get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockJwt()
            .authorities(new SimpleGrantedAuthority("SCOPE_admin")))
        .get().uri("/api/admin/report")
        .exchange()
        .expectStatus().isOk();

    client.mutateWith(mockUser("viewer").roles("USER"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockJwt())
        .post().uri("/api/orders")
        .exchange()
        .expectStatus().isOk();

    client.mutateWith(mockUser("viewer").roles("USER"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("viewer").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk();
}
```

Đây là snippet nằm trong một test đã khai báo `client` và có các handler tương ứng. Có thể tạo client như sau:

```java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
```

`mockJwt()`, `mockUser()` và `csrf()` làm việc trong test context; chúng không đăng nhập vào server từ xa. Khi test production-like, dùng token thật được cấp bởi issuer kiểm thử và kiểm tra login, cookie, CORS/HSTS qua HTTPS/ingress.

### 15.1. Ma trận dùng chung giữa Servlet và Reactive

| Tình huống | Servlet: MockMvc | Reactive: WebTestClient | Hợp đồng cần chứng minh |
| --- | --- | --- | --- |
| GET API public | `get("/api/public/ping")` | `get().uri(...)` | Ẩn danh có thể đọc |
| GET API admin thiếu scope | `with(jwt().authorities(...))` | `mutateWith(mockJwt().authorities(...))` | Bị từ chối |
| GET browser admin thiếu role | `with(user(...).roles("USER"))` | `mutateWith(mockUser(...).roles("USER"))` | Bị từ chối |
| POST API Bearer không CSRF | `with(jwt())` | `mutateWith(mockJwt())` | Hợp lệ theo threat model |
| POST browser thiếu token | `with(user(...))` | `mutateWith(mockUser(...))` | 403 |
| POST browser có token | `with(csrf())` | `mutateWith(csrf())` | Qua CSRF |
| OPTIONS preflight | `options(...).header(...)` | `options().uri(...).header(...)` | Đúng CORS source cho chain |
| CSP hai chain | `header().string(...)` | `expectHeader().valueEquals(...)` | Chính sách đúng response |
| HSTS HTTPS | `secure(true)` và HTTPS public | Secure exchange/HTTPS public | HSTS đúng hostname |
| Login/logout | Form filters/session | Reactive web filters/WebSession | URL nằm trong chain phù hợp |

Đừng so sánh mọi status bằng nhau theo kiểu máy móc nếu API Bearer trả 401 còn form login chuyển hướng 302. Kiểm tra **đúng quyết định bảo mật** và nguồn gốc status.

## 16. Quan sát HTTP thực tế qua proxy và TLS

### 16.1. Preflight CORS

```bash
# Dùng endpoint staging thật do bạn quản lý; URL dưới đây chỉ là ví dụ.
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://spa.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type"

curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://web.example.com" \
  -H "Access-Control-Request-Method: POST"
```

Preflight đầu phải được xét theo API CORS allowlist; preflight sau không được cấp origin sai. Với CORS credentialed, kiểm tra `Access-Control-Allow-Credentials` và không cho `Access-Control-Allow-Origin: *`.

### 16.2. Headers và HTTPS

```bash
curl -i "https://api.example.com/api/public/ping"
curl -i "https://api.example.com/public/help"
```

Quan sát `Content-Security-Policy` riêng, `X-Content-Type-Options` và `Strict-Transport-Security`. HSTS cần đo trên **HTTPS public** chứ không chỉ backend HTTP. CDN/proxy có thể thêm/xóa header; nếu frontend HTML được phục vụ từ CDN, kiểm tra CSP trên URL CDN/frontend thực sự.

Đừng in session cookie/JWT thật ra báo cáo chia sẻ. Dùng account/test tokens được cấp phép. Trên PowerShell, gọi `curl.exe` nếu `curl` bị ánh xạ sang `Invoke-WebRequest`.

## 17. Chẩn đoán các lỗi do sai phạm vi chain

### Lỗi 1 — `/admin/**` vẫn truy cập được dù API chain có `anyRequest().authenticated()`

**Nguyên nhân:** chain chỉ match `/api/**`, không có fallback, hoặc một chain khác được chọn trước với `permitAll` rộng.

**Cách điều tra:** liệt kê các bean chain, matcher và `@Order`; thử `/admin/**` với user USER và ADMIN; kiểm tra fallback bao phủ URL đó. Không giả định Boot sẽ tự tạo fallback khi có custom chains.

### Lỗi 2 — Browser POST không cần CSRF sau khi thêm Bearer API

**Nguyên nhân:** `csrf.disable()` của API được áp vào chain quá rộng, hoặc browser chain cũng đã tắt CSRF.

**Cách điều tra:** xác nhận `securityMatcher` và selected chain của POST, rồi thử token thiếu/sai/đúng. Không tắt CSRF toàn app để xử lý vấn đề CORS.

### Lỗi 3 — OPTIONS preflight 401 mặc dù Bearer JWT hợp lệ khi POST

**Nguyên nhân:** preflight thường không gửi cookie/token; CORS source không được xử lý trước authentication, proxy chặn OPTIONS hoặc chain matcher theo method loại trừ OPTIONS.

**Cách điều tra:** gửi `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` đầy đủ; kiểm tra API CORS source, `@Order` và cả ingress.

### Lỗi 4 — CSP trên API đúng nhưng trang HTML không có CSP

**Nguyên nhân:** chỉ API chain cấu hình CSP, browser chain không cấu hình, hoặc HTML do CDN phục vụ ngoài Spring.

**Cách điều tra:** kiểm tra từng response theo URL thực, nơi phát HTML và CSP `connect-src`. CORS phía API không thay thế CSP trên frontend.

### Lỗi 5 — `GET /login` trả 404 khi chuyển form login sang chain `/admin/**`

**Nguyên nhân:** login endpoint mặc định ngoài chain; filter ở admin chain không xử lý `/login`.

**Cách điều tra:** thiết kế login URL thuộc matcher hoặc để form login ở fallback browser chain; nếu dùng `loginPage` custom phải tự cung cấp GET HTML.

### Lỗi 6 — API Bearer tạo session hoặc browser login không duy trì được

**Nguyên nhân:** session/context repository hoặc entry point bị cấu hình sai chain. Browser route có thể vào stateless chain; API có thể vô tình dùng session repository.

**Cách điều tra:** kiểm tra cookie, `SessionCreationPolicy` Servlet hoặc `ServerSecurityContextRepository` Reactive, login/logout và request sau authentication.

### Lỗi 7 — HSTS có trên `/admin/**` nhưng không có trên `/api/**`

**Nguyên nhân:** API chain tắt headers/HSTS, cấu hình HSTS khác nhau hoặc request bị backend nhìn là HTTP do proxy.

**Cách điều tra:** đo HTTPS public cho cả hai URL, thống nhất HSTS ở mức host hoặc edge, kiểm tra trusted forwarded headers.

### Lỗi 8 — URL đã `denyAll` nhưng vẫn trả 200

**Nguyên nhân:** request không vào chain có `denyAll` hoặc một chain khác được ưu tiên trước; cũng có thể ingress rewrite khiến path backend khác path dự kiến.

**Cách điều tra:** kiểm tra chain selection trước authorization, kiểm tra URL public/backend, thử variant dấu slash và encoded path.

### Lỗi 9 — Preflight cho origin browser được cấp trên API dù không mong đợi

**Nguyên nhân:** CORS source khác chain bị áp nhầm; nguồn CORS global ở proxy/controller quá rộng; hoặc response bị cache sai theo Origin.

**Cách điều tra:** so sánh preflight trên `/api/**` và `/admin/**`, kiểm tra nguồn header và `Vary`; không cấp credential CORS cho origin ngoài allowlist.

### Lỗi 10 — Actuator lộ endpoint nhạy cảm khi management port khác app port

**Nguyên nhân:** management context/port có cấu hình riêng; fallback ở application port không bảo vệ mọi đường đi.

**Cách điều tra:** test đúng cổng management, endpoint exposure, authentication và network policies; không suy từ kết quả security test của app port.

## 18. Quy trình rà soát khi thêm hoặc nâng cấp security chain

1. **Khóa phiên bản:** ghi JDK, Spring Boot, Spring Framework, Spring Security và loại web stack thực sự được chọn; kiểm tra dependency graph, không suy từ một dependency khai báo.
2. **Vẽ inventory URL:** API, browser, admin, login/logout, webhook, actuator, error, public và static assets.
3. **Liệt kê các chain:** `@Order`, `securityMatcher`, cơ chế xác thực, CSRF, CORS source, CSP/HSTS và session policy.
4. **Dự đoán chain selection:** với mỗi URL ghi chain đầu tiên sẽ match; tìm URL không chain nào match và matcher rộng che matcher hẹp.
5. **Đối chiếu authorization:** sắp xếp rule từ cụ thể đến tổng quát; thử cả user hợp lệ, thiếu quyền, anonymous.
6. **Thử unsafe HTTP methods:** phân biệt CSRF token thiếu/sai, authorization 403, preflight OPTIONS và việc JWT/cookie được gửi.
7. **Kiểm tra per-chain headers:** CSP, `nosniff` và HSTS ở response có thực; nếu có CDN, xem nơi phát header.
8. **Kiểm tra login/logout/session:** endpoint có thuộc chain chứa filter, cookie flags, rotation, expiry và entry point.
9. **Kiểm tra URL normalization:** context path, servlet path, trailing slash, encoded slash, semicolon và ingress rewrite; không tùy tiện nới firewall.
10. **Kiểm tra management context:** nếu Actuator chạy port riêng, test ngay tại cổng đó.
11. **Rà soát migration:** Spring Security 5.x dùng `antMatchers`/adapter cũ, 6.x dùng bean/Lambda DSL và matcher mới, 7.x thay đổi cách PathPattern matcher trên Servlet; chạy lại regression tests sau nâng major.
12. **Kiểm tra qua HTTPS public:** phản hồi CORS, CSP, HSTS, redirect, cookie và proxy; đừng dừng ở mock tests.

### Manifest mẫu cho review

| Thuộc tính | API chain | Browser chain |
| --- | --- | --- |
| Order | 1 | 2 |
| Chain matcher | `/api/**` | Fallback mọi request |
| Auth | JWT Resource Server | Form login |
| Anonymous/public | GET `/api/public/**` | `/public/**`, login, error |
| Quyền nhạy cảm | `SCOPE_admin` | `ROLE_ADMIN` |
| CSRF | Tắt có điều kiện: Bearer-only | Bật |
| CORS | SPA origin, no credentialed CORS | Browser origin, credentialed nếu cần |
| CSP | API response policy | HTML/browser policy |
| HSTS | Thống nhất theo host | Thống nhất theo host |
| Session | Stateless security context | Session/WebSession |
| Login/logout | Không có form endpoints | `/login`, `/logout` |
| Negative tests | JWT thiếu scope; path ngoài API | User thiếu role, POST thiếu CSRF |

## 19. Bài tập thực hành

### Bài tập 1 — Chain selection

Một ứng dụng có chain `@Order(1)` match `/api/**` và fallback chain `@Order(2)` không có matcher. Hãy xác định chain cho `/api/orders`, `/api/public/ping`, `/admin/report`, `/unknown`, `/login`, `/api-v2/orders`. Vì sao `anyRequest().authenticated()` của chain API không bảo vệ `/admin/report`?

### Bài tập 2 — Sửa CSRF bị mở quá rộng

Nhóm đổi API chain thành `securityMatcher("/**")` nhưng vẫn `csrf.disable()`. Browser chain `@Order(2)` vẫn bật CSRF. Hãy giải thích vì sao browser chain có thể không bao giờ được chọn, sửa matcher và thêm test browser POST thiếu token phải bị 403.

### Bài tập 3 — Hai nguồn CORS

Frontend SPA `https://spa.example.com` dùng Bearer JWT gọi `/api/**`. Trang quản trị `https://web.example.com` dùng session cookie gọi `/admin/**`. Viết hai `CorsConfigurationSource` Servlet và ánh xạ source vào đúng chain; test OPTIONS từ origin được phép và origin sai. Làm lại cho WebFlux bằng đúng package reactive.

### Bài tập 4 — Login endpoint nằm sai chain

Form login được khai báo trong chain chỉ match `/secured/**`, URL processing mặc định `/login`. Giải thích vì sao POST `/login` có thể không hoạt động; cấu hình `/secured/login` cùng GET login page và CSRF đúng.

### Bài tập 5 — Servlet và Reactive cùng contract

Xây hai ứng dụng độc lập với API JWT và browser form, dùng `MockMvc` và `WebTestClient`. Tạo regression tests cho JWT thiếu scope, browser thiếu ADMIN, CSRF thiếu token, CORS sai origin, CSP khác chain và fallback endpoint.

### Bài tập 6 — HSTS, reverse proxy và Actuator

Public URL `https://example.com/portal/api/orders` được ingress rewrite thành backend `/api/orders`. Actuator phục vụ cổng quản lý khác. Hãy xác định security matcher tại backend, kiểm tra HSTS trên HTTPS public và kiểm tra bảo mật của management port. Vì sao fallback app chain không tự chứng minh Actuator context an toàn?

## 20. Checklist trước khi merge hoặc triển khai

- [ ] Biết chính xác thứ tự và chain matcher của tất cả `SecurityFilterChain`/`SecurityWebFilterChain`.
- [ ] Có fallback chain bao phủ URL ngoài các nhóm đặc biệt, hoặc quyết định deny rõ ràng được kiểm thử.
- [ ] Không có chain ưu tiên cao với matcher rộng che mất chain khác.
- [ ] Phân biệt `securityMatcher` với `requestMatchers`/`pathMatchers` và `anyRequest`/`anyExchange`.
- [ ] Public URL dùng `permitAll` khi vẫn cần CSRF/headers; không dùng `web.ignoring` ngoài chủ đích.
- [ ] CSRF chỉ miễn ở API Bearer-only đã đánh giá; browser cookie/session vẫn có token đúng.
- [ ] CORS source tường minh theo chain; preflight OPTIONS từ origin hợp lệ và không hợp lệ đều được kiểm thử.
- [ ] CSP/headers được quan sát ở đúng response; HSTS thống nhất theo hostname trên HTTPS public.
- [ ] Session, login/logout URLs, authentication mechanism và JWT decoder được kiểm thử riêng.
- [ ] Có test ranh giới URL, HTTP methods, dispatcher type, encoded path và ingress rewrite.
- [ ] HTTP firewall vẫn chặt, không nới chỉ để vượt qua lỗi 400/403.
- [ ] Actuator/management port có security và exposure policy riêng nếu cần.
- [ ] Có manifest chain và regression tests chạy sau mỗi nâng cấp Spring Security/Boot.

## Nguồn tham khảo chính thức

1. [Spring Security — Servlet Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) — nhiều chain, `securityMatcher`, fallback, `@Order`, endpoint do filter cung cấp.
2. [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, thứ tự và chọn chain trên WebFlux.
3. [Spring Security — Servlet Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) và [Reactive Request Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — rule matchers và lựa chọn quyền.
4. [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html) và [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — preflight và nguồn CORS theo chain/stack.
5. [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) và [Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — CSRF token, request matchers và ngoại lệ.
6. [Spring Security — Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) và [Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — security headers, CSP/HSTS.
7. [Spring Security — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html) và [Reactive HTTP Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — normalized paths và xử lý request bất thường.
8. [Spring Security — Servlet MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html), [MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) và [Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — test đúng security filters.

**Câu hỏi tự đánh giá:** Vì sao `anyRequest().authenticated()` trong một chain chỉ match `/api/**` không bảo vệ `/admin/**`? `csrf.disable()` thuộc chain API có làm tắt CSRF ở browser chain không, với điều kiện matcher đúng? Tại sao CORS origin được phép ở browser chain không tự được phép ở API chain? Và vì sao HSTS tuy có header writer riêng từng chain lại có tác động ở mức hostname trên trình duyệt?
