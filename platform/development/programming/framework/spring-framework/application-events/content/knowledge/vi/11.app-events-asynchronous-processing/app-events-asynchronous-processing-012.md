# Theo dõi queue và từ chối tác vụ trong Spring Application Events bất đồng bộ

## 1. Vì sao phải theo dõi hàng đợi?

Khi một `@EventListener` dùng `@Async`, phương thức xử lý sự kiện được gửi đến một `TaskExecutor`. Việc `publishEvent(...)` trả về nhanh **không có nghĩa** sự kiện đã được xử lý: tác vụ có thể đang chờ trong queue, đang chạy, bị từ chối ngay lúc gửi, hoặc xử lý thất bại sau khi được nhận.

Với `ThreadPoolTaskExecutor`, năng lực xử lý phụ thuộc vào số luồng, thời gian chạy mỗi tác vụ, giới hạn queue và tốc độ sự kiện đến. Khi tốc độ đến duy trì cao hơn tốc độ xử lý, queue tăng, độ trễ tăng; đến ngưỡng cấu hình, executor phải **từ chối tác vụ** hoặc áp dụng một chính sách thay thế.

Một hệ thống cần trả lời được:

- Có bao nhiêu listener task đang chạy và đang xếp hàng?
- Một sự kiện phải đợi bao lâu trước khi bắt đầu xử lý?
- Có bao nhiêu tác vụ bị từ chối, bị xử lý lỗi hoặc bị mất?
- Khi quá tải, bên phát sự kiện cần retry, giảm tải, trả lỗi hay dùng một hàng đợi bền vững?

**Giới hạn quan trọng:** Spring Application Events là cơ chế thông báo bên trong ứng dụng; `ThreadPoolTaskExecutor` dùng hàng đợi trong bộ nhớ, không phải message broker bền vững. Ứng dụng dừng/crash có thể làm mất các tác vụ chưa hoàn tất. Không được đồng nhất "đã publish" với "đã xử lý thành công".

## 2. Luồng từ publisher đến executor

Với `@EventListener` kèm `@Async("eventExecutor")`, luồng khái quát là:

```text
publisher.publishEvent(event)
        |
        v
Spring ApplicationEventMulticaster
  tìm listener phù hợp theo kiểu event
        |
        v
@Async proxy gửi tác vụ đến eventExecutor
        |
        +--> có worker rảnh/phù hợp --> chạy listener
        |
        +--> chưa chạy được --> xếp vào queue hữu hạn
        |
        +--> queue đầy, không thể mở thêm worker
                                    |
                                    v
                              rejection policy
                          (throw / caller runs / discard)
```

Mặc định, bộ multicaster của Spring gọi listener theo hướng đồng bộ. Trong mô hình này, chính `@Async` chuyển việc **thực thi phương thức listener** sang executor đã đặt tên. Nếu cấu hình `SimpleApplicationEventMulticaster.setTaskExecutor(...)` để làm bất đồng bộ ở cấp multicaster, vị trí nộp task và phạm vi ảnh hưởng sẽ khác; cần quan sát đúng executor mà ứng dụng đang dùng. Không cấu hình cả hai cách một cách máy móc.

### Quy tắc nhận tác vụ của ThreadPoolExecutor

Với `corePoolSize`, `maxPoolSize`, `queueCapacity`:

1. Khi số worker còn dưới `corePoolSize`, executor có thể tạo thêm worker để nhận tác vụ.
2. Khi đã có đủ core worker, tác vụ tiếp theo được đưa vào queue nếu còn chỗ.
3. Chỉ khi queue đầy, executor mới thử tạo thêm worker đến `maxPoolSize`.
4. Nếu cả queue và giới hạn worker đều đã bão hòa, tác vụ bị từ chối theo `RejectedExecutionHandler`.

Vì vậy, đặt `maxPoolSize=32` nhưng queue cực lớn có thể khiến ứng dụng vẫn chỉ chạy gần mức core trong một thời gian dài; tác vụ chờ tăng trước khi pool tăng. Queue mặc định không giới hạn thực tế theo nhu cầu vận hành dễ gây tồn đọng và áp lực bộ nhớ. Queue hữu hạn giúp xác định rõ khi nào phải xử lý quá tải.

Ví dụ với `corePoolSize=1`, `maxPoolSize=1`, `queueCapacity=1`: tác vụ 1 đang chạy, tác vụ 2 nằm trong queue, tác vụ 3 bị từ chối nếu tác vụ 1 vẫn chưa kết thúc.

## 3. Nên đo những chỉ số nào?

| Chỉ số | Cách lấy / nguồn | Dấu hiệu cần chú ý |
| --- | --- | --- |
| Số tác vụ chờ (queue depth) | `executor.getQueueSize()` hoặc queue của `ThreadPoolExecutor` | Tăng kéo dài hoặc liên tục gần capacity |
| Số worker bận | `executor.getActiveCount()` | Bằng mức tối đa trong thời gian dài |
| Kích thước pool hiện tại | `executor.getPoolSize()` | Pool có mở rộng như dự kiến không |
| Queue còn chỗ | `executor.getThreadPoolExecutor().getQueue().remainingCapacity()` | Gần 0 nhiều lần liên tiếp |
| Số tác vụ đã hoàn thành | `getCompletedTaskCount()` trên native pool | Tốc độ hoàn thành thấp hơn tốc độ nhận |
| Số tác vụ bị từ chối | Counter riêng trong rejection handler hoặc nơi bắt lỗi nộp tác vụ | Bất kỳ giá trị tăng nào khi sự kiện quan trọng không được phép mất |
| Thời gian chờ / xử lý | Gắn timestamp lúc publish, lúc listener bắt đầu và khi xong | p95/p99 vượt mục tiêu dịch vụ |
| Lỗi xử lý | Counter và log bên trong listener/handler bất đồng bộ | Task đã được nhận nhưng không hoàn thành nghiệp vụ |

Các chỉ số pool là **ảnh chụp trạng thái gần đúng**, thay đổi liên tục giữa các lần đọc. `getCompletedTaskCount()` không phải thống kê chính xác tuyệt đối trong mọi thời điểm, và **không tự cung cấp số lần rejection**; muốn theo dõi rejection đáng tin cậy phải đếm riêng. Phân biệt ít nhất ba kết quả: **accepted**, **rejected**, **processed successfully**.

Khi đặt cảnh báo, xem nhiều mẫu đo liên tiếp thay vì báo động vì một lần queue tăng đột biến. Một hệ thống có queue rỗng nhưng listener lỗi liên tục vẫn là hệ thống lỗi; ngược lại, queue ngắn có thể bình thường khi chạy theo đợt. Cần kết hợp queue depth, độ trễ, rejection rate và mức tiêu thụ CPU/DB.

## 4. Ví dụ hoàn chỉnh: chủ động tạo queue đầy và bắt rejection

Ví dụ Java 17+ dưới đây chạy trong một dự án **Spring Boot 3.x** đã có `spring-boot-starter`. Chương trình cố ý giữ sự kiện 1 trong worker, để sự kiện 2 nằm trong queue rồi gửi sự kiện 3 nhằm tạo rejection. `CountDownLatch` giúp tình huống ổn định, không phụ thuộc vào `Thread.sleep(...)`.

Tạo file `src/main/java/example/events/EventQueueDemo.java`:

```java
package example.events;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.context.event.EventListener;

@SpringBootApplication
@EnableAsync
public class EventQueueDemo {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(EventQueueDemo.class, args)) {
            // CommandLineRunner hoàn tất trước khi run(...) trả về.
        }
    }

    public record JobRequested(int id) {
    }

    public static class DemoGate {
        final CountDownLatch firstStarted = new CountDownLatch(1);
        final CountDownLatch releaseFirst = new CountDownLatch(1);
        final CountDownLatch processed = new CountDownLatch(2);
        final AtomicInteger rejected = new AtomicInteger();
    }

    public static class JobListener {
        private final DemoGate gate;

        public JobListener(DemoGate gate) {
            this.gate = gate;
        }

        @Async("eventExecutor")
        @EventListener
        public void on(JobRequested event) {
            if (event.id() == 1) {
                gate.firstStarted.countDown();

                try {
                    gate.releaseFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    return;
                }
            }

            System.out.println("PROCESSED job=" + event.id());
            gate.processed.countDown();
        }
    }

    @Bean
    DemoGate demoGate() {
        return new DemoGate();
    }

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor(DemoGate gate) {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(1);
        executor.setThreadNamePrefix("event-worker-");

        // Tự đếm số lần từ chối và tiếp tục giữ hành vi báo lỗi.
        executor.setRejectedExecutionHandler((task, pool) -> {
            gate.rejected.incrementAndGet();
            throw new RejectedExecutionException("Event executor is full");
        });

        return executor; // Spring khởi tạo và quản lý vòng đời bean.
    }

    @Bean
    JobListener jobListener(DemoGate gate) {
        return new JobListener(gate);
    }

    @Bean
    CommandLineRunner scenario(
            ApplicationEventPublisher publisher,
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor,
            DemoGate gate) {

        return args -> {
            try {
                publisher.publishEvent(new JobRequested(1));

                if (!gate.firstStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Worker 1 did not start");
                }

                publisher.publishEvent(new JobRequested(2));

                System.out.printf(
                        "SATURATED active=%d queued=%d%n",
                        executor.getActiveCount(),
                        executor.getQueueSize());

                try {
                    publisher.publishEvent(new JobRequested(3));
                    throw new IllegalStateException(
                            "Expected job 3 to be rejected");
                } catch (TaskRejectedException ex) {
                    System.out.println("REJECTED job=3");
                }
            } finally {
                // Giải phóng worker cả khi có lỗi ở bước publish.
                gate.releaseFirst.countDown();
            }

            if (!gate.processed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Jobs 1 and 2 did not finish");
            }

            System.out.println("REJECTIONS=" + gate.rejected.get());
        };
    }
}
```

Chạy trong project đã cấu hình Gradle wrapper và Spring Boot plugin:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Ngoài log khởi động/shutdown của Spring Boot, các dòng do chương trình in ra theo thứ tự:

```text
SATURATED active=1 queued=1
REJECTED job=3
PROCESSED job=1
PROCESSED job=2
REJECTIONS=1
```

**Diễn giải từng bước:**

1. Job 1 được executor nhận và giữ tại `releaseFirst.await()`. `firstStarted` báo cho luồng phát biết worker đã bắt đầu.
2. Job 2 được submit khi worker duy nhất đang bận nên chiếm vị trí duy nhất trong queue.
3. Trước khi thả job 1, luồng phát nhìn thấy `active=1` và `queued=1`; lúc submit job 3, pool không còn chỗ.
4. Rejection handler tăng `rejected` và ném `RejectedExecutionException`; `ThreadPoolTaskExecutor` chuyển lỗi nộp task thành `TaskRejectedException` cho phía gọi, nên khối `catch` quanh `publishEvent(...)` ghi nhận được.
5. Khối `finally` nhả job 1, sau đó worker đơn xử lý lần lượt job 1 rồi job 2. Job 3 **không được xử lý**.
6. Latch `processed` chỉ để đồng bộ ví dụ và xác nhận 2 job đã chạy xong; ứng dụng production không nên chặn publisher để chờ từng event như vậy.

Đây là một mô phỏng kiểm thử quá tải; **cấu hình 1 worker, queue 1** chỉ nhằm chứng minh cơ chế, không phải kích thước pool được khuyến nghị cho môi trường production.

## 5. Các chính sách từ chối: mỗi lựa chọn có hậu quả khác nhau

`ThreadPoolTaskExecutor` cho phép cấu hình `RejectedExecutionHandler` của Java. Bảng sau mô tả các chính sách thường dùng khi executor đang hoạt động và bị bão hòa:

| Chính sách | Hành vi | Tác động trong event listener |
| --- | --- | --- |
| `AbortPolicy` (mặc định) | Ném lỗi từ chối | Publisher có thể nhận biết lỗi nộp task; cần quy trình xử lý |
| `CallerRunsPolicy` | Chạy task trên luồng đang submit | Tạo backpressure, nhưng `publishEvent` có thể bị chậm và tác vụ chạy trong luồng publisher |
| `DiscardPolicy` | Bỏ qua task mới mà không thông báo | Có thể mất sự kiện trong im lặng |
| `DiscardOldestPolicy` | Bỏ task đang đợi lâu nhất rồi thử submit lại | Có thể mất sự kiện cũ và phá kỳ vọng về thứ tự |

Ví dụ thay thế cấu hình handler (đây là **đoạn cấu hình minh họa**, không phải file độc lập):

```java
executor.setRejectedExecutionHandler(
        new java.util.concurrent.ThreadPoolExecutor.CallerRunsPolicy());
```

Với `CallerRunsPolicy`, một task của listener có thể chạy ngay trong luồng gọi `publishEvent` khi pool đầy, làm tăng độ trễ request và khiến kỳ vọng "listener luôn chạy trên luồng riêng" không còn đúng. Khi pool đã shutdown, chính sách này có thể không chạy task. Không dùng nó chỉ để tránh nhìn thấy exception.

Với `DiscardPolicy` và `DiscardOldestPolicy`, tác vụ có thể bị bỏ mất mà phương thức publish không biết. Chỉ cân nhắc khi **mất tác vụ được chấp nhận một cách rõ ràng** (chẳng hạn cập nhật thống kê có thể tính lại); với email giao dịch, thanh toán hoặc công việc bắt buộc, cần cơ chế lưu bền và retry.

Với `AbortPolicy`, việc bắt `TaskRejectedException` trong luồng publish có thể giúp trả lỗi quá tải, ghi counter hoặc chủ động chuyển tác vụ sang đường xử lý khác. Không bao mọi exception thành "rejected": lỗi xảy ra **sau khi listener bắt đầu chạy** có ý nghĩa khác và cần ghi nhận riêng.

## 6. Đưa các chỉ số vào hệ thống theo dõi

### Theo dõi trực tiếp qua executor

Có thể đọc nhanh các thông số từ bean `ThreadPoolTaskExecutor`:

```java
ThreadPoolTaskExecutor executor = /* bean đã inject */;
int active = executor.getActiveCount();
int queued = executor.getQueueSize();
int poolSize = executor.getPoolSize();
int remaining = executor.getThreadPoolExecutor()
        .getQueue().remainingCapacity();
long completed = executor.getThreadPoolExecutor()
        .getCompletedTaskCount();
```

Đoạn trên là **mảnh code để đặt trong service quản trị/monitoring**, không phải chương trình độc lập. Không dùng số queue tại một thời điểm để chứng minh tác vụ nào đã hoàn thành. Kết hợp thống kê theo thời gian và request/event ID trong log.

### Spring Boot Actuator và Micrometer

Khi ứng dụng có `spring-boot-starter-actuator`, Spring Boot có khả năng tự đăng ký metrics cho các bean `ThreadPoolTaskExecutor` mà có native executor. Tên và nhãn metric phụ thuộc phiên bản/registry; kiểm tra thực tế qua danh sách ở `/actuator/metrics` nếu ứng dụng có endpoint HTTP và đã cấu hình mở endpoint. Có thể xuất sang Prometheus/OTLP hoặc hệ thống giám sát khác bằng registry phù hợp.

**Metric reject riêng vẫn cần chủ động tạo:** counter `gate.rejected` trong ví dụ minh họa nguyên tắc đếm. Ở hệ thống thực, đăng ký counter này vào Micrometer theo tên ứng dụng (ví dụ `application.events.rejected`), gắn nhãn executor/loại sự kiện với số lượng giá trị nhãn được kiểm soát. Không gắn `orderId` hoặc UUID làm tag vì sẽ tạo số series quá lớn.

Một dashboard hữu ích gồm: queue depth, active/pool size, rejection rate, event processing latency, event wait latency và processing error rate. Đặt cảnh báo theo thời gian liên tục, tải nền và mục tiêu vận hành thực tế; giá trị ngưỡng không thể suy ra chỉ từ `queueCapacity`.

### Ghi nhận thời gian chờ

Gắn thời điểm phát sự kiện vào dữ liệu đo hoặc record quan sát (tránh tin hoàn toàn vào đồng hồ từ máy khác), ghi thời điểm listener **bắt đầu**, thời điểm xử lý **kết thúc**. Khi đó:

- *Wait latency* ≈ `listenerStart - eventPublishTime`.
- *Processing latency* ≈ `listenerEnd - listenerStart`.
- *End-to-end latency* ≈ `listenerEnd - eventPublishTime`.

Đây là độ trễ toàn hành trình, gồm cả các phần overhead khác; không mặc nhiên bằng riêng thời gian nằm trong queue. Theo dõi p95/p99 thay vì chỉ lấy trung bình.

## 7. Ứng phó khi queue bắt đầu đầy

**Bước 1 — Kiểm tra khả năng xử lý:** Xác định tác vụ chậm do CPU, khóa, DB connection pool, HTTP timeout hay chính logic listener. Nếu tăng số thread trong khi DB đã bão hòa, tình hình có thể tệ hơn.

**Bước 2 — Chọn cơ chế giới hạn có kiểm soát:** Đặt `corePoolSize`, `maxPoolSize`, `queueCapacity` dựa trên tải đo được. Queue hữu hạn thường rõ ràng hơn queue không giới hạn. Thử nghiệm cả tải đột biến và tải kéo dài, đo độ trễ và tỷ lệ rejection.

**Bước 3 — Quyết định trách nhiệm của publisher khi bị từ chối:** Với event không quan trọng, có thể ghi nhận và chủ động bỏ qua theo chính sách. Với công việc bắt buộc, chỉ dùng retry có giới hạn và backoff nếu an toàn; không retry tức thì trong vòng lặp khi pool đã đầy. Cân nhắc trả thông báo quá tải để upstream giảm tốc.

**Bước 4 — Nếu không được mất sự kiện, đổi cơ chế lưu trữ:** Ghi một bản ghi công việc/outbox cùng transaction nghiệp vụ rồi để worker riêng đọc và gửi thông điệp qua broker/hàng đợi bền vững. Thiết kế idempotency key, retry, dead-letter và kiểm soát ghi trùng. Không dựa duy nhất vào queue trong bộ nhớ của event executor.

**Bước 5 — Quan sát sau thay đổi:** Đo lại throughput hoàn thành, memory, CPU, thời gian chờ và các lỗi. Tăng `queueCapacity` chỉ làm tăng lượng việc có thể chờ; nó **không tự tăng tốc độ xử lý** và có thể tăng độ trễ đuôi.

## 8. Những điểm dễ nhầm với @Async và giao dịch

- **Lỗi nộp task khác lỗi chạy task:** Rejection từ executor thường được báo trong luồng gọi nộp task và có thể được publisher bắt như ví dụ. Một `@Async` listener `void` ném exception **sau khi bắt đầu chạy** không truyền exception đó trở lại lời gọi `publishEvent`; phải ghi log/metrics và cấu hình `AsyncUncaughtExceptionHandler` hoặc bắt lỗi có chủ đích trong listener.
- **Không có transaction tự động đi theo luồng async:** Một listener chạy trên thread khác không mặc nhiên thừa hưởng transaction và `ThreadLocal` của publisher. Nếu cần phản ứng sau commit, dùng thiết kế sự kiện/giao dịch phù hợp, ví dụ xem xét `@TransactionalEventListener` và hợp đồng thực thi riêng của annotation này.
- **Không bảo đảm thứ tự hoàn thành:** Nhiều worker có thể hoàn thành event theo thứ tự khác thứ tự publish. `@Order` không tạo hàng đợi FIFO toàn cục giữa các tác vụ async.
- **Không dùng queue depth làm dấu hiệu thành công:** Queue về 0 chỉ nói không còn task đang chờ; task có thể vẫn đang chạy hoặc đã thất bại. Đếm accepted/rejected/succeeded/failed theo từng giai đoạn.
- **Không nhân bản @Async và multicaster async thiếu mục đích:** Cả hai đều có thể đưa công việc qua executor; nếu dùng cùng lúc phải biết chính xác task nào chạy trong executor nào, cách lỗi lan truyền và cách đo queue.
- **Không trông đợi shutdown xử lý hết trong mọi trường hợp:** Shutdown có thể dừng/interrupt task tùy cấu hình. Có thể cấu hình graceful shutdown, nhưng khi process chết đột ngột hoặc máy gặp sự cố, queue trong memory vẫn không đủ độ bền.

## 9. Kịch bản kiểm thử và checklist production

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Tải dưới năng lực xử lý | Queue nhỏ, task hoàn tất, rejected = 0 |
| Worker bận và queue còn chỗ | Task mới được nhận, queue tăng trong giới hạn |
| Worker bận và queue đầy | Policy được gọi; counter rejection tăng hoặc backpressure đúng thiết kế |
| Listener ném lỗi trong async thread | Ghi nhận failure; publisher không bị hiểu nhầm là đã xử lý thành công |
| Hệ thống downstream chậm | Thời gian chờ tăng; có timeout/backpressure/retry phù hợp |
| Shutdown khi còn task | Hành vi dừng đúng chính sách; công việc quan trọng có cơ chế phục hồi |
| Tăng số lượng worker | Xác minh DB/API downstream chịu được và latency thật sự cải thiện |

Trước khi triển khai, hãy chốt rõ: queue capacity có giới hạn; tên executor riêng cho event; metrics queue/active/rejections/error/latency có dashboard; xử lý rejection minh bạch; retry có backoff và idempotency nếu cần; kiểm thử quá tải và shutdown; và có cơ chế lưu bền khi không được phép mất sự kiện.

**Ghi nhớ:** Queue thể hiện **công việc đang chờ**, rejection thể hiện **công việc executor không thể nhận**. Cần quan sát cả hai và xác định chính sách mất/chờ/thử lại cho từng loại event. Không thể giải quyết overload chỉ bằng cách tăng queue.

## Tài liệu tham khảo

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): cách pool sử dụng core/max/queue và các rejection policy.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): sự kiện đồng bộ mặc định, listener bất đồng bộ và giới hạn của `@Async`.
- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Actuator/Micrometer và metrics cho executor.
