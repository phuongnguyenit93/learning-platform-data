# Đánh giá ảnh hưởng của ghi dữ liệu đến chỉ mục, WAL và sao chép trong PostgreSQL

Một câu lệnh `INSERT`, `UPDATE` hoặc `DELETE` nhìn từ ứng dụng thường rất ngắn. Ví dụ:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;
```

Tuy nhiên, PostgreSQL không chỉ “sửa một ô trong bảng”. Tùy cấu trúc bảng, index và cấu hình hệ thống, thao tác có thể tạo phiên bản tuple mới theo **MVCC**, ghi hoặc cập nhật các mục trong **index**, tạo bản ghi **Write-Ahead Log (WAL)**, làm bẩn các trang bộ nhớ đệm, phát sinh công việc cho **VACUUM**, rồi truyền và áp dụng thay đổi ở các **replica**.

Nếu một dịch vụ tăng từ vài nghìn lên hàng triệu lần ghi mỗi ngày, những chi phí gián tiếp này có thể trở thành nguyên nhân khiến latency tăng, disk I/O cao, WAL phình lớn, replica chậm hoặc ổ đĩa `pg_wal` đầy. Một câu `UPDATE` “chỉ đổi một cột” đôi khi vẫn tạo nhiều I/O hơn một câu `INSERT`; một index mới giúp truy vấn `SELECT` nhanh lên nhưng làm workload ghi đắt hơn; và một transaction COMMIT thành công trên primary chưa tự động đồng nghĩa mọi standby đã áp dụng dữ liệu.

Bài học này hướng dẫn cách **phân tích toàn bộ đường đi của thao tác ghi**, cách **đo bằng công cụ PostgreSQL** và cách **đưa ra đánh đổi có cơ sở** giữa tốc độ ghi, tốc độ đọc, độ bền và độ trễ sao chép.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả đường đi từ câu `INSERT/UPDATE/DELETE` đến heap, index, WAL và standby.
2. Giải thích vì sao MVCC khiến `UPDATE` tạo phiên bản hàng mới và `DELETE` để lại tuple cần được dọn.
3. Phân biệt **HOT update** với non-HOT update và hiểu tác động của indexed columns, expression index, partial index và `fillfactor`.
4. Phân tích chi phí ghi cho B-tree và các loại index khác; nhận diện **write amplification**.
5. Giải thích vai trò WAL trong crash recovery, durability, backup/PITR và physical/logical replication.
6. Nhận diện ảnh hưởng của **full-page images (FPI)**, checkpoint, `wal_compression` và transaction lớn tới lượng WAL.
7. Phân biệt **physical streaming replication** và **logical replication**, đồng thời hiểu phạm vi của replica identity, publication/subscription.
8. Theo dõi các chỉ số như `n_tup_upd`, `n_tup_hot_upd`, `n_dead_tup`, kích thước index, `pg_stat_wal`, WAL LSN và replication lag.
9. Sử dụng `EXPLAIN (ANALYZE, BUFFERS, WAL)` trong **database thử nghiệm** để xem bằng chứng về chi phí của thao tác ghi.
10. Lựa chọn chiến lược batch, index, schema, VACUUM và replication phù hợp mà không tùy tiện tắt các cơ chế bảo đảm dữ liệu.
11. Giải thích tại sao giảm WAL hoặc giảm số index không phải lúc nào cũng là tối ưu đúng.
12. Xây dựng quy trình đánh giá rủi ro trước khi thực hiện một đợt cập nhật dữ liệu lớn.

**Phạm vi:** Tập trung vào PostgreSQL hiện đại, các bảng thông thường có WAL và MVCC. Những tính năng thống kê có thể khác nhau theo phiên bản hoặc quyền của tài khoản. Lab chỉ chạy trên database thử nghiệm; không làm benchmark hay thay đổi cấu hình production bằng cách sao chép nguyên các câu SQL minh họa.

---

## 2. Mô hình tư duy: một thao tác ghi đi qua những lớp nào?

Hình dung ứng dụng thực hiện một transaction thay đổi dữ liệu:

```text
Ứng dụng
   |
   v
BEGIN / INSERT / UPDATE / DELETE / COMMIT
   |
   +----> Kiểm tra quyền, ràng buộc, trigger, FK, khóa
   |
   +----> Heap/table pages: tuple mới, phiên bản mới hoặc đánh dấu xóa
   |           |
   |           +----> Dead tuples, page pruning, VACUUM trong tương lai
   |
   +----> Indexes: tạo/sửa các index tuples cần thiết
   |           |
   |           +----> Có thể phát sinh page split, bloat, write I/O
   |
   +----> WAL: ghi mô tả thay đổi có thể phục hồi
   |           |
   |           +----> Flush WAL để đáp ứng mức durability
   |           +----> Archive WAL / PITR
   |           +----> Physical streaming replication
   |           +----> Logical decoding / logical replication
   |
   +----> Dirty buffers được ghi xuống data files về sau
   |
   +----> COMMIT được xác nhận theo synchronous_commit
                 và cấu hình standby liên quan
```

Điểm quan trọng: **WAL không phải bản sao trực tiếp của câu SQL**, và ghi WAL không đồng nghĩa các trang dữ liệu heap/index đã được flush ngay lập tức.

PostgreSQL thực hiện nguyên tắc **write-ahead**: trước khi một thay đổi trang dữ liệu được xem là bền vững trên data file, WAL cần thiết để phục hồi thay đổi đó phải được ghi/flush theo yêu cầu. Việc ghi các data page được điều phối bởi bộ nhớ đệm, background writer, checkpointer và các tiến trình khác; sau crash, PostgreSQL có thể dùng WAL để khôi phục trạng thái nhất quán.

### 2.1. Ba loại chi phí khác nhau

| Lớp | Chi phí thường thấy | Điều cần đo |
| --- | --- | --- |
| Heap/MVCC | Tuple version mới, dirty buffers, dead tuples, VACUUM | Số hàng thay đổi, HOT, dead/live tuples, table size |
| Index | Index tuple mới, đọc/ghi trang, page split, bloat | Số/lựa chọn index, index size, plan, chi phí ghi |
| WAL/Replication | WAL records, FPI, flush, network send, standby replay/apply | WAL bytes/FPI, commit latency, slot retention, LSN lag |

Cùng một transaction có thể gây áp lực khác nhau lên cả ba lớp. Ví dụ thêm index có thể cải thiện đọc nhưng làm tăng WAL và chi phí update; giảm số transaction nhỏ có thể giảm overhead commit nhưng transaction rất lớn lại tạo burst WAL và lag dài.

### 2.2. Write amplification là gì?

**Write amplification** là hiện tượng một thay đổi logic nhỏ ở ứng dụng kéo theo nhiều hoạt động ghi vật lý hoặc công việc duy trì trạng thái.

Ví dụ khái niệm:

```text
Một UPDATE logic
  -> ghi một tuple version mới trong heap
  -> có thể tạo index entries mới ở nhiều index
  -> ghi WAL cho heap/index/page
  -> giữ tuple cũ cho MVCC
  -> VACUUM/pruning dọn sau
  -> WAL được gửi và áp dụng ở standby
```

Không có hệ số cố định kiểu “một UPDATE = năm lần ghi”. Chi phí thật phụ thuộc kiểu thao tác, số index, kích thước tuple, cách phân bố dữ liệu, trang heap còn chỗ trống, checkpoint, transaction, replica và cấu hình WAL.

---

## 3. Bộ dữ liệu thử nghiệm tự chứa

Ta dùng bảng `orders` có các cột thường thay đổi:

- `status`: trạng thái đơn.
- `amount`: số tiền.
- `note`: ghi chú có thể thay đổi nhiều lần.
- `customer_id`: khóa dùng để tra cứu.
- `updated_at`: thời điểm sửa.

Bảng được đặt trong schema riêng để tránh đụng dữ liệu ứng dụng.

> **Chỉ chạy trong database thử nghiệm được phép reset.** `DROP TABLE IF EXISTS` sẽ xóa dữ liệu của bảng lab cùng tên. Không áp dụng những lệnh này trên production.

### 3.1. Tạo bảng

```sql
CREATE SCHEMA IF NOT EXISTS dml_impact_lab;

DROP TABLE IF EXISTS dml_impact_lab.orders;

CREATE TABLE dml_impact_lab.orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELED')),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
) WITH (fillfactor = 80);
```

`fillfactor = 80` yêu cầu PostgreSQL dành lại một phần không gian trên trang heap khi chèn để tạo cơ hội đặt phiên bản UPDATE mới **cùng trang**. Đây là một đánh đổi: có thể cải thiện khả năng HOT khi phù hợp nhưng làm bảng ban đầu chiếm nhiều trang hơn. Không coi 80 là con số tối ưu cho mọi workload.

### 3.2. Nạp một tập dữ liệu vừa đủ để quan sát

```sql
INSERT INTO dml_impact_lab.orders (
    customer_id, status, amount, note,
    updated_at
)
SELECT
    (g.n % 500) + 1,
    CASE
        WHEN g.n % 10 = 0 THEN 'PAID'
        WHEN g.n % 10 = 1 THEN 'CANCELED'
        ELSE 'NEW'
    END,
    (g.n % 100000)::NUMERIC / 100,
    'initial-' || g.n::TEXT,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
FROM generate_series(1, 12000) AS g(n);

ANALYZE dml_impact_lab.orders;
```

Dữ liệu gồm 12.000 đơn, 500 mã khách hàng và ba trạng thái. Mỗi lần chạy sau khi reset lab cho một tập hợp có cấu trúc tương tự.

```sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_orders,
    COUNT(*) FILTER (WHERE status = 'NEW') AS new_orders
FROM dml_impact_lab.orders;
```

### 3.3. Tạo hai index minh họa

```sql
CREATE INDEX idx_orders_customer
ON dml_impact_lab.orders (customer_id);

CREATE INDEX idx_orders_paid_customer
ON dml_impact_lab.orders (customer_id)
WHERE status = 'PAID';

ANALYZE dml_impact_lab.orders;
```

Lúc này bảng có:

1. Index unique của primary key `order_id`.
2. B-tree index thường trên `customer_id`.
3. B-tree **partial index** trên `customer_id` nhưng chỉ chứa hàng `status = 'PAID'`.

Cả hai index mới phục vụ những kiểu truy vấn đọc khác nhau, nhưng cũng tạo thêm công việc bảo trì khi ghi. Chúng ta sẽ phân biệt UPDATE `note` và UPDATE `status`.

### 3.4. Một số câu SELECT đại diện

```sql
-- Tra cứu một đơn bằng primary key.
SELECT *
FROM dml_impact_lab.orders
WHERE order_id = 500;

-- Lịch sử đơn của một khách hàng.
SELECT order_id, status, amount
FROM dml_impact_lab.orders
WHERE customer_id = 25
ORDER BY order_id DESC;

-- Đơn PAID của một khách hàng.
SELECT order_id, amount
FROM dml_impact_lab.orders
WHERE customer_id = 25
  AND status = 'PAID';
```

Index thường đáng giữ khi chúng phục vụ **truy vấn thực tế quan trọng** và lợi ích đọc lớn hơn chi phí bảo trì/lưu trữ. Không xóa index chỉ vì nó xuất hiện trong đường ghi.

---

## 4. INSERT ảnh hưởng gì đến heap, index và WAL?

Khi INSERT một hàng vào bảng có WAL thông thường, PostgreSQL cần:

1. Xác thực kiểu dữ liệu, `NOT NULL`, `CHECK`, constraint và trigger liên quan.
2. Tìm vị trí phù hợp trong heap page; có thể cấp phát trang mới.
3. Ghi heap tuple mới.
4. Tạo các index tuple tương ứng cho những index mà hàng thỏa điều kiện. Với unique index/primary key, cần kiểm tra tính duy nhất.
5. Ghi WAL đủ để phục hồi các thay đổi được log.
6. Tại COMMIT, thực hiện các bước cần thiết theo chế độ durability và replication được cấu hình.

### 4.1. Một INSERT không chỉ chạm một trang

Nếu một hàng thuộc partial index `idx_orders_paid_customer`, INSERT có thể tạo index entry trong:

- Primary key index.
- `idx_orders_customer`.
- `idx_orders_paid_customer`.

Nếu hàng có `status = 'NEW'`, nó **không phải thành viên** của partial index PAID, nên không cần tạo entry cho index đó.

Tuy nhiên, engine vẫn phải đánh giá điều kiện của index và duy trì các cấu trúc liên quan. Chi phí chính xác thay đổi theo index, cache và bộ dữ liệu.

### 4.2. Ghi từng hàng so với ghi nhiều hàng

Hai dạng:

```sql
INSERT INTO dml_impact_lab.orders (
    customer_id, status, amount
)
VALUES (901, 'NEW', 10.00);

INSERT INTO dml_impact_lab.orders (
    customer_id, status, amount
)
VALUES (902, 'NEW', 20.00);
```

và:

```sql
INSERT INTO dml_impact_lab.orders (
    customer_id, status, amount
)
VALUES
    (901, 'NEW', 10.00),
    (902, 'NEW', 20.00);
```

vẫn cần ghi các hàng và duy trì index, nhưng dạng multi-row có thể giảm overhead round-trip, parse/plan và transaction/commit nếu ứng dụng đang gửi nhiều INSERT rời rạc. Lợi ích thực tế phụ thuộc driver, chuẩn bị statement và cách quản lý transaction.

**Lưu ý:** Các INSERT ví dụ này làm thay đổi bảng lab; chỉ chạy khi bạn muốn thử thêm hàng. Nếu cần giữ dữ liệu gốc, dùng transaction và `ROLLBACK`.

### 4.3. COPY thường hữu ích khi nạp dữ liệu lớn

Trong các đợt tải dữ liệu ban đầu, `COPY` thường hiệu quả hơn việc gửi từng INSERT riêng lẻ:

```sql
-- Cú pháp minh họa, không chạy nếu chưa có nguồn COPY hợp lệ.
COPY dml_impact_lab.orders (
    customer_id, status, amount, note
)
FROM STDIN WITH (FORMAT csv, HEADER true);
```

`COPY FROM STDIN` cần client hỗ trợ truyền dữ liệu qua giao thức COPY. Đây không phải một câu SQL tự lấy tệp CSV từ máy ứng dụng khi chạy riêng trong SQL editor.

Khi nạp dữ liệu quy mô lớn vào bảng mới, có thể cân nhắc **nạp trước rồi tạo index sau**, nếu downtime, constraint, độ an toàn và workload cho phép. Nhưng không nên tự bỏ unique/foreign key hoặc hủy index của bảng production đang phục vụ người dùng chỉ để tăng tốc import.

### 4.4. Sequence và gap không phải lỗi WAL

Cột `GENERATED ALWAYS AS IDENTITY` thường sử dụng sequence. Giá trị sequence được cấp **không bảo đảm liên tục không có khoảng trống** khi transaction rollback hoặc do cache/concurrency.

Đừng suy ra số hàng đã COMMIT bằng cách lấy `MAX(order_id) - MIN(order_id) + 1`. Việc có ID bị bỏ qua không đồng nghĩa WAL hỏng hoặc replica thiếu hàng.

---

## 5. UPDATE theo MVCC: vì sao một hàng có nhiều phiên bản?

Trong PostgreSQL, UPDATE một hàng thông thường không ghi đè nội dung tuple cũ tại chỗ theo mô hình đơn giản. PostgreSQL tạo **phiên bản tuple mới** để các transaction có snapshot khác nhau có thể quan sát dữ liệu đúng theo MVCC.

Ý tưởng:

```text
Trước UPDATE:
Heap page -> [tuple V1: amount=100]

UPDATE amount=120:
Heap page -> [tuple V1: phiên bản cũ]
             [tuple V2: amount=120]

Giao dịch mới đủ điều kiện nhìn V2
Giao dịch cũ có thể còn cần V1
V1 chỉ được dọn khi không còn cần cho MVCC
```

Các trạng thái commit/rollback và khả năng nhìn thấy phiên bản còn phụ thuộc transaction ID, snapshot, lock và metadata nội bộ. Sơ đồ trên chỉ diễn tả nguyên lý, không phải layout byte trên đĩa.

### 5.1. UPDATE một cột cũng có thể tạo nhiều I/O

```sql
UPDATE dml_impact_lab.orders
SET amount = amount + 1
WHERE order_id = 500;
```

Đây không chỉ là phép cộng một số: nó cần tìm hàng, khóa phù hợp, tạo phiên bản mới, ghi WAL và quyết định có cần các index tuple mới không.

Chi phí thay đổi đáng kể giữa:

- UPDATE một cột **không xuất hiện trong index**.
- UPDATE một cột là **khóa của index**.
- UPDATE một cột được dùng trong **predicate của partial index**.
- UPDATE một cột xuất hiện trong **biểu thức index** hoặc được lưu qua `INCLUDE`.
- UPDATE làm giá trị text tăng dài tới mức phải dùng TOAST.
- UPDATE với trigger ghi thêm sang những bảng khác.

### 5.2. UPDATE không thực sự đổi giá trị vẫn có chi phí

Ví dụ:

```sql
UPDATE dml_impact_lab.orders
SET amount = amount
WHERE order_id = 500;
```

Đừng giả định PostgreSQL tự bỏ qua UPDATE chỉ vì giá trị cuối bằng giá trị cũ. Trong đường thực thi thông thường, UPDATE vẫn có thể tạo tuple version mới và WAL.

Khi ứng dụng chỉ muốn ghi nếu giá trị thật sự đổi:

```sql
UPDATE dml_impact_lab.orders
SET amount = 100.00
WHERE order_id = 500
  AND amount IS DISTINCT FROM 100.00;
```

`IS DISTINCT FROM` có ngữ nghĩa rõ cả khi cột nullable; nó giúp tránh thực hiện UPDATE nếu giá trị đã giống giá trị mong muốn.

Nếu cần trigger audit cho mọi yêu cầu cập nhật dù không đổi dữ liệu, việc bỏ qua UPDATE sẽ thay đổi nghiệp vụ. Phải thống nhất chính sách trước.

---

## 6. HOT update: một cơ hội giảm chi phí index

**HOT — Heap-Only Tuple update** — là tối ưu của PostgreSQL cho phép một số UPDATE tạo phiên bản heap mới **mà không cần thêm index entries mới**.

Điều kiện trọng tâm thường gồm:

1. UPDATE không làm thay đổi những cột mà các index thông thường phụ thuộc vào, bao gồm cả cột xuất hiện trong expression/predicate hoặc `INCLUDE` khi có liên quan. Quy tắc chi tiết có thể khác với index dạng *summarizing* như BRIN theo phiên bản.
2. Phiên bản tuple mới có thể đặt **trên cùng heap page** với phiên bản trước.
3. Những điều kiện hệ thống liên quan khác cho phép tối ưu HOT.

Nếu không đủ điều kiện, PostgreSQL phải thực hiện non-HOT update. Khi đó, việc tạo phiên bản mới có thể kéo theo **các index tuples mới cho các index của bảng**, ngay cả với index có khóa không đổi, vì hệ thống cần ánh xạ tới vị trí tuple mới.

### 6.1. Vì sao HOT quan trọng?

Giả sử bảng có 6 index. Một UPDATE chỉ sửa ghi chú:

```sql
UPDATE dml_impact_lab.orders
SET note = 'customer confirmed'
WHERE order_id = 500;
```

Nếu PostgreSQL thực hiện được HOT:

- Vẫn có phiên bản heap mới và WAL tương ứng.
- Nhưng không cần thêm entry mới vào từng index thông thường cho phiên bản này.
- Điều đó có thể giảm write amplification và hạn chế index bloat.

**HOT không có nghĩa “không ghi WAL”, “không sinh dead tuple” hoặc “không tốn chi phí”.** Nó chủ yếu giảm việc bảo trì index của UPDATE đủ điều kiện.

### 6.2. Tại sao fillfactor có liên quan?

Một UPDATE HOT cần phiên bản mới **cùng heap page**. Nếu page đầy, điều kiện này có thể không thỏa dù UPDATE chỉ đổi cột không indexed.

`fillfactor = 80` khi tạo bảng dành lại không gian trên page, nên có thể cải thiện khả năng HOT trong một số workload cập nhật thường xuyên.

Đánh đổi:

- Dùng fillfactor thấp hơn có thể giúp HOT nhiều hơn.
- Nhưng bảng có thể chiếm nhiều trang hơn, tăng footprint đọc/cache.
- UPDATE với giá trị dài/TOAST hoặc page bị phân bố khác vẫn có thể không HOT.
- Không có fillfactor chung tối ưu cho mọi bảng.

### 6.3. Ví dụ UPDATE dễ có cơ hội HOT

Vì `note` trong lab không nằm ở các index:

```sql
UPDATE dml_impact_lab.orders
SET note = note || '-reviewed'
WHERE order_id BETWEEN 200 AND 300;
```

Đây là **ứng viên HOT**, không phải bảo đảm tất cả 101 hàng đều HOT. Khả năng cụ thể phụ thuộc page còn chỗ, kích thước tuple và tình trạng bảng.

### 6.4. Ví dụ UPDATE khó có thể HOT

```sql
UPDATE dml_impact_lab.orders
SET customer_id = customer_id + 500
WHERE order_id BETWEEN 200 AND 300;
```

`customer_id` tham gia index thường và partial index, nên thay đổi có thể đòi hỏi cập nhật index. Không nên mong HOT theo quy tắc thông thường.

Một ví dụ khác:

```sql
UPDATE dml_impact_lab.orders
SET status = 'PAID'
WHERE order_id BETWEEN 201 AND 210
  AND status = 'NEW';
```

Cột `status` xuất hiện trong predicate của partial index `WHERE status='PAID'`. Khi đổi trạng thái, một số hàng **bắt đầu thuộc index**; việc bảo trì index là cần thiết.

### 6.5. Theo dõi HOT update

```sql
SELECT
    schemaname,
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'dml_impact_lab'
  AND relname = 'orders';
```

- `n_tup_upd`: bộ đếm UPDATE được thống kê.
- `n_tup_hot_upd`: số UPDATE dùng HOT theo thống kê.
- `n_dead_tup`: ước lượng dead tuples.
- `last_autovacuum`: lần autovacuum gần nhất nếu có.

Tỷ lệ khái niệm:

```text
HOT ratio = n_tup_hot_upd / n_tup_upd
```

Chỉ tính khi mẫu số khác 0, và nhớ rằng **thống kê tích lũy, có độ trễ và có thể bị reset**. Tỷ lệ từ một thời điểm không tự phản ánh chính xác chỉ một batch vừa chạy, nhất là khi có writer khác.

### 6.6. Indexed column không chỉ là khóa của index

Một index có thể phụ thuộc vào cột theo nhiều cách:

```sql
-- Index expression: thay đổi amount có thể tác động index.
CREATE INDEX idx_orders_amount_bucket
ON dml_impact_lab.orders ((ROUND(amount, 0)));

-- Index INCLUDE: cột amount cũng là dữ liệu thuộc index.
CREATE INDEX idx_orders_customer_cover
ON dml_impact_lab.orders (customer_id)
INCLUDE (amount);

-- Partial index: status được dùng trong điều kiện membership.
CREATE INDEX idx_orders_paid_example
ON dml_impact_lab.orders (amount)
WHERE status = 'PAID';
```

Các index trên chỉ là **minh họa**, không cần tạo đồng thời trong lab nếu chưa có nhu cầu đọc rõ ràng. Chúng có thể làm thay đổi khả năng HOT và chi phí UPDATE.

Nếu phải đánh giá “cột nào là cột HOT-friendly”, cần xem **toàn bộ index definitions**, bao gồm expression, predicate và INCLUDE, không chỉ các khóa bên trái dấu ngoặc của B-tree index.

---

## 7. Càng nhiều index, ghi dữ liệu càng đắt?

Index có mục đích chính là tăng tốc truy vấn và thực thi một số ràng buộc. Nhưng mỗi index cũng là một cấu trúc vật lý cần được duy trì.

### 7.1. Tác động theo thao tác

| Thao tác | Ảnh hưởng thường thấy tới index |
| --- | --- |
| `INSERT` | Tạo entry vào mỗi index phù hợp; kiểm tra unique nếu cần |
| `UPDATE` HOT | Có thể tránh tạo index entries mới cho phiên bản heap |
| `UPDATE` non-HOT | Có thể tạo nhiều index entries mới, tăng chi phí/bloat |
| `DELETE` | Đánh dấu tuple cũ không còn hợp lệ theo MVCC; index entries cũ không nhất thiết bị xóa vật lý ngay |
| `VACUUM` | Thu dọn dead tuples và index entries không còn cần thiết |
| `CREATE INDEX` | Quét bảng và xây index, tiêu thụ I/O/CPU; có thể tạo WAL |
| `REINDEX` | Xây lại cấu trúc index, tốn I/O/CPU, có rủi ro lock/khả dụng tùy chế độ |

Không phải mọi index đều có cùng chi phí. B-tree, GIN, GiST, SP-GiST, BRIN và các extension index có đặc tính riêng.

### 7.2. B-tree

B-tree phù hợp với nhiều điều kiện bằng, khoảng và sắp xếp. Ghi dữ liệu có thể thêm entry, sửa trang và đôi khi page split khi cây cần mở rộng.

Nếu một bảng có rất nhiều B-tree trên các tổ hợp cột khác nhau, INSERT/non-HOT UPDATE có thể chạm nhiều cấu trúc hơn. B-tree không “miễn phí” chỉ vì đọc nhanh.

### 7.3. GIN và chỉ mục tìm kiếm

GIN thường dùng cho mảng, JSONB hoặc full-text search. Tùy operator class và cấu hình, một hàng có thể đóng góp nhiều key/index entries.

Các cơ chế như pending list (khi `fastupdate` được bật) có thể dời một phần công việc cập nhật sang giai đoạn sau, tạo ra các đợt dọn/merge tốn tài nguyên. Độ trễ truy vấn đọc, VACUUM và đặc điểm workload cũng chịu ảnh hưởng.

Đừng đánh đồng chi phí ghi của GIN với B-tree chỉ dựa trên số lượng index.

### 7.4. BRIN

BRIN tóm tắt dữ liệu theo dải trang và thường rất nhỏ khi cột có tương quan với thứ tự vật lý của bảng. Nó có thể phù hợp với bảng thời gian lớn, append-heavy.

Tuy nhiên:

- BRIN không thay thế B-tree cho mọi truy vấn.
- Chất lượng lọc phụ thuộc tương quan dữ liệu và kích thước range.
- Cần duy trì thông tin tóm tắt.
- Ảnh hưởng của cập nhật cột được index đến HOT có các khác biệt theo phiên bản PostgreSQL; phải kiểm tra môi trường cụ thể trước khi dựa vào đó để tối ưu.

### 7.5. Partial index: ít entry hơn nhưng phải xem predicate

Trong lab:

```sql
CREATE INDEX idx_orders_paid_customer
ON dml_impact_lab.orders (customer_id)
WHERE status = 'PAID';
```

Index này chỉ chứa hàng PAID, có thể nhỏ hơn một index toàn bảng nếu tỷ lệ PAID thấp.

Nhưng khi UPDATE:

```sql
UPDATE dml_impact_lab.orders
SET status = 'PAID'
WHERE status = 'NEW'
  AND order_id BETWEEN 100 AND 200;
```

các hàng chuyển trạng thái có thể cần gia nhập partial index. Predicate cũng là yếu tố khi đánh giá HOT.

**Kết luận thực hành:** partial index có thể giảm footprint và tăng tốc truy vấn đặc thù, nhưng không miễn phí với những UPDATE thay đổi điều kiện membership.

### 7.6. Unique index và khóa chính không thể xóa tùy tiện

Một index do PRIMARY KEY/UNIQUE constraint tạo ra còn bảo đảm tính toàn vẹn dữ liệu trong concurrency. Việc loại nó để tăng throughput có thể tạo duplicate hoặc làm sai tham chiếu foreign key.

Khi tối ưu, hãy phân biệt:

- Index phục vụ **constraint bắt buộc**.
- Index hỗ trợ **truy vấn quan trọng**.
- Index dư thừa, không còn dùng hoặc trùng lặp **đã được chứng minh**.

Không đánh giá index chỉ qua tần suất `idx_scan`; một index unique hiếm khi scan vẫn có thể rất quan trọng để bảo đảm dữ liệu.

---

## 8. DELETE: không phải xóa vật lý ngay lập tức

Một câu:

```sql
DELETE FROM dml_impact_lab.orders
WHERE order_id = 500;
```

về ngữ nghĩa làm hàng biến mất khỏi những snapshot phù hợp sau khi COMMIT. Nhưng trên trang vật lý, PostgreSQL thường phải giữ tuple cũ một thời gian cho MVCC; các index entries liên quan cũng cần được dọn khi an toàn.

Vì thế, một chiến dịch DELETE lớn có thể:

- Ghi WAL đáng kể.
- Tạo lượng lớn dead tuples.
- Khiến VACUUM cần nhiều công việc hơn.
- Làm index/table lớn dù số hàng sống đã giảm.
- Gây áp lực I/O và replication.
- Giữ khóa/transaction lâu khi chạy trong một transaction quá lớn.

### 8.1. VACUUM làm gì?

`VACUUM` xử lý các tuple không còn cần thiết theo MVCC, tái sử dụng không gian trong bảng/index và cập nhật metadata liên quan.

Trong lab:

```sql
VACUUM (ANALYZE) dml_impact_lab.orders;
```

Đây là lệnh bảo trì trên database thực hành. Trên production, cần kế hoạch vận hành phù hợp, theo dõi autovacuum và tránh các can thiệp thủ công không cần thiết.

**VACUUM thường không tự trả tất cả dung lượng file về hệ điều hành.** Nó chủ yếu giúp không gian có thể được tái sử dụng bên trong relation; việc thu nhỏ file vật lý lớn có thể cần biện pháp khác như rewrite/repack với những đánh đổi và rủi ro riêng.

### 8.2. Autovacuum và long-running transactions

Autovacuum tự động giúp dọn dead tuples và duy trì khả năng tránh transaction ID wraparound. Nhưng nếu transaction lâu giữ snapshot cũ, PostgreSQL có thể chưa thể dọn một số phiên bản mà snapshot đó còn cần.

Điều này tạo vòng phản hồi bất lợi:

```text
UPDATE/DELETE nhiều
    -> dead tuples tăng
    -> transaction/snapshot lâu
    -> VACUUM bị hạn chế khả năng dọn
    -> bảng/index lớn, đọc/ghi thêm I/O
    -> replication/recovery cũng chịu áp lực
```

Không nên tắt autovacuum để “giảm CPU” mà không có thiết kế thay thế đầy đủ. Nguy cơ bloat và wraparound về sau có thể nghiêm trọng hơn chi phí autovacuum hiện tại.

### 8.3. DELETE theo batch

Thay vì một DELETE hàng triệu dòng trong một transaction, một số hệ thống chọn xóa từng batch có giới hạn để giảm thời gian giữ khóa, lượng WAL burst và độ trễ standby.

Một mẫu trên lab:

```sql
WITH batch AS (
    SELECT order_id
    FROM dml_impact_lab.orders
    WHERE status = 'CANCELED'
    ORDER BY order_id
    LIMIT 200
)
DELETE FROM dml_impact_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
RETURNING o.order_id;
```

Có thể lặp từng batch **qua những transaction riêng**, theo dõi số hàng đã xóa và dừng khi hết. Không viết một vòng lặp vô hạn trong một transaction rồi coi đó là batch theo nghĩa giảm transaction size.

Lưu ý:

- Có thể có writer đồng thời tạo thêm hàng đủ điều kiện.
- Một batch có thể bị block/đụng lock.
- Thứ tự `ORDER BY` cần ổn định.
- Đợt xóa phải có kế hoạch audit, backup và idempotency.
- Tổng WAL không nhất thiết giảm chỉ vì chia batch; một số overhead có thể tăng, nhưng đỉnh tải và thời gian khóa có thể dễ kiểm soát hơn.

### 8.4. TRUNCATE không đồng nghĩa DELETE

`TRUNCATE` có thể loại toàn bộ nội dung bảng nhanh hơn DELETE từng hàng và không sinh dead tuples theo cách tương tự, nhưng nó có ngữ nghĩa khác:

- Yêu cầu lock mạnh, thường `ACCESS EXCLUSIVE`.
- Có hệ quả đối với khóa ngoại và các bảng liên quan.
- Không gọi row-level DELETE triggers theo cách DELETE.
- Là DDL có tính transaction trong PostgreSQL; có thể rollback ở ngữ cảnh phù hợp.
- Có WAL/replication semantics riêng; không phải thao tác “không ghi WAL” đối với bảng thường.

Chỉ chọn TRUNCATE khi **yêu cầu thật sự là bỏ toàn bộ dữ liệu** và các bên liên quan đã chấp thuận.

---

## 9. WAL là gì và có vai trò gì?

**WAL (Write-Ahead Log)** là nhật ký ghi thay đổi giúp PostgreSQL phục hồi dữ liệu sau sự cố và cung cấp dòng thay đổi cho một số cơ chế backup/replication.

Mô hình:

```text
Transaction ghi heap/index
           |
           v
WAL records được tạo
           |
           v
WAL buffer / WAL files
           |
           +----> fsync/flush theo yêu cầu durability
           |
           +----> Crash recovery / redo
           |
           +----> WAL archive + base backup -> PITR
           |
           +----> WAL sender -> Physical standby
           |
           +----> Logical decoding -> Subscriber
```

Một điểm dễ nhầm: WAL **không chỉ chứa INSERT/UPDATE/DELETE ở cấp ứng dụng**. Nó còn ghi những sự kiện cần thiết cho phục hồi như thay đổi trang index, một số hoạt động bảo trì/metadata, full-page images và commit records.

### 9.1. WAL trước khi data page được ghi bền vững

PostgreSQL có thể trả kết quả COMMIT cho client khi WAL đã được flush theo chế độ đồng bộ liên quan, trong khi data pages heap/index chưa được ghi hết về file dữ liệu tại thời điểm đó.

Sau khi crash, hệ thống replay WAL để đưa data files tới trạng thái đúng.

Điều này giải thích vì sao **độ trễ flush WAL** có thể ảnh hưởng commit latency ngay cả khi write throughput trên bảng nhìn có vẻ nhỏ.

### 9.2. WAL không phải backup đầy đủ một mình

WAL archive hữu ích cho Point-in-Time Recovery (PITR), nhưng việc khôi phục thông thường cần một **base backup hợp lệ** và chuỗi WAL liên quan.

Không nên nghĩ “có WAL trên ổ đĩa nên không cần backup”. Cũng không nên coi một replica đơn thuần là chiến lược backup: thao tác xóa nhầm hoặc nhiều loại lỗi logic có thể được sao chép sang standby.

### 9.3. WAL và transaction rollback

Một transaction ghi thay đổi rồi ROLLBACK vẫn có thể đã sinh WAL cho các thao tác đã thực hiện. Rollback về mặt logic không phải thao tác xóa ngược các byte WAL đã ghi.

Vì vậy, chạy:

```sql
BEGIN;

UPDATE dml_impact_lab.orders
SET note = note || '-temporary'
WHERE order_id BETWEEN 1 AND 1000;

ROLLBACK;
```

giúp hoàn tác kết quả logic của UPDATE trong lab, nhưng **không đồng nghĩa phép thử không tạo WAL hoặc I/O**. Đây là lưu ý quan trọng khi đo bằng `EXPLAIN (ANALYZE, BUFFERS, WAL)`.

---

## 10. Vì sao một UPDATE nhỏ có thể tạo nhiều WAL?

WAL volume chịu ảnh hưởng bởi nhiều yếu tố:

| Yếu tố | Cơ chế tác động |
| --- | --- |
| Số hàng thay đổi | Nhiều tuple versions và WAL records |
| Kích thước tuple | Hàng lớn có thể tốn nhiều dữ liệu ghi/log |
| Số và loại index | Thay đổi index cũng tạo WAL |
| HOT hay non-HOT | Non-HOT thường có chi phí index nhiều hơn |
| Full-page images | Ghi ảnh trang sau checkpoint trong tình huống cần bảo vệ |
| Page split | Có thể phát sinh WAL và I/O bổ sung |
| TOAST | Giá trị lớn có thể tạo dữ liệu và index TOAST liên quan |
| Trigger / FK / cascade | Một thao tác logic có thể tạo thêm các thao tác ghi |
| Transaction batch | Commit overhead và đặc tính workload thay đổi |
| wal_level và replication | Dữ liệu WAL phục vụ logical decoding có thể nhiều thông tin hơn |
| Checkpoint/configuration | Ảnh hưởng FPI và write pressure |
| Unlogged/temporary tables | Có logging/data durability semantics khác bảng thường |

Không có công thức chính xác “WAL bytes = kích thước hàng mới” vì hệ thống còn phải log các thông tin trang và phục hồi.

### 10.1. Full-page images (FPI)

Khi `full_page_writes` được bật — cấu hình an toàn thông thường — lần thay đổi đầu tiên của một trang dữ liệu nhất định sau checkpoint có thể khiến PostgreSQL ghi **full-page image** vào WAL để bảo vệ chống tình trạng torn page.

Điều này có thể làm WAL tăng theo từng đợt:

```text
Checkpoint
    |
    +--> lần sửa đầu trên page A -> có thể kèm FPI
    +--> lần sửa tiếp trên A     -> không mặc định lại FPI
    +--> lần sửa đầu trên page B -> có thể kèm FPI
```

Không suy ra FPI chỉ xảy ra đúng một lần cho mỗi bảng; đơn vị liên quan là **page**, và điều kiện thực thi có những ngoại lệ/cơ chế riêng.

### 10.2. Checkpoint quá thường xuyên

Checkpoint thường xuyên có thể làm tăng số lần trang lại đi qua trạng thái “lần sửa đầu sau checkpoint”, làm số FPI tăng trong những workload phù hợp. Nó cũng có thể đẩy áp lực ghi dữ liệu thành những đợt.

Các cấu hình liên quan:

- `checkpoint_timeout`.
- `max_wal_size` (một soft limit ảnh hưởng lịch checkpoint, **không phải giới hạn cứng tuyệt đối cho thư mục pg_wal**).
- `checkpoint_completion_target` trong các phiên bản hỗ trợ.
- Tốc độ ghi và kích thước buffer.

Thay đổi checkpoint parameters phải dựa trên số liệu I/O, recovery-time objective, WAL archiving và tài nguyên thực tế, không áp dụng một con số tối ưu chung.

### 10.3. wal_compression

`wal_compression` có thể giảm dung lượng WAL của **full-page images** trong nhiều tình huống bằng cách nén dữ liệu trang, đổi lại tiêu tốn CPU cho nén/giải nén và có thể ảnh hưởng workload.

Không nên hiểu `wal_compression=on` là “nén toàn bộ WAL records theo tỷ lệ cố định”. Hiệu quả phụ thuộc FPI, loại trang, kiểu dữ liệu, CPU và thuật toán được PostgreSQL/phiên bản hỗ trợ.

### 10.4. Có nên tắt full_page_writes hoặc fsync?

**Không dùng việc tắt `full_page_writes` hoặc `fsync` như một mẹo tối ưu production thông thường.** Những setting này liên quan trực tiếp tới an toàn dữ liệu và khả năng phục hồi khi mất điện/crash.

Giảm durability để tăng benchmark có thể cho con số đẹp nhưng không còn đáp ứng yêu cầu hệ thống thật. Nếu so sánh hai cấu hình, phải giữ **cùng mức bảo đảm dữ liệu** hoặc ghi rõ rằng đang so hai hợp đồng durability khác nhau.

---

## 11. COMMIT, synchronous_commit và độ trễ xác nhận

Một câu hỏi thực tế: khi PostgreSQL trả COMMIT thành công, điều đó bảo đảm điều gì?

Điều này phụ thuộc vào `synchronous_commit`, cấu hình synchronous standby và cách hệ thống lưu trữ xử lý flush.

### 11.1. Các mức đồng bộ

Một số chế độ thường gặp:

| Chế độ | Trực giác | Đánh đổi |
| --- | --- | --- |
| `on` | Theo cấu hình, chờ local WAL flush và có thể chờ xác nhận từ synchronous standby | Durability tốt hơn theo cấu hình, latency có thể cao hơn |
| `local` | Chờ flush WAL local nhưng không chờ standby | Không đợi remote sync |
| `remote_write` | Khi có synchronous standby, chờ standby ghi WAL tới hệ điều hành, chưa nhất thiết flush bền vững | Có thể giảm latency nhưng bảo đảm remote yếu hơn remote flush |
| `remote_apply` | Khi có synchronous standby, chờ WAL được áp dụng để có thể được đọc trên standby theo chính sách | Latency có thể cao hơn |
| `off` | Không nhất thiết chờ WAL flush trước khi xác nhận commit | Có thể mất một số transaction vừa xác nhận nếu crash, không phù hợp mọi nghiệp vụ |

Các mode liên quan standby chỉ phát huy ý nghĩa chờ remote khi **synchronous replication thực sự được cấu hình**, ví dụ qua `synchronous_standby_names` phù hợp.

### 11.2. synchronous_commit=off có phải làm transaction sai ACID?

PostgreSQL vẫn duy trì cấu trúc WAL/recovery, nhưng với commit bất đồng bộ một số transaction vừa được xác nhận có thể mất trong crash trước khi WAL được flush. Đây là một đánh đổi durability có chủ đích.

Không nên chuyển sang `off` để chữa latency của hệ thống tài chính, đơn hàng hoặc dữ liệu quan trọng nếu chưa được phép và chưa đánh giá khả năng chấp nhận mất transaction.

### 11.3. Remote apply khác remote flush

Một standby đã **nhận** WAL chưa chắc đã **flush** WAL; đã flush WAL chưa chắc đã **replay** xong; replay xong chưa chắc một query cũ trên standby tự thấy ngay dữ liệu do snapshot của nó.

Vì thế “standby đã nhận COMMIT” và “ứng dụng có thể đọc thấy kết quả mới qua replica” không luôn là cùng mệnh đề.

---

## 12. Physical streaming replication: sao chép WAL vật lý

Physical replication truyền/áp dụng WAL để standby duy trì bản sao ở cấp **cấu trúc lưu trữ của cluster**.

Dòng dữ liệu khái niệm:

```text
Primary
  WAL sender
      |
      v
Network -> WAL receiver trên standby
                    |
                    v
             WAL được ghi/flush
                    |
                    v
             Recovery / WAL replay
                    |
                    v
             Heap, index, catalog được cập nhật
```

Do đó, nhiều thay đổi của index, page, cấu trúc bảng và schema ở primary sẽ được phản ánh qua WAL replay trên physical standby, theo giới hạn của tính năng/logging.

### 12.1. Index mới cũng làm replica phải làm việc

Nếu trên primary chạy:

```sql
CREATE INDEX idx_orders_amount
ON dml_impact_lab.orders(amount);
```

việc xây index có thể tạo CPU/I/O trên primary và WAL cần replay trên physical standby. Standby không đơn giản chỉ “nhận danh sách dòng SQL mới rồi tạo index bằng một câu SQL tự chạy”; nó khôi phục thay đổi vật lý từ WAL.

Một chiến dịch build/rebuild index lớn vì vậy có thể gây **WAL burst** và replication lag, dù ứng dụng không INSERT hay UPDATE nhiều.

### 12.2. Replica lag có nhiều giai đoạn

Có thể phân biệt các mốc:

- **Sent LSN**: primary đã gửi tới đâu.
- **Write LSN**: standby đã ghi WAL tới đâu.
- **Flush LSN**: standby đã flush WAL tới đâu.
- **Replay LSN**: standby đã áp dụng WAL tới đâu.

Tùy workload, bottleneck có thể nằm ở:

- Network/throughput.
- Disk WAL flush.
- CPU/I/O khi replay.
- Replay conflict với các truy vấn đọc dài ở standby.
- Đợt WAL lớn do DML/index/reindex/backfill.

Đừng chỉ nhìn một số “lag seconds” rồi kết luận chắc nguyên nhân là network.

### 12.3. Physical replication và UNLOGGED table

Dữ liệu của bảng `UNLOGGED` có logging/durability khác bảng thông thường và **không được sao chép qua physical streaming replication như dữ liệu bảng logged thông thường**. Bảng unlogged có thể bị truncate sau crash để bảo đảm tính nhất quán.

Vì vậy, `UNLOGGED` chỉ phù hợp với dữ liệu **có thể tái tạo hoặc chấp nhận mất**, chẳng hạn một số bảng staging/tạm, không phải tài khoản, thanh toán hoặc nguồn dữ liệu chính cần bền vững/replicated.

---

## 13. Logical replication: sao chép thay đổi ở mức dữ liệu

Logical replication sử dụng thông tin WAL và logical decoding để truyền thay đổi dữ liệu theo publication/subscription.

Khái niệm:

```text
Publisher PostgreSQL
   |
   +--> WAL với thông tin phục vụ logical decoding
   |
   +--> Logical decoding / replication slot
                |
                v
         Dòng thay đổi INSERT/UPDATE/DELETE ...
                |
                v
           Subscriber / Apply worker
                |
                v
         Các hàng được áp dụng ở bảng đích
```

Logical replication khác physical replication ở phạm vi và ngữ nghĩa:

| Khía cạnh | Physical | Logical |
| --- | --- | --- |
| Mức sao chép | WAL vật lý / cấu trúc cluster | Thay đổi dữ liệu logic theo publication |
| Phạm vi | Thường toàn cluster WAL-logged | Có thể chọn bảng và loại operation |
| Index của nguồn | Thay đổi vật lý được replay | Index/schema trên subscriber phải được quản lý riêng |
| DDL | Thay đổi schema logged được phản ánh vật lý | DDL **không tự được sao chép** qua cơ chế built-in logical replication |
| Sequence | Trạng thái vật lý được log/replay theo cơ chế tương ứng | Sequence progression không được logical replication đồng bộ như thay đổi hàng thông thường |
| Dùng cho | Standby, HA, read replica, PITR cùng dòng WAL | Chia sẻ dữ liệu chọn lọc, migration, tích hợp hệ thống |
| Chi phí ghi | WAL, gửi và replay | WAL đủ chi tiết, decode, send, apply, subscriber indexes |

### 13.1. wal_level và yêu cầu logical decoding

Để hỗ trợ logical replication, PostgreSQL cần mức WAL phù hợp, thường `wal_level = logical`. Nó có thể đòi hỏi ghi đủ thông tin bổ sung để decode các thay đổi và tiêu tốn thêm tài nguyên.

Không thay `wal_level` trên production một cách tùy tiện; thay đổi có thể cần restart và phải được phối hợp với kế hoạch replication/backup.

### 13.2. Publication không tự tạo schema trên subscriber

Ví dụ cú pháp **minh họa**, không cần chạy trong lab:

```sql
CREATE PUBLICATION orders_publication
FOR TABLE dml_impact_lab.orders
WITH (publish = 'insert,update,delete');
```

Nếu muốn có subscriber thật, phải cấu hình kết nối, quyền, publication/subscription, schema bảng đích và kế hoạch đồng bộ ban đầu. Không có một câu `CREATE PUBLICATION` đơn lẻ nào tự hoàn thành toàn bộ pipeline.

Ở cơ chế logical replication built-in, thay đổi schema như thêm cột hoặc tạo index không tự được truyền/apply như thay đổi dữ liệu DML. DDL hai phía phải được phối hợp riêng để tránh apply lỗi.

### 13.3. REPLICA IDENTITY cho UPDATE và DELETE

Để áp dụng UPDATE/DELETE trên subscriber, hệ thống cần biết **hàng đích nào** cần được sửa/xóa.

Thông thường PostgreSQL sử dụng primary key làm replica identity nếu có. Nếu bảng không có khóa thích hợp, publishing UPDATE/DELETE có thể gặp hạn chế hoặc yêu cầu cấu hình replica identity riêng.

Một lựa chọn:

```sql
-- Chỉ minh họa, KHÔNG tùy tiện chạy trên bảng production.
ALTER TABLE dml_impact_lab.orders
REPLICA IDENTITY FULL;
```

`REPLICA IDENTITY FULL` dùng thông tin hàng cũ rộng hơn để nhận diện hàng, có thể tăng lượng thông tin WAL và chi phí tìm/apply trên subscriber. Nó không phải phương án mặc định tốt hơn primary key.

Bảng lab đã có PRIMARY KEY `order_id`, nên trong tình huống thông thường **không cần chuyển sang FULL**.

### 13.4. Logical subscriber cũng có chi phí ghi riêng

Nếu subscriber có 5 index còn publisher chỉ có 2 index, mỗi thay đổi được logical replication apply có thể phải duy trì **5 index trên subscriber**, theo schema phía đó.

Bottleneck không nhất thiết ở network: apply worker, lock, constraint, index, large transaction và tài nguyên máy subscriber đều có thể giới hạn tốc độ.

### 13.5. Logical replication không tự giải quyết mọi xung đột

Built-in logical replication không phải giải pháp multi-master tổng quát cho phép hai phía tự do ghi rồi tự xử lý xung đột theo nghiệp vụ. Nếu subscriber ghi đè dữ liệu, schema không tương thích hoặc thiếu khóa nhận diện, apply có thể lỗi hoặc dừng.

Cần thiết kế ownership của dữ liệu, DDL rollout, phục hồi slot, xử lý conflict và theo dõi apply workers.

---

## 14. Replication slots và rủi ro đầy pg_wal

Replication slot giúp nguồn giữ những thông tin cần thiết cho consumer tiếp tục đọc WAL từ vị trí của nó, tùy loại slot và cấu hình.

Ví dụ tình huống:

```text
Primary tiếp tục ghi 20 GB WAL
    |
    +--> standby/logical consumer ngừng hoặc rất chậm
                |
                v
           Slot giữ LSN cũ
                |
                v
        WAL có thể không được tái sử dụng
                |
                v
             pg_wal tăng
                |
                v
          Nguy cơ đầy ổ đĩa
```

**Replication slot không phải cơ chế bảo đảm dung lượng WAL có giới hạn.** Nếu consumer chậm, slot có thể giữ WAL rất lâu; các cấu hình retention/limit có đánh đổi giữa an toàn giữ dữ liệu và nguy cơ slot mất khả năng tiếp tục.

### 14.1. Quan sát replication slots

Trên server có quyền xem thông tin phù hợp:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    restart_lsn,
    confirmed_flush_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Các cột:

- `slot_name`: tên slot.
- `slot_type`: physical hoặc logical.
- `active`: có consumer đang dùng slot hay không.
- `restart_lsn`: vị trí WAL sớm nhất có thể còn cần cho slot.
- `confirmed_flush_lsn`: mốc xác nhận của logical slot khi áp dụng.

Không suy ra slot inactive là vô hại. Một slot inactive kéo dài có thể là nguyên nhân giữ WAL.

### 14.2. Không drop slot chỉ để giải phóng dung lượng

Xóa slot đang cần cho replication có thể khiến consumer không thể tiếp tục từ vị trí trước đó và cần resync/rebuild. Đây là thao tác có hệ quả phục hồi và tính sẵn sàng.

Khi nghi WAL bị giữ bởi slot:

1. Xác định slot thuộc hệ thống/consumer nào.
2. Kiểm tra consumer có đang chạy và có lag không.
3. Kiểm tra khả năng phục hồi của consumer.
4. Đánh giá dung lượng ổ đĩa, retention, archiver.
5. Thực hiện kế hoạch được phê duyệt, không drop theo cảm tính.

### 14.3. WAL archive cũng có thể gây tồn đọng

Khi bật archiving, WAL segments có thể phải được giữ cho tới khi archive thành công. Nếu archive command/storage bị lỗi, lượng WAL chưa archive có thể tăng.

Một hệ thống có cả replica và PITR cần theo dõi **cả slots, standby lẫn archiver**, không chỉ mỗi `pg_stat_replication`.

---

## 15. Đo chi phí ghi bằng EXPLAIN (ANALYZE, BUFFERS, WAL)

Đây là công cụ trực tiếp nhất để quan sát **một statement cụ thể** trong lab.

> **Cảnh báo:** `EXPLAIN ANALYZE` **thực thi câu SQL**. Với UPDATE/DELETE/INSERT, nó thật sự ghi dữ liệu. Chỉ chạy trong database thử nghiệm; dùng `BEGIN ... ROLLBACK` nếu muốn hoàn tác thay đổi logic. Rollback **không xóa WAL/I/O đã phát sinh**.

### 15.1. Xem chi phí UPDATE cột không index

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE dml_impact_lab.orders
SET note = note || '-a'
WHERE order_id BETWEEN 200 AND 500;

ROLLBACK;
```

Quan sát phần plan có thể chứa thông tin kiểu:

```text
Update on orders ...
  Buffers: shared hit=..., dirtied=..., written=...
  WAL: records=..., fpi=..., bytes=...
  -> Index Scan ...
Planning Time: ...
Execution Time: ...
```

Đây là **mẫu dạng output**, không phải số đo thật của môi trường người học.

Ý nghĩa:

- `Buffers shared hit/read/dirtied/written`: hoạt động buffer được thống kê.
- `WAL records`: số WAL records do statement ghi nhận.
- `WAL fpi`: số full-page images.
- `WAL bytes`: khối lượng WAL được quy cho statement theo công cụ.
- `Execution Time`: thời gian statement trong phép đo.

Một plan có thể khác theo phiên bản, quyền, loại node và cài đặt. Đừng xem các con số minh họa như mục tiêu KPI.

### 15.2. So sánh với UPDATE cột indexed

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE dml_impact_lab.orders
SET customer_id = customer_id + 1000
WHERE order_id BETWEEN 200 AND 500;

ROLLBACK;
```

Câu này làm thay đổi `customer_id`, cột của các B-tree index. Trong nhiều điều kiện, WAL/index work có thể lớn hơn so với UPDATE cột không index.

Tuy nhiên, **không so sánh chỉ một lần rồi kết luận**: thời điểm checkpoint, cache nóng/lạnh, FPI, kích thước tuple, trạng thái page và hoạt động từ các phiên khác đều tác động.

### 15.3. So sánh status thay đổi partial-index membership

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE dml_impact_lab.orders
SET status = 'PAID'
WHERE order_id BETWEEN 201 AND 500
  AND status = 'NEW';

ROLLBACK;
```

Với các hàng NEW chuyển thành PAID, index một phần dành cho PAID có thể cần entry mới. Tác động khác với UPDATE note, kể cả số hàng được cập nhật bằng nhau.

### 15.4. Điều kiện để benchmark công bằng hơn

Nếu muốn so sánh chi phí một cách nghiêm túc:

- Dùng dữ liệu có kích thước và phân phối tương đương.
- Kiểm tra số hàng **thực sự** được cập nhật, không chỉ số hàng WHERE dự kiến.
- Đảm bảo cùng mức durability/replication.
- Ghi nhận checkpoint/FPI và điều kiện cache.
- Chạy nhiều lần trong môi trường được phép đo, tránh writer đồng thời.
- Đối chiếu latency, WAL bytes, buffers, CPU và index growth.
- Nêu rõ các lần thử rollback vẫn tạo hoạt động WAL.
- Không lấy kết quả bảng 12.000 hàng làm dự báo chắc chắn cho bảng 100 triệu hàng.

Đây là một phương pháp thiết kế phép thử, không phải yêu cầu chạy Content QA hoặc benchmark thực tế trong STEP 4.

---

## 16. Theo dõi thống kê table: UPDATE, HOT và dead tuples

PostgreSQL cung cấp `pg_stat_user_tables`.

```sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_del,
    n_tup_hot_upd,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_stat_user_tables
WHERE schemaname = 'dml_impact_lab'
  AND relname = 'orders';
```

Ý nghĩa cơ bản:

| Cột | Ý nghĩa |
| --- | --- |
| `n_tup_ins` | Số tuple được INSERT theo thống kê |
| `n_tup_upd` | Số tuple được UPDATE |
| `n_tup_del` | Số tuple được DELETE |
| `n_tup_hot_upd` | Số UPDATE theo HOT |
| `n_live_tup` | Ước lượng số tuple sống |
| `n_dead_tup` | Ước lượng dead tuples |
| `last_autovacuum` | Thời điểm autovacuum gần nhất nếu có |
| `vacuum_count` | Số lượt VACUUM thủ công theo thống kê |

**Không đọc các cột ước lượng này như con số transactionally exact.** Thống kê có cơ chế làm mới, tích lũy và reset; những writer khác có thể làm số liệu thay đổi.

### 16.1. Tỷ lệ HOT có thể tính thế nào?

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100::NUMERIC * n_tup_hot_upd
          / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_update_percent
FROM pg_stat_user_tables
WHERE schemaname = 'dml_impact_lab'
  AND relname = 'orders';
```

Nếu `n_tup_upd = 0`, biểu thức tỷ lệ trả NULL thay vì chia cho 0.

Một tỷ lệ HOT thấp là tín hiệu **đáng điều tra**, không tự chứng minh có lỗi. Có thể workload luôn đổi indexed columns nên HOT vốn không phù hợp; hoặc row size, fillfactor, index definitions và page placement hạn chế HOT.

### 16.2. VACUUM thống kê có thể chậm cập nhật

Khi theo dõi sau một batch ngắn, kết quả từ cumulative stats có thể chưa phản ánh ngay. Có thể gọi:

```sql
SELECT pg_stat_clear_snapshot();
```

để bỏ snapshot thống kê đã cache trong transaction/session, nhưng lệnh này **không biến các thống kê tích lũy thành công cụ đo per-statement chính xác**.

Không tùy tiện gọi hàm reset global statistics trong hệ thống đang monitoring; nó làm mất đường cơ sở của những người vận hành khác.

---

## 17. Đo kích thước heap, bảng và index

PostgreSQL có các hàm kích thước relation:

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('dml_impact_lab.orders'::REGCLASS)
    ) AS heap_main_size,

    pg_size_pretty(
        pg_table_size('dml_impact_lab.orders'::REGCLASS)
    ) AS table_storage_size,

    pg_size_pretty(
        pg_indexes_size('dml_impact_lab.orders'::REGCLASS)
    ) AS all_indexes_size,

    pg_size_pretty(
        pg_total_relation_size('dml_impact_lab.orders'::REGCLASS)
    ) AS total_relation_size;
```

Phân biệt:

- `pg_relation_size` mặc định đo **main fork** của relation.
- `pg_table_size` bao gồm phần storage của bảng và một số cấu trúc phụ trợ như TOAST/FSM/VM.
- `pg_indexes_size` là tổng kích thước index liên quan.
- `pg_total_relation_size` bao gồm bảng và index.

Các giá trị này phản ánh **dung lượng hiện tại**, không trực tiếp cho biết có bao nhiêu tuple còn được sử dụng hoặc cần VACUUM.

### 17.1. Xem từng index

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'dml_impact_lab'
  AND tablename = 'orders'
ORDER BY indexname;
```

Một cách xem size từng index theo catalog:

```sql
SELECT
    i.relname AS index_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size
FROM pg_class AS t
JOIN pg_namespace AS n
  ON n.oid = t.relnamespace
JOIN pg_index AS ix
  ON ix.indrelid = t.oid
JOIN pg_class AS i
  ON i.oid = ix.indexrelid
WHERE n.nspname = 'dml_impact_lab'
  AND t.relname = 'orders'
ORDER BY pg_relation_size(i.oid) DESC;
```

Nên đọc index size theo **thời gian** và so với hàng sống/khối lượng ghi. Một index lớn hơn sau INSERT mới là bình thường; lớn lên sau UPDATE/DELETE liên tục rồi không thu hồi/tái sử dụng có thể là dấu hiệu bloat.

### 17.2. Index usage stats không phải index write stats

```sql
SELECT
    indexrelname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE schemaname = 'dml_impact_lab'
  AND relname = 'orders'
ORDER BY indexrelname;
```

Các cột này chủ yếu phản ánh **hoạt động truy vấn đọc qua index**. Chúng không phải bộ đếm “bao nhiêu index tuple đã được INSERT do mỗi UPDATE”.

Đừng kết luận một index không tốn chi phí ghi chỉ vì không có `idx_scan`. Cũng đừng xóa một unique index chỉ vì thấp `idx_scan`.

---

## 18. Đo WAL toàn cluster với pg_stat_wal

PostgreSQL cung cấp thống kê WAL ở phạm vi server qua `pg_stat_wal` trên các phiên bản hỗ trợ.

```sql
SELECT
    wal_records,
    wal_fpi,
    wal_bytes,
    stats_reset
FROM pg_stat_wal;
```

| Trường | Ý nghĩa |
| --- | --- |
| `wal_records` | Tổng số WAL records theo bộ đếm |
| `wal_fpi` | Tổng full-page images theo bộ đếm |
| `wal_bytes` | Tổng bytes WAL theo bộ đếm |
| `stats_reset` | Mốc reset thống kê |

**Quan trọng:** `pg_stat_wal` là **thống kê toàn cluster**, không phải lượng WAL của riêng bảng lab hay riêng transaction hiện tại.

Khi server có nhiều người dùng, chênh lệch `wal_bytes` giữa hai thời điểm bao gồm cả hoạt động từ các session khác.

### 18.1. Đo theo LSN

PostgreSQL có địa chỉ WAL kiểu `pg_lsn`. Một số hàm hữu ích:

```sql
SELECT
    pg_current_wal_insert_lsn() AS current_insert_lsn,
    pg_current_wal_lsn() AS current_write_lsn,
    pg_current_wal_flush_lsn() AS current_flush_lsn;
```

Các khái niệm:

- **Insert LSN**: vị trí WAL đã được chèn vào WAL buffers.
- **Write LSN**: vị trí WAL được ghi.
- **Flush LSN**: vị trí WAL đã flush.

Có thể tính chênh lệch giữa hai LSN đã ghi nhận:

```sql
-- Chỉ minh họa cú pháp; hai LSN dưới đây không phải đo thật.
SELECT pg_wal_lsn_diff(
    '0/16B7C90'::PG_LSN,
    '0/16B6C10'::PG_LSN
) AS wal_distance_bytes;
```

Khi đo thật, hãy thu thập **hai mốc từ cùng server đúng thời điểm**; vì WAL là dòng chung, phép trừ LSN còn chứa hoạt động đồng thời và không tự quy mọi byte cho câu DML đang quan tâm.

### 18.2. Nên dùng số đo nào?

| Mục tiêu | Công cụ thường phù hợp |
| --- | --- |
| Một DML statement trong lab | `EXPLAIN (ANALYZE, BUFFERS, WAL)` |
| Tốc độ WAL toàn server qua thời gian | `pg_stat_wal`, LSN, monitoring |
| INSERT/UPDATE/DELETE và HOT theo table | `pg_stat_user_tables` |
| Dung lượng table/index | `pg_table_size`, `pg_indexes_size` |
| WAL đang bị giữ lại bởi slot | `pg_replication_slots` |
| Tiến độ standby theo gửi/nhận/apply | `pg_stat_replication` và standby WAL functions |
| Công việc archive WAL | `pg_stat_archiver` |

Không dùng một metric duy nhất để giải thích mọi loại chậm.

---

## 19. Quan sát replication lag trên primary

Trên **primary có streaming replication** và quyền quan sát phù hợp:

```sql
SELECT
    application_name,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn,
    pg_wal_lsn_diff(
        pg_current_wal_lsn(),
        replay_lsn
    ) AS primary_to_replay_bytes
FROM pg_stat_replication
ORDER BY application_name;
```

Kết quả có thể rỗng nếu không có standby kết nối/hiển thị tại thời điểm truy vấn.

**Diễn giải cẩn thận:** `primary_to_replay_bytes` là khoảng cách WAL giữa vị trí hiện tại của primary và mốc replay standby báo cáo. Nó không phải “dung lượng mạng đang truyền” thuần túy; cũng không phải độ trễ thời gian chuẩn hóa theo giây.

Các cột có thể NULL hoặc phản ánh trạng thái standby chưa gửi phản hồi mới nhất.

### 19.1. Phân loại bottleneck theo các mốc LSN

Một cách đọc mang tính định hướng:

```text
Primary current WAL LSN
        |
        v
      sent_lsn
        |
        v
      write_lsn
        |
        v
      flush_lsn
        |
        v
      replay_lsn
```

Nếu khoảng **sent → write** lớn, xem network/receive/ghi WAL trên standby.

Nếu khoảng **flush → replay** lớn, xem tốc độ replay, tài nguyên standby hoặc xung đột truy vấn.

Nhưng đây là cách **định hướng điều tra**. Mốc có độ trễ báo cáo và phụ thuộc trạng thái đồng bộ; cần kết hợp logs, CPU, disk và thời gian thực.

### 19.2. Trên standby: kiểm tra receive và replay

Trên **standby**:

```sql
SELECT
    pg_is_in_recovery() AS is_standby,
    pg_last_wal_receive_lsn() AS received_lsn,
    pg_last_wal_replay_lsn() AS replayed_lsn,
    pg_last_xact_replay_timestamp()
        AS last_replayed_commit_time;
```

`pg_last_xact_replay_timestamp()` là mốc timestamp của transaction commit/abort được replay gần nhất theo cách hàm định nghĩa; **không có transaction mới** cũng có thể khiến khoảng thời gian tính từ timestamp này tăng dù standby đã bắt kịp.

Vì vậy đừng suy ra chỉ từ “current time − last replay timestamp” rằng replication luôn chậm. Đối chiếu LSN, số transaction mới, tình trạng kết nối và workload.

### 19.3. Read-after-write trên replica

Một ứng dụng ghi vào primary rồi đọc ngay từ asynchronous standby có thể nhận dữ liệu **cũ**.

Các hướng thiết kế tùy nhu cầu:

- Đọc lại từ primary sau những thao tác cần nhất quán tức thì.
- Dùng cơ chế chờ tới khi standby đã replay tối thiểu LSN thích hợp, nếu hệ thống có thiết kế này.
- Cấu hình synchronous replication ở mức phù hợp khi yêu cầu và chi phí cho phép.
- Chấp nhận eventual consistency với UX/trạng thái rõ ràng cho nghiệp vụ không cần đọc tức thì.

Không mặc định “COMMIT thành công” trên primary đồng nghĩa mọi replica đọc được giá trị mới ngay lập tức.

---

## 20. WAL archiving và sức khỏe backup

Nếu tổ chức lưu archive WAL để PITR, cần theo dõi `pg_stat_archiver`:

```sql
SELECT
    archived_count,
    last_archived_wal,
    last_archived_time,
    failed_count,
    last_failed_wal,
    last_failed_time,
    stats_reset
FROM pg_stat_archiver;
```

Khi có một đợt backfill/UPDATE lớn:

- WAL volume tăng.
- Archiver có thể không theo kịp nếu throughput lưu trữ chậm.
- WAL segments chờ archive có thể tích tụ.
- Replication slots có thể đồng thời giữ WAL.
- Recovery-time objective và thời gian phục hồi có thể thay đổi.

**Rủi ro lớn:** coi `max_wal_size` là nắp cứng cho thư mục `pg_wal`. Trong tình huống cần giữ WAL vì slot/archiving và các điều kiện khác, dung lượng thực tế có thể tăng vượt mốc này.

Cần giám sát **dung lượng filesystem** và khả năng dừng ghi khi hết chỗ, không chỉ các tham số cấu hình.

---

## 21. Backfill hàng triệu dòng: những nguồn chi phí thường bị bỏ sót

Một yêu cầu điển hình:

> Điền cột mới cho 10 triệu đơn hàng lịch sử.

Ví dụ giả định:

```sql
UPDATE orders
SET category = 'STANDARD'
WHERE category IS NULL;
```

Nếu chạy trong một transaction lớn, hệ quả có thể gồm:

- Tạo hàng triệu phiên bản tuple mới.
- Ghi WAL cho heap và index liên quan.
- Sinh dead tuples cần VACUUM.
- Giữ transaction/locks lâu.
- Tăng WAL archive/replication volume.
- Tạo lag cho standby hoặc logical subscriber.
- Khiến autovacuum gặp khó nếu snapshot/transaction dài.
- Tạo burst I/O vượt mức tải bình thường.

### 21.1. Đánh giá trước khi chạy

Cần biết:

1. Có bao nhiêu hàng thực sự cần cập nhật?
2. Cột đổi có nằm trong index, expression, INCLUDE hoặc predicate của partial index không?
3. Có trigger, generated columns, foreign key hoặc cascade liên quan không?
4. Tuple mới có thể HOT không? Page còn chỗ không?
5. WAL/replica/archiver hiện có bao nhiêu headroom?
6. Mức write latency và read latency được chấp nhận là bao nhiêu?
7. Có thể cập nhật theo batch và theo khóa ổn định không?
8. Có backfill đi cùng deployment thay đổi schema/logic app không?
9. Có thể dừng, tiếp tục và chạy lại an toàn không?
10. Sau backfill có cần VACUUM, ANALYZE và kiểm tra index bloat không?

### 21.2. Chỉ cập nhật hàng cần đổi

Thay vì UPDATE mọi hàng:

```sql
UPDATE orders
SET category = 'STANDARD';
```

nên có điều kiện phù hợp:

```sql
UPDATE orders
SET category = 'STANDARD'
WHERE category IS DISTINCT FROM 'STANDARD';
```

Đây là mẫu ở một bảng **giả định** có cột category, không thuộc schema lab. Nó giúp tránh ghi lại những hàng đã đúng giá trị, nếu việc bỏ qua UPDATE tương thích với audit/triggers.

### 21.3. Batch theo khóa

Một pattern dùng khóa có thứ tự:

```sql
-- Mẫu minh họa trên bảng giả định.
WITH batch AS (
    SELECT order_id
    FROM orders
    WHERE category IS DISTINCT FROM 'STANDARD'
    ORDER BY order_id
    LIMIT 1000
)
UPDATE orders AS o
SET category = 'STANDARD'
FROM batch AS b
WHERE o.order_id = b.order_id;
```

Chạy từng batch qua những transaction riêng, kiểm soát rate và quan sát lag. Nếu nhiều worker chạy đồng thời, còn cần phối hợp khóa/chia phạm vi để tránh tranh chấp.

**Batch không tự giảm tổng WAL hoặc tổng công việc update**. Nó chủ yếu giúp kiểm soát **đỉnh tải, transaction duration, lock và khả năng dừng/tiếp tục**.

### 21.4. Cẩn thận với schema migration

Khi thêm cột mới, một số cách thêm default/constraint có thể tối ưu hơn các cách khác tùy phiên bản PostgreSQL. Không mặc định mọi `ALTER TABLE ADD COLUMN ... DEFAULT ...` đều buộc rewrite toàn bảng, cũng không mặc định mọi loại ALTER đều miễn phí.

Nếu chỉ cần default cho **hàng mới**, không nhất thiết phải backfill toàn bộ lịch sử lập tức. Nếu nghiệp vụ cần cột NOT NULL, lập kế hoạch xác thực dữ liệu và thời điểm enforce constraint theo phiên bản hỗ trợ.

Đánh giá thay đổi schema và backfill như **hai công việc khác nhau**, nhưng có mối liên hệ về WAL, lock và replication.

---

## 22. Bulk load ban đầu và thứ tự tạo index

Khi tạo một bảng hoàn toàn mới có hàng trăm triệu hàng và yêu cầu nạp dữ liệu ban đầu, câu hỏi thường là:

> Có nên xây index trước hay sau khi import?

Một số phương án:

### Phương án A — Index đã tồn tại

```text
Tạo bảng + index
      |
      v
COPY / INSERT bulk
      |
      v
Mỗi hàng được đưa vào heap và các index
```

Ưu điểm: index/constraint có hiệu lực trong suốt quá trình nạp. Nhược điểm: phải duy trì index trong lúc nạp, có thể tăng random I/O/WAL.

### Phương án B — Nạp vào bảng mới rồi tạo index

```text
Tạo bảng trống (các constraint cần thiết)
      |
      v
COPY / INSERT bulk vào bảng mới
      |
      v
CREATE INDEX / VALIDATE
      |
      v
ANALYZE -> Cutover
```

Tạo index sau nạp có thể hiệu quả hơn trong một số workload nhờ thuật toán xây dựng index trên dữ liệu đã có. Nhưng nó cũng có:

- Peak CPU, I/O, temp space và WAL riêng.
- Nhu cầu đảm bảo uniqueness và foreign key.
- Lock và khả năng đọc/ghi trong thời gian xây index.
- Khả năng replica phải replay lượng WAL lớn.
- Kế hoạch cutover và rollback.

Không được áp dụng máy móc với bảng production đang có writer/reader. Với hệ thống đang hoạt động, có thể phải dùng `CREATE INDEX CONCURRENTLY` theo quy trình riêng; lệnh này có đặc tính khóa/transaction và hạn chế riêng, không chạy bên trong transaction block thông thường.

### 22.1. COPY không có nghĩa luôn “không ghi WAL”

Với bảng logged thông thường, `COPY` vẫn tạo công việc WAL phù hợp. Một số tình huống nạp dữ liệu và cấu hình có thể tối ưu lượng WAL theo quy tắc PostgreSQL, nhưng không nên tuyên bố mọi COPY đều bỏ WAL hoặc bền vững tương đương trong tất cả chế độ.

---

## 23. UNLOGGED và TEMP: đánh đổi durability có chủ đích

PostgreSQL hỗ trợ:

```sql
CREATE UNLOGGED TABLE dml_impact_lab.staging_events (
    source_id BIGINT,
    payload TEXT
);
```

Dữ liệu trong unlogged table không có chế độ ghi WAL cho thay đổi hàng như bảng logged thông thường. Điều này có thể giảm WAL cho dữ liệu staging tái tạo được, nhưng:

- Dữ liệu không crash-safe như bảng logged; có thể bị truncate sau sự cố.
- Dữ liệu không được cung cấp cho physical standby như dữ liệu logged thông thường.
- Không phù hợp với nguồn dữ liệu chính cần durability/replication.
- Một số hoạt động catalog/DDL vẫn có cơ chế logging riêng; không hiểu “UNLOGGED = không WAL gì cả”.

Với dữ liệu chỉ dùng trong một session:

```sql
CREATE TEMP TABLE session_stage (
    source_id BIGINT,
    payload TEXT
) ON COMMIT DROP;
```

Temp table cũng có tính chất và phạm vi khác bảng bền vững. `ON COMMIT DROP` nghĩa là bảng sẽ bị xóa khi transaction chứa thao tác tạo nó COMMIT; không dùng ví dụ này rồi kỳ vọng bảng sống qua nhiều transaction.

**Chọn unlogged/temp vì dữ liệu có thể mất và được xây lại**, không vì muốn tăng tốc bằng mọi giá.

---

## 24. Trigger, foreign key và cascade là một phần của chi phí ghi

Một UPDATE không chỉ bị chi phối bởi heap/index của bảng trực tiếp.

Các yếu tố có thể làm công việc tăng:

- `BEFORE/AFTER INSERT/UPDATE/DELETE` triggers.
- Audit trigger ghi sang bảng lịch sử.
- Foreign key check cần tra cứu bảng liên quan.
- `ON UPDATE CASCADE` / `ON DELETE CASCADE` tác động nhiều hàng ở bảng con.
- Generated columns và expression indexes.
- Logical decoding và subscriber apply.
- Constraint check, unique conflicts và lock waits.
- Application retry do deadlock/serialization failure.

### 24.1. Một DELETE logic có thể kích hoạt nhiều DELETE khác

Giả sử bảng customers có orders với `ON DELETE CASCADE`. Xóa một khách hàng có hàng triệu order có thể gây nhiều thao tác ghi và WAL ở bảng orders và các index, không chỉ xóa một hàng customers.

Trước khi DELETE/update khóa tham chiếu:

1. Xem quan hệ FK và hành vi cascade.
2. Ước lượng số hàng bị tác động gián tiếp.
3. Quan sát transaction/locks và replica lag.
4. Kiểm tra backup/retention, audit và kế hoạch phục hồi.

Không suy ra chi phí chỉ từ `DELETE FROM customers WHERE id=...` nếu dữ liệu liên quan rất lớn.

### 24.2. Audit và CDC có giá trị nghiệp vụ

Nếu hệ thống cần lịch sử thay đổi, việc tăng WAL/audit storage có thể là chi phí **cần thiết** để đáp ứng truy xuất và tuân thủ. Đừng loại bỏ cơ chế audit hoặc CDC mà không biết chức năng nghiệp vụ đang phụ thuộc vào nó.

---

## 25. Transaction lớn, khóa và retry

Một transaction lớn thường có ít lần COMMIT hơn nhiều transaction nhỏ, nhưng có thể tạo thêm rủi ro:

| Transaction quá lớn | Transaction quá nhỏ |
| --- | --- |
| Giữ lock và snapshot lâu | Nhiều round-trip/commit |
| Tạo burst WAL lớn | Tăng overhead commit |
| Rollback tốn công việc đã làm | Nhiều điểm resume/idempotency |
| Có thể làm VACUUM khó dọn | Có thể giảm hiệu suất bulk throughput |
| Standby/logical apply có thể phải xử lý đợt lớn | WAL/traffic có thể phân tán hơn |

Không có số batch chung tối ưu. Phải đánh giá theo tài nguyên và mục tiêu:

- Throughput mục tiêu.
- Latency ứng dụng.
- WAL generation rate.
- Replication lag.
- Khả năng rollback/retry.
- Số hàng bị khóa.
- RPO/RTO và khung thời gian bảo trì.

### 25.1. Nhìn nhận COMMIT và latency

Một câu UPDATE chạy nhanh trong `EXPLAIN ANALYZE` chưa chắc tương ứng với latency đầy đủ mà ứng dụng thấy khi transaction COMMIT, đặc biệt khi còn chờ WAL flush hoặc synchronous standby.

Khi benchmark hệ thống:

- Đo thời gian statement.
- Đo thời gian COMMIT.
- Đo số transaction/giây và hàng/giây.
- Đo WAL bytes/giây.
- Đo lag primary → standby.
- Đo lock waits, CPU và I/O.

### 25.2. Retry có thể tăng gấp công việc ghi

Nếu transaction bị deadlock hoặc serialization failure rồi ứng dụng retry toàn bộ, một yêu cầu logic có thể tạo công việc nhiều hơn một lần.

Các lỗi như `40P01` (deadlock_detected) hoặc `40001` (serialization_failure) cần chính sách retry phù hợp. Retry phải có giới hạn, backoff và idempotency khi thao tác có tác dụng ngoài database.

Không tự kết luận PostgreSQL không bền vững nếu thấy WAL tăng sau một đợt nhiều retry.

---

## 26. WAL và logical replication khi cập nhật khóa nhận diện

Một thay đổi khóa chính có thể ảnh hưởng mạnh hơn việc cập nhật cột thông thường:

```sql
-- MẪU MINH HỌA, không chạy nếu không muốn đổi identity.
UPDATE dml_impact_lab.orders
SET order_id = order_id + 1000000
WHERE order_id BETWEEN 1 AND 10;
```

Hệ quả có thể gồm:

- Chạm primary key B-tree.
- Duy trì unique constraint.
- Tác động foreign key nếu có bảng tham chiếu.
- Tạo WAL heap/index.
- Trong logical replication, cần có đủ replica identity để tìm hàng cũ và áp dụng thay đổi đúng.

Với schema ứng dụng, primary key thường nên **ổn định**, không thay đổi chỉ vì muốn đổi ID hiển thị. Nếu nghiệp vụ có mã bên ngoài cần thay, cân nhắc một cột riêng và unique constraint phù hợp.

### 26.1. Đừng dùng REPLICA IDENTITY FULL nếu không cần

Với bảng có primary key, logical replication thường nhận diện UPDATE/DELETE qua khóa đó. `REPLICA IDENTITY FULL` có thể tăng lượng dữ liệu cần log/giải mã và chi phí subscriber.

Chỉ thay replica identity khi có yêu cầu kỹ thuật rõ ràng, kế hoạch kiểm thử và phân tích hệ quả.

---

## 27. Bảng quyết định: tối ưu nào có thể giúp và đánh đổi gì?

| Biện pháp | Lợi ích có thể có | Đánh đổi / điều kiện |
| --- | --- | --- |
| Bỏ index không còn cần | Giảm storage và maintenance write | Có thể làm query đọc chậm; kiểm tra constraint |
| Partial index chọn lọc | Index nhỏ, đọc tập trạng thái nhanh | UPDATE predicate có thể tốn chi phí |
| Giảm update cột indexed | Tăng cơ hội HOT | Có thể cần đổi schema hoặc caching |
| Fillfactor phù hợp | Dành chỗ cho HOT | Bảng dùng nhiều trang hơn |
| Tránh UPDATE không đổi giá trị | Ít tuple/WAL | Thay đổi semantics trigger/audit |
| INSERT nhiều hàng | Giảm overhead round-trip | Cần quản lý lỗi/batch |
| COPY cho initial load | Bulk throughput tốt | Nguồn dữ liệu/quyền/constraint phải rõ |
| Build index sau initial load | Giảm chi phí index maintenance khi nạp | Peak index build, lock, WAL |
| Xóa/cập nhật theo batch | Kiểm soát transaction duration và đỉnh tải | Tổng việc không chắc giảm |
| Tune autovacuum | Kiểm soát dead tuples/bloat | Dùng tài nguyên nền; cần số liệu |
| wal_compression | Giảm WAL FPI trong một số workload | Tăng CPU, không nén mọi WAL record |
| Điều chỉnh checkpoint | Cân bằng FPI, recovery và write I/O | Cần đánh giá RTO và storage |
| UNLOGGED staging | Giảm WAL data cho dữ liệu có thể tái tạo | Mất dữ liệu sau crash, không replicated như logged table |
| Synchronous replication | Tăng bảo đảm remote theo mode | Tăng commit latency / ảnh hưởng availability |
| Async replication | Giảm chờ remote lúc commit | Replica có thể stale và mất dữ liệu chưa replicate khi failover |
| Replication slots | Giúp consumer giữ vị trí WAL | Nguy cơ giữ WAL và đầy đĩa |
| Chia workload theo giờ | Giảm cạnh tranh tải cao điểm | Kéo dài thời gian hoàn tất, phức tạp điều phối |

**Không chọn chỉ theo throughput.** Cần xét khả năng phục hồi, tính nhất quán, yêu cầu đọc, RPO/RTO và chi phí vận hành.

---

## 28. Tình huống thực tế 1: cập nhật trạng thái hàng loạt

Một dịch vụ xử lý 500.000 đơn `NEW → PAID` mỗi ngày.

Trong lab, index một phần `WHERE status='PAID'` có thể hỗ trợ truy vấn đọc danh sách PAID nhưng làm mỗi chuyển trạng thái tạo công việc index.

Cần đánh giá:

1. Tỷ lệ query đọc lọc `status='PAID'`.
2. Có thực sự cần partial index này hay một index khác đã đáp ứng?
3. Bao nhiêu hàng thay đổi trạng thái mỗi giây?
4. WAL bytes/statement và WAL bytes/s tăng bao nhiêu?
5. Các replica có replay theo kịp không?
6. Có spike tại cuối mỗi chu kỳ đối soát không?
7. Có xung đột khóa với quy trình thanh toán/đối soát không?
8. Audit trigger có ghi thêm không?

Việc chuyển status là **nghiệp vụ cốt lõi**, không nên bỏ cập nhật hoặc bỏ index một cách tùy tiện. Tối ưu hợp lý có thể là giảm UPDATE thừa, xác thực truy vấn đọc, sắp batch theo mục tiêu tải hoặc chọn cấu trúc index tốt hơn.

---

## 29. Tình huống thực tế 2: ghi chú thay đổi liên tục

Một bảng có vài triệu hàng, ứng dụng sửa `note` thường xuyên nhưng tra cứu theo `order_id` và `customer_id`.

Đây là workload có thể tận dụng HOT nếu:

- `note` không có trong index/expression/predicate/INCLUDE.
- Phiên bản mới còn nằm được trong heap page.
- Fillfactor hợp lý.
- Không có trigger làm thêm nhiều công việc.

Các bước đánh giá:

```text
Quan sát HOT ratio, table/index size
          |
          v
Kiểm tra những index có phụ thuộc note không
          |
          v
Kiểm tra row size / TOAST / fillfactor
          |
          v
Đo UPDATE note với EXPLAIN BUFFERS WAL
          |
          v
Quan sát autovacuum và dead tuples
          |
          v
Đánh giá thay đổi schema/index/fillfactor trên môi trường test
```

Nếu `note` tăng từ vài chục byte lên hàng chục kilobyte, TOAST và kích thước row có thể thành vấn đề riêng. HOT không thể xóa toàn bộ chi phí ghi dữ liệu lớn.

---

## 30. Tình huống thực tế 3: replica lag sau khi CREATE INDEX

Một nhóm thêm index để tăng tốc API tìm kiếm; sau đó standby báo lag tăng, dù ứng dụng không có đợt tăng INSERT rõ rệt.

Hướng điều tra:

1. Xác định có `CREATE INDEX/REINDEX` gần thời điểm lag không.
2. Quan sát WAL rate và archiver.
3. Xem `pg_stat_replication`: sent/write/flush/replay LSN.
4. Quan sát CPU, disk và recovery apply trên standby.
5. Xác định logical hay physical replication: logical không tự replicate DDL/index theo cách physical.
6. Kiểm tra concurrent workload và checkpoint/FPI.
7. Chỉ kết luận sau khi có số liệu theo thời gian.

**Không tự “sửa” bằng việc xóa replica hoặc drop slot**. Đợt lag có thể chỉ là apply đang xử lý lượng WAL lớn; can thiệp sai có thể làm mất đường phục hồi.

---

## 31. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “UPDATE một cột là sửa tại chỗ.” | MVCC thường tạo tuple version mới |
| “DELETE trả lại disk ngay.” | Thường tạo dead tuple, cần VACUUM; file không nhất thiết co lại |
| “Không sửa indexed column nghĩa là chắc HOT.” | Còn điều kiện cùng heap page và index definitions |
| “HOT không tạo WAL.” | HOT vẫn ghi heap/WAL; chủ yếu giảm index maintenance |
| “Chỉ index key mới ảnh hưởng HOT.” | Expression, predicate, INCLUDE cũng có thể liên quan |
| “Thêm index chỉ tốt vì SELECT nhanh hơn.” | Index tăng chi phí ghi/storage và có thể làm HOT khó hơn |
| “Partial index không tốn chi phí UPDATE status.” | Thay predicate membership có thể phải sửa index |
| “Một UPDATE không đổi giá trị luôn miễn phí.” | Vẫn có thể tạo tuple/WAL |
| “WAL = câu SQL được log dạng text.” | WAL là nhật ký phục hồi các thay đổi cần thiết |
| “WAL ghi bao nhiêu bằng kích thước tuple.” | FPI, index, TOAST và nhiều yếu tố khác ảnh hưởng |
| “ROLLBACK xóa WAL phát sinh.” | Rollback logic không loại công việc WAL/I/O đã xảy ra |
| “max_wal_size là trần cứng pg_wal.” | Slots, archive và điều kiện khác có thể khiến WAL tồn lâu |
| “Tắt fsync/full_page_writes là tối ưu an toàn.” | Làm thay đổi bảo đảm dữ liệu và crash recovery |
| “wal_compression nén mọi WAL record.” | Chủ yếu giảm FPI WAL trong những điều kiện phù hợp |
| “COMMIT primary nghĩa là standby đã replay.” | Phụ thuộc synchronous_commit và replication state |
| “Đã receive WAL là query standby đọc được ngay.” | Còn write/flush/replay và snapshot |
| “Logical replication tự đồng bộ DDL/index.” | Built-in logical replication không tự replicate DDL |
| “REPLICA IDENTITY FULL luôn tốt hơn PRIMARY KEY.” | Có thể tăng logging/apply cost |
| “Slot inactive không ảnh hưởng.” | Có thể giữ WAL lâu và làm đầy ổ đĩa |
| “pg_stat_wal đo riêng bảng hiện tại.” | Là thống kê WAL toàn server |
| “idx_scan thấp chứng minh index vô dụng.” | Unique constraint và workload đặc thù vẫn có giá trị |
| “Batch luôn làm ít WAL hơn.” | Thường kiểm soát đỉnh tải/locks, không bảo đảm giảm tổng bytes |
| “VACUUM luôn thu nhỏ file vật lý.” | Chủ yếu tái sử dụng không gian, không luôn trả disk |
| “UNLOGGED giống logged nhưng nhanh hơn.” | Khác durability, crash và replication semantics |
| “EXPLAIN ANALYZE UPDATE chỉ giải thích, không chạy.” | Nó thực thi UPDATE; cần lab/transaction an toàn |
| “Một benchmark lần đầu là đủ.” | Cache, checkpoint, FPI, concurrency gây biến thiên |
| “Replica có thể thay backup.” | Xóa nhầm và lỗi logic có thể được replicate |
| “Tối ưu ghi chỉ là giảm index.” | Cần cân bằng durability, đọc, WAL, vacuum và replication |

---

## 32. Bài tập thực hành

### Bài 1 — Vẽ đường đi của INSERT

Với một đơn hàng mới `status='PAID'`, liệt kê các cấu trúc có thể bị ghi: heap, primary key, index customer_id, partial index PAID, WAL, standby. Giải thích vì sao hàng NEW không phải thành viên partial index PAID.

### Bài 2 — Chỉ sửa ghi chú

Dùng:

```sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE dml_impact_lab.orders
SET note = note || '-x'
WHERE order_id BETWEEN 200 AND 500;
ROLLBACK;
```

Quan sát WAL records/fpi/bytes và số hàng thực sự thay đổi. Tại sao vẫn có WAL dù `note` không được index?

### Bài 3 — UPDATE indexed column

Lặp lại phép đo với `customer_id = customer_id + 1000` trên cùng phạm vi trong transaction rollback. Đưa ra giả thuyết vì sao index maintenance có thể tăng. Vì sao không nên so một lần duy nhất rồi kết luận?

### Bài 4 — HOT ratio

Truy vấn `pg_stat_user_tables` để lấy `n_tup_upd`, `n_tup_hot_upd`, rồi tính `HOT ratio` bằng `NULLIF`.

Tỷ lệ này có phải đo trực tiếp một statement mới chạy trong transaction rollback không? Giải thích tính chất cumulative/delayed.

### Bài 5 — Partial index

Phân tích:

```sql
CREATE INDEX idx_orders_paid_customer
ON dml_impact_lab.orders(customer_id)
WHERE status = 'PAID';
```

Nếu status đổi NEW → PAID, những cấu trúc nào có thể cần thay đổi? Nếu UPDATE chỉ đổi note thì có thể HOT không?

### Bài 6 — Thêm index trên note

Giả sử tạo index `ON orders(note)` để tăng tốc tìm kiếm. Tại sao điều đó có thể làm HOT kém đi khi ứng dụng thường xuyên sửa note? Khi nào lợi ích đọc vẫn đáng để trả chi phí này?

### Bài 7 — Non-HOT update và index không đổi khóa

Giải thích vì sao một non-HOT UPDATE có thể tạo index entries mới ngay cả với index mà giá trị key không đổi. Vai trò của heap tuple location là gì?

### Bài 8 — DELETE và VACUUM

Xóa một batch CANCELED trong lab, quan sát `n_dead_tup`/kích thước table trước sau và chạy VACUUM theo quyền lab. Vì sao kích thước file không nhất thiết giảm ngay?

### Bài 9 — Batch DELETE

Viết một vòng xử lý ứng dụng thực thi câu DELETE theo batch 200 hàng, COMMIT từng batch, dừng khi không còn hàng. Nêu cách xử lý restart, lỗi, concurrency và nguy cơ WAL burst.

### Bài 10 — pg_stat_wal

Đọc `wal_records`, `wal_fpi`, `wal_bytes` và `stats_reset`. Vì sao chênh lệch wal_bytes giữa hai thời điểm có thể chứa hoạt động không liên quan tới lab?

### Bài 11 — EXPLAIN WAL

Chọn một UPDATE chỉ sửa note và một UPDATE đổi status. Dùng `EXPLAIN (ANALYZE, BUFFERS, WAL)` trong transaction test. Phân biệt WAL records, FPI và bytes.

### Bài 12 — Checkpoint và FPI

Vì sao một workload lặp lại trên cùng trang có thể tạo lượng FPI khác nhau tùy thời điểm checkpoint? `wal_compression` có thể giúp trường hợp nào và đánh đổi gì?

### Bài 13 — Physical vs logical replication

Lập bảng so sánh khi primary:

1. UPDATE hàng dữ liệu.
2. CREATE INDEX.
3. ALTER TABLE thêm cột.
4. Dùng UNLOGGED staging.
5. Thay replica identity.

Nêu vì sao kết quả đối với physical standby khác logical subscriber.

### Bài 14 — Replication lag

Từ `pg_stat_replication`, phân biệt `sent_lsn`, `write_lsn`, `flush_lsn` và `replay_lsn`. Nếu replay rất chậm nhưng receive nhanh, bạn sẽ điều tra đâu trước?

### Bài 15 — Replica đọc dữ liệu cũ

Một API ghi trạng thái PAID trên primary rồi đọc ngay từ async standby và thấy NEW. Có thể do lỗi SQL không? Nêu ba chiến lược để đáp ứng những mức nhất quán khác nhau.

### Bài 16 — Replication slot giữ WAL

Một logical consumer đã ngừng nhiều giờ, `pg_wal` tăng nhanh. Sử dụng `pg_replication_slots`, `pg_stat_wal` và monitoring filesystem để tìm tín hiệu. Vì sao không nên drop slot ngay lập tức?

### Bài 17 — Backfill

Một bảng có 8 triệu hàng cần điền cột mới. Viết kế hoạch đánh giá số hàng cần thay đổi, index/HOT, WAL headroom, archiver, batch size, replication lag, retry, lịch bảo trì và đối soát.

### Bài 18 — UNLOGGED staging

Những dữ liệu nào được phép lưu trong UNLOGGED staging? Đâu là hậu quả nếu máy crash hoặc hệ thống failover sang standby giữa quá trình import?

### Bài 19 — Lựa chọn index

Một index ít được đọc nhưng đang giữ ràng buộc UNIQUE. Có được xóa nó để giảm ghi không? Nếu một index khác trùng lặp, cần xem những bằng chứng nào trước khi drop?

### Bài 20 — Transaction và COMMIT latency

Một UPDATE có Execution Time 8 ms nhưng request ứng dụng mất 60 ms trước khi nhận COMMIT. Nêu các nguồn chờ có thể có (flush, synchronous standby, network, lock, application) và cách đo riêng.

### Bài 21 — Logical REPLICA IDENTITY

Nếu bảng publisher không có primary key mà publication chứa UPDATE/DELETE, cần điều tra gì? Vì sao `REPLICA IDENTITY FULL` có thể làm WAL và apply cost tăng?

### Bài 22 — Nhận diện sai lầm của benchmark

Một nhóm đo UPDATE note khi index chưa có rồi đo UPDATE status sau khi tạo thêm bốn index, sau đó kết luận status luôn chậm gấp 10 lần. Hãy chỉ ra những yếu tố chưa được kiểm soát: số hàng, trạng thái index, FPI/checkpoint, HOT, cache, transaction, trigger, WAL, writer đồng thời.

### Bài 23 — Giá trị không đổi

Viết câu UPDATE status chỉ khi giá trị khác trạng thái đích bằng `IS DISTINCT FROM`. Khi nào việc bỏ qua UPDATE có thể thay đổi sự kiện audit hoặc tác dụng phụ của trigger?

### Bài 24 — Recovery và backup

Giải thích vai trò của WAL đối với crash recovery và PITR. Vì sao WAL archive thiếu base backup hợp lệ không đủ để bảo đảm phục hồi và vì sao replica không thay thế backup?

---

## 33. Checklist đánh giá một thay đổi dữ liệu lớn

| Câu hỏi | Cách đánh giá |
| --- | --- |
| Có bao nhiêu hàng thay đổi thật? | `SELECT COUNT(*)`, WHERE, kiểm thử phạm vi |
| Câu lệnh là INSERT, UPDATE hay DELETE? | Xem phiên bản tuple, index, dead tuples |
| Cột UPDATE có trong index không? | Kiểm tra key, INCLUDE, expression, predicate |
| Có khả năng HOT không? | Same page, fillfactor, indexed dependency |
| Có trigger/FK/cascade không? | Kiểm tra ghi gián tiếp và lock |
| Có giá trị TOAST lớn không? | Xem row size, thay đổi payload |
| Có bao nhiêu index? | Index definitions, size, đọc và constraint |
| Có cần giữ tất cả index? | Phân tích workload/constraint trước khi drop |
| Có dữ liệu phải giữ bền vững? | Chọn logged table, không lạm dụng UNLOGGED |
| Đợt ghi tạo bao nhiêu WAL? | `EXPLAIN ... WAL`, WAL rate |
| Có nhiều FPI không? | `wal_fpi`, checkpoint, wal_compression |
| Có rủi ro pg_wal đầy không? | Disk headroom, slots, archiver |
| Có physical standby? | Sent/write/flush/replay LSN |
| Có logical subscriber? | Apply throughput, replica identity, schema |
| Có synchronous replication? | Commit latency và chế độ đồng bộ |
| Đọc replica có cần read-your-writes? | Route đọc/chờ replay/contract consistency |
| Transaction kéo dài bao lâu? | Locks, snapshots, VACUUM, retry |
| Có thể batch không? | Chọn số hàng/transaction và giới hạn tốc độ |
| Batch có thể chạy lại? | Idempotency, checkpoint ứng dụng, phạm vi ổn định |
| Có thể rollback an toàn? | Backup/PITR, kế hoạch vận hành |
| Có cần VACUUM/ANALYZE sau đó? | Dead tuples, statistics, autovacuum |
| Có nguy cơ index/table bloat? | Size theo thời gian, HOT, vacuum |
| Có cần xây lại index? | Chỉ khi có bằng chứng, cân nhắc lock/WAL |
| Có bị writer đồng thời tác động? | Retry, contention, isolation |
| Có xem plan thật chưa? | EXPLAIN và workload tương tự production |
| Có đo trước/sau không? | Latency, rows/s, WAL/s, lag, CPU, disk |
| Có bảo đảm durability phù hợp không? | Không tự tắt fsync/full_page_writes |
| Có theo dõi trong quá trình chạy không? | Alert WAL, lag, disk, autovacuum, error |
| Có điều kiện dừng hoặc rollback rõ không? | Ngưỡng latency/lag/disk, người chịu trách nhiệm |

## Kết luận

Đánh giá một thao tác ghi trong PostgreSQL cần nhìn xa hơn số hàng mà câu SQL báo đã tác động. Một `INSERT` tạo heap tuple và index entries; một `UPDATE` theo MVCC thường tạo phiên bản tuple mới và chỉ có thể tiết kiệm chi phí index nếu đủ điều kiện **HOT**; một `DELETE` không lập tức thu hồi toàn bộ không gian mà thường để lại công việc cho **VACUUM**.

Ở lớp độ bền, **WAL** ghi những thay đổi cần thiết cho crash recovery và hỗ trợ backup/replication. Lượng WAL không chỉ bằng kích thước dữ liệu mới vì còn có index changes, full-page images, checkpoint, TOAST và các tác động gián tiếp khác. Tăng tốc ghi bằng cách tùy tiện tắt các cơ chế durability có thể làm sai yêu cầu hệ thống.

Ở lớp sao chép, **physical replication** replay những thay đổi WAL vật lý, trong khi **logical replication** decode/apply các thay đổi dữ liệu theo publication và cần quản lý schema, replica identity, subscriber indexes riêng. Ghi thành công trên primary không tự bảo đảm một async standby đã replay xong; replication slots và WAL archiving còn có thể khiến `pg_wal` tăng nếu consumer/archive bị chậm.

Quy trình thực hành đáng tin cậy là:

1. Xác định thay đổi logic và số hàng bị ảnh hưởng.
2. Xem MVCC, HOT, index definitions, trigger và FK.
3. Đo `EXPLAIN (ANALYZE, BUFFERS, WAL)` trong môi trường an toàn.
4. Quan sát WAL rate, dead tuples, table/index size, autovacuum và replica lag.
5. Đưa ra đánh đổi giữa tốc độ ghi, tốc độ đọc, durability, phục hồi và tính nhất quán.
6. Kiểm soát batch, monitoring, điều kiện dừng và khả năng chạy lại.

Khi nắm được mối quan hệ giữa **heap/MVCC**, **chỉ mục**, **WAL** và **replication**, bạn sẽ có cơ sở để giải thích vì sao một đợt ghi nhỏ có thể gây I/O lớn, vì sao một index tốt cho SELECT lại gây chi phí UPDATE, và vì sao một chiến dịch backfill phải được thiết kế như một quy trình vận hành có thể đo lường và kiểm soát chứ không chỉ là một câu SQL chạy cho xong.
