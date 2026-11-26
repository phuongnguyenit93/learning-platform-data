# Warm-up và thời gian khởi động trong Spring Batch

## 1. Vì sao throughput tốt vẫn có thể khiến job trễ SLA?

Giả sử một hệ thống dữ liệu chạy job đối soát mỗi 15 phút. Khi đã ổn định, bốn worker xử lý được 20.000 bản ghi/giây. Tuy nhiên, một lần chạy chỉ có 120.000 bản ghi, nên phần xử lý hữu ích mất khoảng 6 giây; trong khi đó manager mất 12 giây để khởi động, worker mới mất 18 giây để sẵn sàng, kết nối cơ sở dữ liệu cần thêm thời gian, rồi job mới commit chunk đầu tiên. **Thời gian chờ trước khi có kết quả có thể lớn hơn thời gian xử lý dữ liệu.**

Lần chạy thứ hai trên cùng các worker thường nhanh hơn. Nhưng không thể vì vậy kết luận tăng số worker là giải pháp: nếu mỗi worker mới đều cần một giai đoạn warm-up, scale ngang liên tục có thể kéo dài thời điểm hệ thống thực sự tăng throughput. Ngược lại, giữ quá nhiều worker và connection pool luôn hoạt động cũng làm lãng phí CPU, bộ nhớ và connection.

Bài **“Warm-up và thời gian khởi động”** thuộc chương **Thông lượng** trong module `SPRING_BATCH_SCALING_OPERATIONS`. Mục tiêu của module là mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán; học cách đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế.

Sau bài học, bạn có thể:

- Phân biệt **startup latency**, **readiness latency**, **time to first successful chunk**, **ramp-up time**, **steady-state throughput** và **end-to-end job wall-clock**.
- Nhận diện các nguồn warm-up: JVM class loading/JIT, Spring context, dependency initialization, JDBC connection pool, database cache, driver, broker, object storage và autoscaling.
- Đo các cột mốc khởi động bằng Spring Boot events, listener của Spring Batch và metric theo đúng phạm vi transaction.
- Thiết kế benchmark **cold start** và **warm start** có thể lặp lại mà không sử dụng cache ấm để che chi phí production.
- Chọn worker luôn chạy hay scale theo đợt, cân bằng latency, throughput, tài nguyên và SLA.
- Thiết kế health/startup/readiness cho manager và worker; tránh launch job trước khi hạ tầng thực sự sẵn sàng.
- Giữ nguyên input snapshot, checkpoint và idempotency khi restart hoặc khi job bị chạy lại sau một đợt triển khai.

**Phạm vi kỹ thuật:** ví dụ Java chủ yếu theo **Java 17+, Spring Batch 5.2.x và Spring Boot 3.x**; phần vận hành sử dụng PostgreSQL/JDBC, HikariCP và Kubernetes khi thích hợp. Các cấu hình Spring Batch 6.x/Boot 4.x cần đối chiếu tài liệu đúng version vì API, tự động cấu hình và hành vi khởi chạy job có thể thay đổi.

## 2. Định nghĩa các mốc thời gian trước khi benchmark

Một hệ thống có manager Spring Batch và worker chạy độc lập cần tách nhiều đồng hồ:

~~~mermaid
sequenceDiagram
    participant S as Scheduler
    participant M as Manager process
    participant B as Broker / metadata
    participant W as Worker process
    participant D as Business DB
    S->>M: Kích hoạt workload / tạo process
    Note over M: JVM + Spring context startup
    M->>B: Kết nối metadata, publish request
    Note over W: Worker pod start, JVM warm-up
    W->>B: Consumer sẵn sàng nhận request
    B-->>W: Giao request
    W->>D: Mở reader/ghi chunk đầu
    D-->>W: Chunk commit thành công
    Note over W,D: Throughput tăng dần và ổn định
    W->>B: StepExecution hoàn tất
    B-->>M: Job kết thúc theo lifecycle
    M-->>S: Kết quả job / trạng thái
~~~

### 2.1. Các metric cần tách

| Tên metric/khái niệm | Bắt đầu tính từ | Kết thúc khi | Điều nó **không** chứng minh |
|---|---|---|---|
| **Process startup time** | Process/container bắt đầu | JVM/application đạt mốc startup xác định | Worker đã kết nối broker hoặc xử lý được item |
| **Spring context/startup time** | `SpringApplication.run` bắt đầu | Context refresh/Boot startup event | Scheduler hoặc các job đã hoàn tất |
| **Readiness latency** | Pod/process bắt đầu | Sẵn sàng phục vụ chức năng được định nghĩa | Mọi downstream có thể chịu tải tối đa |
| **Time to first work** | Workload được yêu cầu | Worker bắt đầu xử lý execution/chunk đầu | Chunk đã commit |
| **Time to first successful chunk (TTFSC)** | Workload được yêu cầu hoặc step bắt đầu, theo định nghĩa | Chunk đầu tiên hoàn thành thành công theo lifecycle | Toàn bộ job đã hoàn tất; mọi side effect ngoài DB đã durable |
| **Ramp-up time** | Bắt đầu xử lý | Throughput đạt ngưỡng ổn định đã quy định | Thông lượng sẽ giữ nguyên khi dữ liệu/lock phân bố thay đổi |
| **Steady-state throughput** | Cửa sổ đo sau ramp-up | Cửa sổ đo kết thúc | Tổng thời gian chạy job nhỏ nhất |
| **End-to-end wall-clock** | Scheduler phát yêu cầu/đến lịch | Job đạt kết quả cuối cùng có thể dùng | Tất cả event downstream đã được tiêu thụ nếu không thuộc điều kiện hoàn tất |

Tên metric chỉ có ý nghĩa khi bạn **ghi rõ origin/destination của nó**. Ví dụ “startup = 10 giây” là mơ hồ: 10 giây từ container created đến process started, từ `main()` đến `ApplicationReadyEvent`, hay từ scheduler đến worker có thể commit?

### 2.2. Một phương trình vận hành

Nếu một run có nhiều pha nối tiếp tương đối rõ:

\[
T_{\mathrm{job,wall}} \approx
T_{\mathrm{queue/start}}+
T_{\mathrm{app/init}}+
T_{\mathrm{worker/wait}}+
T_{\mathrm{first\ work}}+
T_{\mathrm{remaining\ work}}+
T_{\mathrm{finalize}}
\]

Đây là **mô hình kiểm tra nguồn trễ**, không phải khẳng định mọi pha độc lập: manager có thể boot đồng thời worker, DB có thể ấm lên trong lúc xử lý và checkpoint/flush diễn ra xen kẽ. Không cộng các timer chồng lấn rồi tuyên bố đó là wall-clock thực.

### 2.3. Ví dụ có số liệu minh họa

| Thành phần | Job ngắn, worker mới | Job ngắn, worker đã ấm |
|---|---:|---:|
| Lên lịch và cấp phát process | 7 s | 1 s |
| Spring/application khởi tạo | 11 s | 0 s nếu worker vẫn chạy |
| Đợi consumer/DB readiness | 9 s | 1 s |
| Thời gian xử lý hữu ích | 6 s | 6 s |
| Kết thúc và đối soát | 2 s | 2 s |
| **Tổng minh họa (giả định nối tiếp)** | **35 s** | **10 s** |

Đây **không phải kết quả benchmark Spring Batch** mà là ví dụ để nhận ra: một workload nhỏ có thể nhạy với startup hơn throughput khi chạy ổn định. Với workload hàng giờ, chi phí boot chỉ chiếm tỷ lệ nhỏ và không nên tối ưu một phần trăm của tổng runtime bằng cách đánh đổi correctness.

## 3. Cold start, warm start và steady state là ba trạng thái khác nhau

Không có một trạng thái “warm” duy nhất. Một worker có thể ấm ở một tầng và lạnh ở tầng khác.

| Tầng | Cold có thể là | Warm có thể là | Cách xác minh |
|---|---|---|---|
| **Container/image** | Node phải tải image, tạo filesystem/network | Image đã có ở node, pod được tạo nhanh | K8s pod events, pull time, scheduling latency |
| **JVM** | Class loading, bytecode verification, JIT chưa tối ưu | Class đã load, phương thức hot đã được compile | JVM startup/JFR/CPU profile, compilation data |
| **Spring context** | Bean creation, scanning, configuration, migration tasks | Context/bean còn sống trong process | Boot startup events và bước khởi tạo |
| **JDBC pool** | Chưa mở connection/TLS/auth | Có connection hợp lệ sẵn trong pool | Hikari active/idle/total, acquire p95 |
| **DB buffer cache** | Dữ liệu/index chưa ở shared buffers/OS cache | Các trang thường dùng đã cached | Buffer read/hit, I/O metrics, query latency |
| **Query plan / prepared statements** | Driver/server chưa có trạng thái prepared/cache phù hợp | Có thể tái sử dụng trong connection sống lâu | Server/driver stats, SQL behavior |
| **Broker/client** | DNS, TLS, authentication, channel/consumer setup | Connection và subscriptions hoạt động | Consumer count, connection/subscribe time |
| **Object storage/file system** | DNS/TLS, metadata lookup, file cold read | Connection/cache đã sẵn | Request latency, cache hit, object read |
| **Application logic** | Regex/parser/class/codepath chưa dùng | Data structures/cache có sẵn | Phân rã stage timers, JFR |

**Khởi động app nhanh không có nghĩa DB cache đã ấm.** Ngược lại, app mới chạy trên một máy có DB cache sẵn có thể đạt `first chunk` nhanh, nhưng đó không phải cold benchmark “từ số không” ở database.

### 3.1. Những nguồn biến động ngoài ứng dụng

- Kubernetes scheduling, node autoscaling, image pull và container runtime.
- CPU throttling hoặc memory pressure trên pod.
- DNS, service discovery, TLS handshake và secret retrieval.
- Flyway/Liquibase/DDL migration nếu được chạy khi startup; không khuyến khích mỗi worker cùng migrate schema.
- Spring bean tạo connection hoặc query trong constructor/`@PostConstruct`.
- JVM garbage collection/initial heap sizing, CPU frequency scaling và tiered compilation.
- DB được phục vụ bởi cache từ job trước hoặc cạnh tranh với workload khác.
- Remote worker pod readiness chưa đồng nghĩa broker consumer đã đăng ký.

Mọi benchmark phải ghi **pod/node/image**, JVM, database version, tình trạng cache, input snapshot, query plan và số worker. Nếu thiếu các điều kiện này, “warm-up giảm 40%” rất dễ chỉ là hiệu ứng image cache hoặc một node tình cờ rảnh.

## 4. JVM warm-up: class loading, JIT và tiered compilation

HotSpot JVM không nhất thiết chạy mọi đoạn code với cùng hiệu năng ngay sau `main()`:

1. Class được load và verify khi cần.
2. Method có thể bắt đầu ở interpreter hoặc mã biên dịch ở một mức tối ưu.
3. JIT/tiered compilation thu thập profile và biên dịch code hot ở mức cao hơn.
4. Optimized code và inline caches có thể làm throughput tăng sau một số lần xử lý.
5. Garbage collection, allocation, branch profile và số loại object khác nhau có thể làm thông lượng biến động.

### 4.1. Đọc đường cong throughput

~~~text
rows/s
  ^
  |                         ____________ steady band
  |                    ____/
  |               ____/
  |         _____/
  |________/
  +----------------------------------------> thời gian từ lúc bắt đầu xử lý
       JVM/app       warm-up      steady
~~~

Hình trên **chỉ minh họa**. Không phải mọi job đều tăng dần: nhiều job nhanh ngay, có job giảm vì DB cache churn, GC hoặc contention. **Không gọi bất kỳ độ dốc nào là “JIT” nếu không có bằng chứng profiler/compilation.**

### 4.2. Warm-up phải dùng codepath đại diện

Việc chạy 1.000 phép cộng số nguyên trước job không làm ấm logic parse JSON, JDBC mapping, JSON serializer hay writer SQL chính của workload. Để xem hiệu ứng JIT, warm-up phải thực hiện **cùng kiểu codepath và dữ liệu đại diện**, nhưng không được gây duplicate business side effect.

Những cách an toàn hơn:

- Benchmark trên **staging** với snapshot riêng, không ghi ra bảng production.
- Phân biệt warm-up **đọc và tính toán không có side effect** với chạy thật; không giả định read-only warm-up sẽ làm nóng writer/JDBC commit path.
- Dùng Java Flight Recorder (JFR), JIT compilation information, CPU profile và GC logs để xác nhận giai đoạn nào thật sự chiếm thời gian.
- Nếu job ngắn, tính cả warm-up vào SLA thay vì loại bỏ khỏi số liệu để tạo benchmark đẹp.

### 4.3. Các công cụ có thể thay đổi startup

| Kỹ thuật | Mục tiêu | Đánh đổi |
|---|---|---|
| **Class Data Sharing (CDS/AppCDS)** | Giảm một phần chi phí class loading/memory | Cần cấu hình archive/runtime phù hợp; mức cải thiện phải đo |
| **Spring AOT** | Chuẩn bị trước một phần công việc cấu hình/bean metadata | Hỗ trợ và giới hạn theo Spring/Boot version, native reflection/resource hints |
| **GraalVM Native Image** | Giảm JVM startup/footprint trong nhiều workload | Khác biệt GC, peak performance, native image compatibility và build complexity |
| **CRaC/checkpoint restore** trong môi trường hỗ trợ | Khôi phục process sau một điểm khởi tạo | File descriptors/connections/threads/secrets cần lifecycle restore đúng; không coi snapshot kết nối DB còn hợp lệ |
| **Giữ worker sống lâu** | Tránh khởi động lại JVM/connection trên mỗi job | Tốn tài nguyên idle, cần chống stale connection và memory leak |

Không có kỹ thuật nào luôn tốt nhất. Với một job chạy mỗi 15 phút, worker dài hạn có thể hợp lý; với job chỉ chạy một lần mỗi đêm, tối ưu image pull, application startup và đo thời gian thực tế thường có ích hơn giữ hàng trăm pod chờ.

## 5. Spring Boot lifecycle: "started", "ready" và job chạy khi startup

Trong Spring Boot, các mốc lifecycle thường được quan sát qua events như `ApplicationStartedEvent` và `ApplicationReadyEvent`. `ApplicationStartedEvent` xảy ra sau context refresh nhưng **trước** `ApplicationRunner`/`CommandLineRunner`; `ApplicationReadyEvent` xảy ra **sau** các runners đó.

Đây là điểm rất dễ nhầm khi Spring Boot tự launch Spring Batch job.

### 5.1. Startup event không tự chứng minh worker ready

~~~mermaid
flowchart TD
    A["main() / SpringApplication.run"] --> B[Create ApplicationContext / initialize beans]
    B --> C[ApplicationStartedEvent]
    C --> D[ApplicationRunner / CommandLineRunner]
    D --> E[ApplicationReadyEvent]
    E --> F{Worker thực sự có thể xử lý work?}
    F -->|Có| G[Readiness / consumer-healthy]
    F -->|Chưa| H[Chờ broker, metadata DB, readiness custom]
~~~

Nếu một `ApplicationRunner` khởi chạy job **đồng bộ** và đợi job hoàn tất, `ApplicationReadyEvent` có thể được phát **sau toàn bộ job**, không còn phù hợp để đo “thời gian ứng dụng sẵn sàng trước job”. Với asynchronous launch, event có thể xuất hiện sớm hơn trong khi job vẫn chạy; cần đo execution riêng.

Spring Boot 3.x có cơ chế auto-launch Spring Batch jobs thông qua hạ tầng runner khi được bật và cấu hình phù hợp; khi nâng phiên bản hoặc thay đổi cấu hình, **kiểm tra thực tế job được launch bởi ai và ở giai đoạn nào**. Tránh để job vừa được Boot autolaunch vừa được scheduler/API hoặc một runner khác launch lần nữa.

### 5.2. Quy ước timestamp cần chọn trước

Ba thời điểm nên lưu trong structured logs:

- `processStart`: lúc process bắt đầu theo runtime/orchestrator, hoặc `mainEnteredAt` nếu chỉ có instrumentation trong Java.
- `appStarted/ready`: mốc Spring events, có ghi event name và timestamp.
- `jobRequested/jobStarted/firstChunkCommitted/jobCompleted`: mốc thuộc **job execution**, cần liên kết `jobExecutionId`.

Không trừ hai giá trị `System.nanoTime()` của **hai JVM khác nhau**. Monotonic clock chỉ phù hợp tính khoảng thời gian **trong cùng process**; nếu cần end-to-end qua scheduler/manager/worker, dùng UTC event timestamps với đồng bộ clock phù hợp, trace spans hoặc phép đo ở một hệ thống điều phối trung tâm.

## 6. Đo Spring startup đúng cách bằng code

Ví dụ đặt mốc `main()`, `ApplicationStartedEvent` và `ApplicationReadyEvent`:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BatchApplication {
    // Dùng đo trong một JVM, từ lúc class được khởi tạo.
    static final long MAIN_CLASS_INIT_NANOS = System.nanoTime();

    public static void main(String[] args) {
        SpringApplication.run(BatchApplication.class, args);
    }
}
~~~

~~~java
import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupMilestoneLogger {
    private static final Logger log =
            LoggerFactory.getLogger(StartupMilestoneLogger.class);

    @EventListener
    public void onStarted(ApplicationStartedEvent event) {
        logMilestone("spring_started");
    }

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        logMilestone("spring_ready_after_runners");
    }

    private static void logMilestone(String milestone) {
        long elapsed = System.nanoTime()
                - BatchApplication.MAIN_CLASS_INIT_NANOS;
        log.info("milestone={} elapsed_ms={}", milestone,
                TimeUnit.NANOSECONDS.toMillis(elapsed));
    }
}
~~~

Hai class ở cùng package (hoặc bổ sung import phù hợp); code minh họa Spring Boot app có SLF4J và event listener. **`MAIN_CLASS_INIT_NANOS` đo từ lúc class được khởi tạo**, không phải từ khi Kubernetes bắt đầu schedule pod, container start hay toàn bộ JVM launcher. Muốn đo *process* startup đầy đủ, lấy thêm timestamps từ container runtime/orchestrator.

Điểm mạnh của cách này là có cột mốc tương đối rõ. Hạn chế: `ApplicationReadyEvent` **không nhất thiết là consumer-ready**. Nếu worker còn phải đợi broker subscription hoặc custom resource async, cần một điều kiện readiness riêng; nếu job được khởi chạy đồng bộ qua runner thì ready event có thể đến sau job.

### 6.1. Spring Boot ApplicationStartup và profiler

Spring Boot hỗ trợ các cơ chế theo dõi các bước startup (chẳng hạn `ApplicationStartup`/`BufferingApplicationStartup` trong những phiên bản phù hợp) và có thể kết hợp Actuator/JFR. Những công cụ này hữu ích để tìm:

- Bean creation hoặc classpath scanning đắt.
- Migration/config initialization kéo dài.
- Framework/config/proxy creation.
- Thread blocking hay I/O trong factory methods.

Không dùng một profiler nặng trên mọi pod production nếu overhead vượt lợi ích. Chọn sampling/profiling theo môi trường, và đối chiếu với **wall-clock** đo từ bên ngoài ứng dụng.

## 7. Đo time to first successful chunk trong Spring Batch

Một worker được gọi là “sẵn sàng” theo health endpoint nhưng không thể đọc snapshot hoặc commit chunk đầu tiên thì **chưa thực sự chứng minh pipeline hoạt động**. Để đo độ trễ hữu ích, cần biết khoảng thời gian từ lúc `StepExecution` bắt đầu tới chunk đầu tiên hoàn tất thành công.

### 7.1. Listener dùng concurrent map, an toàn với nhiều worker execution

Ví dụ Spring Batch 5.x:

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.ChunkListener;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.stereotype.Component;

@Component
public class FirstSuccessfulChunkListener
        implements StepExecutionListener, ChunkListener {

    private final MeterRegistry registry;
    private final ConcurrentMap<Long, Long> starts =
            new ConcurrentHashMap<>();

    public FirstSuccessfulChunkListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void beforeStep(StepExecution stepExecution) {
        Long id = stepExecution.getId();
        if (id != null) {
            starts.put(id, System.nanoTime());
        }
    }

    @Override
    public void afterChunk(ChunkContext context) {
        StepExecution stepExecution =
                context.getStepContext().getStepExecution();
        Long id = stepExecution.getId();
        if (id == null) {
            return;
        }

        // Atomic remove: chỉ ghi mẫu cho chunk thành công đầu tiên
        // của mỗi StepExecution, kể cả khi nhiều chunk chạy đồng thời.
        Long started = starts.remove(id);
        if (started != null) {
            registry.timer(
                    "batch.step.first.successful.chunk",
                    "step", stepExecution.getStepName())
                    .record(System.nanoTime() - started,
                            TimeUnit.NANOSECONDS);
        }
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        Long id = stepExecution.getId();
        if (id != null) {
            starts.remove(id);
        }
        return null; // Không thay ExitStatus đã có.
    }
}
~~~

Đăng ký listener cho một chunk step (minh họa đoạn builder, các bean khác do ứng dụng cung cấp):

~~~java
return new StepBuilder("workerStep", jobRepository)
        .<InputRow, OutputRow>chunk(200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .listener((StepExecutionListener) firstSuccessfulChunkListener)
        .listener((ChunkListener) firstSuccessfulChunkListener)
        .build();
~~~

`InputRow`/`OutputRow` là DTO của ứng dụng; đoạn builder giả định nằm trong method cấu hình với `jobRepository`, `transactionManager`, `reader`, `processor`, `writer` và `firstSuccessfulChunkListener` đã có. Việc cast các interface tránh nhầm overload khi class implement cả hai loại listener.

### 7.2. Metric này chứng minh được gì?

- `beforeStep` đánh mốc **bắt đầu execution**, không đo toàn bộ khoảng từ lúc scheduler yêu cầu tới khi worker process ra đời.
- `afterChunk` được gọi sau một chunk xử lý thành công theo lifecycle chunk; nó là **mốc proxy cho chunk đầu tiên hoàn tất**, không chứng minh mọi external API/message/file side effect đã durable nếu nằm ngoài transaction.
- `starts.remove(id)` giúp chỉ ghi **một sample/StepExecution** và tránh đếm nhiều chunk khi step multi-threaded. `ConcurrentMap` tránh race với nhiều execution trong cùng process.
- `afterStep` dọn entry khi step không có chunk thành công hoặc fail sớm. Một process crash sẽ mất map in-memory; **không sử dụng metric này làm checkpoint**.
- Dùng tag `stepName` có cardinality thấp; **không đặt `stepExecutionId` làm label của mọi time series** lâu dài. Đặt ID trong log/trace nếu cần điều tra từng run.

Metric ở trên là **step-start → first-successful-chunk latency**, không phải scheduler → first chunk. Để đo end-to-end cần thêm mốc job requested/queue dispatch và correlation ID ở manager/worker. Nếu bạn dùng một listener singleton trên nhiều job instances, map ID `StepExecution` vẫn tách mỗi execution; nếu có nhiều `JobRepository` độc lập tạo ID trùng trong một process, cần key kết hợp repository identity hoặc giới hạn scope listener.

### 7.3. Job không có chunk thì đo gì?

Tasklet step không có chunk lifecycle tương tự, nên cần đo **tasklet-start → tasklet-complete** hoặc milestone nghiệp vụ riêng. Với job chỉ chạy một SQL set-based `INSERT ... SELECT`, time to first chunk **không có nghĩa**; thay bằng time to first committed SQL unit hoặc time to completion.

## 8. Warm-up và readiness: phân biệt "sống", "sẵn sàng" và "chạy có ích"

Một service worker có thể qua được ba trạng thái:

1. **Process alive:** JVM còn chạy, HTTP health endpoint có thể trả lời.
2. **Service ready:** broker consumer/subscription và dependency bắt buộc đã sẵn sàng nhận work theo contract.
3. **Productively processing:** worker load đúng `StepExecution`, reader/messaging/DB hoạt động và chunk đầu tiên đã commit.

Các trạng thái này **không tự động bằng nhau**. Một health endpoint chỉ kiểm tra JVM sống không chứng minh worker có đúng metadata DB hoặc có thể xử lý message được giao.

### 8.1. Quy tắc cho manager và worker độc lập

- Manager có thể chạy sớm nếu broker durable queue lưu request an toàn, nhưng phải xử lý timeout và status khi worker chưa subscribe; không mặc định publish thành công có nghĩa execution đã bắt đầu.
- Worker phải cấu hình `JobRepository` đúng DB/schema dùng chung với manager nếu kiến trúc yêu cầu. `ResourcelessJobRepository` hoặc metadata store riêng trong một kiến trúc remote cần shared metadata sẽ không phù hợp.
- Readiness nên phản ánh dependency **cần thiết** cho khả năng nhận work, nhưng không làm endpoint liveness phụ thuộc DB/broker đang chậm để tránh pod bị kill hàng loạt khi dependency chung outage.
- Khi shutdown, ngừng nhận request mới, drain in-flight work theo chính sách, hoàn tất/rollback transaction rồi mới đóng connection.
- Queue có backlog cao ngay sau deploy **chưa đủ chứng minh worker chậm**: có thể worker chưa ready hoặc còn trong JVM/startup warm-up.

**Một readiness gate không phải distributed lock hay exactly-once protection.** Sau khi probe thành công, broker vẫn có thể redeliver, mạng vẫn có thể mất và execution có thể bị chạy lại. Idempotency/restart vẫn cần.

## 9. JDBC connection pool: warm sớm đến đâu là hợp lý?

Với JDBC, worker không nhất thiết có connection đã xác thực khi JVM báo khởi động. HikariCP có thể mở một số connection sẵn, tạo connection khi cần hoặc kiểm tra sức khỏe connection theo cấu hình. Lần đầu mượn connection có thể chịu DNS, TCP/TLS, database authentication, driver startup và connection validation.

### 9.1. Cấu hình minh họa cho worker dài hạn

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://business-db.internal:5432/batch
    hikari:
      pool-name: business-worker-pool
      maximum-pool-size: 8
      minimum-idle: 2
      connection-timeout: 30000
      validation-timeout: 5000
      max-lifetime: 1800000
      keepalive-time: 120000
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

Giá trị chỉ **minh họa capacity**; phải kiểm tra với số pod, concurrency, database headroom, database/network idle timeout và Hikari version. `maximumPoolSize=8` là trần **mỗi pool/pod**, không phải toàn cluster. `minimumIdle=2` là số connection idle mục tiêu, **không bảo đảm hai connection đã warm ở thời điểm consumer đầu tiên nhận message** nếu chưa xác minh readiness/warmup policy.

Nếu chạy 20 worker pod với `minimumIdle=5`, riêng mức idle mục tiêu đã lên tới 100 connection nếu mỗi pod đạt mục tiêu. Giữ pool ấm có **chi phí cố định** trong khi workload chưa chạy. Với DB server có giới hạn `max_connections`, cộng thêm manager pool, metadata pool, API và rolling deployment surge trước khi tăng `minimumIdle`.

### 9.2. Một phép ping DB có mục đích

Một worker có thể chạy một query nhẹ để xác minh **business database có thể truy cập**, ví dụ `SELECT 1`. Trong Spring Boot 3.x, một `ApplicationRunner` có thể làm việc đó **trước ApplicationReadyEvent**:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

@Component
public class BusinessDatabaseConnectivityCheck
        implements ApplicationRunner {
    private final JdbcTemplate businessJdbcTemplate;

    public BusinessDatabaseConnectivityCheck(
            @Qualifier("businessJdbcTemplate")
            JdbcTemplate businessJdbcTemplate) {
        this.businessJdbcTemplate = businessJdbcTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        Integer ok = businessJdbcTemplate.queryForObject(
                "SELECT 1", Integer.class);
        if (!Integer.valueOf(1).equals(ok)) {
            throw new IllegalStateException("Business DB unavailable");
        }
    }
}
~~~

Đây là **ví dụ cho deployment mà database là dependency bắt buộc khi startup**, không phải khuyến nghị chạy SQL từ mọi pod trong mọi tình huống. Ứng dụng cần tự cung cấp bean `businessJdbcTemplate` đúng datasource. Nếu còn một `ApplicationRunner` khác auto-launch job, thứ tự giữa các runners phải được kiểm soát/test; **không mặc định query ping chạy trước job** chỉ vì cả hai là runner.

Quan trọng: `SELECT 1` chỉ chứng minh connection có thể chạy **một câu SQL nhẹ**, **không** chứng minh schema metadata đúng, user có quyền update bảng nghiệp vụ, query plan ấm, constraint hợp lệ hay worker có thể commit chunk.

### 9.3. Warm cả business pool và metadata pool?

Nếu manager/worker chạy remote partitioning, `JobRepository` cần metadata store dùng chung. Có thể đo riêng:

- `metadata_pool_acquire_ms` để tải/cập nhật `StepExecution`.
- `business_pool_acquire_ms` cho reader/writer.
- `first_business_query_ms` và `first_metadata_query_ms` nếu cần.

Khi cả hai pool trỏ vào **cùng database instance**, tổng connection vẫn nằm dưới cùng giới hạn server. Không lập hai pool 20 connection rồi kết luận “có 20 connection tổng cộng”.

### 9.4. Prewarm và liveness khác nhau

`connectionTimeout` giới hạn thời gian mượn connection, không thay thế query/transaction/network timeout. Nếu DB chậm tạm thời, không nên biến liveness probe thành phụ thuộc trực tiếp vào DB để tất cả worker đồng loạt restart và gây **thundering herd** reconnect.

Readiness cần phản ánh khả năng nhận workload; với worker có message listener chạy không qua HTTP Service, **thành công của HTTP readiness probe không tự chặn broker giao message**. Nếu cần bảo đảm không nhận request trước khi pool/schema/consumer sẵn sàng, chính cơ chế start listener/consumer phải có gating tương ứng.

## 10. Database cache, SQL plan và "warm query" giả tạo

Một truy vấn lần đầu có thể chậm vì data pages/index pages chưa có trong PostgreSQL shared buffers hoặc OS page cache. Sau một lượt quét, dữ liệu có thể được cache, làm lượt thứ hai nhanh hơn mà Java code không đổi.

### 10.1. Khi nào cache ấm có lợi?

- Job lặp lại trên **cùng tập khóa/index nhỏ**, ví dụ bảng dimension/reference được truy vấn nhiều lần.
- Query có index selectivity tốt và thường đọc lại cùng page.
- Nhiều job dùng chung cached reference data mà không chiếm toàn bộ memory.

Ngược lại, một batch scan hàng trăm GB dữ liệu một lần có thể **làm cache churn**; cố prewarm toàn bộ tập dữ liệu chỉ khiến I/O xảy ra **trước** job chứ không giảm tổng I/O hữu ích.

### 10.2. Đo cache thay vì đoán

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, snapshot_key
FROM incoming_payments
WHERE snapshot_key = 'test-snapshot'
  AND id >= 10000
  AND id < 20000
ORDER BY id;
~~~

SQL ở đây giả định có bảng test chứa những cột tương ứng; **không yêu cầu tạo bảng mới** trong workspace. `EXPLAIN ANALYZE` **thực thi query** nên cần chạy trên staging/cửa sổ an toàn. Quan sát `shared hit/read`, plan, row count và latency; một query nhanh hơn sau lần đầu không chứng minh mọi sự khác biệt chỉ do database cache, vì JVM/driver/network cũng có thể thay đổi.

PostgreSQL có các cơ chế extension như `pg_prewarm` trong môi trường hỗ trợ, nhưng không nên bật hoặc quét cache production tự động trước mọi job. Cần cân nhắc **buffer eviction**, disk I/O, DBA approval và việc cache warm làm chậm các workload quan trọng khác.

### 10.3. Query plan và metadata startup

Prepared statements, server-side preparation và plan cache có thể làm những lần query sau khác lần đầu; tùy PostgreSQL/driver/session/SQL shape. Một query đầu tiên chậm cũng có thể là do:

- Connection/TLS/auth lần đầu.
- Cấu hình driver prepare threshold/metadata lookup.
- Database statistics stale hoặc query plan không phù hợp.
- Table/index bloated, storage cache lạnh.
- Lock wait do transaction khác.

**Đừng “sửa” khởi động chậm bằng cách chạy thử một câu INSERT trên business DB rồi rollback**, vì ngay cả khi rollback, câu SQL có thể làm nóng index, ghi WAL, kích hoạt một số side effects/sequence/trigger không có semantics rollback đơn giản; đây không phải warm-up vô hại.

## 11. Broker, object storage và cache ứng dụng

Không phải mọi chậm khởi động đều nằm ở JVM hay JDBC:

| Dependency | Chi phí lần đầu | Cần đo |
|---|---|---|
| RabbitMQ/JMS/Kafka client | DNS, TCP/TLS, auth, channel/consumer setup | Thời gian client connected/subscribed, failed reconnect |
| Object storage | DNS/TLS, metadata/listing, first GET/PUT latency | First request p95 và sustained requests/s |
| File system | Mount, permission, metadata lookup, cold file read | I/O queue, latency, page cache |
| Secrets/config service | Token retrieval, decryption, refresh | Latency startup và retry/backoff |
| HTTP/gRPC downstream | Connection pool, TLS, discovery, auth | First request vs steady request latency |
| Application in-memory cache | Load danh mục/reference data | Load bytes, memory, invalidation và correctness |

### 11.1. Readiness của message consumer

Một message client “đã connect” chưa hẳn đã **subscribe/consume thành công**. Với worker remote partitioning, phải bảo đảm:

1. Consumer được cấu hình đúng queue/topic/version contract.
2. Worker có `StepLocator`/worker step beans cần thiết.
3. Metadata DB chứa đúng `StepExecution` mà request tham chiếu.
4. Schema/serializer nhận được request thuộc version được hỗ trợ.
5. Consumer có capacity để xử lý, broker delivery/ACK/retry chính sách phù hợp.

Không tạo request “giả” trỏ tới một `stepExecutionId` không tồn tại chỉ để làm ấm `StepExecutionRequestHandler`: worker có thể fail, gây DLQ và làm nhiễu dashboard.

### 11.2. Cache dữ liệu tham chiếu

Một cách có thể hữu ích là load trước reference data **đã được version hóa** và thường dùng để processor không phải gọi DB/API từng item. Nhưng:

- Cache phải có nguồn dữ liệu và version/cutoff rõ.
- Nếu mỗi worker load 1 GB dictionary, 20 replicas có thể cần 20 GB RAM và tạo burst I/O.
- Eviction và restart phải trả về kết quả tương đương; không sử dụng cache chưa xác nhận để tính tiền/đối soát.
- Thay dữ liệu giữa job có thể khiến partition 1 và partition 2 tính trên **khác version**; cần snapshot hoặc consistent version contract.

Nếu warm cache mất 60 giây để giảm job processing chỉ 10 giây, đó không phải cải thiện end-to-end latency cho job một lần.

## 12. Worker dài hạn hay pod tạo theo từng job?

Hai lựa chọn đều hợp lý tùy tần suất và SLA.

### 12.1. Mô hình tạo pod mới cho mỗi lần chạy

~~~text
Scheduler → Kubernetes Job
   → schedule pod → image pull → JVM/Spring startup
   → kết nối metadata/broker/DB → xử lý → exit
~~~

Ưu điểm: cách ly workload, ít tài nguyên idle, dễ gắn image/config với job. Đánh đổi: **mỗi lần chạy phải trả startup cost**, chịu variation của node provisioning/image pull. Phù hợp khi workload lớn và chạy không thường xuyên; startup có thể được tính trước vào thời điểm lập lịch nếu SLA cho phép.

### 12.2. Mô hình worker Deployment chạy lâu

~~~text
Worker Deployment (sẵn sàng, consumer hoạt động)
         ↑               ↑
Manager Job 1          Manager Job 2
         └──── Broker / metadata ────┘
~~~

Ưu điểm: amortize JVM/Spring/DB/broker connection cost qua nhiều jobs; job ngắn có thể có TTFSC thấp hơn. Đánh đổi: pool/CPU/memory idle, stale connections, cache aging, version compatibility trong rolling deployment và khả năng một worker giữ state không mong muốn qua nhiều `StepExecution`.

### 12.3. Công thức break-even

Đặt:

- `S`: startup overhead mỗi lần chạy nếu tạo process mới.
- `R`: thời gian xử lý hữu ích khi worker ổn định.
- `F`: số lần chạy trong một khoảng vận hành.
- `C_idle`: chi phí giữ worker sẵn sàng trong khoảng ấy.

Về **độ trễ mỗi job**, nếu `S` lớn so với `R` thì worker dài hạn có thể cải thiện rõ. Về **chi phí hạ tầng**, phải so tổng CPU/memory/pool idle `C_idle` với chi phí khởi động lại `F×S` (đã quy đổi cùng đơn vị chi phí), cùng SLA và rủi ro.

Không lấy một phép cộng giây cộng USD làm kết luận; phân tích phải tách **thời gian**, **chi phí tài nguyên** và **ngân sách SLA**.

### 12.4. Độ trễ khi autoscale từ 0

Một worker pool scale-to-zero có thể tiết kiệm tài nguyên nhưng request đầu tiên phải đợi:

\[
T_{\mathrm{first\ result}}\gtrsim
T_{\mathrm{scale\ trigger}}+
T_{\mathrm{node/pod/start}}+
T_{\mathrm{worker\ ready}}+
T_{\mathrm{first\ commit}}
\]

Nếu broker queue có thể buffer request, điều này không nhất thiết làm mất message, nhưng SLA đầu tiên và queue age tăng. Một HPA nhìn CPU worker **không thể phát hiện sớm workload mới khi worker scale bằng 0 nếu chưa có event-driven scaler hoặc tín hiệu ngoài**; cần thiết kế scale trigger theo queue depth/age hoặc lịch job.

Không đánh giá autoscale chỉ bằng số pod cuối cùng. Ghi thời điểm scale signal, pod scheduled, image pulled, ready, consumer subscribed, first chunk committed và steady throughput.

## 13. Kubernetes: startup, liveness và readiness của worker

Đối với worker **long-running Deployment**, có thể dùng probes để tránh health system quá nóng vội khi startup:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: batch-partition-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: batch-partition-worker
  template:
    metadata:
      labels:
        app: batch-partition-worker
    spec:
      containers:
        - name: worker
          image: example/partition-worker:1.0.0
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 5
            failureThreshold: 24
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
            failureThreshold: 3
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              memory: 1024Mi
~~~

Đây là **manifest minh họa**, image không phải tên image triển khai thật. Yêu cầu ứng dụng có Spring Boot Actuator/probes bật và port/path đúng; không copy nguyên giá trị timeout/resources vào production mà không đo. `startupProbe` làm Kubernetes **tạm trì hoãn kiểm tra liveness/readiness cho tới khi startup probe thành công**, giúp process khởi động chậm có cơ hội hoàn tất trước khi bị liveness restart.

**Giới hạn quan trọng:** Kubernetes readiness probe điều khiển việc pod được đưa vào **Service endpoints**. Một worker nhận message trực tiếp từ broker **không nhất thiết phụ thuộc Service routing**, nên readiness=false **không tự ngăn consumer nhận request**. Cần đồng bộ việc start/stop message listener theo dependency readiness hoặc cấu hình khả năng nhận work độc lập.

### 13.1. Vì sao liveness không nên phụ thuộc DB/broker?

Nếu database outage 60 giây làm liveness của cả 50 pod chuyển thành FAILED, Kubernetes có thể restart tất cả worker, gây burst reconnect/image load và làm outage tệ hơn. Liveness nên phản ánh **process không thể tự phục hồi**; readiness/consumer gating có thể phản ánh dependency không khả dụng tạm thời theo chính sách phục hồi.

Với job worker đang giữ in-flight transaction, shutdown cần giới hạn thời gian drain, tránh nhận thêm work, và dựa vào **idempotency/restart** nếu pod bị kill trước khi commit.

### 13.2. Manager là Kubernetes Job, không phải worker service

Một manager one-shot có thể chạy dưới dạng Kubernetes `Job`:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: payment-batch-manager-20261125
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: manager
          image: example/payment-batch-manager:1.0.0
          env:
            - name: SPRING_BATCH_JOB_ENABLED
              value: "true"
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              memory: 1024Mi
~~~

Manifest chỉ minh họa **vòng đời one-shot**, không có JobParameters, secret, datasource, broker credentials, workload identity hoặc job selection. Ứng dụng cần truyền **identifying `JobParameters` cố định** cho snapshot và bảo đảm cơ chế launch đúng một job được định nghĩa. Tùy cách dùng Spring Boot Batch auto-run/runner, `SPRING_BATCH_JOB_ENABLED` có thể phải được kết hợp với cấu hình tên job và parameters riêng của ứng dụng.

**Kubernetes Job retry là retry container/workload**, không tự biến thành restart đúng `JobInstance` Spring Batch. Nếu pod manager được tạo lại và lại launch với parameters mới, có thể tạo một lần chạy mới và duplicate side effect. Cần định nghĩa contract giữa scheduler run ID, `JobInstance`, checkpoint và business idempotency.

### 13.3. Không nhầm "Ready" của manager với "COMPLETED" của job

Manager batch chạy xong rồi exit có thể **không cần HTTP readiness endpoint** như service dài hạn. Trạng thái cần quan sát là Kubernetes `Job` condition, process exit code và Spring Batch `JobExecution/ExitStatus`, theo thiết kế vận hành. ApplicationReadyEvent của Boot không phải chứng nhận batch completed trừ khi ứng dụng cố ý kết nối hai lifecycle đó và đã kiểm chứng.

## 14. Thời gian khởi động, partition skew và job wall-clock

Đối với một job partitioning, tổng runtime thường bị chi phối bởi **partition hoàn thành chậm nhất**, không chỉ worker trung bình:

~~~text
manager creates 8 partitions
  worker A (already warm): partition 0 → 40s
  worker B (new pod):      boot 15s + partition 1 → 65s
  worker C (already warm): partition 2 → 35s
  worker D (new pod):      boot 18s + partition 3 → 52s
  ... các partition khác

Job cannot complete until all required partitions complete.
~~~

Nếu workload lệch (một partition có 50% dữ liệu), nhanh hóa startup của ba worker rảnh không giải quyết partition nặng nhất. Một chiến lược scale hiệu quả cần đo **worker startup distribution**, partition skew, scheduling fairness và DB/CPU contention.

### 14.1. Phân biệt overhead cố định và tốc độ xử lý

Mô hình đơn giản:

\[
T_{\mathrm{total}} \approx S+\frac{N}{R_{\mathrm{steady}}}
\]

Với `S` là overhead cố định thực sự nằm trên critical path, `N` số item cần xử lý và `R_steady` throughput ổn định. Khi `N` nhỏ, giảm `S` thường đáng giá hơn tăng `R_steady`. Khi `N` lớn, tăng `R_steady` có thể quan trọng hơn.

**Đừng dùng công thức này nếu worker khởi động chồng lấn, partition skew lớn hoặc DB bão hòa mà không điều chỉnh mô hình.** Với parallel partitioning, phải xét critical path/worker chậm nhất và khả năng các pha chồng lên nhau.

### 14.2. Warm workers không cứu được bottleneck downstream

Nếu PostgreSQL WAL/disk hoặc hot row lock đang giới hạn 10.000 rows/s, việc giữ 100 worker JVM sẵn sàng có thể chỉ tạo 100 connection pool và nhiều transaction chờ. **Warm-up giảm startup overhead**, không tự tăng capacity ở nút thắt cuối.

Chỉ tăng worker sau khi đo throughput cùng CPU/IO/locks/pool; không đánh giá hiệu quả warming chỉ dựa vào JVM first-request latency.

## 15. Benchmark cold start và warm start không tự đánh lừa chính mình

Một benchmark có giá trị phải tách **app warm/cold** với **data cache warm/cold**. Nếu chỉ khởi động lại JVM trong khi PostgreSQL shared buffers, OS page cache và broker connection đã ấm, đó **không** phải toàn hệ thống cold start.

### 15.1. Bốn nhóm chạy cần phân biệt

| Profile thử nghiệm | Worker/JVM | DB cache | Mục đích |
|---|---|---|---|
| **A: App cold, DB warm** | JVM/process mới | Cache dữ liệu đã ấm | Đo startup app, class/JIT, connection setup |
| **B: App warm, DB warm** | Process còn sống, codepath đã chạy | Cache đã ấm | Baseline throughput và job latency tốt nhất có điều kiện |
| **C: App cold, DB cold-ish** | JVM/process mới | DB/OS cache ít chứa tập dữ liệu | Đo gần trạng thái sau reboot/deploy lớn, trong staging có kiểm soát |
| **D: App warm, DB cold-ish** | Process còn sống | Tập dữ liệu khác chưa được cache | Phân biệt bottleneck dữ liệu/IO với JVM |

`Cold-ish` nhấn mạnh rằng **khó tạo một trạng thái “database hoàn toàn lạnh” đáng tin cậy** bằng vài thao tác thủ công. Không xóa OS cache, restart PostgreSQL production hoặc tắt cache của hệ thống để tạo benchmark; chỉ thực hiện thao tác có ảnh hưởng toàn DB trong staging/lab với quyền điều hành phù hợp.

### 15.2. Cùng snapshot và mục tiêu ghi

Với job ghi business data:

- Dùng **immutable input snapshot** và cùng tập business IDs.
- Đảm bảo target trước mỗi lượt có cùng trạng thái: trống với `INSERT only`, hoặc được reset/reseed an toàn trong staging nếu so UPSERT.
- Giữ schema, index, query plan, JDK, JDBC driver, Spring Boot/Batch version và transaction policy.
- Ghi số worker pod, requests/limits, image cache state và node placement.
- Không để một lượt warm-up đầu **điền đầy target** rồi lượt sau chỉ chạy `DO NOTHING`; throughput giả có thể tăng vì không còn write thật.
- Đo unique keys và checksum của **kết quả đã commit**, không chỉ `writeCount`.

### 15.3. Chuỗi thời gian cần lấy

~~~text
t0  Scheduler triggers run
t1  Pod scheduled / process started
t2  Spring ApplicationStartedEvent
t3  Spring ApplicationReadyEvent (có thể sau runner)
t4  Worker consumer subscribed + metadata/business deps ready
t5  Manager dispatches first StepExecution request
t6  Worker begins StepExecution / first item read
t7  First successful chunk completes
t8  Throughput enters predefined steady band
t9  Last required partition completed
t10 Manager reports final job outcome
~~~

Không phải job nào cũng có **cùng thứ tự tuyệt đối**: t4 có thể xảy ra trước t3 nếu message listener tự khởi động khi context refresh; t5 có thể xảy ra trước t4 nếu queue buffer request; worker cũng có thể có sẵn từ trước t0. **Lưu timestamp theo tên event và kiểm tra trình tự thực**, không ép hệ thống vào một mô hình lý tưởng.

### 15.4. Định nghĩa steady-state có thể kiểm chứng

Ví dụ định nghĩa vận hành (phải tùy chỉnh theo dữ liệu):

> Hệ thống đạt trạng thái tương đối ổn định khi committed unique items/s trong ít nhất ba cửa sổ liên tiếp 30 giây nằm trong một dải ±10% quanh median cùng run, **và** CPU/DB/GC/queue backlog không đang biến thiên mạnh.

Đây là **tiêu chí minh họa**, không phải chuẩn Spring Batch. Với job chỉ chạy 10–20 giây, không nên tuyên bố có “steady-state 90 giây”; thay vào đó báo **toàn bộ wall-clock** và time-to-first-commit. Với partition data skew, throughput có thể thay đổi vì độ khó dữ liệu chứ không liên quan warm-up; cần phân tích theo partition/phase.

### 15.5. Ma trận benchmark

| Lần đo | Worker | Process state | Snapshot/DB state | Metric chính |
|---|---:|---|---|---|
| 1 | 1 | Cold | Target reset | TTFSC, job wall-clock |
| 2 | 1 | Warm | Target reset | Warmup delta và committed rate |
| 3 | 4 | Cold | Target reset | Startup fan-out, pod schedule p95 |
| 4 | 4 | Warm | Target reset | Steady throughput, DB contention |
| 5 | 8 | Cold | Target reset | Pod/resource ramp và queue lag |
| 6 | 8 | Warm | Target reset | Thông lượng tăng hay lock/WAL bão hòa? |

Mỗi dòng là một **kịch bản thí nghiệm**, không phải kết quả. Lặp nhiều lần và báo median cùng phân bố p95/p99 thời gian startup. Khi chỉ chạy một lần và thấy lượt thứ hai nhanh hơn, chưa đủ để kết luận **JIT** là nguyên nhân.

### 15.6. Mẫu báo cáo cần ghi

| Nhóm | Giá trị cần thu |
|---|---|
| Build và runtime | Image digest, Spring Batch/Boot, JDK, architecture, CPU/memory limits |
| Orchestration | Scheduler timestamp, pod pending/pull/start, node placement, surge |
| Boot startup | `ApplicationStartedEvent`, `ApplicationReadyEvent`, runner/job autolaunch mode |
| Worker readiness | Consumer subscribe time, metadata DB/business DB connection health |
| Batch timeline | Job/StepExecution ID, first chunk, first commit, last partition, total wall time |
| Throughput | Unique committed items/s, rolling rate, p50/p95 ramp duration |
| JDBC | Hikari active/idle/pending, acquisition p95, query latency |
| Database | Buffer hit/read, WAL/IO, lock wait, CPU, connection headroom |
| JVM | Class loading/JIT/GC khi cần, heap, CPU throttling |
| Business | Input snapshot key, unique target keys, checksum, restart pass/fail |

## 16. Ví dụ đọc số liệu: cùng throughput ổn định, SLA khác nhau

Giả sử hai cấu hình đều đạt 25.000 records/s khi worker đã ấm, nhưng mỗi run chỉ có 200.000 records:

| Metric minh họa | Cấu hình X | Cấu hình Y |
|---|---:|---:|
| Startup và readiness trên critical path | 30 s | 5 s |
| Thời gian xử lý hữu ích ở mức ổn định | 8 s | 8 s |
| Hoàn tất/đối soát | 2 s | 2 s |
| **Wall-clock (giả định các pha nối tiếp)** | **40 s** | **15 s** |
| Steady-state throughput | 25.000/s | 25.000/s |

Y cải thiện SLA mà **không cần tăng throughput lúc ấm**. Có thể đạt bằng worker tồn tại sẵn, image pull tối ưu, bớt initialization không cần thiết hoặc connection readiness có kiểm soát.

Với 100 triệu records, phần xử lý khoảng nhiều phút đến hàng giờ; giảm startup 25 giây có thể không đáng bằng tối ưu database throughput 10% hoặc giảm partition skew. **Độ ưu tiên tối ưu phụ thuộc job duration và SLO, không phụ thuộc cảm giác “startup quá lâu”.**

### Chi phí warm-up trên nhiều pod

Nếu một worker cần 10 giây CPU-bound warm-up và bạn đồng thời tạo 40 pod, tổng nhu cầu CPU lúc ramp-up có thể gây **throttling** trên node, kéo dài warm-up của chính các pod ấy. Đôi khi ramp-up tuần tự theo một nhịp giới hạn giúp cluster ổn định hơn và **time-to-full-capacity** tốt hơn so với burst 40 JVM cùng khởi tạo.

Không suy ra một số pod optimal từ ví dụ: đo CPU throttling, scheduling, image pull time và time-to-consumer-ready khi thử các mức replica.

## 17. Khi nào tối ưu startup có hại?

| Cách làm dễ hấp dẫn | Rủi ro thực tế | Giải pháp kiểm chứng |
|---|---|---|
| Mọi pod warm pool tới `maximumPoolSize` | Database cạn connection khi scale/rolling deploy | Budget theo `maxReplicas × pools` và headroom |
| Chạy query đọc toàn bảng để “làm ấm cache” | Chiếm I/O, đẩy dữ liệu cache của app khác ra | Chỉ warm reference/small hot set có lợi ích đo được |
| Gọi writer INSERT/UPDATE rồi rollback để warm | Sequence/WAL/trigger/lock side effects, tải DB | Dùng staging hoặc warm codepath không side effect |
| Auto-launch job từ nhiều replicas | Duplicate `JobExecution` hoặc business writes | Single launch authority, identifying parameters/idempotency |
| Liveness phụ thuộc database | DB outage gây restart storm | Liveness tập trung vào process, readiness/consumer gating riêng |
| Giữ toàn bộ worker luôn ấm | Lãng phí CPU/memory/connection | Tính break-even theo SLA/cost, có idle scaling policy |
| Giảm logging và mọi health check | Mất dấu readiness/timeout thật, khó điều tra | Sampling và metric có mục tiêu, không bỏ kiểm tra thiết yếu |
| Dùng retry vô hạn khi broker/DB chưa ready | Kéo dài startup, spam dependency và DLQ | Backoff/jitter bounded, báo trạng thái rõ |
| Tạo cache mutable ở singleton rồi dùng cho mọi partition | Race, dữ liệu không nhất quán qua job | Immutable/versioned cache hoặc `@StepScope` phù hợp |
| Tắt durability/unique constraints để đẩy first chunk nhanh | Mất dữ liệu hoặc xử lý trùng khi crash | Giữ business invariant, tối ưu SQL/IO thay thế |

### Startup nhanh không đồng nghĩa an toàn hơn

Một worker có thể bỏ qua kiểm tra schema để sớm báo ready, sau đó thất bại khi load `StepExecution` đầu tiên. Một manager có thể phát request trước khi broker consumer đúng version subscribe; queue backlog tăng nhưng dashboard chỉ ghi “app ready=2 s”.

**Tối ưu đúng là rút ngắn critical path mà vẫn bảo toàn các điều kiện cần thiết trước khi nhận work.** Phải giữ log/metric đủ để phát hiện lỗi dependency và khả năng phục hồi theo hợp đồng.

## 18. Retry, restart và warm state không được trở thành nguồn sự thật

Warm-up thường tạo cache, pooled connections, compiled code hoặc in-memory reference data. Những thứ ấy **không phải persistent checkpoint** của Spring Batch.

### 18.1. Khi worker crash sau khi đã warm

Worker mới có thể:

- JIT/classloading lại từ đầu.
- Tạo pool/broker subscriptions mới.
- Nhận một `StepExecution` đã chạy dở.
- Đọc lại chunk đã commit hoặc chưa commit tùy `JobRepository`/business transaction.

**Kết quả nghiệp vụ vẫn phải giống nhau** dù cache/JIT/pooled connection trước đó không còn. Cần:

1. Identifying `JobParameters` và input snapshot cố định.
2. `ExecutionContext`/ItemStream checkpoint lưu bền vững theo model.
3. Reader có sort key/snapshot đúng, không phụ thuộc vị trí in-memory của cursor cũ.
4. Writer idempotent khi item hoặc chunk được phát lại.
5. Worker cũ thực sự dừng hoặc có fencing/lease khi cùng work unit có nguy cơ chạy đồng thời.
6. Các cache/reference datasets có **version** phù hợp với cùng job instance, không tự đổi chỉ vì worker restart.

### 18.2. Thay code giữa restart có thể phá checkpoint

Ví dụ reader cũ có tên `ordersReaderV1`, bản mới đổi thành `ordersReaderV2`. Các key trong `ExecutionContext` có thể không còn được tìm đúng; dù startup bản mới nhanh hơn, restart vẫn có thể xử lý sai số bản ghi.

Không đổi tên job/step/reader/partition một cách tùy tiện khi các instance cũ cần resume. Nếu muốn nâng cấp version qua nhiều worker, cần migration/restart rehearsal và kế hoạch drain, không chỉ rolling deploy sang image mới.

### 18.3. Metadata và business output thuộc resource nào?

Nếu business DB, metadata `JobRepository`, broker và object storage là các tài nguyên độc lập, không tự giả định chúng cùng commit nguyên tử. Một worker có thể ghi business output rồi crash trước khi metadata/ACK được xác nhận. Warm-up và startupProbe **không xử lý** lỗi này.

Một ví dụ idempotent với PostgreSQL:

~~~sql
INSERT INTO processed_events
    (snapshot_key, event_id, payload)
VALUES
    (:snapshotKey, :eventId, :payload)
ON CONFLICT (snapshot_key, event_id) DO NOTHING;
~~~

Đây là **SQL minh họa**, giả định bảng `processed_events` có unique constraint `(snapshot_key,event_id)` và payload nhất quán trong immutable snapshot. `DO NOTHING` không kiểm tra duplicate ID có payload khác; cần checksum/version validation nếu business contract yêu cầu.

### 18.4. Tên trạng thái

Một worker readiness check thành công không có nghĩa `StepExecution` là `COMPLETED`. Broker ACK không chứng minh business effect đã hoàn tất theo mọi topology. JVM startup/health đều là **trạng thái vận hành**, còn Spring Batch `BatchStatus/ExitStatus` và business reconciliation là các nguồn thông tin khác nhau.

## 19. Runbook khi job đầu tiên sau deploy rất chậm

### Bước 1 — Ghi thời điểm và identity

Lấy scheduler trigger, pod schedule/start, image digest, Java/Boot/Batch version, `ApplicationStartedEvent`, `ApplicationReadyEvent`, worker subscribe time, `jobExecutionId`, `stepExecutionId` và first successful chunk.

### Bước 2 — Xác nhận có đúng là cold-start delay

So sánh hai run trên **cùng input snapshot và target state**. Nếu run 2 chỉ có `DO NOTHING` trên dữ liệu đã ghi, đó là hai workload khác nhau; không thể kết luận warm-up đã cải thiện.

### Bước 3 — Phân loại chậm ở tầng nào

- **Pod Pending/ImagePullBackOff:** scheduler/node capacity, registry/network/image size.
- **JVM/Bean initialization:** classloading, bean creation, startup runners, schema migration.
- **First DB connection:** DNS/TLS/auth, Hikari acquisition/creation, database saturation.
- **First SQL:** buffer/cache, SQL plan, lock, I/O; không mặc định JIT.
- **Consumer not ready:** broker connect/subscribe, schema/serializer, metadata DB.
- **Chunk đầu chậm nhưng các chunk sau nhanh:** có thể JIT/cache/pool hoặc dữ liệu đầu nặng hơn.
- **Mọi chunk chậm:** xem DB/CPU/IO/locks/partition skew, không gọi đó là startup-only.

### Bước 4 — Kiểm tra liveness/readiness và runner

Xem Boot `ApplicationReadyEvent` có bị trì hoãn vì job được auto-launch đồng bộ không. Kiểm tra `startupProbe` có đủ ngưỡng cho warm-up hợp lệ; readiness có khớp điều kiện thực của broker consumer hay chỉ là HTTP healthy.

### Bước 5 — Xác định nguyên nhân gốc bằng số liệu

Lấy JFR/Boot startup metrics nếu chậm trong JVM; Hikari active/idle/pending và time-to-connection nếu chậm DB; PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` trên staging nếu nghi cold query; broker consumer count nếu chậm phân phát; Kubernetes events nếu chậm cấp pod.

### Bước 6 — Chọn biện pháp giảm trễ

| Root cause | Hướng khắc phục phù hợp |
|---|---|
| Image pull/node scheduling chậm | Image/cache/node pre-provision, workload priority hợp lệ |
| Spring bean init thừa | Loại bỏ công việc startup không cần, cấu hình/lazy init có chủ đích |
| JVM startup nhiều lần cho job ngắn | Worker dài hạn, AOT/CDS/native nếu benchmark đạt và tương thích |
| DB connection đầu chậm | Hikari minimumIdle hợp lý, kiểm tra TLS/DB, giới hạn reconnect bursts |
| Cache dữ liệu tham chiếu lạnh | Load versioned hot set nếu lợi ích vượt chi phí |
| Manager dispatch trước worker subscribe | Durable queue/consumer gating, đo queue age và readiness |
| Một partition nặng | Cân tải/partition manifest, không chỉ tăng JVM startup speed |
| WAL/lock/DB bão hòa | Tối ưu SQL/transaction/worker concurrency, không warm-up giả |

### Bước 7 — Khôi phục đúng dữ liệu

Nếu worker bị restart nhiều lần do liveness hoặc DB outage, xác minh `JobRepository` và business output trước khi re-dispatch. Restart cùng `JobInstance`/snapshot, kiểm tra idempotency và giữ partition plan. Không xóa metadata status hoặc tạo `run.id` mới để che lỗi khởi động.

### Bước 8 — Báo cáo SLA đầy đủ

Báo end-to-end wall time, TTFSC, startup p50/p95, ramp-up, steady rate và business correctness. Không báo riêng “steady throughput tăng 20%” trong khi job ngắn bị startup kéo dài gấp đôi.

## 20. Ma trận kiểm thử cold/warm và resilience

| Kịch bản | Cách dựng trên staging | Kỳ vọng |
|---|---|---|
| Cold app / warm DB | Khởi động JVM mới, giữ DB cache | Đo được Boot startup, first chunk và wall time |
| Warm app / warm DB | Chạy run tiếp trên process còn sống với target được reset đúng | So sánh hợp lệ, không nhầm duplicate `DO NOTHING` |
| Cold-ish DB | Dùng dữ liệu chưa cache/isolated lab | Phân biệt IO với JVM warmup |
| JVM JIT warm-up | Cùng codepath, cùng loại dữ liệu, JFR profile | Gắn nguyên nhân đúng, không suy từ một lần chạy |
| Hikari pool minimumIdle | Thay mức idle trên staging | First connection latency và DB budget cùng được đo |
| Broker chậm subscribe | Trì hoãn consumer có kiểm soát | Manager theo dõi queue, không mất request |
| Database unavailable lúc startup | Tạm ngắt trong môi trường test | Startup/backoff/readiness theo policy, không restart storm |
| Pod image chưa cache | Test node cold, đo pull/schedule | Biết startup có phụ thuộc image/node không |
| Scale từ 0 | Bắt đầu không có worker, tạo workload | Đo TTFSC, queue age và scale lag |
| Nhiều worker boot đồng thời | Tạo nhiều replica | Không vượt connection headroom hoặc CPU node |
| Worker đang chạy bị kill | Kill giữa chunk | Checkpoint/restart đúng; không trùng business key |
| Business commit rồi mất ACK | Mô phỏng trong topology split resource | Replay idempotent và reconciliation thành công |
| Đổi reader name khi restart | Tạo một failing job instance rồi đổi config | Test phát hiện checkpoint mismatch |
| Rolling deploy có mixed versions | Dùng queue/worker image cũ và mới trong lab | Version contract an toàn hoặc drain đúng |
| Một partition cực nặng | Input skew rõ ràng | Nhận ra critical path, không đổ cho JVM warmup |
| Benchmark ngắn vs dài | 50.000 và 50 triệu item cùng logic | Thấy tỷ trọng startup khác nhau |

Đối với fault injection, không tạo outage thật trên production để “thử xem job có restart được không”; dùng test DB, broker và dữ liệu giả, có cơ chế reset trước mỗi run.

## 21. Checklist trước khi tối ưu startup production

- [ ] Đã thống nhất mốc bắt đầu/kết thúc cho startup, readiness, first chunk, ramp-up và job wall-clock.
- [ ] Biết Boot `ApplicationReadyEvent` xảy ra sau application runners; kiểm tra autolaunch job.
- [ ] Đã phân biệt app cold, DB cache cold, worker cold và cache warm.
- [ ] `main()` timestamp và orchestrator timestamp không bị gọi là cùng một mốc.
- [ ] Không trừ `System.nanoTime` giữa hai JVM; dùng trace/timestamps phù hợp.
- [ ] Time to first successful chunk được đo **riêng** với writer-call latency và throughput.
- [ ] Các metric time series không gắn unique execution IDs không giới hạn cardinality.
- [ ] Kiểm tra Hikari pool, broker subscriptions và metadata DB đúng trong readiness contract.
- [ ] Có startup/liveness/readiness probe hợp lý; liveness không reset cả cluster chỉ vì DB outage.
- [ ] Với queue consumer, biết rõ readiness HTTP **không tự gate** broker delivery.
- [ ] Tính `maxReplicas × pools` và startup CPU burst, kể cả rolling surge.
- [ ] Warm-up cache/SQL không tạo side effect nghiệp vụ hoặc chiếm tài nguyên vượt lợi ích.
- [ ] Không dùng `DO NOTHING` của lần chạy sau để giả vờ warm run nhanh hơn.
- [ ] Snapshot, identifying parameters, partition plan và checkpoint giữ nhất quán khi restart.
- [ ] Writer idempotent và có business reconciliation sau crash/redelivery.
- [ ] Biết startup có đang nằm trên critical path của SLA hay không.
- [ ] Đo database CPU/IO/WAL/locks, worker CPU/GC, broker queue age và slowest partition.
- [ ] Không giảm durability hoặc bỏ constraint để đổi lấy warm-up nhanh.
- [ ] Có benchmark cold/warm lặp lại được và runbook cho first-run slow/scale-from-zero.

## 22. Bài tập thực hành

### Bài tập 1 — Định nghĩa đồng hồ

Cho timeline: scheduler kích hoạt lúc 01:00:00, pod schedule lúc 01:00:03, process bắt đầu lúc 01:00:05, Spring started lúc 01:00:10, Spring ready lúc 01:00:14, worker subscribe lúc 01:00:16, chunk đầu commit lúc 01:00:23, job hoàn tất lúc 01:01:05. Tính process-to-ready, scheduler-to-first-commit, scheduler-to-job-complete. Giải thích vì sao không thể dùng duy nhất “Spring ready tại 01:00:14” để dự đoán SLA.

### Bài tập 2 — Boot lifecycle và JobRunner

Tạo project Spring Boot 3.x + Spring Batch 5.2.x ở môi trường thực hành. Gắn listeners `ApplicationStartedEvent` và `ApplicationReadyEvent` như phần 6; thử một `ApplicationRunner` có tác vụ đồng bộ và trường hợp tự launch một job. Quan sát thứ tự events, rồi kết luận event nào có thể dùng cho đo **app startup** trong từng chế độ.

### Bài tập 3 — Đo first chunk có phân vùng

Thêm `FirstSuccessfulChunkListener` vào worker step partitioning có 8 `StepExecution`. Ghi histogram first successful chunk latency theo step và log execution ID. Thử một partition lỗi trước chunk đầu, một partition hoàn tất và một partition bị retry; xác nhận map cleanup và metric không đếm mỗi chunk là một sample.

### Bài tập 4 — JVM warmup so với DB cache

Chạy hai kiểu benchmark: (A) worker process mới, DB cache đã ấm; (B) worker process còn sống nhưng đọc tập input mới chưa có cache. Dùng JFR/CPU và PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` trên staging. Đưa ra bằng chứng lớp nào làm tốc độ khác nhau; tránh quy mọi cải thiện cho JIT.

### Bài tập 5 — Pool và scale-to-zero

Giả sử một workload chạy mỗi 5 phút, mất 20 giây để worker mới subscribe và 12 giây để xử lý, SLA hoàn tất là 25 giây. So sánh worker dài hạn với scale-to-zero, xác định chiến lược đáp ứng SLA trong giới hạn connection và chi phí. Đưa vào cả thời gian scheduler/node/pod và cold first chunk.

### Bài tập 6 — Kubernetes readiness

Triển khai worker Deployment staging với startup/liveness/readiness probes. Tạm làm broker chậm, quan sát HTTP readiness **có thực sự ngăn consumer nhận request không**. Nếu không, thiết kế cơ chế điều khiển start/stop listener và chống duplicate. Giải thích tại sao liveness không nên thất bại vì DB bị ngắt 30 giây.

### Bài tập 7 — Tìm thời gian startup bị che

Một job dài 30 giây chạy trong Spring Boot `ApplicationRunner` đồng bộ. `ApplicationStartedEvent` xuất hiện sau 9 giây, `ApplicationReadyEvent` sau 40 giây. Nêu vì sao thời gian ready không phải 40 giây bean initialization; thiết kế cách tách Boot startup, job execution và time-to-first-commit.

### Bài tập 8 — So sánh workload ngắn và dài

Với cùng startup overhead 20 giây và steady throughput 10.000 items/s, so thời gian xử lý 50.000 và 5.000.000 item. Đề xuất khi nào ưu tiên worker warm/Boot startup so với SQL/JDBC/partition throughput; điều kiện kiểm chứng là tổng wall-clock và output đúng.

### Bài tập 9 — Restart không phụ thuộc cache

Một worker xử lý 80% input rồi bị kill. Worker mới có JVM và DB pool lạnh; job được restart từ `JobRepository`. Thiết kế kiểm thử để cache mới không làm thay dữ liệu reference version, reader tiếp tục đúng checkpoint và output không trùng/thiếu. Ghi riêng latency restart và latency first chunk sau restart.

**Câu hỏi tự kiểm tra:** Startup latency khác steady throughput ra sao? Tại sao `ApplicationReadyEvent` có thể đến **sau** khi job hoàn tất? `@StepScope` có làm warm cache singleton dùng chung giữa thread trở nên an toàn không? Vì sao `SELECT 1` không chứng minh worker có thể commit chunk? Tại sao health readiness của Kubernetes không tự chặn broker consumer? Vì sao cold JVM nhưng warm DB chưa phải full cold start? Worker scale-to-zero tác động thế nào tới SLA của job ngắn? Vì sao phải giữ input snapshot và checkpoint qua worker restart?

## 23. Tổng kết

**Warm-up và thời gian khởi động** là thành phần của hiệu năng Spring Batch chứ không chỉ là chi tiết triển khai. Đối với job ngắn hoặc remote workers thường xuyên scale từ 0, thời gian schedule pod, khởi động JVM/Spring, chuẩn bị JDBC/broker và commit chunk đầu có thể lớn hơn thời gian xử lý hữu ích. Với job dài, database throughput, partition skew và lock/WAL/IO thường quan trọng hơn vài giây khởi động.

Cách tối ưu đáng tin cậy là **đo đầy đủ scheduler → process → ready → first successful chunk → steady throughput → job completed**, phân biệt cold/warm của JVM với database cache và đo từng bottleneck trước khi thay đổi worker count hoặc pool. Warm-up phải an toàn, không tạo side effect giả, không che transaction/restart failure; việc sử dụng cache hay worker dài hạn phải được cân bằng với CPU, bộ nhớ, connection và SLA.

**Đích đến không phải một con số “startup thấp nhất” tách rời hệ thống, mà là job hoàn tất đúng hạn, dữ liệu chính xác và khả năng khôi phục được kiểm chứng sau lỗi hoặc thay đổi phiên bản.**
