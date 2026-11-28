# ObservationRegistryCustomizer

## 1. Bối cảnh: vì sao cần tùy chỉnh ObservationRegistry?

Trong Spring Boot có tổ chức theo **Spring Modulith**, các application module như **order**, **payment** và **notification** tương tác qua public API hoặc sự kiện miền. Module graph giúp kiểm tra phụ thuộc kiến trúc, còn **Micrometer Observation** giúp ghi nhận những lần tương tác thật khi ứng dụng chạy: thời lượng, lỗi, thuộc tính để phân nhóm và mối liên hệ giữa các spans.

**ObservationRegistryCustomizer** là điểm mở rộng của Spring Boot cho phép can thiệp vào cấu hình **ObservationRegistry** do Spring Boot tự tạo. Nhờ đó, ứng dụng có thể áp dụng một chính sách quan sát chung, chẳng hạn gắn một nhóm nhãn ổn định, loại bỏ observation không hữu ích hoặc đăng ký bộ xử lý theo vòng đời observation.

Bài thuộc chương **Observation API** của module **SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY**. Module học này hướng đến tài liệu hóa ranh giới application module và quan sát tương tác trong Spring Boot bằng module graph, Actuator, event metrics, tracing và context propagation. Mục tiêu riêng ở đây là hiểu **ObservationRegistryCustomizer** và áp dụng nó một cách có kiểm soát để những quan sát ở ranh giới module dễ tìm, dễ so sánh và không tạo quá nhiều telemetry.

Sau bài học, bạn cần giải thích được:

1. **ObservationRegistryCustomizer** là gì và được Spring Boot áp dụng khi nào.
2. Khác biệt giữa **ObservationRegistry**, **Observation**, **ObservationHandler**, **ObservationFilter**, **ObservationPredicate** và **ObservationConvention**.
3. Cách khai báo bean customizer với package import đúng trên Spring Boot **3.x** và **4.x**.
4. Khi nào dùng cấu hình **management.observations.\***, khi nào dùng bean thành phần, khi nào dùng customizer.
5. Cách kiểm chứng tác động của customizer trên metric, trace, module spans và xử lý bất đồng bộ.

## 2. Observation API: các thành phần cần phân biệt

Micrometer Observation cung cấp một lớp mô tả **hoạt động đang diễn ra**, độc lập với việc sau này hoạt động đó được ghi thành meter hay tracing span. Một đoạn mã có thể tạo Observation, còn handler nào được gắn vào registry sẽ quyết định dữ liệu nào được phát ra.

| Thành phần | Vai trò chính | Ví dụ |
| --- | --- | --- |
| **ObservationRegistry** | Chứa cấu hình chung của các Observation: handler, predicate, filter, convention. | Registry do Spring Boot auto-configure. |
| **Observation** | Đại diện một hoạt động được bắt đầu, ghi lỗi và kết thúc. | Một lần xử lý nghiệp vụ tạo đơn. |
| **Observation.Context** | Dữ liệu ngữ cảnh khả biến được handler/filter dùng trong vòng đời Observation. | Tên operation, KeyValues, thông tin lỗi. |
| **ObservationHandler** | Nhận callback vòng đời và tạo metric/span/log hoặc xử lý khác. | Handler tạo timer, handler tracing. |
| **ObservationPredicate** | Quyết định observation có được ghi nhận hay trở thành no-op. | Bỏ observation polling quá nhiễu. |
| **ObservationFilter** | Điều chỉnh Context khi observation sắp kết thúc. | Thêm nhãn cố định vào dữ liệu xuất. |
| **ObservationConvention** | Chuẩn hóa tên và các KeyValues của một loại instrumentation. | Quy ước đặt tên HTTP/server observation. |
| **GlobalObservationConvention** | Convention áp dụng toàn cục cho loại Context tương thích. | Quy chuẩn metadata dùng lại trên nhiều instrumentation. |
| **ObservationRegistryCustomizer** | Callback của **Spring Boot** để tùy chỉnh registry được auto-configure. | Đăng ký filter/predicate hoặc thay đổi cấu hình registry lúc startup. |

Lưu ý rằng **ObservationRegistryCustomizer không phải một khái niệm thay thế cho ObservationHandler**. Customizer chỉ đăng ký hoặc điều chỉnh các thành phần cấu hình; nếu không có đoạn mã hay instrumentation tạo Observation thì customizer không tự phát sinh metric/span nào.

### Sơ đồ vòng đời rút gọn

~~~mermaid
flowchart TD
    Boot["Spring Boot auto-configures ObservationRegistry"] --> Custom["Áp dụng các ObservationRegistryCustomizer"]
    Custom --> Config["Registry chứa predicates, filters, conventions, handlers"]
    App["Instrumentation / application code"] --> Create["Tạo Observation và Context"]
    Config --> Create
    Create --> Pred{"ObservationPredicate cho phép?"}
    Pred -->|"Không"| Noop["No-op: không tạo telemetry cho observation đó"]
    Pred -->|"Có"| Start["start / openScope"]
    Start --> Work["Mã nghiệp vụ thực thi"]
    Work --> Err["error nếu có lỗi"]
    Err --> Filter["Filter chỉnh Context khi stop"]
    Filter --> Handlers["Handler onStop"]
    Handlers --> Out["Metrics / spans / xử lý khác"]
~~~

Sơ đồ là khái quát về các bước chính, không mô tả mọi callback như scope, event hay trình tự nội bộ của từng handler. **ObservationFilter được gọi trước onStop của handler**, nên nhãn được thêm ở giai đoạn này không có nghĩa đã tồn tại ngay tại onStart. Nếu cần dữ liệu sớm cho handler, cân nhắc khởi tạo nó ngay trong context hoặc convention của instrumentation.

## 3. ObservationRegistryCustomizer hoạt động ra sao?

Interface mang dạng khái quát:

~~~java
@FunctionalInterface
public interface ObservationRegistryCustomizer<T extends ObservationRegistry> {
    void customize(T registry);
}
~~~

Đây là **callback tùy chỉnh registry do Spring Boot auto-configure**. Spring Boot nhận các bean của interface này và áp dụng chúng trong quá trình chuẩn bị registry, trước khi ứng dụng dùng registry để thu thập Observation.

Các đặc điểm quan trọng:

- Có thể khai báo **nhiều bean customizer** trong cùng Spring ApplicationContext.
- Có thể dùng lambda vì interface chỉ có một abstract method **customize(...)**.
- Kiểu generic **T** cho phép tùy chỉnh registry cụ thể khi cần. Với bài học thông thường, **ObservationRegistryCustomizer<ObservationRegistry>** là đủ.
- Callback cấu hình registry **một lần trong giai đoạn khởi tạo**; nó không phải callback được gọi mỗi khi xuất hiện một Observation.
- Các bean **ObservationPredicate**, **GlobalObservationConvention**, **ObservationFilter**, **ObservationHandler** cũng được Spring Boot tự đăng ký. Nếu chỉ cần thêm một bean thành phần, không nhất thiết phải bọc nó vào customizer.

Không nên tạo một bean **ObservationRegistry** mới chỉ để thêm một filter. Registry thủ công có thể làm khác đi cơ chế auto-configuration và khiến các bộ xử lý tracing/metrics sẵn có không được gắn như dự kiến. Nên ưu tiên tùy chỉnh registry do framework quản lý.

### So sánh với MeterRegistryCustomizer

| Tiêu chí | ObservationRegistryCustomizer | MeterRegistryCustomizer |
| --- | --- | --- |
| Đối tượng tác động | **ObservationRegistry** | **MeterRegistry** |
| Thay đổi gì? | Predicates, filters, conventions, handlers cho observation lifecycle. | Meter filters, common tags, naming convention, cấu hình meter backend. |
| Liên hệ với traces | Có, gián tiếp thông qua observation/tracing handler. | Không phải điểm cấu hình tracing span. |
| Dùng khi nào? | Chính sách chung cho Observation trước khi chuyển thành telemetry. | Chính sách chỉ dành cho metrics/MeterRegistry. |

**Observation metric và event publication counter không phải cùng một loại:** các metrics được Spring Modulith tạo trực tiếp qua Micrometer MeterRegistry có thể không đi qua mọi ObservationFilter. Muốn thay đổi nhãn của một meter được tạo trực tiếp, cần xem đúng API customizer của meter hoặc Spring Modulith, thay vì kỳ vọng ObservationRegistryCustomizer tác động lên tất cả meters.

## 4. Hai package import: Spring Boot 3.x và 4.x

Một khác biệt dễ gây lỗi biên dịch khi nâng phiên bản là **package** chứa interface:

| Spring Boot | Import của ObservationRegistryCustomizer |
| --- | --- |
| **3.x**, ví dụ 3.5 | **org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer** |
| **4.x** | **org.springframework.boot.micrometer.observation.autoconfigure.ObservationRegistryCustomizer** |

Cả hai đều thực hiện chức năng tùy chỉnh ObservationRegistry do Spring Boot tạo, nhưng **không dùng lẫn import của hai dòng phiên bản**. Đường dẫn mới thuộc cách Spring Boot 4 tách nhóm auto-configuration Micrometer/Observation. Khi viết mã, hãy kiểm tra tài liệu API đúng release train mà dự án đã chọn.

Đối với ứng dụng dùng Spring Modulith, cần bảo đảm **BOM Spring Boot, Spring Modulith và Micrometer** tương thích; không nên chọn phiên bản từng artifact thủ công mà bỏ qua dependency management của dự án.

### Dependency ví dụ cho Spring Boot 3.x

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    // Bật hỗ trợ module spans và Actuator của Spring Modulith.
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Đoạn này nhằm giới thiệu **ObservationRegistry và Modulith instrumentation**. Nếu cần xuất spans đến Zipkin hay Collector qua OTLP, phải thêm **tracing bridge/exporter đúng phiên bản**, cấu hình endpoint và sampling; starter Insight một mình không cung cấp backend tracing.

Với Spring Boot 4.x, sử dụng starter và module auto-configuration đúng dòng 4.x, ví dụ **spring-boot-starter-opentelemetry** nếu chọn đường OTLP. Không dùng lại cấu hình exporter Boot 3.x mà không kiểm tra property mới.

## 5. Ví dụ cơ bản: thêm nhãn có cardinality thấp

Ta muốn mọi Observation thuộc nhóm nghiệp vụ **shop.** có nhãn **business.area=commerce**, phục vụ dashboard và truy vấn metrics/traces theo nhóm.

~~~java
package com.example.shop.observability;

import io.micrometer.common.KeyValue;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.boot.actuate.autoconfigure.observation.ObservationRegistryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ShopObservationConfiguration {

    @Bean
    ObservationRegistryCustomizer<ObservationRegistry> addBusinessArea() {
        return registry -> registry.observationConfig()
            .observationFilter(context -> {
                if (context.getName() != null
                        && context.getName().startsWith("shop.")) {
                    context.addLowCardinalityKeyValue(
                        KeyValue.of("business.area", "commerce"));
                }
                return context;
            });
    }
}
~~~

Đoạn Java trên dùng **import Spring Boot 3.x**. Nếu dự án sử dụng Spring Boot 4.x, chỉ thay import của ObservationRegistryCustomizer bằng:

~~~java
import org.springframework.boot.micrometer.observation.autoconfigure.ObservationRegistryCustomizer;
~~~

Các import Micrometer và Spring Context còn lại giữ nguyên ở phạm vi ví dụ.

**Giải thích từng bước:**

1. Spring Boot tạo/chuẩn bị một **ObservationRegistry**.
2. Bean **addBusinessArea** được gọi để đăng ký **ObservationFilter** vào cấu hình registry.
3. Khi một Observation có tên bắt đầu bằng **shop.** kết thúc, filter bổ sung low-cardinality KeyValue vào Context.
4. Các handler phù hợp có thể dùng KeyValue đó khi ghi dữ liệu metric/span.

Ví dụ dùng giá trị **commerce** cố định nên số lượng giá trị nhãn có giới hạn. Nếu muốn phân loại nhiều nghiệp vụ, dùng danh sách giá trị xác định (chẳng hạn **order**, **payment**, **notification**) và đặt nhãn ở instrumentation nơi biết chính xác module nào đang xử lý.

**Không giả định tên observation của Spring Modulith bắt đầu bằng shop.** Bộ lọc trên chỉ dành cho các Observation do ứng dụng đặt tên theo tiền tố đó. Khi muốn gắn một nhãn chung lên module spans do Spring Modulith instrument, hãy kiểm tra tên/context thực tế hoặc dùng chính sách toàn cục với nhãn ổn định.

## 6. Ví dụ tạo Observation nghiệp vụ để kiểm chứng

Một service có thể inject registry chung rồi tạo Observation:

~~~java
package com.example.shop.order;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class OrderConfirmationService {

    private final ObservationRegistry observations;

    OrderConfirmationService(ObservationRegistry observations) {
        this.observations = observations;
    }

    void confirmOrder() {
        Observation.createNotStarted("shop.order.confirm", observations)
            .lowCardinalityKeyValue("operation", "confirm")
            .observe(() -> {
                // Gọi logic nghiệp vụ cần quan sát ở đây.
                performConfirmation();
            });
    }

    private void performConfirmation() {
        // Ví dụ tự chứa để minh họa điểm instrument.
    }
}
~~~

Sau khi gọi **confirmOrder()** ở môi trường đã bật metric handler, một Observation có tên **shop.order.confirm** có thể tạo timer, mang nhãn **operation=confirm** và **business.area=commerce**. Nếu có tracing handler và sampler/exporter đúng cấu hình, cùng Observation này cũng có thể sinh span.

Khi ứng dụng đã có instrumentation tương tự ở một API public module, cần kiểm tra nguy cơ **duplicate observations** trước khi bọc thêm Observation thủ công. Hai lớp observation lồng nhau là hợp lệ nếu đo **hai công việc khác nhau**, nhưng vô ích nếu cùng đo một khoảng thời gian mà không thêm thông tin.

### Low cardinality và high cardinality

~~~java
Observation.createNotStarted("shop.order.confirm", observations)
    .lowCardinalityKeyValue("module", "order")
    .highCardinalityKeyValue("correlation.id", "sample-123")
    .observe(this::performConfirmation);
~~~

- **Low-cardinality KeyValue** dùng cho cả metrics và traces; nên là các nhóm giá trị ít và ổn định.
- **High-cardinality KeyValue** dùng cho tracing, không được dùng làm metric tag qua handler tiêu chuẩn.
- High-cardinality **không có nghĩa được phép ghi dữ liệu nhạy cảm**. Không thêm email, token, số thẻ hoặc toàn bộ payload. Correlation ID chỉ nên ghi nếu phù hợp chính sách dữ liệu và yêu cầu điều tra.

## 7. ObservationPredicate: lọc bỏ công việc không cần quan sát

Nếu ứng dụng có vòng polling nội bộ xảy ra rất thường xuyên, có thể muốn không tạo Observation cho thao tác này. **ObservationPredicate** quyết định việc tạo Observation có hữu ích không; khi bị từ chối, Observation trở thành **no-op**.

~~~java
@Bean
ObservationRegistryCustomizer<ObservationRegistry> skipNoisyPolling() {
    return registry -> registry.observationConfig()
        .observationPredicate((name, context) ->
            !"shop.internal.polling".equals(name));
}
~~~

Ví dụ này có thể đặt trong class cấu hình ở mục 5 và dùng import tương ứng với Spring Boot version. Trong ứng dụng thật, ưu tiên chính sách hẹp theo tên observation đã biết. Một predicate quá rộng như **name.startsWith("http.")** có thể làm mất dữ liệu HTTP quan trọng, gây khó điều tra lỗi hoặc tạo khoảng mù trong dashboard.

Spring Boot còn cung cấp cách bật/tắt theo tên hoặc prefix qua property:

~~~yaml
management:
  observations:
    enable:
      shop:
        internal:
          polling: false
~~~

Với quy tắc đơn giản theo observation name, property thường dễ đọc và dễ điều chỉnh giữa môi trường hơn mã Java. Chỉ dùng predicate khi cần điều kiện phức tạp hơn, chẳng hạn phụ thuộc thông tin Context hoặc cấu hình riêng của ứng dụng.

**Thứ tự logic:** Predicate được đánh giá khi Observation được tạo, còn Filter chỉnh Context ở giai đoạn gần kết thúc. Vì vậy, đừng dùng filter như cơ chế bảo đảm chặn việc thu thập một Observation; dùng predicate hoặc cấu hình enable khi muốn không ghi nhận nó.

## 8. ObservationFilter: bổ sung hoặc chuẩn hóa metadata

Filter thích hợp khi cần thêm nhãn chung hoặc chỉnh Context trước khi handlers hoàn tất việc xuất dữ liệu.

~~~java
@Bean
ObservationRegistryCustomizer<ObservationRegistry> addDeploymentLabel() {
    return registry -> registry.observationConfig()
        .observationFilter(context -> {
            context.addLowCardinalityKeyValue(
                KeyValue.of("deployment.environment", "training"));
            return context;
        });
}
~~~

Ví dụ trên áp dụng **cho tất cả Observation sử dụng registry này**. Đây là chính sách khá rộng, nên chỉ dùng nhãn ổn định, không tăng mạnh cardinality và không lộ thông tin nội bộ nhạy cảm. Khi triển khai nhiều môi trường, giá trị môi trường nên đến từ cấu hình đã được kiểm soát thay vì hardcode trong bài minh họa.

Trong Spring Boot có một lựa chọn đơn giản hơn cho common tags:

~~~yaml
management:
  observations:
    key-values:
      deployment.environment: training
      service.group: shop
~~~

Với common tags tĩnh, ưu tiên property trên. **Không cần customizer chỉ để gắn hai nhãn cố định.** Dùng customizer/filter khi cần logic có điều kiện, chọn nhóm Observation hoặc chuẩn hóa thông tin mà property không biểu diễn được.

Lưu ý: filter được áp dụng trước khi Observation kết thúc; các handler đã dùng Context ở **onStart** có thể không thấy những giá trị chỉ được thêm sau này. Nếu một thuộc tính cần hiện diện ngay khi bắt đầu, đặt nó vào Context từ nguồn instrumentation hoặc convention thích hợp.

## 9. Customizer, bean thành phần và ObservationConvention

Spring Boot tự động đăng ký các bean kiểu **ObservationPredicate**, **GlobalObservationConvention**, **ObservationFilter** và **ObservationHandler** vào registry. Vì thế cùng một mục tiêu có thể có nhiều cách cấu hình:

| Mục tiêu | Cách nên ưu tiên | Lý do |
| --- | --- | --- |
| Nhãn chung tĩnh | **management.observations.key-values** | Ít mã, dễ đổi theo môi trường. |
| Tắt observation theo name/prefix | **management.observations.enable** | Rõ ràng và tránh predicate Java không cần thiết. |
| Thêm một filter độc lập | **@Bean ObservationFilter** | Spring Boot tự gắn vào registry. |
| Thêm một predicate độc lập | **@Bean ObservationPredicate** | Dễ đọc và test theo unit. |
| Chuẩn hóa tên/tags một instrumentation | **ObservationConvention** phù hợp | Nơi đúng để định nghĩa hợp đồng metadata cho loại observation. |
| Nhiều thao tác cấu hình registry có liên quan | **ObservationRegistryCustomizer** | Tập trung chính sách cấu hình và điều kiện. |
| Thêm hành vi vào vòng đời Observation | **@Bean ObservationHandler** hoặc customizer đăng ký handler | Có callback start/stop/error/event nếu hỗ trợ Context. |

Ví dụ chỉ cần bean filter, không cần customizer:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.observation.ObservationFilter;
import org.springframework.context.annotation.Bean;

@Bean
ObservationFilter addShopTag() {
    return context -> {
        context.addLowCardinalityKeyValue(KeyValue.of("service.group", "shop"));
        return context;
    };
}
~~~

Đoạn method có thể đặt trong một class **@Configuration**. Nếu bean filter này đã được auto-register, **đừng đăng ký cùng instance lần nữa qua customizer**, vì có thể khiến chính sách bị áp dụng lặp lại hoặc làm khó lý giải thứ tự cấu hình.

### ObservationHandler là gì trong mô hình này?

Một handler nhận các callback như **onStart**, **onError**, **onEvent** và **onStop**, tùy loại Context mà **supportsContext** cho phép. Handler có thể tạo timer, span hoặc ghi sự kiện phục vụ điều tra.

Với Spring Boot + Actuator + tracing, framework đã cấu hình các handler phù hợp theo dependency. **Không tự thêm một handler tạo metric hoặc tracing thứ hai chỉ để thấy dữ liệu**, vì có nguy cơ tạo phép đo/span trùng. Khi cần thêm một handler, nên có mục tiêu rõ ràng (ví dụ audit một loại Observation) và kiểm tra dữ liệu xuất ra không lặp.

### Convention và Filter khác nhau ra sao?

**ObservationConvention** thường cung cấp hợp đồng tên và KeyValues khi instrumentation tạo Observation; còn **ObservationFilter** hoạt động trong lifecycle khi Context đã tồn tại và có thể chứa dữ liệu runtime. Nếu cần đổi hẳn tên hay schema của HTTP observation, convention chuyên biệt đáng tin cậy hơn một filter toàn cục chỉ kiểm tra chuỗi name.

## 10. Tác động của customizer lên Spring Modulith module spans

Spring Modulith có instrumentation cho tương tác tại API application module, có thể sinh **Module Entry Span** khi có tracing support. Các thuộc tính được tài liệu hóa gồm:

| Thuộc tính module span | Mục đích |
| --- | --- |
| **module.identifier** | Mã module kỹ thuật, ví dụ **order**. |
| **module.name** | Tên module. |
| **module.method** | Phương thức được gọi. |
| **module.invocation-type** | Hình thức gọi, chẳng hạn **bean** hoặc **event listener**. |

Nếu module instrumentation dùng **ObservationRegistry do Spring Boot quản lý**, chính sách chung do customizer đăng ký có thể tác động lên những Observation này. Ví dụ filter toàn cục thêm **deployment.environment=training** vào Observation có thể xuất hiện trên span tương ứng nếu tracing handler ghi nhận KeyValue đó.

Tuy nhiên, phải tách bạch:

- **Customizer không tự bật module spans**. Cần Spring Modulith observability/Insight starter, Micrometer Tracing, tracer bridge/exporter và cấu hình tương thích.
- **Customizer không đổi module graph**. Ranh giới module và quan hệ phụ thuộc được xác định từ cấu trúc mã nguồn và cấu hình Modulith.
- **Customizer không tự đổi Event Publication Registry**. Trạng thái xử lý sự kiện là vấn đề persistence/lifecycle riêng.
- **Customizer không bảo đảm thay đổi tất cả event metrics**. Một số counter được ghi trực tiếp trên MeterRegistry thay vì phát sinh từ Observation.
- **Customizer không sửa context propagation**. Nếu listener async xử lý trên thread khác, cần cơ chế chuyển context riêng.

### Sơ đồ kiến trúc và dữ liệu vận hành

~~~mermaid
flowchart LR
    Modules["Application modules: order / payment / notification"] --> Insight["Spring Modulith observability"]
    Insight --> Registry["Spring Boot ObservationRegistry"]
    Customizer["ObservationRegistryCustomizer"] --> Registry
    Registry --> Meter["Metrics handler / MeterRegistry"]
    Registry --> Trace["Tracing handler"]
    Meter --> Dashboard["Actuator / Metrics backend"]
    Trace --> Export["OTLP / Zipkin exporter"]
    Export --> Backend["Trace backend"]
    Modules --> Graph["Module graph + /actuator/modulith"]
~~~

Đường từ **Customizer tới Registry** là **cấu hình chung**, không phải một luồng gửi event theo thời gian thực. Đường module graph nằm riêng vì metadata kiến trúc và telemetry runtime có bản chất khác nhau.

## 11. Một kịch bản sử dụng thực tế

Giả sử đội vận hành muốn thống nhất nhãn **deployment.environment** và loại bỏ polling observation quá dày trước khi xuất đến Prometheus hoặc tracing backend. Đồng thời, nhóm muốn giữ lại module spans của **order**, **payment** và **notification** để tìm tương tác bất thường.

Một cấu hình hợp lý:

~~~yaml
spring:
  application:
    name: shop-modulith

management:
  observations:
    key-values:
      deployment.environment: staging
    enable:
      shop:
        internal:
          polling: false
  endpoints:
    web:
      exposure:
        include: health,info,metrics,modulith
~~~

Nếu chỉ cần hai chính sách này, **không phải viết ObservationRegistryCustomizer**. Nếu sau này cần chính sách có điều kiện phức tạp, có thể bổ sung customizer:

~~~java
@Bean
ObservationRegistryCustomizer<ObservationRegistry> shopRegistryPolicy() {
    return registry -> registry.observationConfig()
        .observationPredicate((name, context) -> {
            // Chỉ loại bỏ đúng nhóm hoạt động đã xác định là không cần theo dõi.
            return !"shop.legacy.polling".equals(name);
        })
        .observationFilter(context -> {
            // Gắn metadata cho một nhóm observation nghiệp vụ.
            if (context.getName() != null
                    && context.getName().startsWith("shop.order.")) {
                context.addLowCardinalityKeyValue(
                    KeyValue.of("business.module", "order"));
            }
            return context;
        });
}
~~~

Với chính sách chung, cần quan sát số lượng time series mới, độ trễ xử lý và sự khác biệt giữa trước/sau cấu hình. Nếu có khả năng trùng tên nhãn, quy định nguồn nào được phép đặt hoặc thay thế trước khi đưa vào production.

## 12. Kiểm chứng kết quả ở runtime

### Bước 1 — Xác định registry đang được dùng

Trong Spring Boot context, inject **ObservationRegistry** vào service tạo Observation và xác nhận app chạy với các starter cần thiết. **Không tạo ObservationRegistry.create() trong business code** rồi dùng registry riêng nếu mong customizer Spring Boot tự được áp dụng.

### Bước 2 — Tạo một Observation có thể dự đoán

Gọi **OrderConfirmationService.confirmOrder()** ở mục 6. Nếu có metrics handler, kiểm tra timer với tên **shop.order.confirm** và các low-cardinality tags **operation=confirm**, **business.area=commerce**.

Ví dụ HTTP Actuator sau khi đã expose và có quyền truy cập:

~~~bash
curl -fsS http://localhost:8080/actuator/metrics

curl -fsS http://localhost:8080/actuator/metrics/shop.order.confirm
~~~

Nếu không thấy meter, kiểm tra đã gọi phương thức, registry có metrics handler và Actuator/MeterRegistry có được thiết lập hay chưa. Một **Observation** không nhất thiết dẫn tới một metric nếu handler tương ứng không có mặt.

### Bước 3 — Quan sát trace nếu được cấu hình

Khi ứng dụng có Micrometer Tracing và exporter đến Zipkin/OTLP, gửi request rồi tìm service **shop-modulith** trên trace backend. Kiểm tra span của Observation nghiệp vụ hoặc module entry span, cùng các attributes/tag liên quan. Nếu có sampling, **không có trace sau một request đơn lẻ chưa đủ bằng chứng có lỗi**.

Trong môi trường lab, có thể đặt tỉ lệ sampling cao để xác minh; production cần cân nhắc chi phí/retention.

### Bước 4 — Kiểm tra negative case của predicate

Tạo Observation có tên **shop.internal.polling**; nếu cấu hình chặn ở mục 7 có hiệu lực, nó sẽ không tạo telemetry bình thường. Sau đó tạo **shop.order.confirm** để xác nhận policy không làm mất Observation quan trọng.

### Bước 5 — Kiểm tra với module spans

Khi Spring Modulith Insight và tracing đã bật, thực hiện một luồng giữa các module. Trong trace backend, tìm module span theo **module.identifier** và **module.invocation-type**. Kiểm tra nhãn toàn cục có xuất hiện như kỳ vọng nhưng vẫn giữ lại các thuộc tính module cốt lõi.

**Đừng kiểm tra chỉ bằng /actuator/modulith**: endpoint này mô tả kiến trúc module, không xác minh từng Observation đã được tạo hay exporter gửi span thành công.

## 13. Kiểm thử tích hợp và những giới hạn cần nhớ

Một bộ kiểm thử nhỏ nên có cả **trường hợp được ghi nhận** và **trường hợp bị chặn**:

| Trường hợp | Hành động | Bằng chứng mong đợi |
| --- | --- | --- |
| Customizer được Spring Boot áp dụng | Khởi động application context thật, inject registry do Boot quản lý. | Filter/predicate tác động lên Observation được tạo trong context. |
| Filter thêm low-cardinality tag | Tạo **shop.order.confirm**, kết thúc Observation. | Metric/span có nhãn hợp lệ khi handler có mặt. |
| Predicate chặn observation | Tạo **shop.internal.polling**. | Không có telemetry tương ứng. |
| Observation khác không bị chặn | Tạo **shop.payment.authorize**. | Observation vẫn được ghi khi handler phù hợp. |
| Không làm mất module spans | Thực hiện tương tác module đã instrument. | Span giữ metadata module cần thiết. |
| Async listener | Chuyển việc sang executor. | Trace/log correlation phù hợp với chính sách propagation. |
| Không nhân đôi telemetry | So meter count và số span trước/sau cấu hình. | Không có handler được đăng ký trùng gây tăng đếm. |

Để kiểm thử **riêng logic** của lambda, có thể tạo registry thủ công trong unit test và **gọi customizer.customize(registry) một cách tường minh**. Registry được tạo thủ công không tự trải qua Spring Boot auto-configuration, nên unit test như vậy **không chứng minh** wiring production. Muốn xác nhận wiring, phải dùng application context có auto-configuration tương ứng.

Nếu test đo metrics, cần một MeterRegistry/metrics handler. Nếu test trace, cần tracer handler, sampler và exporter hoặc công cụ kiểm thử tracing. Không coi việc gọi **Observation.observe(...)** không ném exception là bằng chứng telemetry đã tới backend.

## 14. Context propagation khi listener xử lý bất đồng bộ

Trong Spring Modulith, listener sự kiện có thể chạy sau commit và trên executor khác, ví dụ qua **@ApplicationModuleListener**. **ObservationRegistryCustomizer không tự mang trace context từ thread publisher sang thread listener**. Nếu context không được chuyển, span của listener có thể là trace mới hoặc log bị thiếu traceId.

Với Spring Boot 3.x, tài liệu observability mô tả **ContextPropagatingTaskDecorator** cho executor khi dùng **@Async** hoặc AsyncTaskExecutor. Với Spring Boot 4.x, khi dùng auto-configured AsyncTaskExecutor, có thể opt-in qua **spring.task.execution.propagate-context**; nếu tự tạo executor, vẫn cần cấu hình decorator phù hợp.

Ví dụ một TaskDecorator bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

@Configuration(proxyBeanMethods = false)
class AsyncObservationConfiguration {

    @Bean
    ContextPropagatingTaskDecorator contextPropagatingTaskDecorator() {
        return new ContextPropagatingTaskDecorator();
    }
}
~~~

Ví dụ chỉ cho thấy cách cung cấp decorator trong context. **Phải xác nhận executor thực sự dùng decorator đó**. Khi ứng dụng tự quản lý executor hay có nhiều executor, cần nối đúng bean với tác vụ async đang chạy. Không kết luận context propagation hoạt động chỉ vì bean hiện diện.

Trace context và transaction context khác nhau: chuyển observation context không mang transaction JDBC của publisher sang listener. Đối với tác vụ được retry sau restart hoặc qua message broker, nên dùng **eventId** trong payload/log làm tương quan nghiệp vụ bền vững, đồng thời thiết kế propagation phù hợp với boundary thực tế.

## 15. Những lỗi hay gặp khi dùng ObservationRegistryCustomizer

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Import không tồn tại | Dùng package Boot 3.x trên Boot 4.x hoặc ngược lại. | Kiểm tra version và đổi import đúng bảng mục 4. |
| Customizer không tác động | Business code tạo registry riêng hoặc bean không nằm trong Spring context. | Inject ObservationRegistry do Boot quản lý, kiểm tra component scan/auto-config. |
| Metric không có dù Observation chạy | Thiếu metrics handler/MeterRegistry hoặc chưa tạo đúng loại Observation. | Kiểm tra dependencies, handlers, tên metric và việc gọi nghiệp vụ. |
| Không có tracing span | Thiếu tracing bridge/exporter, sampling thấp, collector/backend lỗi. | Kiểm tra pipeline riêng của tracing. |
| Nhãn thêm vào metric nhưng không thấy tại onStart | ObservationFilter áp dụng gần stop. | Đặt nhãn sớm hơn qua instrumentation/convention nếu cần. |
| Nhiều time series bất thường | Gắn orderId/email/requestId vào low-cardinality label. | Giới hạn giá trị nhãn, chuyển định danh sang logs/traces nếu phù hợp. |
| Double-count metric hoặc trùng span | Đăng ký handler lặp, thêm instrumentation lên phương thức đã được quan sát. | Loại bỏ handler/instrumentation dư và test count. |
| Mất module spans sau khi thêm predicate | Predicate quá rộng, chặn cả Observation của module. | Thu hẹp tên/context match và thử nghiệm với trace thật. |
| Listener async có traceId khác | Không propagate context qua executor hoặc xử lý diễn ra muộn. | Cấu hình propagation, giữ eventId và kiểm tra behavior thực. |
| Thấy nhãn nhưng không có module graph | Observation metadata khác metadata kiến trúc. | Kiểm tra Modulith Actuator và cấu trúc application module riêng. |
| Event metric không đổi theo ObservationFilter | Metric được tạo trực tiếp qua MeterRegistry. | Chọn API customizer đúng cho nguồn metric cụ thể. |

Một nguyên tắc quan trọng: **không che lỗi thiết kế bằng filter**. Nếu một quan hệ module vi phạm ranh giới, cần sửa kiến trúc và dùng kiểm thử **ApplicationModules.verify()**; customizer chỉ tác động telemetry, không làm quan hệ phụ thuộc trở nên hợp lệ.

## 16. Nguyên tắc vận hành và quản trị telemetry

**Chọn nhãn ít giá trị.** Các nhóm module, environment, outcome hoặc operation thường phù hợp hơn ID từng đơn hàng. Thiết kế danh sách label cho cả metrics và traces trước khi đưa vào production.

**Giữ cấu hình dễ kiểm soát.** Với common tags hay enable/disable đơn giản, ưu tiên properties. Chỉ dùng ObservationRegistryCustomizer khi có lợi ích từ logic Java. Hạn chế tạo nhiều customizer có quy tắc chồng chéo khiến kết quả khó đoán.

**Không làm mất dữ liệu quan trọng.** Predicate có thể chặn cả metrics và tracing tạo ra từ Observation. Trước khi chặn một observation quá nhiễu, xác nhận nó không cần cho SLO, cảnh báo hoặc điều tra bảo mật.

**Đối chiếu nhiều nguồn.** Module graph xác nhận kiến trúc; Actuator cung cấp endpoint quan sát sức khỏe/metrics; tracing thể hiện những lời gọi đã sampled/export; Event Publication Registry theo dõi trạng thái công bố sự kiện khi cấu hình. Một customizer không thay thế các chức năng ấy.

**Giữ dữ liệu an toàn.** Cấu hình dùng tags/span attributes không được làm lộ bí mật, thông tin cá nhân hoặc payload nhạy cảm. Bảo vệ endpoint Actuator bằng network và authentication/authorization; kiểm soát retention của backend.

## 17. Tài liệu tham khảo chính thức

- **Spring Boot 3.5 — Observability:** https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html — ObservationRegistry, bean auto-registration, common tags, predicate, context propagation.
- **Spring Boot 4.x — Observability:** https://docs.spring.io/spring-boot/reference/actuator/observability.html — registry customization, các lựa chọn cấu hình observation và context propagation.
- **Spring Boot 3.5 — ObservationRegistryCustomizer API:** https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/observation/ObservationRegistryCustomizer.html — interface/package trên Boot 3.x.
- **Spring Boot 4.0 — ObservationRegistryCustomizer API:** https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/micrometer/observation/autoconfigure/ObservationRegistryCustomizer.html — interface/package trên Boot 4.x.
- **Micrometer — Observation Components:** https://docs.micrometer.io/micrometer/reference/observation/components.html — các handler, filter, predicate, convention và trình tự vòng đời.
- **Spring Modulith — Production-ready Features:** https://docs.spring.io/spring-modulith/reference/production-ready.html — Insight starter, module spans, Actuator và event metrics.

## 18. Tổng kết

**ObservationRegistryCustomizer** là một callback của Spring Boot giúp thay đổi cấu hình **ObservationRegistry auto-configured** một cách tập trung. Nó hữu ích khi cần kết hợp filter, predicate, handler hoặc chính sách registry; tuy nhiên nhiều yêu cầu đơn giản đã có thể đáp ứng bằng **management.observations.\*** hoặc các bean **ObservationFilter/ObservationPredicate** mà Spring Boot tự đăng ký.

Khi áp dụng vào ứng dụng Spring Modulith, hãy phân biệt **customization của telemetry** với **kiến trúc module** và **độ tin cậy event processing**. Kết quả chỉ có ý nghĩa khi registry thực sự được dùng bởi instrumentation, có handlers/exporters phù hợp và context được truyền đúng qua các ranh giới bất đồng bộ. Kết hợp module graph, Actuator, event metrics, tracing và structured logs sẽ giúp xác nhận tương tác giữa các module bằng dữ liệu chạy thật, đồng thời giữ telemetry nhất quán, có kiểm soát và dễ vận hành.
