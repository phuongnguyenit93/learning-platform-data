# Low cardinality và khả năng dùng trong metrics

Trong ứng dụng **Spring Boot** dùng **Spring Modulith**, ta muốn trả lời những câu hỏi như “module nào đang công bố nhiều event?”, “tỷ lệ xử lý lỗi của module `inventory` có tăng không?” và “bao nhiêu yêu cầu đi qua `orders`?”. Cách thường dùng là tạo **metrics** và thêm các **tags/labels** như `module.identifier=orders`, `event.type=OrderPlaced` hoặc `outcome=failed`. Nhưng nếu thêm `orderId` hay `traceId` vào tag, chỉ vài nghìn request cũng có thể tạo ra rất nhiều time series khác nhau.

Bài thuộc chương **Cardinality**, với chủ đề trực tiếp **Low cardinality và khả năng dùng trong metrics**. Trong phạm vi mô-đun học **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, bài nối thiết kế ranh giới application module với **module graph**, **Actuator**, **event metrics**, **tracing** và **context propagation**: biết metadata nào có thể dùng để tổng hợp metrics, metadata nào nên dành cho trace/log, và cách kiểm tra tính hợp lý của bộ nhãn khi ứng dụng chạy.

> Ví dụ sử dụng thuật ngữ Micrometer và Spring Modulith trong tài liệu chính thức của các dòng phiên bản hiện hành, đặc biệt Spring Modulith **2.2**. Tên metric được xuất sang Prometheus và tên dependency có thể khác theo phiên bản hoặc naming convention; cần kiểm tra output của ứng dụng thực tế.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **cardinality**, **low cardinality**, **high cardinality** và **time series** theo cách Prometheus/Micrometer sử dụng.
2. Ước lượng số chuỗi metrics từ số giá trị của từng tag và hiểu vì sao số tổ hợp nhãn là yếu tố quyết định.
3. Chọn đúng low-cardinality tags cho các **event publication metrics** của Spring Modulith.
4. Phân biệt `Observation.lowCardinalityKeyValue(...)` với `Observation.highCardinalityKeyValue(...)` và những gì được export sang metrics/tracing.
5. Viết mã Java dùng Micrometer Observation hoặc `MeterRegistry` với tags được kiểm soát.
6. Dùng Actuator, Prometheus và Micrometer detector để tìm dấu hiệu bùng nổ cardinality.
7. Thiết kế nhãn ổn định cho dashboard mà không biến dữ liệu định danh từng giao dịch thành metric labels.

## 2. Cardinality là gì?

**Cardinality của một nhãn** là số lượng **giá trị khác nhau** mà nhãn đó có thể nhận trong phạm vi thời gian, metric và dữ liệu đang xét.

Ví dụ:

| Tag / label | Các giá trị có thể gặp | Nhận xét |
| --- | --- | --- |
| `module.identifier` | `orders`, `payments`, `inventory`, `shipping` | Thường có tập giá trị nhỏ, được quản lý bằng cấu trúc module |
| `module.invocation-type` | `bean`, `event listener` | Tập giá trị hạn chế |
| `outcome` | `success`, `failed`, `cancelled` | Low cardinality nếu nghiệp vụ chuẩn hóa bằng enum |
| `deployment.environment` | `dev`, `staging`, `prod` | Thường hữu hạn |
| `http.method` | `GET`, `POST`, `PUT`, ... | Hữu hạn |
| `http.route` | `/orders/{id}`, `/orders` | Có thể hữu hạn nếu dùng **route template** |
| `order.id` | Một UUID mới cho mỗi đơn hàng | High cardinality |
| `trace.id` | Một giá trị gần như riêng cho mỗi trace | High cardinality |
| `user.email` | Có thể tăng theo số người dùng | High cardinality, đồng thời nhạy cảm |
| `http.target` / URL chứa ID thực | `/orders/1`, `/orders/2`, ... | Có thể high cardinality |
| `exception.message` | Thông điệp kèm dữ liệu cụ thể mỗi lỗi | Thường không phù hợp làm metric label |

**Low cardinality** không có ngưỡng tuyệt đối “dưới N giá trị” dùng chung cho mọi hệ thống. Bản chất là số giá trị **được giới hạn, tương đối nhỏ và dự đoán được**, phù hợp với ngân sách time series thực tế.

**High cardinality** là tập giá trị rất lớn, tăng theo người dùng/request hoặc không có giới hạn thực tế. Một nhãn có 500 giá trị có thể chấp nhận được trong một metric nhưng gây quá tải nếu đi kèm nhiều nhãn khác và histogram. Vì thế, việc gọi tag là “low” vẫn cần tính **tổng số tổ hợp**.

## 3. Tag combination mới là đơn vị tạo time series

Trong Prometheus, một **time series** được xác định bởi **tên metric và tập nhãn có giá trị cụ thể**. Mỗi tổ hợp giá trị nhãn khác nhau tạo thành chuỗi riêng.

Ví dụ hai bộ nhãn:

~~~text
module_events_published_total{module_identifier="orders",event_type="OrderPlaced"}
module_events_published_total{module_identifier="orders",event_type="OrderCancelled"}
~~~

Dù cùng tên metric, chúng là **hai time series** vì `event_type` khác nhau.

### 3.1. Quy tắc tính gần đúng

Nếu một metric có `k` tag độc lập, tag `i` có nhiều nhất `nᵢ` giá trị, thì số **tổ hợp tối đa trên một instance** có thể ước lượng:

\[
N_{\text{series}} \leq \prod_{i=1}^{k} n_i
\]

Đây là **cận trên lý thuyết**: không nhất thiết mọi tổ hợp đều xuất hiện trong ứng dụng. Một số module không phát mọi event; một số outcome chỉ gặp ở module nhất định. Nhưng khi thiết kế, cận trên giúp nhận diện rủi ro trước khi dữ liệu thật xuất hiện.

Ví dụ: ứng dụng có 6 module, 5 loại event, 3 outcome và 2 môi trường (giả định mọi tổ hợp đều có thể tồn tại):

\[
6 \times 5 \times 3 \times 2 = 180\text{ tổ hợp}
\]

Nếu thêm `order.id` với 100.000 giá trị khác nhau:

\[
180 \times 100\,000 = 18\,000\,000\text{ tổ hợp tiềm năng}
\]

Con số 18 triệu là **cận trên**, không phải số chuỗi ứng dụng chắc chắn tạo ra. Trong thực tế, một order ID có thể chỉ đi cùng một số nhãn cụ thể, nhưng chỉ riêng `order.id` đã có nguy cơ tạo hàng chục/hàng trăm nghìn chuỗi theo lưu lượng.

### 3.2. Mỗi nhãn “nhỏ” vẫn có thể nhân lên

Giả sử một `Timer` được gắn:

| Chiều đo | Số giá trị |
| --- | ---: |
| `module` | 8 |
| `operation` | 12 |
| `outcome` | 4 |
| `region` | 3 |
| `instance` | 10 |

Số bộ tag tối đa:

\[
8 \times 12 \times 4 \times 3 \times 10 = 11\,520
\]

**Cả năm nhãn đều có số giá trị tương đối nhỏ**, nhưng kết hợp vẫn có thể tạo 11.520 bộ tag. Nếu timer được xuất thành nhiều series phụ như `_count`, `_sum`, và các `_bucket` của histogram, số **time series thực tế ở backend** còn lớn hơn số bộ tag.

Đừng dùng công thức trên để khẳng định chính xác số series của mọi exporter: tổng còn phụ thuộc **số metric names**, histogram/SLO buckets, replicas, stale series, resource labels, relabeling, retention và các chiều do backend thêm vào.

### 3.3. Sơ đồ: từ một metric đến nhiều series

~~~mermaid
flowchart TD
    M["Metric: shop.order.created"]
    M --> A["module=orders<br/>channel=web<br/>outcome=success"]
    M --> B["module=orders<br/>channel=mobile<br/>outcome=success"]
    M --> C["module=orders<br/>channel=web<br/>outcome=failed"]
    M --> D["... các tổ hợp còn lại"]
    A --> P["Prometheus: mỗi tổ hợp<br/>là một time series"]
    B --> P
    C --> P
    D --> P
~~~

## 4. Tại sao metrics ưu tiên low-cardinality labels?

Metrics thường được thu thập liên tục trên **nhiều instance**, lưu qua **nhiều ngày/tháng** và dùng cho dashboard/cảnh báo. Số time series quá lớn gây rủi ro:

- **Bộ nhớ:** Micrometer giữ meter cho mỗi ID gồm tên và tags; một số registry/backend phải duy trì thêm cấu trúc nội bộ cho mỗi series.
- **Lưu trữ:** mỗi series có nhiều samples theo thời gian; nhiều series tạo ra nhiều chunks và index.
- **CPU/network:** scrape, ingest, compaction, remote write và truy vấn phải xử lý nhiều chuỗi hơn.
- **Dashboard:** truy vấn phân nhóm quá rộng trở nên chậm, kết quả có thể khó diễn giải.
- **Vận hành:** hệ thống có thể gặp giới hạn active series/ingestion hoặc bị từ chối dữ liệu mới.

Ví dụ, một counter `shop.payment.attempts{transaction_id="..."}` làm **mỗi giao dịch có một chuỗi riêng**. Nó không còn hữu ích để đọc “số thanh toán mỗi phút” mà còn làm hạ tầng metrics gánh lượng dữ liệu chi tiết vốn phù hợp hơn với **trace/log/database**.

**Nguyên tắc:** Trong metrics, labels nên biểu diễn **nhóm phân tích ổn định**, chẳng hạn module, operation, outcome, loại event hoặc kênh cố định. Không dùng labels để lưu lịch sử từng cá thể.

## 5. Hai API trong Micrometer: low và high cardinality

Micrometer Observation API tách hai nhóm key-value:

~~~java
Observation observation = Observation.createNotStarted(
        "shop.order.place", observationRegistry);

observation.lowCardinalityKeyValue("module", "orders");
observation.lowCardinalityKeyValue("channel", "web");
observation.highCardinalityKeyValue("operation.run.id", "run-12345");
~~~

### 5.1. Low-cardinality key-values

Với `DefaultMeterObservationHandler`, nhóm `lowCardinalityKeyValue(...)` được dùng làm **meter tags**. Nó thích hợp cho:

- `module=orders`: tên module trong tập cố định.
- `operation=place-order`: loại nghiệp vụ do code định nghĩa.
- `outcome=success/failed`: trạng thái trong enum nhỏ.
- `event_type=OrderPlaced`: tên loại domain event hữu hạn trong mã nguồn.

Nếu metric handler được cấu hình, observation có thể tạo timer/counter tương ứng. Không đồng nghĩa **mỗi observation sẽ tạo mọi loại metric**: meter nào được tạo phụ thuộc vòng đời và handler.

### 5.2. High-cardinality key-values

`highCardinalityKeyValue(...)` dành cho dữ liệu có nhiều giá trị, và **DefaultMeterObservationHandler không thêm chúng vào meter tags**. Tracing handler có thể ghi chúng thành span attributes khi tracer/exporter cho phép.

Tuy nhiên, **đừng mặc nhiên ghi dữ liệu nhạy cảm** vào tracing. Thay vì email, số điện thoại, token hay chi tiết đơn hàng, ưu tiên trace ID và log correlation phù hợp với chính sách dữ liệu.

### 5.3. `Observation.Context.put(...)` lại là chuyện khác

`Observation.Context` có thể giữ thông tin nội bộ cho handler:

~~~java
Observation.Context context = new Observation.Context()
        .put("reservation.stage", "inventory-check");
~~~

Một giá trị thêm bằng `put(...)` không tự trở thành meter tag hay span attribute. Muốn xuất dữ liệu, phải dùng key-value API, convention, filter hoặc handler phù hợp.

### 5.4. Không có “lá chắn” tự động cho MeterRegistry trực tiếp

Khi gọi trực tiếp:

~~~java
registry.counter(
        "shop.order.created",
        "order.id", orderId.toString()
).increment();
~~~

Micrometer có thể tạo **một meter mới cho mỗi order ID**. Việc Observation API phân biệt low/high **không tự ngăn code dùng `MeterRegistry` trực tiếp thêm high-cardinality tags**.

Do đó, lựa chọn tag trong code, conventions, customizers và registry filters vẫn là **trách nhiệm của người thiết kế instrumentation**.

## 6. Low-cardinality metadata có sẵn trong Spring Modulith

Spring Modulith cung cấp khả năng quan sát tương tác module và công bố domain event. Theo tài liệu **Production-ready Features**, hai nhóm event publication metric có sẵn là:

| Metric Micrometer | Mô tả | Low-cardinality keys được tài liệu hóa |
| --- | --- | --- |
| `module.events.published` | Counter tổng hợp event được publish | `module.event.type`, `module.identifier`, `module.name` |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter cho loại event cụ thể | `module.identifier`, `module.name` |

### 6.1. Vì sao `module.identifier` thường an toàn?

`module.identifier` nhận giá trị từ **số lượng application module hữu hạn** như `orders`, `catalog`, `payments`. Khi đội ngũ thêm/bớt một module, danh sách thay đổi có kiểm soát trong codebase.

Ví dụ có 12 module, các metric được phân nhóm theo từng module thường hợp lý hơn rất nhiều so với phân nhóm theo 5 triệu order IDs.

**Nhưng** nếu ứng dụng tạo tên module động theo tenant hoặc dùng một cơ chế module detection tùy chỉnh biến thể không giới hạn, cần kiểm tra thực tế; chữ “module” trong tên tag không tự biến nó thành low cardinality.

### 6.2. Tại sao `module.event.type` cũng thường phù hợp?

Loại event là một **type trong code**, chẳng hạn `OrderPlaced`, `OrderCancelled` hoặc `PaymentCompleted`. Số loại event thường hữu hạn. Nó cho phép dashboard:

- So sánh tốc độ phát `OrderPlaced` giữa các module.
- Phát hiện event type bất thường tăng đột ngột.
- Theo dõi lượng publication theo module và loại event.
- Đặt alert theo nhóm module/event type ổn định.

**Không nhầm event type với event ID**. `OrderPlaced` là một loại event; `OrderPlaced(orderId=...)` là một instance. Đưa ID của instance vào tag sẽ làm tăng cardinality theo số lần event được phát.

### 6.3. `module.name` có thể trùng mục đích với `module.identifier`

Spring Modulith công bố cả technical ID và tên hiển thị của module trong event metrics. Hai tag có thể tương quan gần như một-một, nên số tổ hợp thực tế thấp hơn cận trên nhân độc lập.

Vẫn cần lưu tâm: nếu nhóm vận hành thay đổi `displayName` thường xuyên, dashboard/alert dựa trên tag name có thể phân mảnh số liệu theo thời gian. Dùng **technical identifier ổn định** cho truy vấn, dùng display name khi cần trình bày.

### 6.4. Tag của module span khác tag của event metric

Spring Modulith cũng cung cấp **module entry span** với các thuộc tính như:

| Span attribute | Ý nghĩa |
| --- | --- |
| `module.identifier` | Module được đi vào |
| `module.name` | Tên hiển thị |
| `module.invocation-type` | `bean` hoặc `event listener` |
| `module.method` | Entry method được gọi |

Không được suy ra **mọi span attribute đều tự động thành metric label**. Ví dụ `module.method` xuất hiện trong tài liệu **span tags**; muốn dùng nó trong một metric riêng, phải đánh giá cardinality, convention và hành vi exporter thực tế. Một danh sách phương thức có vẻ hữu hạn, nhưng việc đưa nhiều method vào timer gắn thêm module/operation/outcome có thể tăng số series đáng kể.

## 7. Ví dụ Spring Modulith: custom metric tag từ event

Giả sử hệ thống bán hàng công bố `OrderPlaced` với kênh đặt hàng thuộc một enum cố định:

~~~java
// com/example/shop/orders/OrderChannel.java
package com.example.shop.orders;

public enum OrderChannel {
    WEB, MOBILE, PARTNER
}
~~~

~~~java
// com/example/shop/orders/OrderPlaced.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderPlaced(UUID orderId, OrderChannel channel) {}
~~~

**Cách thiết kế an toàn:** `channel` chỉ có ba giá trị `WEB/MOBILE/PARTNER`. Trong khi đó, `orderId` là UUID mới cho từng đơn hàng.

Spring Modulith cho phép custom tag của **metric theo loại event** bằng `ModulithEventMetricsCustomizer` (ví dụ dưới đây dành cho dòng Modulith có API đó):

~~~java
// com/example/shop/config/EventMetricsConfiguration.java
package com.example.shop.config;

import com.example.shop.orders.OrderPlaced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer modulithEventMetricsCustomizer() {
        return metrics -> metrics.customize(OrderPlaced.class, (event, builder) -> {
            builder.tags("order.channel", event.channel().name());
        });
    }
}
~~~

Đoạn code gắn một tag có tập giá trị nhỏ vào metric **theo từng loại `OrderPlaced`**. Nó **không** gắn `orderId`.

Với các customizer hoặc convention **được viết trong source code**, tài liệu Spring Modulith 2.2 yêu cầu đưa artifact `spring-modulith-observability-api` vào compile scope. Runtime instrumentation/Actuator có thể được cung cấp bằng `spring-modulith-starter-insight`:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    implementation 'org.springframework.modulith:spring-modulith-observability-api'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Chỉ cần nếu muốn Prometheus scrape metric.
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Đoạn ví dụ giả định dự án đã quản lý dependency versions bằng Spring Boot/Spring Modulith BOM tương thích. Không dùng tên artifact của một nhánh khác mà chưa đối chiếu tài liệu phiên bản ứng dụng.

### 7.1. Một customizer nguy hiểm

**Không viết:**

~~~java
// Sai ý tưởng: giá trị mới với mỗi event, bùng nổ time series.
builder.tags("order.id", event.orderId().toString());
~~~

Một event `OrderPlaced` có thể phát sinh cho hàng triệu đơn; dùng `order.id` làm tag biến metrics thành nơi lưu dữ liệu từng đơn và tốn tài nguyên rất lớn.

**Thay bằng:** tag `order.channel`, `outcome` theo enum, hoặc `module.identifier`. Khi cần tra đơn cụ thể, sử dụng structured logs/traces hoặc kho nghiệp vụ có phân quyền.

### 7.2. Nếu channel đến từ input không kiểm soát

Nếu `channel` là chuỗi bất kỳ do user gửi lên, **không dùng trực tiếp** làm tag. Chuẩn hóa sang các nhóm hữu hạn:

~~~java
static String metricChannel(String rawChannel) {
    if (rawChannel == null) {
        return "OTHER";
    }

    return switch (rawChannel.trim().toUpperCase(java.util.Locale.ROOT)) {
        case "WEB" -> "WEB";
        case "MOBILE" -> "MOBILE";
        case "PARTNER" -> "PARTNER";
        default -> "OTHER";
    };
}
~~~

Đây là ví dụ normalization. Danh sách enum cần phù hợp nghiệp vụ, nhưng nên có một nhãn `OTHER` cho giá trị chưa được nhận diện để chặn tập giá trị vô hạn.

## 8. Ví dụ Java: tạo metric tổng hợp bằng Observation API

Một service muốn đo thời gian xử lý và kết quả đặt hàng theo module/kênh.

~~~java
// com/example/shop/orders/OrderProcessingMetrics.java
package com.example.shop.orders;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.UUID;
import org.springframework.stereotype.Component;

@Component
public class OrderProcessingMetrics {

    private final ObservationRegistry registry;

    public OrderProcessingMetrics(ObservationRegistry registry) {
        this.registry = registry;
    }

    public void record(UUID orderId, OrderChannel channel, Runnable action) {
        Observation observation = Observation.createNotStarted(
                "shop.orders.processing", registry);

        observation.lowCardinalityKeyValue("module", "orders");
        observation.lowCardinalityKeyValue("order.channel", channel.name());

        // High-cardinality: minh họa kỹ thuật, không đưa lên metric labels.
        observation.highCardinalityKeyValue(
                "order.id", orderId.toString());

        observation.observe(() -> {
            try {
                action.run();
                observation.lowCardinalityKeyValue("outcome", "success");
            } catch (RuntimeException ex) {
                observation.lowCardinalityKeyValue("outcome", "failed");
                throw ex; // observe(...) ghi nhận lỗi và stop theo lifecycle.
            }
        });
    }
}
~~~

**Cách dùng ý tưởng:**

~~~java
metrics.record(orderId, channel, () -> orderService.placeOrder(orderId));
~~~

Nếu ứng dụng có metrics observation handler phù hợp, một observation kiểu này có thể tạo **Timer** tên `shop.orders.processing` với các low-cardinality tags `module`, `order.channel`, `outcome`. `order.id` được gắn dưới dạng high-cardinality key-value và **không trở thành meter tag** trong `DefaultMeterObservationHandler`.

Trong ví dụ, `outcome` được thêm trong thân hàm trước khi observation stop nên **Timer được ghi ở thời điểm stop** có thể thấy tag. Một số handler chạy lúc start (ví dụ long-task timer nếu cấu hình) có thể không nhận được tag này vì nó chưa tồn tại khi operation bắt đầu. Khi cần tagging nhất quán ngay từ start, hãy thiết kế context/convention cho phù hợp.

**Lưu ý về bảo mật:** `order.id` chỉ minh họa high cardinality. Trong ứng dụng thật, không nên tự động ghi ID khách hàng/đơn hàng vào spans nếu không có nhu cầu, chính sách truy cập và thời hạn lưu dữ liệu rõ ràng. Trace ID có thể đủ để liên hệ log.

### 8.1. Viết trực tiếp `Counter` cũng phải bảo vệ tags

Ví dụ đếm kết quả theo loại kênh:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

// Trong service đã inject MeterRegistry registry:
Counter.builder("shop.orders.completed")
        .tag("module", "orders")
        .tag("channel", channel.name())   // channel là enum hữu hạn.
        .tag("outcome", outcome)          // outcome phải là enum/giá trị chuẩn hóa.
        .register(registry)
        .increment();
~~~

`Counter` có ý nghĩa “một lần hoàn tất hoạt động được đếm theo quy tắc ứng dụng”. Nó không phải metric publication mặc định của Spring Modulith, cũng không chứng minh một domain event listener đã xử lý xong.

### 8.2. Vì sao một nhãn low cardinality chưa đủ?

Giả sử `module` có 8 giá trị nhưng `outcome` là chuỗi lỗi thô:

~~~text
outcome="Payment gateway timeout order 101"
outcome="Payment gateway timeout order 102"
...
~~~

Tổ hợp nhãn vẫn bùng nổ do `outcome`. Cần chuẩn hóa lỗi:

~~~text
outcome="success"
outcome="validation_failed"
outcome="timeout"
outcome="dependency_unavailable"
outcome="other"
~~~

Để điều tra exception cụ thể, giữ thông tin trong tracing/logs phù hợp, không biến message thành tag.

## 9. Bật metrics và quan sát tags trên Spring Boot Actuator

Ví dụ cấu hình `application.yml` cho lab có Actuator và Prometheus:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,prometheus,modulith"
~~~

Sau khi ứng dụng chạy, publish một số `OrderPlaced` và thực thi đoạn code tạo meter:

~~~bash
# Liệt kê tên metrics mà ứng dụng đã đăng ký.
curl -fsS http://localhost:8080/actuator/metrics

# Xem metric gốc của Spring Modulith.
curl -fsS http://localhost:8080/actuator/metrics/module.events.published

# Xem một meter tự tạo khi code đã chạy.
curl -fsS http://localhost:8080/actuator/metrics/shop.orders.processing

# Xem output scrape; tên tag có thể được chuẩn hóa.
curl -fsS http://localhost:8080/actuator/prometheus | grep "module_events_published"
~~~

Các endpoint cần **dependency tương ứng, web exposure và quyền truy cập**. `/actuator/metrics` có thể dùng để khám phá metric ngay trên ứng dụng; `/actuator/prometheus` cần Prometheus registry. `/actuator/modulith` cho biết **kiến trúc module**, không phải metric samples.

### 9.1. Cách đọc output của `/actuator/metrics`

Một response chẩn đoán **minh họa** cho metric là:

~~~json
{
  "name": "shop.orders.processing",
  "description": null,
  "baseUnit": "seconds",
  "measurements": [
    { "statistic": "COUNT", "value": 24.0 },
    { "statistic": "TOTAL_TIME", "value": 1.87 },
    { "statistic": "MAX", "value": 0.18 }
  ],
  "availableTags": [
    { "tag": "module", "values": ["orders"] },
    { "tag": "order.channel", "values": ["WEB", "MOBILE", "PARTNER"] },
    { "tag": "outcome", "values": ["success", "failed"] }
  ]
}
~~~

Cấu trúc ở trên chỉ mô tả **một ví dụ đầu ra** và không hứa giá trị hoặc thống kê MAX luôn xuất hiện trong mọi phiên bản/registry. Khi kiểm tra thật, hãy xem `availableTags` có đúng những nhóm hữu hạn và **không có `order.id`**.

Có thể lọc giá trị tag khi truy vấn Actuator:

~~~bash
# Ví dụ: lọc các samples có module=orders.
curl -fsS "http://localhost:8080/actuator/metrics/shop.orders.processing?tag=module:orders"
~~~

Điều kiện lọc truy vấn Actuator khác với cơ chế tạo tag: nó chỉ chọn những time series đã được instrument và đăng ký, không làm giảm cardinality của chúng.

### 9.2. Prometheus sử dụng low-cardinality labels ra sao?

Trong Prometheus, mỗi tổ hợp labels tạo một time series. Dashboard nên tổng hợp theo chiều hữu hạn.

Ví dụ PromQL **minh họa** (tên exporter thực tế cần xác minh từ `/actuator/prometheus`):

~~~promql
# Tổng số event publications tăng trong 5 phút, phân theo module.
sum by (module_identifier) (
  increase(module_events_published_total[5m])
)
~~~

~~~promql
# Tốc độ event publications theo loại event trong 5 phút.
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

Tên nhãn có thể đổi dấu chấm thành dấu gạch dưới theo naming convention của exporter. Nếu metric đã được hiển thị bằng tên khác, hãy chỉnh truy vấn theo output thực tế.

**Không dùng `sum by (order_id)`**, kể cả khi truy vấn cho kết quả, vì điều đó thường cho thấy đã thiết kế một nhãn không phù hợp ngay từ instrumentation.

## 10. Quan sát và kiểm soát cardinality

### 10.1. Kiểm tra ngay ở nguồn

Khi thêm metric hoặc tag mới:

1. Liệt kê metric names qua `/actuator/metrics`.
2. Với metric cần quan sát, kiểm tra `availableTags` và số giá trị thực tế.
3. So sánh giá trị với danh sách **cho phép** trong thiết kế: modules, event types, outcomes, channels.
4. Truy vấn output `/actuator/prometheus` để xem name/labels sau chuẩn hóa.
5. Tính ngân sách series khi nhân thêm environments, replicas và histogram buckets.
6. Theo dõi mức tăng số meter sau khi phát đủ loại events và xử lý nhiều request có ID khác nhau.

Một lỗi điển hình: ở môi trường test chỉ có một order nên tag `order.id` nhìn như chỉ có một giá trị. Khi production có hàng nghìn đơn, nó phát triển không giới hạn. Vì vậy phải **đánh giá bản chất của field**, không chỉ đếm số giá trị trong một test nhỏ.

### 10.2. Micrometer HighCardinalityTagsDetector

Micrometer cung cấp **`HighCardinalityTagsDetector`** để phát hiện tình huống có quá nhiều meters cùng một tên. API được tài liệu hiện hành mô tả:

~~~java
// Registry đã được Spring Boot tự cấu hình.
registry.config().withHighCardinalityTagsDetector();
~~~

Detector có thể được cấu hình ngưỡng, chu kỳ kiểm tra và consumer nhận cảnh báo tùy phiên bản. Nó giúp chỉ ra các metric names có số meter tăng bất thường.

**Giới hạn:** detector đếm meters cùng tên và phát hiện **nghi ngờ** high cardinality; nó không thể phát hiện mọi trường hợp, chẳng hạn code nhúng UUID vào **tên metric** thay vì tags. Nó cũng không thay thế review nhãn, kiểm thử hay giới hạn ở backend.

Khi triển khai, kiểm tra API của phiên bản Micrometer đang dùng và quản lý vòng đời detector theo hướng dẫn. Không tạo một detector mới cho mỗi request.

### 10.3. Bảo vệ bằng MeterFilter

Nếu một thư viện ngoài đang sinh tag `uri` có quá nhiều giá trị mà chưa thể sửa ngay, Micrometer cung cấp `MeterFilter.maximumAllowableTags(...)`:

~~~java
import io.micrometer.core.instrument.config.MeterFilter;

// Ví dụ giới hạn registrations cho tag "uri" trên metric prefix chỉ định.
registry.config().meterFilter(
        MeterFilter.maximumAllowableTags(
                "http.client.requests", "uri", 100, MeterFilter.deny()
        )
);
~~~

Đây là **hàng rào giới hạn khi đăng ký thêm meter**, không phải phương pháp làm giá trị `uri` tự động hữu hạn. Khi vượt ngưỡng, meter mới có thể bị deny nên có rủi ro **thiếu dữ liệu quan sát**. Cần theo dõi cảnh báo và sửa nguồn phát sinh tag như dùng route template, phân nhóm URI, hoặc loại bỏ nhãn không cần thiết.

**Ưu tiên sửa thiết kế label tại nguồn**, sau đó mới dùng filter/limit như biện pháp phòng vệ.

### 10.4. Không để dữ liệu tùy ý chui vào metric name

Sai:

~~~java
registry.counter("shop.orders." + orderId + ".created").increment();
~~~

Đây là high cardinality **ở tên meter** thay vì ở tag. Đổi thành:

~~~java
registry.counter("shop.orders.created", "module", "orders").increment();
~~~

Tên metric ổn định giúp nhận diện và tổng hợp dữ liệu. Nếu cần phân biệt kênh hoặc outcome, thêm tags có tập giá trị nhỏ. Đừng sửa bằng cách chuyển `orderId` từ metric name sang tag, vì cardinality vẫn cao.

## 11. Liên hệ với tracing và context propagation

**Metrics** và **tracing** đều có thể được tạo từ Micrometer Observation nhưng phục vụ câu hỏi khác nhau:

| Dữ liệu | Mục tiêu | Chiều dữ liệu phù hợp |
| --- | --- | --- |
| **Event publication metric** | Đếm event theo module và event type | `module.identifier`, `module.event.type` |
| **Timer/counter nghiệp vụ tự tạo** | Đo tần suất, duration, outcomes | `module`, `operation`, `outcome`, `channel` hữu hạn |
| **Module entry span** | Xem một lần đi vào ranh giới module | `module.identifier`, `module.invocation-type`, `module.method`, duration/error |
| **Trace context** | Nối các spans thành trace xuyên thread/service | `traceId`, `spanId`, parent context |
| **Logs / Event Publication Registry** | Điều tra một publication, retry và completion cụ thể | Định danh sự kiện/trạng thái theo quy tắc dữ liệu và phân quyền |

`traceId` có thể là khóa liên kết hữu ích trong logs/traces, nhưng **không nên là metric label**. Mỗi trace gần như có ID riêng; dùng `traceId` để nhóm series làm mất ưu thế của metrics.

Với listener `@ApplicationModuleListener` chạy bất đồng bộ, context propagation quyết định quan hệ trace giữa publisher và listener. Nó **không làm `module.identifier` thành high cardinality**, cũng không biến một metric counter thành trace. Nếu listener bị tách trace, event publication metric vẫn có thể tăng; phải điều tra executor/context propagation riêng.

### 11.1. Không suy trạng thái xử lý event từ publication metric

Counter `module.events.published` đếm publication được instrument ở phía phát event, **không bảo đảm listener đã xử lý thành công**. Nếu yêu cầu đếm attempts/failures/completion, cần custom metrics được định nghĩa rõ hoặc dữ liệu từ Event Publication Registry và logs.

Khi tự tạo các processing metrics, có thể dùng `listener` (tên cố định), `outcome` (enum hữu hạn) và `module`. **Không đưa publication ID hoặc retry attempt ID** vào metric labels.

## 12. Các thiết kế thường gặp: tốt và không tốt

| Nhu cầu | Tag nên dùng | Tag cần tránh |
| --- | --- | --- |
| Số event công bố theo module | `module.identifier` | `event.instance.id` |
| Số event theo loại | `module.event.type` | Nội dung `event.payload` |
| Theo dõi thành công/thất bại listener | `listener=inventory.order-placed`, `outcome=success/failed` | `order.id`, exception message chứa ID |
| Phân tích thời gian request theo endpoint | `http.route=/orders/{id}`, `method=POST` | `url=/orders/123456` |
| So sánh môi trường vận hành | `environment=dev/staging/prod` | Tên build/job tùy ý chứa timestamp liên tục |
| Đánh giá số lần gọi theo kênh | `channel=WEB/MOBILE/PARTNER` | Input tự do của khách hàng |
| Điều tra một request riêng lẻ | Trace ID trong tracing/log correlation | `traceId` làm metric label |
| Đối chiếu dependency kiến trúc | Module graph/Actuator | Suy từ một metric có tag module là đầy đủ graph |

### 12.1. Khi một nhãn có vẻ hữu hạn nhưng vẫn rủi ro

- **`tenant`:** 10 tenant hôm nay không bảo đảm còn 10 tenant năm sau; nếu doanh nghiệp mở rộng hàng chục nghìn tenant, nhãn trở nên high cardinality.
- **`error.code`:** nếu là enum nhỏ thì tốt; nếu ghép mã lỗi, resource ID và timestamp thì rất rủi ro.
- **`http.route`:** route template thường tốt; dùng URL thực tế sau path variable lại không tốt.
- **`module.method`:** số method hữu hạn trong một phiên bản code nhưng có thể lớn hơn số module nhiều lần; phải xét cùng các tag khác và chi phí histogram.
- **`module.name`:** nếu phụ thuộc vào tên hiển thị thay đổi thường xuyên sẽ phân mảnh dữ liệu theo deployment.
- **`exception.type`:** có thể chấp nhận cho một metric ít chiều, nhưng danh sách exception class từ thư viện có thể rộng; nên gom thành nhóm lỗi nghiệp vụ/kỹ thuật nếu mục tiêu chỉ là alert.

## 13. Bài tập thực hành

### Bài 1 — Phân loại tags

Đánh dấu những giá trị sau phù hợp làm low-cardinality metric labels trong một ứng dụng Spring Modulith điển hình:

~~~text
module.identifier = orders
module.event.type = OrderPlaced
module.invocation-type = bean
order.id = 9a3e... (UUID)
outcome = success
trace.id = 8f4b...
http.route = /orders/{id}
http.url = /orders/123456
payment.gateway = STRIPE
customer.email = customer@example.com
~~~

**Gợi ý:** Module ID, event type, invocation type, outcome, route template và một enum gateway ổn định thường có thể là low cardinality. Order ID, trace ID, URL thực chứa ID và email không phù hợp cho metric labels. Ngoài cardinality, email còn có vấn đề bảo mật.

### Bài 2 — Tính cận trên

Một service có 10 module, 7 event types, 4 outcomes và 3 regions. Ước lượng tối đa bao nhiêu tổ hợp nhãn nếu tất cả giá trị độc lập? Nếu bổ sung `orderId` với 200.000 giá trị, cận trên mới là bao nhiêu?

**Đáp án định hướng:**

\[
10 \times 7 \times 4 \times 3 = 840
\]

\[
840 \times 200\,000 = 168\,000\,000
\]

Đây là **cận trên lý thuyết**, không phải dự báo số series chắc chắn có. Thảo luận vì sao cần xem cả số instances và số metric families.

### Bài 3 — Tìm lỗi tag trong customizer

Xét hai cách custom metric cho `OrderPlaced`:

~~~java
// A
builder.tags("channel", event.channel().name());

// B
builder.tags("orderId", event.orderId().toString());
~~~

Chọn cách dùng phù hợp cho metrics; giải thích khác biệt về số lượng giá trị. Nếu bắt buộc cần truy vấn theo order ID, đề xuất dùng trace/log hoặc kho nghiệp vụ như thế nào.

### Bài 4 — Quan sát trên Actuator

Khởi động ứng dụng lab có Spring Modulith observability và Prometheus registry, phát vài `OrderPlaced` qua nhiều kênh:

1. Gọi `/actuator/metrics/module.events.published` và xác nhận bộ nhãn module/event type.
2. Tìm metric theo từng event type; kiểm tra tag `order.channel` chỉ có giá trị hữu hạn nếu đã thêm customizer.
3. Đọc `/actuator/prometheus` để tìm tên metric/labels thực tế đã chuẩn hóa.
4. Xác nhận không có `order.id` hoặc `trace.id` trong danh sách tags.
5. Dùng `rate(...)` hoặc `increase(...)` theo nhãn module/kênh nếu backend Prometheus đang lưu dữ liệu.

### Bài 5 — Quyết định có nên dùng histogram

Một timer có 500 bộ tag và histogram được cấu hình 15 bucket hữu hạn. Hãy tính gần đúng ít nhất số chuỗi `_bucket` cho mỗi bộ tag (nếu exporter có `+Inf` bucket, số bucket thực tế có thể lớn hơn) và thêm `_sum`, `_count`. Vì sao việc thêm histogram làm cardinality metrics tăng dù **các tag không đổi**?

**Gợi ý:** Cần phân biệt số bộ tag, số meter trong JVM và số time series sau khi exporter mở rộng histogram thành nhiều metric con.

### Bài 6 — Thiết kế cảnh báo

Nhóm vận hành muốn cảnh báo khi `inventory` xử lý event thất bại tăng. Hãy thiết kế metric có tên ổn định và tags như `module=inventory`, `listener=on-order-placed`, `outcome=success/failed`. Giải thích vì sao không đưa `orderId`/`publicationId` vào tags, và nhắc rằng metric xử lý riêng cần instrumentation/registry phù hợp.

### Bài 7 — Kiểm tra detector và filters

Tạo lab có `MeterRegistry`, đăng ký 15 counters cùng tên nhưng khác `uid` (giá trị 1..15), dùng `HighCardinalityTagsDetector` theo JavaDoc để nhận biết việc sinh nhiều meters. Sau đó thay `uid` bằng `role=admin/user` và quan sát số meter giảm. Giải thích vì sao đây là kiểm chứng cardinality, không phải kiểm thử nghiệp vụ.

## 14. Câu hỏi ôn tập

1. Low cardinality được đánh giá theo bản chất của tập giá trị hay chỉ theo tên tag?
2. Vì sao mỗi tổ hợp labels trên một metric tạo một time series riêng?
3. Công thức cận trên gần đúng số tổ hợp nhãn là gì?
4. Vì sao thêm một tag có 10 giá trị vào một metric đã có 100 tổ hợp có thể làm số tổ hợp tối đa tăng gấp 10?
5. Vì sao `orderId` và `traceId` thường không được dùng làm metric labels?
6. `Observation.lowCardinalityKeyValue` khác `highCardinalityKeyValue` về xử lý metrics?
7. `Observation.Context.put(...)` có tự tạo meter tag không?
8. `MeterRegistry.counter(...)` có tự phân loại high/low để bảo vệ ứng dụng không?
9. Ba low-cardinality keys của `module.events.published` trong Spring Modulith là gì?
10. Tại sao `module.events.published` không trả lời câu hỏi listener đã xử lý thành công?
11. Tag `module.method` trên span có tự động hiện ở mọi metric không?
12. Vì sao histogram làm tăng số series dù cardinality của tags không đổi?
13. `HighCardinalityTagsDetector` phát hiện điều gì, và giới hạn quan trọng của nó là gì?
14. Vì sao dùng `MeterFilter.maximumAllowableTags(...)` chỉ là tuyến phòng vệ cuối?
15. Khi một tag chứa input người dùng, cần làm gì trước khi đưa vào metric?

## 15. Ghi nhớ

**Low cardinality là tập giá trị nhãn nhỏ, hữu hạn và được kiểm soát**, giúp metrics có thể tổng hợp theo nhóm thay vì tạo time series theo từng request hoặc từng người dùng. Ngay cả nhiều tags low cardinality vẫn có thể sinh rất nhiều tổ hợp; hãy tính ngân sách theo **metric name × label combinations × exported series × instances**.

Trong Spring Modulith, các metadata như **`module.identifier`**, **`module.name`** và **`module.event.type`** là ví dụ low-cardinality keys được tài liệu hóa cho event publication metrics. Dùng chúng để xem xu hướng công bố event theo module/type. Các ID như **order ID, trace ID, user ID** nên được xử lý bằng tracing/logs/cơ sở dữ liệu phù hợp thay vì metric tags.

**Micrometer Observation API** tách rõ `lowCardinalityKeyValue(...)` dành cho meter tags và `highCardinalityKeyValue(...)` cho thông tin chi tiết hơn phục vụ tracing. Tuy nhiên, khi dùng `MeterRegistry` trực tiếp hoặc customizer, bạn vẫn phải tự bảo đảm tags hữu hạn. Cuối cùng, dùng Actuator, Prometheus và detector/filter để kiểm tra thiết kế nhãn trên ứng dụng thật.

### Tài liệu tham khảo chính thức

- [Spring Modulith 2.2 — Production-ready Features: Observability Metrics và Low Cardinality Keys](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith JavaDoc — ModulithMetrics.LowKeys](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithMetrics.LowKeys.html).
- [Micrometer — Observation Components: DefaultMeterObservationHandler và key-values](https://docs.micrometer.io/micrometer/reference/observation/components.html).
- [Micrometer — Observation Introduction: low/high cardinality](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).
- [Micrometer — High Cardinality Tags Detector và giới hạn MeterFilter](https://docs.micrometer.io/micrometer/reference/concepts/high-cardinality-tags-detector.html).
- [Prometheus — Metric and Label Naming: label combinations và time series](https://prometheus.io/docs/practices/naming/).
- [Spring Boot — Metrics và Prometheus registry](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
