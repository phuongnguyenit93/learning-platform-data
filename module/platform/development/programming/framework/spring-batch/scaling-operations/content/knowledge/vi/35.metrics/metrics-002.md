# Read count và write count trong Spring Batch

> **Chương:** Metrics
>
> **Module:** SPRING_BATCH_SCALING_OPERATIONS — Mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và xử lý phân tán phù hợp. Bài này tập trung vào hai chỉ số nền tảng để đo tiến độ, tìm nút thắt, đối soát dữ liệu và vận hành job an toàn khi có retry/restart.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích ý nghĩa chính xác của `readCount` và `writeCount` trong một `StepExecution`.
2. Phân biệt item được đọc/đưa vào writer với hàng dữ liệu thực sự được insert, update hoặc gửi ra hệ thống bên ngoài.
3. Dùng `filterCount`, skip counters, `commitCount` và `rollbackCount` để lý giải chênh lệch read/write.
4. Đọc các counters qua Java API và metadata của `JobRepository`; tính throughput có ngữ cảnh.
5. Phân tích số liệu đúng khi step chạy đa luồng, chia partition, retry hoặc restart, tránh tính trùng giữa các lần thực thi.

## 1. Read count và write count đo cái gì?

Trong Spring Batch, các counters là dữ liệu thống kê về **một lần thực thi step** (`StepExecution`). Hai chỉ số phổ biến nhất là:

| Counter | Ý nghĩa chính | Không nên hiểu thành |
| --- | --- | --- |
| `readCount` | Số item mà quá trình đọc của step đã nhận thành công từ `ItemReader.read()`, thường là các kết quả khác `null` được ghi nhận trong thống kê của step | Số dòng SQL đã scan, số lần gọi `read()`, tổng bản ghi có trong nguồn |
| `writeCount` | Số item đầu ra mà quá trình ghi của step đã xử lý thành công qua `ItemWriter` và được ghi nhận vào thống kê step | Số hàng database thực sự insert/update, số request phía nhận đã xử lý thành công |

Theo hợp đồng `ItemReader`, lời gọi `read()` trả về item hoặc `null` để báo hết dữ liệu; `null` **không phải** một item được đọc. Với chunk-oriented processing, framework thu thập thống kê theo vòng đời chunk và ghi trạng thái qua `JobRepository`. Các số đếm cuối cùng cần được diễn giải cùng `BatchStatus`, tình trạng commit/rollback và lần thực thi đang xem.

~~~mermaid
flowchart TD
    A["ItemReader.read()"] --> B{"Trả về item?"}
    B -- "null: hết dữ liệu" --> Z["Kết thúc đọc"]
    B -- "Có" --> C["readCount tăng khi item<br/>được ghi nhận bởi step"]
    C --> D["ItemProcessor"]
    D --> E{"Kết quả?"}
    E -- "null" --> F["filterCount"]
    E -- "Item đầu ra" --> G["ItemWriter.write(Chunk)"]
    G --> H["writeCount: item đầu ra<br/>ghi thành công"]
    E -- "Exception được skip" --> I["processSkipCount"]
    G -- "Exception được skip" --> J["writeSkipCount"]
~~~

Sơ đồ trên thể hiện **luồng logic thông thường**, không mô tả chính xác mọi nhánh retry, rollback hoặc thứ tự cập nhật counter trong mã nguồn. Trong fault-tolerant step, một item có thể được thử lại và số liệu chỉ nên được đánh giá trên trạng thái `StepExecution` thực tế.

### Ví dụ rất nhỏ

Reader đọc bốn đơn hàng `A, B, C, D`. Processor trả về `A, C, D` nhưng trả `null` cho `B` vì đơn hàng không đủ điều kiện. Writer ghi thành công ba item:

| Counter | Kết quả |
| --- | ---: |
| `readCount` | 4 |
| `filterCount` | 1 |
| `writeCount` | 3 |

**Không có lỗi** trong tình huống này. `readCount > writeCount` là kết quả bình thường khi nghiệp vụ cố ý lọc item.

## 2. Vì sao read count có thể khác write count?

Trong một step có processor và fault tolerance, chênh lệch thường liên quan đến:

- **Filter:** `ItemProcessor.process()` trả về `null`, item được đọc nhưng không chuyển sang writer; thống kê thuộc `filterCount`.
- **Process skip:** Processor ném exception được skip policy cho phép bỏ qua; đếm ở `processSkipCount`.
- **Write skip:** Writer xử lý lỗi item mà skip policy cho phép; item bị bỏ qua khi ghi, đếm ở `writeSkipCount`.
- **Reader skip:** Reader ném exception được phép skip; tăng `readSkipCount`, nhưng một lỗi đọc không tạo ra item đọc thành công tương ứng.
- **Retry/rollback:** Cùng item có thể được thử lại, còn các đóng góp thống kê và trạng thái commit có thể thay đổi theo transaction và cơ chế fault tolerance.

Giả sử input có 10.000 item được đọc thành công. Processor lọc 300 item, bỏ qua 20 item lỗi và writer skip thêm 5 item; không có nhánh chuyển đổi một item thành nhiều item ở mức Batch và mọi chunk còn lại đều hoàn tất:

| Chỉ số | Giá trị giả định | Diễn giải |
| --- | ---: | --- |
| `readCount` | 10.000 | Item được reader trả về thành công |
| `filterCount` | 300 | Item bị lọc có chủ đích |
| `processSkipCount` | 20 | Item lỗi bị bỏ qua ở processor |
| `writeSkipCount` | 5 | Item lỗi bị bỏ qua ở writer |
| `writeCount` | 9.675 | Item đầu ra còn lại được ghi thành công |
| `readSkipCount` | 7 | Bảy lỗi đọc bị skip, **tách biệt** với 10.000 item đã đọc thành công |

Trong **ví dụ đơn giản có các giả định nêu trên**, phép kiểm tra hữu ích là:

~~~text
10.000 - 300 - 20 - 5 = 9.675

readCount - writeCount
    ≈ filterCount + processSkipCount + writeSkipCount
~~~

Đây là **phép đối chiếu có điều kiện**, không phải bất biến dùng được cho mọi cấu hình. Khi một writer thực hiện aggregation, biến đổi số lượng bản ghi, một lần write tác động nhiều bảng, hoặc step bị rollback/stop giữa chừng, không được khẳng định đẳng thức trên luôn đúng. Tương tự, không cộng `readSkipCount` vào `readCount` để suy ra số dòng thực sự đã duyệt qua nguồn: retry và lỗi parse có thể tạo nhiều lần thử cho một đơn vị dữ liệu.

### Phân biệt filter với skip

| Tình huống | Biểu hiện | Counter liên quan |
| --- | --- | --- |
| Đơn hàng không thuộc phạm vi xử lý | Processor trả `null` theo quy tắc nghiệp vụ | `filterCount` |
| Giá trị không hợp lệ làm parser ném lỗi và được bỏ qua | Reader throw, skip policy chấp nhận | `readSkipCount` |
| Processor throw với item lỗi có thể skip | Không có output cho item đó | `processSkipCount` |
| Writer throw với item lỗi có thể skip | Không ghi item lỗi sau xử lý fault tolerance | `writeSkipCount` |
| Lỗi DB tạm thời được retry rồi thành công | Item cuối cùng được ghi | Có thể tăng các metric retry riêng; **không đồng nghĩa** write skip |

Đừng gộp “không được ghi” với “ghi lỗi”. Filter là lựa chọn nghiệp vụ; skip là một quyết định xử lý lỗi.

## 3. Write count không nhất thiết là số hàng thực sự thay đổi

`ItemWriter` tiếp nhận **item của Spring Batch**, trong khi một item có thể ánh xạ đến 0, 1 hoặc nhiều tác dụng phụ ở đích.

| Hành vi của writer | `writeCount` phản ánh | Số hàng/hiệu ứng thực tế |
| --- | --- | --- |
| Insert mỗi item thành một hàng mới | Item được writer xử lý thành công | Thường bằng số hàng insert, nếu không conflict và commit thành công |
| PostgreSQL `ON CONFLICT DO NOTHING` | Item truyền qua writer hợp lệ, kể cả duplicate được chấp nhận | Có thể có **0 hàng insert mới** đối với item trùng |
| `UPDATE ... WHERE` không tìm thấy hàng | Nếu writer coi kết quả 0 hàng là hợp lệ, item vẫn có thể được tính | 0 hàng cập nhật |
| Một item ghi hai bảng hoặc nhiều hàng | Item đầu ra của Batch | Nhiều hàng có thể thay đổi từ một item |
| Gọi HTTP/API hoặc phát sự kiện | Item đi qua writer mà không báo lỗi tại thời điểm đó | Thành công cuối cùng hoặc side effect ở bên nhận cần đối soát riêng |

Ví dụ, writer nhận 1.000 event, trong đó 100 event đã tồn tại. Với câu lệnh PostgreSQL:

~~~sql
INSERT INTO imported_events(source_system, event_id, payload)
VALUES (:sourceSystem, :eventId, :payload)
ON CONFLICT (source_system, event_id) DO NOTHING;
~~~

Nếu writer chấp nhận conflict là kết quả bình thường, bước ghi có thể được thống kê `writeCount = 1.000` nhưng chỉ **900 hàng mới** xuất hiện. Từ đó:

- `writeCount` đo **công việc đầu ra được Batch chấp nhận**.
- Số hàng insert/update thực sự phải được đo qua kết quả ghi phù hợp hoặc truy vấn dữ liệu đích.
- Số **business event duy nhất** phải được đối soát bằng business key và chính sách idempotency.

Khi thiết kế dashboard, nên phân biệt `itemsWritten`, `rowsInserted`, `rowsUpdated`, `duplicateNoops` và `conflictingPayloads` nếu nghiệp vụ cần những thông tin đó. `writeCount` một mình không chứng minh dữ liệu đích đầy đủ hay đúng.

## 4. Đọc các counter qua Spring Batch API

Các giá trị thuộc `StepExecution`. API thường dùng gồm:

~~~java
long readCount = stepExecution.getReadCount();
long writeCount = stepExecution.getWriteCount();
long filterCount = stepExecution.getFilterCount();

long readSkipCount = stepExecution.getReadSkipCount();
long processSkipCount = stepExecution.getProcessSkipCount();
long writeSkipCount = stepExecution.getWriteSkipCount();

long commitCount = stepExecution.getCommitCount();
long rollbackCount = stepExecution.getRollbackCount();
~~~

Ví dụ một `StepExecutionListener` ghi log tổng kết khi step kết thúc. Đoạn mã minh họa cho **Spring Batch 5.x** với SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class StepCountLogger implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepCountLogger.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
            "jobExecutionId={} stepExecutionId={} step={} status={} " +
            "read={} write={} filter={} readSkip={} processSkip={} " +
            "writeSkip={} commit={} rollback={}",
            step.getJobExecution().getId(),
            step.getId(),
            step.getStepName(),
            step.getStatus(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getReadSkipCount(),
            step.getProcessSkipCount(),
            step.getWriteSkipCount(),
            step.getCommitCount(),
            step.getRollbackCount()
        );

        return null; // Giữ ExitStatus hiện tại, không sửa kết quả của step.
    }
}
~~~

Đăng ký listener cho step cần quan sát:

~~~java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<InputItem> reader,
        ItemProcessor<InputItem, OutputItem> processor,
        ItemWriter<OutputItem> writer,
        StepCountLogger stepCountLogger) {

    return new StepBuilder("importStep", jobRepository)
            .<InputItem, OutputItem>chunk(200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .listener(stepCountLogger)
            .build();
}
~~~

`InputItem` và `OutputItem` trong ví dụ là kiểu dữ liệu nghiệp vụ do ứng dụng định nghĩa; `reader`, `processor`, `writer` được cung cấp từ các bean tương ứng. `afterStep` phù hợp để **ghi snapshot tổng kết**, còn khi muốn theo dõi throughput liên tục trong job kéo dài nhiều giờ, cần lấy snapshot theo từng cửa sổ hoặc dùng hệ thống metric chuyên biệt.

### Đọc dữ liệu từ JobRepository

Trong schema metadata mặc định của Spring Batch, bảng `BATCH_STEP_EXECUTION` chứa những cột:

~~~sql
SELECT
    STEP_EXECUTION_ID,
    JOB_EXECUTION_ID,
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
~~~

Tên bảng/cột ở đây theo **schema mặc định**; tên bảng có thể khác nếu hệ thống cấu hình prefix khác. Trong ứng dụng, `JobExplorer` là cách API phù hợp để truy cập lịch sử `JobExecution`/`StepExecution` mà không gắn chặt mã vào SQL metadata.

Các giá trị lưu trong repository được cập nhật theo cơ chế transaction và vòng đời step. Trong lúc job đang chạy, snapshot có thể chưa phản ánh hoạt động của chunk chưa commit. Vì vậy cần luôn ghi cùng **ID của JobExecution/StepExecution, status và thời điểm snapshot** thay vì chỉ lưu một số count đứng riêng.

## 5. Đo tốc độ xử lý từ readCount và writeCount

`readCount` và `writeCount` là **số đếm tích lũy của một StepExecution**; muốn biết tốc độ, phải tính thay đổi theo thời gian.

~~~text
readThroughput  = (readCount(t2)  - readCount(t1))  / (t2 - t1)
writeThroughput = (writeCount(t2) - writeCount(t1)) / (t2 - t1)

Đơn vị: item/giây, với t2 - t1 tính bằng giây.
~~~

Ví dụ step có `writeCount = 50.000` lúc 10:00:00 và `writeCount = 65.000` lúc 10:00:30:

~~~text
writeThroughput = (65.000 - 50.000) / 30
                = 500 item/giây
~~~

Đây là **tốc độ item đầu ra của Batch**, không nhất thiết là 500 hàng mới/giây. Nếu chunk đang bị rollback/retry hoặc writer dùng dedupe `DO NOTHING`, cần quan sát thêm tốc độ hàng ghi thực tế và latency của hệ thống đích.

### Các tỷ lệ hỗ trợ chẩn đoán

~~~text
filterRate = filterCount / readCount

processSkipRate = processSkipCount / readCount

readToWriteRatio = writeCount / readCount
~~~

Chỉ tính các tỷ lệ khi mẫu số khác 0; xác định rõ khoảng thời gian, cùng `StepExecution` và các giả định về flow xử lý. `readToWriteRatio` không phải thước đo chất lượng độc lập: khi nghiệp vụ lọc 80% dữ liệu đúng yêu cầu, tỷ lệ 20% là **bình thường**. `readSkipCount` cần mẫu số phù hợp về số lần thử đọc, thường không thể lấy chính xác từ `readCount` nếu có retry.

| Quan sát | Khả năng cần kiểm tra | Dữ liệu bổ sung |
| --- | --- | --- |
| `readCount` tăng nhanh, `writeCount` tăng chậm | Processor lọc nhiều, xử lý chậm, writer bị nghẽn hoặc nhiều chunk đang chạy | Filter/skip count, CPU, processor/write latency, connection pool |
| Hai count đứng yên | Reader kẹt, source hết dữ liệu, thread bị block, step không còn tiến triển | Step status, log, thread dump, DB wait, queue |
| `writeCount` cao nhưng số hàng đích tăng ít | Conflict/no-op, update 0 row, writer biến đổi item, transaction khác | Update counts, unique key, DB rows inserted/updated |
| `rollbackCount` tăng liên tục | Deadlock, timeout, lỗi xử lý hoặc writer | Retry log, exception, DB lock wait, transaction latency |
| Tăng thread nhưng write throughput không cải thiện | Reader/DB I/O/lock trở thành bottleneck | CPU, DB pool, disk/network, per-partition throughput |

Với workload lớn, nên thử các mức concurrency khác nhau trong điều kiện gần giống nhau: cùng dataset, chunk size, kết nối nguồn/đích, hạ tầng và ngưỡng lỗi. Số thread cao hơn không mặc nhiên mang lại nhiều item/giây hơn.

## 6. Đọc số đếm trong các mô hình scaling

### 6.1. Multi-threaded step

Nhiều thread xử lý chunk của **cùng một StepExecution**. `readCount` và `writeCount` là số liệu **tổng hợp của step**, không phải các counter riêng theo thread. Các chunk có thể hoàn tất **khác thứ tự đọc**; không dùng chênh lệch giữa các snapshot làm bằng chứng rằng mọi item ở đầu nguồn đã commit theo thứ tự.

Nếu một reader không thread-safe bị gọi chung từ nhiều thread, counter vẫn có thể tăng và nhìn có vẻ hợp lý dù dữ liệu thực tế bị trùng/bỏ sót. Đối soát theo ID ở nguồn và đích vẫn là điều bắt buộc.

### 6.2. Parallel steps

Mỗi step có `StepExecution` và bộ counter riêng. Nếu hai step xử lý **hai loại nghiệp vụ khác nhau**, cộng tổng `writeCount` có thể không có ý nghĩa. Chỉ cộng khi các step được thiết kế có cùng đơn vị item và miền dữ liệu không chồng lấn.

### 6.3. Partitioning

Mỗi worker partition có `StepExecution` độc lập. Dashboard nên hiển thị:

- `partitionName` hoặc tên worker step, `StepExecutionId` và trạng thái.
- Số item đọc/ghi, throughput, lỗi/rollback của từng partition.
- Tổng hợp qua các partition được xác định là **không chồng lấn** trong **một lượt xử lý được chọn rõ ràng**.

Ví dụ ba partition thành công lần đầu xử lý lần lượt 20.000, 30.000 và 50.000 item. Nếu mỗi item tạo đúng một item đầu ra và không lọc/skip, tổng `writeCount` có thể là 100.000. Nhưng nếu partition thứ hai lỗi sau một số chunk đã commit rồi restart, có thể xuất hiện **nhiều StepExecution thuộc cùng logic partition**. Lúc này, cộng tất cả raw counters mà không xét lượt chạy, trạng thái commit và replay dễ gây nhầm lẫn.

~~~mermaid
flowchart TB
    M["Manager step / partitioner"]
    M --> P1["Worker A<br/>StepExecution A"]
    M --> P2["Worker B<br/>StepExecution B"]
    M --> P3["Worker C<br/>StepExecution C"]
    P1 --> K["Dashboard: ID, status,<br/>read/write/skip/rollback"]
    P2 --> K
    P3 --> K
    K --> V["Đối soát business key ở đích<br/>trước khi kết luận đủ dữ liệu"]
~~~

### 6.4. Retry và restart

Phải phân biệt:

| Phạm vi | Ý nghĩa |
| --- | --- |
| `JobInstance` | Job cùng bộ identifying `JobParameters`, có thể có nhiều lần thực thi nếu restart |
| `JobExecution` | Một lần chạy/thử thực thi job, có trạng thái riêng |
| `StepExecution` | Một lần thực thi step cụ thể, có bộ counters riêng |
| Business record/event ID | Định danh nghiệp vụ dùng để đối soát không trùng/mất item |

Một restart có thể tạo `JobExecution` mới và `StepExecution` mới cho phần cần chạy tiếp. **Không lấy `readCount` của riêng lần restart để suy ra toàn bộ kết quả của job**, cũng không mặc định cộng mọi `StepExecution` của các lần retry/re-run để tính số **item duy nhất**. Cần định nghĩa đang đo **khối lượng công việc đã xử lý theo các lần chạy** hay **số kết quả nghiệp vụ duy nhất cuối cùng**. Hai đại lượng này khác nhau.

Một số chunk có thể đã gọi writer rồi rollback và thử lại. Counter và số lần gọi hàm, đặc biệt khi có side effect ngoài DB, cần được tách bạch. Nếu writer gửi sự kiện/HTTP, kết quả bên nhận không thể suy ra chỉ từ `writeCount`; cần idempotency key, acknowledgement và dữ liệu xác nhận ở hệ thống đích.

## 7. Một case study vận hành

**Bối cảnh:** Job nhập 2 triệu giao dịch mỗi đêm, chia thành 8 partition đọc theo dải khóa. Mỗi partition ghi PostgreSQL bằng upsert, một phần transaction là dữ liệu cũ bị bỏ qua. Trong lần chạy gần nhất, dashboard hiển thị `readCount = 2.000.000` và `writeCount = 1.990.000` khi kết thúc.

Người vận hành không nên kết luận ngay “thiếu 10.000 giao dịch”. Hãy điều tra theo trình tự:

1. Kiểm tra toàn bộ `StepExecution` có `COMPLETED` hay còn `FAILED`, `STOPPED`, đang chạy, hoặc đã restart; nhóm theo đúng tập partition và lần chạy.
2. Kiểm tra `filterCount`, `processSkipCount`, `writeSkipCount` từng partition. Nếu tổng 10.000 item đã được filter đúng nghiệp vụ, chênh lệch là bình thường.
3. Xác minh upsert có no-op hay update không, và tách số item writer đã chấp nhận khỏi số hàng **mới** trong database.
4. Đối soát theo business key của 2 triệu giao dịch với bảng đích; điều tra trường hợp key trùng, bản ghi không hợp lệ, dải partition chồng lấn hoặc nguồn thay đổi trong lúc chạy.
5. Xem `commitCount`, `rollbackCount` và log retry để xác định có lỗi khiến chunk xử lý lại. Kiểm tra timeout, lock wait và connection pool nếu throughput sụt.
6. So sánh tốc độ từng partition. Một partition chậm bất thường có thể do phân phối dữ liệu lệch, query/index kém hoặc tranh chấp khóa.

Nếu tất cả 8 partition đều hoàn tất và 10.000 item được lọc hợp lệ, `writeCount` thấp hơn `readCount` **không phải lỗi**. Nhưng ngay cả khi hai count bằng nhau, job vẫn phải đối soát để phát hiện item trùng, writer no-op hoặc tác dụng phụ không được xác nhận.

## 8. Thực hành kiểm thử và dashboard

### Bộ tình huống kiểm thử gợi ý

| Tình huống | Kỳ vọng cần kiểm tra |
| --- | --- |
| Đọc hết 100 bản ghi, writer ghi cả 100 | `readCount` và `writeCount` đều gần đúng 100 khi step hoàn tất và không có filter/skip |
| Processor trả `null` cho 10/100 item | `filterCount = 10`; `writeCount = 90` trong luồng đơn giản |
| Reader lỗi parse và skip hợp lệ | `readSkipCount` tăng; không nhầm lỗi đọc với item đọc thành công |
| Writer gặp deadlock, retry thành công | `rollbackCount`/log retry có thể tăng; kết quả đích vẫn phải đủ và không trùng |
| Writer sử dụng `ON CONFLICT DO NOTHING` | `writeCount` có thể lớn hơn số hàng insert mới; dashboard phân biệt hai metric |
| Dừng và restart giữa job | Dashboard không đếm lại item duy nhất chỉ vì có nhiều `StepExecution` |
| Tăng 1 → 4 → 8 thread | So sánh delta writeCount/giây, CPU/DB/IO, rollback, duplicate và thời gian job |

### Mẫu dashboard tối thiểu

| Nhóm | Nên hiển thị |
| --- | --- |
| Identity và trạng thái | Job name, JobInstance/JobExecution/StepExecution ID, step/partition name, status, start/end time |
| Throughput | `ΔreadCount/s`, `ΔwriteCount/s` theo cửa sổ thời gian cố định |
| Chất lượng luồng | `filterCount`, read/process/write skip count, tỷ lệ theo định nghĩa rõ ràng |
| Transaction và lỗi | `commitCount`, `rollbackCount`, retry/timeout, exception type |
| Kết quả thực tế | Rows inserted/updated/no-op, unique business keys, đối soát checksum/tổng tiền khi phù hợp |
| Tài nguyên | CPU, heap/GC, thread pool, datasource pool, latency query/writer, disk và network |

Micrometer/Spring Batch observation có thể cung cấp timing và các metric vận hành, nhưng **không nên giả định** mỗi timer/histogram đã tương đương với `StepExecution.readCount` hoặc số hàng database được tạo. Nếu cần Prometheus/Grafana, xây cách export theo metric type phù hợp và thiết lập nhãn có cardinality kiểm soát: ID riêng từng execution rất hữu ích trong log/tracing nhưng không nên tùy tiện gắn làm label trên mọi time series dài hạn.

### Câu hỏi tự kiểm tra

Job đọc 50.000 event. Processor lọc 5.000 item; writer nhận 45.000 item và dùng `INSERT ... ON CONFLICT DO NOTHING`. Sau khi chạy xong, bảng chỉ tăng 30.000 hàng. Nếu job báo `COMPLETED`, các con số có mâu thuẫn hay chứng minh mất dữ liệu không?

**Định hướng trả lời:** Chưa thể kết luận mất dữ liệu. `readCount = 50.000`, `filterCount = 5.000`, `writeCount = 45.000` có thể hoàn toàn nhất quán; 15.000 item writer nhận có thể đã tồn tại nên SQL no-op. Phải đối soát business key, quy tắc conflict và nguồn/đích để phân biệt duplicate hợp lệ với item bị bỏ sót.

## Tài liệu tham khảo

- [Spring Batch Reference — Configuring a Step](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): vòng đời chunk, transaction và thống kê trong step.
- [Spring Batch API — StepExecution](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/StepExecution.html): các getter `getReadCount()`, `getWriteCount()` và counters liên quan.
- [Spring Batch Reference — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): bảng metadata theo dõi `JobExecution`, `StepExecution`.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded step, parallel steps và partitioning.

> **Ghi nhớ:** `readCount` và `writeCount` cho biết Spring Batch đã xử lý bao nhiêu **item trong phạm vi một StepExecution**. Hãy đọc chúng cùng filter/skip, transaction, tình trạng step, thông lượng theo thời gian và **đối soát kết quả đích** trước khi kết luận job đúng hay nhanh hơn.
