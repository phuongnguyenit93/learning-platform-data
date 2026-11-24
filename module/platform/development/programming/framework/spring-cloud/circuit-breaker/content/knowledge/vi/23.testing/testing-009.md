# Kiểm thử nhiều luồng, Bulkhead đầy và hàng đợi bị từ chối

## Mục tiêu của kiểm thử Bulkhead

Trong ứng dụng Spring Cloud dùng Circuit Breaker, Bulkhead giới hạn số lời gọi được phép hoạt động đồng thời để một dependency chậm không chiếm hết tài nguyên của ứng dụng. Khi kiểm thử, cần chứng minh được ba hành vi: số lời gọi đang chạy không vượt giới hạn; lời gọi vượt giới hạn được chờ hoặc từ chối theo cấu hình; tài nguyên được giải phóng khi lời gọi hoàn tất hoặc bị hủy.

Kiểm thử chỉ gọi phương thức tuần tự thường không phát hiện được lỗi cấu hình Bulkhead. Muốn kiểm tra giới hạn concurrency, phải tạo nhiều lời gọi cùng lúc và điều khiển thời điểm chúng bắt đầu/kết thúc. Dùng `CountDownLatch`, `CyclicBarrier` hoặc `Phaser` giúp kiểm thử có tính xác định, thay vì dựa vào `Thread.sleep()` và hy vọng các thread chạy đúng thời điểm.

Hai kiểu Bulkhead của Resilience4j có hành vi cần kiểm tra khác nhau:

| Kiểu | Giới hạn | Khi quá tải |
| --- | --- | --- |
| `SemaphoreBulkhead` | Số lời gọi đang giữ permit, qua `maxConcurrentCalls`. | Có thể từ chối ngay hoặc chờ tối đa `maxWaitDuration` để lấy permit. |
| `ThreadPoolBulkhead` | Số worker và hàng đợi, qua `coreThreadPoolSize`, `maxThreadPoolSize` và `queueCapacity`. | Khi worker và hàng đợi đều đầy, tác vụ mới bị từ chối. |

Không nên dùng một bài kiểm thử cho cả hai loại. Semaphore kiểm soát số lời gọi đang hoạt động; ThreadPoolBulkhead còn có hàng đợi và thực thi supplier trên pool riêng. Kết quả cần xác minh phải tương ứng với loại Bulkhead được dùng trong ứng dụng.

## Phân biệt các giới hạn trước khi viết test

Với `SemaphoreBulkhead`, `maxConcurrentCalls = 3` nghĩa là tại một thời điểm tối đa ba lời gọi được giữ permit. Nếu `maxWaitDuration` bằng 0, lời gọi thứ tư khi cả ba permit đang được sử dụng bị từ chối ngay. Nếu cấu hình thời gian chờ lớn hơn 0, thread gọi có thể chờ permit trong khoảng thời gian đó rồi mới bị từ chối. Không dùng kiểu chờ chặn này trên event-loop của WebFlux.

Với `ThreadPoolBulkhead`, cần xét đồng thời số worker và hàng đợi. Ví dụ `coreThreadPoolSize = 2`, `maxThreadPoolSize = 2`, `queueCapacity = 4` cho phép hai tác vụ đang chạy và tối đa bốn tác vụ chờ. Khi cả hai worker bận và bốn vị trí hàng đợi đã được lấp đầy, tác vụ tiếp theo bị từ chối. Nếu `maxThreadPoolSize` lớn hơn `coreThreadPoolSize`, hành vi tạo thêm worker phụ thuộc vào việc hàng đợi đã đầy và chính sách của executor.

`queueCapacity` không phải giới hạn tổng số lời gọi đã nhận trong suốt vòng đời ứng dụng. Nó chỉ giới hạn tác vụ đang chờ. Khi worker hoàn tất, một tác vụ trong hàng đợi được chuyển sang chạy và chỗ trống của queue được giải phóng.

## Kiểm thử SemaphoreBulkhead với nhiều thread

Ví dụ dưới đây giữ lời gọi đầu tiên bên trong supplier bằng latch. Khi lời gọi đầu tiên đã lấy permit, test gọi supplier lần thứ hai trên thread kiểm thử. Vì giới hạn chỉ có một permit và thời gian chờ bằng 0, lời gọi thứ hai phải bị từ chối.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.bulkhead.BulkheadFullException;
import org.junit.jupiter.api.Test;

class SemaphoreBulkheadConcurrencyTest {

    @Test
    void rejectsCallWhenAllPermitsAreOccupied() throws Exception {
        Bulkhead bulkhead = Bulkhead.of(
            "catalog",
            BulkheadConfig.custom()
                .maxConcurrentCalls(1)
                .maxWaitDuration(Duration.ZERO)
                .build()
        );

        CountDownLatch firstCallEntered = new CountDownLatch(1);
        CountDownLatch releaseFirstCall = new CountDownLatch(1);
        ExecutorService caller = Executors.newSingleThreadExecutor();

        Supplier<String> protectedCall = Bulkhead.decorateSupplier(
            bulkhead,
            () -> {
                firstCallEntered.countDown();
                await(releaseFirstCall);
                return "catalog-data";
            }
        );

        try {
            Future<String> first = caller.submit(protectedCall::get);

            assertTrue(firstCallEntered.await(2, TimeUnit.SECONDS));

            assertThatThrownBy(protectedCall::get)
                .isInstanceOf(BulkheadFullException.class);

            releaseFirstCall.countDown();
            assertThat(first.get(2, TimeUnit.SECONDS)).isEqualTo("catalog-data");
            assertThat(bulkhead.getMetrics().getAvailableConcurrentCalls())
                .isEqualTo(1);
        } finally {
            releaseFirstCall.countDown();
            caller.shutdownNow();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for test latch");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while waiting", error);
        }
    }
}
```

Test có ba điểm đồng bộ quan trọng:

1. `firstCallEntered` báo rằng supplier đầu tiên đã bắt đầu và đang giữ permit.
2. Lời gọi thứ hai được thực hiện khi permit chắc chắn đang bận, vì vậy kết quả từ chối không phụ thuộc vào lịch chạy thread.
3. `releaseFirstCall` cho phép supplier đầu tiên kết thúc; sau đó test xác nhận permit đã được trả lại.

`finally` luôn mở latch và dừng executor để test không để lại thread đang chờ nếu assertion thất bại. Trong test suite thực tế, nên dùng timeout hữu hạn cho mọi lần chờ để một lỗi đồng bộ không làm treo toàn bộ build.

## Kiểm thử giới hạn đồng thời bằng bộ đếm hoạt động

Ngoài việc kiểm tra lời gọi thứ tư bị từ chối, có thể tạo một nhóm lời gọi đồng thời và đo số supplier đang chạy tại cùng thời điểm. `AtomicInteger` ghi số hoạt động hiện tại và số lớn nhất đã quan sát.

```java
AtomicInteger active = new AtomicInteger();
AtomicInteger maxObserved = new AtomicInteger();

Supplier<String> measuredCall = Bulkhead.decorateSupplier(bulkhead, () -> {
    int now = active.incrementAndGet();
    maxObserved.accumulateAndGet(now, Math::max);
    try {
        await(releaseCalls);
        return "ok";
    } finally {
        active.decrementAndGet();
    }
});
```

Trong test đầy đủ, tạo nhiều caller bằng `ExecutorService`, dùng latch để cùng bắt đầu, đợi các supplier đã được chấp nhận đi vào, rồi nhả latch. Cuối cùng xác nhận `maxObserved` không vượt `maxConcurrentCalls`. Nếu test đồng thời kiểm tra các lời gọi bị từ chối, cần phân biệt số task đã submit với số supplier thực sự bắt đầu; task bị từ chối không được tăng `active`.

Không đặt `maxObserved` bằng số thread trong executor của test. Executor kiểm thử chỉ tạo áp lực đồng thời; Bulkhead mới là thành phần cần xác minh. Dùng số caller lớn hơn giới hạn Bulkhead để test có khả năng phát hiện việc cấu hình bị bỏ qua.

## Kiểm thử ThreadPoolBulkhead khi queue đầy

Với ThreadPoolBulkhead, cần tạo một tác vụ đang chạy, một tác vụ đang chờ và sau đó gửi tác vụ thứ ba để xác nhận từ chối. Dùng pool có một worker và một vị trí queue để trạng thái dễ dự đoán:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadConfig;
import org.junit.jupiter.api.Test;

class ThreadPoolBulkheadQueueTest {

    @Test
    void rejectsTaskWhenWorkerAndQueueAreFull() throws Exception {
        ThreadPoolBulkhead bulkhead = ThreadPoolBulkhead.of(
            "legacy-catalog",
            ThreadPoolBulkheadConfig.custom()
                .coreThreadPoolSize(1)
                .maxThreadPoolSize(1)
                .queueCapacity(1)
                .build()
        );

        CountDownLatch firstTaskStarted = new CountDownLatch(1);
        CountDownLatch releaseFirstTask = new CountDownLatch(1);

        try {
            CompletableFuture<String> running = bulkhead.executeSupplier(() -> {
                firstTaskStarted.countDown();
                await(releaseFirstTask);
                return "running";
            });

            assertTrue(firstTaskStarted.await(2, TimeUnit.SECONDS));

            CompletableFuture<String> queued =
                bulkhead.executeSupplier(() -> "queued");

            CompletableFuture<String> rejected =
                bulkhead.executeSupplier(() -> "should-not-run");

            assertThatThrownBy(rejected::join)
                .isInstanceOf(CompletionException.class)
                .hasCauseInstanceOf(BulkheadFullException.class);

            releaseFirstTask.countDown();
            assertThat(running.get(2, TimeUnit.SECONDS)).isEqualTo("running");
            assertThat(queued.get(2, TimeUnit.SECONDS)).isEqualTo("queued");
        } finally {
            releaseFirstTask.countDown();
            bulkhead.close();
        }
    }

    private static void await(CountDownLatch latch) {
        try {
            if (!latch.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Timed out waiting for test latch");
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while waiting", error);
        }
    }
}
```

Với cấu hình trên, tác vụ `running` chiếm worker và chờ latch. Tác vụ `queued` chiếm vị trí chờ duy nhất. Tác vụ `rejected` đến khi worker lẫn queue đều đã đầy nên phải hoàn tất bất thường với `BulkheadFullException` (thường được bọc trong `CompletionException` khi gọi `join()`). Sau khi nhả latch, hai tác vụ đã được nhận phải hoàn tất.

API trả về và cách bọc exception có thể khác nhẹ theo phiên bản Resilience4j. Khi viết test cho phiên bản cụ thể, xác nhận kiểu future và cause thực tế; điều cần giữ là test chứng minh supplier thứ ba không chạy, queue không nhận thêm tác vụ và lỗi từ chối được nhận diện đúng.

## Kiểm tra tác vụ bị từ chối không chạy

Chỉ kiểm tra future thất bại chưa đủ nếu muốn chắc chắn supplier bị từ chối không thực thi. Thêm một bộ đếm vào supplier:

```java
AtomicInteger thirdTaskRuns = new AtomicInteger();

CompletableFuture<String> rejected = bulkhead.executeSupplier(() -> {
    thirdTaskRuns.incrementAndGet();
    return "should-not-run";
});

assertThatThrownBy(rejected::join)
    .isInstanceOf(CompletionException.class)
    .hasCauseInstanceOf(BulkheadFullException.class);
assertThat(thirdTaskRuns).hasValue(0);
```

Counter phải được đọc sau khi future đã hoàn tất bất thường. Nếu supplier chạy ngoài ý muốn, test phát hiện được dù response cuối cùng có thể đã bị ánh xạ thành fallback.

## Kiểm thử hàng đợi được giải phóng

Queue đầy chỉ là trạng thái tạm thời. Khi worker kết thúc, một task đang chờ được lấy ra chạy và vị trí queue trở nên trống. Test nên xác nhận một tác vụ mới có thể được nhận sau khi tải giảm:

1. Giữ tác vụ đầu tiên ở trạng thái đang chạy.
2. Gửi tác vụ thứ hai để lấp queue.
3. Xác nhận tác vụ thứ ba bị từ chối.
4. Nhả tác vụ đầu tiên và đợi tác vụ thứ hai hoàn tất.
5. Gửi tác vụ thứ tư và xác nhận nó được nhận.

Điều này phát hiện trường hợp tài nguyên không được giải phóng sau khi hoàn tất. Với SemaphoreBulkhead, kiểm tra số permit khả dụng trở lại giới hạn ban đầu. Với ThreadPoolBulkhead, kiểm tra pool vẫn nhận được công việc mới sau khi worker và queue đã có chỗ trống.

## Kiểm thử maxWaitDuration của SemaphoreBulkhead

Khi `maxWaitDuration` lớn hơn 0, lời gọi không nhất thiết bị từ chối ngay khi hết permit. Một thread có thể chờ trong khoảng thời gian cấu hình để lấy permit. Có thể kiểm tra hai nhánh:

- Nhả permit trước khi hết thời gian chờ: lời gọi đang chờ được phép tiếp tục.
- Giữ permit quá thời gian chờ: lời gọi đang chờ kết thúc bằng `BulkheadFullException`.

Trong test đồng bộ, thực hiện lời gọi chờ trên một executor riêng để thread test vẫn có thể nhả latch. Đo thời gian chỉ để xác nhận có giới hạn, không khẳng định thời gian thực thi chính xác đến từng mili giây vì scheduler của hệ điều hành có thể làm test trễ. Không dùng `maxWaitDuration` dài trên event-loop WebFlux; thao tác chờ permit có thể chặn thread xử lý nhiều request.

## Kiểm thử reactive pipeline

Với `Mono` hoặc `Flux`, có thể dùng `BulkheadOperator` để giới hạn subscription. Kiểm thử cần xác nhận:

- Subscription đầu tiên chiếm permit khi đi vào pipeline.
- Subscription vượt giới hạn nhận lỗi từ chối theo chính sách Bulkhead.
- Khi publisher hoàn tất, lỗi hoặc bị hủy, permit được giải phóng theo semantics của operator.
- Event-loop không bị block để chờ permit.

Ví dụ minh họa cách áp dụng operator:

```java
Mono<CatalogItem> protectedCall = webClient.get()
    .uri("/catalog/{id}", productId)
    .retrieve()
    .bodyToMono(CatalogItem.class)
    .transformDeferred(BulkheadOperator.of(catalogBulkhead));
```

Trong test, dùng `StepVerifier` để kiểm tra tín hiệu `onNext`, `onComplete` hoặc `onError`. Nếu cần giữ publisher đầu tiên đang chạy, dùng `Sinks.One` hoặc `Sinks.Empty` làm cổng điều khiển thay vì `Thread.sleep()`. Đăng ký subscription thứ hai khi permit đang bị giữ để xác nhận lỗi từ chối. Khi phát tín hiệu hoàn tất cho sink, xác nhận một subscription mới có thể đi qua.

Không gọi `block()` trong mã ứng dụng WebFlux để đợi permit. `block()` đôi khi được dùng trong test ở thread kiểm thử, nhưng với kiểm thử reactive nên ưu tiên `StepVerifier` để xác nhận tín hiệu và tránh tạo cách sử dụng khác với runtime.

## Phân biệt BulkheadFullException và CallNotPermittedException

Hai lỗi này phản ánh hai giới hạn khác nhau:

| Exception | Thành phần phát sinh | Ý nghĩa | Hướng kiểm tra |
| --- | --- | --- | --- |
| `BulkheadFullException` | SemaphoreBulkhead hoặc ThreadPoolBulkhead | Không còn permit, worker hoặc vị trí queue để nhận lời gọi. | Giới hạn concurrency, thời gian giữ permit, worker và queue. |
| `CallNotPermittedException` | Circuit Breaker Resilience4j | Circuit Breaker đang `OPEN` và từ chối lời gọi mới. | Failure rate, slow-call rate, cửa sổ thống kê và thời gian mở. |

Không nên gộp cả hai thành “dependency thất bại” trong mọi metric. Bulkhead có thể từ chối vì ứng dụng gọi đã hết capacity, dù dependency chưa hề nhận request. Circuit Breaker từ chối vì kết quả trước đó cho thấy dependency có thể đang suy giảm. Giữ hai nhóm riêng giúp xác định đúng nơi cần điều chỉnh.

## Kiểm thử tích hợp với Spring Cloud Circuit Breaker

Khi dùng `Resilience4JCircuitBreakerFactory`, cần xác nhận Bulkhead có được factory tự áp dụng theo cấu hình của phiên bản hay ứng dụng tự trang trí lời gọi. Không áp dụng `BulkheadOperator` thủ công thêm lần nữa nếu factory đã gắn Bulkhead, trừ khi chủ đích thiết kế hai giới hạn riêng.

Một bài kiểm thử tích hợp nên:

1. Khởi động Spring context với đúng starter và cấu hình Resilience4j.
2. Inject factory hoặc service thực tế sử dụng factory.
3. Gửi nhiều lời gọi đồng thời đến dependency giả lập có thể giữ request bằng latch.
4. Đếm số request thực sự đến dependency và xác nhận không vượt giới hạn Bulkhead.
5. Gửi thêm request khi Bulkhead đã đầy và xác nhận response/exception là lỗi từ chối Bulkhead.
6. Nhả các request đang giữ và xác nhận lời gọi tiếp theo được chấp nhận.
7. Kiểm tra Circuit Breaker vẫn có trạng thái và metrics độc lập với lỗi từ chối Bulkhead theo chính sách cấu hình.

Trong một số phiên bản Spring Cloud Circuit Breaker Resilience4j, Bulkhead được bật tự động khi module Bulkhead có mặt trên classpath; các property điều khiển việc bật/tắt và loại Bulkhead phụ thuộc phiên bản. Hãy kiểm tra tài liệu release train và condition report trước khi kết luận factory đang dùng SemaphoreBulkhead hay ThreadPoolBulkhead.

## Kiểm thử tải và giới hạn tài nguyên

Test đồng bộ xác nhận đúng/sai của giới hạn trong một tình huống nhỏ. Kiểm thử tải bổ sung giúp quan sát hành vi khi lưu lượng tăng trong thời gian dài. Nên tăng dần concurrency, giữ latency dependency ở các mức khác nhau và ghi lại:

- Số lời gọi đang hoạt động lớn nhất.
- Số lời gọi bị từ chối và tỷ lệ từ chối.
- Kích thước queue theo thời gian và số task chờ lâu nhất.
- Thời gian chờ trước khi được thực thi và thời gian xử lý thực tế.
- Số thread hoạt động, CPU, heap và số connection được sử dụng.
- Latency p95/p99 và tỷ lệ lỗi của dependency.

Không chỉ tăng queue để giảm số lần từ chối. Queue lớn có thể làm request chờ lâu hơn deadline, giữ nhiều object trong heap và làm tăng latency p99. Hãy chọn giới hạn theo năng lực dependency, connection pool, deadline nghiệp vụ và số replica. Nếu mỗi replica cho phép 20 lời gọi đồng thời và chạy 6 replica, dependency có thể nhận khoảng 120 lời gọi đồng thời từ ứng dụng đó.

## Các lỗi thường gặp khi kiểm thử

| Lỗi | Vì sao test không đáng tin | Cách sửa |
| --- | --- | --- |
| Dùng `Thread.sleep()` để hy vọng task đang chạy | Thứ tự thread thay đổi theo tải máy và scheduler. | Dùng latch/barrier để xác nhận task đã vào supplier. |
| Chỉ submit một lời gọi tại một thời điểm | Không tạo được cạnh tranh permit hoặc queue. | Dùng nhiều caller đồng thời và giữ task đầu tiên chưa kết thúc. |
| Kiểm tra số task submit thay cho số supplier bắt đầu | Task bị từ chối cũng đã được submit vào API. | Đếm bên trong supplier và xác nhận task bị từ chối không chạy. |
| Không nhả latch trong `finally` | Test thất bại có thể để thread treo và ảnh hưởng test sau. | Luôn giải phóng latch và shutdown executor trong cleanup. |
| Dùng queue không giới hạn trong test | Không thể tái hiện tình huống queue đầy. | Cấu hình `queueCapacity` nhỏ và hữu hạn. |
| Chỉ kiểm tra lỗi cuối cùng | Fallback có thể che mất lỗi từ chối ban đầu. | Kiểm tra exception, counter, supplier execution và metrics. |
| Nhầm BulkheadFullException với CallNotPermittedException | Điều tra nhầm quá tải ứng dụng thành lỗi dependency. | Assert đúng loại lỗi và theo dõi hai cơ chế riêng. |
| Chạy reactive test bằng cách block event-loop | Không phản ánh hành vi non-blocking của production. | Dùng `StepVerifier` và publisher điều khiển bằng sink. |

## Checklist trước khi chấp nhận test

- [ ] Test giữ được ít nhất một lời gọi bên trong supplier để tạo trạng thái bận có kiểm soát.
- [ ] Số lời gọi đồng thời được chấp nhận không vượt `maxConcurrentCalls` hoặc giới hạn worker.
- [ ] Test lấp đầy queue và chứng minh tác vụ tiếp theo bị từ chối.
- [ ] Supplier của tác vụ bị từ chối không được thực thi.
- [ ] Permit hoặc queue slot được giải phóng sau khi tác vụ kết thúc.
- [ ] Lời gọi mới được chấp nhận sau khi tài nguyên được giải phóng.
- [ ] Bulkhead rejection được phân biệt với Circuit Breaker open.
- [ ] Cleanup luôn nhả latch và dừng executor/pool.
- [ ] Với reactive, test không block event-loop và kiểm tra cancellation/termination.
- [ ] Cấu hình test tương ứng với đúng loại Bulkhead mà runtime thực sự sử dụng.

Kiểm thử nhiều luồng và tình huống Bulkhead đầy phải chứng minh được cả giới hạn lẫn vòng đời tài nguyên. Khi dùng latch để điều khiển lời gọi, xác nhận queue đã đầy trước khi gửi tác vụ tiếp theo và kiểm tra supplier bị từ chối không chạy, test sẽ ổn định hơn và phản ánh đúng hành vi bảo vệ trong Spring Cloud Circuit Breaker. Phân biệt rõ lỗi từ chối của Bulkhead với trạng thái `OPEN` của Circuit Breaker cũng giúp metrics và xử lý sự cố chỉ đúng nguyên nhân.
