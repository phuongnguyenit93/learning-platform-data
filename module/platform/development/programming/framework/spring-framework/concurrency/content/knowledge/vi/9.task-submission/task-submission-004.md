# `get()` có giới hạn thời gian chờ: nhận kết quả tác vụ trong Spring Framework

## Mục tiêu

Khi gửi một tác vụ cho executor, thread gọi thường nhận một `Future<T>` hoặc `CompletableFuture<T>` trước khi kết quả thực sự sẵn sàng. Nếu gọi `get()` không có giới hạn, thread đang chờ có thể bị giữ rất lâu khi tác vụ bị nghẽn I/O, treo tại lock, chờ hàng đợi hoặc không bao giờ hoàn thành. Java cung cấp biến thể **`get(long timeout, TimeUnit unit)`** để người gọi đặt **thời gian chờ tối đa cho một lần lấy kết quả**.

Bài học tập trung vào cách dùng giới hạn thời gian chờ trong bối cảnh Spring Framework concurrency, nơi tác vụ có thể được gửi bằng `AsyncTaskExecutor`, `ThreadPoolTaskExecutor` hoặc một phương thức `@Async` trả `Future`/`CompletableFuture`.

Sau bài này, bạn sẽ:

1. Đọc đúng hợp đồng của `Future.get(timeout, unit)` và phân biệt nó với `get()` không giới hạn.
2. Xử lý riêng thành công, `TimeoutException`, `ExecutionException`, `InterruptedException` và `CancellationException`.
3. Hiểu rằng **hết thời gian chờ của caller không tự hủy tác vụ ở worker**.
4. Sử dụng `get` có thời hạn với Spring `@Async`, biết luồng nào đang chờ, luồng nào đang xử lý.
5. Phân biệt thời hạn chờ kết quả với timeout của HTTP client/database, timeout của cả request, deadline của một quy trình nhiều tác vụ và `CompletableFuture.orTimeout`.
6. Chọn hành vi sau timeout (trả lỗi, fallback, tiếp tục xử lý nền, hủy có kiểm soát) mà không làm mất kết quả hay giữ tài nguyên vô hạn.

## 1. `Future` là gì và `get()` chờ tại đâu?

`Future<T>` là **đối tượng đại diện cho kết quả của một tính toán có thể chưa hoàn tất**. Nó thường được trả từ `ExecutorService.submit(...)`, `AsyncTaskExecutor.submit(...)` hoặc từ lời gọi Spring `@Async` có kiểu kết quả phù hợp.

```text
Caller thread                   Executor / worker thread
    |                                      |
    | submit task ----------------------->|  tác vụ chạy
    |<------------ Future<T> -------------|
    |                                      |  (có thể còn đang xử lý)
    | future.get(timeout, unit)            |
    |     [caller chờ kết quả]             |
    |                                      |
    |<------------- value / error --------|
    | caller chạy tiếp                     |
```

**Điểm quan trọng:** `get()` được gọi trên thread nào thì **thread ấy chờ**. `get(timeout, unit)` không chuyển việc sang worker mới, không tự tăng kích thước pool và không biến I/O blocking thành non-blocking. Trong Spring MVC, nếu request thread gọi `get(...)`, chính request thread có thể bị chặn trong khoảng chờ.

Một future có thể đã hoàn tất trước khi caller gọi `get`; lúc đó phương thức trả về ngay (hoặc ném lỗi/hủy đã ghi nhận). Giới hạn thời gian chờ **không buộc phải đợi đủ thời hạn**.

## 2. Chữ ký và ý nghĩa của giới hạn

Java 17 định nghĩa trên `java.util.concurrent.Future<V>`:

```java
V get(long timeout, TimeUnit unit)
    throws InterruptedException, ExecutionException, TimeoutException;
```

Ví dụ:

```java
String result = future.get(500, TimeUnit.MILLISECONDS);
```

Diễn giải:

- `500` là độ dài **thời gian chờ cho lần gọi `get` này**, không phải thời lượng tối đa của task tính từ lúc submit.
- `TimeUnit.MILLISECONDS` xác định đơn vị. Có thể dùng `SECONDS`, `MICROSECONDS`, `NANOSECONDS` và các đơn vị khác.
- Nếu kết quả đã hoàn tất thành công, trả về giá trị `V`.
- Nếu chưa có kết quả sau thời gian được phép chờ, ném `TimeoutException`.
- Nếu task thất bại, ném `ExecutionException` với nguyên nhân thực trong `getCause()`.
- Nếu thread **đang chờ** bị interrupt, ném `InterruptedException`.
- Nếu future đã bị cancel, có thể ném `CancellationException` (unchecked).

`get()` không tham số khác ở chỗ có thể chờ đến khi future hoàn thành (hoặc bị interrupt/cancel), **không có deadline đặt bởi caller**. Vì vậy nó không thích hợp khi request có thời hạn nghiêm ngặt mà task có thể bị kẹt.

### Bảng kết quả

| Tình trạng tại hoặc trong khi chờ | `future.get(500, MILLISECONDS)` | Caller nên làm gì? |
| --- | --- | --- |
| Thành công trong thời hạn | Trả `T` | Xử lý kết quả bình thường. |
| Task vẫn chưa hoàn tất khi hết thời hạn | Ném `TimeoutException` | Chọn phản hồi/fallback/cancel; không ngầm coi task đã dừng. |
| Task hoàn tất bằng exception | Ném `ExecutionException` | Xem `getCause()`, ghi nhận và phân loại lỗi nghiệp vụ. |
| Thread chờ bị interrupt | Ném `InterruptedException` | Khôi phục interrupt flag nếu không xử lý ở cấp cao hơn; kết thúc chờ hợp lý. |
| Future bị cancel | Ném `CancellationException` | Xử lý trạng thái hủy; không cố lấy giá trị như thành công. |

Một future có `isDone() == true` có thể là **thành công, lỗi hoặc bị hủy**. `isDone()` không đồng nghĩa “có giá trị thành công”; `isCancelled()` chỉ cho biết đã bị hủy. Giữa việc kiểm tra `isDone()` và xử lý kết quả, trạng thái có thể tiếp tục thay đổi (trừ khi đã hoàn tất); thường nên gọi `get(...)` trực tiếp và xử lý ngoại lệ.

### Vì sao timeout không đồng nghĩa task chậm đúng 500 ms?

Thời hạn bắt đầu khi **caller đi vào lần `get`**, có thể sau khi task đã nằm trong queue một khoảng thời gian. Mặt khác, chỉ bản thân lời gọi chờ được giới hạn; tổng độ trễ còn gồm submit, xây request, CPU scheduling, xử lý ngoại lệ và trả response. Java/OS không cam kết thời điểm thread được lên lịch chạy lại chính xác từng mili giây.

Ví dụ: caller submit một task, làm việc khác 2 giây rồi mới gọi `get(500, MILLISECONDS)`. Nó có thể nhận kết quả ngay nếu task đã hoàn tất; hoặc chờ thêm tối đa khoảng thời hạn này nếu task vẫn chưa xong. **Không thể diễn giải thành “task phải hoàn thành trong 500 ms từ lúc submit”.**

## 3. Spring Framework: gửi task và chờ có giới hạn

Ở cấp interface, Spring cung cấp:

- `TaskExecutor` để gửi `Runnable`.
- `AsyncTaskExecutor` để gửi `Runnable`/`Callable` và nhận handle kết quả theo API hiện hành.
- `ThreadPoolTaskExecutor` để cấu hình pool, queue và lifecycle dưới dạng Spring bean.
- `@EnableAsync` và `@Async` để Spring chuyển thực thi phương thức qua executor khi lời gọi đi qua proxy.

Một phương thức Spring:

```java
@Async("reportExecutor")
public CompletableFuture<String> createReport(String id) {
    return CompletableFuture.completedFuture("report:" + id);
}
```

Đoạn trên **chỉ là minh họa thân phương thức**, giả định đã có Spring bean, `@EnableAsync` và executor tên `reportExecutor`. Khi Spring proxy xử lý `@Async`, thân phương thức thường được thực thi trong executor; caller nhận `CompletableFuture<String>` và có thể chờ bằng:

```java
String value = reportService.createReport("A")
    .get(2, TimeUnit.SECONDS);
```

Nếu caller gọi `get` ngay, caller có thể bị chặn tối đa thời hạn trong khi worker tiếp tục xử lý. `@Async` không làm cho một lời gọi `get` trở thành non-blocking. Nếu caller không muốn chặn, hãy cân nhắc callback/composition hoặc hợp đồng async của lớp gọi.

**Lưu ý proxy:** `this.createReport(...)` bên trong chính bean thường **không** đi qua Spring proxy ở mode mặc định, nên annotation có thể không kích hoạt executor. Cần gọi qua reference bean được Spring quản lý, thường từ một bean khác, và chọn executor rõ bằng `@Async("reportExecutor")` khi ứng dụng có nhiều pool.

## 4. Ví dụ hoàn chỉnh Java 17+ và Spring: timeout không hủy task

Ví dụ sau dùng **Java 17+**, Maven và **Spring Framework 6.2.12**. Nó không cần Spring Boot hoặc máy chủ HTTP. Ta dùng `CountDownLatch` để giữ worker tại một bước chờ có chủ đích, bảo đảm caller gặp `TimeoutException`; sau đó caller mở chốt và lấy được kết quả **từ cùng future**. Nhờ vậy không phải dựa vào `Thread.sleep` hoặc so sánh mili giây thiếu ổn định.

Cấu trúc:

```text
spring-timed-get-demo/
├── pom.xml
└── src/main/java/demo/TimedGetDemo.java
```

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-timed-get-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.TimedGetDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tệp `src/main/java/demo/TimedGetDemo.java`:

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class TimedGetDemo {
    public static class Gates {
        final CountDownLatch started = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
    }

    public static class ReportService {
        private final Gates gates;

        public ReportService(Gates gates) {
            this.gates = gates;
        }

        @Async("reportExecutor")
        public CompletableFuture<String> createReport(String id) {
            gates.started.countDown();

            try {
                gates.release.await();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return CompletableFuture.failedFuture(ex);
            }

            return CompletableFuture.completedFuture("report:" + id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        public Gates gates() {
            return new Gates();
        }

        @Bean
        public ReportService reportService(Gates gates) {
            return new ReportService(gates);
        }

        @Bean("reportExecutor")
        public ThreadPoolTaskExecutor reportExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setCorePoolSize(1);
            pool.setMaxPoolSize(1);
            pool.setQueueCapacity(4);
            pool.setThreadNamePrefix("report-");
            return pool;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            Gates gates = context.getBean(Gates.class);
            ReportService service = context.getBean(ReportService.class);

            CompletableFuture<String> future = service.createReport("A");

            try {
                if (!gates.started.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Worker did not start");
                }

                boolean timeoutObserved = false;
                try {
                    future.get(100, TimeUnit.MILLISECONDS);
                } catch (TimeoutException expected) {
                    timeoutObserved = true;
                }

                System.out.println("timeoutObserved=" + timeoutObserved);
                System.out.println("doneBeforeRelease=" + future.isDone());
            } finally {
                // Quan trọng: không để worker chờ vô hạn nếu main gặp lỗi.
                gates.release.countDown();
            }

            String result = future.get(5, TimeUnit.SECONDS);
            System.out.println("result=" + result);
            System.out.println("doneAfterRelease=" + future.isDone());
        }
    }
}
```

Chạy từ thư mục `spring-timed-get-demo`:

```bash
mvn -q compile exec:java
```

Bốn dòng do chương trình in ra khi chạy bình thường:

```text
timeoutObserved=true
doneBeforeRelease=false
result=report:A
doneAfterRelease=true
```

### Phân tích từng bước

1. Spring context tạo `reportExecutor`, một `ThreadPoolTaskExecutor` chỉ có một worker trong ví dụ. `@EnableAsync` đăng ký cơ chế xử lý `@Async`.
2. `context.getBean(ReportService.class)` lấy bean qua Spring. `service.createReport("A")` đi qua proxy; Spring gửi công việc vào `reportExecutor` và trả một `CompletableFuture<String>` cho caller.
3. Worker vào thân `createReport`, giảm `started` xuống 0 rồi đợi `release`. Main chỉ tiếp tục sau khi `started.await(...)` xác nhận worker đã thực sự bắt đầu, vì vậy không dựa vào may rủi thứ tự lên lịch.
4. Main gọi `future.get(100, TimeUnit.MILLISECONDS)` trong khi worker **không thể hoàn tất** vì chốt `release` chưa mở. Lần chờ này hết hạn và ném `TimeoutException`; main in `timeoutObserved=true`.
5. Ngay trước khi mở chốt, worker vẫn đang đợi. Future chưa hoàn tất nên `doneBeforeRelease=false`. **Timeout không tự cancel future, không nhả chốt và không giết worker.**
6. Khối `finally` mở chốt; worker tạo `CompletableFuture.completedFuture("report:A")` và Spring hoàn tất future trả về cho caller.
7. Main gọi `future.get(5, TimeUnit.SECONDS)` **lần thứ hai trên chính future đó**, nhận `report:A`. Sau khi `get` trả giá trị, future đã hoàn tất nên `doneAfterRelease=true`.

Nếu `started.await` hết hạn hoặc thread bị interrupt, ví dụ chủ động ném lỗi và vẫn mở chốt trong `finally`. Một lỗi môi trường hay executor thất bại có thể làm chương trình không in các dòng trên; output mô tả trường hợp chạy bình thường.

### Vì sao đây là bằng chứng đúng?

- `CountDownLatch` tạo quan hệ phối hợp: caller chỉ chờ future khi worker đã chạy tới điểm kiểm soát.
- Worker không thể tính xong và trả kết quả trước khi main mở `release` (trừ khi cơ chế ngoài ý muốn can thiệp).
- Chờ `get(100, MILLISECONDS)` hết hạn chỉ tác động lên hành vi của **main**, không thay trạng thái hoàn tất của task.
- Lần `get(5, SECONDS)` tiếp theo chứng minh cùng future vẫn có thể nhận kết quả sau một lần timeout.

Trong ứng dụng thật, không dùng latch để mô phỏng I/O hoặc giữ worker dài hạn. Chọn timeout client tương ứng, phân bổ thread pool và bảo vệ số lượng tác vụ đang chạy/chờ.

## 5. Xử lý các ngoại lệ riêng biệt

Mẫu sau áp dụng khi đã có `Future<Result> future`. Đây là **mã minh họa trong một phương thức**, cần định nghĩa kiểu `Result` và `fallback()` theo ứng dụng; không phải một chương trình độc lập:

```java
try {
    Result result = future.get(2, TimeUnit.SECONDS);
    return result;
} catch (TimeoutException ex) {
    // Caller hết ngân sách chờ. Task có thể vẫn đang chạy.
    recordTimeout(ex);
    return fallback();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // giữ yêu cầu dừng của caller
    throw new IllegalStateException("Interrupted while waiting", ex);
} catch (ExecutionException ex) {
    Throwable cause = ex.getCause(); // lỗi thật từ task
    throw new IllegalStateException("Task failed", cause);
} catch (CancellationException ex) {
    throw new IllegalStateException("Task was cancelled", ex);
}
```

`recordTimeout(...)`, `fallback()` và `Result` là thành phần nghiệp vụ cần tự triển khai; nếu không cần fallback, có thể chuyển timeout thành lỗi có kiểm soát. `CancellationException` là unchecked nên không nằm trong danh sách `throws` của `Future.get`, nhưng vẫn nên tính đến nếu ứng dụng cho phép hủy task. Các `catch` trên không bao phủ lỗi submit task từ executor trước khi nhận được future (ví dụ `TaskRejectedException` của Spring).

### TimeoutException: người chờ hết thời gian

Không được mặc định rằng timeout đồng nghĩa:

- Task chưa từng bắt đầu. Nó có thể đang nằm trong queue hoặc đã chạy.
- Task chết hoặc bị cancel. Future thường **vẫn pending**.
- Server bên ngoài đã ngừng xử lý request. Một HTTP call đã gửi có thể vẫn đang chạy.
- Có thể retry an toàn ngay. Task cũ có thể vẫn ghi database sau khi caller đã trả fallback.

Khi timeout, cần chọn rõ chiến lược: tiếp tục xử lý nền và lưu kết quả; trả lỗi/fallback trong khi task vẫn chạy; hoặc cố gắng hủy task và giới hạn tài nguyên. Nếu tác vụ có side effect, phải thiết kế idempotency và xác định xử lý kết quả trễ.

### ExecutionException: task đã thất bại

Một task ném `IllegalStateException` có thể khiến `future.get(...)` ném `ExecutionException` bọc lỗi thật. Quan sát `ex.getCause()`, không nhầm nó với timeout. Khi một `CompletableFuture` kết thúc ngoại lệ, `get` cũng đưa thông tin lỗi qua `ExecutionException`, còn `join` thường dùng `CompletionException` (unchecked).

### InterruptedException: thread đang chờ bị yêu cầu dừng

Nếu thread caller bị interrupt trong khi `get`, Java có thể ném `InterruptedException`; trạng thái interrupted thường đã bị xóa khi exception được ném. Nếu không truyền exception lên tầng trên theo hợp đồng, phục hồi bằng:

```java
catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return; // hoặc thoát phương thức theo hợp đồng của caller
}
```

Đây là snippet, không chạy độc lập. Không nuốt interrupt rồi tiếp tục vòng lặp chờ vô hạn. Cũng cần phân biệt **caller bị interrupt** với **worker bị interrupt**: hai thread có vòng đời và ý nghĩa khác nhau.

### CancellationException: task/future bị hủy

Một future bị hủy có thể khiến `get(...)` ném `CancellationException`. `isDone()` vẫn là `true` vì hủy cũng là một trạng thái hoàn tất của future. Nếu cancel đến từ deadline hoặc người dùng, ghi trạng thái hủy một cách tường minh.

## 6. `get(timeout)` không phải `cancel()`

Hai thao tác khác nhau:

| Thao tác | Tác động chính | Điều không được suy diễn |
| --- | --- | --- |
| `get(200, MILLISECONDS)` | Caller chờ kết quả không quá thời hạn định cho lần lấy đó. | Không dừng task, không ngắt worker, không rollback. |
| `future.cancel(false)` | Cố yêu cầu hủy future; với một số implementation có thể ngăn task chưa chạy bắt đầu. | Không buộc tác vụ đang chạy dừng ngay. |
| `future.cancel(true)` | Cố hủy và có thể yêu cầu interrupt worker nếu implementation hỗ trợ. | Không bảo đảm thread dừng, I/O dừng hay side effect được hoàn tác. |
| `future.isCancelled()` | Quan sát trạng thái hủy của future. | Không chứng minh tài nguyên bên ngoài đã sạch. |

Ví dụ Java `ExecutorService.submit(Callable)` thường trả `FutureTask` có khả năng cố interrupt worker nếu `cancel(true)` thành công. Tuy nhiên, `CompletableFuture.cancel(true)` theo hợp đồng của JDK không dùng `mayInterruptIfRunning` để điều khiển xử lý: việc hoàn tất future bằng trạng thái hủy **không bảo đảm ngắt công việc nền**. Một future nhận qua Spring `@Async` còn có lớp proxy/adaptation, nên không nên xây hệ thống dựa trên giả định cancel luôn ngắt một thread cụ thể.

Nếu chọn hủy sau timeout:

```java
try {
    return future.get(500, TimeUnit.MILLISECONDS);
} catch (TimeoutException ex) {
    boolean requested = future.cancel(true);
    // Ghi trạng thái và xử lý side effect có thể đã xảy ra.
    throw new IllegalStateException(
        "Timed out; cancel requested=" + requested, ex);
}
```

Đây là snippet trong phương thức có kiểu trả về phù hợp, không phải chương trình độc lập. **`cancel(true)` là yêu cầu best-effort**, không thay thế client-side request timeout, transaction design, idempotency hoặc kiểm tra trạng thái job.

Với nghiệp vụ có giá trị cao, đôi khi tiếp tục chạy nền và trả `202 Accepted` kèm job ID có thể hợp lý hơn việc tự động cancel, nhưng phải có job status bền vững để người gọi kiểm tra. Ngược lại, tác vụ chỉ để phục vụ request hiện tại có thể nên dừng hợp tác khi caller không cần kết quả nữa.

## 7. Ba loại timeout không nên đánh đồng

### A. Thời gian chờ kết quả của caller

```java
String value = future.get(300, TimeUnit.MILLISECONDS);
```

Giới hạn **một lần lấy kết quả** ở caller. Task có thể đã tốn thời gian nằm trong queue trước đó, và có thể tiếp tục chạy sau khi caller timeout.

### B. Timeout của thao tác I/O bên trong worker

Ví dụ một HTTP client blocking có thể cần connect timeout và response/read timeout; một truy vấn database có thể cần query timeout hoặc transaction timeout phù hợp. Nếu I/O có thể treo lâu, `future.get(300, MILLISECONDS)` chỉ giải phóng caller khỏi **lần chờ ấy**; worker vẫn có thể bị chiếm lâu, làm bão hòa pool.

Cần cấu hình timeout ở **tài nguyên thực sự gây chờ**, đồng thời đặt giới hạn số worker, queue, connection và retry.

### C. Deadline của cả request hoặc cả quy trình

Giả sử một API có ngân sách tổng 1 giây, nhưng phải submit 3 task và lấy từng kết quả. Gọi mỗi `future.get(1, SECONDS)` tuần tự có thể chờ gần 3 giây, chưa tính submit, queue và mã khác.

Nếu cần một **deadline chung**, hãy ghi nhận thời điểm bắt đầu bằng đồng hồ monotonic (`System.nanoTime()`), tính thời gian còn lại trước mỗi lần chờ rồi dùng nó. Không đặt lại full timeout cho mỗi bước. Nếu deadline đã qua, quyết định trả lỗi hoặc fallback thay vì vô tình mở thêm ngân sách.

Mẫu minh họa trong một phương thức có `List<Future<String>> futures`:

```java
long budgetNanos = TimeUnit.MILLISECONDS.toNanos(800);
long deadlineNanos = System.nanoTime() + budgetNanos;

List<String> results = new ArrayList<>();
for (Future<String> future : futures) {
    long remainingNanos = deadlineNanos - System.nanoTime();
    if (remainingNanos <= 0) {
        throw new TimeoutException("Overall deadline exceeded");
    }
    results.add(future.get(remainingNanos, TimeUnit.NANOSECONDS));
}
```

Mẫu này chỉ minh họa **ngân sách chờ chung**; cần import `List`, `ArrayList`, `Future`, `TimeUnit`, `TimeoutException` và xử lý checked exceptions. Nếu deadline phải bao gồm cả thời gian khởi tạo/submit, hãy tính `deadlineNanos` **trước** các thao tác đó. Khoảng deadline dùng trong ví dụ đủ nhỏ so với giới hạn đo của `nanoTime`; với thời hạn cực lớn, cần xử lý phép tính có thể tràn. Sau khi hết hạn, các future chưa hoàn tất vẫn có thể tiếp tục chạy.

`System.nanoTime()` dùng để đo khoảng thời gian, phù hợp hơn `System.currentTimeMillis()` cho deadline nội bộ vì clock wall time có thể bị điều chỉnh. Còn deadline truyền qua hệ thống phân tán cần hợp đồng rõ về múi giờ, clock skew và thời điểm hết hạn.

## 8. `CompletableFuture` có những lựa chọn khác nào?

`CompletableFuture<T>` triển khai `Future<T>` nên có `get(timeout, unit)`, nhưng còn hỗ trợ composition:

| API | Hành vi | Tác động lên future |
| --- | --- | --- |
| `future.get(timeout, unit)` | Caller chờ có giới hạn rồi lấy kết quả hoặc ném lỗi. | Không chủ động hoàn tất/hủy future khi hết hạn. |
| `future.get()` | Caller chờ không đặt hạn mức riêng. | Không chủ động hủy. |
| `future.join()` | Caller chờ tương tự `get()` không giới hạn nhưng lỗi theo dạng unchecked như `CompletionException`. | Không có tham số timeout. |
| `future.orTimeout(timeout, unit)` | Lên lịch hoàn tất future **bằng `TimeoutException`** nếu nó vẫn chưa hoàn tất khi hết thời hạn. | Thay trạng thái hoàn tất của chính `CompletableFuture` và trả cùng future; task nền có thể vẫn chạy. |
| `future.completeOnTimeout(value, timeout, unit)` | Lên lịch hoàn tất bằng giá trị dự phòng nếu còn pending khi hết hạn. | Cũng thay completion của chính future; không tự dừng worker. |
| `future.thenApply(...)` | Biến đổi giá trị sau khi hoàn tất. | Tạo dependent stage, tránh chờ trực tiếp trên caller. |
| `future.whenComplete(...)` | Quan sát thành công hoặc lỗi. | Có thể dùng để log/metrics; không tự tạo phương thức hủy. |

Ví dụ:

```java
CompletableFuture<String> result = service.createReport("B")
    .orTimeout(2, TimeUnit.SECONDS);
```

Đây là snippet dùng `ReportService` có trong ví dụ chính nhưng không độc lập; `orTimeout` có thể làm future kết thúc bằng lỗi timeout, khiến lần `get` sau ném `ExecutionException` với nguyên nhân `TimeoutException`, trong khi `join` thường ném `CompletionException`. Sự hoàn tất bằng timeout có thể xảy ra **trước** khi phương thức worker thật kết thúc; hoàn tất future không đồng nghĩa đã giải phóng mọi thread.

**Chọn API theo ý định:** `get(timeout)` phù hợp khi *một caller cụ thể* chỉ được chờ chừng đó; `orTimeout` phù hợp khi muốn chính completion stage có chính sách timeout. Nếu một future được nhiều consumer dùng chung, việc gọi `orTimeout` hoặc `completeOnTimeout` trên nó thay đổi kết quả mà mọi consumer cùng thấy. Nếu muốn giới hạn thời gian của một nhánh mà giữ future gốc, cần thiết kế một stage/adapter khác có hợp đồng riêng và cân nhắc side effect.

## 9. Vấn đề thực tế trong Spring MVC và background jobs

Một controller Servlet gọi:

```java
String report = reportService.createReport("X")
    .get(500, TimeUnit.MILLISECONDS);
```

đang **chặn request thread** trong tối đa thời hạn chờ. Nếu quá tải, hàng trăm HTTP request cùng chờ có thể giữ rất nhiều servlet threads; dù task nằm ở executor khác, HTTP capacity vẫn bị ảnh hưởng. Đoạn trên là snippet trong controller có xử lý ngoại lệ, không phải chương trình độc lập.

Nếu muốn cho Spring MVC quản lý vòng đời HTTP request bất đồng bộ, có thể dùng các kiểu trả về được hỗ trợ như `Callable<T>`, `DeferredResult<T>` hoặc `CompletionStage<T>`/`CompletableFuture<T>` theo phiên bản và cấu hình. Lúc đó timeout của async HTTP request là một **lớp chính sách khác**; cần xét trạng thái của task nền, response timeout và client disconnect. Việc trả `Future` cho MVC cũng không tự làm I/O bên trong worker non-blocking.

Với background job, caller có thể không cần kết quả ngay. Dùng `Future.get` có timeout chỉ để trả một response tạm thời có thể dẫn tới **kết quả đến muộn**. Nếu job tạo hiệu ứng phụ, nên ghi nhận `jobId`, status, thời điểm hết hạn, idempotency key, và nơi lưu kết quả. Một thread pool cùng queue trong RAM không bảo đảm job sống sót qua restart.

Ví dụ workflow:

```text
POST /reports
   -> kiểm tra idempotency key
   -> lưu job record (PENDING)
   -> gửi task/queue
   -> trả job ID (202 Accepted)

GET /reports/{jobId}
   -> đọc trạng thái PENDING/RUNNING/SUCCEEDED/FAILED
```

Đây là **sơ đồ kiến trúc**, không phải mã API được triển khai trong ví dụ. Nó minh họa lựa chọn khác khi business không yêu cầu caller chờ kết quả đồng bộ.

## 10. Thiết kế timeout hợp lý và các lỗi phổ biến

### Chọn ngân sách theo toàn đường đi

Khi có request deadline, phân bổ cho queue wait, connect, read, xử lý nghiệp vụ, serialization và overhead. Ví dụ client HTTP đặt deadline 1 giây nhưng server gọi `future.get(5, SECONDS)` có thể tiếp tục chờ sau khi client đã bỏ cuộc; cần thiết kế hạn mức ở từng tầng phù hợp.

Đừng chọn `get(timeout)` dài hơn mọi lớp timeout khác mà không có lý do. Ngược lại, timeout quá ngắn có thể gây fallback hoặc retry không cần thiết trong lúc worker sắp hoàn thành; đo p95/p99 và tỷ lệ false timeout để điều chỉnh.

### Tránh timeout lặp nhiều lần thành vô hạn

Mẫu sai:

```java
while (true) {
    try {
        return future.get(100, TimeUnit.MILLISECONDS);
    } catch (TimeoutException ignored) {
        // Lặp mãi: mỗi lần tự cấp thêm 100 ms chờ.
    }
}
```

Nếu không có deadline chung hoặc điều kiện dừng, caller có thể chờ vô hạn dù mỗi lần `get` có timeout. Polling định kỳ chỉ có giá trị khi có mục đích cụ thể như cập nhật tiến độ và có deadline tổng.

### Không thay thế kiểm soát tài nguyên bằng timeout ở caller

Nếu worker treo do HTTP client không timeout, caller bỏ chờ không giải phóng worker. Hệ thống có thể tiếp tục đầy pool và queue. Đặt giới hạn executor, timeout của I/O, retry có ngân sách và quan sát health của downstream. Với `CallerRunsPolicy`, khi bão hòa task có thể chạy ngay trên caller, vì vậy **ngay cả lúc submit** cũng có thể gây chặn trước khi có future.

### Không bỏ qua exception và interrupt

Bắt chung `Exception` rồi trả về `null` khiến người gọi không biết đó là timeout, hủy hay lỗi nghiệp vụ. Đặc biệt, `InterruptedException` thường cần được truyền đi hoặc phục hồi cờ interrupt để shutdown/cancel ở tầng trên còn tác dụng. Chọn fallback cũng cần thể hiện “không có kết quả đúng hạn”, tránh coi nó là dữ liệu thành công có thể dùng để ghi database.

### Không coi `isDone()` là “task thành công”

`future.isDone()` trả `true` cả khi bị hủy hoặc thất bại. Hãy thử lấy kết quả theo hợp đồng, quan sát ngoại lệ và trạng thái tương ứng. `isCancelled()` cũng không xác nhận tác vụ đã dừng mọi side effect.

### Không dựa vào `Thread.sleep` để chứng minh timeout

Nếu ví dụ dùng `Thread.sleep(200)` và `get(100, MILLISECONDS)`, sự chậm trễ của scheduler hoặc tài nguyên môi trường có thể làm quan sát không ổn định. Ví dụ trong bài dùng `CountDownLatch` để chứng minh có kiểm soát. Với test sản phẩm, cân nhắc test double, đồng hồ điều khiển được hoặc latch/phaser thay vì chờ may rủi.

## 11. Checklist khi đọc code `get(timeout)` trong dự án

1. **Future đến từ đâu?** `ExecutorService.submit`, Spring `AsyncTaskExecutor`, `@Async` proxy, hay API khác? Executor có thể chạy đồng bộ và có chính sách từ chối gì?
2. **Ai đang gọi `get`?** Thread Servlet, `main`, worker của pool hay callback? Nó có được phép block và chịu được bao lâu?
3. **Thời hạn bắt đầu khi nào?** Tính từ lúc gọi `get` hay từ deadline toàn request? Có thời gian queue đã mất trước đó chưa?
4. **Nếu chờ hết hạn, task đi đâu?** Tiếp tục chạy, bị cancel best-effort, ghi kết quả trễ hay để lại side effect?
5. **Lỗi được phân biệt chưa?** Timeout, task failure, interrupt, cancel, reject khi submit đều có đường xử lý rõ ràng?
6. **I/O thật có timeout chưa?** HTTP/database/lock có thể giữ worker dù caller đã dừng chờ không?
7. **Có nhiều bước tuần tự không?** Dùng ngân sách deadline chung để tránh cộng dồn nhiều lần `get(timeout)`.
8. **Có thể bỏ chặn caller không?** Trong đường HTTP hoặc pipeline dài, có thể dùng composition, Spring MVC async, job status hoặc queue bền vững thay vì chờ trực tiếp.
9. **Có khả năng quan sát không?** Đo queue wait, task duration, count timeout, exception cause, cancellation và số worker bị chiếm; log cần correlation ID và cleanup khi truyền qua thread.
10. **Tính đúng đắn khi kết quả đến muộn?** Tác vụ cũ có thể tiếp tục update dữ liệu sau khi caller retry; dùng idempotency, version/transaction và chính sách giải quyết trùng lặp.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `future.get(300, MILLISECONDS)` ném `TimeoutException`. Future có nhất thiết đã chuyển thành cancelled không?

**Đáp án:** Không. Đây là hết thời gian chờ **của caller**. Future có thể vẫn pending và worker vẫn chạy. Có thể thử lại `get` sau đó hoặc chọn chiến lược hủy riêng.

**Câu 2.** Một task đã được submit 2 giây trước, caller bây giờ mới gọi `get(100, MILLISECONDS)`. Điều này đặt deadline task tại thời điểm submit + 100 ms không?

**Đáp án:** Không. Giới hạn áp dụng từ khi thực hiện lần `get` này; nếu task đã hoàn tất, `get` trả ngay.

**Câu 3.** Vì sao `future.get(1, SECONDS)` ba lần tuần tự không tự tạo deadline chung 1 giây?

**Đáp án:** Mỗi lần chờ có ngân sách riêng; thời gian chờ có thể cộng dồn. Cần lưu deadline chung bằng đồng hồ monotonic và chỉ truyền thời gian còn lại cho các lần `get` tiếp theo.

**Câu 4.** `get` ném `ExecutionException`. Đây có phải một lần timeout không?

**Đáp án:** Không. Task đã hoàn tất bằng lỗi; hãy xét `ex.getCause()`. Timeout của `get` có ngoại lệ riêng `TimeoutException`.

**Câu 5.** Caller bị interrupt khi đang chờ `Future.get`. Có thể bắt `InterruptedException` rồi tiếp tục chờ mãi không?

**Đáp án:** Không nên. Hãy truyền signal lên hoặc phục hồi interrupt flag và thoát theo hợp đồng để tác vụ shutdown/cancel không bị bỏ qua.

**Câu 6.** `future.cancel(true)` có bảo đảm worker dừng và HTTP request bên ngoài được hủy không?

**Đáp án:** Không. Khả năng interrupt phụ thuộc loại future/executor và hợp tác của tác vụ; `CompletableFuture.cancel(true)` không nhất thiết ngắt computation.

**Câu 7.** Trong demo, tại sao lần `get(5, SECONDS)` thứ hai trả được `report:A` sau khi lần đầu đã timeout?

**Đáp án:** Lần timeout đầu không hủy future. Khi main mở chốt, worker hoàn thành và Spring hoàn tất handle của caller, nên lần `get` sau nhận kết quả.

**Câu 8.** Spring MVC controller gọi `@Async` service rồi `get(500, MILLISECONDS)` ngay. Controller thread có được giải phóng để xử lý request khác trong lúc chờ không?

**Đáp án:** Không. Chính controller thread bị chặn bởi `get`; muốn giải phóng nó cần dùng hợp đồng request async của MVC hoặc thiết kế API khác.

### Ghi nhớ

`Future.get(timeout, unit)` là **giới hạn cho một lần caller chờ kết quả**, không phải công cụ tự dừng tác vụ. Thiết kế đúng phải làm rõ **caller được chờ bao lâu, worker có thể chạy bao lâu, khi nào cần hủy, khi nào cho phép kết quả muộn, và lỗi/side effect được xử lý thế nào**. Trong Spring, luôn xét cả executor, proxy `@Async`, vòng đời HTTP và tài nguyên ở bên dưới.

### Tài liệu tham khảo chính thức

- [Java 17 — Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get(timeout, unit)`, trạng thái và ngoại lệ.
- [Java 17 — CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `orTimeout`, `completeOnTimeout`, `join`, `cancel`.
- [Java 17 — TimeUnit API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/TimeUnit.html): đơn vị thời gian và chuyển đổi.
- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `TaskExecutor`, `@EnableAsync`, `@Async` và executor qualification.
