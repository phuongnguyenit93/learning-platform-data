# Kiểm chứng filter, profile, codec và cấu hình bảo mật

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Kiểm thử WebFlux

Một endpoint trả HTTP 200 chưa đủ để chứng minh ứng dụng WebFlux hoạt động đúng. Request có thể đã đi qua một cấu hình test tối giản, bỏ qua `WebFilter`, dùng nhầm profile, dùng codec không đúng giới hạn hoặc được xử lý khi Spring Security chưa được gắn vào chain. Ngược lại, một unit test có thể cho thấy controller đúng nhưng khi triển khai thực tế lại trả 401/403, lỗi 413 hoặc lộ dữ liệu nhạy cảm.

Bài học này xây dựng chiến lược **kiểm thử cấu hình thật, có phạm vi rõ** cho bốn thành phần: **WebFilter**, **Spring profiles/properties**, **HTTP message codecs** và **reactive security**. Trọng tâm là `WebTestClient`, `@WebFluxTest`, `@SpringBootTest`, `@ActiveProfiles`, Spring Security test support và kiểm thử tích hợp với Spring Boot 3.5 / Spring Framework 6.2.

## 1. Điều cần chứng minh bằng test

Mỗi test nên chứng minh một contract quan sát được, thay vì chỉ gọi endpoint rồi kiểm tra `200 OK`.

| Nhóm | Điều cần kiểm chứng | Test không đủ |
|---|---|---|
| `WebFilter` | Filter được đăng ký, chạy đúng thứ tự, áp dụng cho cả error/anonymous path khi cần | Gọi trực tiếp method filter |
| Profile | Bean của profile đúng xuất hiện; bean của profile khác vắng mặt; property đúng được bind | Đọc file `application-qa.properties` rồi suy luận |
| Codec | Reader/writer, content type, encoding, size cap đúng cho HTTP request thật | Chỉ kiểm tra bean `ObjectMapper` tồn tại |
| Security | Anonymous 401, authenticated đúng role 200, sai role 403, CSRF, rule path/method, deny-by-default | Chỉ test controller method với mock principal |
| Cross-cutting | Filter và security chain cùng chạy; error mapping và codec không bị test bypass | Dùng `bindToController` cho toàn bộ cấu hình |
| Vận hành | Live server, proxy, TLS/HTTP headers, timeout thật | Mock exchange không có socket |

Một ca kiểm thử tốt cần có **điều kiện đầu vào**, **chuỗi middleware thực sự được lắp**, **kết quả kỳ vọng** và một **negative test** cho đường truy cập không được phép.

## 2. WebFlux thực hiện request qua những tầng nào?

```text
Browser / API client
       |
       v
Reactor Netty server / HTTP adapter
       |
       v
WebHttpHandlerBuilder
       |
       +--> WebFilter (order / context / auth / audit)
       |
       +--> Spring Security WebFilterChainProxy
       |
       v
DispatcherHandler
       |
       +--> HandlerMapping
       +--> HandlerAdapter
       +--> ResultHandler / HttpMessageWriter
       |
       v
Controller, RouterFunction or resource handler
       |
       v
HTTP response
```

`WebFilter` là middleware **server-side**; `ExchangeFilterFunction` lại là filter cho **outbound WebClient**. Hai loại có API, điểm chạy và cách test khác nhau. Một test `WebClient` outbound không chứng minh inbound `WebFilter` hoạt động.

Security cho WebFlux sử dụng `SecurityWebFilterChain`; đây là danh sách security filters do `WebFilterChainProxy` điều phối. `@EnableWebFluxSecurity` không đồng nghĩa `@EnableWebFlux`. Annotation thứ hai kích hoạt manual WebFlux infrastructure và có thể làm Spring Boot WebFlux auto-configuration back off, vì vậy không thêm `@EnableWebFlux` chỉ để test Security.

## 3. Chọn đúng độ sâu của WebTestClient

`WebTestClient` có thể test từ controller logic đến server thật. Chọn theo vấn đề cần chứng minh:

| Thiết lập | Load gì? | Phù hợp | Không tự chứng minh |
|---|---|---|---|
| `WebTestClient.bindToController(...)` | Controller được chỉ định và WebFlux setup gọn | Binding, validation, serialization đơn lẻ | Bean filters/profile/Boot security ngoài context |
| `bindToRouterFunction(...)` | RouterFunction và handler được chỉ định | Predicate, route functional | Toàn bộ ApplicationContext |
| `bindToApplicationContext(context)` | Context WebFlux thực, mock request/response | Filter bean, profile, codecs, security config | TCP/TLS/Netty thật |
| `@WebFluxTest` | Test slice của WebFlux | Controller, validation, codec và các config được import | Mọi bean service/filter/security của ứng dụng |
| `@SpringBootTest(MOCK)` | Boot ApplicationContext đầy đủ, không mở server | Bean/profile/security/filter/codec integration nhanh | Transport thực |
| `@SpringBootTest(RANDOM_PORT)` | Embedded reactive server thật | HTTP wire behavior, headers, end-to-end | Dependency bên ngoài nếu vẫn dùng mock |

Spring Boot 3.5 documentation lưu ý: `@WebFluxTest` chỉ quét một tập bean giới hạn, như `@Controller`, `@ControllerAdvice`, `@JsonComponent`, converter và `WebFluxConfigurer`; nó không quét tùy ý mọi `@Component`. Nó cũng **không tự phát hiện custom `SecurityWebFilterChain`** và không tự phát hiện functional `RouterFunction`. Nếu cần những bean đó, dùng `@Import(...)` hoặc `@SpringBootTest`.

Điểm then chốt: một test dùng `bindToController(new ApiController())` có thể trả 200 dù production security sẽ trả 401. Đây không phải bug của Spring; test đã cố tình chọn mức mock không chứa security/filter chain.

## 4. Test WebFilter theo hành vi HTTP

`WebFilter` trả `Mono<Void>` và được gọi trong request pipeline:

```java
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class MarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange, WebFilterChain chain) {

        exchange.getResponse()
                .getHeaders()
                .set("X-Filter-Trace", "visited");

        return chain.filter(exchange);
    }
}
```

Code trên thêm một marker an toàn vào response trước khi gọi chain. Test không nên kiểm tra `MarkerFilter.class.getAnnotation(...)` rồi coi đó là bằng chứng. Hãy gửi request qua context thật và assert:

```java
client.get()
        .uri("/api/public")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .valueEquals("X-Filter-Trace", "visited");
```

Vì filter chạy trước handler và được sắp thứ tự cao, test có thể kiểm tra marker trên cả response thành công và response bị từ chối. Nhưng thứ tự của các WebFilter phải được kiểm chứng theo cấu hình cụ thể; không mặc định mọi filter đều chạy trước security.

### 4.1. Kiểm thử thứ tự

Có thể đăng ký hai filter có `@Order` khác nhau và ghi một dấu vết trong **exchange attribute cho từng request**:

```java
Object current = exchange.getAttribute("filterTrace");
String previous = current == null ? "" : current.toString();
exchange.getAttributes().put(
        "filterTrace", previous + "A");
return chain.filter(exchange);
```

Filter thứ hai thêm chữ B; handler hoặc một filter outer có thể xuất dấu vết đã được allowlist vào test response. Assert `AB` khi mục đích là thứ tự thực thi. Không dùng một `StringBuilder` singleton vì các request sẽ race. Không dựa vào thứ tự file Java, component scan hoặc tên bean nếu order có ý nghĩa.

### 4.2. Kiểm thử lỗi và cancel

Filter có thể dùng `doOnError`, `doFinally` hoặc `onErrorResume`. Test nên bao phủ:

- Handler trả thành công.
- Handler phát error.
- Security trả 401/403.
- Request bị cancel/disconnect.
- Filter đã ghi response rồi phát error.
- Context propagation qua `publishOn` nếu filter đặt dữ liệu trong Reactor Context.

Tránh tự `subscribe()` trong filter: điều đó tách subscription khỏi HTTP lifecycle và làm mất propagation của error/cancel.

### 4.3. Không log body trong test filter

Nếu filter dùng để audit, test nên đảm bảo nó **không** ghi Authorization, Cookie, query string hay body. Dùng route template/method/status/duration đã chuẩn hóa. Đừng tạo test “log raw request để so sánh” rồi vô tình giữ secrets trong CI artifacts.

## 5. Profile là điều kiện cấu hình thực tế, không phải một nhãn

Spring sử dụng `@Profile` và `Environment` để quyết định bean nào được tạo. Ví dụ:

```java
@Component
@Profile("qa")
class QaMarkerFilter implements WebFilter {
    // ...
}
```

Khi active profile là `qa`, bean này mới xuất hiện. Test phải xác minh cả:

1. **Positive:** bean có trong profile qa và behavior tương ứng xuất hiện.
2. **Negative:** bean không được tạo trong profile prod.
3. **Property override:** cùng một application có thể có codec/security/timeouts khác theo profile; test giá trị thật qua HTTP hoặc bean settings.

Sử dụng `@ActiveProfiles("qa")` trên test class để chọn profile, thay vì set profile global trên IDE hoặc chỉnh biến môi trường giữa các test.

### 5.1. Property precedence

Ví dụ:

```properties
# src/main/resources/application.properties
spring.http.codecs.max-in-memory-size=1KB
```

```properties
# src/main/resources/application-qa.properties
spring.http.codecs.max-in-memory-size=128B
```

Khi test có `@ActiveProfiles("qa")`, Boot load cấu hình qa và property 128B được áp dụng. Nếu test có `@ActiveProfiles("prod")` mà không có file `application-prod.properties`, cấu hình chung 1KB vẫn được dùng.

Có thể dùng `@TestPropertySource(properties = "feature.enabled=true")` hoặc `@SpringBootTest(properties = "...")` cho một test cụ thể. Với dynamic port/container, dùng `@DynamicPropertySource`; đừng hardcode shared external resources khi chạy CI song song.

### 5.2. Không thay System.setProperty giữa các test

`System.setProperty("spring.profiles.active","qa")` trong test có thể ảnh hưởng test khác, trong khi Spring TestContext cache lại ApplicationContext theo cấu hình. Nếu test thay đổi environment sau khi context đã tạo thì không làm bean `@Profile` tự đăng ký lại.

Dùng annotation chọn profile trước khi context khởi tạo. Khi context thực sự cần làm mới vì trạng thái cấu hình biến đổi, cân nhắc `@DirtiesContext`, nhưng đừng dùng nó để che việc test phụ thuộc thứ tự chạy.

### 5.3. Security phải không “dễ dãi” hơn ngoài production

Không dùng một profile test chỉ để `permitAll()` rồi tuyên bố security configuration đã pass. Với behavior quan trọng (roles/CSRF), giữ security rules giống production và chỉ thay identity/test data. Nếu production dùng JWT/OAuth2, có thể mock JWT khi test authorization policy nhưng phải có một test khác xác minh validator/issuer/audience và token signature trên request thật.

## 6. Codec và HTTP content negotiation

Codec chịu trách nhiệm chuyển `DataBuffer` sang Java object và ngược lại. Các lỗi phổ biến:

- Thiếu JSON encoder/decoder hoặc Jackson module custom.
- `Content-Type` không tương thích → HTTP 415.
- `Accept` không có response representation → HTTP 406.
- Body sai schema hoặc JSON malformed → HTTP 400.
- Buffer aggregation vượt giới hạn → lỗi size; trong Spring Framework 6.2, nhiều đường `@RequestBody` chuyển `DataBufferLimitException` sang HTTP 413.
- Charset sai hoặc Unicode xử lý không đúng.
- Streaming `Flux<T>` không nên bị gom toàn bộ vào memory.

`spring.http.codecs.max-in-memory-size` của Boot 3.5 là giới hạn buffer khi **codec cần aggregate**; không phải hard limit tổng số bytes của mọi raw `Flux<DataBuffer>`. Nếu muốn kiểm tra upload lớn, cần test quota ở gateway/handler hoặc `DataBufferUtils.join(..., maxByteCount)`.

### 6.1. Test codec phải chọn đúng request path

Khi test một `@RequestBody Mono<String>`, Spring String decoder thực sự được chạy, nên có thể dùng request với body dưới và trên buffer cap. Không chỉ so sánh hai chuỗi Java trong unit test.

Ví dụ:

```java
@PostMapping(
        path = "/api/echo",
        consumes = MediaType.TEXT_PLAIN_VALUE,
        produces = MediaType.TEXT_PLAIN_VALUE)
public Mono<String> echo(@RequestBody Mono<String> body) {
    return body.map(value -> "length=" + value.length());
}
```

Nếu test profile giới hạn codec còn 128B, request 32 ASCII byte phải được xử lý, còn một dòng 256 ASCII byte vượt cap của String decoder. Response status được xác nhận bằng `WebTestClient`. Trong Spring Framework 6.2, đường đọc body này chuyển dữ liệu vượt cap thành lỗi HTTP 413. Với codec tự viết hoặc error handler tùy chỉnh, kết quả có thể khác: hãy kiểm tra contract của chính ứng dụng.

### 6.2. JSON, charset và custom mapper

Kiểm thử JSON nên dùng assert nội dung thay vì so sánh thứ tự key không được contract bảo đảm:

```java
client.get().uri("/api/item")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.name").isEqualTo("book");
```

Nếu ứng dụng đăng ký Jackson `Module` custom, enum converter hoặc codec riêng, hãy test với context đã import đúng bean customizer. `@WebFluxTest` không tự nạp mọi `@Component` hoặc auto configuration của thư viện bên ngoài.

### 6.3. Buffer size không phải byte count toàn pipeline

Một JSON array lớn, NDJSON, SSE, multipart hoặc raw file có thể đi qua reader với semantics khác nhau. Giới hạn aggregation thường áp dụng tới **một item/fragment cần decode**, không tạo trần tổng throughput. Test “payload quá lớn” phải định nghĩa chính xác loại payload và decoder đang dùng.

Đừng tăng limit lên `-1` để làm test pass. Nếu production phải xử lý file lớn, hãy thiết kế route streaming và quota riêng, rồi kiểm thử trên server thật.

## 7. Kiểm thử reactive Spring Security

WebFlux security dùng `ServerHttpSecurity` và `SecurityWebFilterChain`. Các hợp đồng quan trọng:

| Điều kiện | Kỳ vọng |
|---|---|
| GET công khai không credentials | 200 |
| GET cần login, anonymous | 401 khi HTTP Basic challenge được cấu hình |
| GET có user nhưng sai role | 403 |
| GET có đúng role | 200 |
| POST có user hợp lệ nhưng không CSRF token | 403 khi CSRF được bật và yêu cầu token |
| POST có user + CSRF token hợp lệ | 200 hoặc status nghiệp vụ |
| Đường dẫn ngoài rule | 403 nếu `denyAll` |
| Cookie/session hoặc JWT lỗi | Bị từ chối theo chain phù hợp |

Tuyệt đối không cố làm test dễ qua bằng `csrf().disable()`, `permitAll()` hoặc `@WithMockUser` trên mọi method. Những lựa chọn đó có thể khiến test không còn bao phủ đường anonymous hoặc CSRF.

### 7.1. Cấu hình WebTestClient security test support

Với mock ApplicationContext:

```java
WebTestClient client =
        WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
```

Dòng `springSecurity()` ở đây là `org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity`. Nó tích hợp security test support vào mock server setup. Trong dự án mẫu sẽ dùng đúng dạng này.

Sau đó:

```java
client.mutateWith(mockUser("alice").roles("READER"))
        .get()
        .uri("/api/private")
        .exchange()
        .expectStatus().isOk();
```

`mockUser` đưa Authentication giả vào SecurityContext của **test request**. Nó hữu ích để kiểm tra authorization, nhưng **không** test password encoding, HTTP Basic authentication filter, token parsing hoặc chữ ký JWT thực tế.

### 7.2. Kiểm thử CSRF

```java
client.mutateWith(mockUser("alice").roles("READER"))
        .mutateWith(csrf())
        .post()
        .uri("/api/echo")
        .contentType(MediaType.TEXT_PLAIN)
        .bodyValue("ok")
        .exchange()
        .expectStatus().isOk();
```

`csrf()` thuộc `SecurityMockServerConfigurers`. Nó gắn CSRF token phù hợp vào mock request. Nếu authentication có mà thiếu token trên POST được bảo vệ, kỳ vọng 403.

Không áp dụng CSRF một cách máy móc cho mọi public REST API. Với pure stateless bearer-token API, threat model và thiết kế CSRF khác browser session/cookie. Bài này giữ CSRF mặc định bật để kiểm tra rõ sự khác biệt.

### 7.3. Test với server thật

`mockUser` chỉ hoạt động khi WebTestClient được bind vào mock server/security test context. Khi dùng `WebTestClient.bindToServer()` hoặc `@SpringBootTest(RANDOM_PORT)`, request đi qua network, nên dùng credentials/JWT thật hoặc test identity provider phù hợp. Không kỳ vọng test-only SecurityContext tự đi qua HTTP socket.

## 8. Dự án đầy đủ: Java 17 + Spring Boot 3.5.16

Ví dụ này dùng 4 loại kiểm chứng trong cùng project:

1. Hai `WebFilter`: filter chung và filter chỉ active ở `qa`.
2. Profiles `qa` và `prod` có codec limit khác nhau.
3. Spring Security yêu cầu role `READER` cho private endpoint và CSRF cho POST.
4. `WebTestClient` kiểm tra HTTP behavior từ full application context bằng mock server (không cần mở port).

**Cấu trúc thư mục:**

```text
webflux-configuration-tests/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/ConfigTestApplication.java
    │   ├── java/demo/ApiController.java
    │   ├── java/demo/GlobalMarkerFilter.java
    │   ├── java/demo/QaMarkerFilter.java
    │   ├── java/demo/SecurityConfiguration.java
    │   └── resources/
    │       ├── application.properties
    │       └── application-qa.properties
    └── test/java/demo/
        ├── QaConfigurationTest.java
        └── ProductionProfileTest.java
```

### 8.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-configuration-tests</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Dependency management của Boot chọn phiên bản Spring Framework/Spring Security tương thích. Không khai báo Spring Framework 7 cho dự án Boot 3.5. `spring-security-test` cần cho `mockUser`, `csrf` và `springSecurity()`.

### 8.2. application.properties

```properties
spring.application.name=webflux-configuration-tests
spring.http.codecs.max-in-memory-size=1KB
spring.http.codecs.log-request-details=false
```

Đây là cấu hình chung. Codec cap 1 KiB chỉ nhằm minh họa khác biệt với profile qa; production thực tế cần chọn theo payload contract.

### 8.3. application-qa.properties

```properties
spring.http.codecs.max-in-memory-size=128B
```

Active profile `qa` ghi đè max-in-memory-size thành 128 byte. Không đặt `spring.profiles.active` trong main configuration hoặc trong Maven command khi test đã khai báo `@ActiveProfiles`.

### 8.4. ConfigTestApplication.java

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConfigTestApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigTestApplication.class, args);
    }
}
```

### 8.5. ApiController.java

```java
package demo;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api")
public class ApiController {

    @GetMapping(
            path = "/public",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> publicEndpoint() {
        return Mono.just("public");
    }

    @GetMapping(
            path = "/private",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> privateEndpoint() {
        return Mono.just("private");
    }

    @PostMapping(
            path = "/echo",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> echo(
            @RequestBody Mono<String> body) {
        return body.map(value ->
                "length=" + value.length());
    }
}
```

Controller cố tình không tự kiểm tra role hoặc CSRF. Đó là trách nhiệm của `SecurityWebFilterChain`. Endpoint echo dùng `Mono<String>` để Spring WebFlux thực sự decode request body trước khi trả response, nên có thể kiểm tra codec cap bằng HTTP test.

### 8.6. GlobalMarkerFilter.java

```java
package demo;

import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class GlobalMarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse()
                .getHeaders()
                .set("X-Global-Filter", "visited");

        return chain.filter(exchange);
    }
}
```

Đây là filter test-safe, không ghi log/body. Nó được sắp thứ tự rất cao để marker có thể xuất hiện trên response được security từ chối trước khi vào controller. Trong production, đừng dùng một marker response tùy ý làm authentication proof; mục đích ở đây là test việc đăng ký/filter chain.

### 8.7. QaMarkerFilter.java

```java
package demo;

import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

@Component
@Profile("qa")
@Order(Ordered.HIGHEST_PRECEDENCE + 1)
public class QaMarkerFilter implements WebFilter {

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {

        exchange.getResponse()
                .getHeaders()
                .set("X-Profile-Filter", "qa");

        return chain.filter(exchange);
    }
}
```

Khi active profile qa, filter thêm response header `X-Profile-Filter: qa`. Khi profile prod active, bean không được tạo. Việc kiểm tra cả header và bean giúp tránh trường hợp code kiểm tra property nhưng filter thực tế chưa được đăng ký.

### 8.8. SecurityConfiguration.java

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/public").permitAll()
                        .pathMatchers("/api/**").hasRole("READER")
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .csrf(Customizer.withDefaults())
                .build();
    }
}
```

Rules:

- `GET /api/public` cho phép anonymous.
- Các đường `/api/**` còn lại cần role `READER`.
- Đường ngoài rule bị `denyAll`.
- HTTP Basic được bật để anonymous được challenge 401.
- CSRF bật; POST authenticated cần token hợp lệ.
- Không dùng `@EnableWebFlux`; `@EnableWebFluxSecurity` là annotation cho security.

Tại production, đăng ký authentication provider/user details/JWT resource server phù hợp. Test sử dụng `mockUser` để tập trung vào authorization rules, không cố xác minh credentials thật.

### 8.9. QaConfigurationTest.java

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ActiveProfiles("qa")
class QaConfigurationTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void activeProfileRegistersQaFilter() {
        assertThat(
                context.getBeansOfType(QaMarkerFilter.class))
                .hasSize(1);

        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Global-Filter", "visited")
                .expectHeader()
                .valueEquals("X-Profile-Filter", "qa")
                .expectBody(String.class)
                .isEqualTo("public");
    }

    @Test
    void securityIsAppliedToAnonymousRequest() {
        client.get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader()
                .valueEquals("X-Global-Filter", "visited");
    }

    @Test
    void wrongRoleIsForbidden() {
        client.mutateWith(
                        mockUser("guest").roles("GUEST"))
                .get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void readerRoleCanAccessPrivateEndpoint() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("private");
    }

    @Test
    void postWithoutCsrfIsRejected() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postWithCsrfIsAccepted() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .mutateWith(csrf())
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("hello")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("length=5");
    }

    @Test
    void codecAcceptsBodyBelowQaLimit() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .mutateWith(csrf())
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("A".repeat(32))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("length=32");
    }

    @Test
    void codecRejectsBodyAboveQaLimit() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .mutateWith(csrf())
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("A".repeat(256))
                .exchange()
                .expectStatus().isEqualTo(413);
    }
}
```

Tám test này chứng minh filter chung và filter qa được đăng ký thật, HTTP security chain đang hoạt động, role và CSRF được áp dụng, và giới hạn codec 128B có hiệu lực với request `text/plain` đang được decode.

**Lưu ý:** `codecRejectsBodyAboveQaLimit` kỳ vọng 413 theo Spring Framework 6.2 với default error handling cho `DataBufferLimitException` trong đường `@RequestBody`. Nếu ứng dụng thêm `@ControllerAdvice`/`WebExceptionHandler` tùy chỉnh, hãy kiểm tra mapping status thực tế; không sửa test cho 200/500 chỉ để “pass”.

### 8.10. ProductionProfileTest.java

```java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@ActiveProfiles("prod")
class ProductionProfileTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void qaFilterIsAbsentInProdProfile() {
        assertThat(
                context.getBeansOfType(QaMarkerFilter.class))
                .isEmpty();

        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Global-Filter", "visited")
                .expectHeader()
                .doesNotExist("X-Profile-Filter");
    }

    @Test
    void baseCodecLimitAllows256ByteBody() {
        client.mutateWith(
                        mockUser("alice").roles("READER"))
                .mutateWith(csrf())
                .post()
                .uri("/api/echo")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("B".repeat(256))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("length=256");
    }

    @Test
    void securityStillAppliesInProd() {
        client.get()
                .uri("/api/private")
                .exchange()
                .expectStatus().isUnauthorized();
    }
}
```

Trong profile prod, `application.properties` cấp 1 KiB cho codec; 256 byte là hợp lệ. Filter qa không được tạo, nhưng filter chung và security vẫn còn. Test chứng minh sự khác nhau giữa hai profile **bằng hành vi HTTP**, không chỉ bằng giá trị Environment.

### 8.11. Chạy test và kết quả dự kiến

Cài JDK 17+, Maven, rồi chạy tại thư mục có `pom.xml`:

```bash
mvn test
```

Kết quả logic dự kiến (không phụ thuộc timestamp hoặc thứ tự JUnit):

| Nhóm test | Số test | Kỳ vọng |
|---|---:|---|
| QaConfigurationTest | 8 | PASS: filter qa, 401, 403, 200, CSRF, codec 128B |
| ProductionProfileTest | 3 | PASS: filter qa vắng mặt, codec 1KB, security vẫn bật |
| **Tổng** | **11** | **11 test PASS**, Maven exit code `0` |

Không có HTTP server thực được mở vì dùng `WebEnvironment.MOCK`. Điều này phù hợp để test ApplicationContext, mapping và Spring Security WebFilterChain. Khi triển khai production vẫn cần smoke tests qua port thật, reverse proxy, TLS, gateway và external IDP.

Nếu muốn chạy riêng:

```bash
mvn -Dtest=QaConfigurationTest test
mvn -Dtest=ProductionProfileTest test
```

Đừng viết test phụ thuộc vào thứ tự chạy hai class. Spring TestContext tạo/cached context theo active profiles và các thuộc tính; cả hai profile cần có kết quả nhất quán khi chạy riêng hoặc song song.

## 9. Mở rộng bằng @WebFluxTest slice

`@WebFluxTest` phù hợp khi muốn test controller và codec nhưng không cần khởi động toàn bộ application. Ví dụ khung:

```java
@WebFluxTest(controllers = ApiController.class)
@Import(SecurityConfiguration.class)
@ActiveProfiles("qa")
class ApiSliceTest {

    @Autowired
    WebTestClient webClient;

    // Có thể cần explicit import WebFilter/configurer,
    // và bind/apply security test support tùy test setup.
}
```

**Không coi snippet này là project độc lập.** Mặc định slice không scan toàn bộ `@Component` và không tự load custom `SecurityWebFilterChain`. `@Import(SecurityConfiguration.class)` làm rule được đưa vào context; nếu test yêu cầu `GlobalMarkerFilter` hoặc `QaMarkerFilter`, import chúng rõ ràng và đảm bảo có security test support.

Nếu controller có service dependency, dùng `@MockitoBean` từ `org.springframework.test.context.bean.override.mockito.MockitoBean` ở Spring Framework 6.2 thay vì tạo toàn bộ database/broker chỉ cho test controller. `@MockBean` của Spring Boot đã deprecated ở thế hệ Boot 3.4+; code mới nên chọn `@MockitoBean`.

Với functional endpoint `RouterFunction`, `@WebFluxTest` không tự phát hiện route. Import RouterFunction bean hoặc dùng full `@SpringBootTest`.

### 9.1. Khi nào không dùng slice?

Không dùng slice để tuyên bố các điều sau nếu bean tương ứng không được load:

- Profile-specific bean của toàn ứng dụng hoạt động.
- Custom filters chạy đúng với security proxy.
- Codec customizer do auto-configuration phụ thuộc bean khác được áp dụng.
- Error handler, routing function và metrics filter production đã có mặt.
- Authentication provider kết nối với database/IDP hoạt động thật.

Slice test hữu ích vì nhanh và cô lập. Khi kiểm chứng tích hợp giữa filter–profile–codec–security, full context test thường có sức chứng minh cao hơn.

## 10. Test HTTP server thật với RANDOM_PORT

Nếu mục tiêu là xác minh cả Reactor Netty adapter, header serialization, compression, HTTP protocol và transport behavior, dùng:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("qa")
class LiveWebFluxSmokeTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointWorksOverHttp() {
        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-Global-Filter", "visited");
    }
}
```

Đây là snippet bổ sung cần các imports JUnit/Spring. WebTestClient ở đây giao tiếp với embedded server **qua HTTP thực**. Test chỉ dùng anonymous public endpoint nên không cần credentials.

Không gọi `client.mutateWith(mockUser())` trên live client rồi coi đó là authentication qua network. Test Basic Authentication nên cấu hình một test user details service và gửi `Authorization: Basic ...` bằng `headers(headers -> headers.setBasicAuth(...))`; test JWT nên gửi token đã ký bởi test issuer. Secret giả trong test không được lẫn với secret production.

Đừng dùng `@Transactional` ở test phía client rồi kỳ vọng transaction DB bên server thực tự rollback cùng test. HTTP client/server thực là các execution khác nhau; cleanup test fixture phải có chiến lược riêng.

## 11. CSRF, authentication và authorization là ba nhóm test

- **Authentication:** client chứng minh danh tính bằng HTTP Basic, JWT, OAuth2 hoặc session. `mockUser` bỏ qua giai đoạn xác minh credential.
- **Authorization:** danh tính đã có có được phép gọi route/method? Test bằng `mockUser`, `mockJwt`, role/scope/authority.
- **CSRF:** với browser/session cookie, request state-changing cần token hợp lệ; test POST thiếu và có token.

Ví dụ matrix:

| Request | Test principal | CSRF | Kết quả mong đợi |
|---|---|---|---|
| GET /api/public | anonymous | Không cần | 200 |
| GET /api/private | anonymous | Không cần | 401 |
| GET /api/private | GUEST | Không cần | 403 |
| GET /api/private | READER | Không cần | 200 |
| POST /api/echo | READER | Thiếu | 403 |
| POST /api/echo | READER | Có | 200 |
| POST /api/echo | anonymous | Có | 401/403 tùy entry-point/rule ordering; cần xác định |
| GET /unknown | READER | Không cần | 403 theo denyAll |

Với request có nhiều lớp chặn, **trạng thái phụ thuộc lớp xử lý trước**. Không hard-code 401 cho mọi anonymous POST khi CSRF filter có thể từ chối trước authentication entry point.

Nếu ứng dụng dùng JWT resource server, bổ sung test: sai issuer, sai audience, expired, invalid signature, missing scope, revoked token nếu có introspection. Mock JWT chỉ test authorization rule; test signature thật cần gửi signed token qua live server.

## 12. Kiểm thử Filter ordering và error handling có tính an toàn

Các filter audit/rate-limit/auth không nên làm rò thông tin qua response:

- Request bị 401/403 vẫn phải có security headers cần thiết.
- Không gửi user ID, raw token hoặc internal stack trace trong header debug.
- CORS preflight được phân biệt với anonymous business request.
- Filter không được nuốt `onError` làm business request trả 200.
- Filter bổ sung Reactor Context phải truyền đúng khi handler đổi scheduler.
- Response đã commit không thể tùy ý ghi status/headers nữa.

Khi kiểm tra thứ tự, nên assert cả **side effect an toàn** và absence của side effect không mong muốn. Ví dụ filter authentication phải chạy trước handler tạo business side effect, không chỉ kiểm tra response status. Với side-effecting POST, dùng spy/test repository để assert handler không chạy khi security từ chối.

### 12.1. CORS và WebFilter

CORS có thể được cấu hình trong `WebFluxConfigurer` hoặc Spring Security CORS integration. Preflight request `OPTIONS` cần kiểm tra `Origin`, `Access-Control-Request-Method` và những header trả về.

Ví dụ test:

```java
client.options()
        .uri("/api/private")
        .header("Origin", "https://frontend.example")
        .header("Access-Control-Request-Method", "GET")
        .exchange();
```

Status và headers mong đợi phải dựa trên CORS policy thực tế. Không thể assert `Access-Control-Allow-Origin: *` khi policy cho phép credentials hoặc whitelist origin.

Một preflight được CORS filter xử lý có thể không đi qua authorization business như GET thực. Vì vậy test cả preflight và request thật từ origin được phép/không được phép.

## 13. Codec negotiation, JSON errors và multipart

Bên cạnh body size, bổ sung test:

1. POST với `Content-Type` sai phải ra 415 nếu endpoint quy định consumes.
2. GET với `Accept` không tương thích phải ra 406 khi Spring không có representation phù hợp.
3. JSON thiếu trường được validate → 400; không coi đó là lỗi codec 413.
4. Jackson custom serialization có giá trị định dạng đúng.
5. Dữ liệu Unicode có thể round-trip bằng UTF-8.
6. `spring.http.codecs.max-in-memory-size` ảnh hưởng đúng endpoint cần aggregate.
7. NDJSON hoặc SSE streaming không bị test `collectList()` vô hạn.
8. Multipart có max parts, max memory, max disk usage và cleanup.

Ví dụ test 415:

```java
client.mutateWith(mockUser().roles("READER"))
        .mutateWith(csrf())
        .post()
        .uri("/api/echo")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue("{\"x\":1}")
        .exchange()
        .expectStatus().isEqualTo(415);
```

Đừng mặc định endpoint raw `Flux<DataBuffer>` bị ảnh hưởng bởi codec limit như DTO aggregate. Nếu cần limit tổng upload, test byte counter hoặc gateway policy riêng.

## 14. Test profile configuration và điều kiện bean

Ngoài HTTP behavior, assert bean conditions:

```java
assertThat(context.getBeansOfType(QaMarkerFilter.class))
        .hasSize(1);
```

Và ở profile khác:

```java
assertThat(context.getBeansOfType(QaMarkerFilter.class))
        .isEmpty();
```

Khi ứng dụng có nhiều `@ConditionalOnProperty` hoặc `@Profile("!prod")`, cần kiểm tra **cả điều kiện đúng lẫn sai**; chỉ một test positive có thể bỏ sót việc bean xuất hiện cả trong production.

`ApplicationContextRunner` / `ReactiveWebApplicationContextRunner` hữu ích cho việc test một auto-configuration nhỏ theo nhiều cặp property, nhưng runner đơn giản không tự tạo toàn bộ Boot server, security chain hoặc controller của ứng dụng. Dùng nó cho bean graph/condition, rồi dùng WebTestClient integration cho behavior.

### 14.1. TestPropertySource, DynamicPropertySource và precedence

- `@ActiveProfiles` chọn profile trước khi context được tạo.
- `@TestPropertySource` override những test-specific properties; đặt tên key đúng version.
- `@DynamicPropertySource` đăng ký value được tạo lúc test runtime (container port, endpoint).
- `@SpringBootTest(properties = "...")` phù hợp cho vài override cố định.
- Environment variable và command-line có precedence riêng; không giả định một file application-prod luôn là nguồn cuối cùng.

Khi chạy CI với profile không rõ, có thể assert:

```java
assertThat(context.getEnvironment()
        .acceptsProfiles(Profiles.of("qa")))
        .isTrue();
```

Đây là snippet cần `org.springframework.core.env.Profiles`. Với test profile prod, kiểm tra ngược lại. Tuy nhiên kiểm tra Environment một mình không chứng minh filter thực sự chạy; kết hợp HTTP assertion.

## 15. Đừng tự động vô hiệu hóa bảo mật trong test

Những “shortcut” sau khiến test báo xanh nhưng không bao phủ cấu hình:

- `@WebFluxTest` không import custom security configuration nhưng vẫn test private route như thể nó được bảo vệ.
- `WebTestClient.bindToController` test endpoint trực tiếp rồi cho rằng WebFilter đã chạy.
- Cấu hình test profile dùng `permitAll()` trên mọi path.
- Vô hiệu hóa `csrf` trong test riêng khi production yêu cầu CSRF.
- Dùng `mockUser` rồi tuyên bố JWT signature/issuer đã được xác minh.
- Mock toàn bộ `ServerHttpSecurity` thay vì dùng bean chain thật.
- Chỉ assert 200 mà không assert 401/403.
- Chỉ assert có filter bean mà không gửi HTTP request.
- Thay property sau khi context đã cache mà không tạo context mới.

Cách khắc phục: tách mục tiêu **unit**, **context integration** và **live-server/security integration**. Mỗi test có tên mô tả ranh giới mà nó thực sự chứng minh.

## 16. Đánh giá kết quả và chẩn đoán khi test fail

### 16.1. Khi GET private bất ngờ 200

Kiểm tra theo thứ tự:

1. Test đang dùng `bindToController` thay vì ApplicationContext?
2. `SecurityWebFilterChain` có được đăng ký vào context?
3. `springSecurity()` có được apply cho mock WebTestClient?
4. Security rule có permitAll quá rộng hoặc path matcher sai?
5. Filter order có bỏ qua security hay test dùng một client đã mock identity?
6. App đang chạy WebFlux hay bị chọn Spring MVC do classpath?

### 16.2. Khi POST không token vẫn trả 200

Kiểm tra CSRF có bị disable trong configuration/test profile không, endpoint có thuộc scope bị bỏ qua không, test client có mutateWith(csrf()) toàn cục không, và request có thực sự là POST/PUT/PATCH/DELETE cần token không.

Với stateless bearer-only API, CSRF có thể được chủ động tắt theo threat model. Khi đó expected test phải xuất phát từ security design, không sao chép sample browser-session.

### 16.3. Khi body 256B vẫn được nhận trong profile qa

Kiểm tra:

- `@ActiveProfiles("qa")` có được dùng?
- `application-qa.properties` đặt đúng thư mục và key Boot 3.5?
- Có custom `@EnableWebFlux` làm Boot WebFlux auto-config back off?
- Đang dùng raw streaming body thay vì codec aggregate?
- Codec customizer có bị thay thế bởi bean riêng?
- Client có gửi đúng media type và body thực sự được decoder đọc?
- Test có mock controller/service bỏ qua input body?

### 16.4. Khi request trả 403 thay vì 401

CSRF có thể từ chối POST trước authentication. HTTP Basic entry point, form login, bearer-token resource server và custom access-denied handler có semantics khác nhau. Hãy xác định loại authentication/authorization error, không đổi expected response một cách tùy tiện.

### 16.5. Khi test pass riêng nhưng fail khi chạy suite

Xem TestContext cache, global mutable state, `System.setProperty`, shared in-memory database, test fixture, order dependency, random port, security context cleanup và `@DirtiesContext`. Tránh ghi state vào singleton hoặc static field trong WebFilter để đếm request.

## 17. Bảng kiểm thử tối thiểu cho CI

| Ca kiểm thử | Cơ chế | Kỳ vọng |
|---|---|---|
| Public request anonymous | Full context WebTestClient | 200 |
| Private request anonymous | Spring Security chain | 401 |
| Private request wrong role | `mockUser` | 403 |
| Private request correct role | `mockUser` | 200 |
| POST correct user, no CSRF | Security test support | 403 |
| POST correct user + CSRF | `mutateWith(csrf())` | 200 |
| Global WebFilter | Response marker | Có header |
| QA-only filter | `@ActiveProfiles("qa")` | Header có |
| QA filter in prod | `@ActiveProfiles("prod")` | Bean/header vắng |
| Codec 32B in qa | HTTP request decode | 200 |
| Codec 256B in qa | HTTP request decode | 413 |
| Codec 256B in prod | HTTP request decode | 200 |
| Content type sai | `consumes` | 415 |
| JSON hoặc validation sai | Codec/validation | 400 theo contract |
| Real network smoke | RANDOM_PORT | Headers/status đúng |
| Authorization provider/JWT thật | Real credentials/token | Từ chối token sai |
| CORS preflight | Origin/header/method | Đúng policy |
| Timeout, upload lớn | Live server/proxy | Đúng policy và cleanup |

**Lưu ý về coverage:** 11 test runnable trong project tập trung filter, profile, codec và role/CSRF. Các dòng “real network”, token verifier, CORS, multipart cần thêm cấu hình và test theo ứng dụng thực tế; không tuyên bố chúng đã được chứng minh bởi mock-context test.

## 18. Checklist code review

Trước khi merge thay đổi WebFlux configuration, hỏi:

- `WebTestClient` đang bind controller, router, context hay server thật?
- Test có load full `WebFilter` và `SecurityWebFilterChain` mà production sử dụng không?
- `@WebFluxTest` có thiếu `@Import` cho security/codec/functional routes không?
- Profile được chọn bằng `@ActiveProfiles` trước context creation chưa?
- Có test profile dương và âm, không chỉ assert Environment?
- Property key đúng Spring Boot version và có được override ở qa/prod không?
- Codec được test qua body thật và cả ca vượt limit?
- Có test 415/400/406 và kiểm tra content negotiation?
- Anonymous, wrong role, correct role và CSRF được kiểm tra độc lập?
- Có vô tình tắt CSRF/security trong test để cho 200 không?
- Mock identity có bị hiểu lầm là kiểm tra auth provider/JWT signature không?
- Filter có giữ state per request và tôn trọng error/cancel không?
- Nếu filter thay đổi response, thứ tự và commit state có được test?
- Có test với server thật cho adapter, TLS, proxy, timeouts khi cần?
- Có test logging không lộ headers/body/token và không tạo metric labels cardinality cao?
- Test chạy độc lập, không phụ thuộc thứ tự và không dùng mutable global profile?
- Cảnh báo Context cache, thread switch và Reactor Context đã được cân nhắc?
- CI có test report và fail khi exception/status khác contract?

**Ghi nhớ:** Muốn kiểm chứng WebFlux **filter–profile–codec–security**, phải dùng đúng test boundary. `@WebFluxTest` nhanh nhưng không tự nạp tất cả bean/filter/custom security; `@SpringBootTest(MOCK)` và `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` thích hợp để kiểm tra full Spring chain mà không cần socket. `@ActiveProfiles` kiểm chứng bean/property theo môi trường; HTTP request body kiểm chứng codec thực; `mockUser` kiểm chứng authorization, `csrf()` kiểm chứng CSRF. Với JWT/HTTP Basic transport, TCP, TLS, proxy hoặc gateway, thêm live-server integration test. Luôn có cả positive và negative assertions để tránh “test xanh nhưng production sai”.

## Tài liệu tham khảo

- Spring Boot 3.5.16 — [Testing Spring Boot Applications, Auto-configured Spring WebFlux Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html).
- Spring Framework 6.2 — [WebTestClient setup: bindToController, bindToApplicationContext, bindToServer](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html).
- Spring Security 6.5 — [Reactive Test Support: WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html).
- Spring Security 6.5 — [Reactive Testing Authentication with mockUser](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html).
- Spring Security 6.5 — [Testing with CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html).
- Spring Framework 6.2 — [WebFlux @RequestBody and reactive arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html).
- Spring Framework 6.2 — [Reactive Core: codec buffering limits](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html).
- Spring Boot 3.5 — [Common Application Properties: spring.http.codecs.max-in-memory-size](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html).
- Spring Framework 6.2 — [@ActiveProfiles Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/ActiveProfiles.html).
- Spring Framework 6.2 — [@MockitoBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html).
- Spring Framework — [PayloadTooLargeException Javadoc for Spring 6.2](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/server/PayloadTooLargeException.html).
