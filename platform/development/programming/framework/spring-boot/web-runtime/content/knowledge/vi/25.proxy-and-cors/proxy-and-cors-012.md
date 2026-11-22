# Tránh cấu hình CORS trùng tại ứng dụng, gateway và Spring Security

## 1. Vấn đề: API trả HTTP 200 nhưng browser vẫn báo lỗi CORS

Một hệ thống Spring Boot thường có nhiều lớp:

```text
Browser (https://ui.example.test)
       |
       | Origin: https://ui.example.test
       v
API gateway / ingress / NGINX
       |
       v
Spring Security filter chain
       |
       v
Spring MVC / WebFlux controller
       |
       v
Business logic
```

Cả gateway, Spring Security và ứng dụng Spring MVC/WebFlux đều **có khả năng tham gia xử lý CORS**. Khi nhiều nơi cùng thêm response headers mà không có một chính sách thống nhất, browser có thể báo:

```text
Access to fetch at ... has been blocked by CORS policy:
The 'Access-Control-Allow-Origin' header contains multiple values ...
```

Lỗi này **không nhất thiết là API không chạy**. Backend có thể trả 200 và JSON hợp lệ, nhưng browser từ chối cho JavaScript đọc response vì response CORS không hợp lệ. Ví dụ sai:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example.test
Access-Control-Allow-Origin: https://ui.example.test
Content-Type: application/json
```

Dù hai giá trị giống nhau, gửi **hai `Access-Control-Allow-Origin`** vẫn không hợp lệ đối với cơ chế CORS của browser. Trường hợp một lớp nối các giá trị thành `https://ui.example.test, https://other.example.test` cũng không phải định dạng origin hợp lệ: một response CORS chỉ được công bố một origin cụ thể (hoặc `*` trong trường hợp được phép), không phải một danh sách origins phân cách bằng dấu phẩy.

**Mục tiêu:** Mỗi request trên **public route** phải đi qua **một chính sách CORS nhất quán**, và HTTP response cuối cùng không bị nhiều tầng cùng ghi các header CORS mâu thuẫn hoặc trùng lặp.

Phạm vi minh họa: **Spring Boot 3.3.x, Spring Security 6.x, Spring Framework 6.1.x, Java 17+**; ứng dụng mẫu dùng Spring MVC với Java 21. Có thêm phần Spring Cloud Gateway 4.1.x (dòng tương thích với Spring Boot 3.3 qua Spring Cloud 2023.0.x), gateway HTTP thông thường, và so sánh WebFlux. Không lẫn CORS với authentication/authorization, CSRF hay thông tin chuyển tiếp từ proxy.

## 2. CORS là giao ước giữa browser và server, không phải firewall

Một **origin** có ba thành phần:

```text
scheme + host + port
```

Ví dụ:

| URL | Origin | So với `https://ui.example.test` |
| --- | --- | --- |
| `https://ui.example.test/page` | `https://ui.example.test` | Cùng origin |
| `https://api.example.test/v1` | `https://api.example.test` | Khác host |
| `http://ui.example.test/page` | `http://ui.example.test` | Khác scheme |
| `https://ui.example.test:8443/page` | `https://ui.example.test:8443` | Khác port |
| `https://ui.example.test/other` | `https://ui.example.test` | Cùng origin |

Browser áp dụng same-origin policy khi JavaScript đọc dữ liệu qua `fetch` hoặc XMLHttpRequest. Server có thể cho phép một origin được đọc response bằng **CORS response headers**. Client như `curl`, Java `HttpClient`, Postman hoặc backend-to-backend thường không áp dụng cơ chế browser CORS: chúng vẫn gửi request và đọc response theo chính sách của chính chúng.

CORS **không thay thế**:

- Authentication (xác định ai gọi).
- Authorization (ai được đọc/sửa tài nguyên).
- CSRF protection với phiên dùng cookie.
- TLS/HTTPS và xác minh certificate.
- Network policies, API gateway authentication và rate limiting.

Vì CORS không phải xác thực, header `Origin` **không được dùng làm danh tính người gọi**. Một client không phải browser có thể tạo header tùy ý; ngay cả browser chỉ dùng CORS để giới hạn JavaScript đọc response, không có nghĩa mọi tác dụng phụ của request đều tự được ngăn.

## 3. Phân biệt preflight và actual request

Browser có thể gửi **preflight request** trước request thực khi phương thức hoặc request headers vượt điều kiện của “simple CORS request”. Ví dụ JavaScript:

```javascript
const response = await fetch("https://api.example.test/api/ping", {
  method: "GET",
  headers: {
    "Authorization": "Bearer some-token"
  }
});
console.log(await response.text());
```

`Authorization` là request header không thuộc CORS-safelisted request headers, nên browser thường gửi preflight:

```http
OPTIONS /api/ping HTTP/1.1
Host: api.example.test
Origin: https://ui.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Nếu policy cho phép:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example.test
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 1800
Vary: Origin
```

Sau khi preflight thành công, browser mới gửi GET thực. Ví dụ response actual:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://ui.example.test
Content-Type: text/plain

pong
```

Các header/số status phía trên là **dạng minh họa**. Framework có thể trả danh sách `Vary` bao gồm `Access-Control-Request-Method` và `Access-Control-Request-Headers`; thứ tự/chữ hoa và mã trạng thái 2xx có thể khác. Điều cần kiểm tra là policy logic và các trường bắt buộc, không so sánh nguyên văn toàn bộ response.

Một request `GET` đơn giản có thể **không có preflight**, nhưng vẫn cần response `Access-Control-Allow-Origin` thích hợp nếu JavaScript từ origin khác muốn đọc kết quả. Chỉ sửa endpoint `OPTIONS` rồi bỏ quên response GET/POST là chưa đủ.

## 4. Nhận diện response headers và request headers

| Header | Hướng | Chức năng |
| --- | --- | --- |
| `Origin` | Browser → server | Origin khởi tạo request |
| `Access-Control-Request-Method` | Browser → server (preflight) | Phương thức actual dự định |
| `Access-Control-Request-Headers` | Browser → server (preflight) | Header actual muốn gửi |
| `Access-Control-Allow-Origin` | Server → browser | **Một** origin được phép hoặc `*` trong trường hợp hợp lệ |
| `Access-Control-Allow-Methods` | Server → browser (preflight) | Các phương thức có thể dùng |
| `Access-Control-Allow-Headers` | Server → browser (preflight) | Các request headers được phép |
| `Access-Control-Allow-Credentials` | Server → browser | Cho phép browser đọc response khi dùng credentials mode phù hợp |
| `Access-Control-Expose-Headers` | Server → browser | Các response headers bổ sung mà JavaScript có thể đọc |
| `Access-Control-Max-Age` | Server → browser (preflight) | Khoảng cache kết quả preflight, giây |
| `Vary: Origin` | Server → cache/proxy/client | Thông báo response có thể thay đổi theo Origin |

`Access-Control-Allow-Origin` và `Access-Control-Allow-Credentials` là các trường nhạy cảm với việc bị **ghi trùng hoặc mâu thuẫn**. Không dùng nhiều giá trị cho `Access-Control-Allow-Origin`. Nếu allowlist gồm nhiều origins, hãy chọn **origin phù hợp với request hiện tại** để trả trong response, không gửi nguyên danh sách.

`Vary: Origin` quan trọng với CDN/shared cache: response đã được phép cho `https://a.example` không được cache rồi phục vụ nhầm cho `https://b.example`. Khi cache **preflight**, còn cần xét `Access-Control-Request-Method` và `Access-Control-Request-Headers`. Nhiều Spring CORS processors tự đưa vào các giá trị `Vary` thích hợp; không được xóa/chặn chúng ở gateway khi thiết kế cache.

`Vary` bản thân có thể có **nhiều trường hợp lệ** hoặc danh sách giá trị; không áp dụng quy tắc “chỉ một header duy nhất” của `Access-Control-Allow-Origin` cho mọi response header.

## 5. Phân biệt “cấu hình CORS ở nhiều nơi” với “header CORS bị nhân đôi”

Có hai kiểu trùng khác nhau:

**Loại A — trùng cấu hình trong cùng Spring MVC.** Ứng dụng có global `WebMvcConfigurer.addCorsMappings()` và `@CrossOrigin` trên controller. Spring Framework **có cơ chế kết hợp global và local `CorsConfiguration`**. Nhiều origins/methods/headers thường được gộp; một số thuộc tính đơn như `allowCredentials`, `maxAge` có quy tắc override. Vì vậy **không phải cứ có cả hai là chắc chắn response chứa hai `Access-Control-Allow-Origin`**. Vấn đề là policy trở nên khó kiểm toán, và local annotation có thể mở quyền rộng hơn chủ đích.

**Loại B — hai tầng độc lập cùng viết response.** Ví dụ gateway thêm:

```http
Access-Control-Allow-Origin: https://ui.example.test
```

rồi backend Spring MVC hoặc Security cũng thêm:

```http
Access-Control-Allow-Origin: https://ui.example.test
```

Gateway chuyển tiếp upstream response kèm header rồi thêm header mới. Browser nhận hai giá trị, hoặc một chuỗi gộp bằng dấu phẩy, dẫn tới **lỗi CORS thật**. Điều này có thể xảy ra dù mỗi lớp riêng lẻ đã được cấu hình đúng.

**Loại C — cùng ứng dụng có nhiều CORS processors khác nhau.** Một `CorsFilter` bean, Security `.cors(...)` và MVC handler-level CORS có thể tạo nhiều điểm xử lý. Một số Spring CORS implementations bỏ qua thao tác khi thấy response đã có `Access-Control-Allow-Origin`, nên không phải lúc nào chúng cũng xuất ra header trùng. Tuy vậy policy, filter order, error paths và hành vi preflight có thể khác nhau; nên tránh quản lý một endpoint bằng nhiều cơ chế độc lập.

**Mục tiêu chính không phải xóa mọi chỗ có chữ CORS**, mà là có **một policy owner được xác định rõ**, các thành phần cần thiết tích hợp **dùng chung nguồn policy**, và chỉ một nơi chủ động quyết định response CORS cho từng public route.

## 6. Bản đồ nơi có thể chèn CORS header

```text
Request:
Browser
  -> CDN / WAF
  -> API Gateway / Ingress / NGINX
  -> Spring Security CORS filter
  -> Spring MVC HandlerMapping / @CrossOrigin
  -> Controller

Response:
Controller
  -> MVC CorsProcessor có thể thêm ACAO
  -> Security filter / CorsFilter có thể tham gia
  -> API Gateway có thể thêm ACAO lần nữa
  -> CDN có thể sửa hoặc cache
  -> Browser đánh giá response cuối
```

Điểm cần quan sát là **response cuối từ public URL**. Một response lấy trực tiếp từ backend có thể chỉ một `Access-Control-Allow-Origin` nhưng response khi qua gateway có hai. Ngược lại, nếu gateway trả 401 hoặc 404 **trước khi gọi backend**, app dù có CORS đúng cũng không có cơ hội thêm header cho response do gateway tự tạo.

| Lớp | Cấu hình thường gặp | Rủi ro |
| --- | --- | --- |
| Spring MVC | `@CrossOrigin`, `WebMvcConfigurer.addCorsMappings` | Policy cục bộ và toàn cục bị cộng dồn quá rộng |
| Spring Security | `http.cors(...)`, `CorsConfigurationSource` | Preflight bị auth chặn hoặc nhiều sources mơ hồ |
| Servlet filters | `CorsFilter` bean tự thêm | Trùng/khác thứ tự với Security và MVC |
| Spring WebFlux | `CorsWebFilter`, WebFlux global CORS | Tương tự nhưng reactive |
| Spring Cloud Gateway | `globalcors`, route metadata `cors`, `DedupeResponseHeader` | Gateway và service cùng phát header |
| NGINX/Ingress/CDN | `add_header`, `more_set_headers`, CORS middleware | Thêm trùng upstream hoặc chỉ thêm trên 2xx |
| Error handler | 401/403/404/5xx tự dựng | Response lỗi thiếu policy CORS hoặc bị policy khác |

Không phải mọi sản phẩm gateway có cùng cách merge/replace headers. Chỉ dựa vào một bảng cấu hình mà chưa xem response trên mạng là chưa đủ.

## 7. Quy tắc kiến trúc: một chủ sở hữu policy cho mỗi public API boundary

Chọn **một chiến lược ownership**, ghi lại trong tài liệu triển khai và test được:

| Kiến trúc | Owner đề xuất | Điều kiện để vận hành đúng |
| --- | --- | --- |
| Một Spring Boot API, reverse proxy chỉ chuyển tiếp | Spring backend (Security + một nguồn CORS) | Proxy/CDN **không thêm** `Access-Control-Allow-*` |
| Nhiều microservices chung một public API gateway | Gateway | Các backend không tự ghi CORS headers cho public routes hoặc gateway kiểm soát loại bỏ upstream policy theo thiết kế |
| Gateway làm auth, trả 401/403 trước khi gọi service | Thường gateway | Các error responses của gateway cũng cần CORS phù hợp |
| Các service có chính sách origin khác nhau | Gateway per-route **hoặc** backend per-service | Không để cả hai cùng phát; có hợp đồng rõ cho từng route |
| Public asset/static CDN khác API | Owner độc lập theo resource/domain | Không trộn static asset headers với private API policy |
| Backend có internal API không được truy cập bằng browser | Có thể không cần CORS | Authentication/network policy vẫn cần |

“**Một owner**” không nhất thiết đồng nghĩa chỉ có một dòng cấu hình trong cả hệ thống. Nếu Spring Security cần xử lý preflight trước authentication, Security có thể **sử dụng cùng `CorsConfigurationSource`** với ứng dụng; đó là **tích hợp một policy**, không phải hai whitelist độc lập.

Bản contract nên mô tả: public path, danh sách origins, methods, headers, credentials, preflight owner, error-response behavior, cache variation, service nào không được thêm header và trách nhiệm rollback. Nếu app có đường truy cập trực tiếp khác gateway, phải xem chính sách cho đường truy cập ấy riêng — không suy rằng gateway có thể bảo vệ một backend đang lộ Internet.

## 8. Preflight cần đi trước Spring Security authentication

Tài liệu Spring Security nêu rõ: CORS nên được xử lý **trước Spring Security authorization** vì preflight thường **không có cookie phiên** như `JSESSIONID`. Nếu một request preflight bị xem là unauthenticated, security chain có thể trả 401/403 trước khi CORS processor cấp permission cho origin hợp lệ.

Ví dụ triệu chứng:

```text
OPTIONS /api/orders
Origin: https://ui.example.test
Access-Control-Request-Method: POST

HTTP 401 / 403
Access-Control-Allow-Origin: [không có]
```

Browser chỉ hiển thị CORS error, gây cảm giác backend “bị lỗi CORS” dù nguyên nhân sớm nhất là **filter order/auth rule**. Không sửa bằng cách `permitAll()` cho mọi `/api/**` hoặc tắt toàn bộ Spring Security.

Trong Spring Security hiện đại, API cấu hình thường là:

```java
http.cors(Customizer.withDefaults());
```

Khi có **một** `UrlBasedCorsConfigurationSource` phù hợp, Security có thể tích hợp từ nguồn đó. Nếu đã dùng Spring MVC CORS mappings và **không khai báo `CorsConfigurationSource` riêng**, Security có thể tái sử dụng MVC CORS configuration với `.cors(withDefaults())`. Hai lựa chọn được trình bày tách biệt bên dưới.

**Quan trọng:** Khi hệ thống có nhiều `CorsConfigurationSource` beans hoặc nhiều `SecurityFilterChain`, auto selection có thể không xác định được đúng nguồn cho mỗi chain; lúc đó khai báo `cors.configurationSource(...)` tường minh theo chain thay vì chờ framework đoán.

## 9. Phương án A: backend Spring Boot là owner, gateway chỉ chuyển tiếp

Đây là phương án phù hợp khi một API có chính sách riêng, gateway chỉ route/TLS/auth phía ngoài và **không đặt `Access-Control-Allow-*`**. Chọn đúng **một** nguồn `UrlBasedCorsConfigurationSource` và cho Spring Security dùng nguồn ấy.

### 9.1. Project Spring Boot MVC + Security có thể chạy

Ví dụ sử dụng **Spring Boot 3.3.13, Java 21** và Gradle Wrapper. Mã đặt thống nhất trong package `com.example.cors`.

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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

**`src/main/java/com/example/cors/CorsApplication.java`:**

```java
package com.example.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsApplication.class, args);
    }
}
```

**`src/main/java/com/example/cors/ApiController.java`:**

```java
package com.example.cors;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    @GetMapping("/api/ping")
    public ResponseEntity<String> ping() {
        return ResponseEntity.ok()
                .header("X-Request-Id", "demo-123")
                .body("pong");
    }
}
```

Controller **không đặt `@CrossOrigin`**; CORS owner nằm ở cấu hình tập trung bên dưới.

**`src/main/java/com/example/cors/SecurityConfiguration.java`:**

```java
package com.example.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of("https://ui.example.test"));
        config.setAllowedMethods(List.of("GET"));
        config.setAllowedHeaders(
                List.of("Authorization", "Content-Type", "X-Request-Id"));
        config.setExposedHeaders(List.of("X-Request-Id"));
        config.setMaxAge(1800L);
        config.setAllowCredentials(false);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return source;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) throws Exception {

        http
                .cors(cors -> cors.configurationSource(corsSource))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/ping")
                        .permitAll()
                        .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Đặc điểm của ví dụ:

- **Một** `UrlBasedCorsConfigurationSource` định nghĩa allowlist, và Security `.cors(...)` sử dụng chính nguồn ấy.
- Chỉ `https://ui.example.test` được phép CORS cho `/api/**`; không dùng `allowedOrigins("*")`.
- Đường dẫn demo là public GET `/api/ping`; những API khác vẫn được bảo vệ bởi security chain. CORS không thay thế việc bảo vệ chúng.
- Không bật cookies cross-origin: `allowCredentials(false)`. Nếu hệ thống thực sự dùng cookie/session, cấu hình credentials phải được thiết kế riêng cùng CSRF và SameSite/Secure.
- `Access-Control-Expose-Headers: X-Request-Id` giúp JavaScript đọc response header đó (nếu origin được cho phép).
- Không thêm `CorsFilter` bean thứ hai, không thêm `WebMvcConfigurer.addCorsMappings`, không trang trí controller bằng `@CrossOrigin`, và **không** để gateway thêm ACAO.

**`src/main/resources/application.properties`:**

```properties
server.port=8080
server.address=127.0.0.1
```

Cấu hình chỉ nghe loopback để thử trên máy phát triển. Production phải có authentication, network controls và TLS phù hợp. URL `ui.example.test` chỉ là **origin mô phỏng dùng trong header**, không đòi hỏi DNS này phải chạy thật để kiểm tra bằng curl.

### 9.2. Khởi chạy và kiểm tra preflight

Từ thư mục dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

Từ terminal khác:

```bash
curl -i -X OPTIONS \
  -H 'Origin: https://ui.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization' \
  http://127.0.0.1:8080/api/ping
```

Khi Spring Security CORS xử lý đúng, response preflight **thành công ở lớp CORS**, thường 200, có **một**:

```http
Access-Control-Allow-Origin: https://ui.example.test
```

Và một danh sách allowed methods/headers cho phép GET và `Authorization`. Các header như `Vary`, `Access-Control-Max-Age` và status formatting tùy bản Spring/container; không xem toàn bộ HTTP response là stdout cố định.

Request actual:

```bash
curl -i \
  -H 'Origin: https://ui.example.test' \
  http://127.0.0.1:8080/api/ping
```

Body thành công **chính xác**:

```text
pong
```

Response có một ACAO cho origin hợp lệ và `X-Request-Id: demo-123`. So sánh với origin không thuộc allowlist:

```bash
curl -i -X OPTIONS \
  -H 'Origin: https://untrusted.example' \
  -H 'Access-Control-Request-Method: GET' \
  http://127.0.0.1:8080/api/ping
```

Trong Spring CORS processor thông thường, preflight origin không hợp lệ bị từ chối, thường trả 403; **không** nên có `Access-Control-Allow-Origin` cấp quyền cho origin này. Nếu đi qua gateway/security customizations, status thực tế có thể khác, nhưng **không được cấp quyền cho origin không thuộc policy**.

### 9.3. Vì sao ví dụ vẫn có Spring Security nhưng không tạo hai owner?

Spring Security nằm trong filter chain nên được dùng để **điều phối CORS trước authn/authz**. `UrlBasedCorsConfigurationSource` là nơi định nghĩa policy, được đưa thẳng vào `.cors(...)`. Không có một tập origins riêng thứ hai của MVC hay gateway để mâu thuẫn. Security/CORS filter và controller có những trách nhiệm tách biệt.

Ví dụ dùng `.httpBasic(...)` chỉ để có cơ chế authn mặc định cho endpoint không public; không phải hướng dẫn triển khai session/cookie cross-origin. Nếu API thật dùng bearer token, JWT hoặc OAuth2 Resource Server, cần cấu hình authentication tương ứng — **không thay CORS policy để làm auth chạy**.

## 10. Phương án B: Spring MVC giữ policy, Spring Security dùng chung MVC

Nếu dự án đã sử dụng `WebMvcConfigurer.addCorsMappings`, cũng có thể giữ **MVC là nguồn policy** thay vì tạo bean `CorsConfigurationSource` riêng.

Ví dụ **thay thế** cấu hình CORS của mục 9 (không cài cả hai vào cùng sample):

**`MvcCorsPolicy.java` — mẫu tích hợp:**

```java
package com.example.cors;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
public class MvcCorsPolicy implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
                .allowedOrigins("https://ui.example.test")
                .allowedMethods("GET")
                .allowedHeaders("Authorization", "Content-Type")
                .exposedHeaders("X-Request-Id")
                .maxAge(1800);
    }
}
```

Trong security configuration của **phương án B**, dùng:

```java
// Thay cho .cors(cors -> cors.configurationSource(corsSource))
// khi không có CorsConfigurationSource riêng:
http.cors(Customizer.withDefaults());
```

Để chạy phương án B hoàn chỉnh, bỏ bean `corsConfigurationSource()` ở phương án A và thay method `securityFilterChain` cho phù hợp (không injection `UrlBasedCorsConfigurationSource`). Spring Security trong mô hình MVC có thể lấy cùng policy do Spring MVC cung cấp khi không có `CorsConfigurationSource` tùy chỉnh.

**Không có nghĩa** rằng `WebMvcConfigurer` + `.cors(withDefaults())` tự sinh hai ACAO: chúng là một cơ chế **tích hợp** được Spring Security hỗ trợ. Nhưng nếu tiếp tục thêm một `CorsFilter` bean hoặc `@CrossOrigin(origins = "*")` tùy tiện trên controller, policy có thể bị nới rộng, mơ hồ hoặc phải xử lý ở nhiều tầng.

`@CrossOrigin` có thể cần cho một endpoint ngoại lệ, nhưng nên được quy định rõ trong kiến trúc và test xem nó **kết hợp** với global CORS như thế nào. Không khuyến khích rải annotation tại hàng chục controllers mà không có chính sách bao trùm.

## 11. `@CrossOrigin` và global MVC: vì sao kết hợp có thể mở quyền quá rộng?

Spring MVC hỗ trợ CORS ở mức global và local:

```java
// Ví dụ minh họa, KHÔNG thêm vào sample phương án A/B khi chưa có chủ đích.
@CrossOrigin(origins = "https://partner.example.test")
@GetMapping("/api/ping")
public String pingForPartner() {
    return "pong";
}
```

Nếu global MVC cũng cho `https://ui.example.test`, Spring Framework sẽ kết hợp local/global CORS configuration theo quy tắc của `CorsConfiguration.combine(...)`. Với các danh sách như origins, kết quả thường **cộng dồn** origins; không phải local override toàn bộ allowlist. Với thuộc tính đơn, ví dụ `allowCredentials` và `maxAge`, local có thể override global.

Hệ quả:

- Người viết local annotation nghĩ mình “chỉ cho partner”, nhưng global vẫn cho UI, nên tập origin thực tế rộng hơn.
- Một annotation `@CrossOrigin` không khai origins cụ thể có default rộng hơn mong muốn trong một số tình huống.
- Khi đổi chính sách toàn cục, cần kiểm tra local exceptions để biết effective policy; không thể đọc riêng một dòng global rồi kết luận đủ.
- Việc có hai nguồn **không tự tương đương hai header trùng**. Phân biệt **policy merge trong cùng Spring** với **header append tại nhiều HTTP hops**.

Nếu cần ngoại lệ rõ ràng, mô tả per-route/per-handler policy thành một nguồn duy nhất, có test cho cả origin hợp lệ và origin bị từ chối. Với microservices, gateway per-route hoặc backend policy per-service có thể phù hợp hơn việc rải local annotations khó kiểm soát.

## 12. Phương án C: Spring Cloud Gateway là CORS owner

Khi nhiều services được công bố dưới **một public gateway**, gateway thường là nơi hợp lý để cung cấp thống nhất CORS headers. Khi chọn phương án này, backend **không thêm ACAO/ACAC cho public routes**, hoặc gateway phải có cơ chế loại bỏ upstream headers nhất quán đã được kiểm thử. Security bên backend vẫn làm authentication/authorization cho **actual requests**.

Ví dụ Spring Cloud Gateway **Reactive Server 4.1.x** — đây là **cấu hình gateway riêng**, không dán vào project MVC mẫu mục 9:

**`application.yml` của gateway:**

```yaml
server:
  port: 8081

spring:
  cloud:
    gateway:
      globalcors:
        add-to-simple-url-handler-mapping: true
        cors-configurations:
          '[/**]':
            allowedOrigins:
              - "https://ui.example.test"
            allowedMethods:
              - GET
              - POST
              - OPTIONS
            allowedHeaders:
              - Authorization
              - Content-Type
              - X-Request-Id
            maxAge: 1800

      routes:
        - id: api
          uri: http://127.0.0.1:8080
          predicates:
            - Path=/api/**
```

Trong ví dụ này:

- Gateway lắng nghe 8081 và chuyển `/api/**` tới backend 8080; URI/backend host chỉ phù hợp demo **trên cùng máy**, không phải cấu hình Docker/Kubernetes dùng nguyên trạng.
- `globalcors.cors-configurations` khai CORS policy theo URL patterns của **gateway**.
- `add-to-simple-url-handler-mapping=true` hỗ trợ preflight khi route predicates không chọn route (ví dụ predicate theo HTTP method không match OPTIONS).
- Không thêm `@CrossOrigin`, `WebMvcConfigurer` hoặc service-side CORS filter cho cùng public boundary; đảm bảo backend không phát CORS headers trùng.
- Chọn allowed methods/headers thực sự phục vụ API, không mở `*` vô điều kiện. Tên `OPTIONS` có trong list là một lựa chọn minh họa; quyền cho actual method vẫn phải đúng.
- Ở gateway có nhiều routes khác policy, dùng route-level CORS metadata hoặc các URL patterns cụ thể thay cho một wildcard rộng cho mọi API.

Trong Spring Cloud Gateway, **route metadata `cors`** còn cho phép chính sách riêng theo route. Không khai `globalcors` và metadata per-route mâu thuẫn rồi trông chờ framework tự suy ý định. Nếu cần cả hai, phải hiểu chính xác phép kết hợp của phiên bản đang dùng và kiểm thử bằng public request.

**Quan trọng với security:** Khi gateway sở hữu CORS, preflight phải được xử lý trước thành phần authentication/gateway filter từ chối OPTIONS. Nếu có Spring Security **trên chính gateway**, nó cũng cần cho preflight hợp lệ đi qua đúng CORS handler/filter. Cấu hình Gateway globalcors không tự bảo đảm một custom filter hoặc edge WAF trước gateway sẽ không chặn OPTIONS.

## 13. `DedupeResponseHeader` của Gateway: cứu hộ, không phải kiến trúc dài hạn

Spring Cloud Gateway 4.1 có `DedupeResponseHeader` filter, dùng khi cả gateway và downstream đều thêm các headers như `Access-Control-Allow-Origin` và `Access-Control-Allow-Credentials`.

**Ví dụ minh họa trong route configuration:**

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: api
          uri: http://127.0.0.1:8080
          predicates:
            - Path=/api/**
          filters:
            - DedupeResponseHeader=Access-Control-Allow-Credentials Access-Control-Allow-Origin
```

Nếu filter được dùng, có thể loại các **giá trị bị lặp**. Filter hỗ trợ strategies:

- `RETAIN_FIRST` (mặc định).
- `RETAIN_LAST`.
- `RETAIN_UNIQUE`.

**Không tự cho rằng dedupe tạo policy đúng**. Ví dụ backend trả `Access-Control-Allow-Origin: https://service.example` trong khi gateway trả `https://ui.example.test`; giữ first hay last có thể lựa chọn **sai origin**, dù response bây giờ chỉ một giá trị. Dedupe cũng không sửa mọi lỗi như `Access-Control-Allow-Headers` thiếu, redirect preflight, credential mismatch hoặc cache policy sai.

Khi dùng filter, phải hiểu thứ tự response filters và origin policy của từng lớp, kiểm thử cả 200, 401, 403, 404, 500. Tốt nhất là **xóa nguồn sinh header thứ hai** và chỉ dùng dedupe như biện pháp chuyển tiếp/compatibility trong lúc di dời CORS ownership.

## 14. NGINX/Ingress/CDN: không “tiện tay” thêm header nếu backend đã là owner

Một cấu hình rất dễ gây duplicate:

```nginx
# Anti-pattern khi Spring backend đã tự trả Access-Control-Allow-Origin:
location /api/ {
    proxy_pass http://127.0.0.1:8080;
    add_header Access-Control-Allow-Origin "https://ui.example.test" always;
}
```

Nếu backend Spring đã phát ACAO, NGINX `add_header` có thể **thêm** một header nữa vào response cuối. `always` chỉ ảnh hưởng phạm vi response status mà header được thêm; nó **không** có nghĩa “thêm nếu chưa có”.

Nếu chọn **backend owner**, proxy nên chỉ route request, không ghi `Access-Control-Allow-*` và không ghi đè `Vary` cần thiết:

```nginx
# Minh họa location chuyển tiếp, không phải cấu hình TLS/production đầy đủ.
location /api/ {
    proxy_pass http://127.0.0.1:8080;
    # Không add_header Access-Control-Allow-* ở đây.
}
```

Nếu chọn **NGINX owner**, phải thiết kế đầy đủ preflight, actual responses, allowlist origin, credentials, allowed headers/methods, error responses, `Vary` và xử lý upstream CORS headers. Không chỉ thêm mỗi `Access-Control-Allow-Origin` vào response 200 rồi coi đã hoàn tất CORS. Khi nhiều origins được phép, phản chiếu nguyên `Origin` mà không allowlist là một lỗi bảo mật.

Đặc biệt với ingress controllers, CORS có thể được bật bằng annotations hoặc middleware ở **cấp ingress** trong khi app cũng bật. Kiểm tra effective ingress configuration, CDN edge rules, WAF response headers và các inherited NGINX `add_header` ở nhiều scopes.

Nếu gateway là owner và backend còn phát headers, cần **một kế hoạch loại bỏ upstream CORS headers** hoặc di dời policy, không dùng header append như một lớp phủ tùy ý.

## 15. Preflight có thể kết thúc ở gateway và không đến ứng dụng

Một `OPTIONS` request **không nhất thiết tới Spring Boot service**:

```text
Browser OPTIONS
    |
    +--> CDN/WAF từ chối       -> response do edge tạo
    +--> Gateway xử lý CORS    -> response do gateway tạo
    +--> Gateway route OPTIONS -> Spring Security CORS / MVC
```

Điều này giải thích tình huống developer đặt breakpoint trong controller mà không thấy preflight, rồi suy rằng browser “không gửi request”. Muốn biết request ở đâu, quan sát **network trace theo từng hop** và gateway access logs, không chỉ controller logs.

Với gateway làm owner, nên chủ động trả một preflight hợp lệ cho allowlisted origin/method/header ngay tại gateway. Actual request vẫn phải đi qua authentication/authorization. Với backend owner, gateway phải cho OPTIONS đi tới backend CORS processor, đồng thời tránh tạo response lỗi không có CORS headers khi browser cần đọc lỗi.

Nếu gateway trả 401/403 **trước backend**, backend owner không thể tự thêm ACAO cho response ấy. Cần quyết định lại ranh giới CORS (ví dụ chuyển owner ra gateway cho public path) hoặc bố trí error-response handling ở edge nhất quán. Không khắc phục bằng cách thêm một ACAO cố định cho mọi response lỗi, kể cả origin không được phép.

## 16. Thứ tự filter trong Spring Security và nhiều `SecurityFilterChain`

Spring Security thực thi filter chain trước controller. CORS cần được xử lý đúng thứ tự để preflight không bị block chỉ vì không có cookie/token. Với một `SecurityFilterChain`, ví dụ mục 9 đã dùng:

```java
http.cors(cors -> cors.configurationSource(corsSource));
```

Trong hệ thống có nhiều chains, ví dụ `/api/admin/**` và `/api/public/**`, cần xác định:

1. Chain nào match preflight và actual request?
2. Chain đó có CORS config và source phù hợp không?
3. Allowed origin/method/headers có khác giữa hai đường dẫn không?
4. Preflight có bị một chain khác bắt trước và trả 401/403?
5. Gateway có áp dụng CORS cho route cả khi preflight không match method predicate không?

Một `CorsConfigurationSource` bean toàn cục không mặc nhiên giải quyết mọi tổ hợp nhiều chains nếu app cấu hình Security thủ công. Với nhiều nguồn, hãy truyền source **tường minh** cho `.cors(...)` của từng chain, hoặc thiết kế nguồn tập trung route-aware.

**Không làm theo phản xạ:**

```java
// Không phải giải pháp an toàn cho preflight:
http.authorizeHttpRequests(auth -> auth.anyRequest().permitAll());
```

Tắt authorization trên toàn API chỉ để không thấy 401 là sai ranh giới bảo mật. Cần phân biệt **CORS preflight permission** với quyền thực hiện GET/POST/DELETE của một user đã xác thực.

Nếu app chạy sau gateway có identity forwarding, Security và gateway vẫn phải có hợp đồng tin cậy; CORS không xác nhận danh tính người dùng hoặc tính đúng đắn của token.

## 17. `allowCredentials(true)`, wildcard origins và cookies

Khi JavaScript gửi cross-origin request với credentials mode `"include"` (ví dụ cookie phiên), browser đòi response phù hợp:

```http
Access-Control-Allow-Origin: https://ui.example.test
Access-Control-Allow-Credentials: true
```

Không dùng:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Browser không cho phép wildcard ACAO trong credentialed CORS. Ở Spring Framework, khi bật `allowCredentials(true)`, `allowedOrigins` phải liệt kê origins cụ thể, **không** là `"*"`. Có thể dùng `allowedOriginPatterns` khi thực sự cần pattern, nhưng phải rất cẩn thận với domain wildcard, subdomain takeover và partner domains; framework có thể echo lại origin phù hợp thay vì `*`.

**CORS credentials khác CSRF:** Nếu dùng session cookie, cookie vẫn cần cấu hình `SameSite`, `Secure`, `HttpOnly`, HTTPS và CSRF protections thích hợp. Preflight không mang cookie phiên không có nghĩa actual unsafe request đã an toàn. CORS không ngăn mọi kiểu form POST hoặc điều kiện CSRF.

Nếu API dùng bearer token trong `Authorization` header, browser có thể phát preflight do header này không safelisted. `allowedHeaders` phải cho `Authorization`, nhưng không được nhầm điều đó với việc tin mọi token hoặc mở toàn bộ resources cho mọi origin.

Không tùy tiện `allowCredentials(true)` “để hết lỗi” nếu API không dùng credentialed browser requests. Bật quyền không cần thiết làm trust surface rộng hơn.

## 18. Error responses cũng cần chính sách CORS nhất quán

Không chỉ test HTTP 200:

| Response | Ai thường tạo? | Rủi ro CORS |
| --- | --- | --- |
| 200/201/204 | Controller hoặc gateway | Duplicate ACAO vì nhiều layers |
| 301/302/307 | Proxy, login redirect, Spring Security | Redirect preflight hoặc chuyển sang origin/scheme khác |
| 400/404 | MVC validation/error handler, gateway | Response không đi qua cùng CORS path |
| 401/403 | Gateway auth, Spring Security | Preflight bị chặn hoặc actual error không có ACAO |
| 413 | NGINX/body-size limit | Backend chưa hề nhận request để thêm header |
| 429 | WAF/rate limiter | Response từ edge không có CORS policy |
| 500/502/503 | App hoặc gateway upstream error | Header khác nhau giữa lỗi application và lỗi edge |

Browser không thể đọc chi tiết error body nếu response không có CORS headers phù hợp. Vì vậy “server báo 401 nhưng DevTools chỉ hiện CORS” có thể là **hai vấn đề liên tiếp**, không phải tự động lỗi một nơi.

Nếu gateway là owner, kiểm tra gateway áp dụng CORS cho allowed origins ngay cả trên error responses mà gateway **tự tạo**, trong phạm vi an toàn. Nếu backend là owner nhưng edge/WAF chặn trước, cần quyết định cách báo lỗi mà không tạo policy CORS thứ hai mâu thuẫn; đôi khi chính kiến trúc đòi chuyển policy ownership ra edge.

Với requests từ origins **không được phép**, việc thiếu ACAO và browser từ chối đọc body là hành vi mong muốn, không phải lỗi cần “vá” bằng wildcard.

## 19. Caching, `Vary` và preflight `Access-Control-Max-Age`

Caching có thể làm policy đúng ở origin A nhưng sai khi dùng origin B:

```text
Origin A -> Gateway responds ACAO:A -> CDN caches by URL only
Origin B -> CDN returns cached ACAO:A -> Browser B rejects
```

Nếu server trả origin động theo allowlist, response thường cần:

```http
Vary: Origin
```

Preflight còn có inputs:

```http
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

Nên cache key/policy phải phân biệt những yếu tố có thể làm thay đổi response. Spring CORS thường thêm các trường `Vary` liên quan; hãy xác minh CDN/gateway **không loại hoặc ghi đè** chúng.

`Access-Control-Max-Age` là thời gian browser **có thể cache kết quả preflight**, chịu giới hạn của browser, không đồng nhất với `Cache-Control: max-age` của actual API response. Khi thay đổi chính sách origins, preflight cũ có thể còn được browser giữ trong thời gian cho phép; kiểm thử chính sách mới nên xem xét cache hoặc dùng môi trường/profile sạch.

**Không dùng `Access-Control-Allow-Origin: *` chỉ để làm cache đơn giản** cho API riêng tư. Với một API công khai không credentials, wildcard có thể hợp lệ, nhưng phải là quyết định chủ động và độc lập với authz.

## 20. Cách chẩn đoán header trùng theo từng hop

Trước khi sửa code, thu thập **hai response** với cùng `Origin`, method và URL path tương ứng:

```text
A. Truy cập backend trực tiếp qua cổng nội bộ (trong mạng test).
B. Truy cập public URL qua gateway/ingress/CDN.
```

**Ví dụ A — kiểm tra backend từ môi trường có quyền:**

```bash
curl -si \
  -H 'Origin: https://ui.example.test' \
  http://127.0.0.1:8080/api/ping
```

**Ví dụ B — kiểm tra public gateway:**

```bash
curl -si \
  -H 'Origin: https://ui.example.test' \
  https://api.example.test/api/ping
```

Nếu A có **một** ACAO nhưng B có **hai**, gateway/CDN/ingress là nghi phạm chính. Nếu A đã có hai, tìm các filters và MVC/Security configurations của service.

Đếm headers trên Unix-like shell (chỉ dùng trong môi trường tin cậy hoặc với URL test):

```bash
curl -si -H 'Origin: https://ui.example.test' \
  https://api.example.test/api/ping \
  | grep -i '^access-control-allow-origin:'
```

Một response CORS hợp lệ cho request từ allowed origin có **một dòng ACAO với một giá trị origin hợp lệ**. Nếu gateway gộp nhiều giá trị vào một dòng, vẫn sai; phải kiểm tra **cả nội dung**, không chỉ số dòng.

Đừng dùng `curl -I` như kiểm chứng duy nhất: nó gửi **HEAD**, trong khi CORS policy/mappings của HEAD có thể khác GET/OPTIONS. Dùng `curl -i` với method và headers tương ứng với browser request.

Nếu HTTP/2 hoặc proxy chuyển đổi header representations, DevTools/`curl -v` vẫn giúp quan sát response trên dây, nhưng thứ tự headers và cách hiển thị có thể khác. Đọc **effective field values**.

## 21. Thử preflight đúng cách: origin, method và headers

Để tái hiện browser preflight:

```bash
curl -i -X OPTIONS \
  -H 'Origin: https://ui.example.test' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: authorization,content-type' \
  https://api.example.test/api/orders
```

Đây là **request thử nghiệm cho API giả định** `/api/orders`, không phải endpoint của sample `/api/ping`. Cần thay bằng route thật và bảo đảm policy cho phép POST nếu nghiệp vụ cần.

Quan sát:

1. Request có thực sự đến gateway? Đến backend không?
2. `Access-Control-Allow-Origin` có chính xác một giá trị khớp request origin không?
3. Allowed methods có cho **POST** không?
4. Allowed headers có cho **Authorization** và **Content-Type** không?
5. Preflight có bị 301/302 tới login hoặc 401/403 trước xử lý CORS không?
6. Có `Access-Control-Allow-Credentials: true` nếu browser thực sự dùng credentials mode include không?
7. Có `Vary` và `Access-Control-Max-Age` phù hợp với cache không?
8. Actual request **sau đó** có được phép thực hiện bởi Security/business logic không?

`OPTIONS` không phải lúc nào cần khai thành controller method riêng. Trong MVC/Security đã cấu hình CORS đúng, CORS processor có thể xử lý preflight trước controller. Nếu tự tạo `@RequestMapping(method=OPTIONS)` và gửi headers thủ công, có nguy cơ tạo một policy khác, làm sai method/path matching và Security filter order.

## 22. Automated integration test xác minh response không trùng header

Với sample Spring Boot từ mục 9, đã có `spring-boot-starter-test`. Có thể kiểm tra qua HTTP server thật, không chỉ kiểm tra một bean config tồn tại.

**`src/test/java/com/example/cors/CorsHttpTest.java`:**

```java
package com.example.cors;

import static org.assertj.core.api.Assertions.assertThat;

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

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class CorsHttpTest {

    @Autowired
    private TestRestTemplate client;

    @Test
    void preflightGetsExactlyOneAllowedOrigin() {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin("https://ui.example.test");
        headers.add(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET");
        headers.add(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS, "authorization");

        ResponseEntity<String> response = client.exchange(
                "/api/ping",
                HttpMethod.OPTIONS,
                new HttpEntity<>(headers),
                String.class);

        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
        assertThat(response.getHeaders()
                .get(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .containsExactly("https://ui.example.test");
    }

    @Test
    void actualGetGetsExactlyOneAllowedOrigin() {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin("https://ui.example.test");

        ResponseEntity<String> response = client.exchange(
                "/api/ping",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody()).isEqualTo("pong");
        assertThat(response.getHeaders()
                .get(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN))
                .containsExactly("https://ui.example.test");
    }
}
```

Dòng `import java.util.List;` không cần thiết cho test này và có thể bỏ; nó không làm code biên dịch thất bại. Trong IDE, nên bật kiểm tra unused imports để giữ ví dụ gọn.

Chạy:

```bash
./gradlew test
```

Hai tests phù hợp **phương án A** với route `/api/ping`, cho thấy Spring Security đã xử lý preflight trước authn và actual response phát **đúng một ACAO**. Test không có stdout cố định; kết quả hợp lệ là test PASS.

Tuy vậy test này chỉ đi qua **embedded HTTP server của ứng dụng**. Nó không phát hiện được gateway/CDN thêm header. Phải có **smoke/integration test qua public gateway URL** sau deploy, ví dụ gửi origin A và origin B, thử preflight, actual GET, actual 401/403 và kiểm tra duplicate header ở response cuối.

Nếu test cố dùng `@SpringBootTest` với port random trên một máy đã cố định `server.address=127.0.0.1`, nó vẫn có thể dùng loopback, nhưng môi trường CI/container cần đảm bảo khả năng kết nối localhost trong namespace phù hợp.

## 23. WebFlux và WebFlux Security có cùng bài toán ownership

Trong Spring WebFlux reactive application, CORS có thể được cấu hình bằng:

- `@CrossOrigin` trên reactive controllers.
- WebFlux global mappings thông qua `WebFluxConfigurer.addCorsMappings`.
- `CorsWebFilter` và một `CorsConfigurationSource` phù hợp.
- Spring Security WebFlux CORS integration thông qua `SecurityWebFilterChain`.
- Spring Cloud Gateway Reactive Server phía trước.

Tư tưởng vẫn là **một source/policy owner cho public API boundary**. Nhưng các class servlet như `CorsFilter`, `HttpSecurity`, `SecurityFilterChain`, `HttpServletRequest` của Spring MVC **không thay thế trực tiếp** cho WebFlux `CorsWebFilter`, `ServerHttpSecurity`, `SecurityWebFilterChain` và `ServerWebExchange`.

Ví dụ chỉ để nhận diện API WebFlux, không phải một chương trình độc lập:

```java
// Trích đoạn cấu hình reactive Security; cần project WebFlux riêng.
@Bean
SecurityWebFilterChain reactiveSecurity(ServerHttpSecurity http) {
    return http
            .cors(cors -> { })
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/public/**").permitAll()
                    .anyExchange().authenticated())
            .build();
}
```

Cấu hình `.cors(...)` của WebFlux cần một policy source phù hợp với stack thực và version đang chạy. **Không dùng nguyên snippet để thay SecurityConfig của MVC**; phải tạo/đăng ký reactive CORS policy và kiểm thử preflight.

Khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng có mặt, Spring Boot thường mặc định chọn **Servlet** khi phát hiện web application type. Xác nhận stack thực trước khi tìm bean hay debug CORS filter, tránh cấu hình sai thế giới.

## 24. Checklist code review khi nghi cấu hình trùng

Trong code/backend configuration của **chính service được giao kiểm tra**, tìm những dấu hiệu:

```text
@CrossOrigin
WebMvcConfigurer.addCorsMappings
WebFluxConfigurer.addCorsMappings
CorsConfigurationSource
UrlBasedCorsConfigurationSource
CorsFilter
CorsWebFilter
http.cors(...)
SecurityWebFilterChain / ServerHttpSecurity.cors(...)
HandlerMapping CORS configurations
```

Ở lớp gateway/edge, kiểm tra:

```text
spring.cloud.gateway.globalcors.*
Route metadata cors
DedupeResponseHeader
AddResponseHeader / SetResponseHeader
NGINX add_header Access-Control-Allow-*
Ingress CORS annotations
CDN response header policies
WAF / auth middleware trả preflight hoặc errors
```

Đây là checklist cho maintainer; không nên gộp mọi kết quả match và coi chúng **đều đang active**. Phải xác định runtime profile, condition, security chain, route matching và thực tế filter order. Một class có `@CrossOrigin` nhưng không được scan sẽ không gây tác dụng; một ingress annotation bị override cũng không nhất thiết có mặt trên response.

Hãy tạo một bảng ownership trong tài liệu vận hành:

| Public path | CORS owner | Allowed origins | Preflight xử lý ở đâu? | Error response owner |
| --- | --- | --- | --- | --- |
| `/api/shop/**` | Backend shop | `https://ui.example.test` | Spring Security CORS | Backend; proxy errors phải được thống nhất |
| `/api/admin/**` | Gateway | `https://admin.example.test` | Gateway CORS | Gateway |
| `/assets/**` | CDN | Policy public-asset riêng | CDN nếu cần | CDN |
| Internal `/internal/**` | Không dùng browser CORS | Không cấp CORS public | Không bắt buộc | Internal security |

Bảng là **mẫu kiến trúc**. Nếu một route có hai owners hoặc không ai chịu trách nhiệm error responses, cần chỉnh trước khi release.

## 25. Ma trận kiểm thử tối thiểu

| Tình huống | Điều phải được xác minh |
| --- | --- |
| Preflight từ origin cho phép | Phản hồi 2xx, đúng **một** ACAO, methods/headers đủ |
| Actual GET từ origin cho phép | HTTP business status đúng và một ACAO |
| Origin không được cho phép | Không có CORS permission cấp quyền cho origin đó |
| Browser gửi `Authorization` | Preflight cho phép header; actual request vẫn cần token hợp lệ |
| Cookie-based cross-origin | Explicit origin + ACAC khi cần; CSRF, SameSite, Secure hợp lệ |
| Public endpoint trả 401/403 | Không bị gateway và backend nhân đôi ACAO; browser thấy status theo policy |
| Gateway trả 502/503 | Error path của gateway được xử lý theo CORS owner |
| Nhiều origins trong allowlist | Mỗi response chỉ echo **một** matching origin; `Vary` đúng |
| Preflight POST khi route predicate chỉ GET | Gateway không nuốt OPTIONS sai cách |
| CDN cache bật | Không phục vụ cache ACAO của origin A cho origin B |
| HTTP → HTTPS redirect | Không dẫn preflight sang login/redirect vòng lặp |
| `@CrossOrigin` + MVC global | Effective origins/methods không mở rộng ngoài ý định |
| NGINX/Ingress thêm header | Không nhân đôi upstream CORS hoặc có cơ chế owner rõ |
| Nhiều Security chains | Chain match request/preflight có policy đúng |

Khi browser báo lỗi, giữ lại **Network tab** gồm preflight và actual request (nếu có), status, request headers, response headers, redirect chain; sau đó so sánh với `curl -i`. Không chỉ gửi ảnh Console message rồi sửa CORS một cách phỏng đoán.

## 26. Bảng lỗi phổ biến và cách sửa đúng nguyên nhân

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Sửa đúng tầng |
| --- | --- | --- |
| `Multiple CORS header 'Access-Control-Allow-Origin' not allowed` | Gateway và Spring cùng trả ACAO | Xác định owner, loại policy/header dư; dedupe chỉ tạm |
| ACAO thành `originA, originB` | Backend/proxy gộp hai origins | Không gửi danh sách, chỉ một matching origin |
| `Access-Control-Allow-Origin: *` nhưng credentialed fetch lỗi | Wildcard không hợp lệ với credentials include | Explicit allowed origin + ACAC theo policy |
| Preflight 401 | Spring Security hoặc gateway auth chạy trước CORS | Bố trí CORS preflight đúng thứ tự/owner |
| Preflight 404 | Gateway route predicates không match OPTIONS | SCG `add-to-simple-url-handler-mapping` hoặc route/preflight design |
| Preflight thiếu `Authorization` trong allowed headers | Policy chưa cho header được yêu cầu | Cập nhật allowedHeaders tại **owner**, không khắp ba tầng |
| GET 200 nhưng JavaScript không đọc được | Missing/duplicated/wrong ACAO trên actual response | Inspect public response, so sánh backend vs gateway |
| Only 200 okay, 401/403 blocked | Error do tầng khác tạo, thiếu ACAO | Thiết kế error path theo owner |
| Browser origin A được, B thất bại ngẫu nhiên | Cache response không `Vary: Origin` hoặc CDN config sai | Điều chỉnh `Vary`/cache key ở owner/CDN |
| Preflight thành công, POST bị 403 | CSRF/authz/business policy | Sửa authz/CSRF theo nghiệp vụ, không nới CORS |
| Response có CORS nhưng frontend bị mixed content | HTTPS page gọi HTTP API | Dùng HTTPS public URL, không sửa ACAO để bỏ mixed content |
| Local chạy, production lỗi | Ingress/CDN/gateway thêm CORS hoặc khác profile | So sánh network hops và config hiệu lực |
| `@CrossOrigin` vẫn không có hiệu lực | Security chặn trước hoặc request chưa match handler | Kiểm tra filter chain/path/preflight |
| Nhiều `CorsConfigurationSource` beans | Security không tự chọn đúng bean | Chỉ định `.cors(configurationSource(...))` đúng chain |
| `Access-Control-Expose-Headers` thiếu | JS không đọc được header tùy biến | Expose đúng header tại owner, không đổi ACAO |

**Chú ý:** Một lỗi Console CORS có thể **che nguyên nhân thật** như 502 từ gateway hoặc 401 từ Security. Cần kiểm tra response trên mạng trước khi kết luận policy của controller sai.

## 27. Một lớp bảo vệ thêm: client-side request không nên “tự sửa CORS”

Các giải pháp sai thường được đề xuất:

```javascript
// Sai: Access-Control-Allow-Origin là RESPONSE header do SERVER quyết định.
fetch("/api/orders", {
  headers: {
    "Access-Control-Allow-Origin": "*"
  }
});
```

Đưa `Access-Control-Allow-Origin` vào request từ client **không cho phép** server trả dữ liệu cross-origin; còn có thể khiến browser tạo thêm preflight vì custom request header.

Tương tự, `mode: "no-cors"` không phải cách đọc API cross-origin như bình thường: response bị giới hạn kiểu opaque, JavaScript không thể dùng body/headers như với response được CORS cho phép. Tắt web security trong browser chỉ phục vụ debug bất thường và không phải cách chữa production.

Một frontend có thể cấu hình **same-origin proxy** trong development (Vite/webpack dev server) để tránh cross-origin trong môi trường test; điều đó không chứng minh policy CORS của public deployment đã đúng. Hãy kiểm tra cả URL, scheme, port và config tại production.

CORS là **contract của server đối với browser**; client không thể đơn phương nâng quyền bằng request headers.

## 28. Bài tập tư duy về policy ownership

**Tình huống A — cùng response hai ACAO:** Backend trả ACAO cho UI, gateway cũng dùng `AddResponseHeader`. Browser từ chối. Hãy giải thích vì sao code controller vẫn có thể hoạt động khi gọi bằng `curl` nhưng JS không đọc được; hãy chọn backend hoặc gateway làm owner và sửa một tầng.

**Tình huống B — preflight 401:** Security yêu cầu đăng nhập cho `/api/orders`. Browser gửi OPTIONS không có `JSESSIONID`, gateway forward xuống service và nhận 401. Hãy mô tả cách tích hợp CORS processor trước authn cho request hợp lệ mà **không** vô hiệu hóa authorization của actual POST.

**Tình huống C — `@CrossOrigin` + MVC global:** Global cho UI, local cho partner. Spring MVC combine cho origins theo quy tắc nào? Đây có nhất thiết tạo hai ACAO không? Làm sao kiểm thử effective origin list để tránh mở rộng quyền quá mức?

**Tình huống D — CDN cache:** Hai origins được phép, response echo origin động nhưng CDN cache chỉ theo URL. Điều gì xảy ra khi B nhận ACAO của A? Cần `Vary` và cache-key policy nào?

**Tình huống E — gateway tạo 502:** Backend là CORS owner nhưng không hề nhận request vì gateway gặp lỗi upstream. Browser thấy CORS error thay vì 502 detail. Ownership ở public boundary có cần xem lại không? Làm thế nào bổ sung error handling mà không tạo policy thứ hai?

**Tình huống F — cookie auth:** Frontend dùng `credentials: "include"` và API trả ACAO `*`. Vì sao browser từ chối? Tại sao sửa thành explicit origin mà không kiểm tra CSRF/SameSite vẫn chưa đủ?

**Tình huống G — Spring Cloud Gateway:** Route predicate chỉ match GET, preflight OPTIONS không match. Thuộc tính `globalcors.add-to-simple-url-handler-mapping` giải quyết nhóm tình huống nào và vẫn cần test gì?

## 29. Kết luận và quy tắc triển khai

**Quy tắc dễ nhớ:**

1. **Một public API boundary — một CORS policy owner rõ ràng.**
2. Nếu Spring backend là owner, Spring Security **tích hợp cùng policy** để xử lý preflight trước authentication; gateway không thêm headers thứ hai.
3. Nếu gateway là owner, downstream không phát CORS cho public routes hoặc header stripping được thiết kế rõ; gateway xử lý cả preflight và error responses.
4. Cấu hình global MVC và `@CrossOrigin` có thể **combine** chứ không tự sinh duplicate; vẫn phải kiểm tra effective policy.
5. `DedupeResponseHeader` chỉ giúp gỡ duplication trong chuyển tiếp, **không xác định origin nào đúng** và không thay thế thiết kế ownership.
6. **Một** `Access-Control-Allow-Origin` hợp lệ mỗi response cho allowed origin, không phải danh sách origins hoặc hai giá trị giống nhau.
7. `allowCredentials`, allowed methods/headers, `Vary` và cache phải được kiểm thử tại **public URL**, không chỉ backend port.
8. CORS không phải authentication, authorization hay CSRF; không tắt bảo mật để vượt preflight.
9. Trước khi sửa, thu thập response **theo từng hop**: browser → edge/gateway → backend, so sánh headers và status của preflight **và** actual requests.

**Kết quả mong muốn:** Browser nhận một CORS contract thống nhất, API vẫn được bảo vệ bằng Spring Security/gateway authentication, và chính sách không bị vô tình mở rộng hay làm hỏng bởi những bộ lọc thêm header ở các tầng khác nhau.

### Tài liệu tham khảo chính thức

- Spring Framework — CORS với Spring MVC, global/local combination: https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html
- Spring Security — Servlet CORS integration và preflight: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Cloud Gateway 4.1 — Global/Route CORS: https://docs.spring.io/spring-cloud-gateway/reference/4.1/spring-cloud-gateway/cors-configuration.html
- Spring Cloud Gateway 4.1 — DedupeResponseHeader: https://docs.spring.io/spring-cloud-gateway/reference/4.1/spring-cloud-gateway/gatewayfilter-factories/deduperesponseheader-factory.html
- Spring Framework — WebFlux CORS: https://docs.spring.io/spring-framework/reference/web/webflux-cors.html
- MDN — Multiple Access-Control-Allow-Origin headers not allowed: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS/Errors/CORSMultipleAllowOriginNotAllowed
- MDN — Access-Control-Allow-Origin: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Access-Control-Allow-Origin
- Fetch Standard — CORS protocol: https://fetch.spec.whatwg.org/