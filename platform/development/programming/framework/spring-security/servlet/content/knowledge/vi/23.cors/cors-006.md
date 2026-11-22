# `allowedOriginPatterns` và kiểm soát tập nguồn được tin cậy

## 1. Hiểu đúng mục tiêu

Trong ứng dụng **Spring Security Servlet + Spring MVC**, `CorsConfiguration#setAllowedOriginPatterns(...)` khai báo những **mẫu Origin được phép đọc phản hồi cross-origin trong trình duyệt**. API này hữu ích khi nhiều origin hợp lệ tuân theo một quy tắc tên miền, chẳng hạn `https://<tenant>.tenant.example.com`, nhưng cần đặc biệt cẩn thận: ký tự `*` có thể mở rộng tập nguồn được cấp quyền lớn hơn dự kiến.

Điều cốt lõi:

- **Origin** gồm `scheme + host + port` (ví dụ `https://app.example.com:8443`), không bao gồm path, query, fragment. `https://app.example.com` và `http://app.example.com` là hai origin khác nhau; cổng khác cũng tạo origin khác.
- **CORS là cơ chế do trình duyệt thực thi** để kiểm soát JavaScript ở một origin có được đọc phản hồi từ origin khác hay không. Không coi `Origin` là danh tính đáng tin của caller: công cụ HTTP, backend khác hoặc script có thể chủ động đặt header này.
- **CORS không thay thế authentication, authorization hay CSRF protection**. Cho phép origin không đồng nghĩa cấp quyền cho mọi người dùng ở origin ấy. Ngược lại, không cho phép origin không nhất thiết ngăn server nhận mọi loại request.
- `allowedOriginPatterns` là allowlist **theo mẫu**, không phải biểu thức chính quy tùy ý hay cấu hình định tuyến URL. Trong hệ thống có đăng nhập bằng cookie, chỉ cho phép **những origin thực sự do tổ chức kiểm soát**.

**Mục tiêu thực tế:** một giao diện chính `https://app.example.com`, các giao diện tenant trong miền được quản trị `https://*.tenant.example.com`, và môi trường phát triển `http://localhost:5173` có thể gọi `/api/**`; website ngoài tập này không được nhận header CORS cho phép đọc dữ liệu.

## 2. Luồng CORS và vị trí của Spring Security

Giả sử trang tại `https://acme.tenant.example.com` gọi API `https://api.example.com/api/check`.

```text
JavaScript trong trình duyệt
    |
    | Origin: https://acme.tenant.example.com
    | (có thể có preflight OPTIONS)
    v
Servlet container
    |
    v
Spring Security FilterChainProxy
    |
    +--> CorsFilter / CORS processing (khi bật http.cors)
    |        kiểm tra Origin, method, request headers
    |        phản hồi preflight hoặc bổ sung header CORS
    |
    +--> authentication / authorization filters
    |
    v
DispatcherServlet -> Controller -> JSON response
    |
    v
Trình duyệt kiểm tra các header Access-Control-Allow-*
    |
    +--> cho phép JavaScript đọc response nếu phù hợp
    +--> chặn JavaScript đọc response nếu không phù hợp
```

Preflight thường xảy ra khi trình duyệt muốn dùng method hoặc request header không thuộc nhóm được miễn preflight, ví dụ `Authorization`. Trình duyệt gửi:

```http
OPTIONS /api/check HTTP/1.1
Host: api.example.com
Origin: https://acme.tenant.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Server phải xét **Origin** cùng **method của request thực tế** (`GET` trong `Access-Control-Request-Method`) và các header được yêu cầu. Không cần thêm `OPTIONS` vào `allowedMethods` chỉ để cho phép một preflight của method `GET`: `allowedMethods` mô tả method thực tế cần được chấp nhận.

Phản hồi preflight hợp lệ có thể chứa:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://acme.tenant.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 1800
Vary: Origin
Vary: Access-Control-Request-Method
Vary: Access-Control-Request-Headers
```

Thứ tự, chữ hoa/thường và cách gộp các header có thể khác tùy servlet container và Spring. Với preflight được xử lý thành công ngay ở CORS filter, request không cần vào controller hay trải qua đăng nhập của endpoint. Đây là lý do Spring Security khuyến nghị xử lý CORS **trước authentication**: preflight thường không mang thông tin phiên để xác thực.

## 3. `allowedOrigins` khác `allowedOriginPatterns` ra sao?

Hai cấu hình đều mô tả origin được phép, nhưng cách so khớp và giá trị phản hồi khác nhau.

| API | Ý nghĩa | Khi nào dùng |
| --- | --- | --- |
| `setAllowedOrigins(List.of("https://app.example.com"))` | Danh sách origin chính xác | Lựa chọn mặc định cho các frontend đã biết |
| `setAllowedOrigins(List.of("*"))` | Chấp nhận mọi origin, thường phản hồi wildcard `*` | Chỉ cân nhắc với tài nguyên công khai, không dùng cùng `allowCredentials(true)` |
| `setAllowedOriginPatterns(List.of("https://*.tenant.example.com"))` | Chấp nhận origin khớp mẫu | Chỉ khi tất cả subdomain khớp mẫu đều đủ tin cậy |
| `setAllowedOriginPatterns(List.of("*"))` | Có thể khớp mọi origin và phản hồi chính origin gửi đến | **Nguy hiểm**, nhất là với `allowCredentials(true)` |

Với `allowedOriginPatterns`, nếu một origin khớp, Spring sử dụng **giá trị Origin cụ thể** làm `Access-Control-Allow-Origin`, ví dụ:

```http
Origin: https://acme.tenant.example.com
Access-Control-Allow-Origin: https://acme.tenant.example.com
```

Thay vì:

```http
Access-Control-Allow-Origin: *
```

Vì vậy pattern có thể được dùng khi `allowCredentials(true)`. Đây chỉ là khả năng kỹ thuật, **không chứng minh pattern đó an toàn**. Ví dụ `allowedOriginPatterns("*")` cộng `allowCredentials(true)` có thể cấp quyền đọc phản hồi dùng cookie cho rất nhiều website không đáng tin nếu các điều kiện về cookie và trình duyệt cho phép. Trong khi đó, `allowedOrigins("*")` kết hợp `allowCredentials(true)` là cấu hình không hợp lệ theo kiểm tra của Spring.

**Quy tắc lựa chọn:** dùng origin chính xác khi biết rõ hostname; chỉ thêm pattern hẹp khi bài toán thật sự cần wildcard và đã kiểm soát toàn bộ namespace tương ứng.

## 4. Cú pháp pattern và những ranh giới phải kiểm soát

Spring Framework hỗ trợ dấu `*` trong mẫu origin và danh sách cổng dạng `:[...]`. Ví dụ:

```java
// Các biểu thức minh họa cho CorsConfiguration#setAllowedOriginPatterns:
List.of(
    "https://*.tenant.example.com",
    "https://preview.example.com:[8443,9443]",
    "https://*.dev.example.com:[*]"
);
```

- `https://*.tenant.example.com`: chỉ mẫu có scheme HTTPS và hậu tố hostname tương ứng; ký tự `*` có thể khớp nhiều ký tự, kể cả các dấu chấm trong tên con.
- `https://preview.example.com:[8443,9443]`: minh họa cách liệt kê cổng có thể chấp nhận.
- `:[*]`: cho phép nhiều cổng, tăng bề mặt tin cậy; chỉ dùng khi thực sự cần.
- `https://*.example.com/api` **không phải cách cấu hình path**. Browser gửi `Origin` không có `/api`; giới hạn API path bằng `registerCorsConfiguration("/api/**", ...)`.
- `https://*.example.com` không có nghĩa là tự bao gồm `https://example.com`. Nếu cần root domain, khai báo riêng.
- Tránh pattern quá rộng như `*`, `https://*` hoặc `https://*example.com`: chúng có thể cấp quyền cho origin ngoài dự định.
- Tránh cho phép `Origin: null` trừ khi có lý do và đánh giá riêng. Opaque origins (ví dụ một số iframe sandbox, tài liệu `file:`) có thể phát sinh giá trị này.

Xét chính sách minh họa sau: origin chính xác `https://app.example.com` và `http://localhost:5173`; pattern `https://*.tenant.example.com`.

| Origin gửi đến | Kết quả dự kiến | Giải thích |
| --- | --- | --- |
| `https://app.example.com` | Cho phép | Có trong danh sách chính xác |
| `http://localhost:5173` | Cho phép trong môi trường dev | Origin dev được khai báo rõ |
| `https://acme.tenant.example.com` | Cho phép | Khớp pattern |
| `https://a.b.tenant.example.com` | Có thể khớp | Wildcard không tự giới hạn ở đúng một cấp subdomain; phải xét chính sách tên miền |
| `https://tenant.example.com` | Không cho phép | Thiếu phần subdomain trước `.tenant` |
| `http://acme.tenant.example.com` | Không cho phép | Sai scheme |
| `https://acme.tenant.example.com:8443` | Không cho phép | Cổng không được mẫu trên khai báo |
| `https://acme.tenant.example.com.attacker.test` | Không cho phép | Hostname không kết thúc ở hậu tố cho phép |
| `https://attacker.example.net` | Không cho phép | Nằm ngoài allowlist |
| `null` | Không cho phép | Không được cấu hình |

Bảng giả định các origin được trình duyệt serialize ở dạng thông thường. Đừng tự viết thêm một kiểm tra `endsWith("example.com")`: `https://notexample.com` cũng có thể qua một kiểm tra hậu tố quá lỏng. Khi cần kiểm soát từng tenant, nên dùng hostname đã xác minh và danh sách origin đã đăng ký.

## 5. Ví dụ Spring Boot 3.3.x, Spring Security Servlet và Java 17+

Ví dụ độc lập này dùng một `UrlBasedCorsConfigurationSource` dành riêng cho `/api/**`; Spring Security tích hợp qua `http.cors(Customizer.withDefaults())`. Giả định tổ chức thực sự quản lý tất cả hostname được phép dưới `tenant.example.com`. Nếu tenant được tự chọn tên miền hoặc có thể tạo subdomain chạy mã không tin cậy, **không được dùng wildcard này làm tiêu chuẩn tin cậy**.

Khởi tạo dự án Gradle với Java 17+, Spring Boot Web và Spring Security; cấu hình mẫu của `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Tạo `src/main/java/demo/cors/CorsPatternsApplication.java`:

```java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsPatternsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsPatternsApplication.class, args);
    }
}
```

Tạo `src/main/java/demo/cors/SecurityConfig.java`:

```java
package demo.cors;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/check").permitAll()
                        .anyRequest().authenticated())
                .build();
    }

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();

        // Origin cố định: production frontend và frontend local.
        // localhost chỉ nên có trong profile cấu hình phát triển.
        cors.setAllowedOrigins(List.of(
                "https://app.example.com",
                "http://localhost:5173"));

        // Chỉ hợp lệ nếu mọi subdomain này đều do bên mình quản lý.
        cors.setAllowedOriginPatterns(List.of(
                "https://*.tenant.example.com"));

        // Phạm vi API demo chỉ cho phép GET.
        cors.setAllowedMethods(List.of("GET"));
        cors.setAllowedHeaders(List.of(
                "Authorization", "Content-Type", "X-Request-ID"));
        cors.setExposedHeaders(List.of("X-Request-ID"));

        // Phục vụ ví dụ về cookie/session; chỉ bật khi thật sự cần.
        cors.setAllowCredentials(true);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
```

Tạo `src/main/java/demo/cors/DemoController.java`:

```java
package demo.cors;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class DemoController {
    @GetMapping("/check")
    public ResponseEntity<Map<String, String>> check() {
        return ResponseEntity.ok()
                .header("X-Request-ID", "demo-001")
                .body(Map.of("result", "ok"));
    }
}
```

**Giải thích cấu hình:**

1. `http.cors(Customizer.withDefaults())` kích hoạt tích hợp CORS trước các bước xác thực thông thường của Spring Security. Bean `UrlBasedCorsConfigurationSource` cung cấp chính sách cần dùng; không cần đăng ký thêm `CorsFilter` thủ công cho ví dụ này.
2. `setAllowedOrigins(...)` dành cho hai origin cố định. Giá trị `http://localhost:5173` phục vụ phát triển; production nên tách profile để loại bỏ origin này.
3. `setAllowedOriginPatterns(...)` chỉ mở rộng cho tenant subdomain khớp HTTPS. Spring trả origin thực tế khi khớp, kể cả khi `allowCredentials(true)`.
4. `registerCorsConfiguration("/api/**", cors)` giới hạn **đường dẫn API áp dụng CORS**; đây là việc khác với so khớp `Origin`.
5. `setAllowedMethods(List.of("GET"))` là method request thực tế được phép qua CORS. Nó không tự mở quyền `POST`, cũng không làm thay đổi quyết định authorization của Spring Security.
6. `setAllowedHeaders(...)` giới hạn các header mà một preflight có thể xin phép dùng; `setExposedHeaders(...)` nói trình duyệt được cho JavaScript đọc thêm header phản hồi `X-Request-ID`.
7. `setMaxAge(1800L)` cho phép trình duyệt cache kết quả preflight trong khoảng thời gian được thông báo, dưới các giới hạn và chính sách riêng của trình duyệt.
8. `allowCredentials(true)` chỉ cần khi frontend dự kiến dùng credential trong request cross-origin. Khi không cần cookie, ưu tiên không bật chế độ này. Cấu hình này không tự tạo cookie hoặc làm cookie vượt qua các quy tắc `SameSite`, `Secure` của trình duyệt.
9. Quy tắc `.permitAll()` cho GET `/api/check` **chỉ để thử CORS độc lập với đăng nhập**. Endpoint thật cần authorization đúng nghiệp vụ và vẫn có thể trả `401`/`403` dù CORS hợp lệ.

## 6. Thử request và đọc đúng kết quả

Khởi chạy ứng dụng bằng Gradle wrapper của dự án:

```bash
./gradlew bootRun
```

Trên Windows dùng `.\gradlew.bat bootRun`. Nếu chưa có wrapper, tạo bằng Gradle phù hợp với phiên bản Spring Boot đang dùng.

### 6.1. Preflight từ tenant hợp lệ

```bash
curl -i -X OPTIONS "http://localhost:8080/api/check" \
  -H "Origin: https://acme.tenant.example.com" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
```

Với cấu hình ở trên, response mong đợi là HTTP 2xx, có các giá trị tương đương:

```http
Access-Control-Allow-Origin: https://acme.tenant.example.com
Access-Control-Allow-Credentials: true
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: Authorization
```

Giá trị header có thể khác về chữ hoa/thường hoặc cách biểu diễn. Điều cần xác nhận là **origin cụ thể được phản hồi** và method/header được cho phép. Không kỳ vọng `Access-Control-Allow-Origin: *`.

### 6.2. Origin không đáng tin

```bash
curl -i -X OPTIONS "http://localhost:8080/api/check" \
  -H "Origin: https://attacker.example.net" \
  -H "Access-Control-Request-Method: GET"
```

Với CORS processor mặc định trong ví dụ, preflight không khớp thường bị từ chối bằng HTTP `403` (có thể có body `Invalid CORS request`). Quan trọng hơn, response **không có header `Access-Control-Allow-Origin` cấp quyền** cho attacker. Trong ứng dụng có error handling, proxy hoặc filter bổ sung, chi tiết body/status có thể khác; cần kiểm tra header thực tế.

### 6.3. GET thực tế từ origin hợp lệ

```bash
curl -i "http://localhost:8080/api/check" \
  -H "Origin: https://app.example.com"
```

Response dự kiến:

```http
HTTP/1.1 200
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Access-Control-Expose-Headers: X-Request-ID
X-Request-ID: demo-001
Content-Type: application/json
```

Body JSON tương đương `{"result":"ok"}`.

`curl` **không thực thi CORS như trình duyệt**: nó hiển thị kết quả HTTP ngay cả với origin bị từ chối. Dùng `curl` để xem header/status của server, sau đó kiểm tra bằng browser devtools nếu cần xác nhận JavaScript có thực sự được đọc response hay không.

## 7. Kiểm thử tự động chính sách CORS

Tạo `src/test/java/demo/cors/CorsPatternsIntegrationTest.java`:

```java
package demo.cors;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CorsPatternsIntegrationTest {
    @Autowired
    private TestRestTemplate client;

    private ResponseEntity<String> preflight(String origin) {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin(origin);
        headers.setAccessControlRequestMethod(HttpMethod.GET);
        headers.setAccessControlRequestHeaders(List.of("Authorization"));

        return client.exchange(
                "/api/check",
                HttpMethod.OPTIONS,
                new HttpEntity<Void>(headers),
                String.class);
    }

    @Test
    void trustedTenantPatternReflectsConcreteOrigin() {
        ResponseEntity<String> response =
                preflight("https://acme.tenant.example.com");

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .isEqualTo("https://acme.tenant.example.com");
        assertThat(response.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS))
                .isEqualTo("true");
    }

    @Test
    void untrustedOriginCannotPassPreflight() {
        ResponseEntity<String> response =
                preflight("https://attacker.example.net");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(response.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .isNull();
    }

    @Test
    void exactAllowedOriginWorksForRealGet() {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin("https://app.example.com");

        ResponseEntity<String> response = client.exchange(
                "/api/check",
                HttpMethod.GET,
                new HttpEntity<Void>(headers),
                String.class);

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getBody()).contains("\"result\":\"ok\"");
        assertThat(response.getHeaders().getFirst(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .isEqualTo("https://app.example.com");
    }
}
```

Chạy:

```bash
./gradlew test
```

Trên Windows dùng `.\gradlew.bat test`.

Kiểm thử dùng cổng ngẫu nhiên và Servlet server thực giúp quan sát CORS filter cùng security filter chain. Nếu hệ thống có gateway, CDN, nhiều `SecurityFilterChain`, hoặc cấu hình CORS riêng theo môi trường, cần thêm test end-to-end ở đường đi triển khai thật.

**Mở rộng test âm:** `Origin: null`, sai scheme (`http://`), sai port, hostname gần giống, origin root không được liệt kê, method không được cho phép, request header ngoài tập và tenant domain đã thu hồi. Các test âm giúp chứng minh giới hạn của mẫu, không chỉ chứng minh mẫu hợp lệ được chấp nhận.

## 8. Thiết kế allowlist an toàn cho nhiều tenant

Một quyết định tưởng đơn giản như `https://*.tenant.example.com` thực chất là cấp quyền cho **mọi hostname khớp mẫu**, kể cả subdomain mới phát sinh trong tương lai. Hãy kiểm tra chính sách sở hữu tên miền trước khi dùng:

- Nếu **chính hệ thống kiểm soát việc cấp DNS, routing và nội dung** của tất cả subdomain dưới `tenant.example.com`, pattern có thể phù hợp.
- Nếu tenant được **đăng nội dung JavaScript không tin cậy, tự trỏ CNAME, tạo subdomain tùy ý**, hoặc một subdomain từng bị thu hồi vẫn có thể bị takeover, wildcard có thể khiến một origin không đáng tin được đọc tài nguyên của user đã đăng nhập.
- Với custom domains (ví dụ `https://portal.customer-a.com`), nên lưu **danh sách origin chính xác đã xác minh** theo tenant, không mở pattern phủ nhiều miền của khách hàng.
- Khi tenant bị vô hiệu hóa hoặc đổi domain, phải loại origin khỏi allowlist và tính đến việc trình duyệt có thể đã cache preflight theo `Access-Control-Max-Age`.

Một quy trình quản trị origin thực tế:

1. **Đăng ký:** chủ sở hữu tenant khai báo origin đầy đủ (`https://...`), không chỉ hostname.
2. **Xác minh:** kiểm tra quyền quản lý domain/host theo quy trình sản phẩm; không tin ngay chuỗi `Origin` do request tự gửi.
3. **Phê duyệt:** chỉ đưa origin vào cấu hình theo môi trường và dịch vụ API thực sự cần truy cập; quản lý audit và quyền thay đổi danh sách.
4. **Đánh giá:** giới hạn HTTPS, cổng, phạm vi API, quyền cookie; phát hiện subdomain hoặc DNS record không còn người quản lý.
5. **Thu hồi:** xóa origin khi tenant mất quyền hoặc miền bị chuyển giao; chạy lại test âm.

Nếu cần cấu hình động, `CorsConfigurationSource` có thể xác định chính sách theo request dựa trên **metadata tenant đáng tin** và allowlist đã lưu. Không viết logic kiểu “nhận bất kỳ `Origin` nào rồi trả lại chính giá trị đó”, vì đây chỉ là phiên bản động của `allowedOriginPatterns("*")`. Nếu dùng hostname/headers qua reverse proxy để phân giải tenant, chỉ tin header forwarded do proxy đáng tin cung cấp và đã được cấu hình xử lý an toàn.

## 9. Credentials, cookies, CSRF và CORS là bốn khái niệm khác nhau

Khi frontend cần gửi cookie/session từ origin khác:

```javascript
fetch("https://api.example.com/api/check", {
  method: "GET",
  credentials: "include"
}).then(response => response.json());
```

Để browser cho JavaScript đọc phản hồi credentialed, ngoài các điều kiện khác, server cần trả **origin cụ thể** và `Access-Control-Allow-Credentials: true`. Nhưng:

- `credentials: "include"` ở frontend không đảm bảo cookie thực sự được gửi; browser còn xét domain/path, `SameSite`, `Secure`, chính sách third-party cookie và người dùng.
- Cookie đăng nhập vẫn phải gắn với **user/session đã được xác thực** và mỗi endpoint vẫn cần kiểm tra authorization.
- CORS không phải CSRF token. Với request có cookie, hãy duy trì CSRF protection phù hợp với ứng dụng. Ví dụ Security config ở trên không tự tắt CSRF; method ghi dữ liệu như POST/PUT/DELETE vẫn cần được thiết kế riêng.
- `Access-Control-Allow-Origin` và `Access-Control-Allow-Credentials` **không chứng minh caller hợp lệ**; `Origin` có thể bị giả bởi client không phải trình duyệt.
- `Access-Control-Allow-Headers: Authorization` chỉ cho browser biết có thể gửi header đó; không xác thực hay kiểm tra token. Bộ lọc xác thực phải tự kiểm tra token.
- Nếu nội dung thực sự công khai, có thể không cần credentials và có thể dùng cấu hình CORS đơn giản hơn, nhưng phải bảo đảm response không chứa dữ liệu cá nhân.

Không dùng wildcard rộng cộng credentials chỉ vì Spring cho phép pattern; cần đánh giá **origin nào có thể chạy JavaScript** và **user nào có cookie/token được trình duyệt gửi đến API**.

## 10. Cache, reverse proxy và nhiều lớp cấu hình

Với allowlist động hoặc pattern, server có thể phản hồi một `Access-Control-Allow-Origin` khác nhau tùy request. Cache chung/CDN cần phân biệt biến thể theo `Origin`. Spring CORS processor thường bổ sung `Vary: Origin` cùng các header preflight liên quan; đừng để gateway xóa hoặc ghi đè `Vary`.

Các nguồn cấu hình thường gặp:

- Bean `CorsConfigurationSource` dùng với `http.cors(...)` trong Spring Security;
- Cấu hình CORS Spring MVC qua `WebMvcConfigurer#addCorsMappings(...)`;
- `@CrossOrigin` trên controller/handler;
- Servlet `CorsFilter` đăng ký thủ công;
- Gateway, ingress, CDN thêm hoặc sửa header.

Các lớp này có thể phối hợp theo cơ chế riêng, nhưng thêm tất cả “cho chắc” thường gây response chứa nhiều `Access-Control-Allow-Origin` hoặc chính sách không thống nhất. Chọn **một nơi quản lý chính** cho API, hiểu rõ cách Security lấy cấu hình, và kiểm thử trên response thực tế. Với nhiều `SecurityFilterChain` hoặc nhiều servlet path, xác định filter chain nào áp dụng cho endpoint mục tiêu.

Không bật `permitAll()` cho mọi endpoint chỉ để preflight thành công. Tích hợp CORS trước authentication là hướng đúng; authorization của request thực tế vẫn phải giữ nguyên.

## 11. Checklist chẩn đoán và lỗi phổ biến

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách khắc phục |
| --- | --- | --- |
| Preflight trả `401` hoặc redirect login | CORS xử lý sau authentication hoặc chưa tích hợp vào Security | Cấu hình `http.cors(...)` với `CorsConfigurationSource` đúng |
| Server ghi `Invalid CORS request` | Origin, method hoặc header xin phép không khớp | Kiểm tra ba giá trị `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers` |
| `Access-Control-Allow-Origin` thiếu | Origin không có trong allowlist, path không khớp `/api/**`, hoặc proxy thay header | Xem request thực, cấu hình theo path, response cuối cùng |
| `Access-Control-Allow-Origin: *` nhưng frontend dùng cookie | Cấu hình wildcard không tương thích credentialed response | Dùng origin cụ thể/allowlist hẹp, bật credentials khi thật sự cần |
| `allowedOriginPatterns` dường như không áp dụng | Khai báo nhầm `allowedOrigins`, khác bean/source hoặc nhiều filter chain | Xem đối tượng cấu hình thực sự dùng cho request |
| `https://app.example.com` hoạt động, port khác thất bại | Port là một phần của origin | Chỉ thêm port chính xác được phê duyệt |
| Backend trả `200` mà browser báo CORS error | `200` không chứng minh các header CORS đúng | Kiểm tra header và thông báo preflight/actual trong devtools |
| CORS hợp lệ nhưng API vẫn `403` | Authorization hoặc CSRF từ chối request thật | Xem log Security, principal, token/CSRF, không nới origin bừa bãi |
| Mỗi environment có một whitelist khác nhau | Localhost/staging/prod được trộn vào một chính sách | Tách cấu hình/profiles, kiểm soát origin triển khai |
| Phản hồi cache chứa origin của request khác | Cache/proxy không phân biệt biến thể `Origin` | Giữ `Vary` và kiểm tra chính sách cache |

Đặc biệt: browser có thể gửi **simple request** trước khi quyết định chặn JavaScript đọc response. Vì vậy bảo vệ dữ liệu và hành vi server vẫn dựa vào authentication, authorization, CSRF, kiểm tra input và thiết kế endpoint; không dựa vào việc trình duyệt sẽ báo lỗi CORS.

## 12. Bài tập kiểm tra hiểu biết

**Bài tập 1.** Bạn cấu hình `setAllowedOriginPatterns(List.of("https://*.example.com"))` và `allowCredentials(true)`. Một dịch vụ khác cho phép người dùng đăng mã JavaScript tại `https://files.example.com`. Hỏi: pattern có an toàn cho API chứa dữ liệu đăng nhập không?

**Gợi ý trả lời:** Không thể mặc định coi là an toàn. Website `files.example.com` có thể khớp pattern và trở thành origin được trình duyệt cho phép đọc phản hồi credentialed (khi cookie cùng các quy tắc liên quan cho phép). Cần bỏ wildcard rộng, dùng danh sách origin chính xác và tách vùng nội dung không tin cậy.

**Bài tập 2.** Preflight có `Origin: https://acme.tenant.example.com`, `Access-Control-Request-Method: DELETE`, trong khi `allowedMethods` chỉ chứa `GET`. Có nên thêm `OPTIONS` để cho request đi qua?

**Gợi ý trả lời:** Không. Method được xin phép là `DELETE`, vốn nằm ngoài chính sách. Thêm `OPTIONS` không hợp thức hóa `DELETE`; chỉ thêm `DELETE` nếu endpoint thật sự cần và có kiểm soát authorization/CSRF tương ứng.

**Bài tập 3.** Một API phản hồi `Access-Control-Allow-Origin: https://acme.tenant.example.com` nhưng fetch có `credentials: "include"` vẫn bị browser chặn. Hãy kiểm tra gì?

**Gợi ý trả lời:** Kiểm tra `Access-Control-Allow-Credentials: true`, chính sách preflight, header/method được yêu cầu, cấu hình cookie và trình duyệt (`SameSite`, `Secure`, third-party cookie), cùng response cuối cùng qua proxy. CORS cho phép đọc response không đồng nghĩa browser chắc chắn gửi cookie.

## Ghi nhớ

`allowedOriginPatterns` là công cụ hữu ích để diễn đạt allowlist theo tên miền, nhưng **mẫu rộng đồng nghĩa tập origin có quyền đọc phản hồi rộng**. Trong Spring Security Servlet, hãy tích hợp CORS qua `http.cors(...)` cùng nguồn cấu hình rõ ràng, giữ whitelist hẹp theo scheme/host/port/path API, thử cả trường hợp cho phép lẫn từ chối, và không dùng CORS thay thế cơ chế bảo mật của endpoint.