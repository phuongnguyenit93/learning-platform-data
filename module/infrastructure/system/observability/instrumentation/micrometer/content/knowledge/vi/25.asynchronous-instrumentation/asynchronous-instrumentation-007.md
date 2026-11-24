# Tránh ghi nhận nhiều lần khi có đăng ký lại hoặc retry

Trong xử lý bất đồng bộ, cùng một thao tác có thể tạo ra nhiều callback, listener hoặc lần thực thi lại. Nếu mỗi callback đều tăng Counter hoặc dừng Timer mà không kiểm soát, một sự kiện nghiệp vụ có thể bị ghi nhận nhiều lần. Số liệu khi đó phản ánh số lần callback chạy thay vì số thao tác thực sự.

Để tránh lỗi này, cần phân biệt ba việc: đăng ký meter vào registry, đăng ký callback nhận sự kiện và ghi nhận một lần hoàn tất. Micrometer có thể tái sử dụng meter có cùng định danh, nhưng điều đó không tự ngăn một listener bị đăng ký hai lần hoặc một callback bị xử lý lặp.

## 1. Ba loại đăng ký và ghi nhận khác nhau

Các thao tác sau có mục đích khác nhau:

| Thao tác | Ví dụ | Điều cần kiểm soát |
| --- | --- | --- |
| Đăng ký meter | registry.counter("jobs.completed") | Identity của meter: tên và tags |
| Đăng ký callback/listener | eventBus.addListener(handler) | Số subscription đang hoạt động |
| Ghi nhận sự kiện | counter.increment() hoặc sample.stop(timer) | Mỗi logical event chỉ được ghi đúng theo semantics đã chọn |

Một meter có thể được đăng ký một lần rồi nhận hàng nghìn lần increment. Ngược lại, đăng ký cùng listener hai lần có thể khiến một event gọi handler hai lần, dù cả hai lần đều ghi vào cùng một Counter.

~~~mermaid
flowchart TD
    A["Khởi tạo metrics"] --> B["Đăng ký Meter vào Registry"]
    B --> C["Đăng ký listener / callback"]
    C --> D["Event được phát"]
    D --> E{"Đã xử lý event này?"}
    E -- "Chưa" --> F["Ghi Counter / Timer một lần"]
    E -- "Rồi" --> G["Bỏ qua bản giao lặp"]
    F --> H["Kết thúc"]
    G --> H
~~~

Điểm quan trọng là idempotency phải được áp dụng ở đúng lớp. Meter identity xử lý đăng ký meter; subscription lifecycle xử lý callback; event identity hoặc completion guard xử lý việc ghi nhận.

## 2. Đăng ký lại cùng meter không đồng nghĩa với tăng Counter

Micrometer định danh meter bằng Meter.Id, trong đó có tên và tags. Khi gọi lại registry.counter() với cùng tên và cùng tags trên cùng registry, registry thường trả về meter đã đăng ký. Việc lấy lại tham chiếu không tự tăng giá trị Counter.

~~~java
Counter first = registry.counter(
    "jobs.completed",
    "queue", "email"
);

Counter second = registry.counter(
    "jobs.completed",
    "queue", "email"
);

first.increment();
~~~

Hai biến thường tham chiếu đến cùng một meter identity trong registry đó. Sau một lần increment, giá trị chỉ tăng một lần.

Tuy nhiên, các trường hợp sau tạo identity khác:

- Khác tên meter.
- Khác key tags.
- Khác tag value.
- Khác registry.

Ví dụ queue=email và queue=report là hai series riêng. Nếu tag chứa request ID hoặc job ID, mỗi giá trị mới có thể tạo thêm một series và làm cardinality tăng nhanh.

Không dựa vào hành vi tái sử dụng meter để chống duplicate event. Nếu cùng một event gọi increment() hai lần, Counter vẫn tăng hai lần dù cả hai lần dùng đúng một meter.

## 3. Đăng ký listener nhiều lần có thể nhân đôi sự kiện

Một lỗi thường gặp là mỗi lần component khởi động lại, refresh cấu hình hoặc reconnect đều gọi addListener() nhưng subscription cũ chưa được đóng.

~~~java
public void start() {
    eventBus.addListener(this::onJobCompleted);
}

private void onJobCompleted(JobCompleted event) {
    completedJobs.increment();
}
~~~

Nếu start() được gọi ba lần, một event có thể gọi handler ba lần. Meter vẫn chỉ có một identity, nhưng Counter tăng ba lần.

Hãy quản lý subscription như một tài nguyên có vòng đời. Cần biết lúc nào listener được tạo, lúc nào được hủy và liệu một lần start mới có được phép tạo subscription mới hay không.

Ví dụ dưới đây dùng một handle để tránh đăng ký lặp khi component đã hoạt động:

~~~java
import java.util.function.Consumer;

interface EventSource {
    AutoCloseable addListener(Consumer<JobCompleted> listener);
}

public final class JobMetricsListener implements AutoCloseable {

    private final EventSource eventSource;
    private final Counter completedJobs;
    private AutoCloseable subscription;

    public JobMetricsListener(
        EventSource eventSource,
        MeterRegistry registry
    ) {
        this.eventSource = eventSource;
        this.completedJobs = registry.counter("jobs.completed");
    }

    public synchronized void start() {
        if (subscription != null) {
            return;
        }
        subscription = eventSource.addListener(this::onJobCompleted);
    }

    private void onJobCompleted(JobCompleted event) {
        completedJobs.increment();
    }

    @Override
    public synchronized void close() throws Exception {
        if (subscription != null) {
            subscription.close();
            subscription = null;
        }
    }
}
~~~

start() chỉ tạo subscription khi chưa có handle. close() hủy subscription hiện tại và cho phép đăng ký lại sau đó. Trong ứng dụng thực tế, có thể dùng lifecycle hook của Spring như PostConstruct, PreDestroy, SmartLifecycle hoặc cơ chế quản lý subscription của thư viện.

Đóng listener không nhất thiết hủy callback đã được đưa vào hàng đợi trước thời điểm close. Nếu event source có thể giao lại event hoặc callback cũ còn đang chạy, vẫn cần cơ chế chống xử lý trùng ở cấp event.

## 4. Phân biệt đăng ký lại với event được giao lại

Hai tình huống dễ bị nhầm:

- **Duplicate subscription:** cùng một component đăng ký nhiều listener đang hoạt động; một lần publish kích hoạt nhiều callback.
- **Duplicate delivery:** event source giao lại cùng một event, ví dụ message broker redelivery sau timeout hoặc consumer restart.

Hủy subscription dư giải quyết trường hợp thứ nhất. Nó không giải quyết trường hợp thứ hai vì broker có thể giao cùng message nhiều lần ngay cả khi chỉ có một consumer listener.

Nếu event có ID ổn định, có thể dùng ID đó để nhận biết một logical event đã được xử lý:

~~~java
private void onJobCompleted(JobCompleted event) {
    if (!eventDeduplicator.markIfNew(event.eventId())) {
        return;
    }

    completedJobs.increment();
}
~~~

eventDeduplicator là abstraction do ứng dụng triển khai. Với nghiệp vụ quan trọng, việc đánh dấu event đã xử lý cần được lưu bền vững và phối hợp với transaction của phần xử lý nghiệp vụ. Một HashSet trong bộ nhớ chỉ chống lặp trong vòng đời process và có thể tăng không giới hạn nếu không có eviction.

Metrics không phải nguồn dữ liệu giao dịch. Nếu cần số lượng chính xác cho thanh toán, đơn hàng hoặc audit, hãy dùng database/event log làm nguồn sự thật; metrics chỉ phục vụ quan sát vận hành.

## 5. Ghi nhận một lần hoàn tất bằng completion guard

Callback có thể được gọi từ nhiều nhánh cạnh tranh: kết quả thành công, timeout, cancellation hoặc lỗi. Nếu nhiều nhánh cùng kết thúc một operation, cần một điểm thắng duy nhất để dừng Timer.

Dùng AtomicBoolean.compareAndSet(false, true) làm completion guard:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class TimedOperation {

    private final MeterRegistry registry;
    private final Timer.Sample sample;
    private final AtomicBoolean completed = new AtomicBoolean();

    public TimedOperation(MeterRegistry registry) {
        this.registry = registry;
        this.sample = Timer.start(registry);
    }

    public void finish(String outcome) {
        if (!completed.compareAndSet(false, true)) {
            return;
        }

        sample.stop(
            registry.timer(
                "business.operation.duration",
                "outcome", outcome
            )
        );
    }
}
~~~

Chỉ callback đầu tiên chuyển trạng thái từ false sang true và dừng sample. Các callback đến sau không ghi nhận thêm lần nữa. Tag outcome phải thuộc tập giá trị hữu hạn như success, error, timeout hoặc cancelled.

Guard phải thuộc về một logical operation cụ thể. Không dùng một AtomicBoolean dùng chung cho mọi request của singleton service, nếu không operation đầu tiên hoàn tất sẽ chặn mọi lần ghi nhận tiếp theo.

## 6. CompletableFuture: đăng ký nhiều callback và ghi nhận một lần

CompletableFuture hoàn tất một lần, nhưng ứng dụng có thể gắn nhiều dependent callback vào cùng future. Nếu mỗi callback đều dừng cùng một Timer.Sample hoặc tăng cùng Counter, một logical operation có thể bị ghi nhận lặp.

Ví dụ completion guard được chia sẻ giữa các nhánh:

~~~java
public CompletableFuture<Report> generate(ReportRequest request) {
    TimedOperation measurement = new TimedOperation(registry);

    CompletableFuture<Report> future = client.generateAsync(request);

    future.whenComplete((report, error) -> {
        measurement.finish(error == null ? "success" : "error");
    });

    // Một nhánh timeout độc lập cũng có thể cố kết thúc phép đo.
    scheduler.schedule(
        () -> measurement.finish("timeout"),
        10,
        TimeUnit.SECONDS
    );

    return future;
}
~~~

Nếu future hoàn tất trước, callback ghi nhận kết quả và timeout sau đó bị bỏ qua. Nếu timeout đến trước, timeout thắng và callback hoàn tất đến sau không ghi nhận lần thứ hai. Cần quyết định rõ timeout chỉ kết thúc phép đo hay còn phải hủy công việc thực tế; hai hành động này không tự động tương đương.

Mỗi operation phải có một TimedOperation riêng. Nếu callback timeout và callback future cùng dùng chung measurement object, guard mới có thể bảo vệ đúng logical operation đó.

## 7. Retry: phân biệt attempt với logical operation

Retry có nghĩa cùng một logical operation có thể thực hiện nhiều attempt. Số lần attempt và số logical operation là hai đại lượng khác nhau.

Ví dụ một yêu cầu thanh toán thử ba lần mới thành công:

- payment.attempts: ghi nhận ba lần gọi provider.
- business.payment.duration: ghi nhận một lần cho toàn bộ operation, bao gồm cả retry và backoff.

Nếu chỉ có một Counter tên payment.completed nhưng lại increment bên trong mỗi lần retry, số liệu sẽ đếm attempt thành công/thất bại tùy vị trí đặt lệnh, không còn phản ánh số logical payment.

### Đo từng attempt

Tạo Timer.Sample mới cho mỗi lần gọi dependency:

~~~java
private PaymentResult authorizeAttempt(PaymentCommand command) {
    Timer.Sample attempt = Timer.start(registry);
    String outcome = "error";

    try {
        PaymentResult result = paymentGateway.authorize(command);
        outcome = "success";
        return result;
    } catch (RetryablePaymentException ex) {
        outcome = "retryable_error";
        throw ex;
    } finally {
        attempt.stop(
            registry.timer(
                "payment.attempt.duration",
                "outcome", outcome
            )
        );
    }
}
~~~

Mỗi lần authorizeAttempt() được gọi sẽ tạo một observation riêng. Không thêm số attempt, request ID hoặc payment ID làm tag; những giá trị đó không cần thiết để phân tích tổng hợp và có thể tạo cardinality lớn.

### Đo toàn bộ logical operation

Bắt đầu Timer.Sample bên ngoài vòng retry và dừng một lần khi có kết quả cuối:

~~~java
public PaymentResult authorize(PaymentCommand command) {
    Timer.Sample operation = Timer.start(registry);
    String outcome = "error";

    try {
        for (int attempt = 1; ; attempt++) {
            try {
                PaymentResult result = authorizeAttempt(command);
                outcome = "success";
                return result;
            } catch (RetryablePaymentException ex) {
                if (attempt >= MAX_ATTEMPTS) {
                    outcome = "exhausted";
                    throw ex;
                }
                backoff(attempt);
            }
        }
    } finally {
        operation.stop(
            registry.timer(
                "business.payment.duration",
                "outcome", outcome
            )
        );
    }
}
~~~

Timer tổng bao gồm thời gian các attempt và backoff. Mỗi attempt có timer riêng. Cách đặt hai ranh giới này giúp phân biệt dependency chậm với thời gian người dùng phải chờ toàn bộ workflow.

Counter cho số logical operation nên được increment tại một điểm duy nhất theo định nghĩa nghiệp vụ: lúc được tiếp nhận, lúc hoàn tất thành công hoặc lúc kết thúc với bất kỳ outcome nào. Counter attempt được increment bên trong mỗi lần thử. Hãy đặt tên khác nhau cho hai khái niệm.

## 8. Retry của reactive stream: chú ý resubscription

Trong Reactor, retryWhen có thể subscribe lại upstream. Những operator nằm trước retry có thể chạy lại theo mỗi subscription. Nếu tạo sample hoặc increment Counter ở vị trí không phù hợp, số liệu có thể bị nhân lên theo số lần retry.

Ví dụ đo từng attempt:

~~~java
Mono<PaymentResult> attempt = Mono.defer(() -> {
    Timer.Sample sample = Timer.start(registry);

    return paymentClient.authorize(command)
        .doFinally(signal -> {
            String outcome = signal == SignalType.ON_COMPLETE
                ? "success"
                : signal == SignalType.CANCEL
                    ? "cancelled"
                    : "error";

            sample.stop(
                registry.timer(
                    "payment.attempt.duration",
                    "outcome", outcome
                )
            );
        });
});

return attempt.retryWhen(retrySpec);
~~~

Mono.defer tạo sample mới khi upstream được subscribe cho mỗi attempt. doFinally của attempt ghi nhận thời gian attempt tương ứng.

Để đo logical operation, tạo sample bên ngoài phần được retry và đặt điểm kết thúc sau retryWhen:

~~~java
return Mono.defer(() -> {
    Timer.Sample operation = Timer.start(registry);

    return createAttemptPublisher()
        .retryWhen(retrySpec)
        .doFinally(signal -> operation.stop(
            registry.timer(
                "business.payment.duration",
                "outcome", outcomeOf(signal)
            )
        ));
});
~~~

Ở đây doFinally nằm sau retry nên quan sát kết thúc của logical operation sau khi retry hoàn tất hoặc bị hủy. Nếu publisher được subscribe nhiều lần độc lập, mỗi subscription phải có sample riêng; hãy đặt toàn bộ phần tạo sample trong Mono.defer ở ranh giới logical operation để không chia sẻ một sample giữa nhiều subscription.

outcomeOf là hàm ứng dụng ánh xạ signal/kết quả thành tập tag ổn định; nếu cần phân biệt lỗi nghiệp vụ với lỗi kỹ thuật, hãy ánh xạ từ error type hoặc kết quả cuối thay vì exception message.

## 9. Callback có thể đến muộn sau timeout hoặc cancellation

Timeout không nhất thiết dừng công việc nền. Một callback thành công có thể đến sau khi caller đã nhận timeout. Nếu cả hai nhánh cùng ghi Timer, một operation bị tính hai lần hoặc có hai outcome mâu thuẫn.

Hãy quyết định semantics:

- Nếu timeout là kết quả cuối của operation đối với caller, timeout thắng và callback đến muộn không được ghi nhận lại.
- Nếu timeout chỉ là thời gian chờ của caller nhưng công việc vẫn tiếp tục, cần tách metric request.wait.duration và background.execution.duration.
- Nếu công việc được retry ở tầng queue, mỗi lần thực thi có thể là một attempt; logical job chỉ được đếm một lần theo job identity.

Completion guard giúp chọn một terminal outcome. Nó không tự hủy công việc, rollback side effect hoặc bảo đảm event không được xử lý lại sau khi process restart.

## 10. Re-registration của MeterBinder và nhiều registry

MeterBinder.bindTo(registry) có thể được gọi cho các registry khác nhau, ví dụ khi ứng dụng dùng nhiều backend. Đăng ký cùng meter identity vào từng registry là hợp lệ vì mỗi registry quản lý tập meter riêng.

Trong cùng một registry, đăng ký lặp cùng identity thường tái sử dụng meter hiện có. Tuy nhiên:

- Không increment Counter trong bindTo().
- Không phát event nghiệp vụ trong quá trình bind.
- Không tạo listener mới mỗi lần bind nếu binder không sở hữu lifecycle của listener.
- Không giữ một registry toàn cục bên trong binder rồi bỏ qua registry được truyền vào.
- Không giả định một binder chỉ được gọi một lần trong toàn bộ vòng đời ứng dụng.

Binder nên chỉ kết nối nguồn trạng thái với registry. Việc cập nhật trạng thái và ghi nhận event thuộc về luồng nghiệp vụ hoặc callback tương ứng.

## 11. Exactly-once và giới hạn của metrics

Trong hệ thống bất đồng bộ phân tán, delivery thường có semantics at-least-once. Consumer có thể xử lý message, commit nghiệp vụ thành công rồi process dừng trước khi xác nhận message. Broker có thể giao lại message sau khi consumer khởi động lại.

Một AtomicBoolean chỉ bảo vệ các callback trong cùng một object/process. Nó không sống qua restart và không phối hợp transaction với database hoặc broker.

Nếu cần idempotency bền vững:

1. Dùng event ID hoặc idempotency key ổn định.
2. Lưu trạng thái đã xử lý bằng unique constraint hoặc inbox table.
3. Thực hiện dedup và cập nhật nghiệp vụ trong cùng transaction khi có thể.
4. Chỉ phát event tiếp theo sau khi transaction được commit theo thiết kế.
5. Ghi metrics sau khi biết kết quả xử lý/dedup.

Ngay cả khi dedup nghiệp vụ được bảo đảm, việc cập nhật metrics vẫn không phải transaction nguyên tử với database. Process có thể dừng giữa commit nghiệp vụ và increment Counter. Vì vậy, metrics là số đo vận hành có thể sai lệch nhỏ; báo cáo tài chính hoặc số lượng chính thức phải lấy từ nguồn dữ liệu bền vững.

## 12. Tags và cardinality khi ghi nhận retry

Các tag hữu ích:

- outcome=success|error|timeout|cancelled|exhausted
- operation=authorize|capture|refund
- dependency=payment-provider-a nếu tập dependency được giới hạn
- retryable=true|false nếu chiều này có ý nghĩa truy vấn

Tránh:

- attempt=1,2,3,... nếu số lần thử không có giới hạn rõ ràng hoặc tạo quá nhiều series.
- event_id, job_id, payment_id, request_id.
- Exception message, stack trace hoặc URL động.

Nếu cần biết một operation đã thử bao nhiêu lần, có thể ghi một histogram/counter riêng cho số attempt theo nhóm hoặc dùng trace/log để điều tra từng operation. Không biến định danh riêng của từng operation thành tag.

## 13. Kiểm thử chống ghi nhận trùng

Kiểm thử nên mô phỏng callback lặp, timeout cạnh tranh với completion và retry nhiều lần. Ví dụ kiểm tra completion guard:

~~~java
@Test
void recordsOnlyFirstTerminalCallback() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    TimedOperation operation = new TimedOperation(registry);

    operation.finish("success");
    operation.finish("timeout");
    operation.finish("error");

    Timer success = registry.find("business.operation.duration")
        .tag("outcome", "success")
        .timer();
    Timer timeout = registry.find("business.operation.duration")
        .tag("outcome", "timeout")
        .timer();

    assertThat(success).isNotNull();
    assertThat(success.count()).isEqualTo(1L);
    assertThat(timeout).isNull();

    registry.close();
}
~~~

Với listener, cần xác minh:

- Gọi start() nhiều lần chỉ tạo một subscription đang hoạt động.
- Gọi close() rồi start() tạo đúng một subscription mới.
- Một event duy nhất chỉ làm Counter tăng một lần.
- Event được giao lại có cùng event ID được deduplicate theo chính sách.
- Event ID khác nhau vẫn được ghi nhận độc lập.

Với retry, kiểm tra:

- Mỗi attempt được ghi đúng một lần.
- Logical operation chỉ được ghi một lần sau terminal result.
- Backoff nằm trong timer tổng nhưng không nằm trong attempt timer.
- Exhausted, timeout và cancellation có outcome rõ ràng.
- Reactive resubscription tạo sample mới cho mỗi attempt.
- Một publisher được subscribe hai lần tạo hai logical operation samples độc lập.

## 14. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Gọi increment() trong bindTo() | Rebind có thể làm Counter tăng thêm | Chỉ đăng ký meter trong binder |
| Gọi addListener() mỗi lần start mà không giữ handle | Một event gọi nhiều callback | Quản lý subscription lifecycle |
| Nghĩ cùng Meter.Id tự deduplicate event | Callback lặp vẫn tăng Counter nhiều lần | Deduplicate event hoặc completion |
| Increment logical counter bên trong retry | Một operation bị đếm thành nhiều lần | Tách attempt metric và operation metric |
| Dùng chung Timer.Sample cho nhiều attempt | Thời gian bị gộp hoặc dừng nhiều lần | Tạo sample riêng theo attempt |
| Đặt sample reactive ngoài mọi subscription | Nhiều subscription dùng chung sample | Tạo sample trong defer |
| Không xử lý callback đến muộn | Timeout và success cùng được ghi nhận | Dùng terminal guard hoặc tách semantics |
| Chỉ dùng AtomicBoolean cho message redelivery sau restart | Duplicate vẫn xảy ra sau khi process khởi động lại | Dùng durable idempotency key |
| Dùng event ID làm tag | Cardinality tăng không giới hạn | Dùng event ID cho dedup, không dùng làm metric tag |

## 15. Quy trình thiết kế instrumentation idempotent

Khi instrument một luồng bất đồng bộ:

1. Xác định một logical operation và các attempt thuộc về nó.
2. Chọn meter riêng cho số operation, số attempt và duration tương ứng.
3. Đăng ký meter ổn định theo tên và tags có cardinality thấp.
4. Quản lý listener/subscription bằng handle và lifecycle rõ ràng.
5. Dùng event ID để deduplicate delivery nếu nguồn có thể giao lặp.
6. Dùng completion guard để chỉ ghi một terminal result cho một operation trong process.
7. Tạo Timer.Sample mới cho mỗi attempt; giữ một sample riêng cho toàn operation.
8. Với Reactor, đặt sample attempt trong defer và đo logical operation sau retry.
9. Kiểm thử callback lặp, timeout race, cancellation, retry exhaustion và restart/redelivery.
10. Dùng database hoặc event log làm nguồn chính xác cho số liệu nghiệp vụ cần bảo đảm.

Micrometer quản lý meter identity, còn ứng dụng chịu trách nhiệm xác định một sự kiện hoặc operation được ghi nhận bao nhiêu lần. Khi đăng ký lại, hãy quản lý subscription và không tạo side effect trong bước bind. Khi retry, hãy đo attempt và logical operation riêng. Với callback cạnh tranh, dùng completion guard; với message redelivery qua restart, cần idempotency bền vững ở lớp nghiệp vụ. Như vậy metrics mới phản ánh đúng semantics mà dashboard và cảnh báo mong đợi.
