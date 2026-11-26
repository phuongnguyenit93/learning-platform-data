# Quản lý cấu hình bảo vệ theo môi trường và phiên bản

## Mục tiêu và bối cảnh

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, ứng dụng Spring Security được bảo vệ bằng nhiều lớp: **CSRF**, **CORS**, **HTTP security headers**, **Content Security Policy (CSP)**, **HTTP Strict Transport Security (HSTS)**, **HTTP firewall** và **session/cookie protection**. Việc viết đúng một **SecurityFilterChain** trong môi trường phát triển chưa đủ để đảm bảo ứng dụng vẫn an toàn ở staging, production hoặc sau một lần nâng cấp Spring Boot/Spring Security.

Bài **“Quản lý cấu hình bảo vệ theo môi trường và phiên bản”** tập trung vào vòng đời vận hành: **định nghĩa policy → khai báo cấu hình → build/test → phát hành → giám sát → phát hiện sai lệch → sửa hoặc rollback**. Bài áp dụng cho cả **Servlet** và **Reactive/WebFlux**, đồng thời xét lớp proxy/gateway/CDN, TLS termination và cấu hình trình duyệt ở frontend.

Các mục tiêu sau khi học:

1. Xây dựng **ma trận kiểm soát bảo mật** theo môi trường (local, CI, staging, production) và theo phiên bản.
2. Phân biệt **cấu hình mong muốn** trong Git, **cấu hình hiệu lực** khi ứng dụng chạy, và **hành vi quan sát** ở browser/edge.
3. Sử dụng Spring Boot externalized configuration và profiles mà không đặt các cơ chế phòng vệ quan trọng vào trạng thái tắt tùy tiện.
4. Cấu hình CSRF, CORS, CSP, HSTS, cookie/session và HTTP firewall trên **Servlet** lẫn **WebFlux**.
5. Quản lý dependency bằng BOM, kiểm tra thay đổi API qua phiên bản và chạy regression tests trước khi nâng cấp.
6. Thiết kế kiểm thử **fail-closed**, phát hiện wildcard CORS, mất CSRF, thiếu security headers và lỗi proxy HTTPS.
7. Giám sát drift, đo chất lượng rollout, định nghĩa cảnh báo, có runbook xử lý và rollback kiểm soát.
8. Tránh đưa cookie, JWT, CSRF token hoặc dữ liệu nhạy cảm vào log, metrics labels và cấu hình được công khai.

### Thuật ngữ sử dụng

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Policy** | Quy tắc an toàn mong muốn: ai được truy cập, dùng cookie ra sao, bật CSRF/CSP/HSTS thế nào |
| **Configuration** | Cách diễn đạt policy thành properties, Java SecurityFilterChain, gateway rules và manifests |
| **Effective configuration** | Cấu hình thực sự có hiệu lực sau precedence, profiles, conditionals, filter-chain matchers và môi trường runtime |
| **Configuration drift** | Sai lệch giữa cấu hình chuẩn đã phê duyệt và trạng thái thực tế ở pod/instance/gateway |
| **Version matrix** | Bảng ràng buộc Spring Boot, Spring Framework, Spring Security, Java và dependency test |
| **Fail closed** | Nếu cấu hình bắt buộc thiếu/sai, từ chối khởi động hoặc từ chối thao tác thay vì tự mở quyền |
| **Canary rollout** | Triển khai một phần nhỏ lưu lượng để quan sát trước khi mở rộng |
| **Rollback** | Quay lại artifact/cấu hình đã biết tốt; không mặc định rollback sẽ đảo ngược dữ liệu hoặc session đã thay đổi |

## 1. Vì sao cấu hình bảo vệ phải được quản lý như một sản phẩm vận hành?

Một ứng dụng có thể hoạt động ở local nhưng gặp những tình huống sau khi triển khai:

- **CSRF**: dev tắt CSRF cho tiện gọi Postman rồi một profile production vô tình kế thừa cấu hình đó.
- **CORS**: bản đầu chỉ cho origin frontend thật, bản hotfix mở wildcard hoặc phản chiếu mọi Origin cùng credentials để “hết lỗi”.
- **HSTS**: proxy terminate HTTPS nhưng backend thấy HTTP nên thiếu HSTS trên response HTTPS ở edge.
- **CSP**: policy thay đổi theo CDN hoặc release frontend, một lần sửa script nguồn ngoài làm website trắng trang hoặc mở rộng nguồn script không được review.
- **Session**: cookie Secure/HttpOnly/SameSite khác nhau giữa instance; user login được ở pod A nhưng logout hoặc refresh thất bại trên pod B.
- **HTTP firewall**: gateway và Spring Security xử lý encoded slash, semicolon hoặc URL normalization khác nhau dẫn tới 400/403 hoặc bypass matcher.
- **Dependency**: nâng Spring Security nhưng một module spring-security-config cũ nằm trong runtime classpath, gây lỗi method hoặc thay đổi default bảo vệ.
- **Observability**: tăng debug level toàn bộ security chain và vô tình ghi token, Cookie, Authorization header hoặc nội dung user request.
- **Rollback**: quay lại build cũ nhưng không quay lại policy config/CDN tương ứng, hệ thống vẫn sai.

Những vấn đề này ít khi nằm ở một dòng code duy nhất. Cần một cơ chế chứng minh tính nhất quán của **artifact, environment, runtime policy, security chain và hạ tầng HTTP**.

### 1.1. Bốn lớp cần đối chiếu

~~~mermaid
flowchart LR
    A["Chính sách đã duyệt"] --> B["Git và cấu hình khai báo"]
    B --> C["Ứng dụng Spring Security"]
    C --> D["Proxy, CDN và hạ tầng TLS"]
    D --> E["Browser/mobile client thực"]
    E --> F["Test, metrics, security events"]
    F --> G["Phát hiện drift / cảnh báo"]
    G --> A
~~~

Cấu hình “đúng” phải kiểm chứng ở cả các lớp:

1. **Source-of-truth**: rule trong Git và đặc tả policy được review.
2. **Resolved runtime**: property nào thắng, active profiles nào, filter chain nào nhận request.
3. **Wire behavior**: header/cookie từ **điểm truy cập người dùng thật** có đúng không.
4. **Security outcome**: request giả mạo, không đủ quyền hoặc sai origin thực sự bị từ chối mà không tạo side effect.

### 1.2. Phân biệt bug chức năng và lỗ hổng bảo vệ

| Triệu chứng | Có thể là | Cách xác minh |
| --- | --- | --- |
| SPA POST trả 403 | CSRF token sai, role thiếu hoặc chain không khớp | Exception type, token flow, auth state, matcher |
| OPTIONS trả 401 | CORS preflight bị authentication chặn | Gửi OPTIONS không Cookie, kiểm tra CORS filter |
| Login loop production | Cookie SameSite/Secure/Domain hoặc reverse proxy | Browser Network/Storage và forwarded scheme |
| Thiếu HSTS | Backend/proxy trả header sai ở HTTPS edge | Kiểm tra response từ domain public |
| Browser báo CSP violation | Chính sách chặn tài nguyên cần thiết hoặc mã không tuân CSP | Report-only, console và resource inventory |
| Pod A khác pod B về CORS | Drift cấu hình hoặc phiên bản | Config checksum/deployment revision và test từng pod |
| Upgrade chạy được nhưng mất CSRF | Default/DSL thay đổi hoặc SecurityFilterChain khác | Regression test request thiếu token |
| 403 tăng sau release | Cấu hình sai, token lifecycle hoặc đợt tấn công | Correlate release, route, error class; không nới rule ngay |

Đừng biến một lỗi chức năng thành lý do tắt bảo vệ trên toàn ứng dụng. Cần phân loại nguyên nhân rồi điều chỉnh **phạm vi nhỏ nhất**.

## 2. Định nghĩa policy baseline và ma trận theo môi trường

**Baseline** là tập yêu cầu an toàn áp dụng ở mọi môi trường khi cùng phục vụ một loại luồng xác thực. Dev có thể dùng origin localhost, certificate nội bộ hoặc dữ liệu giả; nhưng **không nên tắt CSRF, authorization hay cookie protection chỉ vì đang phát triển** nếu điều đó làm mất khả năng kiểm thử production.

### 2.1. Ma trận ví dụ

| Kiểm soát | Local development | CI/integration | Staging | Production |
| --- | --- | --- | --- | --- |
| CSRF trên route cookie-authenticated | Bật, dùng token test | Bật, có negative tests | Bật như production | Bật và giám sát lỗi |
| Bearer-only API | Chính sách riêng, không cookie fallback | Test JWT invalid/scope | Kiểm tra auth thực | JWT validation, scope, authz |
| CORS có credentials | Exact localhost HTTPS origin | Origin test được chỉ định | Exact staging frontend | **Exact production frontend allowlist** |
| CSP cho HTML | Report-only nếu đang tích hợp | Kiểm tra syntax/source | Report-only hoặc enforce tương đương prod | Enforce với nguồn đã duyệt, báo cáo có scrub |
| HSTS | Tùy hostname HTTPS local | Test ở HTTPS environment | Kiểm tra HTTPS edge | Bật sau khi xác nhận HTTPS và subdomain readiness |
| Session cookie | HttpOnly; HTTPS/Secure khi có HTTPS local | Test attributes | Secure + HttpOnly, SameSite phù hợp | Secure + HttpOnly, SameSite và rotation chuẩn |
| HTTP firewall | Giữ mặc định nghiêm ngặt | Negative tests URL bất thường | Kết hợp gateway/proxy | Không relax quy tắc khi chưa phân tích |
| Sensitive logging | Không dump token thật | Synthetic canary, redaction | Có log sampling an toàn | Allowlist metadata, retention và quyền truy cập |
| Dependency | Version được pin qua BOM | Lock/resolve & scan | Cùng artifact với production | Chỉ release đã kiểm chứng |
| Rollback | Bản đã biết tốt | Kiểm thử mô phỏng | Canaries và diễn tập | Runbook + owner + health gates |

**Staging phải đủ gần production về chính sách**, không chỉ gần về UI và database. Nếu staging bỏ qua WAF, proxy TLS, cookie domain hoặc CSRF, các lỗi quan trọng sẽ chỉ xuất hiện sau khi phát hành.

### 2.2. Invariants không được phá bởi profile

Chọn các **security invariants** có thể test tự động:

- Route nào chấp nhận **cookie authentication** và thay đổi trạng thái thì **CSRF phải bật** trừ ngoại lệ được phê duyệt cụ thể.
- Không dùng wildcard **Access-Control-Allow-Origin** với credentialed CORS.
- Cookie xác thực production phải có **Secure** và **HttpOnly**; SameSite phù hợp với kiến trúc browser.
- Trang HTML cần CSP phải được xác định rõ **origin nào phục vụ HTML**; CSP cấu hình ở API khác origin không tự bảo vệ trang SPA.
- Không log session ID, JWT, access/refresh token, CSRF token hoặc request body nhạy cảm.
- Các route quản trị và actuator nội bộ không tự trở thành public chỉ vì đổi profile.
- Runtime dependency Spring Security phải nhất quán, không trộn module major/minor ngoài BOM đã duyệt.
- Ứng dụng không khởi động nếu origin production bắt buộc bị thiếu hoặc cấu hình có wildcard không được phép.

### 2.3. Khi nào được có ngoại lệ?

Một số ngoại lệ thực tế:

- **localhost HTTP** cho thử nghiệm hạn chế: cần test HTTPS song song; không làm suy yếu production config vì dev.
- **CSP Report-Only** trong rollout chính sách mới: phải có thời hạn, owner và tiêu chí chuyển enforce.
- **CSRF exception** cho một webhook machine-to-machine **thực sự không dùng cookie/browser credential** và có cơ chế xác thực riêng: chỉ áp vào đúng path/method, có test và audit.
- **HSTS includeSubDomains** chưa triển khai nếu một số subdomain cũ chưa hỗ trợ HTTPS: lên kế hoạch khắc phục, không tuyên bố đã hoàn thành yêu cầu bảo vệ toàn domain.

Một ngoại lệ cần lưu **lý do, phạm vi, owner, thời hạn và cách kiểm chứng**. Không dùng nhãn “temporary” cho cấu hình tồn tại vô thời hạn.

## 3. Cấu hình thực tế: Git, Spring Boot properties, profile và secret manager

**Spring Boot externalized configuration** cho phép cùng artifact chạy ở nhiều môi trường. Nhưng profile và property precedence làm thay đổi giá trị hiệu lực: một biến môi trường, command-line argument hoặc cấu hình được mount có thể override file application.yaml.

### 3.1. Tách cấu hình theo bản chất

| Nhóm | Ví dụ | Nơi lưu phù hợp |
| --- | --- | --- |
| Security policy không bí mật | Allowed CORS origins, CSP directives, public HSTS max-age | Git + review + deploy config |
| Secret | OAuth client secret của confidential client, signing key, database password | Secret manager/KMS/vault với quyền tối thiểu |
| Định danh công khai | JWT issuer, JWK Set URL, API hostname | Config có validation theo environment |
| Quy tắc ở gateway | TLS redirect, cache bypass, header normalization | Infra as Code cùng release control |
| Feature flags | CSP Report-Only rollout, audit verbosity | Flag có TTL, owner và guardrail |
| Emergency overrides | Tắt một integration bị lỗi, thay allowlist có kiểm soát | Quy trình change management, audit và tự hết hạn |

**Không lưu secrets trong public Git, log hoặc cấu hình phản hồi qua Actuator.** Environment variables cũng có thể bị lộ qua dump, process inspection hoặc công cụ quản trị; dữ liệu đặc biệt nhạy cảm nên dùng secret manager có rotation và access control.

### 3.2. Những nguyên tắc precedence

Một ứng dụng có thể nhận cấu hình từ nhiều nguồn như config files, biến môi trường, Java system properties hoặc CLI args. **Không đoán chỉ bằng việc đọc application.yaml**. Cần xác minh resolved effective value trong môi trường chạy bằng cơ chế có kiểm soát.

Ví dụ:

~~~text
Git application.yaml:      app.security.allowed-origins=[https://app.example.com]
Deployment environment:    APP_SECURITY_ALLOWED_ORIGINS=...
Command-line override:    --app.security.allowed-origins=...
Actual policy in runtime:  giá trị có precedence cao nhất theo Spring Boot
~~~

**Không công khai toàn bộ Spring Environment hoặc /actuator/env** để debug precedence: những endpoint đó có thể bộc lộ cấu hình nhạy cảm hoặc metadata nội bộ. Nếu bật Actuator, giới hạn network, authentication, RBAC và chỉ cho phép thông tin vận hành cần thiết.

### 3.3. Tránh bật/tắt bảo vệ bằng một Boolean chung

Một flag như **security.enabled=false** là dấu hiệu nguy hiểm: nó có thể vô hiệu hóa authentication, CSRF, CORS validation và headers cùng lúc.

Thay vào đó:

- Giữ **policy bất biến** ở các route cần bảo vệ.
- Tách đúng **authentication contract** nếu route thực sự Bearer-only hoặc machine-to-machine.
- Cấu hình per-environment những giá trị **được phép thay đổi**: origin cụ thể, host URL, trusted proxy, CSP endpoint báo cáo.
- Chỉ cho phép ngoại lệ có đánh giá bảo mật; đặt negative tests để chứng minh phần còn lại vẫn được bảo vệ.
- Thất bại khi config production bị rỗng hoặc sai cú pháp; không fallback sang “allow all”.

## 4. Một mẫu application.yaml đa môi trường, an toàn theo mặc định

Ví dụ dưới đây dành cho một ứng dụng **Spring Boot 3.x / Spring Security 6.x dùng session cookie cho browser**. Đây là **mẫu khởi đầu**, cần thay hostname và đánh giá kiến trúc thực tế.

~~~yaml
# application.yaml -- baseline và các profile override được review
spring:
  application:
    name: protection-service

server:
  servlet:
    session:
      cookie:
        http-only: true
        secure: true
        same-site: lax

app:
  security:
    allowed-origins:
      - "https://app.example.com"
    csp-policy: "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
---
spring:
  config:
    activate:
      on-profile: dev

app:
  security:
    allowed-origins:
      - "https://localhost:5173"
    csp-policy: "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
---
spring:
  config:
    activate:
      on-profile: staging

app:
  security:
    allowed-origins:
      - "https://app.staging.example.com"
---
spring:
  config:
    activate:
      on-profile: prod

app:
  security:
    allowed-origins:
      - "https://app.example.com"
~~~

**Cần lưu ý:**

1. **Baseline không tắt CSRF**, không để CORS wildcard, không dùng secret trong YAML.
2. Dev sử dụng **HTTPS localhost** để kiểm thử Secure cookie và browser behavior gần production.
3. **Staging chỉ khác hostname**, không khác CSRF policy.
4. Production không được chỉ dựa vào profile name để an toàn: deployment pipeline còn phải xác nhận origin allowlist, cookie attributes, chain matchers và TLS readiness.
5. Thuộc tính **server.servlet.session.cookie...** dành cho Servlet. WebFlux/WebSession có cơ chế cấu hình cookie session khác; không copy property Servlet rồi mặc định đã bảo vệ WebFlux.
6. **CSP trên backend chỉ ảnh hưởng response do backend phục vụ**. Nếu SPA HTML được phục vụ từ một domain/CDN riêng, cấu hình CSP trên **origin của HTML** hoặc gateway phục vụ HTML đó.
7. HSTS chỉ gửi khi response HTTPS thực sự phù hợp; nếu proxy terminate TLS, cần kiểm tra header trên response từ **public edge**, không chỉ backend localhost.
8. Khi cùng app có nhiều CORS origins, phải xem xét từng origin đáng tin; không thêm wildcard để sửa nhanh preflight lỗi.

### 4.1. Properties là giá trị đầu vào, không phải policy hoàn chỉnh

YAML chỉ cung cấp tham số. Runtime vẫn cần xác minh:

- Có đúng **CorsConfigurationSource** dùng allowed-origins đó không?
- CORS filter có chạy **trước authentication** cho OPTIONS?
- Route browser có **CsrfFilter** hay bị một SecurityFilterChain khác bắt trước?
- CSP có được gắn vào response HTML thật không?
- Secure/SameSite có xuất hiện trong **Set-Cookie ở edge** không?
- Gateway có override Access-Control-Allow-Origin hoặc Cache-Control không?
- Có SecurityFilterChain nào vô tình không match request nhạy cảm không?

Đó là lý do cần tests thực, không chỉ kiểm tra chuỗi YAML.

## 5. Định nghĩa chính sách typed và fail-fast trong Spring Boot

Để giảm lỗi chính tả và cấu hình rỗng, bind allowed origins/CSP bằng **@ConfigurationProperties** thay vì copy string trực tiếp trong nhiều SecurityFilterChain.

### 5.1. Record configuration properties

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.security")
public record WebProtectionProperties(
        List<String> allowedOrigins,
        String cspPolicy) {

    public WebProtectionProperties {
        if (allowedOrigins == null || allowedOrigins.isEmpty()) {
            throw new IllegalArgumentException(
                "CORS allowedOrigins must not be empty");
        }
        for (String origin : allowedOrigins) {
            if (origin == null || origin.isBlank()
                    || "*".equals(origin)
                    || origin.contains("*")
                    || !isAbsoluteHttpOrigin(origin)) {
                throw new IllegalArgumentException(
                    "Invalid CORS allowed origin configuration");
            }
        }
        if (cspPolicy == null || cspPolicy.isBlank()) {
            throw new IllegalArgumentException(
                "CSP policy must not be blank");
        }
    }

    private static boolean isAbsoluteHttpOrigin(String value) {
        try {
            URI uri = URI.create(value);
            String scheme = uri.getScheme();
            return uri.getHost() != null
                && ("https".equalsIgnoreCase(scheme)
                    || "http".equalsIgnoreCase(scheme))
                && (uri.getRawPath() == null
                    || uri.getRawPath().isEmpty())
                && uri.getRawQuery() == null
                && uri.getRawFragment() == null
                && uri.getUserInfo() == null;
        } catch (IllegalArgumentException ex) {
            return false;
        }
    }
}
~~~

Đây là validation **mức khởi đầu**, không thay cho parser/validation toàn diện theo RFC: cần giới hạn hostname được phép trên production, chuẩn hóa IPv6/punycode/port, cấm HTTP ngoài localhost nếu policy yêu cầu, và không cho origin null. Điều quan trọng là **khi policy rỗng/sai, ứng dụng fail startup**, thay vì tự mặc định sang allow-all.

Trong hệ thống thực có thể dùng **Jakarta Bean Validation** cùng **@Validated** và custom validator kiểm tra exact origin allowlist.

### 5.2. Kết nối typed policy với cấu hình Servlet

Bean WebProtectionProperties có thể được đăng ký qua **@EnableConfigurationProperties(WebProtectionProperties.class)** trên configuration class. Sau đó tạo CORS source và SecurityFilterChain dùng chung một nguồn tham số đã được kiểm tra.

Tránh có ba bản sao origin list trong **application.yaml, @CrossOrigin, custom filter**: khi một nguồn được thay đổi mà nguồn khác không đổi, hành vi CORS có thể khó dự đoán. Nên chọn một nơi làm nguồn chính cho browser-facing API.

## 6. Servlet: nối policy vào CORS, CSRF, headers và HTTP firewall

Các ví dụ dùng **Spring Security 6.x, Spring Boot 3.x, Java 17+** cho Servlet và browser authentication bằng session cookie. Các API minor version thực tế phải được build và kiểm thử theo BOM đã chốt.

### 6.1. CORS source dùng allowlist đã validate

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
@EnableConfigurationProperties(WebProtectionProperties.class)
class ServletCorsConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource(
            WebProtectionProperties policy) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(policy.allowedOrigins());
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(true);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        source.registerCorsConfiguration("/login", cors);
        source.registerCorsConfiguration("/logout", cors);
        return source;
    }
}
~~~

**Preflight OPTIONS không mang session cookie như request POST thực tế.** CORS phải được tích hợp trước authentication. Exact origin allowlist cùng credentials là bắt buộc; không dùng **Access-Control-Allow-Origin: *** hoặc phản chiếu mọi Origin.

Nếu SPA gọi login/logout cross-origin, CORS source cần bao phủ đúng path của các endpoint này; chỉ đăng ký /api/** không tự bảo vệ/hỗ trợ /login hoặc /logout. Đừng cấu hình chồng @CrossOrigin, custom CorsFilter, Gateway và Spring Security để mọi tầng đều tự đặt một tập Allow-Origin khác nhau mà không có owner.

### 6.2. SecurityFilterChain với CSRF và các header đã phê duyệt

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletHttpSecurityPolicy {

    @Bean
    SecurityFilterChain browserChain(
            HttpSecurity http,
            WebProtectionProperties policy) throws Exception {
        return http
            .cors(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(policy.cspPolicy()))
                .httpStrictTransportSecurity(hsts -> hsts
                    .includeSubDomains(true)
                    .maxAgeInSeconds(31536000))
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/assets/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .build();
    }
}
~~~

**Đây là mã minh họa**, không phải toàn bộ policy của một hệ thống thực:

- **CSRF:** Được giữ cho unsafe methods của cookie-authenticated browser; không tắt toàn chain để sửa lỗi SPA POST 403.
- **CORS:** Dùng source đã validate. Nếu nhiều SecurityFilterChain hoặc nhiều CorsConfigurationSource, phải gắn đúng source/chain và test OPTIONS.
- **CSP:** Header trên JSON API **không tự bảo vệ trang HTML của SPA được serve ở origin khác**. Triển khai CSP trên chính origin phục vụ document HTML.
- **HSTS:** Chỉ bật includeSubDomains khi mọi subdomain thuộc phạm vi đã sẵn sàng HTTPS; kiểm tra response tại public HTTPS edge.
- **Security headers:** Spring Security cung cấp nhiều default headers, nhưng CSP là policy do ứng dụng chọn; đừng coi starter tự giải quyết mọi directive.
- **Authorization:** anyRequest().denyAll() minh họa fail-closed. Một website thật cần khai báo public/static/actuator paths và quyền chi tiết đúng nghiệp vụ.
- **formLogin:** Mặc định hỗ trợ form và redirect; SPA dùng JSON login cần authentication handlers và hợp đồng khác.
- **Token cache:** GET /api/csrf phải dùng Cache-Control: no-store và proxy bypass, không chỉ dựa vào header mặc định.

### 6.3. Endpoint token theo session, không cache công khai

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ServletCsrfBootstrapController {

    record CsrfPayload(String headerName, String token) {}

    @GetMapping("/api/csrf")
    ResponseEntity<CsrfPayload> csrf(HttpServletRequest request) {
        CsrfToken token = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("CSRF filter not configured");
        }

        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(new CsrfPayload(
                token.getHeaderName(), token.getToken()));
    }
}
~~~

Trong Spring Security 6.x, request attribute có thể chứa **XOR-masked token**. SPA lấy token JSON phải gửi nguyên giá trị về đúng header và dùng handler tương thích. Không ghép JSON masked với handler chỉ nhận raw token từ cookie mà không sửa hợp đồng.

**GET permitAll không cấp authentication**. Cookie phiên cần HttpOnly/Secure/SameSite và browser gửi nó trong GET/POST tùy credentials/cookie policy. Không log JSON CSRF token, không đặt token trong query string hoặc trace ID.

### 6.4. StrictHttpFirewall, path matching và proxy normalization

Spring Security Servlet sử dụng HTTP firewall kiểm tra request bất thường. **Đừng nới StrictHttpFirewall trên production** chỉ vì một route legacy có encoded slash, semicolon hoặc path normalization khác gateway.

Khi xuất hiện 400/403:

1. Xác minh URL browser gửi, URL sau gateway rewrite và URL Spring nhận.
2. So sánh canonicalization, encoded segments và Servlet MVC matcher.
3. Đánh giá nguy cơ path traversal hoặc bypass securityMatcher/authorization.
4. Ưu tiên sửa đường dẫn/encoding contract; nếu thực sự phải tùy chỉnh firewall, cần security review và negative tests.
5. Triển khai cùng policy qua tất cả instance; không cho pod A nhận URL mà pod B chặn.

**StrictHttpFirewall là thành phần Servlet**, không copy vào WebFlux như một API tương đương. Trên Reactive phải đánh giá HTTP parser, route matching và gateway normalization riêng.

### 6.5. Cookie/session của Servlet

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

SameSite=Lax phù hợp với nhiều trường hợp SPA và API **khác origin nhưng cùng site** qua HTTPS. Nếu hai bên khác site, cookie có thể cần SameSite=None; Secure nhưng vẫn chịu third-party cookie restrictions.

Các environment thực còn phải tính login/logout session rotation, distributed session store, TTL, cookie Domain/Path, proxy HTTPS và các browser cụ thể. Không đặt HttpOnly=false cho session cookie chỉ để frontend đọc CSRF token.

## 7. Reactive/WebFlux: cùng policy nhưng khác API, session và HTTP stack

WebFlux dùng **ServerHttpSecurity**, **SecurityWebFilterChain**, **CsrfWebFilter**, **ServerWebExchange**, **WebSession** và **Mono<CsrfToken>**. Không copy HttpServletRequest/StrictHttpFirewall hoặc property server.servlet.session.cookie vào Reactive app rồi giả định có hiệu lực.

### 7.1. Reactive CorsConfigurationSource

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveWebCorsConfiguration {

    @Bean
    CorsConfigurationSource reactiveCorsSource(
            WebProtectionProperties policy) {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(policy.allowedOrigins());
        cors.setAllowedMethods(List.of(
            "GET", "POST", "PUT", "PATCH", "DELETE"));
        cors.setAllowedHeaders(List.of(
            "Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        source.registerCorsConfiguration("/login", cors);
        source.registerCorsConfiguration("/logout", cors);
        return source;
    }
}
~~~

**Package reactive rất quan trọng**: không import class UrlBasedCorsConfigurationSource của MVC/Servlet khi cấu hình ServerHttpSecurity. Record WebProtectionProperties cần được bind/enable ở context Reactive, không chỉ ở Servlet example.

### 7.2. Reactive SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.reactive.CorsConfigurationSource;

@Bean
SecurityWebFilterChain browserReactiveChain(
        ServerHttpSecurity http,
        WebProtectionProperties policy,
        CorsConfigurationSource reactiveCorsSource) {

    return http
        .cors(cors -> cors.configurationSource(reactiveCorsSource))
        .csrf(Customizer.withDefaults())
        .headers(headers -> headers
            .contentSecurityPolicy(csp -> csp
                .policyDirectives(policy.cspPolicy()))
        )
        .authorizeExchange(auth -> auth
            .pathMatchers("/login", "/assets/**").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/csrf").permitAll()
            .pathMatchers("/api/**").authenticated()
            .anyExchange().denyAll())
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

Tương tự Servlet, ví dụ này minh họa application có WebSession/form login. WebFlux dùng header API riêng để cấu hình HSTS, và cookie của WebSession phải được kiểm tra theo session manager/container tương ứng.

**CSP vẫn cần đặt ở origin phục vụ HTML thật**. Nếu frontend được deploy trên CDN domain riêng, bảo vệ của JSON API không tự áp lên document frontend.

### 7.3. Reactive CSRF bootstrap

~~~java
import java.util.Map;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
class ReactiveCsrfBootstrapController {

    @GetMapping("/api/csrf")
    Mono<ResponseEntity<Map<String, String>>> csrf(
            ServerWebExchange exchange) {

        Mono<CsrfToken> tokenMono =
            exchange.getAttribute(CsrfToken.class.getName());

        if (tokenMono == null) {
            return Mono.error(new IllegalStateException(
                "CSRF WebFilter not configured"));
        }

        return tokenMono.map(token -> ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", token.getHeaderName(),
                "token", token.getToken())));
    }
}
~~~

**Không block() trong Reactive controller** để tạo token; Mono được subscribe trong response pipeline. Token JSON có thể masked tùy ServerCsrfTokenRequestHandler đang hoạt động. GET và POST phải giữ WebSession/cookie phù hợp.

### 7.4. So sánh runtime và giám sát

| Đặc điểm | Servlet | WebFlux |
| --- | --- | --- |
| HTTP security chain | SecurityFilterChain | SecurityWebFilterChain |
| CSRF | CsrfFilter | CsrfWebFilter |
| CORS | Servlet CorsConfigurationSource | Reactive CorsConfigurationSource |
| Request context | HttpServletRequest | ServerWebExchange |
| Session | HttpSession | WebSession |
| CSRF deferred representation | DeferredCsrfToken/Supplier | Mono<CsrfToken> |
| Firewall | StrictHttpFirewall của Servlet | Parser/matcher/gateway Reactive |
| HTTP testing | MockMvc | WebTestClient |

Dù policy baseline giống nhau, phải **test từng stack** trên môi trường chạy thật. Một WebFlux gateway và một Servlet service có thể có hai security boundaries khác nhau; phân định lớp **browser-facing** để không đặt CSRF sai vị trí.

## 8. Quản lý phiên bản Spring Boot, Security, Framework và Java

Một lần nâng cấp dependency có thể thay **hành vi bảo vệ** ngay cả khi mã SecurityFilterChain không đổi. Vì vậy version là một thành phần của policy vận hành.

### 8.1. Ma trận dependency cần được phê duyệt

| Thành phần | Kiểm tra khi cập nhật |
| --- | --- |
| **Spring Boot** | BOM, starters, auto-configuration, Actuator và default properties |
| **Spring Security** | CsrfFilter/CsrfWebFilter, token handler, SecurityFilterChain, headers và matchers |
| **Spring Framework** | MVC/WebFlux route matching, CORS, proxy/forwarded headers |
| **JDK** | Toolchain, runtime baseline, TLS ciphers, certificate handling |
| **spring-security-test** | Phiên bản phù hợp với runtime và các helper MockMvc/WebTestClient |
| **Servlet container / Reactor Netty** | HTTP parser, TLS, cookies, redirect và URL normalization |
| **Ingress/Gateway/CDN** | TLS termination, OPTIONS, header rewrite, caching |
| **Browser/frontend** | SameSite, credentials mode, CSP, HSTS và SPA token bootstrap |
| **Security advisories** | CVE, supported versions và hướng dẫn nâng cấp chính thức |

Các mốc thay đổi quan trọng:

- **Spring Security 5.x → 6.x trên Servlet**: ứng dụng Spring Boot 3 chuyển từ **javax.servlet** sang **jakarta.servlet**; CSRF deferred token và XOR masking mặc định trong 6.x có thể ảnh hưởng SPA đọc raw cookie XSRF.
- **Spring Security 6.x → 7.x**: một số tiện ích/DSL mới như **CsrfConfigurer.spa() trên Servlet từ 7.0**; code gọi tiện ích này không biên dịch được trên 6.x. Reactive có API riêng, không copy DSL Servlet.
- **Những thay đổi giữa các minor releases**: method, deprecated APIs, request matcher và default behaviors cần được xác minh bằng JavaDoc/upgrade notes của phiên bản thực tế.
- **Hạ tầng TLS/cookie**: không nhất thiết phụ thuộc trực tiếp phiên bản Spring Security; một thay đổi container, proxy hay CDN cũng có thể làm mất Secure/HttpOnly/SameSite hoặc HSTS.

**Đừng gán cặp Spring Boot/Spring Security chỉ từ trí nhớ.** Hãy lấy compatibility matrix của BOM và upgrade guide tương ứng version đã chọn, kiểm tra dependency tree rồi chạy regression trên artifact cuối.

### 8.2. Ưu tiên BOM, không pin rời từng Spring Security jar

Ví dụ Maven dùng Spring Boot parent:

~~~xml
<!-- Phiên bản 3.x.y chỉ là placeholder: thay bằng release cụ thể đã duyệt. -->
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Ở đây **3.x.y không phải một phiên bản Maven có thể resolve**; nó nhắc người học phải chốt **version cụ thể** qua quy trình quản trị dependency. Gradle có thể dùng Spring Boot plugin/BOM và dependency locking theo quy ước dự án.

Ví dụ lệnh kiểm tra dependency trong dự án thực:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.security

./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
~~~

Phải xem **runtimeClasspath**, không chỉ source dependencies. Một module transitively kéo Spring Security version cũ vào runtime có thể gây **NoSuchMethodError**, **ClassNotFoundException** hoặc override ngầm một default protection.

### 8.3. Regression test phải quan sát hành vi, không chỉ compile

Một upgrade vẫn có thể compile nhưng làm sai:

- CORS source nào được dùng khi có nhiều beans hoặc filter chains.
- Token CSRF raw/XOR và deferred loading sau GET bootstrap.
- Lựa chọn SecurityFilterChain khi path nằm sau gateway rewrite.
- Default security headers hoặc custom headers override.
- HSTS khi TLS terminate tại ingress.
- Cookie session khi container hoặc framework thay version.
- HTTP firewall với path encoding; proxy và Spring matchers không còn thống nhất.
- Audit event name/metric label thay đổi làm dashboard mất tín hiệu mà không báo lỗi.

Do đó release gate phải gồm **unit + integration + browser/edge behavior**, không chỉ compilation.

### 8.4. Quản lý thông tin phiên bản vận hành

Mỗi release nên có **manifest không chứa bí mật**:

~~~yaml
release:
  application: protection-service
  artifact-digest: "sha256:<artifact-hash>"
  config-revision: "git:<reviewed-commit>"
  dependency-sbom-revision: "sbom:<artifact-id>"
  security-policy-revision: "policy:<approved-version>"
  gateway-policy-revision: "infra:<approved-commit>"
~~~

Các placeholder trên không phải giá trị runtime thực. Khi có incident, SRE cần biết pod A và B đang chạy **artifact + config + gateway policy** nào để phân biệt bug chức năng và drift.

## 9. TLS termination, forwarded headers và cookie ở edge

Khi TLS kết thúc tại reverse proxy, browser đi bằng HTTPS nhưng request backend có thể là HTTP nội bộ. Điều này ảnh hưởng URL redirect, Secure cookie, HSTS và scheme mà app nhìn thấy.

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant EDGE as HTTPS gateway/ingress
    participant APP as Spring Security
    B->>EDGE: HTTPS request với cookie
    EDGE->>APP: HTTP nội bộ + forwarded metadata tin cậy
    APP-->>EDGE: Response và security headers
    EDGE-->>B: HTTPS response sau header normalization
    Note over B,EDGE: Kiểm tra cookie + HSTS + CSP + CORS tại public edge
~~~

### 9.1. Trust boundary với X-Forwarded-*

Một cấu hình Spring Boot Servlet có thể dùng:

~~~properties
# Chỉ khi ứng dụng nằm sau reverse proxy được kiểm soát.
server.forward-headers-strategy=framework
~~~

Giá trị cụ thể phụ thuộc proxy/container và phiên bản Boot. **Không tin X-Forwarded-Host/Proto từ client internet không được lọc**: kẻ tấn công có thể gây host/scheme spoofing nếu gateway không xóa/ghi đè headers đầu vào.

Các bước xác minh:

1. Gateway phải xác định trusted proxies và **sanitize forwarded headers**.
2. Spring Boot chỉ sử dụng chiến lược phù hợp với đường triển khai thực.
3. Redirect Location dùng HTTPS host chính xác, không sinh HTTP URL khi người dùng truy cập HTTPS.
4. Cookie session có **Secure/HttpOnly/SameSite** đúng trên Set-Cookie ở edge.
5. HSTS xuất hiện trên **response HTTPS public**; không coi test HTTP nội bộ là bằng chứng đủ.
6. CSP xuất hiện trên **HTML document origin**, không chỉ API JSON.
7. OPTIONS preflight có header CORS đúng cả khi lỗi authentication hoặc qua gateway.

### 9.2. So sánh kiểm tra ở ba lớp

| Nơi kiểm tra | Mục đích |
| --- | --- |
| Trực tiếp Spring application | Xác minh filter chain, response headers do app ghi, endpoint CSRF no-store |
| Ingress/gateway nội bộ | Kiểm tra rewrite, forwarded headers, TLS semantics và CORS/cache overrides |
| Public HTTPS endpoint | Xem hành vi browser thực: cookie, CSP, HSTS, redirect, OPTIONS, cache |

Nếu kết quả khác nhau, đừng lập tức sửa code Spring. Đối chiếu **header do ứng dụng phát** và **header mà edge trả cho client** trước khi xác định chủ sở hữu vấn đề.

### 9.3. HSTS và CSP cần rollout thận trọng

HSTS với max-age dài **có thể tồn tại trong cache trình duyệt sau khi server rollback**. includeSubDomains áp cho mọi subdomain nằm trong phạm vi, vì vậy phải kiểm kê các ứng dụng legacy chưa HTTPS trước khi bật.

CSP Enforce có thể chặn scripts/styles, iframe, connect-src và làm UI không hoạt động. Dùng **Content-Security-Policy-Report-Only** để quan sát nguồn thực trước rollout, rồi mở rộng theo canary. **CSP report endpoint cần scrub dữ liệu nhạy cảm** trong URI và payload, không gửi cookies/tokens ra telemetry.

Không bật một CSP chỉ để “có header”: policy phải dựa trên nguồn tài nguyên thực và mục tiêu giảm XSS/clickjacking.

## 10. Xem thay đổi policy như migration giao thức

Thay allowed-origin, cookie SameSite, CSRF handler hoặc CSP có thể làm frontend/mobile/client cũ ngừng hoạt động, ngay cả khi response JSON API chưa thay.

### 10.1. Phân loại thay đổi theo blast radius

| Thay đổi | Nguy cơ | Rollout phù hợp |
| --- | --- | --- |
| Thêm origin trong CORS | Cho một origin mới đọc credentialed response | Verify ownership, negative-origin tests và approval |
| Bỏ origin cũ | Frontend cũ báo CORS error | Đo traffic, canary và kế hoạch loại bỏ |
| CSP Report-Only → Enforce | Chặn script/style/frames hoặc API calls của SPA | Quan sát reports, test trình duyệt, canary |
| HSTS max-age/includeSubDomains | Ảnh hưởng subdomain chưa HTTPS, khó rollback ngay | Kiểm kê domain, tăng dần theo policy |
| Cookie SameSite/Domain/Path | Ảnh hưởng SSO, session, iframe, multi-tab | Browser matrix, login/logout, phased rollout |
| CSRF repository/handler | Raw-XOR mismatch, stale token và 403 sau login | Test GET token + POST, kế hoạch tương thích |
| Thay HTTP firewall | Có thể mở bypass hoặc chặn URL hợp lệ | Security review, path-encoding tests |
| Nâng Spring Security major | API/default changes, Java/Boot compatibility | BOM + version matrix + regression |
| Bật security TRACE | Rủi ro log secret và hiệu năng | Scope/TTL hạn chế, redaction trước capture |

### 10.2. Quy trình triển khai có gates

~~~mermaid
flowchart LR
    A["Đề xuất policy change"] --> B["Review, threat model và owner"]
    B --> C["Build với BOM/version pin"]
    C --> D["Security tests CI"]
    D --> E["Staging qua TLS/gateway thật"]
    E --> F["Canary subset"]
    F --> G{"SLO và security gates PASS?"}
    G -->|Có| H["Rollout rộng"]
    G -->|Không| I["Rollback artifact + config"]
    H --> J["Giám sát drift/incident"]
    I --> B
~~~

Trước canary phải quyết định **rollback trigger**, ví dụ: POST đúng token tăng 403 bất thường; CSP violations chặn UI chính; login/logout error tăng; hoặc CORS preflight thất bại tại một origin được phép.

**Không dùng toàn bộ số 403 tăng làm trigger đơn giản**: tấn công bị chặn có thể khiến 403 tăng, trong khi hệ thống vẫn đang bảo vệ đúng. Phải kết hợp **route, exception class, release correlation và thành công của luồng người dùng hợp lệ**.

### 10.3. Rollback không phải nút khôi phục tuyệt đối

Một rollback nên xem xét đồng thời:

- **Artifact digest** và code migration.
- **Config revision** của profiles/properties/secret references.
- **Ingress/CDN/CSP/CORS policy revision**.
- **Session store**, token encoding, cookie domain và CSRF token lifecycle.
- **HSTS browser cache** và CORS preflight cache còn lưu policy cũ trong một thời gian.
- **Data/schema migrations** và hoạt động nghiệp vụ không tự bị đảo ngược.
- **Mobile/browser client versions** ngoài quyền cập nhật đồng thời của backend.

Để vận hành ổn định, một release record cần có **artifact + config + gateway policy** đã được kiểm chứng cùng nhau. Nếu phải rollback, theo dõi việc user cần đăng nhập lại hoặc bootstrap token mới, đừng giả định mọi session còn hiệu lực.

## 11. Regression tests bắt buộc trên Servlet bằng MockMvc

Không nên chỉ test endpoint trả 200. Một bộ test bảo mật phải chứng minh **request bị từ chối khi thiếu điều kiện**, đồng thời vẫn cho request hợp lệ đi qua. Ví dụ dưới đây giả định **Spring Boot 3.x**, test context đã có SecurityFilterChain ở phần 6, và endpoint **POST /api/orders** trả 2xx cho user có quyền với dữ liệu hợp lệ.

### 11.1. CSRF trên browser cookie route phải còn hiệu lực

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ServletBrowserSecurityRegressionTests {

    @Autowired MockMvc mvc;

    @Test
    void unsafeRequestWithoutCsrfIsRejected() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfStillRequiresBusinessAuthorization() throws Exception {
        mvc.perform(post("/api/orders")
                .with(user("alice"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"P100\",\"quantity\":1}"))
            .andExpect(status().is2xxSuccessful());
    }
}
~~~

**Không hiểu nhầm tên test thứ hai**: helper csrf() chỉ cho request qua CSRF filter. Test chỉ nhận 2xx khi **controller và business authorization thật** cho phép. Bổ sung test user có quyền thấp thiếu scope và test object ownership để chứng minh CSRF token **không cấp quyền**.

Quan trọng nhất: test request 403 cần assert **đơn hàng không được tạo**. Status đơn lẻ không đủ để bảo đảm dữ liệu không bị thay đổi trước khi request bị từ chối.

### 11.2. Preflight OPTIONS không được bắt login cookie

~~~java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;

@Test
void allowedCorsPreflightNeedsNoSessionCookie() throws Exception {
    mvc.perform(options("/api/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers",
                "content-type,x-csrf-token"))
        .andExpect(status().isOk())
        .andExpect(header().string(
            "Access-Control-Allow-Origin",
            "https://app.example.com"))
        .andExpect(header().string(
            "Access-Control-Allow-Credentials",
            "true"));
}
~~~

Đoạn này là **thân test** thuộc một class có field MockMvc. Request preflight không gửi session cookie là cố ý. Test khác phải thử **Origin ngoài allowlist** và bảo đảm backend không cho JS của origin đó nhận credentialed response. Nếu proxy/gateway xử lý OPTIONS trước app, kiểm thử thêm qua **public edge**, không chỉ MockMvc.

### 11.3. Test security headers và token no-store

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;

@Test
void csrfEndpointHasNoStoreAndCsp() throws Exception {
    mvc.perform(get("/api/csrf").secure(true))
        .andExpect(status().isOk())
        .andExpect(header().string(
            HttpHeaders.CACHE_CONTROL, containsString("no-store")))
        .andExpect(header().string(
            "Content-Security-Policy",
            containsString("object-src 'none'")))
        .andExpect(header().string(
            "Strict-Transport-Security",
            containsString("max-age=31536000")));
}
~~~

**Test trên GET JSON chứng minh header được ghi, không chứng minh CSP bảo vệ trang SPA HTML khác origin**. HSTS test secure(true) mô phỏng request HTTPS tại Servlet layer; test public edge phải xác minh header cuối được trả sau TLS termination.

### 11.4. Test fail-fast của typed config

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import java.util.List;
import org.junit.jupiter.api.Test;

@Test
void wildcardOriginCannotBeLoaded() {
    assertThrows(IllegalArgumentException.class, () ->
        new WebProtectionProperties(
            List.of("*"),
            "default-src 'self'; object-src 'none'"));
}
~~~

Đây là regression test cho **policy validation**, không thay test browser thực. Trên production nên có test config resolved, xác minh **không** chấp nhận http://evil.example.test hoặc một origin chưa được phê duyệt, chứ không chỉ từ chối "*".

### 11.5. Những giới hạn của MockMvc

MockMvc không mô phỏng hoàn toàn:

- SameSite, third-party cookie policy và DevTools browser.
- Actual TLS/ingress forwarding, CDN header overrides và cache.
- Cookie migration giữa phiên đăng nhập thật khi chỉ dùng helper user().
- Một phiên bản frontend cũ đang gửi raw/XOR CSRF token khác.
- Gateway URL normalization, WAF, CSP enforcement ở browser.
- Session store phân tán trên nhiều instances.

**Unit/integration ở app phải đi cùng browser/edge tests**. Đừng dùng kết quả MockMvc xanh để kết luận mọi môi trường an toàn.

## 12. Regression tests WebFlux bằng WebTestClient

### 12.1. CSRF còn bật cho unsafe methods

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

// Đoạn thân test: webTestClient được gắn SecurityWebFilterChain.
// java.util.Map và endpoint POST /api/orders phải có thật.
webTestClient.mutateWith(mockUser("alice"))
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().isForbidden();

webTestClient.mutateWith(mockUser("alice")).mutateWith(csrf())
    .post().uri("/api/orders")
    .bodyValue(Map.of("sku", "P100", "quantity", 1))
    .exchange()
    .expectStatus().is2xxSuccessful();
~~~

**mockUser()/csrf() là helpers**, không kiểm chứng cookie/WebSession hoặc token JSON thật. Bổ sung integration test **GET /api/csrf → giữ cookie WebSession → POST thiếu/sai/đúng token → login/logout** và kiểm tra dữ liệu không đổi ở request bị chặn.

### 12.2. Reactive preflight và no-store

~~~java
import org.springframework.http.HttpHeaders;

// Đoạn thân test, với WebTestClient đã bind vào app có CORS source.
webTestClient.options().uri("/api/orders")
    .header(HttpHeaders.ORIGIN, "https://app.example.com")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
    .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
        "content-type,x-csrf-token")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueEquals(
        HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
        "https://app.example.com");

webTestClient.get().uri("/api/csrf")
    .exchange()
    .expectStatus().isOk()
    .expectHeader().valueMatches(
        HttpHeaders.CACHE_CONTROL, ".*no-store.*");
~~~

Test này kiểm tra CorsWebFilter/Spring Security integration và endpoint bootstrap. Với user không tin cậy, thêm test origin outside allowlist phải không được browser đọc credentialed response.

**Không copy tests Servlet nguyên xi sang Reactive**. Filter chain, session repository, attribute Mono và cookie behaviors khác nhau; cần regression của đúng stack đang triển khai.

## 13. Kiểm thử browser, gateway và các phiên bản client thực

Các test sau cần chạy trong môi trường staging có **hostname, certificate, gateway/CDN và cookie policy** gần production:

| Kịch bản | Dấu hiệu cần quan sát | Kết quả mong muốn |
| --- | --- | --- |
| GET HTML SPA trên frontend origin | CSP, content type, static assets | CSP có hiệu lực và tài nguyên tin cậy hoạt động |
| GET /api/csrf | Cache-Control, session cookie | no-store, token hợp lệ cho phiên |
| POST browser không CSRF header | Status và database | Bị từ chối, không side effect |
| POST browser token sai | Exception class | Invalid token bị chặn |
| POST browser token đúng, đủ quyền | Kết quả nghiệp vụ | Thành công |
| POST token đúng, thiếu quyền | Authorization | Bị từ chối |
| CORS preflight không cookie | OPTIONS + allow headers | Được phép trước authentication |
| CORS origin không tin cậy | Browser console/Network | Không được đọc credentialed response |
| Cookie Secure/HttpOnly/SameSite | Set-Cookie ở HTTPS edge | Đúng policy |
| URL HTTPS bị redirect | Location/scheme | Không redirect nhầm sang HTTP |
| HSTS public HTTPS | Response header | max-age và scope đúng policy |
| CSP Report-Only/Enforce | Violations và UI flows | Không chặn chức năng hợp lệ, hạn chế nguồn ngoài |
| Path encoding bất thường | Gateway + Spring matcher | Không có bypass role/security matcher |
| Session timeout/login/logout | Cookie/token lifecycle | Token mới sau auth transition |
| Nhiều instance/pod | Cookie và CSRF qua các pod | Không mất state ngoài thiết kế |
| CDN cache token HTML/JSON | Age/X-Cache và body per session | Không shared-cache token |
| Old SPA vs new API | Header/cookie/raw-XOR contract | Không phá client cần hỗ trợ |
| Blue/green phiên bản framework | Test hai release paths | Không khác bảo vệ một cách không chủ đích |

### 13.1. Không lấy curl thành công làm bằng chứng browser đúng

Curl và Postman thường không thực thi **CORS, SameSite, CSP, HSTS** theo cách browser. Một HTTP response 200 từ curl không chứng minh SPA JavaScript được quyền đọc body, browser lưu cookie hay CSP chặn script không tin cậy.

Khi browser báo CORS error, request **đơn giản** vẫn có thể được server xử lý trước khi response bị chặn. Vì thế, với request tấn công/negative test, phải kiểm tra **database state** hoặc audit event để chứng minh không có side effect.

### 13.2. Kiểm tra trên mọi security chain

Nếu cùng backend có hai route:

~~~text
/api/mobile/**  -> OAuth2 Resource Server Bearer-only (stateless)
/api/web/**     -> Cookie session + CSRF + CORS
~~~

đừng kiểm thử duy nhất một chain. Phải chứng minh:

- Mobile chỉ nhận Bearer token hợp lệ, không được xác thực chỉ bằng JSESSIONID của browser.
- Browser cookie route không bypass CSRF nhờ lỡ match mobile chain.
- CORS credentialed policy không mở wildcard cho origin không tin.
- Authentication/authorization và business validation độc lập với CSRF.
- Gateway không rewrite path khiến route rơi nhầm chain.

Một thiết kế nhiều chain phải có **test matrix theo từng matcher**, nhất là khi nâng Spring Security hoặc đổi path parser.

## 14. Phát hiện configuration drift giữa Git, pod và edge

**Configuration drift** là khi những gì runtime thực sự phục vụ khác với policy revision đã phê duyệt. Nó có thể xuất hiện vì manual hotfix, environment override, secret reload, service rollout dở dang, CDN rules khác cluster hoặc một pod không được restart.

### 14.1. Ba tầng so sánh

| Tầng | Ví dụ bằng chứng | Cách kiểm tra |
| --- | --- | --- |
| **Desired** | Git commit policy, Helm/Kustomize revision, signed release manifest | Review và CI |
| **Resolved runtime** | Active profiles, sanitized configuration fingerprint, artifact digest, Spring module versions | Kiểm tra nội bộ không lộ secrets |
| **Observed behavior** | CORS/HSTS/CSP/cookie headers, blocked requests, security metrics | Synthetic probes, browser/edge tests |

**Không phát tán nguyên Environment/Actuator config ra public endpoint** để so sánh. Nếu cần fingerprint, chỉ tính từ **non-secret policy fields đã chuẩn hóa**, đặt nó trong internal deployment metadata và bảo vệ quyền truy cập. Không hash bí mật rồi publish, vì một số giá trị có entropy thấp vẫn có thể bị suy đoán.

### 14.2. Ví dụ drift thực tế

~~~text
Git approved:
    prod allowed origins = https://app.example.com
    CSRF enabled for /api/web/**
    CSP enforce = object-src 'none'

Pod A:
    app origin đúng; CSP đúng

Pod B:
    env override thêm https://debug.example.com
    CSP config rỗng, startup không fail

Gateway:
    response Access-Control-Allow-Origin phản chiếu Origin bất kỳ
~~~

Nếu chỉ đọc Git, hệ thống trông an toàn. Nếu chỉ gọi Pod A, drift không được phát hiện. Cần kiểm tra **từng instance/canary và public edge**, nhất là trong rollout.

### 14.3. Cách triển khai drift detection

1. Lưu release manifest được phê duyệt với **artifact digest, config revision và policy revision**.
2. Khi startup, validate properties bắt buộc; fail startup nếu CSP rỗng/origins sai hoặc có wildcard credentials.
3. Trong deployment, dùng immutable image và GitOps/Infrastructure as Code; hạn chế thay trực tiếp môi trường production.
4. Probe **browser-facing routes** qua public edge và **sample từng pod** bằng synthetic requests không tiết lộ secrets.
5. So sánh runtime version và config fingerprint với manifest; đánh dấu instance mismatch.
6. Khi phát hiện drift, điều tra owner, thay đổi thủ công, precedence và thời điểm rollout.
7. Đồng bộ lại cấu hình qua pipeline có review; không dùng một shell hotfix không được ghi lại để “đồng bộ” tạm.
8. Sau remediation, test lại CORS/CSRF/headers/cookie và quan sát metrics.

### 14.4. Cấu hình động và feature flags

Nếu dùng central config server hoặc dynamic flags, cần có cơ chế:

- **Versioned, atomic update** khi có thể: tránh một nửa cấu hình mới, một nửa cũ trong cùng pod.
- **Schema validation** và fail-closed với giá trị bảo mật không hợp lệ.
- **Rollout/rollback và audit owner** cho từng thay đổi.
- **TTL/expiry** cho ngoại lệ tạm thời như CSP Report-Only hoặc tăng log verbosity.
- **Race conditions giữa instances**: không để pod A nhận origin/token mode mới còn pod B vẫn dùng mode cũ ngoài thời gian chuyển tiếp có kế hoạch.

Không coi một config flag từ xa là miễn trừ code review. Các thay đổi CSP/CORS/CSRF có thể thay đổi security posture tức thời.

## 15. Giám sát security posture và thiết kế cảnh báo có ý nghĩa

Vận hành bảo mật không chỉ là “có 403 hay không”. Cần phân biệt **request tấn công bị chặn** với **request hợp lệ gặp lỗi sau rollout**.

### 15.1. Tín hiệu nên thu thập

| Nhóm | Ví dụ tín hiệu | Cách diễn giải |
| --- | --- | --- |
| **CSRF** | Số request unsafe bị chặn do missing/invalid token theo route | Có thể là bug frontend, session mismatch hoặc một đợt tấn công |
| **CORS** | Tỷ lệ preflight thất bại với origin đã phê duyệt | Có thể lỗi rollout/gateway; origin lạ bị chặn là hành vi đúng |
| **Authentication** | 401, login failures, token expired | Có thể login loop, TTL cookie hoặc attack |
| **Authorization** | 403 do role/scope/ownership | Không đồng nhất với CSRF 403 |
| **Security headers** | Synthetic check CSP/HSTS/X-Content-Type-Options | Phát hiện mất header tại public edge |
| **Session** | Session creation/expiry, login/logout success, invalid session cookies | Phát hiện lỗi cookie/cluster/session store |
| **CSP** | Violation reports theo directive/route | Phát hiện script nguồn mới, XSS indicator hoặc false positive |
| **HTTP firewall** | RequestRejectedException hoặc request abnormal bị chặn | Cần phân biệt traffic scan với URL hợp lệ bị reject |
| **Config drift** | Pod/release revision khác expected, startup validation failures | Gần trực tiếp với thay đổi policy |
| **Client UX** | Tỷ lệ login thành công, form submit/checkout thành công | Tín hiệu kiểm chứng bảo mật không làm vỡ luồng hợp lệ |
| **Secrets hygiene** | Synthetic canary có xuất hiện trong log/APM không | Thất bại nếu canary bí mật bị thu ngoài nơi cho phép |

**Không có một metric name tự động áp dụng cho mọi phiên bản Spring Security.** Các metrics sau đây là **đề xuất semantic** để nhóm vận hành tự instrument hoặc ánh xạ từ Micrometer/Actuator/observations mà stack thực hỗ trợ.

### 15.2. Counter và labels an toàn

~~~text
security_csrf_denied_total{
  environment="prod",
  route="/api/orders",
  reason="invalid",
  release="r42"
}

security_cors_preflight_total{
  environment="prod",
  route="/api/orders",
  decision="denied",
  origin_class="untrusted"
}

security_header_probe_success{
  environment="prod",
  host_group="public-web",
  policy="csp",
  release="r42"
}

security_config_revision_match{
  environment="prod",
  workload="protection-service",
  expected_revision="policy-r42"
}
~~~

Đây là **ví dụ nhãn/metric do ứng dụng tự định nghĩa**, không phải tên metrics mặc định của Spring Security.

Nên ưu tiên **low-cardinality labels**:

- Route **template**, không raw URL chứa orderId/session token.
- HTTP method, error class/category, filter chain label ổn định.
- Environment, release revision và workload name có số lượng hữu hạn.
- Origin **được phân nhóm** trusted/untrusted thay vì ghi mọi Origin bất kỳ của internet vào label.

**Không dùng CSRF token, JWT, JSESSIONID, userId tùy ý, IP thô, full Origin không giới hạn, request body hoặc query làm metric labels**. Điều đó làm lộ bí mật và tạo cardinality bùng nổ.

### 15.3. Mẫu dashboard hữu ích

Một dashboard vận hành HTTP protection nên trả lời được:

1. **Release nào đang chạy?** Artifact digest, config revision, gateway revision theo workload.
2. **CSRF bị từ chối ở đâu?** Route và lý do missing/invalid, không hiển thị giá trị token.
3. **Người dùng hợp lệ có bị ảnh hưởng không?** Tỷ lệ hoàn thành login, refresh, checkout hoặc form submit.
4. **CORS đang chặn origin đã duyệt không?** Synthetic preflight từ origins hợp lệ sau mỗi rollout.
5. **CSP có cản chức năng không?** Violation reports và browser error rate cùng release.
6. **HSTS/CSP/cookie đã ra đến edge chưa?** Kết quả probes từ HTTPS public endpoint.
7. **Các pod có cùng policy không?** Config revision match, failed-startup validation, version mismatch.
8. **Có dấu hiệu lộ dữ liệu không?** Redaction tests staging và kết quả canary, không lưu raw canary production.

### 15.4. Alert theo baseline và hành vi, không theo một ngưỡng tuyệt đối duy nhất

Một số gợi ý:

- **Critical:** Synthetic test xác minh browser route không cần CSRF mà vẫn tạo được dữ liệu; cần chặn rollout/ứng phó ngay.
- **Critical:** Public HTTPS endpoint mất HSTS sau một release đã đặt yêu cầu HSTS, hoặc cookie session mất Secure/HttpOnly.
- **High:** Credentialed CORS trả wildcard hoặc Origin lạ được cho đọc response session.
- **High:** Một pod có config revision không khớp manifest production.
- **High:** Tỷ lệ POST hợp lệ bị CSRF invalid tăng đột ngột ngay sau upgrade Spring Security.
- **Medium:** Preflight của một trusted origin thất bại; CSP report-only cho thấy script nguồn mới chưa được review.
- **Investigate:** RequestRejectedException tăng nhưng chỉ từ scanners, trong khi legitimate flows không đổi.

**Ngưỡng cụ thể** phải dựa trên baseline, traffic seasonality và SLO của hệ thống. Một loạt 403 vì tấn công bị chặn có thể cho thấy cơ chế đang hoạt động; không tự động nới CSRF/CORS vì tỷ lệ 403 tăng.

## 16. Logging và incident runbooks

### 16.1. Metadata đủ chẩn đoán nhưng không lộ bí mật

Một audit record an toàn:

~~~text
timestamp=... environment=prod release=r42
correlationId=req-5bd2 method=POST route=/api/orders
status=403 errorCategory=CSRF_INVALID chain=browser
~~~

Không ghi:

~~~text
Cookie: JSESSIONID=...
Authorization: Bearer eyJ...
X-XSRF-TOKEN: ...
csrfExpected=...
csrfProvided=...
requestBody={"_csrf":"..."}
~~~

Đặc biệt khi bật DEBUG/TRACE cho org.springframework.security, phải biết logger hoặc HTTP middleware của phiên bản thực sự thu thập những gì. Ưu tiên **logging allowlist** cho route template, status, exception class và correlation ID; không dump toàn bộ request/response.

Giới hạn log retention, quyền truy cập, redaction trước APM upload và tắt sampling body ở các endpoint nhạy cảm. **Cache-Control: no-store không tự bảo vệ APM hoặc log**.

### 16.2. Runbook A — CSRF 403 tăng sau release

1. Xác định thời điểm và release/config revision bắt đầu tăng.
2. Chia theo route, method, **MissingCsrfTokenException/InvalidCsrfTokenException** hoặc authz 403 riêng.
3. Kiểm tra GET /api/csrf còn tạo token và no-store, cookie session có hợp lệ không.
4. Kiểm tra frontend gửi **headerName/raw/XOR format** đúng với CsrfTokenRequestHandler của version hiện hành.
5. Xác minh sau login/logout token cũ có được reset và SPA bootstrap token mới không.
6. Kiểm tra gateway đã thay cookies, CORS hay path matcher không.
7. Chạy negative test: POST thiếu token phải bị chặn. Không “fix” bằng csrf.disable().
8. Nếu canary không đạt, rollback code + config tương thích; theo dõi session user chịu ảnh hưởng.

### 16.3. Runbook B — Browser đột nhiên báo CORS error

1. Xem request thực có **OPTIONS preflight** không; OPTIONS thường không có session cookie.
2. Kiểm tra Access-Control-Allow-Origin, Allow-Methods, Allow-Headers và Allow-Credentials.
3. So sánh Origin của frontend với **allowlist đã duyệt**, không chấp nhận wildcard để chữa lỗi.
4. Kiểm tra security filter order và ingress có trả 401/redirect trước CORS không.
5. Kiểm tra proxy cache hoặc CDN có trộn CORS response giữa Origins không.
6. Đối chiếu deploy origin/frontend mới và policy revision của API.
7. Test response 401/403 cũng có CORS phù hợp để frontend hiểu lỗi mà không lộ dữ liệu.
8. Duy trì CSRF và authorization độc lập, vì CORS không thay bảo vệ server.

### 16.4. Runbook C — HSTS/CSP mất sau thay đổi proxy

1. Dùng public HTTPS endpoint kiểm tra headers ở **HTML origin**, không chỉ backend HTTP nội bộ.
2. Kiểm tra header được app phát và có bị ingress/CDN override không.
3. Kiểm tra forwarded proto/host có được sanitize và tin đúng từ proxy không.
4. Với HSTS, đánh giá includeSubDomains và max-age hiện hành trước khi rollback.
5. Với CSP, kiểm tra Report-Only/Enforce và script nguồn bị chặn; không tự mở script-src *.
6. Chạy browser smoke test và synthetic probes; so sánh canary với release cũ.
7. Bổ sung regression cho header loss ở edge và ghi nhận root cause.

### 16.5. Runbook D — Configuration drift giữa các pod

1. Xác minh drift thực sự: artifact digest, active profile, config revision, runtime dependency.
2. Kiểm tra có env/CLI override hoặc manual change không.
3. Nếu drift gây mở quyền, cô lập instance/rollback theo runbook và giảm lưu lượng vào instance đó.
4. Triển khai lại immutable artifact/config đã được duyệt qua pipeline.
5. Chạy lại tests CORS, CSRF, cookie, headers và negative paths.
6. Điều tra vì sao CI/GitOps/synthetic probe không phát hiện sớm; thêm guardrails.

### 16.6. Runbook E — Token hoặc session ID xuất hiện trong log

1. Xác định loại bí mật và những hệ thống nào đã nhận dữ liệu, **không sao chép nguyên giá trị vào ticket**.
2. Chặn nguồn ghi/thu thập, giới hạn quyền truy cập logs/APM.
3. Tùy trường hợp, rotate/invalidate token/session hoặc credential bị ảnh hưởng.
4. Nếu CDN đã cache body nhạy cảm, sửa bypass rule rồi purge/invalidate cache.
5. Phối hợp với đội an ninh và chủ hệ thống về retention, xóa dữ liệu và thông báo cần thiết.
6. Kiểm tra staging redaction với **synthetic canary**, bổ sung tests vào pipeline.
7. Không coi việc “token CSRF không phải mật khẩu” là lý do bỏ qua sự cố có thể kèm cookie/JWT leak.

## 17. Bài tập thực hành

**Bài A — Ma trận môi trường:** Viết policy baseline cho dev, CI, staging, production gồm CSRF, CORS, HSTS, CSP, firewall, session cookie, logging, version pin. Chỉ rõ bất biến không được tắt và ngoại lệ có expiry.

**Bài B — Properties fail-fast:** Dùng WebProtectionProperties từ phần 5, chạy với CORS wildcard hoặc CSP rỗng. Xác minh ứng dụng **fail startup** thay vì tự cho phép mọi origin.

**Bài C — Profiles và precedence:** Đặt allowed origin khác nhau trong application.yaml, một env var và command-line override ở môi trường test. Xác định giá trị hiệu lực theo Spring Boot, sau đó bổ sung gate production không chấp nhận debug origin.

**Bài D — Servlet HTTP headers:** Triển khai SecurityFilterChain, GET token no-store, CSP và HSTS. Dùng MockMvc và browser HTTPS để xác minh; chứng minh CSP trên API JSON không tự bảo vệ HTML frontend khác origin.

**Bài E — WebFlux parity:** Tạo SecurityWebFilterChain tương đương và WebTestClient tests cho CSRF, OPTIONS và no-store. So sánh WebSession với HttpSession và giải thích vì sao config Servlet không áp vào Reactive.

**Bài F — CORS hotfix review:** Một pull request đổi exact CORS allowlist sang wildcard vì frontend bị lỗi. Nêu security impact, sửa đúng origin, chạy negative-origin preflight và xác minh cookie/CSRF.

**Bài G — Upgrade 5.8/6.x/7.x:** Lập version matrix cho dự án đang dùng. Xác định Javax/Jakarta, raw/XOR/deferred token, convenience API spa() của Servlet và mức độ tương thích test dependency; viết regression không phụ thuộc vào default may change.

**Bài H — Firewall normalization:** Gửi test URLs có encoded slash, semicolon và path bất thường qua ingress rồi trực tiếp Servlet app trong môi trường kiểm thử. Xác minh không có bypass securityMatcher/role.

**Bài I — Canary rollout:** Thiết lập gates cho login, checkout, CSP violations, preflight thành công và CSRF negative tests. Chọn rollback trigger, theo dõi session/cookie migration và lưu manifest artifact+config.

**Bài J — Drift drill:** Cố ý làm staging pod có origin override khác baseline (trong phạm vi test). Dùng config revision và public edge probes để phát hiện; rollback bằng pipeline, không sửa tay vĩnh viễn.

**Bài K — Sensitive telemetry:** Bơm synthetic token trong staging, xác minh không có token/cookie trong APM, logs, session replay hoặc metrics labels. Giữ correlation ID và errorCategory đủ chẩn đoán.

**Bài L — Incident tabletop:** Giả lập một release làm mất HSTS trên public edge và đồng thời tăng lỗi CSRF do handler raw/XOR. Trình bày thứ tự triage, owner, canary stop, rollback và postmortem.

## 18. Checklist trước phát hành và nguyên tắc cốt lõi

### 18.1. Release readiness checklist

| Nhóm | Điều kiện PASS |
| --- | --- |
| **Source of truth** | Policy revision đã review; các ngoại lệ có owner, phạm vi và expiry |
| **Profiles** | Dev/staging/prod có resolved config được validate; không có wildcard credentialed CORS |
| **Secrets** | Keys/passwords/credentials ở secret manager, không trong Git/public Actuator |
| **CSRF** | Browser cookie-auth unsafe requests yêu cầu token; không lộ qua cache/log |
| **Authorization** | Request role/scope sai bị từ chối; mọi chain/matcher có negative tests |
| **CORS** | OPTIONS không cần session cookie; origin allowlist chính xác; error responses phù hợp |
| **CSP** | Được áp trên HTML origin; browser flows pass; Report-Only → Enforce có kế hoạch |
| **HSTS/TLS** | Public HTTPS edge trả HSTS đúng readiness; forwarded headers được sanitize |
| **Session** | Secure/HttpOnly/SameSite, rotation, timeout, multi-tab và cluster behavior đã test |
| **HTTP firewall** | Không relax parsing/URL normalization vô lý, không bypass matchers |
| **Dependencies** | BOM, Spring Security modules, Java và runtime versions nhất quán |
| **Tests** | MockMvc/WebTestClient, browser và edge regression pass |
| **Observability** | Low-cardinality metrics, audit không có tokens, dashboard phân biệt lỗi và attack |
| **Drift** | Artifact/config/gateway revisions đồng nhất, startup validation và probes đang hoạt động |
| **Rollout** | Canary gates, owner, escalation và rollback manifest đã được xác định |
| **Post-deploy** | Synthetic probes + user-flow smoke tests + security negative tests pass |

### 18.2. Mười hai nguyên tắc cần nhớ

1. **Quản lý cấu hình bảo vệ như code có version và owner**, không như một tập thủ thuật sửa lỗi runtime.
2. **Baseline của dev/staging/prod phải giữ các bất biến an toàn**; chỉ hostname/origin, certificate và giá trị được phê duyệt mới nên thay đổi tùy môi trường.
3. **Không dùng Boolean security.enabled=false** hoặc tắt CSRF toàn bộ để sửa nhanh một endpoint.
4. **Spring Boot profiles và precedence có thể override YAML**, vì vậy cần test resolved runtime config.
5. **CORS, CSP, HSTS và cookies phải được kiểm tra tại public edge**, không chỉ trong SecurityFilterChain code.
6. **Servlet và WebFlux có API/filter/session khác nhau**, cần test parity theo đúng stack.
7. **BOM/version pin và runtime dependency tree là một phần của security posture**; upgrade có thể thay default protection.
8. **CSRF token/raw-XOR, session rotation, CORS preflight và matcher semantics cần regression** khi nâng framework.
9. **CSP Report-Only và HSTS có đặc tính rollout/rollback riêng**, không thể coi chúng như một config flag tức thời.
10. **Metrics chỉ dùng low-cardinality labels không nhạy cảm**; không log CSRF token, JWT, session ID hoặc full request body.
11. **Drift detection phải so sánh desired, resolved và observed behavior** qua nhiều pod/gateway, không chỉ đọc Git.
12. **Rollback phải ghép artifact, config và gateway policy** đã biết tốt, kết hợp synthetic probes và user-flow metrics.

**Kết luận:** Cấu hình Spring Security tốt không kết thúc ở việc bật một vài filter. Nó phải tồn tại như một **policy có thể giải thích, version, kiểm thử, giám sát và khôi phục** trên mọi môi trường. Giữ CSRF/CORS/security headers/CSP/HSTS/firewall/session protection nhất quán, kiểm soát dependency và đối chiếu hành vi tại browser/edge sẽ giúp đội phát triển phát hành nhanh mà không vô tình mở lỗ hổng khi đổi profile hoặc nâng phiên bản.

## Tài liệu tham khảo chính thức và thực hành bổ trợ

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Security 6.5 — Servlet CSRF và SPA](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Servlet Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — Servlet CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/firewall.html)
- [Spring Security 6.5 — Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Reactive Security Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Security 6.5 — Reactive CORS](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 7.0 — CsrfConfigurer JavaDoc](https://docs.spring.io/spring-security/reference/7.0/api/java/org/springframework/security/config/annotation/web/configurers/CsrfConfigurer.html)
- [Spring — Security Advisories](https://spring.io/security)
- [OWASP — HTTP Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)





