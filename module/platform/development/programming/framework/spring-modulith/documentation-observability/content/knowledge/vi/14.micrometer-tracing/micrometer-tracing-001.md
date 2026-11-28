# Vai trò của Micrometer Tracing

## Mục tiêu học tập

Trong học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, Spring Modulith được sử dụng để mô tả ranh giới application module và quan sát cách các module tương tác trong ứng dụng Spring Boot. Bài này giới thiệu vai trò của **Micrometer Tracing** trong bức tranh đó: từ một lần thực thi trong ứng dụng đến trace có thể theo dõi xuyên qua nhiều thành phần hoặc dịch vụ.

Sau bài học, bạn có thể:

1. Giải thích Micrometer Tracing là gì và vì sao nó đóng vai trò **lớp API trung gian** giữa ứng dụng với tracer implementation như OpenTelemetry hoặc Brave.
2. Phân biệt **trace, span, trace ID, span ID, parent span, attributes, events và baggage**.
3. Mô tả cách Micrometer Observation kết hợp Micrometer Tracing để tạo spans từ những hoạt động đã được instrument.
4. Hiểu vai trò của **Tracer, Propagator, sampler, exporter và tracing backend** trong vòng đời distributed trace.
5. Cấu hình tracing trong Spring Boot theo dependency và property phù hợp với phiên bản đang sử dụng.
6. Giải thích cách Spring Modulith tạo module spans ở ranh giới application module và cách các spans này xuất hiện trong trace.
7. Duy trì trace context qua HTTP, executor, asynchronous listener và reactive pipeline.
8. Liên kết log với trace bằng MDC/correlation ID, đồng thời sử dụng baggage có kiểm soát.
9. Đọc trace để điều tra độ trễ và lỗi mà không nhầm tín hiệu quan sát với bằng chứng về tính đúng đắn nghiệp vụ.

**Phạm vi:** Nội dung tập trung vào Micrometer Tracing trong hệ sinh thái Spring Boot và Spring Modulith. Tên dependency, starter và property cấu hình có thể thay đổi giữa các major version của Spring Boot/Micrometer; hãy đối chiếu tài liệu đúng release của dự án trước khi áp dụng nguyên mẫu.

---

## 1. Bài toán: biết một yêu cầu đã đi qua những đâu

Giả sử một ứng dụng thương mại điện tử được tổ chức thành các application module:

- **orders:** tiếp nhận đơn và điều phối vòng đời đơn hàng;
- **inventory:** giữ và cập nhật tồn kho;
- **payments:** làm việc với cổng thanh toán;
- **shipping:** chuẩn bị giao hàng.

Một request tạo đơn có thể gọi API của inventory, ghi trạng thái đơn, phát event và kích hoạt listener của payments. Nếu chỉ xem log riêng lẻ, kỹ sư vận hành phải ghép các dòng log từ nhiều class và thread để trả lời:

- Bước nào mất nhiều thời gian nhất?
- Lời gọi nào gây lỗi đầu tiên?
- Module nào đã nhận event?
- Request có gọi ra dịch vụ ngoài không?
- Vì sao một listener bắt đầu xử lý muộn sau khi request ban đầu đã trả response?

**Distributed tracing** giải quyết bài toán tương quan này bằng cách biểu diễn các hoạt động liên quan thành một **trace** gồm nhiều **span**. Mỗi span mô tả một đơn vị công việc có thời điểm bắt đầu, kết thúc và metadata riêng. Quan hệ cha–con giữa các span cho thấy một thao tác đã gọi hoặc tạo ra thao tác khác như thế nào.

~~~mermaid
flowchart LR
    A["HTTP request"] --> B["orders"]
    B --> C["inventory"]
    B --> D["Application event"]
    D --> E["payments listener"]
    E --> F["Payment provider"]
    A -.-> T["Một trace"]
    B -.-> T
    C -.-> T
    D -.-> T
    E -.-> T
    F -.-> T
~~~

Sơ đồ trên là một **luồng minh họa**. Việc các bước thực sự xuất hiện trong cùng trace phụ thuộc instrumentation, propagation và sampling của hệ thống. Một mũi tên nghiệp vụ không tự động tương ứng với một span; phải có thư viện hoặc code tạo observation/span tại điểm đó.

## 2. Micrometer Tracing là gì?

**Micrometer Tracing** là một facade/API tracing của hệ sinh thái Micrometer. Nó cung cấp một bộ kiểu và thao tác thống nhất để ứng dụng tạo, quản lý và truyền thông tin trace mà không phải viết toàn bộ logic phụ thuộc trực tiếp vào một thư viện tracing cụ thể.

Các tracer implementation phổ biến trong hệ sinh thái này gồm:

- **OpenTelemetry:** hệ sinh thái tracing/telemetry rộng, thường xuất dữ liệu qua OTLP tới collector hoặc backend hỗ trợ OTLP.
- **OpenZipkin Brave:** tracer implementation thuộc hệ sinh thái Zipkin, thường dùng với Zipkin reporter/backend.

Ứng dụng có thể sử dụng API Micrometer Tracing như `Tracer`, `Span` và `Propagator`. Một **bridge** kết nối API đó với implementation cụ thể, còn exporter/reporter đưa spans đã hoàn tất tới hệ thống nhận dữ liệu.

### 2.1. Micrometer Tracing không phải backend

Phân biệt các thành phần:

| Thành phần | Trách nhiệm | Ví dụ |
| --- | --- | --- |
| **Micrometer Tracing API** | API trung gian để tạo và quản lý trace/span. | `Tracer`, `Span`, `Propagator`. |
| **Tracer implementation** | Thực thi việc tạo span, quản lý context và lấy mẫu. | OpenTelemetry SDK, Brave. |
| **Bridge** | Nối API Micrometer với tracer implementation. | `micrometer-tracing-bridge-otel`, `micrometer-tracing-bridge-brave` trong các cấu hình tương ứng. |
| **Exporter/reporter** | Gửi spans đã hoàn tất ra ngoài. | OTLP exporter, Zipkin reporter. |
| **Collector/backend** | Nhận, lưu, truy vấn và hiển thị traces. | OpenTelemetry Collector, Zipkin, Jaeger hoặc nền tảng quan sát tương thích. |
| **UI truy vấn** | Cho phép tìm trace, xem timeline, lọc span. | Zipkin UI, Jaeger UI, Grafana Tempo qua Grafana. |

Chỉ thêm API hoặc bridge **không đồng nghĩa** đã có backend nhận và hiển thị trace. Nếu exporter chưa được cấu hình, dữ liệu có thể chỉ tồn tại trong tiến trình hoặc không được gửi tới nơi nào.

### 2.2. Vì sao dùng facade?

Một thư viện nghiệp vụ hoặc module không nên buộc toàn bộ mã nguồn phụ thuộc vào một vendor tracing cụ thể nếu không cần tính năng riêng của vendor đó. Micrometer Tracing tạo một lớp API tương đối nhất quán để:

- viết instrumentation ít phụ thuộc backend;
- thay đổi tracer implementation theo lựa chọn hạ tầng;
- tích hợp với Micrometer Observation và Spring Boot;
- dùng chung khái niệm span, context, propagation và baggage;
- kết hợp dữ liệu tracing với metrics/logs theo cách nhất quán.

Facade không làm mọi backend giống nhau hoàn toàn. Một số tính năng nâng cao, cấu hình sampling, baggage hoặc exporter vẫn phụ thuộc implementation và phiên bản.

## 3. Trace và span: hai khái niệm nền tảng

### 3.1. Trace là gì?

**Trace** là tập hợp những span có liên hệ với cùng một hoạt động được theo dõi, thường đại diện cho một request hoặc workflow xuyên qua nhiều thành phần/dịch vụ.

Một trace có:

- **trace ID:** định danh của trace, được dùng để tương quan các span trong trace;
- một hoặc nhiều span;
- quan hệ cha–con hoặc quan hệ liên kết giữa các span;
- thời điểm và metadata của từng span.

Một trace không nhất thiết tương ứng với toàn bộ vòng đời nghiệp vụ. Ví dụ, một đơn hàng tồn tại nhiều ngày, trong khi mỗi HTTP request hoặc lần xử lý event có thể tạo một trace riêng. Muốn liên kết các trace thuộc cùng một đơn hàng, dùng business ID trong log/trace có chính sách phù hợp, không dùng trace ID thay cho order ID.

### 3.2. Span là gì?

**Span** biểu diễn một đơn vị công việc có phạm vi thời gian xác định. Span thường có:

- **span ID:** định danh riêng của span;
- **trace ID:** trace mà span thuộc về;
- **parent span ID** hoặc quan hệ parent phù hợp;
- tên mô tả thao tác;
- thời điểm bắt đầu và kết thúc, từ đó tính duration;
- attributes/tags;
- events hoặc annotations;
- trạng thái kết quả và thông tin lỗi khi được ghi nhận.

Ví dụ một trace xử lý đơn hàng:

~~~text
Trace: 4bf92f3577b34da6a3ce929d0e0e4736

Span A  HTTP POST /orders             0 ms ───────────── 180 ms
  Span B  orders.placeOrder            8 ms ─────── 145 ms
    Span C  inventory.reserve         22 ms ─── 51 ms
    Span D  payments.prepare           72 ms ───────── 132 ms
      Span E  POST payment-provider    85 ms ─── 119 ms
~~~

Các thời điểm và tên span chỉ mang tính minh họa. Trong trace thật, span có thể chồng lấn nếu các bước chạy song song hoặc bất đồng bộ.

### 3.3. Trace ID và span ID khác nhau thế nào?

| Định danh | Phạm vi | Vai trò |
| --- | --- | --- |
| **trace ID** | Một trace | Tìm tất cả span thuộc cùng trace. |
| **span ID** | Một span | Nhận diện một hoạt động cụ thể trong trace. |
| **parent span ID** | Quan hệ giữa span | Cho biết span được tạo trong ngữ cảnh của span nào. |
| **orderId** | Thực thể nghiệp vụ | Liên kết dữ liệu của cùng đơn hàng qua nhiều trace và thời gian. |
| **eventId** | Một event nghiệp vụ | Nhận diện event khi cần deduplicate hoặc đối soát. |

Một trace thường có nhiều span ID nhưng dùng chung trace ID. Một order ID có thể xuất hiện trong nhiều trace khác nhau vì khách hàng có thể xem đơn, thanh toán, hủy hoặc hoàn tiền qua nhiều request độc lập.

**Không sử dụng trace ID làm khóa nghiệp vụ hoặc idempotency key.** Trace ID phục vụ quan sát; khóa nghiệp vụ cần được quản lý bởi domain và persistence.

## 4. Quan hệ cha–con và cấu trúc phân tán

Khi một span đang là current span trong context, một span mới được tạo theo ngữ cảnh đó thường trở thành child span. Ví dụ:

- HTTP server span là span cha của logic xử lý request;
- module entry span là span con khi code đi vào API module;
- HTTP client span là span con khi ứng dụng gọi một dịch vụ khác;
- receiver span tại dịch vụ nhận tiếp tục trace nếu context từ request được trích xuất đúng.

~~~mermaid
flowchart TD
    A["Trace ID: T\nHTTP server span"] --> B["orders span"]
    B --> C["inventory module span"]
    B --> D["HTTP client span"]
    D --> E["Remote service server span"]
    B --> F["event processing span"]
~~~

Trong thực tế, một event bất đồng bộ có thể được biểu diễn bằng parent span hoặc span link tùy cơ chế messaging/tracing và cách instrumentation. Không nên mặc định mọi hoạt động bất đồng bộ đều phải là child trực tiếp của HTTP span đã phát event.

### 4.1. Trace context không chỉ là trace ID

Để nối spans xuyên qua ranh giới process, hệ thống cần truyền **trace context**. Context thường chứa trace ID, span ID và cờ liên quan sampling/trace state. Một propagator mã hóa context thành header hoặc carrier phù hợp, rồi phía nhận trích xuất nó để tiếp tục trace.

Ví dụ với chuẩn W3C Trace Context, HTTP request có thể mang header `traceparent` và tùy trường hợp `tracestate`. Các hệ thống khác có thể sử dụng định dạng B3. Định dạng cụ thể phụ thuộc tracer implementation và cấu hình propagation.

## 5. Vai trò của Micrometer Observation trong việc tạo span

Micrometer có hai API liên quan nhưng không đồng nhất:

- **Micrometer Observation:** mô hình hóa một hoạt động cần quan sát và quản lý context, convention, predicate, filter, handler.
- **Micrometer Tracing:** cung cấp API tracing chuyên biệt để quản lý span, tracer, propagation và baggage.

Observation là điểm tích hợp chung để cùng một instrumentation có thể tạo metrics và tracing. Khi có tracing handler phù hợp, một observation có thể được chuyển thành span.

Trong Spring Boot, các observation handlers được cấu hình tự động theo dependency. Hạ tầng tracing tích hợp với Observation Registry để tạo spans từ những observations được hoàn tất. Nhờ vậy, code có thể instrument một lần ở tầng Observation thay vì tự viết logic riêng cho từng backend.

~~~mermaid
flowchart TD
    A["Code / Spring Boot / Spring Modulith"] --> B["Micrometer Observation"]
    B --> C["Observation.Context"]
    C --> D["ObservationHandler"]
    D --> E["Meter handler"]
    D --> F["Tracing handler"]
    E --> G["MeterRegistry"]
    F --> H["Micrometer Tracing"]
    H --> I["Brave hoặc OpenTelemetry"]
    I --> J["Exporter / Reporter"]
    J --> K["Collector / Trace backend"]
~~~

Sơ đồ khái quát vai trò của từng lớp. Cấu hình thực tế có thể có composite handlers, nhiều registry hoặc nhiều đường xuất dữ liệu.

### 5.1. Low-cardinality và high-cardinality values

Observation cho phép thêm key-values với hai mức:

- **Low-cardinality:** giá trị có tập hữu hạn, được kiểm soát; thường có thể trở thành metric tags và span attributes.
- **High-cardinality:** giá trị có thể thay đổi theo từng request/thực thể; thường chỉ được dùng làm span attributes theo handler tiêu chuẩn.

Ví dụ:

~~~java
Observation.createNotStarted("shop.checkout", registry)
    .lowCardinalityKeyValue("shop.channel", "WEB")
    .highCardinalityKeyValue("order.id", orderId.toString())
    .observe(this::processCheckout);
~~~

Trong ví dụ, `shop.channel` có tập giá trị hữu hạn; `order.id` thường có giá trị riêng cho từng đơn. Đừng biến order ID, customer ID, email hoặc token thành metric tags. High-cardinality không có nghĩa là tự động an toàn về bảo mật; trace backend vẫn lưu dữ liệu và cần quyền truy cập/retention phù hợp.

## 6. Tracer, Span và Propagator làm gì?

Micrometer Tracing cung cấp một số API quan trọng:

| API | Trách nhiệm |
| --- | --- |
| **Tracer** | Tạo span, truy cập current span, đặt span vào scope, truy cập baggage. |
| **Span** | Đại diện hoạt động tracing; đặt tên, tag, event, lỗi và kết thúc. |
| **Propagator** | Inject trace context vào carrier gửi đi và extract context từ carrier nhận vào. |
| **Baggage** | Mang một số giá trị ngữ cảnh được cấu hình đi cùng trace. |
| **CurrentTraceContext** | Quản lý trace context đang hoạt động trong execution context của implementation. |
| **SpanInScope** | Đưa span thành current trong một phạm vi và khôi phục context trước đó khi đóng scope. |

### 6.1. Tạo span thủ công

Spring Boot và các thư viện thường tự tạo spans cho HTTP, messaging hoặc các observation đã instrument. Chỉ tạo span thủ công khi một đoạn code quan trọng chưa có instrumentation phù hợp hoặc cần một ranh giới đo riêng.

~~~java
package com.example.shop.tax;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.stereotype.Service;

@Service
public class TaxCalculator {

    private final Tracer tracer;

    public TaxCalculator(Tracer tracer) {
        this.tracer = tracer;
    }

    public long calculate(long amountInMinorUnit) {
        Span span = tracer.nextSpan()
            .name("calculate-tax")
            .start();

        try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
            span.tag("tax.currency", "VND");

            long tax = Math.round(amountInMinorUnit * 0.1);

            span.event("tax-calculated");
            return tax;
        } catch (RuntimeException exception) {
            span.error(exception);
            throw exception;
        } finally {
            span.end();
        }
    }
}
~~~

Đây là ví dụ minh họa API Micrometer Tracing. `tax.currency` là tag có giá trị giới hạn; không nên gắn toàn bộ input hoặc thông tin cá nhân vào span. Trong code thực, cách tính thuế phải theo chính sách nghiệp vụ và kiểu dữ liệu tiền chính xác của dự án.

Các thao tác đáng chú ý:

- `tracer.nextSpan()` tạo một span theo ngữ cảnh hiện tại nếu có.
- `name(...)` đặt tên mô tả hoạt động.
- `start()` bắt đầu span.
- `tracer.withSpan(span)` đưa span vào scope hiện tại; scope cần được đóng.
- `span.tag(...)` thêm attribute để điều tra.
- `span.event(...)` ghi một mốc sự kiện trong span.
- `span.error(exception)` ghi nhận lỗi theo API.
- `span.end()` kết thúc span để implementation có thể xử lý và xuất dữ liệu.

Không quên kết thúc span trong `finally`. Nếu không, span có thể không được hoàn tất và báo cáo đúng.

### 6.2. Không tạo span cho mọi method

Tạo span thủ công ở mọi method thường làm trace quá chi tiết, tăng chi phí và gây khó đọc. Hãy tạo span ở ranh giới có ý nghĩa:

- một lời gọi ra hệ thống ngoài;
- một bước xử lý nghiệp vụ lớn;
- một đoạn tính toán tốn thời gian;
- một bước async cần điều tra riêng;
- một ranh giới module chưa được framework instrument.

Nếu Spring Modulith đã tạo module entry span cho một API, thêm span thủ công ngay trong method đó có thể làm trùng lặp. Chỉ thêm khi span mới cung cấp một thông tin khác biệt.

## 7. Micrometer Tracing và Spring Boot

Spring Boot tích hợp Micrometer Observation và Micrometer Tracing thông qua Actuator và auto-configuration. Khi các dependency tracing phù hợp có mặt, Boot cấu hình tracer implementation, handlers và exporter theo tổ hợp được chọn.

### 7.1. Những tracer implementation được hỗ trợ

Tài liệu Spring Boot hiện hành mô tả các cấu hình phổ biến:

- **OpenTelemetry với OTLP:** gửi spans theo OpenTelemetry Protocol tới collector/backend hỗ trợ OTLP.
- **OpenZipkin Brave với Zipkin:** dùng Brave và Zipkin reporter để xuất traces tới Zipkin.

Tùy phiên bản Spring Boot, tên starter và dependency có thể khác. Ví dụ, một số dòng Boot mới cung cấp starter tích hợp cao hơn, trong khi các dòng trước khai báo trực tiếp bridge và exporter. Hãy sử dụng **Spring Boot dependency management/BOM tương thích** thay vì tự ghép version ngẫu nhiên.

### 7.2. Minh họa dependency theo hướng OpenTelemetry

Với các dòng Spring Boot mới có starter OpenTelemetry, cấu hình có thể gọn như sau:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Starter này được hỗ trợ trong các dòng Spring Boot có cung cấp nó.
    implementation 'org.springframework.boot:spring-boot-starter-opentelemetry'
}
~~~

Với một số dòng Spring Boot trước đó, cách khai báo thường là bridge và exporter:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-tracing-bridge-otel'
    runtimeOnly 'io.opentelemetry:opentelemetry-exporter-otlp'
}
~~~

Hai đoạn là **hai phương án theo dòng phiên bản**, không khai báo đồng thời một cách máy móc. Spring Boot quản lý version các thành phần tương thích khi sử dụng đúng BOM/plugin của dự án. Kiểm tra reference guide đúng phiên bản trước khi chọn.

### 7.3. Minh họa cấu hình sampling và OTLP

Ví dụ cấu hình sampling cho môi trường phát triển:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: "http://localhost:4318/v1/traces"
~~~

Cấu hình exporter OTLP cụ thể phụ thuộc Spring Boot release, giao thức HTTP/gRPC và endpoint collector. Trong môi trường phát triển, sampling 1.0 giúp quan sát mọi trace trong phạm vi request được instrument; **không mặc định dùng 100% sampling ở production** nếu chưa đánh giá tải và chi phí.

Tài liệu Spring Boot hiện hành ghi nhận sampling mặc định 10% để tránh làm quá tải trace backend. Giá trị này có thể được thay đổi bằng `management.tracing.sampling.probability`. Một số sampler OpenTelemetry còn hỗ trợ parent-based behavior; việc chọn sampler cần dựa trên topology và yêu cầu thu thập.

### 7.4. Cần có backend đang chạy

Để nhìn thấy trace, hệ thống cần một backend hoặc collector đang nhận dữ liệu. Quy trình tổng quát:

1. Ứng dụng tạo observation/span.
2. Tracing handler kết nối Observation với Micrometer Tracing.
3. Tracer implementation hoàn tất span.
4. Exporter/reporter gửi span đến collector/backend.
5. Backend lưu và index trace.
6. Người vận hành truy vấn bằng trace ID, service, operation, thời gian hoặc attributes.

Nếu backend không chạy hoặc endpoint sai, code có thể vẫn khởi động nhưng không thấy dữ liệu ở UI. Kiểm tra log exporter, kết nối mạng, xác thực, sampling và cấu hình endpoint trước khi kết luận instrumentation không hoạt động.

## 8. Vai trò của Micrometer Tracing trong Spring Modulith

Spring Modulith tập trung vào **application module boundaries**. Khi bật observability support, các Spring components thuộc API của application module có thể được instrument bằng aspect để ghi nhận module entry/exit và tạo Micrometer spans.

Ví dụ ứng dụng có:

- `orders` công khai `OrderManagement`;
- `inventory` công khai `InventoryOperations`;
- `payments` công khai `PaymentOperations`.

Khi `orders` gọi `InventoryOperations.reserve(...)`, Spring Modulith có thể tạo module entry span cho lời gọi vào `inventory`. Khi module khác gọi API `payments`, trace có thể thể hiện thêm module span tương ứng.

Các tag module entry span được Spring Modulith tài liệu hóa gồm:

| Tag | Ý nghĩa |
| --- | --- |
| `module.identifier` | Định danh kỹ thuật application module. |
| `module.name` | Tên module. |
| `module.invocation-type` | Loại điểm vào, ví dụ `bean` hoặc `event listener`. |
| `module.method` | Method được thực thi tại điểm instrument. |

Các thuộc tính này giúp đọc trace theo cấu trúc module thay vì chỉ nhìn tên class hoặc HTTP URL.

### 8.1. Module graph và tracing trả lời hai câu hỏi khác nhau

| Module graph / Actuator | Micrometer Tracing |
| --- | --- |
| Mô tả module và quan hệ phụ thuộc được phát hiện từ ứng dụng. | Mô tả các hoạt động runtime đã được instrument và thu thập. |
| Có thể hiển thị module chưa được gọi trong một request. | Chỉ có span khi điểm xử lý thực sự chạy và được lấy mẫu/ghi nhận. |
| Hỗ trợ review cấu trúc và ranh giới. | Hỗ trợ điều tra đường đi, duration và lỗi của một lần xử lý. |
| Không cho biết thời gian thực thi một lời gọi cụ thể. | Không tự chứng minh toàn bộ dependency tĩnh hoặc tính đúng của workflow. |

Spring Modulith Insight starter giúp bật Actuator và observability support. Tuy nhiên, **Insight starter không tự cung cấp mọi exporter/backend**; ứng dụng vẫn cần dependency và cấu hình tracing phù hợp với công cụ giám sát đã chọn.

### 8.2. Luồng ví dụ giữa module

~~~mermaid
sequenceDiagram
    participant Web as HTTP
    participant O as orders
    participant I as inventory
    participant E as Application event
    participant P as payments
    participant T as Trace backend

    Web->>O: POST /orders
    Note over Web,O: HTTP server span
    O->>I: InventoryOperations.reserve()
    Note over O,I: Module entry span
    I-->>O: Reservation result
    O->>E: publish OrderSubmitted
    E->>P: PaymentPreparationListener
    Note over E,P: Listener/module observation nếu được instrument
    P-->>E: Listener result
    O-->>Web: Response
    T-->>T: Nhận các spans được export
~~~

Sơ đồ chỉ minh họa quan hệ nghiệp vụ và quan sát. Event listener có thể chạy đồng bộ hoặc bất đồng bộ; trong trường hợp async, trace có thể tiếp tục bằng context được truyền hoặc xuất hiện với quan hệ span link tùy cơ chế instrumentation.

## 9. Propagation: nối trace qua các dịch vụ

Tạo span trong một tiến trình là chưa đủ để distributed tracing hoạt động. Khi ứng dụng gọi dịch vụ khác qua HTTP, sender cần **inject** trace context vào request; receiver cần **extract** context để tạo span tiếp tục trace.

Quy trình:

~~~mermaid
sequenceDiagram
    participant A as Service A
    participant PropA as Propagator A
    participant Net as HTTP headers
    participant PropB as Propagator B
    participant B as Service B

    A->>PropA: Inject current trace context
    PropA->>Net: traceparent / configured headers
    Net->>PropB: Request headers
    PropB->>B: Extract parent context
    B->>B: Create server/child span
~~~

Header cụ thể tùy propagation format được cấu hình, ví dụ W3C Trace Context hoặc B3. Hai bên cần có cấu hình tương thích; nếu sender dùng một định dạng mà receiver không extract, trace có thể bị chia thành hai phần không liên hệ.

### 9.1. Dùng HTTP client builder được Spring Boot cấu hình

Với Spring Boot, nên sử dụng builder được auto-configure để trace propagation hoạt động:

~~~java
package com.example.shop.shipping;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class ShippingClient {

    private final RestClient client;

    public ShippingClient(RestClient.Builder builder) {
        this.client = builder
            .baseUrl("http://shipping-service")
            .build();
    }

    public String createShipment(String orderReference) {
        return client.post()
            .uri("/shipments")
            .body(orderReference)
            .retrieve()
            .body(String.class);
    }
}
~~~

Dùng auto-configured `RestClient.Builder` giúp Spring Boot gắn observation và propagation theo cấu hình hiện hành. Nếu tự tạo client bằng builder không được Boot quản lý, automatic trace propagation có thể không hoạt động.

Tương tự, khi sử dụng `WebClient`, hãy dùng builder được cấu hình bởi Spring Boot. Kiểm tra đúng phiên bản framework vì API và cách đăng ký observation interceptor có thể thay đổi.

### 9.2. Propagation không đồng nghĩa với bảo đảm xử lý

Propagation truyền thông tin trace, không truyền transaction database hoặc bảo đảm message được giao đúng một lần. Một request có trace context hợp lệ vẫn có thể:

- thất bại ở dịch vụ đích;
- timeout dù dịch vụ đích đã xử lý;
- bị retry và tạo nhiều lần thực thi;
- bị mất dữ liệu khi hệ thống lưu trữ lỗi;
- bị sampling nên không xuất hiện trong backend.

Cần kết hợp retry policy, idempotency, event persistence và kiểm thử nghiệp vụ riêng.

## 10. Context propagation qua thread và reactive pipeline

Nhiều ứng dụng Spring Boot không chỉ chạy trên một thread:

- `@Async` chuyển việc sang executor;
- scheduler xử lý tác vụ định kỳ;
- event listener chạy bất đồng bộ;
- Project Reactor chuyển execution giữa scheduler;
- message consumer chạy trên thread do broker/container quản lý.

Micrometer Tracing cần context phù hợp để biết span nào đang là current trong đoạn code tiếp theo. Context có thể được quản lý bằng ThreadLocal hoặc Reactor Context, nhưng **ThreadLocal không tự đi theo mọi lần đổi thread**.

### 10.1. Spring Boot hỗ trợ propagation

Tài liệu Spring Boot hiện hành mô tả:

- Với Reactor, property `spring.reactor.context-propagation` có thể bật chế độ `auto` để tự động propagation theo cơ chế được hỗ trợ.
- Với `@Async` dùng `AsyncTaskExecutor` auto-configured, có property `spring.task.execution.propagate-context`.
- Nếu tự cấu hình executor, có thể cần `ContextPropagatingTaskDecorator`.

Ví dụ cấu hình:

~~~yaml
spring:
  reactor:
    context-propagation: auto
  task:
    execution:
      propagate-context: true
~~~

Tên property và hành vi hỗ trợ cần đối chiếu đúng Spring Boot release. Với custom executor, ví dụ bean decorator:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

@Configuration(proxyBeanMethods = false)
class TaskContextConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

Bean decorator cần được gắn vào executor thực tế theo cách cấu hình của ứng dụng. Chỉ khai báo bean không bảo đảm mọi executor tùy chỉnh tự động dùng nó.

### 10.2. Span scope phải được đóng đúng thread

Khi dùng API trực tiếp, mở scope và đóng scope trên cùng thread. Ví dụ:

~~~java
Span span = tracer.nextSpan().name("reconcile-stock").start();

try (Tracer.SpanInScope scope = tracer.withSpan(span)) {
    reconcile();
} finally {
    span.end();
}
~~~

Không giữ một scope ThreadLocal mở rồi chuyển đối tượng scope sang thread khác để đóng. Với công việc async, dùng cơ chế continuation/context propagation được hỗ trợ để đưa span phù hợp thành current trên thread thực thi.

### 10.3. Kiểm tra propagation thực tế

Một test có thể kiểm tra:

1. Tạo request vào service A.
2. A gọi service B bằng client builder auto-configured.
3. B tạo server span.
4. So sánh trace ID của các spans.
5. Kiểm tra quan hệ parent hoặc span link theo cơ chế propagation.
6. Thử một nhánh async và xác minh context được phục hồi đúng.
7. Xác minh sau khi scope kết thúc, thread không giữ nhầm context của request trước.

Nếu không có propagation, trace có thể bị đứt hoặc log của thread pool có thể gắn nhầm correlation context. Đây là lý do phải kiểm tra cả happy path lẫn lỗi/timeout.

## 11. Baggage: truyền metadata đi cùng trace

**Baggage** là các giá trị ngữ cảnh được cấu hình để đi cùng trace qua các ranh giới process. Ví dụ:

- `tenant-tier` để phân biệt nhóm dịch vụ được phép dùng;
- `locale` để điều tra vấn đề theo ngôn ngữ;
- `workflow-kind` để phân loại luồng xử lý.

Baggage không phải business database, không phải metric label và không nên chứa dữ liệu nhạy cảm tùy tiện. Vì nó có thể được truyền qua HTTP headers hoặc carrier khác, cần whitelist trường và giới hạn độ dài/giá trị.

### 11.1. Baggage khác span tag thế nào?

| Khái niệm | Vai trò |
| --- | --- |
| **Span tag/attribute** | Metadata gắn với một span để truy vấn span đó. |
| **Baggage** | Metadata được gắn với trace context và có thể truyền tới downstream nếu cấu hình propagation cho phép. |
| **Metric tag** | Chiều phân loại một meter/time series; cần cardinality thấp. |
| **Business ID** | Định danh nghiệp vụ do ứng dụng quản lý, không nên tự động truyền rộng như baggage. |

Baggage propagation và việc sao chép baggage thành span tag là hai cấu hình khác nhau. Một field được phép truyền qua mạng không nhất thiết tự động xuất hiện thành span attribute.

### 11.2. Cấu hình baggage trong Spring Boot

Spring Boot có các property để chỉ định trường baggage từ xa, trường được đưa vào MDC để correlation và trường được gắn thành span tags. Ví dụ minh họa:

~~~yaml
management:
  tracing:
    baggage:
      remote-fields:
        - workflow-kind
      correlation:
        fields:
          - workflow-kind
      tag-fields:
        - workflow-kind
~~~

Cấu hình này chỉ nên dùng với một trường đã được whitelist và có giá trị giới hạn. Kiểm tra tài liệu đúng Boot release để xác nhận cấu trúc property và hỗ trợ của tracer implementation đang dùng.

### 11.3. Không truyền dữ liệu nhạy cảm

Tránh baggage chứa:

- access token, session cookie hoặc credential;
- email, số điện thoại, địa chỉ;
- dữ liệu thanh toán;
- payload nghiệp vụ đầy đủ;
- thông tin cá nhân không cần thiết cho điều tra.

Header có thể đi qua nhiều dịch vụ, proxy và log trung gian. Baggage nên nhỏ, ổn định và được kiểm soát bởi chính sách bảo mật của tổ chức.

## 12. Log correlation: kết nối log với trace

Trace cho thấy quan hệ giữa các hoạt động; log cung cấp chi tiết sự kiện và nội dung thông báo. Khi có trace ID và span ID trong MDC, log có thể được tìm theo cùng trace.

Spring Boot tích hợp Micrometer Tracing thường đưa các giá trị `traceId` và `spanId` vào MDC để correlation. Một dòng log có thể trông như:

~~~text
[4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7] INFO  OrderService - Order submitted
~~~

Đây là format minh họa. Format thật phụ thuộc logging framework, pattern và MDC key đã cấu hình.

### 12.1. Vì sao log correlation hữu ích?

Giả sử trace cho thấy span `payments.prepare` mất 2,4 giây. Người vận hành có thể mở log cùng trace ID để tìm:

- payment provider timeout;
- retry attempt;
- response code;
- thông báo validation;
- trạng thái fallback.

Không cần đưa mọi nội dung log vào span. Span nên chứa metadata cần để định vị và tổng hợp; log giữ chi tiết phù hợp với chính sách bảo mật và retention.

### 12.2. Correlation ID không thay thế trace

Một ứng dụng có thể có request ID hoặc correlation ID do hệ thống tự tạo. Trace ID có mục tiêu tương quan distributed tracing. Hai ID có thể cùng tồn tại:

| ID | Mục tiêu |
| --- | --- |
| `traceId` | Liên kết các spans trong distributed trace. |
| `spanId` | Nhận diện một span cụ thể. |
| `requestId` | Định danh request theo quy ước của ứng dụng/gateway. |
| `orderId` | Liên kết hoạt động nghiệp vụ của đơn hàng. |

Không gán lại trace ID từ order ID. Nếu cần tìm mọi trace liên quan một đơn hàng, ghi order ID vào log hoặc span attribute theo chính sách kiểm soát cardinality và dữ liệu.

## 13. Sampling: vì sao không phải trace nào cũng xuất hiện?

Trong môi trường có lưu lượng lớn, gửi mọi span của mọi request có thể tốn CPU, mạng, dung lượng lưu trữ và chi phí truy vấn. **Sampling** quyết định trace nào được giữ và xuất.

Spring Boot hiện hành mặc định lấy mẫu 10% request trong cấu hình tracing chuẩn để hạn chế quá tải backend. Property `management.tracing.sampling.probability` điều chỉnh xác suất lấy mẫu; giá trị `1.0` tương ứng 100% theo cấu hình sampler phù hợp.

### 13.1. Head-based sampling

Head-based sampling quyết định sớm ở đầu trace. Nếu trace không được chọn, các span downstream thường không được xuất theo cùng trace context. Cách này tiết kiệm tài nguyên nhưng có thể bỏ qua một request mà lỗi chỉ xuất hiện ở cuối.

Ví dụ:

| Probability | Ý nghĩa khái quát |
| --- | --- |
| `0.0` | Không chọn trace nào theo sampler ratio. |
| `0.1` | Chọn khoảng 10% trace theo xác suất. |
| `0.5` | Chọn khoảng 50% trace. |
| `1.0` | Chọn toàn bộ trace theo cấu hình ratio. |

Tỷ lệ thực tế quan sát được trong cửa sổ nhỏ có thể dao động quanh xác suất cấu hình.

### 13.2. Parent-based sampling

Trong hệ thống phân tán, sampler có thể quyết định dựa trên trạng thái sampled của parent context để các dịch vụ downstream nhất quán với trace đã được chọn. Spring Boot/OpenTelemetry có các lựa chọn sampler parent-based tùy phiên bản và implementation.

Không nên chỉ tăng sampling probability ở một dịch vụ trong khi các dịch vụ khác có chính sách không tương thích mà không hiểu cách parent context được xử lý.

### 13.3. Khi nào nên dùng sampling 100%?

- phát triển local để xem đầy đủ trace;
- test tích hợp cần xác minh mọi span trong kịch bản;
- lưu lượng thấp trong môi trường thử nghiệm;
- điều tra ngắn hạn có kiểm soát.

Production thường cần đánh giá lưu lượng, độ dài trace, chi phí backend, dữ liệu nhạy cảm và khả năng lấy mẫu có chủ đích. Sampling 100% không phải lựa chọn mặc định an toàn cho hệ thống tải cao.

### 13.4. Không thấy trace chưa đủ kết luận code không chạy

Trace có thể vắng mặt vì:

- request không được sampling;
- code path không được instrument;
- exporter không gửi được;
- backend từ chối hoặc lọc dữ liệu;
- context propagation bị đứt;
- span chưa kết thúc;
- trace đã hết retention hoặc không khớp truy vấn.

Khi điều tra, kiểm tra sampling và exporter trước khi sửa logic nghiệp vụ dựa trên giả định “không có trace nghĩa là không có xử lý”.

## 14. Exporter và backend: đưa span ra khỏi ứng dụng

Một trace chỉ hữu ích khi dữ liệu có thể được truy vấn. Micrometer Tracing cần implementation và exporter/reporter phù hợp.

### 14.1. OTLP pipeline

~~~mermaid
flowchart LR
    A["Spring Boot app"] --> B["Micrometer Observation"]
    B --> C["Micrometer Tracing"]
    C --> D["OpenTelemetry bridge/SDK"]
    D --> E["OTLP exporter"]
    E --> F["OpenTelemetry Collector"]
    F --> G["Jaeger / Tempo / backend"]
    G --> H["Trace UI / queries"]
~~~

OTLP là giao thức xuất telemetry của OpenTelemetry. Collector có thể nhận OTLP, xử lý, lọc, bổ sung metadata và chuyển tiếp đến backend.

### 14.2. Zipkin pipeline

~~~mermaid
flowchart LR
    A["Spring Boot app"] --> B["Micrometer Observation"]
    B --> C["Micrometer Tracing"]
    C --> D["Brave bridge"]
    D --> E["Zipkin reporter"]
    E --> F["Zipkin backend"]
    F --> G["Zipkin UI"]
~~~

Hai sơ đồ mô tả hai lựa chọn phổ biến. Một ứng dụng thường chọn một tracer implementation và exporter phù hợp thay vì đưa nhiều bridge cạnh tranh vào classpath mà không có chủ đích.

### 14.3. Kiểm tra exporter

Khi không thấy trace trong backend, kiểm tra:

1. Tracer implementation có được auto-configure không?
2. Bridge có trên runtime classpath không?
3. Exporter/reporter có được cấu hình đúng không?
4. Endpoint collector/backend có thể kết nối không?
5. Có lỗi TLS, DNS, authentication hoặc network policy không?
6. Sampling có loại trace không?
7. Backend có nhận nhưng truy vấn sai service/time range không?
8. Batch processor có flush khi ứng dụng dừng đúng cách không?

Việc app khởi động thành công **không chứng minh** exporter đang gửi span thành công. Hãy kiểm tra log exporter, metrics của pipeline hoặc dữ liệu ở collector.

## 15. Micrometer Tracing trong Spring Modulith: ví dụ end-to-end

Giả sử ứng dụng có module `orders`, `inventory` và `payments`.

- HTTP request gọi `OrderService`.
- `OrderService` gọi API công khai `InventoryFacade`.
- Sau khi tạo đơn, ứng dụng publish `OrderPlaced`.
- Listener thuộc `payments` nhận event và chuẩn bị thanh toán.

Spring Modulith observability support có thể instrument các Spring components thuộc **API của application module**, tạo module entry spans khi chúng được gọi. Những spans đó trở thành một phần của trace thông qua Micrometer Observation/Tracing khi tracing được cấu hình.

### 15.1. Cấu hình Insight của Spring Modulith

Nếu muốn cả module Actuator và observability support, có thể dùng starter:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Nếu chỉ cần module observability:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability-core'
}
~~~

Các ví dụ giả định BOM Spring Modulith tương thích đã được cấu hình. Insight starter gom hỗ trợ Actuator và observability của Modulith; **vẫn cần cấu hình tracing implementation/bridge/exporter** để đưa spans tới backend như OTLP hoặc Zipkin.

### 15.2. Code API module

~~~java
package com.example.shop.inventory;

import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class InventoryFacade {

    public void reserve(UUID orderId) {
        // Kiểm tra tồn kho và ghi reservation theo logic ứng dụng.
    }
}
~~~

Một module khác gọi bean API này qua Spring dependency injection:

~~~java
package com.example.shop.orders;

import com.example.shop.inventory.InventoryFacade;
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final InventoryFacade inventory;

    public OrderService(InventoryFacade inventory) {
        this.inventory = inventory;
    }

    public void place(UUID orderId) {
        inventory.reserve(orderId);
    }
}
~~~

Khi điểm vào `InventoryFacade` được Spring Modulith nhận diện và instrumentation hoạt động, trace có thể có module entry span với metadata như `module.identifier=inventory`, `module.name`, `module.invocation-type=bean` và `module.method`.

### 15.3. Listener nhận application event

~~~java
package com.example.shop.payments;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentPreparationListener {

    @EventListener
    public void on(OrderPlaced event) {
        // Chuẩn bị xử lý thanh toán theo chính sách ứng dụng.
    }
}
~~~

Khi listener được gọi và instrumentation nhận diện được điểm vào, module entry span có thể mang invocation type `event listener`. Nếu listener chạy bất đồng bộ, cần kiểm tra context propagation và quan hệ trace thực tế.

### 15.4. Trace cho biết điều gì?

Một trace có thể giúp trả lời:

- Lời gọi vào inventory mất bao lâu?
- Listener payments bắt đầu lúc nào và chạy bao lâu?
- Lỗi xuất hiện ở module nào?
- Có HTTP client span tới payment provider không?
- Trace context có tiếp tục qua lời gọi HTTP hoặc executor không?

Trace không tự chứng minh:

- tồn kho đã được commit đúng;
- payment đã được thu đúng một lần;
- listener không bị retry;
- đơn hàng đã đủ điều kiện giao;
- mọi đường code chưa instrument đều không có lỗi.

Để kiểm chứng tính đúng đắn, cần test module, invariant, transaction, idempotency, event publication tracking và đối soát dữ liệu.

## 16. Phân biệt tracing với metrics và logging

Ba loại tín hiệu có vai trò bổ sung:

| Tín hiệu | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **Metrics** | Hệ thống đang có xu hướng gì trên tập hoạt động lớn? | Tỷ lệ lỗi, request/giây, độ trễ p95, số event publications. |
| **Tracing** | Một request hoặc workflow cụ thể đã đi qua đâu? | Span HTTP, module entry, database, external call. |
| **Logging** | Có thông báo/sự kiện chi tiết nào xảy ra? | Payment provider timeout, validation failed, retry attempt. |

Ví dụ:

- Dashboard metrics cho thấy p95 của `payments` tăng.
- Trace giúp tìm một request chậm và xác định span HTTP tới payment provider mất nhiều thời gian.
- Log correlation theo trace ID cho biết provider trả lỗi timeout và ứng dụng đã retry.

Không nên dùng trace thay metrics cho mọi thống kê tổng hợp vì trace sampling có thể bỏ dữ liệu. Cũng không nên dùng metrics thay log để tìm nội dung lỗi chi tiết của một đơn hàng.

## 17. Giới hạn và rủi ro khi dùng Micrometer Tracing

### 17.1. Không phải mọi code path đều tự có span

Instrumentation tự động chỉ áp dụng cho các thư viện và điểm vào được hỗ trợ. Method nội bộ, private method, code không qua proxy hoặc thư viện không instrument có thể không xuất span. Khi cần, thêm observation/span thủ công ở ranh giới có ý nghĩa.

### 17.2. Trace không phải bằng chứng đầy đủ về nghiệp vụ

Span có status OK chỉ cho biết span kết thúc theo cách được ghi nhận. Transaction bên ngoài có thể rollback, consumer có thể retry, hoặc một bước sau đó có thể thất bại. Hãy kiểm tra state đã commit và các invariant nghiệp vụ.

### 17.3. Sampling làm thiếu dữ liệu

Một trace không xuất hiện có thể do sampler không chọn. Đừng dùng số trace trong backend như số request chính xác khi sampling dưới 100%.

### 17.4. Context propagation có thể bị đứt

Nếu không truyền context qua executor, Reactor hoặc message broker, downstream có thể tạo trace mới hoặc không có parent mong đợi. Kiểm tra integration cụ thể, không giả định mọi thread tự chia sẻ ThreadLocal.

### 17.5. Baggage có thể lan rộng hơn dự kiến

Baggage được truyền qua nhiều dịch vụ theo cấu hình. Nếu chứa dữ liệu nhạy cảm hoặc giá trị quá lớn, nó có thể bị lộ qua headers, logs hoặc backend. Chỉ whitelist trường cần thiết.

### 17.6. Span attributes có thể gây cardinality và chi phí

Tracing backend có thể lưu nhiều attributes, nhưng điều đó không có nghĩa nên gắn toàn bộ request payload hoặc business ID. Giữ attributes có ích cho điều tra, giới hạn kích thước và retention.

### 17.7. Clock và batch export ảnh hưởng cách diễn giải

Các service khác nhau có thể lệch đồng hồ. Span timeline hữu ích để phân tích nhưng không thay thế dữ liệu timestamp/transaction có thẩm quyền. Batch exporter có thể gửi chậm hơn thời điểm span kết thúc; trace UI có thể xuất hiện sau một khoảng trễ.

## 18. Quy trình điều tra một trace bị đứt

**Triệu chứng:** Request tới `orders` có trace ID, nhưng lời gọi tới `inventory` hoặc listener `payments` không xuất hiện trong cùng trace.

Đi theo trình tự:

1. **Xác nhận sampling:** trace ban đầu có được chọn không? Parent context có cờ sampled phù hợp?
2. **Xác nhận instrumentation:** API module có thuộc phạm vi Spring Modulith instrument không? Có runtime dependency core/starter?
3. **Xác nhận HTTP client:** dùng builder do Spring Boot auto-configure hay tự tạo client?
4. **Xác nhận propagation format:** sender inject và receiver extract cùng định dạng tương thích không?
5. **Kiểm tra thread boundary:** có `@Async`, executor, scheduler hoặc Reactor pipeline? Context có được propagate?
6. **Kiểm tra event listener:** listener chạy đồng bộ, sau commit hay async? Có được gọi thật không?
7. **Kiểm tra exporter/backend:** span có được tạo nhưng không export? Có lỗi collector hoặc filter?
8. **Đối chiếu business ID:** dùng orderId/eventId trong dữ liệu nghiệp vụ/log phù hợp để xác định hai bước có cùng workflow dù trace context bị đứt hay không.

~~~mermaid
flowchart TD
    A["Downstream span không xuất hiện trong trace"] --> B{"Parent trace được sampled?"}
    B -->|"Không"| C["Kiểm tra sampling policy"]
    B -->|"Có"| D{"Điểm xử lý đã được instrument?"}
    D -->|"Không"| E["Bật instrumentation hoặc tạo observation"]
    D -->|"Có"| F{"Qua HTTP hoặc message boundary?"}
    F -->|"HTTP"| G["Kiểm tra auto-configured client,\nheaders inject/extract"]
    F -->|"Thread/async/reactive"| H["Kiểm tra context propagation"]
    F -->|"Không"| I["Kiểm tra proxy, module API,\nlistener invocation"]
    G --> J["Kiểm tra exporter/backend"]
    H --> J
    I --> J
~~~

## 19. Checklist triển khai Micrometer Tracing

- [ ] Đã chọn tracer implementation phù hợp (OpenTelemetry hoặc Brave) và kiểm tra tương thích Spring Boot.
- [ ] Đã dùng BOM/dependency management để giữ version bridge/exporter đồng bộ.
- [ ] Đã cấu hình exporter/reporter và backend đang nhận trace.
- [ ] Đã xác minh Observation handlers tạo spans trong môi trường chạy thật.
- [ ] Đã bật Spring Modulith observability nếu muốn module entry spans.
- [ ] Đã kiểm tra span tags module như `module.identifier` và `module.invocation-type`.
- [ ] Đã dùng auto-configured `RestClient.Builder`/`WebClient.Builder` hoặc cấu hình propagation tương đương.
- [ ] Đã kiểm thử propagation qua HTTP, executor, async listener và reactive pipeline được sử dụng.
- [ ] Đã xác định sampler và tỷ lệ sampling cho từng môi trường.
- [ ] Đã bật log correlation nếu cần và xác minh traceId/spanId trong MDC.
- [ ] Baggage được whitelist, giới hạn kích thước và không chứa secret/PII.
- [ ] Span attributes có ý nghĩa và không đưa payload lớn vào telemetry.
- [ ] Dashboard phân biệt metrics, traces và logs; không dùng trace count thay số giao dịch.
- [ ] Có cách đối chiếu trace với orderId/eventId mà không dùng business ID làm trace ID.
- [ ] Có test/diagnostics cho lỗi exporter, context propagation và sampling.

## 20. Bài tập tự luyện

1. **Trace và span:** Một request tạo đơn có một trace với sáu spans. Hãy giải thích vì sao có sáu span ID nhưng chỉ một trace ID.
2. **Facade:** Vì sao Micrometer Tracing được gọi là facade? Bridge và exporter đảm nhận vai trò nào?
3. **Observation:** Một Observation được tạo trong Spring Boot. Điều kiện nào để nó tạo ra span thay vì chỉ ghi metric?
4. **Module spans:** Spring Modulith tạo module entry span cho lời gọi vào inventory. Những thông tin nào có thể dùng để nhận diện module và loại invocation?
5. **Propagation:** Service A gửi HTTP tới service B nhưng trace bị chia. Hãy nêu các bước kiểm tra sender inject, receiver extract và propagation format.
6. **Async:** Listener dùng `@Async` chạy ở thread khác và mất trace context. Hãy đề xuất cách cấu hình context propagation trong Spring Boot.
7. **Sampling:** Production lấy mẫu 10%. Vì sao không thể dùng số trace xuất hiện để báo cáo số request chính xác?
8. **Baggage:** Nhóm muốn truyền `tenant-id` qua nhiều service. Những điều kiện bảo mật, cardinality và propagation nào cần xem xét?
9. **Log correlation:** Trace có lỗi ở payment provider. Làm thế nào dùng traceId/spanId để tìm log liên quan?
10. **Giới hạn:** Một span payment có status OK nhưng database rollback. Vì sao trace không đủ chứng minh giao dịch đã thành công?
11. **Spring Modulith:** Insight starter đã bật module observability nhưng không thấy trace trên Zipkin. Những dependency và cấu hình nào còn có thể thiếu?
12. **Thiết kế:** Khi nào nên tạo span thủ công? Vì sao không nên tạo span cho mọi method?

## 21. Tổng kết

**Micrometer Tracing cung cấp lớp API thống nhất để tạo, quản lý và truyền distributed trace trong ứng dụng Spring.** Nó giúp biến những hoạt động đã được instrument thành spans có quan hệ, metadata và thời lượng, từ đó người vận hành lần theo một request qua nhiều thành phần và dịch vụ.

Trong hệ sinh thái Spring Boot:

- Micrometer Observation cung cấp điểm instrument chung;
- Micrometer Tracing kết nối observations với span lifecycle;
- bridge nối API với OpenTelemetry hoặc Brave;
- propagator duy trì trace context qua các ranh giới;
- exporter/reporter gửi spans tới collector/backend;
- sampling kiểm soát lượng dữ liệu được giữ;
- MDC correlation giúp tìm log theo trace;
- Spring Modulith bổ sung module entry spans để thấy tương tác ở ranh giới application module.

Khi kết hợp module graph, Actuator, event metrics, tracing và context propagation, nhóm phát triển có thể kiểm chứng kiến trúc mô-đun từ cả cấu trúc lẫn hành vi runtime. Tuy nhiên, tracing là **bằng chứng quan sát có giới hạn bởi instrumentation, sampling và propagation**; tính đúng đắn nghiệp vụ vẫn cần được bảo vệ bằng transaction, invariant, idempotency, kiểm thử và đối soát.

### Tài liệu tham khảo

1. [Micrometer Tracing — Reference Documentation](https://docs.micrometer.io/tracing/reference/).
2. [Micrometer Tracing — Configuring with Micrometer Observation](https://docs.micrometer.io/tracing/reference/configuring.html).
3. [Micrometer Tracing — Using Micrometer Tracing Directly](https://docs.micrometer.io/tracing/reference/api.html).
4. [Micrometer Tracing — Span and Baggage Scopes](https://docs.micrometer.io/tracing/reference/context-contracts.html).
5. [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html).
6. [Spring Boot — Observability và Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html).
7. [Spring Modulith — Production-ready Features: Observing Application Modules](https://docs.spring.io/spring-modulith/reference/production-ready.html).
