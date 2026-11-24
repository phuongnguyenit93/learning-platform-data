# Đo CompletableFuture ở nhánh hoàn tất, lỗi hoặc hủy

Một tác vụ bất đồng bộ có thể kết thúc theo nhiều cách: hoàn tất thành công, hoàn tất với exception hoặc bị hủy. Khi dùng Micrometer để đo thời lượng, cả ba đường đều phải dừng cùng một `Timer.Sample`; nếu chỉ ghi ở nhánh thành công, các lần lỗi và hủy sẽ biến mất khỏi thống kê.

Với `CompletableFuture`, có thể gắn một callback `whenComplete` để quan sát trạng thái cuối. Callback này được gọi đúng một lần khi future hoàn tất, bất kể kết quả là giá trị hay exception. Từ đó, ứng dụng phân loại outcome thành một tập tag nhỏ như `success`, `error`, `cancelled` và `timeout`, rồi ghi thời lượng vào Timer tương ứng.

Bài học này tập trung vào instrumentation thủ công tại ranh giới bất đồng bộ. Cách làm phù hợp khi cần kiểm soát tag, xử lý cancellation hoặc đo một pipeline cụ thể mà không phụ thuộc AOP.

## 1. Ba nhánh kết thúc của CompletableFuture

Một CompletableFuture chỉ chuyển sang trạng thái cuối một lần. Những cách hoàn tất thường gặp:

| Nhánh | Cách hoàn tất | Callback nhận được |
|---|---|---|
| Thành công | `complete(value)`, supplier trả về giá trị | `value != null` hoặc có thể là null; `error == null` |
| Lỗi | `completeExceptionally(error)`, supplier ném exception | `error != null` |
| Hủy | `cancel(...)` | `error` thường là `CancellationException` |

Một số API như `orTimeout(...)` làm future hoàn tất exceptional bằng `TimeoutException`. Đây là lỗi có nguyên nhân timeout nên thường nên có outcome riêng để phân biệt với lỗi nghiệp vụ hoặc lỗi phụ thuộc.

Điểm quan trọng là không phải mọi nhánh đều có giá trị kết quả. Khi future hoàn tất exceptional hoặc bị hủy, callback vẫn được gọi nhưng tham số lỗi chứa nguyên nhân kết thúc.

## 2. Chọn đúng ranh giới bắt đầu phép đo

Timer nên bắt đầu ở thời điểm tương ứng với câu hỏi vận hành cần trả lời.

| Mục tiêu | Thời điểm bắt đầu | Thời điểm kết thúc |
|---|---|---|
| Thời gian end-to-end từ lúc nhận yêu cầu | Trước khi submit tác vụ | Future hoàn tất |
| Thời gian chờ trong executor cộng thời gian xử lý | Trước khi submit | Future hoàn tất |
| Thời gian thực thi bên trong worker | Bên trong supplier hoặc worker | Worker hoàn tất |
| Thời gian của một pipeline nhiều stage | Trước stage đầu tiên | Future cuối cùng hoàn tất |

Ví dụ dưới đây đo từ lúc ứng dụng gọi dependency bất đồng bộ đến khi future kết thúc. Khoảng đo có thể bao gồm thời gian chờ queue, I/O và các stage được nối vào future.

Nếu cần đo riêng thời gian queue và thời gian xử lý, hãy tạo hai meter với ranh giới rõ ràng. Không diễn giải duration end-to-end như CPU time của worker.

## 3. Dùng Timer.Sample cho một thao tác bất đồng bộ

`Timer.Sample` cho phép bắt đầu đo trước khi biết Timer đích. Khi future hoàn tất, ứng dụng chọn Timer dựa trên outcome rồi dừng sample:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

final class OrderMetrics {
    private final MeterRegistry registry;

    OrderMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    Timer.Sample start() {
        return Timer.start(registry);
    }

    void stop(Timer.Sample sample, String outcome) {
        sample.stop(registry.timer(
                "orders.submit.duration",
                "outcome", outcome
        ));
    }
}
~~~

Registry quản lý meter theo tên và tag. Khi gọi lại `registry.timer(...)` với cùng tên và cùng outcome, ứng dụng nhận lại meter đã đăng ký thay vì tạo một chuỗi thời gian mới cho mỗi request.

Tag `outcome` có tập giá trị hữu hạn. Không đưa order ID, request ID, customer ID hoặc exception message vào tag.

## 4. Gắn callback cho cả ba nhánh

Ví dụ một service gọi gateway bất đồng bộ:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeoutException;

final class OrderService {
    private final OrderGateway gateway;
    private final MeterRegistry registry;

    OrderService(OrderGateway gateway, MeterRegistry registry) {
        this.gateway = gateway;
        this.registry = registry;
    }

    CompletableFuture<Receipt> submit(Order order) {
        Timer.Sample sample = Timer.start(registry);
        CompletableFuture<Receipt> operation;

        try {
            operation = gateway.submitAsync(order);
        } catch (RuntimeException | Error error) {
            record(sample, "error");
            throw error;
        }

        if (operation == null) {
            record(sample, "contract_error");
            throw new IllegalStateException(
                    "OrderGateway returned a null CompletableFuture"
            );
        }

        operation.whenComplete((receipt, failure) ->
                record(sample, classify(failure)));

        return operation;
    }

    private void record(Timer.Sample sample, String outcome) {
        Timer timer = registry.timer(
                "orders.submit.duration",
                "outcome", outcome
        );
        sample.stop(timer);
    }

    private static String classify(Throwable failure) {
        if (failure == null) {
            return "success";
        }

        Throwable cause = unwrap(failure);
        if (cause instanceof CancellationException) {
            return "cancelled";
        }
        if (cause instanceof TimeoutException) {
            return "timeout";
        }
        return "error";
    }

    private static Throwable unwrap(Throwable failure) {
        Throwable current = failure;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

Callback `whenComplete` quan sát kết quả mà không thay đổi giá trị thành công hoặc chủ động phục hồi exception của future nguồn. Trong ví dụ, service trả lại chính future nguồn sau khi gắn callback. Vì vậy, nếu caller hủy future được trả về, callback gắn trên future đó sẽ nhận trạng thái cancellation.

Phần bắt exception đồng bộ xử lý trường hợp `gateway.submitAsync()` ném lỗi trước khi trả về future. Nếu bỏ nhánh này, sample đã bắt đầu nhưng không có callback nào để dừng nó.

Không trả `null` cho API bất đồng bộ. Ví dụ ghi nhận một outcome hợp đồng riêng rồi ném lỗi để caller nhận biết lỗi lập trình hoặc tích hợp.

## 5. Vì sao dùng whenComplete?

Các callback của CompletionStage có ngữ nghĩa khác nhau:

| API | Khi thành công | Khi lỗi hoặc hủy | Mục đích |
|---|---|---|---|
| `thenApply` | Được gọi | Bỏ qua nhánh lỗi | Biến đổi giá trị thành công |
| `exceptionally` | Bỏ qua | Được gọi để phục hồi hoặc biến đổi lỗi | Xử lý nhánh lỗi |
| `handle` | Được gọi | Được gọi | Quan sát và biến đổi cả kết quả lẫn lỗi |
| `whenComplete` | Được gọi | Được gọi | Quan sát kết quả cuối mà không chủ động biến đổi nó |

Đo thời lượng là một tác dụng phụ quan sát. `whenComplete` phù hợp vì nó chạy ở cả hai trạng thái kết thúc và giữ nguyên kết quả/lỗi của future nguồn khi callback không ném exception.

Không nên chỉ dùng `thenApply` để dừng Timer. Khi tác vụ lỗi hoặc bị hủy, `thenApply` không chạy và sample sẽ không được ghi.

## 6. Phân biệt lỗi, cancellation và timeout

Không phải mọi `Throwable` đều là lỗi nghiệp vụ. Cần phân loại theo nguyên nhân gốc:

- `CancellationException`: future bị hủy.
- `TimeoutException`: thao tác kết thúc vì timeout.
- Exception khác: thao tác kết thúc do lỗi.

Một số stage bọc nguyên nhân trong `CompletionException` hoặc `ExecutionException`. Hàm `unwrap` loại bỏ các wrapper này trước khi phân loại.

Không phân loại theo message như `"timeout after 2s"` hoặc `"user cancelled"`; message có thể thay đổi, được bản địa hóa hoặc chứa dữ liệu động. Hãy dựa trên kiểu exception và trạng thái được kiểm soát.

Nếu ứng dụng có nhiều loại lỗi nghiệp vụ, hãy ánh xạ về một tập nhỏ:

| Nguyên nhân | Outcome đề xuất |
|---|---|
| Hủy bởi caller | `cancelled` |
| Hết thời gian chờ | `timeout` |
| Dependency từ chối hoặc không khả dụng | `dependency_error` |
| Lỗi xử lý nghiệp vụ | `processing_error` |
| Lỗi chưa phân loại | `error` |

Chỉ thêm chiều phân loại nếu nó hỗ trợ dashboard hoặc alert thực tế. Mỗi giá trị mới làm tăng số chuỗi thời gian theo số tổ hợp tag.

## 7. Cancellation phải xảy ra trên future được đo

CompletableFuture có thể tạo ra nhiều stage phụ thuộc:

~~~java
CompletableFuture<Result> source = gateway.callAsync();
CompletableFuture<Result> transformed =
        source.thenApply(this::mapResult);
~~~

Nếu Timer đo toàn bộ pipeline, hãy gắn callback vào `transformed`, vì đó là stage cuối mà caller chờ. Nếu Timer chỉ đo gateway, gắn callback vào `source`.

Hủy một dependent future không tự động hủy future upstream. Ví dụ:

~~~java
CompletableFuture<Result> source = gateway.callAsync();
CompletableFuture<Result> dependent =
        source.whenComplete(this::observe);

dependent.cancel(true);
~~~

Hủy `dependent` không bảo đảm `source` bị hủy. Callback được gắn trên `source` chỉ chạy khi `source` đi đến trạng thái cuối. Vì vậy, hãy xác định future nào đại diện cho thao tác cần đo và future nào caller thực sự có quyền hủy.

Trong ví dụ ở phần 4, callback được gắn vào `operation` rồi service trả lại chính `operation`. Caller hủy đối tượng đó thì trạng thái cancellation được quan sát trực tiếp.

Nếu API cố ý trả một stage phụ thuộc, cần xác định rõ hợp đồng cancellation: hủy stage ngoài có dừng công việc nguồn hay chỉ hủy việc chờ kết quả? Nếu cần truyền cancellation ngược lên nguồn, ứng dụng phải triển khai chính sách đó rõ ràng.

## 8. cancel(true) không bảo đảm worker đã dừng

Khi gọi:

~~~java
future.cancel(true);
~~~

CompletableFuture chuyển sang trạng thái cancelled và callback hoàn tất được gọi. Tham số `mayInterruptIfRunning` không được dùng để điều khiển xử lý trong implementation CompletableFuture; không nên kỳ vọng thread thực hiện supplier sẽ bị interrupt. Supplier có thể tiếp tục chạy nếu executor hoặc thư viện không hỗ trợ cơ chế hủy riêng.

Timer trong bài đo thời gian đến khi future được đánh dấu cancelled. Nó không chứng minh công việc nền đã ngừng sử dụng CPU, kết nối hoặc tài nguyên khác.

Nếu cần đo vòng đời worker thật sự, đặt instrumentation ở worker hoặc dùng LongTaskTimer bắt đầu khi worker thực sự chạy và dừng trong `finally` của worker. Hai số đo trả lời hai câu hỏi khác nhau:

- Future latency: caller chờ bao lâu trước khi nhận một trạng thái cuối.
- Worker duration: công việc nền thực sự chạy bao lâu.

## 9. Timeout và completeOnTimeout

Với `orTimeout`, future hoàn tất exceptional bằng TimeoutException:

~~~java
CompletableFuture<Receipt> future = gateway.submitAsync(order)
        .orTimeout(2, TimeUnit.SECONDS);
~~~

Nếu callback được gắn vào future sau `orTimeout`, outcome có thể được phân loại thành `timeout`.

Với `completeOnTimeout`, future hoàn tất bình thường bằng giá trị fallback:

~~~java
CompletableFuture<Receipt> future = gateway.submitAsync(order)
        .completeOnTimeout(fallbackReceipt, 2, TimeUnit.SECONDS);
~~~

Callback `whenComplete` chỉ thấy một kết quả thành công và không thể tự biết đó là kết quả thật hay fallback do timeout. Nếu cần tag timeout riêng, hãy ghi nhận timeout bằng một tín hiệu tường minh hoặc dùng `orTimeout` để thể hiện timeout là exceptional completion.

Khi thêm timeout, xác định rõ future nào được đo. Nếu Timer gắn vào future gốc còn caller chờ future đã áp timeout, hai mốc kết thúc có thể khác nhau.

## 10. Pipeline nhiều stage: đo một stage hay toàn pipeline?

Giả sử một thao tác gồm ba bước:

~~~java
CompletableFuture<Receipt> pipeline =
        gateway.submitAsync(order)
                .thenCompose(this::loadDetailsAsync)
                .thenApply(this::buildReceipt);
~~~

Có hai lựa chọn instrumentation:

1. Gắn Timer vào future trả về từ `gateway.submitAsync` để đo riêng thời gian gateway.
2. Gắn Timer vào `pipeline` để đo toàn bộ từ lúc submit đến khi tạo receipt xong.

Ví dụ:

~~~java
Timer.Sample sample = Timer.start(registry);

CompletableFuture<Receipt> pipeline = gateway.submitAsync(order)
        .thenCompose(this::loadDetailsAsync)
        .thenApply(this::buildReceipt);

pipeline.whenComplete((receipt, failure) -> {
    sample.stop(registry.timer(
            "orders.pipeline.duration",
            "outcome", classify(failure)
    ));
});

return pipeline;
~~~

Đo pipeline cuối giúp tính cả thời gian các stage nối tiếp và thời gian chờ giữa chúng. Nếu mỗi stage cũng có Timer riêng, các số đo có thể lồng nhau; không cộng các duration lồng nhau để suy ra thời gian end-to-end vì sẽ đếm trùng thời gian chờ.

## 11. Một sample chỉ dừng một lần

Mỗi lần gọi nghiệp vụ cần một `Timer.Sample` riêng. Không chia sẻ sample giữa nhiều request, không lưu sample trong singleton field và không gọi `stop()` ở nhiều callback khác nhau.

Mẫu sai thường gặp:

~~~java
future.thenAccept(value -> sample.stop(successTimer));
future.exceptionally(error -> {
    sample.stop(errorTimer);
    return null;
});
future.whenComplete((value, error) -> sample.stop(finalTimer));
~~~

Ở đây nhiều callback cùng cố ghi một sample. Kết quả có thể là nhiều lần ghi hoặc số liệu khó diễn giải. Chọn một callback terminal duy nhất:

~~~java
future.whenComplete((value, error) ->
        sample.stop(timerFor(classify(error))));
~~~

CompletableFuture có một trạng thái cuối, do đó một callback gắn trên đúng future sẽ được gọi một lần. Nếu cần ghi thêm counter cho cancellation hoặc error, hãy thực hiện trong cùng callback và bảo đảm mỗi lần hoàn tất chỉ tăng một counter outcome.

## 12. Không làm thay đổi kết quả nghiệp vụ trong callback đo

`whenComplete` trả về một CompletionStage mới. Callback được gắn vào future nguồn; nếu callback ném exception, stage phụ thuộc có thể hoàn tất exceptional do lỗi callback. Vì vậy, mã instrumentation cần đơn giản và tránh ném lỗi.

Trong ví dụ phần 4, service giữ lại future nguồn và trả chính nó. Stage phụ thuộc được tạo bởi `whenComplete` chỉ dùng để thực hiện side effect quan sát. Nếu callback ghi metrics có thể thất bại do cấu hình hoặc code tùy chỉnh, hãy xử lý lỗi instrumentation riêng theo chính sách của ứng dụng để tránh che khuất kết quả nghiệp vụ.

Không dùng `handle` để biến mọi lỗi thành kết quả thành công chỉ nhằm dừng Timer. Điều đó làm thay đổi hợp đồng của future và có thể khiến caller không còn nhận được exception gốc.

## 13. Context và thread hoàn tất

Callback `whenComplete` có thể chạy trên thread hoàn tất future. Thread đó có thể khác thread đã tạo sample:

- Future hoàn tất ngay khi callback được đăng ký: callback có thể chạy ngay trên thread đăng ký.
- Future hoàn tất sau trên executor: callback thường chạy trên thread hoàn tất.
- Stage được hoàn tất bởi một I/O client: callback có thể chạy trên thread quản lý I/O của client.

`Timer.Sample` được truyền trực tiếp qua closure, nên không cần dựa vào ThreadLocal để dừng Timer. Tuy nhiên, MDC, security context hoặc tracing context là vấn đề riêng. Nếu callback cần các context đó, dùng cơ chế context propagation phù hợp thay vì giả định chúng tự chuyển qua mọi executor.

Không thực hiện công việc blocking nặng trong callback hoàn tất nếu callback đang chạy trên event-loop hoặc I/O thread. Hãy ghi metrics nhanh rồi chuyển phần xử lý nặng sang executor phù hợp.

## 14. Theo dõi future đang pending bằng LongTaskTimer

Timer chỉ ghi nhận duration khi future hoàn tất. Một future bị treo có thể không xuất hiện trong count hoặc percentile của Timer.

Nếu cần quan sát số tác vụ đang hoạt động, có thể kết hợp LongTaskTimer:

~~~java
LongTaskTimer activeTimer = registry.more()
        .longTaskTimer("orders.submit.active");

LongTaskTimer.Sample active = activeTimer.start();
Timer.Sample completed = Timer.start(registry);

operation.whenComplete((value, error) -> {
    active.stop();
    completed.stop(registry.timer(
            "orders.submit.duration",
            "outcome", classify(error)
    ));
});
~~~

Ở đây:

- LongTaskTimer phản ánh future còn pending và thời lượng đã trôi qua kể từ lúc submit.
- Timer phản ánh duration của lần đã kết thúc theo outcome.

Nếu future không bao giờ hoàn tất, LongTaskTimer vẫn hiển thị future đang active cho đến khi stage chuyển sang trạng thái cuối như success, error, cancellation hoặc timeout. Nếu cancellation chỉ đổi trạng thái future trong khi worker tiếp tục chạy, sample này dừng theo future; muốn đo vòng đời worker thực tế, hãy bắt đầu và dừng một LongTaskTimer riêng bên trong worker.

## 15. Kiểm thử nhánh thành công

Dùng `SimpleMeterRegistry` và một future do test điều khiển. Không dùng `Thread.sleep()` để chờ:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.junit.jupiter.api.Test;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeoutException;

import static org.assertj.core.api.Assertions.assertThat;

class AsyncMeasurementTest {
    @Test
    void recordsSuccessOnlyWhenFutureCompletes() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        CompletableFuture<String> future = new CompletableFuture<>();
        Timer.Sample sample = Timer.start(registry);
        Timer successTimer = registry.timer(
                "operation.duration",
                "outcome", "success"
        );

        future.whenComplete((value, error) ->
                sample.stop(registry.timer(
                        "operation.duration",
                        "outcome", classify(error)
                )));

        assertThat(successTimer.count()).isZero();

        future.complete("done");

        assertThat(future.join()).isEqualTo("done");
        assertThat(successTimer.count()).isEqualTo(1);
    }

    private static String classify(Throwable error) {
        if (error == null) {
            return "success";
        }
        Throwable cause = unwrap(error);
        if (cause instanceof CancellationException) {
            return "cancelled";
        }
        if (cause instanceof TimeoutException) {
            return "timeout";
        }
        return "error";
    }

    private static Throwable unwrap(Throwable error) {
        Throwable current = error;
        while ((current instanceof CompletionException
                || current instanceof ExecutionException)
                && current.getCause() != null) {
            current = current.getCause();
        }
        return current;
    }
}
~~~

Kiểm thử xác minh count chưa tăng khi future pending và tăng sau khi hoàn tất thành công. Duration cụ thể phụ thuộc clock; nếu cần kiểm tra chính xác, dùng MockClock của Micrometer để điều khiển thời gian.

## 16. Kiểm thử nhánh lỗi

Hoàn tất future bằng exception:

~~~java
@Test
void recordsErrorWhenFutureCompletesExceptionally() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    CompletableFuture<String> future = new CompletableFuture<>();
    Timer.Sample sample = Timer.start(registry);
    Timer errorTimer = registry.timer(
            "operation.duration",
            "outcome", "error"
    );

    future.whenComplete((value, error) ->
            sample.stop(registry.timer(
                    "operation.duration",
                    "outcome", classify(error)
            )));

    future.completeExceptionally(
            new IllegalStateException("dependency unavailable")
    );

    assertThat(errorTimer.count()).isEqualTo(1);
}
~~~

Đây là method test bổ sung trong cùng lớp test ở phần trước. Helper `classify` và các import đã khai báo ở đó được dùng lại.

Future vẫn giữ trạng thái exceptional; callback chỉ ghi metrics. Test nên kiểm tra thêm rằng caller gọi `join()` vẫn nhận `CompletionException` với nguyên nhân gốc phù hợp.

## 17. Kiểm thử nhánh hủy

Hủy future trực tiếp:

~~~java
@Test
void recordsCancellationWhenFutureIsCancelled() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    CompletableFuture<String> future = new CompletableFuture<>();
    Timer.Sample sample = Timer.start(registry);
    Timer cancelledTimer = registry.timer(
            "operation.duration",
            "outcome", "cancelled"
    );

    future.whenComplete((value, error) ->
            sample.stop(registry.timer(
                    "operation.duration",
                    "outcome", classify(error)
            )));

    assertThat(future.cancel(true)).isTrue();
    assertThat(future.isCancelled()).isTrue();

    assertThat(cancelledTimer.count()).isEqualTo(1);
}
~~~

Helper `classify` ở phần 15 đã phân loại `CancellationException`. Test này xác minh future bị hủy trực tiếp. Nếu ứng dụng dùng nhiều stage phụ thuộc, hãy kiểm thử cancellation trên đúng stage mà Timer đang quan sát.

## 18. Kiểm thử timeout

Với timeout, không cần đợi hai giây thực:

~~~java
@Test
void recordsTimeoutAsItsOwnOutcome() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    CompletableFuture<String> future = new CompletableFuture<>();
    Timer.Sample sample = Timer.start(registry);
    Timer timeoutTimer = registry.timer(
            "operation.duration",
            "outcome", "timeout"
    );

    future.whenComplete((value, error) ->
            sample.stop(registry.timer(
                    "operation.duration",
                    "outcome", classify(error)
            )));

    future.completeExceptionally(new TimeoutException("deadline exceeded"));

    assertThat(timeoutTimer.count()).isEqualTo(1);
}
~~~

Đây là method test bổ sung trong cùng lớp test; helper `classify` được dùng lại.

Đây là unit test cho nhánh phân loại timeout. Integration test cho `orTimeout` cần xác minh scheduler timeout và future thực tế được áp dụng đúng.

## 19. Kiểm thử lỗi đồng bộ trước khi có future

Một phương thức tạo future có thể ném exception trước khi trả về:

~~~java
CompletableFuture<Result> start() {
    Timer.Sample sample = Timer.start(registry);
    try {
        CompletableFuture<Result> future = gateway.startAsync();
        future.whenComplete((result, error) ->
                sample.stop(registry.timer(
                        "operation.duration",
                        "outcome", classify(error)
                )));
        return future;
    } catch (RuntimeException | Error error) {
        sample.stop(registry.timer(
                "operation.duration",
                "outcome", "error"
        ));
        throw error;
    }
}
~~~

Test cần xác minh:

- Exception đồng bộ vẫn được ném cho caller.
- Timer outcome `error` tăng đúng một lần.
- Không có callback nào được đăng ký nếu gateway chưa trả future.

Đừng chỉ test exceptional completion; lỗi đồng bộ xảy ra trước khi future tồn tại là một đường thực thi riêng.

## 20. Kiểm tra số liệu trên Prometheus

Timer với tag `outcome` có thể được xuất thành các chuỗi thời gian count và sum. Tên chính xác phụ thuộc naming convention và exporter:

~~~promql
sum by (outcome) (
  rate(orders_submit_duration_seconds_count[5m])
)
~~~

Tỷ lệ lỗi:

~~~promql
sum(rate(orders_submit_duration_seconds_count{outcome="error"}[5m]))
/
sum(rate(orders_submit_duration_seconds_count[5m]))
~~~

Tỷ lệ hủy:

~~~promql
sum(rate(orders_submit_duration_seconds_count{outcome="cancelled"}[5m]))
/
sum(rate(orders_submit_duration_seconds_count[5m]))
~~~

Các biểu thức cần xử lý trường hợp mẫu số bằng 0 trong dashboard hoặc alert. Kiểm tra scrape output để xác nhận tên metric và label thực tế.

Không đưa exception message vào label Prometheus. Nếu cần tìm một lỗi cụ thể, dùng trace ID trong trace hoặc log có cấu trúc rồi liên kết với metrics ở mức operation.

## 21. Các lỗi thường gặp

**Chỉ ghi Timer ở nhánh thành công.** Dùng `whenComplete` để nhận cả thành công, lỗi và hủy.

**Dùng thenApply để đo mọi kết quả.** thenApply chỉ chạy khi thành công; nhánh exceptional và cancellation bị bỏ qua.

**Dùng exceptionally để đo toàn bộ.** exceptionally chỉ xử lý nhánh lỗi và có thể phục hồi kết quả; nó không quan sát thành công.

**Không xử lý exception đồng bộ.** Nếu lời gọi tạo future ném exception trước khi trả về, callback không được đăng ký. Ghi sample trong catch rồi ném lại lỗi.

**Không phân loại CancellationException.** Cancellation thường được biểu diễn như exceptional completion. Kiểm tra nguyên nhân gốc trước khi gán outcome error.

**Cho rằng cancel(true) dừng thread.** Cancellation đánh dấu future; worker có thể tiếp tục chạy. Đo riêng worker nếu cần biết thời gian chạy thực.

**Gắn callback vào sai stage.** Đo gateway thì quan sát future gateway; đo toàn pipeline thì quan sát future cuối cùng.

**Hủy dependent stage và mong upstream bị hủy.** Cancellation không tự động truyền ngược qua mọi quan hệ CompletionStage.

**Dừng sample ở nhiều callback.** Một sample cho một thao tác, một callback terminal để tránh ghi nhiều lần.

**Dùng tag có cardinality cao.** Chỉ dùng outcome và nhóm nghiệp vụ hữu hạn; định danh cụ thể để trong log/trace.

**Dùng Timer để quan sát tác vụ đang pending.** Timer chỉ ghi khi hoàn tất. Dùng LongTaskTimer hoặc Gauge cho trạng thái active.

## 22. Checklist triển khai

Trước khi đưa instrumentation bất đồng bộ vào production, hãy xác minh:

- [ ] Timer bắt đầu ở đúng ranh giới submit hoặc worker theo mục tiêu đo.
- [ ] Một Timer.Sample được tạo cho mỗi thao tác.
- [ ] Một callback terminal được gắn vào đúng CompletableFuture.
- [ ] Thành công được ghi với outcome `success`.
- [ ] Exception được ghi với outcome `error` hoặc nhóm lỗi hữu hạn.
- [ ] Cancellation được ghi với outcome `cancelled`.
- [ ] Timeout được phân loại riêng nếu có yêu cầu vận hành.
- [ ] Lỗi đồng bộ trước khi trả future cũng dừng sample.
- [ ] Future trả về không bị thay đổi semantics ngoài ý muốn.
- [ ] Đã xác định cancellation của caller tác động lên future nào.
- [ ] Pipeline được đo ở đúng stage cuối hoặc stage thành phần.
- [ ] Callback không thực hiện công việc blocking và không làm hỏng kết quả nghiệp vụ.
- [ ] Tag không chứa ID hoặc message động.
- [ ] Future pending được theo dõi bằng LongTaskTimer/Gauge nếu cần.
- [ ] Có test cho success, error, cancellation, timeout và synchronous throw.

## 23. Kết luận

Để đo một CompletableFuture đầy đủ, hãy bắt đầu Timer.Sample tại ranh giới nghiệp vụ và gắn một callback `whenComplete` vào future đại diện cho thao tác. Callback phân loại thành công, lỗi, timeout hoặc cancellation rồi dừng sample đúng một lần. Lỗi đồng bộ trước khi future được trả về cần được ghi trong catch riêng.

Hãy quan sát đúng stage mà caller chờ, hiểu rằng hủy dependent future không tự động hủy upstream và `cancel(true)` không bảo đảm worker đã dừng. Timer mô tả thời lượng đến trạng thái cuối của future; LongTaskTimer hoặc Gauge bổ sung thông tin về tác vụ còn pending. Với outcome tag có tập giá trị hữu hạn và kiểm thử điều khiển được, metrics sẽ phản ánh đủ cả ba nhánh kết thúc mà không làm thay đổi hợp đồng bất đồng bộ.

## Tài liệu tham khảo

- [Micrometer – Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – MeterRegistry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Java – CompletableFuture](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java – CompletionStage](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletionStage.html)
