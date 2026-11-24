# DefaultMeterObservationHandler để sinh phép đo từ Observation

`DefaultMeterObservationHandler` là handler của Micrometer chuyển lifecycle của `Observation` thành meter trong `MeterRegistry`. Khi được đăng ký với `ObservationRegistry`, handler chuyển một operation thành các phép đo theo vòng đời: Timer khi operation dừng, Counter khi operation phát event và LongTaskTimer nếu bật theo dõi công việc đang chạy.

Handler chỉ dùng low-cardinality key-values làm meter tags. High-cardinality key-values không trở thành tag metrics, giúp tránh tạo time series riêng cho từng request hoặc giao dịch. Bài này tập trung vào các meter được tạo, thời điểm tạo, cách đăng ký handler và cách xác minh kết quả.

## 1. Vai trò trong kiến trúc Observation

Observation mô tả một lần thực thi. ObservationRegistry điều phối lifecycle và handler. DefaultMeterObservationHandler chuyển lifecycle đó thành meter trong MeterRegistry.

~~~text
Application code
      |
      v
Observation
      |
      | start / event / error / stop
      v
ObservationRegistry
      |
      v
DefaultMeterObservationHandler
      |
      v
MeterRegistry
      |
      +--> Timer
      +--> Counter cho event
      +--> LongTaskTimer (nếu bật)
      |
      v
Metrics backend
~~~

Code nghiệp vụ chỉ cần tạo Observation và đánh dấu các thuộc tính cần thiết. Handler chịu trách nhiệm ghi nhận duration, event count và trạng thái active. Registry backend quyết định cách lưu và xuất meter, chẳng hạn Prometheus hoặc OTLP.

## 2. Những meter được tạo

| Meter | Tên | Thời điểm | Ý nghĩa |
|---|---|---|---|
| Timer | `<observation-name>` | Khi Observation stop | Số lần hoàn tất và thời gian xử lý |
| Counter | `<observation-name>.<event-name>` | Khi phát Observation event | Đếm số lần event xảy ra |
| LongTaskTimer | `<observation-name>.active` | Khi start, nếu bật | Theo dõi operation đang chạy |

Timer là phép đo chính cho Observation đã hoàn tất. Count của Timer là số lần operation kết thúc. Counter không tự tăng một lần cho mọi Observation; nó chỉ được tạo khi code phát event. LongTaskTimer là tùy chọn, hữu ích khi muốn quan sát tác vụ chưa hoàn tất.

## 3. Đăng ký handler trong Micrometer độc lập

Nếu tự tạo ObservationRegistry, hãy đăng ký handler trước khi tạo Observation:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.ObservationRegistry;

MeterRegistry meterRegistry = new SimpleMeterRegistry();
ObservationRegistry observationRegistry = ObservationRegistry.create();

observationRegistry.observationConfig()
    .observationHandler(
        DefaultMeterObservationHandler.builder(meterRegistry).build()
    );
~~~

`DefaultMeterObservationHandler.builder(meterRegistry).build()` tạo handler dùng MeterRegistry đã cung cấp. Các Observation được tạo bằng observationRegistry này sẽ được gửi qua handler phù hợp.

Nếu dùng Micrometer version cũ, constructor và builder API có thể khác. Hãy kiểm tra API theo phiên bản được quản lý bởi BOM của dự án; tránh trộn các phiên bản micrometer-core với registry backend.

Không tạo một ObservationRegistry mới trong mỗi request. Registry nên có vòng đời cấp ứng dụng để các Observation dùng chung handler và cấu hình.
## 4. Spring Boot thường đã đăng ký handler

Khi dùng Spring Boot Actuator cùng MeterRegistry, Spring Boot tự cấu hình ObservationRegistry và DefaultMeterObservationHandler để tạo metrics. Ứng dụng chỉ cần inject ObservationRegistry:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ObservationRegistry observationRegistry;
    private final ProductRepository repository;

    public CatalogService(ObservationRegistry observationRegistry,
                          ProductRepository repository) {
        this.observationRegistry = observationRegistry;
        this.repository = repository;
    }

    public Product findProduct(String productId) {
        return Observation.createNotStarted(
                "catalog.product.lookup",
                observationRegistry
            )
            .lowCardinalityKeyValue("operation", "lookup")
            .observe(() -> repository.findById(productId)
                .orElseThrow(ProductNotFoundException::new));
    }
}
~~~

Nếu Spring Boot đã cung cấp handler, không đăng ký thêm một DefaultMeterObservationHandler cho cùng registry. Handler trùng có thể ghi nhận cùng lifecycle nhiều lần. Với custom ObservationRegistry, hãy xác minh handler thực tế đã được gắn hay chưa.

Dependency thường dùng:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("io.micrometer:micrometer-registry-prometheus")
}
~~~

Actuator và registry backend cung cấp hạ tầng metrics. DefaultMeterObservationHandler tạo meter trong registry; nó không tự mở endpoint scrape hoặc cấu hình Prometheus server.

## 5. Timer được ghi khi Observation dừng

Khi Observation dừng, handler tạo hoặc lấy Timer có tên bằng Observation name, gắn low-cardinality values và ghi thời gian từ start tới stop.

~~~java
Observation observation = Observation.createNotStarted(
        "catalog.product.lookup",
        observationRegistry
    )
    .lowCardinalityKeyValue("region", "ap-southeast-1")
    .lowCardinalityKeyValue("result", "found");

observation.start();
repository.findById(productId);
observation.stop();
~~~

Timer có thể được tìm theo tên và tags:

~~~java
Timer timer = meterRegistry.get("catalog.product.lookup")
    .tag("region", "ap-southeast-1")
    .tag("result", "found")
    .tag("error", "none")
    .timer();
~~~

Timer thường có tag `error=none` khi không có lỗi. Nếu Observation được đánh dấu lỗi, giá trị error là tên class của exception được ghi nhận. Vì vậy, khi query meter, hãy tính đến tag error do handler thêm vào.

Timer chưa ghi nhận lần đang chạy cho tới khi Observation dừng. Nếu cần thấy tác vụ active, bật LongTaskTimer.

## 6. Event tạo Counter

Code có thể phát event trong lifecycle của Observation:

~~~java
Observation observation = Observation.createNotStarted(
        "catalog.product.lookup",
        observationRegistry
    )
    .lowCardinalityKeyValue("region", "ap-southeast-1");

observation.start();
observation.event(Observation.Event.of("cache.miss"));
observation.event(Observation.Event.of("fallback.used"));
observation.stop();
~~~

Handler tạo Counter theo tên ghép Observation name và event name:

- `catalog.product.lookup.cache.miss`
- `catalog.product.lookup.fallback.used`

Mỗi lần phát event, Counter tương ứng tăng một lần. Các low-cardinality values có sẵn tại thời điểm phát event được dùng làm tags.

Tên event phải ổn định và có cardinality thấp. Không ghép request ID, order ID hoặc dữ liệu đầu vào vào event name. Một event name thay đổi theo từng request sẽ tạo nhiều meter không cần thiết.
## 7. LongTaskTimer cho operation đang chạy

Timer thông thường chỉ ghi thời gian khi Observation dừng. Với operation có thể kéo dài nhiều phút, dashboard chỉ nhìn Timer sẽ không thấy lần chạy hiện tại cho đến khi nó hoàn tất.

Có thể bật LongTaskTimer trong builder:

~~~java
DefaultMeterObservationHandler handler =
    DefaultMeterObservationHandler.builder(meterRegistry)
        .includeActiveObservationLongTaskTimer(true)
        .build();

observationRegistry.observationConfig()
    .observationHandler(handler);
~~~

Đoạn đăng ký này dành cho registry độc lập hoặc cấu hình mà handler mặc định chưa được gắn. Trong Spring Boot, chỉ bật tùy chọn này khi bạn đang chủ động thay thế/cấu hình handler hiện có; không thêm một handler thứ hai bên cạnh DefaultMeterObservationHandler auto-configured.

Khi Observation bắt đầu, handler tạo LongTaskTimer có tên `<observation-name>.active`. Trong lúc operation chạy, meter này cung cấp số task đang hoạt động và thời lượng active; khi Observation dừng, sample tương ứng được kết thúc.

~~~java
Observation observation = Observation.createNotStarted(
        "report.export",
        observationRegistry
    )
    .lowCardinalityKeyValue("format", "csv")
    .start();

// Trong khi export chạy, report.export.active theo dõi task đang hoạt động.
reportExporter.export(report);
observation.stop();
~~~

LongTaskTimer chỉ nhận low-cardinality values có sẵn tại thời điểm Observation start. Tag được thêm sau start không xuất hiện trên active timer. Hãy thêm tag cần thiết trước khi gọi start().

Bật LongTaskTimer làm tăng số meter. Chỉ bật cho operation dài như export lớn, batch processing hoặc tác vụ nền cần theo dõi khi chưa hoàn tất.

## 8. Low-cardinality và high-cardinality

DefaultMeterObservationHandler chỉ đưa low-cardinality key-values vào meter tags. High-cardinality key-values không được đưa vào metrics.

~~~java
Observation.createNotStarted("payment.authorize", observationRegistry)
    .lowCardinalityKeyValue("provider", "primary")
    .lowCardinalityKeyValue("outcome", "success")
    .highCardinalityKeyValue("payment.reference", paymentReference)
    .observe(() -> paymentGateway.authorize(payment));
~~~

Timer có thể mang tag provider và outcome. `payment.reference` không trở thành meter tag. Tracing handler có thể dùng high-cardinality value này cho span nếu chính sách telemetry cho phép.

Dùng enum, route template, status group hoặc allowlist cho low-cardinality values. Không đưa user ID, order ID, request ID hoặc URL đầy đủ vào nhóm này. Với active LongTaskTimer, cần có các low-cardinality values trước thời điểm start.

## 9. Xử lý lỗi

Khi code gọi error(exception), handler ghi nhận lỗi trong Observation context. Timer khi stop sẽ mang tag error là tên class exception. Nếu không có lỗi, tag là none.

~~~java
Observation observation = Observation.start(
    "payment.authorize",
    observationRegistry
);

try (Observation.Scope scope = observation.openScope()) {
    paymentGateway.authorize(payment);
}
catch (RuntimeException error) {
    observation.error(error);
    throw error;
}
finally {
    observation.stop();
}
~~~

Với observe(), Observation API quản lý lifecycle và đánh dấu lỗi khi callback ném exception. Khi tự quản lý start/stop, hãy gọi error() trước stop().

Không dùng exception message làm tag vì message có thể chứa ID, URL hoặc dữ liệu đầu vào. Nếu cần phân nhóm lỗi nghiệp vụ, dùng low-cardinality value như outcome=timeout hoặc outcome=rejected.

## 10. Cấu hình histogram cho Timer

Timer được tạo bởi DefaultMeterObservationHandler vẫn nằm trong MeterRegistry, nên có thể nhận cấu hình distribution của registry. Với Spring Boot, cấu hình theo tên Observation:

~~~properties
management.metrics.distribution.percentiles-histogram.catalog.product.lookup=true
management.metrics.distribution.slo.catalog.product.lookup=100ms,300ms,1s
~~~

Tên property và cách bind phụ thuộc phiên bản Boot. Tên meter trong registry là Observation name; tên xuất ở backend có thể được chuẩn hóa theo naming convention.

Chỉ bật histogram khi cần phân tích phân phối. Bucket nhân số series theo tổ hợp tags và số instance. Nếu Observation có nhiều tags hoặc nhiều event name, cần tính ngân sách cardinality trước khi triển khai.

## 11. Kiểm thử handler

Dùng SimpleMeterRegistry để kiểm tra Timer và event Counter:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DefaultMeterObservationHandlerTest {

    @Test
    void createsTimerAndEventCounter() {
        SimpleMeterRegistry meters = new SimpleMeterRegistry();
        ObservationRegistry observations = ObservationRegistry.create();

        observations.observationConfig().observationHandler(
            DefaultMeterObservationHandler.builder(meters).build()
        );

        Observation observation = Observation.createNotStarted(
                "catalog.lookup",
                observations
            )
            .lowCardinalityKeyValue("region", "ap-southeast-1");

        observation.start();
        observation.event(Observation.Event.of("cache.miss"));
        observation.stop();

        Timer timer = meters.get("catalog.lookup")
            .tag("region", "ap-southeast-1")
            .tag("error", "none")
            .timer();

        Counter eventCounter = meters.get("catalog.lookup.cache.miss")
            .tag("region", "ap-southeast-1")
            .counter();

        assertEquals(1L, timer.count());
        assertEquals(1.0, eventCounter.count());
    }
}
~~~

Kiểm tra tag lỗi khi operation ném exception:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry observations = ObservationRegistry.create();
observations.observationConfig().observationHandler(
    DefaultMeterObservationHandler.builder(meters).build()
);

assertThrows(IllegalStateException.class, () ->
    Observation.createNotStarted("payment.authorize", observations)
        .observe(() -> {
            throw new IllegalStateException("gateway unavailable");
        })
);

Timer timer = meters.get("payment.authorize")
    .tag("error", "IllegalStateException")
    .timer();
assertEquals(1L, timer.count());
~~~

Kiểm thử LongTaskTimer riêng:

~~~java
SimpleMeterRegistry meters = new SimpleMeterRegistry();
ObservationRegistry observations = ObservationRegistry.create();

DefaultMeterObservationHandler handler =
    DefaultMeterObservationHandler.builder(meters)
        .includeActiveObservationLongTaskTimer(true)
        .build();

observations.observationConfig().observationHandler(handler);

Observation observation = Observation.createNotStarted(
        "report.export",
        observations
    )
    .lowCardinalityKeyValue("format", "csv")
    .start();

assertEquals(
    1,
    meters.get("report.export.active")
        .tag("format", "csv")
        .longTaskTimer()
        .activeTasks()
);

observation.stop();

assertEquals(
    0,
    meters.get("report.export.active")
        .tag("format", "csv")
        .longTaskTimer()
        .activeTasks()
);
~~~

Mỗi test nên tạo registry riêng và chỉ đăng ký một handler cho mục đích kiểm thử. Nếu chạy trong Spring Boot context đã có default handler, không thêm handler thứ hai vào cùng registry.

## 12. Chẩn đoán khi không thấy meter

Nếu Observation chạy nhưng không thấy Timer hoặc Counter, kiểm tra:

1. Observation dùng đúng ObservationRegistry đã đăng ký handler.
2. DefaultMeterObservationHandler thực sự có trong registry.
3. Observation đã start và stop; Timer chỉ ghi khi stop.
4. Event được phát bằng Observation.event(); không có event thì không có event Counter.
5. Tên meter và low-cardinality tags đúng với query.
6. Observation không bị ObservationPredicate chuyển thành no-op.
7. MeterFilter không từ chối meter hoặc đổi tên meter.
8. Registry backend và endpoint/export hoạt động.

Trong Spring Boot, kiểm tra auto-configuration trước khi tự thêm handler. Một ObservationRegistry được tạo thủ công có thể không có handler của registry mặc định.

Nếu meter có trong /actuator/metrics nhưng không xuất hiện trên Prometheus, hãy kiểm tra exporter, scrape và naming convention thay vì kết luận handler không hoạt động.

## 13. Các lỗi thường gặp

- **Không đăng ký handler:** Observation lifecycle không tạo meter.
- **Đăng ký handler hai lần:** cùng một Observation có thể bị ghi nhận trùng.
- **Chờ Timer trước stop:** Timer hoàn tất được ghi khi Observation dừng.
- **Nghĩ mọi Observation tự tăng Counter:** Counter chỉ được tạo khi phát event.
- **Bật LongTaskTimer không cần thiết:** số meter và chi phí tăng.
- **Thêm tag sau start:** active timer không nhận tag đó.
- **Đưa high-cardinality values vào custom metrics handler:** time series có thể bùng nổ.
- **Không gọi error() khi quản lý lifecycle thủ công:** Timer có thể mang error=none.
- **Dùng exception message làm tag:** cardinality tăng và có thể lộ dữ liệu.
- **Bật histogram quá rộng:** bucket và series tăng đáng kể.
- **Đăng ký handler thủ công trong Spring Boot mà không kiểm tra:** có thể trùng với handler auto-configured.

## 14. Checklist triển khai

- [ ] Dùng một ObservationRegistry có vòng đời cấp ứng dụng.
- [ ] Xác minh DefaultMeterObservationHandler đã được đăng ký.
- [ ] Không thêm handler trùng auto-configuration.
- [ ] Đặt Observation name ổn định.
- [ ] Chỉ dùng low-cardinality values làm meter tags.
- [ ] Dùng event name ổn định và hữu hạn.
- [ ] Hiểu Timer được ghi khi stop và Counter tăng khi phát event.
- [ ] Chỉ bật LongTaskTimer khi cần quan sát operation đang chạy.
- [ ] Thêm tags cần thiết trước start nếu dùng LongTaskTimer.
- [ ] Gọi error() khi tự quản lý lifecycle và operation thất bại.
- [ ] Cấu hình histogram qua MeterRegistry hoặc Spring Boot khi cần.
- [ ] Kiểm thử Timer, event Counter, error tag và active task.
- [ ] Kiểm tra MeterFilter, endpoint và backend khi không thấy metrics.

DefaultMeterObservationHandler chuyển Observation thành metrics theo lifecycle: Timer cho operation hoàn tất, Counter cho event được phát và LongTaskTimer cho operation đang chạy khi bật. Handler chỉ dùng low-cardinality values làm meter tags. Trong Spring Boot, hãy tận dụng handler đã được auto-configure; với ứng dụng Micrometer độc lập, đăng ký handler rõ ràng trên ObservationRegistry.

## Tài liệu tham khảo

- [Micrometer Observation Components — DefaultMeterObservationHandler](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Spring Boot Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Spring Boot Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html)



