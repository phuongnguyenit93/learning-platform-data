# Ghi giả thiết và giới hạn của job trong Spring Batch

## 1. Vì sao một batch job cần ghi rõ giả thiết và giới hạn?

Một Spring Batch job không chỉ là chuỗi `ItemReader → ItemProcessor → ItemWriter`. Nó còn thực thi một **hợp đồng vận hành và dữ liệu**: đầu vào đến từ đâu, job được phép xử lý trường hợp nào, khi nào được xem là thành công, có thể chạy lại hay không, và khối lượng nào hệ thống còn đáp ứng được.

Nhiều sự cố batch không xuất phát từ lỗi cú pháp Java. Chúng xuất phát từ các **giả thiết ngầm** chưa từng được viết ra:

- “File ngày nào cũng đến trước 01:00.”
- “Mỗi mã đơn hàng chỉ xuất hiện một lần.”
- “Reader sẽ đọc lại đúng thứ tự sau restart.”
- “Job không bao giờ chạy hai bản cùng lúc.”
- “Writer ghi database thành công nghĩa là API bên ngoài đã xử lý thành công.”
- “Dữ liệu không bao giờ vượt 100.000 bản ghi.”
- “Nếu mất một dòng lỗi, job vẫn có thể xem là thành công.”

Khi một giả thiết bị phá vỡ, job có thể tạo dữ liệu trùng, bỏ sót giao dịch, quá thời gian SLA, hoặc hoàn tất với kết quả không đáng tin.

**Ghi giả thiết và giới hạn của job** là đưa các điều kiện ngầm thành tài liệu có thể đọc, thảo luận, kiểm chứng và giám sát. Đây là một quyết định thiết kế quan trọng thuộc chủ đề **Spring Batch Core Processing**, không phải công việc viết README cho đủ hình thức.

### Ví dụ nhanh

Giả sử job `importPartnerOrders` nhập đơn hàng từ file đối tác vào 02:00 mỗi đêm.

Một dòng tài liệu yếu:

> Job nhập đơn hàng nhanh, không trùng, có thể restart.

Một bản mô tả có giá trị hơn:

| Loại | Nội dung cụ thể | Cách xác nhận |
|---|---|---|
| Giả thiết | Mỗi lần nhập có một `inputVersion` bất biến | Kiểm tra object version/checksum trước và sau restart |
| Giả thiết | `externalOrderId` duy nhất trong mỗi `sourceSystem` | Báo cáo duplicate và unique constraint |
| Giới hạn | File tối đa 500 MiB và 2 triệu dòng | Preflight validation, từ chối đầu vào vượt ngưỡng |
| Cam kết | Dữ liệu hợp lệ được commit theo chunk, có thể restart | Integration test lỗi ở giữa writer rồi restart |
| Giới hạn | Không hỗ trợ hai execution cùng xử lý một input version đồng thời | Điều phối lock và kiểm thử duplicate launch |
| SLA | 95% lượt chạy với tải chuẩn hoàn tất trong 30 phút | Metric duration theo workload |
| Phản ứng | Nếu file không khớp checksum, job `FAILED` và không publish kết quả | Test thay input giữa các lần chạy |

Những con số trên **chỉ là ví dụ**, không phải ngưỡng chung do Spring Batch đặt ra. Hệ thống thực phải dựa trên khả năng hạ tầng và yêu cầu nghiệp vụ.

## 2. Phân biệt giả thiết, giới hạn, bất biến và quyết định thiết kế

Bốn khái niệm này có liên quan nhưng không đồng nghĩa.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| **Assumption – giả thiết** | Một điều được kỳ vọng đúng để thiết kế hoạt động | “API nguồn giữ kết quả ổn định với cùng snapshot token.” |
| **Constraint – giới hạn/ràng buộc** | Điều kiện hệ thống phải tuân thủ hoặc không được vượt | “Một file tối đa 500 MiB.” |
| **Invariant – bất biến** | Tính chất phải luôn đúng trong mọi execution hợp lệ | “Không có hai giao dịch đã ghi cùng business key.” |
| **Decision – quyết định** | Cách triển khai được chọn giữa các phương án | “Dùng staging snapshot và JDBC writer thay vì đọc API live.” |
| **Risk – rủi ro** | Điều có thể xảy ra nếu giả thiết sai hoặc ràng buộc bị vượt | “Nếu API paging đổi thứ tự, restart có thể bỏ sót item.” |
| **Guarantee – cam kết** | Điều hệ thống hứa thực hiện, có điều kiện/phạm vi rõ | “Trong cùng DB transaction, dữ liệu chunk được rollback khi writer ném lỗi.” |

Ví dụ:

```text
Assumption:
  Source trả dữ liệu ổn định theo inputVersion.

Constraint:
  inputVersion phải có mặt và không được đổi khi restart.

Decision:
  Reader chỉ đọc staging theo inputVersion.

Invariant:
  Mỗi (sourceSystem, externalOrderId) được ghi tối đa một lần.

Risk:
  Nếu staging bị sửa sau checkpoint, cursor có thể trỏ sai item.

Mitigation:
  Immutable staging + checksum + unique constraint.

Verification:
  Test restart khi sourceVersion đổi -> phải fail.
```

Không nên ghi mọi thứ vào một danh sách “lưu ý”. Khi phân loại, người vận hành biết cái nào cần **theo dõi**, cái nào phải **từ chối đầu vào**, và cái nào phải **kiểm chứng bằng test**.

### 2.1. “Giả thiết” không phải bằng chứng

Một giả thiết được ghi ra không tự trở thành đúng. Ví dụ “đối tác luôn gửi file một lần” không đủ để bảo đảm không có duplicate. Cần hỏi:

- Ai xác nhận giả thiết này?
- Có tài liệu hoặc SLA từ đối tác không?
- Có thể tự kiểm tra trong code không?
- Nếu giả thiết sai, job sẽ fail, skip, quarantine hay tiếp tục?
- Hệ thống có giám sát để phát hiện giả thiết sai không?

Với điều kiện ảnh hưởng trực tiếp đến tính toàn vẹn dữ liệu, **nên biến giả thiết thành kiểm tra có thể thi hành**, hoặc thêm cơ chế bảo vệ không phụ thuộc vào giả thiết.

## 3. Ví dụ xuyên suốt: job `dailyPartnerSettlement`

Ta dùng một job giả định để minh họa cách ghi và thực thi hợp đồng.

**Bài toán:** Hằng đêm, doanh nghiệp nhận danh sách giao dịch của đối tác, xác thực, chuẩn hóa và ghi kết quả đối soát vào PostgreSQL.

```text
Scheduler / Operator
        |
        v
JobParameters:
  businessDate
  sourceSystem
  inputVersion
        |
        v
Step 1: validateInputManifest
        |
        v
Step 2: loadTransactions
  ItemReader -> ItemProcessor -> JdbcBatchItemWriter
        |
        v
Step 3: reconcileTotals
        |
        v
Step 4: markResultReady
        |
        v
Report/Downstream system
```

Một job như vậy cần nhiều hơn định nghĩa step. Ngay từ thiết kế, ta phải trả lời:

1. **Input identity:** một lượt chạy đại diện cho tập dữ liệu nào?
2. **Freshness:** nguồn phải sẵn sàng trước mấy giờ?
3. **Schema:** trường nào bắt buộc, kiểu và phiên bản nào?
4. **Volume:** bao nhiêu bản ghi, kích thước file, tốc độ dự kiến?
5. **Data quality:** được phép bỏ qua tối đa bao nhiêu lỗi?
6. **Transaction:** ranh giới commit và tác động ngoài transaction?
7. **Restart:** checkpoint nào và dữ liệu đầu vào có bất biến không?
8. **Concurrency:** có được chạy song song cùng ngày và cùng nguồn không?
9. **Result semantics:** điều kiện nào mới được phát `DataReady`?
10. **Observability:** cần kiểm tra các số liệu và cảnh báo nào?

Đây là một **job contract**. Nó cần được version hóa cùng code và được cập nhật khi thiết kế thay đổi.

## 4. Ghi phạm vi nghiệp vụ: job làm gì và không làm gì?

Trước tiên, tài liệu phải chỉ rõ **mục tiêu và ranh giới**.

Ví dụ:

```markdown
## Job contract: dailyPartnerSettlement

Mục tiêu:
- Đọc giao dịch cho một businessDate và sourceSystem.
- Validate schema và business key.
- Ghi tập giao dịch hợp lệ vào staging/ledger theo policy.
- Đối chiếu tổng số và tổng tiền.
- Chỉ phát tín hiệu sẵn sàng khi bước reconcile đạt yêu cầu.

Không nằm trong phạm vi:
- Tự động sửa dữ liệu thiếu mã giao dịch.
- Tự suy đoán giao dịch trùng nếu không có sourceTransactionId.
- Chuyển tiền ra hệ thống ngân hàng trong cùng transaction DB.
- Tự đọc file mới nhất nếu inputVersion được chỉ định không tồn tại.
```

Ghi rõ **ngoài phạm vi** hữu ích không kém ghi chức năng chính. Nó ngăn một người dùng vận hành tưởng rằng việc khởi động lại job có thể tự sửa dữ liệu nguồn bị hỏng, hoặc nghĩ job đã chịu trách nhiệm gửi tiền trong khi nó chỉ ghi staging.

### 4.1. Định nghĩa “thành công”

Job Spring Batch có `BatchStatus` và `ExitStatus`. Nhưng `COMPLETED` về mặt framework không tự chứng minh dữ liệu đáp ứng mọi yêu cầu nghiệp vụ.

Một hợp đồng tốt quy định:

- Step nhập liệu hoàn tất.
- Không có lỗi dữ liệu quan trọng chưa xử lý.
- Số bản ghi nguồn = số bản ghi được chấp nhận + số bản ghi bị từ chối theo các nhóm đã định nghĩa.
- Tổng tiền và các số kiểm soát đối chiếu phù hợp.
- Dữ liệu đã commit vào bảng đích.
- Tín hiệu `DataReady` chỉ được phát sau khi toàn bộ điều kiện được xác nhận.

Nếu một giao dịch bị bỏ qua do `skipLimit` nhưng vẫn nằm trong giới hạn kỹ thuật, cần quyết định rõ: **job được phép `COMPLETED` hay phải fail tại bước quality gate?**

Đây là quyết định nghiệp vụ, không nên mặc định rằng `skipLimit(10)` nghĩa là “chấp nhận mất 10 giao dịch tài chính”.

## 5. Ghi input contract: nguồn, schema và tính bất biến

Một lỗi thiết kế thường gặp là ghi “job đọc CSV” mà không định nghĩa CSV nào, phiên bản nào, encoding nào và xử lý header ra sao.

Ví dụ bảng input contract:

| Thuộc tính | Giá trị ví dụ | Điều kiện cần xác nhận |
|---|---|---|
| Nguồn | Object storage staging | Chỉ đọc vùng đã được phân quyền |
| `sourceSystem` | `PARTNER_A`, `PARTNER_B` | Allowlist |
| `businessDate` | ISO `yyyy-MM-dd` | Ngày hợp lệ theo timezone nghiệp vụ |
| `inputVersion` | Object version/checksum bất biến | Không đổi giữa chạy và restart |
| Format | CSV UTF-8 | Có header đúng schema |
| Schema version | `v2` | Reject version khác hoặc migration |
| Required fields | `sourceTransactionId`, `amount`, `currency` | Không được thiếu |
| Amount | Decimal, tối đa 2 chữ số thập phân | Giới hạn min/max theo nghiệp vụ |
| Record ordering | Không được dựa vào thứ tự file nếu không cam kết | Reader/restart phải có thứ tự xác định |
| Duplicate key | `(sourceSystem, sourceTransactionId)` | Cùng key không được tạo hai giao dịch |
| Input retention | Ví dụ 30 ngày | Phải đủ dài cho SLA restart/reconcile |

Cột “giá trị ví dụ” cần chuyển thành giá trị được chủ hệ thống nguồn xác nhận. Các trường cụ thể có thể thay đổi theo từng hợp đồng đối tác.

### 5.1. File name không đồng nghĩa file identity

Tên `transactions.csv` có thể được dùng lại hằng ngày. Nếu reader checkpoint tới dòng 400.000 rồi file được ghi đè, lần restart có thể bỏ sót hoặc nhập nhầm.

Nên chốt một định danh ổn định, chẳng hạn:

```text
sourceSystem = PARTNER_A
businessDate = 2025-05-12
inputVersion = sha256:abc123...
```

Trong production, `inputVersion` phải thực sự được liên kết với nội dung nguồn, ví dụ checksum hoặc object-store version ID. Chỉ thêm một chuỗi vào `JobParameters` mà không kiểm tra file tương ứng **không tạo ra tính bất biến**.

### 5.2. Nguồn database cũng cần snapshot semantics

Đọc database theo từng page không có `ORDER BY` ổn định có thể bỏ sót hoặc lặp bản ghi khi dữ liệu thay đổi. Cần ghi:

- Dữ liệu nào được coi là thuộc một lần chạy: `created_at <= cutoff`, snapshot ID hay danh sách ID đã chốt?
- Sort key có duy nhất và ổn định không?
- Có transaction isolation/snapshot phù hợp không?
- Nguồn có thể bị cập nhật trong khi job đang đọc không?
- Nếu thay đổi giữa các page, job fail hay có reconciliation?

Giới hạn “đọc tối đa 500.000 bản ghi” không thay thế việc xác định **đọc đúng 500.000 bản ghi nào**.

## 6. Ghi JobInstance identity và tham số restart

Spring Batch phân biệt:

- **`Job`**: định nghĩa luồng xử lý.
- **`JobInstance`**: một công việc logic được xác định bởi tên job và các **identifying `JobParameters`**.
- **`JobExecution`**: một lần thử chạy của job instance; restart tạo execution mới.
- **`StepExecution`**: lần thực thi từng step, chứa status/counters và `ExecutionContext`.

Ví dụ hợp đồng tham số:

| Tham số | Identifying? | Ý nghĩa |
|---|---|---|
| `businessDate` | Có | Ngày nghiệp vụ cần đối soát |
| `sourceSystem` | Có | Đối tác |
| `inputVersion` | Có | Phiên bản đầu vào bất biến |
| `requestedBy` | Không | Audit người yêu cầu |
| `requestReason` | Không | Lý do vận hành |
| `traceId` | Không | Correlation ID cho log |

Ví dụ tạo tham số cho một job instance:

```java
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2025-05-12", true)
        .addString("sourceSystem", "PARTNER_A", true)
        .addString("inputVersion", "object-version-871", true)
        .addString("requestedBy", "ops-console", false)
        .toJobParameters();
```

**Giới hạn cần ghi:** “Cùng `businessDate + sourceSystem + inputVersion` là cùng một `JobInstance`. Không tự tạo identifying `run.id` mới để xử lý lại một execution đã `FAILED` hoặc `STOPPED` mà đáng lẽ phải restart.”

Nếu muốn chủ động reprocess một file đã được sửa, cần thiết kế một `inputVersion` mới hoặc một quy trình reprocessing riêng, kèm quy tắc ghi đè/reconciliation. Không thay đổi tham số tùy tiện chỉ để né `JobInstanceAlreadyCompleteException`.

### 6.1. Idempotency key khác JobExecution ID

Đừng dùng `jobExecutionId` như khóa duy nhất của giao dịch nghiệp vụ khi cần chống trùng qua restart. `jobExecutionId` sẽ thay đổi ở execution mới. Khóa nghiệp vụ như `(sourceSystem, sourceTransactionId)` mới thể hiện giao dịch không được tạo lặp.

**Tài liệu nên ghi cả hai loại khóa:** khóa để xác định job instance và khóa để chống trùng dữ liệu.

## 7. Thời gian: timezone, cutoff và SLA

Một câu như “job chạy hằng ngày lúc 01:00” vẫn để lại nhiều câu hỏi:

- 01:00 theo timezone nào?
- `businessDate` là ngày của scheduler hay ngày dữ liệu?
- Nếu scheduler chạy trễ sang ngày hôm sau thì chọn ngày nào?
- Thời gian cắt dữ liệu là inclusive hay exclusive?
- Nếu ngày đổi giờ mùa hè (DST), cửa sổ thời gian dài bao nhiêu?
- Khi restart vào ngày khác, có được tính lại cutoff không?

Ví dụ hợp đồng:

```text
Scheduler timezone: Asia/Ho_Chi_Minh
Schedule: 01:00 mỗi ngày
Business date: truyền rõ qua JobParameters
Data window: [businessDate 00:00, nextDate 00:00)
End boundary: exclusive
Restart: giữ nguyên businessDate và inputVersion
SLA: hoàn tất trước 03:00 cho tải nằm trong giới hạn thiết kế
```

Cửa sổ nửa mở `[startInclusive, endExclusive)` thường dễ ghép các ngày liên tiếp mà không đếm trùng bản ghi ở ranh giới.

### 7.1. Không đọc đồng hồ thật trong từng item

Tránh:

```java
// Dễ làm một job chạy qua nửa đêm xử lý hai cutoff khác nhau:
LocalDate businessDate = LocalDate.now();
```

Nên lấy `businessDate` từ `JobParameters` và tính các mốc thời gian một lần theo timezone nghiệp vụ:

```java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

LocalDate date = LocalDate.parse(businessDateText);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

Instant startInclusive =
        date.atStartOfDay(zone).toInstant();

Instant endExclusive =
        date.plusDays(1).atStartOfDay(zone).toInstant();
```

Nếu dữ liệu theo timezone khác, thay `zone` theo business contract. Không tự trừ cộng một số giờ cố định khi bài toán có thể liên quan DST; `atStartOfDay(zone)` và ngày kế tiếp xử lý thay đổi offset theo quy tắc timezone.

**Giả thiết:** dữ liệu nguồn có timezone/offset đúng và được normalize trước khi so cửa sổ. Nếu input chỉ chứa local timestamp không có timezone, cần quy tắc diễn giải rõ, không suy đoán từ timezone mặc định của server.

## 8. Giới hạn dữ liệu: volume, kích thước và dạng tải

Một job cần ghi **capacity envelope** — vùng tải mà hệ thống đã được thiết kế và kiểm thử.

| Yếu tố | Giới hạn ví dụ | Điều gì xảy ra nếu vượt? |
|---|---|---|
| Số file/input version | Một version cho mỗi job instance | Reject request ngoài hợp đồng |
| Kích thước file | Tối đa 500 MiB | Fail preflight/quarantine |
| Số bản ghi | Tối đa 2.000.000 | Không bắt đầu import nếu manifest vượt |
| Kích thước một record | Tối đa 32 KiB | Reject/quarantine record hoặc file theo policy |
| Độ dài business key | Tối đa 120 ký tự | Validation |
| Số lượng transaction active | Theo DB pool và concurrency | Throttle hoặc reject launch |
| Thời gian hoàn thành | SLO 30 phút ở tải chuẩn | Alert nếu vượt; không tự ghi status sai |
| Thời gian lưu nguồn | Ít nhất 30 ngày | Theo dõi retention và recovery window |

Các con số **không phải default Spring Batch**. Chúng phải dựa trên benchmark, giới hạn storage/database và SLA thực tế.

### 8.1. Giới hạn cứng và giới hạn mềm

- **Hard limit:** vượt là không thể xử lý an toàn hoặc không được phép. Ví dụ file lớn hơn dung lượng tối đa mà scanner/parser có thể xử lý; reject/fail trước khi ghi.
- **Soft limit/SLO:** vượt cần cảnh báo hoặc điều phối lại, nhưng không nhất thiết fail. Ví dụ job thường chạy 30 phút, hôm nay 35 phút vì tải tăng.
- **Resource budget:** số connection, heap, CPU, I/O có thể cấp cho job; khi vượt phải throttle hoặc dừng có kiểm soát.

Không nên đánh đồng “SLO 30 phút” với “bắt buộc kill JVM ở phút 30”. Kill cưỡng bức có thể để lại `JobRepository` ở trạng thái chưa được cập nhật, mất cơ hội checkpoint và cần recovery.

### 8.2. Throughput tối thiểu

Nếu phải xử lý 1.200.000 item trong 40 phút thì throughput end-to-end tối thiểu xấp xỉ:

```text
1.200.000 / (40 × 60) = 500 items/second
```

Đây là phép tính lý thuyết, chưa trừ thời gian preflight, file download, reconcile, startup và flush. Benchmark thực tế nên có margin để xử lý tải biến thiên và lỗi tạm thời.

Tài liệu nên chỉ rõ **workload tham chiếu**:

```text
Reference workload:
- 1.200.000 records
- average row 420 bytes
- 1% invalid records (nếu chính sách cho phép)
- PostgreSQL staging, index ở cấu hình production-like
- 4 batch workers
- 30-minute target for full job
```

Không báo rằng job “đạt SLA” chỉ vì chạy nhanh với 1.000 record trên H2. Test nhỏ chứng minh logic, không chứng minh capacity.

## 9. Giới hạn bộ nhớ, chunk size và transaction

Spring Batch xử lý theo chunk để giới hạn số item giữ trong bộ nhớ tại một thời điểm và định nghĩa ranh giới transaction thường gặp.

Ví dụ cấu hình:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.transaction.PlatformTransactionManager;

Step loadTransactionsStep(
        JobRepository repository,
        PlatformTransactionManager transactionManager,
        ItemReader<RawTransaction> reader,
        ItemProcessor<RawTransaction, ValidTransaction> processor,
        ItemWriter<ValidTransaction> writer) {

    return new StepBuilder("loadTransactionsStep", repository)
            .<RawTransaction, ValidTransaction>chunk(
                    200, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`RawTransaction` và `ValidTransaction` là các kiểu dữ liệu nghiệp vụ minh họa. `chunk(200, transactionManager)` thể hiện **commit interval theo số item đọc**, không phải giới hạn kích thước file, số câu JDBC batch hoặc số worker.

### 9.1. Ghi giả thiết cho chunk size

Ví dụ quyết định:

```text
Decision: chunk size = 200

Assumptions:
- Mỗi item nhỏ hơn 32 KiB.
- Reader tiến tuần tự trên snapshot bất biến.
- Writer dùng chung transaction manager của step.
- 200 item không khiến transaction giữ lock quá lâu.

Constraints:
- Timeout của từng thao tác database được cấu hình hữu hạn.
- Một chunk lỗi không được tự commit một phần qua connection riêng.

Verification:
- Benchmark với 50, 200, 500.
- Integration test writer lỗi ở item cuối chunk.
- Kiểm tra rollback và restart không mất/trùng dữ liệu.
```

Một giới hạn item-size không có nghĩa heap luôn đủ: còn buffer reader, JPA persistence context, cache, thread stack và objects tạm. Cần đo memory thực thay vì nhân `chunkSize × averageRowSize` rồi coi đó là toàn bộ heap.

### 9.2. Transaction thực sự bao phủ những gì?

Với `DataSourceTransactionManager` hoặc manager phù hợp, writer JDBC dùng cùng datasource có thể tham gia transaction của step. Nhưng gọi API HTTP, gửi email hoặc ghi object store không tự rollback khi transaction DB rollback.

**Giả thiết cần được ghi thành hạn chế:** “Tính atomic theo chunk chỉ áp dụng cho những thao tác tham gia đúng transaction; các external side effect cần idempotency/outbox.”

Nếu job ghi vào hai database khác nhau, không nên tuyên bố “all-or-nothing” chỉ vì mỗi datasource có transaction manager riêng. Phải chọn mô hình giao dịch phối hợp hoặc thiết kế eventual consistency/reconciliation phù hợp.

## 10. Retry, skip và rollback: giới hạn chịu lỗi

Spring Batch cho phép `faultTolerant()`, `retry(...)`, `retryLimit(...)`, `skip(...)` và `skipLimit(...)`. Nhưng một bộ tham số chung không phản ánh đầy đủ chính sách nghiệp vụ.

Ví dụ giả định:

| Loại lỗi | Retry | Skip | Kết quả mong đợi |
|---|---|---|---|
| Timeout DB tạm thời | Có, tối đa 3 lần | Không | Thành công hoặc step `FAILED` |
| Dòng CSV hỏng encoding | Không | Có nếu chính sách cho phép, tối đa giới hạn | Quarantine/quality gate |
| Mã giao dịch bị thiếu | Không | Không nếu giao dịch bắt buộc | Step `FAILED` |
| Payload trùng hoàn toàn | Không | Có thể dedup như filter/DB conflict | Audit duplicate |
| Payload cùng ID nhưng số tiền khác | Không | Không tự bỏ | Quarantine hoặc `FAILED` |
| File input bị thay version | Không | Không | Fail fast; không restart trên nguồn mới |
| Source file không tồn tại | Không | Không | Fail trước khi ghi |

Giới hạn `skipLimit` là tổng skip của step qua các giai đoạn được phép, không phải số skip riêng của từng giai đoạn. `retryLimit` là giới hạn thử lại theo policy framework, không có nghĩa một lỗi mạng có thể phục hồi nếu reader/cursor không cho phép đọc lại nhất quán.

### 10.1. Ví dụ fault-tolerant step

```java
import org.springframework.batch.item.file.FlatFileParseException;
import org.springframework.dao.TransientDataAccessException;

return new StepBuilder("loadTransactionsStep", repository)
        .<RawTransaction, ValidTransaction>chunk(
                200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(FlatFileParseException.class)
        .skipLimit(5)
        .build();
```

Đây là **ví dụ về policy**, không phải hướng dẫn mọi job tài chính nên chấp nhận bỏ qua 5 giao dịch. Trong một hệ thống đối soát, có thể bắt buộc fail toàn bộ khi bất kỳ dòng nào không đọc được. Chính sách kỹ thuật cần được ký xác nhận bởi chủ dữ liệu.

Không dùng `.skip(Exception.class)` chỉ để job “có vẻ ổn định”: nó có thể che lỗi cấu hình, lỗi bảo mật, lỗi hạ tầng và lỗi code.

### 10.2. Ghi giới hạn cho retry

Một quyết định tốt không chỉ nói “retry 3 lần”, mà còn ghi:

- Exception nào được xem là tạm thời.
- Có backoff không và khoảng nào.
- Timeout mỗi lần gọi API/DB là bao nhiêu.
- Retry tối đa ở **mỗi item, chunk hay remote request**.
- Khi thất bại cuối cùng, có được phép bỏ qua hay bắt buộc fail.
- Side effect có idempotent nếu request trước đã thực sự thành công nhưng phản hồi bị mất không.

Điều này quan trọng với API: client timeout không chứng minh server chưa xử lý yêu cầu. Nếu retry một POST tạo giao dịch, phải dùng idempotency key hoặc một giao thức phù hợp.

## 11. Restartability: ghi cả điều kiện và giới hạn

Nói “job hỗ trợ restart” là chưa đủ. Cần ghi **restart từ đâu, trên dữ liệu nào, và điều kiện nào khiến restart không an toàn**.

### 11.1. Ba câu hỏi trước khi tuyên bố restartable

1. **Reader có checkpoint?** `FlatFileItemReader`, `JdbcPagingItemReader` hoặc custom `ItemStreamReader` có lưu vị trí và thứ tự ổn định không?
2. **Đầu vào có bất biến?** File/object version, API snapshot hoặc staging data còn nguyên không?
3. **Writer có idempotent?** Dữ liệu đã commit ở chunk trước có bị chèn lại khi retry/restart không?

Một hợp đồng restart minh họa:

```text
Restart policy:
- Chỉ restart JobExecution FAILED hoặc STOPPED nếu framework cho phép.
- Cùng JobInstance: giữ identifying JobParameters.
- inputVersion không đổi.
- Reader khôi phục cursor từ StepExecutionContext.
- Database writer ghi theo unique business key.
- External notification tách qua outbox.
- Nếu checksum nguồn không khớp, reject restart.
- Nếu serialized ExecutionContext không tương thích, fail fast.
- Nếu source đã hết retention, áp dụng quy trình reprocess mới.
```

### 11.2. ExecutionContext có phạm vi rõ ràng

**StepExecution context** phù hợp cho checkpoint reader, như `nextIndex`, `lastId`, `pageToken`. **JobExecution context** thường dùng để trao đổi dữ liệu giữa các step, chẳng hạn đường dẫn output đã được xác nhận.

`ExecutionContext` phải lưu dữ liệu nhỏ, có thể serialize và cần thiết cho restart. Không lưu cả triệu bản ghi hoặc object không thể serialize chỉ để tránh re-read nguồn.

Nếu một delegate reader có `ItemStream` nhưng không được step đăng ký lifecycle `open/update/close`, checkpoint có thể không được lưu. Đối với các delegate ẩn trong composite/wrapper, có thể cần `.stream(delegate)`.

### 11.3. Ghi trạng thái `FAILED` không phải bằng chứng dữ liệu đã rollback hết

Một job có nhiều chunk:

```text
Chunk 1: COMMIT 200 records
Chunk 2: COMMIT 200 records
Chunk 3: writer lỗi -> ROLLBACK
JobExecution: FAILED
```

Khi đó 400 record của hai chunk đầu có thể vẫn tồn tại. Restart cần tiếp tục hợp lý, không giả định database rỗng chỉ vì job bị `FAILED`. Cũng không thể suy ra exact committed row count chỉ từ `readCount` hoặc `writeCount` nếu writer có dedup/upsert/filter.

## 12. Concurrency: job có được chạy song song không?

Một giả thiết nguy hiểm là “scheduler chỉ gọi một lần mỗi ngày”. Trong thực tế có thể có:

- Hai instance scheduler hoạt động do failover.
- Người vận hành bấm chạy lại khi job cũ vẫn xử lý.
- Hai file cùng ngày đến gần nhau.
- Một worker bị treo, monitor khởi động worker khác.
- Parallel steps hoặc partitioned step cùng ghi một bảng.

Ghi rõ **concurrency contract**:

| Cấp độ | Câu hỏi thiết kế | Ví dụ quyết định |
|---|---|---|
| Một `JobInstance` | Có được chạy hai execution cùng lúc? | Không; để framework/repository từ chối và giám sát |
| Cùng business date, khác input version | Có được xử lý song song không? | Không nếu cùng ghi snapshot cuối; cần orchestration lock |
| Khác business date | Có được xử lý song song không? | Có nếu khóa dữ liệu không giao nhau |
| Một step | Reader/writer có thread-safe không? | Reader stateful không dùng chung giữa các thread |
| Partitioning | Các vùng dữ liệu có chồng lấp? | Phân chia theo ID range hoặc hash key ổn định |
| Database | Có đủ connection/lock budget? | Giới hạn worker count và pool phù hợp |

Đừng kỳ vọng `ConcurrentHashMap` hoặc một lock trong JVM duy nhất bảo vệ hai ứng dụng khác nhau. Nếu concurrency liên quan tính duy nhất dữ liệu, cần ràng buộc database, khóa điều phối bền vững hoặc cơ chế tương đương.

### 12.1. Giới hạn số worker không đồng nghĩa bảo đảm thứ tự

Nếu xử lý theo nhiều partition, thứ tự hoàn tất giữa partition là không xác định. Chính sách “record nào đến trước thì thắng” có thể thay đổi theo schedule.

Khi cần chọn bản cập nhật mới nhất, dùng `sourceVersion`, `eventTime` và tie-breaker ổn định thay vì thứ tự thread. Khi dữ liệu có tính cộng dồn, thiết kế phép tổng hợp có tính kết hợp/commutative hoặc điều phối thứ tự rõ ràng.

## 13. Data quality: tiêu chuẩn chấp nhận đầu ra

Giả thiết “dữ liệu nguồn sạch” hiếm khi đủ cho production. Nên viết một **bảng kiểm soát chất lượng**:

| Điều kiện | Ngưỡng ví dụ | Hành động |
|---|---|---|
| Thiếu `sourceTransactionId` | 0 | Fail import |
| Giá trị amount âm khi hợp đồng cấm | 0 | Fail/quarantine |
| Dòng malformed nhưng không chứa giao dịch quan trọng | Tối đa 5 | Audit + quality gate |
| Duplicate cùng key và payload giống nhau | Cho phép dedup | Đếm extra occurrences |
| Duplicate cùng key nhưng amount khác nhau | 0 | Fail/quarantine |
| Tổng amount nguồn/đích lệch | 0 | Không phát `DataReady` |
| Record count mismatch | 0 (sau khi cộng các nhóm loại trừ) | Fail reconciliation |
| Schema version không hỗ trợ | 0 | Reject input |

Các ngưỡng ví dụ phải được xác nhận với chủ dữ liệu. Không nên chỉ bật `skipLimit(10)` mà không tính item bị skip vào reconciliation.

### 13.1. Phương trình đối soát cần rõ

Một công thức minh họa với các nhóm được định nghĩa loại trừ nhau:

```text
totalInputRows
  = acceptedUniqueRows
  + exactDuplicateExtraRows
  + invalidRows
  + conflictingDuplicateRows
```

Công thức chỉ hợp lệ khi chính sách tính duplicate là theo **số occurrences thừa** và mỗi input row được gán đúng một nhóm. Nếu thống kê theo số nhóm duplicate hoặc chọn một bản thắng trong nhóm conflict, công thức phải thay đổi.

**Không lấy `StepExecution.writeCount` làm số dòng database mới chèn** khi writer dùng `INSERT ... ON CONFLICT DO NOTHING` hoặc một item có thể sinh nhiều lệnh ghi.

### 13.2. Quality gate là một bước rõ ràng

Một kiến trúc dễ vận hành:

```text
validateInputManifest
        |
        v
loadTransactions
        |
        v
reconcileTotals
        |
   +----+----+
   |         |
  PASS      FAIL
   |         |
   v         v
markReady   Job FAILED / quarantine
```

Nếu logic đối soát phát hiện tổng tiền sai, bước đó nên trả lỗi/exit status theo flow đã thiết kế. Không phát completion event mang ý nghĩa “dữ liệu sẵn sàng” chỉ vì step nhập liệu đã `COMPLETED`.

## 14. Security và compliance cũng là giới hạn của job

Một job “chỉ chạy nội bộ” có thể được chạy bằng account có quyền rộng và đọc dữ liệu nhạy cảm. Vì vậy job contract cần ghi:

- Ai được phép launch/restart/stop?
- Ai được phép chọn `sourceSystem`, `tenantId` hoặc file version?
- Job dùng database user có quyền gì?
- File/object storage path nào được phép đọc?
- Những dữ liệu nào không được ghi vào log hoặc `ExecutionContext`?
- Đầu ra chứa dữ liệu cá nhân có cần mã hóa/retention/audit không?
- Có thể gọi outbound API nào?
- Nếu phát hiện schema lạ hoặc path bất thường, job phản ứng ra sao?

### 14.1. `JobParameters` không phải kênh lưu secret

`JobParameters` được lưu trong batch metadata và có thể hiển thị qua công cụ vận hành. Không đưa access token, mật khẩu hoặc private key vào đó.

Nên truyền một khóa tham chiếu không nhạy cảm rồi lấy credential từ secret manager/ứng dụng cấu hình bảo mật. Tương tự, `ExecutionContext` cũng không phải nơi lưu connection/password/runtime client object.

### 14.2. Ranh giới an toàn cho dữ liệu

Nếu file name do người dùng truyền vào, cần validate và giới hạn vùng filesystem; nếu SQL dùng dữ liệu từ CSV, phải bind tham số. Các giả thiết “tên file luôn đúng” hoặc “partner không bao giờ gửi ký tự đặc biệt” không được dùng để bỏ qua parameter binding và authorization.

## 15. Observability: giả thiết nào cần được đo?

Một điều kiện chỉ được ghi vào tài liệu nhưng không được kiểm tra có thể trở thành lỗi âm thầm khi hệ thống thay đổi.

Gắn giả thiết với chỉ số phù hợp:

| Giả thiết/giới hạn | Metric hoặc kiểm tra |
|---|---|
| File đến trước 01:00 | `input_arrival_lag_seconds` |
| Input không vượt 2 triệu records | Manifest recordCount, `input_rows_total` |
| Job chạy trong SLO | `spring.batch.job` duration và ngưỡng theo workload |
| Step không bị treo | `spring.batch.step.active` hoặc active elapsed |
| Nguồn bất biến khi restart | Checksum/version comparison |
| Duplicate không vượt ngưỡng | `duplicate_extra_rows_total` |
| Sai lệch tổng tiền bằng 0 | Reconciliation result |
| Không có skip không được phép | `StepExecution` read/process/write skip counters |
| Retry lỗi DB nằm trong giới hạn | Retry metrics/log theo exception class |
| Mỗi ngày chỉ có một output “ready” | Unique business key của output event |
| Không ghi dữ liệu sai tenant | Authorization test và audit |

Các metric có tên `input_arrival_lag_seconds`, `duplicate_extra_rows_total` là **metric do ứng dụng tự định nghĩa**, không phải Spring Batch mặc định tạo. Các meter Spring Batch/Micrometer thực tế cần kiểm tra theo version/config của dự án.

Không dùng `jobExecutionId`, `sourceTransactionId` hay raw error message làm tag Prometheus vì cardinality cao và có thể lộ dữ liệu. ID chi tiết nên nằm trong log/trace có phân quyền.

### 15.1. Ghi cách diễn giải dashboard

Tài liệu nên nói rõ:

- Duration được đo cho job execution hay cộng duration của các step?
- Thời gian đang chạy được tính thế nào nếu step chưa có `endTime`?
- Có bao gồm job `FAILED`/`STOPPED` trong thống kê không?
- Kết quả percentile có đủ mẫu để đáng tin không?
- Nếu process chết mà `JobRepository` còn `STARTED`, ai xác minh liveness?

Đừng cộng duration các parallel step để khẳng định đó là wall-clock duration của job. Với step song song, thời gian có thể chồng lấp.

## 16. Từ tài liệu sang code: validate giả thiết đầu vào

Một số giả thiết nên chuyển thành **hard checks** trong ứng dụng. Với Spring Batch 5.2, `JobParametersValidator` là điểm mở rộng phù hợp để kiểm tra các tham số ngay trước khi job thực thi.

### 16.1. Validator cho tham số cơ bản

```java
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.Set;
import java.util.regex.Pattern;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.batch.core.JobParametersValidator;

public final class SettlementJobParametersValidator
        implements JobParametersValidator {

    private static final Set<String> ALLOWED_SOURCES =
            Set.of("PARTNER_A", "PARTNER_B");

    private static final Pattern INPUT_VERSION =
            Pattern.compile("[A-Za-z0-9][A-Za-z0-9._-]{0,127}");

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        if (parameters == null) {
            throw new JobParametersInvalidException(
                    "Missing JobParameters");
        }

        String businessDate = parameters.getString("businessDate");
        String source = parameters.getString("sourceSystem");
        String version = parameters.getString("inputVersion");

        if (businessDate == null) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must be a valid ISO date");
        }

        if (!ALLOWED_SOURCES.contains(source)) {
            throw new JobParametersInvalidException(
                    "sourceSystem is not supported");
        }

        if (version == null
                || !INPUT_VERSION.matcher(version).matches()) {
            throw new JobParametersInvalidException(
                    "inputVersion is invalid");
        }
    }
}
```

Validation này kiểm tra **định dạng và allowlist**, chưa chứng minh:

- Input version thật sự tồn tại.
- Dữ liệu version đó là immutable.
- Caller được quyền chạy nguồn đã chọn.
- File có đúng schema.
- Manifest có đủ số dòng/tổng tiền.

Những điều trên cần được kiểm tra thêm ở API authorization hoặc preflight step. Không dùng regex hợp lệ làm bằng chứng toàn bộ dữ liệu an toàn.

### 16.2. Đăng ký validator vào JobBuilder

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job dailyPartnerSettlement(
        JobRepository repository,
        Step validateInputManifest,
        Step loadTransactions,
        Step reconcileTotals,
        Step markResultReady) {

    return new JobBuilder("dailyPartnerSettlement", repository)
            .validator(new SettlementJobParametersValidator())
            .start(validateInputManifest)
            .next(loadTransactions)
            .next(reconcileTotals)
            .next(markResultReady)
            .build();
}
```

Bốn step trong ví dụ được giả định đã khai báo riêng. Đây là cấu hình **flow tuyến tính**: nếu một step thất bại và không có transition đặc biệt cho phép đi tiếp, job không đi tới step tiếp theo như một lượt thành công bình thường.

Việc có `markResultReady` sau `reconcileTotals` giúp thể hiện rõ rằng “job đã đọc xong file” khác “dữ liệu đã sẵn sàng cho downstream”.

## 17. Preflight step: kiểm tra giới hạn trước khi ghi dữ liệu

Một giới hạn như “input tối đa 2 triệu record” chỉ hữu ích khi được kiểm tra trước khi bắt đầu import tốn tài nguyên.

Giả sử hệ thống lưu manifest theo `inputVersion`:

```java
public record InputManifest(
        String inputVersion,
        String schemaVersion,
        long byteSize,
        long recordCount,
        String checksum
) {
}
```

Một service kiểm tra manifest:

```java
public final class InputManifestPolicy {

    public static final long MAX_FILE_BYTES =
            500L * 1024L * 1024L;

    public static final long MAX_RECORDS = 2_000_000L;

    public void validate(
            InputManifest manifest,
            String expectedVersion) {

        if (manifest == null) {
            throw new IllegalStateException("Input manifest missing");
        }

        if (!expectedVersion.equals(manifest.inputVersion())) {
            throw new IllegalStateException(
                    "Input version does not match parameters");
        }

        if (!"v2".equals(manifest.schemaVersion())) {
            throw new IllegalStateException(
                    "Unsupported schema version");
        }

        if (manifest.byteSize() < 0
                || manifest.byteSize() > MAX_FILE_BYTES) {
            throw new IllegalStateException(
                    "Input exceeds allowed byte size");
        }

        if (manifest.recordCount() < 0
                || manifest.recordCount() > MAX_RECORDS) {
            throw new IllegalStateException(
                    "Input exceeds allowed record count");
        }

        if (manifest.checksum() == null
                || manifest.checksum().isBlank()) {
            throw new IllegalStateException(
                    "Input checksum is missing");
        }
    }
}
```

Đây là một **policy mẫu**, không có sẵn trong Spring Batch. Chú ý: việc manifest ghi checksum không tự chứng minh checksum khớp nội dung; phải có nguồn đáng tin tính và/hoặc xác minh checksum khi mở input.

### 17.1. Tasklet preflight

```java
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public final class ValidateInputManifestTasklet
        implements Tasklet {

    private final InputManifestRepository repository;
    private final InputManifestPolicy policy;
    private final String inputVersion;

    public ValidateInputManifestTasklet(
            InputManifestRepository repository,
            InputManifestPolicy policy,
            String inputVersion) {

        this.repository = repository;
        this.policy = policy;
        this.inputVersion = inputVersion;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext context) {

        InputManifest manifest =
                repository.findRequired(inputVersion);

        policy.validate(manifest, inputVersion);

        return RepeatStatus.FINISHED;
    }
}
```

`InputManifestRepository` là interface nghiệp vụ giả định cung cấp `findRequired(String)`; cần triển khai theo storage thực tế. Nếu manifest sai, tasklet ném exception khiến preflight thất bại, trước khi step nhập liệu bắt đầu.

Đừng đặt kiểm tra số dòng chỉ ở cuối job rồi tiếp tục import file 100 GB dù thiết kế chỉ hỗ trợ 500 MiB. Ngoài preflight, vẫn cần cơ chế giới hạn streaming khi metadata từ nguồn không đáng tin hoặc có thể thay đổi.

## 18. Giới hạn tài nguyên và backpressure

Một job không thể được coi là “ổn định” chỉ nhờ `chunk(200)` nếu nó chạy 100 worker và mỗi worker mở nhiều connection.

Giới hạn vận hành có thể bao gồm:

```text
Maximum concurrent executions per source: 1
Maximum worker threads: 4
JDBC pool max connections reserved/shared: theo cấu hình
Database statement timeout: hữu hạn
HTTP request timeout: hữu hạn
Retry max attempts: theo policy
Memory budget: theo container limit
Output publishing: không chạy trước reconciliation
```

Không nên đặt hard limit tùy ý mà không đo. Một job có cùng số record nhưng row rộng hơn 10 lần hoặc writer gọi API chậm hơn có thể vượt memory/time budget.

### 18.1. Khi vượt công suất phải làm gì?

Có vài phương án, cần ghi rõ lựa chọn:

- **Reject trước launch** nếu vượt hard limit.
- **Đợi trong queue** nếu hệ thống hỗ trợ điều phối; không tạo hàng trăm execution cùng lúc.
- **Throttle concurrency** nếu bottleneck là database/API.
- **Chia partition an toàn** nếu dữ liệu có phân vùng độc lập và worker đủ tài nguyên.
- **Dừng có kiểm soát** nếu vận hành quyết định dừng; `JobOperator.stop` gửi yêu cầu dừng, không kill thread tức thời.
- **Fail và báo sự cố** nếu job không thể hoàn tất trong phạm vi dữ liệu/consistency đã chấp nhận.

Không tự đổi status `STOPPED` hoặc `COMPLETED` trong metadata để “đáp ứng SLA”. Trạng thái phải phản ánh thực tế framework và dữ liệu.

## 19. Ghi các phụ thuộc bên ngoài

Một job có thể phụ thuộc nhiều hệ thống:

| Phụ thuộc | Điều kiện giả thiết | Giới hạn/hành động |
|---|---|---|
| Object storage | File version tồn tại, đọc nhất quán | Timeout và checksum; fail nếu source đổi |
| PostgreSQL | DB có đủ connection, transaction đúng | Bounded retry cho lỗi tạm thời |
| Message broker | Delivery có thể lặp | Consumer idempotent |
| API tỷ giá | Một snapshot tỷ giá cho business date | Chốt rate version trước khi nhập |
| Secret manager | Credential còn hợp lệ trong thời gian chạy | Refresh theo client policy, không lưu secret vào context |
| Scheduler | Có thể gọi lại/overlap | Job instance identity và lock điều phối |
| Monitoring | Metric endpoint có thể bị gián đoạn | Không làm business transaction phụ thuộc trực tiếp vào metrics |

Một giả thiết đặc biệt quan trọng: **“API gọi xong mà client timeout” không chứng minh API chưa xử lý yêu cầu**. Nếu writer gọi dịch vụ thanh toán hoặc gửi lệnh có side effect, cần idempotency key hoặc cơ chế đối soát riêng. Checkpoint của Spring Batch chỉ quản lý tiến độ trong giới hạn transaction/infrastructure mà job sử dụng.

## 20. Ghi quyết định bằng ADR thay vì chỉ trong comment

**Architecture Decision Record (ADR)** là một bản ghi ngắn giải thích vì sao chọn một cách thiết kế, trong bối cảnh và ràng buộc nào. Với batch, một ADR thường nêu:

1. ID, tiêu đề, ngày và trạng thái của quyết định.
2. Bối cảnh nghiệp vụ và hệ thống.
3. Giả thiết và bằng chứng.
4. Ràng buộc kỹ thuật/SLA/dữ liệu.
5. Các phương án đã cân nhắc.
6. Quyết định và lý do.
7. Hệ quả, trade-off và rủi ro còn lại.
8. Cách kiểm chứng.
9. Điều kiện phải xem xét lại.
10. Người chịu trách nhiệm và liên kết tới test/monitoring.

### 20.1. Mẫu ADR có thể dùng lại

```markdown
# ADR-BATCH-001 — <Tên quyết định>

Status: Proposed / Accepted / Superseded
Owner: <Nhóm phụ trách>
Date: <YYYY-MM-DD>
Job: <jobName>
Related requirements: <link>

## Context
Bài toán nghiệp vụ, dữ liệu đầu vào và SLA.

## Assumptions
| ID | Giả thiết | Bằng chứng | Owner | Cách kiểm tra |
|----|-----------|------------|-------|---------------|

## Constraints and invariants
| ID | Điều kiện | Giới hạn/định nghĩa | Hành động khi vi phạm |
|----|-----------|---------------------|-----------------------|

## Options considered
- A: ...
- B: ...

## Decision
Chọn phương án ... vì ...

## Consequences
- Ưu điểm ...
- Hạn chế ...
- Rủi ro ...

## Validation
- Unit test ...
- Integration test ...
- Load test ...
- Monitoring ...

## Review triggers
- Schema/source thay đổi
- Dữ liệu vượt giới hạn
- DB/driver/framework upgrade
- SLA hoặc retry contract thay đổi
```

Một ADR không nhất thiết phải dài. Điều quan trọng là **các quyết định có thể kiểm chứng và thay đổi được quản lý**, thay vì rải rác trong các comment code khó tìm.

### 20.2. ADR mẫu đã điền: chọn staging snapshot

```markdown
# ADR-BATCH-017 — Đọc input version bất biến

Status: Accepted
Job: dailyPartnerSettlement
Owner: Batch Platform + Finance Data
Decision date: 2025-05-12

## Context
Đối tác có thể gửi lại file và job có thể FAILED giữa chừng.
Dữ liệu phải restart được mà không trùng/mất giao dịch.

## Assumptions
- Mỗi inputVersion trỏ tới đúng một nội dung bất biến.
- Storage giữ version ít nhất bằng thời hạn recovery đã cam kết.
- sourceTransactionId là định danh duy nhất trong sourceSystem.

## Constraints
- Không đọc "latest file" trong một lần restart.
- Nếu checksum/version mismatch: fail fast.
- Writer bảo vệ uniqueness bằng business key.
- Không gọi API gửi tiền trong transaction nhập staging.

## Options considered
A. Đọc file latest trực tiếp: đơn giản nhưng dễ đổi nội dung.
B. Chốt object version + checksum: thêm preflight nhưng restart ổn định.
C. Đọc API live mỗi lần: phụ thuộc paging và thay đổi nguồn.

## Decision
Chọn B. JobParameters giữ inputVersion; reader xác minh source.
Step ExecutionContext chỉ lưu cursor/checkpoint.

## Consequences
- Tốn chi phí lưu version.
- Có thể reprocess chính xác một snapshot đã chốt.
- Phải báo lỗi nếu version đã bị xóa quá sớm.

## Validation
- Test restart với cùng source: không thiếu/trùng.
- Test source bị đổi: không được tiếp tục.
- Kiểm tra retention và checksum trên storage.
- Dashboard cảnh báo inputVersion unavailable.

## Review triggers
- Storage thay đổi cơ chế versioning.
- Data volume vượt khả năng giữ snapshot.
- Tăng concurrency hoặc đổi chiến lược partition.
```

Mọi con số/thời điểm trong mẫu là minh họa. Ở dự án thật, ADR cần liên kết tới owner, version code, test và metric thực tế để người sau có thể kiểm tra.

## 21. Assumption register: ghi ai chịu trách nhiệm và khi nào phải xem lại

Với job quan trọng, một ADR có thể không đủ để theo dõi hàng chục giả thiết thay đổi theo thời gian. Có thể tạo **assumption register**:

| ID | Giả thiết | Mức ảnh hưởng nếu sai | Cách chứng minh | Owner | Trạng thái |
|---|---|---|---|---|---|
| A-01 | Source snapshot bất biến | Critical | Version + checksum test | Data Platform | Đã xác minh |
| A-02 | sourceTransactionId không tái sử dụng | Critical | Hợp đồng đối tác + duplicate report | Partner Ops | Cần xác nhận |
| A-03 | File ≤ 500 MiB | High | Historical p99 + hard preflight | Batch Team | Đã xác minh |
| A-04 | DB pool đủ cho 4 worker | Medium | Load test + pool metrics | Infra | Đang đo |
| A-05 | Dữ liệu đến trước 01:00 | Medium | Arrival-time monitoring | Partner Ops | Chưa ổn định |

Nếu giả thiết `A-02` **chưa được xác minh**, không nên tuyên bố dữ liệu chắc chắn không trùng. Có thể thiết kế unique constraint như defense-in-depth và đánh dấu rõ rủi ro còn lại.

### 21.1. Các trạng thái có ích

- **Proposed:** mới được nêu, chưa có bằng chứng.
- **Verified:** đã có bằng chứng hoặc test phù hợp.
- **Violated:** hệ thống quan sát điều kiện không còn đúng.
- **Deprecated:** không còn áp dụng.
- **Replaced:** thay bằng quy tắc/thiết kế khác.

Đây là trạng thái quản trị giả thiết **do nhóm dự án định nghĩa**, không phải `BatchStatus` của Spring Batch.

## 22. Chuyển giới hạn thành test chấp nhận

Tài liệu đáng tin khi có thể trả lời “đã kiểm chứng bằng gì?”. Nên có ít nhất ba nhóm kiểm thử.

### 22.1. Unit test cho validator và policy

Ví dụ kiểm tra quy tắc input size:

```java
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class InputManifestPolicyTest {

    private final InputManifestPolicy policy =
            new InputManifestPolicy();

    @Test
    void acceptsManifestInsideLimits() {
        InputManifest manifest = new InputManifest(
                "version-1",
                "v2",
                100_000L,
                2_000L,
                "checksum-abc"
        );

        assertDoesNotThrow(() ->
                policy.validate(manifest, "version-1"));
    }

    @Test
    void rejectsExcessiveRecordCount() {
        InputManifest manifest = new InputManifest(
                "version-1",
                "v2",
                100_000L,
                2_000_001L,
                "checksum-abc"
        );

        assertThrows(
                IllegalStateException.class,
                () -> policy.validate(manifest, "version-1")
        );
    }

    @Test
    void rejectsChangedInputVersion() {
        InputManifest manifest = new InputManifest(
                "version-2",
                "v2",
                100_000L,
                2_000L,
                "checksum-abc"
        );

        assertThrows(
                IllegalStateException.class,
                () -> policy.validate(manifest, "version-1")
        );
    }
}
```

Đoạn test này chỉ kiểm tra **hàm policy**. Nó chưa chứng minh file thực sự đúng checksum hoặc Spring Batch gọi preflight trước writer.

### 22.2. Integration test với job thật

Dùng `spring-batch-test`, `@SpringBatchTest` và `JobLauncherTestUtils` để kiểm chứng:

- Validator từ chối job parameters sai.
- Preflight fail trước khi step ghi dữ liệu chạy.
- Reader/writer dùng `inputVersion` đã chốt.
- Khi writer lỗi sau hai chunk, chỉ các chunk đã commit tồn tại.
- Restart cùng `JobInstance` đọc tiếp đúng checkpoint.
- Sau restart, business key không trùng, reconcile đạt yêu cầu.
- Một step downstream không được gọi nếu quality gate fail.
- Lệnh stop khi đang chạy kết thúc ở trạng thái thực tế được quan sát, không giả định stop tức thì.

Một test sử dụng in-memory list writer **không chứng minh rollback JDBC**; với consistency quan trọng, cần test tích hợp với datasource và transaction manager tương tự production.

### 22.3. Performance và failure-injection test

Các giả thiết capacity cần đo bằng workload đại diện. Ví dụ ma trận:

| Bài kiểm thử | Mục tiêu | Kết quả cần ghi |
|---|---|---|
| 100.000 records | Baseline nhỏ | Job/step duration, CPU, heap |
| 1.200.000 records | Tải tham chiếu | SLA, throughput, lock wait |
| 2.000.000 records | Giới hạn chấp nhận | Không OOM, không phá DB |
| 2.000.001 records | Vượt hard limit | Reject trước import |
| DB timeout | Recovery | Retry bounded rồi fail hoặc hoàn tất |
| File bị thay giữa restart | Data integrity | Không đọc tiếp trên version khác |
| Broker redelivery | Idempotency | Không phát side effect trùng |
| Hai scheduler cùng launch | Concurrency | Không ghi trùng hoặc chạy sai instance |
| Worker bị kill | Recovery | Metadata được điều tra và xử lý an toàn |

Đừng ghi “pass” nếu chưa chạy. Tài liệu nên có ô **evidence link, môi trường, ngày kiểm thử, commit/version và kết quả đo**. Một benchmark trên môi trường test rất nhỏ không tự chứng minh production sẽ đạt cùng throughput.

## 23. Runbook: người vận hành cần biết giới hạn nào?

Ngoài tài liệu thiết kế, nên có một **runbook** ngắn giúp thao tác khi giả thiết bị vi phạm.

Ví dụ:

```text
Job: dailyPartnerSettlement

When input file missing:
  - Không tự đổi sang latest file.
  - Xác minh sourceSystem, businessDate, inputVersion.
  - Liên hệ upstream/source owner.
  - Chỉ launch lại với version đã được phê duyệt.

When input exceeds MAX_RECORDS:
  - Không tăng limit trong production ngay lập tức.
  - Kiểm tra volume thật, schema và khả năng DB.
  - Chạy benchmark/review capacity trước khi đổi limit.

When job FAILED after some chunks:
  - Kiểm tra StepExecution và ExecutionContext.
  - Kiểm tra dữ liệu đã commit theo business key.
  - Chỉ restart nếu inputVersion giữ nguyên.

When reconciliation mismatches:
  - Không phát DataReady.
  - Thu thập manifest, read/write/skip counts và DB aggregates.
  - Quarantine hoặc xử lý theo data-quality policy.

When job STARTED quá lâu:
  - Kiểm tra worker liveness và thời gian chờ I/O.
  - JobOperator.stop là yêu cầu dừng mềm, không phải kill.
  - Không sửa metadata thành STOPPED thủ công chỉ để hết cảnh báo.
```

Runbook cũng cần chỉ rõ **đường dẫn dashboard**, nơi xem `jobExecutionId`, cách lấy log và người chịu trách nhiệm xử lý. Không lưu password/token trong runbook.

## 24. Khi nào phải cập nhật giả thiết/giới hạn?

Các sự kiện thường đòi hỏi xem lại job contract:

- Upstream đổi schema, encoding, paging hoặc duplicate policy.
- Khối lượng dữ liệu tăng vượt vùng đã benchmark.
- Business chuyển từ xử lý hằng ngày sang gần thời gian thực.
- Thêm parallelism/partitioning hoặc đổi số worker.
- Đổi database, JDBC driver, transaction manager hoặc connection pool.
- Thêm external API side effect vào writer.
- Nâng cấp Spring Batch/Spring Boot làm thay đổi checkpoint serializer/API.
- Đổi retention file/source hoặc quyền truy cập.
- Thay SLA, quy tắc tính ngày nghiệp vụ, timezone.
- Có một sự cố mất/trùng dữ liệu, crash hoặc job bị kẹt metadata.

Nên gắn job contract với **version control**. Khi cập nhật một ràng buộc, phải rà soát đồng thời code validation, test, alert, dashboard, runbook và điều kiện restart. Đừng sửa giới hạn trên wiki nhưng giữ code cũ; cũng đừng đổi code mà không thông báo cho người vận hành.

### 24.1. Luồng review quyết định

```text
New requirement / incident
          |
          v
Identify assumption or limit
          |
          v
Assess data integrity + risk
          |
          v
Evaluate alternatives
          |
          v
Update ADR/job contract
          |
          v
Implement guardrails and tests
          |
          v
Benchmark / failure test
          |
          v
Approve & deploy
          |
          v
Monitor assumption in production
```

Nếu dữ liệu đầu vào phụ thuộc hợp đồng với đối tác, owner kỹ thuật không nên tự xác nhận thay business/data owner rằng một dòng bị skip là chấp nhận được. Quyền quyết định chất lượng dữ liệu và quyền quyết định triển khai kỹ thuật có thể thuộc các nhóm khác nhau.

## 25. Những anti-pattern thường gặp

| Anti-pattern | Vì sao nguy hiểm? | Cách thay thế |
|---|---|---|
| “Job hỗ trợ file lớn” | Không đo được “lớn” | Số dòng/bytes/workload đã benchmark |
| “Dữ liệu luôn sạch” | Bỏ sót schema/quality validation | Input contract và quality gate |
| “Không có duplicate vì đối tác cam kết” | Retry và scheduler có thể phát lại | Business key + unique constraint + audit |
| “Restart được vì dùng Spring Batch” | Reader không lưu checkpoint hoặc input đổi | ItemStream, immutable source và restart test |
| “FAILED nghĩa là chưa ghi gì” | Chunk trước đã commit | Đối soát transaction/checkpoint |
| “Exactly once” cho HTTP call trong writer | DB rollback không rollback HTTP | Outbox/idempotency/reconciliation |
| Chỉ dùng `run.id` mới để xử lý lỗi | Tạo JobInstance mới, bỏ checkpoint | Restart đúng instance hoặc reprocess có chủ đích |
| Coi `writeCount` là số dòng DB | Upsert/dedup có thể ghi ít hơn | Check affected rows/reconciliation |
| Không ghi timezone/cutoff | Chạy qua nửa đêm xử lý sai ngày | Business date và interval rõ ràng |
| “Timeout thì kill process” | Metadata có thể chưa cập nhật | Graceful stop và recovery runbook |
| Tăng `chunkSize`/threads không đo | Lock, memory và DB pool có thể nghẽn | Load test và capacity envelope |
| Tất cả lỗi đều `skip(Exception.class)` | Che lỗi dữ liệu, bảo mật, hạ tầng | Fault policy theo exception |
| Chỉ test happy path | Không thấy lỗi restart/overlap | Fault injection và concurrency test |
| Giả thiết không có owner | Không ai xác nhận khi upstream đổi | Assumption register + review trigger |
| Giới hạn chỉ nằm trong wiki | Code vẫn nhận input vượt limit | Runtime guard + test + alert |
| Không có out-of-scope | Người dùng tưởng job làm cả việc không được thiết kế | Ghi mục tiêu và phạm vi loại trừ |
| Sửa SQL/metadata thủ công để job “chạy tiếp” | Có thể gây mất/trùng dữ liệu | Quy trình recovery có kiểm soát |
| Đưa secret vào `JobParameters`/`ExecutionContext` | Metadata lưu dài hạn và có thể bị xem | Secret manager + least privilege |

## 26. Bài tập thực hành: tạo job contract và ADR

Bạn được giao thiết kế job `importDailyTransactions` xử lý file CSV từ ba đối tác, tối đa 3 triệu dòng/ngày, ghi PostgreSQL và kích hoạt bước báo cáo khi kết quả được xác nhận.

Hãy hoàn thành các phần sau:

1. Viết **job contract** nêu mục tiêu, out-of-scope, đầu vào, đầu ra và tiêu chí `DataReady`.
2. Liệt kê ít nhất 10 giả thiết, phân loại theo data/schema, time, transaction, restart, concurrency, external dependency và security.
3. Với mỗi giả thiết, ghi bằng chứng hiện có, owner, mức độ ảnh hưởng nếu sai và cơ chế phát hiện.
4. Chọn identifying `JobParameters` và giải thích vì sao `jobExecutionId` không phù hợp làm business idempotency key.
5. Ghi capacity envelope: kích thước file, số dòng, item size, concurrency, DB pool và thời gian mục tiêu. Phân biệt hard limit với SLO.
6. Chọn chunk size ban đầu và mô tả cách benchmark để xác nhận, không suy đoán từ cấu hình mặc định.
7. Thiết kế preflight step kiểm tra manifest, source version, schema và giới hạn khối lượng trước khi ghi dữ liệu.
8. Định nghĩa retry/skip policy: lỗi nào retry, lỗi nào được phép bỏ, lỗi nào fail toàn job và vì sao.
9. Viết restart contract có checkpoint, input immutability và writer idempotency; mô phỏng lỗi sau ba chunk.
10. Thiết kế reconciliation: tổng input, accepted, rejected, duplicate và tổng amount phải liên hệ thế nào?
11. Xác định quy tắc xử lý hai scheduler cùng khởi chạy một business date.
12. Viết ADR lựa chọn giữa đọc trực tiếp API live và chốt immutable staging snapshot; nêu rủi ro còn lại.
13. Viết tối thiểu ba unit test cho policy, ba integration test cho transaction/restart và ba load/failure scenarios.
14. Tạo bảng các assumption chưa được xác minh và đề xuất kế hoạch đo/bằng chứng trước khi deploy.
15. Viết runbook cho tình huống input vượt limit, checksum mismatch và worker chết giữa chunk.
16. Định nghĩa review triggers khi upstream đổi schema, dữ liệu tăng gấp đôi hoặc ứng dụng nâng cấp Spring Batch.

**Câu hỏi ôn tập:** Nếu job đã chạy ổn trong sáu tháng với 100.000 dòng/ngày, có thể ghi rằng “job hỗ trợ tối đa 2 triệu dòng” mà không cần đo không?

**Trả lời:** **Không.** Thời gian chạy với 100.000 dòng chỉ là một bằng chứng trong phạm vi đã quan sát. Giới hạn 2 triệu cần được chứng minh bằng workload, database, memory, concurrency và failure/restart test đại diện. Nếu chưa đo, ghi đó là **giả thiết/chỉ tiêu cần xác minh**, không phải một cam kết đã được bảo đảm.

## 27. Tài liệu tham khảo

- [Spring Batch Reference — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `Job`, `JobInstance`, `JobExecution`, `StepExecution` và trạng thái.
- [Spring Batch Reference — Configuring a Job](https://docs.spring.io/spring-batch/reference/job/configuring.html): `JobParametersValidator`, restartability và định nghĩa job.
- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): commit interval, transaction và vòng xử lý reader/processor/writer.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `ExecutionContext` và checkpoint.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): lựa chọn retry theo exception.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): skip policy và skip limit.
- [Spring Batch Reference — Controlling Rollback](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/controlling-rollback.html): giới hạn rollback trong chunk.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): duration và số liệu theo dõi.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `spring-batch-test` và kiểm thử step/job.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): phạm vi transaction và integration với dữ liệu.
- [AWS Prescriptive Guidance — ADR Process](https://docs.aws.amazon.com/prescriptive-guidance/latest/architectural-decision-records/adr-process.html): cách ghi và quản lý architecture decision records.
