# Gắn high-cardinality metadata vào Custom Observation trong Spring Boot

Khi điều tra một request chậm, kỹ sư thường cần biết **thao tác cụ thể nào** đã gặp lỗi. Ví dụ: trong hàng nghìn lần gọi `inventory-service`, một lần thử giữ hàng mất 2,4 giây rồi timeout. Metrics cho biết độ trễ đang tăng, nhưng không thể chỉ ra đầy đủ thông tin của từng lần gọi. Distributed tracing có thể hiển thị một span đại diện cho lần thử đó, kèm metadata hỗ trợ tìm nguyên nhân.

Trong Micrometer Observation, các thuộc tính có rất nhiều giá trị khác nhau, chẳng hạn một mã thử gọi duy nhất cho mỗi request, được gọi là **high-cardinality key-values**. Ta có thể gắn chúng vào một **custom observation** bằng API `highCardinalityKeyValue(...)` hoặc cung cấp chúng từ `ObservationConvention`. Khi tracing handler phù hợp được cấu hình, chúng có thể trở thành **span attributes** để điều tra request cụ thể.

Bài này thuộc phần **Custom observation** của module **SPRING_BOOT_OBSERVABILITY**: thiết lập observability cho Spring Boot với Micrometer Observation, metrics, logs và distributed tracing. Nội dung cũng giải thích ngữ cảnh truyền qua service/thread, tag và cardinality, exporter, sampling và cách liên kết tín hiệu khi xử lý sự cố thực tế.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt low-cardinality và high-cardinality metadata theo mục đích, chi phí và nơi sử dụng.
2. Gắn high-cardinality metadata bằng `Observation.highCardinalityKeyValue(...)` trong một custom observation.
3. Tạo `Observation.Context` và `ObservationConvention` khi nhiều điểm instrument cần hợp đồng tag thống nhất.
4. Giải thích high-cardinality metadata xuất hiện trong trace thế nào và vì sao không tự động được truyền sang service khác.
5. Tránh rò rỉ dữ liệu nhạy cảm, tránh tăng số series metrics và kiểm soát chi phí traces.
6. Kiểm thử metadata ở runtime, đối chiếu metrics/traces/logs và xử lý trường hợp trace bị sampling hoặc exporter bỏ sót.

## 1. High-cardinality metadata là gì?

**Cardinality** là số lượng giá trị khác nhau mà một key có thể mang. Ví dụ `inventory.channel` chỉ có `web` và `batch` thì cardinality thấp. `inventory.attempt.id` có một giá trị mới cho từng lần gọi nên cardinality cao.

| Key | Ví dụ giá trị | Đặc tính | Mục đích phù hợp |
| --- | --- | --- | --- |
| `inventory.operation` | `reserve`, `release` | Low cardinality: tập hữu hạn | Nhóm metric theo loại thao tác |
| `inventory.channel` | `web`, `batch` | Low cardinality | So sánh hành vi theo nguồn gọi |
| `inventory.outcome` | `success`, `failure` | Low cardinality | Theo dõi kết quả theo nhóm |
| `inventory.attempt.id` | `attempt-8d1...` | High cardinality: gần như mỗi lần một giá trị | Tìm một lần thử trong trace |
| `job.execution.id` | Mã của từng lần chạy job | High cardinality | Phân tích một lần chạy nền cụ thể |
| `http.request.raw_path` | `/orders/72834` | High cardinality | Không nên làm metric label; xem xét có thật sự cần giữ |
| `customer.email` | Email người dùng | High và nhạy cảm | **Không thu thập mặc định**, kể cả trong trace |

### 1.1. Phân biệt theo tác động lên hệ thống

Một hệ thống metrics như Prometheus thường lưu mỗi tổ hợp tên metric và labels thành một **time series**. Nếu `inventory.attempt.id` đổi theo mỗi lần gọi, số series có thể tăng theo số request, dẫn đến bộ nhớ, lưu trữ và chi phí truy vấn lớn.

Trong Micrometer Observation, **low-cardinality key-values** thường được metrics handler dùng để gắn nhãn có thể tổng hợp. **High-cardinality key-values** thường được tracing handler sử dụng làm thuộc tính của span, nhằm mô tả *một lần thực thi cụ thể*. Việc một key thực sự xuất hiện ở backend nào còn tùy handler, filter, exporter, sampling và cấu hình thực tế.

Ví dụ, nếu một metric được phân nhóm theo 2 channel, 3 outcome, 4 region và 50 instance, số tổ hợp có thể lên đến **2 × 3 × 4 × 50 = 1.200**. Nếu thêm một nhãn `attempt_id` riêng cho 100.000 request, số lượng tổ hợp có khả năng tăng theo request và mất ý nghĩa tổng hợp.

**High-cardinality không đồng nghĩa dữ liệu được phép thu thập.** Một mã có nhiều giá trị có thể là thông tin cá nhân, mã truy cập hoặc bí mật; các dữ liệu đó vẫn cần được loại bỏ hoặc xử lý theo quy định trước khi đưa vào traces hay logs.

### 1.2. High-cardinality không phải là log hay baggage

Ba khái niệm cần tách bạch:

- **High-cardinality key-value của Observation:** metadata gắn vào `Observation.Context`; tracing handler có thể đưa vào span tương ứng.
- **Log field:** trường được phát sinh bởi hệ thống logging. Nó chỉ xuất hiện khi mã nguồn/logging configuration ghi trường đó. Log có thể chứa trace ID để liên kết với span nhưng không tự lấy mọi key high cardinality của Observation.
- **Baggage:** dữ liệu ngữ cảnh có thể truyền qua các ranh giới service theo cơ chế propagation nếu được cấu hình. Thêm `highCardinalityKeyValue` **không tự biến key thành baggage** và không tự gửi thuộc tính đó đến downstream service.

Không sử dụng high-cardinality metadata làm nơi lưu trạng thái nghiệp vụ có tính bền vững. Trace có thể bị lấy mẫu, bỏ qua, hết hạn lưu trữ hoặc thất lạc do exporter.

## 2. Vòng đời một custom observation

Một Observation thường được tạo và bắt đầu trước thao tác, có thể thêm key-values hoặc event, ghi nhận exception rồi kết thúc. `observe(...)` giúp quản lý các bước thường gặp:

~~~mermaid
flowchart LR
    A["Tạo Observation"] --> B["Gắn low/high-cardinality key-values"]
    B --> C["start + mở Scope"]
    C --> D["Thực thi nghiệp vụ"]
    D --> E{"Có exception?"}
    E -- Có --> F["Ghi nhận error"]
    E -- Không --> G["Hoàn thành"]
    F --> H["Đóng Scope + stop"]
    G --> H
    H --> I["Handlers tạo metrics/spans theo cấu hình"]
~~~

Để bảo đảm metadata có mặt khi handler xử lý lifecycle, hãy **gắn các thuộc tính đã biết trước khi gọi `observe(...)`** hoặc trước `start()`. Khi giá trị chỉ có ở cuối thao tác, có thể bổ sung trong khi Observation đang chạy, nhưng phải kiểm tra handler tương ứng có sử dụng metadata thêm muộn không. Đừng dựa vào việc chỉnh sửa context sau khi `stop()`.

### 2.1. Ví dụ tối giản: gắn một mã lần thử

Giả sử `InventoryGateway` là adapter gọi đến hệ thống tồn kho. Chúng ta dùng một mã giả danh, được sinh nội bộ cho mỗi lần gọi, thay vì đưa mã đơn hàng hoặc dữ liệu người dùng vào span.

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class InventoryReservationService {
    private final ObservationRegistry observationRegistry;
    private final InventoryGateway inventoryGateway;

    public InventoryReservationService(
            ObservationRegistry observationRegistry,
            InventoryGateway inventoryGateway) {
        this.observationRegistry = observationRegistry;
        this.inventoryGateway = inventoryGateway;
    }

    public void reserve(String sku, int quantity) {
        String attemptId = UUID.randomUUID().toString();

        Observation.createNotStarted("inventory.reserve", observationRegistry)
                .lowCardinalityKeyValue("inventory.operation", "reserve")
                .lowCardinalityKeyValue("inventory.channel", "web")
                .highCardinalityKeyValue("inventory.attempt.id", attemptId)
                .observe(() -> inventoryGateway.reserve(sku, quantity));
    }
}

interface InventoryGateway {
    void reserve(String sku, int quantity);
}
~~~

Trong ví dụ:

1. `inventory.reserve` là **tên Observation ổn định**, không bao gồm request ID.
2. `inventory.operation=reserve` và `inventory.channel=web` là **low-cardinality tags**, thích hợp để tổng hợp metrics theo nhóm.
3. `inventory.attempt.id` là **high-cardinality tag**; mỗi lần giữ hàng nhận một UUID mới. Tracing handler có thể gắn nó thành span attribute.
4. `observe(...)` chạy lambda trong scope của Observation; khi có exception, API tiện ích ghi nhận lỗi rồi dừng Observation, sau đó exception tiếp tục được ném ra.

Ví dụ dùng `web` cố định để dễ theo dõi. Trong ứng dụng thật có cả API và job, hãy truyền một giá trị **đã chuẩn hóa** (`web` hoặc `batch`) vào service; không lấy chuỗi tự do từ request làm low-cardinality tag.

### 2.2. API thường dùng

| API | Ý nghĩa | Khi dùng |
| --- | --- | --- |
| `Observation.createNotStarted(name, registry)` | Tạo Observation với tên ổn định, chưa bắt đầu | Định nghĩa ranh giới thao tác |
| `lowCardinalityKeyValue(key, value)` | Thêm một key-value có số giá trị hữu hạn | Metric labels và thuộc tính phân nhóm |
| `highCardinalityKeyValue(key, value)` | Thêm một key-value nhiều giá trị | Truy vết lần thực thi cụ thể |
| `lowCardinalityKeyValues(KeyValues)` | Thêm một nhóm key-values low cardinality | Khi đã chuẩn bị sẵn nhiều key |
| `highCardinalityKeyValues(KeyValues)` | Thêm một nhóm key-values high cardinality | Khi có nhiều thuộc tính liên quan |
| `observation.error(exception)` | Ghi nhận lỗi trong thao tác | Khi quản lý lifecycle bằng tay |
| `observe(Runnable)` / `observe(Supplier<T>)` | Chạy thao tác, quản lý lifecycle và scope | Cách ngắn gọn cho nhiều nghiệp vụ |

Các method và overload cụ thể phải tương thích với phiên bản Micrometer mà Spring Boot đang sử dụng. Khi có hợp đồng key chung, nên đặt các tên key thành hằng số hoặc sử dụng `KeyName` trong tài liệu hóa Observation để tránh lỗi đánh máy.

## 3. Gắn nhiều high-cardinality key-values

Khi một lần gọi cần nhiều thuộc tính để phân tích, dùng `KeyValues` giúp mô tả một nhóm metadata. Ví dụ hai giá trị **không nhạy cảm**: mã thử gọi và loại tác vụ con.

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;

KeyValues traceDetails = KeyValues.of(
        KeyValue.of("inventory.attempt.id", attemptId),
        KeyValue.of("inventory.step.reference", stepReference));

Observation.createNotStarted("inventory.reserve", observationRegistry)
        .lowCardinalityKeyValue("inventory.channel", "batch")
        .highCardinalityKeyValues(traceDetails)
        .observe(() -> inventoryGateway.reserve(sku, quantity));
~~~

`stepReference` trong ví dụ là mã nội bộ giả danh dành cho lần chạy, có thể có rất nhiều giá trị. Chỉ gắn khi dữ liệu thật sự hỗ trợ điều tra. Dù `KeyValues` cho phép gắn nhiều thuộc tính, không nên sao chép toàn bộ request body, đối tượng domain hoặc stack trace vào tags.

### 3.1. Đặt tên key ổn định

Nên đặt tên dạng chữ thường, có namespace và phân đoạn có nghĩa, chẳng hạn `inventory.attempt.id`, `inventory.operation`. Không đổi giữa `attemptId`, `attempt_id` và `inventory.attempt.id` tùy người viết. Tránh đưa dữ liệu động vào **tên key**; giá trị thay đổi theo request, còn tên key phải ổn định.

Trường `exception.message` thường có nhiều giá trị, có thể chứa payload hoặc dữ liệu nhạy cảm, nên không gắn tùy tiện. Hãy dùng `error.type` hay `failure.reason` với tập giá trị cố định, nếu cần tổng hợp theo loại lỗi; thông tin chi tiết chỉ đưa vào dữ liệu điều tra theo chính sách lưu trữ phù hợp.

## 4. Khi cần hợp đồng chung: dùng Observation.Context và ObservationConvention

Gắn key-value trực tiếp tiện lợi với thao tác nhỏ. Tuy nhiên, khi nhiều service/module cùng instrument `inventory.reserve`, tên tag có thể bị viết khác nhau. Lúc đó nên tách logic chuyển dữ liệu nghiệp vụ thành tags ra **ObservationConvention**; dữ liệu của mỗi lần thực thi được lưu trong **Observation.Context** có kiểu rõ ràng.

### 4.1. Khai báo context nghiệp vụ

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;

final class InventoryReserveContext extends Observation.Context {
    private final String channel;
    private final String attemptId;

    InventoryReserveContext(String channel, String attemptId) {
        if (!"web".equals(channel) && !"batch".equals(channel)) {
            throw new IllegalArgumentException("Unsupported channel");
        }
        this.channel = channel;
        this.attemptId = attemptId;
    }

    String channel() {
        return channel;
    }

    String attemptId() {
        return attemptId;
    }
}
~~~

### 4.2. Convention tạo các KeyValues nhất quán

~~~java
package com.example.orders.observation;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

final class InventoryReserveConvention
        implements ObservationConvention<InventoryReserveContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof InventoryReserveContext;
    }

    @Override
    public String getName() {
        return "inventory.reserve";
    }

    @Override
    public String getContextualName(InventoryReserveContext context) {
        return "reserve inventory";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.channel", context.channel()),
                KeyValue.of("inventory.operation", "reserve"));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(InventoryReserveContext context) {
        return KeyValues.of(
                KeyValue.of("inventory.attempt.id", context.attemptId()));
    }
}
~~~

### 4.3. Tạo Observation với convention

~~~java
InventoryReserveContext context =
        new InventoryReserveContext(channel, attemptId);

Observation.createNotStarted(
        null,                             // Chưa dùng custom convention.
        new InventoryReserveConvention(), // Default convention.
        () -> context,
        observationRegistry)
    .observe(() -> inventoryGateway.reserve(sku, quantity));
~~~

Trong factory hỗ trợ convention, thứ tự lựa chọn phổ biến là **custom convention được truyền trực tiếp**, rồi **global convention trong registry hỗ trợ context**, rồi **default convention** được truyền vào. Vì thế, nếu ứng dụng đăng ký một `GlobalObservationConvention` phù hợp, nó có thể thay default trong ví dụ. Khi cần bảo đảm metadata hiển thị đúng, phải xác minh convention thực sự được chọn.

Một enum triển khai `ObservationDocumentation` có thể công bố tên thao tác, tên key low/high cardinality và default convention để sinh tài liệu instrumentation. Nó hỗ trợ **hợp đồng**, nhưng không tự chặn mọi tag sai ở runtime và không thay thế kiểm thử.

## 5. Đưa metadata vào tracing và liên kết logs

Sơ đồ một request tạo đơn hàng:

~~~mermaid
sequenceDiagram
    participant User as Client
    participant Order as order-service
    participant Inventory as inventory-service
    participant Backend as Trace backend
    User->>Order: POST /orders
    Note over Order: HTTP server span
    Order->>Order: Observation inventory.reserve
    Note over Order: high: inventory.attempt.id=attempt-...
    Order->>Inventory: HTTP + traceparent
    Inventory-->>Order: Timeout hoặc kết quả
    Order-->>Backend: Export span nếu được sampling giữ
    Order-->>User: HTTP response
~~~

Khi tracing bridge/handler tạo span cho custom observation, high-cardinality attributes giúp phân biệt **lần thử giữ hàng nào** trong trace. Nếu dùng OpenTelemetry qua Micrometer Tracing, dữ liệu còn phải qua exporter (ví dụ OTLP), Collector và trace backend để xuất hiện trong giao diện truy vấn.

Một request có thể đồng thời có:

- **Metrics:** thời gian xử lý `inventory.reserve` và tỷ lệ lỗi, phân nhóm theo `inventory.channel`.
- **Trace:** các span HTTP server, custom `inventory.reserve` và HTTP client, với trace ID chung nếu context được giữ.
- **Logs:** sự kiện timeout có mã lỗi hoặc tên dependency, và trace ID/span ID khi logging được tích hợp với tracing.

### 5.1. High-cardinality attribute không tự truyền sang service khác

W3C Trace Context thường mang `traceparent` (và có thể `tracestate`) qua HTTP để liên kết span giữa các service. **Span attribute** như `inventory.attempt.id` không mặc nhiên nằm trong `traceparent`, vì vậy dịch vụ nhận sẽ **không tự có giá trị đó** chỉ vì service gọi đã gắn `highCardinalityKeyValue`.

Nếu thật sự cần một metadata được truyền sang downstream:

1. Xác định rõ tác dụng nghiệp vụ, phạm vi và chính sách dữ liệu.
2. Chọn cơ chế truyền phù hợp, chẳng hạn một header nghiệp vụ được kiểm soát hoặc baggage đã cấu hình cho tracing.
3. Giới hạn trường được phép truyền, kích thước, số lượng và tuổi thọ dữ liệu; tránh mang token, email và nội dung cá nhân.
4. Kiểm tra cả hai đầu rằng giá trị tới đúng nơi, không tạo fan-out metadata không cần thiết.

Đừng dùng baggage chỉ để “chuyển tất cả span attributes” vì metadata sẽ đi qua nhiều dịch vụ và có thể bị lộ ở log, proxy hoặc trace backend. Khi chỉ cần tương quan, **trace ID** thường đã đủ làm khóa nối giữa các tín hiệu.

### 5.2. Giữ scope trong xử lý bất đồng bộ

Khi mã chuyển từ thread xử lý HTTP sang `@Async`, executor, Reactor hay messaging, trace context có thể không tự đi theo. Vì vậy, custom observation trong tác vụ async có thể trở thành trace gốc mới hoặc không nằm dưới HTTP span ban đầu.

Trong Spring Boot, nên dùng client HTTP do Spring quản lý để nhận instrumentation tương ứng. Với executor, thiết lập context propagation theo phiên bản Spring Framework/Micrometer đang dùng (ví dụ `ContextPropagatingTaskDecorator` của Spring Framework 6.1+) và kiểm tra kết quả ở backend. **Gắn high-cardinality key không sửa được lỗi mất context.**

### 5.3. Ghi logs có liên kết nhưng không lộ metadata

Ví dụ log có cấu trúc (dữ liệu giả định):

~~~text
2026-11-22T10:15:23Z WARN service=order-service
traceId=9cd1... spanId=7b21... event=inventory_reservation_failed
reason=upstream_timeout dependency=inventory-service duration_ms=2400
~~~

Tra trace bằng trace ID để xem span `inventory.reserve` và các attributes; sau đó quay lại log theo cùng trace ID để xem thông tin timeout. Không cần đưa toàn bộ các high-cardinality attributes vào log: giữ đủ tín hiệu để điều tra và tuân thủ chính sách bảo mật, retention và truy cập.

## 6. Thiết lập môi trường Spring Boot để quan sát kết quả

Trong ứng dụng Spring Boot tích hợp Micrometer, có thể dùng Actuator và thêm các registry/tracing bridge phù hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    // Khi cần distributed tracing dùng OpenTelemetry:
    implementation 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'

    testImplementation 'io.micrometer:micrometer-observation-test'
}
~~~

Một cấu hình **minh họa cho Spring Boot 3.x ở môi trường phát triển**, giả sử có OTLP Collector đang lắng nghe tại localhost:

~~~yaml
spring:
  application:
    name: order-service

management:
  endpoints:
    web:
      exposure:
        include: "health,prometheus"
  tracing:
    sampling:
      probability: 1.0 # Chỉ để kiểm thử, tăng cơ hội quan sát từng trace
  otlp:
    tracing:
      endpoint: http://localhost:4318/v1/traces

logging:
  pattern:
    level: "%5p [traceId=%X{traceId:-},spanId=%X{spanId:-}]"
~~~

Lưu ý:

- Endpoint `/actuator/prometheus` chỉ có nếu registry Prometheus và exposure phù hợp; trong production cần kiểm soát truy cập và network.
- `probability: 1.0` giúp giữ trace trong bài thực hành nhưng làm tăng lượng trace. Production cần chọn sampling theo lưu lượng, chi phí và mục tiêu điều tra.
- Cấu hình OTLP chỉ xác định nơi gửi; Collector và backend vẫn cần được chạy, truy cập được và cấu hình đúng.
- Tên thuộc tính, cách cấu hình tracing và auto-configuration thay đổi giữa các dòng Spring Boot/Micrometer; đối chiếu với phiên bản dự án thực tế.
- Ví dụ pattern logging chỉ minh họa correlation qua MDC; nếu ứng dụng dùng JSON logging hoặc Logback tùy chỉnh, hãy kiểm tra output thực tế.

**Đừng suy ra rằng high-cardinality metadata sẽ có ở backend chỉ vì đã viết code.** Cần cả instrumentation, handlers, sampling, exporter và backend phù hợp.

## 7. Sampling và khả năng nhìn thấy metadata

Một high-cardinality attribute thường chỉ hỗ trợ điều tra tốt khi span chứa nó được **ghi nhận và lưu lại**. Nếu ứng dụng lấy mẫu 10% trace, một request lỗi cụ thể có thể nằm trong 90% request không được lưu trace.

| Tình huống | Có thể xảy ra | Kết luận đúng |
| --- | --- | --- |
| Observation chạy, tracing chưa được cấu hình | Có thể có metrics nhưng không có span | Kiểm tra handler/bridge |
| Tracing có cấu hình, request không được sampling giữ | Không có trace trong backend | Không khẳng định request chưa chạy |
| Có span nhưng thiếu attribute | Convention/tag thêm sai thời điểm hoặc handler không dùng key | Kiểm tra context và handler |
| Có span trong ứng dụng nhưng exporter lỗi | Backend không có trace tương ứng | Kiểm tra hàng đợi, lỗi exporter và Collector |
| Có trace nhưng đứt giữa hai service | Mất propagation hoặc scope async | Kiểm tra `traceparent`, client và executor |
| Có trace và high attribute | Có thể tìm request qua attribute nếu backend hỗ trợ lập chỉ mục/tìm kiếm | Hiệu năng truy vấn còn phụ thuộc backend và cấu hình |

**Head-based sampling** quyết định sớm nên có thể bỏ sót lỗi hiếm. **Tail-based sampling** có thể giữ trace theo trạng thái lỗi hoặc độ trễ sau khi thu thập span, nhưng cần pipeline Collector phù hợp và tốn tài nguyên hơn. Với cả hai cách, **metrics và các logs phù hợp** vẫn cần thiết để phát hiện xu hướng trên toàn bộ traffic.

Ngoài sampling, hãy xem xét **retention, giới hạn số span attributes, giới hạn độ dài value, mức quota ingest và chính sách indexing**. Một value quá dài có thể bị cắt hoặc không được lưu, và một tag xuất hiện trên span không có nghĩa backend hỗ trợ lọc theo tag đó với chi phí thấp.

## 8. Quy tắc bảo mật khi gắn metadata

Traces có thể được chia sẻ rộng rãi cho đội phát triển và vận hành. Vì vậy, **high cardinality không phải khu vực an toàn để lưu thông tin nhạy cảm**.

| Dữ liệu đề xuất | Quyết định | Giải thích |
| --- | --- | --- |
| UUID ngẫu nhiên cho một lần thử | Có thể dùng | Hữu ích để tìm trace; không tự mang thông tin người dùng |
| Tên thao tác hoặc loại lỗi chuẩn hóa | Dùng low-cardinality khi cần | Dễ tổng hợp và ít biến thể |
| Order ID thật | Cân nhắc và kiểm tra quy định | Có thể trở thành định danh liên quan đến người dùng |
| Email, số điện thoại, địa chỉ | Không thu thập mặc định | Dữ liệu cá nhân, không cần cho mọi span |
| Access token, cookie, mật khẩu | Không thu thập | Bí mật xác thực |
| Request/response body nguyên bản | Tránh thu thập | Có thể chứa dữ liệu nhạy cảm và quá lớn |
| Exception message không kiểm soát | Không gắn tự do | Có thể chứa SQL, payload hoặc định danh |

Các biện pháp nên thực hiện:

1. **Thu thập tối thiểu:** mỗi key phải có lý do sử dụng khi điều tra.
2. **Giả danh và chuẩn hóa:** ưu tiên ID nội bộ không có khả năng suy ra dữ liệu cá nhân; không dùng hash thô của dữ liệu bí mật làm “ẩn danh”.
3. **Giới hạn kích thước:** quy định độ dài tối đa cho value và số lượng key trên mỗi span.
4. **Kiểm soát quyền truy cập:** giới hạn người xem traces, logs và khả năng truy vấn theo attributes.
5. **Đặt retention và chính sách xóa:** không giữ dữ liệu lâu hơn nhu cầu và quy định.
6. **Xem xét propagation:** một key được truyền đi sẽ qua nhiều thành phần hơn một attribute chỉ ở span hiện tại.

Không tạo high-cardinality metadata từ chuỗi do người dùng cung cấp mà không có quy trình kiểm tra, giới hạn độ dài và phân loại dữ liệu.

## 9. Kiểm thử metadata bằng TestObservationRegistry

`micrometer-observation-test` cung cấp `TestObservationRegistry` để kiểm tra các Observation đã chạy mà **không cần khởi động Collector hay trace backend**. Với ví dụ `InventoryReservationService`, test có thể kiểm tra rằng metadata được ghi đúng nhóm cardinality.

~~~java
package com.example.orders.observation;

import io.micrometer.observation.Observation;
import io.micrometer.observation.tck.TestObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class HighCardinalityObservationTest {

    @Test
    void recordsAttemptIdAsHighCardinalityMetadata() {
        TestObservationRegistry registry = TestObservationRegistry.create();

        Observation.createNotStarted("inventory.reserve", registry)
                .lowCardinalityKeyValue("inventory.channel", "web")
                .highCardinalityKeyValue("inventory.attempt.id", "attempt-demo-001")
                .observe(() -> { /* giả lập giữ hàng thành công */ });

        assertThat(registry)
                .hasSingleObservationThat()
                .hasBeenStopped()
                .hasNameEqualTo("inventory.reserve")
                .hasLowCardinalityKeyValue("inventory.channel", "web")
                .hasHighCardinalityKeyValue(
                        "inventory.attempt.id", "attempt-demo-001")
                .doesNotHaveError();
    }
}
~~~

Test trên chứng minh tên, vòng đời và metadata trên **Observation runtime**. Nó không chứng minh metadata đã có trong OpenTelemetry span, đã được exporter gửi hoặc đã được backend lập chỉ mục.

### 9.1. Những kiểm thử nên bổ sung

- **Đường đi lỗi:** lambda ném exception; xác minh Observation được dừng và lỗi được ghi nhận theo API testing của version đang dùng.
- **Giá trị channel:** chỉ cho phép `web` và `batch`; tránh nhãn do client tùy ý cung cấp.
- **Không rò rỉ tag:** dùng metrics registry thích hợp để chứng minh `inventory.attempt.id` không xuất hiện trong metric label.
- **Convention:** kiểm tra default/global/custom convention thực sự chọn đúng tên và phân loại key.
- **Tracing integration:** kiểm tra một trace đã được ghi trong môi trường kiểm thử với sampling phù hợp, có attribute cần thiết và liên kết span đúng.
- **Propagated context:** khi qua HTTP và async, kiểm tra trace ID của upstream/downstream đồng nhất nếu luồng thiết kế cần liên kết.
- **Bảo mật:** xác minh không có token, dữ liệu cá nhân hoặc body nhạy cảm trong traces và logs.

Ví dụ quan sát ở runtime:

~~~bash
curl -i http://localhost:8080/actuator/health
curl -s http://localhost:8080/actuator/prometheus
~~~

Với Prometheus, timer có thể xuất hiện thành các series tương ứng thời gian và số lần, nhưng **không nên có label `inventory_attempt_id`**. Tên metric cụ thể có thể được đổi theo quy ước naming của registry; nếu chưa thấy metric, hãy kích hoạt ít nhất một lần thực thi rồi kiểm tra cấu hình registry và handler.

## 10. Điều tra một request chậm có metadata high cardinality

Giả sử p95 của API tạo đơn tăng từ 450 ms lên 2,8 giây. Một trace được lấy mẫu cho thấy span `inventory.reserve` kéo dài 2,4 giây và có thuộc tính `inventory.attempt.id=attempt-demo-001`. Trong log cùng trace ID xuất hiện lỗi `upstream_timeout`.

Quy trình phân tích có cơ sở:

1. **Metrics xác định quy mô:** xem request rate, tỷ lệ 5xx, p95/p99 và sự thay đổi theo phiên bản triển khai, phân nhóm `channel` nếu hợp đồng đã thiết kế.
2. **Trace xác định vị trí chậm:** mở trace chậm đã được giữ, kiểm tra timeline HTTP server → custom `inventory.reserve` → HTTP client → upstream.
3. **High-cardinality metadata nhận diện lần thử:** dùng `inventory.attempt.id` để phân biệt lần gọi đang điều tra với các lần retry hoặc bước xử lý khác, nếu backend cho phép truy vấn attribute này.
4. **Logs cung cấp thông tin sự kiện:** tìm log theo trace ID, kiểm tra mã timeout, loại phụ thuộc, retry và các cảnh báo liên quan.
5. **Metrics của phụ thuộc xác minh xu hướng:** tìm dấu hiệu nghẽn connection pool, tăng queue hoặc timeout của `inventory-service`.
6. **Khắc phục và đo lại:** chỉnh timeout, giới hạn concurrency, rollback hoặc sửa upstream theo nguyên nhân; kiểm tra error rate và latency sau thay đổi.

Không dùng một trace làm bằng chứng rằng **mọi request** cùng bị lỗi. Metrics phản ánh xu hướng toàn hệ thống; trace mô tả một đường đi; logs giúp kiểm tra điều kiện cụ thể. Nếu trace không tồn tại vì sampling, vẫn cần điều tra với metrics và log đã chuẩn hóa.

### 10.1. Nếu retry tạo nhiều lần thử thì sao?

Nếu một request HTTP gọi `inventory-service` tối đa ba lần, có thể có **một parent observation cho toàn bộ hành động** và **một child observation cho mỗi lần thử**. Mỗi child mang mã `inventory.attempt.id` riêng hoặc một số thứ tự retry phù hợp.

~~~mermaid
flowchart TB
    Parent["POST /orders - trace ID chung"] --> Reserve["inventory.reserve tổng thể"]
    Reserve --> A1["attempt 1: timeout"]
    Reserve --> A2["attempt 2: timeout"]
    Reserve --> A3["attempt 3: success"]
    A1 --> Attr1["high: attempt.id=A"]
    A2 --> Attr2["high: attempt.id=B"]
    A3 --> Attr3["high: attempt.id=C"]
~~~

Thiết kế này có ích khi cần đo rõ overhead của retry, nhưng không nên tạo span cho mọi vòng lặp nhỏ. Mỗi span có chi phí và phải có ranh giới kỹ thuật đủ ý nghĩa. Số thứ tự retry `1`, `2`, `3` đôi khi đã đủ để giải thích thứ tự; không cần sinh thêm ID nếu không có nhu cầu tương quan.

## 11. Những lỗi thường gặp

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Đưa request ID vào `lowCardinalityKeyValue` | Metrics có số series rất lớn | Chuyển sang high cardinality nếu thực sự cần, hoặc bỏ |
| Gắn email/token vào `highCardinalityKeyValue` | Dữ liệu nhạy cảm vào trace backend | Không thu thập; dùng mã giả danh có kiểm soát |
| Nhầm high-cardinality metadata với baggage | Downstream không nhận giá trị mong đợi | Thiết kế propagation riêng, có allowlist |
| Đổi tên key tùy ý giữa các service | Khó tìm kiếm và so sánh | Đặt tên theo convention/hợp đồng chung |
| Gắn attribute sau `stop()` | Handler có thể không ghi nhận | Đính kèm trước hoặc trong lifecycle đúng thời điểm |
| Cho rằng có metadata là sẽ có trace | Dữ liệu có thể bị sampling/exporter bỏ qua | Xác minh tracing bridge, sampling, Collector/backend |
| Copy nguyên request body thành tag | Chi phí cao, có thể lộ dữ liệu | Chỉ lấy metadata thiết yếu, rút gọn và kiểm tra |
| Dùng trace làm nhật ký nghiệp vụ bền vững | Mất dữ liệu khi sampling/retention | Lưu trạng thái nghiệp vụ ở nguồn dữ liệu phù hợp |
| Thêm quá nhiều attributes trên mỗi span | Tăng dung lượng và có thể bị giới hạn | Có ngân sách metadata, giới hạn số lượng/độ dài |
| Chỉ unit test Observation | Không thấy lỗi exporter/propagation | Thêm kiểm thử tích hợp pipeline phù hợp |

## 12. Checklist trước khi đưa lên production

| Điều cần xác minh | Bằng chứng mong đợi |
| --- | --- |
| High-cardinality key có mục đích rõ | Biết câu hỏi điều tra cần dùng key |
| Có hợp đồng tên key ổn định | Documentation và convention nhất quán |
| Không chứa dữ liệu nhạy cảm | Đã kiểm tra nguồn giá trị, giới hạn độ dài và phân quyền |
| Low cardinality không chứa ID động | Metrics có tập nhãn hữu hạn |
| Metadata được gắn đúng lifecycle | `TestObservationRegistry` kiểm tra tên, tags và stop |
| Metrics được xác nhận riêng | Query/endpoint có dữ liệu và không chứa high-cardinality label |
| Tracing được xác nhận riêng | Span/attributes xuất hiện trong backend khi được sampling |
| Propagation qua HTTP/async hoạt động | Trace có parent-child hợp lý |
| Logs có correlation nhưng an toàn | Có trace ID khi cần, không sao chép metadata nhạy cảm |
| Exporter và retention được theo dõi | Có tín hiệu lỗi pipeline và giới hạn lưu trữ |

## 13. Bài thực hành

**Bối cảnh:** ứng dụng Spring Boot có endpoint `POST /orders`, gọi `inventory-service` rồi lưu đơn. Khi upstream timeout, đội trực muốn phân biệt từng lần thử nhưng vẫn giữ metrics có cardinality thấp.

**Nhiệm vụ:**

1. Thêm một custom observation `inventory.reserve` bao quanh lời gọi giữ hàng.
2. Gắn `inventory.channel` có tập giá trị `web` hoặc `batch` bằng `lowCardinalityKeyValue`.
3. Sinh một UUID giả danh cho mỗi lần thử và gắn `inventory.attempt.id` bằng `highCardinalityKeyValue`.
4. Viết unit test với `TestObservationRegistry` kiểm tra tên, metadata high/low, lifecycle và trường hợp ném lỗi.
5. Kiểm tra metrics từ registry phù hợp và chứng minh ID của lần thử không trở thành nhãn series.
6. Cấu hình tracing thử nghiệm với sampling phù hợp và exporter đến backend, tìm một span có thuộc tính `inventory.attempt.id`.
7. Thử gọi qua HTTP service khác và qua executor; giải thích khi nào trace context bị đứt và tại sao high-cardinality metadata không tự truyền qua HTTP.
8. Tạo lỗi timeout, đối chiếu metrics, trace và log theo trace ID; ghi lại phần dữ liệu có thể thiếu do sampling và exporter.
9. Đánh giá rủi ro nếu một đồng nghiệp đề xuất thay `attempt.id` bằng email khách hàng hoặc request body.

**Kết quả mong đợi:** mã instrumentation, test kết quả quan sát, ảnh/truy vấn metric không chứa ID động, một span mẫu có high-cardinality attribute (nếu backend đã nhận), và bản phân tích ngắn về timeout, propagation, sampling và quyền riêng tư.

## 14. Ghi nhớ

Gắn **high-cardinality metadata** vào custom Observation giúp diễn giải **một lần thực thi cụ thể** trong distributed trace. API `highCardinalityKeyValue(...)` thích hợp cho thông tin có nhiều giá trị cần phục vụ điều tra; `lowCardinalityKeyValue(...)` dành cho nhãn có tập giá trị nhỏ để tổng hợp metrics. Với hệ thống lớn, dùng `Observation.Context` và `ObservationConvention` để giữ hợp đồng tên/key nhất quán.

High-cardinality metadata **không tự là baggage, không tự được ghi vào logs, không bảo đảm trace được lưu và không phải nơi lưu dữ liệu nhạy cảm**. Để theo dõi lỗi, độ trễ và hành vi ứng dụng Spring Boot trong production, cần phối hợp metadata đúng cách với context propagation, sampling, exporter, metrics, logs và quy trình kiểm thử rõ ràng.

**Tài liệu tham khảo:**

- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Testing Observations](https://docs.micrometer.io/micrometer/reference/observation/testing.html)
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
