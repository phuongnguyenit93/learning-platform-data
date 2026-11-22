# Chèn hàng loạt, công cụ nạp dữ liệu và xử lý theo lô

Trong chương **Đường ghi dữ liệu** của module **DATABASE_PERFORMANCE**, chèn hàng loạt (*bulk insert/bulk load*) và xử lý theo lô giúp đưa nhiều bản ghi vào cơ sở dữ liệu với ít lần trao đổi, ít chi phí chuẩn bị câu lệnh và khả năng kiểm soát transaction tốt hơn. Các kỹ thuật này thường dùng khi nhập dữ liệu từ file, đồng bộ hệ thống, nạp dữ liệu lịch sử, tiếp nhận sự kiện hoặc tạo dữ liệu phân tích. Tối ưu đường ghi cần dựa trên đo đạc tải, execution plan, thống kê I/O và cơ chế lưu trữ; tăng tốc nạp dữ liệu không chỉ là tăng số dòng trong một câu `INSERT`.

Một quy trình nạp tốt phải cân bằng throughput, độ trễ, tính đúng đắn, khả năng phục hồi và tác động tới workload đang chạy. Batch quá nhỏ tạo nhiều round trip và commit; batch quá lớn giữ lock lâu, tăng log, bộ nhớ và thời gian rollback. Tắt constraint hoặc index có thể tăng tốc một số tình huống nhưng cũng làm mất bảo vệ dữ liệu hoặc gây chi phí rebuild lớn. Vì vậy, cần chọn công cụ theo hệ quản trị, thiết kế batch có thể chạy lại an toàn và đo cả giai đoạn nạp lẫn giai đoạn kiểm tra/publish.

## 1. Vì sao cần chèn hàng loạt?

Giả sử ứng dụng nhập một triệu dòng từ file CSV. Nếu gửi một câu `INSERT` cho từng dòng, ứng dụng phải lặp lại nhiều lần việc gửi request, parse SQL, bind tham số, thực thi và nhận kết quả. Khi mỗi request có độ trễ mạng, chi phí round trip có thể lớn hơn thời gian ghi thực tế.

Chèn theo lô cho phép gom nhiều dòng vào một lần gửi hoặc một thao tác chuyên dụng. Công cụ bulk load thường đọc dữ liệu tuần tự, chuyển đổi định dạng hiệu quả và đưa dữ liệu vào storage engine với ít overhead hơn so với từng câu lệnh đơn lẻ.

### 1.1. Các lợi ích thường gặp

- Giảm số lần round trip giữa ứng dụng và database.
- Giảm chi phí parse/prepare lặp lại khi dùng prepared statement hoặc multi-row insert.
- Tăng throughput nhờ đọc file tuần tự và đường nạp chuyên dụng.
- Có thể kiểm soát transaction theo batch để giới hạn thời gian giữ lock và lượng công việc rollback.
- Tạo cơ hội xác thực, loại trùng và chuẩn hóa dữ liệu trong staging trước khi công bố.
- Cho phép checkpoint và tiếp tục từ batch đã hoàn tất thay vì nạp lại toàn bộ file.

### 1.2. Những chi phí vẫn còn

Bulk load không loại bỏ các công việc cốt lõi của database. Engine vẫn có thể phải ghi transaction log/WAL/redo, cập nhật index, kiểm tra constraint, chạy trigger, cấp phát page, duy trì replication và bảo đảm durability. Nếu nạp đồng thời với workload OLTP, bulk load còn cạnh tranh CPU, memory, I/O, log bandwidth và khóa.

Một công cụ có thể đạt tốc độ rất cao khi nạp vào bảng trống, nhưng chậm hơn đáng kể khi bảng có nhiều index, trigger, foreign key hoặc replication đang hoạt động. Hãy benchmark với cấu trúc và cấu hình gần production.

## 2. Chọn phương pháp ghi phù hợp

Không phải mọi trường hợp đều cần tiện ích bulk load. Hãy chọn phương pháp dựa trên kích thước batch, tần suất, nguồn dữ liệu, yêu cầu atomicity và mức độ phức tạp của thao tác ghi.

| Phương pháp | Đặc điểm | Trường hợp phù hợp |
|---|---|---|
| INSERT từng dòng | Một câu lệnh cho mỗi dòng | Khối lượng nhỏ, logic nghiệp vụ riêng cho từng bản ghi |
| Prepared statement theo batch | Tái sử dụng câu lệnh, bind nhiều bộ tham số | Ứng dụng ghi thường xuyên, batch vừa phải |
| Multi-row INSERT | Một câu lệnh chứa nhiều bộ giá trị | Batch vừa, ít round trip, cú pháp được engine hỗ trợ |
| Bulk copy/load chuyên dụng | Đọc luồng hoặc file theo giao thức tối ưu | Nạp file lớn, ETL, import lịch sử |
| Staging rồi merge/upsert | Nạp thô trước, xác thực và hợp nhất sau | Dữ liệu ngoài hệ thống, cần kiểm tra và xử lý trùng |
| Partition exchange/switch | Chuẩn bị partition riêng rồi đưa vào bảng đích | Nạp dữ liệu theo kỳ, cần publish nhanh và cấu trúc phù hợp |

### 2.1. Prepared statement theo batch

Prepared statement giảm việc parse/compile lặp lại và cho phép gửi nhiều bộ tham số theo batch. Cách này thường dễ tích hợp với transaction và validation trong ứng dụng.

Ví dụ Java JDBC:

```java
String sql = "INSERT INTO measurements (device_id, measured_at, value) "
           + "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    connection.setAutoCommit(false);

    int pending = 0;
    for (Measurement row : rows) {
        ps.setLong(1, row.deviceId());
        ps.setTimestamp(2, Timestamp.from(row.measuredAt()));
        ps.setBigDecimal(3, row.value());
        ps.addBatch();
        pending++;

        if (pending == 1000) {
            ps.executeBatch();
            connection.commit();
            pending = 0;
        }
    }

    if (pending > 0) {
        ps.executeBatch();
        connection.commit();
    }
}
```

Đây là mẫu minh họa; xử lý ngoại lệ phải rollback transaction đang mở và khôi phục trạng thái connection trước khi trả connection về pool. Driver có thể hỗ trợ hoặc mô phỏng batch bằng nhiều câu lệnh; kiểm tra tài liệu driver và cấu hình rewrite batch. Kích thước 1.000 chỉ là điểm bắt đầu để benchmark, không phải giá trị tối ưu cho mọi workload.

### 2.2. Multi-row INSERT

Một câu lệnh có nhiều bộ giá trị giúp giảm round trip:

```sql
INSERT INTO measurements (device_id, measured_at, value)
VALUES
    (101, TIMESTAMP '2026-11-19 08:00:00', 12.5),
    (102, TIMESTAMP '2026-11-19 08:00:01', 13.1),
    (103, TIMESTAMP '2026-11-19 08:00:02', 11.9);
```

Số dòng tối đa trong một câu lệnh phụ thuộc giới hạn packet/request, số tham số, kích thước SQL, memory và giới hạn của driver/database. Câu lệnh quá lớn có thể vượt giới hạn packet hoặc tạo chi phí parse và memory cao. Hãy chia thành các nhóm có kích thước đo được.

Không nối chuỗi đầu vào trực tiếp vào SQL để tạo multi-row statement. Dùng bind parameter hoặc API bulk của driver để tránh SQL injection, lỗi escaping và giới hạn độ dài.

## 3. Chuẩn bị dữ liệu trước khi nạp

Chất lượng dữ liệu đầu vào quyết định số lỗi trong lúc ghi và chi phí sửa sau đó. Trước khi nạp, xác định schema đích, encoding, định dạng ngày giờ, quy tắc `NULL`, số thập phân, khóa định danh và cách xử lý bản ghi trùng.

### 3.1. Kiểm tra cấu trúc nguồn

- Xác nhận số cột, thứ tự cột và tên header.
- Kiểm tra delimiter, quote, escape và ký tự xuống dòng trong trường văn bản.
- Xác định encoding, ví dụ UTF-8, và cách xử lý ký tự không hợp lệ.
- Chuẩn hóa ngày giờ theo múi giờ đã thống nhất.
- Xác định dấu thập phân, dấu phân tách hàng nghìn và quy tắc làm tròn.
- Phân biệt trường rỗng, chuỗi rỗng và giá trị `NULL`.
- Kiểm tra độ dài chuỗi, precision/scale và miền giá trị số.
- Xác định khóa tự nhiên hoặc khóa nguồn dùng để nhận diện bản ghi.

CSV không phải lúc nào cũng chỉ là các giá trị ngăn bằng dấu phẩy. Trường văn bản có thể chứa dấu phẩy, dấu quote hoặc newline; parser phải tuân thủ quy tắc quote/escape. Không dùng thao tác tách chuỗi đơn giản theo dấu phẩy cho file CSV tổng quát.

### 3.2. Xác thực ngoài database và trong staging

Có thể kiểm tra sơ bộ trong ứng dụng để loại file sai định dạng sớm. Tuy nhiên, database vẫn cần constraint và validation cuối cùng vì dữ liệu có thể bị thay đổi giữa bước kiểm tra và ghi, hoặc có nguồn ghi khác cùng cập nhật bảng.

Staging table hữu ích khi dữ liệu đến từ hệ thống bên ngoài. Bảng staging giữ dữ liệu nhập cùng metadata batch, số dòng nguồn và trạng thái kiểm tra. Sau khi xác thực, dữ liệu mới được chuyển vào bảng nghiệp vụ.

Ví dụ cấu trúc:

```sql
CREATE TABLE import_stage (
    batch_id       uuid NOT NULL,
    source_row_no  bigint NOT NULL,
    external_id    text,
    measured_at    timestamptz,
    reading_value  numeric(18, 4),
    validation_error text,
    loaded_at      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (batch_id, source_row_no)
);
```

Khóa `(batch_id, source_row_no)` giúp nhận diện từng dòng trong một lần nhập và tránh nạp trùng cùng dòng nguồn khi batch được chạy lại. Có thể bổ sung `source_file_id`, checksum, schema version hoặc `source_system` theo nhu cầu kiểm toán.

## 4. Nạp vào staging rồi hợp nhất

Với file lớn hoặc dữ liệu cần kiểm tra, thường nên tách quy trình thành hai giai đoạn:

1. Nạp dữ liệu thô vào staging bằng công cụ bulk load.
2. Kiểm tra kiểu dữ liệu, khóa, quan hệ, trùng lặp và quy tắc nghiệp vụ.
3. Ghi nhận dòng hợp lệ và dòng bị từ chối.
4. Hợp nhất dữ liệu hợp lệ vào bảng đích bằng `INSERT`, `MERGE` hoặc upsert phù hợp.
5. Đối soát số dòng và publish batch.

### 4.1. Ví dụ PostgreSQL: COPY và upsert

PostgreSQL hỗ trợ `COPY` để nạp dữ liệu theo luồng hiệu quả. Ví dụ:

```sql
COPY import_stage (
    batch_id,
    source_row_no,
    external_id,
    measured_at,
    reading_value
)
FROM STDIN
WITH (FORMAT csv, HEADER true, ENCODING 'UTF8');
```

`COPY FROM STDIN` nhận dữ liệu từ client qua kết nối; `COPY FROM '/path/file.csv'` đọc file trên máy chủ database và yêu cầu quyền truy cập file phù hợp. Với ứng dụng, driver PostgreSQL thường cung cấp API Copy để truyền luồng trực tiếp mà không phải tạo câu `INSERT` cho từng dòng.

Sau khi xác thực, có thể upsert vào bảng đích:

```sql
INSERT INTO measurements (
    external_id, measured_at, reading_value, source_batch_id
)
SELECT external_id,
       measured_at,
       reading_value,
       batch_id
FROM import_stage
WHERE batch_id = :batch_id
  AND validation_error IS NULL
ON CONFLICT (external_id, measured_at)
DO UPDATE SET
    reading_value = EXCLUDED.reading_value,
    source_batch_id = EXCLUDED.source_batch_id;
```

Ví dụ dùng khóa xung đột `(external_id, measured_at)` đã có unique constraint/index ở bảng đích. Cần xác định chính sách khi hai dòng trong cùng batch cùng xung đột một khóa; PostgreSQL không cho một câu `INSERT ... ON CONFLICT DO UPDATE` cập nhật cùng một dòng đích nhiều lần trong một statement. Hãy loại hoặc gộp duplicate trong staging trước khi upsert.

### 4.2. Ví dụ MySQL: LOAD DATA INFILE

MySQL có `LOAD DATA` để nạp file phân tách vào bảng:

```sql
LOAD DATA LOCAL INFILE '/client/path/measurements.csv'
INTO TABLE import_stage
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
ESCAPED BY '\\'
LINES TERMINATED BY '\n'
IGNORE 1 LINES
(@batch_id, @row_no, @external_id, @measured_at, @value)
SET batch_id = @batch_id,
    source_row_no = @row_no,
    external_id = NULLIF(@external_id, ''),
    measured_at = STR_TO_DATE(@measured_at, '%Y-%m-%d %H:%i:%s'),
    reading_value = NULLIF(@value, '');
```

Đây là ví dụ minh họa cho file UTF-8 có header và định dạng ngày giờ đã biết. `LOCAL` đọc file từ máy client; không có `LOCAL` thì file được đọc trên máy chủ và bị giới hạn bởi quyền/biến cấu hình như `secure_file_priv`. Hành vi `LOCAL` có thể bị tắt ở server hoặc client; chỉ bật khi ứng dụng và kết nối được cấu hình an toàn.

Các tùy chọn `FIELDS`, `LINES`, quote và escape phải khớp định dạng file thực tế. Nếu file dùng CRLF, có thể cần `LINES TERMINATED BY '\r\n'`. Không dùng `STR_TO_DATE` với format không khớp dữ liệu vì có thể tạo `NULL` hoặc cảnh báo. Kiểm tra warning, số dòng nạp và các giá trị bị chuyển đổi.

### 4.3. Ví dụ SQL Server: BULK INSERT

SQL Server hỗ trợ `BULK INSERT` để đọc file từ đường dẫn mà SQL Server service có quyền truy cập:

```sql
BULK INSERT dbo.ImportStage
FROM 'D:\\Import\\measurements.csv'
WITH (
    FORMAT = 'CSV',
    FIRSTROW = 2,
    FIELDQUOTE = '"',
    CODEPAGE = '65001',
    TABLOCK,
    BATCHSIZE = 50000,
    ERRORFILE = 'D:\\Import\\measurements_errors'
);
```

Ví dụ yêu cầu phiên bản SQL Server hỗ trợ các tùy chọn CSV tương ứng. Đường dẫn được giải quyết trên máy chủ database, không phải máy chạy ứng dụng; tài khoản dịch vụ SQL Server phải có quyền đọc file và ghi error file. `TABLOCK` có thể giúp bulk load trong một số điều kiện, nhưng cũng ảnh hưởng concurrency. `BATCHSIZE` là số dòng mỗi batch; cần đo lock, log và thời gian commit.

Có thể dùng `bcp` hoặc `SqlBulkCopy` từ ứng dụng .NET để truyền dữ liệu qua client. `SqlBulkCopy` hỗ trợ batch size, transaction và mapping cột; lựa chọn `TableLock` hoặc `KeepIdentity` cần phù hợp với yêu cầu dữ liệu.

### 4.4. Oracle SQL*Loader

Oracle SQL*Loader là tiện ích nạp dữ liệu từ file phẳng. Một control file đơn giản có thể khai báo:

```text
LOAD DATA
INFILE 'measurements.csv'
INTO TABLE IMPORT_STAGE
APPEND
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
TRAILING NULLCOLS
(
  BATCH_ID,
  SOURCE_ROW_NO INTEGER EXTERNAL,
  EXTERNAL_ID,
  MEASURED_AT TIMESTAMP "YYYY-MM-DD HH24:MI:SS",
  READING_VALUE DECIMAL EXTERNAL
)
```

Control file trên minh họa mapping; định dạng timestamp, decimal, delimiter và xử lý header phải khớp file thực tế. SQL*Loader có conventional path và direct path. Direct path có thể giảm một số overhead và nạp nhanh hơn trong điều kiện phù hợp, nhưng có các giới hạn về trigger, constraint, index, concurrency và cấu trúc bảng. Hãy kiểm tra tài liệu Oracle theo phiên bản, xem log/bad/discard file và đối soát số dòng.

## 5. Chọn kích thước batch và transaction

Batch size là một trong những tham số ảnh hưởng mạnh tới throughput và độ ổn định. Không có con số chung cho mọi hệ thống.

### 5.1. Batch quá nhỏ

- Nhiều round trip và lần parse/execute.
- Commit quá thường xuyên làm tăng chi phí flush log và đồng bộ storage.
- Overhead điều phối ứng dụng có thể chiếm phần lớn thời gian.
- Throughput thấp dù database còn tài nguyên.

### 5.2. Batch quá lớn

- Transaction giữ lock và snapshot lâu.
- Log/WAL/undo có thể tăng mạnh và cần nhiều dung lượng.
- Rollback sau lỗi có thể kéo dài và tạo tải lớn.
- Buffer, memory và packet/request có thể vượt giới hạn.
- Một batch lỗi có thể khiến nhiều dòng phải nạp lại.
- Replication hoặc downstream consumer có thể bị dồn backlog.

### 5.3. Tìm batch size bằng benchmark

Thử nhiều kích thước tăng dần, chẳng hạn 500, 2.000, 10.000 và 50.000 dòng, tùy kích thước bản ghi và engine. Với mỗi mức, ghi:

- Rows/second và bytes/second.
- Thời gian parse, truyền dữ liệu, execute và commit.
- CPU, memory, I/O latency và log bytes.
- Lock wait, deadlock, timeout và replication lag.
- Thời gian rollback hoặc retry khi cố ý tạo lỗi kiểm thử.

Chọn vùng mà throughput tăng thêm không đáng kể so với chi phí lock, log và độ trễ. Đừng chỉ chọn batch có tốc độ cao nhất nếu nó làm p95 của workload OLTP tăng vượt SLO.

### 5.4. Commit theo batch

Commit mỗi batch tạo ranh giới phục hồi rõ ràng. Nếu batch thứ 8 lỗi, các batch 1-7 đã commit và có thể được giữ lại; pipeline chỉ cần xử lý lại batch chưa hoàn tất. Nhưng nếu yêu cầu toàn bộ file phải xuất hiện cùng lúc, commit từng batch làm người đọc có thể thấy dữ liệu một phần. Khi đó, nạp vào staging rồi publish bằng một bước nguyên tử hoặc cờ trạng thái.

Không dùng một transaction duy nhất cho hàng tỷ dòng chỉ vì muốn “all-or-nothing” nếu thời gian, log và rollback không thể kiểm soát. Có thể dùng staging, batch id và trạng thái publish để đạt semantics nghiệp vụ mà không giữ một transaction khổng lồ.

## 6. Transaction log, WAL và chế độ bulk load

Database cần log để phục hồi sau sự cố và bảo đảm durability. Bulk load vẫn có chi phí log, nhưng một số engine hỗ trợ đường nạp hoặc chế độ logging tối thiểu trong những điều kiện cụ thể.

### 6.1. PostgreSQL

`COPY` vẫn ghi WAL khi bảng thuộc cơ chế WAL thông thường. Nạp vào bảng không được ghi log đầy đủ như unlogged table có thể giảm WAL trong một số tình huống, nhưng unlogged table không được bảo vệ như bảng logged khi crash và không được replicate theo cách thông thường. Chỉ dùng khi dữ liệu có thể tái tạo và chấp nhận semantics durability/replication tương ứng.

Các lựa chọn như tăng `maintenance_work_mem` cho build index, điều chỉnh checkpoint hoặc tạm thay đổi cấu hình WAL cần được đánh giá trên môi trường kiểm soát. Không tắt `fsync` hoặc durability setting trên hệ thống cần bảo vệ dữ liệu chỉ để tăng tốc nạp.

### 6.2. MySQL/InnoDB

`LOAD DATA` có thể nhanh hơn nhiều câu `INSERT`, nhưng InnoDB vẫn duy trì redo/undo, index và constraint theo semantics transaction. Một số thao tác nạp có thể hưởng lợi từ việc nạp theo thứ tự khóa chính, giảm page split và locality kém. Tắt `unique_checks` hoặc `foreign_key_checks` có thể thay đổi bảo vệ dữ liệu và không phải biện pháp an toàn chung; chỉ cân nhắc trong quy trình được kiểm chứng, với dữ liệu đã xác thực và đối soát đầy đủ.

### 6.3. SQL Server

SQL Server có thể áp dụng minimal logging cho một số bulk operation khi recovery model, table/index, lock và điều kiện nạp đáp ứng yêu cầu. Minimal logging không có nghĩa không ghi log, và điều kiện phụ thuộc recovery model, phiên bản, bảng đích, index và `TABLOCK`. Kiểm tra tài liệu đúng phiên bản và transaction log thực tế trước khi thiết kế.

### 6.4. Oracle

SQL*Loader direct path và một số thao tác direct-path insert có thể giảm redo trong điều kiện logging phù hợp. `NOLOGGING` không phải cam kết tuyệt đối không có redo, và có thể ảnh hưởng khả năng media recovery/standby nếu dữ liệu chưa được bảo vệ theo quy trình. Cần xem database force logging, Data Guard, backup và chính sách phục hồi trước khi sử dụng.

**Nguyên tắc:** không thay đổi chế độ logging/durability chỉ dựa trên benchmark tốc độ. Tính đúng đắn sau crash, khả năng phục hồi, replication và backup là một phần của hiệu năng vận hành tổng thể.

## 7. Index, constraint và trigger khi nạp dữ liệu

Mỗi dòng chèn có thể phải cập nhật nhiều index và kiểm tra nhiều ràng buộc. Khi nạp lượng dữ liệu lớn vào bảng có nhiều index, chi phí bảo trì index có thể chiếm tỷ trọng đáng kể.

### 7.1. Nạp vào bảng trống

Nếu tạo mới bảng hoặc partition, đôi khi có thể nạp dữ liệu trước rồi tạo index sau. Build index một lần trên tập dữ liệu lớn có thể hiệu quả hơn duy trì index cho từng insert. Tuy nhiên, cần xem:

- Có cần unique constraint để phát hiện duplicate trong lúc nạp không.
- Có foreign key hoặc trigger cần chạy ngay không.
- Thời gian tạo index, dung lượng tạm và I/O sau khi nạp.
- Khoảng thời gian bảng chưa có index có ảnh hưởng truy vấn không.
- Khả năng publish bảng/partition mới nguyên tử.

### 7.2. Bảng đang phục vụ OLTP

Không tùy tiện drop index hoặc disable constraint trên bảng đang phục vụ giao dịch. Việc này có thể làm truy vấn khác chậm đột ngột, tạo duplicate hoặc orphan row và cần thời gian rebuild. Nếu cần nạp lớn, cân nhắc staging hoặc partition riêng rồi chuyển dữ liệu theo bước có kiểm soát.

### 7.3. Trigger và computed values

Trigger có thể thực hiện audit, cập nhật counter, phát sinh dữ liệu phụ hoặc kiểm tra nghiệp vụ. Bulk load có thể bật/tắt trigger theo công cụ và tùy chọn; hành vi khác nhau theo engine. Nếu bỏ qua trigger, phải xác định chính xác logic nào bị bỏ qua và cách tái tạo kết quả sau nạp. Không giả định công cụ bulk luôn chạy trigger hoặc luôn bỏ qua trigger.

### 7.4. Thứ tự dữ liệu và index locality

Nạp dữ liệu gần thứ tự khóa của clustered index/B-tree có thể giảm page split và random I/O trong một số workload. Ngược lại, insert khóa ngẫu nhiên có thể phân tán ghi trên nhiều trang. Hãy đo fragmentation/page split, log bytes và tốc độ nạp; sắp xếp đầu vào cũng có chi phí CPU, disk và memory nên không phải lúc nào cũng có lợi.

## 8. Xử lý lỗi, dòng bị từ chối và tính idempotent

Nạp dữ liệu lớn thường gặp lỗi định dạng, kiểu dữ liệu, vi phạm unique/foreign key, dữ liệu thiếu hoặc lỗi kết nối. Một quy trình tốt phải xác định rõ dòng nào được chấp nhận, dòng nào bị từ chối và batch có thể chạy lại như thế nào.

### 8.1. Ghi nhận lỗi theo dòng

Nên lưu tối thiểu:

- Batch/file id và checksum nguồn.
- Số thứ tự dòng hoặc khóa nguồn.
- Mã lỗi và mô tả ngắn.
- Thời điểm nạp và phiên bản schema/parser.
- Trạng thái đã nạp, bị từ chối hay đang chờ xử lý lại.

Không chỉ ghi thông báo lỗi tổng quát như “import failed”. Cần biết số dòng đã đọc, đã ghi, bị loại và lý do để đối soát.

### 8.2. Idempotency và chống nạp trùng

Một tiến trình có thể mất kết nối sau khi database commit nhưng trước khi ứng dụng nhận được xác nhận. Ứng dụng không biết batch đã commit hay chưa và có thể gửi lại. Nếu insert không có khóa chống trùng, dữ liệu có thể bị nhân đôi.

Các biện pháp thường dùng:

- Gán `batch_id` ổn định cho một lần nhập logic.
- Gán khóa nguồn duy nhất cho mỗi dòng, chẳng hạn `(source_system, external_id)`.
- Lưu checksum hoặc version nguồn để phát hiện file bị thay đổi.
- Dùng unique constraint và upsert với quy tắc rõ ràng.
- Ghi checkpoint cùng transaction với dữ liệu của batch.
- Không đánh dấu batch hoàn tất trước khi dữ liệu đã commit và được đối soát.

Ví dụ bảng theo dõi batch:

```sql
CREATE TABLE import_batches (
    batch_id        uuid PRIMARY KEY,
    source_name     text NOT NULL,
    source_checksum text NOT NULL,
    expected_rows   bigint,
    loaded_rows     bigint NOT NULL DEFAULT 0,
    rejected_rows   bigint NOT NULL DEFAULT 0,
    status          text NOT NULL,
    started_at      timestamptz NOT NULL,
    completed_at    timestamptz
);
```

Khi nhận lại cùng `batch_id`, pipeline phải kiểm tra trạng thái và tiếp tục hoặc xác minh kết quả cũ, không tự động chạy lại toàn bộ theo cách có thể cộng trùng.

### 8.3. Retry và checkpoint

Retry chỉ an toàn khi thao tác có tính idempotent hoặc batch chưa commit. Nếu batch đã commit nhưng response bị mất, unique key hoặc bảng batch ledger phải giúp phát hiện trạng thái đó. Với file rất lớn, checkpoint có thể lưu offset, row number, partition hoặc source sequence đã xử lý.

Checkpoint theo byte offset chỉ an toàn nếu parser có thể tiếp tục đúng ranh giới record; CSV có newline nằm trong quoted field khiến offset dòng vật lý không luôn tương ứng với record. Tốt hơn là chia file thành các phần độc lập có checksum và row range rõ ràng hoặc dùng format có record boundary được xác định.

## 9. Kiểm tra và publish dữ liệu

Nạp xong không đồng nghĩa dữ liệu đã sẵn sàng cho người dùng. Cần xác thực số lượng, chất lượng và quan hệ trước khi publish.

### 9.1. Đối soát số dòng

So sánh:

- Số dòng dự kiến trong manifest hoặc file nguồn.
- Số dòng parser đã đọc.
- Số dòng nạp vào staging.
- Số dòng hợp lệ.
- Số dòng bị từ chối.
- Số dòng insert/update/delete ở bảng đích.

Các con số cần có định nghĩa rõ. Ví dụ, một dòng staging có thể cập nhật một dòng đích thay vì insert mới; vì vậy `loaded_rows` không nhất thiết bằng số dòng insert.

### 9.2. Kiểm tra chất lượng

Kiểm tra null ở trường bắt buộc, khóa trùng, giá trị ngoài miền, tham chiếu không tồn tại, tổng tiền, checksum hoặc tổng kiểm soát theo nhóm. Đối với dữ liệu số, có thể so tổng và số lượng theo partition hoặc khoảng thời gian để phát hiện mất dòng.

Không chỉ dựa vào tổng toàn file: một dòng thiếu và một dòng bị nhân đôi có thể triệt tiêu sai lệch số lượng. Hãy đối soát theo khóa hoặc nhóm có ý nghĩa nghiệp vụ.

### 9.3. Publish nguyên tử

Nếu người dùng không được nhìn thấy dữ liệu nhập dở, hãy giữ dữ liệu ở staging cho tới khi kiểm tra xong. Có thể dùng cờ `batch_status = 'PUBLISHED'`, view chỉ đọc batch đã publish, đổi partition hoặc transaction chuyển dữ liệu. Cơ chế cụ thể tùy engine và kích thước dữ liệu.

Với bảng lớn, một transaction publish khổng lồ có thể lại tạo lock/log lớn. Partition switch/exchange hoặc đổi metadata có thể giúp publish nhanh hơn khi schema, index, constraint và điều kiện partition tương thích. Hãy thử trên bản sao schema thực tế và xác minh semantics của engine.

## 10. Xử lý song song và kiểm soát áp lực

Chạy nhiều loader song song có thể tăng throughput khi dữ liệu độc lập và storage còn khả năng phục vụ. Nhưng nhiều worker cùng ghi một bảng có thể tranh chấp index page, khóa, log flush, buffer pool và I/O.

### 10.1. Chia dữ liệu thành phần độc lập

Có thể chia theo:

- Khoảng khóa chính hoặc hash bucket.
- Tenant hoặc nhóm khách hàng.
- Partition theo ngày/tháng.
- File segment hoặc batch id.

Mỗi worker nên có phạm vi dữ liệu không chồng lấn để giảm duplicate và lock contention. Nếu nhiều worker cùng cập nhật một key, cần khóa/serializing phù hợp hoặc gom delta trước khi ghi.

### 10.2. Tăng worker có kiểm soát

Thử số worker tăng dần và quan sát throughput tổng. Nếu throughput không tăng nhưng CPU, I/O wait, lock wait hoặc log latency tăng, hệ thống đã chạm giới hạn ở một tài nguyên. Thêm worker khi bottleneck nằm ở log disk hoặc index hot page thường làm tình hình xấu hơn.

### 10.3. Backpressure

Pipeline cần giảm tốc hoặc tạm dừng khi database không theo kịp. Các tín hiệu có thể gồm:

- Commit latency tăng.
- Transaction log/WAL gần ngưỡng dung lượng hoặc tốc độ flush cao.
- Replication lag hoặc downstream queue tăng.
- Lock wait, deadlock và timeout tăng.
- CPU/I/O vượt ngưỡng vận hành.

Backpressure giúp tránh dồn dữ liệu vào database nhanh hơn khả năng xử lý. Hãy thiết kế queue bền vững, giới hạn số batch đang chạy và khả năng tiếp tục từ checkpoint.

## 11. Tối ưu theo đặc điểm storage và workload

### 11.1. Append-only và khóa tăng dần

Nếu dữ liệu chỉ thêm mới, khóa tăng dần có thể cải thiện locality cho B-tree hoặc clustered index vì insert thường tập trung ở vùng cuối. Tuy nhiên, một điểm ghi cuối có thể trở thành hot page khi concurrency rất cao. Một số engine có cơ chế giảm tranh chấp hoặc thiết kế index phù hợp; cần đo page latch/wait thay vì giả định khóa tăng dần luôn tốt.

### 11.2. Ghi theo thứ tự partition

Với bảng partition theo thời gian, nạp theo từng partition có thể giảm việc chạm nhiều partition và giúp publish/retention dễ hơn. Cần bảo đảm dữ liệu nằm đúng partition và index/constraint được thiết kế tương thích với partition key.

### 11.3. Giảm index không cần thiết

Index không được truy vấn sử dụng vẫn có chi phí duy trì khi insert/update/delete. Trước khi nạp dữ liệu lịch sử lớn, có thể đánh giá index nào cần thiết trong lúc load và index nào có thể tạo sau. Quyết định phải tính thời gian rebuild, dung lượng tạm, tính khả dụng và constraint bảo vệ dữ liệu.

### 11.4. Tách workload OLTP và ETL

Nếu bulk load cạnh tranh với giao dịch trực tuyến, có thể nạp vào database/replica/staging riêng rồi chuyển dữ liệu theo partition hoặc pipeline. Đừng chuyển tải sang replica nếu replication lag sẽ làm truy vấn người dùng nhìn thấy dữ liệu trễ vượt yêu cầu.

## 12. Theo dõi và benchmark đường ghi

Để đánh giá đúng, hãy đo toàn bộ pipeline từ đọc nguồn đến publish, không chỉ thời gian câu lệnh bulk load.

| Nhóm đo | Chỉ số |
|---|---|
| Throughput | Rows/second, MB/second, batch completion rate |
| Độ trễ | Parse, transfer, execute, commit, validation và publish time |
| Database | CPU, memory, logical/physical reads, writes, IOPS, page/latch wait |
| Logging | WAL/redo/binlog/transaction log bytes, flush latency, log growth |
| Transaction | Batch duration, lock wait, deadlock, rollback time |
| Chất lượng | Expected/loaded/rejected/inserted/updated rows, duplicate và validation errors |
| Downstream | Replication lag, CDC lag, queue backlog, consumer throughput |
| Ứng dụng | Network bytes, retry, timeout, connection pool wait |

### 12.1. Benchmark có đối chứng

So sánh ít nhất các phương án phù hợp: insert từng dòng, prepared batch, multi-row insert và bulk load chuyên dụng. Dùng cùng dữ liệu, schema, index, constraint, cấu hình durability và mức đồng thời. Làm nóng cache hoặc ghi rõ trạng thái cache; lặp lại nhiều lần để tránh kết luận từ một lần chạy.

Đo cả khi bảng trống và khi bảng có dữ liệu/index hiện hữu. Nếu production có trigger, foreign key, replication và backup, benchmark nên phản ánh những thành phần quan trọng đó.

### 12.2. Kiểm tra workload hỗn hợp

Chạy bulk load cùng workload đọc/ghi đại diện và quan sát p95/p99 của OLTP. Một phương án nạp đạt 100.000 dòng/giây nhưng làm giao dịch trực tuyến timeout có thể không đáp ứng mục tiêu hệ thống.

### 12.3. Xác định bottleneck

- CPU cao, I/O thấp: xem parse, chuyển đổi dữ liệu, trigger, constraint và index maintenance.
- I/O write cao hoặc log flush chậm: xem log device, commit frequency, durability và batch size.
- Lock wait/deadlock cao: xem transaction scope, key overlap, index và thứ tự ghi.
- Network cao: xem round trip, packet size, compression và vị trí loader.
- Throughput không tăng khi thêm worker: xác định tài nguyên bão hòa và backpressure.
- Load nhanh nhưng publish chậm: xem validation, merge/upsert, index build và transaction publish.

## 13. Quy trình nạp dữ liệu theo lô tham khảo

Một pipeline có thể triển khai theo các bước sau:

1. **Đăng ký batch:** tạo batch id, ghi nguồn, checksum, schema version và số dòng dự kiến.
2. **Kiểm tra file:** encoding, header, delimiter, kiểu dữ liệu và kích thước.
3. **Chia phần:** tạo segment có ranh giới record và khóa nguồn ổn định.
4. **Nạp staging:** dùng COPY, LOAD DATA, BULK INSERT, SQL*Loader hoặc driver batch phù hợp.
5. **Ghi lỗi:** lưu dòng không hợp lệ cùng mã lỗi và vị trí nguồn.
6. **Xác thực:** kiểm tra unique, foreign key, miền giá trị, số dòng và tổng kiểm soát.
7. **Hợp nhất:** insert/upsert vào bảng đích theo khóa và quy tắc update rõ ràng.
8. **Đối soát:** so expected, loaded, rejected, inserted, updated và kết quả theo nhóm.
9. **Publish:** chuyển batch sang trạng thái sẵn sàng bằng transaction hoặc thao tác partition phù hợp.
10. **Checkpoint:** ghi nhận phần hoàn tất và cho phép resume an toàn.
11. **Theo dõi:** giám sát throughput, log, I/O, lock, replication lag và lỗi sau publish.

### 13.1. Trạng thái batch

Một state machine đơn giản có thể gồm:

```text
REGISTERED -> LOADING -> LOADED -> VALIDATING -> VALIDATED -> PUBLISHING -> PUBLISHED
                    \-> FAILED
                                      \-> REJECTED
```

`FAILED` biểu thị bước kỹ thuật không hoàn tất và có thể retry sau khi xác định nguyên nhân. `REJECTED` biểu thị dữ liệu không đạt quy tắc nghiệp vụ. Không gộp hai trạng thái này thành một lỗi chung vì cách xử lý khác nhau.

### 13.2. Resume sau lỗi

Khi loader dừng, xác định batch đã commit đến đâu. Nếu mỗi segment có transaction riêng, checkpoint cần ghi cùng commit dữ liệu segment đó. Khi chạy lại, bỏ qua segment đã hoàn tất và xác minh checksum. Nếu response commit bị mất, tra batch ledger/unique key để xác định trạng thái thay vì nạp lại mù quáng.

## 14. Những sai lầm thường gặp

- **Chèn một dòng mỗi request:** tạo nhiều round trip và overhead không cần thiết.
- **Tạo một câu SQL quá lớn:** vượt giới hạn packet/parameter hoặc tăng chi phí parse và memory.
- **Dùng batch size cố định mà không benchmark:** batch tối ưu phụ thuộc kích thước dòng, index, log và concurrency.
- **Một transaction cho toàn bộ file:** rollback và log có thể quá lớn, khó phục hồi.
- **Commit quá thường xuyên:** tăng chi phí flush log và giảm throughput.
- **Tắt constraint/index trên bảng production:** có thể tạo dữ liệu sai hoặc ảnh hưởng truy vấn khác.
- **Bỏ qua trigger khi bulk load:** các side effect nghiệp vụ có thể không được thực hiện.
- **Không xử lý duplicate:** retry sau timeout có thể nạp trùng.
- **Checkpoint không gắn với commit:** có thể bỏ mất hoặc lặp dữ liệu khi restart.
- **Không kiểm tra encoding và NULL:** dữ liệu có thể bị chuyển đổi sai mà không phát hiện.
- **Chỉ đo thời gian load:** bỏ qua validation, merge, index build, publish và replication lag.
- **Tăng worker vô hạn:** làm tăng tranh chấp log, I/O, index page và lock.
- **Giảm logging mà không xem recovery:** có thể ảnh hưởng backup, restore và replication.

## 15. Checklist thiết kế bulk load và batch processing

- [ ] Đã xác định mục tiêu throughput, độ trễ và mức ảnh hưởng tối đa tới OLTP.
- [ ] Đã chọn prepared batch, multi-row insert, bulk load hoặc staging theo quy mô dữ liệu.
- [ ] Đã xác định encoding, delimiter, quote, newline, `NULL`, timezone và precision.
- [ ] Đã có batch id, source key, checksum và schema version.
- [ ] Đã chọn kích thước batch bằng benchmark có đối chứng.
- [ ] Đã xác định transaction boundary và semantics khi một batch lỗi.
- [ ] Đã thiết kế checkpoint và resume an toàn sau timeout hoặc process crash.
- [ ] Đã có unique constraint/idempotency để chống nạp trùng.
- [ ] Đã kiểm tra index, foreign key, trigger và logging behavior của công cụ bulk.
- [ ] Đã có staging, validation và quy trình lưu dòng bị từ chối khi cần.
- [ ] Đã đối soát expected, loaded, rejected, inserted và updated rows.
- [ ] Đã có bước publish để người đọc không thấy dữ liệu chưa hoàn chỉnh nếu yêu cầu.
- [ ] Đã đo CPU, I/O, log bytes, commit latency, lock wait và replication lag.
- [ ] Đã kiểm thử retry, duplicate, lỗi giữa batch và phục hồi sau crash.
- [ ] Đã xác minh backup, recovery và replication vẫn đáp ứng yêu cầu sau khi nạp.

Chèn hàng loạt và xử lý theo lô giúp giảm overhead của đường ghi khi dữ liệu lớn, nhưng tốc độ thực tế phụ thuộc vào transaction, index, constraint, logging, storage và mức đồng thời. Một pipeline bền vững cần staging khi phù hợp, batch có ranh giới phục hồi, khóa nguồn chống trùng, validation, đối soát và publish có kiểm soát. Hãy đo từ đầu đến cuối và kiểm tra tác động tới workload đang chạy để chọn được cách nạp vừa nhanh vừa có thể vận hành an toàn.
