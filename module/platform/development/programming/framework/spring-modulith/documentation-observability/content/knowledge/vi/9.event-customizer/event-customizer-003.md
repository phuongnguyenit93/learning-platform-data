# Customize metric cho từng event type

## Mục tiêu học tập

Trong chương **Event customizer** của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, ta tìm hiểu cách mở rộng các metric về application event do Spring Modulith tạo trong ứng dụng Spring Boot. Trọng tâm của bài là **tùy biến counter theo từng kiểu event**, thay vì viết một counter mới rồi nhầm nó với metric của framework.

Sau bài học, bạn có thể:

1. Phân biệt counter tổng hợp `module.events.published` và counter dành riêng cho mỗi event type.
2. Giải thích `ModulithEventMetricsCustomizer` và hai overload của `ModulithEventMetrics.customize(...)`.
3. Đăng ký một bean cấu hình để gắn tag **riêng cho OrderSubmitted, PaymentCaptured và StockReservationRejected** theo đúng thuộc tính của từng event.
4. Giữ cardinality của metric ở mức kiểm soát được bằng enum, whitelist, giới hạn giá trị và quy tắc chuẩn hóa.
5. Kiểm tra metric trong `MeterRegistry`, Spring Boot Actuator hoặc hệ thống metrics đang sử dụng.
6. Phân biệt “event đã được publish” với “listener đã hoàn tất” để tránh dựng dashboard và alert sai ý nghĩa.
7. Xử lý những lỗi thường gặp khi chuyển đổi phiên bản, thay đổi tên event, dùng sai scope dependency hoặc backend không nhận được tag.

**Bối cảnh:** Spring Modulith giúp tài liệu hóa ranh giới application module và quan sát tương tác giữa chúng qua module graph, Actuator, metrics, tracing và context propagation. Khi nhiều module trao đổi bằng application event, số lượng **event được phát theo loại** là một tín hiệu hữu ích. Tùy biến theo event type cho phép bổ sung ngữ cảnh nghiệp vụ có giới hạn, chẳng hạn kênh đặt hàng, phương thức thanh toán hoặc lý do từ chối giữ hàng.

> **Phạm vi phiên bản:** Tài liệu này tham chiếu API `ModulithEventMetricsCustomizer` / `ModulithEventMetrics` và dạng metric được mô tả trong Spring Modulith **1.4 trở lên**, đối chiếu với Javadoc **2.2.0**. Một số artifact và cách cấu hình của bản cũ có thể khác; cần kiểm tra BOM và reference guide đúng release đang chạy. Ví dụ mã sử dụng Java 17+ với record, Spring Boot và Micrometer.

---

## 1. Vì sao tùy biến theo từng event type?

Giả sử modular monolith có các application module:

- **orders:** tiếp nhận đơn và phát `OrderSubmitted`;
- **payments:** ghi nhận thanh toán và phát `PaymentCaptured`;
- **inventory:** giữ tồn kho, phát `StockReservationRejected` khi không thể đáp ứng;
- **fulfillment:** xử lý bước chuẩn bị giao hàng theo trạng thái hợp lệ.

Khi traffic tăng, nhóm vận hành nhận được hai câu hỏi:

- **Câu hỏi kỹ thuật:** Trong 5 phút qua, có bao nhiêu lần `OrderSubmitted` được publish từ module `orders`?
- **Câu hỏi phân tích vận hành:** Trong các publication `OrderSubmitted`, kênh `WEB` và `STORE` có tỷ lệ thay đổi thế nào? Lý do từ chối giữ hàng nào đang tăng bất thường?

Một counter mặc định giúp trả lời câu đầu. Để trả lời câu sau bằng Micrometer, ta có thể gắn **các tag cụ thể cho một event type**. Chẳng hạn:

~~~text
module.events.published.orders.OrderSubmitted
    module.identifier = orders
    module.name       = Orders
    sales.channel     = WEB

module.events.published.inventory.StockReservationRejected
    module.identifier  = inventory
    module.name        = Inventory
    rejection.reason   = OUT_OF_STOCK
~~~

Đây là **biểu diễn minh họa về meter và tag**, không phải output từ một ứng dụng cụ thể; tên hiển thị bên ngoài có thể được registry/exporter chuẩn hóa khác nhau.

Điểm quan trọng: `sales.channel` chỉ có nghĩa với `OrderSubmitted`, còn `rejection.reason` chỉ có nghĩa với `StockReservationRejected`. Tùy biến theo **event class** giúp giữ chính sách đo lường gần loại dữ liệu mà nó mô tả.

### 1.1. Một metric có nhiều chuỗi giá trị

Micrometer xác định một meter không chỉ bằng tên mà còn bằng tập tag. Nếu cùng event type có ba giá trị của `sales.channel` thì backend có thể thu ba series khác nhau.

Ví dụ:

| Tên metric | Tag | Ý nghĩa |
| --- | --- | --- |
| `module.events.published.orders.OrderSubmitted` | `sales.channel=WEB` | Những publication của event đặt hàng từ kênh WEB được quan sát. |
| `module.events.published.orders.OrderSubmitted` | `sales.channel=STORE` | Những publication của event đặt hàng từ kênh STORE được quan sát. |
| `module.events.published.orders.OrderSubmitted` | `sales.channel=PARTNER` | Những publication của event đặt hàng từ kênh PARTNER được quan sát. |

Counter thường có giá trị **tích lũy theo tiến trình hoặc vòng đời registry**. Để so sánh lưu lượng trong 5 phút, backend thường sử dụng tốc độ tăng của counter hoặc hiệu số theo cửa sổ thời gian; không dùng trực tiếp giá trị tích lũy như “số sự kiện 5 phút gần nhất”.

## 2. Metric mặc định của Spring Modulith

Theo tài liệu Spring Modulith, instrumentation cung cấp hai nhóm counter cho application events:

| Nhóm | Tên được tài liệu hóa | Phạm vi |
| --- | --- | --- |
| **Tổng hợp tất cả event publications** | `module.events.published` | Theo dõi các publication đã được quan sát và phân nhóm bằng những tag do framework cung cấp. |
| **Counter cho một event type cụ thể** | `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Cho phép làm giàu bằng tag nghiệp vụ dựa trên payload event cụ thể. |

Các **low-cardinality keys** framework mô tả:

| Metric | Key | Nội dung |
| --- | --- | --- |
| Tổng hợp | `module.event.type` | Loại event được phát. |
| Tổng hợp | `module.identifier` | Định danh module. |
| Tổng hợp | `module.name` | Tên module. |
| Theo event type | `module.identifier` | Module gắn với event. |
| Theo event type | `module.name` | Tên module gắn với event. |

### 2.1. Phân biệt tag mặc định và tag tự bổ sung

Khi ta đăng ký customizer cho `OrderSubmitted`, mục tiêu là bổ sung hoặc điều chỉnh **Counter.Builder dành cho event type đó**. Đừng mặc định việc customizer thay đổi mọi span hoặc counter tổng hợp `module.events.published`.

Sơ đồ trách nhiệm:

~~~mermaid
flowchart TD
    P["Ứng dụng publish OrderSubmitted"] --> E["Instrumentation nhận event publication"]
    E --> G["Counter tổng hợp\nmodule.events.published"]
    E --> I["Counter riêng\nmodule.events.published.orders.OrderSubmitted"]
    C["ModulithEventMetricsCustomizer\nOrderSubmitted.class"] --> I
    I --> T["Tag nghiệp vụ: sales.channel"]
    G --> R["Micrometer MeterRegistry"]
    T --> R
    R --> X["Actuator / exporter / backend metrics"]
~~~

Customizing event counter không phải thao tác phát event lại, cũng không biến event thành một message mới. Nó chỉ can thiệp vào metadata của **meter được tạo** trong pipeline observability.

### 2.2. Publication không đồng nghĩa với xử lý thành công

Tên metric có chứa `published` vì nó biểu diễn **publication**, không phải cam kết rằng:

- listener đã nhận và xử lý thành công;
- listener đã commit transaction;
- một publication chỉ tạo một hiệu ứng nghiệp vụ;
- event không bị phát lại sau retry;
- giao dịch ở hệ thống ngoài đã hoàn tất.

Ví dụ: hai publication của cùng một event ID có thể làm counter tăng hai lần, dù hệ thống nghiệp vụ xử lý idempotent và chỉ tạo một đơn. Ngược lại, metric cũng có thể thiếu nếu instrumentation hoặc pipeline thu thập không hoạt động. Nếu muốn biết **đơn đã thanh toán đúng**, phải dùng dữ liệu có thẩm quyền và quy tắc nghiệp vụ, không quy đổi counter publication thành ledger.

## 3. Extension point: ModulithEventMetricsCustomizer

API có package:

~~~java
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;
import org.springframework.modulith.observability.ModulithEventMetrics;
~~~

`ModulithEventMetricsCustomizer` là interface để ứng dụng khai báo cách tùy biến những counter do Spring Modulith tạo cho cross-module events. Phương thức chính có dạng:

~~~java
void customize(ModulithEventMetrics metrics);
~~~

Một Spring bean implement interface này có thể đăng ký cấu hình cho nhiều kiểu event:

~~~java
@Bean
ModulithEventMetricsCustomizer customizer() {
    return metrics -> {
        metrics.customize(OrderSubmitted.class, (event, counter) -> {
            counter.tag("sales.channel", event.channel().name());
        });

        metrics.customize(PaymentCaptured.class, (event, counter) -> {
            counter.tag("payment.method", event.method().name());
        });
    };
}
~~~

Các event ở đoạn mã là **kiểu miền nghiệp vụ do ứng dụng định nghĩa**. Chúng không có sẵn trong Spring Modulith.

### 3.1. Hai overload của ModulithEventMetrics.customize

Javadoc mô tả hai cách đăng ký:

| Chữ ký rút gọn | Nên dùng khi nào? | Lưu ý |
| --- | --- | --- |
| `customize(Class<T>, BiConsumer<T, Counter.Builder>)` | Cần **làm giàu builder hiện có**: thêm tag, description hoặc metadata phù hợp. | Builder đã được framework chuẩn bị; ít tác động lên quy ước mặc định. |
| `customize(Class<T>, Function<T, Counter.Builder>)` | Cần **kiểm soát việc tạo Counter.Builder** cho loại event. | Có thể làm đổi tên/đặc điểm meter; phải cân nhắc tác động tới dashboard và thống kê. |

Javadoc nêu rằng builder do overload `Function` tạo ra vẫn được áp dụng các customization đăng ký qua overload `BiConsumer`. Đây là đặc điểm hữu ích khi một team cần đổi cách tạo builder nhưng vẫn muốn dùng các quy tắc tag bổ sung.

**Nguyên tắc ưu tiên:** bắt đầu với `BiConsumer` nếu chỉ muốn thêm một vài tag theo event type. Đổi toàn bộ builder bằng `Function` chỉ khi có yêu cầu rõ ràng vì nó làm tăng trách nhiệm ổn định hợp đồng telemetry của ứng dụng.

### 3.2. Tham số trong callback là gì?

Với:

~~~java
metrics.customize(OrderSubmitted.class, (event, builder) -> {
    builder.tag("sales.channel", event.channel().name());
});
~~~

- `OrderSubmitted.class` cho framework biết event type được đăng ký.
- `event` là đối tượng event của kiểu `OrderSubmitted` đang được xử lý.
- `builder` là Micrometer `Counter.Builder` được cung cấp cho quá trình tạo counter.
- `builder.tag(key, value)` gắn thêm một nhãn vào meter.

Bạn **không cần** gọi `builder.register(meterRegistry)` hoặc `counter.increment()` trong callback trên. Spring Modulith tiếp tục điều khiển việc tạo và tăng counter theo cơ chế instrumentation; callback chỉ cấu hình builder.

### 3.3. Event type chính xác quan trọng

Một customizer đăng ký cho `OrderSubmitted.class` không có nghĩa nó tự động làm giàu **mọi event của module orders**. Nếu thực tế chỉ phát `OrderCreatedV2`, rule trên không có dữ liệu để áp dụng. Với kế thừa class/interface, không nên suy đoán cách framework đối sánh subtype nếu chưa kiểm chứng bằng Javadoc và test của phiên bản đang dùng.

Cần xem event class là một phần của hợp đồng quan sát: khi đổi tên, tách hoặc hợp nhất kiểu event, phải xem lại customizer, metric name, tag values và truy vấn dashboard.

## 4. Chuẩn bị dependency đúng compile/runtime scope

Các ví dụ bên dưới giả định bạn đã import **Spring Modulith BOM** tương thích với Spring Boot trong dự án. Không trộn riêng version của `-api` và `-core` từ hai release khác nhau.

### 4.1. Dùng Insight starter và bổ sung API

Gradle (Groovy DSL):

~~~groovy
dependencies {
    // Instrumentation, Module Actuator và hạ tầng Insight khi chạy.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Cần cho mã nguồn có import ModulithEventMetricsCustomizer.
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-api</artifactId>
        <!-- compile là scope mặc định của Maven -->
    </dependency>
</dependencies>
~~~

**Vì sao cần khai báo API riêng?** Nếu starter được đưa vào bằng `runtimeOnly`, các kiểu chỉ đến từ starter/transitive runtime dependencies không mặc nhiên khả dụng khi Java compiler xử lý `src/main/java`. File Java import `ModulithEventMetricsCustomizer` phải thấy artifact API trong **compile classpath**.

### 4.2. Chỉ cần observability, không cần Modulith Actuator

Gradle:

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability-core'
    implementation 'org.springframework.modulith:spring-modulith-observability-api'

    // Hạ tầng Spring Boot/Micrometer của ví dụ khi chưa có sẵn.
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-core</artifactId>
        <scope>runtime</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-api</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

Không cần tự khai báo `spring-modulith-observability-core` thêm lần nữa khi Insight starter đã kéo đúng core. Tùy nguồn metrics muốn xuất, có thể phải bổ sung registry/exporter; `-api` không phải là công cụ gửi dữ liệu ra Prometheus hay trace backend.

### 4.3. Kiểm tra classpath

Gradle:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.modulith
~~~

Mục tiêu là kiểm tra **API ở compile scope**, **core ở runtime scope**, phiên bản Spring Modulith đồng bộ và không có dependency exclusion làm mất instrumentation. Nếu build đang dùng Windows PowerShell, có thể gọi `gradlew.bat` tương ứng.

## 5. Ví dụ end-to-end: ba event type, ba chính sách tag

Ta sẽ xây một chính sách tùy biến dùng enum để các giá trị tag luôn thuộc tập nhỏ và có định nghĩa rõ.

### 5.1. Domain event: OrderSubmitted

Trong module `orders`:

~~~java
package com.example.shop.orders;

import java.util.UUID;

public record OrderSubmitted(UUID orderId, SalesChannel channel) {

    public enum SalesChannel {
        WEB, STORE, PARTNER, OTHER
    }
}
~~~

Lớp `OrderSubmitted` là event do ứng dụng tự tạo. `orderId` có ích để truy vết nghiệp vụ nhưng không được đưa vào metric label. `channel` là nguồn của tag `sales.channel`.

### 5.2. Domain event: PaymentCaptured

Trong module `payments`:

~~~java
package com.example.shop.payments;

import java.util.UUID;

public record PaymentCaptured(UUID paymentId, PaymentMethod method) {

    public enum PaymentMethod {
        CARD, BANK_TRANSFER, WALLET, OTHER
    }
}
~~~

`paymentId` là định danh giao dịch, còn `method` thuộc tập giới hạn dùng cho thống kê. **Không đưa token thẻ, số tài khoản hoặc nội dung chuyển khoản** vào metric.

### 5.3. Domain event: StockReservationRejected

Trong module `inventory`:

~~~java
package com.example.shop.inventory;

import java.util.UUID;

public record StockReservationRejected(UUID orderId, RejectionReason reason) {

    public enum RejectionReason {
        OUT_OF_STOCK, RESERVATION_CONFLICT, INVALID_REQUEST, OTHER
    }
}
~~~

`reason` hỗ trợ phân biệt nguyên nhân từ chối giữ hàng. Nếu tổ chức có nhiều mã lỗi chi tiết, nên ánh xạ về một nhóm nguyên nhân ổn định trước khi dùng làm tag.

### 5.4. Một bean customizer cho ba event type

~~~java
package com.example.shop.config;

import com.example.shop.orders.OrderSubmitted;
import com.example.shop.orders.OrderSubmitted.SalesChannel;
import com.example.shop.payments.PaymentCaptured;
import com.example.shop.payments.PaymentCaptured.PaymentMethod;
import com.example.shop.inventory.StockReservationRejected;
import com.example.shop.inventory.StockReservationRejected.RejectionReason;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
public class ShopEventMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer eventMetricsCustomizer() {
        return metrics -> {

            metrics.customize(OrderSubmitted.class, (event, builder) -> {
                builder.tag(
                    "sales.channel",
                    safeName(event.channel(), SalesChannel.OTHER)
                );
            });

            metrics.customize(PaymentCaptured.class, (event, builder) -> {
                builder.tag(
                    "payment.method",
                    safeName(event.method(), PaymentMethod.OTHER)
                );
            });

            metrics.customize(StockReservationRejected.class, (event, builder) -> {
                builder.tag(
                    "rejection.reason",
                    safeName(event.reason(), RejectionReason.OTHER)
                );
            });
        };
    }

    private static <E extends Enum<E>> String safeName(E value, E fallback) {
        return (value == null ? fallback : value).name();
    }
}
~~~

Đoạn code trên cho thấy cách đăng ký bằng API chính thức, nhưng chỉ hoạt động có ý nghĩa khi các event type thực sự được **publish** và được instrumentation nhận diện trong ứng dụng. Code không tự tạo publication hoặc listener.

**Giải thích:**

- Một bean duy nhất định nghĩa ba nhóm chính sách khác nhau.
- `metrics.customize(OrderSubmitted.class, ...)` chọn đúng loại event.
- `Counter.Builder.tag(...)` bổ sung nhãn theo payload có kiểu rõ ràng.
- `safeName(...)` tránh truyền `null` vào Micrometer tag và giới hạn giá trị nhờ enum.
- Các ID của đơn và thanh toán không đi vào tags nên tránh cardinality tăng theo từng giao dịch.
- Không viết một callback dùng chung để phản chiếu tất cả field của event thành tags; hành vi đó dễ lộ dữ liệu và làm số series bùng nổ.

**Vị trí triển khai:** class `ShopEventMetricsConfiguration` phải nằm trong phạm vi component scan/configuration import của Spring Boot; các event record cần thuộc các module/kiểu sự kiện thực tế của dự án. Nếu tách dependency giữa module, chỉ import event từ **API được công khai hợp lệ** theo ranh giới Spring Modulith.

### 5.5. Ví dụ phát và nhận event xuyên module

Một service của module `orders` có thể publish:

~~~java
package com.example.shop.orders;

import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final ApplicationEventPublisher events;

    public CheckoutService(ApplicationEventPublisher events) {
        this.events = events;
    }

    public void submit(UUID orderId, OrderSubmitted.SalesChannel channel) {
        // Trong hệ thống thực: kiểm tra điều kiện tạo đơn và lưu trạng thái.
        events.publishEvent(new OrderSubmitted(orderId, channel));
    }
}
~~~

Ở module khác, ví dụ `payments`, có thể có listener:

~~~java
package com.example.shop.payments;

import com.example.shop.orders.OrderSubmitted;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class OrderSubmittedListener {

    @EventListener
    void on(OrderSubmitted event) {
        // Minh họa điểm nhận event; xử lý thanh toán thật nằm ngoài ví dụ.
    }
}
~~~

Ví dụ chỉ nhằm tạo **luồng application event** để người học quan sát. Nó không triển khai bảo đảm transaction, retry hoặc xử lý thanh toán. Nếu dùng `@TransactionalEventListener`, `@Async`, Event Publication Registry hoặc message broker, cần kiểm tra thời điểm và đường đi của instrumentation theo cấu hình tương ứng.

Những event khác (`PaymentCaptured`, `StockReservationRejected`) phải được publish từ các luồng nghiệp vụ thích hợp để counter và tag của chúng có dữ liệu.

## 6. Hiểu dữ liệu sẽ thu thập được

Sau khi chạy các kịch bản thử nghiệm, giả sử có:

- 10 publication `OrderSubmitted` với `channel=WEB`;
- 4 publication `OrderSubmitted` với `channel=STORE`;
- 3 publication `PaymentCaptured` với `method=CARD`;
- 2 publication `StockReservationRejected` với `reason=OUT_OF_STOCK`.

Một hệ thống metrics có thể biểu diễn các series logic:

| Series được nhận diện theo tên metric và tags | Giá trị counter minh họa |
| --- | ---: |
| `OrderSubmitted{sales.channel="WEB"}` | 10 |
| `OrderSubmitted{sales.channel="STORE"}` | 4 |
| `PaymentCaptured{payment.method="CARD"}` | 3 |
| `StockReservationRejected{rejection.reason="OUT_OF_STOCK"}` | 2 |

**Đây là số liệu giả định.** Mỗi row cũng có thể mang tags framework như `module.identifier` và `module.name`. Registry và exporter có thể đổi cách hiển thị tên meter/tag (đặc biệt khi chuyển sang Prometheus), nên không sao chép các tên viết tắt trong bảng để làm truy vấn production.

### 6.1. Điều customizer không làm

Customizer này:

- **không** làm thay đổi `OrderSubmitted` thành `PaymentCaptured`;
- **không** tạo ra business event mới;
- **không** đếm số listener đã thành công;
- **không** chặn event bị phát lại;
- **không** truyền trace context sang executor hoặc message broker;
- **không** thêm tags vào mọi module invocation span;
- **không** cung cấp backend thu thập metric.

Để thay đổi **module spans**, Spring Modulith có extension point `ModulithObservationConvention`. Để kiểm soát hành vi nghiệp vụ, cần kiểm thử, transaction, idempotency và đối soát riêng.

## 7. Kiểm soát cardinality và thiết kế tag

### 7.1. Cardinality tăng theo tích số tổ hợp

Giả sử counter `OrderSubmitted` có ba chiều tag:

- `sales.channel` có 4 giá trị;
- `customer.segment` có 5 giá trị;
- `region` có 12 giá trị.

Chỉ riêng một event metric có thể cần tới **4 × 5 × 12 = 240 series**, chưa kể module tags và những chiều khác do registry thêm. Nếu thay `region` bằng 100.000 `orderId` thì số tổ hợp tiềm năng tăng rất mạnh; chi phí lưu trữ, truy vấn và cảnh báo có thể trở nên khó kiểm soát.

Bài học quan trọng: **chọn những chiều đo mà dashboard thực sự sử dụng**, và đánh giá tích số cardinality trước khi phát hành.

### 7.2. Bảng phân loại tag

| Thuộc tính event | Có nên dùng làm metric tag? | Lý do |
| --- | --- | --- |
| `SalesChannel.WEB/STORE/PARTNER/OTHER` | **Có** | Giá trị hữu hạn, ý nghĩa vận hành rõ. |
| `PaymentMethod.CARD/BANK_TRANSFER/WALLET/OTHER` | **Có** | Giúp so sánh traffic theo phương thức, không chứa chi tiết thanh toán. |
| `RejectionReason.OUT_OF_STOCK/...` | **Có** | Có thể theo dõi nguyên nhân từ chối theo nhóm. |
| `orderId`, `paymentId`, `eventId` | **Không** | Gần như mỗi event có giá trị riêng. |
| `customerEmail`, số điện thoại, địa chỉ | **Không** | Vừa nhạy cảm, vừa cardinality cao. |
| `exception.getMessage()` | Thường **không** | Có thể chứa dữ liệu biến thiên và bí mật. |
| Toàn bộ `event.toString()` | **Không** | Có thể lộ payload và tăng không giới hạn. |
| `module.identifier` của framework | Có, trong phạm vi định nghĩa framework | Hữu ích để thống kê theo module, giá trị tương đối ổn định. |

### 7.3. Khi event nhận dữ liệu dạng String từ bên ngoài

Ví dụ event lưu `String channel` thay vì enum. Nếu dùng thẳng:

~~~java
builder.tag("sales.channel", event.channel());
~~~

thì `WEB`, `web`, `Web`, `WEB-ANDROID-7` hoặc giá trị bất kỳ sẽ sinh ra nhiều chuỗi giá trị. Hãy chuẩn hóa bằng whitelist rõ ràng:

~~~java
private static String normalizeChannel(String value) {

    if (value == null) {
        return "OTHER";
    }

    return switch (value.trim().toUpperCase(java.util.Locale.ROOT)) {
        case "WEB" -> "WEB";
        case "STORE" -> "STORE";
        case "PARTNER" -> "PARTNER";
        default -> "OTHER";
    };
}
~~~

Sau đó dùng:

~~~java
metrics.customize(OrderSubmitted.class, (event, builder) -> {
    builder.tag("sales.channel", normalizeChannel(event.channel()));
});
~~~

**Lưu ý kiểu dữ liệu:** ví dụ này áp dụng cho **phiên bản event có `channel()` trả về `String`**, thay cho record có enum ở phần 5. Đừng trộn cả hai khai báo vào cùng file Java như thể chúng là một kiểu.

Hạn chế cardinality ở **đầu vào tag** giúp ngăn giá trị lạ vô tình đi vào meter registry. Có thể bổ sung `MeterFilter.maximumAllowableTags(...)` như một lớp phòng vệ của Micrometer, nhưng nó không thay thế thiết kế nhãn đúng từ đầu.

## 8. Tùy biến nhiều event type mà không gây nhầm nghĩa

Một event type nên có **những tag ổn định theo ý nghĩa của chính nó**. Cùng một tên tag trên hai event chỉ nên dùng khi cùng một định nghĩa.

Ví dụ:

| Event | Tag đề xuất | Ý nghĩa cụ thể |
| --- | --- | --- |
| `OrderSubmitted` | `sales.channel` | Kênh tạo đơn ở thời điểm publication. |
| `PaymentCaptured` | `payment.method` | Loại phương thức thanh toán đã được ghi nhận trong event. |
| `StockReservationRejected` | `rejection.reason` | Nhóm lý do từ chối giữ hàng. |

Một số sai lầm:

- Dùng `status=SUCCESS` cho cả “event đã publish”, “payment đã settle” và “stock đã giữ xong”, khiến dashboard không biết status có cùng ý nghĩa hay không.
- Đổi `sales.channel` từ kênh tạo đơn sang kênh chuyển hàng mà không đổi hợp đồng.
- Dùng `failure.reason` lấy trực tiếp exception message có dữ liệu người dùng.
- Đăng ký customizer cho event class cũ sau khi đã chuyển sang event class mới.
- Dùng cùng loại event để phát nhiều ý nghĩa trái ngược, khiến counter không thể phân tích đáng tin cậy.

### 8.1. Khi nên tách thêm metric nghiệp vụ riêng?

Đôi khi yêu cầu không phải “tùy biến publication metric”. Ví dụ, nhóm muốn đếm **số đơn READY_TO_SHIP đã commit thành công** hoặc **số payment duy nhất đã settle**.

Đó là outcome nghiệp vụ, không đồng nghĩa với số lần event được publish. Hãy thiết kế metric riêng cho đúng thời điểm nghiệp vụ (sau commit hoặc từ dữ liệu có thẩm quyền), đặt tên rõ, ghi nhận idempotency và đối soát với state cuối. **Không đổi tên metric publication rồi coi nó là metric thành công nghiệp vụ.**

### 8.2. Khi cần thay toàn bộ Counter.Builder

Trong trường hợp nâng cao, overload nhận `Function<T, Counter.Builder>` cho phép tạo builder mới theo event. Đoạn ví dụ ngắn:

~~~java
metrics.customize(OrderSubmitted.class,
    event -> io.micrometer.core.instrument.Counter
        .builder("shop.order.submission.publications")
        .description("Observed OrderSubmitted publications")
);
~~~

Đây là **phương án thiết kế theo hợp đồng telemetry của ứng dụng**, không còn giữ mặc định tên metric riêng mà framework dùng. Nếu triển khai cách này, đội phát triển phải xác định **nơi gắn tags mặc định**, kiểm tra khả năng xuất và cập nhật dashboard; đồng thời tránh trùng tên với các meter có ý nghĩa khác.

Javadoc cho biết có thể kết hợp `Function` tạo builder với `BiConsumer` thêm tag. Ví dụ:

~~~java
metrics.customize(OrderSubmitted.class,
    event -> io.micrometer.core.instrument.Counter
        .builder("shop.order.submission.publications")
);

metrics.customize(OrderSubmitted.class,
    (event, builder) -> builder.tag(
        "sales.channel",
        event.channel() == null ? "OTHER" : event.channel().name()
    )
);
~~~

Chỉ dùng cách này nếu có nhu cầu đổi builder thực sự. **BiConsumer làm giàu builder chuẩn** đơn giản và ít rủi ro hơn cho các dashboard đang phụ thuộc tên mặc định.

## 9. Kiểm chứng customizer từ ứng dụng tới backend

Một customizer hợp lệ ở compile time chưa chắc đã tạo metric có tag trên backend. Hãy kiểm tra theo từng lớp:

~~~mermaid
flowchart TD
    A["Code compile và bean registered"] --> B["Event thực tế được publish"]
    B --> C["Spring Modulith instrumentation hoạt động"]
    C --> D["Counter.Builder áp dụng customizer"]
    D --> E["MeterRegistry có meter/tag mong muốn"]
    E --> F["Actuator hoặc registry exporter đưa dữ liệu ra"]
    F --> G["Backend nhận và hiển thị series"]
    G --> H["Dashboard dùng đúng tên và semantics"]
~~~

### 9.1. Tầng 1: dependency và Spring bean

Kiểm tra:

- `spring-modulith-observability-api` nằm trong **compile classpath**;
- `spring-modulith-observability-core` hoặc Insight starter nằm trong **runtime classpath**;
- class `@Configuration` được component scan/import;
- bean `ModulithEventMetricsCustomizer` được Spring context tạo;
- tất cả artifact Spring Modulith dùng version tương thích.

Nếu IDE báo không tìm thấy `ModulithEventMetricsCustomizer`, kiểm tra scope trước. Nếu bean không được load, kiểm tra package scan/profile/conditional config.

### 9.2. Tầng 2: phát event thật

Thử lần lượt:

1. Phát `OrderSubmitted` với `SalesChannel.WEB` qua `ApplicationEventPublisher`.
2. Phát `OrderSubmitted` với `SalesChannel.STORE`.
3. Phát `PaymentCaptured` với `PaymentMethod.CARD`.
4. Phát `StockReservationRejected` với `RejectionReason.OUT_OF_STOCK`.
5. Quan sát meter theo loại event. Có thể một event không được instrumentation nhận nếu không phù hợp phạm vi hoặc luồng phát event của cấu hình ứng dụng; **đừng kết luận lỗi tag trước khi xác minh event đó có được đo**.

Nên dùng kịch bản integration thực thay cho việc chỉ gọi trực tiếp lambda customizer trong unit test. Tùy phiên bản, module model và Spring event infrastructure ảnh hưởng đến đường đi instrumented.

### 9.3. Tầng 3: đọc từ Actuator

Ví dụ ở **môi trường phát triển hoặc nội bộ có phân quyền**, cho phép truy cập endpoint metrics:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Các lệnh quan sát:

~~~bash
curl --fail-with-body --silent --show-error \
  http://localhost:8080/actuator/metrics

# Thay <metric-name> bằng đúng tên nhận được ở danh sách.
curl --fail-with-body --silent --show-error \
  "http://localhost:8080/actuator/metrics/<metric-name>"
~~~

Endpoint metrics của Spring Boot Actuator có thể hỗ trợ lọc bằng tham số tag, ví dụ một meter được nhận diện có tag `sales.channel`:

~~~text
GET /actuator/metrics/<metric-name>?tag=sales.channel:WEB
~~~

**Dùng tên meter thực nhận được từ registry/endpoint**. Trong tài liệu Spring Modulith, counter riêng có mẫu `module.events.published.$moduleIdentifier.$simpleEventTypeName`, nhưng registry exporter có thể đổi tên hoặc phân tách tag bằng dấu gạch dưới khi hiển thị trên Prometheus. Không mặc định đường dẫn Actuator giống tên time series Prometheus.

### 9.4. Tầng 4: backend và dashboard

Nếu dùng Prometheus, Grafana, Datadog hoặc hệ thống khác, kiểm tra:

- có registry/exporter phù hợp trong Spring Boot;
- pipeline metrics đang scrape/export thành công;
- tên metric/tag có bị normalized hay đổi không;
- dashboard đang lọc **tên và tag mới**, không dùng metric cũ;
- counter có reset khi tiến trình restart, query có xử lý reset đúng không;
- collector có bỏ tags hoặc drop series do cardinality limit không.

**Sampling của traces khác với metrics counters.** Việc trace không xuất hiện do sampling không tự nói rằng counter cũng mất; hãy kiểm tra riêng đường đi metrics và tracing.

### 9.5. Bài kiểm thử tích hợp có ý nghĩa

Một integration test phù hợp có thể:

1. Khởi động Spring context với Modulith instrumentation, `SimpleMeterRegistry` hoặc registry phù hợp.
2. Publish event từ một module thật sang listener ở module khác trong kịch bản test.
3. Tìm metric riêng theo event type và tag mong đợi.
4. Ghi nhận giá trị counter ban đầu, publish thêm một event, sau đó kiểm tra counter tăng theo định nghĩa.
5. Thử event có `OTHER` để xác minh không sinh vô hạn label values.

Nên kiểm thử bằng **trạng thái meter thực tế** hơn là chỉ assert bean tồn tại. Khi có listener bất đồng bộ, cần đồng bộ điểm quan sát trong test thay vì `Thread.sleep` tùy ý; với metric publication, cần xác định thời điểm meter được ghi nhận của phiên bản framework.

## 10. Mẫu kiểm thử cardinality và semantics

Một cách đặt acceptance criteria rõ ràng:

| Trường hợp | Dữ liệu vào | Kết quả metric mong muốn |
| --- | --- | --- |
| Kênh WEB | `OrderSubmitted(id, WEB)` | Counter riêng có `sales.channel=WEB`. |
| Kênh STORE | `OrderSubmitted(id, STORE)` | Counter riêng có `sales.channel=STORE`. |
| Kênh thiếu | `OrderSubmitted(id, null)` | Tag `sales.channel=OTHER`, không tạo giá trị null. |
| Phương thức CARD | `PaymentCaptured(id, CARD)` | Counter payment có `payment.method=CARD`, không mang tag `sales.channel` do customizer orders tạo. |
| Không có hàng | `StockReservationRejected(id, OUT_OF_STOCK)` | Counter inventory có `rejection.reason=OUT_OF_STOCK`. |
| Gửi lại cùng event | Hai publication có cùng business ID | Counter publication có thể tăng hai lần; dữ liệu nghiệp vụ vẫn cần idempotency. |
| Event type không đăng ký | Một event khác | Không bị gắn các tag chuyên biệt ở ba rule trên. |

Các trường hợp trên tập trung vào **tên metric, event type và tập tag**. Cần đảm bảo cùng một test kiểm tra đường publish thật để phát hiện cấu hình sai, thay vì chỉ mô phỏng hàm tạo nhãn.

### 10.1. Khi tag không được ghi nhận

Điều tra theo thứ tự:

1. Event class được publish có đúng `OrderSubmitted.class` đã đăng ký không?
2. Bean `ModulithEventMetricsCustomizer` có xuất hiện trong Spring context không?
3. Instrumentation có tạo counter riêng cho event không?
4. Ở `MeterRegistry`, counter có tag `sales.channel` hay không?
5. Actuator metrics endpoint có đang expose và trả dữ liệu không?
6. Backend có nhận và giữ tag đó không?
7. Dashboard có đang truy vấn đúng tên metric không?

Những câu hỏi này giúp phân biệt **lỗi compile/config**, **lỗi event instrumentation** và **lỗi pipeline thu thập**. Đổi `Counter.Builder` liên tục khi lỗi thực tế nằm ở exporter thường chỉ làm khó việc điều tra.

### 10.2. Khi metric tự nhiên tăng số series

Xem gần đây có:

- thêm tag chứa ID, URL hoặc payload;
- tăng số giá trị enum mà không kiểm soát;
- bổ sung tenant/customer/user tag có cardinality lớn;
- thêm common tags ở tầng Micrometer registry ngoài customizer;
- nhiều event type bị dùng cùng tên metric và khác tập tag;
- backend tạo thêm dimensions từ resource labels hoặc instance IDs.

Phải xem **tổ hợp tags cuối cùng**, không chỉ ba tag do customizer tự định nghĩa.

## 11. Metric của event type và trace span liên quan nhau thế nào?

Một giao dịch có thể tạo cả metric publication và module entry span:

~~~mermaid
sequenceDiagram
    participant O as orders
    participant P as Spring EventPublisher
    participant M as Micrometer MeterRegistry
    participant L as payments listener
    participant T as Tracing backend

    O->>P: publishEvent(OrderSubmitted)
    P->>M: counter theo event type + sales.channel
    P->>L: dispatch event (đồng bộ hoặc bất đồng bộ)
    L->>T: module span nếu được instrument/export
    Note over M,T: Counter publication không chứng minh listener đã commit
~~~

Đây là sơ đồ **khái niệm**, không áp đặt chính xác thứ tự callback/counter/transaction cho mọi cấu hình Spring Modulith.

### Phân biệt ba dạng tín hiệu

| Nguồn | Câu hỏi được trả lời | Giới hạn |
| --- | --- | --- |
| **Metric `module.events.published`** | Bao nhiêu publication đã được instrumentation ghi nhận theo các tags có sẵn? | Không chứng minh listener đã hoàn tất. |
| **Metric riêng theo event type, có customizer** | Một loại event có bao nhiêu publication theo các thuộc tính nghiệp vụ được chọn? | Không phải bản ghi event duy nhất hoặc ledger. |
| **Module entry span của listener** | Lời gọi listener nào đã được quan sát, ở module nào, mất bao lâu? | Có thể bị sampling hoặc context propagation chia trace; span OK không tự chứng minh commit. |

Nếu event listener chạy trên executor khác hoặc qua message broker, **trace context propagation** cần được kiểm tra riêng. Thêm tag `sales.channel` vào counter không tự truyền trace ID sang listener. Ngược lại, cùng trace ID không đủ để bảo đảm xử lý event đúng một lần.

## 12. Hợp đồng telemetry cũng cần quản lý phiên bản

Một số thay đổi tưởng là refactor có thể phá dashboard:

| Thay đổi | Hậu quả tiềm tàng | Cách quản lý |
| --- | --- | --- |
| Đổi `OrderSubmitted` thành `OrderPlaced` | Tên counter riêng theo event type thay đổi. | Review migration metric name và cập nhật dashboard/alert. |
| Đổi `sales.channel=WEB` thành `sales.channel=ONLINE` | Query cũ không còn tìm được dữ liệu mới. | Quy ước thay đổi label values; chuyển đổi có thời hạn nếu cần. |
| Đổi `PaymentMethod` từ enum sang raw string | Cardinality có thể tăng bất ngờ. | Duy trì hàm normalize hoặc mapping giới hạn. |
| Đổi overload `BiConsumer` sang `Function` với tên builder mới | Có thể thay tên metric và tags mặc định. | Kiểm tra meter registry + contract test. |
| Nâng Spring Modulith / Boot | Có thể thay khả năng instrumentation hoặc biểu diễn backend. | BOM, tài liệu đúng version, integration test. |
| Thêm common tags cho mọi metric | Tổng số series nhân lên theo số giá trị tag mới. | Đánh giá cardinality toàn pipeline. |

Khi cần so sánh xu hướng qua các release, hãy ghi rõ **định nghĩa metric** cùng release ứng dụng, thay vì chỉ giữ mỗi tên. Một metric trùng tên nhưng đổi ý nghĩa đột ngột có thể nguy hiểm hơn metric bị đổi tên vì dashboard vẫn hiển thị nhưng kết luận sai.

### 12.1. Ai nên sở hữu customizer?

Đội sở hữu event type nên định nghĩa ý nghĩa và tập giá trị của trường được đưa vào telemetry. Đội nền tảng/observability có thể đặt quy ước chung về tên, cardinality và bảo mật. Ví dụ:

- Orders sở hữu ý nghĩa `SalesChannel`.
- Payments sở hữu danh mục `PaymentMethod`.
- Inventory sở hữu `RejectionReason`.
- Nhóm nền tảng review liệu ba thuộc tính có phù hợp thành metric tags hay không.

Nếu có nhiều bean `ModulithEventMetricsCustomizer` cùng tùy biến một event type, cần kiểm tra thứ tự áp dụng và cách kết hợp trong release đang dùng. Để tránh cấu hình khó đoán, gom chính sách của một event type vào một điểm rõ ràng hoặc có test contract bao phủ trường hợp kết hợp.

## 13. Những hiểu nhầm cần tránh

### “Tôi cần một counter mới cho mọi event type”

Không nhất thiết. Spring Modulith đã cung cấp counter tổng hợp và counter riêng theo event type trong phạm vi instrumentation hỗ trợ. Khi chỉ thêm một vài tag nghiệp vụ, dùng `ModulithEventMetricsCustomizer` và overload `BiConsumer` thường là lựa chọn phù hợp.

### “Gắn eventId làm tag sẽ dễ điều tra”

Có thể dễ tìm một lần, nhưng hậu quả là số series gần như bằng số event. Dùng log/trace có cấu trúc và kho event có quyền truy cập phù hợp để tra event cụ thể; **không dùng high-cardinality ID làm nhãn metric**.

### “Counter đã tăng nghĩa là listener thành công”

Không. Counter nói về publication được đo, không phải trạng thái cuối của consumer. Dùng listener metrics, Event Publication Registry, transaction logs, dữ liệu nghiệp vụ và đối soát khi cần xác nhận tiến độ hoặc kết quả xử lý.

### “Không thấy trace nghĩa là metric bị lỗi”

Tracing và metrics có pipeline, sampling và exporter khác nhau. Bắt đầu kiểm tra `MeterRegistry` hoặc Actuator metrics để xác minh counter, rồi mới điều tra trace backend nếu yêu cầu là truy vết.

### “Chỉ cần khai báo API trong compile scope là đủ”

API cung cấp extension points; còn cần runtime instrumentation, event flow và metric registry/exporter phù hợp. Nếu mã dùng `ModulithEventMetricsCustomizer` nhưng Spring không tạo bean hoặc core không được bật, sẽ không có customization có hiệu lực.

### “Có thể dùng chung một tag bất kỳ cho mọi event”

Không nên. Tag tên `status` có thể có ý nghĩa mâu thuẫn giữa các event. Hãy dùng tên rõ ngữ nghĩa, dữ liệu chuẩn hóa, cardinality hữu hạn và kế hoạch thay đổi theo phiên bản.

## 14. Checklist trước khi đưa vào production

- [ ] Có `spring-modulith-observability-api` ở compile scope cho code import customizer.
- [ ] Có `spring-modulith-observability-core` hoặc Insight starter ở runtime scope.
- [ ] BOM Spring Modulith tương thích Spring Boot và các artifact cùng dòng version.
- [ ] Bean customizer được Spring context tạo.
- [ ] Mỗi `metrics.customize(EventType.class, ...)` tham chiếu đúng event type thực sự được publish.
- [ ] Đã phân biệt counter tổng hợp với counter riêng theo event type.
- [ ] Tag nghiệp vụ có ý nghĩa được định nghĩa, tập giá trị hữu hạn và fallback rõ.
- [ ] Không đưa `orderId`, `eventId`, số thẻ, email hay payload tự do vào metric tags.
- [ ] Đã kiểm tra meter ở `MeterRegistry` hoặc Actuator sau kịch bản publish thật.
- [ ] Đã kiểm tra collector/exporter và tên/tag được backend thực sự hiển thị.
- [ ] Có integration test hoặc kiểm tra hồi quy cho tag name/value và ý nghĩa của metric.
- [ ] Đã xem xét hệ quả khi retry, event lặp và listener thất bại.
- [ ] Đã đánh giá cardinality của **toàn bộ** tập tag, gồm common tags.
- [ ] Dashboard và alert được cập nhật có kiểm soát khi đổi event class, tags hoặc builder.
- [ ] Actuator endpoint quản trị chỉ được expose cho tác nhân được cấp quyền.

## 15. Bài tập tự luyện

1. **Đọc metric:** Phân biệt ý nghĩa của `module.events.published` và `module.events.published.orders.OrderSubmitted`. Vì sao không nên suy ra số đơn duy nhất từ counter publication?
2. **Viết code:** Với event `InvoiceIssued(UUID invoiceId, InvoiceChannel channel)` và enum `InvoiceChannel {WEB, STORE, API}`, hãy đăng ký customizer gắn tag `invoice.channel`. Không dùng `invoiceId` làm tag.
3. **Compile scope:** Dự án khai báo Insight starter bằng Gradle `runtimeOnly` và không compile được `ModulithEventMetricsCustomizer`. Cần thay đổi dependency nào?
4. **Cardinality:** Một metric có 4 giá trị channel, 5 kết quả và 300.000 customerId. Vì sao thêm customerId là quyết định tồi? Thiết kế lại bộ nhãn.
5. **Kế thừa event:** Customizer đăng ký `OrderSubmitted.class` nhưng ứng dụng chuyển sang publish `OrderSubmittedV2`. Bạn sẽ kiểm tra và sửa gì trước khi kết luận metric framework bị lỗi?
6. **Overload:** Trường hợp nào nên dùng `BiConsumer`, trường hợp nào mới đáng cân nhắc `Function`? Thay đổi builder có thể ảnh hưởng gì đến dashboard?
7. **Điều tra:** Metric của `PaymentCaptured` tăng nhưng payment provider báo giao dịch thất bại. Những bằng chứng nghiệp vụ và observability nào cần xem?
8. **Truy vấn:** Trong một hệ thống metrics có hỗ trợ nhóm theo tag, hãy thiết kế bảng theo dõi publication của `StockReservationRejected` theo `rejection.reason`, tránh suy ra kết quả tồn kho cuối.
9. **Hồi quy:** Sau release mới, dashboard không còn thấy `sales.channel=WEB`. Hãy lần theo bean registration, event class, counter builder, registry, exporter và tên/tag trong backend.
10. **Kiến trúc:** Vì sao customizer event metric không thay thế kiểm thử ranh giới bằng Spring Modulith hoặc module graph từ Actuator?

## 16. Kết luận

Để **customize metric cho từng event type**, Spring Modulith cung cấp `ModulithEventMetricsCustomizer`. Đăng ký bean và gọi `metrics.customize(EventClass.class, (event, builder) -> …)` để bổ sung **tags nghiệp vụ có cardinality thấp** vào counter riêng của từng loại event. Với các yêu cầu đặc biệt hơn, overload nhận `Function<T, Counter.Builder>` cho phép kiểm soát việc tạo builder, nhưng đòi hỏi quản trị hợp đồng telemetry cẩn thận hơn.

Điểm cần giữ đúng là **đối tượng đo**: Spring Modulith ghi nhận *event publications*; phần tùy biến giúp phân loại publication theo thuộc tính sự kiện. Trạng thái listener, transaction commit, hiệu ứng bên ngoài hoặc tính đúng đắn nghiệp vụ phải được kiểm chứng bằng tín hiệu và dữ liệu phù hợp khác. Khi kết hợp metric event, module graph, Actuator, tracing và context propagation, nhóm phát triển sẽ có bức tranh vận hành cụ thể hơn mà vẫn biết giới hạn của từng loại bằng chứng.

### Tài liệu tham khảo chính thức

- [Spring Modulith — Production-ready Features: Observability Metrics và Individual Events Metric](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith 2.2.0 Javadoc — ModulithEventMetricsCustomizer](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html).
- [Spring Modulith 2.2.0 Javadoc — ModulithEventMetrics, hai overload customize](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetrics.html).
- [Spring Modulith — Appendix: artifact và dependency scope](https://docs.spring.io/spring-modulith/reference/appendix.html).
- [Spring Boot — Actuator Metrics endpoint](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
