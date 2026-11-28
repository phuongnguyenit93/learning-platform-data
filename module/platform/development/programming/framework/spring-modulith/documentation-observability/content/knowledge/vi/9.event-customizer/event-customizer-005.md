# Chọn tag có cardinality thấp

Spring Modulith có thể ghi nhận các **domain event được publish** bằng Micrometer counters. Với `ModulithEventMetricsCustomizer`, nhóm phát triển còn có thể thêm thông tin từ từng sự kiện vào metric: kênh đặt hàng, nhóm khách hàng hay nhóm kết quả. Đây là cách giúp dashboard trả lời những câu hỏi nghiệp vụ như “đơn từ kênh mobile đang tăng hay giảm?” mà vẫn giữ được bức tranh kiến trúc theo **application module**.

Nhưng một tag được lấy trực tiếp từ event cũng có thể gây sự cố vận hành. Nếu gắn `orderId` hoặc `eventId` vào counter, mỗi đơn hàng mới có khả năng tạo ra **một meter/time series mới**. Sau một ngày, số chuỗi thời gian có thể tăng theo số đơn hàng dù toàn bộ event thuộc cùng một loại. Đó là vấn đề **high cardinality**.

Bài học thuộc chương **Event customizer** của chủ đề `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Mục tiêu là chọn các **low-cardinality tags** phù hợp khi quan sát sự kiện xuyên module trong Spring Boot, hiểu chính xác API customizer của Spring Modulith, và kiểm chứng metric bằng Actuator/Prometheus. Các nhãn được chọn cần giúp phân tích hành vi mà không làm tăng số series ngoài kiểm soát.

> **Phạm vi:** Ví dụ dùng API `ModulithEventMetricsCustomizer` có trong các dòng Spring Modulith hỗ trợ tính năng này (API xuất hiện từ 1.4). Đối chiếu BOM, dependency tree và tài liệu phiên bản dự án trước khi áp dụng. Tên metric mặc định dưới đây dựa theo tài liệu Spring Modulith; tên series khi export sang Prometheus có thể được chuẩn hóa khác.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích `tag`, `meter`, `time series` và **cardinality** trong Micrometer/Prometheus.
2. Phân biệt nhãn **low cardinality** (giá trị hữu hạn, ít biến thể) với nhãn **high cardinality** (giá trị tăng theo request, user hoặc event).
3. Nêu được những tag mặc định trong event metrics của Spring Modulith và phạm vi áp dụng của `ModulithEventMetricsCustomizer`.
4. Viết customizer dùng enum/nhóm giá trị hữu hạn thay vì đưa ID nghiệp vụ vào `Counter.Builder`.
5. Ước lượng số series có thể phát sinh khi kết hợp nhiều tag, kể cả tag có giá trị hữu hạn.
6. Kiểm tra metric đã được tạo và số lượng tag values sau khi publish event, phân biệt **publish** với **consume**.
7. Quyết định khi nào nên dùng metric, khi nào nên dùng trace/log/correlation ID.

## 2. Cardinality liên quan gì đến application event?

Trong Micrometer, một meter được phân biệt bởi **tên** và **tập tag key/value** của nó. Hai counters có cùng tên nhưng khác một giá trị tag là hai meter khác nhau. Khi export sang backend metrics, chúng thường xuất hiện dưới dạng những **time series** riêng biệt.

Ví dụ, một metric publish event với tag `order.channel`:

~~~text
module.events.published.order.OrderPlaced{order.channel="web"}
module.events.published.order.OrderPlaced{order.channel="mobile"}
module.events.published.order.OrderPlaced{order.channel="partner"}
~~~

Các dòng trên biểu diễn **ý tưởng về bộ meter và tags**; không phải văn bản chính xác từ endpoint Prometheus. Tên metric ở backend có thể được chuyển đổi dấu chấm, chữ hoa và hậu tố counter.

Nếu giá trị `order.channel` chỉ nằm trong ba nhóm `web`, `mobile` và `partner`, nó có **cardinality thấp**. Dù hàng triệu đơn phát ra, số nhóm giá trị vẫn là ba. Trái lại, nếu tag là `order.id`, mỗi đơn mới có ID mới và số giá trị có xu hướng tăng theo lưu lượng.

| Tag | Ví dụ giá trị | Đánh giá | Lý do |
| --- | --- | --- | --- |
| `module.identifier` | `order`, `inventory` | Thường thấp | Danh sách application module được quản lý theo thiết kế. |
| `module.event.type` | `OrderPlaced`, `PaymentAuthorized` | Thường thấp | Tập loại event do code định nghĩa. |
| `order.channel` | `web`, `mobile`, `partner` | Thấp | Enum hoặc bảng phân loại cố định. |
| `customer.segment` | `retail`, `business` | Thấp | Giá trị phân nhóm có kiểm soát. |
| `outcome` | `success`, `failure` | Thấp khi được chuẩn hóa | Chỉ nên dùng tập kết quả xác định trước. |
| `region` | `north`, `central`, `south` | Thấp nếu quy ước rõ | Không lấy chuỗi địa chỉ tùy ý của khách. |
| `order.id` | UUID mỗi đơn hàng | Rất cao | Giá trị mới xuất hiện với gần như mọi event. |
| `event.id` | UUID mỗi lần phát sự kiện | Rất cao | Số biến thể tăng theo số publication. |
| `user.id`, `email` | ID hoặc email người dùng | Rất cao | Vừa gây tăng series, vừa có rủi ro riêng tư. |
| `trace.id` | ID trace mỗi request | Rất cao | Dùng để tương quan trace, không dùng làm metric tag. |
| `error.message` | Text exception tùy ý | Cao/không ổn định | Nội dung lỗi có thể chứa ID hoặc dữ liệu thay đổi. |
| `amount` | Số tiền chính xác | Cao | Giá trị gần như liên tục; nên phân nhóm khi thật sự cần. |

**Low cardinality không có nghĩa chỉ cần tag “trông ngắn”.** Chuỗi `1`, `2`, `3` có thể rất ngắn nhưng nếu đó là order ID thì số giá trị là không giới hạn. Cardinality được quyết định bởi **số giá trị khác nhau có thể phát sinh trong vận hành**, không phải độ dài chuỗi.

## 3. Vì sao số series có thể tăng theo phép nhân?

Giả sử một loại event có hai tag:

- `order.channel`: ba giá trị `web`, `mobile`, `partner`.
- `customer.segment`: hai giá trị `retail`, `business`.

Số tổ hợp tag tối đa cho một tên meter là:

\[
N_{\text{series}} \leq 3 \times 2 = 6
\]

Nếu thêm `payment.method` gồm bốn giá trị, số tổ hợp tiềm năng thành:

\[
N_{\text{series}} \leq 3 \times 2 \times 4 = 24
\]

Với nhiều module, loại event, instance và environment, tổng số series có thể tăng tiếp. Các counters của Spring Modulith còn có metric riêng theo loại event, nên **số tên meter** cũng là một phần của ngân sách lưu trữ. Trong backend Prometheus, nhãn instance/job và các series bổ sung do kiểu meter/registry có thể khiến số chuỗi thực tế khác ước lượng đơn giản.

Ví dụ minh họa tổng quan, nếu có 4 metric tên khác nhau; mỗi metric có 3 kênh và 2 nhóm khách; hệ thống có 3 instances thì có thể xuất hiện tới `4 × 3 × 2 × 3 = 72` tổ hợp series cho những nhãn đang xét. Đây là **ước lượng trần lý thuyết**, không phải số series chắc chắn sẽ có: chỉ những tổ hợp thực sự được ghi nhận và export mới hiện diện.

~~~mermaid
flowchart LR
    A["Một loại event"] --> C["channel: 3 giá trị"]
    C --> S["segment: 2 giá trị"]
    S --> R["Tối đa 6 tổ hợp tag"]
    R --> I["3 instances"]
    I --> N["Tối đa 18 series cho metric đó"]
~~~

**Nguyên tắc thiết kế:** đếm không chỉ cardinality của từng tag mà còn **tích số của các chiều**. Một tag có bảy giá trị có thể chấp nhận được khi dùng riêng, nhưng không nhất thiết phù hợp khi kết hợp với mười chiều khác.

## 4. Những event metrics mà Spring Modulith cung cấp

Theo tài liệu Spring Modulith, khi tính năng event observability được bật đúng phiên bản, hệ thống ghi nhận các publication qua hai nhóm counter:

| Meter logic | Nội dung | Tag có sẵn theo tài liệu |
| --- | --- | --- |
| `module.events.published` | Counter tổng hợp các sự kiện được publish | `module.event.type`, `module.identifier`, `module.name` |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter riêng cho loại event ở một module, có thể bổ sung tag miền nghiệp vụ | `module.identifier`, `module.name` |

Tên thứ hai là **mẫu tên**: phần `$moduleIdentifier` và `$simpleEventTypeName` được thay theo module và event thực tế, ví dụ về mặt khái niệm `module.events.published.order.OrderPlaced`.

`ModulithEventMetricsCustomizer` cho phép tùy biến counter **riêng cho từng event type** bằng cách truy cập `Counter.Builder`. Đây là điểm phù hợp để thêm tag phân nhóm có ý nghĩa, như kênh bán hàng hoặc phân khúc khách hàng. Customizer không phải cách tự động gắn mọi giá trị event lên metric và cũng không có nghĩa mọi event đều phải thêm tag.

### Publication khác consumption

Cần phân biệt các thời điểm:

~~~mermaid
sequenceDiagram
    participant HTTP as HTTP / order service
    participant Pub as ApplicationEventPublisher
    participant Metric as Event publication counter
    participant Listener as inventory listener
    participant DB as Database

    HTTP->>DB: Lưu đơn
    HTTP->>Pub: publish OrderPlaced
    Pub->>Metric: Ghi lượt publication nếu instrumentation hoạt động
    Pub-->>Listener: Listener nhận event (có thể async)
    Listener->>DB: Giữ hàng
    Note over Listener,DB: Consumer có thể lỗi hoặc được thử lại
~~~

Counter `module.events.published` nói về **sự kiện được publish**, không phải số listener đã chạy thành công. Một event có thể được nhiều consumer nhận; listener có thể lỗi, được retry hoặc bỏ qua tùy cấu hình. Muốn đo độ trễ/lỗi consumer cần instrumentation riêng cho listener hoặc những tín hiệu hệ thống cung cấp.

Event Publication Registry (nếu ứng dụng cấu hình backend lưu trữ phù hợp) có thể theo dõi publication chưa hoàn tất và hỗ trợ các cơ chế xử lý lại. Registry cũng **không tự biến publish counter thành một metric đo số lần xử lý thành công**.

## 5. Cách chọn tag trước khi viết customizer

Với mỗi tag định thêm vào event metric, hãy trả lời bốn câu hỏi:

1. **Câu hỏi vận hành là gì?** Ví dụ cần phân biệt số đơn được publish giữa kênh web và mobile để theo dõi một chiến dịch hoặc kiểm tra tích hợp.
2. **Tập giá trị tối đa là bao nhiêu?** Với enum ba phần tử, giới hạn đã rõ. Với chuỗi do client gửi, giới hạn thường không rõ.
3. **Chiều đó kết hợp với những chiều nào?** Event type, module, instance, region, outcome và các nhãn hạ tầng đều có thể nhân số series.
4. **Giá trị có ổn định, nhất quán và an toàn không?** Nếu cùng một ý nghĩa được ghi thành `MOBILE`, `mobile` và `m-app`, chúng có thể tạo ba series không cần thiết.

Đối với ví dụ cửa hàng:

| Câu hỏi | Tag nên cân nhắc | Cách chuẩn hóa |
| --- | --- | --- |
| Đơn đến từ kênh nào? | `order.channel` | Enum: `web` / `mobile` / `partner` |
| Đơn thuộc nhóm khách nào? | `customer.segment` | `retail` / `business` |
| Event do module nào phát? | Sử dụng `module.identifier` có sẵn | Không thêm tag trùng ngữ nghĩa. |
| Có bao nhiêu publication của `OrderPlaced`? | Dùng metric riêng theo event type | Không thêm event ID để đếm từng publication. |
| Đơn hàng cụ thể nào gặp lỗi? | Không nên thêm tag metric | Dùng log/trace/correlation hoặc dữ liệu nghiệp vụ với phân quyền. |
| Người dùng nào phát event? | Không nên thêm user ID | Kiểm tra nguồn nghiệp vụ có quyền truy cập thích hợp. |
| Giá trị đơn là bao nhiêu? | Chỉ dùng một số nhóm giá trị nếu có nhu cầu | Ví dụ `small` / `medium` / `large`, không dùng tiền chính xác. |

**Không thêm tag chỉ vì event có trường đó.** Một trường hữu ích trong domain object chưa chắc hữu ích để nhóm metrics theo thời gian.

## 6. Ví dụ event có các giá trị được kiểm soát

Giả sử module `order` phát một record `OrderPlaced` chứa ID để đối soát nghiệp vụ, kênh đặt hàng và nhóm khách:

~~~java
// com.example.shop.order.OrderPlaced
package com.example.shop.order;

import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID orderId,
        SalesChannel channel,
        CustomerSegment segment) {

    public OrderPlaced {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(channel, "channel");
        Objects.requireNonNull(segment, "segment");
    }

    public enum SalesChannel {
        WEB, MOBILE, PARTNER
    }

    public enum CustomerSegment {
        RETAIL, BUSINESS
    }
}
~~~

Đây là mã Java 17 trở lên. `orderId` tồn tại để nhận diện đơn trong nghiệp vụ nhưng **sẽ không đưa vào metric tag**. Trường `channel` chỉ có ba trường hợp, `segment` chỉ có hai trường hợp, nên phù hợp để dùng làm các nhãn tổng hợp.

Một service trong module `order` có thể phát sự kiện bằng `ApplicationEventPublisher`:

~~~java
package com.example.shop.order;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void place(UUID orderId) {
        // Trong mã thật, lưu đơn và quản lý transaction phù hợp.
        publisher.publishEvent(new OrderPlaced(
                orderId,
                OrderPlaced.SalesChannel.MOBILE,
                OrderPlaced.CustomerSegment.RETAIL));
    }
}
~~~

Đoạn mã minh họa thời điểm publish, chưa mô tả đầy đủ transaction, persistence, idempotency và độ tin cậy của event. Vì vậy không dùng nó làm mẫu hoàn chỉnh cho nghiệp vụ sản xuất.

## 7. Cấu hình `ModulithEventMetricsCustomizer` với tag hữu hạn

Tài liệu Spring Modulith cung cấp interface:

~~~text
org.springframework.modulith.observability.ModulithEventMetricsCustomizer
~~~

Customizer nhận một đối tượng `ModulithEventMetrics`, từ đó có thể gọi `customize(Class<T>, BiConsumer<T, Counter.Builder>)` để điều chỉnh builder khi xử lý event có kiểu phù hợp.

Ví dụ cấu hình:

~~~java
package com.example.shop;

import com.example.shop.order.OrderPlaced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
public class EventObservabilityConfiguration {

    @Bean
    ModulithEventMetricsCustomizer orderEventTags() {
        return metrics -> metrics.customize(
                OrderPlaced.class,
                (event, counter) -> {
                    counter.tag(
                            "order.channel",
                            switch (event.channel()) {
                                case WEB -> "web";
                                case MOBILE -> "mobile";
                                case PARTNER -> "partner";
                            });

                    counter.tag(
                            "customer.segment",
                            switch (event.segment()) {
                                case RETAIL -> "retail";
                                case BUSINESS -> "business";
                            });
                });
    }
}
~~~

Đây là phần quan trọng nhất của bài:

- **Đúng điểm mở rộng:** bean `ModulithEventMetricsCustomizer` tùy biến việc tạo counter cho event type `OrderPlaced`; nó không được gọi thủ công mỗi lần publish.
- **Đúng API:** callback nhận `event` và `Counter.Builder`. Hàm `tag(key, value)` thêm một nhãn vào builder.
- **Đúng cardinality:** tag `order.channel` có tối đa 3 giá trị, tag `customer.segment` có tối đa 2 giá trị, tạo tối đa 6 tổ hợp với một tên metric trước các chiều khác.
- **Không làm lộ ID:** `orderId` vẫn có trong event để phục vụ nghiệp vụ, nhưng callback không đọc ID đó để thêm tag.
- **Đúng mục đích:** counter ghi số lượt publish theo kênh/nhóm khách, không đếm thành công của listener.

Nếu sự kiện có channel chưa biết, nên **chuẩn hóa thành một nhóm hữu hạn** như `other` hoặc xử lý giá trị không hợp lệ tại domain boundary. Với ví dụ enum ở trên, mọi giá trị đã được liệt kê, nên switch không cần nhánh nhận chuỗi tùy ý.

### Dependency cần chú ý

Theo tài liệu Spring Modulith, có thể bật hỗ trợ Insight/observability bằng runtime dependency thích hợp. Khi **viết mã tham chiếu đến interface customizer**, cần có API artifact ở **compile scope**:

~~~xml
<dependencies>
    <!-- Dùng bản tương thích với BOM Spring Modulith của dự án. -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-api</artifactId>
    </dependency>

    <!-- Runtime instrumentation: dùng starter hỗ trợ observability. -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Expose Actuator metrics và/hoặc Prometheus theo nhu cầu. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ trên **không chỉ định version cố định** vì dự án phải dùng BOM/parent tương thích. Starter có thể đã kéo theo một số dependency; kiểm tra dependency tree trước khi khai báo thêm. Với ứng dụng chỉ cần tùy biến event metrics, vẫn phải xác nhận instrumentation ghi counters của phiên bản đang chạy. Tracing backend là hệ thống khác; chỉ cần xuất metrics sang Prometheus thì chưa nhất thiết phải cài OTLP tracing.

## 8. Ví dụ sai: đưa ID vào tag

Đoạn mã sau là **phản ví dụ, không sử dụng trong ứng dụng**:

~~~java
// KHÔNG LÀM NHƯ VẬY:
metrics.customize(OrderPlaced.class, (event, counter) -> {
    counter.tag("order.id", event.orderId().toString());
});
~~~

Nếu có 100.000 đơn hàng khác nhau được publish, giá trị `order.id` có thể tạo đến 100.000 tổ hợp nhãn cho một metric (trước khi cộng các chiều khác), khiến số meter/series tăng theo lưu lượng. Vấn đề có thể xảy ra trong chính ứng dụng ở bước registry tạo meter, **ngay cả trước khi Prometheus kịp scrape**.

Đổi từ `order.id` sang `event.id` hay `trace.id` không giải quyết vấn đề. Cũng không nên đưa UUID vào **tên metric** như `module.events.published.order.ABC-123`: đổi tên chỉ chuyển sự bùng nổ từ tags sang số tên meter.

### Nếu thực sự cần tìm một event riêng?

Chọn công cụ phù hợp với câu hỏi:

| Câu hỏi | Dữ liệu phù hợp | Vì sao |
| --- | --- | --- |
| Có bao nhiêu event `OrderPlaced`/phút? | Counter và `rate`/`increase` | Dữ liệu tổng hợp theo loại event. |
| Tỷ trọng sự kiện theo kênh nào? | Counter với `order.channel` | Kênh là nhãn hữu hạn. |
| Sự kiện mang ID `E123` đã được publish chưa? | Application log có cấu trúc, bảng publication/nghiệp vụ (nếu có) | Cần tra một record cụ thể. |
| Listener nhận sự kiện nhưng vì sao thất bại? | Trace/log liên kết, consumer metrics, dữ liệu nghiệp vụ | Publish counter không phản ánh kết quả xử lý. |
| Module nào gây độ trễ trên request? | Module spans và HTTP spans có context | Cần đường đi thực thi, không chỉ số lượt event. |

Với Micrometer Observation, dữ liệu có cardinality cao có thể được đưa vào **high-cardinality key values** dành cho tracing khi phù hợp, thay vì low-cardinality metric tags. Dù vậy, không nên mặc định đưa mọi ID cá nhân hoặc thông tin nhạy cảm lên trace: phải xét chính sách bảo mật, sampling, lưu giữ và phân quyền.

## 9. Event customizer và tracing: hai loại mở rộng khác nhau

Tên “event customizer” dễ dẫn đến hiểu nhầm rằng chỉ cần thêm tag là sẽ tự động có trace tương ứng. Thực tế:

- `ModulithEventMetricsCustomizer` tùy biến **counter của event publications** qua Micrometer `Counter.Builder`.
- `ModulithObservationConvention` liên quan đến **quy ước observation** cho tương tác module; phạm vi và tag keys của nó là mối quan tâm khác.
- Spring Boot/Micrometer Tracing có thể tạo **spans** khi tracing handler và exporter được cấu hình; customizer counter **không tự tạo span**.
- Event listener bất đồng bộ có thể cần **context propagation** để nối telemetry với request gốc; thêm tag metric không khắc phục được trace ID bị đứt.

~~~mermaid
flowchart TB
    Event["Publisher gửi OrderPlaced"] --> Modulith["Spring Modulith event observability"]
    Modulith --> C["Counter publication"]
    C --> Custom["ModulithEventMetricsCustomizer"]
    Custom --> Meter["Counter + channel/segment tags"]
    Meter --> Prom["Micrometer registry → Actuator/Prometheus"]
    Event -. "Nếu có instrument + context" .-> Listener["Listener bất đồng bộ"]
    Listener --> Span["Observation/Trace nếu cấu hình"]
    Listener --> ErrorMetric["Metric xử lý thành công/lỗi nếu được instrument"]
~~~

Điểm phân biệt: **counter publication** đo số lần phát; **listener processing** đo số lần và kết quả tiêu thụ. Không dùng biểu đồ publication để kết luận “mọi listener đã xử lý đúng một lần”.

## 10. Đo lỗi consumer mà vẫn giữ cardinality thấp

Nếu muốn phân tích listener, tạo một metric **riêng cho số lượt xử lý**, không đặt tên khiến người đọc nhầm với publication counter:

~~~java
package com.example.shop.inventory;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

public class InventoryEventMetrics {

    private final MeterRegistry meters;

    public InventoryEventMetrics(MeterRegistry meters) {
        this.meters = meters;
    }

    public void record(String outcome) {
        String normalized = switch (outcome) {
            case "success" -> "success";
            case "business_rejected" -> "business_rejected";
            case "retryable_failure" -> "retryable_failure";
            default -> "other";
        };

        Counter.builder("shop.event.consumer.attempts")
                .tag("consumer.module", "inventory")
                .tag("event.type", "OrderPlaced")
                .tag("outcome", normalized)
                .register(meters)
                .increment();
    }
}
~~~

Đoạn mã thể hiện **một quy ước tự xây dựng**, không phải metric mặc định của Spring Modulith. Trong dự án thật, nên dùng enum cho `outcome` thay vì chuỗi nếu có thể và ghi nhận tại ranh giới listener để không bỏ sót exception.

Một listener có thể được retry, vì vậy `shop.event.consumer.attempts` đo **số lần thử xử lý**, không đếm số event độc nhất. Muốn đo số event hoàn tất duy nhất, cần thêm dữ liệu trạng thái nghiệp vụ hoặc publication registry và quy tắc idempotency tương ứng.

## 11. Bảo vệ hệ thống bằng ngân sách cardinality

Ngay cả khi mọi tag đều có tập giá trị nhỏ, việc kết hợp quá nhiều tag vẫn có thể tạo hàng nghìn series. Trước khi triển khai, hãy lập một **cardinality budget** cho từng metric:

| Hạng mục | Câu hỏi kiểm tra |
| --- | --- |
| Tên metric | Có bao nhiêu metric names phát sinh theo module/event type? Có đặt giá trị động vào tên không? |
| Tag keys | Có bao nhiêu chiều phân nhóm? Chiều nào thực sự cần cho dashboard/alert? |
| Tag values | Mỗi chiều có tối đa bao nhiêu giá trị, có nhánh `other` rõ ràng không? |
| Tổ hợp tối đa | Tích các số giá trị có nằm trong ngân sách không? |
| Số instances | Sau khi nhân theo instance/job/environment, series có vượt ngân sách không? |
| Tần suất scrape | Metrics lớn có làm tăng CPU, network hoặc storage không? |
| Vòng đời tag | Đổi tên enum/nhóm có tạo thêm series cũ và mới trong thời gian chuyển đổi không? |

Với các tag mới, nên **kiểm tra độ tăng theo traffic**: nếu chạy 10.000 events nhưng cùng một số nhóm hợp lệ, số meter phân biệt bởi tag **không nên tăng theo tỷ lệ 10.000**. Counter value sẽ tăng, còn số tổ hợp series ổn định sau khi đã xuất hiện đủ các nhóm.

### Guardrail bằng Micrometer MeterFilter

Micrometer hỗ trợ các `MeterFilter` như `maximumAllowableTags` để chặn thêm quá nhiều giá trị tag khi một metric family vượt ngưỡng. Ví dụ minh họa cho một ứng dụng đã dùng Micrometer:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.config.MeterFilter;
import org.springframework.boot.actuate.autoconfigure.metrics.MeterRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class MetricSafetyConfiguration {

    @Bean
    MeterRegistryCustomizer<MeterRegistry> limitChannelTags() {
        return registry -> registry.config().meterFilter(
                MeterFilter.maximumAllowableTags(
                        "module.events.published.",
                        "order.channel",
                        4,
                        MeterFilter.deny()));
    }
}
~~~

Ở đây prefix nhắm tới tên metric riêng theo event; giới hạn bốn giá trị cho `order.channel` là **lưới an toàn**, không phải mục tiêu thiết kế. Khi giới hạn bị vượt và `deny()` áp dụng, **những meter mới có thể bị từ chối**, làm thiếu dữ liệu metrics; không dùng cách này để che một tập tag đang tăng không giới hạn. Cần ghi nhận/cảnh báo và sửa ngay nguồn tag không chuẩn hóa.

Khả năng và API của `MeterFilter` có thể thay đổi theo phiên bản Micrometer; kiểm tra docs và danh sách meter thực tế trước khi dùng guardrail trong production.

## 12. Kiểm chứng tags sau khi chạy ứng dụng

Để xác minh customizer hoạt động, cần nhìn thấy ít nhất hai event có channel khác nhau và biết rõ số publication đã phát. Ví dụ cấu hình Actuator cho môi trường phát triển:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
~~~

Registry Prometheus phải có trong dependency nếu muốn dùng `/actuator/prometheus`; exposure không tự cài registry.

### Bước 1 — Khởi động và kiểm tra endpoint

~~~bash
curl -i http://localhost:8080/actuator
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
~~~

Nếu cổng/path khác mặc định, điều chỉnh đúng địa chỉ. HTTP `404` có thể do thiếu dependency, endpoint chưa expose hoặc path khác; `401/403` cho biết còn yêu cầu xác thực/phân quyền.

### Bước 2 — Publish event với nhiều nhóm hữu hạn

Trong môi trường local/test, tạo ít nhất một `OrderPlaced` có `channel=WEB` và một event có `channel=MOBILE`, sau đó kiểm tra counter. Nếu ứng dụng chưa có endpoint tạo đơn, hãy dùng test/luồng nghiệp vụ sẵn có để phát event, tránh thêm API debug vào production.

Ví dụ logic kỳ vọng:

~~~text
OrderPlaced(order-1, WEB, RETAIL)
OrderPlaced(order-2, WEB, RETAIL)
OrderPlaced(order-3, MOBILE, BUSINESS)

Counter publication theo channel/segment:
  web + retail       → count tăng 2
  mobile + business  → count tăng 1
~~~

Các chữ `order-1`, `order-2` chỉ là giá trị minh họa cho ID nghiệp vụ; **không xuất hiện thành tag**.

### Bước 3 — Kiểm tra metric qua Actuator

Trước tiên xem danh sách tại `/actuator/metrics`. Với tên meter mặc định được tài liệu mô tả, có thể thử:

~~~bash
curl -i http://localhost:8080/actuator/metrics/module.events.published
curl -i http://localhost:8080/actuator/metrics/module.events.published.order.OrderPlaced
~~~

Đường dẫn thứ hai giả định module identifier là `order` và simple event class name là `OrderPlaced`. Nếu dự án đặt module ID khác, hãy lấy tên metric thật từ Actuator. Trong phản hồi, kiểm tra `availableTags`, số đo counter và các tổ hợp nhãn `order.channel`, `customer.segment`.

Đừng kiểm tra customizer bằng cách chỉ xem counter tổng `module.events.published`: customizer áp dụng cho **individual event counter**, do đó tag miền nghiệp vụ có thể không xuất hiện ở counter tổng.

### Bước 4 — Kiểm tra Prometheus exposition

~~~bash
curl -i http://localhost:8080/actuator/prometheus
~~~

Tìm series có gốc tên metric event publication và nhãn đã chuẩn hóa. Tên meter dùng dấu chấm trong Micrometer có thể đổi sang dấu gạch dưới và hậu tố `_total` trong Prometheus; tên thực tế cần được lấy từ output. Các tag key chứa dấu chấm cũng có thể được chuyển đổi theo quy tắc backend.

Với Prometheus scrape đã hoạt động, tạo thêm event trong vài chu kỳ scrape và kiểm tra **counter value tăng** trong khi **số lượng giá trị tag vẫn nằm trong tập cho phép**. Nếu event publishing vẫn tăng mà số series cũng tăng tương ứng từng event, cần tìm tag chứa ID hoặc tên metric động.

### Bước 5 — Ước lượng số meter đang có

Trong môi trường test, có thể kiểm tra registry cho tên meter thật:

~~~java
import io.micrometer.core.instrument.Meter;
import io.micrometer.core.instrument.MeterRegistry;

// Đặt trong một test hoặc đoạn chẩn đoán cục bộ đã có MeterRegistry.
String eventMeterName = "module.events.published.order.OrderPlaced";

long uniqueMeters = registry.getMeters().stream()
        .map(Meter::getId)
        .filter(id -> id.getName().equals(eventMeterName))
        .count();

System.out.println("Meters for OrderPlaced: " + uniqueMeters);
~~~

Ở đây `registry` là biến `MeterRegistry` được inject vào test/chẩn đoán; đoạn mã không phải một chương trình Java độc lập. Sau khi phát đủ các tổ hợp channel/segment, số meter cho loại event này nên ổn định theo số tổ hợp đã xuất hiện. Kết quả có thể khác số series Prometheus vì backend còn có nhãn hạ tầng hoặc các series phụ.

## 13. Xử lý các trường hợp khó

### Trường từ client là chuỗi tự do

Giả sử client gửi `channel="ios-app-v27-beta"` hoặc giá trị tùy ý. Nếu đưa nguyên văn vào tag, nhãn không còn hữu hạn. Hãy ánh xạ về một trong những nhóm được phép, hoặc từ chối dữ liệu không hợp lệ tại lớp domain:

~~~java
static String normalizeChannel(String raw) {
    if (raw == null) {
        return "other";
    }

    return switch (raw.trim().toLowerCase(java.util.Locale.ROOT)) {
        case "web" -> "web";
        case "mobile", "ios", "android" -> "mobile";
        case "partner" -> "partner";
        default -> "other";
    };
}
~~~

Đây là hàm minh họa dùng khi đầu vào không được mô hình hóa thành enum. Nếu nhánh `other` quá lớn, cần bổ sung kiểm tra chất lượng dữ liệu, không tự động biến từng giá trị `other` thành một tag mới.

### Một dimension hữu hạn nhưng có quá nhiều giá trị

Ví dụ mã quốc gia thuộc tập hữu hạn, nhưng nếu hiện có hàng trăm quốc gia, kết hợp nó với nhiều dimensions khác vẫn làm số series lớn. Hãy cân nhắc nhóm theo khu vực đã quy ước nếu yêu cầu dashboard chỉ cần mức đó.

### Tên event động hoặc package đổi

Spring Modulith có counter tên riêng theo module identifier và simple event type name. Khi rename module hoặc event class, tên metric có thể thay đổi. Kế hoạch refactor cần tính đến dashboard/alert cũ và mới; không cố “ổn định” bằng cách đưa UUID hoặc chuỗi người dùng vào tên metric.

### Lỗi nhiều loại

Đừng dùng exception message làm `failure.reason`. Nên tạo enum phân nhóm có giới hạn, ví dụ `validation`, `stock_unavailable`, `upstream_failure` và `other`. Nếu người vận hành cần stack trace hoặc mã lỗi chi tiết của một lần xử lý, xem logs/traces phù hợp.

### Metric là publication chứ không phải trạng thái transaction cuối

Counter chỉ phản ánh **thời điểm/sự kiện mà instrumentation ghi nhận**. Không nên suy từ nó rằng transaction đã commit theo chính sách nghiệp vụ, consumer đã hoàn tất hoặc dữ liệu đã đồng bộ mọi nơi. Để trả lời các câu hỏi này phải có publication state, logs/trace và bằng chứng dữ liệu thật.

## 14. Tình huống điều tra: dashboard bỗng có hàng nghìn series

Một ngày, Prometheus bắt đầu ghi nhận số series cho event `OrderPlaced` tăng liên tục, dù khối lượng event chưa thay đổi nhiều. Sau khi xem `/actuator/metrics`, nhóm vận hành phát hiện customizer mới được triển khai đã thêm `customer.id` vào mọi individual event counter.

Các bước xử lý:

1. Xác định metric name và tag key gây tăng giá trị. So sánh số giá trị duy nhất của `customer.id` theo thời gian.
2. Kiểm tra customizer, quy ước metric và những thay đổi gần đây. Xác nhận có trường ID đưa trực tiếp vào `Counter.Builder`.
3. Loại bỏ tag đó hoặc thay bằng nhóm nhỏ thật sự hữu ích cho dashboard, ví dụ `customer.segment`.
4. Kiểm tra registry mới sau khi sửa; xác nhận số meter của loại event ổn định khi traffic tăng.
5. Theo dõi mức sử dụng memory/series và vòng đời dữ liệu cũ trong backend; xóa tag ở nguồn **không lập tức xóa mọi series đã lưu**.
6. Chỉnh dashboard/alert dùng nhãn mới, ghi chú thay đổi để tránh hiểu nhầm khoảng thời gian trước/sau refactor.

Với những trường hợp cần bảo vệ khẩn cấp, `MeterFilter` có thể giới hạn số tag values nhưng có nguy cơ làm thiếu metric. Giải pháp bền vững vẫn là **sửa thiết kế instrumentation**.

## 15. Bài thực hành

Thực hiện trên một ứng dụng Spring Boot/Spring Modulith có module `order` và một luồng phát `OrderPlaced`, trong môi trường test:

1. **Xác nhận module graph.** Kiểm tra module `order` được phát hiện đúng và event class thuộc API phù hợp với thiết kế.
2. **Bật event observability.** Kiểm tra dependency, startup và tên metric event publication trong `/actuator/metrics`.
3. **Thêm customizer.** Sử dụng `ModulithEventMetricsCustomizer` gắn `order.channel` và `customer.segment` như ví dụ.
4. **Phát nhiều event.** Thử ba kênh, hai nhóm khách và số lượng ID khác nhau; dự đoán tối đa sáu tổ hợp tag cho tên meter.
5. **Đọc metrics.** So sánh giá trị counter với số lượt publish, đối chiếu available tags và series Prometheus.
6. **Cố ý thử phản ví dụ trong test cô lập.** Thêm `order.id` làm tag, phát nhiều ID; đo số meter/series tăng như thế nào, sau đó khôi phục thiết kế an toàn.
7. **Xem nhánh consumer.** Nếu có listener `inventory`, thử một lỗi có kiểm soát và giải thích vì sao publication counter không giảm hoặc “đổi thành failure” theo kết quả listener.
8. **Viết quyết định thiết kế.** Mỗi tag phải có mô tả, tập giá trị tối đa, người sử dụng dashboard và phương án xử lý giá trị ngoài danh mục.

Mẫu ghi nhận:

| Metric/tag | Tập giá trị dự kiến | Số giá trị thực quan sát | Có tăng theo số event không? | Quyết định |
| --- | --- | --- | --- | --- |
| `module.identifier` | Các module cố định | … | … | Giữ tag mặc định |
| `order.channel` | web/mobile/partner | … | … | … |
| `customer.segment` | retail/business | … | … | … |
| `order.id` (thử nghiệm sai) | Mỗi event gần như một ID | … | … | Loại bỏ |

### Câu hỏi tự kiểm tra

1. Vì sao một UUID ngắn hoặc dài đều không phù hợp làm tag metric theo ID mỗi đơn?
2. Counter `module.events.published` khác gì với counter riêng cho `OrderPlaced`?
3. `ModulithEventMetricsCustomizer` dùng để tùy biến `Counter.Builder` hay dùng để tạo tracing span?
4. Tại sao thêm hai tag có ba và hai giá trị lại có thể tạo tới sáu series cho một metric?
5. Vì sao ngay cả một tag chỉ có 200 giá trị vẫn có thể gây áp lực khi kết hợp với nhiều dimensions khác?
6. Khi publish counter tăng nhưng listener thất bại, cần kiểm tra tín hiệu nào?
7. Nếu `MeterFilter.maximumAllowableTags` bắt đầu deny meter mới, dữ liệu trên dashboard có còn đầy đủ không?
8. Một request có `traceId` và một event có `eventId`: ID nào nên dùng làm metric tag, ID nào nên dùng để tra cứu chi tiết?
9. Customizer thêm nhãn cho individual event metric, nhưng bạn kiểm tra nhãn đó trên counter tổng và không thấy. Lý do có thể là gì?
10. Sau khi đổi tên event class, vì sao câu truy vấn Prometheus trước đó có thể không còn trả dữ liệu mới?

## 16. Tổng kết

Chọn tag có cardinality thấp là một phần quan trọng khi **tùy biến event metrics trong Spring Modulith**. API `ModulithEventMetricsCustomizer` cho phép thêm thông tin từ domain event vào các individual publication counters, nhưng phải chọn **những nhóm giá trị ít, hữu hạn và có ý nghĩa vận hành**. Module identifier, event type, channel và customer segment thường phù hợp hơn order ID, event ID, user ID hoặc exception message.

Hãy nhớ: **metric publication** trả lời “đã publish bao nhiêu lượt theo nhóm nào?”, còn **trace/log, event publication state và dữ liệu nghiệp vụ** giúp tìm nguyên nhân của từng trường hợp và kết quả ở consumer. Kiểm chứng tags qua Actuator, Prometheus và số meter thực tế sẽ giúp hệ thống quan sát được các tương tác mô-đun mà không tạo ra chi phí series ngoài kiểm soát.

## Tài liệu tham khảo

- [Spring Modulith — Production-ready Features, Observability Metrics và Event Metrics Customizer](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith API — ModulithEventMetricsCustomizer](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html).
- [Spring Modulith API — ModulithEventMetrics](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetrics.html).
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html).
- [Micrometer — High Cardinality Tags Detector](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html).
