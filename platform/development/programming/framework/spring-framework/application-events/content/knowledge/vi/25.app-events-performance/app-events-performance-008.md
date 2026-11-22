# Đo throughput và latency khi xử lý Spring Framework Application Events

## 1. Mục tiêu của việc đo hiệu năng event

Spring Framework cung cấp `ApplicationEventPublisher`, `ApplicationEventMulticaster`, `@EventListener` và `@TransactionalEventListener` để phân phối sự kiện bên trong ứng dụng. Khi khối lượng event tăng, những câu hỏi quan trọng là:

- Mỗi giây application service **phát** bao nhiêu event?
- Mỗi giây các listener **xử lý hoàn tất** bao nhiêu event?
- Một lời gọi `publishEvent(...)` mất bao lâu?
- Một listener mất bao lâu để xử lý một event?
- Từ lúc event được tạo đến lúc xử lý xong mất bao lâu, kể cả thời gian chờ queue?
- Khi tăng tải, event có bị tồn đọng, từ chối, lỗi hoặc bị xử lý trùng không?
- Lượng CPU, thread, GC, database connections và bộ nhớ thay đổi ra sao?

Không thể trả lời chính xác bằng một con số "event throughput". **Thông lượng (throughput)** là số đơn vị công việc hoàn thành trên một đơn vị thời gian, còn **độ trễ (latency)** là thời gian cần để hoàn thành một đơn vị công việc. Một publisher có thể phát 20.000 event/giây vào queue nhưng chỉ có 2.000 event/giây được consumer xử lý xong; nếu chỉ nhìn tốc độ publish, hệ thống tưởng như rất nhanh dù backlog đang tăng.

Đo hiệu năng event phải bắt đầu bằng việc xác định **ranh giới công việc**: lời gọi publisher, dispatch, handler, commit, enqueue, hay end-to-end delivery. Mỗi ranh giới có mục tiêu và số liệu khác nhau.

## 2. Throughput: phân biệt offered, published, processed và committed

Một pipeline tổng quát:

```text
Commands / event producers
   |
   | offered rate (event/s được yêu cầu)
   v
ApplicationEventPublisher.publishEvent(...)
   |
   | publish / dispatch rate (event/s đã bàn giao)
   v
ApplicationEventMulticaster
   |
   +-- [optional executor / queue]
   |       | queue depth, wait time, reject count
   |       v
   +-- @EventListener / ApplicationListener
           |
           | handler start rate
           v
       handle business logic
           |
           +-- success: completed event/s
           +-- error: failed event/s
           +-- retry: attempted event/s tăng
```

Có thể định nghĩa:

| Chỉ số | Định nghĩa | Câu hỏi |
| --- | --- | --- |
| **Offered rate** | Số event/command được gửi vào hệ thống mỗi giây | Tải yêu cầu cao tới đâu? |
| **Publish rate** | Số lời gọi publisher được bàn giao trên một giây | Producer phát nhanh tới đâu? |
| **Completion throughput** | Số xử lý listener hoàn tất thành công trên giây | Hệ thống thực sự tiêu hóa bao nhiêu công việc? |
| **Attempt rate** | Số lượt xử lý, kể cả retry, trên giây | Có đang tốn tài nguyên vì lặp lại không? |
| **Failure rate** | Số xử lý lỗi mỗi giây hoặc tỷ lệ lỗi | Throughput thành công giảm vì lỗi không? |
| **Committed-event rate** | Số sự kiện gắn với thay đổi đã commit theo hợp đồng | Phần nghiệp vụ bền vững đạt bao nhiêu? |

Phân biệt mẫu số: một event được ba listener nhận có thể tạo ba **handler invocations** từ **một** publisher invocation. Nếu đếm mọi listener, đừng gọi tổng đó là số domain events duy nhất đã phát.

Một công thức cơ bản:

```text
throughput = completed_operations / elapsed_seconds

Ví dụ (số liệu giả định để diễn giải công thức):
completed = 12_000 event handling operations
elapsed = 10 seconds
throughput = 1_200 completed operations/second
```

Nếu trong 10 giây có 12.000 lần gọi `publishEvent` nhưng chỉ 8.000 handler executions hoàn tất, **publish rate = 1.200/s** còn **completion throughput = 800/s**. Khi queue tiếp tục nhận tải và không có drop, backlog có xu hướng tăng. Đây không phải cải thiện throughput chỉ vì publisher kết thúc nhanh.

Với event có fan-out, nên đo thêm số listener cần hoàn tất cho mỗi event. Ví dụ `OrderPaid` có ba listener bắt buộc: "3 handler completions" không phải "3 domain events được xử lý".

## 3. Latency: phải đo ít nhất ba đoạn thời gian

### 3.1. Publish-call latency

Thời gian từ ngay trước tới ngay sau `publisher.publishEvent(event)`:

```text
t0: gọi publishEvent
t1: publishEvent trả về
publish latency = t1 - t0
```

Với `SimpleApplicationEventMulticaster` mặc định, listener phù hợp thường chạy **đồng bộ trên publisher thread**. Khi đó publish-call latency bao gồm chi phí phân phối và thời gian chạy các listener đồng bộ (cộng overhead của producer trong đoạn được đo).

Với executor bất đồng bộ, publish-call latency chủ yếu đo thời gian phân phối và submit task, **không phải thời gian xử lý đã hoàn tất**. Một con số publish latency nhỏ có thể đi kèm queue rất dài.

### 3.2. Handler execution latency

Đo ngay bên trong listener:

```text
h0: handler bắt đầu
h1: handler kết thúc (success hoặc failure)
handler latency = h1 - h0
```

Đây là thời gian chạy logic của **một listener invocation**. Với listener gọi SQL, HTTP hoặc các dịch vụ bên ngoài, thời gian chờ I/O sẽ nằm trong thời gian này. Nếu có nhiều listener, đo riêng theo `handler.type` có tập giá trị hữu hạn, không gộp các công việc rất khác nhau thành một trung bình khó hiểu.

Một phép đo chỉ bao quanh enqueue vào worker không thể được gọi là thời gian handler *xử lý xong*. Nếu handler chỉ gửi `CompletableFuture` rồi trả về, đo đến khi future hoàn thành hoặc đo trong chính worker.

### 3.3. End-to-end event latency

Thời gian từ lúc sự kiện được tạo tới khi xử lý đạt kết quả cuối:

```text
created t0 ---> publish/enqueue t1 ---> handler starts t2 ---> handled t3

queue wait / scheduling delay = t2 - t1
handler execution latency     = t3 - t2
end-to-end processing latency = t3 - t0
```

Trong một JVM, có thể dùng `System.nanoTime()` làm đồng hồ đơn điệu đo **khoảng chênh thời gian**, kể cả khác thread cùng process. Không gửi giá trị `nanoTime()` qua broker hoặc sang máy khác để so sánh trực tiếp; mốc gốc của `nanoTime` là tùy tiến trình/JVM. Đối với luồng liên tiến trình, cần timestamp phù hợp, đồng bộ đồng hồ, trace/correlation hoặc phương pháp đo có hiểu biết về clock skew.

Ranh giới kết thúc cũng phải được định nghĩa: xử lý handler trả về, transaction commit, ghi outbox, broker ack hay tác dụng phụ bên ngoài đã thành công. Nếu không thống nhất, hai biểu đồ "end-to-end latency" có thể đo các thứ hoàn toàn khác nhau.

## 4. Mean không đủ: p50, p95, p99 và phân phối

Latency thường có đuôi dài: 99% event nhanh, một số ít mắc I/O chậm hoặc GC pause. Chỉ nhìn **average** có thể che các trường hợp người dùng thực sự cảm nhận là chậm.

| Thống kê | Ý nghĩa | Công dụng |
| --- | --- | --- |
| Mean (trung bình) | Tổng thời gian / số mẫu | Hiểu thời gian trung bình, nhạy với outlier |
| p50 (median) | Khoảng 50% mẫu không lớn hơn mức này | Trường hợp điển hình |
| p95 | Khoảng 95% mẫu không lớn hơn mức này | Độ trễ đuôi thông dụng |
| p99 | Khoảng 99% mẫu không lớn hơn mức này | Bắt chậm bất thường, SLO nghiêm |
| Max | Giá trị lớn nhất trong cửa sổ | Xem outlier, phụ thuộc độ dài cửa sổ |
| Error/timeout count | Số việc không hoàn tất đúng hạn | Đảm bảo latency không chỉ đo success |

Ví dụ giả định: 99 event chạy 2 ms, một event chạy 5.000 ms. Mean ~51,98 ms dù đa số chỉ 2 ms; p99 phụ thuộc cách tính percentile và dữ liệu cửa sổ nhưng có thể phản ánh tail khác biệt. Vì vậy **không so sánh percentile từ mẫu quá nhỏ** hoặc từ những cách tính khác nhau rồi kết luận có regression.

Với Micrometer `Timer`, các phép đo cơ bản có count, total time và max. **Histogram/percentile không mặc định luôn sẵn có ở mọi MeterRegistry/backend**; phải cấu hình distribution statistics phù hợp và hiểu cách exporter tính percentile. P95/P99 thường nên được tính từ histogram phía metrics backend khi cần tổng hợp nhiều process.

Không lấy trung bình cộng các p95 của từng node để ra p95 toàn cluster; percentile không cộng gộp như count hoặc sum. Cần histogram có bucket phù hợp hoặc hệ đo hỗ trợ merge distribution.

## 5. Ví dụ Java 17 + Spring Framework + Micrometer chạy được

Ví dụ dưới đây đo **event trong tiến trình, xử lý đồng bộ**:

- Chạy warm-up trước để JVM/JIT ổn định tương đối, **không** ghi sample warm-up.
- Phát 5.000 `WorkEvent` đã đánh dấu là measured.
- Đếm số publisher calls và handler completions bằng `Counter`.
- Dùng `Timer` đo `publishEvent`, thân listener và end-to-end latency.
- Tính throughput từ số hoàn tất chia cho thời gian của toàn bộ measurement window.
- In count cố định để kiểm chứng; latency/rate là **số đo thực tế thay đổi theo máy**, không bịa một kết quả benchmark.

Đây là bài demo instrumentation có chủ đích, **không phải benchmark khoa học**. Vì listener dùng vòng lặp CPU đơn giản, không đo SQL, broker, queue, transaction hay tác dụng phụ thực. Những thông số tải thực tế cần một thử nghiệm riêng.

### 5.1. Cấu trúc thư mục

```text
spring-event-metrics/
├── pom.xml
└── src/main/java/demo/EventMetricsDemo.java
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-event-metrics</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.14.8</version>
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
                    <mainClass>demo.EventMetricsDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. src/main/java/demo/EventMetricsDemo.java

```java
package demo;

import java.util.Locale;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventMetricsDemo {

    private static final int WARMUP_EVENTS = 2_000;
    private static final int MEASURED_EVENTS = 5_000;

    // createdNanos dùng đo chênh lệch thời gian trong cùng JVM.
    public record WorkEvent(
            int sequence, long createdNanos, boolean measured) {}

    public static final class EventMeters {
        final Counter published;
        final Counter handled;
        final Timer publishTimer;
        final Timer handleTimer;
        final Timer endToEndTimer;

        EventMeters(SimpleMeterRegistry registry) {
            published = Counter.builder("demo.event.published")
                    .tag("type", "work")
                    .register(registry);
            handled = Counter.builder("demo.event.handled")
                    .tag("type", "work")
                    .register(registry);
            publishTimer = Timer.builder("demo.event.publish")
                    .tag("type", "work")
                    .register(registry);
            handleTimer = Timer.builder("demo.event.handle")
                    .tag("type", "work")
                    .register(registry);
            endToEndTimer = Timer.builder("demo.event.end.to.end")
                    .tag("type", "work")
                    .register(registry);
        }
    }

    public static final class WorkHandler {
        private final EventMeters meters;
        private volatile long resultSink;

        WorkHandler(EventMeters meters) {
            this.meters = meters;
        }

        @EventListener
        public void onWork(WorkEvent event) {
            long started = System.nanoTime();

            // Giả lập một công việc CPU, không dùng sleep hay I/O.
            long result = 0;
            for (int i = 0; i < 1_000; i++) {
                result += event.sequence() * 31L + i;
            }
            resultSink = result; // giữ kết quả quan sát được cho JVM

            long finished = System.nanoTime();
            if (event.measured()) {
                meters.handled.increment();
                meters.handleTimer.record(
                        finished - started, TimeUnit.NANOSECONDS);
                meters.endToEndTimer.record(
                        finished - event.createdNanos(),
                        TimeUnit.NANOSECONDS);
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        EventMeters eventMeters(SimpleMeterRegistry registry) {
            return new EventMeters(registry);
        }

        @Bean
        WorkHandler workHandler(EventMeters meters) {
            return new WorkHandler(meters);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            EventMeters meters = context.getBean(EventMeters.class);

            // Warm-up: có dispatch và chạy listener nhưng không record.
            for (int i = 0; i < WARMUP_EVENTS; i++) {
                context.publishEvent(
                        new WorkEvent(i, System.nanoTime(), false));
            }

            long windowStart = System.nanoTime();
            for (int i = 0; i < MEASURED_EVENTS; i++) {
                long created = System.nanoTime();
                long publishStart = System.nanoTime();

                context.publishEvent(
                        new WorkEvent(i, created, true));

                long publishFinished = System.nanoTime();
                meters.publishTimer.record(
                        publishFinished - publishStart,
                        TimeUnit.NANOSECONDS);
                meters.published.increment();
            }
            long windowFinished = System.nanoTime();

            double elapsedSeconds =
                    (windowFinished - windowStart) / 1_000_000_000.0;
            double rate = meters.handled.count() / elapsedSeconds;

            System.out.printf(Locale.ROOT,
                    "counts published=%d handled=%d publishSamples=%d"
                            + " handleSamples=%d endToEndSamples=%d%n",
                    (long) meters.published.count(),
                    (long) meters.handled.count(),
                    meters.publishTimer.count(),
                    meters.handleTimer.count(),
                    meters.endToEndTimer.count());

            System.out.printf(Locale.ROOT,
                    "throughput=%.1f events/s"
                            + " meanPublish=%.3f ms"
                            + " meanHandle=%.3f ms"
                            + " meanEndToEnd=%.3f ms%n",
                    rate,
                    meters.publishTimer.mean(TimeUnit.MILLISECONDS),
                    meters.handleTimer.mean(TimeUnit.MILLISECONDS),
                    meters.endToEndTimer.mean(TimeUnit.MILLISECONDS));
        }
    }
}
```

Chạy với JDK 17+ và Maven tại thư mục `spring-event-metrics`:

```bash
mvn -q clean compile exec:java
```

**Dòng đếm có thể kiểm chứng** trong ví dụ này:

```text
counts published=5000 handled=5000 publishSamples=5000 handleSamples=5000 endToEndSamples=5000
```

Dòng tiếp theo in `throughput=... events/s` và ba mean latency. **Không có số throughput/latency cố định**: kết quả chịu ảnh hưởng CPU, JVM, JIT, load, hệ điều hành, instrumentation và tình trạng môi trường. Đừng copy số đo của một máy sang tài liệu khác làm baseline.

### 5.4. Vì sao các bộ đếm bằng nhau?

- Một `WorkEvent` measured được phát tương ứng một lời gọi `publishEvent(...)`.
- Có duy nhất một `WorkHandler.onWork(...)` đồng bộ, không ném lỗi.
- Handler hoàn thành trước khi `publishEvent(...)` trả về, nên với 5.000 event đo, số hoàn tất = số publisher calls.
- `Timer` ghi **một sample cho mỗi invocation** measured. Warm-up vẫn tạo event nhưng `measured=false` làm các Counter/Timer không tăng; publish timer cũng chỉ ghi trong vòng đo.
- Throughput được tính bằng **handled count / thời gian bao quanh vòng lặp phát toàn bộ event**; vì xử lý đồng bộ, đó là số công việc hoàn tất trên giây của luồng thử nghiệm.

Trong demo, `meanEndToEnd` chứa chi phí dispatch và thân handler, nên thường lớn hơn `meanHandle`; còn `meanPublish` có thể bao gồm các listener và overhead đo khác. Các giá trị sát nhau hoặc khác nhau ít **không tự chứng minh** mức tăng/giảm hiệu năng; phải có nhiều lần chạy và thống kê.

### 5.5. Không dùng sample code làm benchmark sản phẩm

Vòng lặp xử lý CPU có thể được JIT tối ưu và không phản ánh công việc thật; VM warm-up 2.000 event cũng chưa chắc đủ. Benchmark nghiêm túc cần tải tương đương production, trạng thái GC ổn định và các kịch bản lỗi/queue/DB.

Bài học của ví dụ là **instrument đúng boundary và phân biệt count/latency**, không chứng minh Spring có thể xử lý chính xác bao nhiêu event mỗi giây trên một máy bất kỳ.

## 6. Thu thập số liệu bằng Micrometer trong ứng dụng thật

### Counter

Dùng `Counter` cho tổng số lần sự kiện được tiếp nhận, publish attempts, handler completions, failures hoặc retries. Tốc độ cần được tính theo **một cửa sổ thời gian**, ví dụ derivative/rate của counter tại backend monitoring; không lấy giá trị counter tích lũy từ khi process start làm "event/s".

Một cấu trúc tên meter:

```text
app.event.publish.attempts
app.event.handle.completed
app.event.handle.failed
app.event.handle.retried
app.event.queue.rejected
```

Các metric tên trên là **đề xuất schema**, không phải tên tự có sẵn trong Spring. Một số trường hợp timer đã mang count, nên đừng tạo counter trùng lặp không cần thiết nếu backend có thể tính từ timer và yêu cầu không cần phân loại thêm.

### Timer

`Timer` lưu count và total duration, và có thể hỗ trợ histogram/percentiles theo cấu hình. Dùng khi cần thời gian:

```java
// Trích đoạn, cần registry và event đã được định nghĩa.
Timer timer = Timer.builder("app.event.handle")
        .tag("event.type", "order-placed")
        .register(registry);

long start = System.nanoTime();
try {
    handleBusiness(event);
} finally {
    timer.record(System.nanoTime() - start, TimeUnit.NANOSECONDS);
}
```

Không coi trích đoạn này là class chạy độc lập. `finally` giúp ghi sample cả khi logic ném exception. Nếu muốn chia thành success/failure timers, phải biết outcome và thống nhất name/tag; cần lưu lỗi bằng metric riêng hoặc dùng `Timer.Sample` để chọn tag sau khi biết kết quả.

Nên tránh tag có cardinality cao như order ID, email, user ID hoặc event ID. Dùng event type, handler type và outcome có tập giá trị hữu hạn. Mỗi tổ hợp tag làm tăng số chuỗi metric cần lưu.

### LongTaskTimer, Gauge và queue metrics

- `LongTaskTimer` phù hợp khi cần đo số công việc **đang chạy** và thời gian các tác vụ dài chưa hoàn tất. Không thay thế `Timer` cho distribution của tác vụ đã xong.
- `Gauge` phù hợp queue depth, active threads, in-flight tasks. Gauge đo mức hiện tại tại thời điểm đọc, không lưu tổng số event đã đi qua.
- Counter cho rejected/failed/retries giúp phân biệt queue thật sự đang tiêu hóa dữ liệu hay producer chỉ đẩy tải vào mà không kiểm soát.

Đừng biểu diễn queue depth bằng Counter không có decrement; nó cần giá trị có thể lên/xuống hoặc nguồn state đáng tin.

### Observation không tự xuất hiện ở @EventListener

Spring Framework **không tự đóng góp Micrometer Observation** cho phương thức `@EventListener`. Listener đồng bộ thường chạy trong publisher thread và context/trace hiện tại, nhưng không có span/timer riêng chỉ nhờ annotation. Muốn đo latency của handler, có thể dùng `Timer` thủ công như demo, `ObservationRegistry` với `Observation.createNotStarted(...).observe(...)` hoặc AOP `@Observed` được cấu hình đầy đủ.

Chỉ có dependency Actuator/Micrometer hay bean `ObservationRegistry` không tự sinh timer cho mọi listener. Nếu dùng `@Observed`, cần aspect/proxy hoạt động trên invocation thực tế. Đừng dựa vào proxy tự gọi method trong cùng bean để đo được mọi trường hợp.

## 7. Hệ thống async: đo queue wait, throughput xử lý và backlog

Khi cấu hình custom `ApplicationEventMulticaster` với executor, hoặc dùng `@Async`, publisher có thể kết thúc trước khi handler hoàn thành. Khi đó phải có hai nhóm đo:

**Producer side:** publish/enqueue rate, publish latency, task rejection, queue size tại mốc quan sát.

**Consumer side:** handler start rate, handler completed rate, handler duration, queue waiting time, in-flight count, failed/retry counts.

```text
Producer --submit--> bounded queue --dequeue--> Worker listeners
          t0       t1              t2         t3

enqueue latency       = t1 - t0
queue wait             = t2 - t1
handler service time   = t3 - t2
end-to-end latency     = t3 - t0
```

Nếu listener chỉ nhận event rồi gửi tiếp vào queue riêng, việc handler method trả về không phải dấu mốc xử lý business thực sự. Instrument tại worker thực hiện tác vụ cuối, hoặc nêu rõ đó chỉ là handoff latency.

### Bounded executor và backpressure

Một cấu hình `ThreadPoolTaskExecutor` có thể đặt core/max threads và queue capacity. Với queue vô hạn, publisher có thể duy trì tốc độ cao cho tới khi bộ nhớ cạn và latency chờ tăng mạnh. Với queue hữu hạn, khi bão hòa phải có chính sách rejection/caller-runs/backpressure hoặc chặn producer theo hợp đồng.

Ví dụ cấu hình ý tưởng (cần BeanFactory và imports phù hợp, không phải chương trình độc lập):

```java
ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
executor.setCorePoolSize(4);
executor.setMaxPoolSize(8);
executor.setQueueCapacity(1000);
executor.setThreadNamePrefix("event-worker-");
executor.initialize();

SimpleApplicationEventMulticaster multicaster =
        new SimpleApplicationEventMulticaster();
multicaster.setTaskExecutor(executor);
```

Đăng ký multicaster bằng tên bean `applicationEventMulticaster` nếu muốn thay thế mặc định ở `ApplicationContext`. Cần shutdown executor đúng vòng đời. Trong Spring 6.x, một số listener transaction-synchronized không cho phép async execution, nên **không giả định mọi callback đều rời publisher thread**. Thử nghiệm phải phản ánh loại listener thực tế.

**Báo cáo throughput không thể chỉ lấy số producer submit thành công**: thử nghiệm nên chờ drain queue/handler completion, đo event mất, event bị reject, exception và số item còn tồn. Nếu không, bạn đang benchmark tốc độ tăng backlog.

### Công thức đánh giá hàng chờ

Trong một cửa sổ tương đối ổn định, nếu arrival rate là \(\lambda\) và completion rate là \(\mu\):

- Nếu \(\lambda \gt \mu\) lâu dài và event không bị drop, queue/backlog tăng.
- Nếu \(\lambda \lt \mu\), hệ thống có cơ hội xử lý hết backlog, nhưng latency vẫn còn phụ thuộc burst, scheduling và dependency.
- Theo Little's Law trong các điều kiện ổn định phù hợp: \(L = \lambda W\), với \(L\) là lượng công việc trung bình trong hệ thống, \(\lambda\) là throughput hoàn tất trung bình và \(W\) là thời gian trung bình trong hệ thống.

Không suy ra áp dụng Little's Law từ một mẫu burst ngắn khi hệ thống chưa steady state, có loss hoặc chưa đo đúng window. Chú ý "in-flight" có thể bao gồm cả queue và đang chạy; mỗi hệ thống đặt scope khác nhau.

## 8. Tổ chức load test có thể lặp lại

Một bài đo hiệu năng có giá trị cần viết rõ giả định và điều kiện.

1. **Workload đại diện**: event size, số listener, loại listener, SQL/HTTP, dữ liệu nóng/lạnh, fan-out, tỷ lệ lỗi, phân bố payload.
2. **Môi trường**: JDK version, JVM heap/GC, số CPU, thread count, pool size, container limits, DB/broker location, sampling/tracing settings.
3. **Warm-up**: khởi tạo context, làm nóng JIT và connection pool; tránh lẫn thời gian dựng bean vào throughput steady state.
4. **Measurement window**: đo nhiều cửa sổ đủ dài, nói rõ start/end, tách warm-up, ramp-up và cooldown.
5. **Load model**: closed-loop (mỗi client chờ xong rồi gửi tiếp) hoặc open-loop (arrival rate độc lập response). Hai cách cho kết quả tail latency khác nhau.
6. **Correctness check**: đếm số publish, số success, failures, retries, queue rejects và missing/duplicate events.
7. **Resource telemetry**: CPU utilization, GC allocation/pause, heap, thread pools, connections, queue length, network/IO.
8. **Phân tích**: báo p50/p95/p99, rate thành công, lỗi, backlog, saturation và confidence/variance qua nhiều lần chạy.
9. **Công cụ**: dùng JMH cho microbenchmark code-path khi thích hợp; dùng Gatling/k6/JMeter hoặc workload generator chuyên dụng cho end-to-end scenario. Microbenchmark không thay thế integration/load test.
10. **Lặp lại cùng điều kiện**: mỗi variant chạy nhiều lần, xen kẽ thứ tự A/B khi có thể, tránh đo lúc máy bận nhiệm vụ ngoài.

### Coordinated omission và tải thật

Một thử nghiệm closed-loop gửi request mới **sau khi request trước xong** có thể giảm tốc độ phát khi hệ thống chậm. Khi đó những request đáng lẽ tới trong thời gian server bị kẹt không còn được phát, và phân phối latency nhìn có vẻ tốt hơn thực tế.

Với workload có arrival rate dự kiến độc lập với thời gian xử lý, sử dụng open-loop test hoặc cơ chế hiệu chỉnh coordinated omission phù hợp; đồng thời báo tỉ lệ rejected/dropped và backlog. Không chỉ tăng số thread tới khi có một kết quả throughput "đẹp".

### Tránh sai lệch do công cụ đo

- `System.out.println` trong mỗi listener có thể trở thành nút cổ chai I/O; chỉ in summary cuối đo.
- Log DEBUG/stack trace cho mọi event có thể thống trị latency; xác định rõ cấu hình production và baseline.
- Nếu bạn đo vòng lặp xử lý quá đơn giản, overhead Timer/Counter có thể chiếm tỷ trọng lớn: đo cả phiên bản có/không instrumentation khi cần đánh giá overhead.
- Dùng `System.nanoTime()` cho duration nội bộ, không dùng `currentTimeMillis()` khi cần độ chính xác ngắn và tránh thay đổi wall clock.
- Khởi tạo ngẫu nhiên, parse JSON, serialize, tạo object event cũng có chi phí; xác định rõ có đo các bước đó trong publish window hay không.
- Trong benchmark CPU cực ngắn, JIT có thể tối ưu công việc không quan sát được; dùng JMH và state/Blackhole phù hợp để tránh benchmark một phép tính đã bị loại.
- GC, CPU throttling và lock contention có thể làm tail latency nhảy vọt; theo dõi cùng biểu đồ latency.

## 9. Cách đọc kết quả và tìm nút cổ chai

Một quy trình điều tra:

```text
Kịch bản tải giữ nguyên
  |
  +-- publish rate cao nhưng completion thấp?
  |      -> xem queue depth, rejection, active threads, retries
  |
  +-- publish latency cao trong chế độ sync?
  |      -> xem handler duration và fan-out, I/O trong listener
  |
  +-- publish latency thấp nhưng E2E cao?
  |      -> xem queue wait, worker saturation, broker lag
  |
  +-- p99 cao trong khi p50 ổn?
  |      -> xem GC pause, DB pool waits, network tail, lock contention
  |
  +-- throughput tăng nhưng error/drop tăng?
  |      -> đo success throughput, không chỉ attempted throughput
  |
  +-- sau commit callback chậm?
         -> đo phase AFTER_COMMIT riêng, theo dõi I/O ngoài transaction
```

Đừng cố tối ưu `publishEvent` nếu thực chất bottleneck nằm ở database pool hoặc HTTP client được gọi trong listener. Phần lớn hiệu năng của application events phụ thuộc công việc của listener và chính sách đồng bộ/bất đồng bộ, không chỉ chi phí Spring dispatch.

## 10. Transactional events và tính đúng của số đo

`@TransactionalEventListener` cho phép chạy theo phase như `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK` và `AFTER_COMPLETION`. Các phase này khiến "thời điểm hoàn tất event" cần được đặt rất rõ:

- **Publish time**: khi service gọi `publishEvent` bên trong transaction. Event chưa nhất thiết đã commit.
- **Before-commit callback**: còn ở trước commit; lỗi có thể ngăn commit.
- **After-commit handling**: callback chạy khi transaction đã commit. Latency nếu tính từ creation tới callback bắt đầu có thể bao gồm thời gian chờ transaction hoàn tất.
- **Rollback**: một event đã publish có thể không có `AFTER_COMMIT` completion; nếu bạn chỉ đo success, phải đếm cả event bị loại sau rollback theo outcome phù hợp.

Cách đo nên có metric tối thiểu phân biệt `phase` và `outcome` với tập giá trị thấp-cardinality. Một transaction commit thành công không có nghĩa I/O của một listener after-commit cũng thành công; việc handler lỗi sau commit không thể làm rollback lại transaction đó.

Với event liên dịch vụ, `Transactional Outbox` thêm một ranh giới: commit outbox row, relay publish, broker ack, consumer completion. "End-to-end" phải nêu rõ là tới mốc nào và cách xử lý retries/duplicates. Dùng event ID và correlation ID hợp lý, không xem hai lần broker delivery là hai domain facts khác nhau.

## 11. Định nghĩa SLO và capacity planning

Một ví dụ **minh họa mục tiêu**, không phải số đo Spring mặc định:

- Ở tải mục tiêu 2.000 events/giây, completion throughput phải duy trì gần offered rate trong cửa sổ dài.
- p95 end-to-end dưới 200 ms và p99 dưới 500 ms cho loại event có yêu cầu thời gian cụ thể.
- Error/drop/reject rate dưới ngưỡng được thống nhất.
- Backlog tăng đột biến phải trở về mức ổn định trong thời hạn yêu cầu.
- Chừa headroom CPU/threads/connections đủ cho burst và điều kiện một node bị mất.

Các mức trên chỉ là **ví dụ cách đặt SLO**, phải điều chỉnh theo loại event. Một event ghi metrics có thể chấp nhận xử lý trễ; event xác nhận thanh toán hoặc điều phối inventory có thể cần độ tin cậy/độ trễ hoàn toàn khác.

Khi đánh giá capacity, tăng pool size từ 4 lên 32 không chắc tăng throughput 8 lần: có thể bị giới hạn bởi DB connections, CPU, locks, network, fan-out hoặc chính pool downstream. Vì vậy vẽ throughput và p95/p99 theo offered load để tìm điểm saturation thay vì chọn thread count theo trực giác.

## 12. Kiểm thử và tiêu chí QA cho phép đo

Nên có các test và điều kiện kiểm tra:

1. **Đếm đúng:** một event đo tạo đúng một publish sample và một completion sample với một listener đồng bộ phù hợp.
2. **Thất bại:** handler ném lỗi không bị tính vào success throughput; failure counter được tăng qua `catch/finally` thích hợp.
3. **Hai listeners:** một publisher call có thể tạo hai handler samples; dashboard không cộng nhầm thành hai events.
4. **Async:** thử nghiệm đợi mọi handler hoàn tất trước khi tính completion throughput; không chỉ đếm submitted tasks.
5. **Retry:** attempts tăng theo retry; unique event count/idempotent completions được phân loại riêng.
6. **Transaction:** đo AFTER_COMMIT handling trong transaction thật; rollback không bị tính như committed success.
7. **Queue saturation:** có giới hạn queue, đo rejection/backpressure, không mất metric khi bị quá tải.
8. **Timer units:** luôn chỉ rõ ms/s và `TimeUnit`, không cộng nanoseconds với milliseconds.
9. **Percentiles:** xác nhận histogram/percentiles đã được bật, bucket phù hợp và sample count đủ lớn.
10. **Tag privacy/cardinality:** không đưa order ID, email, user ID, IP hoặc secret vào các nhãn metric.
11. **Reproducibility:** ghi JVM, heap, GC, CPU, workload, warm-up, thời gian đo, số lần chạy và môi trường.
12. **Measurement overhead:** không kết luận từ một run; phân tích độ biến thiên, dùng JMH khi đo code path cực ngắn.

Không dùng chỉ số "tối đa event/s" mà bỏ qua lỗi và backlog. Mục tiêu hiệu năng đúng là **công việc nghiệp vụ hoàn tất với latency, tính đúng và độ tin cậy đáp ứng yêu cầu**.

## 13. Các lỗi phổ biến

**Lỗi 1 — Dùng `publishEvent` trả về làm "đã xử lý xong" trong async.** Khi listener chạy trên executor, publisher có thể đã trả về nhưng event vẫn ở queue. Đo handler completion riêng.

**Lỗi 2 — Đếm mỗi listener call thành một domain event.** Fan-out làm tổng invocation lớn hơn số event logic; giữ metric publish và metric handle riêng.

**Lỗi 3 — Chỉ xem mean latency.** Độ trễ p95/p99 và lỗi/timeouts có thể xấu dù average trông ổn.

**Lỗi 4 — Không warm-up.** Tính cả quá trình tạo context, JIT/connection setup vào steady-state throughput làm so sánh lệch.

**Lỗi 5 — Benchmark bằng `println` cho từng event.** Console I/O làm lấn át chi phí dispatch/handler.

**Lỗi 6 — Tạo label bằng event ID.** Micrometer/Prometheus phải giữ một chuỗi metric cho nhiều giá trị tag, gây high cardinality và nguy cơ lộ dữ liệu.

**Lỗi 7 — Tin rằng `@EventListener` tự có Observation.** Spring Framework không tự tạo Observation cho callback; instrument riêng khi cần.

**Lỗi 8 — Không đo rejected/failed events.** Một hệ thống có tốc độ publish cao vì từ chối nhiều work không phải một hệ thống có throughput thành công tốt.

**Lỗi 9 — So sánh hai benchmark khác workload.** Khác kích thước payload, số listener, logging, JVM/GC/DB khiến kết quả không thể dùng kết luận thay đổi Spring code.

**Lỗi 10 — Chỉ đo trên một JVM khi production có broker.** Phải tách outbox, relay, broker lag và consumer latency; không dùng `System.nanoTime` xuyên host.

**Lỗi 11 — Tối ưu throughput bằng queue vô hạn.** Tốc độ submit cao trước mắt có thể đổi lấy OOM và end-to-end latency ngày càng lớn.

**Lỗi 12 — Tính p95 cluster bằng trung bình p95 các node.** Percentile không được cộng gộp trực tiếp; dùng histogram tổng hợp phù hợp.

## 14. Câu hỏi tự kiểm tra

1. **Throughput khác latency như thế nào?** — Throughput là số công việc hoàn tất mỗi giây; latency là thời gian một công việc mất.
2. **Publish rate có thể cao hơn completion throughput không?** — Có, nhất là khi có queue và listener chậm.
3. **`publishEvent` trong mặc định đồng bộ đo được gì?** — Thời gian dispatch cộng thời gian các listener đồng bộ.
4. **Vì sao publish latency trong async không đủ?** — Nó thường chỉ đo enqueue/dispatch, không đo queue wait và handler execution.
5. **Nên dùng đồng hồ nào cho duration trong một JVM?** — `System.nanoTime()` hoặc Timer API phù hợp.
6. **Có thể truyền `nanoTime` sang JVM khác để tính E2E không?** — Không, không có gốc thời gian chung có ý nghĩa.
7. **P95/p99 có tự xuất hiện khi tạo `Timer` không?** — Không phải ở mọi backend/cấu hình; cần hỗ trợ distribution statistics/histogram.
8. **Vì sao không dùng event ID làm tag metric?** — Cardinality cao và dễ lộ thông tin.
9. **Listener AFTER_COMMIT chạy chậm có thể rollback DB đã commit không?** — Không.
10. **Một event có ba listener đồng bộ, có bao nhiêu publisher calls?** — Có thể chỉ một; handler invocations là đại lượng khác.
11. **Tăng số thread có luôn tăng throughput tuyến tính không?** — Không; có thể nghẽn tài nguyên chia sẻ.
12. **Một benchmark tuyên bố 10.000 event/s cần công bố những gì?** — Workload, môi trường, window, success count, latency percentiles, errors/backlog và cách đo.

## Tài liệu tham khảo

- [Spring Framework — Application Events & @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework 6.2.8 — SimpleApplicationEventMulticaster Javadoc](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer — Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer — Distribution Summaries and Histograms](https://docs.micrometer.io/micrometer/reference/concepts/distribution-summaries.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
