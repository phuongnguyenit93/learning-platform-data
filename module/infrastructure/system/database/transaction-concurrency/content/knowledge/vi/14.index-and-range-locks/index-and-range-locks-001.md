# Điều kiện truy vấn và đường truy cập quyết định tập dữ liệu được chạm tới

Trong cơ sở dữ liệu đồng thời, một câu truy vấn không chỉ xác định **hàng nào cần trả về**. Nó còn ảnh hưởng đến cách DBMS tìm hàng, những khóa hoặc vùng dữ liệu mà DBMS phải bảo vệ, và các giao dịch khác có thể tiếp tục hay phải chờ. Hai câu truy vấn có cùng kết quả logic nhưng dùng đường truy cập khác nhau có thể tạo ra phạm vi đọc, phạm vi khóa và mức tranh chấp rất khác nhau.

Điều này đặc biệt quan trọng với khóa phạm vi (range lock), gap lock, next-key lock và predicate lock. Những cơ chế này giúp bảo vệ một điều kiện truy vấn trước các thay đổi đồng thời, kể cả trường hợp một hàng mới được chèn vào vùng dữ liệu mà truy vấn đang quan tâm. Phạm vi được bảo vệ phụ thuộc vào điều kiện lọc, chỉ mục, thứ tự cột trong chỉ mục, kế hoạch thực thi và cách DBMS triển khai isolation level.

Một nguyên tắc cần nhớ: **điều kiện truy vấn mô tả dữ liệu cần tìm; đường truy cập quyết định DBMS phải đi qua những phần dữ liệu nào để tìm và bảo vệ kết quả đó.** Vì thế, khi phân tích blocking hoặc phantom, chỉ nhìn vào câu `WHERE` là chưa đủ. Cần xem chỉ mục và execution plan của DBMS.

## 1. Tập kết quả và tập dữ liệu được chạm tới

Giả sử bảng `orders` có một triệu hàng, trong đó chỉ có 20 hàng thuộc khách hàng 42:

```sql
SELECT order_id, created_at, total
FROM orders
WHERE customer_id = 42;
```

Nếu có chỉ mục phù hợp trên `customer_id`, DBMS có thể tìm đến vùng chỉ mục chứa khóa 42 rồi truy cập các hàng tương ứng. Nếu không có chỉ mục, DBMS có thể phải quét phần lớn hoặc toàn bộ bảng để tìm 20 hàng đó.

Hai kế hoạch có thể trả về cùng 20 hàng, nhưng số trang và mục chỉ mục được đọc rất khác nhau:

```text
Có index trên customer_id:
  Index seek -> các entry customer_id = 42 -> các hàng phù hợp

Không có index phù hợp:
  Scan nhiều hàng/trang -> kiểm tra customer_id từng hàng -> giữ 20 kết quả
```

Với một truy vấn đọc thông thường, khác biệt này chủ yếu thể hiện qua CPU, I/O và thời gian chạy. Khi truy vấn cần khóa dữ liệu, hoặc chạy dưới isolation level bảo vệ predicate/range, đường truy cập còn có thể ảnh hưởng đến lượng tài nguyên bị khóa hoặc vùng mà DBMS theo dõi xung đột.

Phải phân biệt ba tập sau:

- **Tập kết quả (result set):** những hàng thỏa điều kiện và được trả về.
- **Tập dữ liệu được quét (scan set):** những entry, hàng hoặc trang DBMS phải xem xét theo execution plan, bao gồm cả dữ liệu cuối cùng bị loại bởi điều kiện còn lại.
- **Tập tài nguyên được bảo vệ (lock/predicate protection set):** những hàng, khóa chỉ mục, khoảng khóa hoặc predicate mà DBMS bảo vệ để duy trì isolation.

Ba tập này có liên quan nhưng không nhất thiết trùng nhau. Một hàng bị đọc trong quá trình scan có thể không nằm trong kết quả cuối cùng. Một predicate lock có thể biểu diễn điều kiện truy vấn ở mức rộng hơn một hàng cụ thể. Một row lock có thể chỉ khóa các hàng trả về, trong khi việc ngăn phantom cần cơ chế bảo vệ khoảng dữ liệu.

## 2. Điều kiện WHERE ảnh hưởng đến phạm vi tìm kiếm

Điều kiện lọc càng cụ thể và có thể tận dụng chỉ mục, DBMS càng có cơ hội truy cập một vùng dữ liệu nhỏ. Ngược lại, điều kiện rộng hoặc khó dùng chỉ mục có thể buộc DBMS quét nhiều hàng hơn.

Ví dụ, với chỉ mục B-tree trên `order_id`:

```sql
SELECT *
FROM orders
WHERE order_id = 500;
```

Điều kiện bằng trên khóa chỉ mục có thể tìm một entry nhanh. Trong khi đó:

```sql
SELECT *
FROM orders
WHERE order_id BETWEEN 500 AND 900;
```

DBMS phải tìm và duyệt một dải khóa. Dải này có thể chứa nhiều hàng và nhiều khoảng giữa các khóa hiện có. Nếu truy vấn chạy ở isolation level cần ngăn phantom, hệ quản trị có thể phải bảo vệ toàn bộ dải liên quan để một giao dịch khác không chèn một hàng mới thỏa điều kiện trong khi transaction hiện tại còn phụ thuộc vào kết quả.

Điều kiện trên cột không có chỉ mục phù hợp có thể dẫn đến scan. Ví dụ:

```sql
SELECT *
FROM orders
WHERE status = 'PENDING';
```

Nếu không có chỉ mục hữu ích trên `status`, DBMS có thể phải xem xét nhiều hàng. Trong một số DBMS và isolation level, điều đó có thể làm tăng phạm vi khóa hoặc predicate protection, tăng khả năng các thao tác khác bị chặn hoặc bị coi là xung đột.

## 3. Index seek và scan khác nhau thế nào?

**Index seek** định vị một vị trí hoặc dải khóa trong chỉ mục rồi đi qua phần liên quan. **Index scan** duyệt một phần lớn hoặc toàn bộ chỉ mục. **Table/heap scan** duyệt các trang dữ liệu của bảng để kiểm tra hàng.

| Đường truy cập | Cách DBMS tìm dữ liệu | Tác động thường gặp |
|---|---|---|
| Index seek | Đi đến khóa hoặc khoảng khóa phù hợp trong B-tree | Thường giảm số entry cần xem xét khi điều kiện chọn lọc tốt |
| Index range scan | Bắt đầu tại khóa đầu rồi duyệt đến khi hết dải | Phạm vi được duyệt gắn với biên range và thứ tự khóa |
| Index full scan | Duyệt nhiều hoặc toàn bộ entry của chỉ mục | Có thể đọc nhiều entry dù kết quả cuối nhỏ |
| Table/heap scan | Duyệt nhiều hoặc toàn bộ trang bảng | Có thể chạm đến rất nhiều hàng và trang |

Một index seek không tự động đồng nghĩa với chỉ khóa đúng một hàng. Điều kiện có thể xác định cả một dải, hoặc một phần của khóa ghép. Ngược lại, một scan không nhất thiết luôn khóa toàn bảng: hành vi phụ thuộc DBMS, isolation level, loại truy vấn và chính sách khóa. Tuy vậy, scan rộng thường làm tăng số tài nguyên phải xem xét và có thể làm tăng tranh chấp.

Execution plan cho biết DBMS thực sự dùng đường truy cập nào. Khi điều tra lock footprint, cần xem operator seek/scan, điều kiện seek, predicate còn lại (residual predicate), thứ tự join và loại chỉ mục được dùng.

## 4. Chỉ mục ghép và thứ tự cột

Chỉ mục ghép (composite index) chứa nhiều cột theo một thứ tự xác định. Thứ tự đó ảnh hưởng đến những điều kiện có thể định vị một vùng liên tục trong B-tree.

Giả sử tạo chỉ mục:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
```

Truy vấn sau có thể dùng phần đầu của chỉ mục để định vị khách hàng rồi duyệt khoảng thời gian:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-02-01 00:00:00';
```

Với thứ tự `(customer_id, created_at)`, DBMS có thể tìm nhóm khóa của khách hàng 42 rồi duyệt dải `created_at` trong nhóm đó. Nếu chỉ mục có thứ tự `(created_at, customer_id)`, điều kiện thời gian có thể trở thành phần định vị chính và `customer_id` được kiểm tra sau, tùy optimizer và DBMS.

Ví dụ minh họa:

```text
Index (customer_id, created_at)

(41, 2026-01-03)
(41, 2026-01-12)
(42, 2026-01-02)  <-- bắt đầu vùng cần tìm
(42, 2026-01-18)
(42, 2026-01-29)  <-- kết thúc vùng cần tìm
(43, 2026-01-05)
```

Chỉ mục phù hợp có thể thu hẹp vùng scan và vùng khóa. Tuy nhiên, không phải mọi điều kiện trên cột thứ hai đều được dùng như một seek range nếu cột đầu không được ràng buộc phù hợp. Quy tắc chính xác còn phụ thuộc optimizer, thống kê, toán tử so sánh và loại index.

### 4.1. Điều kiện bằng và điều kiện range

Với B-tree ghép `(a, b, c)`, truy vấn có điều kiện bằng trên `a`, bằng hoặc range trên `b` thường có thể định vị một dải tương đối hẹp. Khi một cột đã dùng điều kiện range, điều kiện trên các cột sau có thể chỉ còn được kiểm tra như residual predicate trong một số kế hoạch.

Ví dụ:

```sql
-- Có thể định vị tốt theo (a, b)
WHERE a = 10 AND b >= 100 AND b < 200 AND c = 'OPEN'

-- Thiếu điều kiện trên cột đầu a
WHERE b >= 100 AND b < 200
```

Trong truy vấn thứ hai, index `(a, b, c)` không nhất thiết giúp tìm một dải liên tục theo `b`; DBMS có thể cần scan nhiều phần của index hoặc chọn một index khác.

### 4.2. Index covering

Một covering index chứa đủ cột cần cho truy vấn, giúp DBMS có thể trả kết quả từ chỉ mục mà không cần truy cập bảng trong một số kế hoạch. Điều này có thể giảm I/O và số trang dữ liệu phải đọc. Nhưng nó không có nghĩa không còn lock hoặc không còn xung đột: các quy tắc khóa trên index, hàng và isolation level vẫn áp dụng.

## 5. Điều kiện không sargable có thể làm đường truy cập rộng hơn

Một predicate được gọi là sargable khi DBMS có thể dùng nó để tìm kiếm hiệu quả qua chỉ mục. Việc áp dụng hàm hoặc phép biến đổi lên cột có thể khiến điều kiện khó dùng index thông thường.

Ví dụ với index trên `created_at`:

```sql
-- Thường khó dùng index B-tree thông thường làm seek theo created_at
WHERE DATE(created_at) = DATE '2026-11-14'
```

Có thể viết thành khoảng nửa mở:

```sql
WHERE created_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00'
```

Điều kiện khoảng cho phép B-tree trên `created_at` định vị dải thời gian. Cách viết này cũng tránh vấn đề biên cuối ngày và thường dễ tối ưu hơn. Cần chú ý kiểu dữ liệu và múi giờ nếu cột là timestamp có timezone.

Một số dạng predicate khác có thể làm giảm khả năng dùng index:

- Dùng hàm trên cột mà không có functional index hoặc computed column index phù hợp.
- Ép kiểu ngầm khiến DBMS phải chuyển đổi cột thay vì giá trị tham số.
- Tìm chuỗi bằng `LIKE '%text'` với wildcard ở đầu, khi index B-tree thông thường không hỗ trợ mẫu đó.
- Dùng phép `OR` trên nhiều cột mà optimizer không thể kết hợp index hiệu quả.
- Dùng toán tử hoặc biểu thức không tương thích với loại index hiện có.

Không phải các dạng này luôn buộc table scan. DBMS có thể dùng bitmap, index union, expression index hoặc chiến lược khác. Cần kiểm tra execution plan thay vì suy luận chỉ từ cú pháp.

## 6. Vì sao cần khóa khoảng và bảo vệ predicate?

Khóa hàng hiện có chỉ bảo vệ những hàng đã được tìm thấy. Nhưng một điều kiện truy vấn còn có thể bị thay đổi bởi một thao tác `INSERT` tạo hàng mới thỏa predicate, hoặc `UPDATE` làm một hàng chuyển vào vùng kết quả. Đây là hiện tượng phantom.

Giả sử T1 kiểm tra các đơn đặt hàng trong khoảng số 100 đến 200:

```sql
SELECT *
FROM orders
WHERE order_no BETWEEN 100 AND 200;
```

T1 thấy 10 hàng. Trong khi T1 vẫn đang thực hiện transaction, T2 chèn `order_no = 150` rồi commit. Nếu T1 chạy lại truy vấn và thấy hàng thứ 11, tập kết quả đã thay đổi do một hàng mới xuất hiện. Đây là phantom read trong mô hình isolation cho phép nó.

Để ngăn phantom, DBMS cần bảo vệ **điều kiện hoặc khoảng khóa**, chứ không chỉ các hàng hiện có. Các cách triển khai phổ biến gồm:

- Gap lock hoặc next-key lock trong InnoDB.
- Key-range lock trong SQL Server khi dùng `SERIALIZABLE`.
- Predicate lock và theo dõi phụ thuộc trong PostgreSQL `SERIALIZABLE` (SSI).

Các cơ chế này có semantics khác nhau. Một số thực sự khiến thao tác chèn phải chờ; một số ghi nhận quan hệ đọc/ghi để phát hiện lịch nguy hiểm và có thể hủy transaction.

## 7. InnoDB: index range và next-key lock

InnoDB của MySQL sử dụng chỉ mục để xác định phạm vi khóa. Với locking read hoặc thao tác ghi trong các điều kiện thích hợp, đặc biệt ở `REPEATABLE READ`, InnoDB có thể dùng **next-key lock**. Next-key lock kết hợp khóa trên một index record với khóa trên gap đứng ngay trước record đó. Gap lock bảo vệ khoảng giữa các giá trị index để ngăn insert vào khoảng được khóa.

Giả sử có index trên `order_no` với các giá trị 100, 200 và 300. Một truy vấn khóa dải từ 100 đến 200 có thể khiến InnoDB khóa các record và gap liên quan đến vùng tìm kiếm. Một giao dịch khác chèn giá trị 150 có thể bị chặn vì insert cần đặt entry vào gap đang bị khóa.

```sql
-- Transaction T1, MySQL InnoDB
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT *
FROM orders
WHERE order_no >= 100
  AND order_no < 200
FOR UPDATE;
```

```sql
-- Transaction T2
START TRANSACTION;

INSERT INTO orders(order_no, customer_id)
VALUES (150, 42);
-- Có thể phải chờ gap/next-key lock của T1.
```

Phạm vi khóa thực tế phụ thuộc index được dùng và access path. Nếu điều kiện range dùng index `order_no`, DBMS có thể khóa dải index liên quan. Nếu không có index phù hợp, truy vấn có thể quét và khóa nhiều record hơn dự kiến, làm tăng blocking.

### 7.1. Unique lookup khác range lookup

Một phép tìm chính xác theo toàn bộ unique key thường chỉ cần khóa record được tìm thấy khi hàng tồn tại, thay vì khóa một khoảng rộng. Nếu hàng không tồn tại, quy tắc gap lock có thể vẫn có vai trò tùy isolation level và loại câu lệnh.

Ví dụ:

```sql
SELECT *
FROM orders
WHERE order_id = 500
FOR UPDATE;
```

Nếu `order_id` là unique index, đây là một equality lookup cụ thể. So với truy vấn range trên cột không unique, phạm vi khóa thường hẹp hơn. Tuy nhiên, không nên suy ra chính xác lock mode chỉ từ câu SQL; cần xem index, isolation level và lock instrumentation của phiên bản InnoDB đang chạy.

### 7.2. Isolation level ảnh hưởng gap lock

Trong InnoDB, `REPEATABLE READ` thường sử dụng next-key locking cho các thao tác locking read và write nhằm ngăn một số phantom. Ở `READ COMMITTED`, gap locking phần lớn được giảm hoặc tắt cho các tìm kiếm thông thường, nhưng vẫn có ngoại lệ như kiểm tra foreign key và duplicate key. Do đó, cùng một điều kiện và index có thể tạo phạm vi khóa khác nhau ở isolation level khác nhau.

Gap lock có thể tương thích với gap lock khác trong một số tình huống và không phải lúc nào cũng hoạt động như khóa độc quyền trên một hàng. Khi phân tích deadlock hoặc insert bị chặn, hãy xem lock type, index name và khoảng khóa trong thông tin chẩn đoán InnoDB.

## 8. SQL Server: key-range lock

SQL Server có thể sử dụng **key-range lock** ở isolation level `SERIALIZABLE` để ngăn giao dịch khác chèn hoặc thay đổi khóa chỉ mục làm cho hàng mới xuất hiện trong phạm vi predicate.

Ví dụ:

```sql
-- Transaction T1
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT order_id, order_no
FROM dbo.Orders
WHERE order_no >= 100
  AND order_no < 200;
```

Trong khi T1 còn mở, T2 thử chèn một hàng có `order_no = 150`. Nếu phạm vi được bảo vệ bằng key-range lock trên index thích hợp, thao tác chèn có thể phải chờ cho đến khi T1 kết thúc.

```sql
-- Transaction T2
BEGIN TRANSACTION;

INSERT INTO dbo.Orders(order_no, customer_id)
VALUES (150, 42);
-- Có thể chờ key-range lock do T1 giữ.
```

Key-range lock được triển khai trên khóa chỉ mục và phụ thuộc access path. Một index seek có thể bảo vệ một khoảng hẹp. Nếu optimizer chọn scan trên index rộng hoặc bảng, SQL Server có thể phải bảo vệ một phạm vi lớn hơn, tăng khả năng blocking. Lock escalation cũng có thể xảy ra trong một số điều kiện, làm phạm vi khóa ở mức cao hơn.

SQL Server có nhiều kiểu key-range lock như `RangeS-S`, `RangeS-U`, `RangeI-N` và `RangeX-X`, tương ứng với loại truy cập và xung đột khác nhau. Không cần ghi nhớ tên từng mode để hiểu nguyên tắc: `SERIALIZABLE` phải ngăn một transaction khác làm thay đổi tập hàng mà truy vấn hiện tại phụ thuộc vào.

## 9. PostgreSQL: predicate lock trong Serializable Snapshot Isolation

PostgreSQL có cách tiếp cận khác. Ở isolation level `SERIALIZABLE`, PostgreSQL sử dụng Serializable Snapshot Isolation (SSI). Các truy vấn đọc có thể tạo **SIREAD predicate locks** để ghi nhận vùng dữ liệu đã đọc. Những dấu vết này phục vụ phát hiện phụ thuộc đọc/ghi nguy hiểm.

SIREAD lock không phải khóa chặn thông thường. Nó không khiến một thao tác `INSERT` phải chờ chỉ vì vùng đó đã được đọc. Thay vào đó, PostgreSQL theo dõi khi một transaction khác ghi vào vùng có thể ảnh hưởng đến kết quả đọc. Nếu các phụ thuộc tạo thành cấu trúc có thể dẫn đến lịch không serializable, DBMS có thể hủy một transaction với lỗi serialization.

Đường truy cập vẫn quan trọng. PostgreSQL có thể ghi nhận predicate lock ở mức tuple, page hoặc relation tùy kế hoạch và khả năng theo dõi. Nếu một truy vấn phải scan rộng hoặc số lượng predicate lock vượt ngưỡng quản lý, hệ thống có thể gộp (promote) thông tin theo dõi lên mức rộng hơn. Điều đó có thể làm tăng false positive: hai transaction bị coi là xung đột dù dữ liệu thực tế chúng quan tâm không giao nhau hoàn toàn.

Ví dụ:

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT order_id
FROM orders
WHERE order_no >= 100
  AND order_no < 200;

-- Các thao tác đọc/ghi tiếp theo phụ thuộc vào kết quả này.
```

Nếu một transaction khác chèn hàng `order_no = 150`, PostgreSQL có thể ghi nhận phụ thuộc predicate và phát hiện serialization anomaly khi đánh giá lịch. Giao dịch không nhất thiết phải chờ insert; một bên có thể bị hủy khi commit hoặc khi DBMS phát hiện cấu trúc nguy hiểm.

Vì vậy, không nên mô tả SIREAD như một gap lock chặn insert. Mục tiêu tương tự là bảo vệ semantics Serializable, nhưng cơ chế là theo dõi xung đột và abort thay vì nhất thiết khóa khoảng vật lý.

## 10. Cùng một WHERE nhưng access path khác nhau

Giả sử hai phiên bản hệ thống chạy cùng truy vấn:

```sql
SELECT order_id
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-02-01 00:00:00';
```

Phiên bản A có index `(customer_id, created_at)`. Optimizer có thể seek vào vùng customer 42 và duyệt khoảng ngày cần thiết. Phiên bản B chỉ có index trên `created_at` hoặc không có index hữu ích, nên có thể phải xem nhiều entry hơn.

| Thuộc tính | Kế hoạch A | Kế hoạch B |
|---|---|---|
| Index | `(customer_id, created_at)` | Không có index ghép phù hợp |
| Đường truy cập có thể chọn | Seek/range scan hẹp | Scan rộng hoặc dùng index khác rồi lọc |
| Dữ liệu cần xem xét | Chủ yếu các entry của customer 42 trong tháng | Có thể xem nhiều khách hàng hoặc nhiều tháng hơn |
| Khả năng tranh chấp | Thường thấp hơn nếu lock footprint theo access path | Có thể cao hơn do nhiều hàng/trang/entry được chạm tới |

Đây là xu hướng, không phải cam kết rằng mọi optimizer sẽ chọn đúng kế hoạch A. Thống kê, độ chọn lọc, kích thước bảng, parameter sniffing, cache và chi phí random I/O đều có thể khiến optimizer chọn kế hoạch khác.

### 10.1. Residual predicate

Một kế hoạch có thể dùng index để tìm một phần điều kiện rồi kiểm tra phần còn lại sau khi lấy các entry. Ví dụ index trên `created_at` có thể tìm tháng 1, sau đó mới kiểm tra `customer_id = 42`. Những entry của khách hàng khác đã được xem xét nhưng bị loại khỏi kết quả.

Trong một số cơ chế khóa theo index range, các entry được quét hoặc khoảng index được bảo vệ có thể rộng hơn tập kết quả cuối cùng. Đây là lý do cần xem cả seek predicate và residual predicate trong execution plan.

### 10.2. Statistics và parameter-sensitive plan

Optimizer dùng thống kê để ước lượng số hàng thỏa điều kiện. Nếu thống kê cũ hoặc dữ liệu phân bố lệch, optimizer có thể chọn scan dù có index, hoặc seek rồi phải truy cập quá nhiều hàng.

Tham số truy vấn cũng ảnh hưởng. `customer_id = 42` có thể trả 20 hàng, trong khi một customer khác có hàng trăm nghìn đơn. Một plan tối ưu cho giá trị đầu tiên có thể không phù hợp cho giá trị khác trong một số DBMS/cơ chế cache plan.

Khi lock contention tăng bất thường sau khi dữ liệu lớn lên hoặc sau một lần deploy, hãy so sánh actual execution plan, số hàng ước lượng/thực tế và thống kê index. Không chỉ xem câu SQL có thay đổi hay không.

## 11. Join order cũng ảnh hưởng đến dữ liệu được chạm tới

Truy vấn join có thể bắt đầu từ bảng khác nhau tùy optimizer. Cùng một kết quả logic nhưng join order và join method khác nhau có thể làm thay đổi số hàng trung gian, số index lookup và thứ tự lấy khóa.

Ví dụ:

```sql
SELECT o.order_id
FROM customers AS c
JOIN orders AS o ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH'
  AND o.status = 'PENDING';
```

Nếu `region = 'NORTH'` rất chọn lọc, optimizer có thể bắt đầu từ `customers` rồi tìm đơn hàng theo `customer_id`. Nếu `status = 'PENDING'` rất chọn lọc, nó có thể bắt đầu từ `orders` rồi nối sang khách hàng. Mỗi kế hoạch chạm đến tập index và hàng trung gian khác nhau.

Với locking read hoặc transaction cập nhật nhiều bảng, thứ tự truy cập có thể ảnh hưởng đến thứ tự lấy khóa và nguy cơ deadlock. Nếu các transaction đi qua nhiều bảng theo thứ tự khác nhau, một bên có thể giữ khóa ở bảng A trong khi chờ B, bên kia giữ B và chờ A.

Không nên ép join order chỉ để làm cho kế hoạch trông dễ hiểu. Hãy dùng actual plan và lock graph để xác định vấn đề, sau đó cân nhắc index, query shape hoặc quy ước truy cập tài nguyên thống nhất.

## 12. Ví dụ: điều kiện trên cột không có index làm tăng vùng khóa

Giả sử bảng `payments` có nhiều triệu hàng và một giao dịch cần khóa các khoản thanh toán đang ở trạng thái `PENDING` của một merchant:

```sql
SELECT payment_id
FROM payments
WHERE merchant_id = 900
  AND status = 'PENDING'
FOR UPDATE;
```

Nếu chỉ có index trên `payment_id`, DBMS có thể phải scan nhiều hàng để tìm những khoản thanh toán cần khóa. Tùy DBMS, số hàng thực tế bị khóa có thể chỉ là các hàng kết quả, nhưng scan rộng vẫn tăng I/O và thời gian transaction; một số cơ chế Serializable/range locking cũng có thể bảo vệ vùng rộng hơn.

Một index phù hợp có thể là:

```sql
CREATE INDEX idx_payments_merchant_status
ON payments (merchant_id, status);
```

Với PostgreSQL, nếu phần lớn truy vấn chỉ cần hàng `PENDING`, partial index cũng có thể hữu ích:

```sql
CREATE INDEX idx_payments_pending_merchant
ON payments (merchant_id, payment_id)
WHERE status = 'PENDING';
```

Index này giúp tìm các hàng có trạng thái pending theo merchant. Nó không thay đổi quy tắc khóa của DBMS, nhưng có thể giảm số entry cần xem xét và thời gian giữ khóa. Cần kiểm tra tần suất thay đổi status, chi phí duy trì index và kế hoạch thực thi trước khi tạo index.

## 13. Predicate thay đổi có thể tạo phantom

Phantom không chỉ xuất hiện khi `INSERT`. Một hàng hiện có có thể được `UPDATE` để bắt đầu thỏa điều kiện hoặc ngừng thỏa điều kiện.

Ví dụ T1 truy vấn:

```sql
SELECT *
FROM employees
WHERE department_id = 10
  AND salary > 50000;
```

Trong khi T1 còn phụ thuộc vào tập kết quả, T2 có thể:

- Chèn nhân viên mới vào phòng ban 10 với lương 60000.
- Cập nhật nhân viên từ phòng ban khác sang phòng ban 10.
- Tăng lương của một nhân viên trong phòng ban 10 từ 45000 lên 60000.

Các thao tác này làm xuất hiện một hàng mới trong tập kết quả theo predicate, dù không nhất thiết tạo một row mới vật lý. DBMS cần bảo vệ predicate hoặc kiểm tra phụ thuộc để Serializable vẫn đúng.

Tương tự, cập nhật một hàng làm nó không còn thỏa điều kiện có thể làm tập kết quả giảm. Khái niệm phantom thường được giới thiệu qua insert, nhưng về mặt predicate, mọi thay đổi khiến membership của một hàng trong tập kết quả thay đổi đều có liên quan.

## 14. Làm sao đọc execution plan khi điều tra khóa?

Khi một truy vấn tạo nhiều blocking hoặc serialization failure, hãy xem plan với các câu hỏi cụ thể:

1. **DBMS dùng index nào?** Xác định tên index và các cột tham gia seek.
2. **Đường truy cập là seek hay scan?** Một scan có thể khiến DBMS xem xét nhiều entry hoặc trang hơn dự kiến.
3. **Điều kiện nào là seek predicate?** Đây là phần giúp định vị vùng trong index.
4. **Điều kiện nào là residual predicate?** Các hàng có thể đã được đọc trước khi bị loại khỏi kết quả cuối.
5. **Số hàng ước lượng có gần số hàng thực tế không?** Sai lệch lớn có thể dẫn đến kế hoạch kém.
6. **Có sort, hash, nested loop hoặc join order nào làm tăng thời gian giữ transaction không?** Kế hoạch chậm kéo dài thời gian giữ lock.
7. **Có lock escalation hoặc predicate-lock promotion không?** Kiểm tra theo công cụ của DBMS.
8. **Có transaction khác ghi vào cùng range hoặc predicate không?** Ghép plan với lock/wait graph và transaction timeline.

Plan giải thích cách DBMS tìm dữ liệu; lock diagnostics giải thích tài nguyên nào đang bị giữ hoặc xung đột. Cần kết hợp cả hai để hiểu vì sao một truy vấn chạm đến dữ liệu ngoài dự kiến hoặc vì sao một insert phải chờ.

## 15. Biện pháp giảm phạm vi dữ liệu được chạm tới

Một số hướng tối ưu thường hữu ích:

- Tạo index có thứ tự cột phù hợp với điều kiện equality, range và join phổ biến.
- Viết predicate sargable, tránh bọc cột trong hàm nếu có thể chuyển thành điều kiện range hoặc dùng expression index.
- Giữ kiểu dữ liệu tham số khớp với cột để tránh ép kiểu bất lợi.
- Chọn cột lọc có tính chọn lọc phù hợp ở đầu index ghép.
- Cập nhật statistics để optimizer ước lượng cardinality tốt hơn.
- Chỉ khóa các hàng hoặc bảng thực sự cần thiết; với PostgreSQL join, có thể dùng locking clause `OF` để giới hạn bảng bị khóa khi phù hợp.
- Rút ngắn transaction để giảm thời gian giữ lock hoặc snapshot.
- Thống nhất thứ tự truy cập nhiều tài nguyên để giảm deadlock.
- Đo actual execution plan và lock footprint dưới dữ liệu, tải và tham số gần với production.

Không nên tạo index cho mọi điều kiện `WHERE`. Index chiếm dung lượng và làm tăng chi phí `INSERT`, `UPDATE`, `DELETE`; quá nhiều index còn khiến optimizer có nhiều lựa chọn và làm tăng bảo trì. Chỉ mục cần dựa trên workload thực tế và được đo sau khi thay đổi.

## 16. Những hiểu lầm thường gặp

- **Cho rằng chỉ các hàng trả về mới được chạm tới.** DBMS có thể quét nhiều entry rồi mới lọc kết quả.
- **Cho rằng index seek luôn đồng nghĩa với một row lock.** Seek có thể định vị một range và cơ chế isolation có thể bảo vệ cả khoảng.
- **Cho rằng không có index thì DBMS luôn khóa toàn bảng.** Hành vi phụ thuộc DBMS, isolation level, loại truy vấn và lock escalation; scan rộng làm tăng vùng xem xét nhưng không tự động có cùng lock semantics ở mọi hệ thống.
- **Cho rằng `FOR UPDATE` khóa cả hàng chưa tồn tại.** PostgreSQL khóa các hàng được tìm thấy; bảo vệ gap/predicate cần cơ chế khác.
- **Đánh đồng gap lock, next-key lock, key-range lock và predicate lock.** Chúng cùng giải quyết một số vấn đề về phantom nhưng cơ chế và hành vi chờ khác nhau.
- **Cho rằng predicate lock PostgreSQL là khóa chặn insert.** SIREAD trong SSI chủ yếu ghi nhận phụ thuộc để phát hiện serialization anomaly; nó không hoạt động như row/gap lock chặn thông thường.
- **Chỉ xem câu SQL khi điều tra blocking.** Cần xem actual execution plan, index, lock diagnostics và transaction đang giữ khóa.
- **Tạo index mà không kiểm tra kế hoạch.** Optimizer có thể không dùng index mới, hoặc index có thứ tự cột không phù hợp với predicate.

## 17. Quy trình phân tích một truy vấn gây tranh chấp

Khi một câu lệnh bị chặn hoặc làm các giao dịch khác chờ, hãy đi theo trình tự:

1. Xác định isolation level và loại câu lệnh: đọc thông thường, locking read hay ghi.
2. Ghi lại predicate đầy đủ, gồm điều kiện `WHERE`, join condition, range và các biểu thức.
3. Lấy actual execution plan cùng số hàng ước lượng và thực tế.
4. Xác định index được dùng, seek range, scan range và residual predicate.
5. Dùng lock diagnostics để xác định hàng, key, page, range, table hoặc predicate đang được bảo vệ.
6. Kiểm tra transaction khác có `INSERT` hoặc `UPDATE` làm hàng đi vào/ra predicate hay không.
7. Xác định phạm vi lock có rộng hơn cần thiết vì index thiếu, index order chưa phù hợp hoặc plan scan không.
8. Thử index hoặc cách viết predicate phù hợp trong môi trường kiểm thử; so sánh plan, thời gian chạy, lock wait và thông lượng.
9. Xác nhận bất biến và phantom vẫn được bảo vệ sau tối ưu. Không bỏ cơ chế range/predicate protection chỉ để giảm blocking nếu điều đó làm yếu isolation cần thiết.

## 18. Những điểm cần ghi nhớ

- Điều kiện truy vấn xác định tập kết quả; execution plan xác định đường truy cập và dữ liệu DBMS phải xem xét.
- Index seek/range scan thường thu hẹp vùng dữ liệu cần duyệt; scan rộng có thể tăng I/O, thời gian transaction và phạm vi tranh chấp.
- Thứ tự cột trong composite index quyết định những điều kiện equality và range nào có thể định vị hiệu quả.
- Residual predicate có thể loại hàng sau khi DBMS đã đọc entry; tập scan không nhất thiết bằng tập kết quả.
- Ngăn phantom cần bảo vệ predicate hoặc khoảng dữ liệu, không chỉ khóa các hàng hiện có.
- InnoDB có gap/next-key lock; SQL Server có key-range lock; PostgreSQL SSI dùng SIREAD predicate lock để theo dõi phụ thuộc và có thể abort transaction.
- Các cơ chế trên không đồng nghĩa với nhau. Có cơ chế làm insert chờ, có cơ chế ghi nhận xung đột rồi hủy một transaction.
- Khi điều tra blocking, hãy ghép actual execution plan với lock/wait diagnostics và transaction timeline.
- Tối ưu index và predicate có thể giảm dữ liệu được chạm tới, nhưng cần kiểm tra rằng các bất biến và mức isolation vẫn được bảo vệ.

Khi đánh giá một câu truy vấn trong môi trường đồng thời, hãy nhìn cả điều kiện logic và đường truy cập mà DBMS chọn. Một predicate nhỏ trên giấy có thể dẫn đến scan lớn nếu index không phù hợp; ngược lại, một index được thiết kế đúng có thể thu hẹp range cần đọc và bảo vệ. Hiểu được mối liên hệ này giúp giải thích blocking, phantom và sự khác nhau giữa các chiến lược khóa của từng hệ quản trị.
