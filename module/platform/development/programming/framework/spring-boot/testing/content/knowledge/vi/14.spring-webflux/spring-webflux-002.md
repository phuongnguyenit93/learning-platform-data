# Spring WebFlux: WebTestClient gắn Controller, ApplicationContext hoặc server thật

## 1. Tại sao cùng WebTestClient lại có nhiều phạm vi kiểm thử?

`WebTestClient` là công cụ kiểm thử HTTP của Spring, sử dụng phong cách xây request rồi xác minh response:

```java
client.get()
      .uri("/api/hello/Mai")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .jsonPath("$.message")
      .isEqualTo("Xin chào, Mai!");
```

Tuy nhiên, điều quan trọng nhất không phải cú pháp `expectStatus()` mà là **request thực sự đi tới đâu**. Với Spring WebFlux, Spring Framework hỗ trợ ba lựa chọn chính:

1. **`WebTestClient.bindToController(controller)`**: dựng một WebFlux mock server setup cho annotated controller được cung cấp trực tiếp. **Không** cần Spring `ApplicationContext` ứng dụng, **không** mở HTTP socket.
2. **`WebTestClient.bindToApplicationContext(context)`**: dùng các bean và WebFlux handler chain từ một `ApplicationContext` đã nạp. Request/response vẫn là mock objects, **không** qua TCP; nhưng controller, WebFilter, codec và hạ tầng trong context có thể tham gia.
3. **`WebTestClient.bindToServer().baseUrl(...)`**: client gửi HTTP qua network tới một server thật đã chạy. Có client connector, TCP/HTTP transport và embedded web server trong phạm vi kiểm thử.

Vì vậy, cùng một phép kiểm tra JSON có thể chứng minh các điều khác nhau. Test controller đơn lẻ xanh không chứng minh component scan, security filter, database hoặc HTTP transport của ứng dụng thật. Test gắn context xanh chưa chứng minh Netty/TCP. Live-server test kiểm chứng thêm network nhưng vẫn không tự chứng minh reverse proxy, TLS hoặc load balancer production nếu chúng không có trong môi trường test.

**Mục tiêu của bài này** là chọn đúng ranh giới, dựng ví dụ Java 17 chạy được, đọc chính xác kết quả và tránh nhận định quá rộng từ một test xanh.

## 2. Kết quả học tập

Sau bài, bạn có thể:

- Phân biệt `bindToController`, `bindToApplicationContext` và `bindToServer` về cấu hình, bean lifecycle và HTTP transport.
- Dùng `WebTestClient` để assert status, header, JSON, body kiểu Java record và POST request.
- Tạo controller độc lập bằng `new` và fake service, không cần Spring context.
- Nạp WebFlux context nhỏ qua `@SpringJUnitConfig`/`@EnableWebFlux` rồi gắn client vào context.
- So sánh `@WebFluxTest` với full Boot mock context qua `@SpringBootTest` + `@AutoConfigureWebTestClient`.
- Chạy server bằng `@SpringBootTest(webEnvironment=RANDOM_PORT)` và kiểm tra trực tiếp bằng `bindToServer`.
- Xác định WebFilter, controller advice, codec/Jackson, security chain và Spring bean wiring được bao phủ đến đâu.
- Giải thích khi nào dùng Reactor `StepVerifier`, cách xử lý stream dài và các rủi ro transaction, port, timeout, context cache.
- Viết test độc lập với test khác, không nhầm WebFlux với Spring MVC.

## 3. Sơ đồ request: mock exchange và network exchange

```text
Lựa chọn A: bindToController
    WebTestClient
        |
        +--> WebFlux mock handler chain do test dựng
                  |
                  +--> controller instance do test truyền vào
                           |
                           +--> fake/mock service do test tự tạo
    Không cần Spring app context; không dùng TCP.

Lựa chọn B: bindToApplicationContext
    WebTestClient
        |
        +--> WebHttpHandlerBuilder từ ApplicationContext
                  |
                  +--> WebFilters / WebExceptionHandlers
                  +--> HandlerMapping / HandlerAdapter / codecs
                  +--> controller bean -> service bean...
    Có Spring context; không dùng TCP.

Lựa chọn C: bindToServer
    WebTestClient
        |
        +--> HTTP connector -> TCP -> live Reactor Netty server
                                           |
                                           +--> WebFlux handler chain
                                           +--> controller/service...
    Có network và server thật; client có thể nằm ngoài process server.
```

**Không nhầm các khái niệm:**

| Công cụ | Vai trò |
| --- | --- |
| `WebClient` | HTTP client dùng trong application code để gọi hệ thống ngoài |
| `WebTestClient` | Test HTTP client với API assertion, dùng mock server hoặc live server |
| `MockMvc` | Test Spring MVC trên mock Servlet infrastructure |
| `MockMvcWebTestClient` | Adapter để dùng WebTestClient-style assertions với Spring MVC |
| `StepVerifier` | Công cụ reactor-test cho tín hiệu `Mono`, `Flux` và virtual time |

Trong mock mode, `WebTestClient` vẫn kiểm tra WebFlux routing, conversion, codecs và response contract theo cấu hình server mock. Nó không chỉ gọi trực tiếp một method controller bằng Java.

## 4. Bảng so sánh ba cách bind

| Tiêu chí | `bindToController` | `bindToApplicationContext` | `bindToServer` |
| --- | --- | --- | --- |
| Đầu vào | Controller instance | Spring `ApplicationContext` | Live server base URL |
| Cần Spring TestContext? | Không | Có context được tạo trước | Không bắt buộc ở phía client |
| Dùng Spring IoC wiring? | Không, test tự truyền dependency | Có trong scope context | Có trên server nếu server dùng Spring |
| Cần socket TCP? | Không | Không | Có |
| Controller được test | Controller truyền vào builder | Controller bean trong context | Controller server đang phục vụ |
| Global WebFilter của app | Không tự nạp | Có nếu nằm trong context | Có nếu nằm trong server |
| Security chain của app | Không tự nạp | Tùy context | Theo server đang chạy |
| Codec/Jackson | WebFlux setup được dựng cho controller | Theo WebFlux config trong context | Codec phía server thật và client |
| HTTP port/connection | Không được test | Không được test | Được test |
| Tốc độ thường gặp | Nhẹ | Phụ thuộc kích thước context | Thường cao chi phí hơn |
| Dùng cho | Controller contract hẹp | Spring/WebFlux wiring và filter behavior | HTTP integration/end-to-end |

**Quan trọng:** `bindToApplicationContext` không xác định context là nhỏ hay lớn. Context nhỏ từ `@SpringJUnitConfig` và full Boot context đều có thể được dùng, nhưng mức độ bean được nạp khác nhau.

## 5. Mô hình controller binding: thứ gì được tạo, thứ gì không?

Ví dụ tối thiểu:

```java
HelloService fake = name -> Mono.just(
        new HelloReply("Fake " + name, "fake"));

HelloController controller = new HelloController(fake);

WebTestClient client =
        WebTestClient.bindToController(controller).build();
```

Mọi type được khai báo đầy đủ ở dự án mẫu phía dưới. Spring Framework tạo WebFlux infrastructure cho controller instance và dùng mock request/response để điều phối request.

Vẫn có thể kiểm tra:

- `@GetMapping`, `@PostMapping` và mapping path.
- `@PathVariable`, `@RequestBody`, content negotiation.
- JSON serialization và deserialization qua codecs có sẵn.
- HTTP status, response header và body.
- Reactive `Mono`/`Flux` trả về từ handler.

Nhưng **không tự nạp** Spring Boot component scan, production service beans, `@ControllerAdvice` của ứng dụng, `WebFilter`, security config hoặc remote dependencies.

Nếu test cần exception handler, validator, codec customizer hoặc WebFilter đặc thù, cần thêm chúng vào mock server builder theo API Spring Framework, hoặc chuyển sang context binding. Không nên viết một standalone test rồi kết luận toàn bộ Spring Boot configuration hoạt động.

## 6. Mô hình ApplicationContext binding

Cú pháp cơ bản:

```java
@SpringJUnitConfig(WebConfig.class)
class ContextWebTest {
    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .build();
    }
}
```

Đây là khung minh họa, chưa runnable nếu chưa có `WebConfig`. `bindToApplicationContext` sử dụng `WebHttpHandlerBuilder.applicationContext(context)` để dựng WebFlux WebHandler chain từ những beans đang có.

Điều này có hai hệ quả:

- Nếu context có `WebFilter`, controller advice, codec configuration và Spring-managed controller thì chúng có thể tham gia vào request.
- Nếu context **không** có WebFlux infrastructure/HandlerMapping phù hợp, binding không tự biến một context service-only thành web server. Context thuần nên dùng `@EnableWebFlux` cùng các bean rõ ràng; context Boot reactive dùng Boot auto-configuration.

`@EnableWebFlux` thích hợp khi dựng **context nhỏ, tự cấu hình WebFlux** bằng Spring Framework. Không thêm annotation này bừa bãi vào mọi Boot application: nó có thể thay đổi cách Boot WebFlux auto-configuration tùy biến behavior. Ở dự án mẫu, annotation chỉ được đặt trên `TestConfig` của test context nhỏ.

## 7. Mô hình live server binding

Cú pháp:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8080")
        .build();

client.get()
      .uri("/api/hello/Mai")
      .exchange()
      .expectStatus().isOk();
```

`bindToServer` **không tự khởi động HTTP server**. Nó tạo client gắn địa chỉ thật; server phải được startup từ trước.

Trong Spring Boot test, cách chắc chắn hơn để tránh xung đột cổng là:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class LiveApiTest {
    @LocalServerPort
    int port;

    @Test
    void sendsHttpOverTcp() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();
        // Gửi request và assert response.
    }
}
```

Đây là khung minh họa, chưa có test cụ thể. `RANDOM_PORT` khiến Boot mở web server trên cổng ngẫu nhiên; `@LocalServerPort` inject cổng được cấp. Trong Boot 3.3 import là `org.springframework.boot.test.web.server.LocalServerPort`.

Nếu dùng `@SpringBootTest(webEnvironment=MOCK)`, server **không** mở socket. Nếu muốn WebTestClient trong mock context, dùng `@AutoConfigureWebTestClient`; đừng tạo `bindToServer("http://localhost:8080")` rồi hy vọng nó truy cập một mock server.

## 8. Chọn cách bind dựa vào điều cần chứng minh

| Yêu cầu nghiệp vụ/kỹ thuật | Cách bắt đầu hợp lý |
| --- | --- |
| GET trả đúng JSON khi service trả một object giả | `bindToController` |
| Controller bean được Spring tạo và inject đúng | `bindToApplicationContext` hoặc `@WebFluxTest` |
| Global WebFilter thêm response header | Context binding hoặc live server |
| SecurityWebFilterChain từ chối user thiếu quyền | Context có security config hoặc live server |
| REST endpoint chạy qua TCP và Netty | `bindToServer` |
| Controller → service → repository thật | `@SpringBootTest` với context/infrastructure phù hợp |
| WebFlux controller slice trong Boot, không cần server | `@WebFluxTest` + `WebTestClient` |
| Functional `RouterFunction` thay cho annotation controller | `bindToRouterFunction` |
| Test reactive operator `timeout`/`retryWhen` | JUnit + `StepVerifier` |
| HTTP outbound client contract | `@RestClientTest`/`WebClientTest` hoặc mock HTTP server đúng mục tiêu |

## 9. Dự án runnable: Java 17 và Spring Boot 3.3.0

Dự án sử dụng cùng một API `/api/hello`, một service thật và một global `WebFilter`. Ta kiểm tra năm mức setup để thấy **body/header** khác nhau, đặc biệt là khi filter chỉ tồn tại trong context.

Phiên bản **Spring Boot 3.3.0** được cố định để classpath và import minh họa thống nhất, không phải khuyến nghị giữ release cũ cho production. Dự án thực nên dùng release/Gradle/JDK được tổ chức hỗ trợ.

### 9.1. Cây thư mục

```text
webtestclient-modes/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/
    │   ├── WebfluxDemoApplication.java
    │   ├── HelloReply.java
    │   ├── HelloRequest.java
    │   ├── HelloService.java
    │   ├── DefaultHelloService.java
    │   ├── HelloController.java
    │   └── TraceHeaderFilter.java
    └── test/java/example/
        ├── HelloControllerBindTest.java
        ├── HelloContextBindTest.java
        ├── HelloWebFluxSliceTest.java
        ├── HelloBootMockTest.java
        └── HelloLiveServerTest.java
```

### 9.2. Gradle settings

**`settings.gradle`:**

```groovy
rootProject.name = 'webtestclient-modes'
```

### 9.3. Gradle build

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` cung cấp Spring WebFlux, Reactor, codec/Jackson và Reactor Netty; `spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito và Spring Test (`WebTestClient`). Không thêm `spring-boot-starter-web` trong ví dụ để Boot nhận đúng **reactive web application type**.

Nếu cả MVC và WebFlux trên classpath của ứng dụng Boot 3.3, Boot thường ưu tiên MVC. Muốn test WebFlux, phải chủ động cấu hình reactive web application type, ví dụ property `spring.main.web-application-type=reactive`, và kiểm tra những libraries đã import.

### 9.4. Application entry point

**`src/main/java/example/WebfluxDemoApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebfluxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebfluxDemoApplication.class, args);
    }
}
```

Full Boot context sẽ quét package `example` để tìm annotated components. Standalone `bindToController` không cần Spring Boot application class này.

### 9.5. Java records

**`src/main/java/example/HelloReply.java`:**

```java
package example;

public record HelloReply(String message, String source) {}
```

**`src/main/java/example/HelloRequest.java`:**

```java
package example;

public record HelloRequest(String name) {}
```

Java 17 record thuận tiện cho DTO immutable. Jackson từ WebFlux starter có thể đọc/ghi JSON record trong ứng dụng mẫu.

### 9.6. Service contract và implementation

**`src/main/java/example/HelloService.java`:**

```java
package example;

import reactor.core.publisher.Mono;

public interface HelloService {
    Mono<HelloReply> hello(String name);
}
```

**`src/main/java/example/DefaultHelloService.java`:**

```java
package example;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class DefaultHelloService implements HelloService {
    @Override
    public Mono<HelloReply> hello(String name) {
        return Mono.just(new HelloReply(
                "Xin chào, " + name + "!", "service"));
    }
}
```

`DefaultHelloService` không truy cập DB hay network, nên giúp cô lập khác biệt do binding. Với ứng dụng thật, service có thể gọi reactive repository hoặc `WebClient`; điều đó làm test integration nặng hơn và yêu cầu hạ tầng giả hoặc container phù hợp.

### 9.7. Controller reactive

**`src/main/java/example/HelloController.java`:**

```java
package example;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/hello")
public class HelloController {
    private final HelloService service;

    public HelloController(HelloService service) {
        this.service = service;
    }

    @GetMapping("/{name}")
    public Mono<HelloReply> get(@PathVariable String name) {
        return service.hello(name);
    }

    @PostMapping("/echo")
    public Mono<HelloReply> echo(
            @RequestBody Mono<HelloRequest> request) {
        return request.flatMap(body ->
                service.hello(body.name()));
    }
}
```

Controller dùng constructor injection và trả reactive `Mono<HelloReply>`. `POST /api/hello/echo` decode JSON thành `HelloRequest` trong reactive pipeline. Không có Bean Validation hoặc exception advice trong ví dụ, nên không tự suy luận hợp đồng HTTP 400 cho mọi đầu vào không hợp lệ.

### 9.8. Global WebFilter

**`src/main/java/example/TraceHeaderFilter.java`:**

```java
package example;

import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;
import reactor.core.publisher.Mono;

@Component
public class TraceHeaderFilter implements WebFilter {
    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain) {
        exchange.getResponse().getHeaders()
                .set("X-App-Filter", "active");
        return chain.filter(exchange);
    }
}
```

Filter này có thể được Spring scan trong Boot application context, hoặc được khai báo riêng trong test `@Configuration`. Nó thêm `X-App-Filter: active` vào response.

**Chìa khóa của demo:** standalone controller test không nạp `TraceHeaderFilter`; context test và live-server test có bean filter sẽ nhìn thấy header.

## 10. Test A — `bindToController`, không tạo Spring ApplicationContext

**`src/test/java/example/HelloControllerBindTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

class HelloControllerBindTest {
    private WebTestClient client() {
        HelloService fake = name -> Mono.just(
                new HelloReply("Fake " + name, "fake"));

        HelloController controller = new HelloController(fake);
        return WebTestClient.bindToController(controller).build();
    }

    @Test
    void getMapsPathAndSerializesJsonWithoutGlobalFilter() {
        client().get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().doesNotExist("X-App-Filter")
                .expectBody()
                .jsonPath("$.message").isEqualTo("Fake Mai")
                .jsonPath("$.source").isEqualTo("fake");
    }

    @Test
    void postDecodesRecordBody() {
        client().post()
                .uri("/api/hello/echo")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new HelloRequest("An"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Fake An")
                .jsonPath("$.source").isEqualTo("fake");
    }
}
```

Đây là **hai test runnable**, không dùng `@Autowired` hoặc `@SpringBootTest`. Test tự tạo một fake service theo lambda và tạo controller bằng constructor.

**Bằng chứng:** WebFlux request mapping, path variable, reactive controller return value, JSON codec cho GET và POST. `X-App-Filter` vắng mặt **theo thiết kế**, vì filter là bean của ứng dụng nhưng standalone test chỉ đưa controller instance vào builder.

**Chưa được chứng minh:** component scan, dependency injection qua Spring, global filter/security/advice của app, TCP transport, persistence.

## 11. Test B — `bindToApplicationContext` với WebFlux context nhỏ

**`src/test/java/example/HelloContextBindTest.java`:**

```java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.config.EnableWebFlux;

@SpringJUnitConfig(HelloContextBindTest.TestConfig.class)
class HelloContextBindTest {
    @Configuration(proxyBeanMethods = false)
    @EnableWebFlux
    static class TestConfig {
        @Bean
        HelloService helloService() {
            return new DefaultHelloService();
        }

        @Bean
        HelloController helloController(HelloService service) {
            return new HelloController(service);
        }

        @Bean
        TraceHeaderFilter traceHeaderFilter() {
            return new TraceHeaderFilter();
        }
    }

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient
                .bindToApplicationContext(context)
                .build();
    }

    @Test
    void usesControllerAndFilterBeansFromContext() {
        client.get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-App-Filter", "active")
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Xin chào, Mai!")
                .jsonPath("$.source")
                .isEqualTo("service");
    }
}
```

`@SpringJUnitConfig` đăng ký `SpringExtension` và tạo một context từ `TestConfig`. `@EnableWebFlux` tạo WebFlux handler infrastructure; các `@Bean` khai báo service/controller/filter trong context nhỏ.

Ở đây **Spring inject service vào controller**. `bindToApplicationContext` tạo mock WebHandler chain từ context đó, nên `TraceHeaderFilter` tham gia. Test nhận đúng `Xin chào, Mai!` và header `active`.

**Chưa được chứng minh:** full Boot component scan/auto-configuration hay TCP, vì context này được tạo từ test config nhỏ, không phải `SpringApplication` full app.

### 11.1. Tại sao context service-only chưa đủ?

Một `ApplicationContext` chỉ có `HelloService` và `HelloController` chưa chắc có WebFlux `HandlerMapping`, `HandlerAdapter`, codecs hoặc WebHandler root. `bindToApplicationContext` đòi một context được cấu hình cho WebFlux. `@EnableWebFlux` hoặc Boot reactive auto-configuration giải quyết phần hạ tầng này.

**Không đồng nhất `@EnableWebFlux` với `@SpringBootTest`:** thứ nhất bật WebFlux configuration trong context đã chọn; thứ hai là cơ chế Boot bootstrap có thể nạp nhiều thành phần ứng dụng khác.

## 12. Test C — `@WebFluxTest`, cách slice thông dụng của Spring Boot

**`src/test/java/example/HelloWebFluxSliceTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(HelloController.class)
class HelloWebFluxSliceTest {
    @Autowired
    WebTestClient client;

    @MockBean
    HelloService service;

    @Test
    void mapsControllerWithMockedServiceBean() {
        when(service.hello("Mai"))
                .thenReturn(Mono.just(
                        new HelloReply("From mock", "mock")));

        client.get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("From mock")
                .jsonPath("$.source").isEqualTo("mock");

        verify(service).hello("Mai");
    }
}
```

`@WebFluxTest` là Spring Boot **test slice** cho WebFlux controllers. Nó cấu hình WebFlux infrastructure và một `WebTestClient` trong test context, nhưng không quét mọi service bean thông thường. `@MockBean HelloService` cung cấp collaborator để controller được dựng.

**Điểm khác standalone:** controller là bean được Spring tạo trong slice, không phải `new HelloController(fake)`. Nhưng service vẫn là mock, nên test chưa chứng minh business logic của `DefaultHelloService`.

**Điểm khác full Boot context:** `@WebFluxTest` giới hạn các loại beans. Đừng mặc định global `WebFilter`, security config, repository hoặc functional `RouterFunction` của production đều xuất hiện. Nếu cần những thành phần ngoài slice, nhập test configuration có chủ đích hoặc chọn integration test.

Spring Boot 3.3 dùng `@MockBean`; các dòng Boot mới chuyển sang Framework `@MockitoBean`. Không thay import theo tên “mới hơn” nếu Spring Framework version của dự án chưa hỗ trợ.

## 13. Test D — full Boot mock context, không mở server TCP

**`src/test/java/example/HelloBootMockTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        classes = WebfluxDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class HelloBootMockTest {
    @Autowired
    WebTestClient client;

    @Test
    void testsFullApplicationBeansWithMockExchange() {
        client.get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-App-Filter", "active")
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Xin chào, Mai!")
                .jsonPath("$.source")
                .isEqualTo("service");
    }
}
```

`@SpringBootTest` nạp Boot application context với các beans thật của app trong ví dụ; `@AutoConfigureWebTestClient` cấu hình client để thực hiện mock web request trong context đó. `WebFluxDemoApplication` trong package `example` làm Spring scan service/controller/filter.

Test này chứng minh **Boot wiring và global WebFilter** trong mock exchange, nhưng **không chứng minh** embedded Netty HTTP server. `WebEnvironment.MOCK` **không** mở cổng thực.

Khác `@WebFluxTest`, full context có thể dựng nhiều bean production, nên test thường chậm hơn và phụ thuộc external configuration nhiều hơn. Chỉ chọn full context khi các integration points đó thật sự thuộc mục tiêu.

## 14. Test E — live server, HTTP qua loopback

**`src/test/java/example/HelloLiveServerTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        classes = WebfluxDemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class HelloLiveServerTest {
    @LocalServerPort
    int port;

    @Test
    void sendsRealHttpAndVerifiesFilterAndBody() {
        WebTestClient client = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        client.get()
                .uri("/api/hello/Mai")
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .valueEquals("X-App-Filter", "active")
                .expectBody()
                .jsonPath("$.message")
                .isEqualTo("Xin chào, Mai!")
                .jsonPath("$.source")
                .isEqualTo("service");
    }
}
```

`RANDOM_PORT` mở embedded server thực ở một cổng khả dụng; `@LocalServerPort` lấy cổng; `bindToServer` gửi request tới loopback TCP socket. Nếu server không chạy hoặc port sai, request không có mock fallback.

**Bằng chứng:** HTTP parsing, embedded Reactor Netty server, WebFlux handler chain của app, global filter và response body đi qua network.

**Chưa chứng minh:** TLS/ingress/load balancer trong production, vì chúng không nằm trên đường đi localhost. Nếu ứng dụng cần xác minh chúng, phải dựng môi trường test chứa các thành phần ấy.

### 14.1. `@Autowired WebTestClient` ở random-port test

Spring Boot 3.3 cũng hỗ trợ client `WebTestClient` được tự cấu hình để gắn vào server đang chạy trong `@SpringBootTest(RANDOM_PORT)` khi reactive WebFlux/test infrastructure có mặt. Bài này tạo client thủ công bằng `bindToServer` nhằm **làm rõ ranh giới** và địa chỉ thật.

## 15. Chạy ví dụ và kết quả mong đợi

Với JDK 17, Gradle Wrapper tương thích (ví dụ Gradle 8.5) và dependencies truy cập được:

```bash
./gradlew test
./gradlew test --tests example.HelloControllerBindTest
./gradlew test --tests example.HelloContextBindTest
./gradlew test --tests example.HelloWebFluxSliceTest
./gradlew test --tests example.HelloBootMockTest
./gradlew test --tests example.HelloLiveServerTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.HelloLiveServerTest
```

**Kết quả mong đợi:** tổng **6 lần thực thi JUnit test pass**: controller binding có 2 methods, mỗi class còn lại có 1 method. Không có stdout nghiệp vụ cố định; Gradle thường hiển thị `BUILD SUCCESSFUL` khi các task thành công. Startup logs, số task và thời gian phụ thuộc môi trường.

### 15.1. Đối chiếu hành vi của năm test

| Test | Dữ liệu service | Filter header | Spring context | TCP |
| --- | --- | --- | --- | --- |
| `HelloControllerBindTest` | `Fake Mai` / `fake` | Không có | Không | Không |
| `HelloContextBindTest` | `Xin chào, Mai!` / `service` | `active` | Nhỏ, từ `TestConfig` | Không |
| `HelloWebFluxSliceTest` | `From mock` / `mock` | Không cố định trong assertion | Slice WebFlux | Không |
| `HelloBootMockTest` | `Xin chào, Mai!` / `service` | `active` | Full Boot | Không |
| `HelloLiveServerTest` | `Xin chào, Mai!` / `service` | `active` | Full Boot/server | Có |

Ở `HelloWebFluxSliceTest`, không assert global filter vì test slice selection phụ thuộc cấu hình của slice/phiên bản. Khi cần xác minh filter, dùng context setup có bean rõ như Test B/D/E.

## 16. `configureClient()` và `mutate()`

Sau khi bind mock server, muốn cấu hình những tùy chọn HTTP client (base URL, default request headers, filters...), có thể chuyển sang client builder:

```java
WebTestClient client = WebTestClient
        .bindToController(new HelloController(fakeService))
        .configureClient()
        .baseUrl("/api")
        .defaultHeader("X-Test-Case", "standalone")
        .build();

client.get()
        .uri("/hello/Mai")
        .exchange()
        .expectStatus().isOk();
```

Đây là đoạn minh họa: `fakeService` phải được khởi tạo như Test A. Base URL `/api` ở mock setup là URI prefix, không biến mock client thành live HTTP client. Nếu lại gọi `/api/hello/Mai`, path có thể bị lặp.

Với `bindToServer()`, builder cho phép đặt `baseUrl("http://...")` trực tiếp. Muốn tạo client mới dựa trên client đã có:

```java
WebTestClient adapted = client.mutate()
        .defaultHeader("X-Test-Case", "changed")
        .build();
```

Đoạn này chỉ cấu hình client. Nó **không tự thêm Spring WebFilter** vào ứng dụng, không đổi server route và không bảo đảm security token có hiệu lực. Với `@AutoConfigureWebTestClient` của Boot, có thể dùng bean `WebTestClientBuilderCustomizer` theo phiên bản để tùy biến client tự cấu hình.

## 17. Assertion có giá trị: status, header, JSON và typed body

### 17.1. Kiểm tra status chính xác

```java
client.get().uri("/api/hello/Mai")
        .exchange()
        .expectStatus().isOk();
```

Khi API contract yêu cầu 201 Created, dùng `isCreated()`, không dùng `is2xxSuccessful()` quá rộng. Tương tự, với lỗi validation 400/401/403/404, assert status theo contract đã triển khai.

### 17.2. Header thuộc hợp đồng

```java
client.get().uri("/api/hello/Mai")
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
        .valueEquals("X-App-Filter", "active");
```

Header trong ví dụ được WebFilter đặt. Ở standalone Test A, assertion ngược là `doesNotExist("X-App-Filter")` vì filter không được đăng ký.

### 17.3. JSONPath

```java
client.get().uri("/api/hello/Mai")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message").isEqualTo("Xin chào, Mai!")
        .jsonPath("$.source").isEqualTo("service");
```

`jsonPath` không phụ thuộc thứ tự JSON keys. Tránh assert raw JSON string byte-by-byte nếu whitespace và key order không thuộc hợp đồng.

### 17.4. Deserialize thành record

```java
HelloReply reply = client.get()
        .uri("/api/hello/Mai")
        .exchange()
        .expectStatus().isOk()
        .expectBody(HelloReply.class)
        .returnResult()
        .getResponseBody();

assertEquals(
        new HelloReply("Xin chào, Mai!", "service"),
        reply);
```

Đây là đoạn trong test cần import JUnit `assertEquals`, sử dụng client gắn vào context/service thật. Nếu body rỗng, `getResponseBody()` có thể là `null`; phải assert status/body expectation tương ứng thay vì dereference mù quáng.

### 17.5. POST với Java record

```java
client.post()
        .uri("/api/hello/echo")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new HelloRequest("Mai"))
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.message")
        .isEqualTo("Xin chào, Mai!");
```

`bodyValue` mã hóa request body phía client; server decode vào `Mono<HelloRequest>`. Nếu muốn xác nhận validation/error response, phải thêm validation và exception mapping vào ứng dụng trước khi đưa expected status vào test.

## 18. Reactive response: `Mono`, `Flux`, SSE

Với `Mono<HelloReply>`, `expectBody(HelloReply.class)` hoặc `expectBody().jsonPath` thường đủ. Với JSON array trả từ `Flux<ItemView>`:

```java
client.get()
        .uri("/api/items")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(ItemView.class)
        .hasSize(2);
```

Đây là ví dụ minh họa, cần `ItemView` và endpoint `/api/items`; không phải route của dự án mẫu.

Với **server-sent events hoặc stream không kết thúc**, đừng dùng `expectBodyList` mà chờ vô hạn. Có thể lấy response `Flux` để kiểm tra một số tín hiệu:

```java
Flux<String> stream = client.get()
        .uri("/events")
        .exchange()
        .expectStatus().isOk()
        .returnResult(String.class)
        .getResponseBody();

StepVerifier.create(stream)
        .expectNext("connected")
        .thenCancel()
        .verify();
```

Đoạn minh họa cần `reactor-test` trong test classpath, imports `Flux`/`StepVerifier` và endpoint phát event tương ứng; SSE thực tế có thể dùng `ServerSentEvent<T>` hoặc codec khác. Không cam kết mọi SSE response sẽ decode thành cùng dạng `String`.

Nếu chỉ cần kiểm tra logic operator `retryWhen`, `timeout` hoặc `onErrorResume` trong service thuần, dùng unit test Reactor `StepVerifier`, có thể dùng virtual time, thay vì mở live server cho mọi trường hợp.

**Không nhầm:** WebTestClient assertion API hỗ trợ chờ response trong test; nó không có nghĩa controller production nên gọi `block()` trên Reactor Netty event loop.

## 19. Controller advice, filters và Spring Security

Trong standalone `bindToController`:

- WebFlux infrastructure cần thiết cho annotated controller được dựng.
- Global `WebFilter` của ứng dụng **không tự scan** vào setup.
- `@ControllerAdvice` custom của ứng dụng cũng phải được đăng ký có chủ đích nếu muốn assert error mapping.
- `SecurityWebFilterChain` của production không tự có chỉ vì starter Spring Security tồn tại ở một ứng dụng khác.

Trong `bindToApplicationContext`, những beans thuộc context có thể tham gia. Với Boot full mock/live context, còn phụ thuộc vào active profiles, conditional bean definitions và security configuration cụ thể.

Ví dụ từ Spring Security Test, **không runnable trong demo vì demo không khai báo security**:

```java
WebTestClient secured = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();

secured.mutateWith(mockUser("mai"))
        .get().uri("/private")
        .exchange()
        .expectStatus().isOk();
```

Cần module `spring-security-test`, static imports của `SecurityMockServerConfigurers`, WebFlux security configuration và endpoint `/private`. Đừng dùng đoạn này để chứng minh security nếu test chưa thực sự có filter chain.

Khi context test nhận 401/403 còn standalone nhận 200, có thể đó là **khác biệt đúng** vì security chain chỉ tồn tại trong context. Không vội sửa controller hoặc tắt filter cho tất cả test.

## 20. Functional routes: `bindToRouterFunction`

Spring WebFlux còn hỗ trợ routing theo hàm, không dùng annotated controller. `bindToController` không phải lựa chọn đúng cho một `RouterFunction` không được cung cấp dưới dạng controller.

Ví dụ:

```java
RouterFunction<ServerResponse> route =
        RouterFunctions.route(
                RequestPredicates.GET("/fn/ping"),
                request -> ServerResponse.ok().bodyValue("pong"));

WebTestClient client =
        WebTestClient.bindToRouterFunction(route).build();

client.get().uri("/fn/ping")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("pong");
```

Đây là đoạn minh họa độc lập về WebFlux functional API, cần imports thuộc `org.springframework.web.reactive.function.server`. Nó không dùng Spring context/live server.

Nếu router là bean của ứng dụng, dùng context binding phù hợp hoặc Boot full context. `@WebFluxTest` có thể không tự phát hiện custom `RouterFunction` bean; có thể phải `@Import` router configuration hoặc dùng `@SpringBootTest`.

## 21. Môi trường mock Boot và live Boot: cùng app nhưng khác ranh giới

Hai annotations thường bị nhầm:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class MockContextTest { }
```

và:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class LiveServerTest { }
```

Khác biệt chính:

| Mặt so sánh | `MOCK` + `@AutoConfigureWebTestClient` | `RANDOM_PORT` |
| --- | --- | --- |
| SpringApplication tạo Boot context | Có | Có |
| Controller/service/filter app | Có theo config | Có theo config |
| HTTP server/socket TCP | **Không** | **Có** |
| Nhu cầu port | Không | Có, thường `@LocalServerPort` |
| Request handling | Mock web exchange | Client/server transport thật |
| Chi phí | Thường nhẹ hơn live server | Thường nặng hơn |
| Giao dịch DB | Phụ thuộc cơ chế test | Server thread/transaction khác test thread |

`@WebFluxTest` còn nhẹ hơn nếu mục tiêu chỉ một controller. Đừng xếp `@WebFluxTest` lên `@SpringBootTest` để “có cả hai”; chọn một context strategy đúng mục tiêu.

## 22. Transaction, repository, hiệu ứng ngoài

Nếu endpoint tạo dữ liệu, một test chỉ assert 200/201 và body có thể chưa chứng minh repository ghi thành công. Ở integration test nên query dữ liệu qua repository/database thật khi hợp đồng yêu cầu.

**Đặc biệt với live server:** Spring Boot `RANDOM_PORT` xử lý request ở server thread/transaction riêng. `@Transactional` gắn trên JUnit test method **không tự rollback** các transaction đã commit trong server-side request. Với reactive database, còn có Reactor context/reactive transaction manager thay vì chỉ thread-local JDBC semantics; phải thiết kế fixture theo công nghệ đang dùng.

Giải pháp:

- Dùng database ephemeral/Testcontainers, schema riêng và cleanup có chủ đích.
- Không gọi API production hoặc DB production trong test tự động.
- Khi API có external gateway, dùng mock HTTP server hoặc test doubles ở ranh giới phù hợp.
- Không dùng `@DirtiesContext` như cách rollback database: đóng context không xóa transaction đã commit.
- Với JPA/JDBC blocking trong ứng dụng reactive, lưu ý không block event loop; điều đó là một rủi ro vận hành riêng.

## 23. Context cache và trạng thái dùng chung

Spring TestContext cache `ApplicationContext` theo cấu hình. Hai test `@SpringBootTest` tương đương có thể tái sử dụng context; khi đổi profile/properties/mocks hoặc `webEnvironment`, context cache key có thể khác.

- `bindToController`: test có thể tự tạo controller/fake mỗi method, không có Spring cache.
- `bindToApplicationContext`: singleton beans có thể được tái sử dụng giữa test methods/classes dùng chung context.
- `@WebFluxTest`: context slice và mock configuration có thể cache riêng.
- `@SpringBootTest(MOCK)`: full context không mở socket; bean state vẫn có thể tồn tại qua test methods.
- `@SpringBootTest(RANDOM_PORT)`: embedded server thuộc context; port có thể được reuse khi context được cache.

**Không suy ra test instance mới đồng nghĩa singleton state mới.** Reset in-memory caches/fakes/test data bằng fixture phù hợp; không để test phụ thuộc vào thứ tự chạy. `@DirtiesContext` chỉ nên dùng khi context thực sự phải bị đóng hoặc tái tạo.

## 24. Timeout, HTTP errors và độ ổn định

Một số lỗi không nằm ở controller:

- `bindToServer` báo `Connection refused`: live server chưa chạy hoặc host/port sai.
- Client dùng `http://localhost:8080` nhưng Boot chạy `RANDOM_PORT` khác.
- Body streaming không bao giờ kết thúc nhưng test dùng cách chờ toàn bộ.
- API phụ thuộc HTTP client/DB bị chậm, timeout phát sinh ở upstream.
- `@WebFluxTest` fail vì service chưa được mock/inject.
- Context binding fail vì thiếu WebFlux `HandlerMapping` hoặc bean configuration.
- MVC app bị nhầm là WebFlux app do có cả starters.

Có thể đặt timeout có giới hạn qua `WebTestClient.Builder` theo API của version dự án. Đừng tăng timeout tùy tiện để che deadlock hoặc lỗi môi trường. Với live-server test do Spring Boot quản lý, không cần `Thread.sleep()` để chờ port Boot đã tạo, trừ trường hợp startup async riêng chưa được điều phối readiness.

## 25. Đọc lỗi theo đúng binding

| Triệu chứng | Phạm vi liên quan | Cách xử lý |
| --- | --- | --- |
| `404` trong `bindToController` | Controller instance/path/mapping | Kiểm tra `@RequestMapping`, URI, controller registration |
| `404` trong context binding | Handler mapping/bean registration | Kiểm tra WebFlux config, controller/router bean |
| `404` từ live HTTP | Server route/deployment URL | Kiểm tra base URL, port, context path và server logs |
| `NoSuchBeanDefinitionException` trong `@WebFluxTest` | Slice exclude service | `@MockBean`/`@MockitoBean` hoặc import bean có chủ đích |
| `Failed to load ApplicationContext` | Context bootstrap/bean graph | Đọc lỗi gốc đầu tiên trong stack |
| Response thiếu `X-App-Filter` | Filter không nằm trong mock setup/context | Thêm WebFilter có chủ đích hoặc đổi mức test |
| `401/403` ngoài mong đợi | Security chain/filter | Cung cấp authentication/CSRF đúng hợp đồng |
| JSON decode fail | Codec/content type/schema | Xem `Content-Type`, record fields, client/server codecs |
| `Connection refused` | Live server không chạy | `RANDOM_PORT` và `@LocalServerPort` |
| Test pass với fake nhưng production bug | Mocked dependency không chạy thật | Thêm service/integration test ở ranh giới cần thiết |
| Mockito stub không được dùng | Wrong bean instance/arguments | Kiểm tra scope/mock bean/verify arguments |
| Một test pass, suite fail | Shared singleton/DB state, cache | Reset fixture/isolation, tránh phụ thuộc thứ tự |
| Test Boot chọn MVC thay vì WebFlux | Cả hai starters present | Chọn reactive web application type có chủ đích |
| Biên dịch fail khi nâng Boot 4 | Test modules/imports thay đổi | Dùng BOM/starter và package của major mới |

### 25.1. JSONPath không thay thế DB assertion

`expectBody().jsonPath("$.id")` chỉ khẳng định response có ID. Nếu API tạo resource, test integration nên kiểm tra ID ấy truy vấn lại được ở DB khi hợp đồng yêu cầu. Với standalone fake service, một ID chỉ là dữ liệu giả từ test.

### 25.2. Header filter chỉ xuất hiện nếu được đăng ký

Trong bài mẫu, Test A nhận không có `X-App-Filter`; Test B/D/E nhận header. Điều này không có nghĩa WebTestClient tự “thêm filter ở context mode”; nó có nghĩa **context chứa `TraceHeaderFilter` bean** nên handler chain đã áp dụng nó.

### 25.3. Phản hồi lỗi cần contract cụ thể

Ví dụ API đã thiết kế trả 404:

```java
client.get()
        .uri("/api/items/missing")
        .exchange()
        .expectStatus().isNotFound()
        .expectBody()
        .jsonPath("$.code")
        .isEqualTo("ITEM_NOT_FOUND");
```

Đây là **đoạn minh họa**, không phải endpoint trong demo. Phải có `@ControllerAdvice`/exception mapping phù hợp trước khi kỳ vọng status/error code. Không assert một thông báo lỗi Java nội bộ thay đổi theo version nếu nó không phải API contract.

## 26. Spring MVC khác Spring WebFlux như thế nào?

Với một MVC controller và Servlet `WebApplicationContext`, Spring Framework dùng `MockMvcWebTestClient`:

```java
WebTestClient mvcClient = MockMvcWebTestClient
        .bindToController(new MvcController())
        .build();
```

Đây là đoạn minh họa MVC, cần Spring MVC test dependencies và `MvcController`. Đối với WebFlux annotated controller, dùng `WebTestClient.bindToController`. Hai loại binding dùng hạ tầng khác nhau, dù API assertion phía client có phần tương đồng.

Nếu Spring Boot có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Boot 3.3 thường ưu tiên MVC. Không kết luận ứng dụng là reactive chỉ vì import được `WebTestClient`; hãy kiểm tra actual application type, controllers và server stack.

## 27. Bài tập thực hành

### Bài 1 — Dự đoán kết quả của mỗi binding

Với code mục 9, hãy điền expected:

| Test | `message` | `source` | `X-App-Filter` |
| --- | --- | --- | --- |
| Standalone controller | `Fake Mai` | `fake` | Không có |
| Context nhỏ | `Xin chào, Mai!` | `service` | `active` |
| WebFlux slice | `From mock` | `mock` | Không nằm trong contract test |
| Full Boot mock | `Xin chào, Mai!` | `service` | `active` |
| Live server | `Xin chào, Mai!` | `service` | `active` |

Giải thích từng ô dựa vào **dependency nào được inject** và **request đi qua handler chain nào**, không dựa vào cách viết `expectBody`.

### Bài 2 — Chỉ đổi fake service

Đổi Test A từ `"Fake " + name` thành `"Hello test " + name` nhưng giữ expected cũ. Hai assertion JSON phải đỏ. Khôi phục hoặc sửa expected theo contract mới. Filter header vẫn không xuất hiện.

### Bài 3 — Bỏ WebFilter khỏi context

Trong `HelloContextBindTest.TestConfig`, tạm bỏ bean `TraceHeaderFilter`. Body vẫn đúng từ service, nhưng assertion `X-App-Filter` đỏ. Thêm lại bean. Vì sao lỗi này **không** chứng minh controller mapping sai?

### Bài 4 — Lỗi thiếu service bean ở WebFlux slice

Trong Test C, bỏ `@MockBean HelloService` và chạy riêng test. WebFlux slice có thể fail tạo controller vì service không được nạp. Khôi phục. Giải thích tại sao chuyển sang full Boot context sẽ thay đổi **phạm vi** test chứ không chỉ sửa cú pháp.

### Bài 5 — Live port sai

Trong Test E, thay port lấy từ `@LocalServerPort` bằng một port không có listener trong sandbox. `bindToServer` phải lỗi kết nối; client **không chuyển sang mock handler**. Khôi phục port thật.

### Bài 6 — POST qua ba cách binding

Gửi `POST /api/hello/echo` với `HelloRequest("Mai")`:

- Test A sẽ trả `Fake Mai` vì fake service.
- Test B/D/E trả `Xin chào, Mai!` vì service thật.
- Test C cần stub `service.hello("Mai")`; nếu không mock có thể trả null và gây lỗi reactive pipeline.

Mỗi test phải assert status/body theo dependency graph riêng, không copy expected mù quáng.

### Bài 7 — Functional router

Tạo một `RouterFunction` cho `GET /fn/ping`, kiểm tra bằng `bindToRouterFunction`. Sau đó đưa router thành bean trong context và dùng `bindToApplicationContext`. Phân biệt route object tự tạo với bean Spring đăng ký.

### Bài 8 — Bổ sung validation

Thêm Bean Validation và error handler cho `HelloRequest`. Tạo test invalid body có status 400 theo contract. Kiểm tra cả việc service không được gọi nếu validation chặn trước handler logic. Không mặc định demo gốc tự tạo error JSON đó.

### Bài 9 — Reactive stream

Thêm endpoint `Flux<String>` có giới hạn và test `expectBodyList`; thêm SSE endpoint không kết thúc và dùng `returnResult` + StepVerifier/thenCancel. Vì sao ngủ cố định hoặc chờ toàn bộ body sẽ tạo test bất định?

### Bài 10 — Security boundary

Thêm Spring Security WebFlux ở nhánh sandbox. Compare standalone controller với context/live security. Viết một test anonymous bị 401/403 và một test principal hợp lệ, dùng security test support và kiểm tra đúng contract. Không bỏ filter chỉ để giữ status 200.

## 28. Checklist review trước khi chốt bài

- [ ] Tôi biết chính xác client đang gắn vào **controller, context hay server**.
- [ ] Tôi biết request có đi qua TCP thật hay không.
- [ ] Tôi phân biệt controller instance tự tạo với controller bean Spring tạo.
- [ ] Với context binding, context đã có WebFlux infrastructure/handler mappings.
- [ ] Với live binding, base URL và port trỏ đúng server test, không trỏ production.
- [ ] Tôi biết những WebFilter/security/controller advice thực sự có mặt.
- [ ] Tôi không nhầm MVC `MockMvcWebTestClient` với WebFlux binding.
- [ ] Tôi assert status, header/body/JSON fields thuộc hợp đồng.
- [ ] Tôi không dùng service mock để kết luận service thật hoạt động.
- [ ] Tôi biết `Flux`/SSE response có thể không bao giờ kết thúc.
- [ ] Tôi không dùng `block()` trong production event loop chỉ vì test thuận tiện.
- [ ] Với DB/live server, tôi hiểu cleanup và transaction boundary.
- [ ] Context cache không làm state mutable từ test khác rò vào kết quả.
- [ ] Tôi dùng Boot test annotation/import phù hợp major version.
- [ ] Tôi kiểm tra số test được thực thi chứ không chỉ nhìn build xanh.

## 29. Sơ đồ quyết định và kết luận

```text
Cần kiểm tra gì?
    |
    +-- Mapping/JSON của một controller với service fake?
    |      -> WebTestClient.bindToController(controller)
    |
    +-- Spring bean wiring/WebFilter/codec/advice?
    |      -> bindToApplicationContext(context)
    |         hoặc @WebFluxTest / @SpringBootTest(MOCK)
    |
    +-- Real HTTP/TCP/Web server?
    |      -> bindToServer().baseUrl(...)
    |         hoặc @SpringBootTest(RANDOM_PORT)
    |
    +-- Functional endpoint thay vì annotated controller?
    |      -> bindToRouterFunction(router)
    |
    +-- Logic reactive không liên quan HTTP?
           -> JUnit + StepVerifier, không cần server
```

**Thông điệp cốt lõi:** `WebTestClient` không định nghĩa duy nhất một mức kiểm thử. Chính **cách binding** quyết định ranh giới bằng chứng. `bindToController` kiểm tra controller với mock WebFlux infrastructure; `bindToApplicationContext` kiểm tra các web beans đã được Spring cấu hình; `bindToServer` kiểm tra HTTP thật qua network. Chọn mức nhỏ nhất đủ bảo vệ hợp đồng và bổ sung live integration test khi rủi ro transport/production wiring thực sự quan trọng.

## 30. Tài liệu chính thức

- Spring Framework — WebTestClient: các chế độ bind, requests, assertions: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — Spring WebFlux overview: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebFlux configuration: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Boot 3.3 — Testing Spring Boot Applications, WebFluxTest và WebTestClient: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot — Testing Spring Boot Applications (dòng mới): https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html
- Spring Security — Reactive testing: https://docs.spring.io/spring-security/reference/reactive/test/index.html
- Reactor — StepVerifier and testing: https://projectreactor.io/docs/core/release/reference/testing.html
- JUnit Jupiter User Guide: https://docs.junit.org/current/user-guide/
