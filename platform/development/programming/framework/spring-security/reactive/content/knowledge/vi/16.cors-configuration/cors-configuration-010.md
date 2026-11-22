# Tránh xung đột giữa `CorsWebFilter`, cấu hình WebFlux và Spring Security

## 1. Vấn đề và mục tiêu học tập

Một API xây dựng bằng **Spring WebFlux + Spring Security Reactive** thường được gọi từ frontend ở origin khác. Ví dụ, frontend tại `http://localhost:3000` gọi API ở `http://localhost:8080`. Khi trình duyệt báo **CORS error**, developer có thể thử thêm `@CrossOrigin`, viết `WebFluxConfigurer#addCorsMappings`, đăng ký `CorsWebFilter` hoặc gọi `ServerHttpSecurity.cors(...)`. Các lựa chọn đều có lý do tồn tại, nhưng nếu cùng được bật với chính sách không nhất quán thì kết quả khó dự đoán: preflight `OPTIONS` bị `401`, browser từ chối vì `Access-Control-Allow-Origin` không hợp lệ, chính sách ở controller không có tác dụng, hoặc môi trường production cho phép nhiều origins hơn dự kiến.

**Mục tiêu của bài:** hiểu **ai xử lý CORS, xử lý trước hay sau Spring Security, và policy nào thực sự áp dụng cho một request**. Ta sẽ chọn một cấu hình chủ đạo, trình bày các phương án thay thế *không dùng đồng thời*, sau đó kiểm thử cả origin hợp lệ lẫn origin bị cấm.

Kết thúc bài, bạn có thể:

- Phân biệt CORS với authentication, authorization và CSRF.
- Hiểu request **preflight** và thứ tự filter bắt buộc trong ứng dụng có Security.
- So sánh `CorsWebFilter`, cấu hình CORS của Spring WebFlux (`WebFluxConfigurer`, `@CrossOrigin`) và `ServerHttpSecurity.cors(...)`.
- Dùng một `CorsConfigurationSource` Reactive nhất quán, không vô tình tạo nhiều CORS filters.
- Xử lý các lỗi do cookie, origin, header, method, nhiều security chains hoặc reverse proxy/gateway.
- Viết ví dụ chạy được trên **Java 17+, Spring Boot 3.x, Spring Security 6.x**, cùng test `WebTestClient`.

> **Phạm vi:** Spring **WebFlux Reactive**, không phải Spring MVC/Servlet. Các import cần nhớ là `org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource`, `org.springframework.web.cors.reactive.CorsWebFilter`, `ServerHttpSecurity` và `SecurityWebFilterChain`. Không chép sang WebFlux các API Servlet như `HttpSecurity`, `CorsFilter` trong `org.springframework.web.filter`, hoặc `org.springframework.web.cors.UrlBasedCorsConfigurationSource` không có `.reactive`.

## 2. Origin, preflight và actual request

**Origin** gồm *scheme + host + port*, không gồm path:

```text
http://localhost:3000         (frontend A)
http://localhost:8080         (backend: origin khác)
http://localhost:4200         (frontend B: origin khác)
https://localhost:3000        (khác scheme)
https://app.example.com       (origin production)
```

Vì vậy `http://localhost:3000/app` và `http://localhost:3000/admin` là **cùng origin**, còn `https://app.example.com` và `https://www.app.example.com` khác origin.

CORS (**Cross-Origin Resource Sharing**) là hợp đồng browser kiểm tra trước khi cho JavaScript đọc/sử dụng một cross-origin response. Server có thể trả:

- `Access-Control-Allow-Origin`: origin được phép.
- `Access-Control-Allow-Methods`: method được phép trong preflight.
- `Access-Control-Allow-Headers`: request headers được phép.
- `Access-Control-Allow-Credentials`: dùng với request có credentials theo Fetch mode.
- `Access-Control-Expose-Headers`: một số response headers bổ sung JavaScript có thể đọc.
- `Access-Control-Max-Age`: thời gian browser cache kết quả preflight.
- `Vary`: để proxy/cache phân biệt response theo origin và preflight metadata thích hợp.

**CORS không xác thực danh tính.** Một origin được cho phép vẫn phải có password, session hoặc bearer token nếu endpoint protected. `curl`, service-to-service clients và Postman thường không cưỡng chế browser CORS policy; lệnh `curl` đọc được body **không chứng minh** website frontend có thể đọc body.

### Request có header Authorization thường cần preflight

Khi frontend muốn gọi:

```http
GET /api/me HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Authorization: Basic ...
```

browser thường gửi request kiểm tra trước:

```http
OPTIONS /api/me HTTP/1.1
Host: localhost:8080
Origin: http://localhost:3000
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Request OPTIONS này **không mang cookie/credentials của actual request theo cách server có thể dùng để bắt login**. Nếu Security bắt authenticate trước khi CORS được xử lý, request có thể nhận `401 Unauthorized`, `WWW-Authenticate`, hoặc redirect tới login; browser chặn ngay và actual GET không diễn ra.

Một preflight thành công có thể trả:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:3000
Access-Control-Allow-Methods: GET,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Max-Age: 1800
Vary: Origin
```

Đây là ví dụ logic; Spring có thể trả headers theo thứ tự/chữ hoa khác, hoặc bổ sung `Vary: Access-Control-Request-Method` và `Vary: Access-Control-Request-Headers`. Test nên kiểm tra **giá trị hợp đồng**, không cứng nhắc về thứ tự serialization.

**Cốt lõi:** CORS phải được kiểm tra **trước Spring Security authentication/authorization** đối với preflight. Tài liệu chính thức của Spring Security Reactive khuyến nghị cơ chế `CorsWebFilter` ở đúng thứ tự.

## 3. Nơi CORS có thể được cấu hình trong ứng dụng WebFlux

| Cơ chế | Hoạt động ở đâu? | Phù hợp khi | Điểm cần chú ý |
| --- | --- | --- | --- |
| `WebFluxConfigurer#addCorsMappings` | `HandlerMapping` của WebFlux | Quy tắc CORS theo route/controller | Một WebFilter bảo mật đứng trước có thể chặn preflight trước khi HandlerMapping làm việc |
| `@CrossOrigin` | Handler/controller | Quyền cross-origin cục bộ | Có thể **kết hợp cộng dồn** với global HandlerMapping config, gây mở rộng origins |
| Bean `CorsWebFilter` | Top-level WebFlux `WebFilter` | Cần CORS chạy sớm, bao gồm functional endpoints | Phải đặt trước security và tránh thêm filter CORS trùng lặp |
| `ServerHttpSecurity.cors(...)` | Bên trong security filter chain | Ứng dụng WebFlux có Spring Security | Dùng `CorsConfigurationSource` Reactive; không trùng policy với top-level filter |
| API Gateway / ingress / CDN | Trước service | Chính sách tập trung nhiều services | Gateway và backend cùng set headers có thể gây response lỗi |

Không có quy tắc “mọi nơi trừ X đều bị cấm”. **Tránh xung đột** nghĩa là chọn một nơi chịu trách nhiệm chính cho policy của từng đường request, biết nơi nào xử lý preflight, và không có các rule mâu thuẫn.

### `WebFluxConfigurer` và `@CrossOrigin`: cấu hình có thể được hợp nhất

Spring WebFlux hỗ trợ CORS tại `HandlerMapping`; một `@CrossOrigin` trên controller có thể được **kết hợp** với global mappings. Các trường đa giá trị như origin/method/header thường được hợp nhất theo quy tắc cộng dồn; các trường đơn trị như `allowCredentials` và `maxAge` có quy tắc override.

Ví dụ nếu cấu hình global cho `https://portal.example.com` và một controller có `@CrossOrigin(origins="https://preview.example.com")`, đừng mặc định chỉ preview được phép: sau khi kết hợp có thể **cả hai** origins được phép tại controller đó.

Đây khác với trường hợp **hai CORS WebFilters** ở các vị trí khác nhau. Khi có hai filter, filter chạy trước có thể chặn request hoặc hoàn thành preflight, khiến filter khác không còn cơ hội áp policy. Không có bảo đảm “cả hai luôn ghi hai header”; kết quả tùy thứ tự và matcher. Chính sự phụ thuộc này làm việc debug khó.

### `ServerHttpSecurity.CorsSpec` làm gì?

Spring Security 6.x cho phép:

```java
.cors(cors -> cors.configurationSource(source))
```

với `source` là `org.springframework.web.cors.reactive.CorsConfigurationSource`. Theo Javadoc Spring Security 6.5, cấu hình này tích hợp CORS ở đúng thứ tự; khi không có source thì không tự sinh danh sách origins hợp lệ. Một bean `CorsConfigurationSource` phù hợp có thể được tự sử dụng; chỉ định tường minh bằng `configurationSource(...)` làm đường đi dễ hiểu hơn.

Ngược lại:

```java
.cors(cors -> cors.disable())
```

nghĩa là **không bật CORS integration trong security chain**, không phải một lệnh thay đổi quy tắc trình duyệt. Nó chỉ phù hợp khi CORS đã có một owner khác được xác định rõ ràng (ví dụ một `CorsWebFilter` độc lập đứng trước security), hoặc khi sản phẩm cố tình không cần cross-origin support.

## 4. Các xung đột điển hình

### 4.1. Cùng đăng ký filter CORS độc lập và bật CORS trong Security

Giả sử hệ thống có bean `CorsWebFilter` với origins A nhưng Security lại gắn một `CorsConfigurationSource` origins B:

```java
// Minh họa cấu trúc dễ mâu thuẫn, KHÔNG dùng trong demo chính:
@Bean
CorsWebFilter corsWebFilter(CorsConfigurationSource sourceA) {
    return new CorsWebFilter(sourceA);
}

// Ở một security chain khác:
http.cors(cors -> cors.configurationSource(sourceB));
```

**Vấn đề:** cùng request có thể chịu hai policy, và filter được chạy trước có thể xử lý hoàn tất preflight hoặc trả headers trước filter còn lại. Policy không còn một nguồn sự thật.

**Sửa:** chọn **source chung chỉ trong Security CORS** *hoặc* chọn top-level `CorsWebFilter` có ordering đúng và tắt đường Security CORS tương ứng; đồng thời loại bỏ rule HandlerMapping mâu thuẫn.

### 4.2. Preflight OPTIONS bị 401/redirect

`OPTIONS` trong CORS preflight thường thiếu credentials, nhưng `.anyExchange().authenticated()` có thể bắt login nếu CORS chưa chạy. Thêm:

```java
.pathMatchers(HttpMethod.OPTIONS, "/api/**").permitAll()
```

có thể tránh một số 401 nhưng **không thêm `Access-Control-Allow-Origin`**. Đây không phải thay thế cho CORS processing, và permit-all quá rộng có thể không hợp với một số kiến trúc. Cần xử lý preflight sớm và kiểm chứng bằng request có đủ `Origin` và `Access-Control-Request-*`.

### 4.3. Hai `Access-Control-Allow-Origin` trên cùng response

Ví dụ gateway ghi:

```http
Access-Control-Allow-Origin: *
```

còn backend lại ghi:

```http
Access-Control-Allow-Origin: https://app.example.com
```

Browser có thể báo **multiple values** hoặc giá trị không hợp lệ. Header ACAO không phải danh sách origins được phép ngăn bằng dấu phẩy. Chọn một nơi phát header hoặc loại bỏ phần header do tầng khác tự chồng lên; không vá bằng cách tắt security.

### 4.4. Allowed origin, method, header không khớp

Origin bao gồm scheme, host, port: `http://localhost:3000` khác `http://localhost:4200`; không thêm path hoặc dấu slash cuối khi khai báo `allowedOrigins`.

Một preflight cho:

```http
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: authorization,content-type,x-csrf-token
```

có thể bị từ chối nếu policy chỉ cho GET hoặc thiếu `X-CSRF-TOKEN`. Đừng mở `allowedMethods("*")` và `allowedHeaders("*")` chỉ để “chữa CORS”; hãy bám hợp đồng frontend và path cụ thể.

### 4.5. Gateway hoặc reverse proxy xử lý trước ứng dụng

Spring Cloud Gateway, nginx, ingress hoặc CDN có thể tự trả OPTIONS hoặc thêm ACAO vào response. Test chỉ gọi `localhost` service không thấy được lỗi trên hostname public. Cần kiểm thử **đúng tuyến đi thực tế**, rõ trách nhiệm giữa gateway và service.

### 4.6. Nhiều `SecurityWebFilterChain`

Một source gắn vào chain `/ui/**` không mặc nhiên áp vào `/api/**`, nếu security matchers khác nhau. Chain có order sớm hơn có thể “nuốt” request trước chain được dự kiến. Kiểm tra `securityMatcher`, `@Order` và CORS source của từng chain, thay vì chỉ tìm dòng `.cors(...)` có tồn tại ở đâu đó trong project.

## 5. Phương án chính: một Reactive `CorsConfigurationSource` dùng trong Security

Đây là cấu hình được chọn cho ví dụ: **không tạo riêng bean `CorsWebFilter`, không thêm CORS `WebFluxConfigurer`, không thêm `@CrossOrigin` vào controller**. Một nguồn cấu hình được Spring Security gắn vào đúng filter order.

Thiết kế:

- Frontend được phép: `http://localhost:3000`.
- Backend: `http://localhost:8080`.
- Chỉ đường `/api/**` có CORS cross-origin.
- Method cho `/api/**`: GET, OPTIONS.
- Request headers được phép: `Authorization`, `Content-Type`.
- `allowCredentials(false)` vì demo không dùng cookie cross-origin; phần sau trình bày cấu hình cookie riêng.
- `GET /api/me` cần HTTP Basic; `GET /public/ping` là endpoint public nhưng không thuộc CORS mapping.

Vì demo chỉ gọi GET/OPTIONS, Spring Security CSRF mặc định **không cần tắt**. Những endpoint POST làm thay đổi trạng thái phải có chính sách CSRF phù hợp, độc lập với CORS.

## 6. Ví dụ Java 17+ chạy được

Yêu cầu Spring Boot 3.x / Spring Security 6.x / Java 17+ và Gradle wrapper.

### 6.1. Dependencies (`build.gradle`)

Trong dự án đã cấu hình Spring Boot plugin và repositories:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Không thêm `spring-boot-starter-web` để tránh chuyển demo sang MVC/Servlet.

### 6.2. Tệp `src/main/java/demo/cors/CorsDemoApplication.java`

```java
package demo.cors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CorsDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CorsDemoApplication.class, args);
    }
}
```

### 6.3. Tệp `src/main/java/demo/cors/SecurityConfig.java`

```java
package demo.cors;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    UrlBasedCorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:3000"));
        cors.setAllowedMethods(List.of("GET", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setAllowCredentials(false);
        cors.setMaxAge(1800L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            UrlBasedCorsConfigurationSource corsSource) {

        return http
            .cors(cors -> cors.configurationSource(corsSource))
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    ReactiveUserDetailsService userDetailsService() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("demo123"))
            .roles("READER")
            .build();
        return new MapReactiveUserDetailsService(reader);
    }
}
```

**Giải thích:**

1. `UrlBasedCorsConfigurationSource` nằm trong package `org.springframework.web.cors.reactive`, **không phải package Servlet**.
2. Source chỉ đăng ký `/api/**`. `GET /public/ping` vẫn public theo security authorization nhưng không tự có ACAO cross-origin.
3. `.cors(cors -> cors.configurationSource(corsSource))` đặt CORS **vào security chain ở thứ tự thích hợp**. Không cần đăng ký thêm `CorsWebFilter` bean.
4. `.anyExchange().authenticated()` vẫn bảo vệ `/api/me` trên **request thực**. Việc OPTIONS preflight được CORS xử lý không cấp quyền cho GET sau đó.
5. HTTP Basic chỉ dùng demo cục bộ. **Base64 không mã hóa mật khẩu**; production phải dùng TLS và cơ chế authentication phù hợp. Không đưa cặp `reader/demo123` vào JavaScript bundle.
6. `setAllowCredentials(false)` phù hợp demo không dựa vào cross-origin cookies. Nó không thay authentication/authorization và không có nghĩa “browser không thể gửi bất cứ Authorization header nào”; request có custom header vẫn phải thỏa mãn Fetch/CORS policy của browser.
7. Không gọi `.csrf(csrf -> csrf.disable())`. CORS và CSRF là hai chính sách độc lập; ứng dụng có browser Basic credentials tự gửi có thể vẫn cần CSRF cho request ghi.

### 6.4. Tệp `src/main/java/demo/cors/ApiController.java`

```java
package demo.cors;

import java.util.Map;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context -> Map.of(
                "user", context.getAuthentication().getName()));
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }
}
```

Controller dùng `ReactiveSecurityContextHolder` lấy identity do Spring Security xác minh, không tin username từ query parameter. `GET /api/me` thành công trả:

```json
{"user":"reader"}
```

### 6.5. Chạy

Từ thư mục dự án có Gradle wrapper:

```bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun
```

Cổng mặc định Spring Boot trong demo là `8080`. Khi chạy sản phẩm thực, bật HTTPS, giới hạn thông tin trong error/logging và không dùng tài khoản demo.

## 7. Kiểm tra CORS bằng curl

### 7.1. OPTIONS preflight đúng origin, không có credentials

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Kết quả mong đợi:

- Preflight được chấp nhận, thường `200 OK`, không cần Basic header.
- `Access-Control-Allow-Origin: http://localhost:3000`.
- Allowed methods chứa GET; allowed headers chứa authorization.
- Không có challenge `401`/redirect yêu cầu login cho OPTIONS.

### 7.2. GET thực có credentials hợp lệ

```bash
curl -i -u reader:demo123 \
  -H "Origin: http://localhost:3000" \
  http://localhost:8080/api/me
```

Kết quả: status `200 OK`, JSON `{"user":"reader"}` và ACAO của frontend. `curl -u` gửi Basic header **chỉ để test local**; không gửi password qua HTTP trên production.

### 7.3. Preflight từ origin không được phép

```bash
curl -i -X OPTIONS http://localhost:8080/api/me \
  -H "Origin: https://evil.example" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization"
```

Với `CorsWebFilter`/mặc định `DefaultCorsProcessor`, preflight không được phép thường bị `403 Forbidden`. Trọng tâm không chỉ là status: origin đó **không được cấp** ACAO để browser đọc API.

### 7.4. Request không có `Origin`

```bash
curl -i -u reader:demo123 \
  http://localhost:8080/api/me
```

Vì đây không phải request CORS, server có thể trả JSON `200` mà **không** có ACAO. Thiếu header CORS trên request không có `Origin` là bình thường.

### 7.5. Public endpoint nằm ngoài CORS mapping

```bash
curl -i \
  -H "Origin: http://localhost:3000" \
  http://localhost:8080/public/ping
```

Endpoint có thể trả `pong` nhờ `.pathMatchers("/public/**").permitAll()`, nhưng browser frontend **không được tự động đọc** response cross-origin vì `/public/**` không nằm trong CORS source. `permitAll` không tự cấu hình CORS.

**Lưu ý:** `curl` không áp dụng browser CORS policy; nó chỉ cho ta xem headers/status. Sau đó phải thử từ frontend origin thật trong Developer Tools → Network và xem cả OPTIONS lẫn actual request.

## 8. Kiểm thử tích hợp bằng `WebTestClient`

Tệp `src/test/java/demo/cors/CorsIntegrationTest.java`:

```java
package demo.cors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class CorsIntegrationTest {

    private static final String FRONTEND = "http://localhost:3000";
    private static final String REJECTED = "https://evil.example";

    @Autowired
    WebTestClient client;

    @Test
    void preflightDoesNotNeedAuthentication() {
        client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
            .expectHeader().doesNotExist(HttpHeaders.WWW_AUTHENTICATE);
    }

    @Test
    void actualRequestStillNeedsAuthentication() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND);
    }

    @Test
    void allowedOriginAndCorrectPasswordCanGetUser() {
        client.get().uri("/api/me")
            .header(HttpHeaders.ORIGIN, FRONTEND)
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().valueEquals(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN, FRONTEND)
            .expectBody()
            .jsonPath("$.user").isEqualTo("reader");
    }

    @Test
    void disallowedPreflightIsRejected() {
        client.options().uri("/api/me")
            .header(HttpHeaders.ORIGIN, REJECTED)
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
            .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void requestWithoutOriginDoesNotNeedCorsHeaders() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("reader", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
    }
}
```

Chạy:

```bash
# Linux/macOS
./gradlew test --tests 'demo.cors.CorsIntegrationTest'

# Windows
gradlew.bat test --tests "demo.cors.CorsIntegrationTest"
```

**Ý nghĩa kiểm thử:**

- `preflightDoesNotNeedAuthentication`: CORS chạy đủ sớm và OPTIONS không bị Basic filter yêu cầu credentials.
- `actualRequestStillNeedsAuthentication`: preflight pass **không** tự cấp quyền cho API.
- `allowedOriginAndCorrectPasswordCanGetUser`: actual GET có origin hợp lệ, credentials đúng, được phép đọc.
- `disallowedPreflightIsRejected`: policy thực sự từ chối origin không đáng tin.
- `requestWithoutOriginDoesNotNeedCorsHeaders`: request same-origin-style/server-to-server không bị phụ thuộc vào ACAO.

Các test trên chạy với ứng dụng WebFlux mock server; chúng chưa test browser cookie/third-party policy hoặc gateway. Với production, bổ sung test gọi hostname public qua ingress để bắt xung đột headers ngoài ứng dụng.

## 9. Phương án thay thế A: top-level `CorsWebFilter`

Một `CorsWebFilter` độc lập phù hợp với ứng dụng có functional routes, yêu cầu filter xử lý sớm hoặc kiến trúc đã chọn filter tại tầng WebFlux. **Không bật đồng thời với cấu hình Security CORS của demo phần 6**.

Ví dụ **thay thế** bean (trích đoạn trong một `@Configuration`):

```java
@Bean
@Order(Ordered.HIGHEST_PRECEDENCE)
CorsWebFilter standaloneCorsWebFilter() {
    CorsConfiguration cfg = new CorsConfiguration();
    cfg.setAllowedOrigins(List.of("http://localhost:3000"));
    cfg.setAllowedMethods(List.of("GET", "OPTIONS"));
    cfg.setAllowedHeaders(List.of("Authorization", "Content-Type"));

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", cfg);
    return new CorsWebFilter(source);
}
```

Import bổ sung:

```java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
```

Trong **security chain thay thế**, không gắn một source filter CORS thứ hai:

```java
// Chỉ khi top-level CorsWebFilter đã được đăng ký và chạy trước Security.
return http
    .cors(cors -> cors.disable())
    .authorizeExchange(ex -> ex
        .pathMatchers("/public/**").permitAll()
        .anyExchange().authenticated())
    .httpBasic(Customizer.withDefaults())
    .formLogin(form -> form.disable())
    .build();
```

`@Order(Ordered.HIGHEST_PRECEDENCE)` biểu thị yêu cầu chạy sớm, nhưng khi hệ thống có nhiều WebFilters/gateway cần kiểm thử thứ tự **thực tế**. Tắt `ServerHttpSecurity.cors` ở phương án này **không vô hiệu hóa quy tắc CORS của browser**; trách nhiệm đã chuyển sang top-level `CorsWebFilter`.

Không copy cả hai phương án chính và thay thế vào cùng project rồi mong Spring tự chọn policy hợp lý.

## 10. Phương án thay thế B: `WebFluxConfigurer` và `@CrossOrigin`

Spring Framework hỗ trợ cấu hình **global HandlerMapping** như sau:

```java
@Configuration
class WebFluxCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("http://localhost:3000")
            .allowedMethods("GET", "OPTIONS")
            .allowedHeaders("Authorization", "Content-Type")
            .maxAge(1800);
    }
}
```

Import:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.config.CorsRegistry;
import org.springframework.web.reactive.config.WebFluxConfigurer;
```

**Đây là phương án thay thế để học**, không thêm vào demo Security CORS source ở phần 6. Khi chỉ dùng HandlerMapping config, nếu một Security WebFilter yêu cầu authentication **trước HandlerMapping**, preflight vẫn có thể bị 401; vì vậy Spring Security khuyến nghị xử lý CORS trước security. Không quảng bá `WebFluxConfigurer` một mình là cách sửa chuẩn cho mọi app có Spring Security.

Đặt `@CrossOrigin` trên controller:

```java
@CrossOrigin(origins = "https://preview.example.com")
@GetMapping("/api/preview")
public Mono<String> preview() {
    return Mono.just("preview");
}
```

Đây là **đoạn minh họa bên trong controller**, không phải class Java độc lập. Global + local HandlerMapping CORS có thể kết hợp theo quy tắc cộng dồn; đừng mặc định local origin sẽ thay thế toàn bộ global origins.

Nếu một endpoint thật sự cần origin riêng, có thể thêm path-specific mapping vào `CorsConfigurationSource` mà security đang dùng thay vì mỗi team khai báo CORS ở một nơi khác nhau.

## 11. Nhiều security chains và nguồn CORS

Trong một ứng dụng WebFlux có thể có:

- `/api/**` dùng bearer/JWT hoặc Basic và cần CORS từ một SPA.
- `/admin/**` dùng cookie session, chỉ dành cho một origin tin cậy.
- `/public/**` thực sự public nhưng không nhất thiết public cross-origin.

Dùng `securityMatcher` và `@Order` nếu có nhiều `SecurityWebFilterChain`. Một đoạn minh họa cấu hình chain:

```java
// Trích đoạn trong @Configuration, với apiCorsSource được cung cấp.
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            new PathPatternParserServerWebExchangeMatcher("/api/**"))
        .cors(cors -> cors.configurationSource(apiCorsSource))
        .authorizeExchange(ex -> ex.anyExchange().authenticated())
        .build();
}
```

Các import khi triển khai:

```java
import org.springframework.core.annotation.Order;
import org.springframework.security.web.server.util.matcher
    .PathPatternParserServerWebExchangeMatcher;
```

Đây **không phải class chạy độc lập**; `apiCorsSource` và cơ chế authenticate cụ thể phải được ứng dụng cung cấp, và chain còn lại cần được cấu hình theo policy của chúng. Mục đích: cho thấy CORS cần được đặt trong **chain thực sự match request**, không phải chỉ khai báo ở một chain bất kỳ.

**Các câu hỏi phải test:**

1. OPTIONS `/api/me` có match security chain API đúng thứ tự không?
2. `/api/**` được origin A cho phép nhưng `/admin/**` không vô tình mở cho A chứ?
3. Bean `CorsWebFilter` top-level có ghi đè policy theo chain không?
4. Chain fallback có đứng trước chain API làm API chain không bao giờ được chọn?
5. Khi dùng cookie/session ở một chain khác, CORS credentials và CSRF có đúng policy của chain đó không?

## 12. Credentials, cookies, JWT và CORS

`setAllowCredentials(true)` chỉ phù hợp khi frontend cần **credentialed cross-origin response** (chẳng hạn Fetch `credentials: "include"` với cookie). Những điều kiện đi kèm:

- Chỉ cho **origin chính xác đã tin cậy**; không dùng `allowedOrigins("*")` với credentials. Spring Framework có kiểm tra quy tắc này.
- Đặt `Access-Control-Allow-Credentials` đúng theo policy, nhưng **đừng nghĩ header này ép browser gửi cookie**: cookie còn chịu `Secure`, `SameSite`, domain/path, third-party policy và Fetch credentials mode.
- Khi dùng session cookie cho POST/PUT/DELETE, cần CSRF token hợp lệ nếu threat model cần. CORS không ngăn mọi form request bị trình duyệt tự gửi.
- Nếu frontend gửi `X-CSRF-TOKEN`, cần khai báo header đó trong allowedHeaders, cùng allowedMethods cho request thực.
- Với bearer token được frontend gửi tường minh trong `Authorization`, phải cho header Authorization qua preflight và vẫn kiểm chứng token/issuer/audience/scope ở backend.
- Không bật origins wildcard và lạm dụng `allowedOriginPatterns("*")` với credentials chỉ vì dev frontend gọi nhiều port.

Một config minh họa **thay thế** cho cookie-based frontend:

```java
CorsConfiguration cookieCors = new CorsConfiguration();
cookieCors.setAllowedOrigins(List.of("https://app.example.com"));
cookieCors.setAllowCredentials(true);
cookieCors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
cookieCors.setAllowedHeaders(List.of(
    "Content-Type", "X-CSRF-TOKEN"));
cookieCors.setMaxAge(600L);
```

Đây chỉ là phần cấu hình CORS cho một security model khác, không tự triển khai session login hoặc CSRF repository. Với frontend cookie session, `fetch` có thể dùng:

```javascript
fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
```

Request vẫn có thể bị browser từ chối nếu cookie policy không cho gửi, hoặc bị API 401 nếu session không tồn tại. Không sửa bằng wildcard origin.

## 13. CORS không thay thế CSRF, authentication hoặc authorization

Ba ví dụ để phân biệt:

**Tình huống A:** OPTIONS preflight trả `200`, GET thực trả `401` vì thiếu Basic/JWT. Đây có thể là **kết quả đúng**: frontend origin được phép dùng API, nhưng request chưa xác thực.

**Tình huống B:** OPTIONS cho POST trả thành công, actual POST trả `403` vì thiếu CSRF token. Đây có thể là **CSRF protection hoạt động đúng**, không phải CORS thiếu header. Nếu browser dùng cookie tự gửi, đừng tắt CSRF chỉ để yêu cầu POST thành công.

**Tình huống C:** GET có credentials hợp lệ nhưng trả `403` do role/scope không đủ. CORS chỉ liên quan origin, không quyết định user có quyền đọc tài nguyên.

Vì vậy, quy trình đúng là: **preflight policy → actual request → authentication → CSRF/authorization/business policy**. Những bước có thể từ chối độc lập và cần được giám sát phân loại.

CORS chỉ bảo vệ tương tác của browser. Client không chịu CORS như `curl` vẫn có thể gọi API; backend phải tự xác thực và phân quyền mọi request. Không dùng CORS thay cho API key, OAuth2 scope hay object ownership.

## 14. Gateway/CDN và hiện tượng “localhost chạy, production lỗi”

Khi đường đi là:

```text
Browser → CDN / Ingress / Gateway → WebFlux / Spring Security → Handler
```

CORS có thể được xử lý ở tầng proxy trước backend. Gateway đôi khi **trả OPTIONS trực tiếp**, hoặc **chèn ACAO vào response** sau backend. Nếu backend cũng tự set ACAO mà hai policy khác nhau, browser có thể thấy nhiều giá trị và từ chối.

**Quy trình chuẩn hóa:**

1. Xác định nơi thật sự nhận preflight đầu tiên và nơi nào phát `Access-Control-Allow-*` trên hostname public.
2. Chọn owner của CORS policy cho từng route: gateway **hoặc** ứng dụng (hoặc một phối hợp có hợp đồng rõ).
3. Nếu gateway đã set headers, không để app phát thêm giá trị không tương thích; nếu app chịu trách nhiệm, gateway không nên ghi đè lung tung.
4. Kiểm thử cả `OPTIONS` và request thực qua **public URL**, không chỉ service localhost.
5. Kiểm tra `Vary: Origin` và các preflight headers để cache/proxy không trả chính sách của origin A cho origin B.
6. Kiểm tra response lỗi do gateway tạo (`502`, `503`): console browser có thể ghi “CORS error” chỉ vì response lỗi thiếu ACAO; nguyên nhân gốc vẫn có thể là upstream outage.
7. Không ghi raw Authorization/JWT/cookie/CSRF vào telemetry khi debug.

Đừng cho `Access-Control-Allow-Origin: *` trong production chỉ để khắc phục nhanh; đây là một thay đổi phạm vi frontend có thể đọc dữ liệu.

## 15. Chẩn đoán theo triệu chứng

| Dấu hiệu | Khả năng | Kiểm tra |
| --- | --- | --- |
| Preflight OPTIONS `401` | Security chạy trước CORS hoặc source sai chain | Gửi OPTIONS đầy đủ headers, kiểm tra matcher và filter order |
| OPTIONS redirect `/login` | Form login entry point bắt preflight | CORS filter phải chạy trước authentication |
| OPTIONS `403` | Origin/method/request header không được cho phép | So `Origin`, `Access-Control-Request-*` và source |
| OPTIONS `200`, GET `401` | Authentication của actual request thiếu/sai | Kiểm tra Authorization/Cookie hiện diện, không log giá trị |
| OPTIONS `200`, POST `403` | CSRF hoặc authorization, không nhất thiết là CORS | Kiểm tra token, role và CORS headers |
| Browser báo multiple ACAO | Gateway và app hoặc hai filters cùng đặt header | Kiểm tra raw response headers từng tầng |
| Browser báo wildcard với credentials | `*` và `allowCredentials(true)` không tương thích | Dùng trusted exact origins |
| Curl GET `200` nhưng frontend CORS lỗi | Curl không thực thi CORS như browser | Browser Network/Console, preflight và ACAO |
| `@CrossOrigin` không giúp OPTIONS | Preflight bị Security chặn trước HandlerMapping | Dùng CORS trước security, không chỉ annotation |
| GET public bị browser chặn | `permitAll` không tự cấu hình CORS | Kiểm tra path mapping của CORS source |
| Response lỗi 500 không có ACAO | Error handler/proxy không phát CORS headers | Kiểm tra lỗi gốc, thứ tự xử lý errors |
| Chỉ một origin frontend hoạt động | Port/scheme/host khác allowed origins | So chính xác origin trong Network |
| Không gửi được session cookie | Fetch mode/SameSite/Secure/third-party cookie policy | Kiểm tra cookie attrs và browser policy |
| Nâng version rồi test thất bại | Auto-config/source/chains behavior thay đổi | Đối chiếu version và integration tests |

**Quy trình sửa lỗi tuần tự:**

1. Ghi nhận frontend origin + URL API + method + request headers dự kiến.
2. Dùng curl/WebTestClient tái hiện đúng preflight có `Origin` và `Access-Control-Request-Method`.
3. Kiểm tra headers/status preflight trước, rồi actual request sau.
4. Liệt kê các nơi khai báo policy: `@CrossOrigin`, `WebFluxConfigurer`, `CorsWebFilter`, `ServerHttpSecurity.cors`, gateway/proxy.
5. Chọn **một CORS owner** và loại các cấu hình trùng lặp không chủ đích; đảm bảo source là **Reactive**.
6. Kiểm tra security chain matchers/order, cookie/CSRF/authorization riêng.
7. Chạy lại positive và negative integration tests, rồi thử browser thật và gateway.

Có thể bật tạm logging phát triển:

```properties
logging.level.org.springframework.security=DEBUG
```

Không log token, Basic password, raw `Authorization`, cookie hoặc session ID. Một lỗi CORS không phải lý do để bỏ security chain hoặc bật wildcard toàn API.

## 16. Những ngộ nhận cần tránh

**Ngộ nhận 1: `permitAll()` giải quyết CORS.** Không. Nó chỉ bỏ yêu cầu authorization cho các route phù hợp, không phát `Access-Control-Allow-Origin`.

**Ngộ nhận 2: `@CrossOrigin` luôn chạy trước security.** Không. `@CrossOrigin` được xử lý ở HandlerMapping; security WebFilters có thể chặn trước khi đến đó.

**Ngộ nhận 3: Bật càng nhiều CorsWebFilter càng chắc.** Không. Nhiều filter/policies có thể cùng xử lý một request với kết quả phụ thuộc thứ tự.

**Ngộ nhận 4: Chỉ cần return status 200 trên OPTIONS.** Không. Browser còn cần kiểm tra allow-origin, allow-methods, allow-headers và credentials policy.

**Ngộ nhận 5: Có ACAO là user đã authenticated.** Không. CORS chỉ quy định trình duyệt được phép sử dụng response cross-origin.

**Ngộ nhận 6: CORS chặn CSRF.** Không. Form cross-site vẫn có thể được browser gửi; cookie-based unsafe methods cần CSRF protection thích hợp.

**Ngộ nhận 7: `*` được dùng với mọi credentialed request.** Không. `allowCredentials(true)` và wildcard `allowedOrigins("*")` không hợp lệ theo quy tắc CORS thông thường.

**Ngộ nhận 8: Cùng host thì cùng origin bất kể port.** Không. Port và scheme là một phần của origin.

**Ngộ nhận 9: Curl POST thành công nghĩa là browser sẽ thành công.** Không. Curl không cưỡng chế CORS policy của browser; vẫn phải test frontend thực.

**Ngộ nhận 10: Chỉ cần sửa backend, gateway không liên quan.** Không. Proxy có thể tạo hoặc ghi đè CORS headers; phải xem đường đi thật.

**Ngộ nhận 11: CORS của một SecurityWebFilterChain tự áp cho chain còn lại.** Không nên giả định; phụ thuộc vào matchers/filter placement.

**Ngộ nhận 12: Khi gặp lỗi, nên tắt CORS trong Security mà không làm gì khác.** Nếu không có filter/policy thay thế đúng thứ tự, frontend cross-origin vẫn không được hỗ trợ.

## 17. Checklist trước production

| Hạng mục | Tiêu chí đạt |
| --- | --- |
| Đúng WebFlux API | Reactive `CorsConfigurationSource`, `UrlBasedCorsConfigurationSource`, `ServerHttpSecurity` |
| CORS owner | Xác định rõ Security, standalone filter, HandlerMapping hay gateway chịu trách nhiệm |
| Không chồng policies | Không có origins/methods/headers mâu thuẫn trên cùng path |
| Filter ordering | Preflight OPTIONS xử lý trước yêu cầu xác thực |
| Positive origin | Origin được phép nhận đúng ACAO và allowed methods/headers |
| Negative origin | Origin lạ bị từ chối, không vô tình được phản chiếu |
| Security | Actual request vẫn phải authentication/authorization phù hợp |
| CSRF | Không tắt CSRF vì nhầm CORS lỗi |
| Origin chính xác | Scheme/host/port đúng; không path hoặc trailing slash |
| Credentialed requests | Exact trusted origins, correct `allowCredentials`, cookie/Fetch mode |
| Gateway | Không trùng ACAO, test qua public hostname |
| Multiple chains | Matchers và CORS source áp đúng chain |
| Errors | 401/403/5xx có headers phù hợp nếu frontend cần đọc lỗi |
| Cache | `Vary` và private response cache policy đúng |
| Browser | Network tab xác nhận OPTIONS và actual request |
| Observability | Log nguyên nhân ở mức an toàn, không lộ credentials |
| Tests | `WebTestClient` và browser E2E bao gồm allow/deny cases |

## 18. Câu hỏi tự kiểm tra

**1. Vì sao preflight phải được xử lý trước Spring Security?** Vì OPTIONS thường không mang credentials để server xác thực như actual request; Security xử lý trước có thể từ chối 401 hoặc redirect.

**2. `@CrossOrigin` và WebFlux global mapping có luôn tạo duplicate headers?** Không. Chúng có quy tắc kết hợp ở HandlerMapping; rủi ro là origins được hợp nhất/mở rộng ngoài ý định.

**3. Vì sao không đăng ký cả standalone `CorsWebFilter` và `.cors(configurationSource(...))` theo hai rules khác nhau?** Request có thể bị filter trước chặn/hoàn thành hoặc nhận CORS headers mâu thuẫn, rất khó xác định policy thực.

**4. `OPTIONS permitAll` đã đủ chưa?** Chưa. Nó không tự sinh CORS headers hay so khớp requested method/header.

**5. `GET /api/me` có ACAO đúng nhưng password sai thì điều gì xảy ra?** API vẫn trả authentication failure/401. CORS không cấp quyền.

**6. Có thể dùng `allowedOrigins("*")` cùng `allowCredentials(true)` không?** Không; phải sử dụng trusted exact origins hoặc pattern đã được thiết kế chặt và test kỹ.

**7. `curl` thấy 200 nhưng browser báo CORS có mâu thuẫn không?** Không. `curl` không thực thi chính sách CORS của browser.

**8. Thêm CORS chỉ ở UI security chain đã đủ cho API chain chưa?** Không được giả định. Phải kiểm tra đúng chain matcher và source API.

**9. Gateway có thể gây CORS lỗi dù backend đúng không?** Có. Gateway có thể chặn OPTIONS hoặc thêm/chỉnh ACAO, dẫn tới response sai trên public hostname.

**10. Đổi CORS policy cần kiểm tra điều gì quan trọng nhất?** Không vô tình mở thêm origins hoặc làm yếu authentication/authorization/CSRF; cần cả positive và negative integration tests.

## Ghi nhớ

- Spring Security Reactive cần **CORS trước authentication** để preflight không bị challenge.
- `CorsWebFilter`, `WebFluxConfigurer`, `@CrossOrigin` và `ServerHttpSecurity.cors(...)` là những đường cấu hình có phạm vi và thời điểm khác nhau.
- Với WebFlux + Security, **một Reactive `CorsConfigurationSource` được truyền vào `.cors(cors -> cors.configurationSource(...))`** là cấu hình rõ ràng, dễ kiểm thử.
- Không thêm nhiều filters CORS mâu thuẫn; phân biệt sự kết hợp tại HandlerMapping với hai WebFilters độc lập.
- `allowCredentials`, origin, method, request headers, gateway và cookie policy đều ảnh hưởng browser.
- CORS **không thay authentication, authorization hay CSRF**. Preflight pass không đảm bảo actual request thành công.
- Kiểm thử cả **OPTIONS và actual request**, **origin hợp lệ và bị cấm**, **có/không có authentication**, và đường đi qua **gateway**.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Reactive CORS integration](https://docs.spring.io/spring-security/reference/6.5/reactive/integrations/cors.html)
- [Spring Security 6.5 — `ServerHttpSecurity.CorsSpec`](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CorsSpec.html)
- [Spring Security 6.5 — `ServerHttpSecurity` Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Framework 6.2 — CORS in WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux-cors.html)
- [Spring Framework 6.2 — `CorsWebFilter` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/reactive/CorsWebFilter.html)
- [Spring Framework 6.2 — `CorsConfiguration` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/cors/CorsConfiguration.html)
