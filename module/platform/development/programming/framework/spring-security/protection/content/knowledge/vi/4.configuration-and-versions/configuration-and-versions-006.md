# Tách cấu hình dùng chung khỏi phần riêng cho Servlet hoặc Reactive

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Phạm vi:** Tổ chức cấu hình phòng vệ HTTP và trình duyệt trong Spring Security thành **chính sách dùng chung** và **bộ chuyển đổi theo web stack**. Các cơ chế cần xét gồm CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session, xác thực và phân quyền cho Servlet/Spring MVC lẫn Reactive/WebFlux.  
> **Mốc tham chiếu:** 26/11/2026; ví dụ Java dùng Lambda DSL, phù hợp về phong cách với các dòng Spring Security 6.5/7.x. Khi sao chép vào ứng dụng, kiểm tra API, package và cấu hình thực tế của phiên bản Spring Boot/Spring Security đang sử dụng.

## 1. Vì sao cần tách hai phần cấu hình?

Một tổ chức có hai dịch vụ:

- **Dịch vụ A:** Spring MVC/Servlet, dùng cookie đăng nhập, controller đồng bộ, `SecurityFilterChain`.
- **Dịch vụ B:** Spring WebFlux/Reactive, có WebSession hoặc token theo thiết kế, handler không chặn luồng, `SecurityWebFilterChain`.

Cả hai đều cần chính sách: URL công khai phải thật sự công khai; `/admin/**` yêu cầu vai trò ADMIN; chỉ frontend `https://app.example.com` được gọi API từ trình duyệt; nội dung HTML phải có CSP; request dùng cookie không được bỏ qua CSRF; HTTPS cần HSTS và session phải được quản lý an toàn.

Nếu sao chép nguyên lớp `HttpSecurity` từ MVC sang WebFlux, dự án sẽ dùng nhầm API hoặc cấu hình có vẻ giống nhưng không hiệu lực. Nếu tạo một “lớp bảo mật chung” dùng cả `HttpSecurity` và `ServerHttpSecurity`, lớp này buộc phụ thuộc cả hai stack, khó kiểm thử và dễ tạo những bean không đúng môi trường.

**Hướng tổ chức bền vững:** chia thành **quyết định bảo mật chung** (*what*) và **cách thi hành theo HTTP stack** (*how*).

```text
                     QUYẾT ĐỊNH CHUNG
       +---------------------------------------------+
       | Allowed origins, CSP directives             |
       | Public/admin URL intent, roles/authorities  |
       | Browser-session policy, HTTPS requirements  |
       | Threat model và tiêu chí kiểm thử           |
       +----------------------+----------------------+
                              |
                   Pure Java policy object
                              |
                 +------------+------------+
                 |                         |
                 v                         v
          SERVLET ADAPTER             REACTIVE ADAPTER
       HttpSecurity                   ServerHttpSecurity
       SecurityFilterChain            SecurityWebFilterChain
       RequestMatcher                 ServerWebExchangeMatcher
       CsrfTokenRepository            ServerCsrfTokenRepository
       Servlet CorsSource             Reactive CorsSource
       HttpSession                    WebSession
       HttpFirewall                   ServerWebExchangeFirewall
                 |                         |
                 v                         v
          MockMvc / HTTP test          WebTestClient / HTTP test
                 +------------+------------+
                              |
                  CÙNG HỢP ĐỒNG BẢO MẬT
```

### Người học cần đạt được

1. Xác định thành phần nào có thể dùng chung **giá trị và quyết định**, thành phần nào phải có **triển khai riêng**.
2. Định nghĩa policy thuần Java cho origin, CSP, URL và quyền; áp dụng nó vào `HttpSecurity` hoặc `ServerHttpSecurity`.
3. Cấu hình đúng bean `SecurityFilterChain`/`SecurityWebFilterChain` và CORS source của từng stack.
4. Giải thích vì sao CSRF repository, session repository, HTTP firewall và authentication manager không thể dùng thay cho nhau.
5. Kiểm thử được **hành vi tương đương** dù hai stack có HTTP status, entry point và cách lưu phiên khác nhau.
6. Tránh sai lệch cấu hình khi nâng Spring Security hoặc tách một dịch vụ MVC thành một dịch vụ WebFlux.

## 2. Bảng ranh giới: dùng chung điều gì, tách riêng điều gì?

| Khía cạnh | Có thể dùng chung | Phải giữ ở adapter Servlet/Reactive |
| --- | --- | --- |
| Quyền truy cập | Vai trò `ADMIN`, nguyên tắc deny-by-default, URL nghiệp vụ công khai | `authorizeHttpRequests`/`requestMatchers` so với `authorizeExchange`/`pathMatchers` |
| Phạm vi security chain | Ý định bảo vệ mọi endpoint; phân nhóm web/API | `SecurityFilterChain`/`RequestMatcher` so với `SecurityWebFilterChain`/`ServerWebExchangeMatcher` |
| CORS | Danh sách origin, method, header, cho phép credentials hay không | `org.springframework.web.cors.UrlBasedCorsConfigurationSource` so với `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource` |
| CSRF | Quyết định giữ CSRF cho client dùng credential tự động | `CsrfFilter`/`HttpSessionCsrfTokenRepository` so với `CsrfWebFilter`/`WebSessionServerCsrfTokenRepository` |
| CSP / headers | Chuỗi policy CSP, mục tiêu clickjacking/cache/mime-sniffing | Header configurer của `HttpSecurity` và `ServerHttpSecurity` |
| HSTS / HTTPS | Yêu cầu truy cập HTTPS, thời gian HSTS, phạm vi subdomain | Cách ghi header/redirect và tích hợp proxy theo stack |
| Identity | Mô hình user, role/permission, quy tắc băm mật khẩu | `UserDetailsService`/`AuthenticationManager` so với `ReactiveUserDetailsService`/`ReactiveAuthenticationManager` |
| Session | Quy tắc timeout, logout, không tái sử dụng phiên sau đổi quyền | `HttpSession`/`SecurityContextRepository` so với `WebSession`/`ServerSecurityContextRepository` |
| HTTP firewall | Chủ trương từ chối URL nguy hiểm, không nới URL parser tùy tiện | `StrictHttpFirewall` so với `StrictServerWebExchangeFirewall` |
| Kiểm thử | Danh sách kịch bản công khai/admin/CSRF/CORS/CSP/HSTS | `MockMvc` so với `WebTestClient`, cả hai cần test HTTPS/proxy thực |

**Nguyên tắc thực hành:** Dùng chung **dữ liệu chính sách, tên quyền và hợp đồng bảo mật**; chỉ dùng chung code framework khi nó thực sự không phụ thuộc cách xử lý request. Không tạo một `SecurityFilterChain` rồi mong WebFlux sử dụng nó, hay lấy `HttpSessionCsrfTokenRepository` làm repository Reactive.

## 3. Thiết kế một policy dùng chung không phụ thuộc web stack

Một cách rõ ràng là đặt các quyết định ổn định vào lớp Java không import `jakarta.servlet.*`, `org.springframework.security.web.*` hay `org.springframework.web.server.*`.

### 3.1. `BrowserProtectionPolicy`: record Java 17

```java
package com.example.security.policy;

import java.util.List;
import java.util.Objects;

public record BrowserProtectionPolicy(
        List<String> allowedOrigins,
        List<String> allowedCorsMethods,
        List<String> allowedCorsHeaders,
        boolean allowCredentials,
        String publicPath,
        String adminPath,
        String adminRole,
        String cspDirectives) {

    public BrowserProtectionPolicy {
        allowedOrigins = List.copyOf(
            Objects.requireNonNull(allowedOrigins));
        allowedCorsMethods = List.copyOf(
            Objects.requireNonNull(allowedCorsMethods));
        allowedCorsHeaders = List.copyOf(
            Objects.requireNonNull(allowedCorsHeaders));
        Objects.requireNonNull(publicPath);
        Objects.requireNonNull(adminPath);
        Objects.requireNonNull(adminRole);
        Objects.requireNonNull(cspDirectives);
    }
}
```

Đây là model **policy**, không phải một filter. Java `record` yêu cầu Java 16+; ví dụ hướng tới môi trường Java 17 trở lên của Spring Boot 3/4. Kiểu danh sách được tạo bản sao `List.copyOf` để các cấu hình Servlet/Reactive không thể vô tình sửa nội dung gốc khi build CORS source.

### 3.2. Tạo cùng dữ liệu policy ở mỗi ứng dụng

```java
package com.example.security.policy;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SharedPolicyConfiguration {

    @Bean
    BrowserProtectionPolicy browserProtectionPolicy() {
        return new BrowserProtectionPolicy(
            List.of("https://app.example.com"),
            List.of("GET", "POST", "PUT", "DELETE"),
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"),
            true,
            "/public/**",
            "/admin/**",
            "ADMIN",
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
        );
    }
}
```

Ở môi trường thật, có thể nạp `allowedOrigins` và các giá trị cấu hình từ property đã validate thay vì hard-code. Không tự động nhận mọi origin từ request rồi đưa lại vào `Access-Control-Allow-Origin`, và không kết hợp wildcard `*` với `allowCredentials=true`.

**Lưu ý:** chuỗi `publicPath`/`adminPath` chỉ là **ý định ứng dụng** khi hai hệ thống có cùng layout URL. Servlet 7 có thể dùng `PathPatternRequestMatcher` và servlet path riêng; Reactive dùng `ServerWebExchangeMatcher`. Nếu tuyến đường khác nhau, lưu *định danh route hoặc hợp đồng quyền* ở model chung rồi ánh xạ thành đường dẫn trong từng adapter. Không giả định mọi pattern của hai parser có ngữ nghĩa giống hệt nhau.

### 3.3. Những gì không nên nhét vào record này

Không thêm các trường kiểu `HttpSecurity`, `ServerHttpSecurity`, `CsrfTokenRepository`, `CorsConfigurationSource`, `SecurityFilterChain` hoặc đối tượng session. Chúng là API hạ tầng theo từng stack và thường có vòng đời do Spring quản lý. Một cấu hình “chung” nhưng import cả Spring MVC và WebFlux dễ làm code chỉ chạy đúng trong một application type mà không ai nhận ra.

Cũng không nên biến một policy object thành nơi chứa mọi công tắc như `disableCsrf`, `ignoreEverything`, `allowAllCors` chỉ để thống nhất cú pháp. Những quyết định có rủi ro như tắt CSRF phải có **threat model và ngoại lệ rõ ràng**, không trở thành giá trị mặc định lan sang nhiều dịch vụ.

## 4. Adapter Servlet: ánh xạ policy vào `HttpSecurity`

Ứng dụng **Spring MVC/Servlet** tạo `SecurityFilterChain` và Servlet CORS source. Các ví dụ ở mục 4 và mục 5 là **hai ứng dụng riêng**, dùng cùng lớp `BrowserProtectionPolicy` chứ không đăng ký đồng thời hai web stacks.

### 4.1. Cấu hình bảo mật Servlet

```java
package com.example.security.servlet;

import com.example.security.policy.BrowserProtectionPolicy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebSecurity
public class ServletProtectionConfiguration {

    @Bean
    SecurityFilterChain browserChain(
            HttpSecurity http,
            BrowserProtectionPolicy policy,
            UrlBasedCorsConfigurationSource servletCorsSource)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(policy.publicPath()).permitAll()
                .requestMatchers(policy.adminPath())
                    .hasRole(policy.adminRole())
                .anyRequest().authenticated()
            )
            .cors(cors -> cors
                .configurationSource(servletCorsSource)
            )
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(policy.cspDirectives())
                )
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

Đoạn trên có một chain bao phủ toàn bộ URL nếu không có `securityMatcher` hẹp hơn. `requestMatchers` kiểm tra quyền **bên trong chain**, còn `permitAll` chỉ bỏ qua yêu cầu phân quyền. Mặc dù `/public/**` là công khai, một request POST vào đây vẫn có thể cần CSRF token nếu dùng browser cookie/session.

`hasRole("ADMIN")` thường so khớp authority `ROLE_ADMIN` (trừ khi ứng dụng đổi cấu hình tiền tố). Nếu hệ thống có phân quyền phức tạp hơn, chuẩn hóa **tên quyền/role** ở miền nghiệp vụ và áp dụng rule theo từng stack; đừng lặp tên quyền tùy tiện trong mọi controller.

### 4.2. CORS source riêng cho Servlet

```java
package com.example.security.servlet;

import com.example.security.policy.BrowserProtectionPolicy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class ServletCorsConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource servletCorsSource(
            BrowserProtectionPolicy policy) {

        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(policy.allowedOrigins());
        config.setAllowedMethods(policy.allowedCorsMethods());
        config.setAllowedHeaders(policy.allowedCorsHeaders());
        config.setAllowCredentials(policy.allowCredentials());

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
```

Ở Servlet, package chính xác là `org.springframework.web.cors.UrlBasedCorsConfigurationSource`. Bean được inject **tường minh** vào `.cors(...)` nên không phụ thuộc chuyện Spring Security tự chọn source nào khi ứng dụng có nhiều `CorsConfigurationSource`.

**CORS là policy của trình duyệt.** Trả đúng `Access-Control-Allow-Origin` không xác thực người dùng, không cấp quyền ADMIN và không vô hiệu CSRF. Preflight `OPTIONS` thường không kèm cookie nên phải được xử lý trước khi bộ lọc authentication chặn request.

### 4.3. Những cấu hình khác vẫn thuộc Servlet adapter

| Cơ chế | Servlet API | Tại sao giữ riêng? |
| --- | --- | --- |
| CSRF repository mặc định | `HttpSessionCsrfTokenRepository` | Dùng `HttpSession`, không tồn tại trên WebFlux |
| Thực thi security filter chain | `FilterChainProxy`, `SecurityFilterChain` | Phụ thuộc Servlet `Filter` và `HttpServletRequest` |
| Session | `HttpSession`, `SessionCreationPolicy` | Reactivity/WebSession không có các API này |
| HTTP firewall | `StrictHttpFirewall` | Kiểm soát `HttpServletRequest` và servlet path |
| Custom request matcher | `RequestMatcher` | Khớp Servlet request, context/servlet path |
| Form login/logout | `HttpSecurity.formLogin`/`logout` | Lưu/truy xuất `SecurityContext` qua cơ chế Servlet |

Nếu ứng dụng có form login và cookie, đừng tự thêm `SessionCreationPolicy.STATELESS` chỉ vì một API khác dùng bearer token. Cần tách **API chain** và **browser chain** nếu chúng có threat model hoặc cơ chế authentication khác nhau.

## 5. Adapter Reactive: áp cùng policy bằng `ServerHttpSecurity`

Ứng dụng WebFlux khác sử dụng **chính record policy ở mục 3**, nhưng tự tạo `SecurityWebFilterChain` và **Reactive CORS source**.

### 5.1. Cấu hình bảo mật Reactive

```java
package com.example.security.reactive;

import com.example.security.policy.BrowserProtectionPolicy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class ReactiveProtectionConfiguration {

    @Bean
    SecurityWebFilterChain browserChain(
            ServerHttpSecurity http,
            BrowserProtectionPolicy policy,
            UrlBasedCorsConfigurationSource reactiveCorsSource) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(policy.publicPath()).permitAll()
                .pathMatchers(policy.adminPath())
                    .hasRole(policy.adminRole())
                .anyExchange().authenticated()
            )
            .cors(cors -> cors
                .configurationSource(reactiveCorsSource)
            )
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(policy.cspDirectives())
                )
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Trong WebFlux, method `authorizeExchange` và `pathMatchers` thay cho `authorizeHttpRequests` và `requestMatchers`. Bean trả về `SecurityWebFilterChain`. Với `formLogin`, người dùng có thể duy trì ngữ cảnh xác thực trong `WebSession` theo cấu hình Reactive; không sử dụng Servlet `HttpSession`.

### 5.2. CORS source riêng cho Reactive

```java
package com.example.security.reactive;

import com.example.security.policy.BrowserProtectionPolicy;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveCorsConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource reactiveCorsSource(
            BrowserProtectionPolicy policy) {

        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(policy.allowedOrigins());
        config.setAllowedMethods(policy.allowedCorsMethods());
        config.setAllowedHeaders(policy.allowedCorsHeaders());
        config.setAllowCredentials(policy.allowCredentials());

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", config);
        return source;
    }
}
```

So với code Servlet, **logic policy** giống nhau nhưng import đã đổi sang `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`. Hai class trùng tên từ hai package **không** cùng kiểu. `ServerHttpSecurity.CorsSpec.configurationSource(...)` nhận `org.springframework.web.cors.reactive.CorsConfigurationSource`; truyền bản Servlet vào đây sẽ sai kiểu.

### 5.3. Những cơ chế chỉ có ý nghĩa với Reactive

| Cơ chế | Reactive API | Không nhầm với |
| --- | --- | --- |
| Security chain | `SecurityWebFilterChain`, `WebFilterChainProxy` | Servlet `SecurityFilterChain`/`FilterChainProxy` |
| Request matcher | `ServerWebExchangeMatcher` | Servlet `RequestMatcher` |
| CSRF | `CsrfWebFilter`, `ServerCsrfTokenRepository` | `CsrfFilter`, `CsrfTokenRepository` Servlet |
| Repository CSRF thường dùng | `WebSessionServerCsrfTokenRepository` | `HttpSessionCsrfTokenRepository` |
| Ngữ cảnh xác thực | `ServerSecurityContextRepository` | `SecurityContextRepository` Servlet |
| Session | `WebSession` | `HttpSession` |
| Authentication manager | `ReactiveAuthenticationManager` | `AuthenticationManager` đồng bộ |
| Firewall | `StrictServerWebExchangeFirewall` | `StrictHttpFirewall` |
| Kiểm thử | `WebTestClient` | `MockMvc` |

Chỉ có chung từ “CSRF”, “CORS”, “filter” hoặc “session” **không** làm cho những interface này có thể thay thế lẫn nhau.

## 6. Authentication và authorization: tách chính sách khỏi nguồn danh tính

### 6.1. Có thể chia sẻ gì?

Có thể dùng chung:

- Tên vai trò/authority theo hợp đồng nghiệp vụ: `ROLE_USER`, `ROLE_ADMIN`, `REPORT_VIEW`.
- Quyết định yêu cầu ADMIN cho `/admin/**` hoặc `REPORT_VIEW` để đọc báo cáo.
- Quy tắc chuẩn hóa username, nguyên tắc vô hiệu hóa account, chính sách mật khẩu hoặc MFA.
- `PasswordEncoder` nếu cả hai dịch vụ dùng cùng định dạng hash mật khẩu và cùng mô hình đăng nhập.
- Mô hình dữ liệu user, permission, các DTO hoặc interface nghiệp vụ thuần Java không mang loại request.

**Nhưng không nên dùng chung nguyên bean authentication HTTP** nếu một hệ là đồng bộ còn hệ kia là Reactive.

| Servlet | Reactive |
| --- | --- |
| `UserDetailsService` trả `UserDetails` đồng bộ | `ReactiveUserDetailsService` trả `Mono<UserDetails>` |
| `AuthenticationManager` trả `Authentication` | `ReactiveAuthenticationManager` trả `Mono<Authentication>` |
| Có thể dùng JDBC/JPA blocking qua adapter Servlet | Nên dùng repository/driver Reactive thực sự hoặc giải pháp offload được thiết kế rõ |
| Ngữ cảnh theo request thread/Servlet filter | Ngữ cảnh theo Reactor Context và Reactive filters |

Không viết `Mono.just(jpaRepository.findByUsername(...))` trong handler Reactive rồi gọi đó là non-blocking: phương thức JPA đã **chạy blocking trước khi tạo Mono**. Nếu cần tích hợp nguồn legacy blocking, phải thiết kế giải pháp offload/caching/điều phối riêng và kiểm thử tải; không dùng nó như mô hình Reactive tiêu chuẩn.

### 6.2. Ví dụ username/password đơn giản

**Servlet:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Bean
UserDetailsService servletUsers(PasswordEncoder encoder) {
    return new InMemoryUserDetailsManager(
        User.withUsername("demo")
            .password(encoder.encode("lab-only-password"))
            .roles("USER")
            .build()
    );
}
```

**Reactive:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.password.PasswordEncoder;

@Bean
MapReactiveUserDetailsService reactiveUsers(PasswordEncoder encoder) {
    return new MapReactiveUserDetailsService(
        User.withUsername("demo")
            .password(encoder.encode("lab-only-password"))
            .roles("USER")
            .build()
    );
}
```

Hai method trên thuộc **hai cấu hình ứng dụng khác nhau**. Bean `PasswordEncoder` có thể khai báo theo cùng policy hash (chẳng hạn `PasswordEncoderFactories.createDelegatingPasswordEncoder()`), nhưng nguồn user/test credential trong code chỉ dành cho lab; môi trường production nên dùng store, secret và vòng đời account có quản lý.

Nếu cả hai service dùng OAuth2 Resource Server, policy chung có thể chuẩn hóa **cách diễn giải claim thành authority**, nhưng adapter xác thực HTTP vẫn phải chọn cơ chế `jwt(...)`/resource server theo stack và kiểm tra cách token được xác minh ở phiên bản Security tương ứng.

## 7. CSRF: dùng chung quyết định, tách repository và vòng đời token

**Mục đích chung:** browser có thể tự gửi cookie/session tới server khi user đã đăng nhập; website độc hại có thể lợi dụng điều này để tạo yêu cầu thay đổi trạng thái. CSRF token giúp kiểm soát tình huống đó.

**Quyết định chung hợp lý:** “Mọi form/SPA dùng session cookie phải gửi CSRF token hợp lệ khi thay đổi dữ liệu”. Nhưng cách thực hiện phải phụ thuộc web stack.

| Trường hợp | Servlet | Reactive |
| --- | --- | --- |
| Bộ lọc | `CsrfFilter` | `CsrfWebFilter` |
| Repository mặc định | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Lưu session | `HttpSession` | `WebSession` |
| Cấu hình DSL | `http.csrf(Customizer.withDefaults())` | `http.csrf(Customizer.withDefaults())` |
| Kiểm thử | `MockMvc` + `SecurityMockMvcRequestPostProcessors.csrf()` | `WebTestClient` + `SecurityMockServerConfigurers.csrf()` |
| SPA cookie repository | `CookieCsrfTokenRepository` (nếu chọn) | `CookieServerCsrfTokenRepository` (nếu chọn) |

Mặc dù hai câu lệnh `.csrf(Customizer.withDefaults())` trông y hệt, giá trị repository mặc định và cách xử lý request **khác nhau**. Việc nhận token trong SPA còn bị ảnh hưởng bởi deferred token, cơ chế chống BREACH và việc làm mới token khi login/logout; phải đối chiếu tài liệu **đúng version**.

### 7.1. Đừng đặt boolean `disableCsrf` trong policy chung rồi dùng vô điều kiện

Ví dụ sai về thiết kế:

```java
// KHÔNG DÙNG: coi tất cả service và client đều miễn CSRF.
if (policy.disableCsrf()) {
    http.csrf(csrf -> csrf.disable());
}
```

Nếu một API chỉ nhận bearer token mà client chủ động gửi qua `Authorization` header, có thể đánh giá CSRF khác với browser dùng session cookie. **Ngoại lệ phải theo đường đi và cơ chế credential thực tế**, không theo nhãn “Servlet” hay “Reactive”.

Tốt hơn, lập bảng contract riêng:

| Client | Credential | CSRF goal |
| --- | --- | --- |
| Form web | Cookie session | Giữ CSRF cho POST/PUT/PATCH/DELETE |
| SPA | Cookie session | Giữ CSRF; cấp/refresh token cho JavaScript đúng cách |
| API machine-to-machine | Bearer token chủ động gửi; không có auth cookie | Có thể đánh giá miễn CSRF theo threat model |
| Webhook | Chữ ký HMAC, timestamp; không dùng cookie | Có thể loại trừ đường webhook **hẹp**, vẫn phải xác minh chữ ký/chống replay |

Nếu có nhiều chain, chỉ một chain được chọn cho request; phải cấu hình CSRF đúng ở **từng chain liên quan**. Nếu URL không match bất kỳ chain nào thì CSRF filter của Spring Security cũng không bảo vệ URL đó.

## 8. CORS: chính sách dùng chung, hai kiểu `CorsConfigurationSource`

Policy ở mục 3 đã chứa allowlist origin/method/header và `allowCredentials`. Cả hai adapter có thể dùng cùng giá trị đó, nhưng phải tạo hai bean khác **package**.

```text
BrowserProtectionPolicy.allowedOrigins() == ["https://app.example.com"]
                          |
              +-----------+-----------+
              |                       |
          Servlet                   Reactive
       UrlBasedCors...            UrlBasedCors...
          (servlet)                 (reactive)
              |                       |
       HttpSecurity.cors()       ServerHttpSecurity.cors()
              |                       |
          Servlet CORS               WebFlux CORS
```

Khi web page ở `https://app.example.com` gọi API ở `https://api.example.com` kèm cookie, CORS preflight cần được xử lý trước lớp authentication vì preflight thường không mang cookie session. CORS policy không có nghĩa server chấp nhận user/role bất kỳ. Nếu frontend không dùng cookie, xem xét `allowCredentials=false` thay vì bật theo thói quen.

Một request thử điển hình:

```http
OPTIONS /orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Kỳ vọng là server trả allow-origin phù hợp cho origin được phép, cùng allowed methods/headers; thử lại với `Origin: https://untrusted.example` phải **không** cấp quyền CORS cho origin đó. Không dùng `permitAll()` cho OPTIONS như giải pháp thay thế toàn bộ CORS config.

## 9. CSP, HSTS và security headers: chia sẻ policy nhưng cấu hình riêng

Policy chung `cspDirectives` có thể áp dụng nhất quán:

```text
default-src 'self'; object-src 'none'; frame-ancestors 'none'
```

Cả hai stack có API header để ghi `Content-Security-Policy`; ví dụ mục 4.1 và mục 5.1 đã làm điều đó. **CSP không được Spring Security thêm mặc định** vì framework không biết ứng dụng tải script, stylesheet, font và iframe từ đâu. Khi frontend có CDN, inline script, nonce hoặc iframe hợp lệ, nhóm cần điều chỉnh CSP có kiểm soát; có thể bắt đầu bằng `Content-Security-Policy-Report-Only`.

Các header mặc định như `X-Content-Type-Options: nosniff` và `X-Frame-Options` được Spring Security quản lý tùy phiên bản/cấu hình. **Không** dùng chung các Java configurer kiểu `HeadersConfigurer<HttpSecurity>` với `ServerHttpSecurity.HeaderSpec`: chúng khác hệ API.

### 9.1. HSTS là policy chung, cách cấu hình khác nhau

HSTS (`Strict-Transport-Security`) được gửi trong điều kiện HTTPS phù hợp. Trên Servlet:

```java
http.headers(headers -> headers
    .httpStrictTransportSecurity(hsts -> hsts
        .includeSubDomains(true)
        .maxAgeInSeconds(31536000)
    )
);
```

Trong WebFlux, API và kiểu thời gian khác:

```java
import java.time.Duration;

http.headers(headers -> headers
    .hsts(hsts -> hsts
        .includeSubdomains(true)
        .maxAge(Duration.ofDays(365))
    )
);
```

Đây là các mẫu **tùy chỉnh riêng**, không nhất thiết phải ghi đè HSTS mặc định nếu đã đáp ứng nhu cầu. Bật `preload` và `includeSubDomains` có tác động tới toàn bộ subdomain, nên cần quyết định ở policy/đội vận hành và kiểm tra đủ hệ thống trước khi triển khai.

**Reverse proxy:** nếu HTTPS được kết thúc ở ingress rồi chuyển HTTP vào ứng dụng, cần kiểm tra `Forwarded`/`X-Forwarded-Proto`, danh sách proxy đáng tin và response **HTTPS public**. Thấy HSTS thiếu ở `http://localhost:8080` không tự chứng minh HTTPS production thiếu HSTS.

### 9.2. Bất biến quan trọng trên mọi stack

- Route công khai `permitAll()` vẫn nên nhận các header đã định nghĩa trên security chain.
- Một route **không đi qua security chain** sẽ không nhận header do Spring Security thêm.
- Không dùng `headers(headers -> headers.disable())` chỉ để sửa một header đơn lẻ.
- CSP phải kiểm thử trên trang HTML và các nguồn tài nguyên thực tế; `frame-ancestors` là policy clickjacking cần được đánh giá cùng X-Frame-Options.
- HSTS phải kiểm tra qua HTTPS và proxy, không dựa duy nhất vào mock response HTTP.

## 10. HTTP firewall: không thể chuyển bean giữa Servlet và Reactive

Mục tiêu chung của HTTP firewall là ngăn request có URL/path bất thường vượt qua quy tắc matcher hoặc bị các thành phần hiểu khác nhau. Hai stack có triển khai riêng:

| Servlet | Reactive |
| --- | --- |
| `org.springframework.security.web.firewall.StrictHttpFirewall` | `org.springframework.security.web.server.firewall.StrictServerWebExchangeFirewall` |
| Dùng trong `FilterChainProxy`/`HttpFirewall` | Dùng trong `WebFilterChainProxy`/`ServerWebExchangeFirewall` |
| Xử lý Servlet request, encoded path, path normalization, method | Xử lý `ServerWebExchange` và path/method/header/parameter theo Reactive |

Tài liệu Spring Security mô tả các dạng URL nguy hiểm như traversal `/../`, nhiều dấu slash `//`, semicolon/matrix variable, encoded slash và method bất thường. Các default firewall chặt chẽ giúp ngăn mismatch giữa authorization matcher và request routing.

**Không tạo một bean firewall dùng chung với kiểu `Object` rồi ép kiểu ở runtime**; hãy sử dụng bean cụ thể cho từng stack khi thật sự cần thay chính sách. Hầu hết ứng dụng nên giữ mặc định và thêm test cho URL bất thường.

Ví dụ tình huống cần điều tra: một Servlet application dùng matrix variables yêu cầu cho phép semicolon. Nếu thay `StrictHttpFirewall.setAllowSemicolon(true)` mà không xem proxy/container/MVC và matcher có hiểu URL giống nhau hay không, request `/admin;role=x/report` có thể đi qua đường logic không lường trước. Tương tự, WebFlux có `StrictServerWebExchangeFirewall` riêng với API điều chỉnh tương ứng. Bắt buộc viết test tấn công trước và sau khi nới.

## 11. Session, logout và context: hai cách lưu trạng thái

Ứng dụng browser có thể cần duy trì đăng nhập và CSRF token qua phiên. Quyết định chung là “khi user logout, không được tiếp tục dùng phiên cũ để truy cập tài nguyên nhạy cảm”, nhưng cách triển khai khác:

| Mục tiêu | Servlet | Reactive |
| --- | --- | --- |
| Lưu phiên web | `HttpSession` | `WebSession` |
| Repository security context | `SecurityContextRepository`, thường dùng repo gắn session | `ServerSecurityContextRepository` |
| Chính sách stateless | `SessionCreationPolicy.STATELESS` cho chain phù hợp | Chọn cơ chế authentication/repository Reactive, không dùng `SessionCreationPolicy` |
| Logout | Servlet logout filters/handlers | Reactive logout web filters/handlers |
| Kiểm tra token CSRF | Repo Servlet, session/cookie | Repo Reactive, WebSession/cookie |

Trong Servlet, chain bearer API có thể chọn:

```java
import org.springframework.security.config.http.SessionCreationPolicy;

http.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
);
```

**Đây là cấu hình chỉ dành cho một chain Servlet API thực sự dùng authentication không dựa vào session**. Không đặt mặc định cho browser chain có form login. `STATELESS` còn không đảm bảo các component ứng dụng khác không tạo `HttpSession`.

Reactive không có setter `sessionCreationPolicy` tương đương. Nếu thiết kế bearer API không lưu context vào WebSession, phải chọn `ServerSecurityContextRepository`, authentication mechanism và cache/lifecycle của WebFlux phù hợp; không ép `HttpSessionSecurityContextRepository` vào `ServerHttpSecurity`.

Các kiểm thử session cần bao gồm login/logout, CSRF token sau khi logout/login, session fixation, thời gian hết hạn và cookie flags (`Secure`, `HttpOnly`, `SameSite`). Những thuộc tính này còn phụ thuộc container, Spring Session, browser và reverse proxy.

## 12. Nhiều security chain: giữ policy chung mà không tạo lỗ hổng URL

Trong ứng dụng lớn, API và browser có thể dùng **hai** chain có mechanism khác nhau. Cần phân biệt **policy chung** (CSP/origins) và **các rule theo chain**.

Ví dụ Servlet minh họa việc áp policy chung vào một API chain và browser fallback:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain browser(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults());
    return http.build();
}
```

Đây là **khung phân chia chain**, chưa áp đầy đủ CORS/CSP cho cả hai: khi triển khai, các chain cần gọi riêng helper cấu hình header/CORS/CSRF phù hợp. `http` là đối tượng **riêng cho mỗi chain**, không gọi `build()` hai lần trên cùng một đối tượng.

Trong WebFlux, cấu trúc tương tự nhưng dùng `SecurityWebFilterChain`, `ServerHttpSecurity`, `securityMatcher(ServerWebExchangeMatcher)`, `authorizeExchange` và `pathMatchers`.

**Nguy cơ dễ bỏ sót:** nếu chỉ khai báo `securityMatcher("/api/**")` mà không có fallback, `/admin/**` có thể không đi qua **bất kỳ** Spring Security chain nào. `anyRequest().authenticated()` trong API chain không bảo vệ `/admin/**`. Cần test các URL ngoài API, đường dẫn public và URL lỗi/actuator.

### 12.1. Chia sẻ helper theo *cùng một* stack

Nếu nhiều Servlet chain dùng cùng headers và CORS, có thể tạo helper **chỉ dành cho Servlet**:

```java
static void applyServletBrowserDefaults(
        HttpSecurity http,
        BrowserProtectionPolicy policy,
        org.springframework.web.cors.UrlBasedCorsConfigurationSource cors)
        throws Exception {

    http.cors(corsDsl -> corsDsl.configurationSource(cors));
    http.csrf(Customizer.withDefaults());
    http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
            .policyDirectives(policy.cspDirectives())));
}
```

Đặt helper này trong Servlet module, gọi một lần từ mỗi chain phù hợp **trước `http.build()`**. Reactive cần một helper khác nhận `ServerHttpSecurity` và Reactive `CorsConfigurationSource`. Không chuyển helper Servlet thành generic `Object security` rồi dùng `instanceof` cho cả hai.

Các cơ chế login, HTTP Basic, authorization và session là phần riêng của mỗi chain, không nên bị helper shared vô tình bật giống nhau cho toàn bộ API và browser.

## 13. Cách tổ chức source để tránh trộn classpath

Ví dụ cấu trúc module gợi ý (không yêu cầu mọi dự án phải chia thành các Gradle/Maven module):

```text
security-policy/
  src/main/java/com/example/security/policy/
    BrowserProtectionPolicy.java
    SharedPolicyConfiguration.java
    AuthorityNames.java

servlet-app/
  src/main/java/com/example/security/servlet/
    ServletProtectionConfiguration.java
    ServletCorsConfiguration.java
    ServletIdentityAdapter.java
  src/test/java/.../
    ServletSecurityTests.java

reactive-app/
  src/main/java/com/example/security/reactive/
    ReactiveProtectionConfiguration.java
    ReactiveCorsConfiguration.java
    ReactiveIdentityAdapter.java
  src/test/java/.../
    ReactiveSecurityTests.java
```

**Ý nghĩa dependency:**

```text
security-policy     <- Java model / quyết định / hợp đồng kiểm thử
     ^        ^
     |        |
servlet-app     reactive-app
  Spring MVC       Spring WebFlux
  servlet filters  reactive web filters
```

Module `security-policy` lý tưởng không import Spring Security Servlet hoặc WebFlux; có thể đưa `@Configuration` tạo bean vào app bootstrap nếu muốn giữ module chung hoàn toàn thuần Java. Khi dùng một shared JAR chứa các lớp `@Configuration`, giới hạn component scanning/auto-configuration để tránh cả hai adapter bị đăng ký trong một application context.

Spring Boot thường ưu tiên **Servlet/MVC** nếu cả Web MVC và WebFlux hiện diện trên classpath (trừ khi cấu hình web application type khác). Vì vậy, chỉ thấy `spring-boot-starter-webflux` trong dependency graph **không** chứng minh app đang dùng `SecurityWebFilterChain`. Xác nhận `WebApplicationType` thực tế và kết quả integration test.

Với một shared starter tự viết, các adapter có thể dùng `@ConditionalOnWebApplication(type = SERVLET/REACTIVE)` và điều kiện classpath/bean phù hợp; cần test bootstrap cho từng loại. Việc khai báo bean chuyên biệt cho mỗi stack **chỉ vì class có trên classpath** không đủ an toàn.

## 14. Kiểm thử: cùng hợp đồng, hai bộ test riêng

Điều nên tái sử dụng là **bảng kịch bản và tiêu chí chấp nhận**, không phải một `MockMvc` client để kiểm thử WebFlux hoặc một `WebTestClient` bắt chước toàn bộ Servlet.

| Hợp đồng chung | Test Servlet | Test Reactive |
| --- | --- | --- |
| `GET /public/ping` không auth vẫn truy cập được | `MockMvc.get` + security filters | `WebTestClient.get` + `springSecurity()` |
| `GET /admin/report` dưới user không có ADMIN bị từ chối | `with(user(...))`, kỳ vọng 403 | `mutateWith(mockUser(...))`, kỳ vọng 403 |
| `GET /admin/report` dưới ADMIN qua được authorization | Test với role ADMIN + handler | Test với role ADMIN + handler |
| POST có cookie/session thiếu CSRF bị từ chối | `MockMvc.post` không `csrf()` | `WebTestClient.post` không `csrf()` |
| POST có CSRF token hợp lệ | `with(csrf())` | `mutateWith(csrf())` |
| CORS preflight origin được phép | `MockMvc`/HTTP `OPTIONS` có `Origin` | `WebTestClient`/HTTP `OPTIONS` |
| Origin không được phép | Không trả CORS allow-origin cho origin lạ | Cùng mục tiêu |
| HTML có CSP và `nosniff` | Assert response header | Assert response header |
| HTTPS có HSTS theo policy | `get(...).secure(true)` + test public | Test HTTPS public / WebFlux secure exchange |
| URL bất thường bị xử lý an toàn | Test Servlet firewall/proxy | Test Reactive firewall/proxy |
| Logout làm phiên cũ mất hiệu lực | Test `HttpSession` + CSRF | Test `WebSession` + CSRF |

### 14.1. Servlet: ví dụ test authorization, CSRF và CSP

Giả sử đã có `MockMvc mvc` được cấu hình với Spring Security, có endpoint `/public/ping`, `/admin/report` và `POST /orders` trả 200 khi hợp lệ:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void policyIsAppliedToServletRequests() throws Exception {
    mvc.perform(get("/public/ping"))
        .andExpect(status().isOk())
        .andExpect(header().exists("Content-Security-Policy"))
        .andExpect(header().string("X-Content-Type-Options", "nosniff"));

    mvc.perform(get("/admin/report").with(user("bob").roles("USER")))
        .andExpect(status().isForbidden());

    mvc.perform(post("/orders").with(user("bob").roles("USER")))
        .andExpect(status().isForbidden());

    mvc.perform(post("/orders")
            .with(user("bob").roles("USER"))
            .with(csrf()))
        .andExpect(status().isOk());
}
```

Nếu handler POST trả 201/204 thì sửa kỳ vọng theo contract; nếu endpoint không tồn tại thì test 404 không chứng minh policy đúng. Test phải có security filters (chẳng hạn cấu hình `springSecurity()` khi khởi tạo MockMvc thủ công).

### 14.2. Reactive: cùng mục tiêu với WebTestClient

Giả sử `WebTestClient client` đã bind vào `ApplicationContext` và áp dụng `springSecurity()`:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@Test
void policyIsAppliedToReactiveRequests() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("Content-Security-Policy")
        .expectHeader().valueEquals("X-Content-Type-Options", "nosniff");

    client.mutateWith(mockUser("bob").roles("USER"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("bob").roles("USER"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("bob").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk();
}
```

Đây là **khung test có fixture phù hợp**, không có nghĩa cứ copy là có controller và user. `mockUser` của test không đăng nhập vào server từ xa. Nếu sử dụng HTTP Basic, OAuth2 hoặc JWT khác form login, entry point/expected status cho user ẩn danh có thể khác; so sánh **quyết định bảo mật** trước khi buộc mọi status phải trùng tuyệt đối.

### 14.3. Test CORS và HTTPS ở môi trường thật

```bash
# Thay tên miền ví dụ bằng endpoint staging/production của bạn.
curl -i -X OPTIONS "https://api.example.com/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"

curl -i -X OPTIONS "https://api.example.com/orders" \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: POST"

curl -i "https://app.example.com/public/ping"
```

Quan sát allow-origin cho origin hợp lệ, không allow origin lạ, và `Content-Security-Policy`/`Strict-Transport-Security`/`X-Content-Type-Options` ở response HTTPS public. Trên PowerShell có thể gọi `curl.exe` để dùng cú pháp command line này thay vì alias `curl`. Chỉ dùng URL mà bạn quản lý.

## 15. Những lỗi thiết kế hoặc migration thường gặp

### Lỗi A — “Một bean `CorsConfigurationSource` dùng được cho mọi ứng dụng”

**Triệu chứng:** copy `org.springframework.web.cors.UrlBasedCorsConfigurationSource` từ MVC vào WebFlux, IDE báo không tương thích hoặc preflight không được xử lý.

**Nguyên nhân:** hai stack có interface và class cùng tên nhưng package khác. **Cách sửa:** giữ giá trị allowlist trong policy chung, tạo bean Servlet và bean Reactive riêng như mục 4.2/5.2. Test `OPTIONS` với `Origin` thực.

### Lỗi B — “Cùng annotation `@Configuration` nên cả hai filter chain đều được áp dụng”

**Triệu chứng:** ứng dụng có `SecurityFilterChain` và `SecurityWebFilterChain` nhưng một phần rule không có hiệu lực.

**Nguyên nhân:** Spring Boot chọn một web application type; Servlet và WebFlux có pipeline khác nhau. **Cách sửa:** chỉ đăng ký adapter phù hợp hoặc dùng điều kiện bootstrap chặt chẽ; kiểm tra filter chain đang hoạt động.

### Lỗi C — “Đưa CSRF vào shared config nên hai dịch vụ an toàn như nhau”

**Triệu chứng:** Servlet dùng session cookie chặn POST; Reactive lại cho POST đi qua hoặc SPA bị 403 sau login.

**Nguyên nhân:** shared policy không tự cài `CsrfWebFilter`, repository hoặc cơ chế refresh token. **Cách sửa:** cấu hình CSRF theo từng stack và test token thiếu/sai/đúng, login/logout và repository.

### Lỗi D — “Dùng một authentication manager cho cả blocking và non-blocking”

**Triệu chứng:** WebFlux bị chặn luồng bởi truy vấn JDBC/JPA đồng bộ, hoặc dependency injection sai kiểu.

**Nguyên nhân:** `AuthenticationManager` và `ReactiveAuthenticationManager` không thay thế lẫn nhau. **Cách sửa:** dùng adapter authentication phù hợp; nếu buộc tích hợp blocking backend, thiết kế bridge có giới hạn và kiểm thử tải thay vì đặt thao tác blocking trực tiếp trong reactive event loop.

### Lỗi E — “Public URL dùng `web.ignoring()` để giảm cấu hình”

**Triệu chứng:** static assets/public endpoints không còn CSP/HSTS/`nosniff` do Spring Security ghi.

**Nguyên nhân:** `web.ignoring()` khiến Servlet bỏ qua Security filter chain; `permitAll()` vẫn đi qua filter chain. **Cách sửa:** ưu tiên `permitAll()` khi muốn public nhưng giữ phòng vệ HTTP; kiểm tra route thật sau CDN/proxy.

### Lỗi F — “Chung mọi chain một helper nên API và browser có cùng session”

**Triệu chứng:** API vốn định dùng bearer token lại sinh session; browser form login không duy trì đăng nhập vì cấu hình stateless bị áp chung.

**Nguyên nhân:** helper chứa cả session policy, authentication mechanism và CSRF exception không phù hợp với từng chain. **Cách sửa:** chỉ chia sẻ CSP/origin và contract; tách login, repository, session strategy theo chain.

### Lỗi G — “Response HTTP local không có HSTS nghĩa là policy hỏng”

**Triệu chứng:** localhost backend không có HSTS nhưng HTTPS public có, hoặc ngược lại.

**Nguyên nhân:** HSTS liên quan HTTPS và proxy termination. **Cách sửa:** kiểm tra HTTPS public, forwarded headers và cấu hình proxy. Bảo đảm không tin header `X-Forwarded-*` do client bất kỳ tự đặt.

### Lỗi H — “Cùng string `/admin/**` đảm bảo mọi parser cho cùng kết quả”

**Triệu chứng:** MVC và WebFlux xử lý trailing slash hoặc URL được encode khác nhau, rule bảo mật lệch handler.

**Nguyên nhân:** matcher và web stack khác, Security 7 Servlet dùng `PathPatternRequestMatcher` theo quy tắc đường dẫn bỏ context path. **Cách sửa:** dùng policy chung để định nghĩa **ý định quyền**, ánh xạ path chính xác theo stack và test trailing slash, case, encoded path, servlet mapping/proxy rewrite.

## 16. Quy trình tách cấu hình trong dự án đang chạy

1. **Khóa baseline:** ghi phiên bản Boot/Framework/Security đã resolve, Java và web application type; lập bảng các chain/matcher đang có.
2. **Trích xuất ý định bảo mật:** role, URL public/admin, allowed origin/method/header, CSP/HSTS, client cookie hay bearer, yêu cầu session và logout.
3. **Tạo policy model thuần Java:** tránh nhập nhằng với repository/filters; kiểm tra tính hợp lệ của origin và CSP; xác định ai sở hữu việc thay đổi policy.
4. **Viết adapter Servlet hiện hữu:** chuyển logic vào `SecurityFilterChain`, Servlet CORS source và các bean identity/session/firewall tương ứng.
5. **Viết adapter WebFlux độc lập:** dùng `SecurityWebFilterChain`, Reactive CORS source, WebSession/Reactive Authentication; không kéo các bean Servlet sang.
6. **Đảm bảo chain coverage:** `securityMatcher`/`@Order` chính xác; fallback chain bảo vệ các URL còn lại; các chain được áp CSP/CORS/CSRF có chủ đích.
7. **Chạy cùng bảng kịch bản trên hai stack:** public/ADMIN, thiếu token CSRF, origin lạ, CSP/HSTS, login/logout, URL bất thường.
8. **Thử đường HTTPS qua proxy/CDN:** xác minh headers, request path, cookie flags, HSTS và request normalization.
9. **Dọn code lặp thực chất:** loại bỏ bản sao policy, nhưng giữ các adapter khác nhau khi API/semantics khác.
10. **Ghi quyết định và điều kiện thay đổi:** một lần cập nhật allowed origins/CSP hoặc threat model phải có test/đánh giá tác động cho cả hai ứng dụng.

Không bắt đầu bằng việc đưa mọi dòng cấu hình Spring Security vào một library dùng chung. Bắt đầu từ **hợp đồng được kiểm chứng**, rồi quyết định mức độ chia sẻ thực sự cần thiết.

## 17. Bài tập thực hành

**Bài 1 — Phân loại thành phần.** Cho các đối tượng: `PasswordEncoder`, `CorsConfiguration`, `CorsConfigurationSource`, `CSRF token repository`, `BrowserProtectionPolicy`, `SecurityFilterChain`, `SecurityWebFilterChain`, tên vai trò `ADMIN`, `StrictHttpFirewall` và `StrictServerWebExchangeFirewall`. Hãy xếp từng đối tượng vào *policy chung* hay *adapter theo stack*, kèm lý do. Lưu ý `CorsConfiguration` là kiểu dữ liệu Spring Framework có thể tái tạo từ policy nhưng không phải lý tưởng để đưa vào domain model thuần Java.

**Bài 2 — Tách mã cấu hình.** Từ một lớp `@Configuration` đang chứa hard-code origin/CSP và `HttpSecurity`, tách thành `BrowserProtectionPolicy` + cấu hình Servlet như mục 3/4. Tạo một ứng dụng WebFlux khác dùng cùng policy, rồi chứng minh không có class Servlet trong Reactive adapter.

**Bài 3 — Kiểm thử tương đương.** Tạo các endpoint `GET /public/ping`, `GET /admin/report` và `POST /orders` ở hai ứng dụng. Với MockMvc và WebTestClient, chứng minh public truy cập được, USER bị từ chối ở admin, ADMIN truy cập được, POST thiếu CSRF bị từ chối, POST có token đúng vượt qua bước CSRF, HTML có CSP.

**Bài 4 — Sửa CORS source sai stack.** Một người đưa `org.springframework.web.cors.UrlBasedCorsConfigurationSource` vào `ServerHttpSecurity.cors(...)`. Giải thích lỗi kiểu, sửa import và bean, thử preflight `Origin: https://app.example.com` và một origin không đáng tin.

**Bài 5 — Phân chia browser/API.** Dịch vụ MVC có browser form dùng session cookie và API bearer. Thiết kế hai `SecurityFilterChain`, áp CSP/CORS chung khi có ý nghĩa, giữ CSRF cho browser và đánh giá API riêng theo threat model. Thêm fallback chain để bảo vệ `/admin/**` nằm ngoài `/api/**`; viết test cho URL không được chain hẹp match.

## 18. Checklist khi bàn giao cấu hình dùng chung

- [ ] Policy chung ghi **mục tiêu và dữ liệu**, không chứa `HttpSecurity`/`ServerHttpSecurity`, Servlet/Reactive repository hay filter.
- [ ] Chỉ đăng ký adapter tương ứng với web application type; đã kiểm tra component scan và auto-configuration.
- [ ] `SecurityFilterChain`/`SecurityWebFilterChain` dùng đúng API; các filter chain có thứ tự và fallback rõ ràng.
- [ ] Origin/method/header/credentials CORS giống nhau về **ý định** và được chuyển thành đúng source của từng stack.
- [ ] CSRF đúng với credential model; token/repository/handler/login/logout được kiểm thử theo stack.
- [ ] Vai trò/authority dùng chung có semantics nhất quán; authentication manager, user service và repository phù hợp blocking/Reactive.
- [ ] CSP/headers/HSTS được xác nhận ở từng chain và trên HTTPS public; các exception được giải thích.
- [ ] Session/logout, cookie flags và CSRF token rotation được kiểm thử.
- [ ] HTTP firewall của từng stack được giữ chặt; test path traversal, encoded URL, semicolon/trailing slash.
- [ ] Không dùng `web.ignoring()` vô tình bỏ qua HTTP protection trên static/public resources.
- [ ] Có bảng kiểm thử hợp đồng chạy độc lập bằng MockMvc và WebTestClient, cùng smoke tests qua proxy thực.
- [ ] Nhóm quản lý policy có quy trình duyệt thay đổi origin/CSP/role và kiểm tra tác động lên cả hai ứng dụng.

## Tài liệu chính thức để đối chiếu

1. [Spring Security — Servlet Java Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html) — `SecurityFilterChain`, `HttpSecurity`, nhiều chain và phạm vi `securityMatcher`.
2. [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `SecurityWebFilterChain`, `ServerHttpSecurity` và các điểm mở rộng cấu hình cho Reactive.
3. [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html) và [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — CORS source theo từng stack và yêu cầu xử lý preflight trước authentication.
4. [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) và [Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — repository, token lifecycle, BREACH, SPA và phương pháp kiểm thử.
5. [Spring Security — Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) và [Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — CSP, HSTS, các header mặc định và cấu hình khác biệt.
6. [Spring Security — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html) và [Reactive Web Exchange Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — hai loại firewall và request normalization.
7. [Spring Security — Servlet Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html) và [Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html) — matcher và rule theo HTTP stack.
8. [Spring Security — Servlet MockMvc Integration](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html) và [Reactive WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — gắn security filters vào test.

**Tự đánh giá:** Tại sao có thể chia sẻ `cspDirectives` nhưng không chia sẻ một bean `CorsConfigurationSource` cho cả Servlet và Reactive? Vì sao `SessionCreationPolicy.STATELESS` không phải lựa chọn chung cho mọi client? Điều gì xảy ra khi một chain chỉ match `/api/**` nhưng ứng dụng có `/admin/**`? Bạn cần những test nào để chứng minh hai web stack triển khai **cùng chính sách bảo mật**?
