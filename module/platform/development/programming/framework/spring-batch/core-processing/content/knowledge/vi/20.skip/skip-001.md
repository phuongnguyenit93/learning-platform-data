# Skip item không xử lý được

Trong Spring Batch, skip là cơ chế cho phép một chunk Step bỏ qua một item khi gặp lỗi đã được xác định là có thể chấp nhận, rồi tiếp tục xử lý các item còn lại. Cơ chế này hữu ích khi nguồn dữ liệu có một số bản ghi lỗi riêng lẻ nhưng nghiệp vụ vẫn cho phép hoàn tất phần dữ liệu hợp lệ.

Ví dụ, một Job import 100.000 dòng đơn hàng có thể gặp vài dòng sai định dạng, thiếu trường bắt buộc hoặc trùng khóa. Nếu dừng toàn bộ Job vì từng lỗi dữ liệu riêng lẻ, việc xử lý sẽ kém hiệu quả. Có thể cấu hình Spring Batch skip các exception cụ thể, giới hạn số item được bỏ qua và ghi nhận những item đó để sửa hoặc đối soát.

Skip là một quyết định có kiểm soát. Không nên bỏ qua mọi exception chỉ để Job kết thúc thành công. Lỗi dữ liệu của một item có thể được skip nếu nghiệp vụ cho phép; lỗi kết nối database, lỗi cấu hình hoặc lỗi lập trình thường cần retry hoặc làm Step thất bại.

## 1. Skip hoạt động ở đâu trong chunk processing?

Một chunk Step thực hiện chu trình đọc, xử lý và ghi. Exception có thể phát sinh ở bất kỳ giai đoạn nào:

```text
ItemReader
    |
    +-- exception được phép skip --> Read skip
    |
    v
ItemProcessor
    |
    +-- exception được phép skip --> Process skip
    |
    v
ItemWriter
    |
    +-- exception được phép skip --> Write skip
    |
    v
Commit chunk
```

Skip chỉ áp dụng cho exception được cấu hình trong fault-tolerant Step và còn trong giới hạn cho phép. Nếu exception không được phép skip hoặc số lần skip vượt giới hạn, Step có thể kết thúc ở trạng thái `FAILED`.

| Giai đoạn | Ví dụ lỗi | Kết quả khi được phép skip |
|---|---|---|
| Read | Dòng CSV không parse được | Bỏ qua bản ghi không đọc được và tiếp tục nếu reader có thể phục hồi. |
| Process | Số tiền âm hoặc thiếu mã đơn hàng | Bỏ qua item đầu vào không hợp lệ. |
| Write | Bản ghi trùng khóa theo quy tắc nghiệp vụ | Bỏ qua item đầu ra không thể ghi, nếu framework xác định được item lỗi và chính sách cho phép. |

Skip không biến một Step thành công về mọi mặt. Nó cho biết Step đã tiếp tục theo chính sách dù có một số item bị bỏ qua. Vì vậy, cần theo dõi skip count và báo cáo các item lỗi.

## 2. Cấu hình skip cơ bản

Với Spring Batch 5, có thể bật fault tolerance và khai báo exception được phép skip trên chunk Step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, Order> orderProcessor,
        ItemWriter<Order> orderWriter,
        SkipListener<OrderInput, Order> orderSkipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .faultTolerant()
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .listener(orderSkipListener)
            .build();
}
```

Trong ví dụ:

- `.faultTolerant()` bật cấu hình xử lý lỗi cho chunk Step.
- `.skip(InvalidOrderException.class)` cho phép bỏ qua exception dữ liệu đã xác định.
- `.skipLimit(50)` đặt giới hạn tổng số item được skip trong Step.
- `.listener(orderSkipListener)` đăng ký listener để ghi nhận item bị skip.

Với cấu hình này, tối đa 50 skip được chấp nhận. Nếu phát sinh skip thứ 51, giới hạn bị vượt và Step thất bại. Skip limit được áp dụng tổng hợp cho các lỗi ở giai đoạn đọc, xử lý và ghi, không phải 50 cho mỗi giai đoạn.

Nên đặt giới hạn rõ ràng theo yêu cầu nghiệp vụ. Nếu một Job import 100.000 dòng chỉ cho phép tối đa 20 dòng lỗi, hãy cấu hình giới hạn tương ứng và giám sát tỷ lệ lỗi. Một con số quá lớn có thể khiến Job hoàn tất dù chất lượng dữ liệu nguồn đã xuống cấp nghiêm trọng.

## 3. Chọn exception nào có thể skip?

Chỉ skip exception mà ứng dụng hiểu rõ và biết rằng việc bỏ qua item không làm sai lệch kết quả nghiệp vụ ở mức không thể chấp nhận.

Các ví dụ có thể cân nhắc:

- `FlatFileParseException`: một dòng tệp không thể parse theo định dạng dự kiến.
- `InvalidOrderException`: item vi phạm quy tắc dữ liệu của một đơn hàng.
- `DuplicateKeyException`: bản ghi bị trùng khóa và nghiệp vụ quy định bản ghi trùng phải bị loại.
- Một exception domain riêng biểu thị item không đủ điều kiện xử lý.

Các ví dụ thường không nên skip một cách mặc định:

- `DataAccessResourceFailureException`: database hoặc tài nguyên dữ liệu không truy cập được.
- `TransientDataAccessException`: lỗi tạm thời có thể phù hợp với retry hơn.
- `FileNotFoundException`: tệp đầu vào bắt buộc không tồn tại, thường là lỗi cấu hình hoặc đầu vào cấp Job.
- `OutOfMemoryError`: lỗi tài nguyên nghiêm trọng, không phải lỗi item có thể bỏ qua.
- Exception do lỗi lập trình như `NullPointerException` không được dự kiến.

Việc phân loại cuối cùng phụ thuộc nghiệp vụ. Ví dụ `DuplicateKeyException` có thể là lỗi item có thể bỏ qua trong một Job import, nhưng cũng có thể chỉ ra dữ liệu đích bị sai hoặc Job đang chạy trùng nếu hệ thống yêu cầu mỗi bản ghi phải được ghi chính xác một lần.

Không nên cấu hình `.skip(Exception.class)` như một cách xử lý chung. Cách đó có thể che giấu lỗi hạ tầng và lỗi lập trình, khiến Job báo hoàn tất với dữ liệu thiếu.

## 4. Skip ở giai đoạn đọc (read skip)

Read skip xảy ra khi `ItemReader` ném exception trong lúc đọc một item và exception đó được cho phép skip.

Ví dụ, reader đọc CSV có thể ném `FlatFileParseException` khi một dòng không có đủ cột hoặc chứa giá trị không đúng định dạng:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skipLimit(25)
```

Nếu reader có thể tiếp tục từ vị trí phù hợp sau dòng lỗi, Spring Batch có thể bỏ qua dòng đó và đọc dòng tiếp theo. Cần kiểm tra hành vi reader cụ thể, vì không phải mọi lỗi nguồn dữ liệu đều cho phép tiếp tục an toàn.

Ví dụ, lỗi parse một dòng thường gắn với một bản ghi riêng. Nhưng lỗi mất kết nối đến database hoặc file bị đóng giữa chừng có thể làm reader không thể tiếp tục. Skip các lỗi kiểu đó có thể làm mất một đoạn dữ liệu lớn hoặc khiến trạng thái đọc không đáng tin cậy.

### SkipListener khi reader lỗi

Với read skip, Spring Batch chưa có item hoàn chỉnh để truyền cho listener. Vì vậy, callback có dạng `onSkipInRead(Throwable t)` và chỉ nhận exception:

```java
@Override
public void onSkipInRead(Throwable exception) {
    log.warn("Could not read input record: {}",
            exception.getClass().getSimpleName());
}
```

Một số exception như `FlatFileParseException` có thể cung cấp số dòng hoặc thông tin nguồn. Có thể dùng thông tin đó để ghi báo cáo lỗi. Không nên ghi toàn bộ nội dung dòng nếu dữ liệu chứa thông tin cá nhân hoặc bí mật.

## 5. Skip ở giai đoạn xử lý (process skip)

Process skip xảy ra khi `ItemProcessor` ném exception cho một item. Đây là trường hợp thường gặp khi kiểm tra dữ liệu hoặc áp dụng quy tắc nghiệp vụ.

Ví dụ:

```java
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput item) {
        if (item.orderId() == null || item.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        if (item.amount() == null || item.amount().signum() <= 0) {
            throw new InvalidOrderException("Order amount must be positive");
        }

        return new Order(
                item.orderId(),
                item.customerId(),
                item.amount());
    }
}
```

Nếu `InvalidOrderException` được cấu hình skip, item lỗi không được chuyển đến writer và Step có thể tiếp tục với item khác.

Process skip phù hợp khi lỗi thuộc riêng item, ví dụ thiếu trường bắt buộc hoặc vi phạm quy tắc miền dữ liệu. Nếu processor gặp lỗi tạm thời khi gọi dịch vụ tham chiếu, retry có thể phù hợp hơn. Nếu processor gặp lỗi lập trình, không nên tự động skip vì điều đó có thể làm sai kết quả của nhiều item.

`SkipListener.onSkipInProcess` nhận item đầu vào và exception:

```java
@Override
public void onSkipInProcess(
        OrderInput item,
        Throwable exception) {

    log.warn("Skipping order input {} because of {}",
            item.orderId(),
            exception.getClass().getSimpleName());
}
```

Đây là nơi phù hợp để ghi nhận business key của item bị bỏ qua, miễn là dữ liệu được phép ghi log.

## 6. Skip ở giai đoạn ghi (write skip)

Write skip xảy ra khi `ItemWriter` ném exception khi ghi item hoặc chunk. Ví dụ, một đơn hàng trùng khóa có thể bị database từ chối.

```java
.faultTolerant()
.skip(DuplicateKeyException.class)
.skipLimit(100)
```

Write skip phức tạp hơn process skip vì writer nhận một nhóm item. Nếu một lần ghi chunk thất bại, framework cần xác định item nào gây lỗi trước khi có thể bỏ qua riêng item đó. Trong quá trình này, transaction chunk có thể rollback và writer có thể được gọi lại với nhóm item nhỏ hơn hoặc từng item để tìm phần tử lỗi.

Vì vậy, writer phải chịu được việc gọi lại. Nếu writer chỉ ghi database trong transaction do Step quản lý, rollback có thể hoàn tác các thao tác ghi chưa commit. Nếu writer gửi HTTP request, ghi file hoặc publish message ngoài transaction, tác dụng phụ có thể đã xảy ra trước khi exception được ném; lần gọi lại có thể tạo dữ liệu trùng.

`SkipListener.onSkipInWrite` nhận item đầu ra và exception:

```java
@Override
public void onSkipInWrite(Order item, Throwable exception) {
    log.warn("Could not write order {}: {}",
            item.orderId(),
            exception.getClass().getSimpleName());
}
```

Chỉ skip lỗi writer nếu có thể xác định lỗi thuộc một item và nghiệp vụ cho phép loại item đó. Lỗi database mất kết nối hoặc schema sai thường không phải lỗi riêng của item.

## 7. SkipLimit và cách giới hạn lỗi

Skip limit bảo vệ Job khỏi việc bỏ qua quá nhiều item. Đây là giới hạn tổng hợp cho read skip, process skip và write skip.

Ví dụ:

```java
.faultTolerant()
.skip(FlatFileParseException.class)
.skip(InvalidOrderException.class)
.skip(DuplicateKeyException.class)
.skipLimit(20)
```

Với giới hạn 20, Step có thể tiếp tục sau tối đa 20 item skip thuộc các loại exception được cấu hình. Khi phát sinh skip tiếp theo làm tổng số vượt 20, Step thất bại.

Không nên hiểu skip limit là số exception được phép phát sinh trong toàn Job hoặc một giới hạn riêng cho từng loại exception. Nó thuộc Step và được áp dụng trên tổng skip count của các giai đoạn trong Step đó.

### Chọn skip limit theo yêu cầu nghiệp vụ

Có thể chọn giới hạn theo:

- Số lượng tuyệt đối, ví dụ tối đa 20 dòng lỗi.
- Quy mô dữ liệu, ví dụ số lỗi tối đa trong một lô import đã biết.
- Ngưỡng chất lượng, ví dụ tỷ lệ bản ghi lỗi không vượt quá mức nghiệp vụ chấp nhận.

`skipLimit` là số lượng, không phải tỷ lệ phần trăm. Nếu cần chính sách theo tỷ lệ, có thể dùng `SkipPolicy` tùy chỉnh hoặc cơ chế kiểm tra tổng hợp riêng. Cần tính rõ mẫu số và thời điểm đánh giá để tránh quyết định skip không nhất quán.

## 8. Skip và noSkip

Có thể khai báo exception được skip và exception không được skip. Ví dụ, cho phép skip exception dữ liệu chung nhưng loại trừ một lỗi nghiêm trọng:

```java
.faultTolerant()
.skip(Exception.class)
.noSkip(FatalImportException.class)
.skipLimit(50)
```

Đây là ví dụ về khả năng khai báo loại trừ, không phải khuyến nghị skip mọi `Exception`. Trong ứng dụng thực tế, nên khai báo class exception cụ thể và chỉ mở rộng khi hiểu rõ hệ thống exception.

Khi các loại exception có quan hệ kế thừa, Spring Batch phân loại theo exception type đã cấu hình. Cần kiểm tra thứ tự/độ cụ thể của loại exception để bảo đảm một lỗi nghiêm trọng không vô tình được phân loại là skippable do lớp cha quá rộng.

## 9. Dùng SkipPolicy tùy chỉnh

Khi quy tắc skip phức tạp hơn danh sách exception, có thể triển khai `SkipPolicy`. Policy nhận exception và số lượng skip đã xảy ra để quyết định có cho phép bỏ qua hay không.

Hợp đồng cơ bản:

```java
public interface SkipPolicy {
    boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException;
}
```

Ví dụ policy giới hạn skip cho một loại lỗi nghiệp vụ:

```java
public class InvalidOrderSkipPolicy implements SkipPolicy {

    private final long limit;

    public InvalidOrderSkipPolicy(long limit) {
        this.limit = limit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount) {
        boolean invalidOrder = throwable instanceof InvalidOrderException;
        return invalidOrder && skipCount < limit;
    }
}
```

Nếu policy trả về `false`, exception không được skip và sẽ được truyền ra theo cơ chế của Step. Policy tùy chỉnh cần xử lý rõ lỗi nghiêm trọng, lỗi không xác định và giới hạn. Cần lưu ý `skipCount` là số skip đã được ghi nhận trong ngữ cảnh policy, vì vậy phải kiểm thử biên giới limit để bảo đảm hành vi đúng yêu cầu.

Đăng ký policy trên Step bằng `.skipPolicy(...)` thay cho cấu hình skip đơn giản:

```java
.faultTolerant()
.skipPolicy(new InvalidOrderSkipPolicy(50))
```

Khi dùng custom policy, policy chịu trách nhiệm quyết định các trường hợp được skip. Không nên trộn `.skip(...)`, `.noSkip(...)` và custom policy mà không hiểu precedence và hành vi của builder ở phiên bản đang sử dụng.

## 10. Ghi nhận item bị skip bằng SkipListener

`SkipListener` cung cấp callback theo giai đoạn để ứng dụng lưu lý do hoặc tạo báo cáo reject:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable exception) {
        log.warn("Read skip: {}", exception.getMessage());
    }

    @Override
    public void onSkipInProcess(
            OrderInput item,
            Throwable exception) {
        log.warn("Process skip for order {}: {}",
                item.orderId(), exception.getMessage());
    }

    @Override
    public void onSkipInWrite(
            Order item,
            Throwable exception) {
        log.warn("Write skip for order {}: {}",
                item.orderId(), exception.getMessage());
    }
}
```

Có thể dùng listener để:

- Ghi business key của item lỗi.
- Lưu loại exception và lý do bị skip.
- Ghi số dòng nguồn hoặc vị trí đọc.
- Tạo file reject để người dùng sửa dữ liệu.
- Gửi metric về số item bị bỏ qua theo loại lỗi.

### Lưu ý transaction khi ghi reject

Nếu listener ghi reject vào database, cần xác định thao tác đó tham gia transaction nào. Với cùng datasource/transaction manager, bản ghi reject có thể được commit hoặc rollback cùng transaction chunk theo cấu hình và thời điểm callback. Nếu ghi qua transaction manager khác hoặc hệ thống ngoài, không có bảo đảm nguyên tử tự động.

Thiết kế lưu reject cần tránh bản ghi trùng khi chunk rollback/retry. Có thể dùng unique key dựa trên batch ID, nguồn, số dòng hoặc business key; hoặc ghi reject qua outbox/audit store có cơ chế idempotent. Không nên giả định mọi listener callback luôn chỉ tạo một tác dụng phụ bên ngoài bất kể retry.

## 11. Skip khác filter như thế nào?

Filter và skip đều khiến item không đến writer, nhưng ý nghĩa khác nhau:

| Tiêu chí | Filter | Skip |
|---|---|---|
| Nguyên nhân | Item hợp lệ nhưng không thuộc kết quả cần tạo. | Có exception khi đọc, xử lý hoặc ghi. |
| Cách thực hiện | Processor trả về `null`. | Cấu hình exception trong skip policy. |
| Bộ đếm | `filterCount`. | `readSkipCount`, `processSkipCount`, `writeSkipCount`. |
| SkipListener | Không được gọi. | Được gọi khi item thực sự bị skip. |
| Skip limit | Không tiêu thụ skip limit. | Có tính vào skip limit. |
| Ví dụ | Bỏ đơn hàng đã hủy khỏi báo cáo. | Bỏ đơn hàng thiếu mã bắt buộc theo chính sách. |

Không nên trả về `null` để che giấu dữ liệu lỗi nếu cần báo cáo lỗi. Ngược lại, không nên ném exception và skip một item hợp lệ chỉ vì nó không nằm trong phạm vi báo cáo.

## 12. Kết hợp retry và skip

Retry và skip có thể cùng xuất hiện trong một fault-tolerant Step, nhưng chúng giải quyết các tình huống khác nhau:

- **Retry:** thử lại khi exception có khả năng tạm thời và thao tác có thể chạy lại an toàn.
- **Skip:** bỏ qua item khi lỗi đã được xác định là có thể chấp nhận.
- **Fail:** dừng Step khi lỗi không thể tiếp tục an toàn hoặc vượt giới hạn.

Ví dụ:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(200, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .build();
```

Trong cấu hình này, lỗi truy cập dữ liệu tạm thời được thử lại tối đa theo giới hạn. Lỗi dữ liệu đã xác định có thể bị skip. Khi một exception được cấu hình cho cả retry và skip, Spring Batch thường thử lại trước; nếu retry không thành công và exception vẫn thuộc nhóm skippable, nó có thể được skip theo chính sách. Hãy kiểm thử integration với exception thực tế để xác nhận kết quả cuối cùng, đặc biệt khi writer có thể gây rollback và được gọi lại.

Không retry lỗi dữ liệu cố định như thiếu trường bắt buộc nếu không có cơ chế nào có thể làm dữ liệu thay đổi giữa các lần thử. Cũng không skip lỗi hạ tầng kéo dài chỉ để tránh Job thất bại.

## 13. Rollback và tác động của skip

Chunk thường được xử lý trong transaction. Khi exception xảy ra, transaction chunk hiện tại có thể rollback trước khi framework hoàn tất việc retry hoặc skip. Các chunk đã commit trước đó vẫn được giữ lại.

Khi skip một item:

- Item lỗi không được xử lý/ghi thành công trong pipeline chính.
- Spring Batch tiếp tục với item khác nếu chính sách cho phép.
- Skip count tương ứng được cập nhật.
- `SkipListener` có thể ghi nhận item và exception.

Với write skip, framework có thể rollback chunk rồi thử ghi các item theo nhóm nhỏ hơn để xác định item lỗi. Do đó writer cần chịu được việc được gọi lại. Các thao tác ngoài transaction như HTTP, email hoặc file không tự rollback và cần idempotency.

Skip không đồng nghĩa rollback toàn bộ Job. Những chunk đã commit vẫn tồn tại; chunk hiện tại được xử lý theo transaction và fault-tolerance policy.

## 14. Theo dõi skip count trong StepExecution

`StepExecution` lưu các bộ đếm riêng cho từng giai đoạn:

| Bộ đếm | Ý nghĩa |
|---|---|
| `readSkipCount` | Số item bị skip khi reader phát sinh exception. |
| `processSkipCount` | Số item bị skip khi processor phát sinh exception. |
| `writeSkipCount` | Số item bị skip khi writer phát sinh exception. |
| `skipCount` | Tổng số skip của Step. |
| `readCount` | Số item reader đọc thành công. |
| `writeCount` | Số item được writer ghi theo metadata Step. |
| `filterCount` | Số item processor loại bỏ bằng cách trả về `null`. |

Có thể truy vấn các bộ đếm qua `StepExecution` hoặc `JobExplorer` để hiển thị trên màn hình vận hành. Không nên chỉ nhìn `BatchStatus.COMPLETED` rồi kết luận mọi item đều được xử lý; Step có thể hoàn tất với một số skip nằm trong giới hạn.

Ví dụ, một lần import có `readCount = 10.000`, `processSkipCount = 12`, `writeSkipCount = 3` và `filterCount = 100` cho thấy đã có item bị loại theo cả hai cơ chế. Cần dùng `SkipListener` và audit filter riêng để biết chính xác business key và lý do của từng item.

Không nên áp dụng một công thức cố định cho mọi Step như `readCount = writeCount + filterCount + skipCount`. Writer có thể tạo nhiều output cho một input, processor có thể filter, retry/rollback làm luồng xử lý phức tạp và các bộ đếm phản ánh từng giai đoạn khác nhau.

## 15. Ví dụ: import file và tạo reject report

Giả sử một Job nhập tệp CSV đơn hàng. Yêu cầu:

- Bỏ qua dòng không parse được.
- Bỏ qua đơn hàng thiếu mã hoặc có số tiền không hợp lệ.
- Dừng Job nếu có quá 30 item lỗi.
- Ghi nhận business key và nguyên nhân của item bị skip.
- Retry lỗi database tạm thời khi ghi.

Processor ném exception nghiệp vụ:

```java
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("Missing order ID");
        }

        if (input.amount() == null || input.amount().signum() <= 0) {
            throw new InvalidOrderException("Amount must be positive");
        }

        return new Order(input.orderId(), input.amount());
    }
}
```

Step cấu hình skip và retry:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(250, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(FlatFileParseException.class)
        .skip(InvalidOrderException.class)
        .skipLimit(30)
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .listener(orderSkipListener)
        .build();
```

Với thiết kế này, lỗi parse và lỗi validation có thể được skip trong giới hạn 30; lỗi database tạm thời được retry. Nếu tổng skip vượt 30, Step thất bại để người vận hành xem xét chất lượng dữ liệu.

Trong triển khai thật, reject report cần ghi nhận cả dòng nguồn không parse được và item đã parse nhưng không hợp lệ. Với read skip, listener không nhận item hoàn chỉnh; có thể lấy line number hoặc raw data an toàn từ exception. Với process/write skip, listener nhận item tương ứng.

## 16. Xử lý lỗi khi vượt skip limit

Khi số skip vượt giới hạn, Spring Batch ném exception giới hạn skip và Step kết thúc thất bại. Job flow có thể dùng transition dựa trên kết quả Step để chuyển đến Step báo lỗi, gửi thông báo hoặc dừng Job theo chính sách.

Không nên tăng skip limit tự động mỗi khi Job thất bại. Trước tiên cần xem:

- Loại exception nào chiếm phần lớn skip count.
- Lỗi xuất hiện ở reader, processor hay writer.
- Dữ liệu nguồn có thay đổi bất thường hay không.
- Lỗi có thực sự là lỗi riêng của item hay là sự cố hạ tầng.
- Tỷ lệ item lỗi có vượt ngưỡng chất lượng mà nghiệp vụ chấp nhận không.

Nếu tỷ lệ lỗi tăng đột biến, dừng Job và xử lý nguồn dữ liệu có thể an toàn hơn tiếp tục skip. Skip limit là một hàng rào bảo vệ, không phải mục tiêu cần tận dụng hết.

## 17. Restart sau khi Step có skip hoặc thất bại

Nếu Step hoàn tất thành công với skip count nằm trong giới hạn, Job thường tiếp tục flow. Các item bị skip không tự động được thử lại trong một lần chạy bình thường sau đó; muốn xử lý lại, ứng dụng cần có quy trình reprocess hoặc tạo input đã sửa.

Nếu Step thất bại vì skip limit bị vượt hoặc gặp exception không được xử lý, Job có thể được restart nếu trạng thái và cấu hình cho phép. Khi restart:

- JobInstance và identifying parameters cần giữ đúng nếu muốn tiếp tục lần nghiệp vụ cũ.
- Reader có hỗ trợ `ItemStream`/checkpoint có thể tiếp tục từ vị trí đã commit.
- Các chunk đã commit trước đó thường không được xử lý lại trong cùng Step restart.
- Chunk chưa commit cần được xử lý lại theo checkpoint và fault-tolerance policy.
- Writer phải an toàn khi một item được gửi lại do rollback/restart.

Không nên xóa metadata hoặc sửa trực tiếp `StepExecution` để bỏ qua skip limit. Nếu cần reprocess các item lỗi, hãy lưu reject data có business key và tạo một Job/Step riêng với định danh rõ ràng.

## 18. Những lỗi thường gặp

### Skip mọi exception

Điều này có thể che giấu lỗi database, lỗi cấu hình hoặc lỗi lập trình. Chỉ skip exception cụ thể đã được nghiệp vụ cho phép.

### Đặt skip limit quá cao

Job có thể hoàn tất dù phần lớn dữ liệu bị bỏ qua. Chọn giới hạn theo yêu cầu chất lượng và theo dõi tỷ lệ lỗi.

### Nhầm skip với filter

Filter là processor trả `null` cho item hợp lệ nhưng không cần output. Skip là xử lý exception. Hai cơ chế có bộ đếm và listener khác nhau.

### Skip lỗi tạm thời thay vì retry

Timeout hoặc deadlock có thể phục hồi. Skip ngay có thể làm thiếu dữ liệu; hãy cân nhắc retry có giới hạn và backoff.

### Không ghi nhận item bị skip

Nếu không có `SkipListener` hoặc reject store, khó xác định bản ghi nào cần sửa và chạy lại. Hãy lưu business key, nguồn và lý do theo chính sách bảo mật.

### Ghi reject không idempotent

Listener hoặc writer có thể được gọi lại khi transaction rollback/retry. Dùng unique key hoặc cơ chế chống trùng cho reject record.

### Nghĩ write skip luôn xác định được một item lỗi

Writer nhận cả chunk; lỗi có thể liên quan toàn bộ batch hoặc tài nguyên đích. Chỉ skip khi framework có thể xác định item và lỗi thực sự có thể bỏ qua.

### Restart nhưng không xem checkpoint

Reader không hỗ trợ state có thể đọc lại từ đầu hoặc bỏ sót dữ liệu nếu trạng thái nguồn thay đổi. Kiểm tra `ExecutionContext` và writer trước khi restart.

## 19. Quy trình quyết định một item có được skip không

Khi một item không xử lý được, hãy phân loại nguyên nhân trước khi cấu hình:

1. Item có hợp lệ nhưng không thuộc kết quả cần tạo không? Nếu có, dùng filter bằng cách trả `null`.
2. Có exception gắn với riêng item không? Nếu không, điều tra lỗi hạ tầng hoặc lỗi hệ thống.
3. Exception có được nghiệp vụ cho phép bỏ qua không? Nếu có, cấu hình `.skip(...)` hoặc `SkipPolicy`.
4. Lỗi có khả năng tạm thời và thao tác có thể lặp an toàn không? Nếu có, cân nhắc `.retry(...)` trước khi quyết định skip.
5. Tổng số item lỗi tối đa được chấp nhận là bao nhiêu? Đặt `skipLimit` phù hợp.
6. Cần lưu business key, dòng nguồn và nguyên nhân nào để đối soát? Đăng ký `SkipListener`.
7. Nếu vượt giới hạn, Job cần fail, dừng hay chuyển sang Step báo cáo lỗi? Thiết kế flow rõ ràng.
8. Nếu restart, reader có checkpoint và writer có thể chạy lại an toàn không?

| Tình huống | Cơ chế phù hợp |
|---|---|
| Một dòng CSV sai định dạng, có thể bỏ qua | Read skip cho exception parse cụ thể. |
| Một item thiếu trường bắt buộc | Process skip cho exception validation. |
| Một bản ghi trùng khóa theo quy tắc nghiệp vụ | Write skip nếu lỗi chỉ thuộc item và có thể xác định an toàn. |
| Database timeout tạm thời | Retry có giới hạn và backoff. |
| Database mất kết nối kéo dài | Fail Step, khôi phục hạ tầng rồi restart. |
| Item hợp lệ nhưng ngoài phạm vi báo cáo | Filter bằng cách trả `null`. |
| Số item lỗi vượt ngưỡng chất lượng | Fail Step và xử lý reject data. |

## Kết luận

Skip cho phép Spring Batch bỏ qua item gặp exception đã được xác định là có thể chấp nhận ở reader, processor hoặc writer. Dùng `.skip(...)` để khai báo loại lỗi, `.skipLimit(...)` để giới hạn tổng số item bị bỏ qua và `SkipListener` để ghi nhận item cùng nguyên nhân. Chỉ skip lỗi riêng của item; dùng retry cho lỗi tạm thời và để Step thất bại khi lỗi hệ thống hoặc dữ liệu không thể tiếp tục an toàn. Cần phân biệt skip với filter, theo dõi các skip counter và bảo đảm reject report cùng writer có thể xử lý rollback/retry mà không tạo tác dụng phụ trùng lặp.
