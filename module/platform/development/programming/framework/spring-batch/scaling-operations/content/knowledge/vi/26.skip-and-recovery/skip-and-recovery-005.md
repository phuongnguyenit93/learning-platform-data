# Recoverer sau khi retry hết lượt trong Spring Batch

> **Chương:** Skip và recovery
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và xử lý phân tán; đo nút thắt, bảo đảm thread safety, retry/restart và lựa chọn kiến trúc theo tài nguyên thực tế. Bài học đi sâu vào **điểm kết thúc retry**, các kiểu **recovery có kiểm soát** và cách tránh làm mất dữ liệu hoặc tạo tác dụng phụ trùng khi chạy nhiều worker.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích **retry exhausted** là gì và phân biệt recovery với skip, filter, rollback, restart.
2. Phân biệt **fault-tolerant step của Spring Batch** với **`RetryTemplate` và `RecoveryCallback` của Spring Retry**; không nhầm recovery thành một phương thức mặc định của `StepBuilder`.
3. Cấu hình retry có giới hạn, backoff và xử lý sau khi hết lượt bằng ba hướng: **fail**, **skip có audit**, hoặc **defer/fallback có kết quả nghiệp vụ rõ ràng**.
4. Thiết kế recoverer có idempotency key, transaction/outbox và quy trình replay, tránh báo thành công giả khi hệ thống bên ngoài chưa xử lý.
5. Kiểm thử ngưỡng retry, ngoại lệ không retry được, worker partition đồng thời, crash/restart và đối soát kết quả.

## 1. Khi retry hết lượt, hệ thống phải quyết định điều gì?

Giả sử một job nhập 2 triệu đơn hàng. Trong `ItemProcessor`, worker cần gọi dịch vụ tra cứu phân nhóm khách hàng. Đôi lúc dịch vụ trả timeout:

~~~text
ORDER-1001
   |
   +-- Lần gọi #1: timeout
   +-- Lần gọi #2: timeout
   +-- Lần gọi #3: timeout
   |
   +-- Hết ngân sách retry: làm gì tiếp?
          A. Fail worker/step để vận hành khắc phục?
          B. Skip item nếu nghiệp vụ cho phép mất item này?
          C. Ghi trạng thái DEFERRED để xử lý bù?
          D. Trả fallback đã được hợp đồng nghiệp vụ chấp nhận?
~~~

**Retry** trả lời câu hỏi “có nên thử lại thao tác bị lỗi hay không?”. **Recovery** trả lời câu hỏi khác: “khi thử lại không còn phù hợp hoặc không còn lượt, phải chuyển công việc vào trạng thái nào?”.

Một recoverer tốt **không mặc định biến lỗi thành thành công**. Nó phải tạo ra kết quả có thể giải thích, kiểm toán, khôi phục và đối soát.

### Bốn kết quả cần phân biệt

| Kết quả | Ý nghĩa | Có thể làm job `COMPLETED`? | Điều kiện an toàn |
| --- | --- | --- | --- |
| **Fail** | Không tiếp tục vì yêu cầu chưa đạt | Không, nếu lỗi làm step/job thất bại | Lưu checkpoint và có runbook restart |
| **Skip** | Chấp nhận loại bỏ item cụ thể khỏi luồng bình thường | Có thể, nếu trong `skipLimit` | Exception được whitelist; item được quarantine/replay |
| **Defer** | Chuyển việc sang hàng đợi/bảng chờ có trạng thái rõ | Có thể, theo hợp đồng nghiệp vụ | Bản ghi DEFERRED được lưu bền vững, idempotent, có worker xử lý bù |
| **Fallback** | Dùng kết quả thay thế đáp ứng quy tắc nghiệp vụ | Có thể | Fallback thực sự hợp lệ, được theo dõi và có giới hạn |

Ví dụ không thể gọi thanh toán thành công chỉ vì recoverer trả về `true` sau ba lần timeout. API có thể **đã trừ tiền nhưng mất phản hồi** hoặc chưa thực hiện gì; cần tra cứu trạng thái qua idempotency key trước khi quyết định bước tiếp.

## 2. Phân biệt các cơ chế trong hệ sinh thái Spring

Khái niệm “recoverer” dễ gây nhầm vì ứng dụng Spring có nhiều cơ chế xử lý lỗi:

| Cơ chế | Nơi thực thi | Hành vi khi hết retry |
| --- | --- | --- |
| `FaultTolerantStepBuilder` với `retry(...)` | Trong fault-tolerant chunk step **Spring Batch** | Xét cấu hình skip/fail; không tự gọi một `RecoveryCallback` do ứng dụng không đăng ký |
| `SkipPolicy` / `skip(...)` | Trong step Batch | Nếu exception skippable và còn budget, skip item; hết budget thì fail |
| `RetryTemplate` + `RecoveryCallback<T>` | **Spring Retry** do ứng dụng chủ động gọi | Gọi recovery callback khi retry không tiếp tục, theo hợp đồng template |
| `RetryTemplate` không có recovery callback | Spring Retry | Propagate lỗi theo cơ chế template khi retry không thành công |
| `JobOperator.restart(...)` | Vận hành job Spring Batch | Tạo lượt thực thi mới cho `JobInstance` có thể restart |
| Quarantine/replay workflow | Ứng dụng tự thiết kế | Xử lý bù item sau khi dữ liệu/hạ tầng đã được khắc phục |

**Lưu ý:** Spring Batch dùng các ý tưởng/cơ chế retry trong fault-tolerant processing, nhưng `RetryTemplate.execute(retryCallback, recoveryCallback)` là API **Spring Retry**, không phải phương thức `.recover(...)` có sẵn của `FaultTolerantStepBuilder` trong cấu hình Batch 5.x phổ biến.

Không nên thêm một `RetryTemplate` bên trong processor **và** bật retry cùng exception ở step mà không tính tổng số attempts: hai tầng retry có thể nhân số lần gọi dịch vụ bên ngoài, tăng tải và làm cạn tài nguyên khi hệ thống đang lỗi.

## 3. Luồng quyết định sau khi retry thất bại

~~~mermaid
flowchart TD
    A["Read / Process / Write"] --> B{"Có exception?"}
    B -- "Không" --> S["Kết quả bình thường"]
    B -- "Có" --> C{"Exception retryable?"}
    C -- "Có, còn lượt" --> R["Backoff rồi thử lại"]
    R --> A
    C -- "Không hoặc hết lượt" --> D{"Có recovery policy hợp lệ?"}
    D -- "Không" --> F["Propagate error / Step FAILED"]
    D -- "Skip được và còn budget" --> K["Skip item + SkipListener<br/>quarantine"]
    D -- "Defer/fallback được phép" --> E["Kết quả có trạng thái rõ<br/>ghi bền vững"]
    K --> N["Tiếp tục chunk theo policy"]
    E --> N
~~~

Sơ đồ mô tả các **lựa chọn thiết kế**, không có nghĩa tất cả nhánh đều do một API duy nhất quyết định. Trong Spring Batch, retry/skip có thể gây rollback và tái thực thi chunk trước khi phân loại item. Với `RetryTemplate` được gọi thủ công, recovery callback trả kết quả hoặc ném lỗi theo logic ứng dụng.

### Phân biệt retry với restart

- **Retry**: thử lại một thao tác/item/chunk theo chính sách trong một quá trình xử lý; thường có giới hạn số lần và backoff.
- **Restart**: khởi tạo `JobExecution` mới cho **cùng `JobInstance`** sau thất bại/dừng; dùng `JobRepository` và `ExecutionContext` để khôi phục.
- **Recovery**: quyết định kết quả thay thế, hoãn xử lý hoặc thất bại khi retry không còn hiệu quả.
- **Replay/reprocess**: xử lý lại dữ liệu đã skip/defer hoặc dữ liệu nghiệp vụ cần sửa, có thể bằng **workflow riêng** chứ không nhất thiết bằng restart job cũ.

Một worker có thể đã retry ba lần rồi thất bại; sau khi vận hành restart job, worker lại xử lý công việc đó. Vì vậy **giới hạn retry trong một lần thực thi không phải ngân sách attempts xuyên toàn bộ lịch sử JobInstance**.

## 4. Kịch bản A — Hết retry và fail step

Đối với lỗi hạ tầng nghiêm trọng hoặc bước có yêu cầu **không được thiếu một item**, fail là lựa chọn bảo thủ và thường an toàn hơn tạo một kết quả giả.

Ví dụ fault-tolerant chunk step Spring Batch 5.x:

~~~java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step criticalImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputOrder> reader,
        ItemProcessor<InputOrder, OutputOrder> processor,
        ItemWriter<OutputOrder> writer) {

    return new StepBuilder("criticalImportStep", jobRepository)
            .<InputOrder, OutputOrder>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .build();
}
~~~

`InputOrder` và `OutputOrder` là kiểu dữ liệu do ứng dụng định nghĩa. Ví dụ lược bỏ `@Configuration` và các imports bean. `retryLimit(3)` thể hiện giới hạn retry trong chính sách của step; hãy kiểm thử số lần gọi thực tế theo loại lỗi, giai đoạn chunk và phiên bản được dùng thay vì suy diễn rằng mọi reader/writer đều có cùng số lần gọi.

Ở đây **không cấu hình skip** `TransientDataAccessException`. Khi lỗi DB tiếp diễn vượt khả năng retry, step có thể `FAILED` thay vì nuốt lỗi. Operator xác định nguyên nhân, sửa kết nối/tài nguyên rồi restart job nếu đủ điều kiện.

**Tránh** cấu hình `skip(TransientDataAccessException.class)` chỉ để job hoàn thành: lỗi database không nói rằng một item nghiệp vụ sai; skip có thể làm mất hàng loạt bản ghi hợp lệ.

### Khi nào cách fail đúng hơn fallback?

| Hoạt động | Vì sao nên fail khi không biết kết quả |
| --- | --- |
| Ghi ledger tài chính | Không được coi giao dịch đã ghi nếu chưa xác nhận commit |
| Thanh toán qua API | Timeout có thể là trạng thái *không rõ*, phải reconcile bằng idempotency key |
| Cập nhật dữ liệu bắt buộc | Thiếu item vi phạm invariant của output |
| Thay đổi schema/permission DB | Retry liên tục hoặc skip không sửa được lỗi gốc |
| Dữ liệu nguồn bị sai hàng loạt | Cần dừng và xác minh chất lượng đầu vào |

## 5. Kịch bản B — Sau retry, skip item khi được phép

Một số lỗi ban đầu có thể retry nhưng sau khi dùng hết attempts, nghiệp vụ cho phép **bỏ qua một item**. Khi đó có thể cấu hình exception nằm trong cả retry và skip policy:

~~~java
.faultTolerant()
.retry(PartnerTemporaryException.class)
.retryLimit(3)
.skip(PartnerTemporaryException.class)
.skipLimit(5)
.listener(skipListener)
~~~

Đây là **đoạn cấu hình bổ sung trong step builder**, không phải bean độc lập. `PartnerTemporaryException` là exception ứng dụng; `skipListener` triển khai `SkipListener<I,O>` tương ứng.

Trong đường xử lý được hỗ trợ, sau khi retry không còn khả năng tiếp tục, lỗi có thể được **skip** nếu classifier cho phép và `skipLimit` chưa hết. Nếu lỗi không skippable hoặc đã vượt ngưỡng, step thất bại. Hành vi chi tiết ở đọc/xử lý/ghi và transaction cần được kiểm thử, nhất là khi writer có thể rollback chunk nhiều lần.

### Vì sao không phải mọi lỗi hết retry đều được skip?

Giả sử dịch vụ enrichment mất kết nối trong 30 phút. Nếu mỗi worker đều skip hàng chục nghìn order vì timeout, job có thể báo `COMPLETED` nhưng dữ liệu downstream thiếu gần như toàn bộ enrichment. Một giới hạn nhỏ **theo worker StepExecution** chỉ là một hàng rào, không phải cam kết chất lượng cho toàn job.

Khi chọn skip, cần:

- Exception thể hiện lỗi **được phép bỏ item**, không chỉ là lỗi hệ thống chung.
- `skipLimit` phù hợp với số item của worker và tổng mức chấp nhận của job.
- `SkipListener` ghi đúng source ID, phase và reason vào quarantine.
- Có cách sửa/replay các item đã skip, kể cả ở partition `COMPLETED`.
- Có đối soát số business keys đủ điều kiện và số đã thực sự xử lý.

### Skip và filter khác nhau

Nếu `ItemProcessor.process(item)` trả `null`, Spring Batch xem item là **filtered**, không phải skipped. `filterCount` tăng, **`SkipListener` không được gọi** vì không có exception được skip.

Không nên chuyển mọi kết quả thất bại thành `null` sau khi retry hết lượt. Cách này biến một lỗi không xử lý được thành filter “hợp lệ” và có thể che mất dữ liệu bị loại.

## 6. Kịch bản C — Dùng RecoveryCallback của Spring Retry

Khi ứng dụng thật sự muốn **trả về một kết quả dự phòng có trạng thái rõ**, có thể sử dụng `RetryTemplate` với `RecoveryCallback<T>` của **Spring Retry**.

Ví dụ: processor tra cứu nhóm khách hàng từ dịch vụ chỉ-đọc. Nếu dịch vụ không sẵn sàng sau các attempts, hệ thống được phép **lưu một bản ghi `DEFERRED`** thay vì đoán nhóm khách hàng. Một quy trình độc lập sẽ xử lý lại các bản DEFERRED khi dịch vụ phục hồi.

### 6.1. Cấu hình RetryTemplate có giới hạn và backoff

~~~java
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.retry.backoff.ExponentialBackOffPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

@Bean
RetryTemplate partnerRetryTemplate() {
    RetryTemplate template = new RetryTemplate();

    // Chỉ retry exception được xác định là lỗi tạm thời.
    SimpleRetryPolicy retryPolicy = new SimpleRetryPolicy(
            3,
            Map.of(PartnerTemporaryException.class, true));
    template.setRetryPolicy(retryPolicy);

    ExponentialBackOffPolicy backoff = new ExponentialBackOffPolicy();
    backoff.setInitialInterval(200L);
    backoff.setMultiplier(2.0);
    backoff.setMaxInterval(2_000L);
    template.setBackOffPolicy(backoff);

    return template;
}
~~~

Các giá trị **3 attempts, 200 ms và 2 giây** chỉ minh họa. `SimpleRetryPolicy` của Spring Retry tính giới hạn `maxAttempts` theo **số attempts tối đa gồm lần gọi đầu**, nhưng cần đo số lời gọi thật nếu kết hợp các tầng retry khác. Không nên đặt backoff quá lớn trong hàng nghìn worker khiến thread bị chiếm giữ lâu; hãy cân nhắc timeout, circuit breaker và điều phối công việc deferred.

Trong Gradle, ứng dụng cần có thư viện Spring Retry tương thích:

~~~groovy
dependencies {
    implementation 'org.springframework.retry:spring-retry'
}
~~~

Nếu ứng dụng đã nhận được Spring Retry thông qua dependency quản lý sẵn, không cần khai báo lại phiên bản thủ công trái với dependency management. Ví dụ hướng tới Spring Batch 5.x / Spring Retry tương thích; cấu hình package có thể khác khi dùng phiên bản lớn khác.

### 6.2. Định nghĩa đầu ra không che thất bại

~~~java
public record InputOrder(String sourceId, String customerId) {}

public enum EnrichmentState {
    READY,
    DEFERRED
}

public record EnrichmentDecision(
        String sourceId,
        String customerId,
        EnrichmentState state,
        String customerSegment) {

    public static EnrichmentDecision ready(
            InputOrder input, String segment) {
        return new EnrichmentDecision(
                input.sourceId(), input.customerId(),
                EnrichmentState.READY, segment);
    }

    public static EnrichmentDecision deferred(InputOrder input) {
        return new EnrichmentDecision(
                input.sourceId(), input.customerId(),
                EnrichmentState.DEFERRED, null);
    }
}
~~~

`DEFERRED` là **trạng thái nghiệp vụ công khai**, không phải tương đương `COMPLETED` của bản ghi đầu ra. Một hệ thống downstream chỉ chấp nhận `READY` phải chặn các bản ghi deferred cho tới khi được xử lý bù thành công.

### 6.3. Processor có RecoveryCallback

~~~java
import org.springframework.batch.item.ItemProcessor;
import org.springframework.retry.support.RetryTemplate;

public final class PartnerEnrichmentProcessor
        implements ItemProcessor<InputOrder, EnrichmentDecision> {

    private final RetryTemplate retryTemplate;
    private final PartnerClient partnerClient;

    public PartnerEnrichmentProcessor(
            RetryTemplate retryTemplate,
            PartnerClient partnerClient) {
        this.retryTemplate = retryTemplate;
        this.partnerClient = partnerClient;
    }

    @Override
    public EnrichmentDecision process(InputOrder input) {
        return retryTemplate.execute(
                context -> {
                    // Chỉ gọi API đọc dữ liệu. Timeout được phân loại
                    // thành PartnerTemporaryException bởi client.
                    String segment =
                            partnerClient.lookupSegment(input.customerId());
                    return EnrichmentDecision.ready(input, segment);
                },
                context -> {
                    Throwable last = context.getLastThrowable();
                    if (!(last instanceof PartnerTemporaryException)) {
                        // Không biến lỗi dữ liệu, bug hay lỗi bảo mật
                        // thành DEFERRED.
                        throw new IllegalStateException(
                                "Recovery không cho phép loại lỗi này", last);
                    }
                    // Không ghi API/quarantine ngoài transaction ở đây.
                    // Writer sẽ lưu DEFERRED bền vững theo sourceId.
                    return EnrichmentDecision.deferred(input);
                });
    }
}
~~~

`PartnerClient` và `PartnerTemporaryException` là contract/exception minh họa do ứng dụng định nghĩa. `RetryTemplate.execute(retryCallback, recoveryCallback)` là **lời gọi do processor chủ động thực hiện**; khi hết retry theo policy và chuyển sang recovery, callback trả về một `EnrichmentDecision` hoặc ném exception.

**Trường hợp lỗi không retryable:** Không được mặc nhiên cho mọi exception đi qua recovery giống nhau. Đoạn code kiểm tra `last` nhằm không đổi lỗi programming/authorization/schema thành trạng thái deferred. Cũng có thể thiết kế recovery policy riêng theo phân loại lỗi, nhưng phải kiểm thử đúng logic khi template không cho phép retry.

### 6.4. Writer phải lưu DEFERRED thật sự

~~~text
InputOrder ORDER-1001
       |
       v
PartnerEnrichmentProcessor
       |
       +-- READY ----------> Writer: ghi kết quả enrichment hợp lệ
       |
       +-- DEFERRED -------> Writer: ghi trạng thái chờ xử lý
                                      + sourceId ổn định
                                      + reason/nextRetryAt nếu cần
                                      + unique business key
                                      + transactional outbox nếu phát message
~~~

Giả sử writer dùng một bảng `enrichment_results` có khóa duy nhất `(source_version, source_id)`. Khi nhận `DEFERRED`, nó phải **upsert có kiểm soát** trạng thái chờ; khi nhận `READY`, nó lưu kết quả enrichment. Quy tắc chuyển trạng thái `DEFERRED → READY` cần bảo vệ bằng transaction/optimistic locking nếu nhiều worker hoặc replay cùng cập nhật.

**Không** chỉ `return EnrichmentDecision.deferred(...)` mà không có writer xử lý trạng thái đó. Nếu writer âm thầm bỏ qua DEFERRED, job có thể hoàn thành mà không còn dấu vết công việc cần làm. Recovery callback cũng không có cam kết rằng transaction chunk sẽ commit: nếu writer rollback, processor có thể được gọi lại và đường recovery có thể xuất hiện lại.

### DEFERRED không phải Batch skip

Trong ví dụ trên, processor **trả về một output item**, không ném exception cuối cùng cho fault-tolerant step. Vì thế:

- Không tự động tăng `processSkipCount`.
- `SkipListener.onSkipInProcess` không tự được gọi.
- Output có thể được tính vào các chỉ số xử lý/ghi theo hành vi writer.
- Muốn biết tổng item chưa enrichment, phải có metric **`deferredCount` hoặc số dòng DEFERRED** ở tầng nghiệp vụ.

Đây là khác biệt quan trọng giữa **recovery trả một giá trị có ý nghĩa nghiệp vụ** và **skip một item** trong Spring Batch.

## 7. RecoveryCallback không thay thế transaction và idempotency

Một callback chỉ biết kết quả từ các lần gọi mà ứng dụng **quan sát được**. Trong hệ thống phân tán, timeout không chứng minh lệnh bên ngoài chưa thành công.

### Nếu API có tác dụng phụ

Giả sử worker gọi API thanh toán:

~~~text
Gửi charge(orderId=123, idempotencyKey=PAY-123)
       |
       +-- Hệ thống nhận đã xử lý thành công
       |
       +-- Phản hồi bị mất do timeout
       |
       +-- Retry hoặc recovery không biết trạng thái thật
~~~

Sai lầm là recoverer đánh dấu `FAILED` rồi gửi một yêu cầu thanh toán mới với **idempotency key khác**, dẫn tới nguy cơ thu tiền hai lần. Cần truy vấn trạng thái theo **cùng một idempotency key**, có cơ chế reconciliation hoặc chuyển sang `UNKNOWN/PENDING_CONFIRMATION` thay vì khẳng định thành công/thất bại không có bằng chứng.

### So sánh hai loại lời gọi bên ngoài

| Loại thao tác | Recovery phù hợp | Cảnh báo |
| --- | --- | --- |
| API tra cứu dữ liệu chỉ đọc | Có thể defer hoặc dùng fallback được duyệt | Cần biết kết quả còn hợp lệ trong bao lâu |
| Ghi ledger hoặc thanh toán | Fail hoặc trạng thái **chưa xác định** để reconcile | Không tạo lần ghi mới tùy ý sau timeout |
| Gửi email/thông báo | Outbox với dedupe key, trạng thái chờ giao | “Đã gửi” có thể khác “đã nhận” |
| Đọc file/input bất biến | Retry nếu transient I/O, sau đó fail/quarantine theo rule | Không bỏ qua vùng dữ liệu quan trọng |
| Database tạm mất kết nối | Retry có giới hạn, sau đó fail bước | Không skip item hợp lệ vì lỗi hạ tầng |

### Ba mức bảo vệ thường cần phối hợp

1. **Identity:** `jobInstance + sourceVersion + businessId + operation` hoặc key nghiệp vụ phù hợp, ổn định qua retry/restart.
2. **Durability:** Trạng thái `DEFERRED`/outbox/quarantine phải commit cùng transaction thích hợp với kết quả nghiệp vụ.
3. **Replay safety:** Consumer và writer có unique constraint, idempotency và luật chuyển trạng thái cho trường hợp hai worker cùng nhìn thấy một item.

Một biến `AtomicInteger` hoặc `ConcurrentHashMap` trong JVM không thay thế khóa bền vững khi worker nằm ở nhiều process/container.

## 8. Recovery khi lỗi nằm ở ItemReader, ItemProcessor hay ItemWriter

| Giai đoạn | Đặc thù | Lựa chọn thường phù hợp |
| --- | --- | --- |
| **Read** | Có thể chưa dựng được item; reader giữ cursor/offset | Retry lỗi I/O transient, fail nếu checkpoint không tin cậy; skip lỗi parse riêng lẻ nếu nghiệp vụ cho phép |
| **Process** | Có input item để giữ correlation ID | Retry tra cứu tạm thời; sau hết lượt có thể defer output hoặc skip validation theo policy |
| **Write** | Writer xử lý cả chunk, có transaction hoặc side effect | Retry có idempotency, rollback đúng; fail/reconcile nếu kết quả bên ngoài chưa rõ |

### Read recovery cần biết item nào?

Nếu một `FlatFileItemReader` không parse được dòng 421, `FlatFileParseException` có thể giúp nhận diện file và số dòng. Nếu kết nối reader JDBC lỗi, exception thường **không** đồng nghĩa một business item cụ thể bị sai. Không tạo một “read recovery” xóa ngẫu nhiên record cuối rồi tiếp tục nếu nguồn/offset chưa chắc chắn.

### Process recovery có thể che mất dữ liệu

Nếu recoverer trả `null` từ `ItemProcessor`, Batch xem đó là **filter**. Đây có thể là lựa chọn đúng nếu rule nghiệp vụ chủ động loại item, nhưng không phù hợp khi cần báo cáo “dịch vụ enrichment lỗi, sẽ xử lý lại”.

Nên trả một đối tượng **`DEFERRED` có identity rõ**, hoặc ném lỗi để Batch skip/fail theo chính sách đã thiết kế.

### Write recovery có thể lặp tác dụng phụ

Trong chunk-oriented step, `ItemWriter` có thể được gọi lại sau rollback để thử cô lập item lỗi. Recovery ở tầng writer không được tự coi một request đã xử lý nếu không có xác nhận. Tác dụng phụ ngoài transaction, ví dụ API/S3/Kafka, cần được thiết kế idempotent; không giả định một lần `write(...)` tương đương một lần commit bền vững.

## 9. Retry exhausted dưới góc nhìn StepExecution và JobRepository

`JobRepository` theo dõi `JobInstance`, `JobExecution`, `StepExecution`, status, counters và checkpoint. Với một worker fault-tolerant:

~~~text
Worker StepExecution: ordersWorker:range-0003
  readCount          = ...
  writeCount         = ...
  processSkipCount   = ...
  rollbackCount      = ...
  status             = FAILED / COMPLETED / STOPPED ...
  ExecutionContext   = checkpoint + input range
~~~

**Không có một counter mặc định duy nhất luôn biểu diễn “số item đã chạy recovery callback thành công”** cho mọi kiểu recovery ứng dụng. Nếu dùng `RetryTemplate` trong processor, hãy tạo metric riêng:

| Metric | Ý nghĩa |
| --- | --- |
| `partner_retry_attempts_total` | Số attempts gọi dịch vụ; cân nhắc không gắn business ID làm metric label |
| `partner_retry_exhausted_total` | Số lần một lời gọi đến trạng thái không tiếp tục retry |
| `enrichment_deferred_total` | Số quyết định DEFERRED được ghi nhận; cần phân biệt attempt và item unique |
| `enrichment_deferred_pending` | Số bản ghi chờ còn tồn tại trong durable store |
| `enrichment_recovered_total` | Số bản DEFERRED đã được xử lý thành READY |
| `batch_step_rollback_count` | Chỉ báo rollback tại Batch worker, không đồng nhất số retries |

Tách **số attempts** với **số business item duy nhất**. Một item bị retry ba lần trong lần chạy đầu và lại chạy ở lần restart có thể làm metric attempts tăng nhiều hơn số item thực.

### Restart khi retry đã hết

Giả sử partition A `COMPLETED`, partition B `FAILED` do hết retry, partition C `COMPLETED`:

~~~mermaid
sequenceDiagram
    participant O as Operator
    participant J as JobRepository
    participant S as StepExecutionSplitter
    participant W as Worker B
    O->>J: Restart cùng JobInstance
    S->>J: Đối chiếu status và context các partition
    J-->>S: A,C COMPLETED; B FAILED
    S-->>W: Chạy lại partition B nếu được chọn
    W->>W: Đọc checkpoint / thực thi lại
    W->>J: Ghi counters, context, status mới
~~~

Trong restart, có thể có `JobExecution` và `StepExecutionId` mới, nhưng **partition key → input** phải giữ ổn định. `RetryContext` trong RAM của lần gọi `RetryTemplate` không phải bản lưu attempts bền vững xuyên process crash. Nếu cần giới hạn **tổng số lần giao dịch ngoài** qua tất cả restart, phải lưu budget ở một ledger bền vững, không chỉ dựa vào `retryLimit` từng lần thực thi.

## 10. Partitioning: một lỗi remote có thể khuếch đại thế nào?

Trong local/remote partitioning, nhiều worker cùng gặp một dịch vụ đang lỗi:

~~~text
8 worker đồng thời
  × 3 attempts mỗi item
  × 200 item đang cần enrichment
  = tối đa 4.800 lời gọi theo ví dụ giả định
    nếu tất cả đều thử đủ số lượt trong cửa sổ quan sát
~~~

Đây là **phép minh họa sức ép**, không phải công thức dự báo throughput. Nếu có **retry cả ở step** ngoài `RetryTemplate` của processor, số lời gọi còn có thể tăng thêm; rollback làm xử lý lại chunk cũng có thể gây lặp. Điều phối chỉ dựa vào `gridSize` không đảm bảo giới hạn tốc độ đến API ngoài.

### Guardrails nên có

- **Timeout rõ ràng:** Client HTTP/database phải có connect/read timeout. Không để một attempt treo vô hạn.
- **Backoff có giới hạn:** Tránh retry dồn dập. Với nhiều worker, cân nhắc jitter để tránh cùng thức dậy tại một thời điểm.
- **Circuit breaker hoặc quota:** Khi downstream thực sự không sẵn sàng, giảm requests mới và chuyển sang trạng thái defer/fail có kiểm soát.
- **Concurrency bound:** Giới hạn số worker gọi cùng dịch vụ; thread pool, semaphore hoặc rate limiter có scope phù hợp với hạ tầng.
- **Retry budget xuyên nhiều pod:** Nếu là quota nghiệp vụ hoặc downstream quota nghiêm ngặt, cần giải pháp phân tán; `AtomicInteger` trong một JVM không đủ.
- **Metric phân tầng:** Có metric attempts, exhausted, deferred, failure, queue depth và latency; phân biệt item unique với retries.

### Local so với remote

| Rủi ro | Local partitioning | Remote partitioning |
| --- | --- | --- |
| Nhiều worker gọi API đồng thời | Các thread cùng JVM; có thể dùng limiter chung trong process | Nhiều JVM/pod; limiter process-local không đại diện toàn cụm |
| Recovery state rò giữa partitions | Singleton mutable field hoặc `ThreadLocal` | Tương tự trong từng worker JVM; thêm shared external state |
| Lặp yêu cầu khi fail | Chunk rollback/restart | Thêm broker redelivery và worker cũ có thể chưa dừng |
| Dedupe | Unique key ở database/đích | Cùng yêu cầu, cần hiệu lực xuyên JVM |
| Observability | Thread, StepExecution, DB pool | Bổ sung message ID, consumer, broker lag/ack |

`@StepScope` giúp mỗi worker `StepExecution` có bean có state riêng, nhưng **không** biến một reader stateful trong multi-threaded chunk thành thread-safe và không cung cấp distributed lock cho recovery của các worker từ xa.

## 11. Một thiết kế DEFERRED thực tế cần những bảng/trạng thái nào?

Nếu nghiệp vụ chấp nhận xử lý enrichment sau, có thể dùng một bảng kết quả và một bảng công việc chờ (hoặc một bảng có đủ cột), ví dụ:

~~~sql
-- Schema minh họa, cú pháp upsert/locking tùy hệ quản trị CSDL.
CREATE TABLE enrichment_results (
    source_version VARCHAR(120) NOT NULL,
    source_id      VARCHAR(160) NOT NULL,
    state          VARCHAR(20) NOT NULL,
    segment        VARCHAR(120),
    updated_at     TIMESTAMP NOT NULL,
    PRIMARY KEY (source_version, source_id)
);

CREATE TABLE enrichment_recovery_queue (
    source_version VARCHAR(120) NOT NULL,
    source_id      VARCHAR(160) NOT NULL,
    state          VARCHAR(24) NOT NULL,
    attempt_count  INTEGER NOT NULL,
    next_retry_at  TIMESTAMP,
    last_reason    VARCHAR(100),
    PRIMARY KEY (source_version, source_id)
);
~~~

Một flow có kiểm soát:

1. Writer lưu `DEFERRED` và bản ghi công việc chờ theo `sourceVersion + sourceId` trong transaction phù hợp.
2. Recovery worker đọc bản ghi chờ đến hạn, **claim** atomically để tránh hai worker cùng xử lý.
3. Recovery worker gọi partner API với timeout, retry và backoff riêng.
4. Nếu thành công, cập nhật kết quả sang `READY` và đánh dấu queue `DONE` trong transaction thích hợp.
5. Nếu vẫn lỗi, tăng attempt count bền vững, đặt `next_retry_at` hoặc đưa vào dead-letter/manual review sau ngưỡng.
6. Dashboard đối soát `DEFERRED` chưa hoàn thành trước khi publish sang downstream yêu cầu đầy đủ dữ liệu.

Một API đọc theo identity không tự tạo hiệu ứng trùng, nhưng cập nhật `READY` và phát message có thể bị lặp nếu worker chết giữa commit và acknowledgement. Cần unique key, luật chuyển trạng thái và outbox/inbox nếu phát message ra hệ thống khác.

**Tránh hai nguồn chân lý mâu thuẫn:** Khi vừa có `enrichment_results` vừa có `enrichment_recovery_queue`, ghi trạng thái phải được phối hợp bằng transaction hoặc thiết kế eventual consistency có reconciliation. Nếu writer chỉ tạo `DEFERRED` nhưng không enqueue, item có thể bị bỏ quên.

## 12. RecoveryCallback phải xử lý ngoại lệ của chính recovery

Đường recovery cũng có thể thất bại: database quarantine hết dung lượng, transaction rollback, serialized payload lỗi hoặc permission của queue không hợp lệ.

Nếu việc ghi công việc chờ là **bắt buộc**, không được nuốt lỗi rồi trả fallback `READY`. Có thể để exception của writer/recovery làm step `FAILED` để người vận hành sửa hạ tầng. Cần bảo đảm không tạo “orphan” — business output nói deferred nhưng durable queue không có item.

### Các trường hợp nhất định không được xem là recovery thành công

| Trường hợp | Cách xử lý |
| --- | --- |
| Recovery callback trả null khi processor không có chính sách filter | Coi là lỗi thiết kế, không âm thầm bỏ item |
| Không thể lưu durable DEFERRED | Fail step hoặc giữ một cơ chế ghi bền vững tương đương |
| Không biết thanh toán đã thành công hay chưa | Reconcile, không tự gửi lệnh mới không idempotent |
| Source version không xác định | Không replay theo file/offset bất ổn định |
| Writer dùng side effect ngoài transaction | Idempotency + outbox/reconciliation |
| Quota retry nghiệp vụ xuyên JobInstance đã hết | Escalate/manual review, không reset khi restart |

### Lựa chọn khung exception chuẩn

Không coi mọi `Exception` là retryable. Nên tạo exception phân tầng:

~~~java
public class PartnerTemporaryException extends RuntimeException {
    public PartnerTemporaryException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class PartnerPermanentException extends RuntimeException {
    public PartnerPermanentException(String message) {
        super(message);
    }
}
~~~

Chỉ `PartnerTemporaryException` thuộc retry policy trong ví dụ. `PartnerPermanentException` phải được phân loại rõ: fail step, skip theo một policy khác nếu dữ liệu riêng lẻ thực sự không hợp lệ, hoặc xử lý thủ công. Không trả `DEFERRED` vô hạn cho lỗi permanent do lỗi dữ liệu hoặc yêu cầu xác thực sai.

## 13. Kiểm thử retry exhausted và recoverer

### 13.1. Unit test: hết ba attempts rồi nhận DEFERRED

Giả sử service chỉ đọc luôn ném `PartnerTemporaryException`. Có thể kiểm thử `RetryTemplate` riêng không cần chạy toàn bộ batch job:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.retry.support.RetryTemplate;

class PartnerRecoveryTest {

    @Test
    void hetRetryTraVeDeferredKhongTraVeThanhCongGia() {
        RetryTemplate template = new RetryTemplate();
        template.setRetryPolicy(new SimpleRetryPolicy(3));

        AtomicInteger attempts = new AtomicInteger();
        InputOrder input = new InputOrder("ORDER-01", "C-01");

        EnrichmentDecision decision = template.execute(
                context -> {
                    attempts.incrementAndGet();
                    throw new PartnerTemporaryException(
                            "Partner timeout", null);
                },
                context -> {
                    assertInstanceOf(
                            PartnerTemporaryException.class,
                            context.getLastThrowable());
                    return EnrichmentDecision.deferred(input);
                });

        assertEquals(3, attempts.get());
        assertEquals(EnrichmentState.DEFERRED, decision.state());
        assertEquals("ORDER-01", decision.sourceId());
    }
}
~~~

`SimpleRetryPolicy(3)` ở test là chính sách đơn giản cho **ba attempts tối đa**. `assertInstanceOf` có ở JUnit 5 các phiên bản phù hợp; có thể thay bằng `assertTrue(... instanceof ...)` khi cần. Test không chứng minh bản ghi DEFERRED đã bền vững — phần đó thuộc **writer integration test**.

### 13.2. Test trường hợp thành công ở lượt thứ hai

~~~text
Attempt #1: PartnerTemporaryException
Attempt #2: trả "GOLD"
Kỳ vọng:
  - Kết quả READY, segment = GOLD
  - RecoveryCallback không chạy
  - Số calls là 2
  - Không ghi bản DEFERRED
~~~

Test này giúp phát hiện việc recoverer bị gọi quá sớm hoặc code tự bỏ item ngay khi gặp lỗi đầu tiên.

### 13.3. Ma trận kiểm thử bắt buộc

| Kịch bản | Điều cần chứng minh |
| --- | --- |
| Thành công ngay lần đầu | Không gọi recovery, không phát sinh retry |
| Timeout rồi thành công trong ngân sách | Đủ attempts, không defer/skip |
| Lỗi tạm thời vượt max attempts | Recovery diễn ra đúng policy; trạng thái DEFERRED nếu được duyệt |
| Lỗi không retryable | Không lặp vô ích, không bị “biến” thành fallback thành công |
| Recovery callback tự thất bại | Step/transaction xử lý lỗi, không mất công việc |
| Writer rollback sau khi processor trả DEFERRED | Lần xử lý lại không nhân đôi queue/output |
| Processor trả null ngoài chủ đích | Test phát hiện filter âm thầm |
| Kết hợp retry ở template và ở Batch step | Đo **tổng số lời gọi thực** để tránh nhân bội requests |
| Nhiều partition gọi cùng partner | Không quá tải downstream; metric và limiter hoạt động |
| Job restart khi worker `FAILED` | Partition key/input/checkpoint giữ nguyên; không giả định budget xuyên lượt |
| Remote broker redelivery | Duplicate requests không tạo double side effect |
| DEFERRED được replay | Chuyển trạng thái sang READY đúng một lần theo business key |
| API trả timeout sau khi đã commit | Reconcile bằng idempotency key; không phát thêm lệnh không an toàn |
| Partner outage kéo dài | Rate limit, circuit breaker, queue backlog và cảnh báo không bị vô hạn |

### 13.4. Integration test cần assert dữ liệu, không chỉ BatchStatus

Một `JobExecution` có thể `COMPLETED` với nhiều item `DEFERRED` vì đó là kết quả dự kiến theo hợp đồng. Test phải kiểm tra:

- `READY`: những item thành công có dữ liệu enrichment hợp lệ.
- `DEFERRED`: những item chưa xử lý được có **record bền vững và source key** tương ứng.
- `FAILED`/`SKIPPED`: phân biệt trạng thái lỗi framework với trạng thái nghiệp vụ.
- Không có item input “biến mất” nếu hợp đồng yêu cầu mỗi input có một outcome.
- Khi replay thành công, số `DEFERRED_PENDING` giảm và `READY` tăng đúng.
- Writer/queue dùng unique key và transaction đủ để chịu rollback/restart.

Không lấy `writeCount` của StepExecution làm số hàng mới của database nếu writer có upsert/no-op. Không lấy attempts làm số item lỗi duy nhất.

## 14. Runbook khi retry exhausted tăng đột biến

1. **Xác định phạm vi:** JobInstance, JobExecution, StepExecution, tên partition, input snapshot và thời điểm lỗi.
2. **Phân loại exception:** Lỗi transient thật hay permanent? Có thay đổi schema, credentials, rate limit hoặc policy gần đây không?
3. **Kiểm tra downstream:** Latency, error rate, throttling, quota, timeout và số kết nối.
4. **Đếm attempts thực tế:** Có retry lồng nhau giữa Spring Batch, `RetryTemplate`, HTTP client, message broker hoặc service mesh không?
5. **Kiểm tra dữ liệu pending:** Số item DEFERRED, độ tuổi lâu nhất, số lần replay, dead-letter và item bị thất lạc khỏi queue.
6. **Đảm bảo an toàn giao dịch:** Các trạng thái DEFERRED/READY và audit/queue đã commit nhất quán chưa?
7. **Kiểm tra concurrency:** Worker slots, executor queue, remote consumer, database pool, limiter và circuit breaker.
8. **Chọn biện pháp khôi phục:** Fail/restart sau khi sửa hạ tầng, xử lý bù DEFERRED, hoặc replay quarantine nếu cần.
9. **Đối soát nghiệp vụ:** Tập business keys nguồn bằng hợp của các trạng thái được chấp nhận theo contract, không có duplicate side effect.
10. **Điều chỉnh policy dựa trên số đo:** Đặt max attempts, timeout, backoff, rate limit và alert threshold phù hợp SLO; không tăng retry vô hạn để che lỗi.

### Gợi ý dashboard

| Nhóm | Chỉ số |
| --- | --- |
| Framework Batch | `BatchStatus`, read/write/skip/rollback count theo worker |
| Retry | attempts, exhausted, retryable/nonretryable counts và latency |
| Recovery | DEFERRED unique, pending backlog, aging, recovery success/failure |
| Hạ tầng | CPU, heap, DB pool, HTTP connection pool, broker lag và request timeout |
| Dữ liệu | Business key unique, missing, duplicate/no-op, reconciliation failures |
| Vận hành | Số lần restart, thời gian phục hồi, số item cần manual review |

Khi xuất metric, không đưa từng `sourceId` vào label dài hạn vì cardinality sẽ rất lớn. Đưa định danh item vào audit store/log có kiểm soát, còn metric tổng hợp theo loại lỗi, job, môi trường và nhóm partition.

## 15. Bài tập tình huống

Job làm giàu 4 triệu khách hàng chia thành **8 partition**. Mỗi worker có `TaskExecutor` riêng và processor dùng `RetryTemplate` tối đa 3 attempts. Khi dịch vụ enrichment timeout, một recoverer trả `null` để job tiếp tục. Người vận hành quan sát:

- `BatchStatus=COMPLETED` cho nhiều worker;
- `filterCount` tăng mạnh nhưng `processSkipCount=0`;
- không có bản ghi trong bảng quarantine;
- một số lần retry từ HTTP client xảy ra **bên trong** ba attempts của `RetryTemplate`;
- restart job không tạo lại được những item đã bị filter ở worker `COMPLETED`.

**Câu hỏi:**

1. Vì sao `filterCount` tăng còn `processSkipCount` không tăng?
2. Đã thực sự có một recovery đáng tin cậy chưa?
3. Có thể giới hạn số HTTP attempts chỉ bằng `retryLimit(3)` của step không?
4. Nếu dùng `DEFERRED`, những thành phần nào phải lưu bền vững để replay?
5. Cần kiểm thử gì khi hai worker cùng xử lý một business key do dữ liệu partition overlap?

**Định hướng trả lời:** Trả `null` từ processor là **filter**, không phải skip; vì vậy không có `SkipListener` và dữ liệu đã bị loại khỏi luồng bình thường. Recoverer đáng tin cậy nên fail/skip có audit hoặc trả **DEFERRED có writer lưu bền vững**, không âm thầm xóa item. Retry lồng giữa các tầng có thể nhân số HTTP calls, cần đếm attempts thực tế và đặt timeout/backoff/quota nhất quán. DEFERRED cần source key, input version, trạng thái, next retry, reason và writer/queue idempotent; test phải phát hiện overlap, duplicate và race khi cập nhật kết quả.

## Tài liệu tham khảo

- [Spring Batch Reference — Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retry trong fault-tolerant chunk step.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): quyết định skip và `skipLimit`.
- [Spring Retry API — RetryTemplate](https://docs.spring.io/spring-retry/docs/current/apidocs/org/springframework/retry/support/RetryTemplate.html): thực thi retry callback và recovery callback.
- [Spring Retry API — RecoveryCallback](https://docs.spring.io/spring-retry/docs/current/apidocs/org/springframework/retry/RecoveryCallback.html): hợp đồng recovery khi retry không thể tiếp tục.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): checkpoint và restart.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): partitioning, concurrency và remote processing.
- [Spring Batch API — SkipListener](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/SkipListener.html): quan sát item được skip thật sự.

> **Ghi nhớ:** Sau khi retry hết lượt, **recovery phải là một quyết định nghiệp vụ có thể kiểm chứng**, không chỉ là bắt exception rồi trả `null` hoặc “thành công”. Trong Spring Batch, retry exhausted có thể dẫn đến **skip hoặc fail** theo policy; muốn dùng `RecoveryCallback` cần gọi `RetryTemplate` của Spring Retry một cách tường minh. Nếu chấp nhận defer/fallback, phải lưu trạng thái bền vững, đối soát và bảo đảm idempotency khi worker rollback, restart hoặc chạy phân tán.
