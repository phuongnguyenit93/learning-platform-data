# Đăng ký convention như một bean

Một ứng dụng Spring Boot được tổ chức bằng **Spring Modulith** có thể quan sát lời gọi đi qua ranh giới các **application module**. Để nhóm vận hành đọc được những dữ liệu đó một cách nhất quán, ta cần một **observation convention**: quy ước đặt tên và xác định các cặp key–value đi kèm với một thao tác được instrument.

Spring Modulith hỗ trợ đăng ký một triển khai `ModulithObservationConvention` như **Spring bean**. Đây là cách đưa quy tắc gắn metadata cho module observation vào Spring ApplicationContext để thành phần observability của Modulith có thể sử dụng. Bài học trình bày cách đăng ký, cách mở rộng quy ước có sẵn mà vẫn giữ metadata quan trọng, rồi kiểm tra tác dụng qua metrics, traces và logs trong khi hệ thống chạy.

Bài thuộc chương **Observation convention** của module `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`. Phạm vi rộng của module học là tài liệu hóa module graph, kiểm tra ranh giới bằng Spring Modulith, quan sát tương tác qua Actuator, event metrics, tracing và context propagation. Riêng bài này tập trung vào **cách cấu hình convention như một bean**, các rủi ro khi tùy chỉnh observation và phương pháp xác minh bean thực sự được sử dụng.

> **Lưu ý phiên bản:** Ví dụ Java chính bên dưới sử dụng API **Spring Modulith 2.1+/2.2** (các kiểu `ModulithObservationConvention` và `ModulithContext` nằm trong package `org.springframework.modulith.observability`). Ở dòng **1.4.x và một số bản 2.0.x**, những kiểu này thuộc `org.springframework.modulith.observability.support` và API mặc định có khác biệt. Hãy chọn BOM Spring Modulith tương thích với Spring Boot của dự án; không sao chép nguyên import giữa các phiên bản mà chưa kiểm tra.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của `Observation`, `ObservationRegistry`, `ObservationConvention` và `ModulithContext`.
2. Đăng ký `ModulithObservationConvention` bằng `@Bean` trong một lớp `@Configuration`.
3. Tùy chỉnh **low-cardinality key values** mà vẫn giữ metadata module do Spring Modulith cung cấp.
4. Hiểu khi nào cần tùy chỉnh `getName()`, `getContextualName(...)` và **high-cardinality key values**, cũng như tác động lên dashboard.
5. Phân biệt convention cho module observation với customizer dùng cho **event publication counters**.
6. Kiểm tra bean có được tạo, module graph có được nhận diện, và telemetry có thay đổi sau lời gọi thật.
7. Tìm nguyên nhân khi đã khai báo bean nhưng trace/metric không thay đổi.

## 2. Convention nằm ở đâu trong đường đi của telemetry?

Khi một lời gọi đi vào API công khai của một application module, phần tích hợp observability của Spring Modulith có thể tạo Micrometer observation (khi được bật và khi lời gọi thuộc phạm vi instrumentation). Convention xác định **tên và key values** cần gắn vào observation; các handler phù hợp sau đó có thể biến observation thành metrics hoặc spans.

~~~mermaid
flowchart TB
    Call["Lời gọi qua API application module"] --> Intercept["Spring Modulith instrumentation"]
    Intercept --> Context["ModulithContext: module + invocation"]
    Convention["Spring bean: ModulithObservationConvention"] --> Define["Tên observation + key values"]
    Context --> Define
    Define --> Registry["Micrometer ObservationRegistry"]
    Registry --> Metrics["Meter handler / MeterRegistry"]
    Registry --> Tracing["Tracing handler / Span"]
    Metrics --> Prom["Actuator + Prometheus nếu cấu hình"]
    Tracing --> TraceBackend["Exporter + tracing backend nếu cấu hình"]
~~~

**Điểm quan trọng:** convention **không tự tạo traffic, không tự khởi chạy tracing exporter và không tự biến mọi phương thức Java thành span**. Nó chỉ mô tả observation đang được tạo bởi instrumentation tương ứng. Cần có lời gọi thực tế, đúng điểm instrument, observation handler và đường thu thập telemetry.

### Các thành phần thường bị nhầm

| Thành phần | Trách nhiệm | Không làm thay |
| --- | --- | --- |
| `ApplicationModules` / module graph | Nhận diện module và phụ thuộc tĩnh | Không ghi mọi lời gọi runtime |
| Instrumentation của Modulith | Bao quanh một số tương tác qua module để tạo observation | Không thay thiết kế module hoặc instrument mọi Java method |
| `ModulithContext` | Chứa thông tin liên quan module/lời gọi được quan sát | Không phải một Spring bean dùng để cấu hình |
| `ModulithObservationConvention` | Quy ước tên và key values từ `ModulithContext` | Không tự xuất metric/trace |
| `ObservationRegistry` và handlers | Nhận lifecycle observation, có thể sinh meter/span | Không mặc định có backend thu thập |
| Actuator / Prometheus / OTLP | Phơi bày hoặc vận chuyển telemetry | Không suy ra dependency graph từ telemetry |

Trong một modular monolith, nhiều module có thể cùng chạy trong **một JVM và cùng `service.name`**. Các key values liên quan module giúp phân biệt phần công việc nằm ở `order`, `inventory` hay `payment` mà không giả định mỗi module là một microservice.

## 3. Trường hợp nào cần một custom convention?

Spring Modulith đã có quy ước mặc định, nên **không cần tự triển khai convention chỉ để bật observability**. Nên cân nhắc custom convention khi có yêu cầu cụ thể:

- Dashboard muốn phân biệt observation bắt nguồn từ ranh giới **application module** với HTTP/JDBC observations bằng một nhãn ổn định.
- Nhóm vận hành cần một quy tắc tên contextual nhất quán khi tìm module spans.
- Ứng dụng cần bổ sung một thuộc tính được chuẩn hóa có **tập giá trị nhỏ** để lọc metrics.
- Dự án có quy định về key naming, ví dụ một prefix cho các nhãn nội bộ, và muốn áp dụng tập trung.

Không nên tạo custom convention chỉ vì muốn thêm `orderId`, `customerId` hoặc `traceId` làm **metric tag**: mỗi giá trị khác nhau có thể tạo một time series. Dữ liệu này phù hợp hơn với trace/log có kiểm soát hoặc nguồn dữ liệu nghiệp vụ.

Một quy ước tốt phải **giữ được tên/metadata có ích mà Modulith đã tạo**, chỉ bổ sung hoặc thay đổi những phần có lý do vận hành rõ ràng.

## 4. Ví dụ tối thiểu: đăng ký bean bằng `@Configuration`

Giả sử ứng dụng có gốc package `com.example.shop`, bên dưới là các application module `order` và `inventory`. Ta tạo lớp cấu hình trong package gốc để Spring component scan tìm thấy:

~~~text
com/example/shop/
├── ShopApplication.java
├── ObservabilityConfiguration.java
├── CustomModulithObservationConvention.java
├── order/
│   └── OrderService.java
└── inventory/
    └── InventoryService.java
~~~

**File `ObservabilityConfiguration.java`:**

~~~java
package com.example.shop;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration(proxyBeanMethods = false)
public class ObservabilityConfiguration {

    @Bean
    ModulithObservationConvention moduleObservationConvention() {
        return new CustomModulithObservationConvention();
    }
}
~~~

**File `CustomModulithObservationConvention.java`:**

~~~java
package com.example.shop;

import io.micrometer.common.KeyValues;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

public final class CustomModulithObservationConvention
        implements ModulithObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
        // Giữ các key values module do Modulith xác định,
        // sau đó thêm một nhãn có đúng một giá trị.
        return context.getLowCardinalityValues()
                .and("telemetry.scope", "application-module");
    }
}
~~~

Ở ví dụ sử dụng API 2.1+/2.2, interface đã cung cấp các **default methods** cho `getName()`, `getContextualName(...)`, `getHighCardinalityKeyValues(...)` và `supportsContext(...)`. Ta chỉ override `getLowCardinalityKeyValues(...)` để thêm một nhãn. Phương thức `KeyValues.and(String, String)` trả về collection key values mới với cặp được bổ sung.

Ba quyết định trong ví dụ rất quan trọng:

1. **Spring quản lý convention:** `@Bean` trả về đúng kiểu `ModulithObservationConvention`; ứng dụng không cần gọi bean theo cách thủ công sau mỗi request.
2. **Giữ mặc định:** `context.getLowCardinalityValues()` giữ những nhãn do Modulith tạo; ta chỉ bổ sung `telemetry.scope`.
3. **Cardinality hữu hạn:** giá trị `application-module` là hằng số. Mọi observation chịu quy ước này cùng có giá trị đó, không tạo một tag value mới cho từng request.

Nhãn `telemetry.scope` là **quy ước do ứng dụng tự đặt**, không phải thuộc tính mặc định Spring Modulith bắt buộc cung cấp. Nó có thể giúp phân nhóm những operation/metrics hỗ trợ nhãn này; sự xuất hiện trong backend phụ thuộc handler, instrumentation và pipeline xuất dữ liệu.

### Vì sao đặt cấu hình ở package gốc?

Spring Boot thường scan các bean từ package chứa `@SpringBootApplication` trở xuống. Nếu `ShopApplication` ở `com.example.shop`, lớp cấu hình cũng ở package đó sẽ được phát hiện theo quy ước mặc định. Nếu lớp cấu hình nằm ngoài phạm vi scan, `@Bean` có thể không được tạo.

Trong ứng dụng có chiến lược scan tùy chỉnh, cũng có thể `@Import(ObservabilityConfiguration.class)` từ cấu hình đã được nạp. Mục tiêu là để class được Spring xử lý, chứ không phải để lưu file trong một thư mục mang tên `observability`.

## 5. Tại sao dùng `@Bean` thay vì tự tạo đối tượng lúc chạy?

Spring Modulith observability được tích hợp vào **Spring ApplicationContext**. Nó tìm và sử dụng bean convention được cung cấp bởi ứng dụng. Vì vậy cách sau **không thay thế đăng ký bean**:

~~~java
// Đoạn minh họa hành vi không đủ:
var convention = new CustomModulithObservationConvention();
// Đối tượng này chỉ là biến local, Spring không tự nhận nó là bean.
~~~

Để Spring nạp được convention, thường chọn **một trong hai** cơ chế:

1. Dùng một phương thức `@Bean` trong lớp `@Configuration` như ví dụ chính.
2. Đánh dấu lớp implementation bằng `@Component` và đảm bảo component scan bao phủ nó.

**Không dùng cả `@Component` lẫn `@Bean` cho cùng implementation** nếu không có chủ đích. Hai bean cùng kiểu có thể làm quá trình chọn convention trở nên không rõ ràng hoặc gây lỗi ứng dụng tùy cách auto-configuration truy xuất bean.

Với bài học này, cách `@Configuration` + `@Bean` dễ kiểm soát hơn: vị trí đăng ký rõ ràng và có thể thay implementation theo môi trường bằng cấu hình nếu thật sự cần.

## 6. Dependency tối thiểu cho ví dụ

Với Maven, khai báo các artifact tương thích qua Spring Boot và Spring Modulith BOM. Khi **mã ứng dụng import trực tiếp `ModulithObservationConvention`**, cần có API artifact ở **compile scope**, bên cạnh phần tích hợp runtime:

~~~xml
<dependencies>
    <!-- API để biên dịch lớp CustomModulithObservationConvention -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-api</artifactId>
    </dependency>

    <!-- Tích hợp module observability và Actuator ở runtime -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Nếu muốn thấy metrics từ Actuator/Prometheus -->
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

Đây là **cấu hình mô tả vai trò dependency**, không phải một `pom.xml` hoàn chỉnh. Starter và dependency management có thể đã kéo theo một số artifact, vì vậy kiểm tra dependency tree để tránh thêm trùng. Tùy cách triển khai, bạn cũng cần dependency Spring MVC/WebFlux, Micrometer Tracing bridge và exporter để có HTTP request và traces hiển thị trên backend.

**Tách rõ ba việc:**

- **Compile:** mã Java phải nhìn thấy interface `ModulithObservationConvention` và `ModulithContext`.
- **Instrumentation:** Spring Modulith Insight/observability phải được bật để quan sát tương tác module.
- **Export:** nếu muốn tra traces trong Tempo/Jaeger/Zipkin hay metrics ở Prometheus, phải cấu hình phần tracing/metrics backend tương ứng.

Thêm API dependency chỉ để mã biên dịch **không** làm tracing tự hoạt động. Đăng ký bean cũng không tự mở Actuator endpoint.

## 7. Khác biệt API giữa các phiên bản

Các ví dụ trên mạng không phải lúc nào cũng dùng cùng package. Theo API chính thức của Spring Modulith:

| Dòng phiên bản | Package cho các kiểu convention/context | Lưu ý khi triển khai |
| --- | --- | --- |
| **1.4.x và một số bản 2.0.x** | `org.springframework.modulith.observability.support` | Interface và default implementation có thể yêu cầu override rõ thêm các phương thức; đối chiếu Javadoc của phiên bản đó. |
| **2.1+/2.2** | `org.springframework.modulith.observability` | Interface có default methods; ví dụ chính trong bài sử dụng `context.getLowCardinalityValues()` và override một phương thức. |

Ví dụ hướng dẫn **không nên copy sang 1.4.x chỉ bằng cách đổi import**, vì `ModulithContext` ở nhánh cũ có API khác. Với dự án cũ, cách ổn định hơn là triển khai interface theo đúng Javadoc của version mà BOM thực sự dùng, và kiểm tra tên mặc định/key values bằng test.

Nếu sử dụng các blog cũ, hãy kiểm tra cả tên artifact, package, phương thức, Spring Boot tương thích. Không đoán version từ code snippet.

## 8. Convention mặc định cung cấp điều gì?

Spring Modulith tạo observation liên quan đến **module entry** và những tương tác được instrument. Theo tài liệu chính thức, thông tin thường được thể hiện quanh các thuộc tính:

| Thuộc tính logic | Ý nghĩa |
| --- | --- |
| `module.identifier` | ID kỹ thuật của application module |
| `module.name` | Tên module |
| `module.invocation-type` | Kiểu lời gọi, ví dụ bean invocation hoặc event listener |
| `module.method` | Phương thức module được thực thi |

Tùy phiên bản và instrumentation, các key có thể thuộc nhóm low/high cardinality khác nhau. **Không mặc định** rằng mọi thuộc tính đều trở thành Prometheus label: convention phân biệt low/high cardinality, còn metric handler có quy tắc riêng khi biến observation thành meter. Tên thực tế cần được xác minh trong ứng dụng.

Convention mặc định sử dụng thông tin từ `ModulithContext`. Vì vậy, cách bổ sung an toàn thường là **mở rộng** bộ key values của context thay vì thay thế toàn bộ bằng một collection mới.

### Phản ví dụ: vô tình làm mất metadata module

~~~java
@Override
public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
    // KHÔNG NÊN: làm mất các low-cardinality keys có sẵn.
    return KeyValues.of("telemetry.scope", "application-module");
}
~~~

Đoạn mã trên có thể khiến người vận hành mất khả năng lọc theo module ID nếu không còn keys liên quan module. Nó chỉ phù hợp khi bạn **chủ đích** thay toàn bộ tập key và chấp nhận tác động lên truy vấn/dashboard, điều hiếm khi cần trong bài toán này.

Thay thế bằng:

~~~java
@Override
public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
    return context.getLowCardinalityValues()
            .and("telemetry.scope", "application-module");
}
~~~

**Tránh trùng tên tag**: không thêm một key custom có cùng tên với key mặc định nhưng giá trị mâu thuẫn. Sử dụng tên mới rõ ràng và kiểm tra kết quả cuối cùng trước khi triển khai dashboard.

## 9. Low cardinality và high cardinality

**Cardinality** là số lượng giá trị phân biệt có thể xuất hiện ở một key. Tên ngắn chưa chắc cardinality thấp: `orderId="1"` có thể tạo ra hàng triệu giá trị, còn `deployment.zone="north"` chỉ có vài giá trị.

| Key gợi ý | Ví dụ | Nhóm đánh giá | Cách sử dụng |
| --- | --- | --- | --- |
| `telemetry.scope` | `application-module` | Rất thấp | Nhãn phân nhóm an toàn |
| `application.module` | `order` / `inventory` | Thường thấp | Dùng khi chưa có nhãn module tương đương |
| `deployment.stage` | `dev` / `test` / `prod` | Thấp nếu chuẩn hóa | Có thể dùng làm metric label nếu cần |
| `invocation.type` | `bean` / `event-listener` | Thấp | Phân nhóm dạng lời gọi |
| `module.method` | Tên phương thức | Có thể tăng theo số method | Cần đánh giá số lượng và mục đích |
| `order.id` | UUID mỗi đơn hàng | Rất cao | Không dùng làm metric label |
| `customer.email` | Email người dùng | Rất cao và nhạy cảm | Không đưa vào tag; hạn chế cả trace/log |
| `trace.id` | ID trace từng request | Rất cao | Dùng làm correlation trong tracing, không dùng làm metric label |
| `exception.message` | Thông điệp lỗi tùy ý | Cao/không ổn định | Chuẩn hóa thành nhóm lỗi hoặc ghi log có kiểm soát |

Số series có thể tăng theo **tích số chiều**. Nếu thêm một key có 3 giá trị vào metric vốn có 4 modules × 2 loại invocation, số tổ hợp tiềm năng thay đổi từ `8` thành `24` (chưa kể instance, environment và metric names). Vì vậy, ngay cả khi mỗi key có ít giá trị, không nên thêm nhiều chiều tùy ý.

**High-cardinality key values** có thể phù hợp với tracing để truy một lần thực thi, nhưng vẫn cần tuân thủ chính sách dữ liệu, sampling và chi phí lưu trữ. Không biến thông tin cá nhân hoặc ID nghiệp vụ thành trace attributes nếu không có nhu cầu cụ thể và cơ chế bảo vệ phù hợp.

## 10. Tùy chỉnh tên observation và tên hiển thị span

Ngoài key values, convention còn liên quan hai loại tên:

- `getName()`: tên **observation logic**, thường dùng trong việc định danh meter/observation.
- `getContextualName(ModulithContext)`: tên mang **ngữ cảnh lời gọi**, có thể được tracer sử dụng để hiển thị span dễ đọc.

Ở API 2.1+/2.2, interface có default implementations. Nếu chỉ muốn thêm một tag, hãy giữ tên mặc định để giảm nguy cơ thay đổi dashboard và truy vấn.

Khi có nhu cầu đổi tên, trước tiên phải phân biệt mục tiêu:

| Mục tiêu | Cách làm phù hợp |
| --- | --- |
| Muốn tìm tất cả thao tác module bằng một nhãn | Thêm low-cardinality key như `telemetry.scope` |
| Muốn span name dễ đọc | Xem `getContextualName(...)` và naming convention đang được dùng |
| Muốn metric được gom theo một operation ổn định | Cân nhắc `getName()` cùng tác động đến time series |
| Muốn xem từng order ID | Dùng truy vết/log/correlation có kiểm soát, không nhét ID vào tên operation |

**Không đặt `orderId`, `userId` hoặc UUID vào tên observation**, vì tên thay đổi theo traffic có thể làm tăng số meter hoặc tạo vô số span names, khiến dashboard và truy vấn khó kiểm soát.

Nếu vẫn cần override tên contextual, hãy bảo đảm:

1. Không làm mất module identity hoặc tên operation quan trọng.
2. Tên chỉ chứa những thành phần đã chuẩn hóa hoặc metadata kỹ thuật ổn định.
3. Test so sánh trace trước và sau thay đổi để xác nhận tên đủ rõ.
4. Các bộ lọc hoặc dashboards phụ thuộc tên cũ đã được đánh giá và cập nhật.

## 11. Phân biệt bean convention với các điểm mở rộng khác

Trong cùng một ứng dụng, có thể gặp nhiều API cấu hình telemetry. Chúng không thể thay thế tùy ý cho nhau:

| Điểm mở rộng | Phạm vi chủ yếu | Ví dụ |
| --- | --- | --- |
| `ModulithObservationConvention` | Quy ước cho module observations | Thêm nhãn `telemetry.scope=application-module` |
| `ModulithEventMetricsCustomizer` | Tùy chỉnh counters của **event publications** | Thêm tag `sales.channel=mobile` cho một loại domain event |
| `ObservationFilter` của Micrometer | Điều chỉnh context/key values trong luồng observation theo cơ chế chung | Gắn nhãn tổ chức khi có điều kiện thích hợp |
| `MeterFilter` của Micrometer | Chấp nhận, từ chối hoặc biến đổi meter IDs | Giới hạn cardinality hay áp dụng rename metric |
| Tracing sampler/exporter | Quyết định trace nào được giữ và gửi ra backend | Sampling, OTLP endpoint |
| Logging configuration/MDC | Chọn định dạng và trường tương quan trong logs | In `traceId`/`spanId` trong structured log |

Ví dụ: một `OrderPlaced` được publish rồi được một listener `inventory` xử lý. Event publication counter đo **số lần publish**, còn convention của module observation mô tả **thao tác module được instrument**. Nếu listener lỗi sau commit, publication counter không đủ để chứng minh kết quả xử lý; cần xem listener metrics, traces/logs, publication registry (nếu có) và trạng thái nghiệp vụ.

## 12. Quy trình nạp và sử dụng bean

Một custom convention có hiệu lực khi **cả hai điều kiện** đều thỏa mãn:

1. Spring đã tạo bean `ModulithObservationConvention` trong ApplicationContext.
2. Phần tích hợp observability của Spring Modulith đang hoạt động và sử dụng bean đó khi instrument module interactions.

~~~mermaid
flowchart TD
    Start["Spring Boot startup"] --> Config["Component scan / @Import configuration"]
    Config --> Bean["Tạo ModulithObservationConvention bean"]
    Start --> Insight["Auto-configuration Modulith Insight"]
    Bean --> Wire["Chọn convention cho module observation"]
    Insight --> Wire
    Wire --> Call["Lời gọi vào API module"]
    Call --> Obs["Tạo observation với convention"]
    Obs --> Output["Metrics / spans khi có handler & exporter"]
~~~

Mã `@Bean` có thể hoàn toàn đúng nhưng vẫn chưa thấy telemetry nếu:

- File cấu hình nằm ngoài phạm vi component scan nên bean không được tạo.
- Đang có nhiều bean cùng kiểu khiến quá trình chọn bean không rõ ràng.
- Thiếu dependency runtime Modulith Insight/observability.
- Base package/module discovery không nhận diện module như mong đợi.
- Lời gọi chạy trong cùng bean hoặc không đi qua điểm instrumentation.
- Observation có nhưng không có handler cho metrics hoặc tracing.
- Tracing exporter/sampling/backend chưa hoạt động.

Vì thế, kiểm tra **bean tồn tại** chỉ là bước đầu, chưa phải bằng chứng convention đã tác động tới telemetry.

## 13. Xác minh bean trong Spring ApplicationContext

Cách nhanh nhất là kiểm tra Spring context bằng một test. Ví dụ dùng Spring Boot Test, JUnit 5 và AssertJ nếu dự án đã có những dependency này:

~~~java
package com.example.shop;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

@SpringBootTest
class ObservationConventionRegistrationTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void registersOneConventionBean() {
        var beans = applicationContext
                .getBeansOfType(ModulithObservationConvention.class);

        assertThat(beans).hasSize(1);
        assertThat(beans.values().iterator().next())
                .isInstanceOf(CustomModulithObservationConvention.class);
    }
}
~~~

Test này trả lời một câu rất cụ thể: **Spring có một bean đúng kiểu custom convention**. Nó chưa chứng minh rằng có module interaction nào được instrument hoặc tracing exporter gửi dữ liệu thành công.

### Kiểm tra trực tiếp logic thêm tag

Ở các phiên bản hỗ trợ `ModulithContext`, một test chi tiết hơn có thể cung cấp context được dựng từ test fixtures phù hợp, rồi gọi `getLowCardinalityKeyValues(...)` và so key values. Tuy nhiên `ModulithContext` cần thông tin module, method invocation và environment, nên không nên tạo “context giả” quá đơn giản làm mất ngữ nghĩa module.

Với chức năng thực tế, cách xác minh quan trọng hơn là gửi một lời gọi module rồi xem telemetry đầu ra.

## 14. Xác minh tác dụng qua Actuator, metrics và tracing

Giả sử module `order` có REST endpoint gọi API của module `inventory`. Trước tiên, dùng Spring Modulith kiểm tra module graph để biết hai module được nhận diện chính xác:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleStructureTest {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Sau đó bật Actuator và các backend tương ứng. Với Prometheus registry, cấu hình ví dụ cho **local/test**:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  tracing:
    sampling:
      probability: 1.0
~~~

Giá trị sampling `1.0` chỉ thuận tiện cho bài thử nghiệm; không mặc định phù hợp với production. Nếu cần tracing tới backend, bổ sung bridge và exporter tương thích với stack đang dùng, và cấu hình đúng OTLP/Zipkin endpoint. Actuator metrics **không tự xuất spans**.

### Bước 1 — Xác nhận endpoint

~~~bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
~~~

Trên Windows PowerShell, có thể dùng `curl.exe` nếu `curl` trỏ tới alias khác. Nếu trả `404`, kiểm tra endpoint exposure, registry và management port/path. Nếu trả `401`/`403`, cần xác thực hoặc quyền truy cập theo cấu hình. Không mở endpoint quản trị công khai chỉ để làm bài thực hành.

### Bước 2 — Tạo lời gọi qua module boundary

Dùng một tuyến nghiệp vụ thực tế hoặc endpoint thử nghiệm trong staging:

~~~text
HTTP GET /demo/orders/availability
    ↓
order.OrderService
    ↓ gọi API module
inventory.InventoryService
~~~

Gửi request vài lần, ghi thời điểm và HTTP status. **Không mặc định** một lời gọi Java đều tạo span module; phải có đúng module boundary, điểm instrument và cấu hình phù hợp.

### Bước 3 — Kiểm tra nhãn mới

Ở những observations có metric handler tương ứng, nhãn `telemetry.scope=application-module` có thể xuất hiện trong meter được tạo. Kiểm tra danh sách meter trước:

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/prometheus
~~~

**Tên meter phải lấy từ output thực tế**, vì tên và quy tắc meter của Modulith/handler có thể thay đổi theo phiên bản. Tìm nhãn đã thêm và xác minh những nhãn module có sẵn vẫn còn; chú ý rằng một số low/high-cardinality keys không phải lúc nào cũng cùng xuất hiện trong cả metric và span.

Ở tracing backend, chọn đúng `service.name`, khung thời gian request và xem spans được instrument. Một ví dụ biểu diễn **minh họa**:

~~~text
service.name = shop-application
traceId = 41ad... (ví dụ)

HTTP GET /demo/orders/availability   110 ms
  └─ module operation: order           83 ms
     └─ module operation: inventory   24 ms
        telemetry.scope = application-module
~~~

Các tên span, thời gian và tag key còn phụ thuộc instrumentation và bridge/exporter; không phải output cố định của Modulith. Nếu đã có HTTP span nhưng không có module span, đừng vội kết luận bean không hoạt động: hãy kiểm tra module detection và điểm instrument.

### Bước 4 — Đối chiếu trước và sau thay đổi

| Điểm so sánh | Trước khi đăng ký custom convention | Sau khi đăng ký |
| --- | --- | --- |
| Spring bean custom convention | Không | Có đúng một bean |
| Module graph | Các module dự kiến | Không đổi chỉ vì thêm convention |
| Tên observation mặc định | Theo phiên bản | Giữ nguyên nếu không override tên |
| Low-cardinality keys mặc định | Có khi được instrument | Vẫn có vì đã kế thừa context |
| `telemetry.scope` | Chưa có | `application-module` ở observation tương ứng |
| HTTP server span | Theo HTTP instrumentation | Không bắt buộc thay đổi |
| Trace/log correlation | Theo tracing context | Không tự sửa lỗi async propagation |

**Điều chứng minh được:** khi quan sát thực tế có nhãn mới trong đúng loại module observation, convention đã tác động đến đường instrumentation đó. Nếu chỉ thấy bean trong context mà thiếu nhãn trên output, bài kiểm tra mới dừng ở **đăng ký bean**, chưa chứng minh được hiệu lực runtime.

## 15. Context propagation khi có application event

Convention không giải quyết mọi tình huống mất ngữ cảnh tracing. Giả sử `order` phát `OrderPlaced` và một listener ở `inventory` xử lý sau commit:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as order
    participant E as Event publisher
    participant I as inventory listener
    participant T as Metrics/Tracing

    C->>O: POST /orders
    O->>T: HTTP/module observations
    O->>E: Publish OrderPlaced
    O-->>C: 201 Created
    Note over E,I: Listener có thể chạy trên executor khác, sau commit
    E-->>I: OrderPlaced
    I->>T: Module/listener observation nếu được instrument
~~~

Nếu listener được instrument nhưng trace context không chuyển sang thread mới, span của listener có thể xuất hiện trong **trace khác** hoặc thiếu trace ID. Custom convention vẫn có thể thêm `telemetry.scope` lên observation của listener; nhưng nó **không tự nối trace ID**.

Muốn liên kết:

- Kiểm tra executor thực tế dùng cho listener và cơ chế truyền context trong phiên bản Spring/Micrometer đang sử dụng.
- Với message broker, cần instrumentation truyền và trích xuất trace headers ở producer/consumer.
- Nếu async work có vòng đời độc lập, dùng event/correlation ID nghiệp vụ hoặc span links phù hợp khi truy nguyên quan hệ.
- Kiểm tra riêng **publication state** và kết quả consumer; việc HTTP trả `201` không bảo đảm listener thành công.

**Trace context, transaction context và idempotency key** giải quyết những vấn đề khác nhau. Đăng ký convention không làm listener chạy đồng bộ, không mở rộng transaction và không bảo đảm exactly-once processing.

## 16. Những lỗi thường gặp khi đăng ký convention

| Triệu chứng | Khả năng | Hướng kiểm tra |
| --- | --- | --- |
| IDE không tìm được `ModulithObservationConvention` | Chưa có compile dependency hoặc import sai package theo phiên bản | Đối chiếu BOM/Javadoc; thêm API artifact ở compile scope |
| Spring test không tìm được custom bean | `@Configuration` nằm ngoài component scan, chưa import hoặc profile không bật | Kiểm tra package gốc, cấu hình scan và test ApplicationContext |
| Có hai bean convention | Đăng ký cả `@Component` và `@Bean` hoặc nhiều cấu hình trùng | Giữ một lựa chọn rõ ràng; kiểm tra bean names/types |
| Bean có nhưng không có span module | Thiếu runtime instrumentation, module discovery sai hoặc chưa gọi qua ranh giới instrumented | Xem dependency, module graph, lời gọi thực |
| Có HTTP spans nhưng không có tag mới | Tag chỉ gắn với module observations | Tìm module spans, không dùng HTTP span làm phép kiểm tra chính |
| Module spans có nhưng mất nhãn module | Override low keys và thay toàn bộ `KeyValues` | Kế thừa `context.getLowCardinalityValues()` rồi bổ sung tag |
| Metrics tăng số series bất thường | Tag chứa user/request/event ID, hoặc quá nhiều chiều phân nhóm | Giới hạn tập giá trị, xem số meter IDs và labels |
| Đổi tên convention làm dashboard trống | Tên meter/operation đã thay nhưng truy vấn chưa cập nhật | So tên/labels thật và sửa dashboard/alert |
| Trace bị tách khi listener chạy | Thiếu context propagation qua executor/broker | Kiểm tra tracing context và cơ chế async |
| Actuator hiển thị metrics nhưng trace backend trống | Thiếu bridge/exporter, sampling hoặc lỗi receiver | Kiểm tra từng chặng export và backend |

Lỗi cần khoanh vùng bằng **bằng chứng theo thứ tự**: compile → Spring bean → Modulith instrumentation → observation handler → exporter → backend. Không nên sửa nhiều cấu hình một lúc khi chưa biết chặng nào không hoạt động.

## 17. Bài thực hành: từ bean tới telemetry có chứng cứ

Chuẩn bị một Spring Boot application có ít nhất hai module `order` và `inventory`, một HTTP endpoint gọi công khai từ module này sang module kia, Actuator và bộ thu telemetry phù hợp.

1. **Xác định phiên bản:** ghi lại Spring Boot/Spring Modulith và package chứa `ModulithObservationConvention`; chọn đúng mẫu Java của phiên bản.
2. **Xác nhận module graph:** chạy kiểm tra ranh giới bằng `ApplicationModules.of(...).verify()` và bảo đảm module API được phát hiện.
3. **Đăng ký bean:** tạo `ObservabilityConfiguration` cùng `CustomModulithObservationConvention`, dùng `@Bean` trả về interface.
4. **Kiểm tra ApplicationContext:** xác nhận chỉ có một custom convention bean đúng loại.
5. **Tạo baseline:** tạm sử dụng convention mặc định trong môi trường test, gửi cùng request và ghi tên/attributes của module observation.
6. **Kích hoạt custom convention:** thêm `telemetry.scope=application-module` bằng cách kế thừa low-cardinality values từ context; gửi lại request.
7. **So output:** tra Actuator metrics và tracing backend, ghi nhãn nào thêm, nhãn nào giữ nguyên, tên observation có đổi không.
8. **Kiểm tra event listener:** phát `OrderPlaced` để xem quan sát ở consumer (nếu instrumentation bao phủ) và ghi nhận trace có được liên kết không.
9. **Thử phản ví dụ có kiểm soát:** trong test riêng, thay low keys bằng collection chỉ chứa một key, quan sát mất module metadata rồi khôi phục implementation an toàn.
10. **Ghi quyết định vận hành:** tại sao chọn nhãn mới, tập giá trị tối đa, truy vấn/dashboard cần dùng và giới hạn khi suy luận từ spans/metrics.

Mẫu ghi chép:

| Hạng mục | Giá trị kỳ vọng | Kết quả quan sát | Kết luận |
| --- | --- | --- | --- |
| Convention bean | Một bean đúng implementation | … | … |
| Module graph | Có `order` và `inventory` | … | … |
| Module observation | Có sau khi gọi API module thuộc phạm vi hỗ trợ | … | … |
| Keys mặc định | Không bị mất | … | … |
| `telemetry.scope` | `application-module` | … | … |
| Metrics ở backend | Có khi handler/export phù hợp | … | … |
| Trace/parent context | Liên kết khi propagation hoạt động | … | … |
| Listener sau commit | Kiểm tra riêng trạng thái nghiệp vụ | … | … |

Không đánh dấu PASS chỉ vì ứng dụng khởi động thành công: hãy ghi rõ **chặng nào đã kiểm chứng**. Nếu chưa có backend, ghi `NOT VERIFIED` cho phần xuất trace/metric ngoài ứng dụng.

## 18. Câu hỏi tự kiểm tra

1. `ModulithObservationConvention` khác gì `ObservationRegistry`?
2. Tại sao tạo một object `new CustomModulithObservationConvention()` trong phương thức bất kỳ chưa đủ để Spring Modulith sử dụng nó?
3. Đăng ký convention dưới dạng `@Bean` cần những điều kiện gì về component scan và dependency?
4. Vì sao nên dùng `context.getLowCardinalityValues().and(...)` thay vì trả về `KeyValues.of(...)` chỉ có tag mới?
5. Một nhãn `orderId` có cardinality cao dù mã đơn chỉ gồm vài ký tự là vì sao?
6. Bạn sẽ kiểm tra thế nào để phân biệt “bean chưa được đăng ký” với “bean đã có nhưng module không được instrument”?
7. Convention cho module observation và `ModulithEventMetricsCustomizer` phục vụ cùng một mục tiêu hay hai loại dữ liệu khác nhau?
8. Vì sao `service.name` vẫn có thể là `shop-application` khi span liên quan module `inventory`?
9. Khi thay đổi `getName()`, có những ảnh hưởng gì tới metrics, dashboard và alerts?
10. Tại sao cùng một convention vẫn có thể tạo observation của listener trong trace mới khi có `@Async`?

## 19. Tổng kết

Đăng ký **`ModulithObservationConvention` như một Spring bean** là cách tập trung quy ước đặt tên và key values cho những module observations mà Spring Modulith tạo ra. Trong API mới, việc giữ các key values mặc định của `ModulithContext` rồi bổ sung một nhãn low-cardinality là lựa chọn dễ kiểm chứng, có ít tác động bất ngờ đến việc phân tích ranh giới mô-đun.

Làm đúng cần nhiều hơn một đoạn mã `@Bean`: phải dùng đúng package/API theo phiên bản, có dependency ở compile/runtime phù hợp, đảm bảo class cấu hình được Spring nạp, có lời gọi qua điểm instrumentation và có đường thu thập metrics/traces. Khi kết hợp module graph, Actuator, tracing, event metrics và context propagation, các nhãn từ convention trở thành một phần bằng chứng để đối chiếu **kiến trúc dự kiến** với **hành vi đã được quan sát**.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Production-ready Features / Conventions](https://docs.spring.io/spring-modulith/reference/production-ready.html).
- [Spring Modulith — ModulithObservationConvention (API hiện hành)](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservationConvention.html).
- [Spring Modulith — ModulithContext (API hiện hành)](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html).
- [Spring Modulith 1.4.x — ModulithObservationConvention (API cũ)](https://docs.spring.io/spring-modulith/docs/1.4.x/api/org/springframework/modulith/observability/support/ModulithObservationConvention.html).
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html).
