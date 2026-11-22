# Giới hạn đồng thời của SimpleAsyncTaskExecutor

## 1. Mục tiêu và tình huống cần giải quyết

`SimpleAsyncTaskExecutor` là một triển khai `AsyncTaskExecutor` của Spring Framework. Mỗi lần nhận một tác vụ, nó tạo **một thread mới** để chạy tác vụ đó; nó **không duy trì pool để tái sử dụng thread**. Vì thế, nếu một ứng dụng nhận nhiều tác vụ chậm cùng lúc, số thread và số tác vụ đang thực thi có thể tăng nhanh. Giới hạn đồng thời (*concurrency limit*) cho phép đặt một trần trên **số lần thực thi tác vụ đang hoạt động tại một thời điểm** của chính executor này.

Ví dụ một dịch vụ chỉ chịu được tối đa 8 yêu cầu bên ngoài thực thi đồng thời. Nếu ứng dụng nhận 50 tác vụ gần như cùng lúc, không nên mặc định tạo 50 tác vụ đang chạy để gọi dịch vụ đó. Có thể cấu hình:

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor("remote-");
executor.setConcurrencyLimit(8);
```

Đây là snippet cấu hình, cần có Spring Framework trên classpath. Với giới hạn 8, executor điều phối để không quá 8 tác vụ mà **nó** đang thực thi đồng thời. Tác vụ thứ 9 không mặc nhiên được đưa vào hàng đợi riêng. **Theo chính sách mặc định, thread gọi `execute(...)` bị chặn cho đến khi một suất thực thi trống.** Từ Spring Framework 6.2.6, có thể chọn từ chối ngay thay vì chặn caller.

Bài này làm rõ cơ chế giới hạn, hai chính sách khi chạm trần, cách tích hợp với `@Async`, ảnh hưởng của platform/virtual threads, khi nào nên dùng và lúc nào cần đổi sang executor có pool cùng hàng đợi.

## 2. Nắm đúng mô hình thực thi trước khi đặt limit

### 2.1. Mỗi tác vụ tạo thread riêng

Khi gọi:

```java
executor.execute(() -> handleRequest());
```

`SimpleAsyncTaskExecutor` tạo một thread mới cho tác vụ được chấp nhận. Sau khi tác vụ kết thúc, thread đó kết thúc, **không quay về pool để phục vụ tác vụ tiếp theo**. Một concurrency limit dương chỉ giới hạn số tác vụ có thể chạy đồng thời; nó **không biến executor thành thread pool**.

Phân biệt các thông số:

| Thuật ngữ | Ý nghĩa với `SimpleAsyncTaskExecutor` |
| --- | --- |
| Số tác vụ được chấp nhận | Tác vụ đã vượt qua bước giới hạn và được executor khởi chạy |
| Số tác vụ đồng thời | Số tác vụ còn đang thực thi, bị khống chế bởi `concurrencyLimit` nếu cấu hình dương |
| Số thread được tạo qua thời gian | Có thể rất lớn vì mỗi tác vụ mới lại tạo thread, kể cả khi limit nhỏ |
| Hàng đợi nội bộ | **Không có task queue kiểu `ThreadPoolExecutor`** để tích lũy công việc chờ |
| Thread gọi `execute` | Có thể **bị chặn** khi limit đầy theo cấu hình mặc định |
| Nhiều instance ứng dụng | Mỗi executor ở mỗi JVM giữ giới hạn riêng; không tạo hạn mức toàn cluster |

Đặt `setConcurrencyLimit(1)` có nghĩa là tại mỗi thời điểm chỉ có tối đa **một** tác vụ thực thi qua executor đó. Nó không có nghĩa rằng **cùng một thread** sẽ xử lý mọi tác vụ; các lần thực thi vẫn dùng những thread được tạo mới.

### 2.2. Diễn tiến khi concurrencyLimit = 2

Giả sử cả A, B và C đều mất 5 giây; A và B đã chạy:

```text
Thời điểm    Task A      Task B      Task C             Thread nộp C
t0           đang chạy   đang chạy   chưa được nhận    gọi execute(C)
t0..t5       đang chạy   đang chạy   chưa được nhận    bị chặn vì đủ 2 suất
t5           kết thúc    đang chạy   được nhận         execute(C) mới trả về
t5..         xong        đang chạy   chạy trên thread  tiếp tục việc của caller
                                    mới
```

Đây là dòng thời gian minh họa, không phải một lịch chạy được bảo đảm: A/B có thể kết thúc khác lúc, caller khác có thể chiếm suất trước, và hệ điều hành quyết định lúc thread mới được lập lịch.

Điểm mấu chốt: **cái đang chờ là lời gọi nộp tác vụ**, chứ không phải một task đã nằm sẵn trong hàng đợi executor. Chặn ở cổng nộp việc có thể tạo *backpressure* đơn giản, nhưng cũng khiến request thread, scheduled thread hoặc thread của consumer bị giữ lại.

Nếu sử dụng `@Async`, lời gọi từ bean khác được Spring gửi vào executor. Khi executor đang chạm giới hạn với chính sách chặn, **bản thân lời gọi phương thức được đánh dấu `@Async` vẫn có thể bị chặn ở bước submit**. Vì vậy, annotation không bảo đảm caller luôn trở lại ngay lập tức trong điều kiện quá tải.

## 3. Các thiết lập và giá trị biên cần hiểu

Các API dưới đây được xác nhận với Spring Framework **6.2.10**. Phần có ghi rõ “từ 6.2.6” không áp dụng cho mọi bản 6.0, 6.1 hoặc 6.2 cũ hơn.

| API / giá trị | Hành vi |
| --- | --- |
| `setConcurrencyLimit(n)` với `n > 0` | Giới hạn tối đa `n` task thực thi đồng thời trên executor này |
| `setConcurrencyLimit(1)` | Cho phép tối đa một task chạy mỗi lúc; vẫn tạo thread mới cho từng task |
| Mặc định `-1` / `UNBOUNDED_CONCURRENCY` | **Không giới hạn đồng thời**; đây là trạng thái mặc định |
| `0` / `NO_CONCURRENCY` | Tắt khả năng chấp nhận thực thi đồng thời; **không dùng 0 để biểu diễn chạy tuần tự**, hãy dùng 1 |
| `getConcurrencyLimit()` | Đọc giá trị giới hạn đã cấu hình |
| `isThrottleActive()` | Cho biết chế độ throttle có được bật, **không phải** số tác vụ đang chạy hay trạng thái đã đầy |
| `setRejectTasksWhenLimitReached(false)` | **Mặc định:** chặn thread nộp việc cho đến khi có chỗ |
| `setRejectTasksWhenLimitReached(true)` | **Từ 6.2.6:** khi đầy thì từ chối ngay bằng `TaskRejectedException` |
| `setVirtualThreads(true)` | **Từ Spring 6.1, JDK 21+:** tạo virtual thread thay cho platform thread; không tự bỏ giới hạn |
| `setTaskTerminationTimeout(ms)` | **Từ Spring 6.1:** thiết lập thời gian chờ kết thúc task khi `close()`; có chi phí theo dõi task |

**Lưu ý thay đổi cấu hình lúc runtime:** nên coi concurrency limit là cấu hình ở thời điểm tạo executor. API nền `ConcurrencyThrottleSupport` cảnh báo không đổi qua lại giữa `-1` và một giới hạn cụ thể khi đang chạy, vì trạng thái đếm concurrency có thể không nhất quán. Nếu cần đổi hạn mức động, hãy thiết kế và kiểm thử cơ chế quản trị riêng thay vì sửa tùy tiện giữa lúc nhiều task đang hoạt động.

### 3.1. Trường hợp để mặc định `-1`

Với platform threads, nhiều tác vụ dài/đợi I/O có thể tạo nhiều thread, dùng bộ nhớ stack, tài nguyên scheduler và gây áp lực lên CPU. Với virtual threads, chi phí thread thường thấp hơn nhưng **số truy vấn DB, HTTP requests, file descriptors, downstream quota, bộ nhớ ứng dụng và công việc đang chờ vẫn có giới hạn thật**.

Không có “giới hạn an toàn mặc định” áp dụng cho mọi workload. Nếu dùng `SimpleAsyncTaskExecutor` trong đường xử lý có lưu lượng lớn, phải biết mức tải dự kiến và cách hệ thống chống quá tải.

### 3.2. Giới hạn không đồng nghĩa với timeout

`setConcurrencyLimit(8)` **không** quy định tác vụ phải hoàn thành trong một thời gian nhất định và cũng **không** tự đặt thời gian chờ cho HTTP client, JDBC hoặc I/O. Nếu tám tác vụ đang chạy bị treo vô thời hạn, caller thứ chín có thể tiếp tục chờ theo chế độ blocking.

Cần phân biệt ba timeout khác nhau:

1. **Submission wait:** thời gian caller chờ được nhận vào executor khi đã đủ suất; `SimpleAsyncTaskExecutor` không cung cấp một queue-wait timeout cấu hình trực tiếp qua `setConcurrencyLimit`.
2. **Execution timeout:** thời gian tối đa mà tác vụ hoặc dependency được phép hoạt động; cần đặt ở API phù hợp như HTTP client, JDBC, hoặc cơ chế deadline/cancellation có kiểm soát.
3. **Termination timeout:** `setTaskTerminationTimeout` phục vụ **đóng executor**, không phải timeout cho mỗi task lúc đang chạy.

## 4. Hai chính sách khi chạm giới hạn: chặn caller và từ chối ngay

### 4.1. Mặc định: block người nộp việc

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor("blocking-");
executor.setConcurrencyLimit(2);
// Không bật setRejectTasksWhenLimitReached(true): giữ mặc định false.
```

Nếu hai task đang chiếm hai suất, lời gọi `executor.execute(thirdTask)` sẽ chờ cho đến khi có suất trống. Điều này giúp không cho số task đang chạy vượt quá giới hạn nhưng **không tạo hàng đợi được quản lý riêng**.

Ưu điểm: đơn giản cho luồng nộp việc chấp nhận chờ, tạo sức ép ngược để giảm tốc độ submit.

Rủi ro: một HTTP request đang cần trả lời, event-loop, job scheduler, hoặc message consumer có thể bị chặn bất ngờ. Nếu task bên trong executor đang đợi một công việc được nộp lại vào **cùng executor** mà limit đã đầy, có thể xảy ra deadlock hoặc chuỗi chờ kéo dài. Không gọi `execute` theo kiểu lồng rồi chờ kết quả mà không tính công suất còn lại.

### 4.2. Từ Spring 6.2.6: reject ngay khi đầy

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor("reject-");
executor.setConcurrencyLimit(2);
executor.setRejectTasksWhenLimitReached(true);
```

Khi cả hai suất đang bận, submission mới sẽ ném `org.springframework.core.task.TaskRejectedException`. Ngoại lệ này kế thừa `java.util.concurrent.RejectedExecutionException`. Caller cần có chính sách rõ: trả lỗi quá tải, yêu cầu retry sau, điều tiết đầu vào, hoặc chuyển việc sang một queue/job store đáng tin cậy tùy nghiệp vụ. **Không coi việc reject là tác vụ đã được lưu và sẽ tự chạy lại.**

Cơ chế reject này có mặt từ **Spring Framework 6.2.6**. Nếu dự án chạy Spring Framework 6.2.5 hoặc cũ hơn, không sao chép phương thức `setRejectTasksWhenLimitReached(true)` mà chưa nâng phiên bản/kiểm tra API.

### 4.3. Bảng chọn chính sách

| Yêu cầu | Gợi ý |
| --- | --- |
| Một batch producer kiểm soát được tốc độ, chấp nhận đợi | Concurrency limit dương và chính sách **block** có thể đủ |
| API HTTP cần phát hiện quá tải nhanh | Cân nhắc **reject**, xử lý lỗi tại biên HTTP; tránh giữ servlet/event-loop thread lâu |
| Muốn chờ trong một queue có kích thước, số worker ổn định | Dùng `ThreadPoolTaskExecutor` với pool/queue/rejection policy thiết kế rõ |
| Tác vụ bắt buộc tồn tại sau restart, retry có idempotency | Dùng job store, message broker, outbox hoặc hệ thống xử lý nền bền vững |
| Muốn giới hạn tổng số call đến downstream trên nhiều pod | Hạn mức/concurrency control dùng chung hoặc giới hạn tại downstream; giới hạn local không đủ |

## 5. Ví dụ chạy được: một suất thực thi và từ chối task thứ hai

Ví dụ độc lập dùng **Java 17 + Maven + Spring Framework 6.2.10**. Nó chứng minh tình huống đã có một task đang chiếm suất, task thứ hai bị từ chối ngay trong **chế độ reject**. `CountDownLatch` giữ task đầu tiên còn hoạt động để kết quả không phụ thuộc vào may rủi thread scheduling.

Tạo cây tệp:

```text
simple-executor-limit/
├── pom.xml
└── src/main/java/demo/LimitDemo.java
```

**Tệp `pom.xml`:**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>simple-executor-limit</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-core</artifactId>
            <version>6.2.10</version>
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
                <configuration>
                    <mainClass>demo.LimitDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**Tệp `src/main/java/demo/LimitDemo.java`:**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import org.springframework.core.task.SimpleAsyncTaskExecutor;
import org.springframework.core.task.TaskRejectedException;

public final class LimitDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        CountDownLatch firstFinished = new CountDownLatch(1);

        try (SimpleAsyncTaskExecutor executor =
                     new SimpleAsyncTaskExecutor("limited-")) {
            executor.setConcurrencyLimit(1);
            executor.setRejectTasksWhenLimitReached(true);

            executor.execute(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                } finally {
                    firstFinished.countDown();
                }
            });

            try {
                if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("First task did not start");
                }

                System.out.println("limit=" + executor.getConcurrencyLimit());
                System.out.println("throttle=" + executor.isThrottleActive());

                boolean rejected = false;
                try {
                    executor.execute(() ->
                            System.out.println("UNEXPECTED SECOND TASK"));
                } catch (TaskRejectedException ex) {
                    rejected = true;
                }
                System.out.println("secondRejected=" + rejected);
            } finally {
                // Luôn giải phóng worker, kể cả khi phần kiểm tra thất bại.
                releaseFirst.countDown();
                if (!firstFinished.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("First task did not finish");
                }
            }

            System.out.println("firstFinished=true");
        }
    }
}
```

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn -q compile exec:java
```

**Standard output từ chương trình:**

```text
limit=1
throttle=true
secondRejected=true
firstFinished=true
```

Tại sao kết quả xác định?

1. Trước khi thử submit task thứ hai, main thread đã đợi `firstStarted`: task thứ nhất đã bắt đầu và đang chờ `releaseFirst`.
2. `concurrencyLimit=1` nên không còn suất. Chính sách `setRejectTasksWhenLimitReached(true)` khiến lời gọi `execute` thứ hai ném `TaskRejectedException` ngay ở nơi submit.
3. Mệnh đề catch đặt `rejected=true`, vì vậy `UNEXPECTED SECOND TASK` không được in.
4. Khối `finally` giải phóng task thứ nhất và đợi `firstFinished`, không để ví dụ treo worker.

Đây là ví dụ **độc lập**, không cần chạy Spring Boot application context; lớp `SimpleAsyncTaskExecutor` có thể được khởi tạo trực tiếp khi đã có thư viện Spring trên classpath. Kết quả nói về **chế độ reject**; nếu bỏ dòng bật reject, lời gọi `execute` thứ hai trong main sẽ **bị chặn** trong khi task thứ nhất vẫn chờ main mở latch. Vì main không tới được `finally` để mở latch, ví dụ sẽ bị deadlock. Do đó **không xóa dòng reject và chạy nguyên ví dụ khi muốn thử blocking**.

### Nếu cần kiểm tra hành vi blocking an toàn

Dùng **một thread riêng làm submitter**, và để thread điều phối (không bị chặn) chịu trách nhiệm mở latch của task đang giữ suất:

```text
main:       submit task A -> chờ A bắt đầu -> mở submitter -> sau đó mở latch A
task A:     bắt đầu -> chờ latch -> hoàn thành, nhả suất
submitter:  execute(task B) -> bị chặn khi A giữ suất -> hết chặn -> trở lại
task B:     được chấp nhận, chạy trên thread mới
```

Cách này tránh vòng chờ “main bị chặn khi submit B; A lại đợi main mở latch”. Không dùng một phép `sleep(100)` rồi kết luận đã chứng minh điều kiện race; đồng bộ bằng latch/barrier và kiểm tra các trạng thái thực thi thực sự.

## 6. Cấu hình rõ executor cho `@Async` trong ứng dụng Spring

Để một phương thức `@Async` thực sự dùng executor vừa giới hạn, nên cấu hình bean có tên và chỉ định tên đó ở annotation. Đoạn dưới đây là **mã tích hợp trong ứng dụng Spring có cấu hình async**, không phải chương trình `javac` độc lập như mục 5.

**Cấu hình Spring Framework 6.2.10+:**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {
    @Bean("limitedIoExecutor")
    public SimpleAsyncTaskExecutor limitedIoExecutor() {
        SimpleAsyncTaskExecutor executor =
                new SimpleAsyncTaskExecutor("limited-io-");

        executor.setConcurrencyLimit(8);
        executor.setRejectTasksWhenLimitReached(true);
        return executor;
    }
}
```

**Service dùng executor này:**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @Async("limitedIoExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Công việc thực tế ở đây phải có timeout, logging và xử lý lỗi.
        String result = "Generated: " + reportId;
        return CompletableFuture.completedFuture(result);
    }
}
```

**Cách hoạt động:**

- Một bean khác inject `ReportService` rồi gọi `generate(...)`. Spring proxy bắt lời gọi, gửi phần thân phương thức vào executor tên `limitedIoExecutor`.
- Nếu có ít hơn 8 task đang chạy, Spring có thể submit task mới. Khi đủ 8, phương thức submit bị reject theo cấu hình và caller cần xử lý thất bại này. **Lỗi ở bước submit** khác với **lỗi xảy ra bên trong task** sau khi đã được chấp nhận.
- `@Async` trả `CompletableFuture<String>` giúp bên gọi xử lý kết quả hoặc lỗi bất đồng bộ. Nếu dùng `@Async void`, ngoại lệ trong phần thân không có future để trả về caller và cần thiết kế `AsyncUncaughtExceptionHandler`/quan sát phù hợp.
- Phải gọi service thông qua **Spring-managed proxy**. Tự gọi `this.generate(...)` trong cùng bean thường bỏ qua interception của `@Async` ở chế độ proxy mặc định.
- Nếu phương thức gọi dịch vụ thật, phải đặt timeout cho chính HTTP/DB client. Việc executor giới hạn 8 không tự đặt timeout cho tác vụ.

Không được mặc định rằng mỗi ứng dụng Spring Boot đều dùng `SimpleAsyncTaskExecutor`. Ví dụ, Spring Boot 3.5 có thể tự cấu hình `ThreadPoolTaskExecutor` khi dùng platform threads, hoặc `SimpleAsyncTaskExecutor` khi bật virtual threads trên JDK 21+ và điều kiện auto-configuration tương ứng thỏa mãn. Cấu hình tường minh với `@Async("limitedIoExecutor")` giúp tránh suy đoán executor mặc định và đảm bảo giới hạn của tác vụ này được áp dụng ở đúng bean.

## 7. Chọn giới hạn dựa trên công suất, không dựa vào số request tối đa

Một giá trị như 4, 8, 16 không thể đúng cho mọi ứng dụng. Nên đặt giới hạn dựa trên **tài nguyên khan hiếm nhất** mà các task tiêu thụ và kiểm tra thực nghiệm.

Ví dụ: dịch vụ xuất báo cáo gọi API bên ngoài, và mỗi instance ứng dụng chỉ được phép gửi tối đa 6 request đang hoạt động. Concurrency limit 6 có thể giới hạn số task chạy tại executor này; nhưng nếu mỗi task đồng thời mở thêm 3 kết nối hoặc gọi nhiều bước, số request thực tế không còn đồng nhất với số task. Khi đó, cần giới hạn ở cấp call/resource thích hợp.

Các câu hỏi trước khi chọn limit:

1. **Task chủ yếu chờ I/O hay xử lý CPU?** Tác vụ CPU-bound quá nhiều thread sẽ tranh CPU; tác vụ chờ I/O có thể cho phép concurrency cao hơn nhưng còn giới hạn kết nối.
2. **Một task sử dụng bao nhiêu tài nguyên?** Số kết nối DB, HTTP sockets, heap, request đến downstream, file descriptors, dịch vụ trả phí/quota.
3. **Dùng bao nhiêu instance?** Nếu có 4 pod, mỗi pod đặt 8, có thể có **tối đa 32 task đang chạy trên bốn executor độc lập**; giới hạn đó không tạo trần toàn hệ thống.
4. **Khi đã đủ suất thì caller sẽ ở đâu?** Nếu caller là HTTP request thread, blocking có thể làm tăng latency; reject cần phản hồi HTTP/retry rõ ràng.
5. **Mất bao lâu để một suất trống lại?** Task bị treo lâu, timeout quá lớn hoặc retry vô hạn có thể khiến toàn bộ suất bị chiếm.
6. **Cần hàng đợi hay xử lý bền vững không?** Nếu công việc cần xếp hàng, giữ được sau restart và retry, cân nhắc hệ queue/job ngoài JVM.

Có thể theo dõi active task count, thời gian chờ submit, tốc độ bị reject, p95/p99 latency, CPU, heap, HTTP connection pool và tỷ lệ lỗi downstream. `getConcurrencyLimit()` và `isThrottleActive()` chỉ cho biết **cấu hình**, không thay thế metric về saturation thực tế. Có thể dùng `TaskDecorator` hoặc instrumentation bên ngoài để đo số task đang chạy, nhưng phải bảo đảm luôn giảm bộ đếm trong `finally`.

## 8. Virtual threads và giới hạn đồng thời

Từ Spring Framework 6.1 trên **Java 21+**, `SimpleAsyncTaskExecutor` có:

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor("virtual-");
executor.setVirtualThreads(true);
executor.setConcurrencyLimit(100);
```

Đây là snippet cho JDK 21+, không chạy được với JDK 17 nếu bật virtual threads. Khi sử dụng virtual threads, mỗi task vẫn có virtual thread mới; Spring không biến executor này thành pool. Virtual threads giúp giảm chi phí giữ nhiều công việc đang chờ I/O, nhưng **không tăng vô hạn năng lực của database, service downstream, CPU hay bộ nhớ**.

Giới hạn 100 trong ví dụ vẫn là trần của các task thực thi qua **executor này**, bất kể dùng virtual hay platform threads. Tránh hai kết luận sai:

- “Virtual threads rẻ nên đặt limit = -1 luôn an toàn.” Không đúng nếu task gọi downstream có quota hoặc tải memory/CPU đáng kể.
- “Đã có concurrency limit thì không cần timeout.” Không đúng; một task treo có thể giữ suất quá lâu.

Trong Spring Boot, `spring.threads.virtual.enabled=true` phụ thuộc phiên bản Spring Boot và yêu cầu JDK 21+; hãy xác nhận executor thực tế qua cấu hình/bean trước khi áp dụng giới hạn. Những thuộc tính cấu hình pool truyền thống có thể không tác động tới `SimpleAsyncTaskExecutor` khi ứng dụng dùng virtual threads.

## 9. So sánh với `ThreadPoolTaskExecutor` để chọn đúng công cụ

| Tiêu chí | `SimpleAsyncTaskExecutor` | `ThreadPoolTaskExecutor` |
| --- | --- | --- |
| Cách dùng thread | Thread mới cho mỗi tác vụ; không tái sử dụng | Worker threads trong pool, có thể tái sử dụng |
| Concurrency | `setConcurrencyLimit(n)` | `corePoolSize`, `maxPoolSize` và chính sách thực thi |
| Khi đầy | Mặc định chặn submitter; từ 6.2.6 có thể reject ngay | Thường đưa vào queue theo `queueCapacity`; khi pool/queue đạt giới hạn có rejection |
| Task queue | Không có queue quản lý riêng | Có hàng đợi được cấu hình |
| Độ phù hợp | Tác vụ ít hoặc có kiểm soát; đơn giản; thích hợp với virtual threads nếu giới hạn đúng | Lưu lượng tác vụ đáng kể, cần tái sử dụng worker và điều chỉnh queue |
| Vòng đời | Có `close()` và timeout chờ task; không có cơ chế pause/resume của pool | Quản lý lifecycle và giám sát pool phong phú hơn |

Khi chọn `ThreadPoolTaskExecutor`, đừng nghĩ `maxPoolSize` luôn là số thread đang chạy ngay khi tải tăng. Với queue có dung lượng dương, thread pool có thể ưu tiên đưa task vào queue trước khi tăng từ core lên max. Phải kiểm tra **core, max, queue và rejection policy** như một bộ.

Không thay `SimpleAsyncTaskExecutor` bằng `ThreadPoolTaskExecutor` chỉ vì thấy giới hạn thấp; chọn theo nhu cầu quản trị, tần suất task, behavior của caller khi quá tải và chi phí tạo thread. Nhưng với hệ thống sản xuất cần queue rõ ràng, số worker ổn định, metrics và shutdown có điều phối, thread pool thường hợp lý hơn.

## 10. Các lỗi thường gặp và cách sửa

### Lỗi 1: đặt limit nhưng tưởng có hàng đợi

**Hiện tượng:** request chậm khi đạt limit dù “chỉ gọi `@Async`”. **Nguyên nhân:** `SimpleAsyncTaskExecutor` mặc định chặn caller trong lúc submit, chứ không nhận task rồi xếp vào queue.

**Sửa:** chấp nhận backpressure và đo thời gian chờ nếu phù hợp; hoặc từ Spring 6.2.6 bật reject và xử lý overload; hoặc chuyển sang pool có queue nếu cần đợi bất đồng bộ trong queue.

### Lỗi 2: dùng `setConcurrencyLimit(0)` để chạy một task mỗi lần

**Sai:** 0 tương ứng `NO_CONCURRENCY`, không phải “một task”. **Sửa:** dùng 1. Với chính sách block, 0 có thể khiến submitter chờ không có suất; với reject, submission sẽ bị từ chối.

### Lỗi 3: bật `setRejectTasksWhenLimitReached(true)` nhưng không xử lý rejection

**Hiện tượng:** lỗi nộp tác vụ xuất hiện trực tiếp ở đường request/job, hoặc dữ liệu bị bỏ lỡ vì giả định task “đã vào queue”. **Sửa:** bắt lỗi tại biên phù hợp, quyết định trả HTTP 429/503, retry có giới hạn và idempotency, hoặc ghi việc vào hệ thống bền vững. Chọn HTTP status theo nguyên nhân và hợp đồng API, không áp một mã mặc định cho mọi trường hợp.

### Lỗi 4: chặn caller ngay trên event loop hoặc worker khan hiếm

**Hiện tượng:** dù task được tách bất đồng bộ, endpoint khác cũng chậm vì thread submit bị giữ. **Sửa:** tránh gọi blocking submission trên event-loop; cân nhắc reject, asynchronous queue/worker riêng hoặc kiến trúc non-blocking tương thích.

### Lỗi 5: giới hạn theo executor nhưng tưởng bảo vệ toàn cluster

**Hiện tượng:** tăng số pod khiến số call vào DB/downstream tăng vượt quota. **Sửa:** tính concurrency theo số instance và số call thực tế trong mỗi task; nếu cần trần toàn cluster thì dùng admission control/chính sách dùng chung ở tầng thích hợp.

### Lỗi 6: nhầm `setTaskTerminationTimeout` với timeout tác vụ

**Hiện tượng:** task I/O treo, không giải phóng suất dù đã cấu hình shutdown timeout. **Sửa:** đặt timeout cho từng dependency và chiến lược cancellation; shutdown timeout chỉ liên quan `close()`. Khi bật timeout đóng executor dương, Spring cần theo dõi các task, làm tăng overhead mỗi task.

### Lỗi 7: dùng `isThrottleActive()` như phép kiểm tra đã đầy

**Sai:** giá trị trả về biểu thị throttle đang bật, không cho biết số tác vụ đang chạy. **Sửa:** đo active submissions/running tasks và rejection/wait time bằng instrumentation riêng.

### Lỗi 8: đổi từ `-1` sang limit dương khi hệ thống đang hoạt động

**Rủi ro:** quá trình đếm concurrency ở trạng thái unbounded có thể không đồng nhất khi chuyển runtime, theo cảnh báo của API nền. **Sửa:** cấu hình giới hạn từ đầu, thay đổi theo quy trình có thử nghiệm và không đổi qua lại tùy tiện.

### Lỗi 9: lồng tác vụ trên executor có một suất

Một task đang giữ suất 1/1 lại gọi `execute(childTask)` vào cùng executor với chính sách block, rồi đợi child. Submit child không thể qua throttle khi parent chưa kết thúc; parent lại không thể kết thúc nếu chờ child. Đây là deadlock do quan hệ phụ thuộc. **Sửa:** tránh blocking nested submission cùng executor khan hiếm; thiết kế dependency không vòng hoặc sử dụng mô hình thực thi phù hợp.

### Lỗi 10: xem giới hạn đồng thời là cơ chế bảo đảm độ tin cậy

Executor chỉ điều phối tác vụ trong process, không lưu bền vững, không tự retry, không biến nghiệp vụ thành transaction và không chống request lặp. Với tác vụ bắt buộc hoàn thành sau restart, hãy dùng job/queue có trạng thái và chiến lược idempotency.

## 11. Cách kiểm thử cấu hình trong hệ thống thật

Để kiểm chứng ứng dụng chứ không chỉ đọc cấu hình, chuẩn bị một workload có thể chủ động giữ task rồi thả task:

1. Cấu hình limit nhỏ, ví dụ 2, trên **đúng executor bean được gọi**. Dùng `@Async("beanName")` để tránh nhầm executor mặc định.
2. Chạy đồng thời 2 task có điểm đồng bộ `CountDownLatch` để chắc chắn đang giữ hai suất. Đừng dựa hoàn toàn vào `Thread.sleep(...)` để tái hiện tình huống.
3. Từ một thread nộp việc riêng, submit task thứ ba. Với chính sách **block**, kiểm tra thread nộp việc chỉ hoàn tất sau khi đã có suất trống. Với **reject**, kiểm tra nhận `TaskRejectedException` và task thứ ba không chạy.
4. Giải phóng một task, xác nhận các tác vụ còn lại tiếp tục theo chính sách dự kiến. Dùng timeout cho test để test không treo nếu cấu hình sai.
5. Đo số task đồng thời cực đại và số thread được tạo trong nhiều lượt; với `SimpleAsyncTaskExecutor`, thread có thể được tạo lại giữa các lượt, khác với pool.
6. Thử khi task ném exception, bị timeout, shutdown và khi ứng dụng chạy nhiều instance. Kiểm tra các request/retry bị từ chối có được xử lý đúng hợp đồng nghiệp vụ.
7. Khi triển khai thực tế, giám sát p95/p99 latency của caller, số rejection, thời gian chờ submission, mức dùng DB/HTTP connections và khả năng phục hồi khi downstream chậm.

Bài test ở mục 5 kiểm chứng một trường hợp reject có tính xác định. Nó **không chứng minh** giới hạn sẽ đạt throughput mong muốn hoặc không gây nghẽn trong một hệ thống nhiều instance. Việc chọn limit cần phép đo ở tải và topology thật.

## 12. Ghi nhớ và tài liệu tham khảo

- **Không cấu hình:** `SimpleAsyncTaskExecutor` mặc định **unbounded** (`-1`), mỗi task có thread riêng.
- **Giới hạn dương:** `setConcurrencyLimit(n)` đặt trần số task chạy đồng thời trên executor đó.
- **Khi đầy:** mặc định **block caller**; từ Spring **6.2.6** có thể bật **reject ngay** bằng `setRejectTasksWhenLimitReached(true)`.
- **Không có pool/queue:** limit không tạo ra `ThreadPoolTaskExecutor`.
- **Virtual threads:** giảm chi phí thread trong một số workload nhưng không bỏ ràng buộc tài nguyên hoặc timeout.
- **Trong Spring:** xác định đúng bean executor, chính sách lỗi, số instance, latency của caller và khả năng xử lý quá tải.

Tài liệu chính thức:

1. [Spring Framework 6.2.10 Javadoc – SimpleAsyncTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/core/task/SimpleAsyncTaskExecutor.html) — hành vi tạo thread, limit, block/reject, virtual threads, shutdown.
2. [Spring Framework 6.2.14 Javadoc – ConcurrencyThrottleSupport](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/util/ConcurrencyThrottleSupport.html) — giá trị mặc định và cảnh báo về đổi limit lúc runtime.
3. [Spring Framework Reference – Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html) — mô hình `TaskExecutor`, `@Async`, so sánh các triển khai.
4. [Spring Boot 3.5 Reference – Task Execution and Scheduling](https://docs.spring.io/spring-boot/3.5/reference/features/task-execution-and-scheduling.html) — executor auto-configuration và virtual threads.

Giới hạn đồng thời là **cơ chế kiểm soát số tác vụ đang thực thi**, không phải hàng đợi và không phải cam kết tốc độ. Khi chọn `SimpleAsyncTaskExecutor`, câu hỏi thiết kế quan trọng nhất là: **khi đã dùng hết mọi suất, thread nộp công việc phải đợi hay hệ thống phải từ chối ngay?**
