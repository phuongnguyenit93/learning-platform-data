# delayedExecutor và việc lên lịch bắt đầu công việc

Từ Java 9, `CompletableFuture` cung cấp `delayedExecutor` để trì hoãn thời điểm một tác vụ được chuyển đến Executor thực thi. API này hữu ích khi muốn bắt đầu một bước xử lý sau một khoảng chờ, chẳng hạn trì hoãn một lần thử lại hoặc một continuation bất đồng bộ.

Điểm quan trọng là `delayedExecutor` trì hoãn **việc submit tác vụ đến executor đích**. Nó không bảo đảm tác vụ bắt đầu chính xác tại thời điểm hết delay, không tự lặp tác vụ theo chu kỳ và không cung cấp handle lịch để hủy như `ScheduledExecutorService`.

## 1. Hai overload của delayedExecutor

Java 9 bổ sung hai phương thức static:

~~~java
static Executor delayedExecutor(long delay, TimeUnit unit)
static Executor delayedExecutor(
        long delay,
        TimeUnit unit,
        Executor executor
)
~~~

- Overload hai tham số sử dụng default asynchronous execution facility của `CompletableFuture`.
- Overload ba tham số chuyển command đến executor do ứng dụng cung cấp sau khi hết delay.
- `delay` là khoảng thời gian trì hoãn; `unit` xác định đơn vị như `MILLISECONDS`, `SECONDS` hoặc `MINUTES`.

Phương thức trả về một `Executor`. Mỗi lần gọi `execute(command)`, command được giữ lại trong khoảng delay rồi mới được submit đến executor đích. Nếu delay bằng 0 hoặc âm, không có khoảng chờ dương; command vẫn được chuyển theo cơ chế thực thi của executor đích.

Với overload mặc định, CompletableFuture sử dụng default asynchronous execution facility. Trong cấu hình thông thường, facility này là `ForkJoinPool.commonPool()`. Nếu cần kiểm soát thread pool, hãy dùng overload nhận executor.

## 2. Delay không phải thời điểm bắt đầu chính xác

Ví dụ:

~~~java
Executor delayed = CompletableFuture.delayedExecutor(
        500,
        TimeUnit.MILLISECONDS
);
~~~

Delay được áp dụng cho mỗi command khi executor nhận nó. Sau khoảng thời gian đó, command được chuyển đến executor đích. Tác vụ có thể bắt đầu muộn hơn nếu executor đích đang bận hoặc hệ thống thiếu tài nguyên.

Cần phân biệt:

- Delay là khoảng chờ trước khi submit command.
- Thời gian thực thi của command bắt đầu sau khi executor đích nhận và chạy nó.
- Không có cam kết real-time rằng code bắt đầu chính xác sau 500 ms.
- Nhiều command cùng delay không có cam kết thứ tự bắt đầu chỉ vì chúng dùng chung một executor trì hoãn.

Không dùng API này để đo thời gian chính xác, đồng bộ hóa thread hoặc thực hiện deadline nghiêm ngặt.

## 3. Kết hợp với CompletableFuture

Dùng `supplyAsync` khi tác vụ trả về kết quả:

~~~java
Executor delayed = CompletableFuture.delayedExecutor(
        300,
        TimeUnit.MILLISECONDS
);

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> "work completed",
                delayed
        );
~~~

Dùng `runAsync` khi tác vụ không trả về kết quả:

~~~java
CompletableFuture<Void> future =
        CompletableFuture.runAsync(
                () -> sendNotification(),
                CompletableFuture.delayedExecutor(
                        1,
                        TimeUnit.SECONDS
                )
        );
~~~

Lời gọi tạo CompletableFuture trả về ngay; command được submit sau khoảng delay. Thread gọi không cần ngủ bằng `Thread.sleep`.

Có thể dùng delayed executor cho continuation bất đồng bộ:

~~~java
CompletableFuture<String> result = loadData()
        .thenApplyAsync(
                data -> transform(data),
                CompletableFuture.delayedExecutor(
                        200,
                        TimeUnit.MILLISECONDS
                )
        );
~~~

Continuation chỉ được submit sau khi stage trước hoàn tất và delay đã trôi qua. Nếu stage trước hoàn tất bất thường, hành vi tiếp tục tuân theo hợp đồng của loại continuation được chọn.

## 4. Chỉ định executor đích

Overload ba tham số cho phép kiểm soát nơi command thực sự chạy:

~~~java
ExecutorService workers = Executors.newFixedThreadPool(2);

Executor delayed = CompletableFuture.delayedExecutor(
        500,
        TimeUnit.MILLISECONDS,
        workers
);
~~~

Sau delay, command được submit đến `workers`. Cách này hữu ích khi cần giới hạn số thread, tách nhóm tác vụ hoặc áp dụng chính sách thực thi riêng.

Ứng dụng vẫn sở hữu executor tùy chỉnh. `delayedExecutor` không tự shutdown executor được truyền vào. Chỉ shutdown sau khi các tác vụ cần thiết đã hoàn tất hoặc đã được xử lý theo chính sách dừng.

## 5. So sánh với ScheduledExecutorService

| Nhu cầu | delayedExecutor | ScheduledExecutorService |
|---|---|---|
| Trì hoãn một lần submit | Có | Có, qua `schedule` |
| Dùng trực tiếp làm Executor cho CompletableFuture | Có | Có thể dùng executor của scheduler |
| Nhận handle để hủy lịch | Không trực tiếp | Có, `ScheduledFuture` |
| Lập lịch lặp theo chu kỳ | Không | Có, `scheduleAtFixedRate` hoặc `scheduleWithFixedDelay` |
| Chọn executor đích riêng | Có overload nhận Executor | Scheduler thực thi task của nó |

Nếu chỉ cần một Executor trì hoãn cho CompletableFuture, `delayedExecutor` thường gọn hơn. Nếu cần hủy lịch, lấy trạng thái lịch hoặc chạy định kỳ, dùng `ScheduledExecutorService`.

~~~java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> scheduled = scheduler.schedule(
        () -> sendNotification(),
        500,
        TimeUnit.MILLISECONDS
);

// Có thể yêu cầu hủy lịch trước khi task bắt đầu:
scheduled.cancel(false);
~~~

Scheduler còn cung cấp các phương thức lập lịch lặp mà delayedExecutor không có.

## 6. Retry và các bước xử lý có độ trễ

Một lần retry có thể được submit sau khoảng chờ:

~~~java
Executor retryExecutor = CompletableFuture.delayedExecutor(
        2,
        TimeUnit.SECONDS
);

CompletableFuture<String> retry =
        CompletableFuture.supplyAsync(
                () -> callRemoteService(),
                retryExecutor
        );
~~~

Đây chỉ là một lần submit có trì hoãn. Nếu cần nhiều lần retry, ứng dụng phải tự xác định số lần thử, điều kiện retry, backoff, jitter, timeout và điều kiện dừng. Không tạo vòng lặp retry vô hạn chỉ bằng cách gọi lại delayedExecutor.

Với dịch vụ từ xa, cũng cần xem xét giới hạn tốc độ, idempotency và khả năng một yêu cầu trước vẫn đang chạy khi yêu cầu retry bắt đầu.

## 7. Hủy tác vụ và giới hạn của CompletableFuture

`delayedExecutor` trả về Executor, không trả về `ScheduledFuture`. Caller không có handle lịch riêng để hủy command đang chờ.

Có thể gọi `cancel` trên CompletableFuture:

~~~java
future.cancel(false);
~~~

Lệnh này làm future chuyển sang trạng thái bị hủy nếu nó chưa hoàn tất. Tuy nhiên, cancellation của CompletableFuture không phải cam kết chung rằng một tác vụ đã bắt đầu sẽ bị interrupt hoặc dừng ngay. Nó cũng không thay thế việc đóng socket, stream hoặc tài nguyên mà tác vụ đang sử dụng.

Nếu cần hủy lịch trước khi command được submit, dùng `ScheduledExecutorService.schedule` và giữ lại `ScheduledFuture`. Nếu cần dừng một tác vụ đang chạy, thiết kế cơ chế hủy hợp tác như kiểm tra interrupt flag, token hủy hoặc đóng tài nguyên phù hợp.

## 8. Exception trong tác vụ bất đồng bộ

Exception phát sinh trong supplier hoặc runnable được lưu trong trạng thái hoàn tất bất thường của CompletableFuture. Khi gọi `join()`, lỗi thường được ném dưới dạng `CompletionException`, với nguyên nhân gốc có thể lấy qua `getCause()`.

Có thể xử lý bằng `exceptionally`, `handle` hoặc `whenComplete`:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> loadValue(),
                CompletableFuture.delayedExecutor(
                        300,
                        TimeUnit.MILLISECONDS
                )
        ).exceptionally(exception -> "fallback");
~~~

Delay không thay đổi hợp đồng xử lý exception của CompletableFuture. Hãy quan sát future hoặc gắn callback xử lý lỗi thay vì bỏ quên lỗi của tác vụ bất đồng bộ.

## 9. Ví dụ hoàn chỉnh với Java 17+

Tạo file **DelayedExecutorDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class DelayedExecutorDemo {
    public static void main(String[] args) {
        Executor defaultDelayed = CompletableFuture.delayedExecutor(
                200,
                TimeUnit.MILLISECONDS
        );

        CompletableFuture<String> defaultTask =
                CompletableFuture.supplyAsync(
                        () -> "default executor",
                        defaultDelayed
                );

        ExecutorService workers = Executors.newFixedThreadPool(2);

        try {
            Executor customDelayed = CompletableFuture.delayedExecutor(
                    200,
                    TimeUnit.MILLISECONDS,
                    workers
            );

            CompletableFuture<String> customTask =
                    CompletableFuture.supplyAsync(
                            () -> "custom executor",
                            customDelayed
                    );

            System.out.println(defaultTask.join());
            System.out.println(customTask.join());
        } finally {
            workers.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac DelayedExecutorDemo.java
java DelayedExecutorDemo
~~~

Kết quả stdout:

~~~text
default executor
custom executor
~~~

Ví dụ minh họa hai overload. Tác vụ thứ nhất dùng default asynchronous execution facility; tác vụ thứ hai được submit đến thread pool do ứng dụng tạo. `join()` chờ kết quả, còn `shutdown()` giải phóng thread pool tùy chỉnh sau khi tác vụ hoàn tất.

Output không phụ thuộc thread nào chạy trước vì chương trình in theo thứ tự gọi `join()`, không giả định thời điểm bắt đầu chính xác.

## 10. Lỗi thường gặp

**Nhầm delayedExecutor với một thread ngủ:** executor trì hoãn việc submit command; nó không làm thread gọi `execute` ngủ trong suốt khoảng delay.

**Cho rằng tác vụ bắt đầu chính xác khi hết delay:** command chỉ được chuyển đến executor đích sau delay; hàng đợi và tải hệ thống có thể khiến nó bắt đầu muộn hơn.

**Dùng delayedExecutor để chạy lặp:** mỗi lần submit là một lần trì hoãn. Muốn chạy định kỳ, dùng ScheduledExecutorService.

**Cho rằng có thể hủy lịch bằng Executor:** Executor không cung cấp ScheduledFuture. Dùng scheduler nếu cần hủy lịch.

**Quên shutdown executor tùy chỉnh:** executor truyền vào vẫn do ứng dụng quản lý.

**Cho rằng cancel luôn interrupt tác vụ:** CompletableFuture cancellation không bảo đảm dừng computation đang chạy. Dùng cơ chế hủy hợp tác và quản lý tài nguyên riêng.

**Bỏ qua exception của future:** tác vụ bất đồng bộ có thể hoàn tất bất thường; quan sát kết quả bằng join/get hoặc callback xử lý lỗi.

## 11. Checklist lựa chọn

- Cần trì hoãn việc submit một tác vụ CompletableFuture: dùng `CompletableFuture.delayedExecutor`.
- Dùng overload hai tham số khi chấp nhận default async facility.
- Dùng overload ba tham số khi cần chỉ định executor đích.
- Không giả định tác vụ bắt đầu chính xác khi delay kết thúc.
- Cần hủy lịch, lấy ScheduledFuture hoặc chạy định kỳ: dùng ScheduledExecutorService.
- Quản lý executor tùy chỉnh và tài nguyên theo đúng quyền sở hữu.
- Xử lý cancellation và exception của CompletableFuture tường minh.

`CompletableFuture.delayedExecutor` là API hiện hành từ Java 9 để trì hoãn việc chuyển command đến executor thực thi. Chọn nó khi cần một Executor có delay cho tác vụ bất đồng bộ; chọn ScheduledExecutorService khi cần quản lý lịch, hủy lịch hoặc thực thi định kỳ.
