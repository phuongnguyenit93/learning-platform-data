# Theo dõi retry count trong Spring Batch

## 1. Vì sao retry count là chỉ số cần theo dõi?

Một Job Spring Batch có thể kết thúc `COMPLETED` dù trong lúc chạy từng gặp nhiều lỗi tạm thời: database deadlock, HTTP 503, timeout hoặc lỗi kết nối chập chờn. Nếu các lỗi đó được cấu hình **retry**, ứng dụng có thể tự thử lại rồi tiếp tục. Chỉ nhìn trạng thái cuối của Job sẽ không thấy sự suy giảm của dịch vụ phụ thuộc.

Ví dụ Job nhập 100.000 đơn hàng hoàn thành trong 20 phút, nhưng một bước phải thử lại 5.000 lần khi gọi API. Job vẫn thành công, song số lần retry tăng có thể báo hiệu sự cố sắp xảy ra, làm tăng thời gian xử lý và chi phí của downstream service.

**Theo dõi retry count** là đo đúng số lần thử lại và các sự kiện lỗi đi kèm, gắn với Job/Step phù hợp, sau đó đưa chúng vào log, metric và cảnh báo. Bài học tập trung vào phần **Monitoring** của Spring Batch Core Processing, gồm:

- Hiểu sự khác nhau giữa retry attempt, failed attempt, retry exhaustion, rollback, skip và Job restart.
- Đọc retry count từ ngữ cảnh retry tại thời điểm xử lý, thay vì suy luận sai từ StepExecution.
- Gắn listener để phát log và metric theo cấu hình retry.
- Dùng Micrometer và Prometheus để tổng hợp, hiển thị xu hướng và cảnh báo.
- Theo dõi tỉ lệ phục hồi sau retry, số lần retry vượt giới hạn và thời gian xử lý.
- Thiết kế metric an toàn với cardinality thấp, không đưa dữ liệu nhạy cảm vào label.
- Kiểm thử các kịch bản retry thành công, retry hết hạn, skip, rollback và restart.
- Điều chỉnh cách viết giữa **Spring Batch 5.2.x** và **Spring Batch 6.x**.

## 2. Định nghĩa đúng những con số

Từ “retry count” có thể chỉ nhiều con số khác nhau. Trước khi vẽ dashboard, phải định nghĩa rõ **đơn vị đếm** và **thời điểm tăng**.

| Chỉ số | Đơn vị | Ý nghĩa |
| --- | --- | --- |
| **Initial attempts** | Lần gọi | Những lần xử lý đầu tiên, trước khi có retry. |
| **Retry attempts** | Lần gọi lại | Những lần gọi bổ sung sau một lần lỗi trước đó. |
| **Failed attempts** | Lần ném lỗi | Mỗi lần retryable callback kết thúc bằng exception; gồm cả lần lỗi đầu tiên và lần lỗi cuối khi hết giới hạn. |
| **Recovered after retry** | Thao tác được phục hồi | Một retry scope có lỗi nhưng về sau hoàn thành thành công. |
| **Retry exhausted** | Retry scope hết ngân sách | Đã dùng hết số lần theo policy mà vẫn chưa thành công. |
| **Rollback count** | Transaction rollback | Số transaction rollback mà StepExecution ghi nhận; một retry có thể kèm rollback, nhưng không tương đương nhau. |
| **Skip count** | Item bỏ qua | Số item được bỏ qua theo skip policy; không phải số lần gọi lại. |
| **Job restart count** | JobExecution mới | Số lần khởi động lại cùng JobInstance sau FAILED/STOPPED; xảy ra ở tầng Job, không phải retry trong Step. |

### Ví dụ với retryLimit(3) ở Spring Batch 5.2

Giả sử một ItemProcessor dùng `retryLimit(3)` đối với một exception có thể thử lại. Ở API này, giới hạn 3 tương ứng tối đa **3 lần thực thi item** (một lần đầu và tối đa hai lần gọi lại).

| Kết quả xử lý một item | Số attempt thực thi | Failed attempts | Retry attempts đã chạy | Kết quả cuối |
| --- | ---: | ---: | ---: | --- |
| Thành công ngay | 1 | 0 | 0 | Thành công. |
| Lỗi một lần rồi thành công | 2 | 1 | 1 | Phục hồi sau retry. |
| Lỗi hai lần rồi thành công | 3 | 2 | 2 | Phục hồi sau retry. |
| Lỗi cả ba lần | 3 | 3 | 2 | Hết retry; Step có thể fail hoặc skip tùy policy. |

Từ bảng này thấy rõ: **3 failed attempts không đồng nghĩa 3 retry attempts**. Một listener tăng counter ở mỗi sự kiện exception sẽ ghi nhận cả lần thất bại cuối cùng, khi **không còn retry nào tiếp theo**.

Đối với một retry scope khép kín:

~~~text
actual_attempts = 1 initial_attempt + executed_retry_attempts
failed_attempts = số callback kết thúc bằng exception

Nếu 2 lần lỗi rồi lần 3 thành công:
  actual_attempts = 3
  failed_attempts = 2
  executed_retry_attempts = 2

Nếu cả 3 lần đều lỗi và bị chặn:
  actual_attempts = 3
  failed_attempts = 3
  executed_retry_attempts = 2
~~~

Không nên áp dụng phép tính một cách máy móc cho mọi trường hợp listener/transaction lồng nhau. Với stateful retry, rollback, reprocessing và nhiều tầng retry, cần xác định chính xác callback mà mỗi listener quan sát.

## 3. Retry của Step khác restart của Job

~~~text
JobInstance (job=importOrders, businessDate=2026-11-16)
   |
   +-- JobExecution #101
   |     |
   |     +-- StepExecution importStep
   |           |
   |           +-- item A: success on first attempt
   |           +-- item B: fail -> retry -> success
   |           +-- item C: fail -> retry -> fail -> FAILED
   |
   +-- JobExecution #102 (Job restart)
         |
         +-- StepExecution importStep
               +-- resume theo checkpoint
               +-- item C: success
~~~

Hai cấp độ hoàn toàn khác nhau:

- **Retry**: cùng một JobExecution, framework gọi lại một thao tác đã lỗi theo RetryPolicy của Step hoặc thư viện gọi API. Có thể làm tăng thời gian, số HTTP request và rollback.
- **Restart**: tạo **JobExecution mới** cho JobInstance cũ; đọc metadata/ExecutionContext và tiếp tục phần công việc cần làm lại. Không nên cộng số JobExecution rồi gọi đó là retry count.

Một item có thể được thử hai lần ở JobExecution #101 và thêm một lần ở JobExecution #102. Số lần gọi nghiệp vụ xuyên nhiều execution cần thống kê ở mức **business key** bằng hệ thống audit/idempotency phù hợp; Spring Batch không tự cung cấp một trường “retry_count_lifetime” bền vững cho từng item.

## 4. Spring Batch có sẵn retry count trong metadata không?

**Không có một cột retry count chuẩn cho từng item trong `BATCH_STEP_EXECUTION`.** Metadata StepExecution thường có:

- `READ_COUNT`: số item đọc được.
- `WRITE_COUNT`: số item viết theo Step.
- `FILTER_COUNT`: số item bị processor lọc.
- `READ_SKIP_COUNT`, `PROCESS_SKIP_COUNT`, `WRITE_SKIP_COUNT`: số item được skip theo giai đoạn.
- `COMMIT_COUNT`: số transaction commit.
- `ROLLBACK_COUNT`: số transaction rollback.

Các số đếm này có giá trị vận hành, nhưng không biểu diễn trực tiếp số retry callback hay số lần tái thử thành công.

Ví dụ: một chunk có thể rollback vì lỗi writer, rồi nhiều item được xử lý lại. Ngược lại, một logic retry cho HTTP call có thể thực hiện nhiều lần trong cùng transaction mà không tạo thêm rollback tương ứng. Do đó:

~~~text
rollbackCount != retryCount
skipCount     != retryCount
readCount     != số lần ItemReader.read() đã bị gọi
JobExecution count != retry attempt count
~~~

Nếu muốn quan sát retry theo thời gian thực, nên instrument tại **retry listener** hoặc lớp gọi dịch vụ có retry, rồi kết hợp số liệu đó với StepExecution trong log/dashboard.

### Đọc StepExecution để bổ sung ngữ cảnh

Ví dụ Spring Batch 5.2.x:

~~~java
StepExecution se = ...; // lấy từ JobRepository/JobExplorer
long rollbacks = se.getRollbackCount();
long readSkips = se.getReadSkipCount();
long processSkips = se.getProcessSkipCount();
long writeSkips = se.getWriteSkipCount();
long commits = se.getCommitCount();
~~~

Thông tin này giúp trả lời “Step có bị rollback/skip nhiều không?”, không trả lời trực tiếp “item được retry bao nhiêu lần?”.

## 5. RetryContext là nguồn quan sát lúc xử lý

Với **Spring Batch 5.2.x**, fault-tolerant chunk processing sử dụng **Spring Retry**. Listener thuộc package `org.springframework.retry` có thể nhận `RetryContext` và exception:

~~~java
public interface RetryListener {
    // onError được gọi sau một lần callback thất bại.
    <T, E extends Throwable> void onError(
        RetryContext context,
        RetryCallback<T, E> callback,
        Throwable throwable);
}
~~~

Trong ngữ cảnh đang retry, `context.getRetryCount()` cho biết bộ đếm retry mà chính retry implementation duy trì. Listener có thể ghi:

~~~text
02:00:05 WARN retry_failure job=importOrders step=loadStep
              failure_number=1 category=transient_db
02:00:06 WARN retry_failure job=importOrders step=loadStep
              failure_number=2 category=transient_db
02:00:07 INFO item_processed_after_retry job=importOrders step=loadStep
~~~

Có ba điều quan trọng:

1. **`onError` được gọi khi callback thất bại**, kể cả lần lỗi cuối. Tăng metric từ callback này thì hãy đặt tên “failed attempts” hoặc “failure events”, tránh gọi nhầm là “successful retry”.
2. **`getRetryCount()` là bộ đếm trong retry context hiện tại**, không phải số retry tích lũy của toàn JobExecution và không mặc nhiên được lưu lâu dài trong JobRepository.
3. Khi một chunk rollback, retry có thể liên quan đến việc nhận diện lại item sau transaction. Việc cache/khôi phục context phụ thuộc cơ chế retry và cấu hình Step. Không dùng một biến counter toàn cục không an toàn thread để suy luận retry của từng item.

Nếu một dịch vụ ở trong ItemProcessor còn dùng `@Retryable` hoặc RetryTemplate riêng, có thể có **hai tầng retry**. Listener của Step có thể chỉ thấy lỗi cuối của tầng bên trong, trong khi HTTP client đã thực hiện nhiều request. Muốn đo “số lần gọi HTTP thật”, phải instrument gần HTTP client hoặc sở hữu rõ tầng retry cần giám sát.

## 6. Cấu hình retry trong Step (Spring Batch 5.2.x)

Ví dụ một Step đọc dữ liệu, gọi dịch vụ bổ sung thông tin, rồi ghi đích. Lỗi database tạm thời được phép retry tối đa ba attempt cho mỗi retry scope.

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.RetryListener;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step loadOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> enrichmentProcessor,
        ItemWriter<Order> orderWriter,
        RetryListener retryMonitoringListener) {

    return new StepBuilder("loadOrdersStep", jobRepository)
            .<Order, Order>chunk(20, transactionManager)
            .reader(orderReader)
            .processor(enrichmentProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .listener(retryMonitoringListener)
            .build();
}
~~~

Ở đây, `Order`, reader, processor và writer là các type/bean nghiệp vụ của ứng dụng. Ví dụ tập trung vào cách tích hợp retry monitoring. Những bước tạo schema, datasource và ItemReader/Writer có thể khác theo dự án.

- `.faultTolerant()` mở các khả năng retry/skip của Step.
- `.retry(TransientDataAccessException.class)` chọn loại lỗi được retry; lỗi dữ liệu bất biến như sai định dạng thường không nên retry.
- `.retryLimit(3)` ở 5.2 giới hạn **tổng số attempt tối đa** thành ba cho lỗi này.
- `.listener(retryMonitoringListener)` đăng ký callback quan sát mà không phải nhúng logging/metrics vào processor.
- `chunk(20, transactionManager)` xác định ranh giới transaction của 20 item; lỗi khi ghi có thể khiến chunk rollback và được xử lý lại theo policy.

Với lỗi hệ thống kéo dài, không đặt retry limit quá lớn. Số retry cao có thể kéo dài thời gian Job, giữ connection/transaction lâu và tăng tải dịch vụ đang suy yếu. Cần kết hợp timeout, backoff và policy giới hạn hợp lý.

## 7. Ghi metric bằng RetryListener và Micrometer

Ví dụ listener Spring Batch 5.2.x / Spring Retry 2.x dưới đây xuất **counter của failed callback attempts**. Nó không cố lấy item ID làm metric label, không ghi nguyên nội dung exception vào Prometheus và không nhầm số lỗi với số retry đã diễn ra.

**RetryFailureMetricsListener.java**:

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;

public final class RetryFailureMetricsListener implements RetryListener {

    private static final Logger log =
            LoggerFactory.getLogger(RetryFailureMetricsListener.class);

    private final MeterRegistry registry;
    private final String jobName;
    private final String stepName;

    public RetryFailureMetricsListener(
            MeterRegistry registry,
            String jobName,
            String stepName) {
        this.registry = registry;
        this.jobName = jobName;
        this.stepName = stepName;
    }

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        String category = classify(throwable);

        Counter.builder("app.batch.retry.failed.attempts")
                .description(
                    "Failed callback attempts reported by RetryListener")
                .tag("job", jobName)
                .tag("step", stepName)
                .tag("failure_category", category)
                .register(registry)
                .increment();

        log.warn(
            "batch_retry_failure job={} step={} " +
            "failure_number={} failure_category={} exception_type={}",
            jobName,
            stepName,
            context.getRetryCount(),
            category,
            throwable.getClass().getSimpleName()
        );
    }

    private String classify(Throwable throwable) {
        if (throwable instanceof TransientDataAccessException) {
            return "transient_db";
        }
        return "other";
    }
}
~~~

**Đăng ký listener cho một Step:**

~~~java
@Bean
RetryListener retryMonitoringListener(MeterRegistry meterRegistry) {
    return new RetryFailureMetricsListener(
            meterRegistry, "importOrdersJob", "loadOrdersStep");
}
~~~

Nếu cùng ứng dụng có nhiều Step, tạo listener với jobName/stepName tương ứng hoặc xây factory cung cấp listener cho từng Step. Không tạo một bean singleton có các field `currentJob`, `currentStep` rồi sửa chúng mỗi khi Step chạy: điều đó gây race condition khi các Job chạy đồng thời.

### Cách đọc số liệu listener

Trong ví dụ trên:

- Mỗi lần `onError` chạy thì counter tăng một đơn vị.
- Lần lỗi đầu tiên của item cũng làm tăng counter.
- Lần lỗi cuối khi retry hết ngân sách vẫn làm tăng counter.
- Nếu item thành công ngay, listener không tăng counter.
- Nếu retry lỗi một lần rồi thành công, counter tăng 1 dù có **2 attempt thực tế**.

Vì thế tên `app.batch.retry.failed.attempts` là có chủ đích. Nếu bạn cần **số retry attempt thực sự bắt đầu**, phải đo ở điểm thực thi callback hoặc sự kiện *before retry* tương ứng, rồi đảm bảo không tính initial attempt. Không đổi tên counter này thành `retry_attempts_total` chỉ để có dashboard đơn giản.

### Ghi jobExecutionId vào log

ID của JobExecution hữu ích khi truy vấn sự cố cụ thể, nhưng là **tag cardinality cao** đối với metric.

Trong Step listener chạy trên thread có Step context, có thể lấy metadata:

~~~java
import org.springframework.batch.core.scope.context.StepContext;
import org.springframework.batch.core.scope.context.StepSynchronizationManager;

StepContext stepContext = StepSynchronizationManager.getContext();
if (stepContext != null) {
    Long jobExecutionId =
            stepContext.getStepExecution().getJobExecution().getId();

    // Đưa jobExecutionId vào log / trace, không đưa vào metric tag.
}
~~~

Không mặc định StepSynchronizationManager luôn hiện diện ở mọi callback ngoài thread Step, đặc biệt khi dùng xử lý bất đồng bộ, remote chunking hoặc cơ chế retry bên ngoài Step. Khi không có context, xử lý null và lấy thông tin từ tracing/message metadata tương ứng.

## 8. Dùng cả counter, histogram và trạng thái cuối

Một dashboard có ích không chỉ hiển thị tổng exception. Cần tối thiểu ba loại tín hiệu:

| Tín hiệu | Kiểu metric | Câu hỏi nó trả lời |
| --- | --- | --- |
| `app.batch.retry.failed.attempts` | Counter | Bao nhiêu callback bị lỗi trong thời gian quan sát? |
| `app.batch.retry.exhausted` | Counter (tự instrument) | Bao nhiêu retry scope đã dùng hết ngân sách? |
| `app.batch.retry.recovered` | Counter (tự instrument) | Bao nhiêu retry scope cuối cùng thành công sau lỗi? |
| `app.batch.retry.failures.per.scope` | DistributionSummary/Histogram | Các scope lỗi thường trải qua bao nhiêu failed attempts? |
| `spring.batch.step` | Timer built-in | Step chạy lâu hơn bình thường không? |
| `spring.batch.job` | Timer built-in | Job thường hoàn thành hay thất bại, mất bao lâu? |
| `rollbackCount` từ StepExecution | Metadata lưu JDBC | Bao nhiêu lần rollback trong StepExecution? |
| `processSkipCount`, `writeSkipCount` | Metadata lưu JDBC | Bao nhiêu item bỏ qua sau lỗi theo policy? |

Ba metric có tiền tố `app.batch.retry` phía trên là **metric do ứng dụng định nghĩa**, không phải mặc định Spring Batch cung cấp.

Không nên tự suy ra `exhausted` bằng quy tắc “getRetryCount == retryLimit” trong mọi callback. Policy có thể thay đổi theo exception, timeout, skip hoặc các tầng retry khác. Tốt hơn nên dùng callback/exhaustion event phù hợp API phiên bản, hoặc ghi kết quả thực tế của retry scope sau khi policy xác nhận hết giới hạn.

Với **Spring Retry 2.x**, có thể dùng `RetryListener.onSuccess` để quan sát lần callback thành công; kết hợp `RetryContext.getRetryCount() > 0` để biết scope từng gặp thất bại. Khi implement `close`, cần hiểu callback có thể mang exception cuối và vòng đời của stateful retry; hãy kiểm thử trên Step thực tế trước khi kết luận số scope thành công/hết hạn.

## 9. Retry count trong Micrometer và Actuator

Với Spring Boot 3.x, có thể thêm các dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
~~~

Ví dụ cấu hình xuất metric Prometheus:

~~~properties
management.endpoints.web.exposure.include=health,info,prometheus
management.endpoint.prometheus.enabled=true
~~~

Cần cấu hình xác thực/phân quyền hoặc chỉ mở endpoint trong mạng giám sát nội bộ. Không công khai endpoint quản trị rộng hơn yêu cầu.

Từ tên metric Micrometer `app.batch.retry.failed.attempts`, Prometheus thường xuất series theo dạng:

~~~text
app_batch_retry_failed_attempts_total{
  job="importOrdersJob",
  step="loadOrdersStep",
  failure_category="transient_db"
} 42
~~~

Đây là **ví dụ về metric do ứng dụng instrument**; tên Prometheus cuối cùng phụ thuộc naming convention và exporter. Nó chỉ là tổng tăng dần của các failure events mà listener đã thấy; không phải checkpoint bền vững trong JobRepository.

### Built-in metrics Spring Batch

Spring Batch có một số metric chung như `spring.batch.job`, `spring.batch.step`, `spring.batch.item.read`, `spring.batch.item.process` và `spring.batch.chunk.write`. Các timer giúp phát hiện Job/Step hay hoạt động item chậm đi khi retry tăng. Tập metric có thể khác theo phiên bản và cấu hình quan sát.

Ở Spring Batch 5.2, metric tích hợp hoạt động qua Micrometer global registry. Ở Spring Batch 6.x, tài liệu yêu cầu thiết lập **ObservationRegistry** để bật hệ thống quan sát tích hợp; có thể nối nó với MeterRegistry bằng observation handler.

Không giả định framework đã xuất sẵn `retryCount` cho từng item từ những timer này. Nếu cần một counter riêng cho retry, hãy đăng ký listener hoặc instrument đúng retry subsystem.

## 10. Query Prometheus để theo dõi xu hướng

Giả sử metric được xuất thành `app_batch_retry_failed_attempts_total`.

**Tốc độ xuất hiện failed attempts trong 5 phút:**

~~~promql
sum by (job, step) (
  rate(app_batch_retry_failed_attempts_total[5m])
)
~~~

Kết quả có đơn vị xấp xỉ **failure event/giây**. Khi đồ thị cao lên, hệ thống đang gặp lỗi lặp lại thường xuyên hơn.

**Tổng failed attempts trong 1 giờ gần nhất:**

~~~promql
sum by (job, step, failure_category) (
  increase(app_batch_retry_failed_attempts_total[1h])
)
~~~

**Tỉ trọng lỗi database tạm thời trong tất cả failure events:**

~~~promql
sum by (job, step) (
  rate(app_batch_retry_failed_attempts_total{
    failure_category="transient_db"
  }[10m])
)
/
clamp_min(
  sum by (job, step) (
    rate(app_batch_retry_failed_attempts_total[10m])
  ),
  1e-9
)
~~~

Với dashboard, có thể kết hợp một biểu đồ tốc độ lỗi và một biểu đồ thời lượng Step để nhận diện mối quan hệ giữa retry tăng và thời gian xử lý kéo dài.

### Tỉ lệ retry: nên dùng mẫu số nào?

“Tỉ lệ retry” có thể mang nhiều nghĩa:

- **Failed attempts / tổng callback attempts**: đo xác suất lỗi theo lần gọi.
- **Retry attempts / tổng callback attempts**: đo phần trăm các lần gọi là gọi lại.
- **Số item phải retry / số item được xử lý**: đo tỉ trọng item bị ảnh hưởng.
- **Retry-exhausted scopes / retry scopes đã bắt đầu**: đo độ nghiêm trọng theo từng đơn vị nghiệp vụ.

Các tỉ lệ này cần **cả tử số lẫn mẫu số cùng phạm vi đo**. Không lấy failed attempts chia trực tiếp cho `READ_COUNT` rồi gọi đó là “retry rate” chuẩn, vì Step có thể rollback, reprocess, filter, skip và writer có thể retry theo chunk.

Nếu mục tiêu là theo dõi item thực sự cần retry, cần định danh retry scope/item ổn định trong hệ thống quan sát và đếm một lần cho mỗi scope bị ảnh hưởng. Không đặt item ID làm tag Prometheus; sử dụng log/tracing có business key, và chỉ ghi aggregate metric vào registry.

## 11. Thiết kế dashboard vận hành

Một dashboard cho Job `importOrdersJob` có thể gồm:

| Ô giám sát | Nguồn | Cách hiểu |
| --- | --- | --- |
| Job status gần nhất | JobRepository/JobExplorer | COMPLETED, FAILED, STARTED... |
| Step duration theo thời gian | `spring.batch.step` | Độ trễ xử lý thay đổi như thế nào? |
| Failed retry callback rate | Custom counter + PromQL rate | Số lần callback báo exception tăng hay giảm? |
| Retry exhausted | Custom counter đúng theo exhaustion callback | Policy có xử lý được lỗi không? |
| Recovered after retry | Custom counter | Có bao nhiêu trường hợp được retry cứu thành công? |
| Rollback count / StepExecution | JDBC metadata | Transaction rollback nhiều ở Step nào? |
| Skip count / StepExecution | JDBC metadata | Bản ghi nào bị skip theo policy? |
| 5 loại failure category nhiều nhất | Custom metric với nhãn bounded | Lỗi từ database, HTTP, timeout, throttling hay loại khác? |

Khi đọc biểu đồ, cần đặt retry count cạnh thời lượng và throughput. Ví dụ:

- Retry event tăng, Step vẫn COMPLETED: có thể downstream đang suy yếu nhưng policy còn hấp thụ được.
- Retry event tăng, duration tăng và throughput giảm: có dấu hiệu bottleneck rõ.
- Retry event bằng 0 nhưng Job FAILED: có thể lỗi **không retryable**, lỗi cấu hình hoặc listener chưa instrument đúng đường đi.
- Rollback count tăng mà retry events không tăng tương ứng: có thể lỗi transaction/commit khác, hoặc retry được đo ở sai tầng.

Một dashboard không thể chứng minh exactly-once cho writer ngoài transaction; phải có metric nghiệp vụ và audit/idempotency tương ứng.

## 12. Phân nhóm lỗi và thiết kế label

Metric monitoring rất dễ gây tải lớn nếu mỗi bản ghi hoặc exception message trở thành một chuỗi time series.

**Nhãn nên có cardinality hữu hạn:**

~~~text
job = importOrdersJob
step = loadOrdersStep
failure_category = transient_db | timeout | rate_limited | other
service = order-import
environment = staging | production
~~~

**Không dùng các giá trị sau làm metric label:**

~~~text
jobExecutionId = 123456789
orderId = ORDER-2026-11-16-0000001
customerEmail = customer@example.com
exceptionMessage = timeout calling https://.../orders/123
requestId = UUID...
stackTrace = ...
~~~

Các giá trị này thay đổi theo từng execution/item, gây bùng nổ số series, tốn RAM trên Prometheus và có nguy cơ làm lộ dữ liệu nhạy cảm. Đưa chúng vào **structured logs** hoặc **traces**, với chính sách masking, retention và quyền truy cập phù hợp.

Nếu class exception quá nhiều, không dùng `throwable.getClass().getName()` làm metric tag không giới hạn. Thay bằng whitelist nhóm lỗi ổn định như `transient_db`, `external_timeout`, `rate_limited`, `other`.

## 13. Retry, skip, rollback và restart trong cùng một sự cố

Xét một record xấu gây exception mỗi lần:

~~~text
retryLimit = 3
skipLimit  = 1
exception vừa retryable vừa skippable theo policy

attempt 1 -> error -> onError
attempt 2 -> error -> onError
attempt 3 -> error -> onError
             retry exhausted
             skip policy cho phép bỏ record
Job có thể tiếp tục và hoàn thành
~~~

Các con số có thể là:

- Failed attempts từ retry listener: **3**.
- Actual retry attempts sau lần đầu: **2**.
- Process skip count: **1** nếu record được skip trong processor.
- Job status: vẫn có thể `COMPLETED`.
- Rollback count: phụ thuộc transaction, phase và cách retry/skip được thực hiện; không suy ra từ 3 failure events.

Một Step có thể retry ở **writer** trên cả chunk. Khi chunk bị rollback, processor có thể chạy lại cho nhiều item dù bản thân các item này không lỗi. Nếu đếm mỗi lần gọi `process()` rồi gọi đó là retry count, kết quả sẽ bao gồm cả reprocessing do rollback, khác retry attempts của writer.

Với reader có trạng thái di chuyển, phải đặc biệt cẩn thận. Nếu reader tiêu thụ item trước rồi ném lỗi, retry `read()` có thể chuyển sang bản ghi kế tiếp, khiến dữ liệu bị bỏ qua. Monitoring số lần lỗi không thay thế kiểm chứng reader có hành vi retry-safe, checkpoint ổn định và xử lý dữ liệu đúng.

## 14. Tránh double counting khi nhiều tầng retry

Ví dụ một ItemProcessor gọi HTTP client:

~~~text
Spring Batch Step retryLimit(3)
   |
   +-- Processor
        |
        +-- HTTP client riêng retry 2 lần
              |
              +-- request #1: timeout
              +-- request #2: timeout
              +-- request #3: success
~~~

Nếu HTTP client phục hồi sau request #3, listener retry của Spring Batch có thể **không thấy lỗi nào**, vì processor cuối cùng trả thành công. Metric từ HTTP client lại ghi nhận hai lần gọi lại.

Ngược lại, nếu HTTP client hết retry và ném exception ra processor, Spring Batch còn có thể retry cả processor, làm số HTTP request tăng thêm.

Hãy đặt tên theo **layer** và **đơn vị đếm**:

~~~text
app_http_client_failed_requests_total
app_http_client_retry_attempts_total
app_batch_step_failed_callbacks_total
app_batch_step_retry_exhausted_total
~~~

Chỉ số từ các tầng khác nhau phục vụ những câu hỏi khác nhau. Không cộng chúng thành một “retryCount” duy nhất rồi coi đó là số lần item đã chạy lại, trừ khi đã xác định rõ phép quy đổi.

## 15. Có nên lưu retry count vào ExecutionContext?

`ExecutionContext` được thiết kế để lưu **trạng thái phục hồi** của Job hoặc Step tại checkpoint. Nó không phải metric storage được cập nhật an toàn sau mọi failed callback.

Nếu trong `onError` gọi:

~~~java
// Ví dụ điều KHÔNG nên mặc định sử dụng để lấy số retry chính xác:
stepExecution.getExecutionContext()
    .putInt("retryCount", oldCount + 1);
~~~

thì có các rủi ro:

- Transaction rollback có thể làm mất một phần cập nhật, trong khi side effect ngoài transaction đã phát sinh.
- Context chỉ được persist tại các mốc thích hợp, không bảo đảm flush sau từng onError.
- Nhiều thread/partition cùng sửa một key có thể gây mất cập nhật.
- Sau restart, StepExecution khác có context khác; cộng dồn thiếu quy ước có thể không phản ánh mọi attempt đã xảy ra.
- Chỉ số retry trong ExecutionContext có thể trộn lẫn với trạng thái checkpoint quan trọng của reader.

**Khuyến nghị:** dùng Micrometer cho xu hướng, structured log/tracing cho từng sự kiện, và một **audit store nghiệp vụ bền vững** nếu cần biết số request/idempotency operation chính xác qua process crash. Audit nên có khóa event/scope ổn định và cơ chế chống ghi trùng; cần định nghĩa rõ rằng metric/audit đếm “đã thực thi”, “đã thất bại” hay “đã được ghi nhận”.

## 16. Spring Batch 6.x: thay đổi API retry monitoring

Kể từ Spring Batch 6.0, retry của framework không còn dựa trên Spring Retry như cách dùng ở 5.x; nó dựa trên **Spring Framework 7 core retry**.

| Chủ đề | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Retry API chính | `org.springframework.retry.*` | `org.springframework.core.retry.*` |
| Listener | `org.springframework.retry.RetryListener` | `org.springframework.core.retry.RetryListener` |
| Cấu hình Step | `.faultTolerant().retry(...).retryLimit(3).listener(retryListener)` | `.faultTolerant().retryPolicy(policy).retryListener(listener)` trên builder 6.x |
| Cách quan sát | `onError(RetryContext, RetryCallback, Throwable)` và `getRetryCount()` | `beforeRetry`, `onRetryFailure`, `onRetryPolicyExhaustion`, `onRetrySuccess`; một số bản Framework 7 có `RetryState` |
| Giá trị giới hạn | `retryLimit(3)` ở 5.x: tối đa 3 lần thử item | `RetryPolicy.builder().maxRetries(3)` ở Framework 7: 3 lần **retry sau lần đầu**, tức tối đa 4 attempts |
| Metadata StepExecution | Không có retry_count chuẩn cho từng item | Vẫn không thay thế custom retry telemetry cho từng item |

### Ví dụ cấu hình Step 6.x

~~~java
import java.util.Set;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.dao.TransientDataAccessException;

// Theo API Spring Framework 7:
RetryPolicy retryPolicy = RetryPolicy.builder()
        .maxRetries(2) // 1 initial + tối đa 2 retries = 3 attempts
        .includes(Set.of(TransientDataAccessException.class))
        .build();

// Theo builder chunk-oriented của Spring Batch 6:
Step step = new StepBuilder("loadOrdersStep", jobRepository)
        .<Order, Order>chunk(20)
        .transactionManager(transactionManager)
        .reader(orderReader)
        .processor(enrichmentProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retryPolicy(retryPolicy)
        .retryListener(coreRetryListener)
        .build();
~~~

`coreRetryListener` ở ví dụ này phải là implementation của **`org.springframework.core.retry.RetryListener`**, không phải `org.springframework.retry.RetryListener` của Batch 5.2. Đừng copy nguyên listener cũ và chỉ đổi import.

### Ví dụ listener theo API Spring Framework 7

~~~java
import org.springframework.core.retry.RetryListener;
import org.springframework.core.retry.RetryPolicy;
import org.springframework.core.retry.Retryable;

RetryListener listener = new RetryListener() {

    @Override
    public void onRetryFailure(
            RetryPolicy policy,
            Retryable<?> retryable,
            Throwable exception) {
        // Tăng failed retry attempt counter.
    }

    @Override
    public void onRetryPolicyExhaustion(
            RetryPolicy policy,
            Retryable<?> retryable,
            org.springframework.core.retry.RetryException exception) {
        // Tăng exhaustion counter, gắn với job/step đã biết.
    }

    @Override
    public void onRetrySuccess(
            RetryPolicy policy,
            Retryable<?> retryable,
            Object result) {
        // Ghi nhận scope phục hồi sau retry.
    }
};
~~~

**Lưu ý version:** chữ ký cụ thể và callback bổ sung của `RetryListener` có thể khác giữa các bản vá Spring Framework 7.0.x. Khi cần đếm **mọi attempt**, bao gồm attempt đầu và retry, những bản 7.0.x mới cung cấp `onRetryableExecution(..., RetryState)`; hãy xem Javadoc đúng version dependency đang được quản lý và test ranh giới counter.

Khác biệt **`retryLimit(3)` ở Batch 5** và **`maxRetries(3)` ở Framework 7** rất quan trọng. Nếu không làm rõ, dashboard và alert sau nâng cấp có thể xuất hiện chênh lệch chỉ vì hệ thống cho phép thêm một lần thực thi.

## 17. Kiểm thử phép đếm retry

Một bài test monitoring phải định nghĩa trước **điểm instrumentation**, **đơn vị đếm**, **policy** và **kết quả kỳ vọng**.

| Kịch bản | Kỳ vọng với retryLimit(3) ở Spring Batch 5.2 |
| --- | --- |
| Item thành công lần đầu | 1 callback attempt, 0 failed attempt, 0 executed retry. |
| Lỗi 1 lần rồi thành công | 2 callback attempts, 1 failure event, 1 retry. |
| Lỗi 2 lần rồi thành công | 3 callback attempts, 2 failure events, 2 retries. |
| Lỗi cả 3 attempt | 3 failed attempts, 2 retries thực thi; Step FAILED hoặc skip tùy policy. |
| Exception không nằm trong retry policy | Không tự retry; Step có thể FAILED/skip; listener chỉ ghi sự kiện nếu lỗi đi qua callback được quan sát. |
| Writer rollback rồi processor chạy lại | Rollback/reprocessing có thể tăng khác với retry listener events. |
| Job restart sau FAILED | JobExecution mới, scope retry mới; tổng counter cấp ứng dụng tiếp tục theo vòng đời metrics backend. |
| Có retry ở cả HTTP client và Spring Batch | Counters của hai layer khác nhau, không được cộng mù quáng. |

### Ví dụ kiểm tra metric bằng spring-batch-test

Đây là **khung integration test** minh họa, giả định dự án đã cấu hình Job `importOrdersJob`, listener và một processor có thể giả lập lỗi.

~~~java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;

import static org.junit.jupiter.api.Assertions.*;

// Các bean được inject trong test context có @SpringBatchTest:
// JobLauncherTestUtils launcher;
// MeterRegistry registry;
// Một fault injector được reset để chỉ ném lỗi đúng 2 lần.

@Test
void recordsFailedAttemptsBeforeSuccessfulRetry() throws Exception {
    Counter counterBefore = registry.find(
            "app.batch.retry.failed.attempts")
        .tags(
            "job", "importOrdersJob",
            "step", "loadOrdersStep",
            "failure_category", "transient_db")
        .counter();

    double before = counterBefore == null
            ? 0
            : counterBefore.count();

    JobExecution execution = launcher.launchJob(
        new JobParametersBuilder()
            .addLong("testRun", System.nanoTime())
            .toJobParameters()
    );

    assertEquals(BatchStatus.COMPLETED, execution.getStatus());

    Counter counterAfter = registry.find(
            "app.batch.retry.failed.attempts")
        .tags(
            "job", "importOrdersJob",
            "step", "loadOrdersStep",
            "failure_category", "transient_db")
        .counter();

    assertNotNull(counterAfter);
    assertEquals(2.0, counterAfter.count() - before, 0.001);
}
~~~

Ở đây, test **phải** có fault injector xác định đúng hai failure callback đi qua listener; nếu processor/writer hoặc Step khác tạo thêm lỗi, assertion `2` không còn có ý nghĩa. Với test chạy song song hoặc registry được chia sẻ giữa nhiều Job, hãy cấp MeterRegistry độc lập cho test hoặc cô lập các Step/job, thay vì tính chênh lệch trên counter chung.

Đối với Step thực thi bất đồng bộ, cần chờ JobExecution đến trạng thái cuối trước khi assert. Không đặt toàn bộ bài integration test trong transaction che khuất commit/rollback thực tế của Job.

### Đếm attempt thật bằng fault injector

Trong một unit test riêng của logic gọi dịch vụ, có thể dùng biến đếm để xác nhận số lần callback được **thực sự thực thi**:

~~~java
AtomicInteger invocations = new AtomicInteger();

Integer result = retryTemplate.execute(context -> {
    int callNumber = invocations.incrementAndGet();
    if (callNumber <= 2) {
        throw new TransientDataAccessResourceException("temporary");
    }
    return 42;
});

assertEquals(42, result);
assertEquals(3, invocations.get());
~~~

Đây là ví dụ minh họa **Spring Retry 2.x**; cần cấu hình RetryTemplate với policy cho phép ít nhất ba total attempts và import các type phù hợp. Đếm invocation ở lớp cần đo là cách kiểm chứng khác biệt giữa “attempt đã gọi” và “event exception đã ghi”.

## 18. Cảnh báo khi retry count tăng

Không nên cảnh báo chỉ vì một item có một lần retry. Lỗi tạm thời là lý do retry policy tồn tại. Mức cảnh báo phải phản ánh ngưỡng vận hành và rủi ro nghiệp vụ.

Ví dụ chính sách:

| Điều kiện | Mức độ | Hành động |
| --- | --- | --- |
| Failed attempt rate tăng nhẹ, Job vẫn COMPLETED | Theo dõi | Xem latency và tình trạng dịch vụ phụ thuộc. |
| Failed attempt rate cao liên tục 10–15 phút | Warning | Xem category, capacity, timeout và traffic thay đổi. |
| Retry exhaustion xảy ra lặp lại trong Step quan trọng | Critical tùy nghiệp vụ | Kiểm Step status, item backlog và khả năng xử lý lại. |
| Retry cao cùng với throughput giảm | Warning/Critical | Xác định bottleneck, cân nhắc backoff hoặc giảm tải. |
| Retry tăng sau triển khai phiên bản mới | Điều tra | So sánh theo version và lỗi, tránh kết luận do nguyên nhân khác. |
| Lỗi không retryable khiến Job FAILED | Critical tùy SLA | Cảnh báo qua BatchStatus dù retry metric bằng 0. |

Ví dụ PromQL minh họa một ngưỡng tốc độ lỗi:

~~~promql
sum by (job, step) (
  rate(app_batch_retry_failed_attempts_total[10m])
) > 0.5
~~~

Ngưỡng `0.5` tức khoảng 0,5 failure event/giây, chỉ là giá trị **minh họa**. Trong thực tế, cần hiệu chỉnh theo throughput của Job, giờ chạy theo lịch, SLA, và lỗi nào là bình thường. Một Job chỉ chạy mỗi đêm không nên bị so sánh liên tục với service chạy 24/7 bằng cùng ngưỡng.

Prometheus counter có thể reset khi JVM khởi động lại. Dùng `rate`/`increase` cho các khoảng thời gian thay vì lấy chênh lệch trực tiếp của hai lần scrape mà không xét reset. Nếu cần số retry **chính xác theo một business batch qua nhiều lần khởi động**, cần audit có tính bền vững riêng.

## 19. Những lỗi thường gặp khi theo dõi retry

**1. Lấy `StepExecution.rollbackCount` đặt tên thành retry count.** Rollback là hành vi transaction; nhiều lần retry có thể đi kèm một rollback hoặc ngược lại. Cần lấy từ retry listener hay instrumentation ở đúng callback.

**2. Mỗi `onError` đều được gọi là “đã retry thêm một lần”.** `onError` biểu diễn lần thất bại vừa xảy ra. Lần cuối có thể hết retry, nên không có attempt tiếp theo. Đặt tên metric chính xác.

**3. Đếm cả Job restart vào retry count của item.** JobExecution mới có identity riêng; hai cấp độ cần chỉ số khác nhau.

**4. Chỉ nhìn số lỗi tổng cộng, không nhìn throughput.** Job xử lý một triệu item có thể có nhiều failure events hơn Job xử lý một nghìn item mà vẫn khỏe hơn theo tỉ lệ.

**5. Dùng itemId/executionId làm metric tag.** Làm tăng cardinality và tiêu thụ tài nguyên. Dùng log/trace cho định danh chi tiết.

**6. Không phân biệt retry ở Step và retry ở HTTP client.** Một exception có thể bị xử lý nhiều lớp; metric “retry count” chung dễ bị đếm lặp hoặc thiếu.

**7. Cho rằng metric Micrometer tự lưu vào JobRepository.** Metric sống theo MeterRegistry và backend monitoring; ExecutionContext và bảng metadata có mục đích khác.

**8. Gắn listener cho Step chưa bật fault tolerance.** Cần xác minh Step thực sự dùng retry policy và listener đúng builder/version. Retry ở thư viện bên ngoài Step sẽ không tự đi qua Batch RetryListener.

**9. Quên skip/recover sau khi exhausted.** Retry hết hạn không nhất thiết làm Job FAILED nếu lỗi được cấu hình skip. Dashboard cần theo dõi cả outcome và skip count.

**10. Đổi phiên bản nhưng giữ kỳ vọng retry limit cũ.** Spring Batch 5.2 `retryLimit(3)` và Spring Framework 7 `maxRetries(3)` có cách diễn đạt khác nhau về số lần thử, nên test boundary phải được cập nhật.

**11. Đếm bằng AtomicInteger toàn cục trong Job đa luồng.** Counter không có scope và không đồng bộ có thể sai khi phân vùng/parallel Step. Micrometer counters thread-safe hơn cho tổng quan, và log có context cho từng execution.

**12. Ghi quá nhiều log ở mọi lỗi ngay trên đường nóng.** Một sự cố lớn có thể tạo hàng triệu dòng log. Với hệ thống throughput cao, nên dùng sampling/rate limiting cho log và giữ metrics tổng hợp.

## 20. Bài tập thực hành

### Bài 1 — Đếm failed attempts

Tạo Step có processor ném exception tạm thời hai lần cho item ID 7, lần ba trả kết quả. Cấu hình `retryLimit(3)` (Spring Batch 5.2), gắn `RetryListener.onError` và Micrometer counter.

Kỳ vọng: 3 callback attempts, 2 failure events, 2 actual retries; Step `COMPLETED` nếu các item khác cũng hợp lệ.

### Bài 2 — Hết retry và skip

Giữ exception luôn xảy ra tại item ID 7, dùng `retryLimit(3)` rồi cấu hình `skip`/`skipLimit` phù hợp. Xác minh counter lỗi ghi đủ các lần thất bại và StepExecution ghi đúng item skip count. Đừng suy ra retry từ rollbackCount.

### Bài 3 — Đưa metric lên Prometheus

Bật Actuator Prometheus endpoint trong môi trường test, export counter `app.batch.retry.failed.attempts` và viết hai query `rate`/`increase` để so sánh khi dịch vụ phụ thuộc bình thường và khi có timeout.

### Bài 4 — Hai tầng retry

Thêm retry ở HTTP client và retry ở Batch Step. Ghi metric khác nhau cho mỗi tầng, đo tổng request vật lý rồi chứng minh vì sao không được cộng các counter khác tầng như cùng đơn vị.

### Bài 5 — Restart sau failure

Cho JobExecution đầu thất bại sau khi đã retry hết ngân sách, sửa nguồn lỗi rồi restart đúng JobInstance. Kiểm tra JobRepository có hai JobExecution; dashboard thể hiện số failure events ở từng execution qua log/trace, còn metric tổng là aggregate theo Job/Step.

### Bài 6 — Chống cardinality explosion

Giả lập 100.000 item lỗi và tạo metric sai khi dùng itemId làm tag. Thiết kế lại thành nhãn `job`, `step`, `failure_category` cùng log có correlation ID. Phân tích khác biệt số series trước/sau.

### Bài 7 — Chuyển API lên Spring Batch 6

Chuyển từ Spring Retry listener sang Spring Framework core RetryListener. Dùng `RetryPolicy.builder().maxRetries(2)` để giữ tổng ba attempts như cấu hình `retryLimit(3)` của 5.x; sửa test kiểm count và các callback failure/exhaustion cho đúng dependency version.

## 21. Tài liệu tham khảo chính thức

- [Spring Batch 5.2 — Retry Logic](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch 5.2 — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html)
- [Spring Batch 5.2 — FaultTolerantStepBuilder API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/step/builder/FaultTolerantStepBuilder.html)
- [Spring Retry 2.x — RetryListener API](https://docs.spring.io/spring-retry/docs/2.0.12/apidocs/org/springframework/retry/RetryListener.html)
- [Spring Batch 6 — Retry](https://docs.spring.io/spring-batch/reference/retry.html)
- [Spring Batch 6 — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch 6 — Micrometer Support](https://docs.spring.io/spring-batch/reference/spring-batch-observability/micrometer.html)
- [Spring Framework 7 — RetryListener API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/retry/RetryListener.html)
- [Spring Framework 7 — RetryPolicy.Builder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/retry/RetryPolicy.Builder.html)
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)

