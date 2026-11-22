# Đối chiếu input, skipped và output counts

Trong Spring Batch, số bản ghi đầu vào, số bản ghi bị bỏ qua (*skipped*) và số bản ghi đầu ra được theo dõi ở những bộ đếm khác nhau. Muốn biết một bước xử lý đã xử lý hết dữ liệu hay chưa, cần đọc các bộ đếm theo đúng giai đoạn `read`, `process` và `write`, sau đó đối chiếu chúng trên cùng một lần thực thi của `StepExecution`.

Điểm quan trọng là `readCount`, `writeCount`, `filterCount` và các skip count không đo cùng một việc. Một item được đọc thành công có thể được ghi ra, bị lọc có chủ đích, hoặc bị bỏ qua vì lỗi ở giai đoạn xử lý hay ghi. Một lỗi đọc được chấp nhận theo skip policy lại được ghi nhận riêng, vì item đó chưa được đọc thành công.

## 1. Xác định đơn vị cần đếm

Trước khi so sánh số liệu, hãy xác định “một input” và “một output” đang có nghĩa là gì trong step.

- **Input item** là một item mà `ItemReader` cung cấp cho Spring Batch. Nó có thể tương ứng với một dòng file, một hàng cơ sở dữ liệu, một message hoặc một đối tượng được tạo từ nhiều dòng nguồn.
- **Output item** là một item được chuyển tới `ItemWriter` và được ghi thành công theo hợp đồng của writer.
- **Output record/row** là số bản ghi vật lý được tạo trong hệ thống đích. Số này có thể khác `writeCount` nếu một item tạo ra nhiều hàng, hoặc writer ghi theo một cấu trúc khác.

Ví dụ, một `ItemReader` đọc từng đơn hàng và một `ItemWriter` ghi mỗi đơn hàng thành một hàng thì `writeCount` có thể được so sánh trực tiếp với số hàng đầu ra. Nếu writer tách một đơn hàng thành ba dòng chi tiết, `writeCount` vẫn đếm số item đơn hàng đã ghi thành công; nó không tự động trở thành số dòng chi tiết.

Hãy ghi rõ đơn vị trong báo cáo, chẳng hạn “input items”, “written order items” hoặc “database rows”. Nếu nguồn có header, trailer, comment hoặc nhiều dòng tạo thành một item, tổng số dòng vật lý của nguồn cũng không nhất thiết bằng số item mà reader xử lý.

## 2. Các bộ đếm của `StepExecution`

Spring Batch lưu số liệu của mỗi lần chạy step trong `StepExecution`. Những bộ đếm thường dùng để đối chiếu gồm:

| Bộ đếm | Ý nghĩa | Cách hiểu khi đối chiếu |
|---|---|---|
| `readCount` | Số item được đọc thành công | Các item đã đi qua reader và được framework nhận là item đọc được |
| `writeCount` | Số item được ghi thành công | Số item mà lần ghi hoàn tất thành công; không nhất thiết là số hàng vật lý ở đích |
| `filterCount` | Số item bị processor lọc | Processor trả về `null`; đây thường là quyết định nghiệp vụ có chủ đích, không phải skip |
| `readSkipCount` | Số lỗi đọc được chấp nhận và bỏ qua | Item không được đọc thành công do lỗi ở reader |
| `processSkipCount` | Số item bị bỏ qua do lỗi processor | Item đã được đọc nhưng lỗi xử lý được skip policy chấp nhận |
| `writeSkipCount` | Số item bị bỏ qua do lỗi writer | Item đã qua các bước trước nhưng không được ghi vì lỗi ghi được chấp nhận |
| `skipCount` | Tổng số skip ở cả ba giai đoạn | Bằng tổng read skip, process skip và write skip |
| `commitCount` | Số lần transaction commit | Đếm lần commit, không phải số item hay số output record |
| `rollbackCount` | Số lần transaction rollback | Hữu ích để điều tra transaction/retry; không phải số item bị skip |

Có thể lấy các bộ đếm này trực tiếp từ `StepExecution` bằng các phương thức như `getReadCount()`, `getWriteCount()`, `getFilterCount()`, `getReadSkipCount()`, `getProcessSkipCount()`, `getWriteSkipCount()` và `getSkipCount()`.

### Phân biệt filter và skip

Filter và skip đều có thể làm cho một item đã đọc không xuất hiện trong output, nhưng nguyên nhân và bộ đếm khác nhau:

- **Filter:** processor chủ động trả về `null`, ví dụ loại đơn hàng đã hủy theo quy tắc nghiệp vụ. Item được tính vào `filterCount`, không tính vào `skipCount`.
- **Skip:** reader, processor hoặc writer phát sinh exception và cấu hình skip policy cho phép bỏ qua lỗi đó. Item được tính vào skip count của đúng giai đoạn.

Vì vậy, `readCount - writeCount` không đồng nghĩa với `skipCount`. Phần chênh lệch có thể gồm cả item bị filter và item bị skip trong process hoặc write.

## 3. Công thức đối chiếu

Với một step xử lý theo mô hình chunk, khi step hoàn tất bình thường và mọi item đọc thành công đều đi tới một kết quả cuối cùng, có thể dùng các quan hệ sau.

**Tổng skip:**

```text
skipCount = readSkipCount + processSkipCount + writeSkipCount
```

**Phân loại các item đã đọc thành công:**

```text
readCount = writeCount
          + filterCount
          + processSkipCount
          + writeSkipCount
```

`readSkipCount` không nằm trong công thức thứ hai vì item bị lỗi ngay khi đọc không trở thành một item đọc thành công và không được cộng vào `readCount`.

Nếu reader xử lý hết một tập input gồm các candidate record, mỗi candidate tương ứng đúng một item reader, ta có thể tính:

```text
attemptedInputCount = readCount + readSkipCount
```

Kết hợp hai quan hệ trên:

```text
attemptedInputCount = writeCount + filterCount + skipCount
```

Công thức cuối chỉ dùng được khi phạm vi input đã được đọc hết và đơn vị đếm ở nguồn khớp với đơn vị item của reader. Nếu step dừng sớm, reader bỏ qua dữ liệu theo logic riêng, hoặc một item được tạo từ nhiều dòng nguồn, cần dùng số liệu nguồn độc lập để giải thích phần chênh lệch.

### Ví dụ đối chiếu

Giả sử một file có 1.000 record hợp lệ theo định nghĩa input của ứng dụng. Reader đọc thành công 990 item và có 10 record lỗi định dạng được skip ở giai đoạn đọc. Trong 990 item đã đọc:

- Processor lọc 40 item vì không đáp ứng điều kiện nghiệp vụ.
- 5 item phát sinh lỗi trong processor và được skip.
- 3 item phát sinh lỗi trong writer và được skip.
- 942 item được ghi thành công.

| Chỉ số | Giá trị |
|---|---:|
| Input candidates đã thử đọc | 1.000 |
| `readCount` | 990 |
| `readSkipCount` | 10 |
| `filterCount` | 40 |
| `processSkipCount` | 5 |
| `writeSkipCount` | 3 |
| `writeCount` | 942 |
| `skipCount` | 18 |

Kiểm tra các quan hệ:

```text
skipCount = 10 + 5 + 3 = 18

readCount = 942 + 40 + 5 + 3 = 990

attemptedInputCount = 990 + 10 = 1.000

attemptedInputCount = 942 + 40 + 18 = 1.000
```

Các số liệu khớp nhau. Có 942 output items được ghi thành công, 40 item bị filter và 18 item bị skip. Nếu writer tạo một hàng đích cho mỗi item, có thể kỳ vọng 942 hàng được ghi. Nếu writer tạo nhiều hàng cho mỗi item, cần đếm số hàng đích bằng truy vấn hoặc metric riêng.

## 4. Đọc đúng ý nghĩa của từng loại skip

### Read skip

`readSkipCount` tăng khi reader phát sinh lỗi và lỗi đó được skip policy cho phép bỏ qua. Ví dụ thường gặp là một dòng file không thể parse hoặc một record nguồn không thể chuyển thành item.

Vì item chưa được đọc thành công, lỗi này không nằm trong `readCount`. Khi cần giải thích số lượng input, hãy xem `readCount` cùng `readSkipCount`, đồng thời kiểm tra reader có bỏ qua header, comment hoặc record theo quy tắc riêng hay không.

### Process skip

`processSkipCount` tăng khi processor phát sinh exception và Spring Batch quyết định skip item đó. Item đã được reader cung cấp nên đã nằm trong `readCount`, nhưng không đi tiếp tới writer.

Phân biệt trường hợp processor trả về `null`: trường hợp đó là filter và được tính vào `filterCount`, không phải `processSkipCount`.

### Write skip

`writeSkipCount` tăng khi thao tác ghi phát sinh exception và skip policy cho phép bỏ qua item gây lỗi. Item đó đã được đọc thành công, nên nằm trong `readCount`, nhưng không được tính vào `writeCount` của lần ghi thành công.

Writer thường nhận một chunk gồm nhiều item. Khi ghi chunk lỗi, Spring Batch có thể rollback và thực hiện lại các thao tác cần thiết để xác định item gây lỗi theo cấu hình fault-tolerant. Vì vậy, không nên suy ra số item bị skip từ số lần writer được gọi hoặc số lần transaction rollback. Hãy dùng bộ đếm của `StepExecution` và log skip tương ứng.

## 5. Ghi lại và quan sát các bộ đếm

Một `StepExecutionListener` có thể ghi lại các bộ đếm sau khi step kết thúc. Ví dụ dưới đây dùng API listener phổ biến của Spring Batch:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class StepCountLogger implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepCountLogger.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "step={} status={} read={} written={} filtered={} " +
            "readSkipped={} processSkipped={} writeSkipped={} totalSkipped={}",
            stepExecution.getStepName(),
            stepExecution.getStatus(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getFilterCount(),
            stepExecution.getReadSkipCount(),
            stepExecution.getProcessSkipCount(),
            stepExecution.getWriteSkipCount(),
            stepExecution.getSkipCount()
        );

        // null giữ nguyên ExitStatus hiện tại của step.
        return null;
    }
}
```

Đăng ký listener này với step cần quan sát. Log nên chứa ít nhất tên step, trạng thái, định danh lần chạy và các bộ đếm. Trong hệ thống nhiều job chạy đồng thời, chỉ log số lượng mà không có `jobExecutionId` hoặc thông tin tương đương sẽ khiến việc đối chiếu các lần chạy dễ nhầm lẫn.

Để biết item nào bị skip và vì sao, có thể bổ sung `SkipListener`. Listener phân biệt ba callback:

- `onSkipInRead(Throwable t)`: lỗi xảy ra trong reader; callback không có item vì reader không tạo được item.
- `onSkipInProcess(T item, Throwable t)`: có item đầu vào và lỗi xảy ra trong processor.
- `onSkipInWrite(S item, Throwable t)`: có item đầu ra và lỗi xảy ra trong writer.

Ghi log mã nghiệp vụ của item khi có thể, loại exception và thông tin nguồn. Với read skip, ghi vị trí file, offset, khóa nguồn hoặc ngữ cảnh reader sẵn có. Tránh ghi dữ liệu nhạy cảm nguyên văn vào log. Nếu ứng dụng lưu record lỗi vào bảng reject/quarantine, hãy dùng khóa tương quan để so sánh bảng đó với skip count.

## 6. Đối chiếu từ metadata đã lưu

Spring Batch thường lưu các bộ đếm step trong bảng metadata `BATCH_STEP_EXECUTION`. Có thể truy vấn theo `JOB_EXECUTION_ID` để lấy các step của cùng một lần chạy:

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    READ_COUNT,
    WRITE_COUNT,
    FILTER_COUNT,
    READ_SKIP_COUNT,
    PROCESS_SKIP_COUNT,
    WRITE_SKIP_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

Tên bảng hoặc prefix có thể được tùy chỉnh theo cấu hình repository. Nếu hệ thống dùng prefix khác, thay `BATCH_` bằng prefix đang được cấu hình. Cần kiểm tra đúng schema metadata của môi trường trước khi chạy truy vấn.

Khi đọc kết quả:

1. Chọn đúng `JOB_EXECUTION_ID` và `STEP_EXECUTION_ID`.
2. Kiểm tra `STATUS` trước khi áp dụng công thức cân đối.
3. Tính `skipCount` từ ba cột skip để nhìn rõ giai đoạn phát sinh.
4. So sánh `READ_COUNT` với tổng `WRITE_COUNT`, `FILTER_COUNT`, `PROCESS_SKIP_COUNT` và `WRITE_SKIP_COUNT`.
5. Đối chiếu số output vật lý bằng dữ liệu đích hoặc metric riêng nếu writer không ghi theo tỷ lệ một item thành một row.

Có thể đọc cùng thông tin qua `JobExplorer` và các đối tượng `JobExecution`/`StepExecution`, thay vì truy vấn SQL trực tiếp. Dù dùng cách nào, hãy giữ cùng phạm vi lần chạy khi so sánh.

## 7. Quy trình điều tra khi số liệu không khớp

Khi báo cáo input và output không cân bằng, thực hiện lần lượt các bước sau:

1. **Chốt phạm vi:** xác định job execution, step execution, khoảng thời gian và partition đang được so sánh. Không trộn số liệu của các lần chạy khác nhau.
2. **Chốt đơn vị:** xác định input là dòng nguồn, message hay item reader; output là item writer hay hàng vật lý trong hệ thống đích.
3. **Kiểm tra trạng thái:** chỉ kỳ vọng công thức cân đối đầy đủ khi step hoàn tất và đã xử lý hết input thuộc phạm vi. Step `FAILED`, `STOPPED` hoặc bị dừng giữa chunk có thể còn item chưa được phân loại.
4. **Tính tổng skip:** cộng `readSkipCount`, `processSkipCount` và `writeSkipCount`; sau đó xem giai đoạn nào chiếm phần lớn.
5. **Tính phần filter:** kiểm tra `filterCount` và điều kiện trong processor. Đừng gộp filter vào skip khi lập báo cáo lỗi.
6. **Đối chiếu writer:** kiểm tra hợp đồng writer, log ghi, transaction và số hàng thực tế ở đích. `writeCount` cho biết số item ghi thành công theo framework, không xác nhận độc lập số hàng vật lý.
7. **Xem log lỗi và skip:** dùng `SkipListener`, log ứng dụng và bảng reject/quarantine để tìm nguyên nhân theo từng item.
8. **Kiểm tra retry/rollback và restart:** retry có thể khiến reader, processor hoặc writer được gọi nhiều lần. `rollbackCount` phản ánh transaction rollback, không thể cộng trực tiếp vào số input hoặc skip. Khi job được restart, hãy phân biệt execution hiện tại với các execution trước của cùng `JobInstance`.

Nếu step đã `COMPLETED`, reader đã đọc hết phạm vi input, và mô hình một item đi qua một processor rồi tới writer, nhưng:

```text
readCount != writeCount + filterCount
              + processSkipCount + writeSkipCount
```

thì cần tìm phần item chưa được phân loại hoặc khác biệt trong cách ứng dụng đo dữ liệu. Đừng tự gán phần chênh lệch đó thành skip. Kiểm tra trạng thái thực thi, phạm vi dữ liệu, reader/processor/writer tùy chỉnh và các listener có thay đổi luồng xử lý.

## 8. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `readCount - writeCount` là số skip | Chênh lệch còn có thể gồm `filterCount`, process skip và write skip |
| Filter là một loại skip | Filter được ghi ở `filterCount`; skip được ghi ở ba bộ đếm skip theo giai đoạn |
| Read skip đã nằm trong `readCount` | Read skip là lỗi đọc được chấp nhận; nó được ghi ở `readSkipCount` riêng |
| `writeCount` luôn bằng số hàng trong database | `writeCount` đếm item được ghi thành công; writer có thể tạo nhiều hoặc ít hàng vật lý hơn |
| `commitCount` là số record đã lưu | Đây là số lần transaction commit; một commit có thể bao gồm cả chunk |
| `rollbackCount` là số item thất bại | Một rollback có thể liên quan đến nhiều item và retry; hãy đọc skip count riêng |
| Cộng số liệu của mọi lần restart thành tổng output | Các execution có thể xử lý lại cùng phạm vi; cần xác định execution nào là nguồn báo cáo và kiểm tra tính idempotent của writer |
| Step `FAILED` vẫn phải cân bằng như step `COMPLETED` | Lỗi giữa chunk có thể để lại item đã đọc nhưng chưa được ghi, filter hoặc skip |

## 9. Checklist cho báo cáo output consistency

Trước khi kết luận một lần chạy đã cân bằng, hãy xác nhận:

- [ ] Đang so sánh cùng một `JobExecution` và `StepExecution`.
- [ ] Đã xác định rõ input item, output item và output record có cùng đơn vị hay không.
- [ ] Đã xem `STATUS` của step.
- [ ] Đã tính `skipCount` bằng tổng ba loại skip.
- [ ] Đã tách `filterCount` khỏi skip.
- [ ] Đã kiểm tra quan hệ giữa `readCount`, `writeCount`, `filterCount`, `processSkipCount` và `writeSkipCount`.
- [ ] Đã giải thích `readSkipCount` khi đối chiếu với tổng input nguồn.
- [ ] Đã xác nhận số output vật lý ở hệ thống đích nếu `writeCount` không đại diện trực tiếp cho số hàng.
- [ ] Đã kiểm tra log lỗi, retry, rollback, restart hoặc partition khi số liệu chưa khớp.

Một báo cáo rõ ràng nên trình bày riêng `readCount`, `writeCount`, `filterCount`, từng loại skip, `skipCount`, trạng thái step và đơn vị đo. Khi các con số được lấy từ cùng execution và cùng phạm vi dữ liệu, chúng cho thấy item đã được ghi, được lọc hay bị bỏ qua ở giai đoạn nào, đồng thời giúp phát hiện phần input chưa được giải thích.
