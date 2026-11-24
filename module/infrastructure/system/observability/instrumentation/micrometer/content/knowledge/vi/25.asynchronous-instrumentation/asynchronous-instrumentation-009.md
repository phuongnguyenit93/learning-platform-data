# Kiểm thử hoàn tất chậm, lỗi bất đồng bộ và tác vụ bị hủy

## Mục tiêu

Trong xử lý bất đồng bộ, lời gọi phương thức thường kết thúc trước khi công việc thật sự hoàn tất. Một phương thức có thể trả về CompletableFuture hoặc CompletionStage ngay sau khi gửi tác vụ sang executor, gọi HTTP client hay publish message. Nếu dừng Timer ngay khi phương thức trả về, metric chỉ đo thời gian gửi tác vụ, không đo thời gian chờ kết quả.

Muốn đo đúng latency bất đồng bộ, instrumentation phải giữ trạng thái bắt đầu cho đến khi stage hoàn tất. Đồng thời, nó cần phân biệt kết quả thành công, lỗi, timeout và cancellation. Các trường hợp này có thể có cùng thời lượng nhưng mang ý nghĩa vận hành khác nhau.

Sau bài này, bạn có thể:

- Xác định ranh giới bắt đầu và kết thúc của một thao tác bất đồng bộ.
- Dùng Timer.Sample để ghi thời gian khi CompletionStage hoàn tất.
- Phân loại success, error, timeout và cancelled bằng tag có cardinality thấp.
- Hiểu khác biệt giữa cancellation signal và việc công việc nền thực sự dừng.
- Kiểm thử hoàn tất chậm bằng MockClock, không dùng Thread.sleep().
- Tránh ghi metric hai lần khi có nhiều callback hoặc nhiều lớp instrumentation.

## Vì sao đo bất đồng bộ cần giữ trạng thái đến lúc hoàn tất?

Xét một thao tác gọi dịch vụ từ xa:

~~~java
CompletableFuture<Response> future = client.fetchAsync();
return future;
~~~

Lời gọi fetchAsync() có thể chỉ mất vài mili giây để tạo request và trả về future. Phản hồi có thể đến sau vài trăm mili giây hoặc vài giây. Nếu dùng Timer.record() quanh lời gọi trên, Timer chỉ đo thời gian khởi tạo request.

Hãy phân biệt các khoảng thời gian:

| Khoảng đo | Bắt đầu | Kết thúc | Câu hỏi được trả lời |
|---|---|---|---|
| Submission latency | Trước khi submit/gọi client | Khi nhận được future | Việc gửi tác vụ mất bao lâu? |
| Queue wait | Khi tác vụ được submit | Khi worker bắt đầu chạy | Tác vụ phải chờ bao lâu trong queue? |
| Execution time | Khi worker bắt đầu xử lý | Khi xử lý kết thúc | Phần xử lý trên worker mất bao lâu? |
| End-to-end async latency | Trước khi khởi tạo thao tác | Khi stage hoàn tất | Người gọi phải chờ bao lâu để nhận kết quả cuối cùng? |

Không có một khoảng đo đúng cho mọi câu hỏi. Ví dụ, latency của một lời gọi HTTP bất đồng bộ thường cần bao gồm cả thời gian chờ mạng; thời gian thực thi của callback trên worker lại là một metric khác.

## Dùng Timer.Sample và dừng ở callback hoàn tất

Timer.Sample lưu thời điểm bắt đầu bằng monotonic clock của MeterRegistry. Ta có thể tạo sample trước khi gọi thao tác bất đồng bộ và dừng nó trong callback khi CompletionStage hoàn tất.

Ví dụ đơn giản:

~~~java
Timer.Sample sample = Timer.start(registry);

CompletionStage<Response> stage = client.fetchAsync();
stage.whenComplete((response, error) -> {
    Timer timer = registry.timer("client.request.duration",
            "client", "catalog");
    sample.stop(timer);
});

return stage;
~~~

Timer chỉ được cập nhật khi stage hoàn tất. Nếu stage đang chờ, count của Timer chưa tăng. Thời gian được đo là khoảng từ trước khi gọi client đến lúc stage phát tín hiệu hoàn tất.

Không dùng Timer.record(() -> client.fetchAsync()) cho mục tiêu này. Lambda kết thúc ngay khi trả về CompletionStage, nên thời gian chờ bất đồng bộ nằm ngoài khoảng đo.

### Đăng ký Timer sau khi biết kết quả

Timer.Sample cho phép chọn Timer khi dừng sample. Nhờ đó có thể thêm outcome vào tag dựa trên kết quả cuối cùng:

- success: stage hoàn tất bình thường.
- error: stage hoàn tất ngoại lệ do lỗi xử lý.
- timeout: stage hoàn tất với TimeoutException.
- cancelled: stage hoàn tất do CancellationException.

Giữ các giá trị outcome trong một tập hữu hạn. Không dùng exception message, request ID hoặc dữ liệu đầu vào làm tag.

## Tạo lớp instrumentation cho CompletionStage

Ví dụ sau đo từ lúc bắt đầu gọi hàm cung cấp stage cho đến khi stage nguồn hoàn tất. Nó xử lý cả lỗi đồng bộ khi gọi hàm và lỗi bất đồng bộ khi stage hoàn tất:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.util.Objects;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeoutException;
import java.util.function.Supplier;

public final class AsyncOperationMetrics {
    private final MeterRegistry registry;

    public AsyncOperationMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public <T> CompletionStage<T> observe(
            String operation,
            Supplier<? extends CompletionStage<T>> invocation) {
        Timer.Sample sample = Timer.start(registry);

        final CompletionStage<T> source;
        try {
            source = Objects.requireNonNull(
                    invocation.get(),
                    "invocation must return a CompletionStage"
            );
        } catch (RuntimeException | Error exception) {
            stop(sample, operation, classify(exception));
            throw exception;
        }

        source.whenComplete((result, failure) ->
                stop(sample, operation, classify(failure)));

        // Trả về stage nguồn, không tạo thêm một stage phụ.
        return source;
    }

    private void stop(Timer.Sample sample, String operation, String outcome) {
        Timer timer = registry.timer(
                "async.operation.duration",
                "operation", operation,
                "outcome", outcome
        );
        sample.stop(timer);
    }

    private static String classify(Throwable failure) {
        if (failure == null) {
            return "success";
        }

        Throwable cause = failure;
        while ((cause instanceof CompletionException
                || cause instanceof ExecutionException)
                && cause.getCause() != null) {
            cause = cause.getCause();
        }

        if (cause instanceof CancellationException) {
            return "cancelled";
        }
        if (cause instanceof TimeoutException) {
            return "timeout";
        }
        return "error";
    }
}
~~~

Cách sử dụng:

~~~java
CompletionStage<Profile> profile = metrics.observe(
        "profile.load",
        () -> profileClient.loadAsync(profileId)
);
~~~

Supplier giúp instrumentation bắt đầu sample trước khi gọi client. Nếu truyền một future đã được tạo từ trước, thời gian trước khi gọi observe() sẽ không được tính.

Callback whenComplete được gắn vào stage nguồn. Phương thức whenComplete trả về một stage phụ; ví dụ không trả stage phụ đó mà trả về source. Nhờ vậy, caller vẫn tương tác với chính stage mà client cung cấp. Callback chỉ làm công việc instrumentation ngắn gọn và không nên ném exception.

CompletionStage chỉ hoàn tất một lần, nên callback hoàn tất chỉ ghi một observation. Lỗi đồng bộ khi invocation.get() ném exception đi qua nhánh riêng và cũng chỉ dừng sample một lần. CompletionStage không định nghĩa cancel(); khả năng hủy phụ thuộc API của stage nguồn. Nếu nguồn là CompletableFuture, caller có thể hủy chính future đó. Không giả định toCompletableFuture() trên mọi implementation sẽ hủy computation gốc.

### Giữ tag có cardinality thấp

Tag operation nên là tên thao tác cố định như profile.load, payment.authorize hoặc inventory.reserve. Tag outcome chỉ nên nhận success, error, timeout hoặc cancelled.

Không thêm các tag sau:

- profileId, orderId hoặc requestId.
- URL đầy đủ hoặc query string.
- Exception message.
- Nội dung response hoặc payload.

Nếu cần biết loại exception để điều tra, ghi exception class vào log hoặc trace. Nếu số lớp exception được kiểm soát và thật sự cần phân tích bằng metrics, hãy chuẩn hóa thành một nhóm lỗi hữu hạn thay vì xuất tên exception tùy ý.

## Phân biệt lỗi bất đồng bộ, timeout và cancellation

### Lỗi bất đồng bộ

Khi stage hoàn tất ngoại lệ, whenComplete nhận Throwable ở tham số failure. Với CompletableFuture, lỗi có thể được bọc trong CompletionException; khi dùng get(), lỗi cũng có thể được bọc trong ExecutionException. Hãy bỏ các lớp wrapper này để phân loại nguyên nhân gốc.

Ví dụ:

~~~java
CompletableFuture<Response> source = new CompletableFuture<>();

source.completeExceptionally(
        new IllegalStateException("remote service rejected request")
);
~~~

Instrumentation ghi outcome=error. Metric không nên lưu message của exception làm tag.

### Timeout

CompletableFuture.orTimeout(...) hoàn tất future ngoại lệ bằng TimeoutException nếu không có kết quả trước thời hạn:

~~~java
CompletableFuture<Response> source = client.fetchAsync()
        .toCompletableFuture()
        .orTimeout(2, TimeUnit.SECONDS);
~~~

Nếu stage được instrumentation quan sát là source sau khi áp dụng orTimeout(), callback sẽ nhận TimeoutException và ghi outcome=timeout.

completeOnTimeout(value, timeout, unit) có semantics khác: future hoàn tất bình thường với giá trị fallback. Instrumentation chỉ nhìn thấy một kết quả thành công về mặt CompletionStage. Nếu fallback mang ý nghĩa timeout trong nghiệp vụ, hãy ghi rõ outcome riêng ở lớp nghiệp vụ hoặc dùng một kiểu kết quả thể hiện fallback.

### Cancellation

Với CompletableFuture, cancel(...) hoàn tất future bằng CancellationException:

~~~java
CompletableFuture<Response> source = client.fetchAsync().toCompletableFuture();

boolean cancelled = source.cancel(true);
~~~

Khi future nguồn bị hủy, callback whenComplete nhận cancellation exception và có thể ghi outcome=cancelled.

Tuy nhiên, cancellation signal không luôn đồng nghĩa với công việc nền đã dừng. CompletableFuture không trực tiếp kiểm soát computation tạo ra kết quả; tham số mayInterruptIfRunning không bảo đảm thread đang chạy bị interrupt. Một HTTP client hoặc thư viện khác có thể có API hủy request riêng.

Vì vậy, cần xác định metric đang đo điều gì:

- Nếu đo thời gian đến khi API future báo cancellation, dừng sample khi future hoàn tất do cancel.
- Nếu đo thời gian đến khi tác vụ thật sự dừng, phải nhận tín hiệu hoàn tất từ executor, client hoặc resource owner sau khi việc hủy đã được thực thi.
- Nếu cancellation chỉ hủy một stage phụ, stage nguồn có thể vẫn chạy. Hãy gắn instrumentation vào đúng stage đại diện cho ranh giới cần đo.

Không kết luận rằng worker đã ngừng chỉ từ outcome=cancelled của một CompletableFuture.

## Tránh đo sai ranh giới và ghi hai lần

### Bắt đầu trước hay sau khi submit?

Nếu cần end-to-end latency từ lúc nhận yêu cầu đến khi kết quả hoàn tất, bắt đầu sample trước khi gọi client hoặc submit tác vụ.

Nếu chỉ cần thời gian xử lý trên worker, bắt đầu sample bên trong Runnable/Callable khi worker thực sự chạy. Hai metric này trả lời hai câu hỏi khác nhau:

~~~java
import java.util.concurrent.RejectedExecutionException;

Timer.Sample submittedAt = Timer.start(registry);

try {
    executor.execute(() -> {
        Timer.Sample executionStartedAt = Timer.start(registry);
        try {
            processBatch();
        } finally {
            executionStartedAt.stop(registry.timer("batch.execution"));
            submittedAt.stop(registry.timer("batch.end.to.end"));
        }
    });
} catch (RejectedExecutionException rejected) {
    submittedAt.stop(registry.timer(
            "batch.end.to.end", "outcome", "rejected"));
    throw rejected;
}
~~~

Ví dụ trên chỉ minh họa ranh giới. Trong hệ thống thực tế, nếu cần đo queue wait riêng, hãy dừng sample submit tại thời điểm worker bắt đầu và tạo sample khác cho execution. Bảo đảm mọi nhánh success, error và cancellation đều đi qua đúng điểm dừng.

### Không stop sample ở cả finally lẫn callback

Một lỗi phổ biến là dừng Timer.Sample khi phương thức trả về future, rồi lại dừng lần nữa trong callback. Kết quả là một thao tác có thể tăng count hai lần và có hai duration khác nhau.

Với thao tác bất đồng bộ, sample phải được dừng tại một điểm kết thúc duy nhất. Lỗi đồng bộ trước khi tạo stage cần nhánh dừng riêng; stage đã được tạo thì callback của stage chịu trách nhiệm dừng sample.

### Chọn whenComplete hay whenCompleteAsync

whenComplete thường chạy callback trên thread hoàn tất stage. Nếu callback chỉ ghi Timer, đây là lựa chọn đơn giản để ghi gần thời điểm hoàn tất.

whenCompleteAsync đưa callback sang executor. Khi đó, sample chỉ được dừng sau khi callback được lên lịch và thực thi. Duration có thể bao gồm thêm thời gian chờ callback trong executor. Nếu muốn đo thời gian dispatch callback, đó có thể là một metric riêng; nếu chỉ muốn đo thời gian hoàn tất thao tác nguồn, hãy tránh vô tình cộng queue delay của callback.

### Không giữ Observation.Scope xuyên thread

Observation có thể tạo cả metrics và tracing thông qua ObservationRegistry. Có thể bắt đầu Observation khi thao tác bắt đầu, gọi error(exception) khi stage thất bại và stop khi stage hoàn tất. DefaultMeterObservationHandler tạo Timer khi Observation dừng và LongTaskTimer cho observation đang hoạt động.

Scope của Observation thường gắn với thread hiện tại. Không mở Scope trên một thread rồi để nó tồn tại đến callback trên thread khác. Nếu cần truyền trace context qua ranh giới bất đồng bộ, dùng cơ chế context propagation phù hợp và mở/đóng scope trên từng thread theo đúng vòng đời.

## Theo dõi tác vụ đang chạy lâu

Timer chỉ ghi một observation khi thao tác hoàn tất. Nếu cần nhìn thấy tác vụ vẫn đang chạy, dùng LongTaskTimer:

~~~java
LongTaskTimer longTaskTimer = LongTaskTimer.builder("async.operation.active")
        .tag("operation", "report.generate")
        .register(registry);

LongTaskTimer.Sample activeSample = longTaskTimer.start();
CompletionStage<Report> stage = reportService.generateAsync();

stage.whenComplete((report, failure) -> activeSample.stop());
~~~

LongTaskTimer theo dõi thời gian và số tác vụ đang hoạt động trước khi chúng hoàn tất. Có thể dùng LongTaskTimer cùng Timer: LongTaskTimer để quan sát tác vụ đang treo hoặc chạy quá lâu, Timer để thống kê latency sau khi kết thúc.

Nếu lời gọi generateAsync() ném exception đồng bộ trước khi trả về stage, phải dừng activeSample trong nhánh catch rồi ném lại exception. Nếu không, LongTaskTimer sẽ tiếp tục coi thao tác là đang hoạt động dù không có stage nào được tạo.

Nếu chỉ dùng Timer, dashboard không có mẫu cho tác vụ chưa hoàn tất. Một tác vụ bị treo vô hạn có thể không làm count tăng, dù nó đang chiếm tài nguyên.

## Dùng @Timed cho phương thức trả về CompletableFuture

Micrometer có TimedAspect để áp dụng @Timed lên phương thức được Spring AOP proxy. TimedAspect hỗ trợ phương thức trả về CompletionStage/CompletableFuture và dừng timing khi stage hoàn tất, kể cả khi hoàn tất ngoại lệ.

Ví dụ cấu hình:

~~~java
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimedConfiguration {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
~~~

Phương thức nghiệp vụ:

~~~java
import io.micrometer.core.annotation.Timed;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

import java.util.concurrent.CompletableFuture;

@Service
public class ReportService {

    @Async
    @Timed(value = "report.generate")
    public CompletableFuture<Report> generateAsync() {
        return CompletableFuture.supplyAsync(this::generateReport);
    }

    private Report generateReport() {
        // Tạo báo cáo.
        return new Report();
    }
}
~~~

TimedAspect cần Spring AOP và phương thức phải được gọi qua proxy. Self-invocation bên trong cùng bean có thể bỏ qua proxy. Spring Boot không tự nhận @Timed trên mọi phương thức bất kỳ nếu không có integration/aspect phù hợp. Hãy kiểm tra cấu hình AOP của ứng dụng trước khi dựa vào annotation.

@Timed thuận tiện khi chỉ cần duration và count. Nếu cần phân loại riêng success, error, timeout và cancelled bằng tag, instrumentation thủ công với Timer.Sample hoặc Observation có thể diễn đạt chính sách rõ hơn. Tránh đo cùng một thao tác bằng cả TimedAspect và callback Timer thủ công nếu không muốn count bị nhân đôi.

## Kiểm thử hoàn tất chậm mà không dùng sleep

Kiểm thử bất đồng bộ không nên phụ thuộc Thread.sleep() vì dễ chậm, không ổn định và tạo race condition. Có thể giữ CompletableFuture chưa hoàn tất, điều khiển thời gian bằng MockClock, rồi hoàn tất future theo ý muốn.

Ví dụ kiểm thử thành công sau bốn giây:

~~~java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AsyncOperationMetricsTest {
    @Test
    void recordsDurationOnlyAfterAsyncStageCompletes() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        try {
            AsyncOperationMetrics metrics = new AsyncOperationMetrics(registry);
            CompletableFuture<String> source = new CompletableFuture<>();

            CompletionStage<String> observed =
                    metrics.observe("profile.load", () -> source);

            clock.add(Duration.ofSeconds(4));

            assertThat(registry.find("async.operation.duration")
                    .tag("operation", "profile.load")
                    .timer()).isNull();

            source.complete("ready");

            Timer timer = registry.get("async.operation.duration")
                    .tag("operation", "profile.load")
                    .tag("outcome", "success")
                    .timer();

            assertThat(timer.count()).isEqualTo(1);
            assertThat(timer.totalTime(TimeUnit.SECONDS)).isEqualTo(4.0);
            assertThat(observed).isSameAs(source);
        } finally {
            registry.close();
        }
    }
}
~~~

Test này chứng minh Timer chưa được tạo trước khi stage hoàn tất. Sau khi clock tiến bốn giây và future hoàn tất, Timer có đúng một observation với duration bốn giây. Không cần chờ thời gian thật.

## Kiểm thử lỗi, timeout và cancellation

Các snippet dưới đây là những phương thức test bổ sung trong cùng class AsyncOperationMetricsTest ở ví dụ trước. Chúng dùng lại các import chung đã khai báo ở đầu phần kiểm thử.

### Stage hoàn tất ngoại lệ

~~~java
@Test
void recordsAsyncFailure() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        AsyncOperationMetrics metrics = new AsyncOperationMetrics(registry);
        CompletableFuture<String> source = new CompletableFuture<>();

        metrics.observe("profile.load", () -> source);
        source.completeExceptionally(
                new CompletionException(new IllegalStateException("failed"))
        );

        Timer timer = registry.get("async.operation.duration")
                .tag("operation", "profile.load")
                .tag("outcome", "error")
                .timer();

        assertThat(timer.count()).isEqualTo(1);
    } finally {
        registry.close();
    }
}
~~~

CompletionException được bóc để phân loại nguyên nhân bên trong là lỗi thông thường. Test chỉ xác minh outcome và count; không đưa message exception vào tag.

### Stage bị hủy

~~~java
@Test
void recordsCancellationSeparatelyFromFailure() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        AsyncOperationMetrics metrics = new AsyncOperationMetrics(registry);
        CompletableFuture<String> source = new CompletableFuture<>();

        metrics.observe("profile.load", () -> source);
        assertThat(source.cancel(true)).isTrue();

        Timer timer = registry.get("async.operation.duration")
                .tag("operation", "profile.load")
                .tag("outcome", "cancelled")
                .timer();

        assertThat(timer.count()).isEqualTo(1);
    } finally {
        registry.close();
    }
}
~~~

Test này kiểm tra cancellation của chính stage nguồn. Nó không chứng minh một thread hoặc request bên ngoài đã dừng thực thi; điều đó cần test ở API thực hiện cancellation.

### Stage hết thời gian chờ

Có thể kiểm thử phân loại timeout mà không cần đợi timer thật:

~~~java
@Test
void recordsTimeoutSeparatelyFromCancellation() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        AsyncOperationMetrics metrics = new AsyncOperationMetrics(registry);
        CompletableFuture<String> source = new CompletableFuture<>();

        metrics.observe("profile.load", () -> source);
        source.completeExceptionally(new TimeoutException("deadline exceeded"));

        Timer timer = registry.get("async.operation.duration")
                .tag("operation", "profile.load")
                .tag("outcome", "timeout")
                .timer();

        assertThat(timer.count()).isEqualTo(1);
    } finally {
        registry.close();
    }
}
~~~

Test này mô phỏng kết quả của orTimeout(). Một integration test riêng có thể xác minh cấu hình timeout thật của client hoặc CompletableFuture.

### Lỗi đồng bộ trước khi có stage

Nếu invocation ném exception trước khi trả về future, instrumentation cũng phải dừng sample:

~~~java
@Test
void recordsSynchronousFailureBeforeStageCreation() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();
    try {
        AsyncOperationMetrics metrics = new AsyncOperationMetrics(registry);

        assertThatThrownBy(() -> metrics.observe(
                "profile.load",
                () -> {
                    throw new IllegalArgumentException("invalid request");
                }
        )).isInstanceOf(IllegalArgumentException.class);

        Timer timer = registry.get("async.operation.duration")
                .tag("operation", "profile.load")
                .tag("outcome", "error")
                .timer();

        assertThat(timer.count()).isEqualTo(1);
    } finally {
        registry.close();
    }
}
~~~

## Đọc metrics và chẩn đoán

Giả sử timer async.operation.duration có tag operation và outcome. Các truy vấn Prometheus minh họa:

### Tốc độ hoàn tất theo outcome

~~~promql
sum by (operation, outcome) (
  rate(async_operation_duration_seconds_count[5m])
)
~~~

### Latency trung bình của thao tác thành công

~~~promql
sum by (operation) (
  rate(async_operation_duration_seconds_sum{outcome="success"}[5m])
)
/
sum by (operation) (
  rate(async_operation_duration_seconds_count{outcome="success"}[5m])
)
~~~

### Tỷ lệ timeout

~~~promql
sum by (operation) (
  rate(async_operation_duration_seconds_count{outcome="timeout"}[5m])
)
/
sum by (operation) (
  rate(async_operation_duration_seconds_count[5m])
)
~~~

Tên metric thực tế phụ thuộc naming convention và base unit của registry. Nếu cần percentile latency, bật histogram phù hợp và dùng histogram_quantile() trên bucket. Không lấy trung bình p95 của từng instance để suy ra p95 toàn service.

Khi điều tra một thao tác chậm, kết hợp:

- Timer duration để biết thời gian từ khi bắt đầu đến khi stage hoàn tất.
- LongTaskTimer để thấy số tác vụ vẫn đang hoạt động và thời gian hiện tại của chúng.
- Timer count theo outcome để biết tỷ lệ error, timeout và cancelled.
- Executor queue metrics để biết tác vụ đang chờ worker.
- Trace/log để tìm nguyên nhân của một request cụ thể.

## Những lỗi thường gặp

**Dừng Timer khi phương thức trả về future.** Đây chỉ là submission latency. Dừng sample trong callback hoàn tất stage.

**Bắt đầu sample sau khi đã tạo future.** Thời gian khởi tạo hoặc submit bị loại khỏi phép đo. Nếu cần end-to-end latency, bắt đầu trước invocation.

**Chỉ đo success.** Stage lỗi hoặc bị hủy không được ghi sẽ làm latency và throughput bị thiên lệch. Ghi một outcome cho mọi cách hoàn tất.

**Gộp timeout với cancellation.** Timeout là hết deadline; cancellation là tín hiệu hủy. Hai trạng thái cần tag riêng nếu dashboard cần phân biệt.

**Cho rằng cancel đồng nghĩa tác vụ đã dừng.** CompletableFuture cancellation chỉ thay đổi trạng thái future; nguồn thực thi có thể tiếp tục nếu không có cơ chế hủy tương ứng.

**Stop sample nhiều lần.** Không dừng ở finally của phương thức submit rồi lại dừng ở callback. Mỗi thao tác chỉ có một đường kết thúc.

**Dùng whenCompleteAsync mà không tính queue delay.** Callback chạy muộn làm duration bị cộng thêm thời gian chờ executor. Chọn callback đồng bộ nhẹ nếu muốn dừng sát thời điểm stage hoàn tất.

**Dùng Thread.sleep() trong unit test.** Test phụ thuộc lịch CPU và thời gian thật. Dùng future điều khiển được và MockClock.

**Chỉ dùng Timer cho tác vụ chạy rất lâu.** Timer chỉ có mẫu sau khi hoàn tất. Dùng thêm LongTaskTimer để quan sát tác vụ đang hoạt động.

**Bật nhiều lớp instrumentation cho cùng một thao tác.** TimedAspect, Observation và Timer thủ công có thể cùng ghi duration. Chọn một ranh giới sở hữu metric hoặc đặt tên riêng cho các khoảng đo khác nhau.

**Đưa exception message hoặc ID vào tag.** Dùng nhóm outcome cố định; chi tiết điều tra để trong log hoặc trace.

## Checklist kiểm thử instrumentation bất đồng bộ

1. Xác định rõ metric đo submission, queue wait, execution hay end-to-end latency.
2. Bắt đầu Timer.Sample trước đúng ranh giới cần đo.
3. Dừng sample khi stage nguồn hoàn tất, không phải khi phương thức trả future.
4. Xử lý lỗi đồng bộ khi chưa tạo được stage.
5. Phân loại success, error, timeout và cancelled.
6. Bóc CompletionException/ExecutionException trước khi phân loại.
7. Xác minh cancellation signal có thực sự dừng công việc nền hay không.
8. Bảo đảm một thao tác chỉ ghi một duration.
9. Giữ callback nhẹ và tránh vô tình đo queue delay của callback executor.
10. Dùng LongTaskTimer nếu cần quan sát tác vụ chưa hoàn tất.
11. Kiểm thử bằng CompletableFuture điều khiển được và MockClock, không dùng sleep.
12. Giữ operation/outcome tags có cardinality hữu hạn.
13. Kiểm tra histogram, count, total time và truy vấn trên backend.

## Kết luận

Đo bất đồng bộ phải theo dõi đến khi công việc thật sự phát tín hiệu hoàn tất. Timer.Sample giúp giữ thời điểm bắt đầu qua ranh giới thread và dừng trong callback của CompletionStage. Hãy ghi nhận cả thành công, lỗi, timeout và cancellation; hiểu rằng cancellation của CompletableFuture không bảo đảm computation nền đã dừng; và chỉ dừng sample một lần. MockClock cùng future điều khiển được giúp kiểm thử thời gian chậm, lỗi và hủy một cách ổn định mà không cần chờ thời gian thật.

## Tài liệu tham khảo

- [Micrometer - Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer.Sample, ghi nhận duration và hỗ trợ @Timed cho phương thức trả về CompletableFuture.
- [Micrometer - Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html): Observation lifecycle, DefaultMeterObservationHandler, Timer và LongTaskTimer.
- [Micrometer - MockClock API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/MockClock.html): clock có thể điều khiển để kiểm thử duration.
- [Java - CompletionStage](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletionStage.html): semantics của whenComplete và completion bình thường/ngoại lệ.
- [Java - CompletableFuture](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cancel, orTimeout, completeOnTimeout và semantics cancellation.
