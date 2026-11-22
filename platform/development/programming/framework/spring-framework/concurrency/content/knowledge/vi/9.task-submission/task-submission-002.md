# Gửi Runnable hoặc Callable qua submit() trong Spring Framework

## 1. Vì sao cần submit() thay vì chỉ gọi execute()?

Một ứng dụng thường có những công việc như tạo báo cáo, tính toán điểm, xử lý dữ liệu nhập hoặc gửi thông báo. Thành phần nghiệp vụ muốn **gửi một tác vụ để executor thực thi**, đồng thời có thể cần biết khi nào tác vụ hoàn tất, nhận giá trị tính được hoặc biết tác vụ đã thất bại.

Khi chỉ muốn yêu cầu thực thi, hợp đồng `execute(Runnable)` đủ dùng. Nhưng khi cần **một handle để theo dõi kết quả**, các phương thức `submit(...)` tiện hơn vì trả về `Future`.

Trong Java và Spring, hai dạng tác vụ cơ bản là:

- **`Runnable`**: hành động có phương thức `run()`, không trả về giá trị. Phù hợp cho tác vụ tạo side effect như ghi audit, cập nhật chỉ số, gửi sự kiện.
- **`Callable<T>`**: tác vụ có phương thức `call()` trả về một `T`, đồng thời có thể khai báo ném checked exception. Phù hợp khi caller cần kết quả xử lý.

Ví dụ:

```java
Runnable audit = () -> System.out.println("Audit stored");

Callable<Integer> score = () -> 10 * 2 + 1;
```

Hai dòng này chỉ **tạo task**, chưa gửi chúng vào executor. Đây là fragment; cần import `java.util.concurrent.Callable` và có thể đặt trong method Java bình thường.

Gửi task thường có dòng đời:

```text
caller
  | submit(Runnable / Callable)
  v
executor -- accept / queue / schedule --> worker thread --> task.run()/call()
  |
  +-- return Future immediately (for an async executor)
          |
          +-- get() / get(timeout) -> value or exception
          +-- isDone(), isCancelled(), cancel(...)
```

Mô hình trên áp dụng cho executor thực sự chạy bất đồng bộ. Một implementation của `AsyncTaskExecutor` có thể sử dụng chính sách thực thi cụ thể khác, nên hãy kiểm tra bean đang dùng; **submit không tự bảo đảm task chạy trên một thread mới**.

## 2. Phải dùng đúng interface: TaskExecutor, AsyncTaskExecutor và ExecutorService

Trong Spring Framework 6.x, những kiểu thường gặp có cấp độ khả năng khác nhau:

| Kiểu | API chính | Có submit(Runnable/Callable)? | Vai trò |
| --- | --- | --- | --- |
| `java.util.concurrent.Executor` | `execute(Runnable)` | Không | Hợp đồng tối thiểu của JDK |
| `org.springframework.core.task.TaskExecutor` | `execute(Runnable)` | Không | Interface executor cơ bản trong Spring, mở rộng `Executor` |
| `org.springframework.core.task.AsyncTaskExecutor` | `execute(...)` và `submit(...)` | Có | Interface Spring khi caller muốn `Future` |
| `java.util.concurrent.ExecutorService` | `execute`, `submit`, `shutdown`... | Có | Executor của JDK có các API quản lý kết quả và vòng đời |
| `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` | Hỗ trợ `AsyncTaskExecutor`, chạy trên pool | Có | Bean executor của Spring được cấu hình và quản lý vòng đời |

**Lỗi biên dịch rất dễ gặp:**

```java
TaskExecutor executor = /* Spring-managed executor */;
// executor.submit(() -> 42); // KHÔNG biên dịch: TaskExecutor không khai báo submit().
executor.execute(() -> System.out.println("Run without Future"));
```

Nếu service thực sự cần `Future`, tiêm interface `AsyncTaskExecutor` (hoặc `ExecutorService` nếu thiết kế phụ thuộc JDK service interface). Không ép kiểu một `TaskExecutor` bất kỳ thành `ThreadPoolTaskExecutor` chỉ để gọi `submit`; việc đó ràng buộc nghiệp vụ vào implementation và có thể gây `ClassCastException`.

Khi dùng Spring-managed `ThreadPoolTaskExecutor`, bạn có thể tiêm nó bằng **kiểu interface `AsyncTaskExecutor`**. Điều này cho phép đổi executor tương thích trong cấu hình mà không sửa business service.

## 3. Phân biệt submit(Runnable) và submit(Callable<T>)

### 3.1. submit(Runnable): theo dõi việc hoàn thành

Chữ ký:

```java
Future<?> submit(Runnable task);
```

Dùng khi task **không tạo một giá trị trả về trực tiếp**:

```java
Runnable task = () -> counter.incrementAndGet();
Future<?> future = asyncExecutor.submit(task);
Object result = future.get(); // null nếu task kết thúc bình thường.
```

Đây là fragment, yêu cầu các biến `counter` và `asyncExecutor` đã được khai báo và xử lý checked exceptions từ `get()`.

Những điều cần nắm:

- `Future.get()` đợi đến khi `Runnable` hoàn tất; **giá trị kết quả là `null`** nếu task thành công.
- `null` không chứng minh tác vụ “không làm gì”: side effect có thể đã xảy ra.
- Nếu `Runnable.run()` ném exception và implementation lưu lỗi qua `Future`, `get()` sẽ ném `ExecutionException` với nguyên nhân gốc ở `getCause()`.
- `submit` có thể từ chối task ngay tại thời điểm gửi, ví dụ `TaskRejectedException` từ `ThreadPoolTaskExecutor` khi pool và queue đã quá tải.

### 3.2. submit(Callable<T>): nhận giá trị hoặc lỗi

Chữ ký:

```java
<T> Future<T> submit(Callable<T> task);
```

Dùng khi task **có kết quả**:

```java
Callable<Integer> task = () -> 10 * 2 + 1;
Future<Integer> future = asyncExecutor.submit(task);
Integer value = future.get(); // 21 khi task thành công.
```

`Callable.call()` có thể ném checked exceptions, trong khi `Runnable.run()` không khai báo `throws Exception`. Dù vậy, cả runtime exception của hai loại task đều cần được quan sát qua `Future` và cách xử lý của executor.

### 3.3. Bảng kết quả cần nhớ

| Cách gọi | Kiểu trả về của submit | Giá trị từ Future.get() khi thành công | Tác vụ lỗi |
| --- | --- | --- | --- |
| `submit(Runnable)` | `Future<?>` | `null` | Thông thường `ExecutionException` chứa cause |
| `submit(Callable<String>)` | `Future<String>` | Chuỗi do `call()` trả về | `ExecutionException` |
| `submit(Callable<Integer>)` | `Future<Integer>` | Số nguyên do `call()` trả về | `ExecutionException` |

Trong Spring Framework 6.1+, `AsyncTaskExecutor` có default implementation cho hai overload `submit`, tạo `FutureTask` và ủy quyền sang `execute`. Implementation như `ThreadPoolTaskExecutor` có thể ghi đè phương thức để dùng trực tiếp executor service nội bộ. **Hợp đồng kết quả** giống nhau, còn chi tiết thực hiện phụ thuộc implementation.

### 3.4. Overload và lambda: đừng để ý nghĩa mơ hồ

Một lambda dạng biểu thức method invocation có thể phù hợp cả dạng value-producing và statement. Khi đọc code, khai báo rõ kiểu có thể giúp tránh nhầm overload:

```java
Runnable update = () -> counter.incrementAndGet();
Callable<Integer> calculate = () -> 10 * 2 + 1;

Future<?> updated = asyncExecutor.submit(update);
Future<Integer> calculated = asyncExecutor.submit(calculate);
```

Các biến `counter` và `asyncExecutor` là dependency trong fragment này. Kiểu `Runnable` hoặc `Callable<T>` giúp người đọc hiểu tác giả có mong đợi giá trị trả về hay không.

## 4. Future đại diện cho điều gì?

`Future<V>` là **handle** của một phép tính bất đồng bộ. Nó không tự lưu một bản sao đầy đủ nghiệp vụ, không cam kết durability qua restart và không phải công cụ quan sát mọi task trong hệ thống.

Các thao tác cốt lõi:

- `get()`: chờ vô hạn cho đến khi task hoàn thành, bị hủy hoặc thất bại. Nếu caller bị interrupt trong lúc đợi, có thể ném `InterruptedException`.
- `get(timeout, unit)`: chờ tối đa một khoảng thời gian; nếu chưa hoàn tất, ném `TimeoutException`. Nó **không tự hủy** task đang chạy.
- `isDone()`: true nếu đã hoàn tất bình thường, lỗi hoặc bị hủy; **không đồng nghĩa thành công**.
- `isCancelled()`: cho biết `Future` đã được hủy qua cơ chế cancellation.
- `cancel(true)`: thử hủy và cho phép interrupt worker nếu task đang chạy. Trả true không bảo đảm mã task dừng ngay lập tức.
- `cancel(false)`: thử hủy nhưng không yêu cầu interrupt task đã chạy. Với task đang chờ trong queue, có thể ngăn nó thực thi, tùy implementation.

Ví dụ khung xử lý timeout:

```java
try {
    String value = future.get(2, TimeUnit.SECONDS);
    use(value);
} catch (TimeoutException ex) {
    // Task có thể vẫn đang chạy.
    future.cancel(true); // Chỉ khi nghiệp vụ cho phép dừng.
}
```

Đây là **fragment**; `future` là `Future<String>`, `use` là hàm nghiệp vụ, cần import `TimeUnit` và `TimeoutException`, đồng thời xử lý hoặc khai báo `InterruptedException`/`ExecutionException`. Không tự ý gọi `cancel(true)` nếu công việc đã gửi có side effect không được phép bỏ dở.

**Quan hệ bộ nhớ:** trong JDK, các hành động thực hiện trong task xảy ra *happens-before* các hành động của thread khác sau khi thread đó trả về thành công từ `Future.get()` tương ứng. Vì thế test có thể kiểm tra side effect sau `get()` mà không cần ngủ một khoảng thời gian đoán trước.

## 5. Ví dụ Spring Framework 6.2.1 chạy được với Java 21

Chương trình minh họa đầy đủ:

1. Inject `AsyncTaskExecutor` vào một service qua constructor.
2. Gửi `Runnable` có side effect và quan sát kết quả `null`.
3. Gửi `Callable<Integer>` và nhận giá trị.
4. Gửi `Callable` ném lỗi và đọc nguyên nhân qua `ExecutionException`.
5. Dùng `CountDownLatch` để mô phỏng task đang chờ; `get(timeout)` ném timeout nhưng task vẫn tiếp tục sau khi được giải phóng.

### 5.1. Cấu trúc dự án

```text
spring-submit-demo/
├── pom.xml
└── src/main/java/demo/SubmitTaskDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-submit-demo</artifactId>
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
          <mainClass>demo.SubmitTaskDemo</mainClass>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
```

**Tệp `src/main/java/demo/SubmitTaskDemo.java`:**

```java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SubmitTaskDemo {
    public static final class JobService {
        private final AsyncTaskExecutor executor;
        private final AtomicInteger auditCount = new AtomicInteger();

        public JobService(AsyncTaskExecutor executor) {
            this.executor = executor;
        }

        public Future<?> recordAudit() {
            Runnable task = () -> auditCount.incrementAndGet();
            return executor.submit(task);
        }

        public int auditCount() {
            return auditCount.get();
        }

        public Future<Integer> calculate(int input) {
            Callable<Integer> task = () -> input * 2 + 1;
            return executor.submit(task);
        }

        public Future<Integer> fail() {
            Callable<Integer> task = () -> {
                throw new IllegalStateException("example error");
            };
            return executor.submit(task);
        }

        public Future<String> waitForRelease(
                CountDownLatch started, CountDownLatch release) {
            Callable<String> task = () -> {
                started.countDown();
                release.await();
                return "released";
            };
            return executor.submit(task);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean("jobExecutor")
        public ThreadPoolTaskExecutor jobExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(8);
            executor.setThreadNamePrefix("job-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        public JobService jobService(
                @Qualifier("jobExecutor") AsyncTaskExecutor executor) {
            return new JobService(executor);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            JobService jobs = context.getBean(JobService.class);

            Future<?> audit = jobs.recordAudit();
            System.out.println("Runnable result=" +
                    audit.get(5, TimeUnit.SECONDS));
            System.out.println("Audit count=" + jobs.auditCount());

            Future<Integer> value = jobs.calculate(10);
            System.out.println("Callable result=" +
                    value.get(5, TimeUnit.SECONDS));

            Future<Integer> failure = jobs.fail();
            try {
                failure.get(5, TimeUnit.SECONDS);
                throw new AssertionError("Expected task failure");
            } catch (ExecutionException ex) {
                System.out.println("Failure cause=" +
                        ex.getCause().getClass().getSimpleName());
            }

            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            Future<String> slow = jobs.waitForRelease(started, release);
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            try {
                slow.get(20, TimeUnit.MILLISECONDS);
                throw new AssertionError("Expected timeout");
            } catch (TimeoutException expected) {
                System.out.println("Timeout observed=true");
            } finally {
                release.countDown();
            }
            System.out.println("After release=" +
                    slow.get(5, TimeUnit.SECONDS));
        }
    }
}
```

### 5.2. Chạy chương trình

Yêu cầu JDK 21 trở lên và Maven đã cài. Trong thư mục `spring-submit-demo`, chạy:

```bash
mvn -q -DskipTests compile exec:java
```

Output của chương trình đã được biên dịch và chạy kiểm chứng:

```text
Runnable result=null
Audit count=1
Callable result=21
Failure cause=IllegalStateException
Timeout observed=true
After release=released
```

Lệnh dùng `maven.compiler.release=21` để bảo đảm mã nguồn biên dịch theo Java 21; output phía trên là output của chương trình, không tính log phụ có thể xuất hiện tùy phiên bản Maven/JVM.

### 5.3. Vì sao kết quả ổn định?

- `audit.get(...)` chỉ trả về sau khi task `Runnable` kết thúc; vì vậy biến `auditCount` đã tăng trước khi in.
- `calculate(10)` trả về `21` thông qua `Future<Integer>`.
- `fail()` ném `IllegalStateException` bên trong worker; `Future.get(...)` ở caller ném `ExecutionException`, có `getCause()` là exception ban đầu.
- Task `waitForRelease(...)` báo đã bắt đầu bằng `started.countDown()`, sau đó chờ ở `release.await()`; caller chắc chắn không có kết quả trước khi mở latch, nên `get(20, MILLISECONDS)` đi vào nhánh timeout.
- Sau khi `release.countDown()`, task có thể chạy tiếp và `get(...)` trả về `"released"`; timeout ở caller **không tự hủy** công việc.
- Chương trình đóng Spring context bằng `try-with-resources`. Executor là Spring-managed bean nên được quản lý lifecycle. Các task đều đã hoàn tất trước khi context đóng.

Tất cả output được in từ thread chính sau khi quan sát `Future`; không giả định worker chạy theo một thứ tự tự nhiên nào khi nhiều task được gửi cùng lúc.

## 6. Trình tự xử lý kết quả và lỗi

Một `Future<T>` có thể có các trạng thái kết thúc khác nhau.

### 6.1. Thành công

Với `Callable<T>`, `get()` trả về giá trị của `call()`. Với `Runnable`, `get()` trả về `null` nếu không xảy ra lỗi.

### 6.2. Thất bại trong task

Nếu task ném exception, `Future.get()` ném `ExecutionException`; `ExecutionException.getCause()` là lỗi từ task. Với `ThreadPoolTaskExecutor.submit(...)`, một lỗi trong task thường được giữ trong `FutureTask`, nên **không nên trông chờ chỉ log của worker đã đủ**.

Một mẫu xử lý khi chờ có giới hạn:

```java
try {
    Integer result = future.get(3, TimeUnit.SECONDS);
    save(result);
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause();
    // Log/categorize lỗi nghiệp vụ từ worker.
} catch (TimeoutException ex) {
    // Bổ sung chính sách timeout/cancel/retry phù hợp.
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // Cho caller quyết định kết thúc/tháo lui tác vụ.
}
```

Đây là **fragment**: `future` thuộc kiểu `Future<Integer>`, `save` là method nghiệp vụ, cần imports `TimeUnit`, `ExecutionException` và `TimeoutException`. Mẫu dùng `Thread.currentThread().interrupt()` khi caller quyết định không ném tiếp `InterruptedException`, để giữ tín hiệu interruption. Nếu hợp đồng method cho phép, có thể truyền `InterruptedException` lên tầng trên.

### 6.3. Timeout khi chờ

`TimeoutException` chỉ nói rằng kết quả chưa sẵn sàng *trong giới hạn chờ của caller*. Tác vụ có thể tiếp tục xử lý thành công sau đó. Khi timeout xảy ra, cần xác định liệu caller có bỏ kết quả, retry, hủy hoặc lưu trạng thái để truy vấn về sau.

Không nên retry tác vụ tạo side effect ngay khi timeout mà không có idempotency key: lần cũ có thể hoàn thành sau đó, gây thực hiện hai lần.

### 6.4. Task bị hủy

Khi `Future.cancel(true)` thành công, `Future.get()` sẽ ném `CancellationException`. Nếu task đã chạy, interrupt chỉ là yêu cầu hợp tác; task có thể chưa dừng ngay. Một số lời gọi I/O, native API hoặc code bỏ qua interrupt có thể tiếp tục làm việc.

Nếu cần hủy công việc, thiết kế task có điểm kiểm tra interruption, đóng tài nguyên đúng cách và ghi trạng thái phù hợp. Không coi `cancel(true)` là rollback giao dịch hoặc undo side effect đã ghi.

### 6.5. Lỗi ngay lúc gửi task

`ThreadPoolTaskExecutor.submit(...)` có thể ném `TaskRejectedException` nếu executor không chấp nhận task vì saturation hoặc shutdown. Trường hợp này xảy ra **ngay tại submit**, trước khi có một `Future` hợp lệ để caller chờ.

Mẫu tách biệt:

```java
try {
    Future<Integer> submitted = asyncExecutor.submit(
            (Callable<Integer>) () -> 21);
    // Lúc này đã có handle để xử lý giá trị/lỗi sau khi chạy.
} catch (TaskRejectedException ex) {
    // Không có task mới được chấp nhận; xử lý overload ở caller.
}
```

Đây là fragment cần import `Callable`, `Future` và `TaskRejectedException`; `asyncExecutor` là dependency đã khai báo. Việc submit thành công có nghĩa task được chấp nhận theo chính sách executor, **không** bảo đảm task đã chạy thành công.

## 7. Phân biệt execute(), submit() và submitCompletable()

Trong Spring Framework 6.x:

| API | Tham số | Giá trị trả về | Khi phù hợp |
| --- | --- | --- | --- |
| `TaskExecutor.execute(Runnable)` | `Runnable` | `void` | Không cần handle kết quả |
| `AsyncTaskExecutor.submit(Runnable)` | `Runnable` | `Future<?>` | Cần biết task hoàn thành, lỗi hoặc hủy |
| `AsyncTaskExecutor.submit(Callable<T>)` | `Callable<T>` | `Future<T>` | Cần kết quả có kiểu `T` |
| `AsyncTaskExecutor.submitCompletable(Runnable)` | `Runnable` | `CompletableFuture<Void>` | Muốn chain callback khi task void hoàn tất |
| `AsyncTaskExecutor.submitCompletable(Callable<T>)` | `Callable<T>` | `CompletableFuture<T>` | Muốn kết hợp kết quả theo CompletionStage |

`CompletableFuture` có các API như `thenApply`, `thenCompose`, `allOf` và `exceptionally`, phù hợp khi cần kết hợp các bước bất đồng bộ mà không chủ động gọi `get()` ở mỗi bước. Tuy nhiên callback có thể chạy trên thread hoàn thành stage hoặc executor khác tùy phương thức; cần nắm rõ execution context.

Dùng `submitCompletable(...)` khi bạn thực sự cần chaining. Với bài toán “gửi một `Runnable` hoặc `Callable` và thu nhận `Future`”, hai overload `submit(...)` là đủ.

**`@Async` không đồng nghĩa `submit(...)`.** `@Async` là interceptor dựa trên Spring proxy cho method phù hợp, được kích hoạt bằng `@EnableAsync` hoặc XML annotation-driven. Gọi `asyncExecutor.submit(...)` trực tiếp không cần `@EnableAsync` và không phụ thuộc self-invocation/proxy của `@Async`.

## 8. Không gọi get() sai chỗ

`submit()` thường quay lại nhanh sau khi executor nhận task, cho phép caller làm việc khác. Nhưng:

```java
Integer value = asyncExecutor.submit(
        (Callable<Integer>) () -> expensiveCalculation()).get();
```

Nếu `expensiveCalculation()` mất nhiều thời gian, cách viết trên làm caller **đứng chờ ngay sau submit**. Nó có thể hợp lý khi cần kết quả ngay, nhưng không tạo được lợi ích bất đồng bộ ở phía caller. Đoạn là fragment, yêu cầu `expensiveCalculation` có sẵn và xử lý checked exceptions.

Một số vấn đề thường gặp:

- **Trong Spring MVC:** giữ servlet request thread chờ `Future.get()` có thể làm cạn request workers dưới tải. Hãy cân nhắc API thiết kế theo trạng thái tác vụ hoặc cơ chế async request nếu nghiệp vụ phù hợp.
- **Trong Reactor event loop:** gọi `get()`/`join()` blocking có thể chặn event-loop thread và làm tăng latency của nhiều request; không thực hiện lời gọi blocking trên event loop.
- **Trong cùng thread pool nhỏ:** Task A giữ worker và gọi `submit(B).get()` vào *chính pool đó*, trong khi tất cả workers đều đang chờ các task con khác. Những task con nằm trong queue không bao giờ được chạy — **thread starvation deadlock**. Cần bỏ việc chờ lồng nhau hoặc tách orchestration khỏi worker pool, thay đổi cấu trúc phụ thuộc, không chỉ tăng pool một cách tùy tiện.
- **Trong HTTP/API với timeout ngắn:** dùng `get(timeout)` nhưng quên timeout ở DB/HTTP client bên trong task có thể để worker tiếp tục chạy rất lâu sau khi caller bỏ cuộc.

### Tình huống deadlock điển hình

Giả sử một pool có `corePoolSize=maxPoolSize=1` và queue vẫn còn chỗ:

```text
Worker-1 thực thi task A
    -> A submit(task B) vào cùng pool
    -> B nằm trong queue
    -> A gọi B.get() và chờ
    -> Worker-1 không thể nhận B vì vẫn đang chạy A
    -> Không có worker khác -> không có tiến triển
```

Đây là deadlock do thiết kế luồng công việc, **không phải lỗi của Future**. Chỉ tăng `queueCapacity` làm B tiếp tục chờ mà không giải quyết dependency vòng.

## 9. Sizing executor và kiểm soát overload

`ThreadPoolTaskExecutor` sử dụng `ThreadPoolExecutor` bên dưới, nên `submit` cũng chịu các giới hạn thực thi như `execute`.

- **`corePoolSize`:** số worker lõi; pool thường mở worker tới ngưỡng này trước khi xếp hàng.
- **`queueCapacity`:** số task có thể chờ trong queue, không tính task đang chạy. Với giá trị dương, Spring thường dùng `LinkedBlockingQueue`; với 0, dùng `SynchronousQueue`, không lưu backlog.
- **`maxPoolSize`:** giới hạn tổng workers; khi queue đã nhận task, pool thường không mở rộng ngoài core cho đến khi queue đầy.
- **Rejection policy:** khi không thể nhận task, mặc định thường báo lỗi từ chối. Có thể cấu hình các policy khác nhưng phải hiểu hậu quả.
- **Shutdown:** executor đang đóng có thể không nhận thêm task; đã submit không có nghĩa có cơ chế đảm bảo task tồn tại qua restart.

Ví dụ trong chương trình hoàn chỉnh: `core=2`, `max=2`, `queue=8` chỉ là một cấu hình học tập có giới hạn. Không dùng nguyên các giá trị này cho mọi ứng dụng; cần đo throughput, queue wait, số task chạy, CPU, thời gian chờ I/O, giới hạn connection pool và rejection.

Hãy phân biệt hai loại thời gian:

1. **Queue wait:** từ lúc submit đến lúc worker bắt đầu thực thi.
2. **Execution time:** từ khi worker bắt đầu đến khi task kết thúc.

Thời gian từ `submit` tới lúc `Future.get()` có kết quả có thể gồm cả hai, cộng thời gian scheduler/caller. Nếu chỉ nhìn `Future.isDone()`, bạn chưa biết nút thắt nằm ở queue hay bên trong task.

### Khi nào cần backpressure?

Nếu tốc độ sinh task cao hơn tốc độ xử lý trong thời gian dài, một queue hữu hạn sẽ đầy. Cấu hình queue vô hạn có thể biến rejection thành latency lớn và memory retention. Hãy áp dụng giới hạn đầu vào, retry có backoff, timeout và chính sách giảm tải rõ ràng. Với nghiệp vụ cần bảo đảm giao việc, cân nhắc durable messaging/outbox; in-memory executor chỉ xử lý trong tiến trình hiện tại.

## 10. Exception visibility và giám sát

Một khác biệt vận hành quan trọng giữa `execute` và `submit` là **đường xuất hiện của exception**.

Với `submit`, task thường được bọc trong `FutureTask`; exception bên trong được giữ để `Future.get()` báo cho caller. Nó có thể **không** được một `UncaughtExceptionHandler` của worker nhìn thấy như một exception thoát thẳng khỏi `run()`.

Hệ quả:

- Nếu gọi `submit` nhưng bỏ hẳn `Future`, lỗi có thể không được ghi nhận ở nơi bạn mong đợi.
- Một `TaskDecorator` trong Spring thường thấy wrapper thực thi; với `submit` nó có thể thấy `FutureTask` thay vì `Runnable/Callable` gốc. Nếu muốn quan sát lỗi, phải thiết kế hook/metrics hoặc đọc kết quả theo hợp đồng.
- `ThreadPoolExecutor.afterExecute(...)` có thể cần kiểm tra `Future` để lấy lỗi từ task đã submit; không mặc định tham số `Throwable` luôn chứa lỗi task.
- Với các task quan trọng, một nơi rõ ràng phải chịu trách nhiệm kiểm tra `Future`, ghi log lỗi, cập nhật trạng thái, hoặc phát sự kiện thất bại.

Không dùng `Future.get()` vô hạn ngay trong instrumentation callback trên worker mà có thể deadlock; chỉ đọc kết quả khi Future chắc chắn đã hoàn tất và xử lý cancellation/exception phù hợp.

## 11. Thread safety, transaction và context của caller

Gửi task sang pool nghĩa là mã task có thể chạy ở **thread khác** và tại **thời điểm khác**.

### 11.1. Thread safety

Nhiều task có thể chạy đồng thời, cùng truy cập một service singleton hoặc dữ liệu chia sẻ. Sử dụng immutable inputs, `AtomicInteger`, đồng bộ hóa có chủ đích hoặc cấu trúc dữ liệu thread-safe khi cần. Ví dụ sử dụng `AtomicInteger` để side effect từ `Runnable` được an toàn khi nhiều threads cập nhật.

### 11.2. Transaction

Gửi một `Callable` bên trong method `@Transactional` không làm transaction hiện tại tự động truyền sang worker thread. Transaction context thường gắn với thread; task cần transaction riêng nếu nó làm DB work. Ngoài ra, nếu submit trước khi transaction của caller commit, task có thể đọc dữ liệu chưa sẵn sàng hoặc side effect bị lệch khi caller rollback.

Với việc phải xảy ra **sau commit**, cân nhắc `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc outbox pattern theo yêu cầu độ bền. Không để executor làm thay trách nhiệm ordering/consistency của giao dịch.

### 11.3. Security và log context

MDC, `SecurityContext` và `ThreadLocal` của thread gọi không mặc nhiên xuất hiện ở worker. Nếu cần correlation id hoặc principal, truyền những trường cần thiết một cách an toàn hoặc dùng cơ chế context propagation/task decorator được cấu hình đúng. Cần tránh truyền mutable request objects hoặc giữ thông tin bảo mật trong queue lâu hơn cần thiết.

### 11.4. Cancellation và resource cleanup

Task cần tôn trọng interruption khi phù hợp; đóng socket/file/DB resources trong `try-finally` hoặc `try-with-resources`. Với tác vụ đã ghi side effect một phần, cancellation không phục hồi dữ liệu; cần idempotency, transaction hoặc cơ chế bù trừ tùy nghiệp vụ.

## 12. Kiểm thử submit không phụ thuộc vào sleep

Một unit test không nhất thiết phải dùng thread pool thật. Nếu service chỉ cần `AsyncTaskExecutor`, có thể dùng fake executor hoặc implementation đồng bộ phù hợp để kiểm tra việc gửi task. Khi cần kiểm tra concurrency thật, dùng `CountDownLatch` hoặc `Phaser` để kiểm soát các mốc thay vì `Thread.sleep(100)` và hy vọng worker đã chạy.

Trong ví dụ chương trình, hai latch có nhiệm vụ:

- `started` bảo đảm worker đã đến điểm chờ.
- `release` bảo đảm caller kiểm thử nhánh timeout trước khi task được giải phóng.

Mẫu kiểm thử ngắn, yêu cầu một `AsyncTaskExecutor executor` có sẵn:

```java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);

Future<String> task = executor.submit(() -> {
    started.countDown();
    release.await();
    return "done";
});

try {
    if (!started.await(5, TimeUnit.SECONDS)) {
        throw new AssertionError("Worker did not start");
    }

    try {
        task.get(20, TimeUnit.MILLISECONDS);
        throw new AssertionError("Expected timeout");
    } catch (TimeoutException expected) {
        // Đúng: task vẫn chờ release.
    }
} finally {
    release.countDown();
}

if (!"done".equals(task.get(5, TimeUnit.SECONDS))) {
    throw new AssertionError("Unexpected result");
}
```

Đây là **fragment** cần imports `CountDownLatch`, `Future`, `TimeUnit`, `TimeoutException` và xử lý checked exceptions. Task được thả trong `finally` để tránh để worker bị kẹt nếu assert thất bại.

Unit test cho một `Callable<Integer>` thuần không cần Spring context; integration test mới cần kiểm tra bean wiring, pool sizing, rejection, lifecycle và actual threading.

## 13. Các lỗi phổ biến khi dùng submit()

| Sai lầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| Gọi `submit` qua biến `TaskExecutor` | Interface không khai báo `submit` | Tiêm `AsyncTaskExecutor` khi cần `Future` |
| Cho rằng `submit(Runnable).get()` trả giá trị từ lambda | `Runnable.run()` là `void` | Dùng `Callable<T>` để có `T` |
| Submit xong bỏ `Future` nhưng muốn biết task lỗi | Lỗi có thể nằm trong Future mà không có consumer | Quan sát `get` hoặc error reporting phù hợp |
| Gọi `get()` ngay trong servlet/event loop | Caller bị chặn, giảm throughput | Tránh blocking ở đường nhạy latency |
| Dùng `get(timeout)` rồi nghĩ task bị hủy | Timeout chỉ áp dụng cho caller | Quyết định cancellation/cleanup riêng |
| Gọi `cancel(true)` rồi nghĩ chắc chắn đã rollback | Interrupt là tín hiệu; task có thể đã ghi side effect | Thiết kế idempotency, transaction, cleanup |
| Bỏ qua `ExecutionException.getCause()` | Mất nguyên nhân lỗi thật | Phân loại/ghi log cause đúng chỗ |
| Đếm `isDone()==true` là success | Trạng thái done bao gồm lỗi và cancel | Xử lý `get`/`isCancelled` để biết kết quả |
| Submit task con rồi `get()` trong cùng pool nhỏ | Có thể tạo starvation deadlock | Tránh nested blocking, điều chỉnh orchestration |
| Tăng `maxPoolSize` nhưng queue rất lớn | Queue được dùng trước khi mở thread ngoài core | Đo queue wait và chỉnh core/queue/max cùng nhau |
| Dùng `submit` thay cho durable messaging | Future và in-memory queue mất khi process chết | Dùng broker/outbox nếu cần durability |
| Tưởng ThreadLocal/transaction tự truyền sang worker | Thread context thường không chia sẻ | Truyền dữ liệu rõ ràng, cấu hình propagation khi cần |

## 14. Bài tập suy luận

**Bài 1.** Tác vụ sau thuộc kiểu nào và `Future.get()` trả gì?

```java
Runnable r = () -> System.out.println("saved");
Future<?> f = executor.submit(r);
```

Đáp án: đó là `Runnable`. Nếu task hoàn thành bình thường, `f.get()` trả `null`; dòng chữ `saved` là side effect được in ra. Fragment yêu cầu `AsyncTaskExecutor executor` đã được khai báo.

**Bài 2.** Với `Callable<String>` trả `"ok"`, `Future<String>.get()` cho kết quả gì?

Đáp án: trả `"ok"` nếu hoàn thành thành công; nếu task ném exception, caller nhận `ExecutionException`; nếu đang chờ và bị interrupt, caller nhận `InterruptedException`.

**Bài 3.** Caller nhận `TimeoutException` từ `future.get(1, SECONDS)`, sau đó retry gọi cùng tác vụ gửi email. Có chắc email chỉ được gửi một lần?

Không. Future cũ có thể vẫn đang chạy và hoàn tất sau timeout. Nếu cần retry an toàn, sử dụng idempotency key, trạng thái công việc, hoặc giải pháp giao việc bền vững đúng đặc thù nghiệp vụ.

**Bài 4.** Vì sao `Future.isDone()==true` chưa chứng minh task thành công?

Vì trạng thái done cũng bao gồm task thất bại hoặc bị hủy. Cần đọc kết quả hoặc exception bằng `get()` và nhận biết cancellation.

**Bài 5.** Một Spring service chỉ nhận `TaskExecutor` nhưng cần trả `Future<Integer>`. Có nên ép kiểu sang `ThreadPoolTaskExecutor`?

Không. Hãy biểu đạt dependency cần thiết bằng `AsyncTaskExecutor` và cấu hình một bean phù hợp. Điều đó vẫn tách business logic khỏi implementation.

## 15. Checklist áp dụng vào ứng dụng Spring

Trước khi dùng `submit` trong production, kiểm tra:

1. **API:** client cần kết quả hay chỉ side effect? Chọn `Runnable` hoặc `Callable<T>` và interface `AsyncTaskExecutor` đúng khả năng.
2. **Bean:** executor thực tế được tiêm có tên, core/max/queue/rejection và lifecycle phù hợp? Có bị nhầm pool không?
3. **Outcome:** ai đọc `Future`, xử lý `ExecutionException`, `CancellationException`, `TaskRejectedException` và ghi nhận trạng thái cuối?
4. **Timeout:** có giới hạn hợp lý trên Future và trên DB/HTTP bên trong task? Caller timeout thì task còn chạy hay bị hủy theo chính sách nào?
5. **Context:** transaction, security, MDC và dữ liệu input có còn hợp lệ khi worker chạy sau đó?
6. **Concurrency:** có nested blocking hoặc các task phụ thuộc nhau trong cùng pool nhỏ không? Có đủ hạn mức downstream?
7. **Operations:** quan sát active threads, queue size, queue wait, execution time, rejection, error và memory dưới tải thực?
8. **Durability:** tác vụ có bắt buộc tồn tại qua restart hay không? Nếu có, một in-memory executor với Future là chưa đủ.

**Ghi nhớ:** `submit(Runnable)` giúp theo dõi **việc hoàn thành** của hành động không có giá trị trả về, còn `submit(Callable<T>)` giúp theo dõi **một kết quả kiểu T**. Cả hai trả `Future` để caller có thể biết thành công, lỗi, timeout hoặc cancellation; quyền quyết định thực thi, giới hạn tài nguyên và lifecycle vẫn thuộc executor được cấu hình.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — AsyncTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/task/AsyncTaskExecutor.html)
- [Spring Framework 6.2 — ThreadPoolTaskExecutor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Java 21 — Future Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java 21 — ExecutorService Javadoc](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html)