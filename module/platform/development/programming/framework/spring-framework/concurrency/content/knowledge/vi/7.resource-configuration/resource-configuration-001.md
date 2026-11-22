# Tách bộ thực thi cho các nhóm công việc có đặc điểm khác nhau trong Spring Framework

## Mục tiêu

Ứng dụng Spring thường đồng thời xử lý nhiều nhóm tác vụ: kiểm tra nghiệp vụ ngắn cần phản hồi nhanh, tính toán CPU, gọi API bên ngoài có thể chờ lâu, đồng bộ dữ liệu và tạo báo cáo nền. Nếu mọi nhóm dùng chung một executor/hàng đợi, tác vụ chậm có thể chiếm toàn bộ worker, khiến tác vụ nhanh phải xếp hàng và trễ hạn.

Bài học trình bày cách **phân nhóm tác vụ theo đặc tính tài nguyên và mục tiêu vận hành**, cấp `ThreadPoolTaskExecutor` riêng cho từng nhóm, cấu hình số luồng, hàng đợi, chính sách từ chối, timeout, vòng đời và quan sát số liệu. Qua một ví dụ chạy được với Java 17+ và Spring Framework, bạn sẽ kiểm chứng tác vụ nhanh có thể hoàn thành khi nhóm chậm vẫn đang bị chặn.

Sau bài này, bạn có thể:

1. Phân biệt công việc CPU-bound, blocking I/O, latency-sensitive, background/batch và tác vụ phụ thuộc dịch vụ ngoài dễ nghẽn.
2. Giải thích tại sao một pool dùng chung tạo head-of-line blocking, và vì sao nhiều pool giúp cô lập một phần tải theo mô hình **bulkhead**.
3. Tạo nhiều bean executor, chọn đúng pool bằng `@Async("beanName")` hoặc `@Qualifier` và tránh sai sót do proxy.
4. Chọn thông số core/max/queue/rejection phù hợp với giới hạn tài nguyên và dữ liệu đo được.
5. Thiết kế lỗi, timeout, giới hạn downstream, logging context, shutdown và metrics cho từng nhóm.
6. Hiểu giới hạn: tách thread pool không tự tách CPU, database connection, heap, lock hay quota dịch vụ bên ngoài.

**Điểm cốt lõi:** Một executor là nơi tiếp nhận và phân phối tác vụ; việc tách executor giúp tránh *worker và queue của nhóm A* bị nhóm B chiếm. Nó không tự làm công việc blocking trở thành non-blocking hoặc bảo đảm độ trễ tối đa trong mọi tình huống.

## 1. Một executor chung làm nghẽn nhóm nhanh như thế nào?

Giả sử pool chung chỉ có hai worker. Hai tác vụ gọi API ngoài bằng HTTP client blocking đều treo khi chờ phản hồi. Một tác vụ tính toán nhẹ được gửi sau:

```text
                      SHARED EXECUTOR
                       queue [FAST]
                               |
                 +-------------+--------------+
                 |                            |
            worker 1                       worker 2
            SLOW A                         SLOW B
            chờ network                   chờ network

              FAST phải đợi worker rảnh dù chỉ cần 2 ms CPU.
```

Thời gian đợi của FAST đến từ **queueing delay**, không phải độ phức tạp phép tính. Nếu pool và queue có hạn, FAST còn có thể bị từ chối khi cả hai đã đầy. Nếu queue rất lớn, caller có thể nhận `Future` sớm nhưng kết quả thực tế trễ rất lâu.

Phân nhóm theo nhu cầu:

```text
FAST tasks -> [fastExecutor queue] -> [fast workers] -> response
SLOW tasks -> [slowExecutor queue] -> [slow workers] -> integration result
BATCH      -> [batchExecutor queue] -> [batch workers] -> background result
```

Một slow worker chờ I/O không lấy mất fast worker. Nhóm có mức ưu tiên cao có thể có queue, budget thời gian và chính sách quá tải khác. Đây là **cách ly tại tầng thread execution**; các pool vẫn chạy trong cùng process/JVM và có thể tranh chấp CPU, bộ nhớ hoặc connection.

Tách pool đáng giá khi nhóm có khác biệt rõ về thời gian chạy, phương thức chờ, SLA, giới hạn downstream hoặc hậu quả khi quá tải. Không tạo một pool riêng cho mỗi method một cách máy móc: quá nhiều pool làm tăng tổng thread, heap, chi phí quản lý và khó cân bằng tài nguyên.

## 2. Nhận dạng nhóm công việc

| Đặc tính | Ví dụ | Hướng tiếp cận |
| --- | --- | --- |
| **CPU-bound** | Hash, tính toán lớn, xử lý dữ liệu trong bộ nhớ | Giới hạn worker gần ngân sách CPU thực tế; đo CPU, p95/p99 và context switching. |
| **Blocking I/O** | JDBC, HTTP client blocking, đọc file chậm | Có thể cần nhiều worker hơn CPU nhưng phải giới hạn theo connection pool, timeout, quota, memory. |
| **Latency-sensitive** | Bước bắt buộc để trả response API | Cấp capacity và queue riêng, theo dõi độ trễ đuôi, có fail-fast/overload policy. |
| **Background/batch** | Tạo báo cáo, rebuild index, đồng bộ theo đợt | Giới hạn throughput riêng, không chen vào fast pool; muốn bền vững cần job store/broker. |
| **Unreliable downstream** | Dịch vụ bên thứ ba có timeout/429 nhiều | Pool/bulkhead riêng, timeout, rate limit, circuit breaker và retry hữu hạn khi phù hợp. |
| **Scheduled work** | Job chạy mỗi phút/đêm | `TaskScheduler` quyết định lịch; có thể giao phần việc nặng sang executor khác. |

Các nhãn có thể trùng nhau. Ví dụ “gọi thanh toán” vừa là I/O chậm tiềm tàng, vừa latency-sensitive và bị quota giới hạn. Quyết định nhóm cần dựa trên **hành vi thực tế**, không chỉ tên package.

Trước khi phân nhóm, thu thập: request/task per second, thời gian CPU, thời gian I/O wait, queue wait, p95/p99, timeout, số tác vụ đồng thời, số connection DB/HTTP được phép và giới hạn CPU container. Số luồng hợp lý được quyết định bởi cả những tài nguyên này.

## 3. Spring cung cấp những thành phần gì?

`TaskExecutor` là abstraction của Spring cho việc chạy `Runnable`, trên nền khái niệm `Executor` của JDK. `AsyncTaskExecutor` mở rộng khả năng submit tác vụ và nhận `Future`. `ThreadPoolTaskExecutor` là bean thuận tiện bọc `java.util.concurrent.ThreadPoolExecutor`, cho phép cấu hình pool qua API Spring.

`@EnableAsync` kích hoạt xử lý các phương thức `@Async`; `@Async("fastExecutor")` chọn bean executor tên `fastExecutor`, còn `@Async("slowExecutor")` chọn bean khác. Khi không chỉ định tên, Spring dùng cơ chế chọn executor mặc định (cấu hình `AsyncConfigurer`, bean phù hợp, hoặc fallback tùy môi trường). **Không nên để việc lựa chọn pool quan trọng phụ thuộc vào phỏng đoán về mặc định.**

Dòng chảy lời gọi:

```text
Caller thread
  -> Spring proxy của WorkService
       -> interceptor đọc @Async("slowExecutor")
       -> lấy bean slowExecutor
       -> submit method invocation
              -> slow worker thực thi thân method
              -> hoàn tất Future hoặc báo lỗi

Caller có Future/CompletableFuture, chưa chắc đã có value.
```

Cơ chế proxy mặc định chỉ chặn lời gọi **đi qua proxy**. Nếu cùng bean gọi `this.slowMethod()`, annotation thường không phát huy tác dụng. Đồng thời, `@Async` không tự động thay đổi bean scope, thread safety hay transaction context.

Hai bean `ThreadPoolTaskExecutor` thực sự độc lập khi chúng sở hữu các thread pool bên dưới **khác nhau**. Nếu hai adapter cùng bọc một JDK `Executor` duy nhất, việc đặt hai tên bean không tạo cách ly thực chất. Hãy kiểm tra cả instance delegate và metrics.

## 4. Hiểu đúng core, max, queue và rejection

| Thuộc tính | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `corePoolSize` | Mức worker lõi mà `ThreadPoolExecutor` có thể duy trì. | Không phải giới hạn concurrency tối đa khi max lớn hơn. |
| `maxPoolSize` | Số worker tối đa của pool. | Không tăng ngay tới max chỉ vì có task mới nếu queue còn nhận được. |
| `queueCapacity` | Giới hạn số task đang chờ. | Queue dương thường được cấp dưới dạng `LinkedBlockingQueue`; zero dùng `SynchronousQueue`. |
| `threadNamePrefix` | Nhận diện worker trong log/thread dump. | Không thay thế việc đo số worker, queue wait và rejection. |
| `RejectedExecutionHandler` | Quyết định khi pool không còn khả năng nhận thêm. | Policy có thể ném lỗi, chạy trên caller hoặc bỏ task. |
| Lifecycle | Đóng pool và xử lý task đang chạy/chờ khi context shutdown. | Cần chính sách timeout và xử lý công việc còn dở. |

Với `ThreadPoolExecutor` có queue hữu hạn dương, trình tự thường là: tạo worker cho tới mức core; sau đó xếp task vào queue khi còn chỗ; khi queue đầy mới tăng worker tới max; cuối cùng reject nếu không còn capacity. Vì vậy:

```text
core=2, max=20, queue=10000
```

không có nghĩa pool nhanh chóng tạo 20 worker khi có 100 tác vụ. Nó có thể giữ hai worker và xếp phần lớn task vào queue. Cấu hình queue quá lớn đôi khi che lấp overload, làm p99 và memory xấu hơn.

Với `queueCapacity=0`, không có hàng đợi chứa task chờ thông thường; pool có thể tạo worker tới max và từ chối sớm khi đã bão hòa. Không có con số “đúng” mặc định: phải lựa chọn theo SLA, lượng tải burst, thời gian xử lý, tổng memory và chính sách hạ nguồn.

## 5. Ví dụ chạy được: FAST hoàn tất khi SLOW vẫn chờ

Ví dụ dùng Java 17+, Maven, Spring Framework `6.2.12`; **không yêu cầu Spring Boot hoặc HTTP server**. Cấu hình hai `ThreadPoolTaskExecutor`:

- `fastExecutor`: một worker, queue bốn task; một tác vụ nhẹ cần hoàn thành sớm.
- `slowExecutor`: một worker, queue hai task; mô phỏng công việc I/O chờ lâu.

Thay vì `Thread.sleep()` rồi đo thời gian (dễ không ổn định), dùng `CountDownLatch` để **chủ động giữ slow worker**, xác nhận worker đã bắt đầu, rồi gửi FAST. Nếu FAST hoàn tất khi latch vẫn khóa thì hai pool đã cung cấp vùng thực thi tách biệt trong ví dụ.

Cấu trúc thư mục:

```text
separate-executors-demo/
├── pom.xml
└── src/main/java/example/SeparateExecutorsDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>separate-executors-demo</artifactId>
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
                    <mainClass>example.SeparateExecutorsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Tạo `src/main/java/example/SeparateExecutorsDemo.java`:

```java
package example;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class SeparateExecutorsDemo {

    public record Result(String value, String threadName) {
    }

    public static class Gates {
        final CountDownLatch slowStarted = new CountDownLatch(1);
        final CountDownLatch allowSlowFinish = new CountDownLatch(1);
    }

    public static class WorkService {
        private final Gates gates;

        public WorkService(Gates gates) {
            this.gates = gates;
        }

        @Async("slowExecutor")
        public CompletableFuture<Result> slowIntegration(String id) {
            gates.slowStarted.countDown();
            try {
                if (!gates.allowSlowFinish.await(10, TimeUnit.SECONDS)) {
                    return CompletableFuture.failedFuture(
                        new IllegalStateException("Slow task timed out")
                    );
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                return CompletableFuture.failedFuture(ex);
            }

            return CompletableFuture.completedFuture(
                new Result("slow:" + id, Thread.currentThread().getName())
            );
        }

        @Async("fastExecutor")
        public CompletableFuture<Result> fastCalculation(String id) {
            return CompletableFuture.completedFuture(
                new Result("fast:" + id, Thread.currentThread().getName())
            );
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
        public WorkService workService(Gates gates) {
            return new WorkService(gates);
        }

        @Bean("fastExecutor")
        public ThreadPoolTaskExecutor fastExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(4);
            executor.setThreadNamePrefix("fast-");
            return executor;
        }

        @Bean("slowExecutor")
        public ThreadPoolTaskExecutor slowExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(2);
            executor.setThreadNamePrefix("slow-");
            return executor;
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            Gates gates = context.getBean(Gates.class);
            WorkService service = context.getBean(WorkService.class);
            ThreadPoolTaskExecutor fastPool =
                context.getBean("fastExecutor", ThreadPoolTaskExecutor.class);
            ThreadPoolTaskExecutor slowPool =
                context.getBean("slowExecutor", ThreadPoolTaskExecutor.class);

            CompletableFuture<Result> slow = service.slowIntegration("A");

            try {
                if (!gates.slowStarted.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Slow worker did not start");
                }

                CompletableFuture<Result> fast = service.fastCalculation("B");
                Result fastResult = fast.get(10, TimeUnit.SECONDS);

                boolean fastFinishedWhileSlowBlocked = !slow.isDone();

                gates.allowSlowFinish.countDown();
                Result slowResult = slow.get(10, TimeUnit.SECONDS);

                System.out.println("separateExecutors=" + (fastPool != slowPool));
                System.out.println("fastFinishedWhileSlowBlocked="
                    + fastFinishedWhileSlowBlocked);
                System.out.println("fastUsesFastPool="
                    + fastResult.threadName().startsWith("fast-"));
                System.out.println("slowUsesSlowPool="
                    + slowResult.threadName().startsWith("slow-"));
                System.out.println("fastValue=" + fastResult.value());
                System.out.println("slowValue=" + slowResult.value());
            } finally {
                gates.allowSlowFinish.countDown();
            }
        }
    }
}
```

Chạy trong thư mục `separate-executors-demo`:

```bash
mvn -q compile exec:java
```

Sáu dòng do **chương trình** in ra khi chạy thành công (log Maven nếu có nằm ngoài các dòng này):

```text
separateExecutors=true
fastFinishedWhileSlowBlocked=true
fastUsesFastPool=true
slowUsesSlowPool=true
fastValue=fast:B
slowValue=slow:A
```

### Diễn giải luồng thực thi và kết quả

1. Context tạo hai executor bean khác nhau, mỗi bean có worker pool riêng. So sánh `fastPool != slowPool` cho `true`.
2. Caller nhận `CompletableFuture<Result>` khi gửi `slowIntegration("A")` qua Spring proxy. Worker slow gọi `slowStarted.countDown()` rồi chờ `allowSlowFinish`.
3. Main chờ `slowStarted.await(...)`, do đó biết task chậm đã thực sự bắt đầu.
4. Main gọi `fastCalculation("B")` qua proxy, lần này dùng `fastExecutor` chứ không chờ worker slow. `fast.get(...)` hoàn tất trước khi main nhả slow latch.
5. Biểu thức `!slow.isDone()` cho `true` trước khi latch được nhả. Đây là bằng chứng có kiểm soát rằng nhóm nhanh chạy độc lập với worker đang chờ của nhóm chậm.
6. Main nhả latch, lấy kết quả slow rồi in theo thứ tự xác định; các tiền tố `fast-`/`slow-` chứng minh tên worker tương ứng.

Cặp latch chỉ dành cho **thí nghiệm**. Ứng dụng thật phải dùng timeout HTTP/database và kiểm soát concurrency thích hợp, không giữ worker bằng latch như xử lý nghiệp vụ. Con số một worker mỗi pool nhằm dễ quan sát, không phải công thức cấu hình production.

Với `@Async`, phương thức thật trả `CompletableFuture.completedFuture(result)` **trong worker**; Spring interceptor trả một completion handle cho caller. Điều đó không biến thân phương thức thành lời gọi đồng bộ trên caller. Nếu caller gọi `.get()` hoặc `.join()` ngay, caller vẫn có thể chờ.

## 6. Các cách chọn executor theo nhóm

### Dùng @Async theo tên

`@Async("fastExecutor")` và `@Async("slowExecutor")` là lựa chọn trực quan khi công việc được tổ chức thành method của bean Spring. Đặt tên bean theo **mục đích và SLA**, như `paymentExecutor`, `externalIoExecutor`, `reportExecutor`, thay vì `pool1`, `pool2`.

Nếu một phương thức được gọi qua `this.method()` trong chính bean, lời gọi không qua proxy mặc định và annotation không chuyển công việc sang executor dự kiến. Giải pháp thường là tách tác vụ async sang bean khác được inject rồi gọi qua reference của Spring.

### Inject executor tường minh

Khi cần xây nhiều task trong một phương thức, hoặc service điều phối task động, inject executor theo qualifier:

```java
@Service
public class ReportDispatcher {
    private final AsyncTaskExecutor reportExecutor;

    public ReportDispatcher(
            @Qualifier("reportExecutor") AsyncTaskExecutor reportExecutor) {
        this.reportExecutor = reportExecutor;
    }

    public Future<String> dispatch(String id) {
        return reportExecutor.submit(() -> "report:" + id);
    }
}
```

Đây là snippet cho ứng dụng Spring, không phải file Java độc lập; cần import Spring annotation, `AsyncTaskExecutor`, `Future` và khai báo bean `reportExecutor`. Ý nghĩa: mỗi lần `dispatch` gửi một `Callable` tới **pool đã được chọn** và trả handle; mã nghiệp vụ phải tiếp tục thiết kế xử lý lỗi, timeout và tính bền vững.

### Executor mặc định

`AsyncConfigurer` có thể cung cấp executor mặc định cho phương thức `@Async` không ghi giá trị. Chỉ dùng default khi ranh giới tài nguyên không quan trọng hoặc đã thống nhất chính sách. Với các nhóm cần cách ly, `@Async("namedExecutor")` giúp reviewers và vận hành nhìn thấy rõ pool nào chịu tải.

Spring không tự phân tích rằng method “gọi API” nên vào I/O pool hay method “tính toán” nên vào CPU pool. Phân loại và routing là quyết định của thiết kế.

## 7. Cách ước lượng số thread cho từng nhóm

### CPU-bound

Với tác vụ dùng CPU liên tục, số worker hữu hiệu thường gần số CPU khả dụng của tiến trình/container, còn phụ thuộc workload khác và mục tiêu độ trễ. Ví dụ một container có hai CPU không nên mặc nhiên cấp năm executor CPU-bound, mỗi executor tám worker, rồi kỳ vọng 40 thread chạy song song thực sự. Tổng CPU vẫn chỉ khoảng hai CPU; có thể tăng contention và context switching.

Bắt đầu với ngân sách CPU tổng thể, đo throughput, CPU utilization, p95/p99 và thời gian queue. Điều chỉnh dựa trên profile và giới hạn CPU quota thực tế.

### Blocking I/O

Nếu task có nhiều thời gian chờ network/DB, pool có thể cần nhiều worker hơn CPU. Một công thức sơ bộ trong mô hình nhất định là:

\[
N_{\text{threads}} \approx N_{\text{CPU}} \times U_{\text{target}} \times (1 + W/C)
\]

Ở đây `W` là thời gian chờ I/O, `C` là thời gian CPU, `U_target` là mức sử dụng CPU mục tiêu. **Đây là giả định bắt đầu**, không phải quy tắc áp dụng cơ học. Pool 100 worker không hữu ích khi DB chỉ cấp 10 connection hoặc API giới hạn 20 calls đồng thời. Ràng buộc thực thường là min của CPU, connection pool, quota, memory, timeout và ngân sách downstream.

Theo Little's Law ở tải ổn định, lượng công việc đồng thời trung bình liên hệ với tốc độ đến và thời gian xử lý/ở trong hệ thống. Chẳng hạn 20 request/s, mỗi request cần khoảng 0,25 s I/O, thì trung bình có khoảng 5 request đang trong giai đoạn đó. Phải dự phòng burst và đo latency thực; không coi tính toán trung bình là cam kết p99.

### Nhóm yêu cầu latency thấp

Queue nhỏ có kiểm soát có thể bảo vệ deadline hơn queue rất lớn. Nếu đầu vào vượt khả năng phục vụ, cần fail-fast, degraded response, retry sau, hoặc admission control. Một `Future` được trả ngay khi submit không có nghĩa kết quả có mặt trước deadline.

### Background và batch

Có thể chấp nhận nhiều thời gian chờ hơn nhưng vẫn phải giới hạn queue/memory. Những việc phải hoàn tất sau restart **không thể chỉ dựa vào queue trong `ThreadPoolTaskExecutor`**, vì RAM không bền vững. Dùng persistent job store/broker và thiết kế idempotency khi cần.

## 8. Backpressure và chính sách từ chối

| Policy | Khi bão hòa | Cần lưu ý |
| --- | --- | --- |
| `AbortPolicy` | Ném lỗi từ chối khi submit. Spring thường biểu diễn thành `TaskRejectedException`. | Caller biết overload; tầng nghiệp vụ phải quyết định phản hồi/retry/fallback. |
| `CallerRunsPolicy` | Caller tự chạy task nếu pool chưa shutdown. | Tạo backpressure nhưng có thể chạy việc rất chậm trên HTTP request thread, làm suy yếu cách ly. |
| `DiscardPolicy` | Bỏ task. | Không dùng cho việc cần bảo đảm xử lý; dễ mất dữ liệu âm thầm. |
| `DiscardOldestPolicy` | Bỏ phần tử cũ nhất trong queue rồi thử nhận task mới. | Có thể mất tác vụ đã được nhận, gây đảo ưu tiên/thứ tự. |

Ví dụ setter khi cấu hình bean:

```java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(2);
executor.setMaxPoolSize(4);
executor.setQueueCapacity(8);
executor.setThreadNamePrefix("integration-");
executor.setRejectedExecutionHandler(
    new java.util.concurrent.ThreadPoolExecutor.AbortPolicy()
);
```

Đây là **mảnh cấu hình minh họa**, cần trả `executor` từ `@Bean` để Spring khởi tạo/quản lý vòng đời.

Khi đã quá tải, retry ngay lập tức và không giới hạn lên cùng pool có thể tạo **retry storm**. Cần giới hạn số lần, backoff, jitter, timeout, circuit breaker hoặc rate limit tùy nghiệp vụ. Chọn chính sách bỏ task phải được quyết định bởi yêu cầu dữ liệu; không vì “tăng throughput” mà làm mất thanh toán, audit hoặc công việc quan trọng.

## 9. Giới hạn của việc tách pool

**CPU chung.** Nhiều pool vẫn tranh chấp CPU của cùng máy/container. Nếu batch chiếm toàn bộ CPU, FAST có thể chậm dù giữ worker riêng.

**Database chung.** `fastExecutor` và `slowExecutor` có thể cùng dùng DataSource. Khi nhóm slow giữ hết connection, nhóm fast vẫn kẹt tại bước lấy connection. Giới hạn concurrent DB calls, transaction duration, query timeout; nếu cần cách ly nghiêm ngặt phải có chính sách ở tầng connection hoặc storage.

**HTTP client và dịch vụ ngoài.** Có thể bị nghẽn chung connection pool, DNS, socket hoặc quota rate limit. Hai nhóm riêng trong một JVM không đảm bảo tổng số call qua nhiều replica nằm dưới quota.

**Heap/GC.** Mỗi queued task giữ object và closure. Nhiều queue lớn làm tăng heap, GC pause, memory pressure. Pool riêng không ngăn JVM bị OOM.

**Lock và state.** Hai nhóm có thể cùng tranh một monitor, cache lock hoặc row database. Tách worker không thay thế đồng bộ hóa và transaction đúng.

**Shutdown/crash.** Queue trong bộ nhớ bị mất khi process chết. Task cần bền vững phải được lưu nhận trạng thái bên ngoài và có cơ chế khôi phục.

Do đó executor bulkhead chỉ là **một tầng** trong chiến lược chống nghẽn. Với downstream cần bảo vệ, cân nhắc semaphore bulkhead, connection pool riêng, rate limiter, timeout và circuit breaker phù hợp.

## 10. Lỗi, timeout, cancellation và context

Phân biệt:

1. **Gửi task bị từ chối:** executor/queue bão hòa hoặc đang shutdown; lời gọi tại điểm submit có thể ném `TaskRejectedException`. Không có bảo đảm đã nhận task.
2. **Task chạy rồi thất bại:** `Future.get()` có thể ném `ExecutionException`; `CompletableFuture.join()` thường báo `CompletionException`. Quan sát future/callback để không mất lỗi.
3. **Caller chờ quá lâu:** `Future.get(timeout, unit)` ném `TimeoutException` nhưng **không tự dừng task**; `CompletableFuture.orTimeout` cũng không bảo đảm worker bị interrupt.
4. **Hủy:** cancellation/interruption phụ thuộc hợp tác của tác vụ và thư viện I/O; không bảo đảm rollback hiệu ứng phụ ở dịch vụ ngoài.

Với `@Async` trả `void`, caller không có handle nhận lỗi. Cấu hình `AsyncUncaughtExceptionHandler` nếu thật sự cần, nhưng các công việc quan trọng nên có kênh kết quả/trạng thái.

Ví dụ quan sát `CompletableFuture` (giả định đã có `WorkService service` của ví dụ chính):

```java
service.fastCalculation("C").whenComplete((value, error) -> {
    if (error != null) {
        System.err.println("Failed: " + error.getMessage());
    } else {
        System.out.println(value.value());
    }
});
```

`whenComplete` quan sát lỗi và thành công; `exceptionally` hoặc `handle` có thể được dùng để quyết định fallback. Callback `thenApply` không tự bảo đảm chạy trên một thread khác; dùng biến thể `...Async(..., executor)` khi cần chọn executor cho bước tiếp theo, tránh vô tình chuyển việc sang common pool của JDK.

`@Async` tạo ranh giới thread: MDC logging, `SecurityContext`, request-scoped context, `ThreadLocal`, transaction của thread caller **không mặc nhiên** chuyển sang worker. Có thể dùng `TaskDecorator` hoặc cơ chế truyền context có kiểm soát, phải khôi phục/xóa trong `finally` vì worker được tái sử dụng. Transaction của caller không trở thành transaction của worker; nếu task nền cần giao dịch, thiết kế ranh giới riêng qua Spring bean/proxy phù hợp.

Trong Spring MVC, controller gọi `.get()`/`.join()` ngay sẽ chặn controller thread dù service dùng executor khác. Giải phóng Servlet request thread cần hợp đồng xử lý HTTP async phù hợp, độc lập với quyết định phân pool của `@Async`.

## 11. Lifecycle, shutdown và độ bền

Mỗi `ThreadPoolTaskExecutor` bean có vòng đời do Spring container quản lý. Khi đóng `ApplicationContext`, Spring thực hiện quy trình shutdown theo hợp đồng lifecycle. Với ứng dụng thực, cần định nghĩa:

- Có dừng nhận công việc mới trong giai đoạn shutdown không?
- Task đã nhận nhưng còn đang chạy hoặc ở queue được phép hoàn tất trong bao lâu?
- Nếu deadline shutdown hết, có thể interrupt/cancel hay phải ghi lại trạng thái?
- Nếu một executor được nhiều thành phần sử dụng, ai sở hữu quyền shutdown?
- Với việc có giá trị nghiệp vụ, đã có idempotency, retry và persistent job record chưa?

`ThreadPoolTaskExecutor` có các tùy chọn shutdown như `setWaitForTasksToCompleteOnShutdown` và `setAwaitTerminationSeconds` (xem API phiên bản đang dùng). Không đồng nhất “pool tách riêng” với “công việc đã submit chắc chắn chạy thành công”. Trong ví dụ chính, main chờ cả hai `Future` hoàn tất rồi mới đóng context, nên không phải xử lý recovery khi restart.

## 12. Theo dõi và đánh giá hiệu quả thực tế

Gắn nhãn theo executor, ví dụ `pool=fast`, `pool=slow`, rồi quan sát:

| Chỉ số | Ý nghĩa |
| --- | --- |
| `active threads`, `pool size`, `queue depth` | Có bị bão hòa worker/queue không, ở nhóm nào? |
| Queue waiting time và execution duration | Độ trễ đến từ chờ hay thời gian xử lý thật? |
| p50/p95/p99 end-to-end latency | Việc tách pool có bảo vệ SLA của FAST không? |
| Submitted/succeeded/failed/rejected/cancelled | Có lỗi hoặc công việc bị mất không? |
| CPU, heap, GC, tổng số thread | Phân pool có tăng overhead hoặc memory pressure không? |
| DB/HTTP connection usage, 429 và downstream timeout | Nghẽn còn nằm ở tài nguyên dùng chung nào? |

`ThreadPoolTaskExecutor` cung cấp một số snapshot như `getPoolSize()`, `getActiveCount()`, `getQueueSize()` (theo API phiên bản). Snapshot không đủ để thực hiện logic “queue còn chỗ, chắc submit sẽ thành công”: trạng thái có thể đổi trước lúc gửi.

Một vòng cải tiến có kiểm soát:

1. Đo baseline khi dùng pool chung; xác định nhóm nào tạo queue wait/tail latency.
2. Xác định nhóm cần cách ly và tổng ngân sách CPU/thread/connection/memory.
3. Khai báo executor riêng, giới hạn queue và rejection theo hậu quả nghiệp vụ.
4. Tạo tải nhóm slow vượt ngưỡng, quan sát FAST có còn hoàn tất trong mục tiêu không.
5. Thử đồng thời CPU/DB/downstream saturation để phát hiện nút cổ chai chia sẻ.
6. Theo dõi metrics sau triển khai và tinh chỉnh dựa trên tải thực.

Nếu dùng Spring Boot Actuator/Micrometer, có thể instrument executor theo integration phù hợp, nhưng cần kiểm tra thiết lập metrics trong chính ứng dụng; Spring Framework lõi không tự có dashboard hoàn chỉnh.

## 13. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Tất cả `@Async` dùng một pool mặc định | Task chậm chiếm worker/queue của task nhanh. | Route tường minh theo nhóm tài nguyên. |
| Tạo hai bean tên khác nhưng cùng delegate | Vẫn chung thread pool và hàng đợi. | Kiểm tra instance/metrics thật. |
| Đặt `maxPoolSize` lớn và queue cực lớn rồi chờ tự tăng thread | Queue thường đầy trước khi mở rộng vượt core. | Hiểu thứ tự worker–queue–max và đo tải. |
| Cho queue không giới hạn để tránh rejection | Tăng tail latency/memory, che overload. | Queue hữu hạn, admission control và lỗi có chủ đích. |
| Dùng `CallerRunsPolicy` cho nhóm cần latency thấp | Task chậm có thể chạy trong HTTP caller. | Chọn overload policy theo SLA. |
| Tách pool CPU nhưng tổng worker lớn hơn nhiều CPU quota | Tranh chấp CPU, context switching. | Tính ngân sách CPU toàn process. |
| Chỉ tách pool mà dùng chung connection pool đang bão hòa | FAST vẫn nghẽn phía DB/HTTP. | Giới hạn downstream, thêm quota/timeout. |
| Quên `@EnableAsync` hoặc dùng self-invocation | Annotation không đi qua interceptor. | Gọi qua Spring bean/proxy. |
| `@Async` xong controller lập tức `join()` | Caller vẫn bị chặn. | Chọn HTTP async/composition phù hợp. |
| Không xử lý rejection, task failure và timeout | Mất kết quả hoặc retry storm. | Quan sát Future, giới hạn retry, định nghĩa fallback. |
| Tin rằng queue RAM đảm bảo công việc qua restart | Task có thể bị mất khi crash. | Dùng job store/broker nếu cần durability. |
| Mang `ThreadLocal` sang worker rồi không dọn | Có thể rò rỉ context giữa request. | Propagation và cleanup trong `finally`. |

## 14. Tự kiểm tra

**Câu 1.** Hai tác vụ HTTP blocking đang giữ hai worker của pool chung. Một tác vụ tính toán 2 ms được submit. Nó có chắc nhận kết quả sau 2 ms không?

**Đáp án:** Không. Queue waiting time có thể lớn hơn rất nhiều thời gian xử lý. Tách nhóm và timeout I/O giúp bảo vệ worker của tác vụ nhanh.

**Câu 2.** Hai executor riêng nhưng đều dùng cùng một JDBC connection pool tối đa bốn connection. Bốn tác vụ slow giữ hết connection. FAST có chắc được cách ly không?

**Đáp án:** Không. Chỉ thread pool được tách; JDBC connection là tài nguyên chia sẻ. Cần quản lý concurrency/timeout ở tầng dữ liệu.

**Câu 3.** `corePoolSize=2`, `maxPoolSize=20`, `queueCapacity=10000`. Khi nhận 100 task trong thời gian ngắn, pool có chắc tạo 20 worker không?

**Đáp án:** Không. Với queue dương, task thường được xếp hàng sau khi đủ core trước khi tăng worker vượt core.

**Câu 4.** `CallerRunsPolicy` có giữ chắc giả định phương thức `@Async` chạy trên worker riêng khi pool quá tải không?

**Đáp án:** Không. Caller có thể phải tự chạy task bị từ chối, gây tăng latency. Đây là dạng backpressure với đánh đổi cần cân nhắc.

**Câu 5.** Vì sao trong ví dụ dùng `CountDownLatch` thay cho `Thread.sleep()`?

**Đáp án:** Để xác nhận slow worker thực sự đã vào method và đang bị giữ lại trước khi submit FAST, tránh kết luận dựa trên lịch chạy may rủi.

**Câu 6.** Có năm executor CPU-bound, mỗi pool tám worker, nhưng container chỉ được hai CPU. Việc phân pool có tạo 40 CPU xử lý song song thật không?

**Đáp án:** Không. Các thread vẫn tranh chấp hai CPU; tổng concurrency cần được điều chỉnh theo quota và số liệu thực tế.

**Câu 7.** Một báo cáo nền phải tiếp tục sau khi ứng dụng restart. Tách `reportExecutor` riêng đã đủ chưa?

**Đáp án:** Chưa. Thread pool/queue RAM không bền vững; cần lưu trữ job và kế hoạch retry/khôi phục/idempotency.

**Câu 8.** Nhận `CompletableFuture` từ `@Async` có chứng tỏ công việc hoàn tất hoặc caller không bao giờ chờ không?

**Đáp án:** Không. Future là handle của kết quả; `get()`/`join()` vẫn có thể chặn, còn task có thể đang chạy hoặc thất bại.

### Điều cần nhớ

Để tách bộ thực thi đúng cách, hãy xác định **đặc tính tác vụ, yêu cầu latency, giới hạn downstream, tổng ngân sách tài nguyên và cách xử lý overload**. Cấp mỗi nhóm thật sự cần cách ly một executor/queue có kiểm soát, theo dõi số liệu riêng và kiểm nghiệm dưới tải. Cách ly worker giúp giảm ảnh hưởng chéo, nhưng an toàn hệ thống còn phụ thuộc CPU, DB, heap, lock, timeout và độ bền công việc.

### Tài liệu tham khảo

- [Spring Framework 6.2 — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html): `TaskExecutor`, `ThreadPoolTaskExecutor`, `@Async`, qualifier và rejection.
- [Spring Framework 6.2 — ThreadPoolTaskExecutor API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html): core/max/queue, monitoring, lifecycle.
- [Java 17 — ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): worker/queue, saturation và chính sách từ chối.
- [Java 17 — CountDownLatch API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): phối hợp thời điểm thực thi và happens-before.
