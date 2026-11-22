# ATTACH, DETACH và quản lý vòng đời dữ liệu trong PostgreSQL

Một hệ thống ghi nhật ký, giao dịch, sự kiện IoT hoặc bản ghi truy cập có thể tăng thêm hàng triệu dòng mỗi tháng. Dữ liệu mới được truy vấn thường xuyên, dữ liệu cũ chỉ cần tra cứu khi kiểm toán, và dữ liệu quá hạn phải được lưu trữ hoặc xóa theo chính sách. Nếu tất cả nằm trong một bảng khổng lồ, việc xóa từng hàng bằng `DELETE` có thể tốn nhiều thời gian, sinh nhiều WAL và để lại những phiên bản hàng cần `VACUUM` dọn dẹp.

**Declarative partitioning** cho phép PostgreSQL tổ chức một bảng logic thành nhiều bảng con (*partitions*) theo khoảng thời gian, danh sách giá trị hoặc hàm băm. Khi phân vùng theo tháng, hệ thống có thể:

1. Tạo sẵn một bảng cho tháng mới.
2. **`ATTACH PARTITION`** để gắn một bảng đã tồn tại vào cây phân vùng, kể cả khi bảng đó đã chứa dữ liệu hợp lệ.
3. Tiếp tục truy vấn qua **bảng cha** như một bảng logic thống nhất.
4. Khi tháng cũ hết vòng đời phục vụ trực tuyến, **`DETACH PARTITION`** để tách nó thành một bảng độc lập.
5. Sao lưu/xuất dữ liệu cũ, xác minh rồi mới **`DROP TABLE`** nếu chính sách cho phép.

Hình dung:

```text
               events (partitioned parent)
                         |
           +-------------+-------------+
           |             |             |
     events_2026_01  events_2026_02  events_2026_03
      [Jan rows]      [Feb rows]      [Mar rows]
           |                             ^
           | DETACH                      | ATTACH
           v                             |
   standalone table              staging_march
    / archive candidate          (existing table)
           |
      Export + verify
           |
   Retain / DROP later
```

Hai thao tác `ATTACH` và `DETACH` là **thay đổi quan hệ giữa bảng cha và bảng con**, không mặc nhiên là các lệnh sao chép hoặc xóa toàn bộ hàng. Nhờ vậy, quản lý dữ liệu theo chu kỳ có thể hiệu quả hơn nhiều so với chuyển/xóa từng bản ghi. Tuy nhiên, tính an toàn phụ thuộc vào **giới hạn partition, ràng buộc dữ liệu, khóa DDL, default partition, index, foreign key, transaction và quy trình lưu trữ**.

Bài thuộc chương **Phân vùng** của module *Database Engine Relational PostgreSQL*. Nội dung cung cấp thí nghiệm SQL tự chứa, sơ đồ vận hành, các tình huống lỗi, lưu ý triển khai production và bài tập có đáp án.

**Mục tiêu:**

- Hiểu cách PostgreSQL định tuyến `INSERT` và loại bỏ partition không liên quan khi truy vấn (*partition pruning*).
- Tạo bảng phân vùng `RANGE` theo thời gian và kiểm tra giới hạn `FROM ... TO ...`.
- `ATTACH` một bảng thông thường đã có dữ liệu, dùng `CHECK` đã được xác thực để giảm rủi ro full-table scan.
- Xử lý tác động của **default partition** và dữ liệu nằm trong khoảng sắp gắn.
- Phân biệt `DETACH PARTITION` thường với `DETACH PARTITION CONCURRENTLY`, kể cả `FINALIZE` khi thao tác đồng thời bị gián đoạn.
- Xây dựng quy trình **hot → warm → archive → delete**, có đối chiếu số hàng, bản sao lưu, retention và legal hold.
- Hiểu ảnh hưởng đến khóa, index, primary key/unique, FK, transaction, logical replication và giám sát.

> **An toàn:** Mọi lệnh DDL/DML thực hành dùng schema riêng `partition_lifecycle_lab` trong database thử nghiệm. Không chạy `DROP`, `DETACH` hoặc chỉnh retention trên bảng sản xuất nếu chưa có quyền và runbook. Không chạy lệnh `DETACH ... CONCURRENTLY` bên trong `BEGIN ... COMMIT`; nó có giới hạn transaction riêng.

---

## 1. Partitioned table và partition vật lý

### 1.1. Bảng cha là một quan hệ logic

Giả sử bảng logic `events` chứa cột `event_time`. Ta có thể chia theo tháng:

```text
events
  event_time  < 2026-02-01 --> events_2026_01
  event_time  < 2026-03-01 --> events_2026_02
  event_time  < 2026-04-01 --> events_2026_03
```

Với declarative partitioning của PostgreSQL, bảng cha định nghĩa cấu trúc và phương pháp phân vùng. Các partition là **những quan hệ riêng có lưu trữ dữ liệu**; một bảng partitioned parent ở dạng thông thường không giữ heap row của chính nó.

### 1.2. Những phương pháp phân vùng chính

| Phương pháp | Cú pháp điển hình | Tình huống |
|---|---|---|
| `RANGE` | `PARTITION BY RANGE (event_time)` | Dữ liệu theo tháng/ngày, số có khoảng |
| `LIST` | `PARTITION BY LIST (region)` | Nhóm trạng thái, vùng hoặc danh mục hữu hạn |
| `HASH` | `PARTITION BY HASH (tenant_id)` | Phân phối các khóa theo modulo/remainder |

Chủ đề quản lý vòng đời theo thời gian đặc biệt phù hợp với **`RANGE`**, vì thường lưu/xóa toàn bộ một tháng hoặc một ngày.

### 1.3. Khoảng RANGE là nửa mở

Partition:

```sql
FOR VALUES FROM ('2026-01-01 00:00:00+00')
           TO ('2026-02-01 00:00:00+00')
```

bao gồm **giá trị từ cận dưới** và **không bao gồm cận trên**:

```text
2026-01-01 00:00:00+00    được nhận
2026-01-31 23:59:59+00    được nhận
2026-02-01 00:00:00+00    không thuộc Jan
```

Phần thập phân giây cũng được xử lý chính xác theo cận nửa mở. Không mô tả tháng bằng `BETWEEN ... 23:59:59` vì có thể bỏ sót timestamp có microseconds.

### 1.4. Partition pruning khác index scan

PostgreSQL có thể **bỏ qua partition** không thể chứa hàng thỏa điều kiện:

```sql
SELECT COUNT(*)
FROM events
WHERE event_time >= TIMESTAMPTZ '2026-02-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-03-01 00:00+00';
```

Đây là **partition pruning**. Sau khi chọn partition tháng Hai, PostgreSQL vẫn có thể **Seq Scan** hoặc **Index Scan** ở bên trong partition đó. Một Seq Scan trên partition nhỏ **không có nghĩa pruning đã thất bại**.

---

## 2. Bộ dữ liệu thực hành theo tháng

### 2.1. Kiểm tra database

```sql
SHOW server_version;
SELECT current_database(), current_user;
```

Tạo schema riêng. Nếu đã có schema cùng tên chứa dữ liệu từ lượt khác, hãy đổi sang database thực hành khác thay vì xóa đối tượng không thuộc phạm vi của mình.

### 2.2. Tạo parent partitioned table

```sql
CREATE SCHEMA partition_lifecycle_lab;

CREATE TABLE partition_lifecycle_lab.events (
    event_id BIGINT NOT NULL,
    tenant_id INTEGER NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (event_time, event_id)
) PARTITION BY RANGE (event_time);
```

Điểm cần hiểu:

- `event_time` là **partition key**.
- `PRIMARY KEY (event_time, event_id)` bao gồm partition key để phù hợp yêu cầu uniqueness của partitioned parent.
- PostgreSQL định tuyến các câu `INSERT INTO ...events` đến partition thích hợp.
- Parent không chứa heap dữ liệu thông thường; các partition mới là nơi lưu hàng.

**Vì sao không khai báo `PRIMARY KEY (event_id)` trên parent?** PostgreSQL không có một B-tree global duy nhất bao phủ mọi RANGE partition theo cách bảo đảm trực tiếp uniqueness của `event_id` khi partition key là `event_time`. `PRIMARY KEY`/`UNIQUE` của partitioned parent phải bao gồm toàn bộ cột partition key theo quy tắc áp dụng. Khóa `(event_time,event_id)` không ngăn hai hàng ở hai tháng có cùng `event_id` nhưng `event_time` khác nhau.

### 2.3. Tạo partition tháng Một

```sql
CREATE TABLE partition_lifecycle_lab.events_2026_01
PARTITION OF partition_lifecycle_lab.events
FOR VALUES FROM ('2026-01-01 00:00:00+00')
           TO ('2026-02-01 00:00:00+00');
```

### 2.4. Tạo partition tháng Hai

```sql
CREATE TABLE partition_lifecycle_lab.events_2026_02
PARTITION OF partition_lifecycle_lab.events
FOR VALUES FROM ('2026-02-01 00:00:00+00')
           TO ('2026-03-01 00:00:00+00');
```

Chưa tạo partition tháng Ba; chúng ta sẽ tạo **một bảng độc lập có sẵn dữ liệu** rồi thử `ATTACH` nó.

### 2.5. Tạo index qua parent

```sql
CREATE INDEX events_tenant_time_idx
ON partition_lifecycle_lab.events
    (tenant_id, event_time DESC);
```

Định nghĩa index tại partitioned parent thể hiện một **partitioned index**, với các index vật lý tương ứng trên các partition con. Không hiểu đây là một global B-tree đơn nhất với tất cả entry của mọi partition.

### 2.6. Chèn dữ liệu qua parent

```sql
INSERT INTO partition_lifecycle_lab.events
    (event_id, tenant_id, event_time, event_type, payload)
VALUES
    (1001, 10, '2026-01-15 08:00:00+00',
     'login', '{"source":"web"}'),
    (1002, 20, '2026-01-31 23:59:59+00',
     'purchase', '{"total":100}'),
    (2001, 10, '2026-02-01 00:00:00+00',
     'login', '{"source":"mobile"}'),
    (2002, 10, '2026-02-18 12:30:00+00',
     'logout', '{}');
```

Không cần chèn trực tiếp vào tên partition. PostgreSQL tự chọn `events_2026_01` hoặc `events_2026_02` từ `event_time`.

### 2.7. Kiểm tra định tuyến

```sql
SELECT
    tableoid::regclass AS physical_partition,
    event_id,
    event_time,
    event_type
FROM partition_lifecycle_lab.events
ORDER BY event_time;
```

`tableoid` là system column cho biết quan hệ vật lý chứa tuple được trả về. Khi truy vấn qua parent, nó hữu ích để quan sát hàng thực sự nằm ở partition nào.

Kết quả dự kiến:

| event_id | Partition | Thời điểm |
|---:|---|---|
| 1001 | `events_2026_01` | 15/01/2026 |
| 1002 | `events_2026_01` | 31/01/2026 |
| 2001 | `events_2026_02` | 01/02/2026 |
| 2002 | `events_2026_02` | 18/02/2026 |

Tên đầy đủ của `tableoid::regclass` có thể được schema-qualified hoặc không tùy `search_path`; đừng so sánh chuỗi hiển thị một cách cứng nhắc.

### 2.8. Nếu INSERT vào một tháng chưa có partition

```sql
-- Lúc này chưa có partition tháng Ba hoặc DEFAULT:
-- INSERT INTO partition_lifecycle_lab.events
--     (event_id, tenant_id, event_time, event_type)
-- VALUES (3001, 10, '2026-03-03 00:00+00', 'login');
```

Lệnh trên có thể báo:

```text
ERROR: no partition of relation "events" found for row
```

Đây là hành vi cần thiết: PostgreSQL không có partition hợp lệ để chứa hàng. **Ứng dụng không nên phụ thuộc vào việc tự động tạo partition chỉ vì INSERT vào tháng mới.** Phải có lịch tạo/gắn partition trước khi dữ liệu đến, hoặc một default partition được thiết kế có chủ đích.

---

## 3. ATTACH PARTITION dùng trong trường hợp nào?

`ATTACH PARTITION` gắn một bảng **đã tồn tại** vào bảng cha partitioned, với giới hạn phạm vi được khai báo.

### 3.1. Cú pháp chính

```sql
ALTER TABLE parent_table
ATTACH PARTITION existing_table
FOR VALUES FROM (lower_bound)
           TO (upper_bound);
```

Ví dụ cho tháng Ba:

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_03
FOR VALUES FROM ('2026-03-01 00:00:00+00')
           TO ('2026-04-01 00:00:00+00');
```

Ở thời điểm chuẩn bị thực hiện lệnh này, bảng `events_2026_03` phải **đã tồn tại**, là bảng phù hợp với cấu trúc parent và có dữ liệu trong phạm vi được phép. Chúng ta sẽ tạo bảng đó ở phần tiếp theo.

### 3.2. Khác CREATE TABLE ... PARTITION OF như thế nào?

| Thao tác | Tình huống |
|---|---|
| `CREATE TABLE child PARTITION OF parent ...` | Tạo partition mới trực tiếp trong cây |
| `CREATE TABLE child (...); ALTER TABLE parent ATTACH PARTITION child ...` | Tạo bảng độc lập trước, nạp/kiểm tra dữ liệu rồi gắn sau |
| `ALTER TABLE parent DETACH PARTITION child` | Tách partition hiện có thành bảng độc lập |

Phương án `ATTACH` đặc biệt hữu ích khi dữ liệu được **nạp hàng loạt** trong một bảng staging, chuẩn bị constraint/index trước, hoặc cần **đưa dữ liệu lịch sử đã có** vào một cây partition.

### 3.3. ATTACH không phải COPY

Nếu bảng standalone có một triệu hàng, `ATTACH` không mặc định sao chép từng hàng sang một bảng con khác. Nó biến **chính bảng hiện có** thành partition theo các kiểm tra và thay đổi metadata cần thiết.

Tuy vậy, PostgreSQL có thể phải **quét bảng** để chứng minh mọi hàng đều nằm trong bound hoặc tạo/đối chiếu index và ràng buộc cần thiết. Vì vậy không được hiểu “ATTACH là metadata-only trong mọi hoàn cảnh”.

---

## 4. Tạo bảng staging tháng Ba và ATTACH có dữ liệu sẵn

### 4.1. Tạo standalone table theo cấu trúc parent

```sql
CREATE TABLE partition_lifecycle_lab.events_2026_03
(
    LIKE partition_lifecycle_lab.events
      INCLUDING DEFAULTS
      INCLUDING CONSTRAINTS
      INCLUDING INDEXES
);
```

Lệnh trên tạo một **bảng thông thường** với các cột, default, CHECK constraints và index/PK tương ứng được copy theo tùy chọn `LIKE`. `LIKE` không có nghĩa bảng mới tự động trở thành partition hoặc tự kế thừa mọi đối tượng phụ thuộc bên ngoài, quyền, trigger, FK theo cách giống hệt parent. Khi triển khai thực tế, cần đối chiếu cấu trúc/constraints/index một cách có chủ đích.

### 4.2. Nạp dữ liệu tháng Ba vào bảng staging

```sql
INSERT INTO partition_lifecycle_lab.events_2026_03
    (event_id, tenant_id, event_time, event_type, payload)
VALUES
    (3001, 10, '2026-03-02 09:00:00+00',
     'login', '{"source":"web"}'),
    (3002, 20, '2026-03-15 18:00:00+00',
     'purchase', '{"total":250}'),
    (3003, 10, '2026-03-31 23:59:59+00',
     'logout', '{}');
```

Ở thời điểm này, các hàng **chỉ nằm trong bảng standalone**. Query qua `partition_lifecycle_lab.events` chưa thấy chúng.

### 4.3. Kiểm tra cận dữ liệu trước ATTACH

```sql
SELECT
    COUNT(*) AS total_rows,
    MIN(event_time) AS min_time,
    MAX(event_time) AS max_time
FROM partition_lifecycle_lab.events_2026_03;

SELECT COUNT(*) AS out_of_range_rows
FROM partition_lifecycle_lab.events_2026_03
WHERE NOT (
    event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
    AND event_time <
        TIMESTAMPTZ '2026-04-01 00:00:00+00'
);
```

Vì `event_time NOT NULL`, phép kiểm tra `NOT (...)` ở ví dụ này không bỏ qua các hàng có thời gian NULL. Kết quả `out_of_range_rows` phải bằng **0**.

Đây là kiểm tra nghiệp vụ hữu ích nhưng **chưa thay** ràng buộc đã được PostgreSQL xác thực.

### 4.4. Tạo CHECK constraint đúng bound

```sql
ALTER TABLE partition_lifecycle_lab.events_2026_03
ADD CONSTRAINT events_2026_03_bounds_chk
CHECK (
    event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
    AND event_time < TIMESTAMPTZ '2026-04-01 00:00:00+00'
);
```

Một `CHECK` **đã được xác thực** và đủ để chứng minh phạm vi partition có thể giúp PostgreSQL tránh bước quét lại toàn bộ bảng để xác nhận dữ liệu lúc `ATTACH`. Điều này rất quan trọng với bảng staging lớn.

Không chỉ viết `WHERE` khi kiểm tra bằng SELECT rồi giả định database có thể tin kết quả ấy. PostgreSQL dựa trên constraint hợp lệ và những quy tắc xác minh của nó.

### 4.5. Với bảng lớn: NOT VALID rồi VALIDATE

Có thể chuẩn bị constraint trong một giai đoạn riêng:

```sql
-- Mẫu thay thế cho ADD CHECK ở mục 4.4;
-- không chạy hai mẫu cùng tên trên một bảng.
--
-- ALTER TABLE partition_lifecycle_lab.events_2026_03
-- ADD CONSTRAINT events_2026_03_bounds_chk
-- CHECK (
--   event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
--   AND event_time < TIMESTAMPTZ '2026-04-01 00:00:00+00'
-- ) NOT VALID;
--
-- ALTER TABLE partition_lifecycle_lab.events_2026_03
-- VALIDATE CONSTRAINT events_2026_03_bounds_chk;
```

`NOT VALID` cho phép tách việc khai báo constraint khỏi bước quét xác thực dữ liệu cũ theo quy tắc của PostgreSQL. **Phải thực hiện `VALIDATE CONSTRAINT` thành công trước khi tin constraint giúp bỏ scan lúc ATTACH.** Một CHECK còn `NOT VALID` không chứng minh toàn bộ hàng cũ hợp lệ.

### 4.6. Chuẩn bị index tương ứng

Parent đang có index:

```sql
ON events (tenant_id, event_time DESC)
```

Ta có thể tạo trước index tương đương trên staging:

```sql
CREATE INDEX events_2026_03_tenant_time_idx
ON partition_lifecycle_lab.events_2026_03
    (tenant_id, event_time DESC);
```

Khi attach, PostgreSQL có thể **gắn index tương thích hiện có** vào partitioned index của parent, thay vì phải xây index tương ứng trong cửa sổ DDL. Nếu thiếu index cần thiết, hệ quản trị có thể tạo index trên partition mới theo quy tắc.

Index và constraint không chỉ là vấn đề hiệu năng: nếu parent có `PRIMARY KEY`/`UNIQUE`, partition phải đáp ứng các yêu cầu tương ứng. Chuẩn bị cấu trúc ở staging giúp giảm công việc trong thời điểm ATTACH.

### 4.7. Thực hiện ATTACH

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_03
FOR VALUES FROM ('2026-03-01 00:00:00+00')
           TO ('2026-04-01 00:00:00+00');
```

Sau thành công, `events_2026_03` trở thành partition của `events`. Bảng vẫn có dữ liệu tháng Ba; không cần INSERT lại các hàng.

### 4.8. Xác nhận parent thấy dữ liệu mới

```sql
SELECT
    tableoid::regclass AS physical_partition,
    event_id,
    event_time,
    event_type
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-04-01 00:00:00+00'
ORDER BY event_time;
```

Kết quả dự kiến có các ID `3001`, `3002` và `3003`, đều nằm trong `events_2026_03`.

### 4.9. Những lý do ATTACH có thể thất bại

| Tình huống | Nguyên nhân |
|---|---|
| Có hàng tháng Tư trong bảng tháng Ba | Dữ liệu vi phạm bound cần attach |
| Bound tháng Ba chồng lấn partition đã có | Các partition RANGE cùng cấp không được có vùng giao nhau |
| Thiếu/khác cột hoặc cấu trúc không tương thích | Bảng gắn phải đáp ứng định nghĩa của parent |
| Một index/constraint cần thiết không thể bảo đảm | DDL không thể hoàn tất hợp lệ |
| Có default partition chứa hàng thuộc tháng Ba | Hàng đó sẽ không còn hợp lệ trong default sau ATTACH |
| Không lấy được lock trong thời gian quy định | Có giao dịch khác đang dùng đối tượng |
| Không đủ quyền/đối tượng có dependency không hợp lệ | PostgreSQL không thể thực hiện thao tác schema |

Không nên tự động retry mọi lỗi DDL: **lỗi bound hoặc dữ liệu sai phải được sửa**, không phải lỗi tranh chấp tạm thời.

---

## 5. Tại sao CHECK constraint trước ATTACH quan trọng?

Giả sử bảng staging chứa **50 triệu hàng**. PostgreSQL phải bảo đảm:

```text
MỌI event_time >= 2026-03-01 00:00 UTC
VÀ
MỌI event_time <  2026-04-01 00:00 UTC
```

Nếu không có bằng chứng ràng buộc phù hợp, database có thể cần **scan toàn bộ bảng staging** để kiểm tra.

### 5.1. Full scan không làm ATTACH thành COPY

Một lần scan có thể đọc rất nhiều dữ liệu và giữ lock cần thiết, nhưng vẫn không có nghĩa PostgreSQL sao chép lại mọi hàng từ bảng staging sang bảng con khác. Đó là **validation scan**.

### 5.2. CHECK validated là bằng chứng bền vững

```sql
ALTER TABLE partition_lifecycle_lab.events_2026_03
ADD CONSTRAINT events_2026_03_bounds_chk
CHECK (
  event_time >= TIMESTAMPTZ '2026-03-01 00:00+00'
  AND event_time < TIMESTAMPTZ '2026-04-01 00:00+00'
);
```

Constraint này không chỉ chứng minh những hàng hiện có hợp lệ mà còn **ngăn hàng được ghi sau đó vi phạm** cận theo quy tắc kiểm tra PostgreSQL.

### 5.3. Bằng chứng phải đủ chặt

Một CHECK:

```sql
-- Quá rộng, không đủ chứng minh toàn bộ hàng thuộc March:
-- CHECK (event_time >= TIMESTAMPTZ '2026-01-01 00:00+00')
```

không chứng minh bảng chỉ có hàng tháng Ba. Nó cho phép cả hàng tháng Tư/Tháng Năm, nên không thể thay CHECK đúng bound.

### 5.4. Giới hạn của CHECK với NULL

Trong SQL, `CHECK` coi điều kiện `TRUE` **hoặc `UNKNOWN` là không vi phạm**. Vì thế nếu partition key nullable, một CHECK chỉ gồm phép so sánh có thể không chứng minh mọi hàng nằm đúng khoảng do NULL.

Trong ví dụ, `event_time NOT NULL` đã được khai báo; tính không NULL cùng điều kiện khoảng làm kiểm tra rõ ràng hơn. Không tự bỏ `NOT NULL` khi đưa mẫu vào hệ thống thật.

### 5.5. Constraint khác không tự thay CHECK cho ATTACH

Một SELECT trước ATTACH, một tài liệu vận hành hoặc một lời hứa ở tầng application **không được PostgreSQL xem là bằng chứng đã enforce** đối với mọi hàng của bảng. Hãy để database giữ constraint khi muốn dựa vào nó cho validation.

---

## 6. Locking của ATTACH PARTITION

ATTACH là DDL và có tác động đến những session đồng thời. “Chỉ đổi metadata” **không có nghĩa không có lock**.

### 6.1. Mức khóa đáng nhớ

Với declarative partitioning hiện đại:

- `ATTACH PARTITION` cần lock kiểu **`SHARE UPDATE EXCLUSIVE` trên bảng cha**.
- Bảng đang được attach cần lock mạnh hơn, thường là **`ACCESS EXCLUSIVE`**, trong quá trình thao tác.
- Nếu có **default partition** cần được kiểm tra để bảo đảm không chứa hàng thuộc bound mới, PostgreSQL có thể scan default partition và giữ **`ACCESS EXCLUSIVE`** trên đối tượng liên quan trong lúc xác minh.
- Nếu bảng gắn/default là cây partition con, việc xác minh có thể đi xuống các partition lá.

Chi tiết lock, thời gian chờ và tác động của các trường hợp phụ thuộc phiên bản/DDL thực tế; khi triển khai, đọc đúng tài liệu phiên bản server.

### 6.2. Vì sao nên chuẩn bị bảng trước?

Đưa những bước tốn tài nguyên ra trước cửa sổ attach:

1. Nạp dữ liệu vào standalone table.
2. Kiểm tra phạm vi.
3. Validate CHECK.
4. Tạo index tương ứng.
5. Chạy `ANALYZE` nếu cần.
6. Chỉ sau đó mới `ATTACH`.

Mục tiêu là **rút ngắn công việc cần làm khi giữ lock trên parent và các đối tượng tham gia**.

### 6.3. Giới hạn thời gian chờ lock

Trong một transaction DDL riêng trên lab:

```sql
-- Ví dụ cách dùng SET LOCAL, không chạy lại nếu bảng đã attach:
-- BEGIN;
-- SET LOCAL lock_timeout = '5s';
-- ALTER TABLE partition_lifecycle_lab.events
-- ATTACH PARTITION partition_lifecycle_lab.events_2026_03
-- FOR VALUES FROM ('2026-03-01 00:00+00')
--            TO ('2026-04-01 00:00+00');
-- COMMIT;
```

`lock_timeout` giúp thao tác **thất bại có kiểm soát nếu chờ lock quá lâu**, thay vì treo vô hạn trong quá trình triển khai. Khi lỗi xảy ra trong transaction, rollback và đánh giá điều kiện trước khi thử lại.

### 6.4. ATTACH không có tùy chọn CONCURRENTLY tương đương DETACH

PostgreSQL có cú pháp `DETACH PARTITION CONCURRENTLY` để giảm lock trên parent trong những trường hợp được hỗ trợ, nhưng không có một `ATTACH PARTITION CONCURRENTLY` tương đương để chỉ cần thêm chữ `CONCURRENTLY`.

Để tối ưu ATTACH online, dùng **staging + validated CHECK + index chuẩn bị sẵn + quản lý lock/timeouts**.

---

## 7. Default partition: ích lợi và cái giá của sự linh hoạt

Một **default partition** nhận các hàng không khớp với các bound đã khai báo.

### 7.1. Tạo default partition

Sau khi hoàn tất các kịch bản DETACH CONCURRENTLY ở phần 10, có thể thử:

```sql
-- Bài lab nên chạy phần này SAU phần detach concurrent,
-- vì default partition hạn chế DETACH ... CONCURRENTLY.
CREATE TABLE partition_lifecycle_lab.events_default
PARTITION OF partition_lifecycle_lab.events
DEFAULT;
```

Nếu có default partition, một `INSERT` với tháng chưa có partition cụ thể có thể đi vào bảng default thay vì báo “không tìm thấy partition”.

### 7.2. Tại sao default có thể làm ATTACH khó hơn?

Giả sử đã có default và trong đó đang có sự kiện tháng Tư. Sau này bạn muốn:

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_04
FOR VALUES FROM ('2026-04-01 00:00+00')
           TO ('2026-05-01 00:00+00');
```

Khi thêm partition tháng Tư, các hàng tháng Tư **không còn được phép thuộc default partition**. PostgreSQL phải chứng minh default **không chứa** hàng nào rơi vào bound mới. Nếu có, attach có thể **thất bại** cho tới khi dữ liệu được di chuyển một cách nhất quán.

### 7.3. Tác động scan và lock default

Nếu không có CHECK phù hợp loại trừ bound mới, PostgreSQL có thể phải scan default partition khi attach. Với default partition khổng lồ, việc này làm thời gian DDL/khóa tăng mạnh.

Một CHECK đã validated trên default chứng minh:

```text
event_time < lower_bound
OR
event_time >= upper_bound
```

có thể giúp tránh scan xác minh cho bound mới, **nếu đúng với mọi hàng hiện có và đủ chặt theo quy tắc PostgreSQL**.

### 7.4. Không thể chỉ copy rồi attach khi default vẫn chứa bản gốc

Sai về mặt quy trình:

```text
1. COPY các hàng tháng Tư từ default sang staging April.
2. ATTACH April ngay.
3. Bỏ mặc các hàng tháng Tư vẫn nằm trong default.
```

Khi attach, default còn hàng thuộc April nên không còn hợp lệ. Ngoài ra, hệ thống có writer đồng thời có thể tiếp tục đưa bản ghi tháng Tư vào default trong lúc di chuyển.

**Quy trình phải xử lý nhất quán**: xác định cửa sổ ghi/khóa, chuyển đúng hàng từ default sang bảng đích, xóa hàng gốc và ngăn race với writers trước/đến khi attach. Với hệ thống lớn, cần thiết kế migration có transaction, locks và backfill phù hợp thay vì chép mẫu SQL không kiểm soát.

### 7.5. DEFAULT không thay thế lịch tạo partition

Default giúp giảm nguy cơ INSERT thất bại khi thiếu partition, nhưng có thể:

- Trở thành bảng lớn khó prune.
- Khiến attach partition mới phải validate thêm.
- Làm khó `DETACH PARTITION CONCURRENTLY`.
- Che dấu việc vận hành quên tạo partition đúng hạn.

Một phương án là **không dùng default**, tạo partition trước nhiều kỳ và giám sát lỗi định tuyến. Một phương án khác là default có kiểm soát với quy trình kiểm tra/migrating định kỳ. Chọn theo SLA và năng lực vận hành.

---

## 8. DETACH PARTITION: đưa dữ liệu ra khỏi parent

`DETACH PARTITION` ngắt quan hệ partition giữa bảng con và parent, giữ lại bảng đó như một **bảng độc lập**.

### 8.1. Cú pháp cơ bản

```sql
ALTER TABLE parent_table
DETACH PARTITION partition_table;
```

Ví dụ, sau khi tháng Một không cần nằm trong tập truy vấn online:

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_01;
```

### 8.2. Sau DETACH điều gì xảy ra?

Trước:

```text
events parent
  events_2026_01   <- các SELECT qua parent có thể thấy
  events_2026_02
  events_2026_03
```

Sau:

```text
events parent
  events_2026_02
  events_2026_03

events_2026_01     <- bảng standalone vẫn tồn tại
```

Các hàng tháng Một **không còn xuất hiện trong query qua parent**, nhưng vẫn còn trong `events_2026_01`.

### 8.3. Kiểm tra bằng SQL

```sql
SELECT COUNT(*) AS visible_from_parent
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-01 00:00+00';
```

Sau khi detach January và không có các partition/default khác mang hàng January, kết quả là **0**.

Nhưng:

```sql
SELECT COUNT(*) AS rows_in_detached_table
FROM partition_lifecycle_lab.events_2026_01;
```

sẽ đếm được **2 hàng** theo dữ liệu demo.

### 8.4. DETACH không tự giải phóng disk

Đây là một hiểu nhầm nghiêm trọng trong retention:

```text
DETACH:
  parent không thấy hàng cũ
  standalone table vẫn chiếm storage

DROP TABLE detached_table:
  xóa đối tượng và dữ liệu của bảng đó
  dung lượng có thể được thu hồi theo quy tắc PostgreSQL
```

Nếu yêu cầu là **lưu trữ**, detach là bước chuyển trạng thái. Nếu yêu cầu là **xóa theo retention**, phải còn bước xóa table sau khi đáp ứng chính sách và kiểm tra an toàn.

### 8.5. Ảnh hưởng đến query/INSERT của ứng dụng

Sau khi detach:

- Query qua parent chỉ thấy các partition **còn attached**.
- Query trực tiếp bảng standalone vẫn có thể thấy dữ liệu cũ nếu role có quyền.
- Nếu ứng dụng cố INSERT sự kiện January vào parent và không có default/partition phù hợp, câu INSERT sẽ thất bại.
- Nếu có default, sự kiện January có thể bị định tuyến sang default, làm phá giả định “dữ liệu tháng January đã rút hoàn toàn khỏi online”.

Phải xác định policy về **late-arriving events** trước khi detach một kỳ.

---

## 9. Lock của DETACH thường

`DETACH PARTITION` không có `CONCURRENTLY` thường yêu cầu lock mạnh trên parent, điển hình **`ACCESS EXCLUSIVE`**, và có thể chặn những thao tác khác trong lúc thay đổi cấu trúc.

### 9.1. Vì sao nguy hiểm trong bảng có traffic cao?

`ACCESS EXCLUSIVE` xung đột với các loại lock khác, kể cả nhiều thao tác đọc thông thường trên parent. Dù thao tác DDL nhanh, **đợi lock** hoặc giữ lock có thể tạo một hàng đợi request.

Thời gian thực tế của việc detach phụ thuộc vào:

- Transaction dài đang dùng bảng/partition.
- Các lock khác trên parent.
- Số quan hệ phụ thuộc cần cập nhật.
- FK/trigger/index/DDL concurrent.
- Tải và phiên bản PostgreSQL.

### 9.2. Transaction có thể bọc DETACH thường

```sql
-- Mẫu minh họa nếu muốn áp deadline cho lock.
-- Không chạy lại sau khi January đã detached.
--
-- BEGIN;
-- SET LOCAL lock_timeout = '5s';
-- ALTER TABLE partition_lifecycle_lab.events
-- DETACH PARTITION partition_lifecycle_lab.events_2026_01;
-- COMMIT;
```

Ở dạng thường, việc đặt DETACH trong một transaction DDL hợp lệ có thể giúp phối hợp với thay đổi metadata khác. Nhưng **giữ transaction mở lâu sau DDL** có thể kéo dài thời gian giữ lock. Tổ chức transaction ngắn và có kiểm soát.

### 9.3. Khi nào nên dùng DETACH thường?

- Maintenance window có thể chấp nhận lock mạnh.
- Hệ thống nhỏ, số transaction ít.
- Môi trường không phù hợp/không hỗ trợ CONCURRENTLY.
- Có default partition (vì hạn chế của CONCURRENTLY).
- Cần phối hợp DDL theo một transaction có chủ đích.

Không mặc định dùng DETACH thường trên bảng traffic cao chỉ vì câu lệnh ngắn.

---

## 10. DETACH PARTITION CONCURRENTLY

PostgreSQL hỗ trợ dạng **`DETACH PARTITION CONCURRENTLY`** trong các phiên bản hiện đại nhằm giảm mức khóa trên parent và tránh chặn lâu các hoạt động thông thường khi có transaction khác đang dùng cây partition.

### 10.1. Cú pháp

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_02
CONCURRENTLY;
```

Trong lab, sau khi detach January, February vẫn attached và **chưa tạo default partition**, nên có thể dùng February để thử dạng concurrent.

### 10.2. Vì sao khác DETACH thường?

Khái quát:

```text
DETACH thường:
  lock mạnh trên parent
  thay đổi quan hệ partition
  hoàn tất trong một giao dịch DDL

DETACH CONCURRENTLY:
  giảm lock cần trên parent
  thực hiện nhiều pha / nhiều transaction nội bộ
  có thể chờ những transaction đang sử dụng parent
  có trạng thái "pending detach" giữa các pha
```

`DETACH CONCURRENTLY` thường dùng lock kiểu **`SHARE UPDATE EXCLUSIVE`** trên parent thay vì `ACCESS EXCLUSIVE` ở dạng thường, nhưng không có nghĩa không còn lock, wait hoặc ảnh hưởng performance.

### 10.3. KHÔNG chạy trong transaction block tường minh

Không làm:

```sql
-- KHÔNG HỢP LỆ:
-- BEGIN;
-- ALTER TABLE partition_lifecycle_lab.events
-- DETACH PARTITION partition_lifecycle_lab.events_2026_02
-- CONCURRENTLY;
-- COMMIT;
```

`CONCURRENTLY` cần cơ chế giao dịch riêng của PostgreSQL nên không được chạy trong `BEGIN ... COMMIT` tường minh. Đặc biệt lưu ý các **migration frameworks** thường tự bọc toàn bộ migration trong một transaction.

### 10.4. KHÔNG hỗ trợ khi parent có DEFAULT partition

Một giới hạn cần nhớ: **`DETACH PARTITION CONCURRENTLY` không được dùng nếu parent có default partition**.

Đây là lý do lab tạo default **sau** phần thử detach concurrent. Với hệ thống production có default, hãy thiết kế phương án phù hợp thay vì chỉ thêm `CONCURRENTLY` rồi mong DDL thành công.

### 10.5. Hai pha và pending detach

Ở dạng đồng thời, PostgreSQL thực hiện công việc trong **hai transaction**. Đại ý:

1. Pha đầu đánh dấu partition được tách theo quy trình phù hợp và commit.
2. Chờ những transaction còn dùng quan hệ parent thuộc phạm vi cần thiết.
3. Pha tiếp theo hoàn tất việc detach.

Nếu bị gián đoạn ở giữa, partition có thể ở trạng thái **pending detach**, chưa phải standalone hoàn chỉnh theo cách có thể xử lý tùy ý.

### 10.6. Khôi phục thao tác bị gián đoạn với FINALIZE

Khi xác nhận có một partition đang pending detach do thao tác concurrent trước đó bị ngắt, có thể dùng:

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_02
FINALIZE;
```

**Chỉ chạy khi thật sự có pending detach phù hợp**, không phải lệnh bạn thực thi tự động mỗi lần. Nếu detach concurrent đã thành công, bảng February không còn là partition của parent nên lệnh FINALIZE không có ý nghĩa.

### 10.7. Không có nhiều pending detach cùng lúc

PostgreSQL đặt hạn chế đối với những thao tác detach concurrent chưa hoàn tất. Nếu một partition còn pending, bạn phải **hoàn tất/khôi phục** trạng thái đó theo quy trình trước khi tiếp tục thay đổi tương ứng.

Đừng cho nhiều job retention độc lập chạy `DETACH CONCURRENTLY` trên cùng một parent mà không có điều phối.

### 10.8. Khi nào nên dùng CONCURRENTLY?

- Parent có tải đọc/ghi thường xuyên.
- Không có default partition.
- Migration runner cho phép DDL **ngoài transaction**.
- Có thể chờ và giám sát những transaction còn sử dụng bảng.
- Có runbook xử lý pending detach/`FINALIZE` khi bị gián đoạn.

Không sử dụng như một giải pháp bỏ qua mọi kiểm tra FK/backup/retention.

---

## 11. Quan sát cây partition và trạng thái DETACH

### 11.1. pg_partition_tree

PostgreSQL hiện đại hỗ trợ:

```sql
SELECT *
FROM pg_partition_tree(
    'partition_lifecycle_lab.events'::regclass
);
```

Hàm trả về quan hệ root, con và cấp độ, giúp kiểm tra những partition **còn thuộc cây**.

### 11.2. pg_inherits và trạng thái pending detach

```sql
SELECT
    child_ns.nspname AS child_schema,
    child.relname AS child_name,
    parent_ns.nspname AS parent_schema,
    parent.relname AS parent_name,
    inh.inhdetachpending
FROM pg_inherits AS inh
JOIN pg_class AS child
    ON child.oid = inh.inhrelid
JOIN pg_namespace AS child_ns
    ON child_ns.oid = child.relnamespace
JOIN pg_class AS parent
    ON parent.oid = inh.inhparent
JOIN pg_namespace AS parent_ns
    ON parent_ns.oid = parent.relnamespace
WHERE inh.inhparent =
    'partition_lifecycle_lab.events'::regclass
ORDER BY child.relname;
```

`inhdetachpending` được dùng trong các phiên bản hỗ trợ concurrent detach. Nếu phiên bản PostgreSQL cũ không có trường này, dùng tài liệu/catal​og đúng phiên bản; không coi query trên là portable tới mọi phiên bản.

Giá trị **TRUE** cho biết quan hệ kế thừa/partition đang ở trạng thái pending detach cần được chẩn đoán trước khi tiếp tục.

### 11.3. Xem bound từ catalog

```sql
SELECT
    child.relname AS partition_name,
    pg_get_expr(child.relpartbound, child.oid)
        AS partition_bound
FROM pg_class AS child
JOIN pg_inherits AS inh
    ON inh.inhrelid = child.oid
WHERE inh.inhparent =
    'partition_lifecycle_lab.events'::regclass
ORDER BY child.relname;
```

Đây là cách kiểm tra **bound do database đang thực thi**, thay vì tin tên bảng `events_2026_03` tự chứng minh nó là dữ liệu tháng Ba.

### 11.4. tableoid để biết hàng thuộc partition nào

```sql
SELECT
    tableoid::regclass AS leaf_table,
    COUNT(*) AS rows_count
FROM partition_lifecycle_lab.events
GROUP BY tableoid
ORDER BY tableoid::regclass::text;
```

Query trên cho biết số hàng đang visible qua parent theo từng relation chứa row. Partition trống không xuất hiện trong kết quả `GROUP BY tableoid`; để thấy cả partition rỗng cần dùng catalog.

### 11.5. Xem index đi cùng partition

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'partition_lifecycle_lab'
ORDER BY tablename, indexname;
```

Đừng suy rằng khi DETACH, mọi index trên bảng cũ bị xóa. Bảng standalone vẫn cần index/constraints riêng cho việc truy vấn và lưu trữ; cách các index được liên kết/đặt tên cần kiểm tra catalog sau DDL.

---

## 12. Kiểm tra partition pruning bằng EXPLAIN

### 12.1. Query một tháng

Trước khi detach một partition đang dùng trong ví dụ, thử:

```sql
EXPLAIN
SELECT event_id, tenant_id, event_time
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-04-01 00:00:00+00';
```

Nếu March attached và không có default chứa dữ liệu cần xét, plan có thể chỉ đọc `events_2026_03`.

### 12.2. Seq Scan trên đúng partition vẫn có thể là tốt

Kế hoạch minh họa:

```text
Seq Scan on events_2026_03
  Filter: (event_time >= ... AND event_time < ...)
```

Nếu March chỉ có 3 hàng trong lab, quét nó là lựa chọn rẻ. **Partition pruning đã hoạt động** nếu các partition Jan/Feb không còn nằm trong plan dù không dùng B-tree.

### 12.3. Query không có partition key

```sql
EXPLAIN
SELECT event_id
FROM partition_lifecycle_lab.events
WHERE tenant_id = 10;
```

Điều kiện `tenant_id` không phải partition key trong thiết kế RANGE theo `event_time`. Planner có thể phải xem nhiều partition; index `(tenant_id,event_time)` trên từng partition vẫn có thể giúp truy cập trong từng partition.

### 12.4. Đừng biến đổi partition key không cần thiết

```sql
-- Không ưu tiên nếu muốn prune theo timestamp range:
-- WHERE event_time::date = DATE '2026-03-15'
```

Biến đổi `TIMESTAMPTZ` thành `DATE` còn phụ thuộc timezone và có thể làm khó khả năng suy ra bound RANGE. Với một ngày theo UTC:

```sql
WHERE event_time >= TIMESTAMPTZ '2026-03-15 00:00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-03-16 00:00:00+00'
```

Với ngày nghiệp vụ theo timezone khác, chuyển **hai mốc ngày địa phương** sang instant tương ứng rồi bind giá trị typed.

### 12.5. Runtime partition pruning

Với prepared statements và một số kiểu plan, PostgreSQL có thể prune partition ở **thời điểm thực thi** dựa trên giá trị tham số:

```sql
PREPARE events_by_window(TIMESTAMPTZ, TIMESTAMPTZ) AS
SELECT event_id, event_time
FROM partition_lifecycle_lab.events
WHERE event_time >= $1
  AND event_time < $2;

EXPLAIN EXECUTE events_by_window(
    TIMESTAMPTZ '2026-03-01 00:00+00',
    TIMESTAMPTZ '2026-04-01 00:00+00'
);

DEALLOCATE events_by_window;
```

Không kết luận “generic plan thì luôn quét toàn bộ partition”. PostgreSQL hỗ trợ các hình thức pruning lúc planning và execution tùy loại plan, tham số và version. Hãy xem `EXPLAIN`, các nhánh bị loại, `Subplans Removed` hoặc `never executed` khi có.

---

## 13. Index, PRIMARY KEY và UNIQUE khi ATTACH/DETACH

### 13.1. Mỗi partition có storage/index riêng

Index được khai báo trên parent định hướng các index tương ứng trên từng partition; trong declarative partitioning kiểu này không có một B-tree global bao phủ tất cả partition.

Vì thế trước khi attach bảng staging lớn, hãy kiểm tra:

- Index cần phục vụ query trên partition mới.
- Index/constraint tương ứng với parent.
- Tính hợp lệ của các index có sẵn.
- Chi phí tạo index trong thời gian attach.

### 13.2. Khóa chính cần bao gồm partition key

Với parent:

```sql
PRIMARY KEY (event_time, event_id)
```

PostgreSQL có thể đảm bảo uniqueness theo cặp khóa này nhờ cách dữ liệu được phân bố và ràng buộc ở partitions.

Nhưng:

```text
event_id=123, event_time=2026-01-10
event_id=123, event_time=2026-02-10
```

khác cặp khóa và không bị PK composite cấm. Nếu nghiệp vụ yêu cầu **event_id duy nhất toàn hệ thống**, cần một chiến lược cấp ID/kiểm soát bổ sung (ví dụ service cấp số, bảng khóa định danh riêng, thay đổi mô hình key) và hiểu giới hạn uniqueness của partitioned table.

### 13.3. Quy tắc với UNIQUE/PRIMARY KEY

Đối với partitioned parent, một unique/primary-key constraint hợp lệ phải bao gồm tất cả cột partition key theo những giới hạn PostgreSQL áp dụng; các biểu thức dùng làm partition key cũng có giới hạn khi cần khai báo uniqueness ở parent.

Không áp dụng máy móc cú pháp unique của bảng thường lên partitioned parent mà không kiểm tra partition scheme.

### 13.4. Index sau DETACH

Khi tách partition:

- Bảng con trở thành bảng standalone.
- Index vật lý trên bảng vẫn có thể tồn tại, dưới dạng index của chính bảng standalone.
- Các liên kết metadata với partitioned indexes/constraints của parent được thay đổi theo quy tắc DDL.
- Cần kiểm tra lại `pg_indexes` và `pg_constraint`, đặc biệt nếu muốn làm archive độc lập hoặc attach vào parent khác.

Không giả định detaching là một thủ tục tự xóa mọi index để giảm disk.

---

## 14. Foreign key, trigger và các phụ thuộc vòng đời

### 14.1. Partition không độc lập tuyệt đối về nghiệp vụ

Một partition có thể đang nằm trong các quan hệ:

- Foreign key tới bảng khác.
- Foreign key từ bảng khác tham chiếu đến parent/partition theo khả năng phiên bản.
- Trigger/audit.
- Views/materialized views.
- Các job ETL/CDC/logical replication.
- Quyền truy cập, policy, schema và storage configuration.

Trước khi DETACH hoặc DROP, cần xác định **ai còn tham chiếu dữ liệu của kỳ đó**.

### 14.2. Lệnh DROP có thể bị FK/dependency ngăn

`DROP TABLE` không luôn thành công nếu có đối tượng phụ thuộc. **Không dùng `CASCADE` như phương án “cho chạy được”** mà không đọc danh sách đối tượng sẽ bị ảnh hưởng: CASCADE có thể kéo theo việc bỏ ràng buộc hoặc đối tượng quan trọng khác.

### 14.3. Trigger có thể tác động tới bảng khác

Một `INSERT`/`UPDATE` trên parent/partition có thể kích hoạt trigger theo cấu hình và phiên bản. Khi attach/detach, cách trigger được kế thừa/clone/phụ thuộc cần được đánh giá cụ thể.

Một archive table standalone có thể không còn chịu các policy/routing giống khi nó là partition. Không suy rằng “đã detach nhưng mọi trigger/authorization vẫn giống 100%”.

### 14.4. Đừng biến dữ liệu archive thành lỗ hổng quyền

Sau DETACH, một ứng dụng có thể vẫn truy cập bảng standalone nếu được cấp quyền. Nhưng các quy tắc authorization vốn dựa vào parent hoặc RLS/policy có thể không còn được áp dụng theo cách bạn kỳ vọng.

Khi tách dữ liệu nhạy cảm:

1. Rà soát owner, grants và RLS của bảng standalone.
2. Xác định role nào được đọc archive.
3. Kiểm tra chính sách encryption/masking và backup.
4. Không chỉ đổi tên bảng rồi coi như đã bảo vệ dữ liệu.

---

## 15. Quản lý vòng đời: hot, warm, archive, delete

Một chính sách retention có thể được mô tả:

| Giai đoạn | Tuổi dữ liệu ví dụ | Nơi lưu | Truy cập |
|---|---|---|---|
| **Hot** | 0–30 ngày | Partition attached, index đầy đủ | Ứng dụng online |
| **Warm** | 31–90 ngày | Partition attached, index theo workload | Báo cáo/đối chiếu |
| **Archive** | 91 ngày–2 năm | Detached table hoặc lưu trữ ngoài | Theo quyền/nhu cầu |
| **Delete** | Hết retention | Xóa bảng/bản sao tương ứng theo chính sách | Không còn truy cập thường |

Đây là **ví dụ**, không phải chính sách bắt buộc. Hệ thống tài chính, y tế, pháp lý hoặc dữ liệu cá nhân có thể có thời hạn lưu trữ, legal hold và nghĩa vụ xóa khác nhau.

### 15.1. Tạo partition trước khi tháng bắt đầu

Với dữ liệu theo tháng:

```text
Ngày 20 tháng N:
    chuẩn bị partition N+1

Ngày 01 tháng N+1:
    writer đã có partition hợp lệ

Sau khi tháng N-3 đóng sổ:
    kiểm tra late events / đối soát
    DETACH partition N-3

Sau khi archive được xác nhận:
    DROP standalone table nếu retention cho phép
```

Không đợi tới khi INSERT lỗi vì thiếu partition rồi mới tạo tháng kế tiếp.

### 15.2. Một partition có thể không trùng với “tháng gần nhất” ở mọi timezone

Nếu partition key `TIMESTAMPTZ` và bound được viết UTC, tháng January của hệ thống là **tháng theo UTC**. Người dùng ở vùng giờ +07 có thể coi một số instant tối cuối ngày UTC là ngày đầu tháng địa phương.

Phải xác định rõ:

- Retention theo thời điểm UTC, ngày lịch địa phương hay thời điểm giao dịch?
- Bound được tính từ nguồn nào?
- Timestamp ở client/server có timezone không?
- Có cần giải quyết ngày DST ở các thị trường khác không?

Không tự coi `event_time::date` của session bất kỳ là cơ sở để xác định partition retention.

### 15.3. Late-arriving events

Một sự kiện xảy ra tháng Một nhưng đến server tháng Tư có thể mang `event_time` tháng Một. Nếu partition January đã detach:

- Không có default/partition January: INSERT vào parent thất bại.
- Có default: hàng có thể đi vào default, làm loãng retention.
- Nếu ứng dụng ép `event_time=received_at` để tránh lỗi, có thể làm sai dữ liệu nghiệp vụ.

Giải pháp tùy hợp đồng:

- Cho phép một **grace period** trước khi detach.
- Có staging đặc biệt cho late events và xử lý đối soát.
- Ghi vào kho archive qua pipeline được kiểm soát.
- Từ chối late events quá hạn với thông báo rõ.

Không dùng `ATTACH`/`DETACH` như thay thế cho chính sách xử lý dữ liệu đến trễ.

### 15.4. Legal hold

Nếu một kỳ đang bị giữ theo yêu cầu điều tra hoặc nghĩa vụ pháp lý, hệ thống **không được tự động DROP** partition đó chỉ vì cron đã đến ngày. Tách việc xác định **hết hạn theo thời gian** khỏi việc **được phép xóa**.

### 15.5. Không quên backup và replica

Partition đã detach vẫn là dữ liệu cần bảo vệ nếu chính sách lưu trữ yêu cầu. Trước khi xóa:

- Xác minh archive có bản sao hợp lệ.
- Xác minh backup có thể restore.
- Kiểm tra quyền truy cập/ẩn danh/encryption.
- Xem trạng thái replication/CDC.
- Chỉ xóa bản gốc theo quy trình được duyệt.

---

## 16. Export partition đã DETACH

Sau khi `events_2026_01` thành standalone, có thể xuất dữ liệu theo nhu cầu.

### 16.1. COPY ra client

Trong `psql`, ví dụ:

```sql
COPY (
    SELECT event_id, tenant_id, event_time,
           event_type, payload
    FROM partition_lifecycle_lab.events_2026_01
    ORDER BY event_time, event_id
)
TO STDOUT
WITH (FORMAT CSV, HEADER TRUE);
```

Ví dụ trên in CSV ra đầu ra client. Nếu muốn ghi file cục bộ từ `psql`, có thể dùng meta-command `\copy` phù hợp, với **đường dẫn do người vận hành chọn** và quyền file được bảo vệ.

### 16.2. Vì sao không xem COPY là backup đầy đủ?

CSV export có thể không giữ mọi thành phần:

- DDL, indexes và constraints.
- Ownership/grants/RLS.
- Trigger và các dependency.
- Kiểu/collation và các thiết lập khác.
- Sequence/cấu trúc liên quan.
- Tính nhất quán giữa nhiều bảng nếu export không có snapshot phù hợp.

Nếu cần một bản sao có thể phục hồi như một bảng PostgreSQL, dùng chiến lược backup/restore phù hợp (`pg_dump`, physical backup...) theo hướng dẫn vận hành. CSV phù hợp cho một số mục đích trao đổi/analytics, nhưng không tự thay backup.

### 16.3. Đối chiếu số hàng

Trước export:

```sql
SELECT COUNT(*) AS source_rows
FROM partition_lifecycle_lab.events_2026_01;
```

Sau export, đối chiếu:

- Số hàng.
- Tổng checksum/hash hoặc sample kiểm tra nếu có chiến lược đáng tin.
- Min/max event_time và event_id.
- Schema/version của dữ liệu.
- Quyền/đường dẫn/bucket retention của archive.

`COUNT(*)` bằng nhau chưa chứng minh mọi nội dung giống nhau, nhưng là một kiểm tra nền.

### 16.4. Tách lưu trữ không đồng nghĩa đã chuyển sang kho lạnh

Nếu detached table vẫn nằm trên cùng database và tablespace, disk vẫn bị sử dụng. Có thể cần:

- Export sang object storage.
- Copy/restore vào một archive database.
- Chuyển tablespace khi phù hợp và có quy trình quản lý.
- Dùng data warehouse/lake cho nhu cầu báo cáo.

Lựa chọn phải dựa vào cách truy xuất, RPO/RTO, chi phí và nghĩa vụ quản trị dữ liệu.

---

## 17. DROP TABLE partition cũ và xóa dữ liệu theo lô

### 17.1. Xóa toàn bộ một partition thường rẻ hơn DELETE từng hàng

Nếu đã detach và xác minh có thể xóa:

```sql
-- Chỉ chạy khi thật sự muốn hủy dữ liệu January trong lab:
-- DROP TABLE partition_lifecycle_lab.events_2026_01;
```

Đối với retention loại bỏ **toàn bộ một tháng**, DROP một bảng partition có thể tránh chi phí từng-row DELETE và dọn dead tuples tương ứng. Nhưng DDL vẫn có lock/dependencies và có thể tạo tác động lên catalog, backup, replication và ứng dụng.

### 17.2. Có thể DROP partition attached trực tiếp không?

Có thể `DROP TABLE` một partition đang attached, theo quy tắc và locks PostgreSQL, để loại partition cùng dữ liệu. Nhưng nếu muốn:

- Export/archive trước.
- Di chuyển sang kho khác.
- Kiểm tra nội dung tháng cũ.
- Có thời gian chờ trước xóa.

thì **DETACH trước** giúp tách rõ bước ngừng phục vụ online khỏi bước xóa cuối.

### 17.3. DELETE WHERE date vẫn khác DROP partition

```sql
DELETE FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-01 00:00+00';
```

Lệnh DELETE là row-level DML. Nó có thể:

- Ghi WAL cho nhiều hàng.
- Kích hoạt row-level triggers/FK work.
- Tạo dead tuples cần VACUUM.
- Giữ locks và tạo contention.
- Chạy rất lâu nếu khối lượng lớn.

Khi mục tiêu là xóa **trọn partition**, `DETACH/DROP` thường là chiến lược đáng xem xét, nhưng **ngữ nghĩa trigger/FK và bảo đảm nghiệp vụ khác**. Không thay row-level DELETE bằng DROP khi ứng dụng dựa vào trigger delete để thu hồi các tài nguyên khác.

### 17.4. TRUNCATE cũng có giới hạn

`TRUNCATE` nhanh cho nhiều bảng thường, nhưng có quy tắc lock/FK/transaction và phạm vi với parent/partitions. Không dùng `TRUNCATE parent` để “chỉ xóa tháng Một”: nó có thể tác động nhiều partition theo cách không mong muốn.

Nếu cần dọn một partition đang attached hoặc detached, xác định **chính xác bảng đích** và dependencies. Với lifecycle thông thường, archive rồi detach/drop là chuỗi dễ kiểm toán hơn.

### 17.5. DROP không bảo đảm dữ liệu biến mất khỏi mọi bản sao ngay lập tức

Sau DROP:

- Bản sao lưu cũ có thể còn dữ liệu theo retention của backup.
- Replica/CDC có độ trễ và quy tắc đồng bộ.
- Object storage export còn bản sao độc lập.
- Log/audit/application cache có thể còn thông tin.

Yêu cầu “xóa dữ liệu theo quy định” phải tính cả vòng đời những bản sao, không chỉ lệnh SQL trên primary.

---

## 18. Theo dõi size và phân bố partition

### 18.1. Dung lượng từng partition

```sql
SELECT
    c.oid::regclass AS relation_name,
    pg_size_pretty(
        pg_total_relation_size(c.oid)
    ) AS total_size
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'partition_lifecycle_lab'
  AND c.relkind = 'r'
ORDER BY pg_total_relation_size(c.oid) DESC;
```

`pg_total_relation_size` bao gồm những cấu phần lưu trữ liên quan như table/index/TOAST theo quy tắc của hàm. Đối tượng standalone sau detach vẫn xuất hiện trong schema nếu chưa DROP.

### 18.2. Thống kê từng partition

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'partition_lifecycle_lab'
ORDER BY relname;
```

`n_live_tup` và `n_dead_tup` là **ước lượng** từ thống kê, không phải số hàng chính xác tại thời điểm SELECT. Dữ liệu live/dead biến đổi theo workload và độ trễ của thống kê.

### 18.3. Xem transaction đang mở

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Transaction lâu có thể làm DDL phải chờ lock hoặc chờ pha của detach concurrent. Quyền xem thông tin phiên khác phụ thuộc role monitoring.

### 18.4. Xem blocking pids

```sql
SELECT
    pid,
    application_name,
    pg_blocking_pids(pid) AS blocking_pids,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

Quan sát vào thời điểm thao tác đang bị chặn. Sau khi session khác kết thúc, danh sách có thể rỗng; không suy rằng DDL trước đó không từng bị blocking.

---

## 19. Runbook vận hành ATTACH cho một kỳ mới

**Tình huống:** ngày 20/03 chuẩn bị partition April.

### Giai đoạn A — Thiết kế trước cửa sổ DDL

1. Chọn bound UTC/local đúng nghiệp vụ: `[2026-04-01, 2026-05-01)`.
2. Kiểm tra cây hiện tại không có partition chồng lấn.
3. Kiểm tra default partition và có dữ liệu April trong đó không.
4. Dự báo số hàng/index và dung lượng.
5. Xác nhận schema/constraints/index của April cần giống parent.
6. Lập kế hoạch xử lý late events và quyền ghi vào kỳ mới.

### Giai đoạn B — Chuẩn bị standalone table

```sql
-- Ví dụ minh họa: chỉ tạo khi chưa có April partition.
CREATE TABLE partition_lifecycle_lab.events_2026_04
(
    LIKE partition_lifecycle_lab.events
      INCLUDING DEFAULTS
      INCLUDING CONSTRAINTS
      INCLUDING INDEXES
);

ALTER TABLE partition_lifecycle_lab.events_2026_04
ADD CONSTRAINT events_2026_04_bounds_chk
CHECK (
    event_time >= TIMESTAMPTZ '2026-04-01 00:00+00'
    AND event_time < TIMESTAMPTZ '2026-05-01 00:00+00'
);
```

Trên bảng lớn phải bảo đảm CHECK đã validated. Nếu staging còn đang ghi, cần giao thức đóng băng/cắt writers phù hợp trước khi ATTACH.

### Giai đoạn C — ATTACH

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_04
FOR VALUES FROM ('2026-04-01 00:00+00')
           TO ('2026-05-01 00:00+00');
```

Trong production, triển khai cùng lock timeout, maintenance policy, giám sát và rollback plan. Nếu default chứa hàng April, **lệnh có thể thất bại** cho tới khi xử lý dữ liệu đó.

### Giai đoạn D — Hậu kiểm

```sql
SELECT *
FROM pg_partition_tree(
    'partition_lifecycle_lab.events'::regclass
);

EXPLAIN
SELECT event_id
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-04-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-05-01 00:00+00';
```

Hậu kiểm tại tầng ứng dụng còn nên bao gồm thử INSERT có kiểm soát, routing, metrics lỗi “no partition” và policy truy cập. Thí nghiệm ở đây không yêu cầu thay đổi trực tiếp dữ liệu production.

---

## 20. Runbook DETACH và lưu trữ một kỳ cũ

**Tình huống:** tháng January đã hết thời gian truy cập online.

### Giai đoạn A — Quyết định được phép detach

- Đã qua hạn cuối nhận sự kiện January?
- Đã đóng sổ và đối chiếu nghiệp vụ?
- Có late-arriving events cần xử lý không?
- Có query/báo cáo online còn cần January?
- Có FK/dependency từ bảng khác?
- Có legal hold hoặc yêu cầu audit?
- Có backup/restore plan cho dữ liệu?

### Giai đoạn B — Đảm bảo concurrency phù hợp

Đối với parent traffic thấp/maintenance window:

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_01;
```

Đối với parent traffic cao **không có default partition** và phiên bản hỗ trợ:

```sql
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_01
CONCURRENTLY;
```

**Chọn một trong hai**, không chạy liên tiếp hai lệnh trên cùng một partition. Ví dụ trong lab đã detach January ở phần 8 thì nó không còn attached; lệnh thứ hai lúc đó chỉ là cú pháp tham khảo.

### Giai đoạn C — Kiểm tra kết quả

```sql
SELECT COUNT(*) AS parent_january_rows
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-01-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-02-01 00:00+00';

SELECT COUNT(*) AS detached_rows
FROM partition_lifecycle_lab.events_2026_01;
```

Nếu parent không còn partition/default nào chứa January, kết quả parent là 0 và standalone vẫn giữ dữ liệu cũ.

### Giai đoạn D — Archive và xác minh

1. Ghi số hàng và min/max thời gian.
2. Xuất hoặc sao lưu với định dạng phù hợp.
3. Xác minh độ toàn vẹn/bản phục hồi.
4. Đăng ký nơi lưu, thời hạn giữ, quyền và người chịu trách nhiệm.
5. Theo dõi replica/CDC và consumers liên quan.

### Giai đoạn E — Xóa sau khi đủ điều kiện

```sql
-- Chỉ sau khi đáp ứng retention và được phép xóa:
-- DROP TABLE partition_lifecycle_lab.events_2026_01;
```

**Điểm cốt lõi:** DETACH và DROP là **hai quyết định vận hành khác nhau**. Không tự động thực hiện cả hai trong cùng một lệnh mà bỏ qua thời gian archive/kiểm chứng.

---

## 21. Tự động hóa lịch vòng đời

Một hệ thống có hàng trăm partition cần quy trình định kỳ thay vì thao tác thủ công dựa trên ngày tháng trong tên file SQL.

### 21.1. Ví dụ lịch theo tháng

```text
Hàng ngày:
  - kiểm tra thiếu partition cho 60 ngày tới
  - kiểm tra số hàng trong default (nếu có)
  - cảnh báo partition chưa được chuẩn bị

Hàng tháng, trước mốc chuyển kỳ:
  - tạo/ATTACH partition tháng kế tiếp
  - xác minh routing và indexes

Hàng tháng, sau khi kỳ cũ được đóng sổ:
  - kiểm tra retention/legal hold
  - DETACH (có concurrency phù hợp)
  - export/archive
  - checksum/restore test
  - DROP khi đã được phê duyệt
```

Đây là lịch minh họa; tần suất cần theo khối lượng dữ liệu và chính sách nghiệp vụ.

### 21.2. Scheduler không nên tự chế SQL từ input không tin cậy

DDL chứa **tên relation** và **bound**, không thể bind identifier bằng parameter giống giá trị trong SELECT. Nếu ứng dụng tạo tên partition từ ngày hoặc tenant:

- Validate khoảng thời gian và tên hợp lệ.
- Dùng cơ chế quote identifier tương ứng khi tạo SQL động.
- Không nối trực tiếp chuỗi do người dùng gửi vào tên bảng/SQL.
- Chạy với quyền DDL tối thiểu cần thiết.
- Có lock điều phối để hai scheduler không cùng tạo/attach một kỳ.

### 21.3. Idempotency của công việc vận hành

Một job tạo partition có thể được gửi lại sau timeout hoặc crash. Trước khi làm gì, nó cần đối chiếu **trạng thái thực tế trong catalog**:

```text
Partition April đã tồn tại?
    |
    +-- Có: bound/DDL/index đúng chưa?
    |       |
    |       +-- Đúng -> coi bước chuẩn bị đã xong
    |       +-- Sai  -> báo conflict, không ghi đè
    |
    +-- Không: tạo staging/attach theo runbook
```

Không dùng `DROP ... CASCADE; CREATE ...` làm cách “retry nhanh” cho một partition có thể đang chứa dữ liệu thật.

### 21.4. Chỉ một bộ điều phối DDL

Nhiều worker đồng thời có thể:

- Đua nhau tạo cùng một partition.
- Đụng locks trên parent.
- Chạy detach trong lúc attach.
- Làm xuất hiện pending detach chưa được xử lý.
- Thực thi DROP trước khi job export xác nhận xong.

Nên có một coordinator hoặc trạng thái công việc bền vững, phân biệt **PREPARED → ATTACHED → DETACHED → ARCHIVED → VERIFIED → DELETED** và các nhánh lỗi/retry.

### 21.5. Không giả định mọi bước có thể rollback như một transaction

Một số DDL có thể thực hiện trong transaction, nhưng `DETACH ... CONCURRENTLY` không chạy trong transaction block tường minh và gồm nhiều pha. Export sang hệ thống ngoài cũng không được rollback bởi PostgreSQL.

Vì vậy workflow phải có:

- Checkpoint trạng thái.
- Bước hậu kiểm.
- Idempotent retry khi có thể.
- Quy trình phục hồi khi dừng giữa chừng.

Đây là đặc điểm của **workflow quản lý vòng đời**, không chỉ là một câu SQL.

---

## 22. Những lỗi vận hành thường gặp

### 22.1. ATTACH sai khoảng

Bạn đặt tên `events_2026_04` nhưng bound:

```sql
FOR VALUES FROM ('2026-04-01') TO ('2026-06-01')
```

thì bảng có thể bao phủ **hai tháng**, dù tên chỉ nói April. PostgreSQL tin bound DDL, không kiểm tra ý nghĩa tên bằng lịch.

### 22.2. Chênh timezone

Một script tính tháng theo timezone local nhưng ghi bound UTC không tương ứng. Hàng sát nửa đêm có thể vào partition không như báo cáo nghiệp vụ dự đoán. Kiểm chứng boundary bằng timestamp có timezone cụ thể.

### 22.3. Quên tháng kế tiếp

Không có partition và không có default → INSERT thất bại. Có default → dữ liệu có thể dồn vào default, dẫn tới attach sau khó hơn.

### 22.4. Dùng tên bảng thay catalog làm nguồn tin

Một table tên `events_2026_01` có thể là standalone sau DETACH hoặc đã attach với bound khác. Trạng thái đúng cần đọc `pg_partition_tree`, `pg_inherits` và `pg_get_expr(relpartbound, ...)`.

### 22.5. Chạy DETACH CONCURRENTLY trong migration transaction

Framework bọc migration trong `BEGIN` khiến lệnh không hợp lệ. Cần cơ chế migration ngoài transaction hoặc chọn DETACH thường với kế hoạch lock.

### 22.6. Có default partition mà vẫn dùng CONCURRENTLY

PostgreSQL không hỗ trợ tổ hợp đó. Không bỏ qua error rồi coi partition đã tách.

### 22.7. Bỏ qua pending detach

Nếu CONCURRENTLY bị gián đoạn, một partition có thể vẫn pending. Phải xác định bằng catalog và xử lý `FINALIZE` khi thích hợp trước các thao tác tiếp theo.

### 22.8. Chỉ kiểm tra count sau DETACH

`COUNT(*)` giữa parent và standalone giúp xác nhận tính visible, nhưng không thay kiểm tra checksum, index/constraints, backup và quyền truy cập archive.

### 22.9. DETACH rồi nghĩ disk đã giảm

Standalone table còn tồn tại và chiếm dung lượng. Muốn giải phóng dung lượng từ data source cũ cần có bước xóa/chuyển theo chính sách.

### 22.10. DROP khi chưa kiểm tra legal hold

Xóa toàn bộ một tháng có thể vi phạm nghĩa vụ lưu giữ. Dùng retention state riêng và xác nhận quyền trước bước irreversible.

---

## 23. Phân biệt ATTACH/DETACH với DELETE, VACUUM và DROP

| Thao tác | Thay đổi tập rows của parent? | Dữ liệu gốc còn không? | Mục đích |
|---|---|---|---|
| `ATTACH PARTITION` | Parent bắt đầu thấy rows của bảng được attach | Còn, nay là partition | Đưa bảng vào cây |
| `DETACH PARTITION` | Parent ngừng thấy rows của partition tách | **Còn** trong standalone | Ngừng phục vụ online/chuẩn bị archive |
| `DELETE WHERE ...` | Xóa rows hợp điều kiện theo transaction | Dữ liệu committed bị xóa, tuple cũ cần VACUUM | Xóa chọn lọc |
| `TRUNCATE` | Loại rows trên bảng đích theo phạm vi lệnh | Không phải archive | Dọn nhiều hàng nhanh, lock mạnh |
| `DROP TABLE partition` | Partition/dữ liệu bị loại khỏi database | **Không còn bảng đó** | Xóa toàn kỳ khi được phép |
| `VACUUM` | Không đổi logic các rows còn sống | Không phải xóa partition | Thu hồi/tái sử dụng tuple storage đủ điều kiện |

Không thay thế một cách máy móc các lệnh này cho nhau. `DELETE` có row-level trigger, FK behavior và MVCC khác `DROP`. `VACUUM` không thay quyết định retention. `ATTACH` và `DETACH` quản lý **membership**, không làm thay policy bảo mật hoặc lưu trữ.

---

## 24. Tình huống nâng cao: partition nhiều tầng

PostgreSQL có thể có **subpartitioning**, ví dụ RANGE theo tháng rồi HASH theo tenant:

```text
events parent, RANGE(event_time)
   |
   +-- events_2026_03, HASH(tenant_id)
          |
          +-- events_2026_03_h0
          +-- events_2026_03_h1
          +-- events_2026_03_h2
          +-- events_2026_03_h3
```

### 24.1. ATTACH subtree

Một bảng được attach có thể bản thân là partitioned table, với các partition con. Khi PostgreSQL phải xác minh dữ liệu nằm trong bound, việc scan/lock có thể **đi qua các partition lá** nếu không có CHECK đủ chứng minh.

### 24.2. DETACH cả một tháng

Nếu parent chia tháng trước, detach partition cấp tháng có thể tách **cả một subtree** khỏi parent, giúp archive toàn bộ kỳ theo cách có cấu trúc.

Nhưng:

- Query trực tiếp subtree vẫn có thể lấy dữ liệu.
- Các bảng con/index/constraints vẫn tồn tại trong database.
- Có nhiều quan hệ cần tính kích thước và backup.
- FK/dependency/lock trở nên phức tạp hơn.

### 24.3. Đừng tạo quá nhiều partition vì “càng nhỏ càng nhanh”

Mỗi partition tạo thêm catalog metadata, index và công việc planning/DDL. Quá nhiều partition có thể làm tăng:

- Thời gian planning.
- Số file/relation phải quản lý.
- Công việc autovacuum/stats.
- Chi phí DDL/backup.
- Độ phức tạp vận hành và permissions.

Chọn độ hạt tháng/ngày/giờ dựa theo **data volume, truy vấn, retention granularity và chi phí quản lý**, không phải khẩu hiệu “partition càng nhỏ càng tốt”.

---

## 25. Bài tập thực hành có đáp án

### Bài 1 — RANGE có bao gồm cận trên?

Partition:

```sql
FOR VALUES FROM ('2026-03-01 00:00+00')
           TO ('2026-04-01 00:00+00')
```

**Hỏi:** hàng đúng `2026-04-01 00:00+00` thuộc partition March không?

**Đáp án:** Không. `FROM` bao gồm cận dưới, `TO` không bao gồm cận trên. Hàng đó thuộc April nếu có partition tương ứng.

### Bài 2 — Vai trò của ATTACH

**Hỏi:** ATTACH table 5 triệu hàng có mặc định copy 5 triệu hàng sang relation mới không?

**Đáp án:** Không. Nó gắn bảng hiện có làm partition. Nhưng có thể phải quét validate dữ liệu, đối chiếu/tạo index và giữ locks.

### Bài 3 — Phân biệt CREATE PARTITION OF và ATTACH

**Đáp án:** `CREATE TABLE ... PARTITION OF` tạo partition mới trực tiếp; `ATTACH PARTITION` gắn **bảng đã tồn tại** có cấu trúc/rows hợp lệ vào parent.

### Bài 4 — Viết ATTACH April

**Đáp án:**

```sql
ALTER TABLE partition_lifecycle_lab.events
ATTACH PARTITION partition_lifecycle_lab.events_2026_04
FOR VALUES FROM ('2026-04-01 00:00+00')
           TO ('2026-05-01 00:00+00');
```

Chỉ chạy khi bảng April đã tồn tại, phù hợp schema và không có bound chồng lấn.

### Bài 5 — CHECK giúp tránh scan

**Câu hỏi:** Tại sao chuẩn bị CHECK đã validated cho staging trước ATTACH?

**Đáp án:** Để PostgreSQL có bằng chứng mọi hàng của staging nằm trong bound partition, có thể tránh quét toàn bộ staging lúc attach, giảm thời gian giữ lock.

### Bài 6 — CHECK không đủ chặt

Staging March có CHECK `event_time >= '2026-01-01'`. Có đủ chứng minh March không?

**Đáp án:** Không, vì CHECK vẫn cho phép February/April. Cần ràng buộc đủ bao phủ cả cận dưới và cận trên March, đã được xác thực.

### Bài 7 — NOT VALID

**Câu hỏi:** CHECK mới thêm với `NOT VALID` có được xem là bằng chứng mọi hàng cũ hợp lệ chưa?

**Đáp án:** Chưa. Cần `VALIDATE CONSTRAINT` thành công trước khi dùng nó làm cơ sở bỏ validation scan.

### Bài 8 — ATTACH có default chứa April

Default đang chứa hàng April, bạn attach April partition. Điều gì có thể xảy ra?

**Đáp án:** PostgreSQL phải kiểm tra default không còn hàng thuộc bound mới. Nếu vẫn có, attach có thể thất bại. Cần chuyển dữ liệu nhất quán và ngăn concurrent writers gây race.

### Bài 9 — Lock ATTACH

**Đáp án:** ATTACH cần `SHARE UPDATE EXCLUSIVE` trên parent và có thể lấy `ACCESS EXCLUSIVE` trên bảng được attach/default khi xác minh, nên cần chuẩn bị CHECK/index và giám sát DDL.

### Bài 10 — DETACH không xóa dữ liệu

**Hỏi:** Sau `DETACH PARTITION events_2026_01`, SELECT qua parent có thấy January không? Bảng January có còn?

**Đáp án:** Parent không còn nhìn thấy rows từ partition đó; `events_2026_01` vẫn tồn tại như standalone table và có thể query trực tiếp.

### Bài 11 — Disk sau DETACH

**Đáp án:** Dung lượng không tự giảm chỉ vì detach. Bảng standalone còn lưu dữ liệu/index; cần archive/drop theo chính sách nếu muốn giải phóng storage.

### Bài 12 — DETACH CONCURRENTLY trong BEGIN

```sql
BEGIN;
ALTER TABLE partition_lifecycle_lab.events
DETACH PARTITION partition_lifecycle_lab.events_2026_02
CONCURRENTLY;
COMMIT;
```

**Đáp án:** Không hợp lệ. `DETACH ... CONCURRENTLY` không chạy bên trong explicit transaction block.

### Bài 13 — DEFAULT và CONCURRENTLY

Parent có default partition. Có thể dùng `DETACH ... CONCURRENTLY` không?

**Đáp án:** Không theo giới hạn PostgreSQL hiện hành. Phải chọn quy trình khác hoặc thiết kế lại default strategy.

### Bài 14 — Pending detach

**Câu hỏi:** Một thao tác concurrent detach bị gián đoạn giữa hai pha. Cần làm gì?

**Đáp án:** Kiểm tra trạng thái pending detach trong catalog, xác định thao tác chưa hoàn tất và dùng `ALTER TABLE ... DETACH PARTITION ... FINALIZE` khi đúng trường hợp, không chạy detach mới mù quáng.

### Bài 15 — Tại sao partition pruning không phải Index Scan?

Plan chỉ có `Seq Scan on events_2026_03`, không có January/February.

**Đáp án:** PostgreSQL đã prune những partition không liên quan. Seq Scan bên trong March nhỏ có thể vẫn tối ưu.

### Bài 16 — Query dễ prune

**Yêu cầu:** tìm tháng March theo UTC.

```sql
SELECT event_id
FROM partition_lifecycle_lab.events
WHERE event_time >= TIMESTAMPTZ '2026-03-01 00:00+00'
  AND event_time <  TIMESTAMPTZ '2026-04-01 00:00+00';
```

### Bài 17 — Primary key parent

**Hỏi:** Vì sao parent partitioned RANGE(event_time) dùng PK `(event_time,event_id)` thay vì PK chỉ `event_id`?

**Đáp án:** Quy tắc UNIQUE/PK của partitioned parent cần bao gồm partition key, vì không có index unique global kiểu phổ thông qua mọi partition. PK composite không đảm bảo `event_id` đơn lẻ duy nhất giữa tháng khác nhau.

### Bài 18 — DELETE vs DROP

**Câu hỏi:** Xóa 10 triệu hàng January bằng `DELETE` có cùng hệ quả với DROP một partition January không?

**Đáp án:** Không. DELETE là DML từng row, trigger/FK/WAL/MVCC khác. DROP loại cả relation và dữ liệu, cần xác định retention/permissions/dependencies.

### Bài 19 — Late events

Event January đến trong April sau khi January detached và parent không có default.

**Đáp án:** INSERT theo `event_time` January sẽ không có partition hợp lệ và thất bại. Cần grace period, staging/archive pipeline hoặc chính sách từ chối late events; không tự sửa timestamp gốc.

### Bài 20 — Export không thay backup

**Hỏi:** COPY CSV của detached table có giữ PK/index/trigger/permissions không?

**Đáp án:** Không đầy đủ. CSV giữ giá trị hàng theo định dạng xuất; muốn bản sao có thể phục hồi như PostgreSQL table cần backup/DDL và kiểm thử restore phù hợp.

### Bài 21 — Quản lý legal hold

Tháng January hết retention nhưng đang chịu legal hold.

**Đáp án:** Không tự động DROP. Cần lớp quyết định/xác nhận xóa độc lập với scheduler ngày tháng.

### Bài 22 — Nhận diện partition trong catalog

**Yêu cầu:** nêu cách xem bound thật.

**Đáp án:** Dùng `pg_inherits` kết hợp `pg_class` và `pg_get_expr(child.relpartbound, child.oid)`; không tin tên bảng đủ để chứng minh bound.

### Bài 23 — ATTACH CONCURRENTLY

**Hỏi:** Có cú pháp `ALTER TABLE ... ATTACH PARTITION ... CONCURRENTLY` giống DETACH không?

**Đáp án:** Không. Để giảm downtime ATTACH, chuẩn bị staging, validated CHECK, index, kiểm soát default và lock timeout.

### Bài 24 — Workflow lặp lại

**Câu hỏi:** Scheduler chạy lại sau timeout nhưng April đã attached. Nên `DROP April` rồi tạo lại cho chắc không?

**Đáp án:** Không. Kiểm tra catalog, bound, indexes và trạng thái. Nếu đã đúng, coi bước hoàn tất; nếu xung đột, báo và điều tra. Không phá dữ liệu để “idempotent hóa” bằng DROP.

### Bài 25 — Các giai đoạn retention

**Yêu cầu:** vẽ chuỗi vòng đời.

**Đáp án:**

```text
PREPARED
    -> ATTACHED / ONLINE
    -> CLOSED / VERIFIED
    -> DETACHED
    -> EXPORTED / ARCHIVED
    -> RESTORE-TESTED
    -> DELETED (khi hết retention và không legal hold)
```

### Bài 26 — Phân biệt DROP và archive

**Hỏi:** Một partition đã DETACH nhưng vẫn cùng tablespace và database có được xem là “đã lưu sang cold storage” không?

**Đáp án:** Không mặc định. Nó là standalone table vẫn lưu tại database; cold storage có thể đòi hỏi export/move và chính sách truy cập khác.

---

## 26. Checklist trước khi ATTACH/DETACH trong production

### Thiết kế partition

1. **Partition key và bound:** đảm bảo chính xác, không chồng lấn, cận trên nửa mở.
2. **Timezone:** quy định UTC hoặc mốc local được chuyển rõ ràng.
3. **Mức hạt phân vùng:** ngày/tháng/giờ cân bằng query pruning và chi phí quản trị.
4. **Primary key/unique:** gồm partition key theo giới hạn PostgreSQL; xác định uniqueness toàn nghiệp vụ.
5. **Index/constraint:** đồng nhất với parent, phù hợp query và yêu cầu ghi.

### ATTACH

6. **Staging table:** đúng cột/kiểu/NOT NULL/DEFAULT và cấu trúc cần thiết.
7. **Dữ liệu staging:** nằm hoàn toàn trong bound và đã kiểm tra ngoại lệ.
8. **Validated CHECK:** đủ chặt để chứng minh bound, tránh scan trong pha attach khi có thể.
9. **Index chuẩn bị sẵn:** tránh xây index lớn dưới lock của DDL.
10. **Default partition:** không có hàng thuộc bound mới hoặc đã được chuyển nhất quán.
11. **Lock/timeouts:** biết parent/child/default có thể bị khóa thế nào.
12. **Pruning và routing:** kiểm tra query và thử INSERT sau attach.

### DETACH

13. **Đã đóng sổ kỳ cũ:** không còn writer bình thường/late event chưa giải quyết.
14. **Phân biệt thường và CONCURRENTLY:** xem lock/transaction/default restrictions.
15. **Không bọc CONCURRENTLY trong BEGIN:** migration runner phải hỗ trợ ngoài transaction.
16. **Pending detach:** có runbook catalog inspection và FINALIZE.
17. **Foreign keys/dependencies:** xác định impact của bảng standalone.
18. **Permissions/RLS:** không để dữ liệu archive lộ ngoài phạm vi.

### Archive/delete

19. **Số hàng và ranh giới:** đối chiếu trước/sau, kiểm tra sample/hash khi cần.
20. **Backup/export:** định dạng đúng, có restore test và manifest lưu trữ.
21. **Retention/legal hold:** chỉ xóa khi policy và approval cho phép.
22. **DROP vs DETACH:** hiểu DETACH vẫn giữ disk, DROP mới loại relation.
23. **Replicas/CDC:** biết dữ liệu/schema có được đồng bộ và consumer ảnh hưởng thế nào.
24. **Giám sát tài nguyên:** DDL locks, WAIT, WAL, disk, autovacuum.

### Tự động hóa

25. **Scheduler idempotent:** không tạo/trùng/drop mù quáng khi retry.
26. **Một coordinator DDL:** tránh attach/detach cạnh tranh trên cùng parent.
27. **Có deadline và cảnh báo:** partition tháng sau phải sẵn trước ngày chuyển kỳ.
28. **Quy trình phục hồi:** nếu attach/detach/export bị gián đoạn thì có bước xác minh và tiếp tục an toàn.

---

## 27. Tổng kết

**`ATTACH PARTITION` gắn một bảng có sẵn vào cây partition; `DETACH PARTITION` đưa một partition đang attached trở lại thành bảng standalone.** Chúng giúp tổ chức dữ liệu theo vòng đời mà không cần di chuyển/xóa từng hàng trong những tình huống phù hợp.

Nhớ các nguyên tắc quan trọng:

- **RANGE partition dùng khoảng nửa mở**: `FROM` bao gồm, `TO` không bao gồm. Bound phải theo đúng timezone nghiệp vụ.
- **ATTACH có thể kiểm tra toàn bộ bảng staging và default partition**. Tạo/validate `CHECK` đủ chứng minh bound, chuẩn bị index trước để giảm chi phí trong cửa sổ DDL.
- **ATTACH cần lock**, ngay cả khi dữ liệu không được COPY sang bảng mới.
- **DETACH thường có lock mạnh trên parent**; `DETACH ... CONCURRENTLY` giảm mức khóa nhưng **không chạy trong transaction block** và **không dùng khi có default partition**.
- **CONCURRENTLY có thể để lại pending detach nếu bị gián đoạn**; cần quan sát trạng thái và dùng `FINALIZE` đúng trường hợp.
- **DETACH không xóa dữ liệu hay giải phóng storage**. Bảng cũ vẫn tồn tại, nên archive/backup/verify và DROP là những bước tách biệt.
- **Pruning không đồng nghĩa index scan**. Một plan Seq Scan chỉ trên partition cần thiết có thể hoàn toàn phù hợp.
- **Không coi partitioning là thay thế cho UNIQUE/FK/RLS/backup**. Cần thiết kế các bất biến, quyền và phụ thuộc trên toàn vòng đời.
- **Retention phải có quy trình nghiệp vụ**: xử lý late events, legal hold, replica/CDC, khôi phục và phê duyệt xóa.

**Câu hỏi cuối cùng cho mỗi kỳ dữ liệu:** “Partition mới đã được chuẩn bị và chứng minh bound hợp lệ chưa? Partition cũ có thật sự được phép rời online và được phép xóa chưa? Nếu thao tác bị ngắt giữa chừng, catalog và dữ liệu đang ở trạng thái nào, và có thể phục hồi an toàn ra sao?”

### Tài liệu PostgreSQL chính thức

- [Table Partitioning — Declarative Partitioning, Partition Maintenance](https://www.postgresql.org/docs/current/ddl-partitioning.html).
- [ALTER TABLE — ATTACH PARTITION, DETACH PARTITION, CONCURRENTLY, FINALIZE](https://www.postgresql.org/docs/current/sql-altertable.html).
- [CREATE TABLE — PARTITION OF, FOR VALUES, DEFAULT](https://www.postgresql.org/docs/current/sql-createtable.html).
- [Partition Pruning và Planner](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITION-PRUNING).
- [Indexes on Partitioned Tables](https://www.postgresql.org/docs/current/ddl-partitioning.html#DDL-PARTITIONING-DECLARATIVE-MAINTENANCE).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Catalog pg_inherits](https://www.postgresql.org/docs/current/catalog-pg-inherits.html).
- [Partition Information Functions](https://www.postgresql.org/docs/current/functions-admin.html).
- [EXPLAIN và đọc kế hoạch](https://www.postgresql.org/docs/current/using-explain.html).
- [COPY](https://www.postgresql.org/docs/current/sql-copy.html), [DROP TABLE](https://www.postgresql.org/docs/current/sql-droptable.html).
