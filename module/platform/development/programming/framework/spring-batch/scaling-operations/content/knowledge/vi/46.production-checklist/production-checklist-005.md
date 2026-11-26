# Đã kiểm tra restartability trước khi đưa Spring Batch lên production

Một job xử lý hàng triệu bản ghi có thể chạy hàng giờ và gặp lỗi sau khi phần lớn dữ liệu đã được ghi. Điều kiện để vận hành an toàn là **job có thể tiếp tục từ trạng thái hợp lệ sau lỗi**, không bỏ sót bản ghi, không tạo tác động nghiệp vụ trùng lặp và không phải xóa dữ liệu để chạy lại. Checklist này tập trung vào cách **chứng minh restartability bằng cấu hình, thử nghiệm gây lỗi và bằng chứng đối soát**, đặc biệt khi Spring Batch dùng multi-threaded step, parallel steps, partitioning hoặc worker phân tán.

**Kết quả cần đạt:** trước khi bật lịch chạy production, đội phát triển và vận hành có thể trả lời bằng bằng chứng: job nào được phép restart, dùng tham số và snapshot dữ liệu nào, checkpoint nằm ở đâu, thao tác ghi có an toàn khi chạy lại không, xử lý ra sao khi tiến trình chết đột ngột, và đầu ra sau restart có đúng như một lần chạy thành công hay không.

## 1. Hiểu đúng đối tượng được restart

Trong Spring Batch, **JobInstance** được xác định bởi tên job và tập **identifying JobParameters**. Mỗi lần thực thi cùng instance tạo một **JobExecution** mới; mỗi step có **StepExecution** riêng với trạng thái, bộ đếm và **ExecutionContext** lưu tiến độ. **JobRepository** lưu các metadata đó bền vững để framework có căn cứ khôi phục công việc.

Ví dụ job nhập hóa đơn có tham số định danh:

~~~text
Job name              = importInvoices
identifying parameters:
  businessDate         = 2026-11-25
  inputSnapshotId      = invoices-20261125-v1

JobInstance #117
  JobExecution #501: FAILED
    validateInput: COMPLETED
    importInvoices: FAILED       (đã commit tới checkpoint)
    reconcile: chưa chạy

  JobExecution #508: COMPLETED   (restart cùng JobInstance #117)
    validateInput: được bỏ qua vì đã COMPLETED
    importInvoices: tiếp tục từ checkpoint hợp lệ
    reconcile: chạy và hoàn tất
~~~

Spring Batch thường bỏ qua step đã **COMPLETED** khi restart cùng JobInstance; step chưa hoàn tất được chạy lại theo cấu hình và state đã lưu. Tính chất này **không tự bảo đảm exactly-once cho nghiệp vụ**: một API bên ngoài, email, message hoặc tác dụng phụ đã xảy ra trước khi checkpoint được xác nhận vẫn có thể bị thực hiện lại.

| Tình huống | Ý nghĩa | Cách vận hành |
|---|---|---|
| **Restart** | Chạy JobExecution tiếp theo cho **cùng JobInstance**, dùng metadata để khôi phục | Giữ nguyên identifying parameters, kiểm tra trạng thái và checkpoint |
| **Retry** | Thử lại một thao tác lỗi trong quá trình xử lý, có giới hạn | Dùng cho lỗi tạm thời; vẫn phải xét idempotency |
| **Rerun** | Tạo **JobInstance mới** với identifying parameters mới | Dành cho đợt xử lý mới hoặc chủ động xử lý lại, cần chính sách chống trùng |
| **Replay** | Phát lại dữ liệu / message từ nguồn | Chỉ an toàn khi xác định phạm vi và có cơ chế idempotent hoặc bù trừ |

Không tăng **run.id** hoặc đổi ngày xử lý để “restart” một instance cũ: nếu giá trị đổi là identifying parameter, framework xem đó là **instance mới**, có thể đọc lại từ đầu và bỏ qua checkpoint cũ. Ngược lại, instance đã **COMPLETED** không được khởi chạy lại theo cách restart thông thường. Với instance đang **STARTED**, **UNKNOWN** hoặc **ABANDONED**, phải xác minh trạng thái và xử lý theo quy trình phục hồi phù hợp; không giả định cứ gọi restart là được.

## 2. Những điều kiện phải chứng minh trước khi thử restart

### 2.1. JobRepository và metadata sống qua sự cố

JobRepository phải dùng kho lưu trữ bền vững, được backup, có cấu trúc schema đúng phiên bản Spring Batch, kết nối ổn định và không bị dọn dẹp metadata trong thời gian còn cần restart. Một job có thể ghi dữ liệu thành công nhưng không khôi phục được nếu mất **BATCH_JOB_INSTANCE**, **BATCH_JOB_EXECUTION**, **BATCH_STEP_EXECUTION** hoặc execution context tương ứng.

- Xác nhận ứng dụng restart truy cập **đúng JobRepository** của lần chạy lỗi, kể cả sau khi thay pod, máy chủ hoặc worker.
- Xác nhận quyền đọc/ghi metadata, transaction manager, datasource, connection pool, thời gian chờ và cấu hình isolation đáp ứng tải đồng thời.
- Xác nhận serialization của **ExecutionContext** tương thích giữa bản đang chạy và bản sẽ dùng để restart. Không tự ý đổi lớp, khóa state, định dạng serializer hoặc schema trong lúc còn instance dang dở.
- Có chính sách backup, retention và kiểm tra phục hồi cho metadata; không xóa execution lỗi để làm dashboard “sạch”.

### 2.2. Identifying JobParameters và dữ liệu đầu vào bất biến

Restart phải xử lý **cùng tập dữ liệu logic**, không phải “dữ liệu mới nhất tại thời điểm khởi động lại”.

- Với file: lưu **snapshot ID**, đường dẫn bất biến, checksum, encoding và phiên bản schema; không thay nội dung tại cùng đường dẫn giữa hai execution.
- Với database: chốt watermark, khoảng khóa hoặc phiên bản snapshot bằng identifying parameters / bảng manifest. Tránh query phụ thuộc **NOW()**, trạng thái thay đổi liên tục hay phân trang không có thứ tự ổn định.
- Với API/queue: lưu cursor, offset, idempotency key hoặc manifest theo hợp đồng nguồn; tính lại giới hạn và offset một cách tùy tiện có thể gây mất/trùng.
- Nếu thao tác nghiệp vụ phụ thuộc code, bảng cấu hình hay schema tham chiếu, phải kiểm tra tính tương thích khi restart sau deploy.

Ví dụ chọn **businessDate=2026-11-25** và **inputSnapshotId=invoices-20261125-v1** làm identifying parameters. Đường dẫn vật lý có thể là thuộc tính không định danh nếu bất biến và ánh xạ ổn định, nhưng checksum/snapshot phải được kiểm chứng trước khi mở lại reader.

### 2.3. Reader có checkpoint đáng tin cậy

Reader có trạng thái phải thực hiện đúng vòng đời **ItemStream.open(ExecutionContext)**, **ItemStream.update(ExecutionContext)** và **ItemStream.close()** (nếu sử dụng ItemStream), đồng thời có tên state duy nhất trong step. Checkpoint phải chỉ đến **vị trí đã commit an toàn**; cấu hình **saveState(true)** chỉ hữu ích khi reader thực sự quản lý trạng thái và được gọi theo vòng đời chuẩn.

Với file reader một luồng, framework có thể lưu tiến độ đọc để tiếp tục từ dòng phù hợp sau rollback. Với reader database, cần khóa sắp xếp ổn định, tránh offset trên tập dữ liệu đang biến động, và xác định bản ghi đầu/cuối của khoảng xử lý. Nếu dùng custom reader, phải thử lỗi ở giữa chunk, không chỉ thử chạy thành công từ đầu.

**Lưu ý:** **saveState(false)** loại bỏ cơ chế ghi checkpoint của reader tương ứng; nó không “sửa” vấn đề thread safety. Khi cố ý dùng lại dữ liệu từ đầu, chỉ được làm vậy nếu toàn bộ đường ghi và kiểm soát số lượng chịu được replay và đã có bài test chứng minh.

### 2.4. Writer và tác động phụ phải idempotent hoặc được giao dịch hóa

Chunk-oriented step thường xử lý và commit theo từng chunk. Khi reader, dữ liệu đích và metadata dùng **cùng ranh giới giao dịch phù hợp**, rollback/commit có thể được phối hợp. Tuy nhiên, ghi qua **API HTTP, email, Kafka, storage hoặc datasource khác** không mặc nhiên nằm trong cùng một transaction với JobRepository.

Tình huống nguy hiểm:

~~~text
1. Worker gửi yêu cầu thanh toán sang dịch vụ ngoài -> dịch vụ đã xử lý.
2. Worker chết trước khi ghi nhận checkpoint / xác nhận message.
3. Job restart hoặc broker redeliver -> gửi lại yêu cầu thanh toán.
4. Dịch vụ ngoài ghi nhận hai giao dịch nếu không có idempotency key.
~~~

Các biện pháp cần chọn theo nghiệp vụ: unique constraint cho **business key**, thao tác **UPSERT** có ý nghĩa idempotent, **idempotency key** ổn định giữa các lần thử, bảng **outbox/inbox**, deduplication, hoặc quy trình bù trừ có audit. Không hứa “exactly once” chỉ vì cấu hình Spring Batch bật restart.

## 3. Ví dụ: nhập file hóa đơn có thể restart

Giả sử phải nhập snapshot CSV gồm 100.000 dòng, mỗi dòng có **invoice_id** và **amount**. Bảng đích có ràng buộc **UNIQUE(invoice_id)**; tất cả lần thử của cùng JobInstance sử dụng đúng một snapshot đã xác minh checksum.

~~~sql
-- Ví dụ PostgreSQL: khóa nghiệp vụ ngăn tạo hai hóa đơn cùng ID.
CREATE TABLE invoice_import (
    invoice_id BIGINT PRIMARY KEY,
    amount NUMERIC(18, 2) NOT NULL
);

-- Với cùng snapshot dữ liệu, thao tác ghi lặp không thêm bản ghi trùng.
INSERT INTO invoice_import (invoice_id, amount)
VALUES (:invoice_id, :amount)
ON CONFLICT (invoice_id) DO NOTHING;
~~~

Trong mô hình thực tế cần thêm định danh batch/tenant nếu **invoice_id** chỉ duy nhất trong một phạm vi; đồng thời phát hiện trường hợp cùng key nhưng nội dung khác, không âm thầm bỏ qua xung đột. **ON CONFLICT** ở ví dụ là cú pháp PostgreSQL, không phải SQL chạy trên mọi hệ quản trị.

Một cấu hình Spring Batch 5 theo API builder minh họa reader có checkpoint và writer idempotent:

~~~java
@Configuration
class InvoiceImportConfiguration {

    record InvoiceLine(long invoiceId, BigDecimal amount) {}

    @Bean
    @StepScope
    FlatFileItemReader<InvoiceLine> invoiceReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {
        return new FlatFileItemReaderBuilder<InvoiceLine>()
                .name("invoiceFileReader") // Khóa state ổn định trong ExecutionContext
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .delimited()
                .names("invoice_id", "amount")
                .fieldSetMapper(fields -> new InvoiceLine(
                        fields.readLong("invoice_id"),
                        fields.readBigDecimal("amount")))
                .saveState(true)
                .build();
    }

    @Bean
    JdbcBatchItemWriter<InvoiceLine> invoiceWriter(DataSource dataSource) {
        return new JdbcBatchItemWriterBuilder<InvoiceLine>()
                .dataSource(dataSource)
                .sql("""
                    INSERT INTO invoice_import (invoice_id, amount)
                    VALUES (:invoice_id, :amount)
                    ON CONFLICT (invoice_id) DO NOTHING
                    """)
                .itemSqlParameterSourceProvider(row -> new MapSqlParameterSource()
                        .addValue("invoice_id", row.invoiceId())
                        .addValue("amount", row.amount()))
                .build();
    }

    @Bean
    Step importStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<InvoiceLine> invoiceReader,
            JdbcBatchItemWriter<InvoiceLine> invoiceWriter) {
        return new StepBuilder("importStep", jobRepository)
                .<InvoiceLine, InvoiceLine>chunk(200, transactionManager)
                .reader(invoiceReader)
                .writer(invoiceWriter)
                .build();
    }

    @Bean
    Job importInvoices(JobRepository jobRepository, Step importStep) {
        return new JobBuilder("importInvoices", jobRepository)
                .start(importStep)
                .build();
    }
}
~~~

Các import Java được lược bỏ để tập trung vào cơ chế. Reader trên là **stateful và dùng trong step một luồng**. Đừng gắn TaskExecutor để nhiều thread chia sẻ reader này mà chưa giải quyết thread safety và checkpoint. Giải pháp cho tải lớn thường là partition theo file/range độc lập, mỗi worker nhận reader và state riêng, sau đó đo lại throughput và độ chính xác.

Trước khi start job, cần có một bước kiểm tra **inputFile trỏ đến snapshot đúng**, checksum khớp manifest và dữ liệu không bị thay thế. Ví dụ chỉ cho thấy cách lưu offset và chặn bản ghi trùng; nó chưa bao gồm validate input, xử lý dữ liệu lỗi, quyền truy cập file hay đối soát cuối job.

## 4. Restartability thay đổi thế nào khi scale?

| Mô hình | Rủi ro khi restart | Kiểm tra bắt buộc |
|---|---|---|
| **Một step, một luồng** | Checkpoint sai, nguồn dữ liệu thay đổi, ghi trùng | Gây lỗi giữa chunk; đối chiếu kết quả sau restart với baseline |
| **Multi-threaded step** | Reader/writer/state dùng chung không an toàn; thứ tự hoàn tất khác thứ tự đọc | Xác minh thread safety, state độc lập hoặc cơ chế replay idempotent; không tin vào một offset dùng chung |
| **Parallel steps** | Step đã COMPLETED bị chạy lại do cấu hình hoặc tác động chéo giữa các step | Xác minh phụ thuộc luồng, key và phạm vi ghi; kiểm tra step được bỏ qua đúng khi restart |
| **Local partitioning** | Trùng/gãy khoảng chia, partition name đổi giữa hai execution | Giữ ổn định partition key, giới hạn và tên step; phục hồi riêng partition lỗi |
| **Remote partitioning** | Worker chết, kết quả đến trễ, job quản lý hiểu sai trạng thái | Metadata chung nhất quán; worker idempotent; chỉ điều phối restart khi biết worker cũ không còn ghi |
| **Remote chunking / messaging** | Message xử lý xong nhưng ACK thất bại, message gửi lại | Dedup theo business key / message ID; thử redelivery, timeout, duplicate reply và thứ tự bất định |

**Partitioning:** mỗi partition cần ranh giới rõ (ví dụ **id từ 1 đến 10.000**, **10.001 đến 20.000**), **ExecutionContext** riêng và tên partition ổn định để framework nhận diện step execution đã hoàn thành. Nếu dữ liệu phân hoạch lại khi restart, chỉ thay **gridSize** hoặc thuật toán chia range cũng có thể làm metadata không tương ứng, gây vùng dữ liệu chồng lấn hoặc bị bỏ sót. Việc có thể thay đổi số worker **đang xử lý các partition cố định** khác với việc tái chia partition.

**Remote chunking:** cần nắm rõ đường đi của request, response, ACK và transaction của consumer. Hãy giả định message có thể bị phát lại hoặc phản hồi về muộn, rồi chứng minh bằng kiểm thử rằng output cuối cùng vẫn chính xác.

**Multi-threaded step:** một singleton reader có trạng thái không tự an toàn khi nhiều thread cùng gọi. Ngay cả khi có đồng bộ, thứ tự các chunk commit khác nhau vẫn có thể khiến checkpoint một chiều không biểu diễn được tất cả phần việc đã hoàn tất. Phương án khả thi hơn là chia nguồn theo partition có checkpoint độc lập hoặc thiết kế replay và dedup có chủ đích; phải đo throughput sau khi tăng độ an toàn.

## 5. Ma trận kiểm thử lỗi bắt buộc

Chuẩn bị **snapshot dữ liệu cố định** có N bản ghi hợp lệ, K bản ghi bị từ chối theo quy tắc đã biết và checksum của đầu ra kỳ vọng. Chạy baseline đến COMPLETED, chụp lại số lượng, tổng tiền, danh sách khóa nghiệp vụ và số step/partition. Mỗi kịch bản dưới đây nên chạy với **JobInstance kiểm thử riêng**, nhưng mọi lần restart bên trong kịch bản phải giữ nguyên identifying parameters.

| Kịch bản gây lỗi | Kỳ vọng cần quan sát | Tiêu chí PASS |
|---|---|---|
| Throw exception **trước commit chunk** | Chunk lỗi bị rollback; restart đọc lại phần chưa commit | Không thiếu/nhân đôi dữ liệu; state đi tiếp từ checkpoint commit trước |
| Lỗi **sau vài chunk đã commit** | Các chunk cũ còn nguyên; chỉ phần chưa hoàn tất được làm tiếp | Kết quả cuối khớp baseline, không có side effect trùng |
| **Stop có kiểm soát**, sau đó restart | Execution chuyển sang STOPPED và lưu state hợp lệ | Restart được, các step hoàn thành được bỏ qua như thiết kế |
| **SIGKILL / OOM / mất máy** | Metadata có thể vẫn là STARTED, worker/broker có thể còn công việc | Quy trình nhận diện execution mồ côi, xác minh worker đã dừng, khôi phục trạng thái theo hướng dẫn vận hành và restart thành công |
| **Timeout sau khi dịch vụ ngoài xử lý thành công** | Request có thể gửi lại | Idempotency key hoặc inbox/outbox ngăn tác dụng phụ lần hai |
| Worker của **một partition** lỗi | Các partition thành công được giữ, phần lỗi được phục hồi | Mỗi khóa nguồn đúng một kết quả logic; không thay ranh giới partition |
| **Redelivery** cùng message | Consumer có thể xử lý hai lần | Bản ghi/trạng thái nghiệp vụ chỉ có một hiệu lực |
| Restart sau **deploy thay đổi code/schema** | Reader, serializer hoặc query có thể không tương thích | Có chiến lược tương thích, drain hoặc migration; không làm mất state |
| Gọi lại instance đã **COMPLETED** | Framework chặn chạy lại cùng JobInstance | Không tự tạo kết quả trùng bằng cách thay run.id |
| **Hai operator** cùng yêu cầu restart | Có cạnh tranh vận hành | Chỉ một execution hợp lệ tiến hành; khóa/phân quyền/giám sát ngăn chạy chồng |

Khi thử crash thật, **không kỳ vọng Spring Batch tự chuyển STARTED thành FAILED** sau khi JVM bị kill: status lưu ở repository có thể chưa cập nhật. Cần quy trình recovery đã được kiểm chứng cho đúng phiên bản đang triển khai. Không tự chỉnh các bảng **BATCH_*** để vượt chặn restart nếu chưa xác minh trạng thái worker và chưa có quy trình được phê duyệt, backup, audit.

### Cách thực hiện một vòng thử minh họa

1. Tạo snapshot 10.000 hóa đơn, checksum nguồn, manifest business keys; lưu tên job và identifying parameters. Khởi chạy job với chunk size 200.
2. Chờ tối thiểu vài chunk commit, chủ động phát sinh lỗi tại một điểm xác định; lưu **JobExecution ID**, **StepExecution ID**, commit count, read/write count, log và trace ID.
3. Xác nhận execution thất bại hoặc dừng đúng kỳ vọng; nếu giả lập kill, thực hiện quy trình reconciliation của execution mồ côi trước khi restart.
4. Khởi chạy **restart cùng JobInstance**, không đổi identifying parameters hay snapshot; ghi lại JobExecution ID mới và các step được chạy/bỏ qua.
5. Đối soát đầu ra với baseline: số lượng unique keys, tổng amount, tập khóa, checksum nếu có, số lần side effect bên ngoài và trạng thái các partition.
6. Lặp lại tại ranh giới trước/sau commit, sau API side effect và tại worker riêng lẻ. Thử lại khi tăng worker count **mà không đổi partition manifest**.

## 6. Bằng chứng và truy vấn đối soát

Không đánh giá restart chỉ bằng **ExitStatus=COMPLETED**. Một execution hoàn tất vẫn có thể để lại bản ghi trùng, thiếu dữ liệu hoặc gọi API ngoài nhiều lần.

~~~sql
-- Ví dụ PostgreSQL; chỉ dùng trên dataset thử nghiệm đã cô lập.
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT invoice_id) AS unique_invoices,
    COALESCE(SUM(amount), 0) AS total_amount
FROM invoice_import;

-- Theo dõi lịch sử tất cả execution của cùng một JobInstance.
SELECT
    j.JOB_INSTANCE_ID,
    e.JOB_EXECUTION_ID,
    e.STATUS AS job_status,
    s.STEP_NAME,
    s.STATUS AS step_status,
    s.READ_COUNT,
    s.WRITE_COUNT,
    s.COMMIT_COUNT,
    s.ROLLBACK_COUNT
FROM BATCH_JOB_INSTANCE j
JOIN BATCH_JOB_EXECUTION e ON e.JOB_INSTANCE_ID = j.JOB_INSTANCE_ID
JOIN BATCH_STEP_EXECUTION s ON s.JOB_EXECUTION_ID = e.JOB_EXECUTION_ID
WHERE j.JOB_INSTANCE_ID = :job_instance_id
ORDER BY e.JOB_EXECUTION_ID, s.STEP_EXECUTION_ID;
~~~

Tùy database và phiên bản schema, cần điều chỉnh cú pháp truy vấn, kiểu bind parameter và tên schema. Các bộ đếm trong **một StepExecution** mô tả execution đó; khi restart cần xem **cả lịch sử execution** và đối soát dữ liệu nghiệp vụ, không suy số record cuối cùng chỉ từ một read_count hoặc phép cộng write_count. Nếu writer sử dụng **ON CONFLICT DO NOTHING**, số item Spring Batch chuyển vào writer cũng không nhất thiết bằng số row SQL mới được thêm.

Hồ sơ kiểm thử cần lưu tối thiểu: bản Spring Batch/Boot và commit ứng dụng, snapshot/hash đầu vào, identifying parameters, cấu hình chunk/worker/partition, tập kịch bản lỗi, JobExecution ID trước/sau restart, thông tin status/checkpoint, số liệu đối soát và chữ ký xác nhận của chủ sở hữu nghiệp vụ/vận hành.

### Chỉ số giám sát khi restart ở production

- **Lag và tiến độ**: thời gian từ checkpoint gần nhất, số item/chunk đã commit, số partition đang chạy/failed, độ lệch so với baseline throughput.
- **Độ ổn định**: số lần restart trên một JobInstance, lỗi rollback/retry/skip, JobRepository deadlock hoặc timeout, worker mất heartbeat.
- **Tính toàn vẹn**: duplicate business keys, missing keys, chênh lệch aggregate, số message redelivery, số lần gọi API trùng idempotency key.
- **Giới hạn vận hành**: thời gian tối đa execution ở STARTED khi không còn heartbeat, số lần recovery cho phép, điều kiện cảnh báo hoặc chuyển sang xử lý thủ công.

## 7. Runbook khi job production bị gián đoạn

~~~mermaid
flowchart TD
    A[Phát hiện job gián đoạn] --> B[Thu thập JobInstance và JobExecution ID]
    B --> C{Có worker hoặc message in-flight?}
    C -->|Có| D[Dừng hoặc cô lập công việc cũ, xác minh side effect]
    C -->|Không| E[Kiểm tra JobRepository và checkpoint]
    D --> E
    E --> F{Input snapshot và code còn tương thích?}
    F -->|Không| G[Escalate: khôi phục snapshot hoặc lập kế hoạch migration]
    F -->|Có| H{Trạng thái có cho phép restart?}
    H -->|Không| I[Recovery metadata theo quy trình được phê duyệt]
    H -->|Có| J[Restart cùng JobInstance]
    I --> J
    J --> K[Giám sát step, partition, retry và side effect]
    K --> L[Đối soát kết quả nghiệp vụ và lưu bằng chứng]
~~~

Trước thao tác restart, operator cần kiểm tra lần lượt: **(1)** phạm vi dữ liệu và identifying parameters, **(2)** execution/step đang ở trạng thái nào, **(3)** worker cũ đã ngừng ghi hay chưa, **(4)** metadata và checkpoint còn nguyên, **(5)** code/schema/input còn tương thích, **(6)** writer và API ngoài có bảo vệ khi retry hay không.

Khi metadata cho phép restart, thực hiện qua **JobOperator** hoặc hệ thống điều phối đã tích hợp Spring Batch; chẳng hạn ở các phiên bản hỗ trợ API tương ứng, **JobOperator.restart(failedExecutionId)** tạo execution mới cho instance cũ. Không gọi một job mới với tham số định danh tùy ý chỉ để vượt lỗi. Nếu xuất hiện **UNKNOWN**, **ABANDONED**, execution mồ côi hoặc worker chưa xác định trạng thái, thực hiện recovery được phê duyệt trước.

Sau restart, giám sát cho tới trạng thái kết thúc, sau đó đối soát dữ liệu và tác động phụ độc lập với status của framework. Nếu sai lệch, đưa instance vào quy trình xử lý sự cố, không liên tục restart để thử may rủi.

## 8. Checklist ký duyệt production

Chỉ đánh dấu **Đạt** khi có bằng chứng, test case hoặc tài liệu vận hành gắn với từng mục.

| Hạng mục kiểm tra | Bằng chứng tối thiểu | Đạt khi |
|---|---|---|
| **[ ] Instance identity** | Danh sách identifying JobParameters và quy tắc đặt batch/snapshot ID | Restart giữ nguyên instance; rerun có quy trình riêng |
| **[ ] Input reproducibility** | Manifest, checksum, watermark và quy tắc đóng băng đầu vào | Hai execution đọc cùng dữ liệu logic |
| **[ ] Metadata durability** | Test mất pod/host, backup/restore JobRepository, retention | Metadata và ExecutionContext vẫn truy cập được |
| **[ ] Checkpoint correctness** | Test lỗi trước và sau commit, log và state trước/sau restart | Không bỏ sót hay xử lý sai vùng đã commit |
| **[ ] Step lifecycle** | Lịch sử JobExecution/StepExecution của test restart | Step COMPLETED được bỏ qua; step lỗi tiếp tục đúng |
| **[ ] Reader safety** | Review ItemStream, state key, sort/range và thread safety | Không chia sẻ state sai giữa các thread |
| **[ ] Writer idempotency** | Unique constraints, upsert/dedup hoặc outbox, test duplicate request | Chạy lại không tạo hiệu lực nghiệp vụ thứ hai |
| **[ ] Partition stability** | Manifest partition key/range và test worker failure | Không đổi partition identity khi restart |
| **[ ] Distributed recovery** | Test worker crash, message redelivery, timeout, reply đến muộn | Không có worker cũ và mới ghi chồng ngoài kiểm soát |
| **[ ] Deploy compatibility** | Test restart qua bản phát hành hoặc quy trình drain/migrate | Serializer, schema và code tương thích |
| **[ ] Stale execution recovery** | Runbook xử lý STARTED mồ côi, người chịu trách nhiệm, audit | Có thể phục hồi an toàn khi crash đột ngột |
| **[ ] Data reconciliation** | SQL/checksum/tổng tiền/unique business keys so với baseline | Không thiếu/trùng/sai giá trị và side effect |
| **[ ] Observability** | Dashboard, alert, trace ID, Execution ID và cảnh báo SLA | Nhận biết được stuck execution và sai lệch sớm |
| **[ ] Operator drill** | Biên bản diễn tập restart, thời gian phục hồi và kết quả | Người trực triển khai đúng runbook và đạt RTO/RPO đã thống nhất |

**Điều kiện chặn phát hành:** chưa có test crash và restart thành công; dữ liệu nguồn có thể thay đổi mà không có snapshot/watermark; writer gây side effect lặp không được kiểm soát; reader không an toàn khi tăng concurrency; không có cách xử lý execution STARTED mồ côi; hoặc thiếu phép đối soát nghiệp vụ sau restart.

## 9. Những ngộ nhận hay gặp

**“Job có JobRepository nên chắc chắn restart được.”** Repository lưu metadata, nhưng không bảo đảm input bất biến, reader khôi phục đúng, hoặc external side effect không lặp. Cần test đầu cuối.

**“Có retry rồi thì không cần restart.”** Retry giải quyết lỗi trong execution đang chạy. Crash tiến trình, mất host hoặc stop có kiểm soát là tình huống phục hồi JobInstance sau đó.

**“Chỉ cần tăng run.id và chạy lại.”** Nếu run.id là identifying parameter, đó là JobInstance mới, checkpoint cũ không được sử dụng. Hậu quả có thể là replay toàn bộ đầu vào.

**“Mọi step sẽ tự chạy lại từ đầu.”** Với restart thông thường, step đã COMPLETED được bỏ qua. Cấu hình **allowStartIfComplete(true)** thay đổi hành vi và cần mục đích rõ ràng; **startLimit** có thể chặn số lần chạy step. Ở cấp job, cấu hình không cho restart như **preventRestart()** cũng phải được xem xét.

**“Đặt saveState(false) là xử lý được parallelism.”** Cách này không cho reader lưu checkpoint; chỉ chấp nhận khi replay được thiết kế, có khóa nghiệp vụ và đối soát toàn bộ.

**“Step COMPLETED nghĩa là nghiệp vụ exactly-once.”** Framework có thể đã hoàn thành xử lý chunk nhưng ngoại tác qua API hoặc message có ngữ nghĩa at-least-once. Hãy kiểm tra bằng business key và idempotency key.

## 10. Bài thực hành tự kiểm tra

Chọn một job thực tế đang chạy lâu hoặc có partition. Lập bảng ba cột **failure point – checkpoint kỳ vọng – bằng chứng không trùng/mất dữ liệu** cho ít nhất bốn thời điểm: trước commit, sau commit, worker mất kết nối và trước ACK message. Dùng snapshot cố định để chạy thử, lưu lại hai JobExecution cùng JobInstance và đối chiếu tập business keys với baseline.

Tự trả lời các câu hỏi sau trước khi đánh dấu hoàn thành checklist:

1. Nếu worker bị kill ngay sau khi API ngoài nhận request thành công, thao tác nào ngăn gọi lặp có tác dụng nghiệp vụ?
2. Nếu deployment thay reader hoặc serializer trong khi còn execution lỗi, làm thế nào biết ExecutionContext cũ có đọc được?
3. Nếu tăng số worker từ 4 lên 8, partition key/range nào phải giữ cố định để restart không mất hoặc trùng dữ liệu?
4. Nếu JobRepository ghi **STARTED** nhưng không còn process, operator xác minh điều gì trước khi recovery?
5. Số liệu nào chứng minh đầu ra đúng, kể cả khi **read_count** và **write_count** giữa các lần thực thi khác nhau?

**Tiêu chuẩn hoàn thành bài học:** người học trình bày được khác biệt restart/retry/rerun, giải thích cơ chế checkpoint của JobRepository và ItemStream, thực hiện được test crash có kiểm soát, restart đúng instance và cung cấp bằng chứng nghiệp vụ không thiếu/trùng dữ liệu trong kiến trúc scale đã chọn. Chỉ khi đáp ứng các điều đó, mục **“Đã kiểm tra restartability”** trong checklist production mới thực sự được xác nhận.
