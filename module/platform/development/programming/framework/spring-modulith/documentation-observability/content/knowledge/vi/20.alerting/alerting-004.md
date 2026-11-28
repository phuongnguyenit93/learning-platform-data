# Cảnh báo event type không còn được xử lý

Trong ứng dụng Spring Boot chia thành các application module bằng Spring Modulith, một module có thể phát domain event để module khác xử lý. Ví dụ, module `order` phát `OrderCompleted`; module `inventory` cập nhật tồn kho và module `notification` gửi thông báo. Khi một event type đột ngột không còn được xử lý, trạng thái đơn hàng và các bước nghiệp vụ phía sau có thể không đồng bộ dù HTTP request ban đầu đã trả về thành công.

Một cảnh báo hữu ích cần phân biệt ba tình huống:

1. **Không còn event được publish:** module nguồn không phát event như kỳ vọng.
2. **Event đã được publish nhưng listener không hoàn tất:** executor bị nghẽn, listener lỗi, hoặc publication bị treo.
3. **Listener hoàn tất nhưng metric/trace không phản ánh đúng:** thiếu instrumentation, sai nhãn, sampling hoặc cấu hình registry.

Nếu chỉ nhìn một counter tổng số event được publish, ta không thể biết listener có xử lý thành công hay không. Bài học này kết hợp **Spring Modulith Event Publication Registry**, Micrometer metrics, Prometheus alert rules và runbook để cảnh báo khi event type không còn được xử lý.

Bài thuộc chương **Alerting** của module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Mục tiêu là kiểm chứng tương tác giữa application module trong lúc ứng dụng vận hành, đồng thời giữ cảnh báo có ý nghĩa và có thể hành động.

> **Phạm vi phiên bản:** Phần lifecycle status trong bài dùng Spring Modulith 2.2.0. Các trạng thái `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED` và `RESUBMITTED` được giới thiệu từ 2.0; `ABANDONED` có từ 2.2. Với Spring Modulith cũ hơn, Event Publication Registry vẫn ghi nhận publication hoàn tất/chưa hoàn tất, nhưng không có đầy đủ status lifecycle mới. Luôn kiểm tra API và property theo BOM của dự án.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Phân biệt event publication, listener invocation và publication completion.
2. Giải thích metric mặc định của Spring Modulith đo event được publish, không phải event được consume.
3. Dùng Event Publication Registry để nhận diện publication chưa hoàn tất theo event type và listener.
4. Thiết kế metric cho backlog, publication age, failed attempts và listener completion.
5. Viết alert cho event không được publish, event đã publish nhưng không có listener completion, và backlog bị kẹt.
6. Cấu hình Staleness Monitor để nhận diện publication nằm quá lâu ở trạng thái chờ hoặc đang xử lý.
7. Phân biệt cảnh báo kỹ thuật với việc tự động retry/resubmit event.
8. Xử lý false positive do traffic thấp, sampling, retention hoặc listener không được registry theo dõi.

## 2. Event type không còn được xử lý có nghĩa gì?

Một event type có thể bị “im lặng” ở nhiều điểm trong luồng:

~~~mermaid
flowchart LR
    Source["Module nguồn"] --> Publish["Publish OrderCompleted"]
    Publish --> Registry["Event Publication Registry"]
    Registry --> Listener["Listener ở module đích"]
    Listener --> Complete["Xử lý thành công"]
    Listener --> Failed["Lỗi / bị treo"]
    Source -. "Không phát event" .-> NoPublish["Không có publication mới"]
    Registry -. "Chưa hoàn tất" .-> Backlog["PUBLISHED / PROCESSING / FAILED"]
~~~

| Tình huống | Dấu hiệu | Ý nghĩa |
| --- | --- | --- |
| Producer không phát event | Không có publication/counter mới trong cửa sổ thời gian dự kiến | Có thể producer ngừng hoạt động hoặc nghiệp vụ không phát sinh |
| Event được publish, không có completion | Publication còn ở trạng thái chưa hoàn tất hoặc không có completion counter | Consumer có thể không chạy, bị nghẽn hoặc lỗi |
| Listener đang chạy quá lâu | Publication ở `PROCESSING` quá ngưỡng | Listener có thể bị treo hoặc xử lý lâu hơn SLA |
| Listener thất bại | Publication ở `FAILED` | Cần xem exception và quyết định retry |
| Listener bị từ bỏ | Publication ở `ABANDONED` | Không còn nằm trong luồng resubmission thông thường |
| Không có publication cho listener kỳ vọng | Event có được publish nhưng registry không có target listener tương ứng | Listener có thể không được đăng ký hoặc không thuộc nhóm listener được registry theo dõi |

**Không có event mới chưa chắc là lỗi.** Một event như `OrderCompleted` có thể chỉ phát sinh khi có đơn hoàn tất. Nếu trong khoảng 15 phút không có đơn nào, không có publication mới là hành vi bình thường. Alert “không có event” chỉ hợp lý khi có kỳ vọng về traffic, lịch chạy hoặc synthetic canary.

Ngược lại, nếu counter publication tăng nhưng listener không hoàn tất, đó là tín hiệu mạnh hơn về vấn đề ở consumer. Hai tình huống này cần alert riêng.

## 3. Phân biệt metrics publication và processing

Spring Modulith Insight cung cấp observability cho tương tác module và domain events. Các metrics event publication mặc định gồm:

| Metric logic | Ý nghĩa |
| --- | --- |
| `module.events.published` | Counter tổng hợp số domain event được publish |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter cho event type cụ thể, có thể bổ sung tag nghiệp vụ |

Metric tổng hợp có các low-cardinality keys như `module.event.type`, `module.identifier` và `module.name`. Metric cho event cụ thể có thể được tùy chỉnh qua `ModulithEventMetricsCustomizer`.

**Các metric trên đo publication.** Chúng không cho biết listener nào đã bắt đầu xử lý, listener nào hoàn tất, hay publication nào đang bị kẹt. Đừng đặt tên alert “consumer healthy” chỉ dựa trên counter publication tăng.

Để biết kết quả xử lý, cần kết hợp:

- **Event Publication Registry:** lưu publication theo từng transactional listener và đánh dấu hoàn tất khi listener chạy thành công.
- **Custom listener metrics:** đếm số lần listener thành công/thất bại theo event type và listener.
- **Backlog/age gauges:** đo số publication chưa hoàn tất và tuổi của publication cũ nhất.
- **Logs/traces:** điều tra một publication cụ thể, exception và module span.

### Một publication được ghi cho từng listener

Event Publication Registry tích hợp với cơ chế event của Spring. Khi event được publish, registry xác định các transactional event listeners sẽ nhận event và ghi publication entry trong transaction nghiệp vụ gốc. Khi listener hoàn tất thành công, entry tương ứng được đánh dấu hoàn tất. Nếu listener lỗi, entry chưa được đánh dấu hoàn tất để có thể xử lý phục hồi.

Vì registry ghi theo **event và listener target**, một event có thể có nhiều publication entries. Ví dụ `OrderCompleted` được hai listener xử lý thì có thể có hai entries riêng. Do đó, số publication không nhất thiết bằng số event duy nhất.

## 4. Event Publication Registry và lifecycle status

Từ Spring Modulith 2.0, mỗi publication có lifecycle status:

| Status | Ý nghĩa | Cách diễn giải khi alert |
| --- | --- | --- |
| `PUBLISHED` | Publication đã được ghi và đang chờ xử lý/được tiếp nhận | Có thể là backlog bình thường; cảnh báo nếu tuổi vượt SLA |
| `PROCESSING` | Listener đã nhận publication và đang thực thi | Theo dõi tuổi xử lý để phát hiện tác vụ treo |
| `COMPLETED` | Listener đã hoàn tất thành công | Không còn là backlog |
| `FAILED` | Listener ném exception hoặc publication cũ bị đánh dấu stale | Cần kiểm tra lỗi và kế hoạch phục hồi |
| `RESUBMITTED` | Publication lỗi đã được gửi lại để xử lý | Theo dõi lần xử lý tiếp theo |
| `ABANDONED` | Theo Spring Modulith 2.2, policy quyết định dừng resubmission | Cần cảnh báo riêng vì publication đã bị từ bỏ |

Luồng điển hình:

~~~mermaid
stateDiagram-v2
    [*] --> PUBLISHED
    PUBLISHED --> PROCESSING
    PROCESSING --> COMPLETED
    PROCESSING --> FAILED
    FAILED --> RESUBMITTED
    RESUBMITTED --> PROCESSING
    FAILED --> ABANDONED
~~~

Một publication ở `PUBLISHED` lâu có thể cho thấy executor không nhận task. `PROCESSING` lâu có thể do listener đang chạy lâu hoặc bị treo. `FAILED` thể hiện lỗi đã được ghi nhận. `RESUBMITTED` cho biết đã có thao tác gửi lại, nhưng chưa chứng minh listener đã hoàn tất.

### Registry không theo dõi mọi listener mặc định

Mặc định, Event Publication Registry ghi nhận các listener được đánh dấu bằng `@TransactionalEventListener` hoặc annotation meta-annotated tương ứng. `@ApplicationModuleListener` đáp ứng điều kiện này vì nó là listener bất đồng bộ, transactional và chạy sau commit.

Listener chỉ dùng `@EventListener` thông thường không tự động có cùng publication lifecycle. Nếu hệ thống có consumer kiểu này, cần instrument success/failure riêng hoặc chuyển sang cơ chế transactional listener phù hợp nếu nghiệp vụ yêu cầu theo dõi bền vững.

`@ApplicationModuleListener` là shortcut cho async transactional event listener: nó chạy sau khi transaction nguồn commit và thực thi trong transaction riêng (mặc định `REQUIRES_NEW`). Vì vậy, HTTP request có thể trả response trước khi listener hoàn tất. Alert cho event listener phải dựa trên trạng thái consumer/publication, không dựa vào HTTP response của producer.

Có thể tùy chỉnh annotation kích hoạt registry bằng property `spring.modulith.events.registry-trigger-annotation`. Hãy kiểm tra cấu hình này trước khi kết luận rằng một listener không tạo publication là listener bị lỗi.

## 5. Bật observability và Event Publication Registry

Với Spring Modulith 2.2, starter Insight là cách thuận tiện để bật actuator và observability cho application module:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <version>2.2.0</version>
    <scope>runtime</scope>
</dependency>
~~~

Để lưu Event Publication Registry, bổ sung starter persistence phù hợp. Ví dụ với JPA:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-jpa</artifactId>
</dependency>
~~~

Hoặc dùng JDBC:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-jdbc</artifactId>
</dependency>
~~~

Chọn đúng một persistence integration theo hệ thống lưu trữ của ứng dụng và quản lý version qua BOM Spring Modulith. Starter Insight cung cấp actuator/observability; starter JPA/JDBC/MongoDB cung cấp persistence cho publication registry. Hai mục đích này liên quan nhưng không thay thế nhau.

Để xuất metrics Prometheus, cần Micrometer registry phù hợp, ví dụ `micrometer-registry-prometheus`, và expose endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus,modulith
~~~

Không expose các endpoint quản trị công khai. Giới hạn quyền truy cập qua security/network policy và chỉ mở endpoint cần thiết.

### Kiểm tra các endpoint

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/module.events.published
curl -i http://localhost:8080/actuator/prometheus
curl -i http://localhost:8080/actuator/modulith
~~~

Endpoint `/actuator/modulith` cung cấp cấu trúc application module và dependencies. Nó hữu ích để kiểm tra ranh giới kiến trúc, nhưng **không phải endpoint trạng thái xử lý từng event publication**. Trạng thái publication phải được đọc từ Event Publication Registry hoặc metric tùy chỉnh dựa trên registry.

## 6. Cấu hình Staleness Monitor

Một listener có thể để publication ở `PUBLISHED`, `PROCESSING` hoặc `RESUBMITTED` nếu ứng dụng crash hoặc listener bị treo. Spring Modulith 2.0 cung cấp Staleness Monitor để đánh dấu những publication quá cũ thành `FAILED`.

Điểm cần nhớ: các ngưỡng staleness mặc định đều là `Duration.ZERO`. Khi tất cả duration bằng zero, monitor không đăng ký scheduled task và không tự động đánh dấu publication stale.

Ví dụ cấu hình:

~~~yaml
spring:
  modulith:
    events:
      staleness:
        check-interval: 1m
        published: 2m
        processing: 10m
        resubmitted: 2m
~~~

Các giá trị trên chỉ là ví dụ. Chọn ngưỡng dựa trên SLA và thời gian xử lý thực tế:

- `published`: bao lâu một publication được phép chờ trước khi coi là stale.
- `processing`: thời gian tối đa một listener được phép ở trạng thái đang xử lý.
- `resubmitted`: thời gian chờ sau khi gửi lại trước khi coi là stale.
- `check-interval`: chu kỳ kiểm tra các publication cũ.

Staleness Monitor **chỉ đánh dấu FAILED**, không tự sửa nguyên nhân nghiệp vụ và không đảm bảo tự resubmit. Sau khi trạng thái được cập nhật, alert có thể phát hiện failure và runbook quyết định cách phục hồi.

Đừng đặt ngưỡng thấp hơn thời gian xử lý bình thường. Một event batch lớn hoặc downstream chậm có thể bị đánh dấu stale dù listener vẫn đang làm việc.

## 7. Thiết kế metric cho listener

Để cảnh báo event type không còn được xử lý, nên có một bộ metric theo từng cặp **event type + listener**:

| Metric ứng dụng | Loại | Mục đích |
| --- | --- | --- |
| `shop.event.listener.completed` | Counter | Số lần listener hoàn tất thành công |
| `shop.event.listener.failed` | Counter | Số lần listener ném lỗi |
| `shop.event.listener.incomplete` | Gauge | Số publication chưa hoàn tất |
| `shop.event.listener.oldest.incomplete.age.seconds` | Gauge | Tuổi của publication chưa hoàn tất lâu nhất |
| `shop.event.listener.processing` | Gauge | Số publication đang xử lý, nếu snapshot hỗ trợ phân loại status |

Dùng tag có tập giá trị hữu hạn, chẳng hạn:

- `event_type=OrderCompleted`
- `listener=inventory.order-completed`
- `module=inventory`

Không đưa publication UUID, order ID, tenant ID, request ID hoặc trace ID vào metric tags. Những giá trị này có cardinality cao; giữ chúng trong logs/traces để điều tra từng lần xử lý.

### Đếm kết quả invocation trong listener

Có thể đếm thành công/thất bại ngay tại listener. Đặt listener ID ổn định giúp đối chiếu với publication target:

~~~java
package com.example.shop.inventory;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryManagement {

    private final Counter completed;
    private final Counter failed;

    InventoryManagement(MeterRegistry registry) {
        this.completed = Counter.builder("shop.event.listener.completed")
                .tag("event_type", "OrderCompleted")
                .tag("listener", "inventory.order-completed")
                .register(registry);

        this.failed = Counter.builder("shop.event.listener.failed")
                .tag("event_type", "OrderCompleted")
                .tag("listener", "inventory.order-completed")
                .register(registry);
    }

    @ApplicationModuleListener(id = "inventory.order-completed")
    void on(OrderCompleted event) {
        try {
            updateInventory(event);
            completed.increment();
        } catch (RuntimeException exception) {
            failed.increment();
            throw exception;
        }
    }

    private void updateInventory(OrderCompleted event) {
        // Gọi nghiệp vụ cập nhật tồn kho.
    }
}
~~~

Đoạn mã đếm **số lần listener invocation**. Khi một publication được retry, mỗi lần chạy có thể tăng counter thêm một lần. Counter completed không phải số event duy nhất đã hoàn tất. Nếu cần đếm publication duy nhất, hãy dùng trạng thái/ID của registry hoặc một cơ chế deduplication nghiệp vụ.

Việc ném lại exception là cần thiết để framework và Event Publication Registry nhận biết listener thất bại. Không nuốt exception sau khi tăng failure counter, vì khi đó listener có thể bị đánh dấu thành công dù nghiệp vụ chưa hoàn tất.

## 8. Đo backlog và tuổi publication từ registry

Event Publication Registry cung cấp API để tìm publication chưa hoàn tất. Với Spring Modulith 2.2, `EventPublicationRegistry.findIncompletePublications()` trả về các publication chưa hoàn tất; mỗi publication có event, target listener, publication date, completion attempts và status.

Với một event type quan trọng, có thể định kỳ lấy snapshot và cập nhật gauges. Trong Spring Modulith 2.2, `getLastPublicationDate()` phản ánh lần publish/resubmit gần nhất; dùng giá trị này để đo tuổi chờ sau lần resubmit thay vì luôn tính từ publication đầu tiên:

~~~java
package com.example.shop.observability;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

import com.example.shop.order.OrderCompleted;
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.modulith.events.EventPublication;
import org.springframework.modulith.events.core.EventPublicationRegistry;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
class OrderCompletedPublicationMetrics {

    private static final String LISTENER_ID = "inventory.order-completed";

    private final EventPublicationRegistry publications;
    private final AtomicLong incomplete = new AtomicLong();
    private final AtomicLong failed = new AtomicLong();
    private final AtomicLong oldestAgeSeconds = new AtomicLong();

    OrderCompletedPublicationMetrics(
            EventPublicationRegistry publications,
            MeterRegistry meters) {

        this.publications = publications;

        Gauge.builder("shop.event.listener.incomplete", incomplete, AtomicLong::get)
                .tag("event_type", "OrderCompleted")
                .tag("listener", LISTENER_ID)
                .register(meters);

        Gauge.builder("shop.event.listener.failed", failed, AtomicLong::get)
                .tag("event_type", "OrderCompleted")
                .tag("listener", LISTENER_ID)
                .register(meters);

        Gauge.builder("shop.event.listener.oldest.incomplete.age.seconds",
                        oldestAgeSeconds, AtomicLong::get)
                .tag("event_type", "OrderCompleted")
                .tag("listener", LISTENER_ID)
                .register(meters);
    }

    @Scheduled(fixedDelayString = "30000")
    void refresh() {

        var now = Instant.now();

        var pending = publications.findIncompletePublications().stream()
                .filter(publication -> publication.getEvent() instanceof OrderCompleted)
                .filter(publication -> LISTENER_ID.equals(
                        publication.getTargetIdentifier().getValue()))
                .toList();

        incomplete.set(pending.size());
        failed.set(pending.stream()
                .filter(publication ->
                        publication.getStatus() == EventPublication.Status.FAILED)
                .count());

        long oldest = pending.stream()
                .mapToLong(publication -> Math.max(0,
                        Duration.between(publication.getLastPublicationDate(), now).toSeconds()))
                .max()
                .orElse(0);

        oldestAgeSeconds.set(oldest);
    }
}
~~~

Trong ứng dụng, bật scheduling nếu chưa bật bằng `@EnableScheduling`. Listener ID trong snapshot phải khớp với `id` của listener; nếu không khai báo ID, target identifier mặc định thường dựa trên signature đầy đủ của listener method. Đối với nhiều event types/listeners, tạo một cấu hình allowlist rõ ràng thay vì dùng mọi tên event động.

Ví dụ này phù hợp để minh họa và cho hệ thống có số publication chưa hoàn tất vừa phải. `findIncompletePublications()` đọc tập publication chưa hoàn tất; nếu backlog rất lớn, không nên quét toàn bộ store mỗi 30 giây. Khi đó, cân nhắc truy vấn tổng hợp/paging ở repository persistence hoặc một bảng snapshot chuyên dụng.

Nếu completion mode là `DELETE`, các publication hoàn tất bị xóa khỏi registry; vì vậy không thể dùng registry để thống kê lịch sử completed. Counter listener hoặc hệ thống event analytics riêng vẫn cần thiết.

## 9. Các loại cảnh báo cần có

Không nên gộp tất cả thành một alert duy nhất. Một bộ alert thực dụng gồm:

| Alert | Điều kiện | Mức độ gợi ý |
| --- | --- | --- |
| Event type không còn được publish | Không có publication trong cửa sổ thời gian dù nghiệp vụ dự kiến có traffic | Warning |
| Event đã publish nhưng listener không hoàn tất | Publication counter tăng, completion counter không tăng | Critical |
| Backlog quá cũ | Tuổi publication chưa hoàn tất vượt SLA | Warning/Critical theo ngưỡng |
| Listener thất bại | Có publication ở `FAILED` hoặc failure counter tăng | Warning/Critical |
| Publication bị từ bỏ | Có `ABANDONED` | Critical nếu event ảnh hưởng nghiệp vụ |
| Consumer không có telemetry | Metric expected listener bị mất hoặc scrape target down | Warning |

### Alert 1 — Event type không còn được publish

Dùng khi producer phải phát event theo lịch hoặc theo một lưu lượng nghiệp vụ có thể dự đoán. Có thể kiểm tra số publication trong một cửa sổ:

~~~promql
increase(module_events_published_total{
  module_event_type="OrderCompleted"
}[20m]) == 0
~~~

Tên metric/label Prometheus ở ví dụ đã được chuẩn hóa từ meter/tag Micrometer; hãy xác nhận tên thật tại `/actuator/prometheus`. Alert này chỉ hợp lý nếu hệ thống kỳ vọng sẽ có đơn hoàn tất trong cửa sổ 20 phút. Nếu event hiếm hoặc traffic theo giờ làm việc, điều chỉnh cửa sổ hoặc dùng synthetic canary.

Nếu metric series chưa từng được tạo, biểu thức so sánh có thể không trả về series. Có thể dùng `absent_over_time(...)` cho trường hợp không có sample, nhưng cần ghép với điều kiện service/producer đang healthy và lịch nghiệp vụ thực sự kỳ vọng event.

### Alert 2 — Event được publish nhưng listener không hoàn tất

Đây là cảnh báo trực tiếp nhất cho chủ đề bài học:

~~~promql
increase(module_events_published_total{
  module_event_type="OrderCompleted"
}[15m]) > 0
and
increase(shop_event_listener_completed_total{
  event_type="OrderCompleted",
  listener="inventory.order-completed"
}[15m]) == 0
~~~

Điều kiện thứ nhất xác nhận producer đã phát event; điều kiện thứ hai xác nhận listener không ghi nhận invocation thành công trong cùng cửa sổ. Có thể thêm `for: 5m` trong Prometheus rule để tránh cảnh báo khi một batch event vừa được publish và listener đang xử lý bình thường.

Để biểu thức này hoạt động ổn định, đăng ký counter listener ngay khi bean được tạo (như ví dụ ở phần 7), nhờ đó series có giá trị 0 trước khi event đầu tiên xuất hiện.

### Alert 3 — Publication backlog quá cũ

~~~promql
shop_event_listener_oldest_incomplete_age_seconds{
  event_type="OrderCompleted",
  listener="inventory.order-completed"
} > 300
~~~

Ngưỡng 300 giây là ví dụ. Nếu SLA xử lý event là 30 giây, hãy chọn ngưỡng gần với SLA cộng một khoảng đệm phù hợp. Nếu listener bình thường xử lý batch trong 8 phút, ngưỡng 5 phút sẽ tạo false positive.

### Alert 4 — Publication thất bại

~~~promql
shop_event_listener_failed{
  event_type="OrderCompleted",
  listener="inventory.order-completed"
} > 0
~~~

Gauge failed trong ví dụ là số publication chưa hoàn tất có status `FAILED`. Sau khi publication được resubmit và xử lý xong, gauge sẽ giảm. Có thể bổ sung counter invocation failure để theo dõi tốc độ lỗi trong cửa sổ.

## 10. Ví dụ Prometheus alert rules

Các rule sau minh họa cách nhóm cảnh báo:

~~~yaml
groups:
  - name: spring-modulith-event-processing
    rules:
      - alert: OrderCompletedNotPublished
        expr: increase(module_events_published_total{module_event_type="OrderCompleted"}[20m]) == 0
        for: 5m
        labels:
          severity: warning
          module: order
        annotations:
          summary: "Không thấy event OrderCompleted mới"
          description: "Kiểm tra producer và xác nhận traffic nghiệp vụ có được kỳ vọng trong cửa sổ này không."

      - alert: OrderCompletedNotProcessed
        expr: |
          increase(module_events_published_total{module_event_type="OrderCompleted"}[15m]) > 0
          and
          increase(shop_event_listener_completed_total{event_type="OrderCompleted",listener="inventory.order-completed"}[15m]) == 0
        for: 5m
        labels:
          severity: critical
          module: inventory
        annotations:
          summary: "OrderCompleted đã publish nhưng listener chưa hoàn tất"
          description: "Kiểm tra backlog, listener logs, executor và Event Publication Registry."

      - alert: OrderCompletedPublicationTooOld
        expr: shop_event_listener_oldest_incomplete_age_seconds{event_type="OrderCompleted",listener="inventory.order-completed"} > 300
        for: 2m
        labels:
          severity: warning
          module: inventory
        annotations:
          summary: "Publication OrderCompleted đang chờ quá lâu"
          description: "Publication cũ nhất đã vượt ngưỡng tuổi cấu hình."

      - alert: OrderCompletedPublicationFailed
        expr: shop_event_listener_failed{event_type="OrderCompleted",listener="inventory.order-completed"} > 0
        for: 1m
        labels:
          severity: critical
          module: inventory
        annotations:
          summary: "Có publication OrderCompleted thất bại"
          description: "Kiểm tra completion attempts, exception và quyết định resubmit."

      - alert: OrderCompletedPublicationAbandoned
        expr: shop_event_listener_abandoned{event_type="OrderCompleted"} > 0
        for: 1m
        labels:
          severity: critical
          module: inventory
        annotations:
          summary: "Có publication OrderCompleted bị từ bỏ"
          description: "Kiểm tra AbandonPolicy, dữ liệu event và quyết định xử lý thủ công."
~~~

Tên metric/label trong ví dụ là kết quả chuẩn hóa theo Prometheus và metric tùy chỉnh của bài. Hãy thay bằng exposition thực tế của ứng dụng. Không copy rule trước khi xác minh metric có tồn tại, label có đúng tên và counter được khởi tạo từ đầu.

## 11. Giám sát trường hợp không có traffic bằng canary

Với event hiếm, alert dựa trên “không có event trong 15 phút” dễ báo sai. Có thể tạo một **synthetic event** theo lịch trong môi trường kiểm thử hoặc một luồng canary riêng:

1. Một scheduler phát event canary với payload tối thiểu.
2. Listener canary xử lý và ghi completion timestamp/metric.
3. Alert nếu canary không hoàn tất trong SLA.
4. Canary không được thay đổi dữ liệu nghiệp vụ thật.

Canary kiểm tra được cả producer, event publication, executor, listener và đường ghi nhận completion. Tuy nhiên, nó không chứng minh mọi event business đều được xử lý đúng; vẫn cần registry/backlog metrics cho từng loại event quan trọng.

Một lựa chọn khác là dựa trên business heartbeat: ví dụ mỗi phút có đơn hoàn tất hoặc mỗi giờ có một batch import. Chỉ dùng no-event alert khi lịch nghiệp vụ đó được xác nhận.

## 12. Xử lý retry và resubmission

Khi alert phát hiện publication thất bại, không nên tự động resubmit mọi event ngay lập tức. Trước tiên xác định:

- Listener có lỗi tạm thời hay lỗi dữ liệu không thể phục hồi?
- Downstream service/database đã hoạt động lại chưa?
- Event có idempotent không?
- Có nguy cơ một event đã thực hiện side effect nhưng transaction đánh dấu completion thất bại không?
- Publication đã được resubmit bởi instance khác chưa?

Spring Modulith cung cấp API:

- `FailedEventPublications.resubmit(ResubmissionOptions)` từ 2.0 để resubmit publication ở trạng thái failed.
- `FailedEventPublications` là abstraction cho các publication chưa hoàn tất; phương thức `resubmit(ResubmissionOptions)` chỉ gửi lại những publication đang failed.

Các options có thể giới hạn batch size, số publication in-flight, minimum age và filter. Với event quan trọng, nên resubmit theo event type/target phù hợp, có batch limit và quan sát kết quả sau từng đợt. Trong Spring Modulith 2.2, `IncompleteEventPublications` đã deprecated để chuyển sang API lifecycle mới.

**Resubmit không đồng nghĩa exactly-once.** Listener có thể được gọi nhiều lần; thao tác cập nhật dữ liệu cần idempotent hoặc có cơ chế deduplication bằng event ID/business key.

Không bật `spring.modulith.events.republish-outstanding-events-on-restart=true` một cách máy móc trong deployment nhiều instance. Tài liệu Spring Modulith lưu ý việc republish outstanding events khi restart thường không được khuyến nghị trong multi-instance deployments vì instance khác có thể vẫn đang xử lý. Hãy dùng cơ chế resubmission phù hợp và hiểu trạng thái claim/processing của registry.

## 13. ABANDONED và chính sách dừng retry

Từ Spring Modulith 2.2, một publication có thể được đánh dấu `ABANDONED` nếu `AbandonPolicy` quyết định không nên retry nữa. Ví dụ:

- Payload không thể deserialize do schema không tương thích.
- Downstream trả lỗi permanent.
- Số lần xử lý đã vượt giới hạn vận hành.

Property `spring.modulith.events.resubmission.abandon-after-attempts` mặc định là `-1`, tức không bật framework default abandonment theo số lần thử. Nếu cấu hình policy/attempt limit, hãy theo dõi abandoned publications riêng vì chúng không còn được đưa vào luồng resubmission thông thường.

Một publication abandoned không có nghĩa listener đã hoàn tất thành công. Không gộp `ABANDONED` vào `COMPLETED` trong dashboard hoặc alert. Đây là tín hiệu cần người vận hành xem xét và quyết định xử lý thủ công/compensation.

Spring Modulith 2.2 cung cấp bean `AbandonedEventPublications` để đọc các publication đã bị từ bỏ. Có thể dùng `findAll()` để tạo gauge theo event type:

~~~java
long abandonedOrderCompleted = abandonedEventPublications.findAll().stream()
        .filter(publication -> publication.getEvent() instanceof OrderCompleted)
        .count();
~~~

Đưa giá trị này vào gauge `shop.event.listener.abandoned` với tag `event_type=OrderCompleted` để rule `OrderCompletedPublicationAbandoned` có dữ liệu. Chỉ dùng tập event types hữu hạn khi tạo metric. API này cũng cung cấp thao tác purge; không gọi purge như một cách xử lý alert vì thao tác đó xóa bằng chứng publication đã bị từ bỏ.

Nếu cấu hình `spring.modulith.events.completion-mode: DELETE`, publication hoàn tất sẽ bị xóa thay vì giữ lại. Completion mode cũng chi phối cách lưu publication `ABANDONED`. Khi cần điều tra lịch sử, cân nhắc `UPDATE` hoặc `ARCHIVE` và đặt retention/purge policy rõ ràng.

## 14. False positives và những giới hạn cần hiểu

| Nguyên nhân | Vì sao có thể báo sai | Cách giảm nhiễu |
| --- | --- | --- |
| Không có traffic nghiệp vụ | Event type không được phát trong cửa sổ | Dùng lịch nghiệp vụ, volume baseline hoặc canary |
| Sampling trace | Một số trace không xuất hiện ở backend dù listener đã chạy | Dựa vào metrics/registry, không dựa vào trace count |
| Listener không transactional | Registry không ghi publication cho listener thông thường | Instrument custom success/failure hoặc dùng transactional listener |
| Listener chưa đăng ký | Không có target publication cho listener mong đợi | So event type với danh sách consumer kỳ vọng và integration tests |
| Completion mode DELETE | Registry xóa publication sau khi hoàn tất | Dùng counter completion hoặc archive mode nếu cần lịch sử |
| Staleness monitor chưa bật | Publication bị treo có thể ở PROCESSING/PUBLISHED lâu mà chưa thành FAILED | Cấu hình duration staleness khác zero và alert theo tuổi |
| Ngưỡng xử lý quá thấp | Listener hợp lệ bị đánh dấu stale | Chọn threshold theo phân bố latency thực tế |
| Nhiều instance | Một instance có thể chưa thấy toàn bộ trạng thái hoặc metric cục bộ | Dùng backend tổng hợp, scrape tất cả instance và phân biệt label instance |
| Retry tạo nhiều invocation | Completion counter tăng nhiều lần cho cùng publication | Phân biệt invocation counter và unique publication state |
| Metric label sai | Alert query không match series thực tế | Kiểm tra `/actuator/prometheus` và test rule |

### Event Publication Registry không phải event broker dashboard

Registry theo dõi publication tới transactional listeners trong ứng dụng. Nếu event được externalize sang Kafka/RabbitMQ, cần theo dõi thêm broker-specific signals như consumer lag, offset commit, dead-letter queue và broker delivery failures. Publication được đánh dấu hoàn tất có thể chỉ có nghĩa listener đã hoàn thành bước gửi message tới broker, không chứng minh consumer downstream bên ngoài đã xử lý message.

## 15. Runbook khi alert kích hoạt

Khi nhận `OrderCompletedNotProcessed` hoặc `OrderCompletedPublicationTooOld`:

1. **Xác nhận producer:** kiểm tra counter `module.events.published`, module nguồn, traffic và log phát event.
2. **Xác nhận target listener:** kiểm tra listener ID, bean có được đăng ký và registry có tạo publication cho target đó.
3. **Kiểm tra status:** phân biệt `PUBLISHED`, `PROCESSING`, `FAILED`, `RESUBMITTED` và `ABANDONED`.
4. **Xem publication age và attempts:** xác định backlog mới tăng hay một publication cũ bị kẹt; xem completion attempts và last resubmission date.
5. **Kiểm tra executor:** queue depth, thread pool saturation, rejected tasks và thời gian chạy listener.
6. **Kiểm tra dependency:** database, API hoặc broker mà listener cần gọi; tìm exception và trace/log correlation.
7. **Khôi phục nguyên nhân:** sửa lỗi code/config hoặc phục hồi downstream trước khi resubmit.
8. **Resubmit có kiểm soát:** giới hạn theo event type/target, batch size và số in-flight; xác nhận idempotency.
9. **Xác nhận recovery:** backlog giảm, publication chuyển sang COMPLETED, completion metric tăng và alert tự clear.
10. **Rà soát nguyên nhân gốc:** bổ sung test, dashboard, retry policy hoặc capacity phù hợp.

Không xóa publication lỗi chỉ để làm dashboard xanh. Việc purge hoặc chuyển archive cần tuân theo chính sách lưu giữ và có bằng chứng nghiệp vụ đã được xử lý/compensate.

## 16. Bài thực hành: tạo alert cho OrderCompleted

Chuẩn bị ứng dụng có hai module `order` và `inventory`:

1. Thêm Spring Modulith Insight và một Event Publication Registry persistence phù hợp.
2. Tạo `OrderCompleted` được publish trong transaction của module `order`.
3. Tạo listener `@ApplicationModuleListener(id = "inventory.order-completed")` ở module `inventory`.
4. Xác nhận Event Publication Registry ghi entry cho listener và đánh dấu completed khi xử lý thành công.
5. Bật Actuator metrics/Prometheus và xác nhận metric `module.events.published` tăng khi phát event.
6. Thêm custom listener completed/failed counters và gauge backlog/oldest age.
7. Cố ý làm listener ném exception trong môi trường test; xác nhận publication không bị đánh dấu completed và failure signal xuất hiện.
8. Cố ý làm listener chậm hơn ngưỡng; kiểm tra Staleness Monitor sau khi cấu hình.
9. Viết alert “published but no completion” và “oldest incomplete age exceeds SLA”.
10. Tạm dừng phát event để kiểm tra no-publish alert; xác nhận rule chỉ kích hoạt khi traffic được kỳ vọng.
11. Khôi phục listener và resubmit một batch có giới hạn; xác nhận backlog giảm và listener idempotent.
12. Ghi lại metric names/labels thật, ngưỡng alert, runbook owner và bằng chứng recovery.

Mẫu ghi kết quả:

| Kịch bản | Publication metric | Registry status | Listener completion | Alert mong đợi |
| --- | --- | --- | --- | --- |
| Listener xử lý thành công | Tăng | COMPLETED | Tăng | Không |
| Producer không phát event | Không tăng | Không có entry mới | Không tăng | No-publish nếu traffic được kỳ vọng |
| Listener ném exception | Tăng | FAILED | Không tăng | Processing failure |
| Listener bị treo | Tăng | PROCESSING/PUBLISHED quá lâu | Không tăng | Backlog/age |
| Publication được resubmit | Không nhất thiết có publication mới | RESUBMITTED → PROCESSING | Tăng khi hoàn tất | Alert clear sau recovery |
| Listener bị abandon | Tăng | ABANDONED | Không tăng | Abandoned publication |

### Câu hỏi tự kiểm tra

1. Vì sao `module.events.published` không đủ để chứng minh listener đã xử lý event?
2. Event Publication Registry tạo publication entry theo event hay theo từng listener target?
3. Trạng thái `PUBLISHED` khác `PROCESSING` ở điểm nào?
4. Vì sao `FAILED` và `ABANDONED` cần được cảnh báo riêng?
5. Staleness Monitor có hoạt động khi mọi duration đều bằng zero không?
6. Nếu listener dùng `@EventListener` thông thường, vì sao registry có thể không ghi publication?
7. Vì sao alert “không có event trong 15 phút” có thể sai với event hiếm?
8. Tại sao phải phân biệt completion invocation counter với số publication duy nhất?
9. Completion mode `DELETE` ảnh hưởng thế nào đến việc truy vấn lịch sử completed publications?
10. Vì sao resubmit event cần idempotency?

## 17. Tổng kết

Cảnh báo event type không còn được xử lý cần quan sát cả **phía publish** lẫn **phía consume**. Spring Modulith Insight cung cấp metrics `module.events.published` để theo dõi publication; metric này không đo listener completion. Event Publication Registry ghi publication theo từng transactional listener và cung cấp bằng chứng về các publication chưa hoàn tất. Từ Spring Modulith 2.0, status lifecycle giúp phân biệt chờ xử lý, đang xử lý, hoàn tất, thất bại và resubmit; Spring Modulith 2.2 bổ sung trạng thái abandoned.

Một hệ thống cảnh báo đáng tin cậy kết hợp publication counters, listener success/failure counters, backlog/age gauges, Staleness Monitor và canary cho event có lịch kỳ vọng. Alert cần phân biệt producer không phát event với consumer không hoàn tất event, dùng ngưỡng theo SLA và tránh nhãn cardinality cao. Khi alert kích hoạt, hãy kiểm tra registry, listener target, executor, downstream dependency và idempotency trước khi resubmit. Như vậy, dashboard phản ánh được việc event thực sự đi qua các ranh giới application module và hoàn tất xử lý.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html).
- [Spring Modulith 2.2 — Production-ready Features và Observability Metrics](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith — EventPublicationRegistry API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/core/EventPublicationRegistry.html).
- [Spring Modulith — EventPublication API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/EventPublication.html).
- [Spring Modulith — FailedEventPublications API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/FailedEventPublications.html).
- [Spring Modulith — AbandonedEventPublications API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/AbandonedEventPublications.html).
- [Spring Modulith — ApplicationModuleListener API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/events/ApplicationModuleListener.html).
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/).
