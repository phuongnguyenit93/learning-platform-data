# Kiểm thử event publication metric

## 1. Vì sao cần kiểm thử event publication metric?

Trong chương **Kiểm thử** của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, chúng ta tìm hiểu cách xác minh các metrics mà Spring Modulith ghi nhận khi application module publish domain event. Khi ứng dụng có các module như `order`, `payment` và `inventory`, event publication là một cách quan trọng để các module giao tiếp mà không cần phụ thuộc trực tiếp vào implementation của nhau.

Spring Modulith cung cấp observability metrics để đếm các domain event được publish. Những counter này giúp trả lời các câu hỏi vận hành:

- Module nào đang phát event?
- Loại event nào xuất hiện nhiều?
- Tần suất publish event có tăng bất thường sau một lần triển khai không?
- Một luồng nghiệp vụ có phát event đúng như kỳ vọng không?
- Custom tags có được thêm vào counter riêng của event không?

Kiểm thử metric cần xác nhận **sự kiện được publish làm counter tăng đúng** và các tag nhận diện module/event có giá trị mong đợi. Một bài test như vậy bổ sung cho kiểm thử nghiệp vụ event publication, đồng thời giúp phát hiện lỗi cấu hình observability trước khi triển khai dashboard.

### Mục tiêu học tập

1. Hiểu hai counter event publication do Spring Modulith đăng ký.
2. Phân biệt metric đếm event được publish với Event Publication Registry theo dõi listener lifecycle.
3. Cấu hình observability support và MeterRegistry trong ứng dụng.
4. Viết integration test kiểm tra aggregate counter và counter theo từng event type.
5. Kiểm thử custom tags bằng `ModulithEventMetricsCustomizer`.
6. Xác minh metrics qua Actuator và Prometheus exposition.
7. Xử lý counter tích lũy, async listener, test context và cardinality.
8. Chẩn đoán khi event đã được publish nhưng metric không xuất hiện.

## 2. Event publication metric đo điều gì?

Spring Modulith observability đăng ký hai dạng counter cho domain events được publish trong ứng dụng.

| Metric | Ý nghĩa | Low-cardinality tags |
| --- | --- | --- |
| `module.events.published` | Counter tổng hợp các event publication | `module.event.type`, `module.identifier`, `module.name` |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter riêng cho một event type trong module | `module.identifier`, `module.name` |

Ví dụ, module `order` publish event `OrderCompleted`. Hai counter tương ứng có thể được biểu diễn như sau:

```text
module.events.published
  module.identifier = order
  module.name = Order
  module.event.type = OrderCompleted
  count = 1

module.events.published.order.OrderCompleted
  module.identifier = order
  module.name = Order
  count = 1
```

Counter tổng hợp giúp phân tích event publication trên toàn ứng dụng hoặc lọc theo module/event type. Counter riêng theo event giúp xem một loại domain event cụ thể mà không cần dựa vào tag event type của metric tổng hợp.

Tên metric riêng được ghép từ technical module identifier và simple event type name. Khi xây dựng test, hãy dùng đúng identifier thực tế mà Spring Modulith phát hiện từ package/module arrangement.

### 2.1. Metric là counter, không phải timer

Event publication metrics là counter. Giá trị tăng khi event được publish; bản thân counter không đo:
- Thời gian listener xử lý event.
- Số listener xử lý thành công.
- Số event đang chờ.
- Số lần retry hoặc số publication bị abandon.
- Thời gian từ lúc publish đến lúc listener hoàn thành.

Có thể dùng `rate()` hoặc `increase()` trên counter trong Prometheus để tính tốc độ hoặc tổng lượng event theo một khoảng thời gian. Counter không thay thế tracing/timer nếu cần đo latency của listener. Nếu cần theo dõi trạng thái xử lý, hãy dùng Event Publication Registry hoặc metric nghiệp vụ riêng.

### 2.2. Metric publication và Event Publication Registry khác nhau

Đây là hai cơ chế có mục đích khác nhau:

| Cơ chế | Theo dõi điều gì? | Dùng khi |
| --- | --- | --- |
| Event publication metric | Số lượng domain event được publish | Dashboard, trend, throughput và alert |
| Event Publication Registry | Trạng thái publication đối với từng transactional listener | Theo dõi pending, processing, completed, failed và resubmission |

Trong Spring Modulith 2.x, publication có lifecycle như `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED`, `RESUBMITTED` và `ABANDONED` (trạng thái ABANDONED từ 2.2). Metric tổng hợp không thay thế các trạng thái này.

Ví dụ: counter `module.events.published` tăng khi order phát `OrderCompleted`. Điều đó không chứng minh listener inventory đã xử lý thành công. Muốn xác minh listener hoàn tất, hãy kiểm tra publication registry hoặc kết quả nghiệp vụ tương ứng.

## 3. Chuẩn bị dependency và MeterRegistry

### 3.1. Bật Spring Modulith observability

Có thể dùng Spring Modulith Insight starter để đưa actuator và observability support vào ứng dụng:

```groovy
dependencies {
    implementation platform(
        "org.springframework.modulith:spring-modulith-bom:$springModulithVersion"
    )

    // Core APIs and module detection used by the application.
    implementation "org.springframework.modulith:spring-modulith-starter-core"

    runtimeOnly "org.springframework.modulith:spring-modulith-starter-insight"

    // Nếu cần xuất metrics qua Prometheus.
    runtimeOnly "io.micrometer:micrometer-registry-prometheus"

    testImplementation "org.springframework.boot:spring-boot-starter-test"
    testImplementation "org.springframework.modulith:spring-modulith-starter-test"
}
```

Dùng phiên bản Spring Modulith BOM tương thích với dòng Spring Boot của dự án. Insight starter bao gồm observability support; ứng dụng vẫn cần MeterRegistry phù hợp và có thể thêm exporter/registry theo nền tảng monitoring.

Nếu chỉ cần event metrics mà không cần module actuator, có thể dùng `spring-modulith-observability-core` ở runtime thay cho Insight starter. Không cần khai báo cả hai nếu Insight starter đã đưa observability core vào dependency graph.

### 3.2. Thêm API khi cần customizer

Nếu ứng dụng muốn tùy chỉnh counter theo event type, thêm `spring-modulith-observability-api` ở compile scope:

```groovy
dependencies {
    implementation "org.springframework.modulith:spring-modulith-observability-api"
}
```

Artifact này cung cấp API `ModulithEventMetricsCustomizer` để cấu hình custom tags hoặc cách tạo counter cho một loại event. Việc thêm customizer không thay thế observability core runtime.

### 3.3. MeterRegistry trong test

Spring Boot auto-configures MeterRegistry khi có Micrometer registry trên classpath. Trong integration test, có thể inject `MeterRegistry` để kiểm tra counter trực tiếp. Nếu test profile không có registry nào, hãy bổ sung một registry test như `SimpleMeterRegistry` hoặc cấu hình registry riêng trong test context.

Ví dụ test chỉ cần đọc giá trị counter:

```java
@Autowired
MeterRegistry meterRegistry;
```

Không nên tạo một registry riêng trong test rồi kiểm tra registry đó nếu ứng dụng thực tế lại ghi metrics vào một registry khác. Hãy inject đúng bean mà instrumentation đang sử dụng.

## 4. Chuẩn bị module và domain event mẫu

Giả sử ứng dụng có root package `com.acme.shop` và module `order` nằm trong `com.acme.shop.order`. Module này publish `OrderCompleted` khi đơn hàng hoàn tất.

Có thể đánh dấu lớp khởi động của ứng dụng bằng `@Modulithic` để khai báo rõ root package mà Spring Modulith dùng để phát hiện application modules:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic
@SpringBootApplication
public class ShopApplication {}
```

### 4.1. Khai báo event

```java
package com.acme.shop.order;

import java.util.UUID;

public record OrderCompleted(
        UUID orderId,
        SalesChannel channel
) {}
```

Đặt enum ở file riêng `SalesChannel.java` trong cùng package:

```java
package com.acme.shop.order;

public enum SalesChannel {
    WEB, STORE
}
```

`SalesChannel` là enum có số giá trị hữu hạn. Ví dụ này sẽ dùng nó làm custom metric tag ở phần sau.

### 4.2. Publish event từ service thuộc module

```java
package com.acme.shop.order;

import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderManagement {

    private final ApplicationEventPublisher events;

    public OrderManagement(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void complete(UUID orderId, SalesChannel channel) {
        // Các bước chuyển trạng thái đơn hàng được thực hiện ở đây.
        events.publishEvent(new OrderCompleted(orderId, channel));
    }
}
```

Trong test, gọi `OrderManagement.complete(…)` để event được publish từ một component thuộc module `order`. Cách này giúp Spring Modulith có ngữ cảnh module phù hợp để gắn identifier và name vào metric.

Nếu event được publish từ một test helper nằm ngoài package/module hoặc từ một component không được quản lý bởi Spring, kết quả module metadata có thể không giống luồng chạy thật. Hãy test qua entry point nghiệp vụ của module.

Để minh họa tương tác giữa hai module, module inventory có thể đăng ký listener cho event này:

```java
package com.acme.shop.inventory;

import com.acme.shop.order.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryManagement {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Xử lý nghiệp vụ tồn kho.
    }
}
```

Trong ứng dụng thực tế, `@ApplicationModuleListener` thường xử lý event sau transaction commit. Integration test chỉ kiểm tra publication counter không cần chờ listener hoàn tất; nếu kiểm tra side effect tồn kho, hãy cấu hình transaction và chờ kết quả listener riêng.

## 5. Kiểm thử aggregate counter và per-event counter

Integration test nên khởi động application context thật để observability auto-configuration, module detection, event publisher và MeterRegistry cùng hoạt động.

### 5.1. Viết integration test

```java
package com.acme.shop.order;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderEventMetricsIntegrationTests {

    @Autowired
    OrderManagement orderManagement;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void incrementsAggregateAndIndividualEventCounters() {

        var aggregateTags = new String[] {
            "module.identifier", "order",
            "module.event.type", "OrderCompleted"
        };

        var individualTags = new String[] {
            "module.identifier", "order"
        };

        double aggregateBefore =
                count("module.events.published", aggregateTags);

        double individualBefore =
                count("module.events.published.order.OrderCompleted",
                        individualTags);

        orderManagement.complete(UUID.randomUUID(), SalesChannel.WEB);

        double aggregateAfter =
                count("module.events.published", aggregateTags);

        double individualAfter =
                count("module.events.published.order.OrderCompleted",
                        individualTags);

        assertThat(aggregateAfter).isEqualTo(aggregateBefore + 1);
        assertThat(individualAfter).isEqualTo(individualBefore + 1);
    }

    private double count(String name, String... tags) {
        Counter counter = meterRegistry.find(name)
                .tags(tags)
                .counter();

        return counter == null ? 0.0 : counter.count();
    }
}
```

Test này xác minh hai điều:
- Counter tổng hợp tăng một đơn vị cho event `OrderCompleted` thuộc module `order`.
- Counter riêng của `OrderCompleted` trong module `order` cũng tăng một đơn vị.

Tên tag và giá trị phải khớp với module metadata thực tế. Nếu module có display name khác `Order`, điều đó không ảnh hưởng đến truy vấn trong ví dụ vì test lọc bằng `module.identifier`.

### 5.2. Vì sao so sánh delta thay vì giá trị tuyệt đối?

MeterRegistry thường sống cùng application context. Nếu nhiều test dùng chung context, counter có thể đã được tăng bởi test trước. Vì vậy, đừng luôn khẳng định counter phải bằng đúng `1`.

Cách an toàn là:
1. Đọc giá trị trước khi thực hiện hành động.
2. Gọi đúng một lần nghiệp vụ publish event.
3. Đọc lại counter.
4. Kiểm tra hiệu số tăng đúng một đơn vị.

Nếu test yêu cầu trạng thái ban đầu hoàn toàn sạch, có thể dùng context riêng hoặc làm mới context cho test class. Không reset registry dùng chung giữa các test song song vì có thể ảnh hưởng test khác.

### 5.3. Kiểm tra nhiều lần publish

Có thể mở rộng test để publish hai event và xác minh delta là hai:

```java
double before = count(
        "module.events.published",
        "module.identifier", "order",
        "module.event.type", "OrderCompleted"
);

orderManagement.complete(UUID.randomUUID(), SalesChannel.WEB);
orderManagement.complete(UUID.randomUUID(), SalesChannel.STORE);

double after = count(
        "module.events.published",
        "module.identifier", "order",
        "module.event.type", "OrderCompleted"
);

assertThat(after - before).isEqualTo(2.0);
```

Không đưa `orderId` vào tag chỉ để phân biệt hai event. Mỗi ID mới sẽ tạo một time series mới và làm tăng cardinality.

## 6. Kiểm thử custom tags với ModulithEventMetricsCustomizer

Spring Modulith cho phép thêm tags vào counter riêng của event type bằng `ModulithEventMetricsCustomizer`. Đây là cách phù hợp khi dashboard cần phân nhóm theo một thuộc tính nghiệp vụ có số giá trị giới hạn, ví dụ channel, region tier hoặc event category.

### 6.1. Khai báo customizer

```java
package com.acme.shop.observability;

import com.acme.shop.order.OrderCompleted;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> metrics.customize(
                OrderCompleted.class,
                (event, builder) ->
                        builder.tags("sales_channel", event.channel().name())
        );
    }
}
```

Customizer ở ví dụ này thêm `sales_channel` vào counter riêng của `OrderCompleted`. Giá trị chỉ có `WEB` hoặc `STORE` nên cardinality có giới hạn.

Theo API, `customize(Class, BiConsumer)` nhận event instance và `Counter.Builder` đã được khởi tạo theo event type. Có overload khác nhận `Function` để tùy chỉnh cách tạo builder. Nếu chỉ thêm tags, overload `BiConsumer` là đủ.

### 6.2. Kiểm thử custom tag

Bổ sung assertion cho counter riêng:

```java
double before = count(
        "module.events.published.order.OrderCompleted",
        "module.identifier", "order",
        "sales_channel", "WEB"
);

orderManagement.complete(UUID.randomUUID(), SalesChannel.WEB);

double after = count(
        "module.events.published.order.OrderCompleted",
        "module.identifier", "order",
        "sales_channel", "WEB"
);

assertThat(after - before).isEqualTo(1.0);
```

Counter tổng hợp `module.events.published` giữ bộ tag chuẩn của nó. Customizer được tài liệu Spring Modulith mô tả để làm giàu **individual event metrics**. Vì vậy hãy kiểm tra custom tag trên meter riêng của event type.

### 6.3. Chọn custom tag có cardinality thấp

Nên dùng các thuộc tính:
- Có tập giá trị nhỏ và được kiểm soát.
- Có ý nghĩa phân tích trên dashboard.
- Không thay đổi liên tục theo từng event.
- Không chứa thông tin nhận dạng hoặc dữ liệu nhạy cảm.

Không nên dùng `orderId`, email, customer ID, UUID, request ID hoặc payload làm metric tag. Những giá trị đó có thể khác nhau ở gần như mỗi event và khiến số time series tăng nhanh.
## 7. Kiểm thử event publication bằng PublishedEvents

`PublishedEvents` và event publication metrics kiểm tra hai khía cạnh khác nhau. `PublishedEvents` xác minh event nghiệp vụ có được phát ra hay không; MeterRegistry xác minh counter observability có tăng hay không.

Ví dụ dùng `@ApplicationModuleTest`:

```java
package com.acme.shop.order;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderModuleEventTests {

    @Autowired
    OrderManagement orderManagement;

    @Test
    void publishesOrderCompleted(PublishedEvents events) {

        orderManagement.complete(UUID.randomUUID(), SalesChannel.WEB);

        assertThat(events.ofType(OrderCompleted.class))
                .hasSize(1);
    }
}
```

Đây là module test tập trung vào event publication. Nó không tự xác minh metric counter. Nếu muốn kiểm tra cả hai trong cùng test, cần cấu hình observability và inject MeterRegistry; với bài kiểm thử metrics, full application context thường thuận tiện hơn để bảo đảm instrumentation được auto-configure.

## 8. Xác minh qua Actuator và Prometheus

### 8.1. Expose metrics endpoint

Để kiểm tra trực tiếp trên môi trường chạy, expose endpoint metrics và Prometheus:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus"
```

Trong production, chỉ expose endpoint theo chính sách bảo mật của hệ thống. Không mở management endpoint công khai chỉ để kiểm tra metric.

### 8.2. Đọc aggregate counter qua Actuator

Gọi endpoint:

```bash
curl "http://localhost:8080/actuator/metrics/module.events.published"
```

Có thể lọc theo module và event type:

```bash
curl "http://localhost:8080/actuator/metrics/module.events.published?tag=module.identifier:order&tag=module.event.type:OrderCompleted"
```

Response metrics endpoint thường chứa:
- Tên metric.
- Measurement có statistic `COUNT`.
- Giá trị counter.
- Danh sách available tags và các giá trị có thể lọc.

Để xem counter riêng của event, dùng tên metric tương ứng:

```bash
curl "http://localhost:8080/actuator/metrics/module.events.published.order.OrderCompleted"
```

Nếu endpoint trả 404, hãy kiểm tra observability support, tên metric thực tế và registry đã đăng ký meter hay chưa.

### 8.3. Kiểm tra Prometheus exposition

Khi dùng Prometheus registry, endpoint `/actuator/prometheus` xuất metric theo tên và tag đã được chuẩn hóa. Ví dụ aggregate counter có dạng gần như sau:

```text
module_events_published_total{
  module_identifier="order",
  module_name="Order",
  module_event_type="OrderCompleted"
} 1.0
```

Micrometer chuyển dấu chấm trong tên metric/tag thành định dạng phù hợp với Prometheus. Hãy kiểm tra output thật của phiên bản registry đang dùng trước khi viết PromQL hoặc alert rule.

## 9. Kiểm thử khi listener bất đồng bộ

Một module có thể publish event và module khác xử lý bằng `@ApplicationModuleListener`. Listener thường được xử lý theo cơ chế transactional/asynchronous của Spring Modulith.

Điều cần nhớ:
- Event publication metric đếm event được publish.
- Listener có thể bắt đầu hoặc hoàn tất sau thời điểm counter đã tăng.
- Không chờ listener hoàn thành chỉ để assert counter publication.
- Nếu test side effect của listener, cần đợi điều kiện xử lý thực tế bằng cơ chế đồng bộ phù hợp như Awaitility hoặc Scenario API.
- Nếu listener thất bại, counter publication không biến thành counter failure tự động.

Ví dụ: order publish `OrderCompleted` và inventory xử lý cập nhật tồn kho. Counter của order tăng khi event được publish. Để xác minh tồn kho đã cập nhật, cần assert trạng thái tồn kho hoặc publication status; không suy luận từ counter.

### 9.1. Kiểm tra Event Publication Registry riêng biệt

Với transactional listener, Event Publication Registry lưu publication theo listener và theo dõi lifecycle. Trong Spring Modulith 2.x, trạng thái có thể gồm:

| Status | Ý nghĩa |
| --- | --- |
| `PUBLISHED` | Đã ghi nhận publication và đang chờ xử lý |
| `PROCESSING` | Listener đã nhận publication và đang chạy |
| `COMPLETED` | Listener hoàn tất thành công |
| `FAILED` | Listener thất bại hoặc publication bị đánh dấu stale |
| `RESUBMITTED` | Publication lỗi đã được gửi lại |
| `ABANDONED` | Chính sách quyết định dừng retry (từ 2.2) |

Nếu mục tiêu là kiểm tra listener hoàn tất, hãy dùng Event Publication Registry API phù hợp và cấu hình persistence cần thiết. Metric counter không thể thay thế kiểm tra trạng thái này. Với JDBC hoặc JPA, Spring Modulith có các starter persistence tương ứng như `spring-modulith-starter-jdbc` và `spring-modulith-starter-jpa`. Hạ tầng lưu publication này chỉ cần khi muốn kiểm tra/recover lifecycle; bài test counter metrics không cần dựng publication store.

## 10. Các tình huống kiểm thử nên có

| Trường hợp | Hành động | Kỳ vọng |
| --- | --- | --- |
| Một event được publish | Gọi service publish một event | Aggregate và per-event counter tăng 1 |
| Hai event cùng loại | Publish hai instance cùng event type | Counter tương ứng tăng 2 |
| Hai event type khác nhau | Publish hai loại event | Aggregate counter tăng cho từng event; per-event counter tách biệt |
| Hai module publish event | Gọi service ở hai module | Tag module identifier phân biệt nguồn phát |
| Custom tag hợp lệ | Publish event có channel WEB | Per-event counter có tag `sales_channel=WEB` |
| Listener chạy async | Publish event có listener async | Publication counter tăng; listener completion được kiểm tra riêng |
| Listener thất bại | Cố ý làm listener ném exception | Counter publication vẫn phản ánh event đã phát; registry status phản ánh lỗi |
| Không bật observability | Chạy context thiếu observability support | Không có Modulith event counter; test cấu hình phải phát hiện |
| Counter đã có từ test trước | Dùng chung context/registry | So sánh delta, cô lập test và kiểm tra call path |

Không phải mọi ứng dụng đều cần toàn bộ các case trên. Chọn những case phản ánh luồng event quan trọng và quy ước tag của hệ thống.

## 11. Troubleshooting khi metric không xuất hiện

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không có `module.events.published` | Thiếu observability core/Insight hoặc MeterRegistry | Kiểm tra dependency runtime và registry bean |
| Có metric nhưng không có module tag như mong đợi | Event được publish ngoài module context hoặc module detection không nhận package | Publish qua Spring bean thuộc module và kiểm tra package/module arrangement |
| Có aggregate metric nhưng thiếu per-event metric | Đang truy vấn sai tên event hoặc sai technical module identifier | Kiểm tra simple event type name và meter names đã đăng ký |
| Counter không tăng trong test | Test không gọi service publish event hoặc dùng registry khác | Inject service thật và đúng MeterRegistry trong application context |
| Counter tăng nhiều hơn kỳ vọng | Test context dùng chung, test khác cũng publish cùng event, hoặc nghiệp vụ publish nhiều lần | So sánh delta, cô lập test và kiểm tra call path |
| Custom tag không xuất hiện | Thiếu observability API compile dependency hoặc customizer không được đăng ký | Kiểm tra bean và `spring-modulith-observability-api` |
| Custom tag xuất hiện trên sai meter | Đang kiểm tra aggregate metric thay vì individual event metric | Kiểm tra counter riêng theo module/event type |
| Prometheus endpoint không có metric | Endpoint chưa expose hoặc registry không phải Prometheus | Kiểm tra `management.endpoints.web.exposure.include` và registry |
| Prometheus metric name khác | Micrometer chuẩn hóa tên meter/tag | Kiểm tra raw `/actuator/prometheus` output |
| Metric tăng nhưng listener chưa xử lý xong | Metric đếm publication, không đếm listener completion | Kiểm tra listener và Event Publication Registry |
| Metric có cardinality quá cao | Customizer thêm order ID/customer ID hoặc dữ liệu động | Loại bỏ high-cardinality tags, dùng enum/category hữu hạn |

### Thứ tự debug đề xuất

1. Xác nhận ứng dụng đã bật Spring Modulith observability.
2. Xác nhận MeterRegistry được Spring Boot quản lý.
3. Gọi service thực tế để publish event trong module.
4. Kiểm tra tên metric tổng hợp và metric riêng theo event.
5. Kiểm tra tags mặc định: module identifier, module name và event type.
6. Kiểm tra customizer bean nếu dùng custom tags.
7. Kiểm tra Actuator endpoint và Prometheus exposition.
8. Nếu cần biết listener có thành công không, kiểm tra publication registry riêng.

## 12. Quy tắc để test metrics ổn định

- Dùng integration test với application context thật khi xác minh auto-configuration.
- Gọi service nghiệp vụ thuộc module để tạo event.
- Dùng counter delta để tránh phụ thuộc trạng thái registry từ test khác.
- Không dùng thời gian chờ cố định để kiểm tra publication counter nếu event publish diễn ra đồng bộ.
- Nếu listener bất đồng bộ, chờ side effect của listener bằng điều kiện rõ ràng; không dùng metric publication làm tín hiệu hoàn tất.
- Dùng module identifier và event type ổn định trong truy vấn.
- Chỉ thêm custom tags có tập giá trị giới hạn.
- Tránh reset MeterRegistry toàn cục trong test chạy song song.
- Tách test publication metric khỏi test Event Publication Registry lifecycle.
- Kiểm tra output Prometheus thực tế trước khi viết query/dashboard phụ thuộc vào tên đã chuẩn hóa.

## 13. Bài tập thực hành

Ứng dụng bán hàng có module `order` và `inventory`. Module order publish `OrderCompleted` sau khi đơn hàng được hoàn tất. Module inventory nhận event qua `@ApplicationModuleListener` để cập nhật tồn kho. Dashboard cần hiển thị tổng số event và số event theo sales channel.

**Yêu cầu**

1. Khai báo dependency để bật Spring Modulith event metrics.
2. Viết integration test xác minh aggregate counter `module.events.published` tăng sau khi gọi `OrderManagement.complete`.
3. Xác minh counter riêng `module.events.published.order.OrderCompleted` tăng đúng một.
4. Tạo `ModulithEventMetricsCustomizer` thêm tag `sales_channel` từ enum.
5. Viết assertion cho counter riêng với tag `sales_channel=WEB`.
6. Giải thích vì sao không thêm `orderId` vào metric tag.
7. Giải thích vì sao publication metric tăng không chứng minh inventory listener đã hoàn thành.
8. Nêu cách kiểm tra trạng thái listener bằng Event Publication Registry.

**Gợi ý đáp án**

- Dùng Spring Modulith Insight starter hoặc observability core runtime; dùng BOM tương thích Spring Boot.
- Inject MeterRegistry trong `@SpringBootTest` và so sánh giá trị counter trước/sau khi publish.
- Dùng tên counter riêng ghép từ module identifier và simple event type name.
- Customizer thêm tag từ enum có tập giá trị hữu hạn; customizer API cần artifact `spring-modulith-observability-api` ở compile scope.
- `orderId` có cardinality cao, không phù hợp làm metric label.
- Counter đo event publication; listener completion cần kiểm tra trạng thái publication hoặc side effect.
- Dùng Event Publication Registry để kiểm tra `PUBLISHED`, `PROCESSING`, `COMPLETED`, `FAILED` và trạng thái liên quan.

## 14. Ghi nhớ

**Kiểm thử event publication metric là kiểm tra counter tăng đúng khi module publish domain event.** Spring Modulith cung cấp counter tổng hợp `module.events.published` và counter riêng theo module/event type. Aggregate counter có tags event type, module identifier và module name; counter riêng có module identifier và module name. `ModulithEventMetricsCustomizer` cho phép bổ sung tags cho individual event metrics.

Hãy dùng integration test với MeterRegistry thật của application context, gọi service thuộc module để publish event, rồi so sánh counter trước và sau. Kiểm tra custom tags với giá trị cardinality thấp. Phân biệt rõ publication metric với Event Publication Registry: metric đếm event đã phát, còn registry theo dõi trạng thái xử lý của từng transactional listener. Nhờ đó, test xác minh đúng tín hiệu cần quan sát và dashboard không diễn giải nhầm publication thành xử lý thành công.

## Tài liệu tham khảo

1. [Spring Modulith – Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): event publication counters, tags mặc định và ModulithEventMetricsCustomizer.
2. [Spring Modulith – ModulithEventMetrics API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetrics.html): tùy chỉnh Counter.Builder theo event type.
3. [Spring Modulith – ModulithEventMetricsCustomizer API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html): contract của customizer bean.
4. [Spring Modulith – ModulithMetrics API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithMetrics.html): định nghĩa aggregate event metric và low-cardinality keys.
5. [Spring Modulith – Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event publication, ApplicationModuleListener, Event Publication Registry và lifecycle.
6. [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): MeterRegistry, Actuator metrics endpoint và registry integrations.
7. [Spring Modulith – Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `PublishedEvents` và kiểm thử theo application module.
