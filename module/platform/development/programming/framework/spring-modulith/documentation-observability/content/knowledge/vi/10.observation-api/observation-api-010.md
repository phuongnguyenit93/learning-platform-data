# Phân biệt dữ liệu đi vào metrics và traces

> **Chương:** Observation API  
> **Bối cảnh:** Spring Modulith Documentation & Observability — học cách dùng module graph, Spring Boot Actuator, event metrics, tracing và context propagation để kiểm chứng ứng dụng Spring Boot có ranh giới application module rõ ràng khi vận hành.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả vai trò của `Observation`, `ObservationRegistry`, `Observation.Context` và `ObservationHandler` trong Micrometer.
2. Phân biệt dữ liệu được dùng cho **metrics** với dữ liệu được gửi đến **distributed tracing**, đặc biệt là `lowCardinalityKeyValue(...)` và `highCardinalityKeyValue(...)`.
3. Giải thích vì sao một `Observation` có thể tạo timer trên metrics nhưng chưa chắc có span xuất hiện trong trace backend.
4. Đọc kết quả qua Spring Boot Actuator `/actuator/metrics`, đối chiếu các span trong Zipkin/Tempo/Jaeger và nhận ra tác động của sampling.
5. Liên hệ `Observation` với **module entry spans** và **event publication counters** của Spring Modulith mà không nhầm hai cơ chế.
6. Chọn tên operation, tag, event và correlation metadata có giá trị chẩn đoán nhưng không làm metrics nổ cardinality hoặc tiết lộ dữ liệu nhạy cảm.

## 2. Một operation, hai cách quan sát

Giả sử HTTP request `POST /orders` được xử lý trong module `orders`, sau đó gọi module `payments`. Ta muốn trả lời hai nhóm câu hỏi khác nhau:

| Câu hỏi | Loại tín hiệu phù hợp |
| --- | --- |
| Trung bình mỗi giây module `orders` xử lý bao nhiêu operation? | **Metrics:** tốc độ, số lần, phân phối độ trễ |
| Trong 5 phút, 95% operation mất không quá bao lâu? | **Metrics:** histogram/percentile nếu được cấu hình |
| Request nào đã chờ `payments` và `inventory`, mỗi bước bao lâu? | **Traces:** chuỗi span và quan hệ cha–con |
| Operation nào đã gặp lỗi, có mã correlation kỹ thuật nào? | **Traces** cho điều tra từng lần; **metrics** cho tỷ lệ lỗi tổng hợp |
| Module `orders` phụ thuộc tĩnh vào những module nào? | **Module graph/Actuator modulith**, không phải metrics hay traces |

Micrometer **Observation API** cho phép một điểm instrument diễn tả *một operation đang diễn ra*. Các `ObservationHandler` được đăng ký quyết định có biến vòng đời operation đó thành timer, span, log hoặc tín hiệu khác hay không.

~~~mermaid
flowchart LR
    Code["Code ứng dụng / Spring Modulith"] --> Obs["Micrometer Observation<br/>name + context + key-values + lifecycle"]
    Obs --> Registry["ObservationRegistry"]
    Registry --> MetricHandler["Meter ObservationHandler"]
    Registry --> TraceHandler["Tracing ObservationHandler"]
    MetricHandler --> Meter["MeterRegistry<br/>timer / metrics"]
    TraceHandler --> Span["Micrometer Tracing<br/>span / trace"]
    Meter --> Actuator["Actuator /metrics<br/>Prometheus / dashboard"]
    Span --> Exporter["Exporter / collector<br/>trace backend"]
~~~

Sơ đồ cho thấy một **điểm phát tín hiệu chung**, nhưng có hai đường xuất dữ liệu độc lập. Tạo `Observation` không có nghĩa hệ thống đã tự cài Prometheus, tracer hoặc trace exporter.

## 3. Các thành phần của Observation API

| Thành phần | Chức năng | Lưu ý khi dùng |
| --- | --- | --- |
| `Observation` | Đại diện một operation, có vòng đời `start → scope → stop`; cho phép thêm key-values và ghi nhận lỗi | Phải bảo đảm kết thúc observation và đóng scope |
| `ObservationRegistry` | Điểm đăng ký và cấu hình các handler/convention/filter; được Spring Boot tạo và quản lý khi tích hợp observability | Dùng bean do Spring cung cấp, tránh tự tạo registry rời rạc |
| `Observation.Context` | Giữ metadata phục vụ instrumentation/handlers và trạng thái observation | Dữ liệu đặt trong context **không tự động trở thành tag** |
| `ObservationHandler` | Xử lý các sự kiện vòng đời observation | Handler cho metrics và handler cho tracing có nhiệm vụ khác nhau |
| `ObservationConvention` | Đặt tên operation và xác định key-values nhất quán | Hữu ích với instrumentation dùng chung |
| `ObservationPredicate` | Chấp nhận hoặc bỏ qua một observation | Có thể khiến operation không tạo tín hiệu |
| `ObservationFilter` | Điều chỉnh context/metadata trước khi observation kết thúc | Phụ thuộc giai đoạn xử lý, cần hiểu lifecycle |
| `MeterRegistry` | Quản lý meter như timer, counter, gauge và xuất metrics | Không phải nơi quản lý span |
| `Tracer` và trace exporter | Quản lý span, trace context, sampling và xuất dữ liệu tracing | Không quyết định tổng số counter của ứng dụng |

Một handler chuẩn cho metrics là `DefaultMeterObservationHandler`. Khi handler này được gắn vào `ObservationRegistry`, nó có thể tạo **Timer theo tên observation** khi operation dừng; các tín hiệu event của Observation còn có cơ chế ghi nhận tùy handler/phiên bản. Với tracing handler, vòng đời observation có thể tạo và đóng một **span**.

**Không được suy luận ngược:** thấy `MeterRegistry` hoạt động chưa đủ để khẳng định tracing bridge đã được đăng ký; thấy trace trong backend cũng không chứng minh một metrics registry cụ thể đã scrape thành công.

### 3.1. Vòng đời quan trọng hơn lời gọi API lẻ

~~~mermaid
sequenceDiagram
    participant App as Application
    participant Obs as Observation
    participant H as ObservationHandlers
    App->>Obs: createNotStarted(name, registry)
    App->>Obs: low/high cardinality key-values
    App->>Obs: start()
    Obs->>H: onStart
    App->>Obs: openScope()
    Note over App,Obs: Business code thực thi trong scope
    App->>Obs: error(exception) nếu có
    App->>Obs: close scope
    App->>Obs: stop()
    Obs->>H: onStop
    Note over H: Metrics timer hoàn tất; span đóng
~~~

Thay vì quản lý thủ công từng bước, có thể dùng `observation.observe(() -> work())`; Micrometer quản lý start, scope, stop và báo lỗi khi callback ném exception theo hợp đồng API. Với công việc bất đồng bộ, thời điểm callback kết thúc có thể khác thời điểm tác vụ nền thực sự hoàn tất — cần chọn phạm vi quan sát thích hợp.

## 4. Quy tắc cốt lõi: low cardinality và high cardinality

**Cardinality** là số giá trị khác nhau mà một tag có thể nhận. Với metrics, mỗi tổ hợp `meter name + tags` có thể tạo một time series riêng. Nếu đặt giá trị riêng từng request thành metric tag, số series tăng cực nhanh, làm tốn bộ nhớ và chi phí backend.

Micrometer phân metadata thành hai nhóm:

| Phân loại | Ví dụ | Đi vào metrics? | Đi vào traces? |
| --- | --- | --- | --- |
| **Low cardinality** — số giá trị nhỏ, hữu hạn, được kiểm soát | `module.identifier=orders`, `operation=quote`, `channel=WEB` | **Có**, dưới dạng meter tags khi metrics handler sử dụng | **Có**, dưới dạng span attributes/tags khi tracing handler sử dụng |
| **High cardinality** — nhiều giá trị hoặc không có giới hạn thực tế | `operation.reference=req-7f...`, đường dẫn chứa ID | **Không** được đưa vào meter tags bởi handler metrics mặc định | **Có thể có** trên span khi handler/exporter cho phép |
| **Dữ liệu trong `Observation.Context` không được đưa ra làm key-value** | Object request/response, thông tin nội bộ của handler | Không tự xuất | Không tự xuất |
| **Dữ liệu nghiệp vụ không được instrument** | Nội dung object trong bộ nhớ, database row | Không | Không |

Quy tắc được Spring Boot diễn đạt rõ: **low-cardinality tags được đưa vào metrics và traces; high-cardinality tags chỉ được đưa vào traces**. “Chỉ” ở đây nói về **đường xử lý observation metadata mặc định**, không có nghĩa trace backend luôn nhận tất cả high-cardinality attributes: sampling, filter, exporter và cấu hình riêng vẫn có thể loại chúng.

### 4.1. Tên phương thức và ý nghĩa

~~~java
observation.lowCardinalityKeyValue("channel", "WEB");
observation.highCardinalityKeyValue("operation.reference", "ref-8e2a");
~~~

Hai lời gọi đều đưa metadata vào observation, nhưng **đánh dấu mục đích sử dụng khác nhau**. Hãy dùng `lowCardinalityKeyValue` khi có một tập giá trị ổn định và câu hỏi thống kê rõ ràng. Hãy cân nhắc `highCardinalityKeyValue` khi cần định vị một operation cụ thể trong trace, với chính sách bảo mật và lưu trữ phù hợp.

Không phải cứ gọi `highCardinalityKeyValue` là có thể đặt email, access token, dữ liệu thanh toán hoặc thông tin cá nhân vào span. Trace data có thể được gửi đến hệ thống bên ngoài và lưu trong thời gian dài; ưu tiên định danh kỹ thuật ngẫu nhiên, hạn chế quyền truy cập và áp dụng quy tắc che giấu/redaction của tổ chức.

### 4.2. Một ví dụ cardinality

Giả sử mỗi operation có 3 channel và 4 kết quả xử lý; metric `shop.order.quote` có tối đa **12 tổ hợp tag** từ hai chiều đó trước khi xét các common tags. Nếu thêm `orderId` và có 500.000 đơn, metric có thể tăng đến hàng triệu tổ hợp qua thời gian. Tracing có thể dùng ID kỹ thuật để điều tra từng operation, nhưng không biến ID thành low-cardinality metric tag.

## 5. Ví dụ Java: một observation sinh hai loại metadata

Ví dụ sau nằm trong module `orders` của ứng dụng Spring Boot. Chúng ta có một service với hai nhãn được kiểm soát và một mã tham chiếu kỹ thuật dùng để đối chiếu trace.

~~~java
package com.example.shop.orders;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class OrderQuoteService {

    public enum Channel {
        WEB, MOBILE, API
    }

    private final ObservationRegistry observationRegistry;

    public OrderQuoteService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public String createQuote(String opaqueReference, Channel channel) {
        return Observation
            .createNotStarted("shop.order.quote", observationRegistry)
            .contextualName("quote order")
            .lowCardinalityKeyValue("module.identifier", "orders")
            .lowCardinalityKeyValue("order.channel", channel.name())
            .highCardinalityKeyValue("operation.reference", opaqueReference)
            .observe(() -> calculateQuote());
    }

    private String calculateQuote() {
        // Chỉ mô phỏng thao tác; không phải hệ thống định giá thực.
        return "QUOTE_READY";
    }
}
~~~

**Phân tích theo từng dòng:**

1. `"shop.order.quote"` là tên observation có số biến thể cố định. Với metrics handler mặc định, đây thường là **tên Timer**.
2. `contextualName("quote order")` là tên có ý nghĩa khi quan sát trong ngữ cảnh trace; tên hiển thị span phụ thuộc tracing convention/handler.
3. `module.identifier=orders` và `order.channel=WEB/MOBILE/API` thuộc low cardinality: chúng có thể tạo các meter time series khác nhau và xuất hiện trên span.
4. `operation.reference` có nhiều giá trị: chỉ dành cho việc tìm span/trace, không dùng làm nhãn của Timer.
5. `observe(...)` mở scope cho code trong callback và dừng observation khi callback kết thúc; khi có lỗi được ném ra, API xử lý việc báo lỗi theo lifecycle.

Trong code production, xác minh `opaqueReference` không chứa thông tin nhạy cảm; nếu không cần tra cứu theo reference thì bỏ hẳn high-cardinality attribute. Đừng truyền raw token, email, số điện thoại hay giá trị nhạy cảm chỉ để minh họa tracing.

### 5.1. Cùng một operation được nhìn bằng hai góc độ

Giả sử bạn đã chạy `createQuote("ref-a1", Channel.WEB)` và `createQuote("ref-b2", Channel.MOBILE)`. **Bảng dưới là dự kiến khái niệm, không phải output được đo thực tế:**

| Thuộc tính | Metrics Timer `shop.order.quote` | Span tương ứng |
| --- | --- | --- |
| Tên operation | `shop.order.quote` (tên meter) | Có thể hiển thị `quote order` theo contextual name |
| `module.identifier` | `orders` | `orders` |
| `order.channel` | `WEB` hoặc `MOBILE` | `WEB` hoặc `MOBILE` |
| `operation.reference` | **Không có** trong tags mặc định | Có thể thấy `ref-a1`, `ref-b2` trên span được xuất |
| Thời gian | COUNT, tổng thời gian, giá trị tối đa và histogram nếu cấu hình | Start/end timestamps và duration của từng span |
| Định danh | Meter identity = name + tags | `traceId`, `spanId`, parent relationship |

Metrics giúp so sánh trung bình/tốc độ/percentile qua nhiều lần gọi; trace cho phép xem một lần cụ thể đi qua module nào và chờ ở đâu. Tracing thường dùng sampling, vì vậy **số span backend nhận được có thể thấp hơn số lần timer ghi nhận**.

## 6. Những gì metrics handler thực sự ghi nhận

Khi `DefaultMeterObservationHandler` được đăng ký trong `ObservationRegistry`, kết quả cơ bản của một observation hoàn tất là **Timer** có tên observation.

| Dữ liệu | Đưa vào meter thế nào? | Khi nào thấy? |
| --- | --- | --- |
| Observation name | Tên meter, ví dụ `shop.order.quote` | Khi handler tạo/ghi meter |
| Low-cardinality key-values | Tag của timer (cùng một name có thể chia thành nhiều series) | Khi timer được ghi |
| High-cardinality key-values | **Không** làm meter tags | Không xuất hiện trong metric mặc định |
| Khoảng thời gian start–stop | Timer thống kê duration | Sau observation hoàn tất |
| Lỗi được báo cho observation | Handler có thể thêm tag `error` theo loại lỗi | Sau operation lỗi, tùy cơ chế báo lỗi |
| `Observation.event(...)` | Một số phiên bản/handler có thể tạo event counter riêng theo observation/event name | Chỉ khi handler hỗ trợ và có event được signal |
| Long task timer | Có cấu hình/hỗ trợ riêng, không mặc định có ở mọi phiên bản | Khi bật và handler theo dõi task đang chạy |

Với Micrometer Observation bản hiện hành, tài liệu `DefaultMeterObservationHandler` mô tả Timer `<observation-name>`; Counter `<observation-name>.<event-name>` cho `Observation.event(...)`; LongTaskTimer `<observation-name>.active` là **tùy chọn**. Không mặc định mọi observation sẽ tự tạo nhiều meter loại khác nhau trong mọi tổ hợp phiên bản.

**Lưu ý đếm thời gian:** duration trong Timer là một sample cho operation hoàn tất. Timer có thể cung cấp `COUNT`, `TOTAL_TIME` và `MAX`; histogram/percentile phụ thuộc cấu hình distribution. Timer không tự cho biết thao tác thuộc trace nào hay `orderId` của lần gọi cụ thể.

### 6.1. Cardinality cao làm hại metrics ra sao?

Một meter thường được phân biệt bằng `name + tags`. Nếu tag `operation.reference` có một triệu giá trị khác nhau, registry có thể phải giữ một lượng rất lớn meter/time series. Điều này ảnh hưởng bộ nhớ ứng dụng, thời gian scrape, chi phí ingest và chi phí truy vấn. Thiết kế dùng các nhóm hữu hạn:

~~~text
Tốt: order.channel = WEB | MOBILE | API
Tốt: outcome       = SUCCESS | REJECTED | ERROR
Tránh: order.id    = ORD-00001 | ORD-00002 | ...
Tránh: request.url = /orders/1 | /orders/2 | ...
~~~

Nếu cần route HTTP, dùng mẫu `/orders/{id}` làm nhãn thống kê thay vì path chứa ID. Nếu cần điều tra một order, sử dụng correlation an toàn trong trace/log có quyền truy cập phù hợp.

## 7. Những gì tracing handler thực sự ghi nhận

Khi tracing handler/bridge được cài đặt, một observation có thể được biểu diễn thành span. Dữ liệu thường liên quan:

| Dữ liệu | Trong trace/span | Giới hạn |
| --- | --- | --- |
| Tên operation/contextual name | Tên span | Có thể được thay đổi bởi convention/handler |
| Low-cardinality key-values | Span attributes/tags | Chỉ xuất khi handler/exporter hỗ trợ |
| High-cardinality key-values | Span attributes/tags | Không phải giấy phép ghi dữ liệu nhạy cảm |
| Start/end, duration | Thời điểm và thời lượng của span | Đọc theo waterfall của từng lần chạy |
| Current trace context | `traceId`, `spanId`, parent/links | Cần propagation để không đứt khi đổi thread |
| Lỗi/exception | Error metadata hoặc span status tùy instrumentation | Không mặc định mọi lỗi đều có stack trace |
| Event signal | Có thể là span event khi tracing handler hỗ trợ | Không đồng nghĩa Spring application event publication |

Ví dụ **đơn giản hóa** của span trong một request tạo quote:

~~~yaml
traceId: "61ba9472a8c84eaa88555d08f7811620"
spanId: "83aa5501277a9b12"
parentSpanId: "6c51539fbb9c0ca0"
name: "quote order"
durationMs: 18
attributes:
  module.identifier: "orders"
  order.channel: "WEB"
  operation.reference: "ref-a1"
~~~

Đây là **mô hình minh họa**, không phải payload chuẩn của Zipkin/OTLP/Jaeger. Span thực tế có thể không xuất vì sampler loại bỏ, collector không truy cập được, thiếu bridge, hoặc có cấu hình lọc/redaction. `traceId` và `spanId` là định danh trace, **không phải mặc định là low-cardinality metric tags**.

### 7.1. Sampling không đồng nghĩa cắt giảm metrics

Đặt `management.tracing.sampling.probability=0.1` có thể khiến chỉ một phần operation được ghi nhận trong tracing backend. Tuy nhiên, metrics timer vẫn có thể ghi nhận **mọi observation hoàn tất** nếu meter handler đang hoạt động. Vì thế:

- Nếu Timer có `COUNT=1,000` nhưng chỉ tìm thấy khoảng 100 span trong backend, sampling có thể là giải thích hợp lý.
- Nếu có spans nhưng thiếu một số Operation tags, kiểm tra tracing convention, filter, collector và exporter.
- Nếu cả Timer lẫn span đều không có, kiểm tra xem instrumentation có thật sự tạo observation và có bị `ObservationPredicate` loại bỏ hay không.

Không lấy số lượng span trong backend làm tổng số request chính xác. Traces là dữ liệu chi tiết, thường được lấy mẫu; metrics là dữ liệu tổng hợp theo thời gian.

## 8. Ứng dụng vào Spring Modulith: module entry và event metrics

Trong Spring Modulith, phần observability instrument các **Spring component thuộc API của application module**. Khi có lời gọi đi vào một điểm được quan sát, framework tạo Micrometer Observation và, với tracing pipeline phù hợp, sinh module entry span.

Tài liệu Spring Modulith công bố các key của module entry:

| Key trên module span | Ý nghĩa |
| --- | --- |
| `module.identifier` | Định danh kỹ thuật của module |
| `module.name` | Tên dễ đọc của module |
| `module.method` | Method được thực thi tại module entry |
| `module.invocation-type` | Loại lời gọi, như `bean` hoặc `event listener` |

Các tên key trên giúp tra cứu từng lần gọi của module trong trace. Không suy diễn rằng **cả bốn key** chắc chắn xuất hiện dưới cùng hình thức trên mọi timer: danh sách low/high cardinality của observation convention và handler quyết định chúng có trở thành **metric tags** hay không. Cần đối chiếu dữ liệu runtime và API của dòng Spring Modulith thực tế.

### 8.1. Ví dụ đồng bộ qua ranh giới module

~~~mermaid
sequenceDiagram
    participant HTTP as HTTP Server
    participant Orders as orders module
    participant Payments as payments module
    participant Handlers as Observation handlers
    HTTP->>Orders: placeOrder()
    Note over Orders: Instrumented module entry observation
    Orders->>Payments: authorize()
    Note over Payments: Instrumented module entry observation
    Payments->>Handlers: Observation lifecycle
    Note over Handlers: Timer/metric tags và span/trace tags
    Payments-->>Orders: Result
    Orders-->>HTTP: Response
~~~

Một trace có thể cho biết lời gọi `orders.placeOrder` dẫn tới `payments.authorize`, còn metrics có thể cho biết số lần `payments` được instrument và latency của những operation đó trong một khoảng thời gian. Cùng module identifier xuất hiện trong cả hai loại tín hiệu **không có nghĩa mỗi timer series tương ứng với đúng một span trong backend**.

### 8.2. Event publication counter không phải Timer của Observation

Spring Modulith còn có metrics đếm các domain event đã được publish:

- `module.events.published`, counter tổng hợp có tag `module.identifier`, `module.name`, `module.event.type`.
- `module.events.published.$moduleIdentifier.$simpleEventTypeName`, counter riêng từng event type có thể làm giàu bằng `ModulithEventMetricsCustomizer`.

Chúng là **event publication counters** do Spring Modulith cung cấp, có quy ước tên và key riêng. Đừng mặc định chúng được tạo bằng cách gọi `Observation.event(...)` từ ví dụ `shop.order.quote` ở trên. Cũng không được lấy counter publish làm bằng chứng listener đã xử lý thành công.

| Tín hiệu | Đo điều gì? | Ví dụ câu hỏi |
| --- | --- | --- |
| Module entry span | Một lần đi vào API của module được instrument | Lần gọi thanh toán này nằm dưới request nào? |
| Timer tạo từ Observation | Tần suất và thời lượng operation được quan sát | Mức latency của thao tác quote theo channel? |
| Event publication counter | Số lần domain event được phát ra theo module/type | `orders` công bố bao nhiêu `OrderPlaced`? |
| Event Publication Registry | Vòng đời publication đến transactional listener | Publication nào còn chưa hoàn tất? |
| Module graph/Actuator `modulith` | Module và dependency được nhận diện | Module `notifications` phụ thuộc vào event type của ai? |

Những dữ liệu này **bổ trợ** nhau, không thay thế nhau.

## 9. Cấu hình tối thiểu để kiểm tra cả hai đầu ra

### 9.1. Phần metrics/Actuator

Với một dự án Spring Boot có dependency management tương thích, phần metrics thường dựa trên Actuator:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Khi cần Prometheus, thêm registry:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Trong môi trường học tập, expose endpoints cần thiết:

~~~yaml
# application-dev.yml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
~~~

Nếu không dùng Prometheus, có thể bỏ `prometheus` khỏi `include`. Bảo vệ management endpoints ở môi trường production; `exposure` chỉ quyết định đường HTTP có được công bố, còn xác thực/phân quyền cần cấu hình riêng.

### 9.2. Phần Spring Modulith và tracing

Nếu muốn module entry spans và Actuator module metadata, có thể dùng Spring Modulith Insight starter:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Nó cung cấp hỗ trợ observability/Actuator của Modulith, nhưng muốn **xuất traces** còn phải cài Micrometer Tracing bridge, exporter và cấu hình collector phù hợp với **dòng Spring Boot đang dùng**. Ví dụ Spring Boot 3.x thường dùng các artifact Micrometer Tracing + exporter tương ứng; Spring Boot 4.x có hệ starter OpenTelemetry riêng. Không trộn cấu hình từ các major version khi chưa xác minh BOM.

Trong môi trường thử nghiệm, có thể tạm bật sampling toàn phần:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Chỉ tăng sampling để dễ kiểm tra; production cần xem xét lưu lượng, chi phí, dữ liệu và khả năng lưu trữ trace. Cấu hình sampling **không thay thế** exporter và không tự mở trace UI trên `/actuator/metrics`.

### 9.3. Một luồng kiểm tra nên làm

1. Tạo request khiến `OrderQuoteService.createQuote(...)` chạy, đồng thời qua ít nhất một public API module được Modulith instrument.
2. Kiểm tra `/actuator/metrics/shop.order.quote` sau khi operation kết thúc.
3. Tìm trace tương ứng trong tracing backend, quan sát các spans có tag module và span của `quote order` nếu đã được instrument và sample.
4. Xác nhận `order.channel` xuất hiện trên cả meter tags lẫn span attributes (nếu handler tương ứng hoạt động).
5. Xác nhận `operation.reference` không nằm trong metric tags, nhưng có thể thấy trong span được xuất khi cấu hình cho phép.

## 10. Đọc metrics ở Actuator

Sau khi gọi ít nhất một operation `createQuote(...)`:

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/shop.order.quote
~~~

Ví dụ response **minh họa** của Timer:

~~~json
{
  "name": "shop.order.quote",
  "measurements": [
    {"statistic": "COUNT", "value": 2.0},
    {"statistic": "TOTAL_TIME", "value": 0.04},
    {"statistic": "MAX", "value": 0.027}
  ],
  "availableTags": [
    {"tag": "module.identifier", "values": ["orders"]},
    {"tag": "order.channel", "values": ["WEB", "MOBILE"]},
    {"tag": "error", "values": ["none"]}
  ]
}
~~~

Giá trị và đơn vị thời gian ở đây **chỉ để minh họa cách đọc**; Actuator trả `baseUnit` hoặc thông số khác theo meter/version và sẽ phản ánh số đo thực tế của ứng dụng. Khi cần tính duration, xác minh đơn vị trước khi suy ra milliseconds.

Điểm cần thấy:

- `COUNT`: số sample Timer đã ghi.
- `TOTAL_TIME`: tổng duration của các sample được chọn.
- `MAX`: thời lượng tối đa được meter theo dõi trong cửa sổ/thời gian phù hợp với registry.
- `availableTags`: các chiều tag có thể dùng để lọc. **Không có** `operation.reference`.

Lọc riêng channel:

~~~bash
curl -i "http://localhost:8080/actuator/metrics/shop.order.quote?tag=module.identifier:orders&tag=order.channel:WEB"
~~~

Actuator dùng **tên meter Micrometer gốc** trong đường dẫn, không dùng tên đã được chuẩn hóa sang Prometheus. Nếu không thấy metric, hãy xác minh operation thực sự chạy và kết thúc, Registry có meter handler, endpoint được expose và request đang đi vào đúng instance/management port.

### 10.1. Kiểm tra tên Prometheus thật trước khi viết truy vấn

Với registry Prometheus:

~~~bash
curl -s http://localhost:8080/actuator/prometheus
~~~

Timer có thể xuất dưới các series theo quy ước Prometheus như `shop_order_quote_seconds_count`, `shop_order_quote_seconds_sum`; tên thực tế phụ thuộc registry và base unit. Ví dụ giả sử exporter dùng các series này:

~~~promql
# Tốc độ hoàn tất operation, nhóm theo module và channel.
sum by (module_identifier, order_channel) (
  rate(shop_order_quote_seconds_count[5m])
)
~~~

~~~promql
# Thời gian trung bình trong 5 phút, đơn vị giây.
sum(rate(shop_order_quote_seconds_sum[5m]))
/
sum(rate(shop_order_quote_seconds_count[5m]))
~~~

Đây là **PromQL minh họa dựa trên tên giả định**. Luôn tra tên series/labels thực tế ở endpoint scrape hoặc giao diện Prometheus. Nếu cần p95/p99, phải cấu hình histogram/percentile phù hợp; không lấy `MAX` trong Actuator rồi gọi đó là p95.

## 11. Đọc cùng operation trong tracing backend

Trong Zipkin, Tempo, Jaeger hoặc công cụ tương đương, tìm trace của request tạo quote theo thời gian và service name. Một cây span lý tưởng có thể gồm:

~~~text
Trace: 61ba9472...
└── HTTP POST /orders/quotes
    └── orders module entry
        └── quote order
            └── payments module entry (nếu operation gọi module này)
~~~

Thực tế số span phụ thuộc instrumentation. Nếu `quote order` nằm trong một module entry span, nó có thể là child; nếu chạy bên ngoài scope hiện hành, nó có thể trở thành root span của trace mới.

Kiểm tra **attributes của span quote**:

~~~text
module.identifier = orders
order.channel     = WEB
operation.reference = ref-a1   # chỉ nếu được gửi an toàn
~~~

Hai thuộc tính đầu là low-cardinality, thuộc tính cuối là high-cardinality. Cả ba **có thể** hiện trên một span được xuất, trong khi Timer chỉ chia theo hai thuộc tính đầu và các tag chung khác.

**Mối quan hệ cha–con không tự đảm bảo:** dùng `@Async`, `Executor` hoặc Reactor scheduler có thể làm observation hiện hành mất khỏi thread mới. Spring Boot tích hợp Micrometer Context Propagation; cần cấu hình hoặc decorate executor và truyền Reactor Context phù hợp khi thực sự có ranh giới bất đồng bộ. Với durable event hoặc message broker, còn cần trace headers/correlation metadata theo giao thức.

## 12. Những nhầm lẫn thường gặp

| Hiện tượng hoặc nhận định | Giải thích đúng |
| --- | --- |
| “Mỗi `Observation` chắc chắn thành một span” | Không; phải có tracing handler/bridge, exporter, sampling và điểm instrumentation phù hợp |
| “Span backend có 100 bản ghi thì chỉ có 100 operation” | Không chắc; sampler có thể chỉ giữ một phần |
| “High-cardinality tags nên xuất luôn vào Prometheus cho tiện tìm kiếm” | Không; dễ tạo lượng time series khổng lồ, trái mục đích phân loại |
| “Low-cardinality keys chỉ có trong metrics” | Với Spring Boot/Micrometer tracing, chúng cũng có thể được gắn vào span |
| “Mọi dữ liệu trong `Observation.Context` đều tự thành span tags” | Không; handler/convention quyết định metadata nào được xuất |
| “`module.events.published` là timer sinh từ `shop.order.quote`” | Không; đây là counter event publication của Spring Modulith |
| “Có module graph thì chắc chắn có module spans” | Không; graph thể hiện dependency, spans cần execution và observability |
| “Có trace nhưng log không có `traceId` nghĩa là trace sai” | Có thể chỉ thiếu log correlation/MDC hoặc context trong thread log |
| “Một span mất parent là do module graph sai” | Thường cần kiểm tra trace context propagation và instrumentation |
| “Mọi key có nhiều giá trị đều được phép đưa vào trace” | Trace backend vẫn có yêu cầu bảo mật, retention và chi phí lưu trữ |

### 12.1. Kiểm tra tính an toàn của metadata

Trước khi thêm một key, hỏi:

1. Mục tiêu là tổng hợp dashboard hay điều tra từng lần chạy?
2. Số giá trị khác nhau có bị giới hạn bởi enum/hợp đồng hay không?
3. Giá trị có chứa thông tin cá nhân, bí mật hoặc dữ liệu cần xóa theo quy định không?
4. Hệ thống tracing/metrics lưu dữ liệu trong bao lâu và ai được phép truy cập?
5. Nếu không thu thập key đó thì có giải pháp an toàn hơn như correlation ID hoặc log audit phân quyền không?

Thông tin cần để thực thi nghiệp vụ phải truyền bằng tham số, command/event payload hoặc persistence chính thức. Observation context **không phải** nơi giữ trạng thái nghiệp vụ thiết yếu.

## 13. Bài thực hành: chứng minh đường đi khác nhau của metadata

**Bài toán:** ứng dụng Spring Boot có module `orders` và `payments`; `orders` instrument operation `shop.order.quote`. Có ba channel `WEB`, `MOBILE`, `API` và mỗi request có một correlation reference giả lập an toàn.

Thực hiện:

1. Thêm Spring Boot Actuator và, nếu cần module entry spans, Spring Modulith Insight starter; cấu hình metrics và tracing exporter tương thích.
2. Tạo bean `OrderQuoteService` theo phần 5. Chỉ dùng reference tổng hợp như `ref-demo-001` trong môi trường học tập.
3. Gọi operation 5 lần: 3 WEB, 1 MOBILE, 1 API. Đợi các observation hoàn tất.
4. Truy vấn `GET /actuator/metrics/shop.order.quote`; ghi `COUNT` và `availableTags`, sau đó lọc `order.channel:WEB`.
5. Xác minh **không có `operation.reference` trong meter tags**.
6. Bật tracing ở môi trường thử nghiệm với exporter và sampling phù hợp. Tìm một trace được ghi nhận, xác minh `order.channel` cùng `operation.reference` nếu backend không lọc attribute này.
7. Giảm sampling trong môi trường test; so sánh số trace có mặt với số metric samples. Giải thích vì sao số liệu có thể khác nhau.
8. Nếu có lời gọi qua `@Async` hoặc Reactor, chủ động kiểm tra quan hệ parent/child; áp dụng context propagation phù hợp khi cần.

Mẫu bảng đối chiếu:

| Quan sát | Kỳ vọng nếu hạ tầng đầy đủ | Lý do |
| --- | --- | --- |
| Timer `shop.order.quote` | `COUNT=5`, nếu không có lần gọi khác/reset | Meter handler ghi một sample cho mỗi operation hoàn tất |
| Lọc `order.channel:WEB` | `COUNT=3` | Low cardinality chia meter theo channel |
| Tag `operation.reference` trên metrics | Không xuất hiện | High cardinality không trở thành metric tag mặc định |
| Span `quote order` | Có thể tìm thấy khi được sample và exporter hoạt động | Tracing handler tạo span |
| Attribute `operation.reference` trên span | Có thể hiển thị theo cấu hình | High cardinality dành cho trace |
| Cạnh `orders → payments` trên graph | Không đổi chỉ vì thêm observation | Graph biểu diễn phụ thuộc tĩnh |

**Tiêu chí hoàn thành:** bạn chỉ ra được hai tập metadata từ cùng observation; giải thích được điều kiện xuất metric và trace; không đếm span để suy ra tổng số request; không đưa high-cardinality key vào metric tag; phân biệt custom operation với event publication metrics của Modulith.

## 14. Câu hỏi ôn tập

1. Có một `ObservationRegistry` trong Spring Boot thì đã chắc chắn có tracing exporter chưa?
2. Vì sao `module.identifier` thích hợp làm low-cardinality key còn `orderId` thường không?
3. `highCardinalityKeyValue("operation.reference", "...")` có tạo một series Prometheus theo từng reference không?
4. Khi `Observation.observe(...)` kết thúc, metrics handler mặc định thường ghi loại meter gì?
5. Tại sao `COUNT` của Timer có thể cao hơn số spans tìm được trong tracing backend?
6. Dữ liệu trong `Observation.Context` có tự được xuất ra ngoài không?
7. Khác biệt giữa `module.events.published` và một Timer như `shop.order.quote`?
8. Vì sao span của event listener bất đồng bộ có thể không thuộc cùng trace với request phát event?
9. Muốn tra một request cụ thể thì dùng metrics hay traces? Muốn tính p95 latency của hàng triệu requests thì dùng nguồn nào?

**Đáp án gợi ý:** (1) Không; cần handler/bridge và exporter riêng. (2) Module identifier hữu hạn còn order ID tăng theo nghiệp vụ. (3) Không với metrics handler mặc định. (4) Timer. (5) Sampling/collector/instrumentation có thể loại bớt traces. (6) Không, cần convention/handler đưa dữ liệu thành key-values phù hợp. (7) Counter đếm công bố domain event khác với Timer đo thời lượng custom operation. (8) Mất hoặc không mang trace context qua async boundary, hoặc listener xử lý lại sau thời điểm request đã kết thúc. (9) Traces để điều tra một lần chạy; metrics histogram/percentiles cho phân phối latency ở quy mô lớn.

## 15. Tóm tắt

**Observation API** cho phép instrument một operation duy nhất và dùng nhiều handler để tạo dữ liệu quan sát. Quy tắc quan trọng nhất khi phân biệt đường đi dữ liệu:

~~~text
Observation name + duration + LOW CARDINALITY keys
                │
                ├── Metrics handler  → Timer / meter tags / dashboard
                │
                └── Tracing handler  → Span / attributes / trace backend

HIGH CARDINALITY keys ────────────────→ Trace attributes (nếu được xuất)
                                        Không đưa vào metric tags mặc định
~~~

Trong Spring Modulith, việc hiểu đường đi này giúp bạn lý giải **module entry spans**, đọc **event publication metrics**, truy vấn Actuator và đánh giá context propagation mà không đánh đồng module graph với hoạt động runtime. Luôn kiểm chứng output thật trong ứng dụng vì mỗi đường xuất dữ liệu còn phụ thuộc phiên bản, handlers, sampling, registry và exporter.

### Tài liệu tham khảo

- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry, low/high cardinality key-values, context propagation.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): Context, handler, timer, span và vòng đời observation.
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): API quan sát, conventions và key-value semantics.
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html): nguy cơ cardinality khi thiết kế metric tags.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): truy vấn Actuator và cách xuất dữ liệu sang monitoring system.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): Micrometer Tracing, sampling và exporters.
- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): module entry spans, module metadata và event publication counters.

> **Lưu ý phiên bản:** ví dụ hướng đến các dòng Spring Boot/Spring Modulith/Micrometer hiện hành; một số handler, cấu hình timer, tracing bridge hoặc exporter có khác biệt giữa major versions. Khi triển khai, đối chiếu tài liệu đúng phiên bản và BOM của dự án. Bài được viết ở STEP 4; việc Content QA chuyên sâu thuộc bước riêng.
