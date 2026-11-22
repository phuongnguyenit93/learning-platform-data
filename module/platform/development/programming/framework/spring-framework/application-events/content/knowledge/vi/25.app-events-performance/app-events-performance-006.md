# Executor capacity cho async event trong Spring Framework

## 1. Vì sao event bất đồng bộ cần giới hạn năng lực xử lý?

Trong Spring Framework Application Events, `ApplicationEventPublisher.publishEvent(...)` thường được dùng để giảm coupling giữa thành phần phát (publisher) và thành phần nhận (listener). Khi listener chạy đồng bộ theo multicaster mặc định, tác vụ listener chiếm thời gian của thread publisher. Khi dùng `@Async` hoặc cấu hình executor cho `ApplicationEventMulticaster`, việc xử lý có thể chuyển sang worker thread.

Bất đồng bộ **không làm công việc biến mất**: nó chỉ chuyển công việc sang một tài nguyên hữu hạn gồm **số thread đang chạy, hàng đợi chờ, CPU, bộ nhớ, kết nối DB và các dịch vụ bên ngoài**. Nếu event đến nhanh hơn tốc độ listener xử lý, backlog tăng; với queue không giới hạn, ứng dụng có thể có vẻ "vẫn publish nhanh" cho tới khi latency tăng mạnh hoặc bộ nhớ cạn.

**Executor capacity** là khả năng hệ thống tiếp nhận và xử lý các tác vụ event ở tải mục tiêu, gồm:

- **Concurrency:** có bao nhiêu listener task có thể thực sự chạy đồng thời?
- **Queue capacity:** tối đa bao nhiêu task được chờ khi các worker bận?
- **Throughput:** bao nhiêu event/s hoàn thành ổn định, không phải chỉ bao nhiêu event/s được submit?
- **Latency:** event phải đợi bao lâu từ lúc publish đến lúc handler bắt đầu và hoàn tất?
- **Rejection/backpressure:** hệ thống làm gì khi tất cả worker và queue đều đầy?
- **Reliability:** điều gì xảy ra khi task thất bại, event bị từ chối hoặc JVM restart?

Một executor thiết kế tốt không nhất thiết làm mọi event chạy nhanh nhất ở tải bất kỳ; nó phải **có giới hạn rõ ràng và phản ứng có chủ đích khi quá tải**.

## 2. `@Async @EventListener` và executor tham gia ở đâu?

Ví dụ một listener:

```java
@Async("eventExecutor")
@EventListener
public void onPaymentCaptured(PaymentCaptured event) {
    notificationService.sendReceipt(event.paymentId());
}
```

Đây là **mã minh họa**, không phải chương trình độc lập. Muốn hoạt động đúng, cần:

1. Một Spring-managed bean chứa method `public` này.
2. Cấu hình `@EnableAsync`.
3. Một `Executor` hoặc `TaskExecutor` bean tên `eventExecutor`.
4. `PaymentCaptured` là event type thật do ứng dụng định nghĩa.
5. `notificationService` là dependency phù hợp, có timeout và chính sách xử lý lỗi.

Với `@Async("eventExecutor")`, async interceptor đưa method invocation vào executor được chỉ định. `publishEvent(...)` có thể trả về trước khi worker xử lý xong. Vì thế, `publishEvent()` kết thúc bình thường **không chứng minh** email đã gửi hoặc handler đã hoàn tất.

Một luồng đơn giản:

```text
Thread publisher
  |
  +-- publishEvent(PaymentCaptured)
      |
      +-- Spring tìm listener phù hợp
          |
          +-- @Async proxy submit task
              |
              +-- [các worker đang chạy]
              +-- [queue các task đang chờ]
              |
              +-- [nếu đầy: rejection policy]
  |
  +-- publisher có thể tiếp tục

Worker thread
  |
  +-- lấy task khi có capacity
  +-- listener thực thi
  +-- success / failure / retry theo thiết kế
```

**Không nhầm hai hình thức async khác nhau:**

- `@Async @EventListener`: async nằm ở **method listener**, được Spring AOP/interceptor thực thi khi event infrastructure gọi bean proxy.
- `SimpleApplicationEventMulticaster.setTaskExecutor(...)`: async nằm ở **multicaster**, có thể áp dụng cho nhiều listener hỗ trợ async execution.

Một ứng dụng không cần bật cả hai cho cùng một đường event nếu không có lý do rõ ràng; nếu cùng bật, event có thể phải qua **nhiều lần submit/hop**, tăng độ phức tạp trong đo latency và cấu hình executor.

## 3. Hiểu chính xác `ThreadPoolTaskExecutor`

`org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` là adapter/configuration của Spring quanh Java `ThreadPoolExecutor`. Các tham số quan trọng:

| Thuộc tính | Ý nghĩa | Rủi ro khi cấu hình sai |
| --- | --- | --- |
| `corePoolSize` | Số thread core mà pool có thể duy trì | Quá thấp: queue hình thành sớm; quá cao: overhead/DB contention |
| `maxPoolSize` | Giới hạn thread tối đa khi cần mở rộng | Không giới hạn: quá nhiều thread, memory/context switch |
| `queueCapacity` | Số task tối đa chờ trong queue | Không giới hạn: backlog và memory tăng, che giấu quá tải |
| `keepAliveSeconds` | Thời gian sống của non-core idle threads | Quá ngắn: churn; quá dài: giữ tài nguyên lâu |
| `threadNamePrefix` | Tiền tố tên worker | Thiếu: khó debug/thread dump |
| `RejectedExecutionHandler` | Cách xử lý khi đã đầy | Policy mơ hồ: mất task hoặc chặn publisher ngoài ý muốn |
| `waitForTasksToCompleteOnShutdown` | Chính sách shutdown đối với task đã nhận | Shutdown thiếu kiểm soát có thể mất việc |
| `awaitTerminationSeconds` | Giới hạn thời gian chờ kết thúc khi shutdown | Đặt không phù hợp: dừng ứng dụng kéo dài hoặc bỏ dở |

Đối với `ThreadPoolTaskExecutor`, cấu hình mặc định thường là **core pool 1, max gần như không giới hạn và queue không giới hạn**. Vì queue không đầy, thực tế pool thường **không mở rộng lên max** như người mới nghĩ; nhiều task chỉ xếp hàng sau một worker. Cần đặt **cả `queueCapacity` và `maxPoolSize`** nếu muốn giới hạn resource và cho phép tăng thread có kiểm soát.

### 3.1. Thuật toán tiếp nhận task của `ThreadPoolExecutor`

Với cấu hình queue có capacity hữu hạn, về mặt nguyên tắc:

```text
Submit task
  |
  +-- Số worker < corePoolSize?
  |      └-- Có -> tạo worker mới chạy task
  |
  +-- Nếu core đã đủ:
  |      └-- Thử đưa task vào queue
  |             └-- Thành công -> task chờ
  |
  +-- Queue đầy?
  |      └-- Có -> thử tăng worker (tới maxPoolSize)
  |
  +-- Worker đã max và queue đã đầy?
         └-- RejectedExecutionHandler xử lý từ chối
```

Điểm dễ bỏ sót: `maxPoolSize=20` **không có nghĩa** sẽ lập tức chạy 20 worker khi 5 task đầu tới. Với `corePoolSize=2`, pool trước tiên có thể chạy 2 task, rồi **xếp queue** những task tiếp theo; nó thường chỉ tăng quá core **sau khi queue đầy**.

Khi `queueCapacity=0`, Spring dùng hành vi handoff trực tiếp tương tự `SynchronousQueue`, không có backlog hữu hạn trong queue. Điều này có thể khiến pool mở thread nhanh lên tới `maxPoolSize`, sau đó reject. Nếu `maxPoolSize` lại cực lớn, sự bùng nổ thread có thể nguy hiểm.

**Không có cấu hình core/max/queue tối ưu cho mọi hệ thống.** Hãy bắt đầu từ nhu cầu throughput/latency và tài nguyên ngoại vi, rồi đo dưới tải.

## 4. Tính capacity bằng throughput và thời gian phục vụ

Các biến:

- \(\lambda\): tốc độ event đến trung bình, đơn vị event/giây.
- \(S\): thời gian một worker thực sự xử lý một event trung bình, đơn vị giây/event.
- \(C\): số worker song song có ích (không nhất thiết chỉ là số thread cấu hình).
- \(\mu \approx C/S\): năng lực xử lý lý tưởng event/giây nếu tasks tương đối đồng nhất, không có nút cổ chai khác.
- \(W\): thời gian trung bình event tồn tại trong hệ thống từ lúc được tiếp nhận đến khi hoàn tất, gồm cả thời gian queue.
- \(L\): số task trung bình đang xử lý hoặc chờ.

Theo Little's Law trong điều kiện **hệ thống ổn định**:

\[
L = \lambda W
\]

Nếu chỉ xét số task đang **thực sự được phục vụ**, ước lượng nhu cầu concurrency ở tải trung bình là:

\[
C_{\text{busy}} \approx \lambda S
\]

### Ví dụ 1: tải đều

Giả sử:

- Publish **200 event/s**.
- Handler dùng trung bình **50 ms = 0,05 s** để hoàn tất.
- Chưa kể nút cổ chai CPU/DB/network.

Ước lượng worker bận trung bình:

\[
C_{\text{busy}} \approx 200 \times 0.05 = 10
\]

Nếu cấu hình **10 worker** và mọi thứ đúng như trung bình, utilization có thể sát 100%; chỉ một đợt burst hoặc tăng latency cũng gây queue. Với mục tiêu utilization khoảng 70% để có headroom, phép tính quy hoạch sơ bộ:

\[
C \gtrsim \frac{10}{0.7} \approx 14.3
\]

Một điểm bắt đầu thử nghiệm có thể là **15 worker**, *nếu* CPU, DB pool và dịch vụ ngoài cho phép mức song song đó. Đây là **ước lượng sizing ban đầu**, không phải bằng chứng 15 là cấu hình chính xác. Phải kiểm tra thêm p95/p99 latency và tải burst thật.

Nếu task CPU-bound mà host chỉ có vài CPU cores hữu dụng, tăng từ 10 lên 15 threads có thể không tăng throughput. Nếu handler chủ yếu chờ HTTP/DB, concurrency nhiều hơn có thể hữu ích nhưng phải xét giới hạn connection pool, HTTP client và rate limit ngoại vi.

### Ví dụ 2: burst vượt năng lực

Giả sử executor và các dependency ổn định ở **300 event/s**, nhưng trong **2 giây** có burst **500 event/s**. Nếu queue ban đầu trống và bỏ qua hiệu ứng transient:

\[
\text{backlog tăng} \approx (500 - 300)\times2 = 400\ \text{event}
\]

Nếu sau burst input giảm về **100 event/s**, phần capacity dư để dọn queue khoảng **200 event/s**, nên 400 task chờ cần khoảng **2 giây** để xử lý hết trong mô hình lý tưởng. Trong thực tế, tail latency, độ lệch kích thước task, retry và DB contention có thể làm thời gian dọn backlog dài hơn.

Một queue capacity chỉ 100 task sẽ chạm giới hạn sớm trong kịch bản trên; có rejection/backpressure. Queue 1 triệu task thì có thể nuốt burst nhưng cũng có thể tạo độ trễ khổng lồ nếu áp lực kéo dài. **Tăng queue không sửa được tình trạng arrival rate luôn lớn hơn service rate**.

### 4.1. Không dùng Little's Law sai mục đích

- \(L = \lambda W\) là quan hệ ở trạng thái ổn định, không phải lời hứa hệ thống không queue.
- Dùng **thời gian trung bình** cho công thức cơ bản; đừng coi phép thay p99 vào công thức là định lý sizing.
- Số thread hữu ích phụ thuộc throughput thực của DB, API ngoài, CPU, locks, GC và contention.
- Cần phân biệt **queue waiting time** và **handler execution time** trong đo đạc.
- Để bảo vệ SLO, hãy load-test với tốc độ peak, phân phối thời gian xử lý và lỗi ngoại vi tương tự thực tế.

## 5. Cấu hình executor có giới hạn và lựa chọn policy

Một cấu hình production khởi đầu có thể là:

```java
@Configuration
@EnableAsync
class AsyncEventsConfig {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(12);
        executor.setQueueCapacity(200);
        executor.setThreadNamePrefix("event-");
        executor.setKeepAliveSeconds(30);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
```

Đây là **đoạn cấu hình minh họa**, không phải chương trình độc lập. Cần import `@Configuration`, `@Bean`, `@EnableAsync`, `ThreadPoolTaskExecutor` và `java.util.concurrent.ThreadPoolExecutor`; các con số **không phải giá trị khuyến nghị chung**.

Tính chất:

- Chạy tối đa **12 worker threads** trên pool này; queue chờ tối đa **200 tasks**.
- Khi queue đã đầy và thread đã lên 12, task tiếp theo bị `AbortPolicy` từ chối.
- `@Async("eventExecutor")` trỏ rõ ràng tới executor này; tránh phụ thuộc default executor không xác định theo kỳ vọng của người viết.
- `ThreadPoolTaskExecutor` chuyển tình huống reject của underlying executor thành `TaskRejectedException` (một lỗi thuộc hợp đồng `TaskExecutor`) tại đường submit tương ứng.
- `setWaitForTasksToCompleteOnShutdown(true)` là một **chính sách shutdown**, không phải cơ chế durable queue. Nếu JVM crash, pending tasks vẫn có thể mất.

Cần đo mức đóng góp của event vào các resource khác: ví dụ executor 12 threads nhưng HTTP client chỉ cho 4 connections thì bottleneck vẫn ở HTTP; tăng threads có thể chỉ tăng thời gian chờ connection.

## 6. Ví dụ Java 17+ chạy được: queue đầy và event thứ ba bị từ chối

Ví dụ này minh họa capacity bằng một tình huống **xác định** thay vì tạo tải ngẫu nhiên:

- `ThreadPoolTaskExecutor`: `corePoolSize=1`, `maxPoolSize=1`, `queueCapacity=1`.
- Event A vào worker và được **giữ lại bởi latch**, chiếm một thread.
- Event B được submit và **đợi trong queue** có đúng một slot.
- Event C được publish khi **worker đang bận và queue đã đầy**, nên lời submit từ listener `@Async` bị `TaskRejectedException` theo `AbortPolicy`.
- Sau khi thả latch, worker xử lý A rồi B; C không được chạy.

**Ý nghĩa:** Không phải event C sai type hay listener chưa được đăng ký. Đó là **quá tải đã được giới hạn**; nếu cần bảo đảm xử lý C, ứng dụng phải có cơ chế backpressure/persistence/retry chủ động.

### 6.1. Cấu trúc dự án

```text
spring-async-capacity-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncCapacityDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'spring-async-capacity-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
}

application {
    mainClass = 'demo.AsyncCapacityDemo'
}
```

Java 17+ và Gradle 8+ là đủ cho project console này.

### 6.2. `src/main/java/demo/AsyncCapacityDemo.java`

```java
package demo;

import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class AsyncCapacityDemo {

    public record WorkEvent(String id) {}

    // Một bean không bị proxy async, để quan sát từ main và worker.
    public static class Probe {
        final CountDownLatch firstStarted = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);
        final CountDownLatch finished = new CountDownLatch(2);
        final ConcurrentLinkedQueue<String> completed =
                new ConcurrentLinkedQueue<>();
        final AtomicReference<String> workerName =
                new AtomicReference<>();
    }

    public static class WorkListener {
        private final Probe probe;

        public WorkListener(Probe probe) {
            this.probe = probe;
        }

        @Async("eventExecutor")
        @EventListener
        public void onWork(WorkEvent event) {
            try {
                if ("A".equals(event.id())) {
                    // A bắt đầu chạy, nhưng chưa hoàn thành.
                    probe.firstStarted.countDown();
                    if (!probe.release.await(5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException("release timeout");
                    }
                }
                probe.workerName.set(Thread.currentThread().getName());
                probe.completed.add(event.id());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("interrupted", ex);
            } finally {
                probe.finished.countDown();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {

        @Bean("eventExecutor")
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(1);
            executor.setThreadNamePrefix("event-");
            executor.setRejectedExecutionHandler(
                    new ThreadPoolExecutor.AbortPolicy());
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }

        @Bean
        WorkListener workListener(Probe probe) {
            return new WorkListener(probe);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            Probe probe = context.getBean(Probe.class);
            ThreadPoolTaskExecutor executor =
                    context.getBean("eventExecutor",
                            ThreadPoolTaskExecutor.class);

            // A giữ worker; dùng latch thay vì Thread.sleep().
            context.publishEvent(new WorkEvent("A"));
            try {
                if (!probe.firstStarted.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "A did not start on executor");
                }

                // Worker vẫn bị A giữ: B chỉ có thể vào queue.
                context.publishEvent(new WorkEvent("B"));

                int active = executor.getActiveCount();
                int queued =
                        executor.getThreadPoolExecutor()
                                .getQueue().size();

                // A đang chạy + B đang queue => C phải bị reject.
                boolean rejected = false;
                try {
                    context.publishEvent(new WorkEvent("C"));
                } catch (TaskRejectedException ex) {
                    rejected = true;
                }

                System.out.println("while blocked: active=" + active
                        + ", queued=" + queued);
                System.out.println("third publication rejected="
                        + rejected);

                if (active != 1 || queued != 1 || !rejected) {
                    throw new IllegalStateException(
                            "capacity assertions failed");
                }
            } finally {
                probe.release.countDown();
            }

            if (!probe.finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "worker tasks did not finish");
            }

            List<String> done = List.copyOf(probe.completed);
            if (!done.equals(List.of("A", "B"))) {
                throw new IllegalStateException(
                        "unexpected completed events: " + done);
            }

            System.out.println("processed=" + String.join(",", done));
            System.out.println("ran on event executor="
                    + probe.workerName.get().startsWith("event-"));
            System.out.println("after drain: queued="
                    + executor.getThreadPoolExecutor()
                            .getQueue().size());
        }
    }
}
```

Chạy ở thư mục dự án:

```bash
gradle -q run
```

Các dòng **do chương trình in ra** khi cấu hình và các assertions hoạt động như trên:

```text
while blocked: active=1, queued=1
third publication rejected=true
processed=A,B
ran on event executor=true
after drain: queued=0
```

Gradle/Spring có thể in thông báo build hoặc logging riêng. Output này là kết quả mong đợi theo logic của demo; nó **không giả định** worker chạy nhanh hay chậm theo scheduler, vì latch buộc A phải đang chạy trong lúc B xếp queue và C được submit.

### 6.3. Giải thích kết quả

1. `AnnotationConfigApplicationContext` tạo `WorkListener`, đăng ký `@EventListener`, bật async proxy nhờ `@EnableAsync`.
2. Event A được publish. Listener proxy submit task tới pool. Vì pool còn chưa có core worker, nó tạo một thread `event-*` để chạy A.
3. Trong handler A, `firstStarted.countDown()` báo cho main biết A đã bắt đầu, rồi A chờ `release`.
4. Main chờ `firstStarted` thành công mới publish B. Khi đó worker đang bận và `core=max=1`, nên B vào queue có capacity 1.
5. Main chụp metrics `active=1`, `queued=1`, tiếp tục publish C. Pool không thể tạo thêm worker và queue đã đầy. `AbortPolicy` từ chối; đường submit `@Async` ném `TaskRejectedException` mà publisher bắt được **trong ví dụ này**.
6. Dù C đã được publish ở mức API, **handler C không được executor chấp nhận**. C không được xử lý; đừng gọi đó là "xử lý thành công".
7. `finally` thả latch A. Worker lần lượt hoàn tất A và lấy B từ queue. Pool có một worker nên thứ tự hoàn thành của hai task này là A rồi B.
8. Main chờ latch của hai task hoàn tất, xác minh danh sách `["A", "B"]`, prefix thread và queue đã rỗng.

**Tại sao có `try/finally`?** Nếu test bất ngờ ném lỗi lúc kiểm tra capacity, `finally` vẫn thả worker A, tránh để context shutdown đợi task mãi. Chương trình không dùng sleep để đoán thứ tự.

**Giới hạn của ví dụ:** `AbortPolicy` làm lỗi bị phát hiện tại đường submit. Một policy khác có thể chạy task trên thread publisher, bỏ task hoặc gọi logic tùy biến; không được khái quát output trên cho mọi executor/multicaster.

## 7. Các rejection policy và backpressure

Khi executor không còn capacity, quyết định về task bị từ chối là **quyết định nghiệp vụ** chứ không chỉ là lựa chọn kỹ thuật.

Các chính sách thường gặp của Java `ThreadPoolExecutor`:

| Chính sách | Khi pool và queue đầy | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| `AbortPolicy` | Ném `RejectedExecutionException` (qua `ThreadPoolTaskExecutor` có thể là `TaskRejectedException`) | Lộ tình trạng quá tải, dễ đo rejection | Caller phải xử lý lỗi; event có thể bị mất nếu chỉ catch rồi bỏ |
| `CallerRunsPolicy` | Chạy task ngay trên thread submit **nếu executor chưa shutdown** | Tạo backpressure bằng cách làm chậm publisher | Thread HTTP/transaction có thể bị block; khi shutdown policy có thể bỏ task |
| `DiscardPolicy` | Bỏ task bị từ chối | Không làm chậm publisher | **Mất event âm thầm**, rất nguy hiểm với business-critical event |
| `DiscardOldestPolicy` | Bỏ task chờ cũ nhất rồi thử submit mới | Giữ ưu tiên task đến sau | Mất task cũ, đảo ý nghĩa ordering; không phù hợp tác vụ quan trọng |
| Custom handler | Tùy implementation: đo, log, đưa vào durable queue, trả lỗi | Có thể đáp ứng yêu cầu đặc thù | Phải kiểm thử overload, lỗi phụ và shutdown |

### 7.1. Chọn `AbortPolicy` cho demo và fail-fast

Một sự kiện không được executor nhận thường nên làm hệ thống **nhìn thấy rõ** điều đó. `AbortPolicy` là lựa chọn dễ kiểm thử; nhưng caller phải quyết định tiếp theo:

```java
try {
    publisher.publishEvent(new ReportRequested(reportId));
} catch (TaskRejectedException ex) {
    metrics.recordRejectedEvent();
    // Tùy thiết kế: trả trạng thái quá tải, chuyển việc vào queue
    // bền vững hoặc để giao dịch thất bại trước commit.
    throw ex;
}
```

Đây là **mã minh họa**; `metrics`, `ReportRequested`, `reportId` do ứng dụng cung cấp. Không coi `catch` rồi im lặng là xử lý thành công. Trong một event dispatch có nhiều listeners, rejection có thể xảy ra **sau khi listener khác đã có side effect**; không được giả định `publishEvent` là một lệnh nguyên tử đối với tất cả listeners.

### 7.2. Vì sao `CallerRunsPolicy` vừa hữu ích vừa nguy hiểm?

Nếu publisher là request thread, policy này có thể khiến request **tự thực thi listener tốn thời gian** khi pool đầy. Điều đó làm giảm tốc độ submit mới, tạo backpressure. Nhưng:

- P99 latency của HTTP request tăng đột ngột;
- Thread publisher có thể đang giữ lock hoặc transaction;
- Nếu sự kiện được publish trước commit, side effect có thể chạy trước khi transaction gốc hoàn tất;
- Khi executor đã shutdown, `CallerRunsPolicy` có thể không chạy task và không nhất thiết ném lỗi như bạn kỳ vọng;
- Việc listener chạy trên thread caller làm khác ngữ cảnh security/MDC/transaction so với worker.

Chỉ dùng khi hiểu rõ event contract và kiểm thử saturation; đừng chọn như một "cách tránh TaskRejectedException" chung cho mọi hệ thống.

### 7.3. Backpressure ở upstream

Nếu tốc độ đến cao hơn throughput lâu dài, cần tác động **trước khi queue đầy**:

- Giới hạn request concurrency/rate limit hoặc trả `429 Too Many Requests` / `503 Service Unavailable` theo API contract.
- Dùng semaphore/bulkhead ở producer hoặc consumer; cấp admission token trước khi nhận việc.
- Chuyển tác vụ quan trọng vào **durable queue/outbox**, worker đọc theo capacity; publisher không phụ thuộc queue bộ nhớ.
- Giảm số event phát trùng hoặc coalesce các thông báo không cần giữ từng occurrence khi nghiệp vụ cho phép.
- Phân nhóm event theo độ ưu tiên để một loại chậm không chiếm toàn bộ queue của loại quan trọng.
- Tối ưu logic handler và I/O, giảm thời gian giữ connection, thiết lập timeout/retry/backoff.

**Không dùng queue không giới hạn để thay cho backpressure**; đó chỉ là trì hoãn thời điểm lộ quá tải.

## 8. Cách định cỡ thread pool theo loại workload

### 8.1. CPU-bound event listener

Ví dụ: mã hóa ảnh, nén/transform JSON lớn, tính toán phức tạp. CPU là nút cổ chai; nếu host chỉ có 4 CPU cores khả dụng, mở 100 worker CPU-bound thường không tạo 25 lần throughput. Hệ quả có thể là context switching và cache pressure.

Thực hành: thử pool gần số CPU cores **thực sự được cấp cho container**, có headroom cho HTTP/GC và các thread khác. Đo CPU utilization, runnable threads, GC pauses, task latency. Nếu một số CPU cores đang dùng cho traffic API, executor background không nên chiếm hết chúng.

### 8.2. I/O-bound event listener

Ví dụ: gọi REST service, gửi email, ghi DB. Thread thường chờ I/O, nên concurrency có thể cần cao hơn CPU cores. Nhưng constraint chính có thể là:

- JDBC connection pool và số transaction đồng thời;
- HTTP client pool/connection per route;
- Rate limit của đối tác;
- Timeout của network call;
- Số lượng open sockets/file descriptors;
- Retry traffic khuếch đại khi downstream lỗi.

Nếu HTTP service chỉ cho 20 concurrent requests, executor 100 threads có thể gây backlog **bên trong HTTP client**, không làm tăng throughput. Cần sizing cả chuỗi, không chỉ executor.

### 8.3. Event nặng và event nhẹ chung một pool

Một email handler chậm hoặc external API bị timeout có thể làm nhiều event nhẹ bị kẹt cùng queue. Cân nhắc **executor riêng theo workload/SLO**:

```java
@Async("emailExecutor")
@EventListener
public void sendEmail(EmailRequested event) {
    // I/O-bound, rate limit của email provider.
}

@Async("computeExecutor")
@EventListener
public void calculate(CalculationRequested event) {
    // CPU-bound, capacity theo số core.
}
```

Đây là đoạn mã minh họa. Cần hai executor bean, Spring-managed listener và `@EnableAsync`. Phân tách pool giúp **bulkhead isolation**, giảm tình trạng một downstream chậm làm tê liệt toàn bộ event processing. Tuy nhiên thêm pool cần quản lý tổng số threads, memory và shutdown toàn ứng dụng.

## 9. Đo những metric nào để biết capacity có phù hợp?

Không chỉ theo dõi `poolSize` hoặc số event được publish. Cần cả **tốc độ, áp lực queue, thời gian chờ, tỷ lệ lỗi và side effect hoàn tất**.

| Metric | Ý nghĩa / tín hiệu |
| --- | --- |
| Active threads | Bao nhiêu worker đang bận; nếu luôn sát max thì có nguy cơ saturation |
| Pool size / core / max | Pool đang mở rộng hay đứng ở core |
| Queue size / remaining capacity | Backlog hiện tại và khoảng cách tới rejection |
| Queue waiting time | Event chờ bao lâu trước khi handler bắt đầu |
| Handler execution time | Công việc thực tế mất bao lâu, trung bình/p95/p99 |
| End-to-end event latency | Từ lúc event được nhận/ghi tới lúc side effect hoàn tất |
| Submitted / completed task rate | Có đang nợ công việc và backlog tăng không |
| Rejected tasks rate | Tần suất executor không còn capacity |
| Handler failures / retries | Event nhận nhưng xử lý lỗi hoặc phải làm lại |
| Oldest pending task age | Task chờ lâu nhất, hữu ích hơn queue size với SLO |
| DB/HTTP pool utilization | Phát hiện nút cổ chai phía dưới |
| Shutdown pending tasks | Công việc còn lại khi dừng ứng dụng |

Spring `ThreadPoolTaskExecutor` cho phép quan sát một số chỉ số:

```java
int active = executor.getActiveCount();
int poolSize = executor.getPoolSize();
int queue = executor.getThreadPoolExecutor().getQueue().size();
long done = executor.getThreadPoolExecutor().getCompletedTaskCount();
```

Đây là **đoạn minh họa**, `executor` là bean `ThreadPoolTaskExecutor` đã được tạo. Các giá trị là **snapshot của trạng thái đang đổi theo thời gian**, không phải một transaction nhất quán. Ví dụ, queue size có thể thay đổi ngay sau khi đọc; vì vậy dùng metrics aggregation và alert theo xu hướng, không thiết kế logic nghiệp vụ phụ thuộc tuyệt đối vào phép đọc tức thời.

Trong ứng dụng Spring Boot + Micrometer, các executor metric có thể được bind vào monitoring tùy cấu hình/loại bean. Phải kiểm tra tên meter thực tế trong hệ thống, dashboard và version, không mặc định mọi custom executor tự có tên metric giống nhau.

### 9.1. Ghi thời gian chờ thực tế

Một event có thể mang `occurredAt`, nhưng nếu clock của publisher và worker không đồng bộ giữa các service, timestamp không đủ chính xác để đo latency toàn hệ thống. Với in-process event, có thể ghi **monotonic time** ở điểm submit và ở đầu handler hoặc gắn `TaskDecorator` để quan sát queue waiting time.

Một minh họa:

```java
long submittedAt = System.nanoTime();
publisher.publishEvent(new WorkRequested(id, submittedAt));

// Bên trong handler, trước khi làm việc:
long queueWaitNanos = System.nanoTime() - event.submittedAtNanos();
```

Đây là **mã minh họa in-process**, không phù hợp lưu `nanoTime` để chuyển sang JVM khác hoặc replay về sau. `System.nanoTime()` chỉ có ý nghĩa đo khoảng thời gian tương đối trong cùng tiến trình; nếu event đi qua broker/nhiều máy, dùng clock và tracing được chuẩn hóa thích hợp.

Lưu ý `queueWaitNanos` ở handler có thể bao gồm cả thời gian dispatch và proxy overhead, không nhất thiết chỉ là thời gian trong `ThreadPoolExecutor` queue. Muốn tách chính xác, instrument ở mức task submission/start hoặc task decorator.

### 9.2. Alert theo tốc độ tăng backlog

Ví dụ tín hiệu:

- Queue utilization duy trì cao trong nhiều phút;
- `rejected tasks > 0` ở nhóm event quan trọng;
- Queue waiting p99 vượt SLO;
- Completed task rate nhỏ hơn incoming task rate trong thời gian dài;
- Thread active sát max nhưng CPU/DB utilization chỉ thấp: có thể nghẽn I/O/locks;
- Oldest event chưa xử lý tăng tuổi liên tục.

Alert phải gắn với **quyết định vận hành**: scale, giảm traffic, tạm dừng một nguồn, bật backpressure, xem lỗi downstream hoặc xử lý DLQ. Chỉ tăng threshold queue có thể khiến SLO xấu đi nhưng alert bớt xuất hiện.

## 10. Hai cơ chế async không hoàn toàn tương đương

### 10.1. `@Async` trên listener

```java
@Async("eventExecutor")
@EventListener
public void handle(WorkRequested event) {
    // Handler chạy qua async method proxy nếu cấu hình đúng.
}
```

Lợi ích: chỉ method được annotate dùng executor, dễ dành pool riêng theo loại event. Cần:

- `@EnableAsync`;
- bean Spring được proxy;
- method có chữ ký được `@Async` hỗ trợ (`void` hoặc `Future`/`CompletableFuture`);
- cân nhắc self-invocation (`this.method()` không đi qua proxy);
- thiết lập `AsyncUncaughtExceptionHandler` đối với exception của `void` async method.

`@Async @EventListener` **không hỗ trợ phát event mới bằng giá trị return của listener**. Nếu cần event tiếp theo, gọi `ApplicationEventPublisher.publishEvent(...)` tường minh bên trong handler sau khi công việc đã thành công.

### 10.2. `SimpleApplicationEventMulticaster.setTaskExecutor(...)`

Một cách khác là đặt executor trên event multicaster:

```java
@Bean(name = "applicationEventMulticaster")
ApplicationEventMulticaster applicationEventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {

    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

Đây là **đoạn minh họa**, cần import `ApplicationEventMulticaster`, `SimpleApplicationEventMulticaster`, `Qualifier`, `TaskExecutor`, `Bean`. Khi thay multicaster của context bằng bean tên đặc biệt `applicationEventMulticaster`, những listener cho phép async execution có thể được submit qua executor này.

**Chú ý quan trọng:** Không phải mọi `ApplicationListener` đều cho phép chạy async qua multicaster. Trong Spring 6.2, `ApplicationListener.supportsAsyncExecution()` giúp xác định điều đó; các listener dạng transaction-synchronized, ví dụ `TransactionalApplicationListener`, cần chạy phần **đăng ký synchronization ở publisher thread** và khai báo không hỗ trợ async execution qua multicaster. Vì vậy, nếu muốn xử lý hậu commit ở thread nền, cấu hình `@Async` phù hợp **cho chính handler** là một cách khác, và phải bảo toàn ý nghĩa transaction phase.

Ngoài ra, **rejection handling có thể khác giữa hai đường**. Chính sách cụ thể của multicaster, executor, error handler và version quyết định task có ném lỗi, được xử lý ở thread khác hay fallback. Không áp dụng mù kết luận "event C sẽ ném `TaskRejectedException`" từ ví dụ `@Async` mục 6 cho một multicaster tùy biến.

### 10.3. Vì sao không bật cả hai mà thiếu chủ đích?

Nếu custom multicaster submit listener invocation vào một executor, rồi listener lại là `@Async` nên proxy submit thêm lần nữa, mỗi event có thể tạo **hai task scheduling steps**. Điều này làm tăng queue/capacity cần tính, khiến thread context/tracing khó theo dõi và xử lý rejection ở hai điểm khác nhau.

Một kiến trúc đơn giản hơn:

- Chọn **`@Async` per listener** nếu cần cách ly theo workload và executor.
- Chọn **multicaster executor** nếu bạn có lý do rõ ràng để chuyển phần lớn listener sang async và đã xem xét transaction/order/error semantics.
- Giữ listener đồng bộ nếu side effect phải hoàn tất trước khi publisher trở về, hoặc nếu giá trị quá nhỏ để cần thêm scheduling overhead.

## 11. `@TransactionalEventListener`, transaction và saturation

Ví dụ nghiệp vụ:

```java
@Transactional
public void createOrder(String orderId) {
    repository.insert(orderId);
    publisher.publishEvent(new OrderCreated(orderId));
}
```

Một listener hậu commit:

```java
@Async("eventExecutor")
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderCreated event) {
    notificationService.send(orderIdFrom(event));
}
```

Đây là **các đoạn minh họa**, cần Spring transaction infrastructure, repo/service do ứng dụng định nghĩa và executor. `AFTER_COMMIT` yêu cầu event được publish **trong transaction phù hợp**; listener xử lý sau khi transaction commit và có thể tiếp tục trên executor nếu được cấu hình qua async advice.

Các điểm cần đặc biệt chú ý với capacity:

1. **Worker thread không tự mang theo imperative transaction của publisher.** Nếu handler cần ghi DB, gọi một service bean có transaction mới phù hợp.
2. Sau commit, tài nguyên của transaction gốc có thể vẫn gắn với publisher thread trong giai đoạn cleanup. Khi callback ghi DB, cân nhắc `REQUIRES_NEW` thay vì giả định `REQUIRED` tự tạo một commit mới.
3. Nếu executor bị reject tại thời điểm callback hậu commit submit async task, **transaction chính đã commit**. Không thể rollback đơn hàng đã lưu chỉ vì queue đầy.
4. Nếu event cần phải được xử lý dù JVM chết sau commit, **không dựa vào queue in-memory**; sử dụng transactional outbox/persisted queue.
5. `@TransactionalEventListener` mặc định `fallbackExecution=false`: nếu event được phát ngoài transaction, listener có thể bị bỏ qua hoàn toàn.
6. Với event có nhiều listeners, việc một listener bị từ chối không chứng minh các listener trước đó chưa chạy.

**Điểm thiết kế:** Nếu sự kiện hậu commit là hoạt động quan trọng (lập hóa đơn, gửi yêu cầu thanh toán, đồng bộ kế toán), capacity của executor phải đi kèm **persistence và retry**. Chỉ đặt max threads cao hơn không giải quyết lỗi crash hoặc áp lực sustained load.

### 11.1. Transactional outbox để không mất công việc

```text
Transaction T1
  +-- INSERT/UPDATE business data
  +-- INSERT outbox(eventId, payload, status=NEW)
  +-- COMMIT
       |
       +-- background worker đọc outbox theo batch/capacity
           |
           +-- submit/execute với giới hạn concurrency
           +-- success -> mark DONE
           +-- transient failure -> retry with backoff
           +-- permanent failure -> dead-letter/quarantine
```

Outbox đưa **ý định thực hiện hậu xử lý** vào cùng transaction với thay đổi nghiệp vụ; nếu process chết, worker khác có thể tiếp tục. Vẫn cần idempotency khi tác vụ thành công ở downstream nhưng update trạng thái local thất bại, dẫn đến retry.

Một cách đơn giản hơn với queue/broker bền vững cũng có thể phù hợp nếu hệ thống đã có hạ tầng, nhưng cần giải quyết đồng bộ trạng thái DB và message publication. Executor thread pool ở JVM không phải message broker.

## 12. Retry và capacity: tránh khuếch đại tải khi downstream lỗi

Một handler gọi HTTP service có thể lỗi timeout. Nếu mỗi request thất bại được retry ngay vài lần trong chính listener, **một event đầu vào tạo ra nhiều external calls**, làm thời gian phục vụ tăng và throughput giảm.

Ví dụ:

```text
Bình thường:
  100 event/s x 1 HTTP call = 100 call/s

Downstream gặp lỗi và retry tối đa 3 lần ngay:
  100 event/s x tối đa 3 attempts = 300 call/s
```

Cần định nghĩa rõ **3 attempts** là tổng số lần gọi, không phải ba lần retry cộng lần đầu. Kết quả thực phụ thuộc tỷ lệ lỗi và retry policy; ví dụ chỉ minh họa hệ số khuếch đại tối đa.

Khi lỗi lan rộng, thay vì retry ngay trong worker:

- Exponential backoff + jitter, giới hạn tổng thời gian/attempts.
- Circuit breaker khi downstream không còn phục vụ.
- Rate limit/bulkhead cho từng đối tác.
- Durable retry queue với `nextAttemptAt`, thay vì giữ worker thread bằng sleep.
- Dead-letter cho lỗi không khôi phục.
- Idempotency key cho side effect có thể bị gửi trùng.

**Không giữ worker thread ngủ nhiều giây trong khi backlog tăng** nếu có thể dùng scheduler/queue bền vững. Việc đó trực tiếp làm giảm throughput khả dụng của executor.

## 13. Shutdown và lifecycle: capacity khi ứng dụng dừng

Một pool có thể chứa:

```text
active=8 tasks
queued=120 tasks
```

Nếu deploy/scale-down/kill pod ngay lúc đó, in-memory tasks có thể mất. `waitForTasksToCompleteOnShutdown` và timeout giúp **shutdown có trật tự trong một số điều kiện**, không bảo vệ trước `SIGKILL`, crash, mất điện hoặc container bị ép dừng quá thời gian grace period.

Cần tính:

- Thời gian trung bình/p99 của task còn chạy;
- Số task trong queue và thời gian cần drain;
- Kết nối DB/HTTP client có còn sống trong thời gian shutdown không;
- Pod termination grace period và readiness/draining;
- Worker có thể tiếp tục xử lý trên node khác nếu task đã persisted không;
- Khi executor đã shutdown, rejection policy hoạt động như thế nào.

**Không giữ độ tin cậy của hệ thống bằng cách chờ shutdown vô hạn.** Nếu task quan trọng, lưu durable trước, rồi worker có thể phục hồi dù shutdown đột ngột.

Ví dụ `setWaitForTasksToCompleteOnShutdown(true)` trong demo chỉ giúp hoàn thành A/B trong cùng tiến trình; C đã bị reject nên **không xuất hiện lại** khi ứng dụng chạy lần sau.

## 14. Kiểm thử capacity và overload có tính xác định

### 14.1. Tại sao không dùng `Thread.sleep()` để tạo race?

Một test kiểu:

```java
publishEvent(A);
Thread.sleep(20);
publishEvent(B);
publishEvent(C);
```

có thể flake: trên máy phát triển worker kịp chạy, còn CI bị tải hoặc thread scheduling khác thì queue đầy sớm hơn. Dùng `CountDownLatch`/barrier như ví dụ mục 6 giúp xây dựng **điều kiện saturation cố định**.

Test nên xác minh:

1. A đã bắt đầu chạy, giữ một worker.
2. B đã vào queue đang có đúng một slot.
3. C bị reject theo policy đã cấu hình.
4. Khi thả A, A và B hoàn tất.
5. C không có side effect, không bị âm thầm tính là thành công.
6. Exception/rejection được quan sát và ghi metric.
7. Shutdown không treo khi còn task đang chờ.

### 14.2. Load test để đo SLO thật

Ngoài deterministic unit/integration test, cần load test với:

- Tốc độ steady, peak và burst, không chỉ gửi vài event;
- Phân phối thời gian handler, đặc biệt p95/p99;
- Độ trễ do DB/HTTP service và rate limits;
- CPU throttling, memory/GC, GC pauses;
- Retry under failure, circuit-breaker state và số event bị reject;
- Tốc độ queue drain khi traffic trở về bình thường;
- Failover/deploy/shutdown khi queue còn task.

Nên báo cáo **throughput hoàn tất và event latency từ enqueue đến completion**, không chỉ số lệnh `publishEvent`/giây. Một hệ thống nhận 10.000 event/s mà chỉ xử lý được 1.000 event/s không phải "đạt 10.000 event/s" về mặt nghiệp vụ.

### 14.3. Các assertion hữu ích

Trong test:

```java
assertEquals(1, executor.getActiveCount());
assertEquals(1,
        executor.getThreadPoolExecutor().getQueue().size());
assertThrows(TaskRejectedException.class,
        () -> publisher.publishEvent(new WorkEvent("C")));
```

Đây là **đoạn minh họa**, giả định A đã được giữ bằng latch, B đã queue, `AbortPolicy` đang dùng và sự kiện C chỉ được listener `@Async` có executor đó xử lý. Nếu không tạo điều kiện saturation xác định, assertions trên có thể không ổn định.

Sau khi release và chờ `finished`, kiểm tra event thực sự hoàn tất và queue rỗng. Một `@RecordApplicationEvents` test có thể ghi nhận C **đã được publish** dù listener C bị executor reject; đừng nhầm recorder của publisher với một biên nhận hoàn thành xử lý.

## 15. Chẩn đoán các lỗi capacity thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| `@Async` listener có độ trễ lớn khi tải tăng | Queue backlog, worker busy hoặc downstream chậm | Đo queue wait, service time và dependency limits |
| `maxPoolSize=50` nhưng pool chỉ có 1 thread | Queue mặc định quá lớn/không giới hạn, core=1 | Thiết lập queue capacity hữu hạn và core phù hợp |
| CPU cao, tăng threads lại chậm hơn | CPU-bound overload, context switching | Giới hạn concurrency theo CPU thực, tối ưu computation |
| CPU thấp nhưng active threads chạm max | Blocking I/O, lock hoặc DB/HTTP pool contention | Kiểm tra I/O wait, timeout và dependency pools |
| `TaskRejectedException` tại publish | Pool + queue đầy và reject policy | Admission control, durable queue, backpressure, scale theo số liệu |
| Event "đã publish" nhưng không xử lý | Executor reject hoặc async failure | Phân biệt accepted/submitted/completed; giám sát lỗi |
| HTTP p99 tăng bất thường khi full queue | `CallerRunsPolicy` chạy trên publisher thread | Cân nhắc AbortPolicy và backpressure explicit |
| Queue tăng mãi không giảm | Arrival rate vượt sustained throughput | Giảm input, tăng năng lực thực, tối ưu service hoặc dùng persisted queue |
| Retry làm lỗi nặng hơn | Retry storm, external rate limit | Backoff+jitter, circuit breaker và hạn mức attempts |
| Trong transaction, event async không thấy DB vừa lưu | Worker chạy trước commit, thread transaction khác | `AFTER_COMMIT` hoặc outbox và transaction đúng |
| Sau commit bị reject nhưng DB vẫn có order | Transaction chính đã commit | Ghi outbox trong T1, không kỳ vọng rollback hậu commit |
| Event bị mất khi deploy | Queue in-memory không durable | Durable outbox/broker, graceful drain |
| Test flake về queue size | Không kiểm soát scheduling | Dùng latch để giữ worker và queue ổn định |
| Event không chạy với `@Async` | Thiếu `@EnableAsync`, sai executor name hoặc bypass proxy | Kiểm tra bean/proxy/executor |
| Listener khác bị chậm dù event nhẹ | Shared pool bị loại event chậm chiếm dụng | Separate executors theo workload/SLO |

## 16. Checklist đưa executor async events vào production

### Kiến trúc và độ tin cậy

- [ ] Event nào có thể mất khi quá tải, event nào bắt buộc persist/retry?
- [ ] Nếu dữ liệu DB commit mà task bị reject, có **outbox** hoặc recovery path không?
- [ ] Có định danh event, correlation ID và idempotency key để tránh side effect trùng?
- [ ] Có tránh chuyển entity mutable, request object hoặc transaction-bound object qua thread không?
- [ ] Event có được phát vào transaction phase phù hợp nếu cần `AFTER_COMMIT`?

### Capacity và vận hành

- [ ] Đã đo arrival rate bình thường, burst rate, handler service time trung bình/p95/p99?
- [ ] Đã tính concurrency ban đầu từ throughput và service time, rồi load-test?
- [ ] `corePoolSize`, `maxPoolSize`, `queueCapacity` có giới hạn rõ ràng?
- [ ] Dependency pool, rate limit, memory và CPU có đủ headroom?
- [ ] Rejection policy được chọn có chủ đích và test đủ overload/shutdown?
- [ ] Có metrics active, queue, handler latency, rejected, failures, retries và oldest pending age?
- [ ] Có alert và hành động cụ thể khi queue tiến gần capacity?

### Đường thực thi và test

- [ ] Chọn `@Async` per listener hay multicaster executor có chủ đích, tránh double scheduling?
- [ ] `@EnableAsync` và tên executor chính xác, method được Spring proxy intercept?
- [ ] Đã kiểm tra `@TransactionalEventListener` không bị đưa vào multicaster executor sai thread?
- [ ] Test saturation sử dụng latch/barrier, không dựa vào `Thread.sleep`?
- [ ] Shutdown có kế hoạch drain, timeout và recovery cho task durable?

**Kết luận:** Executor capacity là một phần của **hợp đồng vận hành và độ tin cậy** của Spring Application Events. Cấu hình `ThreadPoolTaskExecutor` bằng `corePoolSize`, `maxPoolSize`, `queueCapacity` và rejection policy có giới hạn; sizing theo tốc độ event và thời gian xử lý thực tế; đo latency/backlog thay vì chỉ đếm publish; khi công việc quan trọng phải sống qua quá tải hoặc crash, kết hợp backpressure với outbox/queue bền vững. `@Async` chỉ thay đổi cách scheduling, **không tự tạo thêm CPU, database connections hay tính bền vững**.

## Tài liệu chính thức

- [Spring Framework 6.2 — Task Execution and Scheduling, `@Async` và executors](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html)
- [Spring Framework 6.2 — `ThreadPoolTaskExecutor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.2 — `SimpleApplicationEventMulticaster` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.2 — `ApplicationListener.supportsAsyncExecution()`](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring Framework 6.2 — Application Events and Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Framework 6.2 — Observability and Context Propagation](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
- [Java SE 17 — `ThreadPoolExecutor` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
