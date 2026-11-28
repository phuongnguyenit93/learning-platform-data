# Tùy biến tag bằng ModulithEventMetricsCustomizer

## 1. Bài toán và kết quả cần đạt

Đây là bài **Thực hành tổng hợp** trong module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Mục tiêu rộng hơn của module là dùng Spring Modulith để tài liệu hóa ranh giới *application module* và kiểm chứng tương tác giữa các phần của ứng dụng Spring Boot khi hệ thống chạy: từ **module graph** và **Actuator** tới **event metrics**, **tracing** và **context propagation**.

Giả sử ứng dụng bán hàng gồm hai module:

- `orders` nhận yêu cầu đặt hàng và phát sự kiện `OrderSubmitted`.
- `notifications` lắng nghe sự kiện để ghi nhận thông báo đơn hàng.

Nhóm vận hành đã thấy counter `module.events.published`, nhưng muốn trả lời những câu hỏi cụ thể hơn: *Có bao nhiêu sự kiện đặt hàng được phát từ kênh WEB so với MOBILE? Sự kiện phân bố thế nào ở thị trường VN và TH?* Ta sẽ dùng **`ModulithEventMetricsCustomizer`** để thêm hai tag `sales.channel` và `sales.market` vào counter riêng của `OrderSubmitted`.

Sau bài này, bạn có thể:

1. Hiểu hai nhóm counter về event publication được Spring Modulith cung cấp và phạm vi tùy biến.
2. Khai báo đúng bean `ModulithEventMetricsCustomizer` và dùng `ModulithEventMetrics.customize(Class<T>, BiConsumer<T, Counter.Builder>)`.
3. Chọn các giá trị tag có số lượng hữu hạn (*low cardinality*) để không làm nổ số chuỗi thời gian trong hệ thống metrics.
4. Tạo một application module phát event và một module lắng nghe, rồi quan sát tag qua Actuator/Micrometer.
5. Kiểm tra kết quả bằng kịch bản có nhiều tổ hợp tag và giải thích vì sao metric publish không chứng minh consumer đã xử lý thành công.
6. Phân biệt việc gắn tag cho **counter** với việc tùy biến **tracing/Observation**.

**Sản phẩm hoàn thành:** một Spring Boot demo có event đi qua ranh giới module, một bean customizer đúng API Spring Modulith, metric chia theo hai chiều nghiệp vụ, kết quả xác minh và danh sách giới hạn khi triển khai production.

## 2. Hiểu counter mặc định trước khi tùy biến

Từ Spring Modulith **1.4**, observability hỗ trợ các counter về sự kiện domain được publish. Tài liệu mô tả hai nhóm chính:

| Metric | Ý nghĩa | Các tag tích hợp |
| --- | --- | --- |
| `module.events.published` | Counter tổng hợp các event publication | `module.event.type`, `module.identifier`, `module.name` |
| `module.events.published.<moduleIdentifier>.<simpleEventTypeName>` | Counter riêng của từng loại event, ví dụ `module.events.published.orders.OrderSubmitted` | `module.identifier`, `module.name`; có thể thêm tag theo nội dung event |

Counter riêng mới là đối tượng mà `ModulithEventMetricsCustomizer` được thiết kế để mở rộng. Ví dụ, sau khi cấu hình, một số mẫu metric có thể được phân biệt bằng các tag:

~~~text
metric: module.events.published.orders.OrderSubmitted
tags: module.identifier=orders, sales.channel=WEB,    sales.market=VN

metric: module.events.published.orders.OrderSubmitted
tags: module.identifier=orders, sales.channel=MOBILE, sales.market=TH
~~~

Đây là biểu diễn minh họa về **tên và tag**. Trong Micrometer, hai tập tag khác nhau tạo thành hai *meter series* khác nhau, dù phần tên metric giống nhau. Tên metric khi xuất sang Prometheus thường được chuẩn hóa theo naming convention của exporter; kiểm tra đầu ra thực tế thay vì đoán cách chuyển dấu chấm, chữ hoa hoặc hậu tố counter.

**Ba nhận định cần giữ rõ:**

- **Event được publish** là lúc application phát sự kiện theo cơ chế Spring. Số này không xác nhận transaction nguồn đã commit trong mọi tình huống.
- **Event được listener xử lý** là một mốc khác. Listener có thể chạy bất đồng bộ, thất bại hoặc được retry. Publication Registry và outcome nghiệp vụ cần được theo dõi riêng.
- **Tag ở counter riêng của event** không tự động được thêm vào `module.events.published` tổng hợp hoặc mọi span trace. Tracing có cơ chế `ModulithObservationConvention` riêng.

API tham khảo chính thức: [ModulithEventMetricsCustomizer](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html), [ModulithEventMetrics](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithEventMetrics.html).

## 3. Thiết kế tag: hữu hạn, ổn định và có mục đích

Trong bài thực hành, event chứa các giá trị nghiệp vụ:

~~~text
OrderSubmitted(
  eventId,
  orderId,
  channel = WEB | MOBILE | PARTNER,
  market  = VN | TH | OTHER
)
~~~

Ta cần hai tag:

| Tag | Tập giá trị cho phép | Tác dụng |
| --- | --- | --- |
| `sales.channel` | `WEB`, `MOBILE`, `PARTNER` | So sánh nguồn phát sinh đơn |
| `sales.market` | `VN`, `TH`, `OTHER` | So sánh thị trường theo nhóm đã định nghĩa |

Với ba kênh và ba thị trường, số tổ hợp tag nghiệp vụ tối đa cho một loại event là:

\[
3 \times 3 = 9
\]

Với hai instance ứng dụng, có thể quan sát tối đa 18 series riêng theo nhãn instance cho metric đó (chưa tính những nhãn khác của hệ thống). Khi triển khai nhiều module, nhiều event type và nhiều nhãn hạ tầng, tổng số series sẽ tăng theo tích các số lựa chọn.

**Không dùng các trường sau làm tag Micrometer:** `orderId`, `eventId`, email, số điện thoại, user ID, IP tùy ý, URL thô chứa tham số hoặc nội dung exception. Những giá trị này thường có cardinality lớn, khiến hệ thống metrics tiêu tốn nhiều bộ nhớ, thời gian scrape và chi phí lưu trữ. Chúng cũng có thể rò rỉ dữ liệu nhạy cảm.

Một lựa chọn đúng là dùng **enum** hoặc bảng ánh xạ giá trị về nhóm có giới hạn. Nếu nhận chuỗi ngoài từ API, cần chuẩn hóa/whitelist trước khi xây tag; một giá trị lạ nên trở thành `OTHER` hoặc `UNKNOWN` theo hợp đồng giám sát. Giữ **tên tag** cố định; chỉ thay **giá trị** trong tập được cho phép.

## 4. Chuẩn bị project Spring Boot + Spring Modulith

### 4.1. Chọn phiên bản tương thích

Ví dụ theo **Spring Boot 4.2 + Spring Modulith 2.2.0**, dùng Java 21 và Gradle. Các phiên bản khác cần đối chiếu [ma trận tương thích Spring Modulith](https://docs.spring.io/spring-modulith/reference/appendix.html).

Khai báo dependency theo vai trò:

~~~groovy
// build.gradle - phần liên quan của dự án Gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.modulith:spring-modulith-starter-core'

    // Bắt buộc ở compile classpath để source import được SPI customizer.
    implementation 'org.springframework.modulith:spring-modulith-observability-api'

    // Bật Actuator và instrumentation của Spring Modulith ở runtime.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Tùy chọn khi muốn xuất /actuator/prometheus:
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
}
~~~

Ví dụ cấu hình BOM trong Gradle có plugin `io.spring.dependency-management`:

~~~groovy
dependencyManagement {
    imports {
        mavenBom 'org.springframework.modulith:spring-modulith-bom:2.2.0'
    }
}
~~~

Ngoài BOM Modulith, dự án phải dùng Spring Boot plugin/BOM cho **cùng thế hệ**. Các khai báo là trích đoạn để đưa vào build hiện có; không phải một file `build.gradle` hoàn chỉnh tự chạy nếu thiếu plugin, repository hoặc cấu hình Java.

**Tại sao tách hai dependency?** `spring-modulith-starter-insight` được tài liệu khuyến nghị ở runtime để kích hoạt Actuator và observability. Nhưng mã Java cần thấy kiểu `ModulithEventMetricsCustomizer` lúc biên dịch, vì vậy `spring-modulith-observability-api` phải có ở **compile scope**. Chỉ dùng `runtimeOnly` cho cả hai có thể khiến IDE/Gradle báo `cannot find symbol ModulithEventMetricsCustomizer`. Không cần thêm `spring-modulith-actuator` lần nữa khi đã dùng insight starter.

Ở Spring Modulith 1.4, API customizer cũng có nhưng cấu trúc artifact có khác thế hệ 2.x; điều chỉnh dependency theo **đúng tài liệu/Javadoc của phiên bản ứng dụng**, tránh copy nguyên dependency 2.2 sang 1.4.

### 4.2. Cấu hình quan sát qua Actuator

Trong `src/main/resources/application.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,modulith,prometheus

  # Ở môi trường thật, xác thực và giới hạn mạng quản trị phải được cấu hình riêng.
~~~

- `/actuator/metrics` giúp liệt kê và truy vấn meter trong JVM.
- `/actuator/modulith` hiển thị cấu trúc module.
- `/actuator/prometheus` chỉ có khi cấu hình Micrometer Prometheus registry phù hợp.
- Nếu dùng Spring Boot có endpoint access model, cần kiểm tra thêm `management.endpoint.*.access` và giới hạn access toàn cục.

Trong production, endpoint metrics và đặc biệt module graph cần được bảo vệ bằng mạng quản trị/quyền hạn; không mở toàn bộ Actuator hoặc tắt Spring Security chỉ để thực hành. Nếu Actuator chạy trên `management.server.port` riêng, dùng cổng đó khi kiểm tra.

### 4.3. Cấu trúc package minh họa

~~~text
src/main/java/com/example/shop/
├── ShopApplication.java
├── orders/
│   ├── OrderSubmitted.java
│   ├── OrderService.java
│   └── OrderController.java
├── notifications/
│   └── OrderAuditListener.java
└── observability/
    └── ModulithMetricsConfiguration.java
~~~

Với quy tắc mặc định của Spring Modulith, các package con trực tiếp của package ứng dụng là ứng viên application module. Ở đây có `orders`, `notifications` và `observability`. Nếu không muốn config thuần kỹ thuật tạo thành một module riêng trong module graph, có thể đặt `ModulithMetricsConfiguration` trực tiếp trong package ứng dụng gốc `com.example.shop`. **Trong ví dụ tiếp theo, ta chọn cách đặt trong package gốc** để tập trung vào hai module nghiệp vụ.

## 5. Tạo domain event với các thuộc tính có cardinality nhỏ

Đặt event ở **package gốc của module orders**, là phần API công khai theo quy tắc Modulith mặc định. Nếu đặt trong subpackage `orders.internal` thì module khác không nên truy cập trực tiếp; nếu dùng subpackage `orders.api`, cần cấu hình named interface/phạm vi API tương ứng.

~~~java
// src/main/java/com/example/shop/orders/OrderSubmitted.java
package com.example.shop.orders;

import java.util.UUID;

public record OrderSubmitted(
        UUID eventId,
        UUID orderId,
        SalesChannel channel,
        Market market
) {
    public enum SalesChannel {
        WEB, MOBILE, PARTNER
    }

    public enum Market {
        VN, TH, OTHER
    }
}
~~~

Mỗi event có `eventId` và `orderId` phục vụ liên kết log và xử lý idempotent. Ta **không đưa các ID vào tag**. `SalesChannel` và `Market` là enum nên tập giá trị bị giới hạn bởi code và không thay đổi theo từng yêu cầu.

### 5.1. Service phát sự kiện

~~~java
// src/main/java/com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final ApplicationEventPublisher events;

    public OrderService(ApplicationEventPublisher events) {
        this.events = events;
    }

    // Demo không lưu DB, chỉ phát một event để đo metric.
    public UUID submitOrder(OrderSubmitted.SalesChannel channel,
                            OrderSubmitted.Market market) {

        UUID orderId = UUID.randomUUID();

        events.publishEvent(new OrderSubmitted(
            UUID.randomUUID(), orderId, channel, market
        ));

        return orderId;
    }
}
~~~

Đây là ứng dụng mô phỏng, chưa lưu trạng thái đơn hàng. Trong nghiệp vụ thật, thao tác lưu đơn và `publishEvent(...)` thường đặt trong một transaction thích hợp; nếu yêu cầu khôi phục sự kiện sau khi JVM chết, dùng Event Publication Registry/persistence tương ứng. **Đếm publish không đồng nghĩa transaction đã commit**, và không thể dùng counter này như số đơn hàng đã giao thành công.

### 5.2. API để kích hoạt sự kiện

~~~java
// src/main/java/com/example/shop/orders/OrderController.java
package com.example.shop.orders;

import java.util.Map;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {

    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Map<String, String> submit(@RequestBody PlaceOrderRequest request) {
        UUID id = service.submitOrder(request.channel(), request.market());
        return Map.of("orderId", id.toString());
    }

    public record PlaceOrderRequest(
        OrderSubmitted.SalesChannel channel,
        OrderSubmitted.Market market
    ) {}
}
~~~

Trong hệ thống thực, thêm Bean Validation và xử lý giá trị null để trả lỗi 4xx rõ ràng. Ví dụ dùng enum cố định nhằm minh họa metrics, không phải hợp đồng API thương mại hoàn chỉnh.

### 5.3. Listener nằm ở module khác

~~~java
// src/main/java/com/example/shop/notifications/OrderAuditListener.java
package com.example.shop.notifications;

import com.example.shop.orders.OrderSubmitted;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderAuditListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderAuditListener.class);

    @EventListener
    public void on(OrderSubmitted event) {
        log.info("OrderSubmitted observed: eventId={}, orderId={}",
            event.eventId(), event.orderId());
    }
}
~~~

Listener ở `notifications` phụ thuộc vào **API event** của `orders`. Đây là ví dụ đồng bộ để dễ lặp lại bài đo và không cần DB. Khi chuyển sang `@ApplicationModuleListener` cho xử lý bất đồng bộ theo transaction, phải bổ sung transaction gốc, quy trình retry, idempotency và registry theo yêu cầu ứng dụng. Metric published không biến thành metric processed sau khi đổi annotation.

### 5.4. Điểm khởi động

~~~java
// src/main/java/com/example/shop/ShopApplication.java
package com.example.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

## 6. Phần chính: khai báo `ModulithEventMetricsCustomizer`

Đặt cấu hình trong package `com.example.shop` để được component scan và không tạo thêm module ứng dụng thuần kỹ thuật.

~~~java
// src/main/java/com/example/shop/ModulithMetricsConfiguration.java
package com.example.shop;

import com.example.shop.orders.OrderSubmitted;
import java.util.Locale;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration
class ModulithMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer orderSubmittedMetricTags() {

        return metrics -> {
            metrics.customize(OrderSubmitted.class, (event, builder) -> {
                builder.tags(
                    "sales.channel",
                    event.channel().name().toLowerCase(Locale.ROOT),
                    "sales.market",
                    event.market().name().toLowerCase(Locale.ROOT)
                );
            });
        };
    }
}
~~~

**Giải thích chính xác từng phần:**

1. `ModulithEventMetricsCustomizer` là một **functional interface** có phương thức `void customize(ModulithEventMetrics metrics)`. Spring Modulith thu thập các bean kiểu này để cấu hình cách tạo event metrics.
2. `metrics.customize(OrderSubmitted.class, ...)` đăng ký phép tùy biến cho **đúng loại event** `OrderSubmitted`. Event khác không tự nhận hai tag này.
3. Lambda nhận `event` và `builder`. `builder` là `io.micrometer.core.instrument.Counter.Builder` đã được framework tạo cho metric; gọi `builder.tags(...)` để thêm dữ liệu mà không phải tự xây một metric mới.
4. `event.channel()` và `event.market()` được chuyển thành giá trị tag đơn giản, ổn định. `Locale.ROOT` tránh ảnh hưởng của locale máy chủ khi chuyển chữ hoa sang chữ thường.
5. Các tag này áp dụng cho **counter riêng theo loại event** do Spring Modulith tạo. Chúng không tự động làm tăng số event, kích hoạt listener, sửa transaction hoặc thêm tag vào trace.

Tài liệu chính thức dùng cùng mẫu:

~~~java
@Bean
ModulithEventMetricsCustomizer customizer() {
    return metrics -> {
        metrics.customize(MyCustomDomainEvent.class, (event, builder) -> {
            builder.tags("someTag", event.getValue());
        });
    };
}
~~~

Ví dụ trong bài có thay `event.getValue()` bằng hai enum hữu hạn nhằm bảo đảm metric dùng được lâu dài.

### 6.1. Biến thể với nhiều loại event

Một bean customizer có thể đăng ký nhiều rule:

~~~java
@Bean
ModulithEventMetricsCustomizer multipleEventsCustomizer() {
    return metrics -> {
        metrics.customize(OrderSubmitted.class, (event, builder) ->
            builder.tags("sales.channel",
                event.channel().name().toLowerCase(Locale.ROOT)));

        // Ví dụ nếu ứng dụng có thêm một loại event khác:
        // metrics.customize(PaymentReceived.class, (event, builder) ->
        //     builder.tags("payment.method",
        //         event.method().name().toLowerCase(Locale.ROOT)));
    };
}
~~~

**Chú ý:** đây là **biến thể thay thế** cấu hình ở trên, không nên đăng ký thêm như bean thứ hai chỉ để copy ví dụ vì có thể thêm trùng key `sales.channel` hoặc khiến chính sách tag khó kiểm soát. Chọn một nơi chịu trách nhiệm rõ ràng cho từng loại event.

### 6.2. Khi nào cần overload `Function<T, Counter.Builder>`?

`ModulithEventMetrics` còn có overload:

~~~java
<T> ModulithEventMetrics customize(
    Class<T> type,
    java.util.function.Function<T,
        io.micrometer.core.instrument.Counter.Builder> factory
);
~~~

Overload này cho phép tùy biến **cách tạo builder** của counter theo event. Nó mạnh hơn nhưng cũng dễ làm lệch tên metric hoặc các tag framework mặc định nếu bạn tự xây builder mà không bảo toàn hợp đồng. Trong bài thực hành thêm hai tag, hãy dùng overload **`BiConsumer<T, Counter.Builder>`** vì bộ khung metric đã được Spring Modulith chuẩn bị. Chỉ dùng factory khi thật sự cần thiết và có kiểm thử names/tags tương ứng.

## 7. Gửi request và quan sát metric

Khởi động ứng dụng với dependency/configuration ở trên. Với server mặc định `localhost:8080`, gửi một số request (ví dụ PowerShell, dùng `curl.exe` tránh alias `curl`):

~~~powershell
curl.exe -i -X POST "http://localhost:8080/orders" -H "Content-Type: application/json" -d '{"channel":"WEB","market":"VN"}'

curl.exe -i -X POST "http://localhost:8080/orders" -H "Content-Type: application/json" -d '{"channel":"MOBILE","market":"TH"}'

curl.exe -i -X POST "http://localhost:8080/orders" -H "Content-Type: application/json" -d '{"channel":"WEB","market":"VN"}'

curl.exe -i -X POST "http://localhost:8080/orders" -H "Content-Type: application/json" -d '{"channel":"PARTNER","market":"OTHER"}'
~~~

Với Windows PowerShell 5.1, nếu bị lỗi quote body JSON ở `curl.exe`, có thể dùng lệnh PowerShell gốc:

~~~powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8080/orders" -ContentType "application/json" -Body '{"channel":"WEB","market":"VN"}'
~~~

Các request trên làm `OrderService` phát **bốn** event `OrderSubmitted` với ba tổ hợp tag. Nếu chưa có request nào được xử lý, metric có thể chưa xuất hiện vì counter được tạo/đăng ký khi event được phát.

### 7.1. Xem danh sách meter

~~~powershell
curl.exe -i "http://localhost:8080/actuator/metrics"
~~~

Tìm tên metric phù hợp. Theo quy ước trong tài liệu, metric riêng của event ví dụ có thể là:

~~~text
module.events.published.orders.OrderSubmitted
~~~

Khi truy vấn:

~~~powershell
curl.exe -i "http://localhost:8080/actuator/metrics/module.events.published.orders.OrderSubmitted"
~~~

Trong kết quả `availableTags`, tìm các cặp `sales.channel` / `sales.market`. Nếu tên được cấu hình/naming strategy của hệ thống biến đổi, lấy **tên thực tế** từ `GET /actuator/metrics` thay vì hardcode tên này.

Ví dụ JSON **minh họa hình dạng dữ liệu**, không phải snapshot từ ứng dụng đang chạy:

~~~json
{
  "name": "module.events.published.orders.OrderSubmitted",
  "measurements": [{"statistic": "COUNT", "value": 4.0}],
  "availableTags": [
    {"tag": "sales.channel", "values": ["web", "mobile", "partner"]},
    {"tag": "sales.market", "values": ["vn", "th", "other"]},
    {"tag": "module.identifier", "values": ["orders"]}
  ]
}
~~~

Ở một JVM mới khởi động và chỉ chạy bốn request ví dụ, giá trị đếm tổng **có thể** là 4. Trên hệ thống đã nhận các request khác hoặc có nhiều instance, số này sẽ khác. `availableTags` cho biết tập giá trị đã quan sát, **không nói có bao nhiêu event cho từng tổ hợp tag**.

### 7.2. Lọc theo tag để kiểm tra đúng kết quả

Actuator metrics API hỗ trợ query parameter `tag` để lọc meter:

~~~powershell
curl.exe -i "http://localhost:8080/actuator/metrics/module.events.published.orders.OrderSubmitted?tag=sales.channel:web&tag=sales.market:vn"

curl.exe -i "http://localhost:8080/actuator/metrics/module.events.published.orders.OrderSubmitted?tag=sales.channel:mobile&tag=sales.market:th"
~~~

Nếu bạn chỉ phát bốn event minh họa trong một JVM mới, sau khi không có thêm event, số đếm mong đợi gần như:

| sales.channel | sales.market | Số event publish trong demo |
| --- | --- | ---: |
| `web` | `vn` | 2 |
| `mobile` | `th` | 1 |
| `partner` | `other` | 1 |
| Tổng | | 4 |

Để kiểm thử trên một môi trường đã chạy lâu, hãy đọc giá trị **trước** và **sau** đợt request, rồi so **delta** thay vì ép tổng counter bằng đúng 4. Counter được Micrometer tạo và giữ trong registry của mỗi JVM; khi restart, giá trị in-memory sẽ đặt lại.

### 7.3. Xem Prometheus khi có registry

Khi đã thêm `micrometer-registry-prometheus` và expose endpoint `prometheus`:

~~~powershell
curl.exe -i "http://localhost:8080/actuator/prometheus"
~~~

Tìm các dòng metric có nguồn gốc từ `module.events.published.orders.OrderSubmitted` và nhãn tương ứng. **Tên Prometheus** có thể biến đổi theo naming convention (gạch dưới, hậu tố `_total`, chuyển chữ hoa/thường); đừng viết truy vấn PromQL chính thức trước khi nhìn vào dữ liệu thực của `/actuator/prometheus`. Các key Micrometer có dấu chấm cũng có thể được chuẩn hóa thành dấu gạch dưới ở exporter.

Khi đã biết tên thực, có thể thiết kế dashboard theo `sales_channel` và `sales_market`, ví dụ tổng tốc độ event publish theo kênh trong 5 phút. Một dashboard nên phân biệt tốc độ/số event đã phát với số event đã xử lý, và tránh so trực tiếp counter raw của các instance vừa restart.

## 8. Kiểm chứng module boundary và hành vi publish

Spring Modulith giúp đối chiếu các phần của thiết kế:

~~~mermaid
flowchart LR
    U[REST client] --> O[orders: OrderService]
    O -->|publish OrderSubmitted| E[Spring event mechanism]
    E -->|@EventListener| N[notifications: OrderAuditListener]
    E --> M[Modulith event instrumentation]
    M --> C[Counter riêng OrderSubmitted]
    C --> T[sales.channel, sales.market]
    M --> A[Counter tổng module.events.published]
    C --> R[Actuator /metrics và Prometheus exporter]
~~~

*Hình minh họa đường dữ liệu ở mức khái niệm. Cơ chế nội bộ khi instrument event phụ thuộc cấu hình và phiên bản Spring Modulith.*

Nếu đã expose `modulith`, thử:

~~~powershell
curl.exe -i "http://localhost:8080/actuator/modulith"
~~~

Mong đợi thấy `orders` và `notifications` trong module graph, cùng quan hệ event listener tương ứng. Endpoint này xác nhận **cấu trúc module**, không chứa các giá trị `sales.channel`, `sales.market` và không chứng minh listener đã hoàn tất.

Với tracing, một ứng dụng có thể instrument các lời gọi qua module, mang các tag như `module.name`, `module.method`, `module.invocation-type`. Khi dùng async executor, cần bảo đảm propagation của tracing context/MDC nếu muốn nhìn một trace nối liền; tag counter không tự sửa vấn đề mất context. `ModulithEventMetricsCustomizer` giải quyết **metric tags**, còn `ModulithObservationConvention` là cơ chế tùy biến convention của module Observation.

## 9. Kiểm thử tính đúng đắn của tag

Không cần khẳng định metric chính xác chỉ vì code bean được tạo thành công. Hãy xác minh các dấu hiệu có thể quan sát:

| Kiểm tra | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| Có customizer trong runtime | Khởi động ứng dụng và xem dependency/bean cấu hình | Không có `ClassNotFoundException`, bean được Spring tạo |
| Một event WEB/VN | Gửi một POST `WEB` + `VN` | Counter riêng có `sales.channel=web`, `sales.market=vn` |
| Nhiều tổ hợp tag | Gửi WEB/VN, MOBILE/TH, PARTNER/OTHER | Các series được phân biệt đúng |
| Tag khác giữ nguyên | Quan sát `module.identifier` và `module.name` | Tag mặc định vẫn có |
| Chỉ một event type được custom | Phát thêm event khác nếu có | Không tự gắn tag OrderSubmitted cho event khác |
| Summary counter | Quan sát `module.events.published` | Không kỳ vọng summary có hai tag nghiệp vụ từ customizer |
| Giá trị ngoài tập cho phép | Gửi `channel=RANDOM_CHANNEL` vào API enum | Request bị từ chối hoặc được xử lý theo chính sách validation, không sinh một tag tùy ý |
| Không đưa ID vào tag | Xem `availableTags`, đầu ra scrape | Không có `orderId` / `eventId` |
| Restart app | So count trước/sau | Có thể reset, vì counter in-memory không phải kho dữ liệu nghiệp vụ |

### 9.1. Kiểm tra qua `MeterRegistry` trong test

Trong một test tích hợp đã bật observability và có Spring Context, bạn có thể inject Micrometer `MeterRegistry`. Ví dụ dưới đây là phần assertions trọng tâm sau khi gọi `OrderService`; project phải cấu hình test starter và observability phù hợp để không tắt instrumentation trong test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.orders.OrderService;
import com.example.shop.orders.OrderSubmitted.Market;
import com.example.shop.orders.OrderSubmitted.SalesChannel;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class OrderSubmittedMetricsTest {

    @Autowired OrderService orders;
    @Autowired MeterRegistry registry;

    @Test
    void customTagsArePresentOnIndividualEventCounter() {
        String metricName = "module.events.published.orders.OrderSubmitted";

        Counter before = registry.find(metricName)
            .tags("sales.channel", "web", "sales.market", "vn")
            .counter();
        double oldCount = before == null ? 0.0 : before.count();

        orders.submitOrder(SalesChannel.WEB, Market.VN);

        Counter after = registry.find(metricName)
            .tags("sales.channel", "web", "sales.market", "vn")
            .counter();

        assertThat(after).isNotNull();
        assertThat(after.count()).isGreaterThan(oldCount);

        assertThat(after.getId().getTag("module.identifier"))
            .isEqualTo("orders");
    }
}
~~~

**Lưu ý khi kiểm thử:** một số cấu hình Spring Boot mặc định giảm/tắt instrumentation trong test context; nếu bean metric không xuất hiện, bật observability cho test theo starter và cách cấu hình của **đúng phiên bản Boot** rồi kiểm chứng bằng HTTP test thực tế. Đoạn code không phải test runnable độc lập: cần các lớp ở phần 5, Gradle test starter và các bean Spring Modulith.

Dùng `oldCount` để test có thể chạy lại trong context đã được sử dụng. Tùy loại test và cách xử lý event, có thể phải đợi bằng điều kiện có timeout thay vì đọc ngay. Test chỉ nên khẳng định **publish counter** tăng; muốn khẳng định listener hoàn tất, thêm assertion riêng cho effect nghiệp vụ sau listener.

### 9.2. Kiểm thử chất lượng theo tình huống lỗi

Thử bỏ bean `ModulithEventMetricsCustomizer` khỏi ứng dụng. Khi vẫn có runtime observability, counter riêng vẫn có thể xuất hiện với tag mặc định nhưng **không còn** tag `sales.channel` và `sales.market`. Điều này chứng minh phần tag tùy biến thực sự đến từ bean.

Sau đó thử vô tình thay:

~~~java
builder.tags("order.id", event.orderId().toString());
~~~

Không cần chạy tải lớn để chứng minh tác hại: đọc code và nhận thấy mỗi đơn có ID khác, do đó số tổ hợp tag tăng theo số đơn. Loại bỏ dòng này; thay bằng một trong các enum hữu hạn và chỉ giữ ID trong log/trace có kiểm soát, không đưa vào meter tag.

## 10. Lỗi thường gặp và cách chẩn đoán

### 10.1. `ModulithEventMetricsCustomizer` không import được

**Nguyên nhân:** thiếu `spring-modulith-observability-api` trên compile classpath, hoặc đang dùng phiên bản Spring Modulith không có interface này.

**Kiểm tra:** resolved dependency của module ứng dụng; xác định Modulith có từ 1.4 trở lên và tên artifact tương ứng. Với Modulith 2.x, thêm compile dependency `spring-modulith-observability-api`; giữ implementation runtime (insight/observability-core). Đừng trộn artifact của 1.x và 2.x.

### 10.2. Không thấy `module.events.published...` trong Actuator

Khả năng thường gặp:

1. Chỉ thêm API compile mà **chưa bật observability runtime** bằng insight starter hoặc các dependency phù hợp.
2. Chưa publish event từ ứng dụng; counter có thể được đăng ký khi event đầu tiên đi qua instrumentation.
3. Event nằm ngoài mô hình application module hoặc không được instrumentation nhận diện như kỳ vọng; kiểm tra package root và listener xuyên module.
4. Ứng dụng chạy ở profile khác, dùng artifact cũ hoặc dependency bị loại ở runtime.
5. `/actuator/metrics` chưa expose hay bị endpoint access/Spring Security chặn.
6. Đang hỏi metric name không đúng; xem danh sách ở `GET /actuator/metrics`.
7. Đang dùng một JVM khác (management port/proxy/load balancer trỏ instance không nhận request).

Đừng giải quyết bằng cách tạo thủ công một counter trùng tên với counter của Modulith. Trước hết xác minh instrumentation đã hoạt động.

### 10.3. Có counter tổng nhưng không thấy tag tùy biến

- Xem **counter riêng** `module.events.published.orders.OrderSubmitted`, vì customizer nhắm đến metric riêng theo event type.
- Kiểm tra event class được dùng làm key trong `metrics.customize(...)` có đúng **chính class của event được publish** không.
- Kiểm tra bean `@Configuration` nằm trong component scan và `@Bean` không bị profile/conditional configuration loại bỏ.
- Xem `availableTags` hoặc dữ liệu MeterRegistry để xác nhận các giá trị đã xuất hiện.
- Kiểm tra event sample dùng enum có giá trị tương ứng và không làm phát sinh exception trước khi publish.
- Nếu có nhiều customizer trùng loại event/tag, giảm về một cấu hình rõ ràng để tránh xung đột.

### 10.4. Chỉ thấy một giá trị tag dù đã gửi nhiều event

Có thể bạn đang xem một JVM riêng, test đã restart app, query có filter `tag`, hoặc metric của request thứ hai chưa được publish. Hãy kiểm tra từng request trả đúng HTTP status, listener có log và truy vấn **không có filter** trước; sau đó lọc các tổ hợp cụ thể để so delta.

### 10.5. Dashboard Prometheus không tìm thấy tên giống Micrometer

Exporter có naming convention riêng: dấu chấm, dấu gạch ngang, chữ hoa và hậu tố counter thường được chuẩn hóa. Hãy xem dữ liệu `/actuator/prometheus`, lấy tên metric/label chính xác rồi mới viết PromQL. Không giả định rằng tên Micrometer có dấu chấm sẽ xuất hiện nguyên văn trong Prometheus.

### 10.6. Metrics có nhiều series và chi phí tăng

Kiểm tra lại tag mới: có vô tình dùng `customerId`, `sessionId`, `orderId` hoặc đường dẫn dynamic không? Nếu có, thay bằng enum/nhóm giá trị hữu hạn, giới hạn số tổ hợp và cân nhắc `MeterFilter.maximumAllowableTags` như **cơ chế phòng vệ bổ sung** chứ không thay thế thiết kế cardinality tốt ngay từ đầu.

## 11. Khi đưa vào hệ thống doanh nghiệp

### 11.1. Giới hạn trách nhiệm của customizer

`ModulithEventMetricsCustomizer` chỉnh cách tạo **counter cho event publication**. Không tự:

- xác định một đơn đã lưu thành công trong DB;
- xác định listener đã xử lý thành công hoặc đã retry bao nhiêu lần;
- thêm tag vào mọi Observation/span;
- truyền MDC/tracing context sang executor bất đồng bộ;
- cung cấp dữ liệu lịch sử vĩnh viễn sau khi JVM khởi động lại.

Muốn biết listener hoàn tất, dùng Event Publication Registry (nếu được cấu hình) và đo effect nghiệp vụ. Muốn quan sát tương tác giữa các module, dùng Modulith observability/Micrometer Observation và tracing bridge/exporter. Muốn giữ correlation xuyên thread, kiểm tra TaskDecorator/context propagation. Một dashboard đúng nên trình bày **published**, **completed**, **failed** và **backlog** như những tín hiệu có ý nghĩa khác nhau.

### 11.2. Ranh giới module và dashboard

Giữ kiểu sự kiện công khai trong module `orders` để `notifications` phụ thuộc theo hướng module hợp lệ. `ApplicationModules.verify()` giúp kiểm tra ranh giới, còn `GET /actuator/modulith` giúp xem module graph lúc runtime. Phải nhớ module graph là bằng chứng về **cấu trúc**, không phải bằng chứng về số lượt event hoặc tình trạng của listener.

### 11.3. Quy ước tổ chức

Trước khi đưa tag mới vào hệ thống metrics, cần thống nhất:

- Một nơi định nghĩa tên tag và ý nghĩa, ví dụ `sales.channel`, `sales.market`.
- Bảng giá trị hợp lệ và cách chuẩn hóa đối với giá trị lạ.
- Chủ sở hữu metric, loại event và mục đích dashboard/alert.
- Ngưỡng cardinality và tài nguyên của registry/exporter.
- Quy tắc không gắn thông tin nhận dạng cá nhân hoặc business IDs có số lượng lớn.
- Kiểm thử hồi quy khi đổi event schema hoặc tên enum, vì đó là thay đổi đầu vào dashboard.

Nếu có các vùng mới, nên map sang nhóm `other` trước rồi cập nhật schema tag một cách có kế hoạch. Không tạo một tag value duy nhất cho mỗi thị trường/cửa hàng mà không đánh giá cardinality toàn hệ thống.

## 12. Bài tập nâng cao

1. Thay đổi ví dụ để đếm hai loại event `OrderSubmitted` và `OrderCancelled`. Mỗi loại có tập tag riêng; dùng **một** bean customizer đăng ký hai `metrics.customize(...)`.
2. Tạo một enum channel mới `CALL_CENTER`. Tính lại số tổ hợp tag tối đa và cách nó ảnh hưởng chi phí metric.
3. Cấu hình một **async listener** trong `notifications` với transaction phù hợp, quan sát counter publish tăng trước khi xử lý xong. Thêm một metric/outcome riêng để đo listener success.
4. Bật Prometheus registry, xác định tên metric sau naming convention và viết một truy vấn tốc độ publication theo channel.
5. Tắt observability runtime nhưng giữ API compile; ghi nhận sự khác biệt giữa việc **biên dịch được customizer** và **không có metric khi chạy**.
6. Dùng module graph và tracing để quan sát tương tác `orders -> notifications`. Chủ động thử môi trường async thiếu context propagation và giải thích vì sao tag counter vẫn có thể xuất hiện trong khi trace mất liên kết.
7. Thêm kiểm tra không cho phép tag có cardinality lớn trong quy trình code review/observability test.

## 13. Câu hỏi tự đánh giá

1. `module.events.published` và `module.events.published.orders.OrderSubmitted` khác nhau về mục đích và tag mặc định như thế nào?
2. Vì sao `ModulithEventMetricsCustomizer` cần được đăng ký thành bean Spring?
3. Tại sao `spring-modulith-observability-api` cần ở compile classpath khi source code import customizer?
4. Overload `customize(Class<T>, BiConsumer<T, Counter.Builder>)` phù hợp hơn factory overload ở trường hợp thêm tag nào?
5. Vì sao `orderId` là tag không tốt dù nó rất hữu ích để điều tra một đơn cụ thể?
6. Ba channel và ba market tạo tối đa bao nhiêu tổ hợp tag mới cho một event type?
7. Vì sao hai metric cùng tên nhưng khác tag vẫn được xem là những series khác nhau?
8. Tại sao endpoint `/actuator/modulith` không giúp kiểm tra có tag `sales.channel` trên counter?
9. Nếu thấy counter publish tăng mà listener không tạo thông báo, cần quan sát nguồn nào tiếp theo?
10. Khi Prometheus không có tên metric y hệt Micrometer, bạn nên kiểm tra ở đâu?
11. `ModulithObservationConvention` liên quan gì đến bài thực hành và khác `ModulithEventMetricsCustomizer` ra sao?
12. Khi dùng async listener, vì sao context propagation cần được kiểm tra riêng với việc tùy biến tag metric?

## Tài liệu tham khảo

- [Spring Modulith — Production-ready Features: Observability Metrics](https://docs.spring.io/spring-modulith/reference/production-ready.html): hai loại event counter, bảng tag mặc định và ví dụ `ModulithEventMetricsCustomizer`.
- [Spring Modulith 2.2 — ModulithEventMetricsCustomizer API](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html): functional interface và phương thức `customize(ModulithEventMetrics)`.
- [Spring Modulith 2.2 — ModulithEventMetrics API](https://docs.spring.io/spring-modulith/docs/2.2.0/api/org/springframework/modulith/observability/ModulithEventMetrics.html): hai overload `customize(...)` cho counter builder.
- [Spring Modulith — Modules and Compatibility](https://docs.spring.io/spring-modulith/reference/appendix.html): BOM, modules và compatibility.
- [Spring Modulith 1.4 Release](https://spring.io/blog/2025/05/28/spring-modulith-1-4-1-3-6-and-1-2-13-released/): thời điểm API event metrics/customizer được giới thiệu.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): truy vấn metrics, registry và exporter.
- [Micrometer — Naming Meters and Tags](https://docs.micrometer.io/micrometer/reference/concepts/naming.html): quy ước tên và tag, nguyên tắc cardinality.

