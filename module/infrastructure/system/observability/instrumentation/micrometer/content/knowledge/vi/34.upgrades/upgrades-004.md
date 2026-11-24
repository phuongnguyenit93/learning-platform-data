# Chuyển dần phép đo thủ công sang Observation tại ranh giới phù hợp

Micrometer Observation giúp tách **ranh giới của một thao tác** khỏi cách ghi metrics hoặc traces. Thay vì tự tạo Timer.Sample, tự dừng timer và tự ghi nhận lỗi ở mỗi service, ứng dụng tạo một Observation bao quanh thao tác. Các ObservationHandler đã đăng ký quyết định cần tạo Timer, span, log hoặc hành vi khác.

Việc chuyển đổi nên diễn ra từng ranh giới, có đối chiếu metric cũ và mới. Observation phù hợp với một thao tác có điểm bắt đầu, kết thúc và ngữ nghĩa rõ ràng, chẳng hạn xử lý checkout, gọi dịch vụ thanh toán hoặc đồng bộ một batch. Gauge, DistributionSummary và các Counter độc lập vẫn có thể tiếp tục dùng API meter trực tiếp.

## 1. Observation thay đổi điều gì?

Với cách đo thủ công, code nghiệp vụ thường biết cả tên metric, tags, registry và cách xử lý exception:

~~~java
Timer.Sample sample = Timer.start(meterRegistry);
String error = "none";

try {
    checkoutService.execute(command);
}
catch (RuntimeException exception) {
    error = exception.getClass().getSimpleName();
    throw exception;
}
finally {
    sample.stop(
        meterRegistry.timer(
            "checkout.processing.duration",
            "channel", command.channel(),
            "error", error
        )
    );
}
~~~

Cách này hoạt động, nhưng mỗi nơi phải tự bảo đảm sample luôn được dừng, error được ghi đúng và tags nhất quán. Nếu sau này cần tracing, code nghiệp vụ lại phải biết thêm cách tạo span hoặc truyền trace context.

Với Observation, code mô tả thao tác và metadata. Handler chịu trách nhiệm chuyển lifecycle thành metrics hoặc tracing:

~~~java
Observation.createNotStarted(
        "checkout.processing.duration",
        observationRegistry
    )
    .lowCardinalityKeyValue("channel", command.channel())
    .observe(() -> checkoutService.execute(command));
~~~

observe(...) thực hiện vòng đời start, mở scope, chạy callback, ghi nhận exception, đóng scope và stop. Với DefaultMeterObservationHandler, khi Observation dừng, Micrometer tạo Timer theo tên Observation, gắn các low-cardinality key-values và tag error. Nếu registry có tracing handler, cùng Observation có thể tạo span.

Observation không tự động bảo đảm mọi backend đều nhận cả metrics và traces. Kết quả phụ thuộc handler và exporter đã được cấu hình trong ObservationRegistry.

## 2. Chọn đúng ranh giới trước khi thay code

Một Observation nên đại diện cho một thao tác có ý nghĩa với người vận hành hoặc nghiệp vụ. Ranh giới quá rộng khiến số liệu khó định vị; ranh giới quá nhỏ tạo quá nhiều span và meter, làm tăng chi phí và nhiễu.

Các ranh giới thường phù hợp:

- Một thao tác nghiệp vụ như checkout, tạo đơn hàng hoặc hoàn tiền.
- Một lời gọi đến hệ thống bên ngoài như payment provider hoặc inventory service.
- Một job nền hoặc batch có thời điểm bắt đầu và kết thúc rõ ràng.
- Một giai đoạn xử lý có thể được phân tích riêng khi điều tra latency.
- Một thao tác thư viện cần phát metrics và tracing thống nhất cho ứng dụng sử dụng nó.

Không nên tạo Observation cho từng getter, setter, phép chuyển đổi nhỏ hoặc mỗi dòng code. Hãy đặt nó ở nơi có thể trả lời câu hỏi vận hành như “checkout mất bao lâu?”, “lời gọi payment provider lỗi ở đâu?” hoặc “batch nào đang chạy quá lâu?”.

Trước khi thêm Observation, kiểm tra framework hoặc thư viện đã instrument thao tác đó chưa. Spring Boot và Spring Framework đã có observations cho nhiều ranh giới HTTP, messaging và data access. Instrument lại cùng một ranh giới có thể tạo span lồng nhau không cần thiết hoặc ghi thời gian hai lần.

## 3. Kiểm kê phép đo hiện tại

Trước khi sửa code, lập danh sách meter đang có và ý nghĩa của từng meter. Đừng chỉ ghi tên metric; cần biết nơi cập nhật, đơn vị, tags, tần suất và dashboard đang sử dụng.

| Phép đo hiện tại | Câu hỏi cần xác định | Hướng chuyển đổi |
|---|---|---|
| Timer hoặc Timer.Sample | Đo thao tác nào, bắt đầu/kết thúc ở đâu, tags nào được quyết định sau khi xử lý? | Thường chuyển thành Observation |
| Counter cho sự kiện trong thao tác | Sự kiện có nằm trong lifecycle của một Observation không? | Có thể dùng Observation.event() |
| Counter nghiệp vụ độc lập | Counter có được tăng mà không có một thao tác cha phù hợp không? | Giữ Counter trực tiếp |
| LongTaskTimer | Cần theo dõi công việc đang chạy hay chỉ thời lượng sau khi hoàn tất? | Có thể dùng active Observation LongTaskTimer hoặc giữ meter |
| Gauge | Đo state hiện tại nào và ai sở hữu source object? | Thường giữ Gauge trực tiếp |
| DistributionSummary | Đo kích thước, số byte, số item hay đại lượng không phải thời gian? | Giữ DistributionSummary hoặc viết handler chuyên biệt |
| Meter tùy chỉnh | Có phép tổng hợp hoặc schema riêng không? | Giữ meter hoặc xây ObservationHandler riêng |

Observation mặc định không phải bộ thay thế cho mọi loại meter. DefaultMeterObservationHandler tạo Timer khi Observation dừng, Counter khi phát event và LongTaskTimer nếu được bật. Nó không tự thay Gauge hoặc DistributionSummary.

## 4. Chuẩn hóa metric contract trước khi migrate

Metric contract gồm tên metric, tập tag keys, ý nghĩa giá trị, đơn vị và cách diễn giải. Dashboard, alert và truy vấn backend thường phụ thuộc vào contract này.

Với DefaultMeterObservationHandler, Timer có tên bằng tên Observation. Timer được gắn:

- Tất cả low-cardinality key-values của Observation.
- Tag error, chứa thông tin lớp exception nếu có lỗi hoặc none nếu không có lỗi. Hãy kiểm tra cách biểu diễn chính xác của phiên bản Micrometer đang dùng trước khi yêu cầu giữ nguyên từng giá trị tag từ metric cũ.

Điều này quan trọng khi Timer cũ không có tag error. Nếu giữ cùng metric name nhưng thay đổi tập tag keys, một số backend như Prometheus có thể gặp schema không nhất quán. Trước khi chuyển, chọn một trong các cách:

1. Bổ sung tag error vào metric thủ công cũ để hai phía có cùng schema.
2. Đổi tên metric mới theo phiên bản, ví dụ checkout.processing.duration.v2, rồi cập nhật dashboard và alert.
3. Thực hiện migration trong một khoảng chuyển tiếp có kiểm soát, sau đó loại bỏ metric cũ.

Không ghi đồng thời metric cũ và Observation mới vào cùng một meter ID cho cùng một lần xử lý. Nếu cả hai cùng ghi Timer, count và total time sẽ bị nhân đôi.

## 5. Chuyển Timer thủ công sang Observation

Giả sử service đang đo thời gian xử lý checkout bằng Timer.Sample:

~~~java
public Receipt checkout(Command command) {
    Timer.Sample sample = Timer.start(meterRegistry);
    String error = "none";

    try {
        return checkoutService.execute(command);
    }
    catch (RuntimeException exception) {
        error = exception.getClass().getSimpleName();
        throw exception;
    }
    finally {
        sample.stop(
            meterRegistry.timer(
                "checkout.processing.duration",
                "channel", command.channel(),
                "error", error
            )
        );
    }
}
~~~

Sau khi chuyển, inject ObservationRegistry và đặt Observation quanh cùng một thao tác:

~~~java
public Receipt checkout(Command command) {
    return Observation.createNotStarted(
            "checkout.processing.duration",
            observationRegistry
        )
        .lowCardinalityKeyValue("channel", command.channel())
        .observe(() -> checkoutService.execute(command));
}
~~~

Hai đoạn code cần đo cùng một ranh giới. Nếu Timer cũ bắt đầu trước validation và kết thúc sau khi lưu đơn hàng, Observation mới cũng phải bao phủ đúng khoảng đó. Nếu thay đổi ranh giới cùng lúc, so sánh latency trước/sau sẽ không còn đáng tin.

Nếu muốn đặt tên span dễ đọc khác với tên metric, dùng ObservationConvention để định nghĩa technical name và contextual name. Không nhồi tên class hoặc method động vào metric name.

## 6. Chuyển Counter thành Observation event khi có ngữ nghĩa phù hợp

Một Counter có thể biểu diễn một sự kiện xảy ra bên trong thao tác, chẳng hạn checkout phải retry hoặc dùng phương thức thanh toán dự phòng.

~~~java
public Receipt checkout(Command command) {
    Observation observation = Observation.createNotStarted(
        "checkout.processing",
        observationRegistry
    );

    return observation.observe(() -> {
        PaymentResult result = paymentService.pay(command);

        if (result.retried()) {
            observation.event(Observation.Event.of("payment.retry"));
        }

        return orderService.complete(command, result);
    });
}
~~~

Với DefaultMeterObservationHandler, event tạo Counter có tên theo dạng `<observation-name>.<event-name>`, được gắn low-cardinality key-values có tại thời điểm event xảy ra. Ví dụ trên tạo counter tương ứng `checkout.processing.payment.retry`.

Không phải Counter nào cũng nên chuyển thành event. Nếu Counter đếm số đơn hàng được tạo độc lập với một thao tác quan sát, hoặc tên metric hiện tại là contract quan trọng, giữ Counter trực tiếp. Event nên mô tả một mốc trong lifecycle của Observation, không phải cách đổi tên tùy tiện cho mọi Counter.

Một Observation Timer cũng có count, vì vậy không tạo thêm Counter chỉ để đếm số lần hoàn tất nếu Timer count đã trả lời đúng câu hỏi. Tuy nhiên, Counter riêng vẫn có ích khi nó biểu diễn một sự kiện nghiệp vụ khác với số lần Observation hoàn tất.

## 7. Giữ Gauge và DistributionSummary khi chúng đo đại lượng khác

Gauge đo trạng thái hiện tại, ví dụ số request đang hoạt động, queue size hoặc số connection đang được sử dụng. Observation đo lifecycle của một thao tác. Hai khái niệm không thay thế nhau.

DistributionSummary đo phân phối của một đại lượng số không phải thời gian, ví dụ payload size hoặc số item trong batch. DefaultMeterObservationHandler không tự tạo DistributionSummary từ một Observation.

Có thể giữ meter trực tiếp bên cạnh Observation:

~~~java
public BatchResult process(Batch batch) {
    Observation observation = Observation.createNotStarted(
        "batch.processing",
        observationRegistry
    );

    return observation.observe(() -> {
        BatchResult result = batchProcessor.process(batch);

        processedItems.record(result.itemCount());
        payloadBytes.record(batch.payloadSize());

        return result;
    });
}
~~~

Observation cung cấp thời lượng, lỗi và tracing cho thao tác batch. DistributionSummary vẫn ghi nhận số item và số byte. Hãy giữ hai meter có tên và đơn vị rõ ràng, tránh tạo custom handler chỉ để thay một API meter đơn giản nếu không có nhu cầu dùng chung lifecycle.

## 8. Dùng ObservationConvention để gom tên và tags

Khi nhiều nơi tạo cùng một loại Observation, không nên lặp tên và tag keys trong từng method. ObservationConvention tập trung quy tắc đặt tên và phân loại key-values.

Ví dụ context cho thao tác checkout:

~~~java
public final class CheckoutContext extends Observation.Context {

    private final String channel;
    private final String paymentMethod;

    public CheckoutContext(String channel, String paymentMethod) {
        this.channel = channel;
        this.paymentMethod = paymentMethod;
    }

    public String channel() {
        return channel;
    }

    public String paymentMethod() {
        return paymentMethod;
    }
}
~~~

Convention:

~~~java
import io.micrometer.common.KeyValue;
import io.micrometer.common.KeyValues;
import io.micrometer.observation.GlobalObservationConvention;

public final class CheckoutObservationConvention
        implements GlobalObservationConvention<CheckoutContext> {

    @Override
    public boolean supportsContext(Observation.Context context) {
        return context instanceof CheckoutContext;
    }

    @Override
    public String getName() {
        return "checkout.processing";
    }

    @Override
    public String getContextualName(CheckoutContext context) {
        return "checkout";
    }

    @Override
    public KeyValues getLowCardinalityKeyValues(CheckoutContext context) {
        return KeyValues.of(
            KeyValue.of("channel", context.channel()),
            KeyValue.of("payment.method", context.paymentMethod())
        );
    }
}
~~~

Tạo Observation bằng convention và context supplier:

~~~java
Observation.createNotStarted(
        new CheckoutObservationConvention(),
        () -> new CheckoutContext(command.channel(), command.paymentMethod()),
        observationRegistry
    )
    .observe(() -> checkoutService.execute(command));
~~~

Với Spring Boot, đăng ký convention này thành bean để registry dùng làm global convention:

~~~java
@Bean
GlobalObservationConvention<CheckoutContext> checkoutObservationConvention() {
    return new CheckoutObservationConvention();
}
~~~

Trong dự án thực tế, dùng một instance convention dùng chung. Khi truyền custom convention trực tiếp, caller chịu trách nhiệm chọn đúng convention cho context. Context supplier giúp trì hoãn tạo context nếu Observation bị tắt hoặc registry là no-op. Context chuyên biệt cũng giúp convention truy cập dữ liệu có kiểu thay vì tra cứu key chuỗi.

Low-cardinality tags phải có tập giá trị hữu hạn, chẳng hạn channel hoặc payment method. Không đưa order ID, user ID, request ID hoặc URL chứa định danh vào metric tags. Nếu cần định danh để tìm trace, chỉ cân nhắc high-cardinality attribute khi chính sách dữ liệu cho phép.

## 9. Chuyển xử lý exception và outcome

Với Timer thủ công, code thường phải tự chọn tag error, status hoặc outcome. Observation có thể nhận exception qua observe(...) và chuyển nó đến handler.

~~~java
Observation.createNotStarted("inventory.reserve", observationRegistry)
    .lowCardinalityKeyValue("warehouse", warehouse)
    .observe(() -> inventoryService.reserve(items));
~~~

Nếu reserve ném exception, observe ghi nhận lỗi và vẫn dừng Observation. DefaultMeterObservationHandler thêm tag error cho Timer. Không cần tự tạo một Counter lỗi trùng với Timer nếu Timer có thể cung cấp count theo tag error cho dashboard.

Nếu nghiệp vụ cần outcome rõ như accepted, rejected hoặc partial, có thể thêm low-cardinality key-value vào context trước khi Observation dừng. Khi tự điều khiển lifecycle, hãy đặt outcome trước stop():

~~~java
Observation observation = Observation.createNotStarted(
    "payment.authorize",
    observationRegistry
).lowCardinalityKeyValue("channel", channel);

observation.start();

try (Observation.Scope scope = observation.openScope()) {
    Authorization result = paymentService.authorize(command);
    observation.lowCardinalityKeyValue(
        "outcome",
        result.accepted() ? "accepted" : "rejected"
    );
    return result;
}
catch (RuntimeException exception) {
    observation.error(exception);
    throw exception;
}
finally {
    observation.stop();
}
~~~

Nếu bật active Observation LongTaskTimer, các low-cardinality key-values dùng làm tags cho meter active phải có trước start(). Key được thêm sau start có thể xuất hiện trong Timer khi stop nhưng không được thêm ngược vào LongTaskTimer đã tạo.

Không dùng exception message hoặc dữ liệu tự do làm outcome tag. Hãy giữ tập giá trị nhỏ và ổn định.

## 10. Theo dõi tác vụ đang chạy

DefaultMeterObservationHandler mặc định tạo Timer khi Observation dừng. Nếu cần biết tác vụ nào vẫn đang chạy, có thể bật LongTaskTimer cho active observations:

~~~java
observationRegistry.observationConfig()
    .observationHandler(
        DefaultMeterObservationHandler.builder(meterRegistry)
            .includeActiveObservationLongTaskTimer(true)
            .build()
    );
~~~

Khi bật, Observation tạo meter active theo dạng `<observation-name>.active` lúc start và dừng nó khi Observation stop. Meter này giúp theo dõi số task đang chạy, tổng duration active và task active lâu nhất.

Không bật active LongTaskTimer cho mọi Observation nếu không cần. Mỗi loại Observation có thể tạo thêm meter và tag combinations. Chỉ bật cho các ranh giới có thời gian chạy dài hoặc cần phát hiện công việc bị treo.

## 11. Tích hợp Spring Boot

Trong ứng dụng Spring Boot, inject ObservationRegistry do Boot quản lý. Các handler và convention được cấu hình theo dependency và auto-configuration của ứng dụng.

~~~java
@Service
public class CheckoutService {

    private final ObservationRegistry observationRegistry;

    public CheckoutService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public Receipt checkout(Command command) {
        return Observation.createNotStarted(
                "checkout.processing",
                observationRegistry
            )
            .lowCardinalityKeyValue("channel", command.channel())
            .observe(() -> performCheckout(command));
    }

    private Receipt performCheckout(Command command) {
        // Xác thực, thanh toán và hoàn tất đơn hàng.
        return new Receipt();
    }
}
~~~

Spring Boot tự động đăng ký các bean như ObservationHandler, GlobalObservationConvention, ObservationPredicate và ObservationFilter vào registry được quản lý. Tuy nhiên, việc có metrics hoặc spans còn phụ thuộc vào các registry, tracing bridge và exporter có trong classpath cũng như cấu hình ứng dụng.

Trong ứng dụng Micrometer thuần, cần tự tạo registry và đăng ký handler tương ứng. Ví dụ kiểm thử dùng DefaultMeterObservationHandler:

~~~java
MeterRegistry meterRegistry = new SimpleMeterRegistry();
ObservationRegistry observationRegistry = ObservationRegistry.create();

observationRegistry.observationConfig()
    .observationHandler(
        DefaultMeterObservationHandler.builder(meterRegistry).build()
    );
~~~

Đừng đăng ký thêm một meter handler nếu framework đã cấu hình handler tương đương cho cùng registry; có thể tạo duplicate handling hoặc metrics ngoài dự kiến.

## 12. Với Reactor, đo lifecycle subscription chứ không đo lúc tạo publisher

Một method trả Mono hoặc Flux thường chỉ lắp ráp pipeline. Không bọc lời gọi tạo publisher bằng Observation.observe(...) theo cách đồng bộ, vì Observation có thể dừng ngay khi method trả về publisher, trước khi subscription thực thi.

Với Reactor, dùng tích hợp trong module reactor-core-micrometer:

Thêm dependency tương thích với phiên bản Reactor và Micrometer mà dự án đang dùng; khi dự án quản lý bằng BOM, để BOM chọn version thay vì ghim một version riêng:

~~~gradle
implementation("io.projectreactor:reactor-core-micrometer")
~~~

~~~java
import reactor.core.observability.micrometer.Micrometer;

public Mono<Receipt> checkoutReactive(Command command) {
    return checkoutService.checkout(command)
        .name("checkout.processing")
        .tap(Micrometer.observation(observationRegistry));
}
~~~

tap(Micrometer.observation(...)) theo dõi lifecycle của reactive sequence qua subscription và terminal signal. Có thể truyền một Observation supplier tùy chỉnh để dùng convention và context chuyên biệt:

~~~java
return checkoutService.checkout(command)
    .name("checkout.processing")
    .tap(Micrometer.observation(
        observationRegistry,
        registry -> Observation.createNotStarted(
            checkoutConvention,
            checkoutContextSupplier,
            registry
        )
    ));
~~~

Đưa operator vào đúng vị trí của pipeline để Observation bao phủ công việc cần đo. Vị trí tương đối của `retry()` quyết định ranh giới:

~~~java
// Một Observation cho toàn operation, bao gồm các lần retry.
source.retry(2)
    .tap(Micrometer.observation(observationRegistry));

// Một Observation cho mỗi attempt được retry.
source.tap(Micrometer.observation(observationRegistry))
    .retry(2);
~~~

share và cache cũng có thể thay đổi số subscription hoặc phần công việc upstream được thực thi; hãy quyết định rõ muốn đo từng attempt, toàn operation hay từng subscriber. Kiểm tra phiên bản Reactor và reactor-core-micrometer tương thích qua BOM của dự án.

## 13. Chuyển đổi mà không tạo instrumentation trùng

Một ranh giới không nên vừa có Timer thủ công vừa có Observation tạo Timer cho cùng một lần xử lý. Điều này có thể xảy ra khi:

- Method service đã được bọc bởi Observation nhưng caller vẫn ghi Timer cũ.
- Spring Boot đã tự instrument HTTP hoặc database, trong khi ứng dụng thêm Observation cho cùng thao tác kỹ thuật.
- Một aspect và một đoạn code thủ công cùng đo một method.
- Retry khiến một phía đo từng attempt còn phía kia đo toàn operation nhưng hai metric dùng cùng tên.

Trước khi triển khai, vẽ ranh giới và xác định mỗi meter thuộc về một instrumentation owner. Nếu cần đo cả operation lẫn attempt, dùng hai tên khác nhau và mô tả rõ semantics.

Không tạo Observation con cho mọi method được gọi. Chỉ tạo child observation khi nó biểu diễn một bước có giá trị chẩn đoán riêng; đảm bảo scope của parent được mở trong lúc child được tạo để tracing có thể giữ quan hệ cha-con.

## 14. Quy trình migration từng bước

Có thể triển khai theo từng nhóm service:

1. **Inventory**: liệt kê Timer, Counter, LongTaskTimer, Gauge, DistributionSummary, tags và dashboard phụ thuộc.
2. **Chọn boundary**: xác định thao tác nào có lifecycle rõ ràng và chưa được framework instrument.
3. **Định nghĩa contract**: thống nhất Observation name, contextual name, low/high cardinality keys và error/outcome semantics.
4. **Cấu hình handlers**: xác nhận registry có meter handler; chỉ thêm tracing handler khi ứng dụng cần tracing.
5. **Migrate một operation**: thay một Timer.Sample bằng Observation, giữ nguyên phạm vi bắt đầu/kết thúc và xử lý lỗi.
6. **Kiểm thử**: xác nhận count, duration, tags, event và exception behavior; so sánh với metric cũ.
7. **Canary**: triển khai ở một instance hoặc một nhóm traffic nhỏ, theo dõi scrape, series count và dashboard.
8. **Mở rộng**: chuyển các boundary tương tự khi số liệu ổn định.
9. **Dọn dẹp**: xóa Timer hoặc Counter cũ chỉ sau khi dashboard, alert và truy vấn đã chuyển.
10. **Tài liệu hóa**: ghi lại tên Observation, convention và ý nghĩa tags để các nhóm khác dùng nhất quán.

Nếu cần dual-run để so sánh, ghi metric mới dưới tên hoặc namespace tạm riêng. Không để hai đường instrumentation cùng ghi vào một meter ID. Đặt thời hạn kết thúc dual-run để tránh duy trì hai schema lâu dài.

## 15. Kiểm thử Observation thay cho Timer thủ công

Một unit test với SimpleMeterRegistry có thể xác nhận Observation tạo Timer đúng tên và tags:

~~~java
@Test
void observationRecordsTimerWithLowCardinalityTags() {
    SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
    ObservationRegistry observationRegistry = ObservationRegistry.create();

    observationRegistry.observationConfig()
        .observationHandler(
            DefaultMeterObservationHandler.builder(meterRegistry).build()
        );

    Observation.createNotStarted("checkout.processing", observationRegistry)
        .lowCardinalityKeyValue("channel", "web")
        .observe(() -> { });

    assertEquals(
        1,
        meterRegistry.get("checkout.processing")
            .tag("channel", "web")
            .tag("error", "none")
            .timer()
            .count()
    );
}
~~~

Kiểm tra lỗi:

~~~java
@Test
void observationRecordsErrorAndStillStopsTimer() {
    SimpleMeterRegistry meterRegistry = new SimpleMeterRegistry();
    ObservationRegistry observationRegistry = ObservationRegistry.create();

    observationRegistry.observationConfig()
        .observationHandler(
            DefaultMeterObservationHandler.builder(meterRegistry).build()
        );

    assertThrows(
        IllegalStateException.class,
        () -> Observation.createNotStarted(
                "checkout.processing",
                observationRegistry
            )
            .observe(() -> {
                throw new IllegalStateException("payment failed");
            })
    );

    Timer timer = meterRegistry.getMeters().stream()
        .filter(meter -> meter.getId().getName().equals("checkout.processing"))
        .map(Timer.class::cast)
        .findFirst()
        .orElseThrow();

    assertEquals(1, timer.count());
    assertNotNull(timer.getId().getTag("error"));
}
~~~

Bổ sung test cho các điểm sau:

- Event tạo Counter với tên và low-cardinality tags mong đợi.
- High-cardinality key-value không trở thành meter tag.
- LongTaskTimer active chỉ xuất hiện khi được bật.
- Active meter nhận đầy đủ tags cần thiết tại thời điểm start.
- Observation dừng khi callback thành công hoặc ném exception.
- Context và convention được chọn đúng.
- Không có hai instrumentation cùng ghi một operation.
- Reactive observation kết thúc khi sequence complete, error hoặc cancel.

Để so sánh với Timer cũ, dùng cùng input và cùng ranh giới. Đừng so sánh một Timer đo toàn request với một Observation chỉ đo phần gọi repository.

## 16. Các chỉ số cần theo dõi trong giai đoạn chuyển đổi

Trong canary, không chỉ xem latency. Theo dõi cả tính đầy đủ của metric contract:

| Chỉ số kiểm tra | Dấu hiệu bất thường |
|---|---|
| Timer count | Tăng gấp đôi hoặc giảm mạnh so với traffic |
| Timer total time / latency | Ranh giới đo cũ và mới khác nhau |
| Error tag | Exception không được ghi nhận hoặc giá trị tag thay đổi |
| Low-cardinality tags | Thiếu key, thêm key ngoài dự kiến hoặc giá trị không chuẩn hóa |
| Active observation | Task không dừng hoặc tags không đầy đủ |
| Event counters | Event bị phát nhiều lần do retry hoặc không được phát |
| Series count | Cardinality tăng ngoài dự kiến |
| Trace count và parent-child | Span trùng lặp hoặc mất quan hệ cha-con |
| Scrape/export errors | Registry hoặc exporter không xử lý schema mới |

Khi metric count thay đổi, đối chiếu với request count hoặc domain event độc lập để xác định đó là thay đổi traffic hay thay đổi instrumentation. Không kết luận migration thành công chỉ vì metric mới xuất hiện.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chuyển mọi Counter thành Observation event | Sinh nhiều Observation không cần thiết | Chỉ dùng event cho mốc nằm trong lifecycle |
| Nghĩ Observation thay Gauge hoặc Summary | Mất số liệu state hoặc phân phối đại lượng | Giữ meter trực tiếp hoặc viết handler có chủ đích |
| Bọc cả method trả Mono bằng observe đồng bộ | Observation dừng trước khi reactive work chạy | Dùng Reactor tap(Micrometer.observation(...)) |
| Giữ Timer cũ cùng Observation mới | Count và total time bị nhân đôi | Chỉ một owner ghi mỗi meter ID |
| Không tính tag error mặc định | Prometheus label schema có thể thay đổi | Đồng bộ tag keys hoặc version metric name |
| Đặt boundary khác nhau khi migrate | So sánh latency sai | Giữ cùng điểm bắt đầu và kết thúc |
| Đưa ID động vào low-cardinality tag | Cardinality tăng mạnh | Chuyển sang high cardinality hoặc bỏ khỏi metrics |
| Instrument lại thao tác đã được Spring hỗ trợ | Timer/span trùng hoặc lồng không cần thiết | Kiểm tra instrumentation có sẵn |
| Quên đăng ký handler | Observation không tạo metrics/traces như mong đợi | Xác minh registry và handler |
| Dùng Observation cho mọi method nhỏ | Tăng chi phí và nhiễu trace | Chọn boundary có ý nghĩa vận hành |

## 18. Checklist hoàn tất migration

- [ ] Đã kiểm kê meter, tags, đơn vị và dashboard hiện tại.
- [ ] Đã xác định thao tác nào đã được framework hoặc thư viện instrument.
- [ ] Mỗi Observation đại diện cho một boundary có ý nghĩa.
- [ ] Tên metric/span và contextual name được thống nhất.
- [ ] Low-cardinality và high-cardinality keys được phân loại đúng.
- [ ] Đã kiểm tra tag error và schema backend.
- [ ] Timer thủ công cũ không còn ghi trùng với Observation.
- [ ] Counter chỉ chuyển thành event khi phù hợp với lifecycle.
- [ ] Gauge và DistributionSummary vẫn được ghi nhận.
- [ ] Active LongTaskTimer chỉ bật cho operation cần theo dõi.
- [ ] Reactive pipeline được instrument theo subscription lifecycle.
- [ ] Unit test xác nhận count, tags, error, event và active state.
- [ ] Canary không làm tăng series count hoặc scrape errors bất thường.
- [ ] Dashboard và alert đã được chuyển trước khi xóa metric cũ.
- [ ] Tài liệu convention và metric contract đã được cập nhật.

Chuyển sang Observation là thay đổi cách mô tả một thao tác và chia sẻ lifecycle của nó với metrics, tracing hoặc handler khác. Hãy bắt đầu từ những Timer đang đo một operation rõ ràng, giữ nguyên ranh giới và metric contract, rồi chuyển từng nhóm sau khi kiểm thử. Counter độc lập, Gauge và DistributionSummary vẫn có thể dùng meter API trực tiếp; mục tiêu là dùng Observation ở nơi lifecycle chung mang lại giá trị, không phải thay toàn bộ meter bằng một abstraction duy nhất.

## Tài liệu tham khảo

- [Micrometer Observation — Components](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer Observation — Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Spring Boot Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Reactor — Exposing metrics and observations](https://projectreactor.io/docs/core/release/reference/metrics.html)

