# Tạo cột cờ từ điều kiện nghiệp vụ

Trong một ứng dụng đặt hàng, bảng dữ liệu thường lưu các thông tin gốc như trạng thái đơn, số tiền phải trả, số tiền đã thanh toán và ngày đến hạn. Tuy nhiên, giao diện hoặc báo cáo lại cần những câu trả lời ngắn gọn:

- Đơn hàng **đã thanh toán đủ** chưa?
- Đơn hàng **quá hạn** chưa?
- Đơn hàng có **bị hủy** không?
- Đơn hàng có **thiếu ngày đến hạn** không?
- Đơn hàng có thuộc nhóm **giá trị cao** không?

Ta có thể chuyển những điều kiện nghiệp vụ này thành **cột cờ** (*flag column*) ngay trong kết quả SQL. Ví dụ, cờ `is_overdue = 1` biểu thị đơn hàng quá hạn, còn `is_overdue = 0` biểu thị không quá hạn theo một quy tắc đã xác định.

Công cụ phổ biến nhất là biểu thức **`CASE WHEN ... THEN ... ELSE ... END`**. Bài học sẽ chỉ ra cách định nghĩa cờ rõ nghĩa, xử lý `NULL`, kết hợp nhiều điều kiện, ưu tiên quy tắc nghiệp vụ, dùng cờ trong lọc và thống kê, cũng như quyết định khi nào nên tính động hoặc lưu cờ lâu dài.

## 1. Cột cờ là gì?

**Cột cờ** là một giá trị dùng để thể hiện kết quả của một điều kiện hoặc một quyết định nghiệp vụ. Cờ thường có hai trạng thái:

| Giá trị cờ | Ý nghĩa thông dụng |
| --- | --- |
| `1` hoặc `TRUE` | Điều kiện đúng |
| `0` hoặc `FALSE` | Điều kiện sai |

Ví dụ:

| order_id | total_amount | paid_amount | is_fully_paid |
| ---: | ---: | ---: | ---: |
| 101 | 1200000 | 1200000 | 1 |
| 102 | 300000 | 100000 | 0 |
| 103 | 500000 | 0 | 0 |

Ở đây, quy tắc là **đã thanh toán đủ nếu `paid_amount >= total_amount`**.

Cờ là **kết quả của một phép tính từ dữ liệu và quy tắc**, không nhất thiết là một cột được lưu vật lý trong bảng. SQL có thể tạo ra cột này lúc truy vấn:

```sql
SELECT
    order_id,
    total_amount,
    paid_amount,
    CASE
        WHEN paid_amount >= total_amount THEN 1
        ELSE 0
    END AS is_fully_paid
FROM shop_orders;
```

Các mục cần phân biệt:

- **Dữ liệu gốc:** `paid_amount`, `total_amount`, `order_status`, `due_date`.
- **Điều kiện nghiệp vụ:** `paid_amount >= total_amount`.
- **Cột cờ suy ra:** `is_fully_paid`, mang giá trị `1` hoặc `0`.
- **Nhãn nghiệp vụ nhiều trạng thái:** `'PAID'`, `'OVERDUE'`, `'CANCELLED'`; vẫn có thể tạo bằng `CASE`, nhưng không còn là cờ nhị phân đơn giản.

### 1.1. Cờ không thay thế quy tắc nghiệp vụ

Một điều kiện “quá hạn” có thể được hiểu theo nhiều cách:

- Ngày đến hạn đã qua và **chưa thanh toán đủ**.
- Ngày đến hạn đã qua, bất kể thanh toán.
- Chỉ tính những đơn **đang hoạt động**.
- Bỏ qua những đơn **đã hủy hoặc hoàn thành**.
- Nếu chưa có ngày đến hạn, xem là **không quá hạn** hay **chưa xác định**?

Trước khi viết SQL, phải xác định ý nghĩa mong muốn. Hai truy vấn đều có thể chạy đúng cú pháp nhưng trả cờ khác nhau vì hai cách hiểu nghiệp vụ khác nhau.

## 2. Chuẩn bị bảng và dữ liệu mẫu

Các ví dụ chính dùng cú pháp SQL quan hệ phổ biến, với **PostgreSQL** làm môi trường thực hành. Dùng một database thử nghiệm để tạo bảng `shop_orders`:

```sql
CREATE TABLE shop_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_status VARCHAR(20) NOT NULL
        CHECK (order_status IN (
            'NEW', 'CONFIRMED', 'COMPLETED', 'CANCELLED'
        )),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0),
    paid_amount NUMERIC(12, 2) NOT NULL
        CHECK (paid_amount >= 0),
    due_date DATE,
    shipped_at TIMESTAMP
);
```

Thêm chín đơn hàng:

```sql
INSERT INTO shop_orders (
    order_id, customer_id, order_status,
    total_amount, paid_amount, due_date, shipped_at
)
VALUES
    (101, 10, 'CONFIRMED', 1200000, 1200000, '2026-11-10', NULL),
    (102, 10, 'CONFIRMED',  300000,  100000, '2026-11-20', NULL),
    (103, 11, 'CANCELLED',  500000,       0, '2026-11-01', NULL),
    (104, 12, 'COMPLETED',  900000,  900000, '2026-11-12',
        '2026-11-12 16:00:00'),
    (105, 13, 'NEW',        250000,       0, NULL, NULL),
    (106, 14, 'CONFIRMED',  700000,       0, '2026-11-05', NULL),
    (107, 15, 'CONFIRMED',       0,       0, '2026-11-14', NULL),
    (108, 16, 'CONFIRMED',  700000,  700000, '2026-11-14', NULL),
    (109, 17, 'CONFIRMED',  450000,       0, NULL, NULL);
```

Để kết quả của bài thực hành không thay đổi theo ngày chạy, ta dùng **ngày đánh giá cố định 14/11/2026** trong các ví dụ quá hạn.

Bảng tóm tắt dữ liệu:

| order_id | order_status | total_amount | paid_amount | due_date | shipped_at |
| ---: | --- | ---: | ---: | --- | --- |
| 101 | CONFIRMED | 1200000 | 1200000 | 2026-11-10 | `NULL` |
| 102 | CONFIRMED | 300000 | 100000 | 2026-11-20 | `NULL` |
| 103 | CANCELLED | 500000 | 0 | 2026-11-01 | `NULL` |
| 104 | COMPLETED | 900000 | 900000 | 2026-11-12 | Có giá trị |
| 105 | NEW | 250000 | 0 | `NULL` | `NULL` |
| 106 | CONFIRMED | 700000 | 0 | 2026-11-05 | `NULL` |
| 107 | CONFIRMED | 0 | 0 | 2026-11-14 | `NULL` |
| 108 | CONFIRMED | 700000 | 700000 | 2026-11-14 | `NULL` |
| 109 | CONFIRMED | 450000 | 0 | `NULL` | `NULL` |

Những trường hợp được cài vào dữ liệu mẫu có chủ đích: đơn thanh toán đủ, thanh toán một phần, quá hạn, hủy, ngày đến hạn thiếu, giá trị bằng không và ngày đến hạn đúng ngày đánh giá.

## 3. CASE WHEN: cách tạo cột cờ phổ biến nhất

Dạng cơ bản của **searched CASE**:

```sql
CASE
    WHEN dieu_kien_1 THEN gia_tri_1
    WHEN dieu_kien_2 THEN gia_tri_2
    ...
    ELSE gia_tri_mac_dinh
END
```

SQL kiểm tra các nhánh `WHEN` theo thứ tự logic. Biểu thức `CASE` trả **giá trị của nhánh `THEN` đầu tiên có điều kiện là `TRUE`**. Nếu không nhánh nào đúng, nó trả `ELSE`; nếu không có `ELSE`, kết quả là `NULL`.

Với cột cờ nhị phân:

```sql
CASE
    WHEN dieu_kien THEN 1
    ELSE 0
END AS flag_name
```

### 3.1. Ví dụ: cờ thanh toán đủ

```sql
SELECT
    order_id,
    total_amount,
    paid_amount,
    CASE
        WHEN paid_amount >= total_amount THEN 1
        ELSE 0
    END AS is_fully_paid
FROM shop_orders
ORDER BY order_id;
```

Kết quả cờ:

| order_id | is_fully_paid | Diễn giải |
| ---: | ---: | --- |
| 101 | 1 | Đã thanh toán đủ |
| 102 | 0 | Còn thiếu |
| 103 | 0 | Chưa thanh toán |
| 104 | 1 | Đã thanh toán đủ |
| 105 | 0 | Chưa thanh toán |
| 106 | 0 | Chưa thanh toán |
| 107 | 1 | Tổng tiền và đã trả đều bằng 0 |
| 108 | 1 | Đã thanh toán đủ |
| 109 | 0 | Chưa thanh toán |

**Điểm ranh giới:** theo quy tắc `paid_amount >= total_amount`, đơn `107` có `0 >= 0` nên cờ bằng `1`. Nếu nghiệp vụ không coi đơn giá trị 0 là “đã thanh toán”, phải sửa **định nghĩa điều kiện**, ví dụ:

```sql
CASE
    WHEN total_amount > 0
         AND paid_amount >= total_amount
    THEN 1
    ELSE 0
END AS is_fully_paid
```

Không nên âm thầm đổi từ `>=` sang `>`, vì phép `paid_amount > total_amount` sẽ chỉ đánh dấu những trường hợp trả **nhiều hơn** số phải trả.

### 3.2. CASE là biểu thức, không phải lệnh điều khiển luồng ứng dụng

`CASE` có thể được đặt ở nhiều vị trí mà SQL chấp nhận một **biểu thức**: trong `SELECT`, `ORDER BY`, `GROUP BY` phù hợp, điều kiện `WHERE`, hoặc biểu thức cập nhật `UPDATE ... SET`.

Ví dụ:

```sql
SELECT
    order_id,
    CASE
        WHEN order_status = 'CANCELLED' THEN 'Đã hủy'
        ELSE 'Chưa hủy'
    END AS cancellation_label
FROM shop_orders;
```

Biểu thức không tự cập nhật `order_status` hay tạo cột vật lý mới. Nó chỉ xác định **giá trị trong tập kết quả** của câu truy vấn.

### 3.3. CASE so với CASE dạng đơn giản

Ngoài `CASE WHEN dieu_kien`, SQL có dạng **simple CASE**:

```sql
CASE order_status
    WHEN 'CANCELLED' THEN 1
    ELSE 0
END AS is_cancelled
```

Dạng đơn giản so sánh một biểu thức với các giá trị cụ thể. Dạng tìm kiếm (*searched CASE*) linh hoạt hơn khi phải kết hợp nhiều điều kiện:

```sql
CASE
    WHEN order_status = 'CANCELLED'
         OR order_status = 'COMPLETED'
    THEN 1
    ELSE 0
END AS is_closed
```

Với những cờ từ quy tắc nghiệp vụ phức hợp, **searched CASE** thường dễ đọc và mở rộng.

## 4. Chọn kiểu dữ liệu cho cột cờ: số, Boolean hay chữ?

Cùng một điều kiện có thể tạo nhiều dạng giá trị.

### 4.1. Cờ số 0/1

```sql
SELECT
    order_id,
    CASE
        WHEN order_status = 'CANCELLED' THEN 1
        ELSE 0
    END AS is_cancelled
FROM shop_orders;
```

**Ưu điểm:** dễ hiển thị và hỗ trợ đếm/tổng hợp có điều kiện bằng `SUM` trong nhiều DBMS. Các biểu thức `CASE THEN 1 ELSE 0` cũng tương đối dễ chuyển đổi giữa các hệ quản trị SQL.

### 4.2. Cờ Boolean

Trên PostgreSQL:

```sql
SELECT
    order_id,
    CASE
        WHEN order_status = 'CANCELLED' THEN TRUE
        ELSE FALSE
    END AS is_cancelled
FROM shop_orders;
```

Có thể viết gọn bằng biểu thức logic:

```sql
SELECT
    order_id,
    (order_status = 'CANCELLED') AS is_cancelled
FROM shop_orders;
```

Ở bảng mẫu, `order_status` được khai báo `NOT NULL` nên biểu thức trực tiếp cho `TRUE` hoặc `FALSE`. Nếu cột nguồn có thể `NULL`, phép `=` có thể trả kết quả logic **`UNKNOWN`**, được biểu diễn bằng SQL `NULL`. Dùng `CASE ... ELSE FALSE` khi nghiệp vụ muốn quy tất cả các trường hợp không được xác nhận đúng thành sai.

### 4.3. Cờ chữ

```sql
SELECT
    order_id,
    CASE
        WHEN paid_amount >= total_amount THEN 'YES'
        ELSE 'NO'
    END AS payment_flag
FROM shop_orders;
```

Kiểu này phù hợp với một số báo cáo hoặc định dạng trao đổi dữ liệu, nhưng chuỗi `'YES'`/`'NO'` là giá trị văn bản có thể bị viết không thống nhất. Ở tầng ứng dụng, Boolean thường diễn đạt tốt hơn khi chỉ có hai trạng thái.

### 4.4. Trường hợp không thể quyết định: dùng trạng thái thứ ba

Nếu dữ liệu không đủ để kết luận, chỉ dùng `0` và `1` có thể làm mất thông tin. Có thể giữ `NULL` hoặc dùng trạng thái rõ nghĩa như `'UNKNOWN'`.

Ví dụ ngày đến hạn chưa có:

```sql
SELECT
    order_id,
    CASE
        WHEN due_date IS NULL THEN 'UNKNOWN'
        WHEN due_date < DATE '2026-11-14' THEN 'PAST_DUE_DATE'
        ELSE 'NOT_PAST_DUE_DATE'
    END AS due_date_state
FROM shop_orders;
```

Đây là **nhãn ba trạng thái**. Nó phân biệt “chưa có dữ liệu để đánh giá” với “đã đánh giá và không quá hạn”.

## 5. Kết hợp AND, OR, NOT để tạo cờ nghiệp vụ

Một cờ không nhất thiết được quyết định bằng một phép so sánh duy nhất.

### 5.1. Cờ đơn hàng bị hủy

```sql
CASE
    WHEN order_status = 'CANCELLED' THEN 1
    ELSE 0
END AS is_cancelled
```

Dữ liệu mẫu chỉ có đơn `103` nhận `is_cancelled = 1`.

### 5.2. Cờ đơn hàng đã đóng

Giả sử nghiệp vụ định nghĩa “đã đóng” là đơn `COMPLETED` hoặc `CANCELLED`:

```sql
CASE
    WHEN order_status IN ('COMPLETED', 'CANCELLED') THEN 1
    ELSE 0
END AS is_closed
```

Trong dữ liệu mẫu, đơn `103` và `104` có `is_closed = 1`.

### 5.3. Cờ đơn hàng giá trị cao

Giả sử đơn từ **1.000.000 trở lên** là “giá trị cao”:

```sql
CASE
    WHEN total_amount >= 1000000 THEN 1
    ELSE 0
END AS is_high_value
```

Chỉ đơn `101` thỏa điều kiện ở bảng mẫu.

**Quy tắc ranh giới:** `>= 1000000` bao gồm đúng 1.000.000, còn `> 1000000` không bao gồm. Người viết truy vấn phải thống nhất ranh giới với mô tả nghiệp vụ.

### 5.4. Cờ đã giao hàng

Nếu nghiệp vụ coi `shipped_at` có giá trị là bằng chứng đã giao cho đơn vị vận chuyển:

```sql
CASE
    WHEN shipped_at IS NOT NULL THEN 1
    ELSE 0
END AS is_shipped
```

Đơn `104` nhận `is_shipped = 1`.

Cần phân biệt **đã giao cho vận chuyển** với **đã đến tay khách hàng**. Cột `shipped_at` chỉ chứng minh điều mà hệ thống định nghĩa nó ghi nhận. Nếu muốn cờ `is_delivered`, cần dữ liệu về trạng thái giao hàng hoặc thời điểm giao thành công, không thể đổi tên cờ và coi ý nghĩa như nhau.

## 6. Tạo cờ quá hạn từ nhiều điều kiện

Xây một quy tắc tương đối đầy đủ:

> Một đơn hàng được coi là **quá hạn thanh toán** tại ngày 14/11/2026 nếu ngày đến hạn trước ngày đó, số tiền đã trả nhỏ hơn số tiền cần trả, và đơn không ở trạng thái `CANCELLED` hoặc `COMPLETED`.

Biểu thức:

```sql
CASE
    WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
         AND due_date < DATE '2026-11-14'
         AND paid_amount < total_amount
    THEN 1
    ELSE 0
END AS is_overdue
```

Truy vấn đầy đủ:

```sql
SELECT
    order_id,
    order_status,
    due_date,
    total_amount,
    paid_amount,
    CASE
        WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
             AND due_date < DATE '2026-11-14'
             AND paid_amount < total_amount
        THEN 1
        ELSE 0
    END AS is_overdue
FROM shop_orders
ORDER BY order_id;
```

Trong dữ liệu mẫu, chỉ đơn **`106`** có `is_overdue = 1`.

| order_id | is_overdue | Lý do |
| ---: | ---: | --- |
| 101 | 0 | Đã thanh toán đủ |
| 102 | 0 | Chưa đến hạn |
| 103 | 0 | Đã hủy |
| 104 | 0 | Hoàn thành và thanh toán đủ |
| 105 | 0 | Chưa có ngày đến hạn; nhánh `ELSE` áp dụng |
| 106 | 1 | Đến hạn trước 14/11, chưa trả, vẫn hoạt động |
| 107 | 0 | Không còn khoản thiếu; hạn đúng 14/11 |
| 108 | 0 | Đã trả đủ; hạn đúng 14/11 |
| 109 | 0 | Chưa có ngày đến hạn; nhánh `ELSE` áp dụng |

### 6.1. Vì sao dùng ngày cố định thay cho CURRENT_DATE?

Khi học hoặc viết báo cáo hồi cứu, điều kiện:

```sql
due_date < CURRENT_DATE
```

sẽ cho kết quả thay đổi theo ngày chạy và theo ngữ nghĩa ngày hiện hành của DBMS/phiên kết nối.

Để kết quả thực hành có thể dự đoán được, bài dùng:

```sql
due_date < DATE '2026-11-14'
```

Trong ứng dụng thật, nên truyền **ngày đánh giá** như một tham số nghiệp vụ, ví dụ `:as_of_date` trong các thư viện hỗ trợ named parameter, thay vì cố định một ngày trong mã SQL:

```sql
-- Ký hiệu :as_of_date là tham số của tầng ứng dụng,
-- không phải cú pháp bind chung của mọi SQL driver.
CASE
    WHEN due_date < :as_of_date
         AND paid_amount < total_amount
         AND order_status NOT IN ('CANCELLED', 'COMPLETED')
    THEN 1
    ELSE 0
END AS is_overdue
```

### 6.2. “Quá hạn” theo ngày và theo thời điểm khác nhau

Nếu nghiệp vụ quy định quá hạn **sau thời điểm cụ thể**, một cột `TIMESTAMP`/`TIMESTAMPTZ` cùng múi giờ có thể phù hợp hơn cột `DATE`.

Ví dụ:

- “Đến hết ngày 14/11 theo giờ Việt Nam mới quá hạn” khác với
- “Quá 17:00 ngày 14/11 theo giờ UTC là quá hạn”.

Khi dùng `DATE`, điều kiện `due_date < as_of_date` nghĩa là ngày đến hạn **trước** ngày đánh giá; nó không chứa khái niệm một giờ cụ thể trong ngày. Chọn kiểu và phép so sánh phù hợp với quy tắc nghiệp vụ về hạn, múi giờ và ranh giới.

## 7. NULL và logic ba giá trị ảnh hưởng đến cờ thế nào?

Trong SQL, phép so sánh với `NULL` thường không trả `TRUE` hoặc `FALSE` mà trả **`UNKNOWN`**.

```sql
SELECT
    NULL = NULL        AS null_equals_null,
    NULL < DATE '2026-11-14' AS null_date_compare;
-- Hai biểu thức cho NULL/UNKNOWN theo ngữ nghĩa SQL.
```

Với `CASE WHEN điều_kiện THEN 1 ELSE 0 END`, nhánh `THEN` chỉ được chọn khi điều kiện là **`TRUE`**. Nếu điều kiện là `FALSE` **hoặc `UNKNOWN`**, biểu thức chuyển đến nhánh tiếp theo hoặc `ELSE`.

Do đó:

```sql
CASE
    WHEN due_date < DATE '2026-11-14' THEN 1
    ELSE 0
END AS is_past_due
```

sẽ trả `0` khi `due_date IS NULL`. Đây là một **quyết định ngầm của công thức**, và có thể hoặc không phù hợp với nghiệp vụ.

### 7.1. Phân biệt sai và chưa biết

Nếu cần giữ sự khác biệt:

```sql
CASE
    WHEN due_date IS NULL THEN NULL
    WHEN due_date < DATE '2026-11-14' THEN 1
    ELSE 0
END AS is_past_due
```

Giá trị có thể là:

- `1`: chắc chắn đã qua ngày đến hạn.
- `0`: chắc chắn chưa qua ngày đến hạn.
- `NULL`: chưa biết ngày đến hạn nên chưa thể đánh giá.

Không có `ELSE` cũng khiến `CASE` trả `NULL` khi không nhánh `WHEN` nào đúng. Điều đó có thể hữu ích nếu cố ý tạo cờ ba trạng thái, nhưng dễ gây lỗi nếu người đọc tưởng đầu ra chỉ có `0` và `1`.

### 7.2. Dùng IS NULL và IS NOT NULL đúng mục đích

**Không viết:**

```sql
CASE
    WHEN due_date = NULL THEN 1
    ELSE 0
END AS has_missing_due_date
```

Vì `due_date = NULL` không cho `TRUE`, kể cả khi `due_date` đang `NULL`.

**Viết:**

```sql
CASE
    WHEN due_date IS NULL THEN 1
    ELSE 0
END AS is_due_date_missing
```

Trong dữ liệu mẫu, đơn `105` và `109` có `is_due_date_missing = 1`.

### 7.3. Dùng COALESCE cần cẩn trọng

`COALESCE` lấy giá trị đầu tiên khác `NULL`:

```sql
SELECT
    order_id,
    COALESCE(paid_amount, 0) AS paid_amount_for_display
FROM shop_orders;
```

Nhưng **thay thiếu dữ liệu bằng 0** là lựa chọn nghiệp vụ, không đơn thuần là thao tác hiển thị. Nếu `paid_amount` có thể `NULL` và ý nghĩa là “chưa biết đã trả bao nhiêu”, việc coi `NULL` là 0 có thể tạo sai cờ chưa thanh toán.

Ở bảng mẫu, `paid_amount` được khai báo `NOT NULL` nên không cần `COALESCE` cho cột này. Với dữ liệu thật, hãy phân biệt “chưa thanh toán” (`0`) với “không có thông tin thanh toán” (`NULL`).

## 8. Tạo nhiều cờ cùng lúc trong một SELECT

Một báo cáo có thể cần nhiều câu trả lời độc lập cho mỗi đơn hàng:

```sql
SELECT
    order_id,
    CASE
        WHEN paid_amount >= total_amount THEN 1
        ELSE 0
    END AS is_fully_paid,
    CASE
        WHEN order_status = 'CANCELLED' THEN 1
        ELSE 0
    END AS is_cancelled,
    CASE
        WHEN shipped_at IS NOT NULL THEN 1
        ELSE 0
    END AS is_shipped,
    CASE
        WHEN due_date IS NULL THEN 1
        ELSE 0
    END AS is_due_date_missing,
    CASE
        WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
             AND due_date < DATE '2026-11-14'
             AND paid_amount < total_amount
        THEN 1
        ELSE 0
    END AS is_overdue
FROM shop_orders
ORDER BY order_id;
```

Kết quả của dữ liệu mẫu:

| order_id | is_fully_paid | is_cancelled | is_shipped | is_due_date_missing | is_overdue |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 101 | 1 | 0 | 0 | 0 | 0 |
| 102 | 0 | 0 | 0 | 0 | 0 |
| 103 | 0 | 1 | 0 | 0 | 0 |
| 104 | 1 | 0 | 1 | 0 | 0 |
| 105 | 0 | 0 | 0 | 1 | 0 |
| 106 | 0 | 0 | 0 | 0 | 1 |
| 107 | 1 | 0 | 0 | 0 | 0 |
| 108 | 1 | 0 | 0 | 0 | 0 |
| 109 | 0 | 0 | 0 | 1 | 0 |

Các cờ thể hiện **những thuộc tính khác nhau**, không nhất thiết loại trừ lẫn nhau. Ví dụ một đơn có thể vừa **đã thanh toán đủ** vừa **đã hủy** nếu hệ thống cho phép hủy sau thanh toán và còn chờ hoàn tiền. Không nên suy ra một cờ `is_cancelled = 1` thì mọi cờ khác bắt buộc bằng 0, trừ khi có quy tắc và ràng buộc dữ liệu cụ thể.

### 8.1. Khi nào nên dùng nhiều cờ?

Dùng nhiều cờ nếu người dùng cần trả lời **nhiều câu hỏi độc lập**:

- Có thanh toán đủ không?
- Có quá hạn không?
- Có thiếu dữ liệu không?
- Đã được chuyển đến bộ phận vận chuyển chưa?

Dùng một nhãn trạng thái khi màn hình muốn hiển thị **một kết luận ưu tiên duy nhất**. Hai cách này không thay thế hoàn toàn cho nhau.

## 9. Cờ độc lập và nhãn trạng thái có thứ tự ưu tiên

Xét quy tắc tạo nhãn:

1. Đơn `CANCELLED` → `'CANCELLED'`.
2. Đơn `COMPLETED` → `'COMPLETED'`.
3. Đơn đã thanh toán đủ → `'PAID'`.
4. Đơn thiếu ngày đến hạn → `'MISSING_DUE_DATE'`.
5. Đơn chưa trả đủ và đã qua hạn → `'OVERDUE'`.
6. Trường hợp còn lại → `'OPEN'`.

Dùng nhiều nhánh `WHEN`:

```sql
SELECT
    order_id,
    order_status,
    CASE
        WHEN order_status = 'CANCELLED' THEN 'CANCELLED'
        WHEN order_status = 'COMPLETED' THEN 'COMPLETED'
        WHEN paid_amount >= total_amount THEN 'PAID'
        WHEN due_date IS NULL THEN 'MISSING_DUE_DATE'
        WHEN due_date < DATE '2026-11-14'
             AND paid_amount < total_amount
        THEN 'OVERDUE'
        ELSE 'OPEN'
    END AS business_state
FROM shop_orders
ORDER BY order_id;
```

Kết quả:

| order_id | business_state |
| ---: | --- |
| 101 | PAID |
| 102 | OPEN |
| 103 | CANCELLED |
| 104 | COMPLETED |
| 105 | MISSING_DUE_DATE |
| 106 | OVERDUE |
| 107 | PAID |
| 108 | PAID |
| 109 | MISSING_DUE_DATE |

### 9.1. Thứ tự WHEN quyết định nhánh được chọn

Một hàng có thể thỏa **nhiều điều kiện**. Ví dụ đơn `104` vừa `COMPLETED` vừa `paid_amount >= total_amount`. Vì nhánh `COMPLETED` đứng trước, nó nhận nhãn `'COMPLETED'`.

Nếu chuyển nhánh `paid_amount >= total_amount` lên trước, đơn `104` sẽ nhận `'PAID'`. Hai kết quả đều đúng với hai quy tắc ưu tiên khác nhau, nhưng chỉ một kết quả có thể đúng theo nghiệp vụ đã được xác nhận.

Một cờ nhị phân:

```sql
CASE WHEN condition THEN 1 ELSE 0 END
```

thường chỉ cần một điều kiện. Ngược lại, một **nhãn nhiều trạng thái** nên đi kèm tài liệu về **thứ tự ưu tiên**, để tránh việc chỉnh thứ tự nhánh vô tình làm đổi ý nghĩa.

### 9.2. Không xem CASE là lời hứa về mọi hiệu ứng khi tính biểu thức

`CASE` có ngữ nghĩa chọn nhánh kết quả, nhưng cách DBMS tối ưu, ép kiểu và tính một số biểu thức có thể khác nhau. Đặc biệt, đừng dựa vào `CASE` để điều khiển các hàm có tác dụng phụ hoặc đảm bảo mọi biểu thức nguy hiểm đều không được đánh giá ở mọi giai đoạn lập kế hoạch. Đối với phép chia, ép kiểu hoặc biểu thức có thể lỗi, hãy thiết kế dữ liệu đầu vào và điều kiện một cách an toàn.

## 10. Lọc theo cờ: SELECT, WHERE và CTE

Một cột cờ trong `SELECT` giúp **hiển thị** kết quả đánh giá, nhưng không tự lọc hàng.

### 10.1. Chỉ tạo cờ, giữ toàn bộ đơn hàng

```sql
SELECT
    order_id,
    CASE
        WHEN total_amount >= 1000000 THEN 1
        ELSE 0
    END AS is_high_value
FROM shop_orders
ORDER BY order_id;
```

Truy vấn trả cả chín hàng, chỉ thêm cột `is_high_value`.

### 10.2. Chỉ lấy hàng thỏa điều kiện

Nếu chỉ muốn lấy các đơn giá trị cao:

```sql
SELECT order_id, total_amount
FROM shop_orders
WHERE total_amount >= 1000000
ORDER BY order_id;
```

Truy vấn này chỉ trả `order_id = 101` trong dữ liệu mẫu.

**Khác biệt:**

- `CASE` trong `SELECT`: **gắn nhãn** các hàng được chọn.
- Điều kiện trong `WHERE`: **loại bỏ** các hàng không thỏa.

Nếu chỉ cần lọc hàng, dùng điều kiện trực tiếp trong `WHERE` thường ngắn và rõ hơn việc tính cờ rồi lọc cờ.

### 10.3. Muốn lọc bằng tên cờ, dùng CTE hoặc bảng dẫn xuất

Trong SQL phổ biến, alias `is_overdue` được định nghĩa ở `SELECT` **không thể được tham chiếu trực tiếp trong `WHERE` cùng cấp**:

```sql
-- Không phải cú pháp portable:
SELECT
    order_id,
    CASE
        WHEN due_date < DATE '2026-11-14'
             AND paid_amount < total_amount
        THEN 1 ELSE 0
    END AS is_overdue
FROM shop_orders
WHERE is_overdue = 1;
```

Cách rõ ràng hơn là dùng **CTE**:

```sql
WITH order_flags AS (
    SELECT
        order_id,
        order_status,
        due_date,
        paid_amount,
        total_amount,
        CASE
            WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
                 AND due_date < DATE '2026-11-14'
                 AND paid_amount < total_amount
            THEN 1
            ELSE 0
        END AS is_overdue
    FROM shop_orders
)
SELECT order_id, due_date, is_overdue
FROM order_flags
WHERE is_overdue = 1
ORDER BY order_id;
```

Kết quả: đơn `106`.

Lợi ích của CTE là phần định nghĩa cờ và phần sử dụng cờ có thể được đọc độc lập. CTE không mặc nhiên được lưu vật lý và không tự bảo đảm thứ tự đầu ra; `ORDER BY` ngoài cùng vẫn cần thiết khi ứng dụng quan tâm thứ tự hàng.

### 10.4. Bảng dẫn xuất cũng có thể làm việc tương tự

```sql
SELECT f.order_id, f.is_cancelled
FROM (
    SELECT
        order_id,
        CASE
            WHEN order_status = 'CANCELLED' THEN 1
            ELSE 0
        END AS is_cancelled
    FROM shop_orders
) AS f
WHERE f.is_cancelled = 1;
```

Truy vấn trả đơn `103`. Đây là ví dụ một **derived table** tạo ra cột suy ra mà truy vấn ngoài có thể sử dụng.

## 11. Đếm và tính tỷ lệ từ cột cờ

Cờ số `0`/`1` có một ưu điểm: có thể **tổng hợp** bằng `SUM` hoặc đếm có điều kiện.

### 11.1. Đếm đơn thanh toán đủ và đơn quá hạn

```sql
SELECT
    COUNT(*) AS total_orders,
    SUM(
        CASE
            WHEN paid_amount >= total_amount THEN 1
            ELSE 0
        END
    ) AS fully_paid_orders,
    SUM(
        CASE
            WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
                 AND due_date < DATE '2026-11-14'
                 AND paid_amount < total_amount
            THEN 1
            ELSE 0
        END
    ) AS overdue_orders
FROM shop_orders;
```

Kết quả từ dữ liệu mẫu:

| total_orders | fully_paid_orders | overdue_orders |
| ---: | ---: | ---: |
| 9 | 4 | 1 |

Vì `CASE` luôn trả `1` hoặc `0` cho từng hàng nên `SUM` cộng tổng số hàng có cờ bằng `1`.

### 11.2. Vì sao COUNT(flag) không đếm số cờ bằng 1?

`COUNT(expression)` đếm số giá trị **khác `NULL`**, không phải chỉ đếm giá trị khác `0`.

```sql
SELECT COUNT(
    CASE
        WHEN order_status = 'CANCELLED' THEN 1
        ELSE 0
    END
) AS misleading_count
FROM shop_orders;
-- 9, vì mọi hàng đều trả 1 hoặc 0, không có NULL.
```

Nếu muốn dùng `COUNT`, có thể để những hàng không thỏa điều kiện trả `NULL`:

```sql
SELECT COUNT(
    CASE
        WHEN order_status = 'CANCELLED' THEN 1
        ELSE NULL
    END
) AS cancelled_count
FROM shop_orders;
-- 1
```

Có thể bỏ `ELSE NULL` vì đó là mặc định của `CASE` khi không nhánh nào đúng. Tuy nhiên, khi tạo **cờ hiển thị** với yêu cầu chỉ `0` và `1`, vẫn nên giữ `ELSE 0` tường minh.

### 11.3. PostgreSQL: COUNT FILTER

PostgreSQL hỗ trợ cú pháp tổng hợp có điều kiện:

```sql
SELECT
    COUNT(*) AS total_orders,
    COUNT(*) FILTER (
        WHERE order_status = 'CANCELLED'
    ) AS cancelled_orders,
    COUNT(*) FILTER (
        WHERE paid_amount >= total_amount
    ) AS fully_paid_orders
FROM shop_orders;
```

Dạng `FILTER` rất dễ đọc, nhưng không phải mọi DBMS phổ biến đều hỗ trợ cùng cú pháp. `SUM(CASE WHEN ... THEN 1 ELSE 0 END)` thường là lựa chọn quen thuộc khi cần truy vấn có tính tương thích rộng.

### 11.4. Tính tỷ lệ

Trên PostgreSQL:

```sql
SELECT
    COUNT(*) AS total_orders,
    SUM(
        CASE WHEN paid_amount >= total_amount THEN 1 ELSE 0 END
    ) AS fully_paid_orders,
    100.0 * SUM(
        CASE WHEN paid_amount >= total_amount THEN 1 ELSE 0 END
    ) / NULLIF(COUNT(*), 0) AS fully_paid_percent
FROM shop_orders;
```

Với chín hàng và bốn đơn thanh toán đủ, tỷ lệ khoảng **44,44%**.

Những lưu ý:

- `100.0` giúp biểu thức dùng số có phần thập phân thay vì vô tình bị chia nguyên trên một số hệ quản trị.
- `NULLIF(COUNT(*), 0)` tránh chia cho 0 khi tập dữ liệu được lọc rỗng; kết quả tỷ lệ có thể là `NULL` nếu mẫu số bằng 0.
- Cách làm tròn/kiểu số và định dạng phần trăm tùy DBMS hoặc tầng hiển thị.

### 11.5. Thống kê theo khách hàng

```sql
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(
        CASE WHEN paid_amount >= total_amount THEN 1 ELSE 0 END
    ) AS fully_paid_count
FROM shop_orders
GROUP BY customer_id
ORDER BY customer_id;
```

Truy vấn tạo **một hàng cho mỗi khách hàng**, thay vì một hàng cho mỗi đơn. `CASE` được đánh giá trên từng đơn trong nhóm, rồi `SUM` cộng các cờ lại.

## 12. Cờ dựa trên dữ liệu ở bảng khác: EXISTS và NOT EXISTS

Đôi khi điều kiện nghiệp vụ phụ thuộc vào **sự tồn tại của bản ghi liên quan**, chứ không chỉ các cột của một bảng.

Giả sử có bảng kiểm tra rủi ro:

```sql
CREATE TABLE risk_review (
    review_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES shop_orders(order_id),
    review_status VARCHAR(20) NOT NULL
);

INSERT INTO risk_review (review_id, order_id, review_status)
VALUES
    (1, 102, 'OPEN'),
    (2, 102, 'OPEN'),
    (3, 106, 'RESOLVED'),
    (4, 108, 'OPEN');
```

Muốn tạo cờ **có ít nhất một đánh giá rủi ro đang mở**, có thể dùng `EXISTS`:

```sql
SELECT
    o.order_id,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM risk_review AS r
            WHERE r.order_id = o.order_id
              AND r.review_status = 'OPEN'
        ) THEN 1
        ELSE 0
    END AS has_open_risk_review
FROM shop_orders AS o
ORDER BY o.order_id;
```

Kết quả: `102` và `108` nhận `1`; các đơn khác nhận `0`. Dù đơn `102` có **hai** đánh giá đang mở, nó chỉ là **một hàng** trong kết quả ngoài với cờ bằng `1`.

### 12.1. Vì sao EXISTS phù hợp để tạo cờ tồn tại?

Nếu dùng `LEFT JOIN` trực tiếp:

```sql
SELECT o.order_id, r.review_id
FROM shop_orders AS o
LEFT JOIN risk_review AS r
    ON r.order_id = o.order_id
   AND r.review_status = 'OPEN';
```

đơn `102` xuất hiện **hai hàng** vì có hai bản ghi `risk_review` khớp. Nếu tạo cờ và đồng thời thống kê số đơn trên kết quả JOIN, việc nhân hàng có thể làm sai số đếm.

`EXISTS` hỏi một câu đơn giản: **có ít nhất một hàng liên quan thỏa điều kiện hay không?** Nó không cần nhân bản hàng ở truy vấn ngoài để trả cờ.

### 12.2. Cờ không tồn tại bản ghi liên quan

`NOT EXISTS` là lựa chọn tự nhiên cho cờ **chưa có bản ghi liên quan**:

```sql
SELECT
    o.order_id,
    CASE
        WHEN NOT EXISTS (
            SELECT 1
            FROM risk_review AS r
            WHERE r.order_id = o.order_id
        ) THEN 1
        ELSE 0
    END AS has_no_risk_review
FROM shop_orders AS o
ORDER BY o.order_id;
```

`NOT EXISTS` kiểm tra **không có hàng nào thỏa điều kiện**, nên có ý nghĩa rõ ràng ngay cả khi bảng con có các trường khác bị `NULL`. Tuy nhiên, phải xác định ngữ nghĩa của các cột dùng trong điều kiện tương quan, đặc biệt nếu khóa tham chiếu được phép `NULL`.

## 13. Cờ Boolean trực tiếp và CASE: khi nào dùng cách nào?

Trên PostgreSQL, biểu thức so sánh có kiểu Boolean, vì vậy có thể viết:

```sql
SELECT
    order_id,
    paid_amount >= total_amount AS is_fully_paid,
    order_status = 'CANCELLED' AS is_cancelled,
    due_date IS NULL AS is_due_date_missing
FROM shop_orders;
```

Đây là cách ngắn để tạo cờ Boolean khi **điều kiện đã đúng hoàn toàn về nghiệp vụ**.

Dùng `CASE` khi cần:

- Cờ kiểu số `0`/`1` để tương thích báo cáo.
- Đổi kiểu giá trị trả về thành `'YES'`/`'NO'`.
- Quy định rõ cách xử lý `NULL`/`UNKNOWN`.
- Nhiều nhánh điều kiện ưu tiên.
- Mô tả các trường hợp ngoại lệ hoặc chính sách nghiệp vụ.

| Nhu cầu | Ví dụ nên cân nhắc |
| --- | --- |
| Boolean đơn giản trong PostgreSQL | `paid_amount >= total_amount AS is_fully_paid` |
| Số 0/1 rõ ràng | `CASE WHEN paid_amount >= total_amount THEN 1 ELSE 0 END` |
| Không biết thì trả NULL | `CASE WHEN due_date IS NULL THEN NULL WHEN ... THEN 1 ELSE 0 END` |
| Có chính sách ngoại lệ | `CASE WHEN order_status = 'CANCELLED' THEN 0 WHEN ... THEN 1 ELSE 0 END` |
| Nhãn nhiều trạng thái | `CASE WHEN ... THEN 'CANCELLED' WHEN ... THEN 'PAID' ELSE 'OPEN' END` |

**Không nên rút ngắn câu SQL bằng cách đánh mất ý nghĩa.** Một biểu thức Boolean ngắn nhưng bỏ sót quy tắc loại trừ đơn đã hủy có thể tạo cờ sai.

## 14. Dùng cờ trong ORDER BY, GROUP BY và báo cáo

### 14.1. Ưu tiên hiển thị đơn quá hạn lên trước

Có thể tính cờ trong CTE rồi sắp xếp:

```sql
WITH flagged AS (
    SELECT
        order_id,
        total_amount,
        due_date,
        CASE
            WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
                 AND due_date < DATE '2026-11-14'
                 AND paid_amount < total_amount
            THEN 1 ELSE 0
        END AS is_overdue
    FROM shop_orders
)
SELECT order_id, total_amount, due_date, is_overdue
FROM flagged
ORDER BY is_overdue DESC, due_date ASC NULLS LAST, order_id ASC;
```

Ví dụ này dùng `NULLS LAST` của PostgreSQL. Cờ quá hạn bằng `1` được ưu tiên; sau đó sắp theo ngày đến hạn và mã đơn.

Nếu chạy trên DBMS không hỗ trợ `NULLS LAST` với cùng cú pháp, có thể thay bằng biểu thức `CASE` trong `ORDER BY` để xác định vị trí `NULL`.

### 14.2. Nhóm theo cờ

```sql
WITH flagged AS (
    SELECT
        CASE
            WHEN order_status = 'CANCELLED' THEN 1
            ELSE 0
        END AS is_cancelled
    FROM shop_orders
)
SELECT is_cancelled, COUNT(*) AS number_of_orders
FROM flagged
GROUP BY is_cancelled
ORDER BY is_cancelled;
```

Kết quả:

| is_cancelled | number_of_orders |
| ---: | ---: |
| 0 | 8 |
| 1 | 1 |

Đây là cách tạo báo cáo “bao nhiêu đơn thuộc mỗi nhóm”. Khi cần nhóm theo nhiều cờ, lưu ý một đơn có thể góp mặt ở **nhiều chỉ số tổng hợp** khác nhau; không được cộng các chỉ số độc lập rồi mặc định tổng bằng số đơn.

### 14.3. Cờ và việc giới hạn hàng

Nếu muốn lấy tối đa ba đơn chưa thanh toán đủ, ưu tiên đơn có tiền lớn:

```sql
SELECT order_id, total_amount, paid_amount
FROM shop_orders
WHERE paid_amount < total_amount
ORDER BY total_amount DESC, order_id ASC
LIMIT 3;
```

Trên PostgreSQL/MySQL/SQLite, `LIMIT 3` chọn tối đa ba hàng sau khi xác định điều kiện và thứ tự. Các DBMS khác có cú pháp tương đương như `TOP` (SQL Server) hoặc `FETCH FIRST` (Oracle và PostgreSQL).

Không nên đặt `LIMIT` trước khi đánh giá đúng tập đơn cần chọn nếu nghiệp vụ yêu cầu “top 3 trong số đơn chưa trả đủ”. Khi thứ tự có giá trị trùng, thêm khóa phụ duy nhất để việc chọn top N ổn định.

## 15. Cờ tính động, cờ trong VIEW và cờ lưu vật lý

Có ba cách triển khai thường gặp:

| Cách triển khai | Dữ liệu cờ nằm ở đâu? | Đặc điểm |
| --- | --- | --- |
| **Biểu thức SELECT/CTE** | Chỉ ở kết quả truy vấn | Không tạo cột lưu mới, dùng dữ liệu hiện hành; có thể lặp logic giữa nhiều truy vấn nếu không quản lý tốt |
| **VIEW** | Định nghĩa truy vấn được lưu, kết quả được tính khi truy vấn view thông thường | Tái sử dụng quy tắc trong nhiều câu SQL; cần quản lý thay đổi định nghĩa view |
| **Cột lưu vật lý hoặc generated column** | Cột tồn tại trong schema, có thể lưu hoặc tính tùy cơ chế DBMS | Có thể thuận tiện cho tra cứu/chỉ mục, nhưng cần hiểu quy tắc cập nhật, tính nhất quán và giới hạn biểu thức |

### 15.1. VIEW tái sử dụng định nghĩa cờ

Trên PostgreSQL:

```sql
CREATE VIEW shop_order_flags AS
SELECT
    order_id,
    customer_id,
    order_status,
    total_amount,
    paid_amount,
    due_date,
    CASE
        WHEN paid_amount >= total_amount THEN 1
        ELSE 0
    END AS is_fully_paid,
    CASE
        WHEN order_status = 'CANCELLED' THEN 1
        ELSE 0
    END AS is_cancelled
FROM shop_orders;
```

Sau đó có thể đọc cờ:

```sql
SELECT order_id, is_fully_paid, is_cancelled
FROM shop_order_flags
WHERE is_fully_paid = 1
ORDER BY order_id;
```

Một **view thông thường** lưu định nghĩa truy vấn, không tự sao chép dữ liệu như một bảng kết quả vật lý. Nếu `paid_amount` trong `shop_orders` thay đổi và DBMS xử lý truy vấn view trên dữ liệu hiện hành, giá trị `is_fully_paid` được tính lại theo định nghĩa.

### 15.2. Generated column khi biểu thức phù hợp

PostgreSQL hỗ trợ generated column với biểu thức đáp ứng những ràng buộc nhất định. Một ví dụ **trên bảng thử nghiệm riêng**:

```sql
-- PostgreSQL 12+:
CREATE TABLE payment_summary_demo (
    order_id INTEGER PRIMARY KEY,
    total_amount NUMERIC(12, 2) NOT NULL,
    paid_amount NUMERIC(12, 2) NOT NULL,
    is_fully_paid BOOLEAN
        GENERATED ALWAYS AS (paid_amount >= total_amount) STORED
);
```

Giá trị `is_fully_paid` được suy ra từ các cột cùng hàng. Ở chế độ `STORED`, dữ liệu kết quả được lưu theo cơ chế của DBMS và cập nhật khi các cột phụ thuộc thay đổi, thay vì ứng dụng tự viết lại cờ.

Nhưng không phải mọi điều kiện có thể dùng trong generated column. Đặc biệt, một cờ “quá hạn so với **ngày hiện tại**” phụ thuộc thời gian và có thể đổi **ngay cả khi hàng không bị cập nhật**. Không thể mặc định viết `CURRENT_DATE` vào một generated column stored mà mong nó tự chuyển từ `0` sang `1` khi sang ngày mới. PostgreSQL có giới hạn về tính bất biến (*immutability*) của biểu thức generated column.

### 15.3. Khi nào không nên lưu cờ thủ công?

Nếu lưu cả:

```text
total_amount = 300000
paid_amount  = 300000
is_fully_paid = 0
```

thì dữ liệu **mâu thuẫn** với quy tắc `paid_amount >= total_amount`. Mỗi lần thay đổi tiền phải đồng bộ thêm cờ, và mọi đường ghi dữ liệu đều cần thực hiện đúng.

Với cờ thuần suy ra từ dữ liệu nguồn, tính trong truy vấn, view hoặc generated column thường dễ bảo đảm nhất quán hơn. Nếu nghiệp vụ thực sự cần **lưu quyết định ở một thời điểm lịch sử** (ví dụ kết quả duyệt rủi ro đã được phê duyệt), đó có thể là một **sự kiện/trạng thái được ghi nhận độc lập**, không còn là cờ tính lại đơn giản.

### 15.4. Cờ phụ thuộc thời gian và snapshot

So sánh:

- `is_overdue_now`: phụ thuộc thời điểm đánh giá; nên tính theo ngày/thời gian hiện hành hoặc tham số.
- `was_overdue_at_close`: trạng thái tại thời điểm đóng kỳ báo cáo; có thể cần lưu kết quả, ngày đánh giá và phiên bản quy tắc để tái hiện lịch sử.

Dùng một cột vật lý tên `is_overdue` mà không ghi rõ thời điểm đánh giá dễ khiến ứng dụng hiểu nhầm một giá trị đã cũ là trạng thái hiện tại.

## 16. Hiệu năng và khả năng dùng chỉ mục

Việc tính cờ trong `SELECT` thường đơn giản, nhưng với bảng lớn và điều kiện phức tạp, cần cân nhắc nơi tính và cách lọc.

### 16.1. Lọc trực tiếp trên cột nguồn khi chỉ cần hàng khớp

Nếu chỉ cần đơn giá trị cao:

```sql
SELECT order_id, total_amount
FROM shop_orders
WHERE total_amount >= 1000000;
```

Điều kiện trực tiếp này cho bộ tối ưu cơ hội dùng chỉ mục phù hợp trên `total_amount`.

So sánh với:

```sql
SELECT order_id
FROM shop_orders
WHERE CASE
    WHEN total_amount >= 1000000 THEN 1
    ELSE 0
END = 1;
```

Dạng thứ hai diễn đạt cùng mục đích trong bảng mẫu nhưng bao bọc cột bằng biểu thức; khả năng tối ưu và dùng chỉ mục có thể khác tùy DBMS. Nếu không cần xuất cờ, điều kiện `WHERE total_amount >= 1000000` thường dễ hiểu hơn.

### 16.2. Chỉ mục phục vụ cờ quá hạn

Trên PostgreSQL, có thể cân nhắc một chỉ mục trên ngày đến hạn cho những đơn đang còn khoản phải trả:

```sql
-- PostgreSQL-specific, ví dụ trên dữ liệu thử nghiệm:
CREATE INDEX idx_shop_orders_unpaid_due
ON shop_orders (due_date)
WHERE order_status NOT IN ('CANCELLED', 'COMPLETED')
  AND paid_amount < total_amount;
```

Truy vấn:

```sql
SELECT order_id, due_date
FROM shop_orders
WHERE order_status NOT IN ('CANCELLED', 'COMPLETED')
  AND paid_amount < total_amount
  AND due_date < DATE '2026-11-14';
```

có thể tận dụng chỉ mục một phần (*partial index*) nếu bộ tối ưu nhận thấy có lợi. Không nên khẳng định truy vấn **luôn** dùng chỉ mục: kế hoạch phụ thuộc kích thước bảng, thống kê, cấu hình và khả năng chứng minh điều kiện phù hợp.

Điểm quan trọng là chỉ mục ví dụ dựa trên **dữ liệu hàng và quy tắc ổn định**, còn mốc ngày đánh giá xuất hiện **trong điều kiện truy vấn**. Không đưa `CURRENT_DATE` vào vị từ của một chỉ mục một phần theo kiểu coi ngày hiện tại là hằng số bất biến vĩnh viễn.

### 16.3. Tránh lặp quy tắc ở nhiều nơi mà không kiểm soát

Nếu báo cáo A định nghĩa “quá hạn” là `due_date < CURRENT_DATE`, báo cáo B thêm điều kiện chưa thanh toán và báo cáo C bỏ qua đơn hủy, ba chỉ số sẽ không còn cùng ý nghĩa.

Có thể quản lý quy tắc qua:

- View hoặc CTE dùng chung trong một câu truy vấn.
- Hàm SQL/logic truy cập dữ liệu được quản lý theo phiên bản.
- Hợp đồng nghiệp vụ nêu rõ điều kiện và thời điểm đánh giá.
- Thử nghiệm ở cấp dữ liệu mẫu, đặc biệt các ranh giới và trường hợp `NULL`.

Không nhất thiết tạo abstraction cho mỗi phép `CASE` nhỏ; điều đáng ưu tiên là **cùng một tên cờ phải có cùng một định nghĩa nghiệp vụ**.

## 17. Khác biệt giữa các DBMS

`CASE` là biểu thức SQL phổ biến; phần lớn ví dụ số `THEN 1 ELSE 0` có thể áp dụng rộng rãi. Tuy nhiên, **kiểu Boolean và cú pháp bổ sung** có khác biệt.

| Hệ quản trị | Tạo cờ 0/1 | Lưu ý về Boolean và cú pháp khác |
| --- | --- | --- |
| PostgreSQL | `CASE WHEN ... THEN 1 ELSE 0 END` | Có kiểu `BOOLEAN` và literal `TRUE`/`FALSE`; có thể dùng biểu thức điều kiện trực tiếp làm cột Boolean; hỗ trợ `FILTER` trong aggregate. |
| MySQL | `CASE WHEN ... THEN 1 ELSE 0 END` | `BOOLEAN`/`BOOL` thường là alias của `TINYINT(1)`; có hàm `IF(condition, a, b)` riêng của MySQL, nhưng `CASE` dễ chuyển hệ hơn. |
| SQLite | `CASE WHEN ... THEN 1 ELSE 0 END` | Không dùng kiểu Boolean lưu trữ riêng giống PostgreSQL; thường biểu diễn bằng số `0`/`1`, có literal `TRUE`/`FALSE` trong phiên bản hiện đại. |
| SQL Server | `CASE WHEN ... THEN 1 ELSE 0 END` | Có kiểu `BIT` cho cờ; không thể dùng mọi biểu thức Boolean như cột trong `SELECT` theo cách PostgreSQL; có `IIF` nhưng `CASE` quen thuộc hơn. |
| Oracle Database truyền thống | `CASE WHEN ... THEN 1 ELSE 0 END` | Các bản trước Oracle 23c không có kiểu `BOOLEAN` dùng trực tiếp trong SQL như PostgreSQL; dùng số hoặc chuỗi. Oracle mới hỗ trợ SQL BOOLEAN theo phạm vi phiên bản. |

### 17.1. SQL Server: ép cờ số sang BIT

```sql
-- SQL Server:
SELECT
    order_id,
    CAST(
        CASE
            WHEN order_status = 'CANCELLED' THEN 1
            ELSE 0
        END AS BIT
    ) AS is_cancelled
FROM shop_orders;
```

`BIT` phù hợp khi ứng dụng muốn một cờ lưu/nhận theo kiểu SQL Server. Nếu chỉ cần đếm, `SUM(CASE ... THEN 1 ELSE 0 END)` vẫn là cách thống kê đơn giản.

### 17.2. MySQL: IF là tiện ích của phương ngữ

```sql
-- MySQL-specific:
SELECT
    order_id,
    IF(paid_amount >= total_amount, 1, 0) AS is_fully_paid
FROM shop_orders;
```

Có thể viết tương đương bằng `CASE`:

```sql
SELECT
    order_id,
    CASE
        WHEN paid_amount >= total_amount THEN 1
        ELSE 0
    END AS is_fully_paid
FROM shop_orders;
```

Khi viết SQL hỗ trợ nhiều DBMS, `CASE` là nền tảng dễ dùng lại hơn các hàm điều kiện riêng như `IF` hoặc `IIF`.

### 17.3. Kiểu trả về của CASE

Các biểu thức `THEN`/`ELSE` cần tạo ra kiểu kết quả mà DBMS có thể xác định và chuyển đổi tương thích. Ví dụ:

```sql
CASE WHEN condition THEN 1 ELSE 'NO' END
```

có thể gặp lỗi ép kiểu hoặc hành vi khác nhau giữa DBMS vì trộn số với chữ. Khi tạo cờ, nên nhất quán:

- Số: `THEN 1 ELSE 0`.
- Boolean: `THEN TRUE ELSE FALSE` ở DBMS hỗ trợ.
- Văn bản: `THEN 'YES' ELSE 'NO'`.

Sự nhất quán này giúp driver và ứng dụng đọc kiểu dữ liệu ổn định.

## 18. Ranh giới và ngoại lệ cần kiểm tra trong nghiệp vụ

Trước khi đưa một cột cờ vào báo cáo, xem các trường hợp sau:

| Trường hợp | Câu hỏi phải trả lời |
| --- | --- |
| Số tiền bằng đúng ngưỡng | Dùng `>=` hay `>`? |
| Đơn có tổng tiền bằng 0 | Có coi là thanh toán đủ không? |
| Thanh toán nhiều hơn số tiền phải trả | Cờ “đủ” vẫn bằng 1 hay cần cờ “trả thừa”? |
| Đơn hủy nhưng đã thu tiền | Cờ “đã trả đủ” có tiếp tục bằng 1 không? |
| Không có `due_date` | Quá hạn = 0, = `NULL`, hay có cờ thiếu dữ liệu riêng? |
| Hạn đúng ngày đánh giá | Có bị xem là quá hạn ngay không? |
| Hạn có giờ/múi giờ | So sánh theo instant nào và vùng thời gian nào? |
| Trạng thái nghiệp vụ không hợp lệ | Có cần `CHECK`/khóa ngoại tới bảng trạng thái không? |
| Không có bản ghi liên quan | Dùng `EXISTS`/`NOT EXISTS` hay một quy tắc khác? |
| Cờ được lưu lâu dài | Ai cập nhật khi dữ liệu nguồn đổi hoặc khi qua ngày mới? |

Những trường hợp này thường là **lý do chính** khiến hai câu `CASE` gần giống nhau lại cho số liệu khác nhau. Bản thân câu lệnh SQL không thể quyết định thay cho yêu cầu nghiệp vụ.

## 19. Bài tập thực hành

Các bài dưới đây sử dụng bảng `shop_orders` đã tạo ở mục 2. Hãy dự đoán giá trị cờ trước khi đọc lời giải.

### Bài 1. Tạo cờ đơn giá trị cao

**Yêu cầu:** Đánh dấu đơn có `total_amount >= 1000000`.

```sql
SELECT
    order_id,
    CASE
        WHEN total_amount >= 1000000 THEN 1
        ELSE 0
    END AS is_high_value
FROM shop_orders
ORDER BY order_id;
```

**Đáp án:** Chỉ `order_id = 101` nhận `1`.

### Bài 2. Tạo cờ đơn đã đóng

**Yêu cầu:** `is_closed = 1` nếu trạng thái là `COMPLETED` hoặc `CANCELLED`.

```sql
SELECT
    order_id,
    CASE
        WHEN order_status IN ('COMPLETED', 'CANCELLED') THEN 1
        ELSE 0
    END AS is_closed
FROM shop_orders
ORDER BY order_id;
```

**Đáp án:** `103` và `104` nhận `1`.

### Bài 3. Tạo cờ thiếu ngày đến hạn

```sql
SELECT
    order_id,
    CASE
        WHEN due_date IS NULL THEN 1
        ELSE 0
    END AS is_due_date_missing
FROM shop_orders
ORDER BY order_id;
```

**Đáp án:** `105` và `109` nhận `1`.

**Câu hỏi:** Vì sao `due_date = NULL` không thay thế được `IS NULL`? Vì phép `= NULL` tạo kết quả `UNKNOWN`, không phải `TRUE`.

### Bài 4. Tạo cờ quá hạn thanh toán

**Yêu cầu:** Quá hạn tại ngày 14/11/2026 khi chưa trả đủ, ngày đến hạn đã qua, và đơn không bị hủy hoặc hoàn thành.

```sql
SELECT
    order_id,
    CASE
        WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
             AND due_date < DATE '2026-11-14'
             AND paid_amount < total_amount
        THEN 1
        ELSE 0
    END AS is_overdue
FROM shop_orders
ORDER BY order_id;
```

**Đáp án:** Chỉ `106` nhận `1`.

### Bài 5. Sửa quy tắc “thanh toán đủ” với đơn tiền bằng 0

**Yêu cầu:** Chỉ xem đơn là thanh toán đủ khi `total_amount > 0` và đã trả ít nhất tổng tiền.

```sql
SELECT
    order_id,
    CASE
        WHEN total_amount > 0
             AND paid_amount >= total_amount
        THEN 1
        ELSE 0
    END AS is_fully_paid
FROM shop_orders
ORDER BY order_id;
```

**Đáp án:** `101`, `104`, `108` nhận `1`; đơn `107` nhận `0` theo quy tắc mới.

### Bài 6. Tạo cờ ba trạng thái

**Yêu cầu:** Với `due_date`, tạo `is_past_due` = `1` nếu đã qua hạn, `0` nếu chưa qua hạn, và `NULL` nếu chưa có ngày đến hạn.

```sql
SELECT
    order_id,
    CASE
        WHEN due_date IS NULL THEN NULL
        WHEN due_date < DATE '2026-11-14' THEN 1
        ELSE 0
    END AS is_past_due
FROM shop_orders
ORDER BY order_id;
```

**Đáp án:** `101`, `103`, `104`, `106` nhận `1`; `102`, `107`, `108` nhận `0`; `105` và `109` nhận `NULL`.

**Lưu ý:** Đây là cờ “ngày đến hạn đã qua”, **không phải** cờ “quá hạn thanh toán”. Vì vậy đơn `103` đã hủy hoặc `104` đã trả đủ vẫn có thể mang `is_past_due = 1`.

### Bài 7. Đếm số đơn bị hủy

```sql
SELECT
    SUM(
        CASE
            WHEN order_status = 'CANCELLED' THEN 1
            ELSE 0
        END
    ) AS cancelled_count
FROM shop_orders;
```

**Đáp án:** `1`.

**Câu hỏi tiếp:** `COUNT(CASE WHEN ... THEN 1 ELSE 0 END)` có trả 1 không? Không, trong dữ liệu mẫu nó trả **9** vì cả `0` và `1` đều khác `NULL`.

### Bài 8. Tìm đơn có đánh giá rủi ro đang mở

Sau khi tạo `risk_review` ở mục 12:

```sql
SELECT
    o.order_id,
    CASE
        WHEN EXISTS (
            SELECT 1
            FROM risk_review AS r
            WHERE r.order_id = o.order_id
              AND r.review_status = 'OPEN'
        ) THEN 1 ELSE 0
    END AS has_open_risk_review
FROM shop_orders AS o
ORDER BY o.order_id;
```

**Đáp án:** `102` và `108` có cờ `1`. Đơn `102` có hai đánh giá nhưng vẫn chỉ xuất hiện một lần.

### Bài 9. Tạo nhãn trạng thái ưu tiên

**Yêu cầu:** Ưu tiên `CANCELLED`, sau đó `COMPLETED`, sau đó `PAID`, sau đó `OVERDUE`, cuối cùng `OPEN`.

Một lời giải:

```sql
SELECT
    order_id,
    CASE
        WHEN order_status = 'CANCELLED' THEN 'CANCELLED'
        WHEN order_status = 'COMPLETED' THEN 'COMPLETED'
        WHEN paid_amount >= total_amount THEN 'PAID'
        WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
             AND due_date < DATE '2026-11-14'
             AND paid_amount < total_amount
        THEN 'OVERDUE'
        ELSE 'OPEN'
    END AS business_state
FROM shop_orders
ORDER BY order_id;
```

**Câu hỏi:** Lời giải này khác mẫu ở mục 9 thế nào? Nó **không** có trạng thái `MISSING_DUE_DATE`; đơn `105` và `109` được gắn `OPEN`. Đây là minh họa rằng thiếu một nhánh ngoại lệ sẽ đổi ý nghĩa đầu ra mà SQL vẫn hợp lệ.

### Bài 10. Tính tỷ lệ đơn quá hạn

```sql
SELECT
    COUNT(*) AS total_orders,
    SUM(
        CASE
            WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
                 AND due_date < DATE '2026-11-14'
                 AND paid_amount < total_amount
            THEN 1 ELSE 0
        END
    ) AS overdue_count,
    100.0 * SUM(
        CASE
            WHEN order_status NOT IN ('CANCELLED', 'COMPLETED')
                 AND due_date < DATE '2026-11-14'
                 AND paid_amount < total_amount
            THEN 1 ELSE 0
        END
    ) / NULLIF(COUNT(*), 0) AS overdue_percent
FROM shop_orders;
```

**Đáp án:** `total_orders = 9`, `overdue_count = 1` và tỷ lệ khoảng **11,11%**.

## 20. Quy trình thiết kế cột cờ có thể bảo trì

Khi nhận một yêu cầu “thêm cờ” trong báo cáo hoặc API, có thể tiến hành theo trình tự:

1. **Viết điều kiện bằng ngôn ngữ nghiệp vụ.** Ví dụ: “quá hạn khi đã qua hạn, chưa trả đủ và chưa đóng/hủy”.
2. **Xác định nguồn dữ liệu.** Cần những cột nào, có cần dữ liệu từ bảng liên quan không?
3. **Xác định ranh giới.** Dùng `>` hay `>=`? “Hôm nay” thuộc vùng thời gian nào?
4. **Xử lý dữ liệu thiếu.** `NULL` có nghĩa “sai”, “chưa biết” hay một trạng thái riêng?
5. **Chọn kiểu cờ.** Boolean, số `0`/`1`, chuỗi `YES/NO` hay nhãn nhiều trạng thái?
6. **Xác định mức ưu tiên nếu có nhiều nhánh.** Với `CASE` nhiều `WHEN`, nhánh đúng đầu tiên được chọn.
7. **Đặt tên rõ ý nghĩa.** `is_fully_paid`, `is_overdue`, `is_due_date_missing` dễ hiểu hơn `flag1` hoặc `status2`.
8. **Quyết định phạm vi tính.** Tính ở `SELECT`, CTE, view hay lưu cờ? Với cờ phụ thuộc thời gian, cần có thời điểm đánh giá rõ ràng.
9. **Sử dụng đúng trong lọc và tổng hợp.** `SUM(CASE ... THEN 1 ELSE 0 END)` đếm số hàng thỏa điều kiện; `COUNT(CASE ... THEN 1 ELSE 0 END)` thì không.
10. **Giữ định nghĩa nhất quán.** Cùng một tên cờ phải được hiểu giống nhau giữa báo cáo, API và ứng dụng.

**Điểm cần ghi nhớ:** `CASE WHEN ... THEN ... ELSE ... END` là cách diễn đạt rẽ nhánh rất hữu ích trong SQL. Để tạo **cột cờ từ điều kiện nghiệp vụ**, quan trọng nhất là xác định đúng quy tắc và ngoại lệ trước khi chuyển thành biểu thức. Khi dữ liệu thiếu, mốc thời gian, thứ tự ưu tiên và kiểu giá trị trả về đều được mô tả tường minh, cờ sẽ có ý nghĩa đáng tin cậy trong truy vấn, báo cáo và giao tiếp giữa các hệ thống.
