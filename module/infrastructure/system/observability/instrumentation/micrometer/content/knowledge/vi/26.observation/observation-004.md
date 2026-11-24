# observe để quản lý vòng đời một khối mã đồng bộ

## Observation bao quanh một lần thực thi

Micrometer Observation cung cấp một abstraction chung để mô tả một lần thực thi có vòng đời rõ ràng. Một Observation có thể được xử lý bởi nhiều handler: handler phía metrics có thể ghi Timer, handler phía tracing có thể tạo Span, và handler khác có thể bổ sung logging hoặc context.

Với một khối mã đồng bộ, phương thức **observe(...)** là cách ngắn gọn để quản lý vòng đời. Ứng dụng tạo Observation, bổ sung các thuộc tính cần thiết, rồi truyền khối mã cần đo vào observe. API quản lý việc bắt đầu, mở scope trong lúc thực thi, ghi nhận lỗi khi có exception và kết thúc Observation khi khối mã trả về hoặc ném lỗi.

Ví dụ:

~~~java
public InventoryResult reconcile(
        InventoryService service,
        ObservationRegistry observationRegistry
) {
    return Observation.createNotStarted(
            "inventory.reconcile",
            observationRegistry
        )
        .lowCardinalityKeyValue("operation", "reconcile")
        .observe(service::reconcile);
}
~~~

Ở đây, lời gọi service.reconcile() chạy bên trong Observation. Khi method hoàn tất, Observation được dừng. Nếu method ném RuntimeException, lifecycle vẫn được kết thúc và lỗi được chuyển đến handler theo cấu hình; exception tiếp tục được truyền cho caller.

Observation không tự động đồng nghĩa với một Timer hoặc Span. Dữ liệu được tạo ra phụ thuộc các ObservationHandler đã đăng ký trên ObservationRegistry. Nếu registry không có handler metrics hoặc tracing tương ứng, khối mã vẫn có thể chạy qua lifecycle Observation nhưng không có metric hoặc trace được xuất.

## Observation khác Timer trực tiếp ở điểm nào?

Timer là meter chuyên đo thời lượng và số lần một thao tác được ghi nhận. Observation là abstraction cho lifecycle của một hoạt động; nó có thể được nhiều handler chuyển thành các tín hiệu khác nhau.

| Khía cạnh | Timer trực tiếp | Observation |
|---|---|---|
| Mục đích | Đo count và duration | Mô tả lifecycle của một hoạt động |
| API chính | record, Sample | createNotStarted, observe, start, stop |
| Metrics | Ghi trực tiếp vào Timer | Handler metrics chuyển Observation thành meter |
| Tracing | Không tự tạo span | Handler tracing có thể tạo span |
| Context | Chủ yếu là meter tags | Có Observation.Context và scope hiện hành |
| Lỗi | Ứng dụng quyết định tag/record | Có thể ghi error vào lifecycle để handler xử lý |
| Phù hợp | Một phép đo thời lượng đơn giản | Một hoạt động cần phối hợp metrics, traces và context |

Nếu chỉ cần đo thời lượng một khối mã và không cần context chung, Timer.record là lựa chọn đơn giản. Nếu cùng một thao tác cần tạo metrics và trace bằng một lifecycle thống nhất, Observation phù hợp hơn.

Không nên tạo Timer thủ công và Observation có metrics handler cho cùng một đoạn mã nếu cả hai cùng đại diện một phép đo giống nhau, trừ khi chủ đích là có hai metric khác nhau. Nếu không, count và duration có thể bị ghi hai lần.

## Tạo Observation chưa bắt đầu

### createNotStarted

Observation.createNotStarted(name, registry) tạo một Observation chưa bắt đầu. Tại thời điểm này có thể bổ sung các key-value, convention hoặc context cần thiết trước khi lifecycle bắt đầu.

Ví dụ:

~~~java
Observation observation = Observation.createNotStarted(
    "catalog.product.lookup",
    observationRegistry
);

observation.lowCardinalityKeyValue("source", "primary-cache");
observation.lowCardinalityKeyValue("operation", "lookup");

Product product = observation.observe(
    () -> catalogService.findProduct(productId)
);
~~~

Tên Observation nên mô tả hoạt động ổn định, có ý nghĩa nghiệp vụ hoặc kỹ thuật. Không đưa ID sản phẩm, request ID, email hoặc giá trị tự do vào tên Observation vì tên có thể trở thành tên meter hoặc span tùy handler.

Các key-value cần được đặt trước khi bắt đầu Observation để handler nhận được metadata đầy đủ trong lifecycle. Những thuộc tính phát sinh sau khi xử lý bắt đầu có thể được thêm vào context hoặc theo API tương ứng, nhưng phải hiểu thời điểm handler đọc chúng.

### observe với khối trả về kết quả

Khi khối mã trả về một giá trị, observe có thể trả lại chính giá trị đó:

~~~java
PaymentResult result = Observation.createNotStarted(
        "payment.authorize",
        observationRegistry
    )
    .lowCardinalityKeyValue("payment.type", "card")
    .observe(() -> paymentService.authorize(command));
~~~

Caller nhận PaymentResult như khi gọi service trực tiếp. Observation bao quanh lời gọi và kết thúc trước khi kết quả được trả ra ngoài.

Đây là cách phù hợp cho các method đồng bộ trả về giá trị. Không cần tự gọi start và stop nếu toàn bộ công việc nằm trong một Supplier đồng bộ.

### observe với khối không trả về kết quả

Với thao tác void, có thể dùng dạng Runnable:

~~~java
Observation.createNotStarted(
        "cache.refresh",
        observationRegistry
    )
    .lowCardinalityKeyValue("cache", "product")
    .observe(() -> cacheService.refresh());
~~~

Khối mã được thực thi trong Observation và lifecycle được kết thúc khi Runnable hoàn thành. Nếu exception thoát khỏi khối mã, Observation có thể ghi nhận lỗi trước khi kết thúc và exception vẫn được truyền ra caller.

Nếu lambda có thể ném checked exception, hãy kiểm tra overload API phù hợp của phiên bản Micrometer đang dùng; không bọc exception tùy tiện theo cách làm mất semantics của lỗi.

## Lifecycle: start, scope, error và stop

Phương thức observe quản lý lifecycle tự động. Trong một số tình huống, ứng dụng cần tách thời điểm tạo Observation, bắt đầu, mở scope và kết thúc. Khi đó có thể dùng API lifecycle thủ công.

Luồng cơ bản:

~~~text
createNotStarted
      |
      v
    start
      |
      v
  openScope
      |
      v
  run business code
      |
      +---- success ------------------+
      |                               |
      +---- exception -> error ------+
                                      |
                                   close scope
                                      |
                                     stop
~~~

Ví dụ:

~~~java
Observation observation = Observation.createNotStarted(
    "inventory.reconcile",
    observationRegistry
);

observation.lowCardinalityKeyValue("operation", "reconcile");
observation.start();

try (Observation.Scope scope = observation.openScope()) {
    inventoryService.reconcile();
} catch (RuntimeException | Error ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Các bước có ý nghĩa riêng:

- **createNotStarted:** tạo context và xác định tên Observation nhưng chưa bắt đầu lifecycle.
- **start:** thông báo cho các handler rằng Observation bắt đầu.
- **openScope:** đặt Observation hiện hành vào scope để code bên trong có thể truy cập context hiện tại.
- **error:** ghi nhận exception vào context để handler xử lý.
- **close scope:** khôi phục Observation trước đó trên thread hiện tại.
- **stop:** kết thúc Observation và cho handler hoàn tất việc ghi nhận.

Dùng try-with-resources cho Scope để scope luôn được đóng, kể cả khi code ném exception. Gọi stop trong finally để bảo đảm lifecycle được kết thúc trên cả nhánh thành công và thất bại.

Nếu dùng observe(...), không tự gọi start/stop thêm lần nữa bên trong khối mã. Điều đó có thể tạo lifecycle lồng hoặc dừng Observation sai thời điểm.

## Scope và Observation hiện hành

### Scope giúp truyền context trong lời gọi đồng bộ

Khi mở Observation.Scope, Observation trở thành current observation trên thread hiện tại. Instrumentation bên dưới có thể lấy current observation để thêm thông tin hoặc tạo Observation con.

Ví dụ:

~~~java
Observation.createNotStarted(
        "order.submit",
        observationRegistry
    )
    .observe(() -> {
        paymentService.authorize(command);
        inventoryService.reserve(command);
    });
~~~

Các Observation được tạo trong lúc scope cha đang mở có thể được liên kết với context hiện hành tùy API và handler. Điều này hữu ích để giữ quan hệ giữa các bước xử lý của cùng một hoạt động.

Scope có tính chất gắn với thread. Nếu khối mã đồng bộ gọi các method khác trên cùng thread, current observation có thể được nhìn thấy trong phạm vi đó. Khi chuyển sang executor hoặc thread khác, context không tự động được truyền trong mọi trường hợp; cần cơ chế context propagation phù hợp.

### Scope lồng nhau

Có thể mở Observation con trong khi Observation cha đang hoạt động:

~~~java
Observation.createNotStarted(
        "order.submit",
        observationRegistry
    )
    .observe(() -> {
        Observation.createNotStarted(
                "payment.authorize",
                observationRegistry
            )
            .observe(() -> paymentService.authorize(command));

        Observation.createNotStarted(
                "inventory.reserve",
                observationRegistry
            )
            .observe(() -> inventoryService.reserve(command));
    });
~~~

Với handler tracing, Observation con có thể trở thành span con của span cha nếu context propagation và tracing handler được cấu hình. Với handler metrics, mỗi Observation có thể tạo meter theo convention tương ứng; cần thiết kế tên và tag để không làm tăng cardinality không kiểm soát.

Không nên tạo Observation mới cho mọi helper method nhỏ. Chọn ranh giới có ý nghĩa vận hành như xử lý order, authorize payment hoặc reserve inventory.

## Xử lý exception đúng lifecycle

### observe tự quản lý lỗi trong khối đồng bộ

Với dạng observe, không cần tự viết catch/finally chỉ để dừng Observation:

~~~java
Result result = Observation.createNotStarted(
        "report.generate",
        observationRegistry
    )
    .observe(() -> reportService.generate());
~~~

Nếu generate ném RuntimeException, Observation API có thể ghi nhận lỗi cho handler và kết thúc lifecycle, sau đó ném lại exception để caller xử lý. Không nuốt exception chỉ để metrics ghi nhận thành công.

Nếu cần phân loại outcome thành success, failure hoặc timeout, hãy bổ sung low-cardinality key-value phù hợp. Cần xác định cách gắn outcome ở thời điểm đã biết kết quả. Không đưa exception message hoặc stack trace vào low-cardinality key-value.

### Dùng lifecycle thủ công khi cần kiểm soát

Khi cần thêm xử lý trong catch hoặc finally, có thể quản lý thủ công:

~~~java
Observation observation = Observation.createNotStarted(
    "report.generate",
    observationRegistry
).start();

try (Observation.Scope scope = observation.openScope()) {
    reportService.generate();
} catch (RuntimeException | Error ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Không gọi observation.error(null) ở nhánh thành công. Không gọi stop trước khi khối mã thực sự hoàn tất. Nếu exception đã được xử lý và không còn được xem là lỗi của hoạt động, quyết định có ghi error hay không phải theo semantics nghiệp vụ.

Nếu dùng observe và lại bắt exception bên ngoài để gọi error lần nữa, có thể ghi nhận lỗi trùng. Chỉ dùng một cơ chế quản lý lifecycle cho một Observation.

## Low-cardinality và high-cardinality key-value

Observation.Context có thể mang thuộc tính được handler sử dụng theo cách khác nhau. Với metrics, key-value cần có tập giá trị hữu hạn để tránh tạo quá nhiều meter hoặc time series.

### Low-cardinality key-value

Dùng lowCardinalityKeyValue cho các chiều phân loại có số giá trị nhỏ và ổn định:

~~~java
Observation.createNotStarted(
        "payment.authorize",
        observationRegistry
    )
    .lowCardinalityKeyValue("payment.type", "card")
    .lowCardinalityKeyValue("outcome", "success")
    .observe(() -> paymentService.authorize(command));
~~~

Ví dụ giá trị hợp lệ:

- payment.type: card, bank_transfer, wallet.
- outcome: success, failure, timeout.
- operation: create, update, cancel.
- region: các vùng triển khai đã định nghĩa.

Các giá trị này có thể được dùng làm metric tag theo convention/handler. Cần giới hạn số giá trị có thể xuất hiện.

### High-cardinality key-value

Dùng highCardinalityKeyValue cho thuộc tính có giá trị đa dạng hoặc duy nhất khi handler tracing cần giữ chúng:

~~~java
Observation.createNotStarted(
        "payment.authorize",
        observationRegistry
    )
    .lowCardinalityKeyValue("payment.type", "card")
    .highCardinalityKeyValue("payment.reference", paymentReference)
    .observe(() -> paymentService.authorize(command));
~~~

Payment reference có thể hữu ích khi tìm một trace cụ thể, nhưng không phù hợp làm metric tag. Handler metrics mặc định được thiết kế để tránh đưa high-cardinality values vào metric dimensions; handler tracing có thể giữ chúng như span attributes.

Không đưa password, token, dữ liệu thẻ, email hoặc dữ liệu cá nhân nhạy cảm vào Observation context chỉ vì đó là high-cardinality. High-cardinality không có nghĩa là được phép gửi dữ liệu nhạy cảm. Chỉ ghi thuộc tính cần thiết, an toàn và có chính sách bảo vệ phù hợp.

## ObservationRegistry và ObservationHandler

### Registry là điểm điều phối

ObservationRegistry quản lý current observation và danh sách handler. Khi Observation bắt đầu, mở scope, ghi error hoặc stop, registry điều phối lifecycle đến các handler đã đăng ký.

Trong Spring Boot, ObservationRegistry thường được auto-configure khi Actuator và các integration phù hợp có mặt. Metrics handler và tracing handler được đăng ký theo dependency cùng cấu hình. Vì vậy, khi ứng dụng dùng Spring Boot, nên inject ObservationRegistry do context cung cấp thay vì tạo registry mới trong mỗi service.

Ví dụ:

~~~java
@Service
public class InventoryService {

    private final ObservationRegistry observationRegistry;

    public InventoryService(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public InventoryResult reconcile() {
        return Observation.createNotStarted(
                "inventory.reconcile",
                observationRegistry
            )
            .observe(this::doReconcile);
    }

    private InventoryResult doReconcile() {
        // Xu ly dong bo.
        return InventoryResult.success();
    }
}
~~~

Trong ví dụ, registry được inject và dùng chung. Không tạo ObservationRegistry mới cho mỗi lần gọi vì registry mới có thể không có handler metrics/tracing và không chia sẻ context với phần còn lại của ứng dụng.

### Handler quyết định tín hiệu nào được tạo

Một Observation có thể được tiêu thụ bởi nhiều handler. Handler metrics có thể chuyển lifecycle thành Timer hoặc meter tương ứng; handler tracing có thể tạo span; handler khác có thể xử lý logging hoặc context.

Nếu không có handler phù hợp, Observation không tự biến thành metric. Khi điều tra metric không xuất hiện, hãy kiểm tra:

1. ObservationRegistry được inject có phải registry của Spring context không?
2. MeterObservationHandler hoặc handler metrics tương ứng có được đăng ký không?
3. Handler có filter hoặc convention loại bỏ Observation không?
4. Observation có được start và stop không?
5. Tên và key-value có được convention ánh xạ đúng không?
6. MeterFilter có từ chối meter được handler tạo ra không?
7. Registry exporter có gửi dữ liệu đến backend không?

Không thêm handler metrics trùng lặp nếu Spring Boot đã tự đăng ký. Hai handler cùng ghi một Observation có thể tạo meter trùng hoặc ghi hai lần.

## Đặt tên và convention cho Observation

Tên Observation nên ngắn, ổn định và mô tả hoạt động. Ví dụ:

- inventory.reconcile
- payment.authorize
- order.submit
- catalog.product.lookup

Không đưa dữ liệu động vào tên. Một Observation cho mỗi product ID hoặc request ID sẽ làm tăng số meter/span name và gây khó khăn khi tổng hợp.

ObservationConvention có thể tùy chỉnh tên và key-value được dùng cho metrics/traces theo quy tắc thống nhất. Khi ứng dụng có nhiều service hoặc nhiều nhóm Observation, convention giúp tránh mỗi component tự đặt tên và tag theo cách khác nhau.

Nếu dùng ObservationDocumentation hoặc convention được cung cấp bởi framework, hãy giữ tên và low-cardinality dimensions nhất quán. Không thay đổi convention tùy tiện giữa các phiên bản nếu dashboard và alert phụ thuộc vào tên metric được sinh ra.

## Khi nào nên dùng observe và khi nào dùng Timer?

| Tình huống | Lựa chọn phù hợp |
|---|---|
| Đo thời lượng một lambda đồng bộ, chỉ cần Timer | Timer.record |
| Đo hoạt động cần cả metrics và tracing | Observation.observe |
| Cần current observation cho các lời gọi con | Observation với scope |
| Cần gắn low/high-cardinality context | Observation |
| Cần tách thời điểm start và stop thủ công | Timer.Sample hoặc Observation lifecycle tùy nhu cầu |
| Chỉ cần đếm một sự kiện | Counter |
| Cần đo trạng thái hiện tại | Gauge |

Observation không thay thế mọi meter. Counter và Gauge vẫn là lựa chọn trực tiếp cho các đại lượng đơn giản. Observation có giá trị khi cần lifecycle chung và context được chia sẻ giữa nhiều handler.

Với khối đồng bộ, observe(...) giúp bao quanh chính xác đoạn code được truyền vào. Nếu method trả về trước khi một công việc async hoàn tất, observe sẽ kết thúc theo lifecycle của khối được thực thi; không mặc định nó theo dõi toàn bộ công việc được submit sang thread khác.

## Kiểm thử Observation.observe

### Kiểm tra lifecycle và kết quả trả về

Một test nên xác minh khối mã được thực thi đúng một lần, kết quả được trả về và exception được truyền ra caller khi có lỗi.

Ví dụ:

~~~java
String result = Observation.createNotStarted(
        "test.operation",
        observationRegistry
    )
    .observe(() -> {
        invocationCounter.incrementAndGet();
        return "done";
    });

assertThat(result).isEqualTo("done");
assertThat(invocationCounter).hasValue(1);
~~~

Có thể bổ sung test exception:

~~~java
assertThrows(IllegalStateException.class, () ->
    Observation.createNotStarted(
            "test.operation",
            observationRegistry
        )
        .observe(() -> {
            throw new IllegalStateException("failed");
        })
);
~~~

Ngoài việc xác minh exception, dùng test handler hoặc metrics handler để kiểm tra lifecycle error/stop đã được phát như mong đợi.

### Kiểm tra metric handler

Trong Spring Boot integration test, inject ObservationRegistry và MeterRegistry từ application context. Thực thi Observation qua observe, sau đó kiểm tra meter theo tên và convention mà phiên bản dự án cấu hình.

Nếu tự dựng registry trong test, phải đăng ký handler metrics tương ứng. Một ObservationRegistry rỗng không tự tạo Timer chỉ vì test đã gọi observe.

Cần kiểm tra count, total time và tag có đúng semantics. Với duration thực tế, nên xác minh count và duration lớn hơn hoặc trong khoảng hợp lý thay vì yêu cầu một thời gian chính xác tuyệt đối.

### Kiểm tra scope và context

Có thể đăng ký một test ObservationHandler để xác minh:

- Handler nhận sự kiện start.
- Current observation tồn tại bên trong scope.
- Scope được đóng sau khi khối mã kết thúc.
- Error được ghi nhận khi khối mã ném exception.
- Stop luôn được gọi.
- Observation lồng nhau có quan hệ context đúng.

Với ứng dụng có executor hoặc async boundary, kiểm tra context propagation riêng. Test đồng bộ trên một thread không chứng minh context tự truyền qua mọi executor.

## Những sai lầm thường gặp

**Cho rằng gọi observe tự động tạo Timer.** Observation cần handler metrics phù hợp. Registry không có handler thì không có meter được tạo.

**Tạo ObservationRegistry mới trong mỗi method.** Registry mới có thể không có handler và không chia sẻ context với Spring Boot. Inject registry từ application context.

**Gọi start/stop thủ công bên trong observe.** observe đã quản lý lifecycle. Chọn observe hoặc lifecycle thủ công cho mỗi Observation.

**Quên đóng Scope hoặc gọi stop khi exception.** Dùng try-with-resources cho Scope và finally cho stop trong lifecycle thủ công.

**Nhầm scope với async context propagation.** Scope thường gắn với thread hiện tại. Qua executor hoặc reactive boundary cần context propagation phù hợp.

**Đưa ID duy nhất vào low-cardinality key-value.** Điều này có thể làm tăng cardinality của metrics. Dùng high-cardinality attribute cho trace khi phù hợp và an toàn.

**Ghi dữ liệu nhạy cảm vào high-cardinality key-value.** Thuộc tính trace vẫn được gửi đến backend và cần tuân thủ chính sách bảo vệ dữ liệu.

**Đo thời gian submit async thay vì thời gian hoàn tất.** observe đồng bộ kết thúc khi khối mã trả về. Muốn đo toàn bộ async lifecycle cần cơ chế theo dõi completion.

**Tạo Observation cho mọi helper nhỏ.** Quá nhiều Observation làm trace phức tạp và tạo metrics dư thừa. Chọn ranh giới có ý nghĩa vận hành.

**Đăng ký handler metrics trùng với auto-configuration.** Có thể ghi meter lặp. Kiểm tra handler hiện có trước khi thêm.

## Checklist dùng observe cho khối mã đồng bộ

Trước khi đưa Observation vào một đoạn code, hãy xác minh:

1. Tên Observation ổn định và mô tả hoạt động rõ ràng chưa?
2. Khối mã được truyền vào observe có đúng ranh giới cần đo không?
3. ObservationRegistry được inject từ Spring context chưa?
4. Có handler metrics/tracing phù hợp được đăng ký không?
5. Khối mã trả về kết quả có được observe và trả lại đúng không?
6. Exception có được ghi nhận rồi truyền tiếp không?
7. Nếu dùng lifecycle thủ công, Scope có được đóng và stop có nằm trong finally không?
8. Các lời gọi con có cần current observation và scope không?
9. Context có cần truyền qua executor hoặc thread khác không?
10. Low-cardinality key-value có tập giá trị hữu hạn không?
11. High-cardinality attributes có an toàn và chỉ dùng khi cần không?
12. Kiểm thử có xác minh handler, meter và lifecycle chứ không chỉ xác minh method chạy không?

## Kết luận

Observation.observe(...) là cách thuận tiện để quản lý lifecycle của một khối mã đồng bộ. Nó bao quanh thao tác, mở scope trong lúc thực thi, ghi nhận lỗi khi cần và kết thúc Observation khi khối mã hoàn tất. Khi cần kiểm soát chi tiết, có thể quản lý thủ công bằng start, openScope, error và stop; Scope phải được đóng và stop phải luôn chạy.

Observation chỉ tạo metrics hoặc traces khi ObservationRegistry có handler tương ứng. Hãy inject registry do Spring Boot quản lý, chọn tên và low-cardinality key-value ổn định, tránh dữ liệu nhạy cảm và kiểm thử cả lifecycle lẫn meter được tạo ra. Dùng Timer trực tiếp cho phép đo thời lượng đơn giản; dùng Observation khi cần một lifecycle và context chung cho nhiều handler.
