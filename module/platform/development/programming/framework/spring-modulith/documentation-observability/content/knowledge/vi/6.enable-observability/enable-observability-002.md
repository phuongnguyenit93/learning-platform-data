# Thêm observability API khi cần tùy biến

## Mục tiêu học tập

Trong chương **Bật quan sát** của học phần **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**, mục tiêu là giúp bạn dùng Spring Modulith để quan sát tương tác giữa các application module của ứng dụng Spring Boot, đồng thời giữ rõ ranh giới giữa phần instrument do framework cung cấp và phần tùy biến do ứng dụng chịu trách nhiệm.

Sau bài học, bạn có thể:

1. Giải thích vai trò của `spring-modulith-observability-api`, `spring-modulith-observability-core` và `spring-modulith-starter-insight`.
2. Biết **khi nào phải đưa observability API vào compile classpath**, và khi nào chỉ cần runtime instrumentation.
3. Tùy biến **metric cho sự kiện nghiệp vụ** với `ModulithEventMetricsCustomizer` và hiểu điểm đặt của `ModulithEventMetrics`.
4. Tùy biến tên và các key-value của **module observation** bằng `ModulithObservationConvention`.
5. Phân biệt metric tags, trace attributes, correlation IDs và context propagation; chọn cardinality phù hợp.
6. Xác minh cấu hình bằng dependency tree, kiểm thử tạo event và dữ liệu quan sát thực tế, tránh khẳng định vượt quá tín hiệu đã thu thập.

> **Phạm vi phiên bản:** Các ví dụ dùng tên artifact và API có trong Spring Modulith **2.2.x**, với dependency được quản lý bằng BOM tương thích với Spring Boot của dự án. Một số dòng phiên bản cũ dùng tên artifact khác, chẳng hạn `spring-modulith-observability` thay vì tách `-core` và `-api`. Hãy kiểm tra tài liệu đúng phiên bản triển khai trước khi sao chép dependency.

## 1. “Bật quan sát” và “tùy biến quan sát” là hai nhu cầu khác nhau

Giả sử ứng dụng bán hàng có bốn application module:

- **orders:** tạo đơn và phát `OrderSubmitted`;
- **inventory:** giữ số lượng hàng cần bán;
- **payments:** ghi nhận kết quả thanh toán;
- **shipping:** chuẩn bị giao hàng khi thỏa điều kiện.

Nhóm phát triển muốn biết một yêu cầu xử lý đơn đi qua những module nào, ở mỗi ranh giới mất bao lâu và bao nhiêu sự kiện được phát. Spring Modulith có thể instrument những Spring component thuộc API của application module, tạo Micrometer observations/spans và phát metric dành cho application events.

**Nhu cầu mặc định:** bật observability để có dấu vết và metric do framework cung cấp. Không cần ứng dụng import bất kỳ interface tùy biến nào.

**Nhu cầu nâng cao:** bổ sung tag `channel=WEB` hoặc `channel=STORE` cho metric của `OrderSubmitted`, hoặc điều chỉnh observation convention cho lời gọi qua API module. Lúc này mã nguồn ứng dụng cần tham chiếu kiểu Java từ **observability API**.

Hai nhu cầu dẫn tới hai cấu hình classpath khác nhau. Sơ đồ khái quát:

~~~mermaid
flowchart LR
    A["Application code\nOrderSubmitted, configuration"] -->|"compile"| B["spring-modulith-observability-api"]
    C["Spring Modulith module APIs"] --> D["spring-modulith-observability-core"]
    B --> D
    D --> E["Micrometer Observation / Metrics"]
    E --> F["Registry, tracing bridge,\nexporter, monitoring backend"]
    G["spring-modulith-starter-insight"] -.->|"gom dependency runtime"| D
    G -.->|"thêm Actuator"| H["Spring Boot Actuator"]
~~~

Đây là sơ đồ **trách nhiệm**, không phải tuyên bố về đầy đủ các dependency chuyển tiếp. API cung cấp kiểu để code biên dịch; core cung cấp hạ tầng runtime; Micrometer và hệ thống thu thập quyết định dữ liệu đi tới đâu.

## 2. Phân biệt ba artifact chính

| Artifact | Vai trò trọng tâm | Scope thường dùng | Khi nào cần? |
| --- | --- | --- | --- |
| `spring-modulith-starter-insight` | Gói tiện dụng cho Actuator module và observability module. | Maven `runtime` / Gradle `runtimeOnly` | Muốn bật bộ tính năng Insight mặc định cho ứng dụng chạy. |
| `spring-modulith-observability-core` | Hạ tầng quan sát module và event publication. | `runtime` / `runtimeOnly` | Muốn observability mà không nhất thiết cần toàn bộ starter. |
| `spring-modulith-observability-api` | Các giao diện công khai để mã ứng dụng tùy biến event metrics và observation convention. | Maven compile mặc định / Gradle `implementation` | **Mã Java trực tiếp import interface hoặc lớp từ API này.** |

Tài liệu hiện hành cũng mô tả `spring-modulith-starter-insight` bao gồm Spring Boot Actuator và những thành phần cần thiết cho Insight. Tuy nhiên, nếu **dự án khai báo starter ở runtime**, mã nguồn trong `src/main/java` không nhận được quyền import các kiểu Java của starter vào **compile classpath** chỉ nhờ dependency đó.

### Quy tắc dễ nhớ

- Chỉ muốn **quan sát mặc định**: thêm starter Insight **hoặc** observability core phù hợp, chưa cần khai báo API độc lập.
- Muốn **viết bean Java để custom metric/convention**: thêm `spring-modulith-observability-api` vào **compile scope**.
- Muốn **xuất trace về Jaeger, Zipkin, Grafana/Tempo hoặc backend khác**: còn cần Micrometer tracing bridge/exporter, cấu hình sampling, endpoint và backend tương ứng; observability API **không thay thế** phần này.
- Muốn **sinh module graph/canvas thành tài liệu khi build/test**: dùng hỗ trợ documentation như `spring-modulith-docs`, không thêm observability API chỉ để tạo sơ đồ.
- Muốn **đảm bảo phát lại event publication**: đó là chức năng của cơ chế event publication registry/persistence, khác với metrics customizer.

## 3. Những tình huống thực sự cần thêm observability API

Một yêu cầu nên dẫn tới `spring-modulith-observability-api` khi ứng dụng **định nghĩa customization bằng code**. Ví dụ:

| Yêu cầu | Có cần import observability API? | Lý do |
| --- | --- | --- |
| Xem các span được tạo mặc định khi qua API module | Không | Runtime instrumentation do core phụ trách. |
| Có metric tổng số application events phát ra | Không, nếu chỉ dùng metric mặc định | Spring Modulith tạo các counter mặc định khi được bật và cấu hình phù hợp. |
| Thêm tag `channel=WEB/STORE` cho event `OrderSubmitted` | **Có** | Cần cung cấp bean `ModulithEventMetricsCustomizer`. |
| Thêm một giá trị convention ổn định cho module observations | **Có** | Cần triển khai `ModulithObservationConvention`. |
| Chỉ muốn đọc `/actuator/modulith` | Không | Đây là chức năng của `spring-modulith-actuator`/Insight starter. |
| Tăng tỷ lệ lấy mẫu traces | Thường không | Thuộc cấu hình tracing/management của Spring Boot và pipeline quan sát. |
| Truyền trace context qua message broker | Không bắt buộc | Chủ yếu liên quan hạ tầng tracing và cơ chế propagation; có thể cần integration riêng. |
| Bổ sung log có `orderId`, `traceId` | Không bắt buộc | Đây là bài toán logging/correlation; không nhất thiết cần API tùy biến của Modulith. |

**Điểm quyết định:** có sử dụng class/interface trong package `org.springframework.modulith.observability` tại thời điểm biên dịch hay không?

## 4. Cấu hình dependency đúng scope

Các ví dụ dưới đây giả định dự án đã dùng BOM Spring Modulith để đồng bộ phiên bản. Không điền một version tùy ý cho từng artifact vì điều đó dễ gây trộn các release không tương thích.

### 4.1. Gradle: starter ở runtime, API tùy biến ở compile

~~~groovy
dependencies {
    // Hạ tầng Insight hoạt động khi ứng dụng chạy
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'

    // Cho phép mã Java của ứng dụng import API customization
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
}
~~~

Lựa chọn này phù hợp khi muốn giữ cả Module Actuator lẫn observability mặc định và bổ sung một hoặc vài bean tùy biến. **Không cần** khai báo `spring-modulith-observability-core` lần nữa nếu starter đã mang nó theo.

### 4.2. Gradle: chỉ observability, không yêu cầu Module Actuator

~~~groovy
dependencies {
    runtimeOnly 'org.springframework.modulith:spring-modulith-observability-core'
    implementation 'org.springframework.modulith:spring-modulith-observability-api'

    // Ví dụ hạ tầng chung; thực tế còn phụ thuộc Spring Boot setup.
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

Bổ sung tracer bridge/exporter nếu cần quan sát traces trên hệ thống ngoài. Trong một ứng dụng đã có Micrometer và Actuator từ các starter khác, nên kiểm tra dependency tree trước khi khai báo thêm.

### 4.3. Maven: kết hợp runtime và compile

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
        <!-- Mặc định Maven scope là compile -->
    </dependency>
</dependencies>
~~~

Nếu muốn tách Core riêng:

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
</dependencies>
~~~

Trong phương án tách core, các dependency Micrometer/Spring Boot phục vụ instrumentation và xuất telemetry cần được lựa chọn theo cấu hình của ứng dụng.

### 4.4. Vì sao compile classpath dễ bị hiểu nhầm?

Giả sử bạn viết:

~~~java
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;
~~~

và chỉ khai báo `runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'`. Build có thể báo không tìm thấy `ModulithEventMetricsCustomizer`: Gradle **không đưa `runtimeOnly` lên compile classpath**. Đây là lỗi scope, không phải bằng chứng Spring Modulith không hỗ trợ API.

Sửa bằng cách khai báo:

~~~groovy
implementation 'org.springframework.modulith:spring-modulith-observability-api'
~~~

Cần phân biệt **dependency được starter kéo vào** với **dependency khả dụng khi compile mã ứng dụng**. Sau khi sửa, xác minh bằng:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Hoặc với Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.modulith
~~~

Trên Windows, dùng lệnh tương đương cho build wrapper (`gradlew.bat`) nếu shell không hỗ trợ `./gradlew`. Lệnh chỉ kiểm tra classpath; để xác nhận telemetry hoạt động còn cần chạy ứng dụng.

## 5. Hiểu metric mặc định trước khi tùy biến

Theo tài liệu production-ready của Spring Modulith 2.2, observability tạo hai nhóm counter cho application events:

1. **`module.events.published`**: tổng hợp các publication được quan sát.
2. **`module.events.published.$moduleIdentifier.$simpleEventTypeName`**: counter riêng cho một kiểu event trong một module, có thể được làm giàu bằng tag nghiệp vụ phù hợp.

Tập tag thấp cardinality được framework mô tả cho nhóm metric tổng hợp:

| Metric hoặc observation | Tag/key điển hình | Ý nghĩa |
| --- | --- | --- |
| `module.events.published` | `module.event.type` | Loại event đã phát. |
| `module.events.published` | `module.identifier` | Định danh application module. |
| `module.events.published` | `module.name` | Tên module. |
| Counter riêng từng event | `module.identifier`, `module.name` | Nguồn module của event cụ thể. |
| Module entry spans | `module.identifier`, `module.name`, `module.method`, `module.invocation-type` | Mô tả tương tác ở ranh giới module. |

**Tùy biến bằng `ModulithEventMetricsCustomizer` nhắm tới counter theo kiểu event.** Đừng mặc định việc thêm tag vào counter riêng cũng tự động thay đổi ý nghĩa của metric tổng hợp.

Ví dụ với module `orders`, event `OrderSubmitted` có thể tạo tên theo quy ước:

~~~text
module.events.published.orders.OrderSubmitted
~~~

Tập tag bổ sung do ứng dụng chọn cần có **ý nghĩa rõ ràng**. Nếu gắn `channel`, hãy xác định `channel` là kênh đặt hàng ở thời điểm **event được phát**, không nhất thiết là kênh thanh toán hoặc giao hàng của đơn.

### Metric không phải sổ cái nghiệp vụ

Counter tăng khi instrumentation quan sát một lần publication. Nó không tự chứng minh:

- Event đã được listener xử lý và commit;
- Event không bị giao lại;
- Giao dịch thanh toán ngoài hệ thống đã thành công;
- Số đơn hàng duy nhất bằng đúng giá trị counter.

Khi cần số liệu tài chính hoặc kết luận bất biến nghiệp vụ, dùng dữ liệu nghiệp vụ có thẩm quyền và đối soát. Metric phù hợp để quan sát lượng sự kiện, xu hướng, bất thường và theo dõi tương tác module.

## 6. Tùy biến event metrics bằng `ModulithEventMetricsCustomizer`

Đây là use case quan trọng nhất của observability API.

### 6.1. Định nghĩa event minh họa

Ứng dụng có một event miền nghiệp vụ:

~~~java
package com.example.shop.orders;

import java.util.UUID;

// Kiểu event do chính ứng dụng định nghĩa, không phải lớp Spring Modulith dựng sẵn.
public record OrderSubmitted(UUID orderId, String channel) {}
~~~

`channel` xuất phát từ một tập giá trị hữu hạn như `WEB`, `STORE`, `PARTNER`. `orderId` là dữ liệu cần để tìm đơn hàng cụ thể; **không nên đưa nó vào nhãn metric**.

### 6.2. Khai báo bean customization

~~~java
package com.example.shop.config;

import com.example.shop.orders.OrderSubmitted;
import java.util.Locale;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithEventMetricsCustomizer;

@Configuration(proxyBeanMethods = false)
public class ModuleMetricsConfiguration {

    @Bean
    ModulithEventMetricsCustomizer orderSubmittedMetrics() {
        return metrics -> metrics.customize(
            OrderSubmitted.class,
            (event, builder) -> {
                builder.tag("channel", normalizeChannel(event.channel()));
            }
        );
    }

    private static String normalizeChannel(String input) {
        if (input == null) {
            return "OTHER";
        }

        return switch (input.toUpperCase(Locale.ROOT)) {
            case "WEB" -> "WEB";
            case "STORE" -> "STORE";
            case "PARTNER" -> "PARTNER";
            default -> "OTHER";
        };
    }
}
~~~

**Giải thích dòng quan trọng:**

- `ModulithEventMetricsCustomizer` là một interface của observability API; Spring Modulith tiếp nhận bean này khi tạo event metric.
- `metrics.customize(OrderSubmitted.class, ...)` chọn **kiểu event cụ thể**.
- Đối số thứ hai là callback được cung cấp event và Micrometer `Counter.Builder`; callback dùng `builder.tag(...)` để bổ sung tag trước khi counter tương ứng được tạo.
- `normalizeChannel(...)` giới hạn số giá trị của tag để giữ cardinality thấp.
- Không cần tự tạo `Counter` hoặc gọi `increment()` trong bean trên; framework vẫn quản lý bước ghi nhận publication theo cơ chế observability của nó.

Cấu trúc API được mô tả bởi interface `ModulithEventMetrics`: overload dùng `BiConsumer<T, Counter.Builder>` tùy chỉnh builder cho event; overload khác nhận `Function<T, Counter.Builder>` khi cần chủ động cách tạo builder. Với phần lớn nhu cầu chỉ thêm một vài nhãn, **overload BiConsumer đơn giản hơn và dễ bảo trì hơn**.

### 6.3. Tại sao cần lọc kênh trước khi gắn tag?

Giả sử nguồn nhận `channel` từ HTTP request và được đưa nguyên vẹn vào event. Nếu người dùng gửi `channel=WEB-123456` cho mỗi request, số series metric sẽ tăng nhanh.

Bộ đo thường phân chia time series theo tổ hợp các nhãn. Nếu có:

- 20 application modules;
- 15 kiểu event;
- 3 kênh kinh doanh;

thì số tổ hợp có thể lớn nhưng vẫn được kiểm soát theo thiết kế. Nếu thay ba kênh bằng hàng trăm nghìn `orderId`, cardinality dễ vượt ngân sách của metric backend.

Vì vậy:

- **Tốt:** `channel=WEB|STORE|PARTNER|OTHER`; `result=SUCCESS|REJECTED`.
- **Cân nhắc kỹ:** tên method/module khi số lượng động hoặc thay đổi liên tục.
- **Tránh làm metric tag:** `orderId`, `customerId`, email, URL có tham số động, trace ID, UUID, payload event.

Thông tin có cardinality cao hoặc nhạy cảm có thể cần trong **trace/log có phân quyền**, nhưng ngay cả ở đó cũng phải tuân thủ quy tắc bảo vệ dữ liệu và chính sách retention.

### 6.4. Tùy biến nhiều kiểu event

Có thể đăng ký nhiều quy tắc trong cùng một bean nếu chúng cùng thuộc một chính sách telemetry:

~~~java
@Bean
ModulithEventMetricsCustomizer shopEventMetrics() {
    return metrics -> {
        metrics.customize(OrderSubmitted.class,
            (event, builder) -> builder.tag(
                "channel", normalizeChannel(event.channel())
            )
        );

        metrics.customize(PaymentSettled.class,
            (event, builder) -> builder.tag(
                "settlement_type", normalizeSettlement(event.type())
            )
        );
    };
}
~~~

Đoạn trên là **phần trích trong class cấu hình minh họa**: `PaymentSettled` và `normalizeSettlement` là kiểu/hàm miền nghiệp vụ bạn phải định nghĩa. Trước khi thêm nhiều event, hỏi xem nhãn này có thực sự hỗ trợ truy vấn/alert hay chỉ làm tăng độ phức tạp.

Nếu hai bean cùng tùy biến một kiểu event hoặc cùng tên nhãn, cần kiểm tra hành vi kết hợp của release đang dùng; tránh phụ thuộc vào thứ tự áp dụng callback nếu chính sách đó chưa được xác định rõ.

## 7. Tùy biến module observation bằng `ModulithObservationConvention`

Một nhu cầu khác là đổi cách **module invocations** được thể hiện trong Micrometer observations.

Spring Modulith cung cấp `ModulithObservationConvention`, một `ObservationConvention<ModulithContext>`. Convention mặc định sử dụng dữ liệu của `ModulithContext` như module, invocation và các low/high-cardinality key values. Khi có yêu cầu rõ ràng, ứng dụng có thể đăng ký bean convention riêng.

### 7.1. Khi nào nên điều chỉnh convention?

- Chuẩn hóa tên hoặc nhãn của module span để phù hợp dashboard của tổ chức.
- Gắn một thuộc tính ổn định như `business.domain=commerce` vào các module observations.
- Điều chỉnh các key values cho một hệ thống tracing/metrics có quy ước đặt tên chung.
- Giữ ổn định một hợp đồng quan sát nội bộ khi đổi công cụ giám sát.

Không cần viết convention riêng nếu bạn chỉ muốn một trường chung như `service.name` hay environment cho mọi metric; những trường này có thể phù hợp hơn khi cấu hình resource attributes/common tags của hạ tầng Micrometer/tracing.

### 7.2. Ví dụ thêm key có cardinality hữu hạn

~~~java
package com.example.shop.config;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration(proxyBeanMethods = false)
public class ModuleObservationConfiguration {

    @Bean
    ModulithObservationConvention shopModuleConvention() {
        return new ModulithObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
                return context.getLowCardinalityValues()
                        .and(KeyValue.of("business.domain", "commerce"));
            }
        };
    }
}
~~~

**Ý nghĩa:** ví dụ giữ các key values hiện có của `ModulithContext` và bổ sung một nhãn ổn định do ứng dụng kiểm soát. Các phương thức khác sử dụng default methods của interface, vì vậy không cố thay đổi `getName()` hay `getContextualName()`.

Những điều cần kiểm tra trong hệ thống thực:

1. Nếu tag đã có từ common tags, tránh tạo trùng tên và kiểm tra cách Micrometer xử lý tag trùng.
2. Thay đổi convention có thể ảnh hưởng truy vấn, dashboard và alert hiện hữu. Cần review như **thay đổi hợp đồng telemetry**.
3. Không nên xóa ngẫu nhiên các key mà framework cung cấp (`module.identifier`, `module.invocation-type`, ...) vì chúng giúp phân tích ranh giới module.
4. Khi điều chỉnh high-cardinality keys, cần hiểu sự khác nhau giữa **trace attribute** và **metric tag** trong backend sử dụng; không giả định dữ liệu nhạy cảm được xử lý an toàn chỉ vì đặt ở nhóm high-cardinality.
5. Tên/kiểu API cụ thể có thể khác theo dòng release. Trước khi nâng Spring Modulith, so sánh Javadoc của `ModulithObservationConvention` và `ModulithContext` ở phiên bản đích.

### 7.3. Khác biệt giữa hai cơ chế tùy biến

| Tiêu chí | `ModulithEventMetricsCustomizer` | `ModulithObservationConvention` |
| --- | --- | --- |
| Mục tiêu trực tiếp | Counter riêng theo kiểu application event. | Observation của tương tác module, gồm tên và các key values theo convention. |
| Điểm mở rộng | `ModulithEventMetrics.customize(EventClass, callback)`. | Bean triển khai `ModulithObservationConvention`. |
| Đối tượng dữ liệu | Event cụ thể và `Counter.Builder`. | `ModulithContext` của invocation được quan sát. |
| Ví dụ sử dụng | Thêm `channel` vào `OrderSubmitted`. | Thêm `business.domain` vào module observation. |
| Rủi ro chính | Bùng nổ số series khi tag có cardinality cao. | Làm thay đổi tên/tag span, phá truy vấn và dashboard. |
| Yêu cầu dependency | Observability API ở compile và core/starter ở runtime. | Tương tự. |

Về phạm vi, **event metrics customizer không tự thay đổi module span**, và **module observation convention không mặc định tùy biến mọi event counter theo tên event**. Hãy chọn đúng extension point thay vì cố dùng một hook cho mọi nhu cầu.

## 8. Đặt ranh giới giữa ứng dụng, Micrometer và tracing backend

Một hiểu nhầm thường gặp là thêm `spring-modulith-observability-api` sẽ làm span tự xuất hiện trên Grafana hoặc Zipkin. Luồng thực tế có thêm các bước:

~~~mermaid
sequenceDiagram
    participant Biz as orders / payments
    participant Mod as Modulith observability core
    participant Mic as Micrometer Observation
    participant Bridge as Tracing bridge / exporter
    participant Back as Backend quan sát

    Biz->>Mod: Phát OrderSubmitted hoặc gọi API module
    Mod->>Mic: Tạo observation / counter
    Note over Mod,Mic: Customizer/convention thay đổi metadata
    Mic-->>Bridge: Tín hiệu nếu tracing được cấu hình
    Bridge-->>Back: Xuất spans theo sampling và transport
    Note over Back: Dashboard chỉ hiển thị dữ liệu đã nhận
~~~

### 8.1. API và core không thay exporter

Nếu code customizer compile thành công nhưng không thấy trace:

- Xác nhận ứng dụng đã bật runtime instrumentation qua core/starter.
- Xác nhận có Micrometer Observation/Tracing và bridge/exporter phù hợp với Spring Boot hiện dùng.
- Xác nhận endpoint của backend, authentication và kết nối mạng.
- Kiểm tra sampling trong môi trường test; sampling thấp có thể khiến không thấy span.
- Đảm bảo request đã thật sự đi qua điểm được Spring Modulith instrument, ví dụ lời gọi component thuộc API của một application module.

**API compile thành công là bằng chứng classpath, không phải bằng chứng dữ liệu đã được thu thập và xuất đi.**

### 8.2. Context propagation là chủ đề liên quan nhưng riêng biệt

Tương tác bất đồng bộ có thể đi qua `@Async`, executor, scheduler, transaction event listener hoặc message broker. Để các span liên quan nhìn thấy trong cùng trace hoặc có link phù hợp, cần propagation và instrumentation tương ứng qua những ranh giới này.

Thêm event metric tag `channel` không tự làm trace context đi theo message. Ngược lại, việc hai span chia sẻ traceId cũng không đảm bảo event không lặp hoặc kết quả nghiệp vụ đã commit.

**Định danh khác chức năng:**

- `traceId`: giúp theo dõi tương quan một chuỗi tác vụ quan sát.
- `orderId`: định danh thực thể nghiệp vụ qua nhiều request và lần retry.
- `eventId` hoặc `idempotencyKey`: dùng để phát hiện/tránh xử lý trùng một thao tác hoặc message.

Chỉ số và trace được xây cho khả năng điều tra; nghiệp vụ vẫn cần ràng buộc dữ liệu, idempotency và kiểm thử riêng.

## 9. Chiến lược đặt metric tags an toàn

Trước khi thêm tag, trả lời bốn câu hỏi: **dữ liệu có ý nghĩa gì, có bao nhiêu giá trị, ai sử dụng và có cần giữ ổn định lâu dài không?**

| Thuộc tính | Có phù hợp làm metric tag? | Lý do |
| --- | --- | --- |
| `channel=WEB/STORE/PARTNER` | Thường phù hợp | Tập giá trị hữu hạn và hữu ích để so sánh lưu lượng. |
| `event.result=ACCEPTED/REJECTED` | Có thể phù hợp | Phân tách kết quả, nếu ý nghĩa đã được chuẩn hóa rõ. |
| `module.identifier` | Phù hợp theo metric framework | Giúp tổng hợp theo module; số lượng tương đối hữu hạn. |
| `orderId` | Không | Số giá trị tăng theo từng đơn, tạo rất nhiều time series. |
| `customerEmail` | Không | Vừa có cardinality cao vừa chứa thông tin cá nhân. |
| `traceId` | Không | Gần như mỗi trace có giá trị riêng. |
| `exception.message` | Thường không | Có thể chứa dữ liệu động hoặc nhạy cảm. |
| `tenantId` hàng trăm nghìn giá trị | Thường không | Dễ phá ngân sách cardinality; cân nhắc phân nhóm hữu hạn thay thế. |

### 9.1. Bất biến đặt tên

Hãy định nghĩa ý nghĩa trước khi triển khai:

- `channel` phản ánh **kênh tạo đơn đã được normalize**, không phải raw HTTP header.
- `module.identifier` dùng đúng định nghĩa module của framework, không tự ghi nhãn khác mang cùng tên.
- `result` cần mô tả trạng thái ở **thời điểm đo**: event đã được phát khác với handler đã hoàn tất hoặc transaction đã commit.
- Không tái sử dụng tên metric cũ cho một ý nghĩa hoàn toàn mới mà không có kế hoạch migration.

### 9.2. Giá trị event nên được kiểm soát tại nguồn

Dữ liệu người dùng nhập vào cần được chuẩn hóa **trước khi** tạo metric tag. Từ `OrderSubmitted(channel="web")`, `OrderSubmitted(channel="WEB")` và `OrderSubmitted(channel="web-mobile-v42")`, ta có thể quy về một trong số ít nhóm được thống nhất.

Không dùng biểu thức tạo tag bằng chuỗi không giới hạn, ví dụ:

~~~java
// KHÔNG NÊN: mỗi orderId tạo ra một giá trị nhãn khác nhau.
builder.tag("order.id", event.orderId().toString());
~~~

Nếu cần truy tìm sự kiện của một đơn, gửi `orderId` qua log có cấu trúc hoặc trace attribute đã được đánh giá chính sách bảo mật; không dùng metric label để lập chỉ mục từng thực thể.

## 10. Kiểm chứng cấu hình từ classpath đến dữ liệu thực

Thêm một bean customization là thay đổi hành vi quan sát. Nên kiểm tra theo tầng để tránh lẫn nguyên nhân:

| Tầng | Câu hỏi xác minh | Ví dụ phép kiểm tra |
| --- | --- | --- |
| **Compile** | Mã import API có biên dịch? | `compileJava`, xem `compileClasspath`. |
| **Runtime** | Core/starter có trên runtime classpath? | `runtimeClasspath`, khởi động ứng dụng. |
| **Bean registration** | Spring nhận bean customizer/convention? | Context test kiểm tra loại bean và cấu hình. |
| **Publication** | App có thật sự phát loại event đã đăng ký? | Gọi kịch bản `OrderSubmitted`; kiểm tra publisher path. |
| **Metric** | Meter được tạo với tên và tag mong muốn? | Kiểm tra `MeterRegistry` hoặc endpoint metrics được bật. |
| **Tracing** | Có module span ở điểm invocation được instrument? | Kiểm tra trace của luồng liên module. |
| **Export** | Backend nhận được tín hiệu? | Kiểm tra collector, exporter, sampling và dashboard. |
| **Bảo mật & chi phí** | Có nhãn nhạy cảm/cardinality bất thường? | Review tag và ngân sách series. |

### 10.1. Quy trình xác minh bằng kịch bản nghiệp vụ

Giả sử nhóm đã thêm customizer `OrderSubmitted`:

1. Khởi động ứng dụng với `spring-modulith-observability-core` hoặc starter Insight; xác nhận bean customization không gây lỗi khởi tạo.
2. Phát ít nhất hai sự kiện với `channel="WEB"` và `channel="STORE"` từ đường nghiệp vụ hợp lệ.
3. Kiểm tra meter theo tên event và nhãn `channel`. Kỳ vọng tag nhận `WEB` và `STORE`, không có `orderId`.
4. Phát event với một giá trị ngoài danh sách, ví dụ `channel="MOBILE-UNKNOWN"`. Kỳ vọng nhãn `OTHER` nhờ hàm normalize.
5. Kiểm tra metric tổng hợp `module.events.published` riêng; xác nhận ý nghĩa của nó không bị diễn giải là số đơn duy nhất.
6. Nếu kỳ vọng span đi kèm, chạy tương tác module đã được instrument và xác minh tracing bridge/exporter.
7. Review dashboard/alert sau thay đổi nhãn; giữ tương thích hoặc cập nhật truy vấn có kiểm soát.

Một ví dụ cấu hình môi trường kiểm thử sử dụng Actuator metrics:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Ví dụ này chỉ kích hoạt khả năng **truy cập metrics qua Actuator HTTP** theo cấu hình Spring Boot phù hợp. Nếu muốn endpoint Prometheus, cần registry và expose endpoint tương ứng. Trong sản phẩm thực tế, hãy bật endpoint quản trị theo quyền hạn và topology của hệ thống.

Có thể dùng `GET /actuator/metrics` để duyệt tên meter khi endpoint được expose:

~~~bash
curl --fail-with-body http://localhost:8080/actuator/metrics
~~~

Tiếp đó kiểm tra meter theo tên riêng của event. Tên HTTP hiển thị và cách backend chuẩn hóa có thể khác giữa Micrometer và Prometheus; nên xác minh trực tiếp trong registry/endpoint của ứng dụng rồi mới viết query dashboard.

### 10.2. Ý tưởng kiểm thử hồi quy có ý nghĩa

Kiểm thử nên đánh vào **hợp đồng telemetry**:

- Event `OrderSubmitted("WEB")` tạo một meter có tag `channel=WEB` trong tập metric kỳ vọng.
- Giá trị lạ không tạo nhãn mới không giới hạn, được ánh xạ `OTHER`.
- `ModulithObservationConvention` vẫn giữ key values mặc định cần thiết cho dashboard.
- Hai kiểu event khác nhau không vô tình bị gán cùng ý nghĩa metric nếu thiết kế yêu cầu phân biệt.
- Không có nhãn `orderId` hay `customerEmail`.

Kiểm thử chỉ “bean tồn tại” không chứng minh callback đã chạy với event thực. Nếu dự án có integration test context, hãy kích hoạt luồng phát event thật và kiểm tra kết quả quan sát; đồng thời tránh viết test chỉ mô phỏng lại từng dòng của chính hàm normalize mà bỏ qua integration path.

### 10.3. Diễn giải thành công đúng mức

Một kịch bản có counter tăng, span được xuất và Actuator healthy **không chứng minh** đơn hàng đã được tính tiền đúng hoặc event không trùng. Đây là bằng chứng instrumentation đã thu thập tín hiệu theo định nghĩa. Sự đúng đắn nghiệp vụ vẫn dựa trên invariant, transaction, deduplication, kiểm thử và đối soát.

## 11. Các lỗi thường gặp và cách tìm nguyên nhân

### Lỗi 1 — Không compile được `ModulithEventMetricsCustomizer`

**Triệu chứng:** IDE báo không tìm thấy package `org.springframework.modulith.observability` hoặc kiểu customizer.

**Nguyên nhân hay gặp:** chỉ có starter/core ở `runtimeOnly`, không khai báo `spring-modulith-observability-api` trong compile classpath.

**Xử lý:** thêm artifact API ở `implementation` hoặc Maven compile; kiểm tra version bằng BOM và dependency tree.

### Lỗi 2 — Code compile nhưng metric không có tag mới

Khả năng cần điều tra:

- Chưa bật runtime observability core/starter.
- Event thực tế có lớp khác với kiểu được đăng ký trong `metrics.customize(...)`.
- Không có đường phát event hoặc không chạy kịch bản này.
- Bean cấu hình nằm ngoài phạm vi component scan hoặc không được tạo vì profile/condition.
- Đang xem metric tổng hợp thay vì counter **riêng theo event**.
- Dashboard đang hiển thị series cũ hoặc mất tag qua bước chuyển đổi/export.
- Tag mới chưa được backend ghi nhận trong cửa sổ dữ liệu đang xem.

**Xử lý:** kiểm tra bean registration, event type, runtime registry, rồi mới kiểm tra exporter và dashboard.

### Lỗi 3 — Có module spans nhưng không thấy trên hệ thống tracing

Quan sát module core có thể đã chạy nhưng **chưa có tracing bridge/exporter** hoặc bị sampling. Cần xác minh cấu hình Spring Boot phù hợp và backend tiếp nhận. Không có căn cứ để sửa bằng cách thêm API customization nếu chỉ thiếu exporter.

### Lỗi 4 — Dashboard bị tăng số lượng series sau khi thêm tag

Tình huống thường do lấy tag từ ID hoặc giá trị đầu vào không giới hạn. Cách xử lý là thay nhãn bằng **tập giá trị hữu hạn**, giảm chiều đo không cần thiết và đánh giá tác động với metric backend. Có thể cần xóa/chờ hết retention của series cũ tùy hệ thống lưu trữ.

### Lỗi 5 — Mất các nhãn mặc định sau khi viết convention

Nếu custom convention trả về một tập key values mới mà không giữ phần framework cung cấp, dashboard phụ thuộc `module.identifier` hoặc `module.method` có thể mất dữ liệu. Ví dụ ở phần 7 sử dụng `context.getLowCardinalityValues().and(...)` để giữ các low-cardinality values từ context. Khi đổi tên convention, kiểm tra cả low/high-cardinality key values, tên observation và span mà công cụ tiêu thụ kỳ vọng.

### Lỗi 6 — Nhầm sự kiện đã phát với xử lý nghiệp vụ hoàn tất

`module.events.published` đo theo publication instrumentation, không phải bản ghi ledger hoặc bằng chứng mọi event consumer đã commit. Nếu cần theo dõi listener retries, publication registry và độ trễ xử lý, hãy thiết kế các metric tương ứng với **định nghĩa rõ ràng**, kết hợp dữ liệu event registry và tracing; đừng đổi tên tag để khiến metric mặc định có vẻ mang nghĩa khác.

## 12. Checklist trước khi đưa customization vào production

- [ ] Đã xác định nhu cầu: tùy biến event counter hay module observation?
- [ ] Đã chọn Spring Modulith version tương thích Spring Boot và quản lý đồng bộ bằng BOM?
- [ ] Có `spring-modulith-observability-api` ở **compile scope** khi code import API?
- [ ] Có core/starter tương ứng trên **runtime classpath**?
- [ ] Đã xác minh bean customizer/convention được Spring đăng ký?
- [ ] Tag mới có tập giá trị nhỏ, ổn định và ý nghĩa được tài liệu hóa?
- [ ] Không đưa dữ liệu nhạy cảm, `orderId`, `traceId`, email vào metric labels?
- [ ] Có kiểm tra metric riêng theo event, không đánh đồng với metric tổng hợp?
- [ ] Có kiểm tra propagation, tracing bridge và exporter nếu cần traces?
- [ ] Dashboard, alert, recording rules được cập nhật hoặc duy trì tương thích?
- [ ] Có kiểm thử trường hợp tag lạ, lỗi cấu hình và dữ liệu không được export?
- [ ] Chỉ expose các Actuator endpoint cần thiết cho actor được cấp quyền?

## 13. Bài tập tự luyện

1. Một dự án đã dùng `runtimeOnly('spring-modulith-starter-insight')` và muốn viết bean `ModulithEventMetricsCustomizer`. Thay đổi Gradle nhỏ nhất là gì? Giải thích vì sao cần thêm dependency này dù starter có các dependency chuyển tiếp.
2. Team muốn thêm `orderId` làm tag để điều tra đơn cụ thể. Những rủi ro cardinality và bảo mật là gì? Đề xuất một cách làm thay thế.
3. `OrderSubmitted` có trường `channel` với giá trị từ request bên ngoài. Hãy thiết kế tập giá trị hữu hạn và cơ chế xử lý giá trị lạ trước khi gắn nhãn.
4. Một dashboard đang dựa vào `module.identifier`. Khi tùy biến `ModulithObservationConvention`, bạn cần giữ và kiểm thử điều gì?
5. Code customizer đã compile và bean có mặt trong context nhưng không thấy `channel` trên dashboard. Hãy nêu thứ tự điều tra từ event publication, runtime meter registry tới exporter.
6. Vì sao traceId không thay thế được eventId/idempotencyKey khi một event được giao lại?
7. Khi chỉ cần module graph qua `/actuator/modulith`, tại sao không nhất thiết thêm observability API ở compile scope?

## 14. Kết luận

Khi chỉ cần các khả năng quan sát mặc định, Spring Modulith hỗ trợ triển khai gọn bằng `spring-modulith-starter-insight` hoặc `spring-modulith-observability-core` ở runtime. **Chỉ thêm `spring-modulith-observability-api` ở compile scope khi mã ứng dụng thật sự cần dùng extension points để tùy biến**, chủ yếu là:

- `ModulithEventMetricsCustomizer`: làm giàu counter theo từng kiểu application event bằng nhãn nghiệp vụ có cardinality được kiểm soát.
- `ModulithObservationConvention`: điều chỉnh quy ước đặt tên/key values cho observations của tương tác module.

Tùy biến quan sát giúp nhóm vận hành trả lời câu hỏi nghiệp vụ-vận hành chính xác hơn, ví dụ lưu lượng đặt hàng theo kênh hoặc độ trễ gọi API module. Nó **không tự triển khai tracing backend**, không tự truyền context qua mọi ranh giới bất đồng bộ và không chứng minh mọi giao dịch nghiệp vụ đã đúng. Luôn kiểm tra scope, event type, tags, instrumented path và dữ liệu thu thập thực tế sau khi thay đổi.

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features: Observing Application Modules, Event Metrics, Conventions](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith — Appendix: Artifacts và typical scopes](https://docs.spring.io/spring-modulith/reference/appendix.html).
- [Javadoc: ModulithEventMetricsCustomizer](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetricsCustomizer.html).
- [Javadoc: ModulithEventMetrics](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithEventMetrics.html).
- [Javadoc: ModulithObservationConvention](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservationConvention.html).
- [Javadoc: ModulithContext](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html).
