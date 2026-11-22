# RestClientCustomizer, RestTemplateCustomizer và WebClientCustomizer trong Spring Boot

## 1. Mục tiêu: tùy biến HTTP client mà không bỏ qua Spring Boot

Một ứng dụng Spring Boot có thể gọi nhiều HTTP API downstream: hồ sơ khách hàng, thanh toán, kho hàng, báo cáo. Mỗi client cần các lựa chọn khác nhau về base URL, thời gian chờ, TLS, header, cơ chế ghi log, kiểm tra lỗi và tracing. Nếu code ở mọi service đều tạo `new RestTemplate()`, `RestClient.create()` hoặc `WebClient.create()`, bạn dễ bỏ qua những thành phần HTTP client đã được Spring Boot tự cấu hình.

Spring Boot 3.3 cung cấp ba callback theo từng loại client:

- **`RestClientCustomizer`:** thay đổi `RestClient.Builder`, dành cho client có API fluent **blocking**.
- **`RestTemplateCustomizer`:** thay đổi **đối tượng `RestTemplate`** sau khi builder khởi tạo, dành cho API blocking lâu đời.
- **`WebClientCustomizer`:** thay đổi `WebClient.Builder`, dành cho HTTP client **reactive** với `Mono` và `Flux`.

Ba cơ chế có tên gần nhau nhưng **không dùng thay thế nhau**. `RestTemplateCustomizer` không nhận builder; nó nhận RestTemplate thật. `RestClientCustomizer` không tác động đến RestTemplate. `WebClientCustomizer` không làm RestClient chuyển thành non-blocking.

Bài học sử dụng **Java 17+, Spring Boot 3.3.13, Spring Framework 6.1, Gradle**. Mục tiêu thực hành gồm tạo ba bean customizer, chạy một HTTP endpoint, viết integration tests chứng minh header được gắn, biết khi nào dùng cấu hình local/global, và hiểu các rủi ro khi tự tạo client hay ghi đè HTTP transport.

## 2. Bảng so sánh ba interface

| Khía cạnh | `RestClientCustomizer` | `RestTemplateCustomizer` | `WebClientCustomizer` |
|---|---|---|---|
| Loại client | `RestClient` | `RestTemplate` | `WebClient` |
| Giao thức lập trình | Blocking, fluent API | Blocking, classic API | Reactive, Publisher-based |
| Phương thức | `customize(RestClient.Builder)` | `customize(RestTemplate)` | `customize(WebClient.Builder)` |
| Callback chạy trên | Builder đã được Boot chuẩn bị | Template được `RestTemplateBuilder` tạo | Builder đã được Boot chuẩn bị |
| Cách dùng tiêu chuẩn | Inject `RestClient.Builder` | Inject `RestTemplateBuilder` | Inject `WebClient.Builder` |
| Cấu hình hay dùng | `defaultHeader`, interceptor, status handler | Interceptors, error handler, request factory | `defaultHeader`, exchange filter, connector |
| Đường tạo trực tiếp bỏ qua customizer Boot | `RestClient.create()` | `new RestTemplate()` | `WebClient.create()` |
| Điều kiện đặc biệt | Boot 3.3 có điều kiện với application không phải reactive web | Boot tự cung cấp builder, không cung cấp sẵn singleton RestTemplate | Phải có WebClient trên classpath |

**Package chính xác của Spring Boot 3.3:**

```java
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;

import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;
```

Đây là đoạn imports để tham khảo, không phải file Java hoàn chỉnh. Những API client thuộc Spring Framework, còn những `*Customizer` nêu trên thuộc Spring Boot 3.3. Khi đọc hướng dẫn Boot 4.x cần kiểm tra package trước khi copy vì những API có thể đã được chuyển vị trí.

## 3. Vì sao Spring Boot khuyến nghị inject builder?

### 3.1. Auto-configuration dành cho RestClient

Trong điều kiện phù hợp, Spring Boot 3.3 cung cấp bean `RestClient.Builder` **prototype**. Builder được cấu hình với `HttpMessageConverters`, `ClientHttpRequestFactory` và customizers được đăng ký. Mỗi injection point thông thường nhận một builder đã được chuẩn bị; service dùng builder để tạo một `RestClient` có cấu hình riêng.

```text
@Bean RestClientCustomizer ...
             │
             ▼
Boot RestClientAutoConfiguration
             │
             ▼
RestClient.Builder prototype
             │
       Service inject builder
             │
       baseUrl, headers, ...
             │
             ▼
          build()
             │
             ▼
    RestClient (blocking)
```

**Lưu ý riêng cho Boot 3.3:** `RestClientAutoConfiguration` có điều kiện `NotReactiveWebApplicationCondition`. Vì vậy **một ứng dụng chỉ chạy WebFlux reactive** không nhất thiết có bean RestClient.Builder tự động như ứng dụng MVC. Không nên mặc định tất cả builder đều tồn tại chỉ vì class API có mặt.

### 3.2. Auto-configuration dành cho RestTemplate

Boot **không tự cung cấp một RestTemplate singleton mặc định**. Thay vào đó, Boot tạo `RestTemplateBuilder`. Gọi `build()` sẽ xây RestTemplate, áp cấu hình request factory/converters và customizers phù hợp:

```text
@Bean RestTemplateCustomizer ...
             │
             ▼
Auto-configured RestTemplateBuilder
             │
       .setReadTimeout(...)
             │
             ▼
           build()
             │
             ▼
RestTemplate được tạo/configure
             │
 RestTemplateCustomizer.customize(template)
             │
             ▼
 RestTemplate hoàn chỉnh
```

Đây là khác biệt quan trọng về **thời điểm**: callback tùy biến RestTemplate chạy khi tạo/configure template, không phải mỗi lần HTTP request được gửi.

`RestTemplateBuilder` trả builder mới khi gọi method cấu hình, ví dụ:

```java
RestTemplate template = builder
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(5))
        .build();
```

Đây là mảnh code trong service đã inject `RestTemplateBuilder builder` và import `Duration`. Nếu bạn gọi `builder.setReadTimeout(...)` rồi **bỏ giá trị trả về**, builder gốc không bị sửa theo ý định. Hãy dùng chain hoặc gán kết quả mới.

### 3.3. Auto-configuration dành cho WebClient

Khi `WebClient` có mặt, Spring Boot cung cấp `WebClient.Builder` **prototype**, chuẩn bị codec, HTTP connector và tài nguyên dùng chung phù hợp. Các `WebClientCustomizer` bean được áp cho builder này.

```text
@Bean WebClientCustomizer ...
             │
             ▼
Boot WebClientAutoConfiguration
             │
             ▼
WebClient.Builder prototype
             │
             ▼
           build()
             │
             ▼
WebClient request → Mono/Flux
             │
        subscription
             │
             ▼
          HTTP I/O
```

`RestClient.Builder` và `WebClient.Builder` đều **mutable/stateful**: sửa cùng một builder có thể tác động đến những client build sau. Nếu tạo nhiều clients từ một builder instance, dùng `clone()` để giữ settings tách biệt. Sau khi build, thường inject client đã được cấu hình làm singleton, không tiếp tục mutate builder dùng chung giữa nhiều threads.

## 4. Phạm vi tùy biến: local, global hay thủ công

### Cấp 1: chỉ một client

```java
RestClient billing = restBuilder.clone()
        .baseUrl("https://billing.example.test")
        .defaultHeader("X-Client-Name", "billing")
        .build();

WebClient inventory = webBuilder.clone()
        .baseUrl("https://inventory.example.test")
        .defaultHeader("X-Client-Name", "inventory")
        .build();

RestTemplate reports = templateBuilder
        .setReadTimeout(Duration.ofSeconds(7))
        .build();
```

Đoạn này là **mảnh minh họa** trong class đã inject builders và import `Duration`; miền `example.test` không phải hệ thống HTTP thật. Local settings phù hợp base URL/credential/trust bundle/timeout riêng cho một đối tác.

### Cấp 2: policy chung cho mọi client cùng family

```java
@Bean
RestClientCustomizer appTag() {
    return builder -> builder.defaultHeader(
            "X-Application-Name", "order-api");
}
```

Mảnh code thuộc một `@Configuration` class, cần imports tương ứng. Bean được Boot thu thập và áp cho các **RestClient.Builder do Boot cung cấp**. Đây là cấu hình application-wide **trong phạm vi RestClient**, không phải toàn bộ outbound HTTP clients của JVM.

### Cấp 3: tạo client trực tiếp, chủ động bỏ auto-configuration

```java
RestClient rawRestClient = RestClient.create();
RestTemplate rawTemplate = new RestTemplate();
WebClient rawWebClient = WebClient.create();
```

Các client này có mặc định riêng của Spring Framework, nhưng **không tự nhận các bean customizer của Boot**. Có thể dùng chúng khi chủ đích tự cấu hình hoàn toàn; không nên sử dụng theo thói quen rồi ngạc nhiên vì thiếu timeout, TLS bundle hoặc observation.

**Nguyên tắc thực tế:** ưu tiên builder của Boot; dùng customizer chung cho policy trung tính, dùng client bean riêng cho đối tác và credentials riêng. Không đặt API token hoặc Authorization của partner A trong một global customizer, vì client tới partner B có thể gửi nhầm secret.

## 5. Ví dụ project Java 17+ chạy đủ ba client

Ví dụ duy nhất dưới đây dùng **Spring Boot 3.3.13** và có server **Spring MVC/Tomcat**. Thêm WebFlux starter để có `WebClient` outbound, không chuyển server sang reactive. Một endpoint `GET /echo` phản hồi giá trị header `X-Demo-Client`. Mỗi customizer gắn một giá trị khác nhau, giúp test kiểm chứng cả ba family.

### 5.1. Cấu trúc

```text
http-client-customizers/
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/clients/HttpClientApplication.java
    │   └── resources/application.properties
    └── test/
        └── java/com/example/clients/HttpClientCustomizerTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Hai starters cùng xuất hiện có chủ đích: MVC để có server Tomcat, WebFlux để có `WebClient`. RestClient và RestTemplate vẫn **blocking**. Chỉ cần một project có cả ba clients để quan sát; production nên chọn dependencies thật sự cần.

**`src/main/resources/application.properties`:**

```properties
server.port=8080
spring.application.name=http-client-customizers
```

### 5.2. Application, customizer beans và endpoint

**`src/main/java/com/example/clients/HttpClientApplication.java`:**

```java
package com.example.clients;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.boot.web.client.RestTemplateCustomizer;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class HttpClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(HttpClientApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ClientCustomization {

    @Bean
    RestClientCustomizer restClientCustomizer() {
        // Tham số là RestClient.Builder, không phải RestClient.
        return builder -> {
            builder.defaultHeader("X-Demo-Client", "rest-client");
        };
    }

    @Bean
    RestTemplateCustomizer restTemplateCustomizer() {
        // Tham số là RestTemplate đã được RestTemplateBuilder tạo.
        return template -> {
            template.getInterceptors().add((request, body, execution) -> {
                request.getHeaders().set(
                        "X-Demo-Client", "rest-template");
                return execution.execute(request, body);
            });
        };
    }

    @Bean
    WebClientCustomizer webClientCustomizer() {
        // Tham số là WebClient.Builder.
        return builder -> {
            builder.defaultHeader("X-Demo-Client", "web-client");
        };
    }
}

@RestController
class EchoController {
    @GetMapping(
            path = "/echo",
            produces = MediaType.TEXT_PLAIN_VALUE)
    String echo(
            @RequestHeader(
                    value = "X-Demo-Client",
                    required = false) String source) {
        return source == null ? "missing" : source;
    }
}
```

Chỉ có một top-level `public class` trong file. Hai class còn lại package-private được Spring Boot component scan vì cùng package với application. Ở đây:
- `RestClientCustomizer` thêm default header vào builder.
- `RestTemplateCustomizer` gắn một `ClientHttpRequestInterceptor` vào template. **Callback tạo interceptor chỉ chạy lúc build**; lambda interceptor bên trong mới chạy mỗi request.
- `WebClientCustomizer` thêm default header vào builder.
- `EchoController` trả chuỗi request header nhìn thấy, hoặc `missing` nếu không có.

Không có code tự `subscribe()` hay gửi request khi khởi tạo customizer. Các customizers được dùng để **thiết lập client**, không phải trực tiếp gọi downstream.

### 5.3. Chạy và dùng curl

Trong project có JDK 17+, Gradle tương thích:

```bash
gradle bootRun
```

Nếu đã tạo Gradle Wrapper, có thể dùng `./gradlew bootRun` (macOS/Linux), hoặc `.\gradlew.bat bootRun` trong Windows PowerShell.

```bash
curl -s http://localhost:8080/echo
curl -s -H "X-Demo-Client: manually-set" http://localhost:8080/echo
```

Body dự kiến lần lượt là:

```text
missing
manually-set
```

`curl` không được Java customizer tác động; header thứ hai là do câu lệnh gửi rõ ràng. Để quan sát Spring Boot customizer, phải dùng các Java clients xây từ Boot builders, như integration test bên dưới.

## 6. Integration test chứng minh ba customizers hoạt động

Test chạy server trên cổng bất kỳ, inject builders do Boot auto-configure, gửi HTTP thật đến `/echo` và assert response. Vì có cả starter web và webflux nhưng server chọn MVC, Boot có đủ các builders trong ví dụ này.

**`src/test/java/com/example/clients/HttpClientCustomizerTest.java`:**

```java
package com.example.clients;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.reactive.function.client.WebClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class HttpClientCustomizerTest {

    @LocalServerPort
    int port;

    @Autowired
    RestClient.Builder restClientBuilder;

    @Autowired
    RestTemplateBuilder restTemplateBuilder;

    @Autowired
    WebClient.Builder webClientBuilder;

    private String localUrl() {
        return "http://localhost:" + port + "/echo";
    }

    @Test
    void restClientReceivesHeader() {
        String body = restClientBuilder.build()
                .get()
                .uri(localUrl())
                .retrieve()
                .body(String.class);

        assertEquals("rest-client", body);
    }

    @Test
    void restTemplateReceivesHeader() {
        RestTemplate client = restTemplateBuilder.build();
        String body = client.getForObject(
                localUrl(), String.class);

        assertEquals("rest-template", body);
    }

    @Test
    void webClientReceivesHeader() {
        String body = webClientBuilder.build()
                .get()
                .uri(localUrl())
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(5));

        assertEquals("web-client", body);
    }

    @Test
    void directFactoryDoesNotSeeBootCustomizers() {
        String a = RestClient.create()
                .get()
                .uri(localUrl())
                .retrieve()
                .body(String.class);

        String b = new RestTemplate()
                .getForObject(localUrl(), String.class);

        String c = WebClient.create()
                .get()
                .uri(localUrl())
                .retrieve()
                .bodyToMono(String.class)
                .block(Duration.ofSeconds(5));

        assertEquals("missing", a);
        assertEquals("missing", b);
        assertEquals("missing", c);
    }
}
```

Chạy:

```bash
gradle test
```

**Kết quả kỳ vọng khi môi trường và dependencies đúng:** cả bốn test pass. Đây là mục tiêu được suy ra từ code và Spring API, **chưa phải bằng chứng đã chạy Gradle**.

| Test | Client khởi tạo từ đâu | Body trả về |
|---|---|---|
| `restClientReceivesHeader` | `RestClient.Builder` được Boot inject | `rest-client` |
| `restTemplateReceivesHeader` | `RestTemplateBuilder` được Boot inject | `rest-template` |
| `webClientReceivesHeader` | `WebClient.Builder` được Boot inject | `web-client` |
| `directFactoryDoesNotSeeBootCustomizers` | `RestClient.create()`, `new RestTemplate()`, `WebClient.create()` | Ba giá trị `missing` |

`block(Duration.ofSeconds(5))` được sử dụng **chỉ trong JUnit thread** để assert kết quả một cách thuận tiện. Không copy `block()` vào WebFlux event-loop handler. Trong service WebFlux thật, return/compose `Mono` và để framework subscribe.

Một test thật có cổng ngẫu nhiên chứng minh client đã gửi HTTP qua network đến đúng controller và header cuối cùng được server nhìn thấy. Nó có giá trị hơn chỉ kiểm tra customizer bean tồn tại trong Spring context.

## 7. Customizer chạy lúc nào, interceptor chạy lúc nào?

Một số log gây nhầm lẫn:
- Log trong `RestClientCustomizer.customize` xuất hiện khi builder được cấu hình, **không phải mỗi outbound request**.
- Log trong `RestTemplateCustomizer.customize` xuất hiện khi template được build/configure.
- Log trong `WebClientCustomizer.customize` xuất hiện khi builder được chuẩn bị, không bảo đảm một request đã được subscribe.
- `ClientHttpRequestInterceptor.intercept` của RestClient/RestTemplate chạy **khi request được thực thi**.
- `ExchangeFilterFunction` trong WebClient tham gia **pipeline của request được subscribe**.

### 7.1. RestClient: builder callback và request interceptor

```java
@Bean
RestClientCustomizer requestTag() {
    return builder -> {
        builder.requestInterceptor((request, body, execution) -> {
            request.getHeaders().set(
                    "X-App-Instance", "orders");
            return execution.execute(request, body);
        });
    };
}
```

Mã minh họa này thuộc `@Configuration`, cần imports; nó tác động lên request thông qua interceptor đã được thêm vào builder. Không nên log raw body, token hoặc cookies tại đây.

### 7.2. RestTemplate: template callback và interceptor

```java
@Bean
RestTemplateCustomizer requestTag() {
    return template -> template.getInterceptors().add(
            (request, body, execution) -> {
                request.getHeaders().set(
                        "X-App-Instance", "orders");
                return execution.execute(request, body);
            });
}
```

`RestTemplateCustomizer` được gọi khi tạo template, nhưng lambda `intercept(...)` chạy cho các HTTP requests do template đó thực thi. Đừng nhầm với `RestTemplateRequestCustomizer`: giao diện này được dùng để tùy chỉnh một `ClientHttpRequest` theo contract của builder, không giống callback tác động lên template.

### 7.3. WebClient: reactive ExchangeFilterFunction

```java
@Bean
WebClientCustomizer requestTag() {
    return builder -> builder.filter((request, next) -> {
        ClientRequest tagged = ClientRequest.from(request)
                .header("X-App-Instance", "orders")
                .build();
        return next.exchange(tagged);
    });
}
```

Đoạn này dùng `ClientRequest` của Spring WebFlux; cần import `org.springframework.web.reactive.function.client.ClientRequest`. Một filter có thể đọc metadata và gửi request cho next function; nếu tự consume response body phải bảo đảm lifecycle và buffer release. **Không tự gọi `subscribe()` trong filter** làm mất cancel/error propagation.

**Thực hành:** dùng customizer để đăng ký interceptor/filter một lần; dùng interceptor/filter cho policy **theo từng request**.

## 8. Thứ tự customizers và sự khác biệt giữa additive/replace

Có thể có nhiều bean cùng interface, do ứng dụng hoặc một thư viện cung cấp. Spring hỗ trợ `@Order`/`Ordered` để kiểm soát thứ tự áp dụng trong cơ chế thu thập bean có sắp xếp. Nhưng **không nên dựa vào thứ tự ngẫu nhiên** hoặc mặc định “bean cuối thắng” cho mọi setter.

Một số method **bổ sung** cấu hình, trong khi method khác **thay thế** cấu hình:

| API | Ý nghĩa |
|---|---|
| `RestClient.Builder.defaultHeader(...)` | Đặt header mặc định, có thể bị request-level/interceptor tác động |
| `WebClient.Builder.filter(...)` | Thêm ExchangeFilterFunction theo thứ tự filter pipeline |
| `RestTemplate.getInterceptors().add(...)` | Thêm interceptor vào danh sách |
| `RestTemplate.setErrorHandler(...)` | Thay error handler hiện tại |
| `RestTemplate.setRequestFactory(...)` | Thay request factory |
| `RestTemplateBuilder.customizers(...)` | **Thay danh sách** customizers đã có |
| `RestTemplateBuilder.additionalCustomizers(...)` | Thêm customizer mà không thay toàn bộ |
| `RestTemplateBuilder.messageConverters(...)` | Chọn lại converters, có thể mất defaults |
| `RestTemplateBuilder.additionalMessageConverters(...)` | Bổ sung converters |

Ví dụ sắp thứ tự minh họa:

```java
@Bean
@Order(10)
RestClientCustomizer commonHeader() {
    return builder -> builder.defaultHeader(
            "X-Application", "order-service");
}

@Bean
@Order(20)
RestClientCustomizer commonStatusHandler() {
    return builder -> builder.defaultStatusHandler(
            status -> status.is5xxServerError(),
            (request, response) -> {
                throw new IOException("Downstream 5xx: "
                        + response.getStatusCode());
            });
}
```

Đây là **mảnh code** cần imports `Bean`, `Order`, `RestClientCustomizer`, `IOException`. Không phải file độc lập. `@Order` hữu ích khi callbacks có quan hệ thứ tự, nhưng policy tốt hơn là làm chúng tương đối độc lập. `defaultStatusHandler` sẽ tác động đến response khi gọi `retrieve()` theo contract, chứ không ném lỗi trong lúc Spring dựng builder.

Nếu một `RestTemplateCustomizer` thêm interceptor bằng `add(...)` và sau đó cùng template bị chạy callback lần nữa, interceptor có thể bị thêm trùng. Không tự invoke callback vô điều kiện trên client đã xây. Viết test kiểm tra số lần request đi qua filter nếu có nhiều module cùng customizer.

## 9. Khi nào dùng bean client riêng thay vì customizer global?

Với nhiều đối tác, bean client theo partner làm rõ trust boundary và cấu hình:

```java
@Configuration(proxyBeanMethods = false)
class PartnerClients {

    @Bean("billingClient")
    RestClient billing(RestClient.Builder builder) {
        return builder
                .baseUrl("https://billing.example.test")
                .defaultHeader("X-Service", "billing")
                .build();
    }

    @Bean("catalogClient")
    WebClient catalog(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.example.test")
                .defaultHeader("X-Service", "catalog")
                .build();
    }

    @Bean("legacyTemplate")
    RestTemplate legacy(RestTemplateBuilder builder) {
        return builder
                .rootUri("https://legacy.example.test")
                .setReadTimeout(Duration.ofSeconds(7))
                .build();
    }
}
```

Đây là **class minh họa** cần imports và downstream hosts thật; `example.test` chỉ là miền ví dụ. Các builder đến từ Boot nên vẫn giữ customizer global tương ứng. `RestTemplateBuilder.rootUri` áp cho các URI bắt đầu bằng `/` trong những phương thức tương ứng; URI tuyệt đối được xử lý riêng.

Khi đã có nhiều beans cùng type, sử dụng `@Qualifier("billingClient")` hoặc constructor với qualifier để tránh ambiguity. Nếu cần API key, Bearer token, mTLS certificate hoặc truststore riêng cho partner, cấu hình trên bean cụ thể thay vì gắn global. Dùng allowlist outbound URL và validate input để tránh SSRF khi base URL/URI có nguồn dữ liệu bên ngoài.

## 10. Timeout và HTTP transport: không phải mọi client giống nhau

Ba client khác nhau về API lẫn transport:

- `RestClient` và `RestTemplate` đều blocking. Timeout thường gắn với `ClientHttpRequestFactory` hoặc HTTP client underlying.
- `WebClient` trả `Mono/Flux`, dùng `ClientHttpConnector` (thường Reactor Netty nếu starter-webflux).
- Timeout kết nối, timeout chờ response, timeout tổng pipeline và timeout nghiệp vụ là những đại lượng khác nhau.
- Retry một POST không idempotent có thể tạo side effect hai lần nếu server đã xử lý xong nhưng response thất lạc.

### 10.1. RestTemplateBuilder trong Boot 3.3

```java
RestTemplate template = builder
        .setConnectTimeout(Duration.ofSeconds(2))
        .setReadTimeout(Duration.ofSeconds(5))
        .build();
```

Mảnh code cần `RestTemplateBuilder builder` và `Duration`. Ghi nhớ builder là dạng trả object mới.

### 10.2. RestClient với request factory

```java
ClientHttpRequestFactorySettings settings =
        ClientHttpRequestFactorySettings.DEFAULTS
                .withConnectTimeout(Duration.ofSeconds(2))
                .withReadTimeout(Duration.ofSeconds(5));

ClientHttpRequestFactory factory =
        ClientHttpRequestFactories.get(settings);

RestClient client = restBuilder.clone()
        .requestFactory(factory)
        .build();
```

Mảnh code cần imports `org.springframework.boot.web.client.ClientHttpRequestFactorySettings`, `ClientHttpRequestFactories`, `org.springframework.http.client.ClientHttpRequestFactory`, `Duration`, `RestClient`; `restBuilder` là builder đã được inject. Khi thay factory, phải kiểm tra lại TLS, proxy, HTTP resource sharing và instrumentation — không tự cho rằng factory mới kế thừa mọi setting cũ.

### 10.3. WebClient với Reactor Netty

```java
HttpClient netty = HttpClient.create()
        .responseTimeout(Duration.ofSeconds(5));

WebClient client = webBuilder.clone()
        .clientConnector(new ReactorClientHttpConnector(netty))
        .build();
```

Cần import `reactor.netty.http.client.HttpClient`, `org.springframework.http.client.reactive.ReactorClientHttpConnector` và `Duration`. `responseTimeout` không đồng nghĩa timeout của toàn bộ request pipeline. `Mono.timeout`/deadline trong service có thể thêm ràng buộc khác và việc cancel có phụ thuộc upstream/driver.

**Giới hạn:** thay connector thủ công có thể làm mất shared HTTP resources/TLS/metrics đã được Boot chuẩn bị. Không tạo connection pool mới cho mỗi request. Tùy biến hẹp theo service và đo latency/concurrency trước khi phổ biến toàn ứng dụng.

## 11. SSL bundles, secrets và xác thực từng HTTP partner

Với HTTPS, client cần **xác thực certificate chain và hostname**; dùng SSL bundle theo tên thay vì trust-all. Boot 3.3 cung cấp:

```java
RestClient securedRest = restBuilder.clone()
        .baseUrl("https://partner.example.test")
        .apply(restClientSsl.fromBundle("partner-trust"))
        .build();

WebClient securedWeb = webBuilder.clone()
        .baseUrl("https://partner.example.test")
        .apply(webClientSsl.fromBundle("partner-trust"))
        .build();

RestTemplate securedLegacy = templateBuilder
        .setSslBundle(sslBundles.getBundle("partner-trust"))
        .build();
```

Các biến `restClientSsl`, `webClientSsl`, `sslBundles` phải được inject; tương ứng với `RestClientSsl` thuộc `org.springframework.boot.autoconfigure.web.client`, `WebClientSsl` thuộc `org.springframework.boot.autoconfigure.web.reactive.function.client` và `SslBundles` thuộc `org.springframework.boot.ssl`. Bundle phải được khai báo bằng `spring.ssl.bundle.jks.*` hoặc `spring.ssl.bundle.pem.*` trong config. Đoạn code này **không chạy độc lập** nếu chưa có cert/truststore và partner server thật.

Đặt Authorization header ở customizer global cho mọi host là **rủi ro rò rỉ credential**. Chỉ nên thêm token khi biết rõ URL/trust domain hoặc trong từng client bean, và không log secret qua HTTP interceptor/filter. Đừng tắt hostname verification, bỏ qua TLS certificate hay dùng trust-all để “sửa nhanh” lỗi handshake.

## 12. Observability, lỗi và request context

Khi ứng dụng có Spring Boot Actuator/Micrometer Observation phù hợp, Boot có thể đăng ký customizers để thu thập metric/tracing cho HTTP clients. Dùng auto-configured builder giúp giữ những hỗ trợ này. Tạo trực tiếp client có thể khiến không còn tracing/observations như bạn mong đợi.

**Error handling khác nhau:**
- `RestClient.retrieve()` có các default status handlers và khả năng thêm `defaultStatusHandler`.
- `RestTemplate` dùng `ResponseErrorHandler`.
- `WebClient.retrieve()` chuyển 4xx/5xx thành reactive error theo contract; `exchangeToMono` cho phép xử lý response status/body tường minh.

Không viết một callback tùy biến rồi giả định ba client sẽ ném cùng một kiểu exception cho HTTP 404, timeout hoặc hỏng JSON. Viết contract và test riêng cho từng loại client.

**Request context:** correlation ID, traceparent và tenant/user context phải được lấy từ nguồn đáng tin và chuyển qua runtime đúng cách. Trên WebFlux, `ThreadLocal` hoặc `RequestContextHolder` không luôn theo cùng execution path giữa các operators; dùng Reactor Context/instrumentation thích hợp. Không dùng raw URL, token hoặc user ID làm metric tag có cardinality vô hạn.

Không log toàn bộ request/response body trong một global filter mặc định: có nguy cơ lộ PII, JWT, session cookies, password hoặc dữ liệu thanh toán. Cần cấu hình masking, sampling và bounds nếu thực sự có yêu cầu.

## 13. Các cách làm mất cấu hình của Spring Boot

### 13.1. Tự định nghĩa RestTemplateBuilder mà không qua configurer

Cách dễ làm mất defaults:

```java
@Bean
RestTemplateBuilder replacement() {
    return new RestTemplateBuilder()
            .setConnectTimeout(Duration.ofSeconds(3));
}
```

Vì bean `RestTemplateBuilder` của bạn thay bean auto-configured, những customizers và settings Boot chuẩn bị **không đương nhiên được mang theo**.

Nếu thật sự cần bean builder tùy chỉnh, Boot 3.3 có `RestTemplateBuilderConfigurer`:

```java
@Bean
RestTemplateBuilder replacement(
        RestTemplateBuilderConfigurer configurer) {
    return configurer.configure(new RestTemplateBuilder())
            .setConnectTimeout(Duration.ofSeconds(3));
}
```

Hai đoạn trên là **hai phương án đối chiếu**, không được cùng định nghĩa bean trùng trong một ứng dụng. `RestTemplateBuilderConfigurer` thuộc `org.springframework.boot.autoconfigure.web.client` của Boot 3.3. Phương án thứ hai giữ cơ chế cấu hình Boot trước khi thêm setting mới. Tuy nhiên phần lớn ứng dụng **không cần tự định nghĩa RestTemplateBuilder bean**.

### 13.2. Tạo client trực tiếp

```java
RestClient rest = RestClient.create();
RestTemplate template = new RestTemplate();
WebClient web = WebClient.create();
```

Các client này không tự nhận `RestClientCustomizer`/`RestTemplateCustomizer`/`WebClientCustomizer` của Boot. Integration test mục 6 chỉ rõ điều này.

### 13.3. Chỉ customizer một family rồi chờ family khác thay đổi

Một `RestClientCustomizer` không sửa WebClient hoặc RestTemplate. Nếu muốn cả ba cùng gửi một policy header, phải có ba cơ chế phù hợp hoặc một lớp client abstraction tự triển khai nhưng **không chia sẻ trực tiếp** một callback vì các signatures khác nhau.

### 13.4. Dùng builder mutable đồng thời hoặc sửa sau khi build

`RestClient.Builder`/`WebClient.Builder` là stateful. Không cache một singleton builder rồi cho nhiều threads mutate base URL/headers song song. Hãy build clients đã được cấu hình ở startup và tái sử dụng chúng, hoặc dùng `clone()` cho cấu hình độc lập.

## 14. Reactivity: thêm WebClientCustomizer không biến ứng dụng thành reactive

Một ứng dụng Spring MVC có thể dùng `WebClient` outbound; điều đó không làm `DispatcherServlet` tự biến thành `DispatcherHandler`. Ngược lại, trong ứng dụng WebFlux thuần, gọi `RestTemplate`/`RestClient` trực tiếp trên Netty event-loop sẽ **block thread**. Không gọi `block()` tùy tiện trong WebFlux handler hoặc reactive filter.

Cần lựa chọn:
- **MVC/Servlet + blocking libraries:** `RestClient` (API fluent mới) hoặc `RestTemplate` (legacy) là phương án tự nhiên.
- **WebFlux + reactive downstream:** `WebClient` là lựa chọn phù hợp.
- **WebFlux nhưng buộc gọi blocking SDK:** tách công việc sang bounded scheduler/thread pool và giới hạn concurrency; đó là workaround, không phải hiệu năng mặc định.

`WebClient` chỉ thực hiện request khi Publisher được subscribe. Nếu service gọi `webClient.get()...bodyToMono(...)` rồi bỏ Publisher đi, không có HTTP I/O; customizer đúng cũng không giúp request chạy. Trả `Mono` cho Spring WebFlux hoặc compose pipeline phù hợp; không tự `subscribe()` trong business service làm mất error/cancellation propagation.

## 15. Test strategy: từ callback tới HTTP thực

| Loại test | Điều chứng minh được | Điều chưa chứng minh |
|---|---|---|
| Unit test customizer | Callback gọi method builder/template | Boot có đăng ký bean, network effect |
| Spring context test | Bean tồn tại, DI wired | Header thực gửi, timeout thật |
| `@SpringBootTest(RANDOM_PORT)` như mục 6 | Boot builder + HTTP network request + response | TLS, proxy, latency cao, retries |
| MockRestServiceServer | RestClient/RestTemplate request/response mapping | Socket/TLS/connection pool |
| WebClient mock ExchangeFunction | Filter behavior, status/body handling | Connector networking |
| Local slow server | Timeout, error handling | Production load/hạ tầng proxy |
| TLS test CA giả lập | Truststore/hostname verification | Real CA rotation/production trust |

Đừng chỉ xem Spring context có bean `RestClientCustomizer` rồi kết luận mọi clients nhận policy đó. Cần kiểm tra **client được tạo từ đâu**, và request thực tế đến đâu. Tương tự, `@WebMvcTest`/`@JsonTest` không tự đảm bảo toàn bộ HTTP client auto-configuration có mặt; dùng integration test đúng scope.

Các assertions hữu ích: đúng header family, policy riêng không lẫn host, timeout có giới hạn, status 4xx/5xx được xử lý, certificate sai bị từ chối, secrets không bị log, tracing hoạt động khi bật dependencies, và blocking/reactive không lẫn thread model.

## 16. Troubleshooting thực tế

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không thấy header của `RestClientCustomizer` | Code gọi `RestClient.create()` | Inject builder Boot, build từ đó |
| Không thấy `RestTemplateCustomizer` | Dùng `new RestTemplate()` hoặc bean riêng | Inject `RestTemplateBuilder` rồi build |
| Không thấy `WebClientCustomizer` | Dùng `WebClient.create()` hoặc tự builder | Inject Boot `WebClient.Builder` |
| `RestTemplate` bean không tìm thấy | Boot không cung cấp RestTemplate singleton mặc định | Tạo từ RestTemplateBuilder và đăng ký bean nếu cần |
| `RestClient.Builder` không có ở WebFlux-only | Boot 3.3 RestClient auto-config có điều kiện non-reactive | Kiểm tra app type, chọn WebClient hoặc config riêng |
| Timeout của RestTemplate không đổi | Bỏ giá trị builder trả về từ method | Chain và build từ builder mới |
| Customizer log một lần nhưng HTTP gọi nhiều lần | Callback chạy lúc build, không phải mỗi request | Dùng interceptor/filter cho request-time behavior |
| Headers bị lặp | Thêm nhiều interceptors, append/overwrite hoặc config chồng | Audit thứ tự và test header cuối |
| Request factory mới làm mất SSL/proxy/metrics | Ghi đè transport Boot đã cấu hình | Dùng Boot builder, chọn override có chủ đích |
| WebClient Mono không gửi request | Publisher chưa được subscribe | Return/compose Mono, không discard |
| WebFlux throughput kém sau khi đổi client | Gọi blocking RestClient/RestTemplate trên event-loop | Dùng WebClient hoặc offload blocking I/O |
| HTTP 4xx xử lý khác nhau giữa clients | Khác error handler và default status semantics | Thiết kế/test contract riêng cho từng family |
| Một partner nhận credential của partner khác | Global Authorization header | Đặt secret per client/trust domain |
| Tắt hostname verification để "hết lỗi" | Trust bundle/CA/SAN sai | Sửa cert, truststore, không trust-all |
| Không thấy tracing dù Actuator có mặt | Khởi tạo client ngoài Boot builder hoặc thiếu exporter | Kiểm tra auto-configuration, registry, instrumentation |
| Test với mock pass nhưng production timeout | Mock không thực hiện socket I/O | Thử local slow server, TLS và pool |

## 17. Checklist triển khai

- [ ] Import đúng ba `*Customizer` thuộc Spring Boot 3.3.
- [ ] Xác định client thuộc blocking RestClient/RestTemplate hay reactive WebClient.
- [ ] Nắm rõ chữ ký callback: builder, template instance, builder.
- [ ] Dùng Boot-managed builders thay vì tạo client trực tiếp vô ý.
- [ ] Dùng global customization cho header/interceptor/policy chung không chứa secret.
- [ ] Giữ base URL, OAuth token, API key, SSL bundle và timeout riêng per partner.
- [ ] Đặt thứ tự customizers có chủ đích, tránh nhiều setter thay cùng cấu hình.
- [ ] Biết `RestTemplateBuilder` trả builder mới; `RestClient.Builder` và `WebClient.Builder` mutable.
- [ ] Nếu phải thay `RestTemplateBuilder` bean, dùng `RestTemplateBuilderConfigurer`.
- [ ] Không tự thay connector/factory nếu không kiểm tra lại connection pool, TLS, instrumentation.
- [ ] Không block Reactor event-loop; đừng tự subscribe Publisher trong service.
- [ ] Integration test tạo ba clients từ Boot và gọi test endpoint thật.
- [ ] Kiểm tra resilience (timeout, retry, HTTP errors), observability và log privacy.
- [ ] Thử cả đường tạo thẳng để biết ranh giới customizer không áp.
- [ ] Kiểm tra điều kiện auto-config khi app WebFlux-only hoặc nâng Boot major version.

## 18. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `RestTemplateCustomizer` không nhận `RestTemplateBuilder`?  
**Đáp án:** Interface tùy biến RestTemplate instance đã được tạo; builder là nơi đăng ký callback và gọi khi build.

**Câu 2:** `RestClientCustomizer` có làm `RestTemplate` thay đổi không?  
**Đáp án:** Không; hai family dùng các callbacks riêng dù đều là blocking HTTP clients.

**Câu 3:** `WebClient.create()` có nhận `WebClientCustomizer` từ Spring Boot không?  
**Đáp án:** Không. Inject `WebClient.Builder` được Boot auto-configure rồi build.

**Câu 4:** Vì sao timeout cấu hình trên RestTemplateBuilder có thể bị bỏ qua?  
**Đáp án:** Method cấu hình trả builder mới; nếu không giữ và build từ object mới thì setting không có hiệu lực.

**Câu 5:** Có nên gắn `Authorization` chứa secret vào `RestClientCustomizer` global?  
**Đáp án:** Thường không, vì có thể gửi nhầm token sang host khác. Dùng partner-specific bean và authentication policy đúng phạm vi.

**Câu 6:** Có thể khai báo nhiều bean cùng loại customizer không?  
**Đáp án:** Có, nhưng cần tránh settings đụng nhau, dùng `@Order` khi cần và kiểm tra kết quả request thực tế.

**Câu 7:** Một `Mono` WebClient chưa subscribe có gửi HTTP không?  
**Đáp án:** Không theo mô hình reactive cơ bản; phải return/compose và có subscriber thực sự.

**Câu 8:** Test nào tốt để xác nhận Boot đã áp callback lên cả ba clients?  
**Đáp án:** `@SpringBootTest` với RANDOM_PORT, inject ba Boot builders, gửi HTTP đến endpoint local và assert header/body.

## 19. Tài liệu chính thức

1. Spring Boot 3.3.13 — Calling REST Services, RestClient/RestTemplate/WebClient Customization: https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html
2. Spring Boot 3.3.13 — RestClientCustomizer JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/client/RestClientCustomizer.html
3. Spring Boot 3.3.13 — RestTemplateBuilder JavaDoc, `additionalCustomizers` và `setReadTimeout`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/client/RestTemplateBuilder.html
4. Spring Boot 3.3.13 — WebClientCustomizer JavaDoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/web/reactive/function/client/WebClientCustomizer.html
5. Spring Boot 3.3.13 — RestClientAutoConfiguration và điều kiện application: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/web/client/RestClientAutoConfiguration.html
6. Spring Boot 3.3.13 — HTTP Clients How-to: https://docs.spring.io/spring-boot/3.3/how-to/http-clients.html
7. Spring Framework — WebClient ExchangeFilterFunction: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html
8. Spring Framework — REST Clients: https://docs.spring.io/spring-framework/reference/integration/rest-clients.html

**Ghi nhớ:** `RestClientCustomizer` và `WebClientCustomizer` chỉnh **builder**, `RestTemplateCustomizer` chỉnh **template đã được tạo**. Dùng builder do Spring Boot quản lý để giữ codecs, connector, TLS và observability khi có; chọn global customization cho policy chung, local customization cho từng đối tác và xác minh bằng HTTP integration test thực tế.