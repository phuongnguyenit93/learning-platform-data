# Thiết lập base test cho ứng dụng WebFlux

## Mục tiêu bài học

**Spring Cloud Contract** cho phép mô tả hành vi HTTP hoặc thông điệp bằng **Groovy DSL** và **YAML DSL**, sinh kiểm thử hợp đồng phía **producer** và phát hành stub để **consumer** dùng qua **Stub Runner**. Với ứng dụng dựa trên **Spring WebFlux**, việc chọn đúng công cụ chạy HTTP test và cấu hình **base test class** quyết định generated tests có thật sự kiểm chứng ứng dụng reactive hay không.

Điểm khác biệt quan trọng: WebFlux sử dụng các kiểu reactive như `Mono`, `Flux` và có thể triển khai endpoint qua annotation controller hoặc functional router. Một test setup dành cho Spring MVC/MockMvc không mặc nhiên áp dụng được cho ứng dụng WebFlux. **Spring Cloud Contract Verifier** cần được cấu hình để generated tests sử dụng cơ chế tương thích, thường là **WebTestClient** thông qua tích hợp Rest Assured WebTestClient ở các phiên bản hỗ trợ.

Sau bài học, bạn có thể:

- Giải thích vai trò của base test và phân biệt contract DSL, generated producer test, WebTestClient và stub.
- Chọn chiến lược kiểm thử **application context**, **standalone handler/router** hoặc **HTTP server thực** theo mức bảo đảm cần thiết.
- Hiểu cấu hình `WEBTESTCLIENT` cho Maven/Gradle và điều kiện cần để generated test được biên dịch, chạy.
- Thiết kế base test với dữ liệu, đồng hồ, dependency và trạng thái reactive được kiểm soát.
- Phân biệt response JSON hữu hạn với stream/SSE và xác định phần nào cần test chuyên biệt.
- Chẩn đoán các lỗi thường gặp về test mode, timeout, security filter, Reactor context và độ tin cậy trong CI.

## 1. Vì sao ứng dụng WebFlux cần base test phù hợp?

Một endpoint reactive có thể được viết:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    private final OrderQueryService queryService;

    OrderController(OrderQueryService queryService) {
        this.queryService = queryService;
    }

    @GetMapping("/{id}")
    Mono<ResponseEntity<OrderResponse>> getOrder(@PathVariable String id) {
        return queryService.findById(id)
            .map(ResponseEntity::ok)
            .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

Các kiểu `OrderQueryService` và `OrderResponse` là ví dụ của ứng dụng, không thuộc Spring Cloud Contract. Điểm cần chú ý:

- Controller trả về `Mono<ResponseEntity<OrderResponse>>`; quá trình xử lý có thể hoàn tất **bất đồng bộ**.
- Nếu publisher phát ra một order, HTTP response là **200 OK** với JSON tương ứng.
- Nếu publisher hoàn tất rỗng, controller trả về **404 Not Found** theo logic ví dụ.
- Nếu publisher phát lỗi, kết quả HTTP phụ thuộc xử lý exception của WebFlux; **không thể mặc định mọi lỗi đều trở thành 404**.

Hợp đồng chỉ mô tả **HTTP method, URL, headers, body và status** mà consumer nhìn thấy. Base test có nhiệm vụ thiết lập đúng ứng dụng, test client và fixture để generated producer test thực thi endpoint đó. Không nên đưa `Mono`, `Flux` hay tên repository nội bộ vào hợp đồng chỉ vì đó là implementation reactive.

### Sơ đồ hai nhánh từ một hợp đồng

~~~mermaid
flowchart TD
    A["Contract Groovy/YAML"] --> B["Spring Cloud Contract Verifier"]
    B --> C["Generated producer test"]
    B --> D["Stub/mapping"]
    E["Base test WebFlux<br/>Test client + context + fixtures"] --> C
    C --> F["Gọi HTTP handler/route của producer"]
    F --> G["Kiểm chứng status, header, JSON"]
    D --> H["Phát hành stub artifact"]
    H --> I["Consumer test qua Stub Runner"]
~~~

**Generated producer test và consumer stub không thực thi cùng một chương trình.** Base test chỉ tham gia nhánh producer. Stub Runner phục vụ dữ liệu theo stub mapping đã tạo; nó không chạy `Mono` hay gọi các phương thức fixture từ base class của producer.

## 2. WebTestClient, RestAssuredWebTestClient và MockMvc khác nhau thế nào?

Trong Spring WebFlux, **WebTestClient** là công cụ thử HTTP được thiết kế để tương tác với server hoặc handler WebFlux. Spring Cloud Contract có các chế độ sinh test khác nhau; ở chế độ WebTestClient, một số phiên bản sinh mã thông qua **RestAssuredWebTestClient** (adapter của Rest Assured) để cấu hình và kiểm tra HTTP.

| Công cụ | Vai trò điển hình | Cảnh báo |
| --- | --- | --- |
| **WebTestClient** | Gửi request và assert response WebFlux trong test do lập trình viên viết | Chưa chắc generated test của Verifier gọi trực tiếp API fluent `WebTestClient` |
| **RestAssuredWebTestClient** | Tích hợp Rest Assured với WebTestClient; được generated test dùng trong test mode tương ứng | Base test phải khởi tạo đúng context/client trước khi test chạy |
| **RestAssuredMockMvc / MockMvc** | Công cụ kiểm thử dành cho Servlet/Spring MVC | Không tự động thay thế được cho WebFlux |
| **RestAssured qua HTTP port thật** | Thử request vào server đang lắng nghe trên cổng mạng | Cần chạy HTTP server và cấu hình host/port, thường chậm hơn kiểm thử in-memory |
| **StepVerifier** | Kiểm tra tín hiệu `Publisher` và thời gian trong Reactor | Không phải công cụ tự động kiểm chứng HTTP contract thay cho Verifier |

Ví dụ một test WebFlux viết tay có thể dùng `WebTestClient`:

~~~java
@Autowired
WebTestClient client;

@Test
void shouldReturnPaidOrder() {
    client.get()
        .uri("/api/orders/ORD-1001")
        .accept(MediaType.APPLICATION_JSON)
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.id").isEqualTo("ORD-1001")
        .jsonPath("$.status").isEqualTo("PAID");
}
~~~

Đoạn trên là **test viết tay**, chưa phải generated test của Spring Cloud Contract. Để Verifier sinh kiểm thử tương thích với WebFlux, phải chọn đúng **test mode** và thiết lập base class theo API mà generated tests thực tế sử dụng.

## 3. Hợp đồng mẫu cho producer WebFlux

Tại `src/test/resources/contracts/orders/get_paid_order.yml`:

~~~yaml
description: "Truy vấn đơn hàng đã thanh toán qua WebFlux"
name: get_paid_order
request:
  method: GET
  url: /api/orders/ORD-1001
  headers:
    Accept: application/json
response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    id: ORD-1001
    status: PAID
~~~

Đây vẫn là **hợp đồng HTTP thông thường**. Không cần một cú pháp contract khác chỉ vì controller trả `Mono`:

- Request: GET /api/orders/ORD-1001.
- Response: status 200, JSON có id và status.
- Producer test phải khởi tạo WebFlux application/handler và fixture tạo điều kiện để trả response này.
- Stub có thể trả JSON tương ứng cho consumer, bất kể consumer được viết bằng WebClient, RestTemplate hoặc công cụ khác.

Hợp đồng cho tình huống không tìm thấy:

~~~yaml
description: "Truy vấn đơn hàng không tồn tại"
name: get_missing_order
request:
  method: GET
  url: /api/orders/ORD-9999
response:
  status: 404
~~~

Nếu đội cần hợp đồng hóa body lỗi hoặc header, phải bổ sung theo giao diện đã thỏa thuận. Đừng giả định WebFlux tự động trả cùng schema lỗi với Spring MVC ở mọi cấu hình.

## 4. Chọn chế độ sinh test WebTestClient

Với những phiên bản Spring Cloud Contract có hỗ trợ **WEBTESTCLIENT** test mode, lựa chọn này định hướng Verifier sinh test tương thích với HTTP testing của WebFlux thay vì MockMvc.

### Maven plugin

Ví dụ cấu hình tối giản trong `pom.xml`:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-contract-maven-plugin</artifactId>
            <version>VERSION_PHU_HOP</version>
            <extensions>true</extensions>
            <configuration>
                <testMode>WEBTESTCLIENT</testMode>
                <baseClassForTests>
                    com.example.orders.contract.WebFluxContractBase
                </baseClassForTests>
                <contractsDirectory>
                    src/test/resources/contracts
                </contractsDirectory>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

`VERSION_PHU_HOP` là **placeholder**, không phải phiên bản có thể copy nguyên vào build. Cần chọn release tương thích với Spring Boot, Spring Cloud và test libraries của dự án. Cấu hình plugin ở đây không thay thế dependency quản lý bởi BOM hoặc những dependency kiểm thử cần thiết.

### Gradle Groovy DSL

~~~groovy
plugins {
    id 'org.springframework.cloud.contract' version 'VERSION_PHU_HOP'
}

contracts {
    testMode = 'WEBTESTCLIENT'
    baseClassForTests = 'com.example.orders.contract.WebFluxContractBase'
    contractsDslDir = file('src/test/resources/contracts')
}
~~~

Đây là **khung cấu hình Gradle Groovy DSL**, không phải cú pháp của `build.gradle.kts`. Tên tùy chọn, cách khai báo plugin và dependencies phải được đối chiếu với phiên bản Spring Cloud Contract đang sử dụng.

### Kiểm tra test mode có thực sự hiệu lực

Sau khi sinh test, cần xác minh:

1. Đầu ra không chỉ tồn tại mà **được biên dịch và test runner phát hiện**.
2. Generated source tham chiếu đến **adapter HTTP phù hợp** với WebFlux và base class đúng tên/package.
3. Base class khởi tạo HTTP test client trước khi generated test gọi request.
4. Khi chạy test, request đi đến **đúng producer handler/router**, không phải một stub độc lập chỉ trả response mong đợi.
5. Test runner báo test đã thực thi; không chấp nhận tình trạng build xanh vì contract tests bị bỏ qua.

Không sửa generated test bằng tay để đổi `MockMvc` thành `WebTestClient`. Generated source được sinh lại trong các build tiếp theo; phải sửa cấu hình test mode và base test.

## 5. Thiết lập base test với ApplicationContext

Đối với ứng dụng dùng annotation controllers hoặc functional router của WebFlux, kiểm thử qua **Spring ApplicationContext** cho phép sử dụng router, handler, converter, exception handler và nhiều filter đã cấu hình.

Ví dụ base class tham khảo cho các phiên bản Verifier sinh test với `RestAssuredWebTestClient`:

~~~java
package com.example.orders.contract;

import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
public abstract class WebFluxContractBase {

    @Autowired
    private ApplicationContext applicationContext;

    @BeforeEach
    void setUpContractClient() {
        RestAssuredWebTestClient.applicationContextSetup(applicationContext);
    }
}
~~~

Đây là **mẫu cho một cách tích hợp**. Các API như `applicationContextSetup(...)` và kiểu generated test cần được kiểm chứng với phiên bản Rest Assured/Spring Cloud Contract của dự án. Một số cấu hình có thể chọn truyền một `WebTestClient` được tạo sẵn cho adapter thay vì dùng trực tiếp application context.

Ý nghĩa:

- `@SpringBootTest` tạo context của ứng dụng producer.
- Chế độ `MOCK` thường không mở cổng HTTP ngẫu nhiên; WebTestClient có thể gắn vào application context để xử lý request trong tiến trình test.
- `@BeforeEach` bảo đảm adapter được thiết lập trước mỗi generated test.
- Generated test chạy các assertion HTTP dựa trên hợp đồng.

**Điều kiện quan trọng:** annotation này phải thực sự khởi tạo một **WebFlux application context**. Nếu dự án có cả Spring MVC và WebFlux, cách Boot chọn web application type và dependencies có thể ảnh hưởng mode thực tế. Không dùng `@SpringBootTest` như bằng chứng đủ rằng test đã chạy bằng WebFlux.

### Base class không nhất thiết cần mở server thật

Kiểm thử in-memory qua application context thường đủ để xác minh controller/route, JSON serialization và nhiều filter. Nhưng nó không tự kiểm tra chi tiết của HTTP server thực như cấu hình cổng, TLS, reverse proxy hoặc một số behavior phụ thuộc Netty/runtime mạng.

Nếu những yếu tố đó là một phần cam kết quan trọng, cần **integration test qua HTTP server thật** ở lớp kiểm tra bổ sung hoặc chọn chiến lược test phù hợp.

## 6. Phương án dùng WebTestClient có sẵn

Trong dự án Spring Boot WebFlux, có thể sử dụng `@AutoConfigureWebTestClient` để có client được inject. Ví dụ:

~~~java
package com.example.orders.contract;

import io.restassured.module.webtestclient.RestAssuredWebTestClient;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
public abstract class WebFluxLiveServerContractBase {

    @Autowired
    WebTestClient webTestClient;

    @BeforeEach
    void configure() {
        RestAssuredWebTestClient.webTestClient(webTestClient);
    }
}
~~~

Đây là phương án **khác** với `applicationContextSetup`, không phải phần phải gộp cả hai vào cùng một base class. Khi dùng `RANDOM_PORT`, server có thể chạy trên cổng động, và `WebTestClient` được cấu hình để gọi instance của ứng dụng test. Cần xác minh `@AutoConfigureWebTestClient`, cách autowire và API adapter hoạt động đúng trên phiên bản Boot/Rest Assured đã chọn.

**Không tự hardcode cổng 8080** vào generated test. Cổng đó có thể đang bị ứng dụng khác dùng hoặc không trùng server của test. Ưu tiên client được test context cấu hình hoặc cơ chế port injection tương ứng.

### Khi nào dùng phương án nào?

| Tiêu chí | Bind vào ApplicationContext | HTTP server trên RANDOM_PORT |
| --- | --- | --- |
| Tốc độ | Thường nhanh hơn, không phải mở cổng mạng | Thường nặng hơn |
| Kiểm tra handler/router/serialization | Có, trong phạm vi context | Có, qua HTTP thật |
| Kiểm tra runtime HTTP server | Không đầy đủ | Bao phủ nhiều yếu tố mạng/server hơn |
| Tính cô lập | Ít va chạm port | Cần điều phối server và client |
| Phù hợp | Contract tests thường xuyên trong producer CI | Khi cần xác minh cấu hình server hoặc xử lý qua HTTP socket |

Cả hai cách đều có thể đúng. Chọn theo **điều hợp đồng cần chứng minh**, phiên bản framework và chi phí CI; tránh mặc định rằng cách nặng hơn luôn tốt hơn.

## 7. Standalone setup: nhanh nhưng phạm vi hẹp

Đôi khi nhóm chỉ muốn kiểm tra một handler hoặc controller WebFlux độc lập. `WebTestClient` hỗ trợ gắn vào controller/router bằng các cách xây dựng client phù hợp. Một ví dụ test WebFlux **viết tay**:

~~~java
WebTestClient client = WebTestClient
    .bindToController(new OrderController(fakeOrderQueryService))
    .build();

client.get()
    .uri("/api/orders/ORD-1001")
    .exchange()
    .expectStatus().isOk();
~~~

Đoạn này minh họa chiến lược **standalone**, không phải lệnh thiết lập adapter Verifier có thể copy trực tiếp. Nếu muốn generated tests dùng một handler dựng thủ công, phải cấu hình RestAssuredWebTestClient theo API standalone tương ứng phiên bản và bảo đảm base class mang đủ dependency.

Standalone setup có giới hạn:

- Có thể **bỏ qua WebFilterChain/security** nếu không tự thêm các thành phần cần thiết.
- Không tự xác minh đầy đủ `@ControllerAdvice`, codec, routing và configuration được ứng dụng thật nạp.
- Nếu handler trả một mock response mà không đi qua logic producer cần kiểm tra, test PASS có thể chỉ chứng minh mock đáp ứng contract.

Vì vậy, với kiểm thử hợp đồng nhằm bảo vệ tương thích tích hợp, **application context** thường là lựa chọn khởi đầu có tính đại diện tốt hơn. Standalone phù hợp khi phạm vi cố ý là một handler và các giới hạn đã được ghi rõ.

## 8. Base test cần dữ liệu fixture cho luồng reactive

Một endpoint `Mono<OrderResponse>` vẫn có thể phụ thuộc vào repository reactive, cache hoặc HTTP client gọi service khác. Generated contract test cần dữ liệu **ổn định và độc lập**, không lấy từ production.

Ví dụ test fixture cho reactive repository (mã minh họa):

~~~java
import java.time.Duration;
import org.junit.jupiter.api.BeforeEach;

@BeforeEach
void seedFixture() {
    // Chỉ dùng database riêng của test.
    orderRepository.deleteAll()
        .then(orderRepository.save(
            new OrderEntity("ORD-1001", "PAID")
        ))
        .block(Duration.ofSeconds(5));
}
~~~

`OrderEntity` và `orderRepository` là các thành phần của ứng dụng mẫu. Đoạn trên chỉ trình bày ý tưởng chuẩn bị dữ liệu; khi triển khai thật, phải đặt nó trong base class phù hợp, khai báo dependency và bảo đảm không xóa dữ liệu dùng chung của test khác.

### Có được dùng block() trong base test không?

Trong **vòng đời test**, tại một phương thức setup chạy ở luồng kiểm thử thích hợp, `block(Duration)` đôi khi là cách thuận tiện để đợi fixture hoàn tất **trước khi generated test gửi HTTP request**. Nó khác với việc gọi `block()` trong code xử lý request chạy trên event loop WebFlux.

Quy tắc:

1. Chỉ block ở ranh giới test khi cần, không mang cách viết đó sang controller/service chạy reactive.
2. Đặt timeout rõ để test không chờ vô hạn.
3. Không block trên luồng Reactor non-blocking/event loop; tình huống đó có thể gây lỗi hoặc tắc nghẽn.
4. Cân nhắc khả năng dữ liệu được lưu/đọc theo transaction và consistency model thực tế của backend.
5. Nếu dùng database chung cho các test chạy song song, `deleteAll()` có thể xóa fixture của test khác. Hãy dùng database/namespace riêng hoặc cơ chế cách ly thích hợp.

Một base test đúng cần bảo đảm dữ liệu đã được ghi xong **trước** khi request reactive được gửi; nếu setup chỉ gọi `repository.save(...)` nhưng không subscribe hoặc await publisher, thao tác có thể chưa thực thi.

## 9. Fake dependency bên ngoài nhưng không giả lập mất chính producer

Order Service có thể sử dụng `WebClient` gọi một service khác. Nếu producer contract test phụ thuộc vào network bên ngoài, kết quả dễ chập chờn vì latency, DNS, token hoặc dữ liệu thay đổi.

Có thể thiết lập **test double** ở ranh giới dependency, chẳng hạn fake `PaymentGateway` hoặc fake `OrderQueryService`, tùy mục tiêu kiểm tra.

| Có thể mock/fake | Không nên thay hoàn toàn |
| --- | --- |
| Payment gateway bên ngoài | Controller/route cần xác minh |
| Đồng hồ và ID generator | JSON serialization mà consumer phụ thuộc |
| Repository bằng dữ liệu kiểm thử được kiểm soát | HTTP status/error mapping của producer |
| Bên phát event ở biên phù hợp | Logic business quyết định event có được tạo không |

Nếu base test chỉ cung cấp một mock controller trả luôn `200` và JSON giống hệt hợp đồng, phép thử không có ý nghĩa xác minh rằng **controller thật của producer** đáp ứng giao diện.

Với Spring WebFlux, test doubles thường trả `Mono.just(...)`, `Mono.empty()`, `Mono.error(...)` hoặc `Flux` theo tình huống. Cần xây dựng đủ kịch bản để phân biệt:

- **Có dữ liệu:** producer trả 200 và body hợp lệ.
- **Không có dữ liệu:** producer trả 404 theo quy tắc đã định nghĩa.
- **Dependency lỗi:** producer chuyển lỗi thành mã HTTP và schema đã thỏa thuận, không tự suy diễn.
- **Timeout:** xử lý theo hợp đồng hoặc chính sách vận hành phù hợp; không giả định timeout luôn được quy định bởi Contract DSL.

Mock phải mô phỏng **đầu vào của producer thật**, không tự tạo sẵn kết quả cuối làm bỏ qua logic cần test.

## 10. WebFlux và thời gian: đừng chữa flaky test bằng sleep

Một response reactive hữu hạn có thể được tạo sau thao tác bất đồng bộ. Khi `WebTestClient` gọi `exchange()`, test cần đợi response hoàn tất hoặc hết thời gian chờ, thay vì tự thêm `Thread.sleep(...)` trước request.

Các nguồn gây flaky:

| Nguyên nhân | Dấu hiệu | Giải pháp |
| --- | --- | --- |
| Fixture reactive chưa subscribe | Lúc có bản ghi, lúc 404 | Await publisher hoàn tất trong setup |
| Event loop bị block | Timeout ngẫu nhiên | Bỏ blocking khỏi luồng non-blocking |
| Test dùng thời gian thật | Timestamp lệch giữa các lần | Inject `Clock` hoặc dùng matcher đúng yêu cầu |
| Dependency remote chậm | CI fail phụ thuộc mạng | Fake tại biên hoặc dùng môi trường tích hợp kiểm soát |
| Timeout quá thấp | Fail khi CI tải cao | Chọn timeout có cơ sở; tách test performance |
| Test shared state | Chạy riêng PASS, chạy suite FAIL | Cách ly dữ liệu, cache, subscription và publisher |

Ví dụ một ứng dụng cần cấp `createdAt` theo thời điểm hiện tại: hãy dùng `Clock` được inject và có `Clock.fixed(...)` trong test setup khi hợp đồng cần giá trị xác định. Nếu hợp đồng chỉ yêu cầu timestamp đúng định dạng, cân nhắc matcher thay vì so sánh đúng từng nano-giây.

Đối với `Flux` có xử lý time-based hoặc backpressure, `StepVerifier.withVirtualTime(...)` hữu ích trong **unit test của reactive pipeline**, nhưng virtual time không mặc định thay `Clock` trong toàn bộ application context hoặc giả lập network cho Verifier. Cần tách các loại bằng chứng.

## 11. Kiểm tra lỗi và validation bằng hợp đồng riêng

Một bài producer contract testing nên có ít nhất những kịch bản mà consumer thực sự sử dụng để phân nhánh. Với Order Service:

~~~text
GET /api/orders/ORD-1001 -> 200 + JSON đơn hàng
GET /api/orders/ORD-9999 -> 404
POST /api/orders với body sai -> 400 + JSON lỗi theo thỏa thuận
~~~

Ví dụ kịch bản YAML cho validation:

~~~yaml
description: "Từ chối request tạo đơn hàng với quantity âm"
name: reject_negative_quantity
request:
  method: POST
  url: /api/orders
  headers:
    Content-Type: application/json
  body:
    customerId: "CUS-TEST-1001"
    quantity: -1
response:
  status: 400
  headers:
    Content-Type: application/json
  body:
    code: INVALID_QUANTITY
~~~

`INVALID_QUANTITY` là mã lỗi **minh họa**, chỉ dùng nếu đó là cam kết mà producer và consumer đã thống nhất. Với WebFlux, validation có thể hoạt động qua bean validation, functional handler hoặc logic tùy chỉnh; base test phải nạp những thành phần thật sự quyết định lỗi.

**Một nguy cơ của standalone setup** là bỏ qua filter, exception handler hoặc validation cấu hình ngoài controller, khiến generated test nhìn thấy response khác runtime thật. Cần xác nhận test setup bao phủ đúng những thành phần mà hợp đồng công bố.

## 12. WebFilter, security và Reactor Context

Ứng dụng WebFlux thường có các thành phần như:

- `WebFilter` thêm request ID, tenant, trace header hoặc thông tin xác thực.
- Spring Security filter chain quyết định quyền gọi endpoint.
- `Reactor Context` mang dữ liệu theo luồng reactive, chẳng hạn trace hoặc thông tin tenant.
- Codec/exception handler quyết định JSON output và mã HTTP.

Trong base test:

1. Nếu hợp đồng bao gồm hành vi xác thực hoặc header liên quan, đừng vô tình **bỏ qua filter** chỉ vì standalone test dễ cấu hình.
2. Nếu endpoint yêu cầu identity giả lập, hãy cấp một **test principal/credential** phù hợp, không đưa token production vào contract.
3. Nếu producer dùng Reactor Context, test phải đi qua luồng thiết lập context của ứng dụng, không giả định một `ThreadLocal` tĩnh sẽ theo mọi thao tác reactive.
4. Đảm bảo filter hoặc custom exception handler được đưa vào application context mà test đang sử dụng.

Không phải mọi security policy đều cần được mô tả trong cùng một HTTP contract. Có thể tách security tests chuyên biệt, nhưng **hợp đồng về status/header/body phải được xác minh trong ngữ cảnh có ý nghĩa với consumer**.

## 13. Functional router có khác annotation controller không?

Spring WebFlux có thể dùng:

- `@RestController` cùng `@GetMapping`, `@PostMapping`.
- `RouterFunction<ServerResponse>` cùng handler functions.

Hợp đồng bên ngoài vẫn là HTTP request/response:

~~~text
GET /api/orders/ORD-1001
Accept: application/json

-> 200, Content-Type: application/json
-> {"id":"ORD-1001","status":"PAID"}
~~~

Verifier không cần biết endpoint được định tuyến bởi annotation hay functional router. Nhưng **base test** phải gắn HTTP client vào đúng thành phần:

- Dùng application context: có thể bao gồm các router functions/handlers được nạp trong context.
- Dùng standalone: cần bind đúng controller hoặc router và chủ động đưa những filter/exception handler cần thiết vào test setup.
- Dùng HTTP server thật: bảo đảm router được register trong application và port/client đúng.

Trong tài liệu hoặc code review, hãy nói rõ **chiến lược bind client** thay vì chỉ ghi “đã dùng WebTestClient”. Hai test cùng dùng WebTestClient có thể bao phủ những phần ứng dụng khác nhau.

## 14. Response streaming: không phải mọi Flux đều nên kiểm tra như JSON đơn

`Mono<OrderResponse>` trả một response hữu hạn thường phù hợp với generated HTTP contract test. Nhưng một `Flux` có thể biểu diễn:

- Danh sách JSON hữu hạn được serialize hoàn chỉnh.
- Chuỗi event qua `text/event-stream` (SSE).
- Streaming NDJSON hoặc một publisher không bao giờ hoàn tất.

**Hợp đồng HTTP thông thường cho một body JSON cố định không tự kiểm chứng toàn bộ ngữ nghĩa streaming**, bao gồm thứ tự các event, backpressure, cancellation, reconnect, timeout và các message phát ra sau một khoảng thời gian.

| Loại endpoint | Hướng kiểm thử phù hợp |
| --- | --- |
| `Mono<ResponseEntity<T>>` | Generated HTTP contract test với WebTestClient mode |
| `Flux<T>` trả danh sách hữu hạn | Có thể dùng HTTP contract nếu response được serialize/hoàn tất như cam kết; kiểm tra output thực tế |
| SSE liên tục | Cân nhắc contract cho những event có thể quan sát và thêm WebTestClient/StepVerifier/integration tests chuyên biệt |
| Publisher vô hạn hoặc yêu cầu backpressure | Cần test reactive chuyên biệt với thời gian và số tín hiệu được kiểm soát |

Không cố định `Thread.sleep(5000)` rồi hy vọng stream phát xong. Nếu cần chờ một số event, hãy dùng công cụ có thể xác định số tín hiệu và điều kiện kết thúc, giới hạn thời gian hợp lý và dọn subscription sau test.

Contract có thể giúp xác minh **cấu trúc một message/event**; nó không phải bằng chứng đầy đủ cho đặc tính thời gian và vận hành của cả stream.

## 15. Chẩn đoán generated test không chạy đúng WebFlux

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Generated tests tham chiếu `RestAssuredMockMvc` | Test mode vẫn là MockMvc | Kiểm tra `WEBTESTCLIENT` và mã sinh thực tế |
| Không biên dịch được `RestAssuredWebTestClient` | Thiếu module/dependency test hoặc sai version | Kiểm tra dependency management và classpath test |
| Generated test không gọi được HTTP client | Base class chưa setup client hoặc không được kế thừa | Xem `baseClassForTests`, `@BeforeEach` và generated source |
| Test 404 dù route tồn tại ngoài runtime | Context/standalone setup thiếu router hoặc mapping | Kiểm tra route được nạp và chiến lược bind |
| Test trả 401/403 ngoài ý muốn | Security filter hoạt động nhưng test identity thiếu | Thiết lập principal/credential test theo phạm vi hợp đồng |
| Test PASS nhưng production lỗi security | Standalone setup đã bỏ filter | Tăng độ phủ qua context/server test |
| Test timeout | Reactive fixture chưa được subscribe, event loop bị block hoặc dependency ngoài chậm | Xem luồng reactive, timeout và external calls |
| `block()` gây lỗi | Block trên event loop/non-blocking thread | Chuyển blocking ra setup test phù hợp hoặc dùng reactive chain |
| Test chạy riêng PASS, chạy suite FAIL | Shared DB/cache/fake publisher/port | Cách ly fixture và quản lý lifecycle |
| Consumer Stub Runner PASS, producer không khớp | Stub cũ hoặc producer contract tests chưa chạy | Gắn version stub với revision đã xác minh |

Để chẩn đoán, hãy xem **ba loại bằng chứng**: source của generated tests, báo cáo test thực sự chạy và stub artifact đã được đóng gói. Chỉ nhìn màu xanh của build không bảo đảm Verifier đã kiểm tra ứng dụng WebFlux.

## 16. Thiết kế cổng kiểm soát trong CI

Một quy trình producer/consumer hữu ích:

~~~mermaid
flowchart TD
    A["Checkout producer + contract revision"] --> B["Đọc hợp đồng Groovy/YAML"]
    B --> C["Sinh test mode WEBTESTCLIENT"]
    C --> D{"Biên dịch và phát hiện generated tests?"}
    D -->|Không| X["BLOCK"]
    D -->|Có| E["Base test chuẩn bị WebFlux context + fixtures"]
    E --> F["Chạy producer contract tests"]
    F --> G{"PASS và không bị skip?"}
    G -->|Không| X
    G -->|Có| H["Tạo stub artifact có version"]
    H --> I["Consumer test qua Stub Runner"]
    I --> J{"PASS với đúng stub version?"}
    J -->|Không| X
    J -->|Có| K["Lưu release evidence có phạm vi"]
~~~

Một biên bản kiểm tra do dự án **tự thiết kế**:

~~~yaml
# Không phải output mặc định của Spring Cloud Contract.
producer_revision: "order-service@abc123"
contracts_revision: "contracts@def456"
test_mode: WEBTESTCLIENT
base_test: "com.example.orders.contract.WebFluxContractBase"
expected_contracts:
  - get_paid_order
  - get_missing_order
generated_tests_detected: true
producer_contract_tests: PASS
stub_artifact: "com.example:order-service:2.4.0:stubs"
consumer_stub_tests: PASS
~~~

Để CI đáng tin:

1. Đối chiếu **danh sách hợp đồng mong đợi** với các contract thực sự được xử lý.
2. Xác nhận generated tests thuộc test compilation/task; không chỉ hiện diện dưới `target` hoặc `build`.
3. Bảo đảm test mode `WEBTESTCLIENT` có hiệu lực và base test phù hợp.
4. Kiểm tra generated tests thực sự chạy; phát hiện trường hợp `0 tests` hoặc skip bất thường.
5. Chốt cùng contract revision, producer build và stub artifact; tránh dùng `latest` không kiểm soát.
6. Chạy consumer tests với **stub đúng phiên bản** và assert logic consumer, không chỉ kiểm tra stub server khởi động.
7. Không đánh đồng một vài contract tests PASS với toàn bộ thuộc tính về backpressure, tính chịu tải, an ninh và vận hành của WebFlux.

## 17. Tình huống thực hành

### Bài tập A — Đổi từ MVC sang WebFlux

Một producer chuyển từ `spring-boot-starter-web` sang `spring-boot-starter-webflux`. Hợp đồng YAML vẫn là GET /api/orders/ORD-1001, nhưng generated tests đang dùng MockMvc và không gọi được controller.

**Yêu cầu:** cho biết cần kiểm tra/cập nhật ở test mode, base class và dependencies; giải thích vì sao **không cần đổi URL trong contract chỉ vì công nghệ server thay đổi**.

**Gợi ý:** chọn test mode WebTestClient nếu phiên bản hỗ trợ, tạo base class WebFlux và xác minh generated source. Hành vi HTTP vẫn được giữ nếu API không đổi.

### Bài tập B — Publisher chưa được subscribe

Trong `@BeforeEach`, base test gọi `repository.save(entity)` rồi kết thúc. Một vài lần chạy test trả 404 cho order cần tồn tại.

**Yêu cầu:** giải thích điều gì có thể chưa xảy ra và đề xuất cách chuẩn bị dữ liệu chắc chắn trước request.

**Gợi ý:** một `Mono` cold có thể chưa thực thi nếu không có subscription. Tại test boundary, await publisher hoàn tất theo cách kiểm soát được; dùng timeout và dữ liệu cách ly.

### Bài tập C — Bỏ qua security filter

Một generated test sử dụng standalone setup, producer test PASS cho endpoint yêu cầu authentication. Khi consumer gọi server thật thì nhận 401.

**Yêu cầu:** phân biệt phạm vi test đã chạy với phạm vi hợp đồng kỳ vọng; chọn cách thiết lập context/identity thích hợp.

**Gợi ý:** standalone có thể thiếu security filters. Nếu auth là một phần giao diện công khai, thử qua context/server có filter thật và test credentials phù hợp.

### Bài tập D — Event stream không kết thúc

Producer cung cấp `text/event-stream` và mỗi giây phát một sự kiện. Một test đang đợi toàn bộ response body hoàn tất rồi báo timeout.

**Yêu cầu:** lý giải tại sao cách kiểm tra không phù hợp và đề xuất phép thử cho số event hữu hạn hoặc một khoảng thời gian đã được kiểm soát.

**Gợi ý:** stream vô hạn không có body hoàn chỉnh theo cách một JSON response thông thường. Dùng test streaming có kiểm soát số tín hiệu, timeout, cancellation và StepVerifier/WebTestClient phù hợp; không dùng sleep cố định.

### Bài tập E — Stub cũ khiến CI đánh giá sai

Producer WebFlux bản 2.4.0 chạy contract tests PASS, consumer test PASS với Stub Runner nhưng đang lấy `order-service:2.3.0:stubs`.

**Yêu cầu:** xác định bằng chứng còn thiếu và đề xuất cách khóa revision/version.

**Gợi ý:** phát hành stub 2.4.0 từ đúng hợp đồng/build đã được producer test, rồi chạy lại consumer tests trên artifact đó; lưu revision và báo cáo hai phía.

## 18. Checklist base test WebFlux trước khi chấp nhận

- [ ] Hợp đồng Groovy/YAML mô tả hành vi HTTP/message thực sự consumer cần, không ràng buộc implementation reactive.
- [ ] Chọn đúng test mode `WEBTESTCLIENT` theo khả năng của plugin đang dùng.
- [ ] Base test class nằm đúng package và được `baseClassForTests` hoặc mapping tương đương chọn.
- [ ] Generated tests sử dụng adapter phù hợp với WebFlux, được biên dịch và thực thi.
- [ ] Chọn rõ chiến lược context, standalone hoặc HTTP server thật và phạm vi bảo đảm.
- [ ] WebTestClient/RestAssuredWebTestClient được thiết lập trước generated test.
- [ ] Route/controller, JSON codecs, exception handler và filter quan trọng được nạp đúng.
- [ ] Fixture reactive đã được subscribe/await đúng cách trước request và được cách ly.
- [ ] Không block event loop; setup dùng timeout rõ và không dựa vào `Thread.sleep` tùy tiện.
- [ ] Múi giờ, thời gian, ID và dữ liệu ngoài được kiểm soát bằng fixture/dependency phù hợp.
- [ ] Mock ở ranh giới phụ thuộc, không thay mất behavior producer cần kiểm chứng.
- [ ] Các trường hợp 200/404/400 và security/error behavior quan trọng có kịch bản phù hợp.
- [ ] Streaming/SSE và thuộc tính thời gian, backpressure được kiểm tra chuyên biệt khi cần.
- [ ] Stub artifact sinh từ cùng contract revision và producer build đã kiểm tra.
- [ ] Consumer test qua Stub Runner dùng đúng stub version, kết quả CI có thể truy vết.
- [ ] Không coi build xanh khi thiếu generated tests hoặc test bị skip là bằng chứng tương thích.

**Ghi nhớ:** **Base test WebFlux** không đơn thuần là thay MockMvc bằng WebTestClient. Nó phải kết nối generated producer tests với **đúng WebFlux handler, application context và dữ liệu kiểm thử**, đồng thời xác định những phần runtime nào đang được kiểm tra. Khi test mode, fixture và CI được cấu hình đúng, Spring Cloud Contract mới tạo ra bằng chứng đáng tin rằng hành vi HTTP của producer reactive vẫn phù hợp với những consumer đã được kiểm chứng.
