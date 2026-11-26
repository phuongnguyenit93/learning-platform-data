# Cấu hình theo môi trường và nguồn gốc triển khai

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Phạm vi:** Thiết kế cấu hình phòng vệ HTTP/trình duyệt theo môi trường **local, development, staging, production** và theo **nguồn gốc (origin) mà trình duyệt nhìn thấy**. Áp dụng đồng thời tư duy bảo vệ CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, cookie/session và chẩn đoán proxy cho **Servlet/Spring MVC** và **Reactive/WebFlux**.  
> **Mốc tham chiếu:** 26/11/2026. Các ví dụ cấu hình sử dụng Lambda DSL; tên property liên quan proxy có thể khác giữa các dòng Spring Boot 3.x và 4.x. Hãy dùng tài liệu đúng phiên bản đang chạy và xác minh response thực tế.

## 1. Mục tiêu của bài học

Sau bài này, người học có thể:

1. Phân biệt **environment**, **origin**, **site**, **host**, **public URL** và **internal backend URL**.
2. Tách chính sách bảo mật bất biến khỏi các giá trị triển khai được phép thay đổi giữa `local`, `staging` và `prod`.
3. Nạp danh sách origin, CSP và HSTS có kiểm tra hợp lệ bằng Spring Boot configuration properties; từ chối cấu hình nguy hiểm thay vì tự mở quyền khi thiếu biến.
4. Cấu hình CORS/CSRF/security headers và session đúng cho cả `HttpSecurity`/`SecurityFilterChain` lẫn `ServerHttpSecurity`/`SecurityWebFilterChain`.
5. Hiểu sự ảnh hưởng của ingress/reverse proxy, TLS termination, `Forwarded`/`X-Forwarded-*`, hostname và URL rewrite đối với bảo mật.
6. Dùng kiểm thử HTTP và quy trình triển khai để phát hiện origin sai, preflight 401/403, cookie bị chặn, HSTS biến mất, CSP phá giao diện và URL lọt filter chain.

### Tình huống xuyên suốt

Ứng dụng có frontend và backend cùng phục vụ đăng nhập bằng cookie/session:

| Môi trường | Frontend người dùng truy cập | Backend API người dùng truy cập | Backend nội bộ |
| --- | --- | --- | --- |
| Local | `http://localhost:5173` | `http://localhost:8080` | `http://localhost:8080` |
| Staging | `https://app.staging.example.com` | `https://api.staging.example.com` | `http://api:8080` |
| Production | `https://app.example.com` | `https://api.example.com` | `http://api:8080` |

Các tên miền `example.com` mang tính minh họa, không phải endpoint có thể gọi trực tiếp. Trong staging/production, trình duyệt dùng **HTTPS công khai**, còn ứng dụng có thể chỉ nhận HTTP từ reverse proxy ở mạng nội bộ. Những lớp phòng vệ phải đánh giá theo cả **URL ngoài trình duyệt** và **cách Spring nhận request phía trong**.

## 2. Mô hình mối đe dọa: mỗi môi trường thay đổi điều gì?

### 2.1. Những mục tiêu không nên giảm khi đổi môi trường

| Chính sách | Local | Staging | Production |
| --- | --- | --- | --- |
| `/admin/**` phải có ADMIN | Giữ | Giữ | Giữ |
| Route khác cần xác thực trừ danh sách public | Giữ | Giữ | Giữ |
| CSRF cho browser sử dụng credential tự động | Giữ | Giữ | Giữ |
| CORS không tự phản chiếu origin bất kỳ | Giữ | Giữ | Giữ |
| CSP có chính sách được chủ động xác định | Giữ baseline | Kiểm thử sát prod | Enforce đã kiểm chứng |
| Strict HTTP firewall | Giữ | Giữ | Giữ |
| Không ghi token/session/password vào log | Giữ | Giữ | Giữ |
| Đánh giá cookie/session/logout | Giữ | Giữ | Giữ |

**Không tạo một `@Profile("dev")` với `anyRequest().permitAll()` và `csrf.disable()` chỉ để frontend gọi API dễ hơn.** Profile sai ở production có thể loại bỏ toàn bộ chính sách. Một ứng dụng khởi động được trong môi trường phát triển bằng cấu hình yếu không chứng minh nó sẽ an toàn khi được promote.

### 2.2. Những giá trị thực sự thay đổi

- Origin frontend được phép, cổng HTTP trong local và tên miền HTTPS ở staging/prod.
- Hệ thống nhận TLS trực tiếp hay sau proxy và danh sách proxy đáng tin.
- CSP của các tài nguyên bên ngoài có thật: CDN, font, media, reporting endpoint.
- Cookie `Domain`/`Path`/`Secure`/`SameSite` theo kiến trúc cross-origin/cross-site.
- Cách cấp chứng chỉ, secret, session store, vòng đời key và timeout theo yêu cầu vận hành.
- Domain/HSTS policy, đặc biệt `includeSubDomains`/`preload` và tình trạng HTTPS của các subdomain.
- Các endpoint thật của monitoring/health-check có được công khai và cấp quyền đúng không.

Những thay đổi này phải được **giới hạn bằng validation và kiểm thử**, không trở thành công tắc cho phép tắt hệ thống bảo vệ ở môi trường khác.

## 3. Hiểu chính xác “origin”, “site” và địa chỉ triển khai

### 3.1. Origin là bộ ba scheme + host + port

Một *origin* gồm:

```text
origin = scheme (http/https) + hostname + port (hiển thị khi khác cổng chuẩn)
```

| URL | Origin | Khác origin với `https://app.example.com`? |
| --- | --- | --- |
| `https://app.example.com/dashboard` | `https://app.example.com` | Không |
| `https://app.example.com:443/a` | `https://app.example.com` về ngữ nghĩa | Không |
| `https://api.example.com/orders` | `https://api.example.com` | **Có**: khác hostname |
| `http://app.example.com` | `http://app.example.com` | **Có**: khác scheme |
| `https://app.example.com:8443` | `https://app.example.com:8443` | **Có**: khác port |
| `http://localhost:5173` | `http://localhost:5173` | **Có** so với `http://localhost:8080` |

**Không** khai báo origin có path như `https://app.example.com/dashboard` trong CORS allowlist. Cũng không thêm slash cuối `https://app.example.com/` như thể đó là phần origin. `Origin` không bao gồm path, query hay fragment; CORS kiểm tra scheme/host/port.

Đừng tin `Origin` như bằng chứng người dùng được xác thực: client không phải browser có thể tự gửi header này. CORS là cơ chế kiểm soát khả năng truy cập response từ **mã JavaScript trên trình duyệt**, không thay authorization.

### 3.2. “Same-site” không giống “same-origin”

Giả sử frontend là `https://app.example.com` và backend là `https://api.example.com`:

- Chúng **cross-origin** nên JavaScript cần CORS khi gọi API.
- Chúng có thể **same-site** theo quy tắc *schemeful same-site*: cùng scheme HTTPS và cùng registrable domain `example.com`.
- Cookie `SameSite=Lax` hoặc `Strict` có thể hoạt động khác với tình huống thật sự **cross-site**, ví dụ frontend `https://app.other-example.net` gọi backend `https://api.example.com`.

Vì vậy, **cross-origin không đồng nghĩa phải dùng `SameSite=None`**. Trước khi sửa cookie, xác định request là same-site hay cross-site theo quy tắc browser, nơi cookie được gắn, phạm vi Domain/Path và cách fetch/XHR gửi credentials.

Khi thực sự cần gửi session cookie trong ngữ cảnh cross-site, thường phải dùng `SameSite=None; Secure`, HTTPS và `credentials` đúng cách. Chính sách chặn third-party cookies của một số trình duyệt vẫn có thể ảnh hưởng; `SameSite=None` **không bảo đảm** browser sẽ luôn gửi cookie.

### 3.3. Public origin và backend origin có thể khác

```text
Browser
  https://api.example.com/orders
        |
        | TLS, Host, Origin, Cookies
        v
Edge / CDN / Ingress
  - terminate TLS
  - route by Host
  - may rewrite path /api -> /
  - add Forwarded or X-Forwarded-Proto
        |
        | HTTP inside trusted network
        v
Spring Boot backend http://api:8080/orders
        |
        +-- Spring Security chain
        +-- CSRF / CORS / headers / authorization
        +-- handler/controller
```

Không dùng `http://api:8080` làm origin frontend trong CORS khi trình duyệt chỉ thấy `https://api.example.com`. Browser gửi `Origin` theo trang frontend, chẳng hạn `https://app.example.com`; nguồn truy cập đến API mà người dùng nhìn thấy là `https://api.example.com`. URL nội bộ chỉ phục vụ routing và chẩn đoán proxy.

## 4. Thiết kế cấu hình Spring Boot theo môi trường

### 4.1. Bất biến nằm trong Java; giá trị triển khai nằm trong properties

Một tổ chức có thể giữ cố định các rule:

```text
/public/**    -> permitAll
/admin/**     -> hasRole("ADMIN")
mọi URL khác -> authenticated
CSRF cho browser cookie -> bật
không origin wildcard khi có credential
firewall -> strict
```

Trong khi đó, chỉ một số giá trị thay đổi theo môi trường:

```yaml
# application.yml — mặc định chia sẻ (MINH HỌA)
security:
  http:
    allowed-origins: []          # Không mở origin mặc định
    allow-credentials: true
    csp: "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
    hsts-include-subdomains: false
    hsts-max-age: 365d
```

**Lưu ý:** nếu ứng dụng cần browser frontend, danh sách origin trống ở cấu hình chung nên dẫn tới lỗi khởi động qua validation (mục 5), hoặc một quy tắc từ chối CORS có chủ đích với dịch vụ không có cross-origin client. Không tự điền wildcard `*` khi thiếu cấu hình.

Các file profile-specific chỉ minh họa giá trị deploy; không thêm bean security yếu chỉ vì khác môi trường:

```yaml
# application-local.yml — ví dụ môi trường local trên HTTP
security:
  http:
    allowed-origins:
      - "http://localhost:5173"
    hsts-include-subdomains: false
```

```yaml
# application-staging.yml — staging dùng HTTPS public
security:
  http:
    allowed-origins:
      - "https://app.staging.example.com"
    hsts-include-subdomains: false
```

```yaml
# application-prod.yml — production
security:
  http:
    allowed-origins:
      - "${SECURITY_FRONTEND_ORIGIN}"  # Cấp bởi deployment; không có default mở rộng
    hsts-include-subdomains: false      # Bật true chỉ khi đã đánh giá toàn bộ subdomain
```

Ở đây `SECURITY_FRONTEND_ORIGIN` là biến môi trường ví dụ phải được cấp giá trị như `https://app.example.com`. Dòng placeholder **không** phải URL hợp lệ nếu biến chưa được resolve; validation phải làm deployment lỗi trước khi phục vụ traffic.

**Chọn profile từ môi trường triển khai**, không hard-code `spring.profiles.active` trong `application-prod.yml`:

```bash
# Ví dụ Unix shell; trên Windows dùng cách thiết lập biến môi trường tương ứng.
export SPRING_PROFILES_ACTIVE=prod
export SECURITY_FRONTEND_ORIGIN=https://app.example.com
java -jar app.jar
```

Spring Boot cho phép nạp property từ nhiều nguồn (classpath, environment, external config, command line...), có thứ tự ưu tiên. Kiểm tra **effective configuration** và nguồn thay đổi quan trọng; chỉ đọc `application.yml` trong source không chứng minh giá trị runtime. `spring.profiles.active` phải được đặt trong nguồn không profile-specific (hoặc biến môi trường/command line), không trong tài liệu đã kích hoạt bằng `spring.config.activate.on-profile`.

### 4.2. Đừng dùng profile làm biên giới tin cậy

Phân quyền URL/CSRF/header không được phụ thuộc chỉ vào việc profile tên `prod` đã bật hay chưa. Một lệnh deploy sai profile phải **không** biến API thành `permitAll`. Giả sử một service production khởi động dưới profile `local`, chúng ta vẫn mong:

1. Endpoint `/admin/**` giữ yêu cầu ADMIN.
2. CSRF không bị tắt.
3. CORS chỉ nhận origin được cấu hình và bị validator/nguyên tắc triển khai chặn khi origin HTTP localhost lọt vào môi trường công khai.
4. HTTPS security headers/CSRF/session không biến mất.

Có thể thêm chính sách từ chối start nếu production deployment không ở profile hoặc môi trường ký định danh dự kiến; **không dùng profile đơn độc như xác thực hạ tầng**. CI/CD/Kubernetes admission, secret access, RBAC, immutable deployment manifest và kiểm thử response cũng cần thực hiện.

### 4.3. Cấu hình profile tổ hợp

Spring Boot hỗ trợ profile groups, ví dụ nhóm `staging` kích hoạt một số config riêng. Nhưng `spring.profiles.active`, `spring.profiles.default` và định nghĩa `spring.profiles.group` có các ràng buộc đặt ở tài liệu không profile-specific. Nếu cấu hình không được nạp, kiểm tra vị trí property và priority trước khi sửa security filters.

Không chia nhỏ thành `cors-off`, `csrf-off`, `headers-off` profile như một cách tiện debug; việc nhiều profile kết hợp có thể tạo trạng thái bảo mật không dự tính. Khi cần thử một cấu hình bất thường trong local, dùng một test context độc lập, không tạo đường dễ vô tình kích hoạt trên staging/prod.

## 5. Ràng buộc cấu hình ở startup: fail closed

Một `@ConfigurationProperties` record giúp bind và kiểm tra các giá trị trước khi ứng dụng nhận request.

### 5.1. Record cấu hình có kiểm tra origin và CSP

```java
package com.example.security;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Objects;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "security.http")
public record HttpProtectionProperties(
        List<String> allowedOrigins,
        boolean allowCredentials,
        String csp,
        boolean hstsIncludeSubdomains,
        Duration hstsMaxAge) {

    public HttpProtectionProperties {
        allowedOrigins = List.copyOf(
            Objects.requireNonNull(allowedOrigins, "allowedOrigins required"));
        if (allowedOrigins.isEmpty()) {
            throw new IllegalArgumentException(
                "A browser frontend origin must be explicitly configured");
        }
        for (String origin : allowedOrigins) {
            if (!origin.equals(origin.trim()) || origin.equals("*")) {
                throw new IllegalArgumentException("Invalid CORS origin: " + origin);
            }
            URI uri = URI.create(origin);
            String scheme = uri.getScheme();
            if (scheme == null
                    || !(scheme.equalsIgnoreCase("https")
                         || scheme.equalsIgnoreCase("http"))
                    || uri.getHost() == null
                    || (uri.getRawPath() != null
                        && !uri.getRawPath().isEmpty())
                    || uri.getRawQuery() != null
                    || uri.getRawFragment() != null
                    || uri.getUserInfo() != null) {
                throw new IllegalArgumentException(
                    "Expected exact origin: scheme://host[:port]");
            }
        }
        if (csp == null || csp.isBlank()) {
            throw new IllegalArgumentException("CSP must not be blank");
        }
        Objects.requireNonNull(hstsMaxAge, "hstsMaxAge required");
        if (hstsMaxAge.isNegative()) {
            throw new IllegalArgumentException(
                "HSTS max-age must not be negative");
        }
    }
}
```

Đây là model **cho ứng dụng có một frontend cross-origin được cấp phép**; nếu một service không có bất kỳ browser client nào, có thể thiết kế model/validator khác để cho phép danh sách CORS trống và **không trả CORS allow-origin**. Không suy rằng mọi Spring Boot API cần ít nhất một CORS origin.

`List.copyOf` tránh chỉnh sửa allowlist sau khi bind. Validator cơ bản yêu cầu origin thật (không path, query, fragment, user info). Trong production cần mở rộng kiểm tra port, IDN, lệnh wildcard pattern `allowedOriginPatterns`, hostname thuộc miền do tổ chức kiểm soát và ban đầu không nhận giá trị chưa resolve. Đặc biệt, mã ở đây **cho phép** HTTP origin để phục vụ localhost; phần chặn HTTP origin ở production là trách nhiệm của guardrail mục 5.3.

### 5.2. Đăng ký cấu hình bằng bean

```java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(HttpProtectionProperties.class)
class HttpProtectionPropertyConfig {
}
```

Trong ứng dụng có `@ConfigurationPropertiesScan` đúng phạm vi cũng có thể để Spring Boot phát hiện kiểu record, nhưng không nên vô tình khai báo hai bean cùng ý nghĩa. Với Spring Boot 3/4, record được hỗ trợ constructor binding; cách bind/validate chính xác cần kiểm tra với phiên bản và starter đang dùng.

### 5.3. Guardrail riêng cho production

Có thể bổ sung một kiểm tra trước khi ứng dụng sẵn sàng nhận traffic:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

@Configuration
class ProductionOriginGuard {

    @Bean
    ApplicationRunner rejectInsecureProductionOrigins(
            HttpProtectionProperties properties,
            Environment environment) {

        return args -> {
            if (!environment.acceptsProfiles(Profiles.of("prod"))) {
                return;
            }
            for (String origin : properties.allowedOrigins()) {
                if (!origin.startsWith("https://")) {
                    throw new IllegalStateException(
                        "Production CORS origins must use HTTPS");
                }
                if (origin.contains("localhost")
                        || origin.contains("127.0.0.1")) {
                    throw new IllegalStateException(
                        "Localhost origins are forbidden in production");
                }
            }
        };
    }
}
```

Đoạn guardrail minh họa nguyên tắc **fail closed** và cần được mở rộng bằng allowlist domain/manifest đáng tin; kiểm tra chuỗi `contains("localhost")` **không đủ** thay thế kiểm định DNS/URI/IP hoặc biên giới triển khai. `ApplicationRunner` chạy trước khi Spring Boot báo sẵn sàng theo lifecycle thông thường, nhưng web server có thể đã bind cổng trong giai đoạn context refresh. Hãy để ingress chỉ định tuyến đến instance **ready** và chuyển các điều kiện cấu hình sống còn sang validation ngay khi bind properties nếu cần đảm bảo không phục vụ bất kỳ request nào. Guardrail không thay thế kiểm soát ingress/CI/CD.

Một môi trường staging cũng nên kiểm tra **HTTPS và domain staging**. Tuyệt đối không tự chuyển sang `allowedOrigins("*")` để vượt qua lỗi cấu hình.

## 6. Servlet: cấu hình nguồn CORS, CSRF, CSP và HSTS từ properties

Ví dụ sau dành cho **Spring MVC/Servlet**, dùng bean `SecurityFilterChain`. User store/authentication phải được cấu hình riêng; ở đây chỉ trình bày phần HTTP protection.

```java
package com.example.security.servlet;

import com.example.security.HttpProtectionProperties;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebSecurity
class ServletHttpProtection {

    @Bean
    UrlBasedCorsConfigurationSource servletCorsSource(
            HttpProtectionProperties p) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(p.allowedOrigins());
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(p.allowCredentials());

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain browser(
            HttpSecurity http,
            UrlBasedCorsConfigurationSource servletCorsSource,
            HttpProtectionProperties p) throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .cors(cors -> cors.configurationSource(servletCorsSource))
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(p.csp()))
                .httpStrictTransportSecurity(hsts -> hsts
                    .includeSubDomains(p.hstsIncludeSubdomains())
                    .maxAgeInSeconds(p.hstsMaxAge().toSeconds()))
            )
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Lưu ý:

- `UrlBasedCorsConfigurationSource` ở ví dụ thuộc package **`org.springframework.web.cors`** (Servlet), không phải package reactive.
- `cors.configurationSource(...)` chọn một nguồn policy **tường minh**; hữu ích khi ứng dụng có nhiều CORS source. Nếu dựa vào Spring MVC CORS configuration, cần xác nhận cách Security tự phát hiện trong phiên bản tương ứng.
- `csrf(Customizer.withDefaults())` giữ CSRF khi browser tự gửi session cookie; không nên đổi theo profile.
- CSP được khai báo tường minh; Spring Security **không thêm CSP mặc định**.
- HSTS header được Spring Security thêm trên **HTTPS** theo nhận thức request đã được xử lý; `hstsMaxAge` là giá trị cấu hình, không mặc định tự bật preload.
- Một `SecurityFilterChain` không có `securityMatcher` riêng bao phủ request còn lại. Nếu có nhiều chain, phải xác nhận CSP/CORS/CSRF cho mỗi chain.

**Đừng sao chép vào production trước khi điều chỉnh CSP và cookie policy.** `default-src 'self'` có thể chặn JS/CSS/CDN không cùng origin, ảnh hưởng chức năng chứ không hẳn là bug Security.

## 7. Reactive: cùng policy nhưng bean khác cho WebFlux

WebFlux sử dụng `ServerHttpSecurity`/`SecurityWebFilterChain` và **CORS source reactive**.

```java
package com.example.security.reactive;

import com.example.security.HttpProtectionProperties;
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveHttpProtection {

    @Bean
    UrlBasedCorsConfigurationSource reactiveCorsSource(
            HttpProtectionProperties p) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(p.allowedOrigins());
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(p.allowCredentials());

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain browser(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource reactiveCorsSource,
            HttpProtectionProperties p) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**", "/error").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .cors(cors -> cors.configurationSource(reactiveCorsSource))
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(p.csp()))
                .hsts(hsts -> hsts
                    .includeSubdomains(p.hstsIncludeSubdomains())
                    .maxAge(p.hstsMaxAge()))
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Những phần **không** thể bê nguyên từ Servlet:

- CORS source nằm ở `org.springframework.web.cors.reactive`.
- CSRF Reactive dùng `CsrfWebFilter`, `WebSessionServerCsrfTokenRepository` theo mặc định, không dùng `HttpSessionCsrfTokenRepository`.
- Request matcher Reactive dùng `ServerWebExchangeMatcher`/`pathMatchers`, không dùng Servlet `RequestMatcher`.
- Session và security context dùng `WebSession`/`ServerSecurityContextRepository`.
- API HSTS là `.hsts(...).maxAge(Duration)`, khác `.httpStrictTransportSecurity(...).maxAgeInSeconds(long)` trong Servlet.

Đây là **ví dụ cho ứng dụng WebFlux độc lập**, không nên đăng ký đồng thời với Servlet config cùng tên trong một context. Nếu ứng dụng có cả Spring MVC và WebFlux dependencies, xác minh `WebApplicationType` mà Boot chọn, thay vì suy từ thư viện có mặt trên classpath.

## 8. CORS theo origin triển khai: quyết định và quy trình kiểm thử

### 8.1. CORS không là “cho phép internet”

Phần lớn API có thể nhận request từ `curl` hay mobile app mà không cần CORS, vì CORS được browser kiểm soát. Một origin lạ không đọc được response qua JavaScript không có nghĩa request không thể đến server hoặc trạng thái không thể bị thay đổi. Authentication, authorization, CSRF và chống abuse là cơ chế độc lập.

**Quy tắc tối thiểu** cho frontend dùng cookie:

1. Liệt kê origin chính xác (scheme/host/port), không dùng `*`.
2. Chỉ bật `allowCredentials=true` khi thực sự cần cookie/credentials cross-origin.
3. Giới hạn HTTP methods và request headers.
4. Khi preflight hợp lệ, trả allow-origin cụ thể, allowed methods/headers và credentials phù hợp.
5. Phân biệt frontend **origin** với tên miền API hoặc internal service DNS.
6. Kiểm tra origin không được cho phép và các response lỗi; response phải không cấp quyền CORS cho origin lạ.

### 8.2. Preflight thực tế

```http
OPTIONS /orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Browser có thể gửi preflight **không có cookie session**. Vì vậy CORS phải được xử lý trước authentication; nếu không ứng dụng có thể trả 401/403 ngay tại preflight. Trong Spring Security, hãy cấu hình `CorsConfigurationSource` đúng stack và xác định filter chain phục vụ URL.

Kiểm tra cache ở CDN/proxy: response CORS thay đổi theo `Origin` phải được cache theo policy tương ứng, thường có `Vary: Origin` (và có thể các preflight request headers). Cache cấu hình sai có thể làm response chứa allow-origin của origin này được phát cho origin khác.

### 8.3. Những cấu hình dễ gây lỗ hổng

| Sai lầm | Vấn đề | Cách tiếp cận |
| --- | --- | --- |
| `allowedOrigins("*")` + credential | Không hợp lệ với phản hồi CORS credentialed theo chuẩn | Origin cụ thể, kiểm tra allowlist |
| Phản chiếu mọi header `Origin` | Bất kỳ website nào được đọc response nếu server cấp credential CORS | Chỉ nhận origin đã được cấp phép |
| Dùng `allowedOriginPatterns("https://*.example.com")` cho mọi subdomain | Một subdomain bị chiếm quyền có thể được phép đọc API | Ưu tiên exact origin, đánh giá sở hữu mọi subdomain |
| Dùng hostname backend `api:8080` làm allowed origin | Browser thực tế không gửi origin nội bộ | Cấu hình dựa trên frontend public origin |
| `@CrossOrigin("*")` rải rác ở controller | Rule CORS thiếu tập trung, dễ vượt policy chung | Xây nguồn policy rõ ràng và test |
| Cho OPTIONS `permitAll` rồi bỏ CORS filter | Có thể vượt authorization nhưng browser vẫn chặn | Tích hợp đúng CORS source |
| Tắt CSRF để “sửa CORS” | Có thể mở CSRF cho cookie session | Phân biệt preflight, CORS, authentication và CSRF |

## 9. CSRF qua các môi trường: cookie, token và session

CSRF nguy hiểm khi browser **tự đính kèm** credential như cookie session vào request bị kích hoạt từ website khác. Đổi domain giữa local/staging/prod có thể ảnh hưởng cookie và token, nhưng không làm mô hình rủi ro biến mất.

### 9.1. Đừng đánh giá CSRF chỉ từ loại HTTP API

| Cách xác thực | Nguy cơ CSRF và hướng cấu hình |
| --- | --- |
| Form login + session cookie | **Giữ CSRF**; form POST và logout POST phải gửi token |
| SPA + cookie session | **Giữ CSRF**; có cơ chế cấp token/cập nhật sau login/logout |
| Bearer token do client chủ động gửi ở `Authorization`, không có auth cookie | Có thể đánh giá miễn CSRF cho chain API theo threat model |
| HTTP Basic được browser ghi nhớ và tự đính kèm | Vẫn phải đánh giá CSRF, không mặc định an toàn |
| Webhook ký HMAC, timestamp, không session cookie | Có thể loại trừ CSRF ở đúng route, nhưng phải chống giả mạo và replay |

Trong Spring Security 6+, CSRF token có cơ chế **deferred loading** và **BREACH masking**; SPA đọc token thô từ cookie có thể cần request handler/SPA integration đúng version. Sau login/logout token cũ có thể bị xóa; browser cần lấy token mới trước khi POST tiếp. Không tắt CSRF toàn app để tránh lỗi 403.

### 9.2. Cookie `SameSite`, `Secure`, `HttpOnly`, `Domain`, `Path`

Cookie session cần kiểm tra theo **nguồn gốc triển khai thực tế**:

- `Secure`: chỉ gửi qua HTTPS; staging/prod public cần đúng cơ chế HTTPS.
- `HttpOnly`: hạn chế JavaScript đọc cookie session; thường nên bật cho auth session.
- `SameSite`: kiểm soát cookie trên yêu cầu same-site/cross-site; không thay CSRF token.
- `Domain`: cookie host-only thường hạn chế hơn cookie mở rộng `.example.com` cho tất cả subdomain.
- `Path`: giới hạn nơi cookie được gửi theo đường dẫn nhưng không thay biên giới bảo mật giữa ứng dụng.
- `Max-Age`/session timeout: xác định phiên sống bao lâu, hành vi khi hết hạn và logout.

**Không đặt `HttpOnly=false` cho cookie session chỉ để JavaScript đọc được.** Nếu SPA cần đọc cookie `XSRF-TOKEN`, đó có thể là một cookie **CSRF riêng** theo kiến trúc được đánh giá, khác cookie session xác thực.

### 9.3. Thuộc tính Spring Boot cho Servlet và Reactive khác namespace

**Servlet (`application-prod.yml` minh họa):**

```yaml
server:
  servlet:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

**Reactive (`application-prod.yml` cho app WebFlux độc lập):**

```yaml
server:
  reactive:
    session:
      timeout: 30m
      cookie:
        secure: true
        http-only: true
        same-site: lax
```

Đây là **hai ứng dụng riêng**; tên cookie, thuộc tính hỗ trợ và cách servlet container/WebSession adapter áp dụng có thể khác theo Boot version. Với frontend truly cross-site, có thể cần `same-site: none` kèm `secure: true` và kiểm thử browser; không đổi sang `none` chỉ vì frontend và API khác subdomain.

Trong local dùng HTTP, `Secure` có thể ngăn cookie được gửi trong một số môi trường (localhost có ngoại lệ browser tùy nền tảng). Tốt nhất chạy HTTPS local nếu cần mô phỏng production, hoặc cấu hình cookie local **có giới hạn và được test** mà không làm thay đổi profile production.

### 9.4. Session store khi deploy nhiều replica

Một login thành công trên pod A nhưng request tiếp theo đến pod B có thể mất authentication/CSRF token nếu session chỉ lưu trong bộ nhớ từng pod và không có sticky routing. Cần chọn chiến lược session có chủ đích: session store dùng chung (ví dụ Spring Session), sticky session có giới hạn hoặc thiết kế token không dựa session.

Mọi lựa chọn phải kiểm tra logout, timeout, session fixation, rotation, cookie scope và resilience của store. Không mặc định hai deployment có cùng Security config nghĩa là session của chúng tương đương khi topography khác nhau.

## 10. CSP và HSTS: khác biệt triển khai cần tránh nhầm

### 10.1. CSP phải dựa trên tài nguyên mà trang thật sự tải

Ví dụ baseline:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'
```

Policy này có thể chặn script ở CDN, font server, iframe hoặc kết nối API khác origin nếu ứng dụng dùng chúng; mục đích là **kiểm soát nguồn**, không phải phá chức năng. Phải hiểu các directive như `script-src`, `style-src`, `connect-src`, `img-src`, `font-src`, `frame-ancestors` và các nonce/hash khi có script động.

Một SPA ở `https://app.example.com` gọi `https://api.example.com` cần kiểm tra CSP `connect-src` của **trang frontend**. **CORS là chính sách backend**, còn CSP `connect-src` là chính sách mà browser áp dụng dựa trên response **trang frontend**. Chỉnh CORS phía API không tự sửa lỗi CSP trên frontend.

Nếu frontend là một web server/CDN độc lập với Spring Security API, cấu hình CSP **trên Spring API response** không thay thế CSP của trang HTML phục vụ từ CDN. Gắn đúng policy ở nơi phát response. Trong staging, dùng `Content-Security-Policy-Report-Only` để quan sát vi phạm trước khi enforce ở production khi cần; nhưng phải có deadline và regression tests để tránh ở report-only mãi.

### 10.2. HSTS không phải công tắc profile

Spring Security có thể ghi HSTS mặc định trên **HTTPS**; HSTS không nên được mong đợi trên HTTP local. Chính sách production có thể là:

```http
Strict-Transport-Security: max-age=31536000
```

hoặc có thêm `includeSubDomains` khi mọi subdomain đáp ứng HTTPS. `preload` đòi điều kiện nghiêm ngặt và có hậu quả khó đảo ngược nhanh. Nếu staging chạy trên subdomain của một domain production có HSTS `includeSubDomains`, browser vẫn có thể bắt buộc HTTPS đối với staging; việc “tắt HSTS ở staging” không xóa chính sách cha đã ghi nhớ.

**Không đặt `max-age=0` trong profile local rồi đẩy vô tình ra production**: giá trị đó yêu cầu browser xóa trạng thái HSTS cho host, khác hoàn toàn việc local HTTP không phát HSTS.

### 10.3. Security headers khác với cấu hình CDN

Spring Security hỗ trợ `X-Content-Type-Options`, cache control, frame options và HSTS theo default/version. CSP **không có mặc định chung**. CDN/proxy có thể thêm/xóa header hoặc phục vụ static assets mà request không đi qua Spring. Hãy xác định ai sở hữu:

1. CSP của trang HTML/frontend.
2. CORS của API origin.
3. Cache-Control của tài nguyên tĩnh so với dữ liệu riêng tư.
4. HSTS ở public HTTPS edge hoặc backend được cấu hình trusted-forwarding.
5. Cookie flags ở ứng dụng, session infrastructure hoặc ingress.

Một header đúng ở MockMvc nhưng thiếu trên `https://app.example.com` không tự chứng minh Spring Security bị hỏng; có thể tài nguyên được CDN phục vụ. Ngược lại, header xuất hiện ở CDN không chứng minh request đã được Spring Security authorization xử lý.

## 11. Reverse proxy, TLS termination và Forwarded headers

### 11.1. Vì sao Spring Security thấy HTTP trong khi browser thấy HTTPS?

```text
Client HTTPS :443 -----------------> Ingress / proxy
                                       |
                                       | HTTP :8080
                                       v
                                 Spring application

Client sees: scheme=https, host=api.example.com
Backend sees: scheme=http, host=api:8080
```

Một số logic (redirect, absolute URL, secure-request detection, cookie flags, HSTS) cần biết public scheme/host đúng. Proxy có thể gửi `Forwarded: proto=https;host=api.example.com` hoặc `X-Forwarded-Proto: https`. Nhưng nếu ứng dụng **tin giá trị do bất kỳ client ngoài gửi**, attacker có thể giả mạo host/proto hoặc gây redirect sai.

### 11.2. Phải xác định vị trí tin cậy

- Ingress phải **xóa/ghi đè** `Forwarded`/`X-Forwarded-*` do client ngoài tự đặt.
- Backend chỉ chấp nhận traffic từ proxy/trusted network và kiểm soát danh sách proxy/IP.
- Cấu hình forwarded-header strategy phù hợp với Boot version, container và deployment.
- Không lắp đồng thời nhiều cơ chế xử lý forwarded headers gây xử lý lặp/nhân đôi prefix.
- Test redirect/login URL, HSTS, cookie Secure, Host validation, `X-Forwarded-Prefix` và URL rewrite trên HTTPS public.

### 11.3. Tên property thay đổi giữa các dòng Boot

Trong Spring Boot 3.x, tài liệu dùng:

```yaml
# Spring Boot 3.x (kiểm tra nhánh patch cụ thể)
server:
  forward-headers-strategy: framework
```

Trong tài liệu Spring Boot mới hơn, namespace có thể là:

```yaml
# Một số dòng Spring Boot mới: kiểm tra chính xác application-properties
server:
  request:
    header:
      forwarded:
        strategy: framework
```

Không sao chép cả hai property vào cùng YAML rồi đoán cái nào hiệu lực; xác minh tên theo **Spring Boot BOM đã resolve** và kiểm tra binding/condition logs. Khi dùng `framework`, Spring Framework hỗ trợ xử lý forwarded headers, tương ứng `ForwardedHeaderFilter` ở Servlet và `ForwardedHeaderTransformer` ở Reactive. Với container hỗ trợ native, có thể dùng chiến lược native/web-server phù hợp version; đồng thời cấu hình proxy trust đúng để tránh header spoofing.

Đừng dùng header `X-Forwarded-Proto: https` được gửi thẳng từ browser như bằng chứng HTTPS thật. Chỉ header do proxy được tin cậy phát mới có ý nghĩa tại backend.

### 11.4. URL rewrite và security matcher

Một service công khai ở `/portal/api/orders` nhưng ingress rewrite thành `/orders` trước khi gọi backend sẽ khiến Spring Security thường match **đường dẫn backend**. Nếu chain chỉ chọn `securityMatcher("/portal/api/**")`, request có thể không được xử lý như dự kiến.

Kiểm thử cả public URL lẫn đường dẫn backend, context path, servlet path và filter-chain matcher. Với Spring Security 7 Servlet, `PathPatternRequestMatcher` kỳ vọng path trong ứng dụng, bỏ context root; khi có servlet path phải tính đúng prefix. Không nới `/**` với `permitAll` để “chữa” lỗi mismatch.

## 12. HTTP firewall và security chain trong các hạ tầng khác nhau

Khi proxy hoặc container normalize URL khác nhau, các biến thể như `/admin//report`, encoded slash `%2F`, semicolon `;` hoặc path traversal `..` có thể dẫn đến sai lệch giữa route handler và authorization matcher. Spring Security Servlet thường dùng `StrictHttpFirewall`; Reactive dùng `StrictServerWebExchangeFirewall`.

**Bất biến giữa local/staging/prod:** không nới firewall chỉ để vượt qua lỗi 400 ở staging. Tìm nguồn encode URL (frontend, CDN, proxy, container), thống nhất cách diễn giải path, kiểm tra request có thể bị route đến handler nhạy cảm không.

Giữ fallback `SecurityFilterChain`/`SecurityWebFilterChain` bảo vệ các URL còn lại. Nếu một chain chỉ match `/api/**` còn ingress rewrite mất prefix `/api`, không có fallback có thể khiến request đi qua ngoài Spring Security.

Kịch bản kiểm thử:

| Đầu vào | Mục tiêu |
| --- | --- |
| `/admin/report` | USER không thể truy cập, ADMIN được phép |
| `/admin/report/` | Không bypass do trailing slash |
| `/admin//report` | Bị từ chối/normalize an toàn, không bypass |
| `/admin/%2e%2e/public` | Không vượt rule phân quyền |
| `/admin;v=1/report` | Được xử lý đúng firewall/parser policy |
| `/portal/api/orders` trên public ingress | Trúng đúng chain sau rewrite |
| `OPTIONS /orders` từ origin lạ | Không bị cấp CORS allow-origin |

Trong WebFlux, đừng kéo `StrictHttpFirewall` Servlet vào pipeline Reactive. Trong Servlet, đừng tắt toàn bộ `FilterChainProxy` bằng `web.ignoring()` cho asset/public URL nếu vẫn muốn Spring Security ghi headers.

## 13. Kiểm thử có thể tái sử dụng qua các môi trường

### 13.1. Trước tiên kiểm tra cấu hình sau khi bind

Viết test cho `HttpProtectionProperties` để bảo đảm:

- `allowedOrigins` rỗng hoặc có `*` → bị từ chối khi service cần một frontend.
- `https://app.example.com/path` → bị từ chối vì origin có path.
- `https://app.example.com/` → không được coi là exact origin.
- `http://localhost:5173` được chấp nhận ở local (nếu cấu hình local cho phép).
- `http://localhost:5173` trong môi trường prod → bị guardrail chặn.
- CSP trống hoặc HSTS duration âm → bị chặn.
- Thiếu biến `SECURITY_FRONTEND_ORIGIN` trong prod → deployment không khởi động bình thường.

Các test trên nên chạy trong CI với **environment/profile cố định**, không phụ thuộc biến từ máy lập trình viên.

### 13.2. Servlet: test Spring Security, không chỉ controller

Với `MockMvc` đã tích hợp Spring Security, endpoint `POST /orders` trả 200 khi có CSRF token và user hợp lệ:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void servletProtectionContract() throws Exception {
    mvc.perform(get("/public/ping"))
        .andExpect(status().isOk())
        .andExpect(header().exists("Content-Security-Policy"))
        .andExpect(header().string("X-Content-Type-Options", "nosniff"));

    mvc.perform(get("/admin/report")
            .with(user("viewer").roles("USER")))
        .andExpect(status().isForbidden());

    mvc.perform(post("/orders")
            .with(user("viewer").roles("USER")))
        .andExpect(status().isForbidden());

    mvc.perform(post("/orders")
            .with(user("viewer").roles("USER"))
            .with(csrf()))
        .andExpect(status().isOk());
}
```

Đây là khung test trong một class có `MockMvc mvc`, controller và fixture thích hợp. Nếu POST trả 201/204, chỉnh expectation theo hợp đồng HTTP, không thay CSRF policy. Phải gắn `springSecurity()` khi tự tạo MockMvc; test controller không qua filters có thể báo kết quả sai.

### 13.3. Reactive: test cùng hợp đồng với WebTestClient

Với `WebTestClient client` đã bind vào `ApplicationContext` và áp dụng `springSecurity()`:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void reactiveProtectionContract() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("Content-Security-Policy");

    client.mutateWith(mockUser("viewer").roles("USER"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isForbidden();

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

Test giả định handler tồn tại và quyền cho user là phù hợp. `mockUser()` chỉ mô phỏng user ở test bind-to-context; không phải cơ chế đăng nhập thật qua HTTP từ xa.

### 13.4. Preflight và HTTPS public bằng curl

```bash
# CORS đúng origin (dùng endpoint thật thuộc môi trường test)
curl -i -X OPTIONS "https://api.staging.example.com/orders" \
  -H "Origin: https://app.staging.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"

# Origin lạ phải không nhận quyền CORS
curl -i -X OPTIONS "https://api.staging.example.com/orders" \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: POST"

# Header public qua TLS/ingress
curl -i "https://api.staging.example.com/public/ping"
```

Thay `example.com` bằng endpoint mình sở hữu; tránh gửi cookie/token thật trong log. Trong PowerShell, dùng `curl.exe` nếu `curl` là alias của `Invoke-WebRequest`. Khi kiểm tra HSTS, **không** chỉ gọi `http://api:8080` nội bộ. Test spoofed forwarded headers chỉ trong môi trường thử nghiệm đã được ủy quyền và không bao giờ dùng kỹ thuật đó trên hệ thống ngoài phạm vi.

### 13.5. Bảng acceptance nên áp dụng cho mỗi release

| Case | Local | Staging | Production |
| --- | --- | --- | --- |
| Public URL có header CSP/nosniff | Test | Test | Smoke test |
| USER không đọc được `/admin/**` | Test | Test | Smoke test với account riêng |
| POST thiếu/sai CSRF token | 403 | 403 | Kiểm thử được ủy quyền |
| POST token hợp lệ | Qua CSRF | Qua CSRF | Không làm thay đổi dữ liệu thật ngoài test |
| Preflight đúng Origin | Cho phép localhost origin | Cho phép staging origin | Cho phép prod origin |
| Preflight sai Origin | Không cho phép | Không cho phép | Không cho phép |
| Cookie session flags | Phù hợp local | `Secure` và HTTPS | `Secure` và HTTPS |
| HSTS trên HTTPS public | Không bắt buộc nếu HTTP local | Có theo policy | Có theo policy |
| CSP trang frontend/CDN | Test dev UX | Report-only/enforce tùy kế hoạch | Enforce phù hợp |
| URL rewrite/encoded path | Unit/integration | End-to-end qua ingress | Smoke test có kiểm soát |
| Logout/session expiry/replica | Test | Test multi-instance | Monitoring/regression |

## 14. Chẩn đoán lỗi cấu hình theo môi trường

### Lỗi A — Local chạy được nhưng staging bị CORS

**Biểu hiện:** frontend `https://app.staging.example.com` gửi preflight, API trả thiếu `Access-Control-Allow-Origin` hoặc 403.

**Kiểm tra:** giá trị bound `security.http.allowed-origins` có origin staging chính xác không; `Origin` có port/scheme khác không; nguồn CORS Servlet/Reactive đúng package không; filter chain của URL có cấu hình `cors(...)` không; ingress có chặn OPTIONS không. Không sửa bằng `allowedOrigins("*")` hoặc tắt CSRF.

### Lỗi B — Có `Access-Control-Allow-Origin` nhưng browser vẫn không gửi cookie

**Nguyên nhân có thể:** fetch thiếu `credentials: "include"`, server thiếu `Access-Control-Allow-Credentials: true`, cookie sai Domain/Path/Secure/SameSite, browser third-party cookie policy hoặc session đã hết hạn.

**Kiểm tra:** Network tab trên đúng browser và request/response cookie, không chỉ cURL. CORS credential approval khác với việc browser thực tế có cookie hợp lệ để gửi.

### Lỗi C — Login HTTPS bị redirect về HTTP

**Nguyên nhân có thể:** backend không biết scheme public vì TLS terminate ở proxy, forwarded headers không được xử lý hoặc đã bị xử lý sai nhiều lần.

**Kiểm tra:** location header `Location`, proxy trust, Boot forwarded strategy đúng phiên bản, cookie Secure và redirect URL. Không tin `X-Forwarded-Proto` do client tùy ý tự gửi.

### Lỗi D — HSTS ở staging khác production

**Nguyên nhân có thể:** HTTPS public vs HTTP backend, policy CDN riêng, parent-domain HSTS `includeSubDomains`, nhiều writer ghi header hoặc edge chưa triển khai cùng rule.

**Kiểm tra:** `curl -i https://...` qua đường đi thật, nguồn ghi `Strict-Transport-Security`, chính sách HSTS domain cha và timeout/caching. Không suy ra từ test localhost HTTP.

### Lỗi E — CSP chặn API dù CORS đúng

**Biểu hiện:** browser console ghi “Refused to connect ... violates connect-src”.

**Nguyên nhân:** CSP `connect-src` trên response frontend không cho phép API origin. CORS server vẫn có thể đúng. **Cách xử lý:** cập nhật CSP frontend có chủ đích (đúng API origin), giữ allowlist CORS backend và kiểm thử đường gọi thật.

### Lỗi F — CSP chỉ mất ở static assets hoặc trang CDN

**Nguyên nhân:** response không đi qua Spring Security; ingress/CDN phục vụ trực tiếp hoặc Servlet `web.ignoring()`. Cần cấu hình headers ở nơi phát response và kiểm chứng `permitAll()` vs `ignoring()`.

### Lỗi G — POST bị 403 sau lần login thứ hai

**Nguyên nhân:** token cũ bị xóa/rotated, deferred CSRF loading, SPA chưa nhận token mới, cookie/session khác do đổi domain hoặc load balancing nhiều replica.

**Kiểm tra:** CSRF repository, token request handler, cookie scope, session store, login/logout events; phân biệt CSRF denial với authorization denial.

### Lỗi H — Một số URL nhạy cảm thành public ở môi trường mới

**Nguyên nhân:** ingress rewrite prefix, servlet context/servlet path khác hoặc thiếu fallback chain; matcher `securityMatcher("/api/**")` không bao phủ URL backend đã rewrite.

**Kiểm tra:** `@Order` và matcher của mọi chain, selected chain logs, request path thực tế, firewall/normalization; test USER/ADMIN qua ingress.

### Lỗi I — Production vô tình nhận localhost origin

**Nguyên nhân:** profile sai, môi trường CI tái sử dụng property local, biến môi trường được ưu tiên hơn file config hoặc validation thiếu.

**Cách xử lý:** guardrail fail closed, allowlist domain production trong deployment manifest, kiểm tra effective configuration và chạy smoke test sau promote. Không chỉ dựa vào tên `prod`.

## 15. Quy trình thay đổi và phát hành cấu hình bảo mật

1. **Xác định phiên bản đã resolve.** Ghi Spring Boot, Spring Framework, Spring Security, JDK và Servlet/WebFlux; kiểm tra BOM/dependency overrides. Tên property và DSL có thể khác giữa Boot 3/4 và Security 6/7.
2. **Xác định public request path.** Ghi public frontend/API origin, port, path rewrite, TLS termination và trusted proxy range.
3. **Phân loại theo môi trường.** Chỉ origin và các tham số hạ tầng được khác, còn authorization, CSRF, strict firewall và rule chung phải bền vững.
4. **Đưa dữ liệu vào externalized config.** Không lưu password/private key/token trong source YAML; dùng secret manager/secret store với chính sách cấp quyền.
5. **Kiểm tra ngay khi khởi động.** Reject origin wildcard, URL có path, CSP rỗng, origin không HTTPS ở prod và các ràng buộc domain/port/credential.
6. **Cấu hình adapter theo stack.** Servlet `SecurityFilterChain` + Servlet Cors source; WebFlux `SecurityWebFilterChain` + Reactive Cors source.
7. **Chạy test CI ở nhiều cấu hình.** Kiểm thử binding local/staging/prod, origin đúng/sai, CSRF token, authorization, CSP/HSTS và session.
8. **Triển khai staging giống topology production.** Có ingress/TLS, session store, cookie policy và proxy trust tương tự; kiểm tra multi-replica.
9. **Canary/promote có quan sát.** Theo dõi lỗi 401/403, preflight failures, CSP violation, bất thường logout/session và header regression; không log token/cookie.
10. **Có rollback.** Rollback không chỉ quay code mà còn phải quản lý config, secret rotation, CDN cache, cookie/domain và HSTS lâu dài.

**Không xem “chạy thành công với `SPRING_PROFILES_ACTIVE=prod`” là chứng nhận an toàn.** Phải kiểm chứng HTTP response, chọn chain, proxy, browser và lifecycle credential trong môi trường public.

## 16. Bài tập thực hành

### Bài 1 — Kiểm tra origin theo ba môi trường

Tạo `application-local.yml`, `application-staging.yml`, `application-prod.yml` với origin tương ứng như bảng ở mục 1. Định nghĩa `HttpProtectionProperties` và thêm kiểm thử các giá trị:

- `https://app.example.com` → hợp lệ cho prod.
- `http://localhost:5173` → hợp lệ cho local nhưng bị prod guardrail từ chối.
- `https://app.example.com/dashboard` và `https://app.example.com/` → bị từ chối vì không phải exact origin.
- `*` → bị từ chối.
- thiếu `SECURITY_FRONTEND_ORIGIN` → service không được ready trong prod.

Giải thích vì sao validation có giá trị hơn cách tự động chuyển sang wildcard khi cấu hình thiếu.

### Bài 2 — CORS đúng nhưng cookie vẫn bị chặn

Giả sử frontend `https://app.other-example.net` gọi `https://api.example.com` bằng `fetch(..., {credentials: "include"})`. Server trả đúng CORS allow-origin/allow-credentials nhưng browser không gửi session cookie. Hãy phân tích `SameSite=None; Secure`, cookie Domain/Path, third-party cookie restrictions và lỗi scheme/port.

So sánh với frontend `https://app.example.com` gọi `https://api.example.com`: hai origin khác nhau nhưng có thể same-site.

### Bài 3 — HSTS và reverse proxy

Staging có HTTPS công khai nhưng backend HTTP. Khi gọi localhost, không thấy HSTS; khi gọi public đôi khi có header. Thiết kế ba phép kiểm tra để xác định nguồn ghi HSTS, trusted forwarded headers, proxy redirect và scheme detection; tránh việc chấp nhận header do client giả mạo.

### Bài 4 — Hai stack, cùng chính sách

Tạo một ứng dụng Servlet và một ứng dụng WebFlux độc lập dùng cùng record `HttpProtectionProperties`. Hai ứng dụng có `/public/ping` công khai, `/admin/report` yêu cầu ADMIN, `POST /orders` yêu cầu CSRF với cookie session, và CORS allowlist staging. Viết test MockMvc/WebTestClient và cURL preflight để chứng minh policy tương đương dù implementation khác nhau.

### Bài 5 — CSP frontend khác CORS backend

Trang `https://app.example.com` tải từ CDN và gọi `https://api.example.com`. Browser báo CSP `connect-src` bị vi phạm, không có CORS error. Hãy xác định ai sở hữu CSP header, thêm API origin vào `connect-src` một cách kiểm soát, rồi giữ nguyên CORS backend. Giải thích vì sao chỉ thay API CORS không sửa được lỗi.

### Bài 6 — Load balancing và CSRF/session

Triển khai hai replicas, mỗi pod giữ session trong memory. Login qua pod A thành công; POST tiếp theo trúng pod B bị 403 vì token/session không tồn tại. Đề xuất shared session store hoặc chiến lược thích hợp, và bổ sung test login/logout/token refresh qua nhiều replica.

## 17. Checklist trước khi go-live

- [ ] Biết rõ public origins (scheme/host/port) và internal backend addresses; không đưa path vào CORS allowlist.
- [ ] Đã xác định same-origin/same-site/cross-site; không tự dùng `SameSite=None` chỉ vì khác subdomain.
- [ ] Không có profile nào tự tắt CSRF, auth, headers hay firewall trong deployment public.
- [ ] Properties thiếu/sai (wildcard, HTTP prod, CSP trống) làm startup hoặc readiness thất bại.
- [ ] Secret/credential không nằm trong source YAML, build artifact hay log.
- [ ] Chọn đúng Servlet/Reactive CORS source; kiểm tra origin đúng/sai bằng preflight thực.
- [ ] CSRF token và session/login/logout hoạt động với cookie browser, kể cả qua nhiều replica.
- [ ] CSP đúng trên **response frontend HTML**, `connect-src` cho phép API cần thiết, report-only/enforce có kế hoạch.
- [ ] HSTS kiểm tra qua HTTPS public; `includeSubDomains`/`preload` có đánh giá vận hành.
- [ ] Proxy xử lý forwarded headers theo Boot version và chỉ tin proxy đáng tin; URL/redirect không bị host/proto spoofing.
- [ ] Firewall và fallback chain bảo vệ encoded/rewritten paths, admin routes và các endpoint vận hành nhạy cảm.
- [ ] Cookie `Secure`/`HttpOnly`/`SameSite`/`Domain`/`Path` được quan sát bằng browser và HTTP response.
- [ ] Có test CI và smoke test staging/prod cho 401/403, CORS, CSRF, CSP, HSTS và session.
- [ ] Có giám sát, kế hoạch rollback và người chịu trách nhiệm cập nhật allowlist/domain/HSTS.

## Tài liệu tham khảo chính thức

1. [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html) — profile activation, profile-specific configuration, profile group và thứ tự nguồn cấu hình.
2. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html) — property sources, environment variables, configuration binding và quản lý giá trị runtime.
3. [Spring Boot — Embedded Web Servers / Reverse Proxy](https://docs.spring.io/spring-boot/how-to/webserver.html) — forwarded headers và các chiến lược nhận public scheme/host; phải đối chiếu đúng nhánh Boot đang chạy.
4. [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html) — `server.forward-headers-strategy` cho dòng 3.x.
5. [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html) — session cookie, `SameSite` và tùy chỉnh embedded container.
6. [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html) — tra cứu thuộc tính `server.servlet.session.*` / `server.reactive.session.*` đúng phiên bản.
7. [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html) và [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — nguồn CORS, preflight và per-chain configuration.
8. [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) và [Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — session, CSRF token repository, SPA/BREACH và login/logout.
9. [Spring Security — Servlet Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) và [Reactive Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — CSP, HSTS, cache và clickjacking.
10. [Spring Security — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html) và [Reactive HTTP Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — request normalization và kiểm soát URL bất thường.

**Câu hỏi tự đánh giá:** Browser gửi `Origin` nào khi frontend ở `https://app.example.com` còn backend nội bộ là `http://api:8080`? Vì sao hai origin khác nhau vẫn có thể same-site? Vì sao CORS thành công không chứng minh cookie sẽ được browser gửi? HSTS phải được đo ở đâu khi TLS terminate ở ingress? Và điều gì khiến cấu hình local không thể vô tình mở quyền trong production?
