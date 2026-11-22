# Kết hợp skip và retry

Trong Spring Batch, `retry` và `skip` là hai cơ chế fault tolerance thường được kết hợp trong một chunk-oriented Step. Retry cho phép thử lại một thao tác có khả năng thành công sau một lỗi tạm thời. Skip cho phép bỏ qua một item gặp lỗi mà nghiệp vụ chấp nhận loại khỏi kết quả, để Step tiếp tục xử lý các item còn lại.

Hai cơ chế giải quyết hai loại tình huống khác nhau. Ví dụ, lỗi deadlock khi ghi database thường có thể retry vì transaction có thể thành công ở lần thử sau. Một bản ghi có định dạng không hợp lệ có thể được skip nếu quy tắc nghiệp vụ cho phép bỏ bản ghi đó. Nếu một exception vừa được cấu hình retryable vừa skippable, Spring Batch thường ưu tiên retry trước; khi retry đã hết giới hạn, skip policy mới quyết định có thể bỏ qua item hay Step phải thất bại.

## 1. Retry và skip giải quyết vấn đề gì?

Trong chunk processing, Spring Batch đọc item, xử lý bằng `ItemProcessor`, rồi ghi kết quả bằng `ItemWriter`. Exception có thể phát sinh ở bất kỳ giai đoạn nào.

| Cơ chế | Mục đích | Ví dụ phù hợp |
|---|---|---|
| Retry | Thử lại lỗi tạm thời có khả năng tự phục hồi | Deadlock, lock contention, timeout tạm thời khi gọi dịch vụ |
| Skip | Bỏ qua item lỗi theo chính sách nghiệp vụ | Dòng file sai định dạng, bản ghi vi phạm quy tắc có thể loại bỏ |

Retry không có nghĩa là bỏ qua lỗi. Nếu lần thử tiếp theo thành công, item vẫn được xử lý bình thường. Skip có nghĩa là chấp nhận không đưa item lỗi vào kết quả xử lý chính, đồng thời ghi nhận việc bỏ qua.

Ví dụ một file có 1.000 đơn hàng:

- Một đơn hàng có ngày tháng sai định dạng có thể được skip nếu nghiệp vụ cho phép.
- Một lần ghi database gặp deadlock có thể retry để thử lại cùng thao tác.
- Nếu retry hết giới hạn mà lỗi vẫn xảy ra, Spring Batch kiểm tra exception có thuộc nhóm được phép skip hay không.
- Nếu exception không retry được hoặc không được skip, Step kết thúc thất bại.

## 2. Cấu hình retry và skip trong một Step

Spring Batch bật fault-tolerant behavior bằng `.faultTolerant()` trên builder của chunk Step. Sau đó có thể khai báo exception retryable, giới hạn retry, exception skippable và giới hạn skip.

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(DeadlockLoserDataAccessException.class)
            .retryLimit(3)
            .skip(FlatFileParseException.class)
            .skipLimit(20)
            .build();
}
```

Trong ví dụ:

- `DeadlockLoserDataAccessException` được xem là lỗi có thể retry.
- `retryLimit(3)` giới hạn số lần retry theo chính sách được cấu hình.
- `FlatFileParseException` được phép skip.
- `skipLimit(20)` giới hạn tổng số item được skip trong Step.

Các exception và giới hạn trong ví dụ chỉ mang tính minh họa. Hãy chọn loại exception cụ thể theo reader, processor, writer và nghiệp vụ thực tế. API class hoặc package có thể khác giữa các phiên bản Spring Batch và Spring Framework của dự án.

## 3. Spring Batch kết hợp retry và skip như thế nào?

Khi một item gặp exception, Spring Batch phân loại lỗi theo cấu hình fault tolerance. Nếu lỗi được cấu hình retryable, framework thử lại theo retry policy. Nếu các lần retry vẫn thất bại, skip policy có thể được áp dụng nếu exception cũng được cho phép skip và chưa vượt skip limit.

```text
Đọc / Process / Write item
          |
          v
       Exception
          |
          v
  Exception có retryable?
       /       \
     Có         Không
     |            |
     v            v
 Retry còn     Kiểm tra
 lượt không?   skip policy
   /   \
 Có     Hết
 |       |
 v       v
Thử lại  Exception skippable?
          /       \
        Có         Không
        |            |
        v            v
  Skip item       Step FAILED
  nếu còn skip limit
```

Điểm quan trọng là retry được dùng để vượt qua lỗi tạm thời; skip là quyết định cuối cùng cho phép bỏ item. Nếu exception không được cấu hình retryable, Spring Batch có thể đánh giá trực tiếp skip policy. Nếu exception được retry nhưng retry hết giới hạn, nó chỉ được bỏ qua khi skip policy cho phép.

Không nên cấu hình cùng một exception vào cả retry và skip chỉ để “chắc chắn Job tiếp tục”. Cần xác định rõ ý nghĩa nghiệp vụ: lỗi có khả năng phục hồi nên được retry; lỗi dữ liệu được chấp nhận loại bỏ mới nên được skip.

## 4. retryLimit và skipLimit không phải cùng một bộ đếm

Hai giới hạn điều khiển hai việc khác nhau:

| Thuộc tính | Giới hạn điều gì? | Khi vượt giới hạn |
|---|---|---|
| `retryLimit` | Số lần thử lại cho lỗi thuộc retry policy | Không retry thêm; framework tiếp tục xử lý theo skip policy hoặc làm Step thất bại |
| `skipLimit` | Tổng số item được phép bỏ qua trong Step | Step thất bại khi số skip vượt giới hạn |

`skipLimit` được tính chung cho các loại skip ở bước đọc, xử lý và ghi. Các counter tương ứng là `readSkipCount`, `processSkipCount` và `writeSkipCount`; tổng skip được theo dõi ở `StepExecution`.

Ví dụ, nếu `skipLimit(5)` và Step đã skip 3 item khi đọc cùng 2 item khi process, tổng đã đạt 5. Nếu một item khác cần skip, Step vượt giới hạn và thất bại thay vì tiếp tục bỏ item đó.

Không dùng `retryLimit` để giới hạn tổng số item lỗi của Step. Một lỗi có thể được thử lại nhiều lần; nhiều item khác nhau cũng có thể gặp retry. `skipLimit` mới là giới hạn số item được chấp nhận bỏ qua.

## 5. Phân loại exception theo tính chất lỗi

Thiết kế fault tolerance nên bắt đầu từ nguyên nhân lỗi, không phải từ mong muốn để Job luôn chạy đến cuối.

| Nhóm lỗi | Ví dụ | Chính sách thường phù hợp |
|---|---|---|
| Lỗi tạm thời | Deadlock, lock timeout, dịch vụ tạm thời unavailable | Retry có giới hạn, có thể kèm backoff |
| Lỗi dữ liệu của một item | Ngày sai định dạng, mã nghiệp vụ không hợp lệ | Skip nếu nghiệp vụ cho phép; nếu không thì fail |
| Lỗi cấu hình | Sai tên bảng, thiếu tham số bắt buộc, thiếu quyền | Fail sớm; retry thường không giúp khắc phục |
| Lỗi hạ tầng kéo dài | Database mất kết nối lâu, broker ngừng hoạt động | Retry có giới hạn hoặc fail để vận hành xử lý |
| Lỗi lập trình | Null pointer do bug, invariant bị vi phạm | Thường fail và sửa lỗi; không nên skip rộng |

Retry các exception quá rộng như `Exception.class` có thể làm Job thử lại lỗi không thể phục hồi, kéo dài thời gian chạy và che khuất nguyên nhân. Skip các exception quá rộng cũng nguy hiểm vì có thể bỏ qua lỗi hạ tầng hoặc lỗi lập trình, dẫn đến dữ liệu thiếu mà Job vẫn báo hoàn tất.

Ưu tiên cấu hình các exception cụ thể. Nếu dùng exception cha, hãy chắc chắn mọi subclass đều có cùng chính sách retry hoặc skip.

## 6. Retry và skip ở ba giai đoạn đọc, xử lý, ghi

Exception có thể phát sinh ở ba giai đoạn khác nhau. Cách framework nhận diện item lỗi và cách quan sát cũng khác nhau.

### Lỗi khi đọc (read)

Reader có thể ném exception khi đọc file, parse dòng hoặc truy vấn nguồn dữ liệu. Ví dụ, một dòng file không đúng định dạng có thể tạo `FlatFileParseException`. Nếu dòng lỗi được phép bỏ qua, cấu hình skip cho exception này.

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(20)
```

Với lỗi kết nối nguồn dữ liệu tạm thời, có thể cấu hình retry nếu reader và nguồn dữ liệu hỗ trợ việc gọi lại an toàn. Cần kiểm tra reader có giữ vị trí đọc nhất quán sau exception hay không.

### Lỗi khi xử lý (process)

Processor có thể ném exception khi kiểm tra hoặc chuyển đổi item. Ví dụ, một giá trị nghiệp vụ không hợp lệ có thể được skip theo quy tắc:

```java
public class ValidateOrderProcessor implements ItemProcessor<Order, Order> {

    @Override
    public Order process(Order order) {
        if (order.getAmount().signum() < 0) {
            throw new InvalidOrderException("Negative order amount");
        }

        return order;
    }
}
```

Nếu `InvalidOrderException` được cấu hình skippable, item đó được bỏ qua khi chính sách skip cho phép. Processor nên tránh side effect không idempotent vì nó có thể được gọi lại trong quá trình retry hoặc phục hồi chunk.

### Lỗi khi ghi (write)

Writer có thể ném exception khi insert database, ghi file hoặc gửi message. Retry có thể hữu ích với deadlock hoặc lỗi tạm thời. Skip có thể áp dụng với lỗi gắn với một item cụ thể, nếu writer và nghiệp vụ hỗ trợ xác định item đó.

Write-skip phức tạp hơn read/process-skip vì writer thường nhận cả chunk. Khi một item trong chunk gây lỗi, Spring Batch có thể rollback chunk và gọi lại writer với các tập item nhỏ hơn để xác định item lỗi, tùy cơ chế fault tolerance và loại writer. Vì vậy, writer phải chịu được việc được gọi nhiều lần và cần idempotent nếu side effect không được transaction hoàn tác.

## 7. Ví dụ kết hợp lỗi tạm thời và lỗi dữ liệu

Giả sử Job nhập đơn hàng từ file vào database:

- Dòng file không parse được: bỏ qua nếu nghiệp vụ chấp nhận.
- Database deadlock: thử lại vì transaction có thể thành công ở lần tiếp theo.
- Đơn hàng có amount âm: skip nếu được quy định là bản ghi không hợp lệ có thể loại bỏ.
- Database mất kết nối kéo dài: retry có giới hạn; khi hết retry, Step thất bại vì lỗi này không được skip.

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(DeadlockLoserDataAccessException.class)
            .retryLimit(3)
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .build();
}
```

Trong cấu hình này, `DeadlockLoserDataAccessException` được retry nhưng không được skip. Nếu deadlock vẫn xảy ra sau số lần thử tối đa, Step thất bại. Các exception dữ liệu được khai báo skippable thì có thể bị bỏ qua, miễn tổng skip chưa vượt 50.

Đây là cấu hình minh họa. Nếu exception dữ liệu cũng có thể xuất hiện ở writer hoặc reader, hãy xác nhận loại exception thực tế và vị trí phát sinh. Chính sách skip/retry phải phù hợp với contract của component ở từng giai đoạn.

## 8. Retry cần giới hạn và backoff

Retry liên tục không giới hạn có thể giữ transaction, thread và connection quá lâu. Một retry policy tốt thường có:

- Giới hạn số lần thử lại.
- Phân loại lỗi transient cụ thể.
- Khoảng chờ giữa các lần retry khi hệ thống đích cần thời gian phục hồi.
- Backoff tăng dần nếu phù hợp, tránh nhiều worker cùng retry dồn dập.
- Logging và metric để quan sát số lần retry, loại exception và thời gian chờ.

Backoff thường được dùng với lỗi như HTTP 429/503 hoặc database contention. Có thể cấu hình `BackOffPolicy` thông qua builder ở các phiên bản Spring Batch hỗ trợ API tương ứng. Với dịch vụ bên ngoài, cũng cần tôn trọng `Retry-After`, timeout và rate limit của dịch vụ.

Không retry lỗi validation cố định như ngày sai định dạng hoặc thiếu tham số. Cùng một input không hợp lệ thường vẫn không hợp lệ ở lần thử tiếp theo.

## 9. Rollback và việc gọi lại writer

Trong chunk processing, exception có thể làm transaction chunk rollback. Khi retry, Spring Batch có thể gọi lại processor hoặc writer cho item/chunk liên quan. Vì vậy, cần hiểu side effect của từng component.

Với database writer dùng cùng transaction manager, các thay đổi chưa commit thường được rollback cùng chunk. Khi retry, writer có thể ghi lại mà không để lại các insert của lần thất bại.

Với HTTP API, email, file hoặc message broker, rollback database không tự thu hồi side effect đã xảy ra. Ví dụ writer gửi 20 message rồi message thứ 21 lỗi; nếu chunk được retry, 20 message đầu có thể được gửi lại.

Để tránh trùng:

- Dùng idempotency key ổn định cho mỗi item hoặc message.
- Dùng unique constraint hoặc upsert cho dữ liệu database phù hợp.
- Dùng outbox để ghi ý định publish cùng transaction nghiệp vụ.
- Với file, ghi tạm và publish sau khi hoàn tất, hoặc dùng writer hỗ trợ checkpoint.
- Tránh side effect ngoài transaction trong processor.

Retry chỉ an toàn khi lần thực hiện lại không tạo ra kết quả nghiệp vụ trùng hoặc sai.

## 10. Writer và write-skip cần đặc biệt cẩn thận

Khi writer nhận một chunk gồm nhiều item, nó có thể ghi một số item rồi gặp exception. Nếu các thao tác ghi tham gia cùng transaction, rollback có thể hoàn tác phần đã ghi. Nếu không, phần dữ liệu đã ghi có thể còn lại.

Để hỗ trợ write-skip, Spring Batch có thể cần gọi lại writer với các nhóm item nhỏ hơn để cô lập item lỗi. Một writer vì vậy không nên giả định mỗi chunk chỉ được gọi đúng một lần. Nó cần:

- Không bắt exception rồi trả về bình thường nếu dữ liệu chưa được ghi.
- Ném exception phù hợp để framework áp dụng retry/skip.
- Có khả năng chịu gọi lại sau rollback.
- Dùng transaction hoặc idempotency cho các thao tác ghi.
- Không tạo side effect không thể hoàn tác trước khi biết kết quả cuối cùng.

Nếu writer chỉ có thể ghi toàn chunk như một lệnh bulk và không thể xác định item lỗi, hãy cân nhắc staging, validation trước khi ghi hoặc tách thao tác để có thể cô lập bản ghi lỗi.

## 11. SkipListener và RetryListener

Listener giúp quan sát việc skip và retry. `SkipListener` có các callback cho từng giai đoạn:

| Callback | Khi nào được gọi? |
|---|---|
| `onSkipInRead(Throwable)` | Khi một lỗi đọc được chấp nhận skip |
| `onSkipInProcess(item, Throwable)` | Khi item bị skip do lỗi processor |
| `onSkipInWrite(item, Throwable)` | Khi item bị skip do lỗi writer |

Ví dụ ghi nhận item bị skip:

```java
public class ImportSkipListener implements SkipListener<Order, Order> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Skipped input while reading: {}", throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable throwable) {
        log.warn("Skipped order {} during processing: {}",
                item.getId(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        log.warn("Skipped order {} during writing: {}",
                item.getId(), throwable.getMessage());
    }
}
```

Đăng ký listener bằng `.listener(skipListener)` trong cấu hình Step. Dùng listener để ghi nhận lý do, ID item và vị trí nguồn để có thể điều tra hoặc xuất báo cáo lỗi.

`RetryListener` của Spring Retry có thể được dùng để quan sát vòng đời retry, tùy phiên bản và API builder đang dùng. Không nên gửi email hoặc gọi API không idempotent trực tiếp trong callback retry/skip; callback có thể được gọi trong transaction hoặc trong quá trình phục hồi. Nếu cần lưu bản ghi lỗi bền vững, hãy dùng cơ chế transaction phù hợp hoặc outbox.

## 12. Đếm skip và theo dõi kết quả Step

`StepExecution` cung cấp các counter:

| Counter | Ý nghĩa |
|---|---|
| `readSkipCount` | Số item bị skip ở giai đoạn đọc |
| `processSkipCount` | Số item bị skip ở giai đoạn xử lý |
| `writeSkipCount` | Số item bị skip ở giai đoạn ghi |
| `skipCount` | Tổng số item bị skip |
| `readCount` | Số item đọc thành công |
| `writeCount` | Số item ghi thành công |
| `rollbackCount` | Số lần rollback được ghi nhận |

Có thể ghi metric sau Step:

```java
public class ImportMetricsListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // Không cần khởi tạo mutable counter riêng.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "step={}, read={}, write={}, readSkip={}, processSkip={}, " +
                "writeSkip={}, retry-related rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getRollbackCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

`rollbackCount` không phải số lần retry chính xác: một rollback có thể xảy ra vì nhiều nguyên nhân, và retry có thể bao gồm các thao tác khác nhau tùy phase. Nếu cần đo retry, hãy dùng retry listener hoặc metric chuyên biệt.

## 13. noRollback không đồng nghĩa với skip

Spring Batch cho phép cấu hình một số exception không làm transaction rollback bằng `noRollback(...)` trong fault-tolerant Step. Đây là một lựa chọn nâng cao và cần hiểu rõ loại exception cùng thời điểm side effect xảy ra.

`noRollback` chỉ thay đổi hành vi rollback cho loại exception được chỉ định. Nó không tự động đánh dấu item là skippable, không thay thế `skip(...)` và cũng không retry exception nếu chưa cấu hình retry policy.

Ví dụ khái niệm:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(20)
.noRollback(InvalidOrderException.class)
```

Chỉ dùng `noRollback` khi việc giữ các thay đổi đã thực hiện trong transaction là đúng với nghiệp vụ và an toàn. Nếu một exception xảy ra sau khi writer ghi dữ liệu chưa hoàn chỉnh, không rollback có thể khiến chunk commit trạng thái một phần. Với nhiều Step, retry và skip, mặc định rollback thường dễ reasoning hơn; chỉ thay đổi khi đã xác định rõ hậu quả.

## 14. Những nhầm lẫn thường gặp

**Cho rằng retry và skip là hai tên gọi cho cùng một việc.** Retry thử lại thao tác; skip chấp nhận bỏ item. Chọn theo nguyên nhân và yêu cầu nghiệp vụ.

**Cho rằng exception retry hết giới hạn tự động được skip.** Chỉ khi exception thuộc skip policy và skip limit chưa bị vượt, item mới có thể được bỏ qua. Nếu không, Step thất bại.

**Cho rằng skipLimit áp dụng riêng cho từng phase.** Skip limit là giới hạn tổng của Step, cộng các skip ở read, process và write.

**Retry mọi exception.** Lỗi validation, lỗi cấu hình hoặc bug thường không tự biến mất khi thử lại. Hãy chọn exception transient cụ thể.

**Skip lỗi hạ tầng.** Bỏ qua database outage hoặc broker unavailable có thể làm mất dữ liệu. Những lỗi này thường cần retry có giới hạn hoặc fail.

**Cho rằng rollback thu hồi mọi side effect.** Rollback chỉ tác động đến resource tham gia transaction. API, email, file và message cần idempotency hoặc cơ chế phục hồi riêng.

**Cho rằng writer chỉ được gọi một lần.** Retry và write-skip có thể khiến writer được gọi lại. Writer cần chịu được việc replay.

**Dùng noRollback thay cho skip.** NoRollback chỉ thay đổi transaction behavior; skip policy mới quyết định item có được bỏ qua hay không.

## 15. Kiểm thử khi kết hợp retry và skip

Một bài kiểm thử có ý nghĩa cần xác nhận cả kết quả cuối cùng lẫn số lần thực hiện:

1. Tạo một item gây lỗi transient ở lần đầu nhưng thành công ở lần sau; xác nhận retry xảy ra và item vẫn được ghi.
2. Tạo một item gây lỗi dữ liệu thuộc skip policy; xác nhận item bị skip và các item còn lại tiếp tục.
3. Tạo một exception vừa retryable vừa skippable; xác nhận retry được áp dụng trước và sau khi hết retry, skip policy quyết định kết quả.
4. Tạo số item lỗi vượt skip limit; xác nhận Step thất bại.
5. Tạo exception không retryable và không skippable; xác nhận Step thất bại ngay theo chính sách.
6. Làm writer thất bại sau một phần thao tác; xác nhận transaction rollback hoặc idempotency ngăn ghi trùng khi writer được gọi lại.
7. Kiểm tra `readSkipCount`, `processSkipCount`, `writeSkipCount`, `skipCount`, `writeCount` và trạng thái Step.

Với retry có backoff, test nên dùng policy hoặc clock có thể kiểm soát để không phải chờ thời gian thực dài. Với side effect bên ngoài, dùng fake service hoặc test container để kiểm tra idempotency key và số giao dịch thực sự được tạo.

## 16. Quy tắc thiết kế khi dùng chung retry và skip

Hãy phân loại exception trước khi cấu hình: lỗi transient được retry có giới hạn; lỗi dữ liệu có thể loại bỏ được skip; lỗi cấu hình, lỗi lập trình và lỗi hạ tầng không thể phục hồi cần làm Step thất bại. Nếu một exception vừa retryable vừa skippable, xác định rõ sau khi retry hết giới hạn thì nghiệp vụ có chấp nhận bỏ item hay không.

Đặt `retryLimit` và `skipLimit` tường minh, theo dõi counter và ghi nhận item bị skip bằng listener. Bảo đảm reader/processor/writer chịu được việc gọi lại; đặc biệt writer phải idempotent nếu thao tác ghi không được rollback hoàn toàn. Với các side effect ngoài transaction, cân nhắc outbox hoặc idempotency key thay vì dựa vào rollback.

Kết hợp đúng retry và skip giúp Job tự phục hồi trước lỗi tạm thời, tiếp tục xử lý khi gặp dữ liệu cá biệt được phép bỏ qua, đồng thời vẫn thất bại rõ ràng khi hệ thống không thể bảo đảm kết quả đúng.
