# CASE trong lọc, sắp xếp và tổng hợp dữ liệu SQL

Một câu truy vấn SQL không phải lúc nào cũng xử lý mọi dòng theo cùng một quy tắc. Đôi khi cần phân loại đơn hàng theo giá trị, ưu tiên một trạng thái khi sắp xếp, chỉ cộng doanh thu của các đơn đã thanh toán hoặc áp dụng điều kiện lọc khác nhau tùy loại bản ghi. Biểu thức **`CASE`** cho phép diễn đạt các nhánh điều kiện này ngay trong SQL.

`CASE` là **biểu thức trả về một giá trị**, không phải một cấu trúc điều khiển luồng chương trình như câu lệnh `if` trong Java. Kết quả của nó có thể đặt trong `SELECT`, `WHERE`, `ORDER BY`, `GROUP BY`, `HAVING` hoặc bên trong các hàm tổng hợp như `SUM` và `COUNT`.

Bài học tập trung vào ba ứng dụng quan trọng:

1. **Lọc:** chọn hàng theo quy tắc thay đổi tùy tình huống.
2. **Sắp xếp:** tạo khóa sắp xếp tùy chỉnh theo nghiệp vụ.
3. **Tổng hợp:** tính số lượng, tổng tiền, trung bình và nhiều chỉ tiêu có điều kiện trong cùng truy vấn.

Các ví dụ chính dùng PostgreSQL, nhưng cú pháp `CASE` cơ bản theo SQL được hỗ trợ rộng rãi ở MySQL, SQL Server, Oracle và SQLite. Cách dùng kiểu boolean, toán tử ngày giờ, hàm tổng hợp nâng cao và khả năng tối ưu có thể khác nhau theo hệ quản trị.

## 1. Hai dạng của biểu thức CASE

### 1.1. Searched CASE: kiểm tra những điều kiện độc lập

Dạng linh hoạt nhất là:

```sql
CASE
    WHEN condition_1 THEN result_1
    WHEN condition_2 THEN result_2
    WHEN condition_3 THEN result_3
    ELSE default_result
END
```

DBMS chọn **kết quả của nhánh `WHEN` đầu tiên có điều kiện là `TRUE`**. Nếu không nhánh nào đúng, sử dụng `ELSE`; nếu bỏ `ELSE`, kết quả mặc định là `NULL`. Vì vậy, thứ tự các nhánh có ý nghĩa, nhất là khi các điều kiện chồng lấn.

Ví dụ phân nhóm mức giá:

```sql
SELECT
    CASE
        WHEN 1200 >= 1000 THEN 'HIGH'
        WHEN 1200 >= 500  THEN 'MEDIUM'
        ELSE 'LOW'
    END AS price_band;
-- HIGH
```

Giá trị 1200 thỏa cả hai điều kiện, nhưng **chỉ nhánh đầu tiên** được chọn. Nếu đảo thứ tự hai nhánh, kết quả sẽ thành `MEDIUM`; vì vậy với các ngưỡng `>=`, thường kiểm tra từ mức cao xuống thấp.

### 1.2. Simple CASE: so sánh một biểu thức với nhiều giá trị

Dạng thứ hai dùng khi mỗi nhánh kiểm tra **bằng** với một giá trị cụ thể:

```sql
CASE expression
    WHEN value_1 THEN result_1
    WHEN value_2 THEN result_2
    ELSE default_result
END
```

Ví dụ:

```sql
SELECT
    CASE 'PENDING'
        WHEN 'PENDING'   THEN 'Chờ xử lý'
        WHEN 'PAID'      THEN 'Đã thanh toán'
        WHEN 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Trạng thái khác'
    END AS status_label;
-- Chờ xử lý
```

Simple `CASE` phù hợp cho việc ánh xạ mã trạng thái sang nhãn hoặc thứ tự ưu tiên. Nó không thể thay trực tiếp một nhánh chứa bất đẳng thức như `amount >= 1000` hoặc nhiều biểu thức nối bằng `AND`; trong trường hợp đó dùng searched `CASE`.

### 1.3. CASE không phải vòng lặp hay câu lệnh điều khiển

Ví dụ bên dưới tính ra một chuỗi phân loại cho **mỗi dòng**:

```sql
SELECT
    amount,
    CASE WHEN amount >= 1000 THEN 'LARGE' ELSE 'SMALL' END AS size_label
FROM orders;
```

Nó không tự tạo hai truy vấn khác nhau, không thay đổi cấu trúc bảng và không chạy một lệnh `UPDATE`/`DELETE` trong từng nhánh `THEN`. Mỗi nhánh `THEN` trả về **một biểu thức giá trị** tương thích với các nhánh còn lại.

## 2. Bộ dữ liệu mẫu xuyên suốt

Tạo bảng tạm `demo_orders` trong PostgreSQL để có thể chạy các ví dụ độc lập với hệ thống thực tế:

```sql
CREATE TEMP TABLE demo_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    region VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    priority INTEGER,
    shipped_on DATE
);

INSERT INTO demo_orders
    (order_id, customer_id, region, status, amount, priority, shipped_on)
VALUES
    (101, 1, 'NORTH',   'PAID',      1200, 1, DATE '2026-11-01'),
    (102, 2, 'SOUTH',   'PENDING',    400, 2, NULL),
    (103, 1, 'NORTH',   'CANCELLED',  900, NULL, NULL),
    (104, 3, 'SOUTH',   'PAID',       700, 3, DATE '2026-11-03'),
    (105, 4, 'CENTRAL', 'PAID',       300, NULL, DATE '2026-11-04'),
    (106, 2, 'SOUTH',   'REFUNDED',   200, 2, DATE '2026-11-05'),
    (107, 5, 'NORTH',   'PENDING',   1500, 1, NULL),
    (108, 5, 'CENTRAL', 'PAID',       600, 2, DATE '2026-11-06'),
    (109, 6, 'NORTH',   'PAID',      1000, 2, NULL),
    (110, 7, 'CENTRAL', 'CANCELLED',  500, NULL, NULL);
```

| order_id | customer_id | region | status | amount | priority | shipped_on |
|---:|---:|---|---|---:|---:|---|
| 101 | 1 | NORTH | PAID | 1200 | 1 | 2026-11-01 |
| 102 | 2 | SOUTH | PENDING | 400 | 2 | `NULL` |
| 103 | 1 | NORTH | CANCELLED | 900 | `NULL` | `NULL` |
| 104 | 3 | SOUTH | PAID | 700 | 3 | 2026-11-03 |
| 105 | 4 | CENTRAL | PAID | 300 | `NULL` | 2026-11-04 |
| 106 | 2 | SOUTH | REFUNDED | 200 | 2 | 2026-11-05 |
| 107 | 5 | NORTH | PENDING | 1500 | 1 | `NULL` |
| 108 | 5 | CENTRAL | PAID | 600 | 2 | 2026-11-06 |
| 109 | 6 | NORTH | PAID | 1000 | 2 | `NULL` |
| 110 | 7 | CENTRAL | CANCELLED | 500 | `NULL` | `NULL` |

Bảng có **10 đơn hàng**. Số đơn `PAID` là 5, `PENDING` là 2, `CANCELLED` là 2 và `REFUNDED` là 1. Tổng giá trị đơn `PAID` bằng **3800** đơn vị tiền đang được giả định trong ví dụ; không nên suy ra đây là doanh thu thực tế nếu bài toán có thuế, chiết khấu, hoàn tiền hoặc đơn vị tiền khác nhau.

Các truy vấn chọn dữ liệu sẽ dùng `ORDER BY order_id` khi cần hiển thị một thứ tự cụ thể, vì SQL không bảo đảm thứ tự dòng nếu thiếu `ORDER BY`.

## 3. Dùng CASE trong SELECT để tạo giá trị phân loại

### 3.1. Phân nhóm theo ngưỡng

Phân các đơn thành ba mức: `HIGH` nếu giá trị từ 1000 trở lên; `MEDIUM` nếu từ 500 đến dưới 1000; còn lại `LOW`.

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        WHEN amount >= 500  THEN 'MEDIUM'
        ELSE 'LOW'
    END AS amount_band
FROM demo_orders
ORDER BY order_id;
```

Kết quả theo nhóm:

| amount_band | order_id |
|---|---|
| HIGH | 101, 107, 109 |
| MEDIUM | 103, 104, 108, 110 |
| LOW | 102, 105, 106 |

Lưu ý **nhánh `WHEN amount >= 1000` phải đứng trước `WHEN amount >= 500`**. Nếu đảo lại, tất cả đơn giá trị cao cũng bị xếp vào `MEDIUM` vì chúng đã thỏa nhánh đầu tiên.

Khi các mức được định nghĩa bằng khoảng **không chồng lấn**, có thể viết rõ từng khoảng, nhưng giữ thứ tự ngưỡng giảm dần thường dễ bảo trì hơn:

```sql
CASE
    WHEN amount >= 1000 THEN 'HIGH'
    WHEN amount >= 500  THEN 'MEDIUM'
    ELSE 'LOW'
END
```

Nếu `amount` có thể `NULL`, hai điều kiện `>=` sẽ không thành `TRUE`, vì vậy dòng thiếu số tiền đi vào `ELSE 'LOW'`. Điều này chỉ đúng nghiệp vụ nếu muốn coi “không biết số tiền” là `LOW`; nếu không, cần thêm `WHEN amount IS NULL THEN 'UNKNOWN'` trước các nhánh so sánh.

### 3.2. Đặt nhãn theo trạng thái

```sql
SELECT
    order_id,
    status,
    CASE status
        WHEN 'PENDING'   THEN 'Đang chờ'
        WHEN 'PAID'      THEN 'Đã thanh toán'
        WHEN 'REFUNDED'  THEN 'Đã hoàn tiền'
        WHEN 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Khác'
    END AS status_label
FROM demo_orders
ORDER BY order_id;
```

Nhãn được tạo ngay trong kết quả; cột gốc `status` không thay đổi. Với hệ thống thực tế, có thể đặt bản dịch/nhãn hiển thị ở tầng ứng dụng nếu hỗ trợ đa ngôn ngữ hoặc bảng trạng thái có metadata; ví dụ ở đây tập trung vào cú pháp và ý nghĩa của `CASE`.

### 3.3. Kết hợp nhiều thuộc tính

Một đơn có thể cần nhãn “cần chú ý” nếu đang chờ lâu hoặc có mức ưu tiên cao. Ví dụ đơn giản không phụ thuộc ngày hiện tại:

```sql
SELECT
    order_id,
    status,
    priority,
    CASE
        WHEN status = 'PENDING' AND priority = 1
            THEN 'PENDING_URGENT'
        WHEN status = 'PENDING'
            THEN 'PENDING_NORMAL'
        WHEN status = 'PAID' AND shipped_on IS NULL
            THEN 'PAID_NOT_SHIPPED'
        ELSE 'OTHER'
    END AS action_group
FROM demo_orders
ORDER BY order_id;
```

Theo dữ liệu mẫu, ID 107 thuộc `PENDING_URGENT`, ID 102 thuộc `PENDING_NORMAL` và ID 109 thuộc `PAID_NOT_SHIPPED`. Trạng thái và mức ưu tiên được kết hợp trực tiếp trong từng điều kiện `WHEN`.

## 4. CASE trong WHERE: lọc theo nhiều quy tắc

`WHERE` cần một điều kiện logic để quyết định giữ hay loại từng hàng. `CASE` có thể **tạo ra giá trị được so sánh** trong `WHERE`, hoặc trả về một kết quả logic trong DBMS hỗ trợ kiểu boolean như PostgreSQL. Tuy nhiên, khi các điều kiện có thể viết rõ bằng `AND` và `OR`, cách đó thường dễ đọc và dễ tối ưu hơn.

### 4.1. Lọc theo ngưỡng khác nhau tùy trạng thái

Yêu cầu:

- Với đơn `PAID`, chỉ lấy đơn có `amount >= 500`.
- Với đơn `PENDING`, chỉ lấy đơn có `amount >= 1000`.
- Với các trạng thái còn lại, không lấy.

Có thể dùng searched `CASE` trả về `1` hoặc `0`:

```sql
SELECT order_id, status, amount
FROM demo_orders
WHERE
    CASE
        WHEN status = 'PAID' AND amount >= 500 THEN 1
        WHEN status = 'PENDING' AND amount >= 1000 THEN 1
        ELSE 0
    END = 1
ORDER BY order_id;
```

**Kết quả:** ID **101, 104, 107, 108, 109**.

- ID 101, 104, 108, 109 là đơn `PAID` và có số tiền đạt ít nhất 500.
- ID 107 là đơn `PENDING` và có số tiền đạt ít nhất 1000.
- ID 105 (`PAID`, 300) và ID 102 (`PENDING`, 400) bị loại; các trạng thái khác cũng bị loại.

Về logic, có thể viết trực tiếp:

```sql
SELECT order_id, status, amount
FROM demo_orders
WHERE (status = 'PAID' AND amount >= 500)
   OR (status = 'PENDING' AND amount >= 1000)
ORDER BY order_id;
```

Hai cách cho cùng tập kết quả trên mẫu này. Dạng `AND`/`OR` thường thể hiện điều kiện lọc trực tiếp và dễ cho DBMS nhận diện những predicate có thể tận dụng chỉ mục. Dùng `CASE` khi quy tắc thực sự cần phân nhánh thành một **giá trị**, hoặc khi biểu thức điều kiện sẽ được dùng lại theo một cách có chủ đích.

### 4.2. Tạo ngưỡng rồi so sánh với cột

Một cách khác là để `CASE` chọn **ngưỡng số**, thay vì chọn đúng/sai:

```sql
SELECT order_id, status, amount
FROM demo_orders
WHERE status IN ('PAID', 'PENDING')
  AND amount >= CASE status
        WHEN 'PAID' THEN 500
        WHEN 'PENDING' THEN 1000
        ELSE 999999999
      END
ORDER BY order_id;
```

Khi `status = 'PAID'`, ngưỡng là 500; khi `status = 'PENDING'`, ngưỡng là 1000. Điều kiện `status IN (...)` chặn các trạng thái ngoài phạm vi. Giá trị mặc định lớn trong `ELSE` chỉ là chi tiết phụ ở ví dụ này và không nên coi là một quy tắc nghiệp vụ. Có thể tránh giá trị giả bằng cách dùng `ELSE NULL`; khi đó phép so sánh với `NULL` không thành `TRUE`:

```sql
WHERE amount >= CASE status
    WHEN 'PAID' THEN 500
    WHEN 'PENDING' THEN 1000
    ELSE NULL
END
```

Trong `WHERE`, kết quả `UNKNOWN` sẽ bị loại. Tuy nhiên, nếu điều kiện ngoài `CASE` dễ đọc hơn và dùng được chỉ mục tốt hơn, hãy chọn cách diễn đạt trực tiếp.

### 4.3. Tham số lọc tùy chọn

Giả sử giao diện cho phép nhập `:min_amount` hoặc bỏ trống để không lọc theo số tiền. Có thể dùng:

```sql
-- :min_amount là tham số được bind bởi ứng dụng.
SELECT order_id, amount
FROM demo_orders
WHERE CASE
        WHEN :min_amount IS NULL THEN 1
        WHEN amount >= :min_amount THEN 1
        ELSE 0
      END = 1;
```

Nếu không có ngưỡng (tham số `NULL`), mọi hàng được giữ. Nếu có ngưỡng, chỉ các hàng đạt ngưỡng được giữ. Cách ngắn và thường rõ hơn:

```sql
SELECT order_id, amount
FROM demo_orders
WHERE :min_amount IS NULL
   OR amount >= :min_amount;
```

Các tham số dạng `:min_amount` chỉ là cú pháp đại diện cho giá trị được ứng dụng bind; không phải mọi giao diện SQL chạy trực tiếp đều hiểu tên tham số theo cú pháp này. Tránh nối chuỗi người dùng trực tiếp vào SQL.

### 4.4. CASE không thay thế nhóm ngoặc an toàn

Giả sử ứng dụng chỉ cho phép xem đơn của một khu vực:

```sql
-- Điều kiện khu vực áp dụng cho MỌI nhánh lọc.
SELECT order_id
FROM demo_orders
WHERE region = :authorized_region
  AND (
       (status = 'PAID' AND amount >= 500)
       OR (status = 'PENDING' AND amount >= 1000)
  );
```

Dù lựa chọn `CASE` hay `AND`/`OR`, phải bảo đảm điều kiện phạm vi quyền truy cập được áp cho toàn bộ kết quả. Dấu ngoặc không chỉ giúp đọc mà còn ngăn việc một nhánh `OR` nằm ngoài kiểm soát khu vực hoặc tenant.

## 5. CASE trong ORDER BY: sắp xếp theo ưu tiên nghiệp vụ

`ORDER BY` mặc định sắp theo giá trị biểu thức, chẳng hạn chữ cái hoặc số tăng/giảm. Nhưng thứ tự nghiệp vụ của các trạng thái thường **không trùng thứ tự chữ cái**.

Giả sử giao diện cần ưu tiên:

1. `PENDING` — đang chờ xử lý.
2. `PAID` — đã thanh toán.
3. `REFUNDED` — đã hoàn tiền.
4. `CANCELLED` — đã hủy.
5. Trạng thái khác, nếu có, ở cuối.

### 5.1. Tạo thứ tự tùy chỉnh bằng simple CASE

```sql
SELECT order_id, status, priority
FROM demo_orders
ORDER BY
    CASE status
        WHEN 'PENDING'   THEN 0
        WHEN 'PAID'      THEN 1
        WHEN 'REFUNDED'  THEN 2
        WHEN 'CANCELLED' THEN 3
        ELSE 4
    END ASC,
    order_id ASC;
```

Với dữ liệu mẫu, thứ tự `order_id` là:

```text
PENDING   : 102, 107
PAID      : 101, 104, 105, 108, 109
REFUNDED  : 106
CANCELLED : 103, 110

Toàn bộ: 102, 107, 101, 104, 105, 108, 109, 106, 103, 110
```

Các số 0–4 chỉ là **khóa sắp xếp tạm trong truy vấn**, không thay đổi dữ liệu `status`. Thêm `order_id` ở cuối để thứ tự giữa các dòng cùng trạng thái được xác định, đặc biệt quan trọng khi dùng `LIMIT`/`OFFSET` để phân trang.

### 5.2. Kết hợp thứ tự trạng thái, mức ưu tiên và NULL

Yêu cầu nâng cao:

- Nhóm trạng thái theo thứ tự trên.
- Trong từng nhóm, `priority` nhỏ hơn đứng trước.
- `priority IS NULL` đứng cuối nhóm.
- Nếu các khóa trước giống nhau, `order_id` tăng dần.

Có thể dùng `CASE` bổ sung để xếp `NULL`, tránh phụ thuộc mặc định của DBMS:

```sql
SELECT order_id, status, priority
FROM demo_orders
ORDER BY
    CASE status
        WHEN 'PENDING' THEN 0
        WHEN 'PAID' THEN 1
        WHEN 'REFUNDED' THEN 2
        WHEN 'CANCELLED' THEN 3
        ELSE 4
    END,
    CASE WHEN priority IS NULL THEN 1 ELSE 0 END,
    priority ASC,
    order_id ASC;
```

Thứ tự ID:

```text
107, 102, 101, 108, 109, 104, 105, 106, 103, 110
```

Trong nhóm `PENDING`, ID 107 ưu tiên 1 đứng trước ID 102 ưu tiên 2. Trong nhóm `PAID`, ưu tiên 1 (101) rồi 2 (108, 109), 3 (104), cuối cùng là `NULL` (105). Nhóm `CANCELLED` gồm hai dòng có `priority NULL` nên tiếp tục phân định bằng ID.

**Vì sao cần `CASE WHEN priority IS NULL THEN 1 ELSE 0 END`?** PostgreSQL/Oracle thường đặt `NULL` cuối khi `ASC`, nhưng SQL Server/MySQL/SQLite theo mặc định thường đặt `NULL` đầu. Biểu thức `CASE` thể hiện ý định nhất quán giữa các phương ngữ. Trên DBMS hỗ trợ `NULLS LAST`, có thể dùng `priority ASC NULLS LAST` thay cho phần `CASE` xếp `NULL`.

### 5.3. Phân cấp ưu tiên đặc biệt cho một nhóm

Giả sử muốn hiển thị **đơn chờ có mức ưu tiên 1** lên trước tất cả, sau đó là các đơn chờ khác, rồi các trạng thái còn lại:

```sql
SELECT order_id, status, priority
FROM demo_orders
ORDER BY
    CASE
        WHEN status = 'PENDING' AND priority = 1 THEN 0
        WHEN status = 'PENDING' THEN 1
        WHEN status = 'PAID' THEN 2
        WHEN status = 'REFUNDED' THEN 3
        WHEN status = 'CANCELLED' THEN 4
        ELSE 5
    END,
    order_id;
```

Nhánh đặc biệt phải đứng **trước** nhánh `WHEN status = 'PENDING'`. Nếu đảo ngược, đơn chờ ưu tiên 1 đã khớp nhánh tổng quát và không bao giờ vào nhánh đặc biệt.

### 5.4. CASE trong ORDER BY và phân trang

`CASE` chỉ tạo thứ tự nhóm, không bảo đảm thứ tự các dòng đồng hạng. Nếu phân trang theo trạng thái và ưu tiên nhưng không có khóa phụ duy nhất, DBMS có thể trả các dòng cùng thứ hạng theo thứ tự khác giữa những lần truy vấn.

```sql
-- Có khóa phụ duy nhất.
SELECT order_id, status
FROM demo_orders
ORDER BY
    CASE status
        WHEN 'PENDING' THEN 0
        WHEN 'PAID' THEN 1
        ELSE 2
    END,
    order_id
LIMIT 5 OFFSET 0;
```

`LIMIT/OFFSET` phù hợp PostgreSQL/MySQL/SQLite; SQL Server dùng `OFFSET ... FETCH` với cú pháp riêng. Dù có thứ tự ổn định cho cùng một trạng thái dữ liệu, phân trang bằng offset vẫn có thể bị dịch khi dữ liệu được thêm/xóa hoặc thay đổi trạng thái giữa hai lần tải trang.

### 5.5. Sắp theo ngày giao hàng, chưa giao cuối

```sql
SELECT order_id, shipped_on
FROM demo_orders
ORDER BY
    CASE WHEN shipped_on IS NULL THEN 1 ELSE 0 END,
    shipped_on DESC,
    order_id ASC;
```

Kết quả ID là **108, 106, 105, 104, 101, 102, 103, 107, 109, 110**. Các ngày giao có giá trị được xếp từ mới đến cũ; các dòng `NULL` nằm cuối. Đây cũng là ví dụ cho thấy `CASE` trong `ORDER BY` có thể điều khiển **vị trí dữ liệu thiếu** mà không biến `NULL` thành ngày giả.

## 6. CASE trong GROUP BY: tạo nhóm tính toán

`CASE` có thể phân loại mỗi dòng trước khi gom nhóm. Với các mức giá ở phần 3:

```sql
SELECT
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        WHEN amount >= 500 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS amount_band,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM demo_orders
GROUP BY
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        WHEN amount >= 500 THEN 'MEDIUM'
        ELSE 'LOW'
    END
ORDER BY amount_band;
```

Trong nhiều DBMS, việc tham chiếu lại biểu thức phân nhóm trong `ORDER BY` có thể viết gọn bằng alias hoặc dùng CTE. Cách sáng sủa và thường dễ mở rộng hơn là tính nhãn **một lần ở lớp truy vấn dưới**:

```sql
WITH classified AS (
    SELECT
        order_id,
        amount,
        CASE
            WHEN amount >= 1000 THEN 'HIGH'
            WHEN amount >= 500 THEN 'MEDIUM'
            ELSE 'LOW'
        END AS amount_band
    FROM demo_orders
)
SELECT
    amount_band,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM classified
GROUP BY amount_band
ORDER BY
    CASE amount_band
        WHEN 'HIGH' THEN 1
        WHEN 'MEDIUM' THEN 2
        ELSE 3
    END;
```

Kết quả:

| amount_band | order_count | total_amount |
|---|---:|---:|
| HIGH | 3 | 3700 |
| MEDIUM | 4 | 2700 |
| LOW | 3 | 900 |

Các phép cộng minh họa: `HIGH = 1200 + 1500 + 1000 = 3700`; `MEDIUM = 900 + 700 + 600 + 500 = 2700`; `LOW = 400 + 300 + 200 = 900`. Tổng tất cả đơn trong bảng là 7300.

**Lưu ý:** `GROUP BY` theo alias trong cùng tầng truy vấn có thể khác biệt giữa phương ngữ; dùng CTE như ví dụ giúp tách rõ bước phân loại và bước tổng hợp. Đồng thời, nếu thay đổi quy tắc phân nhóm, chỉ cần sửa biểu thức trong CTE.

## 7. CASE bên trong SUM: tổng hợp có điều kiện

Đây là một trong những ứng dụng quan trọng nhất của `CASE`. Hàm `SUM` cộng các giá trị được truyền vào; `CASE` quyết định mỗi dòng góp bao nhiêu vào tổng.

### 7.1. Tổng số tiền của đơn PAID

```sql
SELECT
    SUM(
        CASE WHEN status = 'PAID' THEN amount ELSE 0 END
    ) AS paid_amount
FROM demo_orders;
-- 3800
```

Với từng hàng:

- Nếu `status = 'PAID'`, trả về `amount` để cộng.
- Nếu trạng thái khác, trả về `0` để không đóng góp vào tổng.
- Kết quả: `1200 + 700 + 300 + 600 + 1000 = 3800`.

Có thể đọc như “với mỗi đơn, nếu đã thanh toán thì lấy số tiền, nếu chưa thì lấy 0; sau đó cộng toàn bộ”. Đây là **conditional aggregation** (tổng hợp có điều kiện).

### 7.2. Tổng nhiều trạng thái trong một lượt nhóm

```sql
SELECT
    region,
    COUNT(*) AS all_orders,
    SUM(CASE WHEN status = 'PAID'
             THEN amount ELSE 0 END) AS paid_amount,
    SUM(CASE WHEN status = 'PENDING'
             THEN amount ELSE 0 END) AS pending_amount,
    SUM(CASE WHEN status = 'CANCELLED'
             THEN amount ELSE 0 END) AS cancelled_amount
FROM demo_orders
GROUP BY region
ORDER BY region;
```

Kết quả:

| region | all_orders | paid_amount | pending_amount | cancelled_amount |
|---|---:|---:|---:|---:|
| CENTRAL | 3 | 900 | 0 | 500 |
| NORTH | 4 | 2200 | 1500 | 900 |
| SOUTH | 3 | 700 | 400 | 0 |

Trong ví dụ, đơn `REFUNDED` 106 không cộng vào bất kỳ cột tiền trạng thái nào ở trên. Nếu muốn báo cáo doanh thu thuần, cần **định nghĩa nghiệp vụ** về hoàn tiền, giảm giá, thuế và loại tiền; bảng trên chỉ cho thấy cách tách số tiền theo mã trạng thái.

### 7.3. Có ELSE 0 và không có ELSE khác nhau thế nào?

So sánh:

```sql
SELECT
    SUM(CASE WHEN status = 'PAID'
             THEN amount ELSE 0 END) AS paid_sum_with_zero,
    SUM(CASE WHEN status = 'PAID'
             THEN amount END) AS paid_sum_without_else
FROM demo_orders;
```

Với bảng có đơn `PAID`, cả hai trả 3800. Nhưng nếu một nhóm **không có bất kỳ đơn `PAID` nào**, biểu thức không có `ELSE` tạo toàn `NULL` và `SUM` trên các đầu vào chỉ `NULL` trả về **`NULL`**, còn biểu thức có `ELSE 0` trả về **0** nếu nhóm có hàng.

Ví dụ rõ ràng:

```sql
SELECT
    SUM(CASE WHEN status = 'UNKNOWN'
             THEN amount ELSE 0 END) AS sum_zero,
    SUM(CASE WHEN status = 'UNKNOWN'
             THEN amount END) AS sum_null
FROM demo_orders;
-- sum_zero = 0; sum_null = NULL
```

Với **bảng hoàn toàn rỗng**, cả `SUM` đều trả `NULL` vì không có đầu vào để tổng hợp, kể cả khi biểu thức có `ELSE 0`. Nếu cần luôn trả 0 trong trường hợp đó, dùng `COALESCE(SUM(...), 0)` theo ngữ nghĩa báo cáo.

## 8. CASE bên trong COUNT: đếm có điều kiện

`COUNT(*)` đếm tất cả hàng, còn `COUNT(expression)` chỉ đếm những hàng có biểu thức **khác `NULL`**.

### 8.1. Đếm các đơn đã thanh toán

```sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_orders,
    COUNT(CASE WHEN status = 'PENDING' THEN 1 END) AS pending_orders,
    COUNT(CASE WHEN status = 'CANCELLED' THEN 1 END) AS cancelled_orders
FROM demo_orders;
```

Kết quả:

| total_orders | paid_orders | pending_orders | cancelled_orders |
|---:|---:|---:|---:|
| 10 | 5 | 2 | 2 |

Lý do `COUNT(CASE WHEN ... THEN 1 END)` đúng: khi điều kiện không đúng, `CASE` không có `ELSE` trả về `NULL` nên `COUNT` bỏ qua.

**Lỗi phổ biến:**

```sql
-- KHÔNG dùng dạng này để đếm riêng PAID:
COUNT(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
```

Vì cả `1` và `0` đều **khác `NULL`**, `COUNT` sẽ đếm **toàn bộ 10 dòng**, không phải 5. Dùng một trong hai dạng:

```sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)
SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
```

Trong nhóm có ít nhất một hàng, hai biểu thức thường cho cùng số lượng khi `status` xác định. Tuy nhiên, trên **tập đầu vào rỗng**, `COUNT` trả 0 trong khi `SUM` trả `NULL` nếu không có `COALESCE`.

### 8.2. Đếm khách hàng khác nhau theo điều kiện

Có thể kết hợp `DISTINCT` với `CASE`:

```sql
SELECT
    COUNT(DISTINCT CASE
        WHEN status = 'PAID' THEN customer_id
    END) AS customers_with_paid_orders
FROM demo_orders;
-- 5
```

Trong dữ liệu mẫu, các khách hàng có đơn `PAID` là ID **1, 3, 4, 5, 6**. Khách hàng 1 chỉ được đếm một lần dù có thể xuất hiện trong các trạng thái khác; khách hàng 5 cũng được đếm một lần dù có nhiều đơn.

Nếu muốn đếm **tất cả khách hàng từng xuất hiện**, dùng `COUNT(DISTINCT customer_id)`, kết quả là 7. Hai câu hỏi nghiệp vụ khác nhau và hai biểu thức trả lời những câu hỏi khác nhau.

### 8.3. Điều kiện tổng hợp có NULL

Giả sử muốn đếm đơn **chưa có mức ưu tiên**:

```sql
SELECT
    COUNT(CASE WHEN priority IS NULL THEN 1 END)
        AS orders_without_priority
FROM demo_orders;
-- 3
```

Ba dòng có `priority IS NULL` là 103, 105 và 110. Cần dùng `IS NULL`, không phải `priority = NULL`, vì so sánh bằng với `NULL` cho kết quả logic `UNKNOWN`.

## 9. CASE trong AVG: trung bình của đúng tập cần đo

Đây là nơi dễ xảy ra sai lệch mẫu số.

Mục tiêu: “Giá trị đơn hàng trung bình **của các đơn PAID**.”

```sql
SELECT
    AVG(CASE WHEN status = 'PAID' THEN amount END)
        AS avg_paid_amount
FROM demo_orders;
-- 760
```

Có 5 đơn `PAID` với tổng 3800 nên trung bình là **3800 / 5 = 760**. Các đơn không `PAID` tạo `NULL` nên `AVG` bỏ qua, không đưa chúng vào mẫu số.

Nếu viết:

```sql
SELECT
    AVG(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
        AS paid_amount_per_all_order
FROM demo_orders;
-- 380
```

thì mẫu số là **10 dòng** (các đơn không `PAID` đóng góp số 0), cho kết quả **3800 / 10 = 380**. Điều này có thể đúng nếu chỉ tiêu muốn đo là “số tiền `PAID` bình quân trên **mọi đơn hàng**”, nhưng **không phải giá trị bình quân của các đơn `PAID`**.

Khi dùng `AVG(CASE ...)`, phải xác định:

- Nhánh không thỏa điều kiện cần trả `NULL` để **không tham gia trung bình** hay trả `0` để **tham gia mẫu số với giá trị 0**?
- Nếu cột `amount` có thể `NULL`, có cần loại khỏi mẫu số hay coi là 0?
- Nếu không có hàng hợp lệ, có muốn `AVG` trả `NULL` để biểu thị “không đủ dữ liệu” hay cố tình thay bằng 0 ở lớp báo cáo?

Những lựa chọn này ảnh hưởng ngữ nghĩa thống kê, không chỉ cú pháp.

## 10. Tổng hợp có điều kiện theo nhiều chiều

### 10.1. Bảng báo cáo kiểu pivot

Có thể biến các mã trạng thái ở nhiều hàng thành các **cột chỉ tiêu** cho từng khu vực:

```sql
SELECT
    region,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END)
        AS pending_count,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS paid_count,
    SUM(CASE WHEN status = 'REFUNDED' THEN 1 ELSE 0 END)
        AS refunded_count,
    SUM(CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END)
        AS cancelled_count
FROM demo_orders
GROUP BY region
ORDER BY region;
```

Kết quả:

| region | total_orders | pending_count | paid_count | refunded_count | cancelled_count |
|---|---:|---:|---:|---:|---:|
| CENTRAL | 3 | 0 | 2 | 0 | 1 |
| NORTH | 4 | 1 | 2 | 0 | 1 |
| SOUTH | 3 | 1 | 1 | 1 | 0 |

Nếu các trạng thái loại trừ nhau và toàn bộ tập trạng thái đã được liệt kê, tổng các cột đếm trạng thái bằng `total_orders`. Nếu hệ thống bổ sung trạng thái mới mà truy vấn chưa cập nhật, tổng có thể nhỏ hơn `total_orders`; đó là lý do cần quản lý tập mã trạng thái nhất quán.

### 10.2. Tỷ lệ đơn PAID trên toàn bộ đơn

```sql
SELECT
    region,
    COUNT(*) AS total_orders,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        AS paid_orders,
    100.0 * SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS paid_percentage
FROM demo_orders
GROUP BY region
ORDER BY region;
```

Kết quả xấp xỉ:

| region | total_orders | paid_orders | paid_percentage |
|---|---:|---:|---:|
| CENTRAL | 3 | 2 | 66.67 |
| NORTH | 4 | 2 | 50.00 |
| SOUTH | 3 | 1 | 33.33 |

`100.0` giúp phép chia giữ phần thập phân trong những DBMS có phân biệt phép chia số nguyên; `NULLIF(COUNT(*), 0)` ngăn mẫu số bằng 0 khi cấu trúc truy vấn có khả năng trả nhóm rỗng. Cách hiển thị và làm tròn tỷ lệ thực tế tùy kiểu số và DBMS.

### 10.3. Chỉ lấy các nhóm đạt mục tiêu bằng HAVING

Yêu cầu: “Chỉ hiển thị những khu vực có **tổng giá trị đơn PAID ít nhất 1000**.”

```sql
SELECT
    region,
    SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
        AS paid_amount
FROM demo_orders
GROUP BY region
HAVING SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END) >= 1000
ORDER BY region;
```

**Kết quả:** chỉ `NORTH` với `paid_amount = 2200`. `CENTRAL` có 900, `SOUTH` có 700 nên không đạt ngưỡng.

`WHERE` lọc **từng dòng trước khi nhóm**, còn `HAVING` lọc **nhóm sau khi tính tổng hợp**. Dùng `CASE` trong `SUM` giúp tính chỉ tiêu theo trạng thái mà vẫn có thể giữ tất cả dòng cho các chỉ tiêu khác như `COUNT(*)`.

## 11. Phân biệt WHERE và CASE bên trong hàm tổng hợp

Hai truy vấn sau thường bị hiểu nhầm là tương đương:

```sql
-- A: lọc PAID trước khi nhóm.
SELECT
    region,
    COUNT(*) AS rows_after_filter,
    SUM(amount) AS paid_sum
FROM demo_orders
WHERE status = 'PAID'
GROUP BY region;

-- B: giữ mọi đơn để tính các chỉ tiêu khác,
-- nhưng chỉ cộng amount của PAID.
SELECT
    region,
    COUNT(*) AS all_orders,
    SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
        AS paid_sum
FROM demo_orders
GROUP BY region;
```

Ở ví dụ A, `COUNT(*)` là **số đơn `PAID`** vì các trạng thái khác đã bị `WHERE` loại. Ở ví dụ B, `COUNT(*)` là **tất cả đơn** của khu vực, còn `paid_sum` chỉ cộng tiền `PAID`.

Dùng `WHERE` nếu **mọi chỉ tiêu** đều chỉ cần một tập dòng đã lọc. Dùng `CASE` bên trong hàm tổng hợp khi muốn tính **nhiều chỉ tiêu trên những tập con khác nhau** trong cùng một truy vấn nhóm.

Ví dụ chỉ cần một truy vấn cho cả doanh thu đơn PAID và số đơn chờ:

```sql
SELECT
    region,
    COUNT(*) AS all_orders,
    SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
        AS paid_amount,
    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END)
        AS pending_count
FROM demo_orders
GROUP BY region;
```

Nếu đặt `WHERE status = 'PAID'` ở truy vấn này, `pending_count` sẽ luôn bằng 0, làm mất ý nghĩa chỉ tiêu.

## 12. FILTER so với CASE trong tổng hợp

Một số DBMS hỗ trợ cú pháp `FILTER (WHERE ...)` cho từng hàm tổng hợp, ví dụ PostgreSQL:

```sql
-- PostgreSQL
SELECT
    region,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    SUM(amount) FILTER (WHERE status = 'PAID') AS paid_amount
FROM demo_orders
GROUP BY region
ORDER BY region;
```

Cú pháp này diễn đạt điều kiện ngay trên phép tổng hợp. Hai biểu thức thường được so với:

```sql
COUNT(CASE WHEN status = 'PAID' THEN 1 END)

SUM(CASE WHEN status = 'PAID' THEN amount END)
```

**Lưu ý:** `SUM(amount) FILTER (...)` có thể trả `NULL` nếu không có giá trị phù hợp để cộng, tương tự `SUM(CASE ... THEN amount END)`; nó khác với `SUM(CASE ... THEN amount ELSE 0 END)` khi một nhóm có hàng nhưng không có đơn `PAID`. Với báo cáo cần hiển thị 0, có thể dùng `COALESCE(..., 0)`.

`FILTER` được hỗ trợ ở PostgreSQL và một số hệ khác, nhưng **không phải cú pháp portable trên mọi phiên bản MySQL hoặc SQL Server**. `SUM(CASE WHEN ... THEN ... ELSE ... END)` thường là phương án dễ chuyển DBMS hơn. Không nên tự kết luận `FILTER` hay `CASE` luôn nhanh hơn; bộ tối ưu và cấu trúc dữ liệu quyết định kế hoạch thực tế.

## 13. NULL và logic ba giá trị trong CASE

### 13.1. WHEN chỉ chọn nhánh nếu điều kiện là TRUE

Với searched `CASE`, nếu biểu thức `WHEN` có kết quả `FALSE` **hoặc `UNKNOWN`**, DBMS sẽ xét nhánh tiếp theo. Vì `NULL` tạo `UNKNOWN` trong nhiều phép so sánh, nên cần xử lý trường hợp thiếu giá trị tường minh.

```sql
SELECT
    order_id,
    priority,
    CASE
        WHEN priority = 1 THEN 'URGENT'
        WHEN priority > 1 THEN 'NORMAL'
        ELSE 'UNSPECIFIED'
    END AS priority_label
FROM demo_orders
ORDER BY order_id;
```

Với ID 103, 105, 110 có `priority NULL`, hai điều kiện `priority = 1` và `priority > 1` đều `UNKNOWN` nên chúng được gán `UNSPECIFIED`.

Có thể diễn đạt rõ hơn:

```sql
CASE
    WHEN priority IS NULL THEN 'UNSPECIFIED'
    WHEN priority = 1 THEN 'URGENT'
    ELSE 'NORMAL'
END
```

Nếu nghiệp vụ phân biệt ưu tiên bằng 0, âm hoặc các mức không hợp lệ, các giá trị đó cũng cần quy tắc riêng thay vì mặc định gom vào `NORMAL`.

### 13.2. Bẫy CASE expression WHEN NULL

Đoạn sau **không phát hiện `NULL`** theo ý định:

```sql
SELECT
    priority,
    CASE priority
        WHEN NULL THEN 'UNKNOWN'
        ELSE 'KNOWN'
    END AS priority_state
FROM demo_orders;
```

Vì simple `CASE` dùng phép so sánh tương đương `=` giữa biểu thức và các giá trị nhánh, `NULL` không khớp `WHEN NULL`. Hàng có `priority NULL` cũng đi vào `ELSE 'KNOWN'`, trái mong muốn.

Cách đúng là searched `CASE` kết hợp `IS NULL`:

```sql
SELECT
    priority,
    CASE
        WHEN priority IS NULL THEN 'UNKNOWN'
        ELSE 'KNOWN'
    END AS priority_state
FROM demo_orders;
```

### 13.3. Không có ELSE là NULL

```sql
SELECT
    order_id,
    CASE
        WHEN status = 'PAID' THEN amount
    END AS paid_only_amount
FROM demo_orders
ORDER BY order_id;
```

Các đơn không `PAID` có `paid_only_amount = NULL`. Điều này hữu ích khi đặt biểu thức trong `COUNT` hoặc `AVG` để loại khỏi phép tính, nhưng có thể gây bất ngờ nếu dùng như số tiền mặc định trong màn hình. Hãy thêm `ELSE 0` chỉ khi 0 là giá trị hợp lý về nghiệp vụ.

## 14. Kiểu dữ liệu của các nhánh CASE

Các nhánh `THEN` và `ELSE` cần tạo ra **kiểu kết quả tương thích** theo quy tắc chuyển kiểu của DBMS. Không nên mặc định có thể trả chuỗi, số, ngày và boolean tùy tiện trong cùng `CASE`.

Ví dụ đúng:

```sql
SELECT
    CASE
        WHEN amount >= 1000 THEN 0.10
        ELSE 0.05
    END AS discount_rate
FROM demo_orders;
```

Hai nhánh là các số tương thích để diễn đạt tỷ lệ. Một ví dụ dễ phát sinh lỗi hoặc ép kiểu ngoài ý định:

```sql
-- Tránh trộn ý nghĩa số và chuỗi trong cùng cột kết quả.
CASE
    WHEN amount >= 1000 THEN amount
    ELSE 'N/A'
END
```

PostgreSQL có thể cố ép `'N/A'` sang kiểu số và báo lỗi. Một hệ khác có thể ép cả hai nhánh sang chuỗi, dẫn tới việc so sánh hoặc cộng tổng không còn như mong muốn.

Nếu muốn cả giá trị số và thông báo thiếu, có thể:

- Giữ một cột `amount` kiểu số, cho phép `NULL` khi chưa biết.
- Tạo cột trạng thái hiển thị riêng bằng `CASE`.
- Chỉ chuyển số thành chuỗi ở tầng hiển thị nếu cần, với định dạng có kiểm soát.

Ví dụ:

```sql
SELECT
    order_id,
    amount,
    CASE
        WHEN amount >= 1000 THEN 'HIGH_VALUE'
        ELSE 'STANDARD'
    END AS amount_category
FROM demo_orders;
```

Cũng cần cẩn trọng với `ELSE NULL`: DBMS sẽ suy ra kiểu từ các nhánh còn lại hoặc ngữ cảnh; có thể dùng `CAST` khi cần đảm bảo kiểu đầu ra rõ ràng, nhất là trong `UNION`, view hoặc API có hợp đồng kiểu chặt.

## 15. CASE không bảo đảm thứ tự đánh giá mọi biểu thức

Một cách hiểu thường gặp là `CASE` luôn “ngừng chạy” hoàn toàn sau nhánh phù hợp và có thể dùng để bao bọc bất kỳ phép toán nguy hiểm nào. Trong các DBMS, quy tắc lựa chọn **kết quả nhánh** được bảo đảm theo ngữ nghĩa `CASE`, nhưng bộ tối ưu có thể tính sớm một số **biểu thức con**, hằng số hoặc phép tổng hợp trước khi `CASE` chọn kết quả.

Ví dụ không nên xem `CASE` là lá chắn tuyệt đối cho phép chia cho 0 trong mọi trường hợp:

```sql
-- Ví dụ phân tích ý nghĩa; không dựa vào CASE để bảo vệ
-- mọi phép tổng hợp hoặc biểu thức được tính trước.
SELECT
    CASE
        WHEN MIN(denominator) = 0 THEN 0
        ELSE SUM(numerator / denominator)
    END
FROM measurements;
```

Ở PostgreSQL, giá trị của hàm tổng hợp có thể được tính trước khi `CASE` ở tầng ngoài chọn nhánh, nên phép chia cho 0 vẫn có thể gây lỗi. Cách thiết kế tốt là bảo vệ **ngay tại phép chia** khi nghiệp vụ xác định không thể chia cho 0:

```sql
SELECT
    SUM(numerator / NULLIF(denominator, 0))
        AS safe_ratio_sum
FROM measurements;
```

`NULLIF(denominator, 0)` tạo `NULL` khi mẫu số bằng 0; phép chia tạo `NULL` và `SUM` bỏ qua các giá trị `NULL`. Đây chỉ đúng nếu nghiệp vụ cho phép **bỏ qua** những mẫu số bằng 0; có thể cần báo lỗi, đếm riêng lỗi dữ liệu hoặc xử lý theo quy tắc khác.

Không nên dùng `CASE` để thay thế việc kiểm tra dữ liệu đầu vào, ràng buộc `CHECK` hoặc quy tắc chuyển kiểu an toàn. Tương tự, dù biểu thức điều kiện được viết theo thứ tự nào trong `WHERE`, DBMS vẫn có thể tối ưu thứ tự đánh giá; không dựa vào “short-circuit” ngầm giữa các predicate để tránh lỗi ép kiểu.

## 16. CASE và hiệu năng truy vấn

`CASE` rất linh hoạt nhưng cũng có thể khiến truy vấn phức tạp hơn và ảnh hưởng khả năng dùng chỉ mục trong một số tình huống.

### 16.1. Đặt CASE ở WHERE hay diễn đạt predicate trực tiếp?

Ví dụ lọc đã thanh toán, số tiền từ 500:

```sql
-- Có CASE:
SELECT order_id
FROM demo_orders
WHERE CASE
        WHEN status = 'PAID' AND amount >= 500 THEN 1
        ELSE 0
      END = 1;

-- Predicate trực tiếp:
SELECT order_id
FROM demo_orders
WHERE status = 'PAID'
  AND amount >= 500;
```

Truy vấn thứ hai thường dễ hiểu và tạo điều kiện để optimizer xét chỉ mục trên `status` hoặc `(status, amount)`. Truy vấn thứ nhất buộc DBMS xem xét kết quả một biểu thức `CASE`, có thể cần chỉ mục biểu thức hoặc một bước tính thêm.

Không khẳng định mọi truy vấn chứa `CASE` trong `WHERE` đều chậm: hiệu năng phụ thuộc DBMS, thống kê, phân bố giá trị, chỉ mục và kế hoạch. Khi cần tối ưu, dùng công cụ như `EXPLAIN` trên tập dữ liệu đại diện.

### 16.2. CASE trong ORDER BY có thể cần sắp xếp

```sql
SELECT order_id, status
FROM demo_orders
ORDER BY
    CASE status
        WHEN 'PENDING' THEN 0
        WHEN 'PAID' THEN 1
        ELSE 2
    END,
    order_id;
```

Thứ tự sắp xếp là **giá trị tính từ trạng thái**, không phải thứ tự chữ cái của cột `status`. Một chỉ mục bình thường trên `status` chưa chắc phục vụ trực tiếp đúng thứ tự này. Trên PostgreSQL có thể cân nhắc chỉ mục biểu thức khi truy vấn lặp lại rất nhiều và dữ liệu đủ lớn, nhưng cần cân bằng chi phí cập nhật chỉ mục và khả năng thay đổi thứ tự nghiệp vụ.

Nếu thứ tự trạng thái là cấu hình dùng rộng rãi hoặc có thể chỉnh sửa, một bảng danh mục `order_statuses(status_code, display_rank, ...)` cùng phép `JOIN` có thể thích hợp hơn việc lặp cùng biểu thức `CASE` trên nhiều truy vấn.

### 16.3. CASE trong tổng hợp và số lượt quét

Tổng hợp nhiều điều kiện bằng `SUM(CASE ...)` giúp tính nhiều chỉ tiêu trong cùng phép nhóm, nhưng số lượng biểu thức có thể ảnh hưởng chi phí CPU và độ phức tạp bảo trì. Chỉ số tốt phải đi kèm quy tắc rõ: mỗi trạng thái có được loại trừ nhau không, dữ liệu `NULL` được tính thế nào và có cần nhóm theo vùng/đơn vị tiền không?

Nếu báo cáo cần hàng trăm trạng thái động, việc tạo hàng trăm cột `CASE` thủ công có thể không còn hợp lý. Cân nhắc báo cáo theo hàng (`GROUP BY region, status`), pivot có kiểm soát hoặc tầng báo cáo riêng tùy yêu cầu.

## 17. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Đặt nhánh ngưỡng `>= 500` trước `>= 1000` | Giá trị cao bị xếp thành MEDIUM | Kiểm tra điều kiện cụ thể hơn trước |
| Nghĩ simple `CASE col WHEN NULL` bắt được `NULL` | Dòng thiếu giá trị không khớp | Dùng `CASE WHEN col IS NULL` |
| Bỏ `ELSE` nhưng tưởng mặc định là 0 | `SUM`/cột hiển thị có thể trả `NULL` | Quyết định rõ ngữ nghĩa của `ELSE` |
| Dùng `COUNT(CASE ... THEN 1 ELSE 0 END)` để đếm điều kiện | Đếm toàn bộ hàng vì 0 cũng khác NULL | Dùng `COUNT(CASE ... THEN 1 END)` hoặc `SUM(CASE ... THEN 1 ELSE 0 END)` |
| Dùng `AVG(CASE ... THEN amount ELSE 0 END)` cho “trung bình của nhóm khớp” | Mẫu số gồm cả hàng không khớp, kết quả bị thấp | Bỏ `ELSE` để những hàng không khớp trả NULL |
| Đặt `WHERE status='PAID'` trong báo cáo cần đếm cả PENDING | Các hàng PENDING bị loại trước khi nhóm | Dùng CASE bên trong SUM/COUNT |
| Dùng `CASE` để điều khiển thứ tự trạng thái mà không có khóa phụ | Kết quả phân trang không ổn định giữa các dòng đồng hạng | Thêm khóa duy nhất vào ORDER BY |
| Dùng `CASE` trộn số với chuỗi `'N/A'` | Lỗi ép kiểu hoặc kết quả kiểu ngoài ý muốn | Tách cột giá trị và nhãn |
| Dùng `CASE` để che phép chia/ép kiểu có thể lỗi | Một số biểu thức có thể được tính trước nhánh | Bảo vệ tại phép toán, kiểm tra dữ liệu |
| Giấu toàn bộ predicate trong `CASE` khi `AND`/`OR` đủ rõ | Khó đọc và có thể khó tận dụng chỉ mục | Viết điều kiện trực tiếp khi phù hợp |
| Cho rằng SQL `CASE` giống `switch` có `break` | Hiểu sai giá trị/luồng xử lý | Nhớ rằng CASE trả một giá trị từ nhánh phù hợp đầu tiên |
| Dùng thứ tự CASE cố định cho quy tắc thay đổi thường xuyên | Khó đồng bộ nhiều truy vấn | Cân nhắc bảng danh mục thứ tự hoặc một lớp biểu thức chung |

## 18. Bài tập thực hành

### Bài 1. Phân nhóm số tiền

**Yêu cầu:** tạo cột `amount_band` với quy tắc: từ 1000 trở lên là `HIGH`; từ 500 đến dưới 1000 là `MEDIUM`; dưới 500 là `LOW`.

**Đáp án:**

```sql
SELECT
    order_id,
    CASE
        WHEN amount >= 1000 THEN 'HIGH'
        WHEN amount >= 500 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS amount_band
FROM demo_orders;
```

Số đơn từng nhóm: `HIGH = 3`, `MEDIUM = 4`, `LOW = 3`.

### Bài 2. Đếm số đơn PAID bằng CASE

**Yêu cầu:** viết hai cách đếm đơn `PAID`.

**Đáp án:**

```sql
SELECT
    COUNT(CASE WHEN status = 'PAID' THEN 1 END) AS paid_count_1,
    SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END) AS paid_count_2
FROM demo_orders;
```

Cả hai bằng **5** với bảng mẫu. Trong tình huống bảng rỗng, `COUNT` trả 0 còn `SUM` trả `NULL` trừ khi dùng `COALESCE`.

### Bài 3. Tổng PAID theo khu vực

**Yêu cầu:** tính tổng giá trị `PAID` cho từng `region` và giữ cả những vùng có trạng thái khác.

**Đáp án:**

```sql
SELECT
    region,
    SUM(CASE WHEN status = 'PAID' THEN amount ELSE 0 END)
        AS paid_total
FROM demo_orders
GROUP BY region
ORDER BY region;
```

`CENTRAL = 900`, `NORTH = 2200`, `SOUTH = 700`.

### Bài 4. Tính trung bình có điều kiện

**Yêu cầu:** tính giá trị trung bình của **chỉ các đơn `PAID`**.

**Đáp án:**

```sql
SELECT AVG(CASE WHEN status = 'PAID' THEN amount END)
    AS avg_paid_amount
FROM demo_orders;
-- 760
```

Không dùng `ELSE 0` nếu muốn loại các dòng không phải `PAID` khỏi mẫu số.

### Bài 5. Sắp xếp trạng thái tự định nghĩa

**Yêu cầu:** `PENDING` đứng trước `PAID`, tiếp đến `REFUNDED`, cuối cùng là `CANCELLED`. Các dòng cùng trạng thái sắp theo `order_id` tăng.

**Đáp án:**

```sql
SELECT order_id, status
FROM demo_orders
ORDER BY
    CASE status
        WHEN 'PENDING' THEN 1
        WHEN 'PAID' THEN 2
        WHEN 'REFUNDED' THEN 3
        WHEN 'CANCELLED' THEN 4
        ELSE 5
    END,
    order_id;
```

### Bài 6. Sửa lỗi đếm

Truy vấn sau có gì sai?

```sql
SELECT COUNT(
    CASE WHEN status = 'CANCELLED' THEN 1 ELSE 0 END
) AS cancelled_count
FROM demo_orders;
```

**Đáp án:** nó đếm **10** vì tất cả hàng cho kết quả `1` hoặc `0`, đều khác `NULL`. Sửa bằng `COUNT(CASE WHEN status='CANCELLED' THEN 1 END)` hoặc `SUM(CASE WHEN status='CANCELLED' THEN 1 ELSE 0 END)`, kết quả đúng là **2**.

### Bài 7. Chọn đơn theo ngưỡng khác nhau

**Yêu cầu:** lấy đơn `PAID` có số tiền ít nhất 500 hoặc đơn `PENDING` có số tiền ít nhất 1000.

**Đáp án:**

```sql
SELECT order_id, status, amount
FROM demo_orders
WHERE (status = 'PAID' AND amount >= 500)
   OR (status = 'PENDING' AND amount >= 1000)
ORDER BY order_id;
```

Kết quả ID **101, 104, 107, 108, 109**. Có thể dùng searched `CASE` như ở phần 4 để diễn đạt cùng quy tắc; khi chỉ lọc, cách viết predicate trực tiếp thường rõ hơn.

### Bài 8. CASE và NULL

**Yêu cầu:** những đơn có `priority IS NULL` phải được gắn `'UNASSIGNED'`; ưu tiên 1 là `'URGENT'`; các mức khác là `'NORMAL'`.

**Đáp án:**

```sql
SELECT
    order_id,
    CASE
        WHEN priority IS NULL THEN 'UNASSIGNED'
        WHEN priority = 1 THEN 'URGENT'
        ELSE 'NORMAL'
    END AS priority_label
FROM demo_orders
ORDER BY order_id;
```

Các đơn `UNASSIGNED` là ID **103, 105, 110**. Đừng dùng simple `CASE priority WHEN NULL` vì phép so sánh với `NULL` không khớp.

## Kết luận

`CASE` biến quy tắc rẽ nhánh thành **một giá trị biểu thức** để SQL sử dụng ở nhiều vị trí. Trong **lọc**, nó có thể chọn ngưỡng hoặc tạo kết quả điều kiện, nhưng `AND`/`OR` thường rõ hơn khi chỉ cần kết hợp predicate. Trong **sắp xếp**, `CASE` tạo thứ tự trạng thái và vị trí `NULL` theo nghiệp vụ. Trong **tổng hợp**, `SUM(CASE ...)` và `COUNT(CASE ...)` cho phép tính nhiều chỉ tiêu theo điều kiện trong cùng truy vấn nhóm.

Ba nguyên tắc cần ghi nhớ là: **nhánh `WHEN` phù hợp đầu tiên quyết định kết quả; bỏ `ELSE` sẽ nhận `NULL` nếu không có nhánh đúng; và `COUNT`/`SUM`/`AVG` xử lý `NULL` khác nhau**. Chọn đúng kết quả ở từng nhánh, viết rõ thứ tự ưu tiên và xác định mẫu số trong báo cáo sẽ giúp các truy vấn `CASE` chính xác, dễ đọc và dễ bảo trì.

