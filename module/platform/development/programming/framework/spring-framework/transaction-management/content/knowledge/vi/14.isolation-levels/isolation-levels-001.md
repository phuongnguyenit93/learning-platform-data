# Dirty read, non-repeatable read và phantom read trong Spring Transaction Management

## 1. Tại sao cùng một câu SELECT lại có thể cho kết quả khác?

Khi hai hoặc nhiều transaction hoạt động đồng thời, việc **đọc dữ liệu** không chỉ phụ thuộc vào SQL được viết đúng hay sai. Kết quả còn phụ thuộc vào thời điểm transaction khác sửa/commit dữ liệu, mức cô lập (*isolation level*) của transaction đang đọc, và cơ chế triển khai của database (MVCC, locking, snapshots).

Ba hiện tượng nền tảng cần phân biệt:

- **Dirty read (đọc bẩn):** đọc thấy dữ liệu **chưa commit** của transaction khác; dữ liệu đó sau này có thể bị rollback.
- **Non-repeatable read (đọc không lặp lại):** đọc **cùng một hàng** hai lần trong một transaction nhưng nhận giá trị khác nhau vì transaction khác đã commit cập nhật/xóa hàng đó giữa hai lần đọc.
- **Phantom read (đọc bóng ma):** thực thi lại **cùng truy vấn theo điều kiện** và thấy **tập hàng thỏa điều kiện thay đổi** do transaction khác đã commit chèn/xóa/sửa những hàng liên quan.

Những hiện tượng này làm thay đổi quyết định nghiệp vụ: kiểm tra tồn kho rồi tính tiền, tính tổng số đơn chưa xử lý, xác minh hạn mức rồi ghi giao dịch, v.v. Chỉ thêm `@Transactional` mà **không hiểu isolation** không bảo đảm toàn bộ các lần đọc trong method quan sát cùng một trạng thái database.

Bài này giúp bạn:

1. Tự vẽ timeline cho ba bất thường, nhận ra **ai chưa commit, ai đã commit và câu truy vấn nào đọc lại**.
2. Hiểu mức bảo đảm tối thiểu của các mức cô lập SQL và vì sao bảng lý thuyết **khác** hành vi thật ở PostgreSQL/MySQL.
3. Cấu hình `@Transactional(isolation = ...)` trong Spring và biết giới hạn của propagation, proxy, connection.
4. Chạy ví dụ **Java 17 + Spring Boot + PostgreSQL** dùng hai transaction phối hợp bằng `CountDownLatch` để nhìn thấy non-repeatable read/phantom tại `READ_COMMITTED`, và sự ổn định tại PostgreSQL `REPEATABLE_READ`.
5. Tránh các ngộ nhận về dirty read, MVCC, `readOnly`, commit, lock và `SERIALIZABLE`.

> **Ranh giới:** Đây là các hiện tượng do **đồng thời giữa transaction**. Đọc lại một hàng sau chính lệnh `UPDATE` của transaction hiện tại có thể thấy giá trị mới; đó là việc transaction nhìn thấy **writes của chính nó**, không phải non-repeatable read do transaction khác.

## 2. Một số thuật ngữ cần nắm trước

| Thuật ngữ | Ý nghĩa trong bài |
| --- | --- |
| Transaction T1/T2 | Hai phạm vi công việc SQL có thể chạy song song trên các connection khác nhau |
| `BEGIN` | Mở một transaction (hoặc thiết lập ranh giới bắt đầu, tùy DB/driver) |
| `COMMIT` | Yêu cầu database xác nhận các thay đổi còn lại của transaction |
| `ROLLBACK` | Hủy thay đổi chưa commit của transaction |
| Isolation level | Quy tắc/khả năng nhìn thấy trạng thái dữ liệu và xử lý xung đột khi các transaction chạy đồng thời |
| Snapshot | Ảnh chụp logic về những phiên bản dữ liệu mà một truy vấn/transaction được phép đọc |
| MVCC | Multi-Version Concurrency Control: lưu/đọc nhiều phiên bản để hỗ trợ concurrency |
| Locking read | Đọc có yêu cầu khóa phù hợp, chẳng hạn `SELECT ... FOR UPDATE` trong một số DB |
| Predicate | Điều kiện xác định tập hàng, ví dụ `WHERE status = 'OPEN'` |
| Serialization anomaly | Một kết quả nhiều transaction commit không tương đương với **bất kỳ** thứ tự chạy lần lượt nào |

**Isolation không đồng nghĩa “khóa cả database”.** Với PostgreSQL/MySQL InnoDB, nhiều hành vi đọc được triển khai bằng MVCC; isolation cao hơn không nhất thiết biến mọi SELECT thành khóa chặn mọi writer. `SERIALIZABLE` có thể dùng phát hiện xung đột rồi abort một transaction, thay vì cho tất cả transaction chạy tuần tự về mặt thời gian thực.

## 3. Dirty read: nhìn thấy dữ liệu chưa commit của người khác

Giả sử tài khoản ID 1 có số dư đã commit là **100**.

### 3.1. Timeline

```text
Thời điểm     T1 (người ghi)                         T2 (người đọc)
---------     -----------------------------------    --------------------------
t0            (DB đang có balance=100)
t1            BEGIN
t2            UPDATE account SET balance=900
              WHERE id=1
              -- 900 CHƯA COMMIT
t3                                                 BEGIN (READ UNCOMMITTED)
t4                                                 SELECT balance ... -> 900 (*)
t5            ROLLBACK
              -- DB trở về 100
t6                                                 T2 đã dùng giá trị 900
t7                                                 COMMIT/ROLLBACK T2
```

Dấu `(*)` chỉ xảy ra nếu **database và mức isolation thật sự cho phép đọc dirty value**. T2 đã sử dụng giá trị 900 chưa từng được commit; nếu dùng nó để quyết định chuyển tiền/hạn mức, quyết định đó dựa trên một trạng thái không bền vững.

**Cốt lõi của dirty read:** T2 đọc **trước khi T1 commit**. Nếu T1 đã commit rồi T2 đọc lại và thấy 900, đó **không** phải dirty read, dù giá trị khác với lần trước.

### 3.2. Vì sao rollback của T1 không “sửa lại” những quyết định T2 đã thực hiện?

`ROLLBACK` hoàn tác phần SQL chưa commit của T1, nhưng không tự thu hồi mọi dữ liệu mà T2 đã chép sang biến Java, cache, HTTP response, event hoặc log. Một quyết định tính phí dựa trên 900 có thể đã gửi đi trước khi T1 rollback. Vì thế đọc dirty value làm ứng dụng dễ đưa ra hành vi nghiệp vụ sai ngay cả khi database cuối cùng giữ lại số dư 100.

### 3.3. Có thể dùng PostgreSQL để tái hiện dirty read không?

**Không.** PostgreSQL hiện đại nhận lệnh yêu cầu `READ UNCOMMITTED` nhưng thực thi như `READ COMMITTED`. T2 sẽ **không** thấy dữ liệu chưa commit của T1; trong timeline trên, một SELECT thông thường của T2 trả về 100 chứ không phải 900.

Vì vậy, một test “bật `Isolation.READ_UNCOMMITTED` trong Spring + PostgreSQL mà không thấy dirty read” **không phải bằng chứng Spring bỏ qua annotation**; đây là semantics của PostgreSQL.

Nếu cần thử hiện tượng dirty read, hãy dùng DB thực sự hỗ trợ nó, ví dụ **MySQL InnoDB** với `READ UNCOMMITTED` và hai connection/session. Không nên dùng mức này cho những quyết định cần dữ liệu đáng tin.

### 3.4. Dirty read khác dirty write

- **Dirty read:** T2 **đọc** thay đổi chưa commit của T1.
- **Dirty write:** T2 **ghi đè** thay đổi chưa commit của T1 trước khi T1 kết thúc, là một tình huống khác và thường bị DB chặn bằng cơ chế khóa.

Không lấy “transaction bị khóa khi UPDATE” làm kết luận rằng dirty read nhất thiết được phép hay bị chặn. Đọc và ghi có thể có chính sách đồng thời khác nhau.

## 4. Non-repeatable read: cùng một hàng, hai giá trị đã commit khác nhau

Tình huống: T1 đọc số dư ID 1 là 100. Trong khi T1 **vẫn đang mở**, T2 sửa số dư thành 200 rồi **commit**. T1 đọc lại **đúng cùng một hàng** và nhận 200.

### 4.1. Timeline chuẩn

```text
Thời điểm     T1 (đọc)                                T2 (ghi)
---------     -------------------------------------    ------------------------
t0            (balance=100 đã commit)
t1            BEGIN ISOLATION LEVEL READ COMMITTED
t2            SELECT balance WHERE id=1 -> 100
t3                                                     BEGIN
t4                                                     UPDATE ... balance=200
t5                                                     COMMIT
t6            SELECT balance WHERE id=1 -> 200
t7            COMMIT
```

T1 chưa kết thúc, nhưng **hai câu SELECT giống nhau** cho kết quả khác nhau do **transaction khác đã commit** ở giữa. Đây là non-repeatable read.

Điều kiện nhận diện:

1. Có ít nhất hai lần đọc cùng một dữ liệu định danh (ví dụ cùng `WHERE id=1`) trong **một transaction T1**.
2. T2 commit sự thay đổi trong khoảng giữa hai lần đọc.
3. T1 thấy phiên bản khác khi đọc lại.

Nếu T1 commit sau lần SELECT đầu rồi mở transaction khác mới đọc lại, đó là **hai transaction độc lập**, không phải non-repeatable read bên trong một transaction.

### 4.2. Hệ quả nghiệp vụ

Một luồng:

```text
T1: đọc balance = 100
T1: kiểm tra đủ tiền để chi 80
T2: trừ 50 và commit, balance = 50
T1: đọc balance lần nữa = 50
```

Nếu T1 tính toán dựa vào lần đọc 100 nhưng vẫn ghi theo giả định cũ, có thể xảy ra lỗi xử lý nghiệp vụ hoặc lost update tùy cách viết SQL và locking. **Non-repeatable read và lost update là hai hiện tượng khác nhau**; nâng isolation không thay thế atomic SQL update, optimistic locking/version check, hoặc cơ chế xử lý xung đột thích hợp.

### 4.3. READ_COMMITTED trong PostgreSQL

Ở PostgreSQL, mỗi câu lệnh dưới `READ COMMITTED` dùng một snapshot nhìn thấy các thay đổi đã commit **trước khi câu lệnh bắt đầu**, cùng với writes của chính transaction. Sau khi T2 commit, **câu SELECT mới** của T1 có thể nhìn thấy giá trị 200. Nhưng nếu T2 chưa commit khi SELECT thứ hai bắt đầu, câu SELECT thường tiếp tục thấy giá trị đã commit trước đó.

Không diễn giải “READ_COMMITTED” thành “mọi SELECT trong cùng transaction đọc một snapshot duy nhất”. Nó chỉ không đọc dữ liệu chưa commit của transaction khác; non-repeatable read và phantom vẫn có thể xảy ra.

## 5. Phantom read: cùng điều kiện, tập hàng khác nhau

Giả sử bảng `orders` đang có **1** đơn hàng ở trạng thái `OPEN`.

T1 cần đếm số đơn đang mở:

```sql
SELECT COUNT(*) FROM orders WHERE status = 'OPEN';
```

Trong khi T1 chưa kết thúc, T2 tạo thêm một đơn `OPEN` và commit:

```sql
INSERT INTO orders(id, status) VALUES (2, 'OPEN');
```

T1 chạy lại câu SELECT theo cùng điều kiện.

### 5.1. Timeline

```text
Thời điểm     T1 (đọc theo điều kiện)                  T2 (chèn)
---------     -------------------------------------    ------------------------
t0            (id=1, status='OPEN' đã commit)
t1            BEGIN ISOLATION LEVEL READ COMMITTED
t2            COUNT(*) WHERE status='OPEN' -> 1
t3                                                     BEGIN
t4                                                     INSERT (id=2,'OPEN')
t5                                                     COMMIT
t6            COUNT(*) WHERE status='OPEN' -> 2
t7            COMMIT
```

T1 **không đổi điều kiện WHERE** nhưng tập kết quả thay đổi do transaction khác commit thêm một hàng thỏa điều kiện. Hàng mới đó thường được gọi là **phantom row**.

Cách quan sát tốt hơn `COUNT(*)` là hai lần thực thi:

```sql
SELECT id FROM orders WHERE status='OPEN' ORDER BY id;
```

Lần 1 trả tập `[1]`, lần 2 trả tập `[1, 2]` trong cùng T1. Nếu một hàng bị xóa hoặc chuyển trạng thái khiến nó không còn khớp predicate, tập cũng có thể giảm.

### 5.2. Phân biệt với non-repeatable read

| Câu hỏi | Non-repeatable read | Phantom read |
| --- | --- | --- |
| Cùng thứ gì được đọc lại? | **Một hàng đã được xác định** (id cụ thể) | **Một truy vấn theo điều kiện** trả về tập hàng |
| Thay đổi điển hình từ T2 | `UPDATE account SET balance=200 WHERE id=1` | `INSERT order(status='OPEN')`; hoặc DELETE/UPDATE làm đổi tập khớp |
| Kết quả dễ quan sát | `balance: 100 → 200` | `COUNT(*) 1 → 2`, hoặc danh sách ID thay đổi |
| Câu truy vấn minh họa | `SELECT balance WHERE id=1` | `SELECT id WHERE status='OPEN'` |
| Đặc điểm chính | Giá trị của hàng cũ bị thay đổi giữa hai lần đọc | Tập hàng thỏa predicate bị thay đổi |

Một query theo predicate cũng có thể chứng kiến giá trị hàng hiện hữu thay đổi; lúc đó hiện tượng có thể chồng lấn về quan sát. Để học và test riêng hai loại, dùng **một hàng định danh cho non-repeatable** và **một hàng chèn mới cho phantom** như các ví dụ trên.

### 5.3. Vì sao phantom nguy hiểm?

Các thao tác như “đảm bảo không quá 10 đơn đang mở”, “không có booking trùng khoảng thời gian”, “không có invoice chưa thanh toán” thường dựa trên **kết quả theo điều kiện**, không phải chỉ đọc một ID. Nếu kiểm tra và chèn theo assumption mà không có constraint/locking/serialization phù hợp, hai transaction có thể cùng thấy một tập hàng hợp lệ rồi đều ghi, tạo vi phạm nghiệp vụ.

Đây là nơi cần đánh giá **constraint ở database**, transaction isolation, row/range/predicate locking hoặc optimistic concurrency. Không coi chỉ chuyển sang `REPEATABLE_READ` là luôn đủ chống mọi **write skew** hoặc bảo đảm invariant trên mọi DB.

## 6. Bảng isolation theo **mức bảo đảm tối thiểu của chuẩn SQL**

Bốn tên mức cô lập và ba hiện tượng có thể tóm tắt như sau:

| Mức cô lập theo SQL | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `READ UNCOMMITTED` | **Có thể** | **Có thể** | **Có thể** |
| `READ COMMITTED` | **Không** | **Có thể** | **Có thể** |
| `REPEATABLE READ` | **Không** | **Không** | **Có thể theo chuẩn** |
| `SERIALIZABLE` | **Không** | **Không** | **Không** |

**Đọc đúng bảng:** “Có thể” nghĩa là **chuẩn cho phép hiện tượng**, không có nghĩa mỗi DB đều phải tạo ra hiện tượng đó hoặc mọi phiên test đều tái hiện được. Một DB được quyền **cung cấp bảo đảm mạnh hơn mức tối thiểu**. Ngoài ba hiện tượng này còn có write skew, serialization anomaly và những tương tác khóa/đọc khác; bảng trên **không phải phép chứng minh** mọi nghiệp vụ đã serializable.

Một cách nhớ:

- `READ UNCOMMITTED`: được phép thấy giá trị chưa commit nếu DB triển khai đúng level này.
- `READ COMMITTED`: loại dirty read, nhưng hai SELECT khác statement có thể thấy phiên bản đã commit mới.
- `REPEATABLE READ`: ổn định khi đọc lại hàng đã đọc, nhưng **chuẩn SQL cho phép** phantom; hành vi DB có thể nghiêm ngặt hơn.
- `SERIALIZABLE`: các transaction commit thành công phải tương đương một thứ tự chạy tuần tự hợp lệ; DB có thể chặn, chờ hoặc abort transaction khi có xung đột.

Với Spring, `Isolation.READ_COMMITTED` và các enum tương tự là **yêu cầu gửi tới transaction manager/driver**; mức thật sự hỗ trợ và hành vi phụ thuộc database.

## 7. Hành vi **thực tế** của PostgreSQL và MySQL InnoDB

### 7.1. PostgreSQL: READ_UNCOMMITTED được đối xử như READ_COMMITTED

PostgreSQL hỗ trợ bốn tên mức yêu cầu nhưng thực tế triển khai ba mức phân biệt:

| Mức yêu cầu trong PostgreSQL | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `READ UNCOMMITTED` (được xử lý như `READ COMMITTED`) | Không | Có thể | Có thể |
| `READ COMMITTED` | Không | Có thể | Có thể |
| `REPEATABLE READ` | Không | Không | **Không** |
| `SERIALIZABLE` | Không | Không | Không; ngăn thêm serialization anomalies |

Đặc biệt, PostgreSQL `REPEATABLE READ` dựa trên snapshot của **câu lệnh không điều khiển transaction đầu tiên** trong giao dịch. Các câu SELECT thường về sau nhìn thấy cùng snapshot đó (cộng thêm những thay đổi do chính transaction thực hiện), nên **phantom do transaction khác commit không xuất hiện** với kiểu đọc trong bài.

Điều này **không mâu thuẫn** bảng chuẩn: chuẩn chỉ quy định tối thiểu; PostgreSQL được quyền mạnh hơn. Dù vậy, `REPEATABLE READ` của PostgreSQL **vẫn có thể có serialization anomalies** như write skew. Khi yêu cầu mọi transaction commit tương đương chạy tuần tự, cân nhắc `SERIALIZABLE` và chuẩn bị xử lý `serialization_failure`/retry.

Mức mặc định của PostgreSQL là `READ COMMITTED`. Với Spring, `Isolation.DEFAULT` thường đồng nghĩa dùng mặc định của DB/transaction manager, **không mặc định là SERIALIZABLE hoặc REPEATABLE_READ**.

### 7.2. MySQL InnoDB: snapshot read và locking read không giống nhau

InnoDB mặc định thường ở `REPEATABLE READ`. Với **plain consistent SELECT** (non-locking read), các lần đọc trong cùng transaction dùng snapshot được thiết lập bởi lần consistent read đầu tiên; các phantom do insert của transaction khác thường **không xuất hiện trong chuỗi plain SELECT** đó.

Tuy nhiên, `SELECT ... FOR UPDATE`/`FOR SHARE`, `UPDATE` và `DELETE` là các thao tác có semantics khóa và/current read khác. InnoDB dùng **next-key locks/gap locks** ở các trường hợp range locking tại `REPEATABLE READ` để hạn chế inserts gây phantom theo phạm vi khóa. Nếu trộn consistent non-locking reads với locking reads/DML trong cùng transaction, có thể nhìn thấy những trạng thái dữ liệu không cùng một snapshot logic.

Vì vậy, không thể nhìn bảng chuẩn rồi khẳng định chắc chắn “MySQL REPEATABLE READ luôn thấy phantom”, cũng không nên ngược lại khẳng định “mọi truy vấn MySQL REPEATABLE READ hoạt động giống nhau và không thể có vấn đề đồng thời khác”. Phải phân tích **kiểu SELECT, chỉ mục, predicate, khóa và version MySQL**.

### 7.3. Tổng kết điểm khác biệt

| Điểm so sánh | PostgreSQL | MySQL InnoDB |
| --- | --- | --- |
| Mức mặc định phổ biến | `READ COMMITTED` | `REPEATABLE READ` |
| `READ UNCOMMITTED` | Được xử lý như `READ COMMITTED` | Có hỗ trợ mức `READ UNCOMMITTED` thực sự |
| `REPEATABLE READ`, plain SELECT | Snapshot transaction ổn định; không thấy phantom từ T2 | Snapshot của first consistent read; thường không thấy phantom từ T2 |
| Khóa/locking read | Tùy isolation và lệnh, có thể chờ/khác snapshot | Next-key/gap locks quan trọng ở range locking |
| `SERIALIZABLE` | Có cơ chế phát hiện xung đột, có thể abort với SQLSTATE `40001` | Semantics locking/serialization riêng, có thể chặn/timeout/deadlock |

Không thay thế kiểm thử trên database production bằng một kết luận chỉ dựa trên tên `Isolation` của Spring hoặc kết quả trên H2.

## 8. Thực hành bằng hai cửa sổ psql trên PostgreSQL

Các bước sau dành cho **database thực hành riêng** và **hai connection/session khác nhau**. Đừng chạy các câu reset dữ liệu trong môi trường có dữ liệu cần bảo toàn.

Giả sử PostgreSQL đã chạy, mở **Session A** và **Session B** (hai terminal/psql riêng). Chạy setup **một lần khi cả hai không còn transaction đang mở**:

```sql
CREATE TABLE IF NOT EXISTS isolation_accounts (
    id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS isolation_orders (
    id INTEGER PRIMARY KEY,
    state VARCHAR(12) NOT NULL
);

TRUNCATE TABLE isolation_accounts, isolation_orders;

INSERT INTO isolation_accounts(id, balance) VALUES (1, 100);
INSERT INTO isolation_orders(id, state) VALUES (1, 'OPEN');
```

Đây là SQL **PostgreSQL** cho một lab sandbox; `TRUNCATE` xóa mọi hàng ở hai bảng được chỉ định. Với DB có khóa ngoại, thứ tự và quy tắc truncate khác; không chạy tùy tiện trên DB đang sử dụng.

### 8.1. Non-repeatable read ở READ COMMITTED

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance FROM isolation_accounts WHERE id = 1;
-- 100
```

Giữ A đang mở. **Session B:**

```sql
BEGIN;
UPDATE isolation_accounts SET balance = 200 WHERE id = 1;
COMMIT;
```

Quay về **Session A:**

```sql
SELECT balance FROM isolation_accounts WHERE id = 1;
-- 200
COMMIT;
```

A đã đọc cùng ID 1 hai lần trong cùng transaction, cho kết quả 100 rồi 200. Điều kiện thiết yếu là B commit **giữa hai SELECT**.

### 8.2. Phantom read ở READ COMMITTED

Trước test, reset bảng order trong **một session không có transaction đang mở**:

```sql
TRUNCATE TABLE isolation_orders;
INSERT INTO isolation_orders(id, state) VALUES (1, 'OPEN');
```

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;
SELECT id FROM isolation_orders
WHERE state = 'OPEN' ORDER BY id;
-- id = 1
```

**Session B:**

```sql
BEGIN;
INSERT INTO isolation_orders(id, state) VALUES (2, 'OPEN');
COMMIT;
```

**Session A:**

```sql
SELECT id FROM isolation_orders
WHERE state = 'OPEN' ORDER BY id;
-- id = 1, 2
COMMIT;
```

A thấy một **hàng mới thỏa cùng WHERE**, minh họa phantom read. Có thể thay câu SELECT bằng `COUNT(*)` để thấy 1 rồi 2.

### 8.3. REPEATABLE READ giữ snapshot cũ

Reset dữ liệu trước khi bắt đầu:

```sql
TRUNCATE TABLE isolation_accounts, isolation_orders;
INSERT INTO isolation_accounts(id, balance) VALUES (1, 100);
INSERT INTO isolation_orders(id, state) VALUES (1, 'OPEN');
```

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM isolation_accounts WHERE id = 1;
-- 100
SELECT COUNT(*) FROM isolation_orders WHERE state = 'OPEN';
-- 1
```

**Session B:**

```sql
BEGIN;
UPDATE isolation_accounts SET balance = 200 WHERE id = 1;
INSERT INTO isolation_orders(id, state) VALUES (2, 'OPEN');
COMMIT;
```

**Session A tiếp tục:**

```sql
SELECT balance FROM isolation_accounts WHERE id = 1;
-- Vẫn 100
SELECT COUNT(*) FROM isolation_orders WHERE state = 'OPEN';
-- Vẫn 1
COMMIT;
```

Sau khi A commit và **bắt đầu một query/transaction mới**, có thể thấy `balance=200`, `COUNT=2`. PostgreSQL `REPEATABLE READ` không có nghĩa cả database không đổi: B **đã commit thật**, nhưng snapshot của A không tự tiến lên để đọc phiên bản B vừa commit.

### 8.4. Thử READ UNCOMMITTED trên PostgreSQL

Reset balance về 100 và dùng hai session:

**B:**

```sql
BEGIN;
UPDATE isolation_accounts SET balance = 900 WHERE id = 1;
-- Chưa COMMIT/ROLLBACK.
```

**A:**

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;
SELECT balance FROM isolation_accounts WHERE id = 1;
-- PostgreSQL trả giá trị đã commit trước UPDATE của B, ví dụ 100.
COMMIT;
```

**B:**

```sql
ROLLBACK;
```

Bài này cố ý minh họa **không có dirty read ở PostgreSQL**, không phải ví dụ dirty read thành công. Để tái hiện dirty read thật, cần loại database có semantics khác.

## 9. Cấu hình Spring `@Transactional(isolation = ...)`

Trong Spring, enum `org.springframework.transaction.annotation.Isolation` gồm:

```java
Isolation.DEFAULT
Isolation.READ_UNCOMMITTED
Isolation.READ_COMMITTED
Isolation.REPEATABLE_READ
Isolation.SERIALIZABLE
```

Ví dụ cấu hình service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountQueryService {

    @Transactional(
        isolation = Isolation.READ_COMMITTED,
        readOnly = true
    )
    public void readLatestCommittedValues() {
        // JdbcTemplate hoặc JPA truy vấn trong transaction này.
    }

    @Transactional(
        isolation = Isolation.REPEATABLE_READ,
        readOnly = true
    )
    public void readConsistentSnapshot() {
        // Các lần đọc theo cùng snapshot, tùy DB implementation.
    }
}
```

Đây là một **đoạn minh họa**, không phải một chương trình độc lập; muốn chạy phải khai bean và code truy cập dữ liệu. `isolation` được áp dụng khi **một transaction vật lý mới được tạo**, phụ thuộc transaction manager và driver/database.

### 9.1. `Isolation.DEFAULT` là gì?

`@Transactional` mặc định:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.DEFAULT
)
```

`DEFAULT` không có nghĩa tự động chọn `READ_COMMITTED` hay `SERIALIZABLE` cho tất cả DB. Nó yêu cầu dùng isolation mặc định của resource/transaction manager. PostgreSQL thường mặc định `READ_COMMITTED`; InnoDB thường mặc định `REPEATABLE READ`.

Trong dự án cần behavior ổn định qua nhiều engine, cân nhắc khai rõ level quan trọng tại service boundary và test trên DB thực tế. Vẫn phải kiểm tra DB có hỗ trợ level được yêu cầu, vì `@Transactional` **không thể ép một driver/DB không hỗ trợ behavior đó**.

### 9.2. Một transaction trong outer, inner yêu cầu level khác

```java
@Service
public class OuterService {
    private final InnerService inner;

    public OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void outer() {
        inner.inner();
    }
}

@Service
public class InnerService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void inner() {
        // ...
    }
}
```

Với `REQUIRED`, inner thường **tham gia transaction đã có**, nên không được mở transaction vật lý SERIALIZABLE mới chỉ vì annotation của inner. Mặc định Spring có thể cho tham gia theo isolation của outer. Nếu muốn từ chối cấu hình isolation không tương thích, với manager thích hợp có thể bật `setValidateExistingTransaction(true)` để **phát hiện mismatch**.

`REQUIRES_NEW` mở transaction riêng và có thể áp dụng isolation mới, nhưng làm thay đổi ranh giới commit/rollback, số connection cần dùng và atomicity. Không sử dụng nó chỉ để che một sai sót về thiết kế service.

### 9.3. Proxy, thread và transaction manager

- Với Spring AOP proxy mode, lời gọi phải đi **qua Spring-managed proxy** để advice `@Transactional` kích hoạt. `this.someTransactionalMethod()` trong cùng bean thường không tạo transaction advice mới.
- Với JDBC imperative, transaction gắn với thread; một `ExecutorService`/`new Thread` bên trong method không tự mang transaction của thread gọi sang thread mới. Trong ví dụ Java bên dưới, **mỗi thread gọi một Spring-managed service method**, có transaction riêng.
- Phải có `PlatformTransactionManager` cho đúng `DataSource` hoặc JPA/EntityManager. Một annotation không tạo transaction nếu không có infrastructure.
- `@Transactional(readOnly=true)` khác `isolation=...`: read-only là hint/setting của transaction, **không** có nghĩa snapshot luôn cố định hoặc SQL ghi sẽ bị cấm ở mọi driver.
- Với JPA/Hibernate, persistence context/first-level cache có thể che một non-repeatable read ở **cùng managed entity** ngay cả khi database ở READ_COMMITTED; muốn test **semantics của database**, dùng JDBC hoặc chủ động quản lý flush/clear/refresh và hiểu query.
- Phương thức đánh dấu transaction trả về/throw exception có các rollback rules riêng; isolation không nói “có exception thì rollback” hay ngược lại.

## 10. Ví dụ Java 17 chạy được: hai transaction được đồng bộ rõ thứ tự

Ta viết một project Spring Boot nhỏ dùng **PostgreSQL**, không chọn H2 để suy đoán behavior của PostgreSQL. Bài tập thực thi **hai lần** trên cùng database sandbox, lần lượt với `READ_COMMITTED` và `REPEATABLE_READ`.

Mỗi lần chạy kịch bản:

1. Reset hai bảng demo về account balance=100, một order OPEN.
2. Thread reader bắt đầu transaction, đọc account balance và số order OPEN, rồi báo đã đọc xong.
3. Thread coordinator gọi writer service; writer thực hiện UPDATE balance=200 và INSERT order OPEN trong một transaction **khác**, commit khi method proxy trả về.
4. Coordinator báo writer đã commit; reader tiếp tục đọc lại **trong transaction ban đầu**.
5. In hai cặp giá trị. Với PostgreSQL RC: `100→200` và `1→2`. Với RR: `100→100` và `1→1`.

Thay vì `Thread.sleep(500)` (không bảo đảm thứ tự), dùng `CountDownLatch` để không phụ thuộc vào tốc độ CPU. Demo giả định chỉ nó đang chỉnh sửa hai bảng trong một database local riêng.

### 10.1. Cấu trúc file

```text
isolation-anomalies-lab/
├── build.gradle
├── settings.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/isolation/
    │   ├── IsolationApplication.java
    │   ├── ReaderService.java
    │   └── WriterService.java
    └── resources/
        └── application.yml
```

**`settings.gradle`:**

```groovy
rootProject.name = 'isolation-anomalies-lab'
```

**`build.gradle`:** Bộ phiên bản cố định **Java 17 + Spring Boot 3.3.13** để ví dụ tái lập; không hàm ý đây là bản mới nhất.

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot tự quản lý version của JDBC starter, HikariCP và PostgreSQL driver qua dependency management; không cần khai `spring-tx` thủ công. Chúng ta dùng `JdbcTemplate` để đọc giá trị DB trực tiếp, không bị persistence context của JPA cache.

### 10.2. Chuẩn bị PostgreSQL riêng cho demo

Nếu có Docker và cổng 55432 trên máy chưa bị sử dụng:

```bash
docker run -d --name isolation-lab-pg \
  -e POSTGRES_DB=isolab \
  -e POSTGRES_USER=isolab \
  -e POSTGRES_PASSWORD=local_only \
  -p 55432:5432 postgres:16
```

Trên PowerShell có thể nhập một dòng:

```powershell
docker run -d --name isolation-lab-pg -e POSTGRES_DB=isolab -e POSTGRES_USER=isolab -e POSTGRES_PASSWORD=local_only -p 55432:5432 postgres:16
```

Kiểm tra server:

```bash
docker exec isolation-lab-pg pg_isready -U isolab -d isolab
```

Đây là mật khẩu **chỉ dùng trên máy thực hành**, không dùng cho production. Container ví dụ không mount persistent volume; khi xóa container có thể mất dữ liệu, phù hợp với lab nhưng không dành cho dữ liệu thật.

**`src/main/resources/application.yml`:**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:postgresql://localhost:55432/isolab"
    username: ${DB_USER:isolab}
    password: ${DB_PASSWORD:local_only}
    hikari:
      maximum-pool-size: 5
```

Pool size 5 đủ cho ít nhất hai connection cần chạy song song trong demo. Đặt host/port/user/password theo môi trường của bạn nếu không dùng Docker. Không hardcode thông tin production trong YAML.

### 10.3. ReaderService: đọc hai lần trong **cùng transaction**

**`src/main/java/demo/isolation/ReaderService.java`:**

```java
package demo.isolation;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReaderService {
    private final JdbcTemplate jdbc;

    public ReaderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record Observation(
        int firstBalance,
        long firstOpenOrders,
        int secondBalance,
        long secondOpenOrders
    ) {}

    @Transactional(isolation = Isolation.READ_COMMITTED, readOnly = true)
    public Observation readCommitted(
            CountDownLatch firstReadDone,
            CountDownLatch writerCommitted) {
        return observe(firstReadDone, writerCommitted);
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ, readOnly = true)
    public Observation repeatableRead(
            CountDownLatch firstReadDone,
            CountDownLatch writerCommitted) {
        return observe(firstReadDone, writerCommitted);
    }

    private Observation observe(
            CountDownLatch firstReadDone,
            CountDownLatch writerCommitted) {

        int firstBalance = jdbc.queryForObject(
            "SELECT balance FROM iso_accounts WHERE id = 1",
            Integer.class
        );
        long firstCount = jdbc.queryForObject(
            "SELECT COUNT(*) FROM iso_orders WHERE state = 'OPEN'",
            Long.class
        );

        // Reader đã tạo snapshot/hoàn tất lần đọc đầu.
        firstReadDone.countDown();

        try {
            if (!writerCommitted.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Writer timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Reader interrupted", ex);
        }

        int secondBalance = jdbc.queryForObject(
            "SELECT balance FROM iso_accounts WHERE id = 1",
            Integer.class
        );
        long secondCount = jdbc.queryForObject(
            "SELECT COUNT(*) FROM iso_orders WHERE state = 'OPEN'",
            Long.class
        );

        return new Observation(
            firstBalance, firstCount, secondBalance, secondCount
        );
    }
}
```

`observe(...)` là private helper **được gọi từ hai public method sau khi Spring proxy đã mở transaction**. Không gắn `@Transactional` trên helper và không tự gọi public transactional method từ chính bean. Transaction giữ connection/snapshot xuyên suốt thời gian reader chờ tín hiệu writer.

Hàm `queryForObject(..., Integer.class)` đọc kiểu `INTEGER`, còn PostgreSQL `COUNT(*)` trả kiểu `BIGINT` nên dùng `Long.class`. Các giá trị không null nhờ bảng/record khởi tạo ở runner.

### 10.4. WriterService: thay đổi đồng thời và commit

**`src/main/java/demo/isolation/WriterService.java`:**

```java
package demo.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WriterService {
    private final JdbcTemplate jdbc;

    public WriterService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void publishChange() {
        jdbc.update(
            "UPDATE iso_accounts SET balance = 200 WHERE id = 1"
        );
        jdbc.update(
            "INSERT INTO iso_orders (id, state) VALUES (2, 'OPEN')"
        );
    }
}
```

`publishChange()` ghi cả UPDATE và INSERT trong một transaction; với cấu hình mặc định PostgreSQL ở đây, writer chạy ở `READ_COMMITTED`. Coordinator gọi method trên **Spring-managed bean khác thread**; transaction writer commit khi lời gọi proxy trả về bình thường.

Nếu writer thất bại trước commit, kịch bản không đáp ứng tiền đề; chương trình nên báo lỗi thay vì in output như thể writer đã commit thành công.

### 10.5. Application: chạy kịch bản hai lần và in kết quả

**`src/main/java/demo/isolation/IsolationApplication.java`:**

```java
package demo.isolation;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class IsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }

    @Bean
    CommandLineRunner run(
            ReaderService reader,
            WriterService writer,
            JdbcTemplate jdbc) {

        return args -> {
            // CHỈ trên database riêng dùng cho bài thực hành.
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS iso_accounts ("
                + "id INTEGER PRIMARY KEY, balance INTEGER NOT NULL)"
            );
            jdbc.execute(
                "CREATE TABLE IF NOT EXISTS iso_orders ("
                + "id INTEGER PRIMARY KEY, state VARCHAR(12) NOT NULL)"
            );

            ExecutorService pool = Executors.newFixedThreadPool(2);
            try {
                scenario(
                    "READ_COMMITTED", false, reader, writer, jdbc, pool
                );
                scenario(
                    "REPEATABLE_READ", true, reader, writer, jdbc, pool
                );
            } finally {
                pool.shutdownNow();
            }
        };
    }

    private static void scenario(
            String label,
            boolean repeatable,
            ReaderService reader,
            WriterService writer,
            JdbcTemplate jdbc,
            ExecutorService pool) throws Exception {

        // Reset trước khi tạo transaction reader/writer.
        jdbc.execute("TRUNCATE TABLE iso_orders, iso_accounts");
        jdbc.update(
            "INSERT INTO iso_accounts(id, balance) VALUES (1, 100)"
        );
        jdbc.update(
            "INSERT INTO iso_orders(id, state) VALUES (1, 'OPEN')"
        );

        CountDownLatch firstReadDone = new CountDownLatch(1);
        CountDownLatch writerCommitted = new CountDownLatch(1);

        Future<ReaderService.Observation> future =
            pool.submit(() -> repeatable
                ? reader.repeatableRead(firstReadDone, writerCommitted)
                : reader.readCommitted(firstReadDone, writerCommitted)
            );

        try {
            if (!firstReadDone.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Reader timed out");
            }
            // Đợi reader đọc xong rồi mới thực hiện writer transaction.
            writer.publishChange();
        } finally {
            // Được phát SAU khi lời gọi proxy writer kết thúc.
            // Nếu writer lỗi, ngoại lệ vẫn thoát; không báo thành công.
            writerCommitted.countDown();
        }

        ReaderService.Observation observation =
            future.get(30, TimeUnit.SECONDS);

        System.out.println(label + ": " + observation);
    }
}
```

**Chỉ chạy ở database thực hành**: runner dùng `TRUNCATE TABLE iso_orders, iso_accounts` khi mỗi kịch bản bắt đầu, xóa các record demo. Không chạy trên schema production chứa dữ liệu cần giữ.

Cách tránh race:

- Reader khởi động **transaction của chính nó** qua proxy ở thread trong pool.
- Reader chỉ `countDown(firstReadDone)` sau **cả hai SELECT đầu**.
- Coordinator đợi tín hiệu rồi gọi writer; writer mở và commit **transaction khác**.
- Chỉ **sau khi writer proxy trả về**, coordinator mới mở `writerCommitted` cho reader chạy hai SELECT tiếp.
- Không dựa vào `sleep` hay thứ tự ngẫu nhiên của thread scheduling.

Nếu reader không có kết nối/DB chậm, timeout 30 giây gây exception thay vì giả vờ có kết quả. Trong môi trường tải cao có thể tăng thời hạn chờ; timeout chỉ là bảo vệ kịch bản demo, không quyết định isolation.

### 10.6. Lệnh chạy và stdout

Tạo project với Gradle Wrapper (ví dụ từ Spring Initializr), ở thư mục project chạy:

```bash
./gradlew bootRun
```

PowerShell:

```powershell
.\gradlew.bat bootRun
```

Với PostgreSQL đã sẵn sàng, database demo không có writer ngoài và các class/config đúng như trên, hai dòng do chương trình in ra là:

```text
READ_COMMITTED: Observation[firstBalance=100, firstOpenOrders=1, secondBalance=200, secondOpenOrders=2]
REPEATABLE_READ: Observation[firstBalance=100, firstOpenOrders=1, secondBalance=100, secondOpenOrders=1]
```

Các log khởi động và Gradle có thể xuất hiện thêm. Tên `Observation[...]` và tên field đến từ `record Observation` của Java 17; đó là kết quả `toString()` mặc định của record.

**Phân tích:**

- `READ_COMMITTED`: SELECT account sau writer commit thấy 200 thay vì 100 → **non-repeatable read**. Cùng điều kiện `state='OPEN'` đếm được 2 thay vì 1 → **phantom read**.
- PostgreSQL `REPEATABLE_READ`: hai SELECT sau writer commit vẫn thấy snapshot cũ: account=100 và count=1. Writer đã commit thay đổi trong DB, nhưng reader hiện tại chưa nhìn thấy nó.
- Không có ví dụ dirty read ở đây, vì PostgreSQL không cho dirty read ngay cả khi yêu cầu `READ_UNCOMMITTED`.

Điều kiện dữ liệu và transaction đã được mã hóa rõ; đây không phải chứng minh rằng mọi câu SQL hoặc mọi DB sẽ có output tương tự.

### 10.7. Quan sát sau khi reader kết thúc

Sau scenario `REPEATABLE_READ`, một transaction/query **mới** chạy:

```sql
SELECT balance FROM iso_accounts WHERE id=1;
SELECT COUNT(*) FROM iso_orders WHERE state='OPEN';
```

sẽ thấy 200 và 2 nếu không có writer khác. Việc reader vẫn thấy 100/1 trong snapshot riêng **không** ngăn writer commit, không có nghĩa dữ liệu “bị mất”, và không có nghĩa toàn bộ hệ thống đứng yên.

## 11. Vì sao dùng transaction khác thread mà không “truyền” transaction từ reader?

Ở Spring JDBC imperative, `@Transactional` gắn connection/transaction context với **luồng thực thi hiện tại** thông qua infrastructure của Spring. Nếu bên trong một transactional method chỉ tạo `new Thread(...)` rồi chạy code JDBC, thread mới **không tự kế thừa** transaction của thread cũ.

Ví dụ trên cố ý cần **hai transaction độc lập chạy đồng thời** để quan sát anomalies:

```text
Main/Coordinator Thread
   |
   +-- submit readerService.readCommitted(...) vào pool thread
   |       -> Spring proxy mở transaction T1, giữ connection #1
   |
   +-- gọi writerService.publishChange(...) trong main thread
   |       -> Spring proxy mở transaction T2, connection #2
   |       -> COMMIT T2
   |
   +-- phát latch cho T1 tiếp tục đọc
           -> T1 đọc thêm trên connection #1, rồi kết thúc
```

Việc tách threads ở đây là **công cụ tái hiện concurrency có kiểm soát**, không phải gợi ý chia một transaction nghiệp vụ sang nhiều thread. Khi cần xử lý async thật, phải thiết kế transaction boundary và idempotency thích hợp cho từng task.

Nếu bạn thử tái hiện bằng cách gọi hai method trong **cùng thread** mà cả hai dùng `Propagation.REQUIRED`, method thứ hai có thể **tham gia cùng transaction vật lý** thay vì tạo transaction độc lập. Khi đó bạn không tạo được tình huống T1 đọc trong lúc T2 ở transaction khác update/commit như trong timeline.

## 12. READ_COMMITTED có đảm bảo mọi nghiệp vụ chính xác không?

Không. `READ_COMMITTED` ngăn dirty read, nhưng non-repeatable/phantom có thể phá giả định:

```text
T1: COUNT(booking WHERE room=101 AND overlaps(slot)) -> 0
T2: COUNT(booking WHERE room=101 AND overlaps(slot)) -> 0
T1: INSERT booking for room=101/slot
T2: INSERT booking for room=101/slot
T1/T2: COMMIT
```

Nếu DB không có constraint/locking chống trùng lịch và cả hai INSERT không xung đột ở khóa hiện hữu, hai transaction có thể cùng ghi booking xung đột. Vấn đề này là **race/invariant violation** gắn với predicate, không chỉ là việc hai câu SELECT đọc ra số khác nhau.

Các biện pháp (tùy DB và yêu cầu):

1. **Database constraint**: unique index, exclusion constraint hoặc quy tắc bảo đảm invariant; đây thường là tuyến bảo vệ cuối cùng quan trọng nhất.
2. **Atomic SQL update/insert có điều kiện**: tránh vòng đọc rồi ghi tách rời nếu có cách diễn đạt nguyên tử.
3. **Optimistic locking/versioning**: detect concurrent update của cùng entity/row, retry phù hợp.
4. **Explicit locking**: `SELECT ... FOR UPDATE` đối với hàng hiện có và range/predicate lock phù hợp engine. Với query trả **không có hàng**, chỉ `FOR UPDATE` trên tập rỗng thường **không khóa được “khoảng trống” như mong muốn** trên mọi DB.
5. **SERIALIZABLE**: ngăn những lịch commit không thể serial hóa bằng chiến lược của DB; cần **retry toàn bộ transaction** khi DB abort một lần thực thi.

Không khẳng định “chọn REPEATABLE_READ sẽ giải quyết chắc chắn mọi booking overlap”; PostgreSQL RR có thể vẫn gặp write skew nếu hai transaction cùng đọc một snapshot rồi ghi những hàng khác nhau.

## 13. SERIALIZABLE: mạnh hơn nhưng không đồng nghĩa “không cần xử lý lỗi”

Trong Spring:

```java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void reserveResource() {
    // Đọc invariant, sau đó ghi dữ liệu phụ thuộc invariant.
}
```

Với PostgreSQL, serializable transaction có thể bị từ chối với SQLSTATE **40001** nếu việc commit tất cả transaction đồng thời sẽ tạo một lịch không thể tương đương chạy tuần tự. Đây là một **cơ chế bảo đảm correctness**: DB từ chối một số execution, không nhất thiết chặn tất cả query cho đến khi một transaction khác xong.

Các điểm quan trọng:

- Một lần `@Transactional` thất bại với serialization error không có nghĩa database “hỏng” hoặc business logic cần commit bất chấp. **Transaction đó đã thất bại** và cần xem xét retry.
- Retry, nếu có, phải là **một transaction mới** đọc lại điều kiện đầu vào, thường ở phía **ngoài transaction proxy** của mỗi attempt. Không chỉ retry câu `INSERT` cuối cùng trên cùng transaction đã bị abort.
- Retry nên **giới hạn số lần**, có backoff khi thích hợp và phân biệt lỗi có thể retry với lỗi dữ liệu/constraint không thể retry.
- External side effects (gửi email/HTTP) bên trong attempt có thể bị lặp khi retry; cân nhắc outbox/after-commit và idempotency.
- `SERIALIZABLE` có chi phí và semantics phụ thuộc DB, không phải lựa chọn bắt buộc cho mọi báo cáo hoặc mọi giao dịch đọc.

Một transaction đọc-only không ghi cũng có thể có cân nhắc riêng về snapshot/serialization trên DB; đừng suy rằng chỉ writer mới cần xử lý lỗi concurrency.

## 14. Những điều dễ nhầm về JPA/Hibernate và Spring Data JPA

### 14.1. Một entity đã managed có thể bị cache trong persistence context

`EntityManager.find(Account.class, 1L)` hai lần trong cùng persistence context thường trả **cùng managed entity**, không nhất thiết gửi hai câu SELECT tới DB. Do đó, một test “đọc hai lần, không đổi” ở Spring Data JPA **chưa chứng minh** database đã ngăn non-repeatable read.

Nếu cần kiểm tra isolation tại DB:

- Dùng JDBC trực tiếp như ví dụ.
- Hoặc hiểu cách JPA flush/clear/refresh, entity state, query cache và database query thực sự được phát ra.
- Tránh `EntityManager.clear()` tùy tiện trong nghiệp vụ vì có thể ảnh hưởng trạng thái đang chờ flush; nó là công cụ test cần kiểm soát.

### 14.2. Flush không phải commit

Trong JPA, `entityManager.flush()` có thể gửi SQL trước transaction commit. Transaction khác ở `READ_COMMITTED` vẫn **không được đọc dirty state** chỉ vì flush đã chạy; nó phải đợi dữ liệu được commit để thấy phiên bản mới phù hợp isolation. Sau flush, transaction hiện tại vẫn có thể rollback.

### 14.3. Repository method và outer transaction

Nếu service ngoài đã mở transaction và gọi một repository có transaction declaration khác, nó thường **tham gia outer**. Isolation của repository không tự tạo transaction vật lý mới. Chọn isolation ở **service boundary sở hữu nghiệp vụ** và xác minh manager thực sự được dùng.

### 14.4. readOnly không đồng nghĩa repeatable read

Hai thuộc tính riêng:

```java
@Transactional(
    readOnly = true,
    isolation = Isolation.READ_COMMITTED
)
```

Một transaction chỉ-đọc ở RC vẫn có thể thấy non-repeatable/phantom do transaction khác commit giữa hai SELECT. Không suy từ chữ “readOnly” rằng snapshot cố định.

## 15. Hướng dẫn test và chẩn đoán khi kết quả không như dự đoán

| Triệu chứng | Nguyên nhân hay gặp | Hướng xác minh |
| --- | --- | --- |
| Muốn thấy dirty read ở PostgreSQL nhưng luôn thấy committed data | PostgreSQL `READ_UNCOMMITTED` được xử lý như RC | Đọc documentation DB, không ép kỳ vọng sai |
| T1 không nhìn thấy UPDATE vừa commit ở RC | T2 chưa commit trước khi câu SELECT thứ hai bắt đầu; hoặc test không thực sự cùng DB/connection tách biệt | Dùng latch, log boundary, xác nhận thời điểm commit |
| T1 thấy dữ liệu thay đổi dù tưởng RR | Không có transaction thật giữa hai SELECT; mở transaction mới; hoặc đang dùng DB khác | Kiểm tra proxy, isolation, connection, `@Transactional` |
| JPA test không thay đổi entity ở RC | Persistence context trả cùng managed entity, không query DB lần hai | Bật SQL logging/test JDBC, quản lý EntityManager rõ ràng |
| Inner `@Transactional(isolation=SERIALIZABLE)` không nâng level | `REQUIRED` tham gia outer transaction | Đặt level tại outer owner hoặc bật validation |
| Test dùng `Thread.sleep` cho kết quả lúc được lúc không | Scheduling không xác định | Dùng CountDownLatch/phối hợp rõ commit trước reread |
| Test đang `@Transactional` ở lớp test | Test framework mở transaction và có thể rollback cuối test | Tách transaction test khỏi reader/writer, đọc DB sau commit |
| Pool connection quá nhỏ, chương trình treo | Reader giữ connection trong khi writer cần connection thứ hai | Đủ pool size và timeout, tránh giữ transaction dài ở production |
| SERIALIZABLE báo SQLSTATE `40001` | DB phát hiện serialization conflict | Retry toàn transaction có giới hạn theo policy |
| Truy vấn SQL thay đổi nhưng không hiểu là phantom hay nonrepeatable | Dùng query theo hàng ID lẫn predicate | Tách hai case như ví dụ |

### Checklist trước khi kết luận isolation đang hoạt động

1. **DB và engine đúng**: PostgreSQL/MySQL InnoDB/H2 không thể giả định giống hệt nhau.
2. **Transaction thật**: có `PlatformTransactionManager`, đúng DataSource, lời gọi qua proxy.
3. **Hai connection/transaction độc lập**: writer không được tham gia transaction reader.
4. **Thứ tự sự kiện**: first SELECT → writer UPDATE/INSERT → writer COMMIT → second SELECT.
5. **Query bất biến**: cùng ID cho non-repeatable, cùng predicate cho phantom.
6. **Không đọc cache JPA thay DB**: xác nhận SELECT thực sự chạy.
7. **Isolation áp dụng tại transaction owner**: không chỉ ở inner method đang join outer.
8. **Dữ liệu test cố định và sạch**: không có writer thứ ba, reset chỉ trong database sandbox.
9. **Kết quả sau transaction**: phân biệt dữ liệu trong snapshot T1 với dữ liệu đã commit mà transaction mới có thể thấy.

## 16. Bài tập tự kiểm tra

**Bài 1 — Xác định hiện tượng**

```text
T1: BEGIN
T1: SELECT balance WHERE id=1 -> 100
T2: BEGIN
T2: UPDATE balance=80 WHERE id=1
T2: COMMIT
T1: SELECT balance WHERE id=1 -> 80
T1: COMMIT
```

**Đáp án:** non-repeatable read nếu database/mức isolation cho phép T1 thấy 80. Không phải dirty read vì T2 đã commit trước lần đọc thứ hai.

**Bài 2 — Dữ liệu chưa commit**

```text
T2: UPDATE balance=900 (chưa commit)
T1: SELECT balance -> 900
T2: ROLLBACK
```

**Đáp án:** dirty read, nếu database thật sự cho phép. PostgreSQL không cho timeline kết quả này dưới bất kỳ isolation level hỗ trợ nào.

**Bài 3 — Tập kết quả đổi**

```text
T1: SELECT id FROM orders WHERE state='OPEN' -> [1]
T2: INSERT (2,'OPEN'); COMMIT
T1: SELECT id FROM orders WHERE state='OPEN' -> [1,2]
```

**Đáp án:** phantom read vì tập hàng khớp `WHERE` đổi giữa hai query trong cùng T1.

**Bài 4 — Vì sao PostgreSQL REPEATABLE_READ không cho phantom dù bảng SQL chuẩn có ô “có thể”?**

**Đáp án:** chuẩn SQL chỉ nêu mức bảo đảm **tối thiểu**; PostgreSQL sử dụng snapshot transaction ổn định ở RR, tạo bảo đảm mạnh hơn, nhưng vẫn có serialization anomalies khác.

**Bài 5 — Muốn bảo đảm không có hai booking trùng lịch thì chỉ chọn REPEATABLE_READ là đủ?**

**Đáp án:** chưa chắc. Cần thiết kế constraint/locking/serializable và xử lý xung đột theo DB; RR có thể vẫn có write skew, và plain snapshot read không tự bảo vệ mọi predicate invariant.

**Bài 6 — Vì sao `@Transactional(readOnly=true)` không đủ để ngăn phantom ở PostgreSQL RC?**

**Đáp án:** read-only và isolation là hai thuộc tính khác nhau. T1 ở RC có thể nhận snapshot mới tại SELECT tiếp theo dù T1 không tự ghi dữ liệu.

**Bài 7 — Một method inner khai SERIALIZABLE được gọi từ outer REQUIRED/READ_COMMITTED. Có tự tạo physical SERIALIZABLE transaction không?**

**Đáp án:** không. Inner thường tham gia outer và dùng isolation đã có; cần chọn đúng transaction boundary hoặc `REQUIRES_NEW` có chủ đích, cùng với kiểm tra mismatch khi cần.

## 17. Kết luận

Ba bất thường dễ nhớ bằng **trạng thái commit và đối tượng đọc lại**:

- **Dirty read:** đọc dữ liệu **chưa commit** của T2.
- **Non-repeatable read:** đọc lại **cùng hàng** và thấy giá trị khác sau khi T2 **commit**.
- **Phantom read:** chạy lại **cùng điều kiện tìm kiếm** và thấy **tập hàng khác** sau khi T2 **commit**.

Bảng SQL chuẩn diễn tả những hiện tượng **được phép hay bị cấm** ở từng mức cô lập; **database có quyền bảo vệ mạnh hơn**. PostgreSQL `READ_UNCOMMITTED` thực tế như `READ_COMMITTED`, còn `REPEATABLE_READ` chặn cả phantom trong snapshot read. Spring `@Transactional(isolation = ...)` chỉ yêu cầu manager/driver áp dụng một mức khi mở transaction phù hợp; propagation, proxy, database semantics, caching và concurrency thực tế mới quyết định kết quả.

**Để áp dụng an toàn:** chọn isolation ở transaction owner, thêm DB constraints cho invariant, test bằng hai transaction thật và lịch chạy xác định, đọc documentation của đúng database, và chuẩn bị xử lý concurrency conflict khi dùng `SERIALIZABLE`.

## Nguồn chính thức để đối chiếu

- PostgreSQL — Transaction Isolation và bảng các bất thường: https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — SET TRANSACTION, snapshot và READ UNCOMMITTED: https://www.postgresql.org/docs/current/sql-set-transaction.html
- Spring Framework — TransactionDefinition, isolation constants: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — Using `@Transactional`, isolation/propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation và proxy/thread: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Transaction Propagation, existing transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- MySQL 8.4 — InnoDB Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- MySQL 8.4 — Consistent Nonlocking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html
