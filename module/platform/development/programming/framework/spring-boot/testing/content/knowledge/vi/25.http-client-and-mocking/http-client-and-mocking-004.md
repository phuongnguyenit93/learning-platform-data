# HTTP stub server cho WebClient và HTTP client cần kiểm chứng transport

## Mục tiêu bài học

Khi ứng dụng Spring Boot gọi REST API của đối tác bằng `WebClient`, có ít nhất hai câu hỏi khác nhau:

1. **Logic của client có đúng không?** Ví dụ: status `404` được chuyển thành exception nào, dữ liệu JSON được giải mã thành DTO ra sao, có retry hay không.
2. **HTTP request thật có đúng không?** Ví dụ: client có gửi đúng `GET/POST`, path, query parameters, headers, JSON body, content type, authorization, TLS, timeout và encoding qua một kết nối HTTP thật hay không.

Mock một interface Java hoặc `ExchangeFunction` có thể trả về `ClientResponse` tùy ý mà **không hề tạo TCP connection, serialize một HTTP request thật hoặc chạy HTTP codec/runtime như cấu hình sản xuất**. Khi hợp đồng cần bao phủ **transport**, một **HTTP stub server** chạy trên loopback với cổng động — ví dụ **WireMock** hoặc **OkHttp MockWebServer** — là lựa chọn phù hợp hơn.

Bài thuộc nhóm **HTTP client và giả lập** của module **Spring Boot – testing**, đi sâu vào đề bài **HTTP stub server cho WebClient và client cần kiểm chứng transport**. Trọng tâm là kiểm outbound HTTP client, không nhầm với kiểm controller/inbound server.

Sau bài này, bạn có thể:

- Phân biệt mock collaborator, fake `ExchangeFunction`, HTTP stub server và sandbox API thật.
- Dùng WireMock 3 tạo HTTP server trên **cổng ngẫu nhiên** để tránh xung đột trong CI.
- Dùng chính `WebClient` và `ClientHttpConnector` để phát HTTP request thật đến stub.
- Kiểm HTTP method, path, URI encoding, query parameters, headers, media type, JSON serialization/deserialization.
- Stub và xác minh phản hồi `2xx`, `404`, `503`, `204 No Content`, phản hồi chậm và sự khác nhau giữa **HTTP errors** với **transport errors**.
- Dùng `StepVerifier` của Reactor để kiểm `Mono` bất đồng bộ mà không tùy tiện `Thread.sleep`.
- Chọn giữa một **JUnit integration test thuần** và một **`@SpringBootTest`** khi cần xác minh cấu hình `WebClient.Builder` của ứng dụng.
- Cấu hình base URL động, quản lý lifecycle/reset, tránh rò request journal và tránh gọi API thật.
- Đọc lỗi WireMock “unmatched request” để phát hiện request encoding/header mismatch.
- Hiểu giới hạn của stub server đối với DNS, TLS truststore, HTTP/2, reverse proxy, connection pooling, backpressure và network faults production.
- Chạy ví dụ đầy đủ bằng **Java 17, Spring Boot 3.3.5, Gradle, WebFlux/WebClient, WireMock 3.9.2, JUnit Jupiter và Reactor Test**.

**Quy tắc:** Nếu lỗi cần bắt có thể chỉ xảy ra khi **HTTP bytes đi qua socket** (URI encoding, request headers thực, client runtime timeout, connection reset…), đừng chỉ dùng mock trả `Mono.just(...)`. Hãy để client thật gọi một stub HTTP server và kiểm cả **outbound request** lẫn **inbound response**.

## 1. HTTP stub server là gì?

Một HTTP stub server là một HTTP service **do test điều khiển**, lắng nghe trên một local address/port và trả response theo các điều kiện matching được khai báo. Với WireMock, test có thể:

1. Đăng ký request matcher: `GET /api/v1/products/BK-001?include=stock`.
2. Định nghĩa response: status `200`, header `Content-Type: application/json`, JSON body.
3. Thực thi code client thật, ví dụ `partnerGateway.getProduct("BK-001")`.
4. Xem request journal: server nhận request đúng phương thức, URL, header, body bao nhiêu lần?
5. Đăng ký lỗi khác, ví dụ `503`, `404`, delay hoặc connection fault, rồi kiểm ứng xử của client.

Mô hình:

~~~text
JUnit Jupiter test
   |
   |   gọi SUT (PartnerGateway)
   v
Spring WebClient
   |
   |  ClientHttpConnector / Reactor Netty
   |  HTTP trên localhost + cổng động
   v
WireMock HTTP stub server
   |
   +-- match GET/POST/path/query/header/body
   +-- response 200/204/404/503 + JSON
   +-- optional delay/connection fault
   +-- lưu request journal để verify
   |
   v
WebClient response decoding/status mapping
   |
   v
Mono<Product> / Mono<ReserveReceipt> / error
   |
   v
StepVerifier + WireMock.verify(...)
~~~

Điểm quan trọng: **stub server không phải production server**. Test không cần quyền gọi internet hay credentials thật. Đồng thời nó vẫn cho phép **cùng client runtime** thực hiện request qua HTTP, không phải trả thẳng Java object cho service.

### Điều gì được kiểm thật?

- WebClient phát request qua HTTP connector thực.
- URI builder tạo đúng path/query và encode các giá trị được truyền.
- Các headers cuối cùng gửi lên wire (theo WireMock journal).
- Jackson hoặc HTTP message codecs chuyển Java record thành JSON và ngược lại.
- Xử lý status codes qua `retrieve()`/`onStatus`.
- Response timeout, cancellation và các lỗi ở mức HTTP trong môi trường local có kiểm soát.

### Điều gì chưa được bảo đảm?

- Server bên ngoài thực sự dùng đúng business protocol/schema mới nhất.
- DNS, TLS certificates, CDN, gateway, load balancer, proxy hoặc authentication production.
- Độ trễ của internet, packet loss, kết nối chập chờn trên một mạng WAN thật.
- HTTP/2 negotiation/TLS handshake nếu stub chỉ chạy **HTTP/1.1 không mã hóa**.
- Contract giữa hai team nếu stub mappings không được đồng bộ với OpenAPI/Pact/provider.
- Retry/backoff/connection pool trong tải lớn trừ khi tạo tests chuyên biệt.

Stub server là **một lớp kiểm thử trung gian** giữa unit test thuần và end-to-end test với hệ thống bên ngoài.

## 2. Khi nào mock WebClient và khi nào cần server thật?

| Mục tiêu | Cách kiểm phù hợp | Khả năng bắt lỗi |
| --- | --- | --- |
| Mapping thuần Java, format một message | Unit test không Spring | Logic Java |
| Service có collaborator `PartnerGateway` | Mockito mock interface/collaborator | Nhánh logic của service |
| Chỉ muốn giả lập `ClientResponse` | Fake `ExchangeFunction` | Reactor handling và client logic, không có socket |
| Cần biết URL, headers, HTTP method, JSON bytes | **WireMock/MockWebServer + WebClient thật** | HTTP request/response ở transport path local |
| Cần biết `WebClient.Builder` được Spring Boot cấu hình ra sao | `@SpringBootTest` + HTTP stub | Wiring, properties, codecs, filters/customizers |
| Cần kiểm outbound TLS/mTLS thực | HTTPS stub + trust/key material dành riêng test | TLS handshake/certificate/client config |
| Cần xác minh provider contract | Consumer-driven contract test hoặc provider sandbox | Mức tương thích với API thực |
| Cần kiểm toàn bộ request/response từ UI đến third party | End-to-end test có hạ tầng riêng | Hệ thống liên kết, chi phí/flakiness cao hơn |

**Anti-pattern 1:** Mock `PartnerGateway` rồi tuyên bố đã kiểm `WebClient gửi đúng Authorization header`. Khi service không chạy HTTP code thật, kết luận này không có bằng chứng.

**Anti-pattern 2:** Unit test trực tiếp mock chain `webClient.get().uri(...).retrieve().bodyToMono(...)`. Mock chain dễ vỡ khi refactor và có thể làm test xanh dù URI encoding/header thật sai.

**Anti-pattern 3:** Dùng `@WebFluxTest` để kiểm một outbound client mà không thật sự khởi chạy client/network path. `@WebFluxTest` tập trung **WebFlux controllers**; `WebTestClient` thường kiểm **inbound web handler**. Nó không thay thế HTTP stub server cho một `WebClient` gọi đối tác bên ngoài.

## 3. Hai HTTP test doubles phổ biến

### 3.1. WireMock

WireMock có:

- HTTP server chạy in-process hoặc standalone.
- Request matching theo method/path/query/header/cookies/body.
- Response stubbing JSON, status, headers, fixed delay, faults.
- Request journal và `verify` số lần gọi.
- Scenario/state machine, record/playback và proxy.
- JUnit Jupiter extension hoặc `WireMockServer` start/stop thủ công.

Bài chọn **WireMock 3.9.2** cho ví dụ runnable vì API Java ổn định, có cả request matching và verification rõ ràng. Không cần Docker để chạy WireMock dạng Java server in-process.

### 3.2. OkHttp MockWebServer

`MockWebServer` nhận request HTTP thật và có thể **enqueue** `MockResponse`, kiểm `RecordedRequest`. Nó gọn với các test tuyến tính (một request → một response) hoặc socket policies. Khi cần match nhiều endpoints/headers phức tạp, WireMock DSL thuận tiện hơn.

Mẫu kiến trúc (không phải class runnable):

~~~java
MockWebServer server = new MockWebServer();
server.start();

server.enqueue(new MockResponse()
        .setResponseCode(200)
        .setBody("{\"ok\":true}")
        .addHeader("Content-Type", "application/json"));

WebClient client = WebClient.builder()
        .baseUrl(server.url("/").toString())
        .build();

// ... gọi client, xem RecordedRequest ...

server.shutdown();
~~~

Đây là snippet cần `okhttp3.mockwebserver` dependency/imports và code subscription. Khi chọn MockWebServer, vẫn phải kiểm request thực tế, không chỉ verify DTO Java.

### Tại sao cổng động quan trọng?

Cấu hình WireMock fixed port `8080` dễ xung đột với app đang chạy hoặc một job CI khác. Dùng:

~~~java
new WireMockServer(wireMockConfig().dynamicPort());
~~~

Sau `server.start()`, gọi `server.baseUrl()` để lấy URL thật. Nếu dùng JUnit extension, có thể gọi `wireMockExtension.port()` hoặc runtime info. **Không gán `http://localhost:8080` cho client** khi server đã chọn cổng động.

## 4. WebClient và runtime transport

`WebClient` thuộc Spring WebFlux. Khi có `spring-boot-starter-webflux`, Spring Boot thường tự cấu hình một `WebClient.Builder` được tùy biến theo các HTTP codecs, observability, SSL bundles hoặc client connector phù hợp với classpath.

Ví dụ thành phần ứng dụng:

~~~java
@Service
class PartnerService {
    private final WebClient webClient;

    PartnerService(WebClient.Builder builder,
                   @Value("${partner.base-url}") String baseUrl) {
        this.webClient = builder.baseUrl(baseUrl).build();
    }
}
~~~

Đây là snippet kiến trúc; project đầy đủ nằm ở phần 8. Builder có thể sử dụng Reactor Netty khi starter WebFlux đem Reactor Netty vào classpath. **Không mặc định mọi WebClient đều là Reactor Netty**: ứng dụng có thể chọn JDK HTTP, Jetty hoặc custom `ClientHttpConnector`. Bằng chứng cuối cùng phải đến từ classpath/configuration thực tế và phép thử transport tương ứng.

### Cấu hình qua Builder hay `WebClient.create`?

- **Inject `WebClient.Builder` của Spring Boot**: bảo vệ wiring production như filters/customizers, codecs và HTTP connector do Boot cấu hình.
- **`WebClient.builder()` trong JUnit thuần**: đủ để test request/response logic và transport HTTP mặc định trên classpath, nhưng không khẳng định mọi Boot customization của ứng dụng.
- **`WebClient.create(baseUrl)`**: đơn giản, nhưng không tự áp dụng những `WebClientCustomizer` Boot chỉ gắn trên injected builder.

Do đó ví dụ có **hai tầng**: test JUnit thuần thực hiện HTTP thật; test Spring Boot full-context xác nhận injectable `WebClient.Builder` cũng đi đến stub server.

### HTTP transport error khác HTTP status error

Phân biệt:

- **HTTP status error:** Server thực sự trả response, ví dụ `404`, `503`. Với `retrieve()` mặc định, WebClient thường tạo `WebClientResponseException` cho 4xx/5xx, trừ khi `onStatus` tùy biến.
- **Network/transport error:** DNS fail, connection refused/reset, SSL handshake fail, read timeout, connection pool acquisition fail. Không nhất thiết có HTTP status vì response chưa được nhận hoặc không hoàn chỉnh. Lỗi thường đi qua `WebClientRequestException` và nested causes, nhưng chính xác exception chain tùy connector.
- **Publisher timeout:** `mono.timeout(Duration...)` có thể phát `TimeoutException` khi không có signal đúng hạn; đây là Reactor operator timeout, không đồng nghĩa socket-level read timeout.
- **Decode error:** HTTP 200 có body JSON không phù hợp DTO; có thể gây exception decode chứ không phải HTTP status error.

Test phải mô phỏng **đúng loại failure** mới bảo vệ được code xử lý failure đó.

## 5. Thiết kế fixture HTTP có tính phản ví dụ

Stub một response bất kỳ và kiểm `Mono` emit một object đôi khi chưa đủ. Một fixture tốt phải bắt được:

| Thuộc tính request/response | Ca nên tạo | Bug được phát hiện |
| --- | --- | --- |
| Method | GET đọc product; POST tạo reservation | Client gửi sai method |
| Path | `/api/v1/products/BK-001` | Client thiếu version hoặc sai SKU |
| Query | `include=stock` | Client bỏ param |
| Query encoding | `q=Java & Spring` | Dấu `&` bị tách thành param khác |
| Default header | `X-Client-Name: shop-backend` | Filter/builder không áp dụng |
| Accept | `application/json` | Client không khai báo format mong muốn |
| Content-Type | POST `application/json` | DTO bị gửi sai media type |
| JSON body | `sku=BK-001`, `quantity=2` | Serializer/sai tên field/quantity |
| Correlation ID | `X-Request-Id: req-007` | Client không truyền trace/business request ID |
| 200 | Product DTO hợp lệ | Mapping response |
| 404 | Product không tồn tại | Business error mapping |
| 503 | Provider unavailable | Propagate đúng HTTP error |
| 204 | Body rỗng | Xử lý empty completion thay vì giả định DTO |
| Delay | Server chậm rõ rệt | Timeout và cancel policy |
| Request count | Đúng một request | Bắt duplicate call/retry ngoài ý muốn |

**Expected độc lập**: Không dựng expected JSON bằng chính serializer đang test rồi dùng cùng serializer để verify, vì cả hai có thể cùng sai. Dùng JSON literal/fixture có các fields và values từ API contract.

**Không kiểm mỗi `verify(1, getRequestedFor(...))` mà bỏ qua response mapping.** Khi body decode sai, request có thể vẫn đúng. Cần kiểm **cả hai chiều**.

## 6. Kiến trúc project chạy được

Project dùng **Java 17 + Spring Boot 3.3.5 + Gradle + JUnit 5 + WireMock 3.9.2**. Không cần Docker hoặc API đối tác thật.

- **`PartnerGateway`** là production adapter chứa WebClient.
- Method `getProduct` gọi GET có path variable, query `include=stock`, Accept header và tùy biến 404.
- Method `searchOne` kiểm query parameter chứa space/`&`.
- Method `reserve` gọi POST và serialize JSON body, kèm header `X-Request-Id`.
- Test class `PartnerGatewayTransportTest` start/stop một WireMock server **mỗi test method**, tạo gateway với WebClient thực và kiểm request/response.
- Test class `PartnerGatewayBootWiringTest` bootstrap Spring Boot full context, cấp `partner.base-url` qua `@DynamicPropertySource`, inject **Boot WebClient.Builder** qua service và xác minh outbound traffic thật.
- Các test mô phỏng **404, 503, 204, slow response**, không thực hiện request tới internet.

### 6.1. Cây thư mục

~~~text
webclient-transport-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/transport/
    │   ├── TransportDemoApplication.java
    │   └── PartnerGateway.java
    └── test/java/com/example/transport/
        ├── PartnerGatewayTransportTest.java
        └── PartnerGatewayBootWiringTest.java
~~~

Wrapper scripts/JAR cần được tạo từ Gradle phù hợp hoặc lấy từ project có sẵn; `gradle-wrapper.jar` là binary, không thể dựng bằng chép Markdown.

### 6.2. `settings.gradle`

~~~groovy
rootProject.name = 'webclient-transport-lab'
~~~

### 6.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
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
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'org.wiremock:wiremock-standalone:3.9.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

**Tại sao các dependencies này đủ cho ví dụ?**

- `spring-boot-starter-webflux`: `WebClient`, Reactor, JSON codecs qua Jackson, và HTTP connector Reactor Netty mặc định.
- `spring-boot-starter-test`: Spring TestContext, JUnit Jupiter, assertions và Spring Boot testing.
- `reactor-test`: `StepVerifier` để kiểm `Mono` mà không tự sleep/poll.
- `wiremock-standalone:3.9.2`: WireMock Java HTTP server với dependencies đóng gói/shaded để giảm xung đột classpath.
- `junit-platform-launcher` và `useJUnitPlatform()` hỗ trợ Gradle/JUnit Jupiter.
- Không cần `@WebFluxTest`, vì mục tiêu là outbound `WebClient` chứ không phải controller.
- Không cần H2, database, Testcontainers hoặc Docker.

**Ghi chú version:** Project chốt Boot **3.3.5** và WireMock **3.9.2**, không tự pha trộn import/class API của WireMock 4 beta hoặc Spring Boot 4. Trong dự án thực, dùng BOM/versions chuẩn hóa của team và kiểm dependencies để tránh xung đột Netty/Jackson/SLF4J.

### 6.4. `TransportDemoApplication.java`

~~~java
package com.example.transport;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TransportDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TransportDemoApplication.class, args);
    }
}
~~~

Ứng dụng demo cần `partner.base-url` để tạo `PartnerGateway`. Với test Spring Boot, giá trị này được cấp từ WireMock local. Nếu chạy `bootRun` mà không cấu hình property, startup có thể báo thiếu `partner.base-url`, đó là bảo vệ tốt hơn việc âm thầm gọi URL production. Mục tiêu runnable của bài là **`gradlew test`**.

### 6.5. `PartnerGateway.java`: outbound adapter thật

~~~java
package com.example.transport;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class PartnerGateway {

    private final WebClient webClient;

    public PartnerGateway(
            WebClient.Builder builder,
            @Value("${partner.base-url}") String baseUrl) {

        this.webClient = builder
                .baseUrl(baseUrl)
                .defaultHeader("X-Client-Name", "shop-backend")
                .build();
    }

    public Mono<Product> getProduct(String sku) {
        return webClient.get()
                .uri(builder -> builder
                        .path("/api/v1/products/{sku}")
                        .queryParam("include", "stock")
                        .build(sku))
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .onStatus(
                        code -> code.value() == 404,
                        response -> response.createException()
                                .map(error ->
                                    new ProductNotFoundException(
                                            sku, error)))
                .bodyToMono(Product.class)
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "Empty body for product " + sku)));
    }

    public Mono<Product> searchOne(String term) {
        return webClient.get()
                .uri(builder -> builder
                        .path("/api/v1/search")
                        .queryParam("q", "{term}")
                        .build(term))
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .bodyToMono(Product.class);
    }

    public Mono<ReserveReceipt> reserve(
            ReserveRequest request, String requestId) {

        return webClient.post()
                .uri("/api/v1/reservations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header("X-Request-Id", requestId)
                .bodyValue(request)
                .retrieve()
                .bodyToMono(ReserveReceipt.class);
    }

    public Mono<Product> getProductWithTimeout(
            String sku, Duration timeout) {

        // Đây là Reactor publisher timeout; không phải
        // socket read-timeout của Netty.
        return getProduct(sku).timeout(timeout);
    }

    public record Product(
            String sku, String title, long priceCents) {
    }

    public record ReserveRequest(
            String sku, int quantity) {
    }

    public record ReserveReceipt(
            String reservationId, String state) {
    }

    public static class ProductNotFoundException
            extends RuntimeException {

        public ProductNotFoundException(
                String sku, Throwable cause) {
            super("Product not found: " + sku, cause);
        }
    }
}
~~~

**Vì sao production code trên phù hợp với bài test transport?**

1. Dùng `WebClient.Builder` nên full-context test có thể đưa vào cùng Boot builder/customizers thay vì dựng một mock chain.
2. `baseUrl` được inject qua property `partner.base-url`, giúp test trỏ client tới stub HTTP server mà không sửa production logic.
3. `getProduct` dùng path variable **không nối string thô** vào URI; query parameter được tách riêng.
4. `searchOne` dùng `"{term}"` làm URI variable trong query: dấu cách và ký tự `&` được encode theo URI variable handling của WebClient.
5. `defaultHeader` thêm `X-Client-Name` để test xác nhận request header cuối cùng.
6. `reserve` serialize `ReserveRequest` thành JSON bằng HTTP codec thật, rồi deserialize `ReserveReceipt`.
7. `retrieve()` xử lý 4xx/5xx mặc định; riêng `404` được map thành `ProductNotFoundException` bằng `onStatus`.
8. `response.createException()` tiêu thụ body lỗi để lấy exception gốc trước khi bọc, tránh để một response body chưa được xử lý.
9. `switchIfEmpty` nêu rõ hợp đồng: GET product **không chấp nhận body rỗng**; 204 không lặng lẽ trở thành sản phẩm `null`.
10. `getProductWithTimeout` minh họa một **Reactor publisher timeout** mà test có thể kiểm, không khẳng định đã cấu hình TCP socket/connect timeout.

### Tại sao dùng Java records?

Java 17 hỗ trợ `record` và Jackson do Spring Boot quản lý có thể serialize/deserialize record DTO trong ngữ cảnh phù hợp. Các giá trị tiền được diễn tả dưới dạng `priceCents: long` để tránh sai số floating point trong bài học transport. Business thật cần kiểm currency/precision/validation riêng.

## 7. Test HTTP transport bằng WireMockServer và JUnit Jupiter

**`src/test/java/com/example/transport/PartnerGatewayTransportTest.java`**

~~~java
package com.example.transport;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.test.StepVerifier;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PartnerGatewayTransportTest {

    private WireMockServer server;
    private PartnerGateway gateway;

    @BeforeEach
    void startServerAndCreateRealClient() {
        server = new WireMockServer(
                wireMockConfig().dynamicPort());
        server.start();

        // Không mock ExchangeFunction: WebClient gọi qua HTTP.
        gateway = new PartnerGateway(
                WebClient.builder(), server.baseUrl());
    }

    @AfterEach
    void stopServer() {
        if (server != null && server.isRunning()) {
            server.stop();
        }
    }

    @Test
    void getSendsCorrectMethodPathQueryAndHeaders() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/BK-001"))
                .withQueryParam("include", equalTo("stock"))
                .withHeader("X-Client-Name",
                        equalTo("shop-backend"))
                .withHeader("Accept",
                        containing("application/json"))
                .willReturn(okJson(
                    "{\"sku\":\"BK-001\","
                    + "\"title\":\"Java Basics\","
                    + "\"priceCents\":2500}")));

        StepVerifier.create(gateway.getProduct("BK-001"))
                .assertNext(product -> {
                    assertEquals("BK-001", product.sku());
                    assertEquals("Java Basics", product.title());
                    assertEquals(2500L, product.priceCents());
                })
                .verifyComplete();

        server.verify(1, getRequestedFor(
                    urlPathEqualTo("/api/v1/products/BK-001"))
                .withQueryParam("include", equalTo("stock"))
                .withHeader("X-Client-Name",
                        equalTo("shop-backend"))
                .withHeader("Accept",
                        containing("application/json")));
    }

    @Test
    void queryParameterIsEncodedAndNotSplitByAmpersand() {
        server.stubFor(get(urlPathEqualTo("/api/v1/search"))
                .withQueryParam("q",
                        equalTo("Java & Spring"))
                .willReturn(okJson(
                    "{\"sku\":\"BK-010\","
                    + "\"title\":\"Java & Spring\","
                    + "\"priceCents\":4100}")));

        StepVerifier.create(
                    gateway.searchOne("Java & Spring"))
                .assertNext(result -> {
                    assertEquals("BK-010", result.sku());
                    assertEquals("Java & Spring",
                            result.title());
                })
                .verifyComplete();

        server.verify(1, getRequestedFor(
                    urlPathEqualTo("/api/v1/search"))
                .withQueryParam("q",
                        equalTo("Java & Spring")));
    }

    @Test
    void postSerializesJsonAndCorrelationHeader() {
        server.stubFor(post(
                    urlEqualTo("/api/v1/reservations"))
                .withHeader("Content-Type",
                        containing("application/json"))
                .withHeader("X-Request-Id",
                        equalTo("req-007"))
                .withRequestBody(equalToJson(
                    "{\"sku\":\"BK-001\",\"quantity\":2}"))
                .willReturn(okJson(
                    "{\"reservationId\":\"RES-9\","
                    + "\"state\":\"ACCEPTED\"}")));

        StepVerifier.create(
                    gateway.reserve(
                        new PartnerGateway.ReserveRequest(
                                "BK-001", 2),
                        "req-007"))
                .assertNext(result -> {
                    assertEquals("RES-9",
                            result.reservationId());
                    assertEquals("ACCEPTED", result.state());
                })
                .verifyComplete();

        server.verify(1, postRequestedFor(
                    urlEqualTo("/api/v1/reservations"))
                .withHeader("Content-Type",
                        containing("application/json"))
                .withHeader("X-Request-Id",
                        equalTo("req-007"))
                .withRequestBody(equalToJson(
                    "{\"sku\":\"BK-001\",\"quantity\":2}")));
    }

    @Test
    void notFoundMapsHttp404ToDomainError() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/MISSING"))
                .willReturn(aResponse()
                    .withStatus(404)
                    .withHeader("Content-Type",
                            "application/json")
                    .withBody("{\"code\":\"NOT_FOUND\"}")));

        StepVerifier.create(gateway.getProduct("MISSING"))
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(
                        PartnerGateway.ProductNotFoundException.class,
                        error);
                    assertEquals(
                        "Product not found: MISSING",
                        error.getMessage());
                })
                .verify();

        server.verify(1, getRequestedFor(
                urlPathEqualTo("/api/v1/products/MISSING")));
    }

    @Test
    void serviceUnavailableRetainsHttpStatus() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/DOWN"))
                .willReturn(aResponse()
                    .withStatus(503)
                    .withHeader("Content-Type",
                            "application/json")
                    .withBody("{\"error\":\"unavailable\"}")));

        StepVerifier.create(gateway.getProduct("DOWN"))
                .expectErrorSatisfies(error -> {
                    WebClientResponseException ex =
                        assertInstanceOf(
                            WebClientResponseException.class,
                            error);
                    assertEquals(503,
                            ex.getStatusCode().value());
                    assertTrue(ex.getResponseBodyAsString()
                            .contains("unavailable"));
                })
                .verify();
    }

    @Test
    void noContentDoesNotBecomeFakeProduct() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/EMPTY"))
                .willReturn(aResponse().withStatus(204)));

        StepVerifier.create(gateway.getProduct("EMPTY"))
                .expectErrorSatisfies(error -> {
                    IllegalStateException ex =
                        assertInstanceOf(
                            IllegalStateException.class,
                            error);
                    assertEquals(
                        "Empty body for product EMPTY",
                        ex.getMessage());
                })
                .verify();
    }

    @Test
    void slowResponseCausesReactivePublisherTimeout() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/SLOW"))
                .willReturn(aResponse()
                    .withStatus(200)
                    .withHeader("Content-Type",
                            "application/json")
                    .withFixedDelay(1500)
                    .withBody(
                        "{\"sku\":\"SLOW\","
                        + "\"title\":\"Slow\","
                        + "\"priceCents\":1}")));

        StepVerifier.create(
                    gateway.getProductWithTimeout(
                            "SLOW", Duration.ofMillis(250)))
                .expectError(TimeoutException.class)
                .verify(Duration.ofSeconds(5));

        // Không assert một response JSON: timeout đã
        // kết thúc reactive pipeline trước khi nhận body.
    }

    @Test
    void monoIsColdAndSendsNoRequestBeforeSubscription() {
        server.stubFor(get(
                    urlPathEqualTo("/api/v1/products/COLD"))
                .willReturn(okJson(
                    "{\"sku\":\"COLD\","
                    + "\"title\":\"Cold Mono\","
                    + "\"priceCents\":99}")));

        var result = gateway.getProduct("COLD");

        // Chỉ dựng Mono, chưa subscribe -> chưa gửi HTTP.
        server.verify(0, getRequestedFor(
                urlPathEqualTo("/api/v1/products/COLD")));

        StepVerifier.create(result)
                .assertNext(value ->
                    assertEquals("COLD", value.sku()))
                .verifyComplete();

        server.verify(1, getRequestedFor(
                urlPathEqualTo("/api/v1/products/COLD")));
    }
}
~~~

### Vì sao bộ test này thật sự kiểm transport?

**`WireMockServer` có cổng động và socket HTTP thật.** `server.start()` gọi trước khi client tạo base URL; `server.baseUrl()` trả endpoint hiện tại. Không có JDK interface mock nào thay `WebClient` hoặc `ClientHttpConnector`.

**WireMock matcher ở phía server** nhìn được các request sau khi đã qua URI encoding, HTTP header encoding và serialization. Ví dụ, nếu client vô tình nối chuỗi `"?q=Java & Spring"` mà không encode, matcher `withQueryParam("q", equalTo("Java & Spring"))` có thể không match, dù Java string phía client trông có vẻ đúng.

**`equalToJson`** so nội dung JSON theo cấu trúc. Nó không mặc định yêu cầu thứ tự object keys giống nguyên văn, vì JSON object ordering thường không thuộc API contract. Khi contract cần field bắt buộc, matcher mặc định không bỏ qua unexpected fields theo cách lỏng lẻo một cách vô ý.

**`StepVerifier`** kiểm publisher phát đúng một signal value hoặc đúng error. Không dùng `block()` hoặc `Thread.sleep(...)` tùy tiện trong mỗi test.

**Request count** được verify ở server. Một bug làm client gửi hai request trong cùng một test có thể bị bắt bởi `verify(1, ...)`, kể cả hai request trả cùng DTO.

**HTTP status/error** được tạo bởi stub server, rồi đi qua WebClient `retrieve()` và xử lý reactive thật. Không tạo `WebClientResponseException` bằng tay chỉ để ép test pass.

### Về test timeout

- Stub giữ response **1.500 ms**.
- Client pipeline đặt `Mono.timeout(250 ms)`.
- Test chờ tối đa 5 giây cho verification.
- Expected là `java.util.concurrent.TimeoutException` từ **Reactor timeout operator**.
- Điều này **không chứng minh** rằng Netty `responseTimeout` hay TCP connect-timeout đã được cấu hình.
- Một CI quá tải có thể làm timing tests nhiễu; nếu bài test biến thành flaky, hãy điều chỉnh timeout/delay có biên đủ lớn hoặc dùng virtual time đối với logic thời gian thuần. Không dùng `VirtualTimeScheduler` để tuyên bố đã kiểm socket timeout thật.

### Vì sao reset server theo method?

`@BeforeEach` tạo một server mới, `@AfterEach` dừng server. Vì mỗi test có request journal và stubs riêng, không có chuyện test trước để lại mapping mà test sau vô tình dùng. Đổi lại, startup HTTP server cho từng method tốn thời gian hơn. Với suite lớn, có thể start một server theo class và gọi `resetAll()` trước từng test, nhưng cần quản lý parallel test methods.

## 8. Kiểm Spring Boot wiring: injected `WebClient.Builder` cũng phải gọi stub

Test JUnit thuần dùng `WebClient.builder()` thật, nhưng chưa chứng minh **Spring Boot WebClient.Builder** được inject vào `@Service`, và base URL nhận từ application properties đúng.

Để kiểm wiring, thêm một class `@SpringBootTest` sử dụng cùng production `PartnerGateway`. WireMock được start **trước khi Spring resolve dynamic property**, và context được evict sau class để tránh reuse một DataSource/HTTP client trỏ server đã dừng.

**`src/test/java/com/example/transport/PartnerGatewayBootWiringTest.java`**

~~~java
package com.example.transport;

import com.github.tomakehurst.wiremock.WireMockServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import reactor.test.StepVerifier;

import static com.github.tomakehurst.wiremock.client.WireMock.*;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;
import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
    classes = TransportDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class PartnerGatewayBootWiringTest {

    // Cố ý start trước khi Spring tạo ApplicationContext.
    // Chỉ một class dùng URL này, context được evict cuối class.
    private static final WireMockServer SERVER =
            startServer();

    private static WireMockServer startServer() {
        WireMockServer server = new WireMockServer(
                wireMockConfig().dynamicPort());
        server.start();
        return server;
    }

    @DynamicPropertySource
    static void registerPartnerUrl(
            DynamicPropertyRegistry registry) {
        registry.add("partner.base-url",
                SERVER::baseUrl);
    }

    @Autowired
    private PartnerGateway gateway;

    @BeforeEach
    void resetStubMappingsAndRequestJournal() {
        SERVER.resetAll();
    }

    @AfterAll
    static void stopStub() {
        SERVER.stop();
    }

    @Test
    void bootConfiguredClientCallsLocalStub() {
        SERVER.stubFor(get(
                    urlPathEqualTo("/api/v1/products/BOOT-1"))
                .withHeader("X-Client-Name",
                        equalTo("shop-backend"))
                .withQueryParam("include",
                        equalTo("stock"))
                .willReturn(okJson(
                    "{\"sku\":\"BOOT-1\","
                    + "\"title\":\"Spring Boot\","
                    + "\"priceCents\":7000}")));

        StepVerifier.create(gateway.getProduct("BOOT-1"))
                .assertNext(value -> {
                    assertEquals("BOOT-1", value.sku());
                    assertEquals(7000L, value.priceCents());
                })
                .verifyComplete();

        SERVER.verify(1, getRequestedFor(
                    urlPathEqualTo("/api/v1/products/BOOT-1"))
                .withQueryParam("include",
                        equalTo("stock")));
    }

    @Test
    void bootConfiguredClientSerializesPostBody() {
        SERVER.stubFor(post(
                    urlEqualTo("/api/v1/reservations"))
                .withHeader("X-Request-Id",
                        equalTo("boot-request"))
                .withRequestBody(equalToJson(
                    "{\"sku\":\"BOOT-1\",\"quantity\":3}"))
                .willReturn(okJson(
                    "{\"reservationId\":\"RES-BOOT\","
                    + "\"state\":\"ACCEPTED\"}")));

        StepVerifier.create(gateway.reserve(
                    new PartnerGateway.ReserveRequest(
                            "BOOT-1", 3),
                    "boot-request"))
                .assertNext(receipt ->
                    assertEquals("RES-BOOT",
                            receipt.reservationId()))
                .verifyComplete();

        SERVER.verify(1, postRequestedFor(
                urlEqualTo("/api/v1/reservations"))
                .withRequestBody(equalToJson(
                    "{\"sku\":\"BOOT-1\",\"quantity\":3}")));
    }
}
~~~

### Vì sao test này là full-context test, không phải test controller?

- `@SpringBootTest(webEnvironment=NONE)` nạp Spring Boot application beans nhưng không cần mở HTTP server inbound.
- `PartnerGateway` thật được Spring tạo bằng **`WebClient.Builder` do Boot cung cấp**.
- `@DynamicPropertySource` đăng ký `partner.base-url` trỏ local stub trước khi bean sử dụng nó.
- WireMock vẫn nhận **outbound HTTP** qua socket; nó không giả lập server của chính ứng dụng.
- `@DirtiesContext(AFTER_CLASS)` tránh một context được tái sử dụng sau khi local server đã dừng.
- `SERVER.resetAll()` reset mapping và request journal trước từng method, bảo đảm độc lập nếu chúng chạy tuần tự.
- Static server được start trong class initialization để bảo đảm URL đã có khi Spring khởi tạo bean. Đây là lựa chọn dành riêng demo; các dự án lớn có thể dùng `WireMockExtension`/framework integration phù hợp.

### Nếu có global WebClient filters thì sao?

Trong ứng dụng thật, một `WebClientCustomizer` có thể thêm OAuth Bearer token, trace header, logging filter hoặc custom codec. Test plain `WebClient.builder()` **không tự có** những tùy biến đó. Full-context test dùng injected builder và có thể thêm matcher cho header do customizer tạo:

~~~java
SERVER.stubFor(get(urlPathEqualTo("/protected"))
        .withHeader("X-Trace-Id", matching(".+"))
        .willReturn(okJson("{\"ok\":true}")));
~~~

Đây là snippet mở rộng; production phải thật sự cấu hình header trên WebClient builder thì matcher mới pass. Không đưa token thật vào WireMock mappings/logs.

## 9. Tổng hợp test cases và kết quả dự kiến

Bộ project cung cấp **10 JUnit `@Test` methods**:

| Class | Test | Điều bảo vệ |
| --- | --- | --- |
| `PartnerGatewayTransportTest` | `getSendsCorrectMethodPathQueryAndHeaders` | GET, path, query, header, response DTO |
| `PartnerGatewayTransportTest` | `queryParameterIsEncodedAndNotSplitByAmpersand` | URI encoding ký tự `&` và space |
| `PartnerGatewayTransportTest` | `postSerializesJsonAndCorrelationHeader` | POST, JSON body, Content-Type, request ID |
| `PartnerGatewayTransportTest` | `notFoundMapsHttp404ToDomainError` | 404 → domain exception |
| `PartnerGatewayTransportTest` | `serviceUnavailableRetainsHttpStatus` | 503 → WebClientResponseException |
| `PartnerGatewayTransportTest` | `noContentDoesNotBecomeFakeProduct` | 204 → error khi contract yêu cầu body |
| `PartnerGatewayTransportTest` | `slowResponseCausesReactivePublisherTimeout` | Reactor publisher timeout |
| `PartnerGatewayTransportTest` | `monoIsColdAndSendsNoRequestBeforeSubscription` | Reactive cold publisher và request count |
| `PartnerGatewayBootWiringTest` | `bootConfiguredClientCallsLocalStub` | Spring injected WebClient.Builder + base URL |
| `PartnerGatewayBootWiringTest` | `bootConfiguredClientSerializesPostBody` | Spring full wiring gửi JSON POST thật |

### Chạy project

Máy cần JDK 17, Gradle Wrapper tương thích và internet để lấy Maven dependencies lần đầu. **Không cần Docker**.

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng một lớp:

~~~bash
./gradlew test --tests 'com.example.transport.PartnerGatewayTransportTest'
./gradlew test --tests 'com.example.transport.PartnerGatewayBootWiringTest'
~~~

Báo cáo thường có ở:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.transport.PartnerGatewayTransportTest.xml
    └── TEST-com.example.transport.PartnerGatewayBootWiringTest.xml
~~~

Kỳ vọng **10 tests pass** khi code và môi trường tương thích. Đây là **dự kiến dựa trên source**, không phải tuyên bố đã chạy Gradle tại máy người đọc. Không có `System.out.println` trong test, nên không có stdout nghiệp vụ cố định. Gradle có thể báo `BUILD SUCCESSFUL`, hoặc dùng cache `UP-TO-DATE/FROM-CACHE`.

Để buộc chạy lại khi chẩn đoán lỗi transport:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu chưa có Wrapper mà đã có Gradle tương thích:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó commit scripts/JAR theo policy repository. Không tự nâng dependency của project thật chỉ vì tutorial dùng một bản Boot khác.

### Kết quả assertions không phụ thuộc cổng WireMock

Không assert `server.port() == 8080`. WireMock chọn port hiện thời; chính `server.baseUrl()` cấp cho client. Test chỉ quan tâm client có đến được server hiện tại và server xác minh request đúng.

## 10. Request matching: tránh test “xanh giả”

WireMock hỗ trợ nhiều matcher. Chọn loại tương ứng với API contract:

### `urlEqualTo` và `urlPathEqualTo`

~~~java
get(urlEqualTo("/api/v1/products/BK-001?include=stock"))
~~~

matcher trên URL gồm query string (có thể nhạy với thứ tự/ký tự encode).

~~~java
get(urlPathEqualTo("/api/v1/products/BK-001"))
    .withQueryParam("include", equalTo("stock"))
~~~

matcher path và query riêng, thường dễ bảo trì hơn khi có nhiều query params và không muốn phụ thuộc thứ tự chúng xuất hiện.

### `withHeader`

~~~java
withHeader("Accept", containing("application/json"))
~~~

Kiểm header **đã thực sự đến stub server**. `Content-Type` thường có thể kèm charset, vì thế `containing("application/json")` có thể phù hợp hơn `equalTo("application/json")` nếu contract cho phép suffix. Nếu header có giá trị phải khớp chính xác (chẳng hạn một application-specific ID), dùng `equalTo` sẽ phát hiện sai lệch.

### JSON: structural matching

~~~java
withRequestBody(equalToJson(
        "{\"sku\":\"BK-001\",\"quantity\":2}"))
~~~

JSON object không cần trùng thứ tự keys, nhưng các field/value cần đúng theo matcher. Khi contract chỉ yêu cầu một vài fields và cho phép mở rộng payload, có thể dùng `matchingJsonPath` có chủ đích; tránh làm test quá lỏng đến mức misspelled field không bị bắt.

### Request count và retry

~~~java
server.verify(1, postRequestedFor(
        urlEqualTo("/api/v1/reservations")));
~~~

Một hành động đặt hàng thông thường không nên tự động gửi hai POST trừ khi API có idempotency key và retry policy đúng. Verify count giúp bắt double subscription hoặc retry ngoài ý muốn. Khi retry được thiết kế, expected count có thể là 2/3, nhưng phải thử **chuỗi phản hồi** (503 trước, 200 sau) và kiểm business idempotency.

### Unmatched requests

Khi request không match một stub nào, WireMock thường trả **404 mặc định** và ghi thông tin unmatched vào request journal; với một số JUnit extension configurations, unmatched requests cũng có thể được báo fail. Nếu client có custom mapping 404, lỗi gốc “sai URL/header” có thể bị che thành “product not found”.

Khi test fail, xem:

1. Stub matcher định nghĩa gì?
2. Request thực tế có method/path/query/header/body nào?
3. Query có bị encode thành một param khác không?
4. Có missing Accept/Content-Type hoặc header sai case/value không?
5. Client có gọi nhầm hostname/port/API version không?
6. WireMock có lưu request journal của test trước không?
7. Có default 404 vì **unmatched** thay vì do scenario cố ý stub 404 không?

Điểm thực hành: **Với một bài test mong 404 nghiệp vụ, vẫn verify request đã match đúng stub path.**

## 11. HTTP response status: 2xx/4xx/5xx và body rỗng

### 2xx thành công

`retrieve().bodyToMono(Product.class)` decode JSON body thành `Product`. Nếu HTTP status 200 nhưng body không phải JSON hợp lệ, decoder có thể fail; đó là **decode error**, không phải HTTP status failure. JSON test fixture nên có field types/range tương ứng contract (ví dụ `priceCents` là số nguyên).

### 204 No Content

Một HTTP 204 thường không có response body. Nếu nghiệp vụ yêu cầu một `Product`, default `bodyToMono(Product.class)` có thể kết thúc empty. Demo có `switchIfEmpty(Mono.error(...))` để biến nó thành lỗi contract rõ ràng. Nhưng không nên áp dụng quy tắc này cho mọi API: với DELETE thành công trả 204, `Mono<Void>` completion là kết quả hợp lý.

### 404 Not Found

`retrieve()` mặc định tạo `WebClientResponseException` cho 4xx/5xx. Demo dùng `onStatus` **chỉ đối với 404** để map sang `ProductNotFoundException`. Status khác như 503 vẫn đi qua behavior mặc định.

Để kiểm business logic của exception, test phải assert **type** và message/cause phù hợp; đừng assert một broad `RuntimeException.class` vì lỗi decode/connection cũng thỏa điều kiện ấy.

### 503 Service Unavailable

HTTP 503 có response, headers và status code. Không nhầm với connection refused hoặc DNS failure, vì các lỗi transport **không có HTTP 503** để kiểm.

Nếu ứng dụng có retry/backoff, chỉ nên retry **những lỗi transient đã được phân loại**. Đối với POST tạo reservation, cần idempotency key và hợp đồng provider: một timeout sau khi server đã xử lý request có thể khiến retry tạo reservation trùng.

## 12. Delay, timeouts, cancellation và lỗi socket

HTTP stub server có thể tạo delay có kiểm soát:

~~~java
server.stubFor(get(urlEqualTo("/slow"))
        .willReturn(aResponse()
            .withFixedDelay(1500)
            .withStatus(200)
            .withBody("OK")));
~~~

Có nhiều dạng timeout:

| Timeout | Tầng xử lý | Ý nghĩa |
| --- | --- | --- |
| `Mono.timeout(Duration)` | Reactor operator | Publisher không phát signal đúng hạn |
| Connect timeout | HTTP connector/TCP | Không thiết lập được connection kịp |
| Response timeout | HTTP connector/runtime | Server không trả response trong thời gian giới hạn |
| Read timeout | Socket/network/connector | Chờ dữ liệu quá lâu trong quá trình đọc |
| Pool acquire timeout | Connection pool | Không lấy được connection kịp |
| Business deadline | Service/application | Tổng thời gian nhiều lần gọi/retry vượt SLA |

Test `slowResponseCausesReactivePublisherTimeout` **chỉ kiểm Reactor timeout**. Muốn test Netty `responseTimeout`, cần cấu hình `HttpClient.responseTimeout` trên `ReactorClientHttpConnector` và dùng delay trong stub server. Khi assert exception, thường kiểm **nhóm transport exception/root cause** hơn là hardcode một message của Netty dễ thay đổi theo version.

### Cấu hình Reactor Netty response timeout (snippet mở rộng)

~~~java
HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofMillis(400));

WebClient client = WebClient.builder()
        .clientConnector(
            new ReactorClientHttpConnector(httpClient))
        .baseUrl(stubBaseUrl)
        .build();
~~~

Snippet cần imports `reactor.netty.http.client.HttpClient`, `ReactorClientHttpConnector` và `WebClient`, và một stub server URL thật. Nó **thay connector bằng một connector mới**, nên trong app thực cần giữ hoặc tích hợp những SSL, proxy, observability, connection pool settings và customizers đã có nếu chúng thuộc production contract.

### Connection reset và malformed response

WireMock có fault injection (ví dụ `Fault.CONNECTION_RESET_BY_PEER` tùy server/HTTP runtime). Đây là snippet lý thuyết:

~~~java
server.stubFor(get(urlEqualTo("/broken"))
        .willReturn(aResponse()
                .withFault(Fault.CONNECTION_RESET_BY_PEER)));
~~~

Khi connection bị cắt, WebClient có thể ném transport exception **không có HTTP status**. Cần kiểm phù hợp connector/OS và tránh khẳng định mọi platform tạo cùng exact exception class/message.

### Không dùng `Thread.sleep` vô căn cứ

`Thread.sleep(500)` trong test để “chờ request” dễ flake vì CI scheduling và CPU không ổn định. Dùng `StepVerifier`, server request journal, latch hoặc cơ chế await có timeout có giới hạn. Với Reactor logic thuần không qua HTTP, `StepVerifier.withVirtualTime` hữu ích; nhưng **virtual time không giả lập network socket**.

## 13. Retry và idempotency khi có stub server

Nhiều lỗi HTTP client xảy ra ở retry policy:

- Gặp 503, client retry quá nhiều làm tăng tải provider.
- Gặp 404, client retry vô ích.
- POST bị timeout sau khi server đã lưu dữ liệu, retry tạo duplicate.
- Không tôn trọng `Retry-After`/rate limit.
- Không propagate correlation/idempotency key qua các attempts.
- Unit mock chỉ trả final 200 nên không thấy số request thật.

Một test retry có ý nghĩa cần:

1. Stub lần gọi đầu trả 503.
2. Stub lần tiếp theo trả 200 (WireMock **scenarios** hoặc response templating/state).
3. Gọi client thật.
4. Assert final DTO và số request chính xác.
5. Kiểm header idempotency/correlation được giữ ở mỗi attempt.
6. Assert retry chỉ áp dụng cho mã/exception được phân loại.
7. Kiểm bound (max retries, backoff, jitter) và tổng deadline.

**Không thêm retry một cách vô điều kiện vào production adapter chỉ để test có thêm trường hợp.** Demo giữ client đơn giản, không tự retry; việc verify `1` giúp phát hiện double request ngoài ý muốn. Một hệ thống cần retry phải có contract rõ, đặc biệt với operations thay đổi trạng thái.

### Một ví dụ chính sách ở mức ý tưởng

~~~java
mono.retryWhen(
    Retry.backoff(2, Duration.ofMillis(200))
         .filter(error -> isTransient(error)));
~~~

Đây là snippet lý thuyết; cần `Retry` import, `mono` và predicate `isTransient` do ứng dụng định nghĩa. Không copy và chạy độc lập. Với `WebClientResponseException`, có thể lọc theo status 502/503/504/429 tùy hợp đồng. Với network errors, phải phân biệt lỗi có thể retry an toàn hay không.

## 14. Cách xác minh HTTPS/TLS và proxy khi chúng là hợp đồng

Trong nhiều bài, HTTP loopback đủ để kiểm method/URI/body/status. Nhưng nếu production client cần:

- Mutual TLS (client certificate).
- Custom truststore/CA, certificate pinning.
- HTTP proxy có authentication.
- SNI và hostname verification.
- HTTP/2 ALPN.
- Custom connection pool, TLS renegotiation, keep-alive hoặc redirects.

thì **HTTP stub server không TLS** không chứng minh các cấu hình đó. Bạn cần một **HTTPS stub** với certificates dành cho test, client SSL configuration tương ứng và assertions chứng minh handshake thành công/thất bại đúng khi cấu hình sai.

WireMock hỗ trợ HTTPS dynamic port. Có thể dùng:

~~~java
new WireMockServer(
    wireMockConfig()
        .dynamicHttpsPort()
        .httpDisabled(true));
~~~

Đây là snippet cấu hình nâng cao, không thuộc demo runnable và có thể cần truststore/key configuration. Không vô hiệu hóa certificate validation trong production để làm test xanh; điều đó làm mất chính thuộc tính TLS cần kiểm.

### Redirects

Một HTTP stub có thể trả `301/302/307/308` với `Location`. Client runtime có tự follow redirects hay không tùy connector/config. Test phải kiểm **số request, method/body preservation, host whitelist và sensitive header handling**. Đặc biệt không gửi `Authorization` sang một redirect host không được tin cậy.

### Proxy

Nếu app dùng corporate proxy, WireMock trên localhost có thể đi đường bypass và không chứng minh proxy config. Để test proxy cần cấu hình test proxy riêng, không dùng credentials production.

## 15. Phân biệt outbound client test và inbound WebTestClient

Hai tên dễ nhầm:

- **`WebClient`**: HTTP **client** để ứng dụng gọi REST API bên ngoài.
- **`WebTestClient`**: test client cho WebFlux/web application endpoint; có thể bind trực tiếp vào controller/application context hoặc chạy với server thật.

Khi kiểm outbound call:

~~~text
Application's WebClient -> external HTTP stub
~~~

Khi kiểm inbound controller:

~~~text
WebTestClient -> application's WebFlux controller
~~~

Nếu bạn dùng `@WebFluxTest` và `WebTestClient.bindToApplicationContext(...)`, test có thể không mở socket inbound. Nó có thể kiểm mapping/validation tốt nhưng không tự xác minh **WebClient gửi request qua transport đến provider**.

Nếu cần kiểm cả hai chiều, dùng integration test gồm app HTTP server ở `RANDOM_PORT` và external WireMock stub, rồi gửi request HTTP vào app; xác nhận app gọi stub. Đó là **end-to-end qua hai HTTP hops**, chậm hơn và đòi cleanup/port management nhiều hơn demo này.

## 16. Cách cấu hình base URL đúng trong Spring Boot

Trong application thực, không hardcode partner URL trong adapter. Dùng configuration properties hoặc `@Value` với một key rõ ràng:

~~~properties
partner.base-url=https://api.partner.example
~~~

Đây là minh họa production settings. Trong integration tests, giá trị được **override sang local stub**:

~~~java
@DynamicPropertySource
static void partnerUrl(DynamicPropertyRegistry registry) {
    registry.add("partner.base-url", SERVER::baseUrl);
}
~~~

Lợi ích:

- Test không cần biết trước cổng stub.
- Không cần `System.setProperty` toàn JVM.
- Không phải sửa production source chỉ để gọi mock.
- Bean `PartnerGateway` vẫn sử dụng cùng constructor/config wiring.
- Có thể fail sớm nếu thiếu base URL thay vì vô tình gọi một server khác.

**Không trộn nhiều nguồn URL cho cùng client mà không biết precedence**, ví dụ vừa có `@Value("${partner.base-url}")` vừa có custom `WebClientCustomizer` hardcode base URL khác. Khi test only mock collaborator, lỗi precedence này có thể không bị phát hiện; full-context test với actual HTTP stub sẽ giúp bắt.

### Khi dùng `@TestPropertySource`

Nếu stub luôn ở một fixed address và bạn kiểm soát port, có thể override bằng `@TestPropertySource(properties=...)`. Nhưng dynamic port từ WireMock khiến `@DynamicPropertySource` là lựa chọn sạch hơn.

### Khi dùng JUnit `@RegisterExtension`

WireMock 3 có `WireMockExtension` cho JUnit Jupiter:

~~~java
@RegisterExtension
static WireMockExtension wiremock =
    WireMockExtension.newInstance()
        .options(wireMockConfig().dynamicPort())
        .build();
~~~

Đây là snippet minh họa; cần imports. Extension quản lý start/stop/reset, có thể gọi `wiremock.stubFor(...)` và `wiremock.port()`. Nó giúp tránh manual lifecycle, nhưng khi dùng với Spring cached context cần đồng bộ thời điểm container/server còn sống và context được tái sử dụng. Trong project runnable, phần JUnit thuần dùng manual per-test server, còn phần full context dùng static server được start sớm và `@DirtiesContext` để minh họa rõ hơn boundaries.

## 17. Isolation và parallel tests

Một HTTP stub test dễ rò state theo cách ít thấy:

- Mapping từ test trước vẫn tồn tại.
- WireMock request journal còn request cũ; `verify(1)` có thể fail vì thành 2.
- Hai test classes cùng dùng port 8080.
- Static server dừng nhưng Spring `ApplicationContext` cache vẫn giữ WebClient có base URL cũ.
- Một test gọi `server.resetAll()` trong lúc test khác đang gọi server nếu chạy song song.
- Một test dùng response scenario stateful nhưng không reset state trước method.
- Client retry background còn chạy sau khi test kết thúc, request vào server đã stop.

Biện pháp:

1. **Random port** cho mỗi server instance.
2. Isolate server theo test method hoặc class có lifecycle rõ.
3. `resetAll()` stubs/request journal trước từng test khi dùng chung server.
4. Khi parallel tests share server, tránh reset giữa chừng; dùng server riêng hoặc resource lock.
5. Không reuse Spring context với local server đã stop; `@DirtiesContext` hoặc chia lifetime thống nhất.
6. Mọi reactive pipeline được subscribe và kiểm kết thúc/timeout rõ trước teardown.
7. Không rely vào test method ordering; fixture phải độc lập.
8. Không dùng default real partner URL làm fallback trong test.
9. Hạn chế logging body chứa token, user PII hoặc data nhạy cảm.
10. Nếu test dùng file-based WireMock mappings, kiểm chúng thuộc đúng resource directory và tránh loading mappings từ module khác.

Một test có thể chạy xanh **một mình** nhưng fail **cả suite** vì request journal hoặc cache — đó là dấu hiệu isolation/lifecycle, không phải lý do để thêm `Thread.sleep`.

## 18. Đọc lỗi và xử lý đúng lớp

| Triệu chứng | Nguyên nhân có thể | Hướng chẩn đoán |
| --- | --- | --- |
| `Connection refused` | WireMock chưa start hoặc base URL sai port | Start server trước client call, dùng `server.baseUrl()` |
| `404` ngoài dự kiến | Unmatched stub do path/query/header sai | Xem request journal và matcher |
| ProductNotFoundException trong test success | Request bị unmatched, WireMock trả 404 | Verify request URL/path/query chính xác |
| `JsonParseException`/`DecodingException` | Response body/header không đúng JSON | Dùng `okJson` và schema DTO phù hợp |
| `UnsupportedMediaTypeException` | `Content-Type` không phù hợp codec | Stub header đúng contract |
| POST matcher không tìm thấy | Client body field/order/media type sai | Xem recorded body, dùng `equalToJson` |
| `StepVerifier` never completes | Mono không được subscribe, server delay/timeout | Kiểm cold publisher, timeout và lifecycle |
| Verify expected 1 nhưng found 0 | Client chưa subscribe hoặc gọi URL khác | StepVerifier trước verify, xem journal |
| Verify expected 1 nhưng found 2 | Retry/double subscription/request cũ | Reset server, kiểm retry policy |
| Timeout nhưng HTTP status không có | Đây là transport/publisher error | Không assert status code cho lỗi socket |
| 503 bị map thành ProductNotFoundException | `onStatus` predicate quá rộng | Chỉ map 404, giữ status khác |
| 204 được xem như DTO null | Không xử lý empty `Mono` | `switchIfEmpty` theo contract |
| WebFlux test context thiếu PartnerGateway | `@WebFluxTest` là slice controller | Dùng full-context hoặc import đúng bean |
| Boot client không dùng custom header/filter | Dựng `WebClient.builder()` ngoài Boot | Inject Boot `WebClient.Builder`, dùng full-context test |
| Parallel CI lỗi bind port | Port hardcode 8080 | Dynamic port |
| HTTPS handshake fail | Truststore/SNI/cert không phù hợp | Dùng HTTPS stub + test CA |
| Proxy redirect làm lộ header | Client follow redirect khác host | Test header forwarding và whitelist |
| Test chạy đơn lẻ xanh, suite đỏ | Server reset/context cache/static state | Cô lập lifecycle/reset/`@DirtiesContext` có mục đích |
| WireMock class/version conflict | Trộn WireMock 2/3/4 hoặc Jetty deps | Kiểm Gradle dependency tree; dùng version tương thích |
| Test quá chậm | Start server theo mỗi method quá nhiều | Dùng class-scoped server + reset khi an toàn |
| WebClient request ghi log token thật | Debug logging quá rộng | Dùng fake credentials/sanitize, disable sensitive logs |
| Không gọi HTTP nhưng test vẫn xanh | WebClient hoặc gateway đã bị Mockito mock | Dùng real WebClient + server.verify(...) |

### Quy trình debug tối ưu

1. **Xác minh loại test:** mock collaborator, fake ExchangeFunction hay HTTP stub thật?
2. **Xác minh lifecycle:** server đã start? có đang nghe cổng nào? client base URL là gì?
3. **Xác minh đường truyền:** request thực có đến server không?
4. **Xem request journal**: method/path/query/headers/body, không chỉ exception của WebClient.
5. **Kiểm stub matcher:** sai ở đâu, query encoding hay Content-Type?
6. **Kiểm response**: status, headers, content type, valid JSON và delay/fault.
7. **Kiểm WebClient error handling**: `retrieve`, `onStatus`, `exchangeToMono`, decode.
8. **Kiểm reactive subscription**: `Mono` chỉ dựng chưa chạy; StepVerifier/block có được gọi?
9. **Kiểm timeout/retry** và số lần request. Timeout operator khác socket timeout.
10. **Kiểm Boot wiring/context cache** nếu plain test pass nhưng full-context fail.
11. **Kiểm parallel suite**: static server, resetAll và shared states.
12. **Không nới matcher cho xanh** trước khi hiểu API contract đúng.

## 19. Những mở rộng đáng học sau bài

### Request body lớn, streaming và backpressure

JSON body nhỏ và một response nhỏ không chứng minh được multipart upload, streaming `Flux<DataBuffer>`, chunked transfer encoding, SSE hoặc backpressure khi consumer chậm. Khi contract thuộc nhóm này, dùng stub hỗ trợ streaming/chunked, đo cancellation và resource release. Một test chỉ gọi `bodyToMono(String.class)` không đủ.

### Binary payload

Nếu WebClient gửi file hoặc đọc image/PDF, test cần kiểm bytes/hash, content length, content disposition, boundary multipart và codec tương ứng, không chỉ string JSON. WireMock có thể trả `byte[]` body. Tránh convert binary thành String rồi so sánh vì encoding có thể thay đổi dữ liệu.

### Redirect và cookie jar

WebClient/Netty connector có redirect policy và cookie handling khác trình duyệt. Test redirect, cookie, Set-Cookie và forbidden header forwarding khi ứng dụng phụ thuộc chúng.

### OAuth/OIDC

Nếu WebClient dùng OAuth2 client credentials, cần kiểm token request/client filter cùng resource request hoặc stub token endpoint tách biệt. Không hardcode token production; fake token và verify header forwarding trong test. Đừng mock token service rồi tuyên bố đã kiểm TLS trust/transport.

### Observability

HTTP client thường có trace/span và Micrometer metrics. Test có thể kiểm header correlation/trace được truyền tới stub và metrics recorded, nhưng đừng assert trace ID ngẫu nhiên là một chuỗi cố định. Nếu tracing không thuộc contract, không khiến mỗi test phụ thuộc một telemetry backend ngoài.

## 20. Bài tập tự luyện

**Bài A — đổi HTTP method:** Tạm đổi `getProduct` từ `get()` sang `post()` và chạy test GET. Vì WireMock matcher yêu cầu GET, test phải fail. Hoàn nguyên.

**Bài B — xóa query:** Bỏ `queryParam("include","stock")`. Matcher và verify phải bắt lỗi. Giải thích vì sao chỉ assert DTO không đủ.

**Bài C — URI encoding:** Thay `searchOne("Java & Spring")` bằng nối string trực tiếp `"?q=" + term` trong nhánh thử nghiệm. Quan sát request journal và kiểm matcher mất khả năng nhận đúng q value. Hoàn nguyên.

**Bài D — header:** Xóa `defaultHeader("X-Client-Name",...)` và chạy GET test. Test phải fail ở matcher/verify.

**Bài E — JSON body:** Đổi field `quantity` thành tên `qty` trong DTO hoặc thêm converter làm sai serialization. POST test `equalToJson` phải phát hiện khác biệt.

**Bài F — 404 vs 503:** Sửa predicate `onStatus` thành match mọi 4xx/5xx. Test 503 phải fail vì sai domain exception; hoàn nguyên 404-only mapping.

**Bài G — 204 No Content:** Bỏ `switchIfEmpty` và chạy test 204. Giải thích vì sao publisher hoàn thành empty, và tại sao contract của GET product không nên coi đó là thành công nếu yêu cầu body.

**Bài H — cold Mono:** Bỏ `StepVerifier.create(result)` nhưng vẫn verify request count. Vì chưa subscribe, không có request. Giải thích khác biệt giữa dựng publisher và chạy publisher.

**Bài I — timeout:** Thay `Mono.timeout` bằng Reactor Netty `responseTimeout` trong một test riêng. Stub delay vẫn > timeout. Kiểm exception category/root cause mà không hardcode connector message.

**Bài J — retry 503:** Thêm retry có giới hạn cho GET idempotent, dùng WireMock scenario trả 503 rồi 200. Assert final DTO và đúng hai requests. Không áp dụng retry mù cho POST.

**Bài K — Boot customizer:** Tạo một `WebClientCustomizer` gắn header `X-App-Trace` rồi kiểm bằng full-context test. Test plain builder không nhất thiết có header đó; lý giải sự khác nhau.

**Bài L — WireMock extension:** Thay manual server per method bằng `@RegisterExtension static WireMockExtension`. Kiểm reset trước mỗi test và server lifetime khi Spring context caching.

**Bài M — HTTPS:** Chạy WireMock HTTPS dynamic port, tạo CA/cert dành riêng test và cấu hình client truststore. Chứng minh handshake thành công; một test cố ý sai CA phải fail. Không disable TLS verify.

**Bài N — lỗi socket:** Dùng `Fault.CONNECTION_RESET_BY_PEER` để tạo lỗi transport. Assert không có HTTP status vì kết nối bị ngắt trước khi response được xử lý.

**Bài O — contract versioning:** Thay đổi JSON field `priceCents` thành `amountCents` trong stub. Giữ DTO cũ và quan sát decode/default behavior. Thêm validation nếu thiếu field là lỗi nghiệp vụ.

**Bài P — parallel:** Cho hai test classes dùng một WireMockServer class-scoped, bật parallel. Quan sát vấn đề `resetAll()` khi tests cùng chạy; chuyển sang isolated server hoặc resource lock.

## 21. Checklist trước khi merge HTTP client integration tests

- [ ] Test dùng **WebClient thật** và stub server thật khi mục tiêu là transport?
- [ ] Không nhầm outbound `WebClient` với inbound `WebTestClient`?
- [ ] Stub server chạy local/random port, client base URL từ server instance?
- [ ] Không có production/fallback URL hoặc credentials thật trong test?
- [ ] Có xác minh HTTP method/path/query/headers mà stub **thực nhận**?
- [ ] URI variable/query encoding được test bằng ký tự phản ví dụ như space/`&`?
- [ ] POST JSON kiểm cả Content-Type, body và response DTO?
- [ ] Request count được xác minh khi retry/double subscription là rủi ro?
- [ ] 2xx, 404, 5xx và 204 được kiểm theo hợp đồng?
- [ ] Không đánh đồng HTTP status error với connection/transport exception?
- [ ] Timeout test biết rõ **tầng timeout** đang kiểm?
- [ ] Không dùng `Thread.sleep` để thay reactive completion?
- [ ] WireMock mapping/request journal được reset giữa các tests khi share server?
- [ ] Container/server lifecycle khớp Spring context cache và parallel tests?
- [ ] Nếu dùng global Boot WebClient customization, có full-context test với builder được inject?
- [ ] Khi cần TLS/proxy/HTTP2, có test transport đúng protocol thay vì HTTP stub trơn?
- [ ] Không disable certificate validation chỉ để có test xanh?
- [ ] Retry/backoff có max attempts/deadline và idempotency contract?
- [ ] Test data/headers không làm lộ tokens, PII hoặc secrets trong logs?
- [ ] CI không cần third-party API thật để chạy repeatably?
- [ ] Test verify cả outbound request và inbound response, không chỉ non-null DTO?
- [ ] Trước khi merge, đã đọc test report và bảo đảm test thật sự thực thi?

## 22. Tài liệu tham khảo

- [Spring Framework — Testing WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): khuyến nghị dùng mock web server thực như WireMock/OkHttp MockWebServer khi kiểm network client.
- [Spring Boot 3.3 — Calling REST Services](https://docs.spring.io/spring-boot/3.3/reference/io/rest-client.html): injected `WebClient.Builder`, connector/runtime và customizers.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): request building, `retrieve`/`exchangeToMono`, filters, status handling.
- [Spring Framework 6.1 — WebClient.RequestHeadersSpec](https://docs.spring.io/spring-framework/docs/6.1.17/javadoc-api/org/springframework/web/reactive/function/client/WebClient.RequestHeadersSpec.html): default 4xx/5xx behavior và `onStatus`.
- [WireMock — Stubbing](https://wiremock.org/docs/stubbing/): request matching và response configuration.
- [WireMock — Request Matching](https://wiremock.org/docs/request-matching/): path/query/header/body matchers.
- [WireMock — Verifying](https://wiremock.org/docs/verifying/): request journal và exact request counts.
- [WireMock — JUnit Jupiter](https://wiremock.org/docs/junit-jupiter/): `WireMockExtension`, random port, reset lifecycle.
- [WireMock — Configuration](https://wiremock.org/docs/configuration/): `dynamicPort`, HTTPS/faults và server options.
- [WireMock — Installation](https://wiremock.org/docs/download-and-installation/): WireMock 3.x standalone Java dependency.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, publisher signaling và virtual time.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slice, context.

**Ghi nhớ:** Khi cần chứng minh **HTTP client phát đúng request qua transport**, hãy dùng `WebClient` thật kết nối một **WireMock/MockWebServer local**. Stub request phải match **method/path/query/headers/body**, rồi test phải assert cả **response/error và số lần HTTP request thực**. Với Spring Boot filters/codecs/properties, thêm một full-context test dùng **injected WebClient.Builder**. Phân biệt đúng status error, decode error, timeout operator và socket fault; quản lý lifecycle để bài test chạy tin cậy trên CI.
