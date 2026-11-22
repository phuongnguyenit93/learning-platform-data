# Sinh dãy số hoặc lịch ngày khi phù hợp bằng truy vấn đệ quy SQL

Không phải lúc nào dữ liệu cần truy vấn cũng đã có sẵn thành từng dòng trong bảng. Một báo cáo có thể cần **mọi ngày trong tháng**, kể cả những ngày không phát sinh giao dịch; một phép thử cần **dãy số từ 1 đến N**; hoặc một phép tính cần tạo các mốc **mỗi 7 ngày** để chia kỳ.

SQL có thể tạo những tập như vậy ngay trong truy vấn. Một kỹ thuật quan trọng là **CTE đệ quy (`WITH RECURSIVE`)**: bắt đầu từ một giá trị, sinh giá trị tiếp theo theo quy tắc, và lặp cho đến khi đạt điều kiện dừng. Khi sử dụng đúng, nó giúp tạo **dãy số, dãy ngày, mốc thời gian** và kết hợp với dữ liệu thực để tìm ngày thiếu, điền số 0 hoặc phân tích cửa sổ liên tục.

Tuy nhiên, **không phải lúc nào cũng nên dùng đệ quy**. PostgreSQL có `generate_series`, một số hệ quản trị có hàm sinh dãy riêng, còn những lịch nghiệp vụ dùng nhiều lần thường phù hợp với **bảng lịch (calendar/date dimension)**. Bài học sẽ giải thích **cách làm** lẫn **khi nào cách đó phù hợp**.

Các ví dụ chạy chính trên **PostgreSQL**. Các phần đối chiếu chỉ rõ khác biệt của SQL Server, MySQL, SQLite và Oracle Database.

## 1. Tại sao phải sinh dãy thay vì đọc dữ liệu có sẵn?

Giả sử có bảng đơn hàng:

| Ngày | Số đơn đã thanh toán |
|---|---:|
| 10/11/2026 | 3 |
| 13/11/2026 | 1 |
| 14/11/2026 | 1 |
| 16/11/2026 | 1 |

Nếu dùng `GROUP BY ordered_on` trên đơn hàng, những ngày **11/11, 12/11, 15/11** không có đơn đã thanh toán sẽ **không xuất hiện**.

Nhưng báo cáo “số đơn theo **từng ngày từ 10 đến 16/11**” thường cần:

| Ngày | Số đơn |
|---|---:|
| 10/11 | 3 |
| 11/11 | **0** |
| 12/11 | **0** |
| 13/11 | 1 |
| 14/11 | 1 |
| 15/11 | **0** |
| 16/11 | 1 |

Muốn báo cáo đủ bảy ngày, cần **một tập ngày độc lập với dữ liệu đơn hàng**. Sau đó dùng `LEFT JOIN` với số liệu đã tổng hợp; ngày nào không có dòng khớp sẽ được hiển thị bằng `0` theo quy tắc báo cáo.

Tương tự, muốn tạo dãy số `1, 2, 3, ..., 10` mà không cần bảng số, bạn có thể dùng một truy vấn đệ quy.

### 1.1. Khi nào việc sinh dãy có ích?

- Lập **lịch ngày đầy đủ**, kể cả ngày chưa có dữ liệu.
- Tìm **khoảng trống** trong hoạt động theo ngày.
- Phân tích **cửa sổ ba, bảy hoặc ba mươi ngày lịch liên tiếp**.
- Tạo các **mốc tuần/tháng** cho báo cáo.
- Sinh số thứ tự hoặc những bước mô phỏng nhỏ, có điểm dừng.
- Tạo bộ dữ liệu thử nghiệm hữu hạn mà không phải nhập từng dòng.

**Không** nên tự sinh hàng triệu ngày hoặc số chỉ vì SQL cho phép. Hãy cân nhắc một hàm sinh dãy chuyên dụng hoặc bảng số/bảng lịch đã lập chỉ mục khi phạm vi lớn hoặc được dùng thường xuyên.

## 2. Cấu trúc của một recursive CTE

Mẫu thường gặp trong PostgreSQL:

```sql
WITH RECURSIVE sequence(n) AS (
    -- Anchor member: giá trị khởi đầu.
    SELECT 1

    UNION ALL

    -- Recursive member: sinh bước tiếp theo.
    SELECT n + 1
    FROM sequence
    WHERE n < 10
)
SELECT n
FROM sequence
ORDER BY n;
```

Kết quả:

```text
n
--
1
2
3
4
5
6
7
8
9
10
```

Có ba thành phần cốt lõi:

1. **Anchor member (phần neo):** `SELECT 1` tạo dòng đầu tiên, không tham chiếu chính CTE.
2. **Recursive member (phần đệ quy):** `SELECT n + 1 FROM sequence ...` dựa vào dòng được sinh ở bước trước để tạo dòng tiếp.
3. **Điều kiện dừng:** `WHERE n < 10` ngăn sinh thêm sau khi đã tạo giá trị 10.

`UNION ALL` ghép kết quả neo với các kết quả sinh ở những vòng lặp tiếp theo. Trong PostgreSQL, truy vấn đệ quy được xử lý bằng cơ chế lặp với một tập làm việc; SQL được trình bày theo cú pháp đệ quy nhưng không nhất thiết dùng ngăn xếp gọi hàm giống đệ quy trong Java.

### 2.1. Từng bước sinh dữ liệu

| Vòng | Giá trị hiện tại `n` | Điều kiện `n < 10` | Giá trị mới |
|---:|---:|---|---:|
| Neo | Chưa có | Không áp dụng | **1** |
| 1 | 1 | TRUE | 2 |
| 2 | 2 | TRUE | 3 |
| … | … | … | … |
| 8 | 8 | TRUE | 9 |
| 9 | 9 | TRUE | 10 |
| 10 | 10 | FALSE | Không sinh thêm |

Điều kiện được kiểm tra trên **giá trị đầu vào của nhánh đệ quy**, nên câu `WHERE n < 10` vẫn cho phép nhánh sinh ra `10`.

Nếu bạn đổi thành `WHERE n <= 10`, dãy sẽ sinh thêm **11**. Đây là lỗi **off-by-one** (lệch một) phổ biến.

### 2.2. Vì sao thường dùng UNION ALL?

`UNION ALL` **không loại trùng**; nó giữ tất cả dòng do từng bước sinh ra. Với một dãy tăng một chiều và điểm dừng rõ ràng, mỗi giá trị xuất hiện đúng một lần nên nó phù hợp.

`UNION` (không có `ALL`) loại các dòng trùng theo toàn bộ các cột đầu ra. Việc này có thể hữu ích trong một số truy vấn đi qua đồ thị, nhưng:

- Có chi phí loại trùng.
- Không thay thế điều kiện dừng đúng.
- Nếu bạn thêm cột `step_no` liên tục tăng, mỗi dòng khác nhau dù giá trị nghiệp vụ lặp lại; `UNION` vẫn có thể chạy không dừng.

**Để sinh dãy số/ngày, hãy thiết kế bước thay đổi tiến về giới hạn và có điều kiện dừng minh bạch.** Không dựa vào `UNION` để “tự cứu” một truy vấn đệ quy sai.

## 3. Sinh dãy số với giới hạn trên

### 3.1. Sinh số từ 0 đến 6

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 0
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 6
)
SELECT n
FROM numbers
ORDER BY n;
```

Kết quả là `0, 1, 2, 3, 4, 5, 6` — **7 số**.

Hai cách biểu diễn ranh giới rất hay gặp:

| Mục tiêu | Anchor | Điều kiện trên giá trị hiện tại |
|---|---:|---|
| `[0, 6]` (gồm cả 6) | 0 | `n < 6` |
| `[0, 7)` (bỏ 7) | 0 | `n + 1 < 7` |

Cách thứ hai biểu đạt trực tiếp **ranh giới trên không bao gồm**:

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 0
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n + 1 < 7
)
SELECT n
FROM numbers
ORDER BY n;
```

Kết quả vẫn là `0` tới `6`.

### 3.2. Sinh từ giá trị khác 1

Muốn sinh các số nguyên từ 5 đến 12:

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 5
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 12
)
SELECT n
FROM numbers
ORDER BY n;
```

Kết quả: `5, 6, 7, 8, 9, 10, 11, 12`.

Không cần thay logic bên trong theo toàn bộ giá trị; chỉ cần chọn **điểm bắt đầu** và **điểm dừng** đúng.

### 3.3. Tạo dãy với bước nhảy lớn hơn 1

Muốn `2, 5, 8, 11, 14, 17`, mỗi lần tăng 3:

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 2
    UNION ALL
    SELECT n + 3
    FROM numbers
    WHERE n + 3 <= 17
)
SELECT n
FROM numbers
ORDER BY n;
```

Ở đây điều kiện `n + 3 <= 17` kiểm tra **giá trị sắp sinh** không vượt mốc cuối. Kết quả dừng ở 17.

Nếu dùng `WHERE n < 17`:

```sql
-- Không đúng nếu muốn chặn không vượt 17:
SELECT n + 3
FROM numbers
WHERE n < 17;
```

nhánh cuối với `n = 17` không chạy, nhưng nhánh với `n = 14` sinh 17 là hợp lệ. Ở ví dụ này nó tình cờ cũng dừng đúng vì 17 nằm trên lưới bước nhảy. Với giới hạn như 16, điều kiện `n < 16` cho phép `14 + 3 = 17` **vượt giới hạn**. Kiểm tra giá trị mới thường giúp tránh lỗi.

### 3.4. Dãy giảm dần

```sql
WITH RECURSIVE countdown(n) AS (
    SELECT 10
    UNION ALL
    SELECT n - 2
    FROM countdown
    WHERE n - 2 >= 0
)
SELECT n
FROM countdown
ORDER BY n DESC;
```

Kết quả: `10, 8, 6, 4, 2, 0`.

Quy tắc tổng quát:

- Dãy tăng: **bước dương** và kiểm tra **mốc trên**.
- Dãy giảm: **bước âm** và kiểm tra **mốc dưới**.
- Bước bằng 0 hoặc bước đi sai hướng có nguy cơ **không bao giờ tới điều kiện dừng**.

### 3.5. Tránh sinh neo khi khoảng yêu cầu rỗng

Một vấn đề của mẫu `SELECT start UNION ALL ...` là **anchor luôn sinh một dòng**, ngay cả khi `start > end`.

Ví dụ nếu yêu cầu dãy từ 10 đến trước 5, tập kết quả đúng phải **rỗng**, không phải chứa 10.

Dùng CTE tham số và kiểm tra khoảng ngay ở anchor:

```sql
WITH RECURSIVE
params AS (
    SELECT
        10::INTEGER AS start_n,
        5::INTEGER AS end_exclusive
),
numbers(n) AS (
    SELECT p.start_n
    FROM params AS p
    WHERE p.start_n < p.end_exclusive

    UNION ALL

    SELECT n.n + 1
    FROM numbers AS n
    CROSS JOIN params AS p
    WHERE n.n + 1 < p.end_exclusive
)
SELECT n
FROM numbers
ORDER BY n;
```

Kết quả: **0 dòng**.

Đổi `start_n = 4` và `end_exclusive = 9` trong `params` sẽ cho `4, 5, 6, 7, 8`.

Việc kiểm tra khoảng rỗng ở anchor đặc biệt quan trọng khi đầu vào đến từ **tham số ứng dụng**. Đừng để một khoảng người dùng nhập không hợp lệ bị chuyển thành một dòng ngoài phạm vi.

## 4. Điều kiện dừng: rủi ro cần hiểu trước khi áp dụng

Truy vấn đệ quy **có thể chạy rất lâu hoặc không dừng** nếu không tiến về giới hạn.

### 4.1. Ví dụ truy vấn không có điểm dừng

```sql
-- CẢNH BÁO: không chạy; đây là ví dụ về đệ quy vô hạn.
WITH RECURSIVE numbers(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM numbers
)
SELECT COUNT(*)
FROM numbers;
```

Nhánh đệ quy không có `WHERE` giới hạn. Truy vấn tổng hợp `COUNT(*)` cần đọc toàn bộ nguồn, nhưng nguồn **không có kết thúc**.

Có những DBMS đặt giới hạn số vòng đệ quy; DBMS khác có thể dùng tài nguyên đến khi bị hủy hoặc chạm giới hạn tài nguyên. **Không dùng một giới hạn thực thi mặc định làm thay cho logic dừng.**

### 4.2. Chặn bởi số bước khi giới hạn động

Giả sử công cụ được phép sinh tối đa **366 ngày** trong một lần:

```sql
WITH RECURSIVE days(day_value, step_no) AS (
    SELECT DATE '2026-11-10', 1

    UNION ALL

    SELECT day_value + 1, step_no + 1
    FROM days
    WHERE day_value < DATE '2026-12-31'
      AND step_no < 366
)
SELECT day_value, step_no
FROM days
ORDER BY day_value;
```

Ở đây có hai ràng buộc:

- **Giới hạn nghiệp vụ:** `day_value < DATE '2026-12-31'`.
- **Giới hạn phòng vệ:** `step_no < 366` để tránh tạo quá nhiều dòng trong trường hợp biên ngày thay đổi.

Cần hiểu rằng giới hạn bước **có thể cắt ngắn kết quả một cách âm thầm** nếu khoảng yêu cầu dài hơn số bước cho phép. Với một API sản xuất, cách tốt hơn là **kiểm tra độ dài khoảng và trả lỗi rõ ràng** khi vượt hạn mức, thay vì trả một lịch thiếu ngày mà người dùng không biết.

### 4.3. LIMIT ở ngoài không phải cơ chế phòng vệ tổng quát

Có thể thấy ví dụ:

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM numbers
)
SELECT n FROM numbers LIMIT 10;
```

Trong một số trường hợp PostgreSQL chỉ cần lấy một số dòng đầu nên truy vấn trên **có thể** kết thúc sau khi đã nhận đủ dòng. Nhưng điều đó **không an toàn để dựa vào**, vì `ORDER BY`, `JOIN`, `COUNT` hoặc các phép xử lý khác ở ngoài có thể buộc engine đánh giá thêm rất nhiều dòng, và DBMS khác xử lý khác.

**Hãy đặt điều kiện dừng trong recursive member**, đồng thời kiểm soát giới hạn đầu vào.

### 4.4. Kiểu dữ liệu cũng cần đủ phạm vi

Nếu tăng một `INTEGER` mãi, phép `n + 1` có thể tràn kiểu. Với phạm vi lớn, chọn `BIGINT` hoặc kiểu phù hợp ở anchor và ở nhánh đệ quy. Nhưng đổi sang `BIGINT` không giải quyết được truy vấn đệ quy thiếu điểm dừng.

## 5. Sinh lịch ngày bằng WITH RECURSIVE

Kiểu `DATE` trong PostgreSQL biểu diễn một **ngày trên lịch**, không chứa giờ hay múi giờ. Ta có thể tăng một ngày bằng `day_value + 1`.

### 5.1. Tạo lịch từ 10 đến hết 16/11/2026

```sql
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'

    UNION ALL

    SELECT day_value + 1
    FROM calendar
    WHERE day_value < DATE '2026-11-16'
)
SELECT day_value
FROM calendar
ORDER BY day_value;
```

Kết quả:

```text
2026-11-10
2026-11-11
2026-11-12
2026-11-13
2026-11-14
2026-11-15
2026-11-16
```

**Vì sao là 7 dòng?** Anchor sinh ngày 10/11; nhánh đệ quy lần lượt sinh 11, 12, 13, 14, 15, 16. Khi giá trị hiện tại là 16/11, điều kiện `day_value < DATE '2026-11-16'` sai nên dừng.

### 5.2. Khoảng nửa mở [start, end)

Trong báo cáo thực tế, quy tắc **lấy đầu kỳ, bỏ đầu kỳ kế tiếp** thường dễ áp dụng hơn. Ví dụ toàn bộ ngày từ 10/11 đến trước 17/11:

```sql
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'

    UNION ALL

    SELECT day_value + 1
    FROM calendar
    WHERE day_value + 1 < DATE '2026-11-17'
)
SELECT day_value
FROM calendar
ORDER BY day_value;
```

Kết quả giống phần trước: ngày 10–16/11.

Tuy nhiên, nếu `start >= end`, anchor trên vẫn sinh ngày bắt đầu. Muốn truy vấn hoàn chỉnh xử lý được **khoảng rỗng**, hãy kiểm tra cả anchor.

### 5.3. Tạo lịch có tham số, bảo toàn quy tắc khoảng rỗng

```sql
WITH RECURSIVE
bounds AS (
    SELECT
        DATE '2026-11-10' AS start_day,
        DATE '2026-11-17' AS end_exclusive
),
calendar(day_value) AS (
    SELECT b.start_day
    FROM bounds AS b
    WHERE b.start_day < b.end_exclusive

    UNION ALL

    SELECT c.day_value + 1
    FROM calendar AS c
    CROSS JOIN bounds AS b
    WHERE c.day_value + 1 < b.end_exclusive
)
SELECT day_value
FROM calendar
ORDER BY day_value;
```

Bảng `bounds` ở đây **cũng là CTE**, dùng để đặt tên hai ranh giới. Hai nhánh của CTE đệ quy cùng tham chiếu nó.

Đổi `start_day = DATE '2026-11-17'`, `end_exclusive = DATE '2026-11-17'` thì:

- Anchor không sinh dòng vì `start_day < end_exclusive` là FALSE.
- Không có dòng để nhánh đệ quy tạo bước tiếp.
- Kết quả là **tập rỗng**, đúng nghĩa `[start, end)`.

Trong ứng dụng, có thể thay literal ngày bằng **tham số có kiểu `DATE`** do driver truyền vào. Không ghép chuỗi đầu vào của người dùng trực tiếp thành câu SQL.

## 6. Sinh toàn bộ ngày trong tháng, kể cả tháng nhuận

Khi muốn tạo lịch của một tháng, không nên viết cố định “tháng luôn có 30 ngày”. Dùng **đầu tháng hiện tại** và **đầu tháng tiếp theo**.

Ví dụ tháng 2 năm nhuận **2024**:

```sql
WITH RECURSIVE
bounds AS (
    SELECT
        DATE '2024-02-01' AS month_start,
        DATE '2024-03-01' AS next_month_start
),
calendar(day_value) AS (
    SELECT month_start
    FROM bounds
    WHERE month_start < next_month_start

    UNION ALL

    SELECT c.day_value + 1
    FROM calendar AS c
    CROSS JOIN bounds AS b
    WHERE c.day_value + 1 < b.next_month_start
)
SELECT
    day_value,
    EXTRACT(ISODOW FROM day_value)::INTEGER AS iso_weekday
FROM calendar
ORDER BY day_value;
```

Kết quả có **29 ngày**, bao gồm **2024-02-29**.

- `EXTRACT(ISODOW FROM day_value)` trong PostgreSQL trả **1 = thứ Hai** đến **7 = Chủ nhật**.
- Toán tử ép kiểu `::INTEGER` là cú pháp PostgreSQL; có thể dùng `CAST(... AS INTEGER)` nếu muốn cách viết SQL phổ thông hơn.

Nếu thay mốc thành `2025-02-01` và `2025-03-01`, lịch có **28 ngày**, vì 2025 không nhuận.

### 6.1. Chỉ lấy ngày làm việc thứ Hai đến thứ Sáu

```sql
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1
    FROM calendar
    WHERE day_value < DATE '2026-11-16'
)
SELECT
    day_value
FROM calendar
WHERE EXTRACT(ISODOW FROM day_value) BETWEEN 1 AND 5
ORDER BY day_value;
```

Trong khoảng 10–16/11/2026, câu trên trả các ngày **10, 11, 12, 13, 16**; loại **thứ Bảy 14/11** và **Chủ nhật 15/11**.

**Không nên hiểu “thứ Hai đến thứ Sáu” luôn đồng nghĩa “ngày làm việc thực tế”**: ngày lễ, ngày nghỉ bù, lịch làm việc theo cửa hàng hoặc ca kíp cần một **bảng lịch nghiệp vụ** có thuộc tính riêng. Recursive CTE tạo được dãy ngày, nhưng không tự biết ngày lễ của doanh nghiệp.

### 6.2. Sinh các mốc tuần thay vì từng ngày

Ví dụ các ngày bắt đầu mỗi kỳ 7 ngày:

```sql
WITH RECURSIVE week_starts(day_value) AS (
    SELECT DATE '2026-11-02'

    UNION ALL

    SELECT day_value + 7
    FROM week_starts
    WHERE day_value + 7 < DATE '2026-12-01'
)
SELECT day_value AS week_start
FROM week_starts
ORDER BY day_value;
```

Kết quả: `2026-11-02`, `2026-11-09`, `2026-11-16`, `2026-11-23`, `2026-11-30`.

Nếu bài toán yêu cầu **tuần ISO** thì cần định nghĩa đúng thứ Hai đầu tuần và cách tuần đi qua ranh giới tháng/năm. Sinh các mốc cách nhau 7 ngày chỉ tạo **chu kỳ bảy ngày từ điểm bắt đầu**, không tự đảm bảo trùng với lịch tuần của mọi nghiệp vụ.

## 7. Dữ liệu thực hành: đơn hàng theo ngày

Ta tạo bảng có ngày đặt hàng, cửa hàng, trạng thái và giá trị đơn. Bộ dữ liệu được thiết kế để có **những ngày không có đơn PAID**, dù có thể có đơn trạng thái khác.

Chỉ chạy các lệnh tạo bảng và nhập dữ liệu **một lần trong database thực hành**.

```sql
CREATE TABLE lesson227_orders (
    order_id INTEGER PRIMARY KEY,
    store_id INTEGER NOT NULL,
    ordered_on DATE NOT NULL,
    order_status VARCHAR(20) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0)
);

INSERT INTO lesson227_orders (
    order_id,
    store_id,
    ordered_on,
    order_status,
    amount
)
VALUES
    (1, 1, DATE '2026-11-10', 'PAID',     100000.00),
    (2, 1, DATE '2026-11-10', 'PAID',      50000.00),
    (3, 1, DATE '2026-11-12', 'PENDING',   70000.00),
    (4, 1, DATE '2026-11-13', 'PAID',      40000.00),
    (5, 2, DATE '2026-11-10', 'PAID',      80000.00),
    (6, 2, DATE '2026-11-14', 'PAID',     120000.00),
    (7, 2, DATE '2026-11-14', 'REFUNDED',  30000.00),
    (8, 2, DATE '2026-11-16', 'PAID',      90000.00),
    (9, 1, DATE '2026-11-17', 'PAID',      60000.00);
```

Trong giai đoạn **từ 10 đến hết 16/11/2026**, dữ liệu thỏa `order_status = 'PAID'` có các đơn **1, 2, 4, 5, 6, 8**:

| Ngày | Đơn PAID | Số đơn | Doanh thu |
|---|---|---:|---:|
| 10/11 | 1, 2, 5 | 3 | 230.000 |
| 11/11 | Không có | 0 | 0 |
| 12/11 | Không có (đơn 3 là PENDING) | 0 | 0 |
| 13/11 | 4 | 1 | 40.000 |
| 14/11 | 6 (đơn 7 là REFUNDED) | 1 | 120.000 |
| 15/11 | Không có | 0 | 0 |
| 16/11 | 8 | 1 | 90.000 |

Tổng cộng **6 đơn PAID, 480.000** trong giai đoạn này. Đơn 9 ngày 17/11 nằm **ngoài kỳ** nên không được tính.

## 8. Vì sao chỉ GROUP BY không tạo ngày thiếu?

Nếu truy vấn trực tiếp trên bảng:

```sql
SELECT
    ordered_on,
    COUNT(*) AS paid_order_count,
    SUM(amount) AS paid_amount
FROM lesson227_orders
WHERE order_status = 'PAID'
  AND ordered_on >= DATE '2026-11-10'
  AND ordered_on <  DATE '2026-11-17'
GROUP BY ordered_on
ORDER BY ordered_on;
```

Kết quả chỉ có **4 dòng**, cho các ngày 10, 13, 14, 16/11. SQL không tự tạo nhóm cho những ngày **không có bản ghi PAID**.

Để tạo nhóm cho ngày 11, 12, 15/11, ta cần **sinh bộ lịch ngày**, rồi nối với tập tổng hợp.

### 8.1. Tạo CTE ngày và CTE tổng hợp đơn

```sql
WITH RECURSIVE
calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1
    FROM calendar
    WHERE day_value < DATE '2026-11-16'
),
paid_daily AS (
    SELECT
        ordered_on,
        COUNT(*) AS paid_order_count,
        SUM(amount) AS paid_amount
    FROM lesson227_orders
    WHERE order_status = 'PAID'
      AND ordered_on >= DATE '2026-11-10'
      AND ordered_on <  DATE '2026-11-17'
    GROUP BY ordered_on
)
SELECT
    c.day_value,
    COALESCE(p.paid_order_count, 0) AS paid_order_count,
    COALESCE(p.paid_amount, 0) AS paid_amount
FROM calendar AS c
LEFT JOIN paid_daily AS p
    ON p.ordered_on = c.day_value
ORDER BY c.day_value;
```

Kết quả:

| day_value | paid_order_count | paid_amount |
|---|---:|---:|
| 2026-11-10 | 3 | 230000 |
| 2026-11-11 | 0 | 0 |
| 2026-11-12 | 0 | 0 |
| 2026-11-13 | 1 | 40000 |
| 2026-11-14 | 1 | 120000 |
| 2026-11-15 | 0 | 0 |
| 2026-11-16 | 1 | 90000 |

### 8.2. Hai CTE có vai trò khác nhau

- `calendar`: bảo đảm **một dòng cho mỗi ngày** trong kỳ, độc lập với đơn hàng.
- `paid_daily`: tổng hợp **chỉ các đơn PAID**, tối đa một dòng cho mỗi ngày có đơn.
- `LEFT JOIN`: giữ **mọi ngày** từ `calendar`, kể cả khi `paid_daily` không có dòng cùng ngày.
- `COALESCE`: biến giá trị thiếu sau `LEFT JOIN` thành số 0 theo quy tắc hiển thị.

`calendar` là tập **khóa ngày đầy đủ**; `paid_daily` là tập **số liệu thực tế có thể thưa**.

### 8.3. Vì sao điều kiện lọc phải được đặt đúng chỗ?

Nếu viết:

```sql
-- Sai nếu muốn giữ đủ mọi ngày trong lịch.
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1 FROM calendar
    WHERE day_value < DATE '2026-11-16'
)
SELECT
    c.day_value,
    COUNT(o.order_id)
FROM calendar AS c
LEFT JOIN lesson227_orders AS o
    ON o.ordered_on = c.day_value
WHERE o.order_status = 'PAID'
GROUP BY c.day_value;
```

`WHERE o.order_status = 'PAID'` loại các dòng do `LEFT JOIN` bổ sung `NULL` cho ngày không có đơn. Ngày 12 có đơn nhưng chỉ `PENDING` cũng bị loại. Kết quả không còn lịch đầy đủ.

Một phương án trực tiếp đúng là đặt trạng thái vào `ON`:

```sql
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1 FROM calendar
    WHERE day_value < DATE '2026-11-16'
)
SELECT
    c.day_value,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.amount), 0) AS paid_amount
FROM calendar AS c
LEFT JOIN lesson227_orders AS o
    ON o.ordered_on = c.day_value
   AND o.order_status = 'PAID'
GROUP BY c.day_value
ORDER BY c.day_value;
```

Trong dữ liệu mẫu, kết quả trùng với `calendar LEFT JOIN paid_daily`. Khi báo cáo cần nhiều chỉ số hoặc join thêm quan hệ một–nhiều, **tiền tổng hợp mỗi nguồn** thường giúp kiểm soát việc đếm lặp tốt hơn.

## 9. Lưu ý COUNT(*) sau LEFT JOIN

Một câu sai phổ biến:

```sql
SELECT
    c.day_value,
    COUNT(*) AS rows_after_join
FROM calendar AS c
LEFT JOIN paid_daily AS p
    ON p.ordered_on = c.day_value
GROUP BY c.day_value;
```

Ở đây `calendar` và `paid_daily` là các CTE của ví dụ trước; đoạn trích trên chỉ minh họa cách đếm.

Ngày không có `paid_daily` vẫn được `LEFT JOIN` giữ lại dưới dạng **một dòng với các cột bên phải `NULL`**, nên `COUNT(*)` bằng **1**, không phải 0.

Nếu nối trực tiếp với bảng `orders` và muốn đếm đơn, dùng:

```sql
COUNT(o.order_id)
```

vì `COUNT(column)` bỏ qua giá trị `NULL` ở phía đơn hàng. Nếu đã có `paid_daily` là một dòng mỗi ngày, có thể dùng:

```sql
COALESCE(p.paid_order_count, 0)
```

mà không cần đếm lại các dòng đã tổng hợp.

**Việc sinh lịch giải quyết bài toán thiếu ngày; việc chọn phép đếm đúng vẫn là một quyết định độc lập.**

## 10. Tìm những ngày không có đơn PAID

Đôi khi không cần hiển thị toàn bộ lịch, chỉ cần trả về **các ngày trống** trong khoảng.

Dùng lịch đệ quy và `NOT EXISTS`:

```sql
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1
    FROM calendar
    WHERE day_value < DATE '2026-11-16'
)
SELECT c.day_value
FROM calendar AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson227_orders AS o
    WHERE o.ordered_on = c.day_value
      AND o.order_status = 'PAID'
)
ORDER BY c.day_value;
```

Kết quả:

```text
2026-11-11
2026-11-12
2026-11-15
```

`NOT EXISTS` hỏi trực tiếp: “**Không có bất kỳ đơn PAID nào thuộc ngày này?**”

Ngày 12 vẫn được coi là trống theo định nghĩa **đơn PAID**, mặc dù có đơn `PENDING`. Nếu yêu cầu là “ngày không có bất kỳ đơn nào”, bỏ `AND o.order_status = 'PAID'` trong truy vấn con; khi đó ngày 12 sẽ **không** thuộc kết quả trống.

### 10.1. Cách khác với LEFT JOIN

```sql
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1 FROM calendar
    WHERE day_value < DATE '2026-11-16'
)
SELECT c.day_value
FROM calendar AS c
LEFT JOIN lesson227_orders AS o
    ON o.ordered_on = c.day_value
   AND o.order_status = 'PAID'
WHERE o.order_id IS NULL
ORDER BY c.day_value;
```

Kết quả cũng là các ngày **11, 12, 15/11**.

Điều kiện `o.order_status = 'PAID'` phải ở `ON` để xác định **bản ghi PAID được tính là khớp**. `WHERE o.order_id IS NULL` sau đó chỉ lấy các ngày **không có đơn PAID phù hợp**.

`o.order_id` là khóa chính không `NULL`, nên dấu `IS NULL` phản ánh trường hợp **không có dòng bên phải khớp**.

## 11. Tạo lịch theo từng cửa hàng: CROSS JOIN có chủ đích

Yêu cầu thực tế có thể là: “Với **mỗi cửa hàng**, hiển thị doanh thu PAID cho **mỗi ngày** của kỳ, kể cả ngày không phát sinh đơn.”

Lúc này cần tạo **khung tổ hợp**:

\[
\text{Tập cửa hàng} \times \text{Tập ngày}.
\]

Ví dụ dữ liệu có cửa hàng 1, 2; ta thêm một cửa hàng 3 **không có đơn trong bảng** để minh họa số 0. Tập cửa hàng được tạo trong CTE `stores`, không phụ thuộc việc cửa hàng đó có đơn hay không.

```sql
WITH RECURSIVE
stores(store_id) AS (
    VALUES (1), (2), (3)
),
calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1
    FROM calendar
    WHERE day_value < DATE '2026-11-16'
),
paid_by_store_day AS (
    SELECT
        store_id,
        ordered_on,
        COUNT(*) AS paid_orders,
        SUM(amount) AS paid_amount
    FROM lesson227_orders
    WHERE order_status = 'PAID'
      AND ordered_on >= DATE '2026-11-10'
      AND ordered_on <  DATE '2026-11-17'
    GROUP BY store_id, ordered_on
)
SELECT
    s.store_id,
    c.day_value,
    COALESCE(p.paid_orders, 0) AS paid_orders,
    COALESCE(p.paid_amount, 0) AS paid_amount
FROM stores AS s
CROSS JOIN calendar AS c
LEFT JOIN paid_by_store_day AS p
    ON p.store_id = s.store_id
   AND p.ordered_on = c.day_value
ORDER BY s.store_id, c.day_value;
```

Có **3 cửa hàng × 7 ngày = 21 dòng**. Cửa hàng 3 xuất hiện ở đủ bảy ngày với chỉ số 0. Những dòng đáng chú ý:

| store_id | Ngày | Đơn PAID | Số tiền |
|---:|---|---:|---:|
| 1 | 10/11 | 2 | 150.000 |
| 1 | 12/11 | 0 | 0 |
| 1 | 13/11 | 1 | 40.000 |
| 2 | 10/11 | 1 | 80.000 |
| 2 | 14/11 | 1 | 120.000 |
| 2 | 16/11 | 1 | 90.000 |
| 3 | Mọi ngày trong kỳ | 0 | 0 |

Đây là trường hợp `CROSS JOIN` **có chủ đích**: ta muốn mọi tổ hợp cửa hàng–ngày, rồi mới gắn số liệu.

### 11.1. Cẩn thận khi tổ hợp lớn

Với **10.000 cửa hàng × 3.650 ngày**, bạn tạo **36,5 triệu tổ hợp** trước khi xét điều kiện khác. Nếu nhu cầu chỉ là các cửa hàng đang hoạt động hoặc 30 ngày gần nhất, hãy thu hẹp tập cửa hàng và khoảng ngày từ đầu.

Đối với hệ thống có nhiều cửa hàng, bảng lịch có thể kết hợp với **bảng cửa hàng được lọc theo ngày hoạt động**, hoặc chiến lược báo cáo khác, để tránh tạo số dòng không cần thiết.

## 12. Dùng lịch đầy đủ để tính cửa sổ ngày liên tiếp

Hàm cửa sổ như `SUM(...) OVER (...)` rất hữu ích, nhưng phải hiểu **ROWS tính trên số dòng đã xuất hiện**.

Nếu bảng đơn chỉ có hoạt động vào ngày 10, 13, 14, 16/11, “ba dòng trước” không đồng nghĩa với “ba ngày lịch”.

Hãy tạo **một dòng cho mỗi ngày** trước khi tính cửa sổ ba ngày:

```sql
WITH RECURSIVE
calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1
    FROM calendar
    WHERE day_value < DATE '2026-11-16'
),
paid_daily AS (
    SELECT
        ordered_on,
        SUM(amount) AS paid_amount
    FROM lesson227_orders
    WHERE order_status = 'PAID'
      AND ordered_on >= DATE '2026-11-10'
      AND ordered_on <  DATE '2026-11-17'
    GROUP BY ordered_on
),
full_daily AS (
    SELECT
        c.day_value,
        COALESCE(p.paid_amount, 0) AS paid_amount
    FROM calendar AS c
    LEFT JOIN paid_daily AS p
        ON p.ordered_on = c.day_value
)
SELECT
    day_value,
    paid_amount,
    SUM(paid_amount) OVER (
        ORDER BY day_value
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS revenue_last_up_to_3_days
FROM full_daily
ORDER BY day_value;
```

Kết quả:

| Ngày | Doanh thu ngày | Tổng trong tối đa 3 ngày lịch gần nhất |
|---|---:|---:|
| 10/11 | 230.000 | 230.000 |
| 11/11 | 0 | 230.000 |
| 12/11 | 0 | 230.000 |
| 13/11 | 40.000 | 40.000 |
| 14/11 | 120.000 | 160.000 |
| 15/11 | 0 | 160.000 |
| 16/11 | 90.000 | 210.000 |

Giải thích ngày **16/11**: cửa sổ gồm **14, 15, 16/11**, nên tổng = `120000 + 0 + 90000 = 210000`.

Ở **đầu chuỗi**, cửa sổ chưa đủ ba ngày trong tập đã sinh: ngày 10 chỉ có một dòng, ngày 11 có hai dòng. Nếu nghiệp vụ cần cửa sổ **đầy đủ ba ngày** ngay từ ngày 10, phải sinh thêm ngày 8 và 9 làm dữ liệu nền trước khi tính, sau đó mới lọc kết quả hiển thị từ ngày 10.

**Cảnh báo:** cùng cú pháp `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` trên tập chỉ có **các ngày phát sinh doanh thu** sẽ tính ba **ngày có dữ liệu**, không phải ba **ngày lịch liên tục**. Khung lịch đầy đủ giải quyết sự khác biệt này.

## 13. Sinh lịch từ tham số và bảo vệ phạm vi trong ứng dụng

Trong ứng dụng, ngày bắt đầu và ngày kết thúc thường do người dùng chọn. Một chiến lược an toàn là:

1. Chuyển dữ liệu đầu vào thành **`DATE`** ở ứng dụng/driver.
2. Xác định ranh giới **`start_day`** và **`end_exclusive`**.
3. Kiểm tra `start_day < end_exclusive` và khoảng không quá dài.
4. Truyền tham số có kiểu phù hợp; không ghép chuỗi SQL trực tiếp.
5. Sinh ngày chỉ trong khoảng đã được kiểm tra.

Ví dụ PostgreSQL với tham số giả định `:start_day` và `:end_exclusive` (ký hiệu binding của tầng ứng dụng, **không phải cú pháp literal chung để dán trực tiếp vào psql**):

```sql
WITH RECURSIVE
bounds AS (
    SELECT
        CAST(:start_day AS DATE) AS start_day,
        CAST(:end_exclusive AS DATE) AS end_exclusive
),
calendar(day_value) AS (
    SELECT b.start_day
    FROM bounds AS b
    WHERE b.start_day < b.end_exclusive

    UNION ALL

    SELECT c.day_value + 1
    FROM calendar AS c
    CROSS JOIN bounds AS b
    WHERE c.day_value + 1 < b.end_exclusive
)
SELECT day_value
FROM calendar
ORDER BY day_value;
```

Trong PostgreSQL JDBC `PreparedStatement`, ký hiệu giữ chỗ thông dụng là `?`. Khi viết SQL thật cho JDBC, dùng `?` và truyền `LocalDate`/`java.sql.Date` phù hợp thay vì mặc định driver hỗ trợ tên `:start_day`.

### 13.1. Ví dụ Java tính đầu và cuối kỳ

```java
import java.time.LocalDate;

LocalDate startDay = LocalDate.of(2026, 11, 10);
LocalDate endExclusive = LocalDate.of(2026, 11, 17);

if (!startDay.isBefore(endExclusive)) {
    throw new IllegalArgumentException(
            "Ngày bắt đầu phải trước ngày kết thúc"
    );
}

long dayCount =
        java.time.temporal.ChronoUnit.DAYS.between(
                startDay, endExclusive);

if (dayCount > 366) {
    throw new IllegalArgumentException(
            "Khoảng ngày vượt giới hạn báo cáo"
    );
}
```

Đây là **kiểm tra trong ứng dụng** trước khi gửi truy vấn đến DBMS; nó không phụ thuộc cách PostgreSQL xử lý đệ quy. Khi nghiệp vụ muốn cho phép một khoảng rỗng và trả 0 dòng, thay vì báo lỗi, hãy xử lý theo quy ước riêng.

### 13.2. Vì sao kiểm tra phạm vi quan trọng?

Một công cụ báo cáo cho phép chọn từ năm 1900 đến năm 2100 có thể sinh hơn 73.000 dòng ngày. Con số đó chưa quá lớn nếu chỉ có một lịch, nhưng **JOIN mỗi ngày với hàng nghìn cửa hàng, sản phẩm hoặc phân đoạn khách hàng** có thể tạo một số dòng rất lớn.

Thêm biên giới hạn vào truy vấn đệ quy và **giới hạn đầu vào nghiệp vụ** là cách quản trị tài nguyên rõ ràng hơn trông chờ DBMS tự ngắt.

## 14. DATE, TIMESTAMP và múi giờ: “một ngày” là gì?

**Sinh dãy `DATE`** và **sinh dãy thời điểm `TIMESTAMPTZ`** là hai bài toán khác nhau.

- `DATE '2026-11-14'` biểu diễn **ngày theo lịch**, không có múi giờ riêng.
- `TIMESTAMP '2026-11-14 00:00:00'` là ngày giờ không đi kèm timezone.
- `TIMESTAMPTZ` trong PostgreSQL biểu diễn một **thời điểm trên dòng thời gian**, thường được hiển thị theo timezone phiên.

Nếu báo cáo hỏi “ngày 14/11 theo giờ Việt Nam”, đó là **khoảng hai mốc nửa đêm theo `Asia/Ho_Chi_Minh`**, không phải tự động là ngày UTC 14/11.

### 14.1. Một instant có thể thuộc hai ngày khác nhau

```sql
SELECT
    TIMESTAMPTZ '2026-11-13 17:30:00+00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh' AS vietnam_time,
    TIMESTAMPTZ '2026-11-13 17:30:00+00'
        AT TIME ZONE 'UTC' AS utc_time;
```

Hai giá trị hiển thị là:

- Giờ Việt Nam: **2026-11-14 00:30:00**.
- Giờ UTC: **2026-11-13 17:30:00**.

Do đó, một sự kiện có thể thuộc ngày 14/11 trong báo cáo Việt Nam nhưng thuộc ngày 13/11 trong báo cáo UTC.

### 14.2. Lịch DATE làm khung, chuyển biên mỗi ngày thành instant

Giả sử có bảng `events(event_id, happened_at TIMESTAMPTZ, status)`. Yêu cầu là **mỗi ngày theo giờ Việt Nam**, gồm các ngày có số sự kiện bằng 0.

Mẫu truy vấn:

```sql
-- Ví dụ thiết kế: cần có bảng events với các cột đã nêu.
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1
    FROM calendar
    WHERE day_value < DATE '2026-11-16'
)
SELECT
    c.day_value,
    COUNT(e.event_id) AS event_count
FROM calendar AS c
LEFT JOIN events AS e
    ON e.happened_at >= (
           c.day_value::TIMESTAMP
           AT TIME ZONE 'Asia/Ho_Chi_Minh'
       )
   AND e.happened_at < (
           (c.day_value + 1)::TIMESTAMP
           AT TIME ZONE 'Asia/Ho_Chi_Minh'
       )
   AND e.status = 'CONFIRMED'
GROUP BY c.day_value
ORDER BY c.day_value;
```

Mỗi ngày `c.day_value` được đổi thành **hai mốc instant**:

1. Nửa đêm địa phương đầu ngày.
2. Nửa đêm địa phương đầu ngày tiếp theo.

Điều kiện `>= start AND < end` bảo đảm một sự kiện đúng biên nửa đêm **không bị tính vào hai ngày**.

Trong PostgreSQL, `AT TIME ZONE 'Asia/Ho_Chi_Minh'` trên `TIMESTAMP` diễn giải ngày giờ địa phương thành `TIMESTAMPTZ`, giúp so sánh với cột `happened_at` cùng kiểu.

### 14.3. Không mặc định mỗi ngày địa phương dài đúng 24 giờ

Ở khu vực có thay đổi giờ mùa hè, chẳng hạn `America/New_York`, một ngày theo lịch có thể dài **23 hoặc 25 giờ thực**.

Nếu xây dựng lịch theo ngày địa phương, hãy tăng **`DATE` thêm một ngày**, sau đó chuyển **mỗi nửa đêm địa phương** sang instant. Đừng mặc định lấy mốc `TIMESTAMPTZ` rồi cộng đúng `INTERVAL '24 hours'` để biểu diễn đầu ngày tiếp theo ở mọi vùng.

Một recursive CTE sinh ngày có thể giúp tạo **các ngày địa phương đúng thứ tự**; ngữ nghĩa múi giờ phải được áp dụng khi gắn dữ liệu thời điểm vào từng ngày.

## 15. Khi PostgreSQL có generate_series: thường đơn giản hơn đệ quy

Trong PostgreSQL, hàm `generate_series` trực tiếp tạo dãy số hoặc timestamp. Nếu chỉ cần **dãy đều với bước cố định**, nó thường **ngắn, rõ ràng và phù hợp hơn** so với tự xây dựng recursive CTE.

### 15.1. Sinh dãy số

```sql
SELECT n
FROM generate_series(1, 10, 1) AS g(n)
ORDER BY n;
```

Kết quả: các số `1` đến `10`.

Các tham số là:

1. `start`: giá trị bắt đầu.
2. `stop`: **giá trị cuối được bao gồm nếu nằm đúng trên bước nhảy**.
3. `step`: bước tăng/giảm.

`generate_series(2, 17, 3)` trả `2, 5, 8, 11, 14, 17`.

Với `start > stop` và bước dương, hàm trả **tập rỗng**. Với bước âm, có thể sinh dãy giảm:

```sql
SELECT n
FROM generate_series(10, 0, -2) AS g(n)
ORDER BY n DESC;
```

Kết quả: `10, 8, 6, 4, 2, 0`.

Không dùng bước `0`; PostgreSQL báo lỗi cho bước bằng 0.

### 15.2. Sinh dãy ngày

`generate_series` có dạng timestamp với bước `INTERVAL`; ta ép các mốc thành `TIMESTAMP` rồi đổi đầu ra về `DATE`:

```sql
SELECT
    g.day_timestamp::DATE AS day_value
FROM generate_series(
    TIMESTAMP '2026-11-10 00:00:00',
    TIMESTAMP '2026-11-16 00:00:00',
    INTERVAL '1 day'
) AS g(day_timestamp)
ORDER BY day_value;
```

Kết quả cũng là ngày 10–16/11/2026.

Hàm nhận **biên cuối bao gồm**. Nếu ứng dụng dùng khoảng `[start_day, end_exclusive)`, có thể trừ một ngày khỏi mốc ngày cuối **khi đầu vào là `DATE`**, sau khi kiểm tra khoảng không rỗng.

Ví dụ tháng 11/2026:

```sql
SELECT g.dt::DATE AS day_value
FROM generate_series(
    TIMESTAMP '2026-11-01 00:00:00',
    TIMESTAMP '2026-11-30 00:00:00',
    INTERVAL '1 day'
) AS g(dt)
ORDER BY day_value;
```

Để tránh phải tự xác định ngày cuối tháng, có thể đặt mốc từ `DATE`:

```sql
WITH bounds AS (
    SELECT
        DATE '2026-11-01' AS month_start,
        DATE '2026-12-01' AS next_month_start
)
SELECT g.dt::DATE AS day_value
FROM bounds AS b
CROSS JOIN LATERAL generate_series(
    b.month_start::TIMESTAMP,
    (b.next_month_start - 1)::TIMESTAMP,
    INTERVAL '1 day'
) AS g(dt)
ORDER BY day_value;
```

Đây là cách **không cần đệ quy** trong PostgreSQL và trả đủ 30 ngày của tháng 11.

### 15.3. So sánh nhanh hai cách

| Tiêu chí | `WITH RECURSIVE` | `generate_series` PostgreSQL |
|---|---|---|
| Sinh số 1..100 | Viết anchor, UNION ALL, điều kiện dừng | `generate_series(1,100)` |
| Sinh từng ngày | Có thể tăng `DATE + 1` | Hàm timestamp + `INTERVAL '1 day'` |
| Bước cố định | Có | Có; thường ngắn hơn |
| Bước tiếp theo phụ thuộc trạng thái/tính toán trước | **Linh hoạt hơn** | Thường không phù hợp bằng |
| Điều kiện dừng tự thiết kế | Bắt buộc quản lý rõ | Hành vi biên của hàm đã được xác định |
| Chuyển sang nhiều DBMS | Dựa trên mẫu recursive CTE, chỉnh cú pháp | Hàm riêng, không phổ quát |
| Dãy lớn hoặc sử dụng thường xuyên | Có thể tốn chi phí đệ quy | Thường là lựa chọn đáng cân nhắc |
| Lịch có ngày lễ/ngày làm việc theo doanh nghiệp | Cần bổ sung dữ liệu | Cũng cần bổ sung dữ liệu |

**Lựa chọn thực tế trong PostgreSQL:** nếu chỉ muốn dãy số/dãy ngày đều, hãy **xem xét `generate_series` trước**. Học recursive CTE vẫn quan trọng vì nó mô tả cách tạo kết quả từ bước trước và có thể được dùng trong những bài toán trạng thái phức tạp hơn.

## 16. Khi nào nên dùng bảng lịch thay vì sinh lại?

Một **bảng lịch** có thể lưu sẵn từng ngày với các thuộc tính phục vụ nhiều báo cáo:

```text
calendar_date
-------------
day_date
iso_weekday
iso_week_number
month_number
quarter_number
year_number
is_weekend
is_business_day
is_public_holiday
fiscal_period
...
```

Ví dụ thiết kế:

```sql
CREATE TABLE lesson227_calendar_dimension (
    day_date DATE PRIMARY KEY,
    is_business_day BOOLEAN NOT NULL,
    fiscal_year INTEGER,
    fiscal_period INTEGER
);
```

Ở hệ thống thực tế, bảng lịch cần được **điền dữ liệu và duy trì theo quy tắc nghiệp vụ**. Bài học không tự động thêm ngày lễ hoặc năm tài chính vào bảng minh họa này.

### 16.1. Bảng lịch hữu ích khi

- Nhiều báo cáo cùng dùng các kỳ ngày, tuần, tháng.
- Cần **ngày lễ**, **ngày nghỉ bù**, **ngày làm việc theo vùng**.
- Cần lịch tài chính, tuần bán lẻ hoặc năm tài chính không trùng năm dương lịch.
- Cần liên kết thông tin ngày với các bảng fact lớn trong hệ thống phân tích.
- Cần thay đổi lịch theo **vùng hoặc đơn vị tổ chức**, có quản lý phiên bản/quy tắc.

### 16.2. Khi nào không cần bảng lịch?

Nếu chỉ cần một truy vấn thử nghiệm với 7 ngày, tạo hoặc bảo trì một bảng vĩnh viễn có thể là quá mức cần thiết. `generate_series` hoặc recursive CTE là đủ.

### 16.3. Đừng giả định ngày lễ chỉ cần EXTRACT(DOW)

`EXTRACT(ISODOW ...) BETWEEN 1 AND 5` chỉ xác định **thứ Hai–thứ Sáu**, không tự loại được:

- Ngày lễ rơi vào ngày làm việc.
- Ngày nghỉ bù.
- Ngày làm việc cuối tuần theo quy định riêng.
- Ngày cửa hàng đóng cửa đặc biệt.

Một bảng lịch nghiệp vụ có dữ liệu chính thức và chủ sở hữu chịu trách nhiệm cập nhật thường phù hợp hơn phép tính từ thứ trong tuần.

## 17. Bảng số (tally table) là một lựa chọn khác

Ngoài bảng lịch, nhiều hệ thống có **bảng số nguyên liên tiếp** để tái sử dụng, thường gọi là *numbers table* hoặc *tally table*.

Một bảng số có thể lưu:

```text
n
--
0
1
2
3
4
5
...
```

Từ đó suy ra ngày:

```sql
-- Ví dụ thiết kế, giả định có bảng numbers(n).
SELECT
    DATE '2026-11-10' + n AS day_value
FROM numbers
WHERE n BETWEEN 0 AND 6
ORDER BY n;
```

Bảng số không cần truy vấn đệ quy lúc chạy nếu đã được tạo và quản lý trước. Tuy nhiên:

- Phải đảm bảo dãy số được điền đủ, không có lỗ hổng.
- Phải có số lớn nhất đáp ứng phạm vi sử dụng.
- Với ứng dụng nhỏ, thêm bảng này có thể không cần thiết.

Một ưu điểm của bảng số là có thể dùng cho **nhiều loại chuỗi**: ngày, tuần, vị trí trong văn bản, tổ hợp mẫu, v.v. Nhưng với PostgreSQL, `generate_series` thường đáp ứng rất thuận tiện các nhu cầu đó mà không cần lưu bảng số riêng.

## 18. Sinh khoảng theo bước thời gian: giờ và phút

Tư duy đệ quy cũng có thể tạo các mốc giờ, nhưng phải xác định **kiểu thời gian** và **đơn vị bước**.

Ví dụ các mốc giờ trong một ngày, dùng `TIMESTAMP` không có múi giờ:

```sql
WITH RECURSIVE hourly_slots(slot_start) AS (
    SELECT TIMESTAMP '2026-11-14 08:00:00'

    UNION ALL

    SELECT slot_start + INTERVAL '1 hour'
    FROM hourly_slots
    WHERE slot_start + INTERVAL '1 hour'
          < TIMESTAMP '2026-11-14 13:00:00'
)
SELECT slot_start
FROM hourly_slots
ORDER BY slot_start;
```

Kết quả: `08:00`, `09:00`, `10:00`, `11:00`, `12:00` — năm mốc, mỗi mốc có thể đại diện khoảng `[slot_start, slot_start + 1 hour)`.

### 18.1. Khoảng nửa mở tránh trùng ranh giới

Nếu các ca là:

- `[08:00,09:00)`
- `[09:00,10:00)`
- `[10:00,11:00)`

thì sự kiện đúng lúc `09:00` chỉ thuộc ca thứ hai, không bị đếm hai lần.

### 18.2. Ca làm việc theo múi giờ

Ở các khu vực có DST, có những giờ địa phương **không tồn tại** hoặc xuất hiện **hai lần** khi đổi giờ. Nếu mục tiêu là tạo các giờ thực trên dòng thời gian, cần thiết kế dựa trên instant/timestamp with timezone và cách biểu diễn múi giờ; nếu là các **ca địa phương cố định**, cần quy tắc xử lý ngày đổi giờ.

Không áp dụng mù quáng “cộng đúng một giờ” cho mọi dạng lịch ca qua vùng DST. Với lịch ngày, việc sinh `DATE` rồi xác định hai nửa đêm theo timezone khu vực thường rõ nghĩa hơn.

## 19. Đối chiếu cú pháp giữa các hệ quản trị

Không phải DBMS nào cũng viết `WITH RECURSIVE` hay phép cộng ngày giống PostgreSQL.

| DBMS | Cú pháp recursive CTE | Ghi chú |
|---|---|---|
| **PostgreSQL** | `WITH RECURSIVE` | `DATE + 1` để tăng ngày; có `generate_series` rất tiện |
| **MySQL 8.0+** | `WITH RECURSIVE` | Thường dùng `DATE_ADD(..., INTERVAL 1 DAY)`; giới hạn độ sâu `cte_max_recursion_depth` |
| **SQLite** | `WITH RECURSIVE` | Thường lưu ngày dưới dạng văn bản ISO và dùng `date(value, '+1 day')` |
| **SQL Server** | `WITH` (không dùng `RECURSIVE`) | `DATEADD(day,1,...)`; tùy chọn `OPTION (MAXRECURSION n)`; `GENERATE_SERIES` ở phiên bản/phạm vi tương thích thích hợp |
| **Oracle Database** | Recursive subquery factoring bằng `WITH` trong nhiều phiên bản | Có cú pháp và giới hạn riêng; cũng có các phương pháp khác để sinh dãy |

### 19.1. MySQL 8.0+

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < 10
)
SELECT n
FROM numbers
ORDER BY n;
```

Sinh ngày:

```sql
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE('2026-11-10')

    UNION ALL

    SELECT DATE_ADD(day_value, INTERVAL 1 DAY)
    FROM calendar
    WHERE day_value < DATE('2026-11-16')
)
SELECT day_value
FROM calendar
ORDER BY day_value;
```

MySQL có cấu hình `cte_max_recursion_depth` để giới hạn số bước đệ quy (giá trị mặc định thông dụng là **1000** trong MySQL 8.0). Đừng xem nó là điều kiện nghiệp vụ; nếu khoảng dài hơn, cần điều chỉnh có kiểm soát hoặc chọn cách sinh dãy khác.

### 19.2. SQL Server

Trong T-SQL, CTE đệ quy sử dụng `WITH`, **không thêm từ `RECURSIVE`**:

```sql
WITH numbers(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 10
)
SELECT n
FROM numbers
ORDER BY n
OPTION (MAXRECURSION 100);
```

Ngày kế tiếp dùng `DATEADD`:

```sql
WITH calendar(day_value) AS (
    SELECT CAST('2026-11-10' AS date)

    UNION ALL

    SELECT DATEADD(day, 1, day_value)
    FROM calendar
    WHERE day_value < CAST('2026-11-16' AS date)
)
SELECT day_value
FROM calendar
ORDER BY day_value
OPTION (MAXRECURSION 100);
```

Ở SQL Server, giới hạn recursion mặc định thường là **100**, còn `OPTION (MAXRECURSION n)` cho phép điều chỉnh trong một khoảng hợp lệ. `MAXRECURSION 0` gỡ giới hạn do tùy chọn này, **không bảo đảm truy vấn dừng**; nên giữ điều kiện dừng hợp lý.

Các phiên bản SQL Server mới có `GENERATE_SERIES` (được giới thiệu từ SQL Server 2022, với mức tương thích cơ sở dữ liệu phù hợp) cho việc sinh dãy số, giúp tránh recursive CTE nếu chỉ cần chuỗi số đơn giản.

### 19.3. SQLite

SQLite thường biểu diễn ngày bằng chuỗi ISO `YYYY-MM-DD` và có hàm `date` để tính ngày kế tiếp:

```sql
WITH RECURSIVE calendar(day_value) AS (
    VALUES ('2026-11-10')

    UNION ALL

    SELECT date(day_value, '+1 day')
    FROM calendar
    WHERE day_value < '2026-11-16'
)
SELECT day_value
FROM calendar
ORDER BY day_value;
```

Điều kiện so sánh chuỗi ở đây có ý nghĩa theo **ngày lịch** vì mọi giá trị được chuẩn hóa cùng định dạng ISO `YYYY-MM-DD`. Nếu trộn định dạng `DD/MM/YYYY`, timestamp với offset khác nhau hoặc chuỗi thiếu số 0 đệm, so sánh từ điển có thể không phản ánh đúng thứ tự ngày.

### 19.4. Oracle Database

Oracle hỗ trợ recursive subquery factoring trong `WITH`, với cú pháp có thể khác PostgreSQL. Ví dụ minh họa cho dãy số ở những phiên bản hỗ trợ:

```sql
WITH numbers(n) AS (
    SELECT 1 FROM dual

    UNION ALL

    SELECT n + 1
    FROM numbers
    WHERE n < 10
)
SELECT n
FROM numbers
ORDER BY n;
```

Oracle cũng có những cách riêng để sinh dãy, chẳng hạn các truy vấn phân cấp với `CONNECT BY LEVEL`; không áp dụng máy móc cú pháp `WITH RECURSIVE` của PostgreSQL vào mọi phiên bản Oracle.

## 20. Hiệu năng: chi phí sinh dãy và chi phí JOIN báo cáo

Sinh 7 hoặc 30 ngày là công việc nhỏ. Nhưng cần quan tâm:

1. **Số dòng được sinh:** 30 ngày khác 30 triệu số.
2. **Bước nhảy:** bước 1 giây cho 10 năm sẽ tạo hàng trăm triệu mốc.
3. **Số nhóm nhân với lịch:** 1.000 cửa hàng × 365 ngày = 365.000 tổ hợp.
4. **Kiểu JOIN:** nối trực tiếp từng ngày với bảng sự kiện lớn có thể tạo nhiều phép tìm kiếm.
5. **Điều kiện lọc nguồn:** lọc trạng thái và khoảng thời gian sớm giúp tránh đọc dữ liệu không cần thiết.
6. **Chỉ mục:** cột ngày, cửa hàng và trạng thái có thể cần chỉ mục phù hợp với workload.

Một chỉ mục minh họa trong PostgreSQL:

```sql
CREATE INDEX lesson227_orders_status_day_idx
    ON lesson227_orders (order_status, ordered_on);
```

Nếu báo cáo thường lọc theo **cửa hàng và ngày**, có thể xem xét chỉ mục theo `(store_id, ordered_on)` hoặc tổ hợp khác. Việc chọn chỉ mục phải dựa trên các truy vấn thật, độ chọn lọc và chi phí ghi dữ liệu.

### 20.1. EXPLAIN để xem kế hoạch truy vấn

```sql
EXPLAIN
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1
    FROM calendar
    WHERE day_value < DATE '2026-11-16'
)
SELECT
    c.day_value,
    COUNT(o.order_id)
FROM calendar AS c
LEFT JOIN lesson227_orders AS o
    ON o.ordered_on = c.day_value
   AND o.order_status = 'PAID'
GROUP BY c.day_value
ORDER BY c.day_value;
```

Kế hoạch có thể gồm những bước đệ quy, quét nguồn, JOIN và aggregate; PostgreSQL có thể hiển thị các nút liên quan đến `Recursive Union` hoặc `WorkTable Scan`. Việc sử dụng chỉ mục phụ thuộc số dòng và thống kê; với bảng mẫu chỉ có 9 đơn, quét toàn bảng có thể hợp lý hơn.

`EXPLAIN ANALYZE` còn **thực thi truy vấn** để đo thời gian. Chỉ dùng khi phù hợp và biết rõ tác động của câu SQL.

### 20.2. Không phải mọi truy vấn đệ quy đều tối ưu nhờ CTE

Recursive CTE thường có tính linh hoạt khi **bước sau phụ thuộc kết quả bước trước**, nhưng nếu chỉ sinh ngày theo bước đều, hàm `generate_series` hoặc bảng lịch có thể đơn giản hơn và giảm chi phí xử lý.

Một nguyên tắc dễ dùng:

- **Cần chuỗi ngắn, đơn giản:** dùng cách dễ hiểu nhất của DBMS.
- **PostgreSQL và chuỗi đều:** ưu tiên cân nhắc `generate_series`.
- **Quy tắc sinh tiếp phức tạp, phụ thuộc trạng thái:** recursive CTE có thể phù hợp.
- **Lịch nghiệp vụ dùng lặp lại với thuộc tính bổ sung:** bảng calendar dimension thường phù hợp.

## 21. Các lỗi phổ biến khi sinh dãy và lịch ngày

### Lỗi 1. Không có điều kiện dừng

```sql
-- Không chạy: có thể không dừng.
WITH RECURSIVE n(x) AS (
    SELECT 1
    UNION ALL
    SELECT x + 1 FROM n
)
SELECT COUNT(*) FROM n;
```

**Sửa:** định nghĩa rõ giá trị kết thúc và điều kiện trong recursive member.

### Lỗi 2. Lệch một ngày ở ranh giới

```sql
-- Sinh cả ngày 17, dù mục tiêu chỉ đến hết 16:
WHERE day_value < DATE '2026-11-17'
```

Với nhánh `SELECT day_value + 1`, điều kiện kiểm tra giá trị hiện tại `< 17` cho phép **16 + 1 = 17**. Sửa thành `day_value < DATE '2026-11-16'`, hoặc xét giá trị mới `day_value + 1 < DATE '2026-11-17'`.

### Lỗi 3. Anchor sinh dòng dù khoảng rỗng

```sql
WITH RECURSIVE n(x) AS (
    SELECT 10
    UNION ALL
    SELECT x + 1 FROM n WHERE x < 5
)
SELECT x FROM n;
```

Kết quả chứa **10**, dù yêu cầu `[10,5)` phải rỗng. Cần kiểm tra `start < end_exclusive` ngay ở anchor.

### Lỗi 4. Nhánh đệ quy không tiến về điểm dừng

```sql
-- Nguy hiểm: n luôn bằng 1, điều kiện luôn đúng.
WITH RECURSIVE n(x) AS (
    SELECT 1
    UNION ALL
    SELECT x FROM n WHERE x < 10
)
SELECT COUNT(*) FROM n;
```

Không sinh tiến triển, truy vấn có thể không dừng. Phải có bước thay đổi rõ ràng, đúng hướng và chặn vòng lặp.

### Lỗi 5. Dùng LIMIT ở ngoài để “ngăn vô hạn”

`LIMIT` ở truy vấn cuối không phải cơ chế an toàn nếu có `ORDER BY`, `JOIN`, `COUNT` hoặc optimizer xử lý khác. Đặt điều kiện dừng trong recursive member.

### Lỗi 6. Tưởng GROUP BY tự sinh ngày chưa có giao dịch

`GROUP BY ordered_on` chỉ tạo nhóm cho **những ngày xuất hiện trong dữ liệu**. Muốn ngày có số đơn 0, sinh khung lịch độc lập rồi `LEFT JOIN`.

### Lỗi 7. Dùng INNER JOIN với lịch rồi làm mất ngày rỗng

```sql
FROM calendar AS c
JOIN paid_daily AS p
    ON p.ordered_on = c.day_value
```

`INNER JOIN` chỉ giữ ngày có dữ liệu. Nếu muốn đầy đủ, dùng `LEFT JOIN` với `calendar` ở phía trái.

### Lỗi 8. Đặt điều kiện bảng bên phải trong WHERE

```sql
-- Có thể loại ngày không có đơn PAID.
FROM calendar AS c
LEFT JOIN lesson227_orders AS o
    ON o.ordered_on = c.day_value
WHERE o.order_status = 'PAID'
```

Điều kiện null-rejecting này loại ngày chỉ có dữ liệu `NULL` sau `LEFT JOIN`. Nếu muốn giữ lịch đủ ngày, đặt trạng thái trong `ON` hoặc trong CTE tổng hợp nguồn trước khi JOIN.

### Lỗi 9. Dùng COUNT(*) để đếm đơn sau LEFT JOIN

Ngày không có đơn vẫn có một dòng được bảo toàn, nên `COUNT(*)` có thể bằng 1. Dùng `COUNT(o.order_id)` hoặc số đếm trong CTE tổng hợp.

### Lỗi 10. Dùng ROWS trước khi lấp ngày thiếu

Cửa sổ `ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` đếm **dòng**, không tự đếm **ngày lịch**. Nếu bảng chỉ có ngày phát sinh đơn, “3 dòng” có thể cách nhau nhiều ngày. Tạo lịch ngày liên tục trước khi tính.

### Lỗi 11. Nhầm một ngày lịch với 24 giờ thực

Đặc biệt ở múi giờ có DST, ngày địa phương có thể dài 23 hoặc 25 giờ. Dùng `DATE` tạo lịch và chuyển từng ranh giới nửa đêm sang instant theo timezone cần báo cáo.

### Lỗi 12. Tạo tổ hợp cửa hàng × ngày quá lớn

`CROSS JOIN` có thể hữu ích để báo cáo mọi cửa hàng–ngày, nhưng số dòng bằng tích hai tập. Hãy lọc phạm vi phù hợp và cân nhắc khả năng mở rộng.

### Lỗi 13. Cố dùng recursive CTE khi DBMS có hàm chuyên dụng

Trên PostgreSQL, `generate_series(1, 100)` thường ngắn và rõ hơn một CTE đệ quy nhiều dòng. Hãy chọn công cụ phù hợp, không xem đệ quy là bắt buộc.

### Lỗi 14. Coi thứ tự sinh là thứ tự hiển thị

Ngay cả khi giá trị sinh tăng từ 1 lên N, khi hiển thị kết quả nên dùng:

```sql
ORDER BY n;
```

Đừng dựa vào thứ tự thực thi nội bộ của recursive CTE như một cam kết thứ tự kết quả. `ORDER BY` ở câu ngoài cùng xác định thứ tự người dùng nhận được.

## 22. Bài tập thực hành kèm lời giải

Các bài dùng PostgreSQL và bảng `lesson227_orders` của phần 7 khi có `FROM lesson227_orders`. Tự dự đoán trước khi xem đáp án.

### Bài 1. Sinh số 1 đến 8

**Yêu cầu:** dùng `WITH RECURSIVE` tạo tám dòng từ `1` đến `8`.

```sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 8
)
SELECT n
FROM numbers
ORDER BY n;
```

**Đáp án:** `1, 2, 3, 4, 5, 6, 7, 8`. Anchor 1 được tính là dòng đầu tiên.

### Bài 2. Sinh các bội số của 5 không vượt quá 30

```sql
WITH RECURSIVE multiples(n) AS (
    SELECT 5
    UNION ALL
    SELECT n + 5
    FROM multiples
    WHERE n + 5 <= 30
)
SELECT n
FROM multiples
ORDER BY n;
```

**Đáp án:** `5, 10, 15, 20, 25, 30`. Điều kiện trên **giá trị mới** tránh vượt quá 30.

### Bài 3. Đếm số ngày của tháng nhuận

```sql
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2024-02-01'
    UNION ALL
    SELECT day_value + 1
    FROM calendar
    WHERE day_value + 1 < DATE '2024-03-01'
)
SELECT
    COUNT(*) AS days_in_month,
    MAX(day_value) AS last_day
FROM calendar;
```

**Đáp án:** `days_in_month = 29`, `last_day = 2024-02-29`.

### Bài 4. Tại sao câu sau tạo thêm 17/11?

```sql
WITH RECURSIVE calendar(d) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT d + 1
    FROM calendar
    WHERE d < DATE '2026-11-17'
)
SELECT d FROM calendar ORDER BY d;
```

**Đáp án:** khi `d = 16/11`, điều kiện `d < 17/11` vẫn TRUE nên sinh thêm **17/11**. Để chỉ lấy tới hết 16/11, dùng `WHERE d < DATE '2026-11-16'` hoặc `WHERE d + 1 < DATE '2026-11-17'`.

### Bài 5. Lịch PAID đủ bảy ngày

**Yêu cầu:** tạo 7 ngày 10–16/11, đếm đơn PAID; ngày rỗng phải hiện 0.

```sql
WITH RECURSIVE calendar(d) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT d + 1 FROM calendar
    WHERE d < DATE '2026-11-16'
)
SELECT
    c.d,
    COUNT(o.order_id) AS paid_order_count
FROM calendar AS c
LEFT JOIN lesson227_orders AS o
    ON o.ordered_on = c.d
   AND o.order_status = 'PAID'
GROUP BY c.d
ORDER BY c.d;
```

**Đáp án:** lần lượt `3, 0, 0, 1, 1, 0, 1`; tổng là **6 đơn**.

### Bài 6. Vì sao COUNT(*) sai trong báo cáo ngày?

Nếu thay `COUNT(o.order_id)` ở bài 5 bằng `COUNT(*)`, ngày 11/11 không có đơn sẽ có số đếm bao nhiêu?

**Đáp án:** `1`, vì `LEFT JOIN` tạo một dòng lịch với các cột đơn hàng `NULL`. `COUNT(*)` đếm dòng đó; `COUNT(o.order_id)` bỏ qua `NULL` nên đếm `0`.

### Bài 7. Những ngày không có đơn PAID

```sql
WITH RECURSIVE calendar(d) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT d + 1 FROM calendar
    WHERE d < DATE '2026-11-16'
)
SELECT d
FROM calendar
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson227_orders AS o
    WHERE o.ordered_on = d
      AND o.order_status = 'PAID'
)
ORDER BY d;
```

**Đáp án:** **11, 12, 15/11/2026**.

### Bài 8. Tìm ngày không có bất kỳ đơn nào

**Yêu cầu:** giữ khoảng ngày của bài 7 nhưng xét **mọi trạng thái**.

```sql
WITH RECURSIVE calendar(d) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT d + 1 FROM calendar
    WHERE d < DATE '2026-11-16'
)
SELECT c.d
FROM calendar AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson227_orders AS o
    WHERE o.ordered_on = c.d
)
ORDER BY c.d;
```

**Đáp án:** **11 và 15/11/2026**. Ngày 12 có đơn `PENDING` nên không phải ngày “không có bất kỳ đơn nào”.

### Bài 9. Báo cáo doanh thu từng ngày

```sql
WITH RECURSIVE calendar(d) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT d + 1 FROM calendar
    WHERE d < DATE '2026-11-16'
),
daily AS (
    SELECT
        ordered_on,
        SUM(amount) AS paid_amount
    FROM lesson227_orders
    WHERE order_status = 'PAID'
      AND ordered_on >= DATE '2026-11-10'
      AND ordered_on <  DATE '2026-11-17'
    GROUP BY ordered_on
)
SELECT
    c.d,
    COALESCE(p.paid_amount, 0) AS paid_amount
FROM calendar AS c
LEFT JOIN daily AS p
    ON p.ordered_on = c.d
ORDER BY c.d;
```

**Đáp án:** `230000, 0, 0, 40000, 120000, 0, 90000`. Tổng bằng **480000**.

### Bài 10. Đếm số ngày không có đơn PAID

Dùng danh sách ngày ở bài 7 rồi đếm thay vì liệt kê:

```sql
WITH RECURSIVE calendar(d) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT d + 1 FROM calendar
    WHERE d < DATE '2026-11-16'
)
SELECT COUNT(*) AS no_paid_days
FROM calendar AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM lesson227_orders AS o
    WHERE o.ordered_on = c.d
      AND o.order_status = 'PAID'
);
```

**Đáp án:** **3 ngày** (11, 12, 15/11).

### Bài 11. Lịch theo cửa hàng

**Yêu cầu:** tạo mọi cặp `store_id` 1, 2 và ngày 10–16/11, bao gồm ngày không có doanh thu.

```sql
WITH RECURSIVE
stores(store_id) AS (
    VALUES (1), (2)
),
calendar(d) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT d + 1 FROM calendar
    WHERE d < DATE '2026-11-16'
),
daily AS (
    SELECT
        store_id,
        ordered_on,
        SUM(amount) AS revenue
    FROM lesson227_orders
    WHERE order_status = 'PAID'
      AND ordered_on >= DATE '2026-11-10'
      AND ordered_on <  DATE '2026-11-17'
    GROUP BY store_id, ordered_on
)
SELECT
    s.store_id,
    c.d,
    COALESCE(p.revenue, 0) AS revenue
FROM stores AS s
CROSS JOIN calendar AS c
LEFT JOIN daily AS p
    ON p.store_id = s.store_id
   AND p.ordered_on = c.d
ORDER BY s.store_id, c.d;
```

**Đáp án:** **14 dòng**, do `2 × 7`. Tổng doanh thu cửa hàng 1 trong kỳ = `100000 + 50000 + 40000 = 190000`; cửa hàng 2 = `80000 + 120000 + 90000 = 290000`.

### Bài 12. Tổng ba ngày lịch gần nhất ở 16/11

Theo dữ liệu đã lấp ngày rỗng, doanh thu 14, 15, 16/11 lần lượt là 120000, 0, 90000. Tính giá trị:

```sql
SUM(paid_amount) OVER (
    ORDER BY day_value
    ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
)
```

ở ngày 16/11.

**Đáp án:** **210000**. Nếu chưa lấp lịch, “ba dòng” có thể là ba **ngày có giao dịch**, dẫn đến chỉ số khác.

### Bài 13. Sinh lịch từ khoảng rỗng

```sql
WITH RECURSIVE
bounds AS (
    SELECT
        DATE '2026-11-17' AS first_day,
        DATE '2026-11-17' AS end_exclusive
),
calendar(d) AS (
    SELECT first_day
    FROM bounds
    WHERE first_day < end_exclusive

    UNION ALL

    SELECT c.d + 1
    FROM calendar AS c
    CROSS JOIN bounds AS b
    WHERE c.d + 1 < b.end_exclusive
)
SELECT d FROM calendar;
```

**Đáp án:** **0 dòng** vì `first_day = end_exclusive` và anchor đã kiểm tra khoảng rỗng.

### Bài 14. Viết lại dãy 1..10 bằng generate_series

```sql
SELECT n
FROM generate_series(1, 10) AS g(n)
ORDER BY n;
```

**Đáp án:** mười số từ 1 đến 10. Trong PostgreSQL, đây thường là cách **đơn giản hơn** một recursive CTE nếu chỉ cần dãy đều.

### Bài 15. Lựa chọn công cụ

Hãy chọn **recursive CTE**, **`generate_series`**, hoặc **bảng lịch** cho từng tình huống:

1. Sinh 30 ngày của một tháng trong một báo cáo PostgreSQL đơn giản.
2. Tính lịch nghỉ lễ theo địa phương, năm tài chính riêng và ngày làm việc của nhiều chi nhánh, dùng chung hàng trăm báo cáo.
3. Sinh chuỗi mốc tiếp theo dựa trên kết quả tính của bước trước, không có bước cộng cố định.
4. Sinh số 1 đến 100 để dựng dữ liệu thử nhỏ trong PostgreSQL.

**Gợi ý đáp án:**

1. `generate_series` thường gọn nhất; recursive CTE cũng hợp lệ.
2. **Bảng lịch nghiệp vụ** có dữ liệu được quản lý, bổ sung thuộc tính vùng/chi nhánh nếu cần.
3. **Recursive CTE**, với bước tiến và điều kiện dừng rõ ràng.
4. `generate_series(1,100)` thường đơn giản, không cần dựng CTE đệ quy.

Điểm quan trọng là chọn công cụ theo **đặc tính dữ liệu và yêu cầu**, không mặc định mọi bài toán liên quan tới dãy ngày đều bắt buộc dùng đệ quy.

## 23. Bảng ghi nhớ

| Yêu cầu | Mẫu hoặc lưu ý |
|---|---|
| Sinh số 1..N trong PostgreSQL bằng đệ quy | `WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x < N)` |
| Sinh ngày theo `DATE` | Anchor `DATE '...'`, nhánh `day_value + 1` |
| Giữ cả ngày cuối | `WHERE current_day < last_day` khi nhánh sinh `current_day + 1` |
| Giữ đầu, bỏ cuối `[start,end)` | Kiểm tra `next_day < end_exclusive`; anchor cũng kiểm tra `start < end_exclusive` |
| Tránh lặp vô hạn | Bước có tiến triển, điều kiện dừng, kiểm tra phạm vi |
| Sinh ngày không có dữ liệu | Lịch độc lập + `LEFT JOIN` dữ liệu đã tổng hợp |
| Đếm đơn đúng sau `LEFT JOIN` | `COUNT(o.order_id)`, không dùng `COUNT(*)` |
| Tìm ngày không có dữ liệu | Lịch + `NOT EXISTS` hoặc `LEFT JOIN ... IS NULL` |
| Báo cáo từng cửa hàng–ngày | `stores CROSS JOIN calendar`, sau đó `LEFT JOIN` dữ liệu |
| Cửa sổ ba ngày lịch | Tạo đủ một dòng/ngày trước khi dùng `ROWS` |
| Lịch theo múi giờ | Tạo `DATE` rồi chuyển ranh giới nửa đêm theo vùng thành instant |
| PostgreSQL sinh dãy đều đơn giản | `generate_series` thường tiện hơn |
| Lịch ngày lễ/năm tài chính dùng lại | Bảng calendar dimension |
| SQL Server | Recursive CTE dùng `WITH`, tăng ngày bằng `DATEADD`, có `MAXRECURSION` |
| MySQL | `WITH RECURSIVE`, `DATE_ADD`, chú ý `cte_max_recursion_depth` |
| SQLite | `WITH RECURSIVE`, `date(value,'+1 day')` với chuỗi ISO |
| Hiệu năng | Kiểm soát số dòng sinh, tránh tổ hợp quá lớn, xem `EXPLAIN` |

## 24. Kết luận

**Recursive CTE cho phép sinh dãy số hoặc lịch ngày bằng cách định nghĩa giá trị khởi đầu, quy tắc tạo bước kế tiếp và điều kiện dừng.** Đối với báo cáo theo ngày, lợi ích lớn nhất thường không phải việc tạo số 1..N, mà là tạo **khung thời gian đầy đủ** để những ngày không có dữ liệu vẫn xuất hiện đúng với số đếm hoặc doanh thu bằng 0.

Một mẫu ngắn có thể nhớ:

```sql
WITH RECURSIVE calendar(day_value) AS (
    SELECT DATE '2026-11-10'
    UNION ALL
    SELECT day_value + 1
    FROM calendar
    WHERE day_value < DATE '2026-11-16'
)
SELECT day_value
FROM calendar
ORDER BY day_value;
```

Khi dùng mẫu này, cần luôn trả lời bốn câu hỏi:

1. **Sinh tập gì?** Số nguyên, ngày theo lịch, giờ địa phương hay instant?
2. **Dừng ở đâu?** Mốc cuối có được bao gồm không; khoảng rỗng xử lý thế nào?
3. **Dùng tập sinh để làm gì?** Lấp ngày thiếu, tìm khoảng trống, tạo khung cửa hàng–ngày hay tính cửa sổ?
4. **Có công cụ phù hợp hơn không?** `generate_series` cho dãy đều trong PostgreSQL, hoặc bảng lịch cho các quy tắc nghiệp vụ dùng lại.

Nếu chỉ cần dãy tăng đều, hãy chọn cách **đơn giản và hiệu quả nhất** của hệ quản trị. Nếu mỗi bước phụ thuộc kết quả bước trước, hoặc cần thể hiện quy tắc sinh có trạng thái, recursive CTE là một công cụ mạnh. Dù chọn cách nào, **định nghĩa đúng ranh giới và giới hạn quy mô** là điều kiện để truy vấn trả số liệu đầy đủ, chính xác và an toàn.

## Tài liệu tham khảo

- [PostgreSQL — WITH Queries, Recursive Queries](https://www.postgresql.org/docs/current/queries-with.html): anchor, recursive member, working table và các lưu ý xử lý truy vấn đệ quy.
- [PostgreSQL — Set Returning Functions](https://www.postgresql.org/docs/current/functions-srf.html): hàm `generate_series` cho số và timestamp.
- [PostgreSQL — Date/Time Functions and Operators](https://www.postgresql.org/docs/current/functions-datetime.html): phép cộng ngày, `EXTRACT`, timezone và các hàm thời gian.
- [SQL Server — Recursive CTE](https://learn.microsoft.com/en-us/sql/t-sql/queries/recursive-common-table-expression-transact-sql): cú pháp `WITH` đệ quy và `MAXRECURSION`.
- [MySQL — Recursive Common Table Expressions](https://dev.mysql.com/doc/refman/8.4/en/with.html): cú pháp và giới hạn đệ quy.
- [SQLite — The WITH Clause](https://www.sqlite.org/lang_with.html): truy vấn đệ quy và các dạng CTE.

