# TestObservationRegistry để xác minh vòng đời và dữ liệu quan sát

Micrometer Observation là lớp instrumentation chung cho các hoạt động như xử lý request, gọi dịch vụ phụ thuộc hoặc thực hiện use case. Khi kiểm thử, chỉ xác nhận phương thức nghiệp vụ trả về đúng kết quả là chưa đủ: cần biết Observation có được tạo đúng tên, bắt đầu và kết thúc đúng lúc, nhận lỗi khi có exception và mang đúng key-values hay không.

TestObservationRegistry thuộc module kiểm thử của Micrometer Observation. Nó cung cấp một registry dành cho test cùng các assertion giúp kiểm tra những Observation đã được phát ra. Nhờ vậy, có thể xác minh instrumentation mà không cần gửi metrics đến Prometheus, xuất span đến Zipkin hoặc khởi chạy một tracing backend.

## 1. TestObservationRegistry giải quyết vấn đề gì?

Một service có thể dùng Observation để đo một thao tác:

~~~java
Observation.createNotStarted("business.checkout", observationRegistry)
    .lowCardinalityKeyValue("channel", "web")
    .observe(() -> checkoutService.execute(command));
~~~

Đoạn code này có thể chạy đúng về nghiệp vụ nhưng instrumentation vẫn có lỗi:

- Tên Observation bị đổi ngoài ý muốn.
- Thiếu low-cardinality key-value dùng để phân nhóm metrics.
- Observation không được stop khi có exception.
- Lỗi không được báo bằng observation.error(...).
- Code chỉ tạo Observation nhưng không đi qua lifecycle như dự kiến.
- Một refactor làm mất Observation hoặc tạo thêm Observation trùng.

TestObservationRegistry giúp kiểm tra các hành vi đó ở cấp Observation. Nó ghi nhận những Observation đã được tạo và cho phép assertion về tên, trạng thái lifecycle và dữ liệu context.

~~~mermaid
flowchart TD
    A["Unit test"] --> B["Service / instrumentation"]
    B --> C["ObservationRegistry"]
    C --> D["TestObservationRegistry"]
    D --> E["Ghi lại Observation và lifecycle"]
    E --> F["TestObservationRegistryAssert"]
    F --> G["Kiểm tra tên, trạng thái, key-values"]
~~~

Đây là test ở lớp Observation API. Nó không chứng minh Prometheus scrape endpoint hoạt động, exporter gửi span thành công hoặc backend đã lưu telemetry.

## 2. Thêm dependency kiểm thử

Với Gradle:

~~~kotlin
dependencies {
    implementation("io.micrometer:micrometer-observation")
    testImplementation("io.micrometer:micrometer-observation-test")
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-observation</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-observation-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Trong ứng dụng Spring Boot, dependency management của Spring Boot BOM nên quản lý phiên bản Micrometer. Không tự đặt một phiên bản riêng cho observation-test khác với observation đang dùng trong ứng dụng.

Các lớp thường dùng trong bài:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
~~~

Artifact test chỉ cần ở test scope. Không đóng gói TestObservationRegistry vào runtime artifact của ứng dụng.

## 3. Tạo TestObservationRegistry

Tạo registry trong mỗi test để các Observation được ghi nhận độc lập:

~~~java
TestObservationRegistry observationRegistry =
    TestObservationRegistry.create();
~~~

Sau đó truyền registry vào service hoặc instrumentation đang kiểm thử. Nếu service nhận ObservationRegistry qua constructor, có thể inject TestObservationRegistry trực tiếp vì nó triển khai abstraction ObservationRegistry.

Không dùng một TestObservationRegistry static chung cho nhiều test. Registry dùng chung có thể giữ lại Observation từ test trước và làm assertion phụ thuộc thứ tự chạy.

Ví dụ một service nhỏ:

~~~java
public class CheckoutService {

    private final ObservationRegistry observationRegistry;

    public CheckoutService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public CheckoutResult checkout(CheckoutCommand command) {
        return Observation.createNotStarted(
                "business.checkout",
                observationRegistry
            )
            .lowCardinalityKeyValue("channel", command.channel())
            .observe(() -> performCheckout(command));
    }

    private CheckoutResult performCheckout(CheckoutCommand command) {
        // Thực hiện validation, tính phí và lưu đơn hàng.
        return new CheckoutResult();
    }
}
~~~

Service chỉ phụ thuộc ObservationRegistry. Nhờ đó, test có thể truyền TestObservationRegistry, còn ứng dụng thật dùng registry được Spring Boot cấu hình.

## 4. Xác minh Observation được tạo, start và stop

Test cơ bản:

~~~java
import io.micrometer.observation.tck.TestObservationRegistry;
import io.micrometer.observation.tck.TestObservationRegistryAssert;
import org.junit.jupiter.api.Test;

class CheckoutServiceTest {

    @Test
    void recordsCheckoutObservation() {
        TestObservationRegistry registry =
            TestObservationRegistry.create();
        CheckoutService service = new CheckoutService(registry);

        service.checkout(new CheckoutCommand("web"));

        TestObservationRegistryAssert.assertThat(registry)
            .hasObservationWithNameEqualTo("business.checkout")
            .that()
            .hasBeenStarted()
            .hasBeenStopped()
            .hasLowCardinalityKeyValue("channel", "web");
    }
}
~~~

Assertion xác nhận:

- Có Observation mang tên business.checkout.
- Observation đã bắt đầu.
- Observation đã kết thúc.
- Context chứa low-cardinality key-value channel=web.

Đây là kiểm tra trực tiếp instrumentation tại ranh giới service. Nếu code vô tình bỏ lời gọi Observation hoặc thay đổi tên, test sẽ thất bại dù kết quả nghiệp vụ vẫn đúng.

## 5. Kiểm tra low-cardinality và high-cardinality key-values

Observation có thể mang hai nhóm key-values:

| Loại | Mục đích | Ví dụ |
| --- | --- | --- |
| Low-cardinality | Dùng cho metrics dimensions, số lượng giá trị hữu hạn | channel=web, outcome=success |
| High-cardinality | Dùng cho tracing hoặc chẩn đoán từng operation | order.id, request.id |

Ví dụ instrumentation:

~~~java
Observation.createNotStarted("business.checkout", registry)
    .lowCardinalityKeyValue("channel", "web")
    .lowCardinalityKeyValue("outcome", "success")
    .highCardinalityKeyValue("order.id", "order-123")
    .observe(() -> checkout());
~~~

Test có thể xác minh các key-values đã được gắn đúng:

~~~java
TestObservationRegistryAssert.assertThat(registry)
    .hasObservationWithNameEqualTo("business.checkout")
    .that()
    .hasLowCardinalityKeyValue("channel", "web")
    .hasLowCardinalityKeyValue("outcome", "success")
    .hasHighCardinalityKeyValue("order.id", "order-123");
~~~

Không biến order ID hoặc request ID thành low-cardinality key-value. Test có thể kiểm tra phân loại key-value để ngăn một thay đổi instrumentation vô tình đưa dữ liệu định danh vào metrics labels.

Với dữ liệu nhạy cảm, cần kiểm tra cả việc có đưa giá trị đó vào Observation hay không. High-cardinality không đồng nghĩa với an toàn; giá trị vẫn có thể được ghi vào span hoặc telemetry backend.

## 6. Xác minh đường thành công và đường lỗi

Khi thao tác thất bại, instrumentation cần báo lỗi vào Observation rồi kết thúc lifecycle. API observe(...) thường quản lý lifecycle cho đoạn code đồng bộ, bao gồm báo lỗi và stop khi exception thoát khỏi callback.

Ví dụ service:

~~~java
public Receipt pay(PaymentCommand command) {
    return Observation.createNotStarted(
            "business.payment",
            observationRegistry
        )
        .lowCardinalityKeyValue("operation", "authorize")
        .observe(() -> paymentGateway.authorize(command));
}
~~~

Test đường lỗi:

~~~java
@Test
void recordsPaymentFailure() {
    TestObservationRegistry registry =
        TestObservationRegistry.create();
    PaymentGateway gateway = command -> {
        throw new PaymentUnavailableException();
    };
    PaymentService service = new PaymentService(registry, gateway);

    assertThatThrownBy(() -> service.pay(new PaymentCommand()))
        .isInstanceOf(PaymentUnavailableException.class);

    TestObservationRegistryAssert.assertThat(registry)
        .hasObservationWithNameEqualTo("business.payment")
        .that()
        .hasBeenStarted()
        .hasBeenErrored()
        .hasBeenStopped();
}
~~~

Test xác minh exception vẫn được truyền về caller và Observation nhận trạng thái lỗi trước khi kết thúc. Nếu phiên bản Micrometer đang dùng có assertion DSL khác cho trạng thái lỗi, có thể dùng một ObservationHandler ghi nhận callback onError và onStop để kiểm tra cùng hành vi.

Không chỉ assert rằng exception được ném. Một service có thể truyền exception đúng nhưng quên báo lỗi cho Observation khi tự quản lý lifecycle thủ công.

## 7. Kiểm tra Observation.event(...)

Event đánh dấu một mốc xảy ra bên trong operation, ví dụ đã reserve inventory hoặc đã gọi payment provider. Event không kết thúc Observation.

Ví dụ:

~~~java
Observation observation = Observation.createNotStarted(
    "business.checkout",
    registry
);

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    observation.event(Observation.Event.of("inventory.reserved"));
    observation.event(Observation.Event.of("payment.authorized"));
} finally {
    observation.stop();
}
~~~

TestObservationRegistry có thể được dùng để xác minh Observation đã được tạo và kết thúc. Khi cần assert chính xác danh sách event hoặc thứ tự event, thêm một ObservationHandler nhỏ trong test để thu thập callback onEvent.

~~~java
List<String> events = new ArrayList<>();

ObservationHandler<Observation.Context> eventRecorder =
    new ObservationHandler<>() {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onEvent(
            Observation.Event event,
            Observation.Context context
        ) {
            events.add(event.getName());
        }
    };

registry.observationConfig().observationHandler(eventRecorder);
~~~

Sau khi thực hiện operation:

~~~java
assertThat(events).containsExactly(
    "inventory.reserved",
    "payment.authorized"
);
~~~

Handler này bổ sung cho TestObservationRegistry. Nó không thay thế registry test; registry test vẫn ghi nhận Observation và assertion lifecycle, còn recorder xác minh event cụ thể.

## 8. Kiểm tra Scope được mở và đóng

Scope làm Observation thành context hiện hành trong đoạn code đang chạy. Nếu instrumentation cần Scope để tạo quan hệ parent-child hoặc truy cập current observation, test nên xác minh cả mở và đóng.

TestObservationRegistryAssert tập trung vào Observation lifecycle và context. Để kiểm tra callback Scope, dùng handler thu thập sự kiện:

~~~java
List<String> scopeEvents = new ArrayList<>();

ObservationHandler<Observation.Context> scopeRecorder =
    new ObservationHandler<>() {
        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onScopeOpened(Observation.Context context) {
            scopeEvents.add("opened:" + context.getName());
        }

        @Override
        public void onScopeClosed(Observation.Context context) {
            scopeEvents.add("closed:" + context.getName());
        }
    };

registry.observationConfig().observationHandler(scopeRecorder);
~~~

Sau khi chạy code mở scope:

~~~java
assertThat(scopeEvents).containsExactly(
    "opened:business.checkout",
    "closed:business.checkout"
);
~~~

Điều này giúp phát hiện lỗi quên close Scope. Nếu Scope bị bỏ quên, callback đóng không xuất hiện và context có thể bị rò rỉ sang phần xử lý tiếp theo trên cùng thread.

Với scope lồng nhau, test thứ tự mở/đóng theo LIFO. Scope được mở sau phải đóng trước; khi child đóng, parent phải trở lại current context.

## 9. Kiểm tra custom Observation.Context và ObservationHandler

Ứng dụng có thể tạo context riêng để mang dữ liệu đặc thù cho một loại operation:

~~~java
public final class PaymentContext extends Observation.Context {

    private final String provider;

    public PaymentContext(String provider) {
        this.provider = provider;
    }

    public String getProvider() {
        return provider;
    }
}
~~~

Handler chuyên biệt:

~~~java
public final class PaymentHandler
        implements ObservationHandler<PaymentContext> {

    private final List<String> callbacks;

    public PaymentHandler(List<String> callbacks) {
        this.callbacks = callbacks;
    }

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof PaymentContext;
    }

    @Override
    public void onStart(PaymentContext context) {
        callbacks.add("start:" + context.getProvider());
    }

    @Override
    public void onError(PaymentContext context) {
        callbacks.add("error:" + context.getProvider());
    }

    @Override
    public void onStop(PaymentContext context) {
        callbacks.add("stop:" + context.getProvider());
    }
}
~~~

Trong test, đăng ký handler với registry:

~~~java
List<String> callbacks = new ArrayList<>();
registry.observationConfig()
    .observationHandler(new PaymentHandler(callbacks));
~~~

Tạo Observation dùng supplier để cung cấp context chuyên biệt:

~~~java
Observation.createNotStarted(
        "payment.authorize",
        () -> new PaymentContext("provider-a"),
        registry
    )
    .observe(() -> paymentGateway.authorize(command));
~~~

Sau đó kiểm tra callback:

~~~java
assertThat(callbacks).containsExactly(
    "start:provider-a",
    "stop:provider-a"
);
~~~

Test đường lỗi cần xác nhận callback error xuất hiện giữa start và stop. Handler chuyên biệt cũng cần test supportsContext để bảo đảm nó không xử lý HTTP hoặc Observation không thuộc loại payment.

## 10. Kiểm tra nhiều handler cùng nhận một Observation

Một ứng dụng có thể dùng đồng thời metrics handler, tracing handler và handler tùy chỉnh. Test nên xác minh composite được cấu hình theo đúng semantics.

Với chiến lược all-matching, mọi handler hỗ trợ context đều được gọi. Với first-matching, chỉ handler đầu tiên phù hợp được gọi. Hai chiến lược có mục đích khác nhau:

| Chiến lược | Trường hợp sử dụng |
| --- | --- |
| All-matching | Metrics và tracing cần cùng xử lý một Observation |
| First-matching | Các handler là lựa chọn thay thế cho cùng một context |

Test có thể đăng ký hai recorder độc lập, chạy một Observation rồi kiểm tra cả hai đều nhận start/stop. Nếu chỉ một recorder nhận callback, kiểm tra composite handler và thứ tự đăng ký.

Trong Spring Boot, các handler metrics/tracing mặc định có thể đã được auto-configure. Trước khi đăng ký thêm handler, hãy xác minh registry hiện có gì để tránh tạo Timer hoặc span trùng.

## 11. Kiểm tra Observation lồng nhau

Một use case có thể tạo Observation cha và các Observation con:

~~~java
Observation.createNotStarted("business.checkout", registry)
    .observe(() -> {
        Observation.createNotStarted("inventory.reserve", registry)
            .observe(() -> inventory.reserve(command.items()));

        Observation.createNotStarted("payment.authorize", registry)
            .observe(() -> payment.authorize(command.payment()));
    });
~~~

Test có thể kiểm tra từng tên Observation đã được tạo và hoàn tất. Khi cần xác minh parent-child relationship ở tracing layer, phải kiểm tra span/trace context với tracing test exporter hoặc tracer test phù hợp. Chỉ thấy hai Observation trong TestObservationRegistry chưa chứng minh span con có đúng parent span.

Observation lồng nhau cũng cần kiểm tra scope được đóng đúng thứ tự. Nếu code tự quản lý scope, dùng try-with-resources và kiểm tra callback scope recorder.

## 12. Kiểm tra xử lý bất đồng bộ

Không dùng observe(...) quanh một lời gọi chỉ trả về CompletableFuture nếu muốn đo đến khi future hoàn tất. observe(...) quản lý lifecycle đồng bộ quanh việc gọi callback; nếu callback trả về future ngay, Observation có thể stop trước khi công việc nền kết thúc.

Với operation bất đồng bộ, giữ Observation đến terminal completion và chỉ mở Scope quanh đoạn submit nếu cần:

~~~java
public CompletableFuture<Report> generate(ReportCommand command) {
    Observation observation = Observation.start(
        "business.report.generate",
        observationRegistry
    );

    CompletableFuture<Report> future;
    try (Observation.Scope scope = observation.openScope()) {
        future = reportClient.generateAsync(command);
    } catch (RuntimeException error) {
        observation.error(error);
        observation.stop();
        throw error;
    }

    return future.whenComplete((report, error) -> {
        if (error != null) {
            observation.error(error);
        }
        observation.stop();
    });
}
~~~

Test dùng future hoàn tất rồi join trước khi assert:

~~~java
TestObservationRegistry registry = TestObservationRegistry.create();
AsyncReportService service = new AsyncReportService(
    registry,
    command -> CompletableFuture.completedFuture(new Report())
);

service.generate(new ReportCommand()).join();

TestObservationRegistryAssert.assertThat(registry)
    .hasObservationWithNameEqualTo("business.report.generate")
    .that()
    .hasBeenStarted()
    .hasBeenStopped();
~~~

Với future chạy trên executor khác, test phải chờ completion bằng future/join hoặc latch phù hợp trước khi đọc kết quả. Không dùng Thread.sleep làm cơ chế đồng bộ vì dễ tạo test chập chờn.

Nếu cần kiểm tra context propagation sang thread khác, TestObservationRegistry chỉ xác minh lifecycle Observation. Hãy bổ sung test cho Context Propagation hoặc tracing integration trên executor thực tế.

## 13. Dùng TestObservationRegistry trong Spring Boot

Ở unit test, cách đơn giản nhất là truyền TestObservationRegistry trực tiếp vào service. Ở SpringBootTest, ứng dụng thường đã có ObservationRegistry do auto-configuration tạo.

Có hai chiến lược:

1. Kiểm tra hành vi của service bằng TestObservationRegistry trong test độc lập.
2. Kiểm tra cấu hình Spring Boot bằng ObservationRegistry thật của ApplicationContext và quan sát handler/endpoint tương ứng.

Không thay ObservationRegistry mặc định bằng TestObservationRegistry trong toàn bộ context một cách tùy tiện, vì việc thay bean có thể làm mất các handler metrics hoặc tracing do auto-configuration cung cấp. Nếu cần test customizer hoặc auto-configuration, dùng context test có cấu hình rõ ràng và kiểm tra các handler đang được đăng ký.

Ví dụ test Spring Boot xác minh bean registry tồn tại:

~~~java
@SpringBootTest
class ObservationConfigurationTest {

    @Autowired
    ObservationRegistry observationRegistry;

    @Test
    void createsObservationRegistry() {
        assertThat(observationRegistry).isNotNull();
    }
}
~~~

Test này chỉ xác nhận Spring tạo registry. Để xác minh một operation cụ thể, gọi service và kiểm tra handler, meter hoặc span tương ứng.

## 14. Phân biệt Observation test với metrics test và tracing test

Các test này xác minh các lớp khác nhau:

| Công cụ | Điều xác minh | Không chứng minh |
| --- | --- | --- |
| TestObservationRegistry | Tên Observation, lifecycle, context và key-values | Timer đã được export hoặc span đến backend |
| SimpleMeterRegistry | Counter, Gauge, Timer và measurement trong bộ nhớ | Prometheus naming hoặc HTTP export |
| PrometheusMeterRegistry | Prometheus exposition và tên metric đã chuẩn hóa | Prometheus server đã scrape thành công |
| Tracing test exporter/reporter | Span, attributes, parent-child và export payload ở test | Backend production đã lưu trace |
| End-to-end test với collector/backend | Đường telemetry qua receiver và backend test | Hành vi ở mọi môi trường production |

TestObservationRegistry không thay thế các registry test khác. Nó kiểm tra hợp đồng Observation mà instrumentation phát ra. Nếu code tạo Observation đúng nhưng meter handler không được cấu hình, TestObservationRegistry vẫn có thể pass trong khi không có Timer.

## 15. Các lỗi kiểm thử thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy Observation | Tên sai, code không tạo Observation hoặc test chưa gọi service | Kiểm tra tên và thực hiện đúng operation |
| Observation đã start nhưng chưa stop | Lifecycle thủ công thiếu finally hoặc terminal callback | Bảo đảm stop ở mọi đường kết thúc |
| Không có error state | Code không gọi observation.error(error) | Báo lỗi trước khi stop |
| Thiếu low-cardinality key-value | Gắn key-value ở nhánh không chạy hoặc sai tên key | Assert key và value cụ thể |
| Test pass nhưng không có Timer | Chưa đăng ký meter handler hoặc test chỉ dùng Observation registry | Bổ sung test MeterRegistry riêng |
| Event bị thiếu | Event không được phát hoặc recorder không hỗ trợ context | Kiểm tra event call và supportsContext |
| Scope không được đóng | Thiếu try-with-resources hoặc close ở nhánh lỗi | Dùng try-with-resources |
| Test async đọc registry quá sớm | Future chưa hoàn tất | join hoặc await terminal signal |
| Test phụ thuộc thứ tự | Dùng chung registry mutable giữa test | Tạo TestObservationRegistry mới cho mỗi test |
| Test context không thấy parent | Scope/context propagation không được thiết lập | Kiểm tra scope và tracing/context integration |

## 16. Quy trình viết test cho Observation

Với mỗi instrumentation quan trọng:

1. Tạo TestObservationRegistry mới.
2. Truyền registry vào service hoặc component cần kiểm thử.
3. Thực hiện đúng thao tác nghiệp vụ.
4. Assert tên Observation.
5. Assert trạng thái started và stopped.
6. Assert error state cho đường thất bại.
7. Assert low-cardinality và high-cardinality key-values theo hợp đồng.
8. Dùng recorder handler nếu cần kiểm tra event hoặc Scope callbacks.
9. Với async, đợi terminal completion trước khi assert.
10. Dùng test riêng cho MeterRegistry, tracing exporter và endpoint export.

Nên kiểm thử ít nhất các nhánh thành công, lỗi, timeout, cancellation và thao tác bất đồng bộ nếu service hỗ trợ các đường này. Không cần kiểm tra mọi chi tiết implementation nội bộ; hãy tập trung vào hợp đồng quan sát mà dashboard, alert và tracing dựa vào.

## 17. Checklist

- [ ] Có micrometer-observation-test ở test scope.
- [ ] Phiên bản observation-test tương thích với Micrometer Observation trong ứng dụng.
- [ ] Mỗi test tạo TestObservationRegistry riêng.
- [ ] Service nhận ObservationRegistry qua constructor hoặc abstraction phù hợp.
- [ ] Tên Observation được kiểm tra chính xác.
- [ ] Lifecycle start/stop được xác minh.
- [ ] Đường lỗi được kiểm tra và exception vẫn truyền về caller.
- [ ] Low-cardinality và high-cardinality key-values đúng mục đích.
- [ ] Event và Scope callbacks được kiểm tra khi instrumentation sử dụng chúng.
- [ ] Async test chờ future/publisher hoàn tất trước khi assert.
- [ ] Metrics và tracing export có test riêng phù hợp.

TestObservationRegistry giúp kiểm tra Observation mà ứng dụng phát ra trước khi dữ liệu được chuyển thành metrics hoặc tracing. Nó xác minh tên, lifecycle và context một cách trực tiếp, đồng thời giúp phát hiện lỗi thiếu stop, thiếu error hoặc key-values sai. Kết hợp nó với recorder handler cho event/scope và các test registry/export riêng sẽ tạo ra bộ kiểm thử rõ ràng cho toàn bộ instrumentation mà không nhầm lẫn giữa Observation lifecycle với việc lưu telemetry ở backend.
