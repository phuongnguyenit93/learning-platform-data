# CompletableFuture.delayedExecutor(): lên lịch khởi chạy mà không chặn luồng chờ

## 1. Tình huống thực tế và mục tiêu

Một hệ thống Java có thể cần **khởi chạy một bước sau khoảng trễ**: đợi một chút trước khi thử lại thao tác tạm thời lỗi, trì hoãn ghi metric, kích hoạt bước xử lý khi điều kiện thời gian chín muồi, hoặc tạo khoảng cách giữa hai lần gọi dịch vụ. Một cách làm dễ nghĩ tới là:

~~~java
// Không phải chương trình độc lập.
Thread.sleep(500);
doWork();
~~~

`Thread.sleep(500)` **chặn chính thread đang chạy** trong thời gian ngủ. Nếu dòng này nằm trên request thread, event handler, hoặc worker pool đang ít thread, nó giữ một thread không làm được công việc khác. Nếu cùng lúc có hàng nghìn tác vụ “đợi một chút”, việc dùng sleep để trì hoãn từng task có thể lãng phí worker và gây nghẽn.

Từ **Java 9**, `CompletableFuture.delayedExecutor(...)` cung cấp một cách khác: **đặt lịch để công việc được gửi tới executor sau một khoảng trễ**, thay vì buộc thread của caller phải ngủ cho tới thời điểm đó.

~~~java
// Chữ ký API; không phải chương trình độc lập.
static Executor delayedExecutor(long delay, TimeUnit unit);

static Executor delayedExecutor(
    long delay, TimeUnit unit, Executor executor);
~~~

Hai overload trả về **`Executor`**; chúng không trả `ScheduledFuture`, không tự trả kết quả nghiệp vụ và không tạo một Future để theo dõi tác vụ đơn lẻ. Ta thường kết hợp executor được trả về với `CompletableFuture.runAsync(...)`, `supplyAsync(...)` hoặc các continuation `thenApplyAsync(...)`, `thenRunAsync(...)`.

**Nguyên tắc chính:** Việc **lên lịch khởi chạy** không chặn caller. Nhưng nếu caller tiếp tục gọi `join()` hay `get()` ngay trên Future chưa hoàn tất, thì **chính lời gọi chờ đó** vẫn có thể chặn caller.

Bài này thuộc phạm vi **Java concurrency nói chung** và chỉ dùng API chuẩn của JDK, không đi vào cơ chế framework.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích ba thời điểm: **gửi lịch**, **hết thời gian trễ**, **thực sự được worker chạy**.
2. Phân biệt hai overload `delayedExecutor` và lý do nên truyền base executor cho workload có yêu cầu vận hành.
3. Hiểu rằng mỗi lần gọi `execute(...)` trên delayed executor bắt đầu một khoảng trễ **riêng**.
4. Kết hợp `runAsync`, `supplyAsync` và `thenApplyAsync` với executor trì hoãn.
5. Viết ví dụ Java 17+ đúng về lifecycle, exception, timeout và kết quả stdout.
6. Không dùng `cancel(true)` trên `CompletableFuture` như bằng chứng supplier đã bị interrupt hoặc công việc bên ngoài đã dừng.
7. Biết khi nào nên chọn `ScheduledExecutorService`, `ScheduledFuture`, retry policy có deadline, hoặc cấu trúc scheduling khác.
8. Kiểm thử có kiểm soát mà không khẳng định scheduler chạy chính xác tại một mốc đồng hồ tường.

## 2. Hợp đồng API: delayedExecutor thực sự làm gì?

Javadoc `CompletableFuture` mô tả: phương thức trả về một executor **gửi task tới executor nền sau khoảng delay cho trước**, hoặc **không delay nếu giá trị delay không dương**. Mỗi khoảng trễ bắt đầu khi gọi `execute` trên executor được trả về.

~~~text
Thread caller                    delayed executor            base executor
     |                                 |                           |
     |-- execute(runnable) ----------->|                           |
     |<--------- trở về --------------|                           |
     |                                 |  đợi điều kiện thời gian  |
     |        caller làm việc khác     |                           |
     |                                 |---- submit runnable ----->|
     |                                 |                           |
     |                                 |                   worker chạy runnable
     |                                 |                           |
     |                                 |                   runnable hoàn tất
~~~

Khác `Thread.sleep()`, việc chờ delay trong sơ đồ **không bắt caller phải giữ một thread đang ngủ cho mỗi tác vụ đã lên lịch**. Chi tiết timer/scheduler nội bộ là vấn đề triển khai JDK và không nên dựa vào số lượng thread nội bộ hoặc tên thread nội bộ như một API contract.

### 2.1. Ba thời điểm cần phân biệt

| Mốc | Nghĩa | Độ chính xác có thể dựa vào |
| --- | --- | --- |
| **T0 – gọi `execute`** | Caller yêu cầu delayed executor nhận task; đồng hồ delay cho lần gọi đó bắt đầu | Mốc logic của yêu cầu |
| **T1 – đủ delay** | Task đủ điều kiện được gửi sang base executor | Không phải bảo đảm task đã chạy |
| **T2 – base worker bắt đầu** | Thread do base executor phân công thực thi task | Có thể muộn hơn T1 do queue/scheduler/tải |
| **T3 – task hoàn tất** | `CompletableFuture` liên quan có outcome | Có thể muộn hơn T2 do CPU/I/O hoặc block |

Không được đồng nhất `delay = 500 ms` với “tác vụ sẽ kết thúc sau đúng 500 ms”. Delayed executor không đưa ra SLA realtime chính xác từng mili-giây; scheduler, OS, CPU, GC, executor queue và tải hệ thống có thể khiến task thực thi **sau** thời điểm đủ điều kiện.

### 2.2. Hai overload

**Không cung cấp executor nền:**

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
Executor delayed =
    CompletableFuture.delayedExecutor(
        250, TimeUnit.MILLISECONDS);
~~~

Task được gửi tới **default executor** theo hợp đồng của `CompletableFuture`. Không nên mặc định rằng các task blocking I/O đều phù hợp với default async execution facility. Phần lớn trường hợp dùng `CompletableFuture` thông thường có liên quan tới `ForkJoinPool.commonPool()` theo quy định của class, cùng những ngoại lệ về mức song song; hãy xem hợp đồng JDK đang chạy.

**Có executor nền rõ ràng:**

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
ExecutorService base =
    Executors.newFixedThreadPool(4);

Executor delayed =
    CompletableFuture.delayedExecutor(
        250, TimeUnit.MILLISECONDS, base);
~~~

Khi hết delay, công việc được gửi tới `base`; bạn chủ động quản lý kích thước pool, tên thread, queue, rejection policy và shutdown. `delayed` chỉ có kiểu `Executor`, không có `shutdown()`; executor nền nếu là `ExecutorService` cần được quản lý theo lifetime của ứng dụng.

### 2.3. Delayed executor không tự thực thi logic nghiệp vụ

~~~java
// Mẫu minh họa; không phải chương trình độc lập.
Executor delayed =
    CompletableFuture.delayedExecutor(100, TimeUnit.MILLISECONDS);

// Chỉ tạo Executor, chưa có runnable được đăng ký.
~~~

Chưa có task nào được lên lịch chỉ vì bạn tạo executor. Delay cho một task thực sự bắt đầu khi **`delayed.execute(runnable)` được gọi** — thường là trong `runAsync(...)` hay khi một async continuation đủ điều kiện chạy.

## 3. Ví dụ 1 — delay dương, caller không cần sleep (Java 17+)

Ta dùng một delay dương và hai latch. Latch thứ nhất báo worker đã bắt đầu, latch thứ hai giữ worker **chưa hoàn tất** cho tới khi main kiểm tra `isDone()`. Như vậy output ổn định mà không phải đoán thời lượng chạy của OS.

Tạo tệp `DelayedStartDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class DelayedStartDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                30, TimeUnit.MILLISECONDS, base);

            CompletableFuture<String> job =
                CompletableFuture.supplyAsync(() -> {
                    entered.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException(
                            "worker interrupted", ex);
                    }
                    return "finished";
                }, delayed);

            // Main không dùng sleep để giữ thread chờ delay.
            // Latch xác nhận worker đã thực sự bắt đầu.
            entered.await();
            System.out.println("worker started = true");
            System.out.println("done before release = "
                + job.isDone());

            release.countDown();
            System.out.println("result = " + job.join());
        } finally {
            release.countDown();
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy trên JDK 17+:

~~~bash
javac DelayedStartDemo.java
java DelayedStartDemo
~~~

Stdout khi không có ngắt ngoại lai:

~~~text
worker started = true
done before release = false
result = finished
~~~

**Giải thích:**

1. `supplyAsync(..., delayed)` đưa runnable vào delayed executor; method trả một `CompletableFuture<String>` **ngay, không cần caller ngủ 30 ms**.
2. Sau khi đủ delay, runnable được submit vào `base`. Worker gọi `entered.countDown()`, rồi chờ `release`.
3. Main chờ **sự kiện có thể kiểm tra** `entered`, chứ không dùng `Thread.sleep(...)` để đoán worker đã bắt đầu chưa.
4. Main in `job.isDone() == false` trước khi mở `release`, vì worker vẫn đang chờ latch.
5. Main mở latch, `join()` chờ giá trị hoàn tất và in `finished`.
6. `finally` mở latch dù có lỗi ở caller, sau đó shutdown base pool để không rò worker.

Điểm cần nhìn đúng: ví dụ **có `entered.await()` và `join()` làm main chờ để kiểm chứng**, nhưng **bản thân hành động lên lịch** của delayed executor không chặn main trong thời gian delay. Đây là hai hành động khác nhau. Trong ứng dụng thực, caller có thể nhận Future và tiếp tục xử lý việc khác thay vì đợi.

## 4. Mỗi lần execute có một khoảng trễ riêng

Một `Executor delayed` có thể dùng lại cho nhiều task. Đừng hiểu nó là một chiếc đồng hồ duy nhất bắt đầu ở thời điểm bạn gọi `delayedExecutor(...)`.

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
Executor delayed = CompletableFuture.delayedExecutor(
    500, TimeUnit.MILLISECONDS, base);

CompletableFuture<Void> a =
    CompletableFuture.runAsync(this::doA, delayed);

// Sau đó, ở một thời điểm khác:
CompletableFuture<Void> b =
    CompletableFuture.runAsync(this::doB, delayed);
~~~

Delay của A bắt đầu khi runnable của A được gửi qua `execute`. Delay của B bắt đầu **khi runnable của B được gửi**, không tính từ lúc object delayed executor được tạo và không tính từ lúc A được gửi.

Điều này rất quan trọng khi xây dựng retry, deferred callback hoặc quy trình có nhiều stage. Từng lần submission tạo một yêu cầu delay mới; delayed executor không đồng nghĩa lịch chạy định kỳ.

### 4.1. Ví dụ 2 — dùng cùng delayed executor nhiều lần (Java 17+)

Tạo tệp `ReuseDelayedExecutorDemo.java`:

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ReuseDelayedExecutorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newFixedThreadPool(2);
        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                20, TimeUnit.MILLISECONDS, base);

            CompletableFuture<Integer> a =
                CompletableFuture.supplyAsync(() -> 10, delayed);
            CompletableFuture<Integer> b =
                CompletableFuture.supplyAsync(() -> 20, delayed);

            CompletableFuture.allOf(a, b).join();
            System.out.println("results = "
                + List.of(a.join(), b.join()));
            System.out.println("both done = "
                + (a.isDone() && b.isDone()));
        } finally {
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ReuseDelayedExecutorDemo.java
java ReuseDelayedExecutorDemo
~~~

Stdout:

~~~text
results = [10, 20]
both done = true
~~~

Hai runnable được gửi qua **cùng object delayed executor**, nhưng mỗi lời gọi `supplyAsync` đăng ký task riêng và bắt đầu delay riêng. `allOf` đợi cả hai Future hoàn tất rồi giá trị được lấy theo thứ tự A, B — **không phải thứ tự hoàn tất trên worker**.

Không dùng elapsed time của ví dụ này để suy ra scheduler đã đáp ứng chính xác 20 ms; nó chỉ kiểm tra **hợp đồng kết quả và phối hợp**.

### 4.2. Delay không dương

Javadoc cho phép delay **bằng 0 hoặc âm**: không áp dụng thời gian trễ dương. Đây là cách dùng hợp lệ khi bạn có chung pipeline nhưng tham số delay được tính toán động.

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
Executor noDelay = CompletableFuture.delayedExecutor(
    0, TimeUnit.MILLISECONDS, base);
~~~

**Không được suy ra `delay <= 0` làm task chạy ngay trên thread caller.** Nó vẫn là cơ chế `Executor`; thực thi phụ thuộc base executor và scheduler. “Không thêm delay” khác “thực thi đồng bộ”.

Nếu dùng giá trị âm do sai số tính toán deadline, hãy hiểu đó là yêu cầu chạy không trì hoãn, không phải lỗi buộc JDK ném exception. Tuy nhiên **`TimeUnit` hoặc base executor là null** không phải giá trị hợp lệ; tránh truyền null và kiểm tra các tham số do caller cung cấp.

## 5. Chạy ở đâu? Tầm quan trọng của base Executor

Với overload ba tham số:

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
Executor delayed =
    CompletableFuture.delayedExecutor(
        100, TimeUnit.MILLISECONDS, ioPool);
~~~

Executor bị trì hoãn là một **lớp chuyển tiếp**. Sau delay, tác vụ **được gửi tới `ioPool`**; thread nào thực thi do ioPool quyết định.

- Base executor **một worker**: hai task đủ hạn có thể phải chạy tuần tự nếu một task chiếm worker.
- Base executor **nhiều worker**: các task có cơ hội chạy đồng thời theo pool capacity.
- Base executor **queue có giới hạn**: khi quá tải, việc submit có thể bị từ chối theo rejection policy.
- Base executor **đã shutdown** trước thời điểm submit: delayed runnable không còn đương nhiên được chấp nhận.
- Base executor custom thực thi inline: hợp đồng chấp nhận base executor tùy biến, nhưng bạn phải hiểu cách executor đó chạy runnable. Không mặc định có một thread mới cho mỗi task.

**Không hứa thời gian hoàn tất đúng bằng delay** khi base executor có queue dài. Delay chỉ liên quan thời điểm task được gửi sang base, không bảo đảm lúc worker bắt đầu.

### 5.1. Ví dụ 3 — kiểm soát tên thread thực thi (Java 17+)

Tạo tệp `DelayedBaseExecutorDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class DelayedBaseExecutorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor(
            task -> new Thread(task, "delayed-base-1")
        );

        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                25, TimeUnit.MILLISECONDS, base);

            CompletableFuture<String> currentThreadName =
                CompletableFuture.supplyAsync(
                    () -> Thread.currentThread().getName(), delayed
                );

            System.out.println("running on = "
                + currentThreadName.join());
        } finally {
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DelayedBaseExecutorDemo.java
java DelayedBaseExecutorDemo
~~~

Stdout:

~~~text
running on = delayed-base-1
~~~

Task thực tế chạy trên thread mà `base` tạo ra, chứ không chạy trên main chỉ vì main gọi `supplyAsync`. Khi không cung cấp base, bạn cũng không nên dựa vào tên của thread nội bộ như một hợp đồng công khai.

Trong production, nên cấu hình một `ThreadFactory` với tên tăng dần theo pool thay vì một tên cố định nếu có nhiều worker. Ngoài ra cần quản lý unhandled task failures và lifecycle executor theo chính sách ứng dụng.

## 6. delayedExecutor trong chuỗi CompletionStage

Không chỉ hỗ trợ `supplyAsync`, delayed executor còn dùng được ở các method `...Async(..., Executor)`.

Ví dụ:

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
CompletableFuture<String> response =
    firstStage.thenApplyAsync(
        value -> normalize(value),
        CompletableFuture.delayedExecutor(
            200, TimeUnit.MILLISECONDS, base)
    );
~~~

Continuation `normalize(value)` không được submit cho delayed executor **trước khi `firstStage` hoàn tất bình thường**. Khi `firstStage` hoàn tất, logic dependent stage mới đưa runnable vào delayed executor; **kể từ đó** mới bắt đầu tính delay của continuation.

Nếu `firstStage` thất bại, một `thenApplyAsync` bình thường không chạy function normalize. Future phụ thuộc được hoàn tất ngoại lệ theo semantics CompletionStage; không có lý do để “sleep 200 ms rồi mới ném lỗi” chỉ vì bạn gắn delayed executor với success-only continuation.

### 6.1. thenApply khác thenApplyAsync

- `thenApply(fn)` không nhận executor; function có thể chạy đồng bộ ở thread hoàn tất stage hoặc thread đăng ký sau khi stage đã xong, tùy tình huống.
- `thenApplyAsync(fn)` dùng default async executor.
- `thenApplyAsync(fn, delayed)` đăng ký continuation cần submit qua delayed executor **sau khi dependency sẵn sàng**.
- `thenRunAsync(action, delayed)` dùng khi continuation không cần giá trị đầu vào.
- `handleAsync((value, error) -> ..., delayed)` có thể chạy trên cả normal/exceptional completion, nhưng exception handling phải theo chính sách rõ ràng.

Không dùng một `thenApply` không có tham số executor rồi cho rằng delayed executor ở stage trước sẽ tự trì hoãn **mọi** continuation sau đó. Mỗi stage có chính sách thực thi riêng.

### 6.2. Ví dụ 4 — delay chỉ bắt đầu sau khi upstream hoàn tất (Java 17+)

Tạo tệp `DelayedContinuationDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class DelayedContinuationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<String> upstream =
                new CompletableFuture<>();

            Executor delayed = CompletableFuture.delayedExecutor(
                30, TimeUnit.MILLISECONDS, base);

            CompletableFuture<String> downstream =
                upstream.thenApplyAsync(
                    text -> text + "-after-delay", delayed);

            System.out.println("before upstream = "
                + downstream.isDone());

            upstream.complete("ready");
            System.out.println("result = " + downstream.join());
            System.out.println("upstream = " + upstream.join());
        } finally {
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DelayedContinuationDemo.java
java DelayedContinuationDemo
~~~

Stdout:

~~~text
before upstream = false
result = ready-after-delay
upstream = ready
~~~

Vì `upstream` chưa hoàn tất tại dòng in đầu, `downstream` không thể hoàn tất. Khi `upstream.complete("ready")` chạy, continuation mới đủ điều kiện submit qua delayed executor. `join()` của main sau đó **có thể chờ**, nhưng việc **gắn continuation** ban đầu không chặn caller.

Nếu upstream không bao giờ hoàn tất, delay của continuation **không bao giờ bắt đầu**. Đây là điểm khác biệt lớn với mô hình “hẹn giờ tuyệt đối tính từ lúc tạo pipeline”.

### 6.3. Delay lũy tiến trong chuỗi nhiều stage

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
Executor delayed = CompletableFuture.delayedExecutor(
    100, TimeUnit.MILLISECONDS, base);

CompletableFuture<String> result =
    CompletableFuture.completedFuture("A")
        .thenApplyAsync(s -> s + "B", delayed)
        .thenApplyAsync(s -> s + "C", delayed);
~~~

Hai continuation **không** cùng được submit tại một thời điểm. Stage thứ hai chỉ đủ điều kiện sau khi stage thứ nhất hoàn tất; mỗi lần submit qua `delayed` tạo một khoảng delay riêng. Do đó có thể phát sinh **hai khoảng chờ liên tiếp** cộng với thời gian thực thi/queue. Không giả định tổng thời gian chính xác 200 ms.

Nếu muốn “chỉ trì hoãn một lần trước cả chuỗi”, tạo stage đầu tiên được lên lịch bằng delayed executor, rồi dùng continuation không trì hoãn hoặc chỉ định base executor tùy ý.

## 7. Điểm dễ nhầm: delay, blocking, completion

### 7.1. Non-blocking scheduling không đồng nghĩa non-blocking business code

~~~java
// Minh họa, không phải chương trình độc lập.
CompletableFuture<String> future =
    CompletableFuture.supplyAsync(
        () -> readBlockingSocket(),
        CompletableFuture.delayedExecutor(
            100, TimeUnit.MILLISECONDS, base)
    );
~~~

Caller không cần ngủ trong 100 ms để lên lịch. Nhưng khi worker cuối cùng chạy `readBlockingSocket()`, **worker đó vẫn có thể bị chặn bởi socket**. delayedExecutor không biến một API I/O đồng bộ thành I/O non-blocking.

Nếu có nhiều task I/O chặn lâu, cần giới hạn connection, cấu hình pool, timeout và cancellation đúng theo nguồn I/O. Delayed executor chỉ giải quyết **thời điểm submit**, không giải quyết mọi vấn đề blocking.

### 7.2. join() và get() vẫn chờ

~~~java
// Có thể block caller đến khi delay + work hoàn tất.
String value = CompletableFuture.supplyAsync(
    () -> "done", delayedExecutor).join();
~~~

Đoạn này viết bằng async API nhưng caller vẫn chờ kết quả. Cách dùng không chặn caller là **giữ Future để compose**:

~~~java
// Mẫu minh họa, không phải chương trình độc lập.
CompletableFuture<String> value =
    CompletableFuture.supplyAsync(
        () -> "done", delayedExecutor);

CompletableFuture<Void> useLater =
    value.thenAccept(this::consume);
// Caller có thể tiếp tục công việc khác.
~~~

Chọn cách dùng theo contract của caller: cần kết quả ngay thì việc chờ có thể là chủ ý; chỉ muốn đặt lịch thì không gọi `join` ngay.

### 7.3. Delay không phải deadline

`delayedExecutor(500, MILLISECONDS)` nói **đợi trước khi submit**. `orTimeout(500, MILLISECONDS)` nói **nếu Future chưa hoàn tất trong khoảng thời gian đó thì hoàn tất ngoại lệ với TimeoutException**. Hai ý nghĩa trái ngược:

| API | Hành vi mục tiêu |
| --- | --- |
| `delayedExecutor(d, unit)` | Trì hoãn lúc đưa runnable vào base executor |
| `Thread.sleep(d)` | Chặn current thread trong khoảng chờ |
| `CompletableFuture.orTimeout(d, unit)` | Đặt timeout exceptional completion cho Future nếu chưa xong |
| `CompletableFuture.completeOnTimeout(v, d, unit)` | Hoàn tất Future bằng fallback value nếu chưa xong |
| `Future.get(d, unit)` | Giới hạn thời gian **caller chờ** |
| `ScheduledExecutorService.schedule(..., d, unit)` | Lên lịch one-shot task và trả `ScheduledFuture` |
| `scheduleAtFixedRate/scheduleWithFixedDelay` | Lịch chạy định kỳ; không có sẵn trong delayedExecutor |

`orTimeout` và `completeOnTimeout` trả về **chính CompletableFuture được gọi**, không mặc định một bản sao độc lập. Cả hai ảnh hưởng **outcome của Future**, chứ không tự interrupt công việc đang chạy hoặc hủy lời gọi mạng đã gửi.

### 7.4. Vì sao không dùng delay để “đảm bảo task A đã xong”?

Sai lầm:

~~~java
// SAI: không bảo đảm A đã hoàn tất.
startA();
CompletableFuture.runAsync(
    this::startB,
    CompletableFuture.delayedExecutor(
        100, TimeUnit.MILLISECONDS)
);
~~~

Nếu A mất 500 ms, B vẫn có thể bắt đầu khi A chưa xong. Khi B **phụ thuộc vào kết quả A**, dùng `thenRun`, `thenCompose` hoặc continuation phụ thuộc Future của A thay vì đoán thời lượng bằng một delay tùy ý.

Delay là công cụ **scheduling theo thời gian**; Future dependency mới là cách diễn đạt quan hệ “sau khi công việc khác hoàn tất”.

## 8. Exception và xử lý thất bại

Task chạy thông qua `supplyAsync` hoặc `runAsync` có thể ném unchecked exception. `CompletableFuture` tương ứng sẽ hoàn tất ngoại lệ.

### Ví dụ 5 — lỗi từ task trì hoãn được giữ trong CompletableFuture (Java 17+)

Tạo tệp `DelayedFailureDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class DelayedFailureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor();
        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                20, TimeUnit.MILLISECONDS, base);

            CompletableFuture<String> result =
                CompletableFuture.supplyAsync(() -> {
                    throw new IllegalArgumentException("invalid");
                }, delayed);

            try {
                result.join();
            } catch (CompletionException ex) {
                System.out.println("failure = "
                    + ex.getCause().getClass().getSimpleName());
            }

            System.out.println("exceptional = "
                + result.isCompletedExceptionally());
        } finally {
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DelayedFailureDemo.java
java DelayedFailureDemo
~~~

Stdout:

~~~text
failure = IllegalArgumentException
exceptional = true
~~~

`join()` có thể ném `CompletionException` bao bọc nguyên nhân task. Nếu dùng `get()`, một task thất bại thông thường được báo bằng `ExecutionException`. Đừng để exception bị giữ trong Future nhưng không có ai quan sát: nếu task có vai trò quan trọng, caller phải có kênh giám sát, callback hoặc future composition.

**Không coi delayedExecutor là error handler.** Nó chỉ quyết định khi nào giao task cho base. Retry, fallback, circuit breaking, logging và phân loại lỗi là trách nhiệm riêng.

### 8.1. Base executor bị từ chối task

Hãy cân nhắc trường hợp:

~~~text
T0: delayed.execute(task) được gọi, delay chưa hết
T1: ứng dụng shutdown base executor
T2: delay hết, delayed executor cố submit task sang base
T3: base không nhận task vì đã shutdown
~~~

Không có bảo đảm task sẽ chạy thành công nếu base không còn nhận công việc. `RejectedExecutionException` và chính sách rejection của base executor là những yếu tố phải quan sát. **Không tự khẳng định mọi implementation đều chuyển tất cả lỗi reject trễ thành cùng một exception trong Future**; hãy test theo JDK và base executor thực tế, đặt deadline cho chờ outcome, và quản lý shutdown có trật tự.

Một lỗi vận hành phổ biến là shutdown base ngay sau khi đăng ký task delay mà chưa chờ những task đó được bàn giao/thực thi. Thiết kế lifetime phải bao trùm cả thời gian chờ delay lẫn thời gian chạy task.

## 9. Cancellation: cancel Future không phải bảo đảm công việc dừng

### 9.1. CompletableFuture.cancel có giới hạn riêng

`CompletableFuture.cancel(boolean mayInterruptIfRunning)` đánh dấu Future hoàn tất bằng trạng thái cancellation nếu việc hủy được chấp nhận. Theo hợp đồng `CompletableFuture`, tham số `mayInterruptIfRunning` **không được dùng để điều khiển việc chạy công việc**; không xem `cancel(true)` là lời hứa worker sẽ bị interrupt.

Với task đã bắt đầu:

- Future có thể báo cancelled trong lúc user code vẫn đang chạy.
- Worker có thể tiếp tục các side effect sau khi Future bị cancel.
- Việc cancel không tự đóng connection, rollback giao dịch hoặc hoàn tất cleanup.
- Nếu task đã hoàn tất trước khi cancel, `cancel` không thể đổi outcome terminal trước đó.
- Nếu cancel trước lúc runnable thực sự được chạy, implementation có thể tránh gọi user code, nhưng **không dựa vào điều đó làm cơ chế hủy tác vụ bên ngoài**.

### 9.2. Ví dụ 6 — Future đã cancel nhưng task đang chạy vẫn hoàn thành side effect (Java 17+)

Ví dụ dùng latch để bảo đảm task **đã bắt đầu** trước khi cancel; vì vậy không phụ thuộc race “cancel trước khi task được worker nhận”.

Tạo tệp `DelayedCancellationDemo.java`:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DelayedCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService base = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sideEffect = new AtomicBoolean();

        try {
            Executor delayed = CompletableFuture.delayedExecutor(
                20, TimeUnit.MILLISECONDS, base);

            CompletableFuture<Void> future =
                CompletableFuture.runAsync(() -> {
                    entered.countDown();
                    try {
                        release.await();
                        sideEffect.set(true);
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    } finally {
                        finished.countDown();
                    }
                }, delayed);

            entered.await();
            boolean cancelled = future.cancel(true);
            release.countDown();
            finished.await();

            System.out.println("cancel accepted = " + cancelled);
            System.out.println("future cancelled = "
                + future.isCancelled());
            System.out.println("side effect = "
                + sideEffect.get());
        } finally {
            release.countDown();
            base.shutdown();
            if (!base.awaitTermination(5, TimeUnit.SECONDS)) {
                base.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac DelayedCancellationDemo.java
java DelayedCancellationDemo
~~~

Stdout trong tình huống test không có interrupt ngoài ý muốn:

~~~text
cancel accepted = true
future cancelled = true
side effect = true
~~~

Phân tích:

1. `entered.await()` bảo đảm runnable đã bắt đầu, đã gọi `entered.countDown()` và đang chờ `release` hoặc sắp đến lời gọi chờ.
2. Main gọi `future.cancel(true)` khi Future chưa hoàn tất. CompletableFuture đánh dấu cancelled nhưng **không có bảo đảm interrupt worker**.
3. Main mở `release`, worker tiếp tục `sideEffect.set(true)`. `finished` cho biết đường code cuối đã thực hiện.
4. Future vẫn ở trạng thái cancelled, mặc dù user code đã thực hiện side effect.
5. `finally` đảm bảo mở latch ngay cả khi caller gặp lỗi, tránh worker kẹt; base được shutdown.

**Bài học:** Nếu cần hủy công việc thật sự, bạn phải thiết kế token hủy được worker kiểm tra, API I/O có cancellation, giới hạn deadline, hoặc ownership của executor/task phù hợp. Việc chỉ hủy `CompletableFuture` không đủ để chứng minh tài nguyên đã được giải phóng.

### 9.3. Hủy trước khi hết delay

Nếu Future bị cancel khi task còn đang đợi lịch, tùy implementation user code có thể không được gọi khi runnable cuối cùng tới base. Tuy nhiên một timer đã được đăng ký trước đó có thể vẫn còn tồn tại tới thời điểm đủ hạn, và cancellation outcome không bảo đảm mọi tài nguyên scheduling nội bộ đã được gỡ theo cách bạn mong muốn.

Nếu nhu cầu là **hủy chính xác một timer chưa kích hoạt**, có thể cân nhắc `ScheduledExecutorService.schedule`, nơi caller giữ một `ScheduledFuture` để gọi `cancel(...)` theo hợp đồng. `delayedExecutor` chỉ trả `Executor`, không có phương thức `cancel(taskId)`.

## 10. Vì sao delayedExecutor không phải bộ lập lịch toàn năng?

### 10.1. Nó chỉ trả Executor

`Executor.execute(Runnable)` có kiểu trả về `void`. Bạn có thể lấy `CompletableFuture` khi dùng `runAsync`/`supplyAsync`, nhưng đó là **Future kết quả của task**, không phải `ScheduledFuture` quản lý lịch trình trực tiếp.

Không có các method sau trên object trả về bởi `delayedExecutor`:

~~~java
// Sai nếu delayed chỉ khai báo là Executor:
// delayed.scheduleAtFixedRate(...);
// delayed.scheduleWithFixedDelay(...);
// delayed.getDelay(...);
// delayed.shutdown();
~~~

Muốn lịch tuần hoàn, thường dùng `ScheduledExecutorService` hoặc cơ chế scheduling có lifecycle rõ ràng. Muốn trì hoãn **một bước bất đồng bộ** trong pipeline CompletableFuture, delayedExecutor là một cách biểu diễn tự nhiên.

### 10.2. So sánh với ScheduledExecutorService

| Đặc điểm | `CompletableFuture.delayedExecutor` | `ScheduledExecutorService` |
| --- | --- | --- |
| Kết quả API tạo lịch | `Executor` | Service hỗ trợ `schedule` và các API định kỳ |
| Khi gửi một runnable | `execute`, hoặc dùng qua `runAsync` | `schedule(command, delay, unit)` |
| Return handle của một lần submit | `execute` trả void; `runAsync` trả CompletableFuture | `schedule` trả `ScheduledFuture` |
| Delay | Trước khi submit vào base executor | Đợi tới thời gian đủ điều kiện chạy theo scheduler |
| Lịch định kỳ | Không có method định kỳ riêng | `scheduleAtFixedRate`, `scheduleWithFixedDelay` |
| Hủy lịch cụ thể | Không có timer handle riêng từ `Executor` | Có `ScheduledFuture.cancel(...)` |
| Lifecycle | Base executor cần được quản lý riêng | Service có `shutdown` và `awaitTermination` |
| Compose pipeline | Rất tiện trong `thenApplyAsync` / `runAsync` | Cần bridge sang Future/CompletableFuture nếu muốn compose |

Cả hai đều chịu ảnh hưởng của scheduler và tải; không có API nào ở đây biến chương trình thành realtime scheduler cứng.

### 10.3. Ví dụ 7 — ScheduledFuture có cancellation handle (Java 17+)

Tạo tệp `ScheduledAlternativeDemo.java`:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ScheduledAlternativeDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<String> task = scheduler.schedule(
                () -> "scheduled-ok",
                20, TimeUnit.MILLISECONDS
            );

            System.out.println("result = " + task.get());
            System.out.println("done = " + task.isDone());
        } finally {
            scheduler.shutdown();
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                scheduler.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac ScheduledAlternativeDemo.java
java ScheduledAlternativeDemo
~~~

Stdout:

~~~text
result = scheduled-ok
done = true
~~~

`schedule` trả `ScheduledFuture<String>`, cho phép lấy kết quả, quan sát/hủy pending task theo hợp đồng. Trong ví dụ ta không hủy vì muốn in kết quả thành công xác định, nhưng việc có handle này là khác biệt thiết kế quan trọng với delayed executor.

**Lưu ý:** `cancel(true)` trên `ScheduledFuture` cũng không phải cam kết mọi side effect đã rollback hoặc mọi task chạy ở native I/O đã dừng ngay; khả năng interrupt/cancel phụ thuộc trạng thái và code task.

## 11. Backoff và retry: delay không thay thế chính sách retry

Một ứng dụng có thể muốn thử lại sau 100 ms khi dịch vụ tạm thời lỗi. Dùng sleep trong mỗi worker:

~~~java
// Đơn giản nhưng giữ worker trong lúc backoff.
try {
    callRemote();
} catch (TransientFailure ex) {
    Thread.sleep(100);
    retry();
}
~~~

Nếu hàng nghìn task cùng đang backoff, pool có thể bị chiếm bởi những thread không làm công việc hữu ích. Với delayed executor, có thể **đưa bước retry thành một stage được lên lịch sau**, không giữ nguyên worker ở vị trí sleep.

### 11.1. Mẫu retry bất đồng bộ một lần

~~~java
// Mẫu Java 17+, không phải chương trình độc lập.
// ioExecutor, first, callRemoteAsync() đã được xác định.
Executor later = CompletableFuture.delayedExecutor(
    200, TimeUnit.MILLISECONDS, ioExecutor);

CompletableFuture<String> recovered =
    first.handle((value, error) -> {
        if (error == null) {
            return CompletableFuture.completedFuture(value);
        }
        return CompletableFuture.supplyAsync(
            () -> callRemote(), later);
    }).thenCompose(next -> next);
~~~

Ý tưởng:

1. Nếu `first` thành công, trả Future đã hoàn tất với cùng giá trị; **không trì hoãn nhánh success**.
2. Nếu `first` thất bại, tạo một Future cho **lần retry** bằng `supplyAsync(..., later)`. Việc submit retry không giữ thread chờ suốt 200 ms.
3. `thenCompose` **làm phẳng** `CompletableFuture<CompletableFuture<String>>` thành một Future kết quả.
4. Lỗi từ retry được phản ánh trong `recovered`, không tự bị biến thành thành công giả.

**Đây là mẫu khái niệm, không phải retry engine production.** Nó chỉ retry một lần và đang retry **mọi lỗi**, kể cả những lỗi không nên retry. Trong sản phẩm, phải phân loại lỗi transient, giới hạn lần thử, có deadline tổng, jitter/backoff, idempotency và cơ chế cancellation của I/O thực tế.

### 11.2. Exponential backoff và jitter

Một chính sách có thể tính:

~~~text
attempt 1 -> delay 100 ms
attempt 2 -> delay 200 ms
attempt 3 -> delay 400 ms
attempt 4 -> delay 800 ms
+ jitter có giới hạn để nhiều client không cùng retry đúng một lúc
~~~

Không nhân đôi số delay vô hạn trong kiểu `long`; cần giới hạn trần, tính số học tránh overflow và giới hạn tổng thời gian. Đừng lặp retry vô hạn mà không có deadline hoặc cancellation token. Retry task có side effect chỉ an toàn khi operation được thiết kế idempotent hoặc có duplicate suppression.

### 11.3. Queue growth và memory pressure

Trì hoãn submission giúp tránh giữ worker **đang ngủ**, nhưng **không loại bỏ trạng thái chờ** trong hệ thống. Nếu mỗi giây có rất nhiều task hẹn sau nhiều phút, vẫn có dữ liệu lịch, callback, Future và closure đang chờ.

Hãy đo số request pending, thời gian chờ, tốc độ enqueue và khả năng base executor xử lý. Delayed executor không tự áp đặt một giới hạn số task đang chờ. Nếu cần backpressure, bạn phải thiết kế queue/capacity hoặc sử dụng scheduler có chính sách rõ ràng.

## 12. Lifecycle: shutdown đúng lúc, tránh mất công việc

Một quy trình phổ biến là:

~~~text
T0: tạo base executor
T1: tạo delayedExecutor(500 ms, base)
T2: gửi CompletableFuture.supplyAsync(..., delayed)
T3: caller muốn shutdown ứng dụng
T4: task chưa tới hạn submit vào base
~~~

Nếu `base.shutdown()` xảy ra ở T3, nó có thể không nhận task vào T4. Điều này khác với việc một task **đã được base nhận** trước shutdown, có thể còn được chạy theo hợp đồng `ExecutorService.shutdown()`.

**Mẫu xử lý theo ứng dụng:**

- Ngừng nhận request mới trước khi đóng pool.
- Theo dõi những deferred task còn là trách nhiệm của ứng dụng.
- Có deadline cho việc chờ hoàn tất các Future quan trọng.
- Nếu deadline hết, ghi nhận tác vụ chưa hoàn tất và có chính sách hủy hoặc phục hồi.
- Chỉ shutdown base executor khi không còn task cần submit vào nó, hoặc đã chấp nhận mất/cancel những task đó.
- Không giả định `CompletableFuture.cancel(true)` lập tức hủy công việc bên ngoài.
- Khi có công việc phải tồn tại qua JVM restart/crash, lưu lịch vào hệ thống bền vững thay vì chỉ dựa vào lịch trong bộ nhớ.

### 12.1. Hạn chế của chính finally trong các ví dụ

Các ví dụ đơn giản dùng `future.join()` trước khi shutdown nên base thường còn sống tới lúc task hoàn tất. Trong production, nếu bạn **không chờ Future nào** mà lại shutdown pool ngay sau khi gửi lịch, đó là một bug lifecycle dễ tạo các Future treo hoặc không hoàn tất theo kỳ vọng.

Cũng không nên giải quyết bằng `Thread.sleep(delay + 100)` ở cuối main; nó chỉ đoán lịch, không xác nhận công việc đã thực thi. Chờ qua Future, latch, task registry hoặc một giao thức shutdown đúng sẽ an toàn hơn.

### 12.2. Tác vụ quan trọng cần lịch bền vững

`delayedExecutor` là cơ chế in-memory JDK; nó không tự ghi task xuống database, không tự restore sau khi process chết và không bảo đảm exactly-once delivery cho nghiệp vụ. Với tác vụ như “gửi hóa đơn sau 24 giờ”, hãy cân nhắc lưu lịch/job vào kho bền vững có ack/retry/idempotency.

Đây là ranh giới kiến trúc chứ không phải thiếu sót cần “vá” bằng thêm một `Thread.sleep` hay thêm worker vào pool.

## 13. Hiệu năng và tính chính xác thời gian

### 13.1. Trễ thực tế gồm nhiều thành phần

Có thể mô tả độ trễ quan sát được:

~~~text
end-to-end latency
  = thời gian trì hoãn đặt lịch
  + sai số scheduling
  + thời gian chờ base executor
  + thời gian thực thi task
  + thời gian callback / publish outcome
~~~

Công thức là mô hình phân tích, không phải cam kết JDK báo riêng từng đại lượng. Nếu base executor đang quá tải, phần queue có thể lớn hơn chính delay bạn đặt.

### 13.2. Cách benchmark phù hợp

- Đo `System.nanoTime()` cho **duration**, không dùng clock tường `currentTimeMillis()` để tính elapsed chính xác.
- Warm up JIT, chạy nhiều lần dưới tải đại diện.
- Đo median, p95/p99 và tỷ lệ task bắt đầu muộn so với thời điểm mong đợi.
- Tách thời gian từ `execute` tới đủ hạn với thời gian queue/base worker bắt đầu; không đổ mọi độ trễ cho timer.
- So sánh cùng pool size và cùng workload nếu muốn đánh giá khác biệt với `ScheduledExecutorService`.
- Với I/O, theo dõi connection usage, timeout, thread pool saturation và pending task count.
- Không khẳng định độ chính xác realtime dựa trên một lần chạy `delay=10 ms`.
- Nếu task cần không được chạy **sớm hơn** deadline nghiệp vụ, xác định contract deadline theo clock monotonic và thời điểm tạo yêu cầu; không dùng một chuỗi sleep đoán thời gian.

### 13.3. Fairness và thứ tự chạy

Hai task có cùng delay không có bảo đảm **thứ tự hoàn tất** giống thứ tự gửi. Task được đưa vào base sau khi đủ hạn, nhưng base có nhiều worker, queue policy và scheduler riêng.

Nếu nghiệp vụ yêu cầu task B chạy **sau khi task A thành công**, tạo dependency bằng `thenCompose`/`thenRun`. Nếu cần thứ tự toàn bộ sự kiện, dùng queue/single-thread executor theo contract phù hợp và phân tích failure; chỉ đặt delay giống nhau không biến các task thành FIFO transaction.

## 14. Sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Tưởng `delayedExecutor(...)` tự bắt đầu task | Nó chỉ tạo Executor; chưa gọi `execute` | Dùng `runAsync/supplyAsync` hoặc `execute` |
| Tưởng delay bắt đầu lúc tạo Executor | Delay bắt đầu theo mỗi `execute` | Gắn mốc thời gian cho mỗi submission |
| Dùng `Thread.sleep` trong caller để lập lịch | Chặn caller, không tạo deferred submission | Dùng delayed executor hoặc scheduler |
| Gọi `join()` ngay rồi tuyên bố không block | `join()` vẫn chờ Future | Trả Future hoặc compose callback |
| Tưởng `delay=0` chạy trên caller | Chỉ là không trì hoãn; base vẫn quyết định | Không dựa vào thread identity ngoài contract |
| Tưởng task bắt đầu đúng T0 + delay | Base có thể bận hoặc queue dài | Đặt SLA, đo delay/queue riêng |
| Dùng `thenApplyAsync(..., delayed)` rồi kỳ vọng delay từ lúc tạo pipeline | Delay bắt đầu khi continuation được submit, thường sau upstream complete | Phân biệt readiness của stage và time delay |
| Gắn delayed executor ở stage A rồi kỳ vọng mọi stage sau cũng bị delay | Mỗi stage có executor/scheduling policy riêng | Chỉ định executor ở từng stage cần delay |
| Dùng delay để thay dependency A → B | Delay không bảo đảm A đã xong | Dùng completion stage dependency |
| Dùng delay để thay timeout | Delay trì hoãn khởi chạy, không giới hạn thời gian | Dùng deadline/`orTimeout`/`get(timeout)` |
| Cho rằng Future cancel nghĩa worker đã ngừng | CompletableFuture.cancel không bắt buộc interrupt | Dùng cancellation protocol riêng |
| Cho rằng runAsync trên delayed luôn chạy sau khi base shutdown | Base có thể reject task | Giữ base sống đúng lifetime, xử lý failure |
| Dùng delayed executor để chạy định kỳ | Chỉ delay mỗi lần execute, không có periodic API | Dùng ScheduledExecutorService |
| Dùng delayed executor như scheduler bền vững qua process restart | In-memory, không persistence | Lưu job/lịch bền vững khi cần |
| Không giới hạn pending delayed tasks | Tài nguyên scheduling/closure/GC có thể tăng | Backpressure và theo dõi pending |
| Dùng executor mặc định cho nhiều I/O chặn lâu | Có thể gây contention/starvation | Chọn base executor phù hợp |
| Catch lỗi Future rồi nuốt | Mất kết quả/quan sát thất bại | Log nguyên nhân, propagate/handle theo hợp đồng |
| Chỉ thêm một `sleep` vào test để chờ đủ delay | Dễ flake trên CI | Dùng latch/Future và timeout xác nhận |
| Gửi delayed task rồi shutdown base ngay | Task có thể chưa tới hạn submit | Quản lý lifecycle bao trùm delay |
| Coi `ScheduledFuture.cancel` là rollback nghiệp vụ | Cancel không đảo ngược side effect đã có | Idempotency và cleanup rõ |

## 15. Kiểm thử đúng, không phụ thuộc timing tuyệt đối

### 15.1. Một kiểm thử tốt kiểm chứng gì?

Với `delayedExecutor`, các kiểm thử nên tập trung vào hợp đồng:

1. **Task được gọi sau khi lập lịch:** cuối cùng Future hoàn tất và trả giá trị.
2. **Base executor được dùng:** tên worker hoặc instrumentation của base chứng minh task chạy trên base đã cấu hình.
3. **Continuation chờ upstream:** downstream chưa chạy trước khi upstream complete.
4. **Một delayed Executor tái sử dụng được:** nhiều task có Future độc lập.
5. **Delay không dương:** task vẫn có thể được thực thi mà không cần đợi delay dương.
6. **Exception được công bố:** lỗi của supplier/continuation xuất hiện trong Future.
7. **Cancellation semantics:** Future có thể cancelled trong khi task đã chạy còn tiếp tục.
8. **Shutdown:** không đóng base trước những delayed task cần thiết, hoặc có chính sách bỏ/cancel rõ.
9. **Timeout:** quan sát outcome khác nhau giữa task chưa tới hạn và Future timeout.
10. **Không rò thread:** base shutdown và chờ kết thúc theo deadline.

### 15.2. Latch chứng minh thứ tự, elapsed time đo độ trễ

`CountDownLatch` giúp sắp xếp các **sự kiện** như task đã bắt đầu, task đã chờ, upstream đã hoàn tất và task đã được phép kết thúc. Nó không thể làm hệ điều hành cam kết một scheduler chính xác tới microsecond.

Khi test thực sự muốn kiểm tra “delay ít nhất khoảng N”, có thể đo `System.nanoTime()` và chọn tolerance phù hợp với CI, nhưng không ép một giá trị stdout thời gian cụ thể cho mọi máy. Cũng không nên làm test chờ hàng giờ chỉ để chứng minh delayedExecutor có delay.

### 15.3. Đừng nhầm CountDownLatch.await() với Thread.sleep()

Trong `DelayedStartDemo`, main gọi `entered.await()` để test sắp đặt trạng thái; đó **là một lời chờ có chủ ý để xác nhận** rằng worker đã vào một điểm. Nó không có nghĩa `delayedExecutor.execute` tự block caller. Sự khác biệt nằm ở **đường API nào gây chờ**.

Với service production, caller thường chỉ giữ `CompletableFuture<T>` hoặc trả nó lên tầng khác; nơi nào thực sự phải chờ có thể quyết định bằng `join`, `get`, timeout hoặc composition.

## 16. Checklist triển khai production

- Có phân biệt thời điểm tạo delayed executor, **gọi execute**, đủ delay, và worker start?
- Delay đang đại diện cho backoff/trì hoãn hợp lý, không dùng thay quan hệ phụ thuộc hay timeout?
- Với I/O chặn lâu, đã chọn base executor phù hợp và giới hạn mức đồng thời chưa?
- Nếu chỉ cần không chặn caller, code có tránh gọi `join/get` ngay sau `supplyAsync` không?
- Đã hiểu mỗi submission trên cùng delayed executor có một delay riêng?
- Với continuation, có hiểu delay chỉ bắt đầu khi stage trước đủ điều kiện kích hoạt continuation?
- Có biết delay 0/âm không đảm bảo chạy inline trên caller?
- Có giới hạn task pending, closure giữ dữ liệu và deadline tổng của request?
- Nếu task failure, có quan sát `CompletableFuture` qua callback/get/join đúng cách?
- Có phân loại transient/permanent failure khi dùng delay cho retry?
- Retry có giới hạn số lần, jitter, idempotency và deadline không?
- Với cancellation, có hiểu `CompletableFuture.cancel(true)` không chắc interrupt worker?
- Có giao thức xác nhận side effect/cleanup nếu tác vụ đã bắt đầu?
- Có tránh shutdown base trước thời điểm delayed task cần submit không?
- Nếu cần lịch định kỳ/cancel timer handle, đã cân nhắc `ScheduledExecutorService`?
- Nếu task phải sống qua crash/restart, đã có lưu lịch bền vững chưa?
- Có test bằng latch/Future thay vì sleep phỏng đoán scheduler?
- Đã kiểm tra timeouts và rejection trên executor đang dùng?
- Có đo queue delay, hold time, p95/p99 và số pending task trong tải đại diện?
- Phần này chỉ dùng cơ chế Java concurrency chuẩn, không lẫn một framework riêng?

## 17. Câu hỏi tự kiểm tra

**1.** Gọi `CompletableFuture.delayedExecutor(500, MILLISECONDS)` có ngay lập tức lên lịch một task nào không?

Không. Nó trả về một `Executor`. Từng delay bắt đầu khi có `execute(runnable)` trên executor đó, ví dụ thông qua `supplyAsync(..., delayed)`.

**2.** Vì sao `supplyAsync(..., delayed).join()` vẫn có thể chặn caller?

Vì `join()` đợi kết quả của Future chưa xong. Việc lên lịch không chặn không có nghĩa caller được miễn chờ khi chính caller chủ động `join`.

**3.** Delay hết nhưng base executor đang bận. Task có chắc chạy ngay không?

Không. Task mới đủ điều kiện được submit; việc worker thực sự chạy còn phụ thuộc queue và năng lực base.

**4.** Dùng lại một delayed executor có làm mọi task chia sẻ cùng một đồng hồ bắt đầu lúc tạo executor không?

Không. Mỗi lần `execute` bắt đầu một khoảng trễ riêng.

**5.** `thenApplyAsync(fn, delayed)` tạo từ upstream chưa hoàn tất. Delay bắt đầu lúc tạo stage không?

Không. Continuation chỉ được submit sau khi upstream hoàn tất bình thường; từ lúc submit mới tính delay cho continuation.

**6.** Delay 0 có bảo đảm function chạy trên thread đang gọi `execute` không?

Không. Nó chỉ bỏ khoảng trễ dương; base executor và scheduler vẫn quyết định cách thực thi.

**7.** Có thể dùng `delayedExecutor` để chạy cron/periodic task không?

Không có API periodic trên `Executor` trả về. Với lịch lặp, dùng `ScheduledExecutorService` hoặc hệ thống scheduler thích hợp.

**8.** `orTimeout` có giống `delayedExecutor` không?

Không. `orTimeout` đặt deadline cho outcome của Future; `delayedExecutor` trì hoãn thời điểm đưa runnable vào base.

**9.** Khi `future.cancel(true)` trả true trên `CompletableFuture`, có chứng minh supplier đã bị interrupt không?

Không. `CompletableFuture.cancel` không dùng `mayInterruptIfRunning` để điều khiển execution theo contract. Supplier đang chạy có thể vẫn làm side effect.

**10.** Có nên shutdown base executor ngay sau khi gửi task delay 10 giây nếu task đó bắt buộc phải chạy không?

Không. Khi delay hết, base có thể đã từ chối task. Lifecycle cần bao trùm cả khoảng chờ và thời gian thực thi.

**11.** Vì sao `Thread.sleep(100)` trước khi bắt đầu B không đảm bảo A đã xong?

Thời gian thực thi A thay đổi theo tải/scheduler/I/O. Nếu B phụ thuộc A, dùng `thenCompose`/`thenRun` chờ completion của A.

**12.** Nếu cần hủy chính xác một timer chưa kích hoạt và có handle theo dõi, lựa chọn nào rõ ràng hơn?

`ScheduledExecutorService.schedule(...)` trả `ScheduledFuture` hỗ trợ `cancel(...)` và kiểm tra trạng thái theo hợp đồng.

**13.** delayedExecutor có tự lưu task qua việc JVM restart không?

Không. Đây là cơ chế in-memory; tác vụ bền vững phải được lưu và phục hồi bởi hệ thống phù hợp.

**14.** Có nên khẳng định task chạy đúng sau 25 ms dựa trên một stdout đo thời gian không?

Không. Scheduler và queue có thể làm lệch thời gian; dùng đo duration nhiều lần, tolerance hợp lý, và tách delay scheduling khỏi queue wait.

## 18. Tài liệu JDK và kết luận

Các tài liệu chính thức để kiểm tra mốc phiên bản và hợp đồng API:

- [CompletableFuture — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Executor — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html)
- [ScheduledExecutorService — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledExecutorService.html)
- [ScheduledFuture — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ScheduledFuture.html)

`CompletableFuture.delayedExecutor` có từ **Java 9**. Javadoc nêu rõ: delay được áp dụng trước khi submit runnable vào default/base executor; **mỗi khoảng delay bắt đầu khi gọi `execute`** trên executor trả về. Do đó API thuận tiện để xây dựng những bước trì hoãn và continuation bất đồng bộ mà không bắt caller dùng `Thread.sleep`.

### Bảng ghi nhớ

~~~text
delayedExecutor(delay, unit, base):
  Trả Executor, KHÔNG tự chạy task.
  execute(task) -> bắt đầu tính delay của riêng task.
  Hết delay -> gửi task tới base executor.
  Base executor -> quyết định worker, queue, thời điểm chạy.

runAsync/supplyAsync(..., delayed):
  Lên lịch không cần caller sleep.
  Trả CompletableFuture để quan sát outcome.

thenApplyAsync(..., delayed):
  Upstream complete -> submit continuation -> bắt đầu delay riêng.

join()/get():
  VẪN có thể chặn thread caller khi Future chưa hoàn tất.

cancel(true) trên CompletableFuture:
  Không bảo đảm interrupt user code đang chạy.

ScheduledExecutorService:
  Phù hợp khi cần ScheduledFuture và các lịch định kỳ.
~~~

**Kết luận:** `delayedExecutor()` giải quyết việc **trì hoãn submission**, không chiếm một thread caller chỉ để ngủ. Nhưng nó không bảo đảm deadline realtime, không biến I/O blocking thành non-blocking, không tự bảo vệ lifecycle executor và không cung cấp cancellation/persistence của một scheduler chuyên dụng. Hãy chọn base executor phù hợp, compose Future theo dependency thực, có deadline và quan sát lỗi, đồng thời tách rõ scheduling khỏi kết thúc công việc.