# ADD, DROP, TRUNCATE, REORGANIZE và COALESCE PARTITION

Partitioning chia dữ liệu của một bảng thành nhiều partition được quản lý bởi MySQL. Khi bảng được thiết kế partition đúng theo miền dữ liệu và workload, người vận hành có thể thêm vùng dữ liệu mới, loại bỏ vùng đã hết hạn, làm rỗng một partition, chia/ghép lại ranh giới hoặc thay đổi số partition của bảng HASH/KEY. Các thao tác này thường được thực hiện bằng `ALTER TABLE` và có thể tác động trực tiếp tới dữ liệu, thời gian khóa, dung lượng lưu trữ, replication và khả năng phục hồi.

Năm thao tác cần phân biệt là `ADD PARTITION`, `DROP PARTITION`, `TRUNCATE PARTITION`, `REORGANIZE PARTITION` và `COALESCE PARTITION`. Chúng không thay thế cho nhau: `DROP` loại cả định nghĩa partition lẫn dữ liệu bên trong; `TRUNCATE` giữ partition nhưng xóa dữ liệu; `REORGANIZE` phân phối lại dữ liệu giữa các partition RANGE/LIST; `COALESCE` giảm số partition HASH/KEY và phân phối lại dữ liệu. Chọn sai lệnh có thể làm mất dữ liệu hoặc tạo một đợt rebuild/flush lớn ngoài dự kiến.

Bài học này thuộc module `DATABASE_MYSQL`, nơi bạn làm chủ thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là quản lý vòng đời partition an toàn, hiểu giới hạn theo partitioning method và xác minh kết quả bằng metadata cùng dữ liệu thực tế.

Sau bài học, bạn có thể:

- Chọn đúng thao tác quản lý partition theo RANGE, LIST, HASH hoặc KEY.
- Thêm partition mới bằng `ADD PARTITION` khi điều kiện ranh giới cho phép.
- Loại partition và dữ liệu bằng `DROP PARTITION`.
- Làm rỗng dữ liệu nhưng giữ partition bằng `TRUNCATE PARTITION`.
- Chia hoặc gộp partition RANGE/LIST bằng `REORGANIZE PARTITION`.
- Giảm số partition HASH/KEY bằng `COALESCE PARTITION`.
- Hiểu tác động của `MAXVALUE`, unique key và giới hạn foreign key.
- Kiểm tra partition metadata, số hàng và query pruning.
- Lập quy trình bảo trì có kiểm soát dữ liệu, DDL, lock, backup và replication.

## 1. Chọn thao tác theo partitioning method

Các thao tác có phạm vi hỗ trợ khác nhau. Bảng dưới đây là hướng dẫn thực hành cho partitioning do người dùng định nghĩa trong MySQL:

| Thao tác | RANGE / LIST | HASH / KEY | Tác dụng chính |
| --- | --- | --- | --- |
| `ADD PARTITION` | Có | Có | RANGE/LIST: thêm miền hoặc giá trị mới; HASH/KEY: tăng số partition bằng số lượng chỉ định |
| `DROP PARTITION` | Có | Không; dùng `COALESCE` để giảm số partition | Xóa partition và toàn bộ dữ liệu trong đó |
| `TRUNCATE PARTITION` | Có | Có | Xóa dữ liệu trong partition, giữ định nghĩa partition |
| `REORGANIZE PARTITION` | Có | Không | Chia/gộp hoặc thay đổi ranh giới/nhóm giá trị, đồng thời phân phối lại dữ liệu |
| `COALESCE PARTITION` | Không | Có | Giảm số partition HASH/KEY và phân phối lại dữ liệu |

Với HASH/KEY, dùng `ADD PARTITION PARTITIONS n` để tăng thêm `n` partition; dùng `COALESCE PARTITION n` để giảm đi `n` partition. Cú pháp này khác RANGE/LIST, nơi `ADD PARTITION` khai báo định nghĩa partition mới. Không dùng `REORGANIZE PARTITION` cho HASH/KEY. Việc tăng/giảm HASH/KEY có thể phân phối lại dữ liệu và phát sinh I/O lớn; ngoại lệ về hiệu quả có thể có với LINEAR HASH/KEY.

## 2. Kiểm tra bảng partition trước khi bảo trì

Trước khi chạy DDL, xác định partitioning method, biểu thức partition và ranh giới hiện tại.

```sql
SHOW CREATE TABLE event_log;
```

`SHOW CREATE TABLE` là nguồn quan trọng để xem định nghĩa partition đầy đủ, gồm:

- `PARTITION BY RANGE`, `LIST`, `HASH` hoặc `KEY`.
- Biểu thức/cột được dùng để phân vùng.
- Tên từng partition.
- `VALUES LESS THAN` hoặc `VALUES IN`.
- `MAXVALUE` nếu có.
- Số partition của HASH/KEY.

Có thể xem metadata qua `INFORMATION_SCHEMA.PARTITIONS`:

```sql
SELECT
    PARTITION_ORDINAL_POSITION,
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_EXPRESSION,
    PARTITION_DESCRIPTION,
    TABLE_ROWS,
    DATA_LENGTH,
    INDEX_LENGTH
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'event_log'
ORDER BY PARTITION_ORDINAL_POSITION;
```

Với InnoDB, `TABLE_ROWS` là ước lượng, không phải số hàng chính xác. Khi cần xác minh số hàng trước/sau thao tác, chạy `COUNT(*)` trên phạm vi phù hợp hoặc truy vấn partition cụ thể:

```sql
SELECT COUNT(*) AS rows_in_partition
FROM event_log PARTITION (p2026_11);
```

`PARTITION (...)` trong SELECT là partition selection. Nó hữu ích cho kiểm tra hoặc truy vấn có chủ đích, nhưng không thay thế partition pruning tự động của optimizer.

## 3. Tạo bảng RANGE COLUMNS dùng trong ví dụ

Ví dụ bảng log theo ngày:

```sql
DROP TABLE IF EXISTS event_log;

CREATE TABLE event_log (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    tenant_id INT UNSIGNED NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (event_id, event_date),
    KEY idx_event_date_tenant (event_date, tenant_id)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p_before_2026_10 VALUES LESS THAN ('2026-10-01'),
    PARTITION p2026_10 VALUES LESS THAN ('2026-11-01'),
    PARTITION p2026_11 VALUES LESS THAN ('2026-12-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Với `RANGE COLUMNS(event_date)`, các partition được sắp theo ranh giới tăng dần:

- `p_before_2026_10` chứa ngày trước 01/10/2026.
- `p2026_10` chứa ngày từ 01/10/2026 đến trước 01/11/2026.
- `p2026_11` chứa ngày từ 01/11/2026 đến trước 01/12/2026.
- `pmax` chứa các giá trị còn lại từ 01/12/2026 trở đi.

Chèn dữ liệu thử:

```sql
INSERT INTO event_log
    (event_id, event_date, tenant_id, event_type, payload)
VALUES
(1, '2026-10-15', 10, 'LOGIN', JSON_OBJECT('user', 'an')),
(2, '2026-11-05', 10, 'ORDER', JSON_OBJECT('order_id', 9001)),
(3, '2026-11-20', 20, 'PAYMENT', JSON_OBJECT('amount', 125.50)),
(4, '2026-12-03', 10, 'LOGOUT', JSON_OBJECT('user', 'an'));
```

Đây là trạng thái ban đầu của fixture. Các ví dụ DDL tiếp theo là những kịch bản bảo trì riêng, không phải một migration script cần chạy liên tiếp từ đầu tới cuối. Trước mỗi thao tác, xác nhận partition được nêu vẫn tồn tại và có đúng boundary; để khôi phục fixture ban đầu, chạy lại toàn bộ phần này.

`pmax` là partition đón các giá trị chưa có partition cụ thể. Nó thuận tiện để tránh lỗi khi dữ liệu tương lai xuất hiện, nhưng khi đã có `MAXVALUE` thì không thể đơn giản `ADD PARTITION` vào phía sau nó. Muốn tạo partition tháng mới trước `pmax`, phải `REORGANIZE` partition `pmax` để tách một phần miền giá trị.

### 3.1. Lưu ý về unique key và foreign key

Với bảng partitioned, mọi cột được dùng trong partitioning expression phải xuất hiện trong mọi unique key của bảng, bao gồm primary key. Trong ví dụ, `event_date` nằm trong primary key `(event_id, event_date)`. Nếu thêm `UNIQUE(event_id)` riêng lẻ, MySQL sẽ từ chối vì unique key đó không chứa cột partitioning.

Điều này có hệ quả thiết kế: `PRIMARY KEY(event_id, event_date)` chỉ bảo đảm tổ hợp là duy nhất, không tự bảo đảm `event_id` duy nhất toàn bảng. Nếu nghiệp vụ cần ID duy nhất toàn cục, cân nhắc cấp ID không trùng ở tầng ứng dụng hoặc duy trì bảng registry không partitioned có unique key trên `event_id`.

InnoDB với user-defined partitioning không hỗ trợ foreign key constraints trên bảng partitioned; bảng partitioned cũng không thể được tham chiếu bằng foreign key theo cách thông thường. Nếu nghiệp vụ phụ thuộc FK, phải đánh giá lại mô hình dữ liệu trước khi partition. Không nên bỏ constraint mà không thay thế cơ chế bảo vệ toàn vẹn dữ liệu.

## 4. ADD PARTITION — thêm partition mới

`ADD PARTITION` có cú pháp khác nhau theo partitioning method: RANGE/LIST khai báo partition mới cùng boundary hoặc tập giá trị; HASH/KEY chỉ định số partition cần thêm.

### 4.1. ADD cho RANGE khi chưa có MAXVALUE

Với bảng RANGE không có partition `MAXVALUE`, có thể thêm partition ở cuối miền hiện tại. Ví dụ dưới đây tạo một bảng lab nhỏ rồi thêm partition tháng kế tiếp:

```sql
CREATE TABLE event_log_without_max (
    event_id BIGINT UNSIGNED NOT NULL,
    event_date DATE NOT NULL,
    PRIMARY KEY (event_id, event_date)
) ENGINE = InnoDB
PARTITION BY RANGE COLUMNS (event_date) (
    PARTITION p_before_2026_12 VALUES LESS THAN ('2026-12-01'),
    PARTITION p2026_12 VALUES LESS THAN ('2027-01-01')
);

ALTER TABLE event_log_without_max
ADD PARTITION (
    PARTITION p2027_01 VALUES LESS THAN ('2027-02-01')
);
```

Điều kiện quan trọng:

- Bảng phải partition theo RANGE.
- Partition mới phải mở rộng miền hợp lệ ở cuối danh sách partition.
- Ranh giới RANGE mới phải lớn hơn ranh giới cao nhất hiện tại.
- Không được thêm partition phía sau partition `MAXVALUE`.
- Tên partition không được trùng với tên đang tồn tại.

Ví dụ trên dùng bảng minh họa `event_log_without_max`; bảng `event_log` ở phần 3 đã có `pmax`, vì vậy không thể áp dụng nguyên câu ADD đó lên bảng này.

### 4.2. ADD cho LIST

Với LIST partitioning, partition mới nhận các giá trị chưa được gán cho partition hiện có:

```sql
CREATE TABLE regional_events (
    event_id BIGINT UNSIGNED NOT NULL,
    region_id INT NOT NULL,
    event_type VARCHAR(40) NOT NULL,
    PRIMARY KEY (event_id, region_id)
) ENGINE = InnoDB
PARTITION BY LIST COLUMNS (region_id) (
    PARTITION p_north VALUES IN (1, 2),
    PARTITION p_south VALUES IN (3, 4)
);

ALTER TABLE regional_events
ADD PARTITION (
    PARTITION p_central VALUES IN (5, 6)
);
```

Không thêm lại giá trị đã thuộc partition khác. Mỗi giá trị hợp lệ phải được ánh xạ vào đúng một partition; nếu không có partition phù hợp, INSERT sẽ lỗi.

### 4.3. ADD cho HASH/KEY

Với bảng HASH hoặc KEY, `ADD PARTITION PARTITIONS n` tăng tổng số partition thêm `n` partition. Không khai báo tên partition hay boundary riêng:

```sql
DROP TABLE IF EXISTS session_hash_add;

CREATE TABLE session_hash_add (
    session_id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    PRIMARY KEY (session_id, customer_id)
) ENGINE = InnoDB
PARTITION BY HASH (customer_id)
PARTITIONS 8;

ALTER TABLE session_hash_add
ADD PARTITION PARTITIONS 2;
```

Nếu bảng đang có 8 partition, câu lệnh trên tăng tổng số lên 10. Con số `2` là số partition được thêm, không phải tổng số partition đích.

Khác với RANGE/LIST, việc tăng số partition HASH/KEY có thể làm thay đổi ánh xạ của nhiều hàng. Với HASH/KEY thông thường, MySQL phải phân phối lại dữ liệu giữa các partition; LINEAR HASH/LINEAR KEY có thể giảm lượng di chuyển. Hãy đo dung lượng tạm, I/O, thời gian DDL, metadata lock và replication lag trước khi áp dụng trên bảng lớn.

### 4.4. Khi đã có MAXVALUE

Giả sử `pmax` đang chứa mọi ngày từ 01/12/2026 trở đi. Để tạo partition tháng 12/2026, chia `pmax` thành partition tháng 12 và `pmax` mới:

```sql
ALTER TABLE event_log
REORGANIZE PARTITION pmax INTO (
    PARTITION p2026_12 VALUES LESS THAN ('2027-01-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Các hàng tháng 12 đang nằm trong `pmax` được phân phối sang `p2026_12`; các hàng từ 01/01/2027 trở đi vẫn ở `pmax`. Đây là `REORGANIZE`, không phải `ADD`, vì phải tách miền đã được partition `MAXVALUE` bao phủ.

## 5. DROP PARTITION — xóa partition và dữ liệu

`DROP PARTITION` xóa định nghĩa partition cùng toàn bộ dữ liệu đang nằm trong partition đó. Nó không di chuyển dữ liệu sang partition khác.

Ví dụ:

```sql
ALTER TABLE event_log
DROP PARTITION p2026_10;
```

Sau thao tác:

- Partition `p2026_10` không còn tồn tại.
- Các hàng thuộc miền từ 01/10/2026 đến trước 01/11/2026 trong partition đó bị loại khỏi bảng.
- Các partition còn lại vẫn tồn tại.
- Dữ liệu trong `p2026_11` và `pmax` không bị xóa bởi lệnh này.

`DROP PARTITION` áp dụng cho RANGE/LIST. Với HASH/KEY, dùng `COALESCE PARTITION` nếu mục tiêu là giảm số partition.

### 5.1. DROP khác DELETE

| Tiêu chí | `DELETE FROM ... WHERE ...` | `ALTER TABLE ... DROP PARTITION` |
| --- | --- | --- |
| Phạm vi | Các hàng thỏa điều kiện | Toàn bộ dữ liệu trong partition chỉ định |
| Định nghĩa partition | Giữ nguyên | Partition bị loại bỏ |
| Predicate | Có thể dùng điều kiện hàng | Chỉ chọn theo tên partition |
| Mục tiêu thường gặp | Xóa một tập hàng nghiệp vụ | Loại bỏ hẳn một vùng dữ liệu đã hết vòng đời |
| Khả năng rollback | DML transactional có thể rollback trước commit | DDL có implicit commit; không thể dùng ROLLBACK để khôi phục partition đã drop |

Trước khi DROP:

1. Xác nhận đúng schema, bảng và tên partition.
2. Đếm hoặc kiểm tra phạm vi dữ liệu cần loại.
3. Archive/export dữ liệu nếu cần lưu lịch sử.
4. Kiểm tra backup và khả năng phục hồi.
5. Kiểm tra query/report/replication có phụ thuộc vùng dữ liệu đó không.
6. Chạy trong cửa sổ vận hành phù hợp và xác minh sau DDL.

Không dùng DROP PARTITION chỉ để làm bảng nhỏ hơn nếu dữ liệu vẫn thuộc yêu cầu lưu trữ hoặc kiểm toán.

## 6. TRUNCATE PARTITION — xóa dữ liệu nhưng giữ partition

`TRUNCATE PARTITION` làm rỗng một hoặc nhiều partition được chỉ định nhưng giữ nguyên định nghĩa partition. Đây là cách làm sạch một vùng dữ liệu để tái sử dụng mà không thay đổi ranh giới partition.

Ví dụ:

```sql
ALTER TABLE event_log
TRUNCATE PARTITION p2026_11;
```

Partition `p2026_11` vẫn tồn tại với cùng ranh giới tháng 11/2026, nhưng dữ liệu trong partition bị xóa.

Có thể truncate nhiều partition:

```sql
ALTER TABLE event_log
TRUNCATE PARTITION p2026_10, p2026_11;
```

Ví dụ trên chỉ hợp lệ nếu các partition đó vẫn tồn tại. Không chạy lại sau khi đã DROP chúng.

Trong luồng ví dụ của bài, `p2026_10` đã bị DROP ở phần 5. Muốn thử câu TRUNCATE nhiều partition này, hãy khôi phục fixture ở phần 3 trước hoặc bỏ `p2026_10` khỏi danh sách.

### 6.1. TRUNCATE khác DROP

| Thao tác | Partition definition | Dữ liệu bên trong | Có thể INSERT lại vào miền đó? |
| --- | --- | --- | --- |
| `DROP PARTITION p` | Bị xóa | Bị xóa | Không theo partition cũ; cần định nghĩa partition phù hợp trước |
| `TRUNCATE PARTITION p` | Được giữ | Bị xóa | Có, partition tiếp tục nhận dữ liệu thuộc miền của nó |

### 6.2. TRUNCATE PARTITION khác DELETE theo predicate

`DELETE` xóa từng hàng thỏa predicate và có thể phát sinh chi phí undo, redo, trigger và row-level work theo số hàng. `TRUNCATE PARTITION` là thao tác DDL trên partition, không phải một câu DELETE có điều kiện; nó có implicit commit và không thể rollback dữ liệu đã truncate bằng `ROLLBACK` thông thường.

Trước khi truncate, hãy chắc chắn partition chỉ chứa dữ liệu được phép xóa. Nếu chỉ muốn xóa một phần hàng trong partition, dùng DELETE với predicate phù hợp thay vì truncate toàn partition.

## 7. REORGANIZE PARTITION — chia hoặc gộp RANGE/LIST

`REORGANIZE PARTITION` thay đổi cách dữ liệu được chia giữa một hoặc nhiều partition RANGE/LIST. Dữ liệu hiện có trong các partition được chỉ định sẽ được phân phối lại theo định nghĩa mới.

Các trường hợp thường gặp:

- Chia một partition lớn thành nhiều partition nhỏ.
- Gộp một số partition thành một partition lớn hơn.
- Tách `MAXVALUE` để tạo partition cho một khoảng mới.
- Thay đổi nhóm giá trị trong LIST partitioning.

### 7.1. Chia partition RANGE

Giả sử `p2026_11` hiện bao phủ từ 01/11/2026 đến trước 01/12/2026. Muốn chia thành hai nửa tháng:

```sql
ALTER TABLE event_log
REORGANIZE PARTITION p2026_11 INTO (
    PARTITION p2026_11a VALUES LESS THAN ('2026-11-16'),
    PARTITION p2026_11b VALUES LESS THAN ('2026-12-01')
);
```

Ranh giới mới phải bao phủ chính xác miền mà partition cũ đang đại diện:

- `p2026_11a`: từ 01/11 đến trước 16/11.
- `p2026_11b`: từ 16/11 đến trước 01/12.

Các hàng hiện có trong `p2026_11` được phân phối sang hai partition mới theo `event_date`. Không có hàng nào bị xóa nếu định nghĩa mới bao phủ đúng miền cũ.

### 7.2. Gộp partition RANGE

Nếu hai partition liên tiếp có ranh giới phù hợp, có thể gộp chúng:

```sql
ALTER TABLE event_log
REORGANIZE PARTITION p2026_11a, p2026_11b INTO (
    PARTITION p2026_11 VALUES LESS THAN ('2026-12-01')
);
```

Sau thao tác, dữ liệu từ hai partition được gộp vào partition mới `p2026_11`. Tổng miền giá trị được bao phủ phải tương đương miền cũ; không được vô tình bỏ sót hoặc chồng lấn ranh giới.

### 7.3. Tách MAXVALUE

Ví dụ ở phần 4.4 là một dạng REORGANIZE quan trọng: tách partition `pmax` thành partition tháng cụ thể và `pmax` mới. Khi quản lý bảng theo tháng, đây là cách phổ biến để tạo partition mới nếu luôn giữ một partition catch-all.

Nếu `pmax` đã chứa dữ liệu tương lai, MySQL phải phân phối lại dữ liệu vào partition mới. Đánh giá lượng dữ liệu có thể phải di chuyển và thời gian DDL trước khi chạy.

### 7.4. REORGANIZE LIST

Với LIST partitioning, các giá trị của partition cũ phải được phân bổ đầy đủ vào các partition mới. Ví dụ:

```sql
ALTER TABLE regional_events
REORGANIZE PARTITION p_north INTO (
    PARTITION p_north_1 VALUES IN (1),
    PARTITION p_north_2 VALUES IN (2)
);
```

Partition cũ có giá trị 1 và 2; định nghĩa mới phân chia tập giá trị đó thành hai partition. Không bỏ sót giá trị và không gán cùng một giá trị vào nhiều partition.

### 7.5. Điều kiện quan trọng khi REORGANIZE

- Chỉ dùng cho RANGE/LIST partitioning.
- Các định nghĩa mới phải bao phủ đúng miền giá trị của các partition cũ được tổ chức lại.
- Tên partition mới phải hợp lệ và không trùng.
- Dữ liệu hiện có phải có thể phân phối theo định nghĩa mới.
- Với RANGE có `MAXVALUE`, phải bảo đảm partition cuối mới vẫn xử lý mọi giá trị còn lại.
- Đánh giá lượng dữ liệu cần di chuyển, thời gian DDL, metadata lock và I/O.

Không coi REORGANIZE là thao tác chỉ đổi tên partition. Khi ranh giới thay đổi, MySQL có thể phải đọc và ghi lại dữ liệu để phân phối lại.

## 8. COALESCE PARTITION — giảm số partition HASH/KEY

`COALESCE PARTITION` áp dụng cho bảng partition theo HASH hoặc KEY. Nó giảm số partition và phân phối lại dữ liệu vào số partition còn lại.

Tạo bảng HASH lab:

```sql
DROP TABLE IF EXISTS session_hash;

CREATE TABLE session_hash (
    session_id BIGINT UNSIGNED NOT NULL,
    customer_id INT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (session_id, customer_id),
    KEY idx_session_hash_customer (customer_id)
) ENGINE = InnoDB
PARTITION BY HASH (customer_id)
PARTITIONS 8;
```

Giảm từ 8 partition xuống 6:

```sql
ALTER TABLE session_hash COALESCE PARTITION 2;
```

Tham số `2` là số partition cần loại khỏi tổng số partition; InnoDB phân phối lại dữ liệu theo định nghĩa HASH/KEY còn lại. Không chọn tên partition cụ thể trong câu COALESCE.

### 8.1. COALESCE khác DROP PARTITION

- `DROP PARTITION` loại partition có tên và dữ liệu trong đó; dùng với RANGE/LIST.
- `COALESCE PARTITION n` giảm số partition HASH/KEY và phân phối lại hàng; không phải xóa tùy ý một nhóm dữ liệu.

Với HASH/KEY, việc giảm số partition không có nghĩa một phần dữ liệu bị mất. Các hàng vẫn thuộc bảng, nhưng vị trí partition được tính lại theo số partition mới.

### 8.2. Tăng số partition HASH/KEY

Để tăng số partition hiện có, dùng `ADD PARTITION PARTITIONS n`:

```sql
ALTER TABLE session_hash
ADD PARTITION PARTITIONS 4;
```

Ví dụ bảng đang có 8 partition sẽ có 12 partition sau câu lệnh. Đây là cách tăng số partition mà vẫn giữ partitioning method/expression hiện tại. Với HASH/KEY không dùng LINEAR, thao tác có thể copy/phân phối lại dữ liệu giữa các partition; với LINEAR HASH/KEY, chi phí di chuyển có thể thấp hơn.

Chỉ dùng `ALTER TABLE ... PARTITION BY HASH/KEY (...) PARTITIONS n` khi cần thay đổi partitioning expression hoặc phương pháp phân vùng, không phải cách thông thường để chỉ tăng số partition. Thao tác đổi scheme có thể tạo cấu trúc bảng mới và copy dữ liệu; hãy kiểm tra `ALGORITHM`/`LOCK` được hỗ trợ, thử trên staging và chuẩn bị cửa sổ vận hành.

## 9. Ảnh hưởng của partition maintenance tới DDL và transaction

Các lệnh quản lý partition ở trên đều là thao tác `ALTER TABLE`. DDL trong MySQL có quy tắc implicit commit; không đặt một lệnh DROP/TRUNCATE/REORGANIZE PARTITION giữa transaction DML với kỳ vọng có thể `ROLLBACK` toàn bộ.

Ví dụ không an toàn về kỳ vọng rollback:

Đây là kịch bản độc lập để minh họa implicit commit. Hãy khôi phục fixture ở phần 3 trước khi chạy để hàng `event_id = 2` vẫn tồn tại trong `p2026_11`.

```sql
START TRANSACTION;

UPDATE event_log
SET event_type = 'ARCHIVED'
WHERE event_id = 2 AND event_date = '2026-11-05';

ALTER TABLE event_log
TRUNCATE PARTITION p2026_11;

ROLLBACK;
```

DDL có thể commit transaction đang mở trước khi thực hiện; `ROLLBACK` cuối không phục hồi các hàng đã truncate hoặc thay đổi DML đã được commit do implicit commit.

MySQL 8.0 có atomic DDL cho nhiều thao tác DDL của InnoDB, nghĩa là statement DDL được bảo đảm hoàn tất hoặc phục hồi nhất quán khi server crash trong các điều kiện được hỗ trợ. Atomic DDL không có nghĩa DDL tham gia transaction DML của người dùng hoặc có thể rollback sau khi statement thành công.

### 9.1. Metadata lock và thời gian bảo trì

DDL cần metadata lock để thay đổi định nghĩa bảng. Một transaction đang sử dụng bảng có thể giữ metadata lock lâu hơn dự kiến và khiến ALTER TABLE phải chờ. Ngược lại, DDL đang chờ có thể làm các statement mới xếp hàng theo cơ chế metadata locking.

Trước khi chạy partition maintenance trên bảng lớn:

- Kiểm tra transaction đang mở và thời gian chạy của chúng.
- Kiểm tra metadata lock/wait nếu bảng đang có workload cao.
- Đánh giá DDL có cần di chuyển/rebuild dữ liệu hay không.
- Xác nhận `ALGORITHM` và `LOCK` được hỗ trợ cho thao tác, phiên bản và engine cụ thể.
- Đặt timeout/giám sát phù hợp và có kế hoạch hủy nếu DDL chờ quá lâu.

Không mặc định mọi partition operation đều `INSTANT`, `INPLACE` hoặc `LOCK=NONE`. Khả năng online phụ thuộc loại thao tác, phiên bản MySQL, engine, định nghĩa bảng và các giới hạn hiện hành. Thử trên bản sao staging có quy mô gần thực tế.

## 10. Xác minh partition sau thao tác

Sau DDL, kiểm tra lại định nghĩa:

```sql
SHOW CREATE TABLE event_log;
```

Kiểm tra metadata:

```sql
SELECT
    PARTITION_ORDINAL_POSITION,
    PARTITION_NAME,
    PARTITION_METHOD,
    PARTITION_DESCRIPTION,
    TABLE_ROWS
FROM INFORMATION_SCHEMA.PARTITIONS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'event_log'
ORDER BY PARTITION_ORDINAL_POSITION;
```

Kiểm tra số hàng theo partition:

```sql
SELECT 'p2026_11' AS partition_name, COUNT(*) AS row_count
FROM event_log PARTITION (p2026_11)
UNION ALL
SELECT 'p2026_12', COUNT(*)
FROM event_log PARTITION (p2026_12)
UNION ALL
SELECT 'pmax', COUNT(*)
FROM event_log PARTITION (pmax);
```

Chỉ chạy truy vấn cho các partition còn tồn tại theo định nghĩa hiện tại. `COUNT(*)` là số hàng chính xác tại snapshot truy vấn, nhưng có thể tốn thời gian nếu partition lớn.

### 10.1. Xác minh ranh giới bằng dữ liệu mẫu

Với RANGE theo ngày, kiểm tra các ngày ở ngay trước, đúng tại và ngay sau boundary:

```sql
SELECT event_id, event_date
FROM event_log
WHERE event_date IN (
    '2026-11-15',
    '2026-11-16',
    '2026-11-30',
    '2026-12-01'
)
ORDER BY event_date, event_id;
```

Với `VALUES LESS THAN`, giá trị bằng boundary thuộc partition kế tiếp. Ví dụ `VALUES LESS THAN ('2026-12-01')` không bao gồm ngày 01/12.

## 11. Partition pruning sau khi thay đổi partition

Partition maintenance cần giữ đúng ranh giới để optimizer loại bỏ partition không liên quan khi query có predicate phù hợp (*partition pruning*).

Ví dụ:

```sql
EXPLAIN PARTITIONS
SELECT event_id, event_date, event_type
FROM event_log
WHERE event_date >= '2026-11-01'
  AND event_date < '2026-12-01';
```

Quan sát cột `partitions` trong EXPLAIN để biết partition nào được truy cập. Với MySQL 8.x, hình thức EXPLAIN có thể hiển thị khác theo format; dùng `EXPLAIN` phù hợp phiên bản nếu `EXPLAIN PARTITIONS` không được hỗ trợ trong môi trường cụ thể.

Predicate nên tương thích với biểu thức partition. Tránh bọc cột partition bằng hàm hoặc chuyển đổi không cần thiết nếu điều đó ngăn pruning. Ví dụ khoảng thời gian nửa mở (`>= đầu`, `< ngày kế tiếp`) thường rõ ràng và tránh lỗi biên hơn việc dùng `DATE_FORMAT()` trên cột.

Sau REORGANIZE hoặc ADD/DROP, chạy lại các truy vấn đại diện để xác nhận pruning vẫn phù hợp và không vô tình quét `pmax` cùng nhiều partition không cần thiết.

## 12. Quy trình bảo trì partition theo tháng

Một quy trình vận hành thường gặp cho bảng log theo tháng:

1. Trước tháng mới, xác định partition tháng cần tạo và boundary chính xác.
2. Kiểm tra `SHOW CREATE TABLE` và `INFORMATION_SCHEMA.PARTITIONS`.
3. Nếu có `pmax`, dùng `REORGANIZE pmax` để tách tháng mới và giữ `pmax`.
4. Xác minh dữ liệu tương lai đã được ánh xạ vào partition mới.
5. Khi tới thời hạn lưu trữ, archive/backup partition cũ trước khi DROP.
6. Dùng `DROP PARTITION` nếu muốn loại cả dữ liệu và định nghĩa, hoặc `TRUNCATE PARTITION` nếu muốn giữ partition rỗng.
7. Kiểm tra số hàng, boundary, query pruning, replication lag và dung lượng sau thao tác.

Ví dụ tạo partition tháng 01/2027 khi đang có `pmax`:

```sql
ALTER TABLE event_log
REORGANIZE PARTITION pmax INTO (
    PARTITION p2027_01 VALUES LESS THAN ('2027-02-01'),
    PARTITION pmax VALUES LESS THAN (MAXVALUE)
);
```

Ví dụ loại tháng 10/2026 sau khi đã archive và xác nhận retention:

Đây là thao tác retention độc lập. Nếu đã chạy `DROP PARTITION p2026_10` ở phần 5, hãy khôi phục fixture hoặc bỏ qua ví dụ này.

```sql
ALTER TABLE event_log
DROP PARTITION p2026_10;
```

Hai thao tác phải được lên lịch theo boundary và chính sách retention. Không chạy DROP trước khi dữ liệu archive được xác minh có thể đọc/khôi phục.

## 13. Lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng ADD sau partition `MAXVALUE` | DDL thất bại vì không thể thêm miền sau MAXVALUE | REORGANIZE partition MAXVALUE để tách miền mới |
| Dùng DROP để chỉ làm rỗng partition | Mất cả định nghĩa partition | Dùng TRUNCATE PARTITION |
| Dùng TRUNCATE khi muốn bỏ partition | Partition rỗng vẫn tồn tại | Dùng DROP PARTITION nếu muốn loại định nghĩa và dữ liệu |
| Dùng DROP/TRUNCATE mà không archive | Mất dữ liệu cần lưu trữ | Kiểm tra retention, backup và export trước |
| REORGANIZE không bao phủ đúng miền cũ | DDL bị từ chối hoặc boundary không đúng ý định | Tính lại tập giá trị/range bao phủ đầy đủ |
| Dùng REORGANIZE cho HASH/KEY | Không đúng partitioning method | Dùng ADD PARTITION PARTITIONS n để tăng hoặc COALESCE PARTITION n để giảm |
| Dùng COALESCE cho RANGE/LIST | Không đúng partitioning method | Dùng DROP/REORGANIZE theo mục tiêu |
| Dùng DROP PARTITION cho HASH/KEY | Không được hỗ trợ như RANGE/LIST | Dùng COALESCE PARTITION |
| Nghĩ COALESCE xóa dữ liệu | Hiểu sai việc giảm số partition | COALESCE phân phối lại dữ liệu vào số partition còn lại |
| Quên unique key phải chứa partition key | Không tạo được unique/primary key mong muốn | Thiết kế lại key hoặc dùng registry table |
| Giả định partitioned InnoDB vẫn hỗ trợ FK | Schema không tạo được hoặc thiết kế không hợp lệ | Xác minh giới hạn FK trước khi chọn partitioning |
| Nghĩ DDL partition có thể rollback | Dữ liệu đã bị DROP/TRUNCATE không được ROLLBACK phục hồi | Tách DDL khỏi transaction nghiệp vụ và chuẩn bị backup |
| Mặc định DDL là online, không lock | Workload bị chặn hoặc migration chờ metadata lock | Kiểm tra ALGORITHM/LOCK và thử staging |
| Không kiểm tra partition pruning sau thay đổi | Query quét nhiều partition hơn dự kiến | Dùng EXPLAIN và predicate theo partition key |

## 14. Bài tập thực hành

1. Tạo `event_log` ở phần 3. Chạy `SHOW CREATE TABLE` và truy vấn `INFORMATION_SCHEMA.PARTITIONS` để ghi lại các boundary.
2. Tạo bảng RANGE không có `MAXVALUE`, thêm partition mới bằng `ADD PARTITION`; thử thêm boundary nhỏ hơn boundary cuối và giải thích lỗi.
3. Tạo bảng LIST. Thêm partition cho các giá trị chưa được gán; thử thêm lại giá trị đã tồn tại và quan sát lỗi.
4. Chạy `DROP PARTITION` trên một partition lab có dữ liệu. Xác minh cả partition definition và dữ liệu đã biến mất.
5. Chạy `TRUNCATE PARTITION` trên một partition khác. Xác minh partition vẫn tồn tại nhưng số hàng bằng 0.
6. Chia partition tháng bằng `REORGANIZE PARTITION`. Kiểm tra các hàng ở hai phía boundary, đặc biệt ngày đúng bằng boundary.
7. Gộp lại các partition vừa chia. Đối chiếu tổng số hàng trước và sau.
8. Tạo bảng HASH có 8 partition rồi `COALESCE PARTITION 2`. Kiểm tra số partition còn lại và tổng số hàng không đổi.
9. Tăng số partition HASH bằng `ADD PARTITION PARTITIONS n`, sau đó giảm bằng `COALESCE PARTITION n`; so sánh số partition, tổng số hàng và tác động phân phối lại.
10. Chạy `EXPLAIN PARTITIONS` cho truy vấn theo ngày trước và sau khi reorganize.
11. Quan sát metadata lock trong lúc một session giữ transaction dùng bảng và session khác chạy ALTER PARTITION trên môi trường lab.
12. Viết runbook bảo trì tháng gồm archive, tạo partition mới, loại partition hết hạn, kiểm tra row count, pruning và replication lag.

## 15. Checklist trước khi chạy partition maintenance

- [ ] Đã xác nhận đúng schema, bảng, partitioning method và định nghĩa hiện tại.
- [ ] Đã xác định mục tiêu là thêm miền, xóa dữ liệu, làm rỗng, chia/gộp hay giảm số partition.
- [ ] Đã chọn đúng lệnh theo RANGE/LIST/HASH/KEY.
- [ ] Đã kiểm tra `MAXVALUE` và ranh giới hiện tại.
- [ ] Đã xác nhận partition mới không trùng tên và không chồng lấn/thiếu miền.
- [ ] Đã kiểm tra quy tắc unique key phải chứa partitioning columns.
- [ ] Đã xác minh giới hạn foreign key của bảng partitioned InnoDB.
- [ ] Đã đếm/đánh giá dữ liệu bị ảnh hưởng và archive/backup nếu cần.
- [ ] Đã đánh giá lượng dữ liệu cần di chuyển, disk space và I/O.
- [ ] Đã kiểm tra transaction dài, metadata lock và cửa sổ vận hành.
- [ ] Đã xác minh ALGORITHM/LOCK phù hợp với phiên bản và thao tác.
- [ ] Đã có kế hoạch kiểm tra replication lag và workload sau DDL.
- [ ] Đã kiểm tra lại SHOW CREATE TABLE, partition metadata, row count và pruning.
- [ ] Không dựa vào ROLLBACK để phục hồi DDL đã hoàn tất.

## 16. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể phân biệt rõ `ADD`, `DROP`, `TRUNCATE`, `REORGANIZE` và `COALESCE PARTITION`; chọn đúng thao tác cho RANGE/LIST/HASH/KEY; giải thích cách xử lý `MAXVALUE`; chia/gộp partition mà không mất miền dữ liệu; hiểu tác động DDL và metadata lock; đồng thời xác minh được partition definitions, row count và pruning sau bảo trì.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — Management of RANGE and LIST Partitions](https://dev.mysql.com/doc/refman/8.4/en/partitioning-management-range-list.html)
- [MySQL 8.4 Reference Manual — Management of HASH and KEY Partitions](https://dev.mysql.com/doc/refman/8.4/en/partitioning-management-hash-key.html)
- [MySQL 8.4 Reference Manual — Partitioning Limitations](https://dev.mysql.com/doc/refman/8.4/en/partitioning-limitations.html)
- [MySQL 8.4 Reference Manual — INFORMATION_SCHEMA PARTITIONS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-partitions-table.html)
- [MySQL 8.4 Reference Manual — ALTER TABLE Partition Operations](https://dev.mysql.com/doc/refman/8.4/en/alter-table.html)
