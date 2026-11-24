# Đo thao tác bất đồng bộ với đường lỗi, hủy và retry được kiểm chứng

Trong bài thực hành này, bạn sẽ instrument một job bất đồng bộ được triển khai bằng CompletableFuture. Job có thể hoàn tất thành công, thất bại do lỗi tạm thời, thất bại vĩnh viễn hoặc bị caller hủy. Với lỗi tạm thời, runner được phép retry một số lần có giới hạn.

Mục tiêu là đo đúng thời lượng của một attempt và toàn bộ job, đồng thời chứng minh bằng test rằng lỗi, cancellation và retry được xử lý đúng. Bài dùng Timer.Sample và MeterRegistry để đo thời gian, Counter để đếm attempt/retry/kết quả, MockClock để điều khiển thời gian và một retry scheduler giả lập để test không phụ thuộc vào sleep.

## Kết quả cần đạt

Sau khi hoàn thành, bạn có thể:

- Đo một CompletableFuture từ lúc bắt đầu công việc đến khi future hoàn tất.
- Phân biệt thời lượng một attempt với thời lượng toàn job.
- Ghi nhận success, failure và cancelled bằng tập tag outcome hữu hạn.
- Chỉ retry lỗi được phân loại là tạm thời và giới hạn số lần retry.
- Không retry khi operation bị hủy.
- Chuyển cancellation từ future kết quả đến future của attempt đang chạy.
- Kiểm tra count, totalTime, retry count và exception bằng test xác định.
- Giải thích giới hạn của CompletableFuture.cancel(true) đối với công việc đang chạy.

## Bối cảnh bài toán

Một dịch vụ tạo báo cáo gọi một dependency bất đồng bộ. Dependency có thể trả kết quả sau một khoảng thời gian, ném lỗi hoặc bị hủy. Một số lỗi mạng có thể thử lại; lỗi dữ liệu không hợp lệ không nên retry.

Runner nhận một operation trả về CompletableFuture và điều phối tối đa N lần retry sau attempt đầu tiên. Ví dụ maxRetries bằng 2 có nghĩa tối đa 3 attempt:

~~~text
Attempt 1
  ├─ success  → hoàn tất job
  ├─ failure không retry được → hoàn tất lỗi
  ├─ cancelled → hủy job, không retry
  └─ lỗi tạm thời → chờ retry
                    Attempt 2
                      ├─ success → hoàn tất job
                      ├─ failure cuối cùng → hoàn tất lỗi
                      └─ lỗi tạm thời → có thể chạy Attempt 3
~~~

Job có hai cấp thời gian:

| Timer | Bắt đầu | Kết thúc | Ý nghĩa |
|---|---|---|---|
| job.attempt.duration | Khi một attempt bắt đầu | Khi attempt success, failure hoặc cancelled | Độ trễ của từng lần gọi dependency |
| job.duration | Khi caller bắt đầu job | Khi job có kết quả cuối cùng hoặc bị hủy | Thời gian end-to-end, bao gồm cả khoảng chờ retry |

Các Counter:

| Meter | Khi tăng | Tag |
|---|---|---|
| job.attempts | Trước mỗi lần gọi operation | Không cần tag |
| job.retries | Khi một retry được lên lịch thành công | Không cần tag |
| job.completed | Khi job có trạng thái cuối cùng | outcome=success, failure hoặc cancelled |

Không thêm attempt number, request ID, exception message hoặc trace ID làm metric tag. Attempt number đã được phản ánh bằng Counter; outcome chỉ có ba giá trị hữu hạn.

## Vì sao không đo bằng Timer.record quanh lời gọi async?

Đoạn code sau không đo thời gian xử lý thực tế:

~~~java
timer.record(() -> client.fetchAsync());
~~~

Lệnh fetchAsync thường trả về CompletableFuture ngay sau khi submit công việc. Timer.record dừng khi phương thức trả future, nên số đo chủ yếu là thời gian khởi tạo hoặc submit, không phải thời gian chờ dependency hoàn tất.

Với công việc bất đồng bộ, tạo Timer.Sample trước khi bắt đầu và dừng sample trong callback hoàn tất:

~~~java
Timer.Sample sample = Timer.start(registry);
CompletableFuture<Result> source = client.fetchAsync();

source.whenComplete((value, error) -> {
    String outcome = error == null ? "success" : "failure";
    sample.stop(registry.timer(
            "job.attempt.duration",
            "outcome", outcome));
});
~~~

Đây mới là điểm kết thúc phù hợp cho thời lượng attempt. Bài thực hành sẽ mở rộng ví dụ để xử lý cả cancellation, lỗi đồng bộ lúc tạo future và retry.

## Thiết kế API điều phối retry

Tạo một abstraction cho lịch retry. Ứng dụng thật dùng ScheduledExecutorService; test dùng scheduler thủ công để quyết định chính xác khi nào retry chạy.

~~~java
import java.time.Duration;

public interface RetryScheduler {
    Cancellable schedule(Runnable task, Duration delay);
}

@FunctionalInterface
public interface Cancellable {
    void cancel();
}
~~~

Đặt RetryScheduler và Cancellable trong hai file Java riêng vì cả hai là public top-level type. Các ví dụ tiếp theo giả định chúng nằm cùng package với runner.

Adapter dùng scheduler thật:

~~~java
import java.time.Duration;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public final class ExecutorRetryScheduler implements RetryScheduler {
    private final ScheduledExecutorService executor;

    public ExecutorRetryScheduler(ScheduledExecutorService executor) {
        this.executor = executor;
    }

    @Override
    public Cancellable schedule(Runnable task, Duration delay) {
        ScheduledFuture<?> scheduled = executor.schedule(
                task, delay.toNanos(), TimeUnit.NANOSECONDS);
        return () -> scheduled.cancel(false);
    }
}
~~~

Runner nhận operation, số retry tối đa, độ trễ retry và predicate phân loại lỗi. maxRetries không bao gồm attempt đầu tiên.

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CancellationException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.IntFunction;
import java.util.function.Predicate;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public final class AsyncJobRunner<T> {
    private final MeterRegistry registry;
    private final RetryScheduler retryScheduler;
    private final int maxRetries;
    private final Duration retryDelay;
    private final Predicate<Throwable> retryable;
    private final Counter attempts;
    private final Counter retries;

    private static final class RetryTicket implements Cancellable {
        private final AtomicReference<Cancellable> delegate = new AtomicReference<>();
        private final AtomicBoolean started = new AtomicBoolean();
        private final AtomicBoolean cancelled = new AtomicBoolean();

        void setDelegate(Cancellable scheduled) {
            delegate.set(scheduled);
            if (cancelled.get() && !started.get()) {
                scheduled.cancel();
            }
        }

        boolean tryStart() {
            if (cancelled.get()) {
                return false;
            }
            started.set(true);
            return !cancelled.get();
        }

        @Override
        public void cancel() {
            if (!started.get()) {
                cancelled.set(true);
                Cancellable scheduled = delegate.get();
                if (scheduled != null) {
                    scheduled.cancel();
                }
            }
        }
    }

    public AsyncJobRunner(
            MeterRegistry registry,
            RetryScheduler retryScheduler,
            int maxRetries,
            Duration retryDelay,
            Predicate<Throwable> retryable) {
        if (maxRetries < 0) {
            throw new IllegalArgumentException("maxRetries must be >= 0");
        }
        if (retryDelay.isNegative() || retryDelay.isZero()) {
            throw new IllegalArgumentException("retryDelay must be positive");
        }
        this.registry = Objects.requireNonNull(registry);
        this.retryScheduler = Objects.requireNonNull(retryScheduler);
        this.maxRetries = maxRetries;
        this.retryDelay = retryDelay;
        this.retryable = Objects.requireNonNull(retryable);
        this.attempts = registry.counter("job.attempts");
        this.retries = registry.counter("job.retries");
    }

    public CompletableFuture<T> execute(
            IntFunction<CompletableFuture<T>> operation) {
        Objects.requireNonNull(operation);
        Timer.Sample totalSample = Timer.start(registry);
        CompletableFuture<T> result = new CompletableFuture<>();
        AtomicReference<CompletableFuture<T>> activeAttempt =
                new AtomicReference<>();
        AtomicReference<Cancellable> pendingRetry = new AtomicReference<>();

        result.whenComplete((value, error) -> {
            if (result.isCancelled()) {
                CompletableFuture<T> active = activeAttempt.getAndSet(null);
                if (active != null) {
                    active.cancel(true);
                }
                Cancellable scheduled = pendingRetry.getAndSet(null);
                if (scheduled != null) {
                    scheduled.cancel();
                }
            }

            String outcome = result.isCancelled()
                    ? "cancelled"
                    : error == null ? "success" : "failure";

            totalSample.stop(registry.timer(
                    "job.duration", "outcome", outcome));
            registry.counter("job.completed", "outcome", outcome).increment();
        });

        runAttempt(operation, 1, result, activeAttempt, pendingRetry);
        return result;
    }

    private void runAttempt(
            IntFunction<CompletableFuture<T>> operation,
            int attemptNumber,
            CompletableFuture<T> result,
            AtomicReference<CompletableFuture<T>> activeAttempt,
            AtomicReference<Cancellable> pendingRetry) {
        if (result.isDone()) {
            return;
        }

        attempts.increment();
        Timer.Sample attemptSample = Timer.start(registry);

        CompletableFuture<T> source;
        try {
            source = Objects.requireNonNull(
                    operation.apply(attemptNumber),
                    "operation returned null");
        } catch (RuntimeException | Error error) {
            if (error instanceof CancellationException) {
                attemptSample.stop(registry.timer(
                        "job.attempt.duration", "outcome", "cancelled"));
                result.cancel(false);
            } else {
                attemptSample.stop(registry.timer(
                        "job.attempt.duration", "outcome", "failure"));
                handleFailure(
                        operation, attemptNumber, error,
                        result, activeAttempt, pendingRetry);
            }
            return;
        }

        CompletableFuture<T> measured = measureAttempt(source, attemptSample);
        activeAttempt.set(measured);
        if (result.isCancelled()) {
            measured.cancel(true);
        }

        measured.whenComplete((value, error) -> {
            activeAttempt.compareAndSet(measured, null);
            if (result.isDone()) {
                return;
            }
            if (error == null) {
                result.complete(value);
                return;
            }

            Throwable cause = unwrap(error);
            if (cause instanceof CancellationException) {
                result.cancel(false);
            } else {
                handleFailure(
                        operation, attemptNumber, cause,
                        result, activeAttempt, pendingRetry);
            }
        });
    }

    private CompletableFuture<T> measureAttempt(
            CompletableFuture<T> source,
            Timer.Sample sample) {
        CompletableFuture<T> measured = new CompletableFuture<>() {
            @Override
            public boolean cancel(boolean mayInterruptIfRunning) {
                boolean cancelled = super.cancel(mayInterruptIfRunning);
                if (cancelled) {
                    source.cancel(mayInterruptIfRunning);
                }
                return cancelled;
            }
        };

        measured.whenComplete((value, error) -> {
            String outcome = measured.isCancelled()
                    ? "cancelled"
                    : error == null ? "success" : "failure";
            sample.stop(registry.timer(
                    "job.attempt.duration", "outcome", outcome));
        });

        source.whenComplete((value, error) -> {
            if (error == null) {
                measured.complete(value);
            } else {
                measured.completeExceptionally(unwrap(error));
            }
        });
        return measured;
    }

    private void handleFailure(
            IntFunction<CompletableFuture<T>> operation,
            int attemptNumber,
            Throwable error,
            CompletableFuture<T> result,
            AtomicReference<CompletableFuture<T>> activeAttempt,
            AtomicReference<Cancellable> pendingRetry) {
        if (result.isDone()) {
            return;
        }

        boolean canRetry = attemptNumber <= maxRetries && retryable.test(error);
        if (!canRetry) {
            result.completeExceptionally(error);
            return;
        }

        RetryTicket ticket = new RetryTicket();
        pendingRetry.set(ticket);
        if (result.isDone()) {
            pendingRetry.compareAndSet(ticket, null);
            ticket.cancel();
            return;
        }
        try {
            Cancellable scheduled = retryScheduler.schedule(() -> {
                if (!pendingRetry.compareAndSet(ticket, null)) {
                    return;
                }
                if (!ticket.tryStart()) {
                    return;
                }
                runAttempt(
                        operation, attemptNumber + 1, result,
                        activeAttempt, pendingRetry);
            }, retryDelay);
            ticket.setDelegate(Objects.requireNonNull(scheduled));
            retries.increment();

            if (result.isCancelled()
                    && pendingRetry.compareAndSet(ticket, null)) {
                ticket.cancel();
            }
        } catch (RuntimeException schedulingError) {
            pendingRetry.compareAndSet(ticket, null);
            ticket.cancel();
            result.completeExceptionally(schedulingError);
        }
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

Điểm cần chú ý trong runner:

- Timer.Sample tổng được tạo một lần khi caller gọi execute; nó dừng khi result có trạng thái cuối.
- Mỗi attempt có Timer.Sample riêng; sample dừng khi future của attempt hoàn tất.
- Lỗi đồng bộ khi operation.apply ném exception cũng được ghi vào attempt timer.
- Retry chỉ chạy khi attempt thất bại, số retry chưa vượt maxRetries và predicate trả true.
- Cancellation không đi qua nhánh retry.
- Future trả về theo dõi active attempt và hủy future đó khi caller hủy result.
- Retry đang chờ cũng được hủy khi result bị hủy.
- Tag outcome chỉ có success, failure và cancelled.

Trong ứng dụng thật, operation.apply nên khởi chạy công việc và trả future nhanh chóng. Không thực hiện I/O blocking bên trong lời gọi này trên thread xử lý request.

## Giới hạn quan trọng của cancellation

CompletableFuture.cancel(true) đánh dấu future là cancelled và chuyển yêu cầu hủy đến source future trong ví dụ. Tuy nhiên, CompletableFuture không bảo đảm interrupt công việc đang chạy trong mọi trường hợp. Chẳng hạn, future được tạo từ supplyAsync không nhất thiết dừng được computation chỉ vì caller gọi cancel(true).

Muốn dừng công việc thực sự, adapter của dependency phải hỗ trợ cancellation: hủy HTTP request, đóng stream, cancel database query hoặc kiểm tra cancellation token trong vòng lặp. Runner có thể bảo đảm trạng thái logical job là cancelled, không retry và ghi metric cancelled; khả năng dừng tài nguyên bên dưới phụ thuộc API của dependency.

Không retry CancellationException. Nếu một client dùng exception riêng để biểu diễn cancellation, hãy ánh xạ nó thành cancellation trước khi đưa vào retry classifier.

## Scheduler thủ công cho test xác định

Test không nên chờ một khoảng thời gian thật để retry chạy. Scheduler giả lập lưu task vào queue và chỉ chạy khi test gọi runNext:

~~~java
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.Deque;

public final class ManualRetryScheduler implements RetryScheduler {
    private final Deque<Runnable> tasks = new ArrayDeque<>();

    @Override
    public Cancellable schedule(Runnable task, Duration delay) {
        tasks.addLast(task);
        return () -> tasks.remove(task);
    }

    public int pendingTasks() {
        return tasks.size();
    }

    public void runNext() {
        tasks.removeFirst().run();
    }
}
~~~

Scheduler này bỏ qua thời gian delay nhưng giữ nguyên quyết định có schedule retry hay không. Test tự advance MockClock để mô phỏng thời gian attempt và thời gian chờ. Khi chạy ứng dụng thật, thay scheduler này bằng ExecutorRetryScheduler.

## Chuẩn bị registry và helper trong test

SimpleMeterRegistry lưu meter trong bộ nhớ; MockClock giúp test đặt elapsed time chính xác:

~~~java
import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

MockClock clock = new MockClock();
SimpleMeterRegistry registry =
        new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
ManualRetryScheduler scheduler = new ManualRetryScheduler();
~~~

Tạo runner chỉ retry lỗi transient:

~~~java
AsyncJobRunner<String> runner = new AsyncJobRunner<>(
        registry,
        scheduler,
        1,
        Duration.ofSeconds(1),
        error -> error instanceof TransientGatewayException);
~~~

Với maxRetries bằng 1, tổng số attempt tối đa là 2. Định nghĩa exception dùng trong test:

~~~java
public class TransientGatewayException extends RuntimeException {
    public TransientGatewayException(String message) {
        super(message);
    }
}

public class PermanentJobException extends RuntimeException {
    public PermanentJobException(String message) {
        super(message);
    }
}
~~~

Đặt mỗi exception class trong file riêng nếu khai báo là public. Các lớp test bên dưới cũng là các file test riêng và dùng chung package với những helper trong bài.

Trong mỗi test, tạo registry mới và đóng registry sau khi assertion hoàn tất. Không dùng registry static chung cho nhiều test vì meter count và totalTime sẽ tích lũy giữa các lần chạy.

## Test 1: attempt thành công

Future được test giữ lại để điều khiển thời điểm hoàn tất:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class AsyncJobRunnerSuccessTest {
    @Test
    void recordsAttemptAndWholeJobDuration() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        ManualRetryScheduler scheduler = new ManualRetryScheduler();
        AsyncJobRunner<String> runner = new AsyncJobRunner<>(
                registry, scheduler, 1, Duration.ofSeconds(1),
                error -> error instanceof TransientGatewayException);

        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> result = runner.execute(attempt -> source);

        clock.add(Duration.ofMillis(120));
        source.complete("report-ready");

        assertThat(result.join()).isEqualTo("report-ready");
        assertThat(registry.get("job.attempts").counter().count()).isEqualTo(1.0);
        assertThat(registry.get("job.retries").counter().count()).isEqualTo(0.0);

        Timer attemptTimer = registry.get("job.attempt.duration")
                .tag("outcome", "success").timer();
        Timer jobTimer = registry.get("job.duration")
                .tag("outcome", "success").timer();

        assertThat(attemptTimer.count()).isEqualTo(1);
        assertThat(attemptTimer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(120.0);
        assertThat(jobTimer.count()).isEqualTo(1);
        assertThat(jobTimer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(120.0);
        assertThat(registry.get("job.completed")
                .tag("outcome", "success").counter().count()).isEqualTo(1.0);

        registry.close();
    }
}
~~~

Test chứng minh Timer không dừng khi execute trả future. Nó chỉ ghi nhận sau khi source hoàn tất. Cả attempt timer và job timer bằng 120 ms vì job chỉ có một attempt và không có thời gian chờ retry.

## Test 2: lỗi tạm thời rồi retry thành công

Attempt đầu thất bại sau 40 ms. Test advance thêm 20 ms để mô phỏng thời gian chờ, chạy retry thủ công, rồi hoàn tất attempt thứ hai sau 70 ms:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class AsyncJobRunnerRetryTest {
    @Test
    void retriesTransientFailureAndMeasuresBothAttempts() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        ManualRetryScheduler scheduler = new ManualRetryScheduler();
        AsyncJobRunner<String> runner = new AsyncJobRunner<>(
                registry, scheduler, 1, Duration.ofSeconds(1),
                error -> error instanceof TransientGatewayException);

        CompletableFuture<String> first = new CompletableFuture<>();
        CompletableFuture<String> second = new CompletableFuture<>();
        AtomicInteger calls = new AtomicInteger();

        CompletableFuture<String> result = runner.execute(attempt ->
                calls.getAndIncrement() == 0 ? first : second);

        clock.add(Duration.ofMillis(40));
        first.completeExceptionally(
                new TransientGatewayException("temporary gateway error"));

        assertThat(result.isDone()).isFalse();
        assertThat(scheduler.pendingTasks()).isEqualTo(1);
        assertThat(registry.get("job.retries").counter().count()).isEqualTo(1.0);

        clock.add(Duration.ofMillis(20));
        scheduler.runNext();
        assertThat(calls.get()).isEqualTo(2);

        clock.add(Duration.ofMillis(70));
        second.complete("done-after-retry");

        assertThat(result.join()).isEqualTo("done-after-retry");
        assertThat(registry.get("job.attempts").counter().count()).isEqualTo(2.0);

        Timer failedAttempt = registry.get("job.attempt.duration")
                .tag("outcome", "failure").timer();
        Timer successfulAttempt = registry.get("job.attempt.duration")
                .tag("outcome", "success").timer();
        Timer totalJob = registry.get("job.duration")
                .tag("outcome", "success").timer();

        assertThat(failedAttempt.count()).isEqualTo(1);
        assertThat(failedAttempt.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(40.0);
        assertThat(successfulAttempt.count()).isEqualTo(1);
        assertThat(successfulAttempt.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(70.0);
        assertThat(totalJob.count()).isEqualTo(1);
        assertThat(totalJob.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(130.0);

        registry.close();
    }
}
~~~

Tổng thời lượng job là 130 ms: 40 ms attempt đầu, 20 ms chờ retry và 70 ms attempt thứ hai. Tổng thời lượng các attempt chỉ là 110 ms. Hai số đo trả lời hai câu hỏi vận hành khác nhau.

## Test 3: lỗi vĩnh viễn không được retry

Lỗi validation hoặc dữ liệu không hợp lệ không nên tiêu tốn thêm request:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class AsyncJobRunnerPermanentFailureTest {
    @Test
    void doesNotRetryPermanentFailure() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        ManualRetryScheduler scheduler = new ManualRetryScheduler();
        AsyncJobRunner<String> runner = new AsyncJobRunner<>(
                registry, scheduler, 3, Duration.ofSeconds(1),
                error -> error instanceof TransientGatewayException);

        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> result = runner.execute(attempt -> source);

        clock.add(Duration.ofMillis(15));
        source.completeExceptionally(new PermanentJobException("invalid input"));

        assertThatThrownBy(result::join)
                .isInstanceOf(CompletionException.class)
                .hasCauseInstanceOf(PermanentJobException.class);
        assertThat(registry.get("job.attempts").counter().count()).isEqualTo(1.0);
        assertThat(registry.get("job.retries").counter().count()).isEqualTo(0.0);
        assertThat(scheduler.pendingTasks()).isZero();
        assertThat(registry.get("job.attempt.duration")
                .tag("outcome", "failure").timer().count()).isEqualTo(1);
        assertThat(registry.get("job.duration")
                .tag("outcome", "failure").timer().count()).isEqualTo(1);

        registry.close();
    }
}
~~~

Test xác nhận retry classifier quyết định lỗi nào có thể thử lại. Không dùng exception class hoặc message tùy ý làm metric tag; classifier chỉ dùng chúng trong logic ứng dụng.

## Test 4: caller hủy khi attempt đang chạy

Khi caller hủy job, runner phải hủy future đang hoạt động, ghi outcome cancelled và không schedule retry:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class AsyncJobRunnerCancellationTest {
    @Test
    void cancellationPropagatesAndIsNotRetried() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        ManualRetryScheduler scheduler = new ManualRetryScheduler();
        AsyncJobRunner<String> runner = new AsyncJobRunner<>(
                registry, scheduler, 3, Duration.ofSeconds(1),
                error -> error instanceof TransientGatewayException);

        CompletableFuture<String> source = new CompletableFuture<>();
        CompletableFuture<String> result = runner.execute(attempt -> source);

        clock.add(Duration.ofMillis(25));
        assertThat(result.cancel(true)).isTrue();

        assertThat(result.isCancelled()).isTrue();
        assertThat(source.isCancelled()).isTrue();
        assertThat(registry.get("job.attempts").counter().count()).isEqualTo(1.0);
        assertThat(registry.get("job.retries").counter().count()).isEqualTo(0.0);
        assertThat(scheduler.pendingTasks()).isZero();

        Timer attemptTimer = registry.get("job.attempt.duration")
                .tag("outcome", "cancelled").timer();
        Timer jobTimer = registry.get("job.duration")
                .tag("outcome", "cancelled").timer();
        assertThat(attemptTimer.count()).isEqualTo(1);
        assertThat(attemptTimer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(25.0);
        assertThat(jobTimer.count()).isEqualTo(1);
        assertThat(jobTimer.totalTime(TimeUnit.MILLISECONDS)).isEqualTo(25.0);
        assertThat(registry.get("job.completed")
                .tag("outcome", "cancelled").counter().count()).isEqualTo(1.0);

        registry.close();
    }
}
~~~

Test này xác nhận cancellation được chuyển từ future kết quả đến source future trong ví dụ. Với HTTP client hoặc database client thật, cần test thêm adapter của client để xác nhận request hoặc query bên dưới được hủy.

## Test 5: hủy trong lúc đang chờ retry

Cancellation cũng phải loại bỏ retry đã được schedule nhưng chưa chạy:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class AsyncJobRunnerCancelPendingRetryTest {
    @Test
    void cancelsScheduledRetryWhenCallerCancelsJob() {
        MockClock clock = new MockClock();
        SimpleMeterRegistry registry =
                new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);
        ManualRetryScheduler scheduler = new ManualRetryScheduler();
        AsyncJobRunner<String> runner = new AsyncJobRunner<>(
                registry, scheduler, 2, Duration.ofSeconds(1),
                error -> error instanceof TransientGatewayException);

        CompletableFuture<String> first = new CompletableFuture<>();
        AtomicInteger calls = new AtomicInteger();
        CompletableFuture<String> result = runner.execute(attempt -> {
            calls.incrementAndGet();
            return first;
        });

        clock.add(Duration.ofMillis(10));
        first.completeExceptionally(new TransientGatewayException("try later"));

        assertThat(scheduler.pendingTasks()).isEqualTo(1);
        assertThat(result.cancel(false)).isTrue();
        assertThat(scheduler.pendingTasks()).isZero();

        // Không gọi scheduler.runNext(): attempt tiếp theo không được chạy.
        assertThat(calls.get()).isEqualTo(1);
        assertThat(registry.get("job.attempts").counter().count()).isEqualTo(1.0);
        assertThat(registry.get("job.retries").counter().count()).isEqualTo(1.0);
        assertThat(registry.get("job.completed")
                .tag("outcome", "cancelled").counter().count()).isEqualTo(1.0);

        registry.close();
    }
}
~~~

Test này dùng registry và runner mới. Nó chứng minh runner hủy task retry đang chờ và không tạo attempt mới sau khi job đã bị hủy.

## Kiểm tra đồng hồ và meter identity

MockClock phải được truyền vào chính SimpleMeterRegistry dùng để tạo Timer.Sample. Nếu sample dùng system clock trong khi test chỉ advance một MockClock khác, duration không thể bằng giá trị mong đợi.

Mỗi test nên kiểm tra ít nhất:

| Assertion | Điều được bảo vệ |
|---|---|
| job.attempts.count | Mỗi lần gọi operation được đếm một lần |
| job.retries.count | Chỉ retry được schedule mới được đếm |
| attempt timer count | Mỗi attempt kết thúc tạo đúng một observation |
| attempt timer totalTime | Đo đúng khoảng thời gian của attempt |
| job timer totalTime | Bao gồm cả thời gian chờ retry |
| job.completed outcome | Chỉ ghi một trạng thái cuối cùng cho job |
| result.isCancelled hoặc exception cause | Hành vi trả về vẫn đúng với caller |

Timer được chọn theo name và tag. Khi test tìm meter, dùng đúng tag outcome. Một meter tồn tại nhưng count bằng 0 không chứng minh phép đo đã hoàn tất.

## Những tình huống bổ sung cần tự thử

Sau khi các test chính chạy đúng, mở rộng bài thực hành với các tình huống:

1. Attempt đầu ném RuntimeException đồng bộ trước khi trả CompletableFuture. Attempt timer vẫn phải được ghi là failure.
2. Operation trả về null. Runner phải hoàn tất job bằng lỗi cấu hình và không để future treo.
3. Hai lỗi transient liên tiếp với maxRetries bằng 1. Chỉ có hai attempt; lỗi thứ hai là lỗi cuối cùng.
4. Dependency tự hủy source future. Job kết quả cũng phải thành cancelled và không retry.
5. Retry scheduler từ chối task. Job phải kết thúc bằng lỗi schedule thay vì treo vô hạn.
6. Caller hủy sau khi job đã hoàn tất. cancel phải trả false và không tạo thêm meter observation.
7. Hai job chạy đồng thời. Timer.Sample và state retry phải độc lập giữa hai job.

Các trường hợp này giúp phát hiện race condition quanh active future, retry task và trạng thái hoàn tất cuối cùng. Không lưu Timer.Sample hoặc future đang chạy trong field dùng chung của singleton service.

## Mở rộng: thêm Observation hoặc tracing

Bài thực hành dùng Timer.Sample để đo duration bất đồng bộ. Nếu cần tạo span cho job, có thể thêm Observation quanh logical job, nhưng không giữ Observation.Scope mở xuyên qua thời gian chờ hoặc chuyển thread. Scope gắn với execution context của thread hiện tại; mở ở một thread và đóng ở thread khác có thể làm sai việc khôi phục context.

Một hướng triển khai là giữ Observation trong state của logical job, mở và đóng scope ngắn trong từng callback cần đặt Observation hiện tại, đồng thời dùng Micrometer Context Propagation khi context phải đi qua executor hoặc reactive scheduler. Gọi observation.error(exception) cho lỗi cuối cùng và observation.stop() đúng một lần khi job kết thúc. Retry attempt có thể có Observation riêng nếu cần phân tích từng lần gọi dependency.

Không tạo span cho mọi retry chỉ vì có Counter retry. Chọn ranh giới theo câu hỏi điều tra: một span cho toàn job giúp nhìn end-to-end; span con cho từng attempt giúp thấy dependency call và thời gian chờ retry.

## Tiêu chí hoàn thành

- [ ] Timer tổng chỉ dừng khi job có kết quả cuối cùng hoặc bị hủy.
- [ ] Timer attempt dừng khi từng future attempt hoàn tất.
- [ ] Lỗi đồng bộ khi khởi chạy operation vẫn được đo.
- [ ] Lỗi transient được retry đúng giới hạn.
- [ ] Lỗi permanent không được retry.
- [ ] Cancellation không kích hoạt retry.
- [ ] Hủy job đang chạy chuyển cancellation đến future attempt.
- [ ] Hủy job đang chờ retry loại bỏ task retry.
- [ ] Exception cuối cùng vẫn được truyền về caller.
- [ ] Tag outcome chỉ có success, failure và cancelled.
- [ ] Test dùng MockClock và scheduler giả lập, không dùng Thread.sleep().
- [ ] Test chứng minh job duration bao gồm thời gian chờ retry.
- [ ] State của từng job độc lập khi có nhiều operation đồng thời.

## Kết quả mong đợi

Với kịch bản một attempt lỗi sau 40 ms, chờ retry 20 ms rồi thành công sau 70 ms, các số đo phải là:

| Meter | Tag | Count | Total |
|---|---|---:|---:|
| job.attempt.duration | outcome=failure | 1 | 40 ms |
| job.attempt.duration | outcome=success | 1 | 70 ms |
| job.duration | outcome=success | 1 | 130 ms |
| job.attempts | Không có | 1 series | 2 |
| job.retries | Không có | 1 series | 1 |
| job.completed | outcome=success | 1 | 1 |

Kết quả này thể hiện sự khác nhau giữa thời lượng dependency attempt và thời lượng người gọi phải chờ toàn bộ job. Với cancellation, outcome phải là cancelled và retry không tăng. Với lỗi permanent, outcome cuối là failure và không có retry được schedule.

## Tài liệu tham khảo

- [Micrometer Timers and Timer.Sample](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Observation](https://docs.micrometer.io/micrometer/reference/observation.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Java CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)

Bài thực hành hoàn tất khi metrics phản ánh đúng cả từng attempt và toàn bộ job, đồng thời các test chứng minh success, failure, cancellation và retry. Dùng Timer.Sample để dừng phép đo tại callback hoàn tất, giữ outcome có cardinality thấp, giới hạn retry theo loại lỗi và kiểm tra cancellation ở cả attempt đang chạy lẫn retry đang chờ. Khi tích hợp dependency thật, xác minh thêm khả năng hủy I/O bên dưới vì trạng thái cancelled của CompletableFuture không tự bảo đảm computation đã dừng.
