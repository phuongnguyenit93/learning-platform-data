# Đối chiếu mặc định CSRF và header trên phiên bản đang dùng

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Phạm vi:** Xác minh chính sách CSRF và HTTP security response headers thực sự có hiệu lực trong Spring Security cho **Servlet (Spring MVC)** và **Reactive (WebFlux)**; kết hợp kiểm thử các kịch bản trình duyệt, phiên, proxy và các vấn đề HTTP firewall/CORS liên quan.  
> **Mốc tài liệu:** 26/11/2026. Các ví dụ sử dụng Lambda DSL phổ biến ở Spring Security 6.5/7.x; phải kiểm tra lại tài liệu **đúng dòng đã resolve** thay vì coi mọi mặc định ở mọi phiên bản là giống nhau.

## 1. Vấn đề: “Mặc định của Spring Security” là mặc định nào?

Một nhóm nâng cấp Spring Boot rồi chạy kiểm thử thấy:

- `POST /orders` trả **403** dù người dùng đã đăng nhập.
- Giao diện SPA không còn gửi được CSRF token sau login/logout.
- `GET /public/logo.svg` không có `X-Content-Type-Options`.
- Hệ thống HTTPS chạy sau reverse proxy không thấy `Strict-Transport-Security`.
- Bản scan báo thiếu `Content-Security-Policy`, nhưng nhóm cho rằng Spring Security sẽ tự phát sinh header này.

Những hiện tượng trên không thể giải thích chỉ bằng câu “Spring Security bật bảo vệ theo mặc định”. Kết quả cuối cùng phụ thuộc đồng thời vào:

1. **Phiên bản đã resolve:** Spring Security, Spring Framework, Spring Boot, các module Security và các bản vá đang chạy thực tế.
2. **Web stack:** Servlet dùng `HttpSecurity`/`SecurityFilterChain`; Reactive dùng `ServerHttpSecurity`/`SecurityWebFilterChain`.
3. **Cấu hình ứng dụng:** bao nhiêu filter chain, chain nào match URL, có `csrf.disable()`, `headers.disable()`, custom request matcher hoặc `web.ignoring()` không.
4. **Bản chất HTTP request:** method, origin, cookie/session, HTTPS, proxy, path, xác thực và quyền truy cập.
5. **Ai ghi header cuối cùng:** Spring Security, controller, Servlet container, reverse proxy, CDN hoặc nền tảng hosting.

Vì vậy, **mặc định tài liệu** là giả thuyết khởi đầu; **dependency graph + cấu hình chain + integration test + response public thực tế** mới chứng minh ứng dụng đang bảo vệ điều gì.

### Mục tiêu học tập

Sau bài này, người học có thể xác định phiên bản thực tế, liệt kê kỳ vọng CSRF và headers theo stack, chạy kiểm thử có/không có token trên các HTTP method, đo response headers dưới HTTP/HTTPS, so sánh trước/sau nâng cấp và chẩn đoán các trường hợp mặc định bị thay bởi cấu hình hoặc proxy.

## 2. Bước đầu tiên: xác định chính xác phiên bản và đường đi request

Nếu dùng **Spring Boot**, phiên bản Spring Security thường được quản lý bằng **BOM** tương ứng với dòng Boot. Tuy nhiên, một property override, dependency trực tiếp, Gradle resolution rule hoặc BOM khác có thể làm phiên bản chạy thực tế khác bản Boot dự kiến.

**Maven:**

```bash
# Chạy tại project có Maven Wrapper
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework
./mvnw help:effective-pom
```

**Gradle:**

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

Trên Windows dùng `mvnw.cmd`/`gradlew.bat`. Trong Maven, `-Dincludes` lọc groupId, nên có thể thu hẹp đến các artifact cụ thể khi output lớn. Trong WebFlux vẫn nên kiểm tra `spring-security-web`/`spring-security-config` và các module liên quan; nguồn gốc Reactor/WebFlux phải nằm cùng thế hệ Framework được Boot quản lý.

**Ghi vào phiếu đối chiếu trước khi thay bất cứ cấu hình nào:**

| Thông tin | Giá trị cần ghi |
| --- | --- |
| JDK, Spring Boot | Java runtime, phiên bản Boot/BOM, Spring Framework |
| Spring Security | `spring-security-core`, `-web`, `-config`, `-test` và module OAuth2 nếu dùng |
| Loại ứng dụng | Servlet / MVC / WAR hay Reactive / WebFlux |
| Chain | Danh sách `SecurityFilterChain` hoặc `SecurityWebFilterChain`, `@Order` và matcher |
| CSRF | Bật/tắt, repository, handler, matcher loại trừ, cách client nhận/gửi token |
| Headers | Các header Spring Security quản lý, custom writers, header từ proxy/CDN |
| Giao thức | Truy cập HTTP hay HTTPS; TLS terminate tại đâu; xử lý forwarded headers |
| Client | Browser form, SPA dùng cookie, bearer token API, mobile hoặc webhook |

Để tìm đúng tài liệu, dùng **URL có số phiên bản** trong [Spring Security Reference](https://docs.spring.io/spring-security/reference/index.html), ví dụ nhánh `6.5` hoặc `7.2`. Trang `/reference/` không khóa số phiên bản, vì vậy nội dung có thể thay đổi sau khi ứng dụng của bạn đã được phát hành.

### Cần xác minh filter chain nào đang chạy

```text
Browser / API client
       |
       v
Ingress, CDN, TLS proxy
       |
       v
Spring Security chọn chain đầu tiên match request
       |
       +---- Servlet: FilterChainProxy -> SecurityFilterChain
       |
       +---- Reactive: WebFilterChainProxy -> SecurityWebFilterChain
       |
       v
CSRF / authentication / authorization / headers / ...
       |
       v
Handler / controller
       |
       v
Response có thể tiếp tục được sửa bởi proxy/CDN
```

Một bean chain có `securityMatcher("/api/**")` không mặc nhiên bảo vệ `/admin/**`; `anyRequest()` chỉ áp dụng **bên trong chain đã match**. Nếu mọi chain đều không match một URL, bộ lọc bảo mật Spring Security không xử lý URL đó. Nếu Servlet dùng `web.ignoring()`, request cũng đi qua ngoài Spring Security filter chain; cách này khác `permitAll()` (request vẫn đi qua chain, được phép truy cập).

## 3. CSRF mặc định: Spring Security bảo vệ request nào?

**Cross-Site Request Forgery (CSRF)** là tình huống website ngoài ý muốn khiến trình duyệt gửi request thay đổi trạng thái tới hệ thống mà người dùng đang đăng nhập, tận dụng credential tự động đính kèm như cookie session. CSRF token là bằng chứng bổ sung để phân biệt request chủ động hợp lệ với request bị kích hoạt từ ngữ cảnh khác.

Trong cấu hình web thông thường, **CSRF được bật mặc định** ở cả Servlet và WebFlux. Mặc định Spring Security kiểm tra các HTTP method không được coi là an toàn.

| HTTP method | Đánh giá CSRF mặc định | Lý do |
| --- | --- | --- |
| `GET` | Thường không yêu cầu token | GET theo thiết kế phải chỉ đọc |
| `HEAD` | Thường không yêu cầu token | Tương tự GET nhưng không có body |
| `OPTIONS` | Thường không yêu cầu token | Dùng để truy vấn khả năng/preflight |
| `TRACE` | Thường không yêu cầu token | Nằm trong nhóm method an toàn của matcher CSRF mặc định; nên đánh giá chính sách cho TRACE riêng |
| `POST` | **Yêu cầu token** | Có thể làm thay đổi trạng thái |
| `PUT` | **Yêu cầu token** | Có thể sửa/thay tài nguyên |
| `PATCH` | **Yêu cầu token** | Có thể cập nhật một phần |
| `DELETE` | **Yêu cầu token** | Có thể xóa tài nguyên |

Các method khác cũng có thể bị kiểm tra vì không thuộc tập an toàn. Mặc định này giả định ứng dụng dùng **đúng ngữ nghĩa method**. Nếu `GET /transfer?amount=...` thay đổi dữ liệu, việc “GET không cần token” không làm endpoint an toàn: cần sửa endpoint để dùng method thay đổi trạng thái và thêm kiểm soát phù hợp.

### 3.1. Phân biệt CSRF với các cơ chế khác

- **Authentication** xác minh ai đang gửi request.
- **Authorization** xác minh user được phép làm gì.
- **CSRF** chống request do bên ngoài kích hoạt nhưng vẫn mang credential hợp lệ của user.
- **CORS** điều khiển browser cho phép origin khác đọc/gửi request theo quy tắc cross-origin; CORS không thay CSRF.
- **HTTP firewall** xử lý request có cấu trúc/path bất thường trước hoặc quanh quá trình so khớp request.
- **Security headers** hướng dẫn browser bảo vệ tài nguyên response; chúng không thay thế kiểm tra token CSRF.

Do đó, một request POST có user hợp lệ vẫn có thể nhận `403 Forbidden` nếu thiếu token. Một POST có CSRF token hợp lệ vẫn có thể nhận 403 vì user không đủ quyền. Đọc **nguyên nhân từ log/test** trước khi thay cấu hình.

### 3.2. Repository mặc định không đồng nghĩa cookie XSRF-TOKEN mặc định

| Thành phần | Servlet / Spring MVC | Reactive / WebFlux |
| --- | --- | --- |
| Bộ lọc xử lý | `CsrfFilter` | `CsrfWebFilter` |
| Repository mặc định | `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` |
| Nơi lưu kỳ vọng token | `HttpSession` | `WebSession` |
| Repository cookie tùy chọn | `CookieCsrfTokenRepository` | `CookieServerCsrfTokenRepository` |
| Header token điển hình | `X-CSRF-TOKEN`, hoặc `X-XSRF-TOKEN` khi dùng cookie repository | Tương tự, tùy repository/handler |
| Tham số form thường dùng | `_csrf` | `_csrf` |
| Filter chain | `SecurityFilterChain` | `SecurityWebFilterChain` |

**Điều dễ hiểu lầm:** Spring Security không tự trả `X-CSRF-TOKEN` trong **response header** trên mọi GET. Đó thường là **request header** client cần gửi khi dùng POST/PUT/PATCH/DELETE. Nếu cần JavaScript nhận token, ứng dụng phải tích hợp với form/template, cookie repository hay endpoint cung cấp token phù hợp.

Với repository mặc định dựa trên session, không thấy cookie `XSRF-TOKEN` là **bình thường**. Ngược lại, có cookie `XSRF-TOKEN` cũng không chứng minh endpoint đang kiểm tra token; cần thử request thiếu/sai token thật sự.

### 3.3. Điểm khác biệt quan trọng khi chuyển Security 5 → 6+

Theo tài liệu di chuyển Spring Security 6 cho **Servlet**:

1. **Deferred CSRF token:** token được tải khi thực sự cần, thay vì buộc đọc session cho mọi request.
2. **BREACH protection:** giá trị token được trình bày với yếu tố ngẫu nhiên theo request; mặc định `XorCsrfTokenRequestAttributeHandler` xử lý token.
3. **SPA cần chú ý:** JavaScript đọc token thô từ cookie nhưng handler mặc định có thể đợi dạng token đã mã hóa; cần cấu hình tích hợp SPA đúng phiên bản.
4. **Login/logout:** token cũ có thể bị làm mới/xóa; SPA phải lấy token mới trước request thay đổi trạng thái kế tiếp.

Trong **Reactive**, `XorServerCsrfTokenRequestAttributeHandler` là mặc định từ Security 6.0, thay cho `ServerCsrfTokenRequestAttributeHandler` của 5.8. WebFlux dùng `WebSession`, nên không bê nguyên repository/handler Servlet vào Reactive.

**Đừng so sánh trực tiếp chuỗi token lấy ở hai lần render** rồi kết luận session bị thay: token được che bằng ngẫu nhiên có thể khác nhau trên từng request dù underlying token vẫn tương ứng. Hãy kiểm thử token **được client gửi** có được server xác thực không.

### 3.4. Login/logout và session

CSRF cũng áp dụng cho **login** và **logout** ở các flow Spring Security thông thường. Với CSRF bật mặc định, logout qua POST là hướng an toàn: ép user logout bằng một GET từ website ngoài có thể trở thành logout CSRF. Hãy kiểm tra cả cookie session hết hạn, session fixation, token cũ và token mới sau login/logout.

Với ứng dụng dùng bearer token trong `Authorization` header do JavaScript/native client chủ động gắn, nhóm có thể quyết định điều chỉnh CSRF theo threat model. Tuy nhiên, nếu cùng API vẫn nhận cookie được browser tự gửi thì gọi nó là “REST” hoặc “stateless” không tự làm CSRF biến mất. HTTP Basic trong một số browser cũng cần được đánh giá như một dạng credential có thể tự gửi lại.

## 4. Header mặc định: bảng tham chiếu và những điều không tự có

Với một response thực sự đi qua chain Spring Security, tài liệu chung của các dòng hiện đại nêu các **giá trị tham chiếu** sau:

```http
Cache-Control: no-cache, no-store, max-age=0, must-revalidate
Pragma: no-cache
Expires: 0
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Strict-Transport-Security: max-age=31536000 ; includeSubDomains
```

**Dòng HSTS ở trên chỉ áp dụng khi request được nhận diện là HTTPS.** Đây là **baseline tài liệu** để đối chiếu, không phải cam kết rằng mỗi response trong hệ thống luôn có nguyên xi mọi dòng: controller, Spring MVC/WebFlux, resource handler, proxy, custom header writer hoặc chain selection có thể thay đổi kết quả. Thứ tự header, cách viết khoảng trắng và hoa/thường có thể khác mà không làm thay đổi ngữ nghĩa.

| Header | Mặc định tham chiếu khi đi qua chain | Ý nghĩa và cách đối chiếu |
| --- | --- | --- |
| `Cache-Control` | `no-cache, no-store, max-age=0, must-revalidate` | Giảm khả năng lưu nội dung nhạy cảm; có thể bị ứng dụng ghi đè có chủ đích cho static assets |
| `Pragma`, `Expires` | `no-cache` và `0` | Tương thích hành vi cache trên các client cũ |
| `X-Content-Type-Options` | `nosniff` | Yêu cầu trình duyệt không suy đoán loại nội dung; vẫn phải thiết lập `Content-Type` chính xác |
| `X-Frame-Options` | `DENY` | Giảm nguy cơ clickjacking bằng iframe; `SAMEORIGIN` là một tùy chỉnh có chủ đích |
| `X-XSS-Protection` | `0` ở các dòng hiện đại | Tắt XSS auditor cũ; **không phải** là tắt mọi lớp chống XSS. Dòng 5.x cũ từng dùng giá trị `1; mode=block` |
| `Strict-Transport-Security` | Thường `max-age=31536000; includeSubDomains` **chỉ HTTPS** | Browser ghi nhớ chính sách chỉ dùng HTTPS; kiểm tra HTTPS và reverse proxy |
| `Content-Security-Policy` | **Không được thêm mặc định** | Phải tự thiết kế CSP cho ứng dụng, có thể bắt đầu bằng Report-Only |
| `Content-Security-Policy-Report-Only` | **Không mặc định** | Cần bật có chủ đích |
| `Permissions-Policy` | **Không mặc định** | Tự khai báo tính năng browser được phép |
| `Clear-Site-Data` | **Không mặc định** | Chỉ thêm có chủ đích, ví dụ trên logout |
| `Access-Control-Allow-Origin` | **Không phải header vô điều kiện** | Chỉ xuất hiện theo xử lý CORS/request có `Origin` và allowlist phù hợp |
| `Set-Cookie` | **Không do bộ header writer mặc định quyết định toàn bộ** | Thuộc session/container/framework/app; kiểm tra `Secure`, `HttpOnly`, `SameSite` riêng |

**Lưu ý khi so sánh Servlet với Reactive:** tài liệu chi tiết về `Referrer-Policy` có khác biệt mô tả: trang Servlet nêu không tự thêm header này, còn trang Reactive hiện hành mô tả mặc định `Referrer-Policy: no-referrer`. Vì vậy, không dùng một bảng duy nhất để áp cứng cả hai stack. Hãy kiểm tra phiên bản tài liệu tương ứng và response thực tế; nếu chính sách referrer là yêu cầu bắt buộc, cấu hình tường minh ở đúng stack.

### 4.1. Vì sao không có CSP theo mặc định?

Một CSP an toàn phải biết chính xác trang tải script/style/image/font từ đâu, có iframe hay không, dùng nonce/hash hay inline script không. Framework không thể tự chọn policy chung mà không nguy cơ chặn chức năng hợp lệ.

Ví dụ policy cho ứng dụng đơn giản:

```http
Content-Security-Policy: default-src 'self'; object-src 'none'; frame-ancestors 'none'
```

Policy cần được đánh giá với tài nguyên thật. `frame-ancestors 'none'` hạn chế nhúng trang trong frame; có thể triển khai `Content-Security-Policy-Report-Only` để quan sát trước khi enforce. CSP **không thay thế** escaping output, validation, authentication hay CSRF.

### 4.2. Vì sao HSTS có thể “biến mất” sau proxy?

HSTS chỉ được browser tiếp nhận qua **HTTPS hợp lệ**. Nếu client kết nối `https://app.example.com` vào reverse proxy, còn proxy gửi HTTP tới backend, ứng dụng có thể thấy scheme là HTTP nếu forwarded headers không được xử lý an toàn. Khi đó backend có thể không phát HSTS.

Kiểm tra ba bề mặt:

1. HTTPS public từ phía browser: `https://app.example.com/...`.
2. HTTP backend nội bộ: chỉ để chẩn đoán, không dùng làm kết luận HSTS production.
3. Cấu hình proxy/trusted forwarded headers: xác định ai được phép cung cấp `Forwarded` hoặc `X-Forwarded-Proto`.

Nếu thêm `preload` hoặc `includeSubDomains`, đánh giá toàn bộ subdomain có hỗ trợ HTTPS trước khi áp dụng lâu dài. Không bật preload chỉ vì scanner gợi ý, vì việc gỡ bỏ khỏi danh sách preload có thể mất thời gian.

### 4.3. Header nào có thể được ứng dụng ghi đè?

Spring Security thường thêm cache-control an toàn, nhưng tài liệu cho phép ứng dụng cung cấp header cache riêng cho static resources. Reverse proxy/CDN cũng có thể xóa, thêm hoặc gộp response headers. Vì vậy:

- `Cache-Control: public, max-age=...` trên file CSS **có thể** là quyết định cache hợp lý.
- Cùng header trên response chứa dữ liệu tài khoản nhạy cảm cần xem lại.
- Một header chỉ xuất hiện trên đường public nhưng không có trong MockMvc/WebTestClient có thể do proxy.
- Header xuất hiện trong mock test nhưng mất khi truy cập public có thể do CDN hoặc URL không đi qua Spring Security tại đường deployment.

Không coi mọi khác biệt văn bản là lỗ hổng; đối chiếu **đích bảo vệ** và nguồn ghi header.

## 5. Cấu hình baseline Servlet để kiểm chứng

Ví dụ sau chạy trong ứng dụng **Spring MVC/Servlet** đã có nguồn xác thực và endpoint phục vụ test. Chính sách public chỉ mở `/probe`; phần còn lại cần đăng nhập. CSRF và security headers dùng mặc định, **không thêm CSP** để xác minh rằng CSP không xuất hiện khi chưa được khai báo.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletBaselineSecurity {

    @Bean
    SecurityFilterChain baseline(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/probe").permitAll()
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .headers(Customizer.withDefaults())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
```

Đoạn cấu hình tường minh giúp người học chỉ đúng các tính năng đang được bật. Một ứng dụng Spring Security chuẩn thường đã bật CSRF và default headers ngay cả khi không gọi `csrf(...)` và `headers(...)`, nhưng khi đối chiếu nên viết tường minh để thuận tiện xác nhận. **Không nhất thiết phải tạo lại một bean baseline trên production** nếu production đã có nhiều chain: thêm bean mới có thể làm đổi thứ tự chọn chain. Hãy chỉnh cấu hình đang sở hữu URL và test.

### 5.1. Tùy chỉnh sau khi đã ghi nhận baseline

Ví dụ thêm CSP sau khi đã có phiếu đối chiếu:

```java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
        )
    )
);
```

Ví dụ này **thay thế** lời gọi `.headers(Customizer.withDefaults())` ở cấu hình trên, không cần khai báo cả hai. Các header mặc định khác vẫn được giữ khi chỉ tùy chỉnh CSP như vậy.

Ví dụ thay `X-Frame-Options: DENY` bằng `SAMEORIGIN` cho ứng dụng cần frame cùng origin:

```java
http.headers(headers -> headers
    .frameOptions(frame -> frame.sameOrigin())
);
```

Chỉ dùng `SAMEORIGIN` khi có nhu cầu rõ ràng; nếu ứng dụng cho phép iframe từ nhiều origin phải đánh giá CSP `frame-ancestors` riêng. Không dùng `headers(headers -> headers.disable())` chỉ để thay một header.

### 5.2. Muốn dùng CSRF token trong cookie cho SPA?

Trong Servlet, có thể cấu hình `CookieCsrfTokenRepository` nhưng **đây là tùy chỉnh, không phải mặc định**:

```java
import org.springframework.security.web.csrf.CookieCsrfTokenRepository;

// Dùng cho các phiên bản có hỗ trợ API này:
http.csrf(csrf -> csrf
    .csrfTokenRepository(CookieCsrfTokenRepository.withHttpOnlyFalse())
);
```

`withHttpOnlyFalse()` cho phép JavaScript đọc cookie XSRF, nên chỉ dùng khi kiến trúc client thực sự cần. Với Spring Security 6+, xử lý token bị che (BREACH) và cơ chế deferred token khiến **chỉ cấu hình cookie repository chưa chắc đã đủ cho SPA**. Phải xem hướng dẫn SPA của **đúng dòng phiên bản**, cân nhắc handler phù hợp và xác minh token mới sau login/logout. Tài liệu Spring Security 7.2 có hỗ trợ tiện ích `csrf(csrf -> csrf.spa())`; không sao chép API này sang 6.5 mà chưa kiểm tra nó tồn tại ở phiên bản đang dùng.

## 6. Cấu hình baseline Reactive cho WebFlux

Trong WebFlux, dùng `SecurityWebFilterChain` và `ServerHttpSecurity`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveBaselineSecurity {

    @Bean
    SecurityWebFilterChain baseline(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/probe").permitAll()
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .headers(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Đối chiếu với Servlet:

- `authorizeExchange`/`pathMatchers` thay cho `authorizeHttpRequests`/`requestMatchers`.
- `CsrfWebFilter` dùng `WebSessionServerCsrfTokenRepository` mặc định; không dùng `HttpSessionCsrfTokenRepository`.
- `SecurityWebFilterChain` thay cho `SecurityFilterChain`.
- `ServerHttpSecurity.headers(...)` có configurer riêng; một số tên method của header writer có khác biệt giữa Servlet và Reactive **cũng như giữa các dòng phiên bản**.
- WebFlux phản hồi bất đồng bộ; dùng `WebTestClient` để kiểm chứng, tránh dùng MockMvc cho WebFlux.

Thêm CSP ở WebFlux dùng phong cách tương tự:

```java
http.headers(headers -> headers
    .contentSecurityPolicy(policy -> policy
        .policyDirectives(
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
        )
    )
);
```

Nếu ứng dụng có cả Spring MVC và WebFlux dependencies, xác minh Spring Boot đã chọn web application type nào. Không khai báo cả hai bean baseline rồi cho rằng request sẽ đi qua hai cơ chế bảo mật song song.

## 7. Kiểm thử CSRF: so sánh request thiếu, sai và đúng token

Một phép thử hữu ích cần **ít nhất ba yêu cầu khác nhau**:

1. **POST đã xác thực, không token:** kỳ vọng bị CSRF từ chối.
2. **POST đã xác thực, token sai:** vẫn bị từ chối.
3. **POST đã xác thực, token hợp lệ:** vượt qua CSRF để thực hiện phần còn lại (có thể còn bị từ chối bởi authorization hoặc validation).

Cần bổ sung GET/HEAD và method thay đổi trạng thái phù hợp. **Không dùng một POST anonymous** để kết luận CSRF có bật hay không, vì ứng dụng có thể trả 401/redirect ở lớp authentication trước khi kiểm thử mong muốn trở nên rõ ràng.

### 7.1. Servlet: `MockMvc` + `spring-security-test`

Giả sử ứng dụng có `POST /orders` trả 200 cho user `alice` khi request hợp lệ; test đã được cấu hình Spring Security filter chain (ví dụ dùng `@SpringBootTest` với `@AutoConfigureMockMvc`):

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ServletCsrfBaselineTest {

    @Autowired MockMvc mvc;

    @Test
    void unsafeRequestRequiresValidToken() throws Exception {
        mvc.perform(post("/orders").with(user("alice")))
           .andExpect(status().isForbidden());

        mvc.perform(post("/orders")
                .with(user("alice"))
                .with(csrf().useInvalidToken()))
           .andExpect(status().isForbidden());

        mvc.perform(post("/orders")
                .with(user("alice"))
                .with(csrf()))
           .andExpect(status().isOk());
    }
}
```

Đoạn test giả định dự án đã có controller, hợp đồng HTTP và quyền truy cập phù hợp. Trong Spring Boot 4, tên test starter/import auto-configuration có thể thay đổi theo cấu trúc module Boot; nếu annotation import khác, chọn dependency/testing annotation đúng với phiên bản của dự án. Nếu endpoint trả 201 hoặc 204, điều chỉnh kỳ vọng theo contract, **không sửa chính sách CSRF** chỉ để khớp ví dụ. Khi build mock test thủ công, cần áp dụng `springSecurity()` để bộ lọc được chạy.

### 7.2. Reactive: `WebTestClient` + `spring-security-test`

Giả sử `client` là `WebTestClient` đã bind vào `ApplicationContext` và áp dụng `springSecurity()`, endpoint `POST /orders` trả 200:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void reactiveUnsafeRequestRequiresCsrf() {
    client.mutateWith(mockUser("alice"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("alice"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk();
}
```

Ví dụ thiết lập client cho integration test:

```java
WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
```

Khi test WebFlux, `mockUser()` và `csrf()` của `spring-security-test` tác động vào test context, không tự tạo phiên xác thực tại một server HTTP từ xa. Để kiểm thử từ trình duyệt/qua proxy phải dùng credential và token thật do ứng dụng cấp.

### 7.3. Những kịch bản phát hiện sai lệch mặc định

| Thử nghiệm | Kết quả thường kỳ vọng | Nếu khác, cần điều tra |
| --- | --- | --- |
| GET công khai | Không yêu cầu token | Có filter/cấu hình CSRF tùy chỉnh? Endpoint có side effect? |
| POST có session, thiếu token | 403 nếu user đã xác thực và CSRF áp dụng | Chain match? CSRF bị tắt? Endpoint được loại trừ? |
| POST token sai | 403 | Repo/handler có kiểm tra hay không? |
| POST token đúng | Vượt qua CSRF; status tùy nghiệp vụ | Session hết hạn? Xử lý BREACH? Authorization? |
| POST login không token | Bị chặn nếu login đi qua CSRF mặc định | Login URL có thuộc chain? |
| Logout GET | Không thực hiện logout trong flow mặc định có CSRF | Custom logout matcher đã mở GET? |
| SPA sau login/logout | Có cách lấy token mới, POST tiếp tục hợp lệ | Token cookie cũ đã bị xóa, deferred loading |
| Preflight OPTIONS | Không bị bắt CSRF theo matcher mặc định | CORS source, authorization, proxy chặn OPTIONS |

Nếu sản phẩm dùng session cookie, nên kiểm tra thêm SameSite, Secure, HttpOnly, session timeout và session fixation. Các thuộc tính cookie không thể suy ra từ riêng `CsrfFilter`.

## 8. Kiểm thử response headers ở nhiều tầng

### 8.1. Servlet: kiểm tra header từ MockMvc

Giả sử endpoint `GET /probe` được cho phép, chain đang chạy với default headers:

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void baselineResponseHeaders() throws Exception {
    mvc.perform(get("/probe"))
       .andExpect(status().isOk())
       .andExpect(header().string("X-Content-Type-Options", "nosniff"))
       .andExpect(header().string("X-Frame-Options", "DENY"))
       .andExpect(header().doesNotExist("Content-Security-Policy"));
}

@Test
void hstsRequiresSecureRequest() throws Exception {
    mvc.perform(get("/probe").secure(true))
       .andExpect(status().isOk())
       .andExpect(header().exists("Strict-Transport-Security"));
}
```

Trong test baseline này, cố ý **không** cấu hình CSP. Nếu CSP đã được controller/proxy/test customization thêm, expectation `doesNotExist` không còn phù hợp; đó là dấu hiệu cần xác định **nguồn ghi header**, không phải mặc định framework bất ngờ sai. Test `.secure(true)` mô phỏng request HTTPS đối với Servlet; nó không thay thế thử HTTPS từ browser qua reverse proxy.

Không nên khẳng định chính xác chuỗi HSTS bằng cách đối sánh dấu cách: hãy tách `max-age`, `includeSubDomains` và `preload` thành các thuộc tính ngữ nghĩa cần đối chiếu, đồng thời cố định chính sách nếu sản phẩm bắt buộc giá trị cụ thể.

### 8.2. Reactive: kiểm tra header với WebTestClient

Với client WebFlux đã có `springSecurity()` và handler `GET /probe`:

```java
@Test
void reactiveDefaultHeaders() {
    client.get().uri("/probe")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().valueEquals("X-Content-Type-Options", "nosniff")
        .expectHeader().valueEquals("X-Frame-Options", "DENY")
        .expectHeader().doesNotExist("Content-Security-Policy");
}
```

Đối với HSTS, phải đảm bảo exchange mô phỏng secure scheme/SSL đúng cách hoặc thực hiện request HTTPS thực qua server; một test dùng URL HTTP nội bộ không đủ để kết luận mặc định HSTS bị tắt.

### 8.3. So sánh qua HTTPS public và HTTP nội bộ

Với endpoint do bạn quản lý, kiểm tra bằng `curl`:

```bash
# Quan sát header public trên HTTPS; không thêm -k để bỏ qua kiểm tra TLS.
curl -i "https://app.example.com/probe"

# Quan sát origin/backend chỉ khi bạn được quyền truy cập môi trường nội bộ.
curl -i "http://localhost:8080/probe"

# Preflight CORS hợp lệ và sai origin phải được kiểm tra riêng.
curl -i -X OPTIONS "https://app.example.com/api/orders" \
  -H "Origin: https://frontend.example.com" \
  -H "Access-Control-Request-Method: POST"
```

Lệnh trên là mẫu sử dụng tên miền minh họa; hãy thay bằng endpoint thật có chủ đích. Trên PowerShell, `curl` đôi khi là alias của `Invoke-WebRequest`; để dùng cú pháp cURL, gọi `curl.exe`. Khi kiểm tra có cookie/session, chỉ dùng tài khoản test và tránh dán giá trị session/token vào log chia sẻ.

**Một phiếu đo hữu ích** gồm các cột:

| Kênh | URL/method | Auth/cookie | Scheme | Response headers | CSRF status | Ghi chú |
| --- | --- | --- | --- | --- | --- | --- |
| MockMvc | GET `/probe` | Ẩn danh | HTTP mock | Default header baseline | Không áp dụng | Server-side security chain |
| MockMvc | GET `/probe` | Ẩn danh | HTTPS mock | Có HSTS nếu mặc định | Không áp dụng | Mô phỏng `secure(true)` |
| WebTestClient | GET `/probe` | Ẩn danh | Test exchange | Header theo reactive config | Không áp dụng | Reactive filter chain |
| Browser | GET HTML | Có session | HTTPS public | Header sau CDN/proxy | Không áp dụng | Dựa trên Network inspector |
| Browser | POST `/orders` | Có session | HTTPS public | Headers + status | Token thiếu/đúng | Test CSRF thật |
| API test | OPTIONS preflight | Không cookie | HTTPS public | CORS allowlist | Không yêu cầu mặc định | Phân biệt CORS/CSRF |

## 9. Các tình huống chẩn đoán khi tài liệu và runtime không khớp

### Tình huống A — POST từ browser trả 403 sau nâng Security 5 lên 6

**Dấu hiệu:** ứng dụng dùng cookie session; GET chạy, POST không chạy. Mã Java không gọi `csrf.disable()`.

**Giả thuyết:** CSRF vẫn bật, nhưng SPA chưa xử lý deferred token/BREACH handler hoặc token bị xóa sau login/logout.

**Kiểm tra:** thử POST bằng test helper `with(csrf())` hoặc `mutateWith(csrf())`; xác minh repository, handler, header token, session cookie và thời điểm token mới được trả về. Đối chiếu migration guide của đúng phiên bản. **Không sửa bằng cách tắt CSRF cho toàn chain.**

### Tình huống B — Static asset thiếu X-Frame-Options/CSP/HSTS

**Dấu hiệu:** các trang HTML có header, file CSS/JS public lại không.

**Giả thuyết:** Servlet có `web.ignoring()` cho `/assets/**`, hoặc asset được CDN/nginx phục vụ trực tiếp.

**Kiểm tra:** xác định asset có đi qua security chain hay không; so sánh `permitAll()` với ignore; đọc response tại nguồn CDN. Khi cần bảo vệ bằng Spring Security headers, để request đi qua chain và dùng `permitAll()` theo chính sách.

### Tình huống C — Không có HSTS dù test controller thành công

**Dấu hiệu:** HTTP backend không phát HSTS; browser public HTTPS có hoặc không.

**Giả thuyết:** request backend bị nhận là HTTP, TLS terminate tại proxy, forwarded headers chưa được xử lý hoặc proxy xóa header.

**Kiểm tra:** `curl -i https://...` tại cổng public; kiểm tra trust proxy/forwarded scheme; xác minh policy ở proxy nếu HSTS do proxy ghi. Không đánh giá dựa trên HTTP localhost duy nhất.

### Tình huống D — Scan báo thiếu CSP

**Dấu hiệu:** `X-Frame-Options: DENY` có nhưng `Content-Security-Policy` vắng mặt.

**Nguyên nhân:** Spring Security **không thêm CSP mặc định**. Không phải một lỗi phát sinh do nâng phiên bản.

**Giải pháp:** thiết kế CSP cho ứng dụng; có thể bật `reportOnly()` trước khi enforce; sau đó kiểm thử HTML, script, iframe, CDN và các route thực tế.

### Tình huống E — HTTP 403 trên OPTIONS preflight

**Dấu hiệu:** lỗi browser “CORS preflight failed”, dễ bị nhầm với CSRF.

**Giả thuyết:** preflight không gửi session cookie, chính sách CORS/authorization hoặc proxy chặn trước khi vào handler. Mặc định CSRF thường **không** yêu cầu token cho OPTIONS.

**Kiểm tra:** gửi `Origin` và `Access-Control-Request-Method` đầy đủ; kiểm tra `CorsConfigurationSource` Servlet/Reactive đúng package và xử lý trước authentication; xác minh allowed origins/methods/headers. CORS không là header luôn có trên mọi response.

### Tình huống F — Một số URL bảo vệ đúng, URL khác lại không có headers

**Dấu hiệu:** `/api/**` có headers nhưng `/admin/**` không.

**Giả thuyết:** chain API được cấu hình riêng với `securityMatcher("/api/**")`, thiếu fallback chain, hoặc filter chain có `headers.disable()`.

**Kiểm tra:** liệt kê các bean chain và `@Order`; xác nhận request được xử lý bởi chain đầu tiên phù hợp; thêm test ở ranh giới URL, xem lại request path rewrite và HTTP firewall khi có encoded paths. Nếu không có chain match, Spring Security không thể ghi header cho request đó.

### Tình huống G — Kết quả X-XSS-Protection khác bảng từ tài liệu cũ

**Dấu hiệu:** tài liệu Spring Security 5.x ghi `X-XSS-Protection: 1; mode=block`, bản hiện đại cho `0`.

**Giải thích:** đây là thay đổi chủ đích theo thực hành bảo mật trình duyệt hiện đại; XSS auditor cũ đã lỗi thời. `0` không có nghĩa Spring Security vô hiệu hóa CSRF, CSP hay toàn bộ bảo vệ chống XSS. Hãy áp dụng CSP, output encoding và validation phù hợp thay vì bật lại XSS auditor cũ chỉ để khớp scanner.

### Tình huống H — Referrer-Policy khác giữa Servlet và Reactive

**Dấu hiệu:** bảng chuẩn của nhóm khẳng định mọi stack đều không có `Referrer-Policy`, nhưng một WebFlux service có `no-referrer`.

**Giải thích:** tài liệu chi tiết của hai stack có mô tả khác nhau. Ghi nhận điều kiện runtime, phiên bản và cấu hình; nếu cần policy thống nhất, khai báo tường minh phù hợp cho từng stack và thêm test. Đừng sửa production theo bảng version-agnostic chưa kiểm tra.

## 10. Quy trình đối chiếu trước và sau khi nâng cấp

Có thể dùng quy trình dưới đây cho pull request nâng Spring Security hoặc Spring Boot:

1. **Khóa đường baseline:** ghi phiên bản JDK/Boot/Framework/Security đã resolve; ghi URL, stack, chain và cấu hình proxy. Không lấy version từ riêng `pom.xml`.
2. **Chọn request đại diện:** GET public/private, POST có/không token, login/logout, OPTIONS preflight, URL bất thường, HTTPS HTML và static resources.
3. **Thu kết quả trước nâng cấp:** lưu HTTP status, response headers, token lifecycle và session behavior; phân biệt response từ backend với response public.
4. **Đọc tài liệu versioned:** so sánh mặc định CSRF, repository, handler (đặc biệt 5→6), headers, API đã deprecate và migration guide.
5. **Thực hiện nâng cấp phụ thuộc và cấu hình:** ưu tiên BOM của Boot, sửa bean/filter chains theo Lambda DSL và tương thích Servlet/Reactive.
6. **Chạy lại cùng bộ request:** phân biệt thay đổi mong đợi (ví dụ `X-XSS-Protection: 0`) với regression (bỏ mất CSRF, HSTS hay authorization).
7. **Điều tra khác biệt theo tầng:** dependency → chain match → CSRF handler/repository → custom headers → reverse proxy/CDN.
8. **Chốt policy tường minh khi quan trọng:** CSP, Referrer-Policy, HSTS, CORS allowlist, các ngoại lệ CSRF và mục tiêu cookie/session.

### Ví dụ bảng diff cho một lần nâng cấp

| Mục | Trước nâng cấp | Sau nâng cấp | Kết luận |
| --- | --- | --- | --- |
| POST với token sai | 403 | 403 | Đạt yêu cầu chống CSRF |
| POST token đúng | 200 | 403 | Điều tra token masking/deferred loading và session |
| `X-Content-Type-Options` | `nosniff` | `nosniff` | Giữ nguyên |
| `X-XSS-Protection` | `1; mode=block` | `0` | Có thể là thay đổi mặc định có chủ đích theo version |
| HSTS HTTPS public | Có | Không | Điều tra proxy/scheme/header writer |
| CSP custom | Có | Không | Điều tra chain selection/header config |
| OPTIONS từ origin lạ | Không allow origin | Cho phép `*` | Lỗi CORS policy cần sửa |

Các số liệu ở bảng là **kịch bản minh họa**, không đại diện một bộ kết quả kiểm thử thực tế đã chạy trên hệ thống người học.

## 11. Bài tập thực hành

**Bài tập 1 — Đọc mặc định theo phiên bản.** Một dịch vụ đang chạy Spring Security 6.5 và một dịch vụ khác 7.2. Hãy lập bảng ghi CSRF enabled, token repository, request handler và các header mặc định của từng dịch vụ từ tài liệu **theo số phiên bản**. Đánh dấu những chính sách phải kiểm chứng runtime thay vì suy từ tài liệu.

**Bài tập 2 — Servlet CSRF.** Tạo endpoint POST chỉ cho user đã đăng nhập. Dùng MockMvc kiểm thử POST thiếu token, token sai, token đúng; bổ sung thử login/logout qua GET/POST. Giải thích vì sao `with(user(...))` cần xuất hiện trong test trước khi suy ra lỗi CSRF.

**Bài tập 3 — Reactive CSRF.** Với WebFlux, tạo `SecurityWebFilterChain` và endpoint POST tương tự. Dùng `WebTestClient`/`spring-security-test` để so sánh token và kiểm tra `WebSessionServerCsrfTokenRepository`. Giải thích lý do không dùng `HttpSessionCsrfTokenRepository`.

**Bài tập 4 — Header qua proxy.** Truy cập `GET /probe` qua HTTP localhost và HTTPS public. Lập bảng `X-Content-Type-Options`, `X-Frame-Options`, HSTS, CSP, Referrer-Policy và cache headers. Xác định header nào do Spring Security, ứng dụng hoặc proxy thêm; không yêu cầu mọi header giống nhau ở cả hai kênh.

**Bài tập 5 — Chẩn đoán SPA.** Sau nâng Security 5→6, SPA có cookie `XSRF-TOKEN` nhưng POST sau logout/login bị 403. Giải thích ảnh hưởng của deferred tokens, masking/BREACH, token rotation và cách đối chiếu với hướng dẫn SPA của đúng phiên bản.

## 12. Checklist hoàn thành bài

- [ ] Biết chính xác phiên bản đã resolve và dùng tài liệu Spring Security có số phiên bản.
- [ ] Xác nhận stack Servlet/Reactive, chain match URL và mọi đường public đi qua chain dự kiến.
- [ ] Phân biệt CSRF token **request** với security response headers; không đòi `X-CSRF-TOKEN` tự xuất hiện ở response.
- [ ] Hiểu method được kiểm tra CSRF theo mặc định và có test thiếu/sai/đúng token.
- [ ] Nhận diện repository/handler mặc định, deferred loading và BREACH khi nâng từ 5 lên 6+.
- [ ] Kiểm tra lifecycle token khi login/logout và browser cookie/session.
- [ ] Đối chiếu `Cache-Control`, `Pragma`, `Expires`, `nosniff`, `X-Frame-Options`, `X-XSS-Protection` và HSTS.
- [ ] Biết CSP/Permissions-Policy/Clear-Site-Data không mặc định, CORS header chỉ xuất hiện theo policy/request.
- [ ] Xác minh HSTS trên HTTPS public và xem xét proxy/trusted forwarded headers.
- [ ] Test cả Servlet bằng MockMvc và Reactive bằng WebTestClient khi sản phẩm hỗ trợ cả hai.
- [ ] Ghi nhận mọi sai khác version/runtime trong phiếu trước khi chỉnh policy production.

## Tài liệu chính thức để đối chiếu

1. [Spring Security Reference — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html) — matcher mặc định, `HttpSessionCsrfTokenRepository`, BREACH, deferred tokens, SPA, login/logout và test.
2. [Spring Security Reference — Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — `CsrfWebFilter`, `WebSessionServerCsrfTokenRepository`, token handler và logout trong WebFlux.
3. [Spring Security Reference — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/features/exploits/headers.html) — bảng header mặc định tham chiếu và HSTS chỉ trên HTTPS.
4. [Spring Security Reference — Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html) — CSP, cache control, frame options, HSTS, referrer, permissions và custom headers.
5. [Spring Security Reference — Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — header support của WebFlux và những khác biệt với Servlet.
6. [Spring Security Reference 6.5 — Servlet CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html) — ví dụ khóa dòng tài liệu khi ứng dụng vẫn đang ở Security 6.5.
7. [Spring Security Reference 7.2 — Servlet CSRF](https://docs.spring.io/spring-security/reference/7.2/servlet/exploits/csrf.html) — ví dụ khóa dòng tài liệu khi ứng dụng dùng Security 7.2.
8. [Spring Security — Servlet MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) và [Reactive WebTestClient CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html) — kiểm thử cơ chế chống CSRF có hiệu lực.

**Tự đánh giá:** Vì sao `POST` có user hợp lệ vẫn nhận 403? Vì sao không thấy `XSRF-TOKEN` cookie chưa thể kết luận CSRF bị tắt? Vì sao thiếu CSP là trạng thái mặc định nhưng thiếu HSTS trên HTTPS public cần điều tra? Và bằng cách nào bạn chứng minh response thực tế đang đi qua đúng security chain?
