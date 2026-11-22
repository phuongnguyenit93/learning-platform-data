# Retry limit

Trong Spring Batch, retry limit quy định số lần framework được phép thử lại một thao tác khi gặp exception thuộc nhóm có thể retry. Retry hữu ích với lỗi tạm thời như deadlock, timeout hoặc dịch vụ phụ thuộc chập chờn. Sau một số lần thử giới hạn, nếu thao tác vẫn thất bại, Spring Batch chuyển sang bước xử lý tiếp theo theo cấu hình skip hoặc đánh dấu step thất bại.

Retry limit giúp tránh việc một item lỗi khiến job dừng ngay lập tức, đồng thời ngăn hệ thống thử vô hạn và tiêu tốn tài nguyên. Để dùng đúng, cần hiểu giới hạn này áp dụng cho lần thử lại của item, loại exception nào được phép retry, điều gì xảy ra khi hết giới hạn và cách retry tương tác với transaction, skip và restart.

## 1. Retry limit là gì?

Trong chunk-oriented step, reader lấy item, processor xử lý item và writer ghi nhóm item. Nếu một thao tác ném exception được phân loại là retryable, Spring Batch có thể thử lại theo retry policy của step.

`retryLimit(n)` đặt giới hạn số lần retry cho lỗi đã được khai báo bằng `retry(...)`. Lần thực hiện ban đầu vẫn xảy ra trước khi retry. Ví dụ `retryLimit(3)` cho phép tối đa ba lần thử lại sau lần đầu theo cách diễn giải của cấu hình retry trong Spring Batch.

```text
Lần thực hiện ban đầu
       |
       +-- thành công --> tiếp tục
       |
       +-- exception retryable
                 |
                 v
             Retry #1
                 |
                 +-- thành công --> tiếp tục
                 |
                 +-- thất bại --> Retry #2
                                  |
                                  +-- thành công --> tiếp tục
                                  |
                                  +-- thất bại --> Retry #3
                                                   |
                                                   +-- thành công --> tiếp tục
                                                   |
                                                   +-- thất bại --> hết retry
                                                                    |
                                                                    v
                                                        áp dụng skip hoặc fail
```

Điểm cần nhớ: retry limit không phải số lần chạy lại toàn bộ job, cũng không phải số lần step được khởi chạy. Nó là giới hạn retry của thao tác/item theo retry policy trong step fault-tolerant.

## 2. Cấu hình retryLimit trong Spring Batch 5

Để bật retry, chunk step cần được cấu hình fault tolerant. Sau đó khai báo số lần retry và loại exception được phép retry.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientPartnerException.class)
        .retryLimit(3)
        .build();
}
```

Trong ví dụ này, chỉ `TransientPartnerException` được chỉ định là có thể retry. Nếu exception khác xuất hiện, nó không tự động được retry chỉ vì step có `.faultTolerant()`.

`retryLimit(3)` giới hạn số lần thử lại cho một lỗi/item theo retry policy. Khi retry vẫn không thành công sau giới hạn, exception tiếp tục được xử lý theo skip policy nếu exception cũng được phép skip; nếu không, step thất bại.

## 3. Chọn đúng exception để retry

Retry chỉ hữu ích khi có khả năng lần thử tiếp theo thành công mà không cần thay đổi dữ liệu đầu vào hoặc code. Vì vậy, chỉ nên retry lỗi có tính tạm thời.

| Loại exception | Ví dụ | Hướng xử lý thường phù hợp |
|---|---|---|
| Lỗi deadlock hoặc lock contention | Database báo deadlock khi cập nhật | Retry có giới hạn và backoff |
| Timeout tạm thời | Dịch vụ tham chiếu không phản hồi đúng hạn | Retry có giới hạn, timeout và backoff |
| Lỗi kết nối ngắn hạn | Connection reset hoặc lỗi mạng tạm thời | Retry nếu thao tác an toàn để gọi lại |
| Dữ liệu sai định dạng | Thiếu trường bắt buộc, số lượng âm | Validation, skip hoặc fail theo nghiệp vụ; retry thường không giúp |
| Lỗi cấu hình | Sai URL, thiếu credential, sai schema | Fail nhanh để sửa cấu hình |
| Lỗi lập trình | NullPointerException, mapping sai | Fail để điều tra; không retry mù quáng |

Ví dụ, nếu processor luôn ném `InvalidOrderException` vì quantity bằng 0, gọi lại processor ba lần vẫn nhận cùng dữ liệu sai. Retry chỉ kéo dài thời gian xử lý mà không cải thiện kết quả.

Ngược lại, nếu writer gặp lỗi deadlock khi cập nhật một bản ghi, lần thử lại sau khi transaction rollback có thể thành công khi transaction khác đã giải phóng lock.

## 4. Chỉ định exception được retry

Có thể khai báo nhiều loại exception:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retry(TransientPartnerException.class)
.retryLimit(3)
```

Trong cấu hình này, các exception thuộc những loại đã khai báo được xem là retryable. Nên chọn các loại exception cụ thể hoặc một superclass có ý nghĩa rõ ràng, tránh retry một nhóm quá rộng.

Ví dụ không nên dùng:

```java
// Không nên retry mọi lỗi một cách không phân biệt
.faultTolerant()
.retry(Exception.class)
.retryLimit(10)
```

Retry mọi exception có thể làm chậm việc phát hiện lỗi cấu hình, lỗi dữ liệu và lỗi lập trình. Nó cũng có thể lặp lại thao tác không an toàn hoặc tạo tải lớn hơn cho một dịch vụ đang gặp sự cố.

Khi cần phân loại rõ hơn, hãy tạo exception riêng ở lớp tích hợp, ví dụ `TransientPartnerException` cho lỗi tạm thời từ đối tác và `InvalidPartnerResponseException` cho phản hồi sai hợp đồng. Điều đó giúp retry policy thể hiện chính xác ý nghĩa nghiệp vụ.

## 5. Điều gì xảy ra khi retry limit bị vượt?

Khi exception retryable tiếp tục xảy ra và retry policy đã hết số lần cho phép, Spring Batch không tiếp tục thử vô hạn. Framework chuyển sang recovery path của chunk.

Có hai tình huống chính:

- Nếu exception cũng được cấu hình là skippable và skip limit còn cho phép, item có thể bị skip và step tiếp tục.
- Nếu exception không được phép skip, hoặc skip limit đã bị vượt, step thất bại.

Ví dụ retry rồi skip:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderRow, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientPartnerException.class)
    .retryLimit(3)
    .skip(TransientPartnerException.class)
    .skipLimit(20)
    .build();
```

Trong ví dụ này, nếu lỗi đối tác không hết sau các lần retry, exception có thể được xử lý như một skip nếu chính sách skip cho phép và giới hạn skip chưa bị vượt. Đây chỉ là lựa chọn phù hợp khi nghiệp vụ chấp nhận loại bỏ item đó và có cơ chế ghi nhận để xử lý sau.

Nếu dữ liệu không được phép bỏ qua, không cấu hình skip cho exception đó. Khi retry hết giới hạn, step sẽ thất bại để tránh báo hoàn thành với dữ liệu thiếu.

## 6. Phân biệt retryLimit và skipLimit

`retryLimit` và `skipLimit` kiểm soát hai điều khác nhau:

| Cấu hình | Câu hỏi | Ý nghĩa |
|---|---|---|
| `retryLimit(n)` | Thử lại lỗi này bao nhiêu lần? | Giới hạn số lần retry theo retry policy |
| `skipLimit(n)` | Cho phép loại bỏ bao nhiêu item lỗi? | Giới hạn tổng số skip của step execution |

Retry cố gắng thực hiện lại thao tác để xử lý item thành công. Skip chấp nhận không xử lý item đó và tiếp tục với item khác.

Ví dụ một item gặp timeout:

1. Lần đầu gọi dịch vụ bị timeout.
2. Spring Batch retry theo giới hạn cấu hình.
3. Nếu lần thử sau thành công, item tiếp tục qua writer và không bị skip.
4. Nếu retry hết giới hạn và exception được phép skip, item có thể bị loại bỏ.
5. Nếu exception không được phép skip, step thất bại.

Không nên đặt skip limit cao để bù cho retry policy thiếu chính xác. Hãy quyết định riêng lỗi nào có thể thử lại và lỗi nào có thể loại bỏ.

## 7. Retry khác restart job

Retry xảy ra trong quá trình xử lý một step execution để thử lại thao tác/item bị lỗi. Restart tạo một `JobExecution` mới cho cùng `JobInstance` sau khi execution trước thất bại hoặc dừng và được phép restart.

| Cơ chế | Phạm vi | Mục đích |
|---|---|---|
| Retry | Một thao tác/item trong step fault-tolerant | Khắc phục lỗi tạm thời ngay trong execution hiện tại |
| Restart | JobInstance đã thất bại hoặc dừng | Tiếp tục job từ metadata/checkpoint đã lưu |
| `startLimit` | Số lần step được phép bắt đầu | Giới hạn số lần khởi chạy step |
| `JobParametersIncrementer` | Tạo parameters cho instance tiếp theo | Tạo JobInstance mới |

Không tăng `run.id` chỉ để vượt retry limit. Làm vậy tạo JobInstance mới, không tiếp tục cùng checkpoint và có thể xử lý lại dữ liệu đã commit.

## 8. Retry và transaction rollback

Trong chunk-oriented step, mỗi chunk được xử lý trong transaction. Khi lỗi xảy ra trong reader, processor hoặc writer, Spring Batch có thể rollback transaction chunk trước khi recovery/retry tùy loại exception và cấu hình.

```text
Chunk transaction bắt đầu
        |
        v
Processor hoặc Writer
        |
        +-- thành công --> commit chunk
        |
        +-- lỗi retryable
                 |
                 v
            rollback/recovery
                 |
                 v
             thử lại theo policy
                 |
                 +-- thành công --> tiếp tục commit
                 |
                 +-- hết retry --> skip hoặc fail
```

Chi tiết số lần reader/processor/writer được gọi lại phụ thuộc giai đoạn lỗi, retry policy, skip policy và cơ chế recovery của step. Không nên giả định mỗi item chỉ được đọc hoặc xử lý đúng một lần.

Các thay đổi trong transaction database của chunk có thể rollback nếu transaction manager quản lý đúng datasource. Side effect ngoài transaction như gửi email, gọi HTTP API hoặc publish message không tự động được rollback.

## 9. Retry khi writer ghi cả chunk

Writer nhận một nhóm item cùng lúc. Nếu writer ném exception, framework có thể cần khôi phục và xác định item gây lỗi, đặc biệt khi kết hợp retry với skip. Vì thế, một writer call có thể được thực hiện lại cho cùng chunk hoặc các phần của chunk tùy cơ chế fault tolerance.

Điều này ảnh hưởng đến thiết kế writer:

- Các lệnh ghi cần an toàn khi được gọi lại.
- Không nuốt exception để giả vờ chunk thành công.
- Dùng khóa duy nhất, upsert hoặc idempotency key khi có khả năng ghi trùng.
- Tránh gọi API ngoài không idempotent trong writer nếu thao tác có thể được retry.
- Nếu writer thực hiện nhiều side effect, xác định cách phục hồi khi chỉ một phần thao tác thành công.

Không nên dựa vào retry limit để bảo đảm exactly-once. Retry chỉ điều khiển số lần thử; tính idempotent của thao tác ghi vẫn là trách nhiệm của thiết kế dữ liệu và tích hợp.

## 10. Cấu hình backoff giữa các lần retry

Retry liên tục không có khoảng nghỉ có thể làm hệ thống phụ thuộc quá tải hơn, nhất là khi dịch vụ ngoài đang gặp sự cố. Backoff thêm khoảng chờ giữa các lần thử.

Ví dụ cấu hình exponential backoff:

```java
ExponentialBackOffPolicy backOffPolicy = new ExponentialBackOffPolicy();
backOffPolicy.setInitialInterval(500L);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(5000L);

return new StepBuilder("callPartnerStep", jobRepository)
    .<Request, Response>chunk(20, transactionManager)
    .reader(requestReader)
    .processor(partnerProcessor)
    .writer(responseWriter)
    .faultTolerant()
    .retry(TransientPartnerException.class)
    .retryLimit(3)
    .backOffPolicy(backOffPolicy)
    .build();
```

Với các giá trị trên, khoảng chờ bắt đầu ở 500 ms, tăng theo hệ số 2 và bị giới hạn tối đa 5 giây. Thời gian thực tế của toàn bộ job còn phụ thuộc số lần retry, thời gian mỗi request và số item lỗi.

Backoff cần phối hợp với timeout của client, transaction timeout và deadline của job. Không nên giữ transaction hoặc connection mở trong thời gian chờ dài nếu thao tác có thể được tổ chức lại để tránh điều đó.

## 11. Retry có thể cần giới hạn theo loại lỗi

Trong ứng dụng thực tế, một số lỗi chỉ nên retry một hoặc hai lần, trong khi lỗi khác có thể được thử nhiều lần hơn. Có thể dùng retry policy tùy chỉnh hoặc exception classifier để biểu diễn chính sách phức tạp.

Ví dụ về quy tắc:

| Exception | Retry limit gợi ý | Backoff |
|---|---:|---|
| Deadlock database | 3 | Ngắn, tăng dần |
| Timeout API đối tác | 2–3 | Exponential, có giới hạn |
| Rate limit từ API | Theo `Retry-After` nếu client hỗ trợ | Tôn trọng thời gian server yêu cầu |
| Validation exception | 0 | Không retry |
| Authentication/configuration error | 0 | Fail nhanh và cảnh báo |

Các con số chỉ là ví dụ thiết kế. Hãy chọn theo SLA, đặc tính dịch vụ và khả năng chịu tải; không áp dụng máy móc cho mọi job.

## 12. Stateful và stateless retry

Retry có thể cần giữ thông tin về lần thử trước. Trong xử lý batch, một item có thể được nhận diện bằng key để framework liên kết trạng thái retry qua các lần gọi trong quá trình recovery.

- **Stateless retry:** retry được thực hiện trong cùng ngữ cảnh lời gọi và không cần lưu trạng thái lâu dài theo item ngoài retry context hiện tại.
- **Stateful retry:** trạng thái retry được liên kết với item qua key và có thể tồn tại qua các lần rollback/recovery của chunk trong cùng execution.

Với reader/writer có transaction rollback, stateful retry có thể hữu ích để không lặp vô hạn một item qua các lần khôi phục chunk. Tuy nhiên, item cần có định danh ổn định và retry context cần được quản lý phù hợp. Không nhầm retry context với checkpoint bền vững của `ExecutionContext` hoặc restart JobInstance.

Nếu tự cấu hình retry policy, hãy hiểu rõ retry state được giữ ở đâu, key item có ổn định không và khi nào retry context được xóa. Chính sách tùy chỉnh cần được kiểm thử với rollback và skip thực tế.

## 13. Retry trong processor khác retry trong writer

Retry có thể phát sinh ở các giai đoạn khác nhau:

| Giai đoạn | Ví dụ | Lưu ý |
|---|---|---|
| Read | Lỗi tạm thời khi truy vấn nguồn hoặc đọc file qua mạng | Reader có thể cần hỗ trợ state để phục hồi đúng vị trí |
| Process | Timeout khi gọi dịch vụ làm giàu dữ liệu | Processor nên tránh side effect không idempotent |
| Write | Deadlock hoặc timeout khi ghi database/API | Writer có thể được gọi lại với chunk hoặc item liên quan |

Chọn exception class dựa trên lỗi thực tế ở từng giai đoạn. Đừng retry lỗi parse dữ liệu cố định hoặc lỗi mapping do code sai. Với lỗi đọc file, cần xem reader có thể đọc lại cùng record sau rollback hay không.

## 14. Retry limit và lỗi không thể retry

Khi exception không nằm trong danh sách retry, framework không thử lại theo retry policy đó. Nó được chuyển sang xử lý skip/fail theo cấu hình.

Có thể dùng `noRetry` để loại trừ một exception khỏi retry policy tổng quát:

```java
.faultTolerant()
.retry(TransientDataAccessException.class)
.noRetry(InvalidOrderException.class)
.retryLimit(3)
```

Ví dụ trên biểu thị lỗi dữ liệu không được retry dù một superclass hoặc policy tổng quát có thể nhận diện nó. Hãy kiểm tra quan hệ kế thừa giữa các exception để tránh cấu hình rộng vô tình bao gồm lỗi không phù hợp.

## 15. Theo dõi số lần retry

Retry có thể che đi sự cố tạm thời nếu chỉ quan sát trạng thái cuối cùng. Một job có thể hoàn thành nhưng đã phải retry nhiều lần, báo hiệu database hoặc dịch vụ phụ thuộc đang không ổn định.

Nên theo dõi:

- Số lần retry theo job, step và exception category.
- Số item cuối cùng thành công sau retry.
- Số item hết retry và bị skip.
- Số item hết retry và làm step thất bại.
- Thời gian chờ backoff và tổng thời gian xử lý.
- Tỷ lệ retry theo thời gian để phát hiện xu hướng tăng.

Không nên dùng mã đơn hàng hoặc dữ liệu cá nhân làm label metric có cardinality cao. Log nên chứa JobExecution ID, StepExecution ID và mã định danh an toàn để liên kết các lần thử.

## 16. Các lỗi thường gặp khi cấu hình retry limit

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Retry mọi `Exception` | Lỗi dữ liệu, cấu hình và lập trình bị thử lại không cần thiết | Chỉ retry exception tạm thời đã xác định |
| Đặt retry limit quá cao | Kéo dài job và tăng tải lên hệ thống đang lỗi | Chọn giới hạn theo SLA và backoff |
| Không cấu hình backoff | Retry dồn dập làm dịch vụ quá tải hơn | Dùng backoff có giới hạn cho lỗi phù hợp |
| Cho rằng hết retry thì item tự động bị skip | Step vẫn thất bại nếu exception không skippable | Cấu hình skip riêng nếu nghiệp vụ cho phép |
| Nhầm retry limit với restart limit | Tạo JobInstance mới hoặc restart sai cách | Phân biệt retry item với restart JobExecution |
| Writer không idempotent | Retry có thể ghi trùng hoặc lặp side effect | Dùng unique key, upsert, idempotency hoặc outbox |
| Nuốt exception trong processor/writer | Framework không nhận biết lỗi để retry | Truyền exception ra ngoài theo hợp đồng |
| Chỉ nhìn trạng thái cuối job | Bỏ qua xu hướng lỗi tạm thời tăng cao | Thu thập retry metrics và log có correlation ID |

## 17. Kiểm thử retry limit

Có thể kiểm thử retry bằng processor hoặc writer giả lập số lần thất bại trước khi thành công.

Ví dụ processor thất bại hai lần rồi thành công:

```java
public class FlakyProcessor implements ItemProcessor<Request, Response> {

    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public Response process(Request request) {
        int attempt = attempts.incrementAndGet();
        if (attempt <= 2) {
            throw new TransientPartnerException("Temporary failure");
        }
        return new Response(request.id(), "OK");
    }
}
```

Với `retryLimit(3)` và exception được cấu hình retry, test có thể xác nhận item cuối cùng được xử lý thành công sau các lần thử. Cũng nên kiểm tra trường hợp thất bại liên tục vượt giới hạn và xác nhận step chuyển sang skip hoặc fail đúng chính sách.

Các trường hợp cần kiểm tra:

1. Exception retryable thành công ngay lần đầu: không phát sinh retry.
2. Exception retryable thất bại một vài lần rồi thành công: item được xử lý thành công.
3. Exception retryable thất bại quá giới hạn: skip hoặc fail theo policy.
4. Exception không retryable: không có lần thử lại bổ sung.
5. Retry kết hợp backoff: số lần thử và khoảng chờ phù hợp cấu hình.
6. Retry ở writer: không tạo dữ liệu trùng khi writer được gọi lại.
7. Restart sau khi step thất bại: JobRepository và checkpoint tiếp tục đúng JobInstance.

Integration test nên kiểm tra cả số lần gọi processor/writer, trạng thái step, skip count và dữ liệu đã commit. Chỉ kiểm tra JobExecution hoàn thành là chưa đủ để xác nhận retry hoạt động đúng.

## 18. Quy trình chọn retry limit cho production

Khi thiết kế retry policy, hãy thực hiện theo thứ tự:

1. Xác định exception đại diện cho lỗi tạm thời và có thể thành công khi thử lại.
2. Kiểm tra thao tác có an toàn khi gọi lặp hay cần idempotency key.
3. Chọn retry limit dựa trên SLA, timeout và khả năng chịu tải của dịch vụ.
4. Cấu hình backoff để tránh retry dồn dập.
5. Quyết định riêng điều gì xảy ra sau khi hết retry: skip có audit hay fail job.
6. Kiểm tra transaction rollback và checkpoint ở từng giai đoạn reader, processor, writer.
7. Thu thập metric về retry, exhaustion và thời gian chờ.
8. Kiểm thử lỗi kéo dài, lỗi thoáng qua và tải đồng thời trước khi triển khai.

Retry policy cần phối hợp với timeout của client và deadline tổng thể. Nếu mỗi lần gọi có timeout 30 giây, retry ba lần cùng backoff có thể làm một item chiếm thời gian đáng kể. Hãy tính tổng thời gian tối đa và bảo đảm không vượt SLA của job.

## Kết luận

`retryLimit` giới hạn số lần Spring Batch thử lại một thao tác/item khi gặp exception được khai báo bằng `retry(...)` trong fault-tolerant chunk step. Khi hết giới hạn, exception được xử lý tiếp theo skip policy nếu được phép; nếu không, step thất bại. Retry khác với skip và restart: retry thử lại thao tác, skip loại item, còn restart tiếp tục JobInstance từ metadata đã lưu.

Hãy chỉ retry lỗi tạm thời, đặt giới hạn vừa đủ, dùng backoff khi cần và bảo đảm reader/processor/writer an toàn khi được gọi lại. Theo dõi retry metrics để phát hiện hệ thống phụ thuộc đang suy giảm, đồng thời thiết kế skip hoặc fail rõ ràng khi retry không còn hiệu quả.
