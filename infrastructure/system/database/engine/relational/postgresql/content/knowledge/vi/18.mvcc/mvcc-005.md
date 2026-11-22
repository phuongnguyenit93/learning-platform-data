# UPDATE, DELETE, phiên bản hàng cũ và hàng chết trong PostgreSQL

Một trong những đặc điểm quan trọng nhất của PostgreSQL là **MVCC — Multi-Version Concurrency Control**, tức cơ chế điều khiển đồng thời bằng nhiều phiên bản dữ liệu.

Khi ứng dụng thực hiện:

```sql
UPDATE orders
SET status = 'PAID'
WHERE order_id = 1001;
```

PostgreSQL không đơn giản ghi đè giá trị `status` vào vị trí của hàng cũ theo cách khiến mọi giao dịch lập tức nhìn cùng một phiên bản mới. Thay vào đó, với bảng heap thông thường, PostgreSQL tạo **phiên bản hàng mới** và đánh dấu phiên bản trước đã bị thay thế. Một giao dịch đang đọc theo snapshot cũ vẫn có thể cần thấy phiên bản trước, còn giao dịch bắt đầu sau khi UPDATE được commit sẽ thấy phiên bản mới.

Tương tự:

```sql
DELETE FROM orders WHERE order_id = 1001;
```

không nhất thiết làm byte dữ liệu của hàng biến mất khỏi tệp ngay lập tức. PostgreSQL đánh dấu rằng phiên bản hàng đã bị xóa về mặt logic, sau đó cơ chế **pruning** và **VACUUM** thu hồi không gian khi không còn giao dịch nào cần phiên bản cũ.

Điều này giải thích những hiện tượng thường gặp:

- UPDATE nhiều lần khiến bảng hoặc index lớn lên dù số hàng nghiệp vụ gần như không đổi.
- DELETE hàng triệu bản ghi không lập tức làm dung lượng file giảm.
- Một câu SELECT trong transaction cũ vẫn thấy dữ liệu mà transaction khác vừa UPDATE hoặc DELETE.
- VACUUM chạy nhưng chưa thể dọn hết dead tuples vì có snapshot cũ còn hoạt động.
- UPDATE cột không nằm trong index đôi khi nhanh hơn UPDATE cột được đánh index nhờ **HOT update**.
- Chỉ số `n_dead_tup` có thể tăng sau nhiều lần ghi, nhưng không phải con số chính xác tại mọi thời điểm.
- Chạy VACUUM đúng cách giúp tái sử dụng không gian, không đồng nghĩa tự thu nhỏ mọi file.

Bài học tập trung giải thích **UPDATE, DELETE, các phiên bản hàng cũ và hàng chết**, trong ngữ cảnh MVCC của PostgreSQL: từ nguyên lý snapshot, tuple metadata, HOT/non-HOT update đến việc dọn rác, theo dõi, điều tra bloat và thực hành an toàn.

## 1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Diễn giải vì sao PostgreSQL duy trì nhiều phiên bản của một hàng khi có UPDATE.
2. Phân biệt **hàng hiện tại**, **phiên bản hàng cũ**, **phiên bản không còn nhìn thấy** và **dead tuple có thể dọn**, thay vì gọi tất cả là “hàng đã xóa”.
3. Giải thích cách DELETE đánh dấu một phiên bản hàng và vì sao SELECT của transaction khác có thể vẫn nhìn thấy hàng đó.
4. Sử dụng mô hình snapshot để dự đoán kết quả trong `READ COMMITTED` và `REPEATABLE READ`.
5. Hiểu vai trò khái quát của các system columns `xmin`, `xmax` và `ctid`, cũng như các giới hạn khi đọc chúng.
6. Phân biệt HOT với non-HOT UPDATE và xem vì sao indexed columns, fillfactor và chỗ trống trên heap page quan trọng.
7. Giải thích vì sao UPDATE/DELETE kéo theo dead tuples, index maintenance, WAL và VACUUM.
8. Hiểu **heap page pruning**, **VACUUM**, **autovacuum**, **VACUUM FULL** và khác biệt giữa tái sử dụng không gian với trả dung lượng cho hệ điều hành.
9. Nhận diện long-running transactions, replication slots và standby feedback có thể giữ lại các phiên bản cũ.
10. Quan sát `pg_stat_user_tables`, kích thước relation, `EXPLAIN (ANALYZE, BUFFERS, WAL)` và các chỉ số liên quan.
11. Phân tích những tình huống UPDATE lặp, DELETE hàng loạt, bảng bloat và transaction ID wraparound.
12. Viết truy vấn, mô phỏng hai session, kiểm tra kết quả và đề xuất giải pháp theo đúng yêu cầu nghiệp vụ.

> **Phạm vi:** Các ví dụ áp dụng cho bảng heap thông thường trong PostgreSQL hiện đại. Một số chi tiết nội bộ, tên trường thống kê và khả năng tối ưu có thể thay đổi giữa phiên bản. Các câu lệnh thay đổi dữ liệu chỉ chạy trên **database thực hành được phép reset**.

---

## 2. Tại sao cần nhiều phiên bản hàng?

Giả sử hệ thống có một hàng:

```text
order_id=101 | status=NEW | amount=100
```

Hai phiên làm việc chạy đồng thời:

```text
Thời điểm   Session A (đọc)              Session B (ghi)
----------------------------------------------------------------
T1          Bắt đầu transaction
T2          Đọc order 101 = NEW
T3                                       UPDATE status='PAID'
T4                                       COMMIT
T5          Đọc lại order 101
T6          COMMIT
```

Câu hỏi: ở T5, Session A thấy `NEW` hay `PAID`?

**Câu trả lời phụ thuộc isolation level và snapshot**:

- Với `READ COMMITTED` thông thường, mỗi statement nhận snapshot phù hợp ở đầu statement. Lần SELECT mới sau COMMIT của B có thể thấy `PAID`.
- Với `REPEATABLE READ`, A giữ snapshot cho transaction sau khi snapshot đó được thiết lập, nên lần SELECT sau vẫn thấy `NEW`, dù B đã commit.

Để hỗ trợ hai hành vi này mà không buộc mọi SELECT chờ UPDATE, PostgreSQL cần quản lý thông tin về **phiên bản dữ liệu**.

### 2.1. Mô hình khái niệm

```text
Trước UPDATE:
    Tuple V1: (id=101, status=NEW)

Session B UPDATE:
    Tuple V1: (id=101, status=NEW)   <- phiên bản cũ
          |
          +----> Tuple V2: (id=101, status=PAID) <- phiên bản mới

Session A với snapshot cũ:
    thấy V1

Session khác với snapshot sau COMMIT:
    thấy V2

Khi không snapshot nào còn cần V1:
    V1 có thể được thu hồi/tái sử dụng theo cơ chế PostgreSQL
```

Đây là mô hình logic, không phải lời hứa rằng V1 và V2 luôn nằm cùng một trang vật lý. Chúng có thể ở cùng heap page hoặc ở các page khác nhau tùy điều kiện.

### 2.2. Khác biệt giữa giá trị logic và tuple vật lý

Một **hàng nghiệp vụ** có khóa `order_id=101` có thể trải qua nhiều **tuple versions**:

```text
V1 NEW
   |
   v
V2 PAID
   |
   v
V3 PAID, note='confirmed'
   |
   v
V4 CANCELED
```

Ứng dụng thường chỉ cần biết **phiên bản hiện hành** theo snapshot của nó; PostgreSQL phải quản lý những phiên bản còn cần cho transaction khác.

Chính vì vậy, “một hàng được UPDATE 1.000 lần” không tương đương với “chỉ một lần ghi lên cùng byte trên đĩa”.

---

## 3. Thuật ngữ cần phân biệt

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Logical row** | Bản ghi theo quan điểm nghiệp vụ, ví dụ đơn hàng #101 |
| **Heap tuple** | Một phiên bản hàng được lưu trong cấu trúc heap của bảng |
| **Tuple version** | Phiên bản của hàng sau INSERT/UPDATE |
| **Snapshot** | Thông tin xác định transaction/tuple nào được một câu đọc nhìn thấy |
| **Visible tuple** | Phiên bản đáp ứng quy tắc visibility đối với snapshot cụ thể |
| **Old tuple version** | Phiên bản cũ sau UPDATE hoặc DELETE; có thể vẫn cần cho snapshot khác |
| **Dead tuple** | Tuple không còn cần cho snapshot đủ điều kiện và có thể được dọn/tái sử dụng theo quy tắc hệ thống |
| **Pruning** | Dọn/thu gọn chain tuple trên heap page khi an toàn |
| **VACUUM** | Bảo trì thu hồi không gian tái sử dụng và hỗ trợ quản lý transaction age |
| **Autovacuum** | Cơ chế tự động kích hoạt VACUUM/ANALYZE theo các điều kiện và ngưỡng |
| **HOT update** | UPDATE tối ưu có thể tránh thêm index tuples mới nếu đáp ứng điều kiện |
| **Bloat** | Tình trạng bảng/index sử dụng nhiều không gian hơn mức cần thiết đối với dữ liệu hữu ích hiện tại |
| **Freeze** | Xử lý metadata transaction của phiên bản cũ để tránh rủi ro XID wraparound |
| **WAL** | Nhật ký ghi trước để phục hồi và sao chép những thay đổi được log |

**Lưu ý quan trọng:** “Phiên bản cũ” **không đồng nghĩa** “đã được phép xóa ngay”. Một tuple có thể không còn hiển thị với các snapshot mới nhưng vẫn cần cho một transaction dài đang giữ snapshot cũ.

### 3.1. Bốn trạng thái khái niệm

```text
INSERT/UPDATE tạo phiên bản mới
           |
           v
Phiên bản đã COMMIT và có thể visible cho một số snapshot
           |
           v
UPDATE/DELETE mới làm phiên bản trở nên cũ
           |
           v
Còn snapshot cần phiên bản cũ?
    |                      |
   Có                     Không
    |                      |
    v                      v
Giữ lại                  Có thể cleanup/prune/VACUUM
    |
    +----> Khi snapshot kết thúc, xét lại khả năng cleanup
```

Trên thực tế, visibility còn phụ thuộc trạng thái commit/abort, tuple metadata, lock và các chi tiết MVCC khác. Sơ đồ này để học ý nghĩa, không mô tả đầy đủ state machine của heap tuple.

---

## 4. Thí nghiệm chuẩn bị: tạo bảng MVCC riêng

Hãy tạo một bảng có đủ khóa chính, cột được index và cột không được index, để quan sát UPDATE theo hai kiểu.

> **Cảnh báo:** `DROP TABLE IF EXISTS` xóa dữ liệu cũ trong bảng thực hành tương ứng. Chỉ chạy các câu này trên database thử nghiệm hoặc schema được phép reset. Không chạy ở production.

### 4.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS mvcc_versions_lab;

DROP TABLE IF EXISTS mvcc_versions_lab.orders;

CREATE TABLE mvcc_versions_lab.orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELED')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    note TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
) WITH (fillfactor = 80);
```

Các ý chính:

- `order_id` là PRIMARY KEY và có unique index.
- `customer_id` sẽ được index để minh họa cập nhật indexed column.
- `note` không nằm trong index, nên có cơ hội HOT UPDATE.
- `status` sẽ tham gia predicate của một partial index.
- `fillfactor = 80` cho PostgreSQL cơ hội để dành không gian trong page, hỗ trợ update in-page khi điều kiện phù hợp. Không bảo đảm mọi UPDATE thành HOT.

### 4.2. Thêm dữ liệu

```sql
INSERT INTO mvcc_versions_lab.orders (
    order_id, customer_id, status, amount, note
)
VALUES
    (101, 1, 'NEW',      100.00, 'created'),
    (102, 1, 'NEW',       80.00, 'created'),
    (103, 2, 'PAID',     150.00, 'paid'),
    (104, 2, 'CANCELED',  50.00, 'cancelled'),
    (105, 3, 'NEW',      200.00, 'created'),
    (106, 4, 'NEW',       25.00, 'created');

CREATE INDEX idx_mvcc_orders_customer
ON mvcc_versions_lab.orders(customer_id);

CREATE INDEX idx_mvcc_orders_paid
ON mvcc_versions_lab.orders(order_id)
WHERE status = 'PAID';

ANALYZE mvcc_versions_lab.orders;
```

### 4.3. Kiểm tra dữ liệu

```sql
SELECT
    order_id, customer_id, status, amount, note
FROM mvcc_versions_lab.orders
ORDER BY order_id;
```

Sáu đơn ban đầu:

| order_id | customer_id | status | amount | note |
| ---: | ---: | --- | ---: | --- |
| 101 | 1 | NEW | 100 | created |
| 102 | 1 | NEW | 80 | created |
| 103 | 2 | PAID | 150 | paid |
| 104 | 2 | CANCELED | 50 | cancelled |
| 105 | 3 | NEW | 200 | created |
| 106 | 4 | NEW | 25 | created |

Bài lab cho phép bạn reset lại bảng bằng các lệnh của mục này trước khi chuyển sang thí nghiệm khác. Tránh chạy liên tiếp mọi UPDATE/DELETE mà vẫn mong đầu ra bằng dữ liệu gốc.

---

## 5. System columns: xmin, xmax và ctid

PostgreSQL cung cấp một số **system columns** trên heap table, giúp quan sát dấu vết ở mức tuple:

- `xmin`: transaction ID liên quan việc tạo phiên bản tuple.
- `xmax`: metadata liên quan việc xóa/thay thế hoặc **khóa** tuple; không được đọc đơn giản như “transaction đã DELETE”.
- `ctid`: vị trí vật lý của phiên bản tuple trong heap (block, offset).

Thử:

```sql
SELECT
    order_id,
    status,
    xmin::TEXT AS xmin_text,
    xmax::TEXT AS xmax_text,
    ctid::TEXT AS tuple_location
FROM mvcc_versions_lab.orders
ORDER BY order_id;
```

Các giá trị `xmin`, `xmax` và `ctid` trong kết quả **phụ thuộc hoàn toàn vào phiên chạy, lịch sử transaction, VACUUM và cách PostgreSQL đặt tuple**. Không có một bộ số cố định để mọi máy phải giống nhau.

### 5.1. xmin nói lên điều gì?

Một tuple version được tạo bởi một transaction nhất định. `xmin` thường cho biết transaction ID tạo ra phiên bản đang được đọc.

Ví dụ ý tưởng:

```text
V1: xmin=500
UPDATE bởi transaction 501
V2: xmin=501
```

Không suy ra thứ tự thời gian nghiệp vụ hoặc thời điểm COMMIT tuyệt đối chỉ bằng việc so hai số `xmin`. Transaction ID có cơ chế cấp phát, wraparound và có thể được xử lý/freeze theo tuổi.

### 5.2. Vì sao xmax không chỉ là dấu DELETE?

Một giải thích phổ biến nhưng thiếu chính xác là “`xmax=0` nghĩa là hàng chưa bị xóa, `xmax!=0` nghĩa là hàng đã bị xóa”.

Thực tế, `xmax` còn được dùng trong cơ chế **row locking**, có thể mang thông tin của transaction chưa commit hoặc MultiXact, và tính visibility còn phụ thuộc trạng thái transaction/các cờ nội bộ.

Vì vậy:

- Không dùng `xmax <> 0` để kết luận một hàng **đã bị DELETE thành công**.
- Không viết logic nghiệp vụ dùng `xmin/xmax` thay các cột trạng thái, audit hoặc timestamp do ứng dụng quản lý.
- Không dùng `xmax` như API xác nhận kết quả `INSERT ... ON CONFLICT` nếu không hiểu rõ tính chất nội bộ và độ ổn định giữa phiên bản.

### 5.3. ctid không phải khóa bền vững

`ctid` đại diện cho vị trí một phiên bản tuple trong heap. Sau UPDATE, phiên bản mới có thể nằm tại vị trí khác; `VACUUM FULL` hoặc những thao tác rewrite bảng cũng có thể làm thay đổi vị trí.

Vì vậy:

- `ctid` có ích khi **nghiên cứu vị trí vật lý** hoặc kỹ thuật nội bộ trong phạm vi cẩn trọng.
- `ctid` **không phải primary key** và không được dùng làm ID lưu lâu dài trong ứng dụng.
- Không giả định `ctid` lớn dần hoặc luôn nằm cùng block khi UPDATE.

### 5.4. Một snapshot không hiển thị mọi phiên bản

Câu SELECT thông thường chỉ trả những tuple **visible với snapshot**; bạn không thể mong query `SELECT xmin,xmax,ctid` tự liệt kê toàn bộ các phiên bản cũ chưa bị dọn trong page.

Muốn khám phá các trạng thái vật lý sâu hơn có thể cần extension và công cụ riêng, chẳng hạn `pageinspect`, nhưng chỉ nên dùng trong lab có quyền phù hợp. Đọc raw page và suy luận các cờ trạng thái vượt phạm vi của query SQL thông thường.

---

## 6. UPDATE tạo phiên bản hàng mới như thế nào?

Ở trạng thái gốc:

```sql
SELECT
    order_id, status, amount, note,
    xmin::TEXT AS xmin_text,
    ctid::TEXT AS ctid_text
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

Sau đó trong một transaction có kiểm soát:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET status = 'PAID',
    updated_at = clock_timestamp()
WHERE order_id = 101
RETURNING
    order_id, status, amount, note,
    xmin::TEXT AS new_xmin,
    ctid::TEXT AS new_ctid;

COMMIT;
```

Phiên bản mới có `status='PAID'`. Nếu tra cứu lại:

```sql
SELECT
    order_id, status,
    xmin::TEXT AS xmin_text,
    ctid::TEXT AS ctid_text
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

bạn đang đọc phiên bản được snapshot hiện tại xem là hợp lệ.

### 6.1. Điều gì xảy ra với phiên bản NEW cũ?

Từ góc nhìn logic:

```text
V1: (id=101, status=NEW)
     xmin=T_insert
     bị UPDATE bởi T_update
         |
         v
V2: (id=101, status=PAID)
     xmin=T_update
```

Khi `T_update` commit:

- Snapshot đủ mới thường thấy V2 và không thấy V1.
- Snapshot cũ có thể còn thấy V1.
- Khi không ai cần V1, không gian của phiên bản này có thể được PostgreSQL thu hồi/tái sử dụng.

### 6.2. UPDATE có thể ghi nhiều thứ hơn hàng mới

Ngoài phiên bản heap mới, có thể có:

- Thông tin cần thiết trong WAL.
- Hoạt động bảo trì index.
- Các trigger/ràng buộc.
- Dead tuples và công việc dọn dẹp sau này.
- Dirty buffers cần được viết về data files.
- Replay trên physical standby hoặc apply trên logical subscriber nếu cấu hình tương ứng.

Trong lab, đổi `status` có thể tác động partial index `WHERE status='PAID'`. Điều đó là một trong các lý do tại sao UPDATE này có thể đắt hơn UPDATE chỉ sửa cột `note`.

### 6.3. UPDATE nhiều hàng cũng không tạo “một phiên bản cũ chung”

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET amount = amount + 10
WHERE customer_id = 1
RETURNING order_id, amount;

ROLLBACK;
```

Hai hàng `101` và `102` có thể bị chọn (nếu dữ liệu gốc chưa đổi khách hàng), mỗi hàng có phiên bản mới riêng trong transaction. `ROLLBACK` làm thay đổi không được commit, nhưng không có nghĩa không tạo công việc heap/WAL trong quá trình thực thi.

---

## 7. Transaction rollback: phiên bản được tạo không trở thành dữ liệu hợp lệ

Một UPDATE có thể thất bại hoặc transaction có thể rollback:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET note = 'temporary note'
WHERE order_id = 102;

SELECT order_id, note
FROM mvcc_versions_lab.orders
WHERE order_id = 102;

ROLLBACK;

SELECT order_id, note
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
```

Trong transaction, chính nó có thể nhìn thấy `temporary note` do nó vừa ghi. Sau rollback, những giao dịch mới nhìn thấy phiên bản trước khi UPDATE đó.

Tuy nhiên, tuple được tạo trong transaction bị abort vẫn có thể để lại dấu vết cần dọn trong heap. Hệ thống phải phân biệt **tuple của transaction đã commit** với **tuple của transaction đã abort** bằng metadata và trạng thái transaction.

**ROLLBACK phục hồi kết quả logic; nó không nhất thiết hoàn nguyên vật lý từng byte tức thời.** Điều này cũng là lý do benchmark UPDATE bên trong transaction rồi rollback vẫn có thể sinh WAL, dirty buffers và công việc cleanup.

---

## 8. Hai session: READ COMMITTED thấy gì sau UPDATE?

Đây là bài lab quan trọng nhất để hiểu snapshot.

Dùng **hai kết nối PostgreSQL độc lập**, ví dụ hai cửa sổ `psql` hoặc hai tab SQL editor có session riêng. Các lệnh được thực hiện theo thứ tự dưới đây. Để kết quả giống mô tả, trước tiên reset bảng và nạp lại dữ liệu gốc ở mục 4.

### 8.1. Session A: mở READ COMMITTED

```sql
-- SESSION A
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

Ban đầu thấy `NEW`.

### 8.2. Session B: cập nhật và commit

```sql
-- SESSION B (kết nối khác)
BEGIN;

UPDATE mvcc_versions_lab.orders
SET status = 'PAID'
WHERE order_id = 101;

COMMIT;
```

Nếu A chỉ SELECT bình thường, nó không nhất thiết chặn B; B có thể commit UPDATE.

### 8.3. Session A: đọc lại sau commit của B

```sql
-- SESSION A (vẫn cùng transaction)
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;

COMMIT;
```

Trong `READ COMMITTED`, statement thứ hai của A nhận snapshot mới theo quy tắc mức cô lập, nên nó có thể thấy `PAID` đã được B commit.

### 8.4. Tại sao A không phải “đọc dữ liệu bẩn”?

A không đọc UPDATE chưa commit của B. Nó chỉ thấy `PAID` **sau khi B COMMIT**, ở một statement được phép dùng snapshot mới.

PostgreSQL không cho phép dirty reads theo ý nghĩa thông thường kể cả khi ứng dụng yêu cầu isolation level `READ UNCOMMITTED`; mức đó được xử lý với hành vi tương tự `READ COMMITTED`.

### 8.5. Snapshot ở đầu statement, không phải đầu dòng

Một câu `SELECT` dài nhận một cách nhìn dữ liệu nhất quán theo snapshot áp dụng cho statement đó. Không nên tưởng mỗi hàng trong kết quả của cùng SELECT tự “chuyển” sang một trạng thái mới ngay khi transaction khác commit.

Những quy tắc cụ thể về lock/recheck trong UPDATE/DELETE ở `READ COMMITTED` có thêm chi tiết, nên cách diễn đạt này chủ yếu để hiểu hành vi SELECT bình thường.

---

## 9. Hai session: REPEATABLE READ vẫn thấy phiên bản cũ

Reset dữ liệu gốc trước ví dụ này, hoặc chọn một hàng còn `NEW` để thử.

### 9.1. Session A: bắt đầu transaction và lấy snapshot

```sql
-- SESSION A
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

Ở lần đọc này, A thấy `NEW`.

### 9.2. Session B: UPDATE và COMMIT

```sql
-- SESSION B
BEGIN;

UPDATE mvcc_versions_lab.orders
SET status = 'PAID'
WHERE order_id = 101;

COMMIT;
```

### 9.3. Session A: đọc lại

```sql
-- SESSION A
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

A **vẫn thấy NEW** theo snapshot của transaction REPEATABLE READ, dù B đã commit.

Sau đó:

```sql
-- SESSION A
COMMIT;

-- Statement/transaction mới:
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 101;
```

Lúc này, với snapshot mới, A có thể thấy `PAID`.

### 9.4. Điểm cần phân biệt: đọc và cập nhật

Nếu A không chỉ SELECT mà **cố UPDATE cùng hàng đã bị B thay đổi sau snapshot**, ở PostgreSQL `REPEATABLE READ` có thể nhận lỗi đồng thời kiểu:

```text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
```

Tình huống có thể cần rollback và retry toàn bộ transaction. Đừng tự suy ra vì A đọc được phiên bản cũ nên nó được phép ghi đè lên phiên bản mới mà không có kiểm tra concurrency.

### 9.5. Các phiên bản cũ được giữ tới lúc nào?

Trong lab này, khi A giữ snapshot trước UPDATE của B, PostgreSQL có thể phải giữ phiên bản OLD để A còn đọc thấy nó.

Khi A kết thúc transaction, phiên bản cũ có thể không còn cần bởi A; nhưng khả năng dọn còn phụ thuộc **những transaction/snapshot khác** và các yếu tố quản lý visibility.

Một giao dịch dài vì vậy có thể khiến dead tuples tồn tại lâu, dù những giao dịch mới không còn thấy các hàng cũ.

---

## 10. DELETE trong MVCC: xóa logic trước, dọn vật lý sau

Đầu tiên, khi câu `DELETE` chạy:

```sql
BEGIN;

DELETE FROM mvcc_versions_lab.orders
WHERE order_id = 102
RETURNING order_id, status, amount;

COMMIT;
```

Trong snapshot mới sau COMMIT:

```sql
SELECT *
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
```

không còn hàng.

Tuy nhiên, điều này không có nghĩa trang heap đã ngay lập tức bỏ mọi dấu vết của tuple 102.

### 10.1. Trạng thái trước và sau DELETE

```text
Trước DELETE:
    V1 (id=102) -> visible đối với snapshot phù hợp

DELETE trong transaction B:
    V1 được ghi metadata bị xóa bởi B

B chưa COMMIT:
    Những session khác thường vẫn thấy V1 theo snapshot
    B thấy hàng đã bị xóa theo thay đổi của chính mình

B COMMIT:
    Snapshot mới không thấy V1
    Snapshot cũ còn có thể thấy V1

Khi không snapshot nào còn cần V1:
    VACUUM/pruning có thể thu hồi không gian
```

Không xuất hiện “V2 hàng đã xóa” giống cách UPDATE tạo phiên bản mới mang giá trị mới. DELETE đánh dấu phiên bản hiện có bị xóa về mặt logic theo metadata MVCC.

### 10.2. DELETE đang mở transaction có bị nhìn thấy ngay không?

Nếu B đã chạy DELETE nhưng **chưa COMMIT**, A với SELECT bình thường ở transaction khác vẫn có thể thấy hàng theo snapshot phù hợp.

Đây là nền tảng tránh dirty read. Nhưng nếu A muốn UPDATE/DELETE/SELECT FOR UPDATE cùng hàng, cơ chế **row-level locks** có thể khiến A phải chờ; MVCC không có nghĩa mọi loại truy cập đều không bị khóa.

### 10.3. ROLLBACK DELETE

```sql
BEGIN;

DELETE FROM mvcc_versions_lab.orders
WHERE order_id = 103;

ROLLBACK;
```

Sau rollback, hàng 103 vẫn hợp lệ theo trạng thái trước transaction, vì DELETE không được commit.

**Không gọi đây là “VACUUM khôi phục hàng”.** VACUUM không phục hồi các DELETE đã commit; rollback mới là cơ chế hủy kết quả của transaction chưa commit.

---

## 11. Cùng lúc DELETE và snapshot cũ

Đây là bản minh họa song song cho DELETE; reset dữ liệu ban đầu trước khi chạy.

### Session A

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
-- Thấy hàng 102.
```

### Session B

```sql
BEGIN;

DELETE FROM mvcc_versions_lab.orders
WHERE order_id = 102;

COMMIT;
```

### Session A, vẫn cùng transaction

```sql
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
-- Vẫn có thể thấy phiên bản cũ của hàng 102.

COMMIT;
```

Sau khi A COMMIT:

```sql
SELECT order_id, status
FROM mvcc_versions_lab.orders
WHERE order_id = 102;
-- Snapshot mới không thấy hàng 102.
```

Sự tồn tại của phiên bản cũ là để bảo vệ **tính nhất quán khi đọc**, không phải lỗi DELETE bị “kẹt”.

### 11.1. Vì sao không nên chạy VACUUM để cố xóa hàng khỏi snapshot A?

VACUUM phải tôn trọng các phiên bản còn cần bởi snapshot hợp lệ. Nếu A đang giữ snapshot cũ, một VACUUM thông thường **không được phép dọn mất dữ liệu mà A vẫn cần**.

Nếu người vận hành thấy dead tuples chưa giảm, cần kiểm tra transaction/snapshot cũ thay vì liên tục chạy VACUUM FULL hoặc kết luận VACUUM đã hỏng.

---

## 12. “Hàng chết” chính xác là gì?

Từ “dead tuple” thường được dùng lỏng để chỉ mọi phiên bản cũ do UPDATE/DELETE. Trong phân tích kỹ thuật, nên phân biệt:

1. **Phiên bản không còn là phiên bản hiện hành**: sau UPDATE, V1 đã được thay thế bằng V2.
2. **Phiên bản còn cần cho một snapshot**: dù cũ, V1 chưa thể thu hồi.
3. **Phiên bản không còn cần cho các snapshot liên quan**: đủ điều kiện được dọn theo cơ chế PostgreSQL.
4. **Không gian đã được dọn/tái sử dụng**: page có thể chứa chỗ trống sẵn cho INSERT/UPDATE tiếp theo.

Dòng đời giản lược:

```text
V1 được INSERT và COMMIT
     |
     +--> UPDATE/DELETE mới
                 |
                 v
         V1 trở thành old version
                 |
                 v
          Còn snapshot cần V1?
            |             |
           Có            Không
            |             |
            v             v
          Giữ         Eligible for cleanup
                           |
                           v
                 Page pruning / VACUUM
                           |
                           v
                Không gian được tái sử dụng
```

**Không phải mọi old tuple đều có thể được dọn ngay; cũng không phải mọi dead tuple được đếm trong thống kê đã được dọn vật lý.**

### 12.1. Dead tuple ước lượng không phải số hàng DELETE

Một UPDATE có thể tạo một phiên bản cũ; một DELETE đã commit có thể tạo một phiên bản không còn cần trong tương lai. Nhưng:

- Có các transaction rollback.
- Page pruning có thể đã dọn một số phiên bản.
- HOT chains có thể chứa nhiều phiên bản.
- VACUUM đã chạy và tái sử dụng không gian.
- Thống kê là giá trị tích lũy hoặc ước lượng, có độ trễ.

Vì vậy không được lấy `n_dead_tup` rồi tuyên bố đó chính là `COUNT(*)` số lần DELETE hoặc số phiên bản heap đã tồn tại vật lý tuyệt đối.

---

## 13. HOT UPDATE: giảm chi phí index nhưng vẫn tạo tuple version

**HOT — Heap-Only Tuple** là một tối ưu quan trọng của PostgreSQL.

Khi một UPDATE đáp ứng điều kiện, phiên bản mới có thể nằm **trên cùng heap page** và không cần tạo index entries mới cho các index thông thường.

Điều kiện phổ biến:

- UPDATE không thay đổi cột được index trực tiếp hoặc gián tiếp theo các quy tắc của PostgreSQL.
- Có đủ chỗ trên **cùng trang heap** cho phiên bản mới.
- Những điều kiện nội bộ khác cho phép tạo HOT chain.

Ví dụ lab:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET note = 'checked by support'
WHERE order_id = 105;

ROLLBACK;
```

`note` không được index trong schema lab, nên đây là **ứng viên HOT**.

Tuy nhiên, vẫn có:

- Phiên bản heap mới.
- Metadata MVCC.
- WAL và dirty buffers tương ứng đối với bảng logged.
- Công việc pruning/VACUUM trong tương lai nếu cần.

**HOT không phải UPDATE tại chỗ và không có nghĩa “không sinh dead tuples”.** Điểm tiết kiệm chính là giảm nhu cầu tạo index tuples mới.

### 13.1. Hình dung HOT chain

```text
B-tree index entry
       |
       v
Heap tuple root (V1)
       |
       v
HOT-updated V2 (cùng heap page)
       |
       v
HOT-updated V3 (cùng heap page)
```

Khi PostgreSQL cần tìm hàng qua index, nó có thể đi theo chain trong heap page để tìm phiên bản visible phù hợp.

Vì index entry vẫn trỏ tới vị trí root của chain, PostgreSQL có thể tránh tạo thêm index entry ở một số UPDATE. Khi phiên bản cũ không còn cần, chain có thể được prune/thu gọn theo các quy tắc an toàn.

### 13.2. Fillfactor hỗ trợ nhưng không bảo đảm HOT

Với:

```sql
CREATE TABLE ... WITH (fillfactor = 80);
```

PostgreSQL cố gắng để lại không gian trên page lúc INSERT theo fillfactor. Điều đó làm tăng khả năng chèn phiên bản UPDATE mới **cùng page**.

Nhưng:

- Một page có thể đã đầy sau nhiều UPDATE.
- Tuple mới có thể dài hơn tuple cũ.
- Kiểu dữ liệu lớn/TOAST làm chi phí khác.
- UPDATE có thể đụng cột index nên không HOT.
- Một số index dạng summarizing, ví dụ BRIN, có quy tắc HOT riêng theo phiên bản.

Không chọn fillfactor bằng cảm tính. Khi quyết định, cần xem kích thước bảng, tần suất UPDATE và tỷ lệ HOT thực tế.

---

## 14. Non-HOT UPDATE và lý do index tăng trưởng

Trong lab, `customer_id` nằm trong index:

```sql
CREATE INDEX idx_mvcc_orders_customer
ON mvcc_versions_lab.orders(customer_id);
```

Nếu UPDATE:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET customer_id = customer_id + 1000
WHERE order_id = 105;

ROLLBACK;
```

hàng mới có giá trị indexed key khác, nên UPDATE không thể được coi là HOT theo điều kiện thông thường.

Tương tự, `status` xuất hiện trong predicate partial index:

```sql
CREATE INDEX idx_mvcc_orders_paid
ON mvcc_versions_lab.orders(order_id)
WHERE status = 'PAID';
```

Khi status chuyển NEW → PAID:

- Hàng mới có thể bắt đầu được đưa vào partial index.
- Những index liên quan phải được duy trì.
- Khả năng HOT bị ảnh hưởng bởi dependency của index.

### 14.1. Tại sao một index có khóa không đổi vẫn có thể được bảo trì?

Ở non-HOT update, phiên bản heap mới có thể có vị trí vật lý khác. Các index entry cần ánh xạ tới các tuple có thể tìm thấy theo quy tắc MVCC.

Vì vậy, một non-HOT UPDATE thường có thể tạo **những index entries mới cho các index khác của bảng**, dù giá trị key của một vài index không thay đổi.

Nói cách khác, PostgreSQL không chỉ duy trì index theo giá trị key; nó còn cần chỉ được tới tuple version phù hợp. Đây là nguồn **write amplification** của non-HOT UPDATE.

### 14.2. Expression và INCLUDE cũng quan trọng

Ví dụ các index sau là **minh họa**; không bắt buộc tạo chúng trong lab:

```sql
-- Expression index phụ thuộc amount.
CREATE INDEX idx_amount_rounded
ON mvcc_versions_lab.orders ((ROUND(amount, 0)));

-- Covering index lưu thêm cột note.
CREATE INDEX idx_customer_covering
ON mvcc_versions_lab.orders (customer_id)
INCLUDE (note);

-- Partial index phụ thuộc status.
CREATE INDEX idx_paid_amount
ON mvcc_versions_lab.orders(amount)
WHERE status = 'PAID';
```

Khi đánh giá HOT, phải xem cả:

- Index key.
- Cột `INCLUDE`.
- Biểu thức index.
- Predicate của partial index.

Một cột không nằm trong **danh sách key đầu** của index vẫn có thể là dependency khiến UPDATE khó HOT.

### 14.3. Tại sao không xóa tất cả index để UPDATE nhanh hơn?

Index còn phục vụ:

- Tra cứu/ORDER BY/filter quan trọng.
- Unique constraint và PRIMARY KEY.
- Truy vấn báo cáo.
- Một số chiến lược thực thi hiệu quả.

Việc xóa index chỉ vì giảm chi phí ghi có thể làm workload đọc chậm nghiêm trọng hoặc phá ràng buộc dữ liệu. Tối ưu cần đánh đổi dựa trên số liệu **đọc và ghi**.

---

## 15. Một UPDATE không đổi giá trị vẫn có thể tạo phiên bản mới

Ví dụ:

```sql
UPDATE mvcc_versions_lab.orders
SET note = note
WHERE order_id = 106;
```

Người mới có thể nghĩ câu này miễn phí, vì `note` cũ và mới như nhau. Nhưng một UPDATE được thực thi bình thường vẫn có thể tạo phiên bản heap mới, phát sinh WAL, trigger và công việc VACUUM, trừ khi có cơ chế nào đó ngăn hoặc tránh việc cập nhật.

Nếu muốn chỉ UPDATE khi giá trị thực sự đổi:

```sql
UPDATE mvcc_versions_lab.orders
SET note = 'verified'
WHERE order_id = 106
  AND note IS DISTINCT FROM 'verified';
```

`IS DISTINCT FROM` có logic rõ cả với `NULL`, khác `<>` trong các trường hợp nullable.

### 15.1. Không tránh UPDATE nếu nghiệp vụ cần ghi nhận tác động

Một hệ thống audit có thể cố ý chạy UPDATE mỗi khi nhận yêu cầu xác nhận, dù giá trị không đổi. Thêm điều kiện `IS DISTINCT FROM` có thể làm:

- Trigger audit không được gọi.
- `updated_at` không thay đổi.
- Một event phát ra ngoài hệ thống bị bỏ qua.

Vì vậy, bỏ UPDATE thừa là **quyết định nghiệp vụ**, không chỉ là mẹo tối ưu hiệu năng.

### 15.2. UPDATE lặp nhiều lần

Nếu cùng một hàng được UPDATE hàng trăm lần trong thời gian ngắn, có thể có nhiều tuple versions đang hoặc đã tồn tại:

```text
V1 -> V2 -> V3 -> V4 -> ... -> Vn
```

Pruning/HOT có thể dọn nhanh các phiên bản không còn cần; nhưng nếu transaction dài giữ snapshot cũ, việc thu hồi bị hạn chế. Kết quả phụ thuộc page, index và tốc độ dọn rác.

---

## 16. DELETE tác động tới index như thế nào?

Khi DELETE một tuple, PostgreSQL không nhất thiết xóa ngay mọi entry ở tất cả index tại thời điểm lệnh DELETE chạy.

Trực giác:

```text
DELETE hàng id=102
   |
   +--> Tuple heap được đánh dấu theo MVCC
   |
   +--> Snapshot mới không còn thấy hàng sau commit
   |
   +--> Index entry cũ có thể còn tồn tại trong một thời gian
   |
   +--> VACUUM/index cleanup khi an toàn
```

Nếu một index scan tìm tới index entry cũ, heap visibility check giúp xác định tuple có thuộc snapshot hiện tại hay không, tùy cơ chế index và khả năng dùng visibility map.

### 16.1. DELETE nhiều không nhất thiết làm index nhỏ ngay

Sau DELETE lớn:

- Bảng còn các vùng trống/tuple chưa dọn.
- Index có thể giữ entries sẽ được cleanup.
- VACUUM có thể giải phóng không gian **để tái sử dụng**.
- File trên filesystem không tự co lại theo mọi lần DELETE.

Vì vậy, “tôi đã DELETE 90% hàng nhưng `du -h` vẫn gần như cũ” không tự chứng minh DELETE thất bại.

### 16.2. DROP/TRUNCATE không đồng nghĩa DELETE

`TRUNCATE` thường loại toàn bộ nội dung bảng hiệu quả hơn DELETE từng hàng, nhưng có hành vi khác về lock, trigger, foreign key, transaction và replication. Nó không phù hợp khi muốn xóa **một tập hàng con** hoặc cần row-level DELETE triggers.

`DROP TABLE` lại xóa chính cấu trúc bảng, hoàn toàn khác DELETE.

Không thay một quy trình DELETE bằng TRUNCATE/DROP chỉ vì muốn thu hồi disk nếu yêu cầu nghiệp vụ không cho phép.

---

## 17. Pruning: thu gọn phiên bản cũ ngay trên heap page

PostgreSQL có thể thực hiện **page pruning** để dọn/thu gọn các tuple versions không còn cần tại heap page, nhất là các HOT chains.

Khác với ý tưởng “chỉ VACUUM mới dọn dữ liệu cũ”, một số thao tác truy cập heap cũng có thể kích hoạt pruning khi điều kiện phù hợp.

Ví dụ:

```text
Ban đầu:
    Page P: [V1 -> V2 -> V3]

Sau các transaction và snapshot liên quan kết thúc:
    V1, V2 không còn cần

Page pruning:
    Có thể giải phóng/thu gọn chain và slot cần thiết
    để truy cập V3 hiệu quả và tái sử dụng không gian
```

### 17.1. Pruning không thay VACUUM

Pruning tập trung ở page/tuple chain và khả năng tái sử dụng tại chỗ. VACUUM còn xử lý các khía cạnh rộng hơn:

- Thu dọn dead tuples.
- Cleanup index entries khi phù hợp.
- Cập nhật thông tin về space/visibility.
- Thực hiện các công việc freeze cần thiết.
- Hỗ trợ duy trì trạng thái toàn relation.

Vì vậy, không nên tắt autovacuum vì “có pruning rồi”.

### 17.2. Pruning làm n_dead_tup khó đối chiếu trực tiếp

Một page có thể được prune trước khi VACUUM toàn bảng. Cùng với độ trễ của thống kê, điều này làm cho bộ đếm dead tuples không phải phép đo trực tiếp, tuyệt đối của từng tuple vật lý tồn tại trên mỗi page.

---

## 18. VACUUM: thu hồi khả năng tái sử dụng không gian

`VACUUM` thông thường có mục tiêu chính là dọn những phiên bản không còn cần, giúp không gian được tái sử dụng, hỗ trợ hiệu quả truy vấn và quản lý transaction age.

Trong database lab:

```sql
VACUUM (ANALYZE) mvcc_versions_lab.orders;
```

**Lưu ý:** `VACUUM` thông thường **không được chạy bên trong transaction block tường minh** bằng `BEGIN ... VACUUM ... COMMIT`. Hãy chạy ở session autocommit hoặc theo cơ chế công cụ tương ứng.

### 18.1. VACUUM thông thường làm gì?

Ở mức khái niệm:

1. Xác định phiên bản hàng nào có thể an toàn dọn theo MVCC.
2. Cleanup heap và index khi cần.
3. Làm không gian trong relation có thể tái sử dụng.
4. Cập nhật thông tin free space/visibility.
5. Freeze các thông tin transaction cũ khi thích hợp.
6. Với `ANALYZE`, cập nhật thống kê giúp query planner.

Mục tiêu của ordinary VACUUM là **bảo trì liên tục** chứ không phải rewrite toàn bộ bảng cho nhỏ nhất.

### 18.2. VACUUM thường không trả lại toàn bộ disk cho hệ điều hành

Giả sử bảng từng chứa 100 triệu hàng, sau đó DELETE 90 triệu hàng.

Ngay cả khi VACUUM dọn thành công:

- Nhiều page trống ở **giữa file** có thể được giữ để INSERT/UPDATE về sau sử dụng lại.
- PostgreSQL có thể thu gọn một phần cuối file trong những tình huống phù hợp, nhưng không nên kỳ vọng mọi page trống đều làm file nhỏ ngay.
- Những index cũng có chiến lược reuse/cleanup riêng.

Nếu mục tiêu bắt buộc là lấy lại phần lớn dung lượng filesystem, cần cân nhắc các biện pháp rewrite/rebuild có kế hoạch, không mặc định ordinary VACUUM sẽ đủ.

### 18.3. VACUUM FULL khác gì?

`VACUUM FULL` **rewrite** bảng để thu gọn không gian vật lý và thường cần **ACCESS EXCLUSIVE lock** trên bảng; nó có thể làm gián đoạn truy cập đồng thời, tạo I/O/WAL và cần thêm không gian tạm trong quá trình rewrite.

Chỉ dùng khi:

- Có bằng chứng bảng bloat đáng kể và cần thu hồi dung lượng thật.
- Có khung bảo trì phù hợp.
- Đã xem lock, đĩa trống, replication và backup.
- Đã cân nhắc phương án thay thế phù hợp.

Không chạy VACUUM FULL mỗi lần DELETE nhiều hàng như cách bảo trì mặc định.

### 18.4. ANALYZE không phải dọn rác

`ANALYZE` cập nhật thống kê phân phối dữ liệu cho planner. Nó **không thay** công việc dọn dead tuples như VACUUM.

```sql
ANALYZE mvcc_versions_lab.orders;
```

có thể giúp planner sau khi dữ liệu thay đổi đáng kể, nhưng không làm dead tuples biến mất chỉ vì chạy ANALYZE.

---

## 19. Autovacuum: cơ chế bảo trì nền

PostgreSQL có **autovacuum** để tự động VACUUM và ANALYZE dựa trên hoạt động ghi, ước lượng số tuple và các tham số cấu hình.

Đây là cơ chế thiết yếu đối với bảng ghi nhiều, không nên coi là một công việc tùy chọn có thể tắt vô hại.

### 19.1. Vì sao autovacuum cần thiết?

Không có bảo trì phù hợp:

- Dead tuples tích tụ.
- Heap và index có nguy cơ bloat.
- SELECT phải kiểm tra nhiều tuple không còn hữu ích.
- Ghi mới phải làm việc với các page/index kém hiệu quả.
- Transaction IDs già đi, có nguy cơ wraparound.
- Bảng có thể bị buộc vào chế độ bảo vệ khi XID age quá lớn.

Autovacuum giúp kiểm soát những nguy cơ này trong điều kiện bình thường.

### 19.2. Ngưỡng kích hoạt thường có dạng nào?

Ý tưởng đơn giản hóa cho một số điều kiện vacuum:

```text
Ngưỡng dead tuples ước tính
  ~ autovacuum_vacuum_threshold
    + autovacuum_vacuum_scale_factor * số hàng ước tính
```

Khi bảng rất lớn, một tỷ lệ phần trăm nhỏ vẫn có thể tương ứng hàng triệu dead tuples.

Nhưng công thức trên là **mô hình nhập môn**. PostgreSQL hiện đại có thêm ngưỡng/điều kiện liên quan INSERT, freeze và cấu hình như maximum threshold; không nên xem nó là toàn bộ thuật toán scheduler của mọi phiên bản.

### 19.3. Cấu hình theo bảng

Ví dụ minh họa về per-table autovacuum options:

```sql
ALTER TABLE mvcc_versions_lab.orders SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.03
);
```

Các giá trị này là **ví dụ cho lab**, không phải một khuyến nghị áp dụng toàn production.

Thay đổi ngưỡng quá thấp có thể tăng hoạt động vacuum nền; quá cao có thể để dead tuples tích tụ. Phải xem quy mô bảng, tốc độ UPDATE/DELETE, free space, I/O, replication và thống kê thực tế.

### 19.4. Autovacuum có thể đến muộn

Một job UPDATE tạo dead tuples rất nhanh có thể khiến autovacuum chưa dọn kịp. Điều này không có nghĩa tính năng bị hỏng:

- Worker slots giới hạn.
- Table đang bị lock hoặc có hoạt động khác.
- Hệ thống thiếu I/O/CPU.
- Transaction dài giữ snapshot.
- Các cấu hình threshold/cost có thể chưa phù hợp.

Cần xem nguyên nhân thay vì tự chạy VACUUM FULL hoặc tắt autovacuum.

---

## 20. Vì sao transaction dài giữ lại hàng cũ?

MVCC chỉ dọn được phiên bản **không còn cần cho những snapshot liên quan**. Một transaction kéo dài có thể giữ một snapshot rất cũ, ngăn PostgreSQL thu hồi những tuple mà transaction đó còn cần thấy.

Ví dụ:

```text
10:00  Session A bắt đầu REPEATABLE READ
10:01  Session A lấy snapshot, thấy bản V1
10:02  Session B UPDATE -> V2, COMMIT
10:03  Session C UPDATE -> V3, COMMIT
10:04  Session D UPDATE -> V4, COMMIT
...
11:00  Session A vẫn mở và còn cần snapshot cũ
```

Nếu A cần thấy V1, hệ thống không thể đơn giản dọn mọi phiên bản cũ rồi chỉ giữ V4.

### 20.1. Idle in transaction có thể nguy hiểm

Một ứng dụng đôi khi:

1. Mở transaction.
2. Chạy SELECT.
3. Đợi HTTP request khác, user input, hoặc gọi API bên ngoài.
4. Quên COMMIT/ROLLBACK.

Session có thể ở trạng thái `idle in transaction`, giữ transaction/snapshot/locks tùy tình huống và gây cản trở VACUUM.

### 20.2. Xem transaction lâu bằng pg_stat_activity

Với quyền quan sát phù hợp:

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    backend_xmin,
    wait_event_type,
    wait_event,
    now() - xact_start AS transaction_age,
    left(query, 120) AS query_preview
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Cột `backend_xmin` có thể cho thấy mốc snapshot/visibility liên quan tới backend. Không phải mọi transaction lâu đều đang giữ cùng một kiểu horizon hoặc có `backend_xmin` khác NULL.

**Không tự terminate các backend** chỉ vì xact_start cũ: phải xác định owner, workload, hệ quả rollback và quyền vận hành. Cần phân biệt query dài hợp lệ, job backup, migration và client bị treo.

### 20.3. Cấu hình bảo vệ idle transaction

PostgreSQL có cấu hình như `idle_in_transaction_session_timeout` để giới hạn session rỗi trong transaction.

Tùy ứng dụng, timeout này có thể hữu ích nhưng cũng có thể làm rollback những transaction chưa được thiết kế để chịu ngắt kết nối. Không áp dụng mà không kiểm tra ứng dụng, pool kết nối và retry.

---

## 21. Replication có thể liên quan đến việc giữ phiên bản cũ

Không chỉ client transaction trên primary mới ảnh hưởng khả năng cleanup.

Một số cơ chế replication, logical decoding hoặc feedback từ standby có thể giữ những mốc transaction/tuple cần thiết để bảo đảm dữ liệu còn đọc/giải mã được.

### 21.1. Replication slots

Trên primary, xem:

```sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin,
    restart_lsn
FROM pg_replication_slots
ORDER BY slot_name;
```

Các cột như `xmin` và `catalog_xmin` có thể phản ánh mốc transaction mà slot cần giữ để phục vụ một số loại dữ liệu, tùy cơ chế và phiên bản.

Cần phân biệt hai ảnh hưởng:

- Slot có thể giữ **WAL** qua `restart_lsn`, làm `pg_wal` tăng.
- Một số retention horizons liên quan slot/decoding có thể ảnh hưởng việc cleanup tuple hoặc catalog tuple.

**Không phải mọi slot luôn giữ mọi dead tuple của tất cả bảng.** Cần xem loại slot, mốc horizon và công việc consumer thực tế.

### 21.2. hot_standby_feedback

Khi physical standby dùng `hot_standby_feedback`, standby có thể báo nhu cầu snapshot cũ lên primary để tránh hủy những phiên bản mà query trên standby vẫn cần.

Đánh đổi:

- Có thể giảm một số recovery conflicts/cancellation của truy vấn dài trên standby.
- Có thể khiến primary giữ lại dead tuples lâu hơn, tăng bloat.

Không bật hoặc tắt `hot_standby_feedback` chỉ bằng một KPI, vì nó ảnh hưởng cả workload đọc standby lẫn cleanup ở primary.

### 21.3. Vì sao replica lag và dead tuples có thể liên quan?

Một consumer chậm có thể:

- Gây giữ WAL.
- Giữ những horizon cần cho logical decoding.
- Tạo tác động gián tiếp qua feedback/snapshot.
- Dẫn đến áp lực storage và VACUUM trong những điều kiện cụ thể.

Nhưng **replication lag không đồng nghĩa trực tiếp dead tuples tăng**. Cần đo cả các mốc transaction, vacuum, slot và tình trạng index/table để xác định nguyên nhân.

---

## 22. Transaction ID wraparound và freezing

PostgreSQL có cơ chế transaction ID với không gian ID hữu hạn và logic so sánh tuổi. Nếu một hệ thống không xử lý/freeze những tuple có thông tin transaction quá cũ, việc tái sử dụng transaction ID trong tương lai có thể làm sai visibility.

Đây là lý do **VACUUM còn có nhiệm vụ chống XID wraparound**, không chỉ dọn dead tuples.

### 22.1. Freeze là gì?

Đối với những phiên bản đã commit đủ cũ và đáp ứng điều kiện, PostgreSQL có thể xử lý metadata theo cơ chế freeze để chúng tiếp tục được xem là hợp lệ khi transaction IDs quay vòng.

Không cần nhớ layout bit nội bộ; cần hiểu:

- Tuple sống lâu cũng cần bảo trì metadata theo thời gian.
- Một bảng hiếm UPDATE/DELETE vẫn có thể cần VACUUM cho freeze.
- Tắt autovacuum hoặc giữ transaction tuổi rất lớn có thể tạo nguy cơ nghiêm trọng.

### 22.2. Các tín hiệu vận hành

Một số cột/hàm liên quan:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname = 'mvcc_versions_lab'
ORDER BY xid_age DESC;
```

`age(relfrozenxid)` là một chỉ số về tuổi transaction ID liên quan khả năng freeze của bảng. Nó không phải tuổi thực bằng ngày/giờ.

Các tham số như `autovacuum_freeze_max_age` ảnh hưởng bảo trì chống wraparound, nhưng không có một ngưỡng “an toàn” chung ngoài bối cảnh phiên bản, tài nguyên và workload.

### 22.3. Không tự tắt anti-wraparound autovacuum

Một số phiên bản có cơ chế chạy autovacuum chống wraparound ngay cả khi cấu hình autovacuum thông thường bị vô hiệu hóa cho table. Không nên dùng điều đó như chiến lược vận hành.

Để hệ thống đến gần tình trạng wraparound có thể dẫn tới chế độ bảo vệ nghiêm ngặt và gián đoạn ghi. Phòng ngừa bằng monitoring và VACUUM định kỳ luôn dễ hơn ứng cứu khi đã quá muộn.

---

## 23. Đo UPDATE, DELETE và HOT bằng pg_stat_user_tables

Trong PostgreSQL, `pg_stat_user_tables` là nơi khởi đầu thực tế.

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
WHERE schemaname = 'mvcc_versions_lab'
  AND relname = 'orders';
```

### 23.1. Giải thích các cột

| Cột | Cách đọc |
| --- | --- |
| `n_tup_ins` | Số tuple INSERT được thống kê |
| `n_tup_upd` | Số tuple UPDATE được thống kê |
| `n_tup_del` | Số tuple DELETE được thống kê |
| `n_tup_hot_upd` | Số UPDATE sử dụng HOT |
| `n_live_tup` | Ước lượng số tuple sống |
| `n_dead_tup` | Ước lượng số dead tuples |
| `last_vacuum` | Lần VACUUM thủ công gần nhất nếu có |
| `last_autovacuum` | Lần autovacuum gần nhất nếu có |
| `vacuum_count` | Tổng số lần VACUUM thủ công theo bộ đếm |
| `autovacuum_count` | Tổng số lần autovacuum theo bộ đếm |

Đây là **thống kê hệ thống**, không phải log audit transactional chính xác. Chúng có thể có độ trễ, bị reset và cùng thay đổi khi nhiều session ghi bảng.

### 23.2. Tính HOT ratio

```sql
SELECT
    relname,
    n_tup_upd,
    n_tup_hot_upd,
    ROUND(
        100::NUMERIC * n_tup_hot_upd
          / NULLIF(n_tup_upd, 0),
        2
    ) AS hot_percent
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_versions_lab'
  AND relname = 'orders';
```

`NULLIF(n_tup_upd,0)` giúp tránh phép chia cho 0 nếu chưa có UPDATE.

Một tỷ lệ HOT thấp không mặc định là lỗi: nếu workload cố ý thay đổi indexed columns, HOT không phù hợp cho những UPDATE đó. Ngược lại, tỷ lệ HOT cao không bảo đảm bảng không có dead tuples hoặc WAL.

### 23.3. Kiểm tra dữ liệu sống bằng COUNT

```sql
SELECT COUNT(*) AS visible_orders
FROM mvcc_versions_lab.orders;
```

Kết quả `COUNT(*)` phụ thuộc snapshot của SELECT. Nó không đếm các phiên bản cũ không visible như một hàng nghiệp vụ riêng.

Đừng so `COUNT(*)` trực tiếp với `n_live_tup + n_dead_tup` và kỳ vọng hai phía luôn bằng nhau: một bên là phép đếm visible theo snapshot, bên kia là ước lượng về các tuple theo thống kê.

### 23.4. Thống kê được làm mới theo cơ chế riêng

Nếu kết quả ngay sau DML chưa thay đổi như kỳ vọng, có thể là do:

- Cơ chế gửi/flush stats.
- Snapshot statistics đã cache.
- Statement/transaction chưa commit.
- VACUUM đã dọn.
- Writer khác đồng thời thay đổi bảng.
- Stats từng được reset.

```sql
SELECT pg_stat_clear_snapshot();
```

có thể bỏ snapshot thống kê đã cache cho session theo khả năng chức năng này. Nó không chuyển `n_dead_tup` thành một phép đếm chính xác theo thời gian thực.

---

## 24. Quan sát dung lượng bảng và index

Dùng các hàm kích thước:

```sql
SELECT
    pg_size_pretty(
        pg_relation_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS heap_main_size,

    pg_size_pretty(
        pg_table_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS table_size,

    pg_size_pretty(
        pg_indexes_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS all_indexes_size,

    pg_size_pretty(
        pg_total_relation_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS total_relation_size;
```

Phân biệt:

- `pg_relation_size` mặc định đo main fork của relation.
- `pg_table_size` tính kích thước table storage cùng các phần liên quan theo định nghĩa.
- `pg_indexes_size` là tổng dung lượng index liên quan.
- `pg_total_relation_size` là bảng cùng index.

### 24.1. Cách hiểu bloat

**Bloat** là vấn đề tương quan giữa dung lượng vật lý và lượng dữ liệu hữu ích. Một file lớn **không tự động là bloat**, vì nó có thể đang chứa nhiều hàng sống hoặc vùng trống có thể sớm tái sử dụng.

Dấu hiệu nên xem cùng nhau:

- Table/index size tăng trong khi hàng sống ổn định.
- UPDATE/DELETE cao.
- Dead tuple estimates lớn trong thời gian dài.
- Index scan/table scan trở nên đắt.
- VACUUM không theo kịp.
- Transaction dài giữ snapshot.
- Workload có nhiều non-HOT UPDATE.

Để kết luận bloat chính xác hơn có thể cần công cụ/extension chuyên biệt và phân tích về page density/free space, không chỉ `pg_total_relation_size`.

### 24.2. pgstattuple là công cụ nâng cao tùy chọn

Extension `pgstattuple` có thể cung cấp thông tin chi tiết hơn về tuple sống, dead tuple và free space theo cơ chế nó đo. Việc cài extension cần quyền và có overhead scan.

Ví dụ **chỉ chạy khi extension đã được cấp quyền/cài sẵn và có nhu cầu vận hành**:

```sql
SELECT *
FROM pgstattuple('mvcc_versions_lab.orders');
```

Không nên chạy liên tục trên các bảng khổng lồ trong giờ cao điểm. Đây là một công cụ đo đạc nâng cao, không phải điều kiện bắt buộc của bài lab.

---

## 25. EXPLAIN ANALYZE của UPDATE/DELETE: một điểm an toàn bắt buộc

`EXPLAIN (ANALYZE, BUFFERS, WAL)` có thể giúp quan sát số hàng xử lý, page buffers, WAL records và thời gian thực thi của một câu DML.

**Cảnh báo cực quan trọng:** Khi có `ANALYZE`, PostgreSQL **thực sự thực thi lệnh UPDATE/DELETE/INSERT**.

Trong lab, có thể bao quanh bởi transaction rồi rollback:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE mvcc_versions_lab.orders
SET note = note || '-test'
WHERE order_id BETWEEN 101 AND 106;

ROLLBACK;
```

Hoặc:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
DELETE FROM mvcc_versions_lab.orders
WHERE status = 'CANCELED';

ROLLBACK;
```

### 25.1. Điều gì cần quan sát?

Một plan có thể có những thông tin dạng:

```text
Update on orders ...
  Buffers: shared hit=..., dirtied=..., written=...
  WAL: records=..., fpi=..., bytes=...
  -> ...
Planning Time: ...
Execution Time: ...
```

Các dấu `...` ở đây chỉ là minh họa cấu trúc; không phải kết quả đo của một hệ thống thật.

Cần xem:

- Số hàng thực sự bị tác động.
- Scan mode để tìm hàng.
- `Buffers`: đọc/đánh dấu dirty/ghi trang được thống kê.
- `WAL`: số record, full-page images và bytes của statement.
- Execution time.
- Kết hợp với `pg_stat_user_tables` khi phân tích lâu dài.

### 25.2. ROLLBACK không xóa chi phí phép thử

Dù dữ liệu logic quay lại như cũ, phép UPDATE/DELETE thử vẫn có thể tạo:

- WAL.
- Dirty buffers.
- Tuple versions/metadata cần xử lý.
- Trigger tác động ngoài DB nếu thiết kế không giao dịch.
- Sequence value đã cấp.

Vì vậy, thực hành trên **database test**, không chạy transaction rollback trên production chỉ vì nghĩ “không thay đổi gì”.

### 25.3. Không đo một lần rồi kết luận

Kết quả EXPLAIN chịu ảnh hưởng:

- Table size và cache.
- Số lượng index.
- Full-page images sau checkpoint.
- Trạng thái HOT/non-HOT.
- Độ dài tuple.
- Transaction concurrent.
- Lock wait, CPU, disk, WAL flush và replication.
- VACUUM/pruning đã xảy ra hay chưa.

Để so sánh hai thiết kế, cần điều kiện thử tương đương và nhiều lần đo; bài học này hướng dẫn công cụ, không đưa ra benchmark tuyệt đối.

---

## 26. Một thí nghiệm dễ hiểu: UPDATE note nhiều lần

Nếu reset lab và chạy một số UPDATE cho một hàng:

```sql
BEGIN;

UPDATE mvcc_versions_lab.orders
SET note = 'v2'
WHERE order_id = 105;

UPDATE mvcc_versions_lab.orders
SET note = 'v3'
WHERE order_id = 105;

UPDATE mvcc_versions_lab.orders
SET note = 'v4'
WHERE order_id = 105;

SELECT order_id, note
FROM mvcc_versions_lab.orders
WHERE order_id = 105;

COMMIT;
```

Trong transaction, kết quả SELECT là `v4`.

Các phiên bản trung gian được tạo trong cùng transaction có thể không cần tồn tại lâu sau khi hệ thống xác định visibility và dọn, nhưng điều đó không có nghĩa các UPDATE trước miễn phí.

### 26.1. Thêm nhiều index thì sao?

Nếu bổ sung index phụ thuộc `note`, mỗi thay đổi note có thể ảnh hưởng index và cơ hội HOT. Điều đó có thể tăng write amplification và bloat với workload ghi chú cập nhật liên tục.

Nhưng index note có thể rất hữu ích nếu API thực sự cần tra cứu theo note; đánh đổi phải dựa trên workload đọc và yêu cầu tìm kiếm.

### 26.2. Không mặc định ba UPDATE cùng transaction bằng một UPDATE

Ba câu UPDATE có thể tạo nhiều lần công việc heap/WAL/trigger. Nếu ứng dụng có thể **gộp ý định thay đổi** để chỉ lưu trạng thái cuối, thường đáng xem xét:

```sql
UPDATE mvcc_versions_lab.orders
SET note = 'v4'
WHERE order_id = 105;
```

Tuy nhiên, nếu v2/v3/v4 là các trạng thái nghiệp vụ quan trọng cần audit hoặc event riêng, không thể bỏ chúng chỉ để giảm write volume.

---

## 27. DELETE hàng loạt và giới hạn transaction

Một câu:

```sql
DELETE FROM mvcc_versions_lab.orders
WHERE status = 'CANCELED';
```

với bảng lab chỉ tác động ít hàng. Nhưng trên bảng nhiều triệu hàng, DELETE một lượng lớn trong một transaction có thể:

- Tạo nhiều dead tuples.
- Ghi WAL đáng kể.
- Tăng công việc VACUUM/index cleanup.
- Giữ khóa và transaction lâu.
- Làm logical/physical replication bị trễ.
- Gây áp lực lên storage/pg_wal.
- Làm gián đoạn application workload.

### 27.1. DELETE theo batch

Một pattern PostgreSQL sử dụng CTE:

```sql
WITH batch AS (
    SELECT order_id
    FROM mvcc_versions_lab.orders
    WHERE status = 'CANCELED'
    ORDER BY order_id
    LIMIT 100
)
DELETE FROM mvcc_versions_lab.orders AS o
USING batch AS b
WHERE o.order_id = b.order_id
RETURNING o.order_id;
```

Trong ứng dụng, có thể chạy từng batch trong **transaction riêng**, dừng khi không còn hàng; lưu checkpoint công việc và giám sát.

**Không nên hiểu batch sẽ giảm chắc chắn tổng số WAL bytes hay số dead tuples.** Batch giúp kiểm soát đỉnh tải, thời gian khóa, khả năng dừng/tiếp tục và tốc độ ứng dụng.

### 27.2. Đừng giả định LIMIT trực tiếp trong DELETE

Cú pháp kiểu:

```sql
-- Không phải cú pháp DELETE ... LIMIT trực tiếp chuẩn trong PostgreSQL.
DELETE FROM mvcc_versions_lab.orders
WHERE status = 'CANCELED'
LIMIT 100;
```

không được PostgreSQL hỗ trợ theo dạng thông thường. Dùng CTE/subquery chọn khóa rồi DELETE qua khóa như ví dụ.

### 27.3. Concurrency và batch

Khi nhiều worker cùng xóa:

- Có thể hai worker chọn cùng hàng trước khi khóa.
- Có lock waits.
- Hàng có thể đổi status giữa lúc SELECT batch và lúc DELETE.
- Phải quyết định quyền xóa và idempotency.
- Có thể cần `FOR UPDATE SKIP LOCKED` cho kiến trúc nhiều worker phù hợp.

Nếu dùng `SKIP LOCKED`, nhớ rằng nó tạo một cách nhìn cố ý bỏ qua hàng đang bị khóa và không phù hợp cho mọi mục tiêu nhất quán/đối soát.

### 27.4. Partitioning giúp gì?

Với dữ liệu cũ theo thời gian, thiết kế **partitioning** có thể giúp loại một partition cũ theo chính sách retention mà không DELETE từng row.

Nhưng việc detach/drop partition còn có quy tắc về lock, schema, foreign key, replication, backup và ứng dụng. Đây là quyết định thiết kế dài hạn, không phải mẹo thay DELETE tức thì cho mọi bảng.

---

## 28. VACUUM không sửa các vấn đề đồng thời thay ứng dụng

MVCC hỗ trợ nhiều người đọc/ghi cùng lúc nhưng không tự bảo đảm mọi business transaction đúng.

### 28.1. Lost update và điều kiện ghi

Giả sử hai dịch vụ đọc `amount=100` rồi tự tính giá trị mới ở ứng dụng:

```text
A đọc 100, quyết định ghi 120
B đọc 100, quyết định ghi 130

A UPDATE SET amount=120
B UPDATE SET amount=130
```

Tùy thứ tự/locking/isolation, kết quả cuối có thể không phản ánh cả hai ý định. Có thể dùng:

- UPDATE nguyên tử theo giá trị hiện tại: `SET amount = amount + 10`, phù hợp khi nghiệp vụ là phép cộng delta.
- Optimistic concurrency với cột version: `WHERE version = expected_version`.
- Row locks và transaction.
- Isolation phù hợp như SERIALIZABLE, xử lý retry nếu có.
- Constraint ngăn giá trị ngoài miền.

VACUUM không có vai trò phát hiện/giải quyết lost updates.

### 28.2. UPDATE ... RETURNING

Một pattern hữu ích:

```sql
UPDATE mvcc_versions_lab.orders
SET amount = amount + 10
WHERE order_id = 101
RETURNING order_id, amount, status;
```

Nó trả **giá trị sau UPDATE** của các hàng thực sự được tác động, giúp ứng dụng biết số hàng thay đổi và giá trị mới theo transaction.

Nhưng RETURNING không thay việc kiểm tra transaction outcome, constraint và concurrency. Không dùng `ctid` làm version token bền vững qua nhiều request.

### 28.3. Optimistic locking bằng version do ứng dụng quản lý

Một bảng nghiệp vụ có cột `row_version BIGINT NOT NULL` có thể dùng mẫu:

```sql
-- Ví dụ minh họa cho bảng có cột row_version.
UPDATE application_orders
SET status = 'PAID',
    row_version = row_version + 1
WHERE order_id = 101
  AND row_version = 7
RETURNING order_id, row_version;
```

Nếu 0 hàng được trả, một khả năng là version đã khác do giao dịch khác cập nhật. Ứng dụng phải phân biệt không tìm thấy hàng, thiếu quyền và xung đột update theo contract.

Đừng lấy `xmin` làm version ứng dụng mặc định; system columns có tính chất nội bộ và vòng đời khác một cột version nghiệp vụ.

---

## 29. Index-only scan và visibility map liên quan gì?

Một số truy vấn có thể dùng **index-only scan**, tức lấy các cột cần thiết từ index khi index chứa đủ thông tin. Nhưng với PostgreSQL MVCC, index entry tự nó thường không cung cấp đầy đủ xác nhận một heap tuple có visible với snapshot hay không.

PostgreSQL có **visibility map** đánh dấu các heap pages được biết là all-visible đối với những snapshot thích hợp, giúp index-only scan có thể tránh nhiều heap fetches.

### 29.1. UPDATE/DELETE ảnh hưởng all-visible

Khi một trang từng all-visible bị thay đổi, trạng thái visibility có thể cần được điều chỉnh. Điều đó có thể làm index-only scans phải quay lại heap kiểm tra visibility nhiều hơn cho tới khi VACUUM/các cơ chế thích hợp xác nhận lại.

Vì vậy, một workload UPDATE dày đặc có thể làm truy vấn đọc chậm hơn dù đã có covering index.

### 29.2. Dùng EXPLAIN trên SELECT

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM mvcc_versions_lab.orders
WHERE order_id BETWEEN 101 AND 106;
```

Nếu planner chọn Index Only Scan, có thể thấy metric `Heap Fetches`. Nhưng với bảng lab chỉ sáu hàng, sequential scan có thể rẻ hơn; không có gì bất thường nếu không thấy Index Only Scan.

### 29.3. All-visible không có nghĩa “không còn bất kỳ phiên bản cũ vật lý nào”

Visibility map là metadata cho phép planner/executor tối ưu các kiểm tra visibility và vacuum, theo điều kiện PostgreSQL. Không nên diễn giải một bit all-visible thành “đĩa không chứa byte nào từ phiên bản cũ”.

---

## 30. WAL và replica: các phiên bản hàng còn ảnh hưởng hệ thống nào?

Với bảng logged thông thường, UPDATE/DELETE còn phát sinh **WAL** cho phục hồi. Physical standby có thể phải replay các thay đổi WAL liên quan heap và index. Logical replication có thể decode thay đổi hàng theo publication/replica identity.

### 30.1. Physical replica

Physical streaming replication nhận và replay WAL. Nếu primary chạy UPDATE nhiều:

- WAL generation rate tăng.
- Standby có thể cần thêm CPU/I/O để replay.
- Asynchronous standby có thể đọc trạng thái cũ cho tới khi replay tới LSN tương ứng.

Độ trễ replica không phải bằng số dead tuples, nhưng hai áp lực có thể xuất hiện cùng lúc trong một đợt ghi lớn.

### 30.2. Logical replica

Trong logical replication, UPDATE/DELETE thường cần thông tin nhận diện hàng đích để apply. Primary key thường là lựa chọn tốt cho **replica identity**; nếu không có khóa phù hợp có thể cần cấu hình khác, với chi phí WAL/apply bổ sung.

Không tự đặt `REPLICA IDENTITY FULL` để “sửa VACUUM”. Đó là cơ chế phục vụ logical replication, không phải giải pháp dọn dead tuple.

### 30.3. DELETE rồi replica vẫn thấy hàng?

Có thể xảy ra trong asynchronous replication nếu standby chưa replay DELETE. Đây là **replication lag**, khác với tình huống Session A trên primary giữ snapshot REPEATABLE READ cũ.

Khi điều tra, cần phân biệt:

1. Đọc snapshot cũ trên cùng primary.
2. Đọc replica chưa replay kịp.
3. Transaction DELETE chưa COMMIT.
4. DELETE không khớp hàng nào.
5. Ứng dụng dùng cache.
6. Có soft delete khác physical DELETE.

Dựa vào đúng tầng để giải thích, không gọi mọi trường hợp “PostgreSQL chưa dọn dead tuples”.

---

## 31. Soft delete khác physical DELETE theo MVCC

Nhiều hệ thống dùng:

```sql
UPDATE orders
SET deleted_at = clock_timestamp()
WHERE order_id = 101;
```

Đây là **soft delete** ở mức ứng dụng. Bản ghi vẫn tồn tại logic trong bảng, chỉ được đánh dấu không còn hoạt động.

Về mặt PostgreSQL, câu trên là **UPDATE**, không phải DELETE:

- Tạo phiên bản tuple mới theo MVCC.
- Có thể sinh phiên bản cũ cần cleanup.
- Nếu `deleted_at` tham gia partial index/biểu thức index, có thể ảnh hưởng HOT.
- Truy vấn phải có filter `deleted_at IS NULL` nếu nghiệp vụ yêu cầu chỉ xem hàng đang hoạt động.

Ví dụ bảng giả định:

```sql
SELECT *
FROM orders_with_soft_delete
WHERE deleted_at IS NULL;
```

Đây là minh họa, bảng `orders_with_soft_delete` không được tạo trong lab.

### 31.1. Vì sao soft delete không tự giảm dung lượng?

Soft delete thường **giữ bản ghi hiện hành** để audit/phục hồi; nó không giải phóng toàn bộ dữ liệu như khi xóa hẳn khỏi tập nghiệp vụ. Thậm chí nó vẫn tạo một phiên bản cũ từ UPDATE.

Nếu retention policy yêu cầu xóa thật sau 90 ngày, cần một quy trình purge riêng và đánh giá MVCC/VACUUM, backup, replicas và yêu cầu pháp lý.

---

## 32. Phân biệt VACUUM, REINDEX và VACUUM FULL

| Công cụ | Mục tiêu chủ yếu | Tác động và lưu ý |
| --- | --- | --- |
| `VACUUM` | Dọn dead tuples, duy trì khả năng reuse/visibility/freeze | Thường tương thích hơn với hoạt động đồng thời; không tự thu gọn toàn bộ file |
| `VACUUM (ANALYZE)` | VACUUM và cập nhật stats planner | Hữu ích sau nhiều thay đổi, nhưng vẫn có chi phí |
| `ANALYZE` | Cập nhật thống kê planner | Không thay dead tuple cleanup |
| `VACUUM FULL` | Rewrite để thu gọn bảng | Lock mạnh, cần tài nguyên và kế hoạch bảo trì |
| `REINDEX` | Xây lại index | Nhắm tới cấu trúc index, có chi phí/lock riêng |
| `REINDEX CONCURRENTLY` | Xây lại index với mục tiêu giảm khóa chặn trong tình huống hỗ trợ | Có giới hạn và quy tắc vận hành riêng |
| `CLUSTER` | Rewrite/đặt lại thứ tự vật lý theo index được chọn | Có lock/chi phí lớn, không phải VACUUM thay thế |
| `pg_repack` (extension bên ngoài) | Có thể hỗ trợ rewrite/repack theo điều kiện | Cần extension, quyền, dung lượng và kế hoạch riêng |

**Không có “nút dọn rác tốt nhất cho mọi bảng”.** Công cụ phù hợp phụ thuộc yêu cầu: dọn tuple, thu hồi disk, sửa index bloat hay cải thiện planner statistics.

### 32.1. Dùng phương pháp ít xâm lấn trước

Nếu bảng bị chậm sau nhiều UPDATE/DELETE:

1. Xác định nguyên nhân thật bằng stats, plan và size.
2. Kiểm tra long transactions/replication slot.
3. Kiểm tra autovacuum có hoạt động không.
4. Đánh giá HOT ratio và index dependencies.
5. Chỉ sau đó mới cân nhắc rewrite/REINDEX/FULL theo nhu cầu.

Bỏ qua bước điều tra rồi chạy VACUUM FULL có thể gây downtime mà không giải quyết được gốc rễ, ví dụ ứng dụng liên tục UPDATE không cần thiết.

---

## 33. Điều tra tình huống: đã DELETE 80% hàng nhưng dung lượng không giảm

Giả sử trước chiến dịch có bảng 200 GB, sau DELETE chỉ còn 20% số hàng logic nhưng file vẫn gần 200 GB.

Các bước phân tích:

### 33.1. Xác nhận DELETE thật sự đã COMMIT

```sql
SELECT COUNT(*) FROM mvcc_versions_lab.orders;
```

Trong môi trường thật, xác định điều kiện DELETE, transaction outcome và nguồn kết nối. Một client có transaction chưa commit không đủ để nói xóa đã hoàn tất.

### 33.2. Kiểm tra số dead tuples ước lượng

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_versions_lab';
```

Nếu dead tuples cao, xem khả năng dọn của autovacuum/VACUUM.

### 33.3. Kiểm tra snapshot giữ tuổi lâu

```sql
SELECT
    pid, state, xact_start, backend_xmin,
    now() - xact_start AS age
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
```

Xem còn transaction cũ hoặc slot/standby feedback cần giữ horizon không.

### 33.4. Kiểm tra table/index size

```sql
SELECT
    pg_size_pretty(
        pg_table_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS table_size,
    pg_size_pretty(
        pg_indexes_size('mvcc_versions_lab.orders'::REGCLASS)
    ) AS index_size;
```

Nếu VACUUM dọn được nhưng file vẫn lớn, có thể không gian đã được **đánh dấu có thể tái sử dụng** bên trong file, không được trả về filesystem.

### 33.5. Ra quyết định

- Nếu sắp INSERT trở lại với khối lượng lớn, reuse có thể rất hữu ích.
- Nếu storage gần đầy và dữ liệu sẽ tiếp tục nhỏ, có thể cần phương án rewrite/repack.
- Nếu bloat tập trung ở index, cần đánh giá index maintenance/rebuild.
- Nếu snapshot cũ chặn cleanup, xử lý vòng đời transaction.
- Nếu logical retention/backup giữ dữ liệu vì chính sách, không dùng VACUUM để lách chính sách.

---

## 34. Điều tra tình huống: UPDATE liên tục và CPU/I/O tăng

Một bảng có 5 triệu hàng, ứng dụng update `last_seen_at` nhiều lần mỗi phút cho nhiều người dùng.

Nếu `last_seen_at` được index, mỗi update có thể ảnh hưởng index và HOT. Nếu không index nhưng page đầy, HOT vẫn có thể thấp.

### 34.1. Các câu hỏi cần đặt

- Ứng dụng có thật sự cần ghi mỗi sự kiện hay có thể coalesce/debounce?
- `last_seen_at` được dùng để tìm kiếm/sort hay chỉ hiển thị?
- Có index expression hoặc partial index phụ thuộc nó không?
- HOT ratio là bao nhiêu?
- Fillfactor hiện tại bao nhiêu?
- Có transaction dài hoặc logical slot giữ horizon không?
- Autovacuum có theo kịp không?
- Table/index size có tăng bất thường không?

### 34.2. Các hướng thiết kế

Có thể cân nhắc:

- Chỉ cập nhật khi thời gian mới cách thời gian cũ đủ ngưỡng nghiệp vụ.
- Gom nhiều sự kiện thành một update nếu không cần chính xác từng lần.
- Di chuyển dữ liệu có tần suất cập nhật cao sang bảng riêng khi giúp phân tách workload.
- Rà soát index phụ thuộc cột thường thay đổi.
- Chỉnh fillfactor và vacuum thresholds sau benchmark.
- Thay đổi mô hình lưu event append-only nếu cần lịch sử đầy đủ.

Không có giải pháp duy nhất: nếu audit yêu cầu lưu từng sự kiện, việc gộp UPDATE có thể làm mất dữ liệu quan trọng; khi đó cần mô hình log/event phù hợp thay vì đơn giản bỏ ghi.

---

## 35. Điều tra tình huống: UPDATE chậm nhưng dead tuples không cao

Một câu UPDATE chậm không nhất thiết do bloat.

Có thể nguyên nhân là:

- Chờ row locks từ transaction khác.
- Constraint/foreign key hoặc trigger đắt.
- WHERE thiếu index nên scan nhiều hàng.
- Ghi WAL/commit flush chậm.
- Synchronous standby chậm.
- Disk I/O bận.
- Non-HOT index maintenance.
- Kiểu dữ liệu lớn/TOAST.
- Transaction retry nhiều.
- Tranh chấp tài nguyên trong ứng dụng.

### 35.1. Quan sát lock waits

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age,
    left(query, 150) AS query_preview
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY query_start NULLS LAST;
```

Đây là điểm khởi đầu, không phải toàn bộ chẩn đoán. Nếu `wait_event_type='Lock'`, cần điều tra blocker theo quyền hệ thống phù hợp, không xem VACUUM là cách chữa mọi lock wait.

### 35.2. Phân biệt thời gian statement và commit

Một UPDATE có Execution Time thấp trong EXPLAIN nhưng API request chậm có thể do:

- Waiting for COMMIT flush.
- Synchronous replication ack.
- Network.
- Client transaction management.
- Lock acquisition ở bước khác.

Đo đường đi hoàn chỉnh trước khi thay index, HOT hoặc autovacuum.

---

## 36. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu chính xác |
| --- | --- |
| “UPDATE ghi đè trực tiếp tuple cũ.” | PostgreSQL thường tạo tuple version mới theo MVCC |
| “DELETE xóa ngay mọi byte khỏi disk.” | DELETE đánh dấu theo MVCC; cleanup diễn ra về sau |
| “Sau DELETE, mọi transaction phải không thấy hàng.” | Snapshot cũ hợp lệ vẫn có thể thấy phiên bản trước |
| “Hàng cũ luôn là dead tuple dọn ngay được.” | Có thể còn cần cho snapshot cũ |
| “Dead tuple nghĩa là câu DELETE thất bại.” | Dead tuples là hệ quả bình thường của MVCC |
| “xmin là timestamp tạo hàng.” | xmin là metadata transaction ID, không phải timestamp |
| “xmax khác 0 chắc chắn là DELETE đã commit.” | xmax còn liên quan row locks/trạng thái transaction |
| “ctid là ID ổn định.” | ctid là vị trí tuple version, có thể đổi |
| “SELECT system columns sẽ thấy mọi phiên bản.” | SELECT thường chỉ trả tuple visible theo snapshot |
| “HOT UPDATE không tạo phiên bản mới.” | HOT vẫn tạo heap tuple version mới |
| “HOT nghĩa là không WAL.” | HOT vẫn có WAL/heap work |
| “Cột không index chắc chắn HOT.” | Còn điều kiện cùng page và index dependency |
| “Chỉ index key quan trọng với HOT.” | INCLUDE, expression, partial predicate cũng có thể ảnh hưởng |
| “Đổi một indexed column chỉ sửa một index.” | Non-HOT có thể đòi hỏi nhiều index entries mới |
| “UPDATE SET x=x miễn phí.” | Vẫn có thể tạo tuple, WAL, trigger |
| “VACUUM xóa dữ liệu đã DELETE khỏi mọi snapshot.” | VACUUM phải tôn trọng snapshots còn cần |
| “VACUUM phải chạy trong BEGIN/COMMIT.” | VACUUM thường không chạy được trong explicit transaction block |
| “VACUUM luôn thu nhỏ file về OS.” | Chủ yếu tái sử dụng không gian trong relation |
| “VACUUM FULL chỉ là VACUUM nhanh hơn.” | FULL rewrite và cần lock mạnh, nhiều tài nguyên |
| “ANALYZE dọn dead tuples.” | ANALYZE cập nhật planner stats |
| “Có pruning thì không cần autovacuum.” | VACUUM còn quản lý index cleanup/freeze và các việc khác |
| “n_dead_tup là số tuple chính xác.” | Là ước lượng có độ trễ |
| “n_tup_upd = số hàng đang sống.” | Là bộ đếm update, không phải live row count |
| “Đóng transaction rất lâu không ảnh hưởng ai.” | Có thể giữ snapshot/locks, chặn cleanup |
| “Replica lag luôn khiến dead tuple tăng.” | Có nhiều cơ chế; cần đo slot/feedback/horizon |
| “Replication slot inactive không gây gì.” | Có thể giữ WAL và những horizon cần thiết tùy slot |
| “Không DELETE thì không cần freeze.” | Tuple sống lâu vẫn có nhu cầu xử lý XID age |
| “ROLLBACK không gây ghi hay rác.” | DML đã chạy vẫn có thể sinh tuple/WAL và cleanup |
| “EXPLAIN ANALYZE UPDATE không sửa dữ liệu.” | Nó thực thi DML; phải thử trong lab an toàn |
| “Bảng nhỏ nhưng file lớn chắc chắn là lỗi.” | Có thể chứa free space dự kiến reuse hoặc bloat thực sự |
| “Soft delete làm mất hàng vật lý.” | Soft delete là UPDATE theo mô hình ứng dụng |
| “VACUUM giải quyết lost update.” | Concurrency đúng cần transaction, locks/versioning/constraints |
| “COUNT(*) bằng n_live_tup chính xác.” | COUNT theo snapshot; n_live_tup là estimate |
| “Lệnh DML nhanh nghĩa là COMMIT cũng nhanh.” | WAL flush/replica/network có thể tăng latency |

---

## 37. Bài tập thực hành

### Bài 1 — Vẽ vòng đời phiên bản

Với hàng `(order_id=101, status='NEW')`, hãy vẽ các phiên bản sau hai UPDATE lần lượt sang `PAID` và đổi `note`. Giải thích phiên bản nào visible với snapshot mới và snapshot cũ.

### Bài 2 — Đọc system columns

Chạy:

```sql
SELECT order_id, xmin, xmax, ctid
FROM mvcc_versions_lab.orders
ORDER BY order_id;
```

Sau đó UPDATE `note` của hàng 105 rồi đọc lại. Vì sao không nên lấy `ctid` làm khóa ứng dụng? Vì sao `xmax<>0` không chứng minh hàng bị DELETE đã commit?

### Bài 3 — READ COMMITTED hai session

Chạy thí nghiệm ở mục 8 bằng hai kết nối. A thấy gì khi đọc trước và sau B COMMIT? Điều gì thay đổi nếu B chưa COMMIT?

### Bài 4 — REPEATABLE READ hai session

Chạy thí nghiệm ở mục 9. Vì sao A vẫn thấy `NEW` sau khi B UPDATE/COMMIT? Lúc nào A bắt đầu thấy `PAID`?

### Bài 5 — DELETE và snapshot

Dùng A giữ snapshot REPEATABLE READ trước khi B DELETE hàng 102. A có thể nhìn thấy hàng 102 sau B COMMIT không? Vì sao VACUUM không được dọn mất phiên bản A còn cần?

### Bài 6 — ROLLBACK UPDATE

Thực hiện UPDATE `note='temporary'` rồi ROLLBACK. Vì sao phiên bản đã rollback không trở thành giá trị hiện hành? Tại sao phép thử vẫn có thể sinh WAL/dirty pages?

### Bài 7 — ROLLBACK DELETE

DELETE hàng 103 trong transaction rồi ROLLBACK. Hàng còn tồn tại không? Phân biệt rollback với VACUUM.

### Bài 8 — HOT ứng viên

UPDATE `note` của hàng 105. Vì sao nó có thể HOT? Hai điều kiện quan trọng nào phải đúng? `fillfactor=80` bảo đảm 100% HOT không?

### Bài 9 — Indexed column

UPDATE `customer_id` của hàng 105. Vì sao khả năng HOT thay đổi? Non-HOT có thể làm những index nào cần entry mới?

### Bài 10 — Partial index

Bảng có partial index `WHERE status='PAID'`. UPDATE `status` từ NEW sang PAID tác động ra sao đến index membership? Tại sao đây không giống UPDATE `note`?

### Bài 11 — Update no-op

Viết:

```sql
UPDATE mvcc_versions_lab.orders
SET note = note
WHERE order_id = 106;
```

Giải thích vì sao có thể vẫn sinh phiên bản và WAL. Viết lại dùng `IS DISTINCT FROM` nếu chỉ muốn thay note khi khác giá trị mong muốn.

### Bài 12 — Đếm hàng visible và dead tuple estimate

So `COUNT(*)` với `n_live_tup` và `n_dead_tup` từ `pg_stat_user_tables`. Vì sao ba con số không cần có quan hệ cộng trừ chính xác ở mọi thời điểm?

### Bài 13 — HOT ratio

Tính:

```sql
ROUND(
  100::NUMERIC * n_tup_hot_upd
  / NULLIF(n_tup_upd,0),
  2
)
```

từ `pg_stat_user_tables`. HOT ratio thấp có nghĩa mọi UPDATE đều sai không?

### Bài 14 — VACUUM

Chạy vài UPDATE/DELETE trong lab, kết thúc transaction, sau đó:

```sql
VACUUM (ANALYZE) mvcc_versions_lab.orders;
```

Giải thích tại sao phải kết thúc transaction trước khi VACUUM và vì sao file không nhất thiết thu nhỏ đáng kể.

### Bài 15 — Autovacuum và freeze

Giải thích hai nhiệm vụ: dọn dead tuples và tránh XID wraparound. Vì sao bảng ít UPDATE/DELETE vẫn cần bảo trì?

### Bài 16 — Long-running transaction

Một session REPEATABLE READ giữ snapshot cũ trong một giờ, trong lúc hàng nghìn UPDATE khác được commit. Điều gì có thể xảy ra với khả năng thu hồi tuple versions? Truy vấn `pg_stat_activity` nào giúp điều tra?

### Bài 17 — pg_stat_replication_slots

Đọc `xmin`, `catalog_xmin`, `restart_lsn` từ `pg_replication_slots`. Phân biệt retention horizon của tuple/catalog với vị trí WAL cần giữ. Vì sao không nên drop slot nếu chưa biết consumer?

### Bài 18 — So sánh VACUUM, VACUUM FULL, REINDEX

Từng công cụ nhằm giải quyết vấn đề gì? Công cụ nào yêu cầu rewrite/lock mạnh? Khi index bloat lớn nhưng heap không lớn, phương án nào đáng điều tra?

### Bài 19 — EXPLAIN ANALYZE UPDATE

Trong transaction lab:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS, WAL)
UPDATE mvcc_versions_lab.orders
SET note = 'changed'
WHERE order_id BETWEEN 101 AND 106;

ROLLBACK;
```

Hãy mô tả WAL records, FPI, bytes và Buffers. Vì sao không nên chạy cùng phép thử trên production chỉ vì có ROLLBACK?

### Bài 20 — DELETE theo batch

Viết câu DELETE tối đa 100 hàng CANCELED qua CTE chọn khóa. Giải thích transaction riêng mỗi batch, idempotency và cách dừng khi hết hàng.

### Bài 21 — Bloat sau DELETE lớn

Một bảng vẫn 200 GB sau khi DELETE phần lớn hàng và VACUUM. Hãy nêu ít nhất bốn lời giải thích khả dĩ và cách kiểm tra từng giả thuyết trước khi đề xuất VACUUM FULL.

### Bài 22 — Index-only scan

Vì sao index-only scan vẫn quan tâm visibility map? UPDATE/DELETE liên tục có thể ảnh hưởng heap fetches như thế nào?

### Bài 23 — Soft delete

Một bảng dùng `deleted_at` thay physical DELETE. Về MVCC, thao tác soft delete tạo phiên bản hàng cũ hay xóa hẳn hàng khỏi heap ngay? Vì sao có thể ảnh hưởng HOT?

### Bài 24 — Optimistic concurrency

Thiết kế một UPDATE với `WHERE row_version=expected_version`. Nếu câu UPDATE trả 0 hàng, ứng dụng cần xử lý thế nào? Có nên dùng `ctid` làm version token bền vững không?

### Bài 25 — Workload nhiều cập nhật

Một bảng có `last_seen_at` được UPDATE hàng chục lần mỗi phút. Đề xuất checklist đánh giá nhu cầu index, HOT ratio, fillfactor, autovacuum, write coalescing và audit requirement.

### Bài 26 — Phân biệt bốn tình huống “DELETE rồi vẫn thấy hàng”

Phân loại:

1. Session khác chưa COMMIT DELETE.
2. Session A có snapshot REPEATABLE READ cũ.
3. Ứng dụng đang đọc async standby chưa replay.
4. Ứng dụng thực hiện soft delete.

Giải thích vì sao không thể dùng một câu `VACUUM` để giải quyết cả bốn.

---

## 38. Checklist đánh giá UPDATE/DELETE trong hệ thống thật

| Câu hỏi | Điều cần xác minh |
| --- | --- |
| Lệnh là UPDATE hay DELETE? | Tạo tuple version mới hay đánh dấu xóa |
| Có bao nhiêu hàng thực sự bị tác động? | WHERE, RETURNING, row count |
| Có thay đổi indexed column không? | Key, INCLUDE, expression, predicate |
| Có cơ hội HOT không? | Không đổi indexed dependency, cùng heap page |
| Fillfactor có phù hợp workload? | Dung lượng page, tỷ lệ UPDATE |
| Có UPDATE không đổi giá trị? | IS DISTINCT FROM nếu nghiệp vụ cho phép |
| Có trigger, FK hay cascade? | Công việc ghi gián tiếp |
| Có snapshot cũ còn hoạt động? | xact_start/backend_xmin |
| Có transaction idle lâu? | Connection pool, timeout |
| Có replication slot giữ horizon? | xmin/catalog_xmin/restart_lsn |
| Có standby feedback? | Quy tắc giữ tuple và nguy cơ bloat |
| DEAD tuple estimate tăng? | pg_stat_user_tables |
| HOT ratio có ý nghĩa? | n_tup_hot_upd/n_tup_upd, scope của stats |
| Autovacuum chạy đúng? | last_autovacuum, thresholds, logs |
| Có wraparound risk? | age(relfrozenxid), freeze policy |
| Table hay index tăng bất thường? | pg_table_size, pg_indexes_size theo thời gian |
| Dung lượng trống trong file có thể reuse? | Không đồng nhất free space với disk đã trả về OS |
| Có cần VACUUM FULL? | Rewrite/lock/disk/HA risk |
| Có cần REINDEX? | Xem index bloat và lock |
| Có nên DELETE theo batch? | WAL, locks, transaction, restart |
| Có thể dùng partition retention? | Thiết kế thời gian dài hạn |
| EXPLAIN DML an toàn chưa? | ANALYZE chạy thật; chỉ lab |
| Có so sánh cùng điều kiện? | Cache, checkpoint, row count, writer khác |
| Có data consistency issue? | Locks, optimistic version, retry |
| Replica có stale? | Replication lag vs snapshot cũ |
| Có soft delete? | UPDATE logic vs physical DELETE |
| Có audit/retention requirement? | Không bỏ ghi hoặc xóa sai lịch sử |
| Có backup và phục hồi? | PITR/base backup, test restore |
| Có ngưỡng dừng an toàn? | WAL/disk/lag/latency/lock waits |

## Kết luận

Trong PostgreSQL, `UPDATE` và `DELETE` được hiểu đúng nhất khi đặt trong mô hình **MVCC — nhiều phiên bản hàng cùng tồn tại theo nhu cầu của các snapshot**.

- **UPDATE** thường tạo một phiên bản tuple mới và đánh dấu phiên bản cũ đã bị thay thế. Snapshot cũ vẫn có thể nhìn thấy phiên bản trước, trong khi snapshot mới thấy phiên bản sau khi transaction commit.
- **DELETE** đánh dấu phiên bản hiện có bị xóa về mặt logic. Nó không bảo đảm dữ liệu vật lý hoặc index entry được xóa tức thì.
- **Old tuple version** không tự đồng nghĩa **dead tuple có thể dọn**. PostgreSQL phải bảo vệ những phiên bản còn cần cho transaction, snapshot hoặc horizon liên quan.
- **HOT update** có thể giảm công việc index khi cột được sửa không ảnh hưởng index dependency và tuple mới nằm cùng heap page. Nó vẫn tạo heap version và WAL.
- **Pruning, VACUUM và autovacuum** giúp cleanup, tái sử dụng không gian và chống XID wraparound. Ordinary VACUUM không mặc định thu nhỏ mọi file về hệ điều hành.
- **Long-running transactions**, một số retention horizons do replication và configuration có thể làm các phiên bản cũ bị giữ lâu hơn, tăng bloat.
- **System columns và stats** như `xmin`, `xmax`, `ctid`, `n_dead_tup` là công cụ để hiểu/điều tra, không phải API nghiệp vụ bảo đảm vĩnh viễn hay những phép đếm tuyệt đối.
- **Hiệu năng UPDATE/DELETE** còn phụ thuộc index, trigger, WAL, locks, I/O, replication và thiết kế transaction. Không tối ưu chỉ bằng một chỉ số.

Khi phân biệt rõ **“không còn visible”**, **“không còn cần cho snapshot”** và **“đã được thu hồi để tái sử dụng”**, bạn sẽ giải thích chính xác vòng đời của hàng trong PostgreSQL, tránh những kết luận sai sau UPDATE/DELETE và biết sử dụng VACUUM cùng các công cụ giám sát một cách an toàn, có cơ sở.
