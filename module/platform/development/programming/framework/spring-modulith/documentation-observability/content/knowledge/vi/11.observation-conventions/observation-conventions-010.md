# Kiểm tra convention với cả metrics và traces

> **Chương:** Observation convention  
> **Phạm vi:** Kiểm chứng cách `ModulithObservationConvention` định nghĩa tên và metadata của module observation khi được chuyển thành Micrometer metrics và distributed tracing trong ứng dụng Spring Boot.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vai trò của `ObservationConvention`, `ModulithObservationConvention`, `ModulithContext` và `ObservationRegistry`.
2. Phân biệt **tên observation dùng cho meter**, **contextual name dùng cho span**, **low-cardinality key-values** và **high-cardinality key-values**.
3. Đăng ký một `ModulithObservationConvention` dưới dạng Spring bean, giữ hành vi mặc định và bổ sung một tag ổn định.
4. Kiểm tra tác động của convention ở **hai đầu ra độc lập**: Actuator/Micrometer Timer và trace/span trên hệ thống tracing.
5. Nhận ra các khác biệt do cấu hình handler, sampling, exporter, context propagation, cách instrument module và phiên bản thư viện.
6. Thiết kế bài kiểm tra có đối chứng, tránh hiểu nhầm “có metrics” nghĩa là “có traces”, hoặc coi một event publication counter là module entry Timer.

## 2. Một convention, nhiều đường xuất dữ liệu

Spring Modulith có thể quan sát các lời gọi đi vào những Spring component thuộc **API của application module**. Các thao tác này được biểu diễn bằng Micrometer `Observation`. `ModulithObservationConvention` quyết định cách đặt tên observation và các key-value gắn với `ModulithContext`.

Ví dụ một request tạo đơn hàng gọi sang module `payments`:

~~~mermaid
flowchart LR
    Request["HTTP POST /orders"] --> Orders["orders.placeOrder()"]
    Orders --> Payment["payments.authorize()"]
    Payment --> Interceptor["Spring Modulith module-entry interceptor"]
    Interceptor --> Convention["ModulithObservationConvention<br/>name / contextual name / key-values"]
    Convention --> Obs["Micrometer Observation"]
    Obs --> MetricHandler["Metrics handler"]
    Obs --> TraceHandler["Tracing handler"]
    MetricHandler --> Timer["Timer theo observation name<br/>low-cardinality tags"]
    TraceHandler --> Span["Span / trace<br/>low + high-cardinality attributes"]
~~~

**Convention không tự gửi metric hoặc trace.** Nó xác định tên và metadata cho operation; các handler/registries mới quyết định dữ liệu có trở thành meter hay span, và exporter mới quyết định dữ liệu có đến backend hay không.

Hai phép kiểm tra phải được thực hiện độc lập:

| Đầu ra | Phương tiện xem | Kết quả cần tìm |
| --- | --- | --- |
| **Metrics** | `MeterRegistry`, `GET /actuator/metrics/{name}` hoặc Prometheus | Timer của operation, COUNT/duration và **low-cardinality tags** |
| **Traces** | Backend tracing như Tempo, Jaeger, Zipkin | Span của module entry, tên dễ đọc, **low- và high-cardinality attributes**, trace/parent context |

Một thay đổi convention được coi là kiểm chứng đầy đủ khi bạn đã xác định **đúng observation được instrument** và thấy những gì cần thấy trên **cả hai đường** tương ứng.

## 3. Những khái niệm cần thống nhất

| Khái niệm | Trách nhiệm | Phân biệt với |
| --- | --- | --- |
| `Observation` | Operation có vòng đời start, scope, stop; chứa context/key-values | Không đồng nghĩa một span đã export |
| `Observation.Context` | Lưu metadata nội bộ để convention/handler sử dụng | Không phải mọi giá trị trong context đều thành tags |
| `ObservationConvention<T>` | Cấp tên, contextual name và low/high-cardinality values theo context type | Không phải tracing exporter |
| `ModulithObservationConvention` | Convention chuyên biệt của Spring Modulith cho `ModulithContext` | Không phải convention cho mọi HTTP/JDBC observation |
| `ObservationRegistry` | Lưu cấu hình handler, convention, filter/predicate; quản lý việc dispatch vòng đời | Không thay thế `MeterRegistry` |
| `MeterRegistry` | Lưu/đẩy meters (Timer, Counter, Gauge...) | Không ghi riêng từng span |
| Tracing handler + `Tracer` | Biến observation thành span, mang trace context | Không tự tạo counter publication |
| `Module graph` / Actuator `modulith` | Mô hình module/dependency được nhận diện | Không chứng minh một operation đã xảy ra |

Trong Spring Modulith, `ModulithObservationConvention` là một interface kế thừa `ObservationConvention<ModulithContext>`. Bốn phương diện bạn thường kiểm tra:

~~~java
// Chữ ký minh họa từ hợp đồng interface,
// không phải đoạn code phải sao chép để định nghĩa interface mới.
String getName();
String getContextualName(ModulithContext context);
KeyValues getLowCardinalityKeyValues(ModulithContext context);
KeyValues getHighCardinalityKeyValues(ModulithContext context);
~~~

Ngoài ra, `supportsContext(Observation.Context context)` quyết định convention có thích hợp với context được truyền vào hay không. Interface chuyên biệt Spring Modulith đã có triển khai mặc định cho các phương thức trên.

## 4. Tên observation và tên span có thể khác nhau

Đừng nhầm hai cơ chế đặt tên:

- `getName()`: tên operation ổn định, thường là **meter name** khi metrics handler tạo Timer. Giá trị này cần ổn định để dashboard có thể tổng hợp nhiều lần chạy.
- `getContextualName(context)`: tên dễ đọc, có bối cảnh thao tác cụ thể; tracing handler có thể dùng làm **span name**. Tùy version và handler, tên span thực tế có thể được chuẩn hóa thêm.

Ví dụ khái niệm:

~~~text
Observation name: "module.invocations"     → Timer /actuator/metrics/module.invocations
Contextual name:  "Payments > authorize"   → tên span có ý nghĩa trong trace UI
~~~

`module.invocations` là giá trị mặc định được định nghĩa trong `ModulithContext.DEFAULT_CONVENTION_NAME` của Spring Modulith hiện hành. Tên contextual ở đây **chỉ minh họa** cách đọc, không cam kết chuỗi giống hệt ở mọi ứng dụng.

Một observation name như `module.invocations.orders.ORD-123` là lựa chọn nguy hiểm: nó tạo tên meter khác nhau theo từng đơn. Hãy để tên ổn định, dùng **low-cardinality tags** cho các chiều phân nhóm cần thiết và **high-cardinality values** cho ngữ cảnh chi tiết của trace nếu an toàn.

## 5. Low cardinality và high cardinality đi đâu?

Micrometer tách hai loại key-values vì mục đích thống kê khác nhau:

| Kiểu metadata | Ví dụ | Metrics handler | Tracing handler |
| --- | --- | --- | --- |
| **Low cardinality** | `module.identifier=payments`, `module.name=Payments`, `deployment.tier=lab` | Có thể tạo meter tags để nhóm Timer | Có thể trở thành span attributes |
| **High cardinality** | `operation.reference=ref-7f3...` | Không đưa thành meter tags theo cơ chế mặc định | Có thể trở thành span attributes |
| Context property chưa chuyển thành key-value | Tham chiếu bean, object method invocation | Không tự xuất | Không tự xuất |

**Cardinality** là số tổ hợp giá trị của nhãn. Meter `module.invocations` với 6 modules × 2 deployment tiers × 5 loại invocation có thể tạo nhiều time series; nếu thêm ID từng đơn hàng thì số series có thể tăng theo số giao dịch.

Với module entry span, tài liệu Spring Modulith ghi nhận các key:

| Key | Ý nghĩa |
| --- | --- |
| `module.identifier` | Định danh application module |
| `module.name` | Tên module để hiển thị |
| `module.method` | Method được thực thi tại điểm vào module |
| `module.invocation-type` | Ví dụ `bean` hoặc `event listener` |

Các key được tài liệu liệt kê cho **module entry span**. Đừng mặc định cả bốn đều là **low-cardinality metric tags**. Cần xem `ModulithContext.getLowCardinalityValues()`, `getHighCardinalityValues()` và response thực tế của phiên bản ứng dụng, vì convention và handler quyết định kênh nhận từng key.

**Không chứa dữ liệu nhạy cảm** trong cả hai nhóm tags. High cardinality chỉ có nghĩa là ít phù hợp để tổng hợp metrics; nó không cho phép tự do đưa thông tin khách hàng, số thẻ hoặc token vào trace backend.

## 6. Quan sát mặc định từ `ModulithContext`

Spring Modulith cung cấp `DefaultModulithObservationConvention.INSTANCE` tại package:

~~~java
import org.springframework.modulith.observability.support.DefaultModulithObservationConvention;
~~~

Theo reference guide, convention mặc định chuyển tiếp các lời gọi tới `ModulithContext`. Context này gắn với **ObservedModule**, một **MethodInvocation** và môi trường runtime, đồng thời có API để lấy:

~~~java
context.getLowCardinalityValues();
context.getHighCardinalityValues();
context.getContextualName();
context.getModule();
context.getInvocation();
~~~

Vì vậy một custom convention nên **giữ lại metadata mặc định**, trừ khi bạn chủ ý thay đổi hợp đồng đo đạc. Nếu trả về một tập `KeyValues` mới mà quên kết hợp giá trị cũ, bạn có thể làm mất `module.identifier` hoặc key khác đang được dùng trong dashboard và trace.

### 6.1. Khi nào thực sự cần custom convention?

Một số tình huống hợp lý:

1. Muốn thêm nhãn **có giới hạn** như `deployment.tier=lab/staging/production` riêng cho module entry observations để đối chiếu cả metrics và traces.
2. Muốn chuẩn hóa tên hiển thị span theo quy tắc đã xác định, chẳng hạn phân nhóm một số loại module invocation.
3. Muốn ghi thêm low/high-cardinality values dựa trên metadata module **đã được chuẩn hóa** và đáp ứng yêu cầu bảo mật.

Nếu chỉ muốn gắn `environment` lên **tất cả metrics**, cân nhắc `management.metrics.tags.*` của Spring Boot; tùy chọn đó không tự thêm span attributes. Nếu chỉ muốn làm giàu **counter của một domain event type**, dùng `ModulithEventMetricsCustomizer`. Việc chọn đúng extension point giúp thay đổi ít phạm vi hơn và dễ kiểm chứng.

## 7. Ví dụ: thêm một low-cardinality tag vào cả hai đường

Giả sử chúng ta cần kiểm tra việc module entry observations ở môi trường học tập đều mang nhãn `deployment.tier=lab`. Nhãn này có tập giá trị rất nhỏ và không chứa dữ liệu cá nhân.

Để tránh làm mất metadata sẵn có, ta dùng **delegate** đến convention mặc định:

~~~java
// src/main/java/com/example/shop/observability/ShopModulithObservationConvention.java
package com.example.shop.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;
import org.springframework.modulith.observability.support.DefaultModulithObservationConvention;

public final class ShopModulithObservationConvention
        implements ModulithObservationConvention {

    private final ModulithObservationConvention delegate =
            DefaultModulithObservationConvention.INSTANCE;

    @Override
    public String getName() {
        return delegate.getName();
    }

    @Override
    public String getContextualName(ModulithContext context) {
        return delegate.getContextualName(context);
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
        return delegate.getLowCardinalityKeyValues(context)
                .and(KeyValue.of("deployment.tier", "lab"));
    }

    @Override
    public KeyValues getHighCardinalityKeyValues(ModulithContext context) {
        return delegate.getHighCardinalityKeyValues(context);
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return delegate.supportsContext(context);
    }
}
~~~

Chúng ta giữ nguyên `getName()`, `getContextualName(...)`, high-cardinality keys và logic `supportsContext(...)` của mặc định; chỉ **nối thêm** một low-cardinality key vào giá trị mặc định.

**Không viết `getLowCardinalityKeyValues(...)` bằng `KeyValues.of("deployment.tier", "lab")` duy nhất** nếu mục tiêu là bổ sung nhãn: cách đó có thể thay toàn bộ low-cardinality keys của module. Nếu sau này muốn thay thật, cần cập nhật dashboard/tracing query và các integration tests liên quan.

Đây là mã phù hợp với API Spring Modulith hiện hành có `ModulithObservationConvention` và `DefaultModulithObservationConvention.INSTANCE`; class/package chính xác cần được đối chiếu BOM/version của dự án khi biên dịch.

### 7.1. Đăng ký bằng một Spring bean

~~~java
// src/main/java/com/example/shop/observability/ObservabilityConfiguration.java
package com.example.shop.observability;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration(proxyBeanMethods = false)
public class ObservabilityConfiguration {

    @Bean
    ModulithObservationConvention modulithObservationConvention() {
        return new ShopModulithObservationConvention();
    }
}
~~~

Đặt cấu hình trong vùng component scan của `@SpringBootApplication` hoặc import tường minh. Spring Modulith có thể tìm bean qua kiểu `ModulithObservationConvention`; không cần tự gọi method convention ở từng nghiệp vụ.

**Một số lưu ý vận hành:**

- Nếu có nhiều bean `ModulithObservationConvention`, cách chọn bean có thể mơ hồ hoặc phụ thuộc cấu hình; để việc test dễ hiểu, chỉ đăng ký customizer đúng mục đích.
- Bean phải thuộc **runtime ApplicationContext**. Cấu hình chỉ nằm trong `src/test/java` không áp dụng cho bản deploy.
- Đảm bảo **runtime observability của Modulith** được bật; khai báo bean convention đơn độc không tự instrument các application modules.
- `deployment.tier` ở ví dụ được hard-code chỉ để học. Production nên lấy từ cấu hình được kiểm soát, chuẩn hóa về tập giá trị hữu hạn, tránh gắn request ID vào đây.

## 8. Dependency và hạ tầng thử nghiệm

Với Spring Modulith hiện hành, có thể dùng starter Insight để cung cấp module Actuator và observability:

~~~xml
<!-- pom.xml; version được quản lý bởi BOM tương thích -->
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-starter-insight</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Vì source Java của ví dụ **import** `ModulithObservationConvention` và `ModulithContext`, cần artifact API trong **compile classpath**:

~~~xml
<dependency>
    <groupId>org.springframework.modulith</groupId>
    <artifactId>spring-modulith-observability-api</artifactId>
</dependency>
~~~

Nếu project chỉ cần observability và muốn tự lắp Actuator, runtime có thể dùng `spring-modulith-observability-core` cùng `spring-boot-starter-actuator` phù hợp. Không khai báo core trùng với dependency đã được starter Insight mang vào trừ khi có lý do riêng.

Một bản Gradle minh họa:

~~~groovy
dependencies {
    implementation "org.springframework.modulith:spring-modulith-observability-api"
    runtimeOnly "org.springframework.modulith:spring-modulith-starter-insight"
}
~~~

### 8.1. Phần metrics

Cho phép truy vấn Actuator Metrics trong môi trường học:

~~~yaml
# application-lab.yml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,modulith"
~~~

`/actuator/metrics` hiển thị meter do Micrometer quản lý. `/actuator/modulith` mô tả cấu trúc module, **không** phải endpoint chứa traces hoặc Timers. Đường dẫn phụ thuộc management port và base path thực tế; nếu có Spring Security, cần cấp quyền đọc tương ứng.

### 8.2. Phần tracing

Muốn thấy span trên backend, cần **tracing bridge/handler**, **exporter/transport**, **collector** và cấu hình tương ứng với Spring Boot đang chạy. Không thể chỉ thêm starter Insight hoặc `management.tracing.sampling.probability` là tự có trace UI.

Trong profile thử nghiệm, có thể dùng:

~~~yaml
management:
  tracing:
    sampling:
      probability: 1.0
~~~

Mức 100% giúp dễ kiểm tra các operation nhỏ; production phải tính toán lưu lượng, chi phí, retention và bảo mật. Với Spring Boot 3.x và 4.x, bộ dependency exporter/tracing được tổ chức khác nhau; hãy dùng reference guide đúng major version thay vì sao chép một cấu hình không tương thích.

## 9. Tạo một luồng nghiệp vụ có module entry

Giả sử ứng dụng có hai module `orders` và `payments`. Class API công khai của module `payments`:

~~~java
// com/example/shop/payments/PaymentApi.java
package com.example.shop.payments;

import org.springframework.stereotype.Service;

@Service
public class PaymentApi {

    public void authorize(String orderId) {
        // Mô phỏng thao tác, không gọi cổng thanh toán thật.
    }
}
~~~

Module `orders` dùng Spring bean này:

~~~java
// com/example/shop/orders/OrderService.java
package com.example.shop.orders;

import com.example.shop.payments.PaymentApi;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final PaymentApi paymentApi;

    public OrderService(PaymentApi paymentApi) {
        this.paymentApi = paymentApi;
    }

    public void placeOrder(String orderId) {
        paymentApi.authorize(orderId);
    }
}
~~~

Khi `PaymentApi` được Spring Modulith nhận diện là **API của module payments** và method được gọi qua Spring bean/proxy được instrument, module entry observation có thể được tạo. Lúc đó custom convention mới có cơ hội bổ sung `deployment.tier=lab`.

Một số lời gọi **không tạo module entry observation** như bạn kỳ vọng:

- Helper thuần Java do code tự tạo bằng `new`, không được Spring quản lý.
- Lời gọi `this.someMethod()` tự đi trong cùng đối tượng và bỏ qua proxy.
- Class nằm trong implementation package không phải điểm vào module API được instrument.
- Bean/module detection chỉ được tùy biến ở test nhưng không có trong runtime artifact.
- Một event listener chạy bất đồng bộ hoặc không thuộc đường instrumentation tương ứng.

Việc không thấy span ở những trường hợp này chưa đủ để kết luận convention sai. Cần xác minh điểm instrument và observation lifecycle trước.

## 10. Bước kiểm tra thứ nhất: metrics

### 10.1. Truy vấn meter sau khi chạy nghiệp vụ

Sau khi gọi `OrderService.placeOrder("demo-order")` từ một điểm vào thực sự, thử:

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/metrics/module.invocations
~~~

`module.invocations` là observation name mặc định được xác định bởi Spring Modulith hiện hành. Nếu bạn thay `getName()`, hãy dùng **tên thực tế**. Nếu meter không tồn tại, kiểm tra trước hết có instrumented module entry và metrics handler hay chưa.

Một response **giả lập để minh họa cấu trúc**:

~~~json
{
  "name": "module.invocations",
  "measurements": [
    {"statistic": "COUNT", "value": 3.0},
    {"statistic": "TOTAL_TIME", "value": 0.015},
    {"statistic": "MAX", "value": 0.009}
  ],
  "availableTags": [
    {"tag": "module.identifier", "values": ["payments", "orders"]},
    {"tag": "deployment.tier", "values": ["lab"]}
  ]
}
~~~

Response này **không phải số liệu đo của dự án đang chạy**. Các trường tag khác, thời gian và số lần gọi tùy instrumentation và phiên bản. Điều cần kiểm tra là sự xuất hiện của `deployment.tier=lab` trên meter có đúng observation name; không xem số `COUNT=3` trong ví dụ như yêu cầu cho mọi chạy thử.

### 10.2. Lọc theo tag convention bổ sung

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.invocations?tag=deployment.tier:lab"
~~~

Nếu API module có key `module.identifier` trong low-cardinality tags:

~~~bash
curl -i "http://localhost:8080/actuator/metrics/module.invocations?tag=deployment.tier:lab&tag=module.identifier:payments"
~~~

Hai tham số `tag=...` được dùng đồng thời để thu hẹp kết quả. Chỉ lọc các key và value thực sự có trong `availableTags` của meter. Nếu tag không hiện:

1. Kiểm tra đây có phải đúng Timer được tạo từ **module entry observation** không.
2. Kiểm tra custom convention bean đã vào ApplicationContext chưa.
3. Kiểm tra code của `getLowCardinalityKeyValues(...)` có gọi delegate và thêm tag không.
4. Kiểm tra có `MeterRegistry`/metrics handler hoạt động và observation đã dừng chưa.
5. Kiểm tra bạn đang truy vấn đúng instance, profile và deployment version.

### 10.3. Không nhầm với event counters

Spring Modulith còn ghi các event publication counters:

~~~text
module.events.published
module.events.published.$moduleIdentifier.$simpleEventTypeName
~~~

Chúng được thiết kế để thống kê **domain event publish**. Các tag của `ModulithObservationConvention` không đương nhiên xuất hiện trên counter riêng của event. Nếu yêu cầu là thêm một tag nghiệp vụ lên counter theo event type, dùng `ModulithEventMetricsCustomizer`; nếu yêu cầu là đổi module entry observation, dùng convention như bài này.

## 11. Bước kiểm tra thứ hai: traces

Với tracer, exporter và collector hoạt động, gửi một request gọi vào `orders` rồi sang `payments`. Tìm trace tương ứng trong backend theo khoảng thời gian, tên service và HTTP request.

Một trace lý tưởng có thể có:

~~~text
Trace: 8c2d...
└── HTTP POST /orders
    └── orders.placeOrder        (module entry, nếu được instrument)
        └── payments.authorize   (module entry, nếu được instrument)
            deployment.tier = lab
            module.identifier = payments
~~~

Tên span chỉ để minh họa. Thực tế contextual name được lấy từ convention và có thể được tracing handler/backend chuẩn hóa; không bắt buộc khớp tên Timer.

Mở **attributes/tags** của span module entry:

- Tìm `deployment.tier=lab`, vì nó được thêm như low-cardinality key-value và tracing handler hỗ trợ đưa những values đó vào span.
- Kiểm tra metadata gốc `module.identifier`, `module.name`, `module.method` và `module.invocation-type` theo những key được backend xuất và logic của version đang dùng.
- Xem `traceId`, `spanId` và quan hệ parent/child; xác định lời gọi `payments` thuộc đúng request nếu context đã được truyền.
- So sánh tên span với `getContextualName(...)`. Nếu muốn đổi tên, thực hiện thay đổi một cách có chủ đích và kiểm tra các truy vấn tracing có phụ thuộc tên cũ hay không.

Nếu metrics có tag nhưng traces không có, **đừng vội sửa convention**. Hãy kiểm tra bridge, exporter, collector, sampling, filters, quyền truy cập UI và điểm instrument.

### 11.1. Vì sao số lượng Timer samples khác số spans?

Timer đo operation được metrics handler ghi nhận trên mỗi instance và thường không chịu sampling của tracing. Trace backend có thể chỉ lưu một phần spans theo xác suất sampling, còn async context có thể khiến một span thuộc trace khác.

Ví dụ:

| Kết quả | Diễn giải hợp lý |
| --- | --- |
| Timer COUNT tăng 100, backend chỉ có 10 spans | Sampling 10% hoặc collector chỉ thu được một phần; chưa chắc mất dữ liệu metrics |
| Timer có `deployment.tier=lab`, span không có | Sai tracing handler/filter/collector, hoặc đang xem span khác |
| Span có tag, Actuator không có Timer | Metrics handler chưa bật, timer chưa hoàn tất, sai meter/instance |
| Cả hai đều không có tag | Convention bean không được dùng, sai module entry, instance hoặc artifact |
| Span tạo một trace mới khi qua executor | Trace context chưa được propagate hoặc operation độc lập |

Đây là các giả thuyết kiểm tra, không phải ánh xạ nguyên nhân duy nhất. Phải đối chiếu config và runtime evidence.

## 12. Một bài test và một phép kiểm tra tích hợp

### 12.1. Phân biệt ba cấp độ kiểm thử

| Cấp | Mục tiêu | Chưa chứng minh được |
| --- | --- | --- |
| Unit test cho convention | Kiểm tra code trả đúng name/key-values với `ModulithContext` hợp lệ | Framework đã instrument một bean thật |
| Integration test với `MeterRegistry` | Kiểm tra module entry đã tạo Timer có tag mong đợi | Collector nhận span và trace parent chính xác |
| Integration/end-to-end với tracing backend | Kiểm tra span/module metadata xuất được và tương quan với request | Toàn bộ metrics/trace production sẽ luôn đầy đủ, vì sampling và mạng có thể khác |

Để unit test convention trực tiếp cần dựng `ModulithContext` với `ObservedModule`, `MethodInvocation` và `Environment` phù hợp. Phép thử này hữu ích nhưng khá sát implementation. Trong bài học, phép kiểm tra tích hợp bằng một request thực vào public API module dễ phản ánh hành vi người dùng quan tâm hơn.

### 12.2. Ví dụ kiểm tra Timer bằng `MeterRegistry`

Mẫu sau giả định `OrderService` đã được bật instrumentation và test có metrics registry. Điều chỉnh annotation test theo phiên bản Spring Boot và bộ test dependencies thực tế:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ModuleObservationConventionIntegrationTests {

    @Autowired MeterRegistry meters;
    @Autowired OrderService orders;

    @Test
    void moduleInvocationHasDeploymentTierOnMetrics() {
        orders.placeOrder("demo-001");

        assertThat(
            meters.find("module.invocations")
                .tag("deployment.tier", "lab")
                .meters()
        ).isNotEmpty();
    }
}
~~~

Để kiểm tra đúng module `payments`, lọc thêm `module.identifier=payments` **nếu key này thực sự thuộc meter tags** trong version đang chạy. Chỉ so kết quả sau khi operation đã hoàn tất. Nếu test không tạo meter do môi trường test tắt observability, bật cơ chế test observability/metrics của Spring Boot version tương ứng.

**Lưu ý về testing theo version:** các dự án Spring Boot 3.x thường dùng `@AutoConfigureObservability` để kích hoạt các thành phần quan sát trong test; những dòng Boot mới có cơ chế `@AutoConfigureMetrics` và `@AutoConfigureTracing` ở các test modules tương ứng. Kiểm tra guide của dòng đang dùng, không mặc định annotation này xuất hiện ở mọi version.

### 12.3. Phép kiểm tra traces phải có assertion riêng

Trong một integration test có tracing backend/test span exporter, nên kiểm tra:

1. Tạo request với một trace context biết trước, ví dụ header W3C `traceparent` nếu transport và ứng dụng hỗ trợ.
2. Gọi một method thuộc API module đã được instrument.
3. Thu spans từ test tracing pipeline hoặc exporter kiểm thử sau khi đã hoàn tất.
4. Tìm span module entry dựa trên `module.identifier` hoặc method metadata.
5. Assert `deployment.tier=lab` và quan hệ trace/parent như thiết kế.

Nếu chỉ nhìn `/actuator/metrics` rồi kết luận tracing đã hoạt động thì test chưa kiểm tra đường thứ hai. Ngược lại, một test chỉ kiểm tra in-memory span cũng chưa chứng minh production collector hoặc dashboard đang nhận dữ liệu.

## 13. Chẩn đoán khi convention hoạt động không như kỳ vọng

| Triệu chứng | Khả năng cần điều tra | Cách kiểm chứng |
| --- | --- | --- |
| Bean `ModulithObservationConvention` không được nhận | Class nằm ngoài component scan, thiếu `@Bean`, profile không bật | Kiểm tra Spring context và bean list trong đúng runtime |
| Java import convention báo lỗi | Thiếu `spring-modulith-observability-api` ở compile classpath | Kiểm tra dependency management và artifact theo version |
| Không có Timer `module.invocations` | Chưa instrument API module, metrics handler chưa bật, operation chưa kết thúc | Kiểm tra điểm gọi/bean proxy, registry, meter list |
| Có Timer nhưng thiếu `deployment.tier` | Custom bean chưa được chọn, code không thêm low-cardinality key | Kiểm tra runtime bean, convention implementation và tag thực |
| Có Timer nhưng `module.identifier` biến mất | Custom convention trả KeyValues mới mà bỏ metadata mặc định | Dùng delegate/`and(...)` để giữ key cũ |
| Có spans nhưng không thấy attribute bổ sung | Sai span, handler/exporter/filter loại bỏ attribute | Xem module entry span thật, trace config, collector |
| Trace không xuất hiện | Thiếu tracing bridge/exporter, sampling hoặc collector lỗi | Kiểm tra Boot tracing setup, logs và backend |
| Span thuộc trace khác sau `@Async` | Không truyền context giữa các thread | Cấu hình propagation trên executor, kiểm tra scope |
| Dashboard sau đổi tên bị trống | Đổi `getName()` đã đổi tên meter, hoặc đổi span name phá truy vấn cũ | Xác nhận tên mới, cập nhật dashboard và theo dõi migration |
| Rất nhiều time series | Thêm tag có số giá trị lớn, ví dụ order ID | Chuyển về enum/nhóm giá trị hữu hạn, bỏ dữ liệu nhạy cảm |
| Event counter không có tag mới | Custom convention áp dụng cho module entry observation, không phải counter event type | Dùng `ModulithEventMetricsCustomizer` cho event counters |
| Endpoint `/actuator/metrics` trả 401/403/404 | Security, HTTP exposure, management port/path | Kiểm tra access policy, dependency và URL thực |

**Một lỗi tư duy phổ biến:** cho rằng `ModulithObservationConvention` là bộ lọc để “chọn module nào xuất trace”. Nó là convention để **đặt tên và cung cấp metadata**; instrumentation, predicates, handlers và exporter là các khâu khác.

## 14. Bài thực hành có đối chứng

**Bài toán:** ứng dụng Spring Boot có module `orders` gọi API `payments`. Cần chứng minh custom convention thêm `deployment.tier=lab` vào **cả Timer metrics và module entry span** mà vẫn giữ metadata mặc định.

Thực hiện:

1. Xây package `com.example.shop.orders` và `com.example.shop.payments` như phần 9. Chạy kiểm chứng module graph để biết `orders → payments` là dependency tĩnh.
2. Thêm Spring Modulith observability/Insight starter cùng observability API compile scope. Cấu hình Actuator metrics và tracing exporter/collector thích hợp.
3. Chạy baseline với convention mặc định: gọi method `payments.authorize(...)` từ module khác, ghi tên Timer/những tags hiện có và tên/attributes của module span.
4. Đăng ký `ShopModulithObservationConvention` bằng `@Bean`. Restart ứng dụng thử nghiệm để áp dụng cấu hình; giữ cùng luồng nghiệp vụ.
5. Đọc `/actuator/metrics/module.invocations` và lọc `deployment.tier:lab`. Xác nhận Timer có COUNT tăng và những tag module cần thiết vẫn còn.
6. Mở tracing backend và tìm span module `payments`. Đọc `deployment.tier=lab` cùng `module.identifier`, các key còn lại và quan hệ parent/child. Ghi lại trace ID dùng để đối chiếu.
7. Đối chứng bằng cách chỉ kiểm tra meter khi tạm tắt tracing exporter ở profile test; nêu vì sao không thấy span nhưng Timer vẫn có thể tăng. Sau đó khôi phục exporter.
8. Thử cho một lời gọi đi qua executor khác thread. Kiểm tra trace parent; nếu context đứt, thêm propagation tương thích rồi so lại. Việc này kiểm chứng **context propagation**, khác với chức năng của convention.
9. Truy vấn `module.events.published` nếu ứng dụng có domain events, chứng minh tag của custom convention không bắt buộc xuất hiện ở counter này.

Mẫu bảng lưu kết quả:

| Phép thử | Baseline | Có convention | Kết luận |
| --- | --- | --- | --- |
| Timer name | `module.invocations` | Vẫn như cũ | Delegate giữ hợp đồng tên |
| Timer tag `deployment.tier` | Chưa có | `lab` | Low-cardinality custom tag áp dụng |
| Module metadata trên Timer | Có những keys theo version | Những keys đó vẫn còn | Không xóa key cũ |
| Span name | Theo contextual name mặc định | Vẫn theo mặc định | Không đổi tên span ngoài yêu cầu |
| Span attribute `deployment.tier` | Chưa có | `lab` nếu tracing pipeline hoạt động | Kiểm tra đường tracing độc lập |
| Event counter riêng | Theo cấu hình gốc | Không nhất thiết đổi | Custom convention khác event metric customizer |

**Tiêu chí đạt:** đọc và lý giải được cả kết quả trên Timer lẫn span; giữ nguyên key-values mặc định; phân biệt lỗi convention với lỗi tracing pipeline; không dùng ID nghiệp vụ làm metric tag; không lấy số lượng spans để suy ra số lần operation thực thi chính xác.

## 15. Câu hỏi tự kiểm tra

1. `getName()` và `getContextualName(context)` phục vụ những mục đích nào?
2. Vì sao nên delegate tới `DefaultModulithObservationConvention.INSTANCE` trước khi thêm key-value?
3. Một tag được thêm bằng `getLowCardinalityKeyValues(...)` có thể xuất hiện ở đâu? Tag high cardinality thì sao?
4. Tại sao Timer có tag mới không chứng minh trace exporter cũng có span mới?
5. Vì sao `module.method` có thể xuất hiện trên span nhưng không nằm trong danh sách `availableTags` của Timer?
6. Bạn sẽ kiểm tra thế nào nếu cả Actuator và tracing UI đều thiếu tag `deployment.tier`?
7. Tại sao cần cấu hình `spring-modulith-observability-api` ở compile scope khi code import interface convention?
8. Có nên dùng `ModulithObservationConvention` để thêm tag `orderId` cho event publication counter không?
9. Nếu span `payments` xuất hiện thành một trace khác khi chạy `@Async` thì sửa convention có giải quyết được không?

**Gợi ý:** (1) tên meter ổn định và tên span theo ngữ cảnh; (2) tránh mất metadata chuẩn; (3) low thường tới metrics và traces, high chỉ tới traces mặc định; (4) hai pipelines độc lập và tracing chịu sampling/exporter; (5) phân loại low/high do convention quyết định; (6) xác minh đúng module entry, bean thực tế, handler, version và instance; (7) để compiler tìm thấy type; (8) không, vừa sai extension point vừa rủi ro cardinality; (9) cần context propagation, không phải thay tên/tag.

## 16. Ghi nhớ

Khi kiểm tra `ModulithObservationConvention`, hãy xem nó như **hợp đồng tên và metadata** của một module observation. Test tốt phải chứng minh:

~~~text
Một module entry observation
          │
          ├── getName() + low-cardinality KeyValues
          │       └── Micrometer Timer / Actuator / Prometheus
          │
          └── contextual name + low/high-cardinality KeyValues
                  └── Trace span / backend tracing
~~~

Ở hai nhánh, dữ liệu được xuất còn phụ thuộc instrumentation, handler, registry, sampler, exporter và context propagation. Với Spring Modulith, tiếp tục kết hợp **module graph** (quan hệ kiến trúc), **Actuator** (metadata và meters), **event metrics** (lượt publish domain events) và **tracing** (các lời gọi được instrument) để kiểm chứng kiến trúc module lúc hệ thống vận hành.

### Tài liệu tham khảo

- [Spring Modulith — Production-ready Features: Conventions](https://docs.spring.io/spring-modulith/reference/production-ready.html) — khai báo Spring bean convention, module entry spans, event publication metrics.
- [Spring Modulith — ModulithObservationConvention API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservationConvention.html) — `getName`, `getContextualName`, low/high key-values và `supportsContext`.
- [Spring Modulith — ModulithContext API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html) — metadata context và tên convention mặc định.
- [Spring Modulith — DefaultModulithObservationConvention API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/support/DefaultModulithObservationConvention.html) — implementation mặc định để delegate.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html) — convention, handler, keys, timer và trace semantics.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — đường dữ liệu low/high cardinality và context propagation.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) và [Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html) — cấu hình quan sát và xuất tín hiệu.

> **Lưu ý phiên bản:** ví dụ mô tả API của Spring Modulith hiện hành có `ModulithObservationConvention`/`ModulithContext`; tên artifact, testing annotations, metric output và tracing exporter có thể khác giữa Spring Boot/Spring Modulith/Micrometer. Hãy dùng BOM tương thích và đối chiếu reference guide của phiên bản đang chạy. Bài viết hoàn thành STEP 4 về nội dung; vòng Content QA chuyên sâu thuộc bước riêng.
