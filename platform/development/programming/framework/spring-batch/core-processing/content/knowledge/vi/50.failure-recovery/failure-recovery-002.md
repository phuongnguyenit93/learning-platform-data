# Failure ở processor trong Spring Batch: phát hiện, xử lý và khôi phục

## 1. Failure ở processor là gì?

Trong một **chunk-oriented step** của Spring Batch, `ItemProcessor<I, O>` nhận một item từ `ItemReader`, thực hiện kiểm tra hoặc biến đổi, rồi trả về item đầu ra cho `ItemWriter`. Lỗi ở processor xảy ra khi phương thức `process(...)` **ném exception** trong quá trình này.

Các nguyên nhân thường gặp:

- **Dữ liệu đầu vào không hợp lệ:** thiếu mã đơn hàng, số tiền âm, định dạng ngày sai, không tìm thấy mã nghiệp vụ bắt buộc.
- **Lỗi phụ thuộc tạm thời:** service tra cứu bị timeout, kết nối mất trong chốc lát, dịch vụ trả 503, cache/backend chưa sẵn sàng.
- **Lỗi logic chương trình:** `NullPointerException` ngoài dự kiến, phép tính sai, mapping nhầm trường, giả định không đúng về dữ liệu.
- **Lỗi trạng thái và concurrency:** processor giữ biến mutable không đúng scope, dữ liệu dùng chung giữa nhiều thread, hoặc kết quả phụ thuộc vào thứ tự item.
- **Lỗi tài nguyên:** hết bộ nhớ, pool kết nối cạn kiệt, cấu hình timeout/retry không phù hợp.

Ví dụ một processor dùng để kiểm tra đơn hàng:

```java
public ValidatedOrder process(OrderInput item) {
    if (item.amount().signum() <= 0) {
        throw new InvalidOrderRowException("amount must be positive");
    }
    return new ValidatedOrder(item.id(), item.amount());
}
```

Với bản ghi có `amount=-10`, processor ném exception. Spring Batch sẽ quyết định **làm step thất bại, retry hay skip** tùy cấu hình của step và loại exception.

Một điểm cần phân biệt ngay từ đầu:

| Kết quả `process(...)` | Spring Batch hiểu thế nào? | Điều gì xảy ra với item? |
| --- | --- | --- |
| Trả về một object `O` | Xử lý thành công | Item đầu ra được đưa tới writer |
| Trả về `null` | **Filter có chủ đích** | Item không được đưa tới writer; tăng `filterCount` |
| Ném exception không được phép xử lý tiếp | **Failure** | Step có thể chuyển `FAILED` và transaction/chunk chịu tác động |
| Ném exception thuộc retry policy | **Retry** | Framework thử lại theo chính sách và giới hạn |
| Ném exception thuộc skip policy | **Skip** | Item bị bỏ qua theo giới hạn và bước xử lý vẫn có thể tiếp tục |

**`null` không phải failure và không phải skip.** Nếu mọi exception bị bắt rồi trả `null`, dashboard có thể cho thấy job `COMPLETED` trong khi dữ liệu lỗi đã biến mất âm thầm. Chỉ dùng filter cho các item mà quy tắc nghiệp vụ cho phép loại bỏ.

## 2. Failure xảy ra ở đâu trong vòng đời chunk?

Một chunk step thường có luồng:

```text
               Chunk transaction
                       |
      +----------------+----------------+
      |                                 |
      v                                 |
 ItemReader<I>                          |
      |                                 |
      v                                 |
 ItemProcessor<I,O>                     |
      |                                 |
      +---- return O ----------------+  |
      |                              |  |
      +---- return null -> FILTER    |  |
      |                              |  |
      +---- throw exception          |  |
                   |                 |  |
                   v                 |  |
             Fault-tolerance        |  |
             configuration          |  |
             /      |       \        |  |
           retry   skip     fail     |  |
                    |                |  |
                    +-- tiếp tục ----+  |
                                     v  |
                                ItemWriter<O>
                                     |
                                 COMMIT hoặc
                                 ROLLBACK
```

Ví dụ `chunk(3)`, đầu vào:

```text
ORD-001 hợp lệ
ORD-002 hợp lệ
ORD-003 lỗi validation trong processor
ORD-004 hợp lệ
ORD-005 hợp lệ
```

Nếu step **không có fault tolerance**, lỗi ở `ORD-003` thường làm chunk hiện tại không thể hoàn tất và step kết thúc `FAILED`. Những chunk đã commit từ trước có thể vẫn giữ dữ liệu của chúng. Nếu step được cấu hình `skip(InvalidOrderRowException.class)` và còn hạn mức skip, framework có thể bỏ qua `ORD-003`, xử lý tiếp các item còn lại và hoàn tất step.

Chi tiết rollback, việc reader/processor được gọi lại và số lần thử phụ thuộc loại exception, policy retry/skip, loại reader, transaction manager và cấu hình Spring Batch. Không nên khẳng định “processor được gọi đúng một lần cho mỗi dòng” khi bật retry hoặc chunk có rollback.

### Transaction của chunk không đồng nghĩa transaction của mọi side effect

Với reader/writer JDBC trong cùng transaction, một rollback có thể hoàn tác các thay đổi database chưa commit của chunk. Nhưng nếu processor gọi HTTP API, gửi message hoặc ghi file ngoài transaction, hiệu ứng đó có thể **không rollback** khi chunk thất bại.

Ví dụ:

```text
processor gọi API trừ tiền -> API thành công
writer ghi database       -> lỗi timeout
Spring Batch rollback chunk
processor được gọi lại    -> API có nguy cơ trừ tiền lần nữa
```

Vì vậy, processor nên ưu tiên **biến đổi/kiểm tra dữ liệu không có side effect**. Nếu phải gọi hệ thống ngoài, cần thiết kế idempotency key, retry có giới hạn, timeout rõ ràng và cơ chế ghi nhận kết quả phù hợp. Không dựa vào rollback JDBC để bảo vệ một API từ xa.

## 3. Phân loại lỗi trước khi quyết định recovery

Khôi phục lỗi hiệu quả bắt đầu bằng việc phân loại theo **khả năng phục hồi** và **mức độ hợp lệ của dữ liệu**.

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp |
| --- | --- | --- |
| Validation vĩnh viễn của một item | Amount âm, thiếu trường bắt buộc, mã không hợp lệ | Skip có kiểm soát hoặc fail/quarantine theo yêu cầu nghiệp vụ |
| Lỗi phụ thuộc tạm thời | HTTP 503, network timeout, tài nguyên tạm chưa sẵn sàng | Retry với giới hạn và backoff |
| Lỗi cấu hình/toàn hệ thống | Thiếu bean, sai schema, credentials sai | Fail nhanh, cảnh báo và sửa cấu hình |
| Lỗi logic không mong đợi | `NullPointerException` do bug, sai invariant | Fail và điều tra; không cấu hình skip rộng |
| Xung đột dữ liệu nghiệp vụ | Cùng mã giao dịch nhưng nội dung khác nhau | Fail hoặc lưu conflict/quarantine, không tự động bỏ qua |
| Item hợp lệ nhưng nằm ngoài phạm vi xử lý | Đơn hàng chưa đến hạn, loại giao dịch bị loại theo chính sách | Trả `null` để filter |

Đừng dùng một rule như `retry(Exception.class)` hoặc `skip(Exception.class)` cho mọi tình huống. Nó có thể lặp vô ích với dữ liệu chắc chắn sai, che giấu bug và làm mất dữ liệu nghiệp vụ.

Một cách thiết kế là tạo **exception có ý nghĩa ở tầng nghiệp vụ**:

```java
public final class InvalidOrderRowException extends RuntimeException {
    public InvalidOrderRowException(String message) {
        super(message);
    }
}

public final class CatalogTemporarilyUnavailableException
        extends RuntimeException {
    public CatalogTemporarilyUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Các lớp exception trên là ví dụ của ứng dụng, không phải exception có sẵn của Spring Batch. Adapter gọi hệ thống ngoài nên chuyển các lỗi thực sự tạm thời thành `CatalogTemporarilyUnavailableException`, nhưng vẫn để các lỗi xác thực, request sai hoặc mapping bug nổi lên dưới kiểu lỗi phù hợp.

## 4. Ví dụ processor phục vụ bài toán kiểm tra đơn hàng

Giả sử job đọc dữ liệu:

```csv
order_id,customer_code,amount
ORD-001,C001,100.00
ORD-002,C002,-20.00
ORD-003,C003,75.50
ORD-004,C004,180.00
```

Quy tắc:

1. `order_id` không được rỗng.
2. `amount` phải lớn hơn 0.
3. `customer_code` phải tham chiếu một khách hàng hợp lệ.
4. Nếu dịch vụ catalog tạm thời lỗi, có thể thử lại.
5. Dòng validation không hợp lệ được skip **chỉ khi policy nhập dữ liệu cho phép**, đồng thời phải có thông tin đối soát.

Model:

```java
import java.math.BigDecimal;

public record OrderInput(
        String orderId,
        String customerCode,
        BigDecimal amount
) {}

public record ValidatedOrder(
        String orderId,
        String customerId,
        BigDecimal amount
) {}

public record CustomerRef(String customerId) {}

public interface CustomerCatalog {
    CustomerRef findCustomer(String customerCode);
}
```

Processor:

```java
import java.math.BigDecimal;
import java.util.Objects;
import org.springframework.batch.item.ItemProcessor;

public final class ValidatingOrderProcessor
        implements ItemProcessor<OrderInput, ValidatedOrder> {

    private final CustomerCatalog customerCatalog;

    public ValidatingOrderProcessor(CustomerCatalog customerCatalog) {
        this.customerCatalog = Objects.requireNonNull(customerCatalog);
    }

    @Override
    public ValidatedOrder process(OrderInput item) {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new InvalidOrderRowException(
                    "order_id is required");
        }

        if (item.customerCode() == null
                || item.customerCode().isBlank()) {
            throw new InvalidOrderRowException(
                    "customer_code is required for " + item.orderId());
        }

        if (item.amount() == null
                || item.amount().compareTo(BigDecimal.ZERO) <= 0) {
            throw new InvalidOrderRowException(
                    "amount must be positive for " + item.orderId());
        }

        // Adapter có thể ném CatalogTemporarilyUnavailableException.
        CustomerRef customer =
                customerCatalog.findCustomer(item.customerCode());

        if (customer == null) {
            throw new InvalidOrderRowException(
                    "unknown customer for " + item.orderId());
        }

        return new ValidatedOrder(
                item.orderId(),
                customer.customerId(),
                item.amount()
        );
    }
}
```

Processor giữ phép biến đổi tương đối đơn giản: input không hợp lệ phát sinh lỗi có thể phân loại; phụ thuộc tạm thời phát sinh exception retryable; kết quả hợp lệ chuyển sang writer. Nếu `CustomerCatalog` thực hiện HTTP request, thao tác tra cứu nên là read-only và có timeout. Tránh gọi API tạo đơn, thanh toán hoặc gửi email bên trong processor vì logic có thể được thực thi lại.

## 5. Cấu hình Spring Batch: fail, retry và skip

Ví dụ dùng **Spring Batch 5.x, Java 17+**, với `JobRepository` và `PlatformTransactionManager` đã được cấu hình. Reader và writer được cung cấp bởi ứng dụng.

### 5.1. Hành vi mặc định: exception làm step thất bại

Không bật fault tolerance:

```java
@Bean
Step validateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, ValidatedOrder> orderProcessor,
        ItemWriter<ValidatedOrder> orderWriter) {

    return new StepBuilder("validateOrdersStep", jobRepository)
            .<OrderInput, ValidatedOrder>chunk(50, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Nếu `process(...)` ném `InvalidOrderRowException` không được xử lý, step thường kết thúc `FAILED`. Mục tiêu của phương án này là **fail fast**: một dòng sai khiến toàn job tạm dừng để người vận hành xử lý, phù hợp khi dữ liệu phải chính xác tuyệt đối.

Không phải mọi hệ thống đều nên skip: nếu job quyết toán không cho phép thiếu giao dịch, việc skip một dòng có thể gây sai lệch số tiền nghiêm trọng dù job báo thành công.

### 5.2. Bật retry cho lỗi tạm thời, skip cho lỗi dữ liệu

```java
@Bean
Step validateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, ValidatedOrder> orderProcessor,
        ItemWriter<ValidatedOrder> orderWriter,
        OrderSkipAuditListener skipAuditListener) {

    return new StepBuilder("validateOrdersStep", jobRepository)
            .<OrderInput, ValidatedOrder>chunk(50, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .retry(CatalogTemporarilyUnavailableException.class)
            .retryLimit(3)
            .skip(InvalidOrderRowException.class)
            .skipLimit(10)
            .listener(skipAuditListener)
            .build();
}
```

Cơ chế:

- `retry(CatalogTemporarilyUnavailableException.class)`: chỉ thử lại lỗi phụ thuộc được phân loại là tạm thời.
- `retryLimit(3)`: giới hạn số attempt theo semantics của Spring Batch/Retry; không hiểu nhầm là luôn có đúng ba lần thử **thêm** sau lần đầu.
- `skip(InvalidOrderRowException.class)`: cho phép bỏ qua item lỗi validation.
- `skipLimit(10)`: đặt ngưỡng tổng số skip của step theo policy, bao gồm lỗi có thể phát sinh từ reader/processor/writer. Khi vượt giới hạn, step thất bại.
- Exception không được cấu hình retry/skip sẽ tiếp tục phát sinh failure theo cơ chế mặc định.

Trong code thực tế, nếu một exception vừa được đưa vào retry vừa được đưa vào skip, hành vi sau khi retry cạn có thể chuyển sang skip tùy cấu hình. Cần quyết định rõ **retry exhausted thì fail hay được phép bỏ qua** theo nghiệp vụ.

Các import chính trong Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;
```

Các class cùng tên trong Spring Batch 6 có thể chuyển package hoặc thay đổi API. Cần đối chiếu tài liệu của phiên bản đang dùng trước khi sao chép import.

### 5.3. Backoff cho retry

Retry liên tục không có khoảng nghỉ có thể làm phụ thuộc đang quá tải càng trở nên tệ hơn. Với Spring Batch 5.x có thể cung cấp `BackOffPolicy` từ Spring Retry:

```java
import org.springframework.retry.backoff.FixedBackOffPolicy;

FixedBackOffPolicy backOff = new FixedBackOffPolicy();
backOff.setBackOffPeriod(250L); // 250 ms

// Trong FaultTolerantStepBuilder:
.retry(CatalogTemporarilyUnavailableException.class)
.retryLimit(3)
.backOffPolicy(backOff)
```

Đây là ví dụ về cú pháp trong chuỗi builder, không phải một Java statement độc lập. Trong production, chọn fixed/exponential backoff theo SLA và khả năng hồi phục của dịch vụ. Với test logic, có thể dùng khoảng nghỉ ngắn hoặc policy test để không làm test suite chậm.

**Giới hạn retry cần xét trên thời gian thực thi:** nhiều item cùng gặp lỗi có thể tạo hàng nghìn request retry. Ngoài retry limit, nên có timeout ở HTTP client/database, circuit breaker hoặc giới hạn tải nếu phù hợp với kiến trúc.

## 6. Retry, skip và rollback tương tác như thế nào?

Đây là phần dễ nhầm nhất của failure recovery.

### 6.1. Lỗi processor có thể khiến chunk được thử lại

Ví dụ chunk có ba item:

```text
Input: [A, B, C]
Processor:
  A -> OK
  B -> lỗi tạm thời
  C -> chưa được xử lý
```

Nếu `B` thuộc retry policy, Spring Batch có thể thử lại lỗi theo cơ chế chunk/fault tolerance. Khi có rollback, một số item đã được đọc hoặc xử lý trước đó có thể được xử lý lại. Điều này phụ thuộc khả năng buffering của reader và cấu hình transaction.

**Không thiết kế processor dựa trên giả định mỗi item được gọi chính xác một lần.** Nếu processor tăng biến đếm global, gửi notification hoặc gọi API ghi dữ liệu, một lần retry/rollback có thể tạo side effect trùng.

### 6.2. Skip không nhất thiết đồng nghĩa mọi lần gọi đều rollback

Đối với exception đã được cấu hình skippable tại processor, Spring Batch có thể bỏ qua item và hoàn tất chunk theo thuật toán fault-tolerant step. Chi tiết rollback phụ thuộc loại lỗi, thời điểm lỗi, chính sách rollback và các thành phần reader/writer.

Vì vậy:

- Không tự suy từ `processSkipCount=1` rằng đã có đúng một transaction rollback.
- Không tự suy từ `rollbackCount=1` rằng có đúng một item bị lỗi.
- Không suy rằng mọi item trước exception đã được commit.
- Đọc trạng thái cuối và dữ liệu đã commit để xác minh hành vi.

### 6.3. Bộ đếm cần quan sát

`StepExecution` cung cấp các bộ đếm quan trọng:

| Bộ đếm/trạng thái | Ý nghĩa chính |
| --- | --- |
| `readCount` | Số item reader đọc thành công theo metadata của step |
| `writeCount` | Số item framework ghi qua writer theo semantics của step |
| `filterCount` | Số item processor chủ động trả `null` |
| `readSkipCount` | Số item bị skip ở reader |
| `processSkipCount` | Số item bị skip do processor |
| `writeSkipCount` | Số item bị skip ở writer |
| `skipCount` | Tổng skip (đọc + xử lý + ghi) |
| `rollbackCount` | Số lần rollback được ghi nhận |
| `commitCount` | Số lần commit của step theo metadata |
| `status` | `COMPLETED`, `FAILED`, `STOPPED`, ... |
| `exitStatus` | Kết quả/exit code, có thể được tùy chỉnh |

Các bộ đếm phản ánh **trạng thái được Spring Batch ghi nhận**, không nhất thiết khớp trực tiếp với số SQL row thực sự được thêm mới nếu writer có upsert/deduplicate hoặc hiệu ứng ngoài transaction. Khi có retry/rollback, số lần method được gọi cũng có thể lớn hơn bộ đếm cuối cùng.

### 6.4. Không dùng `noRollback(...)` một cách tùy tiện

Fault-tolerant step có cơ chế cấu hình exceptions không gây rollback. Tuy nhiên, chỉ bật khi hiểu rõ vị trí lỗi và tính nhất quán của transaction. Không nên thêm:

```java
.noRollback(Exception.class)
```

chỉ để giảm `rollbackCount`. Điều này có thể khiến trạng thái commit không phù hợp với mong đợi và che giấu lỗi xử lý. Xác định chính xác exception, transaction boundary và chiến lược dữ liệu trước khi tùy chỉnh rollback policy.

## 7. Xây SkipListener để ghi nhận dữ liệu lỗi

Nếu chính sách cho phép skip, **việc bỏ qua dữ liệu cần quan sát và đối soát được**. Không chỉ ghi số skip: cần biết nguồn, mã bản ghi, nguyên nhân và cách sửa hoặc xử lý lại.

Spring Batch cung cấp `SkipListener<I,O>`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public final class OrderSkipAuditListener
        implements SkipListener<OrderInput, ValidatedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipAuditListener.class);

    @Override
    public void onSkipInProcess(OrderInput item, Throwable t) {
        log.warn(
                "Skipped invalid order in processor: orderId={}, type={}, reason={}",
                item.orderId(),
                t.getClass().getSimpleName(),
                t.getMessage()
        );
    }
}
```

Trong ví dụ này, cần đăng ký listener vào step qua `.listener(skipAuditListener)` như phần trước.

Lưu ý:

- `onSkipInProcess` dành cho item được **skip ở processor**, không phải mọi lần processor ném lỗi. Lỗi được retry rồi xử lý thành công không phải skip.
- Chỉ log thông tin nghiệp vụ được phép hiển thị; không ghi token, mật khẩu, toàn bộ payload chứa dữ liệu nhạy cảm.
- Với hệ thống cần tái xử lý, có thể ghi item lỗi vào bảng quarantine hoặc một luồng audit có transaction/idempotency được thiết kế riêng.
- Listener không biến giao dịch bên ngoài thành exactly-once. Nếu ghi audit vào hệ thống khác với database của chunk, cần xử lý khả năng lặp khi crash/retry.

**Phân biệt skip với filter:** khi processor trả `null`, `onSkipInProcess` không được gọi vì không có exception skippable. Nếu cần audit các item bị filter theo quy tắc nghiệp vụ, hãy dùng cơ chế riêng.

## 8. Khi nào step thất bại hoàn toàn?

Step có thể kết thúc `FAILED` nếu:

1. Processor ném một exception **không được retry/skip**.
2. Retry được cho phép nhưng cuối cùng vẫn thất bại và policy không cho skip.
3. Số skip vượt quá `skipLimit`.
4. Một lỗi nghiêm trọng phát sinh trong reader/writer/transaction manager/listener hoặc cơ chế hạ tầng.
5. Exception khiến quá trình xử lý không thể hoàn tất theo cấu hình hiện tại.

Ví dụ: step cho phép skip tối đa hai dòng validation nhưng file chứa ba dòng lỗi.

```text
ORD-001  OK
ORD-002  INVALID -> skip #1
ORD-003  OK
ORD-004  INVALID -> skip #2
ORD-005  INVALID -> vượt skip limit -> FAILED
```

Những chunk **đã commit** trước thời điểm failure có thể đã lưu output. Một step `FAILED` **không có nghĩa database luôn quay lại trạng thái hoàn toàn trống như trước job**. Đây là lý do restart, checkpoint và writer idempotent quan trọng.

Khi failure xảy ra, cần ghi nhận `jobExecutionId`, `stepExecutionId`, tên step, status, exception class và tham số nghiệp vụ phù hợp để có thể truy lại sự cố.

## 9. Recovery bằng restart sau lỗi ở processor

### 9.1. Restart khác với chạy job mới

Trong Spring Batch, `JobInstance` được nhận diện bởi tên job và identifying `JobParameters`. Một instance có thể có nhiều `JobExecution` nếu run trước thất bại rồi được restart.

```text
JobInstance: importOrdersJob, businessDate=2026-11-16
    |
    +-- JobExecution #301: FAILED
    |       |
    |       +-- StepExecution #700: FAILED at ORD-150
    |
    +-- JobExecution #302: COMPLETED (restart)
            |
            +-- StepExecution #701: COMPLETED
```

Nếu launch lần thứ hai với **identifying parameters mới**, đó là **một JobInstance khác**, không chứng minh logic restart đúng. Với restart, cần giữ đúng identity và metadata repository.

### 9.2. Vì sao checkpoint ảnh hưởng kết quả?

Chunk-oriented step lưu tiến độ đọc và trạng thái liên quan trong `ExecutionContext` (nếu reader/component được cấu hình lưu trạng thái thích hợp). Trong quá trình restart, Spring Batch có thể tiếp tục từ checkpoint của chunk đã commit, thay vì đọc lại toàn bộ file.

Điều kiện cần cân nhắc:

- Reader có trạng thái và hỗ trợ restart cần được cấu hình `saveState` và tên component ổn định.
- Không xóa `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` hoặc execution context trước khi restart.
- Nguồn input cần ổn định hoặc có phiên bản rõ ràng. Nếu file bị thay đổi giữa hai run, checkpoint có thể trỏ vào dữ liệu khác.
- Writer cần bảo đảm không nhân đôi hiệu ứng khi item được phát lại.
- Processor có state trong RAM không tự động được phục hồi. Nếu state ảnh hưởng logic, phải có kế hoạch lưu/khôi phục qua `ExecutionContext` hoặc thiết kế processor stateless.

### 9.3. Sửa dữ liệu trước khi restart

Giả sử job thất bại vì `ORD-150` có số tiền âm và policy yêu cầu fail. Hai lựa chọn recovery:

**Phương án A — sửa input có quản lý phiên bản:** chỉnh nguồn đúng theo quy trình vận hành, xác định checkpoint có còn hợp lệ không, sau đó restart hoặc chạy lại có kiểm soát. Nếu thay đổi cấu trúc/thứ tự file, không giả định có thể restart nguyên trạng.

**Phương án B — quarantine / skip được phê duyệt:** khi nghiệp vụ cho phép xử lý các dòng còn lại, cấu hình skip chính xác, lưu dấu vết của item bị loại và lên quy trình xử lý bổ sung. Việc tăng `skipLimit` không phải cách tự động “chữa” dữ liệu sai.

Không tự xóa metadata rồi khởi chạy lại để che giấu failure. Nếu cần chạy mới, đó là quyết định riêng và phải kiểm soát dữ liệu đã commit trước đó.

## 10. Idempotency và side effect của processor

Một nguyên tắc quan trọng: **Spring Batch có thể thực thi lại thao tác khi retry, rollback hoặc restart.** Do đó, một processor nên được thiết kế sao cho xử lý lại cùng input không tạo tác dụng phụ ngoài ý muốn.

### Thiết kế nên ưu tiên

```java
public ValidatedOrder process(OrderInput item) {
    // Kiểm tra và tính toán thuần:
    BigDecimal normalizedAmount =
            item.amount().setScale(2, RoundingMode.HALF_UP);
    return new ValidatedOrder(
            item.orderId(),
            item.customerCode(),
            normalizedAmount
    );
}
```

Ví dụ cần import `java.math.BigDecimal` và `java.math.RoundingMode`. Việc gọi lại với cùng input tạo cùng kết quả, giúp retry dễ kiểm soát hơn.

### Thiết kế rủi ro

```java
public ValidatedOrder process(OrderInput item) {
    paymentApi.charge(item.customerCode(), item.amount());
    return toValidatedOrder(item);
}
```

Nếu processor được chạy lại do chunk rollback, API thanh toán có thể bị gọi thêm. Muốn thực hiện nghiệp vụ này, cần:

- Dùng business idempotency key ổn định theo giao dịch nguồn, không dùng `stepExecutionId` làm khóa duy nhất cho nghiệp vụ.
- Đảm bảo phía nhận có khả năng nhận request lặp mà không thực hiện hai lần.
- Phân biệt lỗi timeout **không biết kết quả** với lỗi nghiệp vụ từ chối chắc chắn.
- Cân nhắc outbox, staging hoặc event-driven orchestration phù hợp thay cho side effect trong processor.

**“Retry thành công” không đồng nghĩa “side effect đã xảy ra đúng một lần”.** Test recovery phải xác minh cả trạng thái transaction và tác động thực tế tới hệ thống liên quan.

## 11. Dữ liệu thử nghiệm cho failure ở processor

Một bộ fixture tốt cần có các trường hợp có thể tái hiện:

| Mã test | Đầu vào / điều kiện | Kỳ vọng |
| --- | --- | --- |
| P01 | Tất cả item hợp lệ | `COMPLETED`, không process skip |
| P02 | Một item có amount âm, không cấu hình skip | Step `FAILED` |
| P03 | Một item có amount âm, đã cấu hình skip | Item bị bỏ qua, `processSkipCount=1` nếu còn limit |
| P04 | Processor trả `null` cho item ngoài phạm vi | `filterCount=1`, không tính process skip |
| P05 | Catalog timeout lần đầu rồi thành công | Retry có giới hạn, output cuối chính xác |
| P06 | Catalog luôn trả lỗi tạm thời | Retry exhausted, step `FAILED` nếu không cho skip |
| P07 | Số item invalid vượt `skipLimit` | Step `FAILED`; dữ liệu các chunk đã commit vẫn cần kiểm tra |
| P08 | Failure sau ít nhất một chunk commit | Restart tiếp tục đúng và không nhân đôi output |
| P09 | Processor có state mutable và retry | Phát hiện xử lý sai do state không được rollback |
| P10 | Hai worker xử lý song song | Không lẫn state, không duplicate side effect |
| P11 | Exception là bug lập trình | Không bị skip bởi policy quá rộng |
| P12 | Audit/quarantine item bị skip | Có bản ghi lỗi đủ thông tin và không lộ dữ liệu nhạy cảm |

Với mỗi fixture, hãy định nghĩa **input, fault injection, policy và expected output**. Không chỉ assert `BatchStatus`; nên kiểm tra số bản ghi và nội dung dữ liệu nghiệp vụ thực tế.

## 12. Unit test processor và policy lỗi

### 12.1. Unit test validation

Unit test processor không cần khởi chạy Spring context hay database; nó giúp xác minh chính xác exception được ném khi input sai.

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class ValidatingOrderProcessorTest {

    private final CustomerCatalog catalog = mock(CustomerCatalog.class);
    private final ValidatingOrderProcessor processor =
            new ValidatingOrderProcessor(catalog);

    @Test
    void invalidAmountThrowsValidationException() {
        OrderInput item = new OrderInput(
                "ORD-BAD", "C001", new BigDecimal("-10.00"));

        assertThrows(InvalidOrderRowException.class,
                () -> processor.process(item));

        verifyNoInteractions(catalog);
    }

    @Test
    void validOrderIsMappedToValidatedOrder() {
        when(catalog.findCustomer("C001"))
                .thenReturn(new CustomerRef("CUSTOMER-1"));

        OrderInput item = new OrderInput(
                "ORD-OK", "C001", new BigDecimal("100.00"));

        ValidatedOrder actual = processor.process(item);

        assertEquals("ORD-OK", actual.orderId());
        assertEquals("CUSTOMER-1", actual.customerId());
        assertEquals(new BigDecimal("100.00"), actual.amount());
    }

    @Test
    void transientCatalogFailureIsNotSilentlyFiltered() {
        when(catalog.findCustomer("C001"))
                .thenThrow(new CatalogTemporarilyUnavailableException(
                        "catalog temporarily unavailable",
                        new java.io.IOException("timeout")));

        OrderInput item = new OrderInput(
                "ORD-RETRY", "C001", new BigDecimal("20.00"));

        assertThrows(
                CatalogTemporarilyUnavailableException.class,
                () -> processor.process(item));
    }
}
```

Các test trên xác minh **logic processor và loại exception**, chưa xác minh framework có retry/skip đúng policy hay không. Phần đó cần kiểm thử trên một step chạy thực tế.

### 12.2. Test retry bằng một fake dependency có thể điều khiển

Để mô phỏng transient failure trong integration test, dùng một fake catalog đếm số lần được gọi:

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class FlakyCatalog implements CustomerCatalog {
    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public CustomerRef findCustomer(String customerCode) {
        if (attempts.incrementAndGet() < 3) {
            throw new CatalogTemporarilyUnavailableException(
                    "simulated transient failure", null);
        }
        return new CustomerRef("CUSTOMER-1");
    }

    public int attempts() {
        return attempts.get();
    }
}
```

Fake này trả lỗi hai lần đầu và thành công lần thứ ba. Nó phù hợp với test step chạy tuần tự, xử lý một item cần gọi catalog. Nếu step có nhiều item hoặc chạy song song, bộ đếm chung có thể khiến điều kiện lỗi thay đổi ngoài mong đợi; dùng fake theo business key hoặc một test scope riêng để xác định chính xác lần lỗi của từng item.

Trong integration test với `retryLimit(3)`, nếu chính sách áp dụng đúng cho exception trên, step có thể vượt qua transient failure mà không tạo duplicate output. Cần assert **output cuối cùng** cùng số lần fake được gọi. Không dùng `Thread.sleep(...)` để giả lập lỗi tạm thời.

## 13. Integration test với Spring Batch Test

Với **Spring Batch 5.x**, module `spring-batch-test` cung cấp `@SpringBatchTest` và `JobLauncherTestUtils`. Có thể viết integration test dùng một job test riêng, reader đọc fixture có sẵn và writer ghi vào database test.

Ví dụ cấu trúc:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class OrderProcessorRecoveryIT {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Test
    void skipsOneInvalidOrderAndCompletes() throws Exception {
        // Giả định test context đã có đúng job cần chạy,
        // reader chứa fixture với 5 dòng, 1 dòng validation lỗi,
        // writer ghi output vào database test riêng.
        var params = new JobParametersBuilder()
                .addString("testRun", java.util.UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution = launcher.launchJob(params);
        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions()
                .iterator().next();
        assertEquals(5, step.getReadCount());
        assertEquals(1, step.getProcessSkipCount());
        assertEquals(4, step.getWriteCount());

        // Đồng thời truy vấn output: xác minh đúng bốn order hợp lệ.
    }
}
```

Đây là **khung test minh họa**. Để chạy được, ứng dụng phải cung cấp một job phù hợp với `launcher`, cấu hình `JobRepository`, database/schema test, reader/writer fixture và policy skip đã mô tả. Nếu context có nhiều `Job`, đặt job cụ thể cho `JobLauncherTestUtils` trước khi launch. Nếu processor filter hoặc writer có logic loại bản ghi, điều chỉnh các bộ đếm kỳ vọng theo chính sách thực tế.

Đối với Spring Batch 6.x, công cụ test và một số package đã thay đổi; `JobOperatorTestUtils` thay vai trò khởi chạy job trong các ví dụ kiểm thử Spring Batch 6. Hãy đối chiếu API với phiên bản framework được dự án sử dụng.

### Test vượt skip limit

Với `skipLimit(1)`, fixture có hai item ném `InvalidOrderRowException`. Một test cần xác minh:

1. Step/job kết thúc `FAILED`.
2. Không có item lỗi bị ghi thành dữ liệu nghiệp vụ hợp lệ.
3. Những chunk đã commit trước failure vẫn được xác định rõ.
4. Log/audit có `jobExecutionId` và `stepExecutionId` để điều tra.

Đừng chỉ kiểm tra exception được ném ra từ `launchJob(...)`: Spring Batch thường ghi lỗi vào `JobExecution` và trả về execution có status `FAILED`, tùy loại lỗi/hạ tầng. Cần quan sát `execution.getStatus()` và `execution.getAllFailureExceptions()`.

### Test restart

Với một fixture có nhiều chunk:

- Cho chunk đầu commit thành công.
- Inject failure ở processor trong chunk sau để job `FAILED`.
- Giữ nguyên `JobRepository` và output, sửa điều kiện lỗi của fake dependency.
- Restart đúng `JobInstance` theo API framework, không tạo identifying parameters khác.
- Assert step hoàn tất và output cuối cùng không lặp record.

Nếu muốn test restart checkpoint, reader phải được cấu hình lưu tiến độ phù hợp; không reset database metadata giữa hai execution. Để lặp lại test từ đầu giữa các method, dùng database/schema test biệt lập hoặc cleanup có chủ đích **sau** khi kết thúc toàn bộ kịch bản restart.

## 14. Monitoring và logging khi processor thất bại

Khi điều tra một failure, nên thu thập:

```text
jobName
jobInstanceId
jobExecutionId
stepName
stepExecutionId
businessDate
itemKey (nếu không nhạy cảm)
exceptionType
errorCategory
retryAttempt (nếu được instrumentation)
batchStatus
processSkipCount
rollbackCount
```

**Không ghi raw payload nhạy cảm** vào log hoặc metric label. Nếu có nhiều item lỗi, ghi một mã lỗi/tên trường, khóa nghiệp vụ được phép hiển thị và một mã tra cứu đến dữ liệu lưu an toàn.

Spring Batch hỗ trợ `JobExecution` và `StepExecution` để truy lại trạng thái. Với repository JDBC thông dụng:

```sql
SELECT
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.PROCESS_SKIP_COUNT,
    se.WRITE_COUNT,
    se.ROLLBACK_COUNT,
    se.EXIT_CODE,
    se.EXIT_MESSAGE,
    je.JOB_EXECUTION_ID,
    ji.JOB_NAME
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
  ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE se.STEP_EXECUTION_ID = :stepExecutionId;
```

Truy vấn lấy metadata step chứ không thể tự phân biệt chắc chắn exception ném từ reader, processor hay writer. Phân loại lỗi cần dựa thêm exception class, log có vị trí xử lý, `SkipListener` hoặc instrumentation của ứng dụng.

### Những metric nên bổ sung

| Metric | Mục đích |
| --- | --- |
| `job_execution_failed_total{jobName}` | Số lần job kết thúc thất bại |
| `step_execution_failed_total{jobName,stepName}` | Phát hiện step thường xuyên lỗi |
| `batch_process_skipped_total{jobName,stepName,errorCategory}` | Theo dõi số item bị skip ở processor |
| Retry attempts theo dependency/category | Biết service ngoài đang chập chờn |
| Job/step duration | Phát hiện retry làm batch chậm |
| Quarantine backlog | Biết dữ liệu sai đang tồn đọng |
| Last successful completion | Phát hiện job không còn hoàn tất đúng lịch |

Đây là **tên metric gợi ý tự thiết kế**, không phải cam kết tên metric mặc định của Spring Batch/Micrometer. Khi dùng exporter cụ thể, xác minh metric thực tế và cách chuẩn hóa nhãn. Không đưa `itemId`, `stepExecutionId` hoặc exception message vào metric labels vì số chuỗi thời gian sẽ tăng rất nhanh.

## 15. Những lỗi triển khai recovery thường gặp

### Bắt mọi exception rồi return null

```java
public Output process(Input item) {
    try {
        return convert(item);
    } catch (Exception ex) {
        return null;
    }
}
```

Cách này biến tất cả lỗi thành filter. Job có thể `COMPLETED`, `filterCount` tăng, nhưng không có process skip hoặc failure để cảnh báo. Chỉ filter khi contract nghiệp vụ cho phép.

### Retry lỗi validation mãi không hết

Amount âm, mã khách hàng sai format hoặc trường bắt buộc null sẽ không được “chữa” bằng retry. Retry tốn thời gian và làm tăng tải. Với lỗi xác định, chọn skip/quarantine hoặc fail theo policy.

### Skip quá rộng

`.skip(Exception.class)` có thể bỏ qua bug như `NullPointerException`, lỗi mapping hoặc truy cập tài nguyên. Tập dữ liệu đã mất mà dashboard vẫn báo `COMPLETED`. Nên dùng exception cụ thể và giới hạn skip phù hợp.

### Processor có side effect không idempotent

Nếu processor gửi email, tạo thanh toán hoặc publish message, retry có thể làm phát lại hiệu ứng. Dời thao tác ra khỏi processor khi có thể; với hệ thống ngoài, cần idempotency key và cơ chế xác nhận kết quả.

### Hiểu sai skipLimit

`skipLimit(10)` không nghĩa là “cho phép 10 lỗi mỗi chunk”; giới hạn được áp dụng theo step và tổng skip theo semantics của framework. Nếu batch có nhiều triệu record, đặt giới hạn skip cần dựa trên yêu cầu chất lượng dữ liệu chứ không chỉ chọn số lớn để job luôn chạy hết.

### Chỉ kiểm tra trạng thái job mà bỏ qua dữ liệu output

Một job `COMPLETED` vẫn có thể thiếu dữ liệu do skip/filter, hoặc writer ghi sai kết quả. Cần đối chiếu `readCount`, `processSkipCount`, `writeCount`, số dòng thực tế và giá trị nghiệp vụ.

### Reset repository trước khi restart

Xóa metadata `BATCH_*` có thể phá checkpoint, khiến test không còn là restart thật. Chỉ cleanup sau khi kịch bản đã hoàn tất hoặc trong database test mới.

### Không xem transaction boundary

Một chunk lỗi có thể rollback, còn các chunk trước đã commit. Đừng giả định `FAILED` tự động hoàn tác toàn bộ output của cả job. Writer nên idempotent và test phải kiểm tra output sau failure cũng như sau restart.

### Mutable state trong singleton processor

State như `HashSet`, bộ đếm hoặc cache thay đổi trong processor có thể bị lệch khi rollback hoặc lẫn giữa execution chạy đồng thời. Dùng processor stateless khi có thể; nếu phải dùng state, xác định lifecycle, transaction và checkpoint rõ ràng.

## 16. Bài thực hành

**Bài 1 – Failure mặc định.** Tạo `ItemProcessor` ném `InvalidOrderRowException` khi amount âm. Chạy chunk step không bật fault tolerance. Xác minh `JobExecution`/`StepExecution` có trạng thái `FAILED` và dữ liệu của các chunk đã commit.

**Bài 2 – Skip dữ liệu lỗi.** Bật `.skip(InvalidOrderRowException.class).skipLimit(2)`. Đưa vào 6 item, trong đó 1 item amount âm. Xác minh `processSkipCount=1`, output chỉ có 5 item hợp lệ và skip listener ghi lý do.

**Bài 3 – Vượt giới hạn.** Với cùng policy, tạo 3 item invalid. Xác minh step thất bại khi vượt skip limit, kiểm tra những record đã commit và xác định dữ liệu nào phải xử lý lại.

**Bài 4 – Retry transient error.** Dùng fake `CustomerCatalog` trả timeout hai lần đầu và thành công ở lần thứ ba. Bật retry cho exception cụ thể và xác minh item cuối cùng được ghi đúng một lần.

**Bài 5 – Retry exhausted.** Cho fake luôn ném transient exception. Không cấu hình skip cho loại lỗi này. Xác minh job `FAILED`, log có mã lỗi và thời gian retry không tăng vô hạn.

**Bài 6 – Restart sau failure.** Cho chunk đầu commit, chunk sau gặp lỗi processor. Khắc phục điều kiện lỗi rồi restart đúng `JobInstance`; không xóa metadata. Xác minh không có duplicate output và những item còn lại được xử lý.

**Bài 7 – Side effect.** Tạo processor giả lập gửi thông báo mỗi lần `process` được gọi. Gây retry/rollback để thấy nguy cơ gửi lặp. Sau đó thay bằng thiết kế idempotent hoặc dời việc gửi ra một pipeline an toàn hơn và kiểm chứng kết quả.

**Bài 8 – Monitoring.** Ghi log theo `jobExecutionId`/`stepExecutionId`, truy vấn các bộ đếm `PROCESS_SKIP_COUNT` và `ROLLBACK_COUNT`, đối chiếu với bảng quarantine. Thiết kế cảnh báo khi skip tăng bất thường dù job vẫn `COMPLETED`.

## 17. Kết luận

**Failure ở processor** là một phần của thiết kế recovery trong Spring Batch, không chỉ là một exception cần bắt. Với item không hợp lệ, cần quyết định **fail**, **skip/quarantine** hoặc **filter** theo đúng contract nghiệp vụ; với phụ thuộc tạm thời, dùng **retry có giới hạn**; với lỗi chương trình, ưu tiên fail và điều tra. Những chính sách này phải đi kèm transaction/rollback semantics, checkpoint, idempotency và khả năng restart của job.

Một giải pháp đáng tin cậy không dừng ở `BatchStatus.COMPLETED`: nó phải xác minh **dữ liệu đã commit**, **số item bị skip**, **số lần retry**, **khả năng khôi phục đúng công việc logic**, và **side effect không bị lặp**. Thiết kế processor càng thuần và ít state, các kịch bản retry/restart càng dễ kiểm thử và vận hành.

### Tài liệu tham khảo

- [Spring Batch Reference – Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html)
- [Spring Batch Reference – Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html)
- [Spring Batch Reference – Configuring Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html)
- [Spring Batch Reference – Controlling Rollback](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/controlling-rollback.html)
- [Spring Batch Reference – Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html)
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html)
