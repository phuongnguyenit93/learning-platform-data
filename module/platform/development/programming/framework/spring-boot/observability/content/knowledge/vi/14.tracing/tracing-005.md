# Parent-child span trong distributed tracing với Spring Boot

Khi một request tạo đơn hàng đi qua `order-service`, `inventory-service` và cơ sở dữ liệu, chỉ nhìn tổng thời gian phản hồi HTTP không đủ để biết bước nào gây chậm. **Distributed tracing** biểu diễn đường đi này bằng các **span** liên kết trong cùng một **trace**. Quan hệ **parent-child span** (span cha–con) cho phép thấy thao tác lớn được chia thành các thao tác nhỏ và thời gian của từng bước nằm ở đâu.

Ví dụ: request `POST /orders` mất 2,4 giây; span của bước giữ hàng mất 2,1 giây, còn truy vấn database phía `inventory-service` mất 1,9 giây. Nhìn cây span, nhóm vận hành có cơ sở để ưu tiên điều tra database hoặc connection pool thay vì chỉ tối ưu controller phía `order-service`.

Bài học thuộc chương **Tracing** của module **SPRING_BOOT_OBSERVABILITY**. Nó đặt parent-child span vào bức tranh observability cho Spring Boot bằng **Micrometer Observation, metrics, logs và distributed tracing**; giải thích propagation qua HTTP/thread, tags và cardinality, exporter, sampling, cùng cách liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **trace ID**, **span ID**, **parent span ID**, span gốc và quan hệ cha–con.
2. Hiểu cách `Observation` và `Scope` trong Micrometer tạo ranh giới thao tác và giúp tracing handler dựng cây span.
3. Instrument hai thao tác nghiệp vụ lồng nhau trong Spring Boot mà không tạo span trùng lặp với HTTP instrumentation.
4. Giải thích **W3C Trace Context** và quan hệ span xuyên qua service với HTTP client/server được instrument.
5. Nhận diện tình huống mất quan hệ cha–con khi chuyển thread, chạy `@Async`, Reactor hoặc messaging.
6. Phân biệt quan hệ **parent-child** với **span links**, đồng thời hiểu giới hạn của sampling, exporter và dữ liệu trace.
7. Kiểm thử hierarchy, xử lý lỗi scope, kiểm soát high/low-cardinality metadata và dùng trace cùng metrics/logs khi điều tra sự cố.

## 1. Trace, span và các định danh

Một **trace** mô tả đường đi liên quan đến một hoạt động, thường là một yêu cầu từ người dùng hoặc một tác vụ nền. Mỗi **span** mô tả một khoảng công việc có thời điểm bắt đầu/kết thúc, tên thao tác và những metadata liên quan. Một trace có thể có một hoặc nhiều span.

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Trace ID** | Định danh chung cho các span thuộc cùng trace | `4bf92f3577b34da6a3ce929d0e0e4736` |
| **Span ID** | Định danh riêng của một span trong trace | `00f067aa0ba902b7` |
| **Parent span ID** | Tham chiếu tới span cha trực tiếp | `00f067aa0ba902b7` |
| **Root span** | Span không có parent trong trace được ghi nhận | Span nhận request vào hệ thống |
| **Child span** | Span có parent xác định | Gọi inventory từ bước checkout |
| **Span attributes** | Metadata về span | `dependency.name=inventory` |
| **Span events/status** | Các cột mốc hoặc lỗi trong span | Timeout hoặc exception được ghi nhận |
| **Span kind** | Vai trò span trong một giao tiếp | SERVER, CLIENT, INTERNAL, PRODUCER, CONSUMER |

**Parent và child dùng chung trace ID**, nhưng có **span ID khác nhau**. Ở child, `parentSpanId` tham chiếu tới `spanId` của parent. Đây là quan hệ trực tiếp để backend dựng cây.

Một ví dụ cấu trúc:

~~~text
traceId = 4bf92f3577b34da6a3ce929d0e0e4736

POST /orders                        spanId=1111111111111111  parent=none
└─ orders.checkout                  spanId=2222222222222222  parent=1111111111111111
   └─ inventory.reserve             spanId=3333333333333333  parent=2222222222222222
      └─ HTTP POST inventory        spanId=4444444444444444  parent=3333333333333333
         └─ inventory HTTP server   spanId=5555555555555555  parent=4444444444444444
            └─ DB lookup            spanId=6666666666666666  parent=5555555555555555
~~~

Các span ID ở ví dụ là số giả định để dễ đối chiếu. Dữ liệu production có thể có nhiều nhánh chạy song song, nhánh không được export và các span được tạo bởi framework/dependency khác nhau.

### 1.1. Quan hệ cha–con nói lên điều gì?

Quan hệ cha–con nói rằng một thao tác được thực hiện trong **ngữ cảnh của** thao tác khác, không nhất thiết là “cha gọi hàm con” theo Java call stack trong cùng process. Parent có thể ở một service khác; context được truyền qua HTTP hoặc message. Các child cũng có thể **chạy đồng thời** thay vì nối tiếp.

Quan trọng hơn, **không cộng tổng duration của tất cả child rồi coi đó là duration của parent**. Nhiều child có thể chồng lấn thời gian, và parent còn có thời gian xử lý không nằm trong child. Thời gian “exclusive” của một span, nếu backend hiển thị, phụ thuộc cách phân tích khoảng thời gian và cấu trúc trace.

### 1.2. Parent-child không đồng nghĩa hai span có cùng tên

Một span có tên `orders.checkout`, span con có tên `inventory.reserve`, trong khi HTTP client instrumentation có thể sinh span thứ ba dạng `HTTP POST`. Tên mô tả **loại thao tác**, còn quan hệ cha–con được quyết định bởi **trace/span context lúc span được tạo**.

Một nhãn nghiệp vụ như `order.id` không dùng để gắn quan hệ cha–con và không nên được đưa vào metric labels. Tracing sử dụng các định danh riêng của trace/span để dựng cấu trúc.

## 2. Tạo cây span qua Micrometer Observation

Trong Spring Boot, cách thường dùng để instrument nghiệp vụ là **Micrometer Observation**, không gọi trực tiếp các API của exporter. `ObservationRegistry` quản lý handlers và lifecycle; khi có tracing bridge/handler thích hợp, các Observation có thể trở thành spans.

~~~mermaid
flowchart TD
    Root["HTTP server Observation / scope"] --> Business["orders.checkout Observation / scope"]
    Business --> Reserve["inventory.reserve Observation / scope"]
    Reserve --> Client["HTTP client span"]
    Client --> Remote["Remote HTTP server span"]
    Remote --> Database["DB span nếu có instrumentation"]
    Business --> Metrics["Metrics handler ghi thời gian, count"]
    Reserve --> Trace["Tracing handler tạo spans"]
    Root --> Logs["Logging correlation: traceId/spanId"]
~~~

Các thành phần chính:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Observation.createNotStarted(...)` | Tạo Observation nhưng chưa chạy |
| `start()` | Bắt đầu lifecycle, phát callback phù hợp |
| `openScope()` | Đặt Observation hiện tại vào ngữ cảnh của luồng để thao tác lồng nhau nhận parent |
| `observe(Runnable/Supplier)` | Tiện ích quản lý start, scope, lỗi và stop quanh callback |
| `error(Throwable)` | Ghi nhận exception khi quản lý lifecycle thủ công |
| `stop()` | Hoàn tất Observation và cho handlers xử lý khi kết thúc |
| `ObservationRegistry` | Nơi gắn Observation handlers, conventions, filters và quản lý current Observation |
| Tracing handler/bridge | Chuyển lifecycle và context thành span có ngữ nghĩa tracing |

**Điểm cốt lõi của parent-child:** khi Observation B được tạo và chạy trong `Scope` của Observation A, tracing instrumentation có thể dùng ngữ cảnh đang active để đặt span của B làm **child** của span A. Chỉ việc viết hai đoạn `createNotStarted` liên tiếp **không đảm bảo** chúng có quan hệ cha–con nếu không có scope/context phù hợp.

### 2.1. Dùng observe(...) cho thao tác lồng nhau

Đây là ví dụ ứng dụng Spring Boot có hai bước nghiệp vụ:

~~~java
package com.example.orders.tracing;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final ObservationRegistry registry;
    private final InventoryGateway inventory;
    private final PaymentGateway payment;

    public CheckoutService(ObservationRegistry registry,
                           InventoryGateway inventory,
                           PaymentGateway payment) {
        this.registry = registry;
        this.inventory = inventory;
        this.payment = payment;
    }

    public void checkout(String sku, int quantity) {
        Observation.createNotStarted("orders.checkout", registry)
                .lowCardinalityKeyValue("orders.channel", "web")
                .observe(() -> {
                    reserveInventory(sku, quantity);
                    chargePayment();
                });
    }

    private void reserveInventory(String sku, int quantity) {
        Observation.createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("dependency.name", "inventory")
                .observe(() -> inventory.reserve(sku, quantity));
    }

    private void chargePayment() {
        Observation.createNotStarted("payment.charge", registry)
                .lowCardinalityKeyValue("dependency.name", "payment")
                .observe(payment::charge);
    }
}

interface InventoryGateway {
    void reserve(String sku, int quantity);
}

interface PaymentGateway {
    void charge();
}
~~~

Với tracing handler phù hợp và tất cả các lời gọi chạy đồng bộ trên cùng context:

- `orders.checkout` là **parent** của `inventory.reserve` và `payment.charge`.
- Nếu lời gọi `checkout(...)` nằm trong request HTTP đã được instrument, HTTP server span thường là parent của `orders.checkout`.
- Trong `inventory.reserve`, nếu `InventoryGateway` thực hiện HTTP bằng client được instrument, HTTP client span thường là child của span nghiệp vụ.
- Nếu không cấu hình tracing, code vẫn có thể ghi Observation metrics, nhưng không thể kết luận đã tạo spans ở backend.

Đoạn code giả định `InventoryGateway` và `PaymentGateway` là những adapter được triển khai trong ứng dụng. Nên đặt mỗi public class trong tệp Java riêng và kiểm soát cách xử lý lỗi nghiệp vụ bên ngoài ví dụ.

### 2.2. Scope và lifecycle thủ công

`observe(...)` phù hợp với nhiều thao tác đồng bộ. Khi cần giữ scope trong nhiều nhánh code, có thể quản lý thủ công:

~~~java
Observation parent = Observation.createNotStarted(
        "orders.checkout", observationRegistry);
parent.start();

try (Observation.Scope parentScope = parent.openScope()) {
    Observation child = Observation.createNotStarted(
            "inventory.reserve", observationRegistry);
    child.start();

    try (Observation.Scope childScope = child.openScope()) {
        inventoryGateway.reserve(sku, quantity);
    } catch (RuntimeException exception) {
        child.error(exception);
        throw exception;
    } finally {
        child.stop();
    }
} catch (RuntimeException exception) {
    parent.error(exception);
    throw exception;
} finally {
    parent.stop();
}
~~~

Với cấu trúc `try-with-resources`, scope con đóng trước scope cha và Observation dừng trong `finally` kể cả khi có lỗi. Đây là những bất biến quan trọng:

1. **`start()` trước khi mở scope** và **`stop()` đúng một lần**.
2. Không để scope bị rò rỉ qua request khác hoặc thread pool tái sử dụng.
3. Ghi lỗi trên đúng Observation tương ứng; parent cũng có thể ghi lỗi khi lỗi child không được xử lý.
4. Không gọi `stop()` quá sớm rồi tiếp tục thêm metadata với kỳ vọng handler vẫn dùng.

**Lưu ý:** code trên minh họa lifecycle với exception dạng `RuntimeException`. Trong hệ thống thật, cần bao quát cách xử lý các loại lỗi và cancellation phù hợp API ứng dụng. Với thao tác đơn giản, ưu tiên `observe(...)` để giảm rủi ro quên đóng scope.

### 2.3. Khi nào không nên thêm span?

Spring Boot thường đã instrument HTTP server, HTTP client và các thư viện được hỗ trợ. Không cần thêm một custom Observation chỉ để bao lại **đúng một lời gọi HTTP** mà không mang ý nghĩa nghiệp vụ mới, nếu việc đó tạo hai span gần như trùng nhau.

Nên thêm span cho các **ranh giới nghiệp vụ có giá trị khi điều tra**, chẳng hạn `orders.checkout` bao gồm giữ hàng, tính phí, ghi database; hoặc một bước retry/validation thật sự đáng đo. Quá nhiều span làm tăng CPU, kích thước trace, chi phí lưu trữ và độ nhiễu của timeline.

## 3. Quan hệ span qua HTTP giữa hai service

Trong distributed tracing, parent có thể chạy ở process khác. Muốn nối cây giữa `order-service` và `inventory-service`, hệ thống phải **propagate trace context** qua HTTP.

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Database as DB
    Client->>Order: POST /orders
    Note over Order: SERVER span A
    Order->>Order: orders.checkout span B, parent A
    Order->>Order: inventory.reserve span C, parent B
    Order->>Inventory: HTTP POST + traceparent, CLIENT span D
    Note over Inventory: SERVER span E, remote parent D
    Inventory->>Database: Query, child span F nếu instrument
    Database-->>Inventory: Result
    Inventory-->>Order: HTTP response
    Order-->>Client: Response
~~~

Trong mô hình trên:

- Span A, B, C và D ở `order-service` nằm trong cùng trace.
- Header truyền context từ phía client span D sang phía server của `inventory-service`.
- SERVER span E mang `parentSpanId` tương ứng với ID của CLIENT span D nếu instrumentation/propagation được nối đúng.
- Span F, nếu có, là child của E hoặc của một span nghiệp vụ nằm dưới E.

Không nên tự tạo một server span thứ hai nếu Spring MVC/WebFlux instrumentation đã tạo server span cho request.

### 3.1. W3C Trace Context và traceparent

Một dạng header theo chuẩn W3C:

~~~http
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Các thành phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `00` đầu tiên | Version của định dạng `traceparent` |
| 32 ký tự hex tiếp theo | Trace ID (128-bit) |
| 16 ký tự hex tiếp theo | Parent ID: span ID của phía gửi trong context truyền đi |
| `01` cuối cùng | Trace flags; bit sampled được bật trong ví dụ |

**Parent ID trong header** có nghĩa là span ID mà service nhận nên xem là parent từ xa, không phải “ID của HTTP request” hoặc “ID của nghiệp vụ giữ hàng”. Khi service nhận tạo span SERVER, nó có **span ID mới** nhưng giữ **trace ID** nếu propagation thành công.

Header `tracestate` có thể mang dữ liệu liên quan tracing vendor theo chuẩn; việc có hay không phụ thuộc tracing system. Không đặt mật khẩu, access token hoặc dữ liệu người dùng trong các header truyền trace context.

Nếu dùng B3 thay vì W3C, tên header có thể khác. Hai service phải thống nhất hoặc có cơ chế hỗ trợ chuyển đổi context tương ứng; không chỉ nhìn tên trace ID trong logs rồi suy ra propagation đúng.

### 3.2. Sử dụng HTTP client được Spring Boot instrument

Với Spring Boot 3.2+ có `RestClient.Builder` được cấu hình bởi Spring, một adapter gọi inventory có thể như sau:

~~~java
package com.example.orders.tracing;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class HttpInventoryGateway implements InventoryGateway {
    private final RestClient restClient;

    public HttpInventoryGateway(RestClient.Builder builder) {
        this.restClient = builder
                .baseUrl("http://inventory-service:8080")
                .build();
    }

    @Override
    public void reserve(String sku, int quantity) {
        restClient.post()
                .uri("/inventory/reservations")
                .body(new ReserveRequest(sku, quantity))
                .retrieve()
                .toBodilessEntity();
    }
}

record ReserveRequest(String sku, int quantity) {}
~~~

Khi sử dụng builder **do Spring Boot auto-configure** cùng Observation/tracing instrumentation, HTTP client có thể tạo CLIENT observation/span và thêm header context phù hợp. Ở `inventory-service`, HTTP server instrumentation đọc header để tiếp tục trace.

**Không mặc định rằng `RestClient.create()` tự khởi tạo bằng tay, client SDK bất kỳ hoặc HTTP client của thư viện thứ ba đều được instrument.** Với client tùy chỉnh, phải kiểm tra sự kết nối với `ObservationRegistry` và cơ chế propagator.

Địa chỉ `inventory-service:8080` chỉ minh họa một tên dịch vụ có thể resolve được trong môi trường container; dùng endpoint thích hợp cho hệ thống đang chạy.

## 4. Spring Boot: tracing bridge, exporter và sampling

Trong một ứng dụng Spring Boot 3.x dùng Micrometer Tracing kết hợp OpenTelemetry bridge và OTLP, các dependency minh họa:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Cấu hình thử nghiệm `application.yml`:

~~~yaml
spring:
  application:
    name: order-service

management:
  tracing:
    sampling:
      probability: 1.0   # Chỉ dùng khi test; giữ mẫu cao để dễ xem cây span
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces
~~~

Ý nghĩa:

1. `Actuator` và tracing bridge tham gia cấu hình observability/tracing của Spring Boot.
2. Tracing exporter OTLP chuyển các span được ghi nhận đến Collector hoặc backend tương thích.
3. `probability: 1.0` dùng cho môi trường bài thực hành ít traffic; production cần chọn sampling theo lưu lượng, chi phí và mục tiêu phân tích.
4. `http://localhost:4318/v1/traces` chỉ đúng khi receiver OTLP HTTP có thể truy cập ở chính địa chỉ đó từ process ứng dụng. Trong container, `localhost` có thể trỏ sai đối tượng.

Tên property, module và hành vi auto-configuration có thể khác ở các phiên bản Spring Boot/Micrometer. Giữ dependency theo BOM của dự án và kiểm tra tài liệu tương ứng với phiên bản thực tế.

### 4.1. Có tracing bridge nhưng chưa chắc đã có cây span ở backend

Một đường dữ liệu đầy đủ thường gồm:

~~~mermaid
flowchart LR
    Code["Observation trong code"] --> Registry["ObservationRegistry"]
    Registry --> Handler["Tracing handler / bridge"]
    Handler --> Sampler["Sampling decision"]
    Sampler --> Exporter["OTLP exporter"]
    Exporter --> Collector["OpenTelemetry Collector"]
    Collector --> Backend["Trace backend"]
    Registry --> Metrics["Metrics handler / MeterRegistry"]
    Code --> Logs["Logging / correlation"]
~~~

Trace có thể thiếu ở bất kỳ chặng nào: Observation không có handler, sampler bỏ qua, exporter lỗi, Collector từ chối dữ liệu, backend hết hạn lưu trữ hoặc đang tìm sai service/time range. **Một span không hiện ở UI không chứng minh code chưa chạy.**

### 4.2. Parent-child dưới ảnh hưởng của sampling

Với **head-based sampling**, quyết định thường được thực hiện sớm ở đầu trace và các child có thể kế thừa sampling flag từ parent. Parent context có thể vẫn được truyền sang service kế tiếp khi trace không được ghi lại. Vì vậy:

- Một trace bị loại theo sampling có thể không có bất kỳ span nào được lưu ở backend.
- Các Observation vẫn có thể ghi metrics qua handlers độc lập với tracing.
- Một trace có thể xuất hiện **không đầy đủ** nếu một service instrument sai, exporter lỗi, pipeline bị tách hoặc mỗi service áp dụng chính sách khác nhau.
- Không dùng tỷ lệ trace được lưu làm tỷ lệ request thành công/thất bại nếu sampling không được thiết kế để hỗ trợ suy luận đó.

**Tail-based sampling** có thể đưa ra quyết định sau khi thu thập spans, ví dụ ưu tiên trace lỗi hoặc chậm; tuy nhiên cần Collector/pipeline đủ khả năng giữ các span liên quan và chi phí bộ nhớ/độ trễ xuất cao hơn. Không giả định một cờ `sampling.probability` trong Spring Boot tự bật tail sampling.

## 5. Scope và context propagation khi chuyển thread

Phần khó nhất của parent-child span thường không phải cách đặt tên mà là **giữ đúng trace context** khi luồng thực thi thay đổi. Scope thường gắn với ngữ cảnh hiện hành của thread hoặc execution context. Nếu tạo một child Observation trên thread khác mà không mang context của parent sang, child có thể trở thành root mới.

### 5.1. Ví dụ mất parent trong Executor

~~~java
// Minh họa trường hợp dễ sai:
Observation.createNotStarted("orders.checkout", registry)
        .observe(() -> {
            executor.execute(() ->
                    Observation.createNotStarted("invoice.generate", registry)
                            .observe(this::generateInvoice));
        });
~~~

Nếu `executor` không có context propagation, task chạy trên thread pool có thể không biết current Observation/span của `orders.checkout`. Hệ quả: `invoice.generate` không có parent như kỳ vọng, hoặc không được kết nối vào trace ban đầu.

**Không chữa lỗi bằng cách tự sao chép trace ID vào một String rồi đặt thành tên span**. Parent-child phụ thuộc trace/span context, không chỉ một chuỗi ID. Tự set header hoặc thread-local không đúng có thể làm trace đứt hoặc tạo lỗ hổng bảo mật.

### 5.2. Dùng TaskDecorator có context propagation

Với Spring Framework 6.1+ và dependency context-propagation phù hợp, có thể cấu hình executor:

~~~java
package com.example.orders.tracing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncTracingConfiguration {

    @Bean("observedExecutor")
    ThreadPoolTaskExecutor observedExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("observed-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

`ContextPropagatingTaskDecorator` giúp capture và restore các context đã được đăng ký theo cơ chế Micrometer Context Propagation tại thời điểm task được submit/run. Ví dụ service:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;

@Service
public class InvoiceService {
    private final ObservationRegistry registry;

    public InvoiceService(ObservationRegistry registry) {
        this.registry = registry;
    }

    @Async("observedExecutor")
    public CompletableFuture<Void> generateAsync(String reference) {
        Observation.createNotStarted("invoice.generate", registry)
                .observe(() -> generateInvoice(reference));
        return CompletableFuture.completedFuture(null);
    }

    private void generateInvoice(String reference) {
        // Xử lý invoice; không ghi reference nhạy cảm vào low-cardinality tag.
    }
}
~~~

**Điều kiện để ví dụ có hiệu lực:** `InvoiceService` phải được gọi qua Spring proxy `@Async`; executor phải đúng bean được cấu hình và context accessors phù hợp phải được đăng ký. Khi có nhiều loại executor hoặc scheduling framework khác, cần áp dụng cơ chế propagation tương ứng. Hãy kiểm tra trace thực tế, không chỉ giả định decorator đã giải quyết mọi ranh giới.

Nếu parent scope đã đóng khi async child bắt đầu, child vẫn có thể tham chiếu parent thông qua context đã được capture trước đó; cây span không nhất thiết yêu cầu thời gian thực thi của hai span chồng lấn. Tuy nhiên, điều này còn phụ thuộc cách framework giữ và phục hồi context và trạng thái recording của tracing backend.

### 5.3. Với Reactor, messaging và virtual threads

- **Reactor/WebFlux:** không dựa vào `ThreadLocal` một cách ngây thơ; execution có thể chuyển thread giữa các operator. Sử dụng hỗ trợ context propagation của Reactor/Spring và kiểm tra context trong pipeline thực tế.
- **Messaging/Kafka/RabbitMQ:** cần instrument producer/consumer hoặc headers để propagate trace context. Một consumer xử lý trễ hoặc batch nhiều message có thể chọn parent-child hay span links theo ngữ nghĩa của workflow.
- **Virtual threads:** việc có cùng tên thao tác không bảo đảm parent tự được truyền khi khởi tạo task mới; dùng các cơ chế được framework hỗ trợ và xác minh span relationship.

Một `Observation` đúng tên, có tags và được dừng không tự bảo đảm nó là child của span mong muốn. **Propagation là phép kiểm thử riêng.**

## 6. Parent-child span và span links khác nhau

Không phải mọi mối quan hệ giữa hai công việc đều phù hợp để biểu diễn bằng một parent duy nhất.

| Quan hệ | Dùng khi | Ví dụ |
| --- | --- | --- |
| **Parent-child** | Một thao tác thực thi trong context của thao tác khác | HTTP client span → HTTP server span từ cùng request |
| **Sibling spans** | Hai thao tác cùng parent | Hai lời gọi độc lập tới inventory và payment |
| **Span link** | Cần liên kết với span/context khác mà không đặt một parent trực tiếp | Batch job tiêu thụ nhiều message từ nhiều trace nguồn |
| **Cùng business ID** | Có liên quan nghiệp vụ nhưng không nhất thiết cùng trace | Một đơn hàng được xử lý lại sau nhiều ngày |

Ví dụ batch consumer nhận 100 message, mỗi message có trace context khác nhau. Batch process span không thể có **100 parent span ID** trực tiếp: một span chỉ có **một parent** trong cây. Với hệ thống tracing hỗ trợ, **span links** là cách biểu diễn quan hệ tới nhiều nguồn.

Không tự “ghép trace” bằng cách sao chép trace ID của request bất kỳ vào cả batch. Cần tuân theo semantic conventions và instrumentation của messaging system đang dùng; hỗ trợ span links còn phụ thuộc tracer và backend.

## 7. Attributes, cardinality và bảo mật trong cây span

Span attributes giúp giải thích vì sao một bước chậm hoặc lỗi. Với `inventory.reserve`:

| Key | Giá trị | Phân loại/đánh giá |
| --- | --- | --- |
| `dependency.name` | `inventory` | Low cardinality, hữu ích cho metrics/trace |
| `inventory.operation` | `reserve` | Low cardinality |
| `inventory.channel` | `web`, `batch` | Low cardinality nếu chuẩn hóa |
| `inventory.attempt.id` | Mã giả danh mỗi lần thử | High cardinality, cân nhắc lưu trên trace |
| `http.route` | `/orders/{id}` | Route template phù hợp hơn raw URL |
| `customer.email` | Email người dùng | Không thu thập mặc định |
| `authorization` | Bearer token | Tuyệt đối không ghi vào attributes |

Trong Micrometer Observation:

~~~java
Observation.createNotStarted("inventory.reserve", registry)
        .lowCardinalityKeyValue("dependency.name", "inventory")
        .lowCardinalityKeyValue("inventory.operation", "reserve")
        .highCardinalityKeyValue("inventory.attempt.id", attemptId)
        .observe(() -> inventoryGateway.reserve(sku, quantity));
~~~

**Low-cardinality key-values** thường được dùng cho metric labels và cũng có thể hiện trên span. **High-cardinality key-values** có thể được tracing handler biến thành span attributes, nhưng không nên đưa vào metric labels vì số series tăng theo lưu lượng. Không nên cho rằng mọi handler/exporter đều giữ tất cả thuộc tính: backend có thể giới hạn độ dài, số attributes hoặc indexing.

Một high-cardinality tag **không tự trở thành baggage**. Baggage là cơ chế mang một số dữ liệu ngữ cảnh sang downstream khi được cấu hình, cần kiểm soát rõ allowlist, kích thước và rủi ro riêng tư. Thêm `highCardinalityKeyValue` ở `order-service` không làm `inventory-service` tự nhận cùng key.

### 7.1. Parent và child có tự chia sẻ attributes không?

Không mặc định. Parent-child thường chia sẻ **trace context** (trace ID, sampling state và thông tin cần cho propagation) chứ không phải toàn bộ business attributes. Một tag trên parent không nhất thiết xuất hiện trên child span. Nếu cần cùng attribute ở nhiều span, hãy xác định yêu cầu rõ ràng và chọn cách bổ sung phù hợp; tránh sao chép dữ liệu không cần thiết lên hàng trăm spans.

### 7.2. Quản lý chi phí

Thêm một child span cho mỗi item của một batch 100.000 item có thể tạo lượng dữ liệu tracing rất lớn. Hãy instrument ranh giới có ý nghĩa, cân nhắc sampling và giới hạn attributes/events; dùng metrics để đo lưu lượng và phân bố tổng thể, logs/traces để điều tra các trường hợp cụ thể.

Tương tự, không gắn `order.id` hoặc `trace.id` vào labels của timer `orders.checkout`. Ví dụ 5 route, 4 outcomes, 20 instance, 30 bucket histogram có thể tạo đến **5 × 4 × 20 × 30 = 12.000** series bucket trong mô hình đơn giản, chưa tính labels khác. Thêm request ID sẽ làm cardinality tăng theo số request.

## 8. Quan sát lỗi và độ trễ qua một cây span

Giả sử `POST /orders` bắt đầu chậm sau khi triển khai phiên bản mới. Một trace được sampling giữ có thể hiển thị:

~~~text
POST /orders (SERVER)                 2.40 s
└─ orders.checkout (INTERNAL)          2.32 s
   ├─ inventory.reserve (INTERNAL)     2.10 s
   │  └─ HTTP POST inventory (CLIENT)  2.07 s
   │     └─ reserve (SERVER)           2.03 s
   │        └─ SELECT stock (DB)       1.87 s
   └─ payment.charge (INTERNAL)        0.12 s
~~~

Đây là timeline **giả định**; thời lượng từng child có thể chồng lấn nếu các thao tác đồng thời. Một backend có thể biểu diễn lỗi bằng span status, events hoặc attributes theo SDK/instrumentation.

Hướng điều tra:

1. **Metrics:** xác minh request rate, 5xx rate, latency p95/p99 của `POST /orders` và số lần timeout của inventory-service.
2. **Traces:** mở trace chậm, đọc cấu trúc parent-child để xác định bước inventory chiếm phần lớn thời gian.
3. **Logs:** dùng trace ID/span ID tương quan với log timeout, query hoặc connection pool warning.
4. **Dependency metrics:** đối chiếu JDBC pool pending connections, DB latency, CPU/GC, queue và saturation.
5. **Thay đổi:** kiểm tra rollout, giới hạn concurrency, timeout, retry và kế hoạch rollback.
6. **Đo lại:** sau sửa lỗi, so sánh error ratio, p95/SLO, số timeout và các trace mẫu.

**Không suy luận tình trạng toàn hệ thống chỉ từ một trace.** Traces cho một trường hợp được ghi lại; metrics mô tả xu hướng và mức độ ảnh hưởng; logs hỗ trợ diễn giải lỗi. Số trace quan sát được còn phụ thuộc sampling và retention.

### 8.1. Log correlation và giới hạn của nó

Ví dụ bản ghi:

~~~text
2026-11-22T09:10:15Z ERROR service=order-service
traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=3333333333333333
event=inventory_timeout dependency=inventory-service duration_ms=2070
~~~

Nếu logging được cấu hình để đưa trace/span IDs vào MDC, có thể truy từ log sang trace. Tuy nhiên:

- Không phải mọi log được ghi bên trong một active scope; log nền có thể không có trace ID.
- Trace ID trong log không bảo đảm trace đã được export hoặc sampling giữ lại.
- Không gắn request body, access token, email vào log chỉ để có thêm context.
- Một span có thể báo lỗi nhưng parent không báo lỗi nếu ứng dụng xử lý exception thành công; quy tắc error status phải được diễn giải theo instrumentation thực tế.

## 9. Kiểm thử quan hệ parent-child span

Nên phân tầng kiểm thử để tránh tuyên bố quá mức từ một unit test:

| Tầng | Có thể xác minh | Chưa chứng minh |
| --- | --- | --- |
| **Unit test với TestObservationRegistry** | Observation được tạo/dừng, scope lồng nhau, key-values, lỗi | Span ID và parentSpanId của exporter |
| **Tracing integration test** | Span được tạo bởi tracing handler và parentSpanId đúng | Toàn bộ hạ tầng production |
| **HTTP cross-service test** | Header context và span CLIENT/SERVER tiếp nối trace | Mọi request đều được lưu trace |
| **Async/reactive test** | Context sang thread/pipeline và child không mất parent | Không có lỗi ở mọi executor/framework |
| **Staging backend test** | Collector nhận trace, UI dựng cây, logs correlation | Sự đầy đủ tuyệt đối khi sampling/retention thay đổi |

### 9.1. Test scope lồng nhau bằng TestObservationRegistry

`micrometer-observation-test` hỗ trợ kiểm tra Observation runtime mà không cần Collector. Ví dụ JUnit 5:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

class NestedObservationScopeTest {

    @Test
    void restoresParentScopeAfterChildCompletes() {
        TestObservationRegistry registry = TestObservationRegistry.create();
        Observation.createNotStarted("orders.checkout", registry)
                .observe(() -> {
                    Observation parent = registry.getCurrentObservation();
                    assertNotNull(parent);

                    Observation.createNotStarted("inventory.reserve", registry)
                            .observe(() -> {
                                Observation current = registry.getCurrentObservation();
                                // Trong scope child, current là Observation con.
                                assertNotNull(current);
                                org.junit.jupiter.api.Assertions.assertNotSame(
                                        parent, current);
                            });

                    assertSame(parent, registry.getCurrentObservation());
                });

        assertNull(registry.getCurrentObservation());
    }
}
~~~

Test kiểm tra scope được thiết lập và phục hồi. **Nó chưa chứng minh có parentSpanId đúng trong tracing backend**, vì `TestObservationRegistry` có thể hoạt động mà không có tracing bridge. Để kiểm tra quan hệ span thực tế, cần tracing integration test.

### 9.2. Kiểm thử span IDs bằng in-memory exporter

Ở mức tích hợp, có thể cấu hình OpenTelemetry SDK với exporter kiểm thử trong bộ nhớ (ví dụ `InMemorySpanExporter` khi thêm test dependency SDK tương ứng) hoặc dùng test span handler nếu chọn Brave.

Kịch bản mong đợi:

1. Khởi tạo tracing infrastructure thực, không chỉ `TestObservationRegistry`.
2. Bắt đầu parent Observation `orders.checkout` và mở scope.
3. Bắt đầu child Observation `inventory.reserve` trong scope của parent, sau đó dừng cả hai.
4. Thu các span đã export trong bộ nhớ.
5. Kiểm tra **hai span có cùng trace ID**.
6. Kiểm tra **child.parentSpanId bằng parent.spanId** và **child.spanId khác parent.spanId**.
7. Kiểm tra từng span đã kết thúc, thời gian hợp lý và error/status khi có lỗi.

Trong test này nên **điều khiển sampling** sao cho các span được ghi và tránh lệ thuộc vào OTLP server. Test cross-service riêng phải có HTTP client/server instrumentation và header propagation; local in-memory exporter không chứng minh đã truyền được context giữa hai process.

### 9.3. Kiểm thử HTTP propagation

Kịch bản đơn giản:

- Từ `order-service`, tạo request dưới active span tới test HTTP server hoặc một `inventory-service` thử nghiệm.
- Trên phía nhận, kiểm tra header `traceparent` (nếu đã chọn W3C propagator) và active span SERVER.
- Khẳng định trace ID của span nhận bằng trace ID phía gửi, parentSpanId phù hợp với CLIENT span.
- Chạy thêm ca client tự tạo không có instrumentation để thấy khác biệt và tránh hiểu nhầm tự động.

Không cố định exact span ID trong assertion vì ID thường được sinh ngẫu nhiên; thay vào đó kiểm tra **quan hệ giữa các ID**.

### 9.4. Kiểm thử lỗi và async

Với đường đi lỗi, cho `InventoryGateway` ném timeout rồi kiểm tra Observation dừng và lỗi được ghi nhận; trong tracing integration test, xem span có error information phù hợp. Với async, so sánh context/cây span khi executor **có** và **không** context propagation để thấy vì sao child có thể thành root.

Không dùng sleep dài để kiểm tra duration chính xác trong unit test. Hãy dùng clock/test infrastructure phù hợp và assertions dựa trên quan hệ/hành vi, còn độ trễ thực tế nên xác minh trong integration test chuyên biệt.

## 10. Các lỗi thường gặp khi dựng cây trace

| Triệu chứng | Nguyên nhân khả dĩ | Cách điều tra |
| --- | --- | --- |
| Child thành root span | Không có active scope hoặc mất context khi chuyển thread | Kiểm tra `observe/openScope`, executor/context propagation |
| Hai service có trace ID khác nhau | HTTP client không instrument hoặc propagator không khớp | Xem `traceparent` và cấu hình client/server |
| Có parent nhưng không thấy child | Child không được tạo, bị no-op, tracing handler thiếu hoặc sampling/exporter mất dữ liệu | Kiểm tra Observation runtime, sampler và collector |
| Parent/child có tên trùng lặp khó đọc | Instrument cùng bước hai lần | Xóa span dư hoặc định nghĩa ranh giới nghiệp vụ rõ |
| Scope của request sau mang trace trước | Quên đóng scope hoặc rò rỉ thread-local | Dùng `try-with-resources` hoặc `observe(...)` |
| Trace có nhiều span nhưng không biết bước chậm | Span quá mịn, tên chung chung, thiếu semantic attributes | Đổi cấu trúc theo nghiệp vụ, giữ tên/tag ổn định |
| Parent kết thúc trước child async | Async lifecycle không được thiết kế/propagate rõ | Kiểm tra context capture và ý nghĩa công việc bất đồng bộ |
| Trace chỉ còn span một service | Exporter/downstream không instrument hoặc Collector cấu hình sai | Kiểm tra pipeline từng service |
| Logs có trace ID nhưng backend không tìm thấy trace | Sampling, lỗi exporter, retention hoặc sai time range | Tra cấu hình sampling và telemetry pipeline |
| Metadata high-cardinality xuất hiện ở metric labels | Nhầm `highCardinalityKeyValue` với low cardinality | Sửa convention, kiểm tra MeterRegistry |
| Mất liên kết khi qua Kafka/batch | Header propagation hoặc span-link semantics chưa đúng | Kiểm tra producer/consumer và kiểu quan hệ |

### 10.1. Quy trình kiểm tra từ gần đến xa

Khi không thấy quan hệ cha–con:

1. **Trong code:** xác nhận parent Observation đang active ở điểm tạo child, lifecycle không bị đóng sớm.
2. **Trong process:** xác nhận tracing handler/bridge có tạo spans, child có trace ID giống parent và parentSpanId phù hợp.
3. **Qua network/thread:** xác nhận context được inject/extract hoặc capture/restore đúng.
4. **Ở exporter:** xác nhận sampler và exporter có ghi/đẩy các spans mong đợi.
5. **Ở backend:** kiểm tra service name, trace ID, khoảng thời gian, retention và giới hạn indexing.

Đừng sửa histogram, đổi metric labels hay tăng scrape interval của Prometheus để chữa một lỗi parent-child tracing. Metrics và traces có pipeline riêng, dù cùng được tạo từ Micrometer Observation.

## 11. Checklist trước khi triển khai production

| Tiêu chí | Bằng chứng đạt |
| --- | --- |
| Ranh giới parent/child có ý nghĩa | Sơ đồ hành trình request và tên các thao tác chính |
| Scope được đóng đúng | `observe(...)` hoặc `try-with-resources` rõ ràng |
| Không sinh span trùng | HTTP auto-instrumentation và business spans không chồng nghĩa vô ích |
| W3C propagation được xác minh | CLIENT/SERVER spans cùng trace ID và parentSpanId đúng |
| Async/reactive propagation được xác minh | Test qua executor/WebFlux hoặc messaging đang dùng |
| Sampling được hiểu rõ | Biết phần trace có thể thiếu và tác động chi phí |
| Exporter/Collector hoạt động | Trace có thể tìm trong backend theo trace ID |
| Span attributes an toàn | Không lưu token, PII, request body; giới hạn high cardinality |
| Metrics vẫn đo toàn bộ xu hướng cần thiết | Request rate, error ratio, p95/p99 và SLO nếu có |
| Logs tương quan với trace | Có trace/span ID khi context hiện diện |
| Span IDs và error status được test | Test tại tracing layer, không chỉ ở Observation runtime |
| Có kế hoạch thay đổi instrumentation | Tránh phá dashboard và tăng chi phí khi đổi tên/tags |

## 12. Bài thực hành: theo dõi request tạo đơn qua hai service

**Bối cảnh:** `order-service` xử lý `POST /orders`, sau đó gọi `inventory-service` để giữ hàng và ghi database. Người dùng phản ánh request đôi khi mất hơn 2 giây. Bạn cần có cây span chỉ ra bước chậm và liên kết với metrics/logs.

**Nhiệm vụ:**

1. Thêm Actuator, Micrometer Tracing bridge và exporter phù hợp vào cả hai service. Chọn thống nhất W3C Trace Context.
2. Để HTTP server instrumentation tạo span của request đến `order-service`.
3. Thêm custom Observation `orders.checkout` bao quanh nghiệp vụ, thêm child `inventory.reserve` trong scope của parent.
4. Sử dụng HTTP client được Spring Boot instrument để gọi `inventory-service` và kiểm tra header `traceparent`.
5. Trên service nhận, kiểm tra SERVER span cùng trace ID với CLIENT span phía gửi; nếu có DB instrumentation, xác nhận span DB nằm dưới bước xử lý phù hợp.
6. Viết unit test bằng `TestObservationRegistry` xác minh scope lồng nhau và lifecycle; viết integration test với exporter bộ nhớ để xác nhận parentSpanId.
7. Tạo lỗi timeout giả lập, xem span lỗi, log cùng trace ID và HTTP error metrics; không đưa mã đơn hoặc dữ liệu cá nhân vào metric tags.
8. Thử đưa công việc sang `@Async` không có context propagation, ghi nhận cây span bị đứt; cấu hình `ContextPropagatingTaskDecorator` rồi so sánh.
9. Thay sampling từ 100% ở môi trường thử nghiệm xuống mức thấp, giải thích vì sao một số request không có trace nhưng metrics vẫn có.
10. Đề xuất dashboard request rate, error ratio, p95/p99 và quy trình đi từ panel bất thường đến trace mẫu và logs.

**Kết quả mong đợi:** sơ đồ cây span với trace ID và parentSpanId đối chiếu được, mã Observation/HTTP client, bộ kiểm thử scope và tracing integration, bảng metrics/logs theo một lỗi giả lập và ghi chú về sampling, exporter, context propagation.

## 13. Ghi nhớ

**Parent-child span** biểu diễn mối quan hệ giữa các thao tác trong cùng một trace. Child giữ **trace ID** chung nhưng có **span ID riêng** và tham chiếu **parent span ID**. Trong Spring Boot, Micrometer Observation và scope phù hợp giúp tracing handler tạo các span nghiệp vụ lồng nhau; HTTP client/server instrumentation cùng W3C Trace Context nối quan hệ qua biên service.

Một cây span chính xác phụ thuộc không chỉ code tạo span mà cả **context propagation, sampling, tracing bridge, exporter và backend**. Để điều tra lỗi, độ trễ và hành vi ứng dụng hiệu quả, hãy kết hợp trace với **metrics có cardinality được kiểm soát** và **logs có tương quan trace ID**, luôn phân biệt bằng chứng từ một request với xu hướng toàn hệ thống.

**Tài liệu tham khảo:**

- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Tracing Reference](https://docs.micrometer.io/tracing/reference/)
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/)
- [OpenTelemetry — Traces](https://opentelemetry.io/docs/concepts/signals/traces/)
- [Spring Framework — Context Propagation](https://docs.spring.io/spring-framework/reference/observability.html)
