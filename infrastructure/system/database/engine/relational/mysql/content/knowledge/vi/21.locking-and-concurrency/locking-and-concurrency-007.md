# Đổi chiến lược gap lock theo mức cô lập và loại thao tác

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích gap lock, record lock, next-key lock và insert intention lock trong InnoDB.
- Phân biệt hành vi khóa của `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`.
- Nhận diện khác biệt giữa consistent read, locking read, `UPDATE`, `DELETE` và `INSERT`.
- Dự đoán khi nào một truy vấn phạm vi có thể chặn thao tác chèn hàng mới.
- Hiểu vì sao tra cứu bằng unique key thường khóa hẹp hơn range scan hoặc điều kiện trên cột không unique.
- Thiết kế index và transaction để giảm lock footprint mà vẫn bảo vệ quy tắc nghiệp vụ.
- Kiểm tra gap lock bằng hai session, `EXPLAIN` và các bảng khóa trong `performance_schema`.
- Chọn isolation level và kiểu locking read theo workload đọc/ghi thực tế.

## 1. Gap lock giải quyết vấn đề gì?

InnoDB dùng gap lock để ngăn transaction khác chèn index record vào một khoảng trống trong index. Cơ chế này quan trọng khi transaction cần bảo vệ một phạm vi dữ liệu, kể cả những hàng chưa tồn tại tại thời điểm truy vấn.

Ví dụ, một transaction đọc tất cả công việc có trạng thái `READY` rồi quyết định phân công chúng. Nếu transaction khác có thể chèn thêm một công việc `READY` vào cùng phạm vi trước khi transaction đầu kết thúc, lần đọc tiếp theo có thể thấy thêm hàng mới (phantom). Gap lock và next-key lock giúp InnoDB bảo vệ phạm vi index được quét trong các trường hợp cần thiết.

Gap lock khóa khoảng trống giữa các index record. Các gap ở biên của index cũng có thể được bảo vệ, gồm khoảng trước record đầu tiên và khoảng sau record cuối cùng (liên quan đến supremum pseudo-record). Nó không khóa một hàng dữ liệu theo cách thông thường; mục tiêu chính là ngăn chèn index record vào gap đó.

### 1.1. Ba loại khóa cần phân biệt

| Loại khóa | Phạm vi | Tác dụng chính |
|---|---|---|
| Record lock | Một index record đang tồn tại | Ngăn transaction khác sửa/xóa record theo cách xung đột |
| Gap lock | Khoảng trống giữa các index record | Ngăn transaction khác chèn index record vào khoảng trống |
| Next-key lock | Một index record cùng gap ngay trước record đó | Kết hợp bảo vệ record và ngăn chèn vào gap liên quan |

InnoDB khóa trên index record. Với bảng InnoDB, primary key là clustered index; secondary index có các entry riêng và chứa khóa chính để định vị hàng. Vì vậy, khi đọc kế hoạch khóa, cần hiểu index mà optimizer thực sự sử dụng, không chỉ nhìn tên cột trong `WHERE`.

### 1.2. Gap lock có tính chất đặc biệt

Gap lock mang tính ngăn chèn (inhibitive): mục đích của nó là ngăn một transaction khác đặt index record mới vào gap. Gap lock của các transaction khác nhau có thể cùng tồn tại trên một gap, kể cả khi metadata hiển thị chúng như shared hoặc exclusive gap lock. Chúng không xung đột với nhau theo cách shared/exclusive lock trên record thông thường.

Thao tác INSERT cần một insert intention lock trước khi chèn index record. Insert intention lock báo rằng transaction muốn chèn vào một vị trí cụ thể trong gap. Nó có thể bị gap lock hiện có chặn.

Hai transaction chèn các giá trị khác nhau vào hai vị trí khác nhau trong cùng gap thường có thể cùng tiến hành; insert intention lock được thiết kế để những lần chèn không cùng vị trí không phải chặn nhau chỉ vì chúng nằm trong một gap chung.

## 2. Chiến lược gap lock phụ thuộc isolation level

Gap lock không phải một công tắc độc lập mà ứng dụng bật/tắt tùy câu lệnh. Hành vi phụ thuộc isolation level, loại thao tác, index và access path mà InnoDB sử dụng.

### 2.1. READ COMMITTED

Ở `READ COMMITTED` (RC):

- Mỗi consistent read thông thường tạo read view mới ở đầu statement, nên hai câu SELECT trong cùng transaction có thể thấy các commit mới khác nhau.
- Gap locking cho các search/index scan thông thường được tắt; InnoDB chủ yếu khóa các index record cần thiết.
- Các ngoại lệ quan trọng vẫn có thể dùng gap lock, đặc biệt kiểm tra foreign key và duplicate-key.
- Với `UPDATE`, InnoDB có thể dùng semi-consistent read để đưa phiên bản đã commit gần nhất cho MySQL đánh giá điều kiện `WHERE`; nếu hàng phù hợp, InnoDB đọc lại và khóa hàng để cập nhật.
- Record lock trên hàng không còn phù hợp với điều kiện có thể được giải phóng sau khi đánh giá điều kiện.

RC thường giảm việc INSERT phải chờ gap lock từ range scan, nhưng không loại bỏ mọi lock wait. UPDATE/DELETE vẫn phải khóa hàng được thay đổi; kiểm tra khóa ngoại và khóa duy nhất vẫn có thể cần khóa.

MySQL yêu cầu row-based binary logging cho `READ COMMITTED`. Trước khi đổi isolation level trong hệ thống có replication/binlog, hãy kiểm tra cấu hình `binlog_format`, topology và tài liệu đúng phiên bản server.

### 2.2. REPEATABLE READ

`REPEATABLE READ` (RR) là isolation level mặc định thường gặp của InnoDB:

- Plain `SELECT` là consistent read theo snapshot của transaction và không đặt record/gap lock chỉ vì đọc.
- Locking read như `SELECT ... FOR UPDATE` hoặc `SELECT ... FOR SHARE` thường dùng next-key lock khi quét range.
- `UPDATE` và `DELETE` thường khóa các index record được quét; với điều kiện phạm vi, các gap liên quan có thể được bảo vệ bằng next-key lock.
- Tra cứu bằng toàn bộ unique key để tìm một record đang tồn tại thường chỉ cần record lock, không cần khóa gap trước record đó.

RR cân bằng giữa snapshot ổn định cho đọc và bảo vệ phạm vi cho locking read/ghi. Một plain SELECT trong RR không khóa phạm vi để ngăn INSERT; nếu nghiệp vụ cần bảo vệ phạm vi trước thao tác ghi đồng thời, cần chọn locking read hoặc một cơ chế bảo vệ khác.

### 2.3. SERIALIZABLE

Ở `SERIALIZABLE`, InnoDB tăng mức bảo vệ đọc:

- Khi `autocommit` bị tắt hoặc plain `SELECT` nằm trong transaction tường minh, InnoDB xử lý SELECT như shared locking read.
- Range scan có thể lấy next-key/gap lock để ngăn hàng mới xuất hiện trong phạm vi được bảo vệ.
- Shared lock trên record có thể khiến UPDATE/DELETE phải chờ; gap lock có thể khiến INSERT vào phạm vi phải chờ.
- Khi `autocommit = 1` và một plain SELECT là transaction đọc riêng lẻ, không có transaction nhiều statement để giữ shared lock qua các câu lệnh tiếp theo.

SERIALIZABLE có thể tăng lock wait và deadlock. Không nên nâng toàn bộ workload lên SERIALIZABLE chỉ vì muốn tránh phantom; hãy xác định phạm vi nghiệp vụ thực sự cần bảo vệ.

### 2.4. Bảng so sánh nhanh

| Tình huống | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|
| Plain SELECT | Snapshot riêng cho từng statement, không khóa hàng đọc | Snapshot ổn định trong transaction, không khóa hàng đọc | Trong transaction tường minh, thành shared locking read |
| SELECT ... FOR SHARE / FOR UPDATE trên range | Thường khóa record; không gap-lock cho search thông thường | Có thể dùng next-key/gap lock | Có thể dùng next-key/gap lock |
| UPDATE/DELETE theo range | Khóa hàng cần cập nhật/xóa; gap lock thông thường bị tắt | Có thể khóa next-key trên index range được quét | Có thể khóa next-key trên index range được quét |
| INSERT vào gap đã bị gap lock bảo vệ | Thường không bị gap lock từ search thông thường; vẫn có ngoại lệ FK/duplicate | Có thể phải chờ | Có thể phải chờ |
| FK/duplicate-key checking | Vẫn có thể dùng gap/record lock | Có khóa theo quy tắc InnoDB | Có khóa theo quy tắc InnoDB |
| Mức xung đột đọc/ghi | Thường thấp hơn | Trung bình tùy truy vấn khóa | Thường cao hơn với transaction đọc/ghi chồng lấn |

Bảng này mô tả hành vi phổ biến, không phải cam kết khóa chính xác cho mọi truy vấn. Index được chọn, điều kiện tìm kiếm, dữ liệu hiện có, loại câu lệnh và phiên bản MySQL đều có thể làm thay đổi lock footprint.

## 3. Loại thao tác quyết định cách khóa

Không thể chỉ nhìn isolation level rồi kết luận mọi câu SQL có cùng chiến lược gap lock. Cần phân biệt loại thao tác.

### 3.1. Plain consistent SELECT

Trong RR, một câu SELECT thông thường đọc từ MVCC snapshot. Nó không lấy record lock hoặc gap lock chỉ vì đọc dữ liệu:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT job_id, status
FROM jobs
WHERE status = 'READY';

-- SELECT này đọc snapshot; nó không khóa gap để ngăn INSERT.
```

Transaction khác có thể INSERT một hàng `READY` và commit. Transaction đọc vẫn nhìn thấy snapshot ban đầu khi đọc lại bằng consistent read trong cùng RR transaction.

Ở RC, mỗi statement có read view mới; câu SELECT sau có thể thấy hàng vừa commit. Ở SERIALIZABLE trong transaction tường minh, plain SELECT được chuyển thành shared locking read.

### 3.2. SELECT ... FOR SHARE và SELECT ... FOR UPDATE

Đây là locking read. `FOR SHARE` lấy shared lock; `FOR UPDATE` lấy exclusive lock trên record phù hợp. Với range scan ở RR/SERIALIZABLE, InnoDB có thể lấy next-key lock để bảo vệ cả khoảng trống.

```sql
START TRANSACTION;

SELECT job_id, status
FROM jobs
WHERE status = 'READY'
FOR UPDATE;

-- Xử lý các công việc đã khóa rồi COMMIT/ROLLBACK.
```

Ở RC, search thông thường cho locking read chủ yếu khóa record, không khóa gap; nhưng các kiểm tra khóa ngoại và duplicate-key vẫn là ngoại lệ. Vì thế, INSERT vào vị trí mới trong range có thể tiếp tục trong RC trong khi UPDATE/DELETE trên record đã bị khóa vẫn phải chờ.

### 3.3. UPDATE và DELETE

UPDATE/DELETE là thao tác ghi nên InnoDB cần khóa các hàng bị thay đổi. Với RR, điều kiện range có thể làm phát sinh next-key lock trên index range được quét, ngăn INSERT tạo phantom trong phạm vi.

Ví dụ:

```sql
UPDATE jobs
SET status = 'PROCESSING'
WHERE status = 'READY';
```

Trong RR, InnoDB có thể khóa các index record và gap trong phạm vi `status = 'READY'` theo access path. Một INSERT thêm job mới có status `READY` có thể phải chờ.

Trong RC, gap lock cho search thông thường bị tắt; các hàng thực sự được cập nhật vẫn bị khóa, nhưng INSERT một hàng mới phù hợp thường không bị chặn bởi gap lock của câu UPDATE này. Các ngoại lệ FK/duplicate-key vẫn áp dụng.

DELETE theo range có nguyên tắc tương tự: hàng bị xóa cần khóa; trong RR, gap của index range được quét có thể được bảo vệ bằng next-key lock.

### 3.4. INSERT và insert intention lock

Khi INSERT, InnoDB cần đặt index record mới vào đúng vị trí của index. Trước khi chèn, nó sử dụng insert intention lock trên gap tương ứng. Nếu một transaction khác đang giữ gap/next-key lock ngăn chèn tại vị trí đó, INSERT phải chờ.

Ví dụ:

```sql
INSERT INTO jobs (job_id, status, created_at)
VALUES (9001, 'READY', CURRENT_TIMESTAMP);
```

INSERT không tự động khóa toàn bộ gap trong bảng. Nó khóa vị trí cần chèn và tạo record mới. Các thao tác kiểm tra duplicate key và foreign key có thể phát sinh thêm khóa.

## 4. Index và access path quyết định lock footprint

InnoDB khóa các index record mà quá trình thực thi truy vấn đi qua. Điều kiện `WHERE` mô tả logic cần tìm; index và execution plan quyết định cách tìm hàng và phạm vi record/gap bị khóa.

### 4.1. Index phù hợp thu hẹp phạm vi quét

Ví dụ bảng công việc:

```sql
CREATE TABLE jobs (
    job_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    payload VARCHAR(200) NULL,
    PRIMARY KEY (job_id),
    KEY idx_jobs_status (status)
) ENGINE = InnoDB;
```

Truy vấn lấy các job đang chờ:

```sql
SELECT job_id, status, created_at
FROM jobs
WHERE status = 'READY'
ORDER BY status, job_id
FOR UPDATE;
```

Index `status` cho phép InnoDB tìm dải index của trạng thái `READY` thay vì quét toàn bộ bảng. Secondary index của InnoDB tự chứa primary key làm phần khóa phụ để định vị hàng; vì vậy `job_id` đã có thể tham gia thứ tự index mà không cần khai báo lặp lại trong index này. Trong RR, dải index được quét và gap liên quan có thể bị khóa để ngăn INSERT thêm hàng mới vào phạm vi.

### 4.2. Thiếu index có thể làm phạm vi khóa lớn

Nếu truy vấn không có index phù hợp, optimizer có thể phải quét nhiều record hoặc toàn bộ clustered index. Với locking read hoặc UPDATE/DELETE, số record được kiểm tra và khóa có thể lớn hơn mong muốn, làm tăng chặn và giảm concurrency.

Ví dụ:

```sql
EXPLAIN
SELECT job_id, status
FROM jobs
WHERE payload LIKE '%urgent%'
FOR UPDATE;
```

Điều kiện tìm kiếm có wildcard đầu chuỗi thường khó dùng B-tree index thông thường. Nếu phải quét nhiều hàng, locking read có thể có lock footprint rộng. Cân nhắc mô hình tìm kiếm khác hoặc index phù hợp với dạng truy vấn.

### 4.3. Unique point lookup có thể tránh gap lock

Trong RR, nếu điều kiện bằng sử dụng toàn bộ một unique index để tìm đúng một record đang tồn tại, InnoDB thường chỉ khóa record đó, không khóa gap trước nó:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;
```

Điều này yêu cầu `account_id` là primary key hoặc unique key và điều kiện xác định toàn bộ khóa duy nhất. Với unique index ghép `(tenant_id, external_id)`, chỉ điều kiện đủ cả hai cột mới là unique point lookup.

Nếu chỉ lọc theo một phần unique index ghép hoặc dùng cột không unique, truy vấn có thể trở thành range scan và cần khóa phạm vi rộng hơn.

Nếu unique point lookup không tìm thấy record, InnoDB có thể khóa gap tại vị trí mà record sẽ được chèn để bảo vệ việc tìm kiếm trong RR. Vì vậy, quy tắc “unique lookup chỉ record lock” áp dụng cho trường hợp tìm thấy record duy nhất, không nên suy rộng cho kết quả rỗng.

### 4.4. Kiểm tra bằng EXPLAIN

```sql
EXPLAIN
SELECT job_id, status, created_at
FROM jobs
WHERE status = 'READY'
ORDER BY status, job_id
FOR UPDATE;
```

Quan sát:

- `key`: index được chọn.
- `type`: access type như `const`, `ref`, `range` hoặc `ALL`.
- `rows`: số hàng ước lượng cần đọc.
- `Extra`: điều kiện lọc, sort hoặc thông tin bổ sung.

`EXPLAIN` giúp hiểu access path nhưng không liệt kê đầy đủ mọi lock thực tế. Muốn xác nhận khóa, kết hợp quan sát `performance_schema.data_locks`, `performance_schema.data_lock_waits` và trạng thái InnoDB trên phiên bản hỗ trợ.

## 5. Unique key, non-unique key và gap lock

Một khác biệt quan trọng của RR là unique lookup và non-unique lookup.

| Điều kiện | Hành vi khóa thường gặp trong RR locking read |
|---|---|
| `WHERE primary_key = existing_value FOR UPDATE` | Record lock trên record tìm thấy |
| `WHERE unique_key = existing_value FOR UPDATE` với toàn bộ unique key | Record lock trên record tìm thấy |
| `WHERE non_unique_key = value FOR UPDATE` | Có thể khóa các record phù hợp và gap liên quan bằng next-key lock |
| `WHERE indexed_key BETWEEN low AND high FOR UPDATE` | Quét range, có thể dùng next-key lock trên phạm vi |
| Unique lookup nhưng không tìm thấy hàng | Có thể khóa gap ở vị trí chèn để ngăn phantom |
| Tra cứu không có index phù hợp | Có thể quét nhiều record và tạo lock footprint rộng |

Không nên bỏ qua collation và NULL khi đánh giá unique key. Unique index trên cột nullable có thể cho phép nhiều giá trị NULL; điều kiện `IS NULL` không nhất thiết là unique point lookup.

## 6. Ngoại lệ ở READ COMMITTED: foreign key và duplicate-key

Quy tắc “RC tắt gap lock” chỉ đúng cho search/index scan thông thường. InnoDB vẫn có thể dùng gap lock trong một số thao tác toàn vẹn dữ liệu.

### 6.1. Foreign key check

Khi INSERT/UPDATE một hàng con, InnoDB cần xác minh hàng cha được tham chiếu tồn tại. Quá trình kiểm tra foreign key có thể đặt khóa trên index liên quan để bảo vệ tính toàn vẹn tham chiếu, kể cả ở RC.

Vì vậy, một INSERT ở RC vẫn có thể chờ transaction khác khi liên quan tới khóa ngoại. Không dùng RC với giả định mọi thao tác chèn đều không thể bị gap/record lock chặn.

### 6.2. Duplicate-key check

Khi INSERT vào unique index, InnoDB phải kiểm tra xem giá trị mới có trùng với giá trị hiện có hoặc transaction khác đang ghi hay không. Duplicate-key checking có thể sử dụng record/gap locking và tạo lock wait.

Các câu lệnh như `INSERT ... ON DUPLICATE KEY UPDATE` có đường xử lý khóa riêng vì chúng có thể chuyển thành cập nhật khi phát hiện trùng. Không suy luận hành vi của chúng giống INSERT thuần.

### 6.3. Vì sao ngoại lệ này cần thiết?

Tắt gap lock cho search thông thường ở RC giúp giảm chặn giữa các transaction đọc phạm vi và INSERT. Nhưng InnoDB vẫn phải bảo vệ constraint như foreign key và unique key; nếu không, hai transaction có thể cùng vượt qua kiểm tra rồi tạo dữ liệu vi phạm tính duy nhất hoặc tham chiếu.

## 7. Ví dụ thực hành: range lock chặn INSERT ở REPEATABLE READ

### 7.1. Chuẩn bị bảng thử nghiệm

Chạy một lần trong schema thử nghiệm:

```sql
DROP TABLE IF EXISTS jobs;

CREATE TABLE jobs (
    job_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (job_id),
    KEY idx_jobs_status (status)
) ENGINE = InnoDB;

INSERT INTO jobs (job_id, status, created_at)
VALUES
    (1, 'READY', '2026-01-01 09:00:00'),
    (2, 'READY', '2026-01-01 09:05:00'),
    (3, 'RUNNING', '2026-01-01 09:10:00'),
    (4, 'DONE', '2026-01-01 09:15:00');
```

### 7.2. Session A: khóa phạm vi READY ở RR

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT job_id, status
FROM jobs
WHERE status = 'READY'
FOR UPDATE;

-- Chưa commit; giữ transaction mở.
```

Do `status` không unique và truy vấn sử dụng index `status`, InnoDB có thể dùng next-key lock để bảo vệ các record/gap thuộc phạm vi `READY`. Secondary index InnoDB có primary key làm phần khóa phụ, nên index này cũng có thứ tự theo `job_id` trong các entry có cùng `status`.

### 7.3. Session B: chèn một job mới trong cùng phạm vi

Trong connection khác:

```sql
INSERT INTO jobs (job_id, status, created_at)
VALUES (5, 'READY', '2026-01-01 09:20:00');
```

INSERT có thể chờ Session A vì vị trí index mới nằm trong phạm vi gap đang bị khóa. Giữ Session B ở trạng thái chờ để quan sát.

Quay lại Session A:

```sql
COMMIT;
```

Sau khi Session A kết thúc transaction, Session B có thể tiếp tục nếu không có xung đột khác.

Kết quả cụ thể phụ thuộc access path, thứ tự index và dữ liệu đang có. Nếu optimizer không dùng index dự kiến, phạm vi khóa có thể khác; hãy kiểm tra `EXPLAIN` trước khi thử.

## 8. So sánh cùng thao tác ở READ COMMITTED

Kết thúc các transaction thử nghiệm trước. Đặt Session A sang RC:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT job_id, status
FROM jobs
WHERE status = 'READY'
FOR UPDATE;

-- Giữ transaction mở.
```

Session B chèn một hàng READY có `job_id` mới:

```sql
INSERT INTO jobs (job_id, status, created_at)
VALUES (6, 'READY', '2026-01-01 09:25:00');
```

Trong RC, gap lock cho search/index scan thông thường bị tắt, nên INSERT này thường không phải chờ gap lock của locking read. Các hàng READY đã tồn tại vẫn bị record lock; nếu Session B cập nhật một trong những hàng đó thì vẫn phải chờ.

Kết thúc Session A bằng `COMMIT` hoặc `ROLLBACK`. Nếu INSERT vẫn chờ, hãy kiểm tra các nguyên nhân khác như unique key, foreign key, khóa trên primary key hoặc một transaction khác. RC không loại bỏ mọi dạng khóa.

## 9. So sánh plain SELECT ở RR và RC

### 9.1. REPEATABLE READ: cùng snapshot trong transaction

Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT COUNT(*) AS ready_count
FROM jobs
WHERE status = 'READY';
```

Session B:

```sql
INSERT INTO jobs (job_id, status, created_at)
VALUES (7, 'READY', CURRENT_TIMESTAMP);
COMMIT;
```

Session A chạy lại plain SELECT:

```sql
SELECT COUNT(*) AS ready_count
FROM jobs
WHERE status = 'READY';
```

Trong cùng RR transaction, consistent read tiếp tục dùng snapshot ban đầu, nên không thấy hàng vừa commit của Session B. Plain SELECT không giữ gap lock chỉ vì đọc.

### 9.2. READ COMMITTED: snapshot mới ở mỗi statement

Lặp lại với RC:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT COUNT(*) AS ready_count
FROM jobs
WHERE status = 'READY';
```

Sau khi Session B INSERT và commit, Session A chạy lại SELECT. Ở RC, statement mới tạo read view mới nên có thể thấy hàng vừa được commit.

Điểm khác biệt này thuộc consistent read và snapshot, không phải do SELECT ở RR đã khóa phạm vi. Muốn ngăn INSERT trong khi transaction đang xử lý, cần locking read hoặc cơ chế bảo vệ phù hợp.

## 10. UPDATE/DELETE theo range: đổi isolation thì thay đổi điều gì?

Giả sử Session A chạy:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

UPDATE jobs
SET status = 'PROCESSING'
WHERE status = 'READY';

-- Giữ transaction mở.
```

Trong RR, thao tác có thể khóa next-key trên phạm vi index được quét. Session B INSERT một hàng mới với `status = 'READY'` có thể bị chặn bởi gap lock.

Nếu Session A dùng RC, gap lock của search thông thường bị tắt. Hàng đã được UPDATE vẫn bị exclusive record lock, nhưng INSERT một hàng mới trong cùng giá trị status thường không bị gap lock từ thao tác UPDATE đó chặn.

Một số điểm cần nhớ:

- UPDATE chỉ khóa hàng thực sự được cập nhật; ở RC, các hàng không còn phù hợp sau khi đánh giá điều kiện có thể được nhả khóa sớm.
- DELETE vẫn cần khóa record bị xóa.
- Foreign key cascade/check và duplicate-key check có thể bổ sung khóa.
- Một truy vấn thiếu index phù hợp có thể quét nhiều hàng, làm tăng chi phí khóa dù RC đã tắt gap lock thông thường.
- Nếu điều kiện cập nhật dựa trên một invariant phạm vi, giảm gap lock có thể làm thay đổi tính đúng đắn của logic ứng dụng.

## 11. Insert intention lock và các lần chèn đồng thời

Tạo bảng thử nghiệm có hai index record 10 và 20:

```sql
DROP TABLE IF EXISTS indexed_values;

CREATE TABLE indexed_values (
    value_key INT NOT NULL,
    PRIMARY KEY (value_key)
) ENGINE = InnoDB;

INSERT INTO indexed_values (value_key) VALUES (10), (20);
```

Giả sử gap giữa hai index record là khoảng `(10, 20)`. Hai transaction muốn chèn 13 và 17:

```sql
-- Session A
START TRANSACTION;
INSERT INTO indexed_values (value_key) VALUES (13);
-- Chưa commit.

-- Session B
START TRANSACTION;
INSERT INTO indexed_values (value_key) VALUES (17);
-- Vị trí chèn khác Session A nên không phải chờ insert intention lock của A.
COMMIT;

-- Session A
COMMIT;
```

Hai lần chèn có thể tiến hành đồng thời vì vị trí chèn khác nhau trong cùng gap; insert intention lock không chặn nhau chỉ vì cùng thuộc một khoảng.

Sau khi hai lần chèn hoàn tất, Session C có thể khóa một range:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT value_key
FROM indexed_values
WHERE value_key > 10
  AND value_key < 20
FOR UPDATE;
```

Session D thử chèn một giá trị mới trong range:

```sql
INSERT INTO indexed_values (value_key) VALUES (15);
```

INSERT có thể phải chờ Session C kết thúc transaction vì gap tương ứng đang được bảo vệ. Đây là lý do một gap lock có thể ảnh hưởng đến nhiều giá trị mới dù chưa có record tương ứng trong bảng.

Không nhầm insert intention lock với gap lock thông thường: insert intention biểu thị ý định chèn tại vị trí cụ thể; gap lock thông thường bảo vệ khoảng khỏi các lần chèn xung đột.

## 12. Chọn chiến lược theo loại nghiệp vụ

Không có một isolation level tốt nhất cho mọi workload. Hãy bắt đầu từ quy tắc nghiệp vụ và loại thao tác.

| Nghiệp vụ | Chiến lược có thể phù hợp | Lưu ý |
|---|---|---|
| Hiển thị danh sách, không cần khóa dữ liệu | Plain SELECT ở RR hoặc RC | Dựa vào MVCC; không cần gap lock chỉ để đọc |
| Đọc rồi cập nhật một hàng theo primary key | `SELECT ... FOR UPDATE` hoặc UPDATE có điều kiện | Unique point lookup giúp phạm vi khóa hẹp |
| Lấy một nhóm hàng để xử lý tuần tự | `FOR UPDATE` với index theo điều kiện lọc | RR có thể next-key lock range; RC giảm gap lock nhưng vẫn khóa record |
| Chèn hàng mới vào trạng thái/range đang được xử lý | Đánh giá RR locking read hoặc SERIALIZABLE nếu cần ngăn phantom | Phải kiểm tra gap lock và index access path |
| Tránh chặn INSERT không cần thiết trong workload ghi nhiều | Cân nhắc RC | Chấp nhận snapshot mới theo từng statement và ngoại lệ FK/duplicate |
| Bảo vệ một mã nghiệp vụ duy nhất | UNIQUE constraint/index | Không cần dùng gap lock làm lớp bảo vệ duy nhất |
| Kiểm tra số lượng rồi quyết định thêm hàng | Constraint, atomic counter, locking strategy hoặc SERIALIZABLE | Không dựa vào plain SELECT snapshot nếu cần bảo vệ phạm vi |
| Cập nhật hàng theo điều kiện số lượng | UPDATE có điều kiện như `WHERE quantity >= ?` | Kiểm tra affected rows thay vì đọc rồi ghi tách rời |

### 12.1. Ưu tiên constraint khi có thể

Nếu quy tắc có thể được mô tả bằng `PRIMARY KEY`, `UNIQUE`, `CHECK` hoặc foreign key, hãy để database bảo vệ invariant đó. Constraint hoạt động với mọi đường ghi có quyền truy cập bảng, trong khi logic chỉ nằm trong ứng dụng có thể bị bỏ qua bởi một client khác.

### 12.2. Dùng locking read cho phạm vi cần bảo vệ

Nếu transaction phải đọc một nhóm hàng rồi cập nhật nhóm đó, `SELECT ... FOR UPDATE` có thể thể hiện rõ ý định khóa. Với RR, range scan có thể dùng next-key lock để bảo vệ phantom. Với RC, gap lock thường bị tắt cho search thông thường; hãy đánh giá xem có còn đáp ứng invariant không.

### 12.3. Dùng READ COMMITTED khi giảm gap lock là mục tiêu có chủ đích

RC có thể phù hợp với workload ghi đồng thời cao, nơi việc chặn INSERT do gap lock gây ra nhiều contention và ứng dụng chấp nhận semantics của snapshot theo statement. Tuy nhiên, hãy kiểm tra:

- Các truy vấn có phụ thuộc snapshot ổn định qua nhiều statement không?
- Có logic “đọc số lượng rồi quyết định ghi” cần bảo vệ phạm vi không?
- Unique/FK check có còn tạo lock wait không?
- Cấu hình binary logging và replication có tương thích không?
- Test concurrency có cho thấy throughput/latency thực sự cải thiện không?

Đổi isolation level chỉ để hết lock wait mà không xem xét logic nghiệp vụ có thể tạo race condition.

## 13. Giảm lock footprint bằng thiết kế truy vấn

### 13.1. Dùng điều kiện có thể tận dụng index

Ưu tiên predicate sargable, ví dụ:

```sql
WHERE created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
```

thay vì bọc cột trong hàm nếu điều đó khiến index không được sử dụng:

```sql
WHERE DATE(created_at) = '2026-01-01'
```

Truy vấn thứ hai có thể khiến MySQL phải quét nhiều record hơn nếu không có functional index phù hợp. Với locking read/UPDATE/DELETE, quét rộng có thể kéo theo nhiều khóa hơn.

### 13.2. Chỉ khóa những cột/hàng cần thiết

Không dùng locking read cho toàn bảng nếu chỉ cần một hàng:

```sql
SELECT job_id, status
FROM jobs
WHERE job_id = 101
FOR UPDATE;
```

Với primary key lookup, lock footprint thường hẹp hơn range scan theo trạng thái.

### 13.3. Phân trang công việc theo khóa ổn định

Nếu worker cần lấy một số job để xử lý, có thể dùng `FOR UPDATE SKIP LOCKED` trên phiên bản hỗ trợ:

```sql
START TRANSACTION;

SELECT job_id
FROM jobs
WHERE status = 'READY'
ORDER BY job_id
LIMIT 20
FOR UPDATE SKIP LOCKED;

-- Cập nhật các job đã chọn sang PROCESSING trong cùng transaction.

COMMIT;
```

`SKIP LOCKED` bỏ qua các hàng đang bị transaction khác khóa thay vì chờ chúng. Nó hữu ích cho hàng đợi nhiều worker, nhưng trả về một view dữ liệu không nhất quán và không phù hợp cho mọi nghiệp vụ. Nó không tắt gap lock một cách tổng quát; hãy kiểm tra lock behavior, index và semantics của truy vấn trên phiên bản MySQL đang dùng.

`NOWAIT` có thể được dùng khi muốn truy vấn lỗi ngay nếu không lấy được khóa thay vì chờ. Cả `NOWAIT` và `SKIP LOCKED` điều chỉnh cách xử lý lock wait cho locking read; chúng không thay thế isolation level hay constraint.

### 13.4. Giữ transaction ngắn

Ngay cả khi index và isolation level đã phù hợp, transaction dài vẫn giữ khóa lâu. Tránh gọi HTTP, gửi email, chờ người dùng hoặc thực hiện xử lý CPU nặng trong khi transaction đang giữ lock. Thực hiện công việc ngoài database trước nếu an toàn, sau đó mở transaction ngắn để đọc/kiểm tra lại và ghi.

## 14. Quan sát gap lock và lock wait

### 14.1. Xem transaction đang mở

```sql
SELECT
    trx_id,
    trx_state,
    trx_started,
    trx_wait_started,
    trx_mysql_thread_id,
    trx_query
FROM information_schema.innodb_trx;
```

Truy vấn này giúp xác định transaction lâu, transaction đang chờ và câu SQL gần nhất được ghi nhận. Cần quyền thích hợp để đọc metadata.

### 14.2. Xem data locks trên MySQL 8.0

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY OBJECT_NAME, INDEX_NAME, LOCK_STATUS;
```

Các giá trị `LOCK_MODE` có thể chứa thông tin như `S`, `X`, `GAP`, `REC_NOT_GAP` hoặc `INSERT_INTENTION`, tùy loại lock và phiên bản. Hãy đọc cùng `INDEX_NAME` và `LOCK_DATA` để hiểu record/gap nào liên quan.

### 14.3. Xem quan hệ chờ khóa

```sql
SELECT
    requesting.ENGINE_TRANSACTION_ID AS waiting_trx,
    requesting.OBJECT_NAME,
    requesting.INDEX_NAME,
    requesting.LOCK_MODE AS waiting_lock_mode,
    blocking.ENGINE_TRANSACTION_ID AS blocking_trx,
    blocking.LOCK_MODE AS blocking_lock_mode,
    blocking.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS requesting
  ON requesting.ENGINE = waits.ENGINE
 AND requesting.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON blocking.ENGINE = waits.ENGINE
 AND blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID;
```

Các cột metadata có thể khác giữa phiên bản; xác minh schema `performance_schema` trên server mục tiêu. Không dựa vào một giá trị `LOCK_DATA` đơn lẻ để kết luận toàn bộ phạm vi gap nếu chưa xem index và access path.

### 14.4. SHOW ENGINE INNODB STATUS

```sql
SHOW ENGINE INNODB STATUS;
```

Phần `TRANSACTIONS` và `LATEST DETECTED DEADLOCK` có thể cung cấp chi tiết transaction đang chờ và deadlock gần nhất. Output là ảnh chụp tại thời điểm truy vấn; deadlock mới có thể thay thế thông tin trước đó.

## 15. Deadlock và lock wait khi thay đổi gap lock

Giảm gap lock ở RC không đồng nghĩa loại bỏ deadlock. Các transaction vẫn có thể xung đột khi cùng cập nhật record, lấy khóa theo thứ tự khác nhau, kiểm tra unique key hoặc foreign key.

Khi gặp deadlock:

1. Ghi nhận lỗi và thông tin transaction.
2. Rollback toàn bộ transaction bị thất bại.
3. Nếu nghiệp vụ an toàn để retry, bắt đầu transaction mới và chạy lại toàn bộ đơn vị công việc.
4. Giới hạn số lần retry và dùng backoff phù hợp.
5. Kiểm tra thứ tự truy cập hàng, index, phạm vi khóa và thời gian giữ transaction.

Lock wait timeout khác deadlock. Tùy `innodb_rollback_on_timeout`, timeout có thể chỉ rollback statement hiện tại hoặc toàn transaction. Ứng dụng nên rollback toàn transaction trước khi tái sử dụng connection, trừ khi có một quy trình xử lý rõ ràng khác.

Không retry vô hạn và không chỉ chạy lại câu SQL cuối cùng trong transaction đã thất bại. Các thao tác đọc trước đó và quyết định nghiệp vụ có thể cần được thực hiện lại.

## 16. Những lỗi thường gặp

| Lỗi/hiểu nhầm | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ mọi SELECT đều lấy gap lock | Plain consistent SELECT ở RR/RC thường đọc bằng MVCC, không khóa gap chỉ vì đọc | Phân biệt consistent read với locking read |
| Nghĩ READ COMMITTED không có bất kỳ gap lock nào | FK và duplicate-key checking vẫn có thể dùng gap/record lock | Kiểm tra loại thao tác và constraint |
| Nghĩ REPEATABLE READ luôn khóa khi đọc | Plain SELECT là consistent read, không phải locking read | Dùng `FOR SHARE`/`FOR UPDATE` khi cần khóa |
| Nghĩ unique equality luôn chỉ khóa record | Điều kiện phải dùng toàn bộ unique key và record phải tồn tại; lookup không tìm thấy có thể khóa gap | Xác định cardinality và trạng thái tìm thấy |
| Chỉ nhìn WHERE để đoán lock | Optimizer có thể dùng index khác hoặc full scan | Kiểm tra EXPLAIN và data_locks |
| Tắt gap lock để tăng tốc mà không xem logic | Có thể cho phép phantom/race condition trong nghiệp vụ đọc phạm vi rồi ghi | Kiểm tra invariant và test concurrency trước khi đổi RC |
| Tạo index tùy tiện | Tăng write cost và chưa chắc giảm lock footprint | Thiết kế theo access path thực tế |
| Giữ transaction mở lâu | Lock wait và deadlock tăng | Giữ transaction ngắn, không chờ tác vụ ngoài |
| Nghĩ SKIP LOCKED loại bỏ mọi gap lock | Nó chỉ thay đổi cách xử lý hàng đang bị khóa trong locking read | Đánh giá index và lock semantics riêng |

## 17. Quy trình chọn chiến lược gap lock

1. **Xác định thao tác:** plain SELECT, locking read, UPDATE, DELETE hay INSERT?
2. **Xác định invariant:** có cần ngăn hàng mới xuất hiện trong phạm vi hay chỉ cần khóa các hàng hiện có?
3. **Chọn isolation level:** RR cho snapshot ổn định; RC để giảm gap lock thông thường; SERIALIZABLE khi cần mức tuần tự hóa rộng hơn.
4. **Kiểm tra index:** xác định access path, unique/non-unique lookup và range được quét.
5. **Xem constraint:** foreign key và unique key có thể tạo khóa ngay cả ở RC.
6. **Giảm phạm vi:** dùng predicate sargable, index phù hợp và khóa đúng các hàng cần xử lý.
7. **Mô phỏng hai session:** kiểm tra UPDATE/DELETE/INSERT có chờ nhau không.
8. **Quan sát khóa:** dùng `performance_schema.data_locks`, `data_lock_waits` và InnoDB status.
9. **Đo dưới tải:** theo dõi latency, throughput, deadlock và lock wait timeout.
10. **Xác minh replication:** kiểm tra yêu cầu row-based binary logging khi dùng RC.

## 18. Checklist trước khi triển khai production

- [ ] Đã phân biệt consistent read với locking read.
- [ ] Đã hiểu khác biệt gap lock giữa RC, RR và SERIALIZABLE.
- [ ] Đã xét riêng SELECT, UPDATE, DELETE, INSERT và constraint checks.
- [ ] Đã kiểm tra index được optimizer chọn bằng EXPLAIN.
- [ ] Đã xác định unique lookup có dùng toàn bộ unique key và có tìm thấy record hay không.
- [ ] Đã kiểm tra các ngoại lệ foreign key và duplicate-key ở RC.
- [ ] Đã bảo vệ invariant bằng constraint hoặc locking strategy phù hợp.
- [ ] Đã thử nghiệm hai session trên dữ liệu tương đương production.
- [ ] Transaction ngắn và truy cập record theo thứ tự nhất quán.
- [ ] Có xử lý deadlock, lock wait timeout và retry toàn transaction.
- [ ] Đã kiểm tra row-based binlog/replication khi chọn READ COMMITTED.
- [ ] Đã theo dõi lock wait, deadlock, throughput và latency sau triển khai.

## 19. Kết luận

Gap lock bảo vệ khoảng trống trong index để ngăn transaction khác chèn record vào phạm vi đang được bảo vệ. Trong InnoDB, chiến lược gap lock thay đổi theo isolation level và loại thao tác: RC tắt gap lock cho search/index scan thông thường nhưng vẫn có ngoại lệ foreign key và duplicate-key; RR thường dùng next-key lock cho locking read và thao tác ghi theo range; SERIALIZABLE còn chuyển plain SELECT trong transaction tường minh thành shared locking read.

Index và access path quyết định phạm vi record/gap bị quét, vì vậy cũng ảnh hưởng lock wait và concurrency. Hãy phân biệt consistent read với locking read, dùng unique key và predicate có index khi phù hợp, giữ transaction ngắn và kiểm tra bằng hai session. Chọn RC để giảm gap lock chỉ khi logic nghiệp vụ và cấu hình replication chấp nhận semantics của nó; nếu cần bảo vệ phạm vi, hãy dùng constraint hoặc locking strategy đáp ứng đúng invariant.
