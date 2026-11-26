# Lambda DSL cho HttpSecurity và ServerHttpSecurity

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Phạm vi:** Cấu hình các lớp phòng vệ HTTP và trình duyệt bằng Lambda DSL của Spring Security: CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, xác thực, phân quyền và bảo vệ session trong ứng dụng **Servlet** và **Reactive**.  
> **Định hướng phiên bản:** Dùng phong cách Lambda DSL được hỗ trợ ở Spring Security 6.5 và bắt buộc cho cấu hình Java trong Spring Security 7.x. Kiểm tra API và dependency thực tế của dòng Spring Security do Spring Boot đang quản lý khi áp dụng.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích được ý nghĩa của `Customizer`, `Customizer.withDefaults()`, các lambda lồng nhau và `build()` trong Spring Security.
2. Viết bean `SecurityFilterChain` bằng `HttpSecurity` cho **Servlet / Spring MVC** và bean `SecurityWebFilterChain` bằng `ServerHttpSecurity` cho **Reactive / WebFlux**.
3. Phân biệt **phạm vi áp dụng filter chain** với **quy tắc phân quyền endpoint**, đặc biệt khi có nhiều chain và `@Order`.
4. Cấu hình CSRF, CORS, CSP và security headers bằng Lambda DSL; giải thích HSTS, HTTP firewall và session trong từng stack.
5. Chuyển cú pháp chaining cũ dùng `.and()` sang Lambda DSL, tránh lỗi khi nâng Spring Security 6 → 7.
6. Kiểm thử các tình huống tấn công và phân tích lỗi 401/403, lỗi CORS, headers bị thiếu và request lọt qua filter chain.

## 2. Lambda DSL là gì và vì sao Spring Security dùng nó?

### 2.1. Ý tưởng cốt lõi

**DSL (Domain-Specific Language)** là cách tổ chức API để biểu đạt chính sách bảo mật theo những nhóm lệnh dễ đọc. **Lambda DSL** dùng lambda Java để cấu hình từng nhóm:

```java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/public/**").permitAll()
        .anyRequest().authenticated()
    )
    .csrf(Customizer.withDefaults())
    .formLogin(Customizer.withDefaults());
```

Ở đây:

- `http` là đối tượng cấu hình bảo mật của **Servlet**.
- `authorizeHttpRequests(...)` mở phần cấu hình **authorization** và nhận lambda cấu hình các matcher/rule.
- `csrf(...)` cấu hình chống CSRF; `Customizer.withDefaults()` dùng cấu hình mặc định của thành phần.
- `formLogin(...)` bật/cấu hình đăng nhập bằng biểu mẫu.
- Sau mỗi lần gọi `http.someFeature(lambda)`, API quay lại đối tượng `HttpSecurity` để tiếp tục cấu hình nhóm khác; vì vậy **không cần `.and()`**.
- Cuối cùng, `http.build()` tạo ra `SecurityFilterChain` mà Spring Security dùng khi xử lý request.

Đối tượng `ServerHttpSecurity` dùng cùng **phong cách** cấu hình, nhưng các API và kiểu kết quả khác:

```java
http
    .authorizeExchange(exchanges -> exchanges
        .pathMatchers("/public/**").permitAll()
        .anyExchange().authenticated()
    )
    .csrf(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

Lưu ý: đây là **Java lambda**, không phải Kotlin DSL. Kotlin có cú pháp DSL riêng, dù ý tưởng phân nhóm cấu hình tương tự.

### 2.2. Chained DSL cũ và Lambda DSL mới

**Kiểu cũ** từng xuất hiện trong nhiều tài liệu Spring Security 5:

```java
http
    .authorizeHttpRequests()
        .anyRequest().authenticated()
        .and()
    .formLogin()
        .and()
    .httpBasic();
```

**Kiểu Lambda DSL nên dùng:**

```java
import org.springframework.security.config.Customizer;

http
    .authorizeHttpRequests(authorize -> authorize
        .anyRequest().authenticated()
    )
    .formLogin(Customizer.withDefaults())
    .httpBasic(Customizer.withDefaults());
```

Từ Spring Security 7, phong cách cấu hình không dùng lambda của `HttpSecurity` bị loại bỏ; ứng dụng còn dùng `authorizeHttpRequests().and()` hoặc `formLogin()` không tham số sẽ cần chuyển đổi. Lambda DSL đã được hỗ trợ trong các dòng trước, nên nên hoàn thành việc chuyển cú pháp **trước** khi nâng major. Các lời gọi “không có tham số” và cơ chế dùng `.and()` là vấn đề **cú pháp cấu hình**, không tự động đồng nghĩa tính năng bị bỏ khỏi Spring Security.

| Nhu cầu | Lambda DSL đúng hướng | Điều cần tránh |
| --- | --- | --- |
| Quy tắc URL Servlet | `authorizeHttpRequests(a -> a.anyRequest().authenticated())` | `authorizeHttpRequests().anyRequest()...and()` |
| Quy tắc URL Reactive | `authorizeExchange(a -> a.anyExchange().authenticated())` | Dùng `authorizeHttpRequests` trên `ServerHttpSecurity` |
| Bật tính năng với mặc định | `httpBasic(Customizer.withDefaults())` | `httpBasic()` không tham số ở Security 7 |
| Tùy chỉnh cụ thể | `csrf(csrf -> csrf.ignoringRequestMatchers(...))` | Giữ nguyên kiểu DSL cũ rồi nối `and()` |
| Tắt tính năng có chủ đích | `csrf(csrf -> csrf.disable())` | Tắt toàn bộ CSRF chỉ để làm hết lỗi POST 403 |
| Tạo chain | `return http.build();` | Quên đăng ký bean `SecurityFilterChain` / `SecurityWebFilterChain` |

### 2.3. Ba cách dùng `Customizer` rất dễ nhầm

```java
// 1) Cấu hình feature bằng mặc định
http.httpBasic(Customizer.withDefaults());

// 2) Cấu hình feature theo yêu cầu
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives("default-src 'self'; object-src 'none'")
    )
);

// 3) Vô hiệu hóa có chủ đích (chỉ dùng khi có cơ sở bảo mật)
http.csrf(csrf -> csrf.disable());
```

`Customizer.withDefaults()` là dạng ngắn của lambda rỗng `feature -> {}`. Nó **không** có nghĩa “bật mọi cơ chế bảo mật” hay “tự sinh policy CSP”. Phải xét mặc định của **từng feature** và cấu hình của **từng filter chain**. Ví dụ, CSRF thường đã bật mặc định cho ứng dụng web, còn CSP không thể có một policy phù hợp cho mọi ứng dụng nên Spring Security không tự đặt CSP.

Tương tự, `.disable()` có nghĩa tắt **feature đang cấu hình**. `http.csrf(csrf -> csrf.disable())` tắt CSRF; `http.headers(headers -> headers.disable())` tắt các security header do Spring Security quản lý. Một lời gọi `disable()` nhỏ có thể tạo tác động bảo mật rất lớn.

## 3. Mô hình Servlet và Reactive: giống cú pháp, khác hạ tầng

```text
Servlet / Spring MVC                    Reactive / Spring WebFlux
--------------------                    --------------------------
HTTP request                            HTTP request
    |                                       |
Servlet Filter / FilterChainProxy        WebFilter / WebFilterChainProxy
    |                                       |
SecurityFilterChain                     SecurityWebFilterChain
    |                                       |
HttpSecurity                             ServerHttpSecurity
    |                                       |
authorizeHttpRequests                    authorizeExchange
    |                                       |
HttpServletRequest / HttpSession         ServerWebExchange / WebSession
    |                                       |
Controller MVC                           Handler / Controller WebFlux
```

| Khái niệm | Servlet | Reactive |
| --- | --- | --- |
| Đầu vào cấu hình | `HttpSecurity` | `ServerHttpSecurity` |
| Bean trả về | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Annotation bảo mật độc lập | `@EnableWebSecurity` | `@EnableWebFluxSecurity` |
| Quy tắc URL | `authorizeHttpRequests` + `requestMatchers` | `authorizeExchange` + `pathMatchers` |
| Chọn chain | `securityMatcher(...)` | `securityMatcher(ServerWebExchangeMatcher)` |
| Cơ sở request | `HttpServletRequest` | `ServerWebExchange` |
| Lưu ngữ cảnh/phiên | `HttpSession` và `SecurityContextRepository` Servlet | `WebSession` và `ServerSecurityContextRepository` |
| Kiểm thử | `MockMvc` + Spring Security test | `WebTestClient` + Spring Security test |

**Không sao chép nguyên mã Servlet sang Reactive.** Hai lớp cùng có `csrf`, `cors`, `headers` và `httpBasic` nhưng kiểu configurer, matcher và session repository không trùng nhau. Ứng dụng Spring Boot có thể chứa cả thư viện Web MVC và WebFlux trên classpath; hãy xác minh web application type thực sự được Boot chọn, không tự giả định cả hai cấu hình cùng chạy.

## 4. Cấu hình Servlet đầy đủ bằng `HttpSecurity`

Tình huống: ứng dụng Spring MVC có trang công khai `/public/**`, vùng quản trị `/admin/**` và các URL còn lại cần đăng nhập. Ứng dụng dùng cookie/session và nhận request từ frontend `https://app.example.com`; ta giữ CSRF, tích hợp CORS và bổ sung CSP.

### 4.1. Khai báo `SecurityFilterChain`

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;

@Configuration
@EnableWebSecurity
public class ServletHttpProtectionConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
            );

        return http.build();
    }
}
```

Đọc cấu hình theo thứ tự:

1. `authorizeHttpRequests` cấp quyền cho `/public/**` và `/error`, yêu cầu vai trò ADMIN cho `/admin/**`, còn lại phải đăng nhập.
2. `cors` bật tích hợp với nguồn chính sách CORS **nếu có**; không tự cho phép origin tùy ý.
3. `csrf` giữ cơ chế CSRF mặc định. Với form và cookie session, request thay đổi trạng thái cần CSRF token hợp lệ.
4. `headers` bổ sung CSP. Các header mặc định khác như `X-Content-Type-Options`, `X-Frame-Options`, cache control và HSTS (đối với HTTPS) vẫn được xem xét theo cách Spring Security quản lý.
5. `formLogin` cho phép flow đăng nhập bằng biểu mẫu; `logout` tùy chỉnh URL điều hướng sau logout.
6. `build()` đóng cấu hình thành một filter chain được Spring Security sử dụng ở runtime.

**Mã trên cần hạ tầng xác thực thực tế.** Trong bài tập, có thể cấu hình `UserDetailsService` cho người dùng giả lập; production cần nguồn danh tính, password encoder và chính sách phiên phù hợp. Với role `ADMIN`, Spring Security mặc định so khớp authority có tiền tố `ROLE_ADMIN`.

### 4.2. CORS phải có nguồn policy: ví dụ Servlet

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
    cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", cors);
    return source;
}
```

Đặt method này trong cùng lớp `@Configuration` hoặc một lớp `@Configuration` khác. Frontend gọi cross-origin bằng cookie cần cấu hình `credentials` ở **cả trình duyệt và server**, đồng thời chịu ràng buộc của cookie `SameSite` và HTTPS. Không dùng wildcard `*` trong `Access-Control-Allow-Origin` khi `allowCredentials=true`.

Spring MVC có cơ chế CORS riêng; khi không có bean nguồn policy, Spring Security có thể tích hợp cấu hình CORS từ MVC. Nếu có nhiều nguồn cấu hình hoặc nhiều `SecurityFilterChain`, hãy chỉ rõ nguồn nào phục vụ chain nào thay vì dựa vào cơ chế tự phát hiện.

### 4.3. Trường hợp muốn chỉ vô hiệu hóa CSRF ở một endpoint

Một webhook ngoài hệ thống không có cookie/session có thể xác thực bằng chữ ký request. Khi **đã xác nhận** nguồn xác thực độc lập và threat model, có thể loại trừ đúng đường dẫn webhook khỏi kiểm tra CSRF:

```java
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/webhooks/provider")
);
```

Đây là **ngoại lệ có điều kiện**, không đồng nghĩa webhook tự an toàn. Webhook cần xác minh chữ ký/HMAC, timestamp hoặc chống replay. `ignoringRequestMatchers` chỉ thay đổi kiểm tra **CSRF**, không tự cấp quyền; `authorizeHttpRequests` và các lớp xác thực liên quan vẫn phải được thiết kế đúng.

Không dùng `csrf(csrf -> csrf.disable())` trên toàn ứng dụng chỉ vì một API trả 403. Với ứng dụng có session cookie hoặc cơ chế xác thực trình duyệt tự gửi, việc tắt CSRF có thể mở ra cross-site request forgery.

## 5. Cấu hình Reactive đầy đủ bằng `ServerHttpSecurity`

Tình huống tương đương nhưng chạy **Spring WebFlux**. Thay các API của Servlet bằng API Reactive:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveHttpProtectionConfig {

    @Bean
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**", "/error").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Điểm giống Servlet: mỗi nhóm cấu hình dùng lambda, nhận `Customizer.withDefaults()` hoặc lambda riêng; `build()` tạo chain; kiểm tra authorization, CSRF, CORS và headers.

Điểm khác: authorization dùng `authorizeExchange`/`pathMatchers`/`anyExchange`, bean là `SecurityWebFilterChain`, ngữ cảnh request là `ServerWebExchange`. Ví dụ chọn `httpBasic` để đơn giản hóa minh họa; nếu giao diện có form login, dùng `formLogin(Customizer.withDefaults())` và kiểm tra cơ chế WebSession/CSRF phù hợp.

### 5.1. CORS source đúng package Reactive

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Bean
UrlBasedCorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration cors = new CorsConfiguration();
    cors.setAllowedOrigins(List.of("https://app.example.com"));
    cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
    cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
    cors.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/**", cors);
    return source;
}
```

Điểm dễ sai nhất là `UrlBasedCorsConfigurationSource` có **hai kiểu cùng tên ở hai package**:

- Servlet: `org.springframework.web.cors.UrlBasedCorsConfigurationSource`.
- Reactive: `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`.

Trên Reactive, `ServerHttpSecurity.cors(...)` dùng `CorsConfigurationSource` thuộc reactive package. CORS preflight cần được xử lý trước xác thực vì request `OPTIONS` preflight thường không có session cookie. Nếu không cung cấp CORS source hợp lệ, chỉ thêm `.cors(Customizer.withDefaults())` không tự tạo allowlist mong muốn.

### 5.2. CSRF và session Reactive

WebFlux dùng `WebSession` và các loại `ServerSecurityContextRepository`, không sử dụng `HttpSession`/`HttpSessionSecurityContextRepository` của Servlet. Mặc định bảo vệ CSRF vẫn có ý nghĩa cho request thay đổi trạng thái đến từ **trình duyệt**.

Một ứng dụng bearer-token API thuần túy, không dựa vào credential tự động được trình duyệt gửi, có thể đánh giá lại nhu cầu CSRF theo threat model. Ngược lại, “Reactive” hoặc “stateless” tự nó **không phải** lý do để tắt CSRF nếu frontend còn dùng cookie xác thực.

Nếu API có `httpBasic` và được dùng trực tiếp từ trình duyệt, cần chú ý một số user agent có thể tự gửi lại thông tin Basic authentication; không mặc định kết luận API này miễn nhiễm CSRF.

## 6. Phân biệt `securityMatcher` với `requestMatchers`/`pathMatchers`

Đây là lỗi vừa liên quan cú pháp, vừa có thể trở thành lỗ hổng **bỏ sót filter chain**.

**`securityMatcher` quyết định một filter chain có được chọn để xử lý request hay không.**  
**`requestMatchers` (Servlet) / `pathMatchers` (Reactive) quyết định quyền trên request _đã thuộc chain đó_.**

```text
Request GET /api/admin
        |
        v
Chain #1: securityMatcher("/api/**") ?
        | yes
        v
Chain #1: authorizeHttpRequests(...)
        | /api/admin -> hasRole("ADMIN")
        v
Authorized / 401 / 403

Nếu Chain #1 không match -> xét Chain #2 -> ...
Nếu không chain nào match -> request không được Spring Security bảo vệ.
```

### 6.1. Servlet: hai `SecurityFilterChain` có thứ tự

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class MultipleServletChains {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/login").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
```

`@Order(1)` làm chain API được xét trước. Chain `web` không có `securityMatcher`, nên mặc định match tất cả request **còn lại**. Trong ví dụ, cấu hình CSRF/headers mặc định của từng chain vẫn cần được kiểm tra theo hành vi ứng dụng; muốn CORS và CSP nhất quán phải áp dụng vào các chain tương ứng.

**Cạm bẫy 1 — URL login/logout:** nếu chỉ có chain `securityMatcher("/api/**")` mà lại bật `formLogin` ở chain đó, các endpoint `/login` do filter cung cấp có thể **không nằm trong matcher** và không hoạt động như kỳ vọng. Cần có chain phù hợp hoặc tùy chỉnh URL login để thuộc phạm vi chain.

**Cạm bẫy 2 — tưởng “permitAll” là bỏ qua Security:** `permitAll()` cho phép truy cập theo rule nhưng request vẫn qua filter chain để nhận headers, CSRF (nếu áp dụng), logging, v.v. “Không chain nào match” lại là trường hợp khác và có thể để request đi qua mà không chịu bảo vệ Spring Security.

**Cạm bẫy 3 — thứ tự rule:** đưa một matcher rộng vào trước có thể che matcher hẹp phía sau. Chẳng hạn `requestMatchers("/**").permitAll()` trước `requestMatchers("/admin/**").hasRole("ADMIN")` sẽ phá ý định bảo vệ admin.

### 6.2. Reactive: dùng `ServerWebExchangeMatcher`

```java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Bean
@Order(1)
SecurityWebFilterChain reactiveApi(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityWebFilterChain reactiveFallback(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đặt hai bean này trong một lớp `@Configuration` có `@EnableWebFluxSecurity` (hoặc cấu hình tương đương của ứng dụng). Cơ chế xét chain cũng dựa trên matcher và `@Order`; chỉ một `SecurityWebFilterChain` phù hợp được chọn cho mỗi exchange.

## 7. Các lớp HTTP protection trong Lambda DSL

### 7.1. CSRF: cấu hình đúng với cách client xác thực

**Mục tiêu:** ngăn website bên ngoài tận dụng cookie/credential mà browser tự đính kèm để gửi một thao tác thay đổi dữ liệu thay mặt người dùng.

| Tình huống | Hướng xử lý |
| --- | --- |
| Web MVC có session, form POST, cookie đăng nhập | Giữ CSRF mặc định, đưa token vào form/header |
| WebFlux có cookie và POST JSON | Giữ CSRF, cung cấp token để frontend gửi bằng header |
| API bearer token trong `Authorization` header do client chủ động gửi, không cookie | Có thể đánh giá miễn CSRF theo threat model và cơ chế xác thực thực tế |
| Webhook có chữ ký HMAC và không cookie | Cân nhắc `ignoringRequestMatchers` hẹp (Servlet) hoặc matcher loại trừ tương ứng của Reactive |
| Bị HTTP 403 khi POST | Kiểm tra CSRF token, authentication và authorization trước khi thay security config |

Không kết luận “REST API thì không cần CSRF” chỉ từ tên giao thức. Một REST endpoint gọi bằng browser với cookie session vẫn có thể bị CSRF.

### 7.2. CORS: khác origin và thứ tự xử lý

CORS là chính sách do **trình duyệt** thực thi để kiểm soát truy cập khác origin; Spring Security hỗ trợ trả các CORS header phù hợp. Khi dùng cookie cross-origin, allowlist cần chặt chẽ và cho phép credentials có chủ đích.

Ví dụ kiểm tra preflight:

```http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Response hợp lệ cho origin cho phép có thể chứa `Access-Control-Allow-Origin: https://app.example.com`, `Access-Control-Allow-Methods` và các header tương ứng. Response cho `https://attacker.example` phải **không** cho phép origin đó. Nên kiểm tra bằng request thật, không chỉ kiểm tra rằng code có `.cors(...)`.

**CORS không thay thế authorization hoặc CSRF.** Ngay cả khi trình duyệt chặn JavaScript đọc response, một số request vẫn có thể được gửi tới server; chính sách CSRF tiếp tục có nhiệm vụ riêng.

### 7.3. Security headers, CSP và HSTS

Lambda DSL cho phép thêm CSP trong nhóm `headers`:

```java
// HttpSecurity hoặc ServerHttpSecurity đều có phong cách tương tự:
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
        )
    )
);
```

Chính sách mẫu áp dụng tốt cho trang đơn giản chỉ tải nội dung cùng origin; ứng dụng có CDN, nonce, script inline hoặc iframe hợp lệ phải thiết kế policy riêng. Trước khi enforce ở production, có thể dùng **CSP Report-Only** để quan sát vi phạm.

Spring Security có các security headers mặc định nhưng **không đặt CSP mặc định**. Header `Strict-Transport-Security` (HSTS) chỉ có ý nghĩa khi client truy cập qua **HTTPS**; với TLS terminate tại reverse proxy cần kiểm tra forwarded headers, trust proxy và response quan sát từ phía người dùng.

Không bật `includeSubDomains`/`preload` tùy tiện trước khi xác nhận mọi subdomain thực sự phục vụ HTTPS đúng cách. Dù cú pháp Lambda DSL ngắn, quyết định HSTS là quyết định vận hành có hậu quả lâu dài.

### 7.4. HTTP firewall: không đồng nhất với quyền truy cập

Trong Servlet, `StrictHttpFirewall` (thường dùng mặc định thông qua Spring Security) kiểm soát cấu trúc request bất thường trước khi authorization matcher được xét. Trường hợp điển hình gồm URL chứa dấu phân cách, path encoding hoặc pattern đáng ngờ.

Không xử lý `RequestRejectedException` bằng cách nới firewall đồng loạt như “allow all semicolon” khi chưa xác định nguồn URL bất thường. Cần kiểm tra routing, reverse proxy, Servlet container và cách frontend encode URL; chỉ nới theo trường hợp được đánh giá rủi ro cụ thể.

Reactive có hạ tầng firewall/exchange matcher riêng; đừng bê nguyên `StrictHttpFirewall` Servlet vào `ServerHttpSecurity`. Kiểm thử URL kỳ lạ với **đúng web stack** giúp phát hiện khác biệt khi nâng phiên bản.

### 7.5. Session, logout và trạng thái bảo mật

Ở Servlet, cấu hình phiên có thể được tổ chức bằng `sessionManagement`:

```java
import org.springframework.security.config.http.SessionCreationPolicy;

// Chỉ dành cho API độc lập, không đăng nhập bằng cookie/session:
http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
```

`STATELESS` nghĩa là Spring Security không tạo/đọc `HttpSession` để lấy `SecurityContext` trong mô hình API đó; nó **không** tự bảo đảm mọi component của ứng dụng không tạo session hoặc không tạo cookie. Với ứng dụng giao diện có form login, sử dụng `STATELESS` một cách máy móc có thể làm login không được duy trì.

Reactive dùng `WebSession` và `ServerSecurityContextRepository`. Nếu thiết kế bearer token không lưu context trong phiên, xem xét repository/logic authentication phù hợp; không dùng `SessionCreationPolicy` của Servlet trong `ServerHttpSecurity`.

Sau thay đổi DSL, cần kiểm thử **logout xóa trạng thái xác thực**, session fixation, cookie `Secure`/`HttpOnly`/`SameSite`, timeout, remember-me và hành vi nhiều thiết bị theo yêu cầu sản phẩm. Không xem việc code build thành công là bằng chứng bảo vệ session còn đúng.

## 8. Ví dụ chuyển đổi một cấu hình hiện hữu sang Lambda DSL

Giả sử mã cũ:

```java
// Phong cách cũ, chỉ dùng làm ví dụ migration
http
    .authorizeHttpRequests()
        .requestMatchers("/health").permitAll()
        .anyRequest().authenticated()
        .and()
    .csrf()
        .and()
    .headers()
        .frameOptions().sameOrigin()
        .and()
        .and()
    .formLogin();
```

Phiên bản Lambda DSL tương đương về **ý định**:

```java
http
    .authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/health").permitAll()
        .anyRequest().authenticated()
    )
    .csrf(Customizer.withDefaults())
    .headers(headers -> headers
        .frameOptions(frameOptions -> frameOptions.sameOrigin())
    )
    .formLogin(Customizer.withDefaults());
```

Các bước chuyển đổi thực tế:

1. Tìm tất cả lời gọi cấu hình cũ: `.authorizeHttpRequests()`, `.formLogin()`, `.httpBasic()`, `.csrf()`, `.headers()` và `.and()`.
2. Thay bằng các overload nhận lambda hoặc `Customizer.withDefaults()`; bảo toàn các giá trị cấu hình trước đó.
3. Kiểm tra method/kiểu configurer thay đổi giữa major (ví dụ khái niệm request matcher, path matcher, Jackson/session integration).
4. Xác nhận loại chain đúng: `SecurityFilterChain` cho Servlet, `SecurityWebFilterChain` cho Reactive.
5. Đọc log khởi động của Spring Security và kiểm thử HTTP thực tế, nhất là request bất thường, CSRF, CORS và header.

Với `frameOptions().sameOrigin()`, không nên suy rằng “chuyển cú pháp thì chính sách iframe tự tốt hơn”. `SAMEORIGIN` cho phép nhúng trong iframe cùng origin; nếu ứng dụng không có nhu cầu này, nên cân nhắc chính sách `DENY`/CSP `frame-ancestors` phù hợp.

## 9. Kiểm thử Lambda DSL: chứng minh đúng hành vi bảo mật

Nhìn vào đoạn cấu hình không đủ để xác nhận filter chain đã bảo vệ request như mong muốn. Cần kiểm thử **cả đường đi được cho phép lẫn đường đi bị chặn**.

### 9.1. Một bộ kiểm thử cần có

| Kịch bản | Request ví dụ | Kỳ vọng |
| --- | --- | --- |
| Public endpoint | GET `/public/ping`, không đăng nhập | Được phép truy cập, endpoint tồn tại |
| Private endpoint | GET `/account`, không đăng nhập | 401 hoặc redirect login tùy entry point |
| Admin endpoint | GET `/admin/reports`, user không có vai trò ADMIN | 403 khi đã xác thực nhưng không đủ quyền |
| CSRF thất bại | POST `/submit` có session, thiếu token | 403 (sau khi xác thực) |
| CSRF hợp lệ | POST `/submit` có session, token hợp lệ | Qua bước CSRF và xử lý theo quyền |
| CORS hợp lệ | OPTIONS `/api/**` từ origin allowlist | Preflight được phản hồi đúng CORS headers |
| CORS bị từ chối | OPTIONS từ origin ngoài allowlist | Không cấp quyền CORS cho origin đó |
| CSP | GET trang HTML | Có header CSP như thiết kế |
| HSTS | GET HTTPS qua proxy công khai | Header HSTS theo chính sách |
| Firewall | URL có encoding/path bất thường | Bị từ chối hoặc chuẩn hóa có kiểm soát |
| Nhiều chain | URL thuộc `/api/**` và URL ngoài `/api/**` | Trúng đúng chain, quyền không rò rỉ |
| Session/logout | Login → request → logout → request | Session/context bị vô hiệu hóa phù hợp |

Kết quả “401 hay redirect” phụ thuộc `httpBasic`, `formLogin`, `exceptionHandling` và cách client gửi `Accept`. Tương tự, 403 từ authorization và 403 từ CSRF khác nguyên nhân; nên thu thập log/exception trước khi sửa config.

### 9.2. Servlet: kiểm tra CSRF với `MockMvc`

Với `MockMvc` đã được tích hợp `springSecurity()`, giả sử có endpoint `POST /submit` chỉ yêu cầu user đăng nhập và trả HTTP 200 nếu được xử lý thành công:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void browserPostNeedsCsrfToken() throws Exception {
    mvc.perform(post("/submit").with(user("alice")))
       .andExpect(status().isForbidden());

    mvc.perform(post("/submit").with(user("alice")).with(csrf()))
       .andExpect(status().isOk());
}
```

Ví dụ là phần thân một test đã có `MockMvc mvc`, fixture và controller thích hợp. `with(user(...))` chỉ mô phỏng principal trong test; `with(csrf())` gắn token hợp lệ. Nếu cần kiểm tra token sai, dùng `with(csrf().useInvalidToken())`. Nếu endpoint trả 201/204, chỉnh expectation theo hợp đồng HTTP thực tế.

### 9.3. Reactive: kiểm tra với `WebTestClient`

Với `WebTestClient` đã bind vào `ApplicationContext` và áp dụng `springSecurity()`:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void reactivePostNeedsCsrfToken() {
    client.mutateWith(mockUser("alice"))
        .post().uri("/submit")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("alice"))
        .mutateWith(csrf())
        .post().uri("/submit")
        .exchange()
        .expectStatus().isOk();
}
```

Để tạo một client kiểm thử theo tài liệu Spring Security:

```java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
```

Ví dụ giả định ứng dụng Reactive có endpoint `POST /submit` và mock user được cho phép. Nếu bạn đang gọi một server qua HTTP thật, `mockUser()` không tự biến thành phiên đăng nhập trên server từ xa; cần dùng cơ chế xác thực thật phù hợp hoặc cấu hình test bind-to-context.

### 9.4. Test CORS và headers với request thật

Có thể kiểm tra ở mức HTTP:

```bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"

curl -i "https://app.example.com/"  # kiểm tra CSP và HSTS trên HTTPS
```

Lặp lại preflight với một origin không được phép và xác nhận server không cấp `Access-Control-Allow-Origin` cho origin đó. Với HSTS, kiểm tra trên URL công khai sau proxy/TLS; request HTTP vào backend nội bộ có thể không phát HSTS, kể cả khi hệ thống production được cấu hình đúng.

## 10. Chẩn đoán lỗi thường gặp khi dùng Lambda DSL

### Lỗi 1: `Cannot resolve method and()` hoặc lỗi compile sau nâng Spring Security

**Nguyên nhân thường gặp:** mã dùng chain API kiểu cũ sau khi chuyển lên phiên bản yêu cầu Lambda DSL; hoặc cố dùng method Servlet trên kiểu Reactive.

**Xử lý:** đổi từng nhóm sang `http.authorizeHttpRequests(a -> ...)`, `http.formLogin(Customizer.withDefaults())`, v.v.; xóa `.and()` và xác định kiểu `http` đang là `HttpSecurity` hay `ServerHttpSecurity`.

### Lỗi 2: Thêm `cors(Customizer.withDefaults())` nhưng preflight vẫn 401/403

**Nguyên nhân có thể:** không có `CorsConfigurationSource` đúng package, origin/method/header không khớp, nhiều source gây mơ hồ, proxy chặn `OPTIONS` trước Spring Security, hoặc thứ tự xử lý CORS có vấn đề.

**Xử lý:** kiểm tra preflight có `Origin` và `Access-Control-Request-Method`, đọc response CORS headers và kiểm tra chain được chọn. Trên Servlet/WebFlux dùng đúng nguồn CORS như ở mục 4.2/5.1.

### Lỗi 3: GET chạy nhưng POST bị 403

**Nguyên nhân có thể:** thiếu CSRF token, token gắn với session cũ, cookie không đi qua proxy, hoặc quyền của user không đủ.

**Xử lý:** thử test có token đúng và token sai; kiểm tra exception CSRF và authorization; rà soát session cookie, HTTPS và SameSite. Chỉ thay `csrf` sau khi xác định threat model.

### Lỗi 4: URL `/admin` bị truy cập dù đã cấu hình `hasRole("ADMIN")`

**Nguyên nhân có thể:** một chain được ưu tiên trước có matcher quá rộng; một chain khác kết thúc bằng `permitAll`; hoặc request không match **bất cứ** chain nào.

**Xử lý:** liệt kê bean chain và `@Order`, so sánh `securityMatcher` với matcher phân quyền bên trong, test trực tiếp các URL biên, bao gồm dấu slash/encoded path. Đặt fallback chain bao phủ các URL còn lại.

### Lỗi 5: Cấu hình CSP nhưng header không xuất hiện

**Nguyên nhân có thể:** request vào chain khác, `headers` bị tắt, CSP được cấu hình ở một nhánh không match hoặc response được trả từ proxy/cache.

**Xử lý:** kiểm tra chain, response tại cổng public, cache/proxy và chính xác header `Content-Security-Policy` hoặc `Content-Security-Policy-Report-Only`. Đừng mặc định Spring Security tự sinh CSP khi chỉ bật `headers`.

### Lỗi 6: Chuyển API sang `STATELESS` làm đăng nhập xong vẫn bị xem là chưa đăng nhập

**Nguyên nhân có thể:** chính sách không dùng `HttpSession` cho `SecurityContext` không tương thích với flow form login đã triển khai.

**Xử lý:** phân biệt ứng dụng browser session với bearer API; thiết kế authentication/context repository cho đúng stack; kiểm tra hành vi đăng nhập, logout, timeout và cookie.

## 11. Bài tập thực hành có tiêu chí hoàn thành

**Bài 1 — Chuyển cú pháp cũ.** Chuyển đoạn mã sau sang Lambda DSL:

```java
http
    .authorizeHttpRequests()
        .requestMatchers("/docs/**").permitAll()
        .anyRequest().hasRole("USER")
        .and()
    .httpBasic()
        .and()
    .csrf();
```

**Yêu cầu:** không dùng `.and()`, vẫn để `/docs/**` truy cập công khai và phần còn lại yêu cầu USER. Xác định rõ việc cho phép tài liệu công khai **không** đồng nghĩa tắt CSRF toàn cục.

**Gợi ý lời giải:**

```java
http
    .authorizeHttpRequests(a -> a
        .requestMatchers("/docs/**").permitAll()
        .anyRequest().hasRole("USER")
    )
    .httpBasic(Customizer.withDefaults())
    .csrf(Customizer.withDefaults());
```

**Bài 2 — Hai stack, một chính sách.** Tạo hai ứng dụng độc lập (Servlet và Reactive) có `/health` công khai, `/admin/**` dành cho ADMIN và mọi route còn lại phải xác thực. Thêm CSP `default-src 'self'; object-src 'none'` và CORS cho đúng một origin HTTPS. Dùng `MockMvc` và `WebTestClient` để chứng minh kết quả tương đương ở cấp hành vi.

**Bài 3 — Tìm lỗi lọt chain.** Một ứng dụng chỉ có chain `securityMatcher("/api/**")` và không có chain nào khác. Endpoint `/admin/reports` không nằm dưới `/api/**`. Hãy giải thích liệu `anyRequest().authenticated()` trong chain API có bảo vệ endpoint admin hay không, và đưa ra cấu hình fallback chain.

**Bài 4 — Điều tra một lỗi 403 sau nâng cấp.** Request POST từ trình duyệt dùng cookie session đột nhiên trả 403 sau khi chuyển sang Lambda DSL. Bạn cần ít nhất ba phép kiểm tra độc lập để phân biệt CSRF, CORS và authorization; không giải quyết bằng cách tắt cả CSRF/CORS.

## 12. Checklist trước khi đưa Lambda DSL lên production

- [ ] Xác nhận phiên bản Spring Boot/Spring Security được resolve và hoàn tất chuyển API cũ theo migration guide.
- [ ] Chọn đúng `HttpSecurity`/`SecurityFilterChain` hoặc `ServerHttpSecurity`/`SecurityWebFilterChain`.
- [ ] Không còn `.and()` và các lời gọi cấu hình không tham số đã bị loại bỏ.
- [ ] Hiểu đầy đủ `Customizer.withDefaults()`, mọi cấu hình `disable()` và các ngoại lệ security.
- [ ] Thứ tự `@Order`, `securityMatcher` và matcher phân quyền đã được kiểm tra; có fallback chain phù hợp.
- [ ] CSRF hoạt động cho request trình duyệt dùng credential tự động; các ngoại lệ được giới hạn và có lớp xác thực riêng.
- [ ] CORS trả lời đúng preflight với origin được phép và không cho phép origin lạ.
- [ ] CSP/headers/HSTS kiểm tra trên HTTPS thực tế, xét đến reverse proxy.
- [ ] Test URL có encoding bất thường, firewall và session/logout sau migration.
- [ ] Các trường hợp 401/403 và redirect login có test để bảo đảm hành vi bảo mật không đổi ngoài chủ đích.

## Nguồn tham khảo chính thức

1. [Spring Security: Configuration Migrations, Lambda DSL](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html) — lý do chuyển sang lambda, cách viết `Customizer.withDefaults()`, thay thế `.and()` và yêu cầu của Spring Security 7.
2. [Spring Security: Servlet Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) — bean `SecurityFilterChain`, nhiều chain, phân biệt `securityMatcher` và `requestMatchers`.
3. [Spring Security: WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `ServerHttpSecurity`, `SecurityWebFilterChain`, nhiều chain và Reactive customization.
4. [Spring Security: Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html) và [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — nguồn CORS và thứ tự xử lý preflight.
5. [Spring Security: Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) và [Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — cách bảo vệ request thay đổi trạng thái, token và ngoại lệ.
6. [Spring Security: Servlet Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) và [Reactive Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — security headers, CSP và HSTS.
7. [Spring Security: Servlet MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html), [Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) và [Reactive CSRF Test](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — kiểm thử hiệu lực cấu hình.

**Câu hỏi tự đánh giá:** “`csrf(Customizer.withDefaults())` khác gì `csrf(csrf -> csrf.disable())`? Vì sao `securityMatcher("/api/**")` không bảo vệ `/admin/**` dù bên trong có `anyRequest().authenticated()`? Cần đổi những API nào khi chuyển cấu hình Servlet sang Reactive?”
