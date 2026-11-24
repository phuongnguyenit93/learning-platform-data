# Test custom observation

Một service Spring Boot có custom Observation tên inventory.reserve để đo thời gian giữ hàng. Developer đã thêm low-cardinality tags cho warehouse và outcome, đồng thời ghi exception khi reservation thất bại. Nếu chỉ kiểm tra endpoint trả đúng HTTP status, test chưa chứng minh Observation thực sự được tạo, handler đã nhận đúng context hay metrics/tracing signals có được ghi nhận. Test custom Observation cần kiểm tra lifecycle và dữ liệu telemetry ngay tại ranh giới instrumentation.

Bài **Test custom observation** thuộc chương **Testing observability** của module **SPRING_BOOT_OBSERVABILITY**. Module học cách thiết lập observability cho Spring Boot bằng Micrometer Observation, metrics, logs và distributed tracing; hiểu context propagation, tag/cardinality, exporter, sampling và liên kết các tín hiệu để điều tra lỗi, độ trễ và hành vi ứng dụng trong môi trường thực.

> **Nguyên tắc:** Test Observation bằng registry và handlers dành riêng cho test. Kiểm tra tên operation, context, low/high-cardinality key-values, error và start/stop lifecycle. Nếu cần xác nhận metrics hoặc spans, kiểm tra từng signal qua MeterRegistry/tracing test reporter tương ứng. Không cần gửi telemetry tới Prometheus, OTLP Collector hoặc backend production chỉ để chứng minh code đã instrument đúng.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:
1. Giải thích vì sao custom Observation cần test riêng.
2. Phân biệt test Observation lifecycle với test metrics và tracing exporters.
3. Tạo ObservationRegistry dành riêng cho test.
4. Đăng ký handler để thu thập Observation contexts.
5. Assert tên, contextual name, low/high-cardinality tags và error.
6. Kiểm tra start/stop, scope và exception behavior.
7. Kiểm tra MeterRegistry ghi nhận Timer/Counter từ Observation handlers.
8. Kiểm tra tracing spans bằng test tracer/reporter.
9. Test ObservationPredicate, filters và no-op behavior.
10. Kiểm thử context propagation qua executor/reactive boundary.
11. Phát hiện duplicate observations và metric cardinality regressions.
12. Tránh test phụ thuộc exporter/backend hoặc timing không ổn định.

## 2. Test pyramid cho custom Observation

Một custom Observation có thể được kiểm tra ở nhiều lớp:

| Lớp test | Thành phần | Điều cần chứng minh |
|---|---|---|
| Unit test | ObservationRegistry + test handler | Lifecycle, context, tags, error |
| Metrics test | MeterRegistry + meter handler | Timer/Counter và tag values |
| Tracing test | Test tracer/span reporter | Span name, parent, attributes, error |
| Spring integration test | ApplicationContext + custom bean | Auto-configuration, wiring và proxy |
| End-to-end test | App + Collector/backend test stack | Export protocol, propagation qua process |

Phần lớn logic custom Observation nên được kiểm tra bằng unit/integration tests nhẹ. End-to-end test chỉ cần khi thay đổi exporter, Collector pipeline hoặc propagation protocol; không biến mọi test thành phụ thuộc hạ tầng telemetry.

~~~mermaid
flowchart TD
    A["Custom operation"] --> B["ObservationRegistry"]
    B --> C["Test ObservationHandler"]
    B --> D["MeterObservationHandler"]
    B --> E["TracingObservationHandler"]
    C --> F["Assert context and lifecycle"]
    D --> G["Assert Timer / Counter"]
    E --> H["Assert span and parent"]
~~~

## 3. Thiết kế custom Observation dễ kiểm thử

Ví dụ service dùng ObservationRegistry để instrument một operation:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.stereotype.Service;

@Service
class InventoryReservationService {

    private final ObservationRegistry registry;
    private final InventoryRepository repository;

    InventoryReservationService(
            ObservationRegistry registry,
            InventoryRepository repository) {
        this.registry = registry;
        this.repository = repository;
    }

    Reservation reserve(String warehouse, String sku) {
        return Observation.createNotStarted("inventory.reserve", registry)
                .contextualName("reserve-inventory")
                .lowCardinalityKeyValue("warehouse", warehouse)
                .lowCardinalityKeyValue("operation", "reserve")
                .observe(() -> repository.reserve(warehouse, sku));
    }
}
~~~

Ví dụ minh họa. Trong production, warehouse phải là tập giá trị được kiểm soát; không thêm sku/order/user identifiers vào low-cardinality tags. Nếu repository hoặc framework đã tự tạo Observation cho cùng database call, custom Observation ở đây nên biểu diễn business operation bên ngoài để tránh đếm trùng.

Test cần xác định contract:
- Observation name: inventory.reserve.
- Contextual name: reserve-inventory.
- Low-cardinality key-values: warehouse, operation.
- Terminal behavior: success hoặc exception.
- Handler nào được kỳ vọng nhận Observation.

## 4. Tạo ObservationRegistry riêng cho test

Không nên dùng global registry dùng chung giữa tests vì state và handlers có thể rò rỉ giữa test cases. Tạo registry riêng giúp test xác định rõ handler nào được gọi.

Micrometer cung cấp ObservationRegistry và ObservationHandler APIs. Có thể đăng ký handler đơn giản để ghi nhận lifecycle/context. Một số Micrometer versions cung cấp test utilities như TestObservationRegistry; kiểm tra API của version đang dùng trước khi chọn utility.

Ví dụ handler tự viết:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import java.util.ArrayList;
import java.util.List;

class RecordingObservationHandler
        implements ObservationHandler<Observation.Context> {

    private final List<String> started = new ArrayList<>();
    private final List<String> stopped = new ArrayList<>();

    @Override
    public boolean supportsContext(Observation.Context context) {
        return true;
    }

    @Override
    public void onStart(Observation.Context context) {
        started.add(context.getName());
    }

    @Override
    public void onStop(Observation.Context context) {
        stopped.add(context.getName());
    }

    List<String> started() {
        return started;
    }

    List<String> stopped() {
        return stopped;
    }
}
~~~

Đây là handler minh họa tối giản. Nếu test chạy song song hoặc Observation được ghi từ nhiều threads, dùng collection thread-safe hoặc đồng bộ phù hợp. Với test context chuyên biệt, có thể assert trực tiếp các KeyValues trong context thay vì chỉ lưu name.

## 5. Kiểm tra Observation được start và stop

Ví dụ JUnit test:

~~~java
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class InventoryObservationTest {

    @Test
    void recordsObservationLifecycle() {
        ObservationRegistry registry = ObservationRegistry.create();
        RecordingObservationHandler handler =
                new RecordingObservationHandler();
        registry.observationConfig().observationHandler(handler);

        Observation.createNotStarted("inventory.reserve", registry)
                .observe(() -> "reserved");

        assertThat(handler.started())
                .containsExactly("inventory.reserve");
        assertThat(handler.stopped())
                .containsExactly("inventory.reserve");
    }
}
~~~

Test này chứng minh Observation đi qua start/stop handlers. Nó chưa chứng minh metrics hoặc spans được tạo; các signal đó cần handlers tương ứng.

### 5.1 Kiểm tra lifecycle khi callback ném exception

~~~java
@Test
void stopsObservationWhenOperationThrows() {
    ObservationRegistry registry = ObservationRegistry.create();
    RecordingObservationHandler handler =
            new RecordingObservationHandler();
    registry.observationConfig().observationHandler(handler);

    assertThatThrownBy(() ->
            Observation.createNotStarted("inventory.reserve", registry)
                    .observe(() -> {
                        throw new IllegalStateException("reservation failed");
                    }))
            .isInstanceOf(IllegalStateException.class);

    assertThat(handler.started()).containsExactly("inventory.reserve");
    assertThat(handler.stopped()).containsExactly("inventory.reserve");
}
~~~

Observation API quản lý lifecycle quanh callback; test cần xác nhận stop xảy ra cả success và error path. Nếu code tự gọi start/stop thay vì dùng observe(), cần bảo đảm stop trong finally và không để Observation ở trạng thái mở khi exception xảy ra.

## 6. Assert context và KeyValues

Tên Observation đúng nhưng tags sai vẫn có thể làm dashboard hoặc cardinality bị lỗi. Handler có thể giữ context ở onStart/onStop để test.

Ví dụ kiểm tra context trong handler:

~~~java
@Override
public void onStop(Observation.Context context) {
    assertThat(context.getName()).isEqualTo("inventory.reserve");
    assertThat(context.getContextualName()).isEqualTo("reserve-inventory");
    assertThat(context.getLowCardinalityKeyValues())
            .contains(KeyValue.of("warehouse", "north"));
}
~~~

Đây là đoạn minh họa; cần import KeyValue từ Micrometer và điều chỉnh assertion theo KeyValues API của version đang dùng. Nếu test low-cardinality values, xác nhận đúng key và value, không chỉ xác nhận số lượng tags.

### 6.1 Low-cardinality và high-cardinality assertions

- Low-cardinality values có thể trở thành metric tags; kiểm tra chỉ dùng allowlisted values.
- High-cardinality values có thể dùng cho traces; kiểm tra không đưa secrets/PII vào context.
- Không assert chỉ một tag count nếu thứ tự/extra common tags có thể thay đổi theo cấu hình.
- Không snapshot toàn bộ context nếu có fields chứa runtime objects không ổn định.

Ví dụ test nên khẳng định warehouse thuộc tập north/south/central thay vì nhận raw input tùy ý.

## 7. Kiểm tra error recording

Observation có thể ghi exception vào context khi callback thất bại. Test nên kiểm tra:
- Exception được propagate theo contract của method.
- Context chứa error mong đợi.
- Handler stop vẫn được gọi.
- Tracing handler ghi error event/status theo convention.
- Metric outcome/error tags được chuẩn hóa và bounded.

Ví dụ assertion trong recording handler:

~~~java
@Override
public void onStop(Observation.Context context) {
    Throwable error = context.getError();
    if (error != null) {
        recordedErrors.add(error.getClass());
    }
}
~~~

Chỉ dùng exception class/category làm metric tag nếu được normalize thành tập hữu hạn. Không dùng exception message vì message có thể chứa SQL, user input, URL, credentials hoặc PII.

### 7.1 Business outcome không phải lúc nào cũng là error

Nếu repository trả empty result và service chuyển thành business result “not found”, Observation có thể hoàn tất bình thường. Không ép mọi business rejection thành exception chỉ để tạo error span. Hãy định nghĩa outcome riêng, ví dụ success/not_found/rejected, và chỉ đánh dấu error khi operation technical failure theo contract.

## 8. Kiểm tra Timer/Counter trong MeterRegistry

Để xác nhận Observation tạo metrics, đăng ký meter observation handler và MeterRegistry phù hợp trong test. Trong Spring Boot test context, Actuator/Micrometer auto-configuration có thể cung cấp registry/handlers; unit test thuần cần cấu hình handlers tương ứng.

Ví dụ custom Timer độc lập:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

class InventoryMetrics {
    private final Timer timer;

    InventoryMetrics(MeterRegistry registry) {
        timer = Timer.builder("inventory.reserve.duration")
                .tag("operation", "reserve")
                .register(registry);
    }

    void record(Runnable operation) {
        timer.record(operation);
    }
}
~~~

Test:

~~~java
@Test
void recordsTimerForReservation() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    InventoryMetrics metrics = new InventoryMetrics(registry);

    metrics.record(() -> { });

    Timer timer = registry.find("inventory.reserve.duration")
            .tag("operation", "reserve")
            .timer();

    assertThat(timer).isNotNull();
    assertThat(timer.count()).isEqualTo(1);
}
~~~

Ví dụ này kiểm tra Timer custom, không chứng minh Observation handler tự tạo timer. Để kiểm tra Observation-to-metrics, cấu hình DefaultMeterObservationHandler hoặc handler phù hợp với Spring Boot/Micrometer version rồi assert meter được tạo từ Observation.

### 8.1 Không kiểm tra duration bằng equality chính xác

Duration phụ thuộc scheduler, machine load và clock resolution. Thay vì assert đúng 10 ms, dùng range rộng hoặc assert count và presence. Với logic timing quan trọng, inject Clock hoặc abstraction đo thời gian có thể kiểm soát.

## 9. Kiểm tra tracing span

Observation chỉ tạo span nếu tracing observation handler và Micrometer Tracing bridge/tracer được cấu hình. Trong unit/integration tests, dùng test tracer/reporter do tracing bridge cung cấp, hoặc exporter in-memory phù hợp.

Những điều nên assert:
- Span name/operation name đúng.
- Parent span hoặc trace ID được nối đúng khi context hiện hành tồn tại.
- Attributes có values đã chuẩn hóa.
- Error event/status xuất hiện khi technical failure.
- Span kết thúc sau callback.
- Không có PII/secrets trong attributes/events.

Không assert span ID hoặc trace ID bằng literal cố định; các IDs thường được tạo ngẫu nhiên. Assert quan hệ parent-child và cùng trace ID thay vì so một chuỗi hardcoded.

## 10. Test ObservationPredicate và filtering

ObservationPredicate có thể từ chối một Observation trước khi handlers xử lý. Nếu production cấu hình predicate, test cần xác nhận:
- Observation được cho phép vẫn được handler nhận.
- Observation bị loại không tạo metrics/spans theo policy.
- Predicate không loại nhầm error/slow operations quan trọng.
- Tên và context matching ổn định.

Ví dụ predicate:

~~~java
ObservationPredicate predicate =
        (name, context) -> !name.equals("internal.noisy.operation");
~~~

Unit test cho predicate nên kiểm tra cả allow và deny cases. Tránh regex quá rộng hoặc phụ thuộc tên method có thể đổi theo refactor nếu tên đó không phải contract ổn định.

## 11. Test custom Observation trong Spring Boot context

Unit test registry riêng không chứng minh bean wiring/proxy/auto-configuration của Spring Boot. Dùng @SpringBootTest hoặc slice phù hợp khi cần xác nhận:
- ObservationRegistry được inject đúng.
- Custom bean sử dụng registry từ context.
- MeterRegistry/Observation handlers được auto-configure.
- Configuration properties và filters được áp dụng.
- AOP annotations/proxy nếu operation dùng annotation-based instrumentation.

Ví dụ test context:

~~~java
@SpringBootTest
class InventoryReservationIntegrationTest {

    @Autowired
    InventoryReservationService service;

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void reservationCreatesExpectedMetric() {
        service.reserve("north", "SKU-1");

        assertThat(meterRegistry.getMeters())
                .isNotEmpty();
    }
}
~~~

Đây là skeleton. Trong test thật, assert đúng meter name, tag set và count thay vì chỉ kiểm tra registry có bất kỳ meter nào. Nếu application context có nhiều instrumentation, dùng dedicated registry hoặc lọc meter theo name.

## 12. Test context propagation qua async/reactive boundaries

Observation context có thể được propagate trong cùng thread hoặc qua framework integrations. Khi code chuyển sang executor hoặc reactive pipeline, test cần xác nhận context được truyền đúng theo mechanism ứng dụng đang sử dụng.

Các trường hợp:
- Thread pool task chạy sau khi request thread đã kết thúc.
- CompletableFuture continuation trên executor khác.
- Reactor pipeline chuyển scheduler.
- Message consumer nhận trace context từ headers.
- Custom executor có TaskDecorator/context propagation configuration.

Không giả định ThreadLocal tự động đi theo thread mới. Dùng Micrometer Context Propagation hoặc integration native của Spring/Reactor/Tracing khi phù hợp; kiểm tra version và configuration.

Test nên assert trace ID/parent relationship hoặc observation context value ở bên trong callback async. Dùng latch/future để đồng bộ test; không dùng sleep tùy tiện để chờ background work.

## 13. Test cardinality và privacy regressions

Custom Observation có thể thêm tags theo input. Test nên tạo nhiều values khác nhau và xác nhận meter IDs vẫn nằm trong giới hạn đã định.

Ví dụ:
- Gọi operation với nhiều SKU nhưng metric tag chỉ có warehouse và operation.
- Truyền email canary và xác nhận không xuất hiện trong tags/span attributes.
- Truyền unknown warehouse và xác nhận được normalize thành unknown.
- Ném exception chứa token giả và xác nhận message không bị copy vào metric tags.

Không chỉ kiểm tra một request. Cardinality regressions chỉ lộ ra khi gọi nhiều input khác nhau.

## 14. Test duplicate observations

Một custom business Observation có thể lồng trong HTTP server Observation hoặc database Observation. Nesting là hợp lệ nếu biểu diễn các operation khác nhau. Duplicate xảy ra khi hai instrumentation cùng mô tả một operation và làm metrics/spans bị đếm trùng.

Test cần xác nhận:
- Một inbound request tạo đúng server observation.
- Custom operation tạo một child observation nếu mong đợi.
- Repository instrumentation không bị nhân đôi bởi custom wrapper cùng tên/ý nghĩa.
- Timer/counter count không tăng gấp đôi ngoài chủ đích.
- Span tree thể hiện đúng boundaries.

Không cố assert toàn trace có đúng một span; một request hợp lệ có thể tạo nhiều spans cho HTTP, DB, messaging và custom business operations.

## 15. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Handler không nhận Observation | Registry khác instance hoặc handler chưa đăng ký | Kiểm tra registry wiring và observationConfig |
| Start có nhưng stop không có | Lifecycle tự quản lý thiếu finally hoặc test chưa chờ async | Dùng observe() hoặc bảo đảm terminal path |
| Context name đúng nhưng tags thiếu | Tags thêm sau thời điểm handler callback hoặc convention khác | Kiểm tra lifecycle và KeyValues API |
| Timer không xuất hiện | Chưa đăng ký meter observation handler | Cấu hình handler/Actuator metrics |
| Timer count bằng 0 | Callback chưa chạy hoặc meter query sai tags | Assert operation và available meter IDs |
| Span không xuất hiện | Tracing bridge/handler chưa cấu hình | Kiểm tra tracer và tracing auto-configuration |
| Span không có parent | Context không được propagate qua thread/process | Kiểm tra executor/Reactor/message headers |
| Test pass riêng nhưng fail suite | Shared global registry/state | Dùng registry riêng và cleanup |
| Duplicate spans/timers | Custom Observation trùng auto-instrumentation | Phân biệt operation boundaries và bỏ instrumentation dư |
| Test duration flaky | Assert timing chính xác hoặc sleep cố định | Assert presence/range và dùng synchronization |
| Metric cardinality tăng | Dynamic input làm tag | Allowlist/normalize và test nhiều inputs |
| PII trong context | Copy request data/exception message vào tags | Source minimization và canary assertions |

## 16. Playbook: kiểm thử một custom Observation trước khi release

**Tình huống:** Team thêm Observation cho inventory reservation và cần xác nhận telemetry không bị sai.

1. Viết unit test với ObservationRegistry riêng.
2. Đăng ký recording handler và assert name/contextual name.
3. Assert low-cardinality tags và high-cardinality fields theo policy.
4. Test success, exception và cancellation paths.
5. Assert start/stop đúng một lần cho mỗi operation.
6. Cấu hình MeterObservationHandler trong test và xác nhận Timer/count.
7. Dùng test tracer/reporter để xác nhận span name, parent và error.
8. Test async/context propagation nếu operation chuyển thread hoặc process.
9. Gửi nhiều SKU/user inputs và xác nhận meter cardinality không tăng theo identifier.
10. Gửi synthetic PII canary và xác nhận không xuất hiện trong metrics/traces/logs.
11. Kiểm tra custom observation có trùng auto-instrumentation hay không.
12. Chạy Spring Boot integration test để xác nhận registry/handlers được wire như production.

Sau khi tests pass, dùng staging Collector/backend test nếu thay đổi exporter hoặc OTLP pipeline. Không cần bắt mọi unit test phụ thuộc một telemetry backend đang chạy.

## 17. Bài tập tự kiểm tra

**Bài 1 — Lifecycle.** Vì sao test custom Observation cần assert cả onStart và onStop? Điều gì xảy ra nếu callback ném exception?

**Bài 2 — Registry.** Vì sao mỗi test nên có ObservationRegistry riêng thay vì dùng global registry?

**Bài 3 — Tags.** Một test chỉ assert Observation name nhưng không assert tags có thể bỏ sót lỗi nào?

**Bài 4 — Metrics.** Vì sao recording ObservationHandler chưa chứng minh Timer được tạo trong MeterRegistry?

**Bài 5 — Tracing.** Vì sao không nên assert trace ID bằng literal cố định? Nên assert quan hệ nào?

**Bài 6 — Async.** Vì sao context có thể mất khi callback chạy trên executor khác?

**Bài 7 — Cardinality.** Thiết kế test nào phát hiện SKU/customer ID vô tình trở thành metric tag?

**Bài 8 — Duplicate.** Khi nào hai observations lồng nhau là hợp lệ và khi nào là duplicate instrumentation?

### Gợi ý trả lời

1. Start/stop chứng minh lifecycle hoàn chỉnh; callback lỗi vẫn phải kết thúc observation và giữ error context.
2. Tránh state/handler rò rỉ giữa tests và làm kết quả phụ thuộc thứ tự chạy.
3. Tags có thể thiếu/sai, dynamic hoặc chứa PII; kiểm tra name không đủ.
4. Recording handler chỉ quan sát lifecycle; cần meter observation handler và MeterRegistry để tạo Timer.
5. IDs được sinh ngẫu nhiên. Assert cùng trace ID và đúng parent-child relationship.
6. Context thường gắn với execution context/ThreadLocal; thread khác không tự kế thừa.
7. Gọi operation với nhiều IDs khác nhau rồi assert số Meter.Id/tag values vẫn bounded và không chứa IDs.
8. HTTP server observation chứa business operation child là hợp lệ; hai instrumentation cùng đo một operation và đếm hai lần là duplicate.

## 18. Tài liệu tham khảo chính thức

- [Micrometer Observation — Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html): Observation lifecycle, registry, handlers và conventions.
- [Micrometer Observation — Testing](https://docs.micrometer.io/micrometer/reference/observation/testing.html): test utilities và kiểm tra Observation.
- [Micrometer Observation — API](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html): tạo custom Observation và quản lý lifecycle.
- [Micrometer Metrics — Testing](https://docs.micrometer.io/micrometer/reference/concepts/meters.html): meter registry, meter types và measurements.
- [Micrometer Tracing](https://docs.micrometer.io/tracing/reference/): tracing bridge, spans và context propagation.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): application context và integration testing.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry, handlers và auto-configuration.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): context qua process boundaries.
- [OpenTelemetry — Testing](https://opentelemetry.io/docs/languages/java/instrumentation/): Java instrumentation và test integration concepts.

**Ghi nhớ:** Test custom Observation bằng registry và handler riêng để xác nhận name, context, tags, error và lifecycle. Muốn chứng minh metrics hoặc tracing hoạt động, kiểm tra MeterRegistry và test tracer/reporter riêng; một recording handler không chứng minh exporter đã gửi dữ liệu. Test cả success/error, async propagation, cardinality, PII và duplicate instrumentation. Giữ unit tests độc lập với backend telemetry; chỉ dùng end-to-end tests khi thay đổi exporter, Collector hoặc propagation qua process.

