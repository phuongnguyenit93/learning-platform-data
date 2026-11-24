# Thời gian chờ và tác vụ bất đồng bộ trong kiểm thử

## 1. Vì sao thời gian chờ là một phần của kiểm thử reactive?

Với **Spring Cloud Contract (SCC)**, producer và consumer thống nhất hành vi HTTP hoặc thông điệp qua **Groovy DSL/YAML DSL**. Contract Verifier sinh test để xác nhận producer thực thi đúng cam kết; cùng contract có thể sinh stub để consumer chạy qua **Stub Runner**. Kết hợp trong CI giúp phát hiện thay đổi API không tương thích.

Ở ứng dụng **Spring WebFlux/Reactor**, controller có thể trả `Mono<T>` hoặc `Flux<T>`. Việc nhận request và tạo dữ liệu có thể diễn ra **bất đồng bộ**: truy vấn database reactive, gọi dịch vụ khác, chờ tín hiệu message hoặc chạy một tác vụ lâu. Nếu test chỉ kiểm tra status/body mà không quan tâm cách **subscribe, chờ, timeout, lỗi và hủy tác vụ**, ứng dụng có thể:

- Trả response đúng trong môi trường local nhưng **treo vô thời hạn** khi một dependency không trả tín hiệu.
- Thỉnh thoảng thất bại trên CI vì test chờ quá ngắn hoặc phụ thuộc thời gian thực.
- Test “xanh” khi chỉ tạo `Mono` nhưng không **subscribe**, nên logic chưa từng chạy.
- Thử stub luôn trả ngay, trong khi consumer production không xử lý được phản hồi chậm.
- Cấu hình timeout ở client, server và runner **mâu thuẫn**, khiến test báo sai nguyên nhân.

Bài học này tập trung vào **thời gian chờ và tác vụ bất đồng bộ trong kiểm thử**: xác định trách nhiệm của SCC so với kiểm thử Reactor/WebFlux, chọn timeout theo tầng, sử dụng `StepVerifier`/virtual time, kiểm thử HTTP không đồng bộ và phối hợp stub ứng viên trong CI.

### Mục tiêu

Sau bài này, bạn có thể:

1. Hiểu sự khác nhau giữa `Mono`, `Flux`, subscription, completion, error và cancellation.
2. Phân biệt **timeout nghiệp vụ**, **timeout I/O**, **timeout của HTTP test client** và **timeout toàn bộ job CI**.
3. Viết contract HTTP cho producer WebFlux và kiểm chứng bằng WebTestClient.
4. Kiểm tra luồng Reactor bằng `StepVerifier` và **virtual time** mà không dùng `Thread.sleep`.
5. Mô phỏng dependency chậm/không phản hồi và xác nhận status/error/cleanup đúng.
6. Tránh tạo bài test xanh giả bằng cách mock chính hành vi producer hoặc không chờ tác vụ thực sự hoàn tất.
7. Kiểm tra consumer qua Stub Runner, bổ sung bài test delay/timeouts và xây cổng CI có thể chẩn đoán.

## 2. Một luồng phản hồi reactive diễn ra như thế nào?

~~~mermaid
sequenceDiagram
    participant C as Checkout Consumer
    participant H as HTTP WebFlux
    participant S as Inventory Service
    participant D as Reactive Repository
    C->>H: GET /api/inventory/SKU-123
    H->>S: findStock("SKU-123")
    S->>D: Tạo Publisher truy vấn
    D-->>S: Mono<Stock>
    Note over H,D: Publisher thường chưa làm việc cho đến khi subscribe
    H->>D: Subscribe qua chuỗi reactive
    D-->>H: onNext(stock), onComplete
    H-->>C: HTTP 200 + JSON
~~~

Trong Reactor, không nên đồng nhất “đã tạo publisher” với “đã chạy xong công việc”:

| Tín hiệu/khái niệm | Ý nghĩa | Hệ quả khi kiểm thử |
|---|---|---|
| `Mono<T>` | Publisher tối đa một phần tử, rồi complete/error | Có thể trả giá trị, hoàn tất rỗng hoặc lỗi |
| `Flux<T>` | Publisher 0..n phần tử | Có thể là luồng hữu hạn hoặc kéo dài vô hạn |
| **Subscription** | Consumer đăng ký nhận tín hiệu | Phần lớn chuỗi reactive mới bắt đầu làm việc khi được subscribe |
| `onNext` | Có phần tử mới | Test phải kiểm tra dữ liệu thực sự được phát |
| `onComplete` | Luồng kết thúc thành công | Quan trọng với operation phải hoàn tất |
| `onError` | Luồng kết thúc với lỗi | Contract phải phản ánh lỗi công khai nếu lỗi được chuyển thành HTTP response |
| **Cancellation** | Subscriber hủy | Có thể cần dừng truy vấn, giải phóng tài nguyên hoặc ngừng retry |
| **Timeout** | Không nhận tín hiệu phù hợp trong khoảng chờ | Tùy tầng, có thể sinh lỗi, fallback, HTTP status hoặc kết thúc test |

**Nguyên tắc:** test reactive phải tạo subscription và có điều kiện **kết thúc/giới hạn thời gian rõ ràng**. Chỉ assert một biến `Mono<StockResponse>` khác null không chứng minh đã gọi repository hoặc xử lý kết quả.

## 3. Bốn tầng timeout không thể thay thế lẫn nhau

Một request WebFlux đi qua nhiều tầng. Mỗi tầng có mục đích và người sở hữu khác nhau.

| Tầng | Ví dụ | Điều gì hết hạn? | Vai trò |
|---|---|---|---|
| **Ứng dụng producer** | `mono.timeout(Duration.ofMillis(800))` | Không có tín hiệu từ chuỗi upstream trong khoảng cho phép | Quyết định lỗi/fallback theo semantics API |
| **HTTP client của consumer** | Reactor Netty `responseTimeout` hoặc client timeout | Không nhận HTTP response đúng hạn | Bảo vệ tài nguyên và độ trễ phía consumer |
| **Test client / StepVerifier** | `responseTimeout`, `verify(Duration)` | Bản thân test không hoàn tất đúng lúc | Chặn test treo, tạo thông báo thất bại |
| **Test runner / CI** | JUnit timeout, job timeout | Cả bài test hoặc toàn job kéo dài quá mức | Cổng an toàn cuối cùng, không thay assertion nghiệp vụ |

Ví dụ một nhóm có thể chọn **ngân sách minh họa**:

~~~text
Producer chờ dependency:    tối đa 800 ms
Producer tạo response lỗi:  khoảng 1.000 ms từ khi nhận request
Client consumer timeout:    1.500 ms
HTTP test client deadline:  2.500 ms
JUnit test deadline:        10 s
CI job deadline:            giới hạn tổng thể theo pipeline
~~~

Đây là **số minh họa**, không phải giá trị mặc định hoặc khuyến nghị chung. Chúng phải được chọn theo SLO, hạ tầng, phân phối độ trễ và chiến lược retry của hệ thống thật.

Mỗi khoảng cần đủ dư địa cho serialization, scheduling và độ trễ CI, nhưng không được rộng vô hạn. Một test timeout sau 30 giây không chứng minh API đáp ứng SLO 1 giây; ngược lại, test deadline 100 ms trong môi trường CI bận có thể gây flakiness.

## 4. Ví dụ xuyên suốt: Inventory Service dùng WebFlux

Giả sử **Inventory Service** là producer, **Checkout Service** là consumer. Endpoint:

~~~http
GET /api/inventory/SKU-123 HTTP/1.1
Accept: application/json
~~~

Khi dependency trả kết quả đúng hạn:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"sku":"SKU-123","available":true,"quantity":12}
~~~

Khi backend không trả tín hiệu trong thời hạn nghiệp vụ, API của bài thực hành quyết định trả:

~~~http
HTTP/1.1 504 Gateway Timeout
Content-Type: application/json

{"code":"INVENTORY_TIMEOUT","message":"Inventory lookup timed out"}
~~~

**Lưu ý thiết kế:** `504` và mã `INVENTORY_TIMEOUT` ở đây là **cam kết do đội dịch vụ lựa chọn** cho demo. Spring WebFlux không tự biến mọi `Mono.timeout` thành chính response này. Nếu không xử lý lỗi, một `TimeoutException` có thể được framework ánh xạ thành response khác.

Hai contract tách biệt bảo vệ **hành vi thành công** và **hành vi khi hết thời gian chờ**, nhưng không tự chứng minh deadline nội bộ đạt đúng millisecond. Đo thời gian cần kiểm thử riêng với công cụ phù hợp.

## 5. Controller reactive vẫn là code producer thật

Một lớp controller có thể giữ phản hồi ở dạng `Mono`:

~~~java
package com.example.inventory;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {
    private final InventoryService service;

    public InventoryController(InventoryService service) {
        this.service = service;
    }

    @GetMapping("/{sku}")
    public Mono<ResponseEntity<StockResponse>> getStock(
            @PathVariable String sku) {
        return service.findStock(sku)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
~~~

Các kiểu dùng trong ví dụ:

~~~java
package com.example.inventory;

public record StockResponse(
        String sku, boolean available, int quantity) {
}
~~~

`InventoryService` là application service thật trả `Mono<StockResponse>`. Nếu repository không tìm thấy hàng, controller trả `404` bằng `defaultIfEmpty`. Nếu `Mono` phát lỗi, controller trên **chưa bắt lỗi**: xử lý lỗi có thể đặt ở service hoặc `@RestControllerAdvice` theo hợp đồng.

Khi kiểm thử, cần bảo đảm generated test/HTTP test **gọi controller thật** và subscription thực sự làm việc. Không nên để base test tự trả `Mono.just(new StockResponse(...))` thay controller, vì sẽ che mất logic producer.

## 6. Đặt timeout ở service, không chỉ ở bài test

Một service có thể áp dụng thời hạn và chuyển lỗi timeout thành kết quả được HTTP layer hiểu:

~~~java
package com.example.inventory;

import java.time.Duration;
import java.util.concurrent.TimeoutException;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class InventoryService {
    private final InventoryGateway gateway;

    public InventoryService(InventoryGateway gateway) {
        this.gateway = gateway;
    }

    public Mono<StockResponse> findStock(String sku) {
        return gateway.lookup(sku)
                .timeout(Duration.ofMillis(800))
                .onErrorMap(
                    TimeoutException.class,
                    error -> new InventoryTimeoutException(sku, error)
                );
    }
}
~~~

Giả định `InventoryGateway.lookup` trả `Mono<StockResponse>` và `InventoryTimeoutException` là exception nghiệp vụ của demo:

~~~java
package com.example.inventory;

public class InventoryTimeoutException extends RuntimeException {
    public InventoryTimeoutException(String sku, Throwable cause) {
        super("Inventory lookup timed out for " + sku, cause);
    }
}
~~~

Để chuyển exception này sang response HTTP đã cam kết:

~~~java
package com.example.inventory;

import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class InventoryErrorHandler {
    @ExceptionHandler(InventoryTimeoutException.class)
    public ResponseEntity<Map<String, String>> timeout() {
        return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                .body(Map.of(
                    "code", "INVENTORY_TIMEOUT",
                    "message", "Inventory lookup timed out"
                ));
    }
}
~~~

Đây là các lớp **minh họa** trong nội dung bài học, không phải mã đã chạy hoặc được tạo trong dự án. Trong kiến trúc thực, có thể chọn trả `503` hoặc fallback khác; phải giữ nhất quán với contract và các consumer đang hỗ trợ.

### Cảnh báo về Mono.timeout

- `timeout(Duration)` bắt đầu tính theo **subscription**. Với `Mono`, nếu không có tín hiệu trong khoảng đó, operator phát `TimeoutException` và hủy upstream.
- Với `Flux`, timeout mặc định có thể liên quan **khoảng cách giữa các tín hiệu**, không phải một deadline tổng cho toàn luồng. Nếu API cần deadline toàn bộ, phải định nghĩa và kiểm thử rõ.
- Timeout **không bảo đảm** code blocking không hợp tác sẽ dừng ngay lập tức. Việc hủy reactive subscription không tương đương ngắt an toàn mọi thư viện I/O hoặc tiến trình bên ngoài.
- Xử lý `onErrorResume` thành giá trị mặc định có thể khiến consumer hiểu nhầm lỗi thành thành công; khi fallback được sử dụng, contract cần nói rõ.

## 7. Contract Groovy: thành công dù producer dùng Mono

Nếu endpoint thực trả JSON sau khi Mono phát giá trị, contract HTTP vẫn mô tả **HTTP status, header, body**.

Tệp `src/test/resources/contracts/inventory/stock-found.groovy`:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Checkout đọc được tồn kho từ producer reactive'

    request {
        method GET()
        url '/api/inventory/SKU-123'
        headers {
            header('Accept', 'application/json')
        }
    }

    response {
        status OK()
        headers {
            contentType(applicationJson())
        }
        body(
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

**Điểm quan trọng:** trong HTTP response đã hoàn tất, consumer không nhìn thấy object `Mono`. Consumer nhận **status và bytes JSON**. Vì vậy, không cần “viết Mono trong Groovy DSL”. Công cụ generated test phải được nối đúng với Spring WebFlux stack để request **subscribe vào publisher thật**.

### YAML DSL tương đương

~~~yaml
description: Checkout đọc được tồn kho từ producer reactive
name: reactive_stock_found

request:
  method: GET
  url: /api/inventory/SKU-123
  headers:
    Accept: application/json

response:
  status: 200
  headers:
    Content-Type: application/json
  body:
    sku: SKU-123
    available: true
    quantity: 12
~~~

Không đặt cả hai hợp đồng tương đương trong cùng thư mục chỉ để thử syntax nếu chúng tạo trùng generated test/mapping. Chọn một DSL theo chính sách dự án.

## 8. Contract cho timeout phản hồi bằng HTTP 504

Nếu contract API cam kết status lỗi sau khi hết thời gian chờ, có thể viết một hợp đồng **riêng** với request có kịch bản rõ:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    description 'Báo lỗi khi upstream tồn kho không phản hồi'

    request {
        method GET()
        url '/api/inventory/SKU-TIMEOUT'
    }

    response {
        status GATEWAY_TIMEOUT()
        headers {
            contentType(applicationJson())
        }
        body(
            code: 'INVENTORY_TIMEOUT',
            message: 'Inventory lookup timed out'
        )
    }
}
~~~

Nếu phiên bản DSL không hỗ trợ constant `GATEWAY_TIMEOUT()`, hãy dùng status số theo cú pháp được version hỗ trợ, ví dụ `status 504`, rồi kiểm tra generation thực tế.

Một contract YAML tương đương:

~~~yaml
description: Báo lỗi khi upstream tồn kho không phản hồi
name: reactive_inventory_timeout

request:
  method: GET
  url: /api/inventory/SKU-TIMEOUT

response:
  status: 504
  headers:
    Content-Type: application/json
  body:
    code: INVENTORY_TIMEOUT
    message: Inventory lookup timed out
~~~

**Không nên để test thật phải chờ 800 ms hoặc hàng chục giây cho mọi lần chạy** nếu có cách mô phỏng dependency timeout một cách xác định. Với producer verification, base test có thể sắp xếp **gateway test** cho SKU đặc biệt này phát lỗi timeout hoặc chậm có kiểm soát, miễn là **service production vẫn chạy logic timeout/error mapping thật**.

Contract phía trên chủ yếu bảo vệ **HTTP status và error schema**. Nó không trực tiếp khẳng định response xuất hiện trong đúng 800 ms, hay đảm bảo upstream đã được cancel. Cần thêm Reactor/WebFlux tests cho các thuộc tính thời gian.

## 9. WebTestClient: kiểm tra HTTP endpoint reactive

`WebTestClient` là công cụ Spring dùng để gọi/kiểm tra reactive HTTP. Nó có thể gắn vào application context hoặc server đang chạy, tùy mức độ integration test mong muốn.

Ví dụ một bài kiểm thử **WebFlux HTTP riêng**, không phải mã giả generated test của SCC:

~~~java
package com.example.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class InventoryHttpTest {
    @Autowired
    WebTestClient client;

    @Test
    void findsStock() {
        client.get()
                .uri("/api/inventory/SKU-123")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.sku").isEqualTo("SKU-123")
                .jsonPath("$.available").isEqualTo(true)
                .jsonPath("$.quantity").isEqualTo(12);
    }
}
~~~

Ở ví dụ này `exchange()` gửi request và chờ nhận response để assert. Việc trả `Mono` trong controller **không khiến phép kiểm HTTP phải tự gọi `block()` trong production code**.

Phải đảm bảo môi trường có dữ liệu fixture cho SKU-123. Nếu service gọi một dependency thật không ổn định, cần cô lập đúng điểm cắt của dependency mà vẫn giữ controller/service production trong luồng kiểm chứng.

### Không nhầm WebTestClient với Contract Verifier

- `WebTestClient` là công cụ kiểm thử HTTP cụ thể.
- SCC **sinh** test từ Groovy/YAML contract; tùy phiên bản/plugin, test mode có thể tạo test dùng WebTestClient.
- Một WebTestClient test tự viết **không tự động** đồng nghĩa với generated contract test đã chạy.

Trong CI cần xác nhận cả hợp đồng được phát hiện và generated tests được thực thi.

## 10. Kết nối Contract Verifier với WebFlux đúng test mode

Một dự án WebFlux thường sử dụng chế độ generated test phù hợp với **WebTestClient** (nếu phiên bản SCC đang dùng hỗ trợ), không dùng MockMvc một cách máy móc cho stack reactive.

Ví dụ cấu hình Maven plugin minh họa:

~~~xml
<plugin>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-contract-maven-plugin</artifactId>
    <version>CONTRACT_PLUGIN_VERSION</version>
    <extensions>true</extensions>
    <configuration>
        <testMode>WEBTESTCLIENT</testMode>
        <baseClassForTests>
            com.example.inventory.ReactiveContractTestBase
        </baseClassForTests>
    </configuration>
</plugin>
~~~

`CONTRACT_PLUGIN_VERSION` là placeholder cần thay bằng **phiên bản có thật** tương thích với Spring Boot và Spring Cloud Release Train. Cú pháp và enum `WEBTESTCLIENT` phải được đối chiếu với tài liệu **đúng phiên bản SCC**, rồi xác nhận generated source thực tế.

Ví dụ base test **khởi tạo context WebFlux thật**:

~~~java
package com.example.inventory;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
public abstract class ReactiveContractTestBase {
    // Chuẩn bị test fixture tại điểm cắt dependency.
    // Kiểm tra generated test để biết cần inject/bind WebTestClient
    // hay cấu hình adapter nào theo test mode/plugin version.
}
~~~

Ví dụ này chủ yếu minh họa **base class và phạm vi test**. Đừng giả định nó đủ chạy với mọi generated test: một số phiên bản/mode yêu cầu biến WebTestClient, khởi tạo adapter, thiết lập base URL hoặc một phương thức chuẩn bị riêng. Sau generation, **đọc generated class** và bổ sung chính xác thứ mà nó cần.

Không dùng base test tự dựng `Mono.just(responseMau)` để thay hành vi producer cần kiểm chứng; như vậy test dễ xanh giả.

## 11. Timeout của WebTestClient: deadline của công cụ test

Khi test chờ HTTP response, có thể cấu hình timeout cho WebTestClient. Ví dụ client **gắn vào server**:

~~~java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(3))
        .build();
~~~

Trong ví dụ cần import `java.time.Duration` và `org.springframework.test.web.reactive.server.WebTestClient`. `localhost:8080` chỉ là địa chỉ minh họa; trong Spring Boot test với cổng ngẫu nhiên, phải lấy **port thực tế** từ môi trường test.

Có thể cấu hình timeout khi xây client từ context tùy API binding được dùng:

~~~java
WebTestClient client = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .responseTimeout(Duration.ofSeconds(3))
        .build();
~~~

Ở đoạn này `context` là `ApplicationContext` đã khởi tạo Spring WebFlux. Cách gắn vào context không kiểm tra web server thật, nhưng vẫn dùng handler chain ở phạm vi context.

**Tách đúng ý nghĩa:** nếu `WebTestClient` timeout sau 3 giây, đó là **thất bại công cụ test khi chờ response**, chưa chắc producer đã trả HTTP 504. Muốn xác nhận contract `504 INVENTORY_TIMEOUT`, producer phải **tự chuyển upstream timeout thành HTTP response 504** trước khi test client hết thời gian chờ.

Không đặt test timeout ngắn hơn deadline nghiệp vụ một cách vô tình: test client có thể ngừng chờ trước khi producer kịp gửi response lỗi đã cam kết.

## 12. StepVerifier: kiểm tra tín hiệu Publisher trực tiếp

`reactor-test` cung cấp `StepVerifier` để kiểm tra chuỗi reactive bên dưới tầng HTTP. Đây là nơi phù hợp để xác minh **onNext, onComplete, onError**, còn WebTestClient kiểm tra giao diện HTTP.

Ví dụ service trả `Mono<StockResponse>`:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class InventoryPublisherTest {
    @Test
    void emitsOneStockAndCompletes() {
        Mono<StockResponse> result = Mono.just(
            new StockResponse("SKU-123", true, 12)
        );

        StepVerifier.create(result)
                .expectNextMatches(stock ->
                    stock.sku().equals("SKU-123")
                    && stock.available()
                    && stock.quantity() == 12
                )
                .verifyComplete();
    }
}
~~~

**Lưu ý về phạm vi:** ví dụ trên minh họa API `StepVerifier`. Nó đang kiểm tra một publisher giả do test tạo ra, **không phải InventoryService production**. Khi cần kiểm tra service thật, phải gọi `service.findStock(...)` trên service thật với dependency test ở điểm cắt phù hợp.

Một ví dụ giới hạn toàn bộ thời gian chờ của phép kiểm:

~~~java
StepVerifier.create(service.findStock("SKU-123"))
        .expectNextMatches(stock -> stock.available())
        .expectComplete()
        .verify(Duration.ofSeconds(3));
~~~

`verify(Duration)` giúp test không chờ vô hạn. Đây là **deadline của bài test**; nó không đặt ra semantics HTTP 504 hay thay đổi logic timeout của producer.

### Mono rỗng và lỗi là hai kết quả khác nhau

~~~java
StepVerifier.create(Mono.<StockResponse>empty())
        .verifyComplete();

StepVerifier.create(Mono.<StockResponse>error(
            new IllegalStateException("backend unavailable")))
        .expectError(IllegalStateException.class)
        .verify();
~~~

Một Mono hoàn tất rỗng có thể được controller chuyển thành 404; Mono phát lỗi có thể thành 5xx hoặc được handler ánh xạ sang lỗi có cấu trúc. Test cần phân biệt **không tìm thấy**, **upstream lỗi** và **upstream timeout** theo hợp đồng.

## 13. Virtual time: kiểm thử thời gian dài mà không phải chờ thật

Kiểm tra bằng `Thread.sleep(5_000)` làm bộ test chậm và dễ lỗi trên CI. Reactor `StepVerifier.withVirtualTime` cho phép điều khiển **thời gian ảo** đối với các operator dùng scheduler Reactor phù hợp.

Ví dụ publisher chỉ phát sau 30 phút:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofMinutes(30))
                .map(tick -> "READY")
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(29))
    .thenAwait(Duration.ofMinutes(1))
    .expectNext("READY")
    .verifyComplete();
~~~

Đoạn này có thể được kiểm tra nhanh vì scheduler chạy theo thời gian ảo, **không ngủ 30 phút thật**. Cần tạo publisher **bên trong Supplier** đưa cho `withVirtualTime` để các timer/operator lấy đúng scheduler ảo.

### Kiểm thử timeout khi upstream không bao giờ phát tín hiệu

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(
        () -> Mono.<String>never()
                .timeout(Duration.ofSeconds(3))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
~~~

Bài test này xác nhận **Reactor timeout operator** phát lỗi khi không có tín hiệu. Nó chưa chứng minh tầng HTTP trả đúng status 504; phải có test service/handler/WebTestClient tương ứng.

### Những giới hạn của virtual time

- Chỉ có tác dụng với những thao tác thời gian dùng **scheduler được virtualize** và được tạo đúng thời điểm.
- Không thể tự làm nhanh **HTTP socket**, database, broker hoặc thư viện blocking I/O hoạt động theo đồng hồ thật.
- Timer tạo trước khi virtual scheduler được kích hoạt có thể vẫn dùng scheduler thật.
- Không nên chạy bừa các test virtual time song song nếu có thiết lập scheduler toàn cục gây tương tác; cần kiểm soát cấu hình test.
- `expectNoEvent` ở đầu chuỗi cần tính đến **subscription**; dùng `expectSubscription()` trước khi yêu cầu không có tín hiệu.

**Nguyên tắc:** virtual time dùng để kiểm thử **logic thời gian của Reactor**; WebTestClient/integration tests dùng để kiểm tra **HTTP contract và serialization thực tế**.

## 14. Test timeout với gateway điều khiển được

Để kiểm tra service production với dependency không phản hồi, có thể kiểm soát **gateway** thay vì fake controller hay mock cả service.

Giả sử `InventoryGateway` là port:

~~~java
package com.example.inventory;

import reactor.core.publisher.Mono;

public interface InventoryGateway {
    Mono<StockResponse> lookup(String sku);
}
~~~

Một unit test tạo service thật và gateway test trả publisher không bao giờ hoàn tất:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class InventoryServiceTimeoutTest {
    @Test
    void turnsUpstreamTimeoutIntoDomainError() {
        InventoryGateway silentGateway =
                sku -> Mono.<StockResponse>never();

        InventoryService service = new InventoryService(silentGateway);

        StepVerifier.withVirtualTime(
                () -> service.findStock("SKU-TIMEOUT")
            )
            .expectSubscription()
            .thenAwait(Duration.ofMillis(800))
            .expectError(InventoryTimeoutException.class)
            .verify();
    }
}
~~~

Trong ví dụ, **`InventoryService` là class production thật**, nên `timeout` và `onErrorMap` trong service thực sự được kiểm chứng. Chỉ gateway **được điều khiển** để không trả tín hiệu.

Tuy nhiên, nếu `InventoryService.findStock(...)` thực hiện thao tác tạo timer ngay lúc gọi chứ không ở subscription, hoặc scheduler đã được cố định bên ngoài, cần bảo đảm publisher/timer được tạo bên trong Supplier khi dùng virtual time. Đó là lý do test sử dụng `() -> service.findStock(...)` thay vì tạo `Mono` trước.

Một HTTP contract test khác cần cho request `SKU-TIMEOUT` đi qua **controller production + service production + error handler**, sử dụng gateway test deterministic. Đây là điểm cắt hợp lý; không mock controller trả sẵn `504` vì sẽ bỏ qua logic xử lý timeout mà contract muốn bảo vệ.

## 15. Reactive tác vụ blocking: timeout không sửa được blocking code

Reactive controller không làm một thao tác blocking trở nên non-blocking chỉ vì method trả `Mono`.

Ví dụ **không nên** gọi trực tiếp một API blocking trên event loop:

~~~java
@GetMapping("/blocking-example")
public Mono<String> endpoint() {
    String result = legacyClient.callBlocking(); // Chặn thread đang xử lý
    return Mono.just(result);
}
~~~

Nếu cần tích hợp thư viện legacy blocking, một cách cô lập là:

~~~java
@GetMapping("/bounded-elastic-example")
public Mono<String> endpoint() {
    return Mono.fromCallable(() -> legacyClient.callBlocking())
            .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
}
~~~

`boundedElastic` là nơi phù hợp hơn cho một số tác vụ blocking không thể tránh, nhưng **không thay thế timeout/cancellation của thư viện blocking** và không làm ứng dụng vô hạn tài nguyên. Nên ưu tiên driver/client thực sự non-blocking khi có thể.

Trong kiểm thử:

- Đừng dùng `Thread.sleep` trong handler/test để “giả lập reactive” rồi kết luận ứng dụng hoạt động không chặn.
- Không gọi `block()` trong production event-loop; trong một số test cấp biên, phép chờ có giới hạn có thể dùng để nhận kết quả nhưng không nên thay kiểm tra tín hiệu.
- Với I/O blocking, thiết lập **timeout của chính client/driver** và kiểm chứng đường lỗi; Reactor timeout chỉ tác động ở tầng Publisher.
- Tách test thời gian thực ở mức integration khỏi test dùng virtual time của Reactor.

## 16. Cancellation và cleanup khi client ngừng chờ

Một subscriber có thể hủy trước khi upstream trả kết quả, ví dụ client đóng kết nối hoặc operator `timeout` ngắt chuỗi.

Một test thuần Reactor có thể kiểm tra callback hủy:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

AtomicBoolean cancelled = new AtomicBoolean(false);

Mono<String> pending = Mono.<String>never()
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(pending)
        .expectSubscription()
        .thenCancel()
        .verify(Duration.ofSeconds(2));

org.assertj.core.api.Assertions
        .assertThat(cancelled.get())
        .isTrue();
~~~

Đây là **unit test cơ chế cancellation**, không phải bằng chứng HTTP client đóng kết nối đã hủy được mọi thao tác I/O thật. Với database call, broker hoặc thư viện blocking, phải kiểm chứng cơ chế hủy của driver thực tế khi tài nguyên/chi phí là phần quan trọng của hệ thống.

Trong ứng dụng có retry, cancellation càng quan trọng: một request đã hết deadline không nên tiếp tục tạo retry hoặc tác vụ nền không có chủ sở hữu. Nhưng nếu việc xử lý đã khởi tạo một **background job độc lập có ID**, ngữ nghĩa hủy có thể khác; phải được thiết kế riêng.

## 17. Retry, backoff và timeout: chọn thứ tự có chủ đích

Reactive pipeline thường có các operator như `timeout`, `retryWhen`, `onErrorResume`. **Thứ tự operator thay đổi nghĩa**.

Ví dụ:

~~~java
Mono<StockResponse> result = gateway.lookup("SKU-123")
        .timeout(Duration.ofMillis(300))
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                2, Duration.ofMillis(100)
            )
        );
~~~

Trong pipeline này, timeout 300 ms có thể xảy ra **trên từng subscription/attempt** rồi retry; toàn bộ thời gian có thể lớn hơn 300 ms do nhiều lần thử và backoff. Nếu muốn deadline tổng, cần kiểm soát ở tầng bao ngoài phù hợp:

~~~java
Mono<StockResponse> result = gateway.lookup("SKU-123")
        .retryWhen(
            reactor.util.retry.Retry.backoff(
                2, Duration.ofMillis(100)
            )
        )
        .timeout(Duration.ofSeconds(1));
~~~

Hai đoạn trên là **ví dụ về thứ tự operator**, chưa phải chiến lược retry hoàn chỉnh: `retryWhen` như viết có thể retry **mọi lỗi**, kể cả lỗi không nên retry, trừ khi có `filter`. Trong hệ thống thật phải giới hạn loại lỗi tạm thời, số lần retry, backoff/jitter, ngân sách thời gian và idempotency.

Bài test cần xác nhận cả:

- Số lần gateway được gọi khi gặp lỗi có thể retry.
- Tổng deadline không bị vượt quá ngưỡng cam kết.
- Lỗi 4xx hoặc lỗi validation không bị retry không cần thiết.
- Fallback không che giấu timeout thành response thành công sai semantics.

Nếu consumer timeout trước khi producer hoàn tất retry, consumer có thể thấy lỗi mạng chứ không thấy HTTP status được contract hứa. Các ngân sách phải được thiết kế nhất quán.

## 18. HTTP bất đồng bộ không giống background job trả 202

Có hai mô hình cần phân biệt:

**Mô hình A — Request HTTP chờ kết quả của Mono:**

~~~text
GET /api/inventory/SKU-123
    -> Mono truy vấn dữ liệu
    -> HTTP 200 khi có kết quả, hoặc lỗi/timeout khi không có
~~~

Ở đây contract có thể mô tả response 200/404/504. Thời gian HTTP request còn mở cho đến khi producer hoàn tất hoặc bị kết thúc.

**Mô hình B — HTTP nhận yêu cầu và khởi tạo tác vụ nền:**

~~~text
POST /api/reports
    -> HTTP 202 Accepted + {"jobId":"JOB-1001","status":"PENDING"}
    -> tác vụ được xử lý sau
GET /api/reports/JOB-1001
    -> 200 + {"status":"READY",...} khi hoàn tất
~~~

Với mô hình B, `202 Accepted` **không có nghĩa tác vụ đã hoàn tất**. Hợp đồng cần tách:

1. API tạo job, trả `202` cùng ID và đường dẫn theo dõi.
2. API đọc trạng thái job (pending/running/ready/failed).
3. Nếu có callback/message khi hoàn tất, contract cho message hoặc callback tương ứng.

Không dùng generated test nhận 202 để tuyên bố toàn bộ background job đã thành công. Kiểm thử job completion cần tạo điều kiện chờ có giới hạn, kiểm tra trạng thái cuối cùng và cleanup sau test.

## 19. Polling và điều kiện hoàn tất eventual

Nếu consumer phải polling cho đến khi job READY, đừng dùng sleep cố định rồi mong dữ liệu đã sẵn sàng:

~~~java
// Không nên dùng cách này làm chiến lược đồng bộ chính:
Thread.sleep(2000);
// Sau đó mới hỏi trạng thái; CI chậm có thể vẫn chưa xong.
~~~

Một bài integration test có thể sử dụng **Awaitility** để chờ đến khi một điều kiện cuối cùng đạt, với deadline rõ ràng:

~~~java
import static org.awaitility.Awaitility.await;
import java.time.Duration;

// Minh họa: getStatus gọi endpoint/API thật để đọc trạng thái job.
await()
    .atMost(Duration.ofSeconds(5))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        org.assertj.core.api.Assertions.assertThat(
            reportClient.getStatus("JOB-1001")
        ).isEqualTo("READY");
    });
~~~

Phương thức `reportClient.getStatus` ở đây là **API giả định của consumer test**; nếu client trả `Mono`, cần dùng cơ chế tích hợp test phù hợp, tránh gọi `block()` trên event loop. Awaitility hữu ích ở **ranh giới integration** khi trạng thái thay đổi thật theo thời gian, còn `StepVerifier.withVirtualTime` phù hợp hơn cho **logic Reactor timer** có thể điều khiển scheduler.

Khi polling, phải xem xét:

- Có **timeout cuối cùng** rõ ràng.
- Khoảng polling phù hợp, tránh gây tải quá cao.
- Job ID thuộc đúng test, không chia sẻ trạng thái mơ hồ.
- Có cleanup và log trạng thái cuối khi thất bại.
- Cần tách trạng thái `FAILED` khỏi việc tiếp tục polling vô ích.

## 20. Streaming Flux và SSE: hợp đồng HTTP thường chưa đủ

Một endpoint có thể phát stream:

~~~java
@GetMapping(
    path = "/api/stock/events",
    produces = org.springframework.http.MediaType.TEXT_EVENT_STREAM_VALUE
)
public reactor.core.publisher.Flux<StockEvent> events() {
    return eventService.stream();
}
~~~

Với **Server-Sent Events (SSE)** hoặc `Flux` không kết thúc, response không phải một JSON object hoàn chỉnh như endpoint `GET /api/inventory/SKU-123`.

Trong trường hợp này:

- Contract HTTP thông thường có thể mô tả phần giao thức phù hợp, nhưng **không tự chứng minh** chu kỳ phát event, khoảng ngắt, backpressure, cancellation hay vô hạn stream.
- Test bằng `WebTestClient` có thể lấy body dạng `Flux` rồi dùng `StepVerifier` kiểm tra số event đầu tiên và hủy có chủ đích.
- Phải đặt **giới hạn số event hoặc thời gian** khi test luồng không kết thúc.
- Content-Type `text/event-stream` và encoding event cần được kiểm tra riêng.
- Nếu producer thay đổi schema của event, cần contract message/event phù hợp cùng consumer test xử lý event thực tế.

Ví dụ ý tưởng kiểm tra ba event đầu tiên:

~~~java
Flux<StockEvent> events = client.get()
        .uri("/api/stock/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(StockEvent.class)
        .getResponseBody();

StepVerifier.create(events)
        .expectNextCount(3)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
~~~

Đoạn minh họa giả định `client` là WebTestClient đã cấu hình và endpoint phát ít nhất ba event trong 5 giây. Cần bổ sung assertion về **nội dung/sự kiện** nếu consumer phụ thuộc chúng; chỉ đếm event là chưa đủ kiểm chứng schema.

Nếu stream không bao giờ phát event, test sẽ hết `verify(Duration)` thay vì treo vô hạn. Không gọi `verifyComplete()` cho stream cố ý không kết thúc.

## 21. Contract messaging bất đồng bộ: kích hoạt đường production thật

Spring Cloud Contract hỗ trợ hợp đồng message với trigger và output message. Ví dụ Inventory Service phát sự kiện tồn kho sau khi xử lý:

~~~groovy
import org.springframework.cloud.contract.spec.Contract

Contract.make {
    label 'inventoryChanged'

    input {
        triggeredBy('triggerInventoryChanged()')
    }

    outputMessage {
        sentTo('inventory.events')
        body(
            eventType: 'InventoryChanged',
            sku: 'SKU-123',
            available: true,
            quantity: 12
        )
    }
}
~~~

Trong producer test, `triggerInventoryChanged()` phải được cung cấp ở base class/test support. **Nó nên gọi use case production thực sự làm phát message**, không tự gửi một JSON đúng mẫu vào test sink rồi báo PASS.

Vì output message có thể xuất hiện sau một khoảng delay, cần thiết lập:

- Messaging test infrastructure phù hợp: Spring Cloud Stream test binder, broker test hoặc adapter mà SCC version hỗ trợ.
- Điều kiện nhận message với **timeout hữu hạn** thay vì chờ vô hạn.
- Cách phân biệt event đúng tình huống bằng key/correlation ID, không đọc nhầm message của test khác.
- Cleanup subscription/consumer giữa các test.
- Bằng chứng generated test thật sự quan sát được message do production code phát.

Một contract message có body đúng **không tự kiểm tra** broker production, độ trễ giao hàng, xử lý duplicate hoặc retry. Những thuộc tính đó cần test messaging/integration và theo dõi vận hành tương ứng.

## 22. Stub Runner và trường hợp consumer nhận response chậm

Khi producer tạo stub, Checkout Service có thể chạy client thật với Stub Runner để kiểm tra request/response contract. Tuy nhiên **stub thường trả response mẫu nhanh**; điều đó không chứng minh consumer xử lý đúng latency cao.

Có thể thiết kế **hai nhóm consumer test**:

| Nhóm | Công cụ | Điều cần kiểm tra |
|---|---|---|
| **Contract compatibility** | Stub Runner và stub ứng viên do producer sinh | Client gửi request, giải mã đúng status/header/body/schema |
| **Resilience/latency** | WireMock delay/fault hoặc test HTTP server kiểm soát được | Client áp dụng timeout, retry, fallback, cancellation đúng |

Ví dụ một WireMock mapping **riêng cho bài test resilience**, không phải cam kết rằng SCC DSL tự sinh delay:

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.*;

stubFor(get(urlEqualTo("/api/inventory/SKU-SLOW"))
    .willReturn(aResponse()
        .withStatus(200)
        .withHeader("Content-Type", "application/json")
        .withBody("{\"sku\":\"SKU-SLOW\",\"available\":true,\"quantity\":1}")
        .withFixedDelay(2500)));
~~~

Nếu consumer được thiết kế timeout sau 1.500 ms, request tới stub chậm 2.500 ms phải được test để bảo đảm kết quả lỗi/fallback phù hợp. Đây là **test kiểm tra ứng xử khi chậm**, không thay cho producer verification.

**Chú ý:** `withFixedDelay` tạo delay theo **thời gian thực**, phù hợp với một số integration test nhưng có thể chậm/flaky trên CI. Chỉ dùng cho số ít bài test cần kiểm tra timeout thật, với dư địa thời gian và môi trường ổn định. Các rule nội bộ nên thử bằng `StepVerifier.withVirtualTime` khi được.

Không tự sửa JAR stub ứng viên đã sinh để thêm delay rồi vẫn gọi đó là artifact nguyên bản của producer. Giữ artifact contract và stub resilience riêng, ghi rõ mục đích từng loại test.

## 23. Đặt timeout ở HTTP client consumer

Một WebClient sử dụng Reactor Netty có thể cấu hình response timeout ở tầng HTTP client:

~~~java
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
        .responseTimeout(Duration.ofMillis(1500));

WebClient webClient = WebClient.builder()
        .clientConnector(new ReactorClientHttpConnector(httpClient))
        .baseUrl("http://localhost:8081")
        .build();
~~~

`http://localhost:8081` là URL minh họa nơi stub/test server có thể lắng nghe, không phải địa chỉ môi trường thật. Với Stub Runner, cần lấy host/port thực tế theo cấu hình test.

Cần phân biệt:

- `responseTimeout` ở Reactor Netty có semantics của **network response read/response timeout**, không nhất thiết là **deadline tổng của toàn quy trình**.
- `Mono.timeout(Duration)` trên chuỗi `WebClient.retrieve().bodyToMono(...)` áp thời hạn ở tầng publisher, tính từ subscription theo semantics Reactor.
- **Connect timeout**, pool acquisition timeout, DNS resolution và các giai đoạn khác có chính sách riêng.
- Nếu client có retry, phải xác định timeout **mỗi attempt** hay **toàn bộ call**. Kiểm thử cùng cấu hình thực tế, không chỉ ví dụ đơn lẻ.

Test consumer cần assert **kiểu lỗi hoặc fallback nghiệp vụ** mà ứng dụng xử lý. Không nên gắn cứng message exception Netty không thuộc public API; thông báo chi tiết có thể khác giữa phiên bản/thư viện.

## 24. Timeout không đồng nghĩa lỗi 504

Các trường hợp hay bị đồng nhất:

| Điều xảy ra | Client/consumer quan sát | Có phải HTTP 504 từ producer? |
|---|---|---|
| Producer bắt upstream timeout và trả HTTP 504 JSON | Nhận response `504` có mã lỗi | **Có**, theo contract |
| WebTestClient tự hết `responseTimeout` trước khi producer phản hồi | Test thất bại vì không nhận response | **Không** |
| Consumer WebClient timeout khi chờ | Client nhận error signal hoặc fallback | **Không nhất thiết** |
| JUnit timeout hủy cả test | Test runner báo quá hạn | **Không** |
| CI job timeout | Pipeline bị hủy | **Không** |
| Producer trả 202 và xử lý job sau | Client nhận response `202` sớm | Không phải timeout |

Nếu hợp đồng yêu cầu `504 INVENTORY_TIMEOUT`, phải kiểm tra producer **phát được chính HTTP response đó**. Một test chỉ xác nhận client timeout không chứng minh producer đã thực hiện error mapping.

## 25. Kiểm thử thời gian thực và test virtual nên phân tầng

Không nên dồn mọi thuộc tính thời gian vào một bài end-to-end nặng.

| Loại kiểm thử | Ví dụ | Cách chờ | Mục tiêu |
|---|---|---|---|
| **Reactor unit test** | `timeout`, `retryWhen`, `doOnCancel` | `StepVerifier.withVirtualTime` khi thích hợp | Logic thời gian và tín hiệu chính xác |
| **Service integration test** | Gateway chậm hoặc `Mono.never` | Virtual time nếu adapter hỗ trợ, hoặc chờ có giới hạn | Service phát error/fallback đúng |
| **HTTP producer test** | WebFlux controller + error handler | WebTestClient với responseTimeout đủ lớn | Status/header/body đúng contract |
| **Generated SCC producer test** | Groovy/YAML → generated test | Theo plugin/test mode, deadline runner | Producer đáp ứng hợp đồng |
| **Consumer contract test** | Stub Runner + client thật | Client test timeout có giới hạn | Tương thích request/response |
| **Resilience test** | WireMock fixed delay/fault | Thời gian thật có kiểm soát | Consumer chịu được latency/cancellation |
| **E2E/observability** | Broker, database, tracing | Hạn chờ theo SLO | Tương tác production-like và vận hành |

Một test nhanh bằng virtual time không thay thế việc xác minh **I/O thật**; một test HTTP chờ thật không thay thế việc kiểm tra operator/retry bằng tín hiệu xác định.

## 26. Chống flakiness khi test bất đồng bộ

Những nguyên tắc thực hành:

1. **Không dùng sleep cố định** để đợi sự kiện nếu có thể chờ điều kiện hoặc dùng virtual time.
2. **Không trộn timeout quá sát nhau**: test client cần đủ dư địa để producer phát response timeout nghiệp vụ.
3. **Giới hạn mọi phép chờ**: `verify(Duration)`, `responseTimeout`, Awaitility `atMost`, JUnit/CI job timeout.
4. **Cô lập tài nguyên giữa test**: correlation ID, queue/topic, subscription, test DB, scheduler.
5. **Không dựa vào thứ tự thực thi**: các publisher có thể khác thời điểm phát; đừng giả định bất đồng bộ có thứ tự toàn cục.
6. **Không phụ thuộc wall-clock nếu không cần**: dùng `Clock` inject, virtual scheduler hoặc fixture cố định.
7. **Không để test phát sinh tác vụ nền không cleanup**: cancellation và shutdown có thể quan trọng hơn kết quả happy path.
8. **Không giấu lỗi bằng retry vô hạn**: giới hạn attempt, phân loại retryable và bảo vệ deadline.
9. **Log đủ ngữ cảnh**: request/contract ID, correlation ID, thời điểm bắt đầu/kết thúc và timeout layer.
10. **Kiểm tra kết quả thật sự xảy ra**: assert tín hiệu cuối, HTTP status/body hoặc message đã được quan sát, không chỉ “job được submit”.

Với CI tải cao, không tùy tiện tăng timeout gấp hàng chục lần để “hết đỏ”; trước hết phân loại **flakiness do test**, **chậm do dependency** hay **regression latency của producer**.

## 27. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| StepVerifier test treo | Không có completion/error hoặc thiếu deadline | Dùng `verify(Duration)` và assert đúng terminal signal |
| Test không kích hoạt truy vấn | Publisher được tạo nhưng không subscribe | Dùng StepVerifier/WebTestClient hoặc subscriber có kiểm soát |
| Virtual time vẫn chạy nhiều giây/phút | Publisher/timer tạo trước supplier, scheduler không virtualized hoặc có I/O thật | Tạo publisher trong supplier; tách I/O integration test |
| HTTP test nhận timeout thay vì 504 | Test client hết hạn trước khi producer phát response lỗi | Điều chỉnh ngân sách; test error mapping của producer |
| Producer trả 500 thay vì timeout contract | `TimeoutException` chưa được ánh xạ | Xem `onErrorMap`/`@RestControllerAdvice` và generated test |
| Test xanh với `Mono.just(...)` do base tự trả | Mock/fake chính behavior producer | Cho test đi qua controller/service production |
| Consumer test xanh nhưng WebClient lỗi khi chậm | Stub bình thường trả ngay | Thêm test WireMock delay và cấu hình timeout client |
| Flux test không bao giờ hoàn tất | Stream có chủ đích không kết thúc | Assert vài phần tử rồi `thenCancel` |
| Retry làm request kéo dài quá ngân sách | Timeout đặt trong retry hoặc không có deadline tổng | Kiểm tra thứ tự operator, số attempt, timeout toàn call |
| CI lúc xanh lúc đỏ | Sleep cố định, tài nguyên dùng chung, load/scheduler biến động | Điều kiện eventual + deadline, isolation, virtual time |
| Test message không nhận event | Trigger không đi qua production flow hoặc test binder/broker sai | Kiểm tra trigger, destination, serialization, consumer subscription |
| Cancel không dừng blocking I/O | Driver/library không hỗ trợ cooperative cancellation | Cấu hình timeout I/O, giới hạn tài nguyên, test riêng driver |
| Build xanh nhưng không có generated tests | Plugin không tìm contract hoặc test task bị skip | Kiểm tra generated source, test count và pipeline flags |
| Consumer dùng stub cũ | Version/cache không trỏ artifact ứng viên | Ghim group/artifact/version/classifier và kiểm tra mapping |

## 28. Đưa các cổng reactive/contract vào CI

~~~mermaid
flowchart TD
    A["PR thay code WebFlux, contract hoặc timeout"] --> B["Unit tests StepVerifier / virtual time"]
    B --> C{"Đúng tín hiệu và deadline?"}
    C -- "Không" --> X["Chặn merge"]
    C -- "Có" --> D["Generate và chạy SCC producer tests"]
    D --> E{"HTTP/message contract đạt?"}
    E -- "Không" --> X
    E -- "Có" --> F["Đóng gói stub ứng viên"]
    F --> G["Consumer tests qua Stub Runner"]
    G --> H{"Client xử lý request/response?"}
    H -- "Không" --> X
    H -- "Có" --> I["Resilience tests chọn lọc: delay/fault/cancel"]
    I --> J{"Đạt?"}
    J -- "Không" --> X
    J -- "Có" --> K["Qua cổng tương thích; tiếp tục release"]
~~~

Lệnh tham khảo cho dự án đã tích hợp plugin SCC:

~~~bash
# Maven: sinh, compile, chạy tests và đóng gói theo cấu hình build.
./mvnw clean verify

# Gradle: chạy generated tests nếu plugin đã nối đúng task.
./gradlew clean test
~~~

Tên task, vị trí generated source và tên artifact có thể thay đổi theo phiên bản/plugin. Trên Windows dùng wrapper tương ứng `mvnw.cmd` hoặc `gradlew.bat`.

CI cần lưu:

- Tên contract đã được phát hiện và **số generated tests thực sự chạy**.
- Phiên bản Spring Boot/Spring Cloud/Contract, JDK, test mode.
- Kết quả test Reactor với timeout, retry và cancellation ở các case quan trọng.
- Mã lỗi/stage khi HTTP test thất bại: app 504, client timeout hay runner timeout.
- Group, artifact, version, classifier và commit của **stub ứng viên**.
- Consumer test report với client thật, không gọi nhầm stub production cũ.
- Phân loại test virtual và test thời gian thực để kiểm soát độ ổn định.

Không kết luận pipeline có tính tương thích chỉ từ “build xanh” hoặc một mock luôn trả response mẫu. Producer và consumer phải được kiểm chứng bằng **các đoạn code thật thuộc phạm vi cam kết**.

## 29. Bài thực hành: timeout theo ba lớp

**Bối cảnh:** Inventory Service có API WebFlux `GET /api/inventory/{sku}`; Checkout Service gọi endpoint này. Service lấy dữ liệu từ một gateway reactive.

### Vòng A — Contract HTTP thành công

1. Viết Groovy hoặc YAML contract cho SKU-123 trả `200` với `available:true` và `quantity:12`.
2. Tạo controller `Mono<ResponseEntity<StockResponse>>`.
3. Cấu hình generated tests với test mode WebFlux phù hợp; base class gọi controller thật.
4. Chạy producer verification, kiểm tra generated source và test report.
5. Đóng gói stub ứng viên và chạy Checkout client test với Stub Runner.

**Kết quả mong đợi:** producer và consumer hiểu cùng JSON schema.

### Vòng B — Thời gian chờ ở service

1. Đặt `timeout(Duration.ofMillis(800))` trong service production, ánh xạ timeout sang `InventoryTimeoutException`.
2. Tạo gateway test trả `Mono.never()` (đây là dependency được cô lập, không phải fake service).
3. Dùng `StepVerifier.withVirtualTime` kiểm tra sau 800 ms ảo có error đúng loại.
4. Dùng WebTestClient/integration test kiểm tra error handler trả `504 INVENTORY_TIMEOUT`.
5. Viết contract HTTP riêng cho lỗi timeout với tình huống test data xác định.

**Kết quả mong đợi:** phân biệt được “service tạo lỗi timeout” và “HTTP trả đúng error contract”.

### Vòng C — Consumer có deadline riêng

1. Cấu hình WebClient của Checkout có response timeout phù hợp.
2. Dùng stub ứng viên để kiểm tra schema bình thường.
3. Tạo test WireMock delay riêng (ví dụ 2,5 giây) vượt client deadline 1,5 giây.
4. Assert client phát error/fallback đúng và không retry vô hạn.
5. So sánh với kịch bản producer tự trả 504; hai tình huống không giống nhau.

**Kết quả mong đợi:** consumer xử lý được cả response lỗi công khai và lỗi transport/timeout ở phía mình.

### Vòng D — Flux không kết thúc và cleanup

1. Tạo luồng sự kiện stock dạng `Flux<StockEvent>`.
2. Dùng WebTestClient lấy `Flux` event, `StepVerifier` kiểm tra vài phần tử.
3. Gọi `thenCancel` và xác nhận không treo test.
4. Kiểm tra cleanup/cancellation ở adapter nếu đó là yêu cầu quan trọng.
5. Đưa kết quả của các vòng vào CI.

**Bằng chứng nộp bài:** contracts HTTP, code WebFlux service/controller, generated producer test report, StepVerifier virtual-time test, test WebTestClient status 504, stub coordinate ứng viên, consumer test với delay và log cleanup.

## 30. Checklist trước khi hợp nhất

- [ ] Controller reactive trả đúng `Mono`/`Flux` và generated test thực sự subscribe/gọi implementation.
- [ ] Contract HTTP mô tả status/header/body mà consumer thấy, không nhầm với type Reactor nội bộ.
- [ ] Đã phân biệt upstream timeout, client timeout, test deadline và CI job timeout.
- [ ] Business timeout được ánh xạ sang response theo API contract khi cần.
- [ ] Test client deadline có đủ dư địa để nhận lỗi từ producer, không kết thúc quá sớm.
- [ ] Có StepVerifier tests cho complete, error, timeout và cancellation quan trọng.
- [ ] Virtual-time publisher/timer được tạo **trong Supplier** để lấy đúng scheduler ảo.
- [ ] Không dùng virtual time để giả định network/broker/blocking I/O đã được tăng tốc.
- [ ] Không dùng `Thread.sleep` làm phương pháp đồng bộ chủ đạo.
- [ ] Tác vụ nền 202 có contract tạo job và contract theo dõi/trạng thái hoàn tất khi cần.
- [ ] Flux/SSE không kết thúc được test bằng giới hạn event và `thenCancel`.
- [ ] Base test không mock chính controller/service logic mà contract bảo vệ.
- [ ] Messaging contract đi qua production trigger, có chờ hữu hạn và event correlation.
- [ ] Stub Runner dùng artifact ứng viên, không mặc định giả lập được latency thực.
- [ ] Consumer có test delay/transport timeout và fallback riêng.
- [ ] CI xác nhận số generated tests > 0, lưu version/commit, phân loại lỗi timeout rõ ràng.

## 31. Câu hỏi tự kiểm tra

**1. Vì sao tạo `Mono` nhưng không subscribe chưa chứng minh tác vụ đã chạy?**

Vì nhiều publisher Reactor là **lazy**; tạo chuỗi chưa thực hiện upstream I/O. `StepVerifier` hoặc HTTP test sẽ subscribe và kiểm tra các tín hiệu thực tế.

**2. `WebTestClient.responseTimeout` và `Mono.timeout` khác nhau thế nào?**

Cái đầu giới hạn thời gian **test client chờ HTTP response**; cái sau là operator trong reactive pipeline có thể phát `TimeoutException`. Producer chỉ trả HTTP 504 khi application/error handler chuyển lỗi thành response như contract.

**3. Virtual time có tăng tốc một HTTP request bị chậm vì network thật không?**

Không. Virtual time chỉ điều khiển scheduler/timer Reactor phù hợp; socket, broker và blocking I/O thật vẫn chạy theo thời gian thực.

**4. Tại sao publisher cần được tạo trong Supplier của `withVirtualTime`?**

Để các operator dùng scheduler ảo đã được cài khi StepVerifier tạo subscription. Timer tạo bên ngoài có thể dùng scheduler thật và làm test chờ lâu.

**5. Có nên kiểm tra SSE stream vô hạn bằng `verifyComplete()` không?**

Không, nếu stream được thiết kế không kết thúc. Kiểm tra các phần tử cần thiết rồi `thenCancel` với test deadline rõ ràng.

**6. Khi Stub Runner trả response ngay, điều đó chứng minh gì và chưa chứng minh gì?**

Nó có thể chứng minh client consumer gửi request và xử lý schema/status/body mẫu đúng. Nó chưa chứng minh client xử lý tốt latency, timeout, lỗi mạng và hủy tác vụ; cần resilience tests riêng.

**7. Vì sao timeout đặt trước hay sau retry làm thay đổi kết quả?**

Timeout bên trong chuỗi có retry có thể áp dụng **mỗi lần thử**, khiến tổng thời gian kéo dài. Timeout bao bên ngoài có thể giới hạn tổng chuỗi retry; cần chọn theo SLO và kiểm thử đúng thứ tự operator.

## 32. Tài liệu tham khảo

- [Spring Cloud Contract Reference](https://docs.spring.io/spring-cloud-contract/reference/): Contract Verifier, HTTP/message contracts, generated tests và Stub Runner.
- [Spring Cloud Contract – Contract DSL](https://docs.spring.io/spring-cloud-contract/reference/project-features-contract.html): Groovy/YAML DSL và matcher.
- [Spring Framework – WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): kiểm thử HTTP WebFlux, timeout của client và streaming.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): mô hình xử lý reactive HTTP.
- [Project Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time và test publisher.
- [Reactor Core API](https://projectreactor.io/docs/core/release/api/): `Mono.timeout`, `Flux.timeout`, `retryWhen` và cancellation.
- [Reactor Netty Reference](https://projectreactor.io/docs/netty/release/reference/): HTTP client timeout và kết nối.
- [WireMock Documentation](https://wiremock.org/docs/simulating-faults/): delayed responses và lỗi mạng ở consumer resilience tests.

**Lưu ý phiên bản:** Test mode WebTestClient của Contract Verifier, annotation Spring Boot, cách kết nối client và các option timeout có thể khác theo phiên bản. Luôn đối chiếu tài liệu tương ứng với bộ Spring Boot–Spring Cloud Release Train–Spring Cloud Contract mà dự án dùng và kiểm tra generated source thật. Các đoạn code của bài là ví dụ học tập, **không phải kết quả một build đã được chạy**.

---

**Điểm cần nhớ:** Trong kiểm thử reactive, phải phân biệt **contract của HTTP/message**, **tín hiệu của Mono/Flux** và **deadline của từng tầng**. Dùng Contract Verifier để kiểm tra producer, `StepVerifier`/virtual time để kiểm tra logic bất đồng bộ, WebTestClient để kiểm tra HTTP thật và Stub Runner cùng resilience tests để bảo vệ consumer. Mỗi test cần subscription, thời hạn hữu hạn và bằng chứng thực sự đã chạy; nhờ vậy CI phát hiện thay đổi API không tương thích mà không biến chờ đợi thành test thiếu ổn định.
