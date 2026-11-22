# Nạp dữ liệu lớn, tách dòng lỗi và đối soát kết quả

Nạp hàng nghìn hoặc hàng triệu bản ghi vào Oracle Database không chỉ là chạy một lệnh INSERT nhanh. Một quy trình bulk load đáng tin cậy phải trả lời được nhiều câu hỏi: file nào đã được nhận, bản ghi nào đã được đọc, dòng nào không hợp lệ, dữ liệu nào đã vào bảng đích, transaction nào đã commit, và làm sao chứng minh kết quả cuối cùng khớp với nguồn.

Một kiến trúc dễ vận hành thường chia công việc thành các bước:

**Nhận nguồn → Landing/Staging → Chuẩn hóa → Kiểm tra → Tách dòng lỗi → Nạp bảng đích → Đối soát → Hoàn tất batch.**

Tách dữ liệu thô khỏi dữ liệu đã được xác nhận giúp giữ nguyên bằng chứng đầu vào, sửa lỗi mà không cần đọc lại file gốc, và chạy lại một batch theo cách có kiểm soát. Oracle cung cấp nhiều cơ chế cho từng loại workload: SQL*Loader, external tables, INSERT ... SELECT, direct-path insert, JDBC batching, PL/SQL FORALL và DML error logging. Không có một công cụ phù hợp cho mọi nguồn dữ liệu.

Bài học thuộc nhóm **Thực hành tổng hợp** của Database Engine Relational Oracle. Nội dung tập trung vào thiết kế pipeline nạp dữ liệu lớn, staging, phân loại dòng lỗi, xử lý lỗi theo từng dòng, transaction/chunk, restart an toàn và đối soát source-to-target.

Sau bài này, bạn có thể:

- Chọn cơ chế nạp dữ liệu phù hợp với file, ứng dụng Java hoặc dữ liệu đã nằm trong database.
- Thiết kế batch ID, source row number và lineage cho từng bản ghi.
- Tạo staging table để giữ dữ liệu thô trước khi chuyển đổi.
- Phân biệt SQL*Loader conventional path, direct path và external tables.
- Dùng INSERT ... SELECT, MERGE và JDBC batch cho workload phù hợp.
- Tạo error logging table bằng DBMS_ERRLOG.
- Tách lỗi DML bằng LOG ERRORS và REJECT LIMIT.
- Dùng PL/SQL FORALL SAVE EXCEPTIONS để xử lý lỗi trong bulk PL/SQL.
- Phân biệt lỗi dữ liệu theo dòng với lỗi hệ thống khiến cả statement/job thất bại.
- Chọn batch size và transaction chunk size.
- Thiết kế idempotency, checkpoint và retry.
- Đối soát số lượng, khóa nghiệp vụ, tổng tiền, checksum và dữ liệu chi tiết.
- Lập báo cáo rejected rows, duplicate rows và reconciliation variance.
- Tạo runbook vận hành, phục hồi và kết thúc batch.

> **Phạm vi ví dụ:** Ví dụ dùng Oracle Database 19c, SQL*Loader, SQL, PL/SQL và Java JDBC. Tên bảng, service, file path và business key là giả định. Điều chỉnh kiểu dữ liệu, quyền truy cập, giới hạn tài nguyên và transaction policy theo môi trường thật.

## 1. Mục tiêu của một quy trình bulk load

Một bulk load tốt cần đạt cả throughput lẫn khả năng kiểm soát kết quả.

### 1.1. Throughput

Throughput là lượng dữ liệu xử lý trong một đơn vị thời gian, ví dụ:

- Rows per second.
- MB per second.
- Số file hoàn tất mỗi giờ.
- Số batch hoàn tất trong một cửa sổ ETL.

Chỉ tối ưu tốc độ mà không theo dõi lỗi và tính đầy đủ có thể khiến pipeline nạp nhanh nhưng tạo dữ liệu sai.

### 1.2. Data quality

Mỗi record cần được đánh giá theo quy tắc dữ liệu:

- Có đủ trường bắt buộc không?
- Ngày tháng và số có chuyển đổi được không?
- Mã khách hàng/sản phẩm có tồn tại không?
- Business key có bị trùng không?
- Giá trị có nằm trong miền cho phép không?
- Các trường có nhất quán với nhau không?

### 1.3. Traceability

Với mỗi dòng dữ liệu, hệ thống nên truy ngược được:

- File nguồn.
- Batch ID.
- Source row number hoặc source record ID.
- Thời điểm nhận và nạp.
- Phiên bản mapping/rule.
- Trạng thái xử lý.
- Lý do bị từ chối.

### 1.4. Recoverability

Nếu job dừng giữa chừng, cần biết:

- Chunk nào đã commit.
- Chunk nào chưa chạy.
- Dòng nào đã được xử lý.
- Có thể chạy lại mà không tạo duplicate không?
- Có thể tiếp tục từ checkpoint nào?

### 1.5. Reconciliation

Đối soát phải chứng minh được nguồn và đích khớp theo quy tắc đã thống nhất. Chỉ so sánh tổng số dòng là chưa đủ; hai tập dữ liệu có thể cùng số lượng nhưng khác khóa hoặc giá trị.

## 2. Pipeline tổng thể

~~~text
             SOURCE
        CSV / API / JDBC
               |
               v
        LANDING / FILE STORE
      checksum + immutable file
               |
               v
           STAGING
       raw values + lineage
               |
               v
      NORMALIZE / VALIDATE
        format + business rules
               |
        +------+------+
        |             |
        v             v
     VALID ROWS    REJECT ROWS
        |             |
        v             v
     APPLY DML     ERROR REVIEW
        |
        v
      TARGET
        |
        v
    RECONCILIATION
        |
        v
   BATCH COMPLETION
~~~

### 2.1. Landing

Landing là nơi lưu file hoặc payload nguyên gốc. File nên được giữ bất biến trong thời gian cần đối soát và audit. Ghi nhận checksum, kích thước, tên nguồn và thời điểm nhận.

### 2.2. Staging

Staging là vùng dữ liệu trung gian trong Oracle. Có thể lưu raw text và metadata trước khi ép kiểu hoặc áp dụng business rules.

### 2.3. Validation

Validation phân loại record thành hợp lệ, cần cảnh báo hoặc bị từ chối. Quy tắc cần có mã lỗi ổn định để báo cáo và sửa dữ liệu.

### 2.4. Apply

Apply là bước ghi dữ liệu hợp lệ vào bảng đích bằng INSERT, MERGE hoặc quy trình PL/SQL/JDBC.

### 2.5. Reconciliation

Reconciliation so sánh source, staging, accepted, rejected và target theo batch. Batch chỉ hoàn tất khi đạt các điều kiện kiểm soát đã định nghĩa.

## 3. Thiết kế batch ID và lineage

Batch ID là khóa định danh một lần nhận dữ liệu hoặc một đơn vị xử lý.

### 3.1. Bảng quản lý batch

~~~sql
CREATE TABLE load_batch (
    batch_id          VARCHAR2(40) PRIMARY KEY,
    source_system     VARCHAR2(50) NOT NULL,
    source_file       VARCHAR2(500),
    source_checksum   VARCHAR2(128),
    received_at       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    started_at        TIMESTAMP,
    completed_at      TIMESTAMP,
    batch_status      VARCHAR2(20) NOT NULL,
    expected_rows     NUMBER,
    staged_rows       NUMBER DEFAULT 0 NOT NULL,
    valid_rows        NUMBER DEFAULT 0 NOT NULL,
    rejected_rows     NUMBER DEFAULT 0 NOT NULL,
    inserted_rows     NUMBER DEFAULT 0 NOT NULL,
    updated_rows      NUMBER DEFAULT 0 NOT NULL,
    unchanged_rows    NUMBER DEFAULT 0 NOT NULL,
    error_message     VARCHAR2(2000)
);
~~~

Các trạng thái có thể dùng:

| Trạng thái | Ý nghĩa |
| --- | --- |
| RECEIVED | Đã nhận metadata/file |
| LOADING | Đang nạp vào staging |
| STAGED | Dữ liệu đã vào staging |
| VALIDATING | Đang kiểm tra dữ liệu |
| VALIDATED | Đã phân loại hợp lệ/lỗi |
| APPLYING | Đang ghi vào target |
| APPLIED | Đã hoàn tất bước apply |
| RECONCILING | Đang đối soát |
| COMPLETED | Đối soát đạt yêu cầu |
| PARTIAL | Có kết quả hợp lệ và reject được chấp nhận theo policy |
| FAILED | Batch thất bại |
| CANCELLED | Batch bị hủy theo quy trình |

Trạng thái phải được cập nhật cùng checkpoint và transaction policy. Không đánh dấu COMPLETED chỉ vì lệnh SQL đã trả về thành công.

### 3.2. Tạo batch ID

Có thể dùng UUID hoặc mã sinh từ sequence. Điều quan trọng là batch ID duy nhất và được truyền qua mọi bước.

~~~sql
INSERT INTO load_batch (
    batch_id,
    source_system,
    source_file,
    source_checksum,
    batch_status,
    expected_rows
)
VALUES (
    'BATCH-20261114-0001',
    'ERP',
    'orders_20261114.csv',
    'sha256:example-checksum',
    'RECEIVED',
    250000
);
~~~

Checksum trong ví dụ là placeholder. Khi triển khai, tính checksum trên file thực tế ở landing layer và lưu thuật toán/giá trị rõ ràng.

### 3.3. Source row number

Mỗi record nên có số dòng hoặc source record ID ổn định. Nếu file bị sắp xếp lại trong lần chạy lại, chỉ dựa vào vị trí dòng có thể không đủ; ưu tiên source record ID hoặc business key ổn định khi nguồn cung cấp.

### 3.4. Bảng staging

Ví dụ bảng staging cho đơn hàng:

~~~sql
CREATE TABLE stg_order (
    batch_id          VARCHAR2(40) NOT NULL,
    source_row_no     NUMBER NOT NULL,
    source_record_id  VARCHAR2(100),
    order_id_raw      VARCHAR2(100),
    customer_id_raw   VARCHAR2(100),
    order_date_raw    VARCHAR2(100),
    amount_raw        VARCHAR2(100),
    currency_raw      VARCHAR2(20),
    source_file       VARCHAR2(500),
    loaded_at         TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    validation_status VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    CONSTRAINT pk_stg_order
        PRIMARY KEY (batch_id, source_row_no)
);
~~~

Raw columns được giữ dạng text để việc parse và validation diễn ra có kiểm soát. Nếu nguồn đã là dữ liệu có kiểu mạnh và được kiểm tra trước, staging có thể dùng kiểu dữ liệu phù hợp ngay từ đầu.

### 3.5. Bảng reject

~~~sql
CREATE TABLE load_reject (
    reject_id         NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    batch_id          VARCHAR2(40) NOT NULL,
    source_row_no     NUMBER,
    source_record_id  VARCHAR2(100),
    source_file       VARCHAR2(500),
    reject_stage      VARCHAR2(30) NOT NULL,
    error_code        VARCHAR2(100) NOT NULL,
    error_message     VARCHAR2(2000),
    raw_payload       CLOB,
    rejected_at       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    resolution_status VARCHAR2(20) DEFAULT 'OPEN' NOT NULL
);
~~~

Reject table lưu cả lỗi kỹ thuật và lỗi nghiệp vụ. Có thể tách thành nhiều bảng theo loại lỗi hoặc giữ một bảng chung với reject_stage/error_code.

### 3.6. Không chỉ lưu message tự do

Nên dùng error code ổn định như:

| Error code | Ý nghĩa |
| --- | --- |
| REQUIRED_ORDER_ID | Thiếu mã đơn hàng |
| INVALID_ORDER_DATE | Ngày không đúng định dạng |
| INVALID_AMOUNT | Giá trị tiền không hợp lệ |
| UNKNOWN_CUSTOMER | Không tìm thấy khách hàng |
| DUPLICATE_SOURCE_KEY | Trùng source record |
| DUPLICATE_TARGET_KEY | Business key đã tồn tại |
| INVALID_CURRENCY | Mã tiền tệ không hợp lệ |
| DML_CONSTRAINT_ERROR | DML bị database constraint từ chối |

Message có thể thay đổi theo phiên bản hoặc ngôn ngữ; error code giúp báo cáo và routing ổn định.

## 4. Chọn công cụ nạp dữ liệu

| Cơ chế | Nguồn phù hợp | Điểm mạnh | Cần chú ý |
| --- | --- | --- | --- |
| SQL*Loader | File text/CSV | Công cụ bulk load chuyên dụng | Control file, bad/discard/log files, direct path |
| External tables | File nằm trên database server | Query file bằng SQL | DIRECTORY object, quyền OS, reject limit |
| INSERT ... SELECT | Dữ liệu đã ở trong Oracle | Set-based, ít chuyển dữ liệu | Undo/redo, locks, execution plan |
| Direct-path INSERT | Load lớn vào table/partition | Có thể tăng throughput | Restriction, locking, commit boundary |
| JDBC batching | Dữ liệu đến từ Java | Giảm round trips | Batch size, transaction, partial failures |
| PL/SQL FORALL | Collection trong PL/SQL | Bulk bind giảm context switch | SAVE EXCEPTIONS và SQL%BULK_EXCEPTIONS |
| DML error logging | INSERT/UPDATE/DELETE/MERGE | Tách nhiều lỗi DML theo dòng | Không log được mọi loại lỗi |

### 4.1. Câu hỏi chọn công cụ

- Dữ liệu hiện đang ở file hay trong database?
- File được đặt ở máy ứng dụng hay database server?
- Có cần biến đổi từng record bằng Java không?
- Có cần xử lý lỗi riêng cho từng dòng không?
- Có cần tiếp tục phần hợp lệ khi một số dòng lỗi không?
- Khối lượng có đủ lớn để direct path hoặc bulk load chuyên dụng có lợi không?
- Có cần transaction atomic trên toàn file không?
- Hệ thống có cho phép tạo staging table và reject table không?

### 4.2. Ưu tiên set-based khi dữ liệu đã ở Oracle

Nếu nguồn dữ liệu đã nằm trong bảng Oracle, hãy cân nhắc INSERT ... SELECT hoặc MERGE thay vì kéo hàng triệu dòng lên Java rồi gửi lại.

~~~sql
INSERT INTO order_archive (
    order_id,
    customer_id,
    order_date,
    amount
)
SELECT
    order_id,
    customer_id,
    order_date,
    amount
FROM orders
WHERE order_date < DATE '2025-01-01';
~~~

Database xử lý tập dữ liệu ngay tại nơi lưu trữ, tránh round trips cho từng row.

## 5. SQL*Loader: nạp dữ liệu từ file

SQL*Loader là Oracle utility dùng để load dữ liệu từ external files vào database tables.

### 5.1. Conventional path và direct path

| Chế độ | Mô tả |
| --- | --- |
| Conventional path | Dùng SQL INSERT interface; phù hợp khi cần các xử lý SQL thông thường và tải vừa phải |
| Direct path | Định dạng và ghi data blocks theo đường nạp trực tiếp; thường phù hợp với bulk load lớn |

Direct path có thể giảm một số overhead so với conventional path nhưng có restriction về bảng, index, trigger, constraint, concurrent access và transaction. Kiểm tra SQL*Loader documentation của release đang chạy trước khi chọn.

### 5.2. Các file đầu ra

| File | Mục đích |
| --- | --- |
| Log file | Tóm tắt load, số rows, thời gian, lỗi |
| Bad file | Record không được load do lỗi dữ liệu hoặc conversion |
| Discard file | Record bị loại theo điều kiện WHEN hoặc điều kiện discard |
| Control file | Mô tả cấu trúc input và mapping vào table |

Bad file và discard file có ý nghĩa khác nhau. Record bị discard không nhất thiết là record sai định dạng; nó có thể không thỏa điều kiện chọn lọc trong control file.

### 5.3. Ví dụ CSV

File orders.csv:

~~~csv
1001,501,2026-11-01,125.50,VND
1002,502,2026-11-02,240.00,VND
1003,503,2026-11-03,89.90,VND
~~~

Giả sử file có thứ tự cột như trên và mỗi dòng là một record.

### 5.4. Control file

~~~text
LOAD DATA
INFILE 'orders.csv'
BADFILE 'orders.bad'
DISCARDFILE 'orders.dsc'
APPEND
INTO TABLE stg_order
FIELDS TERMINATED BY ','
OPTIONALLY ENCLOSED BY '"'
TRAILING NULLCOLS
(
    order_id_raw     CHAR,
    customer_id_raw  CHAR,
    order_date_raw   CHAR,
    amount_raw       CHAR,
    currency_raw     CHAR
)
~~~

Control file này là ví dụ đơn giản. Bảng staging trong ví dụ cần được bổ sung batch_id, source_row_no và source_file bằng cách dùng bind/constant fields hoặc bước gán metadata riêng phù hợp với cách vận hành.

Nếu cần source row number ổn định, có thể dùng cơ chế record numbering trong control file hoặc nạp file vào một staging structure có record number. Kiểm tra cú pháp RECNUM và mapping theo control file version.

### 5.5. Chạy SQL*Loader

~~~text
sqlldr userid=app_user@SALES_PROD control=orders.ctl log=orders.log bad=orders.bad discard=orders.dsc direct=false errors=1000
~~~

Không đưa password thật vào command line hoặc shell history. Dùng cơ chế xác thực an toàn phù hợp với môi trường và nhập secret theo prompt/secure store khi được hỗ trợ.

### 5.6. Direct path

Có thể chạy direct path:

~~~text
sqlldr userid=app_user@SALES_PROD control=orders.ctl log=orders.log bad=orders.bad direct=true
~~~

Đánh giá:

- Throughput so với conventional path.
- Index/constraint maintenance.
- Trigger behavior.
- Concurrent access.
- Recovery/logging requirements.
- Thời gian build/rebuild index nếu có.
- Khả năng restart sau lỗi.

Không chuyển sang direct path chỉ dựa vào số lượng rows. Workload và restriction của table mới quyết định.

### 5.7. ERRORS và ROWS

SQL*Loader có tham số điều khiển số lỗi cho phép và số rows giữa các save/commit tùy load path. Các giá trị này không phải một cơ chế transaction policy tổng quát thay thế thiết kế batch.

Đọc log để biết:

- Rows read.
- Rows loaded.
- Rows rejected.
- Rows discarded.
- Rows not loaded do errors.
- Commit points.
- Error messages.

Không kết luận job thành công chỉ vì process exit code là 0 nếu log cho thấy có rejected rows mà nghiệp vụ không cho phép.

### 5.8. Xử lý CSV thực tế

CSV có thể chứa:

- Dấu phẩy bên trong quoted field.
- Quote escape.
- Dòng trống.
- Unicode.
- Newline trong quoted field.
- Decimal separator khác nhau.
- Date format theo locale.

Định nghĩa rõ encoding, delimiter, quote, escape, newline và null representation với bên tạo file. Test file có các trường hợp biên trước khi chạy dữ liệu lớn.

### 5.9. Nạp lại file

Không dùng APPEND lặp lại cùng file nếu chưa có idempotency. Chạy lại có thể tạo duplicate. Dùng batch ID, source key, staging cleanup có kiểm soát hoặc truncate staging riêng của batch trước khi nạp lại.

## 6. External tables: query file bằng SQL

External table cho phép Oracle đọc dữ liệu trong file thông qua SQL mà không cần load trước vào table vật lý.

### 6.1. DIRECTORY object

Oracle cần DIRECTORY object trỏ tới thư mục trên database server:

~~~sql
CREATE OR REPLACE DIRECTORY inbound_dir AS '/u01/data/inbound';
~~~

Cấp quyền đọc:

~~~sql
GRANT READ ON DIRECTORY inbound_dir TO app_user;
~~~

Nếu external table cần ghi bad/log file theo cấu hình, có thể cần quyền WRITE. OS user chạy Oracle database process cũng phải có quyền filesystem tương ứng.

Đường dẫn là đường dẫn trên database server, không phải đường dẫn local của laptop hoặc application server.

### 6.2. Tạo external table

~~~sql
CREATE TABLE ext_order_file (
    order_id_text     VARCHAR2(100),
    customer_id_text  VARCHAR2(100),
    order_date_text   VARCHAR2(100),
    amount_text       VARCHAR2(100),
    currency_text     VARCHAR2(20)
)
ORGANIZATION EXTERNAL (
    TYPE ORACLE_LOADER
    DEFAULT DIRECTORY inbound_dir
    ACCESS PARAMETERS (
        RECORDS DELIMITED BY NEWLINE
        FIELDS TERMINATED BY ','
        OPTIONALLY ENCLOSED BY '"'
        MISSING FIELD VALUES ARE NULL
        (
            order_id_text     CHAR(100),
            customer_id_text  CHAR(100),
            order_date_text   CHAR(100),
            amount_text       CHAR(100),
            currency_text     CHAR(20)
        )
    )
    LOCATION ('orders.csv')
)
REJECT LIMIT UNLIMITED;
~~~

Ví dụ giả định file có cấu trúc đơn giản. Với CSV phức tạp, hãy kiểm tra các tùy chọn access parameters và giới hạn record format của ORACLE_LOADER.

### 6.3. Query external table

~~~sql
SELECT *
FROM ext_order_file;
~~~

External table là cách đọc file như một table trong SQL. Dữ liệu vẫn nằm trong file; SELECT không tự copy dữ liệu vào bảng staging.

### 6.4. Nạp vào staging

~~~sql
INSERT INTO stg_order (
    batch_id,
    source_row_no,
    order_id_raw,
    customer_id_raw,
    order_date_raw,
    amount_raw,
    currency_raw,
    source_file
)
SELECT
    'BATCH-20261114-0001',
    ROWNUM,
    order_id_text,
    customer_id_text,
    order_date_text,
    amount_text,
    currency_text,
    'orders.csv'
FROM ext_order_file;
~~~

ROWNUM ở đây chỉ minh họa việc gán ordinal trong một lần đọc. Nếu cần record identity ổn định qua nhiều lần chạy, hãy tạo source record ID ở upstream hoặc dùng cơ chế record numbering có kiểm soát.

### 6.5. REJECT LIMIT

External table có REJECT LIMIT để giới hạn số lỗi access/record mà Oracle chấp nhận trước khi query thất bại. UNLIMITED không có nghĩa mọi dữ liệu sai đều được chấp nhận hoặc tự chuyển thành reject table có đầy đủ business reason.

Lỗi parse file ở external table khác với lỗi business validation sau khi dữ liệu đã đọc được. Hãy thiết kế riêng:

- File/access rejects.
- Data conversion rejects.
- Business validation rejects.
- Target DML rejects.

### 6.6. Khi nào external tables phù hợp?

- File đã được đặt trên database server hoặc storage được Oracle truy cập.
- Muốn dùng SQL để filter/transform trước khi nạp.
- Muốn tránh copy dữ liệu qua application tier.
- Có thể kiểm soát quyền DIRECTORY và filesystem.

Nếu file chỉ nằm trong pod/application host, cần chuyển file tới vùng mà database server đọc được hoặc dùng JDBC/SQL*Loader từ tầng thích hợp.

## 7. Staging-first: giữ raw data trước khi chuyển đổi

Staging là điểm kiểm soát trung tâm của pipeline.

### 7.1. Vì sao nên giữ raw values?

Nếu parse ngày hoặc số ngay lúc đọc file, một giá trị sai có thể làm hỏng toàn bộ load hoặc mất biểu diễn gốc. Raw staging giúp:

- Giữ giá trị nguồn chính xác.
- Thử lại validation khi business rule thay đổi.
- So sánh raw value với transformed value.
- Phân loại lỗi conversion.
- Audit và trace ngược.

### 7.2. Gán batch metadata

Mọi dòng cần gắn batch ID. Nếu nguồn có source ID, giữ cả source ID.

~~~sql
SELECT
    batch_id,
    source_row_no,
    source_record_id,
    order_id_raw,
    customer_id_raw,
    order_date_raw,
    amount_raw,
    currency_raw
FROM stg_order
WHERE batch_id = :batch_id;
~~~

### 7.3. Không trộn batch

Truy vấn validation, apply và reconciliation phải lọc batch ID. Nếu không, dữ liệu từ batch trước có thể bị đếm hoặc xử lý lại.

### 7.4. Index staging

Các index thường hữu ích:

- (batch_id, source_row_no).
- (batch_id, validation_status).
- (batch_id, source_record_id).

Không tạo quá nhiều index trên staging nếu insert throughput là ưu tiên. Đo chi phí load và query.

### 7.5. Partition staging

Với khối lượng lớn và retention theo batch/date, partition staging theo ngày hoặc batch window có thể giúp quản lý dữ liệu và cleanup. Partition key cần hỗ trợ các query thực tế, đặc biệt batch_id và thời gian nạp.

## 8. Chuẩn hóa và chuyển đổi dữ liệu

Validation cần tách conversion an toàn khỏi business rules.

### 8.1. Ngày tháng

Không dựa vào NLS_DATE_FORMAT mặc định.

~~~sql
TO_DATE(order_date_raw, 'YYYY-MM-DD')
~~~

Format phải thống nhất với source contract. Nếu nguồn có timestamp, dùng TO_TIMESTAMP với format tương ứng.

### 8.2. Số thập phân

Không dựa vào NLS_NUMERIC_CHARACTERS mặc định nếu file có decimal separator rõ ràng.

~~~sql
TO_NUMBER(
    amount_raw,
    '999999999999D99',
    'NLS_NUMERIC_CHARACTERS=''.,'''
)
~~~

Ở đây dấu chấm là decimal separator và dấu phẩy là group separator theo NLS parameter được chỉ định.

### 8.3. Validate conversion trước khi chuyển

Oracle 19c có VALIDATE_CONVERSION:

~~~sql
SELECT
    source_row_no,
    amount_raw,
    VALIDATE_CONVERSION(
        amount_raw AS NUMBER,
        '999999999999D99',
        'NLS_NUMERIC_CHARACTERS=''.,'''
    ) AS amount_is_valid
FROM stg_order
WHERE batch_id = :batch_id;
~~~

VALIDATE_CONVERSION giúp kiểm tra một biểu thức có chuyển đổi được hay không. Nó không thay thế business validation, ví dụ amount phải lớn hơn 0.

### 8.4. Null và empty string

Oracle xử lý zero-length character string như NULL trong SQL cho VARCHAR2. Source contract phải xác định:

- Empty field có nghĩa NULL hay dữ liệu thiếu?
- Chuỗi chỉ chứa space có được trim không?
- Giá trị sentinel như N/A, UNKNOWN có ý nghĩa gì?

Đừng tự chuyển tất cả giá trị rỗng thành 0 hoặc ngày mặc định.

### 8.5. Chuẩn hóa text

Có thể cần:

- Trim khoảng trắng.
- Chuẩn hóa Unicode.
- Chuẩn hóa mã quốc gia/tiền tệ.
- Chuẩn hóa chữ hoa/thường theo business key.
- Loại bỏ ký tự điều khiển không hợp lệ.

Không trim hoặc đổi casing các trường mà khoảng trắng/case là một phần hợp lệ của dữ liệu.

## 9. Validation nhiều lớp

Một record chỉ được chuyển sang accepted khi vượt qua các lớp validation bắt buộc.

### 9.1. Structural validation

- Đúng số cột.
- Đúng delimiter/encoding.
- Record không bị cắt.
- Field length phù hợp.
- Header đúng version.

### 9.2. Type validation

- Ngày parse được.
- Số parse được.
- Timestamp hợp lệ.
- Mã hóa Unicode hợp lệ.

### 9.3. Required-field validation

- Order ID không null.
- Customer ID không null.
- Amount không null nếu nghiệp vụ bắt buộc.

### 9.4. Domain validation

- Currency thuộc danh sách được phép.
- Status nằm trong enum hợp lệ.
- Amount trong giới hạn.
- Date nằm trong khoảng nghiệp vụ.

### 9.5. Referential validation

- Customer tồn tại.
- Product tồn tại.
- Account đang hoạt động.
- Foreign key liên quan hợp lệ.

### 9.6. Duplicate validation

- Duplicate trong cùng file.
- Duplicate giữa các batch.
- Duplicate so với target.
- Duplicate source ID với nội dung khác nhau.

### 9.7. Cross-field validation

- End date không trước start date.
- Currency phù hợp với account.
- Quantity và unit price tạo thành total hợp lệ.
- Status phù hợp với các trường thời gian.

### 9.8. Gán mã lỗi ổn định

Ví dụ tạo view dữ liệu chuyển đổi:

~~~sql
CREATE OR REPLACE VIEW v_stg_order_converted AS
SELECT
    batch_id,
    source_row_no,
    source_record_id,
    order_id_raw,
    customer_id_raw,
    order_date_raw,
    amount_raw,
    currency_raw,
    CASE
        WHEN VALIDATE_CONVERSION(order_id_raw AS NUMBER) = 1
        THEN TO_NUMBER(order_id_raw)
    END AS order_id,
    CASE
        WHEN VALIDATE_CONVERSION(customer_id_raw AS NUMBER) = 1
        THEN TO_NUMBER(customer_id_raw)
    END AS customer_id,
    CASE
        WHEN VALIDATE_CONVERSION(order_date_raw AS DATE, 'YYYY-MM-DD') = 1
        THEN TO_DATE(order_date_raw, 'YYYY-MM-DD')
    END AS order_date,
    CASE
        WHEN VALIDATE_CONVERSION(
            amount_raw AS NUMBER,
            '999999999999D99',
            'NLS_NUMERIC_CHARACTERS=''.,'''
        ) = 1
        THEN TO_NUMBER(
            amount_raw,
            '999999999999D99',
            'NLS_NUMERIC_CHARACTERS=''.,'''
        )
    END AS amount
FROM stg_order;
~~~

View này minh họa chuyển đổi có kiểm tra. Trong hệ thống lớn, có thể dùng staging typed table hoặc materialized transform table để tránh lặp conversion nhiều lần.

### 9.9. Ghi validation rejects

~~~sql
INSERT INTO load_reject (
    batch_id,
    source_row_no,
    source_record_id,
    source_file,
    reject_stage,
    error_code,
    error_message
)
SELECT
    s.batch_id,
    s.source_row_no,
    s.source_record_id,
    s.source_file,
    'VALIDATION',
    CASE
        WHEN s.order_id_raw IS NULL THEN 'REQUIRED_ORDER_ID'
        WHEN VALIDATE_CONVERSION(s.order_id_raw AS NUMBER) = 0
            THEN 'INVALID_ORDER_ID'
        WHEN s.amount_raw IS NULL THEN 'REQUIRED_AMOUNT'
        WHEN VALIDATE_CONVERSION(s.amount_raw AS NUMBER) = 0
            THEN 'INVALID_AMOUNT'
        ELSE 'OTHER_VALIDATION_ERROR'
    END,
    'Record failed validation'
FROM stg_order s
WHERE s.batch_id = :batch_id
  AND (
      s.order_id_raw IS NULL
      OR VALIDATE_CONVERSION(s.order_id_raw AS NUMBER) = 0
      OR s.amount_raw IS NULL
      OR VALIDATE_CONVERSION(s.amount_raw AS NUMBER) = 0
  );
~~~

Nếu một dòng có nhiều lỗi, có thể ghi một reject record cho mỗi lỗi hoặc một record chứa danh sách lỗi. Chọn mô hình nhất quán để báo cáo không đếm nhầm số dòng lỗi thành số lỗi.

## 10. Tách accepted rows và rejected rows

Không nên xóa raw staging sau khi đã tạo reject.

### 10.1. Bảng accepted/typed staging

~~~sql
CREATE TABLE stg_order_valid (
    batch_id          VARCHAR2(40) NOT NULL,
    source_row_no     NUMBER NOT NULL,
    source_record_id  VARCHAR2(100),
    order_id          NUMBER NOT NULL,
    customer_id       NUMBER NOT NULL,
    order_date        DATE NOT NULL,
    amount            NUMBER(15,2) NOT NULL,
    currency_code     VARCHAR2(3) NOT NULL,
    CONSTRAINT pk_stg_order_valid
        PRIMARY KEY (batch_id, source_row_no)
);
~~~

### 10.2. Nạp accepted rows

~~~sql
INSERT INTO stg_order_valid (
    batch_id,
    source_row_no,
    source_record_id,
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code
)
SELECT
    batch_id,
    source_row_no,
    source_record_id,
    order_id,
    customer_id,
    order_date,
    amount,
    currency_raw
FROM v_stg_order_converted
WHERE batch_id = :batch_id
  AND order_id IS NOT NULL
  AND customer_id IS NOT NULL
  AND order_date IS NOT NULL
  AND amount IS NOT NULL
  AND currency_raw IN ('VND', 'USD', 'EUR');
~~~

Đây mới chỉ là ví dụ validation type/domain. Cần bổ sung customer existence, duplicate và các business rules trước khi apply.

### 10.3. Cập nhật trạng thái staging

~~~sql
UPDATE stg_order s
SET validation_status =
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM stg_order_valid v
            WHERE v.batch_id = s.batch_id
              AND v.source_row_no = s.source_row_no
        )
        THEN 'VALID'
        ELSE 'REJECTED'
    END
WHERE s.batch_id = :batch_id;
~~~

Đảm bảo mỗi raw record có đúng một trạng thái cuối của bước validation. Nếu record có nhiều reject reasons, trạng thái vẫn chỉ là REJECTED còn reject table lưu chi tiết từng reason.

## 11. Duplicate detection

Duplicate có thể xuất hiện trong cùng file hoặc so với dữ liệu đã nạp trước.

### 11.1. Duplicate trong batch

~~~sql
SELECT
    order_id,
    COUNT(*) AS duplicate_count
FROM stg_order_valid
WHERE batch_id = :batch_id
GROUP BY order_id
HAVING COUNT(*) > 1;
~~~

### 11.2. Xác định dòng giữ lại

Nếu source contract cho phép chọn một record theo timestamp/priority, dùng ROW_NUMBER với thứ tự xác định:

~~~sql
SELECT *
FROM (
    SELECT
        v.*,
        ROW_NUMBER() OVER (
            PARTITION BY v.order_id
            ORDER BY v.source_row_no DESC
        ) AS rn
    FROM stg_order_valid v
    WHERE v.batch_id = :batch_id
)
WHERE rn = 1;
~~~

Ví dụ chọn dòng cuối chỉ phù hợp nếu source row order thực sự có nghĩa. Nếu không, phải dùng business timestamp hoặc source sequence. Không âm thầm loại duplicate mà không ghi reject/audit.

### 11.3. Duplicate so với target

~~~sql
SELECT
    s.order_id,
    s.source_row_no
FROM stg_order_valid s
JOIN app_order t
  ON t.order_id = s.order_id
WHERE s.batch_id = :batch_id;
~~~

Đây là duplicate nếu business rule yêu cầu insert-only. Nếu nghiệp vụ cho phép cập nhật, chuyển sang MERGE.

### 11.4. Unique constraint vẫn là lớp bảo vệ cuối

Pre-check duplicate không loại bỏ race condition giữa hai batch đồng thời. Unique constraint trên target vẫn cần thiết để bảo vệ tính toàn vẹn.

## 12. Nạp vào target bằng INSERT ... SELECT

Khi accepted rows đã ở staging, set-based INSERT thường hiệu quả hơn loop từng dòng.

### 12.1. Insert-only

~~~sql
INSERT INTO app_order (
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code,
    source_system,
    source_record_id,
    load_batch_id
)
SELECT
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code,
    'ERP',
    source_record_id,
    batch_id
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

### 12.2. Ghi nhận inserted rows

Trong PL/SQL, đọc SQL%ROWCOUNT ngay sau DML cần đo:

~~~sql
DECLARE
    l_inserted NUMBER;
BEGIN
    INSERT INTO app_order (
        order_id, customer_id, order_date, amount,
        currency_code, source_system, source_record_id, load_batch_id
    )
    SELECT
        order_id, customer_id, order_date, amount,
        currency_code, 'ERP', source_record_id, batch_id
    FROM stg_order_valid
    WHERE batch_id = :batch_id;

    l_inserted := SQL%ROWCOUNT;

    UPDATE load_batch
    SET inserted_rows = l_inserted,
        batch_status = 'APPLIED'
    WHERE batch_id = :batch_id;
END;
/
~~~

SQL%ROWCOUNT phải được đọc ngay sau statement cần đo. Nếu chạy UPDATE metadata rồi mới đọc, giá trị sẽ là số rows của UPDATE metadata chứ không phải INSERT trước đó.

### 12.3. Insert conflict

Nếu một row vi phạm unique constraint, INSERT thông thường có thể thất bại. Có thể:

- Kiểm tra duplicate trước.
- Dùng MERGE nếu business rule là upsert.
- Dùng DML error logging để ghi nhận row errors có thể log.
- Tách insert thành chunk để giới hạn phạm vi retry.

Không catch mọi lỗi rồi bỏ qua. Lỗi hệ thống có thể làm cả statement không hoàn thành.

## 13. MERGE cho upsert

MERGE dùng để insert row mới hoặc update row đã tồn tại theo business key.

### 13.1. Ví dụ

~~~sql
MERGE INTO app_customer t
USING (
    SELECT
        customer_id,
        customer_name,
        email
    FROM stg_customer_valid
    WHERE batch_id = :batch_id
) s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET
        t.customer_name = s.customer_name,
        t.email = s.email
WHEN NOT MATCHED THEN
    INSERT (customer_id, customer_name, email)
    VALUES (s.customer_id, s.customer_name, s.email);
~~~

### 13.2. Nguồn MERGE phải xác định

Nếu source có nhiều rows cùng match một target row, MERGE có thể gặp lỗi không thể update cùng row nhiều lần. Hãy deduplicate source theo business rule trước khi MERGE.

### 13.3. Phân biệt inserted và updated

SQL%ROWCOUNT của MERGE thường cho tổng số rows bị tác động, không tự tách số inserted và updated. Nếu cần hai chỉ số riêng, thiết kế cách đo:

- So sánh source với target trước MERGE trong cùng snapshot/transaction phù hợp.
- Gắn action marker trong staging.
- Dùng output/audit mechanism phù hợp với release.
- Đối soát target sau MERGE theo batch ID và source key.

Không báo inserted = total MERGE rows.

### 13.4. Idempotent MERGE

MERGE có thể giúp chạy lại an toàn nếu:

- Match key ổn định.
- Update semantics xác định.
- Source batch không thay đổi ngoài dự kiến.
- Không ghi lại các side effects ngoài target một cách lặp.
- Có unique constraint bảo vệ business key.

MERGE không tự làm mọi pipeline idempotent. Trigger, audit events, sequence generation và side effects cần được xem xét.

## 14. Direct-path INSERT

Direct-path INSERT là kỹ thuật nạp trực tiếp vào segment, thường dùng cho lượng dữ liệu lớn.

### 14.1. APPEND hint

~~~sql
INSERT /*+ APPEND */ INTO app_order_archive (
    order_id,
    customer_id,
    order_date,
    amount
)
SELECT
    order_id,
    customer_id,
    order_date,
    amount
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

Hint APPEND yêu cầu direct-path insert trong các điều kiện mà Oracle có thể áp dụng. Optimizer có thể bỏ qua hint nếu điều kiện không phù hợp; kiểm tra execution behavior và SQL trace/plan.

### 14.2. Lợi ích

- Có thể giảm một số overhead của conventional insert.
- Có thể tận dụng parallel direct-path load khi workload và cấu hình cho phép.
- Phù hợp với append-oriented bulk load.

### 14.3. Hạn chế

- Có restriction theo object type, constraint, trigger, partitioning và transaction state.
- Direct-path insert có thể ảnh hưởng concurrent access và locking.
- Index maintenance và space usage vẫn cần được tính.
- Một số thao tác đọc/ghi tiếp theo trên cùng object trong transaction có thể bị hạn chế.
- Với direct-path hoặc parallel DML, có thể gặp ORA-12838 nếu truy cập lại object đã được sửa trước commit theo các điều kiện áp dụng.

### 14.4. Transaction boundary

~~~sql
INSERT /*+ APPEND */ INTO app_order_archive
SELECT ...
FROM stg_order_valid
WHERE batch_id = :batch_id;

COMMIT;
~~~

Đừng giả định có thể đọc hoặc sửa ngay cùng table trong cùng transaction sau direct-path/parallel DML. Xác nhận restriction cụ thể và đặt commit boundary phù hợp.

### 14.5. NOLOGGING

Một số bulk-load operation có thể dùng NOLOGGING để giảm redo trong điều kiện cho phép, nhưng điều này ảnh hưởng recoverability và backup strategy. Không bật NOLOGGING chỉ để tăng tốc. DBA cần đánh giá database force logging, Data Guard, backup/recovery và quy trình backup sau load.

### 14.6. Partition exchange

Với data warehouse, có thể nạp vào table/partition staging có cấu trúc tương thích rồi dùng EXCHANGE PARTITION để chuyển dữ liệu vào partition đích. Đây là kỹ thuật metadata-oriented rất nhanh trong workload phù hợp, nhưng cần:

- Cấu trúc cột tương thích.
- Constraint phù hợp và validation đúng.
- Xử lý index/local/global indexes.
- Đúng partition key và data boundaries.
- Quy trình kiểm tra dữ liệu trước exchange.
- Transaction/DDL operational plan.

DDL có implicit commit semantics; không đặt EXCHANGE PARTITION trong một transaction mà kỳ vọng rollback như DML.

## 15. DML error logging với DBMS_ERRLOG

DML error logging cho phép Oracle ghi một số lỗi phát sinh trong từng row vào error logging table, trong khi tiếp tục xử lý các rows khác theo semantics của statement.

### 15.1. Tạo error logging table

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name      => 'APP_ORDER',
        err_log_table_name  => 'ERR$_APP_ORDER',
        skip_unsupported    => TRUE
    );
END;
/
~~~

Tạo bảng một lần cho target table. Nếu target có kiểu dữ liệu không hỗ trợ trong error table, skip_unsupported => TRUE yêu cầu bỏ qua các cột không hỗ trợ. Vì vậy, không giả định error table lưu được mọi cột target.

### 15.2. Các cột hệ thống

Error logging table có các cột metadata như:

| Cột | Ý nghĩa |
| --- | --- |
| ORA_ERR_NUMBER$ | Oracle error number |
| ORA_ERR_MESG$ | Error message |
| ORA_ERR_ROWID$ | Rowid liên quan nếu có |
| ORA_ERR_OPTYP$ | DML operation type |
| ORA_ERR_TAG$ | Tag do ứng dụng truyền vào |

Ngoài ra, bảng có các cột tương ứng với những cột target được hỗ trợ.

### 15.3. INSERT với LOG ERRORS

~~~sql
INSERT INTO app_order (
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code
)
SELECT
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code
FROM stg_order_valid
WHERE batch_id = :batch_id
LOG ERRORS INTO err$_app_order ('BATCH-20261114-0001')
REJECT LIMIT UNLIMITED;
~~~

Tag giúp nhận diện batch trong error table.

### 15.4. Đọc lỗi

~~~sql
SELECT
    ora_err_number$,
    ora_err_mesg$,
    ora_err_optyp$,
    ora_err_tag$,
    order_id,
    customer_id,
    amount
FROM err$_app_order
WHERE ora_err_tag$ = 'BATCH-20261114-0001'
ORDER BY order_id;
~~~

### 15.5. REJECT LIMIT

REJECT LIMIT xác định số lỗi tối đa mà statement cho phép trước khi statement bị kết thúc vì vượt ngưỡng. Có thể dùng số cụ thể hoặc UNLIMITED.

~~~sql
LOG ERRORS INTO err$_app_order ('BATCH-20261114-0001')
REJECT LIMIT 100;
~~~

Chọn reject limit theo business policy. UNLIMITED không có nghĩa job luôn thành công: lỗi không được hỗ trợ bởi error logging, lỗi parse, lỗi privilege, lỗi hệ thống hoặc statement-level failure vẫn có thể làm statement thất bại.

### 15.6. MERGE với LOG ERRORS

~~~sql
MERGE INTO app_customer t
USING stg_customer_valid s
ON (t.customer_id = s.customer_id)
WHEN MATCHED THEN
    UPDATE SET t.customer_name = s.customer_name
WHEN NOT MATCHED THEN
    INSERT (customer_id, customer_name)
    VALUES (s.customer_id, s.customer_name)
LOG ERRORS INTO err$_app_customer ('CUSTOMER-BATCH-01')
REJECT LIMIT UNLIMITED;
~~~

Kiểm tra syntax theo Oracle release và loại DML đang dùng. Error logging không thay thế validation trước khi MERGE.

### 15.7. Những lỗi không nên giả định sẽ được log

DML error logging không xử lý mọi loại lỗi:

- Lỗi cú pháp hoặc parse statement.
- Lỗi thiếu quyền.
- Lỗi kết nối hoặc database instance.
- Lỗi tài nguyên như tablespace/space failure.
- Một số lỗi constraint/deferred constraint và restriction riêng của direct-path/parallel DML.
- Các kiểu dữ liệu không được hỗ trợ trong error table.

Oracle documentation có danh sách các restriction cụ thể. Với mỗi DML pattern, kiểm thử lỗi thực tế trên đúng release, access path và table definition.

### 15.8. Error logging không tự tạo business reject workflow

Error table ghi lỗi DML. Nó không tự biết:

- Source file nào chứa record.
- Dòng nguồn ban đầu.
- Có nên retry record không.
- Lỗi nào cần sửa dữ liệu.
- Batch có được phép partial success không.

Để có lineage, đưa source_record_id/source row number vào target hoặc mapping table, hoặc dùng staging để join lại error record theo business key.

### 15.9. Transaction semantics

Error logging vẫn hoạt động trong ngữ cảnh transaction của DML. Ứng dụng phải xác định commit/rollback policy và kiểm thử trường hợp reject limit bị vượt hoặc statement thất bại. Không coi error table là một hệ thống audit độc lập tự động commit ngoài transaction.

## 16. PL/SQL FORALL và SAVE EXCEPTIONS

FORALL là cơ chế bulk bind trong PL/SQL. Nó gửi các giá trị collection vào DML statement mà không phải chạy một context switch SQL/PLSQL cho từng phần tử như loop DML thông thường.

### 16.1. FORALL cơ bản

~~~sql
DECLARE
    TYPE t_order_ids IS TABLE OF app_order.order_id%TYPE;
    l_order_ids t_order_ids := t_order_ids(1001, 1002, 1003);
BEGIN
    FORALL i IN 1 .. l_order_ids.COUNT
        UPDATE app_order
        SET status = 'READY'
        WHERE order_id = l_order_ids(i);
END;
/
~~~

### 16.2. SAVE EXCEPTIONS

Mặc định, lỗi trong một iteration có thể làm FORALL dừng. SAVE EXCEPTIONS yêu cầu Oracle lưu lỗi của các iteration và tiếp tục các iteration còn lại; sau khi hoàn tất, PL/SQL raise ORA-24381.

### 16.3. Ví dụ đầy đủ

~~~sql
DECLARE
    TYPE t_order_ids IS TABLE OF app_order.order_id%TYPE;
    l_order_ids t_order_ids := t_order_ids(1001, 1002, 1003, 1004);

    e_bulk_errors EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_bulk_errors, -24381);
BEGIN
    FORALL i IN 1 .. l_order_ids.COUNT SAVE EXCEPTIONS
        UPDATE app_order
        SET status = 'READY'
        WHERE order_id = l_order_ids(i);

    DBMS_OUTPUT.PUT_LINE('Bulk DML completed without row errors');

EXCEPTION
    WHEN e_bulk_errors THEN
        DBMS_OUTPUT.PUT_LINE(
            'Bulk errors: ' || SQL%BULK_EXCEPTIONS.COUNT
        );

        FOR i IN 1 .. SQL%BULK_EXCEPTIONS.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(
                'Iteration=' ||
                SQL%BULK_EXCEPTIONS(i).ERROR_INDEX ||
                ', Oracle error=' ||
                SQL%BULK_EXCEPTIONS(i).ERROR_CODE
            );
        END LOOP;
END;
/
~~~

### 16.4. ERROR_INDEX

ERROR_INDEX xác định iteration bị lỗi trong FORALL. Với collection dense và range 1 .. COUNT, có thể map trực tiếp về index collection. Với INDICES OF, VALUES OF hoặc sparse collection, cần map iteration index về source record một cách rõ ràng.

### 16.5. SQL%BULK_ROWCOUNT

SQL%BULK_ROWCOUNT(i) cho biết số rows bị ảnh hưởng bởi iteration i. Nó hữu ích khi mỗi key dự kiến update đúng một row:

- 0 rows: không tìm thấy record.
- 1 row: đúng một record.
- Nhiều rows: điều kiện DML không đủ chọn lọc hoặc nghiệp vụ cho phép nhiều rows.

### 16.6. FORALL không phải SQL*Loader

FORALL phù hợp khi dữ liệu đã ở PL/SQL collections. Nếu nguồn là file lớn, SQL*Loader/external tables có thể phù hợp hơn. Không nạp hàng triệu rows vào collection PL/SQL nếu staging/set-based SQL giải quyết được với ít memory hơn.

## 17. JDBC batch cho nguồn dữ liệu từ Java

Khi dữ liệu được đọc từ API, file stream hoặc message queue trong ứng dụng Java, JDBC batching có thể giảm round trips.

### 17.1. PreparedStatement

~~~java
String sql = """
    INSERT INTO stg_order (
        batch_id, source_row_no, order_id_raw,
        customer_id_raw, order_date_raw, amount_raw, currency_raw
    )
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    int pending = 0;

    for (SourceOrder row : sourceRows) {
        ps.setString(1, batchId);
        ps.setLong(2, row.sourceRowNo());
        ps.setString(3, row.orderId());
        ps.setString(4, row.customerId());
        ps.setString(5, row.orderDate());
        ps.setString(6, row.amount());
        ps.setString(7, row.currency());
        ps.addBatch();
        pending++;

        if (pending == 100) {
            ps.executeBatch();
            ps.clearBatch();
            pending = 0;
        }
    }

    if (pending > 0) {
        ps.executeBatch();
        ps.clearBatch();
    }
}
~~~

Batch size 100 là điểm bắt đầu để benchmark, không phải con số tối ưu cho mọi workload.

### 17.2. Transaction chunk

~~~java
connection.setAutoCommit(false);

try {
    // addBatch/executeBatch cho một chunk
    connection.commit();
} catch (SQLException e) {
    connection.rollback();
    throw e;
}
~~~

Nếu commit mỗi 1.000 rows, mỗi chunk là một transaction riêng. Nếu executeBatch mỗi 100 rows nhưng commit sau 1.000 rows, có 10 JDBC batches trong cùng transaction.

### 17.3. BatchUpdateException

Khi executeBatch lỗi, đọc:

- getUpdateCounts().
- getLargeUpdateCounts() nếu dùng API phù hợp.
- getSQLState().
- getErrorCode().
- getNextException().

JDBC driver có thể dừng hoặc tiếp tục sau lỗi theo behavior được tài liệu hóa. Oracle JDBC standard batching dừng tại operation lỗi và trả counts của các operation thành công trước lỗi. Không giả định driver khác có cùng behavior.

### 17.4. Retry

Không retry cả batch một cách mù quáng. Nếu chunk trước đã commit, retry toàn file có thể tạo duplicate. Dùng batch ID, source key, unique constraint và checkpoint.

### 17.5. JDBC batching không thay validation

Batching chỉ tối ưu cách gửi DML. Nó không tự phân loại dữ liệu sai thành reject rows. Hãy validate trước khi gửi hoặc dùng staging và error logging phía Oracle.

## 18. Phân biệt lỗi dòng với lỗi toàn job

Đây là quyết định quan trọng trong thiết kế pipeline.

### 18.1. Lỗi dữ liệu theo dòng

Ví dụ:

- Ngày không hợp lệ.
- Amount không parse được.
- Thiếu customer ID.
- Foreign key không tồn tại.
- Duplicate business key.
- Giá trị ngoài miền cho phép.

Các lỗi này thường có thể gắn với source record cụ thể và đưa vào reject table.

### 18.2. Lỗi statement/job

Ví dụ:

- SQL syntax sai.
- Thiếu quyền.
- Tablespace hết chỗ.
- Database unavailable.
- Network connection mất.
- Deadlock hoặc resource failure.
- Data file không đọc được.
- Service/instance dừng.

Những lỗi này thường cần dừng hoặc retry cả statement/chunk/job theo recovery policy. Không ghi chúng như thể chỉ có một row dữ liệu sai.

### 18.3. Ma trận xử lý

| Loại lỗi | Hành động |
| --- | --- |
| Validation error | Ghi reject theo source row |
| DML constraint error có thể log | Dùng LOG ERRORS hoặc xử lý exception |
| JDBC batch row error | Đọc BatchUpdateException và update counts |
| PL/SQL FORALL row error | SAVE EXCEPTIONS và SQL%BULK_EXCEPTIONS |
| File parse error | SQL*Loader bad file hoặc external table diagnostics |
| Network/system error | Dừng chunk, rollback nếu có thể, retry theo policy |
| Tablespace/privilege/configuration error | Dừng job, sửa nguyên nhân, không retry liên tục |

## 19. Transaction và chunk design

Batch size và transaction chunk size là hai khái niệm khác nhau.

### 19.1. Batch size

Số rows được gom trong một lần gửi/thực thi, ví dụ:

- JDBC addBatch/executeBatch.
- Một lần bulk operation trong ứng dụng.

### 19.2. Transaction chunk size

Số rows được xử lý trong một transaction trước khi commit.

Ví dụ:

~~~text
File: 1,000,000 rows

Transaction 1: 10 batches x 100 rows = 1,000 rows -> COMMIT
Transaction 2: 10 batches x 100 rows = 1,000 rows -> COMMIT
...
Transaction 1000: 1,000 rows -> COMMIT
~~~

### 19.3. Transaction quá nhỏ

- Tăng commit frequency.
- Tăng log sync/commit overhead.
- Có thể giảm throughput.
- Làm khó đảm bảo atomicity toàn file.

### 19.4. Transaction quá lớn

- Tăng undo/redo pressure.
- Giữ locks lâu hơn.
- Tăng rollback duration.
- Tăng rủi ro mất nhiều tiến độ khi lỗi.
- Tăng thời gian phục hồi.

### 19.5. Chọn chunk size bằng benchmark

Đo:

- Elapsed time.
- Rows per second.
- Commit time.
- Undo/redo generation.
- Memory.
- Lock waits.
- Error rate.
- Rollback time.

Không dùng một chunk size chung cho mọi bảng; row width, index, LOB, constraints và concurrency làm thay đổi kết quả.

### 19.6. Atomic file hay partial acceptance?

Hai chính sách thường gặp:

**Atomic file**

- Một record lỗi làm batch không được công nhận hoàn tất.
- Có thể rollback toàn bộ target changes.
- Sửa file và chạy lại toàn bộ batch.
- Phù hợp với file phải nhất quán toàn bộ theo nghiệp vụ.

**Partial acceptance**

- Rows hợp lệ được apply và commit.
- Rows lỗi được giữ trong reject table.
- Batch có thể ở trạng thái PARTIAL.
- Dòng lỗi được sửa và nạp lại theo quy trình riêng.
- Phù hợp khi nghiệp vụ cho phép xử lý độc lập từng record.

Chính sách phải được quyết định trước khi triển khai. Không để behavior mặc định của SQL*Loader hoặc JDBC driver quyết định business atomicity.

## 20. Idempotency và restart an toàn

Idempotency giúp chạy lại cùng input mà không tạo tác dụng phụ ngoài ý muốn.

### 20.1. Business key

Ví dụ unique key:

~~~sql
ALTER TABLE app_order
ADD CONSTRAINT uq_app_order_source
UNIQUE (source_system, source_record_id);
~~~

Nếu cùng source record được gửi lại, database ngăn duplicate key. Cần quyết định duplicate là reject, ignore hay update.

### 20.2. Batch ID và file checksum

Lưu:

- Source system.
- Source file name.
- File checksum.
- File size.
- Source row count.
- Batch ID.
- Mapping/rule version.

Nếu file cùng tên nhưng checksum khác, đó là input khác. Không chỉ dùng file name để xác định đã nạp.

### 20.3. Checkpoint theo chunk

~~~sql
CREATE TABLE load_checkpoint (
    batch_id       VARCHAR2(40) NOT NULL,
    chunk_no       NUMBER NOT NULL,
    first_row_no   NUMBER,
    last_row_no    NUMBER,
    chunk_status   VARCHAR2(20) NOT NULL,
    committed_at   TIMESTAMP,
    processed_rows NUMBER DEFAULT 0 NOT NULL,
    CONSTRAINT pk_load_checkpoint PRIMARY KEY (batch_id, chunk_no)
);
~~~

Checkpoint chỉ được đánh dấu COMMITTED sau khi dữ liệu của chunk đã commit thành công. Ghi checkpoint và target data trong cùng transaction khi thiết kế cho phép.

### 20.4. Recovery sau crash

Khi job restart:

1. Đọc batch status.
2. Xác định file checksum có giống input trước không.
3. Đọc checkpoint cuối đã commit.
4. Xác định chunk chưa hoàn tất.
5. Đối chiếu target theo batch/source key.
6. Tiếp tục chunk chưa commit.
7. Chạy reconciliation lại trước khi đánh dấu hoàn tất.

### 20.5. Không tin riêng trạng thái application

Process có thể chết sau khi Oracle commit nhưng trước khi ứng dụng cập nhật trạng thái batch. Vì vậy cần đối chiếu checkpoint/target trong database trước khi retry.

### 20.6. Unknown commit outcome

Nếu connection mất ngay sau khi client gửi COMMIT, client có thể không biết commit đã thành công hay chưa. Đừng mặc định rollback đã xảy ra. Kiểm tra batch ID/source key/checkpoint trong database trước khi gửi lại.

## 21. Đối soát số lượng

Đối soát số lượng là bước cơ bản nhưng phải dùng cùng phạm vi dữ liệu và cùng batch ID.

### 21.1. Đếm source/staging

~~~sql
SELECT COUNT(*) AS staged_rows
FROM stg_order
WHERE batch_id = :batch_id;
~~~

### 21.2. Đếm accepted

~~~sql
SELECT COUNT(*) AS valid_rows
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

### 21.3. Đếm rejected theo dòng

Nếu một dòng có thể có nhiều reject reasons, đếm distinct source row:

~~~sql
SELECT COUNT(DISTINCT source_row_no) AS rejected_rows
FROM load_reject
WHERE batch_id = :batch_id;
~~~

Nếu cần đếm tổng số lỗi, dùng COUNT(*) và gọi rõ là reject reasons/error records.

### 21.4. Đếm target rows theo batch

~~~sql
SELECT COUNT(*) AS target_rows
FROM app_order
WHERE load_batch_id = :batch_id;
~~~

Điều này yêu cầu target lưu load_batch_id hoặc có mapping table liên quan.

### 21.5. Công thức kiểm soát

Nếu mọi staged record có đúng một trạng thái cuối:

~~~text
STAGED_ROWS = VALID_ROWS + REJECTED_ROWS
~~~

Nếu có trạng thái duplicate/ignored/deferred riêng:

~~~text
STAGED_ROWS =
    INSERTED_ROWS
  + UPDATED_ROWS
  + UNCHANGED_ROWS
  + REJECTED_ROWS
  + DUPLICATE_IGNORED_ROWS
  + DEFERRED_ROWS
~~~

Phải định nghĩa các nhóm mutually exclusive để không đếm một row ở nhiều nhóm.

## 22. Đối soát tổng tiền và aggregate

Nếu dữ liệu có amount, quantity hoặc balance, so sánh aggregate giữa source, accepted và target.

### 22.1. Tổng amount trong accepted staging

~~~sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount,
    MIN(order_date) AS min_order_date,
    MAX(order_date) AS max_order_date
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

### 22.2. Tổng amount trong target

~~~sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount,
    MIN(order_date) AS min_order_date,
    MAX(order_date) AS max_order_date
FROM app_order
WHERE load_batch_id = :batch_id;
~~~

### 22.3. Group by currency

Không cộng trực tiếp các đồng tiền khác nhau:

~~~sql
SELECT
    currency_code,
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount
FROM app_order
WHERE load_batch_id = :batch_id
GROUP BY currency_code
ORDER BY currency_code;
~~~

Đối soát theo currency để tránh tổng amount vô nghĩa giữa VND, USD và EUR.

### 22.4. Aggregate không chứng minh mọi row đúng

Hai tập dữ liệu có thể có cùng count và SUM nhưng khác record. Aggregate là lớp kiểm tra nhanh; cần thêm key-level reconciliation.

## 23. Đối soát theo khóa nghiệp vụ

### 23.1. Source có nhưng target không có

~~~sql
SELECT
    s.order_id,
    s.source_row_no
FROM stg_order_valid s
LEFT JOIN app_order t
  ON t.order_id = s.order_id
 AND t.load_batch_id = s.batch_id
WHERE s.batch_id = :batch_id
  AND t.order_id IS NULL;
~~~

Đây là source rows chưa tìm thấy ở target theo điều kiện mapping trên.

### 23.2. Target có nhưng source không có

~~~sql
SELECT
    t.order_id
FROM app_order t
LEFT JOIN stg_order_valid s
  ON s.order_id = t.order_id
 AND s.batch_id = t.load_batch_id
WHERE t.load_batch_id = :batch_id
  AND s.order_id IS NULL;
~~~

### 23.3. Cùng key nhưng khác dữ liệu

~~~sql
SELECT
    s.order_id,
    s.amount AS source_amount,
    t.amount AS target_amount,
    s.currency_code AS source_currency,
    t.currency_code AS target_currency
FROM stg_order_valid s
JOIN app_order t
  ON t.order_id = s.order_id
 AND t.load_batch_id = s.batch_id
WHERE s.batch_id = :batch_id
  AND (
      NVL(s.amount, -1) <> NVL(t.amount, -1)
      OR NVL(s.currency_code, '???') <> NVL(t.currency_code, '???')
  );
~~~

Chọn sentinel NVL không thể trùng dữ liệu hợp lệ. Với kiểu dữ liệu phức tạp hoặc null semantics quan trọng, dùng biểu thức so sánh null-safe rõ ràng.

### 23.4. Dùng FULL OUTER JOIN

FULL OUTER JOIN có thể phân loại:

- SOURCE_ONLY.
- TARGET_ONLY.
- MATCHED_EQUAL.
- MATCHED_DIFFERENT.

Đây là cách hữu ích khi cần xuất reconciliation detail cho kiểm toán.

## 24. Hash/checksum và fingerprint

Checksum có thể dùng ở nhiều lớp:

- File checksum để xác định input file.
- Row fingerprint để so sánh một record.
- Partition/batch aggregate fingerprint để phát hiện khác biệt nhanh.

### 24.1. File checksum

Tính SHA-256 ở tầng nhận file và lưu trong load_batch. Nếu file bị thay đổi, checksum khác.

### 24.2. Row fingerprint

Có thể tạo hash từ các trường đã canonicalize:

~~~sql
SELECT
    order_id,
    STANDARD_HASH(
        NVL(TO_CHAR(customer_id), '#NULL#') || '|' ||
        NVL(TO_CHAR(order_date, 'YYYY-MM-DD'), '#NULL#') || '|' ||
        NVL(TO_CHAR(amount, 'FM9999999999990D00',
                    'NLS_NUMERIC_CHARACTERS=''.,'''), '#NULL#') || '|' ||
        NVL(currency_code, '#NULL#'),
        'SHA256'
    ) AS row_hash
FROM stg_order_valid
WHERE batch_id = :batch_id;
~~~

Canonicalization phải thống nhất về:

- Field order.
- Character encoding.
- Date/time zone and format.
- Decimal separator/scale.
- Null representation.
- Whitespace/case normalization.

Nếu không chuẩn hóa giống nhau, cùng một giá trị nghiệp vụ có thể tạo hash khác.

### 24.3. Hash không thay thế so sánh chi tiết

Hash giúp so sánh nhanh nhưng không giải thích field nào khác. Khi phát hiện mismatch, chạy key-level compare và xuất các cột lệch để điều tra.

### 24.4. Hash aggregate

Có thể tạo fingerprint theo partition hoặc batch, nhưng không cộng/ghép hash tùy tiện rồi coi như bằng chứng toán học tuyệt đối. Chọn thuật toán và cách canonicalization rõ ràng, ghi lại version.

## 25. Reconciliation report

Một báo cáo đối soát nên có summary và detail.

### 25.1. Summary

| Chỉ số | Ý nghĩa |
| --- | --- |
| Expected rows | Số dòng theo manifest/source |
| Staged rows | Số dòng đã vào staging |
| Valid rows | Số dòng vượt validation |
| Rejected rows | Số dòng bị từ chối |
| Inserted rows | Số dòng mới được insert |
| Updated rows | Số dòng được update |
| Unchanged rows | Số dòng không đổi theo policy |
| Target rows | Số dòng target gắn với batch |
| Missing rows | Source có nhưng target thiếu |
| Extra rows | Target có nhưng source không có |
| Mismatched rows | Cùng key nhưng khác giá trị |
| Amount variance | Chênh lệch tổng amount |

### 25.2. Detail

Mỗi mismatch nên có:

- Batch ID.
- Source record ID/row number.
- Business key.
- Field name.
- Source value.
- Target value.
- Difference/reason.
- Severity.
- Resolution status.

### 25.3. Ví dụ report SQL

~~~sql
SELECT
    b.batch_id,
    b.expected_rows,
    (SELECT COUNT(*)
       FROM stg_order s
      WHERE s.batch_id = b.batch_id) AS staged_rows,
    (SELECT COUNT(*)
       FROM stg_order_valid v
      WHERE v.batch_id = b.batch_id) AS valid_rows,
    (SELECT COUNT(DISTINCT r.source_row_no)
       FROM load_reject r
      WHERE r.batch_id = b.batch_id) AS rejected_rows,
    (SELECT COUNT(*)
       FROM app_order t
      WHERE t.load_batch_id = b.batch_id) AS target_rows,
    b.batch_status
FROM load_batch b
WHERE b.batch_id = :batch_id;
~~~

Nếu có nhiều loại reject, đảm bảo reject table không ghi duplicate reasons thành duplicate rejected rows trong summary.

## 26. Xử lý lỗi và retry theo từng tầng

### 26.1. File-level reject

Ví dụ:

- File không có header bắt buộc.
- Encoding không hợp lệ.
- Số cột sai cấu trúc.
- Checksum không khớp manifest.
- File bị cắt hoặc thiếu trailer.

File-level reject có thể khiến toàn batch FAILED trước khi tạo staging rows.

### 26.2. Record-level reject

Ví dụ:

- Một record có amount không parse được.
- Customer ID không tồn tại.
- Một business key trùng.

Có thể đưa vào reject table và tiếp tục phần còn lại nếu policy cho phép.

### 26.3. Chunk-level failure

Ví dụ:

- Deadlock.
- Tablespace full.
- Network interruption.
- Statement timeout.

Rollback chunk hiện tại nếu transaction còn hoạt động. Xác định commit outcome trước khi retry.

### 26.4. Job-level failure

Ví dụ:

- Database outage.
- Thiếu quyền.
- Sai schema mapping.
- Thiếu service.
- File store unavailable.

Dừng job, giữ staging/log/checkpoint để điều tra. Không đánh dấu các dòng còn lại là dữ liệu lỗi.

### 26.5. Retry policy

| Lỗi | Retry? | Cách xử lý |
| --- | --- | --- |
| Temporary network error | Có điều kiện | Exponential backoff, xác minh commit outcome |
| Deadlock | Có điều kiện | Rollback transaction, retry business unit |
| Invalid date | Không tự retry | Sửa dữ liệu nguồn hoặc mapping |
| Missing customer | Theo nghiệp vụ | Chờ master data hoặc reject |
| Duplicate source ID | Không mù quáng | Đối chiếu idempotency key |
| Tablespace full | Không ngay lập tức | DBA xử lý capacity rồi mới resume |
| Invalid SQL/privilege | Không | Sửa code/config/permission |

### 26.6. Retry phải có giới hạn

Ghi:

- Attempt number.
- Last error.
- Next retry time.
- Backoff duration.
- Max attempts.
- Final status.

Không retry vô hạn trong vòng lặp nóng.

## 27. Hiệu năng và vận hành

### 27.1. Giảm round trips

Với Java, dùng PreparedStatement batching. Với dữ liệu đã ở Oracle, dùng set-based SQL. Với file lớn, benchmark SQL*Loader/external tables.

### 27.2. Chọn index hợp lý

Index hỗ trợ validation và reconciliation nhưng làm tăng chi phí insert/update. Đánh giá:

- Index cần cho uniqueness/integrity.
- Index dùng để query staging.
- Index có thể tạo sau load trong môi trường phù hợp.
- Global/local indexes với partitioning.

Không drop unique/business constraints chỉ để tăng tốc mà không có lớp bảo vệ thay thế.

### 27.3. Statistics

Sau bulk load, statistics có thể cần được thu thập hoặc cập nhật để optimizer có cardinality phù hợp.

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'APP_ORDER',
        cascade => TRUE
    );
END;
/
~~~

Trong production, dùng owner đúng, estimate/sample phù hợp, partition-level strategy và maintenance window. Không mặc định gather full stats trên bảng rất lớn sau mỗi chunk.

### 27.4. Undo và redo

DML tạo undo/redo theo database configuration. Chunk quá lớn có thể tăng áp lực undo và thời gian rollback. Direct path/NOLOGGING có semantics riêng và phải được DBA đánh giá recovery.

### 27.5. Parallel execution

Parallel load có thể tăng throughput nhưng cũng tăng:

- CPU và I/O.
- TEMP usage.
- Concurrent resource consumption.
- Contention trên target/indexes.
- Complexity của transaction/recovery.

Chỉ bật parallel sau khi đo workload và giới hạn tài nguyên. Kiểm tra DOP thực tế thay vì tin rằng hint luôn được thực thi.

### 27.6. Monitoring

Ghi nhận tối thiểu:

- Batch ID.
- File name/checksum.
- Start/end time.
- Rows read/staged/valid/rejected/applied.
- Throughput.
- Chunk/commit count.
- Error counts theo code.
- Retry count.
- Reconciliation status.

## 28. Bài thực hành tổng hợp

Lab mô phỏng nạp đơn hàng vào Oracle bằng staging-first, validation, reject rows, apply và reconciliation.

### Bước 1 — Tạo target

~~~sql
CREATE TABLE app_order_lab (
    order_id          NUMBER PRIMARY KEY,
    customer_id       NUMBER NOT NULL,
    order_date        DATE NOT NULL,
    amount            NUMBER(15,2) NOT NULL,
    currency_code     VARCHAR2(3) NOT NULL,
    source_record_id  VARCHAR2(100) NOT NULL,
    load_batch_id     VARCHAR2(40) NOT NULL,
    CONSTRAINT uq_order_lab_source
        UNIQUE (source_record_id)
);
~~~

### Bước 2 — Tạo batch table và staging

~~~sql
CREATE TABLE load_batch_lab (
    batch_id       VARCHAR2(40) PRIMARY KEY,
    expected_rows  NUMBER,
    batch_status   VARCHAR2(20),
    created_at     TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE TABLE stg_order_lab (
    batch_id          VARCHAR2(40) NOT NULL,
    source_row_no     NUMBER NOT NULL,
    source_record_id  VARCHAR2(100),
    order_id_raw      VARCHAR2(100),
    customer_id_raw   VARCHAR2(100),
    order_date_raw    VARCHAR2(100),
    amount_raw        VARCHAR2(100),
    currency_raw      VARCHAR2(20),
    CONSTRAINT pk_stg_order_lab
        PRIMARY KEY (batch_id, source_row_no)
);

CREATE TABLE reject_order_lab (
    batch_id       VARCHAR2(40),
    source_row_no  NUMBER,
    error_code     VARCHAR2(100),
    error_message  VARCHAR2(1000),
    raw_order_id   VARCHAR2(100),
    raw_amount     VARCHAR2(100),
    rejected_at    TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

### Bước 3 — Tạo batch

~~~sql
INSERT INTO load_batch_lab(batch_id, expected_rows, batch_status)
VALUES ('LAB-001', 5, 'RECEIVED');

COMMIT;
~~~

### Bước 4 — Nạp raw rows

~~~sql
INSERT INTO stg_order_lab (
    batch_id, source_row_no, source_record_id,
    order_id_raw, customer_id_raw, order_date_raw,
    amount_raw, currency_raw
)
VALUES ('LAB-001', 1, 'SRC-001', '1001', '501', '2026-11-01', '125.50', 'VND');

INSERT INTO stg_order_lab VALUES (
    'LAB-001', 2, 'SRC-002', '1002', '502', '2026-11-02', '240.00', 'VND'
);

INSERT INTO stg_order_lab VALUES (
    'LAB-001', 3, 'SRC-003', '1003', '503', '2026-11-03', 'INVALID', 'VND'
);

INSERT INTO stg_order_lab VALUES (
    'LAB-001', 4, 'SRC-004', '1004', '504', '2026-11-04', '-10.00', 'VND'
);

INSERT INTO stg_order_lab VALUES (
    'LAB-001', 5, 'SRC-005', '1005', '505', 'BAD-DATE', '99.00', 'VND'
);

COMMIT;
~~~

### Bước 5 — Validation

~~~sql
INSERT INTO reject_order_lab (
    batch_id, source_row_no, error_code,
    error_message, raw_order_id, raw_amount
)
SELECT
    batch_id,
    source_row_no,
    CASE
        WHEN VALIDATE_CONVERSION(order_id_raw AS NUMBER) = 0
            THEN 'INVALID_ORDER_ID'
        WHEN VALIDATE_CONVERSION(order_date_raw AS DATE, 'YYYY-MM-DD') = 0
            THEN 'INVALID_ORDER_DATE'
        WHEN VALIDATE_CONVERSION(amount_raw AS NUMBER) = 0
            THEN 'INVALID_AMOUNT'
        WHEN TO_NUMBER(amount_raw DEFAULT NULL ON CONVERSION ERROR) < 0
            THEN 'NEGATIVE_AMOUNT'
        ELSE 'OTHER'
    END,
    'Validation failed',
    order_id_raw,
    amount_raw
FROM stg_order_lab
WHERE batch_id = 'LAB-001'
  AND (
      VALIDATE_CONVERSION(order_id_raw AS NUMBER) = 0
      OR VALIDATE_CONVERSION(order_date_raw AS DATE, 'YYYY-MM-DD') = 0
      OR VALIDATE_CONVERSION(amount_raw AS NUMBER) = 0
      OR (
          VALIDATE_CONVERSION(amount_raw AS NUMBER) = 1
          AND TO_NUMBER(amount_raw) < 0
      )
  );
~~~

Đoạn lab dùng DEFAULT NULL ON CONVERSION ERROR có trong Oracle release hỗ trợ cú pháp này. Có thể bỏ nhánh đó và chỉ dùng VALIDATE_CONVERSION nếu muốn tương thích với môi trường cũ hơn.

### Bước 6 — Nạp accepted rows

~~~sql
INSERT INTO app_order_lab (
    order_id,
    customer_id,
    order_date,
    amount,
    currency_code,
    source_record_id,
    load_batch_id
)
SELECT
    TO_NUMBER(order_id_raw),
    TO_NUMBER(customer_id_raw),
    TO_DATE(order_date_raw, 'YYYY-MM-DD'),
    TO_NUMBER(amount_raw),
    currency_raw,
    source_record_id,
    batch_id
FROM stg_order_lab s
WHERE batch_id = 'LAB-001'
  AND NOT EXISTS (
      SELECT 1
      FROM reject_order_lab r
      WHERE r.batch_id = s.batch_id
        AND r.source_row_no = s.source_row_no
  );

COMMIT;
~~~

### Bước 7 — Đối soát counts

~~~sql
SELECT COUNT(*) AS staged_rows
FROM stg_order_lab
WHERE batch_id = 'LAB-001';

SELECT COUNT(DISTINCT source_row_no) AS rejected_rows
FROM reject_order_lab
WHERE batch_id = 'LAB-001';

SELECT COUNT(*) AS target_rows
FROM app_order_lab
WHERE load_batch_id = 'LAB-001';
~~~

### Bước 8 — Đối soát amount

~~~sql
SELECT
    currency_code,
    COUNT(*) AS row_count,
    SUM(amount) AS total_amount
FROM app_order_lab
WHERE load_batch_id = 'LAB-001'
GROUP BY currency_code;
~~~

### Bước 9 — Kiểm tra source rows chưa vào target

~~~sql
SELECT s.source_row_no, s.source_record_id, s.order_id_raw
FROM stg_order_lab s
LEFT JOIN app_order_lab t
  ON t.source_record_id = s.source_record_id
WHERE s.batch_id = 'LAB-001'
  AND t.source_record_id IS NULL;
~~~

### Bước 10 — Chạy lại batch

Thử chạy lại accepted INSERT. Unique constraint trên source_record_id sẽ ngăn duplicate. Sau đó thiết kế MERGE hoặc skip logic theo chính sách idempotency thay vì bắt lỗi rồi bỏ qua.

## 29. Lỗi thường gặp khi bulk load

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| SQL*Loader rows rejected | Format, conversion, constraint | Đọc log và bad file theo source record |
| SQL*Loader rows discarded | Không thỏa WHEN/discard condition | Xem control file và discard file |
| External table query lỗi | DIRECTORY/file permission/format | Kiểm tra DB server path, grants, access parameters |
| ORA-01722 | Invalid number | Validate conversion và NLS |
| ORA-01861/01843 | Date format/month không hợp lệ | Dùng explicit format mask |
| ORA-00001 | Duplicate key | Kiểm tra source key và unique constraint |
| ORA-02291 | Parent key không tồn tại | Kiểm tra load order/reference data |
| ORA-12838 | Truy cập object sau direct/parallel DML trước commit | Đặt commit boundary theo restriction áp dụng |
| ORA-01555 | Undo không đủ cho consistent read dài | Tối ưu query/transaction và undo policy |
| ORA-01653 | Không extend được table segment | DBA kiểm tra tablespace/datafile |
| ORA-01654 | Không extend được index segment | Kiểm tra index tablespace |
| ORA-00060 | Deadlock | Chuẩn hóa thứ tự lock và transaction |
| BatchUpdateException | Một hoặc nhiều JDBC batch operations lỗi | Đọc update counts và driver behavior |
| ORA-24381 | FORALL SAVE EXCEPTIONS có iteration lỗi | Đọc SQL%BULK_EXCEPTIONS |
| DML error log thiếu row | Lỗi không thuộc loại được log hoặc statement failure | Đọc Oracle restriction và statement error |
| Counts source/target lệch | Batch scope sai, duplicate, reject, commit chưa xong | Đối soát theo batch/source key |
| Retry tạo duplicate | Không có idempotency/checkpoint | Dùng unique business key và xác minh commit outcome |

## 30. Checklist vận hành batch

**Nguồn và lineage**

- Có batch ID duy nhất?
- Có file checksum và source row count?
- Có source record ID/row number?
- File gốc có được giữ bất biến?
- Mapping/rule version có được ghi nhận?

**Staging và validation**

- Raw values có được giữ?
- Batch ID được lọc trong mọi query?
- Conversion có explicit format/NLS?
- Validation có mã lỗi ổn định?
- Một row có thể có nhiều reject reason không?
- Duplicate được xử lý theo business rule?

**Apply**

- Chọn đúng SQL*Loader, external table, set-based SQL, JDBC hoặc FORALL?
- Direct path có restriction nào?
- Có unique constraint bảo vệ business key?
- DML error logging có hỗ trợ lỗi đang quan tâm?
- Batch/chunk/transaction size đã đo?

**Recovery**

- Có checkpoint theo chunk?
- Có idempotency?
- Có xử lý unknown commit outcome?
- Retry có giới hạn/backoff?
- Có phân biệt row-level error với system-level error?

**Reconciliation**

- Source/staging/valid/rejected counts khớp?
- Inserted/updated/unchanged được tách rõ?
- Aggregate được so sánh theo currency/date/partition?
- Có key-level anti-join?
- Có kiểm tra field mismatch?
- Batch chỉ COMPLETED sau khi đối soát đạt?

## 31. Câu hỏi tự kiểm tra

1. Vì sao bulk load cần staging?
2. Batch ID dùng để làm gì?
3. Source row number có vai trò gì?
4. SQL*Loader conventional path khác direct path thế nào?
5. Bad file khác discard file thế nào?
6. External table lưu dữ liệu file ở đâu?
7. DIRECTORY object trỏ tới filesystem của máy nào?
8. Vì sao raw staging nên giữ giá trị dạng text?
9. VALIDATE_CONVERSION giúp giải quyết vấn đề gì?
10. Vì sao không nên dựa vào NLS_DATE_FORMAT mặc định?
11. Structural validation khác business validation thế nào?
12. Vì sao duplicate pre-check không thay unique constraint?
13. Khi nào dùng INSERT ... SELECT?
14. Khi nào dùng MERGE?
15. Vì sao source của MERGE cần deduplicate?
16. APPEND hint liên quan direct-path insert thế nào?
17. ORA-12838 có thể xuất hiện khi nào?
18. Vì sao NOLOGGING cần DBA đánh giá recovery?
19. DBMS_ERRLOG.CREATE_ERROR_LOG tạo gì?
20. ORA_ERR_NUMBER$ và ORA_ERR_TAG$ dùng làm gì?
21. LOG ERRORS và REJECT LIMIT hoạt động ra sao?
22. DML error logging có log được mọi lỗi không?
23. Vì sao error logging table không tự thay thế business reject table?
24. FORALL giảm overhead gì?
25. SAVE EXCEPTIONS xử lý lỗi iteration ra sao?
26. SQL%BULK_EXCEPTIONS.ERROR_INDEX là gì?
27. Batch size khác transaction chunk size thế nào?
28. Atomic file khác partial acceptance thế nào?
29. Vì sao retry toàn file có thể tạo duplicate?
30. Idempotency key nên dựa trên gì?
31. Unknown commit outcome là gì?
32. Vì sao counts phải được đối soát theo batch ID?
33. Vì sao count và SUM giống nhau chưa chứng minh hai tập rows giống nhau?
34. Row fingerprint cần canonicalize những gì?
35. Khi nào batch được phép chuyển COMPLETED?

**Gợi ý trả lời:**

1. Giữ raw input, lineage, validation và recovery tách khỏi target.
2. Định danh một lần nhận/xử lý dữ liệu.
3. Truy ngược record và mapping lỗi về nguồn.
4. Conventional dùng SQL INSERT interface; direct path ghi theo đường nạp trực tiếp và có restriction riêng.
5. Bad là record không load do lỗi; discard là record bị loại theo điều kiện.
6. Dữ liệu vẫn nằm trong file; external table cung cấp SQL interface để đọc.
7. Filesystem của database server.
8. Giữ nguyên biểu diễn nguồn và kiểm soát conversion sau đó.
9. Kiểm tra biểu thức có chuyển đổi được sang kiểu dữ liệu đích.
10. Vì kết quả có thể phụ thuộc session/environment và gây parse sai.
11. Structural kiểm tra format/shape; business validation kiểm tra quy tắc nghiệp vụ.
12. Vì race condition có thể xảy ra giữa pre-check và insert.
13. Khi nguồn đã ở database và có thể xử lý set-based.
14. Khi cần update row tồn tại và insert row mới theo key.
15. Một target row không nên bị source match nhiều lần trong cùng MERGE.
16. APPEND yêu cầu direct-path insert khi điều kiện cho phép.
17. Khi truy cập lại object đã sửa bằng direct/parallel DML trước commit theo restriction áp dụng.
18. Vì redo/recovery/backup behavior có thể thay đổi.
19. Tạo error logging table cho target DML table.
20. Mã Oracle error và batch tag.
21. Ghi các row errors được hỗ trợ vào error table và giới hạn số lỗi cho phép trước khi statement bị dừng.
22. Không.
23. Nó không tự lưu đầy đủ business lineage/reason/retry workflow.
24. SQL/PLSQL context switches cho từng row.
25. Tiếp tục các iteration khác, rồi raise ORA-24381 để báo lỗi đã lưu.
26. Index của iteration bị lỗi trong FORALL.
27. Batch size là số lệnh mỗi lần gửi; transaction chunk size là số rows mỗi transaction commit.
28. Atomic rollback toàn đơn vị; partial acceptance commit rows hợp lệ và giữ reject.
29. Vì các chunk/records trước có thể đã commit.
30. Source system + source record ID hoặc business key ổn định.
31. Client không biết COMMIT đã thành công hay chưa sau khi mất kết nối.
32. Để tránh trộn dữ liệu giữa các lần chạy.
33. Hai tập có thể cùng aggregate nhưng khác record.
34. Thứ tự field, null, encoding, date/time, decimal, whitespace/case.
35. Khi apply, transaction/checkpoint và reconciliation đều đạt policy.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c Utilities — SQL*Loader](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-sql-loader.html): conventional/direct path, control files, log/bad/discard files và load options.
- [Oracle Database 19c Utilities — External Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/sutil/oracle-external-tables.html): ORACLE_LOADER, DIRECTORY, access parameters và reject limit.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ERRLOG](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ERRLOG.html): tạo error logging table.
- [Oracle Database 19c SQL Language Reference — INSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html): INSERT, direct-path insert và error logging clause.
- [Oracle Database 19c SQL Language Reference — MERGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MERGE.html): upsert semantics và error logging.
- [Oracle Database 19c PL/SQL Language Reference — Bulk SQL and Bulk Binding](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/bulk-sql-and-bulk-binding.html): FORALL, SAVE EXCEPTIONS, SQL%BULK_EXCEPTIONS và SQL%BULK_ROWCOUNT.
- [Oracle Database 19c SQL Language Reference — VALIDATE_CONVERSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/VALIDATE_CONVERSION.html): kiểm tra khả năng chuyển đổi dữ liệu.
- [Oracle Database 19c SQL Language Reference — STANDARD_HASH](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/STANDARD_HASH.html): tạo hash/fingerprint từ biểu thức.
- [Oracle Database 19c Administrator's Guide — Managing Tables](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-tables.html): quản lý table, partition và bulk data operations.

**Nguyên tắc cần nhớ:** Nạp dữ liệu lớn nên bắt đầu bằng staging có batch ID và source lineage. Validate trước khi apply, tách row-level rejects khỏi lỗi hệ thống, rồi dùng cơ chế phù hợp: SQL*Loader/external tables cho file, set-based SQL cho dữ liệu trong Oracle, JDBC batching cho nguồn Java và FORALL cho PL/SQL collections. DML error logging giúp giữ một số lỗi theo dòng nhưng không xử lý mọi loại lỗi. Chọn transaction chunk, checkpoint và idempotency trước khi chạy production. Chỉ đánh dấu batch hoàn tất sau khi counts, aggregates và key-level reconciliation đều đạt yêu cầu.
