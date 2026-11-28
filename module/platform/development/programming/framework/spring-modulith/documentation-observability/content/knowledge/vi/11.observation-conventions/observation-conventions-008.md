# Giữ tên observation ổn định khi nâng cấp

## 1. Vì sao tên observation là một hợp đồng vận hành?

Trong một ứng dụng Spring Boot sử dụng **Spring Modulith**, kiến trúc được chia thành các application module như **order**, **payment** và **notification**. Tài liệu module graph và Actuator cho biết các module được xác định ra sao; Micrometer Observation, metrics và tracing cho thấy chúng đã tương tác như thế nào khi chương trình chạy. Muốn đối chiếu dữ liệu giữa các bản phát hành, trước hết phải biết **đang đo cùng một hoạt động với cùng một tên và cùng một bộ nhãn hay không**.

Bài thuộc chương **Observation convention** của **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Phạm vi module học là tài liệu hóa ranh giới application module và quan sát tương tác giữa các phần trong Spring Boot, bao gồm module graph, Actuator, event metrics, tracing và context propagation. Chủ đề riêng ở đây là **giữ tên observation ổn định qua nâng cấp framework, refactor code và thay đổi kiến trúc triển khai**.

Giả sử bản v1 phát metric `shop.order.confirm`, còn sau nâng cấp một thư viện đổi tên thành `shop.orders.confirmation`. Nếu không chuẩn bị, dashboard có thể vẽ hai chuỗi thời gian tách rời; cảnh báo truy vấn tên cũ trở nên im lặng; các truy vấn trace theo operation cũng có thể không tìm thấy dữ liệu mới. **Nghiệp vụ không nhất thiết đã hỏng, nhưng hệ thống giám sát có thể không còn nhìn thấy nó.**

Học xong, bạn cần có thể:

1. Phân biệt **technical observation name**, **contextual name**, tên meter xuất ra backend và attributes/tags.
2. Dùng **ObservationConvention** để định nghĩa tên ổn định cho instrumentation do ứng dụng sở hữu.
3. Biết lựa chọn **ModulithObservationConvention** khi cần giữ naming contract của module observations.
4. Kiểm tra sự thay đổi tên/tags trước và sau nâng cấp bằng contract tests và smoke tests.
5. Lập kế hoạch di chuyển dashboard, alert, trace search, service name và các nhãn khi bắt buộc đổi hợp đồng telemetry.

## 2. Một thay đổi tên tác động tới những gì?

Một Observation có thể được đưa đến nhiều hệ thống:

~~~mermaid
flowchart LR
    Code["Business code / Spring Modulith instrumentation"] --> Obs["Micrometer Observation"]
    Convention["ObservationConvention"] --> Obs
    Obs --> Meter["Metrics ObservationHandler"]
    Obs --> Tracing["Tracing ObservationHandler"]
    Meter --> Registry["MeterRegistry"]
    Registry --> Metrics["Actuator / Prometheus / Metrics backend"]
    Tracing --> Export["Zipkin hoặc OTLP exporter"]
    Export --> Trace["Trace backend"]
    Metrics --> Dashboard["Dashboard + alert"]
    Trace --> Query["Trace search + investigation"]
~~~

Convention là nơi đặt **quy tắc tên và KeyValues**, còn ObservationHandler/MeterRegistry/exporter quyết định cách dữ liệu được ghi nhận. Một thay đổi có thể ảnh hưởng tới:

| Bề mặt | Ví dụ trước → sau | Tác động có thể gặp |
| --- | --- | --- |
| **Technical name** | `shop.order.confirm` → `shop.orders.confirmation` | Metric series mới; truy vấn tên cũ ngừng có điểm dữ liệu mới. |
| **Contextual name** | `confirm order` → `order confirmation` | Tên span hiển thị và điều kiện tìm trace có thể khác; technical metric name có thể giữ nguyên. |
| **Low-cardinality keys** | `module=order` → `module=orders` | Dashboard group-by và alerts theo tag tách thành hai nhóm. |
| **High-cardinality keys** | `order.ref` → `order.id` | Truy vấn trace theo attribute cũ có thể không còn kết quả. |
| **Service/resource name** | `shop-modulith` → `shop-core` | Trace/metric backend có thể xem đây là một service mới. |
| **Export format** | Micrometer logical name → tên series trong Prometheus | Có thể được chuẩn hóa ký tự, thêm hậu tố đơn vị hoặc thay đổi cách ánh xạ. |

**Giữ technical name ổn định chưa đủ nếu toàn bộ dashboard cũng phụ thuộc vào key/tag names.** Nên coi mỗi observation quan trọng là một **hợp đồng có tên, semantic meaning, tags, cardinality và hướng dẫn sử dụng**.

## 3. Phân biệt technical name và contextual name

Micrometer `ObservationConvention<T extends Observation.Context>` cho phép tùy chỉnh hai khái niệm dễ bị nhầm:

- **getName()** cung cấp **technical name** của Observation. Đây thường là cơ sở đặt tên cho meter do metrics handler tạo ra và là định danh logic để enable/disable observation theo tên.
- **getContextualName(context)** cung cấp tên dễ đọc trong ngữ cảnh thực thi, được tracing dùng để đặt tên span trong nhiều instrumentation.
- **getLowCardinalityKeyValues(context)** cung cấp nhãn có số giá trị hữu hạn, dùng cho metrics và traces qua handler phù hợp.
- **getHighCardinalityKeyValues(context)** cung cấp thuộc tính có nhiều giá trị, thường dành cho tracing; không nên đưa vào metric label.
- **supportsContext(context)** xác định loại Observation.Context mà convention hỗ trợ.

**Tên technical** nên có tính ổn định cao, ví dụ `shop.order.confirm`, không chứa ID đơn hàng, timestamp, tên instance hoặc version build. **Contextual name** có thể giàu ngữ nghĩa hơn, nhưng nếu hệ thống truy vấn theo span name thì nó cũng là một phần hợp đồng vận hành.

| Đặc điểm | Technical name | Contextual name |
| --- | --- | --- |
| Đối tượng sử dụng phổ biến | Meter name, observation enable/predicate, bảng metric. | Span name dễ đọc trong trace viewer. |
| Mức độ biến thiên | Nên rất thấp, ổn định qua các release. | Cũng nên ổn định nếu được dùng trong search/alert. |
| Ví dụ nên dùng | `shop.order.confirm` | `confirm order` |
| Ví dụ nên tránh | `shop.order.3f72...` | `confirm order 3f72...` |
| Khi thay đổi | Cần cập nhật metric queries/alerts và migration. | Cần kiểm tra trace queries/span filters và tài liệu điều tra. |

**Lưu ý:** Cách tên được trình bày ở backend tùy instrumentation, handler và exporter. Prometheus có thể biến đổi cách biểu diễn meter name, ví dụ tạo các time series hậu tố đơn vị. Đừng giả định chuỗi hiển thị trong PromQL luôn giống nguyên văn `getName()`.

## 4. Thiết kế naming contract ổn định

Một hợp đồng cho hoạt động xác nhận đơn hàng có thể ghi như sau:

| Trường | Giá trị kỳ vọng | Quy tắc |
| --- | --- | --- |
| Technical name | `shop.order.confirm` | Giữ nguyên khi thay implementation/repository hoặc tách method nội bộ. |
| Contextual name | `confirm order` | Không gắn ID của từng đơn. |
| Low-cardinality key | `business.module=order` | Danh sách module hữu hạn, do kiến trúc quy định. |
| Low-cardinality key | `operation=confirm` | Từ vựng nhất quán giữa các release. |
| High-cardinality key | `correlation.id` nếu cần | Không dùng cho metric; không lưu giá trị nhạy cảm. |
| Đơn vị đo | Duration | Ghi rõ đơn vị và cách backend chuẩn hóa. |
| Ngữ nghĩa hoàn tất | Method xử lý xác nhận trả về/throw | Phân biệt với thời gian chờ trong queue hoặc gửi mail ở downstream. |
| Chủ sở hữu | Module order | Có người chịu trách nhiệm đánh giá mọi đổi tên. |

Chọn tên theo **khả năng kinh doanh được đo** thay vì tên lớp/method có thể đổi khi refactor:

~~~text
Nên:
  shop.order.confirm
  shop.payment.authorize
  shop.notification.request

Tránh:
  ShopOrderServiceV2.confirmInternal
  shop.order.2026-11-27.confirm
  shop.order.<orderId>.confirm
  shop.order.confirm.<deploymentId>
~~~

Đặt nghĩa rõ ràng: `shop.notification.request` có thể chỉ đo thời gian **ghi yêu cầu thông báo**, không chứng minh email đã đến người nhận. Nếu ngữ nghĩa thay đổi lớn (từ “ghi tác vụ” thành “gửi email và chờ kết quả”), cân nhắc tên mới **có chủ đích** và migration thay vì giữ tên cũ nhưng làm dữ liệu không còn so sánh được.

## 5. ObservationConvention hoạt động thế nào?

Micrometer hỗ trợ convention gắn trực tiếp tại instrumentation, convention đăng ký toàn cục và convention mặc định do instrumentation cung cấp. Với lời gọi hỗ trợ cả **custom**, **global** và **default** convention, thứ tự ưu tiên được tài liệu hóa là:

1. **Custom convention được truyền trực tiếp** cho instrumentation, nếu có.
2. **GlobalObservationConvention** đã đăng ký trên ObservationRegistry và **supportsContext** cho context đó.
3. **Default convention** được instrumentation cung cấp làm fallback.

~~~mermaid
flowchart TD
    I["Instrumentation tạo Observation"] --> C{"Có custom convention?"}
    C -->|Có| SelectCustom["Dùng custom"]
    C -->|Không| G{"Có global convention hỗ trợ Context?"}
    G -->|Có| SelectGlobal["Dùng global phù hợp"]
    G -->|Không| SelectDefault["Dùng default convention"]
    SelectCustom --> Name["Tên + KeyValues cho Observation"]
    SelectGlobal --> Name
    SelectDefault --> Name
~~~

Hệ quả thực tế:

- Một **global convention** không chắc thắng được convention đã được truyền trực tiếp tại nơi tạo Observation.
- Một convention chỉ hỗ trợ **OrderObservationContext** sẽ không tự đổi tên HTTP observation hoặc Spring Modulith module observations có Context khác.
- Khi viết custom convention cho instrumentation do thư viện bên ngoài sở hữu, nên dùng **extension point chính thức** của thư viện thay vì can thiệp vào registry bằng kiểm tra tên chuỗi thiếu an toàn.
- Nếu có nhiều global conventions cùng hỗ trợ một Context, phải xem thứ tự đăng ký và quy tắc chọn của phiên bản Micrometer; nên tránh hai convention cạnh tranh cho cùng một loại Observation.

**ObservationFilter** là công cụ bổ sung/chỉnh Context ở vòng đời Observation; nó không phải lựa chọn ưu tiên để “đóng băng” tên một instrumentation có convention riêng. **ObservationPredicate** có thể chặn ghi nhận; nó cũng không phải công cụ đổi tên.

## 6. Ví dụ Java: convention ổn định cho một hoạt động nghiệp vụ

Ta định nghĩa một Context riêng và một Convention riêng cho hoạt động **xác nhận đơn**. Đoạn mã sau dùng các API Micrometer Observation, không phụ thuộc một tên phương thức nội bộ có thể bị đổi trong tương lai.

### 6.1. Context riêng

~~~java
package com.example.shop.observability;

import io.micrometer.observation.Observation;

public final class OrderConfirmationContext extends Observation.Context {
    // Bổ sung dữ liệu nghiệp vụ an toàn nếu convention cần phân nhóm.
    // Không giữ token hoặc nội dung nhạy cảm chỉ để xuất telemetry.
}
~~~

### 6.2. Convention trả tên cố định

~~~java
package com.example.shop.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationConvention;

public class StableOrderConfirmationConvention
        implements ObservationConvention<OrderConfirmationContext> {

    public static final String OBSERVATION_NAME = "shop.order.confirm";

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof OrderConfirmationContext;
    }

    @Override
    public String getName() {
        return OBSERVATION_NAME;
    }

    @Override
    public String getContextualName(OrderConfirmationContext context) {
        return "confirm order";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(
            OrderConfirmationContext context) {
        return KeyValues.of(
                KeyValue.of("business.module", "order"),
                KeyValue.of("operation", "confirm"));
    }
}
~~~

**Vì sao thiết kế này ổn định?** Khi đổi tên Java class `OrderConfirmationService` thành `OrderWorkflow`, khi chuyển xử lý sang repository khác hoặc nâng cấp Spring Boot, `getName()` vẫn trả `shop.order.confirm`. KeyValues được khai báo bởi hợp đồng nghiệp vụ thay vì được suy từ tên class hay instance.

### 6.3. Dùng convention trong service

~~~java
package com.example.shop.order;

import com.example.shop.observability.OrderConfirmationContext;
import com.example.shop.observability.StableOrderConfirmationConvention;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderConfirmationService {

    private final ObservationRegistry registry;

    OrderConfirmationService(ObservationRegistry registry) {
        this.registry = registry;
    }

    void confirmOrder() {
        var convention = new StableOrderConfirmationConvention();

        Observation.createNotStarted(
                convention,
                OrderConfirmationContext::new,
                registry
        ).observe(this::performConfirmation);
    }

    private void performConfirmation() {
        // Business logic thực tế nằm ở đây.
    }
}
~~~

Ở đây `Observation.createNotStarted(convention, contextSupplier, registry)` dùng chính convention được truyền vào để cung cấp tên và KeyValues. `observe(...)` quản lý start/scope, ghi lỗi nếu có exception phù hợp và stop khi khối xử lý kết thúc. Tùy handler được gắn trên registry, một Observation có thể sinh metric, trace span hoặc cả hai.

**Điều kiện cần:** ứng dụng phải dùng `ObservationRegistry` có các handlers phù hợp. Trong Spring Boot, ưu tiên inject registry do auto-configuration quản lý. Nếu tự tạo một registry khác mà không có handlers, Observation vẫn chạy về mặt mã nhưng có thể không xuất telemetry.

### 6.4. Khi nào nên dùng GlobalObservationConvention?

Nếu nhiều chỗ của ứng dụng dùng chung **OrderConfirmationContext** và bạn kiểm soát chúng, có thể đăng ký `GlobalObservationConvention<OrderConfirmationContext>` trên registry, để instrumentation không phải truyền custom convention ở từng lời gọi. Nhưng nếu code luôn truyền custom convention trực tiếp, custom có ưu tiên cao hơn global.

~~~java
package com.example.shop.observability;

import io.micrometer.observation.GlobalObservationConvention;

public final class GlobalOrderConfirmationConvention
        extends StableOrderConfirmationConvention
        implements GlobalObservationConvention<OrderConfirmationContext> {
}
~~~

**Ghi chú về ví dụ:** để minh họa khả năng kế thừa, `StableOrderConfirmationConvention` được khai báo không có `final`. Khi dùng cách này, đăng ký `GlobalOrderConfirmationConvention` thành bean GlobalObservationConvention; hoặc có thể cho class gốc implement trực tiếp `GlobalObservationConvention<OrderConfirmationContext>`. Chỉ cần chọn **một** cách đăng ký phù hợp và biết instrumentation đang chọn convention nào.

## 7. Spring Modulith có convention riêng

Đối với module spans, Spring Modulith cung cấp interface **ModulithObservationConvention** (trong package `org.springframework.modulith.observability` ở các dòng hiện hành), kế thừa `ObservationConvention<ModulithContext>`. Tài liệu Spring Modulith cho phép **cung cấp bean ModulithObservationConvention** để tùy chỉnh các observation do Modulith tạo.

Đây là điểm mở rộng phù hợp nếu mục tiêu là **ổn định tên Observation của tương tác module**, thay vì cố thay đổi tên qua filter toàn cục:

~~~java
package com.example.shop.observability;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithObservationConvention;

@Configuration(proxyBeanMethods = false)
class StableModulithNamesConfiguration {

    @Bean
    ModulithObservationConvention stableModuleObservationName() {
        return new ModulithObservationConvention() {
            @Override
            public String getName() {
                return "module.invocations";
            }
        };
    }
}
~~~

Theo API Spring Modulith hiện hành, **ModulithContext.DEFAULT_CONVENTION_NAME** có giá trị **module.invocations**. Trong ví dụ, chuỗi được viết rõ theo hợp đồng muốn duy trì. Không dùng code này để khẳng định mọi phiên bản Spring Modulith đều luôn trả cùng tên; phải kiểm tra bản đang chạy và thực sự có tạo Observation tương ứng.

**Cảnh báo cần thiết:** convention trên chỉ cố định **technical name**. `getContextualName(ModulithContext)`, các tags và cách instrumentation xác định module vẫn có thể khác sau nâng cấp. Nếu trace search phụ thuộc span name, cần kiểm tra thêm contextual name; nếu alert phụ thuộc `module.identifier`, cần kiểm tra các attribute đó. Không xóa metadata module mặc định chỉ để đổi tên.

### Module Entry Span và metric công bố sự kiện là hai loại dữ liệu

Spring Modulith mô tả các thuộc tính module span:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| **module.identifier** | Mã ứng dụng module, ví dụ `order`. |
| **module.name** | Tên hiển thị module. |
| **module.method** | Phương thức ở điểm vào module. |
| **module.invocation-type** | Kiểu lời gọi, chẳng hạn **bean** hoặc **event listener**. |

Ngoài module spans, Spring Modulith còn ghi nhận các counter công bố sự kiện, ví dụ **module.events.published** và các counter theo module/event type. Những counter đó có thể được tạo trực tiếp qua `MeterRegistry` và có extension point riêng, không mặc nhiên chịu tác động khi thay đổi tên module Observation.

**Không nhầm**:

- **module.invocations** — technical name của module entry observation theo convention ở phiên bản tham chiếu.
- **module.events.published** — metric về số lần phát domain event.
- **/actuator/modulith** — endpoint metadata kiến trúc các application module.

Ba tên phục vụ ba mục đích khác nhau. Giữ ổn định một tên không tự giữ ổn định hai tên còn lại.

## 8. Convention, filter, registry customizer và exporter: dùng đúng tầng

| Nhu cầu | Điểm mở rộng nên ưu tiên | Giới hạn |
| --- | --- | --- |
| Giữ tên Observation do ứng dụng tự tạo | **ObservationConvention** được gắn ngay instrumentation. | Phải bảo đảm instrumentation thực sự dùng convention. |
| Giữ tên module entry observation | Bean **ModulithObservationConvention** của Spring Modulith. | Cần dependency/version có extension point này. |
| Chuẩn hóa metadata một loại instrumentation | Convention chuyên biệt của loại Context. | Không áp dụng nếu Context không phù hợp hoặc custom convention khác thắng. |
| Bổ sung nhãn chung vào Context | **ObservationFilter** hoặc cấu hình Boot observations. | Không nên coi là công cụ duy nhất bảo đảm technical name. |
| Đăng ký nhiều thành phần lên registry | **ObservationRegistryCustomizer** của Spring Boot. | Không tự tạo spans hoặc meters; package import khác theo Boot 3.x/4.x. |
| Đổi nhãn của meter được tạo trực tiếp | **MeterRegistryCustomizer/MeterFilter** hoặc extension của nhà phát metrics. | Không đổi cùng lúc trace naming. |
| Đổi tên metric chỉ ở backend | Recording rule/alias tùy hệ thống. | Là lớp tương thích truy vấn, không làm tên upstream ổn định. |
| Giữ sự liên tục trace khi async | Tracing/context propagation + correlation ID. | Không liên quan trực tiếp tới naming convention. |

Một chiến lược an toàn là **đặt tên ở nguồn instrumentation** nếu bạn sở hữu mã tạo Observation. Với instrumentation của framework, ưu tiên extension point được tài liệu hóa; nếu framework không cung cấp, dùng giải pháp tương thích ở backend như lớp chuyển tiếp tạm thời và lên kế hoạch nâng cấp truy vấn, thay vì dùng reflection hoặc can thiệp nội bộ dễ vỡ.

## 9. Các rủi ro khi nâng Spring Boot, Micrometer và Spring Modulith

Nâng cấp có thể thay đổi hành vi observability mà không thay đổi API nghiệp vụ:

1. **Thay đổi default convention**: technical name, contextual name, KeyValues hoặc tag cardinality có thể khác.
2. **Thay đổi lớp Context**: global convention cũ không còn match qua `supportsContext`.
3. **Thay đổi điểm instrumentation**: một method trước đây được quan sát, sau refactor không còn đi qua proxy/aspect.
4. **Thay đổi exporter hoặc registry**: metric name được chuẩn hóa khác, span có thể nằm ở backend khác.
5. **Thay đổi service name/resource attributes**: trace backend chia dữ liệu sang service khác.
6. **Thay đổi sampling**: span mới không xuất hiện, dễ bị nhầm với đổi tên hoặc hỏng instrumentation.
7. **Thay đổi asynchronous execution**: trace context có thể đứt tại executor dù naming convention vẫn ổn định.

Ví dụ nâng **Spring Boot 3.x → 4.x**, bên cạnh thay đổi starter/exporter, package `ObservationRegistryCustomizer` cũng khác. Các project cần rà soát cả API, version và output runtime; **biên dịch thành công không chứng minh dashboard vẫn đúng**.

### Ma trận tương thích nên lập trước khi nâng cấp

| Hạng mục | Baseline bản cũ | Kỳ vọng bản mới | Bằng chứng |
| --- | --- | --- | --- |
| Technical name đơn hàng | `shop.order.confirm` | Giữ nguyên | Contract test + Actuator metrics. |
| Contextual span name | `confirm order` | Giữ nguyên hoặc thay đổi có kế hoạch | Trace backend. |
| Module observation | `module.invocations` | Giữ tên theo convention đã chọn | Tracing/module span query. |
| Module tags | `module.identifier`, `module.invocation-type` | Giữ giá trị có ý nghĩa | Span attributes. |
| Event counter | `module.events.published` | Kiểm tra độc lập | Actuator metrics hoặc registry output. |
| Service name | `shop-modulith` | Giữ nguyên nếu là cùng service | Trace resource/service filter. |
| Alert query | Tên, labels, thresholds của bản cũ | Hoạt động khi bản mới phát dữ liệu | Staging dashboard/alert test. |

Trong bản báo cáo so sánh, nên giữ **thời gian, version framework, version ứng dụng, profile, registry/exporter và sampling**. Nếu hai môi trường khác nhau về sampling hoặc backend, việc so sánh số lượng span không còn tương đương.

## 10. Ghi baseline trước khi thay đổi

Thực hiện trên bản hiện tại trong môi trường kiểm thử hoặc staging:

1. Gửi một tập request nghiệp vụ có thể lặp lại: tạo đơn, xác nhận thanh toán, công bố sự kiện.
2. Ghi lại logical names tại endpoint `/actuator/metrics` và metrics được xuất ra registry/backend.
3. Mở trace mẫu, ghi tên span và những attributes ổn định.
4. Xác định các dashboard, cảnh báo, trace searches và báo cáo đang phụ thuộc vào tên hoặc label.
5. Ghi rõ những thành phần phát metric trực tiếp qua MeterRegistry (ví dụ event counters) để không gộp chúng vào nhóm Observation conventions.

Ví dụ lệnh kiểm tra **sau khi endpoint đã được expose và có quyền truy cập**:

~~~bash
# Danh sách logical names nhìn từ Spring Boot Actuator.
curl -fsS http://localhost:8080/actuator/metrics

# Chỉ xuất hiện sau khi instrumentation đã ghi dữ liệu.
curl -fsS http://localhost:8080/actuator/metrics/shop.order.confirm

# Kiểm tra riêng event counter của Spring Modulith.
curl -fsS http://localhost:8080/actuator/metrics/module.events.published
~~~

Lưu ý những lệnh này chỉ minh họa trên local. Với môi trường thật, cần đúng management port/base path và authentication. Endpoint `/actuator/metrics` không phải nơi truy vấn tracing spans; muốn kiểm tra tên span cần backend tracing như Zipkin/Tempo/Jaeger hoặc pipeline tương đương.

## 11. Kiểm thử hợp đồng tên bằng JUnit

Với convention do ứng dụng sở hữu, có thể viết một unit test nhỏ nhằm bảo vệ hợp đồng mà dashboard và alert phụ thuộc:

~~~java
package com.example.shop.observability;

import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class OrderConfirmationConventionTest {

    private final StableOrderConfirmationConvention convention =
            new StableOrderConfirmationConvention();

    @Test
    void keepsTechnicalNameStable() {
        assertEquals("shop.order.confirm", convention.getName());
    }

    @Test
    void keepsContextualNameStable() {
        assertEquals(
                "confirm order",
                convention.getContextualName(new OrderConfirmationContext()));
    }

    @Test
    void onlySupportsItsOwnContext() {
        assertTrue(convention.supportsContext(
                new OrderConfirmationContext()));
        assertFalse(convention.supportsContext(
                new io.micrometer.observation.Observation.Context()));
    }
}
~~~

Test này bảo vệ **quy tắc đặt tên và phân loại Context**, không phải một integration test xác nhận metric đã được xuất. Nếu đổi implementation nhưng test vẫn pass, convention vẫn giữ contract tên. Tuy nhiên, nếu instrumentation không gọi convention ấy, test đơn thuần vẫn pass dù hệ thống thực tế không phát metric.

### Cần thêm integration test nào?

Tạo một Spring Boot application context với registry do Boot quản lý, kích hoạt instrumentation thực tế, rồi kiểm tra:

- `shop.order.confirm` xuất hiện sau khi chạy nghiệp vụ, cùng low-cardinality keys dự kiến.
- Không xuất hiện một tên mới ngoài ý muốn chỉ do thay class/method nội bộ.
- Module span có `module.identifier` và những thuộc tính truy vấn cần thiết.
- Một listener bất đồng bộ vẫn tạo telemetry khi có đúng tracing handler và sampling.
- Kết quả từ exporter/backend khớp với contract đang được dashboard sử dụng.

Nếu dùng SimpleMeterRegistry hoặc test handlers, hãy gắn handlers phù hợp; `ObservationRegistry.create()` đơn thuần không tự sản xuất metrics nếu chưa có handler. Khi test integration, phải dùng **cùng convention/registry/executor** như production, không chỉ tạo một mô hình kiểm thử khác bản chạy thật.

## 12. Quy trình nâng cấp có thể kiểm chứng

~~~mermaid
flowchart TD
    B["Baseline: tên, tags, queries"] --> C["Khóa contract bằng convention"]
    C --> T["Unit test + integration test"]
    T --> Stage["Chạy bản mới ở staging"]
    Stage --> Compare{"Tên và ngữ nghĩa tương thích?"}
    Compare -->|Có| Deploy["Triển khai theo từng đợt"]
    Compare -->|Không| Plan["Chọn giữ tên cũ hoặc migration có kế hoạch"]
    Plan --> Query["Dashboard/alert truy vấn cả tên cũ và mới"]
    Query --> Deploy
    Deploy --> Watch["Theo dõi coverage, error, metric/trace pipeline"]
    Watch --> Cleanup["Gỡ alias cũ sau thời gian lưu trữ phù hợp"]
~~~

### Pha 1 — Chuẩn bị

Ghi baseline và xác định chủ sở hữu của từng Observation quan trọng. Nếu tên hiện tại mang ý nghĩa chính xác, **ưu tiên giữ nguyên tên** bằng convention chuyên biệt. Kiểm tra các tag và service name sẽ tiếp tục có cùng ngữ nghĩa.

### Pha 2 — Cài đặt và kiểm thử

Viết hoặc sửa custom convention, thêm contract test. Nâng framework/dependency trong một nhánh thay đổi có thể review. Kiểm thử luồng đồng bộ lẫn listener bất đồng bộ: **không có span** có thể do sampling, context propagation hoặc exporter chứ không phải convention.

### Pha 3 — Triển khai đồng tồn tại

Khi bắt buộc đổi tên, cập nhật dashboard/alert để đọc cả hai series trong thời gian rollout và trong khoảng cần đối chiếu dữ liệu lịch sử. Tùy backend, có thể dùng **recording rule**, biểu thức truy vấn kết hợp, hoặc lớp tương thích trên hệ thống quan sát. Không giả định mọi backend có tính năng đổi tên identical.

### Pha 4 — Xác nhận và dọn dẹp

Kiểm tra traffic, error rate, latency distributions, trace search theo service và module, và độ đầy đủ của dữ liệu. Khi bản mới đã ổn định, hết giai đoạn dual query/retention và người dùng dashboard đã chuyển, mới gỡ alias/truy vấn cũ.

### Tại sao không nên phát hai metrics trùng nhau lâu dài?

Việc cố ghi cùng một phép đo dưới hai tên có thể làm tăng cardinality, lưu trữ, chi phí ingest và gây đếm đôi khi ai đó sum cả hai series. **Dual-write** chỉ nên là biện pháp chuyển tiếp được đo lường và có thời điểm kết thúc, nếu backend không hỗ trợ lớp truy vấn tương thích phù hợp.

## 13. Phân biệt lỗi naming với lỗi telemetry

| Triệu chứng | Giả thuyết | Cách kiểm tra |
| --- | --- | --- |
| Metric cũ không tăng sau nâng cấp | Technical name đổi hoặc instrumentation không chạy. | Xem `/actuator/metrics`, log nghiệp vụ, loại Context/convention. |
| Trace không tìm thấy theo span name cũ | Contextual name đổi hoặc span không được export/sampled. | Tra service/time range; kiểm tra tracer/exporter và các attributes khác. |
| Metric cùng tên nhưng dashboard tách hai dòng | Low-cardinality tag đổi tên/giá trị. | So bộ nhãn cũ và mới, template dashboard. |
| Các spans chuyển sang service khác | `spring.application.name` hay resource/service.name đổi. | Kiểm tra cấu hình tài nguyên và exporter. |
| Global convention không có hiệu lực | Context không match hoặc instrumentation truyền custom convention ưu tiên hơn. | Kiểm tra `supportsContext`, thứ tự chọn convention và registry thật. |
| Đã đổi convention nhưng metric event không thay đổi | Event counter được ghi trực tiếp vào MeterRegistry. | Kiểm tra nguồn metric và customizer chuyên biệt Spring Modulith. |
| Module span không xuất hiện | Module observability thiếu, proxy không intercept, sampling thấp hoặc context bị tách. | Kiểm tra starter, module API, trace backend và logs. |
| Có metrics nhưng trace trống | Metrics handler có mặt, tracing bridge/exporter hoặc sampling có vấn đề. | Kiểm tra pipeline trace độc lập. |
| Đổi tên làm số lượng series tăng mạnh | Nhãn kỹ thuật chứa ID/version/timestamp. | Chuẩn hóa nhãn ít giá trị và loại bỏ dữ liệu cá nhân. |
| Alert không báo khi bản mới lỗi | Alert vẫn lọc metric/tag cũ. | Chạy query và kiểm thử cảnh báo trên staging có dữ liệu thật. |

Một quy trình chẩn đoán hợp lý: **nghiệp vụ có chạy không → Observation có được tạo không → convention nào được chọn → handler có xuất dữ liệu không → exporter/backend có nhận không → dashboard/query có nhìn đúng tên và tags không**. Phân loại theo từng tầng để tránh sửa nhầm mã nghiệp vụ khi chỉ lỗi tên truy vấn.

## 14. Các giới hạn cần hiểu với module event và async

Trong ứng dụng Spring Modulith, **module graph** mô tả phụ thuộc; **/actuator/modulith** trình bày metadata kiến trúc; **module entry spans** quan sát tương tác của một số điểm API module; **event metrics** đếm công bố event; **Event Publication Registry** theo dõi publication đến transactional listeners khi cấu hình backend phù hợp. Chúng có mục đích và chính sách tên riêng.

Nếu listener dùng **@ApplicationModuleListener** để chạy sau commit và bất đồng bộ, trace context có thể không truyền qua thread hoặc không còn khi retry sau restart. **Giữ span name ổn định không tự nối lại parent/child trace.** Cần context propagation trên executor và **eventId** trong payload/log để đối chiếu nghiệp vụ.

Đặc biệt, một listener được gọi lại có thể tạo nhiều spans cho cùng **eventId**; đây không nhất thiết là sự kiện nghiệp vụ mới. Nhãn metric không nên dùng eventId vì tạo cardinality cao. Tên operation nên mô tả **lần xử lý listener**, còn kết quả cuối cùng phải xác minh từ transaction, publication status hoặc downstream system.

## 15. Thực hành: phát hiện hồi quy trong một đợt nâng cấp

**Kịch bản:** ứng dụng có module order, payment và notification. Bản hiện tại dùng `shop.order.confirm` và `module.invocations`; nhóm nâng Spring Boot và Spring Modulith để sửa lỗi bảo mật và bổ sung instrumentation.

Thực hiện:

1. Từ bản cũ, phát ba giao dịch mẫu: xác nhận đơn thành công, xác nhận lỗi, và phát sự kiện cho notification xử lý.
2. Lưu danh sách tên metric, labels và trace attributes; ghi các truy vấn đang dùng.
3. Thêm `StableOrderConfirmationConvention` và test giữ tên/tags.
4. Khởi động bản mới trên staging với cùng dữ liệu kiểm thử, cùng sampling và exporter nếu có thể.
5. So sánh tên technical, contextual, service và metadata module; không chỉ so tổng số trace.
6. Cố tình đổi `getName()` thành `shop.orders.confirmed` trong nhánh lab và chứng minh contract test thất bại.
7. Hoàn nguyên tên, kiểm tra dashboard truy vấn lại series như kỳ vọng.
8. Gây lỗi listener notification có kiểm soát; phân biệt trace listener với metric số event công bố.

### Tiêu chí đạt

| Tiêu chí | Bằng chứng |
| --- | --- |
| Technical name nghiệp vụ không đổi | Contract test + logical meter name ở runtime. |
| Contextual span name có chủ đích | Trace search trong backend. |
| Low-cardinality tags tương thích | So các nhãn và giá trị hữu hạn trước/sau. |
| Module spans có thể nhận diện | Thuộc tính `module.identifier`, `module.invocation-type` khi instrumentation có mặt. |
| Không phát sinh series theo orderId | Kiểm tra labels trên metric backend. |
| Dashboard/alert tìm thấy dữ liệu mới | Query trong staging sau deploy. |
| Lỗi async có thể điều tra | eventId trong logs, trace/exporter và trạng thái publication khi được cấu hình. |

## 16. Nguyên tắc bảo trì lâu dài

**Đặt hợp đồng gần nơi sở hữu instrumentation.** Module order nên có test cho observation của order. Framework instrumentation nên dùng convention extension chính thức thay vì bản vá tên ở nhiều dashboard riêng lẻ.

**Đánh version cho ngữ nghĩa, không gắn version vào mọi tên.** Nếu một hoạt động vẫn có ý nghĩa cũ, giữ nguyên tên. Nếu thay đổi phạm vi đo hoặc đơn vị đến mức so sánh lịch sử sai, tạo tên mới có review và kế hoạch migration.

**Giữ tập low-cardinality tags có giới hạn.** Module, operation, outcome và environment phù hợp nếu số giá trị có giới hạn; orderId, userId, email, build ID ngẫu nhiên và requestId không nên dùng làm metric labels.

**Đừng xem naming contract là bảo đảm trace hoàn chỉnh.** Sampling, exporter, backend, context propagation và bảo mật telemetry là những lớp riêng. Kiểm chứng từng lớp khi nâng cấp.

**Cập nhật tài liệu observability cùng thay đổi code.** Một dashboard có ý nghĩa vận hành nên được liên kết với tên Observation, nhãn, owner, span attributes và cách đo thời lượng. Khi đổi convention, thay đổi này cần được review như một thay đổi hợp đồng API.

## 17. Tài liệu tham khảo

Nguồn chính thức để kiểm tra behavior và API theo phiên bản:

- **Micrometer — Observation Components:** https://docs.micrometer.io/micrometer/reference/observation/components.html — convention/default/global, handler, filter, predicate và lifecycle.
- **Micrometer — Observation Introduction:** https://docs.micrometer.io/micrometer/reference/observation/introduction.html — technical name, KeyValues và các cách tạo Observation.
- **Micrometer — ObservationConvention API:** https://javadoc.io/doc/io.micrometer/micrometer-observation/latest/io/micrometer/observation/ObservationConvention.html — `getName`, `getContextualName`, `supportsContext`.
- **Spring Modulith — Production-ready Features:** https://docs.spring.io/spring-modulith/reference/production-ready.html — ModulithObservationConvention, Module Entry Span, metric event publication.
- **Spring Modulith — ModulithObservationConvention API:** https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservationConvention.html — extension point cho module observations.
- **Spring Boot — Observability:** https://docs.spring.io/spring-boot/reference/actuator/observability.html — ObservationRegistry, bean registration, common KeyValues và context propagation.

## 18. Tổng kết

**Giữ tên observation ổn định khi nâng cấp** là duy trì một hợp đồng giữa instrumentation và các hệ thống quan sát đang đọc dữ liệu đó. **ObservationConvention** cho phép kiểm soát technical name, contextual name và KeyValues; khi theo dõi tương tác module của Spring Modulith, hãy sử dụng **ModulithObservationConvention** nếu cần điều chỉnh naming contract tại đúng điểm mở rộng.

Muốn nâng cấp an toàn, hãy **ghi baseline**, **cố định hợp đồng bằng test**, **xác minh ở runtime**, **chuyển tiếp dashboard/alert có kế hoạch** và **phân biệt đổi tên với lỗi telemetry**. Kết hợp module graph, Actuator, event metrics, tracing, logs và context propagation sẽ giúp dữ liệu theo dõi có thể so sánh giữa các bản phát hành, ngay cả khi code và phiên bản framework tiếp tục thay đổi.
