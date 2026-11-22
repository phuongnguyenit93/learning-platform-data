# Skip count trong StepExecution

Trong Spring Batch, một step có thể bỏ qua một số item gặp lỗi nếu lỗi đó thuộc loại được cấu hình cho phép skip. Framework ghi nhận số lượng item bị bỏ qua trong `StepExecution` thông qua các bộ đếm như `readSkipCount`, `processSkipCount`, `writeSkipCount` và `skipCount` tổng.

Các bộ đếm này giúp người phát triển và người vận hành biết lỗi xuất hiện ở giai đoạn nào của chunk processing, mức độ ảnh hưởng ra sao và step có hoàn tất trong giới hạn skip hay không. Để đọc đúng các con số, cần phân biệt skip với filter, retry và rollback; đồng thời hiểu cách `skipLimit` áp dụng cho toàn step.

## 1. Skip trong chunk processing là gì?

Một chunk-oriented step thường xử lý dữ liệu theo chu trình:

```text
ItemReader
    |
    v
ItemProcessor (tùy chọn)
    |
    v
ItemWriter
    |
    v
Commit transaction
```

Trong quá trình này, reader, processor hoặc writer có thể phát sinh exception. Không phải lỗi nào cũng nên làm step thất bại ngay lập tức. Ví dụ:

- Một dòng CSV có định dạng sai nhưng nghiệp vụ cho phép loại riêng dòng đó.
- Một bản ghi có mã khách hàng không hợp lệ và cần đưa vào danh sách lỗi.
- Một item không thể ghi do vi phạm một ràng buộc dữ liệu đã được xác định là lỗi có thể bỏ qua.

Spring Batch hỗ trợ skip policy để phân loại exception. Nếu exception được cho phép skip và giới hạn chưa bị vượt, framework bỏ qua item liên quan và tiếp tục xử lý theo chính sách của step.

Skip không có nghĩa là mọi exception đều được bỏ qua. Các lỗi hạ tầng hoặc lỗi không thể phục hồi như mất kết nối database, file đầu vào không tồn tại hoặc cấu hình sai thường cần làm step thất bại để được xử lý rõ ràng.

## 2. StepExecution lưu những bộ đếm nào?

`StepExecution` đại diện cho một lần thực thi cụ thể của một step. Nó lưu trạng thái, thời gian, execution context và các bộ đếm xử lý item.

Các bộ đếm liên quan trực tiếp đến skip gồm:

| Bộ đếm | Ý nghĩa |
|---|---|
| `readSkipCount` | Số lần item bị bỏ qua do exception trong giai đoạn đọc. |
| `processSkipCount` | Số item bị bỏ qua do exception trong giai đoạn xử lý. |
| `writeSkipCount` | Số item bị bỏ qua do exception trong giai đoạn ghi. |
| `skipCount` | Tổng số skip ở các giai đoạn đọc, xử lý và ghi. |

Trong API, có thể đọc các giá trị này qua những phương thức như:

```java
long readSkips = stepExecution.getReadSkipCount();
long processSkips = stepExecution.getProcessSkipCount();
long writeSkips = stepExecution.getWriteSkipCount();
long totalSkips = stepExecution.getSkipCount();
```

Về mặt khái niệm:

```text
skipCount = readSkipCount
          + processSkipCount
          + writeSkipCount
```

`skipCount` là tổng để theo dõi nhanh mức độ bỏ qua item. Ba bộ đếm thành phần giúp xác định lỗi tập trung ở reader, processor hay writer.

## 3. Phân biệt skip count với các counter khác

`StepExecution` có nhiều bộ đếm. Không nên dùng `skipCount` để suy ra toàn bộ số item đã đọc hoặc số item thành công.

| Counter | Ý nghĩa |
|---|---|
| `readCount` | Số item reader đọc thành công. |
| `writeCount` | Số item được writer ghi thành công theo counter của step. |
| `filterCount` | Số item được processor chủ động lọc bằng cách trả về `null`. |
| `readSkipCount` | Số skip ở giai đoạn đọc. |
| `processSkipCount` | Số skip ở giai đoạn xử lý. |
| `writeSkipCount` | Số skip ở giai đoạn ghi. |
| `skipCount` | Tổng ba nhóm skip. |
| `commitCount` | Số lần transaction của step được commit. |
| `rollbackCount` | Số lần rollback được ghi nhận cho step. |

Ví dụ, một step đọc 1.000 item, processor lọc 20 item, skip 5 item do dữ liệu lỗi và ghi 975 item. Khi đó có thể thấy `filterCount=20`, `skipCount=5` và `writeCount=975` (giả sử không có các yếu tố khác ảnh hưởng counter).

Filter và skip là hai khái niệm khác nhau:

- **Filter:** processor trả về `null` để chủ động loại item theo quy tắc nghiệp vụ. Item bị filter không được tính là skip.
- **Skip:** một exception xảy ra và được skip policy cho phép. Framework ghi nhận item/lần đọc bị bỏ qua vào bộ đếm skip tương ứng.

Ví dụ processor trả về `null` cho đơn hàng có trạng thái `CANCELLED` là filter. Nếu processor ném `InvalidOrderException` và exception đó được cấu hình skip, item được tính vào `processSkipCount`.

## 4. Ba loại skip tương ứng với ba giai đoạn

Spring Batch phân biệt skip theo vị trí exception phát sinh.

### Read skip

`readSkipCount` tăng khi reader phát sinh exception và exception đó được cho phép skip. Ví dụ, `FlatFileItemReader` gặp một dòng không thể parse và ứng dụng cấu hình `FlatFileParseException` là skippable.

Trong lỗi đọc, đôi khi không có item Java hợp lệ để truyền cho listener vì reader chưa tạo được item. Vì vậy callback `onSkipInRead` chỉ nhận exception, không nhận item.

### Process skip

`processSkipCount` tăng khi `ItemProcessor` phát sinh exception được cho phép skip. Ví dụ processor kiểm tra dữ liệu và ném `InvalidOrderException` khi mã khách hàng không hợp lệ.

Item đầu vào đã được reader tạo ra, nhưng không thể chuyển thành item đầu ra. Framework bỏ qua item đó và tiếp tục theo cấu hình.

### Write skip

`writeSkipCount` tăng khi writer phát sinh exception và một hoặc nhiều item được xác định là có thể bỏ qua theo skip policy. Đây là trường hợp cần lưu ý vì writer thường nhận cả chunk. Framework phải xác định item nào gây lỗi ghi để có thể skip đúng item.

Ví dụ, một chunk có 100 đơn hàng nhưng một đơn hàng vi phạm unique constraint. Tùy loại writer, exception và cơ chế fault tolerance, Spring Batch có thể phải thử ghi hoặc phân tích các item để xác định item gây lỗi. Không nên giả định mọi writer đều có thể xác định item lỗi theo cùng một cách hoặc việc skip ở write luôn có chi phí thấp.

## 5. Cấu hình skipLimit

Để bật skip trong chunk-oriented step, thường dùng `.faultTolerant()`, `.skip(...)` và `.skipLimit(...)`.

Ví dụ theo API Spring Batch 5 trở lên:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(50)
            .build();
}
```

Trong ví dụ:

- `faultTolerant()` bật cấu hình xử lý lỗi như skip và retry cho step.
- `skip(...)` khai báo loại exception được phép bỏ qua.
- `skipLimit(50)` đặt giới hạn tổng skip cho step.

Giới hạn skip được áp dụng chung cho lỗi đọc, xử lý và ghi, không phải 50 lần cho mỗi giai đoạn. Nếu step đã skip đủ 50 item, lần skip tiếp theo sẽ làm step thất bại vì vượt giới hạn.

### Ví dụ về cách tính giới hạn

Giả sử cấu hình `.skipLimit(10)`:

| Lần skip | Kết quả |
|---:|---|
| 1 đến 9 | Được phép nếu exception thuộc loại skippable. |
| 10 | Vẫn nằm trong giới hạn. |
| 11 | Vượt giới hạn; step thất bại. |

Điều quan trọng là giới hạn được tính tổng qua các giai đoạn read, process và write. Ví dụ step đã có 4 read skip và 5 process skip thì tổng là 9. Nếu tiếp tục phát sinh một write skip, tổng đạt 10; skip tiếp theo sẽ vượt giới hạn 10.

## 6. Skip exception và noSkip

Không phải cứ cấu hình `faultTolerant()` là tất cả exception đều được skip. Ứng dụng cần chỉ định rõ loại exception được phép bỏ qua. Có thể dùng `.noSkip(...)` để loại trừ một loại exception khỏi chính sách skip.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(Exception.class)
        .noSkip(FileNotFoundException.class)
        .skipLimit(20)
        .build();
```

Ví dụ trên minh họa khả năng loại trừ exception cụ thể. Trong thực tế, cấu hình skip rộng như `Exception.class` thường nguy hiểm vì có thể biến lỗi hệ thống thành lỗi được bỏ qua. Nên khai báo những exception nghiệp vụ cụ thể mà ứng dụng có thể xử lý tiếp.

Một số nguyên tắc:

- Lỗi dữ liệu có thể được skip nếu có quy trình ghi nhận và đối soát.
- Lỗi kết nối, timeout hoặc database unavailable thường cần retry có giới hạn hoặc làm step thất bại.
- Lỗi cấu hình, thiếu file bắt buộc hoặc schema sai thường không nên bị skip.
- Nếu một exception có nhiều nguyên nhân khác nhau, cần phân loại rõ thay vì skip toàn bộ loại exception chung.

## 7. SkipPolicy tùy chỉnh

Khi quy tắc skip phụ thuộc vào nội dung exception, loại dữ liệu hoặc ngữ cảnh xử lý, có thể triển khai `SkipPolicy` tùy chỉnh.

Interface có phương thức quyết định một exception có được skip hay không:

```java
public interface SkipPolicy {
    boolean shouldSkip(Throwable t, long skipCount)
            throws SkipLimitExceededException;
}
```

Ví dụ policy cho phép skip một số lỗi dữ liệu, nhưng không cho phép skip lỗi hệ thống:

```java
public class OrderSkipPolicy implements SkipPolicy {

    private final long limit;

    public OrderSkipPolicy(long limit) {
        this.limit = limit;
    }

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException
                || throwable instanceof FlatFileParseException) {
            if (skipCount < limit) {
                return true;
            }
            throw new SkipLimitExceededException(limit, throwable);
        }

        return false;
    }
}
```

Gắn policy vào step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new OrderSkipPolicy(50))
        .build();
```

Ví dụ minh họa logic phân loại và giới hạn. Khi tự viết policy, cần hiểu tham số `skipCount` mà framework truyền vào, cách policy được gọi ở các giai đoạn khác nhau và cách xử lý exception lồng nhau (cause). Nên dùng policy đơn giản, xác định rõ các loại lỗi được phép bỏ qua và kiểm thử các ngưỡng biên.

## 8. Skip count trong StepExecution được cập nhật ra sao?

Trong quá trình thực thi, Spring Batch cập nhật các counter tương ứng với loại skip. Khi step kết thúc, metadata của `StepExecution` được lưu thông qua `JobRepository`.

Có thể truy cập counter trực tiếp trong listener hoặc khi tra cứu metadata:

```java
long total = stepExecution.getSkipCount();
long read = stepExecution.getReadSkipCount();
long process = stepExecution.getProcessSkipCount();
long write = stepExecution.getWriteSkipCount();
```

Các giá trị này gắn với một `StepExecution` cụ thể. Nếu job được restart, một `JobExecution` mới và các `StepExecution` mới có thể được tạo cho những step cần chạy lại. Vì vậy, không nên mặc định `skipCount` của execution mới là tổng tích lũy của mọi lần chạy trước trong cùng JobInstance.

Muốn báo cáo lịch sử đầy đủ, hãy truy vấn các `StepExecution` thuộc các `JobExecution` liên quan và tổng hợp theo JobInstance, business date hoặc batch reference. Cần giữ rõ mỗi số liệu thuộc execution nào để tránh cộng trùng.

## 9. Theo dõi skip bằng SkipListener

`SkipListener` cung cấp callback để ứng dụng ghi nhận item bị skip ở từng giai đoạn. Đây là nơi phù hợp để lưu thông tin lỗi, mã bản ghi và nguyên nhân, thay vì chỉ dựa vào tổng counter.

Các callback chính:

| Callback | Khi nào được gọi | Thông tin nhận được |
|---|---|---|
| `onSkipInRead(Throwable t)` | Một exception trong reader được skip. | Exception; có thể không có item vì đọc thất bại trước khi tạo item. |
| `onSkipInProcess(I item, Throwable t)` | Một item bị skip do exception trong processor. | Item đầu vào và exception. |
| `onSkipInWrite(O item, Throwable t)` | Một item bị skip do exception trong writer. | Item đầu ra và exception. |

Ví dụ listener:

```java
public class OrderSkipListener
        implements SkipListener<OrderInput, Order> {

    private final RejectedOrderService rejectedOrderService;

    public OrderSkipListener(RejectedOrderService rejectedOrderService) {
        this.rejectedOrderService = rejectedOrderService;
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        rejectedOrderService.recordReadFailure(
                throwable.getMessage(), throwable.getClass().getSimpleName());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        rejectedOrderService.recordRejectedOrder(
                item.orderId(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        rejectedOrderService.recordWriteFailure(
                item.orderId(), throwable.getMessage());
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
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .listener(orderSkipListener)
        .build();
```

Listener giúp lưu chi tiết từng lỗi, còn `StepExecution` counter cung cấp số liệu tổng hợp. Hai cơ chế bổ sung cho nhau.

### Lưu ý khi ghi nhận skip

SkipListener được thiết kế để nhận thông tin về item đã được quyết định skip. Với chunk processing, callback được gọi gần thời điểm commit để giảm nguy cơ ghi nhận skip cho một chunk sau đó bị rollback. Tuy nhiên, cách lưu lỗi vẫn cần phù hợp với transaction manager và tài nguyên mà `RejectedOrderService` sử dụng.

Nếu listener ghi vào database cùng transaction của chunk, bản ghi lỗi có thể được commit cùng trạng thái chunk. Nếu listener gọi hệ thống ngoài hoặc gửi message, thao tác đó không tự động rollback cùng database. Hãy dùng outbox hoặc cơ chế idempotency nếu cần bảo đảm không gửi trùng khi có lỗi ở ranh giới commit.

Đối với read skip, listener không có item hợp lệ để cung cấp. Nếu cần xác định dòng file, có thể lấy thông tin từ exception chuyên biệt như `FlatFileParseException`, vốn có thể chứa nội dung dòng và số dòng, nhưng cần tránh ghi log dữ liệu nhạy cảm.

## 10. Theo dõi skip count bằng StepExecutionListener

`StepExecutionListener` cho phép đọc counter sau khi step kết thúc. Đây là cách thuận tiện để ghi log tổng kết hoặc phát metric.

```java
public class StepSkipSummaryListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepSkipSummaryListener.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Step {} finished: status={}, readSkips={}, " +
                "processSkips={}, writeSkips={}, totalSkips={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getSkipCount());

        return null;
    }
}
```

`afterStep` nhận `StepExecution` của step vừa kết thúc. Trả về `null` nghĩa là listener không yêu cầu thay đổi `ExitStatus` hiện tại. Nếu listener trả về một ExitStatus khác, nó có thể ảnh hưởng kết quả flow; chỉ nên làm vậy khi có yêu cầu nghiệp vụ rõ ràng.

Đăng ký listener:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(stepSkipSummaryListener)
        .build();
```

Với job dài hoặc cần hiển thị status từ một màn hình riêng, có thể dùng `JobExplorer` để tra cứu `JobExecution` và các `StepExecution` sau khi metadata được lưu. Khi tra cứu lịch sử, hãy dùng đúng execution ID hoặc identifying parameters để không nhầm giữa các lần chạy.

## 11. Skip count và trạng thái COMPLETED

Một step có `skipCount` lớn hơn 0 vẫn có thể kết thúc với `BatchStatus.COMPLETED`, miễn là tất cả skip nằm trong chính sách cho phép và các phần việc còn lại hoàn tất.

Ví dụ:

```text
Step: importOrdersStep
BatchStatus: COMPLETED
readCount: 10000
writeCount: 9950
filterCount: 20
readSkipCount: 5
processSkipCount: 15
writeSkipCount: 5
skipCount: 25
```

Step đã hoàn tất theo quy tắc thực thi, nhưng không có nghĩa tất cả item đầu vào đều được ghi. Người vận hành cần đọc counter và danh sách lỗi để hiểu kết quả nghiệp vụ.

Nếu nghiệp vụ yêu cầu job thất bại khi có bất kỳ skip nào, hoặc khi số skip vượt một ngưỡng cảnh báo thấp hơn `skipLimit`, có thể dùng listener/flow logic để đánh giá kết quả và đặt ExitStatus phù hợp. Không nên thay đổi BatchStatus tùy tiện chỉ để hiển thị cảnh báo; hãy phân biệt thành công kỹ thuật với kết quả nghiệp vụ có cảnh báo.

## 12. Skip limit và giới hạn nghiệp vụ

`skipLimit` là ngưỡng bảo vệ step khỏi việc bỏ qua quá nhiều item. Nó không phải mục tiêu số lỗi được phép xảy ra và cũng không thay thế việc theo dõi tỷ lệ lỗi.

Ví dụ, cùng `skipLimit(100)` có ý nghĩa rất khác với hai batch:

- Batch A đọc 10.000.000 item và skip 80 item: tỷ lệ skip rất thấp.
- Batch B đọc 200 item và skip 80 item: tỷ lệ skip rất cao.

Vì vậy, ngoài giới hạn tuyệt đối, ứng dụng có thể cần theo dõi:

- Tổng số item bị skip.
- Tỷ lệ skip trên số item đã đọc hoặc số item có thể xử lý.
- Số skip theo từng loại exception.
- Số skip theo nguồn dữ liệu, nhóm nghiệp vụ hoặc partition.
- Xu hướng skip so với các lần chạy trước.

Nếu tỷ lệ skip vượt ngưỡng nghiệp vụ, job có thể kết thúc với ExitStatus tùy chỉnh như `COMPLETED_WITH_WARNINGS` hoặc `DATA_QUALITY_FAILED`, tùy chính sách. Cần xác định rõ liệu đó là kết quả hoàn tất có cảnh báo hay lỗi phải dừng quy trình.

## 13. Skip, retry và rollback khác nhau như thế nào?

Ba cơ chế này có thể cùng xuất hiện trong một fault-tolerant step nhưng phục vụ mục đích khác nhau.

| Cơ chế | Hành vi | Ảnh hưởng đến skip count |
|---|---|---|
| Skip | Bỏ qua item do exception được cho phép. | Tăng counter skip tương ứng khi item được xác nhận skip. |
| Retry | Thử lại thao tác/item khi exception được xem là có thể phục hồi. | Không tự động tăng skip count chỉ vì đã retry. Nếu cuối cùng item bị skip, mới được tính vào skip. |
| Rollback | Hoàn tác transaction hiện tại theo transaction manager. | Có thể khiến thao tác phải chạy lại; không đồng nghĩa với skip. |

Ví dụ, writer gặp lỗi timeout tạm thời. Step có thể retry writer. Nếu lần retry thành công, item được ghi và không phải skip. Nếu lỗi vẫn tiếp diễn và exception thuộc loại skippable, item có thể bị bỏ qua theo policy. Nếu lỗi không thể skip hoặc vượt giới hạn, step thất bại.

Không nên dùng skip để che lỗi hạ tầng có khả năng làm mất dữ liệu. Với lỗi tạm thời, retry có giới hạn thường phù hợp hơn. Với lỗi dữ liệu không thể xử lý, skip có thể phù hợp nếu có lưu vết và quy trình đối soát.

## 14. Skip ở giai đoạn write có thể phức tạp

Writer nhận một chunk thay vì một item. Nếu ghi cả chunk thất bại, framework cần xác định item nào gây lỗi để có thể skip đúng item. Với một số writer và loại exception, việc xác định này có thể cần nhiều lần thử ghi hoặc rollback.

Ví dụ, chunk gồm các đơn hàng A, B, C. Writer batch insert và database báo duplicate key cho một đơn hàng. Nếu exception không chỉ rõ item gây lỗi hoặc writer không thể phân loại, framework có thể không xác định được item cần skip và step sẽ thất bại.

Để write skip hoạt động đáng tin cậy:

- Exception cần được phân loại rõ và được cấu hình là skippable.
- Writer nên có hành vi xác định khi ghi một chunk.
- Không thực hiện tác dụng phụ bên ngoài transaction mà không có cơ chế idempotency.
- Kiểm tra writer có hỗ trợ cách xử lý lỗi item phù hợp với fault-tolerant step hay không.
- Kiểm thử tình huống một item lỗi nằm giữa chunk và quan sát counter thực tế.

Nếu lỗi là xung đột dữ liệu nghiêm trọng, bỏ qua item có thể che giấu vấn đề. Có thể cần ghi bản ghi vào vùng cách ly, kiểm tra dữ liệu tồn tại và xác định vì sao duplicate xảy ra.

## 15. Skip count khi restart

Counter skip thuộc về một `StepExecution` cụ thể. Khi step được restart, Spring Batch có thể tạo một `StepExecution` mới cho lần thực thi mới. Do đó, khi xem lịch sử, cần phân biệt counter của execution trước với counter của execution sau.

Ví dụ:

```text
JobInstance: importOrdersJob / businessDate=2026-11-15

JobExecution #1
  importOrdersStep StepExecution #101
    status = FAILED
    skipCount = 8

JobExecution #2 (restart)
  importOrdersStep StepExecution #205
    status = COMPLETED
    skipCount = 3
```

Không nên nhìn `skipCount=3` của execution mới rồi kết luận toàn bộ quá trình chỉ có 3 skip. Nếu cần báo cáo xuyên các lần restart, phải truy vấn lịch sử các StepExecution liên quan và tổng hợp theo quy tắc rõ ràng.

Tuy nhiên, việc cộng counter của mọi execution cũng cần thận trọng: một số item có thể đã được xử lý lại sau rollback hoặc restart. Cần phân biệt số lần skip được ghi nhận trong lịch sử với số bản ghi nghiệp vụ duy nhất bị loại. Muốn có số liệu duy nhất theo bản ghi, hãy lưu mã item và trạng thái lỗi trong bảng rejected/error với khóa nghiệp vụ phù hợp.

## 16. Skip count trong partitioning

Với partitioning, mỗi worker step có `StepExecution` riêng và counter skip riêng. Manager step có trạng thái điều phối tổng thể, nhưng không nên giả định `skipCount` của manager tự động là tổng mọi skip của worker.

Ví dụ:

```text
customerManagerStep
  |
  +-- worker partition0: skipCount = 2
  +-- worker partition1: skipCount = 7
  +-- worker partition2: skipCount = 1
```

Tổng skip của các worker trong ví dụ là 10. Để giám sát chính xác, cần truy vấn `StepExecution` của từng partition và cộng theo đúng JobExecution/worker step. Cũng cần giữ partition name hoặc partition key để biết lỗi tập trung ở phạm vi dữ liệu nào.

Nếu job có restart, hãy tách số liệu theo từng execution và partition. Không cộng nhầm counter của manager với worker hoặc cộng lặp những StepExecution đã được ghi nhận trong nhiều lần truy vấn.

## 17. Skip count và JobExplorer

`JobExplorer` cho phép đọc metadata đã lưu. Đây là cách phù hợp để hiển thị counter sau khi execution đã được ghi nhận trong repository.

Ví dụ tra cứu các step execution của một job execution:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        System.out.printf(
                "%s status=%s read=%d write=%d filter=%d " +
                "readSkip=%d processSkip=%d writeSkip=%d totalSkip=%d%n",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getFilterCount(),
                stepExecution.getReadSkipCount(),
                stepExecution.getProcessSkipCount(),
                stepExecution.getWriteSkipCount(),
                stepExecution.getSkipCount());
    }
}
```

Ví dụ này minh họa cách đọc counter của từng step. Nếu cần lịch sử của cùng JobInstance qua nhiều lần restart, hãy lấy các JobExecution thuộc instance đó rồi đọc StepExecution của từng execution.

Khi xây dựng API giám sát, nên trả cả step name, execution ID, status và ba counter thành phần. Một con số tổng đơn lẻ không cho biết lỗi đến từ đọc, xử lý hay ghi.

## 18. Ghi nhận lỗi bị skip để có thể đối soát

Counter cho biết số lượng nhưng không cho biết item nào bị bỏ qua. Trong ứng dụng thực tế, thường cần một nơi lưu lỗi chi tiết.

Một bảng rejected record có thể có các cột:

| Cột | Mục đích |
|---|---|
| `job_execution_id` | Lần thực thi job ghi nhận lỗi. |
| `step_execution_id` | Step cụ thể phát sinh skip. |
| `item_key` | Khóa nghiệp vụ của item nếu xác định được. |
| `skip_phase` | `READ`, `PROCESS` hoặc `WRITE`. |
| `exception_type` | Loại exception. |
| `error_message` | Thông tin lỗi đã được làm sạch. |
| `created_at` | Thời điểm ghi nhận. |
| `partition_name` | Phân vùng xử lý nếu step đang partition. |

Với read skip, `item_key` có thể không có vì reader chưa tạo được item. Khi đó có thể lưu số dòng file hoặc vị trí nguồn nếu exception cung cấp thông tin này.

Nên có unique key phù hợp nếu cùng một item có thể được ghi nhận nhiều lần qua retry/restart. Ví dụ, khóa theo execution, step, item key và loại lỗi có thể giúp phân biệt lịch sử từng lần chạy với danh sách item nghiệp vụ duy nhất bị loại.

Không lưu toàn bộ payload nhạy cảm hoặc stack trace không giới hạn vào bảng lỗi. Chỉ lưu thông tin cần thiết để điều tra, bảo đảm quyền truy cập và thời hạn lưu giữ phù hợp.

## 19. Quyết định flow dựa trên skip count

Một job có thể cần xử lý tiếp khi skip count nằm trong giới hạn, nhưng kết thúc theo nhánh cảnh báo nếu số skip vượt ngưỡng nghiệp vụ. Có thể dùng listener để đánh giá counter và trả ExitStatus tùy chỉnh.

Ví dụ listener:

```java
public class SkipThresholdListener implements StepExecutionListener {

    private final long warningThreshold;

    public SkipThresholdListener(long warningThreshold) {
        this.warningThreshold = warningThreshold;
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getSkipCount() > warningThreshold) {
            return new ExitStatus("COMPLETED_WITH_WARNINGS");
        }
        return null;
    }
}
```

Ví dụ này đặt một ngưỡng cảnh báo thấp hơn hoặc bằng skip limit. Nó không thay thế `skipLimit`; nếu vượt skip limit trong lúc thực thi, step đã thất bại trước khi hoàn tất. Listener chỉ đánh giá số skip của step sau khi step chạy xong.

Flow của job có thể định tuyến theo ExitStatus:

```java
return new JobBuilder("importOrdersJob", jobRepository)
        .start(importOrdersStep)
            .on("COMPLETED_WITH_WARNINGS").to(warningReportStep)
        .from(importOrdersStep)
            .on("COMPLETED").to(successReportStep)
        .from(warningReportStep)
            .on("*").end()
        .from(successReportStep)
            .on("*").end()
        .end()
        .build();
```

Đây là ví dụ về ý tưởng điều khiển flow. Trong ứng dụng thật, cần khai báo đầy đủ các transition cho trạng thái lỗi và xác định trạng thái cuối của job. Không nên để một job kết thúc `COMPLETED` nếu ngưỡng skip đã vi phạm yêu cầu nghiệp vụ bắt buộc.

## 20. Các lỗi thường gặp khi đọc và sử dụng skip count

| Vấn đề | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| `skipCount` bằng 0 dù có item bị loại | Processor trả về `null`, đây là filter chứ không phải skip. | Kiểm tra `filterCount` và logic processor. |
| Step FAILED sau lần skip thứ N | Tổng skip đã vượt `skipLimit`. | Kiểm tra tổng skip ở cả read/process/write và điều chỉnh policy theo nghiệp vụ. |
| Chỉ biết tổng skip, không biết lỗi ở đâu | Chỉ đọc `getSkipCount()`. | Đọc ba counter thành phần và dùng SkipListener. |
| Read skip không có item để ghi log | Reader lỗi trước khi tạo item. | Ghi exception, vị trí dòng hoặc thông tin nguồn nếu có. |
| Writer skip không hoạt động như mong đợi | Writer nhận chunk và exception không xác định được item gây lỗi. | Kiểm tra writer, exception và fault-tolerant behavior. |
| Counter sau restart nhỏ hơn lịch sử | Đang xem StepExecution mới thay vì tổng các lần chạy. | Truy vấn các JobExecution/StepExecution liên quan và tổng hợp có quy tắc. |
| SkipListener ghi lỗi trùng | Tác dụng phụ listener không idempotent hoặc ranh giới transaction chưa được tính đến. | Dùng khóa chống trùng hoặc outbox và lưu execution/item identity. |
| Job COMPLETED nhưng dữ liệu thiếu | Skip nằm trong giới hạn nên step vẫn hoàn tất. | Kiểm tra counter, tỷ lệ skip và kết quả nghiệp vụ. |
| Skip quá nhiều nhưng không bị dừng | Cấu hình skip exception quá rộng hoặc skip limit không phản ánh yêu cầu. | Thu hẹp exception được phép skip và đặt ngưỡng rõ ràng. |

## 21. Quy trình phân tích một step có skip count cao

Khi một step có số skip bất thường, có thể điều tra theo trình tự:

1. **Xác định execution:** lấy JobExecution ID, StepExecution ID và JobInstance tương ứng.
2. **Đọc trạng thái:** kiểm tra `BatchStatus`, `ExitStatus`, thời gian và exception cuối cùng.
3. **Tách counter:** xem `readSkipCount`, `processSkipCount`, `writeSkipCount` và `filterCount`.
4. **Xem skip policy:** xác định exception nào được phép skip và `skipLimit` hiện tại.
5. **Tra cứu chi tiết lỗi:** dùng SkipListener hoặc bảng rejected record để tìm item, dòng file và exception.
6. **So sánh với dữ liệu đầu vào:** xác định lỗi do chất lượng dữ liệu, mapping, quy tắc nghiệp vụ hay hệ thống đích.
7. **Đánh giá tỷ lệ:** so sánh số skip với tổng item và với các lần chạy trước.
8. **Kiểm tra restart/retry:** xác định có item nào bị xử lý lại hoặc lỗi bị ghi nhận nhiều lần không.
9. **Quyết định xử lý:** sửa nguồn, điều chỉnh quy tắc, retry lỗi tạm thời hoặc đưa item vào quy trình đối soát.
10. **Theo dõi lần chạy tiếp theo:** xác nhận counter giảm về mức mong đợi và dữ liệu lỗi đã được xử lý.

Không nên tăng `skipLimit` chỉ để job chạy qua. Nếu lỗi xuất phát từ file sai cấu trúc, database mất kết nối hoặc writer ghi sai schema, tăng giới hạn có thể làm job tiếp tục trong khi dữ liệu đầu ra không còn đáng tin cậy.

## 22. Những điểm cần ghi nhớ

- `StepExecution` lưu `readSkipCount`, `processSkipCount`, `writeSkipCount` và `skipCount` tổng.
- `skipCount` là tổng skip ở giai đoạn read, process và write.
- Filter do processor trả về `null` được tính vào `filterCount`, không phải skip count.
- `skipLimit` áp dụng chung cho cả ba giai đoạn; nếu vượt giới hạn, step thất bại.
- Skip chỉ áp dụng cho exception được policy cho phép; lỗi hệ thống không nên bị skip một cách tùy tiện.
- `SkipListener` cung cấp callback riêng cho read, process và write để ghi nhận chi tiết lỗi.
- `StepExecutionListener.afterStep` có thể đọc counter để log hoặc đánh giá ngưỡng cảnh báo.
- `BatchStatus.COMPLETED` vẫn có thể đi kèm skip count lớn hơn 0 nếu policy cho phép.
- Counter thuộc một StepExecution cụ thể; khi restart cần xem lịch sử execution nếu muốn tổng hợp xuyên nhiều lần chạy.
- Với partitioning, mỗi worker có counter riêng; muốn có tổng phải tổng hợp StepExecution của các partition đúng phạm vi.
- Retry và rollback không tự động đồng nghĩa với skip; chỉ item được quyết định bỏ qua mới làm tăng skip counter.
- Nên lưu chi tiết item bị skip và nguyên nhân để có thể đối soát, sửa dữ liệu và báo cáo chất lượng.

Khi theo dõi một batch job, hãy xem cả tổng `skipCount` lẫn ba counter thành phần, `filterCount`, trạng thái step và danh sách lỗi chi tiết. Những thông tin này cho biết item bị loại ở đâu, vì sao step vẫn hoàn tất hoặc thất bại, và liệu kết quả đầu ra có đáp ứng yêu cầu nghiệp vụ hay không.
