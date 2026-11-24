# Scheduled task observation

Trong chương **Messaging và task observability** của mô-đun **SPRING_BOOT_OBSERVABILITY**, scheduled task observation là cách ghi nhận một lần thực thi công việc được kích hoạt theo lịch. Ứng dụng Spring Boot thường dùng @Scheduled để chạy công việc định kỳ như đồng bộ dữ liệu, dọn dẹp bản ghi hết hạn, tổng hợp báo cáo hoặc kiểm tra trạng thái dependency. Khi không có HTTP request làm điểm bắt đầu, nhóm vận hành vẫn cần biết task có chạy đúng lịch, mất bao lâu, thành công hay thất bại và có bị chồng lấn hay bỏ lỡ lần chạy không.

Micrometer Observation cung cấp một mô hình chung để bao quanh một lần chạy task. Observation có thể tạo metrics và, khi Micrometer Tracing được cấu hình, tạo span cho lần thực thi. Tuy nhiên, annotation @Scheduled không tự động có nghĩa mọi task đã có custom business observation với các tags mong muốn. Cần hiểu scheduler, executor, ObservationRegistry và context propagation để đặt instrumentation đúng vị trí.

Bài này trình bày cách quan sát scheduled tasks trong Spring Boot, từ task đơn giản đến scheduler nhiều thread, cách đo duration/outcome, kết nối metrics với traces/logs, kiểm soát cardinality và xử lý overlap, retry, misfire cùng shutdown.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích scheduled task observation và lý do task nền cần observability.
2. Phân biệt lịch kích hoạt, một lần task execution và business operation bên trong task.
3. Bao quanh task bằng Micrometer Observation và ObservationRegistry.
4. Ghi nhận duration, outcome, error và các thuộc tính low-cardinality.
5. Kết hợp observation với Micrometer Tracing để tạo task spans.
6. Theo dõi scheduler/executor pool metrics và tình trạng backlog.
7. Phân tích overlap, missed execution, long-running task, retry và failure.
8. Bảo đảm context propagation khi task chạy trên thread khác.
9. Kiểm thử success/failure, concurrency và lifecycle của scheduled tasks.
10. Xây dựng runbook để điều tra task không chạy, chạy chậm hoặc chạy trùng.

## 2. Vì sao scheduled task cần observation?

HTTP server request thường có request rate, route, status và latency. Scheduled task có đặc điểm khác:
- Không có inbound request tương ứng cho mỗi lần chạy.
- Task có thể chạy lâu hơn chu kỳ schedule.
- Một lần chạy có thể xử lý hàng nghìn records.
- Task có thể bị retry, overlap hoặc bỏ lỡ do scheduler shutdown.
- Failure có thể chỉ xuất hiện trong logs mà không có HTTP status.
- Một task chạy trên thread pool riêng, tách khỏi request context.

Ví dụ một job đồng bộ inventory chạy mỗi phút. Nếu job bắt đầu trễ, xử lý kéo dài 90 giây hoặc thất bại liên tục, chỉ nhìn HTTP metrics sẽ không phát hiện đầy đủ. Task observation cho phép đo:
- Số lần thực thi.
- Thời gian mỗi lần chạy.
- Tỷ lệ success/failure.
- Loại task hoặc operation.
- Lần chạy hiện tại và thời điểm hoàn tất.
- Trace liên quan nếu task gọi HTTP/database/message broker.

Không nên chỉ log "job started" và "job finished" rồi tự tính latency bằng cách đọc log. Metrics và traces có cấu trúc giúp dashboard, alert và correlation nhất quán hơn.

## 3. Phân biệt schedule, execution và business operation

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Schedule | Quy tắc xác định khi nào task được kích hoạt. | Mỗi 5 phút. |
| Trigger | Một lần scheduler quyết định bắt đầu task. | Lần kích hoạt lúc 10:05. |
| Execution | Một lần thực thi method/task. | Đồng bộ 500 inventory records. |
| Business operation | Công việc logic bên trong execution. | Fetch remote inventory, update database. |
| Retry attempt | Một lần thử lại sau failure. | Lần retry thứ hai cho batch. |

Một task execution có thể chứa nhiều business operations và nhiều dependency spans. Nên tạo observation bao quanh một execution để đo tổng duration; các HTTP/JDBC observations bên trong sẽ thể hiện từng dependency call. Nếu có retry, quyết định đo mỗi attempt riêng và một operation tổng bao quanh toàn bộ retry loop để phân biệt latency từng lần với thời gian hoàn tất business job.

~~~mermaid
flowchart TD
    Trigger["Scheduler trigger"]
    Trigger --> Execution["Scheduled task execution Observation"]
    Execution --> Fetch["Fetch remote data"]
    Execution --> Transform["Transform records"]
    Execution --> Persist["Persist to database"]
    Fetch --> ClientSpan["HTTP client observation/span"]
    Persist --> JdbcSpan["JDBC observation/span"]
    Execution --> Result["Success / failure / duration"]
~~~

## 4. @Scheduled không thay thế instrumentation

Spring Framework hỗ trợ @Scheduled để đăng ký method chạy theo fixed rate, fixed delay hoặc cron expression. Ví dụ:

~~~java
@Component
class InventoryRefreshTask {

    @Scheduled(fixedDelayString = "PT1M")
    void refresh() {
        inventoryService.refresh();
    }
}
~~~

Đoạn code trên đăng ký lịch chạy. Nó không tự định nghĩa đầy đủ các business tags như task.name, outcome, batch size hoặc dependency correlation theo nhu cầu ứng dụng.

Spring Boot có thể cung cấp scheduler infrastructure và metrics cho executor/scheduler tùy cấu hình. Nhưng muốn quan sát một task nghiệp vụ rõ ràng, hãy thêm Observation quanh execution hoặc dùng cơ chế instrumentation phù hợp với version. Đừng suy ra rằng mọi method có @Scheduled đều tự có một Observation mang tên nghiệp vụ mong muốn.

## 5. Tạo Observation quanh scheduled task

Có thể inject ObservationRegistry và dùng Observation API để bao quanh một lần chạy. Ví dụ:

~~~java
@Component
class InventoryRefreshTask {

    private final InventoryService inventoryService;
    private final ObservationRegistry observationRegistry;

    InventoryRefreshTask(
            InventoryService inventoryService,
            ObservationRegistry observationRegistry) {
        this.inventoryService = inventoryService;
        this.observationRegistry = observationRegistry;
    }

    @Scheduled(fixedDelayString = "PT1M")
    void refresh() {
        Observation.createNotStarted(
                        "inventory.refresh",
                        observationRegistry)
                .lowCardinalityKeyValue("task.name", "inventory-refresh")
                .observe(inventoryService::refresh);
    }
}
~~~

Observation tạo quanh method invocation và kết thúc khi method trả về hoặc ném exception. Các Observation handlers đã đăng ký có thể tạo timer và tracing span.

Đây là ví dụ cơ bản. Trong code production, cân nhắc dùng ObservationDocumentation/Convention hoặc helper riêng để chuẩn hóa tên và tags giữa nhiều task. Không lặp chuỗi tùy ý ở nhiều nơi khiến dashboard khó thống nhất.

### Khi nào dùng observe và khi nào dùng start/stop?

- observe(Runnable/Supplier): phù hợp khi chỉ cần bao quanh một đoạn đồng bộ và để API quản lý lifecycle.
- start()/stop(): phù hợp khi lifecycle cần điều khiển rõ qua nhiều bước hoặc callback.
- Scope: cần thiết khi muốn gắn Observation vào current context trong lúc thực thi, nhất là khi code bên trong cần truy cập current observation/tracing context.

Luôn bảo đảm stop được gọi khi có exception. API observe thường quản lý lifecycle giúp tránh quên stop; với start/stop thủ công, dùng try/finally.

## 6. Ghi nhận outcome và error

Task có thể kết thúc thành công, thất bại hoặc bị hủy. Nên phân loại outcome thành tập giá trị hữu hạn:

| Outcome | Ý nghĩa |
| --- | --- |
| success | Task hoàn tất theo mục tiêu. |
| failure | Task thất bại và lần chạy không hoàn tất. |
| skipped | Task chủ động bỏ qua vì điều kiện nghiệp vụ. |
| cancelled | Task bị hủy bởi lifecycle hoặc operator. |

Ví dụ ghi exception:

~~~java
void runObserved() {
    Observation observation = Observation.createNotStarted(
            "report.generate", observationRegistry)
        .lowCardinalityKeyValue("task.name", "daily-report");

    observation.observe(() -> reportService.generate());
}
~~~

Observation API có thể tự ghi nhận exception khi callback ném lỗi theo handler/convention. Nếu code catch exception rồi trả về bình thường, handler có thể chỉ nhìn thấy một lần chạy thành công. Nếu exception được xử lý nhưng task vẫn cần được đánh dấu failure, ghi error/outcome có chủ đích vào Observation theo API phù hợp với Micrometer version.

Không ghi exception message đầy đủ làm metric tag. Message có thể chứa SQL, path, customer data hoặc token; dùng error.type ổn định và log đã được lọc nếu cần chi tiết.

## 7. Low-cardinality tags cho task

Metric tags phải có tập giá trị nhỏ, ổn định. Các tags phù hợp có thể gồm:
- task.name: tên task được định nghĩa trong source/config.
- task.type: cleanup, sync, report, reconciliation.
- outcome: success, failure, skipped, cancelled.
- trigger.type: cron, fixed-delay, fixed-rate, manual nếu cần.
- application/service identity từ Resource.

Tránh các giá trị:
- execution.id hoặc UUID của từng lần chạy.
- customer ID, tenant ID nếu số tenant lớn.
- batch ID, file name hoặc object key.
- timestamp chính xác hoặc cron run ID.
- exception message hoặc raw SQL/URL.

| Field | Low-cardinality? | Đề xuất |
| --- | --- | --- |
| task.name=inventory-refresh | Có nếu danh sách task cố định | Dùng cho metrics. |
| outcome=failure | Có | Dùng cho metrics/alert. |
| trigger.type=cron | Có | Dùng khi phân biệt trigger hữu ích. |
| execution.id=UUID | Không | Dùng trong logs/traces có kiểm soát nếu cần. |
| batch.id=20261122-001 | Không | Tránh metric tag. |
| customer.id=... | Không | Không đưa vào metrics; đánh giá privacy trước khi log/trace. |

Một task có hàng triệu records không có nghĩa cần hàng triệu tag values. Dùng count/summary/histogram hoặc batch size distribution phù hợp thay vì gắn ID của từng record.

## 8. Đo duration, count và business progress

Observation metrics có thể cung cấp timer cho thời gian một execution. Ngoài ra, task có thể cần metrics nghiệp vụ riêng:
- Records discovered.
- Records processed.
- Records failed.
- Batch size.
- Last successful execution timestamp.
- Backlog hoặc oldest item age.
- Retry count.

Không đưa timestamp tuyệt đối hoặc record ID vào metric tags. Dùng gauge/counter/histogram phù hợp. Với last-success timestamp, gauge có thể lưu epoch time nếu backend/query convention được xác định; alert nên tính age của lần thành công gần nhất thay vì tạo một time series mỗi execution.

Ví dụ counter cho số record xử lý:

~~~java
@Component
class InventoryRefreshMetrics {

    private final Counter processed;

    InventoryRefreshMetrics(MeterRegistry registry) {
        this.processed = Counter.builder("inventory.refresh.records")
                .tag("outcome", "processed")
                .register(registry);
    }

    void recordProcessed(long count) {
        processed.increment(count);
    }
}
~~~

Đây là ví dụ tối giản; nếu cần tách processed/failed, hãy dùng tag outcome với tập hữu hạn. Đừng tạo counter riêng cho mỗi batch ID.

Timer observation đo duration của execution; counter đo throughput; gauge đo trạng thái hiện tại; histogram đo phân phối size/duration. Chọn metric theo câu hỏi vận hành cần trả lời.

## 9. Scheduler và executor metrics

Scheduled task thường chạy trên scheduler thread hoặc TaskScheduler/TaskExecutor tùy cấu hình. Spring Boot có thể instrument các executor được quản lý và expose metrics khi Actuator/Micrometer binders được cấu hình.

Các tín hiệu quan trọng:
- Pool size và active threads.
- Queue size/backlog.
- Completed task count.
- Rejected task count.
- Pending tasks.
- Thread starvation hoặc scheduler delay.

Tên meter phụ thuộc loại executor và Boot version. Inspect Actuator metrics endpoint và meter registry thực tế; không giả định mọi scheduler có cùng metric names.

Nếu scheduler chỉ có một thread và một task chạy 10 phút trong khi các task khác cần chạy mỗi phút, những task sau sẽ bị trễ. Tăng pool size có thể cải thiện concurrency nhưng cũng có thể gây overlap và tăng tải database/downstream. Cần hiểu execution semantics trước khi đổi pool.

## 10. fixedDelay, fixedRate và cron

Ba kiểu schedule có ý nghĩa khác nhau:

| Kiểu | Quy tắc | Ảnh hưởng tới quan sát |
| --- | --- | --- |
| fixedDelay | Chờ một khoảng sau khi lần chạy trước kết thúc rồi mới chạy tiếp. | Thường không chồng lấn cùng scheduled registration; chu kỳ thực tế gồm duration + delay. |
| fixedRate | Lập lịch theo khoảng thời gian giữa các lần bắt đầu theo scheduler semantics. | Task chạy lâu có thể gây lag; behavior phụ thuộc scheduler và concurrency. |
| cron | Chạy theo các thời điểm calendar. | Có thể bỏ lỡ thời điểm khi app down; timezone/DST cần xem xét. |

Đừng dùng timer duration để suy ra schedule delay. Nên đo thêm:
- scheduled.expected.time hoặc lateness nếu có thể tính ổn định.
- execution.started.time trong log/trace event, không phải metric label.
- task duration.
- age từ lần thành công gần nhất.

Với cron, cấu hình zone rõ ràng nếu task phụ thuộc múi giờ nghiệp vụ. Thay đổi timezone hoặc daylight saving có thể làm lịch chạy khác kỳ vọng.

## 11. Overlap, concurrency và distributed scheduling

Nếu task mất lâu hơn chu kỳ, cần xác định nó có thể chạy đồng thời hay không. Một số cấu hình scheduler cho phép nhiều threads; nhiều application replicas cũng có thể đăng ký cùng cron và cùng chạy task.

Rủi ro:
- Hai replicas cùng xử lý một batch.
- Một task ghi đè kết quả của task khác.
- Lock contention trong database.
- Retry chạy trùng với execution cũ.
- Job duration tăng do concurrency quá mức.

Observation cho thấy hai executions chồng lấn nhưng không tự ngăn chúng. Cơ chế single-flight, distributed lock, leader election hoặc idempotency phải được thiết kế riêng theo semantics của job.

Nếu dùng distributed lock:
- Đặt lease/TTL hợp lý.
- Xử lý process crash và lock expiry.
- Thiết kế task idempotent.
- Ghi nhận skipped/lock-not-acquired như outcome có kiểm soát.
- Không ghi lock key có chứa customer data vào metric tags.

## 12. Trace context và child observations

Scheduled task không có inbound HTTP span làm parent. Khi scheduler kích hoạt task, thường không có request trace context. Task observation có thể tạo một root span; các HTTP/JDBC/message spans phát sinh trong task trở thành child spans nếu scope/context được mở đúng.

~~~mermaid
flowchart TD
    Scheduler["Scheduler thread"]
    Scheduler --> Task["inventory.refresh Observation"]
    Task --> HTTP["HTTP client span"]
    Task --> JDBC["JDBC span"]
    Task --> Publish["Message publish span"]
    Task --> Log["Structured logs with trace correlation"]
~~~

Khi chạy task trên executor khác, context có thể không tự propagate. Dùng TaskDecorator hoặc context propagation mechanism phù hợp với Spring/Micrometer version. Không chỉ copy MDC bằng tay mà quên trace context; hai thứ có liên hệ nhưng không hoàn toàn đồng nhất.

Nếu task được kích hoạt từ một message hoặc HTTP request rồi chuyển sang background executor, quyết định trace semantics:
- Tiếp tục trace hiện tại nếu đó vẫn là cùng operation.
- Tạo span mới liên kết với context message nếu xử lý bất đồng bộ tách rời.
- Dùng span links nếu mô hình công việc liên quan nhiều parent contexts.

Không giữ scope của một request đã kết thúc rồi dùng lại trong scheduled task độc lập.

## 13. Logs và correlation cho scheduled tasks

Log event hữu ích nên có:
- task.name cố định.
- execution ID nếu cần truy vết một lần chạy, nhưng chỉ ở log field.
- outcome/error.type.
- records processed/failed.
- duration hoặc elapsed time.
- trace ID/span ID khi context có mặt.

Không ghi full payload, credentials, database connection strings hoặc raw customer identifiers. Với một task xử lý nhiều tenant, không gắn toàn bộ tenant IDs vào MDC hoặc trace baggage. Có thể log tenant count hoặc tenant tier nếu phù hợp policy.

Ví dụ:

~~~java
log.atInfo()
        .addKeyValue("task.name", "inventory-refresh")
        .addKeyValue("records.processed", processedCount)
        .addKeyValue("outcome", "success")
        .log("Scheduled inventory refresh completed");
~~~

Nếu log failure, dùng exception class/category và thông tin đã lọc. Không đưa execution ID vào metric tag nhưng có thể dùng trong log để đối chiếu lần chạy.

## 14. Timeout, retry và failure policy

Scheduled task có thể gọi HTTP, JDBC hoặc message broker. Timeout phải được cấu hình ở từng client; Observation chỉ ghi nhận thời gian và kết quả, không tự giới hạn task duration.

Retry policy cần rõ:
- Retry bao nhiêu lần?
- Backoff cố định hay exponential?
- Có jitter không?
- Lỗi nào retry được?
- Khi nào chuyển sang dead-letter/manual recovery?
- Execution tổng thể và từng attempt được đo riêng ra sao?

Một pattern hữu ích là một parent Observation cho task execution và child Observation/span cho mỗi retry attempt. Metric tags có thể gồm attempt outcome nhưng không gắn số attempt không giới hạn hoặc exception message. Counter retry có thể dùng task.name và outcome hữu hạn.

Nếu task có timeout, cancellation cần được ghi nhận riêng nếu đó là trạng thái vận hành quan trọng. Đảm bảo cancellation không bỏ qua cleanup, transaction rollback hoặc release connection.

## 15. Kiểm thử scheduled task observation

Test không nên phụ thuộc chờ cron thật. Gọi method/task runner trực tiếp hoặc dùng scheduler test có kiểm soát để xác minh Observation và metrics.

Các trường hợp cần có:
1. Execution thành công tạo timer và outcome success.
2. Exception tạo error/failure record phù hợp.
3. Task skip do lock hoặc điều kiện nghiệp vụ được phân biệt với success.
4. Duration đo đúng khoảng bao quanh execution.
5. Nhiều executions không tạo high-cardinality tags.
6. Child HTTP/JDBC spans nằm trong task trace.
7. Context propagation hoạt động khi task chuyển thread.
8. Shutdown không để scheduler chạy tiếp hoặc mất trạng thái cần flush.

Ví dụ kiểm thử đơn giản có thể dùng SimpleMeterRegistry:

~~~java
class ScheduledObservationTest {

    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();
    private final ObservationRegistry observations =
            ObservationRegistry.create();

    @Test
    void recordsTaskExecution() {
        observations.observationConfig()
                .observationHandler(new DefaultMeterObservationHandler(registry));

        Observation.createNotStarted("inventory.refresh", observations)
                .lowCardinalityKeyValue("task.name", "inventory-refresh")
                .observe(() -> { });

        assertThat(registry.find("inventory.refresh").timer()).isNotNull();
    }
}
~~~

Đây là skeleton minh họa; constructor/API của handler có thể thay đổi theo Micrometer version. Dùng dependency versions do Spring Boot quản lý và xác nhận meter name convention thực tế. Integration test nên kiểm tra cả Observation handler và tracing bridge nếu cần spans.

## 16. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Task chạy nhưng không có metrics | Chưa tạo Observation hoặc Meter handler không được cấu hình. | Kiểm tra ObservationRegistry và handler. |
| Có metrics nhưng không có trace | Tracing handler/bridge/exporter không hoạt động hoặc trace bị sample out. | Kiểm tra tracer, sampler và exporter. |
| Task chạy trễ | Scheduler thread bị chiếm, queue backlog hoặc task trước quá lâu. | Kiểm tra pool size, active threads, queue và duration. |
| Task chạy đồng thời trên nhiều replicas | Mỗi replica đăng ký cùng schedule. | Dùng distributed lock/leader election/idempotency. |
| Duration tăng bất thường | Downstream chậm, pool cạn hoặc batch lớn. | Đối chiếu child spans, pool metrics và batch size. |
| Task failure nhưng outcome success | Exception bị catch rồi không ghi nhận vào Observation. | Ghi error/outcome rõ ràng khi xử lý exception. |
| Không có child spans | Context scope không active hoặc mất khi chuyển executor. | Kiểm tra scope và context propagation. |
| Metrics cardinality tăng | Execution ID, batch ID hoặc tenant ID được dùng làm tag. | Rà soát low-cardinality key-values. |
| Task chạy sau shutdown | Scheduler không được quản lý/đóng đúng lifecycle. | Kiểm tra scheduler bean và graceful shutdown. |
| Task bị bỏ lỡ sau deploy | Cron trigger xảy ra khi ứng dụng down; không có persistent scheduler. | Xem yêu cầu durability và cân nhắc job scheduler lưu trạng thái. |

## 17. Runbook điều tra scheduled task

1. Xác định task.name, schedule, timezone và scheduler bean.
2. Kiểm tra lần chạy gần nhất, outcome và duration.
3. So sánh thời điểm dự kiến với thời điểm thực tế để xác định scheduling lag.
4. Kiểm tra executor active threads, queue backlog, rejected tasks và pool size.
5. Tìm task trace và xem child HTTP/JDBC/message spans.
6. Kiểm tra exception/error type và retry attempts.
7. Xác định overlap giữa replicas và distributed lock state.
8. Kiểm tra batch size, records processed/failed và oldest backlog age.
9. Kiểm tra context propagation qua async/reactive boundaries.
10. Xác minh metrics tags không chứa execution IDs hoặc identifiers động.
11. Kiểm tra scheduler shutdown/redeploy và missed execution behavior.
12. Nếu job cần chạy bền vững qua downtime, đánh giá persistent job scheduler/queue thay vì chỉ dựa vào in-process @Scheduled.

## 18. Bài tập tự kiểm tra

### Bài 1 — Đo execution

Một task chạy mỗi 5 phút và mất 40 giây. Timer của task nên đo phần nào?

**Đáp án:** Đo duration của một lần execution, khoảng thời gian method/job thực sự chạy. Schedule interval hoặc thời gian chờ tới lần tiếp theo là một đại lượng khác.

### Bài 2 — Task chạy trễ

Task có fixedRate 60 giây nhưng một lần chạy mất 100 giây. Điều gì cần kiểm tra?

**Đáp án:** Scheduler implementation, pool size, queue/lag và overlap semantics. Không giả định task chắc chắn chạy đồng thời hoặc tự bỏ lần kế tiếp; kiểm tra cấu hình scheduler thực tế.

### Bài 3 — Nhiều replicas

Ứng dụng có 4 replicas, mỗi replica đăng ký cùng cron. Vì sao một job có thể chạy 4 lần?

**Đáp án:** @Scheduled chạy trong từng application instance; cần distributed coordination, leader election, distributed lock hoặc job scheduler có persistence nếu chỉ muốn một execution toàn cluster.

### Bài 4 — Không có trace parent

Scheduled task chạy độc lập không được kích hoạt bởi HTTP/message. Span của task có thể là gì?

**Đáp án:** Nó có thể là root span cho task execution. Các dependency spans bên trong trở thành child nếu context scope được duy trì.

### Bài 5 — Outcome sai

Task catch SQLException, log warning rồi return. Vì sao Observation có thể trông như thành công?

**Đáp án:** Callback đã kết thúc bình thường nên handler không thấy exception thoát ra. Nếu task thực sự failure, ghi nhận error/outcome tường minh theo Observation API.

### Bài 6 — Cardinality

Có nên gắn execution UUID vào metric tag để tìm lần chạy lỗi không?

**Đáp án:** Không. Mỗi lần chạy tạo một tag value mới. Đưa execution ID vào log/trace theo policy; metrics dùng task.name và outcome có tập giá trị hữu hạn.

## 19. Checklist triển khai

- [ ] Mỗi task quan trọng có Observation bao quanh một execution.
- [ ] Observation name và task.name ổn định.
- [ ] Outcome success/failure/skipped/cancelled được phân biệt khi cần.
- [ ] Exception được ghi nhận ngay cả khi code catch và xử lý.
- [ ] Duration, count và business progress được đo bằng metric phù hợp.
- [ ] Không dùng execution ID, batch ID, customer ID hoặc timestamp làm metric tag.
- [ ] Scheduler/executor pool metrics và queue backlog được theo dõi.
- [ ] fixedDelay/fixedRate/cron semantics và timezone đã rõ.
- [ ] Overlap và multi-replica execution có coordination/idempotency.
- [ ] Timeout/retry/backoff có giới hạn và được quan sát.
- [ ] Child HTTP/JDBC/message spans được liên kết với task span.
- [ ] Context propagation qua executor/reactive boundaries được kiểm thử.
- [ ] Logs có task name, outcome và correlation fields an toàn.
- [ ] Scheduler lifecycle/graceful shutdown được cấu hình.
- [ ] Job cần durability qua downtime dùng scheduler/queue có persistence.
- [ ] Có dashboard/alert cho last success, duration, failure rate và scheduling lag.

**Ghi nhớ:** Scheduled task là một workload độc lập cần được quan sát như một operation có lifecycle rõ ràng. Tạo Observation quanh mỗi execution, đo duration/outcome và business progress, dùng tags ổn định, theo dõi scheduler pool và context propagation. Khi task có retry, overlap hoặc chạy trên nhiều replicas, cần phối hợp idempotency/locking và lifecycle; metrics cho xu hướng, traces cho dependency path, logs cho sự kiện cụ thể.
