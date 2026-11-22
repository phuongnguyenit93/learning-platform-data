# LIMIT, OFFSET, FETCH FIRST và TOP theo hệ quản trị

Khi truy vấn một bảng có hàng nghìn hoặc hàng triệu bản ghi, ứng dụng thường không cần trả toàn bộ kết quả trong một lần. Danh sách đơn hàng chỉ cần 20 dòng đầu; màn hình quản trị hiển thị từng trang; báo cáo muốn xem 5 sản phẩm doanh thu cao nhất. SQL có nhiều cách **giới hạn số hàng trả về** và **bỏ qua một số hàng trước khi lấy kết quả**, nhưng tên mệnh đề và cú pháp không hoàn toàn giống nhau giữa các hệ quản trị cơ sở dữ liệu (DBMS).

Những tên thường gặp là:

- **`LIMIT`**: giới hạn số hàng, phổ biến trong PostgreSQL và MySQL.
- **`OFFSET`**: bỏ qua một số hàng trước khi trả kết quả; cách ghép với `LIMIT` hoặc `FETCH` tùy DBMS.
- **`FETCH FIRST` / `FETCH NEXT`**: cách diễn đạt giới hạn số hàng theo họ cú pháp chuẩn SQL, hỗ trợ trong PostgreSQL, Oracle và nhiều hệ khác.
- **`TOP`**: cú pháp đặc trưng của Microsoft SQL Server để lấy một số hàng đầu, có các tùy chọn như `PERCENT` và `WITH TIES`.

**Điểm quan trọng nhất:** muốn “3 hàng đầu tiên”, “trang thứ hai” hay “10 hàng mới nhất” có nghĩa xác định, phải nêu rõ **`ORDER BY`**. `LIMIT`, `TOP` hay `FETCH` không tự quyết định thế nào là *đầu tiên*. Không có thứ tự rõ ràng, kết quả có thể thay đổi do chỉ mục, kế hoạch thực thi, dữ liệu hoặc cách DBMS xử lý.

Bài học sử dụng PostgreSQL để tạo bộ dữ liệu thực hành và đối chiếu cú pháp **PostgreSQL, MySQL, SQL Server và Oracle Database**. Một số tính năng phụ thuộc phiên bản; ví dụ Oracle sử dụng cú pháp `OFFSET ... FETCH` từ Oracle Database 12c và PostgreSQL hỗ trợ `FETCH ... WITH TIES` từ phiên bản 13.

## 1. Phân biệt sắp xếp, bỏ qua và giới hạn

Một truy vấn phân trang thường gồm ba quyết định độc lập:

1. **Sắp xếp** các hàng theo tiêu chí nào: ngày tạo, số tiền, mã định danh?
2. **Bỏ qua** bao nhiêu hàng đứng trước vị trí muốn xem?
3. **Trả về** tối đa bao nhiêu hàng tiếp theo?

Ví dụ ý tưởng:

```text
Tập kết quả sau khi lọc:
    10  9  8  7  6  5  4  3  2  1
    |-- sắp theo thứ tự xác định -------|

OFFSET 3  -> bỏ qua 10, 9, 8
LIMIT 4   -> lấy 7, 6, 5, 4
```

Trong mô hình xử lý **logic** của SELECT, `WHERE` lọc dòng, các mệnh đề tổng hợp và `HAVING` xử lý nhóm nếu có, `SELECT` xác định cột kết quả, sau đó `ORDER BY` xác định thứ tự và mệnh đề giới hạn/phân trang chọn một phần kết quả. Tuy nhiên, **kế hoạch thực thi vật lý** có thể dùng chỉ mục theo thứ tự và dừng sớm, thay vì thực sự sắp tất cả hàng vào một bảng tạm.

| Thành phần | Câu hỏi được giải quyết | Điều không được bảo đảm |
| --- | --- | --- |
| `ORDER BY` | Hàng nào đứng trước hàng nào? | Không giới hạn số hàng |
| `LIMIT n` hoặc `FETCH FIRST n ROWS ONLY` | Lấy tối đa bao nhiêu hàng? | Không tự tạo thứ tự khi thiếu `ORDER BY` |
| `OFFSET m` | Bỏ qua bao nhiêu hàng theo thứ tự kết quả? | Không bảo đảm các trang ổn định nếu thứ tự chưa duy nhất hoặc dữ liệu thay đổi |
| `TOP (n)` của SQL Server | Lấy n hàng ở đầu kết quả? | Không có cơ chế bỏ qua m hàng riêng trong chính `TOP` |
| `WITH TIES` | Có lấy thêm hàng đồng hạng với hàng cuối cùng không? | Không bảo đảm số hàng trả về đúng bằng n |

## 2. Tạo bảng dữ liệu mẫu trong PostgreSQL

Để có ví dụ tự chứa, mở một phiên PostgreSQL và chạy:

```sql
CREATE TEMP TABLE demo_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    status TEXT NOT NULL
);

INSERT INTO demo_orders
    (order_id, customer_id, created_at, total_amount, status)
VALUES
    (101, 1, TIMESTAMPTZ '2026-06-01 09:00:00+07', 500.00, 'PAID'),
    (102, 2, TIMESTAMPTZ '2026-06-02 09:00:00+07', 400.00, 'PAID'),
    (103, 1, TIMESTAMPTZ '2026-06-03 09:00:00+07', 400.00, 'PAID'),
    (104, 3, TIMESTAMPTZ '2026-06-04 09:00:00+07', 400.00, 'PAID'),
    (105, 1, TIMESTAMPTZ '2026-06-05 09:00:00+07', 300.00, 'PENDING'),
    (106, 2, TIMESTAMPTZ '2026-06-06 09:00:00+07', 250.00, 'PAID'),
    (107, 4, TIMESTAMPTZ '2026-06-07 09:00:00+07', 200.00, 'PAID'),
    (108, 3, TIMESTAMPTZ '2026-06-08 09:00:00+07', 150.00, 'PENDING'),
    (109, 2, TIMESTAMPTZ '2026-06-09 09:00:00+07', 100.00, 'PAID'),
    (110, 4, TIMESTAMPTZ '2026-06-09 09:00:00+07',  50.00, 'PAID');
```

Bảng có **10 đơn hàng**, trong đó `order_id` là khóa duy nhất, hai đơn 109 và 110 có cùng `created_at`, còn ba đơn 102–104 cùng `total_amount = 400`. Các giá trị trùng này giúp phân biệt `ORDER BY` chưa đủ khóa và cách hoạt động của `WITH TIES`.

Thử sắp xếp:

```sql
SELECT order_id, created_at, total_amount
FROM demo_orders
ORDER BY created_at DESC, order_id DESC;
```

Thứ tự `order_id` khi sắp theo ngày giảm dần và ID giảm dần là:

```text
110, 109, 108, 107, 106, 105, 104, 103, 102, 101
```

**Vì sao thêm `order_id`?** Hai đơn 109 và 110 cùng thời điểm tạo. Chỉ `ORDER BY created_at DESC` không xác định thứ tự giữa chúng. Thêm một khóa duy nhất làm thứ tự toàn phần và phù hợp hơn cho phân trang.

Các ví dụ SQL Server/Oracle/MySQL phía sau dùng tên bảng `orders` theo mô hình có các cột `order_id`, `created_at`, `total_amount`, `status`; muốn chạy trên từng DBMS, cần tạo bảng tương ứng với kiểu ngày giờ và cú pháp DDL của hệ đó. Câu truy vấn PostgreSQL trên `demo_orders` có thể chạy trực tiếp trong cùng phiên vừa tạo.

## 3. `LIMIT`: cách giới hạn phổ biến của PostgreSQL và MySQL

Với PostgreSQL:

```sql
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3;
```

Kết quả là các đơn **110, 109, 108**. `LIMIT 3` giới hạn tối đa ba hàng; nếu truy vấn nguồn chỉ có hai hàng, kết quả chỉ chứa hai hàng chứ không tự bổ sung hàng thứ ba.

Với MySQL, cú pháp thông dụng tương tự:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3;
```

Trong MySQL và PostgreSQL, có thể viết `LIMIT` ở cuối SELECT (sau `ORDER BY` nếu có). Không thể tùy tiện chuyển `LIMIT` lên vị trí ngay sau SELECT như `TOP` của SQL Server.

### 3.1. `LIMIT 0`, giới hạn âm và số lượng không hợp lệ

```sql
-- PostgreSQL: cố ý trả 0 hàng.
SELECT order_id
FROM demo_orders
LIMIT 0;
```

`LIMIT 0` hữu ích khi chỉ muốn lấy metadata cột của kết quả hoặc thử cấu trúc đầu ra mà không lấy dữ liệu. Không nên dùng số âm, chuỗi không phải số, hoặc một giới hạn rất lớn do người dùng tự nhập mà không kiểm tra; từng DBMS có quy tắc báo lỗi và kiểu biểu thức số khác nhau.

Trong PostgreSQL, `LIMIT ALL` tương đương **không đặt giới hạn số hàng**:

```sql
SELECT order_id
FROM demo_orders
ORDER BY order_id
LIMIT ALL;
```

Đây là cú pháp PostgreSQL, không phải cách diễn đạt nên giả định có ở mọi DBMS. Nếu không muốn giới hạn, cách đơn giản và dễ chuyển hệ hơn là **bỏ hẳn LIMIT**.

### 3.2. `LIMIT` không thay thế `ORDER BY`

```sql
SELECT order_id
FROM demo_orders
LIMIT 3;
```

Không thể kết luận chắc chắn ba hàng trả về là đơn có ID nhỏ nhất, được tạo sớm nhất hoặc mới nhất. Hệ quản trị có thể quét bảng/chỉ mục theo một kế hoạch nhất định hôm nay, rồi trả hàng theo kế hoạch khác sau khi thống kê, chỉ mục hoặc dữ liệu thay đổi.

Khi yêu cầu “ba đơn mới nhất”, phải nêu rõ:

```sql
ORDER BY created_at DESC, order_id DESC
LIMIT 3
```

Khi yêu cầu “ba đơn giá trị cao nhất”, phải dùng một khóa phù hợp khác:

```sql
ORDER BY total_amount DESC, order_id DESC
LIMIT 3
```

Hai truy vấn nói về **hai khái niệm đầu tiên khác nhau**.

## 4. `OFFSET`: bỏ qua hàng để lấy trang

Trong PostgreSQL và MySQL, cú pháp quen thuộc:

```sql
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3 OFFSET 3;
```

`OFFSET 3` bỏ ba đơn 110, 109, 108; `LIMIT 3` trả ba đơn kế tiếp:

| Vị trí theo ORDER BY | order_id | Thuộc trang nào khi mỗi trang 3 hàng? |
| ---: | ---: | --- |
| 1 | 110 | Trang 1 |
| 2 | 109 | Trang 1 |
| 3 | 108 | Trang 1 |
| 4 | 107 | Trang 2 |
| 5 | 106 | Trang 2 |
| 6 | 105 | Trang 2 |
| 7 | 104 | Trang 3 |
| 8 | 103 | Trang 3 |
| 9 | 102 | Trang 3 |
| 10 | 101 | Trang 4 |

Vì vậy câu SQL có `LIMIT 3 OFFSET 3` trả **107, 106, 105**.

### 4.1. OFFSET được đếm từ 0

Phần tử đầu tiên có offset **0**. Công thức phổ biến khi giao diện đánh số trang từ 1:

\[
\text{offset} = (\text{page} - 1) \times \text{pageSize}
\]

Với `pageSize = 3`:

| Trang trên giao diện | OFFSET | LIMIT | Các ID trong dữ liệu mẫu |
| ---: | ---: | ---: | --- |
| 1 | 0 | 3 | 110, 109, 108 |
| 2 | 3 | 3 | 107, 106, 105 |
| 3 | 6 | 3 | 104, 103, 102 |
| 4 | 9 | 3 | 101 |
| 5 | 12 | 3 | Không có hàng |

Nếu giao diện sử dụng chỉ số trang bắt đầu từ 0, công thức sẽ là `offset = pageIndex * pageSize`. Điều quan trọng là **API và UI phải thống nhất quy ước**, không cộng/trừ 1 tùy tiện.

### 4.2. Hai cách viết của MySQL

Trong MySQL, có hai dạng LIMIT/OFFSET phổ biến:

```sql
-- Dạng dễ đọc: số lượng cần lấy, rồi số lượng bỏ qua.
SELECT order_id
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3 OFFSET 6;

-- Dạng dùng dấu phẩy: bỏ qua trước, số lượng cần lấy sau.
SELECT order_id
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 6, 3;
```

**Hai câu tương đương về số hàng và vị trí trang.** Đây cũng là lỗi dễ gặp: trong `LIMIT 6, 3`, số **6 là offset**, còn 3 là số hàng muốn lấy; không phải “lấy 6 hàng rồi bỏ 3”.

Để giảm nhầm lẫn, khi viết SQL mới nên ưu tiên dạng có tên **`LIMIT count OFFSET offset`**, nếu DBMS hỗ trợ.

### 4.3. OFFSET mà không có thứ tự xác định

```sql
-- Không có ORDER BY: vị trí các hàng không được cam kết.
SELECT order_id
FROM demo_orders
LIMIT 3 OFFSET 3;
```

Kể cả bảng có PRIMARY KEY và ứng dụng đã thấy dữ liệu thường hiện theo ID, đây **không phải phân trang đáng tin cậy**. Hệ quản trị có quyền trả hàng theo bất kỳ thứ tự vật lý phù hợp nào nếu người viết không yêu cầu ORDER BY.

Ngoài ra, một `ORDER BY` **chưa đủ phân biệt các hàng** cũng có thể làm phân trang không ổn định:

```sql
ORDER BY created_at DESC
```

Vì đơn 109 và 110 có cùng created_at, hai hàng ấy có thể đổi vị trí. Thêm `order_id DESC` để định nghĩa thứ tự xác định trên dữ liệu mẫu:

```sql
ORDER BY created_at DESC, order_id DESC
```

## 5. `FETCH FIRST` / `FETCH NEXT`: cách viết theo họ chuẩn SQL

Nhiều hệ quản trị hỗ trợ cách diễn đạt:

```sql
ORDER BY ...
FETCH FIRST 3 ROWS ONLY
```

hoặc:

```sql
ORDER BY ...
OFFSET 3 ROWS
FETCH NEXT 3 ROWS ONLY
```

Đây là họ cú pháp row limiting của SQL. Các từ `FIRST` và `NEXT`, `ROW` và `ROWS` thường là những biến thể cú pháp được chấp nhận ở các hệ hỗ trợ, nhưng **không nên coi mọi tổ hợp đều có mặt trên mọi phiên bản DBMS**.

### 5.1. PostgreSQL: dùng FETCH FIRST hoặc LIMIT

Hai câu dưới đây có cùng mục đích:

```sql
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3;
```

```sql
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 3 ROWS ONLY;
```

Để lấy trang hai:

```sql
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY;
```

Trong PostgreSQL, `OFFSET ... FETCH` và `LIMIT ... OFFSET` có thể diễn đạt cùng việc bỏ qua và giới hạn. Chọn một cách nhất quán theo chuẩn nhóm/dự án, không trộn nhiều cú pháp tương đương trong cùng câu khi không cần thiết.

### 5.2. Oracle Database: OFFSET/FETCH từ 12c

Trong Oracle Database 12c trở lên, ví dụ lấy ba đơn mới nhất:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 3 ROWS ONLY;
```

Trang thứ hai:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY;
```

Các phiên bản Oracle cũ trước khi hỗ trợ row-limiting clause thường dùng `ROWNUM` hoặc truy vấn lồng với phân tích `ROW_NUMBER()`. Cách viết `ROWNUM` cần đặc biệt cẩn thận vì `ROWNUM` được gán theo tiến trình chọn hàng, không tự thể hiện “top-N theo ORDER BY” khi đặt sai cấp truy vấn.

Ví dụ kiểu cũ để lấy ba hàng đầu sau khi sắp:

```sql
-- Ví dụ cho Oracle cũ: ORDER BY trong subquery,
-- rồi mới áp dụng ROWNUM ở truy vấn ngoài.
SELECT order_id, created_at
FROM (
    SELECT order_id, created_at
    FROM orders
    ORDER BY created_at DESC, order_id DESC
)
WHERE ROWNUM <= 3;
```

Với Oracle hiện đại, cú pháp `FETCH FIRST ... ROWS ONLY` thường thể hiện mục đích dễ đọc hơn. Khi triển khai thực tế, nên đối chiếu các giới hạn và tương tác của row-limiting clause với view, truy vấn phức tạp và phiên bản Oracle đang dùng.

### 5.3. Họ FETCH không đồng nghĩa hỗ trợ trên mọi DBMS

PostgreSQL và Oracle hỗ trợ cú pháp `FETCH FIRST ... ROWS ONLY`; SQL Server sử dụng dạng **OFFSET/FETCH sau ORDER BY** với quy tắc riêng, còn MySQL chủ yếu sử dụng **LIMIT**. Muốn viết SQL có thể di chuyển giữa hệ quản trị, không chỉ thay một từ khóa mà phải xem toàn bộ cú pháp được phiên bản đích chấp nhận.

## 6. `TOP`: cách giới hạn hàng trong Microsoft SQL Server

Trong SQL Server, không viết `LIMIT 3` ở cuối SELECT như PostgreSQL/MySQL. Thay vào đó, có thể dùng **`TOP` ngay sau `SELECT`**:

```sql
SELECT TOP (3)
    order_id,
    created_at
FROM orders
ORDER BY created_at DESC, order_id DESC;
```

`TOP (3)` lấy ba hàng đầu tiên của kết quả được sắp xếp. Không có ORDER BY, SQL Server cũng **không cam kết** ba hàng cụ thể nào sẽ được chọn.

SQL Server hỗ trợ cú pháp `TOP (expression)`; cách viết có ngoặc thường rõ ràng và được khuyến nghị khi biểu thức là số hàng.

### 6.1. TOP không có sẵn tham số “bỏ qua 20 hàng”

`TOP` đơn thuần không có phần `OFFSET`. Để phân trang trong SQL Server hiện đại, dùng `ORDER BY ... OFFSET ... ROWS FETCH NEXT ... ROWS ONLY`:

```sql
SELECT
    order_id,
    created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY;
```

Ở SQL Server, mệnh đề **OFFSET/FETCH nằm trong cấu trúc ORDER BY**: cần có ORDER BY. `FETCH NEXT` yêu cầu một `OFFSET` đi trước trong cú pháp này; để lấy trang đầu có thể dùng `OFFSET 0 ROWS FETCH NEXT 3 ROWS ONLY`, hoặc dùng TOP (3) với ORDER BY.

```sql
-- Trang 1 theo dạng OFFSET/FETCH của SQL Server:
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 0 ROWS FETCH NEXT 3 ROWS ONLY;
```

Đừng sao chép nguyên câu `FETCH FIRST 3 ROWS ONLY` đứng riêng trong PostgreSQL/Oracle rồi kỳ vọng SQL Server hiểu giống hệt. SQL Server có cú pháp OFFSET/FETCH riêng.

### 6.2. `TOP (n) PERCENT`

SQL Server còn hỗ trợ:

```sql
SELECT TOP (20) PERCENT
    order_id,
    total_amount
FROM orders
ORDER BY total_amount DESC, order_id DESC;
```

Ở đây yêu cầu **20% số hàng** trong tập kết quả, không phải 20 hàng. Nếu số hàng tính ra không nguyên, số hàng trả được làm tròn lên theo quy tắc TOP PERCENT; với `WITH TIES`, có thể vượt mức phần trăm tính toán do nhận thêm hàng đồng hạng.

Không nên dùng `PERCENT` cho một API phân trang luôn muốn 20 bản ghi mỗi trang. Khi dữ liệu tăng từ 100 lên 10.000 hàng, “TOP 20 PERCENT” tăng từ khoảng 20 lên khoảng 2.000 hàng — mục đích hoàn toàn khác “TOP 20”.

### 6.3. `TOP ... WITH TIES`

SQL Server hỗ trợ:

```sql
SELECT TOP (2) WITH TIES
    order_id,
    total_amount
FROM orders
ORDER BY total_amount DESC;
```

Nếu giá trị tại vị trí thứ hai là 400 và có nhiều hàng cùng tổng tiền 400, tất cả các hàng đồng hạng ở **ranh giới** đều có thể được trả thêm. Kết quả có thể lớn hơn hai hàng. `WITH TIES` yêu cầu ORDER BY và được giải thích cụ thể ở mục tiếp theo.

### 6.4. TOP trong UPDATE/DELETE: chú ý thứ tự

SQL Server cũng cho phép `TOP` trong một số thao tác ghi như UPDATE/DELETE. Tuy nhiên, không nên suy luận rằng `UPDATE TOP (n)` hoặc `DELETE TOP (n)` tự chọn “n hàng mới nhất”: mệnh đề TOP của DML không tự cung cấp thứ tự có ý nghĩa. Nếu một quy trình ghi phải chọn đúng các hàng theo thứ tự, cần thiết kế truy vấn con hoặc CTE có ngữ nghĩa xác định, ràng buộc cạnh tranh và giao dịch phù hợp.

Bài này chủ yếu phân tích `TOP` khi **truy vấn SELECT**; các ví dụ chọn và ghi dữ liệu thật cần được kiểm soát riêng.

## 7. So sánh bốn hệ quản trị bằng cùng một bài toán

Giả sử cần lấy **3 đơn mới nhất**, sắp theo `created_at DESC, order_id DESC`:

| Hệ quản trị | Cách viết thông dụng |
| --- | --- |
| PostgreSQL | `ORDER BY created_at DESC, order_id DESC LIMIT 3` |
| MySQL | `ORDER BY created_at DESC, order_id DESC LIMIT 3` |
| SQL Server | `SELECT TOP (3) ... ORDER BY created_at DESC, order_id DESC` |
| Oracle 12c+ | `ORDER BY created_at DESC, order_id DESC FETCH FIRST 3 ROWS ONLY` |

Nếu muốn lấy **trang thứ hai** với 3 hàng/trang:

| Hệ quản trị | Cú pháp lấy trang thứ hai |
| --- | --- |
| PostgreSQL | `ORDER BY ... LIMIT 3 OFFSET 3` hoặc `ORDER BY ... OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY` |
| MySQL | `ORDER BY ... LIMIT 3 OFFSET 3` hoặc `ORDER BY ... LIMIT 3, 3` |
| SQL Server | `ORDER BY ... OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY` |
| Oracle 12c+ | `ORDER BY ... OFFSET 3 ROWS FETCH NEXT 3 ROWS ONLY` |

Tất cả các ví dụ trên phải đi kèm **SELECT/FROM và ORDER BY thực sự đúng nghiệp vụ**. Bảng chỉ tập trung vào đoạn giới hạn/phân trang, không phải các câu SQL độc lập có thể chạy khi tách riêng.

### 7.1. Những phần khác biệt cần nhớ

- `LIMIT n OFFSET m`: n là **số hàng lấy**, m là **số hàng bỏ qua**.
- `LIMIT m, n` (MySQL): m là **số hàng bỏ qua**, n là **số hàng lấy**.
- `OFFSET m ROWS FETCH NEXT n ROWS ONLY`: thường bỏ m rồi lấy n; trong SQL Server phải đi cùng ORDER BY.
- `TOP (n)`: SQL Server đặt sau SELECT, không có OFFSET ngay trong TOP.
- `FETCH FIRST n ROWS ONLY`: phổ biến trong PostgreSQL/Oracle và họ chuẩn SQL, không đồng nghĩa hỗ trợ trực tiếp như vậy ở MySQL hoặc SQL Server.
- `WITH TIES` có các vị trí cú pháp riêng tùy DBMS và **có thể trả nhiều hơn n hàng**.

### 7.2. Dấu chấm phẩy và tên bảng

Tất cả ví dụ có thể kết thúc bằng `;`, nhưng tên bảng, cách định nghĩa ngày giờ và cách quote identifier có thể khác. Ví dụ PostgreSQL dùng `TIMESTAMPTZ`, SQL Server thường dùng `datetimeoffset` hoặc `datetime2`, Oracle dùng các kiểu `TIMESTAMP`/`TIMESTAMP WITH TIME ZONE`. Việc đổi cú pháp giới hạn hàng không tự làm toàn bộ DDL và biểu thức của truy vấn trở nên tương thích.

## 8. `WITH TIES`: lấy đủ các hàng đồng hạng ở ranh giới

Giả sử sắp theo tổng tiền giảm dần. Trong dữ liệu mẫu:

| Thứ hạng theo tổng tiền | order_id | total_amount |
| ---: | ---: | ---: |
| 1 | 101 | 500.00 |
| 2 (đồng hạng) | 102 | 400.00 |
| 2 (đồng hạng) | 103 | 400.00 |
| 2 (đồng hạng) | 104 | 400.00 |
| 5 | 105 | 300.00 |
| 6 | 106 | 250.00 |

Nếu chọn **2 hàng** theo tổng tiền, `LIMIT 2` hoặc `FETCH FIRST 2 ROWS ONLY` chỉ trả 2 hàng: đơn 101 và **một trong ba** đơn có tổng 400, nếu không có khóa phụ để phân biệt. Nhưng bài toán “lấy cả các đơn đồng hạng với vị trí thứ hai” cần giữ **cả ba** đơn cùng 400.

### 8.1. PostgreSQL và Oracle

Trong PostgreSQL 13+ và Oracle 12c+ có cú pháp:

```sql
SELECT order_id, total_amount
FROM demo_orders
ORDER BY total_amount DESC
FETCH FIRST 2 ROWS WITH TIES;
```

Đây là câu có thể chạy trực tiếp trên bảng `demo_orders` trong PostgreSQL; để chạy Oracle, dùng bảng `orders` tương ứng. Kết quả gồm **4 hàng**: 101 cùng 102, 103, 104. Thứ tự giữa các đơn có tổng tiền bằng nhau **không xác định**, vì ORDER BY chỉ dùng `total_amount`.

### 8.2. SQL Server

SQL Server viết:

```sql
SELECT TOP (2) WITH TIES
    order_id,
    total_amount
FROM orders
ORDER BY total_amount DESC;
```

Trên dữ liệu tương ứng, yêu cầu cũng trả cả những đơn có mức tổng tiền 400 ở ranh giới. `TOP WITH TIES` dựa trên các **biểu thức ORDER BY**, không phải trên ý nghĩa nghiệp vụ tự suy luận.

### 8.3. Thêm khóa phụ có thể loại bỏ đồng hạng

Xem truy vấn PostgreSQL:

```sql
SELECT order_id, total_amount
FROM demo_orders
ORDER BY total_amount DESC, order_id DESC
FETCH FIRST 2 ROWS WITH TIES;
```

Vì `order_id` là duy nhất, không có hai hàng nào trùng **toàn bộ** khóa ORDER BY `(total_amount, order_id)`. Do đó, kết quả chỉ có đúng **2 hàng**. Đây là đánh đổi:

- Muốn **xếp hạng theo doanh thu và bao gồm mọi đơn đồng hạng doanh thu**, chỉ dùng cột doanh thu trong ORDER BY của WITH TIES (và chấp nhận thứ tự bên trong nhóm đồng hạng không xác định).
- Muốn **phân trang cố định, vị trí từng hàng duy nhất**, thêm khóa phụ duy nhất và dùng giới hạn `ONLY`/LIMIT/TOP thường phù hợp hơn.

Không nên trộn hai yêu cầu “đầy đủ người đồng hạng” với “mỗi trang đúng n hàng” mà không thiết kế rõ quy tắc hiển thị.

### 8.4. `WITH TIES` không đồng nghĩa với RANK mọi nhóm

`WITH TIES` chỉ mở rộng các hàng **đồng hạng với hàng cuối cùng nằm trong phạm vi đã chọn**. Nó không tự tìm mọi nhóm thứ hạng trong toàn tập, và không tự phân biệt các loại xếp hạng `RANK`, `DENSE_RANK`, `ROW_NUMBER`. Nếu bài toán yêu cầu “mọi sản phẩm nằm trong 3 nhóm doanh thu cao nhất”, có thể cần hàm cửa sổ DENSE_RANK trên một truy vấn con, thay vì chỉ giới hạn ba hàng.

## 9. ORDER BY ổn định: điều kiện tiên quyết cho phân trang

Một bộ phận người học thấy câu:

```sql
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC
LIMIT 5;
```

và cho rằng kết quả ổn định vì đã có ORDER BY. Nhưng đơn 109 và 110 có cùng created_at. Nếu ranh giới LIMIT/OFFSET nằm giữa hai đơn có giá trị bằng nhau, DBMS có thể chọn thứ tự khác nhau giữa các lần chạy. Điều đó gây ra hai loại lỗi ở các trang:

1. Một hàng đã nằm ở trang 1 xuất hiện lại trên trang 2.
2. Một hàng nằm giữa nhóm đồng hạng không xuất hiện ở trang nào, tùy các lần truy vấn.

Cách viết rõ hơn:

```sql
ORDER BY created_at DESC, order_id DESC
```

Với `order_id` duy nhất và `created_at` không NULL ở bộ dữ liệu này, mỗi hàng có một vị trí xác định theo hai khóa.

**Tuy nhiên, ORDER BY duy nhất không phải bảo đảm tuyệt đối qua nhiều yêu cầu HTTP khác nhau.** Nếu bảng bị chèn/xóa/cập nhật giữa lúc người dùng chuyển trang, vị trí các hàng vẫn có thể thay đổi; OFFSET sẽ đếm trên **trạng thái dữ liệu tại thời điểm mỗi truy vấn**. Việc thứ tự là xác định trong từng trạng thái database khác với việc kết quả được cố định xuyên suốt phiên phân trang.

### 9.1. Ví dụ hàng bị lặp do có đơn mới

Giả sử trang 1 (size = 3) trả 110, 109, 108. Sau đó một đơn **111 mới hơn tất cả** được thêm vào trước khi trang 2 được gọi.

Thứ tự mới trở thành:

```text
111, 110, 109, 108, 107, 106, 105, ...
```

Nếu trang 2 dùng `OFFSET 3 LIMIT 3`, nó trả **108, 107, 106**. Đơn 108 đã xuất hiện ở trang 1 nên người dùng nhìn thấy trùng. Đây là hiệu ứng thay đổi dữ liệu giữa hai lần truy vấn, dù `ORDER BY created_at DESC, order_id DESC` vẫn hoàn toàn rõ ràng.

### 9.2. Giao dịch và snapshot

Ở những nghiệp vụ cần xem một tập kết quả đúng tại một thời điểm, có thể dùng **snapshot nhất quán** hoặc một cơ chế báo cáo được đóng băng theo thiết kế giao dịch và DBMS. Nhưng giữ giao dịch đọc lâu cho người dùng lướt nhiều trang có thể gây chi phí tài nguyên và vận hành. Không nên chỉ “mở transaction là ổn”: cần xét mức cô lập (`READ COMMITTED`, `REPEATABLE READ`, ...), quy tắc snapshot, thời gian phiên và dung lượng dữ liệu.

Phân trang theo con trỏ (*keyset/cursor pagination*) thường hợp lý hơn cho các màn hình tuần tự đọc dữ liệu đang thay đổi, được giải thích ở mục 11.

## 10. Chi phí của OFFSET lớn và cách DBMS thực thi

Một truy vấn:

```sql
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

về logic yêu cầu bỏ qua **100.000 hàng đứng trước**, sau đó lấy tối đa 20 hàng. DBMS không thể lấy đúng vị trí này nếu không xác định được những hàng đứng trước theo thứ tự yêu cầu. Ngay cả khi có chỉ mục B-tree phù hợp, hệ thống thường vẫn phải đi qua một lượng lớn mục chỉ mục/hàng để bỏ qua, thay vì “nhảy đến hàng thứ 100001” trong thời gian hằng số.

Chi phí của OFFSET sâu có thể thể hiện ở:

- Số hàng phải đọc, so sánh hoặc bỏ qua ngày càng lớn theo vị trí trang.
- Chi phí sort hoặc duyệt chỉ mục nhiều hơn, tùy kế hoạch.
- Độ trễ trang sâu cao hơn trang đầu và lượng CPU/I/O tăng.
- Kết quả giữa các trang dễ dịch chuyển nếu có dữ liệu mới hoặc bị xóa.

Các hệ quản trị có thể có nhiều tối ưu (ví dụ index scan theo thứ tự, top-N sort hoặc dừng sớm), nhưng **OFFSET lớn vẫn là vấn đề cần đo**, không nên giả định engine luôn bỏ qua một triệu hàng tức thì.

### 10.1. Chỉ mục phù hợp với ORDER BY

Trong PostgreSQL, với truy vấn danh sách mới nhất:

```sql
CREATE INDEX idx_demo_orders_recent
ON demo_orders (created_at DESC, order_id DESC);
```

Chỉ mục có thể hỗ trợ DBMS đọc hàng theo thứ tự mong muốn mà không cần sort toàn bộ. Khi truy vấn thêm điều kiện bằng trạng thái:

```sql
SELECT order_id, created_at, total_amount
FROM demo_orders
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

có thể cân nhắc một chỉ mục ứng viên khác:

```sql
CREATE INDEX idx_demo_orders_status_recent
ON demo_orders (status, created_at DESC, order_id DESC);
```

Vì `status` được lọc bằng điều kiện bằng, phần sau của chỉ mục có thể hữu ích cho sắp xếp các đơn trong cùng trạng thái. Không phải chỉ mục nào cũng đáng tạo: chi phí lưu trữ, ghi và kế hoạch thực tế phải được đánh giá trên khối lượng dữ liệu đại diện.

### 10.2. Đọc EXPLAIN thay vì đoán

```sql
EXPLAIN
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3 OFFSET 3;
```

PostgreSQL sẽ cho kế hoạch **ước lượng**. Trong môi trường phù hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3 OFFSET 3;
```

`EXPLAIN (ANALYZE, BUFFERS)` **thực sự chạy SELECT**, cho thông tin thời gian, số hàng và buffer/I/O. Cần xem node Limit, Sort/Index Scan, số dòng đọc và chênh lệch giữa ước lượng với số đo. Trên bảng mẫu 10 dòng, kế hoạch không phản ánh hiệu năng của bảng nhiều triệu hàng.

### 10.3. Trả toàn bộ dữ liệu cùng tổng số hàng có miễn phí không?

Một API phân trang thường cần cả `items` và `totalCount` để vẽ tổng số trang. Câu `COUNT(*)` với điều kiện lọc tương ứng là một phép tính **khác** với việc lấy 20 dòng:

```sql
SELECT COUNT(*)
FROM demo_orders
WHERE status = 'PAID';
```

DBMS có thể cần đọc nhiều thông tin để đếm, tùy chỉ mục, thống kê và độ chọn lọc. Không nên mặc định một truy vấn `LIMIT 20` có thể biết chính xác toàn bộ số hàng thỏa điều kiện mà không tốn thêm công. Với tập dữ liệu lớn, có thể dùng cách chỉ báo **hasNextPage** bằng việc lấy `pageSize + 1` hàng, hoặc chọn chiến lược đếm phù hợp nếu UX không cần tổng số trang chính xác.

## 11. Keyset pagination: phân trang theo khóa thay vì vị trí

Khi người dùng thường **xem tiếp** một danh sách theo thời gian (newsfeed, lịch sử giao dịch, đơn mới), một lựa chọn quan trọng là **keyset pagination** hay *cursor-based pagination*. Thay vì yêu cầu “bỏ qua 100.000 hàng”, ứng dụng yêu cầu “lấy những hàng **đứng sau bản ghi cuối cùng đã thấy** theo khóa sắp xếp”.

### 11.1. Trang đầu

```sql
SELECT order_id, created_at, total_amount
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3;
```

Kết quả trang đầu là **110, 109, 108**. Lưu lại khóa của hàng cuối: `created_at` của đơn 108 là `2026-06-08 09:00:00+07` và `order_id = 108`.

### 11.2. Trang tiếp theo bằng điều kiện khóa

Với PostgreSQL, khi cả hai khóa không NULL, có thể so sánh bộ giá trị:

```sql
SELECT order_id, created_at, total_amount
FROM demo_orders
WHERE (created_at, order_id) <
      (TIMESTAMPTZ '2026-06-08 09:00:00+07', 108)
ORDER BY created_at DESC, order_id DESC
LIMIT 3;
```

Kết quả tiếp theo là **107, 106, 105**. Không có OFFSET. Truy vấn tìm các hàng có cặp khóa **nhỏ hơn theo thứ tự so sánh từ trái sang phải**; với hai cột đều sắp DESC, điều kiện nhỏ hơn phù hợp để đi tới những hàng cũ hơn.

Biểu thức logic tương ứng và dễ diễn đạt hơn ở nhiều DBMS:

```sql
WHERE created_at < :last_created_at
   OR (
       created_at = :last_created_at
       AND order_id < :last_order_id
   )
ORDER BY created_at DESC, order_id DESC
```

Các `:last_created_at` và `:last_order_id` ở đây chỉ là ký hiệu tham số giả trong giải thích, **không phải cú pháp literal có thể chạy trực tiếp trên mọi DBMS**. Trong ứng dụng thực, phải bind tham số theo API/driver.

### 11.3. Vì sao keyset hữu ích?

- **Đi tiếp theo vị trí khóa thực**, thay vì đếm và bỏ qua mọi hàng đứng trước.
- Có thể tận dụng chỉ mục theo các cột lọc/sắp xếp để tìm vùng tiếp theo.
- Khi có đơn mới **đứng trước con trỏ**, trang kế tiếp không bị dịch sang phải theo OFFSET, nên tránh được một số trường hợp lặp hàng.
- Thích hợp với trải nghiệm “Xem thêm”, cuộn vô hạn, lịch sử theo thời gian.

Tuy vậy, keyset không phải công cụ thần kỳ:

- **Không tiện nhảy thẳng đến trang 500** khi chỉ có con trỏ của trang 1.
- Cần khóa sắp xếp **ổn định, đủ phân biệt**; nếu chỉ dùng thời điểm và nhiều hàng có cùng thời điểm, con trỏ có thể bỏ sót hàng. Thêm ID duy nhất.
- Nếu cột sắp xếp có thể cập nhật, hàng có thể chuyển vị trí giữa các lần gọi. Cần cân nhắc điều kiện lọc, chính sách đồng bộ và snapshot nếu bài toán đòi hỏi tính nhất quán tuyệt đối.
- Khi khóa có `NULL`, kết hợp chiều ASC/DESC hoặc collation đặc biệt, phải xây dựng biểu thức con trỏ phù hợp; không thể máy móc áp dụng cùng một dấu `<` cho mọi kiểu ORDER BY.
- Con trỏ gửi cho client cần được thiết kế/kiểm tra an toàn; có thể mã hóa dữ liệu khóa kèm thông tin bộ lọc hoặc chữ ký khi cần chống sửa, nhưng phải xác thực phía server.

### 11.4. OFFSET và keyset nên dùng trong tình huống nào?

| Tiêu chí | OFFSET pagination | Keyset pagination |
| --- | --- | --- |
| Nhảy trực tiếp đến trang n | Dễ: tính offset | Khó nếu không có cursor ở vùng cần đến |
| Trang đầu | Thường đơn giản và nhanh | Cũng đơn giản |
| Trang rất sâu | Có thể tốn chi phí bỏ qua nhiều hàng | Thường tốt hơn khi có index/khóa phù hợp |
| Dữ liệu mới chèn trước trang đang xem | Có thể làm lặp/trượt hàng | Ít bị ảnh hưởng đối với thao tác chèn trước cursor |
| Tổng số trang chính xác | Có thể phối hợp COUNT | Không mặc nhiên có tổng số trang |
| Độ phức tạp API | page, pageSize | cursor, limit, điều kiện thứ tự và bộ lọc |
| Trải nghiệm phù hợp | Bảng quản trị có điều hướng trang số | Feed, lịch sử giao dịch, “Load more” |

Không phải dự án nào cũng cần chuyển sang keyset. Chọn theo yêu cầu UX, độ sâu phân trang, biến động dữ liệu và kế hoạch đo được.

## 12. Phân trang trong API: kiểm soát tham số và bảo mật

Giả sử API nhận `page` và `pageSize`. Trước khi tạo SQL:

1. Quy định `page` bắt đầu từ **1** hay **0** và thống nhất giữa frontend/backend.
2. Kiểm tra `page` là số nguyên hợp lệ, không âm/theo quy ước; kiểm tra `pageSize` dương và không vượt giới hạn tối đa ứng dụng đặt ra.
3. Tính `offset` bằng kiểu số đủ rộng, kiểm tra tràn số khi `(page - 1) * pageSize`.
4. Chọn `ORDER BY` **cố định hoặc từ danh sách cột được phép**; thêm khóa phụ duy nhất.
5. Bind số lượng hàng và offset như **tham số giá trị**, không nối chuỗi không kiểm soát.
6. Không đưa dữ liệu nhạy cảm vào kết quả chỉ vì ứng dụng đang phân trang: danh sách SELECT và quyền truy cập vẫn cần được xác định.

Ví dụ prepared statement trong PostgreSQL:

```sql
PREPARE paged_orders(INTEGER, INTEGER) AS
SELECT order_id, created_at, total_amount
FROM demo_orders
ORDER BY created_at DESC, order_id DESC
LIMIT $1 OFFSET $2;

-- pageSize = 3, page = 2 -> offset = 3.
EXECUTE paged_orders(3, 3);
```

Ứng dụng thực nên truyền giá trị qua `PreparedStatement`/driver tương đương thay vì ghép tham số từ chuỗi do người dùng nhập. Cú pháp bind khác nhau giữa PostgreSQL, SQL Server và Oracle; tên cột/tên bảng dùng để sắp xếp **không thể chỉ thay bằng placeholder giá trị** giống một con số. Nếu cho người dùng chọn “mới nhất”, “giá cao nhất”, “tên A–Z”, phải ánh xạ lựa chọn đó vào **một danh sách ORDER BY đã được xác định trước**.

### 12.1. Ví dụ hợp đồng API

```text
GET /orders?page=2&pageSize=3&sort=newest

Chính sách:
- page bắt đầu từ 1
- pageSize tối đa 100
- sort chỉ nhận: newest, oldest, amount_desc
- newest -> ORDER BY created_at DESC, order_id DESC
- số offset = (2 - 1) * 3 = 3
- trả tối đa 3 bản ghi của người dùng/tổ chức được phép xem
```

Số lượng bản ghi được trả không thể được dùng làm **kiểm soát quyền**. Ví dụ `LIMIT 10` không có nghĩa chỉ lộ tối đa mười bản ghi nhạy cảm nếu điều kiện WHERE thiếu tenant/user authorization; nhiều lần gọi API vẫn có thể duyệt toàn bộ dữ liệu. Bảo vệ phạm vi truy cập cần xảy ra trước khi giới hạn hoặc song song như điều kiện bảo mật bắt buộc.

### 12.2. Phân trang cần lọc theo tổ chức/người dùng trước khi giới hạn

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :authorized_tenant_id
ORDER BY created_at DESC, order_id DESC
LIMIT :page_size OFFSET :offset;
```

Đây là **mẫu minh họa với tham số tên**: cột `tenant_id` và cú pháp placeholder phải phù hợp hệ thống thật. Điều quan trọng là điều kiện phân quyền **nằm ở truy vấn lấy dữ liệu**, không chỉ ở giao diện. Khi người dùng đổi trang hoặc sort, điều kiện ấy không được biến mất.

## 13. Những trường hợp dễ làm sai ý nghĩa kết quả

### 13.1. LIMIT trước khi chọn hàng lớn nhất

Giả sử muốn năm đơn giá trị cao nhất. Truy vấn đúng:

```sql
SELECT order_id, total_amount
FROM demo_orders
ORDER BY total_amount DESC, order_id DESC
LIMIT 5;
```

Truy vấn dễ sai:

```sql
SELECT order_id, total_amount
FROM (
    SELECT order_id, total_amount
    FROM demo_orders
    LIMIT 5
) AS chosen
ORDER BY total_amount DESC, order_id DESC;
```

Truy vấn ngoài chỉ sắp xếp **năm hàng đã được chọn không theo thứ tự xác định** ở truy vấn trong; không thể bảo đảm đó là năm đơn có số tiền cao nhất. ORDER BY ở đúng cấp truy vấn quyết định tập hàng nào được đưa vào LIMIT.

### 13.2. ORDER BY trong subquery không thay thế ORDER BY ngoài

Một subquery/CTE có ORDER BY có thể sử dụng thứ tự đó để xác định chính xác những hàng được FETCH/LIMIT bên trong. Nhưng không nên giả định thứ tự đã được lưu truyền xuyên qua mọi tầng:

```sql
SELECT order_id, total_amount
FROM (
    SELECT order_id, total_amount
    FROM demo_orders
    ORDER BY total_amount DESC, order_id DESC
    LIMIT 5
) AS chosen
ORDER BY order_id ASC;
```

Ở đây **tập năm đơn** được xác định theo số tiền giảm dần ở truy vấn trong, còn **thứ tự hiển thị của năm đơn** được quyết định bởi `ORDER BY order_id ASC` ở ngoài. Hai ORDER BY có mục đích khác nhau.

### 13.3. Giới hạn sau GROUP BY: giới hạn nhóm, không giới hạn hàng nguồn

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(total_amount) AS total_amount
FROM demo_orders
GROUP BY customer_id
ORDER BY total_amount DESC, customer_id
LIMIT 2;
```

Truy vấn trả **hai khách hàng có tổng tiền đơn cao nhất** trong dữ liệu mẫu, không phải “hai đơn hàng rồi mới cộng theo khách”. Nếu đưa `LIMIT 2` vào subquery nguồn trước GROUP BY, doanh thu của từng khách có thể bị thiếu vì chỉ tính trên hai đơn đã chọn.

Khi dùng DISTINCT, tương tự, LIMIT/FETCH được áp dụng lên **các hàng đầu ra sau khi xử lý tập kết quả liên quan** theo mô hình logic, không được hiểu là cố định một số hàng nguồn trước khi loại trùng.

### 13.4. Phân trang với NULL hoặc giá trị sắp xếp trùng

Trong PostgreSQL:

```sql
SELECT order_id, total_amount
FROM demo_orders
ORDER BY total_amount DESC NULLS LAST, order_id DESC
LIMIT 5;
```

Ở bảng mẫu total_amount NOT NULL, nhưng trong bảng thực cột sắp xếp có thể nullable. Vị trí NULL mặc định khác nhau giữa các DBMS. PostgreSQL/Oracle hỗ trợ `NULLS FIRST`/`NULLS LAST` ở ORDER BY; SQL Server thường cần `CASE` hoặc biểu thức thay thế khi muốn kiểm soát vị trí NULL theo chính sách cụ thể.

Nếu cần phân trang nhất quán qua DBMS, phải định nghĩa rõ **thứ tự NULL, quy tắc chữ hoa/chữ thường và collation**, không chỉ tên cột với ASC/DESC. Thêm một khóa duy nhất ở cuối ORDER BY để phân biệt các hàng còn trùng.

### 13.5. Phân trang bằng ROW_NUMBER

Khi cần một cách tiếp cận tương đối dễ áp dụng ở các DBMS có hỗ trợ hàm cửa sổ, có thể đánh số thứ tự rồi lọc ở khối ngoài:

```sql
WITH ranked_orders AS (
    SELECT
        order_id,
        created_at,
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM demo_orders
)
SELECT order_id, created_at
FROM ranked_orders
WHERE rn BETWEEN 4 AND 6
ORDER BY rn;
```

Kết quả tương đương trang 2, size 3 (các ID 107, 106, 105) trong trạng thái dữ liệu mẫu. `ROW_NUMBER()` đánh số từ **1**, nên vị trí trang 2 là 4–6; trong khi OFFSET đếm số hàng bỏ qua từ **0**. Không thể dùng `WHERE rn BETWEEN 4 AND 6` ở **cùng khối SELECT** đang tạo alias `rn`; phải dùng CTE/truy vấn con để khối ngoài lọc được giá trị này.

`ROW_NUMBER` không mặc nhiên nhanh hơn OFFSET; DBMS vẫn phải xác định thứ tự và đánh số các hàng liên quan. Cách viết này đặc biệt hữu ích khi cần gắn số thứ tự, chọn top-N theo **từng nhóm** hoặc hỗ trợ những phiên bản/hệ hạn chế cú pháp OFFSET/FETCH.

## 14. Sai lầm thường gặp khi chuyển đổi giữa các DBMS

| Cách hiểu hoặc cách viết sai | Vấn đề | Cách xử lý |
| --- | --- | --- |
| Sao chép `LIMIT 10` của PostgreSQL vào SQL Server | SQL Server không dùng cú pháp LIMIT ấy | Dùng `TOP (10)` hoặc `OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY` |
| Sao chép `TOP (10)` của SQL Server vào PostgreSQL | TOP không phải cú pháp giới hạn của PostgreSQL | Dùng `LIMIT 10` hoặc `FETCH FIRST 10 ROWS ONLY` |
| Dùng `FETCH FIRST 10 ROWS ONLY` trực tiếp thay thế trong mọi phiên bản MySQL | Hệ thường dùng LIMIT, mức hỗ trợ khác nhau | Dùng cú pháp MySQL của phiên bản đích |
| Quên OFFSET khi viết FETCH NEXT của SQL Server | Cấu trúc OFFSET/FETCH có yêu cầu riêng | Viết `ORDER BY ... OFFSET 0 ROWS FETCH NEXT n ROWS ONLY` |
| Nhầm `LIMIT 10, 20` nghĩa là lấy 10 rồi bỏ 20 | Trong MySQL, số đầu là offset | Hiểu là bỏ 10, lấy 20; ưu tiên LIMIT 20 OFFSET 10 |
| Dùng LIMIT/TOP mà không có ORDER BY | “Hàng đầu tiên” không có nghĩa xác định | Thêm thứ tự theo nghiệp vụ |
| ORDER BY chỉ có ngày, nhiều bản ghi cùng ngày | Các hàng đồng hạng có thể đổi vị trí | Thêm khóa phụ duy nhất, ví dụ order_id |
| Mặc định trang tiếp theo không thay đổi khi dữ liệu mới tới | OFFSET đếm trên trạng thái mỗi lần truy vấn | Cân nhắc keyset/snapshot theo mục tiêu |
| Dùng `WITH TIES` và yêu cầu trang đúng n bản ghi | WITH TIES có thể trả thêm nhiều hàng | Tách nhu cầu đồng hạng khỏi nhu cầu kích thước trang |
| Dùng `TOP 10 PERCENT` khi muốn đúng 10 hàng | PERCENT tính tỷ lệ, không phải số hàng | Dùng `TOP (10)` |
| Tin rằng index làm OFFSET rất lớn thành miễn phí | Thường vẫn phải duyệt các mục cần bỏ qua | Đo bằng EXPLAIN và cân nhắc keyset |
| Tính `(page - 1) * size` mà không xác thực | Page âm, size 0 hoặc tràn số | Ràng buộc phạm vi và kiểu số |
| Nối trực tiếp tên cột sort do user nhập | Dễ gây SQL injection ở identifier/cú pháp | Dùng danh sách lựa chọn ORDER BY cho phép |
| Dùng LIMIT để kiểm soát quyền truy cập | Chỉ giảm số hàng một lần gọi, không phân quyền | Lọc theo quyền/tenant đúng ở phía server |
| Dùng ROW_NUMBER theo ORDER BY không duy nhất | Hạng có thể không ổn định với giá trị bằng nhau | Thêm khóa phụ duy nhất trong OVER |

## 15. Bài tập ứng dụng

Hãy làm các bài dưới đây với bảng `demo_orders` đã tạo ở mục 2; các bài yêu cầu cú pháp DBMS khác sử dụng một bảng `orders` có cấu trúc logic tương đương.

### Bài 1 — Ba đơn mới nhất

Viết câu SELECT lấy đúng ba đơn mới nhất theo `created_at`, dùng `order_id` giảm dần để phân biệt thời điểm trùng nhau. Viết hai phiên bản cho PostgreSQL: một phiên bản dùng `LIMIT`, một phiên bản dùng `FETCH FIRST`.

Gợi ý: cả hai đều có `ORDER BY created_at DESC, order_id DESC` và phải trả **110, 109, 108**.

### Bài 2 — Trang thứ ba, mỗi trang ba hàng

API đánh số trang từ 1. Tính `OFFSET` của trang 3 và viết câu SQL PostgreSQL. Dự đoán ba `order_id` được trả. Sau đó chuyển phần giới hạn sang cú pháp `LIMIT offset, count` của MySQL và `OFFSET ... FETCH` của SQL Server/Oracle.

Gợi ý: `OFFSET = (3 - 1) * 3 = 6`; kết quả của dữ liệu mẫu là **104, 103, 102**.

### Bài 3 — TOP và FETCH khác vị trí thế nào?

Viết câu SQL Server lấy năm đơn có tổng tiền cao nhất bằng `TOP (5)`. Sau đó viết bằng `ORDER BY ... OFFSET 0 ROWS FETCH NEXT 5 ROWS ONLY`. Tại sao câu `SELECT TOP (5) ... LIMIT 5` không phải là cách ghép hai cú pháp để “chắc chắn” lấy năm hàng?

### Bài 4 — Đồng hạng doanh thu

Theo tổng tiền giảm dần, yêu cầu “hai vị trí đầu và tất cả đơn đồng hạng với vị trí thứ hai”. Dùng PostgreSQL `FETCH FIRST 2 ROWS WITH TIES` và SQL Server `TOP (2) WITH TIES`. Dự đoán **số hàng trả về là 4**. Nếu thêm `order_id` vào ORDER BY, vì sao có thể chỉ còn đúng 2 hàng?

### Bài 5 — Dữ liệu thay đổi giữa hai trang

Giả sử trang 1 trả **110, 109, 108**. Sau đó chèn thêm đơn 111 có thời điểm tạo mới hơn tất cả trước khi chạy truy vấn lấy trang 2 bằng `OFFSET 3`. Hãy chỉ ra vì sao **108 có thể xuất hiện lần thứ hai**. Viết cách lấy trang 2 bằng con trỏ `(created_at, order_id)` của đơn 108 để tránh tác động từ một đơn mới đứng trước nó.

### Bài 6 — Sắp xếp có NULL

Giả sử bảng `products` có `rating` nullable. Cần hiển thị các sản phẩm có rating cao nhất trước, sản phẩm chưa có rating cuối cùng; nhiều sản phẩm có thể cùng rating. Hãy thiết kế `ORDER BY` có xử lý NULL và khóa phụ duy nhất. Vì sao chỉ viết `ORDER BY rating DESC` có thể chưa đủ khi chuyển DBMS?

### Bài 7 — Tổng số trang

Một bảng sau khi lọc có 101 hàng, mỗi trang lấy 20 hàng. Có bao nhiêu trang? Trang cuối có bao nhiêu hàng? Vì sao truy vấn lấy trang hiện tại với LIMIT 20 không tự cung cấp miễn phí tổng số 101?

Gợi ý: số trang là `CEIL(101.0 / 20) = 6`; trang cuối có một hàng. Có thể dùng `COUNT(*)` theo điều kiện lọc tương ứng để biết tổng số hàng nếu thật sự cần.

### Bài 8 — Sửa thứ tự đặt LIMIT sai cấp

Một bạn muốn lấy năm đơn có tổng tiền cao nhất nhưng viết `SELECT ... FROM (SELECT ... LIMIT 5) ... ORDER BY total_amount DESC`. Hãy giải thích vì sao câu này không bảo đảm đúng tập kết quả và sửa lại bằng ORDER BY ở cấp tương ứng.

### Bài 9 — Thử phân trang với ROW_NUMBER

Sử dụng `ROW_NUMBER() OVER (ORDER BY created_at DESC, order_id DESC)` và CTE để lấy các hàng có `rn BETWEEN 4 AND 6`. So sánh với `LIMIT 3 OFFSET 3`. Phần nào là vị trí **1-based** và phần nào là số hàng bỏ qua **0-based**?

### Bài 10 — API chống lạm dụng

Đề xuất quy tắc cho các đầu vào `page`, `pageSize`, `sort`: giới hạn pageSize, kiểm tra tràn offset, danh sách sort được phép và điều kiện tenant. Viết một câu SQL có tham số hóa số hàng và offset. Vì sao không nên ghép trực tiếp `ORDER BY ` với một chuỗi sort bất kỳ do client gửi?

## 16. Tóm tắt thực hành

Khi chuyển một yêu cầu phân trang thành SQL, nên thực hiện theo trình tự:

```text
Xác định đúng tập hàng được phép xem và điều kiện lọc
                     |
                     v
Chọn ORDER BY theo nghiệp vụ
  + khóa phụ duy nhất để ổn định thứ tự
                     |
                     v
Chọn cách giới hạn của DBMS
  PostgreSQL/MySQL : LIMIT n OFFSET m
  PostgreSQL/Oracle: OFFSET m ROWS FETCH NEXT n ROWS ONLY
  SQL Server       : TOP (n) hoặc ORDER BY ... OFFSET/FETCH
                     |
                     v
Xác thực page/pageSize/sort, bind tham số
                     |
                     v
Đo hiệu năng; nếu OFFSET sâu, cân nhắc keyset
```

**`LIMIT`, `FETCH FIRST` và `TOP` đều hướng tới việc chọn một phần kết quả, nhưng cú pháp và tính năng phụ trợ khác nhau theo hệ quản trị.** `OFFSET` giúp tính trang bằng vị trí, song cần `ORDER BY` đủ phân biệt và có thể tốn chi phí đáng kể ở những trang sâu. `WITH TIES` giải quyết bài toán đồng hạng chứ không phải giới hạn chính xác kích thước trang. Với danh sách biến động liên tục, keyset pagination thường là hướng cần xem xét.

Nguyên tắc cuối cùng: **phân trang đúng bắt đầu từ ngữ nghĩa sắp xếp và phạm vi dữ liệu, không bắt đầu bằng việc chọn từ khóa LIMIT hay TOP**. Sau khi xác định thứ tự, tính ổn định, quyền truy cập và trải nghiệm trang, mới chọn cú pháp tương thích với PostgreSQL, MySQL, SQL Server hoặc Oracle và kiểm chứng hiệu năng trên hệ thống thực.
