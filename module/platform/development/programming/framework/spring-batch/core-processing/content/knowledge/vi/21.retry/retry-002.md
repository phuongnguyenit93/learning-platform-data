# RetryPolicy

`RetryPolicy` là chính sách quyết định một thao tác có được thử lại sau khi phát sinh exception hay không và khi nào phải dừng retry. Trong Spring Batch, retry policy được dùng ở fault-tolerant chunk step để kiểm soát cách xử lý lỗi tạm thời trong reader, processor hoặc writer.

Thay vì chỉ khai báo một giới hạn retry đơn giản, `RetryPolicy` cho phép mô tả quy tắc phong phú hơn: exception nào được retry, exception nào phải dừng ngay, số lần thử tối đa, cách phân loại exception lồng trong cause và cách theo dõi trạng thái retry. Chính sách retry nên phản ánh khả năng lỗi tự biến mất và tính an toàn khi thực hiện lại thao tác.

## 1. RetryPolicy quyết định điều gì?

Khi một thao tác trong step ném exception, Spring Batch cần quyết định có thử lại thao tác đó hay chuyển sang recovery. `RetryPolicy` trả lời câu hỏi liệu retry còn được phép hay không dựa trên retry context và exception đã ghi nhận.

```text
Thao tác trong chunk
        |
        v
     Exception
        |
        v
     RetryPolicy
        |
        +-- còn được retry --> thử lại thao tác
        |
        +-- không retry nữa --> recovery
                                  |
                                  +-- skip nếu exception skippable
                                  |   và skip limit còn cho phép
                                  |
                                  +-- nếu không --> step FAILED
```

`RetryPolicy` không tự ghi dữ liệu, không sửa item và không quyết định item có được skip hay không. Nó chỉ kiểm soát retry. Sau khi retry không còn được phép, skip policy hoặc cơ chế lỗi mặc định của step sẽ quyết định bước tiếp theo.

## 2. RetryPolicy trong hệ sinh thái Spring Batch

Trong Spring Batch 5, fault-tolerant step tích hợp cơ chế retry của Spring Retry. Interface thường dùng là `org.springframework.retry.RetryPolicy`; các implementation nằm trong package `org.springframework.retry.policy`.

`RetryPolicy` được Spring Retry sử dụng bên trong retry operation. Nó quản lý retry context, ghi nhận exception và xác định còn được thử lại hay không. Spring Batch cung cấp API trên `FaultTolerantStepBuilder` để gắn policy vào chunk step.

Ví dụ import:

```java
import org.springframework.retry.RetryPolicy;
import org.springframework.retry.policy.SimpleRetryPolicy;
import org.springframework.batch.core.step.builder.StepBuilder;
```

Để dùng các policy của Spring Retry, ứng dụng cần có dependency Spring Retry tương thích với phiên bản Spring Batch/Spring Framework đang sử dụng. Với Spring Boot, hãy để dependency management của phiên bản Boot quản lý phiên bản tương ứng thay vì tự ghim một phiên bản không tương thích.

## 3. Cấu hình RetryPolicy cho chunk step

Có thể tạo một `RetryPolicy` bean rồi truyền vào `.retryPolicy(...)` của step builder.

```java
@Bean
RetryPolicy orderRetryPolicy() {
    Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();
    retryable.put(TransientDataAccessException.class, true);
    retryable.put(TransientPartnerException.class, true);
    retryable.put(InvalidOrderException.class, false);

    return new SimpleRetryPolicy(4, retryable, true);
}

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer,
        RetryPolicy orderRetryPolicy) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retryPolicy(orderRetryPolicy)
        .build();
}
```

Trong ví dụ này, lỗi truy cập dữ liệu tạm thời và lỗi đối tác được retry. `InvalidOrderException` bị phân loại không retry. Đối số `4` của `SimpleRetryPolicy` là số lần thực thi tối đa tính cả lần gọi đầu tiên: tối đa một lần ban đầu và ba lần thử lại. Tham số `true` yêu cầu policy xem xét cả chuỗi cause khi phân loại exception.

Khi dùng `.retryPolicy(...)`, hãy cấu hình đầy đủ quy tắc exception và giới hạn ngay trong policy. Không nên đồng thời kỳ vọng các lời gọi `.retry(...)` hoặc `.retryLimit(...)` bổ sung quy tắc vào một policy tùy chỉnh; hãy chọn một cách cấu hình rõ ràng và kiểm tra API của phiên bản Spring Batch đang dùng.

## 4. SimpleRetryPolicy

`SimpleRetryPolicy` là implementation phổ biến khi cần một số lần thử tối đa và một bản đồ exception được retry hay không.

Các thành phần chính:

- `maxAttempts`: số lần thực thi tối đa, bao gồm lần đầu tiên.
- `retryableExceptions`: map từ exception class sang boolean cho biết exception đó có thể retry hay không.
- `traverseCauses`: cho phép phân loại exception dựa trên các cause lồng bên trong.

Ví dụ:

```java
Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();
retryable.put(DeadlockLoserDataAccessException.class, true);
retryable.put(SocketTimeoutException.class, true);
retryable.put(InvalidCustomerException.class, false);

RetryPolicy policy = new SimpleRetryPolicy(5, retryable, true);
```

Với cấu hình này, một exception được phân loại retryable có thể được thử tối đa năm lần tổng cộng. Khi lần thử thứ năm vẫn thất bại, policy không cho phép lần tiếp theo.

`SimpleRetryPolicy` phù hợp khi quy tắc có thể mô tả bằng số lần thử và phân loại exception. Nếu cần giới hạn theo thời gian, phân loại động hoặc kết hợp nhiều điều kiện, hãy cân nhắc policy khác hoặc policy tùy chỉnh.

## 5. Exception classification

Không phải exception nào cũng nên được retry. Một policy tốt phân biệt lỗi tạm thời với lỗi cố định:

| Exception | Ví dụ | Phân loại thường phù hợp |
|---|---|---|
| `TransientDataAccessException` | Deadlock hoặc lỗi database tạm thời | Retry có giới hạn |
| `SocketTimeoutException` | Kết nối đối tác timeout | Retry nếu thao tác an toàn khi gọi lại |
| `TransientPartnerException` | Dịch vụ ngoài tạm thời không khả dụng | Retry có backoff |
| `InvalidOrderException` | Đơn hàng thiếu trường bắt buộc | Không retry; có thể skip hoặc fail |
| `AuthenticationException` | Credential hết hạn hoặc sai | Không retry mù quáng; xử lý cấu hình/credential |
| `NullPointerException` | Lỗi lập trình | Không retry; cần sửa code |

Ví dụ policy không nên retry lỗi dữ liệu:

```java
Map<Class<? extends Throwable>, Boolean> retryable = new HashMap<>();
retryable.put(TransientPartnerException.class, true);
retryable.put(InvalidOrderException.class, false);

RetryPolicy policy = new SimpleRetryPolicy(4, retryable, true);
```

Khi phân loại theo superclass, cần chú ý quan hệ kế thừa. Nếu một superclass được đánh dấu retryable, các subclass có thể được phân loại theo quy tắc tìm kiếm exception của policy. Kiểm tra thứ tự/độ ưu tiên và test các exception thực tế, nhất là khi framework bọc exception gốc trong một exception khác.

## 6. Cause traversal và exception wrapping

Trong ứng dụng Spring, exception gốc thường được bọc qua nhiều lớp. Ví dụ một lỗi socket có thể được bọc thành `ResourceAccessException`, rồi thành exception nghiệp vụ của adapter.

```text
TransientPartnerException
        caused by
ResourceAccessException
        caused by
SocketTimeoutException
```

Nếu chỉ phân loại exception ngoài cùng, policy có thể không nhận ra lỗi gốc là timeout. `SimpleRetryPolicy` có tùy chọn `traverseCauses` để xem xét cause chain khi phân loại.

```java
RetryPolicy policy = new SimpleRetryPolicy(
    4,
    retryableExceptions,
    true // xét cả cause chain
);
```

Chỉ bật cause traversal khi các exception cause được phân loại có chủ đích. Không nên retry mọi exception chỉ vì ở sâu trong cause chain có một loại lỗi chung; cần kiểm tra cách adapter bọc lỗi để tránh retry nhầm lỗi nghiệp vụ hoặc lỗi cấu hình.

## 7. ExceptionClassifierRetryPolicy

Khi mỗi nhóm exception cần một policy khác nhau, có thể dùng `ExceptionClassifierRetryPolicy`. Policy này chọn retry policy dựa trên loại exception hiện tại.

Ví dụ ý tưởng: lỗi deadlock có số lần thử và backoff riêng, lỗi timeout đối tác có giới hạn khác, còn lỗi validation không được retry.

```java
Map<Class<? extends Throwable>, RetryPolicy> policies = new HashMap<>();
policies.put(
    DeadlockLoserDataAccessException.class,
    new SimpleRetryPolicy(5)
);
policies.put(
    TransientPartnerException.class,
    new SimpleRetryPolicy(3)
);
policies.put(
    InvalidOrderException.class,
    new NeverRetryPolicy()
);

ExceptionClassifierRetryPolicy policy = new ExceptionClassifierRetryPolicy();
policy.setPolicyMap(policies);
```

Đoạn code minh họa cách ánh xạ exception sang policy cụ thể; trong ứng dụng thực tế cần cấu hình policy mặc định cho loại exception không có trong map và xác nhận classifier xử lý subclass/cause theo đúng mong muốn.

`ExceptionClassifierRetryPolicy` hữu ích khi một job gọi nhiều hệ thống phụ thuộc có đặc tính lỗi khác nhau. Tuy nhiên, map policy cần được giữ ngắn gọn và có tên exception rõ ràng; nếu quy tắc trở nên quá phức tạp, hãy tách việc phân loại lỗi ở adapter/service trước khi exception đến batch layer.

## 8. NeverRetryPolicy và AlwaysRetryPolicy

Spring Retry cung cấp policy cho hai hành vi biên:

- `NeverRetryPolicy`: không cho phép thử lại sau lần thực hiện ban đầu.
- `AlwaysRetryPolicy`: luôn cho phép retry; cần kết hợp với cơ chế giới hạn khác nếu không muốn retry vô hạn.

`NeverRetryPolicy` phù hợp với lỗi dữ liệu cố định hoặc thao tác không an toàn khi gọi lại. `AlwaysRetryPolicy` cần được dùng rất thận trọng vì nếu không có điều kiện dừng khác, retry có thể kéo dài vô hạn.

```java
RetryPolicy noRetry = new NeverRetryPolicy();
```

Trong batch production, thường nên ưu tiên policy có giới hạn rõ ràng thay vì `AlwaysRetryPolicy`. Một dịch vụ đang ngừng hoạt động không nên bị gọi liên tục vô hạn bởi nhiều worker.

## 9. TimeoutRetryPolicy

`TimeoutRetryPolicy` giới hạn retry theo khoảng thời gian thay vì chỉ số lần thử. Nó có thể hữu ích khi thời gian phục hồi của hệ thống quan trọng hơn số attempt cố định.

Ví dụ:

```java
TimeoutRetryPolicy policy = new TimeoutRetryPolicy();
policy.setTimeout(10_000L); // milliseconds
```

Policy timeout không thay thế timeout của HTTP client, JDBC driver hoặc transaction manager. Nếu một lần gọi bị treo lâu, policy retry không thể tự ngắt lời gọi đó chỉ vì thời gian tổng đã vượt ngưỡng. Cần cấu hình timeout ở tầng I/O để mỗi attempt kết thúc trong khoảng thời gian hữu hạn.

Khi kết hợp timeout policy với backoff, hãy tính tổng thời gian chờ và thời gian thực thi của từng attempt để bảo đảm phù hợp deadline của job.

## 10. RetryPolicy và BackOffPolicy là hai trách nhiệm riêng

`RetryPolicy` quyết định có được retry hay không. `BackOffPolicy` quyết định phải chờ bao lâu trước lần thử tiếp theo. Hai chính sách phối hợp nhưng không thay thế nhau.

```text
Exception
   |
   v
RetryPolicy: còn attempt?
   |
   +-- Không --> recovery
   |
   +-- Có
       |
       v
BackOffPolicy: chờ bao lâu?
       |
       v
Thực hiện lại thao tác
```

Ví dụ cấu hình exponential backoff:

```java
ExponentialBackOffPolicy backOff = new ExponentialBackOffPolicy();
backOff.setInitialInterval(500L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(5_000L);

return new StepBuilder("callPartner", jobRepository)
    .<Request, Response>chunk(20, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retryPolicy(retryPolicy)
    .backOffPolicy(backOff)
    .build();
```

Khoảng chờ tăng từ 500 ms theo hệ số 2 và không vượt 5 giây. Giá trị cần được chọn theo SLA, timeout của client và giới hạn tải của hệ thống phụ thuộc. Với API có trả `Retry-After`, có thể cần backoff policy tùy chỉnh để tôn trọng thời gian server yêu cầu.

## 11. RetryContext và trạng thái retry

Spring Retry dùng `RetryContext` để lưu thông tin của một chuỗi retry, chẳng hạn số lần retry và exception gần nhất. `RetryPolicy` tạo hoặc sử dụng context, ghi nhận exception và quyết định liệu thao tác còn được thử lại hay không.

`RetryContext` khác với Spring Batch `ExecutionContext`:

| Context | Mục đích | Vòng đời |
|---|---|---|
| `RetryContext` | Theo dõi trạng thái của một lần retry | Gắn với retry operation và retry mechanism |
| Step `ExecutionContext` | Lưu checkpoint của step để restart | Được lưu trong JobRepository theo step execution |
| Job `ExecutionContext` | Chia sẻ state cần thiết giữa các step trong job execution | Được lưu trong JobRepository theo job execution |

Không dùng `RetryContext` làm nơi lưu checkpoint bền vững của job. Khi tiến trình JVM dừng, retry context thông thường không thay thế được metadata và state cần thiết để restart.

## 12. Stateless và stateful retry

Với stateless retry, retry được thực hiện trong cùng ngữ cảnh xử lý của thao tác. Với stateful retry, trạng thái retry được liên kết với một item có key ổn định để có thể nhận diện cùng item qua các lần rollback/recovery.

Trong batch, stateful retry có thể hữu ích khi transaction rollback khiến chunk được đưa lại qua recovery và framework cần nhớ số lần thử của item. Để làm được điều đó, item cần một định danh ổn định; nếu không, mỗi lần đọc lại có thể bị xem như một item mới.

Các lưu ý:

- Chọn key từ định danh nghiệp vụ ổn định, không dùng `hashCode()` của object mutable.
- Đảm bảo hai item khác nhau không dùng cùng retry key.
- Xác định retry context cache được giữ ở đâu và thời điểm được dọn.
- Không nhầm retry state với checkpoint restart trong `ExecutionContext`.
- Kiểm thử retry qua rollback, skip và nhiều chunk.

Stateful retry không bảo đảm thao tác bên ngoài chỉ xảy ra một lần. Writer/processor vẫn cần idempotency cho side effect không thuộc transaction.

## 13. RetryPolicy, skip policy và rollback

Ba cơ chế có vai trò riêng:

| Cơ chế | Câu hỏi |
|---|---|
| `RetryPolicy` | Có được thử lại sau exception này không? |
| Skip policy | Nếu không tiếp tục retry, item có được phép loại bỏ không? |
| Rollback classification | Exception này có làm transaction hiện tại rollback không? |

Ví dụ một item gặp timeout từ dịch vụ đối tác:

1. `RetryPolicy` cho phép thử lại.
2. Spring Retry thực hiện backoff nếu được cấu hình.
3. Nếu một lần thử thành công, item tiếp tục qua pipeline.
4. Nếu retry hết giới hạn, skip policy được xem xét.
5. Nếu exception không skippable, step thất bại.

Chunk có thể rollback trong quá trình retry/recovery tùy giai đoạn lỗi và transaction semantics. Một exception được phép retry không có nghĩa transaction không rollback. Tương tự, một exception được skip vẫn có thể làm chunk rollback trước khi item được cô lập.

## 14. Khi nào RetryPolicy được dùng trong chunk?

Retry có thể xảy ra khi lỗi phát sinh ở reader, processor hoặc writer, miễn là step được cấu hình fault tolerance và exception được policy nhận diện.

| Giai đoạn | Ví dụ | Lưu ý thiết kế |
|---|---|---|
| Read | Timeout khi đọc dữ liệu từ nguồn từ xa | Reader phải có cách khôi phục vị trí đọc phù hợp |
| Process | Timeout khi gọi dịch vụ làm giàu dữ liệu | Tránh side effect không idempotent trong processor |
| Write | Deadlock hoặc lỗi kết nối khi ghi | Writer có thể được gọi lại; dùng unique key/upsert/idempotency |

Không nên retry lỗi parse dữ liệu cố định hoặc lỗi mapping do code sai. Nếu một exception cho thấy hợp đồng nguồn đã thay đổi, retry nhiều lần chỉ làm job chậm hơn và che giấu vấn đề.

## 15. Policy tùy chỉnh

Khi các implementation có sẵn không thể mô tả quy tắc cần thiết, có thể triển khai `RetryPolicy` riêng. Policy cần quản lý retry context nhất quán và phải có điều kiện dừng rõ ràng.

Các trách nhiệm cơ bản của một policy gồm:

- Tạo context khi bắt đầu một retry operation.
- Kiểm tra context và quyết định còn được retry không.
- Ghi nhận exception vừa phát sinh.
- Dọn tài nguyên hoặc trạng thái khi retry operation kết thúc.

Không nên triển khai custom policy chỉ để kiểm tra một exception class hoặc giới hạn attempt đơn giản; `SimpleRetryPolicy` thường đủ. Custom policy phù hợp hơn khi quyết định phụ thuộc vào trạng thái nghiệp vụ, deadline hoặc một quy tắc phân loại chuyên biệt.

Khi policy dựa trên dịch vụ ngoài hoặc dữ liệu thay đổi theo thời gian, hãy bảo đảm quyết định retry có thể dự đoán và không tạo tải phụ quá lớn. Tránh gọi một API mạng trong mỗi lần `canRetry` nếu không có cache/timeout phù hợp.

## 16. Retry key và RetryContextCache

Trong stateful retry, retry mechanism cần liên kết các lần thử của cùng item. Retry key phải ổn định trong suốt quá trình recovery.

Ví dụ key theo mã đơn hàng:

```java
public record OrderRow(String orderId, BigDecimal total) {
}

// Key logic minh họa: orderId phải duy nhất trong phạm vi job.
String retryKey(OrderRow row) {
    return row.orderId();
}
```

Với retry context cache, cần giới hạn dung lượng và thời gian giữ state. Nếu cache không được dọn đúng lúc, job dài có thể tăng bộ nhớ. Nếu key va chạm, trạng thái retry của hai item có thể bị trộn.

Trong Spring Batch, cấu hình key generator hoặc retry context cache chỉ nên được thêm khi retry behavior cần stateful và đã xác định rõ semantics của item. Đối với hầu hết lỗi tạm thời đơn giản, policy stateless có giới hạn dễ vận hành hơn.

## 17. RetryPolicy không thay thế timeout và circuit breaker

Retry policy kiểm soát số lần thử lại, nhưng không tự giới hạn thời gian của mỗi lời gọi I/O. Một HTTP call không có timeout có thể treo lâu dù retry policy chỉ cho phép một attempt.

Retry cũng có thể làm một dịch vụ đang quá tải nhận thêm request. Với hệ thống phụ thuộc có tỷ lệ lỗi cao, có thể cần circuit breaker để tạm ngừng gọi trong một khoảng thời gian, kết hợp timeout, backoff và giới hạn concurrency.

| Cơ chế | Trách nhiệm |
|---|---|
| Timeout | Giới hạn thời gian một lần gọi |
| RetryPolicy | Quyết định có thử lại hay không |
| BackOffPolicy | Chờ bao lâu giữa các lần thử |
| Circuit breaker | Tạm ngăn lời gọi khi hệ thống phụ thuộc có dấu hiệu lỗi diện rộng |
| Rate limiter/bulkhead | Giới hạn tốc độ hoặc số lời gọi đồng thời |

Không nên retry mọi lỗi mạng liên tục trong nhiều worker. Tổng số request retry có thể lớn hơn nhiều so với số item, gây hiệu ứng khuếch đại tải.

## 18. Những lỗi thường gặp khi dùng RetryPolicy

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Retry mọi `Exception` | Lỗi dữ liệu và lỗi cấu hình bị thử lại không cần thiết | Phân loại exception cụ thể |
| Nhầm `maxAttempts` với số lần retry bổ sung | Số lần gọi thực tế khác mong đợi | Nhớ `SimpleRetryPolicy.maxAttempts` tính cả lần đầu |
| Không xét cause chain | Exception bị bọc không được nhận diện là retryable | Cấu hình cause traversal có chủ đích |
| Dùng policy vô hạn | Job có thể không kết thúc | Dùng giới hạn attempt hoặc timeout |
| Không cấu hình backoff | Retry dồn dập làm dịch vụ phụ thuộc quá tải | Kết hợp BackOffPolicy |
| Dùng retry thay cho validation | Dữ liệu sai bị thử lại nhiều lần | Validate và skip/fail theo nghiệp vụ |
| Nhầm RetryContext với ExecutionContext | Mong retry state tồn tại qua restart JVM | Lưu checkpoint cần thiết vào ExecutionContext |
| Writer/processor có side effect không idempotent | Retry gây ghi trùng hoặc thao tác lặp | Dùng idempotency key, outbox hoặc compensation |
| Policy tùy chỉnh không có điều kiện dừng | Step bị kẹt trong retry | Thiết kế deadline/attempt limit và kiểm thử |

## 19. Kiểm thử RetryPolicy

Policy nên được kiểm thử độc lập và thông qua một step thực tế. Với `SimpleRetryPolicy`, kiểm tra cả exception retryable, non-retryable và exception bị bọc.

Các trường hợp nên có:

1. Exception retryable: policy cho phép retry đến đúng giới hạn.
2. Exception non-retryable: policy dừng ngay sau lần đầu.
3. Cause chain chứa exception retryable: policy phân loại đúng khi bật traversal.
4. Số attempt tối đa: xác nhận `maxAttempts` bao gồm lần thực thi đầu tiên.
5. Exception retryable rồi thành công: step hoàn tất và không skip item.
6. Retry hết giới hạn: item được skip nếu policy cho phép, nếu không step thất bại.
7. Backoff: xác nhận khoảng chờ không vượt cấu hình.
8. Stateful retry: cùng item dùng cùng key và state được dọn sau recovery.
9. Restart: checkpoint được khôi phục từ JobRepository; không dựa vào RetryContext cũ.
10. Writer retry: không tạo dữ liệu hoặc side effect trùng.

Ví dụ kiểm thử đơn giản với `SimpleRetryPolicy` có thể xác nhận số lần retry tối đa thông qua một `RetryTemplate` hoặc integration test của step. Với Spring Batch, nên kiểm tra thêm `StepExecution` status, retry/skip count và dữ liệu transaction sau recovery.

## 20. Quy trình chọn RetryPolicy cho production

Khi thiết kế retry cho một step, hãy làm rõ:

1. Exception nào thực sự tạm thời và có khả năng thành công khi thử lại?
2. Exception nào phải fail ngay hoặc được xử lý bằng skip?
3. Số lần thử tối đa tính cả lần đầu là bao nhiêu?
4. Có cần phân loại theo cause chain hoặc exception hierarchy không?
5. Backoff và timeout của mỗi lần gọi có phù hợp SLA không?
6. Reader, processor và writer có an toàn khi được gọi lại không?
7. Stateful retry có cần key ổn định hoặc context cache không?
8. Khi hết retry, item được skip hay step phải thất bại?
9. Metric nào cho biết retry đang tăng và dịch vụ phụ thuộc đang suy giảm?
10. Integration test có mô phỏng rollback, retry, skip và restart không?

Bắt đầu với policy đơn giản, giới hạn rõ ràng và danh sách exception ngắn. Chỉ thêm classifier hoặc custom policy khi có yêu cầu cụ thể mà cấu hình cơ bản không diễn đạt được.

## Kết luận

`RetryPolicy` quyết định một thao tác có thể được thử lại hay không sau exception và khi nào retry phải dừng. Trong Spring Batch 5, có thể gắn policy của Spring Retry vào fault-tolerant chunk step bằng `.retryPolicy(...)`. `SimpleRetryPolicy` phù hợp với giới hạn attempt và exception classification; các policy phân loại hoặc tùy chỉnh phù hợp khi mỗi nhóm lỗi cần quy tắc khác nhau.

Giữ riêng trách nhiệm giữa RetryPolicy, BackOffPolicy, skip policy và rollback classification. Chỉ retry lỗi tạm thời, đặt giới hạn hữu hạn, xét cause chain có chủ đích và bảo đảm thao tác an toàn khi gọi lại. RetryContext theo dõi lần thử, còn ExecutionContext lưu checkpoint để restart; hai loại state này không thay thế nhau.
