# Phân biệt kiểm thử handler không mở cổng với kiểm thử HTTP qua máy chủ thật trong Spring Boot

## 1. Bản chất của câu hỏi “đã kiểm thử API chưa?”

Khi một developer nói “endpoint `POST /api/quotes` đã có test”, cần hỏi **request đã đi qua những lớp nào**. Có ít nhất bốn mức khác nhau:

1. **Unit/direct call:** gọi trực tiếp Java method của service hoặc controller. Không có HTTP request, không có servlet, không có socket.
2. **Spring MVC mock request:** dùng `MockMvc` đi qua `DispatcherServlet` và request/response giả lập, kiểm tra MVC mappings, binding, validation, converters, advice và filters đã được nối, **không start HTTP server**.
3. **Full application context nhưng vẫn mock HTTP:** `@SpringBootTest` mặc định `webEnvironment=MOCK`; app beans thực được tạo nhưng `MockMvc` vẫn không mở cổng.
4. **Live HTTP integration:** `@SpringBootTest(webEnvironment=RANDOM_PORT)` start embedded Tomcat (hoặc server phù hợp) rồi `TestRestTemplate`/`WebTestClient` gửi HTTP qua TCP đến port ngẫu nhiên.

Còn mức **deployed E2E** gọi hệ thống sau proxy, ingress, TLS, identity provider và các dependencies trong môi trường thực. Live HTTP test trong một JVM local **không** tự kiểm tra tất cả hạ tầng này.

Bài này thuộc nhóm **Kiểm thử web runtime**. Ví dụ Java đầy đủ dùng **Spring Boot 3.5.16, Java 17+, Spring MVC, Maven, JUnit Jupiter, Mockito, MockMvc, TestRestTemplate** và một Servlet riêng. Mục tiêu là đặt cùng một contract vào nhiều cấp test để hiểu rõ điều mỗi cấp phát hiện và bỏ sót.

**Quy tắc ngắn:** Unit test trả lời “logic có đúng?”; MockMvc trả lời “Spring MVC xử lý request đúng?”; real HTTP trả lời “embedded server nhận và định tuyến HTTP thực đúng?”; staging/E2E trả lời “đường đi qua hạ tầng triển khai có đúng?”.

## 2. So sánh theo công nghệ và lớp xử lý

| Kiểu test | Có ApplicationContext? | Có `DispatcherServlet` thật? | Có HTTP server thật? | Có network socket? |
| --- | --- | --- | --- | --- |
| JUnit gọi `new PriceService()` | Không | Không | Không | Không |
| JUnit gọi `new QuoteController(service)` | Không | Không | Không | Không |
| `MockMvcBuilders.standaloneSetup` | Không bắt buộc | MVC infrastructure thiết lập cho test | Không | Không |
| `@WebMvcTest` + `MockMvc` | Có, MVC slice | Có | Không | Không |
| `@SpringBootTest(MOCK)` + `@AutoConfigureMockMvc` | Có, full app | Có | Không | Không |
| `@SpringBootTest(RANDOM_PORT)` + HTTP client | Có, full app | Có trong MVC | Có | Có |
| `@SpringBootTest(DEFINED_PORT)` + HTTP client | Có, full app | Có trong MVC | Có | Có |
| HTTP smoke qua deployed ingress | App được deploy | Tùy runtime | Có | Có, qua proxy/LB |

`MockMvc` **không đơn thuần chỉ gọi controller trực tiếp**. Nó tạo `MockHttpServletRequest`, chuyển vào Spring MVC `DispatcherServlet` rồi chạy phần lớn xử lý MVC. Nhưng nó **không** yêu cầu Tomcat start, bind port, nhận TCP, chọn Servlet bằng URL pattern hoặc đàm phán TLS.

### 2.1. Bốn `webEnvironment` của Spring Boot 3.5

| Chế độ | Điều gì khởi động? |
| --- | --- |
| `MOCK` (mặc định) | Web ApplicationContext với Servlet mock environment, **không start embedded web server** |
| `RANDOM_PORT` | Embedded HTTP server ở **port ngẫu nhiên** do OS cấp |
| `DEFINED_PORT` | Embedded HTTP server ở `server.port`, mặc định thường 8080 |
| `NONE` | ApplicationContext không có web environment |

`@SpringBootTest` **không có `webEnvironment`** đồng nghĩa `MOCK` trong trường hợp web dependencies có sẵn. Không dùng `@LocalServerPort` với `MOCK` rồi tin rằng ứng dụng đã mở cổng.

### 2.2. Điểm khác biệt dễ bị hiểu sai

| Câu hỏi | Câu trả lời |
| --- | --- |
| “Dùng `@SpringBootTest` là E2E HTTP?” | **Không**, mặc định không có server |
| “Dùng `MockMvc` chỉ test Java method?” | **Không**, có MVC pipeline |
| “Dùng `WebTestClient` là chắc chắn gọi HTTP thật?” | **Không**, có bind-to-context/controller không mở socket |
| “Full context test luôn kiểm tra Servlet URL registration?” | **Không**, khi mock environment không có container dispatch |
| “RANDOM_PORT đồng nghĩa test TLS và ingress?” | **Không**, phải thực sự đi qua TLS/proxy đã cấu hình |
| “Unit/direct test kiểm tra `@Valid` Spring MVC?” | **Không tự động**, validation cần framework invocation |
| “TestRestTemplate thấy HTTP 500 mà không throw thì test pass?” | **Không**, cần assert status/body |

## 3. Gọi trực tiếp handler: đơn giản nhưng không phải HTTP contract test

Giả sử một method tính tiền:

```java
QuoteResponse quote(String sku, int quantity) {
    long price = switch (sku) {
        case "pen" -> 12_000L;
        case "book" -> 35_000L;
        default -> throw new ProductNotFoundException(sku);
    };
    return new QuoteResponse(
            sku, quantity, price, price * quantity);
}
```

Đây là **snippet**, mã project ở mục 9 sử dụng `Math.multiplyExact` và kiểm tra input.

Một unit test điển hình:

```java
PriceService service = new PriceService();
assertEquals(
        new QuoteResponse("pen", 2, 12000, 24000),
        service.quote("pen", 2));
```

Trong snippet này không có HTTP request. Nó không kiểm tra:

- `@PostMapping("/quotes")` đã được Spring đăng ký hay chưa.
- JSON body có deserialize thành `QuoteRequest` không.
- `@Valid`, `@Min`, `@Max` được kích hoạt bởi MVC hay không.
- `@RestControllerAdvice` có chuyển exception thành HTTP 404 không.
- Header/Accept/Content-Type, URL variables, path matching.
- Servlet filters, servlet mappings, Tomcat, TCP/HTTP.

**Vì sao vẫn dùng unit test?** Nó nhanh, ổn định, không cần context/DB, phù hợp kiểm tra hàng chục hoặc hàng trăm edge cases, invariant và branch logic. Đừng biến mọi quy tắc tính tiền thành bài kiểm thử start server.

### 3.1. Gọi trực tiếp controller cũng chưa phải Spring MVC test

`new QuoteController(service).createQuote(new QuoteRequest("pen",0))` gọi Java method như mọi phương thức khác. `@Valid` gắn trên parameter **không tự chạy** khi chỉ gọi bằng Java. Nếu service tự kiểm tra quantity, có thể vẫn throw exception, nhưng đó không phải `MethodArgumentNotValidException` của MVC.

Unit test và MVC validation test là **hai tầng cần bổ sung nhau**, không lấy kết quả một tầng để đại diện tầng kia.

## 4. MockMvc: xử lý Spring MVC thật bằng Servlet objects giả

### 4.1. Đường đi của request MockMvc

```text
JUnit test
     |
     v
MockMvc.perform(post("/api/quotes"))
     |
     v
MockHttpServletRequest / MockHttpServletResponse
     |
     v
Configured servlet filters (nếu được add)
     |
     v
DispatcherServlet
     |
     +--> HandlerMapping / HandlerAdapter
     +--> JSON converter + data binding
     +--> Bean Validation
     +--> @RestController / @Controller
     +--> @ControllerAdvice / @ExceptionHandler
     |
     v
MvcResult / JSON / status / headers
     |
     x    Không có socket/Tomcat listening port
```

Các behavior sau có thể test bằng MockMvc:

- HTTP method và request mapping: GET/POST/PUT/DELETE, path/query variables.
- Request `Content-Type`, response `produces`, `Accept`, 404/405/406/415.
- JSON mapping và charset; URL-encoded form, multipart mock, validation.
- `HandlerInterceptor`, filters và Spring Security **khi được cấu hình trong mock test**.
- MVC exception handler, body serialization, response headers.
- Request-scoped state/session giả lập ở mức MVC.

Những behavior MockMvc **không đủ để chứng minh**:

- Embedded Tomcat/Jetty/Undertow start/bind đúng network interface/port.
- Servlet container chọn một `HttpServlet` custom, Jersey servlet hoặc nhiều dispatchers đúng URL mapping.
- Actual TCP connection, OS sockets, HTTP protocol parsing, TLS/HTTP2 handshake.
- Reverse proxy/Ingress/CDN, real cookie browser rules và network policies.
- Startup lifecycle/management listener ở cổng riêng.
- Latency/throughput trên transport thật hoặc environment production.

### 4.2. `standaloneSetup` và `webAppContextSetup`

Spring Framework hỗ trợ hai cách dựng MockMvc:

```java
// Snippet A: controller được tạo thủ công, không cần Spring Context.
MockMvc mvc = MockMvcBuilders
        .standaloneSetup(new QuoteController(new PriceService()))
        .setControllerAdvice(new ApiErrorHandler())
        .build();
```

Với `standaloneSetup`, bạn cần tự cấu hình những gì relevant: MVC advice, converters, formatters, validator, filters, custom argument resolvers. Nó phù hợp để test MVC handler tập trung, **không đại diện toàn application**.

```java
// Snippet B: dùng MVC configuration trong WebApplicationContext.
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(webApplicationContext)
        .build();
```

Cách B dùng `WebApplicationContext` đã load, gần cấu hình MVC thực hơn. Boot `@WebMvcTest` và `@AutoConfigureMockMvc` tự cấu hình MockMvc, thường đơn giản hơn viết builder.

### 4.3. MockMvc không phải Browser

Bạn có thể gửi `Origin` và test response CORS headers bằng MockMvc; nhưng không có browser JavaScript runtime tự enforce CORS/cookie policy. Muốn kiểm chứng cross-origin frontend thật, cần browser E2E hoặc test trình duyệt đủ xác thực.

## 5. Web slice: `@WebMvcTest` với collaborator mock

Trong Spring Boot 3.5:

```java
@WebMvcTest(QuoteController.class)
class QuoteControllerSliceTest {
    @Autowired MockMvc mvc;
    @MockitoBean PriceService service;
}
```

Đây là **snippet cấu trúc**, chưa có methods/imports. `@WebMvcTest` load những bean cần để test Spring MVC, bao gồm các kiểu `@Controller`, `@ControllerAdvice`, `@JsonComponent`, `Filter`, `HandlerInterceptor`, MVC converters/configurers tương ứng. Nó **không tự scan tất cả `@Service`, `@Repository`, regular `@Component` hoặc `@ConfigurationProperties`** như full application context.

`@MockitoBean` của **Spring Framework 6.2** có package:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Annotation này tạo/thay bean collaborator bằng Mockito mock trong test context. Không cần đăng ký service thật nếu mục tiêu chỉ là kiểm tra MVC contract.

### 5.1. Câu hỏi phù hợp với slice

- Controller có được gọi đúng với JSON request không?
- JSON response có đúng field names/structure không?
- Input `quantity=0` có bị Bean Validation reject 400 không?
- Unknown SKU được `@RestControllerAdvice` trả 404 với stable code không?
- `Content-Type` và `Accept` có đúng không?
- Filter/header, CORS, handler advice đã cấu hình phù hợp với MVC test không?

Một mock service có thể trả dữ liệu được điều khiển theo test. Nếu production service thiếu bean hoặc JDBC config sai, slice vẫn có thể pass — đây là **phạm vi cô lập** của nó, không phải lỗi.

### 5.2. Khi không nên suy diễn từ slice

`@WebMvcTest` không chứng minh đầy đủ database migrations, external dependencies, Spring Bean wiring của service production, network listener, custom Servlet dispatch, TLS/Ingress và concurrency.

Nếu một bean custom converter hoặc configuration không nằm trong slice, dùng `@Import`/`@EnableConfigurationProperties` có chủ đích; đừng import toàn bộ application config một cách không kiểm soát, vì làm mất ý nghĩa slice.

## 6. Full context MockMvc: full wiring nhưng vẫn không mở cổng

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class FullContextMockMvcTest {
    @Autowired MockMvc mvc;
}
```

Đây là **snippet**. Spring Boot tạo application context thực với component scanning và auto-configurations; service/repository beans có thể thật, nhưng HTTP request vẫn do MockMvc mô phỏng.

| Vấn đề | `@WebMvcTest` | `@SpringBootTest(MOCK)` + MockMvc |
| --- | --- | --- |
| Spring context | Một lát cắt web | Gần/full app context |
| Collaborators | Thường `@MockitoBean` | Thường real beans |
| Dependency injection service | Không đầy đủ | Có thể kiểm tra |
| JSON, MVC validation, advice | Có | Có |
| Embedded server port | Không | Không |
| Custom servlet URL registration qua container | Không | Không |
| DB/repositories | Thường không load | Có thể dùng thật/fake theo profiles |
| Startup cost | Thường thấp hơn | Thường cao hơn |

Full-context mock test phù hợp khi muốn phát hiện lỗi dependency injection, configuration/bean wiring và interaction với thực thể nội bộ của app nhưng không cần mở socket. **Full context có thể vẫn truy cập database hoặc downstream** nếu test dùng real beans; không có network listener không đồng nghĩa mọi I/O đều mock.

### 6.1. Transactional test

Nếu test-side transaction được tạo bởi `@Transactional` và request được xử lý trong cùng thread/transaction context, thay đổi DB qua MockMvc có thể rollback sau test. Tuy nhiên async/multi-thread/các transaction propagation khác có thể làm điều này không đúng. Live HTTP test có sự khác biệt rõ ở mục 15.

## 7. Live HTTP: `@SpringBootTest(RANDOM_PORT)` và HTTP client thật

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {
    @LocalServerPort int port;
    @Autowired TestRestTemplate http;
}
```

Với Spring Boot 3.5, `RANDOM_PORT` start embedded web server thật, thường là Tomcat đối với `spring-boot-starter-web`. `@LocalServerPort` có import `org.springframework.boot.test.web.server.LocalServerPort`; giá trị port chỉ hợp lệ sau khi context/server chạy.

### 7.1. Vì sao random port?

- Giảm đụng cổng khi CI/test chạy song song, không yêu cầu 8080 luôn rảnh.
- OS cấp cổng thực; test dùng số port được inject, không hardcode.
- Cho phép multiple test contexts chạy độc lập trong nhiều trường hợp.
- Có thể kiểm tra server bind/start lifecycle thật.

`DEFINED_PORT` dùng port đã cấu hình, có thể phù hợp một số môi trường nhưng dễ conflict. Đừng chọn nó mặc định khi random port đủ dùng.

### 7.2. TestRestTemplate

`TestRestTemplate` là HTTP client test tiện lợi của Boot. Nó thường cho phép kiểm tra `ResponseEntity` của 4xx/5xx mà không throw chỉ do status HTTP, nên phải **assert status và body**. Trong project này, `spring-boot-starter-test` cung cấp dependency cần thiết.

### 7.3. Live HTTP tăng coverage gì?

- Tomcat thực sự chọn Servlet theo URL patterns và dispatch.
- HTTP request/response bytes thực đi qua TCP loopback.
- Container filters đã đăng ký, headers, status, redirects, session handling.
- Context path/servlet path integration và custom servlet registration.
- Codec/converter behavior trên HTTP transport.
- Management port khi được cấu hình riêng và test theo port thật.
- Compression/HTTP2/TLS nếu ứng dụng và test client **thực sự bật và yêu cầu chúng**.

**Không** chứng minh proxy/Ingress, real TLS, cloud DNS, OAuth provider hoặc load balancing khi test chỉ gọi localhost HTTP. Đây là **live server integration**, không tự thành production E2E.

## 8. Ma trận chọn cấp test theo lỗi cần phát hiện

| Rủi ro cần kiểm tra | Unit/direct | MockMvc | Live HTTP |
| --- | :---: | :---: | :---: |
| Business total/quantity/exception | Có | Có thể | Có thể |
| Spring `@GetMapping`/`@PostMapping` | Không | **Có** | **Có** |
| JSON deserialization/serialization | Không | Có | Có |
| Spring MVC `@Valid` | Không tự chạy | Có | Có |
| `@RestControllerAdvice` | Không tự chạy | Có | Có |
| MVC HandlerInterceptor | Không | Có nếu cấu hình | Có |
| Servlet filter logic | Không | Có nếu được đưa vào chain | Có |
| Full production bean graph | Không | Chỉ full-context MockMvc | Có |
| Custom Servlet/Jersey routing bởi container | Không | **Không** | Có |
| Embedded Tomcat thật bind cổng | Không | Không | **Có** |
| TCP/HTTP transport | Không | Không | **Có** |
| Browser CORS enforcement | Không | Không | Cần browser E2E |
| TLS/certificate | Không | Không | Chỉ nếu test bật TLS |
| External Ingress/proxy rewrite | Không | Không | Chỉ khi request qua proxy |
| DB transaction rollback giữa test/server | N/A | Tùy test | **Test-side rollback không áp sang server thread** |
| Concurrent load/p95 under stress | Không | Không | Cần workload performance test riêng |

Một “Có” chỉ nghĩa công cụ **có khả năng** chứng minh khi viết assertion phù hợp, không phải thêm annotation là tự kiểm tra mọi trường hợp.

## 9. Project Java 17+ runnable: cả MVC và Servlet riêng

Dự án có:

- `GET /api/ping` trả JSON.
- `POST /api/quotes` nhận JSON có `@Valid`, trả báo giá.
- `PriceService` nghiệp vụ và `ProductNotFoundException`.
- `ApiErrorHandler` dịch lỗi sang 400/404.
- `DemoHeaderFilter` thêm header `X-Demo-Filter: on`.
- `RawServletConfiguration` tạo một `HttpServlet` ở `/wire/*`, **ngoài Spring MVC**.

Bốn test classes tương ứng: unit, MVC slice, full context mock và live HTTP. Không cần database, Docker, Redis hay API đối tác để chạy.

### 9.1. Thư mục project

```text
web-test-levels/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/webtests/
    │   │   ├── WebTestsApplication.java
    │   │   ├── PriceService.java
    │   │   ├── QuoteController.java
    │   │   ├── ApiErrorHandler.java
    │   │   ├── DemoHeaderFilter.java
    │   │   └── RawServletConfiguration.java
    │   └── resources/application.properties
    └── test/java/com/example/webtests/
        ├── PriceServiceTest.java
        ├── QuoteControllerSliceTest.java
        ├── FullContextMockMvcTest.java
        └── RealHttpServerTest.java
```

Các DTO/exception/Servlet package-private ở cùng file Java có class public là hợp lệ. Tất cả thuộc package `com.example.webtests`; Spring Boot main class cùng package root để component scan.

### 9.2. `pom.xml`

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
    <groupId>com.example</groupId>
    <artifactId>web-test-levels</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
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

Parent quản lý versions của Spring Framework, Tomcat, Jackson, Hibernate Validator, Mockito và JUnit. Không pin các transitive dependencies riêng.

### 9.3. `WebTestsApplication.java`

```java
package com.example.webtests;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebTestsApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebTestsApplication.class, args);
    }
}
```

### 9.4. `PriceService.java`

```java
package com.example.webtests;

import org.springframework.stereotype.Service;

@Service
public class PriceService {

    public QuoteResponse quote(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (quantity < 1 || quantity > 100) {
            throw new IllegalArgumentException(
                    "quantity must be from 1 to 100");
        }

        long unitPrice = switch (sku) {
            case "pen" -> 12_000L;
            case "book" -> 35_000L;
            default -> throw new ProductNotFoundException(sku);
        };

        long total = Math.multiplyExact(
                unitPrice, (long) quantity);

        return new QuoteResponse(
                sku, quantity, unitPrice, total);
    }
}

class ProductNotFoundException extends RuntimeException {
    ProductNotFoundException(String sku) {
        super("Unknown SKU: " + sku);
    }
}
```

Service tự bảo vệ quantity/sku và không có dependency HTTP. `Math.multiplyExact` giúp tránh silent overflow.

### 9.5. `QuoteController.java`

```java
package com.example.webtests;

import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

record QuoteRequest(
        @NotBlank String sku,
        @Min(1) @Max(100) int quantity) {
}

record QuoteResponse(
        String sku, int quantity,
        long unitPriceVnd, long totalVnd) {
}

@RestController
@RequestMapping("/api")
public class QuoteController {

    private final PriceService priceService;

    public QuoteController(PriceService priceService) {
        this.priceService = priceService;
    }

    @GetMapping(value = "/ping",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }

    @PostMapping(value = "/quotes",
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE)
    public QuoteResponse createQuote(
            @Valid @RequestBody QuoteRequest request) {
        return priceService.quote(
                request.sku(), request.quantity());
    }
}
```

`@Valid` trên body khiến MVC Bean Validation kiểm tra quantity/sku. Khi **gọi Java method trực tiếp**, annotation không tự chạy, dù service vẫn có kiểm tra riêng.

### 9.6. `ApiErrorHandler.java`

```java
package com.example.webtests;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> invalid(
            MethodArgumentNotValidException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
                Map.of("code", "INVALID_REQUEST",
                       "message", "Dữ liệu yêu cầu không hợp lệ."));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> badJson(
            HttpMessageNotReadableException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
                Map.of("code", "INVALID_JSON",
                       "message", "JSON không đọc được."));
    }

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<Map<String, String>> unknown(
            ProductNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                Map.of("code", "SKU_NOT_FOUND",
                       "message", "Không tìm thấy sản phẩm."));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> illegal(
            IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(
                Map.of("code", "INVALID_REQUEST",
                       "message", "Tham số không hợp lệ."));
    }
}
```

Advice map Java errors thành public HTTP errors có mã ổn định; không expose raw stack traces.

### 9.7. `DemoHeaderFilter.java`

```java
package com.example.webtests;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class DemoHeaderFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws IOException, ServletException {
        response.setHeader("X-Demo-Filter", "on");
        filterChain.doFilter(request, response);
    }
}
```

Trong live Servlet environment, Filter bean được Boot đăng ký. MockMvc với filter auto-configured cũng có thể chạy filter logic. Nhưng filter hoạt động trong MVC mock **không đủ** để chứng minh nó đã được Tomcat gắn cho custom Servlet path ở server thật.

### 9.8. `RawServletConfiguration.java`

```java
package com.example.webtests;

import java.io.IOException;

import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class RawServletConfiguration {

    @Bean
    ServletRegistrationBean<RawPingServlet> rawPingServlet() {
        ServletRegistrationBean<RawPingServlet> registration =
                new ServletRegistrationBean<>(
                        new RawPingServlet(), "/wire/*");
        registration.setName("rawPingServlet");
        return registration;
    }
}

class RawPingServlet extends HttpServlet {

    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response)
            throws IOException {

        if (!"/ping".equals(request.getPathInfo())) {
            response.sendError(HttpServletResponse.SC_NOT_FOUND);
            return;
        }

        response.setCharacterEncoding("UTF-8");
        response.setContentType("text/plain");
        response.getWriter().write("raw-servlet-ok\n");
    }
}
```

**Đây là điểm chứng minh thực nghiệm:** `/wire/ping` thuộc custom Servlet, **không phải** Spring MVC `@GetMapping`. Với live HTTP, embedded Tomcat chọn `/wire/*` rồi gọi `RawPingServlet`. `MockMvc` gắn DispatcherServlet không làm container-level Servlet selection, vì thế không đủ để test route này.

### 9.9. `application.properties`

```properties
spring.application.name=web-test-levels
server.port=8080
```

Không dùng context path riêng, SSL, DB hoặc Security trong demo để giữ phạm vi tập trung. `RANDOM_PORT` của test sẽ override port main, không tranh 8080 với process đang chạy.

## 10. Unit test đầy đủ: không Spring, không network

Tệp `src/test/java/com/example/webtests/PriceServiceTest.java`:

```java
package com.example.webtests;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceServiceTest {

    private final PriceService service = new PriceService();

    @Test
    void computesTotalWithoutSpring() {
        assertEquals(
                new QuoteResponse("pen", 2, 12000, 24000),
                service.quote("pen", 2));
    }

    @Test
    void rejectsInvalidQuantity() {
        assertThrows(IllegalArgumentException.class,
                () -> service.quote("pen", 0));
    }

    @Test
    void rejectsUnknownSku() {
        assertThrows(ProductNotFoundException.class,
                () -> service.quote("missing", 1));
    }
}
```

Ba tests không tạo ApplicationContext, không mở port, không chạy DispatcherServlet. Kết quả chỉ chứng minh **business service**.

## 11. MVC slice test: `@WebMvcTest` + `MockMvc`

Tệp `src/test/java/com/example/webtests/QuoteControllerSliceTest.java`:

```java
package com.example.webtests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(QuoteController.class)
class QuoteControllerSliceTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    PriceService service;

    @Test
    void dispatchesJsonToController() throws Exception {
        given(service.quote("pen", 2))
                .willReturn(
                        new QuoteResponse("pen", 2, 12000, 24000));

        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"pen","quantity":2}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.sku").value("pen"))
                .andExpect(jsonPath("$.totalVnd").value(24000))
                .andExpect(header().string(
                        "X-Demo-Filter", "on"));

        verify(service).quote("pen", 2);
    }

    @Test
    void beanValidationRejectsBadQuantity() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"pen","quantity":0}
                        """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_REQUEST"));
    }

    @Test
    void pingHasExpectedMapping() throws Exception {
        mvc.perform(get("/api/ping")
                .accept(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.message")
                        .value("pong"));
    }

    @Test
    void wrongMethodReturns405() throws Exception {
        mvc.perform(post("/api/ping"))
                .andExpect(status().isMethodNotAllowed());
    }
}
```

`@MockitoBean` mock `PriceService` nên test contract JSON/MVC không phụ thuộc logic báo giá thật. `@WebMvcTest` được Boot 3.5 auto-configure MockMvc. `DemoHeaderFilter` là `@Component` implements Filter và thuộc loại MVC slice có thể scan; với cấu hình test mặc định có filters, header assertion chứng minh mock filter chain chạy.

**Không suy từ test này rằng Tomcat đã đăng ký filter/Servlet thật**. Nếu dùng `@AutoConfigureMockMvc(addFilters=false)` hoặc `MockMvcBuilders.standaloneSetup` mà không add filters, hành vi filter sẽ khác.

Khi `@WebMvcTest` fail vì thiếu `PriceService` bean và chưa có `@MockitoBean`, đó thường là do slice không load regular `@Service`, không phải production startup fail.

## 12. Full context nhưng HTTP vẫn mock

Tệp `src/test/java/com/example/webtests/FullContextMockMvcTest.java`:

```java
package com.example.webtests;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
class FullContextMockMvcTest {

    @Autowired
    MockMvc mvc;

    @Test
    void checksMvcWithRealServiceButNoPort() throws Exception {
        mvc.perform(post("/api/quotes")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"sku":"book","quantity":2}
                        """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.unitPriceVnd")
                        .value(35000))
                .andExpect(jsonPath("$.totalVnd")
                        .value(70000));
    }
}
```

Khác với MVC slice: `PriceService` thật được tạo và được controller gọi. Nhưng không có Tomcat listening port. `@AutoConfigureMockMvc` chỉ dựng mock request pathway. Nếu test này pass, có thêm bằng chứng dependency injection và business logic trong full Spring context đúng; **chưa** biết `RawPingServlet` thật có được Tomcat route hay không.

## 13. Live server test với cổng thực

Tệp `src/test/java/com/example/webtests/RealHttpServerTest.java`:

```java
package com.example.webtests;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpServerTest {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate http;

    private String url(String path) {
        return "http://127.0.0.1:" + port + path;
    }

    @Test
    void serverIsReallyListening() {
        assertTrue(port > 0);

        ResponseEntity<Map> response = http.getForEntity(
                url("/api/ping"), Map.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("pong",
                response.getBody().get("message"));
    }

    @Test
    void quoteWorksOverHttp() {
        ResponseEntity<QuoteResponse> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new QuoteRequest("pen", 3),
                        QuoteResponse.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals(
                new QuoteResponse("pen", 3, 12000, 36000),
                response.getBody());
        assertEquals("on",
                response.getHeaders().getFirst("X-Demo-Filter"));
    }

    @Test
    void invalidInputReturns400() {
        ResponseEntity<Map> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new QuoteRequest("pen", 0),
                        Map.class);

        assertEquals(HttpStatus.BAD_REQUEST,
                response.getStatusCode());
        assertEquals("INVALID_REQUEST",
                response.getBody().get("code"));
    }

    @Test
    void unknownSkuReturns404() {
        ResponseEntity<Map> response =
                http.postForEntity(
                        url("/api/quotes"),
                        new QuoteRequest("missing", 1),
                        Map.class);

        assertEquals(HttpStatus.NOT_FOUND,
                response.getStatusCode());
        assertEquals("SKU_NOT_FOUND",
                response.getBody().get("code"));
    }

    @Test
    void tomcatDispatchesNonMvcServlet() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/wire/ping"), String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("raw-servlet-ok\n", response.getBody());
        assertEquals("on",
                response.getHeaders().getFirst("X-Demo-Filter"));
    }

    @Test
    void unknownServletPathIs404() {
        ResponseEntity<String> response =
                http.getForEntity(
                        url("/wire/missing"), String.class);

        assertEquals(HttpStatus.NOT_FOUND,
                response.getStatusCode());
        assertNotEquals("raw-servlet-ok\n", response.getBody());
    }
}
```

Đây là HTTP thật qua embedded Tomcat:

- `port > 0` chứng minh có random port được cấp.
- Client gửi HTTP tới loopback; response JSON/body/headers đi qua transport thực.
- Route `/wire/ping` do **RawPingServlet** của Servlet container, không do MVC controller.
- Filter header trên cả MVC và non-MVC endpoints cho thấy registered Servlet filter đang có tác dụng trên live HTTP requests.
- HTTP 400/404 được kiểm tra tại public boundary, không phải chỉ gọi Java exception.

**Giới hạn:** server local không tự chứa reverse proxy, TLS, browser CORS enforcement hoặc external service integration. Test này cũng không phải benchmark p95/throughput.

## 14. Chạy Maven và kiểm tra bằng curl

### 14.1. Chạy toàn bộ JUnit tests

Cần Java 17+, Maven và đủ source files:

```bash
java -version
mvn -version
mvn clean test
```

Các tests `RANDOM_PORT` không yêu cầu 8080 còn trống. Maven/Surefire sẽ hiển thị số tests và kết quả theo version plugin; không có một dòng stdout cố định để cam kết ở mọi môi trường. Nếu một test fail, kiểm tra stack trace theo lớp bị ảnh hưởng.

### 14.2. Chạy project thật

```bash
mvn clean package
java -jar target/web-test-levels-1.0.0.jar
```

Trong terminal khác:

```bash
curl -i http://127.0.0.1:8080/api/ping

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":3}'

curl -i http://127.0.0.1:8080/wire/ping
```

Kỳ vọng:

- `GET /api/ping`: **HTTP 200**, JSON `{"message":"pong"}`.
- `POST /api/quotes`: **HTTP 200**, JSON có chính xác các giá trị:

```json
{"sku":"pen","quantity":3,"unitPriceVnd":12000,"totalVnd":36000}
```

- `GET /wire/ping`: **HTTP 200**, `Content-Type: text/plain`, body có newline cuối:

```text
raw-servlet-ok
```

- Hai đường gọi được filter áp dụng có header `X-Demo-Filter: on`.

### 14.3. Negative cases

```bash
curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"pen","quantity":0}'

curl -i -X POST http://127.0.0.1:8080/api/quotes \
  -H "Content-Type: application/json" \
  -d '{"sku":"missing","quantity":1}'

curl -i http://127.0.0.1:8080/wire/missing

curl -i -X POST http://127.0.0.1:8080/api/ping
```

Kỳ vọng lần lượt: **400 `INVALID_REQUEST`**, **404 `SKU_NOT_FOUND`**, **404 từ RawPingServlet**, và **405 Method Not Allowed từ MVC**. Nếu thêm Security/CSRF, một request POST có thể bị chặn trước controller với 401/403; điều đó cần test theo security contract riêng.

## 15. Transaction rollback: khác biệt thường làm test sai

Khi dùng database và `@Transactional` trên test method, Spring TestContext thường rollback transaction của **test thread** sau method. Nhưng trong `RANDOM_PORT`, HTTP client của test và server-side request handler chạy **khác threads**, tạo **transactions khác nhau**.

### 15.1. Anti-pattern

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Transactional
class OrderHttpIntegrationTest {
    // Gửi POST /orders qua HTTP rồi tưởng INSERT do server thực hiện
    // sẽ được rollback nhờ @Transactional trên test method.
}
```

Đây là **snippet cảnh báo**, không phải test hoàn chỉnh. Transaction của JUnit thread không tự bao trùm server thread, nên DB writes đã commit trong server có thể còn sau test.

### 15.2. Giải pháp

- Mỗi test dùng unique IDs/tenant namespace; cleanup có kiểm soát.
- Dùng Testcontainers DB hoặc test schema/database riêng.
- Reset DB bằng truncate/snapshot/rollback ở đúng ranh giới khi được phép.
- Với Kafka/email/payment, dùng stub/sandbox và tránh side effects thật.
- Không dùng `@DirtiesContext` như một phương án dọn dữ liệu đã commit ngoài context.
- Đừng làm tests phụ thuộc thứ tự và shared mutable state.

Với MockMvc full-context, khi request chạy cùng thread/transaction, test rollback **có thể** hoạt động; tuy nhiên async tasks hoặc transaction propagation riêng vẫn cần kiểm tra. Trong demo này không dùng database, vì vậy caveat này chỉ áp dụng khi mở rộng project.

## 16. WebTestClient và WebFlux: tên client không quyết định có socket hay không

`WebTestClient` có thể hoạt động ở hai chế độ:

| Cách tạo | Có HTTP server? | Mục tiêu |
| --- | --- | --- |
| `WebTestClient.bindToController(...)` | Không | Reactive controller mock |
| `WebTestClient.bindToApplicationContext(...)` | Không | Handler pipeline in-memory |
| `WebTestClient.bindToServer().baseUrl("http://...")` | Có nếu server tồn tại | HTTP integration |
| Boot WebTestClient trong `@WebFluxTest` | Không | Reactive web slice |
| Boot WebTestClient trong `@SpringBootTest(RANDOM_PORT)` | Có | Live server |

Để dùng WebTestClient trong test MVC Boot 3.5, cần `spring-webflux` trên classpath. Nếu không muốn thêm reactive dependency cho tests, `TestRestTemplate` là lựa chọn thuận tiện.

### 16.1. WebFlux tương đương MVC test pyramid

- JUnit + `StepVerifier`: test service `Mono/Flux` trực tiếp, không HTTP.
- `@WebFluxTest` + `WebTestClient`: test reactive handler, codecs/validation/webfilters in-memory.
- `@SpringBootTest(RANDOM_PORT)` + WebTestClient: start reactive HTTP server (thường Reactor Netty) rồi gọi TCP thật.

Nếu cả `spring-boot-starter-web` và `spring-boot-starter-webflux` có mặt, Boot 3.5 **ưu tiên MVC inbound**. Khi chủ đích test reactive runtime với cả hai dependencies, xem `spring.main.web-application-type=reactive` theo tài liệu đúng version.

### 16.2. Cẩn thận với API Boot 4

Một số tài liệu Boot 4 đề cập `RestTestClient`, package names/test support mới. Project này dùng **Boot 3.5.16** và `TestRestTemplate`; không copy nguyên code/test classes từ tài liệu major khác rồi mặc định compile được.

## 17. Security, filters, cookies và CORS qua các cấp test

### 17.1. Spring Security trong MockMvc

Nếu project có `spring-boot-starter-security`, không tự tắt filters để “test pass”. Với `spring-security-test`, có thể dùng:

- `@WithMockUser` để mô phỏng user/roles trong mock tests.
- `SecurityMockMvcRequestPostProcessors.csrf()` cho POST/PUT/DELETE nếu dùng CSRF.
- Assertions 401/403 cho anonymous và role sai.
- Kiểm tra `@AutoConfigureMockMvc(addFilters=true)` và Security filter chain đã được tích hợp.

**MockMvc có thể test security filter logic** trong mock environment; không cần socket cho mọi authorization unit/slice case.

### 17.2. Live HTTP cần bổ sung

Kiểm tra cookie `Set-Cookie`, session stickiness, redirects, actual authentication headers, servlet filter registration và security boundary qua port. Nếu HTTPS được bật, kiểm tra `Secure`/`SameSite` cookie, certificate trust và redirect HTTP→HTTPS. Nhưng demo HTTP local **không** tự chứng minh TLS, mTLS hay proxy behavior.

### 17.3. CORS và Browser

MockMvc và TestRestTemplate có thể gửi Origin/OPTIONS rồi assert CORS headers. Nhưng chúng không phải trình duyệt và **không tự chặn JavaScript cross-origin response**. Cần browser E2E khi CORS là rủi ro thực tế. Không lấy curl 200 làm bằng chứng browser sẽ đọc được response.

### 17.4. Multipart/upload/streaming

MockMvc có hỗ trợ mock multipart requests và assertions controller logic, nhưng giới hạn actual body size, reverse proxy buffering, file spill-to-disk, chunked transfer, network slow clients và HTTP/2 cần live/server/deployment tests. Việc đạt một case mock multipart 10 KiB không chứng minh upload 2 GiB qua gateway hoạt động.

## 18. Khi nào real HTTP local vẫn chưa đủ?

| Chức năng | Vì sao local random-port chưa chứng minh | Test bổ sung |
| --- | --- | --- |
| API gateway/Ingress | Không có path rewrite/load balancer | Staging smoke qua gateway |
| TLS/mTLS | Demo HTTP cleartext | SSL-enabled server và actual truststore |
| OAuth/SSO | Không có identity provider | Sandbox authorization flow |
| Database schema | Không có DB trong demo | Testcontainers và migrations |
| Kafka/Redis/email | Không gọi downstream | Contract/integration tests |
| Cookies ở Browser | Không có browser | Browser end-to-end |
| CORS enforcement | HTTP client không enforce SOP | Browser E2E |
| Container orchestration | Một JVM | Cluster staging |
| HPA/autoscaling | Không có load và replicas | Load/scale test |
| Long-running resource leaks | Vài requests ngắn | Soak testing |
| CDN/browser cache | Localhost bỏ qua CDN | Staging frontend journey |
| Network policy/DNS | Không ở pod/VPC thật | Network-level test |
| HTTP/2/compression | Nếu không bật hoặc không assert thì không biết | Dedicated protocol test |

Một test server thật chỉ chứng minh **các hành vi mà request thực sự đi qua và assertion thực sự kiểm tra**.

## 19. Lựa chọn bộ test phù hợp trong CI

Một chiến lược thường hiệu quả:

- **Nhiều unit tests** cho business/domain edge cases; chạy mỗi commit.
- **MVC/WebFlux slice tests** cho HTTP contract, validation, advice, auth mock; chạy mỗi commit/PR.
- **Một số full-context mock tests** để phát hiện sai DI/configuration, khi cần.
- **Live HTTP RANDOM_PORT tests** cho servlet routing, startup/listener, headers/cookies, HTTP transport; chạy mỗi PR.
- **Testcontainers/sandbox integration** cho DB/downstream, migrations và transactions; có isolation.
- **Staging smoke/browser E2E** cho proxy/TLS/cross-origin/real deployment.
- **Load/soak** để đo concurrency/p95/p99/throughput, không gộp vào functional integration tests.

Không cần lặp lại 100 trường hợp tính tiền qua Tomcat thật khi unit tests đã phủ branch đúng; chỉ một số contract/wiring/transport cases có giá trị khác biệt.

### 19.1. Các nguồn flaky thường gặp

- Hardcode 8080 cho test random port.
- `DEFINED_PORT` đụng service đang chạy.
- Test DB chia sẻ dữ liệu/ID giữa methods, transaction rollback bị hiểu sai.
- Mocking singleton giữ state giữa tests/context cache.
- Dùng `Thread.sleep(100)` để “chờ async”, thay vì await có timeout.
- Spring context caching làm dữ liệu mutable persist; `@DirtiesContext` lạm dụng.
- Parallel tests tạo cùng file/temp dir hoặc external resource.
- HTTP client không có timeout; test treo vô hạn.
- Dựng real context nhiều lần không cần thiết khiến CI chậm.
- Test method chỉ assert `status=200`, không assert đúng body/owner/Content-Type.

Phương án: random ports, unique fixtures, deterministic fake clocks, bounded awaits, Testcontainers isolation, explicit profiles và assertions có ý nghĩa.

## 20. Quy trình chẩn đoán test fail đúng tầng

1. **Unit fail:** kiểm tra business logic/conditions; không tìm lỗi Tomcat.
2. **Unit pass, MockMvc fail 404/405:** kiểm tra controller mapping, URL/method, context path và handler selection.
3. **MockMvc fail 400/415:** kiểm tra DTO/`@Valid`/converters/Content-Type.
4. **MockMvc pass, full-context mock fail startup:** kiểm tra dependency injection, config/profiles, missing beans.
5. **Full-context mock pass, live HTTP fail:** kiểm tra embedded server binding, servlet registration, filter chain, request paths, TCP, active port.
6. **Live HTTP pass, deployed ingress fail:** kiểm tra proxy rewrite, TLS, X-Forwarded-* và network policies.
7. **HTTP status đúng, body sai:** kiểm tra JSON naming, error advice, codec hoặc fallback route.
8. **Only real HTTP + database leaves rows:** kiểm tra transaction boundaries và fixture cleanup.
9. **Security mock pass, browser fail:** kiểm tra cookies, CSRF, CORS, redirect, TLS và identity flow.
10. **Functional tests pass nhưng production chậm:** cần load/soak profiling, không đổi hàng loạt functional tests thành performance tests.

Không lấy việc bỏ filter/disable validation/permitAll mọi route làm cách sửa “xanh build”. Sửa đúng component và thêm regression test ở boundary tương ứng.

### 20.1. Bảng triệu chứng nhanh

| Triệu chứng | Nghi ngờ chính | Hướng kiểm tra |
| --- | --- | --- |
| `@SpringBootTest` nhưng connection refused | `MOCK` không mở server | Dùng `RANDOM_PORT` |
| `@LocalServerPort` rỗng | Không có server | Kiểm tra webEnvironment |
| `@WebMvcTest` thiếu Service bean | Slice không scan service | `@MockitoBean` hoặc import |
| Unit test gọi controller PASS, HTTP 400 | MVC validation/conversion | MockMvc test body |
| MockMvc PASS, `/wire/ping` live 404 | Servlet mapping sai | Test `ServletRegistrationBean` |
| MockMvc filter PASS, servlet khác không có header | Container filter registration khác | Live HTTP non-MVC |
| Live HTTP 200 ở local, 404 sau proxy | Path rewrite/context path | Gateway E2E |
| Live POST 403 | Security/CSRF | Kiểm tra policy/credentials |
| TestRestTemplate nhận response 500 mà test không fail | Không assert status | Assert `getStatusCode()` |
| DB row tồn sau test `@Transactional RANDOM_PORT` | Client/server transactions khác nhau | Reset database |
| Cả WebFlux/MVC starters, test chạy MVC | Boot chọn MVC | Xác định web application type |
| MockMvc chỉ thấy HTML index | SPA fallback | Assert JSON Content-Type/body |
| CI lỗi port in use | Port cố định | `RANDOM_PORT` |
| Browser lỗi CORS dù curl 200 | Browser origin policy | Browser E2E |

## 21. Bài tập và tự kiểm tra

### Bài A: đổi mapping

Đổi `@PostMapping("/quotes")` thành `@PostMapping("/quote")` nhưng giữ tests cũ. Unit `PriceServiceTest` vẫn pass; MockMvc/live HTTP tests gọi `/api/quotes` fail. Bài học: mapping là trách nhiệm web layer.

### Bài B: bỏ `@Valid`

Giữ controller/service nhưng xóa `@Valid` trên `QuoteRequest`. `PriceService` vẫn tự reject quantity 0 thành `IllegalArgumentException`, và advice có thể vẫn trả 400. Vì vậy chỉ assert 400 chưa đủ chứng minh **Bean Validation** đã chạy. Thêm test kiểm tra validation-specific message/code hoặc mock verification service không được gọi với input invalid. Đây là ví dụ quan trọng về **false positives**.

### Bài C: bỏ advice

Xóa `ApiErrorHandler`. Unit tests vẫn phát đúng Java exception, nhưng HTTP error JSON contract biến đổi. MockMvc/live HTTP assertions cho `SKU_NOT_FOUND` phải fail.

### Bài D: đổi custom servlet mapping

Đổi `/wire/*` thành `/other/*`. Spring MVC slice tests vẫn pass, còn live `RealHttpServerTest.tomcatDispatchesNonMvcServlet` fail. Test này chứng minh rủi ro Servlet container routing mà MockMvc không bao phủ.

### Bài E: bật context path

Thêm `server.servlet.context-path=/shop`. Live paths gồm `/shop/api/quotes` và `/shop/wire/ping`. Trong MockMvc, cần thiết lập mock request context path đúng nếu mô phỏng chính xác Servlet context; không tự thêm `/shop` vào `@RequestMapping`.

### Bài F: thêm Security

Thêm Security starter và bảo vệ `/api/quotes` bằng role. Viết MockMvc test `@WithMockUser`/CSRF cho positive/negative; viết live test với credentials/session tương ứng. Kiểm chứng auth khác với việc tắt filters.

### Bài G: thêm PostgreSQL

Cho `PriceService` đọc giá từ DB; giữ slice test mock service để test MVC contract. Thêm live/full-context test với Testcontainers, schema migrations và data reset. Thực nghiệm vì sao `@Transactional` trên test live HTTP không tự rollback server transaction.

### Bài H: hai cách WebTestClient

Xây một WebTestClient bind-to-controller và một bind-to-server; cùng assertion JSON nhưng chỉ cái thứ hai chứng minh request qua socket. Ghi rõ binding trong tên test.

### Câu hỏi nhanh

1. **`@SpringBootTest` mặc định có mở cổng không?** Không, `MOCK`.
2. **MockMvc có đi qua DispatcherServlet không?** Có, với mock Servlet request/response.
3. **MockMvc có kiểm tra real Tomcat Servlet selection không?** Không.
4. **`@WebMvcTest` có load mọi repository/service không?** Không, slice MVC.
5. **`@MockitoBean` giải quyết gì?** Tạo/thay collaborator bean bằng mock trong test context.
6. **Full-context MockMvc có server không?** Không, trừ khi cấu hình một runtime server riêng.
7. **Cách test port thật?** `@SpringBootTest(RANDOM_PORT)` + HTTP client.
8. **Tại sao phải dùng `@LocalServerPort`?** Không hardcode port random.
9. **WebTestClient có luôn qua TCP không?** Không, tùy binding.
10. **Tại sao rollback test-side không đủ cho live HTTP?** Server và client chạy ở threads/transactions khác nhau.
11. **Test TCP local có chứng minh TLS/Ingress không?** Không nếu chưa test qua chúng.
12. **CORS từ curl có chứng minh Browser không?** Không.
13. **Một status 200 có đủ cho correctness không?** Không, cần body/headers/owner assertions.
14. **Lúc nào dùng MockMvc nhiều hơn live HTTP?** Khi kiểm tra MVC contracts/validation nhanh và có thể cô lập.
15. **Có cần cả ba cấp unit, mock, live không?** Có khi có rủi ro ở cả logic, MVC integration và actual server boundary.

## 22. Checklist trước khi xác nhận “web runtime đã được test”

- [ ] Ghi rõ test dùng unit/direct, MockMvc slice, full-context mock hay live HTTP.
- [ ] Không gọi `@SpringBootTest` mặc định là server integration.
- [ ] MVC contracts có tests method/path/JSON/`@Valid`/advice/error response.
- [ ] Collaborators chỉ mock trong slice nơi đúng mục đích.
- [ ] Full-context test xác nhận DI/configuration quan trọng.
- [ ] Khi có custom Servlet/Jersey, có live HTTP test cho URL owner.
- [ ] Dùng `RANDOM_PORT` và `@LocalServerPort` để tránh port conflicts.
- [ ] TestRestTemplate statuses 4xx/5xx đều được assert.
- [ ] Headers, Content-Type, body và status được kiểm tra thay vì chỉ 200.
- [ ] Spring Security/CSRF/CORS được test đúng filter/runtime và có negative cases.
- [ ] Database transactions/cleanup không dựa nhầm test-side rollback khi server thread khác.
- [ ] Test dependencies không trộn sai Boot 3.5/Boot 4 API.
- [ ] Reverse proxy/TLS/management port được kiểm thử ở đúng môi trường.
- [ ] Có smoke test qua executable JAR khi packaging có ảnh hưởng.
- [ ] Browser E2E được dùng cho client-side enforcement và UI flows.
- [ ] Load/soak tests dành cho concurrency/throughput, không suy từ functional HTTP tests.
- [ ] Suite đủ nhanh/deterministic, không dùng fixed port/sleep/fixtures tranh chấp.
- [ ] Kết luận test nêu chính xác boundary nào được kiểm chứng.

## 23. Tài liệu tham khảo chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): MOCK, RANDOM_PORT, DEFINED_PORT, NONE, MockMvc, TestRestTemplate, WebTestClient và rollback caveat.
- [Spring Boot 3.5 — Auto-configured Spring MVC Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.spring-mvc-tests): `@WebMvcTest`, `@MockitoBean`, MockMvc configuration.
- [Spring Framework 6.2 — MockMvc Overview](https://docs.spring.io/spring-framework/reference/6.2/testing/mockmvc/overview.html): MVC request processing với mock Servlet objects.
- [Spring Framework — MockMvc Setup Options](https://docs.spring.io/spring-framework/reference/testing/mockmvc/setup-options.html): `standaloneSetup` vs `webAppContextSetup`.
- [Spring Framework — MockMvc Request Builders](https://docs.spring.io/spring-framework/reference/testing/mockmvc/hamcrest/requests.html): xây mock requests.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): bind-to-controller/context/server.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): Tomcat và server properties.
- [Spring Security — MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): mock user, filters và CSRF.
- [Spring Framework — Test Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback/transaction boundaries.
- [JUnit Jupiter User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit lifecycle, assertions, parallel execution.

**Kết luận:** `MockMvc` kiểm tra Spring MVC bằng request/response giả lập nhưng **không mở cổng**. `RANDOM_PORT` cho phép thử **server thật** (Tomcat/Servlet registration/TCP/HTTP) và kiểm tra những thứ mock không thấy. Không dùng một cấp thay thế tất cả: unit tests bảo vệ logic, MVC slice bảo vệ HTTP contract, full-context mock bảo vệ wiring, live HTTP bảo vệ container boundary, và staging/browser/load tests bảo vệ các ranh giới triển khai còn lại.