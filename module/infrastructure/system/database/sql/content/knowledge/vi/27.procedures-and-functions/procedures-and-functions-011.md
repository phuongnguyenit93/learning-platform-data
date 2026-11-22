# Cursor: khai báo, mở, đọc, đóng và giải phóng

Một truy vấn SQL thường trả cả một **tập kết quả**: `SELECT` tìm những dòng thỏa điều kiện, database tạo kết quả và chương trình nhận các dòng đó. Nhưng đôi khi một thủ tục phải xử lý dữ liệu **từng dòng theo trình tự**, chẳng hạn duyệt danh sách đơn hàng, kiểm tra trạng thái mỗi đơn rồi ghi nhật ký cho từng bản ghi. Lúc này ta có thể gặp **cursor** (*con trỏ truy vấn*).

Cursor không phải “con trỏ bộ nhớ” trong C/C++. Đó là một **đối tượng/trạng thái thực thi truy vấn** cho phép chương trình giữ vị trí trong kết quả và đọc tiếp theo từng bước. Sử dụng cursor đúng nghĩa còn liên quan tới transaction, kết nối database và tài nguyên cần được đóng.

Bài học thuộc chương **Thủ tục và hàm** của module **Database SQL**. Sau khi học, bạn cần hiểu:

- Cursor được **khai báo, mở, đọc bằng `FETCH`, đóng và giải phóng** ra sao.
- Khác biệt giữa **SQL cursor** (`DECLARE CURSOR` rồi `FETCH`) và **cursor trong PL/pgSQL** (`DECLARE` biến, `OPEN`, `FETCH ... INTO`, `CLOSE`).
- Cách dùng `FOUND`, `record`, cursor tham số, cursor động và vòng `FOR` tự quản lý việc mở/đóng.
- Vì sao cursor thông thường **gắn với session/transaction**, khi nào `WITH HOLD` là ngoại lệ, và chuyện gì xảy ra khi `COMMIT` hoặc `ROLLBACK`.
- Khi nào xử lý từng dòng có ý nghĩa, khi nào một câu SQL **set-based** an toàn và hiệu quả hơn.
- Cách tránh giữ tài nguyên quá lâu trong thủ tục, ứng dụng Java/JDBC và SQL client.

Ví dụ chính dùng **PostgreSQL**. MySQL, SQL Server, Oracle và các driver có mô hình cursor riêng; không sao chép nguyên cú pháp PL/pgSQL sang các hệ quản trị khác.

> **Nguyên tắc cốt lõi:** Cursor là **một cách tiêu thụ kết quả truy vấn**, không phải cách làm cho SQL tự động nhanh hơn hay an toàn hơn. Mỗi cursor phải có **vòng đời rõ ràng** và một **thành phần chịu trách nhiệm đóng**.

## 1. Phân biệt truy vấn tập hợp và xử lý từng dòng

SQL là ngôn ngữ thiên về **tập hợp**. Ta mô tả điều cần lấy hoặc thay đổi:

```sql
SELECT order_id, amount
FROM orders
WHERE status = 'PAID'
ORDER BY order_id;
```

Database có thể tối ưu cách truy xuất, lọc, ghép và sắp xếp toàn bộ tập kết quả.

Với cursor, một chương trình có thể đi qua kết quả như sau:

```text
Truy vấn SELECT
       │
       ▼
   Cursor đang mở
       │
       ├─ FETCH 1 → dòng thứ nhất → xử lý
       ├─ FETCH 2 → dòng thứ hai → xử lý
       ├─ FETCH 3 → dòng thứ ba → xử lý
       ├─ ...
       └─ FETCH hết → đóng cursor
```

### 1.1. Tại sao dùng cursor?

Một số nhu cầu hợp lý:

1. Duyệt theo dòng trong **thủ tục** khi mỗi dòng có nhiều nhánh xử lý khác nhau và khó biểu diễn bằng một câu SQL.
2. Tiêu thụ **kết quả lớn theo từng đợt** thay vì tải toàn bộ vào bộ nhớ ứng dụng.
3. Duy trì vị trí khi một ứng dụng tương tác cần `FETCH` tiếp trong cùng phiên.
4. Duyệt các bản ghi và có một thao tác phụ thuộc **dòng hiện tại**, ví dụ cursor có thể cập nhật cùng `WHERE CURRENT OF` trong những điều kiện phù hợp.

Tuy nhiên, một phép đổi trạng thái đồng loạt:

```sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE status = 'PAID'
  AND ordered_at < DATE '2025-01-01';
```

thường **không cần cursor**. Một câu `UPDATE` theo tập hợp giúp database lập kế hoạch và thao tác dữ liệu ở tầng SQL mà không phải gửi hàng nghìn câu lệnh riêng.

### 1.2. Cursor không đồng nghĩa xử lý bất đồng bộ

`FETCH NEXT` chỉ tiến đến phần tiếp theo của một truy vấn đã được mở. Nó không tự tạo job chạy nền, không tự mở một transaction mới, không tự lưu checkpoint bền vững giữa các lần triển khai, và không tự khôi phục sau khi kết nối bị mất.

## 2. Vòng đời chuẩn của cursor

Mô hình khái niệm gồm năm bước:

```text
       ┌────────────┐
       │ 1. DECLARE │  Định nghĩa cursor / biến cursor
       └──────┬─────┘
              ▼
       ┌────────────┐
       │ 2. OPEN    │  Tạo trạng thái truy vấn có thể đọc
       └──────┬─────┘
              ▼
       ┌────────────┐
       │ 3. FETCH   │  Đọc các dòng, cập nhật vị trí
       └──────┬─────┘
              │
        ┌─────┴─────┐
        │ Còn dòng? │
        └──┬─────┬──┘
          Có    Không
           │      │
           └──┐   ▼
              │ ┌────────────┐
              └─│ 4. CLOSE   │  Kết thúc cursor
                └──────┬─────┘
                       ▼
                ┌────────────┐
                │ 5. RELEASE │  Tài nguyên được trả về
                └────────────┘
```

Sơ đồ trên mô tả **ý tưởng chung**, không phải năm lệnh SQL tách biệt ở mọi hệ. Trong PostgreSQL:

- **SQL cursor:** `DECLARE name CURSOR FOR SELECT ...` vừa định nghĩa **vừa mở** cursor ở cấp SQL, sau đó `FETCH`, `MOVE`, `CLOSE`. Không có lệnh SQL `OPEN name` tương ứng.
- **PL/pgSQL cursor:** trong phần `DECLARE` khai báo biến cursor, rồi trong phần `BEGIN ... END` mới `OPEN`, `FETCH ... INTO`, `CLOSE`.
- **Giải phóng:** `CLOSE` giải phóng trạng thái/tài nguyên của cursor; ngoài ra cursor thường tự hết hiệu lực khi transaction kết thúc. PostgreSQL không yêu cầu một lệnh `FREE CURSOR` riêng sau `CLOSE`.

### 2.1. “Khai báo” chưa chắc đã “mở”

Đây là điểm dễ nhầm nhất vì cả SQL và PL/pgSQL đều dùng từ `DECLARE`:

| Ngữ cảnh | Khai báo | Mở | Đọc | Đóng |
|---|---|---|---|---|
| SQL PostgreSQL | `DECLARE c CURSOR FOR ...` | Đã được tạo/mở cùng `DECLARE` | `FETCH NEXT FROM c` | `CLOSE c` |
| PL/pgSQL | `DECLARE c CURSOR FOR ...;` | `OPEN c;` | `FETCH c INTO biến;` | `CLOSE c;` |
| PL/pgSQL `refcursor` không ràng buộc | `DECLARE c refcursor;` | `OPEN c FOR SELECT ...;` | `FETCH c INTO biến;` | `CLOSE c;` |
| PL/pgSQL `FOR record IN SELECT` | Không cần tự khai báo cursor có tên | Tự quản lý | Lặp qua `record` | Tự đóng khi kết thúc bình thường |

**Đừng sao chép** cú pháp `OPEN c;` vào SQL editor như một câu SQL độc lập rồi chờ PostgreSQL hiểu như trong PL/pgSQL.

## 3. Chuẩn bị dữ liệu thực hành

Ta dùng **bảng tạm PostgreSQL**, tồn tại trong phiên kết nối thực hành. Không dùng dữ liệu production để thử các thao tác đọc/khóa/cập nhật theo cursor.

### 3.1. Tạo bảng đơn hàng

```sql
CREATE TEMP TABLE cursor_lab_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PAID', 'PENDING', 'CANCELLED')),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    ordered_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ
);
```

### 3.2. Dữ liệu mẫu

```sql
INSERT INTO cursor_lab_orders
    (order_id, customer_id, status, amount, ordered_at)
VALUES
    (1001, 10, 'PAID',      150, TIMESTAMPTZ '2026-07-01 09:00:00+07'),
    (1002, 10, 'PENDING',    90, TIMESTAMPTZ '2026-07-02 09:00:00+07'),
    (1003, 20, 'PAID',      320, TIMESTAMPTZ '2026-07-03 09:00:00+07'),
    (1004, 20, 'PAID',      110, TIMESTAMPTZ '2026-07-04 09:00:00+07'),
    (1005, 30, 'CANCELLED',  75, TIMESTAMPTZ '2026-07-05 09:00:00+07'),
    (1006, 10, 'PAID',      500, TIMESTAMPTZ '2026-07-06 09:00:00+07'),
    (1007, 40, 'PENDING',   240, TIMESTAMPTZ '2026-07-07 09:00:00+07'),
    (1008, 40, 'PAID',      275, TIMESTAMPTZ '2026-07-08 09:00:00+07'),
    (1009, 30, 'PAID',       40, TIMESTAMPTZ '2026-07-09 09:00:00+07'),
    (1010, 50, 'PENDING',   600, TIMESTAMPTZ '2026-07-10 09:00:00+07'),
    (1011, 50, 'PAID',      125, TIMESTAMPTZ '2026-07-11 09:00:00+07'),
    (1012, 60, 'PAID',      180, TIMESTAMPTZ '2026-07-12 09:00:00+07');
```

Tổng cộng **12 đơn**:

| Trạng thái | Số đơn | Các `order_id` |
|---|---:|---|
| `PAID` | 8 | 1001, 1003, 1004, 1006, 1008, 1009, 1011, 1012 |
| `PENDING` | 3 | 1002, 1007, 1010 |
| `CANCELLED` | 1 | 1005 |

Tổng `amount` của tám đơn `PAID` bằng **1700**.

### 3.3. Kiểm tra dữ liệu nguồn

```sql
SELECT order_id, customer_id, status, amount
FROM cursor_lab_orders
ORDER BY order_id;

SELECT status, COUNT(*) AS order_count,
       SUM(amount) AS total_amount
FROM cursor_lab_orders
GROUP BY status
ORDER BY status;
```

Một câu `SELECT` tập hợp như trên là cách dễ nhất để tính tổng. Ta sẽ dùng cursor để **học vòng đời**, chứ không khuyến nghị thay mọi phép `SUM` bằng vòng lặp.

### 3.4. Ghi chú về bảng `TEMP`

Bảng tạm PostgreSQL **thuộc phiên kết nối tạo ra nó**. Nếu mở một kết nối khác, bảng `cursor_lab_orders` này không tự xuất hiện trên kết nối mới. Khi muốn so sánh hai session, phải dùng bảng dùng chung trong môi trường thử riêng.

Nếu đã chạy ví dụ có `COMMIT` làm thay đổi dữ liệu mẫu, hãy mở **phiên mới** để tạo lại bảng và dữ liệu; `ROLLBACK` không hủy được một transaction đã commit.

## 4. SQL cursor: `DECLARE`, `FETCH`, `CLOSE`

Đây là ví dụ ngắn nhất để hiểu cursor ở cấp SQL PostgreSQL. Chạy **trọn khối** trên cùng một kết nối:

```sql
BEGIN;

DECLARE cur_paid NO SCROLL CURSOR FOR
SELECT order_id, customer_id, amount
FROM cursor_lab_orders
WHERE status = 'PAID'
ORDER BY order_id;

FETCH NEXT FROM cur_paid;
-- Dòng 1001, customer 10, amount 150.

FETCH NEXT FROM cur_paid;
-- Dòng 1003, customer 20, amount 320.

CLOSE cur_paid;

COMMIT;
```

### 4.1. Bước `DECLARE`

```sql
DECLARE cur_paid NO SCROLL CURSOR FOR
SELECT ...
```

Trong cú pháp **SQL của PostgreSQL**, lệnh này tạo một cursor có tên `cur_paid` cho truy vấn. Nó không chỉ tạo biến rỗng như phần `DECLARE` của PL/pgSQL.

`NO SCROLL` nói rằng cursor được dùng theo hướng tiến, không yêu cầu di chuyển lùi. Tên cursor chỉ có ý nghĩa trong **session kết nối** tương ứng.

### 4.2. Bước `FETCH`

```sql
FETCH NEXT FROM cur_paid;
```

đọc **dòng kế tiếp** tính từ vị trí hiện tại. Sau mỗi lần đọc thành công, vị trí cursor được cập nhật.

### 4.3. Bước `CLOSE`

```sql
CLOSE cur_paid;
```

đóng cursor và giải phóng tài nguyên trạng thái của cursor. Sau đó không được tiếp tục `FETCH` bằng tên `cur_paid` trừ khi tạo/mở một cursor mới tương ứng.

### 4.4. Vai trò của transaction

Trong PostgreSQL, SQL cursor thông thường **không có `WITH HOLD`** phải được sử dụng trong một transaction tường minh để tiếp tục `FETCH` qua nhiều lệnh. Nếu transaction kết thúc, cursor đó không còn.

Đừng viết:

```sql
-- Minh họa sai vòng đời, KHÔNG chạy trong thực hành.
BEGIN;
DECLARE cur_paid CURSOR FOR SELECT order_id FROM cursor_lab_orders;
COMMIT;
FETCH NEXT FROM cur_paid;  -- Cursor thông thường đã hết hiệu lực.
```

Một lỗi do `FETCH` sau khi cursor không còn tồn tại có thể làm transaction đang mở rơi vào trạng thái lỗi ở PostgreSQL. Hãy kiểm tra vòng đời thay vì thử cố ý trên phiên đang xử lý công việc khác.

## 5. Đọc nhiều dòng mỗi lần: `FETCH FORWARD n`

Không bắt buộc mỗi lần `FETCH` chỉ lấy một dòng. Với SQL cursor:

```sql
BEGIN;

DECLARE cur_paid CURSOR FOR
SELECT order_id, amount
FROM cursor_lab_orders
WHERE status = 'PAID'
ORDER BY order_id;

FETCH FORWARD 3 FROM cur_paid;
-- 1001, 1003, 1004.

FETCH FORWARD 3 FROM cur_paid;
-- 1006, 1008, 1009.

FETCH FORWARD 3 FROM cur_paid;
-- 1011, 1012: chỉ còn 2 dòng.

FETCH NEXT FROM cur_paid;
-- Không còn dòng.

CLOSE cur_paid;
COMMIT;
```

### 5.1. Số dòng một batch có thể ít hơn `n`

`FETCH FORWARD 3` nghĩa là “lấy **tối đa** ba dòng kế tiếp”, không phải cam kết luôn có ba dòng. Ở cuối tập kết quả, có thể chỉ còn hai, một hoặc không còn dòng nào.

### 5.2. Lợi ích của đọc theo batch

Đọc theo đợt có thể giảm số lần trao đổi ứng dụng–database, nhất là khi kết quả lớn. Chương trình có thể xử lý lần lượt **100, 500 hoặc 1000 dòng** trong một batch mà không giữ toàn bộ triệu dòng trong bộ nhớ ứng dụng.

Nhưng batch size không phải thông số “càng lớn càng tốt”. Nó ảnh hưởng bộ nhớ, thời gian giữ transaction, mạng, độ trễ phản hồi và khả năng dừng sớm khi gặp lỗi.

### 5.3. `FETCH ALL` đọc hết phần còn lại

```sql
FETCH ALL FROM cur_paid;
```

có thể trả **mọi dòng còn lại** từ vị trí hiện tại của cursor. Với tập kết quả khổng lồ, cách này có thể làm mất lợi ích tiêu thụ theo batch ở ứng dụng.

**Cursor không tự bảo đảm tiết kiệm bộ nhớ nếu bạn `FETCH ALL` rồi tải toàn bộ kết quả cùng lúc.**

## 6. Vị trí hiện tại và `MOVE`

`MOVE` thay đổi vị trí cursor **mà không trả về các dòng dữ liệu** như `FETCH`.

```sql
BEGIN;

DECLARE cur_paid CURSOR FOR
SELECT order_id, amount
FROM cursor_lab_orders
WHERE status = 'PAID'
ORDER BY order_id;

FETCH NEXT FROM cur_paid;
-- 1001.

MOVE FORWARD 2 FROM cur_paid;
-- Bỏ qua 1003 và 1004 theo vị trí cursor.

FETCH NEXT FROM cur_paid;
-- 1006.

CLOSE cur_paid;
ROLLBACK;
```

### 6.1. `MOVE` không xử lý các dòng đã bỏ qua

Khi dùng `MOVE FORWARD 2`, chương trình **không nhận về giá trị** `1003`, `1004` để xử lý. Đây là thao tác điều hướng vị trí.

### 6.2. Cursor không có thứ tự xác định nếu `SELECT` không có `ORDER BY`

```sql
DECLARE c CURSOR FOR
SELECT order_id FROM cursor_lab_orders;
```

không bảo đảm dòng đầu tiên luôn là `1001`. Việc di chuyển “bỏ hai dòng” chỉ có ý nghĩa nghiệp vụ nếu truy vấn có **thứ tự rõ ràng**, chẳng hạn:

```sql
ORDER BY order_id
```

Nếu sắp theo thời gian và có các giá trị `ordered_at` trùng nhau, nên thêm khóa phân xử như `order_id`.

## 7. `SCROLL` và `NO SCROLL`: di chuyển tiến, lùi, tới vị trí

Một cursor chỉ cần đọc tuần tự nên ưu tiên lối sử dụng **forward-only**. Khi thực sự cần đọc lùi hoặc tới một vị trí cụ thể, PostgreSQL có cú pháp `SCROLL`.

```sql
BEGIN;

DECLARE cur_scroll SCROLL CURSOR FOR
SELECT order_id, amount
FROM cursor_lab_orders
WHERE status = 'PAID'
ORDER BY order_id;

FETCH NEXT FROM cur_scroll;
-- 1001.

FETCH NEXT FROM cur_scroll;
-- 1003.

FETCH PRIOR FROM cur_scroll;
-- 1001.

FETCH ABSOLUTE 4 FROM cur_scroll;
-- 1006: dòng thứ tư trong thứ tự PAID.

FETCH LAST FROM cur_scroll;
-- 1012.

CLOSE cur_scroll;
ROLLBACK;
```

### 7.1. Các hướng đọc

| Cú pháp PostgreSQL | Tác dụng |
|---|---|
| `FETCH NEXT FROM c` | Lấy dòng kế tiếp |
| `FETCH PRIOR FROM c` | Lấy dòng trước |
| `FETCH FIRST FROM c` | Đến dòng đầu |
| `FETCH LAST FROM c` | Đến dòng cuối |
| `FETCH ABSOLUTE 4 FROM c` | Lấy dòng thứ tư |
| `FETCH RELATIVE 2 FROM c` | Di chuyển tương đối và lấy dòng |
| `FETCH FORWARD 10 FROM c` | Lấy tối đa 10 dòng tiến |
| `FETCH ALL FROM c` | Lấy phần còn lại theo hướng tiến |

### 7.2. Vì sao không luôn bật SCROLL?

Khả năng cuộn lùi có thể yêu cầu hệ quản trị giữ thêm trạng thái hoặc vật liệu hóa dữ liệu. Một số loại query có hàm biến động hoặc điều kiện đặc biệt cũng khiến ý nghĩa đọc lại không đơn giản.

Với tác vụ export hoặc batch một chiều, `NO SCROLL` giúp biểu đạt rõ **không cần quay lại**. Với tương tác điều hướng, cân nhắc `SCROLL` nhưng phải hiểu chi phí.

### 7.3. Không dùng lùi dòng để thay thiết kế phân trang bền vững

Cursor có thể hữu ích khi người dùng duyệt liên tiếp trên **một kết nối còn sống**, nhưng không phải một “token phân trang” ổn định qua nhiều HTTP request nếu mỗi request dùng connection khác.

Với API phân trang độc lập session, thường nên cân nhắc **keyset pagination** hoặc token có thể tái dựng query, thay vì giữ cursor server-side lâu chỉ để người dùng bấm “Trang tiếp”.

## 8. `CLOSE` và giải phóng tài nguyên thực sự

Mỗi cursor đang mở có thể gắn với trạng thái thực thi, snapshot, vị trí, bộ nhớ và đôi khi tệp tạm/khóa. Khả năng giữ tài nguyên cụ thể phụ thuộc loại cursor, kế hoạch và transaction.

### 8.1. `CLOSE` làm gì?

```sql
CLOSE cur_paid;
```

cho PostgreSQL biết cursor đã dùng xong, giải phóng trạng thái portal của cursor. Với ứng dụng nhiều người dùng hoặc xử lý batch, đây là bước quản lý tài nguyên quan trọng.

### 8.2. Điều gì không phải `CLOSE`?

- Không phải `COMMIT`.
- Không phải `ROLLBACK`.
- Không hoàn tác các thay đổi dữ liệu mà chương trình đã ghi.
- Không tự đóng kết nối database.
- Không bảo đảm mọi khóa của transaction khác được thả ngay, vì phạm vi khóa còn phụ thuộc transaction và thao tác đã thực hiện.

Ví dụ:

```sql
BEGIN;
DECLARE c CURSOR FOR
SELECT order_id FROM cursor_lab_orders ORDER BY order_id;
FETCH NEXT FROM c;
CLOSE c;
-- Transaction vẫn còn mở cho tới khi COMMIT/ROLLBACK.
ROLLBACK;
```

### 8.3. `refcursor` không phải chính cursor đang mở

Trong PL/pgSQL, một biến `refcursor` chứa **tên/tham chiếu tới portal**. Nếu đổi:

```sql
v_cursor := NULL;
```

điều đó **không tương đương `CLOSE v_cursor` đã mở trước đó**. Biến là tham chiếu; tài nguyên cursor do database quản lý riêng. Cần đóng portal qua đúng tên/biến khi vẫn còn hợp lệ, hoặc transaction kết thúc theo quy tắc.

### 8.4. Tự đóng khi transaction kết thúc

Cursor PostgreSQL **không có `WITH HOLD`** sẽ tự hết hiệu lực lúc transaction `COMMIT`/`ROLLBACK`. Điều này là cơ chế dọn dẹp cuối, không phải lời khuyên bỏ `CLOSE` trong các thủ tục dài khi còn muốn thực hiện nhiều bước trong cùng transaction.

### 8.5. Có lệnh `DEALLOCATE CURSOR` không?

Trong PostgreSQL, **`DEALLOCATE` dùng cho prepared statement**, không phải bước giải phóng cursor. Đối với cursor, dùng `CLOSE` hoặc để vòng đời transaction/session kết thúc theo quy tắc. `CLOSE ALL` có thể đóng nhiều cursor của session, nhưng không nên dùng tùy tiện trong ứng dụng có các thành phần khác cũng đang sở hữu cursor.

## 9. Cursor và transaction: trường hợp thông thường

Một cursor SQL thông thường trong PostgreSQL không tồn tại độc lập với transaction đã tạo nó.

```text
Session A
  BEGIN
     DECLARE c CURSOR ...
     FETCH 10 FROM c
     FETCH 10 FROM c
     CLOSE c
  COMMIT
```

Trong các ví dụ, transaction được mở trước `DECLARE`, dùng hết cursor, đóng, rồi kết thúc.

### 9.1. `COMMIT` sớm khiến cursor không còn

```text
BEGIN
  DECLARE c CURSOR WITHOUT HOLD
  FETCH ...
COMMIT
FETCH c  ← không được: cursor đã đóng
```

Vì thế, nếu một ứng dụng muốn streaming rất nhiều dòng bằng cursor không holdable, nó thường phải **giữ transaction mở trong thời gian fetch**. Điều này có thể tốn tài nguyên, ảnh hưởng khả năng dọn dữ liệu MVCC và giữ khóa tùy query.

### 9.2. `ROLLBACK` cũng đóng cursor thông thường

Nếu transaction gặp lỗi và phải rollback, đừng cố tiếp tục `FETCH` từ cursor trước lỗi. Mở một transaction mới và thực hiện lại query khi chính sách nghiệp vụ cho phép.

### 9.3. Cursor không chuyển tự do giữa các kết nối

Một cursor được mở trên **session A** không thể được fetch qua **session B** chỉ bằng cách biết cùng tên:

```text
Connection A: DECLARE c CURSOR ...
Connection B: FETCH FROM c   ← không thấy portal của A
```

Điều này đặc biệt quan trọng với **connection pool**: nhiều lời gọi `getConnection()` có thể trả các connection khác nhau, ngay cả khi chúng trỏ cùng database.

## 10. `WITH HOLD`: giữ cursor qua `COMMIT`

PostgreSQL cho phép SQL cursor **holdable** tồn tại sau khi transaction khai báo **commit thành công**:

```sql
BEGIN;

DECLARE cur_hold CURSOR WITH HOLD FOR
SELECT order_id, amount
FROM cursor_lab_orders
WHERE status = 'PAID'
ORDER BY order_id;

FETCH FORWARD 2 FROM cur_hold;
-- 1001 và 1003.

COMMIT;

FETCH FORWARD 2 FROM cur_hold;
-- Tiếp tục 1004 và 1006 trên cùng session.

CLOSE cur_hold;
```

### 10.1. `WITH HOLD` giải quyết điều gì?

Nó cho phép **tiếp tục đọc sau commit của transaction tạo cursor** trong **cùng session**, không bắt ứng dụng giữ transaction mở chỉ để dùng tiếp cursor.

### 10.2. Đổi lại là chi phí giữ kết quả

Để một holdable cursor có thể đọc sau commit mà không còn dựa trực tiếp vào transaction cũ, PostgreSQL có thể **vật liệu hóa phần kết quả còn cần** vào bộ nhớ hoặc tệp tạm theo cơ chế phù hợp. Với kết quả lớn, việc này có thể tốn thời gian, bộ nhớ và dung lượng lưu tạm.

Nó không phải cách miễn phí để “stream một tỷ dòng không giữ transaction”.

### 10.3. Những giới hạn cần nhớ

- Vẫn phải dùng **cùng session/kết nối**. Connection khác không thể lấy cursor theo tên một cách tự động.
- Cursor `WITH HOLD` không sống mãi: `CLOSE` hoặc kết thúc session sẽ giải phóng nó.
- Nếu transaction tạo cursor **rollback**, cursor đó không được giữ lại sau rollback.
- Không thể tùy ý kết hợp một cursor holdable với mọi chế độ khóa dòng như `FOR UPDATE`.
- Việc kết quả đã được giữ lại sau commit khác với yêu cầu **xem dữ liệu nguồn mới nhất**: không coi một holdable cursor là feed cập nhật realtime.

### 10.4. Khác với PL/pgSQL `OPEN`

Cú pháp `WITH HOLD` ở ví dụ là của **SQL `DECLARE CURSOR`**. Cursor mở qua `OPEN` trong PL/pgSQL không đơn giản có một tùy chọn `WITH HOLD` tương đương ở cú pháp `OPEN`. Nếu cần thiết kế hàm/procedure trả `refcursor` để caller fetch, thường phải xác định **transaction còn mở cho tới khi caller đọc xong**.

## 11. PL/pgSQL: khai báo cursor ràng buộc rồi mở

Trong **PL/pgSQL**, phần `DECLARE` dùng để khai báo biến và cursor; phần `BEGIN ... END` là thân thủ tục/khối thực thi.

Ví dụ sau chạy bằng **khối ẩn danh `DO`**, không cần tạo một function lưu vĩnh viễn:

```sql
DO $$
DECLARE
    v_order_id INTEGER;
    v_amount NUMERIC(12, 2);
    v_count INTEGER := 0;
    v_total NUMERIC(14, 2) := 0;

    cur_paid CURSOR FOR
        SELECT order_id, amount
        FROM cursor_lab_orders
        WHERE status = 'PAID'
        ORDER BY order_id;
BEGIN
    OPEN cur_paid;

    LOOP
        FETCH cur_paid INTO v_order_id, v_amount;
        EXIT WHEN NOT FOUND;

        v_count := v_count + 1;
        v_total := v_total + v_amount;

        RAISE NOTICE 'Order %, amount %',
            v_order_id, v_amount;
    END LOOP;

    CLOSE cur_paid;

    RAISE NOTICE 'Paid orders: %, total amount: %',
        v_count, v_total;
END $$;
```

Trên dữ liệu gốc, vòng lặp đi qua **8 đơn `PAID`**, cuối cùng báo `v_total = 1700`.

### 11.1. Phần `DECLARE` trong khối PL/pgSQL

```sql
cur_paid CURSOR FOR
    SELECT order_id, amount FROM ...;
```

khai báo một **bound cursor** (*cursor ràng buộc với query*). Query của cursor được chỉ ra tại vị trí khai báo, nhưng **chưa bắt đầu vòng đọc** cho tới khi `OPEN cur_paid;`.

### 11.2. `OPEN`

```sql
OPEN cur_paid;
```

mở cursor đã khai báo, chuẩn bị trạng thái cần thiết để lấy các dòng từ query.

### 11.3. `FETCH ... INTO`

```sql
FETCH cur_paid INTO v_order_id, v_amount;
```

đọc dòng kế tiếp và gán cột vào các biến PL/pgSQL tương ứng. Phải chú ý **số lượng, thứ tự và kiểu dữ liệu** của cột truy vấn với biến đích.

Khác với SQL `FETCH NEXT FROM c` trả result set cho SQL client, trong PL/pgSQL `FETCH ... INTO` đưa dữ liệu vào **biến thủ tục** để xử lý.

### 11.4. `EXIT WHEN NOT FOUND`

`FOUND` là biến trạng thái đặc biệt của PL/pgSQL. Sau `FETCH`:

- `FOUND = TRUE` nếu lấy được một dòng.
- `FOUND = FALSE` nếu không lấy được dòng nào.

Vì vậy:

```sql
FETCH cur_paid INTO v_order_id, v_amount;
EXIT WHEN NOT FOUND;
```

là cặp lệnh quan trọng để **không xử lý dữ liệu cũ sau khi cursor hết dòng**.

### 11.5. `CLOSE`

```sql
CLOSE cur_paid;
```

đóng cursor sau khi vòng lặp kết thúc. Trong một khối `DO`, transaction còn chịu quản lý của người gọi/SQL client. `CLOSE` không tự `COMMIT`.

## 12. Vì sao phải kiểm tra `FOUND` ngay sau `FETCH`?

Một lỗi rất thường gặp:

```sql
LOOP
    FETCH cur_paid INTO v_order_id, v_amount;
    v_total := v_total + v_amount;
    EXIT WHEN NOT FOUND;
END LOOP;
```

Ở lần `FETCH` cuối không tìm được dòng, các biến đích có thể không chứa một dòng mới hợp lệ. Việc cộng trước khi kiểm tra làm **sai logic xử lý** và tạo nguy cơ dùng trạng thái không phù hợp.

Đúng hơn:

```sql
LOOP
    FETCH cur_paid INTO v_order_id, v_amount;
    EXIT WHEN NOT FOUND;

    v_total := v_total + v_amount;
END LOOP;
```

### 12.1. Không đặt một câu SQL khác giữa `FETCH` và `EXIT WHEN NOT FOUND`

Trong PL/pgSQL, nhiều lệnh như `SELECT INTO`, `PERFORM`, `UPDATE`, `DELETE`, `INSERT`, `MOVE` cũng có thể thay đổi `FOUND`.

Ví dụ ý tưởng **không nên dùng**:

```sql
FETCH cur_paid INTO v_order_id, v_amount;
PERFORM 1;
EXIT WHEN NOT FOUND;
```

`PERFORM 1` có thể đặt lại `FOUND = TRUE` và khiến điều kiện thoát không còn phản ánh kết quả của `FETCH`.

**Quy tắc:** Nếu muốn dùng `FOUND` để biết `FETCH` có dòng hay không, kiểm tra **ngay sau `FETCH`** hoặc lưu giá trị vào biến Boolean trước khi chạy lệnh có thể đổi `FOUND`.

### 12.2. `FOUND` không phải biến toàn cục của database

`FOUND` thuộc **ngữ cảnh thực thi PL/pgSQL**. Một SQL client chạy:

```sql
FETCH NEXT FROM cur_paid;
```

không thể tự viết `IF FOUND THEN ...` như cú pháp SQL độc lập ngoài khối PL/pgSQL. SQL client phải kiểm tra **số dòng trong kết quả** hoặc dùng API của driver.

## 13. Dùng `record` thay vì nhiều biến riêng

Nếu cursor trả nhiều cột, có thể dùng biến kiểu `record`:

```sql
DO $$
DECLARE
    v_row RECORD;
    v_count INTEGER := 0;
    cur_large CURSOR FOR
        SELECT order_id, customer_id, amount
        FROM cursor_lab_orders
        WHERE status = 'PAID'
          AND amount >= 200
        ORDER BY order_id;
BEGIN
    OPEN cur_large;

    LOOP
        FETCH cur_large INTO v_row;
        EXIT WHEN NOT FOUND;

        v_count := v_count + 1;
        RAISE NOTICE 'Order %, customer %, amount %',
            v_row.order_id,
            v_row.customer_id,
            v_row.amount;
    END LOOP;

    CLOSE cur_large;
    RAISE NOTICE 'Large paid orders: %', v_count;
END $$;
```

Các đơn `PAID` có `amount >= 200` trong dữ liệu mẫu là:

| order_id | amount |
|---:|---:|
| 1003 | 320 |
| 1006 | 500 |
| 1008 | 275 |

Tức **3 dòng**. `record` nhận cấu trúc cột của kết quả `FETCH`; sau khi lấy được dòng, có thể truy cập trường bằng `v_row.order_id`, `v_row.amount`.

### 13.1. Khi nào dùng `%ROWTYPE`?

Nếu cursor trả **đầy đủ đúng cấu trúc một bảng**, có thể dùng biến dựa trên kiểu dòng:

```sql
DECLARE
    v_order cursor_lab_orders%ROWTYPE;
```

Tuy nhiên, nếu query chỉ chọn ba cột hoặc có cột biểu thức/alias, `record` thường thuận tiện hơn. Không suy đoán `%ROWTYPE` của bảng nguồn luôn khớp với mọi kết quả cursor.

### 13.2. `record` không biến tên cột thành hợp đồng cố định

Nếu query của cursor đổi alias hoặc bỏ cột, truy cập `v_row.amount` có thể lỗi khi không còn trường đó. Với thủ tục quan trọng, cần giữ **hợp đồng cột** rõ ràng và có quy trình thay đổi schema.

## 14. `refcursor`: biến tham chiếu không ràng buộc query trước

PL/pgSQL hỗ trợ kiểu `refcursor`. Đây là một biến mang **tên portal/cursor**. Ta có thể khai báo biến trước, rồi chỉ định query khi mở:

```sql
DO $$
DECLARE
    v_cursor REFCURSOR;
    v_row RECORD;
BEGIN
    OPEN v_cursor FOR
        SELECT order_id, amount
        FROM cursor_lab_orders
        WHERE status = 'PAID'
        ORDER BY order_id;

    LOOP
        FETCH v_cursor INTO v_row;
        EXIT WHEN NOT FOUND;

        RAISE NOTICE '%, %', v_row.order_id, v_row.amount;
    END LOOP;

    CLOSE v_cursor;
END $$;
```

### 14.1. Bound cursor và unbound `refcursor`

| Khía cạnh | Bound cursor | Unbound `refcursor` |
|---|---|---|
| Query được xác định ở đâu? | Trong khai báo `CURSOR FOR SELECT` | Khi `OPEN ... FOR SELECT` hoặc `OPEN ... FOR EXECUTE` |
| Có cần `OPEN` trong PL/pgSQL? | Có | Có |
| Dùng `FETCH ... INTO`? | Có | Có |
| Có thể quyết định truy vấn động? | Hạn chế bởi query khai báo; có thể tham số hóa | Có thể chọn query lúc mở |
| Có cần `CLOSE`? | Có khi đã dùng xong | Có khi đã dùng xong |

### 14.2. Tên biến khác tên portal

Một biến:

```sql
v_cursor REFCURSOR;
```

có thể được PostgreSQL gán một tên portal phù hợp khi `OPEN`. Tên portal là thứ SQL `FETCH` phía ngoài cần biết nếu cursor được trả qua ranh giới hàm.

Không mặc định chuỗi `'v_cursor'` luôn chính là tên cursor thực tế: quy tắc khởi tạo/tên portal có thể khác theo cách khai báo và phiên bản PostgreSQL.

### 14.3. Gán tên portal tường minh

Trong một trường hợp cần tên đã biết:

```sql
DO $$
DECLARE
    v_cursor REFCURSOR := 'cursor_lab_named';
    v_row RECORD;
BEGIN
    OPEN v_cursor FOR
        SELECT order_id, amount
        FROM cursor_lab_orders
        WHERE status = 'PAID'
        ORDER BY order_id;

    FETCH v_cursor INTO v_row;
    RAISE NOTICE 'First order: %', v_row.order_id;

    CLOSE v_cursor;
END $$;
```

Không mở hai cursor đang sống có **cùng tên portal** trên cùng session. Đối với ứng dụng có nhiều yêu cầu đồng thời, cần chiến lược đặt tên tránh xung đột.

## 15. Cursor có tham số: dùng lại một định nghĩa

Khi một thủ tục cần duyệt đơn theo trạng thái hoặc ngưỡng tiền khác nhau, PostgreSQL PL/pgSQL hỗ trợ **bound cursor có đối số**:

```sql
DO $$
DECLARE
    v_row RECORD;

    cur_filtered CURSOR (
        p_status TEXT,
        p_min_amount NUMERIC
    ) FOR
        SELECT order_id, amount
        FROM cursor_lab_orders
        WHERE status = p_status
          AND amount >= p_min_amount
        ORDER BY order_id;
BEGIN
    OPEN cur_filtered('PAID', 200);

    LOOP
        FETCH cur_filtered INTO v_row;
        EXIT WHEN NOT FOUND;

        RAISE NOTICE 'Matching order %, amount %',
            v_row.order_id, v_row.amount;
    END LOOP;

    CLOSE cur_filtered;
END $$;
```

### 15.1. Cách đọc

```sql
cur_filtered CURSOR (p_status TEXT, p_min_amount NUMERIC) FOR ...
```

là định nghĩa một cursor với **hai tham số của cursor**.

```sql
OPEN cur_filtered('PAID', 200);
```

truyền giá trị khi mở. Bộ lọc được áp theo những tham số đã truyền cho lần mở đó.

### 15.2. Vì sao cách này tốt hơn nối chuỗi?

Với các giá trị như `'PAID'` hoặc `200`, dùng tham số giúp:

- Tránh lỗi trích dẫn chuỗi.
- Thể hiện rõ kiểu dữ liệu.
- Tránh SQL injection do nối chuỗi giá trị không tin cậy.
- Dễ tái sử dụng logic định nghĩa cursor.

Không dùng dynamic SQL chỉ vì giá trị `status` hoặc `amount` thay đổi; bind parameter là đủ khi **cấu trúc truy vấn không đổi**.

## 16. Cursor động: `OPEN ... FOR EXECUTE ... USING`

Khi cấu trúc query thực sự cần được quyết định lúc chạy, PL/pgSQL hỗ trợ cursor mở từ một câu lệnh động:

```sql
DO $$
DECLARE
    v_cursor REFCURSOR;
    v_row RECORD;
    v_status TEXT := 'PAID';
    v_min_amount NUMERIC := 200;
BEGIN
    OPEN v_cursor FOR EXECUTE
        'SELECT order_id, amount
         FROM cursor_lab_orders
         WHERE status = $1
           AND amount >= $2
         ORDER BY order_id'
    USING v_status, v_min_amount;

    LOOP
        FETCH v_cursor INTO v_row;
        EXIT WHEN NOT FOUND;

        RAISE NOTICE '%, %', v_row.order_id, v_row.amount;
    END LOOP;

    CLOSE v_cursor;
END $$;
```

### 16.1. `$1`, `$2` là tham số dữ liệu

Trong chuỗi SQL động, `$1` và `$2` nhận giá trị từ:

```sql
USING v_status, v_min_amount
```

Không ghép trực tiếp dữ liệu người dùng vào SQL kiểu:

```sql
-- Không nên:
-- '... WHERE status = ''' || user_status || ''''
```

### 16.2. Tên bảng và tên cột không dùng parameter theo cách đó

Nếu thật sự cần tên đối tượng động, phải kiểm tra quyền/danh sách cho phép và dùng cơ chế quote identifier thích hợp, ví dụ `format('%I', identifier)` trong PostgreSQL. `USING` dành cho **giá trị dữ liệu**, không biến một tham số thành tên bảng tùy ý.

Dynamic SQL có thêm rủi ro bảo mật, cache plan và độ phức tạp; chỉ dùng khi cấu trúc query thực sự cần thay đổi.

## 17. Vòng `FOR ... IN SELECT`: thường đơn giản hơn cursor tường minh

Trong PL/pgSQL, nếu mục tiêu chỉ là duyệt từng dòng từ một truy vấn, rất nhiều trường hợp **không cần tự viết `OPEN`/`FETCH`/`CLOSE`**:

```sql
DO $$
DECLARE
    v_row RECORD;
    v_count INTEGER := 0;
    v_total NUMERIC(14, 2) := 0;
BEGIN
    FOR v_row IN
        SELECT order_id, amount
        FROM cursor_lab_orders
        WHERE status = 'PAID'
        ORDER BY order_id
    LOOP
        v_count := v_count + 1;
        v_total := v_total + v_row.amount;
    END LOOP;

    RAISE NOTICE 'Orders: %, total: %', v_count, v_total;
END $$;
```

Kết quả: **8 đơn, tổng 1700**.

### 17.1. Vì sao vòng `FOR` có lợi?

- Không cần tự gán hai biến từ `FETCH`.
- Không phải tự viết `EXIT WHEN NOT FOUND`.
- Không phải tự gọi `OPEN`/`CLOSE` cho quá trình duyệt thông thường.
- Mã ngắn hơn, giảm nguy cơ quên đóng cursor trong lối thực thi bình thường.

PL/pgSQL quản lý cursor nội bộ phục vụ vòng lặp theo cơ chế của nó.

### 17.2. Khi nào cursor tường minh vẫn hữu ích?

Khi bạn cần:

- Duy trì vị trí giữa các đoạn xử lý.
- Chủ động `FETCH` một dòng tại nhiều thời điểm.
- Di chuyển hoặc quản lý cursor theo một giao diện riêng.
- Trả `refcursor` cho caller.
- Dùng thao tác định vị dòng hiện tại theo yêu cầu tương thích.

Nếu chỉ cần `FOR row IN SELECT`, đừng dùng cursor tường minh chỉ vì nghĩ “thủ tục phải dùng cursor”.

## 18. Duyệt bound cursor bằng `FOR ... IN cursor`

PL/pgSQL còn cho phép vòng `FOR` trên một **bound cursor** với các đối số:

```sql
DO $$
DECLARE
    v_row RECORD;
    v_count INTEGER := 0;
    cur_filtered CURSOR (p_min NUMERIC) FOR
        SELECT order_id, amount
        FROM cursor_lab_orders
        WHERE status = 'PAID'
          AND amount >= p_min
        ORDER BY order_id;
BEGIN
    FOR v_row IN cur_filtered(200) LOOP
        v_count := v_count + 1;
        RAISE NOTICE 'Large paid order: %', v_row.order_id;
    END LOOP;

    RAISE NOTICE 'Count: %', v_count;
END $$;
```

Vòng `FOR ... IN cursor(...)` **tự mở và đóng cursor** theo cách của cấu trúc này. Không gọi `OPEN cur_filtered(...)` trước một vòng `FOR` vốn sẽ tự mở cùng cursor, vì có thể gây lỗi “cursor already in use”.

### 18.1. Chọn giữa hai kiểu `FOR`

Nếu query chỉ xuất hiện một lần, `FOR record IN SELECT ... LOOP` thường dễ đọc nhất.

Nếu muốn **đặt tên/định nghĩa cursor có tham số** rồi duyệt trọn nó, `FOR record IN cursor(args) LOOP` giúp tiết kiệm câu `FETCH` thủ công.

Nếu cần nắm quyền chủ động vòng đời và trả cursor ra ngoài, chọn `OPEN`/`FETCH`/`CLOSE`.

## 19. Cursor trong hàm và thủ tục

Khối `DO` là một cách thực hành PL/pgSQL không tạo object lâu dài. Trong hệ thống thật, cùng logic có thể nằm trong **function** hoặc **procedure**.

### 19.1. Hàm tính tổng bằng cursor

Đoạn sau tạo **function trong schema hiện hành**. Chỉ chạy trên database thực hành và xóa function sau khi học:

```sql
CREATE OR REPLACE FUNCTION cursor_lab_paid_total()
RETURNS NUMERIC
LANGUAGE plpgsql
AS $$
DECLARE
    v_total NUMERIC(14, 2) := 0;
    v_amount NUMERIC(12, 2);
    cur CURSOR FOR
        SELECT amount
        FROM cursor_lab_orders
        WHERE status = 'PAID';
BEGIN
    OPEN cur;

    LOOP
        FETCH cur INTO v_amount;
        EXIT WHEN NOT FOUND;

        v_total := v_total + v_amount;
    END LOOP;

    CLOSE cur;
    RETURN v_total;
END;
$$;

SELECT cursor_lab_paid_total() AS total_paid;
-- 1700 trên dữ liệu gốc.
```

Function chỉ dùng được khi **session gọi nó nhìn thấy bảng tạm** `cursor_lab_orders`. Bản thân function không làm bảng tạm trở thành bảng dùng chung cho những kết nối khác.

Sau thực hành:

```sql
DROP FUNCTION cursor_lab_paid_total();
```

### 19.2. Cách làm theo tập hợp đơn giản hơn

Với đúng bài toán tính tổng tiền `PAID`, nên cân nhắc:

```sql
SELECT COALESCE(SUM(amount), 0) AS total_paid
FROM cursor_lab_orders
WHERE status = 'PAID';
-- 1700.
```

Một `SUM` vừa ngắn, vừa để database tối ưu, vừa tránh vòng lặp tuần tự. Function dùng cursor ở trên là **ví dụ dạy vòng đời**, không phải mẫu tối ưu hóa doanh thu.

### 19.3. Procedure có cursor

Trong PostgreSQL phiên bản hỗ trợ procedure, một procedure có thể chứa cấu trúc PL/pgSQL tương tự:

```sql
CREATE OR REPLACE PROCEDURE cursor_lab_print_paid()
LANGUAGE plpgsql
AS $$
DECLARE
    v_row RECORD;
    cur CURSOR FOR
        SELECT order_id, amount
        FROM cursor_lab_orders
        WHERE status = 'PAID'
        ORDER BY order_id;
BEGIN
    OPEN cur;

    LOOP
        FETCH cur INTO v_row;
        EXIT WHEN NOT FOUND;

        RAISE NOTICE 'Paid order %, amount %',
            v_row.order_id, v_row.amount;
    END LOOP;

    CLOSE cur;
END;
$$;

CALL cursor_lab_print_paid();
```

Sau khi thực hành:

```sql
DROP PROCEDURE cursor_lab_print_paid();
```

Trong ví dụ này procedure **không gọi `COMMIT`/`ROLLBACK` bên trong**. Quyền điều khiển transaction của procedure PostgreSQL có quy tắc riêng theo cách gọi, nesting và ngữ cảnh; không mặc định procedure được phép commit ở mọi nơi.

### 19.4. Khi function/procedure gọi nhiều câu ghi dữ liệu

Các câu DML vẫn tham gia transaction của ngữ cảnh thực thi. Cursor chỉ quyết định cách **đọc/duyệt** một query, không tự tạo giao dịch riêng cho mỗi `FETCH`.

Không coi `CLOSE` như “đã hoàn tất và commit” một công việc nghiệp vụ.

## 20. Trả `refcursor` từ function để caller tự `FETCH`

Một function PostgreSQL có thể trả **tên của cursor** để caller đọc tiếp. Đây là trường hợp cần hiểu rõ ranh giới **function kết thúc nhưng cursor vẫn đang mở trong transaction**.

Đoạn sau tạo function trong **schema hiện hành của database thực hành**:

```sql
CREATE OR REPLACE FUNCTION cursor_lab_open_paid(p_min NUMERIC)
RETURNS REFCURSOR
LANGUAGE plpgsql
AS $$
DECLARE
    v_cursor REFCURSOR := 'cursor_lab_paid_export';
BEGIN
    OPEN v_cursor FOR
        SELECT order_id, customer_id, amount
        FROM cursor_lab_orders
        WHERE status = 'PAID'
          AND amount >= p_min
        ORDER BY order_id;

    RETURN v_cursor;
END;
$$;
```

Caller phải dùng **cùng transaction và cùng session**:

```sql
BEGIN;

SELECT cursor_lab_open_paid(200);
-- Trả tên: cursor_lab_paid_export.

FETCH FORWARD 2 FROM cursor_lab_paid_export;
-- 1003 và 1006.

FETCH ALL FROM cursor_lab_paid_export;
-- Phần còn lại: 1008.

CLOSE cursor_lab_paid_export;
COMMIT;
```

Xóa function thực hành sau khi đã đóng cursor:

```sql
DROP FUNCTION cursor_lab_open_paid(NUMERIC);
```

### 20.1. Vì sao `SELECT function()` rồi `FETCH` có thể lỗi trong autocommit?

Nếu caller chạy `SELECT cursor_lab_open_paid(200)` **ngoài transaction tường minh** và SQL client autocommit ngay sau câu `SELECT`, cursor không holdable được mở bên trong function thường **đã đóng khi câu đó commit**. Một lệnh `FETCH` tiếp theo sẽ không tìm thấy cursor.

Đó là lý do ví dụ luôn có:

```sql
BEGIN;
SELECT ...;
FETCH ...;
CLOSE ...;
COMMIT;
```

### 20.2. Vì sao đặt tên cố định có thể va chạm?

Nếu trong cùng session gọi function hai lần trước khi đóng cursor cũ, cả hai cùng muốn tên portal `'cursor_lab_paid_export'`; lần mở sau có thể lỗi do tên đã tồn tại.

Trong ứng dụng thật có nhiều cursor, có thể dùng tên do PostgreSQL sinh hoặc cơ chế đặt tên duy nhất và trả lại cho caller. Tên portal không phải khóa bền vững để lưu vào hàng đợi công việc.

### 20.3. `refcursor` không có khả năng sống qua reconnect

Hàm có thể trả một chuỗi tên cursor hợp lệ ở session A. Nhưng nếu caller gửi `FETCH` trên connection B từ pool, B **không có portal đó**. Việc một function “trả về refcursor” không làm cursor thành đối tượng chia sẻ trên toàn database.

## 21. Cập nhật dòng hiện tại: `WHERE CURRENT OF`

Trong các điều kiện cho phép, PostgreSQL hỗ trợ cập nhật/xóa một dòng đang được cursor **định vị tới** bằng `WHERE CURRENT OF`.

Ví dụ thực hành có transaction và cuối cùng rollback:

```sql
BEGIN;

DECLARE cur_pending CURSOR FOR
SELECT order_id, status
FROM cursor_lab_orders
WHERE status = 'PENDING'
ORDER BY order_id
FOR UPDATE;

FETCH NEXT FROM cur_pending;
-- Đơn 1002.

UPDATE cursor_lab_orders
SET processed_at = CURRENT_TIMESTAMP
WHERE CURRENT OF cur_pending
RETURNING order_id, processed_at;
-- Cập nhật dòng hiện tại: 1002.

CLOSE cur_pending;
ROLLBACK;
```

### 21.1. `FOR UPDATE` có vai trò gì?

`FOR UPDATE` trong query cursor yêu cầu PostgreSQL khóa những dòng được chọn theo cơ chế khóa hàng cho việc cập nhật, với hành vi cụ thể tùy thời điểm thực thi và loại cursor. Nó giúp phối hợp với các transaction khác khi muốn sửa dòng đã đọc.

Không giữ transaction có cursor khóa dòng mở lâu trong lúc đợi nhập liệu, gọi API hoặc chờ xử lý ngoài database.

### 21.2. Điều kiện sử dụng `WHERE CURRENT OF`

Một số điểm cần nhớ:

- Cursor phải đang mở, và có **dòng hiện tại hợp lệ**.
- Truy vấn cursor phải phù hợp để định vị dòng của bảng đích; không phải mọi `JOIN`, aggregate, `DISTINCT` hoặc cấu trúc phức tạp đều updatable theo cách này.
- Không dùng `SCROLL` cùng cơ chế khóa `FOR UPDATE` như một phương án tùy ý; các giới hạn của PostgreSQL về scrollable/locking cursor cần được tôn trọng.
- `WHERE CURRENT OF` cập nhật **dòng hiện tại**, không có nghĩa cập nhật tất cả dòng cursor sẽ đọc.

### 21.3. Có nên dùng cho cập nhật hàng loạt?

Nếu yêu cầu chỉ là đánh dấu mọi đơn `PENDING` trước một mốc ngày:

```sql
UPDATE cursor_lab_orders
SET processed_at = CURRENT_TIMESTAMP
WHERE status = 'PENDING'
  AND processed_at IS NULL;
```

thường là cách **set-based** rõ ràng hơn. `WHERE CURRENT OF` hữu ích trong những quy trình thực sự cần quyết định từng dòng, nhưng không nên dùng để thay mọi câu `UPDATE ... WHERE`.

## 22. Cursor, MVCC và dữ liệu đổi trong lúc duyệt

PostgreSQL dùng **MVCC** để quản lý phiên bản dòng và snapshot. Cursor là cách đọc một truy vấn, không phải một luồng “xem dữ liệu mới nhất mỗi khi fetch”.

### 22.1. Dòng mới được chèn sau khi mở cursor

Một câu hỏi thực tế:

> “Tôi đã mở cursor cho các đơn `PAID`. Giao dịch khác chèn thêm đơn `PAID` trong khi tôi đang `FETCH`. Cursor có tự lấy đơn mới không?”

**Không nên kỳ vọng như vậy.** Một cursor đọc query trong ngữ cảnh snapshot/transaction của nó; việc fetch tiếp không có nghĩa định kỳ chạy lại `SELECT` để thấy mọi dòng mới.

Nếu muốn xử lý **hàng đợi liên tục**, cần thiết kế batch/checkpoint hoặc cơ chế queue rõ ràng, chứ không giữ một cursor mở vô hạn để “theo dõi bảng”.

### 22.2. Điều kiện isolation

Trong PostgreSQL, cách snapshot được giữ/được xem chịu quy tắc isolation và thực thi cursor. `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` có hành vi đồng thời khác nhau.

Cursor không thay thế:

- Điều kiện lọc đúng.
- Khóa dòng khi cần cập nhật cạnh tranh.
- Kiểm tra phiên bản (`version_no`) để chống ghi đè.
- Retry toàn transaction sau một số lỗi đồng thời.

### 22.3. `FOR UPDATE` không khóa toàn bộ tương lai

Khóa những dòng hiện có không tự ngăn một giao dịch khác **chèn một dòng mới thỏa predicate** nếu không có cơ chế cô lập/khóa phù hợp. Nếu quy trình yêu cầu “xử lý **toàn bộ** đơn PAID tại một thời điểm nghiệp vụ”, cần xác định rõ mốc snapshot, hàng đợi và ranh giới giao dịch.

## 23. Quản lý cursor khi gặp lỗi

Lỗi có thể xảy ra giữa vòng lặp:

```text
OPEN cursor
    ↓
FETCH 1 → xử lý xong
FETCH 2 → xử lý xong
FETCH 3 → lỗi ràng buộc / lỗi SQL
    ↓
Ai sẽ giải phóng cursor và kết thúc transaction?
```

### 23.1. Lỗi SQL trong transaction PostgreSQL

Nếu một statement phát sinh lỗi trong transaction tường minh, PostgreSQL thường chuyển transaction sang trạng thái **aborted**. Các câu SQL tiếp theo có thể báo:

```text
current transaction is aborted, commands ignored
until end of transaction block
```

Khi đó phải `ROLLBACK` hoặc, nếu đã tạo `SAVEPOINT` phù hợp, phục hồi bằng `ROLLBACK TO SAVEPOINT`. **Không cố chạy tiếp `FETCH`/`CLOSE` như thể transaction vẫn bình thường.**

### 23.2. Dọn dẹp trong PL/pgSQL

Ở đường đi thành công, hãy `CLOSE` tường minh. Nếu lỗi làm cả transaction bị rollback, database sẽ dọn các cursor thông thường gắn với transaction đó.

Với mã có `EXCEPTION`/subtransaction, thời điểm cursor được mở và khả năng portal tồn tại sau khi handler chạy có những quy tắc riêng. Không đơn giản viết `CLOSE c` trong mọi handler mà không xác nhận cursor **vẫn còn mở**; có thể lỗi chồng lỗi nếu portal đã bị dọn.

### 23.3. Phân biệt lỗi fetch hết dòng với lỗi SQL

- **Hết dòng**: trong PL/pgSQL, `FOUND = FALSE` ngay sau `FETCH`; đây là điều kiện kết thúc vòng lặp bình thường.
- **Lỗi SQL**: ví dụ cursor không tồn tại, sai kiểu dữ liệu, deadlock, vi phạm constraint; xử lý như lỗi, không biến tất cả thành “đã đọc hết”.

Một cursor đọc 0 dòng ngay từ đầu không phải lỗi, nhưng nếu nghiệp vụ bắt buộc phải có đối tượng cần xử lý, ứng dụng phải tự coi đó là điều kiện không đạt.

### 23.4. Tránh dọn dẹp bằng `COMMIT` khi gặp lỗi

Đóng cursor là giải phóng tài nguyên đọc; `COMMIT` là chấp nhận dữ liệu giao dịch. Khi thất bại trong quy trình **all-or-nothing**, không gọi `COMMIT` chỉ để “đóng cursor”. Hãy rollback transaction theo chính sách.

## 24. Xem các cursor đang mở trong session

PostgreSQL có system view **`pg_cursors`** để quan sát các cursor có thể thấy trong session hiện tại:

```sql
SELECT
    name,
    statement,
    is_holdable,
    is_scrollable,
    creation_time
FROM pg_cursors
ORDER BY creation_time;
```

### 24.1. Dùng để kiểm tra vòng đời

```sql
BEGIN;

DECLARE cur_inspect CURSOR FOR
SELECT order_id
FROM cursor_lab_orders
ORDER BY order_id;

SELECT name, is_holdable, is_scrollable
FROM pg_cursors
WHERE name = 'cur_inspect';
-- Cursor đang mở có thể xuất hiện.

CLOSE cur_inspect;

SELECT name
FROM pg_cursors
WHERE name = 'cur_inspect';
-- Không còn dòng tương ứng.

ROLLBACK;
```

### 24.2. Những giới hạn của `pg_cursors`

`pg_cursors` phản ánh cursor của **session hiện tại** mà PostgreSQL có thể báo cáo, không phải một bảng liệt kê mọi cursor đang mở ở tất cả connection trong server.

Trường `statement` là thông tin truy vấn được gắn với cursor, không phải chứng cứ rằng mọi dòng đã được đọc hay tổng dung lượng bộ nhớ đã dùng. Khi điều tra giữ cursor quá lâu, cần kết hợp trạng thái transaction, query thực tế và công cụ giám sát.

## 25. Cursor trong ứng dụng Java: JDBC `ResultSet`

Trong Java, một `ResultSet` cho phép đọc kết quả của một `SELECT` lần lượt:

```java
while (resultSet.next()) {
    long orderId = resultSet.getLong("order_id");
    // Xử lý dòng hiện tại.
}
```

Đây là **cursor-style iteration ở tầng API**, nhưng không được mặc định mọi `ResultSet` đều là một PostgreSQL server-side cursor thực thụ. Driver có thể đã tải toàn bộ kết quả vào bộ nhớ, hoặc dùng fetch theo batch tùy cấu hình.

### 25.1. JDBC streaming theo batch với PostgreSQL

Với **PostgreSQL JDBC driver (pgJDBC)**, để driver có thể dùng server-side cursor/fetch theo batch trong những điều kiện hỗ trợ, một cấu hình thường gặp là:

- Kết nối đang trong transaction, **autocommit tắt**.
- Statement/ResultSet phù hợp kiểu **forward-only**.
- `setFetchSize(n)` với `n > 0`.
- SQL là kiểu truy vấn mà driver cho phép áp dụng cơ chế fetch tương ứng.

Ví dụ Java minh họa (giả định có bảng `orders` dùng chung phù hợp trong database ứng dụng, **không phải bảng TEMP từ một session SQL editor khác**):

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderExporter {
    private final DataSource dataSource;

    public OrderExporter(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void exportPaidOrders() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            connection.setAutoCommit(false);

            try {
                String sql = """
                    SELECT order_id, customer_id, amount
                    FROM orders
                    WHERE status = ?
                    ORDER BY order_id
                    """;

                try (PreparedStatement statement =
                        connection.prepareStatement(
                            sql,
                            ResultSet.TYPE_FORWARD_ONLY,
                            ResultSet.CONCUR_READ_ONLY)) {

                    statement.setString(1, "PAID");
                    statement.setFetchSize(500);

                    try (ResultSet result = statement.executeQuery()) {
                        while (result.next()) {
                            long orderId = result.getLong("order_id");
                            long customerId =
                                result.getLong("customer_id");
                            java.math.BigDecimal amount =
                                result.getBigDecimal("amount");

                            // Xử lý hoặc ghi ra luồng đầu ra có kiểm soát.
                            // Tránh giữ mọi dòng trong một List lớn.
                            process(orderId, customerId, amount);
                        }
                    }
                }

                connection.commit();
            } catch (SQLException | RuntimeException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    failure.addSuppressed(rollbackFailure);
                }
                throw failure;
            }
        }
    }

    private void process(
            long orderId,
            long customerId,
            java.math.BigDecimal amount) {
        // Ví dụ điểm mở rộng cho bài học.
    }
}
```

Ví dụ dùng **Java text block** (`"""`), phù hợp Java 15+. Nếu dự án dùng Java cũ hơn, có thể thay bằng chuỗi ghép thông thường.

### 25.2. `setFetchSize(500)` có ý nghĩa gì?

Đây là **gợi ý/hợp đồng của JDBC driver** về số dòng lấy trong mỗi đợt. Với pgJDBC và cấu hình phù hợp, nó có thể khiến driver lấy từng batch từ database thay vì tải toàn bộ kết quả trước khi ứng dụng bắt đầu xử lý.

Nó **không** có nghĩa SQL chỉ xử lý 500 dòng, cũng không đảm bảo chính xác 500 dòng trong mọi lần trao đổi hoặc mọi phiên bản/kiểu statement của driver.

### 25.3. Tại sao `autoCommit=false` quan trọng với pgJDBC?

Cursor server-side cần transaction còn sống trong khi fetch. Nếu mỗi statement được commit tự động ngay khi thực thi, một cursor không holdable có thể không còn để fetch từng batch theo cơ chế driver sử dụng.

Do đó, trong nhiều trường hợp pgJDBC cần **autocommit tắt** để bật cursor-based fetching. Hãy xem cấu hình driver thực tế trước khi khẳng định một `ResultSet` đang streaming.

### 25.4. Vì sao dùng `try-with-resources`?

Nó bảo đảm các đối tượng `ResultSet`, `PreparedStatement` và `Connection` được đóng theo hợp đồng API ở các đường chạy bình thường hoặc có ngoại lệ.

Trong chương trình dùng connection pool, `connection.close()` thường có nghĩa **trả connection về pool**, không phải ngắt kết nối vật lý ngay lập tức. Nhưng vẫn phải **kết thúc transaction rõ ràng**; không lấy việc đóng connection thay cho chủ động commit/rollback.

### 25.5. Không tự điều khiển transaction nếu Spring đã sở hữu

Ví dụ trên là mô hình **JDBC tự quản lý local transaction**. Nếu ứng dụng đang chạy dưới `@Transactional` của Spring, không được sao chép việc `setAutoCommit(false)`, `commit()` và `rollback()` vào repository một cách tùy tiện.

Khi framework quản lý transaction, hãy dùng API data access và cách cấu hình fetch của framework/driver để các bước tham gia đúng transaction. Một `ResultSet` dùng ngoài transaction gốc hoặc trên connection khác có thể mất khả năng fetch.

## 26. Batch size, bộ nhớ và thời gian giữ transaction

Cursor và streaming được dùng nhiều khi kết quả lớn, nhưng phải cân bằng ba yếu tố:

```text
Batch nhỏ
  ├─ Ít bộ nhớ cho mỗi batch
  ├─ Nhiều round-trip mạng hơn
  └─ Có thể giữ transaction lâu nếu tổng dữ liệu lớn

Batch lớn
  ├─ Ít round-trip hơn
  ├─ Tốn bộ nhớ/đầu ra mỗi đợt hơn
  └─ Có thể làm tăng độ trễ trước khi xử lý xong một batch
```

Không có batch size tốt nhất cho mọi workload. Cần xét kích thước mỗi dòng, thời gian xử lý từng dòng, mạng, database, connection pool, snapshot và SLA.

### 26.1. Đừng giữ transaction mở khi chờ I/O ngoài DB

Nếu mã:

```text
BEGIN
  OPEN CURSOR
  FETCH 500
  gọi HTTP đến đối tác (chờ 20 giây)
  FETCH 500
  gửi email
  FETCH 500
COMMIT
```

thì transaction và kết nối có thể bị giữ trong thời gian dài. Với truy vấn khóa dòng, còn gây chờ khóa cho transaction khác.

Nên xem xét:

- Tiêu thụ/ghi kết quả nhanh, không giữ giao dịch khi chờ người dùng.
- Tách công việc ngoài DB khỏi transaction khi bảo toàn tính đúng nghiệp vụ cho phép.
- Dùng **checkpoint theo khóa và batch độc lập** nếu cần công việc dài có thể tiếp tục sau lỗi.
- Dùng hàng đợi/outbox hoặc job framework nếu cần xử lý liên dịch vụ.

### 26.2. Một cursor không phải hệ thống checkpoint

Nếu ứng dụng đọc tới order 1008 rồi connection bị mất, portal của cursor đó không còn để tiếp tục chính xác ở dòng tiếp theo. Muốn khởi động lại, cần cơ chế như:

```text
last_processed_order_id = 1008
```

được lưu bền vững theo thiết kế, rồi query tiếp:

```sql
SELECT order_id, customer_id, amount
FROM cursor_lab_orders
WHERE status = 'PAID'
  AND order_id > 1008
ORDER BY order_id
LIMIT 100;
```

Nhưng dữ liệu có thể được chèn/sửa trong khi job chạy, nên checkpoint phải đi cùng **quy tắc snapshot, thứ tự ổn định, idempotency và thời điểm dữ liệu**. Keyset pagination không tự giải quyết mọi vấn đề đồng thời.

## 27. Cursor so với xử lý theo tập hợp

### 27.1. Tình huống dùng SQL tập hợp

Ví dụ đánh dấu đã xử lý mọi đơn PAID trước tháng 8/2026:

```sql
BEGIN;

UPDATE cursor_lab_orders
SET processed_at = CURRENT_TIMESTAMP
WHERE status = 'PAID'
  AND ordered_at < TIMESTAMPTZ '2026-08-01 00:00:00+07'
  AND processed_at IS NULL
RETURNING order_id, processed_at;

ROLLBACK;
```

Đây là một câu DML mô tả tập đích. Database có thể tối ưu cách tìm dòng và cập nhật. `RETURNING` cho biết những dòng bị tác động trực tiếp.

### 27.2. Tình huống cần xử lý phức tạp từng dòng

Ví dụ mỗi đơn phải qua một thuật toán kiểm tra đặc biệt, gọi một hàm nội bộ trả trạng thái hoặc áp quy tắc phụ thuộc dữ liệu riêng. Một cursor hay `FOR record IN SELECT` có thể hợp lý nếu không diễn đạt được sạch bằng phép tập hợp.

**Nhưng không nên** để mỗi lần `FETCH` lại gọi API mạng trực tiếp trong transaction dài nếu có lựa chọn thiết kế đáng tin cậy hơn.

### 27.3. Nguy cơ N+1

Một thủ tục:

```text
SELECT 10000 khách
  → mỗi khách lại SELECT đơn hàng riêng
```

có thể tạo **10.001 truy vấn** thay vì một JOIN/tổng hợp set-based. Cursor không tự tránh N+1. Nếu vòng lặp thực hiện query phụ cho mỗi dòng, đánh giá khả năng **JOIN, aggregate, prefetch** hoặc xử lý theo batch.

### 27.4. Bảng quyết định

| Nhu cầu | Ưu tiên cân nhắc |
|---|---|
Tính tổng/đếm/nhóm | `SUM`, `COUNT`, `GROUP BY` |
| Đổi trạng thái nhiều dòng cùng quy tắc | `UPDATE ... WHERE ...` |
| Xóa hàng loạt theo điều kiện | `DELETE ... WHERE ...` với kiểm soát an toàn |
| Đọc nhiều dòng và xử lý trong một thủ tục | `FOR record IN SELECT` |
| Điều khiển vị trí đọc chủ động trong thủ tục | Cursor tường minh |
| Xuất kết quả lớn từ Java | JDBC streaming/fetch size phù hợp |
| Công việc chạy lại được sau sự cố | Batch theo khóa + checkpoint/idempotency |
| Truy vấn phân trang qua các request độc lập | Keyset pagination hoặc token truy vấn phù hợp |
| Cập nhật dòng hiện tại đang được cursor khóa | `WHERE CURRENT OF` nếu có yêu cầu thật |

## 28. Những lỗi thường gặp

| Hiểu nhầm/lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Dùng `OPEN c` như câu SQL độc lập | SQL PostgreSQL không dùng `OPEN` theo cách PL/pgSQL | SQL dùng `DECLARE c CURSOR`; PL/pgSQL dùng `OPEN` |
| Khai báo `CURSOR FOR` trong PL/pgSQL rồi `FETCH` luôn | Cursor chưa được mở | `OPEN` trước `FETCH` |
| `FETCH` sau `CLOSE` | Cursor không còn tồn tại | Chỉ fetch khi đang mở |
| `FETCH` sau `COMMIT` với cursor thường | Cursor đã hết hiệu lực | Kết thúc fetch trước commit, hoặc thiết kế `WITH HOLD` phù hợp |
| Trả `refcursor` từ function nhưng SQL client autocommit | Cursor bị đóng trước câu `FETCH` sau | Bọc lời gọi và fetch trong một transaction |
| Dùng connection khác để fetch | Không tìm thấy portal | Dùng cùng session/kết nối |
| Không kiểm tra `FOUND` | Có thể xử lý dữ liệu không hợp lệ khi hết dòng | `EXIT WHEN NOT FOUND` ngay sau `FETCH` |
| Câu SQL khác ghi đè `FOUND` trước khi kiểm tra | Không biết fetch đã hết | Kiểm tra/lưu `FOUND` ngay lập tức |
| `MOVE` rồi tưởng đã xử lý các dòng bị bỏ | Bỏ sót dữ liệu | Dùng `FETCH` khi cần giá trị |
| Quên `ORDER BY` nhưng dựa vào số thứ tự | Kết quả đọc có thể đổi | `ORDER BY` với khóa phân xử |
| Bật `SCROLL` cho mọi cursor | Có thể tăng nhu cầu tài nguyên/giới hạn hiệu năng | Dùng forward-only khi đủ |
| `FETCH ALL` kết quả rất lớn | Tải nhiều dữ liệu, mất lợi ích batch | `FETCH n` hoặc streaming |
| Dùng `refcursor := NULL` để đóng | Portal vẫn có thể tồn tại | `CLOSE` đúng cursor |
| Tưởng `CLOSE` là `COMMIT` | Dữ liệu chưa commit hoặc transaction vẫn mở | Quản lý transaction riêng |
| Giữ cursor mở khi chờ HTTP/UI | Giữ transaction/connection lâu, tăng lock contention | Thiết kế batch/outbox, đóng sớm |
| Dùng `WITH HOLD` để tránh mọi chi phí | Có thể cần vật liệu hóa kết quả | Đánh giá RAM/disk và vòng đời session |
| Tin cursor tự thấy dòng mới | Sai snapshot/ý nghĩa đồng thời | Thiết kế điểm chụp, batch hoặc queue |
| Dùng cursor cho `SUM` đơn giản | Mã dài, khó tối ưu | Dùng `SUM` set-based |
| Vòng cursor lại chạy query mỗi dòng | N+1, round-trip và CPU cao | JOIN/prefetch/batch |
| Bắt mọi lỗi rồi coi là hết dữ liệu | Nuốt lỗi thực thi | Phân biệt `FOUND=FALSE` với SQL exception |
| Quên dọn `ResultSet`/statement/connection | Rò rỉ tài nguyên/pool cạn | `try-with-resources`, commit/rollback đúng |
| Nghĩ `setFetchSize` luôn tạo server cursor | Tùy driver/autocommit/result-set mode | Kiểm tra cấu hình driver và plan/metrics |
| Tưởng `WHERE CURRENT OF` sửa mọi dòng cursor | Chỉ sửa dòng hiện tại | Định nghĩa mục tiêu và row count rõ |

## 29. Bài tập tự luyện

Các bài dưới đây dùng **bảng `cursor_lab_orders` ở mục 3**. Với bài có thay đổi dữ liệu, hãy dùng `BEGIN ... ROLLBACK` hoặc phiên thử riêng. Một số bài chỉ yêu cầu đọc code và giải thích; không cần cố tình tạo lỗi trong một transaction đang làm công việc khác.

### Bài 1 — Định nghĩa cursor

Cursor có phải một bảng mới được lưu bền vững trong database không? Khác biệt chính giữa cursor và một câu `SELECT` trả kết quả một lần là gì?

### Bài 2 — Vòng đời năm bước

Hãy liệt kê các bước khái niệm khai báo, mở, đọc, đóng, giải phóng. Trong PostgreSQL SQL cursor, bước nào được gộp với `DECLARE`?

### Bài 3 — Cursor SQL đầu tiên

Viết một transaction khai báo `cur_paid` để lấy `order_id, amount` của các đơn `PAID` theo `order_id`, đọc hai dòng bằng `FETCH NEXT`, đóng cursor và `ROLLBACK`.

### Bài 4 — Những dòng đầu tiên

Với dữ liệu mẫu, hai lần `FETCH NEXT` đầu tiên trên cursor `PAID ORDER BY order_id` trả những ID và amount nào?

### Bài 5 — Batch `FETCH`

Nếu gọi `FETCH FORWARD 3` liên tiếp ba lần trên tám đơn `PAID`, mỗi lần trả bao nhiêu dòng? Các ID ở batch cuối?

### Bài 6 — `MOVE`

Sau khi `FETCH NEXT` lấy 1001, chạy `MOVE FORWARD 2` rồi `FETCH NEXT`. Dòng cuối được trả là dòng nào? Hai dòng bị bỏ qua có được gửi cho chương trình không?

### Bài 7 — SCROLL

Viết cursor `SCROLL` lấy đơn `PAID` theo ID, sau đó đọc dòng thứ tư và dòng cuối. Giải thích vì sao cần `ORDER BY` để nói “dòng thứ tư” theo ý nghĩa nghiệp vụ.

### Bài 8 — `CLOSE`

Điều gì xảy ra nếu ứng dụng gọi `FETCH` sau khi đã `CLOSE` cursor? `CLOSE` có commit các câu `UPDATE` đã thực hiện trong cùng transaction không?

### Bài 9 — Transaction

Giải thích vì sao cursor thông thường không fetch tiếp được sau khi transaction khai báo `COMMIT`. Nếu cần fetch sau commit trên cùng session, PostgreSQL hỗ trợ mô hình nào?

### Bài 10 — `WITH HOLD`

Viết ví dụ `DECLARE ... CURSOR WITH HOLD`, fetch hai dòng, commit, fetch tiếp, rồi close. Nêu ít nhất hai giới hạn của mô hình này.

### Bài 11 — PL/pgSQL

Viết `DO $$ ... $$` dùng bound cursor `cur_paid`, `OPEN`, `FETCH INTO`, `EXIT WHEN NOT FOUND`, `CLOSE` để đếm tám đơn PAID.

### Bài 12 — `FOUND`

Vì sao phải đặt `EXIT WHEN NOT FOUND` ngay sau `FETCH`? Điều gì có thể xảy ra nếu chen `PERFORM 1` giữa hai lệnh?

### Bài 13 — `record`

Viết ví dụ PL/pgSQL lấy `order_id, customer_id, amount` bằng một biến `record` thay vì ba biến riêng. Trường dữ liệu được truy cập bằng cách nào?

### Bài 14 — Tổng tiền

Tổng amount các đơn PAID bằng bao nhiêu? Viết một câu SQL set-based cho cùng kết quả. Vì sao câu đó thường nên ưu tiên hơn cursor nếu mục tiêu chỉ tính tổng?

### Bài 15 — Cursor tham số

Viết bound cursor có tham số `p_min_amount` để chỉ đọc đơn `PAID` có amount từ 200 trở lên. Những ID nào xuất hiện trên dữ liệu gốc?

### Bài 16 — Dynamic cursor

Sử dụng `OPEN refcursor FOR EXECUTE ... USING` để đọc đơn có `status = 'PAID'` và `amount >= 200` mà không nối trực tiếp các giá trị vào chuỗi SQL.

### Bài 17 — `FOR record IN SELECT`

Viết lại vòng đọc trong bài 11 bằng `FOR r IN SELECT ... LOOP`. Cách nào cần bạn tự `OPEN` và `CLOSE`?

### Bài 18 — Function trả `refcursor`

Một function trả cursor đã mở nhưng caller gọi nó ở autocommit rồi thực hiện `FETCH` trong một câu SQL khác. Vì sao có thể không còn cursor? Cách gọi đúng là gì?

### Bài 19 — `WHERE CURRENT OF`

Viết transaction dùng cursor trên đơn `PENDING ORDER BY order_id FOR UPDATE`, fetch một dòng rồi cập nhật `processed_at` của dòng hiện tại bằng `WHERE CURRENT OF`. Dòng nào được sửa trên dữ liệu gốc?

### Bài 20 — Session và connection pool

Connection A mở cursor tên `export_cur`; connection B nhận cùng tên rồi chạy `FETCH`. Có được không? Vì sao việc nhiều connection cùng trỏ một PostgreSQL database không đủ?

### Bài 21 — Dữ liệu thay đổi đồng thời

Một transaction khác thêm đơn `PAID` sau khi bạn mở cursor. Bạn có thể khẳng định cursor sẽ đọc thêm đơn mới ở cuối không? Muốn xây worker luôn xử lý công việc mới nên thiết kế theo hướng nào?

### Bài 22 — `pg_cursors`

Viết truy vấn PostgreSQL xem các cursor đang mở trong session hiện tại. `pg_cursors` có thể cho bạn thấy cursor của mọi session khác không?

### Bài 23 — JDBC

Trong pgJDBC, hãy nêu những điều kiện phổ biến để `setFetchSize(500)` có thể giúp driver fetch từng batch qua server-side cursor. Vì sao `ResultSet.next()` không tự bảo đảm streaming?

### Bài 24 — Lỗi giữa vòng lặp

Trong transaction PostgreSQL, một câu SQL bên trong vòng cursor vi phạm ràng buộc. Tại sao không nên coi đó là “cursor hết dòng”? Khi nào cần `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT`?

### Bài 25 — Cursor hay `UPDATE`?

Yêu cầu: đánh dấu mọi đơn `PAID` tháng 7/2026 đã được xử lý. Bạn chọn cursor cập nhật từng dòng hay một câu `UPDATE ... WHERE ...`? Nêu lý do và mẫu truy vấn.

### Bài 26 — Streaming không phải checkpoint

Ứng dụng đọc tới order 1008 rồi mất kết nối. Vì sao tên cursor không giúp khôi phục tiếp từ 1009? Hãy đề xuất một cơ chế checkpoint có khóa ổn định và nêu rủi ro khi dữ liệu thay đổi giữa các batch.

### Bài 27 — Resource leak

Một service mở cursor và giữ transaction trong lúc chờ HTTP 30 giây cho mỗi dòng. Nêu ba tác động vận hành có thể xảy ra và cách thiết kế lại.

### Bài 28 — SQL vs PL/pgSQL

Điền vào bảng:

| Ngữ cảnh | Cách khai báo/mở | Đọc | Kết thúc |
|---|---|---|---|
| SQL cursor | ... | ... | ... |
| PL/pgSQL bound cursor | ... | ... | ... |
| PL/pgSQL `FOR r IN SELECT` | ... | ... | ... |

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:** Cursor là trạng thái/portal của truy vấn, không phải một bảng bền vững như `CREATE TABLE`. Cursor cho phép giữ vị trí và fetch từng bước; một `SELECT` thông thường trả kết quả cho client theo cơ chế driver mà không cần caller tự điều khiển một cursor có tên.

**Bài 2:** Khai báo → mở → đọc → đóng → giải phóng. Với **SQL PostgreSQL**, `DECLARE c CURSOR FOR ...` vừa định nghĩa vừa mở cursor; không có SQL `OPEN c` riêng. Với PL/pgSQL, `OPEN` thực hiện ở thân khối sau khai báo biến cursor.

**Bài 3:**

```sql
BEGIN;
DECLARE cur_paid CURSOR FOR
SELECT order_id, amount
FROM cursor_lab_orders
WHERE status = 'PAID'
ORDER BY order_id;
FETCH NEXT FROM cur_paid;
FETCH NEXT FROM cur_paid;
CLOSE cur_paid;
ROLLBACK;
```

**Bài 4:** Lần một: `1001`, amount `150`. Lần hai: `1003`, amount `320`.

**Bài 5:** Ba batch có số dòng **3, 3, 2**. Batch cuối: `1011` và `1012`.

**Bài 6:** Dòng cuối trả `1006`. `MOVE FORWARD 2` bỏ qua vị trí của `1003`, `1004` mà không gửi giá trị hai dòng đó cho chương trình.

**Bài 7:**

```sql
BEGIN;
DECLARE c SCROLL CURSOR FOR
SELECT order_id, amount
FROM cursor_lab_orders
WHERE status = 'PAID'
ORDER BY order_id;
FETCH ABSOLUTE 4 FROM c;
FETCH LAST FROM c;
CLOSE c;
ROLLBACK;
```

Dòng thứ tư là `1006`, cuối cùng `1012`. Không có `ORDER BY`, thứ tự logic của kết quả không được bảo đảm.

**Bài 8:** `FETCH` sau `CLOSE` không có cursor hợp lệ và gây lỗi. `CLOSE` chỉ dọn cursor, không commit thay đổi; transaction vẫn cần `COMMIT` hoặc `ROLLBACK`.

**Bài 9:** Cursor thường gắn với transaction và hết hiệu lực khi commit. Muốn tiếp tục fetch sau commit **trên cùng session**, PostgreSQL có `DECLARE ... CURSOR WITH HOLD ...`; phải cân nhắc chi phí materialization và đóng cursor.

**Bài 10:**

```sql
BEGIN;
DECLARE c CURSOR WITH HOLD FOR
SELECT order_id FROM cursor_lab_orders
WHERE status = 'PAID' ORDER BY order_id;
FETCH 2 FROM c;
COMMIT;
FETCH 2 FROM c;
CLOSE c;
```

Giới hạn: dùng cùng session; có thể giữ kết quả ở bộ nhớ/đĩa; không dùng cho mọi trường hợp khóa dòng; không tồn tại sau session kết thúc.

**Bài 11:**

```sql
DO $$
DECLARE
    v_id INTEGER;
    n INTEGER := 0;
    c CURSOR FOR
        SELECT order_id FROM cursor_lab_orders
        WHERE status = 'PAID' ORDER BY order_id;
BEGIN
    OPEN c;
    LOOP
        FETCH c INTO v_id;
        EXIT WHEN NOT FOUND;
        n := n + 1;
    END LOOP;
    CLOSE c;
    RAISE NOTICE 'Count=%', n;
END $$;
```

Kết quả `n=8`.

**Bài 12:** `FOUND` phản ánh trạng thái lệnh PL/pgSQL gần nhất có thể cập nhật nó. Sau `FETCH` không có dòng, phải thoát ngay. `PERFORM 1` có thể đặt `FOUND=TRUE` và làm mất tín hiệu “đã hết”.

**Bài 13:**

```sql
DO $$
DECLARE
    r RECORD;
    c CURSOR FOR
        SELECT order_id, customer_id, amount
        FROM cursor_lab_orders
        WHERE status = 'PAID'
        ORDER BY order_id;
BEGIN
    OPEN c;
    LOOP
        FETCH c INTO r;
        EXIT WHEN NOT FOUND;
        RAISE NOTICE '%, %, %',
            r.order_id, r.customer_id, r.amount;
    END LOOP;
    CLOSE c;
END $$;
```

**Bài 14:** Tổng `1700`:

```sql
SELECT SUM(amount)
FROM cursor_lab_orders
WHERE status = 'PAID';
```

`SUM` set-based ngắn và để database tối ưu hơn cách lặp cộng thủ công.

**Bài 15:** Dùng:

```sql
cur CURSOR (p_min_amount NUMERIC) FOR
    SELECT order_id, amount
    FROM cursor_lab_orders
    WHERE status = 'PAID'
      AND amount >= p_min_amount
    ORDER BY order_id;
```

Trong thân PL/pgSQL, `OPEN cur(200); ... CLOSE cur;`. Kết quả ID **1003, 1006, 1008**.

**Bài 16:**

```sql
DO $$
DECLARE
    c REFCURSOR;
    r RECORD;
    s TEXT := 'PAID';
    m NUMERIC := 200;
BEGIN
    OPEN c FOR EXECUTE
        'SELECT order_id, amount
         FROM cursor_lab_orders
         WHERE status = $1 AND amount >= $2
         ORDER BY order_id'
    USING s, m;
    LOOP
        FETCH c INTO r;
        EXIT WHEN NOT FOUND;
        RAISE NOTICE '%', r.order_id;
    END LOOP;
    CLOSE c;
END $$;
```

**Bài 17:**

```sql
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT order_id FROM cursor_lab_orders
        WHERE status = 'PAID'
        ORDER BY order_id
    LOOP
        RAISE NOTICE '%', r.order_id;
    END LOOP;
END $$;
```

Vòng `FOR ... IN SELECT` không cần tự gọi `OPEN`/`CLOSE`; cursor tường minh cần các bước đó.

**Bài 18:** Một SQL client autocommit ngay sau lời gọi function có thể đóng cursor không holdable. Cần cùng session và transaction:

```sql
BEGIN;
SELECT cursor_lab_open_paid(200);
FETCH ALL FROM cursor_lab_paid_export;
CLOSE cursor_lab_paid_export;
COMMIT;
```

**Bài 19:**

```sql
BEGIN;
DECLARE c CURSOR FOR
SELECT order_id, status
FROM cursor_lab_orders
WHERE status = 'PENDING'
ORDER BY order_id
FOR UPDATE;
FETCH NEXT FROM c;
UPDATE cursor_lab_orders
SET processed_at = CURRENT_TIMESTAMP
WHERE CURRENT OF c
RETURNING order_id;
CLOSE c;
ROLLBACK;
```

Dòng hiện tại đầu tiên là **1002**.

**Bài 20:** Không. Portal thuộc session kết nối A; B không có cursor đó. Tên giống nhau không liên kết hai local transaction hay hai session.

**Bài 21:** Không thể khẳng định cursor sẽ thấy đơn vừa chèn. Cursor đọc truy vấn theo snapshot/ngữ cảnh của nó, không phải feed tự làm mới. Worker liên tục nên dùng queue, batch truy vấn theo mốc, checkpoint và idempotency.

**Bài 22:**

```sql
SELECT name, statement, is_holdable, is_scrollable
FROM pg_cursors;
```

Đây là các cursor của **session hiện tại** mà PostgreSQL báo cáo, không phải toàn server.

**Bài 23:** Với pgJDBC, thường cần transaction hoạt động (`autoCommit=false`), result set forward-only, fetch size dương và truy vấn được driver hỗ trợ. `ResultSet.next()` là API đọc từng dòng nhưng driver có thể đã buffer toàn bộ kết quả nếu không cấu hình phù hợp.

**Bài 24:** Lỗi SQL và “fetch hết dòng” là hai trường hợp khác nhau. Nếu transaction PostgreSQL bị aborted do SQL error, phải rollback hoặc phục hồi bằng savepoint phù hợp; không che lỗi rồi tiếp tục dùng cursor không còn hợp lệ.

**Bài 25:** Một câu set-based thường phù hợp:

```sql
BEGIN;
UPDATE cursor_lab_orders
SET processed_at = CURRENT_TIMESTAMP
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-07-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-08-01 00:00:00+07'
  AND processed_at IS NULL
RETURNING order_id;
ROLLBACK;
```

Một câu DML rõ tập đích và transaction; không cần `FETCH` từng dòng chỉ để gán cùng một giá trị.

**Bài 26:** Tên cursor không tồn tại bền vững sau khi connection/session mất. Có thể lưu `last_processed_order_id=1008`, rồi đọc `WHERE order_id>1008 ORDER BY order_id LIMIT n`. Cần bảo đảm snapshot/phạm vi dữ liệu, xử lý dòng mới chen trước khóa và idempotency khi retry.

**Bài 27:** Giữ transaction và connection lâu, có thể giữ row lock/snapshot làm chậm transaction khác, gây thiếu connection pool hoặc tăng áp lực MVCC. Thiết kế lại theo batch ngắn, dọn cursor sớm, không chờ API ngoài trong transaction, dùng queue/outbox khi phù hợp.

**Bài 28:**

| Ngữ cảnh | Khai báo/mở | Đọc | Kết thúc |
|---|---|---|---|
| SQL cursor | `BEGIN; DECLARE c CURSOR FOR SELECT ...` | `FETCH NEXT FROM c` | `CLOSE c; COMMIT` |
| PL/pgSQL bound cursor | `DECLARE c CURSOR FOR ...; BEGIN OPEN c;` | `FETCH c INTO var; EXIT WHEN NOT FOUND;` | `CLOSE c; END` |
| PL/pgSQL `FOR r IN SELECT` | `FOR r IN SELECT ... LOOP` | Tự gán `r` từng vòng | `END LOOP`, tự quản lý cursor |

</details>

## 30. Checklist vận hành cursor

Trước khi thêm một cursor vào stored procedure hoặc ứng dụng, hãy hỏi:

1. **Có thực sự cần duyệt từng dòng không?** `UPDATE`, `SUM`, `JOIN`, `GROUP BY` hoặc window function có giải quyết gọn hơn không?
2. **Đây là SQL cursor hay PL/pgSQL cursor?** `DECLARE` có mở ngay hay phải có `OPEN`?
3. **Một dòng kết quả gồm những cột nào?** `FETCH ... INTO` có đúng thứ tự/kiểu, hoặc `record` có tên trường phù hợp không?
4. **Làm sao phát hiện đã hết dòng?** `FOUND` ngay sau `FETCH` hay số dòng trả về của client?
5. **Thứ tự có xác định không?** `ORDER BY` có khóa phân xử khi cần không?
6. **Có cần đọc lùi không?** Nếu chỉ đọc tiến, vì sao không dùng forward-only?
7. **Cursor sống trong transaction/session nào?** Caller có giữ đúng connection trong thời gian fetch không?
8. **Có cần `WITH HOLD` không?** Nếu có, đã tính chi phí materialization và thời điểm đóng chưa?
9. **Ai đóng cursor?** Có đường kết thúc thành công và xử lý lỗi/rollback rõ ràng không?
10. **Có cập nhật dòng đang duyệt không?** Cơ chế khóa, `WHERE CURRENT OF` và concurrency đã rõ chưa?
11. **Có nguy cơ giữ transaction quá lâu không?** Fetch size và thao tác ngoài database có hợp lý không?
12. **Có cần phục hồi sau mất kết nối không?** Cursor không thay checkpoint bền vững.
13. **Ứng dụng có framework transaction manager không?** Không tự commit/rollback connection thuộc quyền framework.
14. **Có thể kiểm tra trạng thái?** Dùng `pg_cursors`, log và metrics phù hợp mà không lộ dữ liệu nhạy cảm.

### 30.1. Ba mẫu nhớ nhanh

**Mẫu SQL cursor:**

```sql
BEGIN;
DECLARE c CURSOR FOR
SELECT order_id FROM cursor_lab_orders ORDER BY order_id;
FETCH 10 FROM c;
CLOSE c;
COMMIT;
```

**Mẫu PL/pgSQL cursor tường minh:**

```sql
DO $$
DECLARE
    r RECORD;
    c CURSOR FOR
        SELECT order_id FROM cursor_lab_orders ORDER BY order_id;
BEGIN
    OPEN c;
    LOOP
        FETCH c INTO r;
        EXIT WHEN NOT FOUND;
        RAISE NOTICE '%', r.order_id;
    END LOOP;
    CLOSE c;
END $$;
```

**Mẫu PL/pgSQL được ưu tiên khi chỉ lặp:**

```sql
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT order_id FROM cursor_lab_orders ORDER BY order_id
    LOOP
        RAISE NOTICE '%', r.order_id;
    END LOOP;
END $$;
```

## 31. Kết luận

Cursor là công cụ để **đọc và xử lý kết quả truy vấn theo từng bước**, đặc biệt hữu ích trong thủ tục, hàm và ứng dụng cần streaming hoặc điều khiển vị trí. Nhưng cursor chỉ thực sự an toàn khi vòng đời của nó được thiết kế rõ:

```text
Khai báo → Mở → FETCH đến khi hết → CLOSE → Giải phóng
               │
               ├── Kiểm tra dòng có tồn tại
               ├── Tôn trọng thứ tự và snapshot
               └── Giữ đúng transaction/session
```

Ba quy tắc đáng nhớ nhất:

1. **Phân biệt cú pháp và vòng đời:** SQL PostgreSQL dùng `DECLARE CURSOR` để tạo/mở; PL/pgSQL khai báo biến rồi mới `OPEN`. Trong vòng lặp, `FETCH ... INTO` đi kèm `EXIT WHEN NOT FOUND`.
2. **Giải phóng đúng tài nguyên:** `CLOSE` cursor khi dùng xong; `COMMIT`/`ROLLBACK` quản lý transaction riêng. Cursor thường không qua được kết thúc transaction, còn `WITH HOLD` có phạm vi và chi phí đặc biệt.
3. **Không dùng cursor thay mọi phép tập hợp:** Trước khi viết vòng lặp từng dòng, hãy cân nhắc `UPDATE ... WHERE`, `SUM`, `GROUP BY`, `FOR ... IN SELECT` hoặc batch theo khóa. Một giải pháp tốt phải vừa đúng dữ liệu, vừa quản lý được tài nguyên và có thể phục hồi khi gặp lỗi.

Khi bạn biết **cursor nào đang mở, vị trí nào vừa đọc, ai sở hữu transaction và lúc nào tài nguyên được đóng**, các thủ tục xử lý từng dòng sẽ dễ hiểu, dễ kiểm chứng và ít gây sự cố hơn.
