# Kiểm tra thay đổi observation convention

> **Chương:** Phiên bản  
> **Phạm vi:** Spring Modulith — application module, Actuator, event metrics, module entry span và Micrometer Observation  
> **Bài toán:** Kiểm tra và kiểm soát những thay đổi về tên observation, contextual name, tag và API `ModulithObservationConvention` khi nâng phiên bản Spring Modulith.

## 1. Tại sao nâng phiên bản có thể làm dashboard “mất” module?

Một ứng dụng Spring Boot được chia thành `orders`, `payments` và `shipping`. Hệ thống giám sát có dashboard hiển thị:

- Thời lượng lời gọi từ `orders` sang API công khai của `payments`.
- Các trace chứa span ở ranh giới module `payments`.
- Tổng số sự kiện nghiệp vụ được phát hành từ từng module.
- Bộ lọc tìm giao dịch theo `module.identifier` hoặc tên hiển thị của module.

Sau khi nâng Spring Modulith, thao tác thanh toán vẫn hoạt động nhưng một truy vấn dashboard trả về 0. Có ít nhất bốn khả năng:

1. **Điểm quan sát không chạy:** lời gọi đi qua Spring bean hoặc module API đã thay đổi, hoặc thiếu dependency instrumentation.
2. **Observation vẫn được tạo nhưng metadata khác:** tên observation, contextual name, keys hoặc values đã đổi; dashboard vẫn tìm khóa cũ.
3. **Trace không hiển thị:** sampling, OpenTelemetry exporter, collector hoặc truy vấn trace backend có vấn đề.
4. **Nguồn dữ liệu khác nhau:** event metric và module entry span là hai loại tín hiệu; sửa convention cho span chưa chắc đổi event metric.

Mục tiêu không phải buộc mọi chi tiết nội bộ của thư viện giống nhau mãi mãi. Ta cần phát hiện chính xác **hợp đồng quan sát mà hệ thống đang tiêu thụ** (name, tag, giá trị, mức cardinality, đường truyền trace) và chủ động quyết định có cập nhật code, dashboard hay kế hoạch migration.

## 2. Observation convention là gì?

Micrometer Observation cung cấp một mô hình chung để phát sinh dữ liệu quan sát. Một `Observation` có tên, ngữ cảnh, các cặp key/value và lifecycle; tùy các handler được cấu hình, dữ liệu có thể trở thành **metric**, **trace/span** hoặc những tín hiệu khác.

`ObservationConvention<ModulithContext>` định nghĩa cách chuyển ngữ cảnh của Spring Modulith thành tên và các key/value chuẩn. `ModulithObservationConvention` là extension point chuyên dụng cho loại context này.

~~~mermaid
flowchart LR
    A["Lời gọi API module\norders → payments"] --> B["Module entry interceptor"]
    B --> C["ModulithContext"]
    C --> D["ModulithObservationConvention"]
    D --> E["ObservationRegistry"]
    E --> F["Meter observation handler\nMetric"]
    E --> G["Tracing observation handler\nSpan"]
    G --> H["Exporter / collector / UI"]
~~~

Các thành phần cần phân biệt:

| Thành phần | Vai trò | Tác động khi đổi |
|---|---|---|
| `getName()` | Tên observation ở mức hệ thống; có thể tác động tên meter hoặc cách nhận diện observation | Query theo observation name có thể bị ảnh hưởng |
| `getContextualName(context)` | Tên có ngữ cảnh cho một lần thực thi; thường giúp người dùng đọc span | Trình xem trace, bộ lọc tên span có thể khác |
| `getLowCardinalityKeyValues(context)` | Key/value có tập giá trị hạn chế, phù hợp với việc gắn nhãn metric | Dashboard, nhóm metric, chi phí cardinality |
| `getHighCardinalityKeyValues(context)` | Chi tiết có thể mang rất nhiều giá trị, thường hữu ích ở trace | Tìm kiếm span, quyền riêng tư và khối lượng dữ liệu |
| `supportsContext(context)` | Xác định convention nào được áp dụng cho loại context | Chọn nhầm convention có thể khiến customizer không hiệu lực |

**Từ “convention” không đồng nghĩa “exporter”.** Convention quyết định cách mô tả observation. Exporter quyết định dữ liệu tracing được gửi đi đâu. Nếu raw span có tag đúng nhưng UI không thấy, cần điều tra pipeline xuất dữ liệu trước khi sửa convention.

Tương tự, một module graph sinh bằng `Documenter` hoặc trả về từ `/actuator/modulith` là bằng chứng về cấu trúc mô-đun, chưa đủ để xác nhận observation có xuất hiện tại runtime.

### Low cardinality và high cardinality

Giả sử ứng dụng có ba module cố định, `module.identifier` chỉ có một vài giá trị (`orders`, `payments`, `shipping`), thường thích hợp cho low cardinality. Ngược lại, method hoặc một định danh request/đơn hàng có thể tăng theo số lượng giao dịch. Không đưa `orderId`, email, token, trace ID hoặc dữ liệu người dùng vào low-cardinality tags; mỗi giá trị mới có thể sinh thêm chuỗi thời gian (time series) và làm tăng chi phí hệ thống giám sát.

Trong tài liệu Spring Modulith 2.2, các key cho module entry span bao gồm:

| Key hiển thị | Nội dung | Nhóm trong API 2.2 |
|---|---|---|
| `module.identifier` | ID logic của module | Low cardinality |
| `module.name` | Tên hiển thị module | Low cardinality |
| `module.invocation-type` | Phân loại lời gọi vào module (bean hoặc event listener) | Low cardinality |
| `module.method` | Method được thực thi | High cardinality |

Các key này mô tả **module entry observation**. Metric sự kiện (`module.events.published` và metric cho từng loại sự kiện) là một nhóm khác, có các convention và cách tùy biến riêng. Không tự kết luận rằng `module.method` là label của mọi metric vì nó được liệt kê trong tag của trace.

## 3. Những mốc phiên bản quan trọng phải đối chiếu

Tại thời điểm biên soạn (27/11/2026), nhánh stable được tài liệu Spring Modulith công bố là **2.2.0**. Khi làm bài trên một dự án thực tế, hãy lấy phiên bản chính xác từ dependency tree hoặc BOM của dự án, sau đó đọc **Javadoc đúng nhánh phiên bản**. Đoạn ví dụ Java ở phần 6 dùng API của Spring Modulith **2.2.x**, không phải mã nguồn dùng chung cho mọi nhánh.

| Mốc | Điều đáng chú ý khi nâng cấp | Việc phải kiểm tra |
|---|---|---|
| Các bản trước 1.4 | Hỗ trợ tracing từng được hiện thực trực tiếp hơn thông qua tracing API | Không giả định mã tùy biến cũ là `ObservationConvention` |
| **1.4.x** | Chuyển hạ tầng observability sang **Micrometer Observation API**, bổ sung event publication metrics | So tên observation, tags, module event counters và custom hooks |
| **2.0.x** | Bước chuyển hệ nền Spring Boot/Framework và các API của nhánh major mới | Kiểm tra tương thích dependency, cấu hình và quy ước quan sát thực tế |
| **2.1.x** | Đơn giản hóa cấu trúc observability; tách artifact API/core và chuyển các API quan sát công khai sang package mới | Sửa dependency/import và chạy lại test convention |
| **2.2.x** | Tiếp tục dùng API quan sát công khai trong `org.springframework.modulith.observability`, với các key `module.identifier` / `module.name` | Kiểm tra trace/metric từ phiên bản đang chạy và dashboard đã được migrate |

Hai ví dụ minh họa chính xác sự khác nhau về **tên lớp Java**:

~~~java
// Spring Modulith 1.4.x:
import org.springframework.modulith.observability.support.ModulithContext;
import org.springframework.modulith.observability.support.ModulithObservationConvention;
~~~

~~~java
// Spring Modulith 2.1.x / 2.2.x:
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;
~~~

Ở Javadoc **1.4.x**, enum `ModulithObservations.LowKeys` nằm trong `org.springframework.modulith.observability.support` và có `MODULE_KEY`, `INVOCATION_TYPE`. Trong **2.2.x**, enum ở `org.springframework.modulith.observability` với `MODULE_IDENTIFIER`, `MODULE_NAME` và `INVOCATION_TYPE`. Đây là thay đổi API cần xem khi code tự tham chiếu hằng số enum. Muốn biết chuỗi key đã được exporter sử dụng, hãy kiểm tra span/metric thực tế; đừng chỉ suy luận từ tên enum.

Điểm khác nữa: trong **1.4.x**, nhiều phương thức `getName()`, `getContextualName(...)` và `getLow/HighCardinalityKeyValues(...)` được hiện thực bởi `DefaultModulithObservationConvention`; còn trong **2.2.x**, `ModulithObservationConvention` cung cấp default implementations và có thể dựa vào `ModulithContext`. Vì vậy một custom class tự triển khai interface 1.4 có thể cần được viết lại.

**Cẩn trọng với tên artifact:** tài liệu 1.4 dùng `spring-modulith-observability`, trong khi 2.1/2.2 dùng `spring-modulith-observability-core` và `spring-modulith-observability-api`. Nếu code của ứng dụng trực tiếp import `ModulithObservationConvention`, cần có API artifact trong compile classpath. `spring-modulith-starter-insight` giúp cấu hình runtime theo BOM đã chọn, nhưng khai báo nó ở `runtime` không đủ cho đoạn Java tham chiếu kiểu API lúc biên dịch.

## 4. Lập baseline trước khi thay đổi convention

Một bài kiểm tra có giá trị cần so sánh **cùng luồng nghiệp vụ**, **cùng mức sampling**, **cùng cấu hình exporter** và **cùng vị trí đo** trước/sau nâng cấp.

Giả sử luồng xử lý:

~~~mermaid
sequenceDiagram
    participant H as HTTP client
    participant O as orders
    participant P as payments
    participant E as Event publisher
    H->>O: POST /demo/orders/ORD-1001/pay
    O->>P: PaymentOperations.authorize(...)
    Note over P: API Spring bean của module payments
    P-->>O: authorized
    O->>E: publish OrderPaid
    O-->>H: 200 OK
~~~

Trước khi upgrade, ghi nhận:

1. **Phiên bản:** Spring Boot, Spring Modulith BOM, Micrometer Observation/Tracing, exporter và backend.
2. **Module identity:** ID `orders`/`payments` và `basePackage` từ `/actuator/modulith`.
3. **Tương tác thử:** một HTTP request đã chắc chắn đi qua Spring bean công khai của module `payments`.
4. **Dữ liệu raw:** observation/span name, contextual name, tags được xuất ra, loại `module.invocation-type`, trace ID và thời lượng.
5. **Metric:** danh sách tên meter và label thực tế tại `/actuator/metrics`, `/actuator/prometheus` nếu đã cài registry.
6. **Dashboard:** các query, alert và bộ lọc đang dựa trên key/value/name cũ.

Ví dụ biên bản baseline (các giá trị sau chỉ là minh họa, **không đại diện cho mặc định của bất kỳ bản cụ thể nào**):

~~~json
{
  "scenario": "orders-calls-payments",
  "release": "before-upgrade",
  "moduleId": "payments",
  "observation": {
    "name": "<captured-from-runtime>",
    "contextualName": "<captured-from-runtime>",
    "lowTags": {
      "<module-id-key-in-this-version>": "payments",
      "<invocation-type-key-in-this-version>": "bean"
    },
    "highTags": {
      "<method-key-in-this-version>": "PaymentOperations.authorize"
    }
  },
  "traceExported": true
}
~~~

Để tránh làm bài kiểm tra phụ thuộc vào một exporter, có thể capture observation ngay trong ứng dụng test bằng một `ObservationHandler` hoặc `ObservationFilter` được cấu hình vào `ObservationRegistry`; sau đó mới so sánh dữ liệu ở backend. **Quan sát tại registry** giúp biết convention đang tạo gì, còn **quan sát tại backend** giúp kiểm chứng pipeline xuất và mapping attributes.

## 5. Đối chiếu dependency và cấu hình runtime

Với một dự án dùng Spring Modulith 2.2.x (và Spring Boot tương thích theo bảng hỗ trợ chính thức), `pom.xml` có thể sử dụng một BOM quản lý phiên bản:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>2.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <!-- Kích hoạt Actuator và module instrumentation runtime. -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-insight</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Cần ở compile scope khi viết custom convention. -->
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-observability-api</artifactId>
    </dependency>

    <!-- Spring Boot Actuator/Tracing/exporter được chọn theo bản Boot thực tế. -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

BOM chỉ quản lý version của **Spring Modulith**; Spring Boot và Micrometer vẫn phải được quản lý bằng dependency management tương thích với hệ nền. Nếu trước đó đã có một BOM Spring Modulith trong dự án, cập nhật bản cũ thay vì khai báo hai BOM cạnh tranh.

Không cần đặt đồng thời `spring-modulith-observability-core` một lần nữa nếu starter Insight đã mang nó vào runtime. Chỉ khai báo core trực tiếp khi dự án chủ động sử dụng observability mà không muốn kéo cả starter Insight.

Các lệnh kiểm tra (thực hiện từ dự án Maven của bạn):

~~~bash
mvn dependency:tree -Dincludes=org.springframework.modulith
mvn dependency:tree -Dincludes=io.micrometer
mvn dependency:tree -Dincludes=org.springframework.boot
~~~

Cần kiểm tra:

- Không có bản 1.4 và 2.2 cùng tồn tại trong runtime classpath.
- Không còn import cũ `org.springframework.modulith.observability.support.ModulithObservationConvention` sau khi chuyển lên API mới.
- Custom convention là bean của Spring và không có hai bean `ModulithObservationConvention` cạnh tranh ngoài ý định.
- Instrumentation thật sự được khởi tạo khi ứng dụng chạy, không chỉ xuất hiện trong source hoặc test dependencies.
- Cấu hình sampling/exporter không làm mất trace dùng để đối chiếu.

Ví dụ `application-local.yml` cho phần Actuator/metric của bài kiểm tra:

~~~yaml
spring:
  application:
    name: order-modulith

management:
  endpoints:
    web:
      exposure:
        include: health,info,modulith,metrics,prometheus
  tracing:
    sampling:
      probability: 1.0
~~~

`prometheus` chỉ có endpoint khi ứng dụng có Micrometer Prometheus registry trên classpath. Endpoint Actuator cần được giới hạn quyền truy cập phù hợp; không copy exposure và sampling 100% sang production. Cấu hình OTLP/collector phụ thuộc bản Spring Boot: không suy từ tài liệu Boot 3 rằng các property mới của Boot 4 sẽ tương đương từng ký tự.

## 6. Ví dụ custom convention an toàn ở Spring Modulith 2.2

Mục tiêu ví dụ: thêm tag cố định `module.group=commerce` để phân loại nhóm nghiệp vụ, đồng thời **giữ mọi tên và key/value mặc định** mà Spring Modulith đã tạo.

Tạo `src/main/java/com/example/order/observability/StableModulithObservationConvention.java`:

~~~java
package com.example.order.observability;

import io.micrometer.common.KeyValues;
import org.springframework.modulith.observability.ModulithContext;
import org.springframework.modulith.observability.ModulithObservationConvention;

public final class StableModulithObservationConvention
        implements ModulithObservationConvention {

    @Override
    public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
        // Sử dụng default convention của API 2.2,
        // sau đó bổ sung đúng một tag có cardinality thấp.
        return ModulithObservationConvention.super
                .getLowCardinalityKeyValues(context)
                .and("module.group", "commerce");
    }
}
~~~

Đăng ký bean trong `src/main/java/com/example/order/observability/ObservabilityConfiguration.java`:

~~~java
package com.example.order.observability;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration
public class ObservabilityConfiguration {

    @Bean
    ModulithObservationConvention modulithObservationConvention() {
        return new StableModulithObservationConvention();
    }
}
~~~

Ví dụ cố ý **không override `getName()` hoặc `getContextualName(...)`**, nên tên và contextual name mặc định của API 2.2 được giữ. Cũng không tự loại các low/high keys mặc định. Đây là lựa chọn an toàn khi chỉ muốn thêm một nhãn ổn định.

Nếu bạn thật sự muốn đổi tên span/observation, hãy xác định ai đang sử dụng tên đó. Đổi `getName()` có thể ảnh hưởng observation name và metric; đổi `getContextualName(...)` có thể ảnh hưởng cách span hiển thị; đổi key `module.identifier` có thể làm dashboard/alert mất khả năng nhóm theo module. Việc đổi một key nên được coi như thay đổi contract với người dùng dữ liệu giám sát.

**Lưu ý API theo phiên bản:** ví dụ trên dựa trên các default method của `ModulithObservationConvention` ở Spring Modulith 2.2. Không paste nguyên xi vào 1.4, vì interface 1.4 không cung cấp cùng bộ default method và nằm ở package khác.

### Lỗi custom convention thường gặp

~~~java
// MINH HỌA SAI: làm mất các key/value mặc định của module.
@Override
public KeyValues getLowCardinalityKeyValues(ModulithContext context) {
    return KeyValues.of("module.group", "commerce");
}
~~~

Đoạn sai trên làm mất `module.identifier`, `module.name`, `module.invocation-type` nếu trước đó chúng được default convention cung cấp. Trong trường hợp này, API Spring Modulith vẫn hoạt động nhưng các dashboard truy vấn theo module dễ bị hỏng.

## 7. Kiểm thử contract của custom convention

Bài kiểm thử nhanh dùng JUnit 5, Mockito và AssertJ (có trong bộ Spring Boot test thông dụng). Ta chỉ kiểm tra logic của custom convention, **không giả vờ rằng test unit có thể chứng minh span đã được xuất**.

~~~java
package com.example.order.observability;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import io.micrometer.common.KeyValues;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.observability.ModulithContext;

class StableModulithObservationConventionTest {

    @Test
    void retainsModuleIdentityAndAddsStableGroup() {
        ModulithContext context = mock(ModulithContext.class);

        when(context.getLowCardinalityValues())
            .thenReturn(KeyValues.of("module.identifier", "payments")
                .and("module.name", "Payments")
                .and("module.invocation-type", "bean"));

        var convention = new StableModulithObservationConvention();
        var tags = convention.getLowCardinalityKeyValues(context);

        assertThat(tags).anyMatch(it ->
            it.getKey().equals("module.identifier")
                && it.getValue().equals("payments"));

        assertThat(tags).anyMatch(it ->
            it.getKey().equals("module.name")
                && it.getValue().equals("Payments"));

        assertThat(tags).anyMatch(it ->
            it.getKey().equals("module.group")
                && it.getValue().equals("commerce"));
    }
}
~~~

Test này chứng minh custom convention không xóa key đã nhận từ context giả lập. Muốn bảo vệ toàn bộ contract sau upgrade, cần **integration test** thực thi qua một Spring bean ở API module và capture observation thực sự do Modulith tạo.

Có thể ghi nhận dữ liệu observation trong test bằng `ObservationFilter`. Ví dụ sau là **probe chẩn đoán cho môi trường test**, dành cho API 2.2:

~~~java
package com.example.order.observability;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationFilter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.observability.ModulithContext;

final class ModulithObservationProbe implements ObservationFilter {
    private static final Logger log =
        LoggerFactory.getLogger(ModulithObservationProbe.class);

    @Override
    public Observation.Context map(Observation.Context context) {
        if (context instanceof ModulithContext) {
            log.debug("Modulith observation name={}, contextualName={}, tags={}",
                    context.getName(),
                    context.getContextualName(),
                    context.getAllKeyValues());
        }
        return context;
    }
}
~~~

Đăng ký probe này với `ObservationRegistry` trong **cấu hình test** để xem raw context khi observation kết thúc; không bật log toàn bộ attributes cho ứng dụng production. Với Micrometer, filter chạy trước các handler nhận sự kiện kết thúc observation, nên thông tin in ra phản ánh context tại thời điểm đó. Nếu log không xuất hiện, kiểm tra filter có được đăng ký vào registry thực tế và lời gọi có tạo observation hay không.

Từ probe, đưa vào assertion của test tích hợp các điều kiện cốt lõi:

~~~text
request: orders -> payments.PaymentOperations.authorize()

module entry observation exists = true
module.identifier = payments
module.name = Payments
module.invocation-type = bean
module.group = commerce
module.method = <actual method name>   (if present)
~~~

Dòng cuối phản ánh tag có thể thuộc high cardinality. Không biến `module.method` thành low-cardinality tag chỉ để viết test dễ hơn.

## 8. So sánh dữ liệu trước và sau nâng cấp

Giả sử trước/sau được lấy từ cùng kịch bản, cùng một số lượng request, cùng exporter. Thay vì chỉ so raw JSON byte-for-byte, so các field theo ý nghĩa.

| Thuộc tính | So sánh thế nào? | Mức ưu tiên |
|---|---|---|
| Module ID | `payments` phải được nhận diện đúng ở metadata module | Bắt buộc |
| Tên observation | Có thay đổi có chủ đích? Dashboard có filter theo tên không? | Cao |
| Contextual span name | Chỉ ảnh hưởng hiển thị hay bị dùng như selector? | Trung bình đến cao |
| Low-cardinality keys | Các key dùng trong dashboard/alert phải tồn tại và có giá trị đúng | Bắt buộc |
| High-cardinality keys | Chi tiết chẩn đoán có được giữ, có lộ dữ liệu nhạy cảm không? | Cao |
| Invocation type | Phân biệt lời gọi bean và xử lý event theo convention thực tế | Cao |
| Parent-child trace | Span từ module nằm đúng trace và có quan hệ hợp lý | Cao |
| Event metrics | Tên metric, tags và cardinality có đổi riêng không? | Cao nếu có dashboard sự kiện |
| Exporter/collector | Trace có được ghi và gửi đến backend không? | Bắt buộc để đối chiếu UI |

Ví dụ mẫu diff **minh họa**:

~~~diff
  "logicalModule": "payments"
- "lowKeys": { "module.key": "payments" }
+ "lowKeys": {
+   "module.identifier": "payments",
+   "module.name": "Payments",
+   "module.invocation-type": "bean",
+   "module.group": "commerce"
+ }
  "highKeys": { "module.method": "authorize" }
~~~

Đây là ví dụ về cách biểu diễn khi mapping key thay đổi; **không có nghĩa mọi bản 1.4 đều xuất đúng `module.key` ở mọi backend**. Dùng data snapshot thật để xác nhận chuỗi key cũ. Trình exporter có thể chuyển đổi tên field hoặc bộ lọc; nếu cần điều tra, so đồng thời raw observation và dữ liệu backend.

### Gợi ý lưu bản snapshot có thể review

Lưu những thông tin cần thiết cho contract, không lưu toàn bộ trace ID ngẫu nhiên:

~~~json
{
  "contract": "module-entry/payments",
  "moduleId": "payments",
  "expectedLowKeyNames": [
    "module.identifier",
    "module.name",
    "module.invocation-type",
    "module.group"
  ],
  "expectedHighKeyNames": [
    "module.method"
  ],
  "spanNamePolicy": "review-on-change",
  "traceLinkPolicy": "preserve-parent-when-synchronous"
}
~~~

Ví dụ là tài liệu về **mong đợi của hệ thống**. Snapshot cần được reviewer cập nhật khi quyết định thay đổi hợp lệ, không tự động “accept all” sau mỗi lần nâng cấp.

## 9. Kiểm tra Actuator, metrics và trace backend

### 9.1. Kiểm tra module graph

~~~bash
curl -i http://127.0.0.1:8080/actuator/modulith
~~~

Kỳ vọng `payments` vẫn là một module có base package đúng, phụ thuộc và được phụ thuộc phù hợp. Nếu graph thay đổi ngoài ý muốn vì refactor package hoặc discovery strategy, trace đổi nhãn có thể là **hệ quả của thay đổi mô hình module**, không hẳn do convention.

### 9.2. Kiểm tra meter thực tế

~~~bash
curl -i http://127.0.0.1:8080/actuator/metrics
curl -i http://127.0.0.1:8080/actuator/prometheus
~~~

Chỉ mở `/actuator/prometheus` khi đã có Prometheus registry. Sự kiện không được phát hành sẽ không tạo thêm số liệu cho event publisher. Sau khi thực hiện kịch bản test, tìm các meter tương ứng `module.events.published` cùng tag module thực tế.

Tên series Prometheus và tên label có thể được chuẩn hóa, ví dụ dấu chấm trong key trở thành dấu gạch dưới; suffix của counter cũng phụ thuộc cách registry xuất dữ liệu. Hãy kiểm tra output `/actuator/prometheus` **trước khi viết PromQL**, đừng suy đoán chính xác tên series từ Javadoc.

### 9.3. Kiểm tra span ở backend

Thực hiện một request có dấu mốc rõ (ví dụ mã đơn hàng test), sau đó trong trace backend:

1. Lọc theo đúng service name và khoảng thời gian.
2. Tìm HTTP root span của request.
3. Tìm module entry span ứng với lời gọi API của `payments`.
4. Mở raw attributes: đối chiếu `module.identifier`, `module.name`, `module.invocation-type` và `module.group`; tìm `module.method` ở mức trace nếu có.
5. Kiểm tra parent/child và duration; nếu có listener chạy trên executor khác, kiểm tra propagation riêng.
6. Đối chiếu cùng bản build và BOM, tránh so instance cũ và mới đang chạy song song.

**Một trace vắng mặt trong UI không chứng minh convention bị lỗi.** Trước khi kết luận, kiểm tra sampling, tracer bridge, exporter, collector, ingestion filters và quyền tìm kiếm trong backend.

## 10. Hướng dẫn sửa khi contract đổi

Chọn cách sửa dựa trên **người sử dụng dữ liệu**:

| Thay đổi phát hiện | Hành động đề xuất |
|---|---|
| Đổi tên package Java của `ModulithObservationConvention` | Cập nhật imports và compile dependency theo phiên bản |
| Enum/key có tên mới | Dùng API mới; xác minh raw key string ở runtime; cập nhật test và query |
| Default observation name thay đổi | Cân nhắc giữ tên cũ bằng custom convention nếu đây là contract bắt buộc; nếu không, migrate dashboard |
| `module.identifier` biến mất vì custom convention trả về KeyValues mới | Ủy quyền default convention rồi chỉ bổ sung tag cần thiết |
| Label mới có cardinality cao | Xóa khỏi low keys, chuyển sang high keys nếu thật sự cần trong trace |
| Event metric đổi nhưng module entry span vẫn đúng | Kiểm tra `ModulithEventMetricsCustomizer`, meter name/tags riêng |
| Có span tại local registry nhưng không thấy backend | Kiểm tra sampling/exporter/collector và processor lọc attribute |
| Module ID đổi khi refactor package | Khai báo ID logic tường minh, kiểm tra `ApplicationModules.verify()` và Actuator |
| Span listener có trace khác sau khi thêm async | Kiểm tra context propagation qua executor/message broker |

### Trường hợp cần tương thích tạm thời

Nếu dashboard cũ đang đọc một tag tên cũ, nên lập kế hoạch có thời hạn:

1. Thống kê các dashboard, alert và consumer đang dùng key cũ.
2. Migrate truy vấn sang key mới khi có thể; có khoảng thời gian so sánh song song.
3. Nếu hệ thống thật sự cần một alias, thêm **alias có cardinality thấp** bằng custom convention/filter và đánh dấu thời hạn xóa.
4. Kiểm tra chi phí cardinality và dữ liệu bị lộ trước khi phát hành alias.
5. Xóa alias và query cũ khi mọi consumer đã chuyển.

Không lấy tên package, tên method chi tiết hoặc ID nghiệp vụ làm module identifier. Module ID nên biểu diễn ranh giới logic ổn định, có thể giữ nguyên khi code refactor mà trách nhiệm module không đổi.

## 11. Checklist nghiệm thu nâng cấp

Đánh dấu thành công khi:

- [ ] Có phiên bản trước/sau từ BOM và dependency tree; không trộn artifact của nhiều nhánh Modulith.
- [ ] Code custom convention compile với package/API của phiên bản mục tiêu.
- [ ] `ApplicationModules.verify()` và `/actuator/modulith` giữ ranh giới module theo thiết kế.
- [ ] Kịch bản HTTP → API Spring bean của module đích được thực thi thật.
- [ ] Module entry observation tồn tại trong raw context, với tên và low/high keys được chấp thuận.
- [ ] `module.identifier`, `module.name` và `module.invocation-type` có giá trị đúng theo baseline đã cập nhật.
- [ ] Tag bổ sung có cardinality thấp, không chứa thông tin người dùng hoặc giá trị thay đổi theo từng request.
- [ ] Event metric và module entry span được kiểm tra riêng; không dùng tín hiệu này thay bằng chứng cho tín hiệu khác.
- [ ] Trace backend nhận span và giữ context qua các bước async (nếu có).
- [ ] Dashboard, alert, saved search và các test snapshot đã được rà soát; thay đổi có chủ đích được review.

**Bài tập:** Dự án đang dùng Spring Modulith 1.4 với custom convention khai báo trong `org.springframework.modulith.observability.support`. Nhóm muốn nâng lên 2.2 và thêm tag `module.group=commerce`. Hãy liệt kê thay đổi dependency/import, viết convention chỉ mở rộng các default keys, rồi trình bày bộ bằng chứng cần có để chứng minh dashboard theo module vẫn hoạt động.

**Câu hỏi tự đánh giá:**

1. Vì sao `/actuator/modulith` hiển thị đúng ba module nhưng dashboard vẫn có thể mất module entry span?
2. Khác biệt giữa `getName()` và `getContextualName(...)` ảnh hưởng bộ phận nào của hệ quan sát?
3. Vì sao không nên thêm `orderId` vào `getLowCardinalityKeyValues(...)`?
4. Khi có span ở registry nhưng không có ở backend, bước kiểm tra tiếp theo là gì?
5. Vì sao kiểm thử unit convention cần bổ sung integration test với lời gọi đi qua Spring bean công khai của module?

## 12. Tài liệu tham khảo theo phiên bản

- [Spring Modulith 1.4 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/1.4/production-ready.html): cơ chế quan sát module của nhánh 1.4 và artifact `spring-modulith-observability`.
- [Spring Modulith 2.2 — Production-ready Features](https://docs.spring.io/spring-modulith/reference/2.2/production-ready.html): module entry spans, tags, event metrics, convention và artifact observability mới.
- [Spring Modulith 1.4 — ModulithObservationConvention Javadoc](https://docs.spring.io/spring-modulith/docs/1.4.x/api/org/springframework/modulith/observability/support/ModulithObservationConvention.html): package/method của nhánh 1.4.
- [Spring Modulith 2.2 — ModulithObservationConvention Javadoc](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservationConvention.html): public API và các default methods ở nhánh 2.2 tại thời điểm biên soạn.
- [Spring Modulith 2.2 — ModulithObservations.LowKeys](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.LowKeys.html): định nghĩa nhóm key low cardinality.
- [Spring Modulith 2.2 — ModulithObservations.HighKeys](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.HighKeys.html): định nghĩa nhóm key high cardinality.
- [Spring Modulith 1.4 GA release notes](https://spring.io/blog/2025/05/28/spring-modulith-1-4-1-3-6-and-1-2-13-released/): thay đổi sang Micrometer Observations API.
- [Spring Modulith 2.1 GA release notes](https://spring.io/blog/2026/06/11/spring-modulith-2-1-ga-2-0-7-and-1-4-12-released/): đơn giản hóa hạ tầng observability.
- [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): convention, registry, handler và filter.

> **Ghi nhớ:** Khi nâng Spring Modulith, hãy coi observation convention như một **hợp đồng của dữ liệu giám sát**. Đối chiếu API theo phiên bản, giữ các tag định danh module ổn định, kiểm tra raw observation rồi mới kết luận về dữ liệu ở dashboard.
