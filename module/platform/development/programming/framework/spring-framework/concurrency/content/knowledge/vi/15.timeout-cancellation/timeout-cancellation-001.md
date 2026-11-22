# Phân biệt thời gian chờ trong hàng đợi, thời gian chạy và thời gian bên gọi chờ

## 1. Bài toán: cùng một task nhưng ba loại độ trễ

Khi một ứng dụng Spring gửi `Runnable` hoặc `Callable<T>` vào `ThreadPoolTaskExecutor`, công việc có thể chưa bắt đầu ngay: worker đang bận, task phải nằm trong hàng đợi, rồi mới được chạy. Trong khi đó, thread gọi có thể xử lý việc khác, chờ kết quả bằng `Future.get()` hoặc đã trả response HTTP.

Vì thế phải phân biệt **ba khoảng thời gian**:

1. **Thời gian chờ trong hàng đợi (queue wait, submit-to-start)**: từ lúc task được gửi/chấp nhận đến khi worker bắt đầu chạy. Khoảng submit-to-start đo được thường có thêm chút overhead của việc gửi/dispatch, không nhất thiết toàn bộ là thời gian nằm vật lý trong `BlockingQueue`.
2. **Thời gian chạy (execution time, runtime)**: từ khi worker bắt đầu phần việc được đo đến khi phần việc kết thúc. Đây là elapsed wall-clock time; có thể gồm cả CPU, JDBC/HTTP I/O, chờ lock, sleep hoặc pause do scheduler.
3. **Thời gian bên gọi chờ (caller wait time)**: khoảng thread gọi bị chặn trong một lời gọi lấy kết quả, ví dụ `Future.get()`, `get(timeout, unit)` hoặc `CompletableFuture.join()`. Caller có thể chờ ngay, chờ muộn, chờ nhiều lần hoặc không chờ lần nào.

**Điểm cốt lõi:** hai loại đầu đo vòng đời của **task**, loại thứ ba đo hành vi của **caller**. Không nên cộng cả ba lại để tìm tổng thời gian hoàn tất tác vụ, vì caller wait thường chồng lên queue wait/runtime.

Một task có thể chờ trong queue 300 ms, chạy 200 ms, nhưng caller lấy kết quả sau 600 ms nên `get()` trả gần như ngay lập tức. Ngược lại, caller có thể timeout sau 100 ms dù task còn chưa bắt đầu chạy và sau đó vẫn hoàn tất bình thường.

## 2. Timeline và công thức đo chính xác

Đặt các timestamp trên cùng đồng hồ đơn điệu của JVM:

- `t0`: thời điểm gần nhất quán với việc submit task.
- `t1`: worker bắt đầu thực hiện task.
- `t2`: task body kết thúc thành công hoặc thất bại.
- `t3`: caller bắt đầu một lần gọi `get()` để chờ kết quả.
- `t4`: lời gọi `get()` đó kết thúc, bằng kết quả, lỗi, timeout hoặc interruption.

```text
Task lifecycle:
t0 submit                 t1 worker begins              t2 task finishes
|--------------------------|-----------------------------|
          queue wait               execution time

Caller thread (independent interval):
                     t3 get() begins          t4 get() returns/throws
                     |------------------------|
                            caller wait
```

Nếu timestamp đặt ở những ranh giới thống nhất:

```text
queueWaitNanos      ≈ t1 - t0
executionNanos       = t2 - t1
submitToFinishNanos ≈ t2 - t0
oneCallerWaitNanos   = t4 - t3

submitToFinish ≈ queueWait + execution
callerWait KHÔNG phải một số hạng cộng thêm vào tổng phía trên.
```

Dấu xấp xỉ nhắc rằng `t0` có thể được ghi ngay trước lệnh `submit()` và vì thế bao gồm chi phí dispatch; `t2` có thể được ghi trước một khoảng nhỏ để Future hoàn tất/đăng kết quả. Để phân tích SLO chính xác, cần mô tả cụ thể mỗi timestamp đo ở boundary nào.

Trong một JVM, dùng `System.nanoTime()` để tính **duration**, không dùng `System.currentTimeMillis()` cho phép trừ thời gian đòi hỏi độ ổn định trước việc chỉnh đồng hồ hệ thống. Giá trị `nanoTime()` là tương đối, **không so sánh trực tiếp giữa hai process/máy khác nhau**.

## 3. Ví dụ số: caller wait phụ thuộc lúc gọi get()

Giả sử:

- Submit tại 0 ms.
- Worker bắt đầu tại 300 ms.
- Task kết thúc tại 500 ms.

Khi ấy queue wait khoảng **300 ms**, execution time **200 ms**, submit-to-finish **500 ms**.

| Caller hành động | Caller wait xấp xỉ | Diễn giải |
| --- | ---: | --- |
| Gọi `get()` ngay sau submit | 500 ms | Chờ cả queue và execution |
| Đến 350 ms mới gọi `get()` | 150 ms | Chỉ chờ phần task chưa hoàn tất |
| Đến 600 ms mới gọi `get()` | Gần 0 ms | Future đã có kết quả |
| Gọi `get(100 ms)` ngay từ 0 ms | 100 ms rồi `TimeoutException` | Task còn ở queue và vẫn có thể tiếp tục |
| Không gọi `get()` | 0 ms | Task vẫn có thể chạy độc lập |

Đây là timeline minh họa lý tưởng, không phải stdout thực tế. Chi phí scheduler, GC và wrapper có thể khiến các mốc chênh lệch nhỏ.

Nếu ứng dụng trả HTTP 202 ngay sau submit, **request latency có thể thấp** trong khi business-job latency rất cao. Nếu controller lập tức gọi `get()`, thread HTTP có thể bị chặn dù task chạy trên pool riêng.

## 4. Queue wait hình thành như thế nào trong ThreadPoolTaskExecutor?

`ThreadPoolTaskExecutor` cấu hình `ThreadPoolExecutor` bên dưới. Quy tắc tiếp nhận task thường là:

1. Ưu tiên tạo core worker khi chưa có đủ `corePoolSize`.
2. Khi đã đủ core worker, thử đưa task vào queue.
3. Nếu queue không nhận thêm được, thử tạo worker đến `maxPoolSize`.
4. Nếu worker và queue đã hết khả năng nhận, áp dụng rejection policy.

Cấu hình `queueCapacity` thay đổi cách xử lý:

- Với `queueCapacity > 0`, Spring dùng `LinkedBlockingQueue` dung lượng đã đặt. Task có thể đợi trước khi worker được giải phóng.
- Với `queueCapacity = 0`, Spring dùng `SynchronousQueue`, không lưu backlog; task được handoff trực tiếp hoặc pool thử mở worker khác.
- Với queue dung lượng rất lớn, số task chờ có thể tích lũy nhiều, làm p95/p99 queue wait và memory retention tăng, dù `maxPoolSize` đã đặt cao.

**queueCapacity là số phần tử, không phải thời gian.** Không tồn tại ý nghĩa “queueCapacity=100 tức chờ tối đa 100 ms”. Thời gian chờ phụ thuộc tốc độ gửi task, tốc độ hoàn thành, pool size và lịch xử lý.

### 4.1. Queue size không bằng queue wait

`executor.getQueueSize()` là một snapshot về lượng task đang chờ, không phải tuổi của task. Một hàng đợi chỉ có một task vẫn có thể chứa task đang chờ rất lâu nếu worker bị kẹt. Ngược lại, queue size bằng 0 vẫn có thể đi kèm runtime cao hoặc nhiều caller đang chờ Future.

Với `SynchronousQueue`, queue size về mặt cấu trúc bằng 0, không đủ để kết luận executor không bị quá tải. Cần theo dõi `activeCount`, throughput, rejection và phân phối submit-to-start latency.

### 4.2. Task bị reject hoặc bị hủy trước khi chạy

Nếu submit ném `TaskRejectedException`, task chưa được chấp nhận. Nếu bị cancel khi chưa bắt đầu, `t1/t2` không tồn tại theo nghĩa task body. Vì vậy không đưa các job này vào histogram “execution time của task đã chạy” với giá trị 0 giả. Ghi riêng **rejected, cancelled-before-start, expired-before-start** để tránh sai lệch thống kê.

## 5. Runtime: thời gian trôi qua, không phải thời gian dùng CPU

Một worker có thể chạy task trong 1 giây nhưng chỉ dùng vài mili giây CPU nếu phần lớn thời gian chờ JDBC, HTTP response, lock, filesystem hoặc semaphore. Đó vẫn là **execution time 1 giây** khi đo elapsed time ở boundary của task.

Phân biệt hai hướng tối ưu:

- Queue wait cao nhưng runtime thấp: thường cần xem backlog, sizing core/max/queue, admission control và fairness.
- Runtime cao nhưng queue wait thấp: thường cần xem logic, I/O, query, lock, downstream timeouts hoặc giới hạn connection pool.

Chỉ tăng số thread khi bottleneck thật sự cho phép có thêm concurrency. Với downstream DB đã cạn connections, tăng thread pool có thể khiến cả queue wait lẫn runtime tệ hơn.

Một fragment đo runtime:

```java
long startedNanos = System.nanoTime();
try {
    return work.call();
} finally {
    long executionNanos = System.nanoTime() - startedNanos;
    recordExecutionTime(executionNanos);
}
```

Đoạn này là fragment, đòi hỏi `Callable<T> work` và hàm `recordExecutionTime(...)` đã khai báo. Nếu metrics callback ném lỗi thì nó có thể làm thay đổi kết quả task; observer nên không ném exception.

## 6. Caller wait: giới hạn của get(timeout) là giới hạn chờ, không phải giới hạn chạy

`Future.get(timeout, unit)` chờ tối đa khoảng được cung cấp cho **lần gọi đó**. Nếu kết quả chưa sẵn sàng, nó ném `TimeoutException`. Quan trọng:

- Timeout của `get` **không tự gọi `future.cancel(...)`**.
- Nó **không dừng** worker và không xóa task khỏi queue.
- Task có thể bắt đầu sau khi caller đã timeout và tiếp tục thực hiện side effect.
- Nếu caller gọi `get(100ms)` nhiều lần, mỗi lần được một budget chờ mới; tổng thời gian caller bị block có thể vượt 100 ms.
- Nếu caller bắt đầu `get(100ms)` sau 900 ms kể từ submit, thời gian toàn workflow có thể khoảng 1.000 ms hoặc hơn, không phải hạn 100 ms từ lúc submit.

Ví dụ fragment:

```java
try {
    String value = future.get(100, TimeUnit.MILLISECONDS);
    use(value);
} catch (TimeoutException ex) {
    // Future vẫn có thể đang ở queue hoặc đang chạy.
    // Quyết định rõ: tiếp tục theo dõi, cancel, trả trạng thái pending...
}
```

Đây là fragment; `Future<String> future`, hàm `use` và các imports/cách xử lý `InterruptedException`/`ExecutionException` phải có trong ứng dụng thật.

### 6.1. Request latency không trùng caller wait

Request latency còn bao gồm validation, serialization, database, logic HTTP và nhiều bước khác. Caller wait chỉ là khoảng thời gian request thread bị chặn do Future. Một request không gọi `get()` có caller wait bằng 0 dù job nền mất nhiều phút.

Ở phía người dùng, cần đặt SLO tách biệt cho **request acknowledgement latency** và **business job completion latency**.

## 7. Deadline, timeout và cancellation: ba ý nghĩa khác nhau

Vì đề bài thuộc nhóm **Hết hạn và hủy**, cần làm rõ sự khác biệt:

| Cơ chế | Hạn chế điều gì? | Có tự dừng task không? |
| --- | --- | --- |
| `Future.get(timeout)` | Thời gian **caller chờ trong một lần** | Không |
| Deadline nghiệp vụ | Hạn cuối mà kết quả còn có giá trị | Không, nếu không có kiểm tra/chính sách |
| Timeout của HTTP/JDBC client trong task | Thời gian I/O/downstream được phép chờ | Phụ thuộc API và cách cấu hình |
| `Future.cancel(true)` | Cố gắng hủy Future và có thể yêu cầu interrupt task | Best-effort, không bảo đảm task dừng ngay |
| `CompletableFuture.orTimeout(...)` | Complete Future bằng lỗi timeout khi chưa xong | Không cam kết interrupt công việc nền |
| `CompletableFuture.completeOnTimeout(...)` | Complete Future bằng giá trị fallback | Không cam kết hủy việc thật |

### 7.1. Hết hạn khi còn ở queue

Một task có deadline 10:00, nhưng đến 10:01 worker mới nhận được. Nếu không có guard, task có thể vẫn thực hiện một công việc đã vô ích. Có thể truyền deadline vào payload rồi kiểm tra **ngay khi bắt đầu thực thi**:

```java
long deadlineNanos = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);

Callable<String> work = () -> {
    if (System.nanoTime() - deadlineNanos >= 0) {
        throw new TimeoutException("Expired before work started");
    }
    return performWork();
};
```

Đây là fragment, cần `Callable`, `TimeUnit`, `TimeoutException` và hàm `performWork()` có sẵn. Nó không lấy task ra khỏi queue trước khi start; nó chỉ bỏ qua phần việc sau khi đã có worker nếu deadline hết hạn.

Để thực sự điều khiển backlog, cần thêm bounded queue, admission control, policy loại bỏ việc cũ và quy trình theo dõi trạng thái.

### 7.2. Hết thời gian chạy

Một task đã nhận worker có thể mắc kẹt ở network/DB. Lúc này `get(timeout)` của caller không đủ; phải cấu hình timeout ở client/downstream và/hoặc cooperative cancellation trong task.

Một phương thức `Future.cancel(true)` của FutureTask có thể gửi interrupt cho worker đang chạy, nhưng không thể khẳng định HTTP/socket/JDBC call nào cũng dừng ngay. `CompletableFuture.cancel(true)` có semantics riêng, không dùng tham số `mayInterruptIfRunning` để bảo đảm interrupt.

### 7.3. Không retry side effect chỉ vì người gọi hết kiên nhẫn

Nếu user gửi thanh toán hoặc email, caller có thể timeout trước khi task ghi xong. Gửi lại cùng một việc ngay lập tức có thể tạo hai side effect. Dùng idempotency key, job status, transaction/outbox hoặc đối soát phù hợp.

Timeout của người gọi phản ánh **thiếu kết quả đúng hạn**, không tự chứng minh công việc chưa xảy ra.

## 8. Thực nghiệm runnable Java 21 + Spring Framework 6.2.1

Chương trình này cố ý tạo hai lần timeout của cùng một `Future<Integer>`:

1. Pool có **1 worker** và queueCapacity=2.
2. Task A chiếm worker, chờ latch.
3. Task B được submit, nhưng không thể chạy vì A đang giữ worker.
4. Caller gọi `B.get(30ms)` và timeout **khi B còn ở queue**.
5. Thả A, task B bắt đầu và bị giữ bởi latch khác.
6. Caller lại `B.get(30ms)` và timeout **khi B đang chạy**.
7. Thả B, đọc kết quả 42. Hai lần timeout không làm Future bị hủy.

Không dùng `Thread.sleep()` để đoán lịch thực thi. Tất cả mốc quan trọng có `CountDownLatch` bảo vệ.

### 8.1. Cấu trúc Maven

```text
task-timing-demo/
├── pom.xml
└── src/main/java/demo/TaskTimingDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>task-timing-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.1</version>
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
        <version>3.5.0</version>
        <configuration>
          <mainClass>demo.TaskTimingDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**Tệp `src/main/java/demo/TaskTimingDemo.java`:**

```java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicLong;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class TaskTimingDemo {
    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("workExecutor")
        public ThreadPoolTaskExecutor workExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(2);
            executor.setThreadNamePrefix("timed-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }
    }

    private static void await(CountDownLatch latch, String step)
            throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException(step + " not reached");
        }
    }

    private static boolean timedOut(
            Future<?> future, AtomicLong callerWaitNanos)
            throws InterruptedException, ExecutionException {
        long beforeWait = System.nanoTime();
        try {
            future.get(30, TimeUnit.MILLISECONDS);
            return false;
        } catch (TimeoutException expected) {
            return true;
        } finally {
            callerWaitNanos.addAndGet(System.nanoTime() - beforeWait);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            ThreadPoolTaskExecutor executor =
                    context.getBean("workExecutor", ThreadPoolTaskExecutor.class);

            CountDownLatch blockerStarted = new CountDownLatch(1);
            CountDownLatch releaseBlocker = new CountDownLatch(1);
            CountDownLatch taskStarted = new CountDownLatch(1);
            CountDownLatch releaseTask = new CountDownLatch(1);
            AtomicLong startedNanos = new AtomicLong();
            AtomicLong finishedNanos = new AtomicLong();
            AtomicLong callerWaitNanos = new AtomicLong();

            try {
                Future<Void> blocker = executor.submit((Callable<Void>) () -> {
                    blockerStarted.countDown();
                    releaseBlocker.await();
                    return null;
                });
                await(blockerStarted, "blockerStarted");

                long submittedNanos = System.nanoTime();
                Future<Integer> task = executor.submit((Callable<Integer>) () -> {
                    startedNanos.set(System.nanoTime());
                    taskStarted.countDown();
                    try {
                        releaseTask.await();
                        return 42;
                    } finally {
                        finishedNanos.set(System.nanoTime());
                    }
                });

                boolean timeoutInQueue = timedOut(task, callerWaitNanos);
                releaseBlocker.countDown();
                await(taskStarted, "taskStarted");
                boolean timeoutWhileRunning = timedOut(task, callerWaitNanos);
                releaseTask.countDown();

                int result = task.get(5, TimeUnit.SECONDS);
                blocker.get(5, TimeUnit.SECONDS);

                long queueWaitNanos = startedNanos.get() - submittedNanos;
                long executionNanos = finishedNanos.get() - startedNanos.get();

                System.out.println("timeoutInQueue=" + timeoutInQueue);
                System.out.println("timeoutWhileRunning=" + timeoutWhileRunning);
                System.out.println("result=" + result);
                System.out.println("cancelled=" + task.isCancelled());
                System.out.println("queueWaitPositive=" + (queueWaitNanos > 0));
                System.out.println("executionPositive=" + (executionNanos > 0));
                System.out.println("callerWaitPositive=" +
                        (callerWaitNanos.get() > 0));
            } finally {
                releaseBlocker.countDown();
                releaseTask.countDown();
            }
        }
    }
}
```

### 8.2. Biên dịch và chạy

Yêu cầu Maven và JDK 21 trở lên. Từ thư mục chứa `pom.xml`:

```bash
mvn -q -DskipTests compile exec:java
```

**Stdout đã biên dịch và kiểm thử thực tế:**

```text
timeoutInQueue=true
timeoutWhileRunning=true
result=42
cancelled=false
queueWaitPositive=true
executionPositive=true
callerWaitPositive=true
```

Chương trình in boolean để tránh khẳng định các số mili giây không ổn định giữa các môi trường. Kết quả 42 và hai lần timeout đã được xác nhận bằng `Future`; `cancelled=false` cho thấy việc timeout ở caller không làm Future bị hủy.

### 8.3. Giải thích ba phép đo trong code

- `submittedNanos` được lấy trước khi gửi B.
- `startedNanos` được ghi khi worker đã bắt đầu B, sau khi A được giải phóng.
- `finishedNanos` được ghi trong `finally` của B khi body B kết thúc.
- `callerWaitNanos` được cộng thêm thời gian elapsed của **hai lời gọi `get(30ms)`** trong hàm `timedOut`.

Do đó:

```java
long queueWaitNanos = startedNanos.get() - submittedNanos;
long executionNanos = finishedNanos.get() - startedNanos.get();
long callerBlockedNanos = callerWaitNanos.get();
```

Đây là fragment giải thích, lấy từ các biến đã khai báo trong ví dụ. Nó đo khoảng submit-to-start, thời gian chạy của B và **tổng thời gian chờ của đúng hai lần get(timeout) được instrument**. Nó không tính lời gọi `get(5, SECONDS)` cuối để nhận 42; muốn đo toàn bộ caller wait của một flow phải bọc tất cả những lần chờ cần tính.

Có thể thêm đoạn sau để xem các số đo trên máy:

```java
System.out.printf(
        "queue=%.3fms, execution=%.3fms, callerWait=%.3fms%n",
        queueWaitNanos / 1_000_000.0,
        executionNanos / 1_000_000.0,
        callerBlockedNanos / 1_000_000.0);
```

Các giá trị này **sẽ thay đổi theo scheduling**, không có stdout số cố định. Hai lần caller wait chồng lên một phần thời gian queue/execution, nên không cộng chúng vào submit-to-finish.

### 8.4. Vì sao test ổn định?

`blockerStarted` bảo đảm worker đã chiếm bởi A. `releaseBlocker` bảo đảm B còn ở queue trong lần timeout đầu. `taskStarted` xác nhận B đã chuyển từ queue sang running. `releaseTask` giữ B đang chạy trong lần timeout thứ hai. `finally` giải phóng cả hai latch nếu assertion xảy ra lỗi, tránh để worker kẹt mãi.

Đây là kỹ thuật test concurrency tốt hơn dựa vào `Thread.sleep(100)`, vì thứ tự thực thi không được quyết định bằng cảm giác rằng thread có lẽ đã chạy.

## 9. Đo thực tế bằng wrapper khi không dùng latch

Trong production có thể bọc `Callable<T>` tại điểm submit:

```java
// Fragment utility: imports Callable, Future, LongConsumer, AsyncTaskExecutor.
public static <T> Future<T> submitMeasured(
        AsyncTaskExecutor executor,
        Callable<T> work,
        LongConsumer queueObserver,
        LongConsumer runtimeObserver) {

    long submittedAt = System.nanoTime();

    return executor.submit(() -> {
        long startedAt = System.nanoTime();
        queueObserver.accept(startedAt - submittedAt);
        try {
            return work.call();
        } finally {
            runtimeObserver.accept(System.nanoTime() - startedAt);
        }
    });
}
```

Đây là fragment cần nằm trong một class và cần observer thread-safe, nhanh, không ném exception; nếu observer ném lỗi có thể làm task hỏng hoặc che mất lỗi nghiệp vụ. Vùng đo submit-to-start bao gồm chi phí dispatch, không phải chỉ riêng thời gian trong cấu trúc queue.

**Nếu submit bị reject**, wrapper chưa từng chạy; phải ghi nhận `TaskRejectedException` ở caller hoặc instrumentation của executor. Nếu task bị hủy trước start, cũng không có runtime sample như task đã chạy.

### 9.1. TaskDecorator của Spring có đủ không?

`ThreadPoolTaskExecutor.setTaskDecorator(...)` có thể bọc callback để thiết lập MDC, context hoặc đo timing. Nhưng với `submit(...)`, callback mà decorator thấy có thể là `FutureTask` đã bọc task gốc; lỗi của task có thể được lưu trong Future thay vì thoát ra khỏi `run()`.

Vì vậy `TaskDecorator` không đương nhiên cho bạn exception và timestamp gốc một cách hoàn chỉnh. Hãy xác định nơi capture submit time, cách nhận diện task, và ai quan sát Future outcome. Không mặc định `catch(Throwable)` quanh `Runnable.run()` sẽ bắt được mọi lỗi từ task submit.

### 9.2. Những chỉ số cần xem cùng nhau

- Histogram queue wait (p50/p95/p99), runtime (p50/p95/p99).
- Caller wait phân theo endpoint/call site.
- Submit-to-completion latency của công việc thật.
- Accepted, rejected, expired, cancelled, failed, succeeded counts.
- `getPoolSize()`, `getActiveCount()`, `getQueueSize()` theo thời gian.
- CPU, GC, thread count, DB/HTTP pool wait, downstream timeout và retry rate.

Một snapshot queue size tại một thời điểm không thay thế được distribution của thời gian chờ.

## 10. Deadline chung cho toàn workflow thay vì reset get(timeout)

Giả sử request có ngân sách **800 ms** tính từ lúc bắt đầu, nhưng mất 500 ms cho validation. Nếu sau đó gọi `future.get(800ms)`, tổng thời gian có thể lên đến 1.300 ms.

Một cách tính budget còn lại bằng monotonic clock:

```java
long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(800);

// ... nhiều bước khác đã trôi qua ...

long remaining = deadline - System.nanoTime();
if (remaining <= 0) {
    throw new TimeoutException("Overall deadline reached");
}

String value = future.get(remaining, TimeUnit.NANOSECONDS);
```

Đây là fragment; cần `Future<String> future` và xử lý các checked exceptions. Mỗi bước tiếp theo phải tính lại `remaining` từ **cùng deadline**. Điều này giới hạn thời gian chờ tổng của caller tốt hơn việc tạo timeout mới mỗi bước, nhưng **chưa tự buộc task dừng đúng deadline**.

Khi truyền qua nhiều JVM, không gửi nguyên giá trị `System.nanoTime()` như timestamp toàn cục: gốc monotonic clock khác nhau. Có thể truyền ngân sách thời gian còn lại hoặc một deadline theo wall clock được xử lý có tính đến sai lệch đồng hồ.

## 11. Spring @Async và CompletableFuture: dễ nhầm phạm vi đo

### 11.1. @Async chỉ chạy qua proxy khi đủ điều kiện

Trong `AdviceMode.PROXY` mặc định, `@Async` cần Spring-managed bean, cấu hình `@EnableAsync` (hoặc XML annotation-driven) và caller gọi qua proxy. Lời gọi `this.asyncMethod()` trong cùng target bypass proxy; lúc đó method có thể chạy đồng bộ, không tồn tại một lượt async submission mới cho method đó.

Nếu muốn đo queue wait của `@Async`, cần instrument tại executor/submission boundary thay vì chỉ lấy timestamp đầu method. Đừng cố sửa “queue wait=0” bằng tăng `maxPoolSize` khi thực ra không có proxy interception.

### 11.2. Future của proxy khác giá trị Future tạm của target

Một method `@Async` khai báo `CompletableFuture<T>` có thể trả `CompletableFuture.completedFuture(value)` trong body. Đây là Future tạm chuyển giá trị từ target; caller nhận Future của proxy. Future của proxy có thể còn pending cho đến khi worker chạy và bridge kết quả hoàn tất.

Khi đo caller wait, đo trên Future caller thực tế cầm; khi đo runtime, xác định thời gian của invocation target/bridge; khi đo queue wait, bắt đầu từ điểm Spring submit invocation task.

### 11.3. get(timeout), orTimeout và completeOnTimeout khác nhau

- `future.get(timeout, unit)` timeout lời gọi **chờ**, không tự thay đổi completion state của Future.
- `CompletableFuture.orTimeout(timeout, unit)` làm Future hoàn tất bằng lỗi timeout nếu vẫn chưa xong, nhưng không cam kết hủy/interrupt worker.
- `CompletableFuture.completeOnTimeout(defaultValue, timeout, unit)` cho phép Future hoàn tất bằng fallback, không chứng minh công việc nền đã dừng.

Không dùng ba API này thay thế cho timeout của JDBC/HTTP client hay contract cancel nghiệp vụ.

## 12. Khi caller timeout: tiếp tục, hủy hay theo dõi?

Các lựa chọn cần dựa trên tính chất công việc:

**Tác vụ có thể bỏ qua**, ví dụ phép tính gợi ý nhanh: caller có thể thử `cancel(...)` hoặc đánh dấu kết quả không còn cần. Task phải hỗ trợ cooperative cancellation nếu muốn thật sự tiết kiệm worker.

**Tác vụ bắt buộc hoàn tất**, ví dụ phát hành hóa đơn: caller timeout không làm yêu cầu nghiệp vụ hết hiệu lực. Cần lưu job ID, trạng thái durable, idempotency, retry có kiểm soát hoặc outbox/broker thích hợp; request nên có cách tra cứu kết quả.

**Tác vụ đã quá deadline nghiệp vụ**, ví dụ refresh một cache snapshot cũ: nên kiểm tra deadline trước khi bắt đầu side effect hoặc tại các safe points trong task và ghi trạng thái expired. Đừng giả vờ queue automatically biết deadline nếu chỉ cấu hình `queueCapacity`.

Tách biệt **ngưng chờ của người gọi**, **ngưng xử lý của worker** và **ngưng hiệu lực nghiệp vụ**.

## 13. Những sai lầm phổ biến

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Xem queue wait, runtime và caller wait là một | Đo sai latency và nguyên nhân | Capture timestamp ở ba boundary riêng |
| Cộng caller wait vào queue + runtime | Đếm trùng thời gian | Đặt timeline song song |
| Cho rằng `get(timeout)` giới hạn execution time | Chỉ giới hạn một lần caller đợi | Thêm deadline/timeout bên trong task |
| Dùng `queueCapacity=100` như queue timeout 100 ms | Capacity là số task | Đo tuổi task và kiểm tra deadline |
| Đợi Future sau khi task đã xong rồi suy runtime từ get() | Caller wait gần 0 dù runtime có thể lớn | Đo start/end trong task |
| Dùng `get(100ms)` nhiều lần và nghĩ tổng là 100ms | Mỗi lời gọi có budget mới | Dùng deadline chung |
| Tin `cancel(true)` luôn kill worker | Interrupt best-effort, phụ thuộc API | Cooperative cancellation và cleanup |
| Chỉ nhìn `getQueueSize() == 0` | Không phản ánh task đang chạy/chờ caller | Theo dõi activeCount, runtime, wait latency |
| Tăng queue để “giải quyết” runtime cao | Chỉ giữ thêm backlog | Tìm bottleneck của task/downstream |
| Gắn timestamp đầu `@Async` và coi đó là submit time | Bỏ mất queue wait | Đo tại proxy/executor boundary |
| Chỉ nhìn `Future.isDone()` và coi success | Done bao gồm cancel/exception | Phân loại outcome riêng |
| Bỏ qua rejection/cancel-before-start | Metrics thiếu những task không chạy | Ghi rejected/cancelled/expired riêng |
| Retry việc tạo side effect ngay sau timeout | Có thể chạy hai lần | Idempotency key và job status |
| Trừ `nanoTime()` của hai máy | Gốc monotonic clock khác nhau | Truyền budget/deadline phù hợp |

## 14. Bài tập tự kiểm tra

**Câu 1.** Submit tại 0 ms, start tại 250 ms, finish tại 400 ms, caller bắt đầu get lúc 300 ms. Tính ba đại lượng.

Queue wait 250 ms, runtime 150 ms, caller wait xấp xỉ 100 ms. Submit-to-finish 400 ms, **không cộng thêm** 100 ms caller wait.

**Câu 2.** Caller nhận `TimeoutException` khi task chưa bắt đầu. Task có bị hủy không?

Không. `Future.get(timeout)` không tự hủy. Task có thể được worker chạy sau khi queue có chỗ giải phóng.

**Câu 3.** Queue wait 900 ms, runtime 10 ms so với queue wait 10 ms, runtime 900 ms — tổng latency gần bằng nhau; cách xử lý có giống nhau không?

Không. Ca đầu cần xem backlog và executor scheduling, ca sau cần xem tác vụ/I/O/lock/downstream. Chỉ tăng queue capacity có thể khiến trường hợp đầu tệ hơn.

**Câu 4.** Một caller không gọi `get()` mà trả HTTP 202 ngay. Caller wait bằng bao nhiêu? Có chứng minh task đã xong không?

Caller wait đối với Future bằng 0; không chứng minh task đã hoàn tất. Cần job completion metric và API trạng thái.

**Câu 5.** Cùng một Future, caller gọi `get(100ms)` ba lần liên tiếp và đều timeout. Tổng thời gian chờ thực tế có thể bao nhiêu?

Khoảng 300 ms cộng overhead, dù mỗi get dùng timeout 100 ms. Để hạn chế cả workflow, dùng một deadline chung.

**Câu 6.** Vì sao `ThreadPoolTaskExecutor.getQueueSize() == 0` không có nghĩa không có người chờ?

Vì task có thể đang chạy lâu, caller đang đợi Future hoặc executor dùng `SynchronousQueue` vốn không giữ phần tử. Queue size không phải caller wait hay runtime.

## 15. Checklist production

Trước khi đưa hệ thống vào vận hành, hãy xác nhận:

- Có định nghĩa rõ mốc submit, worker-start, worker-finish, caller-get-start/end chưa?
- Các timestamp đo duration trong cùng process bằng monotonic clock?
- Có histogram p50/p95/p99 queue wait, runtime, caller wait và submit-to-completion?
- Có tách accepted/rejected/cancelled/expired task khỏi nhóm đã thực thi?
- Có hiểu đúng `corePoolSize`, `maxPoolSize`, `queueCapacity`, rejection policy và pool thực sự được tiêm?
- Nếu dùng `@Async`, lời gọi có đi qua proxy thay vì self-invocation?
- Có deadline chung và tính remaining budget trước mỗi `get(timeout)`?
- Có timeout riêng cho DB/HTTP/lock trong task không?
- Nếu caller timeout, task có nên chạy tiếp hay cố hủy? Ai giữ trạng thái cuối?
- Với side effect, có idempotency/retry/durable job semantics?
- Caller có đang block event-loop hoặc request worker không cần thiết?
- Test có dùng `CountDownLatch`/phương pháp điều phối để phân biệt queued và running, tránh phụ thuộc `Thread.sleep()`?

## 16. Tóm tắt

**Queue wait** là khoảng từ khi submit đến khi worker bắt đầu. **Execution time** là khoảng worker thực thi code được đo. **Caller wait** là khoảng thread gọi đợi Future; nó có thể bao trùm cả queue+runtime, chỉ một phần, gần 0 hoặc kết thúc bằng timeout trong khi task chưa chạy.

Trong Spring, đo ba khoảng thời gian tại ba boundary khác nhau và quan sát cùng với executor metrics. Đặc biệt, **hết thời gian caller chờ không đồng nghĩa task hết hạn hoặc bị hủy**. Thiết kế deadline, timeout downstream, cancellation và idempotency dựa trên yêu cầu nghiệp vụ, không chỉ dựa vào `Future.get(timeout)`.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2.1 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2.1 — AsyncTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html)
- [Java 21 — Future API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 21 — CompletableFuture API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
- [Java 21 — System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime())