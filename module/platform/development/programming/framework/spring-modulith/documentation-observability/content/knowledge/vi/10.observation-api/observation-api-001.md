# Micrometer Observation trong Spring Modulith

## 1. Observation kết nối kiến trúc mô-đun với dữ liệu vận hành như thế nào?

Spring Modulith giúp ứng dụng Spring Boot được tổ chức thành các **application module** có API và ranh giới phụ thuộc rõ ràng. Ví dụ, module `ordering` tạo đơn hàng, module `payment` xử lý thanh toán, còn `notification` phản ứng với sự kiện hoàn tất đơn. Khi kiểm tra mã nguồn, ta có thể xác định `ordering` phụ thuộc vào API của `payment`. Tuy nhiên, khi hệ thống chạy, người vận hành còn cần biết một request có thật sự đi qua `payment` hay không, thời gian xử lý ở điểm vào module là bao lâu và lần gọi nào có lỗi.

**Micrometer Observation** là cơ chế thống nhất để ghi nhận một vùng thực thi. Các `ObservationHandler` được gắn với `ObservationRegistry` có thể biến observation thành metric, trace/span hoặc tín hiệu quan sát khác. Spring Modulith sử dụng cơ chế đó để instrument những lời gọi đi vào API của application module. Nhờ vậy, module graph tĩnh có thể được đối chiếu với tương tác được ghi nhận trong quá trình vận hành.

Đây là bài học thuộc chương **Observation API** của module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Phạm vi bao gồm Spring Modulith, Spring Boot Actuator, event metrics, tracing và context propagation nhằm **tài liệu hóa ranh giới module và quan sát hành vi qua ranh giới**. Observation là một phần của bức tranh đó, chứ không tự thay thế kiểm thử kiến trúc hay hệ thống tracing backend.

Sau bài học, bạn sẽ hiểu:

1. Sự khác nhau giữa `Observation`, `ObservationRegistry`, `Observation.Context`, `ObservationHandler` và `ObservationConvention`.
2. Khi nào Spring Modulith tự tạo **module-entry observation** và dữ liệu nào gắn vào nó.
3. Cách bật observability bằng dependency, metrics registry và tracing exporter tương ứng.
4. Cách ghi thêm một observation nghiệp vụ bằng Java khi cần đo bước xử lý bên trong module.
5. Cách tùy biến convention của module-entry observation và chọn tag có cardinality phù hợp.
6. Cách xử lý trace đứt đoạn khi application event hoặc `@Async` chuyển sang thread khác.
7. Cách kiểm chứng kết quả và phân biệt observation, event counter, Actuator graph, Event Publication Registry.

## 2. Năm thành phần cốt lõi của Micrometer Observation

Micrometer định nghĩa một API instrument có thể gắn với nhiều hệ thống quan sát. Một observation đơn lẻ không đồng nghĩa chắc chắn sẽ có metric và span trên dashboard: kết quả còn phụ thuộc các **handler và exporter** thực sự được cấu hình.

| Thành phần | Chức năng | Ví dụ trong ứng dụng |
| --- | --- | --- |
| `Observation` | Đại diện cho một hoạt động có vòng đời bắt đầu, kết thúc, lỗi và sự kiện kèm theo. | Một lần đi vào API `PaymentService.authorize()`. |
| `ObservationRegistry` | Nơi quản lý cấu hình, handler, predicate, filter và context để xử lý observations. | Registry do Spring Boot autoconfigure và inject vào các bean. |
| `Observation.Context` | Giữ metadata của một observation, gồm các key/value và thông tin cần cho instrumentation. | `ModulithContext` chứa module và lời gọi đang quan sát. |
| `ObservationHandler` | Nhận thông báo của vòng đời observation để xuất kết quả. | Metrics handler ghi timer; tracing handler tạo và hoàn tất span. |
| `ObservationConvention` | Định nghĩa tên, tên ngữ cảnh và các key/value gắn với loại observation. | `ModulithObservationConvention` cho module-entry observation. |

### 2.1. Vòng đời của một observation

Thông thường, instrumentation thực hiện các bước:

~~~mermaid
flowchart LR
    A["Tạo Observation"]
    B["Start"]
    C["Open Scope"]
    D["Thực thi nghiệp vụ"]
    E["Ghi error/event nếu có"]
    F["Close Scope"]
    G["Stop"]
    H["Handler xuất metrics/traces"]
    A --> B --> C --> D --> E --> F --> G --> H
~~~

- **Start/Stop** đánh dấu vòng đời để các handler tính thời gian và kết thúc hoạt động.
- **Scope** làm observation hiện tại sẵn có trong ngữ cảnh thread, để một observation con có thể liên hệ với cha khi được tạo trong scope.
- **Error** ghi nhận lỗi trong phạm vi hoạt động được quan sát. Một lỗi bị bắt và xử lý bên trong có thể cần được báo chủ động nếu instrumentation không nhìn thấy exception.
- **Event** trên observation là tín hiệu nội bộ trong vùng đo; **không đồng nghĩa** Spring `ApplicationEventPublisher` đã phát một domain event.

Micrometer cung cấp cách viết ngắn `observe(...)` để tự quản lý start, scope, error và stop cho đoạn code được bọc. Khi bạn tự quản lý thủ công `start()` và `openScope()`, cần đóng scope và gọi `stop()` ngay cả khi có exception.

### 2.2. Tên observation và contextual name

Hai thuộc tính cần phân biệt:

- **Tên observation** thường là một tên có tính ổn định như `payment.authorize`. Tên này thường trở thành tên của meter hoặc nhóm observation được handler sử dụng.
- **Contextual name** có thể là tên dễ đọc hơn cho span như “authorize payment”; nó mô tả thao tác đang diễn ra.

Không tạo tên observation động theo từng mã đơn hàng hoặc request ID. Nếu mỗi request tạo một tên mới, metrics backend có thể bị bùng nổ số lượng series và khó so sánh.

### 2.3. Low cardinality và high cardinality

Micrometer phân biệt metadata theo số lượng giá trị có thể xuất hiện:

| Loại key/value | Ví dụ | Hệ quả |
| --- | --- | --- |
| **Low cardinality** | `payment.method=card/bank_transfer`, `module.identifier=payment`. | Có số giá trị tương đối nhỏ; thường được đưa vào metric tags và có thể xuất hiện trên spans. |
| **High cardinality** | `order.id`, `transaction.id`, `request.id`. | Số giá trị có thể rất lớn; không đưa vào metric tags, có thể có trên traces nếu handler/exporter hỗ trợ và chính sách dữ liệu cho phép. |

Không phải cứ gọi `highCardinalityKeyValue(...)` là dữ liệu được bảo vệ tự động. Span có thể được gửi đến hệ thống quan sát bên ngoài, nên vẫn phải xem xét quyền riêng tư, thời hạn lưu trữ và quy định nội bộ trước khi ghi ID hoặc dữ liệu nghiệp vụ nhạy cảm.

## 3. Spring Modulith instrument module entry như thế nào?

Spring Modulith nhận diện application modules từ cấu trúc mã nguồn và cấu hình module. Khi bật observability, các **Spring component thuộc API của application module** được trang trí bằng interceptor/aspect để tạo observation cho lời gọi đi vào module. Trong nhánh API hiện đại, các khái niệm liên quan gồm:

- `ModulithObservations.MODULE_ENTRY`: kiểu observation dành cho việc đi vào application module.
- `ModulithContext`: context đặc thù chứa module được quan sát, method invocation và môi trường ứng dụng.
- `ModulithObservationConvention`: interface để chọn tên và metadata của module-entry observation.
- `ModuleEntryInterceptor` và các thành phần hỗ trợ nội bộ: tạo observation khi lời gọi đi qua điểm instrument.

**Phạm vi instrument là điều phải hiểu đúng.** Không phải mọi phương thức Java, helper private, thao tác tự gọi trong một bean hay đối tượng không do Spring quản lý đều tự động tạo module-entry span. Chỉ những điểm vào thực sự nằm trong phạm vi instrumentation và được gọi qua cơ chế Spring phù hợp mới tạo observation.

### 3.1. Ví dụ hai module có lời gọi qua ranh giới

Giả sử package gốc là `com.example.shop`:

~~~text
com.example.shop
├── ShopApplication.java
├── ordering
│   ├── OrderService.java
│   └── OrderPlaced.java
└── payment
    ├── PaymentService.java
    └── internal
        └── PaymentGatewayAdapter.java
~~~

`OrderService` gọi API công khai `PaymentService`. Spring Modulith có thể nhận diện quan hệ phụ thuộc `ordering → payment`, đồng thời observability có thể tạo observation khi lời gọi đi vào API `payment`.

~~~mermaid
sequenceDiagram
    actor C as Client
    participant H as HTTP Controller
    participant O as ordering / OrderService
    participant P as payment / PaymentService
    C->>H: POST /orders
    H->>O: createOrder(...)
    O->>P: authorize(...)
    P-->>O: kết quả thanh toán
    O-->>H: đơn hàng
    H-->>C: HTTP response
    Note over O,P: Module-entry observations có thể xuất hiện tại API của module được instrument
~~~

Ví dụ Java tối giản để minh họa điểm vào API:

~~~java
package com.example.shop.payment;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    public boolean authorize(String orderId, BigDecimal amount) {
        // Logic minh họa. Ứng dụng thật cần gateway và xử lý lỗi phù hợp.
        return amount.signum() > 0;
    }
}
~~~

~~~java
package com.example.shop.ordering;

import java.math.BigDecimal;
import com.example.shop.payment.PaymentService;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final PaymentService paymentService;

    public OrderService(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public boolean placeOrder(String orderId, BigDecimal amount) {
        return paymentService.authorize(orderId, amount);
    }
}
~~~

Đây là ví dụ học thuật về cách một Spring bean công khai được module khác gọi qua ranh giới. Việc đặt code trong API module đúng cấu trúc và bật instrumentation là điều kiện cần; **không thể khẳng định span sẽ xuất hiện chỉ bằng cách nhìn hai class trên**.

### 3.2. Các tag của module-entry span

Tài liệu Spring Modulith công bố các tag sau cho **module-entry span**:

| Tag | Ý nghĩa | Ví dụ minh họa |
| --- | --- | --- |
| `module.identifier` | Định danh kỹ thuật của module. | `payment` |
| `module.name` | Tên hiển thị của module. | `Payment` |
| `module.method` | Phương thức ở điểm vào module. | `authorize` |
| `module.invocation-type` | Loại lời gọi đi vào module. | `bean` hoặc `event listener` |

Từ một trace, người vận hành có thể tìm các module-entry spans để xác định một request đã đi qua những điểm API nào và mỗi điểm mất bao lâu. Những giá trị trong bảng là ví dụ; tên span, tên phương thức cụ thể và cách backend biểu diễn thuộc tính phải kiểm tra từ telemetry thực tế.

### 3.3. Quan hệ với module graph

Hai nguồn dữ liệu có ý nghĩa khác nhau:

| Nguồn | Diễn giải |
| --- | --- |
| `/actuator/modulith` | Module `ordering` **có quan hệ phụ thuộc** với `payment` theo mã nguồn được nhận diện. |
| Module-entry observation/span | Một lần thực thi **đã đi qua điểm vào được instrument** của `payment`. |
| `ApplicationModules.verify()` | Phụ thuộc mã nguồn có vi phạm các quy tắc kiến trúc được Spring Modulith kiểm tra hay không. |

Graph có cạnh nhưng trace không có span vẫn có thể hoàn toàn hợp lý: request có thể đi nhánh khác, phần gọi không được instrument, hoặc span bị sampling loại bỏ. Không xem trace là phép kiểm tra mọi phụ thuộc tĩnh.

## 4. Bật Micrometer Observation trong dự án Spring Boot

### 4.1. Khai báo Spring Modulith observability

Với dự án **Spring Boot 4.x và Spring Modulith 2.x** tương thích, nếu muốn cả Actuator module và instrumentation, dùng Insight Starter:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
}
~~~

Ví dụ Gradle Kotlin DSL giả định phiên bản Spring Modulith đã được quản lý qua BOM/plugin phù hợp. Insight Starter kéo theo Spring Modulith Actuator, observability và hỗ trợ Spring Boot Actuator.

Nếu chỉ cần instrumentation thay vì endpoint cấu trúc:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-observability-core")
}
~~~

Đối với Spring Modulith **1.x**, tên artifact và quan hệ dependency có thể khác, chẳng hạn tài liệu nhánh 1.4 sử dụng `spring-modulith-observability`. Phải chọn theo đúng dòng Spring Modulith và Spring Boot đang chạy, không ghép cấu hình từ hai thế hệ tùy tiện.

Khi tự viết mã tham chiếu các lớp API của Spring Modulith như `ModulithObservationConvention`, hãy thêm API artifact ở **compile scope**:

~~~kotlin
dependencies {
    implementation("org.springframework.modulith:spring-modulith-observability-api")
}
~~~

Không cần thêm artifact API vào compile scope nếu chỉ muốn tự động instrument thông qua starter và không import các lớp của nó trong source.

### 4.2. Metrics registry và tracer/exporter

Observation là một API; muốn xem kết quả cần đường xuất phù hợp:

| Mục tiêu | Thành phần bổ sung |
| --- | --- |
| Xem metrics qua Actuator | Có `MeterRegistry`, metrics observation handler và `/actuator/metrics` được expose/cho phép truy cập. |
| Xuất metrics cho Prometheus | `micrometer-registry-prometheus` và `/actuator/prometheus`. |
| Thu traces | Micrometer Tracing bridge, tracer và exporter tới backend như Zipkin/Tempo qua OpenTelemetry hoặc Brave. |
| Tìm một span trên giao diện | Một backend tracing đang chạy và nhận dữ liệu từ exporter. |

Ví dụ với **Spring Boot 4.x**, muốn dùng OpenTelemetry/OTLP:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")
    implementation("org.springframework.boot:spring-boot-starter-opentelemetry")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Địa chỉ collector và thuộc tính exporter phải cấu hình theo môi trường OTLP và phiên bản Spring Boot thực tế. Với Spring Boot 3.x, cần sử dụng Micrometer Tracing bridge và exporter được tài liệu Boot 3.x hướng dẫn thay vì sao chép nguyên bộ starter Boot 4.x.

### 4.3. Cấu hình thử nghiệm

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,prometheus,modulith"
  tracing:
    sampling:
      probability: 1.0
~~~

Đây là cấu hình dùng để **quan sát dễ hơn ở môi trường dev**. `sampling.probability: 1.0` yêu cầu lấy mẫu toàn bộ trace; production nên chọn mức theo lưu lượng và chi phí. `prometheus` chỉ hoạt động khi có registry tương ứng. Endpoint `modulith` trả cấu trúc module, **không trả danh sách trace**.

Cổng Actuator có thể khác cổng ứng dụng, và cấu hình `management.endpoints.web.base-path` có thể đổi `/actuator`. Cần bảo vệ endpoints quản trị bằng quyền truy cập, bảo mật và network policy.

## 5. Tự tạo một observation nghiệp vụ với `ObservationRegistry`

Spring Modulith tạo observation ở ranh giới module, nhưng đôi khi ta muốn quan sát **một bước bên trong module**, ví dụ thời gian gọi gateway thanh toán. Khi đó, sử dụng Micrometer Observation API trực tiếp.

Giả sử module `payment` có interface ứng dụng `PaymentGateway` với phương thức `capture(String orderId)`; ví dụ bean:

~~~java
package com.example.shop.payment.internal;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class PaymentCaptureService {

    private final ObservationRegistry observationRegistry;
    private final PaymentGateway paymentGateway;

    public PaymentCaptureService(
            ObservationRegistry observationRegistry,
            PaymentGateway paymentGateway) {
        this.observationRegistry = observationRegistry;
        this.paymentGateway = paymentGateway;
    }

    public void capture(String orderId, String channel) {
        Observation.createNotStarted("payment.capture", observationRegistry)
            .contextualName("capture payment")
            .lowCardinalityKeyValue("payment.channel", channel)
            .observe(() -> paymentGateway.capture(orderId));
    }
}
~~~

`PaymentGateway` là interface thuộc ví dụ, cần được cài đặt riêng. `channel` trong ứng dụng thật nên được chuẩn hóa thành một tập giá trị hữu hạn (`web`, `mobile`, `pos`), không nhận chuỗi tùy ý từ người dùng mà không kiểm soát.

Ý nghĩa từng phần:

- `ObservationRegistry` do Spring Boot cung cấp khi observability được cấu hình; nên **inject** registry có sẵn để dùng các handler nhất quán.
- `createNotStarted("payment.capture", ...)` khai báo tên observation ổn định.
- `contextualName("capture payment")` đặt tên dễ đọc cho span.
- `lowCardinalityKeyValue(...)` phân nhóm theo kênh có số lượng giá trị giới hạn, có thể dùng trên metrics.
- `observe(...)` bọc vùng xử lý để start, open scope, ghi nhận exception được ném ra, close scope và stop.

Khi method `capture(...)` chạy bên trong một module-entry observation còn active, observation mới **có thể trở thành span con** trong cùng trace nếu tracing handler đã được cấu hình và context được giữ. Đây là cách thêm chi tiết về bước gateway **bên trong** module; không phải cách thay thế instrumentation ranh giới do Spring Modulith cung cấp.

### 5.1. Thêm high-cardinality metadata khi thực sự cần

Nếu cần điều tra một đơn hàng cụ thể, có thể bổ sung một **correlation identifier đã được cho phép** vào observation:

~~~java
Observation.createNotStarted("payment.capture", observationRegistry)
    .lowCardinalityKeyValue("payment.channel", channel)
    .highCardinalityKeyValue("order.id", orderId)
    .observe(() -> paymentGateway.capture(orderId));
~~~

`highCardinalityKeyValue(...)` không biến `order.id` thành metric tag khi dùng metrics handler chuẩn. Tuy vậy, trace có thể mang giá trị này đến backend, nên chỉ ghi khi chính sách dữ liệu chấp nhận. Tránh email, số điện thoại, mã định danh cá nhân hoặc thông tin thanh toán nhạy cảm.

### 5.2. Khi nào không nên instrument thủ công?

Nếu method đã được Spring Modulith instrument tại API module, tạo thêm một observation bao quanh **cùng toàn bộ method** có thể dẫn đến hai vùng đo trùng nhau. Chỉ thêm manual observation khi nó mô tả **một bước nghiệp vụ/IO có ý nghĩa riêng** như `payment.capture`, `invoice.render` hoặc `shipping.reserve`.

Đặt tên nhất quán giữa các nhóm phát triển để dashboard và trace không trở thành tập hợp hàng nghìn tên gần giống nhau.

## 6. `ModulithContext` và `ModulithObservationConvention`

### 6.1. `ModulithContext` chứa thông tin gì?

Spring Modulith có context dành riêng cho module entry:

~~~java
org.springframework.modulith.observability.ModulithContext
~~~

Theo Java API, `ModulithContext` kế thừa `Observation.Context`, được tạo từ:

- `ObservedModule`: mô-đun đang được quan sát.
- `MethodInvocation`: lời gọi Java được interceptor ghi nhận.
- `Environment`: môi trường cấu hình của ứng dụng.

Context công bố các phương thức như `getModule()`, `getInvocation()`, `getApplicationName()`, `getLowCardinalityValues()`, `getHighCardinalityValues()` và `getContextualName()`. Những giá trị này cho phép convention quyết định nhãn và tên observation dựa trên cấu trúc application module.

Không nên tự khởi tạo `ModulithContext` trong code nghiệp vụ để “giả lập” một module entry. Nó được hỗ trợ như **context cho instrumentation**, được Spring Modulith tạo ở điểm interceptor phù hợp.

### 6.2. `ModulithObservationConvention` dùng để làm gì?

`ModulithObservationConvention` là interface kế thừa `ObservationConvention<ModulithContext>`. Nó cung cấp những phương thức như:

| Phương thức | Mục đích |
| --- | --- |
| `supportsContext(Observation.Context)` | Xác định convention có áp dụng cho context hiện tại hay không. |
| `getName()` | Tên observation ổn định. |
| `getContextualName(ModulithContext)` | Tên dễ đọc cho span/hoạt động. |
| `getLowCardinalityKeyValues(ModulithContext)` | Các key/value với tập giá trị hữu hạn, phù hợp cho metrics. |
| `getHighCardinalityKeyValues(ModulithContext)` | Metadata có thể có nhiều giá trị, phù hợp hơn cho truy vết có kiểm soát. |

Từ Spring Modulith 1.4 trở đi, interface này được công bố; ở nhánh 2.2, các phương thức có triển khai mặc định dựa trên `ModulithContext`. Ta có thể đăng ký một bean để thay đổi convention cho module-entry observations.

### 6.3. Ví dụ bổ sung một nhãn có tập giá trị nhỏ

Giả sử mọi instance của một ứng dụng thuộc nhóm triển khai `shop`. Có thể thêm nhãn `product.area=shop` mà vẫn giữ các nhãn mặc định:

~~~java
package com.example.shop;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration(proxyBeanMethods = false)
class ModuleObservationConfiguration {

    @Bean
    ModulithObservationConvention moduleObservationConvention() {
        return new ModulithObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
                return ModulithObservationConvention.super
                    .getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("product.area", "shop"));
            }
        };
    }
}
~~~

Trong ví dụ này:

1. Bean `ModulithObservationConvention` được Spring tìm thấy trong context ứng dụng.
2. Phương thức mặc định giữ các tag module được framework cung cấp.
3. `KeyValue.of("product.area", "shop")` bổ sung một chiều phân loại có số giá trị nhỏ và ổn định.
4. Ta **không** tự đổi tên meter, contextual name hoặc thêm mã đơn hàng vào low-cardinality tags.

Nếu muốn thay đổi `getName()` hoặc `getContextualName(...)`, hãy xem xét hệ quả đến dashboard/tracing backend và quy ước telemetry trước khi áp dụng. Tên metric thay đổi có thể làm hỏng truy vấn hoặc alert đang tồn tại.

**Lưu ý về API:** các phương thức mặc định và package ở ví dụ theo dòng Spring Modulith 2.2. Khi dùng phiên bản khác, cần đối chiếu JavaDoc của phiên bản dự án. Nếu đang dùng nhánh có thay đổi package hỗ trợ, cần cập nhật imports tương ứng.

### 6.4. Khác với `ModulithEventMetricsCustomizer`

Đừng nhầm hai cơ chế:

| API | Đối tượng tùy biến | Ví dụ sử dụng |
| --- | --- | --- |
| `ModulithObservationConvention` | Naming và key/value của **module-entry observation**. | Thêm nhãn cố định `product.area=shop` vào observation của lời gọi module. |
| `ModulithEventMetricsCustomizer` | Counter riêng cho **một kiểu domain event** đã được phát. | Thêm tag `channel=web/mobile` cho counter `OrderPlaced`. |

Convention dành cho observation không mặc nhiên biến mọi event counter thành module-entry metric, còn event metrics customizer cũng không thay thế convention của span.

## 7. Observation qua application event bất đồng bộ

Trong modular monolith, `ordering` có thể phát `OrderPlaced` và `notification` xử lý bằng `@ApplicationModuleListener`. Annotation này kết hợp hành vi listener theo transaction với bất đồng bộ và transaction xử lý riêng. Vì công việc có thể chạy trên **executor thread**, context của HTTP request hiện tại có nguy cơ bị mất khi chuyển thread.

~~~mermaid
sequenceDiagram
    participant H as HTTP thread / ordering
    participant E as Async executor
    participant N as notification listener
    H->>H: publish OrderPlaced
    H->>E: schedule listener sau commit
    Note over H,E: Chụp current observation/trace context
    E-->>N: chạy task trên worker thread
    Note over E,N: Khôi phục context nếu executor được cấu hình
    N->>N: tạo module-entry observation
~~~

Một lần xử lý event bất đồng bộ có thể xuất hiện trong **cùng trace** nếu:

- Context thích hợp được capture lúc lịch trình công việc được tạo.
- Executor/task decorator truyền và khôi phục context sang thread thực thi.
- Listener nằm trong phạm vi instrumentation, tracer/exporter đã được cấu hình.
- Sampling và quá trình gửi span không loại bỏ tín hiệu đang tìm.

Nếu thiếu một trong các điều kiện, listener có thể vẫn chạy thành công nhưng span tách sang trace khác hoặc không xuất hiện. Vì vậy, thiếu span **không đủ bằng chứng** để kết luận event không được xử lý.

### 7.1. Cấu hình executor truyền context

Với executor do ứng dụng tự khai báo, có thể gắn `ContextPropagatingTaskDecorator`:

~~~java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
class AsyncConfiguration {

    @Bean(name = "taskExecutor")
    ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("module-event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

`ContextPropagatingTaskDecorator` thuộc Spring Framework; cần có thư viện Micrometer Context Propagation trong runtime classpath. Với ứng dụng có nhiều executor, hãy xác minh listener thực sự chạy trên executor đã gắn decorator. Với executor auto-configured trên Spring Boot 4.x, property `spring.task.execution.propagate-context=true` là một cách bật truyền context theo tài liệu Boot. Với các nhánh Boot khác, xem hướng dẫn tương ứng; không giả định một property luôn tồn tại ở mọi phiên bản.

Decorator giúp truyền **current context** qua ranh giới thread. Nó không làm cho event trở nên bền vững, không thêm retry và không tự sinh spans nếu tracing không được bật. Nếu event được đưa qua message broker hoặc sang tiến trình khác, cần cơ chế inject/extract trace headers của messaging instrumentation; task decorator chỉ giải quyết thread trong cùng tiến trình.

### 7.2. Trace continuity không phải event reliability

Spring Modulith có **Event Publication Registry** để theo dõi việc xử lý các publication tới transactional listeners, hỗ trợ phát lại những publication chưa hoàn tất tùy cấu hình. Một lần retry sau khi ứng dụng khởi động lại có thể không còn original HTTP trace context. Khi đó, cần correlation ID nghiệp vụ để nối các lần thử xử lý và xem trạng thái publication.

**Truyền trace context** phục vụ liên kết các vùng thực thi được quan sát. **Event Publication Registry** phục vụ theo dõi và phục hồi xử lý event. Đây là hai mục tiêu riêng; observation không bảo đảm exactly-once delivery hoặc tính idempotent của listener.

## 8. Metrics của domain event có liên quan ra sao?

Ngoài module-entry observations, Spring Modulith ghi nhận các **domain event được phát** bằng Micrometer counter:

| Counter | Công dụng |
| --- | --- |
| `module.events.published` | Đếm tổng các lượt phát domain event, có nhãn như `module.event.type`, `module.identifier`, `module.name`. |
| `module.events.published.$moduleIdentifier.$simpleEventTypeName` | Counter riêng cho từng loại event; có thể thêm tag nghiệp vụ bằng `ModulithEventMetricsCustomizer`. |

**Counter event không phải cùng loại dữ liệu với module-entry observation.** Counter đo số lần một sự kiện được phát; module-entry span/observation đo vùng thực thi tại điểm vào module đã được instrument. Cả hai có thể xuất hiện trong cùng quy trình nghiệp vụ nhưng không suy luận kết quả của cái này từ cái kia.

Ví dụ trong 10 phút:

- `ordering` phát 120 `OrderPlaced` → counter phản ánh hoạt động phát sự kiện.
- Có 100 module-entry spans của `notification` được export → chỉ phản ánh phần được ghi nhận sau instrumentation và sampling.
- Có 99 email thành công → phải xác định từ metric nghiệp vụ, log hoặc trạng thái xử lý event.

Không dùng phép trừ đơn giản giữa ba con số để tính “số event bị mất” khi chưa biết sampling, thời điểm xử lý, retry và semantics của các bộ đếm.

## 9. Kiểm tra observation, metrics và traces trong runtime

### 9.1. Đọc thông tin từ Actuator

Sau khi chạy ứng dụng và tạo một giao dịch đặt hàng:

~~~bash
# Xem cấu trúc application module.
curl -s http://localhost:8080/actuator/modulith

# Liệt kê những meter đã được đăng ký.
curl -s http://localhost:8080/actuator/metrics

# Event counter do Spring Modulith hỗ trợ.
curl -s http://localhost:8080/actuator/metrics/module.events.published

# Xuất metrics nếu có Prometheus registry.
curl -s http://localhost:8080/actuator/prometheus
~~~

**Không có endpoint chuẩn `/actuator/traces` chỉ vì đã thêm Insight Starter.** Để xem span của từng request, truy vấn tracing backend sau khi cấu hình tracer và exporter. Tên meter của module-entry observation cần kiểm tra từ registry thực tế vì convention, phiên bản và naming strategy có thể ảnh hưởng tên.

### 9.2. Diễn giải một trace

Một timeline **minh họa** của request có gọi module `payment`:

~~~text
Trace: POST /orders
└── HTTP server span
    └── module-entry: ordering / placeOrder
        └── module-entry: payment / authorize
            └── custom observation: payment.capture
~~~

Không phải ứng dụng nào cũng tự sinh đủ các chặng như vậy. Chặng `payment.capture` chỉ có nếu mã có instrument thủ công tương ứng; chặng `ordering` và `payment` chỉ có khi lời gọi đi qua điểm vào module được Spring Modulith instrument; các chặng còn lại phụ thuộc tracing stack.

Khi điều tra một trace, kiểm tra:

1. **Trace ID** và các span thuộc cùng trace.
2. **Module identifier/method** để tìm đúng ranh giới có liên quan.
3. **Thời lượng của từng span**, nhớ rằng duration có thể bao gồm thời gian gọi DB/gateway bên trong.
4. **Error và trạng thái thực thi**; một span không có lỗi không mặc nhiên xác nhận nghiệp vụ đã hoàn thành thành công.
5. **Parent/child và thread boundary**, đặc biệt khi event xử lý bất đồng bộ hoặc qua broker.

### 9.3. Kiểm tra theo từng tầng

| Tình huống | Cần xác minh |
| --- | --- |
| `/actuator/modulith` có module nhưng không có span | API có thực sự được gọi qua bean được instrument không; đã có tracing handler, sampling và exporter chưa. |
| Có span HTTP nhưng không thấy span `payment` | Lời gọi có đi nhánh payment không, component có là module API, có dùng Spring proxy/interceptor phù hợp không. |
| `payment.capture` không hiện | Code có thực thi đoạn `observe(...)` không, registry có handler phù hợp không, span có bị lọc hoặc không export không. |
| Counter event tăng nhưng listener không thấy | Xem transaction phase, cấu hình listener, executor, propagation, sampling và Event Publication Registry. |
| Span listener có trace ID khác request | Context mất ở thread boundary hoặc đó là lần retry/thực thi khác. |
| Không thấy metrics qua `/actuator/metrics` | Chưa đăng ký meter, chưa có lưu lượng, thiếu registry/handler, endpoint chưa expose hoặc bị bảo vệ. |
| Dashboard metric tăng quá nhiều series | Kiểm tra tên observation động và low-cardinality tags chứa ID tự do. |
| Trace ghi dữ liệu nhạy cảm | Kiểm tra high-cardinality attributes, masking và chính sách xuất dữ liệu. |

## 10. Một quy trình kiểm chứng được đề xuất

Để bảo đảm việc quan sát có ý nghĩa và vẫn bám theo kiến trúc mô-đun:

1. **Kiểm chứng cấu trúc:** dùng `ApplicationModules.verify()` và tài liệu do `Documenter` sinh để kiểm tra API, package nội bộ và quan hệ phụ thuộc.
2. **Bật observability:** thêm Spring Modulith Insight Starter hoặc module observability phù hợp với phiên bản ứng dụng.
3. **Cấu hình pipeline:** xác định metrics handler/registry, tracing bridge, exporter và backend.
4. **Tạo một giao dịch tái hiện được:** gửi request có gọi qua API `ordering → payment`.
5. **Đọc module graph:** xác nhận runtime nhận diện các application module đúng thiết kế.
6. **Đọc traces:** tìm module-entry spans, phân biệt chúng với observation do ứng dụng tự instrument.
7. **Đọc metrics:** kiểm tra event counters và các timer/meter được registry sinh ra; không nhầm số event đã phát với listener thành công.
8. **Thử bất đồng bộ:** tạo event xử lý trên executor, xác minh context propagation và trace correlation.
9. **Chỉnh convention khi thật sự cần:** chỉ thêm nhãn nghiệp vụ có tập giá trị hữu hạn, không thay đổi tên và tag hàng loạt nếu dashboard không yêu cầu.
10. **Duy trì kiểm chứng:** đưa kiểm tra kiến trúc vào CI, quan sát biến động sau triển khai và đối chiếu khi module boundary thay đổi.

## 11. Những ngộ nhận cần tránh

**“Có `ObservationRegistry` là tự có trace trong Grafana.”** Chưa đủ. Phải có observation handler/tracing bridge, exporter và backend nhận dữ liệu.

**“Bật Insight Starter sẽ tạo span cho mọi method trong mọi package.”** Không. Instrumentation Spring Modulith tập trung vào các điểm vào API application module được hỗ trợ; code tự gọi hoặc internal helper không phải lúc nào cũng được instrument.

**“Low cardinality luôn tốt, high cardinality luôn xấu.”** Sai theo nghĩa đơn giản đó: low cardinality phù hợp cho metric labels; high cardinality có thể có ích trong traces nếu được sử dụng cẩn trọng, không chứa dữ liệu nhạy cảm và được kiểm soát chi phí.

**“`module.events.published` tăng chứng minh một listener đã thành công.”** Không. Counter phản ánh publication; cần tín hiệu xử lý listener riêng.

**“Có module-entry span nghĩa là kiến trúc tuân thủ mọi quy tắc.”** Không. Trace quan sát lần thực thi; `ApplicationModules.verify()` thực thi kiểm chứng quy tắc phụ thuộc tĩnh.

**“Span listener phải luôn là con trực tiếp của HTTP span.”** Không. Listener có thể chạy async, sau khi HTTP kết thúc, hoặc xuất hiện ở lần retry khác; quan hệ tùy context capture và propagation.

## 12. Bài tập thực hành và câu hỏi tự kiểm tra

### Bài tập 1 — Quan sát lời gọi qua ranh giới

Tạo hai application module `ordering` và `payment`. Gọi `OrderService.placeOrder(...)` qua một HTTP endpoint, sau đó đối chiếu `/actuator/modulith` với tracing backend. Xác nhận chiều phụ thuộc cấu trúc và module-entry span nếu instrumentation hoạt động. Ghi lại điểm nào trong trace tương ứng với API module.

### Bài tập 2 — Tạo observation riêng

Thêm một thao tác `PaymentCaptureService.capture(...)` dùng `Observation.createNotStarted(...).observe(...)`. Đặt tên `payment.capture` và tag `payment.channel` có ba giá trị `web`, `mobile`, `pos`. Kiểm tra tracing backend hoặc metrics registry cho thấy gì trước và sau khi instrument.

### Bài tập 3 — Kiểm tra tag cardinality

So sánh `lowCardinalityKeyValue("payment.channel", "web")` với `highCardinalityKeyValue("order.id", "...")`. Giải thích vì sao không nên gán `order.id` làm low-cardinality metric tag. Không sử dụng dữ liệu khách hàng thật khi thực hành.

### Bài tập 4 — Truyền context qua executor

Cho `notification` nhận `OrderPlaced` bất đồng bộ. Trong môi trường dev, so sánh trace của listener trước và sau khi dùng `ContextPropagatingTaskDecorator` trên **executor thực sự được sử dụng**. Ghi nhận liệu trace ID có được nối tiếp và giới hạn của kết quả khi sampling được bật.

### Bài tập 5 — Thêm convention

Đăng ký `ModulithObservationConvention` như mục 6 và thêm tag `product.area=shop`. Kiểm tra tag có xuất hiện trên observation phù hợp. Giữ nguyên nhãn module mặc định và không thay đổi cấu hình production khi chưa đánh giá dashboard.

### Câu hỏi tự kiểm tra

**Câu 1.** `Observation` và `ObservationHandler` khác nhau thế nào?

**Đáp án:** `Observation` mô tả vùng thực thi và vòng đời; `ObservationHandler` xử lý các tín hiệu vòng đời để ghi metrics, tạo spans hoặc hành động quan sát khác.

**Câu 2.** `ModulithObservations.MODULE_ENTRY` biểu diễn sự kiện nào?

**Đáp án:** Hoạt động đi vào application module được instrumentation ghi nhận, không phải một `ApplicationEvent` do mã nghiệp vụ phát.

**Câu 3.** Vì sao không thấy module-entry span chưa đủ để kết luận không có phụ thuộc giữa hai module?

**Đáp án:** Graph chứa quan hệ cấu trúc, trong khi trace chỉ chứa những chặng thực thi được instrument và được thu thập theo sampling/exporter.

**Câu 4.** Lúc nào cần `ModulithObservationConvention`?

**Đáp án:** Khi cần tùy biến naming hoặc key/value của module-entry observations theo quy ước telemetry, chẳng hạn bổ sung nhãn có cardinality thấp.

**Câu 5.** Muốn thêm tag `sales.channel` cho counter riêng của `OrderPlaced`, nên dùng API nào?

**Đáp án:** `ModulithEventMetricsCustomizer`, vì nó được thiết kế cho per-event counter; không nhầm với `ModulithObservationConvention`.

**Câu 6.** `ContextPropagatingTaskDecorator` giải quyết vấn đề gì?

**Đáp án:** Truyền ngữ cảnh observation/trace qua thread boundary của executor; nó không bảo đảm retry, tính bền vững event hoặc khả năng xuất spans khi thiếu tracing backend.

## 13. Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): Insight Starter, module-entry spans, event metrics và conventions.
- [Spring Modulith — `ModulithObservations` Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.html): `MODULE_ENTRY`.
- [Spring Modulith — `ModulithContext` Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html): context module và metadata của lời gọi.
- [Spring Modulith — `ModulithObservationConvention` Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservationConvention.html): convention và các key/value.
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): lifecycle, registry, low/high cardinality và contextual naming.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): handlers và cách dùng `observe(...)`.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): cấu hình observation và context propagation.
- [Spring Boot — Tracing](https://docs.spring.io/spring-boot/reference/actuator/tracing.html): tracing bridge, sampling và exporter.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): kiểm chứng ranh giới module từ mã nguồn.

**Ghi nhớ:** Micrometer Observation ghi nhận **một vùng thực thi**, còn Spring Modulith tạo **module-entry observations** tại các điểm vào API module được instrument. Quan hệ kiến trúc phải được kiểm tra bằng module graph và test; event publication được phản ánh bằng counters riêng; tracing cần handler, exporter và context propagation thích hợp. Đọc kết hợp các nguồn này mới giúp đánh giá chính xác cách hệ thống modular monolith vận hành.
