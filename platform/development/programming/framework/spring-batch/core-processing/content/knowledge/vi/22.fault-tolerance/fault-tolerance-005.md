# No rollback exception

Trong Spring Batch, một chunk-oriented Step thường thực hiện việc đọc, xử lý và ghi item bên trong transaction. Khi một exception xảy ra, framework phải quyết định transaction hiện tại có cần rollback hay không. Mặc định, exception từ `ItemWriter` làm transaction của chunk rollback vì writer có thể đã ghi được một phần dữ liệu trước khi lỗi xuất hiện.

Tuy nhiên, có những trường hợp writer phát hiện một vấn đề trước khi thực hiện bất kỳ thay đổi nào. Ví dụ, writer kiểm tra quy tắc nghiệp vụ và ném `ValidationException` trước khi ghi database. Trong trường hợp này, rollback có thể không cần thiết. Spring Batch cho phép khai báo những exception không làm transaction rollback bằng `noRollback()` trong cấu hình fault-tolerant Step.

`noRollback` chỉ điều khiển quyết định rollback của transaction. Nó không tự bỏ qua exception, không tự retry và không biến Step thành công. Việc tiếp tục hay thất bại vẫn phụ thuộc vào skip policy, retry policy và cách exception được xử lý.

## 1. Rollback trong chunk-oriented processing

Trong chunk-oriented Step, Spring Batch đọc một nhóm item, xử lý chúng rồi gọi writer. Transaction của chunk thường được commit sau khi writer hoàn tất thành công.

```text
Begin transaction
       |
       v
  ItemReader
       |
       v
 ItemProcessor
       |
       v
  ItemWriter
       |
       v
Commit transaction
```

Nếu exception xảy ra trong quá trình ghi, Spring Batch cần xem xét liệu các thay đổi trong transaction có còn hợp lệ hay không. Nếu writer đã ghi một số item rồi mới lỗi, commit phần ghi dở có thể làm dữ liệu không nhất quán. Vì vậy, mặc định exception từ `ItemWriter` khiến transaction của Step rollback.

Ví dụ writer thực hiện các thao tác:

1. Insert đơn hàng A.
2. Insert đơn hàng B.
3. Insert đơn hàng C nhưng gặp lỗi constraint.

Nếu ba thao tác cùng tham gia một transaction database và transaction rollback, insert A và B cũng được hoàn tác. Sau đó, Spring Batch có thể thực hiện retry hoặc skip theo cấu hình Step.

Rollback không phải là thao tác xóa thủ công các bản ghi. Nó là hành vi của transaction manager/database để hủy các thay đổi chưa commit thuộc transaction hiện tại trên những resource tham gia transaction.

## 2. No rollback exception là gì?

No rollback exception là loại exception được khai báo để không làm transaction của chunk rollback khi exception đó xảy ra. Spring Batch cung cấp API `noRollback()` trên cấu hình fault-tolerant Step.

Ví dụ:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .faultTolerant()
            .noRollback(ValidationException.class)
            .build();
}
```

Trong ví dụ, `ValidationException` được đánh dấu là exception không làm transaction rollback. Nếu exception này xuất hiện ở một tình huống mà không có thao tác nào làm mất tính hợp lệ của transaction, framework có thể giữ transaction thay vì rollback chỉ vì exception đó.

Một trường hợp sử dụng hợp lý là writer xác thực toàn bộ chunk trước khi thực hiện ghi. Nếu phát hiện một item không hợp lệ, writer ném `ValidationException` ngay trong giai đoạn kiểm tra, trước khi ghi bất kỳ item nào. Nếu exception này được cấu hình skip và no-rollback, Step có thể bỏ qua item theo policy mà không cần rollback các thao tác ghi chưa từng xảy ra.

Không nên cấu hình `noRollback()` chỉ vì muốn tránh chi phí rollback. Trước hết phải biết chính xác exception được ném ở thời điểm nào và writer đã thực hiện những thay đổi nào.

## 3. Cấu hình `noRollback()` trong Spring Batch 5

Trong Java configuration, `noRollback()` được gọi sau `faultTolerant()` trên builder của Step:

```java
@Bean
Step validateAndWriteOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("validateAndWriteOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .noRollback(ValidationException.class)
            .build();
}
```

`ValidationException.class` là kiểu exception được dùng để phân loại rollback. Có thể khai báo nhiều loại exception bằng nhiều lời gọi `noRollback()` nếu từng loại đã được đánh giá riêng.

Không nên dùng một exception quá rộng như `Exception.class` hoặc `RuntimeException.class` làm no-rollback rule cho toàn Step. Những exception đó có thể bao gồm lỗi database, lỗi ghi dở, lỗi hạ tầng hoặc lỗi lập trình mà transaction cần rollback.

### Khai báo cả skip và noRollback

Trong nhiều tình huống, mục tiêu là bỏ qua item validation lỗi và đồng thời không rollback chunk vì writer đã kiểm tra trước khi ghi. Khi đó, cần khai báo cả skip policy lẫn no-rollback rule:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(ValidationException.class)
        .skipLimit(50)
        .noRollback(ValidationException.class)
        .build();
```

Hai cấu hình có vai trò khác nhau:

- `skip(ValidationException.class)` cho phép Step bỏ qua item khi exception này xảy ra, trong giới hạn skip.
- `noRollback(ValidationException.class)` nói rằng exception này không yêu cầu rollback transaction.

Nếu chỉ khai báo `noRollback()` mà không cấu hình skip hoặc retry phù hợp, exception vẫn có thể làm Step thất bại. No-rollback không phải cơ chế nuốt exception.

## 4. No rollback không đồng nghĩa với skip

Đây là điểm quan trọng nhất khi sử dụng tính năng này. `noRollback` và `skip` giải quyết hai câu hỏi khác nhau:

- **Skip:** item có được phép bỏ qua để Step tiếp tục hay không?
- **No rollback:** exception có yêu cầu transaction hiện tại rollback hay không?

Ví dụ:

| Cấu hình | Quyết định về item | Quyết định transaction |
|---|---|---|
| Chỉ `skip()` | Có thể bỏ item nếu policy cho phép | Theo rollback classification mặc định |
| Chỉ `noRollback()` | Không tự bỏ item; exception vẫn có thể làm Step thất bại | Exception được cấu hình không yêu cầu rollback |
| `skip()` và `noRollback()` | Item có thể được bỏ qua | Exception đó không làm transaction rollback |
| Không có cả hai | Exception thường làm Step thất bại nếu không được xử lý ở nơi khác | Exception từ writer mặc định làm rollback |

Ví dụ, processor ném `ValidationException` và Step cho phép skip. Framework có thể loại item đó khỏi luồng xử lý và tiếp tục với các item khác. `SkipListener` ghi nhận item đã bị bỏ qua.

Nếu writer ném exception, mặc định transaction rollback. Khi exception được khai báo no-rollback, framework không rollback chỉ vì loại exception đó. Nhưng item có được bỏ qua hay Step có thất bại vẫn là quyết định riêng của fault tolerance.

## 5. No rollback không đồng nghĩa với retry

Retry có nghĩa framework thử lại một thao tác hoặc item khi exception được phân loại là retryable. No-rollback chỉ thay đổi quyết định rollback của transaction đối với exception đã cấu hình.

| Cơ chế | Câu hỏi được giải quyết | Ví dụ |
|---|---|---|
| Retry | Có nên thử lại sau lỗi không? | Deadlock tạm thời, timeout ngắn hạn |
| Skip | Có thể bỏ item lỗi và tiếp tục không? | Một bản ghi có dữ liệu nghiệp vụ không hợp lệ |
| No rollback | Exception này có cần rollback transaction không? | Writer từ chối item trước khi ghi bất kỳ dữ liệu nào |

Với lỗi deadlock, transaction thường cần rollback để giải phóng khóa và tạo một lần thử mới trong transaction phù hợp. Không nên đánh dấu deadlock là no-rollback chỉ để tránh rollback. Với lỗi validation xảy ra trước khi ghi, skip kết hợp no-rollback có thể phù hợp hơn.

Khi cùng một exception được khai báo cho nhiều policy, cần kiểm tra tương tác giữa retry, skip và rollback trong phiên bản Spring Batch đang dùng. Không nên suy luận rằng `noRollback()` sẽ tự làm retry hoặc skip hoạt động.

## 6. Vì sao mặc định writer exception làm rollback?

`ItemWriter.write()` nhận một nhóm item. Writer có thể thực hiện nhiều thao tác trước khi ném exception. Framework không thể mặc định biết writer đã ghi được bao nhiêu item hoặc có thể khôi phục trạng thái nội bộ nào.

Ví dụ:

```java
@Component
public class OrderWriter implements ItemWriter<Order> {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            repository.save(order);

            if (order.amount().signum() < 0) {
                throw new ValidationException("Negative order amount");
            }
        }
    }
}
```

Đoạn code trên có lỗi thiết kế: writer ghi từng item rồi mới phát hiện item không hợp lệ. Nếu cấu hình `ValidationException` là no-rollback, các thao tác save trước exception có thể được commit dù item lỗi khiến writer ném exception. Kết quả có thể là một phần chunk đã được ghi.

Nếu muốn dùng no-rollback cho validation, nên kiểm tra trước toàn bộ chunk:

```java
@Override
public void write(Chunk<? extends Order> chunk) {
    for (Order order : chunk) {
        if (order.amount() == null || order.amount().signum() < 0) {
            throw new ValidationException(
                    "Invalid order: " + order.orderId());
        }
    }

    repository.saveAll(chunk.getItems());
}
```

Trong ví dụ này, validation diễn ra trước khi gọi `saveAll`. Nếu validation exception được ném ra, writer chưa bắt đầu thao tác ghi. Đây là kiểu tình huống dễ đánh giá hơn khi xem xét no-rollback.

Tuy nhiên, `saveAll()` hoặc repository implementation vẫn có thể thực hiện nhiều câu lệnh; cần hiểu transaction và hành vi thực tế của persistence provider. Không nên chỉ dựa vào tên phương thức để kết luận rằng không có partial write.

## 7. Ví dụ đầy đủ: validation exception được skip mà không rollback

Giả sử writer nhận chunk đơn hàng. Trước khi ghi, writer xác thực quy tắc chung của chunk. Nếu một item không hợp lệ, writer ném `ValidationException`. Nghiệp vụ cho phép bỏ qua item lỗi và tiếp tục xử lý dữ liệu hợp lệ.

Một cấu hình minh họa:

```java
@Bean
Step writeValidatedOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer,
        OrderSkipListener skipListener) {

    return new StepBuilder("writeValidatedOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(ValidationException.class)
            .skipLimit(20)
            .noRollback(ValidationException.class)
            .listener(skipListener)
            .build();
}
```

Trong ví dụ này:

1. Reader cung cấp các item đầu vào.
2. Processor chuyển chúng thành `Order`.
3. Writer kiểm tra các quy tắc cần áp dụng cho chunk.
4. Nếu writer ném `ValidationException`, exception thuộc nhóm được skip.
5. No-rollback rule cho biết exception này không yêu cầu rollback transaction.
6. SkipListener ghi nhận item bị bỏ qua theo callback tương ứng trong quá trình xử lý fault tolerance.

Chi tiết cách Spring Batch cô lập item gây lỗi trong writer phụ thuộc cơ chế fault tolerance và reader/writer. Ví dụ chỉ minh họa cách khai báo hai policy; cần bảo đảm writer không thực hiện tác dụng phụ trước khi ném validation exception và kiểm thử hành vi thực tế với phiên bản framework của ứng dụng.

Nếu writer không thể xác định chính xác item gây lỗi hoặc có thể ghi một phần chunk, không nên dùng no-rollback cho exception đó. Giữ rollback mặc định an toàn hơn.

## 8. No-rollback và các exception từ Reader, Processor, Writer

Các thành phần trong chunk có hành vi khác nhau khi xảy ra exception. Cần hiểu vị trí lỗi trước khi chọn rollback policy.

### Exception trong ItemReader

Reader có hợp đồng đọc tiến về phía trước. Khi Step được cấu hình skip, một số exception đọc có thể được xử lý mà không rollback transaction của chunk. Với reader dựa trên nguồn transactional như JMS queue, việc đọc message có thể tham gia transaction; khi rollback, message có thể được đưa trở lại queue. Spring Batch có tùy chọn `readerIsTransactionalQueue()` cho trường hợp reader sử dụng transactional queue, để framework không buffer item theo cách thông thường.

Không nên mặc định mọi reader exception đều có cùng rollback behavior. Cần xem loại reader, skip policy và tính transactional của nguồn dữ liệu.

### Exception trong ItemProcessor

Processor biến đổi từng item. Exception trong processor có thể được xử lý theo retry/skip policy. Nếu processor chỉ tính toán và không có tác dụng phụ, việc xử lý lại thường dễ kiểm soát hơn. Nếu processor gọi API ghi dữ liệu hoặc thay đổi hệ thống ngoài, rollback database không hoàn tác được tác dụng phụ đó.

### Exception trong ItemWriter

Writer ghi một nhóm item. Theo mặc định, exception từ writer làm transaction rollback vì framework không thể biết writer đã ghi được một phần hay chưa. Đây là trường hợp thường cần cân nhắc `noRollback()` nếu writer có thể ném một exception trước khi thực hiện bất kỳ thao tác ghi nào.

| Thành phần | Cần đánh giá |
|---|---|
| Reader | Nguồn có transactional không? Item có được buffer không? Skip có được cấu hình không? |
| Processor | Có tác dụng phụ ngoài transaction không? Item có thể retry/skip an toàn không? |
| Writer | Có thể đã ghi một phần trước exception không? Nếu có, rollback có cần thiết không? |

## 9. No-rollback exception không làm Step tự động thành công

Một hiểu lầm phổ biến là khai báo `.noRollback(MyException.class)` sẽ khiến Step bỏ qua lỗi. Điều đó không đúng.

No-rollback chỉ quy định exception không làm transaction rollback. Exception vẫn được đưa qua cơ chế xử lý lỗi của Step. Nếu exception không được skip, không được retry thành công và không được xử lý ở nơi khác, Step vẫn có thể chuyển sang `FAILED`.

Ví dụ:

```java
.faultTolerant()
.noRollback(ValidationException.class)
```

Đoạn cấu hình này không nói rằng `ValidationException` là lỗi có thể bỏ qua. Nếu muốn Step bỏ qua exception và tiếp tục, cần thêm skip policy:

```java
.faultTolerant()
.skip(ValidationException.class)
.skipLimit(20)
.noRollback(ValidationException.class)
```

Ngược lại, nếu exception thể hiện lỗi nghiêm trọng cần dừng Job, không cấu hình skip chỉ để tránh rollback. Hãy xác định riêng kết quả nghiệp vụ mong muốn và transaction behavior.

## 10. Rủi ro khi dùng noRollback không đúng

No-rollback có thể làm transaction commit những thay đổi đã xảy ra trước khi exception được ném ra. Vì vậy, cấu hình quá rộng hoặc chọn sai exception có thể nguy hiểm hơn rollback mặc định.

Các rủi ro chính:

- **Partial write:** writer ghi một số item rồi ném exception; no-rollback có thể để lại một phần dữ liệu.
- **Dữ liệu không nhất quán:** các thao tác liên quan không còn được commit/rollback cùng nhau như thiết kế.
- **Step thất bại nhưng thay đổi đã commit:** exception vẫn có thể làm Step thất bại, trong khi transaction không rollback.
- **Tác dụng phụ lặp:** khi Job được restart, thao tác ngoài transaction có thể được thực hiện lại.
- **Lỗi hạ tầng bị phân loại sai:** dùng superclass rộng có thể làm deadlock, timeout hoặc lỗi ghi không rollback.

Một nguyên tắc thực tế: chỉ cấu hình no-rollback cho exception có ý nghĩa rõ ràng và phát sinh ở thời điểm chắc chắn chưa có thay đổi nào cần hoàn tác trong transaction hiện tại.

## 11. NoRollback trong Spring Batch khác `@Transactional(noRollbackFor=...)`

Spring Framework có thuộc tính `noRollbackFor` trên `@Transactional`. Spring Batch có phương thức `noRollback()` trong cấu hình fault-tolerant Step. Hai cơ chế có liên quan về ý nghĩa nhưng nằm ở hai lớp cấu hình khác nhau.

| Cơ chế | Phạm vi |
|---|---|
| `.noRollback(ValidationException.class)` | Rollback classification của chunk-oriented Step trong Spring Batch |
| `@Transactional(noRollbackFor = ValidationException.class)` | Quy tắc rollback của transaction được quản lý bởi Spring transaction interceptor cho phương thức được annotate |

Nếu một service được gọi bên trong chunk có `@Transactional`, cần hiểu propagation và transaction manager được sử dụng. Transaction của service có thể tham gia transaction hiện tại hoặc tạo transaction riêng tùy propagation. Cấu hình noRollback ở Step không nên được xem là thay thế cho quy tắc rollback của một transaction độc lập bên trong service.

Tránh cấu hình hai nơi với quy tắc mâu thuẫn mà không có kiểm thử tích hợp. Một exception có thể đi qua nhiều ranh giới transaction khác nhau; cần xác định transaction nào đang được quyết định commit hoặc rollback.

## 12. No rollback và transactional reader

Reader thông thường trong chunk processing được xem là forward-only. Spring Batch buffer item đọc được để khi chunk rollback, framework có thể sử dụng lại item mà không cần reader quay ngược.

Với reader đọc từ transactional resource như JMS queue, việc lấy message có thể nằm trong transaction. Khi transaction rollback, message được trả lại queue. Trong trường hợp đó, có thể cấu hình:

```java
@Bean
Step consumeMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<MessageRecord> reader,
        ItemWriter<MessageRecord> writer) {

    return new StepBuilder("consumeMessagesStep", jobRepository)
            .<MessageRecord, MessageRecord>chunk(20, transactionManager)
            .reader(reader)
            .writer(writer)
            .readerIsTransactionalQueue()
            .build();
}
```

`readerIsTransactionalQueue()` điều chỉnh cách Step buffer input cho transactional queue. Đây là thiết lập liên quan đến reader/transactional resource, không phải no-rollback exception. Không dùng hai khái niệm thay thế cho nhau.

## 13. Cách chọn exception cho noRollback

Trước khi thêm một loại exception vào `noRollback()`, hãy trả lời các câu hỏi:

1. Exception được ném từ reader, processor hay writer?
2. Tại thời điểm ném exception, transaction đã thực hiện thay đổi nào chưa?
3. Nếu không rollback, những thay đổi nào có thể được commit?
4. Exception có cần skip, retry hay phải làm Step thất bại?
5. Nếu Step restart, có nguy cơ lặp tác dụng phụ hoặc dữ liệu trùng không?
6. Exception có superclass quá rộng bao gồm các lỗi khác không?
7. Có thể kiểm thử cả trường hợp thành công, skip và lỗi không?

Các loại exception thường cần được xem xét riêng:

| Exception category | Quyết định thường cần cân nhắc |
|---|---|
| Validation exception trước khi ghi | Có thể skip và no-rollback nếu chắc chắn chưa có thay đổi |
| Deadlock hoặc lock acquisition failure | Thường cần rollback và retry trong transaction mới |
| Database connection failure khi ghi | Thường rollback; không nên no-rollback chung chung |
| Constraint violation sau một số lệnh ghi | Thường cần rollback để tránh partial write |
| Lỗi lập trình như `NullPointerException` | Không nên no-rollback hoặc skip tùy tiện; thường cần Step thất bại |
| Lỗi API ngoài | Xem xét tác dụng phụ, retry/idempotency; rollback DB không hoàn tác API |

Đây là hướng dẫn phân loại theo tính chất lỗi, không phải quy tắc tuyệt đối cho mọi database hoặc writer. Cần dựa vào transaction thực tế và hợp đồng của thành phần ghi.

## 14. Kiểm thử rollback behavior

Vì no-rollback có thể làm thay đổi dữ liệu được commit khi exception xảy ra, cần có kiểm thử tích hợp với transaction manager và database phù hợp.

Các tình huống nên kiểm tra:

- Writer ném exception trước khi ghi: xác nhận no-rollback rule được áp dụng như mong muốn.
- Writer ghi một phần rồi ném exception: xác nhận cấu hình không làm dữ liệu dở dang tồn tại ngoài ý muốn.
- Exception được skip: xác nhận item bị bỏ qua và các item khác được xử lý đúng.
- Exception không được skip: xác nhận Step có trạng thái thất bại phù hợp dù transaction không rollback theo rule.
- Exception được retry: xác nhận transaction và thao tác ghi an toàn qua các lần thử.
- Step restart sau lỗi: xác nhận không có bản ghi trùng hoặc trạng thái nghiệp vụ sai.
- Listener/audit ghi nhận skip: xác nhận bản ghi audit có transaction boundary đúng.

Không nên chỉ mock `PlatformTransactionManager` rồi kết luận rollback behavior chính xác. Cần chạy kiểm thử tích hợp để xác nhận trạng thái dữ liệu trong database sau commit/rollback.

## 15. Các lỗi thường gặp

**Nhầm noRollback với skip:** noRollback không tự bỏ item. Muốn Step tiếp tục sau exception, cần cấu hình skip hoặc xử lý exception phù hợp.

**Nhầm noRollback với retry:** noRollback không thử lại thao tác. Retry là policy riêng và thường cần transaction mới khi lần thử trước đã rollback.

**Dùng noRollback cho mọi exception:** có thể commit partial write hoặc thay đổi không nhất quán. Chỉ dùng cho exception cụ thể đã hiểu rõ.

**Cấu hình noRollback cho lỗi writer sau khi đã ghi một phần:** có thể để lại dữ liệu dở dang. Writer cần xác thực trước khi ghi hoặc giữ rollback mặc định.

**Cho rằng Step chắc chắn COMPLETED:** exception vẫn có thể làm Step thất bại dù transaction không rollback.

**Bỏ qua kiểm thử transaction:** chỉ đọc log không đủ để biết dữ liệu nào đã commit. Hãy kiểm tra trạng thái database sau từng tình huống.

**Nhầm `readerIsTransactionalQueue()` với noRollback:** một tùy chọn điều khiển buffering cho transactional reader; tùy chọn kia phân loại exception về rollback.

**Cấu hình trùng hoặc mâu thuẫn với `@Transactional(noRollbackFor=...)`:** cần xác định transaction nào được quản lý ở từng lớp và propagation thực tế.

## Kết luận

`noRollback()` trong fault-tolerant chunk Step khai báo những exception không yêu cầu transaction rollback. Nó hữu ích khi một exception như validation được ném trước khi writer thực hiện bất kỳ thay đổi nào, và nghiệp vụ cho phép xử lý item theo skip policy. No-rollback không tự skip, retry hoặc biến Step thành công; các quyết định đó thuộc những policy riêng. Vì exception từ writer mặc định làm transaction rollback để bảo vệ tính nguyên tử của chunk, chỉ nên bỏ rollback cho loại exception cụ thể mà ứng dụng biết chắc không có partial write cần hoàn tác. Hãy kiểm thử transaction trên database thực tế, phân biệt với `@Transactional(noRollbackFor=...)` và transactional reader, đồng thời bảo đảm restart không tạo dữ liệu trùng hoặc trạng thái nghiệp vụ không nhất quán.
