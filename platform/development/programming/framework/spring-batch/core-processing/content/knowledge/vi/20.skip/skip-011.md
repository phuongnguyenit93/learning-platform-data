# Skip khi restart

Trong Spring Batch, **skip** cho phép Step bỏ qua một item khi lỗi thuộc loại được phép bỏ qua và số lần skip chưa vượt giới hạn cấu hình. Khi Job thất bại vì một lỗi khác hoặc vì đã vượt skip limit, ứng dụng có thể restart cùng JobInstance. Khi restart, Spring Batch dựa vào metadata, trạng thái Step và checkpoint đã commit để xác định phần công việc cần tiếp tục.

Điều quan trọng là phân biệt item đã được skip trong một chunk đã commit với item gặp lỗi trong chunk bị rollback. Item đã skip trong phần công việc đã commit thường nằm trước checkpoint và không được đọc lại khi restart. Nếu chunk chưa commit, trạng thái đọc và thay đổi của chunk có thể bị rollback; khi restart, item trong chunk đó có thể được đọc và xử lý lại, khiến quyết định skip được thực hiện lần nữa.

## 1. Skip trong Spring Batch là gì?

Trong chunk-oriented Step, lỗi có thể xảy ra khi đọc, xử lý hoặc ghi item. Nếu exception được cấu hình là skippable và chưa vượt skip limit, Spring Batch có thể bỏ qua item lỗi và tiếp tục xử lý các item còn lại.

Ba vị trí skip chính:

- **Read skip:** `ItemReader` ném exception khi đọc dữ liệu, ví dụ một dòng file sai định dạng.
- **Process skip:** `ItemProcessor` ném exception cho một item không hợp lệ.
- **Write skip:** `ItemWriter` ném exception khi ghi một item hoặc nhóm item; với writer theo nhóm, framework cần xác định item gây lỗi theo cơ chế phù hợp.

Ví dụ cấu hình Step cho phép bỏ qua tối đa 10 lỗi dữ liệu:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, ProcessedOrder> processor,
        ItemWriter<ProcessedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .skip(FlatFileParseException.class)
            .skip(InvalidOrderException.class)
            .skipLimit(10)
            .build();
}
```

Ví dụ giả định `Order`, `ProcessedOrder` và `InvalidOrderException` là kiểu của ứng dụng. `FlatFileParseException` đại diện cho lỗi parse dòng file. Những exception không được phân loại là skippable sẽ làm Step thất bại theo chính sách xử lý lỗi.

## 2. Skip khác filter và retry

Ba cơ chế này có mục đích khác nhau:

| Cơ chế | Cách hoạt động | Bộ đếm liên quan |
|---|---|---|
| Filter | Processor trả về `null`; item được loại khỏi luồng mà không có exception. | `filterCount` |
| Skip | Reader, Processor hoặc Writer ném exception được phép bỏ qua. | `readSkipCount`, `processSkipCount`, `writeSkipCount`, `skipCount` |
| Retry | Framework thử lại thao tác gặp lỗi, thường dùng cho lỗi tạm thời. | Retry được quản lý theo retry policy; không phải skip count |

Ví dụ:

- Đơn hàng đã hủy nhưng dữ liệu hợp lệ: processor trả `null` để filter.
- Dòng CSV không parse được và được cho phép bỏ qua: read skip.
- Mã khách hàng không tồn tại và được cho phép bỏ qua: process skip.
- Database tạm thời deadlock: retry trước khi quyết định tiếp tục hay thất bại.

Không nên trả `null` chỉ để tránh Job thất bại nếu bản ghi thực sự không hợp lệ và cần được ghi nhận. Ngược lại, không nên ném exception cho một điều kiện lọc nghiệp vụ bình thường.

## 3. Skip limit được áp dụng như thế nào?

`skipLimit(n)` đặt giới hạn tổng số skip cho Step execution, tính trên các lỗi skip ở giai đoạn đọc, xử lý và ghi. Khi số skip vẫn nằm trong giới hạn, item lỗi được bỏ qua. Khi một lỗi skip tiếp theo làm vượt giới hạn, Step thất bại.

Ví dụ với `skipLimit(10)`:

| Số skip tích lũy trong lần thực thi Step | Kết quả |
|---:|---|
| 0 đến 9 | Các lỗi skippable tiếp theo có thể được bỏ qua. |
| 10 | Lỗi thứ 10 vẫn nằm trong giới hạn và được skip. |
| 11 | Lỗi tiếp theo vượt giới hạn; Step thất bại. |

Giới hạn được tính chung cho read, process và write skip, không phải 10 lỗi cho mỗi giai đoạn. Vì vậy, nếu có 4 read skip, 3 process skip và 3 write skip thì tổng là 10.

Skip limit không có nghĩa mọi exception đều được bỏ qua. Cần khai báo loại exception được phép skip; exception không nằm trong chính sách sẽ làm Step thất bại. Có thể dùng `.noSkip(...)` để loại trừ một loại exception khỏi nhóm skip nếu chính sách rộng hơn đã được khai báo.

Về vận hành, hãy xem skip limit là giới hạn của lần thực thi Step hiện tại. Nếu yêu cầu nghiệp vụ là giới hạn tích lũy xuyên nhiều lần restart hoặc nhiều JobExecution, cần lưu bộ đếm nghiệp vụ bền vững theo mã lô/JobInstance và kiểm tra riêng; không nên chỉ dựa vào `skipLimit`.

## 4. Điều gì được lưu khi một chunk commit?

Spring Batch lưu metadata thực thi và trạng thái cần cho restart thông qua `JobRepository`. Với reader triển khai `ItemStream`, phương thức `update(ExecutionContext)` có thể lưu checkpoint, chẳng hạn vị trí đọc hiện tại. Trạng thái được lưu tại ranh giới commit phù hợp với transaction của chunk.

Ví dụ Step đọc file với `FlatFileItemReader`:

```java
FlatFileItemReader<Order> reader =
        new FlatFileItemReaderBuilder<Order>()
                .name("orderFileReader")
                .resource(new FileSystemResource("data/orders.csv"))
                .delimited()
                .names("id", "customerId", "amount")
                .targetType(Order.class)
                .saveState(true)
                .build();
```

`saveState(true)` cho phép reader lưu thông tin cần thiết để khôi phục vị trí đọc khi restart. Với reader hỗ trợ restart, checkpoint thường phản ánh vị trí đã được xử lý đến ranh giới commit gần nhất.

Một chunk có thể gồm item hợp lệ và item bị skip. Khi chunk commit thành công, thay đổi dữ liệu của chunk và checkpoint tương ứng được lưu. Khi restart, reader thường tiếp tục sau checkpoint đó; các item đã xử lý trong chunk đã commit, bao gồm item bị skip, không cần được đọc lại.

## 5. Skip khi chunk đã commit và khi chunk rollback

Đây là khác biệt quan trọng nhất khi hiểu skip trong restart.

### Trường hợp A: chunk có skip đã commit

Giả sử chunk 1 có 5 item, trong đó item thứ 3 không hợp lệ và được skip. Writer ghi các item hợp lệ còn lại; chunk commit thành công:

```text
Chunk 1
  Item 1 -> ghi
  Item 2 -> ghi
  Item 3 -> SKIP
  Item 4 -> ghi
  Item 5 -> ghi
       |
       v
    COMMIT
       |
       +--> Dữ liệu đã ghi được giữ
       +--> Checkpoint được cập nhật
       +--> Skip đã thuộc phần công việc hoàn tất
```

Nếu Job thất bại ở chunk 2 và sau đó restart, reader có thể tiếp tục sau checkpoint của chunk 1. Item thứ 3 không được đọc lại trong lần restart thông thường, vì phần chunk chứa item đó đã hoàn tất và checkpoint đã được lưu.

### Trường hợp B: chunk chưa commit và bị rollback

Giả sử một item trong chunk được skip, nhưng sau đó Writer gặp lỗi không thể skip và làm transaction của chunk thất bại:

```text
Chunk 2
  Item 6 -> ghi tạm
  Item 7 -> SKIP
  Item 8 -> ghi tạm
  Item 9 -> lỗi không được skip
       |
       v
    ROLLBACK
       |
       +--> Thay đổi nghiệp vụ của chunk bị hoàn tác
       +--> Checkpoint mới chưa được commit
       +--> Chunk có thể được đọc/xử lý lại khi restart
```

Sau rollback, trạng thái bền vững vẫn là checkpoint của chunk trước. Khi restart, reader có thể đọc lại các item trong chunk 2. Item 7 có thể lại gây lỗi và được skip lần nữa. Vì vậy, hệ thống ghi reject record hoặc gửi thông báo skip cần có cơ chế chống trùng.

### Bảng tổng hợp

| Tình huống | Checkpoint | Item đã skip có thể xuất hiện lại? |
|---|---|---|
| Chunk có skip và commit thành công | Được cập nhật tới ranh giới commit | Thông thường không, nếu reader khôi phục đúng checkpoint. |
| Chunk có skip nhưng sau đó rollback | Giữ checkpoint của chunk commit trước đó | Có thể, vì item thuộc phần chunk cần đọc lại. |
| Reader không lưu state | Không có checkpoint đọc đáng tin cậy | Có thể phải đọc lại nhiều hoặc toàn bộ dữ liệu; writer cần idempotent. |
| Job/Step được thiết kế chạy lại từ đầu | Phụ thuộc cấu hình và cách khởi tạo dữ liệu | Có thể, cần chính sách chống trùng rõ ràng. |

## 6. Restart một Job sau khi Step thất bại

Khi Job thất bại, Spring Batch giữ metadata của JobInstance, JobExecution và StepExecution. Nếu Job cho phép restart, có thể gọi lại cùng Job với cùng identifying JobParameters. Spring Batch tạo JobExecution mới cho cùng JobInstance và xử lý Step theo trạng thái trước đó.

Ví dụ:

```text
JobInstance: importOrders / fileId=orders-2026-11-15
  |
  +--> JobExecution #1: FAILED
  |       importOrdersStep: FAILED
  |       Chunk 1: COMMITTED (có 1 skip)
  |       Chunk 2: ROLLED BACK
  |
  +--> JobExecution #2: COMPLETED
          importOrdersStep: tiếp tục từ checkpoint đã commit
          Chunk 1: không đọc lại trong restart thông thường
          Chunk 2: được đọc/xử lý lại theo trạng thái reader
```

Các điều kiện cần có:

- Job không bị cấu hình `preventRestart()`.
- Step thất bại có thể restart.
- Reader hỗ trợ lưu/khôi phục state nếu cần tiếp tục từ checkpoint.
- Tên reader ổn định giữa các lần chạy.
- Cùng identifying JobParameters được dùng để restart đúng JobInstance.
- Writer và các tác dụng phụ có khả năng xử lý lặp an toàn.

Một Step đã `COMPLETED` thường được bỏ qua khi restart. Nếu cấu hình `allowStartIfComplete(true)`, Step đã hoàn tất có thể được chạy lại; khi đó các item đã skip trước đây cũng có thể được gặp lại tùy reader và dữ liệu nguồn.

## 7. Skip count và metadata của StepExecution

Spring Batch theo dõi các bộ đếm skip trên `StepExecution`:

| Thuộc tính | Ý nghĩa |
|---|---|
| `getReadSkipCount()` | Số lỗi đọc được skip trong StepExecution. |
| `getProcessSkipCount()` | Số lỗi xử lý được skip. |
| `getWriteSkipCount()` | Số lỗi ghi được skip. |
| `getSkipCount()` | Tổng skip count. |
| `getReadCount()` | Số item đã đọc. |
| `getWriteCount()` | Số item đã ghi. |
| `getFilterCount()` | Số item bị filter do processor trả `null`. |
| `getRollbackCount()` | Số lần rollback được ghi nhận. |

Các bộ đếm giúp điều tra một lần thực thi Step. Khi restart, cần phân biệt StepExecution cũ với StepExecution mới: mỗi lần thực thi có metadata riêng. Nếu cần báo cáo tổng số bản ghi bị skip của toàn bộ lịch sử JobInstance, hãy tổng hợp các StepExecution liên quan trong JobExplorer/JobRepository hoặc lưu số liệu nghiệp vụ vào bảng audit riêng. Không nên chỉ đọc skip count của execution mới rồi xem đó là tổng số skip của mọi lần chạy.

Ví dụ đọc bộ đếm sau khi Step hoàn tất:

```java
for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
    System.out.printf(
            "step=%s, readSkip=%d, processSkip=%d, writeSkip=%d, totalSkip=%d%n",
            stepExecution.getStepName(),
            stepExecution.getReadSkipCount(),
            stepExecution.getProcessSkipCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getSkipCount());
}
```

Để tổng hợp qua nhiều JobExecution của cùng JobInstance, cần lấy các execution lịch sử tương ứng rồi cộng các bộ đếm của StepExecution theo đúng định nghĩa báo cáo. Tránh cộng cả những lần chạy lại cùng một chunk nếu báo cáo muốn đếm số bản ghi nghiệp vụ duy nhất thay vì số lần skip xảy ra.

## 8. Ghi nhận item bị skip bằng SkipListener

`SkipListener` cung cấp callback riêng cho read, process và write skip. Đây là nơi phù hợp để ghi nhận bản ghi lỗi, lưu nguyên nhân hoặc đưa item vào reject flow.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;

public class OrderSkipListener
        implements SkipListener<Order, ProcessedOrder> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable throwable) {
        log.warn("Skipping unreadable input: {}", throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(Order item, Throwable throwable) {
        log.warn("Skipping order {} during processing: {}",
                item.id(), throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(ProcessedOrder item, Throwable throwable) {
        log.warn("Skipping order {} during writing: {}",
                item.id(), throwable.getMessage());
    }
}
```

Đăng ký listener trong Step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(10)
        .listener(orderSkipListener)
        .build();
```

`onSkipInRead()` không nhận item vì Reader có thể thất bại trước khi tạo ra một đối tượng hoàn chỉnh. Với `FlatFileParseException`, có thể lấy thông tin dòng đầu vào từ exception nếu cần lưu nội dung reject, nhưng cần giới hạn dữ liệu nhạy cảm và kích thước log.

## 9. Tránh ghi reject trùng khi restart

SkipListener có thể được gọi lại nếu chunk bị rollback và item được đọc/xử lý lại khi restart. Vì vậy, không nên giả định một callback tương ứng với một bản ghi lỗi duy nhất trong toàn bộ vòng đời JobInstance.

Ví dụ, listener ghi reject vào bảng `batch_reject`:

```text
batch_reject
-------------------------------------------------
job_instance_key | source_record_key | error_code
-------------------------------------------------
2026-11-15       | ORD-1007           | INVALID_AMOUNT
```

Có thể đặt khóa duy nhất trên tổ hợp mã JobInstance và khóa bản ghi nguồn. Khi cùng item bị skip lại sau restart, thao tác ghi reject dùng upsert hoặc insert có kiểm soát để không tạo dòng trùng.

Các lựa chọn thiết kế:

1. **Unique key và upsert:** định danh reject bằng JobInstance/partition/source key và cập nhật thông tin lỗi nếu cần.
2. **Transactional write:** ghi reject trong transaction của chunk khi tài nguyên và transaction manager cho phép, để reject record rollback cùng chunk.
3. **Outbox:** ghi sự kiện reject trong transaction nghiệp vụ rồi gửi sang hệ thống ngoài sau commit.
4. **Idempotency key:** khi gửi lỗi sang API hoặc message broker, dùng mã duy nhất để hệ thống nhận loại bỏ sự kiện trùng.

Nếu listener ghi file hoặc gửi email trực tiếp, các tác dụng phụ đó không tự rollback cùng transaction database. Khi chunk rollback, lần chạy lại có thể tạo file/email trùng. Hãy tách việc gửi thông báo khỏi callback hoặc dùng cơ chế chống trùng bền vững.

## 10. Kết hợp retry và skip khi restart

Retry thường dành cho lỗi tạm thời, còn skip dành cho lỗi item được phép bỏ qua. Một exception có thể được thử lại trước; nếu retry hết giới hạn và exception thuộc nhóm skippable, item có thể được skip. Nếu exception không được retry hoặc không được skip, Step thất bại.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(10)
        .listener(orderSkipListener)
        .build();
```

Ví dụ này retry lỗi truy cập dữ liệu tạm thời tối đa theo giới hạn cấu hình và skip lỗi đơn hàng không hợp lệ. Khi Job restart, item trong chunk đã commit sẽ không được xử lý lại nếu checkpoint hoạt động đúng; item trong chunk rollback có thể được thử lại và có thể đi qua retry/skip policy lần nữa.

Không nên dùng retry cho lỗi dữ liệu không thể tự sửa, ví dụ mã khách hàng sai định dạng. Cũng không nên skip lỗi hạ tầng tạm thời ngay lập tức nếu một lần retry có thể khắc phục. Phân loại exception rõ ràng giúp Job có hành vi restart dễ dự đoán.

## 11. SkipPolicy tùy chỉnh

Khi quy tắc skip phức tạp hơn danh sách exception cố định, có thể triển khai `SkipPolicy`. Policy nhận exception và số lượng skip hiện tại, sau đó quyết định có cho phép bỏ qua hay không.

```java
import org.springframework.batch.core.step.skip.SkipLimitExceededException;
import org.springframework.batch.core.step.skip.SkipPolicy;

public class BusinessSkipPolicy implements SkipPolicy {

    @Override
    public boolean shouldSkip(Throwable throwable, long skipCount)
            throws SkipLimitExceededException {

        if (throwable instanceof InvalidOrderException) {
            return skipCount < 10;
        }

        return false;
    }
}
```

Đăng ký policy:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skipPolicy(new BusinessSkipPolicy())
        .build();
```

Khi dùng `skipPolicy`, policy tự quyết định điều kiện skip và giới hạn. Không nên đồng thời cấu hình các rule `skip()`/`skipLimit()` theo cách gây khó hiểu về thứ tự ưu tiên. Policy tùy chỉnh cần có unit test cho loại exception, ngưỡng skip và hành vi khi vượt ngưỡng.

Nếu ngưỡng phải tích lũy xuyên nhiều lần restart, policy có thể cần truy vấn một kho trạng thái bền vững theo mã JobInstance/lô. Tránh dùng một biến `long skipCount` trong field singleton vì nhiều JobExecution đồng thời hoặc restart có thể làm số đếm sai.

## 12. Các trường hợp Step không được chạy lại khi restart

Restart không có nghĩa toàn bộ Job luôn chạy lại từ Step đầu tiên. Spring Batch xem trạng thái các Step trong JobExecution trước:

- Step đã `COMPLETED` thường được bỏ qua trong lần restart.
- Step thất bại có thể được chạy lại nếu Job và Step cho phép restart.
- Step có `allowStartIfComplete(true)` có thể được chạy lại ngay cả khi lần trước đã hoàn tất.

Điều này ảnh hưởng đến skip:

- Nếu Step chứa skip đã hoàn tất và được bỏ qua khi restart, những item đã skip trong Step đó không được đọc lại chỉ vì Job được restart.
- Nếu Step được chạy lại do `allowStartIfComplete(true)` hoặc một JobInstance mới, dữ liệu có thể được đọc lại và các item lỗi có thể bị skip lần nữa.
- Nếu Step thất bại trong một chunk chưa commit, item trong chunk đó có thể được xử lý lại từ checkpoint gần nhất.

Chỉ bật `allowStartIfComplete(true)` khi Step có thể chạy lặp an toàn. Với Step gửi thông báo, tạo file hoặc cập nhật dữ liệu bên ngoài, cần có idempotency hoặc chính sách ghi đè rõ ràng.

## 13. Kiểm thử skip và restart

Unit test cho processor hoặc SkipPolicy giúp xác nhận exception nào được skip. Integration test cần xác nhận checkpoint, skip count, dữ liệu reject và trạng thái Job sau restart.

Một kịch bản kiểm thử hữu ích:

1. Chuẩn bị file có một item hợp lệ, một item lỗi định dạng được skip và một item làm writer thất bại không thể skip.
2. Chạy Job lần đầu; xác nhận chunk trước lỗi đã commit, chunk chứa lỗi writer bị rollback và Job kết thúc `FAILED`.
3. Xác nhận `StepExecution` lưu các bộ đếm read/process/write skip và checkpoint theo lần thực thi.
4. Sửa điều kiện writer để lần chạy tiếp theo có thể hoàn tất.
5. Restart cùng JobInstance bằng cùng identifying JobParameters.
6. Xác nhận reader tiếp tục từ checkpoint đã commit, item thuộc chunk rollback được xử lý lại và item đã skip trong chunk commit không bị đọc lại.
7. Kiểm tra reject table không có bản ghi trùng dù callback có thể được thực hiện lại cho item của chunk rollback.

Với Spring Batch Test, `JobLauncherTestUtils` có thể launch Job hoặc Step; `JobExplorer`/`JobRepository` hỗ trợ tra cứu các JobExecution và StepExecution sau mỗi lần chạy. Khi test restart, không thêm UUID identifying parameter mới giữa hai lần launch vì điều đó tạo JobInstance khác.

Các assertion nên bao gồm:

- Trạng thái `BatchStatus` và `ExitStatus` của từng JobExecution.
- Số read/process/write skip của từng StepExecution.
- Checkpoint hoặc dữ liệu đầu ra sau commit.
- Số reject record duy nhất theo khóa nghiệp vụ.
- ID JobInstance giống nhau và JobExecution ID khác nhau giữa lần đầu và lần restart.

## 14. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Nghĩ item đã skip sẽ không bao giờ xuất hiện lại | Item thuộc chunk rollback hoặc Step được chạy lại. | Phân biệt skip đã commit với skip trong chunk chưa commit; thiết kế reject idempotent. |
| Dùng `skipLimit` như giới hạn toàn bộ lịch sử JobInstance | Skip limit được áp dụng cho Step execution; các execution có metadata riêng. | Tự quản lý ngưỡng nghiệp vụ tích lũy nếu cần. |
| Nhầm filter với skip | Processor trả `null` không phải exception skip. | Kiểm tra `filterCount` và các skip count riêng. |
| Skip mọi exception | Lỗi hạ tầng hoặc lỗi lập trình có thể bị che giấu. | Chỉ skip exception dữ liệu đã xác định; để lỗi nghiêm trọng làm Step thất bại. |
| Reject listener ghi trùng sau restart | Tác dụng phụ đã xảy ra nhưng chunk chưa commit hoặc callback được gọi lại. | Dùng unique key, upsert, outbox hoặc idempotency key. |
| Reader không lưu state | Restart có thể đọc lại từ đầu hoặc không khôi phục được vị trí. | Dùng reader hỗ trợ `ItemStream` và lưu checkpoint. |
| Đổi identifying JobParameters khi restart | Spring Batch tạo JobInstance mới. | Giữ nguyên identifying parameters để restart đúng instance. |
| Chỉ xem skip count của execution mới | Bỏ qua lịch sử skip ở các execution trước. | Tổng hợp StepExecution lịch sử hoặc dùng audit nghiệp vụ. |

## Kết luận

Skip khi restart phụ thuộc vào ranh giới commit và checkpoint của Step. Item đã skip trong chunk đã commit thường nằm trước checkpoint nên không được đọc lại khi restart thông thường. Item thuộc chunk bị rollback có thể được đọc và skip lại vì trạng thái bền vững vẫn ở checkpoint trước đó. Vì vậy, cần phân biệt skip với filter và retry, cấu hình exception cùng skip limit rõ ràng, dùng reader hỗ trợ lưu state và ghi reject theo cách idempotent. Khi cần giới hạn skip xuyên nhiều lần restart, hãy quản lý bộ đếm nghiệp vụ bền vững thay vì chỉ dựa vào skip limit của một Step execution.
