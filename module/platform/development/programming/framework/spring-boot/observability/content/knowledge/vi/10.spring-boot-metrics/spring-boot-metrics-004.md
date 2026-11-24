# Global registry trong Spring Boot Metrics: cách hoạt động, cấu hình và rủi ro

> **Chương:** Spring Boot metrics  
> **Bài:** Global registry  
> **Module:** `SPRING_BOOT_OBSERVABILITY` — Thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing. Học propagation ngữ cảnh, tag/cardinality, exporter, sampling và liên kết tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trên môi trường thực.

## 1. Global registry giải quyết bài toán gì?

Một thư viện Java muốn đo số lần gửi thông điệp, nhưng không muốn buộc tất cả ứng dụng sử dụng thư viện phải truyền một đối tượng `MeterRegistry` qua mọi constructor. Micrometer cung cấp một điểm truy cập tĩnh:

~~~java
import io.micrometer.core.instrument.Metrics;

Metrics.counter("library.messages.sent", "result", "success")
       .increment();
~~~

Lệnh này tạo hoặc lấy một `Counter` thông qua **global registry** của Micrometer. Thư viện chỉ cần phụ thuộc vào API Micrometer; môi trường chạy quyết định registry cụ thể nào nhận dữ liệu.

Trong ứng dụng Spring Boot, metrics thường được quản lý thông qua **`MeterRegistry` bean** được inject bằng dependency injection. Khi được auto-configuration hỗ trợ, những registry đó còn có thể được nối với global registry. Vì vậy hai hình thức API có thể cùng tồn tại:

~~~java
// Phong cách tĩnh:
Metrics.counter("demo.events", "result", "ok").increment();

// Phong cách Spring injection:
meterRegistry.counter("demo.events", "result", "ok").increment();
~~~

Điểm đáng chú ý: hai lệnh trên **không có nghĩa** đây là hai backend khác nhau. Trong một cấu hình Spring Boot phổ biến, cả hai có thể chạm tới cùng một registry đích. Nếu cùng gọi `increment()` cho **một sự kiện**, bạn đã đo sự kiện đó hai lần.

**Mục tiêu học tập:** hiểu `Metrics.globalRegistry` là gì, nó khác `MeterRegistry` bean ở đâu, Spring Boot kết nối hai phía như thế nào, cách bật/tắt việc đăng ký vào global, lúc nào nên dùng API tĩnh, và cách kiểm tra những lỗi thực tế như số liệu bị nhân đôi, thiếu metric, nhầm registry hoặc ô nhiễm trạng thái trong tests.

## 2. Các registry và API cần phân biệt

| Khái niệm | Bản chất | Dùng để làm gì? |
| --- | --- | --- |
| `MeterRegistry` | Giao diện/kiểu nền cho quản lý meters | Đăng ký và sử dụng `Counter`, `Gauge`, `Timer`, `DistributionSummary`, `LongTaskTimer` |
| `Metrics.globalRegistry` | Một `CompositeMeterRegistry` **tĩnh, dùng chung trong JVM** | Điểm tập hợp cho API tĩnh `Metrics.counter(...)`, `Metrics.timer(...)`... |
| `CompositeMeterRegistry` | Registry chuyển phép đo tới một hoặc nhiều registry con | Xuất cùng một dữ liệu đo tới nhiều backend phù hợp |
| `PrometheusMeterRegistry` | Registry triển khai cho Prometheus | Tạo nội dung metric để Prometheus scrape |
| Registry OTLP hoặc registry khác | Triển khai cho backend khác | Gửi hoặc phơi bày dữ liệu theo cơ chế của backend đó |
| `ObservationRegistry` | Registry của **Micrometer Observation** | Điều phối `Observation`, convention, predicate, filter và `ObservationHandler` |
| Tracer và exporter | Thành phần của distributed tracing | Tạo, lấy mẫu và xuất spans; truyền trace context |

Một số nhầm lẫn thường gặp:

- **Global registry không phải server giám sát toàn công ty.** Nó là đối tượng tĩnh trong **một JVM**. Mỗi tiến trình/instance có global registry của chính mình; không có sự chia sẻ state trực tiếp giữa các pod.
- **Global registry không phải exporter.** Nó giữ các meter và ủy quyền đo lường cho các registry con. Prometheus, OTLP hoặc backend khác nằm ở những lớp tiếp theo.
- **Global registry của Metrics không phải global ObservationRegistry.** `Metrics.counter(...)` là API metrics, còn `Observation.createNotStarted(..., observationRegistry)` sử dụng vòng đời Observation và handlers. Cả hai có thể kết thúc ở cùng một `MeterRegistry` nhưng không phải cùng một API.
- **Global registry không tự liên kết trace/log context.** Để kết hợp metrics, logs và distributed tracing cần Micrometer Observation/Tracing, propagation, exporter và hệ thống phân tích phù hợp.

## 3. Kiến trúc: từ Metrics static API đến backend

~~~mermaid
flowchart TB
    subgraph APP["Một tiến trình Spring Boot"]
      A["Thư viện/legacy code dùng Metrics.counter(...)"]
      B["Service Spring inject MeterRegistry"]
      C["Custom Observation + Meter ObservationHandler"]
      D["Metrics.globalRegistry (static CompositeMeterRegistry)"]
      E["MeterRegistry được Spring Boot cấu hình"]
      A --> D
      B --> E
      C --> E
      D -->|"Khi E được đăng ký vào global"| E
    end
    E --> F["PrometheusMeterRegistry"]
    E --> G["Registry backend khác nếu có"]
    F --> H["/actuator/prometheus"]
    H --> I["Prometheus scrape"]
    I --> J["Dashboard và cảnh báo"]
    G --> K["Exporter/backend tương ứng"]
~~~

Sơ đồ là mô hình khái niệm: một số ứng dụng chỉ có một registry, một số ứng dụng có composite registry để ghép nhiều đích; cách tổ chức bean nội bộ do auto-configuration quyết định. Điều cần hiểu là đường gọi **static** và đường gọi **inject** có thể hội tụ về những registry đích giống nhau.

Khi có nhiều backend, một lần `counter.increment()` có thể được đưa tới mỗi registry con để cùng lưu số liệu ở các hệ thống khác nhau. Việc xuất ra hai backend **không mặc nhiên** làm count ở từng backend tăng hai lần; đó là một sự kiện được biểu diễn ở hai nơi. Đếm trùng xảy ra khi cùng một sự kiện bị ghi **hai lần vào cùng phép đo ở cùng backend**, hoặc khi dữ liệu đã được ingest trùng ở lớp thu thập.

### Một ví dụ

Ứng dụng muốn ghi một lần tạo đơn:

~~~java
meterRegistry.counter(
        "orders.created",
        "channel", "web"
).increment();
~~~

Nếu registry đó cũng được nối vào global registry, đoạn sau cũng sẽ tác động tới hệ thống metrics:

~~~java
Metrics.counter(
        "orders.created",
        "channel", "web"
).increment();
~~~

Đặt **cả hai** trong cùng đường xử lý một đơn sẽ làm bộ đếm tăng hai đơn vị cho một lần tạo đơn. Mục tiêu của việc cấu hình global không phải là tự động đo hai lần; đây là do mã nghiệp vụ chủ động gọi hai lần.

## 4. API của Metrics.globalRegistry

Micrometer có lớp tiện ích `io.micrometer.core.instrument.Metrics`, với một global composite registry và các hàm tĩnh truy cập meters.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.Timer;

Counter success = Metrics.counter(
        "jobs.completed",
        "outcome", "success"
);
success.increment();

Timer timer = Metrics.timer(
        "jobs.processing.duration",
        "operation", "import"
);
timer.record(() -> {
    // Thực hiện tác vụ đồng bộ cần đo.
});
~~~

Các lệnh trên không tự khai báo destination. Để metric xuất hiện ở backend thật, phải có một registry phù hợp được nối vào composite, đồng thời backend đó được cấu hình xuất dữ liệu.

### 4.1. Thêm và gỡ registry con

Trong **Java độc lập**, không dùng Spring Boot auto-configuration, có thể đăng ký một registry với global:

~~~java
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry local = new SimpleMeterRegistry();

Metrics.globalRegistry.add(local);
try {
    Metrics.counter("demo.jobs.done", "result", "ok")
            .increment();

    double count = local.get("demo.jobs.done")
            .tag("result", "ok")
            .counter()
            .count();

    System.out.println(count); // Ví dụ trên registry mới: 1.0
} finally {
    Metrics.globalRegistry.remove(local);
    local.close();
}
~~~

`SimpleMeterRegistry` thích hợp cho ví dụ nhỏ hoặc thử nghiệm trong bộ nhớ. Ở đây:

1. `Metrics.globalRegistry.add(local)` thêm registry con để nhận những lần đo tiếp theo từ static API.
2. `Metrics.counter(...)` tra cứu hoặc đăng ký Counter trong global composite.
3. `local.get(...).counter().count()` đọc dữ liệu **từ registry con**, dễ kiểm chứng.
4. `remove(local)` tháo registry con khỏi global để không ảnh hưởng các đoạn code khác trong cùng JVM.
5. `close()` giải phóng tài nguyên của registry do ví dụ tự tạo.

**Trong Spring Boot đã có auto-configuration**, thường không cần viết đoạn `add(...)` thủ công này. Nếu tự thêm một registry mà Boot đã quản lý, sẽ khó hiểu quan hệ ownership và có thể tạo đường xuất trùng hoặc cấu hình không đồng nhất. Hãy xác định registry bean và cấu hình global mặc định trước khi can thiệp.

### 4.2. Thay đổi trạng thái toàn tiến trình

Vì `Metrics.globalRegistry` là biến tĩnh, thay đổi `add/remove` ảnh hưởng đến **mọi code trong cùng JVM** sử dụng API `Metrics.*`. Đây là lý do việc “dọn sạch global registry” trong một unit test có thể làm hỏng test khác đang chạy song song.

Nếu một đoạn code sở hữu registry riêng, chỉ tháo registry chính nó đã thêm. Không gọi các thao tác xóa toàn bộ global trong ứng dụng/shared test suite khi không quản lý toàn bộ vòng đời tiến trình.

## 5. Global registry trong Spring Boot auto-configuration

Với **Spring Boot 3.x** có Micrometer/Actuator, Spring Boot tự cấu hình `MeterRegistry` dựa trên dependency và property hiện có. Theo cách tích hợp thông dụng của Spring Boot 3.x, các registry do Boot auto-configure được **thêm vào global static composite** của `Metrics` theo mặc định; có thể tắt hành vi này bằng:

~~~yaml
management:
  metrics:
    use-global-registry: false
~~~

Đây là property **kiểm soát việc nối registry do Spring Boot cấu hình vào global `Metrics`**. Nó không có nghĩa là vô hiệu hóa toàn bộ metrics trong Spring Boot.

Sự khác biệt cần nhớ:

| Trạng thái | `MeterRegistry` được inject vào bean | `Metrics.counter(...)` static |
| --- | --- | --- |
| Global được nối với registry Spring Boot | Đo qua registry bean | Có thể cùng ghi tới registry đích đó |
| `management.metrics.use-global-registry=false` | Vẫn hoạt động qua registry bean nếu metrics được cấu hình | Không còn tự động ghi vào registry bean đó qua global; chỉ hoạt động với registry khác nếu ai đó đã đăng ký vào global |
| Không có registry đích tương ứng | Không có backend đích để xuất | Global composite trống không xuất dữ liệu hữu ích |

**Phạm vi phiên bản:** cách đặt property trên được minh họa cho Spring Boot 3.x. Khi dùng Spring Boot phiên bản khác, hãy kiểm tra tài liệu cấu hình/metadata của phiên bản đang dùng trước khi sao chép, vì API và auto-configuration có thể thay đổi.

### Khi nào nên đặt `use-global-registry: false`?

Có thể phù hợp khi tổ chức muốn **mọi mã ứng dụng ghi metrics thông qua `MeterRegistry` do Spring inject**, và chủ động không dùng đường static toàn cục. Những lý do thường gặp là:

- Dễ cô lập test vì các service chỉ phụ thuộc vào registry được truyền vào.
- Giảm sự phụ thuộc vào trạng thái toàn JVM giữa module, thư viện và nhiều application context.
- Làm rõ trách nhiệm cấu hình registry, common tags, filters và exporter.
- Tránh những metrics phát sinh ngoài sự kiểm soát khi thư viện gọi `Metrics.*` tĩnh.

Tuy nhiên, nếu một thư viện đang dựa vào `Metrics.counter(...)`, tắt global mà chưa thay đổi thư viện hoặc cấu hình đăng ký có thể khiến **metrics của thư viện biến mất khỏi registry Spring Boot**. Cần kiểm tra những nơi dùng static API trước khi bật property này trong production.

Không coi việc tắt global là giải pháp cho mọi vấn đề đếm trùng: nếu code service tự gọi `meterRegistry.counter(...).increment()` hai lần, count vẫn sai. Vẫn phải sửa số lần instrument tại boundary nghiệp vụ.

## 6. Thực hành Spring Boot: MeterRegistry được inject

Với mã Spring Boot do nhóm phát triển sở hữu, nên **ưu tiên constructor injection** để registry trở thành dependency tường minh, dễ kiểm soát và dễ test.

### 6.1. Dependency Maven

Ví dụ với Spring Boot 3.x quản lý dependency qua BOM/parent:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

`spring-boot-starter-actuator` cung cấp tích hợp quản trị và metrics. `micrometer-registry-prometheus` thêm registry xuất dữ liệu kiểu Prometheus. Các runtime dependency khác nhau có thể tạo backend khác; đây chỉ là cấu hình minh họa.

### 6.2. Cấu hình `application.yml`

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-service
    use-global-registry: true
~~~

Trong ví dụ:

- `metrics` là endpoint khám phá meter theo tên và tags; `prometheus` là endpoint cho exporter khi có registry phù hợp.
- `application=order-service` là **common tag** để phân biệt ứng dụng ở backend nhiều dịch vụ.
- `use-global-registry: true` được viết tường minh để minh họa quan hệ với static global trong Spring Boot 3.x. Khi muốn cách ly API static, đổi thành `false` sau khi đã rà soát nơi dùng `Metrics.*`.
- Nên giới hạn network/authorization cho Actuator endpoints, nhất là ở production; không mở cổng quản trị công khai chỉ vì muốn scrape dễ dàng.

### 6.3. Service dùng registry đã được Spring quản lý

~~~java
package example.orders;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {
    private final MeterRegistry meterRegistry;

    public CheckoutService(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
    }

    public void checkout(Runnable operation) {
        Timer.Sample sample = Timer.start(meterRegistry);
        String outcome = "success";

        try {
            operation.run();
        } catch (RuntimeException | Error ex) {
            outcome = "error";
            throw ex;
        } finally {
            sample.stop(
                Timer.builder("orders.checkout.duration")
                    .description("Duration of checkout attempts")
                    .tag("outcome", outcome)
                    .register(meterRegistry)
            );
        }
    }
}
~~~

Một lần gọi `checkout(...)` ghi **một sample thời lượng** vào Timer theo kết quả thực tế. `outcome` có hai giá trị hữu hạn nên phù hợp metrics tags. `finally` đảm bảo ghi phép đo cả khi code nghiệp vụ thất bại trên đường xử lý thông thường.

Timer tự ghi số lần qua `count` của nó; không cần thêm Counter thứ hai chỉ để đếm cùng số lần nếu không có mục đích tách riêng. Nếu cần một Counter nghiệp vụ khác, định nghĩa rõ semantics: `orders.created` là số đơn **thật sự được tạo thành công**, khác `orders.checkout.duration` là số lần **thử checkout**.

Với xử lý bất đồng bộ, không dừng Timer ngay khi trả về future nếu mục đích là đo đến khi công việc hoàn tất; dùng callback hoàn thành và propagation phù hợp.

## 7. So sánh cách gọi static với dependency injection

| Tiêu chí | `Metrics.counter(...)` global | Inject `MeterRegistry` |
| --- | --- | --- |
| Cách lấy registry | Thông qua trạng thái tĩnh JVM | Constructor parameter hoặc Spring bean |
| Mức ghép với Spring | Có thể dùng ngoài Spring | Rõ ràng phụ thuộc Spring context |
| Test đơn vị | Cần kiểm soát global state và dọn registry tự thêm | Có thể truyền một `SimpleMeterRegistry` riêng cho test |
| Dễ biết backend nào nhận dữ liệu | Phải xem registry nào đã gắn vào global | Biết registry được inject hoặc composite bean của ứng dụng |
| Dùng trong thư viện đơn giản | Tiện khi không thể inject registry | Tốt nếu API thư viện cho phép cung cấp registry |
| Rủi ro | Trạng thái tĩnh dùng chung, khởi tạo sớm, phụ thuộc auto-registration | Cần truyền dependency theo thiết kế |
| Chia sẻ cùng bộ metrics | Có thể, nếu global chứa registry được inject | Có thể, tùy cấu hình global/composite |

### Quy tắc chọn

- **Mã nghiệp vụ Spring Boot mới:** ưu tiên inject `MeterRegistry` hoặc dùng `ObservationRegistry` khi cần instrument đồng thời metrics và tracing.
- **Thư viện dùng Micrometer nhưng không phụ thuộc Spring:** static `Metrics.*` có thể là lựa chọn tiện, song nên cân nhắc cho phép caller cấp registry thay vì buộc dựa vào global.
- **Code legacy đang dùng static:** hiểu nó được nối vào backend nào trước khi đổi config. Khi refactor sang injection, cần bỏ lời gọi static cũ tại cùng điểm instrument để tránh đo hai lần.
- **Nhiều ứng dụng/test context trong một JVM:** hạn chế global state hoặc quản lý lifecycle cẩn thận.

Global registry không tự xấu hoặc sai. Nó là một công cụ có **phạm vi JVM** và điều kiện sử dụng riêng. Điều quan trọng là biết rõ ai sở hữu registry, ai đăng ký nó, và metric được ghi đúng mấy lần.

## 8. Điều gì xảy ra nếu global registry chưa có registry con?

Đây là một hành vi dễ làm mất dữ liệu ở giai đoạn khởi động ứng dụng. Xem code:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Metrics;

public final class EarlyMetrics {
    private static final Counter STARTED =
            Metrics.counter("service.start.attempts");

    public static void markStarted() {
        STARTED.increment();
    }
}
~~~

Nếu lớp này được khởi tạo và `markStarted()` được gọi **trước khi bất kỳ registry con nào được thêm vào global**, các phép đo thực hiện trong khoảng global composite chưa có registry đích sẽ không có nơi tiếp nhận; chúng không được phát lại như những sự kiện lịch sử khi registry mới xuất hiện.

Khi một registry được thêm sau đó, các phép đo mới có thể được gửi tiếp theo cơ chế composite. Nhưng **giá trị đã bị bỏ lỡ không tự xuất hiện trở lại** trên backend.

Trong Spring Boot, các đoạn code tĩnh, static initializer, hook rất sớm ở quá trình bootstrap hoặc thư viện được tải trước khi context sẵn sàng có thể gặp tình huống này. Đừng dùng số đếm lúc khởi động từ global như một nguồn đảm bảo lưu lại chính xác mọi sự kiện trước thời điểm hệ thống metrics sẵn sàng.

Hướng xử lý:

1. Nếu sự kiện cần độ chính xác tuyệt đối, ghi vào hệ thống nghiệp vụ bền vững hoặc event store phù hợp; metrics vốn không phải event log giao dịch.
2. Với mã Spring, instrument tại thời điểm service nhận được `MeterRegistry` và ứng dụng đã khởi tạo phần metrics cần thiết.
3. Nếu bắt buộc dùng static global trong thư viện, chấp nhận và tài liệu hóa khoảng thời gian chưa có registry hoặc cung cấp cơ chế đăng ký sớm có kiểm soát.
4. Không “vá” bằng cách tạo một registry tĩnh mới trong service rồi mặc định cho rằng Boot sẽ sử dụng nó.

## 9. Global registry và CompositeMeterRegistry: nhiều backend có gì khác?

Một `CompositeMeterRegistry` chứa nhiều registry con. Có thể hình dung:

~~~mermaid
flowchart LR
    A["Counter/TIMER qua CompositeMeterRegistry"] --> B["Prometheus registry"]
    A --> C["Registry OTLP hoặc backend khác"]
    B --> D["Prometheus scrape"]
    C --> E["Collector / monitoring backend"]
~~~

Khi một registry con được thêm, composite liên kết các meter theo cách triển khai của Micrometer; từ đó, một lời gọi ghi phép đo mới có thể được chuyển tới các child registry.

Giả sử `orders.checkout.duration` có hai series backend A và backend B. Số liệu trên **mỗi backend** biểu thị cùng những checkout (theo cấu hình). Không cộng toàn bộ hai backend thành số checkout thực tế; đó là hai bản sao của cùng tín hiệu ở hai hệ thống lưu trữ.

### Trường hợp dễ trùng

- **Cùng một source được scrape hai lần** với label khác nhau và dashboard cộng hai target: lỗi thu thập, khác với lỗi global registry.
- **Ứng dụng gọi cả static và injected API để record cùng sự kiện:** lỗi instrumentation; có thể đếm hai lần trong cùng registry đích.
- **Tạo hai Observation handlers làm cùng trách nhiệm meter trên một observation:** lỗi handler registration.
- **Export cùng một metric đến nhiều backend:** thường là chủ đích nếu muốn hai nơi lưu dữ liệu; bản thân nó không là sai số trong từng backend.

Nếu số liệu bất thường, hãy xác định tầng gây trùng trước khi xóa hoặc thay đổi composite, vì sửa sai tầng có thể làm mất dữ liệu giám sát.

## 10. Global registry khác ObservationRegistry và tracing như thế nào?

Spring Boot observability không chỉ có metrics. Với Micrometer Observation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

Observation observation = Observation.createNotStarted(
        "orders.checkout", observationRegistry)
    .lowCardinalityKeyValue("operation", "create")
    .start();

try (Observation.Scope scope = observation.openScope()) {
    performCheckout();
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Đoạn trên sử dụng `ObservationRegistry`, không trực tiếp gọi `Metrics.globalRegistry`. Khi có **Meter ObservationHandler** trong registry, Observation có thể được chuyển thành Timer hoặc metric khác ở `MeterRegistry` tương ứng. Khi có **Tracing ObservationHandler**, cùng Observation có thể tạo span, truyền ngữ cảnh và được export theo tracing pipeline.

Trong khi đó:

~~~java
Metrics.counter("orders.checkout.attempts").increment();
~~~

là một phép đo Counter trực tiếp. Nó **không tự tạo tracing span**, không tạo trace ID và không chuyển current observation sang thread khác. Muốn kết hợp metrics, logs và tracing, cần sử dụng các API và cấu hình tương ứng cho từng tín hiệu.

Một số stack OpenTelemetry có khái niệm global tracer/provider riêng. Đó là **cơ chế khác** với `Metrics.globalRegistry` của Micrometer; không nên dùng từ “global” để suy rằng hai đối tượng liên quan đến nhau hoặc chia sẻ trạng thái.

### Cardinality và sampling

- Meter handler thường dùng low-cardinality tags để chia metric theo các nhóm hữu hạn.
- High-cardinality metadata như `orderId` hoặc `requestId` có thể phù hợp với span/log được kiểm soát, nhưng **không** nên biến thành metric label qua static hay injected `MeterRegistry`.
- Tracing có sampling: chỉ một phần request có thể có trace được xuất. Metrics có thể đếm mọi request mà không giảm theo sampling của tracing.
- Global registry **không thiết lập sampling cho traces** và cũng không tự truyền trace context giữa dịch vụ.

## 11. Xác minh với Spring Boot Actuator

Để kiểm tra global registry được nối với registry Spring Boot hay chưa, có thể tạo một điểm gọi thử rất đơn giản trong môi trường phát triển, rồi đối chiếu metric ở registry đích. Tránh để endpoint kiểm tra kiểu này tồn tại công khai trong production.

Ví dụ một component Spring:

~~~java
import io.micrometer.core.instrument.Metrics;
import org.springframework.stereotype.Component;

@Component
public class GlobalMetricsProbe {
    public void emitOneEvent() {
        Metrics.counter(
                "demo.global.events",
                "source", "static_api"
        ).increment();
    }
}
~~~

Sau khi gọi `emitOneEvent()`, kiểm tra:

~~~bash
curl http://localhost:8080/actuator/metrics
curl http://localhost:8080/actuator/metrics/demo.global.events
curl http://localhost:8080/actuator/prometheus
~~~

Với Prometheus registry được cấu hình, Counter có thể xuất thành series như `demo_global_events_total`. Hãy dựa vào **tên thật ở output**, vì convention của exporter có thể thay đổi tên, suffix và đơn vị.

### Thử nghiệm so sánh hai chế độ

**Chế độ A — dùng global:**

~~~yaml
management:
  metrics:
    use-global-registry: true
~~~

Gọi `emitOneEvent()`, xem Counter có hiện trong registry Boot và exporter hay không.

**Chế độ B — tắt nối global:**

~~~yaml
management:
  metrics:
    use-global-registry: false
~~~

Khởi động lại một tiến trình sạch với cấu hình này, gọi cùng phương thức, rồi kiểm tra registry Boot. Nếu không có registry khác được gắn thủ công vào global, metric từ `Metrics.counter(...)` sẽ **không còn đi qua đường auto-registration** đến registry Boot.

Để đối chiếu, ghi một Counter khác thông qua `MeterRegistry` được inject. Khi global tắt, Counter thông qua injected registry vẫn có thể xuất bình thường. Đây là bằng chứng trực tiếp để phân biệt “global connection” với “metrics đã bị tắt”.

**Lưu ý về triển khai thực tế:** trạng thái global thuộc JVM, nên chạy thử bằng hai tiến trình tách biệt hoặc bảo đảm dọn state đầy đủ; chỉ đổi property trên một object đang chạy không nhất thiết tháo những registry đã được đăng ký từ trước.

## 12. Kiểm tra trong unit test và integration test

### 12.1. Một unit test dùng registry riêng

Khi service nhận `MeterRegistry` qua constructor, có thể thử bằng `SimpleMeterRegistry` riêng mà không cần can thiệp vào global:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();
CheckoutService service = new CheckoutService(registry);

try {
    service.checkout(() -> {
        // Mô phỏng một lần checkout thành công.
    });

    double count = registry.get("orders.checkout.duration")
        .tag("outcome", "success")
        .timer()
        .count();

    if (count != 1.0) {
        throw new AssertionError("Expected exactly one checkout sample");
    }
} finally {
    registry.close();
}
~~~

Đây là kiểm chứng **semantics của phép đo**: một lần thực thi ghi một Timer sample. Không cần khởi động Spring hay exporter để chứng minh logic đó.

### 12.2. Test bắt buộc dùng global

Nếu phải thử thư viện đang dùng static API, tạo registry tạm, thêm vào global và luôn tháo khi xong:

~~~java
import io.micrometer.core.instrument.Metrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

SimpleMeterRegistry registry = new SimpleMeterRegistry();
Metrics.globalRegistry.add(registry);

try {
    Metrics.counter("demo.test.operations", "outcome", "success")
            .increment();

    double actual = registry.get("demo.test.operations")
            .tag("outcome", "success")
            .counter()
            .count();

    if (actual != 1.0) {
        throw new AssertionError("Expected exactly one operation");
    }
} finally {
    Metrics.globalRegistry.remove(registry);
    registry.close();
}
~~~

Chỉ tháo **registry do test tự thêm**. Trong test suite lớn, các bài test chia sẻ JVM và chạy song song vẫn có thể tương tác qua `Metrics.globalRegistry`; khi đó nên cô lập tiến trình hoặc phối hợp việc sử dụng global state.

### 12.3. Integration test trong Spring Boot

Với app đã chạy Spring context, hãy xác nhận cả hai loại đường đi nếu sản phẩm sử dụng chúng:

1. Gọi một service dùng injected `MeterRegistry`, kiểm tra meter xuất hiện qua Actuator hoặc registry test.
2. Gọi thư viện dùng `Metrics.*` và kiểm tra meter có hiện tại registry Boot khi `use-global-registry=true`.
3. Đổi property trong **một context/tiến trình riêng** rồi xác minh metric static không đi vào registry Boot khi global bị tắt.
4. Kiểm tra số lượng sample sau **một workload xác định**, thay vì đoán chỉ từ dashboard đang có traffic nền.
5. Khi cần tracing, kiểm tra Observation/Tracer riêng; các test registry global không chứng minh trace propagation hoặc sampling đã hoạt động.

Theo workflow của module này, bài học cung cấp ví dụ và phương pháp kiểm tra; việc triển khai và chạy các test trên repository thực sẽ thuộc bước thực hành hoặc xác minh chuyên môn riêng.

## 13. Global registry, tags và MeterFilter: cách tránh bùng nổ series

Việc dùng global hay injected registry **không thay đổi nguyên tắc cardinality**. Một Counter được tạo với `userId` làm tag vẫn có thể sinh một series gần như cho mỗi người dùng, bất kể đi qua đường nào.

~~~java
// Tránh: giá trị gần như duy nhất theo mỗi request.
Metrics.counter(
        "orders.requests",
        "requestId", requestId
).increment();

// Phù hợp hơn: một số nhóm kết quả được định nghĩa trước.
Metrics.counter(
        "orders.requests",
        "outcome", "success"
).increment();
~~~

Nếu có 5 status, 8 route template, 3 method và 10 instance, một metric có thể phát sinh tới **5 × 8 × 3 × 10 = 1.200 tổ hợp nhãn** khi mọi tổ hợp xuất hiện. Thêm một ID mới cho mỗi request có thể khiến series tăng theo traffic.

Nên áp dụng:

- **Low-cardinality key–value** cho tags như `outcome=success/error`, `http.method`, route template và tên môi trường ổn định.
- **High-cardinality key–value** cho spans/logs có kiểm soát khi cần điều tra một request; không đưa ID đó qua `Metrics.counter(..., "id", ...)`.
- **Common tags** qua property `management.metrics.tags.*` (trong Spring Boot 3.x) hoặc cấu hình tương thích. Chú ý cùng tên key ở nhiều chỗ có thể dẫn đến dữ liệu không nhất quán.
- **MeterFilter** để giới hạn/đổi tên/chặn meters khi phù hợp, nhưng chính sách tốt nhất là ngăn cardinality cao ngay tại nơi instrument.
- **Histogram có chọn lọc** vì mỗi bộ nhãn có thể tạo nhiều series bucket. Tránh bật cho mọi meter mà không đánh giá chi phí.

Global registry không tự áp dụng một “chính sách tag chung” nào ngoài cấu hình của các registry con; cách thiết lập filter và common tags ở từng registry vẫn quan trọng. Hãy xác minh output tại đích thay vì chỉ nhìn chuỗi tag ở lời gọi Java.

## 14. Các lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| `Metrics.counter(...)` không xuất hiện trên Prometheus | Global chưa có registry con; Boot tắt global; thiếu Prometheus registry/exporter | Xem `use-global-registry`, dependency và output endpoint |
| Service inject registry ghi được nhưng static API không ghi được | Hai đường không nối cùng registry đích | So sánh context config với `Metrics.globalRegistry` |
| Count tăng gấp đôi sau refactor | Code gọi cả static và injected API cho cùng sự kiện | Tìm đúng nơi `increment()/record()` được gọi |
| Có metric trong app nhưng không có trên dashboard | Sai scrape target, path, label hoặc exporter; query không khớp | Kiểm tra `/actuator/prometheus` và target của backend |
| Dữ liệu lúc startup bị thiếu | Static API chạy trước khi registry con được gắn | Kiểm tra thời điểm khởi tạo và lần record đầu |
| Test A tác động tới test B | Cả hai dùng global registry tĩnh cùng JVM | Dùng registry riêng, cleanup registry tự thêm, tránh test song song |
| Đổi config global nhưng metric vẫn xuất hiện | Có code khác tự thêm registry, app chưa restart hoặc context khác | Kiểm tra thực tế registry con và khởi động tiến trình sạch |
| Số series tăng mạnh | Tag chứa ID/URL thực, nhiều histogram buckets | Kiểm tra labels thật, giới hạn cardinality |
| Metrics đúng nhưng trace không có | Tracing bridge, sampler, exporter hoặc propagation chưa sẵn | Kiểm tra tracing pipeline; global metrics không tạo spans |
| Hai backend có cùng metric | Composite fan-out chủ đích | Đếm riêng từng backend, không cộng các bản sao |
| Counter đọc ở registry mới vẫn bằng 0 | Đọc registry không nhận phép đo hoặc record trước khi registry được nối | Đối chiếu registry đích và thứ tự khởi tạo |

### Quy trình khoanh vùng

1. **Xác định nơi code ghi meter:** static `Metrics.*`, injected `MeterRegistry`, hoặc Observation handler.
2. **Xác nhận registry đích:** bean nào được auto-configure, registry nào có trong global composite, backend nào đang dùng.
3. **Kiểm tra lifecycle:** metrics được ghi trước hay sau khi registry đích sẵn sàng; có record trùng tại cùng boundary không?
4. **Kiểm tra tag/name:** cùng tên metric nhưng tags khác có thể bị tổng hợp gây hiểu sai; theo dõi từng tổ hợp labels.
5. **Kiểm tra exporter và backend:** Actuator metrics, Prometheus scrape và truy vấn thực tế.
6. **Nếu liên quan traces/logs:** kiểm tra `ObservationRegistry`, tracing handler, sampler, propagation và log correlation riêng.
7. **Sau sửa:** xác nhận số đếm trên workload có kiểm soát và xem cảnh báo/SLO còn đúng semantics không.

## 15. Tình huống thực tế: mất metrics khi tắt global

**Bối cảnh.** Nhóm phát triển muốn tăng tính kiểm thử nên thêm:

~~~yaml
management:
  metrics:
    use-global-registry: false
~~~

Các metrics HTTP/JVM do Spring Boot quản lý vẫn xuất hiện bình thường, nhưng dashboard số lần xử lý message từ một thư viện Java cũ bỗng trở về 0.

**Điều tra.** Thư viện cũ ghi bằng:

~~~java
Metrics.counter(
        "legacy.messages.processed",
        "outcome", "success"
).increment();
~~~

Trước khi đổi cấu hình, Spring Boot nối registry đích vào global, nên Counter của thư viện đi tới exporter. Sau khi tắt global, ứng dụng không còn tự nối registry Boot với static global. Counter của thư viện vẫn được gọi, nhưng không có đường xuất về cùng backend.

**Khắc phục.** Nhóm chọn một trong hai hướng có chủ đích:

1. Nếu kiểm soát được thư viện, chuyển sang nhận `MeterRegistry` từ ứng dụng hoặc thiết kế một adapter cung cấp registry cho thư viện. Giữ `use-global-registry=false` và kiểm chứng lại.
2. Nếu chưa thể sửa thư viện, giữ auto-connection global trong ứng dụng đó và cô lập các tests/chiến lược sử dụng registry rõ ràng. Chỉ khi có khả năng kiểm soát và đánh giá kỹ mới đăng ký thủ công một registry tương đương.

Sau thay đổi, nhóm dùng một workload message có số lượng xác định, so sánh chênh lệch Counter, kiểm tra labels và exporter, rồi xác nhận dashboard trở lại bình thường.

**Bài học:** tắt việc nối global **không đồng nghĩa tắt MeterRegistry của Spring Boot**. Nhưng những phần code dựa vào static `Metrics.*` có thể mất đường xuất, nên phải rà soát trước khi chuyển cấu hình.

## 16. Bài tập thực hành

### Bài tập A — phân biệt global và registry bean

Một ứng dụng Spring Boot có `MeterRegistry` bean xuất Prometheus và một thư viện dùng `Metrics.counter(...)`.

1. Vẽ đường dữ liệu khi global được nối vào registry Boot.
2. Giải thích vì sao hai lời gọi `increment()` từ static và injected API có thể cùng cộng vào một Counter.
3. Khi đặt `use-global-registry=false`, đo bằng injected registry còn hoạt động không? Vì sao?
4. Nếu cùng một metric được export tới hai backend, có thể kết luận count bị nhân đôi không?

### Bài tập B — thử nghiệm có số lần xác định

Tạo một service có method `submitOrder()`:

- Ghi một Counter `orders.submitted` từ injected `MeterRegistry` khi đơn được tiếp nhận thành công.
- Gửi chính xác 20 đơn trong môi trường không có traffic nền.
- Kiểm tra count tăng chính xác 20 trong registry đích.
- Tạo thử một lời gọi `Metrics.counter(...).increment()` tại cùng chỗ và giải thích vì sao kết quả tăng thêm 20 khi global đã nối tới cùng registry.
- Loại bỏ lời gọi trùng và xác minh semantics đúng.

### Bài tập C — cô lập tests

Viết một unit test dùng `SimpleMeterRegistry` truyền qua constructor. Viết thêm một test bắt buộc dùng `Metrics.globalRegistry`, đăng ký registry riêng với `add(...)` và tháo bằng `remove(...)` trong `finally`. Hãy giải thích vì sao không nên gọi thao tác xóa toàn bộ global state khi có test khác cùng JVM.

### Bài tập D — phân tích sự cố

Môi trường production có `/actuator/metrics/demo.global.events` không xuất hiện sau deploy, nhưng `/actuator/metrics/jvm.memory.used` vẫn có dữ liệu.

Hãy kiểm tra lần lượt: có phát sinh sự kiện thật không, lời gọi dùng static hay injected, `use-global-registry` là gì, global chứa registry nào, exporter có đúng tên metric không, scrape target có hoạt động không và liệu metric có được record trước khi registry sẵn sàng không.

### Câu hỏi tự kiểm tra

1. `Metrics.globalRegistry` có được chia sẻ trực tiếp giữa các container/pod không?
2. `CompositeMeterRegistry` tạo ra nhiều backend thì việc đó có nhất thiết làm count trong mỗi backend bị nhân đôi không?
3. Vì sao constructor injection giúp đơn vị test dễ cô lập hơn static API?
4. Khi thêm registry vào global sau một lần `increment()` trước đó, phép đo cũ có được phát lại không?
5. Điều gì có thể xảy ra nếu cùng một registry được thêm bằng tay trong khi Spring Boot cũng đang cấu hình registry?
6. Vì sao `management.metrics.use-global-registry=false` không đồng nghĩa tắt mọi HTTP/JVM metrics?
7. Global `MeterRegistry` có tự động tạo span hoặc propagate `traceparent` không?
8. Muốn theo dõi một request cụ thể, tại sao không nên đặt `requestId` vào metric label?
9. Khi sử dụng `ObservationRegistry`, thành phần nào thường chuyển một Observation thành metrics?
10. Khi code và exporter đều đúng nhưng dashboard thiếu metric, chặng nào của pipeline cần kiểm tra tiếp?

**Tiêu chí hoàn thành:** phân biệt được global composite với registry bean và ObservationRegistry; giải thích được cơ chế Spring Boot nối registry trong ví dụ 3.x; chọn đúng static/injection theo tình huống; biết xử lý trạng thái tĩnh trong tests, tránh đo trùng, đọc đúng exporter và bảo vệ tag cardinality.

## 17. Ghi nhớ

- `Metrics.globalRegistry` là **CompositeMeterRegistry tĩnh theo JVM**; nó nhận phép đo từ `Metrics.*` và ủy quyền cho registry con đã đăng ký.
- Spring Boot có thể nối những registry tự cấu hình vào global; với Spring Boot 3.x, `management.metrics.use-global-registry=false` tắt auto-connection này nhưng không tắt injected `MeterRegistry`.
- Với mã Spring Boot mới, **constructor injection** thường làm ownership và test rõ ràng hơn; static API tiện khi thư viện không có cách nhận dependency.
- **Một sự kiện chỉ nên được record một lần cho cùng semantics.** Gọi cả static và injected API trong cùng code path có thể nhân đôi count nếu chúng cùng đến một registry đích.
- Khi global chưa có registry con, các sự kiện ghi vào khoảng trống sẽ không tự được phát lại sau khi registry được thêm.
- Global metrics không tự cung cấp tracing, propagation hay log correlation. Dùng `ObservationRegistry` và tracing pipeline thích hợp nếu cần liên kết tín hiệu.
- Hãy xác minh meter trên Actuator/Prometheus thực tế, kiểm soát cardinality, phân biệt lỗi instrumentation với lỗi exporter hoặc scrape, và dọn trạng thái global do test tự thêm.

## Tài liệu tham khảo

- [Micrometer Reference — Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer Reference — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Reference — Observation introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Spring Boot 3.x Reference — Metrics](https://docs.spring.io/spring-boot/docs/3.3.x/reference/html/actuator.html#actuator.metrics)
- [Spring Boot Reference — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)

