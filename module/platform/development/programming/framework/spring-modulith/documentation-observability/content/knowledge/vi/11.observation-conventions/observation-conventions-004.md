# Delegation tới `ModulithContext`

## 1. Vấn đề: ai quyết định tên và tag của một module observation?

Trong ứng dụng Spring Boot dùng **Spring Modulith**, mỗi *application module* sở hữu phần nghiệp vụ và API công khai riêng. Ví dụ `ordering` gọi `payment` để thanh toán, rồi phát `OrderPlaced` để `notification` xử lý. Spring Modulith có thể nhận diện các ranh giới này, đưa kiến trúc ra endpoint `/actuator/modulith` và tạo Micrometer Observation khi một lời gọi đi vào API module được instrument.

Khi quan sát một lời gọi, hệ thống cần quyết định:

- Observation dùng tên ổn định nào để hệ thống metrics tổng hợp?
- Span nên hiển thị tên có ngữ cảnh nào để dễ nhận biết module và phương thức?
- Tag nào có **low cardinality** và có thể dùng trong metrics?
- Thuộc tính nào có **high cardinality** và phù hợp hơn cho traces?
- Làm sao tùy biến một phần thông tin nhưng **không đánh mất những tag module chuẩn**?

Đây là lý do cần hiểu **delegation tới `ModulithContext`**. Theo tài liệu Spring Modulith, implementation mặc định của `ModulithObservationConvention` **ủy quyền các lời gọi tới các phương thức trên `ModulithContext`**. Thay vì tự lặp lại logic lấy tên module, loại lời gọi và phương thức, convention sử dụng dữ liệu mà context đã biết.

Bài này thuộc chương **Observation convention** của `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Mục đích là hiểu cơ chế chuyển thông tin ranh giới module thành metadata quan sát được, đồng thời giữ quan hệ chính xác giữa module graph, Actuator, event metrics, tracing và context propagation. Nội dung tập trung vào **Observation Convention và ModulithContext**, thay vì giải thích lại toàn bộ Micrometer Observation API.

### Mục tiêu học tập

Sau khi học, bạn có thể giải thích:

1. Vai trò của `ModulithObservationConvention` và `ModulithContext` trong module-entry observation.
2. Năm phương thức quan trọng của convention được chuyển tiếp tới đâu.
3. Metadata nào được context cung cấp và cách phân chia low/high cardinality.
4. Cách đăng ký custom convention dưới dạng Spring bean để bổ sung một tag mà vẫn giữ phần mặc định.
5. Cách phân biệt **delegation về metadata** với **context propagation qua thread**.
6. Cách xác minh kết quả trên metrics/tracing backend và tránh các lỗi làm thay đổi ý nghĩa telemetry.

## 2. Bối cảnh runtime: module-entry observation

Spring Modulith có hỗ trợ **observability của application module**. Khi được kích hoạt, các Spring component thuộc API module có thể được aspect/interceptor bao quanh để ghi nhận điểm vào mô-đun. Loại observation được công bố là:

~~~java
org.springframework.modulith.observability.ModulithObservations.MODULE_ENTRY
~~~

Một lần gọi API module có thể tạo:

~~~mermaid
sequenceDiagram
    participant O as ordering / OrderService
    participant I as Spring Modulith interceptor
    participant C as ModulithContext
    participant V as ModulithObservationConvention
    participant R as ObservationRegistry
    O->>I: payment.authorize(...)
    I->>C: thông tin module, invocation, environment
    I->>V: lấy tên và KeyValues
    V->>C: delegation
    C-->>V: metadata
    V-->>I: tên / tags
    I->>R: ghi nhận observation
    Note over I,R: Handler tương ứng có thể tạo metrics hoặc spans
    I-->>O: kết quả gọi API
~~~

Sơ đồ trình bày **trách nhiệm của các thành phần**, không khẳng định toàn bộ thứ tự gọi các phương thức nội bộ trong mọi phiên bản.

Ba lớp cần phân biệt:

- **`ModulithContext`** giữ thông tin về module và invocation đang được đo.
- **`ModulithObservationConvention`** quyết định thông tin nào trở thành tên và key/value metadata của observation.
- **`ObservationRegistry` và handlers** xử lý vòng đời observation; handler của metrics/tracing tạo dữ liệu tương ứng nếu đã được cấu hình.

Một convention **không tự mở span**, không export sang Zipkin/Tempo và không thay thế việc bật instrumentation. Nó là điểm cấu hình **cách đặt tên và gắn thuộc tính** cho observation được framework tạo.

## 3. `ModulithContext` là gì?

Trong Spring Modulith 2.2, lớp:

~~~java
org.springframework.modulith.observability.ModulithContext
~~~

kế thừa `io.micrometer.observation.Observation.Context`. Nó là một **context chuyên biệt của module-entry observation**. Constructor công khai có dạng:

~~~java
ModulithContext(
    ObservedModule module,
    MethodInvocation invocation,
    Environment environment
)
~~~

Ba tham số cho thấy **context lấy dữ liệu từ chính điểm vào module**, chứ không phải từ một JSON hay request header bất kỳ.

| Thành phần đầu vào | Ý nghĩa |
| --- | --- |
| `ObservedModule module` | Đối tượng mô tả application module đang được quan sát. |
| `MethodInvocation invocation` | Invocation tại điểm instrument, có thông tin phương thức được gọi. |
| `Environment environment` | Cấu hình môi trường Spring có liên quan, ví dụ tên ứng dụng nếu được khai báo. |

### 3.1. Các phương thức công khai

| Phương thức | Vai trò |
| --- | --- |
| `getModule()` | Trả về `ObservedModule` để lấy định danh và tên module. |
| `getInvocation()` | Trả về lời gọi `MethodInvocation` gắn với observation. |
| `getApplicationName()` | Tên ứng dụng nếu có cấu hình; API cho phép giá trị `null`. |
| `getContextualName()` | Tên có ngữ cảnh của hoạt động module đang quan sát. |
| `getLowCardinalityValues()` | Bộ `KeyValues` có tập giá trị nhỏ/phù hợp nhóm metrics. |
| `getHighCardinalityValues()` | Bộ `KeyValues` có nhiều giá trị hơn, thường phục vụ ngữ cảnh trace. |
| `DEFAULT_CONVENTION_NAME` | Hằng tên mặc định của module-entry observation, ví dụ `module.invocations` ở Spring Modulith 2.2. |

`ObservedModule` cũng công bố API như `getIdentifier()`, `getDisplayName()`, `getInvokedMethod(invocation)` và `isEventListenerInvocation(invocation)`. Context kết hợp những thông tin này để cung cấp metadata có ý nghĩa kiến trúc.

Đừng tự tạo `ModulithContext` trong service chỉ để ghi một operation tùy ý. Nó là context của **module-entry instrumentation**. Với bước nghiệp vụ bên trong một module, hãy sử dụng Micrometer `Observation` riêng thay vì giả lập một lần đi vào module.

### 3.2. Context không phải bản đồ module đầy đủ

`ModulithContext` gắn với **một observation cụ thể**, không đại diện cho toàn bộ đồ thị phụ thuộc của ứng dụng. Nếu cần xem mọi application module và quan hệ tĩnh, dùng `ApplicationModules`, `Documenter` hoặc `/actuator/modulith`. Context cho biết invocation đang được instrument thuộc module nào, để observation mang được thông tin nhận diện đúng.

## 4. `ModulithObservationConvention` ủy quyền như thế nào?

Interface:

~~~java
org.springframework.modulith.observability.ModulithObservationConvention
~~~

kế thừa `ObservationConvention<ModulithContext>` của Micrometer. Từ dòng API Spring Modulith 2.2, interface này có **default implementation** cho các phương thức chính. Tài liệu production-ready nêu rõ implementation mặc định chuyển tiếp các lời gọi đến `ModulithContext`.

### 4.1. Bảng ánh xạ delegation

| Phương thức của convention | Nguồn giá trị mặc định / ý nghĩa |
| --- | --- |
| `supportsContext(Observation.Context)` | Chỉ áp dụng cho context thuộc loại `ModulithContext`. |
| `getName()` | Tên ổn định theo `ModulithContext.DEFAULT_CONVENTION_NAME`. |
| `getContextualName(ModulithContext)` | Ủy quyền cho `context.getContextualName()`. |
| `getLowCardinalityKeyValues(ModulithContext)` | Ủy quyền cho `context.getLowCardinalityValues()`. |
| `getHighCardinalityKeyValues(ModulithContext)` | Ủy quyền cho `context.getHighCardinalityValues()`. |

Đây là **bảng khái niệm** của hành vi mặc định trong phiên bản đang học. Nó không có nghĩa convention phải tự tính toán tất cả thông tin đó bằng code của ứng dụng. Chính context giữ trách nhiệm giải thích metadata từ module và invocation.

Sơ đồ:

~~~mermaid
flowchart TB
    I["ModulithObservationConvention"]
    S["supportsContext(context)"]
    N["getName()"]
    C["getContextualName(context)"]
    L["getLowCardinalityKeyValues(context)"]
    H["getHighCardinalityKeyValues(context)"]
    X["ModulithContext"]
    X1["DEFAULT_CONVENTION_NAME"]
    X2["getContextualName()"]
    X3["getLowCardinalityValues()"]
    X4["getHighCardinalityValues()"]
    I --> S
    I --> N --> X1
    I --> C --> X2
    I --> L --> X3
    I --> H --> X4
    S -->|"kiểm tra kiểu"| X
    X --> X2
    X --> X3
    X --> X4
~~~

### 4.2. Tại sao cần thiết kế delegation?

Nếu convention mặc định tự lặp lại logic gọi vào module object và parse `MethodInvocation` ở nhiều nơi, hệ thống dễ có sự không nhất quán: tên span, tag module hoặc phương thức có thể được diễn giải khác nhau. Khi **context là nơi tập trung nguồn thông tin**, custom convention có thể tái sử dụng các giá trị đã được framework chuẩn bị.

Thiết kế này cũng cho phép người viết ứng dụng chỉ ghi đè phần cần thiết:

- Muốn thêm tag cố định có ít giá trị? Ghi đè `getLowCardinalityKeyValues(...)` rồi **nối thêm vào tập mặc định**.
- Muốn hiển thị tên span theo quy ước nội bộ? Ghi đè `getContextualName(...)` nhưng cân nhắc giữ phần tên do context tạo.
- Muốn thêm thuộc tính cho trace? Xem xét `getHighCardinalityKeyValues(...)` cùng chính sách dữ liệu.
- Không có yêu cầu mới? Dùng convention mặc định, tránh tự tạo code cấu hình.

## 5. Context cung cấp những key nào?

Một phần rất quan trọng khi tùy biến là không nhầm **nhóm key của Micrometer Observation**. Java API của Spring Modulith công bố các enum mô tả key cho module entry.

### 5.1. Low-cardinality keys

`ModulithObservations.LowKeys` có:

| Enum key | Tên tag quan sát | Ý nghĩa |
| --- | --- | --- |
| `MODULE_IDENTIFIER` | `module.identifier` | Định danh module, ví dụ `ordering` hoặc `payment`. |
| `MODULE_NAME` | `module.name` | Tên hiển thị của application module. |
| `INVOCATION_TYPE` | `module.invocation-type` | Kiểu đi vào module, ví dụ `bean` hoặc `event listener`. |

Đây là các chiều tương đối ổn định, hợp lý để nhóm những observation cùng module hoặc cùng loại invocation. Chúng không phải order ID, user ID hoặc giá trị payload riêng cho từng lần xử lý.

### 5.2. High-cardinality keys

`ModulithObservations.HighKeys` công bố:

| Enum key | Tên tag quan sát | Ý nghĩa |
| --- | --- | --- |
| `MODULE_METHOD` | `module.method` | Phương thức được thực thi ở điểm vào module. |

Vì vậy, theo **phân loại API Spring Modulith 2.2**, `module.method` thuộc **high-cardinality keys**, dù một số backend tracing có thể hiển thị nó cạnh các thuộc tính khác. Không tự suy diễn rằng mọi tag xuất hiện trên span đều được đưa vào metric label. Metrics handler và tracing handler có cách xử lý metadata khác nhau.

Tổng kết:

~~~text
ModulithContext
  low cardinality:
    module.identifier
    module.name
    module.invocation-type
  high cardinality:
    module.method
~~~

### 5.3. `getApplicationName()` không đồng nghĩa một tag mặc định

`ModulithContext` có thể đọc tên ứng dụng thông qua `getApplicationName()`. Giá trị này có thể `null` và có thể tham gia cách xây dựng contextual name, tùy implementation. Nhưng **không nên tự khẳng định `spring.application.name` sẽ là một low-cardinality tag chuẩn của Spring Modulith chỉ vì context có getter này**.

Khi cần phân nhóm theo tên ứng dụng, hãy kiểm tra conventions và resource attributes của tracing/metrics stack hiện tại, rồi mới quyết định có cần thêm tag tùy biến hay không.

## 6. Ví dụ thực tế: giữ metadata mặc định và thêm tag

Giả sử module `ordering` gọi `payment` để thanh toán:

~~~mermaid
flowchart LR
    O["ordering"]
    P["payment"]
    N["notification"]
    O -->|"gọi API thanh toán"| P
    N -->|"tham chiếu OrderPlaced listener"| O
~~~

Đây là graph **phụ thuộc cấu trúc**. Mỗi khi runtime thực thi một API được instrument, context tương ứng có thể tạo thông tin để spans/metrics nhận biết module và invocation. Chúng ta muốn bổ sung tag nghiệp vụ **`product.area=commerce`** vào **module-entry observations** để dashboard có thêm chiều phân loại ổn định.

### 6.1. Dependency tối thiểu

Ví dụ Gradle Kotlin DSL trong dự án sử dụng Spring Boot và Spring Modulith phiên bản tương thích do BOM/plugin quản lý:

~~~kotlin
dependencies {
    runtimeOnly("org.springframework.modulith:spring-modulith-starter-insight")

    // Cần compile scope vì mã Java của ứng dụng import convention API.
    implementation("org.springframework.modulith:spring-modulith-observability-api")

    // Chỉ cần khi muốn xuất metrics cho Prometheus.
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

`spring-modulith-starter-insight` đem vào hỗ trợ Actuator và observability của Spring Modulith. Để xem traces trên Zipkin, Grafana Tempo hoặc backend khác, cần cấu hình **Micrometer Tracing bridge, exporter và tracing backend** tương ứng. Convention không tự tạo pipeline xuất trace.

### 6.2. Một bean custom convention bổ sung low-cardinality tag

~~~java
package com.example.shop;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration(proxyBeanMethods = false)
public class ObservationConventionConfiguration {

    @Bean
    ModulithObservationConvention moduleObservationConvention() {
        return new ModulithObservationConvention() {

            @Override
            public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
                return ModulithObservationConvention.super
                    .getLowCardinalityKeyValues(context)
                    .and(KeyValue.of("product.area", "commerce"));
            }
        };
    }
}
~~~

Điểm mấu chốt nằm ở biểu thức:

~~~java
ModulithObservationConvention.super.getLowCardinalityKeyValues(context)
    .and(KeyValue.of("product.area", "commerce"))
~~~

Lời gọi `super` sử dụng **hành vi delegation mặc định** của interface, nên phần `module.identifier`, `module.name` và `module.invocation-type` do context cung cấp vẫn được giữ. Sau đó `and(...)` nối thêm tag mới.

Trong Spring Modulith **2.2**, cách này khả thi vì các phương thức tương ứng trên interface có implementation `default`. Ở phiên bản khác, xem API/Javadoc cùng dòng release trước khi dùng cú pháp gọi `super`.

**Tại sao chọn `product.area=commerce`?** Giá trị cố định/hữu hạn giúp phân nhóm rõ ràng. Nếu dùng `orderId` hoặc `customerId` làm low-cardinality tag, số series có thể tăng theo từng giao dịch và gây chi phí lớn.

### 6.3. Dùng trực tiếp getter của `ModulithContext`

Một biến thể khác thể hiện trực tiếp ý nghĩa delegation:

~~~java
@Override
public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
    return context.getLowCardinalityValues()
        .and(KeyValue.of("product.area", "commerce"));
}
~~~

Cả hai ví dụ giữ **tập low-cardinality metadata mặc định**, sau đó bổ sung tag. Trong trường hợp này, gọi `ModulithObservationConvention.super...` có lợi ở tính rõ ràng: code đang dựa vào chính default implementation của convention, thay vì tái hiện trực tiếp mối ánh xạ tới context.

### 6.4. Chỉ tùy biến contextual name khi có lý do rõ ràng

Nếu muốn span hiển thị thêm tiền tố ứng dụng, có thể ghi đè:

~~~java
@Override
public String getContextualName(ModulithContext context) {
    return "shop " +
        ModulithObservationConvention.super.getContextualName(context);
}
~~~

Đây là đoạn minh họa **bên trong anonymous convention ở mục 6.2**, không phải một class độc lập. Tên theo ngữ cảnh có thể chứa tên phương thức/module dễ đọc, nhưng tránh thêm giá trị cá biệt như ID đơn hàng vào **tên span**; dữ liệu truy vết cá biệt nên được đặt trong span attributes khi phù hợp và được phép.

Tránh ghi đè `getName()` để trả tên khác theo từng module hoặc từng request nếu không có yêu cầu và đánh giá rõ. Tên observation ổn định của module-entry có thể ảnh hưởng đến tập metric được tạo và dashboard/alert đang dùng.

## 7. Một ví dụ đầy đủ về delegation mặc định

Để hình dung phương thức của convention thực sự dựa trên dữ liệu nào, bảng sau viết lại **ý nghĩa tương đương** của các thao tác:

~~~java
// Minh họa quan hệ delegation, không phải mã nguồn copy từ thư viện.
boolean supportsContext(Observation.Context context) {
    return context instanceof ModulithContext;
}

String getName() {
    return ModulithContext.DEFAULT_CONVENTION_NAME;
}

String getContextualName(ModulithContext context) {
    return context.getContextualName();
}

KeyValues getLowCardinalityKeyValues(ModulithContext context) {
    return context.getLowCardinalityValues();
}

KeyValues getHighCardinalityKeyValues(ModulithContext context) {
    return context.getHighCardinalityValues();
}
~~~

Code block trên mô tả **các phương thức ở mức ý tưởng**, không phải một lớp Java có thể copy nguyên vẹn để biên dịch. Khi triển khai, bạn phải định nghĩa các phương thức trong class/interface phù hợp và dùng những import tương ứng. Trong bài thực hành, nên dùng bean ở mục 6.2 để tránh sao chép lại toàn bộ các phương thức mặc định.

### 7.1. Vì sao không tạo lại metadata thủ công?

Một cách dễ mắc lỗi là bỏ qua context và tự gắn nhãn tùy tiện:

~~~java
// Phản ví dụ: thay thế mọi tag mặc định bằng đúng một tag mới.
@Override
public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
    return KeyValues.of("product.area", "commerce");
}
~~~

Nếu dùng như trên, các tag `module.identifier`, `module.name` và `module.invocation-type` mà hệ thống vốn cung cấp có thể không còn xuất hiện trong **phần key values do convention trả về**. Dashboard lọc theo module bị mất thông tin quan trọng.

Sửa đúng là lấy tập từ default convention/context rồi dùng `.and(...)`. Việc giữ metadata mặc định có giá trị vì các nhãn đó là **cầu nối giữa cấu trúc module và hoạt động được quan sát**.

### 7.2. Tránh xung đột tên key

Một custom tag không nên dùng lại `module.identifier` hoặc `module.name` với một ý nghĩa khác. Nếu cố gắn hai giá trị trái nhau cho cùng một key, kết quả phụ thuộc cách Micrometer và backend xử lý các cặp trùng, có thể gây sai dashboard. Chọn namespace rõ ràng như `product.area`, `business.channel` hoặc `operation.kind` với danh sách giá trị hữu hạn.

## 8. Phân biệt convention, context và propagation

Hai thuật ngữ dễ bị nhầm là:

- **Delegation tới `ModulithContext`**: một lời gọi Java trong quá trình tạo metadata observation, ví dụ `getLowCardinalityKeyValues(ctx)` → `ctx.getLowCardinalityValues()`.
- **Context propagation**: vận chuyển ngữ cảnh hiện hành của Micrometer/tracing **qua ranh giới thread hoặc process**, để các span và log có thể liên kết với trace gốc.

Đây là hai cơ chế khác nhau:

| Thuộc tính | Delegation | Context propagation |
| --- | --- | --- |
| Mục tiêu | Xác định tên và metadata của module observation. | Giữ liên kết giữa các vùng thực thi. |
| Đối tượng chính | `ModulithObservationConvention` và `ModulithContext`. | Micrometer context propagation, executor, tracer, message headers. |
| Khi nào xảy ra | Lúc instrumentation lấy thông tin cho observation. | Lúc lịch trình task hoặc truyền request/message sang thread/process khác. |
| Nếu thiếu/sai | Tag module hoặc contextual name có thể thiếu/sai. | Span listener có thể mang trace ID khác hoặc tách khỏi trace gốc. |
| Có tự bảo đảm listener thành công? | Không. | Không. |

### 8.1. Ví dụ listener chạy bất đồng bộ

`ordering` phát `OrderPlaced`, `notification` xử lý qua `@ApplicationModuleListener`. Nếu listener dùng executor chạy thread khác, một module-entry span có thể được tạo nhưng **không gắn vào trace HTTP ban đầu** nếu trace context không được chuyển tiếp.

~~~mermaid
flowchart LR
    P["HTTP thread: publish OrderPlaced"]
    Q["Async executor"]
    L["notification event listener"]
    O["Modulith Observation"]
    D["Convention delegates to ModulithContext"]
    P -->|"context propagation"| Q --> L --> O --> D
~~~

Việc tùy biến convention ở mục 6 **không thay thế** cấu hình truyền context qua executor. Trong ứng dụng sử dụng Spring Framework, có thể dùng `ContextPropagatingTaskDecorator` trên đúng `ThreadPoolTaskExecutor` (và bật `@EnableAsync` nếu dùng `@Async`). Với message broker sang tiến trình khác, cần hỗ trợ inject/extract trace context qua message headers.

Một trace bị tách **không chứng minh** delegation thất bại; ngược lại, tag module xuất hiện đúng cũng không chứng minh trace context đã được truyền qua mọi thread.

## 9. Kiểm chứng bằng metrics, spans và Actuator

### 9.1. Chạy ứng dụng và tạo một lần gọi qua API module

Trong môi trường học tập, thử luồng `ordering → payment` với cấu hình `spring-modulith-starter-insight` và custom bean ở mục 6.2. Có thể expose các endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,metrics,modulith,prometheus"
  tracing:
    sampling:
      probability: 1.0
~~~

Sampling `1.0` phù hợp khi cần thử nghiệm ít request, còn production nên chọn tỷ lệ theo tải và chi phí. `prometheus` chỉ tồn tại khi ứng dụng thêm registry phù hợp. Tên endpoint/cổng có thể thay đổi bởi cấu hình management, và các endpoint quản trị cần được bảo vệ.

Sau khi khởi động, dùng:

~~~bash
curl -s http://localhost:8080/actuator/modulith
curl -s http://localhost:8080/actuator/metrics
curl -s http://localhost:8080/actuator/prometheus
~~~

`/actuator/modulith` chỉ công bố **cấu trúc module**, không trả ra observation hay span; `/actuator/metrics` trả những meter được registry ghi nhận; traces cần được xem ở tracing backend sau khi bổ sung tracer/exporter.

### 9.2. Dấu hiệu kiểm chứng đúng delegation

Giả sử cuộc gọi `ordering → payment` đi qua điểm instrument thành công. Trên metric hoặc span tương ứng, kiểm tra:

1. Các tag `module.identifier`, `module.name` và `module.invocation-type` vẫn tồn tại.
2. Tag `product.area=commerce` mới xuất hiện ở nơi handler/backend xuất low-cardinality metadata.
3. Nếu có tracing, span có contextual name phù hợp và thuộc tính `module.method` khi được export.
4. Các meter được tạo không nhân số series theo request ID do custom convention.
5. Nếu đã thay đổi contextual name, không bị mất tên module/phương thức cần thiết để debug.

Một tập giá trị **minh họa**:

~~~text
module.identifier       = payment
module.name             = Payment
module.invocation-type  = bean
product.area            = commerce
module.method           = authorize   # high-cardinality metadata
~~~

Đây là ví dụ về các giá trị có thể xuất hiện, không phải cam kết một backend sẽ hiển thị đúng định dạng này. Trong Micrometer, low/high cardinality ảnh hưởng cách handler ánh xạ thành metric tags hoặc trace attributes.

### 9.3. Phân biệt thay đổi ở metrics và traces

Metrics dùng để xem xu hướng như thời lượng module invocation theo `module.identifier` và `module.invocation-type`. Traces dùng để điều tra một lần xử lý và xem span theo thứ tự thực thi, lỗi hoặc thuộc tính phương thức. Nếu custom convention thay đổi low-cardinality tags, số series metric có thể thay đổi; nếu đổi contextual name, tên span hiển thị có thể đổi. Cần kiểm tra tác động tới truy vấn và alert trước khi đưa lên production.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không import được `ModulithObservationConvention` | Thiếu `spring-modulith-observability-api` ở compile scope hoặc dùng phiên bản khác. | Kiểm tra dependency/BOM và Javadoc cùng phiên bản. |
| Không thấy module-entry spans | Chưa bật instrumentation, API không được gọi qua điểm Spring hỗ trợ, hoặc tracer/exporter chưa hoạt động. | Kiểm tra starter, bean, tracing bridge, sampling và backend. |
| Thêm tag mới rồi mất `module.identifier` | Custom method trả `KeyValues` mới mà không nối với phần mặc định. | Dùng `ModulithObservationConvention.super...` hoặc `context.getLowCardinalityValues().and(...)`. |
| `module.method` không có trên metric labels | Đây là high-cardinality key theo phân loại Spring Modulith. | Tìm trên span attributes khi handler hỗ trợ; đừng ép thành low-cardinality nếu không cần. |
| Tag tùy biến không xuất hiện | Bean không được scan, observation đang xem không phải module entry, không có handler hoặc lưu lượng phù hợp. | Kiểm tra `@Configuration`, `@Bean`, phạm vi instrumentation và registry. |
| Metrics tăng hàng nghìn series mới | Tạo tên observation động hoặc tag với orderId/userId. | Dùng tên ổn định và các tag hữu hạn. |
| Span listener không cùng trace với request | Async executor thiếu context propagation hoặc listener chạy lại trong phiên khác. | Kiểm tra TaskDecorator, tracer, sampling và cơ chế retry. |
| Dashboard lọc theo module bị hỏng sau cập nhật | Đổi tên metric, tag module hoặc contextual naming ngoài ý muốn. | Giữ tên/tag mặc định khi chỉ cần thêm tag; kiểm tra migration truy vấn. |
| `/actuator/modulith` có module nhưng không thấy tag module trên traces | Graph tĩnh có dependency nhưng call runtime chưa đi qua điểm instrument. | Tạo một luồng thực thi xác định, kiểm tra aspect/proxy và tracer. |
| Có counter event nhưng không có span listener | Counter publication khác observation listener; sampling, transaction phase hoặc async có thể ảnh hưởng. | Kiểm tra listener thực thi, logging, trace propagation và exporter. |

## 11. Bài thực hành có định hướng

### Thực hành A — Quan sát mặc định

Chạy ứng dụng có hai module `ordering` và `payment`, bật observability mà **không đăng ký custom convention**. Gọi một API `PaymentService` từ `OrderService`. Ghi lại tên span/metric (nếu backend đã cấu hình) và các tag module đang có. Đối chiếu với API `ModulithObservations.LowKeys` và `HighKeys`.

### Thực hành B — Chứng minh delegation được giữ

Thêm bean `ModulithObservationConvention` ở mục 6.2. Gọi lại cùng API. Kiểm tra **vẫn có module.identifier/module.name/module.invocation-type**, đồng thời xuất hiện `product.area=commerce`. Đây là bằng chứng thực tế rằng đoạn custom không thay thế tập metadata gốc.

### Thực hành C — Tái hiện sai sót thường gặp

Trong nhánh thực hành có thể hoàn tác, đổi implementation sang `return KeyValues.of("product.area","commerce")`, gọi API một lần và so sánh tags với cấu hình B. Sau đó khôi phục cách dùng `.super...and(...)`. Mục tiêu là nhìn thấy hậu quả của việc bỏ qua delegation.

### Thực hành D — Thêm contextual name

Ghi đè `getContextualName(...)` theo mục 6.4, dùng tracing backend xem tên span thay đổi ra sao. Giữ nguyên `getName()` để có cơ sở so sánh tên metric/observation không bị đổi. Nếu chưa có exporter, chỉ kết luận được phần cấu hình code, chưa thể khẳng định backend hiển thị như thế nào.

### Thực hành E — Listener bất đồng bộ

Cho `notification` nhận `OrderPlaced` bằng listener bất đồng bộ. Ghi lại trace ID trên publisher và listener, bật context propagation cho đúng executor và quan sát lại. Giải thích vì sao thay convention **không đủ** để nối hai trace nếu thiếu propagation.

### Câu hỏi tự kiểm tra

**Câu 1.** Delegation tới `ModulithContext` có nghĩa là gì?

**Đáp án:** Các phương thức convention mặc định lấy tên và metadata từ `ModulithContext`, thay vì tự xây dựng lại mọi giá trị bằng logic riêng.

**Câu 2.** Phương thức nào của context cung cấp low-cardinality metadata?

**Đáp án:** `getLowCardinalityValues()`; convention tương ứng có `getLowCardinalityKeyValues(ModulithContext)`.

**Câu 3.** Spring Modulith 2.2 phân loại `module.method` vào nhóm nào?

**Đáp án:** High cardinality, được công bố bởi `ModulithObservations.HighKeys.MODULE_METHOD`.

**Câu 4.** Vì sao khi bổ sung tag nên dùng `.and(...)` trên tập mặc định?

**Đáp án:** Để giữ các tag module được framework tạo và chỉ thêm thông tin cần thiết, tránh phá vỡ dashboard/trace queries đang dựa vào metadata chuẩn.

**Câu 5.** `ModulithObservationConvention` có thể tự nối trace qua `@Async` không?

**Đáp án:** Không. Convention quyết định metadata observation; context propagation qua executor và tracer/exporter là trách nhiệm khác.

**Câu 6.** `ModulithObservationConvention` có phải cách thêm tag cho per-event counter `OrderPlaced` không?

**Đáp án:** Không phải điểm mở rộng chuyên biệt cho việc đó; Spring Modulith cung cấp `ModulithEventMetricsCustomizer` để làm giàu counter của từng loại event.

## 12. Tài liệu tham khảo

- [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html): ghi rõ convention mặc định ủy quyền tới `ModulithContext`, cấu hình Insight Starter và module-entry spans.
- [Spring Modulith — `ModulithObservationConvention` Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservationConvention.html): năm phương thức default của interface.
- [Spring Modulith — `ModulithContext` Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html): constructor và các getter context.
- [Spring Modulith — `ModulithObservations.LowKeys`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.LowKeys.html): bộ key low-cardinality.
- [Spring Modulith — `ModulithObservations.HighKeys`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.HighKeys.html): `MODULE_METHOD` là high-cardinality key.
- [Spring Modulith — `ObservedModule` Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ObservedModule.html): metadata và phương thức của module được quan sát.
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): conventions, handlers, low/high cardinality và scope.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): registry, tích hợp metrics/tracing và context propagation.

**Ghi nhớ:** trong Spring Modulith, `ModulithContext` giữ thông tin module-entry observation; `ModulithObservationConvention` mặc định **ủy quyền cho context** để lấy tên và key/value. Khi tùy biến, hãy **giữ phần mặc định rồi bổ sung đúng tag cần thiết**, phân biệt low/high cardinality và không nhầm cơ chế delegation với việc truyền trace context giữa các thread.
