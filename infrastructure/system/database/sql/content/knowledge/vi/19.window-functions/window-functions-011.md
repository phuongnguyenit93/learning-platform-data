# Đặt tên cửa sổ bằng WINDOW khi được hỗ trợ

Khi một truy vấn SQL dùng nhiều **hàm cửa sổ (window functions)**, ta có thể phải lặp đi lặp lại những mệnh đề dài như:

```sql
OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
```

Viết lặp cùng một cấu hình nhiều lần vừa khó đọc vừa dễ sai: chỉ cần một hàm dùng thiếu `order_id` hoặc một hàm khác quên `ROWS`, hai cột kết quả có thể được tính trên các cửa sổ khác nhau.

Ở những hệ quản trị SQL **có hỗ trợ mệnh đề `WINDOW`**, ta có thể **đặt tên một cửa sổ** rồi tham chiếu tên đó trong các biểu thức `OVER`.

Ví dụ PostgreSQL:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    COUNT(*)    OVER w_customer AS customer_order_count
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
```

Trong ví dụ này:

- `WINDOW w_customer AS (...)` định nghĩa **cấu hình cửa sổ có tên**.
- `OVER w_customer` sử dụng cấu hình ấy để tính `SUM` và `COUNT`.
- Mỗi đơn hàng **vẫn là một hàng kết quả**; việc đặt tên cửa sổ không tự gom các đơn.
- `w_customer` chỉ là **tên trong phạm vi câu SQL**, không tạo bảng tạm, view hoặc dữ liệu được lưu lâu dài.

Bài học sẽ hướng dẫn cú pháp, vị trí đặt `WINDOW`, cách dùng một cửa sổ cho nhiều hàm, cách kế thừa và mở rộng cửa sổ, giới hạn khi đã có `ORDER BY` hay frame, khác biệt giữa `OVER w` và `OVER (w ...)`, và cách viết tương đương ở DBMS **không hỗ trợ named window**.

Các ví dụ chính dùng **PostgreSQL**. Cú pháp có điểm giống với MySQL 8+, SQLite và SQL Server 2022+ ở cấu hình phù hợp, nhưng khả năng mở rộng/kế thừa và giới hạn theo phiên bản cần được kiểm tra trong hệ quản trị thực tế.

## 1. Ôn lại: một cửa sổ trong SQL là gì?

**Window function** là một phép tính cho từng hàng dựa trên **một tập hàng có liên quan**. Khác với `GROUP BY` thường gom các dòng thành một hàng mỗi nhóm, hàm cửa sổ có thể giữ nguyên từng hàng chi tiết và thêm các cột tính toán.

Cấu trúc thường gặp:

```sql
function_name(arguments) OVER (
    PARTITION BY partition_expression
    ORDER BY sort_expression
    ROWS BETWEEN frame_start AND frame_end
)
```

Các thành phần có nhiệm vụ khác nhau:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| `OVER` | Đánh dấu phép tính được thực hiện như hàm cửa sổ | `SUM(amount) OVER (...)` |
| `PARTITION BY` | Chia các hàng thành phân vùng độc lập | Tổng tiền của từng khách |
| `ORDER BY` trong `OVER` | Xác định thứ tự logic trong phân vùng | Đơn đặt trước rồi đến đơn đặt sau |
| **Frame** (`ROWS`, `RANGE`, `GROUPS` khi hỗ trợ) | Xác định phần hàng trong phân vùng được dùng cho hàm phụ thuộc frame | Tổng lũy kế từ đầu phân vùng đến hàng hiện tại |
| `ORDER BY` cuối câu SQL | Sắp các hàng được trả cho ứng dụng | Hiển thị theo mã khách và mã đơn |

Không phải hàm cửa sổ nào cũng cần đủ cả ba thành phần `PARTITION BY`, `ORDER BY` và frame. Ví dụ `SUM(amount) OVER (PARTITION BY customer_id)` tính tổng toàn phân vùng mà không cần sắp thứ tự.

### 1.1. Cửa sổ có tên là gì?

Thay vì viết nguyên cấu hình bên trong mọi `OVER (...)`, ta đặt tên:

```sql
WINDOW w_customer AS (
    PARTITION BY customer_id
)
```

và sử dụng:

```sql
SUM(amount) OVER w_customer
COUNT(*) OVER w_customer
AVG(amount) OVER w_customer
```

Tên `w_customer` **đại diện cho phần đặc tả cửa sổ**, không phải một hàm riêng. Các hàm cùng tham chiếu `w_customer` nhưng thực hiện phép tính khác nhau.

## 2. Tạo dữ liệu mẫu thống nhất

Bài dùng bảng `lesson_orders` gồm tám đơn của ba khách. Một số đơn có cùng thời điểm và cùng giá trị tiền để minh họa việc xếp hạng, khung cửa sổ và các hàng đồng hạng.

Trên **PostgreSQL**, trong database thực hành:

```sql
CREATE TABLE lesson_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    ordered_at TIMESTAMP NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    order_status VARCHAR(20) NOT NULL
);

INSERT INTO lesson_orders
    (order_id, customer_id, ordered_at, amount, order_status)
VALUES
    (201, 1, '2026-10-01 09:00:00', 100, 'PAID'),
    (202, 1, '2026-10-03 10:00:00', 200, 'PAID'),
    (203, 1, '2026-10-03 10:00:00', 200, 'NEW'),
    (204, 2, '2026-10-02 08:00:00', 300, 'PAID'),
    (205, 2, '2026-10-05 11:00:00', 100, 'NEW'),
    (206, 2, '2026-10-06 13:00:00', 100, 'PAID'),
    (207, 3, '2026-10-04 17:00:00', 150, 'PAID'),
    (208, 3, '2026-10-07 10:00:00',  50, 'NEW');
```

Dữ liệu được hiển thị theo mã đơn:

| order_id | customer_id | ordered_at | amount | order_status |
| ---: | ---: | --- | ---: | --- |
| 201 | 1 | 2026-10-01 09:00 | 100 | PAID |
| 202 | 1 | 2026-10-03 10:00 | 200 | PAID |
| 203 | 1 | 2026-10-03 10:00 | 200 | NEW |
| 204 | 2 | 2026-10-02 08:00 | 300 | PAID |
| 205 | 2 | 2026-10-05 11:00 | 100 | NEW |
| 206 | 2 | 2026-10-06 13:00 | 100 | PAID |
| 207 | 3 | 2026-10-04 17:00 | 150 | PAID |
| 208 | 3 | 2026-10-07 10:00 | 50 | NEW |

Các tổng cần ghi nhớ:

| customer_id | Số đơn | Tổng tiền | Tiền đơn PAID |
| ---: | ---: | ---: | ---: |
| 1 | 3 | 500 | 300 |
| 2 | 3 | 500 | 400 |
| 3 | 2 | 200 | 150 |
| **Toàn bảng** | **8** | **1.200** | **850** |

Hai đơn `202` và `203` có cùng `ordered_at`; hai đơn `205` và `206` có cùng `amount`. Đây là những tình huống giúp phân biệt rõ **thứ tự**, **peer**, **frame** và **quy tắc phá hòa**.

## 3. Viết cửa sổ trực tiếp trong OVER

Trước khi đặt tên, hãy viết một truy vấn dùng hai hàm với cùng phân vùng:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
    ) AS customer_total,
    COUNT(*) OVER (
        PARTITION BY customer_id
    ) AS customer_order_count
FROM lesson_orders
ORDER BY customer_id, order_id;
```

Kết quả:

| order_id | customer_id | amount | customer_total | customer_order_count |
| ---: | ---: | ---: | ---: | ---: |
| 201 | 1 | 100 | 500 | 3 |
| 202 | 1 | 200 | 500 | 3 |
| 203 | 1 | 200 | 500 | 3 |
| 204 | 2 | 300 | 500 | 3 |
| 205 | 2 | 100 | 500 | 3 |
| 206 | 2 | 100 | 500 | 3 |
| 207 | 3 | 150 | 200 | 2 |
| 208 | 3 | 50 | 200 | 2 |

Truy vấn đúng, nhưng `PARTITION BY customer_id` được lặp hai lần. Với năm hoặc mười phép tính cùng cửa sổ, phần lặp sẽ dài hơn và dễ tạo ra sai khác không mong muốn.

## 4. Đặt tên cửa sổ bằng WINDOW

Viết lại truy vấn trước với **named window**:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    COUNT(*) OVER w_customer AS customer_order_count
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
```

**Kết quả giữ nguyên tám hàng và các con số trong mục 3.**

### 4.1. Đọc cú pháp từng phần

```sql
WINDOW w_customer AS (PARTITION BY customer_id)
```

gồm:

- `WINDOW`: mở đầu phần khai báo cửa sổ.
- `w_customer`: tên được lựa chọn trong truy vấn này.
- `AS`: nối tên với định nghĩa.
- `(PARTITION BY customer_id)`: đặc tả cửa sổ, không chứa tên hàm `SUM` hay `COUNT`.

Trong `SELECT`:

```sql
SUM(amount) OVER w_customer
```

có nghĩa: áp dụng `SUM` như window aggregate theo cấu hình `w_customer`.

### 4.2. Lợi ích thực tế

- **Giảm lặp SQL:** định nghĩa phân vùng một lần.
- **Đảm bảo tính nhất quán ở mức cấu hình:** các hàm trỏ đến cùng đặc tả.
- **Giúp đặt tên theo ý nghĩa:** `w_customer`, `w_by_time`, `w_running`.
- **Dễ đọc truy vấn nhiều phép tính:** phần `SELECT` tập trung vào đại lượng cần tính.
- **Thuận tiện sửa đổi chung:** nếu tất cả phép tính cần đổi sang phân vùng `(customer_id, order_status)`, có thể đổi tại một vị trí.

Cần lưu ý: **cùng cấu hình không có nghĩa cùng phép tính**. `SUM`, `AVG`, `ROW_NUMBER` và `LAG` dùng cấu hình tương tự nhưng trả loại kết quả khác nhau.

## 5. Vị trí của mệnh đề WINDOW trong câu SQL

Trên PostgreSQL, vị trí thường gặp:

```sql
SELECT ...
FROM ...
WHERE ...
GROUP BY ...
HAVING ...
WINDOW window_name AS (window_specification)
ORDER BY ...
LIMIT ...;
```

Không phải câu SQL nào cũng cần `WHERE`, `GROUP BY`, `HAVING` hay `LIMIT`. Trong các ví dụ chính, `WINDOW` nằm **sau phần lọc/nhóm** và **trước `ORDER BY` cuối cùng**.

Ví dụ:

```sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_amount AS amount_position
FROM lesson_orders
WHERE amount >= 100
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount DESC, order_id ASC
)
ORDER BY customer_id, amount_position;
```

`WHERE amount >= 100` lọc tập hàng **trước khi cửa sổ được áp dụng**. `ORDER BY customer_id, amount_position` cuối cùng sắp các hàng hiển thị.

### 5.1. Không đặt WINDOW lẫn vào OVER

**Không đúng:**

```sql
-- Không phải cú pháp khai báo named window:
SELECT
    SUM(amount) OVER WINDOW w_customer AS (...)
FROM lesson_orders;
```

**Đúng:**

```sql
SELECT
    SUM(amount) OVER w_customer
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
);
```

`OVER` tham chiếu cửa sổ, còn `WINDOW` khai báo tên cửa sổ ở cấp câu truy vấn.

### 5.2. WINDOW là một mệnh đề, không phải một bảng

Tên `w_customer` không có cột dữ liệu riêng để dùng như:

```sql
-- Sai ý nghĩa: w_customer không phải một bảng.
SELECT *
FROM w_customer;
```

Nó cũng không phải một alias được phép đặt vào `JOIN` thay cho bảng nguồn. Nó chỉ là tên của **đặc tả window** được tham chiếu ở các vị trí SQL cho phép.

## 6. OVER w và OVER (w ...): phân biệt chính xác

Đây là điểm quan trọng nhất khi học named windows.

### 6.1. Dùng nguyên cửa sổ đã được khai báo

Ví dụ:

```sql
SELECT
    order_id,
    SUM(amount) OVER w_customer AS customer_total
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
);
```

Cú pháp:

```sql
OVER w_customer
```

là **tham chiếu trực tiếp** đến cửa sổ có tên.

### 6.2. Dùng một cửa sổ làm cơ sở rồi bổ sung cấu hình

Ví dụ muốn cùng phân vùng nhưng xếp theo thời gian:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER (
        w_customer ORDER BY ordered_at, order_id
    ) AS chronological_number
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, chronological_number;
```

Biểu thức:

```sql
OVER (w_customer ORDER BY ordered_at, order_id)
```

**dựa trên định nghĩa `w_customer`**, đồng thời **bổ sung `ORDER BY`**. Vì `w_customer` chỉ có `PARTITION BY`, việc bổ sung thứ tự là hợp lý trong PostgreSQL.

### 6.3. OVER (w) không nên được xem là tương đương tuyệt đối với OVER w

Trên PostgreSQL, có những trường hợp:

```sql
OVER w_name
```

và:

```sql
OVER (w_name)
```

**không hoàn toàn tương đương về khả năng tham chiếu**, nhất là khi named window đã có **frame clause**. `OVER (w_name)` là dạng sao chép/biến đổi đặc tả cửa sổ theo quy tắc cú pháp; PostgreSQL có giới hạn khi sao chép một named window đã chứa frame. `OVER w_name` là cách tham chiếu trực tiếp được dùng trong trường hợp đó.

Ví dụ nên viết:

```sql
SELECT
    order_id,
    SUM(amount) OVER w_running AS running_total
FROM lesson_orders
WINDOW w_running AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
);
```

**Tránh mặc định** thay toàn bộ `OVER w_running` bằng `OVER (w_running)` trên PostgreSQL khi cửa sổ gốc đã có frame. Ở các hệ quản trị khác, cú pháp và giới hạn tham chiếu có thể khác nhau.

## 7. Một WINDOW, nhiều hàm tổng hợp

Một định nghĩa phân vùng có thể phục vụ nhiều phép tính:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS total_amount,
    COUNT(*)    OVER w_customer AS number_of_orders,
    AVG(amount) OVER w_customer AS average_amount,
    MIN(amount) OVER w_customer AS smallest_amount,
    MAX(amount) OVER w_customer AS largest_amount
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
```

Các kết quả theo khách:

| customer_id | total_amount | number_of_orders | average_amount | smallest_amount | largest_amount |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 500 | 3 | 166,67 (xấp xỉ) | 100 | 200 |
| 2 | 500 | 3 | 166,67 (xấp xỉ) | 100 | 300 |
| 3 | 200 | 2 | 100 | 50 | 150 |

Các chỉ số này được **lặp lại trên từng đơn** thuộc khách tương ứng. Số hàng không giảm vì named window không làm nhiệm vụ `GROUP BY`.

### 7.1. Cùng tên cửa sổ không làm các hàm “dùng chung kết quả”

`SUM` và `AVG` có thể cần xử lý những phép tính khác nhau, dù cùng `OVER w_customer`. `WINDOW` chủ yếu là cơ chế **đặt tên và tái sử dụng đặc tả logic**, không phải tuyên bố engine chắc chắn tính mọi aggregate đúng một lần hoặc lưu chung một bảng kết quả.

Bộ tối ưu có thể chia sẻ sort hoặc cấu trúc xử lý cho những cửa sổ tương đương, nhưng không có bảo đảm mọi DBMS/phiên bản đều thực hiện kế hoạch vật lý giống nhau.

### 7.2. Một tên chỉ nên có một ý nghĩa rõ ràng

Đặt tên theo ý nghĩa giúp tránh lỗi:

- `w_customer` — toàn bộ hàng của một khách.
- `w_customer_time` — thứ tự theo thời gian trong một khách.
- `w_customer_running` — khung lũy kế từng hàng trong một khách.
- `w_status` — các đơn thuộc cùng khách và trạng thái.

Không nên đặt tên `w1`, `w2`, `w3` nếu truy vấn nhiều cửa sổ và người đọc khó xác định công dụng.

## 8. Khai báo nhiều cửa sổ trong cùng WINDOW

Một câu SQL có thể khai báo **nhiều named windows** trong cùng mệnh đề `WINDOW`, phân tách bằng dấu phẩy:

```sql
SELECT
    order_id,
    customer_id,
    order_status,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    SUM(amount) OVER w_customer_status AS customer_status_total,
    ROW_NUMBER() OVER w_amount_desc AS amount_position
FROM lesson_orders
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_customer_status AS (
        PARTITION BY customer_id, order_status
    ),
    w_amount_desc AS (
        PARTITION BY customer_id
        ORDER BY amount DESC, order_id ASC
    )
ORDER BY customer_id, order_id;
```

Các cửa sổ tương ứng ba câu hỏi:

1. **Tổng tiền mọi đơn** của khách.
2. **Tổng tiền theo trạng thái** của khách.
3. **Vị trí của đơn** theo số tiền giảm dần trong khách.

Ví dụ, với An:

| order_id | order_status | amount | customer_total | customer_status_total | amount_position |
| ---: | --- | ---: | ---: | ---: | ---: |
| 201 | PAID | 100 | 500 | 300 | 3 |
| 202 | PAID | 200 | 500 | 300 | 1 |
| 203 | NEW | 200 | 500 | 200 | 2 |

**Lưu ý:** thứ tự xuất hiện ở kết quả đã được yêu cầu bằng `ORDER BY customer_id, order_id` ngoài cùng; giá trị `amount_position` được tính theo `amount DESC, order_id ASC` trong cửa sổ.

### 8.1. Không cần một WINDOW riêng cho từng hàm

Nếu ba hàm dùng cùng định nghĩa, chỉ cần khai báo một tên và tham chiếu lại.

Nếu ba hàm dùng **ba kiểu phân vùng hoặc thứ tự khác nhau**, cần khai báo những cửa sổ tương ứng hoặc sử dụng một cửa sổ nền và mở rộng đúng quy tắc.

## 9. Kế thừa một named window để giảm lặp

Trên PostgreSQL, một named window có thể dựa trên một **cửa sổ đã được khai báo trước** trong mệnh đề `WINDOW`, với những giới hạn về điều kiện mở rộng.

Ví dụ:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER w_time AS chronological_number
FROM lesson_orders
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    )
ORDER BY customer_id, chronological_number;
```

Cửa sổ `w_time` **kế thừa `PARTITION BY customer_id`** từ `w_customer` và bổ sung `ORDER BY ordered_at, order_id`.

### 9.1. Sơ đồ phụ thuộc

```text
w_customer
  PARTITION BY customer_id
       |
       +-- SUM(amount) OVER w_customer
       |
       +-- w_time
             ORDER BY ordered_at, order_id
                 |
                 +-- ROW_NUMBER() OVER w_time
```

Ở đây `w_customer` là **cấu hình cơ sở**, không phải bảng tạm hoặc CTE.

### 9.2. Khai báo cửa sổ nền trước cửa sổ dẫn xuất

Cách viết dễ hiểu và phù hợp với PostgreSQL là:

```sql
WINDOW
    base_window AS (...),
    derived_window AS (base_window ...)
```

Không nên đảo lại thứ tự rồi kỳ vọng tên cửa sổ khai báo sau luôn được cho phép tham chiếu từ cửa sổ khai báo trước. Quy tắc phụ thuộc và cú pháp có thể chặt chẽ theo DBMS.

### 9.3. Vì sao không chỉ sao chép cả định nghĩa?

Có thể khai báo hai cửa sổ độc lập:

```sql
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    )
```

Cách này vẫn đúng nhưng lặp `PARTITION BY customer_id`. Kế thừa hữu ích khi nhiều cửa sổ có **phần nền chung dài** hoặc khi muốn biểu thị rõ một **hệ các mức cửa sổ**.

## 10. Kế thừa theo nhiều tầng: phân vùng, thứ tự, frame

Một ví dụ hoàn chỉnh:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS full_partition_total,
    ROW_NUMBER() OVER w_time AS chronological_number,
    SUM(amount) OVER w_running AS running_total,
    SUM(amount) OVER w_full_ordered AS full_ordered_total
FROM lesson_orders
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_full_ordered AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, chronological_number;
```

Trong PostgreSQL, khi định nghĩa cửa sổ dẫn xuất bằng `w_time`, phải bảo đảm cửa sổ nền **chưa có frame** mà ta đang cố bổ sung/sửa đổi.

Ý nghĩa từng tên:

| Cửa sổ | Phân vùng | Thứ tự | Frame | Mục đích |
| --- | --- | --- | --- | --- |
| `w_customer` | Theo khách | Không có | Toàn phân vùng | Tổng, đếm theo khách |
| `w_time` | Theo khách | Thời gian rồi mã đơn | Mặc định theo ngữ cảnh hàm | Đánh số và so sánh đơn theo thứ tự |
| `w_running` | Theo khách | Thời gian rồi mã đơn | Từ đầu phân vùng đến hàng hiện tại | Tổng lũy kế |
| `w_full_ordered` | Theo khách | Thời gian rồi mã đơn | Từ đầu đến cuối phân vùng | Tổng toàn khách dù có `ORDER BY` |

Kết quả tiêu biểu với khách 1:

| order_id | full_partition_total | chronological_number | running_total | full_ordered_total |
| ---: | ---: | ---: | ---: | ---: |
| 201 | 500 | 1 | 100 | 500 |
| 202 | 500 | 2 | 300 | 500 |
| 203 | 500 | 3 | 500 | 500 |

Đây là một trong những cách dùng `WINDOW` hữu ích nhất: có một cấu hình **cơ sở**, sau đó đặt tên các biến thể chỉ khác **frame** nhưng không phải lặp toàn bộ `PARTITION BY`/`ORDER BY`.

## 11. Giới hạn kế thừa: không thể tùy ý sửa mọi thành phần

Kế thừa named window không phải cơ chế ghi đè cấu hình giống một đối tượng lập trình bất kỳ. Trong PostgreSQL, có những hạn chế quan trọng.

### 11.1. Không khai báo lại PARTITION BY của cửa sổ nền

Ví dụ cần tránh:

```sql
-- PostgreSQL: cách mở rộng không hợp lệ.
SELECT
    SUM(amount) OVER (
        w_customer PARTITION BY order_status
    )
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
);
```

Cửa sổ `w_customer` đã có `PARTITION BY customer_id`. Không dùng biểu thức mở rộng để thay nó bằng `PARTITION BY order_status`.

Nếu cần hai phân vùng độc lập, khai báo hai cửa sổ:

```sql
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_status AS (PARTITION BY order_status)
```

### 11.2. Không bổ sung ORDER BY khi nền đã có ORDER BY

Ví dụ:

```sql
-- PostgreSQL: không thể thêm ORDER BY mới vào window đã ordered.
SELECT
    ROW_NUMBER() OVER (
        w_time ORDER BY amount DESC
    )
FROM lesson_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
);
```

Muốn xếp theo tiền thay vì thời gian, hãy tạo một cửa sổ khác dựa trên nền **chỉ có phân vùng**:

```sql
SELECT
    order_id,
    ROW_NUMBER() OVER w_time AS time_position,
    ROW_NUMBER() OVER w_amount AS amount_position
FROM lesson_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    ),
    w_amount AS (
        w_customer ORDER BY amount DESC, order_id ASC
    );
```

### 11.3. Không tùy ý sửa frame của cửa sổ nền đã có frame

Nếu `w_running` đã chứa:

```sql
ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
```

thì không nên cố “kế thừa `w_running` rồi đổi điểm cuối thành `UNBOUNDED FOLLOWING`” theo cách trực tiếp.

Hãy kế thừa từ **`w_time` chưa có frame** để tạo hai cửa sổ anh em:

```sql
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ),
    w_full AS (
        w_time
        ROWS BETWEEN UNBOUNDED PRECEDING
             AND UNBOUNDED FOLLOWING
    )
```

Quy tắc giúp thiết kế dễ bảo trì: **nền chỉ chứa thành phần chung, phần biến thể khai báo ở cửa sổ con**.

### 11.4. Khi cửa sổ có cấu hình khác hẳn nhau

Nếu một hàm phải phân vùng theo `customer_id`, một hàm khác phân vùng theo `order_status` và thứ ba theo tháng đặt đơn, không nên cố ép chúng vào chung một chuỗi kế thừa. Các cửa sổ có thể **độc lập**, miễn tên rõ ràng và truy vấn dễ đọc.

## 12. Ranh giới dễ mắc nhất: ORDER BY làm đổi frame của SUM

Xét hai biểu thức:

```sql
SUM(amount) OVER (
    PARTITION BY customer_id
)
```

và:

```sql
SUM(amount) OVER (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
```

Chúng **không mặc nhiên cho cùng kết quả trên mỗi hàng**.

Trên PostgreSQL, đối với aggregate window, khi có `ORDER BY` nhưng không khai báo frame tường minh, khung mặc định thường tương đương `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`, bao gồm các hàng **đồng hạng theo khóa ORDER BY**.

Vì vậy:

- Không có `ORDER BY`: `SUM` tính **tổng toàn bộ phân vùng khách**.
- Có `ORDER BY` và dùng frame mặc định: `SUM` thường trở thành **tổng lũy kế** theo thứ tự cửa sổ.

### 12.1. Bẫy khi đặt tên một cửa sổ ordered rồi dùng cho mọi SUM

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_time AS amount_up_to_current
FROM lesson_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, ordered_at, order_id;
```

Với khách 1:

| order_id | amount | amount_up_to_current |
| ---: | ---: | ---: |
| 201 | 100 | 100 |
| 202 | 200 | 300 |
| 203 | 200 | 500 |

Nếu người viết kỳ vọng cả ba hàng đều có tổng `500`, họ đã chọn sai **đặc tả cửa sổ**, không phải sai `SUM`.

### 12.2. Cách dùng hai cửa sổ đúng mục đích

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    SUM(amount) OVER w_running AS running_total
FROM lesson_orders
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_running AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
```

Kết quả cho An là `customer_total = 500` trên cả ba đơn, còn `running_total` lần lượt `100, 300, 500`.

Đặt tên `w_customer` và `w_running` làm rõ rằng chúng **không được coi là cùng một cửa sổ**.

## 13. ROWS, RANGE và các hàng đồng hạng

Trong bảng mẫu, đơn `202` và `203` có **cùng thời điểm**.

Nếu dùng cửa sổ:

```sql
WINDOW w_time_only AS (
    PARTITION BY customer_id
    ORDER BY ordered_at
)
```

thì hai đơn có cùng `ordered_at` là **peers** đối với thứ tự cửa sổ ấy.

### 13.1. Frame mặc định với ORDER BY theo thời gian

```sql
SELECT
    order_id,
    amount,
    SUM(amount) OVER w_time_only AS total_by_time
FROM lesson_orders
WHERE customer_id = 1
WINDOW w_time_only AS (
    PARTITION BY customer_id
    ORDER BY ordered_at
)
ORDER BY ordered_at, order_id;
```

Kết quả PostgreSQL:

| order_id | amount | total_by_time |
| ---: | ---: | ---: |
| 201 | 100 | 100 |
| 202 | 200 | 500 |
| 203 | 200 | 500 |

Vì hai đơn cuối có cùng timestamp, frame mặc định kiểu `RANGE` bao gồm cả hai ở thời điểm đó.

### 13.2. Frame ROWS với khóa phá hòa

```sql
SELECT
    order_id,
    amount,
    SUM(amount) OVER w_running AS running_total
FROM lesson_orders
WHERE customer_id = 1
WINDOW w_running AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
)
ORDER BY ordered_at, order_id;
```

Kết quả: `100, 300, 500` cho các đơn `201, 202, 203`.

### 13.3. Vì sao phải đặt tên chính xác theo frame?

Một tên chung như `w_time` có thể che khác biệt giữa:

- Thứ tự theo **mốc thời gian** và gộp những đơn cùng timestamp.
- Thứ tự theo **từng giao dịch**, có mã phá hòa.
- Tổng của **toàn khách** dù có thứ tự.
- Tổng **từ đầu đến hiện tại**.

Nếu report quan tâm các giao dịch lũy kế từng đơn, nên đặt tên như `w_running_rows` hoặc `w_transaction_sequence`. Nếu report quan tâm lũy kế từng mốc thời gian, tên như `w_time_peers` có thể mô tả tốt hơn.

**Tên cửa sổ là một phần tài liệu ngữ nghĩa**, chứ không chỉ là cách rút ngắn ký tự.

## 14. Named window cho ROW_NUMBER, RANK và DENSE_RANK

Ngoài tổng hợp, mệnh đề `WINDOW` hữu ích khi nhiều hàm xếp hạng dùng cùng `PARTITION BY` và `ORDER BY`.

Ví dụ xếp hạng đơn theo tiền trong mỗi khách:

```sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_amount AS row_number_value,
    RANK()       OVER w_amount AS rank_value,
    DENSE_RANK() OVER w_amount AS dense_rank_value
FROM lesson_orders
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount DESC
)
ORDER BY customer_id, amount DESC, order_id;
```

Khi `ORDER BY` trong `w_amount` chỉ chứa `amount`, những đơn có cùng tiền là **peers**.

- `RANK` cùng hạng cho các đơn đồng tiền.
- `DENSE_RANK` cùng hạng và không tạo khoảng trống giữa các mức tiền.
- `ROW_NUMBER` vẫn phải đánh số lần lượt cho từng hàng trong nhóm peers; nhưng nếu chỉ sắp theo `amount`, thứ tự cụ thể giữa các đơn đồng tiền **không được xác định chắc chắn**.

### 14.1. Cần đúng một thứ tự xác định? Tách cửa sổ

Nếu muốn `ROW_NUMBER` chọn thứ tự ổn định theo `order_id`, nhưng `RANK` vẫn đồng hạng theo `amount`:

```sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_amount_unique AS rn,
    RANK() OVER w_amount_peers AS amount_rank,
    DENSE_RANK() OVER w_amount_peers AS amount_dense_rank
FROM lesson_orders
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_amount_unique AS (
        w_customer ORDER BY amount DESC, order_id ASC
    ),
    w_amount_peers AS (
        w_customer ORDER BY amount DESC
    )
ORDER BY customer_id, amount DESC, order_id;
```

Kết quả tiêu biểu:

| customer_id | order_id | amount | rn | amount_rank | amount_dense_rank |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 202 | 200 | 1 | 1 | 1 |
| 1 | 203 | 200 | 2 | 1 | 1 |
| 1 | 201 | 100 | 3 | 3 | 2 |
| 2 | 204 | 300 | 1 | 1 | 1 |
| 2 | 205 | 100 | 2 | 2 | 2 |
| 2 | 206 | 100 | 3 | 2 | 2 |
| 3 | 207 | 150 | 1 | 1 | 1 |
| 3 | 208 | 50 | 2 | 2 | 2 |

**Cảnh báo:** Nếu thêm `order_id ASC` vào cửa sổ dùng cho `RANK`, các đơn tiền bằng nhau nhưng mã khác nhau sẽ **không còn đồng hạng** theo toàn bộ khóa cửa sổ. Đây là lý do thực tế để dùng **hai tên cửa sổ** thay vì ép mọi hàm vào chung một tên.

## 15. Named window cho LAG và LEAD

`LAG` và `LEAD` trả thông tin của hàng đứng trước/sau theo thứ tự trong một phân vùng.

Ví dụ:

```sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    LAG(order_id) OVER w_time AS previous_order_id,
    LAG(amount)   OVER w_time AS previous_amount,
    LEAD(order_id) OVER w_time AS next_order_id
FROM lesson_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, ordered_at, order_id;
```

Với khách 1:

| order_id | previous_order_id | previous_amount | next_order_id |
| ---: | ---: | ---: | ---: |
| 201 | `NULL` | `NULL` | 202 |
| 202 | 201 | 100 | 203 |
| 203 | 202 | 200 | `NULL` |

Dùng chung `w_time` bảo đảm các hàm đều hiểu **“trước/sau” theo cùng một thứ tự**.

### 15.1. LAG và LEAD không giống SUM lũy kế

Đối với `LAG`/`LEAD`, thứ tự trong `OVER` là thành phần then chốt để biết hàng trước hoặc sau. Khung `ROWS BETWEEN ...` không điều khiển `LAG`/`LEAD` theo cùng cách nó điều khiển `SUM`. Vì vậy nên đặt tên cửa sổ chứa **phân vùng + thứ tự**, và chỉ khai báo các biến thể frame khi một hàm thực sự cần.

### 15.2. Đừng bỏ khóa phá hòa

Hai đơn `202` và `203` có cùng timestamp. Nếu `w_time` chỉ dùng `ORDER BY ordered_at`, “đơn trước” giữa chúng không được xác định bởi thời gian. Thêm `order_id` nếu nghiệp vụ muốn thứ tự giao dịch duy nhất.

## 16. FIRST_VALUE và LAST_VALUE: frame vẫn quan trọng

Một tên cửa sổ có thứ tự rất thuận tiện cho `FIRST_VALUE` và `LAST_VALUE`, nhưng cần xét **khung**.

Ví dụ muốn mỗi đơn của khách biết **mã đơn mới nhất của khách theo (ordered_at, order_id)**:

```sql
SELECT
    customer_id,
    order_id,
    FIRST_VALUE(order_id) OVER w_full AS earliest_order_id,
    LAST_VALUE(order_id) OVER w_full AS latest_order_id
FROM lesson_orders
WINDOW w_full AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
    ROWS BETWEEN UNBOUNDED PRECEDING
         AND UNBOUNDED FOLLOWING
)
ORDER BY customer_id, order_id;
```

Kết quả:

| customer_id | order_id | earliest_order_id | latest_order_id |
| ---: | ---: | ---: | ---: |
| 1 | 201 | 201 | 203 |
| 1 | 202 | 201 | 203 |
| 1 | 203 | 201 | 203 |
| 2 | 204 | 204 | 206 |
| 2 | 205 | 204 | 206 |
| 2 | 206 | 204 | 206 |
| 3 | 207 | 207 | 208 |
| 3 | 208 | 207 | 208 |

`UNBOUNDED FOLLOWING` giúp frame bao trùm đến **cuối phân vùng**. Nếu dùng frame mặc định dừng ở hàng hiện tại hoặc peer hiện tại, `LAST_VALUE` có thể trả kết quả **khác** “cuối toàn phân vùng”.

Đặt tên `w_full` làm rõ rằng đây là cửa sổ có **frame toàn phân vùng**, không chỉ một cửa sổ có thứ tự đơn thuần.

## 17. WINDOW kết hợp với GROUP BY

Mệnh đề `WINDOW` không chỉ dùng cho truy vấn chi tiết. Nó cũng dùng được khi câu SQL đã có `GROUP BY`.

Ví dụ muốn thống kê **tổng tiền theo khách**, rồi xếp hạng các khách theo tổng:

```sql
SELECT
    customer_id,
    SUM(amount) AS customer_total,
    RANK() OVER w_spending AS spending_rank
FROM lesson_orders
GROUP BY customer_id
WINDOW w_spending AS (
    ORDER BY SUM(amount) DESC
)
ORDER BY spending_rank, customer_id;
```

Kết quả:

| customer_id | customer_total | spending_rank |
| ---: | ---: | ---: |
| 1 | 500 | 1 |
| 2 | 500 | 1 |
| 3 | 200 | 3 |

### 17.1. Hai cấp đánh giá khác nhau

- `GROUP BY customer_id`: gom tám đơn thành **ba hàng khách hàng**.
- `SUM(amount)`: tính tổng ở mức khách.
- `RANK() OVER w_spending`: xếp hạng **ba hàng nhóm** theo `SUM(amount)`.
- `WINDOW w_spending AS (ORDER BY SUM(amount) DESC)`: đặt tên thứ tự dùng cho hàm xếp hạng ở cấp nhóm.

Cửa sổ xử lý **những hàng còn lại sau grouping/HAVING**, không trực tiếp quay lại tám hàng nguồn để xếp hạng đơn nữa.

### 17.2. CTE giúp tránh lặp biểu thức tổng

Nếu muốn đặt tên `customer_total` rồi dùng trong window specification, dùng CTE:

```sql
WITH totals AS (
    SELECT
        customer_id,
        SUM(amount) AS customer_total
    FROM lesson_orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    customer_total,
    RANK() OVER w_spending AS spending_rank
FROM totals
WINDOW w_spending AS (
    ORDER BY customer_total DESC
)
ORDER BY spending_rank, customer_id;
```

Tên `customer_total` là cột **được cung cấp bởi CTE `totals`**, nên hợp lệ khi cửa sổ của truy vấn ngoài dùng nó.

Ngược lại, một alias vừa được tạo trong `SELECT` **cùng cấp** thường không thể dùng trực tiếp bên trong `WINDOW (...)` của cấp đó trên PostgreSQL. Nếu gặp lỗi alias không được nhận diện, tạo CTE/derived table rồi đặt cửa sổ ở truy vấn ngoài.

## 18. Lọc dữ liệu trước cửa sổ hay lọc kết quả cửa sổ?

Bài toán: chỉ xem các đơn `PAID` và tính tổng tiền `PAID` theo khách.

```sql
SELECT
    order_id,
    customer_id,
    order_status,
    amount,
    SUM(amount) OVER w_customer AS paid_total
FROM lesson_orders
WHERE order_status = 'PAID'
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
```

Kết quả chỉ có các đơn `PAID`. Tổng theo khách là:

- Khách 1: `300`.
- Khách 2: `400`.
- Khách 3: `150`.

### 18.1. WHERE chạy trước ý nghĩa cửa sổ

`WHERE order_status = 'PAID'` lọc hàng **trước** khi cửa sổ nhận tập đầu vào. Vì vậy `SUM(amount) OVER w_customer` ở ví dụ này chỉ cộng những đơn đã trả tiền.

Nếu muốn **giữ cả đơn NEW** nhưng thêm tổng tiền PAID của khách, không dùng `WHERE` như vậy.

### 18.2. Giữ mọi đơn và tính tổng có điều kiện trong cửa sổ

Trên PostgreSQL:

```sql
SELECT
    order_id,
    customer_id,
    order_status,
    amount,
    SUM(amount) FILTER (
        WHERE order_status = 'PAID'
    ) OVER w_customer AS paid_total
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
```

Kết quả **giữ cả tám hàng**, với `paid_total` tương ứng `300`, `400`, `150` theo từng khách.

Một cách dễ chuyển hệ hơn:

```sql
SELECT
    order_id,
    customer_id,
    order_status,
    amount,
    SUM(
        CASE
            WHEN order_status = 'PAID' THEN amount
            ELSE 0
        END
    ) OVER w_customer AS paid_total
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
```

`FILTER` trong aggregate window không được mọi DBMS hỗ trợ như PostgreSQL. Cách `SUM(CASE ...)` có thể phù hợp khi cần tính di động.

### 18.3. Named window không tự ghi nhớ các hàng bị lọc

`WINDOW w_customer AS (PARTITION BY customer_id)` chỉ định nghĩa cách phân vùng **trên tập hàng hiện tại**. Nó không lưu toàn bộ đơn của khách trước khi `WHERE` chạy và không cho phép một cửa sổ “vượt qua” bộ lọc cùng cấp để tự nhìn lại các hàng đã bị loại.

Nếu cần hai tập dữ liệu có phạm vi lọc khác nhau, hãy thiết kế CTE/subquery hoặc điều kiện tổng hợp phù hợp.

## 19. Muốn lọc top N theo cửa sổ đã đặt tên: dùng CTE

Hàm cửa sổ không được tham chiếu trực tiếp trong `WHERE` cùng cấp trên PostgreSQL:

```sql
-- Không hợp lệ trên PostgreSQL.
SELECT order_id, customer_id
FROM lesson_orders
WHERE ROW_NUMBER() OVER w_amount = 1
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount DESC, order_id ASC
);
```

Hãy tính trong CTE:

```sql
WITH ranked AS (
    SELECT
        order_id,
        customer_id,
        amount,
        ROW_NUMBER() OVER w_amount AS rn
    FROM lesson_orders
    WINDOW w_amount AS (
        PARTITION BY customer_id
        ORDER BY amount DESC, order_id ASC
    )
)
SELECT
    customer_id,
    order_id,
    amount
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

Kết quả:

| customer_id | order_id | amount |
| ---: | ---: | ---: |
| 1 | 202 | 200 |
| 2 | 204 | 300 |
| 3 | 207 | 150 |

**Điểm phân biệt:**

- `WINDOW` định nghĩa thứ tự dùng cho `ROW_NUMBER`.
- CTE `ranked` tạo ra **cột `rn` thực sự trong kết quả trung gian**.
- Truy vấn ngoài `WHERE rn=1` lọc **giá trị cột đã được tính ở cấp trước**.

### 19.1. Tên WINDOW có đi ra ngoài CTE không?

Không. Tên `w_amount` chỉ tồn tại **trong khối SELECT nơi nó được khai báo**. Ở truy vấn ngoài, ta dùng được cột `rn` do CTE xuất ra, nhưng **không thể tự dùng `OVER w_amount`** nếu không khai báo lại named window trong chính truy vấn ngoài.

Ví dụ tư duy:

```text
Khối SELECT bên trong CTE:
    WINDOW w_amount AS (...)
    ROW_NUMBER() OVER w_amount AS rn
             |
             v
Khối SELECT ngoài:
    dùng rn như một cột của CTE
    không tự thừa hưởng tên w_amount
```

Đây là một điểm khác biệt với view hoặc bảng được lưu: named window là **tên đặc tả theo phạm vi SQL**, không phải đối tượng chung của database.

## 20. WINDOW trong truy vấn con và phạm vi tên

Mỗi khối `SELECT` có phạm vi tên cửa sổ riêng.

Ví dụ:

```sql
SELECT
    x.customer_id,
    x.order_id,
    x.customer_total
FROM (
    SELECT
        customer_id,
        order_id,
        SUM(amount) OVER w_customer AS customer_total
    FROM lesson_orders
    WINDOW w_customer AS (
        PARTITION BY customer_id
    )
) AS x
ORDER BY x.customer_id, x.order_id;
```

Truy vấn ngoài chỉ nhìn thấy các **cột mà subquery `x` trả về**. Nó không tự nhìn thấy `w_customer`.

### 20.1. Có thể dùng lại cùng tên ở khối SELECT khác?

Có thể khai báo một tên cửa sổ giống nhau trong hai khối SELECT độc lập, vì tên được phân giải theo **phạm vi của từng khối**. Nhưng điều đó không có nghĩa hai định nghĩa được liên kết hay đồng bộ.

Khi nhiều câu SQL cần cùng đặc tả, giải pháp thường là tái sử dụng **mã SQL** có quản lý, hoặc tạo view phù hợp cho phép tính đã hoàn thành. `WINDOW` không tạo một “window object” chung để tham chiếu trong câu lệnh bất kỳ.

### 20.2. Không thể dùng named window như nguồn quan hệ của JOIN

Câu lệnh:

```sql
SELECT *
FROM lesson_orders AS o
JOIN w_customer AS w ON ...;
```

không có ý nghĩa nếu `w_customer` chỉ là tên khai báo ở mệnh đề `WINDOW`. Muốn nối dữ liệu, dùng bảng, derived table, CTE, view hoặc các nguồn quan hệ hợp lệ khác.

## 21. Đặt tên cửa sổ trong ORDER BY cuối câu SQL

Trên PostgreSQL, hàm cửa sổ được phép dùng trong `SELECT` và `ORDER BY` phù hợp. Có thể dùng tên cửa sổ để tính hạng, rồi sắp kết quả theo alias:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    ROW_NUMBER() OVER w_amount AS amount_position
FROM lesson_orders
WINDOW w_amount AS (
    PARTITION BY customer_id
    ORDER BY amount DESC, order_id ASC
)
ORDER BY customer_id, amount_position;
```

Kết quả từng khách hiện theo thứ tự `amount_position = 1,2,...`.

### 21.1. Phân biệt ba lần “sắp”

Trong một câu SQL phân tích có thể có:

1. `ORDER BY` trong `w_amount`: sắp **logic** để xác định `ROW_NUMBER`.
2. `ORDER BY` trong một **cửa sổ khác**: tạo logic tính toán khác, ví dụ theo thời gian.
3. `ORDER BY` ngoài cùng: sắp **hàng kết quả gửi ra**.

`WINDOW` không làm `ORDER BY` của các cửa sổ tự trở thành thứ tự toàn bộ kết quả. Không có `ORDER BY` cuối cùng, thứ tự hàng đầu ra nhìn thấy có thể thay đổi theo execution plan.

### 21.2. Không nên dựa vào một alias được tạo sau để khai báo cửa sổ trước

Ví dụ, nếu muốn xếp hạng theo một công thức:

```sql
amount * 1.1 AS adjusted_amount
```

rồi `ORDER BY adjusted_amount` bên trong named window cùng SELECT, PostgreSQL thường không cho phép dùng alias `adjusted_amount` ở phạm vi đó. Có thể:

- Lặp biểu thức `amount * 1.1` trong window specification.
- Hoặc đưa công thức vào CTE trước, để `adjusted_amount` trở thành cột đầu vào của SELECT ngoài.

CTE thường dễ đọc hơn khi công thức dài và được sử dụng nhiều lần.

## 22. Named WINDOW và hàm phụ thuộc frame

Không phải mọi hàm cửa sổ dùng frame theo cùng cách.

| Nhóm hàm | Ví dụ | Frame có ý nghĩa thế nào? |
| --- | --- | --- |
| Window aggregate | `SUM`, `AVG`, `COUNT`, `MIN`, `MAX` | Frame quyết định các hàng được tính, nếu có frame cụ thể. |
| Navigation/value | `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` | Thường phụ thuộc frame; frame mặc định có thể gây bất ngờ. |
| Offset | `LAG`, `LEAD` | Dựa trên thứ tự và phân vùng; không dùng frame giống `SUM`. |
| Ranking | `ROW_NUMBER`, `RANK`, `DENSE_RANK` | Chủ yếu dựa trên phân vùng và thứ tự; frame không định nghĩa cách đánh hạng theo kiểu tổng lũy kế. |

Đây là lý do **không nên đặt frame trong một named window dùng chung cho mọi hàm** nếu không có chủ đích.

### 22.1. Thiết kế thực tế nên có cửa sổ nền không frame

```sql
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
    ),
    w_entire AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND UNBOUNDED FOLLOWING
    )
```

Khi dùng:

- `LAG(amount) OVER w_time`.
- `ROW_NUMBER() OVER w_time`.
- `SUM(amount) OVER w_running`.
- `LAST_VALUE(order_id) OVER w_entire`.
- `SUM(amount) OVER w_customer` cho tổng toàn khách không cần thứ tự.

Mỗi tên mô tả **đúng mức cấu hình** tương ứng với công thức.

## 23. WINDOW và NULL

Mệnh đề `WINDOW` chỉ tổ chức đặc tả. Các quy tắc `NULL` của window function vẫn như khi viết `OVER (...)` trực tiếp.

### 23.1. NULL trong PARTITION BY

Nếu cột phân vùng cho phép `NULL`, các hàng có cùng giá trị phân vùng `NULL` được gom vào một phân vùng cho mục đích cửa sổ theo ngữ nghĩa `PARTITION BY`.

Ví dụ giả định có bảng `optional_orders` với `customer_id` nullable:

```sql
SELECT
    order_id,
    customer_id,
    COUNT(*) OVER w_customer AS count_in_partition
FROM optional_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
);
```

Những đơn có `customer_id IS NULL` có thể được tính trong cùng phân vùng. Điều đó khác với phép so sánh `customer_id = NULL` trong `WHERE`, vốn không cho `TRUE`.

### 23.2. NULL trong ORDER BY

Nếu sắp theo cột nullable, vị trí `NULL` có thể khác theo DBMS hoặc theo các lựa chọn `NULLS FIRST/LAST`.

Trên PostgreSQL:

```sql
WINDOW w_sort AS (
    PARTITION BY customer_id
    ORDER BY ordered_at ASC NULLS LAST, order_id ASC
)
```

Nếu nghiệp vụ muốn đơn thiếu thời điểm đứng cuối, đặt quy tắc tường minh. Với DBMS không hỗ trợ `NULLS LAST` cùng cú pháp, có thể dùng biểu thức `CASE` trong `ORDER BY` hoặc cú pháp tương đương.

### 23.3. NULL trong aggregate window

`SUM(amount) OVER w_customer` thường bỏ qua giá trị `amount IS NULL`. `COUNT(amount)` đếm giá trị amount không NULL, còn `COUNT(*)` đếm mọi hàng của frame/phân vùng.

Nếu tất cả giá trị thích hợp đều NULL, `SUM` có thể trả NULL. Đổi tên cửa sổ không làm `SUM` tự trả 0. Nếu nghiệp vụ cần 0, hãy dùng `COALESCE` ở vị trí thích hợp.

## 24. Named WINDOW không thay GROUP BY hay truy vấn con

Một câu dễ nhầm:

> “Đã khai báo `WINDOW w_customer AS (PARTITION BY customer_id)` thì không cần `GROUP BY customer_id` nữa.”

Điều này **không đúng** nếu yêu cầu là **một hàng cho mỗi khách**.

### 24.1. GROUP BY trả mức nhóm

```sql
SELECT
    customer_id,
    SUM(amount) AS customer_total
FROM lesson_orders
GROUP BY customer_id
ORDER BY customer_id;
```

Trả **3 hàng**: `(1,500)`, `(2,500)`, `(3,200)`.

### 24.2. WINDOW giữ mức chi tiết

```sql
SELECT
    order_id,
    customer_id,
    SUM(amount) OVER w_customer AS customer_total
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
```

Trả **8 hàng** — mỗi đơn giữ nguyên.

### 24.3. Truy vấn con có thể kết hợp với WINDOW

```sql
WITH totals AS (
    SELECT customer_id, SUM(amount) AS customer_total
    FROM lesson_orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    customer_total,
    RANK() OVER w_spending AS spending_rank
FROM totals
WINDOW w_spending AS (
    ORDER BY customer_total DESC
)
ORDER BY spending_rank, customer_id;
```

Trả **3 hàng khách**, có thứ hạng theo tổng tiền. Ở đây:

- CTE đặt tên tập tổng theo khách.
- `GROUP BY` thực hiện tổng hợp.
- `WINDOW` đặt tên thứ tự để `RANK` sử dụng.

Các công cụ **phối hợp**, chứ không thay thế nhau theo cách 1–1.

## 25. WINDOW có làm truy vấn nhanh hơn không?

**Không thể khẳng định chỉ vì đã đặt tên.** Hai câu SQL:

```sql
SUM(amount) OVER (PARTITION BY customer_id)
COUNT(*) OVER (PARTITION BY customer_id)
```

và:

```sql
SUM(amount) OVER w_customer
COUNT(*) OVER w_customer
WINDOW w_customer AS (PARTITION BY customer_id)
```

mô tả cùng hai phép tính với cùng đặc tả. Việc đổi từ **cấu hình viết lặp** sang **cấu hình có tên** chủ yếu cải thiện **khả năng đọc, tránh lệch logic và bảo trì**.

### 25.1. Bộ tối ưu có thể nhận biết cửa sổ giống nhau

Nhiều DBMS có thể tối ưu những window functions có đặc tả tương thích, chẳng hạn chia sẻ một lần sắp xếp. Đặt tên cửa sổ có thể giúp người đọc thấy phần chung, nhưng không phải lời hứa engine chỉ quét dữ liệu một lần.

Nếu hai window functions có:

- Khóa phân vùng khác nhau.
- Khóa thứ tự khác nhau.
- Frame khác nhau.
- Bộ lọc và mức nhóm đầu vào khác nhau.

thì chi phí vật lý có thể khác nhiều; việc dùng chung một tên không thể ép những phép tính khác nhau trở thành giống nhau.

### 25.2. Xem execution plan thay vì suy đoán

Trên PostgreSQL:

```sql
EXPLAIN
SELECT
    order_id,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER w_time AS chronological_number
FROM lesson_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    );
```

Kế hoạch cho biết engine lựa chọn sort, window aggregation và các bước khác như thế nào trong môi trường hiện tại. Với truy vấn phức tạp, có thể dùng `EXPLAIN ANALYZE` trong môi trường an toàn để xem số liệu thực thi; nó **thực sự chạy câu SQL**.

### 25.3. Khi nào nên tối ưu truy vấn thay vì chỉ đổi tên?

Nếu cửa sổ trên hàng triệu đơn chạy chậm, nên xem:

- Chỉ mục trên các khóa lọc, phân vùng và sắp xếp.
- Có đang chọn **quá nhiều hàng hoặc cột** không.
- Có `JOIN` một-nhiều gây nhân hàng trước cửa sổ không.
- Có cần cửa sổ với `ORDER BY` khác nhau không.
- Có thể lọc tập nguồn hợp lệ sớm hơn không.
- Frame nào được dùng và có gây tính toán lớn không.
- Có thể tính một kết quả tổng hợp cấp khách trước khi nối không.

`WINDOW` giúp **tổ chức** phép tính; nó không thay các quyết định thiết kế dữ liệu và plan.

## 26. Khả năng hỗ trợ theo hệ quản trị SQL

Mệnh đề `WINDOW` và cú pháp **named windows** không phải lúc nào cũng có ở mọi hệ hoặc mọi phiên bản.

| DBMS | Tình trạng đáng biết | Gợi ý sử dụng |
| --- | --- | --- |
| **PostgreSQL** | Hỗ trợ `WINDOW ... AS (...)`, `OVER window_name` và mở rộng named window với quy tắc riêng | Môi trường chính của ví dụ trong bài |
| **MySQL 8.0+** | Hỗ trợ window functions và named window qua mệnh đề `WINDOW`; giới hạn kế thừa/biến đổi cần xem phiên bản | Có thể dùng `WINDOW w AS (...)`, kiểm tra cú pháp mở rộng cụ thể |
| **SQLite 3.25.0+** | Có window functions và mệnh đề `WINDOW`; cũng có cơ chế *window chaining* với các giới hạn | Có thể đặt tên và kế thừa cấu hình nền phù hợp |
| **SQL Server 2022 (16.x)+** | Có mệnh đề `WINDOW`; yêu cầu mức tương thích database phù hợp, thường **160 trở lên** | Không dùng named window như tính năng sẵn có trên SQL Server 2019 hoặc bản cũ hơn |
| **Oracle Database** | Hỗ trợ analytic/window functions lâu đời; **khả năng đặt tên bằng WINDOW tùy phiên bản** | Với phiên bản không hỗ trợ, lặp `OVER (...)` hoặc tái cấu trúc truy vấn |
| **Hệ thống khác** | Có thể có `QUALIFY`, `WINDOW`, các biến thể kế thừa hoặc giới hạn khác | Xem tài liệu của DBMS và phiên bản thực tế |

**Thông điệp quan trọng:** Có `ROW_NUMBER() OVER (...)` **không tự suy ra** DBMS cũng hỗ trợ mệnh đề `WINDOW w AS (...)`. Đây là hai mức tính năng liên quan nhưng không hoàn toàn trùng nhau.

### 26.1. PostgreSQL

Ví dụ chuẩn cho bài:

```sql
SELECT
    order_id,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER w_order AS rn
FROM lesson_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_order AS (
        w_customer ORDER BY ordered_at, order_id
    )
ORDER BY order_id;
```

PostgreSQL cho phép named window được tham chiếu hoặc dùng làm nền theo những quy tắc đã nêu, đặc biệt về `PARTITION BY`, `ORDER BY` và frame.

### 26.2. MySQL 8.0+

MySQL 8.0 hỗ trợ cú pháp tương tự:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER w_amount AS amount_position
FROM lesson_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_amount AS (
        w_customer ORDER BY amount DESC, order_id ASC
    )
ORDER BY customer_id, amount_position;
```

Nếu đang ở MySQL cũ hơn 8.0, cần xác minh hỗ trợ window functions; không thể chỉ đổi `WINDOW` thành cú pháp khác để có toàn bộ khả năng window function nếu engine chưa hỗ trợ `OVER` phù hợp.

### 26.3. SQLite

SQLite có named window:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER w_time AS sequence_number
FROM lesson_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    )
ORDER BY customer_id, sequence_number;
```

SQLite hỗ trợ **window chaining**, nhưng cửa sổ nền trong một phép kế thừa không được có frame nếu định nghĩa mới cần bổ sung frame; cũng không được đưa `PARTITION BY` mới vào phần mở rộng khi quy tắc kế thừa yêu cầu dùng phân vùng của nền.

Tên cửa sổ **không phải object lưu trong database SQLite**; nó chỉ tồn tại trong câu SQL đang chạy.

### 26.4. SQL Server 2022 trở lên

SQL Server 2022 (16.x) bổ sung mệnh đề `WINDOW`. Cần kiểm tra **database compatibility level** — thường phải là **160 trở lên** cho tính năng này.

Ví dụ T-SQL trên môi trường hỗ trợ:

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER w_time AS chronological_number
FROM dbo.lesson_orders
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    )
ORDER BY customer_id, chronological_number;
```

Trên SQL Server 2019 hoặc database SQL Server không bật mức tương thích cần thiết, mệnh đề `WINDOW` có thể không hợp lệ dù các hàm `ROW_NUMBER() OVER (...)` vẫn dùng được.

Trong các hệ cũ, dùng giải pháp **lặp đặc tả trong từng `OVER (...)`** như mục 27.

### 26.5. Oracle Database và các hệ có mức hỗ trợ khác nhau

Nhiều phiên bản Oracle có đầy đủ các **analytic functions** như `ROW_NUMBER`, `RANK`, `LAG` và `SUM(...) OVER (...)`, nhưng không nên mặc định bản Oracle nào cũng hiểu cùng cú pháp `WINDOW window_name AS (...)`.

Một truy vấn chỉ dùng `OVER (...)` trực tiếp thường dễ chuyển hơn giữa các phiên bản Oracle cũ và các DBMS có window functions nhưng không có named window.

Nếu môi trường mục tiêu hỗ trợ named window mới hơn, hãy dùng tài liệu chính thức của đúng **phiên bản/release** để xác nhận cú pháp và giới hạn kế thừa.

## 27. Viết tương đương khi DBMS không hỗ trợ WINDOW

Giả sử cần tính tổng tiền theo khách và thứ tự thời gian.

**Phiên bản dùng named windows:**

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER w_time AS chronological_number
FROM lesson_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    )
ORDER BY customer_id, order_id;
```

**Phiên bản không cần mệnh đề WINDOW:**

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
    ) AS customer_total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS chronological_number
FROM lesson_orders
ORDER BY customer_id, order_id;
```

Hai câu thể hiện cùng ý nghĩa trên những DBMS hỗ trợ các hàm và cú pháp `OVER` tương ứng.

### 27.1. Cái gì thay đổi?

Chỉ có **cách tổ chức đặc tả**:

- Bản thứ nhất dùng tên `w_customer`, `w_time`.
- Bản thứ hai viết trực tiếp `PARTITION BY` và `ORDER BY` trong mỗi `OVER (...)`.

Không cần thêm bảng tạm, không cần thay đổi dữ liệu, cũng không cần giả lập một cửa sổ đã đặt tên bằng `JOIN`.

### 27.2. Nếu biểu thức quá dài thì sao?

Nếu phải lặp một công thức tính cột trung gian trong nhiều window specifications, có thể tạo CTE chứa công thức ấy rồi dùng ở cửa sổ cấp ngoài:

```sql
WITH normalized AS (
    SELECT
        order_id,
        customer_id,
        ordered_at,
        amount,
        CASE
            WHEN order_status = 'PAID' THEN amount
            ELSE 0
        END AS paid_amount
    FROM lesson_orders
)
SELECT
    order_id,
    customer_id,
    SUM(paid_amount) OVER (
        PARTITION BY customer_id
    ) AS paid_total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS chronological_number
FROM normalized
ORDER BY customer_id, chronological_number;
```

CTE giúp đặt tên **giá trị được tính**, còn named window giúp đặt tên **đặc tả phân vùng/thứ tự/frame**. Chúng giải quyết hai nhu cầu khác nhau.

## 28. Những lỗi cú pháp và lỗi logic dễ gặp

| Lỗi | Vì sao không đúng | Cách sửa |
| --- | --- | --- |
| Dùng `WINDOW` như một bảng trong `FROM` | Tên window chỉ là đặc tả, không phải quan hệ | Dùng bảng, CTE, derived table hoặc view |
| Khai báo `WINDOW` trước `WHERE` hoặc sau `ORDER BY` ngoài cùng | Sai vị trí mệnh đề theo cú pháp PostgreSQL | Đặt sau `HAVING`/`GROUP BY` khi có, trước `ORDER BY` cuối |
| Viết `OVER WINDOW w AS (...)` | Đặt khai báo ở sai vị trí | `OVER w` và khai báo `WINDOW w AS (...)` |
| Dùng tên `w` chưa khai báo trong khối SELECT | Tên cửa sổ có phạm vi cục bộ | Khai báo `WINDOW w AS (...)` đúng khối |
| Muốn dùng lại tên WINDOW từ CTE ở truy vấn ngoài | CTE chỉ xuất cột, không xuất tên cửa sổ | Khai báo lại WINDOW hoặc xuất cột đã tính |
| Cố thêm `PARTITION BY` lên base đã có phân vùng | Giới hạn mở rộng named window | Tạo cửa sổ độc lập |
| Cố thêm `ORDER BY` lên base đã có thứ tự | Không thể ghi đè thứ tự theo cách kế thừa đó | Dựa vào base chỉ phân vùng, tạo hai nhánh sắp khác nhau |
| Cố đổi frame của cửa sổ đã có frame | Giới hạn kế thừa và sao chép | Kế thừa từ base **chưa có frame** |
| Dùng `OVER (w)` với base có frame trên PostgreSQL | Không tương đương hoàn toàn với tham chiếu trực tiếp | Dùng `OVER w` |
| Dùng `SUM(amount) OVER w_ordered` nhưng muốn tổng toàn phân vùng | Cửa sổ có `ORDER BY` và frame mặc định thường thành lũy kế | Dùng window không order hoặc frame toàn phân vùng |
| Cho `ROW_NUMBER` và `RANK` dùng cùng thứ tự có ID, vẫn mong đồng hạng theo tiền | ID duy nhất phá peer groups | Tạo window cho ROW_NUMBER với ID, window cho RANK chỉ theo tiền |
| Tin `ORDER BY` trong WINDOW quyết định thứ tự hiển thị | Nó phục vụ phép tính cửa sổ | Có `ORDER BY` cuối câu SQL |
| Dùng window function trong `WHERE` cùng cấp trên PostgreSQL | `WHERE` được đánh giá trước window về ngữ nghĩa | CTE/derived table rồi lọc ngoài |
| Tham chiếu alias SELECT cùng cấp trong WINDOW | Alias chưa có phạm vi dùng phù hợp | Đưa biểu thức vào CTE/derived table |
| Dùng `WINDOW` trên SQL Server cũ | Không phải phiên bản nào cũng hỗ trợ | Dùng `OVER (...)` trực tiếp hoặc nâng môi trường phù hợp |
| Coi WINDOW là tùy chọn tối ưu bắt buộc | Không bảo đảm plan tốt hơn | Dùng để rõ logic, đo bằng EXPLAIN khi cần |

## 29. Bài tập thực hành có lời giải

Tất cả bài dưới đây dùng `lesson_orders` ở mục 2 và cú pháp PostgreSQL.

### Bài 1. Đặt tên một phân vùng khách hàng

**Yêu cầu:** Mỗi đơn hiển thị tổng tiền và số đơn của khách, không viết lặp `PARTITION BY customer_id`.

```sql
SELECT
    order_id,
    customer_id,
    amount,
    SUM(amount) OVER w_customer AS customer_total,
    COUNT(*) OVER w_customer AS order_count
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
```

**Đáp án:** tám hàng; tổng/đếm của khách 1 là `500/3`, khách 2 là `500/3`, khách 3 là `200/2`.

### Bài 2. Đặt tên cửa sổ xếp thứ tự theo thời gian

**Yêu cầu:** Mỗi khách được đánh số các đơn theo thời gian tăng dần; nếu cùng thời gian, mã đơn nhỏ hơn đứng trước.

```sql
SELECT
    order_id,
    customer_id,
    ROW_NUMBER() OVER w_time AS chronological_number
FROM lesson_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, chronological_number;
```

**Đáp án:** khách 1 có `201 → 1`, `202 → 2`, `203 → 3`; khách 2 có `204 → 1`, `205 → 2`, `206 → 3`; khách 3 có `207 → 1`, `208 → 2`.

### Bài 3. Dùng chung cửa sổ cho LAG và LEAD

```sql
SELECT
    order_id,
    customer_id,
    LAG(order_id) OVER w_time AS previous_id,
    LEAD(order_id) OVER w_time AS next_id
FROM lesson_orders
WINDOW w_time AS (
    PARTITION BY customer_id
    ORDER BY ordered_at, order_id
)
ORDER BY customer_id, ordered_at, order_id;
```

**Đáp án:** với khách 1, `201` có trước `NULL`/sau `202`; `202` có trước `201`/sau `203`; `203` có trước `202`/sau `NULL`.

### Bài 4. Kế thừa cửa sổ phân vùng để thêm thứ tự

```sql
SELECT
    order_id,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER w_time AS rn
FROM lesson_orders
WINDOW
    w_customer AS (
        PARTITION BY customer_id
    ),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    )
ORDER BY customer_id, rn;
```

**Đáp án:** `w_time` kế thừa `PARTITION BY customer_id` và bổ sung `ORDER BY`. `SUM` dùng `w_customer` nên cho **tổng toàn khách**, không phải tổng lũy kế.

### Bài 5. Chỉ rõ frame lũy kế

```sql
SELECT
    customer_id,
    order_id,
    amount,
    SUM(amount) OVER w_running AS running_total
FROM lesson_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
    )
ORDER BY customer_id, ordered_at, order_id;
```

**Đáp án:** khách 1 có tổng lũy kế `100, 300, 500`; khách 2 có `300, 400, 500`; khách 3 có `150, 200`.

### Bài 6. Phát hiện khác biệt giữa RANGE và ROWS

```sql
SELECT
    order_id,
    SUM(amount) OVER w_time_only AS running_total
FROM lesson_orders
WHERE customer_id = 1
WINDOW w_time_only AS (
    ORDER BY ordered_at
)
ORDER BY ordered_at, order_id;
```

**Câu hỏi:** Vì sao đơn `202` đã có tổng `500`?

**Đáp án:** `202` và `203` là peers vì cùng `ordered_at`. Với frame mặc định theo `RANGE` trên PostgreSQL, tổng ở mốc ấy bao gồm cả hai đơn. Muốn tổng từng đơn `100,300,500`, dùng `ROWS` với thứ tự đủ xác định, ví dụ thêm `order_id`.

### Bài 7. Kế thừa để tạo hai frame khác nhau

**Yêu cầu:** Một cửa sổ tính lũy kế, một cửa sổ tính tổng toàn phân vùng dù có thứ tự.

```sql
SELECT
    order_id,
    customer_id,
    SUM(amount) OVER w_running AS running_total,
    SUM(amount) OVER w_full AS full_total
FROM lesson_orders
WINDOW
    w_time AS (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ),
    w_running AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND CURRENT ROW
    ),
    w_full AS (
        w_time ROWS BETWEEN UNBOUNDED PRECEDING
                        AND UNBOUNDED FOLLOWING
    )
ORDER BY customer_id, ordered_at, order_id;
```

**Đáp án:** khách 1 có `running_total = 100,300,500` nhưng `full_total = 500` trên mọi đơn. Khách 2 có `300,400,500` và tổng `500`; khách 3 có `150,200` và tổng `200`.

### Bài 8. Giữ đồng hạng theo số tiền

**Yêu cầu:** `ROW_NUMBER` phải ổn định theo mã đơn; `RANK` phải đồng hạng nếu tiền bằng nhau.

```sql
SELECT
    customer_id,
    order_id,
    amount,
    ROW_NUMBER() OVER w_unique AS rn,
    RANK() OVER w_peers AS amount_rank
FROM lesson_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_unique AS (
        w_customer ORDER BY amount DESC, order_id ASC
    ),
    w_peers AS (
        w_customer ORDER BY amount DESC
    )
ORDER BY customer_id, amount DESC, order_id;
```

**Đáp án:** khách 1 có `rn = 1,2,3` và `amount_rank = 1,1,3` theo các đơn `202,203,201`.

### Bài 9. Lọc đơn có tiền lớn nhất mỗi khách

```sql
WITH ranked AS (
    SELECT
        order_id,
        customer_id,
        amount,
        ROW_NUMBER() OVER w_amount AS rn
    FROM lesson_orders
    WINDOW w_amount AS (
        PARTITION BY customer_id
        ORDER BY amount DESC, order_id ASC
    )
)
SELECT customer_id, order_id, amount
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

**Đáp án:** khách 1 → đơn `202` tiền `200`; khách 2 → đơn `204` tiền `300`; khách 3 → đơn `207` tiền `150`.

### Bài 10. Vì sao alias cùng SELECT không dùng được trong WINDOW?

Ý tưởng:

```sql
-- Không hợp lệ như mong muốn trên PostgreSQL:
SELECT
    amount * 1.1 AS adjusted_amount,
    RANK() OVER w_adjusted AS adjusted_rank
FROM lesson_orders
WINDOW w_adjusted AS (
    ORDER BY adjusted_amount DESC
);
```

**Gợi ý sửa bằng CTE:**

```sql
WITH adjusted AS (
    SELECT
        order_id,
        customer_id,
        amount * 1.1 AS adjusted_amount
    FROM lesson_orders
)
SELECT
    order_id,
    adjusted_amount,
    RANK() OVER w_adjusted AS adjusted_rank
FROM adjusted
WINDOW w_adjusted AS (
    ORDER BY adjusted_amount DESC
)
ORDER BY adjusted_rank, order_id;
```

**Đáp án:** `adjusted_amount` là **cột đầu vào** của truy vấn ngoài nên được phép tham chiếu trong định nghĩa cửa sổ cấp đó.

### Bài 11. WINDOW có thay đổi số hàng không?

```sql
SELECT
    order_id,
    customer_id,
    SUM(amount) OVER w_customer AS customer_total
FROM lesson_orders
WINDOW w_customer AS (PARTITION BY customer_id);
```

**Đáp án:** vẫn **8 hàng**. Muốn một hàng mỗi khách:

```sql
SELECT customer_id, SUM(amount) AS customer_total
FROM lesson_orders
GROUP BY customer_id
ORDER BY customer_id;
```

có **3 hàng**. `WINDOW` là cách đặt tên cửa sổ, không phải mệnh đề tổng hợp thành một hàng mỗi nhóm.

### Bài 12. Không hỗ trợ WINDOW: viết lại thế nào?

Viết lại:

```sql
SELECT
    order_id,
    SUM(amount) OVER w_customer AS customer_total,
    ROW_NUMBER() OVER w_time AS rn
FROM lesson_orders
WINDOW
    w_customer AS (PARTITION BY customer_id),
    w_time AS (
        w_customer ORDER BY ordered_at, order_id
    );
```

thành:

```sql
SELECT
    order_id,
    SUM(amount) OVER (
        PARTITION BY customer_id
    ) AS customer_total,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS rn
FROM lesson_orders;
```

**Đáp án:** các giá trị tính toán tương đương. Nếu cần thứ tự hiển thị ổn định, thêm `ORDER BY` cuối cùng ở **cả hai** phiên bản.

### Bài 13. Xếp hạng các khách theo tổng tiền

```sql
WITH customer_totals AS (
    SELECT
        customer_id,
        SUM(amount) AS total_amount
    FROM lesson_orders
    GROUP BY customer_id
)
SELECT
    customer_id,
    total_amount,
    RANK() OVER w_total AS spending_rank
FROM customer_totals
WINDOW w_total AS (
    ORDER BY total_amount DESC
)
ORDER BY spending_rank, customer_id;
```

**Đáp án:** khách 1 và 2 cùng tổng `500`, đồng hạng 1; khách 3 tổng `200`, hạng 3.

### Bài 14. Đổi phần tổng PAID nhưng giữ đơn NEW

```sql
SELECT
    order_id,
    customer_id,
    order_status,
    SUM(
        CASE
            WHEN order_status = 'PAID' THEN amount
            ELSE 0
        END
    ) OVER w_customer AS paid_total
FROM lesson_orders
WINDOW w_customer AS (
    PARTITION BY customer_id
)
ORDER BY customer_id, order_id;
```

**Đáp án:** cả tám đơn xuất hiện; `paid_total` lần lượt là `300`, `400` hoặc `150` theo khách. Nếu thêm `WHERE order_status='PAID'`, các đơn `NEW` bị **loại khỏi kết quả**, nên không còn đáp ứng yêu cầu.

## 30. Quy trình dùng WINDOW trong truy vấn thực tế

Khi một câu SQL có nhiều hàm cửa sổ, có thể làm theo các bước:

1. **Xác định mức dữ liệu đầu ra:** một hàng mỗi đơn hay mỗi khách? Nếu cần gom hàng, dùng `GROUP BY`/CTE ở bước thích hợp.
2. **Liệt kê các phép tính cửa sổ:** tổng theo khách, số đơn, thứ hạng, tổng lũy kế, giá trị hàng trước.
3. **Tách các phần đặc tả:** phân vùng nào giống nhau, thứ tự nào giống nhau, frame nào khác nhau?
4. **Đặt tên theo ý nghĩa:** `w_customer`, `w_time`, `w_running`, `w_full` thay vì một loạt `w1`, `w2`.
5. **Dùng chung base chưa có frame** nếu cần nhiều biến thể thứ tự/frame.
6. **Không kế thừa sai quy tắc:** đừng ghi đè `PARTITION BY`, `ORDER BY` hoặc frame của nền khi DBMS không cho phép.
7. **Nhớ rằng ORDER BY ảnh hưởng SUM/AVG dạng cửa sổ:** kiểm tra lũy kế với tổng toàn phân vùng.
8. **Phân biệt các hàng đồng hạng:** `RANK` có thể cần peers theo tiền, `ROW_NUMBER` lại cần khóa phá hòa để ổn định.
9. **Tính trong CTE nếu cần lọc theo kết quả window:** `WHERE` cùng cấp thường không dùng trực tiếp window function trên PostgreSQL.
10. **Xác định phạm vi tên:** named window chỉ dùng trong khối `SELECT` của nó; không phải object lưu được.
11. **Kiểm tra phương ngữ và phiên bản:** `OVER` hỗ trợ không có nghĩa `WINDOW` được hỗ trợ; SQL Server 2022 cần compatibility level phù hợp.
12. **Đo hiệu năng nếu cần:** đặt tên cải thiện tính bảo trì, không thay thế thiết kế chỉ mục và kế hoạch truy vấn.

**Điểm ghi nhớ:** `WINDOW name AS (...)` là một cách **đặt tên cho đặc tả cửa sổ** khi hệ quản trị hỗ trợ. Sử dụng `OVER name` để tham chiếu trực tiếp; sử dụng `OVER (name ...)` hoặc khai báo cửa sổ kế thừa khi cần bổ sung thành phần và được DBMS cho phép. Named window giúp câu SQL gọn, nhất quán và dễ mở rộng, nhưng **không tạo dữ liệu mới, không làm thay đổi số hàng, không thay `GROUP BY` và không tự bảo đảm tối ưu hiệu năng**. Điều quan trọng nhất vẫn là hiểu đúng **phân vùng, thứ tự, frame và phạm vi tên** của từng phép tính.
