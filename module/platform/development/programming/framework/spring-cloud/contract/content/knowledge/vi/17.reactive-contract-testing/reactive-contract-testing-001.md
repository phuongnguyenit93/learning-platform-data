# Phân biệt hợp đồng HTTP với cách triển khai reactive

Khi một dịch vụ chuyển từ **Spring MVC** sang **Spring WebFlux**, mã controller có thể đổi từ kiểu trả về `OrderView` sang `Mono<OrderView>` hoặc `Flux<OrderEvent>`. Nhưng consumer thường **không gọi phương thức Java của controller**: consumer gửi **HTTP request** và quan sát **status, headers, body, lỗi và cách kết nối kết thúc**. Vì vậy, phải phân biệt **hợp đồng HTTP** với **mô hình lập trình reactive** bên trong producer.

Bài thuộc chương **Kiểm thử reactive** của mô-đun **SPRING_CLOUD_CONTRACT**. Spring Cloud Contract cho phép đặc tả tương tác HTTP hoặc thông điệp bằng **Groovy/YAML DSL**, sinh kiểm thử xác minh **producer**, đóng gói **stub**, rồi dùng **Stub Runner** trong kiểm thử **consumer** và CI để phát hiện thay đổi API không tương thích. Trọng tâm là giữ **cam kết HTTP ổn định** khi triển khai đổi sang WebFlux/Reactor, sử dụng **WebTestClient** để xác minh producer và biết giới hạn của hợp đồng HTTP thông thường khi gặp streaming, backpressure hoặc timeout.

## 1. Hợp đồng mô tả kết quả có thể quan sát được

Ví dụ **Order Service** cung cấp API cho **Billing Service**:

~~~http
GET /api/orders/42
Accept: application/json
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":42,"status":"PAID"}
~~~

Hợp đồng xác định **request nào được chấp nhận** và **response nào phải trả về**; còn cách Order Service truy vấn dữ liệu, quản lý thread và điều phối bất đồng bộ là trách nhiệm triển khai.

| Yếu tố | Thuộc hợp đồng HTTP? | Ví dụ |
| --- | --- | --- |
| Method, path, query, request headers/body | **Có** | `GET /api/orders/42`, header `Accept`. |
| Response status, headers, JSON và giá trị quan trọng | **Có** | `200`, `application/json`, `status=PAID`. |
| Lỗi tài nguyên không tồn tại, thiếu xác thực, không đủ quyền | **Có nếu đã cam kết** | `404`, `401`, `403` và payload lỗi. |
| Media type, cách đóng gói dữ liệu | **Có** | JSON array, SSE hoặc NDJSON. |
| Trả `Mono`, `Flux` hay một object Java đồng bộ | **Không** | Chữ ký method nội bộ của controller. |
| Dùng JPA, R2DBC, WebClient hay JDBC | **Không** | Công nghệ lưu trữ/gọi dịch vụ khác. |
| Sử dụng `subscribeOn`, `publishOn`, scheduler nào | **Không** | Chính sách thực thi Reactor. |
| Có blocking call, giới hạn thread, backpressure nội bộ | **Không tự động** | Cần kiểm kiến trúc và hiệu năng riêng. |

**Không đặt kiểu `Mono` hoặc `Flux` vào body của một HTTP contract bình thường.** Đây không phải giá trị được truyền trên dây. Consumer có thể viết bằng Java, JavaScript, Go, hoặc vẫn dùng Spring MVC; nó chỉ cần giao thức HTTP đã thống nhất.

## 2. So sánh controller đồng bộ và controller reactive

### 2.1. Spring MVC

~~~java
@RestController
@RequestMapping("/api/orders")
class MvcOrderController {

    @GetMapping("/{id}")
    ResponseEntity<OrderView> getOrder(@PathVariable long id) {
        if (id == 42L) {
            return ResponseEntity.ok(new OrderView(42L, "PAID"));
        }
        return ResponseEntity.notFound().build();
    }
}

record OrderView(long id, String status) {}
~~~

Trong ví dụ MVC, handler tính trực tiếp một `ResponseEntity<OrderView>`; Spring chuyển kết quả thành HTTP response.

### 2.2. Spring WebFlux

~~~java
@RestController
@RequestMapping("/api/orders")
class ReactiveOrderController {
    private final OrderLookup orders;

    ReactiveOrderController(OrderLookup orders) {
        this.orders = orders;
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderView>> getOrder(@PathVariable long id) {
        ResponseEntity<OrderView> notFound =
                ResponseEntity.notFound().build();

        return orders.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(notFound);
    }
}

record OrderView(long id, String status) {}

interface OrderLookup {
    Mono<OrderView> findById(long id);
}
~~~

Trong WebFlux, `findById` trả một publisher `Mono<OrderView>`, có thể phát một kết quả, kết thúc rỗng hoặc lỗi. `map` chuyển kết quả tìm thấy thành HTTP 200; `defaultIfEmpty` **chủ động** chuyển trường hợp không có đơn thành HTTP 404. Điều mà Billing quan sát được **không khác** ví dụ MVC nếu cả hai trả cùng status, headers và body.

Nếu đổi controller thành:

~~~java
@GetMapping("/{id}")
Mono<OrderView> getOrder(@PathVariable long id) {
    return orders.findById(id);
}
~~~

thì `Mono.empty()` không còn được ánh xạ tường minh thành `404`; ứng dụng có thể trả response thành công không có body, tùy cách WebFlux handler được cấu hình. **Publisher rỗng không tự động có nghĩa là “tài nguyên không tồn tại” theo HTTP.** Khi API cam kết 404, cần xử lý rõ bằng `ResponseEntity.notFound()` hoặc một `ResponseStatusException` thích hợp.

Điều này cho thấy một thay đổi rất nhỏ trong pipeline Reactor **có thể phá hợp đồng**, còn việc thay nguyên cả implementation nhưng giữ nguyên HTTP response **không nhất thiết phá hợp đồng**.

## 3. Mono và Flux không quyết định riêng HTTP semantics

| Cách triển khai | Ý nghĩa nội bộ | Điều consumer HTTP có thể quan sát |
| --- | --- | --- |
| `Mono<OrderView>` phát một item | Publisher chứa một kết quả. | Thường là một JSON object khi dùng `application/json`. |
| `Mono.empty()` | Hoàn tất mà không phát item. | Có thể là response không có body; muốn 404 cần ánh xạ. |
| `Mono.error(exception)` | Pipeline kết thúc lỗi. | HTTP status/body phụ thuộc exception handler/mapping. |
| `Flux<OrderView>` hữu hạn, `application/json` | Phát nhiều item. | Có thể được ghi thành một JSON array. |
| `Flux<?>`, `text/event-stream` | Phát sự kiện theo thời gian. | SSE streaming, kết nối có thể kéo dài. |
| `Flux<?>`, `application/x-ndjson` | Phát các record JSON liên tiếp. | Các dòng JSON độc lập, không phải JSON array. |
| `delayElements`, publisher chậm | Dữ liệu đến muộn. | Có thể làm consumer timeout; timeout không nhất thiết được hợp đồng body kiểm. |

**Cảnh báo:** một phương thức trả `Mono` chưa chắc thực hiện I/O không blocking. Ngược lại, một endpoint dùng `Flux` không mặc nhiên biến thành SSE. Media type và cấu hình encoder/response quyết định cách dữ liệu được truyền trên HTTP.

## 4. Hợp đồng Groovy DSL không cần nhắc đến Reactor

Tạo `src/test/resources/contracts/orders/get_order.groovy` trong producer:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

[
    Contract.make {
        name 'shouldReturnPaidOrder'
        description 'Đơn 42 tồn tại, trạng thái PAID'

        request {
            method 'GET'
            url '/api/orders/42'
            headers {
                header('Accept', 'application/json')
            }
        }

        response {
            status 200
            headers {
                contentType(applicationJson())
            }
            body(id: 42, status: 'PAID')
        }
    },
    Contract.make {
        name 'shouldReturn404WhenOrderMissing'
        description 'Đơn 999 không tồn tại'

        request {
            method 'GET'
            url '/api/orders/999'
            headers {
                header('Accept', 'application/json')
            }
        }

        response {
            status 404
        }
    }
]
~~~

Hai hợp đồng cùng xác minh **hành vi HTTP**:

1. `GET /api/orders/42` phải trả 200 và JSON có `id=42`, `status=PAID`.
2. `GET /api/orders/999` phải trả 404.

Việc hai tình huống nằm trong một tệp Groovy **không** biến chúng thành một phép kiểm tổng hợp: script trả về list hai `Contract.make` riêng; plugin cần nạp và sinh test cho **cả hai**.

Nếu cần kiểm body lỗi (chẳng hạn `code=ORDER_NOT_FOUND`), hãy thêm header và response body vào hợp đồng 404. Chỉ kiểm status 404 trong consumer stub test dễ tạo kết quả đạt giả khi WireMock trả 404 vì request **không khớp mapping**.

### 4.1. Hợp đồng tương đương bằng YAML

Với nhóm dùng YAML DSL, trường hợp thành công:

~~~yaml
description: Đơn 42 tồn tại, trạng thái PAID
request:
  method: GET
  url: /api/orders/42
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: 42
    status: PAID
~~~

Trường hợp không tìm thấy đặt trong file YAML khác:

~~~yaml
description: Đơn 999 không tồn tại
request:
  method: GET
  url: /api/orders/999
  headers:
    Accept: application/json
response:
  status: 404
~~~

Trong một lượt build, **chỉ giữ một bộ Groovy hoặc YAML làm nguồn hợp đồng có hiệu lực** cho cùng tình huống. Nạp đồng thời cả hai bản tương đương dễ tạo generated tests/stub mappings trùng lặp.

## 5. Chuẩn bị WebFlux producer có fixture xác định

Ví dụ project Java 17+ với `spring-boot-starter-webflux` và Spring Cloud Contract Verifier tương thích.

Ứng dụng:

~~~java
package com.acme.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Service trả dữ liệu giả để bài kiểm thử tái lập:

~~~java
package com.acme.orders;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class InMemoryOrderLookup implements OrderLookup {
    @Override
    public Mono<OrderView> findById(long id) {
        if (id == 42L) {
            return Mono.just(new OrderView(42L, "PAID"));
        }
        return Mono.empty();
    }
}
~~~

Controller WebFlux và các kiểu `OrderView`, `OrderLookup` dùng mã mục 2.2, bổ sung các imports Spring Web/ResponseEntity và Reactor tương ứng. Fixture in-memory giúp kiểm **giao tiếp HTTP**, không chứng minh R2DBC, database hay hiệu năng non-blocking thật. Với một producer thực, nên dùng repository/fixture của môi trường test, có thể kèm Testcontainers và migration.

**Chú ý dependency:** thêm cả `spring-boot-starter-web` và `spring-boot-starter-webflux` có thể khiến Spring Boot chọn ứng dụng Servlet/MVC theo mặc định. Để thực hành WebFlux, dùng stack reactive rõ ràng, tránh để test tưởng đang chạy WebFlux trong khi test context thực tế là MVC.

## 6. Chọn WEBTESTCLIENT cho Contract Verifier

Để generated producer tests gọi handler WebFlux, hãy chọn test mode tương thích. Trong Spring Cloud Contract, **`WEBTESTCLIENT`** là một lựa chọn dành cho WebFlux. Ví dụ Maven plugin:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>4.1.5</version>
    <extensions>true</extensions>
    <configuration>
        <testFramework>JUNIT5</testFramework>
        <testMode>WEBTESTCLIENT</testMode>
        <baseClassForTests>com.acme.orders.ContractTestBase</baseClassForTests>
    </configuration>
</plugin>
~~~

Đây là **đoạn cấu hình trong POM**, chưa phải một POM hoàn chỉnh. `4.1.5` là **ví dụ phiên bản dòng 4.1.x**, không phải yêu cầu dùng phiên bản đó; plugin và dependency phải khớp với Spring Boot/Spring Cloud release train của dự án.

Các dependency minh họa:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-contract-verifier</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

`JUNIT5` là **test framework** chạy generated tests; `WEBTESTCLIENT` là **chế độ thực thi request**. Hợp đồng `.groovy` vẫn có thể sinh test Java/JUnit Jupiter; không bắt buộc chuyển sang Spock/Groovy.

### 6.1. Lớp base test cho WebFlux

Một cách thiết lập tham khảo:

~~~java
package com.acme.orders;

import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest(
    classes = OrderApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
public abstract class ContractTestBase {
    @Autowired
    private ApplicationContext context;

    @BeforeEach
    void setUp() {
        RestAssuredWebTestClient.applicationContext(context);
    }
}
~~~

Lớp này khởi tạo WebFlux application context và nối Rest Assured WebTestClient tới context để generated tests có thể gọi endpoint. **API setup cụ thể phụ thuộc phiên bản Spring Cloud Contract/Rest Assured**; cần đọc generated test để đối chiếu nó thực sự dùng client nào và class base có được kế thừa không. Không sửa trực tiếp file generated test vì lần generate sau có thể ghi đè.

### 6.2. So sánh các test mode

| Test mode | Công cụ / mục tiêu | Khi dùng |
| --- | --- | --- |
| `MOCKMVC` | MockMvc kiểm Spring MVC/Servlet trong test context. | Producer Spring MVC, không phải mặc định cho WebFlux. |
| `WEBTESTCLIENT` | WebTestClient/Rest Assured WebTestClient kiểm WebFlux handler. | WebFlux producer, khi mode được release train hỗ trợ. |
| `EXPLICIT` | Generated test gửi HTTP tới server thực tại host/port. | Khi cần kiểm server/transport HTTP thực trong môi trường test. |

Chế độ `EXPLICIT` có thể dùng với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và HTTP client trỏ tới cổng runtime. **Không chỉ thay `WEBTESTCLIENT` bằng `EXPLICIT` mà giữ nguyên base test**: cách bind và khởi động server khác nhau. Kiểm TLS, gateway, HTTP/2 hoặc network timeout có thể cần integration tests riêng.

## 7. Generated producer test phải xác minh HTTP, không xác minh operator Reactor

Với hợp đồng đã mô tả và cấu hình đúng, một lần build producer thực hiện:

1. Nạp các hợp đồng Groovy hoặc YAML.
2. Sinh test theo `JUNIT5` và `WEBTESTCLIENT`.
3. Kế thừa base test, khởi tạo Spring context và HTTP test client.
4. Gọi `GET /api/orders/42`, xác minh `200` và body `{"id":42,"status":"PAID"}`.
5. Gọi `GET /api/orders/999`, xác minh `404`.

Trong một producer Maven đã cấu hình Contract Verifier:

~~~shell
mvn clean verify
~~~

Hãy kiểm **mã test được sinh**, báo cáo Surefire và số test thực thi. Dòng `BUILD SUCCESS` với 0 generated tests không có giá trị xác nhận hợp đồng. Một test hợp đồng thành công phải phát hiện được khi cố tình làm sai implementation.

| Thay đổi ở WebFlux producer | Hành vi consumer thấy | Kết quả mong đợi |
| --- | --- | --- |
| `status` từ `PAID` sang `PENDING` | JSON khác hợp đồng. | Generated test **FAIL**. |
| Bỏ ánh xạ trường hợp `Mono.empty()` sang 404 | Endpoint thiếu đơn có thể trả status khác. | Test trường hợp 999 **FAIL**. |
| Đổi route sang `/orders/{id}` | Path cũ bị lỗi. | Generated test **FAIL**. |
| Thay `map` bằng cách triển khai tương đương, HTTP giữ nguyên | Không khác biệt quan sát được. | Generated test **PASS**. |

Đây là lợi thế quan trọng: hợp đồng bảo vệ **hành vi** khi nhóm refactor kiến trúc, không buộc code phải dùng một operator nhất định.

### 7.1. Test WebTestClient viết tay để so sánh

Trong một Spring Boot WebFlux test đã cấu hình `WebTestClient`:

~~~java
@Autowired
WebTestClient webTestClient;

@Test
void shouldReadPaidOrder() {
    webTestClient.get()
        .uri("/api/orders/42")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
        .expectBody()
        .jsonPath("$.id").isEqualTo(42)
        .jsonPath("$.status").isEqualTo("PAID");
}

@Test
void missingOrderIs404() {
    webTestClient.get()
        .uri("/api/orders/999")
        .exchange()
        .expectStatus().isNotFound();
}
~~~

Đoạn này minh họa **assertions cần có**, không phải mã test nguyên văn của plugin. Một test viết tay đạt không thay thế việc bảo đảm **generated producer tests thật sự chạy** với source contract đã lưu.

## 8. Consumer dùng WebClient và Stub Runner

Ở phía Billing, client có thể dùng `WebClient`; việc producer triển khai MVC hay WebFlux **không thay đổi HTTP request mà Billing phải gửi**.

~~~java
package com.acme.billing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Component
public class OrderGateway {
    private final WebClient client;

    public OrderGateway(WebClient.Builder builder,
                        @Value("${orders.base-url}") String baseUrl) {
        this.client = builder.baseUrl(baseUrl).build();
    }

    public Mono<OrderView> getOrder(long id) {
        return client.get()
            .uri("/api/orders/{id}", id)
            .retrieve()
            .bodyToMono(OrderView.class);
    }

    public record OrderView(long id, String status) {}
}
~~~

Phương thức `getOrder` trả `Mono` vì **consumer chọn cách sử dụng WebClient**, không phải vì hợp đồng yêu cầu kiểu Java này.

Sau khi producer verification đạt, producer đóng gói artifact `stubs` theo version, ví dụ `com.acme:order-service:1.0.0:stubs`. Consumer có thể viết test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.contract.stubrunner.spring.AutoConfigureStubRunner;
import org.springframework.cloud.contract.stubrunner.spring.StubRunnerProperties;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = "orders.base-url=http://localhost:8089")
@AutoConfigureStubRunner(
    ids = "com.acme:order-service:1.0.0:stubs:8089",
    stubsMode = StubRunnerProperties.StubsMode.LOCAL
)
class OrderGatewayContractTest {
    @Autowired
    private OrderGateway orders;

    @Test
    void readsPaidOrder() {
        StepVerifier.create(orders.getOrder(42))
            .assertNext(order -> {
                assertThat(order.id()).isEqualTo(42);
                assertThat(order.status()).isEqualTo("PAID");
            })
            .verifyComplete();
    }

    @Test
    void handles404() {
        StepVerifier.create(orders.getOrder(999))
            .expectError(WebClientResponseException.NotFound.class)
            .verify();
    }
}
~~~

Đây là test minh họa, cần khai báo Stub Runner, WebClient, Spring Boot Test, `reactor-test` và AssertJ trong project. Với `LOCAL`, artifact stub phải được cài vào Maven local trước khi chạy consumer test; trong CI độc lập máy dùng `REMOTE`, `repositoryRoot` và quyền truy cập tương ứng.

**Stub không chạy implementation reactive của producer**: nó chỉ mô phỏng response HTTP từ hợp đồng. Consumer test giúp bảo đảm WebClient gửi request đúng và xử lý body/status đúng. Nó **không thể thay cho generated producer test**, bởi chính producer thật có thể đã lệch hợp đồng.

## 9. Streaming: nơi hợp đồng HTTP cần chi tiết hơn

Không phải mọi endpoint reactive đều streaming. Một `Flux<OrderView>` hữu hạn với media type `application/json` có thể được serialize thành JSON array hoàn chỉnh, trong khi `text/event-stream` và `application/x-ndjson` thể hiện một giao thức truyền dữ liệu **theo luồng**.

| Endpoint mẫu | Media type | Consumer cần hiểu |
| --- | --- | --- |
| `GET /api/orders` trả danh sách hữu hạn | `application/json` | Một JSON array; kiểm thứ tự nếu API cam kết. |
| `GET /api/orders/42/events` | `text/event-stream` | Chuỗi SSE event, có thể đến dần, kết nối có thể sống lâu. |
| `GET /api/orders/feed` | `application/x-ndjson` | Các JSON object theo từng dòng; không phải một JSON array. |

Ví dụ handler SSE:

~~~java
@GetMapping(
    value = "/api/orders/42/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
Flux<OrderEvent> events() {
    return Flux.just(
        new OrderEvent("CREATED"),
        new OrderEvent("PAID")
    );
}

record OrderEvent(String type) {}
~~~

Một kiểm thử WebTestClient có thể kiểm hai event hữu hạn:

~~~java
Flux<OrderEvent> events = webTestClient.get()
    .uri("/api/orders/42/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .returnResult(OrderEvent.class)
    .getResponseBody();

StepVerifier.create(events.take(2))
    .assertNext(e -> assertThat(e.type()).isEqualTo("CREATED"))
    .assertNext(e -> assertThat(e.type()).isEqualTo("PAID"))
    .expectComplete()
    .verify(Duration.ofSeconds(3));
~~~

Đoạn code này chỉ là **phần thân test**, giả định đã có imports, WebTestClient, AssertJ và Reactor Test. Deadline ba giây là **giới hạn cho ví dụ**, không phải SLA. Với stream thật, có thể cần bảo vệ **event ID, order, framing, reconnect, heartbeat, timeout, cancellation và xử lý lỗi giữa luồng**.

**Một hợp đồng HTTP JSON body tĩnh không tự kiểm được mọi hành vi của SSE/NDJSON**, nhất là stream vô hạn. Phải xem khả năng DSL/plugin của phiên bản đang dùng và bổ sung streaming integration tests thích hợp; đừng giả định Stub Runner tự mô phỏng đầy đủ timing, backpressure và vòng đời luồng.

## 10. Những thuộc tính reactive cần kiểm ngoài hợp đồng

### 10.1. Non-blocking

Một phương thức có thể trả `Mono` nhưng vẫn dùng I/O blocking:

~~~java
Mono<OrderView> find(long id) {
    return Mono.fromCallable(() -> blockingRepository.findById(id));
}
~~~

Nếu blocking I/O chạy trên event-loop, throughput và độ trễ có thể xấu dù contract tests đều **PASS**. Cần đánh giá kiến trúc, sử dụng công cụ phát hiện blocking, hoặc concurrency/load tests. Nếu chuyển blocking I/O lên `boundedElastic`, vẫn phải xét chi phí và giới hạn tài nguyên.

### 10.2. Backpressure

Backpressure cho phép subscriber yêu cầu lượng dữ liệu mà publisher phát theo cơ chế Reactive Streams. Một HTTP contract mô tả body JSON hữu hạn không tự kiểm **request(n)**, buffer overflow, memory pressure hay tốc độ đọc chậm của client. Kiểm chúng bằng Reactor tests, integration tests với streaming và các phép đo vận hành phù hợp.

### 10.3. Timeout, retry và cancellation

Stub trả `200` ngay lập tức không chứng minh WebClient xử lý đúng **timeout, retry, 5xx hoặc việc đóng kết nối**. Với những yêu cầu này, consumer test nên có stub delay/lỗi được cấu hình rõ, `StepVerifier` hoặc virtual time khi phù hợp, và test môi trường mạng riêng khi cần.

Nguyên tắc phân tầng: **Contract Verifier kiểm cam kết giao tiếp**, còn **unit/integration/performance tests** kiểm thuộc tính reactive mà HTTP body/status không biểu đạt đủ.

## 11. Reactive error handling có thể làm thay đổi HTTP contract

WebFlux cho phép ánh xạ trường hợp không có dữ liệu thành lỗi HTTP:

~~~java
return orders.findById(id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND)));
~~~

Hoặc dùng `Mono<ResponseEntity<OrderView>>` như mục 2.2. Dù triển khai nào, khi contract yêu cầu `404` thì generated test phải kiểm điều đó.

Ngược lại, thêm một cơ chế “nuốt lỗi” như:

~~~java
.onErrorReturn(new OrderView(0L, "UNKNOWN"))
~~~

có thể biến một trường hợp lỗi thành response thành công với dữ liệu giả. Đây **không còn là refactor nội bộ** nếu HTTP status/body thay đổi. Tương tự, `onErrorResume`, `onErrorComplete` hoặc `retryWhen` có thể làm thay đổi status, body, timing hoặc thời điểm kết thúc response; phải review tác động quan sát được.

## 12. Fixture và trạng thái trong reactive producer tests

Một contract test chỉ có giá trị nếu dữ liệu mà producer cần **đã sẵn sàng trước khi gửi HTTP request**. Với reactive repository, việc tạo `Publisher` không tự thực thi thao tác ghi.

| Rủi ro | Cách xử lý |
| --- | --- |
| `repository.save(...)` được gọi nhưng không subscribe/await. | Đợi publisher setup hoàn thành trong test lifecycle, có deadline rõ. |
| Test dùng transaction chưa commit; HTTP request chạy nơi khác. | Seed dữ liệu đã commit và có thể nhìn thấy từ handler. |
| Các test cùng sửa ID 42. | Database/schema/key riêng hoặc reset fixture có kiểm soát. |
| Cache còn dữ liệu từ test trước. | Reset cache hoặc key cô lập. |
| Test dùng `Thread.sleep` để chờ side effect. | Dùng phép chờ publisher có điều kiện/timeout xác định. |
| Thời gian/scheduler làm test chập chờn. | Cố định Clock, dùng virtual time ở mức phù hợp. |

Ví dụ **đoạn base test** khi dùng Spring Data reactive repository:

~~~java
@BeforeEach
void prepareFixture() {
    StepVerifier.create(
        repository.deleteAll()
            .then(repository.save(new OrderEntity(42L, "PAID")))
    )
    .expectNextCount(1)
    .verifyComplete();
}
~~~

Đoạn này minh họa ý tưởng: fixture phải **được thực thi và hoàn tất** trước khi generated test chạy. Nó không thay thế cấu hình database, repository, entity hoặc giới hạn thời gian phù hợp. `deleteAll()` chỉ nên dùng với database test cô lập, không dùng trên dữ liệu chia sẻ giữa các bài test hoặc môi trường thật.

## 13. CI bảo vệ hợp đồng khi chuyển MVC sang WebFlux

~~~mermaid
flowchart TD
    A["Thay đổi producer hoặc refactor sang WebFlux"] --> B["Giữ/đọc cùng bộ HTTP contracts"]
    B --> C["Verifier sinh tests với mode WebFlux phù hợp"]
    C --> D["Chạy producer tests 200, 404 và schema"]
    D --> E{"Producer đúng contract?"}
    E -->|Không| F["Chặn publish, sửa implementation hoặc thương lượng API"]
    E -->|Có| G["Chạy reactive tests bổ sung"]
    G --> H["Đóng gói/publish stubs theo version"]
    H --> I["Consumer dùng Stub Runner"]
    I --> J["Đánh giá tương thích với consumer còn hỗ trợ"]
~~~

Quy trình đề xuất:

1. **Giữ bộ HTTP contracts hiện hữu** làm đường cơ sở khi chuyển MVC sang WebFlux. Đừng xóa contract chỉ vì handler đổi từ object sang Mono.
2. **Đổi cấu hình producer verification** sang `WEBTESTCLIENT` hoặc `EXPLICIT` phù hợp WebFlux, đồng thời kiểm generated test được sinh và **thực sự chạy**.
3. **Thử phá API có chủ đích** như đổi `status` hoặc làm sai 404; contract test phải FAIL.
4. **Kiểm reactive runtime riêng** nếu có yêu cầu non-blocking, concurrency, timeout, retry, streaming/cancellation.
5. **Chỉ phát hành stub sau khi producer verification đạt**. Artifact stub phải gắn được với source/contract/version đã xác minh.
6. **Consumer test dùng Stub Runner** với version được ghim, kiểm đúng mã client và lỗi quan trọng.
7. **Review breaking change** nếu đổi JSON array thành SSE/NDJSON, đổi status, Content-Type, schema hoặc quy tắc lỗi. Đây là thay đổi giao tiếp dù hai phía đều sử dụng Reactor.

## 14. Sai lầm thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm |
| --- | --- | --- |
| Generated test không chạy trên WebFlux. | `MOCKMVC` hoặc base test Spring MVC vẫn còn trong cấu hình. | Chọn mode WebFlux hỗ trợ, kiểm generated imports/client và setup. |
| `BUILD SUCCESS` nhưng 0 generated tests. | Test discovery, lifecycle hoặc plugin config sai. | Mở report và source generated tests. |
| ID không tồn tại nhận `200` rỗng thay vì 404. | `Mono.empty()` không được chuyển thành status 404. | Ánh xạ HTTP error tường minh và chạy test 404. |
| WebTestClient không bind được handler. | Base class/client binding sai phiên bản hoặc ứng dụng tự chọn MVC. | Kiểm classpath, test context và generated test. |
| Test lúc thấy đơn 42, lúc không. | Reactive fixture chưa hoàn tất hoặc state leak. | Đợi setup, seed/commit dữ liệu test và cô lập trạng thái. |
| Consumer nhận WireMock 404 ngoài dự kiến. | Mapping không khớp path/header/body hoặc stub version sai. | Đọc mapping trong JAR `stubs`, đối chiếu request thực. |
| HTTP contract pass nhưng throughput kém. | Blocking I/O, scheduler hoặc backpressure ngoài phạm vi contract. | Đo hiệu năng, kiểm blocking và concurrency. |
| Consumer không đọc được response sau migration. | Media type đã đổi từ JSON sang SSE/NDJSON. | Review và version hóa thay đổi giao tiếp, thêm streaming tests. |
| Stream test treo vô hạn. | Không giới hạn event/cancellation/timeout. | Dùng `take(n)` và deadline hữu hạn. |
| Stub test xanh nhưng producer thật sai. | Producer generated tests bị skip hoặc không thực thi code thật. | Bắt buộc producer verification trước publish. |

Chẩn đoán theo đường đi **contract → generated test → WebFlux base test → HTTP response thật → stub mapping → consumer client**. Khi HTTP đúng nhưng concurrency kém, vấn đề thuộc nhánh runtime, không phải lý do để nới lỏng matcher HTTP.

## 15. Thực hành: một hợp đồng, hai cách triển khai

Thực hiện trên một producer Spring Boot WebFlux và một consumer dùng WebClient:

1. **Tạo hợp đồng HTTP** `GET /api/orders/42` trả 200 và `PAID`; `GET /api/orders/999` trả 404, chọn Groovy hoặc YAML làm nguồn duy nhất.
2. **Cài đặt WebFlux controller** trả `Mono<ResponseEntity<OrderView>>`, với `OrderLookup` phát kết quả cho ID 42 và `Mono.empty()` cho ID 999.
3. **Cấu hình Contract Verifier** dùng `JUNIT5` + `WEBTESTCLIENT` và base test có WebFlux application context.
4. **Chạy `mvn clean verify`**, xác nhận generated tests được thực thi và hai tình huống PASS.
5. **Cố tình phá hợp đồng**: bỏ xử lý 404 hoặc đổi `status` thành `state`. Xác nhận test FAIL rồi hoàn nguyên.
6. **Refactor code reactive bên trong** nhưng không đổi status, headers và body. Xác nhận generated tests vẫn PASS.
7. **Đóng gói/cài stub** sau khi producer tests đạt; cho Billing chạy `OrderGateway` và dùng `StepVerifier` kiểm 200 và 404 qua Stub Runner.
8. **Tạo một endpoint Flux hữu hạn** trả JSON array và một endpoint SSE; giải thích khác biệt media type, framing và cách kiểm.
9. **Viết thêm một test ngoài hợp đồng** cho timeout, stream cancellation, blocking hoặc concurrency phù hợp mục tiêu dự án.
10. **Ghi lại các thay đổi có thể phá tương thích** khi chuyển MVC sang WebFlux và đưa cả producer/consumer verification vào CI.

**Tiêu chí đạt:** bạn giải thích được **đâu là lời hứa HTTP, đâu là chi tiết WebFlux/Reactor**, chứng minh producer test phát hiện breaking change và chứng minh consumer có thể kiểm mã gọi bằng stub **mà không khởi động implementation reactive của producer**.

## 16. Câu hỏi tự kiểm tra

1. Đổi controller từ `OrderView` sang `Mono<OrderView>` nhưng giữ nguyên HTTP status/JSON có bắt buộc đổi hợp đồng không? Vì sao?
2. Vì sao `Mono.empty()` không nên tự được hiểu là 404?
3. `testFramework=JUNIT5` và `testMode=WEBTESTCLIENT` quyết định những việc gì?
4. Stub Runner có chạy reactive repository hoặc các operator `Mono` của producer không?
5. Tại sao một contract test pass không chứng minh toàn bộ pipeline non-blocking?
6. Khi nào Flux có thể được serialize thành JSON array, và khi nào phải mô tả SSE/NDJSON riêng?
7. Vì sao một response body tĩnh không đủ kiểm backpressure, reconnect, timeout và cancellation?
8. Vì sao gọi `repository.save(...)` mà bỏ qua Publisher có thể làm fixture reactive chưa được ghi?
9. Đổi 404 sang 200 rỗng là refactor nội bộ hay thay đổi có thể phá hợp đồng?
10. Khi chuyển từ MVC sang WebFlux, vì sao cần giữ các HTTP contracts đang phục vụ consumer như đường cơ sở?

**Ghi nhớ:** **Hợp đồng HTTP mô tả kết quả consumer quan sát qua mạng; Reactor mô tả cách producer tạo ra kết quả đó**. Contract Verifier với `WEBTESTCLIENT` hoặc mode phù hợp xác minh WebFlux producer vẫn đáp ứng status, headers và body; Stub Runner giúp consumer kiểm client độc lập. Những yêu cầu về **non-blocking, backpressure, timing, retry và vòng đời streaming** phải được bảo vệ ở tầng kiểm thử phù hợp. Tách hai trách nhiệm giúp hiện đại hóa sang reactive mà không vô tình thay đổi lời hứa API.
