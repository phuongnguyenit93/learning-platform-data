# ObservationPredicate để lọc observation

> **Chương:** Observation API  
> **Module học tập:** `SPRING_MODULITH_DOCUMENTATION_OBSERVABILITY`  
> **Định hướng:** Dùng Spring Modulith để sinh tài liệu ranh giới application module và quan sát tương tác giữa các phần trong ứng dụng Spring Boot. Học module graph, Actuator, event metrics, tracing và context propagation để kiểm chứng kiến trúc mô-đun khi hệ thống vận hành.  
> **Trọng tâm:** Dùng `ObservationPredicate` của Micrometer để loại những observation không cần thiết, giữ thông tin quan trọng về tương tác module và hiểu rõ hệ quả đối với metrics/tracing.

## 1. Vì sao cần lọc observation?

Một ứng dụng Spring Boot phân chia thành các application module `order`, `inventory` và `notification`. Khi bật Spring Modulith observability, lời gọi vào API của module và một số event listener có thể được ghi nhận dưới dạng Micrometer Observation. Nếu hệ thống còn instrument HTTP request, HTTP client và thao tác nghiệp vụ, một request có thể chứa nhiều span.

Ví dụ:

~~~text
POST /orders                                HTTP server
└── order.complete(...)                     Module order
    ├── inventory.reserve(...)              Module inventory
    ├── notification.pollStatus(...)        Module notification
    ├── notification.pollStatus(...)        Module notification
    └── notification.sendReceipt(...)       Module notification
~~~

Nếu `notification.pollStatus()` được gọi hàng nghìn lần mà ít giúp điều tra sự cố, nhóm vận hành có thể muốn loại **observation tại riêng điểm đo đó**. Đồng thời, nhóm vẫn cần thấy span `order` và `inventory` để xác nhận ranh giới module.

**`ObservationPredicate` cho phép quyết định có tạo một observation hữu hiệu hay trả về observation no-op, dựa trên tên và context của observation.** Đó là cách kiểm soát dữ liệu quan sát tại nguồn thay vì chỉ ẩn nó ở dashboard.

Một giới hạn phải nhớ ngay từ đầu: **lọc observation không hủy lời gọi Java, HTTP request, listener, event hay transaction.** Code nghiệp vụ được thực thi theo cách vốn có. Predicate chỉ tác động đến phần instrumentation đi qua `ObservationRegistry` tương ứng.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cách `ObservationPredicate` tham gia lifecycle của Micrometer Observation.
2. Phân biệt predicate với `ObservationFilter`, `ObservationConvention`, `MeterFilter` và tracing sampler.
3. Đăng ký predicate thông qua Spring Boot bean hoặc trực tiếp trên `ObservationRegistry`.
4. Lọc theo tên và lọc hẹp theo `ModulithContext`, module identifier, loại lời gọi.
5. Viết test chứng minh observation no-op nhưng logic nghiệp vụ vẫn được chạy.
6. Đối chiếu kết quả với module graph, Actuator, event metrics, tracing và context propagation.

## 2. ObservationPredicate nằm ở đâu trong Micrometer?

Micrometer Observation có những thành phần sau:

| Thành phần | Trách nhiệm |
|---|---|
| `ObservationRegistry` | Registry chứa cấu hình predicate, handler, convention và filter |
| `Observation.Context` | Dữ liệu đi cùng một observation và được dùng trong lifecycle |
| `ObservationPredicate` | Quyết định observation có được bật **khi tạo** hay nhận dạng no-op |
| `ObservationHandler` | Phản ứng với các sự kiện như start, stop, error; có thể tạo timer hoặc span |
| `ObservationFilter` | Sửa context trước các callback stop của handler |
| `ObservationConvention` | Quy định tên, contextual name và key-values |
| `MeterRegistry` | Lưu các meter Micrometer, gồm cả meter không xuất phát từ Observation |

Sơ đồ khái niệm:

~~~mermaid
flowchart TD
    A["Framework hoặc ứng dụng muốn tạo observation"] --> B["Tên và Observation.Context"]
    B --> C{"Mọi ObservationPredicate trả true?"}
    C -- "false" --> D["Observation no-op"]
    C -- "true" --> E["Observation hữu hiệu"]
    E --> F["ObservationHandler trên lifecycle"]
    F --> G["Metric qua handler phù hợp"]
    F --> H["Span qua tracing handler"]
    E --> I["ObservationFilter có thể chỉnh context"]
    D --> J["Logic nghiệp vụ vẫn thực thi"]
    E --> J
~~~

Predicate được đánh giá trong giai đoạn tạo observation, **trước khi các lifecycle handler xử lý observation hữu hiệu**. Điều này có ý nghĩa lớn: tag chỉ được bổ sung vào context *sau* thời điểm đó không thể là điều kiện lọc đáng tin cậy.

### 2.1. API cơ bản

`io.micrometer.observation.ObservationPredicate` là functional interface, với hợp đồng:

~~~java
boolean test(String name, Observation.Context context);
~~~

- Trả `true`: không phản đối việc tạo observation. Những predicate khác vẫn có thể loại nó.
- Trả `false`: observation tương ứng trở thành no-op.
- Ném exception: có thể ảnh hưởng đường tạo observation, nên không đặt nghiệp vụ hoặc I/O dễ lỗi trong predicate.

Một `Observation` no-op không tạo các sự kiện lifecycle thực cho handler như observation thông thường. Nhưng với đoạn:

~~~java
Observation.createNotStarted("demo.noisy.poll", registry)
        .observe(() -> performPolling());
~~~

`performPolling()` **vẫn được gọi** kể cả khi predicate loại observation. Predicate không phải cơ chế dừng tác vụ.

### 2.2. Nhiều predicate kết hợp theo AND

Nếu có nhiều predicate, một observation chỉ được chấp nhận khi **tất cả** trả `true`. Chẳng hạn:

| P1 | P2 | Kết quả |
|---|---|---|
| `true` | `true` | Observation hữu hiệu |
| `true` | `false` | No-op |
| `false` | `true` | No-op |
| `false` | `false` | No-op |

Vì vậy khi chỉ muốn chặn nhóm nhỏ, hãy **cho phép mọi loại observation nằm ngoài phạm vi chính sách**. Việc return false mặc định cho những context không quen thuộc có thể vô tình tắt HTTP spans, business observations và instrumentation khác.

## 3. Phân biệt predicate với các cơ chế có tên gần giống

| Cơ chế | Thời điểm/phạm vi | Dùng khi nào | Không giải quyết |
|---|---|---|---|
| `ObservationPredicate` | Khi tạo Micrometer Observation | Quyết định observation hữu hiệu hay no-op theo tên/context | Không dừng business logic |
| `ObservationFilter` | Trước bước stop handler | Thêm, xóa, sửa các key-values/context | Không chọn bỏ observation ngay từ đầu |
| `ObservationConvention` | Quy ước name, contextual name, tags | Chuẩn hóa nội dung telemetry | Không tự chặn observation |
| `MeterFilter` | Ở tầng Micrometer MeterRegistry | Chặn hoặc đổi meter/tag | Không mặc nhiên chặn tracing span |
| Tracing sampler | Tầng trace | Giảm lượng trace thu thập mà vẫn giữ metric | Không đồng nghĩa loại Observation |
| Collector/backend filter | Sau lúc phát telemetry | Giới hạn dữ liệu lưu/xuất/truy vấn | Không loại bỏ mọi chi phí instrumentation trong ứng dụng |
| `management.observations.enable.*` | Cấu hình Spring Boot theo prefix tên | Tắt nhóm observation có tên ổn định | Không thuận tiện cho điều kiện phức tạp theo context |
| Bỏ annotation `@Observed` trùng | Nơi phát sinh instrument | Xóa nguồn đo dư trên cùng method | Không thay thế quan sát có ý nghĩa khác |

**Chọn đúng tầng rất quan trọng.** Nếu chỉ muốn giảm trace nhưng cần giữ timer của HTTP request, tracing sampler phù hợp hơn một predicate chặn cả observation HTTP. Nếu muốn thêm một tag, dùng convention/filter. Nếu cần loại một meter trực tiếp, xem `MeterFilter`.

### 3.1. ObservationPredicate không phải bộ lọc cho mọi metric

Một số metric được tạo trực tiếp từ `MeterRegistry`:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

void recordPayment(MeterRegistry meterRegistry) {
    Counter.builder("payment.accepted")
            .register(meterRegistry)
            .increment();
}
~~~

Counter trên không bắt buộc đi qua `ObservationRegistry`; predicate có thể **không tác động gì** đến nó. Tương tự, các counter domain event như `module.events.published` của Spring Modulith có cơ chế ghi nhận riêng. Không suy đoán rằng chặn span module entry sẽ tự xóa counter event publication.

## 4. Bắt đầu bằng chính sách lọc theo tên

### 4.1. Một ví dụ tối thiểu

Giả sử ứng dụng có observation kỹ thuật mang tên chính xác `diagnostics.noisy.poll`. Muốn loại nó, nhưng giữ các observation khác:

~~~java
package com.acme.shop.observability;

import io.micrometer.observation.ObservationPredicate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ObservationPolicy {

    @Bean
    ObservationPredicate skipNoisyPolling() {
        return (name, context) ->
                !"diagnostics.noisy.poll".equals(name);
    }
}
~~~

Spring Boot đăng ký các bean `ObservationPredicate` vào `ObservationRegistry` được auto-configure. Có thể thay bean lambda bằng class `@Component implements ObservationPredicate` nếu quy tắc phức tạp hơn.

So sánh chính xác `equals` phù hợp khi muốn loại duy nhất một technical observation name. Đừng dùng `contains("poll")` vì nó có thể loại thêm những observation khác tên chỉ tình cờ chứa chuỗi đó.

**Technical name không phải span display name:** tracing UI có thể sử dụng contextual name hoặc conventions khác. Hãy xác minh tên observation theo API và dữ liệu thực tế, không tự suy ra từ tiêu đề hiển thị.

### 4.2. Đăng ký trực tiếp trong Micrometer

Không dùng Spring Boot auto-configuration thì có thể cấu hình registry:

~~~java
import io.micrometer.observation.ObservationRegistry;

ObservationRegistry registry = ObservationRegistry.create();

registry.observationConfig()
        .observationPredicate((name, context) ->
                !"diagnostics.noisy.poll".equals(name));
~~~

Đây là registry **độc lập**. Trong ứng dụng Spring Boot đã tạo registry gắn metrics/tracing handlers, **đừng tự tạo registry thứ hai chỉ để thêm predicate**. Bean predicate hoặc `ObservationRegistryCustomizer` phù hợp sẽ tránh mất cấu hình handler/exporter của registry hiện có.

### 4.3. Khi nào dùng property thay cho Java?

Nếu cần tắt một nhóm tên theo prefix, Spring Boot hỗ trợ cấu hình:

~~~yaml
management:
  observations:
    enable:
      diagnostics:
        noisy: false
~~~

Với cấu hình này, Spring Boot chặn các observation có tên bắt đầu bằng prefix `diagnostics.noisy` trong phạm vi áp dụng của property.

Điểm khác biệt:

- Property phù hợp quy tắc theo **tên/prefix** và có thể điều chỉnh theo environment.
- Predicate phù hợp quy tắc theo **context** như module identifier hoặc loại invocation.
- Khi kết hợp nhiều quy tắc, hãy kiểm tra tất cả có cùng áp vào observation mong muốn không; một quy tắc chặn là đủ để observation không được báo cáo.

## 5. Lọc theo context của Spring Modulith

### 5.1. Vì sao chỉ so tên không đủ?

Spring Modulith ghi nhận các module-entry observation. Ở Javadoc Spring Modulith **2.2.0**, `ModulithContext.DEFAULT_CONVENTION_NAME` là `module.invocations`.

Một policy như sau là quá rộng nếu chỉ muốn bỏ một method ở module notification:

~~~java
// Ví dụ quá rộng:
return !"module.invocations".equals(name);
~~~

Nhiều module entry có thể chia sẻ cùng technical observation name. Cách này có nguy cơ chặn **toàn bộ** module invocations, làm mất năng lực quan sát kiến trúc.

Trong các phiên bản hỗ trợ `ModulithContext`, context chứa:

- `getModule()`: thông tin `ObservedModule`.
- `getInvocation()`: lời gọi method được instrument.
- `getModule().getIdentifier()`: định danh application module.
- `getModule().isEventListenerInvocation(getInvocation())`: phân biệt event-listener invocation với bean invocation.
- `getModule().getInvokedMethod(getInvocation())`: tên method được công cụ nhận diện.

Như vậy predicate có thể dựa trên **cấu trúc có kiểu dữ liệu**, tránh phụ thuộc hoàn toàn vào tên span.

### 5.2. Ví dụ: lọc bean invocation của notification, giữ listener

Giả sử team muốn bỏ các module-entry observations khi một bean công khai trong `notification` được gọi, nhưng **vẫn giữ** event-listener observations của module này và giữ mọi module khác:

~~~java
package com.acme.shop.observability;

import io.micrometer.observation.ObservationPredicate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.observability.ModulithContext;

@Configuration(proxyBeanMethods = false)
class ModuleObservationPolicy {

    @Bean
    ObservationPredicate skipNotificationBeanEntries() {

        return (name, context) -> {

            if (!(context instanceof ModulithContext modulith)) {
                // Giữ HTTP/client/business observations.
                return true;
            }

            String moduleIdentifier = modulith.getModule()
                    .getIdentifier().toString();

            boolean notification = "notification".equals(moduleIdentifier);

            boolean listener = modulith.getModule()
                    .isEventListenerInvocation(modulith.getInvocation());

            // Chỉ chặn bean invocation thuộc notification.
            return !(notification && !listener);
        };
    }
}
~~~

Ý nghĩa chính xác:

1. Nếu context không thuộc Spring Modulith module observation, predicate trả `true` để không ảnh hưởng tầng khác.
2. Nếu module identifier không là `notification`, giữ lại observation.
3. Nếu notification invocation là event listener, giữ lại.
4. Chỉ bỏ observation của **bean invocation thông thường trong notification**.

**Đây là ví dụ cách dùng API, không phải đề xuất mặc định tắt module notification trong production.** Việc giữ hay bỏ phải xuất phát từ yêu cầu giám sát và rủi ro mất dấu vết ở một điểm vào quan trọng.

### 5.3. Muốn chỉ lọc một method cụ thể

Thay vì chặn mọi bean invocation ở `notification`, thu hẹp thêm bằng method:

~~~java
String invokedMethod = modulith.getModule()
        .getInvokedMethod(modulith.getInvocation());

boolean noisy = "pollStatus".equals(invokedMethod);

return !(notification && !listener && noisy);
~~~

Ở đây là **đoạn điều kiện bổ sung** cho lambda ở trên, chưa phải một class hoàn chỉnh. Hãy xác minh giá trị `getInvokedMethod(...)` theo version thực tế; nếu có overloaded methods hoặc proxy, chỉ so tên có thể chưa đủ để phân biệt. Khi cần phân biệt tuyệt đối, xét `modulith.getInvocation().getMethod()` hoặc hợp đồng cụ thể của phương thức.

### 5.4. Điều kiện về compile classpath

Nếu Java code import `ModulithContext`, dependency API phải nằm trên **compile classpath**. Ví dụ Gradle với Spring Boot/Spring Modulith BOM phù hợp:

~~~groovy
dependencies {
    implementation 'io.micrometer:micrometer-observation'
    implementation 'org.springframework.modulith:spring-modulith-observability-api'
    runtimeOnly 'org.springframework.modulith:spring-modulith-starter-insight'
}
~~~

Starter Insight hỗ trợ actuator/observability ở runtime; khai báo `observability-api` bằng `implementation` để trình biên dịch đọc được `ModulithContext`. Kiểm tra tên artifact/package của **phiên bản dự án**; cấu trúc API có thể khác giữa các dòng Spring Modulith.

## 6. Test chứng minh no-op không hủy nghiệp vụ

Một test thuần Micrometer không cần Spring Boot có thể chứng minh rõ hai điều: predicate lọc observation, nhưng lambda nghiệp vụ vẫn chạy.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

class ObservationPredicateTests {

    @Test
    void filteredObservationIsNoopButWorkStillRuns() {

        AtomicInteger handlerStarts = new AtomicInteger();
        AtomicInteger businessCalls = new AtomicInteger();

        ObservationRegistry registry = ObservationRegistry.create();

        registry.observationConfig()
                .observationPredicate((name, context) ->
                        !"diagnostics.noisy.poll".equals(name))
                .observationHandler(
                        new ObservationHandler<Observation.Context>() {

                            @Override
                            public boolean supportsContext(
                                    Observation.Context context) {
                                return true;
                            }

                            @Override
                            public void onStart(
                                    Observation.Context context) {
                                handlerStarts.incrementAndGet();
                            }
                        });

        Observation blocked = Observation.createNotStarted(
                "diagnostics.noisy.poll", registry);

        assertTrue(blocked.isNoop());
        blocked.observe(businessCalls::incrementAndGet);

        Observation allowed = Observation.createNotStarted(
                "checkout.risk-check", registry);

        allowed.observe(businessCalls::incrementAndGet);

        assertEquals(2, businessCalls.get());
        assertEquals(1, handlerStarts.get());
    }
}
~~~

Test chỉ tạo một handler đếm số lần `onStart`. Handler nhận observation được giữ; observation bị predicate từ chối là no-op. Cả hai `observe(...)` vẫn chạy lambda tương ứng.

**Đây là ví dụ kiểm thử để người học sử dụng**, không đồng nghĩa test đã được biên dịch hoặc chạy trong repository của bài học. Kết quả thực tế phải được kiểm chứng với dependency versions của dự án.

## 7. Tác động của predicate đến trace và metrics

Giả sử `order` gọi `inventory` và `notification` trong một request. Nếu predicate chặn notification bean entry, trace có thể thay đổi như sau:

~~~text
Trước:
POST /orders
└── order.complete
    ├── inventory.reserve
    └── notification.pollStatus

Sau:
POST /orders
└── order.complete
    └── inventory.reserve

Logic notification.pollStatus vẫn thực thi trong cả hai trường hợp.
~~~

Những điểm cần hiểu:

- Trace thiếu span `notification` **không có nghĩa** method không được gọi.
- Span ở những công đoạn **bên trong** method bị lọc vẫn có thể được tạo nếu chúng được instrument độc lập; quan hệ parent có thể thay đổi.
- Nếu một timer được tạo bởi handler của chính observation bị chặn, timer đó có thể không có thêm lượt ghi nhận.
- Counter được tạo trực tiếp qua `MeterRegistry` không tự động bị chặn bởi predicate.
- Nếu tracing sampling hoặc exporter cũng thay đổi, không thể quy mọi chênh lệch cho predicate.

### 7.1. Actuator không phải trace viewer

Ở môi trường dev/test, nếu Actuator và permission phù hợp:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info,metrics,modulith"
~~~

~~~bash
curl -i http://localhost:8080/actuator/metrics
curl -i http://localhost:8080/actuator/modulith
~~~

`/actuator/metrics` hiển thị meter Micrometer đã ghi nhận. `/actuator/modulith` công bố metadata **cấu trúc module** của phiên bản đang chạy. Để xác nhận một span cụ thể có bị lọc không, cần hệ thống tracing đã cấu hình exporter/backend, hoặc kiểm thử observation handler như ở mục 6.

### 7.2. Tương tác với Spring Modulith event metrics

Spring Modulith đăng ký các counter domain event publication, chẳng hạn:

- `module.events.published`
- `module.events.published.$moduleIdentifier.$simpleEventTypeName`

Chúng theo dõi **việc phát event**, không phải mọi lần đi vào API module. Predicate lọc `ModulithContext` thường nhằm module invocation observation; không được đồng nhất nó với việc kiểm soát các counter publish. Cũng không được lấy số counter published làm bằng chứng listener xử lý thành công.

## 8. Lọc observation và context propagation là hai vấn đề khác nhau

Khi Spring Modulith xử lý event listener bất đồng bộ, code có thể chạy trên thread khác. Micrometer Context Propagation và việc cấu hình executor là điều kiện quan trọng để giữ liên hệ trace.

| Hiện tượng | Giải thích có thể | Nơi kiểm tra |
|---|---|---|
| Module entry observation no-op | Predicate trả `false` | Logic predicate và context thực nhận |
| Listener có span nhưng trace ID khác | Context chưa được truyền đầy đủ | Executor, propagation, tracing configuration |
| Không có span ở tracing backend nhưng metric còn | Sampling hoặc exporter | Sampling rate, backend, export |
| Không có metric nhưng span có | Meter handler/filter hoặc meter không được đăng ký | ObservationRegistry/MeterRegistry |
| Event counter published tăng nhưng listener trace thiếu | Publish và consume là hai bước, hoặc tracing bị lọc | Publication Registry, logs, predicate, sampling |

**`ObservationPredicate` không tự truyền context qua thread**. Ngược lại, chặn một observation cha có thể thay đổi cấu trúc trace con, nhưng không thay đổi logic listener.

## 9. Các lỗi phổ biến khi dùng ObservationPredicate

### 9.1. Chặn toàn bộ module observations

~~~java
// Sai nếu mục tiêu chỉ là bỏ polling của notification:
return !(context instanceof ModulithContext);
~~~

Mọi observation có `ModulithContext` đều bị loại; module graph vẫn có dependency, nhưng trace mất bằng chứng các tương tác đó.

### 9.2. Chặn tất cả observation khác

~~~java
// Sai khi chỉ muốn lọc module entry:
return context instanceof ModulithContext;
~~~

Code này có thể vô tình loại HTTP, client, database và custom business observations. Hãy trả `true` ngay với context ngoài phạm vi xử lý.

### 9.3. Dựa vào tag chỉ có sau khi stop

`ObservationFilter` có thể gắn thêm key-values ở giai đoạn stop. Predicate chạy tại lúc tạo nên **không thể chắc chắn nhìn thấy các giá trị được thêm về sau**. Đừng lọc theo trạng thái listener “đã thành công” nếu ở thời điểm publish hoặc module entry trạng thái đó chưa tồn tại.

### 9.4. Dùng predicate làm phép đo nghiệp vụ

Predicate không phải callback báo xử lý event thành công. Nếu muốn biết `OrderCompleted` đã làm kho giảm đúng, cần kiểm tra dữ liệu cuối, trace/listener log, Event Publication Registry khi được cấu hình. Observation bị no-op không nói gì về kết quả nghiệp vụ.

### 9.5. Chặn để che duplicate instrumentation

Nếu `@Observed` và Spring Modulith cùng instrument một method, có thể sinh hai span tương tự. Trước tiên kiểm tra annotation, aspects và scope. Thường nên loại/thu hẹp nguồn instrument trùng ngay tại code. Một predicate quá rộng có thể che dấu nhiều module entries thật sự cần quan sát.

### 9.6. Predicate thực hiện I/O hoặc lưu dữ liệu định danh

Không truy vấn database, gọi HTTP, publish event hoặc ghi số liệu nghiệp vụ trong predicate. Nó nên nhanh và không có side effect. Tránh dùng customer ID, token hoặc payload nhạy cảm để log quyết định lọc; nhiều observation được tạo với tần suất rất lớn.

### 9.7. Đọc sai ngữ nghĩa “span không tồn tại”

Trace không có span có thể do:
- Không có lời gọi thật.
- Lời gọi có nhưng instrumentation chưa bật.
- Predicate lọc observation.
- Sampling/exporter/backend bỏ trace.
- Context propagation bị mất.
- Truy vấn sai build, instance hoặc thời gian.

Vì vậy **không suy luận thiếu lời gọi chỉ từ việc thiếu span**.

## 10. Quy trình áp dụng trong một hệ thống nhiều module

Một thay đổi predicate nên được review như thay đổi quan trọng của chính sách observability.

1. **Đo baseline:** xác định span/meter gây nhiễu trên cùng build, kịch bản và khoảng thời gian.
2. **Xác định ranh giới:** đọc module graph và phân biệt module entry với HTTP/client/business step.
3. **Định nghĩa điều kiện hẹp:** theo technical name và context, ưu tiên giữ mọi observation khác.
4. **Xác minh thời điểm dữ liệu:** chỉ dùng thuộc tính có mặt khi observation được tạo.
5. **Kiểm thử no-op:** dùng `Observation.isNoop()` hoặc handler test, đếm số lần gọi nghiệp vụ.
6. **Kiểm chứng trace:** xác nhận chỉ span dự kiến bị loại, các span cần thiết còn.
7. **Kiểm tra metrics độc lập:** phân biệt observation-based meter với direct MeterRegistry counters.
8. **Chạy kịch bản lỗi và async:** không làm mất toàn bộ bằng chứng về listener lỗi hoặc retry.
9. **Lưu thông tin thay đổi:** build ID, rule, mục tiêu, người sở hữu và điều kiện xem xét lại.

### Bảng đối chiếu trước/sau

| Chỉ tiêu | Trước lọc | Sau lọc mong muốn |
|---|---|---|
| Lượt HTTP request thực | 1 | 1 |
| Lượt `order.complete` thực | 1 | 1 |
| Lượt `notification.pollStatus` thực | Ví dụ 2 | Vẫn 2 |
| HTTP observation | Có | Giữ |
| Order module observation | Có | Giữ |
| Notification polling observation | Có | Không tạo hữu hiệu |
| Inventory module observation | Có | Giữ |
| Event published counter | Theo số publish | Không thay đổi vì riêng policy module entry |
| Kết quả DB và business | Đúng yêu cầu | Không đổi |
| Dung lượng trace | Có các span polling | Ít span polling hơn nếu tracing hoạt động |

Bảng là **mục tiêu thực nghiệm**, không phải kết quả được sinh sẵn cho mọi môi trường.

## 11. Case study: inventory “biến mất” khỏi trace

Sau một bản deploy, dashboard vẫn thấy số đơn hàng hoàn tất; `module.events.published` còn tăng. Nhưng hầu hết trace không hiển thị `inventory`, khiến nhóm cho rằng event bị mất.

Nhóm kiểm tra mã phát hiện:

~~~java
@Bean
ObservationPredicate suppressModulith() {
    return (name, context) ->
            !(context instanceof ModulithContext);
}
~~~

Lý do ban đầu là muốn giảm số span của một module không quan trọng. Nhưng predicate chặn **mọi** `ModulithContext`, bao gồm `inventory`, `order` và `notification` nếu chúng được instrument bằng context đó.

Cách xử lý:

1. Thu hẹp điều kiện vào đúng module và method gây nhiễu, cho phép các context còn lại.
2. Kiểm tra số lần thực thi thật qua log có correlation và kết quả transaction.
3. Đối chiếu Event Publication Registry nếu được bật cho transactional listener, cùng trace/span và dữ liệu tồn kho.
4. Ghi rõ thời điểm rule lọc quá rộng có hiệu lực để người đọc dashboard không tưởng rằng hệ thống ngừng gọi module.
5. Chạy lại kịch bản, xác nhận tracing hữu ích và business outcome đều phù hợp.

**Bài học:** chính sách lọc có thể làm giảm khả năng kiểm chứng kiến trúc ở runtime. Không phải thay đổi trong module graph mới làm thay đổi những gì xuất hiện trong trace.

## 12. Bài tập tự thực hành

### Thực hành A: lọc theo tên

Tạo hai observation `diagnostics.noisy.poll` và `checkout.risk-check` trên cùng `ObservationRegistry`. Đăng ký predicate chặn observation đầu.

**Yêu cầu:** kiểm tra `isNoop()`, đếm handler `onStart` và xác nhận cả hai lambda nghiệp vụ vẫn chạy. Dự đoán kết quả trước khi chạy.

### Thực hành B: hai predicate đồng thời

Đăng ký một predicate chặn `diagnostics.noisy.poll`, một predicate chặn `checkout.risk-check`. Tạo cả hai loại observation.

**Yêu cầu:** giải thích vì sao từng observation trở thành no-op dù predicate còn lại có thể trả `true`.

### Thực hành C: lọc theo context của Modulith

Trong ứng dụng có `order`, `inventory`, `notification`, tạo bean predicate ở mục 5.2.

**Yêu cầu:** với các module entry thực sự được instrument, xác minh notification bean invocation bị chặn, nhưng notification event-listener invocation và inventory API invocation được giữ.

### Thực hành D: không đánh đồng telemetry và xử lý nghiệp vụ

Một request có counter `OrderCompleted` tăng một lượt, nhưng trace không có span listener.

**Yêu cầu:** viết ít nhất ba giả thuyết có thể kiểm tra (predicate, sampling, context propagation, listener lỗi, registry chưa cấu hình...) và chọn bằng chứng phù hợp cho từng giả thuyết.

### Thực hành E: chọn đúng công cụ

Đội phát triển muốn: (a) giảm trace volume nhưng vẫn giữ HTTP latency metric; (b) sửa nhãn khu vực trên observation; (c) bỏ hẳn một observation ít giá trị; (d) giới hạn các tag của meter có cardinality cao.

**Gợi ý:** (a) tracing sampler, (b) convention/filter, (c) predicate hoặc config prefix, (d) chỉnh nơi tạo tag và/hoặc MeterFilter.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Predicate trả `false` thì method ở bên trong `Observation.observe(...)` có chạy không?

**Đáp án:** Có. Observation trở thành no-op, nhưng lambda nghiệp vụ vẫn được thực thi.

**Câu 2.** Có hai predicate P1 trả true và P2 trả false. Observation được tạo hữu hiệu không?

**Đáp án:** Không. Tất cả predicate phải cho phép.

**Câu 3.** Tại sao `return !"module.invocations".equals(name)` có thể nguy hiểm?

**Đáp án:** Đây là tên kỹ thuật dùng cho nhiều module entry ở dòng Spring Modulith liên quan; điều kiện có thể chặn quá rộng.

**Câu 4.** Muốn thay đổi tag trước khi handler stop, nên chọn predicate hay filter?

**Đáp án:** `ObservationFilter`; predicate dùng để quyết định tạo hay no-op.

**Câu 5.** Observation bị no-op thì mọi domain-event counter của Spring Modulith đều biến mất?

**Đáp án:** Không thể kết luận như vậy. Counter publish có thể được ghi trực tiếp qua MeterRegistry; phải kiểm tra cơ chế và tên meter thực tế.

**Câu 6.** Trong Spring Boot, có phải luôn cần tự tạo một `ObservationRegistry` mới để đăng ký predicate?

**Đáp án:** Không. Boot hỗ trợ tự đăng ký bean `ObservationPredicate` vào registry auto-configured.

**Câu 7.** Khi không thấy span inventory, có thể suy ra inventory chưa chạy không?

**Đáp án:** Không. Cần xét predicate, instrumentation, sampling/exporter, context propagation và log/dữ liệu nghiệp vụ.

## 14. Checklist review

- [ ] Đã xác định chính xác observation nào cần bỏ và câu hỏi vận hành nào được cải thiện.
- [ ] Predicate chỉ lọc theo thông tin có sẵn lúc tạo observation.
- [ ] Context không thuộc phạm vi lọc được giữ bằng `return true`.
- [ ] Không chặn toàn bộ module entry chỉ để giảm một method gây nhiễu.
- [ ] Không dùng predicate để thay thế business rule, retry policy hoặc transaction handling.
- [ ] Không đặt DB/HTTP I/O hoặc side effect trong `test(...)`.
- [ ] Đã phân biệt predicate với filter, sampler và MeterFilter.
- [ ] Đã xác nhận logic nghiệp vụ vẫn chạy trong test no-op.
- [ ] Đã so tracing và metrics với build, instance và sampling tương đương.
- [ ] Đã xét async listener/context propagation trước khi kết luận span biến mất.
- [ ] Đã ghi lại chính sách lọc và người chịu trách nhiệm để tránh mất thông tin chẩn đoán về sau.

## 15. Ghi nhớ

- **`ObservationPredicate` quyết định tại lúc tạo observation:** `true` cho phép, `false` trả observation no-op.
- Nó **lọc telemetry**, không hủy nghiệp vụ; các `observe(...)` callback vẫn có thể chạy bình thường.
- **Spring Boot tự đăng ký các bean `ObservationPredicate`**, còn cấu hình `management.observations.enable.*` phù hợp khi chỉ muốn lọc theo prefix tên.
- Với Spring Modulith, **`ModulithContext` cho phép lọc theo module/invocation**, tránh dùng chung tên `module.invocations` để loại hàng loạt.
- **`ObservationFilter`, `MeterFilter` và tracing sampler** có nhiệm vụ khác nhau; chọn đúng cấp lọc.
- **Thiếu span không chứng minh thiếu lời gọi.** Kiểm chứng bằng nhiều nguồn: module graph, Actuator, metrics, trace, publication state và kết quả dữ liệu.

## Tài liệu tham khảo

1. [Micrometer — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html) — Cơ chế predicates, filters, handlers và observation no-op.
2. [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html) — ObservationRegistry và lifecycle.
3. [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html) — Bean `ObservationPredicate`, prefix configuration, metrics/tracing.
4. [Spring Boot 3.5 — Observability](https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html) — Tham chiếu với các ứng dụng Spring Boot 3.5.
5. [Spring Modulith — Production-ready Features](https://docs.spring.io/spring-modulith/reference/production-ready.html) — Module observation và event metrics.
6. [Spring Modulith API — ModulithContext](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithContext.html) — Context, module và default convention name.
7. [Spring Modulith API — ObservedModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ObservedModule.html) — Module identifier và phương thức nhận biết event listener.
8. [Spring Modulith API — ModulithObservations](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/observability/ModulithObservations.html) — Observation documentation ở module entry.

