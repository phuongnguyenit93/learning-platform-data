# LIMIT, OFFSET, FETCH và yêu cầu thứ tự xác định trong PostgreSQL

Một bảng PostgreSQL có thể chứa hàng triệu đơn hàng, trong khi màn hình quản trị chỉ muốn hiển thị 20 đơn mỗi lần. Ta thường viết `LIMIT` để giới hạn số hàng, `OFFSET` để bỏ qua một số hàng đầu, hoặc dùng cú pháp chuẩn SQL `FETCH FIRST/NEXT`. Tuy nhiên, những lệnh đó **chỉ thật sự tạo ra các trang có thể dự đoán khi truy vấn xác định rõ thứ tự của các hàng**.

Ví dụ:

```sql
SELECT order_id, created_at
FROM orders
LIMIT 10;
```

Lệnh có thể trả 10 hàng, nhưng **không hề hứa đó là 10 đơn hàng đầu tiên theo thời gian, theo ID hay theo thứ tự chèn**. Ngay cả khi cùng một câu lệnh liên tục trả cùng 10 hàng trong bài lab, đó vẫn không phải một bảo đảm của SQL.

Thêm `ORDER BY created_at DESC` giúp đặt đơn mới lên trước, nhưng nếu nhiều đơn có cùng `created_at` thì thứ tự giữa các đơn đó vẫn chưa được xác định. Đây là nguyên nhân phổ biến khiến phân trang bị **trùng hàng, bỏ sót hàng hoặc thay đổi thứ tự** dù bảng tưởng chừng không có vấn đề gì.

Bài học thuộc chương *Truy vấn cơ bản* trong module *Database Engine Relational PostgreSQL*, hướng dẫn:

- Cú pháp và ý nghĩa của `LIMIT`, `OFFSET`, `FETCH FIRST/NEXT` và `WITH TIES`.
- Lý do **không có `ORDER BY` thì không có thứ tự kết quả được bảo đảm**.
- Cách bổ sung cột phân định duy nhất (*tie-breaker*) để tạo **thứ tự xác định**.
- Cách dùng `NULLS FIRST/LAST`, sắp xếp nhiều cột và xử lý giá trị bằng nhau.
- Phân trang theo số trang (*offset pagination*) và phân trang theo khóa cuối trang (*keyset/cursor pagination*).
- Ảnh hưởng của dữ liệu được chèn, xóa, cập nhật đồng thời; chi phí của `OFFSET` lớn; chỉ mục phục vụ sắp xếp.
- Thiết kế truy vấn an toàn cho API, kiểm tra kết quả và bài tập thực hành.

> **Mấu chốt:** `LIMIT`/`OFFSET`/`FETCH` không tự tạo thứ tự. **`ORDER BY` là điều kiện cơ bản**, và `ORDER BY` với các khóa không duy nhất vẫn có thể chưa đủ để phân trang ổn định. Trong bài, những ví dụ có `FETCH ... WITH TIES` giả định PostgreSQL phiên bản hỗ trợ tính năng này (PostgreSQL 13 trở lên).

## 1. Hiểu kết quả truy vấn là một tập hàng không có thứ tự mặc định

### 1.1. SELECT không tự hứa thứ tự

Xét câu lệnh:

```sql
SELECT order_id, customer_name
FROM orders;
```

Không có `ORDER BY`, PostgreSQL có quyền dùng nhiều kế hoạch thực thi: sequential scan, index scan, parallel scan và các phép nối hoặc xử lý khác. Những kế hoạch đó có thể tạo ra các thứ tự quan sát khác nhau.

Điểm cần nhớ:

- Thứ tự ghi bản ghi **không phải** thứ tự mặc định của `SELECT`.
- Thứ tự vật lý của các row trong heap **không phải** một hợp đồng cho ứng dụng.
- Có index trên `order_id` **không có nghĩa** mọi `SELECT` sẽ trả theo `order_id`.
- Dữ liệu vừa được `VACUUM`, `UPDATE`, thay đổi thống kê hoặc thay đổi query plan vẫn phải được truy vấn với `ORDER BY` nếu thứ tự quan trọng.
- **`LIMIT 10`** chỉ giới hạn số hàng trả ra, không xác định **10 hàng nào** được chọn nếu không có thứ tự.

PostgreSQL có thể đưa ra một thứ tự trông ổn định nhiều lần; tính ổn định đó chỉ là **hệ quả ngẫu nhiên của kế hoạch tại thời điểm thử**, không phải điều kiện đúng để dựa vào.

### 1.2. ORDER BY xác định thứ tự, nhưng cần xét các hàng bằng khóa

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC;
```

Câu này xác định đơn có thời điểm **lớn hơn đứng trước** đơn có thời điểm nhỏ hơn. Nhưng nếu ba hàng có `created_at` bằng nhau, SQL không yêu cầu PostgreSQL trả ba hàng đó theo ID, theo thứ tự chèn hay bất kỳ quy tắc phụ nào.

Muốn xác định cả thứ tự trong nhóm cùng thời điểm:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC;
```

Nếu `order_id` là **PRIMARY KEY**, tổ hợp `(created_at, order_id)` phân biệt mọi hàng, nên đây là một **thứ tự toàn phần ổn định cho cùng một tập dữ liệu và cùng ngữ nghĩa so sánh**.

### 1.3. Thứ tự xác định không đồng nghĩa ảnh chụp dữ liệu bất biến

Ngay cả khi `ORDER BY created_at DESC, order_id DESC` đã duy nhất, các truy vấn phân trang chạy ở **hai thời điểm khác nhau** có thể nhìn thấy dữ liệu khác nhau do transaction khác chèn, xóa hoặc cập nhật.

Vì thế cần phân biệt hai mục tiêu:

1. **Deterministic ordering**: với cùng tập hàng, cùng giá trị khóa và cùng cách sắp xếp, thứ tự có thể xác định.
2. **Consistent pagination across time**: nhiều lần lấy trang đều dựa trên một tập dữ liệu nhất quán hoặc một quy tắc cursor rõ ràng.

`ORDER BY` là nền tảng của mục tiêu 1; nó **chưa tự giải quyết mục tiêu 2**.

## 2. Tạo bộ dữ liệu thực hành có các giá trị sắp xếp trùng nhau

Để nhìn thấy những lỗi hay gặp, dùng một bảng đơn hàng riêng:

```sql
CREATE SCHEMA IF NOT EXISTS page_lab;

CREATE TABLE page_lab.orders (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    customer_name TEXT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled'))
);
```

Thêm 16 đơn; **nhiều đơn cố ý có cùng thời điểm**:

```sql
INSERT INTO page_lab.orders
    (order_id, created_at, customer_name, amount, status)
VALUES
    (101, '2026-11-01 10:00:00+00', 'An',    120000, 'paid'),
    (102, '2026-11-01 10:00:00+00', 'Bình',   85000, 'paid'),
    (103, '2026-11-01 09:00:00+00', 'Chi',   200000, 'new'),
    (104, '2026-11-02 08:00:00+00', 'Dũng',   45000, 'paid'),
    (105, '2026-11-02 08:00:00+00', 'Hà',     99000, 'new'),
    (106, '2026-11-02 08:00:00+00', 'Khánh',  66000, 'paid'),
    (107, '2026-11-03 13:30:00+00', 'Lan',   300000, 'new'),
    (108, '2026-11-03 13:30:00+00', 'Minh',  125000, 'paid'),
    (109, '2026-11-03 13:30:00+00', 'Ngọc',   75000, 'paid'),
    (110, '2026-11-04 07:00:00+00', 'Phúc',   56000, 'new'),
    (111, '2026-11-04 07:00:00+00', 'Quỳnh',  84000, 'paid'),
    (112, '2026-11-05 11:00:00+00', 'Sơn',   150000, 'new'),
    (113, '2026-11-05 11:00:00+00', 'Trang',  70000, 'paid'),
    (114, '2026-11-05 11:00:00+00', 'Uyên',   90000, 'paid'),
    (115, '2026-11-06 12:00:00+00', 'Vy',   105000, 'cancelled'),
    (116, '2026-11-06 12:00:00+00', 'Yến',   40000, 'paid');
```

Các timestamp có offset `+00` để biểu diễn thời điểm UTC. PostgreSQL lưu `TIMESTAMPTZ` như các thời điểm và trình bày lại theo `TimeZone` của phiên; việc sắp xếp theo `TIMESTAMPTZ` dựa trên thời điểm, không chỉ chuỗi hiển thị.

Truy vấn chuẩn dùng xuyên suốt:

```sql
SELECT order_id, created_at, customer_name
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC;
```

Các `order_id` theo thứ tự xác định:

```text
116, 115, 114, 113, 112, 111, 110, 109,
108, 107, 106, 105, 104, 102, 101, 103
```

Thứ tự này đến từ **hai khóa ORDER BY**: thời gian giảm dần trước; khi thời gian bằng nhau, `order_id` giảm dần.

> Các ID và thời điểm là dữ liệu lab được khai báo tường minh, giúp người học kiểm tra kết quả. Không xem thứ tự như trên là do `INSERT` hay `PRIMARY KEY` tự tạo ra khi câu lệnh `SELECT` không có `ORDER BY`.

## 3. LIMIT: lấy tối đa N hàng

`LIMIT` là cú pháp PostgreSQL rất phổ biến để giới hạn số hàng:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Kết quả với bộ dữ liệu lab:

| Vị trí | order_id |
|---:|---:|
| 1 | 116 |
| 2 | 115 |
| 3 | 114 |
| 4 | 113 |
| 5 | 112 |

**`LIMIT 5` nghĩa là trả tối đa năm hàng** sau khi PostgreSQL áp dụng các điều kiện và thứ tự liên quan. Nếu chỉ có ba hàng phù hợp, kết quả chỉ có ba hàng. Nó không tự bổ sung hàng hoặc tự báo lỗi vì chưa đủ năm hàng.

### 3.1. LIMIT với WHERE

```sql
SELECT order_id, amount, status
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

PostgreSQL tìm các hàng `status='paid'` theo điều kiện, rồi trả **tối đa năm hàng đầu theo thứ tự yêu cầu**. Không hiểu `LIMIT 5` là “lấy năm hàng bất kỳ trước, sau đó mới lọc status”.

Thứ tự viết cú pháp thông thường là:

```sql
SELECT ...
FROM ...
WHERE ...
ORDER BY ...
LIMIT ...;
```

Không đặt `LIMIT` trước `ORDER BY` trong cùng một SELECT.

### 3.2. LIMIT 0, LIMIT ALL và LIMIT không được có giá trị âm

```sql
-- Trả không hàng nào.
SELECT order_id FROM page_lab.orders ORDER BY order_id LIMIT 0;

-- Không đặt giới hạn số hàng bằng LIMIT.
SELECT order_id FROM page_lab.orders ORDER BY order_id LIMIT ALL;
```

`LIMIT 0` hữu ích khi muốn biểu đạt một tập kết quả rỗng theo cú pháp giới hạn, hoặc trong một số tình huống xem metadata/cấu trúc truy vấn. `LIMIT ALL` tương đương việc không đặt giới hạn `LIMIT` (nhưng vẫn tuân theo `OFFSET` nếu có).

Không dùng `LIMIT -5`: giá trị âm không hợp lệ. Với ứng dụng nhận `page_size` từ client, phải kiểm tra và giới hạn cỡ trang trước khi truyền vào SQL.

### 3.3. LIMIT không có ORDER BY không tạo “top N”

```sql
SELECT order_id FROM page_lab.orders LIMIT 5;
```

Câu này chỉ có nghĩa **năm hàng nào đó** được chọn theo kế hoạch thực thi, không phải “năm đơn mới nhất” hoặc “năm ID nhỏ nhất”.

Muốn top 5 theo giá trị đơn:

```sql
SELECT order_id, amount
FROM page_lab.orders
ORDER BY amount DESC, order_id DESC
LIMIT 5;
```

Nếu hai đơn cùng `amount`, `order_id DESC` phân định thứ tự; nếu không có cột phụ, vị trí của các đơn đồng giá trị chưa xác định.

## 4. OFFSET: bỏ qua N hàng đầu của tập đã sắp xếp

`OFFSET N` bỏ qua N hàng đầu trước khi trả phần còn lại, theo thứ tự do truy vấn quy định.

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

Kết quả trang thứ hai theo bộ dữ liệu lab:

| Vị trí sau sắp xếp | order_id |
|---:|---:|
| 6 | 111 |
| 7 | 110 |
| 8 | 109 |
| 9 | 108 |
| 10 | 107 |

`OFFSET 5` bỏ qua năm hàng đầu; `LIMIT 5` lấy năm hàng tiếp theo. Truy vấn không thể biết “trang thứ hai” nếu bạn không xác định **trang là thứ hai của thứ tự nào**.

### 4.1. Công thức phân trang theo số trang

Nếu page bắt đầu từ 1:

\[
\text{offset}=(\text{page}-1)\times \text{pageSize}
\]

Ví dụ pageSize = 5:

| Trang | LIMIT | OFFSET | order_id dự kiến |
|---:|---:|---:|---|
| 1 | 5 | 0 | 116, 115, 114, 113, 112 |
| 2 | 5 | 5 | 111, 110, 109, 108, 107 |
| 3 | 5 | 10 | 106, 105, 104, 102, 101 |
| 4 | 5 | 15 | 103 |
| 5 | 5 | 20 | Không có hàng |

Trang thứ nhất:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 0;
```

Trang thứ ba:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 10;
```

Nếu `OFFSET` lớn hơn số hàng phù hợp, kết quả trống; đây thường là tình huống hợp lệ của API.

### 4.2. OFFSET 0 và OFFSET không cần LIMIT

`OFFSET 0` không bỏ qua hàng nào:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY order_id
OFFSET 0;
```

PostgreSQL cho phép dùng `OFFSET` mà không có `LIMIT`:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY order_id
OFFSET 10;
```

Lệnh thứ hai bỏ mười hàng đầu và trả **tất cả hàng còn lại**, không mặc định trả mười hàng. Đừng quên `LIMIT` khi API chỉ cho phép trả một kích thước trang nhỏ.

### 4.3. OFFSET âm và những giá trị không hợp lệ

`OFFSET -1` không hợp lệ. Giá trị `NULL` hoặc những cách dùng đặc biệt không nên được coi là định dạng API chuẩn; hãy truyền các số nguyên rõ nghĩa, giới hạn bởi logic ứng dụng.

Đối với số trang/cỡ trang do client gửi, cần xử lý:

- page phải là số nguyên dương (nếu quy ước từ 1).
- pageSize phải là số nguyên dương và có **ngưỡng tối đa**.
- Offset được tính với kiểu số đủ rộng để không overflow.
- Trang quá sâu có thể bị hạn chế vì chi phí xử lý và yêu cầu sản phẩm.

## 5. FETCH FIRST và FETCH NEXT: cú pháp theo chuẩn SQL

PostgreSQL hỗ trợ cú pháp `FETCH` để diễn đạt số hàng đầu tiên hoặc số hàng tiếp theo:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 5 ROWS ONLY;
```

Tương đương về mục tiêu với:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Một cách viết khác:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH NEXT 5 ROWS ONLY;
```

Trong ngữ cảnh `FETCH`, `FIRST` và `NEXT` đều được chấp nhận với ý nghĩa chọn số hàng theo giới hạn. **`FETCH NEXT` không tự nhớ trang trước**: muốn bỏ qua dữ liệu đầu, vẫn phải ghi `OFFSET` hoặc dùng điều kiện cursor.

### 5.1. OFFSET ... FETCH NEXT ...

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
OFFSET 5 ROWS
FETCH NEXT 5 ROWS ONLY;
```

Lệnh tương ứng:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

Cú pháp `OFFSET 5 ROWS` có tính chất diễn đạt chuẩn SQL; với `LIMIT`, PostgreSQL cũng chấp nhận `OFFSET 5`. Một số hệ quản trị khác hỗ trợ `FETCH` nhưng không dùng `LIMIT` giống PostgreSQL.

### 5.2. FIRST ROW và FIRST 1 ROWS

PostgreSQL chấp nhận dạng:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST ROW ONLY;
```

Khi bỏ số lượng ở dạng `FETCH FIRST ROW ONLY`, mặc định là **một hàng**. Có thể viết đầy đủ:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 1 ROW ONLY;
```

### 5.3. Không trộn LIMIT với FETCH trong cùng SELECT

`LIMIT` và `FETCH FIRST/NEXT` là hai cách cung cấp **giới hạn số hàng** cho một câu SELECT. Không ghép cả hai vào cùng một SELECT:

```sql
-- Không dùng cú pháp pha trộn kiểu này:
-- SELECT * FROM page_lab.orders
-- ORDER BY order_id
-- LIMIT 5 FETCH FIRST 5 ROWS ONLY;
```

Chọn một cách: `LIMIT ... OFFSET ...` cho phong cách PostgreSQL quen thuộc, hoặc `OFFSET ... FETCH ...` khi muốn gần chuẩn SQL/khả chuyển hơn.

## 6. FETCH ... WITH TIES: lấy thêm các hàng đồng hạng ở ranh giới

Một biến thể quan trọng là **`WITH TIES`**. Thay vì cắt đúng số hàng, PostgreSQL có thể trả thêm các hàng **đồng hạng theo toàn bộ biểu thức `ORDER BY`** với hàng cuối nằm trong giới hạn.

Ví dụ:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC
FETCH FIRST 3 ROWS WITH TIES;
```

Trong bộ dữ liệu lab:

- Hai đơn `116` và `115` có `created_at = '2026-11-06 12:00:00+00'`.
- Ba đơn `114`, `113`, `112` có `created_at = '2026-11-05 11:00:00+00'`.
- Hàng thứ ba theo `created_at DESC` thuộc nhóm ngày 05/11; **cả nhóm đồng thời điểm** được lấy.

Do đó, câu lệnh trả **năm hàng** (`116`, `115` và `114`, `113`, `112`), dù viết `FETCH FIRST 3 ROWS WITH TIES`.

**Lưu ý:** Trong mỗi nhóm có cùng `created_at`, thứ tự ID vẫn không xác định vì `ORDER BY` chỉ có thời điểm. Để xem kết quả theo ID ổn định mà vẫn giữ ý nghĩa “mọi hàng cùng thời điểm”, có thể bọc kết quả vào subquery/CTE rồi sắp xếp ngoài:

```sql
WITH top_timestamps AS (
    SELECT order_id, created_at
    FROM page_lab.orders
    ORDER BY created_at DESC
    FETCH FIRST 3 ROWS WITH TIES
)
SELECT order_id, created_at
FROM top_timestamps
ORDER BY created_at DESC, order_id DESC;
```

`WITH TIES` quyết định **tập hàng ở ranh giới** theo thứ tự bên trong; `ORDER BY` ngoài giúp trình bày những hàng đã chọn theo thứ tự xác định.

### 6.1. Vì sao thêm order_id vào ORDER BY sẽ làm mất ties?

Xét:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 3 ROWS WITH TIES;
```

Vì `order_id` là khóa chính, **không có hai hàng nào có cùng toàn bộ khóa sắp xếp** `(created_at, order_id)`. Kết quả chỉ là ba hàng.

Đây là sự khác biệt quan trọng giữa hai mục tiêu:

- **Phân trang với kích thước chính xác và thứ tự duy nhất:** thêm tie-breaker để thứ tự xác định.
- **Lấy mọi hàng đồng hạng theo chỉ số nghiệp vụ:** chỉ đưa những biểu thức xác định hạng vào `ORDER BY` của `FETCH ... WITH TIES`, rồi có thể sắp xếp thêm ở truy vấn bao ngoài.

Đừng cố vừa yêu cầu “mọi hàng cùng điểm được tính đồng hạng” vừa thêm ID duy nhất vào danh sách xếp hạng rồi kỳ vọng `WITH TIES` còn trả những hàng đồng điểm.

### 6.2. WITH TIES yêu cầu ORDER BY

Trong PostgreSQL, `FETCH FIRST N ROWS WITH TIES` cần có `ORDER BY` phù hợp. Nếu không có thứ tự, khái niệm “đồng hạng với hàng cuối” không được xác định.

```sql
-- Không có ORDER BY: cú pháp/ngữ nghĩa không hợp lệ cho WITH TIES.
-- SELECT * FROM page_lab.orders FETCH FIRST 3 ROWS WITH TIES;
```

### 6.3. WITH TIES không phù hợp với API yêu cầu đúng N hàng

Một endpoint khai báo “pageSize = 20” thường muốn trả **tối đa 20 item**. `WITH TIES` có thể trả 21, 50 hoặc nhiều hơn nếu nhiều hàng có cùng khóa xếp hạng ở ranh giới. Vì thế, đừng dùng `WITH TIES` làm lựa chọn mặc định cho phân trang số trang.

Nó phù hợp với các bài toán **top N có đồng hạng**, chẳng hạn “lấy mọi vận động viên có điểm bằng người ở vị trí thứ ba”. Nếu cần đánh số thứ hạng nghiệp vụ, cân nhắc cả `RANK()`/`DENSE_RANK()` và nêu rõ cách xử lý tie.

## 7. ORDER BY: cách xây một thứ tự xác định

### 7.1. Sắp xếp theo một cột chưa chắc đủ

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC
LIMIT 5;
```

Đây là lệnh có ý nghĩa “ưu tiên thời gian mới nhất”, nhưng hàng `116` và `115` có cùng thời điểm; hàng `114`, `113`, `112` cũng có cùng thời điểm. Thứ tự trong mỗi nhóm **không bị quy định**.

Người học có thể thấy ID 116 trước 115 trên một lần chạy và suy ra PostgreSQL mặc định dùng ID giảm dần. Đó là suy luận không có bảo đảm.

### 7.2. Thêm cột phân định duy nhất

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Vì `order_id` duy nhất, mỗi hàng có vị trí xác định với cùng tập dữ liệu:

```text
116, 115, 114, 113, 112
```

Không nhất thiết phải dùng cột tên `id`. Có thể dùng:

- Một khóa chính số nguyên.
- UUID duy nhất, nếu có kiểu sắp xếp ổn định và phù hợp nghiệp vụ.
- Một tổ hợp cột duy nhất, miễn là **thực sự phân biệt** mọi hàng được trả và ngữ nghĩa NULL/collation được xử lý.

Nếu cột tie-breaker cũng có thể trùng, thứ tự vẫn chưa hoàn toàn xác định.

### 7.3. Nhiều cột cùng chiều và khác chiều

```sql
-- Tổng tiền cao xuống thấp; tiền bằng nhau thì ID lớn trước.
SELECT order_id, amount
FROM page_lab.orders
ORDER BY amount DESC, order_id DESC
LIMIT 5;

-- Trạng thái theo tên tăng dần, thời gian mới trước,
-- ID nhỏ trước khi cùng trạng thái và thời gian.
SELECT order_id, status, created_at
FROM page_lab.orders
ORDER BY status ASC, created_at DESC, order_id ASC
LIMIT 8;
```

Mỗi biểu thức `ORDER BY` có thể chọn `ASC` hoặc `DESC` riêng. Trong keyset pagination, **thứ tự hỗn hợp** này cần điều kiện cursor cẩn thận hơn phép so sánh tuple cùng chiều.

### 7.4. ORDER BY NULLS FIRST/LAST

PostgreSQL cho phép điều khiển vị trí `NULL`:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC NULLS LAST, order_id DESC;
```

Trong bảng lab `created_at NOT NULL` nên `NULLS LAST` không làm thay đổi kết quả, nhưng rất quan trọng nếu dữ liệu thực có thời điểm chưa biết.

Mặc định trong PostgreSQL:

| Kiểu sắp xếp | Vị trí NULL mặc định |
|---|---|
| `ORDER BY col ASC` | `NULLS LAST` |
| `ORDER BY col DESC` | `NULLS FIRST` |

Muốn mới nhất trước nhưng để ngày chưa biết xuống cuối:

```sql
SELECT *
FROM (
    VALUES
        (1, TIMESTAMPTZ '2026-11-02 08:00:00+00'),
        (2, NULL::TIMESTAMPTZ),
        (3, TIMESTAMPTZ '2026-11-04 08:00:00+00'),
        (4, NULL::TIMESTAMPTZ)
) AS x(order_id, created_at)
ORDER BY created_at DESC NULLS LAST, order_id DESC;
```

Kết quả ID dự kiến: `3, 1, 4, 2`. Hai hàng `NULL` cùng nhóm được sắp theo `order_id DESC`.

### 7.5. Collation và biểu thức cũng ảnh hưởng khóa sắp xếp

Với chuỗi:

```sql
SELECT order_id, customer_name
FROM page_lab.orders
ORDER BY lower(customer_name), order_id;
```

`lower(customer_name)` có thể trả cùng chuỗi cho hai tên khác nhau về chữ hoa/thường. Vì vậy vẫn cần `order_id` làm tie-breaker nếu muốn thứ tự xác định.

**Collation** quyết định cách so sánh/sắp xếp text. Với các collation có quy tắc đặc biệt, hai chuỗi khác byte có thể được xem tương đương ở mức so sánh. Khi cần phân trang ổn định, hãy dùng khóa phân định duy nhất và đảm bảo các phiên/client áp dụng cùng quy tắc sort. Không giả định việc nâng cấp thư viện collation hoặc đổi cấu hình locale là không có tác động.

### 7.6. ORDER BY bên ngoài mới quyết định thứ tự kết quả cuối

Một subquery/CTE có `ORDER BY` không có nghĩa **truy vấn bên ngoài** luôn giữ thứ tự đó sau khi join, aggregate hoặc biến đổi khác:

```sql
SELECT order_id
FROM (
    SELECT order_id, created_at
    FROM page_lab.orders
    ORDER BY created_at DESC
) AS x
LIMIT 5;
```

Không nên dựa vào thứ tự nội bộ như một hợp đồng phân trang. Viết `ORDER BY` ở tầng SELECT **thực sự áp dụng `LIMIT`/`OFFSET` cuối cùng**, hoặc cấu trúc query có giới hạn bên trong với ngữ nghĩa được chủ động kiểm soát.

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Tương tự, khi có `UNION`, `DISTINCT` hoặc `GROUP BY`, thứ tự cuối vẫn cần `ORDER BY` của truy vấn trả kết quả cho client nếu cần cam kết thứ tự.

## 8. Vì sao LIMIT/OFFSET thiếu thứ tự duy nhất gây trùng hoặc mất hàng?

Giả sử câu lệnh:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC
LIMIT 3 OFFSET 0;
```

Khi có các thời điểm bằng nhau, server chỉ phải giữ đúng thứ tự **giữa các nhóm thời gian**, nhưng được tự do sắp thứ tự **trong nhóm**. Một truy vấn thứ hai:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC
LIMIT 3 OFFSET 3;
```

không có bảo đảm thứ tự trong các nhóm đồng thời điểm giống truy vấn đầu, đặc biệt khi optimizer chọn kế hoạch khác do `LIMIT`/`OFFSET` khác. Kết quả có thể trùng hàng hoặc bỏ qua hàng khi ghép hai trang, **ngay cả không có thay đổi dữ liệu** nếu không có total order.

Khắc phục cơ bản:

```sql
-- Trang 1
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3 OFFSET 0;

-- Trang 2
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 3 OFFSET 3;
```

Với cùng ảnh dữ liệu, thứ tự được phân định bằng `order_id` nên các trang không chồng lên nhau do tie trong sort key.

### 8.1. ORDER BY trên cột unique có đủ không?

Nếu `order_id` là primary key và không `NULL`:

```sql
ORDER BY order_id DESC
```

đủ tạo thứ tự duy nhất. Nhưng nếu bài toán muốn **đơn mới nhất trước**, chỉ sắp theo ID không nhất thiết tương đương thời gian tạo; ID có thể được import, cấp lệch thứ tự, hoặc cập nhật dữ liệu lịch sử.

Hãy chọn **khóa chính theo nghiệp vụ cần sắp xếp**, sau đó thêm **cột unique để phân định**.

### 8.2. Sắp xếp theo số lượng lớn và trường nhiều giá trị trùng

Cột `status` có ba trạng thái `new`, `paid`, `cancelled`. Câu:

```sql
SELECT order_id, status
FROM page_lab.orders
ORDER BY status
LIMIT 5;
```

cho biết nhóm status nào đứng trước, nhưng trong mỗi nhóm có thể có nhiều đơn không có vị trí duy nhất. Nếu thực sự muốn trang theo status:

```sql
SELECT order_id, status
FROM page_lab.orders
ORDER BY status ASC, order_id DESC
LIMIT 5;
```

## 9. Lấy trang sau bằng LIMIT/OFFSET: dễ hiểu nhưng có chi phí

Một API có thể dùng hai tham số:

```text
GET /orders?page=3&pageSize=20
```

Nếu page bắt đầu từ 1, offset là `(3-1)*20 = 40`:

```sql
SELECT order_id, created_at, customer_name, amount
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 40;
```

Thiết kế này có ưu điểm:

- Dễ diễn giải số trang 1, 2, 3.
- Có thể nhảy trực tiếp tới trang bất kỳ.
- Hữu ích khi bảng nhỏ, số trang ít hoặc dữ liệu ít biến động.

Nhưng có hai hạn chế:

1. **Offset lớn thường tốn công xử lý**: server phải xác định và bỏ qua các hàng trước offset.
2. **Dữ liệu thay đổi giữa các lần gọi**: vị trí hàng có thể dịch chuyển, dẫn đến trùng hoặc mất hàng qua các trang.

### 9.1. OFFSET lớn không phải “nhảy miễn phí” tới hàng thứ N

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
```

Về mặt logic, truy vấn phải xác định **ít nhất 100.020 vị trí đầu** theo thứ tự yêu cầu để bỏ qua 100.000 rồi lấy 20 hàng, nếu có đủ dữ liệu. Index phù hợp có thể giúp thứ tự và tránh sort toàn bộ theo cách đắt đỏ, nhưng **vẫn có công việc duyệt/bỏ qua nhiều entry**.

Vì vậy, page 5000 với pageSize 20 có thể chậm hơn page 1 rõ rệt. Đừng suy luận `LIMIT 20` bảo đảm PostgreSQL chỉ đọc/đụng đến 20 hàng.

### 9.2. Chỉ mục phục vụ ORDER BY

Với mẫu truy vấn:

```sql
SELECT order_id, created_at, amount
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

có thể cân nhắc B-tree index:

```sql
CREATE INDEX orders_created_id_desc_idx
ON page_lab.orders (created_at DESC, order_id DESC);
```

Index này có thứ tự phù hợp với `ORDER BY`. PostgreSQL có thể sử dụng index scan để lấy các hàng đầu mà không phải sort toàn bộ bảng, tùy kích thước, thống kê và chi phí.

**Bảng lab chỉ có 16 hàng**, nên optimizer có thể vẫn chọn sequential scan + sort. Điều đó không chứng minh index vô ích cho bảng production lớn.

### 9.3. Khi vừa lọc theo status vừa sắp xếp

Truy vấn:

```sql
SELECT order_id, created_at, amount
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Một index có thể phù hợp hơn:

```sql
CREATE INDEX orders_status_created_id_idx
ON page_lab.orders (status, created_at DESC, order_id DESC);
```

Vì `status` được lọc bằng điều kiện bằng, index có thể tận dụng nhóm trạng thái rồi thứ tự thời điểm/ID. Tuy nhiên index chiếm dung lượng, làm tăng chi phí `INSERT`/`UPDATE` và không nhất thiết tốt nhất nếu status phân bố rất lệch hoặc query ít dùng.

Không tạo index chỉ bằng cách sao chép ví dụ. Hãy đo workload thực, tần suất truy vấn, selectivity và chi phí ghi.

### 9.4. Đọc kế hoạch thực thi

```sql
EXPLAIN
SELECT order_id, created_at
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

Nếu muốn đo runtime/I/O:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

`EXPLAIN ANALYZE` **thực thi câu truy vấn** để thu số liệu; trên SELECT đọc thì phù hợp để thử trong môi trường kiểm soát, nhưng với một lệnh ghi nên hết sức cẩn thận. So sánh `OFFSET 0` và `OFFSET 100000` trên bảng lớn mới cho thấy chênh lệch thực tế; demo 16 hàng chỉ để học cú pháp.

## 10. Keyset pagination: tiếp tục sau khóa cuối trang

Khi cần cuộn danh sách lớn, người dùng thường muốn “lấy thêm 20 hàng sau những hàng đang có” hơn là nhảy tới một **số trang tuyệt đối**. Phân trang theo khóa (*keyset* hoặc *seek pagination*) dùng **giá trị khóa sắp xếp của hàng cuối trang trước** làm con trỏ.

Thay vì:

```sql
SELECT ...
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
```

ta hỏi:

> “Cho tôi năm hàng đứng **sau** cặp khóa `(created_at, order_id)` mà trang trước đã kết thúc.”

### 10.1. Trang đầu không có cursor

```sql
SELECT order_id, created_at, customer_name
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Với dữ liệu lab, trang đầu là:

```text
116, 115, 114, 113, 112
```

Hàng cuối có:

```text
created_at = 2026-11-05 11:00:00+00
order_id   = 112
```

Lưu **cả hai giá trị** làm cursor. Không chỉ lưu timestamp, vì có thể có nhiều hàng cùng timestamp.

### 10.2. Trang tiếp theo với ORDER BY giảm dần

```sql
SELECT order_id, created_at, customer_name
FROM page_lab.orders
WHERE (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-05 11:00:00+00', 112)
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Kết quả:

```text
111, 110, 109, 108, 107
```

Vì cả hai cột được sắp **DESC**, sau cặp khóa cuối trang `(T, ID)` là các hàng có:

- `created_at < T`, **hoặc**
- `created_at = T` và `order_id < ID`.

So sánh tuple `(created_at, order_id) < (T, ID)` thực hiện so sánh **từ trái sang phải**, phù hợp với thứ tự sắp xếp giảm dần ở ví dụ này.

### 10.3. Viết điều kiện tương đương bằng OR

```sql
SELECT order_id, created_at, customer_name
FROM page_lab.orders
WHERE created_at < TIMESTAMPTZ '2026-11-05 11:00:00+00'
   OR (
       created_at = TIMESTAMPTZ '2026-11-05 11:00:00+00'
       AND order_id < 112
   )
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Hai cách tương đương khi các cột so sánh **không NULL**, kiểu dữ liệu có phép so sánh phù hợp và mọi khóa cùng chiều DESC. Cách `OR` diễn đạt rõ vì sao cần tie-breaker.

### 10.4. Trang thứ ba bằng cursor tiếp theo

Trang thứ hai kết thúc ở `order_id=107`, `created_at='2026-11-03 13:30:00+00'`:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-03 13:30:00+00', 107)
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Kết quả:

```text
106, 105, 104, 102, 101
```

Trang tiếp sau có `order_id=103` rồi hết. Cơ chế này không cần `OFFSET 10`, `OFFSET 15`; nó đi tiếp từ **cột mốc thực tế của trang trước**.

### 10.5. ASC thì đổi dấu

Nếu sắp tăng dần theo:

```sql
ORDER BY created_at ASC, order_id ASC
```

thì hàng **sau** cursor `(T, ID)` có khóa:

```sql
WHERE (created_at, order_id) > (T, ID)
```

Đừng sao chép dấu `<` từ truy vấn DESC sang ASC. Sai dấu làm phân trang quay về phía trước hoặc trả tập hàng không đúng.

### 10.6. Thứ tự hỗn hợp phải viết điều kiện khác

Với:

```sql
ORDER BY created_at DESC, order_id ASC
```

điều kiện cho hàng đứng **sau** cursor `(T, ID)` là:

```sql
WHERE created_at < T
   OR (created_at = T AND order_id > ID)
```

Lúc này dùng trực tiếp `(created_at, order_id) < (T, ID)` là **sai**, vì phép so sánh tuple thông thường cho hai thành phần cùng một chiều; còn thứ tự yêu cầu là **DESC cho thời gian nhưng ASC cho ID**.

Ví dụ truy vấn với cursor giả định:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE created_at < TIMESTAMPTZ '2026-11-05 11:00:00+00'
   OR (
       created_at = TIMESTAMPTZ '2026-11-05 11:00:00+00'
       AND order_id > 113
   )
ORDER BY created_at DESC, order_id ASC
LIMIT 5;
```

Ở production, hãy thiết kế cursor theo **tất cả các biểu thức ORDER BY**, chiều sắp xếp, NULL handling và collation đang dùng, rồi xây điều kiện seek tương ứng.

### 10.7. Keyset cần khóa không NULL hoặc cách xử lý NULL rõ ràng

Ví dụ dùng `created_at TIMESTAMPTZ NOT NULL` và `order_id PRIMARY KEY`, vì phép so sánh hàng với `NULL` không còn tuân một thứ tự đơn giản dựa trên dấu `<`/`>`.

Nếu khóa sort nullable:

- Xác định chính sách `NULLS FIRST` hoặc `NULLS LAST`.
- Quy định cách mã hóa cursor cho hàng có `NULL`.
- Viết điều kiện chuyển vùng giữa các hàng có và không có `NULL` một cách tường minh.
- Dùng tie-breaker duy nhất không NULL.

Không áp dụng phép so sánh tuple giản lược cho dữ liệu nullable rồi kỳ vọng mọi hàng `NULL` được đi qua. Tùy quy mô có thể thiết kế một khóa sort chuẩn hóa/được duy trì riêng, nhưng phải đánh giá ngữ nghĩa và index.

### 10.8. Keyset phù hợp trường hợp nào?

| Yêu cầu | LIMIT/OFFSET | Keyset |
|---|---|---|
| Lấy trang 1, 2, 3 với bảng nhỏ | Đơn giản | Cần cursor |
| Nhảy trực tiếp tới trang 500 | Hỗ trợ cú pháp | Không tự nhảy tới số trang tùy ý |
| Cuộn vô hạn feed/log/đơn hàng | Có thể, nhưng offset tăng dần | Thường phù hợp hơn |
| Bảng rất lớn, phân trang sâu | Có thể đắt | Có thể tận dụng index để seek |
| Đơn mới chèn lên đầu giữa các lần tải | Dễ dịch offset | Thường ít bị ảnh hưởng hơn nếu sort key ổn định |
| Sort theo nhiều chiều hoặc nullable | ORDER BY dễ viết hơn | Cursor và điều kiện seek phức tạp hơn |
| Cần ảnh chụp nhất quán tuyệt đối | Không tự bảo đảm | Cũng không tự bảo đảm |

**Keyset không phải “OFFSET nhưng nhanh hơn trong mọi truy vấn”**. Nó là một mô hình API khác, đổi khả năng truy cập trang ngẫu nhiên lấy cơ chế đi tiếp theo khóa.

## 11. Phân trang khi dữ liệu bị chèn, xóa hoặc cập nhật đồng thời

Một ứng dụng thực tế hiếm khi giữ bảng bất biến giữa lúc tải trang 1 và trang 2.

### 11.1. INSERT mới ở đầu khiến OFFSET bị dịch

Giả sử đang có ID theo thứ tự:

```text
Trang 1 ban đầu: [116, 115, 114, 113, 112]
Trang 2 ban đầu: [111, 110, 109, 108, 107]
```

Sau khi client tải trang 1, transaction khác thêm đơn `117` có thời điểm mới hơn tất cả.

Thứ tự mới:

```text
[117, 116, 115, 114, 113, 112, 111, 110, ...]
```

Client tiếp tục gọi `LIMIT 5 OFFSET 5` trên ảnh dữ liệu mới; vị trí 6 lúc này là **112**, vốn đã xuất hiện cuối trang 1. Hàng **112 có thể bị lặp** khi ghép trang.

**ORDER BY có ID unique vẫn không ngăn tình huống này**, vì nguyên nhân là **tập dữ liệu thay đổi**, không phải thứ tự giữa các khóa bằng nhau.

### 11.2. DELETE phía trước khiến OFFSET bỏ sót hàng

Với cùng trang 1 đã tải, nếu một hàng phía trên ranh giới bị xóa trước truy vấn trang 2, các vị trí sau nó dịch lên. Khi bỏ qua năm vị trí, client có thể **bỏ sót một hàng chưa tải**.

Ví dụ, xóa ID 116 sau khi trang 1 đã được nhận: danh sách còn `115,114,113,112,111,110,...`. Trang 2 với `OFFSET 5` bắt đầu ở `110`, nên ID `111` chưa có ở trang 1 lại bị bỏ qua.

### 11.3. Keyset giảm rủi ro dịch offset, nhưng không khóa ảnh dữ liệu

Với cursor cuối trang 1 là `(2026-11-05 11:00:00+00, 112)`:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-05 11:00:00+00', 112)
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Một đơn mới **đứng trước** cursor sẽ không làm đổi điểm bắt đầu của trang tiếp theo. Tuy nhiên:

- Một hàng cũ bị xóa có thể không còn để trả.
- Một hàng đổi `created_at` có thể chuyển qua ranh giới cursor và bị bỏ sót/trùng khi xét nhiều lần lấy trang.
- Một hàng mới nhưng có timestamp **cũ hơn cursor** vẫn có thể xuất hiện ở trang sau.
- Thay đổi điều kiện lọc (ví dụ `status`) có thể khiến hàng rời hoặc vào tập kết quả.

Do đó, keyset **ổn định hơn trước hiện tượng dịch vị trí do chèn ở đầu**, không phải cơ chế tự động bảo đảm “một ảnh chụp vĩnh viễn của danh sách”.

### 11.4. MVCC và isolation level

PostgreSQL dùng MVCC (*Multi-Version Concurrency Control*). Ở isolation `READ COMMITTED` thông thường, **mỗi statement** có thể quan sát snapshot mới. Hai request HTTP phân trang thường chạy hai statement ở hai transaction khác nhau, nên có thể nhìn thấy thay đổi giữa các trang.

Trong một transaction `REPEATABLE READ`, PostgreSQL giữ snapshot nhất quán cho các truy vấn phù hợp trong transaction, giúp cùng một tập dữ liệu không đổi do commit bên ngoài trong suốt transaction đó:

```sql
-- Chỉ minh họa một transaction đọc được kiểm soát.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 0;

SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;

COMMIT;
```

Nhưng **không nên giữ một transaction mở suốt nhiều phút hoặc hàng giờ chỉ để người dùng cuộn trang**: transaction dài có thể giữ snapshot cũ, ảnh hưởng vacuum, tài nguyên và vận hành.

Nếu nghiệp vụ cần một **tập kết quả đóng băng** cho xuất báo cáo, hãy thiết kế snapshot, bộ ID được chốt, export job hoặc chiến lược đọc nhất quán phù hợp thay vì trông chờ `OFFSET`/`keyset` tự giải quyết.

### 11.5. Đọc từ nhiều replica

Nếu các request phân trang đi đến **những replica khác nhau** hoặc một replica đang có độ trễ replication, client có thể thấy các trạng thái dữ liệu khác nhau dù sort key đã duy nhất.

Với yêu cầu tính nhất quán, cần có chính sách routing/read consistency và hiểu replication lag. Việc chọn `ORDER BY` đúng là cần thiết nhưng không thay thế thiết kế đọc nhất quán của toàn hệ thống.

## 12. COUNT(*) và tổng số trang

Giao diện phân trang theo số trang thường hiển thị:

```text
Trang 3 / 25 — 487 đơn hàng
```

Để tính số trang, trước hết cần biết số hàng phù hợp với **cùng bộ lọc**:

```sql
SELECT COUNT(*) AS total_rows
FROM page_lab.orders
WHERE status = 'paid';
```

Nếu `pageSize = 20` và `total_rows = 487` thì số trang là:

\[
\operatorname{totalPages}
=\left\lceil\frac{\operatorname{totalRows}}{\operatorname{pageSize}}\right\rceil
=\left\lceil\frac{487}{20}\right\rceil
=25
\]

### 12.1. Bộ lọc của COUNT và SELECT phải thống nhất

Nếu danh sách chỉ lấy đơn `paid`:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 0;
```

thì `COUNT(*)` cũng phải có `WHERE status='paid'`. Nếu đếm tất cả đơn nhưng phân trang chỉ đơn đã thanh toán, tổng trang hiển thị sẽ sai.

### 12.2. Đếm tổng và lấy trang trong hai truy vấn có thể thấy hai snapshot

Với `READ COMMITTED`, hai statement có thể quan sát thay đổi khác nhau do transaction khác commit giữa chúng. Do đó `COUNT(*)` có thể là 487 ở thời điểm đếm, nhưng tới lúc lấy trang đã có 488 hoặc 486 đơn phù hợp.

Nếu API cần tổng số **chính xác gắn với cùng snapshot** của dữ liệu trang, phải thiết kế transaction/isolation phù hợp hoặc một truy vấn kết hợp; đừng mặc định hai câu SELECT rời luôn khớp tuyệt đối.

### 12.3. COUNT(*) OVER() trong truy vấn phân trang

Có thể dùng window function:

```sql
SELECT
    order_id,
    created_at,
    COUNT(*) OVER () AS total_rows
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 0;
```

`COUNT(*) OVER ()` cho tổng số hàng của tập lọc trong truy vấn này trước `LIMIT`. Tuy nhiên:

- Có thể cần xử lý nhiều hàng hơn so với truy vấn chỉ lấy trang, tăng chi phí trên bảng lớn.
- Nếu `OFFSET` vượt qua tất cả các hàng, truy vấn trả **không hàng nào**, tức cũng **không có ô `total_rows`** để đọc.
- Nó không làm phân trang `OFFSET` miễn nhiễm với thay đổi giữa các request sau đó.

Đây là một lựa chọn để cân nhắc, không phải quy tắc “luôn thay hai truy vấn bằng một truy vấn thì nhanh hơn”.

### 12.4. Không phải API nào cũng cần tổng số trang

Với infinite scroll, client thường chỉ cần biết:

- Các item của trang hiện tại.
- Cursor để lấy trang sau.
- Có còn trang tiếp không?

Một cách phổ biến là lấy `pageSize + 1` hàng để kiểm tra còn hàng tiếp, rồi trả tối đa `pageSize` hàng cho client:

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 6;
```

Nếu pageSize là 5 và nhận 6 hàng, có ít nhất một hàng tiếp theo **tại thời điểm truy vấn**. Lấy hàng thứ 5 làm cursor cho trang kế; hàng thứ 6 chỉ là tín hiệu. Với dữ liệu thay đổi đồng thời, tín hiệu này vẫn có thể thay đổi khi request sau đến.

## 13. Phân trang bằng ROW_NUMBER(): dùng khi cần đánh số vị trí

`ROW_NUMBER()` gán số thứ tự theo một `ORDER BY` trong window:

```sql
WITH numbered AS (
    SELECT
        order_id,
        created_at,
        ROW_NUMBER() OVER (
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM page_lab.orders
)
SELECT order_id, created_at, rn
FROM numbered
WHERE rn BETWEEN 6 AND 10
ORDER BY rn;
```

Kết quả tương ứng trang thứ hai của bộ dữ liệu lab khi pageSize = 5.

**Có hai ORDER BY ở hai tầng:**

1. `ORDER BY` bên trong `OVER` xác định cách đánh `rn`.
2. `ORDER BY rn` ở truy vấn bên ngoài xác định thứ tự **trả kết quả cuối cùng**.

Không nên bỏ `order_id` tie-breaker ở window nếu muốn số thứ tự ổn định trong nhóm trùng `created_at`.

### 13.1. Khi nào ROW_NUMBER hữu ích?

Nó hữu ích khi:

- Cần đánh số mỗi hàng trong một kết quả.
- Cần chọn hàng có thứ hạng trong từng nhóm với `PARTITION BY`.
- Muốn trình bày vị trí trong một báo cáo.

Nhưng trên bảng lớn, việc tính và lọc `rn` không nhất thiết nhanh hơn `LIMIT/OFFSET` hoặc keyset, vì PostgreSQL có thể cần xếp hạng rất nhiều hàng trước khi lấy một khoảng vị trí. Dùng `EXPLAIN` để đánh giá.

### 13.2. ROW_NUMBER khác RANK và DENSE_RANK

Nếu hai đơn có cùng `amount`:

```sql
SELECT
    order_id,
    amount,
    ROW_NUMBER() OVER (ORDER BY amount DESC, order_id DESC) AS rn,
    RANK() OVER (ORDER BY amount DESC) AS business_rank,
    DENSE_RANK() OVER (ORDER BY amount DESC) AS dense_business_rank
FROM page_lab.orders;
```

`ROW_NUMBER` với ID làm khóa phụ cho mỗi hàng một số riêng. `RANK` và `DENSE_RANK` theo `amount` coi các hàng đồng tiền là cùng hạng, với quy tắc khác nhau về khoảng nhảy hạng. Khi yêu cầu **“top 3 mức điểm, bao gồm các hàng đồng điểm”**, hãy xác định muốn `WITH TIES` theo boundary row hay hạng theo `RANK/DENSE_RANK`.

## 14. DISTINCT, GROUP BY và UNION không thay thế ORDER BY

Một số người nghĩ các toán tử này “tự sắp thứ tự”:

```sql
SELECT DISTINCT status
FROM page_lab.orders
LIMIT 2;
```

Không có bảo đảm “hai trạng thái đầu” theo thứ tự chữ cái. Muốn rõ:

```sql
SELECT DISTINCT status
FROM page_lab.orders
ORDER BY status ASC
LIMIT 2;
```

Tương tự:

```sql
SELECT status, COUNT(*) AS so_don
FROM page_lab.orders
GROUP BY status
ORDER BY so_don DESC, status ASC
LIMIT 2;
```

`GROUP BY` không cam kết thứ tự trình bày. `ORDER BY so_don DESC, status ASC` đảm bảo có tie-breaker nếu hai trạng thái có cùng số đơn; `status` ở ví dụ là khóa duy nhất của kết quả sau khi GROUP BY.

### 14.1. Sau UNION cần sắp xếp tập kết quả chung

```sql
SELECT order_id FROM page_lab.orders WHERE status = 'new'
UNION
SELECT order_id FROM page_lab.orders WHERE status = 'paid'
ORDER BY order_id DESC
LIMIT 5;
```

`ORDER BY` cuối sắp xếp tập kết quả UNION chung. Nếu đặt `LIMIT` trong từng nhánh thông qua subquery, ý nghĩa sẽ khác: mỗi nhánh bị giới hạn riêng **trước** khi hợp nhất.

### 14.2. DISTINCT ON cần thứ tự để chọn hàng đại diện

PostgreSQL có `DISTINCT ON`:

```sql
SELECT DISTINCT ON (status)
    status, order_id, created_at
FROM page_lab.orders
ORDER BY status, created_at DESC, order_id DESC;
```

Truy vấn chọn **một hàng đại diện cho mỗi status**, ưu tiên thời gian mới nhất rồi ID lớn nhất. Nếu bỏ thứ tự phụ, hàng đại diện khi có thời điểm bằng nhau có thể không xác định. Đây là cùng bài học về tie-breaker, dù không dùng `LIMIT`.

## 15. Viết truy vấn phân trang an toàn từ ứng dụng

Không nối thẳng `LIMIT`/`OFFSET` từ chuỗi request vào câu SQL nếu không kiểm soát kiểu và phạm vi. Dùng tham số bind và xác thực đầu vào.

### 15.1. Prepared statement trong PostgreSQL

```sql
PREPARE page_orders(INTEGER, INTEGER) AS
SELECT order_id, created_at, customer_name, amount
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT $1 OFFSET $2;

EXECUTE page_orders(5, 0);
EXECUTE page_orders(5, 5);

DEALLOCATE page_orders;
```

`$1` là kích thước trang, `$2` là offset. Chúng là **giá trị**, không phải tên cột SQL; nếu cho người dùng tùy chọn sort key, không thể dùng bind parameter để thay thế tùy ý một identifier trong `ORDER BY` theo nghĩa mong muốn.

### 15.2. Java JDBC với LIMIT/OFFSET

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderQueries {
    public static void readPage(
            Connection connection, int page, int pageSize
    ) throws SQLException {
        if (page < 1 || pageSize < 1 || pageSize > 100) {
            throw new IllegalArgumentException(
                "page >= 1 và pageSize trong khoảng 1..100"
            );
        }

        long offset = ((long) page - 1L) * pageSize;

        String sql = """
            SELECT order_id, created_at, customer_name, amount
            FROM page_lab.orders
            ORDER BY created_at DESC, order_id DESC
            LIMIT ? OFFSET ?
            """;

        try (PreparedStatement stmt =
                 connection.prepareStatement(sql)) {
            stmt.setInt(1, pageSize);
            stmt.setLong(2, offset);

            try (ResultSet rs = stmt.executeQuery()) {
                while (rs.next()) {
                    System.out.println(rs.getLong("order_id"));
                }
            }
        }
    }
}
```

Ví dụ dùng Java text block (Java 15+). `offset` tính bằng `long` để tránh overflow của phép nhân `int` thông thường. Ứng dụng thực tế có thể đặt giới hạn offset rất sâu và áp timeout/resource budget, thay vì cho client yêu cầu trang tùy ý.

### 15.3. Cho client chọn ORDER BY mà không mở đường cho SQL injection

Một request có thể có:

```text
GET /orders?sort=created_at&direction=desc&page=1
```

Tên cột và hướng sort không nên được nối trực tiếp từ chuỗi chưa kiểm soát. Hãy dùng **whitelist**:

| sort hợp lệ | ORDER BY do server sinh |
|---|---|
| `created_at_desc` | `created_at DESC, order_id DESC` |
| `amount_desc` | `amount DESC, order_id DESC` |
| `order_id_asc` | `order_id ASC` |

Mọi sort key cuối cùng phải đủ để tạo thứ tự xác định. Nếu một sort option chưa được hỗ trợ hoặc cần quyền riêng, server từ chối thay vì dùng thẳng đầu vào làm tên cột, biểu thức hay mệnh đề SQL.

### 15.4. Cursor của keyset nên chứa gì?

Một cursor có thể mã hóa:

```json
{
  "createdAt": "2026-11-05T11:00:00Z",
  "orderId": 112,
  "sort": "created_at_desc_order_id_desc"
}
```

Tuy nhiên, trong API production:

- Cursor nên gắn với **sort mode**, bộ lọc và phiên bản format.
- Không để client sửa cursor tùy ý nếu điều đó ảnh hưởng an toàn hoặc logic truy cập; có thể ký/kiểm tra tính toàn vẹn.
- Không nhúng secret hoặc dữ liệu nhạy cảm vào cursor chỉ được base64 hóa, vì base64 **không mã hóa**.
- Tất cả các giá trị sắp xếp ảnh hưởng tới điểm tiếp tục đều phải được lưu hoặc khôi phục một cách đáng tin.
- Khi đổi collation/sort/điều kiện lọc, cursor cũ có thể không còn hợp lệ.

Cursor là **một vị trí logic trong thứ tự**, không phải số dòng vật lý hoặc vị trí byte của file PostgreSQL.

## 16. Bảng tổng hợp LIMIT, OFFSET, FETCH và keyset

| Cách dùng | Dạng SQL | Điểm mạnh | Hạn chế |
|---|---|---|---|
| Lấy N hàng đầu | `ORDER BY ... LIMIT N` | Ngắn gọn, phổ biến | Nếu sort không duy nhất có thể chọn hàng boundary tùy ý |
| Lấy trang K | `ORDER BY ... LIMIT N OFFSET M` | Nhảy trực tiếp theo số trang | Offset sâu tốn công; dữ liệu mới làm dịch vị trí |
| Dạng chuẩn SQL | `ORDER BY ... OFFSET M ROWS FETCH NEXT N ROWS ONLY` | Dễ đọc, gần chuẩn SQL | Cùng vấn đề sort/offset như LIMIT |
| Top N có đồng hạng | `ORDER BY score DESC FETCH FIRST N ROWS WITH TIES` | Giữ mọi hàng bằng khóa xếp hạng ở ranh giới | Có thể trả nhiều hơn N; thứ tự trong ties chưa xác định |
| Cuộn theo cursor | `WHERE (sort_key,id) < (:last_key,:last_id) ORDER BY ... LIMIT N` | Thường hiệu quả và ổn định trước insert ở đầu | Khó nhảy trang ngẫu nhiên; cần xử lý sort/null/cập nhật |
| Đánh số thứ tự | `ROW_NUMBER() OVER (ORDER BY ...)` | Hữu ích khi cần số vị trí/hạng | Có thể phải xử lý nhiều hàng; vẫn cần tie-breaker |

**Tất cả** những cách này đều cần định nghĩa rõ **“đầu tiên” là đầu tiên theo thứ tự nào**. `FETCH WITH TIES` còn cần xác định “đồng hạng” theo những biểu thức nào.

## 17. Các lỗi thường gặp

**1. “`LIMIT 10` là 10 hàng vừa chèn.”** Không. Thiếu `ORDER BY` thì không bảo đảm.

**2. “Có primary key nên SELECT tự trả theo primary key.”** Không. PostgreSQL có thể chọn kế hoạch khác.

**3. “`ORDER BY created_at DESC` luôn đủ ổn định.”** Không nếu nhiều hàng cùng thời điểm; thêm cột unique.

**4. “`LIMIT/OFFSET` sẽ giữ thứ tự tie giống nhau giữa các trang.”** Không có bảo đảm nếu `ORDER BY` không phân định toàn bộ hàng.

**5. “Có `ORDER BY` duy nhất thì phân trang không bao giờ trùng khi có INSERT.”** Không. Offset có thể dịch khi tập dữ liệu thay đổi.

**6. “`OFFSET` nhảy miễn phí qua N bản ghi.”** Không. PostgreSQL vẫn phải xác định và bỏ qua các vị trí trước đó.

**7. “`FETCH NEXT 10` tự nhớ trang vừa tải.”** Không. Cần `OFFSET` hoặc cursor.

**8. “`FETCH FIRST 10 ROWS ONLY` và `WITH TIES` luôn trả cùng số hàng.”** Không. `WITH TIES` có thể trả thêm hàng đồng hạng.

**9. “Thêm ID unique vào ORDER BY vẫn giữ mọi hàng đồng điểm với WITH TIES.”** Không. ID phá sự đồng hạng theo toàn bộ list ORDER BY.

**10. “`ORDER BY DESC` tự để NULL cuối.”** Trong PostgreSQL mặc định DESC có `NULLS FIRST`; dùng `NULLS LAST` nếu muốn.

**11. “Một phép so sánh tuple `<` dùng được cho mọi sort mix ASC/DESC.”** Không. Với hướng hỗn hợp phải dựng điều kiện seek tương ứng.

**12. “Row comparison với NULL đi qua mọi hàng có NULL.”** Không. SQL có ba giá trị; phải thiết kế xử lý NULL.

**13. “`ROW_NUMBER() OVER (ORDER BY ...)` bảo đảm thứ tự output mà không cần ORDER BY ngoài.”** Không nên dựa vào đó cho kết quả cuối.

**14. “`GROUP BY` hoặc `DISTINCT` trả kết quả đã sắp xếp.”** Không có cam kết như vậy.

**15. “`COUNT(*) OVER()` luôn trả total dù OFFSET vượt tập.”** Không. Nếu không có hàng, cũng không có dòng mang tổng.

**16. “Chỉ mục nào cũng giúp ORDER BY + LIMIT.”** Không. Phải xét thứ tự cột, chiều sort, điều kiện lọc, selectivity và kế hoạch.

**17. “Keyset giải quyết mọi vấn đề concurrent writes.”** Không. Cập nhật sort key, lọc thay đổi hoặc đọc từ replica khác vẫn có thể làm tập kết quả khác.

**18. “Có thể ghép trực tiếp chuỗi sort từ request vào SQL.”** Nguy hiểm. Chỉ nhận các sort option từ whitelist.

**19. “`LIMIT 20` nghĩa là DB chỉ xử lý 20 hàng.”** Không. Nó có thể phải sort, lọc, join, aggregate hoặc bỏ qua nhiều hàng trước đó.

**20. “`ORDER BY` trong subquery luôn đủ cho thứ tự SELECT bên ngoài.”** Không. Hãy quy định thứ tự ở tầng trả kết quả.

**21. “Sort theo một cột không unique nhưng hiện tại chạy đúng là được.”** Chỉ đúng do tình cờ. Yêu cầu là SQL có bảo đảm, không phải demo chạy một lần.

**22. “Giữ transaction REPEATABLE READ mở nhiều phút là cách đơn giản để phân trang web.”** Có rủi ro giữ snapshot lâu, ảnh hưởng vacuum và tài nguyên; chỉ dùng trong quy trình có kiểm soát.

## 18. Bài tập thực hành có lời giải

### Bài 1 — LIMIT không có ORDER BY

Cho:

```sql
SELECT order_id
FROM page_lab.orders
LIMIT 3;
```

**Câu hỏi:** Có thể kết luận ba ID là `101,102,103` vì chúng được chèn đầu không?

**Đáp án:** Không. PostgreSQL không bảo đảm thứ tự SELECT thiếu `ORDER BY`. Muốn ba ID nhỏ nhất:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY order_id ASC
LIMIT 3;
```

Kết quả chắc chắn là `101,102,103` với bộ dữ liệu lab.

### Bài 2 — Phân trang theo số trang

**Yêu cầu:** lấy trang thứ ba, pageSize = 4, đơn mới trước và ID lớn trước khi trùng thời điểm.

**Đáp án:**

```sql
SELECT order_id, created_at
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 4 OFFSET 8;
```

Kết quả: `108,107,106,105`. Offset là `(3-1)*4=8`.

### Bài 3 — Viết bằng FETCH NEXT

**Yêu cầu:** chuyển `LIMIT 5 OFFSET 10` thành dạng FETCH.

**Đáp án:**

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
OFFSET 10 ROWS
FETCH NEXT 5 ROWS ONLY;
```

Kết quả: `106,105,104,102,101` trong bộ dữ liệu lab.

### Bài 4 — Tại sao chỉ created_at chưa ổn định?

**Câu hỏi:** Có hai đơn được tạo đúng một giây và cùng timestamp. `ORDER BY created_at DESC LIMIT 1` có bảo đảm chọn đơn có ID cao hơn không?

**Đáp án:** Không. Cần thêm tie-breaker:

```sql
ORDER BY created_at DESC, order_id DESC
LIMIT 1
```

Khi đó trong nhóm thời điểm bằng nhau, ID cao hơn đứng trước.

### Bài 5 — WITH TIES có thể trả bao nhiêu hàng?

Trong bảng lab, hai đơn có thời điểm 06/11 và ba đơn có thời điểm 05/11. Dự đoán:

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC
FETCH FIRST 3 ROWS WITH TIES;
```

**Đáp án:** **5 hàng** gồm các ID `116,115,114,113,112`, nhưng thứ tự trong từng nhóm cùng thời điểm không được cố định nếu không thêm sắp xếp ngoài. Hàng thứ ba thuộc nhóm 05/11 nên toàn bộ nhóm đó được giữ.

### Bài 6 — WITH TIES và khóa unique

```sql
SELECT order_id
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 3 ROWS WITH TIES;
```

**Đáp án:** Đúng **3 hàng**, vì cặp `(created_at,order_id)` là duy nhất; không còn hàng nào có cùng toàn bộ khóa sắp xếp với hàng cuối.

### Bài 7 — NULLS LAST

**Yêu cầu:** sắp thời điểm giảm dần, các hàng có thời điểm NULL xuống cuối, và trong nhóm NULL thì ID lớn trước.

**Đáp án:**

```sql
SELECT order_id, created_at
FROM some_orders
ORDER BY created_at DESC NULLS LAST, order_id DESC;
```

`some_orders` là tên minh họa cho bảng cho phép `created_at NULL`. Với bảng `page_lab.orders` đang dùng `created_at NOT NULL`, `NULLS LAST` là tường minh nhưng không làm thay đổi kết quả.

### Bài 8 — Tìm trang kế bằng keyset

Trang đầu có năm hàng, kết thúc ở `(created_at, order_id) = ('2026-11-05 11:00:00+00', 112)`. Hãy lấy năm hàng sau.

**Đáp án:**

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE (created_at, order_id)
      < (TIMESTAMPTZ '2026-11-05 11:00:00+00', 112)
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Kết quả `111,110,109,108,107`. Nếu chỉ lọc `created_at < ...` sẽ **bỏ qua** những đơn có cùng timestamp với cursor nhưng ID thấp hơn.

### Bài 9 — Keyset với ASC

**Câu hỏi:** `ORDER BY created_at ASC, order_id ASC` dùng điều kiện nào để tìm hàng sau cursor?

**Đáp án:** Với hai cột không NULL và kiểu có thể so sánh:

```sql
WHERE (created_at, order_id) > (:last_created_at, :last_order_id)
```

Trong truy vấn PostgreSQL trực tiếp, thay placeholder bằng tham số SQL thực tế hoặc giá trị có kiểu, không dùng nguyên cú pháp `:name` nếu client chưa hỗ trợ named parameter.

### Bài 10 — Keyset với hướng hỗn hợp

**Yêu cầu:** sắp `created_at DESC, order_id ASC`.

**Đáp án:** Sau cursor `(T,ID)`:

```sql
WHERE created_at < T
   OR (created_at = T AND order_id > ID)
```

Không dùng `(created_at, order_id) < (T, ID)` vì chiều của `order_id` trong ORDER BY là ASC.

### Bài 11 — INSERT mới ảnh hưởng OFFSET ra sao?

Client lấy trang 1 gồm `116..112`. Một đơn `117` mới được chèn ở đầu trước khi client gọi `LIMIT 5 OFFSET 5`.

**Đáp án:** ID `112` có thể xuất hiện lại ở trang 2, vì các vị trí bị đẩy xuống một hàng. Thêm tie-breaker giải quyết thứ tự giữa các hàng đồng timestamp, **không** đóng băng tập dữ liệu giữa các request. Keyset với cursor là lựa chọn thường phù hợp hơn cho infinite scroll.

### Bài 12 — Đếm tổng số hàng sau lọc

**Yêu cầu:** danh sách chỉ gồm đơn `paid`, trả năm đơn mới nhất và số lượng đơn paid tổng cộng.

**Đáp án:**

```sql
SELECT COUNT(*) AS total_paid
FROM page_lab.orders
WHERE status = 'paid';

SELECT order_id, created_at, amount
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
```

Chú ý hai truy vấn ở `READ COMMITTED` có thể nhìn dữ liệu khác nhau nếu giao dịch khác commit ở giữa. Khi yêu cầu số liệu chính xác cùng thời điểm, thiết kế isolation/snapshot phù hợp.

### Bài 13 — COUNT(*) OVER() có luôn trả total không?

```sql
SELECT order_id, COUNT(*) OVER () AS total_rows
FROM page_lab.orders
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 1000;
```

**Đáp án:** Không. Vì offset vượt quá tập hàng lab, kết quả **không có dòng nào**, nên client cũng không nhận được trường `total_rows`.

### Bài 14 — Xác định index phục vụ lọc và sắp xếp

Một endpoint chạy thường xuyên:

```sql
SELECT order_id, created_at
FROM page_lab.orders
WHERE status = 'paid'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

**Đáp án gợi ý:** Có thể xem xét:

```sql
CREATE INDEX orders_paid_paging_candidate
ON page_lab.orders (status, created_at DESC, order_id DESC);
```

Sau đó đo `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện và đánh giá cả chi phí ghi/index. Index không phải đáp án bắt buộc trong mọi bảng.

### Bài 15 — Dọn bài lab an toàn

Khi chắc chắn schema là của riêng bài học:

```sql
-- Chỉ thực hiện nếu không có dữ liệu khác sử dụng schema này.
-- DROP SCHEMA page_lab CASCADE;
```

`DROP SCHEMA ... CASCADE` có thể xóa toàn bộ bảng và đối tượng phụ thuộc trong schema; không chạy trong database dùng chung nếu chưa kiểm tra phạm vi.

## 19. Quy trình thực tế khi xây phân trang PostgreSQL

Trước khi chọn cú pháp, nên trả lời theo thứ tự:

1. **Tập hàng cần lấy là gì?** Xác định `FROM`, `JOIN`, `WHERE` và các điều kiện quyền/tenant.
2. **Người dùng muốn sort theo ý nghĩa nào?** Mới nhất, giá trị cao nhất, tên A–Z hay trạng thái?
3. **Sort key có trùng không?** Nếu có, thêm cột/tổ hợp phân định duy nhất, thường là primary key.
4. **Có NULL trong sort key không?** Chọn `NULLS FIRST/LAST` và tránh điều kiện cursor không xử lý NULL.
5. **API dùng số trang hay cuộn tiếp?** Với trang nhỏ/nhảy trang, `LIMIT/OFFSET` đơn giản; với feed lớn, cân nhắc keyset.
6. **Có cần lấy thêm hàng đồng hạng không?** Nếu có, `FETCH ... WITH TIES` theo **khóa xếp hạng**, không trộn với kỳ vọng pageSize cứng.
7. **Có thay đổi dữ liệu giữa request không?** Xác định chấp nhận dữ liệu “sống” hay cần snapshot/report nhất quán.
8. **Có cần tổng số hàng không?** Đánh giá chi phí `COUNT(*)`, sự nhất quán snapshot và cách hiển thị khi không còn trang.
9. **Index có phù hợp sort/filter không?** Xem thứ tự cột, chiều ASC/DESC, selectivity và kế hoạch thực thi.
10. **Đã giới hạn input API chưa?** Kiểm tra page/pageSize, dùng bind parameters, whitelist sort và bảo vệ cursor.
11. **Đã thử ranh giới chưa?** Các hàng đồng thời điểm, trang cuối ngắn, trang rỗng, insert/delete/update đồng thời, NULL và các bộ lọc khác nhau.
12. **Có replica hoặc partitioning không?** Xác định độ trễ đọc, tính nhất quán và kế hoạch truy vấn trong topology thực tế.

## 20. Tổng kết

Trong PostgreSQL:

- **`LIMIT N`** trả tối đa N hàng; **`OFFSET M`** bỏ qua M hàng đầu.
- **`FETCH FIRST/NEXT N ROWS ONLY`** diễn đạt giới hạn theo cú pháp chuẩn SQL và có thể dùng cùng `OFFSET ... ROWS`.
- **`FETCH ... WITH TIES`** lấy thêm những hàng có **toàn bộ khóa ORDER BY bằng khóa của hàng ranh giới**; số hàng có thể vượt N.
- **Không có `ORDER BY`, thứ tự kết quả không được bảo đảm.** Sắp xếp theo cột có giá trị trùng cũng chưa đủ cho các trang ổn định.
- **Thêm một khóa phân định duy nhất** như `order_id` vào cuối `ORDER BY` để có thứ tự xác định trên cùng tập dữ liệu.
- **`LIMIT/OFFSET` dễ dùng nhưng có thể tốn công ở trang sâu và bị dịch vị trí khi dữ liệu thay đổi.** Keyset pagination dùng khóa cuối trang trước thường phù hợp hơn cho danh sách cuộn dài.
- **MVCC, snapshot, index và thiết kế API** quyết định tính nhất quán và hiệu năng thực tế; không một cú pháp phân trang riêng lẻ nào giải quyết mọi trường hợp.

**Nguyên tắc cuối cùng:** trước khi hỏi “lấy bao nhiêu hàng” hoặc “bỏ qua bao nhiêu hàng”, hãy xác định **“thứ tự nào là đúng, có duy nhất không, và tập dữ liệu có thể thay đổi giữa các lần đọc không?”**. Khi trả lời được ba câu hỏi đó, bạn mới có thể chọn `LIMIT`, `OFFSET`, `FETCH` hoặc keyset một cách có căn cứ.

### Tài liệu tham khảo PostgreSQL

- [SELECT: ORDER BY, LIMIT, OFFSET và FETCH](https://www.postgresql.org/docs/current/sql-select.html).
- [Sorting Rows](https://www.postgresql.org/docs/current/queries-order.html).
- [LIMIT và OFFSET](https://www.postgresql.org/docs/current/queries-limit.html).
- [B-tree Indexes và ORDER BY](https://www.postgresql.org/docs/current/indexes-ordering.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
