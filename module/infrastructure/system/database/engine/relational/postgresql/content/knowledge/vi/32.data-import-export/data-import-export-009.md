# Chia lô, kiểm soát giao dịch và tránh tăng WAL đột biến trong PostgreSQL

## 1. Bài toán: nhập một triệu hàng không chỉ là chạy một triệu INSERT

Một hệ thống thương mại điện tử cần nhập đơn hàng, đồng bộ lịch sử tồn kho, sửa dữ liệu cũ hoặc xóa bản ghi hết hạn. Khi dữ liệu còn vài trăm hàng, một câu `INSERT` hoặc `UPDATE` thường hoàn thành nhanh. Nhưng ở mức hàng triệu đến hàng trăm triệu hàng, thiết kế không phù hợp có thể tạo những vấn đề:

- Một transaction giữ row locks lâu, làm giao dịch khác phải chờ.
- WAL (Write-Ahead Log) tăng rất nhanh, làm đĩa `pg_wal` đầy hoặc làm gián đoạn archiving/replication.
- Checkpoint và những lần ghi full-page images (FPI) tạo thêm I/O, khiến độ trễ tăng theo nhịp.
- Replica chậm áp dụng WAL, làm dữ liệu đọc từ replica bị trễ.
- UPDATE/DELETE để lại dead tuples, làm bảng/index phình to và autovacuum khó theo kịp.
- Batch quá nhỏ tạo quá nhiều lần COMMIT, network round trips và fsync.
- Batch quá lớn làm thời gian rollback, recovery và retry trở nên đắt.
- Một file CSV có dòng lỗi khiến cả lệnh COPY thất bại, không có khả năng restart tại một checkpoint nghiệp vụ.
- Job thử lại sau lỗi có thể nhân đôi dữ liệu nếu thiếu khóa duy nhất và idempotency.
- Thao tác “tối ưu” nguy hiểm như tắt `fsync` hoặc `full_page_writes` làm suy giảm khả năng phục hồi dữ liệu.

Vì thế, **chia lô** không chỉ là cắt dữ liệu thành các đoạn có cùng số hàng. Đây là cách **kiểm soát chi phí, tài nguyên, thời gian khóa, WAL, khả năng khôi phục và tính toàn vẹn giao dịch**.

### 1.1. Mục tiêu

Sau bài này, bạn có thể:

1. Mô tả bản chất WAL, thứ tự log trước data pages và vì sao INSERT/UPDATE/DELETE/COPY tạo WAL.
2. Phân biệt transaction với batch, statement, page và checkpoint.
3. Chọn batch theo số hàng, số byte, thời gian thực thi, WAL delta và mức tải thực tế.
4. Viết import CSV qua `COPY`/`\copy`, staging và merge có idempotency.
5. Thiết kế SQL batch UPDATE/DELETE dùng CTE chọn khóa ổn định vì PostgreSQL không hỗ trợ `UPDATE ... LIMIT` trực tiếp.
6. Kiểm soát `BEGIN`, `COMMIT`, `ROLLBACK`, savepoint, autocommit và retry boundaries.
7. Quan sát WAL bằng `pg_current_wal_lsn()`, `pg_wal_lsn_diff()`, `pg_stat_wal` và số liệu liên quan.
8. Hiểu tác động của `full_page_writes`, checkpoint, `wal_compression`, `max_wal_size`, replication slots và archive backlog.
9. Dùng lock/transaction timeouts, MVCC, vacuum và replica-lag monitoring khi chạy job.
10. Phân biệt tối ưu INSERT và DELETE với các lựa chọn `UNLOGGED`, partition detach/drop, indexing và `TRUNCATE`.
11. Thiết kế import có resume checkpoint, bảo toàn nhất quán, tránh xử lý trùng khi worker crash.
12. Thực hành các bài tập có lời giải và xây runbook để vận hành an toàn.

### 1.2. Đối tượng áp dụng

- Nhập dữ liệu từ file CSV, ETL/ELT, migration.
- Backfill cột hoặc chuyển đổi lược đồ theo nhiều lô.
- Xóa retention data hoặc dọn bảng event lớn.
- Đồng bộ dữ liệu từ nguồn ngoài qua staging.
- Sửa dữ liệu sai có kiểm soát.
- Ghi log sự kiện khối lượng lớn.
- Tăng tốc ingest mà vẫn bảo vệ backup/replication.

> **Lưu ý an toàn:** các ví dụ có DML thật chỉ nên chạy trong database thử nghiệm hoặc theo change plan đã được duyệt. Không dùng `DROP/TRUNCATE/ALTER TABLE ... SET UNLOGGED` hoặc sửa thông số durability ở production chỉ vì muốn giảm WAL. Những lệnh giám sát có thể yêu cầu quyền riêng; không tự cấp superuser cho ứng dụng.

---

## 2. Kiến trúc tổng quát: từ input đến commit và replica

~~~mermaid
flowchart TD
    S["File CSV / batch từ ứng dụng"] --> V["Validate đầu vào / chọn khóa nghiệp vụ"]
    V --> B["Lô N hàng hoặc N MiB"]
    B --> T["BEGIN transaction"]
    T --> W["COPY/INSERT/UPDATE/DELETE"]
    W --> L["WAL records + data buffers"]
    L --> C{"Statement thành công?"}
    C -- "Không" --> R["ROLLBACK lô, quarantine/retry"]
    C -- "Có" --> K["COMMIT lô"]
    K --> N["Cập nhật checkpoint ingest"]
    N --> M["Đo WAL bytes, lag, latency, locks"]
    M --> P{"Còn dữ liệu?"}
    P -- "Có" --> B
    P -- "Không" --> E["Đối chiếu count/checksum; hoàn thành"]
    L --> A["WAL archive / physical replication"]
    A --> Q["Replica replay / point-in-time recovery"]
~~~

Sơ đồ chỉ ra các phụ thuộc, nhưng **checkpoint ingest** nên được ghi **cùng transaction với tác động nghiệp vụ** khi cần bảo đảm atomicity. Một ứng dụng ghi database xong, rồi cập nhật vị trí file ở dịch vụ khác không có transaction chung có thể bị lỗi giữa hai bước; cần idempotent keys và reconciliation.

### 2.1. Bốn đại lượng cần tối ưu đồng thời

| Đại lượng | Chọn lô nhỏ có thể gây | Chọn lô lớn có thể gây |
|---|---|---|
| Thông lượng (rows/s) | Nhiều overhead/COMMIT, round trips | Ít overhead nhưng có thể tạo burst I/O |
| Độ trễ và khóa | Dễ nhường tài nguyên giữa các lô | Transaction giữ locks lâu, ảnh hưởng OLTP |
| WAL/replication | Dòng WAL đều hơn | WAL burst lớn, replication lag tăng |
| Retry/khôi phục | Nhiều checkpoints, dễ resume | Rollback/retry hàng khối dữ liệu |

Không có một batch size đúng cho mọi bảng. Bảng có JSONB lớn, nhiều indexes, triggers hoặc foreign keys có WAL và lock behavior khác bảng đơn giản.

### 2.2. Thuật ngữ

- **Batch/lô:** đơn vị xử lý do ứng dụng hoặc job chọn, ví dụ 5.000 rows.
- **Transaction:** đơn vị atomicity mà PostgreSQL COMMIT hoặc ROLLBACK.
- **Statement:** một câu SQL, ví dụ `COPY` hoặc `UPDATE`.
- **Chunk:** lát cắt của nguồn dữ liệu/file/số khóa được xử lý.
- **Checkpoint ingest:** vị trí nghiệp vụ đã xử lý và xác nhận commit, *khác* PostgreSQL database checkpoint.
- **Database checkpoint:** hoạt động của PostgreSQL ghi các dirty pages phù hợp và bảo đảm cơ sở cho crash recovery, liên quan WAL.
- **WAL LSN:** vị trí logic trong chuỗi WAL, dùng đo chênh lệch WAL và replication progress.

---

## 3. WAL là gì?

### 3.1. Write-Ahead Logging

PostgreSQL tuân theo nguyên tắc log thay đổi trước khi trang dữ liệu tương ứng được coi là ghi bền. Khi transaction thay đổi rows, server ghi WAL records mô tả những thay đổi cần cho crash recovery và, khi cấu hình, physical replication/archive.

~~~text
UPDATE / INSERT / DELETE
          |
          v
     Thay đổi trong buffers
          |
          +--> WAL records ghi vào WAL buffers
                       |
                       v
                 WAL được flush theo durability rules
                       |
                       v
                 COMMIT có thể được xác nhận
          |
          +--> Dirty data pages được flush vào data files về sau
~~~

Chi tiết nội bộ phức tạp hơn hình vẽ, nhưng điểm quan trọng là **database không cần flush mọi data page ngay tại COMMIT** để đảm bảo durability theo cấu hình chuẩn: WAL đóng vai trò khôi phục các thay đổi cần thiết.

### 3.2. WAL có vai trò gì?

1. **Crash recovery:** phát lại WAL để khôi phục trạng thái nhất quán sau sự cố.
2. **Physical streaming replication:** primary gửi WAL cho standbys.
3. **Point-in-time recovery:** dùng base backup + WAL archive để khôi phục tới một thời điểm theo khả năng được cấu hình.
4. **Logical decoding/replication:** diễn giải những thay đổi qua logical slots/protocol khi môi trường phù hợp.

WAL không phải “log debug” có thể xóa thủ công cho nhẹ đĩa.

### 3.3. Vì sao một UPDATE một hàng có thể ghi nhiều byte WAL?

WAL có thể bao gồm:

- Record thay đổi heap tuple/page.
- Các thay đổi index cần WAL tùy loại thao tác.
- Full-page image (FPI) ở những điều kiện cần thiết.
- Transaction-related records.
- Ảnh hưởng phụ từ triggers, foreign keys, partition maintenance và các statements phụ.
- Chi phí do HOT/non-HOT updates, page layout và vacuum/freeze.

Vì thế **row count không đủ dự đoán WAL bytes**.

### 3.4. WAL khác data files và archive

| Thành phần | Mục đích |
|---|---|
| `pg_wal` | Khu vực WAL segments đang được PostgreSQL giữ phục vụ recovery/replication/archive |
| Data files | Trạng thái heap/index pages của bảng |
| WAL archive | Bản lưu WAL dùng cho backup/PITR theo cơ chế archiving |
| Replica WAL receive/replay | Theo dõi dữ liệu physical standby đã nhận/phát lại |
| Logical slot | Giữ vị trí WAL cần cho decoding/consumer; có thể gây WAL retention |

Không được **xóa file trong pg_wal bằng tay** vì thấy thư mục đầy. Đó có thể là WAL vẫn cần cho recovery, slots hoặc archive.

### 3.5. WAL và các transaction đã rollback

Những thao tác DML trước ROLLBACK có thể đã phát sinh WAL; rollback làm **logic dữ liệu không commit**, nhưng không làm những byte WAL đã được ghi biến mất. Chạy rồi ROLLBACK một UPDATE lớn **không phải** cách thử miễn phí về disk/WAL load.

---

## 4. Transaction boundaries và batch size

### 4.1. Một transaction khổng lồ

~~~sql
BEGIN;

-- COPY/INSERT một lượng rất lớn dữ liệu
-- UPDATE nhiều triệu rows
-- DELETE nhiều triệu rows

COMMIT;
~~~

Ưu điểm: toàn bộ thay đổi hoặc thành công hoặc rollback. Nhưng trade-offs:

- Giữ transaction và locks lâu.
- Tăng chi phí retry khi có lỗi cuối batch.
- Có thể tăng WAL retention và replica lag.
- UPDATE/DELETE tạo dead tuples cần vacuum sau transaction, không thể được reclaim như thể từng phần đã commit trước đó.
- Nếu job chạy rất lâu, snapshot/transaction age và lock patterns có thể ảnh hưởng hệ thống.
- Không có checkpoint ứng dụng sau mỗi lô.

### 4.2. Nhiều transactions nhỏ hơn

~~~text
Batch 1: BEGIN → DML rows 1..5000 → COMMIT
Batch 2: BEGIN → DML rows 5001..10000 → COMMIT
Batch 3: BEGIN → DML rows 10001..15000 → COMMIT
...
~~~

Ưu điểm: lock lifetime có giới hạn hơn, dễ pause/resume, giảm rollback scope, có cơ hội điều tiết WAL bursts.

Đổi lại, dữ liệu được commit **từng phần**, không còn atomic toàn job. Người đọc có thể thấy trạng thái trung gian. Phải thiết kế publication/cutover hoặc staging phù hợp nếu nghiệp vụ yêu cầu “chỉ công bố khi tất cả xong”.

### 4.3. Batch size có thể đo theo gì?

- Số rows (ví dụ 1.000–10.000).
- Số byte input (ví dụ MiB của CSV, đặc biệt khi rows dài không đều).
- Thời gian chạy một lô (ví dụ mục tiêu vài trăm mili giây đến vài giây tùy SLO).
- WAL bytes sinh ra mỗi lô.
- Mức lock waits, replication lag và p95 latency.
- Tải CPU/I/O trong thời gian job.

Các con số ví dụ **không phải mặc định tối ưu**. Chọn qua benchmark và guardrails thực tế.

### 4.4. Một lô không nhất thiết bằng một câu SQL

Một transaction có thể gồm:

~~~sql
BEGIN;
INSERT INTO staging ...;
INSERT INTO destination ... SELECT ... FROM staging ...;
UPDATE import_progress ...;
COMMIT;
~~~

Khi nhiều bước thuộc **một lô nghiệp vụ**, đặt chúng trong cùng transaction nếu yêu cầu all-or-nothing. Đừng COMMIT sau INSERT destination rồi mới ghi trạng thái đã xử lý nếu điều đó gây retry duplicate.

---

## 5. ACID khi chia lô

### 5.1. Atomicity theo từng lô

Sau khi chia job thành 100 transactions, PostgreSQL chỉ bảo đảm atomicity **mỗi transaction**. Nếu batch 37 lỗi, 36 batch trước đã commit vẫn tồn tại.

Vì vậy job phải hỗ trợ:

- Resume từ checkpoint hợp lệ.
- Idempotent replay.
- Validation cuối job.
- Trạng thái job: `pending`, `running`, `failed`, `complete`.
- Cơ chế cutover an toàn nếu người đọc không được thấy dữ liệu chưa hoàn tất.

### 5.2. Consistency và constraints

Cắt một batch có thể tạm thời để dữ liệu chưa đủ theo nghiệp vụ. Ví dụ nạp orders trước, order_items sau và người dùng đọc thấy đơn chưa có hàng. Nếu không được phép, hãy nạp vào **staging**, rồi publish với transaction/partition swap hoặc trạng thái `dataset_version` ở cuối.

### 5.3. Isolation và concurrency

Trong `READ COMMITTED`, các transactions liên tiếp của job có thể thấy dữ liệu khác nhau vì concurrent writers. Nếu dùng keyset pagination với điều kiện rõ và idempotency, đây có thể là chủ đích. Nếu job cần một snapshot nhất quán toàn bộ dataset, phải xác định isolation/versioning hoặc tạm khóa writers phù hợp; một loạt READ COMMITTED transactions không tự tương đương một snapshot.

### 5.4. Durability

Khi COMMIT được xác nhận theo cấu hình durability, PostgreSQL đảm bảo mức bền dữ liệu tương ứng. Tăng throughput bằng cách thay `synchronous_commit` có trade-off mất những commits gần nhất khi crash. Không tắt durability theo thói quen.

### 5.5. Trạng thái “job complete” nên commit cùng dữ liệu cuối

Trong hệ thống cần đảm bảo cuối job, cân nhắc trạng thái được publish trong transaction sau khi reconciliation hoàn tất. Job metadata phải phản ánh dữ liệu thực tế, không chỉ “đã đọc hết file”.

---

## 6. Cách chọn lô cho INSERT

### 6.1. INSERT từng row, autocommit

Ví dụ khái niệm:

~~~sql
INSERT INTO app.events(event_id, payload) VALUES (1, '{}');
INSERT INTO app.events(event_id, payload) VALUES (2, '{}');
INSERT INTO app.events(event_id, payload) VALUES (3, '{}');
~~~

Nếu mỗi statement commit riêng, network round trips và commit overhead lớn khi có hàng triệu rows.

### 6.2. Multi-row INSERT

~~~sql
INSERT INTO app.events(event_id, payload)
VALUES
  (1, '{"kind":"open"}'),
  (2, '{"kind":"click"}'),
  (3, '{"kind":"close"}');
~~~

Một statement xử lý nhiều rows, giảm số lần gửi SQL. Trong Java, dùng bind parameters/batching API thay vì nối literal values không kiểm soát.

### 6.3. INSERT SELECT theo tập

~~~sql
INSERT INTO app.events_archive(event_id, payload)
SELECT event_id, payload
FROM app.events
WHERE event_id BETWEEN 1000 AND 2000;
~~~

Khi dữ liệu đã nằm trong PostgreSQL, `INSERT ... SELECT` set-based thường tránh phải gửi toàn bộ rows qua application. Nhưng vẫn tạo WAL và tác động indexes/constraints/triggers của destination.

### 6.4. COPY cho bulk ingest

`COPY FROM` là đường nhập bulk được PostgreSQL tối ưu cho nhiều trường hợp. Nó thường tốt hơn gửi một INSERT riêng trên mỗi row, nhất là khi dữ liệu ở file/stream và transformation cần ở SQL có thể làm sau.

**COPY không tự tạo nhiều commits**: một `COPY FROM` là một statement bên trong transaction hiện tại. Nếu muốn commit mỗi chunk, chia file/stream thành nhiều COPY commands hoặc batch SQL dưới transaction boundaries riêng.

### 6.5. Một statement rất lớn vẫn có giới hạn

Multi-row INSERT với hàng trăm nghìn parameters có thể gặp giới hạn driver/protocol, memory, parse overhead hoặc statement size. Không xây một SQL string dài hàng GB; dùng JDBC batch hoặc COPY stream và thử theo kích thước phù hợp.

---

## 7. SQL lab độc lập: schema và dữ liệu mẫu

Các ví dụ sau dùng schema `wal_batch_lab`. Chạy trong database thử nghiệm có quyền CREATE TABLE/SCHEMA. Tên và ID mẫu không phải dữ liệu thực.

### 7.1. Tạo schema

~~~sql
CREATE SCHEMA IF NOT EXISTS wal_batch_lab;
~~~

### 7.2. Bảng đích

~~~sql
CREATE TABLE wal_batch_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    order_status text NOT NULL
      CHECK (order_status IN ('new','paid','cancelled')),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX ix_wal_batch_orders_status_id
  ON wal_batch_lab.orders(order_status,order_id);
~~~

Index status+ID hữu ích cho truy vấn có lọc status và phân trang qua key nhưng làm tăng chi phí ghi cho INSERT/UPDATE một số cột.

### 7.3. Bảng staging

~~~sql
CREATE TABLE wal_batch_lab.order_stage (
    import_id bigint NOT NULL,
    source_row_no bigint NOT NULL,
    order_id bigint,
    customer_id bigint,
    amount numeric(12,2),
    order_status text,
    PRIMARY KEY (import_id, source_row_no)
);
~~~

Các cột nghiệp vụ ở staging cho phép NULL để có thể nhận dữ liệu lỗi và validate trước khi publish. Ràng buộc primary key của staging chỉ ngăn lặp `import_id,source_row_no`; không tự xác nhận `order_id` hợp lệ.

### 7.4. Bảng metadata job

~~~sql
CREATE TABLE wal_batch_lab.import_jobs (
    import_id bigint PRIMARY KEY,
    source_label text NOT NULL,
    last_committed_row bigint NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','running','failed','complete')),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 7.5. Tạo vài hàng dữ liệu

~~~sql
INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
VALUES
    (101,11,120.00,'new'),
    (102,11, 75.50,'paid'),
    (103,12,250.00,'new'),
    (104,13,400.00,'cancelled'),
    (105,13, 90.00,'new'),
    (106,14, 55.00,'new');

INSERT INTO wal_batch_lab.import_jobs(import_id,source_label,status)
VALUES (9001,'orders-2026-11.csv','pending');
~~~

### 7.6. Xem dữ liệu gốc

~~~sql
SELECT order_id,customer_id,amount,order_status
FROM wal_batch_lab.orders
ORDER BY order_id;
~~~

Kỳ vọng 6 rows, với status `new` ở các ID 101,103,105,106.

---

## 8. Thực hành một lô INSERT cùng checkpoint

### 8.1. Dùng transaction rõ ràng

~~~sql
BEGIN;

INSERT INTO wal_batch_lab.order_stage
    (import_id,source_row_no,order_id,customer_id,amount,order_status)
VALUES
    (9001,1,201,21,10.00,'new'),
    (9001,2,202,21,20.00,'new'),
    (9001,3,203,22,30.00,'paid');

UPDATE wal_batch_lab.import_jobs
   SET last_committed_row=3,
       status='running',
       updated_at=clock_timestamp()
 WHERE import_id=9001;

COMMIT;
~~~

Khi COMMIT thành công, cả staging rows và checkpoint trong cùng transaction được lưu. Nếu lỗi trước COMMIT và ROLLBACK, checkpoint không tiến lên và rows không tồn tại.

### 8.2. Verify ngắn sau commit

~~~sql
SELECT import_id,source_row_no,order_id
FROM wal_batch_lab.order_stage
WHERE import_id=9001
ORDER BY source_row_no;

SELECT import_id,last_committed_row,status
FROM wal_batch_lab.import_jobs
WHERE import_id=9001;
~~~

Kỳ vọng 3 rows và `last_committed_row=3`.

### 8.3. Vì sao checkpoint không nên tăng trước khi ghi rows?

Nếu ghi `last_committed_row=3` commit trước, sau đó INSERT rows thất bại, lần chạy sau bỏ qua rows 1..3 và mất dữ liệu. Nếu checkpoint thuộc transaction với rows, lỗi không thể tạo trạng thái “checkpoint đã tiến nhưng rows chưa commit” theo các ràng buộc transaction bình thường.

### 8.4. Nếu nguồn không đánh số row ổn định?

Không dùng offset của file không ổn định làm cursor. Với message streams, có thể dùng source offset/partition và idempotency key. Với file object storage, dùng file checksum/version cùng row number để phân biệt file đã thay đổi. Khi source thay đổi, checkpoint cũ không còn đáng tin.

---

## 9. Import file CSV: COPY và \copy

### 9.1. Server-side COPY

~~~sql
COPY wal_batch_lab.order_stage
    (import_id,source_row_no,order_id,customer_id,amount,order_status)
FROM '/server/data/orders-batch-001.csv'
WITH (FORMAT csv, HEADER true);
~~~

Lệnh này yêu cầu file nằm **trên filesystem server PostgreSQL** và role có quyền đọc file server thích hợp (ví dụ các server-file privileges rất nhạy cảm). Không dùng trên production nếu ứng dụng chỉ có file ở máy client.

### 9.2. Client-side \copy của psql

~~~text
\copy wal_batch_lab.order_stage (import_id,source_row_no,order_id,customer_id,amount,order_status) FROM '/client/data/orders-batch-001.csv' WITH (FORMAT csv, HEADER true)
~~~

`\copy` là **meta-command của psql**, đọc file phía máy chạy psql và truyền qua `COPY FROM STDIN`; không phải SQL độc lập để gửi qua JDBC Statement.

### 9.3. COPY FROM STDIN trong ứng dụng

Client driver có thể hỗ trợ streaming COPY từ InputStream/Reader, ví dụ pgJDBC `CopyManager`. Dùng driver API phù hợp giúp tránh lưu file lớn trên server hoặc gửi triệu INSERT statements.

### 9.4. CSV có HEADER

Ví dụ file:

~~~csv
import_id,source_row_no,order_id,customer_id,amount,order_status
9001,4,204,22,45.00,new
9001,5,205,23,80.50,paid
9001,6,206,24,90.00,new
~~~

`HEADER true` bỏ dòng tiêu đề đầu theo cú pháp CSV COPY. Số cột và thứ tự phải khớp danh sách COPY; CSV quoting và NULL parsing phải cấu hình đúng nếu dữ liệu có commas/quotes/line breaks.

### 9.5. COPY là một statement, không tự chia transactions

~~~sql
BEGIN;
COPY ... FROM STDIN ...;
COMMIT;
~~~

Nếu toàn bộ file truyền bằng một COPY trong một transaction, lỗi giữa file có thể làm statement thất bại và lượng WAL/processing của phần trước vẫn đã tiêu tốn tài nguyên. Muốn restart từng đoạn, chia stream thành nhiều COPY invocations/batches, mỗi batch có transaction và checkpoint phù hợp.

---

## 10. Xử lý lỗi khi COPY

### 10.1. Dữ liệu sai kiểu

Ví dụ input `amount='not-a-number'` với cột numeric có thể làm COPY thất bại. Nếu client không xử lý và transaction vẫn ở failed state, các SQL sau cũng bị lỗi tới khi rollback.

### 10.2. CSV NULL và chuỗi rỗng

CSV có sự khác nhau giữa giá trị rỗng, chuỗi rỗng được quote, NULL marker và tùy chọn COPY:

- `NULL ''` hoặc marker khác theo option.
- `FORCE_NULL` / `FORCE_NOT_NULL` theo cột trong các tình huống hỗ trợ.
- Dấu quote và escape.

Không mặc định chuỗi rỗng có nghĩa số 0; hãy validate business semantics trước khi merge.

### 10.3. Thay vì bỏ qua lỗi âm thầm

Nhiều pipeline dùng staging columns dạng text để nạp raw CSV, sau đó validate và tách hàng lỗi. Điều này giúp biết lý do reject thay vì để một row lỗi phá toàn file. Nhưng staging text không tự giải quyết encoding, CSV quoting, size limits, duplicates hoặc dữ liệu độc hại; vẫn phải giới hạn và xác minh.

### 10.4. Chọn cách phát hiện lỗi theo phiên bản

Một số PostgreSQL versions mới hơn có thêm COPY options để kiểm soát lỗi conversion trong phạm vi hỗ trợ. Tính năng này **phụ thuộc version** và không thay quy tắc constraints/triggers của mọi trường hợp. Bài giữ mô hình portable: nạp vào staging, kiểm tra và báo lỗi/loại bỏ qua SQL có kiểm soát.

### 10.5. Lỗi COPY có thể để lại dead tuples

COPY FROM đã insert một số rows trước khi gặp lỗi; nếu statement bị rollback, những tuples chưa commit không trở thành dữ liệu hợp lệ nhưng có thể vẫn chiếm không gian vật lý cho tới khi VACUUM reclaim theo cơ chế PostgreSQL. Với file quá lớn và nhiều lỗi, chi phí dung lượng/I/O có thể đáng kể dù không có rows được commit.

### 10.6. Mẫu vận hành

1. Chia input thành chunks có boundaries kiểm chứng được.
2. COPY chunk vào staging, trong transaction.
3. Validate rows và quyết định reject/quarantine.
4. Merge batch hoặc chỉ publish nếu mọi rows đạt policy.
5. Commit dữ liệu và checkpoint cùng transaction.
6. Khi lỗi: rollback chunk, log error class/sanitized row reference, sửa source hoặc quarantine và tiếp tục theo contract.
7. Reconcile tổng accepted/rejected/duplicate counts.

---

## 11. Import vào staging rồi merge: vì sao thường an toàn hơn?

### 11.1. Tách validate khỏi dữ liệu production

Dữ liệu đầu vào có thể chứa:

- Customer ID không tồn tại.
- Order ID trùng.
- Amount âm.
- Status không nằm trong danh sách hợp lệ.
- Dữ liệu được nạp lại do retry.
- Hàng sai encoding/kiểu.
- Dòng duplicate trong cùng một file.

Nếu COPY trực tiếp vào production table có nhiều indexes/triggers/constraints, một lỗi hoặc duplicate có thể làm rollback cả statement. Staging cho phép nhìn và sửa policy trước khi publish.

### 11.2. Query phát hiện hàng lỗi

~~~sql
SELECT source_row_no,order_id,customer_id,amount,order_status,
       CASE
         WHEN order_id IS NULL THEN 'missing_order_id'
         WHEN customer_id IS NULL THEN 'missing_customer_id'
         WHEN amount IS NULL OR amount < 0 THEN 'invalid_amount'
         WHEN order_status NOT IN ('new','paid','cancelled')
              OR order_status IS NULL THEN 'invalid_status'
         ELSE 'valid'
       END AS validation_status
FROM wal_batch_lab.order_stage
WHERE import_id=9001
ORDER BY source_row_no;
~~~

Do `order_stage` có typed numeric, file values không parse được numeric vẫn làm COPY fail trước khi có row để validate. Với raw malformed text cần một raw-text staging table riêng trước khi cast.

### 11.3. Merge bằng INSERT ... ON CONFLICT

~~~sql
INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
SELECT s.order_id,s.customer_id,s.amount,s.order_status
FROM wal_batch_lab.order_stage AS s
WHERE s.import_id=9001
  AND s.order_id IS NOT NULL
  AND s.customer_id IS NOT NULL
  AND s.amount >= 0
  AND s.order_status IN ('new','paid','cancelled')
ON CONFLICT (order_id) DO NOTHING;
~~~

`ON CONFLICT DO NOTHING` làm operation có tính retry-safe đối với duplicate PK, **nhưng có thể che dữ liệu cùng ID mà payload khác nhau**. Với hệ thống tài chính hoặc đồng bộ trạng thái, phải so sánh payload/version và không coi mọi conflict là duplicate hợp lệ.

### 11.4. Bẫy UPSERT cùng ID trong một batch

`INSERT ... ON CONFLICT DO UPDATE` có thể báo lỗi nếu một statement muốn tác động **cùng destination row nhiều lần** do source có duplicate keys. Trước merge, phải quy định chọn phiên bản nào bằng `DISTINCT ON ... ORDER BY` hoặc aggregation/ranking rõ ràng.

### 11.5. Đảm bảo batch không làm sai thứ tự thay đổi

Nếu source có nhiều events của cùng order, cách chọn latest phải dựa trên monotonic source sequence/business version, không chỉ `source_row_no` nếu data có thể đến ngoài thứ tự. Một unconditional UPSERT có thể ghi đè trạng thái mới bằng bản cũ.

---

## 12. Định lượng batch size và WAL budget

### 12.1. Không có công thức cố định cho mọi bảng

Batch “5.000 hàng” có thể tạo:

- Vài MB WAL cho rows nhỏ, ít indexes.
- Hàng chục hoặc hàng trăm MB WAL nếu JSONB lớn, updates nhiều indexes, full-page images hoặc triggers đổ thêm dữ liệu.

Do đó chọn batch bằng thực nghiệm, rồi xây kiểm soát theo **row count + time + bytes/replica lag**.

### 12.2. Bảng policy minh họa

| Mức | Mục tiêu ví dụ | Giải thích |
|---|---|---|
| Thăm dò | 500 rows/batch | Đo WAL/latency đầu tiên |
| Tải nhẹ | 2.000 rows/batch | Thử khả năng đáp ứng SLO |
| Tải trung bình | 5.000 rows/batch | Cân bằng throughput/checkpoints |
| Tải lớn | 10.000 rows/batch | Chỉ dùng nếu metrics vẫn trong giới hạn |
| Quá tải | Giảm batch hoặc tạm dừng | Khi replica lag, WAL/disk/locks vượt ngưỡng |

Các ngưỡng là **ví dụ**, không phải cấu hình production cần copy. Kích thước phù hợp phải chọn trên workload và SLA thực tế.

### 12.3. Không chỉ nhìn rows/s

Một job đạt 100.000 rows/s nhưng làm p99 API latency tăng từ 100ms lên 3s và replication lag tới 15 phút chưa chắc tốt. Đặt budget cho toàn hệ thống, không tối ưu riêng số rows được nạp.

### 12.4. Một batch có thể chứa nhiều giao dịch nhỏ?

Có, nhưng khi gọi “batch” cần nói rõ scope. Trong tài liệu này ưu tiên **một lô logic = một transaction commit** để có checkpoint đơn giản. Nếu phải split một lô lớn thành nhiều transactions, metadata cần phản ánh chi tiết để resume không nhân đôi hoặc bỏ sót.

---

## 13. Đo WAL bằng LSN: pg_current_wal_lsn()

### 13.1. LSN là gì?

**Log Sequence Number (LSN)** là vị trí logic trong luồng WAL của PostgreSQL, thường hiển thị dạng hex như:

~~~text
0/16B6C50
0/16C4200
~~~

LSN không phải số bytes đơn giản hoặc timestamp. PostgreSQL có hàm `pg_wal_lsn_diff(lsn1,lsn2)` để tính khoảng cách giữa hai vị trí WAL, đơn vị **byte**.

### 13.2. Đo trước và sau một lô

Mở session giám sát riêng hoặc thực thi khi không còn transaction chưa commit:

~~~sql
SELECT pg_current_wal_lsn() AS wal_before;
~~~

Chạy một batch và **COMMIT**:

~~~sql
BEGIN;

INSERT INTO wal_batch_lab.orders
  (order_id,customer_id,amount,order_status)
SELECT
  100000 + g,
  1000 + g % 200,
  ((g % 5000) + 1)::numeric / 10,
  'new'
FROM generate_series(1,2000) AS g
ON CONFLICT (order_id) DO NOTHING;

COMMIT;
~~~

Sau đó:

~~~sql
SELECT pg_current_wal_lsn() AS wal_after;
~~~

Lấy hai LSN thực tế và tính:

~~~sql
SELECT pg_wal_lsn_diff(
    '0/16C4200'::pg_lsn,
    '0/16B6C50'::pg_lsn
) AS wal_bytes;
~~~

Hai LSN ở ví dụ cuối là **giá trị giả để minh họa**, không phải output phải giống trên máy của bạn. Hãy thay bằng kết quả quan sát thực.

### 13.3. LSN delta đo gì?

Chênh lệch LSN phản ánh lượng WAL được phát sinh giữa hai mốc trong **WAL stream toàn cluster**, có thể gồm transactions của các sessions khác và hoạt động background. Đây không phải số WAL độc quyền của batch nếu DB còn workload đồng thời.

### 13.4. Mốc WAL nào phù hợp?

PostgreSQL có các hàm như:

- `pg_current_wal_lsn()`: vị trí WAL đã được ghi (written) theo semantics của hàm.
- `pg_current_wal_insert_lsn()`: vị trí WAL được insert vào WAL buffers.
- `pg_current_wal_flush_lsn()`: vị trí WAL được flush theo trạng thái hiện tại.

Để có ước lượng dễ giải thích, đo **trước batch, COMMIT, sau batch** và ghi rõ đó là delta cluster-wide theo loại LSN đã chọn. Không trộn insert LSN với flush LSN rồi suy ra chính xác WAL sinh bởi batch.

### 13.5. Transaction đang mở và LSN

Nếu bạn đo `pg_current_wal_lsn()` khi transaction còn mở, nó có thể chưa bao gồm mọi WAL bạn muốn gán cho một **committed** batch, và việc COMMIT có thể tạo thêm WAL records. Để so sánh các batches đã commit, chọn mốc sau khi COMMIT, trong điều kiện background workload tương đối ổn định.

### 13.6. Chuyển byte sang MiB

~~~sql
SELECT
    pg_wal_lsn_diff('0/16C4200'::pg_lsn,
                    '0/16B6C50'::pg_lsn)
      / 1024 / 1024 AS wal_mib;
~~~

Nếu dữ liệu thực cho WAL bytes là `52,428,800` thì WAL khoảng **50 MiB** (1 MiB = 1,048,576 bytes).

---

## 14. Đo bằng pg_stat_wal

### 14.1. WAL statistics

Trên các PostgreSQL versions hiện đại, `pg_stat_wal` cung cấp một số counters, ví dụ:

~~~sql
SELECT
    wal_records,
    wal_fpi,
    pg_size_pretty(wal_bytes) AS wal_bytes_pretty,
    wal_write,
    wal_sync,
    stats_reset
FROM pg_stat_wal;
~~~

Các cột, thời điểm cập nhật, cách snapshot thống kê và quyền truy cập có thể phụ thuộc major version. Nếu server không có view/cột này, xem tài liệu phiên bản thay vì đoán rằng thông tin đều giống nhau.

### 14.2. wal_bytes và wal_fpi

- **`wal_bytes`:** lượng byte WAL được thống kê phát sinh kể từ khi counters được reset theo semantics PostgreSQL.
- **`wal_fpi`:** lượng full-page images được ghi trong WAL.
- **`wal_records`:** số WAL records, không phải số SQL statements.

`wal_bytes` thường là tổng theo server, không tự phân nhóm theo table hoặc application. Không đọc một lần rồi gọi đó là “WAL của import_job=9001”.

### 14.3. Đo delta

Ghi lại counters trước và sau batch ở hai mốc có ý nghĩa:

~~~text
Before: wal_bytes = X
After:  wal_bytes = Y
Delta ≈ Y - X
~~~

Nhưng phải xét `stats_reset`: nếu counters bị reset giữa hai mốc, delta không còn hợp lệ. Cùng lúc các sessions khác có thể tạo WAL.

### 14.4. Thống kê có thể có độ trễ

Statistics được thu thập và hiển thị theo cơ chế server, có thể có độ trễ/caching nhất định. Không tạo controller “giảm batch khi wal_bytes chưa tăng sau 1ms” dựa trên một sample quá nhỏ.

### 14.5. pg_stat_wal vs LSN

| Công cụ | Ưu điểm | Giới hạn |
|---|---|---|
| LSN diff | Đo khoảng vị trí WAL giữa hai mốc | Bao gồm workload cùng cluster |
| `pg_stat_wal.wal_bytes` delta | Thống kê bytes/WAL records/FPI | Counters global, có reset/delay |
| WAL directory size | Quan sát disk pressure | Không đồng nhất lượng WAL phát sinh |
| `pg_stat_replication` | Quan sát sender và replica lag | Không trực tiếp là WAL bytes sinh ra |
| `pg_stat_archiver` | Quan sát archive success/failure | Không đo duy nhất import volume |

Nên kết hợp thay vì dùng một chỉ số làm chân lý.

---

## 15. pg_wal disk usage: sinh WAL không đồng nghĩa giữ WAL

### 15.1. WAL phát sinh và WAL giữ lại

Hai hiện tượng khác nhau:

1. **WAL generation rate:** số bytes WAL/giây do workload ghi.
2. **WAL retention:** lượng WAL segments server phải giữ để checkpoint recovery, archiving, replication slots hoặc các điều kiện khác.

Một job có thể tạo WAL nhanh nhưng archiving/replay theo kịp nên `pg_wal` ổn định. Hoặc job tạo WAL vừa phải nhưng replica/slot không tiêu thụ nên WAL retained tăng tới đầy đĩa.

### 15.2. max_wal_size không phải giới hạn cứng tuyệt đối

`max_wal_size` là mốc mục tiêu cho checkpoints/WAL handling, không phải “quota đảm bảo `pg_wal` luôn dưới X GB”. WAL có thể giữ vượt mốc do replication slots, WAL archiving bị tắc, `wal_keep_size`, hoạt động recovery hoặc các điều kiện khác.

### 15.3. Không xóa WAL files bằng tay

Nếu thấy `pg_wal` chiếm đĩa, không xóa files theo timestamp/segment name vì có thể phá crash recovery, replica hoặc PITR chain.

Điều tra:

- WAL generation rate.
- `pg_stat_archiver`.
- Replication slots và `restart_lsn`.
- Replica replay/receive lag.
- Checkpoint frequency.
- Backup/archiving trạng thái.
- Tình trạng đĩa thực tế và growth dự kiến.

### 15.4. Đo lượng WAL files hiện tại

PostgreSQL có các hàm quản trị/kiểm tra WAL directory với quyền phù hợp, và OS metrics có thể theo dõi filesystem `pg_wal`. Không grant quyền đọc file hệ thống cho application chỉ để lấy một con số dashboard; ưu tiên monitoring agent/role phù hợp.

### 15.5. WAL segments tái sử dụng

PostgreSQL có thể recycle/reuse WAL segments thay vì tạo/xóa liên tục. Vì vậy số lượng file và dung lượng thư mục trong một snapshot không phải lượng WAL phát sinh trong khoảng thời gian đó.

---

## 16. Checkpoint, full-page writes và WAL spikes

### 16.1. Database checkpoint làm gì?

Checkpoint tiến hành ghi dữ liệu dirty buffers và cung cấp điểm tham chiếu crash recovery. Các cấu hình liên quan:

~~~sql
SHOW checkpoint_timeout;
SHOW max_wal_size;
SHOW min_wal_size;
SHOW checkpoint_completion_target;
SHOW full_page_writes;
SHOW wal_compression;
~~~

Giá trị mặc định có thể khác giữa PostgreSQL versions và deployment/provider. Không copy một cấu hình từ blog cũ mà không đo.

### 16.2. Vì sao checkpoint gây nhịp WAL khác nhau?

Với `full_page_writes=on` theo cấu hình thông thường, lần sửa đầu tiên của một trang sau checkpoint có thể dẫn tới ghi full-page image trong WAL (trong những trường hợp phù hợp), bảo vệ chống partial page writes. Sau checkpoint, workload touching nhiều pages có thể làm FPI tăng mạnh.

### 16.3. FPI không chỉ là dữ liệu row

Một trang PostgreSQL thường 8 KiB ở nhiều builds phổ biến; full-page images làm WAL có thể tăng đáng kể so với chỉ record delta. WAL compression và hole-removal có thể làm kích thước ảnh WAL thấp hơn nguyên trang theo cấu hình và dữ liệu.

### 16.4. Không tắt full_page_writes để “tiết kiệm WAL”

`full_page_writes` bảo vệ crash recovery khi có torn-page writes. Tắt tùy tiện có thể làm hỏng khả năng recovery sau sự cố. Đây là setting liên quan an toàn dữ liệu; không phải nút điều chỉnh batch throughput thông thường.

### 16.5. wal_compression

`wal_compression` có thể nén full-page images trong WAL và giảm bytes ở workload phù hợp, đổi lại CPU cost. Tùy version/build có các thuật toán nén được hỗ trợ; không khẳng định chọn cùng một thuật toán cho mọi deployment.

Cần đo trên workload cụ thể: dung lượng giảm bao nhiêu, CPU tăng bao nhiêu, replica/recovery overhead ra sao.

### 16.6. Checkpoint quá thường xuyên

Nếu checkpoints bị kích hoạt liên tục do WAL growth, I/O data-page write và FPI patterns có thể làm throughput biến thiên. Tăng `max_wal_size` trong ngân sách disk phù hợp có thể giảm frequent requested checkpoints, nhưng **không chữa được WAL retention vô hạn do replication slot stuck**.

### 16.7. Checkpoint_completion_target

Tham số ảnh hưởng pacing checkpoint writes để giảm burst trong điều kiện phù hợp. Không dùng một giá trị ngẫu nhiên mà không đo storage latency, writeback và checkpoint timings.

### 16.8. PostgreSQL version differences

Monitoring checkpoint có thể nằm ở `pg_stat_bgwriter` trên một số versions, hoặc `pg_stat_checkpointer` trên phiên bản mới. Không viết dashboard cứng vào một view/cột chưa xác minh phiên bản.

---

## 17. Chia lô UPDATE: PostgreSQL không có UPDATE ... LIMIT trực tiếp

### 17.1. Cú pháp tưởng đúng nhưng không hợp lệ

~~~sql
-- SAI trên PostgreSQL:
UPDATE wal_batch_lab.orders
SET order_status='paid'
WHERE order_status='new'
LIMIT 2;
~~~

`UPDATE` PostgreSQL không cung cấp trực tiếp `LIMIT` theo cú pháp đó. Cần chọn một tập khóa trước, rồi UPDATE.

### 17.2. CTE chọn khóa theo thứ tự ổn định

~~~sql
WITH todo AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 2
)
UPDATE wal_batch_lab.orders AS o
   SET order_status='paid',
       updated_at=clock_timestamp()
  FROM todo AS t
 WHERE o.order_id=t.order_id
RETURNING o.order_id, o.order_status;
~~~

Với dữ liệu gốc, đợt đầu chọn hai ID `101` và `103`. Khi chạy tiếp, `WHERE order_status='new'` lọc lại danh sách còn lại.

### 17.3. Vì sao cần ORDER BY?

`LIMIT 2` không `ORDER BY` cho phép planner chọn hai rows tùy ý, làm progress khó dự đoán. Một primary key ổn định giúp trace và resume theo business key.

### 17.4. Batch UPDATE tạo WAL đáng kể

Ngoài heap updates, index trên `order_status` có thể phải cập nhật, và page images/visibility có thể ảnh hưởng WAL. Không suy mỗi row đổi một byte status chỉ ghi vài byte WAL.

### 17.5. “Updated 2 rows” không bằng “hai row khác trước”

Nếu UPDATE SET col=col, PostgreSQL vẫn có thể xử lý tuple update và phát sinh WAL/row versions; việc có thay đổi giá trị không phải điều kiện mặc định để bỏ UPDATE. Thêm predicate `IS DISTINCT FROM` khi business chỉ cần cập nhật giá trị thực sự đổi.

### 17.6. Một lô một transaction

Chạy mỗi CTE UPDATE với autocommit hoặc explicit `BEGIN/COMMIT` cho một lô; nếu nhiều statements cùng lô, dùng transaction tường minh. Đừng bọc **toàn vòng lặp hàng trăm lô** trong một transaction duy nhất rồi cho rằng đã giảm lock lifetime.

---

## 18. Batch UPDATE có thể chạy song song với SKIP LOCKED

### 18.1. Worker claim pattern

Khi nhiều workers cùng xử lý một queue/table, cần tránh cùng chọn một row. Có thể dùng `FOR UPDATE SKIP LOCKED` trong CTE:

~~~sql
WITH todo AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE wal_batch_lab.orders AS o
   SET order_status='paid',
       updated_at=clock_timestamp()
  FROM todo AS t
 WHERE o.order_id=t.order_id
   AND o.order_status='new'
RETURNING o.order_id;
~~~

### 18.2. SKIP LOCKED có ý nghĩa gì?

Rows đang bị transaction khác giữ lock phù hợp có thể bị **bỏ qua** thay vì chờ. Hữu ích cho concurrent job workers, nhưng có thể trả tập dữ liệu **không nhất quán theo một snapshot tổng thể**, nên không phù hợp cho mọi loại báo cáo hoặc tính tổng.

### 18.3. Không suy 0 rows nghĩa job đã xong

Nếu worker không nhận row vì tất cả rows còn lại đang bị khóa bởi workers khác, kết quả 0 **không chứng minh** hết việc. Cần phối hợp trạng thái job, retry/poll hoặc query reconciliation sau khi các workers hoàn tất.

### 18.4. Mỗi worker phải COMMIT nhanh

`FOR UPDATE SKIP LOCKED` giữ row locks đến transaction end. Nếu worker claim 2 rows rồi chờ API 2 phút trước COMMIT, locks vẫn bị giữ. Tách thao tác external khỏi transaction bằng outbox khi có thể.

### 18.5. Starvation và fairness

Rows liên tục bị khóa có thể bị skip nhiều lần. Nếu phải đảm bảo mọi row được xử lý, có reconciliation sweep/không SKIP LOCKED ở pha cuối hoặc điều phối retries có giới hạn.

### 18.6. Không dùng SKIP LOCKED để “sửa” deadlock không rõ nguyên nhân

SKIP LOCKED phù hợp patterns kiểu task queue. Nó không thay lock ordering, indexes hoặc transaction design trên workflow yêu cầu cập nhật một tập đầy đủ.

---

## 19. Xóa dữ liệu theo từng lô

### 19.1. Một DELETE khổng lồ

~~~sql
DELETE FROM wal_batch_lab.orders
WHERE order_status='cancelled';
~~~

Nếu bảng lớn, câu này có thể giữ transaction lâu, tạo nhiều dead tuples/WAL, làm replicas lag. Với vài hàng ở lab thì không đáng kể; vấn đề xuất hiện ở quy mô lớn.

### 19.2. CTE key-based DELETE

~~~sql
WITH doomed AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='cancelled'
    ORDER BY order_id
    LIMIT 1000
)
DELETE FROM wal_batch_lab.orders AS o
USING doomed AS d
WHERE o.order_id=d.order_id
RETURNING o.order_id;
~~~

Nếu chọn theo timestamp retention, cần index/query phù hợp và tie-breaker theo PK.

### 19.3. Khi nào dừng?

Không chỉ lặp “đến khi không có rows được DELETE” nếu concurrent locks/changes có thể làm kết quả biến thiên. Đối với task batch đơn worker không SKIP LOCKED, việc 0 rows thường biểu thị không còn match tại thời điểm statement; với concurrent ingest/worker cần cơ chế job cutoff/reconciliation.

### 19.4. DELETE và VACUUM

DELETE đánh dấu row versions không còn live theo MVCC khi an toàn với snapshots, **không thu nhỏ ngay file table**. Autovacuum/VACUUM thường reclaim không gian cho reuse, nhưng không nhất thiết trả dung lượng disk về OS.

### 19.5. Partition retention

Nếu dữ liệu retention được phân vùng theo ngày/tháng, việc detach/drop **một partition cũ** thường rẻ hơn xóa hàng triệu rows bằng DELETE, với caveats về locks, constraints, dependencies, policies và việc thay đổi/đánh rơi cả partition.

Không đưa lời khuyên `DROP PARTITION` chung nếu cần giữ một phần dữ liệu trong partition hoặc cần audit per-row DELETE triggers.

### 19.6. TRUNCATE khác DELETE

`TRUNCATE` nhanh hơn DELETE toàn bảng trong nhiều trường hợp nhưng có semantics khác: statement-level TRUNCATE triggers, locking, identity/cascade options, không tương đương FK/audit row semantics. Nó cũng có thể tạo WAL metadata và chịu transaction rules; **không coi là “zero WAL”**.

---

## 20. Keyset pagination tránh OFFSET lớn

### 20.1. OFFSET có thể trở nên đắt

~~~sql
SELECT order_id
FROM wal_batch_lab.orders
ORDER BY order_id
LIMIT 1000 OFFSET 5000000;
~~~

PostgreSQL thường phải xử lý/bỏ qua nhiều rows trước khi trả batch, khiến chi phí tăng theo offset. Nếu data đang đổi, OFFSET cũng có thể gây bỏ sót/trùng do rows chèn/xóa giữa các lần phân trang.

### 20.2. Keyset theo last committed key

~~~sql
SELECT order_id
FROM wal_batch_lab.orders
WHERE order_id > 100000
ORDER BY order_id
LIMIT 1000;
~~~

Sau lô, lưu largest key đã xử lý để đọc lô tiếp theo. Đây là cơ chế “tiến theo khóa”, không phải offset của vị trí vật lý.

### 20.3. Nếu khóa không liên tục

Không cần các ID liên tục. `WHERE order_id > last_id` xử lý gaps bình thường. Nhưng cần một key monotonic/stable theo logic batch. Nếu khóa có thể thay hoặc hàng mới được chèn với ID nhỏ hơn last_id, chúng có thể bị bỏ qua.

### 20.4. Đồng bộ source có insert concurrent

Nếu job cần xử lý **một ảnh chụp cố định** của data tại thời điểm bắt đầu, keyset paging qua nhiều READ COMMITTED transactions không bảo đảm snapshot cố định; có thể cần watermark, cutoff timestamp, source version hoặc isolation/snapshot design thích hợp.

### 20.5. Keyset ORDER BY composite

Nếu sắp theo `(created_at, order_id)`:

~~~sql
WHERE (created_at,order_id) > ($1,$2)
ORDER BY created_at,order_id
LIMIT 1000;
~~~

Tuple comparison đòi các kiểu và NULL behavior phù hợp. Để tránh ambiguity, nên đảm bảo cặp khóa không NULL và duy nhất/ổn định.

---

## 21. Tách lô đọc (read batch) và lô ghi (write batch)

### 21.1. Không nhất thiết cùng kích thước

Một importer có thể đọc file thành các chunks 1 MiB, chuyển thành 2.000 validated rows rồi ghi transaction theo 2.000 rows. Nếu rows dài hoặc có JSON lớn, batch theo bytes nên ưu tiên hơn batch theo số hàng cố định.

### 21.2. Backpressure

Khi downstream DB chậm, producer không nên tiếp tục đọc/hàng đợi vô hạn làm tăng RAM và độ trễ. Một pipeline tốt có bounded queue và policy chờ/giảm tốc:

~~~text
Producer đọc file
     |
     v
Bounded queue [size max]
     |
     v
Workers nạp batches
     |
     +--> Nếu WAL/disk/lag vượt budget: pause/slow
     |
     +--> Khi khỏe lại: resume có giới hạn
~~~

### 21.3. Kịch bản lỗi giữa lô

- Trước transaction: có thể retry.
- Trong transaction trước COMMIT: rollback toàn lô, retry với idempotency.
- Sau COMMIT trước xác nhận application: **commit outcome có thể chưa rõ**; dùng checkpoint/database uniqueness để đối chiếu trước khi retry.
- Sau checkpoint external service: cần reconciliation giữa hai systems.

### 21.4. Nên giữ “committed watermark” trong DB

Một table progress có `import_id` và `last_committed_row` giúp kiểm soát resume. Nhưng nếu có nhiều workers ghi cùng import, phải thiết kế partitioned ranges, claim semantics và monotonic progress; một watermark đơn không đủ khi batch 3 xong trước batch 2.

---

## 22. JDBC batch insert và autoCommit

### 22.1. Statement batching

Trong Java, `PreparedStatement.addBatch()` và `executeBatch()` giảm overhead per-row:

~~~java
String sql =
    "INSERT INTO wal_batch_lab.orders " +
    "(order_id, customer_id, amount, order_status) " +
    "VALUES (?, ?, ?, ?) " +
    "ON CONFLICT (order_id) DO NOTHING";

connection.setAutoCommit(false);
try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (Order order : batch) {
        ps.setLong(1, order.id());
        ps.setLong(2, order.customerId());
        ps.setBigDecimal(3, order.amount());
        ps.setString(4, order.status());
        ps.addBatch();
    }

    ps.executeBatch();
    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
~~~

Đây là ví dụ logic cần cấu trúc `Order`, imports và Connection management phù hợp, không phải source file Java chạy độc lập. Khi lỗi, app phải đóng/trả connection đúng, kiểm tra transaction state và xử lý retry.

### 22.2. executeBatch không bắt buộc một SQL statement

Driver có thể gửi batch thành nhiều SQL operations; `executeBatch()` không đảm bảo **một** SQL statement hoặc **một** database transaction nếu autoCommit/settings không đúng.

### 22.3. rewriteBatchedInserts

pgJDBC có option `reWriteBatchedInserts` (tên/casing theo docs driver) có thể gộp những INSERT tương thích để giảm round trips. Nó có giới hạn theo SQL shape, RETURNING, conflicts và driver version; benchmark thay vì coi bật option luôn tốt.

### 22.4. Batch update counts

`executeBatch()` trả về mảng update counts hoặc các giá trị đặc biệt theo JDBC API. Với `ON CONFLICT DO NOTHING`, một câu INSERT có thể tác động 0 rows; đừng mặc định update count luôn bằng số entries đã gửi.

### 22.5. Mẫu transaction scope đúng

Trong môi trường có connection pool/framework quản lý transaction, gọi `connection.setAutoCommit(false)` và `commit()` phải tuân thủ contract; không tự commit một connection đang thuộc Spring @Transactional mà không kiểm soát.

### 22.6. Không build một chuỗi SQL bằng input không kiểm soát

Dùng bind parameters; batching không thay SQL injection prevention. Dù batch lớn có thể dùng COPY, input values vẫn phải được encode/quote theo CSV/protocol chuẩn thay vì nối thô.

---

## 23. Kiểm soát COMMIT trong psql, ứng dụng và procedure

### 23.1. psql autocommit mặc định

Trong `psql`, khi không ở explicit transaction block và autocommit đang bật theo cách thông thường, mỗi SQL statement thành công được thực thi trong implicit transaction và commit theo semantics của server/client.

Nếu chạy:

~~~sql
INSERT INTO wal_batch_lab.orders (...) VALUES (...);
INSERT INTO wal_batch_lab.orders (...) VALUES (...);
~~~

bạn có thể đang tạo **hai transactions riêng**, không phải một batch atomic.

### 23.2. Explicit BEGIN/COMMIT

~~~sql
BEGIN;

INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
VALUES (301,31,30.00,'new');

INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
VALUES (302,31,60.00,'paid');

COMMIT;
~~~

Hai statements thuộc cùng một transaction. Nếu statement thứ hai lỗi, transaction có thể vào aborted state; phải rollback hoặc xử lý bằng savepoint trước khi có thể hoàn tất theo ý định.

### 23.3. Một vòng lặp bên trong DO không tự commit sau mỗi iteration

~~~sql
DO $$
DECLARE
    i integer;
BEGIN
    FOR i IN 1..100 LOOP
        INSERT INTO wal_batch_lab.orders
            (order_id,customer_id,amount,order_status)
        VALUES
            (400000+i,44,1.00,'new')
        ON CONFLICT (order_id) DO NOTHING;
    END LOOP;
END $$;
~~~

Đây vẫn có thể là **một statement DO** chạy trong một transaction. Số iterations không bằng số commits. Muốn chia transactions, client nên gửi nhiều statements theo batch boundaries rõ hoặc dùng transaction control trong procedure/DO chỉ ở các ngữ cảnh được PostgreSQL cho phép.

### 23.4. Stored function không thể tự COMMIT tùy ý

Function PL/pgSQL được gọi từ một SQL statement bình thường **không được** tự gọi `COMMIT` hay `ROLLBACK` để chia lô như procedure có transaction control trong ngữ cảnh hợp lệ.

Nếu job đang dùng `SELECT process_everything()` và function loop hàng triệu rows, đừng tưởng thêm `COMMIT` sau mỗi 1.000 rows vào function sẽ hoạt động.

### 23.5. Stored procedure có transaction control với điều kiện

PostgreSQL hỗ trợ `CALL` procedure và transaction control trong những trường hợp cụ thể: `CALL` được gọi ở top-level hoặc một chuỗi `CALL/DO` cho phép, không nằm bên trong một transaction block do client mở, và không có rào cản như exception block/subtransaction hay các hạn chế tương ứng.

Ví dụ khái niệm:

~~~sql
CREATE OR REPLACE PROCEDURE wal_batch_lab.demo_commit()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO wal_batch_lab.orders
        (order_id,customer_id,amount,order_status)
    VALUES (500001,50,5.00,'new')
    ON CONFLICT (order_id) DO NOTHING;

    COMMIT;
END;
$$;
~~~

Khi gọi `CALL wal_batch_lab.demo_commit();` ở top level phù hợp, procedure có thể thực thi transaction control. **Không gọi dưới `BEGIN; CALL ...; COMMIT;` rồi mong COMMIT bên trong procedure luôn hợp lệ**.

Một số procedure attributes như `SECURITY DEFINER` hoặc `SET` clauses có hạn chế transaction control. Với mục tiêu vận hành dễ kiểm soát, **client-side batch transactions thường dễ quản trị hơn** một procedure với COMMIT nội bộ.

### 23.6. Exception block và subtransaction

PL/pgSQL `EXCEPTION` block có cơ chế subtransaction. Không được kết thúc transaction ngay trong block đang chứa exception handler theo hạn chế của PostgreSQL. Nếu cần retry từng batch, để caller xử lý hoặc tổ chức transaction boundaries đúng thay vì dùng exception block làm “transaction riêng”.

### 23.7. Savepoints

~~~sql
BEGIN;
SAVEPOINT before_batch;

-- Chạy một lô SQL có thể bị lỗi.

-- Khi có lỗi có thể xử lý:
ROLLBACK TO SAVEPOINT before_batch;

-- Các thao tác tiếp theo nếu contract cho phép.
COMMIT;
~~~

Savepoint cho rollback một phần **trong cùng transaction**, không giải phóng mọi transaction-scope resources như COMMIT toàn bộ và không biến batch thành một committed unit độc lập. Nó không phải giải pháp giảm WAL retention của một transaction kéo dài hàng giờ.

---

## 24. Retry lô và xử lý commit outcome không rõ

### 24.1. Lỗi trước COMMIT

Nếu database trả error và transaction đã rollback chắc chắn, app có thể retry batch sau khi phân loại lỗi và sửa/đợi điều kiện phù hợp.

Ví dụ:

- `40001` serialization_failure → thường retry **toàn transaction**.
- `40P01` deadlock_detected → thường retry transaction với backoff.
- `23505` unique_violation → có thể là data conflict, không tự retry vô hạn.
- `23514` check_violation → nguồn input/logic sai, thường cần quarantine/fix.
- Disk full → phải xử lý dung lượng/WAL/retention trước khi retry.

### 24.2. Mất kết nối tại thời điểm COMMIT

Client gửi COMMIT, server có thể đã commit nhưng response bị mất. Lúc này **không được** suy đơn giản “transaction chưa chạy”. Với batch import, dùng keys/metadata đã commit để kiểm tra:

~~~sql
SELECT import_id,last_committed_row,status
FROM wal_batch_lab.import_jobs
WHERE import_id=9001;
~~~

Nếu batch commit atomically với checkpoint, trạng thái này hỗ trợ quyết định resume. Nếu checkpoint không tồn tại nhưng data đã commit do thiết kế tách transaction, sẽ có inconsistency cần reconcile.

### 24.3. Idempotency key và unique constraint

Ví dụ staging dùng `PRIMARY KEY(import_id,source_row_no)`. Khi retry cùng source row, có thể dùng:

~~~sql
INSERT INTO wal_batch_lab.order_stage
    (import_id,source_row_no,order_id,customer_id,amount,order_status)
VALUES (9001,7,207,25,10.00,'new')
ON CONFLICT (import_id,source_row_no) DO NOTHING;
~~~

Nhưng nếu source row 7 có payload khác lần trước, `DO NOTHING` có thể che drift. Cần source version/checksum hoặc compare payload trước khi coi retry là idempotent.

### 24.4. Retry không có điểm dừng

Một importer retry mỗi 100 ms khi DB disk full có thể làm cluster quá tải thêm. Sử dụng exponential backoff, jitter, max attempts, circuit breaker và human alert khi lỗi không phục hồi.

### 24.5. Resume qua nhiều workers

Nếu nhiều workers xử lý ranges không theo thứ tự, chỉ lưu `last_committed_row=100000` vì một worker xong range cao nhất có thể khiến bỏ qua ranges chưa xong ở giữa. Cần lưu **completed ranges** hoặc một watermark chỉ tiến khi mọi ranges trước đó đã hoàn tất.

---

## 25. WAL và replication lag

### 25.1. Primary tạo WAL, standby nhận/phát lại

Một primary có thể tạo WAL nhanh hơn tốc độ network/standby ghi/replay. Khi job tạo WAL burst, physical replicas có thể tụt lại, ảnh hưởng:

- Độ mới dữ liệu đọc từ replica.
- Khả năng failover theo RPO mục tiêu.
- Disk pressure do cần giữ WAL.
- I/O/CPU trên standby.
- Thời gian catch-up sau job.

### 25.2. Các LSN quan trọng

Trên primary, `pg_stat_replication` có các trường liên quan vị trí:

- `sent_lsn`: WAL đã được gửi tới standby.
- `write_lsn`: standby đã ghi WAL theo thông tin sender nhận.
- `flush_lsn`: standby đã flush WAL.
- `replay_lsn`: standby đã replay WAL.
- `write_lag`, `flush_lag`, `replay_lag`: các ước lượng thời gian có semantics riêng theo replication status.

### 25.3. Query trên primary

~~~sql
SELECT
    application_name,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    write_lag,
    flush_lag,
    replay_lag
FROM pg_stat_replication;
~~~

Nếu không có replica trực tiếp/streaming connection được quan sát, view có thể không có rows. Không suy “replication lag=0” từ **không có row** nếu môi trường được kỳ vọng có standby.

### 25.4. Ước lượng chênh lệch WAL bytes

~~~sql
SELECT
    application_name,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)::bigint
    ) AS approx_replay_bytes_behind
FROM pg_stat_replication
WHERE replay_lsn IS NOT NULL;
~~~

Đây là khoảng cách theo WAL stream, **không phải** số business rows bị trễ và không hoàn toàn tương đương thời gian replication lag. Query đo chênh lệch tới current WAL position trong khi workload có thể tiếp tục thay đổi.

### 25.5. Kiểm tra từ standby

Trên physical standby, các hàm như:

~~~sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp() AS last_replay_commit_timestamp;
~~~

`pg_last_xact_replay_timestamp()` có thể NULL hoặc cũ khi không có write transactions; không lấy chênh lệch clock làm chỉ số lag tuyệt đối khi primary hoàn toàn nhàn rỗi.

### 25.6. Replica lag threshold để điều tiết batch

Một batch controller có thể:

- Giảm số rows/batch khi replay bytes lag tăng.
- Giảm số workers đồng thời.
- Tạm dừng ngắn để standby catch up.
- Báo lỗi nếu lag/disk vượt ngưỡng nghiêm trọng.
- Tiếp tục với mức nhỏ khi lag giảm bền vững.

Chọn thresholds dựa trên RPO/RTO và workload; không copy “lag > 1 GiB thì sleep 1s” cho mọi hệ thống.

### 25.7. Synchronous replication

Nếu synchronous standby được cấu hình, commit latency có thể phụ thuộc mức xác nhận từ standby theo `synchronous_commit` và synchronous replication settings. Batch lớn vẫn có thể tạo I/O pressure; không suy “có sync standby” đồng nghĩa không bao giờ có replica lag hoặc không bị mất dữ liệu ở mọi failure scenarios.

---

## 26. Replication slots giữ WAL

### 26.1. Slot dùng để làm gì?

Physical/logical replication slots giúp PostgreSQL giữ đủ WAL cần thiết cho consumer/standby theo vị trí. Khi consumer chậm hoặc offline, primary có thể phải giữ WAL lâu hơn.

### 26.2. Kiểm tra slots

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn,
    wal_status
FROM pg_replication_slots;
~~~

Một số cột như `wal_status` có thể khác giữa PostgreSQL versions. `confirmed_flush_lsn` chủ yếu có ý nghĩa với logical slots, không tự có trên physical slot.

### 26.3. Ước lượng backlog từng slot

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    pg_size_pretty(
        pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint
    ) AS wal_retained_from_restart
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
~~~

Đây là chênh lệch vị trí tính toán; nhiều slots/other retention conditions tương tác, nên **không cộng đơn giản mọi slot backlog** để ra dung lượng pg_wal chính xác.

### 26.4. max_slot_wal_keep_size

Một số PostgreSQL versions hỗ trợ giới hạn WAL retention của replication slots qua `max_slot_wal_keep_size`. Giới hạn này có semantics và thời điểm enforce riêng; đặt thấp có thể khiến standby/consumer không catch up được nếu thiếu WAL và phải reinitialize.

Không đặt nó chỉ để che sự cố consumer lâu ngày không hoạt động. Cần theo dõi slot health và có recovery plan.

### 26.5. “Slot inactive” không luôn nên drop

Một logical replication slot inactive có thể thuộc một connector tạm ngừng vì bảo trì; drop có thể khiến consumer mất continuity. Trước khi drop slot:

1. Xác định owner/consumer.
2. Xác minh state và mục tiêu replication.
3. Kiểm tra backlog/dung lượng.
4. Chọn biện pháp resume, resync hoặc drop theo runbook được duyệt.

### 26.6. Batch ingest và slot backlog

Khi importer ghi WAL 200 MiB/s còn logical consumer giải mã được 20 MiB/s, backlog có thể tăng khoảng 180 MiB/s trong thời gian dài. Chỉ giảm batch size mà giữ tổng throughput như cũ chưa chắc giảm backlog; có thể phải giảm ingest **rate** hoặc nâng năng lực consumer.

---

## 27. WAL archive và PITR

### 27.1. Tại sao có archiving?

Với `archive_mode` và `archive_command` hoặc phương án tương đương, WAL segments được archive để hỗ trợ backup/PITR. Nếu archiving bị lỗi, PostgreSQL có thể giữ segments cần archive, góp phần tăng disk usage.

### 27.2. Xem cấu hình

~~~sql
SHOW archive_mode;
SHOW archive_command;
SHOW wal_level;
~~~

Một số managed services ẩn hoặc quản lý các setting này qua provider; không cố sửa bằng superuser giả định.

### 27.3. pg_stat_archiver

~~~sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
~~~

Không kết luận archive đang khỏe chỉ vì `archived_count` lớn. Hãy xem thời điểm archived gần đây, failed counts, backlog và hệ thống archive destination. Khi database nhàn rỗi, việc không có WAL segment mới để archive có thể hợp lệ; phải đối chiếu WAL generation.

### 27.4. Archive backlog và import

Một job xuất 500 GiB WAL trong vài giờ có thể vượt throughput của object storage/archive pipeline, làm retained WAL tăng. Trước migration, ước lượng bytes/WAL từ lab và đảm bảo archive bandwidth, disk headroom và backup/recovery objectives.

### 27.5. wal_level không phải nút “tắt log khi import”

`wal_level` có các mức theo khả năng replication/logical decoding. Hạ tùy tiện có thể phá replication/backups hoặc cần restart; không dùng để né WAL nếu production yêu cầu PITR/replicas.

### 27.6. Tránh phá recovery chain

Không xóa thủ công archived WAL chưa hết retention hoặc ép cleanup không hiểu recovery dependencies. Đưa việc dọn WAL archive vào backup retention policy được kiểm tra khả năng restore, không phải một cron xóa file theo size.

---

## 28. MVCC, dead tuples và VACUUM khi UPDATE/DELETE hàng loạt

### 28.1. PostgreSQL UPDATE thường tạo row version mới

Theo MVCC, UPDATE tạo phiên bản row mới và phiên bản cũ có thể trở thành dead khi không còn transaction nào cần nhìn thấy. DELETE cũng làm row không còn visible với transactions tương ứng, nhưng không ngay lập tức thu hẹp data file.

### 28.2. Batch giúp gì?

Chia transactions giúp giới hạn lock duration và giúp các phiên bản cũ trở nên có thể reclaim dần theo vòng đời transactions. Tuy nhiên tổng số row versions bị UPDATE/DELETE vẫn cần storage/reclamation; batch **không** biến UPDATE thành in-place overwrite zero-WAL.

### 28.3. HOT updates

Một số UPDATE có thể là **HOT (Heap-Only Tuple)** khi những điều kiện thích hợp về index involvement và page space được thỏa. HOT có thể giảm nhu cầu cập nhật indexes. Nhưng không phải cứ chỉ UPDATE một cột không index là chắc chắn HOT: page có thể thiếu chỗ, các indexes có expressions/predicates và cơ chế khác có thể làm HOT không khả thi.

### 28.4. Chỉ số dead tuples

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    last_autovacuum,
    last_analyze
FROM pg_stat_user_tables
WHERE schemaname='wal_batch_lab'
ORDER BY relname;
~~~

Đây là estimates/statistics, không phải precise count tại một snapshot MVCC. Các cột tùy phiên bản; nếu thiếu, xem docs của version.

### 28.5. Vacuum và analyze

Sau bulk changes, có thể cần:

~~~sql
VACUUM (ANALYZE) wal_batch_lab.orders;
~~~

Chạy khi có quyền và trong maintenance window phù hợp. `VACUUM` thông thường giúp reclaim dead tuple space để reuse và cập nhật visibility; `ANALYZE` cập nhật planner statistics. Không tự ép `VACUUM FULL` sau mọi batch: nó rewrite table, cần locks nghiêm ngặt và có chi phí disk/WAL lớn.

### 28.6. Autovacuum không phải optional “tối ưu”

Autovacuum rất quan trọng cho bloat control và transaction ID wraparound prevention. Không disable autovacuum toàn cluster để tránh I/O trong lúc import nếu chưa có kế hoạch đặc biệt bảo vệ hệ thống. Cần quan sát backlog và tune phù hợp.

### 28.7. Index bloat

UPDATE indexed columns hoặc DELETE nhiều rows làm indexes cần maintenance và có thể gây bloat. Reindex có trade-offs lock/disk/WAL và phương án `REINDEX CONCURRENTLY` trong điều kiện hỗ trợ. Không chạy reindex hàng loạt chỉ vì WAL đang tăng mà không kiểm tra nguyên nhân.

---

## 29. Indexes, constraints, triggers và write amplification

### 29.1. Mỗi index đều có chi phí ghi

Khi INSERT rows mới, indexes trên bảng có thể phải thêm entries. Khi UPDATE key/indexed columns, indexes có thể cần thay đổi. Khi DELETE, dead index tuples cần cleanup.

Bảng có 12 indexes thường có chi phí ingest khác một bảng chỉ có primary key, dù rows giống hệt.

### 29.2. Có nên drop indexes để load nhanh?

Chỉ trong những tình huống bulk load được kiểm soát kỹ và sau khi xác định:

- Có traffic đọc/ghi đồng thời hay không.
- Index nào phục vụ UNIQUE/PK/constraint.
- Có thể build lại index trong thời gian/đĩa/WAL budget không.
- DDL locks và downtime chấp nhận được không.
- Khi build index xong có đủ WAL/archive throughput không.
- Có backup/rollback plan không.

**Không tự drop PK/UNIQUE indexes hoặc tắt FK** chỉ để giảm thời gian ingest. Điều đó có thể cho data invalid đi vào bảng.

### 29.3. Rebuild index cũng tạo I/O và WAL

Giảm WAL trong lúc COPY bằng cách trì hoãn index build không đồng nghĩa tổng chi phí biến mất; việc tạo index sau có thể tạo burst mới. Đo cả pipeline, không chỉ giai đoạn COPY.

### 29.4. Triggers có thể nhân số writes

Một INSERT vào bảng nghiệp vụ có thể gọi trigger ghi audit, cập nhật bảng tổng hợp hoặc outbox. Nếu mỗi source row tạo thêm ba DML statements, WAL/locks thực tế khác xa một INSERT đơn.

### 29.5. Foreign keys

FK checks cần indexes thích hợp trên cột tham chiếu trong nhiều workloads; khi bulk load dữ liệu quan hệ, nên nạp theo thứ tự dependencies hoặc staging/publish có constraints chứ không bỏ FK vĩnh viễn.

### 29.6. Batch size và lock contention

Khi nhiều import workers cùng INSERT/UPSERT lên hot unique keys hoặc cùng update aggregate rows, lock contention có thể lớn dù số rows mỗi lô nhỏ. Giảm concurrency hoặc partition work theo key có thể hữu ích hơn chỉ giảm batch size.

---

## 30. UNLOGGED và TEMP: giảm WAL nhưng đổi durability contract

### 30.1. UNLOGGED table

~~~sql
CREATE UNLOGGED TABLE wal_batch_lab.raw_stage_unlogged (
    source_row_no bigint,
    raw_payload text
);
~~~

UNLOGGED table có thể giảm WAL cho **dữ liệu bảng** trong một số workload, nhưng có trade-offs lớn:

- Không có cùng crash safety như logged table; sau crash/unclean shutdown dữ liệu có thể bị truncate.
- Không được replicate vật lý theo cách logged data được replay lên standbys.
- Indexes của unlogged table cũng theo đặc tính unlogged.
- Metadata và các hoạt động liên quan vẫn có thể tạo WAL; đừng gọi là “hoàn toàn zero WAL”.
- Không phù hợp làm nơi lưu checkpoint import quan trọng hoặc dữ liệu nghiệp vụ duy nhất.

### 30.2. Khi nào UNLOGGED hợp lý?

Một raw staging cache có thể được tạo lại hoàn toàn từ file nguồn đã lưu bền, không cần đọc trên replica và có runbook recovery rõ. Khi crash, job nạp lại staging; destination logged và checkpoint authoritative vẫn bảo đảm correctness.

### 30.3. Khi nào không hợp lý?

- Bảng payment/order nghiệp vụ.
- Bảng import_progress là nguồn sự thật duy nhất cho resume.
- Bảng cần physical standby đọc cùng dữ liệu.
- Hệ thống có RPO zero hoặc không thể reload từ nguồn.
- Job chạy ngoài kiểm soát, crash dẫn tới mất dữ liệu không thể tái tạo.

### 30.4. TEMP table

~~~sql
CREATE TEMP TABLE temp_stage (
    order_id bigint,
    amount numeric(12,2)
) ON COMMIT DROP;
~~~

Temp tables sống theo session/transaction tùy ON COMMIT, có logging/durability behavior khác bảng thường. Chúng có thể hữu ích cho dữ liệu trung gian nhỏ, nhưng không tự làm lô DML destination bớt WAL; temp table còn chịu memory/disk, pooling và session state constraints.

### 30.5. Không chuyển bảng production sang UNLOGGED tùy tiện

`ALTER TABLE ... SET UNLOGGED` hoặc đổi loggedness là operation có hệ quả lớn về rewrite/locking/durability/replication theo version. Không dùng như một nút tạm để làm import nhanh mà không được phê duyệt.

---

## 31. synchronous_commit và durability trade-off

### 31.1. Tên dễ hiểu sai

`synchronous_commit` điều khiển lúc nào một COMMIT được xem là hoàn tất theo policy và synchronous replication settings. `synchronous_commit=off` có thể giảm commit latency cho workload chấp nhận mất một số transactions gần đây nếu server crash.

### 31.2. Không phải “tắt WAL”

Ngay cả khi `synchronous_commit=off`, PostgreSQL vẫn ghi WAL theo semantics của nó; điều thay đổi là bảo đảm thời điểm flush/acknowledge COMMIT. Không dùng setting này để giải quyết WAL disk full.

### 31.3. Có thể dùng cho dữ liệu tái tạo?

Một ingest temporary/test workload có thể chấp nhận rủi ro durability thấp hơn khi tất cả dữ liệu có thể reload và policy cho phép. Nhưng phải hiểu failure model, khả năng mất những commits gần nhất, consistency của side effects và cách resume.

### 31.4. Không áp dụng cho financial transactions tùy tiện

Với money movement, order confirmation hoặc dữ liệu có yêu cầu durability chặt, thay synchronous_commit phải có review của DBA, bảo mật và business owners. Tăng thông lượng không biện minh cho mất dữ liệu bất ngờ.

### 31.5. fsync và full_page_writes

`fsync=off` và `full_page_writes=off` có hậu quả crash-recovery nghiêm trọng. Không đề xuất làm thay đổi tạm ở production chỉ để xóa WAL spikes. Điều tiết batch, index/triggers, checkpoint tuning và năng lực archiving/replica thường là các lựa chọn an toàn hơn để xem xét đầu tiên.

---

## 32. Adaptive batching và rate limiting

### 32.1. Không cố giữ rows/s tối đa

Một controller có thể chọn batch theo tình trạng DB:

~~~text
Bắt đầu N=1.000 rows, concurrency=2
          |
          v
Thực hiện batch + COMMIT
          |
          v
Đo latency, WAL delta, replica lag, disk, locks
          |
          +-- Healthy trong nhiều chu kỳ: tăng N nhẹ hoặc workers
          |
          +-- Gần ngưỡng: giữ N, giảm concurrency nếu cần
          |
          +-- Vượt ngưỡng: giảm N / pause / backoff
          |
          +-- Lỗi nghiêm trọng: stop, alert, resume theo checkpoint
~~~

### 32.2. Những tín hiệu tốt

- p95/p99 latency của các API quan trọng.
- Batch execution+commit duration.
- WAL bytes/second và WAL bytes/batch.
- Free disk `pg_wal` và archive backlog.
- Replica replay lag/receive lag.
- Checkpoint frequency, FPI/write I/O.
- Lock waits, deadlocks, active transactions.
- Autovacuum progress/dead tuples.
- Errors/retries/duplicate conflicts.

### 32.3. AIMD (additive increase/multiplicative decrease)

Một thuật toán đơn giản:

- Khi metrics khỏe nhiều chu kỳ: tăng batch thêm 500 rows.
- Khi gần ngưỡng nguy hiểm: giảm batch một nửa.
- Áp giới hạn minimum/maximum và cooldown.
- Giữ progress checkpoint sau mỗi commit.

Đây là mô hình điều khiển minh họa, không phải tham số tối ưu sẵn. Các metrics có độ trễ và nhiễu; cần tránh controller dao động liên tục.

### 32.4. Batch size và worker count là hai cần gạt khác

Giảm 10.000 → 2.000 rows/batch nhưng tăng workers từ 2 → 10 có thể giữ nguyên hoặc tăng WAL generation rate. Khi vấn đề là **throughput WAL vượt khả năng replica/archive**, cần kiểm soát tổng write rate, không chỉ max rows per transaction.

### 32.5. Tạm dừng an toàn

Một importer nên pause ở **boundary sau COMMIT**, không dừng đột ngột giữa transaction không có cleanup. Nếu bắt buộc cancel, caller cần rollback/release lock và đánh dấu trạng thái job phù hợp.

---

## 33. Xuất dữ liệu lớn: COPY TO và streaming

### 33.1. COPY TO STDOUT

Xuất dữ liệu có thể dùng:

~~~sql
COPY (
    SELECT order_id,customer_id,amount,order_status
    FROM wal_batch_lab.orders
    WHERE order_id BETWEEN 100 AND 100000
    ORDER BY order_id
)
TO STDOUT
WITH (FORMAT csv, HEADER true);
~~~

`COPY TO STDOUT` được client hỗ trợ theo protocol; với `psql`, thường tiện dùng `\copy` để ghi file local.

### 33.2. \copy (SELECT ...) TO file

~~~text
\copy (SELECT order_id,customer_id,amount,order_status FROM wal_batch_lab.orders ORDER BY order_id) TO '/client/export/orders.csv' WITH (FORMAT csv, HEADER true)
~~~

Đường dẫn là đường dẫn **ở máy chạy psql**, không phải PostgreSQL server. Người chạy psql phải có quyền ghi file client.

### 33.3. COPY TO khác COPY FROM về WAL

Xuất dữ liệu chỉ đọc không tạo WAL do việc INSERT/UPDATE bảng đích; tuy nhiên query có thể ảnh hưởng tài nguyên, locks/snapshots, temp files và workload nền, và các hoạt động không liên quan khác vẫn tạo WAL. Không suy từ việc “xuất file” rằng DB không phát sinh WAL toàn cluster.

### 33.4. Streaming để giảm RAM

Với file hàng chục GB, không nên đưa toàn bộ result set vào một mảng Java rồi mới ghi file. Dùng COPY TO STDOUT stream hoặc cursor/fetch-size phù hợp driver để xử lý tuần tự, có backpressure.

### 33.5. Xuất theo nhiều transaction có nhất quán không?

Nếu chạy nhiều SELECT/COPY chunks trong nhiều transactions READ COMMITTED, dữ liệu có thể thay đổi giữa các chunks do concurrent writers. Keyset pagination giúp tránh OFFSET lệch nhưng **không tự cung cấp một snapshot nhất quán cho toàn bộ export**.

Khi cần bản xuất có consistency tại một thời điểm, cần thiết kế snapshot/transaction phù hợp; giữ một transaction snapshot nhiều giờ có thể gây vacuum pressure, nên cân bằng snapshot consistency với tải vận hành.

### 33.6. pg_dump không phải COPY tự chế

Nếu mục tiêu là sao lưu database/schema đầy đủ, dùng `pg_dump`/backup solution phù hợp thay vì tự SELECT từng bảng. pg_dump xử lý nhiều đối tượng DB, quyền/schemas và consistency theo cơ chế riêng; export CSV chỉ là **dữ liệu** không đại diện đầy đủ cho schema, indexes, constraints, sequences, extensions và roles.

---

## 34. Xuất theo keyset và snapshot consistency

### 34.1. Keyset trong export

~~~sql
SELECT order_id,customer_id,amount
FROM wal_batch_lab.orders
WHERE order_id > 0
ORDER BY order_id
LIMIT 1000;
~~~

Sau đó truyền last returned order_id cho page tiếp:

~~~sql
SELECT order_id,customer_id,amount
FROM wal_batch_lab.orders
WHERE order_id > 1000
ORDER BY order_id
LIMIT 1000;
~~~

Giá trị 1000 ở page thứ hai chỉ minh họa; phải lấy **last actual key**. Nếu bảng có gaps, vẫn hoạt động.

### 34.2. Snapshot thay đổi qua pages

Nếu job đọc theo `READ COMMITTED` và có row mới được INSERT với `order_id < last_key`, row đó có thể không bao giờ được xuất. Đây có thể phù hợp “export historical existing rows tới watermark”, nhưng phải nêu rõ semantic.

### 34.3. Cutoff watermark

Nếu cần xuất dữ liệu đã ổn định trước một thời điểm, có thể chọn `created_at < cutoff` và keyset theo cặp `(created_at,id)`. Nhưng điều này vẫn không xử lý hoàn hảo các backdated inserts hoặc updates trong nguồn nếu không có invariant source version.

### 34.4. Một REPEATABLE READ transaction dài

Một transaction `REPEATABLE READ` giữ snapshot tương đối ổn định cho các queries trong transaction đó, nhưng có thể cản vacuum cleanup và giữ tài nguyên rất lâu nếu xuất hàng trăm GB chậm. Nếu cần consistency toàn dump và quy mô lớn, nên dùng cơ chế backup/export chuyên dụng hoặc thiết kế snapshot phân tán có kiểm soát.

### 34.5. Không trộn “chia file output” với “chia transaction input”

Một client có thể stream kết quả của **một query** rồi tự chia thành nhiều file 1 GiB. Điều đó chia output files, **không** chia SQL transaction/snapshot trong server. Ngược lại nhiều queries/chunks có thể mở nhiều transactions. Phải nói rõ ranh giới nào đang được chia.

---

## 35. Phân vùng dữ liệu để giảm DELETE retention

### 35.1. Partitioning theo thời gian

Bảng event hàng tỷ rows với retention 90 ngày có thể được phân vùng theo ngày/tuần/tháng:

~~~text
events (partitioned parent)
    |
    +-- events_2026_08
    +-- events_2026_09
    +-- events_2026_10
    +-- events_2026_11
~~~

Khi một partition chứa **toàn bộ dữ liệu** đã hết retention, có thể detach/drop theo runbook. Điều này thường tránh phải DELETE từng row, tạo dead tuples và WAL row-level tương ứng.

### 35.2. Không nhầm metadata operation là free

Detach/drop partition vẫn có locking, catalog changes, dependencies, replica/app impact và trong những trường hợp nhất định WAL. Nếu dùng `DETACH PARTITION CONCURRENTLY`, có constraints/caveats riêng và không áp dụng mọi tình huống/version.

### 35.3. Không bỏ per-row audit một cách vô tình

Nếu DELETE ROW trigger đang ghi audit cho từng event, DROP partition không thực hiện hàng triệu DELETE ROW trigger calls. Cần quyết định contract retention/audit riêng; không chỉ tối ưu speed rồi phát hiện mất compliance audit.

### 35.4. Phân vùng hỗ trợ import

Nạp dữ liệu vào partition tương ứng có thể giúp manage indexes, retention, partition pruning và data lifecycle. Nhưng quá nhiều partitions có thể làm planner/catalog overhead tăng; không tạo một partition mỗi vài trăm rows tùy ý.

### 35.5. Thay dữ liệu nguyên một partition

Một số workflows có thể build dữ liệu mới trong bảng riêng, validate, build indexes và attach partition theo quy tắc PostgreSQL. Cần kiểm tra constraint, FK, lock, replication và version-specific semantics; không coi ATTACH là một thao tác zero-downtime bất kể tình huống.

---

## 36. Chuyển đổi dữ liệu/backfill: khi UPDATE hàng loạt không phải lựa chọn tốt nhất

### 36.1. Ví dụ thêm cột tính toán

Một bảng lớn có cột `normalized_email` mới. UPDATE toàn bộ hàng một lần có thể gây:

- WAL do update heap/indexes.
- Dead tuples và bloat.
- Long transaction.
- Replica lag.
- I/O burst.

### 36.2. Batch theo primary key

~~~sql
WITH ids AS (
    SELECT user_id
    FROM app.users
    WHERE normalized_email IS NULL
      AND user_id > 0
    ORDER BY user_id
    LIMIT 2000
)
UPDATE app.users AS u
SET normalized_email = lower(btrim(u.email))
FROM ids
WHERE u.user_id=ids.user_id
  AND u.normalized_email IS NULL;
~~~

Ví dụ giả định `app.users` và các cột tồn tại; **không chạy nguyên** nếu schema khác. Kết hợp predicate để job idempotent và tránh ghi lại rows đã được xử lý.

### 36.3. Concurrent writers

Nếu ứng dụng có thể sửa email trong khi backfill, cần đảm bảo normalized_email được cập nhật đúng cho **những writes mới** (bằng application dual-write/trigger phù hợp) trước hoặc trong migration, hoặc có reconciliation pass.

### 36.4. Cắt batch theo key chưa đủ nếu không có recheck

Khi một worker chọn IDs rồi chờ trước UPDATE, row có thể đã đổi. DML nên điều kiện lại trên trạng thái cần cập nhật hoặc có locking phù hợp. Trong job nhiều workers, dùng claim/skip locked/reconciliation theo contract.

### 36.5. Rewrite table có khi hợp lý hơn

Với bảng khổng lồ cần thay đổi gần như mọi row, một pipeline tạo **bảng mới**, nhập/biến đổi bằng INSERT SELECT hoặc COPY, tạo indexes, validate và cutover có thể hiệu quả hơn in-place UPDATE. Nhưng table swap/cutover có rủi ro lớn về FKs, sequences, triggers, permissions, replication, concurrent writes và locks. Quyết định theo maintenance windows/operational readiness, không chỉ vì muốn giảm WAL.

### 36.6. Ghép bước schema migration

Một quy trình có thể là:

1. Thêm cột nullable.
2. Deploy code ghi cả cột mới khi có writes.
3. Backfill theo batches.
4. Reconcile dữ liệu.
5. Add/validate constraints, index theo online/concurrent options nếu phù hợp.
6. Đổi read path.
7. Thu hồi logic cũ sau xác nhận.

Đây là pattern “expand → migrate → contract”, giúp tránh big-bang DDL/DML dưới tải.

---

## 37. Isolation và lock timeout cho batch jobs

### 37.1. lock_timeout

~~~sql
BEGIN;
SET LOCAL lock_timeout='2s';

WITH ids AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 500
)
UPDATE wal_batch_lab.orders AS o
SET order_status='paid'
FROM ids
WHERE o.order_id=ids.order_id;

COMMIT;
~~~

Khi đợi lock quá lâu, statement có thể bị hủy và transaction thất bại; client cần rollback/retry. `lock_timeout` không phải giới hạn toàn thời gian DML.

### 37.2. statement_timeout

~~~sql
BEGIN;
SET LOCAL statement_timeout='10s';
-- Một batch SQL
COMMIT;
~~~

Nên chọn thời gian đủ cho batch bình thường nhưng ngăn job đứng vô hạn. Nếu timeout xảy ra, phải kiểm tra transaction và retry semantics.

### 37.3. idle_in_transaction_session_timeout

Giúp chấm dứt sessions giữ transaction mở nhưng không gửi SQL quá lâu. Không thay việc importer trả connection đúng lúc; khi timeout, connection bị đóng và pool cần phục hồi.

### 37.4. Deadlock

Hai workers update các rows theo thứ tự trái nhau có thể deadlock. Chọn thứ tự xử lý keys nhất quán và giữ transactions ngắn có thể giảm nguy cơ, nhưng không loại bỏ hoàn toàn. PostgreSQL phát hiện deadlock và abort một transaction; ứng dụng cần retry theo policy.

### 37.5. Không biến timeout thành “bỏ qua row”

Nếu batch bị lock timeout, không được đánh dấu checkpoint thành công hoặc bỏ hẳn row. Error path cần rollback và giữ job range chưa hoàn tất.

### 37.6. Serializable retry

Dưới isolation SERIALIZABLE, `serialization_failure (40001)` yêu cầu retry transaction (thường bao gồm cả việc đọc lại và tính toán lại quyết định). Không chỉ chạy lại statement cuối cùng rồi dùng dữ liệu đã đọc từ transaction cũ.

---

## 38. WAL burst và storage capacity: lập ngân sách

### 38.1. Một phép ước lượng minh họa

Giả sử thử nghiệm cho biết trung bình mỗi row UPDATE làm phát sinh khoảng **2 KiB WAL** trong workload cụ thể. Nếu import 5 triệu rows:

- Lượng WAL dự kiến ~10.000.000 KiB ≈ 9,54 GiB.
- Nếu job kéo dài 10 phút, WAL generation rate trung bình khoảng 16,3 MiB/s.
- WAL spikes tức thời có thể cao hơn trung bình do checkpoint/FPI và batch concurrency.

Đây chỉ là **số giả lập**. WAL bytes/row không cố định; đo trên representative dataset trước khi quyết định disk budget.

### 38.2. Ngân sách gồm nhiều hệ

Không chỉ tính `pg_wal` disk:

- Primary disk free/IOPS.
- WAL archiving throughput/destination.
- Standby network/replay speed.
- Logical decoding consumers.
- Base backup/PITR retention.
- Temp file usage/sort/hash.
- Heap/index growth do UPDATE/DELETE.
- Rollback/retry overhead.
- Dung lượng staging/raw files.

### 38.3. Headroom khi có sự cố

Một migration mất 2 giờ nên có headroom cho trường hợp archive chậm, standby offline, job phải retry. Không chạy sát giới hạn disk và kỳ vọng `max_wal_size` luôn ngăn WAL growth.

### 38.4. Monitoring trong thời gian job

Nên có dashboard:

| Metric | Ý nghĩa | Hành động nếu xấu |
|---|---|---|
| WAL MiB/s | Write generation rate | Giảm ingest rate/worker count |
| WAL retained / free disk | Nguy cơ disk full | Kiểm tra slots/archive, pause an toàn |
| Replica replay lag bytes | Consumer catch-up | Throttle, điều tra standby |
| Archive failures/backlog | PITR/retention nguy cơ | Sửa archive destination |
| Checkpoint frequency/FPI | Write amplification | Đo/tune storage và WAL config |
| n_dead_tup/autovacuum lag | Bloat pressure | Reclaim/tune sau transactions |
| API p95/p99 latency | Ảnh hưởng khách hàng | Giảm concurrency/batch |
| Transaction age/locks | Blocking | Rút ngắn transactions, tìm blockers |

### 38.5. Thresholds phải có hành động

Alert chỉ có giá trị nếu có runbook: ai được pause job, khi nào dừng ngay, kiểm tra slot/archive như thế nào, resume ở đâu, và khi nào rollback/cutover không an toàn.

---

## 39. Tổng hợp quy trình staging → validate → publish

### 39.1. Luồng xử lý an toàn

~~~mermaid
flowchart TD
    A["Nguồn dữ liệu immutable + checksum"] --> B["Chia chunk có stable ID"]
    B --> C["COPY chunk vào staging"]
    C --> D{"Validate & deduplicate"}
    D -- "Lỗi không được phép" --> E["ROLLBACK chunk; quarantine"]
    D -- "Đạt" --> F["Merge vào bảng logged"]
    F --> G["Ghi checkpoint cùng transaction"]
    G --> H["COMMIT"]
    H --> I["Đo WAL, lag, latency, disk"]
    I --> J{"Thresholds ổn?"}
    J -- "Không" --> K["Pause / giảm batch / alert"]
    K --> I
    J -- "Có" --> L{"Còn chunk?"}
    L -- "Có" --> B
    L -- "Không" --> M["Reconcile accepted/rejected/duplicates"]
    M --> N["Publish dataset version / status complete"]
~~~

### 39.2. Quyết định giữa atomic toàn job và atomic từng chunk

- **Atomic từng chunk:** dữ liệu đích được commit dần, có thể đọc trạng thái một phần. Hợp với event ingest có acceptance/visibility từng lô.
- **Atomic toàn job:** có thể giữ dữ liệu trong staging, sau đó publish bằng metadata version/partition operation trong một transaction ngắn hơn. Cần thiết kế table/schema/reader consistency phù hợp.
- **Atomic theo customer/key range:** có thể commit mỗi entity hoàn chỉnh thay vì một số lượng rows bất kỳ, nếu invariant không cho phép phân đôi một entity.

### 39.3. Dữ liệu raw và dữ liệu đã chuẩn hóa

Giữ raw source immutable/checksum cho phép đối chiếu và reprocess. Trong bảng đích, lưu business keys, import batch identifier và source version khi cần để xác minh kết quả. Không chuyển một event tới trạng thái complete chỉ vì network stream đã kết thúc.

### 39.4. Trạng thái job

Gợi ý state machine:

~~~text
pending -> running -> complete
             |
             v
            failed -> running (resume)
             |
             v
           cancelled (theo policy)
~~~

Nếu job failed ở batch 37, dữ liệu batch 1..36 đã commit có thể vẫn tồn tại. Metadata phải nói rõ phạm vi đã xử lý, không giả vờ transaction toàn job đã rollback.

### 39.5. Job cancellation

Khi người vận hành yêu cầu dừng:

1. Không nhận thêm lô mới.
2. Để lô đang chạy COMMIT hoặc ROLLBACK có chủ đích.
3. Đóng/return connections.
4. Ghi trạng thái và checkpoint đáng tin.
5. Giữ raw source, rejected rows, log/counters.
6. Báo cáo tiến độ committed chứ không chỉ rows đã đọc vào RAM.

---

## 40. Runbook khi WAL tăng đột biến

### 40.1. Nhận diện triệu chứng

- `pg_wal` filesystem free space giảm nhanh.
- Replica replay lag tăng.
- `pg_stat_archiver.failed_count` tăng hoặc archive chậm.
- `pg_stat_wal.wal_bytes` delta tăng.
- Checkpoint/write I/O tăng.
- API latency/lock waits tăng.

### 40.2. Bước 1: chụp số liệu (không gây thêm tải lớn)

~~~sql
SELECT
    pg_current_wal_lsn() AS current_lsn,
    pg_is_in_recovery() AS is_standby;

SELECT wal_records,wal_fpi,wal_bytes,stats_reset
FROM pg_stat_wal;

SELECT slot_name,slot_type,active,restart_lsn
FROM pg_replication_slots;

SELECT application_name,state,sync_state,replay_lsn
FROM pg_stat_replication;

SELECT archived_count,failed_count,
       last_archived_time,last_failed_time
FROM pg_stat_archiver;
~~~

Một số views/columns phụ thuộc PostgreSQL major version và quyền. Không đổi permissions vô tội vạ để có một dashboard.

### 40.3. Bước 2: xác định generation hay retention

- Nếu WAL bytes/s tăng cùng importer mới: điều tra write rate/batch concurrency.
- Nếu WAL bytes/s bình thường nhưng `pg_wal` tiếp tục tăng: điều tra replication slot, archive failures, WAL retention config.
- Nếu cả hai tăng: có thể job burst cộng consumer/archive không theo kịp.

### 40.4. Bước 3: điều tiết tại batch boundary

Giảm số workers hoặc bytes/s, pause sau COMMIT/ROLLBACK. Tránh kill đột ngột backend đang giữ transaction lớn nếu không cân nhắc rollback/recovery effect; đôi khi cancellation là cần thiết theo incident severity và runbook.

### 40.5. Bước 4: điều tra archiving/slots

Nếu một logical slot stale giữ WAL, liên hệ consumer owner trước khi drop. Nếu archive destination full/unreachable, sửa pipeline thay vì xóa WAL files chưa archived.

### 40.6. Bước 5: đánh giá checkpoint và storage

Nếu FPI/checkpoint pressure lớn, xem checkpoint frequency và config có phù hợp disk budget không. Không tắt `fsync/full_page_writes` để chữa khẩn cấp.

### 40.7. Bước 6: đối chiếu job state

Sau pause, đọc checkpoint, nguồn file checksum và destination row counts/keys. Xác định những batches đã commit. Không retry cả file từ đầu nếu có nguy cơ duplicate và thiếu idempotency.

### 40.8. Bước 7: phục hồi có kiểm soát

Resume với batch/concurrency thấp hơn, đo nhiều chu kỳ; ưu tiên bảo vệ RPO/replica, API latency và đĩa. Chỉ tăng dần khi backlog giảm.

### 40.9. Bước 8: postmortem

Ghi số WAL bytes/row, điểm nghẽn archive/replication, checkpoint metrics, số retries, failed batches và độ trễ. Cập nhật capacity plan/test staging để không lặp sự cố.

---

## 41. Kiểm tra và giám sát: truy vấn mẫu

### 41.1. Phiên đang chạy transaction lâu

~~~sql
SELECT
    pid,usename,application_name,state,
    clock_timestamp()-xact_start AS transaction_age,
    wait_event_type,wait_event
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
~~~

### 41.2. Hoạt động bàn staging/đích

~~~sql
SELECT
    relname,
    n_live_tup,n_dead_tup,
    n_tup_ins,n_tup_upd,n_tup_del,
    last_autovacuum,last_analyze
FROM pg_stat_user_tables
WHERE schemaname='wal_batch_lab'
ORDER BY relname;
~~~

### 41.3. Thống kê WAL

~~~sql
SELECT
    wal_records,wal_fpi,
    pg_size_pretty(wal_bytes::bigint) AS wal_volume,
    wal_write,wal_sync,stats_reset
FROM pg_stat_wal;
~~~

### 41.4. Physical replication

~~~sql
SELECT
    application_name,state,sync_state,
    sent_lsn,write_lsn,flush_lsn,replay_lsn,
    replay_lag
FROM pg_stat_replication;
~~~

### 41.5. Slot backlog

~~~sql
SELECT
    slot_name,active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS bytes_from_restart
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
~~~

### 41.6. Không ghép nhiều SELECT monitors thành transaction dài

Nếu dashboard mở transaction rồi query metrics hàng chục phút, chính nó có thể gây snapshot/connection pressure. Đọc thống kê trong sessions ngắn và quản lý privileges.

---

## 42. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| “Cứ chia 10.000 rows là tốt” | WAL bytes/row khác nhau, burst vẫn lớn | Benchmark + resource budgets |
| “Một LOOP 100 lần tự commit 100 lần” | Một function/DO có thể là một transaction | Control COMMIT ở boundary hợp lệ |
| “COPY tự commit từng dòng” | Một COPY là một statement | Chia stream thành nhiều COPY/transactions |
| “COPY lỗi giữa file không tốn WAL/storage” | WAL đã sinh, aborted tuples có thể cần VACUUM | Chunk + validate |
| “\copy là SQL trên server” | Là psql meta-command chạy client | Dùng psql/driver COPY protocol |
| “Dùng \copy server file path” | Đọc file local psql, không phải DB server | Phân biệt COPY/\copy |
| “COMMIT toàn job và COMMIT từng batch giống nhau” | Atomicity khác | Chọn publish strategy |
| “Checkpoint metadata sau COMMIT luôn đủ an toàn” | Có cửa sổ crash giữa hai commits | Ghi checkpoint cùng transaction |
| “ON CONFLICT DO NOTHING luôn an toàn” | Có thể che payload conflict | Key + checksum/version |
| “Cứ retry batch là không trùng” | Unknown commit outcome có thể nhân đôi | Idempotency + reconcile |
| “SET batch size nhỏ là WAL rate nhỏ” | Workers tăng có thể giữ/đẩy rate | Kiểm soát aggregate bytes/s |
| “UPDATE PostgreSQL có LIMIT trực tiếp” | Syntax error | CTE chọn keys rồi UPDATE |
| “LIMIT không ORDER BY ổn cho resume” | Không deterministic | Keyset/ORDER BY stable PK |
| “OFFSET lớn là cách paging hiệu quả” | Tốn scan và nhạy concurrent changes | Keyset pagination |
| “SKIP LOCKED 0 rows nghĩa hết việc” | Rows còn lại có thể locked | Retry/reconciliation |
| “UPDATE status=status không tạo WAL” | Vẫn có tuple update | Predicate IS DISTINCT FROM |
| “DELETE trả disk ngay về OS” | MVCC dead tuples/bloat | Vacuum/partition design |
| “VACUUM FULL sau mọi lô” | Table rewrite, lock và WAL lớn | Normal autovacuum/VACUUM first |
| “max_wal_size chặn WAL ở mức cứng” | Slots/archive có thể khiến giữ vượt | Monitor retention causes |
| “pg_wal đầy thì rm vài segment” | Nguy cơ mất recovery/PITR | Fix slots/archive/capacity |
| “WAL delta là của đúng batch tôi” | Cluster cùng tạo WAL | Isolate workload/measure context |
| “wal_bytes = rows INSERT” | WAL nhiều record/index/FPI | Đo bytes/row |
| “LSN là timestamp” | Là vị trí log | pg_wal_lsn_diff |
| “FPI có thể tắt an toàn” | Crash-recovery risk | Giữ full_page_writes |
| “fsync=off giúp import production không rủi ro” | Mất durability/corruption risk | Không tắt tùy tiện |
| “synchronous_commit=off là zero WAL” | WAL vẫn được ghi | Phân biệt flush ACK vs generation |
| “UNLOGGED giống logged table” | Crash truncate, không physical replicate | Chỉ staging tái tạo được |
| “Index bỏ được không cần rebuild cost” | Rebuild có WAL/lock/IO | Đo toàn pipeline |
| “Replica không lag nếu network nhanh” | Replay/storage/CPU có thể nghẽn | Quan sát replay lag |
| “Slot inactive nên drop ngay” | Consumer mất continuity | Xác định owner/restore plan |
| “Archive không ảnh hưởng import” | Archiving chậm giữ WAL | Capacity plan archive |
| “Truncate và DELETE row triggers như nhau” | Trigger semantics khác | Review event/audit policy |
| “Batch READ COMMITTED có một snapshot chung” | Mỗi transaction thấy snapshot khác | Watermark/snapshot design |
| “Chỉ dùng statement_timeout là đủ” | Không đo lock/pool/replica | Timeouts từng tầng |
| “Rollback thử nghiệm không tạo WAL” | WAL trước rollback vẫn sinh | Test representative lab |
| “Export COPY TO sinh WAL như INSERT” | Read-only export không tạo row-change WAL | Phân biệt I/O/snapshot |
| “Tăng pool/workers luôn tăng tốc” | Lock/IO contention tăng | Benchmark concurrency |
| “Completed file read nghĩa job đã commit” | Dữ liệu/chunk chưa chắc publish | Checkpoint + reconcile |
| “Bỏ qua errors bằng WHEN OTHERS” | Có thể lỡ data/làm sai checkpoint | Catch cụ thể/rethrow |
| “Xóa partition chẳng ảnh hưởng triggers/audit” | Không gọi per-row DELETE | Compliance/runbook |

---

## 43. Checklist trước khi chạy import hàng triệu rows

### 43.1. Dữ liệu và schema

- [ ] Nguồn dữ liệu immutable hoặc có checksum/version.
- [ ] Dedupe keys rõ, import/job ID ổn định.
- [ ] Staging đủ khả năng bắt lỗi input và reject/quarantine.
- [ ] Bảng đích có PK/UNIQUE/FK/CHECK đúng.
- [ ] Trigger/index costs và write amplification đã được ước lượng.
- [ ] Có index cho keyset/WHERE của batch update/delete.

### 43.2. Transaction correctness

- [ ] Một lô có transaction scope rõ.
- [ ] Commit progress và dữ liệu cùng transaction nếu cần.
- [ ] Có retry/idempotency khi crash sau COMMIT không rõ.
- [ ] Có state và resume cho job failed/cancelled.
- [ ] Không giữ toàn job trong một transaction dài vô lý.
- [ ] Nếu atomic toàn job là yêu cầu, có staging/publish version strategy.
- [ ] Concurrent writers và isolation level được review.

### 43.3. WAL và disk

- [ ] Đo WAL bytes/row, WAL bytes/batch trên dữ liệu đại diện.
- [ ] Có disk headroom cho pg_wal/data/index/temp.
- [ ] Monitor checkpoint/FPI và không tắt durability.
- [ ] Xác minh archive capacity và replica replay throughput.
- [ ] Có replication slots owner/backlog monitoring.
- [ ] Không dựa max_wal_size như hard limit.
- [ ] Có pause policy khi WAL retained vượt budget.

### 43.4. Hiệu năng và lock

- [ ] Batch size và workers được benchmark theo p95 API latency.
- [ ] DML dùng stable PK order và selective predicates.
- [ ] Không OFFSET sâu trong job dài.
- [ ] SKIP LOCKED chỉ dùng khi inconsistent view được chấp nhận.
- [ ] Có lock_timeout/statement_timeout phù hợp.
- [ ] Autovacuum không bị chặn/disable.
- [ ] Có strategy post-job ANALYZE/reconciliation.

### 43.5. Vận hành

- [ ] Rollback/cancel plan ở batch boundary.
- [ ] Có dashboard WAL rate, disk, lag, locks, retries.
- [ ] Có alert và người phụ trách.
- [ ] Không log password/PII raw payload tràn lan.
- [ ] Có kiểm thử partial failure/unknown commit.
- [ ] Có kết quả expected counts/checksums.
- [ ] Có canary nhỏ trước bulk migration.

---

## 44. Bài tập thực hành

Các bài tập dùng schema `wal_batch_lab` trong bài nếu không nói khác. Một số đề có SQL cố ý sai hoặc yêu cầu phân tích thay đổi cấu hình; **không chạy trên production**. Khi luyện DML, ưu tiên transaction với `ROLLBACK` hoặc tạo dataset lab mới để giữ số liệu xuất phát.

### Bài 1 — WAL là gì?

Giải thích vì sao PostgreSQL ghi WAL và vì sao data pages chưa được flush hết tại thời điểm COMMIT vẫn có thể được khôi phục sau crash theo durability policy chuẩn.

### Bài 2 — WAL và rollback

Một transaction INSERT 1 triệu rows rồi ROLLBACK. Có thể kết luận WAL phát sinh bằng 0 vì không có rows nào được commit không? Vì sao?

### Bài 3 — Các mức chia lô

Phân biệt batch, statement, transaction và database checkpoint. Một vòng lặp 100 INSERT trong một `DO` block có tự tạo 100 commits không?

### Bài 4 — Một transaction so với nhiều batches

Cho một file 2 triệu rows. Nêu ít nhất bốn lợi ích và ba rủi ro/trade-off của việc chia thành 200 lô × 10.000 rows, mỗi lô commit riêng.

### Bài 5 — Atomic toàn job

Một import có 200 batches; batch thứ 156 lỗi. Yêu cầu business: người dùng chỉ nhìn thấy phiên bản dataset mới sau khi toàn bộ file thành công. Đề xuất cách publish an toàn thay vì ghi trực tiếp từng batch vào bảng đang phục vụ.

### Bài 6 — Chọn batch size

Tại sao 10.000 rows/batch không thể coi là tối ưu mặc định cho mọi bảng? Nêu ít nhất sáu chỉ số nên dùng để điều chỉnh batch.

### Bài 7 — COMMIT trong procedure

Function `SELECT process_all_rows()` loop hàng triệu rows và muốn `COMMIT` mỗi 1.000 rows. Có được không? Cần chuyển transaction control sang đâu? Nếu dùng procedure, nêu một ràng buộc về caller.

### Bài 8 — COPY server-side và \copy client-side

Một CSV nằm trên laptop, server PostgreSQL ở cloud. Vì sao `COPY ... FROM '/home/user/orders.csv'` trên server thường thất bại? Viết dạng `\copy` thích hợp.

### Bài 9 — COPY có tự chia transactions không?

Một `COPY FROM STDIN` nạp 500.000 rows, bị lỗi ở dòng 300.000. Các rows đầu có tự được commit không? Làm cách nào để có checkpoint sau mỗi 10.000 rows?

### Bài 10 — CSV numeric invalid

Staging có cột `amount numeric`, nhưng CSV chứa giá trị `not-a-number`. Có thể nạp bình thường rồi validate bằng `WHERE amount ~ ...` không? Đề xuất mô hình raw staging thích hợp.

### Bài 11 — Import staging và checkpoint

Viết transaction chèn 2 rows vào `wal_batch_lab.order_stage` với import_id=9001, source_row_no=10,11, rồi cập nhật `import_jobs.last_committed_row=11` trong cùng transaction.

### Bài 12 — Checkpoint sai thứ tự

Ứng dụng commit `last_committed_row=50000` trước khi insert rows 40001..50000. Nếu SQL insert lỗi, điều gì xảy ra khi resume? Chỉ ra cách thiết kế đúng.

### Bài 13 — Retry và unique key

Một batch bị mất phản hồi COMMIT. Hãy giải thích cách `PRIMARY KEY(import_id,source_row_no)` hỗ trợ retry, và trường hợp nào `ON CONFLICT DO NOTHING` có thể che bug.

### Bài 14 — Conflict payload

Có staging row ID (9001,25) với amount=100. Retry gửi row cùng key nhưng amount=200. Có nên bỏ qua không? Thiết kế kiểm tra nào giúp phát hiện conflict không tương đương?

### Bài 15 — ON CONFLICT DO UPDATE nhiều rows cùng ID

Một staging batch có hai source rows cùng `order_id=401`. Vì sao một `INSERT ... ON CONFLICT DO UPDATE` có thể báo lỗi? Cách deduplicate trước merge?

### Bài 16 — Đo WAL bằng LSN

Giả sử WAL LSN trước và sau job đã được lưu vào `v_before` và `v_after`. Viết SQL tính WAL bytes/MiB; giải thích vì sao delta này không hoàn toàn chỉ thuộc job nếu database có workload đồng thời.

### Bài 17 — WAL statistics

Dùng `pg_stat_wal` để đọc wal_bytes, wal_fpi và wal_records. Khi đo delta hai lần, cần kiểm tra trường nào để biết stats có bị reset giữa lúc đo?

### Bài 18 — Thư mục pg_wal đầy

Server còn ít disk vì `pg_wal` lớn. Có nên xóa vài WAL segment bằng lệnh OS không? Nêu ít nhất bốn nguồn giữ WAL cần kiểm tra.

### Bài 19 — max_wal_size

Một DBA đặt `max_wal_size=8GB`, nhưng `pg_wal` chiếm 30GB. Có chắc PostgreSQL lỗi không? Vì sao mốc này không phải hard limit?

### Bài 20 — Full-page images

Giải thích vì sao WAL có thể tăng ở thời điểm sau checkpoint. `full_page_writes=off` có phải giải pháp tốt để giảm WAL không?

### Bài 21 — wal_compression

`wal_compression` giúp giảm WAL bytes ở loại workload nào? Trade-off chính? Có phải mọi UPDATE giảm WAL như nhau không?

### Bài 22 — UPDATE LIMIT

Sửa câu SQL không hợp lệ:

~~~sql
UPDATE wal_batch_lab.orders
SET order_status='paid'
WHERE order_status='new'
LIMIT 2;
~~~

Dùng CTE chọn hai `order_id` nhỏ nhất, rồi UPDATE đúng hai hàng.

### Bài 23 — SKIP LOCKED

Hai workers cùng cập nhật những orders new. Viết CTE `FOR UPDATE SKIP LOCKED` và giải thích vì sao worker trả 0 rows chưa chắc là mọi việc đã hết.

### Bài 24 — UPDATE SET same value

`UPDATE orders SET order_status=order_status` có thể tạo WAL và dead tuples không? Viết điều kiện chỉ cập nhật khi giá trị thật sự đổi so với `'paid'`.

### Bài 25 — DELETE theo lô

Viết DELETE tối đa 1.000 orders `cancelled` theo thứ tự ID. Vì sao DELETE không làm kích thước data file giảm ngay?

### Bài 26 — Retention partitioning

Bảng event được phân vùng theo tháng; cần xóa toàn bộ dữ liệu cũ hơn 2 năm. Vì sao drop một partition cũ có thể hiệu quả hơn DELETE từng row? Cần review những rủi ro nào?

### Bài 27 — Keyset vs OFFSET

Vì sao `LIMIT 1000 OFFSET 5000000` thường kém hiệu quả? Viết query trang tiếp theo theo `order_id > last_id`.

### Bài 28 — Concurrency và keyset

Nếu trong lúc job đang xử lý tới `order_id=1000`, transaction khác INSERT row `order_id=900`, job có bắt được row mới không? Nếu yêu cầu snapshot cố định, cần mô hình gì?

### Bài 29 — WAL/replica lag

Viết query xem `sent_lsn, write_lsn, flush_lsn, replay_lsn` từ `pg_stat_replication`. Nếu replay lag tăng khi job chạy, nêu ba biện pháp điều tiết.

### Bài 30 — Time lag vs bytes lag

Vì sao `pg_last_xact_replay_timestamp()` trên standby không phải thước đo tuyệt đối replica lag nếu primary không có transactions mới? Dùng gì để bổ sung?

### Bài 31 — Replication slot retention

Viết SQL tính WAL bytes từ `pg_current_wal_lsn()` tới `restart_lsn` của mỗi slot. Tại sao slot inactive chưa chắc nên drop ngay?

### Bài 32 — Archive backlog

`pg_stat_archiver.failed_count` tăng trong lúc import. Những nguyên nhân nào và vì sao chỉ giảm batch size không phải lúc nào đủ?

### Bài 33 — UNLOGGED stage

Một bảng staging có thể reload từ immutable source. Khi nào `UNLOGGED` hợp lý? Nêu ba trường hợp không nên dùng UNLOGGED.

### Bài 34 — synchronous_commit

`synchronous_commit=off` có làm PostgreSQL không ghi WAL nữa không? Rủi ro chính với commit acknowledgment và crash? Vì sao không nên áp dụng tùy tiện cho payment?

### Bài 35 — Autovacuum

Một batch DELETE 30 triệu rows đã commit. Vì sao file data không giảm kích thước ngay? `VACUUM ANALYZE` hỗ trợ gì, và `VACUUM FULL` có trade-offs nào?

### Bài 36 — Index write amplification

Bảng có 15 indexes, importer thêm 10 triệu rows. Nêu ảnh hưởng lên WAL/IO. Có nên drop mọi indexes và FKs để tăng tốc không?

### Bài 37 — Batch JDBC

Viết pseudocode Java dùng PreparedStatement.`addBatch`/`executeBatch` và một transaction cho 2.000 rows, rollback khi lỗi. Nêu điều `executeBatch` không bảo đảm.

### Bài 38 — Rate limiting

Một worker giảm batch từ 10.000 xuống 2.000 rows nhưng tăng concurrency từ 2 lên 10. WAL bytes/s có chắc giảm không? Thiết kế một policy điều tiết based on WAL rate/replica lag.

### Bài 39 — Timeout

Phân biệt `lock_timeout`, `statement_timeout` và `idle_in_transaction_session_timeout`. Khi một lô bị timeout, checkpoint có được tiến lên không?

### Bài 40 — WAL LSN vs wal_bytes

Nêu khác biệt giữa `pg_wal_lsn_diff` và delta `pg_stat_wal.wal_bytes`. Vì sao không gọi cả hai là WAL riêng của import job khi database có sessions khác?

### Bài 41 — COPY TO và consistency

Bạn xuất bảng 500 triệu rows bằng 500 queries keyset, mỗi query commit riêng. Có bảo đảm một snapshot nhất quán không? So sánh với một transaction REPEATABLE READ dài và cách backup chuyên dụng.

### Bài 42 — pg_dump vs CSV export

Một team muốn dùng `\copy (SELECT * FROM orders) TO orders.csv` làm backup đầy đủ schema có FK, indexes, triggers, sequences và permissions. Vì sao không đủ?

### Bài 43 — Lock contention

Một backfill dùng `UPDATE ... FOR UPDATE SKIP LOCKED` và nhiều workers, nhưng p95 latency của API tăng. Hãy nêu ít nhất năm tín hiệu cần kiểm tra và cách hạ tải.

### Bài 44 — Checkpoint sau crash

Job xử lý 1 triệu rows chia 100 lô. Sau batch 72, connection mất lúc COMMIT và checkpoint hiển thị 710.000. Bạn có được mặc định chạy tiếp từ row 710.001 không? Nêu các bước xác minh trước khi resume.

### Bài 45 — Bảo trì an toàn

Một kỹ sư đề xuất tắt `fsync`, `full_page_writes`, `wal_level` và autovacuum để nhập nhanh hơn. Giải thích các rủi ro và đề xuất đường tối ưu thay thế.

### Bài 46 — Tình huống WAL tăng mà job không đổi

Import vẫn 5 MiB/s nhưng `pg_wal` retained tăng nhanh, replica slot inactive và archive failure tăng. Ưu tiên các bước xử lý nào? Có nên tăng `max_wal_size` vô hạn không?

### Bài 47 — Thiết kế import end-to-end

Bạn nhận CSV 100 GiB gồm order events với `source_event_id` duy nhất, cần kiểm tra, dedup, giữ dữ liệu ở logged destination, có replica và yêu cầu resume sau crash. Phác thảo pipeline, schema metadata, commit boundaries, monitoring và error handling.

### Bài 48 — Thiết kế delete retention quy mô lớn

Bảng event vài tỷ rows, retention 90 ngày, primary còn ít disk, replica có lag, 24/7 OLTP traffic. So sánh batched DELETE với partition lifecycle và lên kế hoạch migration an toàn, bao gồm monitor/rollback/checklist.

### Bài 49 — Unknown commit và external side effect

Một job sau mỗi batch COMMIT xong gọi API gửi webhook, nhưng connection mất đúng lúc COMMIT. Làm sao tránh webhook bị gửi hai lần hoặc gửi cho dữ liệu chưa commit?

### Bài 50 — Runbook tổng hợp

Trong giờ cao điểm, migration backfill 20 triệu rows làm WAL tăng 300 MiB/s, archiver thất bại, slot lag 100 GiB, API p99 từ 200ms lên 5s và autovacuum chưa reclaim dead tuples. Viết runbook ưu tiên safety và khôi phục khả năng vận hành, nêu cách resume mà không làm sai dữ liệu.

---

## 45. Lời giải — bài 1 đến 25

### Bài 1 — WAL và crash recovery

PostgreSQL ghi WAL để có thể khôi phục các changes đã được commit theo mức durability cấu hình, dù data pages chưa được flush toàn bộ. WAL records được đảm bảo ghi/flush theo các quy tắc trước khi coi các thay đổi bền vững. Khi restart sau crash, server replay WAL cần thiết để đưa heap/index files về trạng thái nhất quán.

WAL cũng phục vụ physical replication, archiving và một số hình thức logical decoding. Không nhầm WAL với application log có thể xóa tùy ý.

### Bài 2 — WAL sau ROLLBACK

Không. DML thực thi trước ROLLBACK có thể tạo WAL records, dirty buffers và aborted row versions. ROLLBACK làm các thay đổi **không được commit** nhưng không xóa mọi WAL bytes đã phát sinh khỏi log stream.

Đây là lý do không nên “thử chạy 100 triệu UPDATE rồi ROLLBACK” trong giờ cao điểm chỉ vì tưởng không có chi phí.

### Bài 3 — Phạm vi batch/transaction

- Batch: phạm vi xử lý do job quyết định.
- Statement: câu SQL cụ thể.
- Transaction: atomic COMMIT/ROLLBACK scope.
- Database checkpoint: cơ chế engine flushing pages/recovery point.

Một `DO` block với vòng lặp 100 INSERT có thể chỉ là một SQL statement trong một transaction. **Không tự commit mỗi iteration**.

### Bài 4 — Chia 200 batches

Lợi ích:

1. Transaction và locks được giữ trong từng đoạn ngắn hơn.
2. Dễ pause/resume từ checkpoint.
3. Rollback/retry chỉ cần xử lý lô lỗi.
4. WAL generation có thể được dàn đều nhờ điều tiết giữa lô.
5. Reader/replica có cơ hội catch up giữa batches.

Trade-offs:

1. Job không atomic toàn phần, người đọc có thể thấy data giữa chừng.
2. Nhiều COMMIT, round trips và metadata writes.
3. Cần idempotency/reconciliation, progress bookkeeping.
4. Dễ gặp concurrent changes giữa transactions nếu giả định snapshot thống nhất.

Không có guarantee chắc chắn 10.000 rows/batch là tốt; cần benchmark.

### Bài 5 — Atomic toàn job

Dùng staging/dataset version:

1. Nạp file thành nhiều transactions vào staging có `import_id`/`dataset_version`.
2. Validate từng chunk và cuối job.
3. Reconcile row count, duplicate, source checksum, FK/business invariants.
4. Chỉ khi hoàn tất, trong một transaction ngắn cập nhật metadata `published_version` hoặc thực hiện cutover đã thiết kế.
5. Reader chỉ dùng `published_version`, không thấy dữ liệu chưa được công bố.

Đừng dùng một transaction khổng lồ cho toàn ingest nếu snapshot/lock/WAL budget không cho phép. Cần hiểu metadata cutover và reader snapshots để tránh phiên đọc trộn versions.

### Bài 6 — Chọn batch bằng metrics

Không dùng row count làm đại diện duy nhất vì row sizes/index/JSONB/triggers/FPI khác nhau. Nên đo:

- WAL bytes/batch và WAL MiB/s.
- Batch latency/COMMIT latency.
- API p95/p99.
- Replica receive/replay lag.
- Archive backlog/WAL retained disk.
- Lock waits/deadlocks.
- CPU/I/O/dirty writes/checkpoints.
- Autovacuum/dead tuples.
- Pool active/pending và connection count.

Chọn size/concurrency sao cho cả workload nghiệp vụ lẫn import nằm trong ngân sách.

### Bài 7 — COMMIT trong function

Function PL/pgSQL thông thường không được tự `COMMIT`/`ROLLBACK` giữa các iterations. Chuyển việc chia transaction sang **caller** (Java/psql/script) hoặc dùng procedure có transaction control trong context được cho phép.

Nếu dùng procedure, `CALL` phải ở ngữ cảnh top-level/chuỗi call phù hợp; **không bọc CALL trong một explicit BEGIN transaction block** rồi mong procedure COMMIT nội bộ chạy bình thường. Còn cần xét hạn chế của exception blocks, procedure attributes và version.

### Bài 8 — COPY vs \copy

`COPY ... FROM '/home/user/orders.csv'` tìm file **trên filesystem PostgreSQL server**, không phải laptop client; role có thể còn thiếu server-file privileges.

Trong psql trên laptop, dùng dạng:

~~~text
\copy wal_batch_lab.order_stage (import_id,source_row_no,order_id,customer_id,amount,order_status) FROM '/home/user/orders.csv' WITH (FORMAT csv, HEADER true)
~~~

Đường dẫn là local file path của client psql. `\copy` là psql meta-command, không gửi nguyên vào JDBC Statement.

### Bài 9 — COPY gặp lỗi giữa file

Một COPY đơn là một statement trong transaction; các rows trước lỗi **không tự commit từng dòng**. Khi statement/transaction bị abort, dữ liệu chưa commit không trở thành rows hợp lệ; nhưng chi phí WAL/storage đã phát sinh có thể còn cần VACUUM.

Để có checkpoint mỗi 10.000 rows, chia input thành 10.000-row chunks, dùng mỗi chunk một COPY command trong transaction riêng và cập nhật import progress **cùng transaction**.

### Bài 10 — Raw staging cho CSV lỗi numeric

Không. Vì cột staging là `numeric`, COPY cố cast string `not-a-number` và có thể thất bại **trước khi row tồn tại để query**. Nếu cần inspect những giá trị malformed, dùng staging raw columns dạng text:

~~~sql
CREATE TABLE wal_batch_lab.raw_order_stage (
    import_id bigint,
    source_row_no bigint,
    order_id_text text,
    amount_text text,
    status_text text
);
~~~

Sau đó validate format/cast an toàn, quarantine malformed rows trước khi đưa vào typed staging. Không dùng regex đơn giản làm đảm bảo mọi numeric formats/overflow được cast an toàn; cần các bước validation/exceptions tương thích.

### Bài 11 — Transaction có checkpoint

~~~sql
BEGIN;

INSERT INTO wal_batch_lab.order_stage
    (import_id,source_row_no,order_id,customer_id,amount,order_status)
VALUES
    (9001,10,210,21,10.00,'new'),
    (9001,11,211,22,20.00,'paid')
ON CONFLICT (import_id,source_row_no) DO NOTHING;

UPDATE wal_batch_lab.import_jobs
SET last_committed_row=11,
    status='running',
    updated_at=clock_timestamp()
WHERE import_id=9001;

COMMIT;
~~~

Cần đảm bảo toàn bộ source rows 1..11 đã xử lý thành công nếu dùng watermark tuần tự, không nhảy tới 11 khi còn missing ranges. Với retry, `DO NOTHING` cần payload consistency validation.

### Bài 12 — Checkpoint tiến trước dữ liệu

Nếu metadata đã commit row 50000 nhưng rows 40001..50000 chưa insert, lần resume bỏ qua range chưa nạp → **mất dữ liệu**. Đúng là:

~~~sql
BEGIN;
-- INSERT/COPY chunk và validate/merge.
UPDATE wal_batch_lab.import_jobs SET last_committed_row=50000
WHERE import_id=9001;
COMMIT;
~~~

Nếu bất kỳ bước nào thất bại, ROLLBACK cả chunk và checkpoint. Với multi-workers out-of-order, cần completed-range tracking trước khi nâng watermark.

### Bài 13 — Retry sau unknown commit

Primary key staging `(import_id,source_row_no)` ngăn cùng logical source row bị lưu hai lần. Khi reconnect, kiểm tra progress/row presence và retry idempotently.

Nhưng `ON CONFLICT DO NOTHING` có thể che trường hợp source row đã bị thay đổi, mapping sai hoặc job ID reused cho file mới. Nên lưu checksum/file version và so sánh payload để phân biệt duplicate cùng nội dung với conflict nghiệp vụ.

### Bài 14 — Payload conflict

Không nên bỏ qua. Nếu key (9001,25) đã có amount=100 nhưng retry gửi 200, đây không phải replay tương đương. Có thể:

- Lưu `source_checksum` cho file/row.
- Query payload hiện có khi conflict.
- Raise conflict/reject nếu hash/values khác.
- Dùng import_id duy nhất cho mỗi immutable source object/version.
- Kiểm tra business version để quyết định update được phép hay không.

`ON CONFLICT DO NOTHING` chỉ phù hợp khi contract rõ ràng cho phép bỏ qua mọi duplicate keys, kể cả payload khác — thường không phù hợp dữ liệu tiền.

### Bài 15 — Nhiều source rows cùng destination key

Một `INSERT ... ON CONFLICT DO UPDATE` có thể báo lỗi cardinality vì cùng một command muốn tác động cùng destination row nhiều lần.

Có thể dedupe:

~~~sql
WITH dedup AS (
    SELECT DISTINCT ON (order_id)
        order_id,customer_id,amount,order_status
    FROM wal_batch_lab.order_stage
    WHERE import_id=9001
      AND order_id IS NOT NULL
    ORDER BY order_id,source_row_no DESC
)
INSERT INTO wal_batch_lab.orders
    (order_id,customer_id,amount,order_status)
SELECT order_id,customer_id,amount,order_status
FROM dedup
WHERE customer_id IS NOT NULL
  AND amount >= 0
  AND order_status IN ('new','paid','cancelled')
ON CONFLICT (order_id) DO UPDATE
SET
    customer_id=EXCLUDED.customer_id,
    amount=EXCLUDED.amount,
    order_status=EXCLUDED.order_status;
~~~

Ở đây chọn source_row_no lớn nhất **theo quy tắc giả định**. Nếu thứ tự nguồn không phản ánh freshness, phải dùng source version/event timestamp có tie-breaker và concurrency policy phù hợp.

### Bài 16 — LSN delta

~~~sql
SELECT
    pg_wal_lsn_diff(v_after::pg_lsn, v_before::pg_lsn) AS wal_bytes,
    pg_wal_lsn_diff(v_after::pg_lsn, v_before::pg_lsn)
        / 1024 / 1024 AS wal_mib;
~~~

`v_before`/`v_after` ở đây là placeholders cho LSN thực tế, không phải SQL chạy nguyên nếu chưa khai báo biến/bind parameters. Đo tại hai mốc trước và sau COMMIT. Delta là WAL **toàn cluster giữa hai mốc**, có thể chứa writes của sessions khác, background activity và commit records.

### Bài 17 — pg_stat_wal

~~~sql
SELECT wal_bytes,wal_fpi,wal_records,stats_reset
FROM pg_stat_wal;
~~~

Để tính delta, ghi hai mẫu cùng `stats_reset`. Nếu `stats_reset` đổi, counters không còn cùng baseline, không được lấy Y-X như một lượng WAL hợp lệ. Có thể cần chờ statistics cập nhật hoặc lấy samples đủ dài để giảm nhiễu.

### Bài 18 — pg_wal đầy

**Không xóa WAL segments bằng tay.** Kiểm tra:

1. Replication slots bị giữ `restart_lsn` quá cũ.
2. Physical standby receive/replay lag.
3. Archive failures/backlog.
4. WAL generation tăng từ job mới.
5. Checkpoint/WAL retention settings như `wal_keep_size`, `max_wal_size`.
6. Backup/replication consumers đang ngừng.

Dừng/điều tiết ingest an toàn ở batch boundary, sửa nguyên nhân giữ WAL và chuẩn bị disk headroom.

### Bài 19 — max_wal_size không phải hard limit

Không chắc PostgreSQL lỗi. `max_wal_size` là một mốc checkpoint/WAL management, không phải disk quota cứng. WAL còn có thể cần giữ do archiving chưa hoàn tất, replication slots, `wal_keep_size` và recovery-related requirements. Phải chẩn đoán retention source trước khi tăng cấu hình.

### Bài 20 — FPI và checkpoint

Với `full_page_writes`, lần sửa trang đầu sau checkpoint trong các điều kiện phù hợp có thể ghi full-page image để chống torn writes. Job touch nhiều pages sau checkpoint làm `wal_fpi`/`wal_bytes` tăng theo nhịp.

**Không tắt full_page_writes tùy tiện**: rủi ro crash recovery và hỏng dữ liệu. Đo checkpoint frequency, FPI, WAL compression, storage I/O và batch rate.

### Bài 21 — wal_compression

`wal_compression` có thể nén full-page images khi workload tạo nhiều FPI, giảm WAL bytes/network/archive/replication load, đổi lại CPU nén/giải nén và phụ thuộc dữ liệu/codec/version.

Không phải mọi UPDATE được giảm cùng tỷ lệ: nếu WAL chủ yếu là logical records nhỏ hoặc dữ liệu khó nén, lợi ích có thể ít. Benchmark end-to-end.

### Bài 22 — UPDATE tối đa hai hàng

~~~sql
WITH todo AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 2
)
UPDATE wal_batch_lab.orders AS o
SET order_status='paid',
    updated_at=clock_timestamp()
FROM todo AS t
WHERE o.order_id=t.order_id
RETURNING o.order_id,o.order_status;
~~~

Không có `UPDATE ... LIMIT` trực tiếp. Nếu có concurrent workers, có thể cần `FOR UPDATE SKIP LOCKED` và recheck điều kiện DML.

### Bài 23 — SKIP LOCKED

~~~sql
WITH todo AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='new'
    ORDER BY order_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
UPDATE wal_batch_lab.orders AS o
SET order_status='paid'
FROM todo AS t
WHERE o.order_id=t.order_id
  AND o.order_status='new'
RETURNING o.order_id;
~~~

Nếu các rows còn lại đang bị transaction khác lock, CTE có thể trả 0 dù vẫn còn công việc. Cần worker retry/poll, terminal reconciliation và coordination. `SKIP LOCKED` có inconsistent-view semantics, không thích hợp cho mọi report.

### Bài 24 — UPDATE cùng giá trị

Có. UPDATE có thể tạo heap tuple version mới, WAL, index maintenance theo điều kiện, ngay cả `SET status=status`. Nếu chỉ muốn chuyển khác-paid sang paid:

~~~sql
UPDATE wal_batch_lab.orders
SET order_status='paid',
    updated_at=clock_timestamp()
WHERE order_id=101
  AND order_status IS DISTINCT FROM 'paid';
~~~

`IS DISTINCT FROM` xử lý NULL-safe, dù trong lab `order_status` là NOT NULL.

### Bài 25 — DELETE tối đa 1.000 rows

~~~sql
WITH doomed AS (
    SELECT order_id
    FROM wal_batch_lab.orders
    WHERE order_status='cancelled'
    ORDER BY order_id
    LIMIT 1000
)
DELETE FROM wal_batch_lab.orders AS o
USING doomed AS d
WHERE o.order_id=d.order_id
RETURNING o.order_id;
~~~

MVCC DELETE không thu nhỏ ngay data file. Old tuple versions trở thành reclaimable khi không còn snapshot cần chúng; autovacuum/VACUUM có thể tái sử dụng space, nhưng không nhất thiết trả space cho OS. Với retention cực lớn, partition lifecycle có thể hiệu quả hơn.

---

## 46. Lời giải — bài 26 đến 50

### Bài 26 — Retention bằng partition

Khi một partition chứa toàn bộ rows hết hạn, detach/drop partition có thể tránh DML DELETE từng row, tránh tạo vô số dead tuples cần VACUUM. Tuy nhiên cần review:

- FK/constraints và dependencies.
- Locking khi DETACH/DROP.
- Per-row DELETE audit trigger không được gọi như một loạt DELETE.
- Replica/PITR và schema changes.
- Backup/restore policy cho dữ liệu retention.
- Partition boundaries có khớp ngày retention không.
- Cutover, quyền và rollback plan.

Không DROP một partition đang chứa cả dữ liệu còn hiệu lực.

### Bài 27 — Keyset thay OFFSET sâu

`OFFSET 5000000` yêu cầu bỏ qua lượng rows lớn và dễ nhạy với concurrent inserts/deletes. Keyset:

~~~sql
SELECT order_id,customer_id,amount
FROM wal_batch_lab.orders
WHERE order_id > 5000000
ORDER BY order_id
LIMIT 1000;
~~~

`5000000` trong query chỉ là ví dụ **last_id thực tế**, không phải offset. Đặt last_id bằng ID cuối được xử lý/commit. Sử dụng index PK để tối ưu khi planner phù hợp.

### Bài 28 — Concurrent insert có key nhỏ hơn watermark

Nếu job đã vượt ID 1000, row mới ID 900 sẽ không được thấy qua `WHERE id>1000`. Nếu yêu cầu snapshot dữ liệu tại một thời điểm, cần một nguồn cố định/snapshot, watermark version/created_at phù hợp hoặc một transaction consistent-snapshot với trade-offs về long-running transaction. Nếu phải bắt changes đồng thời, cần CDC/change capture hoặc reconciliation pass, không chỉ keyset đơn giản.

### Bài 29 — Replica monitoring

~~~sql
SELECT
    application_name,
    state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    replay_lag
FROM pg_stat_replication;
~~~

Khi replay lag tăng:

1. Giảm số workers và tổng WAL MiB/s.
2. Chia batch nhỏ hơn hoặc pause ở commit boundary để standby catch up.
3. Điều tra standby CPU/I/O/network và archived WAL/slot backlog.
4. Không chấp nhận read-your-writes trên replica nếu đã vượt SLA, route read phù hợp.
5. Nếu không có rows ở `pg_stat_replication` mà kỳ vọng standby, kiểm tra connection/replication health trước khi kết luận lag bằng 0.

### Bài 30 — Timestamp lag không tuyệt đối

`pg_last_xact_replay_timestamp()` cho thời gian commit transaction được replay cuối cùng. Nếu primary nhàn rỗi hàng giờ, timestamp cũ **không có nghĩa standby đang trễ hàng giờ**. Đo thêm:

~~~sql
SELECT pg_last_wal_receive_lsn(),
       pg_last_wal_replay_lsn();
~~~

Trên primary, dùng `pg_stat_replication` và LSN byte differences; kết hợp health/heartbeats phù hợp. Không dùng một timestamp chênh lệch như chứng cứ duy nhất.

### Bài 31 — Replication slot backlog

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        restart_lsn
    ) AS wal_bytes_from_restart
FROM pg_replication_slots
WHERE restart_lsn IS NOT NULL;
~~~

Inactive slot có thể do maintenance của một connector quan trọng. Drop slot thiếu kiểm soát có thể làm logical/physical consumer không tiếp tục được từ LSN cũ. Phải xác định owner, target, expected restart và recovery/resync plan.

### Bài 32 — Archive backlog

Các nguyên nhân:

- Archive destination full/unreachable.
- Network/object storage latency.
- `archive_command` lỗi permissions/config.
- Archive bandwidth thấp hơn WAL production rate.
- Retry pipeline và retention/destination failures.

Giảm batch size chỉ giúp dàn đều bursts nếu tổng WAL MiB/s còn vượt capacity thì backlog vẫn tăng. Có thể phải giảm **tổng ingest rate**, khôi phục archive pipeline và đảm bảo disk headroom. Không xóa WAL cần cho PITR.

### Bài 33 — UNLOGGED phù hợp có điều kiện

Phù hợp khi:

- Raw staging là cache tái tạo hoàn toàn từ immutable source.
- Không cần physical standby chứa dữ liệu đó.
- Crash làm mất staging không ảnh hưởng published destination/checkpoint.
- Có runbook reload sau restart.

Không phù hợp với:

1. Payments/orders là dữ liệu duy nhất.
2. Import progress/checkpoint cần durability.
3. Tables cần physical replication.
4. Dữ liệu không thể re-ingest.
5. SLO/RPO không cho phép mất staging.

UNLOGGED giảm WAL data writes phù hợp nhưng không tạo “zero WAL mọi thứ”.

### Bài 34 — synchronous_commit

`synchronous_commit=off` **không** ngừng WAL generation. Nó có thể đổi mức đảm bảo khi COMMIT được xác nhận, tăng rủi ro mất các recent acknowledged commits khi crash.

Với payment hay business transactions yêu cầu durability, thay setting này không thể là tối ưu vô hại. Cần review RPO, replication policy, unknown commit outcomes, idempotency và failure cases.

### Bài 35 — DELETE và VACUUM

DELETE dưới MVCC để lại old row versions/index entries cần cleanup khi an toàn. File chưa giảm ngay; free space có thể được tái sử dụng sau VACUUM.

~~~sql
VACUUM (ANALYZE) wal_batch_lab.orders;
~~~

Đây là lệnh maintenance riêng phù hợp trên lab/maintenance window. Nó giúp reclaim dead tuples và cập nhật planner stats. `VACUUM FULL` rewrite table với locking và storage/WAL costs lớn; không chạy sau mỗi batch khi không thật sự cần.

### Bài 36 — Index amplification

Mỗi INSERT có thể cập nhật các indexes thích hợp, tăng WAL records, buffer writes, CPU và lock/contention. 15 indexes làm workload khác bảng chỉ có PK.

Không drop mọi indexes/FKs tùy tiện vì:

- Có indexes bảo đảm UNIQUE/PK.
- FKs/integrity cần được giữ.
- Rebuild indexes cũng tạo WAL, I/O, disk và locks.
- Live readers có thể bị chậm khi thiếu indexes.
- Data có thể trùng/sai trong giai đoạn bỏ constraints.

Chọn indexes tối thiểu thực sự cần, staging/cutover theo plan và benchmark toàn pipeline.

### Bài 37 — JDBC batch

Pseudocode:

~~~java
String sql =
    "INSERT INTO wal_batch_lab.orders " +
    "(order_id, customer_id, amount, order_status) " +
    "VALUES (?, ?, ?, ?) " +
    "ON CONFLICT (order_id) DO NOTHING";

boolean previousAutoCommit = connection.getAutoCommit();
try {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(sql)) {
        int count = 0;
        for (Order row : rows) {
            ps.setLong(1, row.id());
            ps.setLong(2, row.customerId());
            ps.setBigDecimal(3, row.amount());
            ps.setString(4, row.status());
            ps.addBatch();

            count++;
            if (count == 2000) {
                ps.executeBatch();
                connection.commit();
                count = 0;
            }
        }

        if (count > 0) {
            ps.executeBatch();
            connection.commit();
        }
    }
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(previousAutoCommit);
}
~~~

Đây là **pseudocode logic**, không phải code production hoàn chỉnh: sau executeBatch cần `clearBatch()` theo driver API và error handling hợp lệ, đảm bảo mọi branch rollback/close; các loops nên bọc thành **mỗi chunk một transaction với checkpoint tương ứng**. Đừng đặt state/reset không bảo đảm khi connection hỏng; framework/pool transaction manager có thể xử lý transaction thay application.

`executeBatch()` không tự đảm bảo toàn bộ calls là **một server SQL statement** hay transaction nếu autoCommit scope sai. Mọi batch phải có transaction ownership rõ và idempotent retry.

### Bài 38 — Giảm batch nhưng tăng concurrency

Không chắc WAL rate giảm. Trước: 2 workers × 10.000 rows/batch; sau: 10 workers × 2.000 rows/batch. Số rows xử lý đồng thời có thể tương đương, và throughput per second thậm chí lớn hơn.

Policy:

- Đo rolling 30–60s WAL bytes/s, replica replay lag và API latency.
- Nếu lag/disk/latency vượt ngưỡng, **giảm tổng concurrency** hoặc giới hạn rows/s.
- Giảm batch size để rút ngắn transaction/lock lifetime.
- Chỉ tăng dần sau khi các metrics ổn nhiều chu kỳ.
- Giữ hard stop khi `pg_wal` gần disk exhaustion.
- Retry/backoff với jitter, không chạy hai bộ điều khiển cùng đẩy tải ngược nhau.

### Bài 39 — Timeouts

| Setting | Đối tượng |
|---|---|
| `lock_timeout` | Thời gian chờ lock |
| `statement_timeout` | Thời gian thực thi statement |
| `idle_in_transaction_session_timeout` | Session giữ transaction mở nhưng idle quá lâu |

Nếu lô timeout và transaction fail, **không tiến checkpoint**. Caller rollback, phân loại lỗi và retry khi hợp lệ. Nếu checkpoint đã commit từ một transaction khác trước DML, thiết kế đã có bug.

### Bài 40 — LSN vs pg_stat_wal

- `pg_wal_lsn_diff()` tính byte distance giữa hai WAL positions.
- `pg_stat_wal.wal_bytes` là thống kê WAL bytes được thu thập, có reset/snapshot behavior, cùng các counters FPI/records.

Cả hai thường quan sát **global server WAL**, không tự tách theo importer. Với live workload, cần đo controlled window, đánh dấu start/end và chỉ dùng bytes/batch như ước lượng có attribution uncertainty.

### Bài 41 — Export consistency

Nhiều transactions READ COMMITTED có snapshots khác nhau; giữa các chunks có thể có inserts/updates/deletes. Keyset hạn chế OFFSET drift nhưng không tự cung cấp một snapshot nhất quán.

Một transaction REPEATABLE READ có thể cho snapshot ổn định hơn, nhưng export kéo dài hàng giờ có thể giữ snapshot ảnh hưởng VACUUM và tài nguyên. Với backup database lớn, dùng backup/pg_dump hoặc giải pháp snapshot phù hợp thay vì tự viết 500 SELECTs thiếu consistency contract.

### Bài 42 — CSV không phải backup đầy đủ

CSV export của một bảng không lưu đủ:

- Schema DDL.
- Indexes.
- PK/FK/CHECK constraints.
- Triggers, functions.
- Sequences và current values.
- Privileges/ownership.
- Extensions/settings, database-wide objects.
- Consistency across nhiều tables.

Dùng `pg_dump` hoặc chiến lược backup được kiểm thử restore theo mục tiêu; CSV phù hợp data interchange, không phải full backup.

### Bài 43 — Lock/API latency khi backfill

Kiểm tra:

1. p95/p99 và throughput API.
2. Lock waits và `pg_stat_activity.wait_event`.
3. Batch duration và transaction age.
4. Rows/s, WAL MiB/s, checkpoint/FPI.
5. Index scans và query plans.
6. Autovacuum activity/dead tuples.
7. Replica lag, archive backlog, disk free.
8. Worker count/pool pressure/hot rows.

Giảm workers, giảm batch size, thêm pauses ở boundaries, xử lý theo key ranges ít tranh chấp, bảo vệ timeout/lock_timeout phù hợp. Nếu job vẫn không đáp ứng SLO, pause và thiết kế lịch ngoài giờ hoặc phương án build-and-cutover.

### Bài 44 — Crash sau batch 72

Checkpoint hiển thị 710.000 nhưng kế hoạch 72 batches × 10.000 = 720.000. **Không được mặc định** chạy từ 710.001 hoặc 720.001 khi chưa kiểm tra commit outcome.

Các bước:

1. Đọc authoritative checkpoint trong DB sau reconnect.
2. Kiểm tra row keys/source rows tương ứng với batch 72.
3. Xem transaction atomicity: checkpoint có được update trong **cùng transaction** không?
4. Đối chiếu checksum/source version; xác nhận batch boundaries.
5. Nếu checkpoint=710000 và data batch 72 chưa có, retry idempotently.
6. Nếu data batch 72 đã tồn tại nhưng checkpoint chưa lên, thiết kế metadata có vấn đề hoặc có external progress; reconcile và sửa trước khi tiếp.
7. Không tạo duplicate side effects/outbox events.
8. Chỉ resume khi xác định được trạng thái committed tương ứng.

### Bài 45 — Đề xuất tắt durability/autovacuum

Rủi ro:

- `fsync=off`: crash/power loss có thể gây dữ liệu không nhất quán/corruption.
- `full_page_writes=off`: giảm bảo vệ torn-page writes/crash recovery.
- Hạ `wal_level`: có thể ảnh hưởng physical/logical replication/PITR, cần review/restart theo version.
- Tắt autovacuum: dead tuple bloat, wraparound risk và mất khả năng cleanup.

Thay thế:

1. Chunked COPY/INSERT SELECT và key-based DML.
2. Batch transaction boundaries ngắn.
3. Staging hợp lý, UNLOGGED chỉ khi tái tạo được.
4. Loại indexes thật sự không cần theo kế hoạch được phê duyệt.
5. Checkpoint/WAL compression tuning theo metrics.
6. Điều tiết tổng write rate/worker concurrency.
7. Đảm bảo archive/standby throughput và disk headroom.
8. Reconcile/vacuum/analyze sau load khi phù hợp.

### Bài 46 — WAL retained tăng dù ingest rate không đổi

Ưu tiên:

1. Pause/throttle importer nếu free disk quá thấp.
2. Xem archive failures và sửa archive destination/config/permissions.
3. Xem replication slot owner/consumer và lý do inactive.
4. Đo `restart_lsn` backlog và standby health.
5. Đảm bảo disk headroom trong lúc phục hồi, tránh remove WAL bằng tay.
6. Chỉ resume khi archive/consumer bắt đầu catch up và retention pressure hạ.

Tăng `max_wal_size` vô hạn không giải quyết slot/archiver stuck; chỉ dời thời điểm disk exhaustion hoặc làm checkpoint behavior khác. Có thể cần tăng disk có kiểm soát như biện pháp tạm, không thay root-cause fix.

### Bài 47 — Thiết kế ingest CSV 100 GiB

Đề xuất:

1. Đặt immutable source object/version/checksum trong object store có quyền phù hợp.
2. `import_jobs(import_id,source_uri,checksum,status,...)`; `import_chunks(import_id,chunk_id,start_offset,end_offset,checksum,status)`.
3. Đọc chunks bounded size; normalize encoding/CSV, stream COPY tới staging (logged hoặc unlogged **chỉ nếu có reload plan**).
4. Validate required fields, data types, business rules; quarantine rows lỗi với sanitized source line references.
5. Deduplicate theo `source_event_id` được enforce UNIQUE tại destination; xác minh payload/version khi duplicate.
6. Mỗi chunk transaction: merge valid rows, ghi accepted/rejected counts và marked committed chunk status cùng transaction.
7. Khi COMMIT response lost, đọc chunk status và destination keys để đối chiếu; không blind replay.
8. Reconcile tổng source rows = accepted + rejected + duplicates theo policy; không chấp nhận “silent loss”.
9. Monitor WAL bytes/batch, MiB/s, `pg_wal` disk, slots/archive, replica lag, locks, API latency, dead tuples.
10. Điều tiết concurrency/batch theo budget và dừng ở boundary khi nguy cơ disk/lag.
11. Nếu dữ liệu chỉ được công bố khi toàn job hoàn thành, dùng dataset version publish flag trong transaction cuối.
12. Sau job, chạy ANALYZE/reconciliation và lưu report/rollback plan.

### Bài 48 — Retention hàng tỷ rows

**Batched DELETE**:

- Không cần thiết kế partition trước nếu schema hiện tại là table thường.
- Có thể điều tiết lô để giữ locks ngắn hơn.
- Nhưng tổng DELETE tạo WAL/dead tuples/index cleanup lớn và dễ gây replica lag khi xóa hàng tỷ rows.
- Cần vacuum/reclamation; không trả disk về OS ngay.

**Partition lifecycle**:

- Tốt nếu dữ liệu phân bố theo retention key và partitions cũ có thể xóa toàn bộ.
- Detach/drop có thể tránh per-row DML cost nhưng có DDL locks/dependencies/audit implications.
- Cần migration từ table cũ sang partitioned design với dual-write/cutover, validation và capacity plan.

Runbook:

1. Đo size, WAL bytes/row, indexes/trigger/constraints, current replication lag.
2. Định nghĩa retention/legal holds/audit.
3. Nếu chưa partitioned, trong ngắn hạn DELETE theo keyset nhỏ, throttle theo WAL/disk/latency.
4. Lập kế hoạch partitioning trong maintenance/online migration riêng.
5. Monitor dead tuples/autovacuum, archive/slots, p99.
6. Validate dữ liệu hết hạn, backup/restore, rollback/cutover.
7. Không drop partition khi chứa data còn cần giữ.
8. Sau chuyển đổi, tự động hóa lifecycle có approvals/alerts và kiểm thử staging.

### Bài 49 — COMMIT unknown và webhook

Không gọi webhook trực tiếp như một bước “chắc chắn sau COMMIT” dựa trên response mà client có thể mất. Dùng **transactional outbox**:

~~~sql
BEGIN;

-- DML nghiệp vụ.
-- INSERT INTO outbox(event_id unique, payload, status='pending');
-- UPDATE import chunk checkpoint.

COMMIT;
~~~

Worker khác chỉ đọc outbox **đã commit** rồi gửi webhook. Với event_id/idempotency key, webhook receiver deduplicate; worker retry nếu mất response và có dead-letter/reconciliation. Khi COMMIT outcome unknown, reconnect, tra outbox+progress thay vì phát webhook mới ngay. Đây là cách bảo toàn “DB state + intent to send” trong một transaction, nhưng external delivery vẫn thường cần at-least-once + idempotency, không tự exactly once.

### Bài 50 — Runbook WAL 300 MiB/s và sự cố đồng thời

Ưu tiên theo safety:

1. **Báo incident** và xác nhận API impact, disk free, replica RPO/RTO, archive status.
2. **Tạm dừng importer ở commit boundary** hoặc giảm workers ngay; không tiếp tục ở 300 MiB/s khi archive/replication không theo kịp.
3. Lấy snapshot monitoring: `pg_stat_wal`, current LSN, `pg_stat_replication`, `pg_replication_slots`, `pg_stat_archiver`, `pg_stat_activity`, checkpoints/IO.
4. Phân biệt **WAL generation pressure** với **retention pressure**; cả hai có thể đang xảy ra.
5. Sửa archive destination/command/path/network hoặc capacity; theo dõi sự tiến triển của last_archived_wal/time.
6. Xác định slot owner, vì sao lag 100 GiB, khả năng consumer catch up và khôi phục; **không drop slot** không có kế hoạch.
7. Bảo đảm headroom disk, không xóa thủ công `pg_wal`; nếu cần tăng disk tạm thời, thực hiện theo runbook.
8. Kiểm tra long transactions, lock waits và user-facing p99; nếu cần cancel/rollback batch gây sự cố, phân loại commit outcome, không tự terminate sessions vô tội vạ.
9. Cho autovacuum cơ hội reclaim dead tuples sau commits, đánh giá ANALYZE; không chạy `VACUUM FULL` trong giờ cao điểm chỉ để giảm disk.
10. Đối chiếu batch checkpoint, keys và source checksum sau pause/failure; xử lý uncertain COMMIT bằng idempotency.
11. Resume canary nhỏ, giảm batch size/concurrency, áp WAL MiB/s/replica lag/disk thresholds.
12. Chỉ tăng tốc dần khi archive/slot/replica backlog giảm và p99 API ổn định.
13. Cuối job chạy reconciliation, kiểm tra counts/versions và tạo report.
14. Postmortem: đo write amplification, checkpoint/FPI, cấu hình monitoring/capacity và cập nhật migration playbook.

Không “chữa cháy” bằng cách tắt `fsync/full_page_writes`, hạ wal_level, drop replication slot hoặc xóa WAL file mà chưa chứng minh tính an toàn cho recovery.

---

## 47. Bốn mô hình lựa chọn nhanh

| Bài toán | Mô hình nên ưu tiên | Giới hạn cần đánh giá |
|---|---|---|
| Nhập file CSV 50 GiB | Chunked COPY → staging → validate → merge | Transaction/checkpoint, COPY errors, WAL |
| Sửa 20 triệu rows | Keyset/CTE UPDATE theo batches | Locks, WAL, dead tuples, concurrent writers |
| Xóa dữ liệu hết hạn | Partition detach/drop khi phạm vi đủ rõ | DDL locks, audit semantics, dependencies |
| Export 200 GiB | COPY TO STDOUT streaming / pg_dump tùy mục tiêu | Snapshot consistency, file storage |
| Cần giữ toàn dataset atomic | Staging + publish dataset version | Reader routing, cutover, constraints |
| Multi-worker job | FOR UPDATE SKIP LOCKED hoặc partitioned ranges | Inconsistent view, starvation, reconciliation |
| WAL pressure cao | Throttle total write rate và sửa retention bottleneck | Archive/slots/disk/checkpoint |
| Retry sau crash | Unique business IDs + checkpoint atomic | Unknown COMMIT, payload mismatch |
| Gửi sự kiện ra ngoài | Transactional outbox + idempotent worker | At-least-once delivery, consumer dedup |
| Rebuild dữ liệu lớn | Build new table + validate + cutover nếu khả thi | FK/triggers/permissions/DDL locks |

---

## 48. Tài liệu tham khảo PostgreSQL

Khi triển khai trên một major version PostgreSQL cụ thể, đối chiếu tài liệu chính thức theo version thay vì áp tất cả ví dụ từ `/current/`:

- [PostgreSQL — Populate a Database](https://www.postgresql.org/docs/current/populate.html): các phương án bulk load, COPY và indexes.
- [PostgreSQL — COPY](https://www.postgresql.org/docs/current/sql-copy.html): COPY FROM/TO, CSV, STDIN, options và giới hạn.
- [PostgreSQL — psql](https://www.postgresql.org/docs/current/app-psql.html): `\copy` và autocommit.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): multi-row INSERT, ON CONFLICT, RETURNING.
- [PostgreSQL — UPDATE](https://www.postgresql.org/docs/current/sql-update.html): UPDATE FROM và batching qua subquery/CTE.
- [PostgreSQL — DELETE](https://www.postgresql.org/docs/current/sql-delete.html): DELETE USING và subquery.
- [PostgreSQL — Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html): BEGIN/COMMIT/ROLLBACK/savepoints.
- [PostgreSQL — PL/pgSQL Transaction Management](https://www.postgresql.org/docs/current/plpgsql-transactions.html): CALL/DO/procedure transaction control.
- [PostgreSQL — Write-Ahead Log](https://www.postgresql.org/docs/current/wal.html): mục đích WAL và crash recovery.
- [PostgreSQL — WAL Configuration](https://www.postgresql.org/docs/current/wal-configuration.html): checkpoint và WAL tuning.
- [PostgreSQL — WAL Runtime Configuration](https://www.postgresql.org/docs/current/runtime-config-wal.html): wal_level, full_page_writes, wal_compression, max_wal_size, synchronous_commit.
- [PostgreSQL — pg_stat_wal](https://www.postgresql.org/docs/current/monitoring-stats.html): WAL statistics và các monitoring views.
- [PostgreSQL — WAL Functions](https://www.postgresql.org/docs/current/functions-admin.html): `pg_current_wal_lsn` và `pg_wal_lsn_diff`.
- [PostgreSQL — Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html): replication, replay và WAL streaming.
- [PostgreSQL — Replication Slots](https://www.postgresql.org/docs/current/warm-standby.html#STREAMING-REPLICATION-SLOTS): retention liên quan slots.
- [PostgreSQL — Continuous Archiving/PITR](https://www.postgresql.org/docs/current/continuous-archiving.html): archive và recovery chain.
- [PostgreSQL — VACUUM](https://www.postgresql.org/docs/current/sql-vacuum.html): dead tuple cleanup và ANALYZE.
- [PostgreSQL — Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): autovacuum và transaction wraparound.
- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): partition lifecycle.
- [PostgreSQL — UNLOGGED Table](https://www.postgresql.org/docs/current/sql-createtable.html): durability/replication trade-offs.
- [PostgreSQL — Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, waiting và deadlocks.
- [PostgreSQL JDBC Driver — Documentation](https://jdbc.postgresql.org/documentation/): JDBC batches, CopyManager và transaction handling.

Các settings, catalog columns, SQL options và replication capabilities thay đổi theo PostgreSQL/server driver versions. Hãy kiểm tra tính năng trên môi trường triển khai thật.

---

## 49. Tổng kết

**Chia lô hiệu quả là chọn một đơn vị công việc đủ lớn để tiết kiệm overhead nhưng đủ nhỏ để bảo vệ database, replication và khả năng phục hồi lỗi.** Các nguyên tắc quan trọng:

1. **WAL không phải log có thể xóa để giải phóng dung lượng.** Nó phục vụ crash recovery, backup/PITR và replication; đừng xóa `pg_wal` files bằng tay.
2. **COPY không tự commit từng dòng.** Một COPY statement có transaction scope như các SQL khác. Muốn checkpoint từng chunk, chia COPY và commit có chủ đích.
3. **Batch và transaction khác nhau.** Một vòng lặp SQL bên trong function/DO không tự COMMIT mỗi iteration; stored functions bình thường không có transaction control tùy ý.
4. **Một batch commit riêng chỉ atomic cho batch đó.** Nếu toàn dataset phải được công bố cùng lúc, dùng staging + metadata version/cutover.
5. **Checkpoint cùng transaction với data** khi cần chính xác; có idempotency keys/source checksum để xử lý retry sau unknown COMMIT.
6. **Đo WAL bằng LSN hoặc pg_stat_wal**, nhưng nhớ đó thường là WAL cluster-wide, có nhiễu từ workload khác. Kết hợp WAL MiB/s, disk, API latency, replica lag.
7. **Đừng chỉ nhìn số rows.** Indexed UPDATE, triggers, JSONB, FPI và checkpoint có thể làm WAL bytes/row rất khác nhau.
8. **Checkpoints và full-page writes** có thể làm WAL tăng theo nhịp. Không tắt `full_page_writes/fsync` tùy tiện.
9. **max_wal_size không là hard cap.** Slots, archive failures và replication lag có thể khiến WAL retained vượt mốc; điều tra nguyên nhân trước khi tăng disk/config.
10. **UPDATE/DELETE theo lô** dùng CTE chọn PK với ORDER BY/LIMIT; PostgreSQL không có `UPDATE ... LIMIT` trực tiếp.
11. **SKIP LOCKED** hữu ích cho workers cạnh tranh nhưng không chứng minh hết việc khi trả 0 rows; cần reconciliation.
12. **Keyset pagination** tránh OFFSET lớn, nhưng không tự tạo một snapshot cố định khi concurrent writes.
13. **UPDATE/DELETE để lại MVCC row versions** cần autovacuum/VACUUM; phân vùng phù hợp giúp retention rẻ hơn việc DELETE từng row.
14. **UNLOGGED/TEMP** chỉ dùng khi chấp nhận durability/replication trade-offs và có nguồn tải lại; không thay bảng nghiệp vụ đã logged.
15. **Giảm WAL burst bằng kiểm soát tổng write rate** và số workers, không chỉ giảm rows/batch trong khi tăng concurrency.
16. **External side effects** dùng outbox + idempotency; COMMIT response bị mất không chứng minh transaction đã rollback.
17. **Vận hành theo runbook:** quan sát archive/slots/replicas/locks/latency, pause ở boundary, reconcile checkpoints và resume canary.

Mô hình hành động: **phân tích source và invariants → chọn staging/publish strategy → benchmark WAL/bytes/batch → đặt transaction/checkpoint/idempotency → COPY/INSERT/UPDATE/DELETE theo keyset từng lô → đo WAL/lag/locks sau mỗi lô → điều tiết concurrency và pause khi cần → reconcile/publish → VACUUM/ANALYZE và giám sát recovery**.
