# Panel chênh lệch giữa event publish và event handling

## 1. Mục tiêu: nhìn thấy event đang đi đến đâu

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, module **order** có thể công bố sự kiện `OrderPlaced`; module **inventory** giữ hàng, module **payment** xử lý thanh toán và module **notification** gửi thông báo. Một event được publish thành công chưa chứng minh các listener đã xử lý xong. Khi listener chậm, lỗi hoặc bị gián đoạn, số event đã phát và số lượt xử lý hoàn tất sẽ lệch nhau.

Bài thuộc chương **Dashboard** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module học này dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot thông qua module graph, Actuator, event metrics, tracing và context propagation. Chủ đề trực tiếp ở đây là thiết kế **panel chênh lệch giữa event publish và event handling** để vận hành có thể phát hiện backlog, listener lỗi, xử lý chậm và xu hướng phục hồi.

Sau bài học, bạn có thể:

1. Phân biệt event publication, listener delivery, listener execution và xử lý hoàn tất.
2. Sử dụng counter publication có sẵn của Spring Modulith.
3. Khai thác Event Publication Registry để theo dõi trạng thái theo từng listener target.
4. Bổ sung metric `handled` có ngữ nghĩa rõ ràng khi dashboard cần so sánh tốc độ publish và xử lý.
5. Xây dựng panel Prometheus/Grafana cho publish rate, handling rate, pending, failed, oldest age và delivery gap.
6. Tránh đếm sai khi một event được nhiều module tiêu thụ, khi có retry hoặc khi dữ liệu registry được xóa sau completion.

**Điểm quan trọng:** Spring Modulith cung cấp metric publication tích hợp; không có sẵn một counter tổng quát tương ứng tên `module.events.handled`. Dashboard phải lấy trạng thái xử lý từ Event Publication Registry hoặc bổ sung metric do ứng dụng sở hữu. Không lấy tổng publish trừ tổng complete một cách trực tiếp khi chưa chuẩn hóa theo từng listener target.

## 2. Phân biệt các mốc trong vòng đời event

Một event đi qua nhiều mốc khác nhau:

1. **Published:** module nguồn phát event.
2. **Publication recorded:** registry ghi nhận một publication cho từng transactional listener mục tiêu.
3. **Processing:** listener nhận publication và bắt đầu thực thi.
4. **Completed:** listener kết thúc thành công theo ngữ nghĩa completion đã cấu hình.
5. **Failed:** listener ném exception hoặc publication bị đánh dấu stale là thất bại.
6. **Resubmitted:** publication thất bại được đưa trở lại hàng chờ xử lý.
7. **Abandoned:** publication thất bại được chính sách quyết định dừng retry.

~~~mermaid
stateDiagram-v2
    [*] --> PUBLISHED
    PUBLISHED --> PROCESSING
    PROCESSING --> COMPLETED
    PROCESSING --> FAILED
    FAILED --> RESUBMITTED
    RESUBMITTED --> PROCESSING
    FAILED --> ABANDONED
    COMPLETED --> [*]
    ABANDONED --> [*]
~~~

Các trạng thái `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED` và `RESUBMITTED` thuộc lifecycle Event Publication từ Spring Modulith 2.0; `ABANDONED` được bổ sung từ 2.2. Với phiên bản cũ hơn, registry chủ yếu biểu diễn publication đã hoàn tất hoặc còn incomplete; cần điều chỉnh panel theo API/version thực tế.

### Bốn con số không nên gộp

| Số liệu | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Events published** | Module nguồn đã phát bao nhiêu event? | 100 `OrderPlaced`. |
| **Target publications** | Có bao nhiêu lượt giao event đến listener mục tiêu? | 100 event × 2 listener = 200 publication-target. |
| **Listener completed** | Bao nhiêu publication-target đã hoàn tất? | 190 lượt listener hoàn tất. |
| **Pending/failed** | Bao nhiêu publication-target còn chờ hoặc thất bại? | 6 đang chờ, 2 đang chạy, 2 thất bại. |

Nếu một event được ba listener xử lý, một lần publish có thể tạo ba publication-target. Vì vậy, **200 target deliveries so với 100 events published không phải lỗi đếm**. Dashboard cần so sánh các con số cùng cấp: event với event, hoặc publication-target với publication-target.

## 3. Metric publication có sẵn của Spring Modulith

Khi bật observability của Spring Modulith, framework đăng ký hai dạng counter cho domain events:

| Metric logic | Ý nghĩa |
| --- | --- |
| `module.events.published` | Tổng số domain event được publish trong ứng dụng. |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter riêng cho event type, được đặt tên theo module identifier và simple event type name. |

Metric tổng có các low-cardinality keys:

| Tag | Ý nghĩa |
| --- | --- |
| `module.event.type` | Loại event được phát. |
| `module.identifier` | Identifier của module nguồn. |
| `module.name` | Tên hiển thị của module nguồn. |

Metric riêng cho event type có `module.identifier` và `module.name`; event type đã nằm trong tên meter. Có thể thêm tag nghiệp vụ hữu hạn vào metric riêng thông qua `ModulithEventMetricsCustomizer`.

Ví dụ bật các chức năng Actuator và observability bằng starter Insight:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Ứng dụng vẫn cần dependency exporter/registry phù hợp để đưa metrics đến Prometheus hoặc hệ thống giám sát khác. Nếu cần Event Publication Registry bền vững, thêm starter lưu publication theo công nghệ persistence đang dùng, ví dụ JDBC hoặc JPA; Insight không tự thay thế cấu hình persistence cho event publication log.

Có thể thêm tag có số lượng giá trị hữu hạn vào counter riêng của một event type bằng `ModulithEventMetricsCustomizer`:

~~~java
import com.example.shop.order.OrderPlaced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
                OrderPlaced.class,
                (event, builder) -> builder.tag("business.flow", "checkout"));
    }
}
~~~

Ví dụ dùng tag hằng để minh họa extension point. Nếu lấy giá trị từ event, chỉ chọn tập giá trị hữu hạn như channel hoặc outcome đã chuẩn hóa; không gắn order ID, user ID hay correlation ID vào metric.

### 3.1. Prometheus thường chuẩn hóa tên meter

Với Prometheus registry, dấu chấm trong tên Micrometer thường được đổi thành dấu gạch dưới và counter thường có hậu tố `_total`. Metric tổng vì thế thường xuất hiện như:

~~~text
module_events_published_total
~~~

Các tag có thể xuất hiện như:

~~~text
module_event_type
module_identifier
module_name
~~~

Tên cuối cùng phụ thuộc registry, exporter và phiên bản. Trước khi viết query, hãy mở `/actuator/prometheus` hoặc trang scrape của Prometheus để xác nhận **tên series và label thực tế**. Không đoán tên từ tên Java class.

### 3.2. Query publish rate

Ví dụ PromQL tổng hợp tốc độ publish theo module nguồn và event type:

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

Đây là số event publish trung bình mỗi giây trong cửa sổ 5 phút. Dùng `rate()` thay vì lấy chênh lệch raw counter giữa hai lần scrape; `rate()` xử lý counter reset do process restart tốt hơn.

Nếu dashboard chỉ quan tâm một event:

~~~promql
sum by (module_identifier) (
  rate(module_events_published_total{module_event_type="OrderPlaced"}[5m])
)
~~~

Label filter chỉ dùng được nếu series thực tế có label `module_event_type` và giá trị khớp. Nếu metric riêng theo event type được chọn, tên meter đã chứa module/type và query sẽ khác.

## 4. Event Publication Registry cho biết listener đã xử lý tới đâu

Spring Modulith cung cấp **Event Publication Registry** để ghi lại publication cho các transactional event listeners. Khi event được publish, registry xác định các listener mục tiêu và ghi một entry cho mỗi listener như một phần của transaction nghiệp vụ ban đầu. Khi listener chạy thành công, entry được đánh dấu hoàn tất; nếu listener thất bại, entry vẫn incomplete để có thể điều tra hoặc resubmit.

Mặc định, registry theo dõi các listener được annotate hoặc meta-annotate bằng `@TransactionalEventListener`. `@ApplicationModuleListener` là cách khai báo listener theo mô hình Spring Modulith và thuộc nhóm listener transactional này. Có thể thay đổi annotation kích hoạt registry bằng property `spring.modulith.events.registry-trigger-annotation`.

### 4.1. Publication-target là đơn vị thích hợp để đo delivery

Ví dụ:

~~~text
Order module publishes OrderPlaced #101
  -> inventory.onOrderPlaced
  -> notification.onOrderPlaced

Registry records:
  (OrderPlaced #101, inventory listener)
  (OrderPlaced #101, notification listener)
~~~

Một event tạo hai entry. Nếu inventory hoàn tất còn notification thất bại, dashboard nên cho thấy:

| Listener target | Publication count | Completed | Failed/incomplete |
| --- | ---: | ---: | ---: |
| `inventory` | 1 | 1 | 0 |
| `notification` | 1 | 0 | 1 |

Tổng events published vẫn là 1. Tổng publication-target là 2. Đây là lý do panel delivery gap phải group theo **event type + listener target**.

### 4.2. Những trạng thái nên hiển thị riêng

| Status | Cách hiểu khi vận hành | Panel gợi ý |
| --- | --- | --- |
| `PUBLISHED` | Đã ghi nhận, đang chờ hoặc sắp được xử lý. | Pending queue. |
| `PROCESSING` | Listener đã claim publication và đang chạy. | In-flight. |
| `COMPLETED` | Listener đã kết thúc thành công. | Successful handling. |
| `FAILED` | Listener ném lỗi hoặc publication được đánh dấu stale. | Failure backlog. |
| `RESUBMITTED` | Publication lỗi đã được đưa lại vào hàng xử lý. | Retry backlog. |
| `ABANDONED` | Chính sách dừng retry cho publication lỗi. | Terminal failures / cần can thiệp. |

Không cộng `FAILED` và `ABANDONED` vào `COMPLETED`. `RESUBMITTED` là trạng thái quay lại xử lý, không phải một event nghiệp vụ mới.

### 4.3. Registry không đại diện cho mọi kiểu listener

Registry ghi publication cho transactional listeners theo trigger annotation đã cấu hình. Một `@EventListener` thông thường, một consumer Kafka bên ngoài hoặc một tác vụ không tham gia registry có thể không tạo entry. Nếu dashboard cần đo các luồng đó, phải instrument riêng tại consumer/handler hoặc lấy số liệu từ broker.

**Không diễn giải “không có registry entry” thành “không có listener”.** Trước hết xác nhận listener thuộc tập mà registry theo dõi.

## 5. Định nghĩa dashboard trước khi viết query

Đặt ra quy ước metric trước để tất cả panel có thể đối chiếu cùng một ngữ nghĩa:

| Metric logic | Loại | Labels gợi ý | Ý nghĩa |
| --- | --- | --- | --- |
| `module.events.published` | Counter có sẵn | `module.identifier`, `module.event.type` | Event được module nguồn publish. |
| `application.event.deliveries` | Counter custom hoặc dữ liệu registry | `event.type`, `listener.module` | Publication-target được tạo. |
| `application.events.handled` | Counter custom | `event.type`, `listener.module` | Listener xử lý và commit thành công. |
| `application.event.publications` | Gauge custom | `status`, `event.type`, `listener.module` | Số publication hiện có theo trạng thái. |
| `application.event.oldest.pending.seconds` | Gauge custom | `event.type`, `listener.module` | Tuổi của publication pending lâu nhất. |
| `application.event.handling.duration` | Timer/Histogram | `event.type`, `listener.module` | Thời gian listener xử lý. |

Các tên `application.*` là **quy ước do ứng dụng xây dựng**, không phải metric mặc định của Spring Modulith. Nếu lấy số liệu trực tiếp từ Event Publication Registry, cần một read adapter hoặc scheduled collector để chuyển trạng thái thành gauge; không có sẵn một counter tổng quát `module.events.handled`.

### 5.1. Xác định “handled” có nghĩa là gì

Trước khi tạo metric, thống nhất một trong các mốc:

- **Started:** listener đã bắt đầu thực thi.
- **Returned successfully:** phương thức listener trả về không có exception.
- **Committed:** transaction xử lý listener đã commit.
- **Business effect completed:** tác dụng phụ nghiệp vụ đã được xác nhận, ví dụ thông báo đã được nhà cung cấp chấp nhận.

Các mốc này không tương đương. Ví dụ, listener có thể commit một notification request vào database nhưng email chưa được gửi. Metric `handled` nên mô tả chính xác mốc mà nhóm vận hành muốn giám sát.

Với `@ApplicationModuleListener`, một định nghĩa hữu ích là **listener transaction đã commit thành công**. Nếu dùng custom counter, tăng counter sau commit để tránh đếm thành công cho transaction sau đó rollback.

## 6. Tạo counter handling sau commit

Ví dụ dưới đây tạo counter theo event type và listener module. Counter được tăng trong callback `afterCommit`, khi transaction của listener đã commit:

~~~java
package com.example.shop.observability;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Component
public class EventHandlingMetrics {

    private final MeterRegistry registry;

    public EventHandlingMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public void recordAfterCommit(Class<?> eventType, String listenerModule) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()
                || !TransactionSynchronizationManager.isSynchronizationActive()) {
            throw new IllegalStateException(
                    "Handling metric requires an active synchronized transaction");
        }

        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void afterCommit() {
                        Counter.builder("application.events.handled")
                                .description("Listener transactions committed successfully")
                                .tag("event.type", eventType.getSimpleName())
                                .tag("listener.module", listenerModule)
                                .register(registry)
                                .increment();
                    }
                });
    }
}
~~~

Dùng helper trong listener:

~~~java
package com.example.shop.notification;

import com.example.shop.observability.EventHandlingMetrics;
import com.example.shop.order.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPlacedListener {

    private final EventHandlingMetrics metrics;

    OrderPlacedListener(EventHandlingMetrics metrics) {
        this.metrics = metrics;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        createNotificationRequest(event.orderId());
        metrics.recordAfterCommit(OrderPlaced.class, "notification");
    }

    private void createNotificationRequest(String orderId) {
        // Lưu notification request trong transaction của listener.
    }
}
~~~

`@ApplicationModuleListener` cung cấp mô hình listener bất đồng bộ và transactional của Spring Modulith. Callback chỉ tăng counter khi transaction commit. Nếu handler ném exception hoặc transaction rollback, callback `afterCommit` không chạy.

### Giới hạn của counter custom

- Counter Micrometer trong process là telemetry, không phải sổ cái bền vững. Restart có thể reset số liệu.
- Nếu process dừng ngay sau commit nhưng trước callback cập nhật registry, counter có thể thiếu một lần tăng.
- Nếu listener có nhiều side effect bên ngoài transaction (gửi email, gọi HTTP), commit database không chứng minh side effect đó đã hoàn tất.
- Counter này đo số lần listener transaction commit; nếu chính sách retry hoặc completion mode cho phép cùng publication được thực thi lại sau một commit, nó có thể đếm nhiều lần cho một publication. Dùng trạng thái registry nếu cần số publication-target duy nhất đã hoàn tất.
- Với consumer không có transaction, định nghĩa `handled` là “method returned successfully” và ghi rõ trong tên/description.

Do đó, **Event Publication Registry vẫn là nguồn trạng thái bền vững cho publication-target** khi được cấu hình persistence. Counter custom dùng để vẽ tốc độ và xu hướng; không thay thế registry hoặc dữ liệu nghiệp vụ.

## 7. Tạo gauge cho backlog từ Event Publication Registry

Một panel backlog cần biết hiện tại có bao nhiêu publication đang `PUBLISHED`, `PROCESSING`, `FAILED`, `RESUBMITTED` hoặc `ABANDONED`.

Spring Modulith cung cấp API `EventPublicationRegistry.findIncompletePublications()` để đọc publication chưa hoàn tất. Các publication có status và thông tin target. Có thể xây dựng một adapter đọc dữ liệu này và cập nhật gauge theo nhóm:

~~~text
application_event_publications{
  status="PUBLISHED",
  event_type="OrderPlaced",
  listener_module="notification"
} 12

application_event_publications{
  status="PROCESSING",
  event_type="OrderPlaced",
  listener_module="notification"
} 3

application_event_publications{
  status="FAILED",
  event_type="OrderPlaced",
  listener_module="notification"
} 2
~~~

Đây là **series minh họa** cho adapter do ứng dụng xây dựng, không phải tên metric hoặc endpoint mặc định của Spring Modulith.

Với trạng thái `ABANDONED` (Spring Modulith 2.2+), hãy đọc qua API `AbandonedEventPublications` hoặc adapter persistence tương ứng; đừng mặc định rằng API incomplete bao gồm cả publication đã bị dừng retry. Giữ abandoned thành một panel riêng để operator quyết định có cần can thiệp thủ công hay không.

### 7.1. Cách đọc registry

Với volume nhỏ, có thể dùng API registry để lấy tập incomplete rồi group theo status, event type và target. Với hệ thống nhiều publication, tránh quét toàn bộ bảng/collection mỗi lần Prometheus scrape. Thay vào đó:

1. Dùng query aggregate theo status/target ở persistence layer, có index phù hợp.
2. Hoặc cập nhật một read model/bảng tổng hợp khi publication đổi trạng thái.
3. Hoặc chạy scheduled collector với chu kỳ có giới hạn, cache kết quả và đo thời gian truy vấn.

Schema persistence khác nhau giữa JDBC, JPA, MongoDB và các store khác. Không giả định một câu SQL hoặc tên bảng áp dụng cho mọi implementation. Giữ logic đọc trạng thái trong adapter riêng để thay persistence mà không làm hỏng dashboard.

### 7.2. Đếm trạng thái thế nào?

| Nhóm hiển thị | Công thức |
| --- | --- |
| **Waiting** | Số `PUBLISHED` + `RESUBMITTED`. |
| **In flight** | Số `PROCESSING`. |
| **Failed** | Số `FAILED`. |
| **Abandoned** | Số `ABANDONED`. |
| **Outstanding** | Waiting + In flight + Failed, nếu chính sách vận hành vẫn theo dõi failed để retry. |

`ABANDONED` là trạng thái terminal theo chính sách; hiển thị riêng để operator quyết định can thiệp. Không gộp nó vào pending có thể retry.

## 8. Query PromQL cho các panel chính

Các query dưới đây giả định tên series/labels đã được xác nhận trên `/actuator/prometheus` và các metric custom đã được triển khai. Micrometer/Prometheus có thể chuẩn hóa dấu chấm thành dấu gạch dưới.

### Panel A — Publish rate theo event type

~~~promql
sum by (module_identifier, module_event_type) (
  rate(module_events_published_total[5m])
)
~~~

**Visualization:** Time series. Unit: events/second. Legend: `{{module_identifier}} / {{module_event_type}}`.

### Panel B — Handling success rate theo listener target

~~~promql
sum by (listener_module, event_type) (
  rate(application_events_handled_total[5m])
)
~~~

**Visualization:** Time series. Unit: successful listener transactions/second. Legend: `{{listener_module}} / {{event_type}}`.

### Panel C — Pending theo trạng thái

~~~promql
sum by (listener_module, event_type, status) (
  application_event_publications{
    status=~"PUBLISHED|RESUBMITTED|PROCESSING"
  }
)
~~~

**Visualization:** Stacked time series hoặc bar gauge. Tách `PROCESSING` khỏi waiting để biết listener đang bận hay queue đang tích lũy.

### Panel D — Failed và abandoned

~~~promql
sum by (listener_module, event_type, status) (
  application_event_publications{
    status=~"FAILED|ABANDONED"
  }
)
~~~

**Visualization:** Bar gauge hoặc table. Màu cảnh báo nên phân biệt failed có thể retry và abandoned cần can thiệp.

### Panel E — Handling duration

Nếu ứng dụng ghi histogram `application.event.handling.duration`:

~~~promql
histogram_quantile(
  0.95,
  sum by (le, listener_module, event_type) (
    rate(application_event_handling_duration_seconds_bucket[5m])
  )
)
~~~

**Visualization:** Time series. Unit: seconds. p95 tăng thường là tín hiệu sớm cho thấy backlog sẽ tăng nếu tốc độ publish không đổi.

### Panel F — Tỷ lệ listener lỗi

Nếu có counter attempts và success với cùng semantics:

~~~promql
sum by (listener_module, event_type) (
  rate(application_events_failed_total[5m])
)
/
clamp_min(
  sum by (listener_module, event_type) (
    rate(application_events_attempted_total[5m])
  ),
  1e-9
)
~~~

Đơn vị là tỷ lệ từ 0 đến 1; nhân 100 để hiển thị phần trăm. Không dùng `FAILED` gauge hiện tại chia cho publish rate vì một bên là số lượng tồn tại ở thời điểm scrape, bên kia là tốc độ theo thời gian.

## 9. Panel “delivery gap” nên tính thế nào?

Có hai cách hợp lệ, tùy nguồn dữ liệu.

### Cách 1 — Dùng backlog hiện tại theo registry

Với mỗi listener target, hiển thị:

~~~promql
sum by (listener_module, event_type) (
  application_event_publications{
    status=~"PUBLISHED|RESUBMITTED|PROCESSING|FAILED"
  }
)
~~~

Đây là số publication-target chưa hoàn tất tại thời điểm scrape. Có thể tạo một stat tổng và một time series theo listener module. Nếu operator chỉ muốn biết queue đang chờ, bỏ `FAILED` và hiển thị failed riêng.

**Ưu điểm:** phản ánh trạng thái hiện tại của registry, không cần suy luận từ chênh lệch hai counter. `PUBLISHED`, `PROCESSING` và `RESUBMITTED` cho thấy lượng công việc chưa xong; `FAILED` cho thấy phần cần retry hoặc xử lý thủ công.

### Cách 2 — Trừ hai counter cùng cấp và cùng semantics

Nếu ứng dụng có:

- `application_event_deliveries_total`: tăng một lần khi tạo publication-target.
- `application_events_handled_total`: tăng một lần sau khi target hoàn tất thành công.

Thì có thể xem tốc độ chênh lệch theo cùng `listener_module` và `event_type`:

~~~promql
sum by (listener_module, event_type) (
  rate(application_event_deliveries_total[5m])
)
-
sum by (listener_module, event_type) (
  rate(application_events_handled_total[5m])
)
~~~

Giá trị dương kéo dài nghĩa là delivery rate đang cao hơn completion rate trong cửa sổ đó. Giá trị âm có thể xuất hiện tạm thời khi listener xử lý backlog cũ nhanh hơn tốc độ publish mới.

**Không áp dụng công thức này cho `module.events.published_total - application.events.handled_total`** nếu một event có nhiều listener hoặc hai metric có định nghĩa khác nhau. Cần một counter delivery theo từng target, hoặc dùng backlog gauge từ registry.

## 10. Bố cục dashboard Grafana

~~~text
┌──────────────────────┬──────────────────────┬──────────────────────┐
│ Event publish rate   │ Handling success rate │ Outstanding delivery │
│ events/sec           │ listener tx/sec       │ count                 │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ Pending by status    │ Failed / abandoned    │ Oldest pending age    │
│ target + event type  │ target + event type   │ seconds               │
├──────────────────────┼──────────────────────┼──────────────────────┤
│ Handling duration    │ Failure ratio         │ Delivery gap rate     │
│ p50 / p95 / p99      │ percent               │ per target            │
├──────────────────────┴──────────────────────┴──────────────────────┤
│ Table: source module → event type → listener target → status       │
└────────────────────────────────────────────────────────────────────┘
~~~

### Biến lọc nên có

- `source_module`: module phát event.
- `event_type`: loại domain event.
- `listener_module`: module nhận event.
- `environment`: môi trường triển khai.
- `application`: service hoặc instance group.

Giữ label hữu hạn. Không tạo dashboard variable dựa trên `eventId`, `orderId`, `customerId` hoặc trace ID vì cardinality lớn và có thể chứa dữ liệu nhạy cảm.

### Table điều tra

Một bảng drill-down có thể gồm:

| Cột | Ý nghĩa |
| --- | --- |
| Source module | Module phát event. |
| Event type | Loại event. |
| Listener module | Module xử lý publication-target. |
| `PUBLISHED` | Số đang chờ. |
| `PROCESSING` | Số đang chạy. |
| `COMPLETED` | Số hoàn tất trong khoảng thời gian được chọn, nếu store còn giữ. |
| `FAILED` | Số lỗi. |
| `ABANDONED` | Số đã dừng retry. |
| Oldest age | Tuổi publication chưa hoàn tất lâu nhất. |
| p95 handling | Thời gian xử lý p95. |

Nếu completion mode là `DELETE`, completed entries bị xóa khỏi registry nên không thể dựng lịch sử completion bằng cách đếm bảng hiện tại. Dùng counter/time series hoặc archive riêng nếu dashboard cần lịch sử.

## 11. Cảnh báo khi backlog tăng

Alert cần gắn với mục tiêu vận hành, không chỉ một giá trị cố định. Các rule minh họa:

### Pending tồn tại quá lâu

~~~promql
application_event_oldest_pending_seconds{
  status=~"PUBLISHED|RESUBMITTED"
} > 300
~~~

Ví dụ cảnh báo khi publication chờ hơn 5 phút. Chọn ngưỡng theo SLA của event: email notification có thể chấp nhận độ trễ khác với reserve inventory hoặc payment workflow.

### Failed publication tăng

~~~promql
sum by (listener_module, event_type) (
  application_event_publications{status="FAILED"}
) > 0
~~~

Có thể dùng warning khi xuất hiện failure và critical khi số lượng/tuổi vượt ngưỡng. Nếu hệ thống có lỗi transient và retry tự động, thêm thời gian `for:` để tránh alert do một lỗi rất ngắn.

### Publish nhanh hơn handling trong thời gian kéo dài

~~~promql
(
  sum by (listener_module, event_type) (
    rate(application_event_deliveries_total[10m])
  )
-
  sum by (listener_module, event_type) (
    rate(application_events_handled_total[10m])
  )
) > 0
~~~

Kết hợp điều kiện outstanding backlog đang tăng để tránh báo động khi listener đang drain backlog cũ hoặc khi rate chỉ dao động ngắn.

### Alert cần đi kèm hành động

| Điều kiện | Hành động điều tra |
| --- | --- |
| Pending tăng, processing thấp | Kiểm tra scheduler, executor, listener registration và worker capacity. |
| Processing tăng, p95 tăng | Kiểm tra downstream dependency, lock, database và thread pool. |
| Failed tăng | Kiểm tra exception, payload, schema compatibility và retry policy. |
| Abandoned tăng | Xem AbandonPolicy, completion attempts và quy trình can thiệp thủ công. |
| Publish giảm đột ngột | Kiểm tra traffic nghiệp vụ và publisher; không kết luận listener lỗi. |
| Handling giảm nhưng publish ổn định | Kiểm tra consumer/listener, database và downstream. |

## 12. Đọc dashboard qua ví dụ

Giả sử trong 5 phút có:

| Event type | Published events | Listener targets/event | Target deliveries | Completed | Pending/failed |
| --- | ---: | ---: | ---: | ---: | ---: |
| `OrderPlaced` | 100 | 2 | 200 | 190 | 10 |
| `PaymentAuthorized` | 80 | 1 | 80 | 80 | 0 |
| `ShipmentRequested` | 50 | 1 | 50 | 35 | 15 |

Dashboard cho thấy:

- `OrderPlaced`: 10 target deliveries chưa hoàn tất. Drill-down có thể cho thấy 7 pending và 3 failed ở notification.
- `PaymentAuthorized`: publish và handling đang cân bằng.
- `ShipmentRequested`: 15 target deliveries chưa hoàn tất; cần kiểm tra listener logistics và downstream carrier API.

Nếu lấy 230 event publications trừ 305 listener completions, kết quả âm 75 có thể bị hiểu nhầm là không có backlog hoặc hệ thống đã xử lý “dư” 75 event. Thực tế có 25 target deliveries chưa hoàn tất; phần chênh lệch còn lại đến từ fan-out của `OrderPlaced`, được hai listener nhận. **Đơn vị so sánh quyết định kết luận của dashboard.**

## 13. Các yếu tố làm sai lệch chênh lệch

### 13.1. Fan-out và conditional listeners

Một event có thể có nhiều listener; số listener có thể thay đổi theo profile, điều kiện hoặc phiên bản triển khai. Không nhân tổng event publish với một hệ số fan-out cố định nếu tập listener không ổn định. Registry theo target là nguồn tốt hơn để biết publication nào thực sự được tạo.

### 13.2. Retry và resubmission

Resubmit một publication không tạo ra một event nghiệp vụ mới. Nếu custom counter `attempted` tăng mỗi lần listener chạy, nó sẽ đếm số lần thử; `deliveries` chỉ nên tăng khi publication-target được tạo lần đầu. Đặt tên metric theo đúng semantics để không trừ nhầm số lần thử với số publication.

### 13.3. Completion mode

Spring Modulith hỗ trợ các completion mode:

- `UPDATE`: cập nhật entry thành completed; đây là mặc định.
- `DELETE`: xóa entry khi hoàn tất; tiết kiệm dữ liệu lưu trữ nhưng mất khả năng tra cứu completed publications từ registry.
- `ARCHIVE`: chuyển entry hoàn tất sang archive store.

Nếu dashboard cần lịch sử completion, dùng `UPDATE` hoặc `ARCHIVE`, hoặc duy trì counter/warehouse riêng. `DELETE` phù hợp khi chỉ cần theo dõi incomplete publications và không cần tra cứu lịch sử completed trong registry.

### 13.4. Staleness và publication bị kẹt

Publication có thể nằm lâu ở `PUBLISHED`, `PROCESSING` hoặc `RESUBMITTED` nếu ứng dụng crash hoặc listener bị treo. Spring Modulith 2.0 cung cấp Staleness Monitor; monitor chỉ hoạt động khi cấu hình một hay nhiều duration staleness khác zero. Khi được bật, publication quá tuổi có thể được đánh dấu `FAILED`.

Dashboard nên có **oldest pending age** để phát hiện trạng thái kẹt trước khi operator nhìn thấy failure. Không mặc định cho rằng mọi publication lâu đều tự chuyển sang `FAILED`; kiểm tra cấu hình `spring.modulith.events.staleness`.

### 13.5. Restart và counter reset

Counter Micrometer thường reset khi process restart. Dùng `rate()`/`increase()` trên Prometheus thay vì so sánh giá trị counter raw. Với nhiều application instances, phải `sum` trên các instance và group theo label nghiệp vụ; tránh cộng gauge backlog của một registry được scrape nhiều lần nếu dữ liệu đó là bản sao của cùng một store.

## 14. Kiểm chứng dashboard bằng kịch bản thực tế

Không chỉ kiểm tra panel có dữ liệu. Hãy tạo các tình huống có kết quả mong đợi:

### Kịch bản A — Publish và xử lý thành công

1. Publish một `OrderPlaced`.
2. Xác nhận metric `module.events.published` tăng.
3. Xác nhận registry tạo publication-target cho listener.
4. Để listener hoàn tất.
5. Xác nhận status chuyển `COMPLETED` và custom handled counter tăng sau commit.
6. Kiểm tra backlog giảm về 0.

### Kịch bản B — Listener thất bại

1. Tạo event test mà listener chủ động ném exception.
2. Xác nhận publication-target ở trạng thái `FAILED` (với lifecycle hỗ trợ).
3. Xác nhận panel failed tăng, completed không tăng.
4. Kiểm tra log/trace có event type, listener module và error class.
5. Sửa nguyên nhân và resubmit theo quy trình đã định.

### Kịch bản C — Listener chậm

1. Thêm delay có kiểm soát trong listener test.
2. Xác nhận `PROCESSING` hoặc pending age tăng.
3. Kiểm tra p95 handling duration và outstanding count.
4. Kết thúc xử lý, xác nhận completed tăng và backlog giảm.

### Kịch bản D — Một event có nhiều listener

1. Đăng ký hai transactional listeners cho cùng event.
2. Publish một event.
3. Xác nhận một event publication counter tăng một đơn vị.
4. Xác nhận registry tạo hai publication-target.
5. Cho một listener thành công và listener còn lại thất bại.
6. Xác nhận dashboard hiển thị một completed và một failed target.

### Kịch bản E — Retry/resubmit

1. Resubmit một publication failed.
2. Xác nhận status chuyển `RESUBMITTED`, sau đó `PROCESSING`.
3. Xác nhận retry không làm tăng event publish counter như thể có event mới.
4. Khi listener thành công, xác nhận completed target tăng đúng một lần theo semantics đã chọn.

## 15. Truy vết từ panel xuống trace và log

Dashboard cho biết **ở đâu** có chênh lệch; trace và log giúp biết **vì sao**.

Khi phát hiện listener `notification` có p95 tăng:

1. Chọn event type và khoảng thời gian có backlog.
2. Tìm module entry spans của listener với `module.identifier`, `module.invocation-type` và `module.method`.
3. Mở trace để kiểm tra database span, HTTP client span hoặc downstream dependency.
4. Đối chiếu `traceId` trong structured logs và `eventId` trong publisher/consumer logs.
5. Nếu publication đã retry sau restart, trace ban đầu có thể không còn liên kết trực tiếp; dùng eventId và registry state để nối điều tra.

Không đưa `eventId`, `orderId`, `traceId` hoặc customer ID vào metric labels. Dùng chúng trong logs/traces để drill-down; metric labels chỉ nên chứa module, event type, listener target, outcome và environment có số lượng giá trị hữu hạn.

## 16. Checklist trước khi đưa dashboard vào production

- [ ] Đã xác nhận metric `module.events.published` và tags thực tế trên Prometheus scrape.
- [ ] Đã bật Spring Modulith observability phù hợp.
- [ ] Đã cấu hình Event Publication Registry và persistence nếu cần theo dõi transactional listener.
- [ ] Đã xác định tập listener được registry theo dõi.
- [ ] Đã định nghĩa rõ `handled` là started, returned, committed hay business effect completed.
- [ ] Nếu dùng custom handled counter, đã đồng bộ semantics với delivery target và retry.
- [ ] Dashboard group theo source module, event type và listener module.
- [ ] Không so raw event count với target delivery count khi có fan-out.
- [ ] Có panel pending, processing, failed, abandoned và oldest age.
- [ ] Có panel handling rate, duration và failure ratio.
- [ ] Đã quyết định completion mode `UPDATE`, `DELETE` hay `ARCHIVE` theo nhu cầu lịch sử.
- [ ] Đã kiểm tra staleness monitor và retry/resubmission policy.
- [ ] Không dùng eventId/orderId/traceId làm metric labels.
- [ ] Đã thử publish success, listener failure, slow listener, fan-out và retry.
- [ ] Alert có ngưỡng theo SLA và có runbook tương ứng.

## 17. Tài liệu tham khảo chính thức

- **Spring Modulith — Production-ready Features:** https://docs.spring.io/spring-modulith/reference/production-ready.html — `module.events.published`, event-specific counters, module spans và Insight starter.
- **Spring Modulith — Working with Application Events:** https://docs.spring.io/spring-modulith/reference/events.html — Event Publication Registry, target listeners, lifecycle states, resubmission, staleness và completion modes.
- **Spring Modulith — EventPublication API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventPublication.html — status, completion attempts, publication date và resubmission date.
- **Spring Modulith — EventPublicationRegistry API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html — lookup incomplete publications và API xử lý publication.
- **Micrometer — Counters:** https://docs.micrometer.io/micrometer/reference/concepts/counters.html — counter semantics và cách quan sát tốc độ bằng rate.
- **Prometheus — Query Functions:** https://prometheus.io/docs/prometheus/latest/querying/functions/ — `rate`, `increase`, `histogram_quantile` và xử lý counter.
- **Grafana — Prometheus Query Editor:** https://grafana.com/docs/grafana/latest/datasources/prometheus/query-editor/ — xây dựng query và panel từ Prometheus metrics.

## 18. Tổng kết

Panel chênh lệch giữa event publish và event handling phải so sánh đúng **đơn vị công việc**. Metric `module.events.published` cho biết event được phát; Event Publication Registry ghi nhận publication theo từng transactional listener target và theo dõi trạng thái xử lý. Vì một event có thể được nhiều listener nhận, tổng publish và tổng completed target không thể trừ trực tiếp để kết luận backlog.

Dashboard tốt nên kết hợp publish rate, handling success rate, pending/in-flight/failed/abandoned, oldest pending age và handling duration. Nếu cần một counter `handled`, hãy tự instrument với semantics rõ ràng, tốt nhất tăng sau commit khi muốn đo transaction listener hoàn tất. Dùng registry làm nguồn trạng thái bền vững, metric làm xu hướng, trace/log để điều tra nguyên nhân và eventId để tương quan khi retry. Nhờ vậy, dashboard cho biết chính xác module nào đang nhận nhiều event, listener nào đang chậm và publication nào cần được xử lý tiếp.
