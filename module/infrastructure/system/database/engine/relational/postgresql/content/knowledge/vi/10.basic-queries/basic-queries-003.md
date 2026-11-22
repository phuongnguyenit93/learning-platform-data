# WHERE, toán tử so sánh và toán tử logic trong PostgreSQL

## 1. Vì sao `WHERE` là nền tảng của truy vấn dữ liệu?

Khi bảng có vài hàng, bạn có thể chạy `SELECT * FROM orders` rồi tự nhìn để tìm đơn hàng cần xử lý. Nhưng khi bảng có hàng triệu đơn hàng, ứng dụng phải mô tả **điều kiện lọc** rõ ràng để PostgreSQL trả đúng những hàng cần thiết.

Mệnh đề **`WHERE`** dùng để giữ lại các hàng thỏa một **biểu thức điều kiện** (*predicate*). Các điều kiện có thể dựa trên:

- **Toán tử so sánh**: `=`, `<>`, `!=`, `<`, `<=`, `>`, `>=`.
- **Toán tử logic**: `AND`, `OR`, `NOT`.
- **Kiểm tra NULL**: `IS NULL`, `IS NOT NULL`, `IS DISTINCT FROM`.
- **Tập giá trị**: `IN`, `NOT IN`, `ANY`, `ALL`, `EXISTS`.
- **Khoảng giá trị**: `BETWEEN`, `NOT BETWEEN`.
- **Mẫu văn bản**: `LIKE`, `ILIKE`.
- **Các biểu thức khác**: hàm, phép tính, điều kiện liên kết với truy vấn con.

Ví dụ:

```sql
SELECT order_id, customer_name, total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount >= 250000
ORDER BY order_id;
```

Ý nghĩa: “Lấy các đơn **đã thanh toán** và có tổng tiền **từ 250.000 trở lên**, rồi hiển thị theo mã đơn tăng dần”.

Hai ý quan trọng:

1. `WHERE` là **biểu thức logic**, không phải một vòng lặp do bạn phải tự lập trình. PostgreSQL quyết định cách thực thi vật lý theo kế hoạch truy vấn.
2. Một điều kiện trong PostgreSQL có thể cho **TRUE, FALSE hoặc UNKNOWN (NULL)**. Trong `WHERE`, **chỉ những hàng có kết quả TRUE** được giữ lại.

Phần thứ hai giải thích nhiều lỗi phổ biến khi lọc các cột có giá trị `NULL`.

## 2. Chuẩn bị bộ dữ liệu thực hành

Bài học dùng **PostgreSQL** và một schema thử nghiệm riêng. Các câu lệnh dưới đây giả định bạn có quyền tạo schema và bảng trong một database thực hành; không chạy tùy tiện trên production.

### 2.1. Tạo bảng đơn hàng

```sql
CREATE SCHEMA IF NOT EXISTS where_lab;

CREATE TABLE where_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('NEW', 'PAID', 'SHIPPED', 'CANCELLED')
    ),
    total_amount numeric(12,2) NOT NULL
        CHECK (total_amount >= 0),
    priority smallint NOT NULL
        CHECK (priority BETWEEN 1 AND 5),
    placed_at timestamptz NOT NULL,
    shipped_at timestamptz,
    region text
);
```

Giải thích:

| Cột | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `order_id` | `bigint` | Mã đơn duy nhất |
| `customer_name` | `text` | Tên khách hàng |
| `status` | `text` | Trạng thái có tập giá trị cố định |
| `total_amount` | `numeric(12,2)` | Tổng tiền đơn |
| `priority` | `smallint` | Độ ưu tiên từ 1 tới 5 |
| `placed_at` | `timestamptz` | Thời điểm đặt đơn |
| `shipped_at` | `timestamptz`, cho phép NULL | Thời điểm giao cho đơn vị vận chuyển, nếu có |
| `region` | `text`, cho phép NULL | Khu vực, có thể chưa được nhập |

`status` và `total_amount` có `NOT NULL`. Nhưng `region` và `shipped_at` được phép `NULL`, rất hữu ích để luyện **logic ba giá trị**.

### 2.2. Nạp dữ liệu minh họa

```sql
INSERT INTO where_lab.orders
    (
        order_id,
        customer_name,
        status,
        total_amount,
        priority,
        placed_at,
        shipped_at,
        region
    )
VALUES
    (
        101, 'An', 'NEW', 120000.00, 3,
        TIMESTAMPTZ '2026-10-01 09:00:00+07',
        NULL, 'Hà Nội'
    ),
    (
        102, 'Bình', 'PAID', 350000.00, 5,
        TIMESTAMPTZ '2026-10-02 10:30:00+07',
        NULL, 'Hồ Chí Minh'
    ),
    (
        103, 'Chi', 'SHIPPED', 250000.00, 4,
        TIMESTAMPTZ '2026-10-02 15:00:00+07',
        TIMESTAMPTZ '2026-10-04 11:00:00+07',
        'Đà Nẵng'
    ),
    (
        104, 'Dung', 'CANCELLED', 95000.00, 2,
        TIMESTAMPTZ '2026-10-03 11:30:00+07',
        NULL, NULL
    ),
    (
        105, 'Em', 'PAID', 80000.00, 1,
        TIMESTAMPTZ '2026-10-03 20:00:00+07',
        NULL, 'Hà Nội'
    ),
    (
        106, 'Phúc', 'SHIPPED', 550000.00, 5,
        TIMESTAMPTZ '2026-10-04 08:00:00+07',
        TIMESTAMPTZ '2026-10-05 12:00:00+07',
        'Hồ Chí Minh'
    ),
    (
        107, 'Giang', 'NEW', 250000.00, 2,
        TIMESTAMPTZ '2026-10-05 14:00:00+07',
        NULL, 'Đà Nẵng'
    ),
    (
        108, 'Hà', 'PAID', 250000.00, 3,
        TIMESTAMPTZ '2026-10-06 09:00:00+07',
        NULL, NULL
    );
```

Các thời điểm được ghi với múi giờ `+07` để các ví dụ lọc theo ngày có nghĩa rõ ràng. Nếu đã chạy script nạp dữ liệu một lần, chạy lại nguyên câu `INSERT` sẽ vi phạm khóa chính. Hãy thực hành trong database mới hoặc quản lý việc nạp lại có chủ đích.

Tóm tắt tám hàng:

| ID | Khách | Trạng thái | Tổng tiền | Ưu tiên | Khu vực |
| ---: | --- | --- | ---: | ---: | --- |
| 101 | An | NEW | 120.000 | 3 | Hà Nội |
| 102 | Bình | PAID | 350.000 | 5 | Hồ Chí Minh |
| 103 | Chi | SHIPPED | 250.000 | 4 | Đà Nẵng |
| 104 | Dung | CANCELLED | 95.000 | 2 | NULL |
| 105 | Em | PAID | 80.000 | 1 | Hà Nội |
| 106 | Phúc | SHIPPED | 550.000 | 5 | Hồ Chí Minh |
| 107 | Giang | NEW | 250.000 | 2 | Đà Nẵng |
| 108 | Hà | PAID | 250.000 | 3 | NULL |

### 2.3. Mẫu cú pháp `SELECT ... WHERE`

```sql
SELECT <danh_sach_cot>
FROM <ten_bang>
WHERE <dieu_kien>
ORDER BY <cot_sap_xep>;
```

Với bảng mẫu:

```sql
SELECT order_id, customer_name, total_amount
FROM where_lab.orders
WHERE total_amount > 200000
ORDER BY order_id;
```

Kết quả gồm các mã `102, 103, 106, 107, 108` vì tổng tiền của chúng lớn hơn 200.000.

**Không có `ORDER BY`, SQL không đảm bảo thứ tự các hàng được trả về.** Tránh phụ thuộc thứ tự của lệnh `INSERT` hoặc thứ tự vật lý trong bảng.

## 3. Toán tử so sánh cơ bản

PostgreSQL hỗ trợ các toán tử:

| Toán tử | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `=` | Bằng | `status = 'PAID'` |
| `<>` | Khác | `status <> 'CANCELLED'` |
| `!=` | Khác (PostgreSQL chấp nhận) | `status != 'CANCELLED'` |
| `>` | Lớn hơn | `total_amount > 100000` |
| `>=` | Lớn hơn hoặc bằng | `total_amount >= 100000` |
| `<` | Nhỏ hơn | `priority < 3` |
| `<=` | Nhỏ hơn hoặc bằng | `priority <= 3` |

`<>` là cú pháp **khác** trong SQL chuẩn. PostgreSQL cũng chấp nhận `!=`; hai cách viết thường mang cùng ý nghĩa.

### 3.1. `=`: lấy đúng trạng thái

```sql
SELECT order_id, customer_name, status
FROM where_lab.orders
WHERE status = 'PAID'
ORDER BY order_id;
```

Kết quả:

| order_id | customer_name | status |
| ---: | --- | --- |
| 102 | Bình | PAID |
| 105 | Em | PAID |
| 108 | Hà | PAID |

Điều kiện là phép so sánh giá trị, **không phải phép gán**. Trong `WHERE`, `=` không có nghĩa “đặt status thành PAID”.

### 3.2. `<>` và `!=`: không bằng

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE status <> 'CANCELLED'
ORDER BY order_id;
```

Kết quả gồm tất cả mã **trừ 104**, vì 104 là `CANCELLED`.

Có thể viết:

```sql
WHERE status != 'CANCELLED'
```

nhưng nên chọn một quy ước chung trong dự án; `<>` thường dễ đọc với người quen SQL chuẩn.

### 3.3. So sánh lớn/nhỏ và ranh giới

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount >= 250000
ORDER BY order_id;
```

Các mã được giữ: `102, 103, 106, 107, 108`.

Khác biệt giữa `>` và `>=`:

- `total_amount > 250000` giữ `102` và `106`.
- `total_amount >= 250000` còn giữ thêm `103`, `107` và `108`, vì ba đơn này có tổng đúng 250.000.

Khi lọc giá, số lượng hoặc thời gian, sai khác một dấu bằng có thể gây lỗi nghiệp vụ ở **biên của khoảng**.

### 3.4. So sánh các giá trị có kiểu dữ liệu phù hợp

Cột `total_amount` là `numeric(12,2)`, nên:

```sql
WHERE total_amount >= 250000.00
```

thể hiện một ranh giới tiền chính xác theo thập phân. Tránh gửi giá trị tiền đã được tính bằng kiểu dấu phẩy động nhị phân `double` ở ứng dụng rồi kỳ vọng PostgreSQL tự khôi phục độ chính xác ban đầu.

Với thời điểm `timestamptz`, nên so sánh với giá trị timestamp có múi giờ được xác định rõ thay vì một chuỗi ngày giờ có ngữ nghĩa múi giờ không rõ ràng.

## 4. `WHERE` giữ TRUE, không giữ FALSE hoặc UNKNOWN

Nhiều người học SQL nghĩ điều kiện chỉ có hai kết quả: đúng hoặc sai. Nhưng PostgreSQL dùng **logic ba giá trị** đối với những biểu thức có `NULL`:

- **TRUE**: điều kiện đúng.
- **FALSE**: điều kiện sai.
- **UNKNOWN** (được biểu diễn bằng `NULL` trong kết quả boolean): chưa biết đúng hay sai.

Một bảng minh họa:

| Kết quả biểu thức `WHERE` | Hàng có được giữ? |
| --- | --- |
| TRUE | **Có** |
| FALSE | Không |
| UNKNOWN / NULL | Không |

Ví dụ:

```sql
SELECT
    order_id,
    region,
    region = 'Hà Nội' AS is_ha_noi
FROM where_lab.orders
ORDER BY order_id;
```

Với các hàng `104` và `108`, `region` là `NULL`; biểu thức `region = 'Hà Nội'` trả **NULL/UNKNOWN**, không phải `false`.

Lọc:

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE region = 'Hà Nội'
ORDER BY order_id;
```

trả `101` và `105`. Những hàng có region `NULL` không được giữ, vì chưa thể xác định chúng có phải Hà Nội hay không.

### 4.1. `NULL` không phải số 0 hay chuỗi rỗng

`NULL` có nghĩa dữ liệu thiếu/không xác định/không áp dụng, tùy mô hình. Những giá trị sau **không tương đương**:

```sql
SELECT
    0 IS NULL AS zero_is_null,
    '' IS NULL AS empty_string_is_null,
    NULL IS NULL AS null_is_null;
```

`0` là một số, `''` là một chuỗi rỗng, còn `NULL` là ký hiệu đặc biệt của SQL. Không dùng `NULL` một cách tùy tiện để đại diện đồng thời “chưa nhập”, “không áp dụng”, “đang chờ” nếu nghiệp vụ cần phân biệt.

## 5. Kiểm tra NULL bằng `IS NULL` và `IS NOT NULL`

### 5.1. Vì sao không dùng `= NULL`?

Sai:

```sql
SELECT order_id
FROM where_lab.orders
WHERE region = NULL;
```

Biểu thức `region = NULL` trả UNKNOWN trong logic SQL thông thường, kể cả khi `region` bản thân cũng là NULL. Vì vậy, truy vấn không trả các hàng có region NULL như người mới học mong đợi.

Đúng:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE region IS NULL
ORDER BY order_id;
```

Kết quả là `104` và `108`.

### 5.2. `IS NOT NULL`

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE region IS NOT NULL
ORDER BY order_id;
```

Truy vấn trả những hàng có region thực sự có giá trị: `101, 102, 103, 105, 106, 107`.

Tương tự, để tìm đơn đã có thời gian giao vận:

```sql
SELECT order_id, shipped_at
FROM where_lab.orders
WHERE shipped_at IS NOT NULL
ORDER BY order_id;
```

Trên bộ mẫu: `103` và `106`.

**Chú ý nghiệp vụ:** `shipped_at IS NOT NULL` kiểm tra có thời điểm giao vận, không tự bảo đảm trạng thái đơn còn là `SHIPPED`. Quy tắc đồng bộ hai trường phải được ứng dụng/ràng buộc database thiết kế phù hợp.

### 5.3. `NOT (=)` không thay thế `IS NULL`

```sql
-- Không trả hàng region NULL:
SELECT order_id
FROM where_lab.orders
WHERE NOT (region = 'Hà Nội')
ORDER BY order_id;
```

Kết quả của `NOT UNKNOWN` vẫn là **UNKNOWN**, nên các hàng 104 và 108 vẫn bị loại. Muốn bao gồm cả region NULL, phải viết rõ:

```sql
SELECT order_id
FROM where_lab.orders
WHERE region <> 'Hà Nội'
   OR region IS NULL
ORDER BY order_id;
```

Một cách PostgreSQL khác sẽ được giới thiệu ở phần tiếp theo: `IS DISTINCT FROM`.

## 6. So sánh có xét NULL bằng `IS DISTINCT FROM`

PostgreSQL hỗ trợ cú pháp:

```sql
a IS DISTINCT FROM b
a IS NOT DISTINCT FROM b
```

Đây là các phép so sánh **null-safe**: chúng trả TRUE hoặc FALSE thay vì UNKNOWN do `NULL`.

### 6.1. Bảng so sánh

| `a` | `b` | `a = b` | `a IS DISTINCT FROM b` | `a IS NOT DISTINCT FROM b` |
| --- | --- | --- | --- | --- |
| 1 | 1 | TRUE | FALSE | TRUE |
| 1 | 2 | FALSE | TRUE | FALSE |
| 1 | NULL | UNKNOWN | TRUE | FALSE |
| NULL | NULL | UNKNOWN | FALSE | TRUE |

Ví dụ:

```sql
SELECT
    NULL::integer = NULL::integer AS regular_equal,
    NULL::integer IS NOT DISTINCT FROM NULL::integer
        AS null_safe_equal,
    NULL::integer IS DISTINCT FROM 10
        AS null_safe_different;
```

`IS NOT DISTINCT FROM` hữu ích khi muốn coi **hai giá trị NULL** là tương đương trong một phép đối chiếu có chủ đích.

### 6.2. Tìm vùng khác Hà Nội, kể cả chưa khai báo

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE region IS DISTINCT FROM 'Hà Nội'
ORDER BY order_id;
```

Các mã: `102, 103, 104, 106, 107, 108`.

So với `WHERE region <> 'Hà Nội'`, truy vấn mới **có thêm 104 và 108**, vì NULL được coi là khác giá trị chuỗi cụ thể.

**Lựa chọn đúng phụ thuộc nghĩa nghiệp vụ:**

- “Khách hàng thuộc một khu vực khác Hà Nội **đã biết**” → `region <> 'Hà Nội'`.
- “Khách hàng **không có giá trị region chính xác là Hà Nội**, kể cả region chưa nhập” → `region IS DISTINCT FROM 'Hà Nội'`.

Không mặc định mọi `<>` nên đổi thành `IS DISTINCT FROM`. Hai điều kiện diễn đạt hai ý khác nhau khi có NULL.

## 7. Toán tử logic `AND`, `OR`, `NOT`

### 7.1. `AND`: tất cả điều kiện phải đúng

```sql
SELECT
    order_id,
    status,
    total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount >= 250000
ORDER BY order_id;
```

Giữ `102` và `108`. Đơn `105` đã thanh toán nhưng chỉ 80.000 nên bị loại.

`AND` tương ứng với “**và**”: cả hai điều kiện phải TRUE.

### 7.2. `OR`: ít nhất một điều kiện đúng

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE status = 'NEW'
   OR priority = 5
ORDER BY order_id;
```

Kết quả: `101, 102, 106, 107`.

- `101` và `107` có status NEW.
- `102` và `106` có priority 5.

Một hàng thỏa cả hai điều kiện vẫn chỉ xuất hiện **một lần từ bộ lọc của cùng hàng**, không bị nhân đôi chỉ vì dùng `OR`.

### 7.3. `NOT`: phủ định một điều kiện

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE NOT (status = 'CANCELLED')
ORDER BY order_id;
```

Vì `status` trong bảng mẫu luôn `NOT NULL`, điều kiện tương đương `status <> 'CANCELLED'` và trả bảy mã khác 104.

Nhưng khi cột có NULL, `NOT` không biến UNKNOWN thành TRUE; đây là điểm rất quan trọng khi viết điều kiện loại trừ.

### 7.4. Thứ tự ưu tiên: `NOT`, `AND`, `OR`

Trong những biểu thức logic thông thường của PostgreSQL:

1. `NOT` có độ ưu tiên cao hơn `AND`.
2. `AND` có độ ưu tiên cao hơn `OR`.
3. Dấu ngoặc `(...)` cho phép bạn quyết định thứ tự nhóm điều kiện tường minh.

So sánh hai câu:

```sql
-- Ý nghĩa: (NEW và ưu tiên 5) hoặc PAID
WHERE status = 'NEW'
  AND priority = 5
   OR status = 'PAID'
```

và:

```sql
-- Ý nghĩa: NEW và (ưu tiên 5 hoặc PAID)
WHERE status = 'NEW'
  AND (priority = 5 OR status = 'PAID')
```

Chúng **không tương đương**. Với bộ mẫu, biểu thức đầu trả các đơn PAID vì nhánh `OR status = 'PAID'`; biểu thức sau không có đơn nào vì không thể vừa NEW vừa PAID trong cùng một cột trạng thái.

**Khuyến nghị:** với `WHERE` kết hợp cả `AND` và `OR`, **luôn dùng ngoặc để thể hiện ý định nghiệp vụ**, dù bạn nhớ đúng thứ tự ưu tiên.

## 8. Ba giá trị logic và bảng chân trị

Khi một điều kiện có thể UNKNOWN, kết quả của `AND`, `OR` và `NOT` cần hiểu theo logic ba giá trị.

### 8.1. Bảng chân trị cho `AND` và `OR`

Dùng ký hiệu:

- **T** = TRUE.
- **F** = FALSE.
- **U** = UNKNOWN/NULL.

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| T | T | T | T |
| T | F | F | T |
| T | U | U | T |
| F | T | F | T |
| F | F | F | F |
| F | U | F | U |
| U | T | U | T |
| U | F | F | U |
| U | U | U | U |

Với `NOT`:

| A | NOT A |
| --- | --- |
| T | F |
| F | T |
| U | U |

Hai quy tắc trực quan:

- `FALSE AND UNKNOWN = FALSE` vì điều kiện đã chắc chắn sai.
- `TRUE OR UNKNOWN = TRUE` vì điều kiện đã chắc chắn đúng.

Nhưng:

- `TRUE AND UNKNOWN = UNKNOWN`.
- `FALSE OR UNKNOWN = UNKNOWN`.
- `NOT UNKNOWN = UNKNOWN`.

### 8.2. Thử ngay trong PostgreSQL

```sql
SELECT
    TRUE AND NULL::boolean AS true_and_unknown,
    FALSE AND NULL::boolean AS false_and_unknown,
    TRUE OR NULL::boolean AS true_or_unknown,
    FALSE OR NULL::boolean AS false_or_unknown,
    NOT NULL::boolean AS not_unknown;
```

Kết quả:

| Biểu thức | Giá trị |
| --- | --- |
| `TRUE AND NULL` | NULL |
| `FALSE AND NULL` | FALSE |
| `TRUE OR NULL` | TRUE |
| `FALSE OR NULL` | NULL |
| `NOT NULL` | NULL |

Nếu hiển thị trong `psql`, ô NULL có thể trống hoặc hiện theo cấu hình hiển thị. Đừng nhầm ô trống do NULL với chuỗi rỗng.

### 8.3. Ví dụ kết hợp `OR` với cột NULL

```sql
SELECT order_id, region, status
FROM where_lab.orders
WHERE region = 'Hà Nội'
   OR status = 'CANCELLED'
ORDER BY order_id;
```

Kết quả: `101, 104, 105`.

Đơn 104 có `region = NULL`, nhưng `status = 'CANCELLED'` là TRUE. `UNKNOWN OR TRUE` cho TRUE, nên đơn 104 vẫn được giữ.

Ngược lại:

```sql
SELECT order_id, region, status
FROM where_lab.orders
WHERE region = 'Hà Nội'
  AND status = 'CANCELLED'
ORDER BY order_id;
```

Không có hàng nào: các đơn Hà Nội không CANCELLED; đơn CANCELLED có region NULL, làm `UNKNOWN AND TRUE` thành UNKNOWN.

### 8.4. `IS TRUE`, `IS FALSE` và `IS UNKNOWN`

Khi muốn kiểm tra **trạng thái của một biểu thức boolean**, dùng:

```sql
SELECT
    NULL::boolean IS TRUE AS is_true,
    NULL::boolean IS FALSE AS is_false,
    NULL::boolean IS UNKNOWN AS is_unknown;
```

Kết quả: `false`, `false`, `true`.

Một biểu thức:

```sql
WHERE (region = 'Hà Nội') IS NOT TRUE
```

giữ những hàng mà điều kiện `region = 'Hà Nội'` **không phải TRUE**, bao gồm cả FALSE và UNKNOWN. Kết quả có thể giống `region IS DISTINCT FROM 'Hà Nội'` trong trường hợp so sánh cụ thể này; tuy nhiên, `IS DISTINCT FROM` thường diễn đạt ngữ nghĩa so sánh null-safe rõ ràng hơn.

## 9. `BETWEEN` và `NOT BETWEEN`: lọc theo khoảng

### 9.1. `BETWEEN` bao gồm hai đầu mút

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount BETWEEN 250000 AND 350000
ORDER BY order_id;
```

Kết quả: `102, 103, 107, 108`.

`BETWEEN 250000 AND 350000` tương đương về mặt logic với:

```sql
WHERE total_amount >= 250000
  AND total_amount <= 350000
```

Cả **250000** và **350000** đều được bao gồm.

### 9.2. `NOT BETWEEN`

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount NOT BETWEEN 250000 AND 350000
ORDER BY order_id;
```

Trả `101, 104, 105, 106` vì tổng tiền nằm ngoài khoảng [250000, 350000].

Nếu giá trị của cột hoặc biên là NULL, biểu thức có thể trả UNKNOWN; `NOT BETWEEN` không tự cho tất cả hàng NULL đi qua.

### 9.3. Biên thấp phải đứng trước biên cao

Thông thường:

```sql
WHERE total_amount BETWEEN 350000 AND 250000
```

không phải cách viết “từ 250000 đến 350000 theo chiều ngược”. Với giá trị số không NULL, điều kiện này không có hàng nào thỏa.

PostgreSQL có cú pháp `BETWEEN SYMMETRIC` nếu cần chấp nhận biên được truyền theo thứ tự bất kỳ:

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount BETWEEN SYMMETRIC 350000 AND 250000
ORDER BY order_id;
```

Với bộ mẫu, kết quả giống khoảng từ 250000 tới 350000.

Dù vậy, trong mã ứng dụng thường nên **kiểm tra/sắp thứ tự hai biên đầu vào** trước, thay vì dựa vào cú pháp đặc biệt để che việc người dùng nhập sai.

### 9.4. Khoảng ngày giờ: tránh nhầm ngày kết thúc

Với cột `placed_at timestamptz`, việc viết:

```sql
WHERE placed_at BETWEEN
    TIMESTAMPTZ '2026-10-02 00:00:00+07'
    AND TIMESTAMPTZ '2026-10-04 00:00:00+07'
```

**không** bao trùm cả ngày 04/10: nó chỉ bao gồm đến đúng 00:00 của ngày đó.

Khi muốn lấy **toàn bộ ngày 02, 03 và 04 tháng 10 theo múi giờ +07**, dùng **khoảng nửa mở**:

```sql
SELECT order_id, placed_at
FROM where_lab.orders
WHERE placed_at >= TIMESTAMPTZ '2026-10-02 00:00:00+07'
  AND placed_at <  TIMESTAMPTZ '2026-10-05 00:00:00+07'
ORDER BY order_id;
```

Kết quả: `102, 103, 104, 105, 106`.

Cách viết `>= start AND < next_day` tránh bỏ sót các thời điểm có phần lẻ giây ở cuối ngày. Trong hệ thống đa múi giờ, **“ngày” phải được định nghĩa theo timezone nghiệp vụ**; không tự áp dụng `+07` cho mọi dữ liệu toàn cầu.

## 10. `IN` và `NOT IN`: so sánh với một tập giá trị

### 10.1. `IN` tương đương nhiều nhánh `OR`

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE status IN ('PAID', 'SHIPPED')
ORDER BY order_id;
```

Kết quả: `102, 103, 105, 106, 108`.

Đối với các giá trị không NULL, điều kiện trên tương đương:

```sql
WHERE status = 'PAID'
   OR status = 'SHIPPED'
```

`IN` giúp câu SQL gọn và rõ khi một cột phải thuộc tập giá trị cho phép.

### 10.2. Kết hợp `IN` với `AND`

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount >= 250000
ORDER BY order_id;
```

Kết quả: `102, 103, 106, 108`.

Đơn `105` dù PAID nhưng chỉ có 80000 nên bị loại.

### 10.3. `NOT IN`: cẩn thận với NULL

Điều kiện:

```sql
WHERE status NOT IN ('CANCELLED', 'SHIPPED')
```

trả các trạng thái khác hai giá trị trên; với bảng mẫu status NOT NULL, kết quả là `101, 102, 105, 107, 108`.

Nhưng nếu danh sách có **NULL**, ngữ nghĩa sẽ khác trực giác:

```sql
SELECT
    1 NOT IN (2, NULL) AS result_one,
    2 NOT IN (2, NULL) AS result_two,
    1 IN (2, NULL) AS result_three;
```

Kết quả:

| Biểu thức | Giá trị |
| --- | --- |
| `1 NOT IN (2, NULL)` | UNKNOWN/NULL |
| `2 NOT IN (2, NULL)` | FALSE |
| `1 IN (2, NULL)` | UNKNOWN/NULL |

Vì `1` không bằng `2` nhưng không thể xác định nó có bằng giá trị NULL hay không, `NOT IN` trả UNKNOWN. Trong `WHERE`, UNKNOWN bị loại.

**Lỗi rất phổ biến:** dùng `NOT IN (SELECT nullable_column FROM ...)` khi subquery có thể trả NULL, rồi truy vấn trả ít hàng hơn dự kiến, thậm chí không có hàng nào.

### 10.4. Danh sách rỗng và tham số động

Cú pháp:

```sql
-- Không hợp lệ:
WHERE status IN ()
```

không phải SQL hợp lệ trong PostgreSQL. Nếu ứng dụng có danh sách trạng thái có thể rỗng, nên quyết định rõ ý nghĩa:

- Danh sách rỗng nghĩa là **không lấy hàng nào**.
- Danh sách rỗng nghĩa là **không áp dụng bộ lọc**.
- Danh sách rỗng là **input sai cần báo lỗi**.

Không nên tự tạo chuỗi SQL `IN ()`. Có thể dùng `= ANY($1::text[])` với tham số mảng được bind phù hợp, hoặc xây điều kiện SQL động bằng API an toàn, tùy yêu cầu.

## 11. `ANY`, `ALL` và toán tử so sánh với mảng

PostgreSQL có cú pháp so sánh một giá trị với nhiều phần tử:

```sql
expression operator ANY (array_expression)
expression operator ALL (array_expression)
```

### 11.1. `= ANY` với mảng

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE status = ANY (ARRAY['PAID', 'SHIPPED']::text[])
ORDER BY order_id;
```

Kết quả tương đương `status IN ('PAID', 'SHIPPED')` với tập giá trị ví dụ.

Dạng này hữu ích khi ứng dụng truyền **một tham số mảng** qua driver thay vì phải tự ghép danh sách `'PAID','SHIPPED'` vào SQL.

### 11.2. `> ALL`

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount > ALL (ARRAY[100000, 200000]::numeric[])
ORDER BY order_id;
```

Hàng phải có tổng tiền lớn hơn **cả 100000 và 200000**, tức lớn hơn 200000. Kết quả: `102, 103, 106, 107, 108`.

`ALL` tương ứng với “**mọi phần tử**”, còn `ANY` tương ứng “**ít nhất một phần tử**” theo toán tử được dùng.

### 11.3. Tập rỗng và NULL

Một số kết quả dễ bất ngờ:

```sql
SELECT
    'PAID' = ANY (ARRAY[]::text[]) AS any_empty,
    10 > ALL (ARRAY[]::integer[]) AS all_empty,
    10 = ANY (ARRAY[NULL]::integer[]) AS any_null;
```

| Biểu thức | Kết quả |
| --- | --- |
| `x = ANY(empty_array)` | FALSE |
| `x > ALL(empty_array)` | TRUE |
| `10 = ANY(ARRAY[NULL])` | UNKNOWN/NULL |

Đây là hệ quả logic của “tồn tại ít nhất một phần tử thỏa điều kiện” và “mọi phần tử đều thỏa điều kiện”. Khi làm việc với mảng chứa NULL, kết quả còn phụ thuộc toán tử và từng phần tử; không được mặc nhiên coi mọi NULL như FALSE.

**Phân biệt:** `ANY (subquery)` cũng tồn tại với cú pháp khác; khi tham số có kiểu mảng, cần đảm bảo viết đúng dạng `ANY(array_expression)`.

## 12. `EXISTS` và `NOT EXISTS`: lọc theo sự tồn tại của hàng liên quan

Khi muốn biết có hay không hàng phù hợp trong bảng khác, `EXISTS` thường diễn đạt ý định rõ hơn việc lấy một danh sách rồi thử `IN` hoặc `NOT IN`.

### 12.1. Tạo bảng thanh toán minh họa

```sql
CREATE TABLE where_lab.payments (
    payment_id bigint PRIMARY KEY,
    order_id bigint NOT NULL
        REFERENCES where_lab.orders(order_id),
    paid_amount numeric(12,2) NOT NULL
        CHECK (paid_amount >= 0),
    state text NOT NULL
        CHECK (state IN ('PENDING', 'CONFIRMED'))
);

INSERT INTO where_lab.payments
    (payment_id, order_id, paid_amount, state)
VALUES
    (1001, 102, 350000, 'CONFIRMED'),
    (1002, 103, 250000, 'CONFIRMED'),
    (1003, 106, 550000, 'CONFIRMED'),
    (1004, 108, 250000, 'PENDING');
```

Bộ dữ liệu này chỉ để học truy vấn. `orders.status` và `payments.state` không nhất thiết mô phỏng toàn bộ logic thanh toán của hệ thống thật; ví dụ có thể có trạng thái đang đồng bộ hoặc nhiều lần thanh toán.

### 12.2. Tìm đơn có thanh toán đã xác nhận

```sql
SELECT o.order_id, o.customer_name
FROM where_lab.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM where_lab.payments AS p
    WHERE p.order_id = o.order_id
      AND p.state = 'CONFIRMED'
)
ORDER BY o.order_id;
```

Kết quả: `102, 103, 106`.

`EXISTS` trả TRUE nếu truy vấn con tìm thấy **ít nhất một hàng** phù hợp; giá trị cụ thể được chọn trong `SELECT 1` không quan trọng đối với phép kiểm tra tồn tại.

Truy vấn con sử dụng `p.order_id = o.order_id` để liên hệ với từng hàng ở truy vấn ngoài, nên đây là **correlated subquery**.

### 12.3. Tìm đơn chưa có thanh toán nào

```sql
SELECT o.order_id, o.customer_name
FROM where_lab.orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM where_lab.payments AS p
    WHERE p.order_id = o.order_id
)
ORDER BY o.order_id;
```

Kết quả: `101, 104, 105, 107`.

Đơn 108 có một thanh toán `PENDING` nên **không** thuộc nhóm “chưa có thanh toán nào”. Nếu muốn “chưa có thanh toán CONFIRMED”, hãy thêm `AND p.state = 'CONFIRMED'` bên trong `NOT EXISTS`; lúc ấy đơn 108 sẽ được giữ.

### 12.4. Vì sao `NOT EXISTS` thường an toàn hơn `NOT IN` với NULL?

`NOT EXISTS` kiểm tra **có hàng phù hợp hay không**; nó không có vấn đề “một NULL trong danh sách làm toàn bộ phép `NOT IN` thành UNKNOWN” như khi dùng subquery có thể trả NULL.

Điều này không có nghĩa mọi `NOT EXISTS` luôn nhanh hơn `NOT IN`. PostgreSQL có optimizer và nhiều chiến lược thực thi; chọn cú pháp ưu tiên **đúng ngữ nghĩa**, rồi xem `EXPLAIN` với dữ liệu thật khi cần.

## 13. Lọc văn bản với `LIKE` và `ILIKE`

### 13.1. `LIKE`: tìm theo mẫu

`LIKE` cho phép hai ký tự wildcard:

| Wildcard | Ý nghĩa |
| --- | --- |
| `%` | Không hoặc nhiều ký tự |
| `_` | Đúng một ký tự theo cơ chế pattern matching |

Ví dụ tên bắt đầu bằng A:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name LIKE 'A%'
ORDER BY order_id;
```

Kết quả: `101, An`.

Tên kết thúc bằng chữ `n`:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name LIKE '%n'
ORDER BY order_id;
```

Ví dụ này khớp `An`. Dấu `%` ở đầu cho phép không hoặc nhiều ký tự đứng trước `n`.

### 13.2. `ILIKE`: không phân biệt chữ hoa/thường

`ILIKE` là phần mở rộng của PostgreSQL:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name ILIKE 'a%'
ORDER BY order_id;
```

Truy vấn có thể tìm `An` mặc dù mẫu dùng chữ `a` thường.

**Không nhầm `ILIKE` với tự bỏ dấu tiếng Việt.** Nó xử lý khớp mẫu không phân biệt hoa/thường theo cơ chế locale phù hợp, không đảm bảo rằng `'nguyen'` sẽ khớp `'Nguyễn'`. Nếu nghiệp vụ cần tìm không phân biệt dấu, phải thiết kế chiến lược normalization/tìm kiếm riêng.

### 13.3. Tìm ký tự `%` hoặc `_` theo nghĩa đen

Vì `%` và `_` là wildcard, khi cần tìm ký tự thực tế phải escape chúng. Ví dụ:

```sql
SELECT
    'A_B' LIKE 'A!_B' ESCAPE '!' AS match_literal_underscore,
    'A%B' LIKE 'A!%B' ESCAPE '!' AS match_literal_percent;
```

Cả hai trả TRUE. `ESCAPE '!'` nói rằng dấu `!` dùng để escape ký tự mẫu theo sau. Trong code ứng dụng, việc escape wildcard phải được tách biệt với cơ chế **bind SQL parameters**: bind giúp truyền giá trị an toàn, nhưng không tự biến `%` thành ký tự thường trong ý nghĩa của `LIKE`.

### 13.4. `NOT LIKE`, `NOT ILIKE` và NULL

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name NOT ILIKE 'a%'
ORDER BY order_id;
```

Với `customer_name NOT NULL`, truy vấn trả những tên không bắt đầu bằng chữ A theo quy tắc `ILIKE`.

Nếu cột chuỗi cho phép NULL, kết quả `NULL NOT LIKE 'A%'` là UNKNOWN; hàng đó **không tự được giữ**. Muốn đưa NULL vào kết quả loại trừ, phải thêm điều kiện `IS NULL` hoặc dùng quy tắc phù hợp khác.

### 13.5. Collation ảnh hưởng so sánh text

`=`, `<`, `>`, `ORDER BY` và một số thao tác text phụ thuộc quy tắc collation. Đặc biệt với ICU nondeterministic collations, sự bằng nhau của các chuỗi khác byte có thể được định nghĩa khác so với collation `"C"`.

Ví dụ yêu cầu thứ tự mang tính mã ký tự:

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name COLLATE "C" > 'B' COLLATE "C"
ORDER BY customer_name COLLATE "C", order_id;
```

Điều này không phải yêu cầu sắp xếp tự nhiên theo tiếng Việt. Cần chọn collation theo ngữ nghĩa dữ liệu, và biết rằng hỗ trợ `LIKE`/`ILIKE` trên một số nondeterministic collations còn phụ thuộc phiên bản PostgreSQL.

## 14. Các điều kiện kết hợp thường gặp

### 14.1. Dùng ngoặc để thể hiện yêu cầu

Yêu cầu: “Lấy đơn **PAID hoặc SHIPPED**, nhưng chỉ nếu **tổng tiền từ 250.000**”.

Đúng:

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE (status = 'PAID' OR status = 'SHIPPED')
  AND total_amount >= 250000
ORDER BY order_id;
```

Kết quả: `102, 103, 106, 108`.

Một cách ngắn hơn:

```sql
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount >= 250000
```

Sai ý định nếu bỏ ngoặc như sau:

```sql
WHERE status = 'PAID'
   OR status = 'SHIPPED'
  AND total_amount >= 250000
```

Vì `AND` ưu tiên trước `OR`, điều kiện này tương đương:

```sql
WHERE status = 'PAID'
   OR (
       status = 'SHIPPED'
       AND total_amount >= 250000
   )
```

Nó sẽ lấy **mọi đơn PAID**, kể cả đơn `105` chỉ có 80.000 — trái yêu cầu ban đầu.

### 14.2. Kết hợp `NOT` với biểu thức phức hợp

Yêu cầu: “Tìm đơn **không ở trạng thái PAID** và **không có ưu tiên từ 4 trở lên**”.

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE NOT (
    status = 'PAID'
    OR priority >= 4
)
ORDER BY order_id;
```

Kết quả: `101, 104, 107`.

Theo định luật De Morgan trong logic ba giá trị của SQL, có thể diễn đạt:

```sql
WHERE status <> 'PAID'
  AND priority < 4
```

Vì `status` và `priority` không NULL trong bảng mẫu, hai cách viết khớp nhau ở đây. Khi thêm điều kiện trên cột nullable, phải kiểm tra tác động của UNKNOWN một cách cẩn thận; đừng tự thay `NOT (cột = giá_trị)` bằng `IS DISTINCT FROM` mà không xem yêu cầu đối với NULL.

### 14.3. Lọc đơn chưa giao vận nhưng đã thanh toán

```sql
SELECT order_id, status, shipped_at
FROM where_lab.orders
WHERE status = 'PAID'
  AND shipped_at IS NULL
ORDER BY order_id;
```

Kết quả: `102, 105, 108`.

Đây là một kiểu lọc rất phổ biến: phối hợp điều kiện trạng thái với cột thời điểm tùy chọn. Cách viết `shipped_at = NULL` sẽ không đúng.

### 14.4. Dùng `COALESCE` khi muốn gán giá trị thay thế cho NULL

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE COALESCE(region, 'CHƯA KHAI BÁO') = 'CHƯA KHAI BÁO'
ORDER BY order_id;
```

Kết quả `104` và `108`.

Tuy nhiên, nếu một hàng thật sự lưu chuỗi `'CHƯA KHAI BÁO'`, câu trên cũng giữ nó; do đó ý nghĩa **khác** `region IS NULL`.

`COALESCE` tạo giá trị thay thế, không biến NULL thành một chuỗi thực sự được lưu trong bảng. Khi cần lọc chính xác những hàng không có region, `IS NULL` thường rõ hơn và có thể dễ được tối ưu bằng index phù hợp.

## 15. Thời gian, múi giờ và điều kiện ranh giới

### 15.1. So sánh `date`, `timestamp` và `timestamptz`

Trong PostgreSQL:

- `date`: ngày lịch, không có thời gian trong ngày.
- `timestamp without time zone`: ngày giờ, không kèm thông tin múi giờ.
- `timestamp with time zone` / `timestamptz`: thời điểm được diễn giải với ngữ nghĩa múi giờ; hiển thị theo timezone của session.

Với dữ liệu `placed_at timestamptz`, biểu thức:

```sql
WHERE placed_at >= TIMESTAMPTZ '2026-10-03 00:00:00+07'
```

có mốc thời gian rõ ràng. Tránh dùng một chuỗi `'2026-10-03'` mà không hiểu PostgreSQL sẽ ép kiểu và diễn giải timezone như thế nào trong ngữ cảnh đó.

### 15.2. Lấy một ngày theo giờ Việt Nam

Ví dụ chọn toàn bộ ngày 03/10/2026 theo `+07`:

```sql
SELECT order_id, placed_at
FROM where_lab.orders
WHERE placed_at >= TIMESTAMPTZ '2026-10-03 00:00:00+07'
  AND placed_at <  TIMESTAMPTZ '2026-10-04 00:00:00+07'
ORDER BY order_id;
```

Kết quả: `104` và `105`.

Dùng khoảng nửa mở tránh phải tự ghi mốc `23:59:59.999999` ở cuối ngày, vốn dễ sai nếu dữ liệu có độ chính xác vi giây khác hoặc cần tính biên ngày.

### 15.3. Tại sao `placed_at::date = ...` không phải luôn lựa chọn tốt?

```sql
SELECT order_id
FROM where_lab.orders
WHERE (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
      = DATE '2026-10-03';
```

Câu trên có thể hợp lý khi muốn chuyển mỗi timestamp sang **ngày địa phương**. Nhưng nó áp dụng một **biểu thức lên cột**, khiến một B-tree index thông thường trên `placed_at` không tự tương đương với bộ lọc khoảng thời gian.

Khi có thể xác định hai mốc thời gian chính xác, dạng `placed_at >= start AND placed_at < end` thường dễ tận dụng index trên chính cột `placed_at` hơn. Còn nếu cần expression index, phải xét tính chất biểu thức và điều kiện tối ưu riêng.

### 15.4. Những khoảng giờ có DST

Múi giờ `+07` không có thay đổi DST ở Việt Nam hiện nay, nhưng những timezone khác có thể đổi giờ mùa hè. Để lọc “một ngày địa phương” cho một timezone có DST, không nên tự giả định mọi ngày dài đúng 24 giờ. Hãy xác định **mốc bắt đầu của ngày và mốc bắt đầu ngày kế tiếp trong timezone nghiệp vụ**, rồi so sánh timestamp theo khoảng nửa mở.

## 16. `WHERE` với `JOIN` và vị trí của điều kiện

Mệnh đề `WHERE` có thể xuất hiện trong truy vấn nhiều bảng. Với `INNER JOIN`, nhiều trường hợp điều kiện lọc trên bảng đã join có thể viết trong `ON` hoặc `WHERE` và cho cùng tập hàng. Nhưng với **`LEFT JOIN`**, vị trí điều kiện có thể làm thay đổi ngữ nghĩa.

### 16.1. `INNER JOIN`

```sql
SELECT
    o.order_id,
    o.status,
    p.payment_id,
    p.state
FROM where_lab.orders AS o
JOIN where_lab.payments AS p
    ON p.order_id = o.order_id
WHERE p.state = 'CONFIRMED'
ORDER BY o.order_id;
```

Kết quả gồm đơn `102, 103, 106` với thanh toán đã xác nhận.

`ON` xác định mối quan hệ giữa các bảng; `WHERE` xác định những hàng kết quả cần giữ.

### 16.2. `LEFT JOIN` và điều kiện trong `WHERE`

```sql
SELECT
    o.order_id,
    p.payment_id,
    p.state
FROM where_lab.orders AS o
LEFT JOIN where_lab.payments AS p
    ON p.order_id = o.order_id
WHERE p.state = 'CONFIRMED'
ORDER BY o.order_id;
```

Dù dùng `LEFT JOIN`, điều kiện `WHERE p.state = 'CONFIRMED'` loại những hàng không có payment vì `p.state` là NULL ở phía phải. Kết quả lại chỉ có `102, 103, 106`.

### 16.3. Điều kiện bên trong `ON` giữ các hàng phía trái

Nếu muốn lấy **tất cả đơn**, chỉ ghép những payment đã CONFIRMED nếu có:

```sql
SELECT
    o.order_id,
    o.status,
    p.payment_id,
    p.state
FROM where_lab.orders AS o
LEFT JOIN where_lab.payments AS p
    ON p.order_id = o.order_id
   AND p.state = 'CONFIRMED'
ORDER BY o.order_id;
```

Lúc này tất cả 8 đơn đều được giữ; các đơn không có payment CONFIRMED nhận NULL ở các cột từ `p`.

**Quy tắc:** với outer join, đừng tùy tiện chuyển điều kiện từ `ON` sang `WHERE` hoặc ngược lại. Sự khác nhau có thể khiến bạn mất những hàng mà `LEFT JOIN` vốn được dùng để giữ.

### 16.4. Tìm hàng không có đối tượng liên quan

```sql
SELECT o.order_id
FROM where_lab.orders AS o
LEFT JOIN where_lab.payments AS p
    ON p.order_id = o.order_id
WHERE p.payment_id IS NULL
ORDER BY o.order_id;
```

Kết quả: `101, 104, 105, 107`.

Tương đương về ý định với `NOT EXISTS` ở phần trước vì `payment_id` là khóa chính `NOT NULL`. Với bảng có nhiều payment trên một order, phải xác định điều kiện “không có payment nào” hay “không có payment đạt trạng thái cụ thể” một cách tường minh.

## 17. `WHERE` khác `HAVING` như thế nào?

Một truy vấn tổng hợp thường dùng:

- **`WHERE`** để lọc **hàng đầu vào** trước khi nhóm.
- **`GROUP BY`** để gom hàng thành nhóm.
- **`HAVING`** để lọc **nhóm** theo điều kiện tổng hợp.

### 17.1. Chỉ lọc từng hàng

```sql
SELECT
    status,
    COUNT(*) AS order_count
FROM where_lab.orders
WHERE total_amount >= 250000
GROUP BY status
ORDER BY status;
```

Các hàng có tổng tiền từ 250000 là `102, 103, 106, 107, 108`. Sau nhóm:

| status | order_count |
| --- | ---: |
| NEW | 1 |
| PAID | 2 |
| SHIPPED | 2 |

Trạng thái CANCELLED không có đơn nào đạt điều kiện nên không xuất hiện.

### 17.2. Lọc nhóm bằng `HAVING`

```sql
SELECT
    status,
    COUNT(*) AS order_count
FROM where_lab.orders
GROUP BY status
HAVING COUNT(*) >= 2
ORDER BY status;
```

Kết quả:

| status | order_count |
| --- | ---: |
| NEW | 2 |
| PAID | 3 |
| SHIPPED | 2 |

CANCELLED chỉ có một hàng nên nhóm bị loại.

### 17.3. `WHERE COUNT(*) >= 2` là sai chỗ

Không thể dùng aggregate `COUNT(*)` trực tiếp như điều kiện `WHERE` cùng mức SELECT để lọc nhóm. Hãy dùng `HAVING` hoặc dùng subquery/CTE để lấy kết quả tổng hợp rồi lọc ở bên ngoài.

Ví dụ:

```sql
WITH counts AS (
    SELECT status, COUNT(*) AS order_count
    FROM where_lab.orders
    GROUP BY status
)
SELECT status, order_count
FROM counts
WHERE order_count >= 2
ORDER BY status;
```

Ở truy vấn ngoài, `order_count` đã là cột đầu ra của CTE, nên `WHERE order_count >= 2` là hợp lệ.

### 17.4. Bí quyết nhớ thứ tự xử lý logic

Một thứ tự khái niệm hữu ích là:

```text
FROM / JOIN
     |
     v
WHERE           (lọc các hàng)
     |
     v
GROUP BY        (tạo nhóm)
     |
     v
HAVING          (lọc nhóm)
     |
     v
SELECT          (chọn biểu thức đầu ra)
     |
     v
ORDER BY        (sắp xếp kết quả)
     |
     v
LIMIT / OFFSET  (giới hạn kết quả)
```

Đây là **thứ tự logic để hiểu SQL**, không bắt buộc là thứ tự thực thi vật lý mà optimizer chọn.

## 18. `WHERE` trong `UPDATE` và `DELETE`

`WHERE` không chỉ dùng cho `SELECT`. Nó còn quyết định **hàng nào bị thay đổi hoặc xóa**.

### 18.1. `UPDATE ... WHERE`

```sql
BEGIN;

UPDATE where_lab.orders
SET priority = 4
WHERE order_id = 107
  AND status = 'NEW'
RETURNING order_id, status, priority;

ROLLBACK;
```

Ví dụ thực hiện trong một transaction rồi rollback để không làm thay đổi lâu dài dữ liệu bài tập.

Điều kiện `WHERE` ở đây còn kiểm tra trạng thái đơn trước khi chỉnh priority. Nếu đơn không còn NEW, thao tác có thể cập nhật 0 hàng.

**Không giả định “cập nhật 0 hàng” là thành công nghiệp vụ** nếu ứng dụng yêu cầu phải cập nhật đúng một đơn. Hãy đọc `RETURNING` hoặc số hàng bị ảnh hưởng và xử lý tình huống cạnh tranh giữa các transaction.

### 18.2. `DELETE ... WHERE`

```sql
BEGIN;

DELETE FROM where_lab.orders
WHERE status = 'CANCELLED'
  AND total_amount < 100000
RETURNING order_id, status;

ROLLBACK;
```

Với bộ mẫu, điều kiện chọn đơn 104. Do có `ROLLBACK`, dữ liệu không bị xóa vĩnh viễn sau khi transaction kết thúc.

**Cảnh báo:** bỏ `WHERE` trong `DELETE FROM where_lab.orders` sẽ xóa **mọi hàng** đáp ứng quyền/ràng buộc. Trước khi thực thi thao tác phá hủy, nên chạy một câu `SELECT` với cùng điều kiện trong môi trường kiểm soát để kiểm tra tập hàng dự kiến. Trong production, còn cần chính sách backup và rollback rõ ràng.

### 18.3. Điều kiện đúng không có nghĩa không cần transaction

Ví dụ “chỉ trừ tồn kho nếu đủ hàng”:

```sql
UPDATE where_lab.inventory
SET available = available - 1
WHERE product_id = 1001
  AND available >= 1
RETURNING product_id, available;
```

Đây là mẫu minh họa cú pháp (bảng `inventory` chưa được tạo trong bài), cho thấy nên gom kiểm tra và cập nhật vào cùng một statement khi có thể.

Với nghiệp vụ nhiều bước, vẫn cần thiết kế transaction, khóa và mức cô lập phù hợp để giữ toàn vẹn dữ liệu.

## 19. Điều kiện `WHERE` có được thực thi từ trái sang phải không?

**Không được dựa vào việc PostgreSQL luôn đánh giá các điều kiện theo thứ tự bạn viết.** Bộ tối ưu hóa có thể biến đổi, đẩy xuống hoặc sắp xếp lại các biểu thức để tạo kế hoạch thực thi hợp lý.

Ví dụ:

```sql
WHERE status = 'PAID'
  AND total_amount > 100000
```

Bạn không nên coi điều kiện `status = 'PAID'` luôn chạy trước rồi mới kiểm tra `total_amount`. Đối với hai so sánh thuần túy này, kết quả không bị ảnh hưởng bởi thứ tự; nhưng nếu một biểu thức có khả năng phát sinh lỗi/side effect, việc giả định **short-circuit trái sang phải** có thể gây lỗi.

### 19.1. Đừng dùng `AND` để bảo vệ phép cast không an toàn một cách tuyệt đối

Ví dụ một bảng nhập CSV có cột text `raw_quantity`. Bạn muốn lọc chỉ các số nguyên trước khi ép kiểu:

```sql
-- Không nên coi thứ tự AND là hàng rào bảo đảm:
WHERE raw_quantity ~ '^[0-9]+$'
  AND raw_quantity::integer > 0
```

Bộ tối ưu hóa có thể tổ chức đánh giá biểu thức khác với thứ tự văn bản. Ngoài ra, chuỗi toàn chữ số có thể vẫn vượt giới hạn `integer`.

Phương án đúng tùy nghiệp vụ: kiểm tra/chuẩn hóa trong staging, tạo cột đã chuyển kiểu có kiểm soát, hoặc viết biểu thức `CASE` phù hợp để điều kiện hóa phép chuyển:

```sql
SELECT raw_quantity
FROM (
    VALUES ('3'), ('-1'), ('abc'), ('0')
) AS input(raw_quantity)
WHERE CASE
    WHEN raw_quantity ~ '^[0-9]{1,9}$'
    THEN raw_quantity::integer > 0
    ELSE FALSE
END;
```

Ở ví dụ giới hạn tối đa 9 chữ số thập phân không âm, giá trị chắc chắn nhỏ hơn giới hạn integer 32-bit; câu truy vấn trả `'3'`. Đây chỉ là ví dụ bảo vệ phép ép kiểu với miền đầu vào đơn giản, không phải trình kiểm tra số nguyên quốc tế hoàn chỉnh.

**Đừng dùng các hàm có side effect rồi kỳ vọng các nhánh `AND`/`OR` điều khiển thứ tự gọi hàm như câu lệnh lập trình tuần tự.**

### 19.2. `WHERE` là khai báo tập kết quả

Thay vì nghĩ:

```text
1. Kiểm tra status.
2. Sau đó kiểm tra amount.
3. Nếu đúng thì kiểm tra date.
```

hãy nghĩ:

```text
Chọn những hàng thỏa:
status = 'PAID'
AND amount >= 250000
AND placed_at thuộc khoảng ngày được yêu cầu.
```

Sau đó xem PostgreSQL thực hiện bằng index, scan, join và filter như thế nào qua `EXPLAIN` khi có yêu cầu hiệu năng.

## 20. Chọn điều kiện giúp truy vấn sử dụng index

Không phải mọi điều kiện `WHERE` đều tận dụng index giống nhau. Ví dụ:

```sql
CREATE INDEX idx_orders_status_amount
ON where_lab.orders (status, total_amount);

CREATE INDEX idx_orders_placed_at
ON where_lab.orders (placed_at);
```

Những index này là ví dụ để giải thích, không phải danh sách index bắt buộc trong production.

### 20.1. B-tree và các phép so sánh cơ bản

Một index B-tree thông thường phù hợp với nhiều phép so sánh:

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount >= 250000
ORDER BY total_amount, order_id;
```

Với index `(status, total_amount)`, điều kiện **bằng nhau trên cột đầu** và **phạm vi trên cột thứ hai** là một cấu trúc thường có lợi cho B-tree.

Với bảng chỉ có 8 hàng, PostgreSQL có thể chọn quét toàn bảng vì nó rẻ hơn dùng index. Không đánh giá hiệu quả index trên tập dữ liệu minh họa quá nhỏ.

### 20.2. Điều kiện trên biểu thức của cột

```sql
SELECT order_id
FROM where_lab.orders
WHERE placed_at::date = DATE '2026-10-03';
```

Biểu thức trên cột có thể khiến index B-tree thông thường của `placed_at` không được sử dụng như với khoảng thời gian trực tiếp.

Dạng khoảng nửa mở:

```sql
SELECT order_id
FROM where_lab.orders
WHERE placed_at >= TIMESTAMPTZ '2026-10-03 00:00:00+07'
  AND placed_at <  TIMESTAMPTZ '2026-10-04 00:00:00+07';
```

thường dễ tận dụng index `placed_at` hơn cho mục đích lọc theo thời điểm.

**Chú ý timezone:** hai cách trên chỉ tương đương về ngày nếu phiên/cách cast dùng cùng timezone nghiệp vụ. `placed_at::date` chịu ảnh hưởng timezone của session; bản so sánh dùng `+07` đã cố định mốc theo múi giờ đó.

### 20.3. `LIKE 'prefix%'` và `LIKE '%contains%'`

`LIKE 'An%'` có tiền tố cố định, có thể hưởng lợi từ index phù hợp tùy collation/operator class.

`LIKE '%An%'` có wildcard ở đầu, nên B-tree thông thường không dễ khai thác như prefix search. Khi cần tìm chuỗi con trên bảng lớn, PostgreSQL có thể dùng extension `pg_trgm` với GIN/GiST index phù hợp, nhưng lợi ích còn phụ thuộc mẫu, độ chọn lọc và khối lượng dữ liệu.

Không tạo một index cho mọi điều kiện text trước khi biết workload.

### 20.4. `OR` có thể dùng nhiều index hoặc scan

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE status = 'PAID'
   OR priority = 5;
```

PostgreSQL có thể chọn những chiến lược khác nhau như bitmap index scans kết hợp (nếu có index phù hợp), sequential scan hoặc các biến đổi khác theo thống kê và chi phí. Không phải cứ xuất hiện `OR` là chắc chắn index không dùng được.

### 20.5. Điều kiện NULL và partial index

Nếu truy vấn thường xuyên tìm đơn chưa giao vận:

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE shipped_at IS NULL
  AND status = 'PAID';
```

Một **partial index** có thể phù hợp khi bảng rất lớn và số hàng cần xử lý là nhóm nhỏ:

```sql
CREATE INDEX idx_orders_unshipped_paid
ON where_lab.orders (order_id)
WHERE shipped_at IS NULL
  AND status = 'PAID';
```

Index này chỉ bao gồm những hàng thỏa điều kiện trong `WHERE` của định nghĩa index. Nó có chi phí bảo trì khi ghi và không tự giúp mọi kiểu query khác. Cần đo `EXPLAIN` cùng tần suất cập nhật và kích thước dữ liệu trước khi áp dụng.

### 20.6. Đọc `EXPLAIN`

```sql
EXPLAIN
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount >= 250000;
```

Bạn có thể thấy những node như:

- `Seq Scan`: quét tuần tự.
- `Index Scan` hoặc `Index Only Scan`: đọc qua index theo điều kiện phù hợp.
- `Bitmap Index Scan` và `Bitmap Heap Scan`: tổ hợp việc tìm hàng qua index và đọc heap.
- `Filter`: điều kiện được áp dụng để loại hàng.
- `Index Cond`: điều kiện được index tận dụng trong kế hoạch.

`EXPLAIN (ANALYZE, BUFFERS)` còn thực thi truy vấn để đo thời gian/hàng thực tế. Với `SELECT` thường tương đối an toàn hơn; với `UPDATE`, `DELETE` hoặc những câu SQL có side effect, **EXPLAIN ANALYZE vẫn thực hiện tác động**, nên phải dùng transaction/rollback hoặc môi trường test khi đo.

## 21. Tham số hóa `WHERE` trong ứng dụng

Không xây query bằng cách nối trực tiếp input vào SQL:

```java
// Không an toàn và khó kiểm soát kiểu dữ liệu:
String sql = "SELECT * FROM where_lab.orders WHERE status = '"
           + userInput + "'";
```

Cách này tạo rủi ro SQL injection và lỗi quote.

### 21.1. PreparedStatement trong Java/JDBC

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class OrderRepository {

    public void findLargePaidOrders(Connection connection)
            throws Exception {

        String sql =
            "SELECT order_id, total_amount " +
            "FROM where_lab.orders " +
            "WHERE status = ? AND total_amount >= ? " +
            "ORDER BY order_id";

        try (PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setString(1, "PAID");
            statement.setBigDecimal(
                2, new BigDecimal("250000.00")
            );

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("order_id");
                    BigDecimal amount =
                        rs.getBigDecimal("total_amount");
                    System.out.println(id + " " + amount);
                }
            }
        }
    }
}
```

`?` trong JDBC là placeholder được driver bind, **không phải** việc tự chèn text vào SQL. Dùng `BigDecimal` cho cột `numeric` giúp giữ ý nghĩa thập phân của số tiền.

### 21.2. `PREPARE` trong PostgreSQL

Có thể thử trực tiếp trong `psql`:

```sql
PREPARE find_orders (text, numeric) AS
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status = $1
  AND total_amount >= $2
ORDER BY order_id;

EXECUTE find_orders('PAID', 250000);

DEALLOCATE find_orders;
```

Kết quả: `102` và `108`.

Đây là SQL `PREPARE` của PostgreSQL. Driver có thể sử dụng cơ chế prepared/bind khác ở giao thức mạng; cả hai cùng hướng tới việc phân tách **cấu trúc câu lệnh** và **giá trị tham số**.

### 21.3. Bộ lọc tùy chọn với NULL parameter

Giả sử tham số trạng thái có thể NULL để biểu thị “không lọc theo trạng thái”:

```sql
PREPARE search_optional_status(text) AS
SELECT order_id, status
FROM where_lab.orders
WHERE $1 IS NULL OR status = $1
ORDER BY order_id;

EXECUTE search_optional_status(NULL);
EXECUTE search_optional_status('PAID');

DEALLOCATE search_optional_status;
```

Lần chạy với NULL trả cả 8 đơn; lần chạy `'PAID'` trả 102, 105, 108.

Đây là một mẫu tiện dụng nhưng có thể ảnh hưởng cách optimizer chọn kế hoạch, nhất là với bảng rất lớn và tham số có độ chọn lọc thay đổi mạnh. Khi hiệu năng quan trọng, có thể cần những câu query chuyên biệt theo loại bộ lọc, vẫn sử dụng bind parameters an toàn.

**Quan trọng:** `$1 IS NULL OR status = $1` diễn đạt **NULL tham số nghĩa là không áp dụng bộ lọc**, khác với yêu cầu “tìm các hàng có `status IS NULL`”.

## 22. Những lỗi thường gặp khi viết `WHERE`

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| Dùng `= NULL` | Điều kiện trả UNKNOWN, không tìm hàng NULL | `IS NULL` |
| Dùng `<> NULL` | Không lấy được hàng như mong đợi | `IS NOT NULL` |
| Dùng `NOT (col = x)` và mong lấy NULL | `NOT UNKNOWN` vẫn UNKNOWN | Thêm `IS NULL` hoặc dùng `IS DISTINCT FROM` đúng nghĩa |
| `AND` và `OR` không có ngoặc | Bộ lọc sai theo precedence | Đặt ngoặc theo yêu cầu |
| Nhầm `>` và `>=` | Bỏ sót biên | Xác định rõ inclusive/exclusive |
| Nhầm `BETWEEN` là khoảng mở | Lấy cả hai đầu mút | Dùng `>`/`<` nếu muốn khoảng mở |
| Dùng `BETWEEN` đến đúng 00:00 cuối ngày | Bỏ sót phần lớn ngày kết thúc | Dùng `>= start AND < next_day` |
| `NOT IN` với subquery có NULL | Kết quả có thể UNKNOWN hàng loạt | Kiểm soát NULL hoặc dùng `NOT EXISTS` |
| Ghép input vào chuỗi SQL | SQL injection, lỗi quote | Bind parameters |
| Dùng `ILIKE` để “xóa dấu” | Không tìm đủ các tên có dấu | Thiết kế search normalization riêng |
| Viết `col = 'a' OR 'b'` | `'b'` không phải điều kiện boolean hợp lệ | `col IN ('a','b')` hoặc hai so sánh |
| Viết `10 < amount < 100` | Không phải cách biểu diễn chuỗi so sánh SQL thích hợp | `amount > 10 AND amount < 100` |
| Dùng `WHERE COUNT(*) > ...` | Aggregate không dùng trực tiếp ở WHERE cùng mức | `HAVING COUNT(*) > ...` |
| Đặt điều kiện phía phải `LEFT JOIN` trong WHERE | Làm mất hàng không khớp | Xem nên đặt trong `ON` hay WHERE |
| Không thêm `WHERE` cho `UPDATE/DELETE` | Có thể sửa/xóa toàn bảng | Kiểm tra trước, dùng transaction |
| Tưởng optimizer chạy điều kiện từ trái sang phải | Có thể lỗi với cast/hàm không an toàn | Dùng `CASE`/validation phù hợp |
| Đặt hàm lên cột index trong mọi bộ lọc | Index thông thường có thể kém hữu ích | Cân nhắc range/expression index |
| Không có `ORDER BY` mà kỳ vọng thứ tự ổn định | Thứ tự kết quả thay đổi | `ORDER BY` và khóa phá hòa |
| Dùng alias trong `WHERE` cùng SELECT | Alias thường chưa khả dụng ở mức WHERE | Lặp biểu thức hoặc dùng CTE/subquery |

### 22.1. Sai: `status = 'PAID' OR 'SHIPPED'`

Không đúng:

```sql
-- Sai cú pháp/kiểu boolean:
SELECT *
FROM where_lab.orders
WHERE status = 'PAID' OR 'SHIPPED';
```

Đúng:

```sql
SELECT *
FROM where_lab.orders
WHERE status = 'PAID'
   OR status = 'SHIPPED';
```

Hoặc:

```sql
SELECT *
FROM where_lab.orders
WHERE status IN ('PAID', 'SHIPPED');
```

Mỗi nhánh `OR` phải là một biểu thức điều kiện có ý nghĩa boolean.

### 22.2. Sai: viết chuỗi so sánh kiểu toán học

Không dùng:

```sql
-- Không diễn đạt khoảng theo cú pháp SQL:
WHERE 100000 < total_amount < 500000
```

Đúng:

```sql
WHERE total_amount > 100000
  AND total_amount < 500000
```

Đây là một khoảng **mở** ở cả hai đầu; nếu muốn bao gồm 100000 hoặc 500000 thì thay toán tử tương ứng bằng `>=` hoặc `<=`.

### 22.3. Nhầm so sánh text với so sánh số

```sql
SELECT '10'::text < '2'::text AS text_comparison,
       10::integer < 2::integer AS number_comparison;
```

Theo collation `"C"` hoặc thứ tự từ điển tương tự, chuỗi `'10'` có thể đứng trước `'2'` vì ký tự đầu `'1'` đứng trước `'2'`, dù số 10 lớn hơn 2.

Nếu một giá trị là **số lượng** hay **giá tiền**, phải lưu trong kiểu số phù hợp thay vì text rồi dựa vào so sánh chuỗi.

### 22.4. Nhầm `NULL` với giá trị mặc định

Nếu region NULL nghĩa là chưa được gán, đừng tự viết:

```sql
WHERE COALESCE(region, 'Hà Nội') = 'Hà Nội'
```

trừ khi nghiệp vụ thật sự định nghĩa “chưa gán region thì xem là Hà Nội”. Đây là một quy tắc **biến đổi ý nghĩa dữ liệu**, không đơn thuần là cách kiểm tra NULL.

## 23. Bài tập thực hành có đáp án

Dùng bảng `where_lab.orders` và `where_lab.payments` đã tạo ở đầu bài.

### Bài 1. Lấy tất cả đơn có tổng tiền từ 250.000 trở lên

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount >= 250000
ORDER BY order_id;
```

**Đáp án:** mã `102, 103, 106, 107, 108`.

### Bài 2. Lấy đơn PAID có tổng tiền lớn hơn 100.000

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status = 'PAID'
  AND total_amount > 100000
ORDER BY order_id;
```

**Đáp án:** `102` và `108`. Đơn 105 có tiền 80.000 nên bị loại.

### Bài 3. Lấy đơn NEW hoặc có ưu tiên 5

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE status = 'NEW'
   OR priority = 5
ORDER BY order_id;
```

**Đáp án:** `101, 102, 106, 107`.

### Bài 4. Lấy đơn không phải PAID và ưu tiên dưới 4

```sql
SELECT order_id, status, priority
FROM where_lab.orders
WHERE status <> 'PAID'
  AND priority < 4
ORDER BY order_id;
```

**Đáp án:** `101, 104, 107`.

### Bài 5. Lấy đơn có region chưa khai báo

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE region IS NULL
ORDER BY order_id;
```

**Đáp án:** `104` và `108`. Không dùng `region = NULL`.

### Bài 6. Lấy tất cả đơn không có region là Hà Nội, kể cả region NULL

```sql
SELECT order_id, region
FROM where_lab.orders
WHERE region IS DISTINCT FROM 'Hà Nội'
ORDER BY order_id;
```

**Đáp án:** `102, 103, 104, 106, 107, 108`.

Giải thích: `IS DISTINCT FROM` cho phép coi NULL khác một giá trị non-NULL.

### Bài 7. Tổng tiền từ 250.000 đến 350.000, bao gồm cả hai biên

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount BETWEEN 250000 AND 350000
ORDER BY order_id;
```

**Đáp án:** `102, 103, 107, 108`.

### Bài 8. Đơn PAID hoặc SHIPPED có tổng tiền từ 250.000

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE status IN ('PAID', 'SHIPPED')
  AND total_amount >= 250000
ORDER BY order_id;
```

**Đáp án:** `102, 103, 106, 108`.

### Bài 9. Lấy đơn từ ngày 02 đến hết ngày 04/10/2026 (+07)

```sql
SELECT order_id, placed_at
FROM where_lab.orders
WHERE placed_at >= TIMESTAMPTZ '2026-10-02 00:00:00+07'
  AND placed_at < TIMESTAMPTZ '2026-10-05 00:00:00+07'
ORDER BY order_id;
```

**Đáp án:** `102, 103, 104, 105, 106`.

### Bài 10. Lấy đơn chưa giao vận nhưng trạng thái PAID

```sql
SELECT order_id, status
FROM where_lab.orders
WHERE shipped_at IS NULL
  AND status = 'PAID'
ORDER BY order_id;
```

**Đáp án:** `102, 105, 108`.

### Bài 11. Lấy tên khách hàng bắt đầu bằng chữ a, không phân biệt case

```sql
SELECT order_id, customer_name
FROM where_lab.orders
WHERE customer_name ILIKE 'a%'
ORDER BY order_id;
```

**Đáp án:** `101 - An`.

### Bài 12. Tìm đơn có payment đã xác nhận

```sql
SELECT o.order_id
FROM where_lab.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM where_lab.payments AS p
    WHERE p.order_id = o.order_id
      AND p.state = 'CONFIRMED'
)
ORDER BY o.order_id;
```

**Đáp án:** `102, 103, 106`.

### Bài 13. Tìm đơn chưa có payment nào

```sql
SELECT o.order_id
FROM where_lab.orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM where_lab.payments AS p
    WHERE p.order_id = o.order_id
)
ORDER BY o.order_id;
```

**Đáp án:** `101, 104, 105, 107`.

### Bài 14. Truy vấn nào sẽ không trả hàng nào?

```sql
SELECT order_id
FROM where_lab.orders
WHERE region = NULL;
```

**Đáp án:** truy vấn không lấy được các hàng region NULL vì `= NULL` tạo UNKNOWN, không phải TRUE. Phải dùng `IS NULL`.

### Bài 15. Tại sao `1 NOT IN (2, NULL)` không phải TRUE?

**Đáp án:** kết quả của phép so sánh với NULL là UNKNOWN. `1 <> 2` đúng nhưng `1 <> NULL` không xác định; xét toàn bộ `NOT IN` không thể kết luận TRUE nên trả UNKNOWN.

### Bài 16. Phân biệt `WHERE` và `HAVING`

Yêu cầu: chỉ lấy trạng thái có ít nhất 2 đơn hàng.

```sql
SELECT status, COUNT(*) AS order_count
FROM where_lab.orders
GROUP BY status
HAVING COUNT(*) >= 2
ORDER BY status;
```

**Đáp án:** `NEW (2), PAID (3), SHIPPED (2)`. Không đặt `COUNT(*) >= 2` ở `WHERE` của cùng query level.

### Bài 17. Lấy mọi đơn và payment CONFIRMED nếu có

```sql
SELECT o.order_id, p.payment_id
FROM where_lab.orders AS o
LEFT JOIN where_lab.payments AS p
  ON p.order_id = o.order_id
 AND p.state = 'CONFIRMED'
ORDER BY o.order_id;
```

**Đáp án:** cả 8 đơn đều có hàng kết quả; những đơn không có payment CONFIRMED sẽ có `payment_id NULL`. Nếu chuyển `p.state = 'CONFIRMED'` sang `WHERE`, những đơn không khớp bị loại.

### Bài 18. Viết điều kiện an toàn với số tiền truyền từ ứng dụng

**Đáp án gợi ý:** dùng bind parameter trong JDBC:

```sql
SELECT order_id, total_amount
FROM where_lab.orders
WHERE total_amount >= ?
ORDER BY order_id;
```

Ở Java, dùng `PreparedStatement` và `setBigDecimal` cho số tiền; không nối trực tiếp input người dùng vào chuỗi SQL.

### Bài 19. Tìm các hàng mà điều kiện region = Hà Nội không phải TRUE

```sql
SELECT order_id
FROM where_lab.orders
WHERE (region = 'Hà Nội') IS NOT TRUE
ORDER BY order_id;
```

**Đáp án:** `102, 103, 104, 106, 107, 108`. Kết quả bao gồm hàng region NULL, vì biểu thức UNKNOWN là “không phải TRUE”.

### Bài 20. Lọc đơn có tổng tiền từ 250.000 và trạng thái không phải CANCELLED

```sql
SELECT order_id, status, total_amount
FROM where_lab.orders
WHERE total_amount >= 250000
  AND status <> 'CANCELLED'
ORDER BY order_id;
```

**Đáp án:** `102, 103, 106, 107, 108`. Bảng mẫu không có đơn CANCELLED nào đạt mốc 250.000, nhưng điều kiện trạng thái vẫn thể hiện rõ quy tắc.

## 24. Checklist khi thiết kế một biểu thức `WHERE`

Trước khi đưa một bộ lọc vào ứng dụng, nên xác định:

| Câu hỏi | Hành động phù hợp |
| --- | --- |
| Có cột nào cho phép NULL? | Kiểm tra logic ba giá trị; dùng `IS NULL` hoặc `IS DISTINCT FROM` khi đúng nghĩa |
| Điều kiện gồm cả `AND` và `OR`? | Thêm ngoặc thể hiện đúng ưu tiên |
| Biên khoảng có bao gồm giá trị bằng không? | Chọn `>`/`>=`/`<`/`<=` hoặc `BETWEEN` rõ |
| Lọc ngày có bao gồm toàn ngày cuối? | Dùng khoảng `>= start AND < next_day` |
| Input là chuỗi/numeric/timestamp? | Dùng kiểu dữ liệu phù hợp và bind parameters |
| Có danh sách `IN` do người dùng gửi? | Xử lý danh sách rỗng/NULL và dùng parameterization |
| Có subquery `NOT IN` chứa NULL? | Xem lại ngữ nghĩa, cân nhắc `NOT EXISTS` |
| Có điều kiện ở phía phải `LEFT JOIN`? | Kiểm tra khác biệt giữa `ON` và `WHERE` |
| Có phép toán dễ lỗi như cast text thành số? | Không dựa vào thứ tự đánh giá `AND`; validate hoặc `CASE` |
| Cột có index nhưng bị bọc hàm/cast? | Xem kế hoạch `EXPLAIN`; cân nhắc range/expression index |
| Tìm text bằng `LIKE`/`ILIKE`? | Hiểu wildcard, collation, case/accent và index |
| Truy vấn có tổng hợp? | Dùng `WHERE` lọc hàng, `HAVING` lọc nhóm |
| Query dùng `LIMIT`/phân trang? | Thêm `ORDER BY` ổn định |
| Dùng bộ lọc cho `UPDATE`/`DELETE`? | Xác minh tập hàng và dùng transaction/rollback phù hợp |
| Một điều kiện được viết rất phức tạp? | Diễn giải thành câu nghiệp vụ và dùng ngoặc/subquery rõ |

## 25. Tổng kết

**`WHERE`** là công cụ chính để mô tả tập hàng cần lấy hoặc thay đổi trong PostgreSQL. Hiểu đúng toán tử so sánh và logic giúp truy vấn **đúng kết quả trước khi tối ưu tốc độ**.

Những điểm cần nhớ:

1. **`=`, `<>`, `<`, `<=`, `>`, `>=`** so sánh giá trị; chọn đúng điều kiện biên.
2. **`AND`, `OR`, `NOT`** kết hợp điều kiện. Khi có nhiều toán tử, dùng ngoặc thể hiện rõ ý định thay vì phụ thuộc precedence.
3. PostgreSQL dùng **logic ba giá trị**: TRUE, FALSE, UNKNOWN. `WHERE` chỉ giữ những hàng TRUE.
4. **NULL không so sánh bằng `= NULL`**. Dùng `IS NULL`, `IS NOT NULL` và khi thích hợp `IS [NOT] DISTINCT FROM`.
5. **`BETWEEN` bao gồm hai đầu mút**. Với ngày giờ, nên dùng khoảng nửa mở `>= start AND < end` khi cần toàn bộ ngày.
6. **`IN`** giúp viết gọn nhiều điều kiện OR; **`NOT IN` với NULL** dễ cho kết quả bất ngờ. `EXISTS`/`NOT EXISTS` thích hợp khi kiểm tra sự tồn tại của hàng liên quan.
7. **`LIKE`** tìm mẫu; **`ILIKE`** tìm mẫu không phân biệt case theo PostgreSQL. Chúng không tự tạo tìm kiếm bỏ dấu và cũng không phải mọi pattern đều dùng B-tree index hiệu quả.
8. Với **`LEFT JOIN`**, đặt điều kiện trong `ON` hay `WHERE` có thể thay đổi việc giữ những hàng không khớp.
9. **`WHERE` lọc hàng trước tổng hợp; `HAVING` lọc nhóm** sau `GROUP BY`.
10. Trong **`UPDATE` và `DELETE`**, `WHERE` quyết định phạm vi thay đổi. Kiểm tra kỹ điều kiện và kiểm soát transaction.
11. **Không dựa vào việc điều kiện được đánh giá từ trái sang phải** hoặc có short-circuit như một ngôn ngữ lập trình tuần tự.
12. **Dùng bind parameters** để đưa input vào câu SQL và dùng `EXPLAIN` để quan sát kế hoạch index/scan khi cần tối ưu.

Một thói quen hữu ích khi viết SQL là diễn giải `WHERE` thành câu tiếng Việt thật rõ, ví dụ: “Đơn đã thanh toán **và** tiền từ 250.000, **hoặc** đơn ưu tiên cao chưa có thời gian giao vận”. Sau đó đặt ngoặc biểu diễn chính xác câu đó, xác định cách xử lý NULL và thử trên một bộ dữ liệu có cả trường hợp thông thường lẫn trường hợp biên.
