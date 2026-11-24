# Quản lý lịch gửi, tài nguyên nền và đóng registry khi dừng ứng dụng

Micrometer có thể tạo công việc nền để gửi metrics định kỳ, trong khi chính ứng dụng cũng có thể dùng scheduler cho batch job, refresh cache hoặc tác vụ nghiệp vụ có ghi metrics. Các công việc này cần chu kỳ phù hợp, executor có giới hạn và quy trình dừng rõ ràng. Nếu bỏ quên lifecycle, ứng dụng có thể giữ thread hoặc network client sau khi dừng, mất dữ liệu chưa gửi, chạy job trùng trên nhiều replica hoặc tiếp tục ghi meter vào registry đã đóng.

Cần phân biệt ba cơ chế: push registry tự lên lịch publish; pull registry như Prometheus chờ hệ thống giám sát scrape; còn `@Scheduled` là lịch chạy công việc của ứng dụng. Chúng có thể cùng tồn tại nhưng có chủ sở hữu và cách đóng khác nhau.

## 1. Ba loại lịch chạy cần phân biệt

| Cơ chế | Ai kích hoạt? | Công việc | Vòng đời |
|---|---|---|---|
| Push registry scheduler | Registry hoặc exporter | Gom và gửi metrics theo step | Thuộc registry/exporter |
| Pull scrape | Prometheus hoặc collector | Đọc snapshot metrics qua endpoint | Thuộc hệ thống giám sát |
| Application scheduler | Spring hoặc executor của ứng dụng | Chạy batch, refresh, cleanup, polling | Thuộc application context hoặc service |

Với Prometheus pull, ứng dụng không cần tạo một scheduler chỉ để đẩy metrics. Prometheus chủ động gọi endpoint scrape theo chu kỳ cấu hình ở Prometheus server. Mỗi lần scrape, registry cung cấp snapshot hiện tại; Gauge thường được đọc tại thời điểm scrape.

Với push registry, implementation thường có lịch publish theo step. Registry gom các phép đo trong cửa sổ thời gian rồi gửi tới backend. Một số registry tự quản lý scheduler và thread; một số cần được start theo API của implementation hoặc được framework khởi tạo.

`@Scheduled` của Spring phục vụ công việc ứng dụng. Ví dụ, job đồng bộ tồn kho có thể chạy mỗi 30 giây và cập nhật Counter, Timer. Lịch job này không phải lịch export metrics của registry.

## 2. Step, export interval và scrape interval

Ba khái niệm thời gian có liên quan nhưng không đồng nghĩa:

- **Registry step:** khoảng thời gian push registry gom dữ liệu trước một lần publish.
- **Export interval:** chu kỳ exporter gửi batch dữ liệu tới collector/backend; tên và cách cấu hình phụ thuộc registry.
- **Scrape interval:** chu kỳ Prometheus hoặc collector pull endpoint.

Ví dụ, push registry có step 30 giây thì mỗi cửa sổ 30 giây được xuất theo semantics của registry. Nếu Prometheus scrape endpoint mỗi 15 giây thì scrape interval là 15 giây, không làm push registry tự đổi step thành 15 giây.

Chọn chu kỳ theo yêu cầu độ trễ quan sát và chi phí:

- Chu kỳ ngắn giúp dữ liệu mới xuất hiện sớm hơn nhưng tăng tần suất serialize, network và ingest.
- Chu kỳ dài giảm tần suất gửi nhưng làm dashboard và alert cập nhật chậm hơn.
- Scrape quá nhanh có thể đọc cùng một trạng thái nhiều lần mà không đem lại thêm giá trị.
- Step và scrape interval không cần bằng nhau, nhưng phải hiểu cách backend tổng hợp dữ liệu theo từng cửa sổ.

Không giả định mọi registry xử lý counter, timer và histogram theo cùng cách. Step registry có thể xuất delta theo cửa sổ, trong khi registry khác giữ cumulative state. Kiểm tra semantics của backend đang dùng trước khi diễn giải rate hoặc reset.

## 3. Cấu hình lịch publish của push registry

Với push registry, step thường được cấu hình qua config của registry hoặc property do Spring Boot cung cấp. Tên property khác nhau giữa Datadog, Wavefront, StatsD, OTLP và các implementation khác; dùng đúng tài liệu của registry và phiên bản dependency.

Một số implementation có API start/stop hoặc scheduler riêng. Khi tự tạo registry, cần khởi động publisher theo lifecycle mà implementation yêu cầu và dừng nó khi registry không còn được dùng. Không gọi start nhiều lần cho cùng một registry nếu API không cho phép.

Với Spring Boot, ưu tiên để auto-configuration quản lý registry và publisher. Không tự tạo một scheduler thứ hai chỉ để gửi lại cùng meter. Nếu cần tùy chỉnh thread factory, step hoặc export behavior, dùng hook cấu hình mà registry hỗ trợ thay vì can thiệp vào thread nội bộ.

Với Prometheus pull, không cấu hình một push scheduler cho PrometheusMeterRegistry chỉ để phục vụ scrape. Hãy expose endpoint và cấu hình Prometheus scrape ở phía server.

## 4. Quản lý scheduler và executor dùng chung

Mỗi scheduler hoặc exporter có thể sở hữu thread, queue, timer, socket và client riêng. Nên quản lý chúng theo vòng đời cấp ứng dụng:

- Tạo executor một lần khi application context khởi động.
- Chọn pool size theo số lượng và thời gian chạy của task.
- Dùng queue có giới hạn cho executor xử lý công việc được submit; với scheduler, giới hạn số trigger được đăng ký và tránh tạo lịch động vô hạn.
- Đặt thread name prefix để dễ nhận diện trong thread dump.
- Định nghĩa hành vi khi queue đầy hoặc task bị từ chối.
- Dừng nhận task mới và chờ task đang chạy hoàn tất khi shutdown.

Không tạo `ScheduledExecutorService` trong mỗi request hoặc mỗi lần ghi metric. Không đăng ký meter mới với tên/tag động mỗi lần task chạy; đăng ký meter một lần rồi tái sử dụng reference.

Nếu exporter có scheduler riêng, để exporter quản lý scheduler đó. Scheduler của application job chỉ nên phục vụ các job ứng dụng. Chỉ hợp nhất scheduler khi thư viện và lifecycle cho phép, đồng thời bảo đảm một task chậm không làm trễ việc gửi metrics.

## 5. Chạy application job bằng Spring @Scheduled

Spring hỗ trợ `@Scheduled` để chạy công việc theo fixed delay, fixed rate hoặc cron. Cần bật scheduling và dùng một bean do Spring quản lý.

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
class SchedulingConfiguration {
}
~~~

Ví dụ job refresh dữ liệu có ghi nhận kết quả:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class InventoryRefreshJob {
    private final InventoryService inventoryService;
    private final MeterRegistry registry;
    private final Counter completed;
    private final Counter failures;
    private final Timer duration;

    public InventoryRefreshJob(
            InventoryService inventoryService,
            MeterRegistry registry) {
        this.inventoryService = inventoryService;
        this.registry = registry;
        this.completed = registry.counter("inventory.refresh.completed");
        this.failures = registry.counter("inventory.refresh.failures");
        this.duration = registry.timer("inventory.refresh.duration");
    }

    @Scheduled(fixedDelay = 30_000)
    public void refresh() {
        Timer.Sample sample = Timer.start(registry);

        try {
            inventoryService.refresh();
            completed.increment();
        } catch (RuntimeException error) {
            failures.increment();
            throw error;
        } finally {
            sample.stop(duration);
        }
    }
}
~~~

Ví dụ trên đo thời gian mỗi lần chạy, tăng Counter thành công sau khi service hoàn tất và tăng Counter lỗi nếu có exception. Registry và meter được inject/tạo ở constructor; mỗi lần chạy chỉ cập nhật meter đã đăng ký.

Trong ứng dụng thật, hãy định nghĩa rõ cách xử lý exception của scheduled task. Ghi log hoặc phát cảnh báo khi job thất bại; không âm thầm bỏ lỗi khiến job ngừng hoạt động hoặc dữ liệu cũ kéo dài mà không ai biết.

## 6. Fixed delay, fixed rate và cron

| Kiểu lịch | Mốc tính thời gian | Phù hợp |
|---|---|---|
| fixedDelay | Tính từ lúc lần chạy trước hoàn tất | Job cần khoảng nghỉ sau mỗi lần chạy |
| fixedRate | Theo mốc bắt đầu định kỳ | Job cần nhịp chạy đều |
| cron | Theo biểu thức thời gian lịch | Job theo giờ/ngày/tuần |

Ví dụ:

~~~java
@Scheduled(fixedDelay = 30_000)
void refreshAfterPreviousRun() {
    refreshService.refresh();
}

@Scheduled(fixedRate = 60_000)
void sampleAtRegularRate() {
    samplingService.sample();
}

@Scheduled(cron = "0 0/5 * * * *")
void reconcileEveryFiveMinutes() {
    reconciliationService.run();
}
~~~

Với fixedDelay 30 giây, lần kế tiếp được lên lịch sau khi lần trước kết thúc và chờ thêm 30 giây. Với fixedRate 60 giây, scheduler cố gắng giữ nhịp theo mốc định kỳ; nếu một lần chạy kéo dài, lần kế tiếp có thể bị trễ. Cơ chế scheduler của Spring/JDK không mặc định chạy đồng thời hai lần của cùng một periodic task, nhưng nhiều trigger, nhiều bean, nhiều replica hoặc việc submit công việc sang executor bất đồng bộ vẫn có thể tạo chồng lấn.

Dùng fixedDelay cho polling hoặc refresh có thời gian chạy thay đổi. Dùng fixedRate khi cần nhịp định kỳ. Dùng cron cho lịch theo giờ lịch và timezone. Với job dài, hãy đo duration và kiểm soát overlap rõ ràng thay vì chỉ tăng pool size.

## 7. Cấu hình thread pool cho scheduled tasks

Spring có thể dùng `ThreadPoolTaskScheduler` để chạy các method `@Scheduled`. Pool size mặc định có thể không phù hợp nếu nhiều job cùng chạy hoặc một job mất nhiều thời gian.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration
class JobSchedulerConfiguration {

    @Bean
    ThreadPoolTaskScheduler taskScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(3);
        scheduler.setThreadNamePrefix("application-jobs-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        scheduler.setAwaitTerminationSeconds(30);
        return scheduler;
    }
}
~~~

Nếu bean này là scheduler mặc định cho Spring scheduling, mọi method `@Scheduled` dùng scheduler đó sẽ chia sẻ pool. Chọn pool size theo tổng thời gian chạy và số job có thể đến cùng lúc. Đặt pool quá nhỏ làm job chờ; đặt quá lớn làm tăng thread, stack memory và tranh chấp CPU.

Không dùng scheduler thread để thực hiện công việc blocking kéo dài nếu còn nhiều job cần chạy đúng giờ. Có thể để scheduled method chỉ kích hoạt công việc và chuyển phần xử lý sang một executor riêng có giới hạn. Khi làm vậy, cần theo dõi queue, rejection và bảo đảm task bất đồng bộ không bị submit vô hạn.

`ThreadPoolTaskScheduler` có lifecycle do Spring quản lý. Cấu hình chờ task hoàn tất khi shutdown giúp giảm nguy cơ dừng giữa chừng; thời gian chờ cần phù hợp với giới hạn dừng của container hoặc orchestrator.

## 8. Ngăn job chồng lấn trong cùng một instance

Nếu một job có thể chạy lâu hơn chu kỳ mong muốn, hãy xác định chính sách khi lần trước chưa xong:

- Bỏ qua lần kích hoạt mới.
- Chờ lần trước hoàn tất.
- Đưa lần mới vào queue có giới hạn.
- Cho phép chạy song song nếu nghiệp vụ an toàn.

Ví dụ dùng AtomicBoolean để bỏ qua lần mới khi job đang chạy:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

@Component
public class ReconciliationJob {
    private final ReconciliationService reconciliationService;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public ReconciliationJob(ReconciliationService reconciliationService) {
        this.reconciliationService = reconciliationService;
    }

    @Scheduled(fixedRate = 60_000)
    public void run() {
        if (!running.compareAndSet(false, true)) {
            return;
        }

        try {
            reconciliationService.reconcile();
        } finally {
            running.set(false);
        }
    }
}
~~~

Đây là khóa trong một JVM. Nó không ngăn hai replica cùng chạy job. Nếu task được submit sang executor bất đồng bộ, cờ phải bao trùm toàn bộ thời gian xử lý thật, không chỉ thời gian submit.

Nếu bỏ qua lần chạy, nên có metric như `reconciliation.skipped` để vận hành biết lịch đã bị bỏ qua. Đừng tăng Counter thành công cho lần không thực hiện.

## 9. Job chạy trên nhiều replica

Mỗi instance của ứng dụng thường có scheduler riêng. Nếu triển khai 4 replica và mỗi replica có một `@Scheduled(cron = ...)`, cùng một job có thể chạy 4 lần vào thời điểm đó.

Điều này phù hợp với công việc cần xử lý độc lập theo từng instance hoặc từng partition. Nhưng với tác vụ toàn cục như đối soát toàn bộ dữ liệu, gửi báo cáo hằng ngày hoặc cleanup một tập dữ liệu dùng chung, chạy trùng có thể gây duplicate side effect và tăng tải database.

Các cách phối hợp:

- **Distributed lock:** chỉ một instance giữ lock được phép chạy trong một thời điểm.
- **Leader election:** chỉ leader thực hiện công việc toàn cục.
- **Partitioning:** chia dữ liệu theo shard để mỗi instance xử lý phần riêng.
- **Idempotency:** thiết kế thao tác an toàn khi cùng một công việc được thực hiện lại.

Lock cần có lease/timeout và cơ chế phục hồi nếu instance giữ lock bị crash. Không dùng AtomicBoolean hoặc synchronized để thay distributed lock.

Nếu job thực sự chạy trên mọi replica, metrics nên phản ánh đúng phạm vi. Ví dụ Counter theo instance có thể cộng lại ở backend để ra tổng số lần xử lý; nhưng nếu job đáng lẽ chỉ chạy một lần toàn cục, tổng Counter cao hơn dự kiến là dấu hiệu cần điều tra chứ không phải chỉ là vấn đề hiển thị.

## 10. Gauge không cần scheduler riêng để đọc giá trị

Gauge thường đọc giá trị của object được theo dõi khi registry scrape hoặc khi backend yêu cầu giá trị. Không cần tạo một scheduled task chỉ để gọi Gauge mỗi vài giây nếu nguồn dữ liệu đã có thể đọc trực tiếp.

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.atomic.AtomicInteger;

@Component
public class QueueMetrics {
    private final AtomicInteger pendingJobs = new AtomicInteger();

    public QueueMetrics(MeterRegistry registry) {
        Gauge.builder(
                "jobs.pending",
                pendingJobs,
                AtomicInteger::get
            )
            .description("Số job đang chờ xử lý")
            .register(registry);
    }

    public void updatePendingJobs(int value) {
        pendingJobs.set(value);
    }
}
~~~

Giữ reference tới object được Gauge quan sát trong bean có vòng đời ổn định. Một số Gauge giữ weak reference; nếu object bị garbage collection, Gauge có thể trả về giá trị không còn hữu ích.

Chỉ dùng scheduler để refresh nguồn dữ liệu khi việc đọc nguồn đó thực sự cần chạy định kỳ, ví dụ gọi API ngoài hoặc tổng hợp trạng thái từ hệ thống khác. Khi đó, tách metric cho lần refresh thành công, thất bại, thời lượng và thời điểm refresh gần nhất.

## 11. Ghi metrics cho trạng thái job và lỗi nền

Metrics giúp phân biệt job không chạy, job chạy chậm, job thất bại và job bị bỏ qua. Một bộ meter hữu ích có thể gồm:

| Meter | Ý nghĩa |
|---|---|
| `job.run.completed` | Số lần job hoàn tất |
| `job.run.failed` | Số lần job thất bại |
| `job.run.skipped` | Số lần bỏ qua do đang chạy hoặc không có lock |
| `job.run.duration` | Thời gian thực thi |
| `job.last.success.timestamp` | Thời điểm thành công gần nhất |
| `job.queue.depth` | Số công việc đang chờ |

Dùng tag có cardinality thấp như job name từ enum, outcome hoặc partition class. Không đưa job execution ID, payload ID hoặc exception message vào tag.

Gauge timestamp có thể dùng để cảnh báo khi lần thành công gần nhất quá cũ. Counter failure dùng để theo dõi xu hướng lỗi; Timer duration giúp phát hiện job kéo dài bất thường. Không chỉ kiểm tra Counter tăng mà bỏ qua việc job có còn chạy theo lịch hay không.

Với nhiều replica, phân biệt metric theo instance nếu cần chẩn đoán, nhưng tránh tạo một tag tự do cho mỗi lần chạy. Các tag instance thường do common tags hoặc backend target labels quản lý.

## 12. Đóng MeterRegistry đúng vòng đời

`MeterRegistry` có lifecycle và có thể giữ tài nguyên tùy implementation. Push registry hoặc registry tích hợp exporter có thể quản lý publisher, scheduler, client và buffer. Khi registry không còn được dùng, gọi close theo ownership của nó để giải phóng tài nguyên.

Trong chương trình độc lập, có thể dùng try-with-resources:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
    registry.counter("demo.operations").increment();
}
~~~

Với Spring Boot, MeterRegistry thường là bean do auto-configuration quản lý. Inject và sử dụng bean đó; không gọi `registry.close()` từ controller, scheduled job hoặc service nghiệp vụ. Application context sẽ quản lý destruction theo lifecycle của bean.

Nếu tự tạo registry như một bean riêng, khai báo destroy method hoặc cơ chế lifecycle tương ứng để đóng đúng một lần:

~~~java
import org.springframework.context.annotation.Bean;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

@Bean(destroyMethod = "close")
MeterRegistry customMeterRegistry() {
    return new SimpleMeterRegistry();
}
~~~

Đoạn này chỉ dành cho registry do ứng dụng tự sở hữu. Không tạo thêm registry riêng nếu registry auto-configured đã đáp ứng nhu cầu.

## 13. Thứ tự graceful shutdown

Khi ứng dụng dừng, registry cần còn hoạt động trong lúc các request hoặc background task cuối cùng vẫn có thể ghi meter. Một trình tự shutdown hợp lý:

1. Đánh dấu instance không còn nhận traffic mới và ngừng nhận công việc mới.
2. Hủy lịch kích hoạt job mới hoặc dừng scheduler của ứng dụng.
3. Chờ request và job đang chạy hoàn tất trong giới hạn thời gian.
4. Nếu exporter hỗ trợ flush rõ ràng, thực hiện flush cuối khi network và collector vẫn còn sẵn sàng.
5. Đóng các executor do ứng dụng sở hữu và các tài nguyên nền không còn được dùng.
6. Đóng registry/exporter để dừng publisher, giải phóng buffer và client.

Thứ tự thực tế phụ thuộc framework và quan hệ dependency giữa các bean. Đảm bảo scheduled job không còn ghi vào registry sau khi registry đóng. Nếu task phụ thuộc MeterRegistry, để lifecycle của task kết thúc trước lifecycle của registry.

Không giả định `close()` luôn gửi hết dữ liệu còn trong buffer. Hành vi final flush khác nhau giữa registry và exporter. Nếu cần bảo đảm gửi batch cuối, kiểm tra API của implementation và gọi flush khi được hỗ trợ; nếu không có bảo đảm đó, thiết kế shutdown với giới hạn mất dữ liệu có thể chấp nhận.

Shutdown cũng cần có timeout. Container thường chỉ cho process một khoảng grace period trước khi gửi tín hiệu kill. Thời gian chờ job, flush exporter và đóng client phải nằm trong ngân sách đó.

## 14. Dừng ScheduledExecutorService tự quản lý

Nếu ứng dụng tự tạo executor ngoài Spring, chính ứng dụng phải dừng nó. Mẫu shutdown:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

class ExecutorShutdown {
    private static final Logger logger = LoggerFactory.getLogger(ExecutorShutdown.class);

void stopExecutor(ExecutorService executor) {
    executor.shutdown();

    try {
        if (!executor.awaitTermination(20, TimeUnit.SECONDS)) {
            executor.shutdownNow();

            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                logger.warn("Executor did not terminate");
            }
        }
    } catch (InterruptedException interrupted) {
        executor.shutdownNow();
        Thread.currentThread().interrupt();
    }
}
}
~~~

`shutdown()` ngừng nhận task mới và cho task đã submit cơ hội hoàn tất. `shutdownNow()` yêu cầu các task đang chạy dừng bằng interrupt và trả về các task chưa bắt đầu; task chỉ dừng nếu code hợp tác với interruption.

Không bỏ qua InterruptedException rồi tiếp tục chạy như chưa có gì. Khôi phục interrupt flag để tầng lifecycle phía trên có thể xử lý tín hiệu dừng.

Nếu dùng Spring-managed scheduler hoặc executor bean, để Spring quản lý shutdown theo cấu hình bean. Không gọi shutdown thủ công từ nhiều component khác nhau vì có thể dừng pool khi component khác vẫn cần dùng.

## 15. Kiểm tra tài nguyên nền khi vận hành

Các dấu hiệu nên theo dõi:

- Số thread tăng dần sau mỗi lần deploy hoặc reload context.
- Scheduled task bắt đầu trễ so với lịch.
- Queue hoặc số task chờ tăng liên tục.
- Job duration tăng, vượt chu kỳ hoặc vượt shutdown timeout.
- Push exporter báo lỗi gửi, retry kéo dài hoặc buffer tăng.
- Scrape duration tăng khi số meter/series tăng.
- Application shutdown bị kéo dài hoặc process bị kill trước khi hoàn tất.
- Registry vẫn được truy cập sau khi context đã đóng.

Đặt thread name rõ ràng như `application-jobs-` hoặc tên do exporter cung cấp để phân biệt thread trong thread dump. Có thể dùng binder phù hợp để theo dõi executor metrics, nhưng cần tránh instrument chính scheduler bằng một job quá dày làm tăng thêm tải.

Khi một job chạy chậm, kiểm tra cả thời gian xử lý, queue wait, downstream latency và lock contention. Chỉ tăng pool size có thể làm nhiều công việc đồng thời tranh CPU hoặc database hơn mà không giải quyết nguyên nhân.

## 16. Các lỗi thường gặp

- **Nhầm scrape interval với push registry step:** hai lịch thuộc hai phía khác nhau.
- **Tạo scheduler riêng cho từng meter:** lãng phí thread và làm lifecycle phức tạp.
- **Tạo registry trong mỗi job:** meter bị phân mảnh và tài nguyên khó thu hồi.
- **Để scheduled task chạy trên mọi replica dù chỉ cần một lần:** side effect bị lặp.
- **Dùng fixedRate cho job dài mà không có chính sách overlap:** task có thể bị trễ hoặc bị submit chồng qua executor khác.
- **Không theo dõi task bị bỏ qua:** lịch có thể không đạt tần suất mong muốn mà dashboard không thể hiện.
- **Dùng Gauge với object không còn reference mạnh:** giá trị Gauge có thể mất nguồn dữ liệu.
- **Đóng registry trước khi job dừng:** lần ghi cuối có thể thất bại hoặc bị mất.
- **Giả định close luôn flush:** dữ liệu cuối có thể chưa được gửi tùy implementation.
- **Đóng cùng executor từ nhiều bean:** component khác có thể mất tài nguyên đang dùng.
- **Không dành shutdown timeout:** orchestrator có thể kill process trước khi flush và đóng tài nguyên.
- **Nuốt lỗi scheduled task:** job ngừng tạo kết quả nhưng không có tín hiệu vận hành rõ ràng.

## 17. Checklist triển khai

- [ ] Phân biệt push registry schedule, pull scrape và application scheduling.
- [ ] Chọn registry step/export interval theo backend và độ trễ mong muốn.
- [ ] Không tạo push scheduler cho Prometheus pull chỉ để scrape.
- [ ] Dùng scheduler/executor có vòng đời cấp ứng dụng.
- [ ] Chọn pool size và chính sách queue/rejection phù hợp.
- [ ] Dùng fixedDelay, fixedRate hoặc cron theo semantics công việc.
- [ ] Đo duration, completed, failed và skipped cho background job.
- [ ] Kiểm soát overlap trong instance và duplicate giữa các replica.
- [ ] Dùng distributed lock, leader election hoặc partitioning khi job toàn cục.
- [ ] Giữ reference của Gauge source và tránh scheduler chỉ để đọc Gauge.
- [ ] Để Spring quản lý MeterRegistry bean do Boot tạo.
- [ ] Đóng custom registry đúng một lần theo ownership.
- [ ] Dừng job trước khi đóng registry và exporter.
- [ ] Flush cuối chỉ khi implementation hỗ trợ và còn thời gian.
- [ ] Kiểm tra thread, queue, exporter failure và shutdown duration.

Quản lý lịch gửi và tài nguyên nền là một phần của vận hành metrics. Push registry cần publisher theo step, Prometheus pull chỉ cần endpoint được scrape, còn job nghiệp vụ thuộc scheduler của ứng dụng. Dùng chung tài nguyên có giới hạn, đo trạng thái job, kiểm soát chạy trùng và dừng công việc trước khi đóng MeterRegistry để tránh rò rỉ thread, mất dữ liệu cuối hoặc ghi meter sau shutdown.



