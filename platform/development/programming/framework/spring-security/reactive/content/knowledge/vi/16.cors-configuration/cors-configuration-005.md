# Khai báo origin, method, header và exposedHeaders cần thiết

> **Chủ đề cha:** Cấu hình CORS trong **Spring Security reactive / Spring WebFlux**. Bài hướng dẫn cấu hình chính xác `allowedOrigins`, `allowedMethods`, `allowedHeaders`, `exposedHeaders`, `allowCredentials` và `maxAge` bằng `CorsConfiguration` / `UrlBasedCorsConfigurationSource`, kết nối với `ServerHttpSecurity.cors(...)`, thử nghiệm preflight của trình duyệt và kiểm thử bằng `WebTestClient`. Mã thực hành dùng **Java 17+, Spring Boot 3.x, Spring Framework 6.x và Spring Security 6.x**.

## 1. Mục tiêu

Sau bài này bạn có thể:

1. Phân biệt **same-origin policy**, **cross-origin request**, **CORS preflight**, **actual request**, và CORS với authentication/authorization.
2. Xác định origin theo **scheme + host + port**, không nhầm origin với path hay wildcard.
3. Khai báo đúng **HTTP methods** được browser phép dùng cross-origin qua `setAllowedMethods(...)`.
4. Khai báo **request header names** trình duyệt được gửi qua `setAllowedHeaders(...)`, ví dụ `Authorization`, `Content-Type` và `X-Request-Id`.
5. Khai báo **response header names** frontend được đọc bằng `setExposedHeaders(...)`, ví dụ `ETag`, `Location`, `X-Request-Id`.
6. Biết khi nào `allowCredentials(true)` phù hợp, vì sao không kết hợp nó với `allowedOrigins("*")` và các lưu ý về cookie/CSRF.
7. Đặt CORS processing **trước Spring Security authentication** cho preflight `OPTIONS` và không mở nhầm API bằng `permitAll()`.
8. Có một ví dụ WebFlux hoàn chỉnh, kiểm thử origin/method/header được cho phép hoặc bị từ chối, kiểm tra `Access-Control-*` headers.
9. Hiểu vì sao `curl` có thể gọi API dù browser báo CORS và tại sao CORS **không** phải firewall, không thay thế phân quyền.
10. Rà soát cấu hình theo nguyên tắc **minimum necessary cross-origin access**, phân biệt development với production.

## 2. Origin là gì?

Origin của một trang web là bộ ba **scheme, host, port**. Hai URL có cùng origin khi bộ ba này trùng nhau.

| Trang web đang chạy tại | API được gọi tại | Cùng origin? |
| --- | --- | --- |
| `https://app.example.com/home` | `https://app.example.com/api/items` | **Có**, khác path không tạo origin mới |
| `https://app.example.com` | `https://api.example.com` | **Không**, khác hostname |
| `http://localhost:5173` | `http://localhost:8080` | **Không**, khác port |
| `https://app.example.com` | `http://app.example.com` | **Không**, khác scheme |
| `https://app.example.com` | `https://app.example.com:8443` | **Không**, khác port |
| `https://app.example.com/page` | `https://app.example.com/other` | **Có**, cùng scheme/host/port |

Khi browser JavaScript truy cập tài nguyên khác origin, browser áp dụng **same-origin policy** và CORS: server có thể cho phép một số origin đọc response thông qua headers `Access-Control-Allow-Origin` và các header CORS liên quan.

**Quan trọng:** CORS là chính sách **browser kiểm tra trên các request cross-origin**; nó không chặn `curl`, `WebClient`, server-to-server clients hoặc một kẻ tấn công gọi trực tiếp API. Nếu endpoint cần đăng nhập/role/scope/tenant, phải dùng **Spring Security authentication và authorization** độc lập với CORS.

### 2.1 Origin không chứa path và trailing slash

Một cấu hình đúng:

```java
configuration.setAllowedOrigins(
    List.of("https://app.example.com", "http://localhost:5173")
);
```

Đừng cấu hình `"https://app.example.com/dashboard"` hoặc `"https://app.example.com/"` như một origin chuẩn; `Origin` header của browser chỉ chứa scheme, host và port (có những trường hợp `Origin: null` riêng cần đánh giá bảo mật). `https://app.example.com` **khác** `http://app.example.com`, và dev port `5173` **khác** dev port `3000`.

## 3. Năm nhóm tham số quan trọng trong CorsConfiguration

`CorsConfiguration` trong Spring Framework lưu chính sách CORS. Những method có tên gần nhau nhưng ý nghĩa khác:

| Thuộc tính Java | CORS header tương ứng | Quyết định |
| --- | --- | --- |
| `setAllowedOrigins(List<String>)` | `Access-Control-Allow-Origin` | Origin nào được phép đọc response cross-origin |
| `setAllowedMethods(List<String>)` | `Access-Control-Allow-Methods` | HTTP **method thực tế** nào được phép trong request cross-origin |
| `setAllowedHeaders(List<String>)` | `Access-Control-Allow-Headers` | Tên **request headers** nào frontend có thể gửi |
| `setExposedHeaders(List<String>)` | `Access-Control-Expose-Headers` | Tên **response headers** nào frontend JavaScript được đọc |
| `setAllowCredentials(Boolean)` | `Access-Control-Allow-Credentials` | Có cho phép credentialed cross-origin requests ở mức CORS không |
| `setMaxAge(Long)` | `Access-Control-Max-Age` | Gợi ý browser cache kết quả preflight bao lâu, tính bằng giây |
| `setAllowedOriginPatterns(List<String>)` | Thường trả origin thật đã match | Matcher origin động có wildcard theo hostname; cần kiểm soát phạm vi nghiêm ngặt |

**Ghi nhớ dễ nhầm nhất:**

- `allowedHeaders` **không** nói frontend được đọc response headers nào; đó là `exposedHeaders`.
- `exposedHeaders` **không** cho phép frontend gửi request headers; đó là `allowedHeaders`.
- `allowedMethods` liệt kê **GET/POST/PATCH... thực tế**, không cần thêm `OPTIONS` chỉ vì preflight dùng HTTP OPTIONS.
- `allowedOrigins` không quyết định user nào có quyền truy cập route; nó chỉ ảnh hưởng browser CORS.
- `allowCredentials` không tự tạo session/cookie hay xác thực password. Nó chỉ là chính sách CORS về gửi credential và cho phép JS đọc response credentialed.

### 3.1 allowedOrigins: nên dùng danh sách tường minh

Ví dụ frontend từ dev và production:

```java
config.setAllowedOrigins(List.of(
    "http://localhost:5173",
    "https://app.example.com"
));
```

Đây là **mảnh cấu hình** cần nằm trong Spring bean. Trong production, loại bỏ origin localhost nếu không có nhu cầu thật, ví dụ tách bằng Spring profiles và external configuration được kiểm soát. Không nhận origin bất kỳ từ một HTTP request rồi tự động phản chiếu vào response.

Nếu chỉ có một ứng dụng web tin cậy, danh sách **một exact origin** thường tốt hơn wildcard.

### 3.2 allowedOriginPatterns: khi cần nhưng phải cẩn trọng

Ví dụ có thể viết:

```java
config.setAllowedOriginPatterns(
    List.of("https://*.example.com")
);
```

Spring sẽ kiểm tra origin theo pattern và có thể trả **origin thực tế đã match** trong `Access-Control-Allow-Origin`. Nó không phải yêu cầu trình duyệt hiểu chuỗi wildcard của pattern. Tuy nhiên, cho phép **mọi subdomain** có thể bao gồm subdomain chưa được bảo vệ, subdomain bị chiếm quyền hoặc trang của tenant không đáng tin. Nếu dùng với cookies/credentials, rủi ro càng cao.

**Ưu tiên:** exact-origin allowlist. Dùng patterns chỉ khi bạn có cơ chế quản lý hostname/tenant thật sự và kiểm soát quyền sở hữu các host được khớp. Không lấy tenant host thẳng từ `Origin` rồi coi như đã được xác thực.

### 3.3 allowedMethods: khai báo theo nghiệp vụ

```java
config.setAllowedMethods(List.of(
    "GET", "POST", "PATCH"
));
```

Một preflight cho `PATCH /api/items/42` gửi **HTTP OPTIONS**, nhưng `Access-Control-Request-Method: PATCH` để hỏi liệu PATCH **thật sự** có được phép. Vì vậy chỉ cần `PATCH` trong allowedMethods cho câu hỏi đó; không bắt buộc `OPTIONS` trong danh sách chỉ để cho phép preflight.

Nếu application chỉ có GET, đừng mở thêm POST/PUT/DELETE vô điều kiện. Nếu có nhiều routes với mức truy cập khác nhau, có thể đăng ký **CorsConfiguration khác nhau theo path** hoặc sắp xếp security rules cho từng method. CORS method allowlist chỉ là browser restriction, không thay authorization.

### 3.4 allowedHeaders: tên header **client muốn gửi**

```java
config.setAllowedHeaders(List.of(
    "Authorization",
    "Content-Type",
    "X-Request-Id",
    "X-CSRF-TOKEN"
));
```

Một preflight có thể chứa:

```http
OPTIONS /api/items HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,x-request-id
```

Browser đang hỏi: frontend từ origin này được gửi **POST** cùng các **request headers** trên không? Server chỉ cho phép khi origin, method và headers thỏa chính sách. Tên header HTTP không phân biệt hoa/thường về mặt protocol, vì vậy test nên so sánh case-insensitive.

Các lưu ý:

- `Authorization` là request header của Basic/Bearer; **nên liệt kê tường minh** nếu frontend cross-origin cần gửi nó.
- `Content-Type: application/json` thường khiến browser preflight vì không thuộc các giá trị Content-Type CORS-safelisted.
- `X-CSRF-TOKEN` cần cho flow browser có CSRF token theo thiết kế; cho phép nó qua CORS **không làm CSRF protection tự động hợp lệ**.
- `X-Request-Id` là header dành cho tracing nếu được thiết kế và giới hạn đầu vào; tuyệt đối không tin nó như chứng cứ authentication.
- Không liệt kê `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` như một cách “bật” preflight. Đây là các browser/protocol headers của request CORS, không phải custom application headers cần client tự gửi.

### 3.5 exposedHeaders: tên header **JS muốn đọc từ response**

```java
config.setExposedHeaders(List.of(
    "X-Request-Id", "ETag", "Location"
));
```

Ví dụ sau khi gọi API hợp lệ, frontend cần:

- Đọc `X-Request-Id` để đối chiếu một yêu cầu hỗ trợ.
- Đọc `ETag` để hỗ trợ cache/conditional requests.
- Đọc `Location` sau khi tạo resource, nếu endpoint POST trả 201 với Location.

Server có thể gửi `ETag` và `X-Request-Id` bình thường nhưng **JavaScript cross-origin không đọc được chúng** nếu chúng không nằm trong danh sách CORS-safelisted response headers hoặc không được `Access-Control-Expose-Headers` liệt kê. `ETag` và `Location` là ví dụ hữu ích của headers cần expose tường minh.

Các response headers được browser cho phép đọc mặc định theo CORS gồm nhóm safelisted như `Cache-Control`, `Content-Language`, `Content-Length`, `Content-Type`, `Expires`, `Last-Modified` và `Pragma`. Không cần thêm tất cả nhóm đó vào exposedHeaders, nhưng có thể khai báo khi muốn nhất quán. `Set-Cookie` là **forbidden response-header name**: thêm nó vào exposedHeaders **không làm `fetch().headers.get("set-cookie")` đọc được cookie**. Cookie được browser quản lý riêng và chịu quy tắc `SameSite`, `Secure`, third-party cookie restrictions.

### 3.6 maxAge: cache kết quả preflight

```java
config.setMaxAge(1800L); // 1800 giây = 30 phút
```

Browser có thể cache kết quả preflight, nên không cần OPTIONS lặp lại cho cùng loại request mỗi lần. `Access-Control-Max-Age` là **gợi ý**; browser có thể có giới hạn riêng và policy cache khác. Khi thay đổi CORS allowlist, client có thể còn giữ preflight cache tới khi hết hạn. Cân bằng hiệu suất với khả năng thu hồi chính sách.

## 4. Preflight và actual request khác nhau

### 4.1 Luồng có preflight

Một JavaScript client gửi JSON POST và custom headers đến origin API khác:

```text
Frontend https://app.example.com
       |
       | fetch("https://api.example.com/api/items",
       |       { method:"POST", headers:{
       |            "Content-Type":"application/json",
       |            "Authorization":"Bearer ...",
       |            "X-Request-Id":"..."
       |       }})
       |
       v
Browser gửi OPTIONS preflight:
       Origin: https://app.example.com
       Access-Control-Request-Method: POST
       Access-Control-Request-Headers:
           authorization,content-type,x-request-id
       |
       v
CORS processor kiểm origin + method + headers
       |
       +-- được phép -> trả 2xx + Access-Control-Allow-*
       |                   browser mới có thể gửi actual POST
       |
       +-- không được -> browser chặn actual request
       |
       v
Actual POST có credential (nếu client gửi)
       |
       v
Spring Security authentication/authorization/CSRF
       |
       +-- 2xx/4xx/5xx theo nghiệp vụ
       |
       v
Browser kiểm Access-Control-Allow-Origin và credential policy
       |
       v
JS được đọc response/body và những exposedHeaders cho phép
```

**Preflight không phải đăng nhập.** Nó chỉ xác nhận chính sách CORS cho yêu cầu sắp gửi. Preflight thường **không mang session cookie/Basic credentials**, vì vậy phải được xử lý **trước khi Spring Security từ chối anonymous request**, thay vì yêu cầu `ROLE_USER` ở endpoint OPTIONS.

### 4.2 Request không cần preflight

Một GET cross-origin với các headers và Content-Type thỏa điều kiện *CORS-safelisted* có thể không cần preflight; browser vẫn gửi `Origin` và kiểm header `Access-Control-Allow-Origin` trong **actual response**. Việc không có OPTIONS không có nghĩa request là same-origin hay CORS bị tắt.

Một GET có `Authorization` header do frontend đặt thường cần preflight vì `Authorization` không phải CORS-safelisted request header. Một POST gửi `Content-Type: application/json` cũng thường cần preflight.

### 4.3 Bảng phân biệt HTTP header

| Header | Nằm ở request/response | Dùng trong giai đoạn nào |
| --- | --- | --- |
| `Origin` | Request browser → API | Nhận diện origin gọi cross-origin |
| `Access-Control-Request-Method` | Preflight OPTIONS request | Browser hỏi về method của **actual request** |
| `Access-Control-Request-Headers` | Preflight OPTIONS request | Browser hỏi về request headers sẽ gửi |
| `Access-Control-Allow-Origin` | Response preflight/actual | Server chấp nhận origin |
| `Access-Control-Allow-Methods` | Preflight response | Methods cross-origin được phép |
| `Access-Control-Allow-Headers` | Preflight response | Request header names được phép |
| `Access-Control-Expose-Headers` | Actual response | Response header names JS được phép đọc |
| `Access-Control-Allow-Credentials` | Response khi bật credentials | Browser có thể chia sẻ response của credentialed request với JS |
| `Access-Control-Max-Age` | Preflight response | Thời gian browser có thể cache kết quả |
| `Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers` | Response/cache hint | Giúp cache phân biệt những biến thể CORS phù hợp |

**Không nhầm:** `Access-Control-Allow-Headers` không phải danh sách response headers cho JS. `Access-Control-Expose-Headers` không cho phép một request header. Nếu API gửi đúng `X-Request-Id` nhưng frontend không đọc được, thường cần **exposedHeaders**, không phải allowedHeaders.

## 5. Lý do Spring Security reactive cần CORS xử lý sớm

CORS preflight thường không mang thông tin xác thực của user. Nếu WebFlux Security yêu cầu authentication trước khi preflight được xử lý, browser có thể nhận **401** thay vì một CORS preflight response hợp lệ; actual request sẽ không được gửi.

Spring Security WebFlux có tích hợp CORS thông qua `ServerHttpSecurity.cors(...)`, sử dụng `CorsConfigurationSource` và xử lý bằng `CorsWebFilter`. Trong Spring Security **6.1+**, phong cách rõ ràng là:

```java
.cors(Customizer.withDefaults())
```

Khi trong application context có **`CorsConfigurationSource` bean** tương thích, Spring Security có thể sử dụng nó để tạo CORS support trong chain. Nếu bạn dùng `cors(...configurationSource(source))` thì cung cấp source tường minh, không phụ thuộc bean discovery.

Tài liệu Spring Security nêu nguyên tắc: **CORS phải được xử lý trước authentication**, vì preflight không có cookie/identity thông thường. Đừng giải quyết lỗi này bằng cách **`anyExchange().permitAll()`**, bởi như vậy mở toàn bộ API.

### 5.1 Ba cách tích hợp: không phối hợp tùy tiện

**Cách A — đề xuất trong bài:** một `UrlBasedCorsConfigurationSource` bean và `http.cors(Customizer.withDefaults())`. Phù hợp khi muốn một nơi quản lý CORS cho security chain.

**Cách B — đăng ký `CorsWebFilter` bean** với source. Đây là cơ chế Spring WebFlux chuẩn và hữu ích khi cần CORS cho cả annotated/functional endpoints, đặc biệt cần xử lý rất sớm.

**Cách C — `WebFluxConfigurer.addCorsMappings(...)`** hoặc `@CrossOrigin` tại controller/handler mapping. Phù hợp với CORS cấp WebFlux HandlerMapping, nhưng phải đảm bảo preflight **không bị security chặn trước khi đến HandlerMapping**.

**Không nên** đăng ký A, B, C chồng lên nhau mà không có thiết kế; có thể tạo source policy khác nhau, trùng header, khó biết layer nào cho phép/chặn. Hãy chọn một nguồn cấu hình trung tâm phù hợp với security pipeline, có integration tests cho OPTIONS.

## 6. Project Java 17+ hoàn chỉnh: khai báo đúng bốn nhóm CORS chính

Ví dụ này có:

- Frontend **development** `http://localhost:5173` và frontend production `https://app.example.com` được phép cross-origin.
- API `/api/items` có GET và POST. GET cần role `READER`; POST cần role `EDITOR`.
- CORS cho phép GET, POST, PATCH trên `/api/**`, và chỉ bốn request headers cần dùng.
- JavaScript có thể đọc ba response headers: `X-Request-Id`, `ETag`, `Location`.
- HTTP Basic dùng **credential demo** để minh họa authentication/authorization. Trong sản phẩm thực, cân nhắc OAuth2/OIDC hoặc BFF/session đáng tin cậy.
- CSRF **không bị tắt**. Bởi vậy demo test POST chưa có CSRF token sẽ nhận 403 dù preflight POST được phép. Đây là minh chứng CORS không thay thế security.

### 6.1 Dependencies và project layout

Tạo Spring Boot **3.x**, Java **17+**, Gradle Groovy, chọn Spring Reactive Web, Spring Security, Spring Boot Test.

Đây là phần dependencies trong `build.gradle` của một project đã được Spring Initializr tạo với Spring Boot plugin và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Project:

```text
src/main/java/com/example/corsreactive/
  CorsReactiveApplication.java
  SecurityCorsConfig.java
  ItemController.java
src/test/java/com/example/corsreactive/
  CorsIntegrationTest.java
```

Dùng **WebFlux server**; nếu cùng thêm `spring-boot-starter-web` thì Spring Boot thường chọn MVC/Servlet mặc định. `ServerHttpSecurity` / `SecurityWebFilterChain` là cấu hình reactive server, không phải Servlet `HttpSecurity` / `SecurityFilterChain`.

### 6.2 CorsReactiveApplication.java

`src/main/java/com/example/corsreactive/CorsReactiveApplication.java`:

```java
package com.example.corsreactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsReactiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsReactiveApplication.class, args);
    }
}
```

### 6.3 SecurityCorsConfig.java

`src/main/java/com/example/corsreactive/SecurityCorsConfig.java`:

```java
package com.example.corsreactive;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityCorsConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        var config = new CorsConfiguration();

        // 1. Chính xác scheme + host + port, KHÔNG có path.
        config.setAllowedOrigins(List.of(
            "http://localhost:5173",
            "https://app.example.com"
        ));

        // 2. Methods THỰC TẾ; OPTIONS preflight được xử lý riêng.
        config.setAllowedMethods(List.of(
            "GET", "POST", "PATCH"
        ));

        // 3. Các request headers frontend cần gửi.
        config.setAllowedHeaders(List.of(
            "Authorization",
            "Content-Type",
            "X-Request-Id",
            "X-CSRF-TOKEN"
        ));

        // 4. Các response headers frontend được phép đọc.
        config.setExposedHeaders(List.of(
            "X-Request-Id", "ETag", "Location"
        ));

        // Demo không dùng cookie cross-origin: không mở credentials.
        config.setAllowCredentials(false);
        config.setMaxAge(1800L);

        var source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            // Dùng source bean ở trên trong Spring Security CORS.
            .cors(Customizer.withDefaults())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/items")
                    .hasRole("READER")
                .pathMatchers(HttpMethod.POST, "/api/items")
                    .hasRole("EDITOR")
                .anyExchange().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();

        UserDetails editor = User.withUsername("editor")
            .password(encoder.encode("editor-demo-password"))
            .roles("READER", "EDITOR")
            .build();

        return new MapReactiveUserDetailsService(reader, editor);
    }
}
```

**Cách đọc từng phần:**

1. `CorsConfiguration` là cấu hình CORS; các danh sách được đặt **tường minh**, không gọi `applyPermitDefaultValues()` vì method đó có thể tạo các giá trị wildcard quá rộng cho bài toán API bảo vệ bằng credential.
2. `UrlBasedCorsConfigurationSource` là class **reactive** ở package `org.springframework.web.cors.reactive`. Đăng ký `/api/**` để chỉ áp dụng chính sách này cho API route dự kiến.
3. Bean trả `UrlBasedCorsConfigurationSource` để Spring Security WebFlux nhận diện `CorsConfigurationSource` tương thích. `.cors(Customizer.withDefaults())` tích hợp xử lý CORS trong security chain.
4. CORS allowlist methods gồm `PATCH` dù controller demo chưa cung cấp PATCH handler. Điều đó **không tạo ra PATCH route**, **không cấp quyền**, và `anyExchange().denyAll()` vẫn chặn PATCH. Ví dụ này minh họa rõ ranh giới giữa CORS browser policy và authorization server.
5. `setAllowCredentials(false)` là lựa chọn conservative khi không cần cookie/session cross-origin. Nếu browser có `fetch(..., credentials: "include")`, cấu hình này **không đủ** cho browser chia sẻ response; phải thiết kế chính sách credentialed riêng như mục 11.
6. `httpBasic(...)` chỉ là cách tạo user có credential trong test. Không đặt mật khẩu thật trong frontend JavaScript, không dùng Basic qua HTTP mạng thực. Với browser và OAuth2 Bearer, thay HTTP Basic bằng Resource Server được cấu hình/validate đầy đủ.
7. `anyExchange().denyAll()` áp dụng **authorization**, không thay cho CORS. GET/PATCH/POST bị security chặn theo principal, roles, method và CSRF ngay cả khi CORS cho phép origin.

### 6.4 ItemController.java: trả response headers để expose

`src/main/java/com/example/corsreactive/ItemController.java`:

```java
package com.example.corsreactive;

import java.net.URI;
import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ItemController {

    public record ItemView(String id, String name) {}
    public record CreateItem(String name) {}

    @GetMapping(
        value = "/api/items",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<List<ItemView>> listItems() {
        return ResponseEntity.ok()
            .header("X-Request-Id", "req-demo-001")
            .header(HttpHeaders.ETAG, "\"items-v1\"")
            .body(List.of(new ItemView("item-1", "Example")));
    }

    @PostMapping(
        value = "/api/items",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<ItemView>> create(
            @RequestBody Mono<CreateItem> request) {
        return request.map(body ->
            ResponseEntity
                .created(URI.create("/api/items/item-2"))
                .header("X-Request-Id", "req-demo-002")
                .body(new ItemView("item-2", body.name()))
        );
    }
}
```

Giải thích:

- `X-Request-Id` là header response do **ứng dụng** tạo cho mục đích demo. Việc `setExposedHeaders(List.of("X-Request-Id", ...))` cho phép browser JS đọc nó từ một response cross-origin hợp lệ.
- `ETag` là response header dùng cho caching/conditional requests; đã có trong exposedHeaders, frontend có thể đọc.
- `Location` được trả bởi `ResponseEntity.created(...)` sau POST thành công. Nó cũng được liệt kê trong exposedHeaders.
- `ItemView` và `CreateItem` là **nested Java records**, được khai báo trong `ItemController` và Jackson có thể serialize/deserialize khi dùng Spring Boot 3.x.
- CORS không tự làm POST thành công: role EDITOR và CSRF protection vẫn được kiểm tra ở Spring Security. Một POST thiếu CSRF token có thể bị 403 **trước khi controller chạy**.
- Mã chỉ trình bày HTTP/CORS, không phải database-backed CRUD, nên body POST trả một ID demo cố định. Trong dự án thật, cần validation, lưu trữ, IDs ngẫu nhiên/unique và quyền theo tenant.

## 7. Quan sát CORS bằng curl: preflight đúng và sai

Chạy ứng dụng từ Gradle project:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Mặc định, nếu không chỉnh `server.port`, backend thường ở `http://localhost:8080`. Dùng HTTP local với account giả để học; môi trường thực cần **HTTPS/TLS**.

### 7.1 Preflight được phép

```bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type,x-request-id"
```

Một response **dự kiến** theo CORS configuration:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,PATCH
Access-Control-Allow-Headers: authorization,content-type,x-request-id
Access-Control-Max-Age: 1800
Vary: Origin
```

Đây là **minh họa những header quan trọng**, không phải raw output chuẩn hóa byte-for-byte. Spring có thể ghi `Vary` thành nhiều field, khác thứ tự, hoặc thêm `Access-Control-Request-Method` và `Access-Control-Request-Headers`; CORS header values có thể thay đổi thứ tự/hoa thường tùy implementation. Kiểm tra sự hiện diện và ý nghĩa, không so sánh nguyên văn toàn bộ response.

**Quan sát:** Request OPTIONS không có `Authorization`, nhưng vẫn nhận CORS preflight response hợp lệ, vì CORS được xử lý trước khi đòi HTTP Basic login. Điều này **không cho phép** actual POST bỏ qua login.

### 7.2 Origin không thuộc allowlist

```bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: GET"
```

Spring `CorsWebFilter` dùng CORS processor mặc định sẽ **từ chối preflight không hợp lệ** (thường HTTP 403). Browser sẽ không gửi actual request tương ứng. Không bao giờ tự động phản chiếu giá trị `Origin` từ request thành `Access-Control-Allow-Origin` để “chữa” lỗi.

### 7.3 Method không được phép

```bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: DELETE"
```

`DELETE` không nằm trong allowedMethods, vì vậy preflight sẽ bị từ chối. Điều này khác với Spring Security `denyAll()` chặn actual DELETE; preflight có thể kết thúc ở CORS filter **trước** khi authorization.

### 7.4 Header không được phép

```bash
curl -i -X OPTIONS "http://localhost:8080/api/items" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: x-admin-bypass"
```

`X-Admin-Bypass` không thuộc allowedHeaders. Preflight không hợp lệ sẽ bị từ chối. Cho phép một request header qua CORS **không tự tin giá trị header đó**: ngay cả khi bạn thêm nó vào allowedHeaders, backend vẫn phải **không** dùng header không đáng tin để cấp quyền admin.

### 7.5 Actual GET với HTTP Basic

```bash
curl -i -u reader \
  -H "Origin: https://app.example.com" \
  "http://localhost:8080/api/items"
```

Nhập password demo `reader-demo-password` khi curl hỏi. Response kỳ vọng:

```text
HTTP 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: X-Request-Id, ETag, Location
X-Request-Id: req-demo-001
ETag: "items-v1"

[{"id":"item-1","name":"Example"}]
```

Đây là dạng **minh họa**, thứ tự/format headers và JSON do Spring/Jackson quyết định. `curl` **không thực thi CORS browser policy**; nó có thể hiển thị cả header không expose. Header `Access-Control-Expose-Headers` quan trọng vì **browser JavaScript** sẽ bị hạn chế khi đọc `ETag`, `Location`, `X-Request-Id` nếu không được expose.

Nếu bạn gọi actual GET **không có Basic credential**, response vẫn có thể mang `Access-Control-Allow-Origin` nhưng nhận **401 Unauthorized**: CORS pass không đồng nghĩa authentication pass.

## 8. Kiểm thử WebTestClient cho origin, method, allowedHeaders và exposedHeaders

CORS thường bị lỗi chỉ khi chạy browser; vì vậy hãy test rõ **preflight** và **actual response** ngay trong backend CI.

Tạo `src/test/java/com/example/corsreactive/CorsIntegrationTest.java`:

```java
package com.example.corsreactive;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class CorsIntegrationTest {

    private static final String GOOD_ORIGIN =
        "https://app.example.com";

    @Autowired
    WebTestClient client;

    @Test
    void preflightAllowsConfiguredOriginMethodAndHeaders() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "POST")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type,x-request-id")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS, value ->
                    assertThat(value).contains("POST"))
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS, value -> {
                    String lower = value.toLowerCase(Locale.ROOT);
                    assertThat(lower).contains(
                        "authorization", "content-type", "x-request-id");
                });
    }

    @Test
    void rejectsPreflightFromDisallowedOrigin() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, "https://evil.example")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void rejectsPreflightForDisallowedMethod() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "DELETE")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void rejectsPreflightWithDisallowedHeader() {
        client.options()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "x-admin-bypass")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void actualGetExposesConfiguredResponseHeaders() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .headers(headers -> headers.setBasicAuth(
                "reader", "reader-demo-password"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, GOOD_ORIGIN)
            .expectHeader().value(
                HttpHeaders.ACCESS_CONTROL_EXPOSE_HEADERS, value -> {
                    String lower = value.toLowerCase(Locale.ROOT);
                    assertThat(lower).contains(
                        "x-request-id", "etag", "location");
                })
            .expectHeader().valueEquals("X-Request-Id", "req-demo-001")
            .expectHeader().valueEquals(HttpHeaders.ETAG, "\"items-v1\"")
            .expectBody()
            .jsonPath("$[0].id").isEqualTo("item-1");
    }

    @Test
    void allowedCorsOriginDoesNotBypassAuthentication() {
        client.get()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void corsAllowsPostPreflightButCsrfStillProtectsActualPost() {
        client.post()
            .uri("/api/items")
            .header(HttpHeaders.ORIGIN, GOOD_ORIGIN)
            .headers(headers -> headers.setBasicAuth(
                "editor", "editor-demo-password"))
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"name\":\"Not created without CSRF\"}")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Giải thích test:**

1. `preflightAllowsConfiguredOriginMethodAndHeaders` mô phỏng browser `OPTIONS` **không có Basic credentials**, test đủ **origin, actual method và request headers**.
2. `rejectsPreflightFromDisallowedOrigin` xác minh không phản chiếu một origin tùy ý.
3. `rejectsPreflightForDisallowedMethod` kiểm `DELETE` không thuộc `allowedMethods`.
4. `rejectsPreflightWithDisallowedHeader` kiểm header ngoài allowlist không được phép.
5. `actualGetExposesConfiguredResponseHeaders` test **actual authenticated GET**, nơi `Access-Control-Expose-Headers` có ý nghĩa cho browser JavaScript.
6. `allowedCorsOriginDoesNotBypassAuthentication` xác minh dù CORS pass, security vẫn yêu cầu identity.
7. `corsAllowsPostPreflightButCsrfStillProtectsActualPost` cho thấy `Access-Control-Allow-Methods: POST` **không phải** quyền ghi dữ liệu; browser/session CSRF policy vẫn áp dụng. Ví dụ giữ CSRF protection mặc định, không gửi CSRF token nên POST bị 403.

Chạy:

```bash
./gradlew test --tests '*CorsIntegrationTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*CorsIntegrationTest'
```

Đây là **các assertion kỳ vọng từ cấu hình minh họa**, không phải stdout của một lần build đã chạy trong môi trường soạn bài. Trong ứng dụng có nhiều security chains, reverse proxies hoặc CORS layer khác, cần kiểm tra kết quả thực tế và cập nhật tests tương ứng.

### 8.1 Khi nào phải test bằng browser thật?

`WebTestClient` kiểm response status/headers và security filters rất tốt nhưng **không phải trình duyệt**: nó không thực thi same-origin policy, cookies restrictions hay JavaScript `fetch` access-control rules. Cần thêm browser integration/e2e test khi:

- Frontend dùng `credentials:"include"` hoặc session cookies.
- Có `SameSite=None; Secure`, third-party cookie policies hoặc browser extensions.
- Backend đặt phía sau CDN/reverse proxy có thể cache/vary sai.
- CORS policy thay đổi theo environment/tenant/origin.
- Có authentication redirect/OIDC login hoặc một API bị gateway xử lý preflight trước backend.

## 9. Những response headers nào frontend có thể đọc?

Ví dụ browser request cross-origin trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: X-Request-Id, ETag, Location
Content-Type: application/json
X-Request-Id: req-demo-001
ETag: "items-v1"
```

Nếu CORS pass, frontend JavaScript có thể:

```javascript
const response = await fetch("https://api.example.com/api/items", {
  method: "GET",
  headers: {
    Authorization: "Bearer " + accessToken,
    "X-Request-Id": requestId
  }
});

if (!response.ok) {
  throw new Error("HTTP status " + response.status);
}

const traceId = response.headers.get("X-Request-Id");
const etag = response.headers.get("ETag");
const items = await response.json();
console.log({ traceId, etag, items });
```

**Snippet này minh họa frontend sử dụng Bearer header trong một hệ thống thật**, **không chạy đúng ngay với backend demo chỉ có HTTP Basic**. Để chạy Bearer thực, backend phải có Spring Security OAuth2 Resource Server, decoder/issuer/audience/scope validation tương ứng; thay demo Basic không chỉ là đổi string header. Đừng hardcode access token, password hay API key trong mã frontend được publish.

`response.headers.get("Location")` chỉ có giá trị khi **actual response có header Location**, ví dụ POST tạo tài nguyên thành công. Đặt `Location` trong exposedHeaders không tự tạo response header đó.

**Set-Cookie không đọc được:** `Access-Control-Expose-Headers: Set-Cookie` **không** giúp JavaScript truy cập `Set-Cookie`. Browser quản lý cookie; với cookie phiên cần xem `HttpOnly`, `Secure`, `SameSite`, credentials mode và chính sách trình duyệt.

## 10. Những vấn đề khi bật allowCredentials(true)

Bài mẫu sử dụng `setAllowCredentials(false)` vì chỉ cần minh họa request có Authorization header do client gửi và không cần cookie session cross-origin. Một ứng dụng BFF/browser dùng session cookie có thể cần `true`.

### 10.1 Cấu hình với cookie session cross-origin

Ví dụ **thay thế phần khởi tạo CorsConfiguration**, không thêm cùng lúc một policy thứ hai:

```java
CorsConfiguration config = new CorsConfiguration();

config.setAllowedOrigins(List.of(
    "https://app.example.com"
));
config.setAllowedMethods(List.of(
    "GET", "POST", "PATCH"
));
config.setAllowedHeaders(List.of(
    "Content-Type", "X-CSRF-TOKEN", "X-Request-Id"
));
config.setExposedHeaders(List.of(
    "X-Request-Id", "ETag", "Location"
));
config.setAllowCredentials(true);
config.setMaxAge(600L);
```

Phần này là **snippet**, đặt vào `corsConfigurationSource()` khi app thật sự cần cookie cross-origin. Không tự động chép vào project production; còn cần quản lý session, CSRF, origin allowlist và cookie policies.

Trong response CORS khi browser request có credentials, server thường cần:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Browser JavaScript sẽ thường dùng `fetch(url, { credentials: "include", ... })` khi cần gửi/nhận cookie ở cross-origin request. **CORS không vô hiệu các quy tắc cookie**: SameSite, Secure, third-party cookie restrictions, domain/path và session expiry vẫn áp dụng. Đối với cookie cross-site, cần đánh giá `SameSite=None; Secure` và các hạn chế chính sách trình duyệt.

### 10.2 Vì sao không dùng allowedOrigins("*") với credentials?

Cấu hình sau **không hợp lệ** cho credentialed CORS:

```java
config.setAllowedOrigins(List.of("*"));
config.setAllowCredentials(true);
```

Spring Framework có validation để ngăn tổ hợp `allowedOrigins("*")` và `allowCredentials(true)`, vì response `Access-Control-Allow-Origin: *` không tương thích với credentialed browser requests. Nếu cần origin động, `allowedOriginPatterns` có thể phản chiếu origin đã match, nhưng pattern quá rộng với cookies vẫn nguy hiểm. **Tốt nhất là exact-origin allowlist cho frontend được quản trị.**

### 10.3 CORS không phải CSRF protection

Ngay cả khi chỉ cho phép `https://app.example.com`, một trang khác có thể cố gây request tới backend qua các cơ chế mà browser cho phép gửi. CORS chủ yếu hạn chế JavaScript đọc response cross-origin; nó **không ngăn mọi dạng cross-site request có side effect**.

Với browser session/cookies hoặc HTTP Basic được browser tự gửi, cần threat model cho **CSRF**, `SameSite`, session fixation, XSS, content security policy và việc cấp quyền theo user. Không tắt `ServerHttpSecurity.csrf(...)` trên toàn app chỉ vì đã khai báo CORS.

Nếu API dùng Bearer token được frontend thêm thủ công trong header và không dùng ambient browser credentials, CSRF risk có thể khác, nhưng CORS vẫn không phải authentication. Chỉ điều chỉnh CSRF sau khi đánh giá loại client và đặc điểm credential cụ thể.

### 10.4 Authorization header và allowCredentials không đồng nhất hoàn toàn

`Authorization` là **request header name**, phải được phép qua `allowedHeaders` nếu browser định gửi nó ở cross-origin request. `allowCredentials` là flag về **credentialed CORS requests theo browser's credentials mode**, đặc biệt liên quan cookies/HTTP authentication do browser quản lý. Một request có script-added Authorization header không tự suy ra rằng config bắt buộc phải là `allowCredentials(true)` trong mọi tình huống; phải kiểm tra `fetch` credentials mode và flow thực.

Để tránh nhầm trong sản phẩm, ghi rõ giao thức auth (Bearer từ JS, cookie session hay HTTP Basic browser-managed) và kiểm thử browser thực.

## 11. Thêm @CrossOrigin hoặc WebFluxConfigurer khi nào?

Có ứng dụng chỉ cần mở một vài handlers:

```java
@CrossOrigin(
    origins = "https://app.example.com",
    methods = { RequestMethod.GET },
    allowedHeaders = { "Authorization", "X-Request-Id" },
    exposedHeaders = { "ETag", "X-Request-Id" }
)
@GetMapping("/api/items")
public ResponseEntity<?> listItems() {
    // ...
}
```

**Đây chỉ là snippet minh họa annotation**, chưa phải Java class độc lập. Trong Spring WebFlux, `@CrossOrigin` được `HandlerMapping` xử lý khi request tới annotated handler. Nếu Spring Security chặn preflight **trước khi routing**, annotation ở controller không nhất thiết cứu được preflight. Với functional `RouterFunction` cũng cần kiểm tra cách áp dụng CORS.

Một cách khác là `WebFluxConfigurer`:

```java
@Configuration
public class WebCorsConfig implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "PATCH")
            .allowedHeaders(
                "Authorization", "Content-Type", "X-Request-Id")
            .exposedHeaders(
                "ETag", "X-Request-Id", "Location")
            .maxAge(1800);
    }
}
```

Đây là **class snippet**, cần imports `Configuration`, `WebFluxConfigurer`, `CorsRegistry`. Trong Spring Boot có thể chỉ implement `WebFluxConfigurer`, không nhất thiết thêm `@EnableWebFlux`. CORS tại `HandlerMapping` có thể phối hợp với `@CrossOrigin` theo quy tắc merge, nhưng nếu Spring Security và WebFlux có **hai policy khác nhau**, rất dễ khó hiểu response. Trong ứng dụng có Spring Security bảo vệ API, ưu tiên một policy tập trung và test HTTP preflight.

### 11.1 CorsWebFilter bean thay thế

Nếu muốn dùng cách WebFlux WebFilter thay vì để `ServerHttpSecurity` tạo/integrate filter từ source, bạn có thể khai báo:

```java
@Bean
CorsWebFilter corsWebFilter() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of(
        "https://app.example.com"
    ));
    config.setAllowedMethods(List.of("GET", "POST"));
    config.setAllowedHeaders(List.of(
        "Authorization", "Content-Type"
    ));
    config.setExposedHeaders(List.of("X-Request-Id"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);

    return new CorsWebFilter(source);
}
```

**Snippet thay thế** cần import `org.springframework.web.cors.reactive.CorsWebFilter`, `UrlBasedCorsConfigurationSource`, `CorsConfiguration` và `List`. Không đăng ký bean `CorsWebFilter` này đồng thời với một Security CORS filter khác chỉ vì muốn “chắc chắn chạy”; chọn một cơ chế có chủ đích. Tài liệu Spring Security khuyến nghị CORS processing sớm để OPTIONS preflight không bị authentication chặn.

## 12. Quy tắc an toàn khi có nhiều SecurityWebFilterChain

Nếu bạn tách security chains theo path (ví dụ `/api/**` Bearer token và `/web/**` form login), CORS cũng phải được triển khai đúng với các matcher/chains đó.

- `securityMatcher` chọn chain của request theo thứ tự `@Order`; `authorizeExchange` chọn rule bên trong chain.
- Nếu CORS source chỉ đăng ký `/api/**`, preflight tới `/web/**` không được tự cho phép bởi policy đó.
- Nếu một chain khác vô tình match trước CORS-enabled chain, preflight có thể bị chặn hoặc dùng policy khác.
- Nên có một **CORS policy nhất quán** với trust boundary của API; nếu nhiều origins/paths, đặt mapping rõ và test trên **từng path thực**.
- Không “sửa” preflight bằng một catch-all chain `anyExchange().permitAll()`; điều đó có thể mở endpoints mà không còn authentication.
- Nếu gateway/nginx/CDN cũng xử lý CORS, quyết định rõ **tầng duy nhất chịu trách nhiệm**; kiểm tra không trả hai `Access-Control-Allow-Origin` trái nhau.

### 12.1 OPTIONS có cần permitAll() không?

Nếu CORS được xử lý đúng ở `CorsWebFilter` trước Spring Security authentication, một preflight hợp lệ sẽ được trả lời **mà không cần** một authorization rule chung kiểu `pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()`.

Một số kiến trúc có yêu cầu xử lý OPTIONS riêng và có thể khai báo policy cụ thể, nhưng **không** dùng permitAll mọi OPTIONS như phương án mặc định nếu chưa xác định CORS filter order, request matching, gateway và security consequences. Preflight chỉ là một loại request OPTIONS có **Origin** và **Access-Control-Request-Method** hợp lệ; **mọi OPTIONS** không đồng nghĩa preflight.

## 13. Vary, caching và CDN/reverse proxy

Khi API trả `Access-Control-Allow-Origin` khác nhau tùy request `Origin`, shared cache phải phân biệt response phù hợp. Các CORS processors thường dùng header:

```http
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Hoặc một header `Vary` gộp nhiều giá trị, tùy server. **Không hardcode test yêu cầu cùng một format byte**.

Nếu CDN cache một response chứa `Access-Control-Allow-Origin: https://app.example.com` rồi phát lại cho origin khác, browser có thể chặn sai hoặc gặp rủi ro nếu policy/cache key không phù hợp. Với API authenticated, kiểm tra `Cache-Control` của nội dung user-specific; đừng cache nhầm body nhạy cảm chỉ theo URL và origin.

`Access-Control-Max-Age` là preflight cache của browser, **không thay thế** HTTP caching policy cho actual response. `ETag` giúp quản lý conditional request, nhưng muốn JS đọc ETag cross-origin thì ETag phải được expose như phần 3.5.

## 14. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| Browser báo CORS, curl GET vẫn 200 | Curl không thực thi same-origin policy | Kiểm tra OPTIONS/actual Origin, ACAO và browser devtools |
| OPTIONS preflight trả 401 | Security authentication chạy trước CORS | Dùng Spring Security CORS integration hoặc `CorsWebFilter` đúng thứ tự |
| Preflight trả 403 do origin | Scheme/host/port không nằm trong allowlist | So sánh exact `Origin`, port, protocol, env config |
| Preflight 403 khi method PATCH | `allowedMethods` thiếu PATCH | Khai báo actual method tối thiểu cần dùng |
| Preflight 403 khi gửi Authorization | `allowedHeaders` thiếu Authorization | Bổ sung đúng request header name |
| Actual API có ETag nhưng JS không đọc được | `exposedHeaders` thiếu ETag | Thêm ETag vào `setExposedHeaders` |
| JS không đọc `Location` sau POST 201 | `Location` không exposed hoặc không được trả | Expose Location và xác nhận response thật có header |
| Frontend đặt `credentials: "include"` nhưng bị CORS block | ACAC thiếu/false hoặc ACAO là wildcard | Cân nhắc `allowCredentials(true)` với exact origins và cookie policy |
| Browser vẫn không gửi cookie sau khi CORS pass | `SameSite`/`Secure`/third-party cookie policy | Kiểm tra Set-Cookie, site context và browser restrictions |
| POST preflight pass nhưng POST nhận 403 | Spring Security authorization/CSRF chặn actual request | Test credential, role, CSRF token; CORS chỉ cho phép browser gửi |
| Chỉ một route CORS được phép | Source chỉ đăng ký một path hoặc chain mismatch | Kiểm tra `registerCorsConfiguration` và `securityMatcher` |
| Duplicate ACAO hoặc xung đột headers | Gateway và backend cùng thiết lập CORS | Chọn một nơi chịu trách nhiệm, tránh double filter |
| allowedOrigins `"*"` + credentials true lỗi | Không hợp lệ theo Spring/CORS | Dùng exact-origin list hoặc controlled patterns |
| Thêm Set-Cookie vào exposedHeaders vẫn không đọc được | Header bị browser cấm JavaScript đọc | Dùng cookie handling của browser, không expose secret |
| `Origin: null` bị chặn | Sandbox/file/opaque origin không nằm trong allowlist | Xem threat model; đừng cho phép null tùy tiện |
| Preflight đã cache dù đổi policy | `maxAge` và browser cache chưa hết | Đánh giá maxAge khi rollout thay đổi |
| Frontend đọc header khác hoa/thường bị lỗi | Header names case-insensitive, code/test case-sensitive | Kiểm tra tên chuẩn; WebTestClient compare không phân biệt case |
| Resource server trả 401 sau CORS success | Bearer token sai/hết hạn hoặc thiếu | Kiểm tra auth riêng, không mở CORS cho mọi origin |
| Server trả 200 nhưng JS báo CORS | ACAO/ACAC/Vary hoặc preflight không phù hợp | Dùng browser network pane để xem preflight và actual response |

**Thứ tự debug hiệu quả:** Xác định URL, Origin, HTTP method, request headers → kiểm OPTIONS nếu có → kiểm `Access-Control-Allow-*` của response → kiểm Spring Security 401/403/CSRF riêng → kiểm `Access-Control-Expose-Headers` trên actual response → kiểm cookie/proxy/CDN. Không bật `allowedOrigins("*")`/`allowedHeaders("*")` như một phản xạ khi chưa biết mismatch.

## 15. Những lỗi bảo mật nên tránh

1. **Phản chiếu Origin mù quáng:** đọc `request.getHeaders().getOrigin()` và gắn vào ACAO không cần validation. Điều này biến allowlist thành cho phép bất kỳ website nào.
2. **Dùng `allowedOrigins("*")` trong API có cookies/credentialed responses:** không tương thích với `allowCredentials(true)` và có thể gây lộ thông tin qua website không tin cậy.
3. **Dùng `allowedOriginPatterns("https://*.example.com")` khi mọi subdomain không được quản trị như nhau:** subdomain takeover hoặc trang tenant có thể được phép đọc dữ liệu.
4. **Ghi `allowedMethods("*")`/`allowedHeaders("*")` để chữa mọi lỗi:** mở rộng bề mặt CORS không cần thiết, khó audit. Chỉ mở những gì frontend thật sự dùng.
5. **Coi CORS như authentication:** kẻ tấn công vẫn gọi API qua curl/server-to-server; bảo vệ quyền bằng Spring Security và data-level authorization.
6. **Coi CORS như CSRF:** browser có thể gửi cross-site requests theo nhiều cơ chế; đánh giá cookie/session/CSRF riêng.
7. **Permit-all mọi request trong security chain vì OPTIONS bị 401:** tạo bypass; sửa CORS processing order.
8. **Cho phép JS đọc header không cần thiết:** chỉ expose response header có nhu cầu rõ; không cố expose `Set-Cookie` hoặc token nhạy cảm.
9. **Nới local origin trong production không có kế hoạch:** `http://localhost:5173` chỉ nên nằm ở dev config nếu có thể tách.
10. **Quên scheme/port:** `http` khác `https` và 5173 khác 3000; không coi path là một phần origin.
11. **Cấu hình hai lớp CORS lệch nhau:** Gateway, Spring Security và `@CrossOrigin` có thể tạo policy không nhất quán.
12. **Thử CORS chỉ bằng server unit test:** browser còn có credentials mode, cookie policies và preflight caching.
13. **Không kiểm danh sách exposed headers:** API hoạt động, network pane thấy `ETag`, nhưng frontend `response.headers.get("ETag")` trả null.
14. **Nhầm `Access-Control-Allow-Headers` với `Access-Control-Expose-Headers`:** khiến preflight pass nhưng frontend vẫn không đọc được response metadata.
15. **Cache response của người dùng sai cách:** CORS pass không làm personalized response an toàn để cache chung; phải xem authorization, Cache-Control và CDN.
16. **Cho phép Origin: null vô điều kiện:** opaque origins như sandbox/file có thể có đặc tính khó tin cậy hơn exact web origins.
17. **Dùng header X-Request-Id, X-Tenant hoặc Origin làm bằng chứng identity:** các request headers có thể do client gửi; không cấp quyền dựa trên chúng mà thiếu xác minh.
18. **Quên fail closed khi sai CORS:** nếu browser chặn, sửa allowlist/method/header đúng; không thay mọi rule thành permitAll.

## 16. Bài tập mở rộng

### Bài A — Thêm header `X-Correlation-Id`

Frontend cần gửi `X-Correlation-Id` để theo dấu request. Hãy bổ sung vào `setAllowedHeaders(...)`, rồi gửi preflight có `Access-Control-Request-Headers: x-correlation-id`. Đừng chỉ thêm vào `exposedHeaders` vì đây là **request header**. Nếu backend muốn **trả** X-Correlation-Id để JS đọc, lúc ấy thêm nó **cả vào exposedHeaders** và viết response header thực.

### Bài B — Hiển thị ETag

Sau GET, frontend cần đọc `ETag` để dùng `If-None-Match` ở request sau. ETag thuộc **response exposed headers**, còn `If-None-Match` là **request header** có thể phát sinh preflight và cần kiểm tra `allowedHeaders` tùy request flow. Hãy thêm `If-None-Match` khi frontend thực tế gửi, viết test cho preflight, và test caching/conditional response nếu server hỗ trợ.

### Bài C — Tách dev và production origins

Ở dev chỉ cho `http://localhost:5173`. Production chỉ cho `https://app.example.com`. Thực hiện bằng cấu hình có kiểm soát theo profile/environment (ví dụ `@ConfigurationProperties` hoặc property list), kiểm tra khi triển khai. Không cho client chọn origins qua input hoặc một HTTP header tự khai.

### Bài D — Thêm PATCH

CORS đã cho phép PATCH trong ví dụ nhưng server chưa có PATCH route hoặc authority. Hãy viết handler `PATCH /api/items/{id}`, Spring Security rule yêu cầu role EDITOR/scope write, CSRF policy đúng và test cả preflight lẫn actual PATCH. **CORS allowed method không làm handler tự xuất hiện hoặc cấp quyền.**

### Bài E — Browser credentialed session

Đổi demo sang form login/session cookies có HTTPS, bật `allowCredentials(true)` với **một exact origin**, cấu hình CSRF và cookie `SameSite`/`Secure`/`HttpOnly`. Kiểm thử browser `fetch(..., credentials:"include")` có/không token CSRF. Không chép password demo hoặc Bearer token vào query string.

### Bài F — Nhiều tenant

Nếu mỗi tenant có origin riêng, đừng đặt wildcard dễ dãi. Dùng trusted tenant registry được kiểm soát, xác minh hostname, giới hạn origins và xử lý cache `Vary: Origin`. Một tenant origin không nên tự động có quyền đọc dữ liệu tenant khác; authentication/tenant authorization phải kiểm tra độc lập.

## 17. Câu hỏi kiểm tra

**Câu 1.** `allowedHeaders` và `exposedHeaders` khác nhau ở đâu?

**Trả lời:** `allowedHeaders` quyết định **request header names client được gửi** trong cross-origin request; `exposedHeaders` quyết định **response header names browser JavaScript được đọc**. CORS không tự thêm những headers ứng dụng chưa tạo.

**Câu 2.** Một browser gửi OPTIONS preflight cho `POST /api/items`. Phải thêm `"OPTIONS"` vào `allowedMethods` mới thành công?

**Trả lời:** **Không bắt buộc.** `Access-Control-Request-Method: POST` hỏi về method thực tế là POST; CORS processor nhận diện OPTIONS preflight riêng.

**Câu 3.** Header `Authorization` nằm trong danh sách nào?

**Trả lời:** `allowedHeaders` nếu frontend phải gửi header đó cross-origin. Không phải `exposedHeaders`, trừ khi có một lý do cực kỳ đặc biệt để frontend đọc response header Authorization (thường không nên thiết kế như vậy).

**Câu 4.** API trả `ETag`, network pane nhìn thấy nhưng `fetch().headers.get("ETag")` trả null?

**Trả lời:** Với response cross-origin, kiểm tra `Access-Control-Expose-Headers` có `ETag` hay chưa; đồng thời xác nhận CORS overall pass và response thật có ETag.

**Câu 5.** Vì sao `allowedOrigins("*")` không dùng với `allowCredentials(true)`?

**Trả lời:** Credentialed browser requests không được dùng wildcard ACAO; Spring Framework validation từ chối cấu hình này. Dùng exact allowlist hoặc patterns có kiểm soát.

**Câu 6.** CORS preflight 200 có đảm bảo POST actual 200?

**Trả lời:** Không. HTTP authentication, roles/scopes, CSRF, validation, handler mapping và lỗi nghiệp vụ vẫn quyết định actual POST.

**Câu 7.** `curl -i` đọc được API dù browser báo CORS. Server có bị lỗi authentication không?

**Trả lời:** Chưa thể kết luận. Curl không thực thi same-origin policy của browser; hãy mô phỏng preflight/Origin và xem CORS response headers. Authentication là lớp khác.

**Câu 8.** Khi dùng cookies cross-origin, có thể chỉ sửa `allowCredentials(true)` là xong?

**Trả lời:** Không. Cần exact origins, browser `credentials:"include"`, cookie `SameSite`/`Secure`, CSRF protection, HTTPS và authentication/session policy.

**Câu 9.** Dùng `@CrossOrigin` ở controller có luôn giải quyết OPTIONS 401 trước Spring Security?

**Trả lời:** Không bảo đảm, vì security WebFilters có thể chặn preflight trước khi `HandlerMapping` tới controller. Nên tích hợp CORS sớm trong chain.

**Câu 10.** `setAllowedOriginPatterns(List.of("https://*.example.com"))` có tự bảo vệ tenant data không?

**Trả lời:** Không. Nó chỉ match origins; vẫn phải xác minh user, tenant, role và tài nguyên. Đồng thời cần kiểm soát mọi hostname có thể match pattern.

## 18. Checklist triển khai production

- [ ] Đã xác định **exact origins** của frontend, không có trailing path, scheme/port đúng.
- [ ] Có chính sách tách dev/staging/prod, không vô tình đưa localhost/untrusted tenant vào production.
- [ ] `allowedMethods` chứa **chỉ actual methods** thật sự cần cho API.
- [ ] `allowedHeaders` liệt kê `Authorization`, `Content-Type`, CSRF/tracing headers khi frontend thật sự dùng.
- [ ] `exposedHeaders` liệt kê `ETag`, `Location`, `X-Request-Id` chỉ khi JavaScript cần đọc.
- [ ] Đã cân nhắc `allowCredentials` theo cookies/session/credentials mode; không dùng `allowedOrigins("*")` với true.
- [ ] `maxAge` có giá trị hợp lý, lưu ý cache preflight khi rollout thay đổi chính sách.
- [ ] Spring Security WebFlux có CORS integration hoạt động **trước authentication**.
- [ ] Không chồng chéo CORS WebFilter, HandlerMapping, Security và proxy headers khi chưa thiết kế.
- [ ] CORS preflight hợp lệ không bị 401; preflight không hợp lệ bị từ chối.
- [ ] Có test **origin tốt/xấu**, **method tốt/xấu**, **allowed header/xấu**, **actual exposed headers**.
- [ ] Có test rằng allowed origin vẫn cần authentication và authorization.
- [ ] Với browser sessions, CSRF và cookie policies được kiểm tra riêng; CORS không thay thế chúng.
- [ ] Có test e2e bằng browser khi cần `credentials:"include"` hoặc qua reverse proxy/CDN.
- [ ] HTTP personalized response có Cache-Control/Vary đúng; không cache nhầm dữ liệu giữa users/origins.
- [ ] Không ghi secret, API key, Bearer token hoặc Basic password vào logs và không đưa credentials vào URL.

## 19. Tổng kết

Để cấu hình CORS trong Spring Security WebFlux, hãy hiểu và khai báo **bốn nhóm độc lập**: `allowedOrigins` (ai được gọi từ browser), `allowedMethods` (HTTP methods thực tế), `allowedHeaders` (request headers browser được gửi) và `exposedHeaders` (response headers JavaScript được đọc). Với credentials, phải kiểm soát exact origins, cookies/CSRF và browser mode; `maxAge` hỗ trợ cache preflight chứ không cấp quyền truy cập.

**Quy tắc bảo mật quan trọng nhất:** **CORS được xử lý trước authentication cho preflight, nhưng CORS không thay authentication, authorization hoặc CSRF.** Preflight 200 không bảo đảm actual request 200. Giữ security rules, dùng allowlist nhỏ nhất cần thiết và kiểm thử cả response headers lẫn hành vi trình duyệt.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Reactive CORS integration](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — ServerHttpSecurity.cors API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Framework 6.2 — WebFlux CORS](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — CorsConfiguration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
- [Spring Framework — WebFlux CorsWebFilter API](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html)
- [Spring Framework — WebFlux WebFilter integration](https://docs.spring.io/spring-framework/reference/web/webflux/filters.html)
- [MDN — Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS)
- [Fetch Standard — CORS protocol and response headers](https://fetch.spec.whatwg.org/)
