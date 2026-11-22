# AsyncTaskExecutor và các phương thức submit()

> **Chủ đề:** Spring Framework – concurrency  
> **Nhóm kiến thức:** TaskExecutor  
> **Mục tiêu:** Hiểu hợp đồng của `AsyncTaskExecutor`, lựa chọn đúng giữa `execute()`, `submit(Runnable)` và `submit(Callable<T>)`, theo dõi kết quả qua `Future`, quản lý lỗi, hủy, timeout và tài nguyên khi dùng executor trong ứng dụng Spring.

## 1. AsyncTaskExecutor nằm ở đâu trong hệ sinh thái executor?

Java có `java.util.concurrent.Executor` với phương thức `execute(Runnable)`; Spring khai báo `org.springframework.core.task.TaskExecutor` như một abstraction tương thích `Executor`. Hợp đồng chung của `TaskExecutor` cho phép nhiều cách thực thi, kể cả đồng bộ trên caller thread (ví dụ `SyncTaskExecutor`).

`org.springframework.core.task.AsyncTaskExecutor` **mở rộng `TaskExecutor`**, bổ sung khả năng nộp tác vụ và nhận `Future` hoặc `CompletableFuture` để quan sát kết quả. Theo hợp đồng interface, `execute(Runnable)` của một `AsyncTaskExecutor` thực thi tác vụ **bất đồng bộ trên luồng khác caller**, thay vì chạy `Runnable` ngay trên caller thread. Tuy vậy, **lệnh nộp task** có thể phải đợi theo chính sách giới hạn concurrency của implementation hoặc bị từ chối khi executor quá tải; không được khẳng định mọi lệnh `submit` đều trả về ngay lập tức.

~~~text
java.util.concurrent.Executor
            ^
            |
      Spring TaskExecutor
         |         |
         |         +-- SyncTaskExecutor (TaskExecutor đồng bộ)
         |
         +-- AsyncTaskExecutor
                   |
                   +-- SimpleAsyncTaskExecutor
                   +-- ThreadPoolTaskExecutor
                   +-- ConcurrentTaskExecutor / TaskExecutorAdapter
                   +-- các implementation khác
~~~

Lưu ý: Sơ đồ diễn đạt **quan hệ interface và ví dụ implementation**, không biểu diễn đầy đủ cây kế thừa Java giữa mọi class.

`AsyncTaskExecutor` **không phải là** `ExecutorService`. Dù cùng có hai overload `submit`, interface Spring không có các phương thức `invokeAll()`, `invokeAny()`, `shutdown()` hay overload `submit(Runnable, T result)` của JDK `ExecutorService`. Việc quản lý vòng đời thường do Spring bean và implementation cụ thể thực hiện.

## 2. Các phương thức cốt lõi: execute hay submit?

| Lời gọi | Kiểu đầu vào | Kiểu trả về | Ý nghĩa |
| --- | --- | --- | --- |
| `execute(Runnable)` kế thừa `TaskExecutor` | Công việc không khai báo giá trị trả về | `void` | Chỉ yêu cầu thực thi, không có `Future` từ lời gọi này để đợi/thu hồi lỗi |
| `submit(Runnable)` | `Runnable` với `void run()` | `Future<?>` | Nhận handle theo dõi việc hoàn tất; `get()` trả **null** nếu thành công |
| `submit(Callable<T>)` | `Callable<T>` với `T call()` | `Future<T>` | Nhận handle theo dõi việc hoàn tất và lấy chính giá trị do `call()` trả về |
| `submitCompletable(Runnable)` | `Runnable` | `CompletableFuture<Void>` | Được bổ sung từ Spring Framework **6.0**; thuận tiện ghép các bước xử lý |
| `submitCompletable(Callable<T>)` | `Callable<T>` | `CompletableFuture<T>` | Được bổ sung từ Spring Framework **6.0**; nhận giá trị và composition API |

Hai overload `submit` tồn tại từ lâu trong Spring; từ **Spring Framework 6.1**, interface có default implementation, về mặt ý tưởng sử dụng task thích hợp rồi chuyển đến `TaskExecutor.execute(Runnable)`. Implementation vẫn có thể override cách nộp; `ThreadPoolTaskExecutor` có các override riêng. Đừng dựa vào một loại `Future` implementation cụ thể trong mã nghiệp vụ.

Chữ “async” ở đây mô tả **mô hình thực thi**. Còn `Future` là **đại diện cho kết quả/trạng thái trong tương lai**. `submit` thành công chỉ chứng minh executor **chấp nhận** task, chưa khẳng định task bắt đầu, hoàn thành, hay thành công nghiệp vụ.

### 2.1. submit(Runnable): thực thi công việc, không nhận giá trị từ run()

~~~java
Future<?> future = executor.submit(() -> {
    auditWriter.writeEntry("user-42", "LOGIN"); // minh họa một dependency của ứng dụng
});

// Chờ đến khi Runnable hoàn tất hoặc báo lỗi:
Object result = future.get(); // null nếu Runnable thành công
~~~

Đây là **đoạn ghép vào ứng dụng** đã có biến `executor` kiểu `AsyncTaskExecutor` và `auditWriter`; không phải chương trình biên dịch độc lập. Dùng `Runnable` khi tác vụ thực hiện một hành động và caller chỉ cần trạng thái hoàn tất. Sau khi `get()` trả về bình thường, `result == null` là đúng; không có dữ liệu trả về từ `void run()`.

### 2.2. submit(Callable<T>): nhận kết quả có kiểu

~~~java
Future<Integer> totalFuture = executor.submit(() -> {
    return 10 + 20;
});

int total = totalFuture.get(); // 30
~~~

`Callable<T>` có thể trả `T` và khai báo `throws Exception`. Kiểu `T` được suy luận từ lambda/assignment; `Future<Integer>` giúp compiler kiểm tra kiểu. Khi muốn trả giá trị (tổng hợp thống kê, đọc dữ liệu, tính điểm), đây là overload cần chọn.

**Lỗi overload lambda thường gặp:** một expression lambda như `() -> counter.incrementAndGet()` có thể tương thích với cả `Runnable` và `Callable<Integer>`, gây khó hiểu hoặc lỗi overload. Khi mục đích là `Runnable`, viết block không trả giá trị `() -> { counter.incrementAndGet(); }`, hoặc ép kiểu `(Runnable)` tường minh.

### 2.3. execute(Runnable) khác submit(Runnable) ở đường quan sát lỗi

~~~java
executor.execute(() -> doWork());      // không có Future từ execute()
Future<?> future = executor.submit(() -> doWork()); // có handle
~~~

Với `submit`, failure xảy ra **bên trong task** thường được bắt giữ trong `Future`. Nếu không bao giờ quan sát `Future.get()` hoặc một cơ chế theo dõi khác, lỗi có thể bị bỏ sót. Với `execute`, cách báo/ghi log uncaught exception phụ thuộc implementation, thread và error handling. Cả hai đều có thể ném exception **ngay tại thời điểm nộp**, chẳng hạn `TaskRejectedException`.

## 3. Vòng đời của một Future

Hình dung `Future` như biên nhận của một task:

~~~text
Caller                       AsyncTaskExecutor                 Worker thread
  | submit(Runnable/Callable)       |                                |
  |------------------------------->| kiểm tra pool / queue           |
  |                                | có thể ACCEPT hoặc REJECT       |
  |<----- Future (nếu accept) ------|                                |
  |                                |------------ chạy task -------->|
  | làm việc khác                  |                                |
  | future.get()                   |                       tính toán / lỗi
  | ... có thể phải chờ ...        |                                |
  |<------------------------- kết quả / lỗi / bị hủy <---------------|
~~~

Các API JDK `Future` cần hiểu:

- `get()`: **chờ** task hoàn tất và lấy kết quả. Nếu task thất bại, ném `ExecutionException` với `getCause()` là lỗi gốc. Nếu task bị hủy, ném `CancellationException` (unchecked). Nếu thread đang đợi bị interrupt, ném `InterruptedException`.
- `get(timeout, unit)`: chờ **tối đa** thời gian chỉ định. Ném `TimeoutException` khi **hết thời gian chờ**, không mặc định hủy task đang chạy. Muốn hủy, cần quyết định gọi `cancel(...)` và chấp nhận tính best effort.
- `isDone()`: `true` khi Future đã kết thúc theo một cách nào đó: **thành công, lỗi hoặc bị hủy**. Nó **không đồng nghĩa với thành công**.
- `isCancelled()`: đánh dấu task đã bị cancel theo hợp đồng Future.
- `cancel(false)`: yêu cầu hủy; task đã chạy thường được phép tiếp tục mà không bị yêu cầu interrupt.
- `cancel(true)`: yêu cầu interrupt nếu task đang chạy và implementation biết worker thread. **Không bảo đảm** dừng tức thì, rollback database, thu hồi email đã gửi hay chấm dứt mọi I/O.
- **Memory visibility:** theo hợp đồng `Future` của JDK, hành động trong task *happens-before* những hành động theo sau lời gọi `Future.get()` tương ứng ở thread khác. Điều này giải thích vì sao có thể đọc một kết quả đã được task cập nhật sau khi chờ `get()`; nó không biến mọi shared mutable state của hệ thống thành thread-safe.

Một task có thể chạy và kết thúc trước khi caller nhận được reference `Future`; đó là bình thường. Tương tự, một `Future` chưa hoàn tất không cho biết chính xác nó đang ở queue hay đang chạy nếu implementation không cung cấp thêm metric.

## 4. Ví dụ Spring Framework 6.2.x, Java 17+: hai overload submit() chạy được

Ví dụ tạo `ThreadPoolTaskExecutor` dưới dạng Spring bean, lấy qua **interface `AsyncTaskExecutor`** và nộp ba task: một `Runnable`, một `Callable<Integer>`, một `Callable<Integer>` phát lỗi để quan sát cơ chế `ExecutionException`. Không dùng `@Async`, vì nộp task **trực tiếp** cho executor; không cần bật `@EnableAsync`.

Tạo project Maven:

~~~text
spring-submit-demo/
├── pom.xml
└── src/main/java/demo/SubmitDemo.java
~~~

**pom.xml** (chọn Spring Framework 6.2.9 để ví dụ có phiên bản xác định; yêu cầu JDK 17+ và Maven):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-submit-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/SubmitDemo.java**

~~~java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class SubmitDemo {

    @Bean
    public ThreadPoolTaskExecutor workerExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(2);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("lesson-");
        return pool;
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(SubmitDemo.class)) {

            AsyncTaskExecutor executor =
                context.getBean(AsyncTaskExecutor.class);
            AtomicInteger counter = new AtomicInteger();

            // Block void: compiler chọn submit(Runnable).
            Future<?> action = executor.submit(() -> {
                counter.incrementAndGet();
            });

            // Expression trả số: compiler chọn submit(Callable<Integer>).
            Future<Integer> calculation = executor.submit(() -> 7 * 6);

            // Bắt lỗi từ một Callable đã được chấp nhận.
            Future<Integer> failure = executor.submit(
                (Callable<Integer>) () -> {
                    throw new IllegalStateException("simulated failure");
                }
            );

            System.out.println("Runnable result = " + action.get());
            System.out.println("Counter = " + counter.get());
            System.out.println("Callable result = " + calculation.get());
            System.out.println("Callable done = " + calculation.isDone());

            try {
                failure.get();
            } catch (ExecutionException ex) {
                System.out.println("Cause = " + ex.getCause().getMessage());
            }
        }
    }
}
~~~

Chạy từ thư mục `spring-submit-demo`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.SubmitDemo
~~~

Các dòng **do chương trình tự in ra**, có thứ tự và giá trị xác định:

~~~text
Runnable result = null
Counter = 1
Callable result = 42
Callable done = true
Cause = simulated failure
~~~

Giải thích tính xác định:

1. `action.get()` đợi `Runnable` hoàn tất; Runnable không trả giá trị nên in `null`. Cập nhật `AtomicInteger` đã hoàn tất trước khi in `Counter = 1`.
2. `calculation.get()` đợi `Callable<Integer>` và nhận `42`. Sau `get()`, `isDone()` chắc chắn là `true`.
3. `failure.get()` ném `ExecutionException`; `getCause()` là `IllegalStateException` có thông điệp đã xác định. Future này không gây chương trình dừng đột ngột vì được catch.
4. Hai worker có thể thực thi ba task ở các thứ tự khác nhau, nhưng vì caller tự đợi rồi in theo trình tự, **nội dung và thứ tự output vẫn giữ nguyên**.
5. Đóng `AnnotationConfigApplicationContext` qua try-with-resources kết thúc bean lifecycle; `ThreadPoolTaskExecutor` là bean Spring được quản lý và có cơ chế shutdown. Sản phẩm thực tế vẫn phải cấu hình chính sách hoàn tất task đang chờ khi shutdown.

Đây là ví dụ nhỏ về **cách gọi và Future semantics**, không phải bảo đảm cho retry, giao dịch, tác vụ sống qua restart hay toàn bộ nghiệp vụ phân tán.

## 5. Xử lý lỗi đúng ở hai thời điểm khác nhau

**Thời điểm nộp task:**

~~~java
Future<String> future;
try {
    future = executor.submit(() -> externalClient.fetchResult());
} catch (org.springframework.core.task.TaskRejectedException ex) {
    // Pool đóng hoặc quá tải: chưa có Future để theo dõi.
    throw ex;
}
~~~

Đây là **đoạn tích hợp minh họa**, cần các biến `executor` và `externalClient` trong ứng dụng. Nếu caller cần chống lệ thuộc Spring exception, `TaskRejectedException` cũng là một `RejectedExecutionException` theo API hiện đại.

**Sau khi task được chấp nhận:**

~~~java
try {
    String result = future.get(2, java.util.concurrent.TimeUnit.SECONDS);
    processResult(result);
} catch (java.util.concurrent.TimeoutException ex) {
    // Hết thời gian CHỜ, task không tự bị hủy.
    future.cancel(true);  // Best effort; cân nhắc side effect.
} catch (java.util.concurrent.ExecutionException ex) {
    Throwable originalFailure = ex.getCause();
    recordTaskFailure(originalFailure);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw ex;
} catch (java.util.concurrent.CancellationException ex) {
    recordCancellation(ex);
}
~~~

Đây cũng là **đoạn ghép vào ứng dụng**, đặt trong phương thức khai báo `throws InterruptedException` hoặc xử lý lại lỗi, và có các hàm `processResult`, `recordTaskFailure`, `recordCancellation` của nghiệp vụ. Điểm cốt lõi: phân biệt **TaskRejectedException ở submit()** với **ExecutionException ở get()**, và **TimeoutException khi caller chờ quá lâu**. Không chọn timeout/retry tuỳ tiện: cần kiểm soát tác dụng phụ đã chạy và đảm bảo idempotency.

| Hiện tượng | Xảy ra ở đâu | Hành động nên cân nhắc |
| --- | --- | --- |
| `TaskRejectedException` | `submit`/nộp task | Giới hạn tải, phản hồi backpressure, queue bền vững, ghi nhận reject; thường không có Future |
| `ExecutionException` | `Future.get()` | Kiểm tra `getCause()`, phân loại lỗi, retry có kiểm soát nếu idempotent |
| `InterruptedException` | Thread caller đang chờ `get()` | Khôi phục interrupt flag và hủy/thoát theo contract của caller |
| `TimeoutException` | `get(timeout)` | Đánh giá timeout, trả kết quả tạm, có thể yêu cầu cancel; task chưa chắc ngừng |
| `CancellationException` | `get()` trên Future đã cancel | Phân biệt chủ động hủy với lỗi xử lý |
| `isDone() == true` | Kiểm tra trạng thái | Chỉ nói “đã kết thúc”; cần `get()` để biết thành công/thất bại |

**Lưu ý vận hành:** `Future.get()` chặn **thread đang gọi**, không phải chuyển việc chờ sang Spring. Nếu gọi `get()` ngay sau `submit()` trong HTTP handler, bạn đã dùng executor để chạy tác vụ nhưng vẫn giữ request thread đợi; đôi khi cần, nhưng không phải một pipeline bất đồng bộ end-to-end.

## 6. Hủy và interrupt có ý nghĩa giới hạn

`future.cancel(false)` cố hủy công việc chưa bắt đầu hoặc đánh dấu cancel mà không yêu cầu ngắt thread đang chạy. `future.cancel(true)` có thể gửi interrupt đến worker. Cả hai là yêu cầu điều khiển **Future/task**, không phải transaction rollback hay “undo”.

Một tác vụ phản hồi interrupt đúng cách:

~~~java
Future<?> task = executor.submit(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            performOneBoundedUnitOfWork();
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    } finally {
        releaseResources();
    }
});

// Khi nghiệp vụ chủ động quyết định dừng:
task.cancel(true);
~~~

Đoạn này minh họa **mẫu kiểm soát vòng đời**, các hàm `performOneBoundedUnitOfWork()` và `releaseResources()` thuộc mã ứng dụng. Ví dụ giả định một đơn vị công việc có thể ném `InterruptedException`, hoàn tất trong giới hạn và được viết an toàn khi thử lại. Nếu underlying API không đáp ứng interrupt, task có thể tiếp tục chạy dù Future đã ở trạng thái cancelled. Cần timeout riêng cho HTTP/database và phương án xử lý tác dụng phụ một phần.

**Không dùng `isDone()` hay `cancel(true)` như cơ chế xác nhận rằng việc ghi DB, gửi email hoặc thanh toán đã được hoàn tác.** Với các công việc quan trọng, trạng thái cuối cùng phải được lưu/kiểm chứng ở hệ thống sở hữu dữ liệu.

## 7. submitCompletable(): lựa chọn cho chuỗi xử lý không chặn

Spring Framework 6.0+ thêm:

~~~java
CompletableFuture<Integer> total = executor.submitCompletable(() -> {
    return expensiveCalculation();
});

CompletableFuture<String> display =
    total.thenApply(value -> "total=" + value)
         .exceptionally(error -> "unavailable");

display.thenAccept(System.out::println);
~~~

Đoạn trên là **mã minh họa tích hợp**, giả định đã có `executor` và `expensiveCalculation()`. `CompletableFuture` cho phép nối `thenApply`, `thenCompose`, `whenComplete`, `exceptionally` và phối hợp nhiều tác vụ mà không cần caller gọi `get()` ngay. `submitCompletable(Runnable)` trả `CompletableFuture<Void>`, hoàn thành bình thường với `null`.

Tuy nhiên, **continuation cũng cần chọn nơi chạy**:

- `thenApply(...)` không có hậu tố `Async` có thể chạy trên thread hoàn tất future hoặc thread gọi thao tác, tùy trạng thái completion.
- `thenApplyAsync(...)` nếu không truyền executor dùng asynchronous facility mặc định của `CompletableFuture` (thường là `ForkJoinPool.commonPool()`), không mặc định quay về pool Spring đã dùng.
- Nếu muốn quy định tài nguyên, dùng `thenApplyAsync(function, executor)` với `AsyncTaskExecutor` đang sở hữu và giới hạn tải.
- `join()` cũng là lời gọi chặn nếu chưa hoàn tất; failure được bọc bằng `CompletionException`. `get()` dùng `ExecutionException`. Việc dùng `CompletableFuture` không tự đảm bảo timeout, idempotency hay transaction context.

`submitCompletable` giúp biểu diễn pipeline tốt hơn `Future` đơn thuần; khi chỉ cần chờ một tác vụ đơn lẻ, `submit(Runnable/Callable)` vẫn là lựa chọn phù hợp.

## 8. Chọn implementation của AsyncTaskExecutor

| Implementation | Đặc điểm | Cần lưu ý |
| --- | --- | --- |
| `ThreadPoolTaskExecutor` | Adapter kiểu Spring cho `ThreadPoolExecutor`; có core/max pool size, queue capacity, thread prefix, metric như active count/queue size | Cần chọn giới hạn và rejection policy; bean lifecycle và shutdown khác nhau theo cấu hình |
| `SimpleAsyncTaskExecutor` | Tạo thread mới cho mỗi task, **không tái sử dụng thread kiểu pool**; có thể giới hạn concurrency | Không dùng như pool vô hạn; trong môi trường JDK 21+ có thể bật virtual threads theo cấu hình |
| `ConcurrentTaskExecutor` | Adapter cho một `java.util.concurrent.Executor` hiện có | Hành vi scheduling/queue/reject đến từ executor được delegate; chọn adapter khi có executor tùy chỉnh |
| `TaskExecutorAdapter` | Adapter Spring cho executor gốc của JDK | Cần hiểu resource ownership, exception translation và semantics của delegate |
| `SyncTaskExecutor` | Thực thi trực tiếp trên caller thread | **Chỉ triển khai `TaskExecutor`**, không thỏa contract async của `AsyncTaskExecutor` |

Ví dụ cấu hình pool giới hạn qua Spring:

~~~java
@Bean("ioExecutor")
ThreadPoolTaskExecutor ioExecutor() {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(4);
    pool.setMaxPoolSize(8);
    pool.setQueueCapacity(100);
    pool.setThreadNamePrefix("io-");
    pool.setRejectedExecutionHandler(
        new java.util.concurrent.ThreadPoolExecutor.AbortPolicy()
    );
    return pool;
}
~~~

Đây là **đoạn @Bean minh họa**, cần đặt trong `@Configuration` và import các kiểu Spring tương ứng. Số 4/8/100 chỉ minh họa, không phải cấu hình phù hợp mọi hệ thống. Với `ThreadPoolTaskExecutor`, queue có capacity dương thường khiến task xếp hàng trước khi tăng worker vượt `corePoolSize`; khi queue đã đầy mới xét mở rộng đến `maxPoolSize`. Vì vậy chỉ tăng `maxPoolSize` nhưng giữ queue rất lớn có thể không làm tăng concurrency như mong đợi.

Lưu ý `ThreadPoolTaskExecutor` mặc định có core size 1 và queue capacity rất lớn; **không** dùng mặc định này như lựa chọn sản phẩm mà chưa đo tải. Khi pool/queue đều hết sức chứa, tác vụ có thể bị từ chối. Nếu dùng policy chạy trên caller thread thay vì abort, thời gian `submit` có thể tăng và caller phải tự quản lý backpressure.

## 9. Chọn đúng abstraction: manual submit, @Async, ExecutorService

| Tình huống | Cách chọn |
| --- | --- |
| Cần chủ động gửi một `Runnable`, nhận `Future` để đợi/hủy | Inject `AsyncTaskExecutor` rồi `submit(Runnable)` |
| Tác vụ trả về `T` | `submit(Callable<T>)` |
| Cần xử lý nhiều giai đoạn/ghép future | `submitCompletable(...)` và continuation có executor rõ ràng |
| Muốn lời gọi phương thức bean được interceptor thực thi async | `@EnableAsync` + `@Async`, gọi qua Spring proxy |
| Cần `invokeAll`, `invokeAny` hoặc shutdown trực tiếp trên một raw Java pool | Sở hữu/inject `ExecutorService` theo contract JDK; không ép interface Spring cung cấp API không có |
| Chỉ cần thực thi fire-and-forget và đã có giám sát lỗi riêng | `execute(Runnable)` có thể đủ, nhưng không nhận Future |

**Manual `submit` không đòi hỏi Spring proxy:** một service có thể gọi `executor.submit(...)` dù đang trong chính instance đó; đây là API trực tiếp của executor. Trái lại, `@Async` dựa vào interceptor trong chế độ proxy mặc định; `this.someAsyncMethod()` thường bỏ qua proxy nên không được điều phối async.

**Không đánh đồng `Future` của manual submit với return type của `@Async` method.** Với `@Async`, proxy là bên điều phối lời gọi và trả future cho caller; cách khai báo return type, propagation và error handling phải theo tài liệu annotation. Bài này tập trung vào `AsyncTaskExecutor.submit`.

## 10. Những trách nhiệm không do submit tự làm

### 10.1. Thread safety và dữ liệu đầu vào

Hai task đồng thời có thể dùng cùng reference đến collection, entity hay bean singleton. `submit` không sao chép, không đóng băng dữ liệu đầu vào và không biến `HashMap` thành thread-safe. Ưu tiên command immutable, biến local, cấu trúc concurrent phù hợp và cơ chế đồng bộ có phạm vi rõ.

### 10.2. ThreadLocal, security và logging

Caller thường có context như MDC, request attributes, principal, transaction resources. Executor thread không tự được bảo đảm có toàn bộ các context này; nếu cần, chọn `TaskDecorator` hoặc security-aware/context propagation adapter tương ứng và dọn context trong `finally`. Không truyền request object sống sang task chạy sau request.

**Điểm khó với TaskDecorator:** ở các lời gọi `submit` của `ThreadPoolTaskExecutor`, wrapper nhận được có thể là `FutureTask` đã bắt exception của công việc gốc. `try/catch` quanh `runnable.run()` ở decorator có thể không thấy lỗi nghiệp vụ; cần theo dõi `Future.get()` hoặc thiết kế quan sát kết quả khác.

### 10.3. Transaction và request boundary

Trong ứng dụng imperative, transaction Spring thường gắn với thread hiện tại. Nộp việc qua `submit` **không chuyển transaction của caller sang thread worker**. Nếu cần ghi DB trong task, mở transaction phù hợp ngay tại worker, ví dụ gọi một `@Transactional` service bean qua Spring proxy hoặc dùng `TransactionTemplate`. Worker có thể chạy trước khi giao dịch caller commit, nên không nên cho task đọc dữ liệu vừa ghi nhưng chưa commit hoặc phát sự kiện ngoại vi theo giả định commit thành công.

### 10.4. Reliability và idempotency

`submit` đưa task vào executor trong **process đang sống**. Nếu JVM bị kill sau khi task được nhận nhưng trước khi xử lý xong, `Future` không phải durable job record. Khi nghiệp vụ cần chạy lại sau restart hoặc chống duplicate, lưu command/sự kiện ở cơ sở dữ liệu hoặc durable queue, thiết kế idempotency key, retry/backoff và trạng thái hoàn tất.

## 11. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “`submit` trả Future nên chắc chắn task thành công” | Future có thể đang chờ, fail hoặc cancel | Quan sát `get`, callback/completion hoặc metric |
| “`future.isDone()` bằng true tức là đã thành công” | Exception và cancellation cũng kết thúc Future | Kiểm tra lỗi/hủy rồi mới công nhận thành công |
| Gọi `get()` ngay sau từng `submit` trong vòng lặp | Vô tình tuần tự hóa phần chờ, giảm concurrency | Nộp các tác vụ trước, gom Future, rồi đợi/aggregate có deadline |
| Bỏ `Future` của `submit` không quan sát | Exception trong Future có thể bị lặng | Bảo đảm có owner theo dõi kết quả/lỗi |
| Gọi `future.get(1, SECONDS)` rồi tin task đã dừng khi timeout | Timeout chỉ giới hạn thời gian đợi | Chính sách cancel riêng và deadline ở tầng I/O |
| Dùng `cancel(true)` như rollback | Interrupt không hoàn tác tác dụng phụ đã xảy ra | Transaction/compensation, idempotency, checkpoint |
| Catch mỗi `ExecutionException` quanh lời gọi `submit` | Task rejection xảy ra khi nộp, không nằm trong Future | Catch `TaskRejectedException` quanh submit |
| Trộn `AsyncTaskExecutor` với `ExecutorService` | Không cùng API đầy đủ | Chọn interface đúng nhu cầu |
| Trông chờ `@Async`/transaction/request context tự truyền | Thread và proxy boundary độc lập | Context propagation tường minh; transaction riêng |
| Dùng pool/queue không giới hạn để “không bị reject” | Tăng latency/bộ nhớ và có thể OOM | Bounded queue, rejection policy, backpressure và metric |

## 12. Cách kiểm thử một đường submit()

1. **Trạng thái:** kiểm tra `submit(Runnable)` cho `null`, `submit(Callable<T>)` cho đúng `T` và `Future.get()` đợi hoàn tất.
2. **Exception:** nộp task ném một exception xác định; assert `get()` ném `ExecutionException` có `getCause()` đúng loại. Tránh test chỉ dựa vào log worker.
3. **Timeout/cancel:** dùng `CountDownLatch`/barrier kiểm soát task đang chờ rồi đo `get(timeout)`, `cancel(true)`, `isCancelled`; hạn chế phụ thuộc `Thread.sleep` cố định.
4. **Rejection:** cấu hình pool và queue nhỏ, chặn worker bằng latch, nộp vượt capacity; assert chính sách từ chối và đường xử lý của caller.
5. **Concurrency:** đo số luồng chạy đồng thời, xác minh giới hạn tải, kiểm thử shared mutable state trong bean.
6. **Lifecycle:** đóng ApplicationContext khi có task đang chạy/chờ; kiểm tra policy shutdown và việc không để mất dữ liệu nghiệp vụ quan trọng.
7. **Observability:** log taskId/correlationId hợp lệ; theo dõi queue depth, active count, task duration, failure/rejection và timeout.

## 13. Checklist sử dụng đúng

- Tôi biết biến `executor` có đúng kiểu `AsyncTaskExecutor` hay chỉ là `TaskExecutor`.
- Tôi chọn `Runnable` khi không cần giá trị; `Callable<T>` khi cần kết quả.
- Tôi phân biệt `submit` được nhận, `Future` đã hoàn tất và nghiệp vụ đã thành công.
- Tôi có người chịu trách nhiệm quan sát `Future` và xử lý task exception.
- Tôi phân biệt lỗi reject ở **submit** với lỗi xử lý ở **get**.
- Tôi xử lý interrupt, timeout, cancel mà không suy diễn rollback tự động.
- Tôi cấu hình giới hạn executor, queue, overload/rejection và shutdown theo tải thật.
- Tôi không trông chờ tự truyền transaction, request hoặc security context sang worker.
- Tôi dùng durable queue/outbox/idempotency nếu công việc phải phục hồi khi process chết.

**Kết luận:** `AsyncTaskExecutor` mở rộng khả năng thực thi task của Spring để nhận **`Future` quan sát kết quả bất đồng bộ**. `submit(Runnable)` theo dõi hoàn tất và có kết quả `null`; `submit(Callable<T>)` trả giá trị kiểu `T`. Điều đúng của hệ thống còn phụ thuộc cấu hình executor, chính sách lỗi, ranh giới trạng thái/giao dịch và thiết kế nghiệp vụ.

## Tài liệu tham khảo

- Spring Framework Javadoc – AsyncTaskExecutor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html
- Spring Framework Javadoc – TaskExecutor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/task/TaskExecutor.html
- Spring Framework Javadoc – ThreadPoolTaskExecutor: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
- Spring Framework Reference – Task Execution and Scheduling: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Java SE 17 Javadoc – Future: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 Javadoc – ExecutorService: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html