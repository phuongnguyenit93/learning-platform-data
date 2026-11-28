# Kiểm thử custom event metric

## 1. Mục tiêu: xác nhận event metric phản ánh đúng dữ liệu nghiệp vụ

Trong ứng dụng Spring Boot sử dụng **Spring Modulith**, module `order` có thể publish event `OrderPlaced`. Spring Modulith tự ghi nhận số event được publish bằng Micrometer counter. Khi cần phân tích sâu hơn, ứng dụng có thể bổ sung tag như `sales.channel` để dashboard phân biệt event đến từ kênh `WEB`, `MOBILE` hoặc `PARTNER`.

Một custom event metric chỉ có giá trị khi kiểm thử chứng minh được ba điều:

1. **Customizer được nạp vào ApplicationContext** và được áp dụng cho đúng event type.
2. **Counter tăng khi event được publish**, đồng thời mang tag tùy chỉnh có giá trị mong đợi.
3. **Tag không làm bùng nổ cardinality** hoặc đưa dữ liệu nhạy cảm vào hệ thống metrics.

Bài thuộc chương **Kiểm thử** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module học này dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot thông qua module graph, Actuator, event metrics, tracing và context propagation. Chủ đề trực tiếp là **kiểm thử custom event metric**: cấu hình `ModulithEventMetricsCustomizer`, phát event trong test, đọc counter từ `MeterRegistry`, xác nhận tag và giá trị, kiểm tra các trường hợp sai cấu hình và tích hợp vào CI.

Sau bài học, bạn có thể:

- Phân biệt metric publication mặc định với tag do ứng dụng bổ sung.
- Cấu hình `ModulithEventMetricsCustomizer` cho một event type.
- Dùng `@SpringBootTest` và `MeterRegistry` để kiểm tra counter thực tế.
- Kiểm tra event khác nhau tạo series đúng theo tag hữu hạn.
- Tránh gọi nhầm event publish counter là listener handling counter.
- Giữ test độc lập với Prometheus, OTLP hoặc monitoring backend bên ngoài.

## 2. Spring Modulith tạo những event metric nào?

Khi bật Spring Modulith observability, framework đăng ký hai dạng counter cho domain events:

| Metric | Ý nghĩa |
| --- | --- |
| `module.events.published` | Counter tổng hợp số event được publish trong ứng dụng. |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter riêng cho event type, có thể được bổ sung tag theo dữ liệu của event. |

Counter tổng hợp có các low-cardinality tags mặc định:

| Tag | Ý nghĩa |
| --- | --- |
| `module.event.type` | Loại event được publish. |
| `module.identifier` | Identifier của module nguồn. |
| `module.name` | Tên hiển thị của module nguồn. |

Counter riêng theo event type có `module.identifier` và `module.name`. `ModulithEventMetricsCustomizer` cho phép thêm tag vào counter riêng đó. Ví dụ, event `OrderPlaced` có thể bổ sung tag `sales.channel=WEB`.

**Phân biệt:** counter này ghi nhận event đã được publish. Nó không xác nhận listener đã chạy xong, transaction listener đã commit hoặc tác vụ nghiệp vụ đã hoàn thành. Muốn kiểm thử xử lý listener, cần kiểm thử kết quả listener hoặc Event Publication Registry riêng.

## 3. Chuẩn bị dependency cho observability và test

Ví dụ dưới đây dùng **Spring Modulith 2.2.x** và **Spring Boot 4.2.x**. Quản lý phiên bản bằng Spring Boot plugin/dependency management và Spring Modulith BOM tương thích; không ghim các module Modulith vào những version khác nhau.

~~~groovy
dependencies {
    // Actuator + Spring Modulith observability support.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Compile-time API để khai báo ModulithEventMetricsCustomizer.
    implementation 'org.springframework.modulith:spring-modulith-observability-api'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-micrometer-metrics-test'
    testImplementation 'org.springframework.boot:spring-boot-resttestclient'
}
~~~

`spring-modulith-starter-insight` đưa Actuator và observability core vào runtime. Vì class cấu hình của ứng dụng tham chiếu `ModulithEventMetricsCustomizer`, cần `spring-modulith-observability-api` ở compile scope. `spring-boot-micrometer-metrics-test` cung cấp test auto-configuration cho `MeterRegistry` trong Spring Boot 4.x.

Dependency `spring-boot-resttestclient` chỉ cần nếu bạn thực hiện phần kiểm thử HTTP Actuator ở mục 10; test counter qua `MeterRegistry` không cần client này.

Nếu dự án không dùng Insight starter, có thể khai báo `spring-modulith-observability-core` ở runtime cùng `spring-modulith-observability-api` ở compile scope; vẫn cần cấu hình Actuator/Micrometer phù hợp với ứng dụng.

## 4. Tạo event type có thuộc tính dùng làm metric tag

Giả sử package arrangement của ứng dụng như sau:

~~~text
com.example.shop
├── ShopApplication.java
├── order
│   ├── OrderPlaced.java
│   └── SalesChannel.java
└── observability
    └── EventMetricsConfiguration.java
~~~

Application class nằm ở package gốc để Spring Modulith nhận diện module `order`:

~~~java
package com.example.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
}
~~~

Khai báo event và tập giá trị kênh bán hàng:

~~~java
package com.example.shop.order;

public enum SalesChannel {
    WEB,
    MOBILE,
    PARTNER
}
~~~

~~~java
package com.example.shop.order;

public record OrderPlaced(
        String orderId,
        SalesChannel salesChannel) {
}
~~~

`orderId` là dữ liệu định danh từng đơn hàng, có số lượng giá trị gần như không giới hạn. `salesChannel` chỉ có ba giá trị đã định nghĩa, phù hợp hơn để làm metric tag.

## 5. Đăng ký ModulithEventMetricsCustomizer

`ModulithEventMetricsCustomizer` là một Spring bean. Trong callback `customize`, gọi `metrics.customize(EventType.class, BiConsumer)` để sửa `Counter.Builder` cho đúng event type:

~~~java
package com.example.shop.observability;

import com.example.shop.order.OrderPlaced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
class EventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer orderEventMetricsCustomizer() {
        return metrics -> metrics.customize(
                OrderPlaced.class,
                (event, builder) -> {
                    builder.tag("sales.channel", salesChannelTag(event));
                });
    }

    static String salesChannelTag(OrderPlaced event) {
        return event.salesChannel().name();
    }
}
~~~

Customizer chỉ thêm tag `sales.channel` cho counter của `OrderPlaced`. Các event type khác vẫn dùng counter riêng mặc định nếu Spring Modulith nhận diện chúng là domain events.

### 5.1. Chọn đúng overload

`ModulithEventMetrics` cung cấp hai overload:

| Overload | Dùng khi |
| --- | --- |
| `customize(Class<T>, BiConsumer<T, Counter.Builder>)` | Giữ builder mặc định, chỉ thêm tag hoặc mô tả. |
| `customize(Class<T>, Function<T, Counter.Builder>)` | Muốn tự tạo `Counter.Builder`, ví dụ đổi metric name hoặc cấu hình builder theo event. |

Với nhu cầu thêm tag, dùng `BiConsumer` để giữ tên counter và tags mặc định do Spring Modulith tạo. Chỉ dùng `Function` khi thực sự muốn thay đổi cách tạo builder; nếu tự tạo builder, hãy kiểm tra các tags mặc định cần giữ để dashboard không mất khả năng group theo module.

### 5.2. Customizer phải được component scan

Đặt `EventMetricsConfiguration` bên trong package tree được `ShopApplication` scan, hoặc import cấu hình tường minh. Nếu class nằm ngoài vùng scan, ứng dụng vẫn có thể khởi động nhưng tag tùy chỉnh không xuất hiện trong registry.

Không khai báo customizer trong test-only configuration nếu mục tiêu là xác minh cấu hình production. Test nên nạp bean cấu hình thật từ `src/main`.

## 6. Viết integration test bằng Spring Boot và MeterRegistry

Test cần chạy ApplicationContext có Modulith observability và MeterRegistry. Với Spring Boot 4.2:

- `@SpringBootTest` nạp cấu hình ứng dụng thật.
- `@AutoConfigureMetrics(export = false)` bật metrics cho test và không gửi số liệu đến hệ thống bên ngoài.
- `ApplicationEventPublisher` phát event theo cơ chế Spring.
- `MeterRegistry` cho phép đọc counter và tags trực tiếp trong bộ nhớ.

~~~java
package com.example.shop;

import com.example.shop.order.OrderPlaced;
import com.example.shop.order.SalesChannel;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.micrometer.metrics.test.autoconfigure.AutoConfigureMetrics;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@AutoConfigureMetrics(export = false)
class OrderEventMetricIntegrationTests {

    @Autowired
    ApplicationEventPublisher events;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void addsSalesChannelTagToOrderPlacedCounter() {
        double before = countFor(SalesChannel.WEB);

        events.publishEvent(new OrderPlaced("order-1001", SalesChannel.WEB));

        Counter counter = counterFor(OrderPlaced.class, "order", SalesChannel.WEB);

        assertThat(counter).isNotNull();
        assertThat(counter.count()).isEqualTo(before + 1.0);
    }

    private Counter counterFor(
            Class<?> eventType, String moduleIdentifier, SalesChannel channel) {
        return meterRegistry.getMeters().stream()
                .filter(Counter.class::isInstance)
                .map(Counter.class::cast)
                .filter(counter -> counter.getId().getName()
                        .contains(eventType.getSimpleName()))
                .filter(counter -> moduleIdentifier.equals(
                        counter.getId().getTag("module.identifier")))
                .filter(counter -> channel.name().equals(
                        counter.getId().getTag("sales.channel")))
                .findFirst()
                .orElse(null);
    }

    private double countFor(SalesChannel channel) {
        Counter counter = counterFor(OrderPlaced.class, "order", channel);
        return counter == null ? 0.0 : counter.count();
    }
}
~~~

Theo tài liệu Spring Modulith, counter riêng được đặt tên theo module identifier và simple event type name. Helper trong test tìm meter bằng event type, tag `module.identifier` và tag tùy chỉnh trong Meter.Id để tránh phụ thuộc cứng vào quy tắc đặt tên của một phiên bản cụ thể. Nếu application module có identifier tùy chỉnh, hãy dùng identifier thực tế.

### Vì sao lấy giá trị trước khi publish?

Spring Test có thể tái sử dụng ApplicationContext giữa các test method. Registry vì vậy có thể giữ counter từ lần test trước. Đọc `before`, publish event rồi so sánh `before + 1` giúp test không phụ thuộc counter đã được tạo trước đó hay chưa.

### Vì sao không gọi Prometheus hoặc OTLP?

Test này xác minh logic tạo counter và gắn tag. `MeterRegistry` là điểm kiểm tra gần nhất với instrumentation. Exporter, network, credentials và backend ingest thuộc một lớp kiểm thử khác; không cần khởi chạy chúng để xác nhận customizer.

## 7. Kiểm tra nhiều tag value tạo đúng series

Một custom tag có ích khi cùng một event type được phân nhóm theo các giá trị hữu hạn. Bổ sung test để xác nhận `WEB` và `MOBILE` tạo hai series riêng:

~~~java
@Test
void createsSeparateSeriesForSalesChannels() {
    double webBefore = countFor(SalesChannel.WEB);
    double mobileBefore = countFor(SalesChannel.MOBILE);

    events.publishEvent(new OrderPlaced("order-2001", SalesChannel.WEB));
    events.publishEvent(new OrderPlaced("order-2002", SalesChannel.MOBILE));

    assertThat(countFor(SalesChannel.WEB)).isEqualTo(webBefore + 1.0);
    assertThat(countFor(SalesChannel.MOBILE)).isEqualTo(mobileBefore + 1.0);
}
~~~

Kết quả mong đợi:

| Metric name | Tag `sales.channel` | Mức tăng |
| --- | --- | ---: |
| `module.events.published.order.OrderPlaced` | `WEB` | +1 |
| `module.events.published.order.OrderPlaced` | `MOBILE` | +1 |

Counter cùng tên có thể có nhiều series khác nhau do bộ tags khác nhau. Điều đó là hành vi mong đợi của Micrometer.

## 8. Xác minh customizer chỉ tác động đến event type đã đăng ký

`ModulithEventMetricsCustomizer` đăng ký customization theo class. Nếu chỉ đăng ký `OrderPlaced.class`, tag `sales.channel` không nên xuất hiện trên counter của event type khác.

Ví dụ thêm event khác:

~~~java
package com.example.shop.payment;

public record PaymentCaptured(String paymentMethod) {
}
~~~

Có thể kiểm tra counter mặc định của event này không mang tag `sales.channel`:

~~~java
import com.example.shop.payment.PaymentCaptured;

@Test
void doesNotAddOrderTagToOtherEventTypes() {
    events.publishEvent(new PaymentCaptured("CARD"));

    boolean hasSalesChannelTag = meterRegistry.getMeters().stream()
            .filter(Counter.class::isInstance)
            .map(Counter.class::cast)
            .filter(counter -> counter.getId().getName().contains("PaymentCaptured"))
            .filter(counter -> "payment".equals(
                    counter.getId().getTag("module.identifier")))
            .anyMatch(counter -> counter.getId().getTag("sales.channel") != null);

    assertThat(hasSalesChannelTag).isFalse();
}
~~~

Ví dụ giả định `PaymentCaptured` thuộc module `payment` và không có customizer khác gắn tag `sales.channel`. Trong dự án thật, cần tính đến các customizer khác đang được đăng ký cho cùng event type.

Test này giúp phát hiện cấu hình quá rộng, ví dụ vô tình thêm tag cho mọi counter hoặc dùng sai event class trong `customize(...)`.

## 9. Kiểm tra metric tổng hợp và metric theo event type

Spring Modulith tạo counter tổng `module.events.published` bên cạnh counter riêng cho từng event. Customizer theo event type bổ sung tag cho counter riêng; không nên giả định tag nghiệp vụ cũng xuất hiện trong counter tổng hợp.

Một test có thể xác nhận hai cấp metric:

1. Counter tổng hợp tăng khi event được publish.
2. Counter riêng theo event type tăng và có tag `sales.channel`.

Với counter tổng hợp, query theo tên metric và tags mặc định:

~~~java
Counter allEvents = meterRegistry.find("module.events.published")
        .tag("module.identifier", "order")
        .tag("module.event.type", OrderPlaced.class.getName())
        .counter();
~~~

Tên/giá trị `module.event.type` phụ thuộc convention và phiên bản; hãy kiểm tra `Meter.Id` thực tế trong test trước khi cố định assertion. Không suy ra giá trị label từ tên simple class nếu chưa xác minh.

## 10. Kiểm thử bằng Actuator metrics endpoint

Nếu muốn xác minh metric có thể được đọc qua Actuator, expose `metrics` trong profile test:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Với `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `@AutoConfigureMetrics(export = false)`, có thể gọi endpoint metrics để kiểm tra tên meter:

~~~java
import com.example.shop.order.OrderPlaced;
import com.example.shop.order.SalesChannel;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.micrometer.metrics.test.autoconfigure.AutoConfigureMetrics;
import org.springframework.boot.resttestclient.autoconfigure.AutoConfigureRestTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.test.web.servlet.client.RestTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureMetrics(export = false)
@AutoConfigureRestTestClient
class ActuatorEventMetricTests {

    @Autowired
    ApplicationEventPublisher events;

    @Autowired
    RestTestClient restTestClient;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void exposesEventCounterThroughActuator() {
        events.publishEvent(new OrderPlaced("order-3001", SalesChannel.PARTNER));

        Counter counter = meterRegistry.getMeters().stream()
                .filter(Counter.class::isInstance)
                .map(Counter.class::cast)
                .filter(meter -> meter.getId().getName().contains("OrderPlaced"))
                .filter(meter -> "order".equals(
                        meter.getId().getTag("module.identifier")))
                .filter(meter -> "PARTNER".equals(
                        meter.getId().getTag("sales.channel")))
                .findFirst()
                .orElseThrow();

        restTestClient.get()
                .uri("/actuator/metrics/{name}", counter.getId().getName())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name")
                .isEqualTo(counter.getId().getName());
    }
}
~~~

Đây là test lớp HTTP bổ sung. Nếu chỉ cần kiểm tra logic customizer, đọc `MeterRegistry` trực tiếp sẽ nhanh và ít phụ thuộc cấu hình web hơn. Nếu dự án có Spring Security, cấu hình quyền cho endpoint metrics trong test hoặc dùng một security test configuration phù hợp.

## 11. Spring Boot 3.5 và Spring Boot 4.x

Tên/package test annotation thay đổi giữa các dòng Spring Boot:

| Phiên bản | Cách bật observability metrics trong test |
| --- | --- |
| Spring Boot 4.0–4.2 | `@AutoConfigureMetrics` từ `org.springframework.boot.micrometer.metrics.test.autoconfigure`, dependency `spring-boot-micrometer-metrics-test`. |
| Spring Boot 3.5 | `@AutoConfigureObservability` từ `org.springframework.boot.test.autoconfigure.actuate.observability`, dependency test auto-configuration tương ứng của Boot 3.x. |

Không copy import `@AutoConfigureMetrics` của Boot 4.x vào dự án Boot 3.5. Hãy dùng annotation thuộc đúng BOM/major version của dự án. Cách đọc `MeterRegistry`, publish event và assert counter vẫn theo cùng nguyên tắc.

## 12. Unit test riêng cho phần customization

Integration test xác nhận cả Spring context, event publication và counter. Trong trường hợp muốn kiểm tra nhanh logic chuyển thuộc tính event thành tag, có thể viết unit test cho một hàm thuần:

~~~java
package com.example.shop.observability;

import com.example.shop.order.OrderPlaced;
import com.example.shop.order.SalesChannel;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class EventMetricsConfigurationTests {

    @Test
    void mapsSalesChannelToStableTagValue() {
        OrderPlaced event = new OrderPlaced("order-4001", SalesChannel.WEB);

        assertThat(EventMetricsConfiguration.salesChannelTag(event))
                .isEqualTo("WEB");
    }
}
~~~

Unit test này chỉ kiểm tra mapping. Nó **không** chứng minh `ModulithEventMetricsCustomizer` đã được Spring nạp hoặc counter đã tăng. Vì vậy, giữ ít nhất một integration test dùng `MeterRegistry` cho mỗi custom metric quan trọng.

## 13. Khi event listener bất đồng bộ, kiểm thử điều gì riêng?

Event publication counter được tăng ở mốc publish. Nếu event được xử lý bằng `@ApplicationModuleListener`, listener có thể chạy bất đồng bộ và hoàn tất sau đó. Hai mốc cần test riêng:

| Mục tiêu | Cách kiểm thử |
| --- | --- |
| Event đã publish và metric tăng | Publish event rồi đọc `module.events.published...` từ `MeterRegistry`. |
| Listener thực sự xử lý event | Dùng `@ApplicationModuleTest` và `Scenario`, chờ state/event đầu ra hoặc kiểm tra persistence. |
| Publication hoàn tất hoặc thất bại | Kiểm tra Event Publication Registry nếu ứng dụng đã cấu hình registry/persistence. |

Spring Modulith `Scenario` hỗ trợ mô tả stimulus, chờ outcome và xác nhận kết quả cho các luồng event bất đồng bộ. Không dùng việc counter tăng làm bằng chứng listener đã xử lý thành công.

## 14. Kiểm tra cardinality và dữ liệu nhạy cảm

Metric tag tạo thêm một time series cho mỗi tổ hợp tag. Nếu customizer đưa `orderId`, `customerId`, email hoặc trace ID vào tag, số series có thể tăng nhanh, làm tăng RAM, chi phí lưu trữ và thời gian truy vấn. Dữ liệu đó còn có thể bị sao chép tới nhiều hệ thống metrics.

Nên dùng:

- Enum hoặc tập giá trị nhỏ như `sales.channel`.
- Outcome hữu hạn như `accepted`, `rejected`, `retryable`.
- Module identifier hoặc event type đã được chuẩn hóa.

Tránh dùng:

- `order.id`, `customer.id`, `payment.reference`.
- Email, số điện thoại, token hoặc dữ liệu cá nhân.
- `traceId`, `spanId`, request ID hoặc timestamp chính xác.

Một test có thể khóa tập giá trị được phép:

~~~java
@Test
void salesChannelHasOnlySupportedValues() {
    assertThat(SalesChannel.values())
            .containsExactly(
                    SalesChannel.WEB,
                    SalesChannel.MOBILE,
                    SalesChannel.PARTNER);
}
~~~

Test enum không thay thế review cardinality của toàn bộ labels, nhưng giúp ngăn thay đổi vô tình làm tag có vô số giá trị.

## 15. Các lỗi thường gặp khi test custom event metric

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `ModulithEventMetricsCustomizer` | Thiếu `spring-modulith-observability-api` ở compile scope. | Thêm API artifact và đồng bộ version bằng BOM. |
| Counter không xuất hiện | Thiếu observability core/Insight starter hoặc event type không thuộc module được phát hiện. | Kiểm tra runtime dependency và package arrangement. |
| Counter có nhưng thiếu tag custom | Bean customizer không được scan hoặc class trong `customize(...)` không trùng event type. | Kiểm tra component scan và event class chính xác. |
| Test không inject được `MeterRegistry` | Test metrics auto-configuration chưa bật hoặc dependency test thiếu. | Dùng `@AutoConfigureMetrics` (Boot 4.x) hoặc annotation tương ứng (Boot 3.5). |
| Counter tăng nhiều hơn mong đợi | ApplicationContext được cache và counter giữ giá trị giữa test; test khác cũng publish cùng event. | So sánh delta trước/sau publish thay vì luôn assert bằng 1. |
| Counter name không khớp | Module identifier khác tên package dự kiến hoặc event simple name khác. | Kiểm tra module identifier và tên meter thực tế. |
| Prometheus không thấy tên giống test | Prometheus registry chuẩn hóa dấu chấm thành dấu gạch dưới và có thể thêm hậu tố `_total`. | Dùng tên Micrometer trong test; kiểm tra exposition format ở endpoint Prometheus. |
| Tag chứa quá nhiều giá trị | Dùng ID hoặc dữ liệu tự do làm label. | Chuyển sang enum/nhóm giá trị hữu hạn; giữ ID trong logs/traces. |
| Test chỉ pass khi chạy riêng | Test dùng global registry hoặc trạng thái static bị chia sẻ. | Ưu tiên inject `MeterRegistry`; không phụ thuộc global registry nếu không cần. |
| Event metric tăng nhưng listener chưa xong | Đang kiểm thử publish counter thay cho listener completion. | Kiểm tra listener outcome/Scenario hoặc Event Publication Registry riêng. |
| Counter tổng có tag nhưng counter event-specific không có | Customizer áp dụng nhầm metric hoặc test đang truy vấn sai meter. | Đọc đúng counter theo module identifier và event type. |

## 16. Test hygiene và CI

Để test ổn định trong CI:

1. Dùng registry trong bộ nhớ, không gửi metric tới Prometheus/OTLP thật.
2. Inject `MeterRegistry` thay vì truy cập `Metrics.globalRegistry`.
3. Đọc counter trước khi publish và assert delta sau publish để tránh phụ thuộc thứ tự test.
4. Dùng event type top-level và module package rõ ràng để metric name dễ xác định.
5. Dùng tag value hữu hạn, không đưa dữ liệu test duy nhất như order ID vào label.
6. Giữ customizer trong production source; test chỉ phát event và kiểm tra kết quả.
7. Nếu test listener bất đồng bộ, chờ outcome bằng `Scenario`/Awaitility thay vì sleep cố định.
8. Chạy test theo cùng dependency management/BOM với ứng dụng; tránh trộn Spring Boot và Spring Modulith khác major line.

Không cần khởi chạy monitoring backend để kiểm tra customizer. Một test integration với ApplicationContext và in-memory `MeterRegistry` thường đủ để xác nhận việc tạo counter và tag.

## 17. Quy trình kiểm thử từ cấu hình đến metric

~~~mermaid
flowchart TD
    A["Load Spring Boot test context"] --> B["Register ModulithEventMetricsCustomizer"]
    B --> C["Publish OrderPlaced"]
    C --> D["Spring Modulith creates event counter"]
    D --> E["Customizer adds sales.channel tag"]
    E --> F["MeterRegistry stores counter"]
    F --> G["Assert counter delta and tag"]
    G --> H{"Expected series found?"}
    H -->|No| I["Inspect dependencies, module ID, event type, bean scan"]
    I --> A
    H -->|Yes| J["Run test in CI"]
~~~

Thứ tự kiểm tra khi test fail:

1. ApplicationContext có nạp `EventMetricsConfiguration` không?
2. Runtime có `spring-modulith-observability-core`/Insight và compile có `spring-modulith-observability-api` không?
3. `OrderPlaced` có nằm trong application module được Spring Modulith nhận diện không?
4. Test có publish đúng class event không?
5. `MeterRegistry` có nhận counter mặc định không?
6. Counter riêng có tag `sales.channel` không?
7. Giá trị counter tăng đúng một đơn vị so với trước publish không?

## 18. Checklist hoàn thành

- [ ] Đã bật Spring Modulith observability trong runtime.
- [ ] Đã thêm `spring-modulith-observability-api` ở compile scope.
- [ ] `ModulithEventMetricsCustomizer` được khai báo thành Spring bean.
- [ ] Customizer nhắm đúng event type và chỉ thêm tag cần thiết.
- [ ] Event type nằm trong application module được nhận diện.
- [ ] Test dùng ApplicationContext thật và in-memory `MeterRegistry`.
- [ ] Test xác nhận counter xuất hiện và tăng sau publish.
- [ ] Test xác nhận custom tag có giá trị mong đợi.
- [ ] Test không phụ thuộc counter bắt đầu từ 0.
- [ ] Tag dùng giá trị hữu hạn và không chứa ID/dữ liệu nhạy cảm.
- [ ] Test phân biệt publish counter với listener handling outcome.
- [ ] CI chạy test mà không cần monitoring backend bên ngoài.

## 19. Tài liệu tham khảo chính thức

- **Spring Modulith — Production-ready Features:** https://docs.spring.io/spring-modulith/reference/production-ready.html — observability starter, event publication counters và ví dụ `ModulithEventMetricsCustomizer`.
- **Spring Modulith — ModulithEventMetricsCustomizer API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html — callback để đăng ký customization.
- **Spring Modulith — ModulithEventMetrics API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetrics.html — overload `customize(Class, BiConsumer)` và `customize(Class, Function)`.
- **Spring Boot 4.2 — Testing Spring Boot Applications:** https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html — `@AutoConfigureMetrics`, MeterRegistry trong test và global registry.
- **Spring Boot 4.2 — AutoConfigureMetrics API:** https://docs.spring.io/spring-boot/api/java/org/springframework/boot/micrometer/metrics/test/autoconfigure/AutoConfigureMetrics.html — cấu hình metrics cho test và tắt export ngoài.
- **Spring Boot 3.5 — Testing Spring Boot Applications:** https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html — `@AutoConfigureObservability` cho test metrics ở Boot 3.5.
- **Micrometer — Counters:** https://docs.micrometer.io/micrometer/reference/concepts/counters.html — semantics counter và cách đọc số liệu.
- **Spring Modulith — Integration Testing Application Modules:** https://docs.spring.io/spring-modulith/reference/testing.html — `@ApplicationModuleTest`, `Scenario` và kiểm thử event bất đồng bộ.

## 20. Tổng kết

Kiểm thử custom event metric cần xác nhận **đúng event type, đúng counter, đúng tag và đúng mức tăng**. Spring Modulith cung cấp `module.events.published` và counter riêng theo module/event type; `ModulithEventMetricsCustomizer` bổ sung tag vào builder của counter riêng thông qua `ModulithEventMetrics.customize(...)`.

Một integration test với `@SpringBootTest`, metrics test auto-configuration và `MeterRegistry` trong bộ nhớ có thể phát event rồi xác nhận counter tăng cùng tag `sales.channel` mà không cần monitoring backend. Hãy kiểm tra delta thay vì giả định counter bằng 1, dùng tag có cardinality thấp và giữ riêng test publication metric với test listener completion. Như vậy, custom event metric vừa phản ánh đúng event được phát vừa an toàn để đưa vào dashboard vận hành.
