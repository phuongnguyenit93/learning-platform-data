# Recovery sau retry hết

Trong Spring Batch, retry cho phép thử lại một thao tác khi gặp lỗi có khả năng phục hồi, chẳng hạn deadlock hoặc lỗi kết nối tạm thời. Tuy nhiên, retry luôn có giới hạn. Khi số lần thử đã hết mà thao tác vẫn thất bại, ứng dụng phải có cách xử lý tiếp theo. Đây là phần **recovery sau retry hết**.

Recovery không có nghĩa là tiếp tục thử vô hạn. Tùy loại lỗi và yêu cầu nghiệp vụ, Spring Batch có thể bỏ qua item theo skip policy, ghi nhận item lỗi để xử lý sau, hoặc làm step thất bại để người vận hành khắc phục rồi restart. Chọn đúng nhánh giúp tránh mất dữ liệu, ghi trùng hoặc che giấu lỗi hệ thống.

## 1. Retry và retry exhaustion

Trong chunk processing, reader lấy item, processor xử lý và writer ghi kết quả. Nếu một thao tác phát sinh exception thuộc loại có thể retry, Spring Batch có thể thử lại theo retry policy đã cấu hình.

Ví dụ một writer cập nhật database gặp deadlock. Database có thể chọn một transaction làm nạn nhân và rollback transaction đó. Đây là lỗi có thể tạm thời: nếu thử lại sau một khoảng chờ, transaction có thể thành công.

```text
Item / chunk được xử lý
          |
          v
       Writer
          |
          +---- Deadlock exception
                    |
                    v
                 Retry
                    |
             +------+------+
             |             |
          Thành công     Vẫn lỗi
             |             |
             v             v
          Commit       Retry tiếp
                           |
                           v
                     Hết retry limit
                           |
                           v
                      Recovery path
```

**Retry exhaustion** xảy ra khi thao tác vẫn phát sinh lỗi sau khi đã sử dụng hết số lần thử được phép. Từ thời điểm này, retry policy không tiếp tục thử lại; exception được chuyển sang bước xử lý tiếp theo của fault-tolerant step.

Trong Spring Batch, nhánh tiếp theo thường là:

- Nếu exception được skip policy cho phép và chưa vượt `skipLimit`, item có thể được bỏ qua; `SkipListener` có thể ghi nhận lỗi.
- Nếu exception không được phép skip hoặc đã vượt giới hạn skip, exception làm chunk/step thất bại.
- Nếu ứng dụng dùng một retry/recovery abstraction riêng, callback recovery của abstraction đó có thể thực hiện hành động thay thế theo thiết kế.

Không phải mọi lỗi sau retry đều có thể được phục hồi tự động. Cần phân biệt lỗi tạm thời, lỗi dữ liệu và lỗi cấu hình/hạ tầng.

## 2. Cấu hình retry trong Spring Batch

Với chunk-oriented step, cấu hình retry thường được đặt trong phần fault-tolerant của step builder.

```java
@Bean
Step updateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("updateOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(DeadlockLoserDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

Trong ví dụ, step chỉ retry exception deadlock được chỉ định. Không nên retry mọi `Exception`, vì lỗi như dữ liệu sai định dạng, thiếu cột bắt buộc hoặc câu SQL sai sẽ không tự biến mất sau vài lần thử.

`retryLimit` đặt giới hạn cho retry policy. Khi đọc tài liệu/API của phiên bản Spring Batch và Spring Retry đang dùng, cần xác nhận cách policy tính số lần gọi (lần đầu và các lần thử lại) để không nhầm giữa tổng số attempt với số retry bổ sung. Trong vận hành, nên log số attempt thực tế thay vì suy đoán từ tên cấu hình.

### Chọn exception được retry

Các lỗi thường có thể cân nhắc retry nếu nguyên nhân là tạm thời:

- Deadlock hoặc lock acquisition failure.
- Một số lỗi kết nối database có thể phục hồi.
- Timeout khi gọi dịch vụ ngoài, nếu thao tác có thể gửi lại an toàn.
- Lỗi tạm thời từ hệ thống lưu trữ hoặc message broker.

Các lỗi thường không nên retry:

- Dữ liệu không hợp lệ hoặc vi phạm quy tắc nghiệp vụ cố định.
- SQL/schema sai hoặc thiếu cột.
- File bắt buộc không tồn tại.
- Quyền truy cập bị từ chối do cấu hình.
- Lỗi lập trình không có khả năng tự phục hồi.

Nếu exception có nhiều nguyên nhân, hãy phân loại rõ theo exception cụ thể hoặc cause chain. Một exception chung như `DataAccessException` có thể bao gồm cả lỗi tạm thời lẫn lỗi không thể khắc phục bằng retry.

## 3. Recovery sau retry hết trong fault-tolerant step

Trong Spring Batch chunk processing, retry và skip thường được cấu hình cùng nhau. Khi thao tác đã hết retry, framework kiểm tra exception theo skip policy. Nếu exception được phép skip, item có thể được bỏ qua và chunk tiếp tục. Nếu không, step thất bại.

Ví dụ cho phép retry deadlock, nhưng nếu sau retry vẫn không thành công thì bỏ qua item theo chính sách nghiệp vụ:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skip(DeadlockLoserDataAccessException.class)
        .skipLimit(20)
        .build();
```

Ví dụ này minh họa một lựa chọn có điều kiện: sau khi retry deadlock hết, exception deadlock cũng được skip nếu giới hạn còn cho phép. Chỉ nên làm vậy nếu nghiệp vụ chấp nhận bỏ qua item đó và có cơ chế đối soát. Nếu deadlock phản ánh database đang quá tải hoặc tranh chấp diện rộng, bỏ qua từng item có thể che giấu sự cố hệ thống; khi đó nên để step thất bại.

Điểm quan trọng là retry policy và skip policy giải quyết hai câu hỏi khác nhau:

- Retry policy: có nên thử lại exception này không, và thử tối đa bao nhiêu lần?
- Skip policy: sau khi không thể xử lý item, có được phép bỏ qua nó để tiếp tục step không?

Nếu exception không được skip, hết retry sẽ làm exception thoát ra ngoài và step thất bại. Đó cũng là một recovery decision hợp lệ: dừng để giữ dữ liệu đáng tin cậy và chờ can thiệp.

## 4. Khi nào nên skip sau retry exhaustion?

Skip phù hợp khi item lỗi có thể được loại riêng mà không làm sai kết quả của các item còn lại. Ví dụ:

- Một đơn hàng có mã tham chiếu không hợp lệ.
- Một dòng file sai định dạng nhưng các dòng khác độc lập.
- Một bản ghi không thỏa điều kiện nghiệp vụ đã được định nghĩa là có thể loại.

Skip thường không phù hợp nếu lỗi cho thấy toàn bộ hệ thống đích đang không khả dụng. Ví dụ, writer không ghi được vì database mất kết nối. Bỏ qua các item khi database đang lỗi có thể khiến phần lớn dữ liệu không được ghi nhưng job vẫn chạy qua.

Trước khi cho phép skip một exception sau retry, hãy xác định:

1. Item có độc lập với các item khác không?
2. Bỏ qua item có làm mất một nghĩa vụ nghiệp vụ không?
3. Có thể ghi nhận item lỗi để sửa và chạy bù sau không?
4. Exception là lỗi riêng của item hay dấu hiệu lỗi hệ thống?
5. Có thể xác định chính xác item gây lỗi không, đặc biệt khi lỗi phát sinh trong writer nhận cả chunk?

Nếu không trả lời được các câu hỏi này, để step thất bại thường an toàn hơn.

## 5. Ghi nhận item sau retry hết bằng SkipListener

Khi một item bị skip, `SkipListener` là nơi phù hợp để ghi nhận thông tin lỗi và khóa nghiệp vụ để có thể đối soát.

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    private final RejectedOrderService rejectedOrderService;

    public OrderSkipListener(RejectedOrderService rejectedOrderService) {
        this.rejectedOrderService = rejectedOrderService;
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        rejectedOrderService.recordReadFailure(
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        rejectedOrderService.recordRejectedOrder(
                item.orderId(),
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        rejectedOrderService.recordWriteFailure(
                item.orderId(),
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }
}
```

Đăng ký listener trong step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(orderSkipListener)
        .build();
```

Listener cung cấp thông tin theo giai đoạn:

- `onSkipInRead`: reader thất bại trước khi tạo được item; callback chỉ có exception.
- `onSkipInProcess`: có item đầu vào và exception từ processor.
- `onSkipInWrite`: có item đầu ra và exception từ writer.

Đối với lỗi writer, framework có thể phải xác định item gây lỗi trong chunk. Không phải mọi writer hoặc exception đều cho phép xác định item lỗi một cách đơn giản.

### Bảo đảm việc ghi nhận lỗi không tạo thêm lỗi

Nếu `RejectedOrderService` ghi vào cùng database và cùng transaction của chunk, việc ghi bản ghi lỗi có thể tham gia transaction đó. Nếu listener gửi message hoặc gọi API bên ngoài, tác dụng phụ không tự động rollback cùng transaction database.

Nên dùng khóa chống trùng, chẳng hạn `(job_execution_id, step_execution_id, item_id, error_type)`, hoặc outbox nếu cần gửi thông báo. Không nên để một item bị retry/skip nhiều lần tạo ra hàng loạt bản ghi lỗi giống nhau mà không có cách phân biệt lịch sử và bản ghi duy nhất.

## 6. Recovery bằng dead-letter hoặc rejected-record store

Một lựa chọn phổ biến là lưu item không xử lý được vào vùng cách ly (quarantine/rejected store) để sửa hoặc xử lý lại sau. Đây không phải hành vi tự động của Spring Batch; ứng dụng cần xây dựng nơi lưu và quy trình vận hành.

Một bảng rejected item có thể lưu:

| Trường | Mục đích |
|---|---|
| `batch_id` | Định danh batch nghiệp vụ. |
| `job_execution_id` | Lần thực thi ghi nhận lỗi. |
| `step_execution_id` | Step phát sinh lỗi. |
| `item_key` | Khóa nghiệp vụ của item. |
| `payload_reference` | Đường dẫn hoặc khóa tới dữ liệu gốc nếu payload lớn. |
| `exception_type` | Loại lỗi cuối cùng sau retry. |
| `error_message` | Thông tin lỗi đã được làm sạch. |
| `attempt_count` | Số lần thử đã ghi nhận nếu ứng dụng theo dõi. |
| `recovery_status` | Trạng thái như `PENDING`, `REPROCESSED`, `RESOLVED`. |
| `created_at` | Thời điểm ghi nhận. |

Với dữ liệu nhạy cảm, không nên lưu toàn bộ payload hoặc thông tin xác thực vào bảng lỗi. Có thể lưu khóa tham chiếu tới kho dữ liệu có kiểm soát truy cập.

Một quy trình xử lý lại rejected item thường gồm:

1. Lọc các item ở trạng thái `PENDING`.
2. Xác định và sửa nguyên nhân lỗi nếu cần.
3. Tạo một batch xử lý lại có định danh riêng hoặc đưa item vào một job recovery.
4. Ghi kết quả thành công/thất bại mới mà vẫn giữ lịch sử lần lỗi trước.
5. Đánh dấu item đã được xử lý lại bằng một transaction nhất quán.

Không nên xóa dấu vết lỗi ban đầu khi recovery thành công; lịch sử đó hữu ích cho audit và phân tích chất lượng dữ liệu.

## 7. Recovery bằng RetryListener và callback

Trong hệ sinh thái Spring Retry, `RetryListener` cho phép quan sát vòng đời retry, ví dụ mở context, nhận thông báo mỗi lần lỗi và đóng context sau khi hoàn tất. Nó hữu ích để log attempt, phát metric hoặc gắn correlation ID.

```java
public class LoggingRetryListener implements RetryListener {

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        // Ghi nhận một lần retry thất bại.
        log.warn("Retry attempt failed: {}", throwable.toString());
    }
}
```

API callback cụ thể và cách đăng ký listener phụ thuộc phiên bản Spring Retry/Spring Batch đang sử dụng. Trong Spring Batch fault-tolerant step, listener cần được đăng ký theo cơ chế hỗ trợ của builder/step. Không nên nhầm `RetryListener` dùng để quan sát retry với một recovery callback có quyền quyết định cách thay thế kết quả.

Nếu dùng `RetryTemplate` trực tiếp trong một service, Spring Retry hỗ trợ `RecoveryCallback` để định nghĩa kết quả khi retry policy hết attempt:

```java
RetryTemplate retryTemplate = RetryTemplate.builder()
        .maxAttempts(3)
        .fixedBackoff(1000)
        .retryOn(TransientDataAccessException.class)
        .build();

OrderResult result = retryTemplate.execute(
        context -> orderGateway.submit(order),
        context -> recoveryService.recordPending(order, context.getLastThrowable()));
```

Ví dụ này minh họa cách sử dụng Spring Retry độc lập: khi retry hết, recovery callback ghi nhận yêu cầu cần xử lý sau và trả về một `OrderResult` theo hợp đồng của ứng dụng. Nếu recovery callback không thể tạo kết quả hợp lệ, nó nên ném exception để lỗi được truyền lên caller.

Không nên bọc tùy tiện toàn bộ `ItemProcessor` hoặc `ItemWriter` bằng một `RetryTemplate` riêng nếu step đã có retry policy của Spring Batch. Hai tầng retry chồng nhau có thể làm số attempt thực tế lớn hơn dự kiến, khó tính thời gian và gây lặp tác dụng phụ.

## 8. Backoff sau mỗi lần retry

Thử lại ngay lập tức nhiều lần có thể làm hệ thống đang quá tải càng quá tải hơn. Backoff tạo khoảng chờ giữa các lần thử, cho dịch vụ/database thời gian phục hồi.

Các chiến lược thường gặp:

- **Fixed backoff:** mỗi lần chờ cùng một khoảng thời gian.
- **Exponential backoff:** thời gian chờ tăng dần theo số lần thử.
- **Exponential backoff with jitter:** thêm độ ngẫu nhiên để nhiều worker không cùng retry đúng một thời điểm.

Ví dụ cấu hình policy trong fault-tolerant step:

```java
ExponentialBackOffPolicy backOffPolicy = new ExponentialBackOffPolicy();
backOffPolicy.setInitialInterval(500L);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(5000L);

return new StepBuilder("callPartnerStep", jobRepository)
        .<PartnerRequest, PartnerResponse>chunk(50, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(ResourceAccessException.class)
        .retryLimit(3)
        .backOffPolicy(backOffPolicy)
        .build();
```

Thời gian backoff phải nằm trong ngân sách thời gian của job và timeout của dịch vụ. Với nhiều partition, nên cân nhắc jitter hoặc giới hạn concurrency để tránh retry storm.

## 9. Khi retry hết và exception không được skip

Nếu exception không thuộc skip policy hoặc skip limit đã bị vượt, step thường kết thúc `FAILED`. Đây là recovery path quan trọng: dừng xử lý, lưu metadata, phát cảnh báo và chờ khắc phục.

Ví dụ một step chỉ retry deadlock, không cho skip:

```java
return new StepBuilder("criticalBalanceStep", jobRepository)
        .<BalanceInput, BalanceUpdate>chunk(100, transactionManager)
        .reader(balanceReader)
        .processor(balanceProcessor)
        .writer(balanceWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
```

Nếu deadlock tiếp tục sau khi hết retry, exception làm step thất bại. Dữ liệu của transaction chunk chưa commit được rollback theo transaction manager. Các chunk trước đã commit vẫn còn hiệu lực.

Sau đó, người vận hành cần:

1. Tra cứu JobExecution/StepExecution và exception cuối cùng.
2. Xác định nguyên nhân deadlock hoặc lock contention.
3. Kiểm tra các chunk đã commit và tác dụng phụ ngoài transaction.
4. Khắc phục nguyên nhân, ví dụ tối ưu index, thay đổi thứ tự cập nhật hoặc giảm concurrency.
5. Restart cùng JobInstance bằng đúng identifying JobParameters nếu job cho phép.
6. Xác nhận reader/writer có checkpoint và có thể xử lý lại item an toàn.

Không nên đổi identifying JobParameters chỉ để né lỗi `JobInstance` đã tồn tại nếu mục tiêu là restart. Thay đổi tham số định danh sẽ tạo một đơn vị xử lý logic khác.

## 10. Recovery ở cấp Job flow

Ngoài recovery cho từng item, job có thể có một step riêng để ghi nhận hoặc xử lý khi step chính thất bại. Flow có thể định tuyến theo `ExitStatus` của step.

Ví dụ:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step recordFailureStep,
        Step publishSuccessStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importStep)
                .on("FAILED").to(recordFailureStep)
            .from(importStep)
                .on("COMPLETED").to(publishSuccessStep)
            .from(recordFailureStep)
                .on("COMPLETED").fail()
            .from(publishSuccessStep)
                .on("*").end()
            .end()
            .build();
}
```

Trong ví dụ, khi `importStep` thất bại sau retry exhaustion, flow chạy `recordFailureStep` để lưu thông tin hoặc phát cảnh báo. Sau khi ghi nhận thành công, flow vẫn kết thúc job với trạng thái thất bại theo `.fail()`, vì dữ liệu import chưa hoàn tất.

Nếu recovery step thực sự khắc phục được lỗi và nghiệp vụ cho phép coi toàn bộ quy trình đã hoàn tất, có thể thiết kế transition kết thúc thành công. Nhưng cần hiểu rằng việc chuyển flow sang nhánh recovery không tự làm cho step import đã thất bại trở thành `COMPLETED`. Hãy giữ lại thông tin lỗi ban đầu và quy định rõ status/ExitStatus cuối cùng của job.

Recovery step cũng có thể thất bại. Khi đó cần giữ nguyên lỗi gốc và lỗi recovery để người vận hành biết cả thao tác chính lẫn thao tác khắc phục đều không thành công.

## 11. Recovery bằng restart sau khi sửa nguyên nhân

Retry diễn ra trong một execution. Restart là việc khởi chạy lại một JobInstance đã thất bại hoặc dừng theo cách cho phép, tạo `JobExecution` mới.

```text
JobInstance: importOrdersJob / businessDate=2026-11-15
   |
   +-- JobExecution #1
   |      +-- importStep: FAILED (retry exhausted)
   |
   +-- JobExecution #2 (restart sau khi khắc phục)
          +-- importStep: tiếp tục theo checkpoint
```

Restart phù hợp khi nguyên nhân đã được sửa, chẳng hạn:

- Dịch vụ đối tác đã hoạt động trở lại.
- Database đã giải phóng lock hoặc được tối ưu truy vấn.
- File đầu vào đã được sửa và được quản lý như cùng một batch input theo quy tắc nghiệp vụ.
- Cấu hình kết nối đã được khắc phục.

Khi restart, cần dùng lại đúng identifying parameters để nhận diện cùng JobInstance. Đồng thời, phải bảo đảm dữ liệu đầu vào và checkpoint còn tương thích. Nếu thay file cùng đường dẫn bằng nội dung khác, checkpoint cũ có thể không còn đúng.

Không nên restart ngay khi nguyên nhân chưa được khắc phục. Làm vậy chỉ lặp lại cùng lỗi, tiêu tốn tài nguyên và có thể tạo tác dụng phụ lặp.

## 12. Reader, processor và writer cần an toàn khi recovery

Sau retry exhaustion, tùy lựa chọn skip hoặc restart, một item có thể được đọc/xử lý/ghi lại. Vì vậy, recovery cần xét toàn bộ pipeline.

### Reader

- Hỗ trợ checkpoint nếu cần restart.
- Dùng nguồn dữ liệu ổn định giữa các lần chạy.
- Không làm mất item khi transaction rollback hoặc khi xác nhận message.
- Có thứ tự và khóa phân trang ổn định.

### Processor

- Ưu tiên logic deterministic, không có side effect.
- Không tạo UUID hoặc timestamp mới mỗi lần gọi nếu chúng ảnh hưởng identity/kết quả.
- Nếu tra cứu dữ liệu ngoài, dùng snapshot/version cố định khi cần kết quả tái lập.
- Tránh sửa state mutable dùng chung khi chạy song song.

### Writer

- Dùng unique key hoặc idempotency key để chống ghi trùng.
- Xác định rõ tài nguyên nào tham gia transaction.
- Không giả định HTTP call, email hoặc message publish được rollback cùng database.
- Có cơ chế đối soát hoặc outbox cho tác dụng phụ bên ngoài.

Một processor deterministic không đủ bảo đảm toàn bộ recovery an toàn nếu writer vẫn insert trùng hoặc hệ thống ngoài nhận lặp yêu cầu.

## 13. Recovery khi gọi API hoặc hệ thống ngoài

Lỗi timeout khi gọi API có một điểm khó: client không biết chắc server đã xử lý request hay chưa. Ví dụ, đối tác đã nhận yêu cầu tạo thanh toán nhưng response bị mất trên đường về. Nếu retry bằng một request mới không có khóa chống trùng, có thể tạo hai thanh toán.

Các biện pháp thường dùng:

- Dùng idempotency key ổn định theo batch ID và item ID.
- Lưu trạng thái request/response trong database.
- Dùng outbox để ghi sự kiện cùng transaction dữ liệu nghiệp vụ rồi publisher gửi lại có kiểm soát.
- Khi timeout, tra cứu trạng thái giao dịch bằng business reference trước khi gửi lại.
- Phân biệt lỗi chắc chắn chưa được xử lý với lỗi không rõ kết quả.

Ví dụ tạo khóa ổn định:

```java
String idempotencyKey = batchId + ":" + order.orderId();
partnerClient.submit(order, idempotencyKey);
```

Khóa phải giữ nguyên qua các lần retry và restart của cùng một yêu cầu nghiệp vụ. Không tạo khóa mới mỗi lần gọi.

## 14. Retry exhaustion trong partitioning

Với partitioning, mỗi worker step có thể có retry policy riêng. Khi retry của một item hết, worker có thể skip item nếu policy cho phép hoặc thất bại. Manager step sau đó tổng hợp trạng thái của các partition theo cơ chế điều phối.

```text
managerStep
  |
  +-- partition0: COMPLETED
  +-- partition1: FAILED (retry exhausted)
  +-- partition2: COMPLETED
  +-- partition3: COMPLETED
```

Các partition đã hoàn tất và chunk đã commit không tự động rollback khi partition1 thất bại. Khi restart, Spring Batch có thể chạy lại partition chưa hoàn tất theo metadata. Cần giữ tên/range partition ổn định và writer idempotent để không xử lý trùng các tác dụng phụ.

Nếu partition thất bại do lỗi hệ thống chung như database unavailable, việc để các partition khác tiếp tục retry có thể làm tăng tải. Có thể cần giới hạn concurrency, backoff và một cơ chế dừng có kiểm soát thay vì để mọi worker retry liên tục.

## 15. Quan sát retry và recovery

Để hiểu vì sao một item đi vào recovery, nên ghi nhận các thông tin:

- Job name, JobExecution ID và StepExecution ID.
- Partition name nếu có.
- Item/business key hoặc vị trí nguồn.
- Exception type và cause cuối cùng.
- Số attempt thực tế và thời gian backoff.
- Hành động cuối cùng: retry thành công, skip, ghi rejected item hay làm step thất bại.
- Correlation ID/idempotency key cho request ngoài.

Có thể dùng `RetryListener` để quan sát các lần thử và `SkipListener` để ghi nhận item bị bỏ qua. `StepExecutionListener` hoặc `JobExecutionListener` có thể tổng kết trạng thái sau khi step/job kết thúc.

Không nên log payload nhạy cảm hoặc toàn bộ stack trace vào mọi lần retry. Hãy ghi exception type, business key và correlation ID; lưu chi tiết cần điều tra ở nơi có kiểm soát truy cập.

## 16. Kiểm thử recovery sau retry hết

Kiểm thử nên xác nhận cả đường đi thành công và thất bại:

1. Lần gọi đầu thất bại, lần retry sau thành công: item được ghi đúng và không bị skip.
2. Mọi lần thử đều thất bại, exception skippable: item được ghi nhận skip đúng một lần theo semantics listener và step tiếp tục.
3. Mọi lần thử đều thất bại, exception không skippable: chunk rollback và step kết thúc `FAILED`.
4. Vượt `skipLimit`: step thất bại dù exception thuộc loại skippable.
5. Recovery callback hoặc rejected-record writer thất bại: lỗi recovery được thể hiện rõ, không che mất lỗi gốc.
6. Restart sau khi khắc phục: reader tiếp tục từ checkpoint và dữ liệu không bị ghi trùng.
7. API timeout sau khi server đã nhận request: idempotency key ngăn tác dụng phụ lặp.

Có thể dùng mock để mô phỏng exception tạm thời và kiểm tra số lần gọi. Với transaction/restart, nên có integration test dùng JobRepository và database test để xác nhận metadata, commit, rollback và StepExecution thực tế.

## 17. Các lỗi thường gặp khi xử lý retry exhaustion

| Vấn đề | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Retry mãi nhưng không phục hồi | Retry cả lỗi không thể khắc phục hoặc không có giới hạn phù hợp. | Chỉ retry exception transient và đặt limit. |
| Hết retry nhưng item bị mất | Không có skip/rejected-record path và lỗi bị xử lý không đúng. | Để step fail hoặc lưu item vào vùng cách ly theo nghiệp vụ. |
| Job COMPLETED dù database đang lỗi | Exception hạ tầng bị cấu hình skip quá rộng. | Thu hẹp skip policy; không skip lỗi hệ thống diện rộng. |
| Ghi lỗi trùng sau retry | Listener/recovery có side effect không idempotent. | Dùng khóa chống trùng và transaction/outbox phù hợp. |
| Recovery callback trả dữ liệu giả | Cố thay thế lỗi bằng giá trị mặc định không hợp lệ. | Chỉ trả fallback khi nghiệp vụ định nghĩa rõ; nếu không, ném exception. |
| Restart tạo JobInstance mới | Identifying JobParameters thay đổi. | Dùng lại đúng identifying parameters khi restart. |
| Restart đọc sai dữ liệu | File hoặc tập dữ liệu nguồn thay đổi. | Giữ input bất biến, dùng batch ID/version/snapshot. |
| Nhiều worker retry cùng lúc gây quá tải | Không có backoff/jitter hoặc concurrency quá cao. | Giới hạn worker, tăng backoff và kiểm soát tải downstream. |
| RetryTemplate và step retry chồng nhau | Hai tầng retry cùng thực hiện mà không tính tổng attempt. | Chọn một tầng retry chính hoặc tính rõ số lần gọi tổng thể. |

## 18. Quy trình vận hành khi retry hết

Khi một step thất bại sau retry exhaustion, người vận hành có thể theo trình tự:

1. **Xác định execution:** tìm JobExecution, StepExecution và partition liên quan.
2. **Đọc lỗi cuối cùng:** kiểm tra exception, cause chain, số lần thử và thời điểm xảy ra.
3. **Phân loại lỗi:** transient, lỗi dữ liệu, lỗi cấu hình hay lỗi hệ thống.
4. **Kiểm tra transaction:** xác định chunk nào đã commit, chunk nào rollback và tác dụng phụ ngoài transaction nào có thể đã xảy ra.
5. **Kiểm tra recovery path:** item đã được skip, lưu rejected hay step đã thất bại hoàn toàn?
6. **Khắc phục nguyên nhân:** sửa dữ liệu, khôi phục dịch vụ, tối ưu truy vấn hoặc giải phóng lock.
7. **Chọn cách tiếp tục:** xử lý rejected item riêng, restart cùng JobInstance hoặc tạo batch mới theo nghiệp vụ.
8. **Kiểm tra idempotency:** bảo đảm ghi database và gọi API không tạo kết quả trùng.
9. **Theo dõi execution tiếp theo:** xác nhận trạng thái, counter, dữ liệu đầu ra và danh sách lỗi.
10. **Lưu audit:** giữ lịch sử lỗi ban đầu và kết quả recovery để có thể đối soát.

Không nên tăng `retryLimit` hoặc `skipLimit` chỉ để job chạy qua. Nếu nguyên nhân không được giải quyết, tăng giới hạn thường chỉ kéo dài thời gian lỗi và có thể làm dữ liệu đầu ra khó tin cậy hơn.

## 19. Những điểm cần ghi nhớ

- Retry exhaustion xảy ra khi thao tác vẫn thất bại sau số lần thử được cho phép.
- Sau retry exhaustion, Spring Batch áp dụng skip policy; item có thể bị skip nếu exception được phép và giới hạn còn lại, nếu không step thất bại.
- Retry policy quyết định có thử lại hay không; skip policy quyết định có thể bỏ qua item sau lỗi hay không.
- Chỉ skip lỗi item mà nghiệp vụ chấp nhận loại bỏ và có cơ chế ghi nhận/đối soát.
- Dùng `SkipListener` để lưu chi tiết item bị skip; counter `StepExecution` chỉ cung cấp số lượng tổng hợp.
- Dead-letter/rejected store là cơ chế do ứng dụng thiết kế, không tự xuất hiện chỉ vì cấu hình retry.
- `RetryListener` hỗ trợ quan sát retry; `RecoveryCallback` của Spring Retry có thể định nghĩa hành động sau khi retry policy hết attempt.
- Với lỗi không thể skip, để step thất bại và restart sau khi khắc phục là một recovery path hợp lệ.
- Restart dùng cùng identifying JobParameters để tiếp tục cùng JobInstance; không thêm ID mới ngoài ý muốn.
- Reader cần checkpoint, processor cần deterministic và writer cần idempotent để recovery an toàn.
- Gọi API ngoài cần idempotency key ổn định, outbox hoặc cơ chế đối soát khi kết quả timeout không rõ ràng.
- Trong partitioning, mỗi worker có trạng thái riêng; partition đã commit không tự rollback khi partition khác thất bại.
- Backoff và giới hạn concurrency giúp tránh retry storm khi hệ thống downstream đang quá tải.

Recovery sau retry hết là quyết định về tính đúng đắn của dữ liệu, không chỉ là cách để job tiếp tục chạy. Hãy xác định rõ lỗi nào được retry, lỗi nào có thể skip, khi nào cần cách ly item và khi nào phải dừng để restart sau khi khắc phục. Khi các nhánh này được thiết kế cùng với checkpoint, transaction và idempotency, Spring Batch có thể phục hồi có kiểm soát mà vẫn giữ được khả năng truy vết và đối soát.
