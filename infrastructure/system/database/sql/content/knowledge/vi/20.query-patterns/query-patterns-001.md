# Khử trùng lặp và chọn một hàng đại diện có quy tắc trong SQL

Khi làm việc với dữ liệu thực tế, bạn thường gặp câu hỏi: **“Mỗi khách hàng chỉ được xuất hiện một hàng trong báo cáo, nhưng khách hàng có nhiều bản ghi lịch sử thì phải giữ hàng nào?”** Ví dụ:

- Chọn **trạng thái mới nhất** của mỗi khách hàng.
- Giữ **địa chỉ đã được xác minh**, nếu có; nếu không thì dùng địa chỉ mới nhất chưa xác minh.
- Chọn **giao dịch gần nhất** cho mỗi tài khoản.
- Chỉ lấy **một phiên bản hợp lệ nhất** trong các bản ghi nhập trùng.
- Chọn **giá ưu tiên** từ nhiều nhà cung cấp theo một chính sách rõ ràng.
- Xử lý một bảng có nhiều dòng trên mỗi khóa rồi nối vào báo cáo **một dòng trên một khách hàng**.

Có hai yêu cầu dễ bị nhầm:

1. **Khử trùng lặp:** xác định những dòng được coi là cùng một thực thể hoặc cùng một sự kiện, rồi chỉ giữ những giá trị cần thiết.
2. **Chọn một hàng đại diện có quy tắc:** trong mỗi nhóm có nhiều dòng, chọn **đúng một dòng** theo thứ tự ưu tiên được định nghĩa trước.

`SELECT DISTINCT` có thể loại các dòng **giống nhau về những cột đang chọn**, nhưng nó không biết hàng nào là **mới nhất, đáng tin cậy nhất hoặc ưu tiên nhất**. Với bài toán chọn đại diện, kỹ thuật phổ biến là **`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)`**; PostgreSQL còn có `DISTINCT ON`, và một số DBMS hỗ trợ các biến thể khác.

Bài thuộc chương **Mẫu truy vấn**, module **Database SQL**. Ví dụ chính dùng **PostgreSQL**, với giải thích phần nào áp dụng rộng rãi và phần nào phụ thuộc hệ quản trị.

## 1. Trùng lặp theo cột, trùng thực thể và lịch sử hợp lệ

Trước khi xóa hoặc loại dòng, bạn phải định nghĩa **“trùng” theo nghĩa nào**.

### 1.1. Các dòng giống nhau trên những cột được chọn

Giả sử bảng nguồn có:

| source_row_id | email | city |
|---:|---|---|
| 1 | `a@example.org` | Hà Nội |
| 2 | `a@example.org` | Hà Nội |
| 3 | `b@example.org` | Huế |

Nếu chỉ chọn `email` và `city`, hai dòng 1 và 2 có giá trị giống nhau hoàn toàn trên hai cột này. `SELECT DISTINCT email, city` sẽ trả hai tổ hợp, không trả ba dòng.

Nhưng nếu chọn thêm `source_row_id`, ba dòng lại khác nhau. **`DISTINCT` xét toàn bộ tổ hợp các biểu thức được chọn**, không tự hiểu khóa nghiệp vụ.

### 1.2. Nhiều dòng trên một thực thể không nhất thiết là dữ liệu sai

Một khách hàng có thể có nhiều bản ghi lịch sử:

| history_id | customer_id | status_code | effective_at |
|---:|---:|---|---|
| 1001 | 1 | NEW | 01/10 |
| 1002 | 1 | ACTIVE | 09/11 |
| 1003 | 1 | PENDING | 09/11 |

Đây có thể là **ba sự kiện hợp lệ** trong lịch sử khách hàng, không phải ba bản sao cần xóa. Nếu báo cáo cần **trạng thái đại diện**, bạn chọn một hàng **trong kết quả truy vấn**; không có nghĩa phải xóa hai dòng lịch sử còn lại khỏi cơ sở dữ liệu.

### 1.3. Trùng theo khóa nghiệp vụ

Một tệp nhập có thể chứa hai dòng cùng `external_order_id`, trong khi mỗi dòng có thời điểm nhập hoặc nội dung khác nhau. Theo hợp đồng dữ liệu, bạn có thể cần **một phiên bản mới nhất trên mỗi external_order_id**.

Nhưng nếu cùng mã đó được tái sử dụng ở nhiều cửa hàng, khóa thật phải là **`(store_id, external_order_id)`**. Chọn sai khóa có thể gộp nhầm những thực thể khác nhau.

### 1.4. Ba câu hỏi cần trả lời trước khi viết SQL

1. **Khóa nhóm là gì?** Ví dụ `customer_id`, `order_id`, hoặc `(store_id, external_id)`.
2. **Đại diện “tốt nhất” là gì?** Mới nhất, đã xác minh, nguồn ưu tiên, còn hiệu lực, giá thấp nhất, hay một thứ tự kết hợp?
3. **Nếu hai dòng cùng mức ưu tiên thì chọn thế nào?** Cần tiêu chí phá hòa (*tie-breaker*) để bảo đảm một hàng duy nhất, ổn định.

Nếu chưa định nghĩa đủ ba điều, viết `DISTINCT` hoặc `LIMIT 1` có thể làm dữ liệu trông gọn hơn nhưng không giải quyết đúng yêu cầu.

## 2. Dữ liệu thực hành: nhiều bản ghi trạng thái trên một khách hàng

Tạo hai bảng PostgreSQL trong **database thực hành**:

- `lesson247_customers`: mỗi khách hàng một dòng.
- `lesson247_status_history`: nhiều bản ghi trạng thái theo khách hàng, có thời điểm hiệu lực và cờ xác minh.

### 2.1. Tạo bảng

```sql
CREATE TABLE lesson247_customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE lesson247_status_history (
    history_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lesson247_customers(customer_id),
    status_code VARCHAR(20) NOT NULL,
    is_verified BOOLEAN NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL,
    source_name VARCHAR(30) NOT NULL
);
```

`history_id` là **khóa duy nhất cho từng bản ghi lịch sử**, còn `customer_id` là **khóa nhóm** khi cần chọn một trạng thái đại diện cho khách hàng. `effective_at` không được phép `NULL` trong bảng mẫu; phần sau sẽ giải thích cách xử lý nếu hệ thống thực tế cho phép thời điểm thiếu.

### 2.2. Thêm dữ liệu

```sql
INSERT INTO lesson247_customers (
    customer_id, customer_name
)
VALUES
    (1, 'An'),
    (2, 'Bình'),
    (3, 'Chi'),
    (4, 'Dũng'),
    (5, 'Hà'),
    (6, 'Lan');

INSERT INTO lesson247_status_history (
    history_id,
    customer_id,
    status_code,
    is_verified,
    effective_at,
    source_name
)
VALUES
    (1001, 1, 'NEW',       FALSE, TIMESTAMPTZ '2026-10-01 09:00:00+07', 'manual'),
    (1002, 1, 'ACTIVE',    TRUE,  TIMESTAMPTZ '2026-11-09 10:00:00+07', 'crm'),
    (1003, 1, 'PENDING',   FALSE, TIMESTAMPTZ '2026-11-09 10:00:00+07', 'import'),

    (1004, 2, 'NEW',       TRUE,  TIMESTAMPTZ '2026-11-01 10:00:00+07', 'manual'),
    (1005, 2, 'ACTIVE',    TRUE,  TIMESTAMPTZ '2026-11-10 08:00:00+07', 'crm'),

    (1006, 3, 'PENDING',   FALSE, TIMESTAMPTZ '2026-11-11 09:00:00+07', 'import'),
    (1007, 3, 'PENDING',   FALSE, TIMESTAMPTZ '2026-11-11 09:00:00+07', 'import'),

    -- Khách hàng 4, Dũng, không có lịch sử.

    (1008, 5, 'ACTIVE',    TRUE,  TIMESTAMPTZ '2026-10-20 10:00:00+07', 'crm'),
    (1009, 5, 'SUSPENDED', FALSE, TIMESTAMPTZ '2026-11-12 09:00:00+07', 'import'),
    (1010, 5, 'ACTIVE',    TRUE,  TIMESTAMPTZ '2026-11-12 09:00:00+07', 'crm'),

    (1011, 6, 'ACTIVE',    TRUE,  TIMESTAMPTZ '2026-11-12 08:00:00+07', 'manual');
```

Dữ liệu có các tình huống có chủ đích:

- **An** có hai bản ghi cùng `effective_at` (1002 và 1003), nhưng khác trạng thái và cờ xác minh.
- **Chi** có hai dòng (1006 và 1007) trùng thời điểm và các thuộc tính nghiệp vụ, nhưng khác `history_id`.
- **Hà** có hai dòng cùng thời điểm (1009 và 1010), một dòng đã xác minh, một dòng chưa.
- **Dũng** không có dòng lịch sử nào.
- **Bình** và **Lan** giúp thấy các trường hợp không có tranh chấp tại thời điểm mới nhất.

**Quan trọng:** không tự động gọi 1002/1003 là “bản ghi trùng cần xóa” chỉ vì cùng `customer_id` và thời điểm. Chúng có thể đại diện cho hai sự kiện được nhận từ các nguồn khác nhau.

### 2.3. Mốc kiểm tra theo quy tắc “mới nhất, rồi history_id lớn nhất”

Định nghĩa quy tắc đầu tiên:

> Với mỗi khách hàng có lịch sử, chọn dòng có `effective_at` **lớn nhất**; nếu thời điểm bằng nhau, chọn `history_id` **lớn nhất**.

Dự kiến:

| customer_id | customer_name | history_id đại diện | Giải thích |
|---:|---|---:|---|
| 1 | An | **1003** | Hai dòng cùng ngày giờ; 1003 lớn hơn 1002 |
| 2 | Bình | **1005** | Thời điểm mới nhất |
| 3 | Chi | **1007** | Trùng thời điểm; phá hòa bằng khóa |
| 4 | Dũng | **Không có dòng** | Chưa có lịch sử |
| 5 | Hà | **1010** | Cùng giờ với 1009; khóa lớn hơn |
| 6 | Lan | **1011** | Chỉ có một dòng |

Chính sách phá hòa `history_id DESC` chỉ hợp lệ nếu doanh nghiệp đồng ý **khóa lớn hơn được ưu tiên khi thời điểm bằng nhau**. Một ID tăng không phải lúc nào cũng phản ánh “sự kiện xảy ra sau” trong hệ thống phân tán hoặc dữ liệu nhập lại. Trong ví dụ, đó là **quy ước chọn ổn định khi hòa**, không phải bằng chứng rằng ID lớn hơn luôn có ngữ nghĩa mới hơn.

## 3. SELECT DISTINCT thực sự làm gì?

`DISTINCT` trả các tổ hợp giá trị **khác nhau trên toàn bộ biểu thức trong danh sách `SELECT`**.

### 3.1. Đếm số khách hàng có lịch sử

```sql
SELECT DISTINCT customer_id
FROM lesson247_status_history
ORDER BY customer_id;
```

Kết quả: `1, 2, 3, 5, 6`. Đúng là mỗi `customer_id` xuất hiện một lần, nhưng **không có cột `history_id` hay `status_code` được chọn**.

### 3.2. Thêm cột có thể khiến DISTINCT không giảm số dòng

```sql
SELECT DISTINCT
    customer_id,
    history_id,
    status_code,
    effective_at
FROM lesson247_status_history
ORDER BY customer_id, history_id;
```

Vì `history_id` là khóa duy nhất, truy vấn vẫn trả **toàn bộ 11 dòng**. Không có hàng nào trùng trên tất cả bốn cột.

Không nên suy luận:

```sql
SELECT DISTINCT customer_id, status_code, effective_at
FROM lesson247_status_history;
```

sẽ trả đúng một dòng trên khách hàng. Một khách hàng có thể có nhiều trạng thái/thời điểm; hơn nữa việc loại các dòng có cùng giá trị biểu thức **không chọn một bản ghi nguyên vẹn theo thứ tự ưu tiên**.

### 3.3. DISTINCT có ý nghĩa khi chỉ muốn tập giá trị

Nếu câu hỏi là “có những mã trạng thái nào?”:

```sql
SELECT DISTINCT status_code
FROM lesson247_status_history
ORDER BY status_code;
```

Đây là cách dùng `DISTINCT` đúng mục đích. Nếu câu hỏi là “**trạng thái đại diện nào cho mỗi khách hàng?**”, bạn cần **quy tắc chọn dòng**.

## 4. GROUP BY khác với chọn một hàng nguyên vẹn

`GROUP BY` gom các dòng theo khóa để tính giá trị tổng hợp như `COUNT`, `MAX`, `MIN` và `SUM`.

```sql
SELECT
    customer_id,
    COUNT(*) AS history_count,
    MAX(effective_at) AS latest_effective_at
FROM lesson247_status_history
GROUP BY customer_id
ORDER BY customer_id;
```

Kết quả có một dòng trên mỗi khách hàng **có lịch sử**, nhưng chỉ biết:

- Có bao nhiêu sự kiện.
- Thời điểm mới nhất là gì.

Nó **chưa chỉ ra dòng `history_id` nào được chọn**, và cũng không tự xác định `status_code` đi cùng thời điểm đó.

### 4.1. Không thể lấy tùy ý cột không thuộc GROUP BY

Trong PostgreSQL, câu sau không hợp lệ:

```sql
-- Sai vì status_code không được GROUP BY hay tổng hợp.
SELECT
    customer_id,
    MAX(effective_at),
    status_code
FROM lesson247_status_history
GROUP BY customer_id;
```

Không có lý do logic nào để PostgreSQL biết `status_code` nào đi cùng `MAX(effective_at)` khi một khách hàng có nhiều trạng thái.

Trong một số chế độ cấu hình hoặc hệ quản trị khác, việc chọn một cột không nhóm/không tổng hợp có thể bị từ chối hoặc có hành vi phụ thuộc quy tắc riêng. Dù DBMS cho chạy, **không được xem giá trị cột không nhóm là một hàng đại diện có quy tắc**.

### 4.2. MAX(status_code) không có nghĩa trạng thái mới nhất

```sql
SELECT
    customer_id,
    MAX(status_code) AS lexicographically_largest_status,
    MAX(effective_at) AS latest_effective_at
FROM lesson247_status_history
GROUP BY customer_id;
```

Hai phép `MAX` có thể chọn giá trị từ **hai dòng khác nhau**. `MAX(status_code)` là so sánh giá trị chuỗi theo quy tắc kiểu/collation của DBMS, không phải “trạng thái của bản ghi mới nhất”.

**Khi cần một hàng nguyên vẹn, các cột được xuất phải đến từ cùng một dòng được chọn theo quy tắc.**

## 5. Mẫu chính: ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)

Hàm cửa sổ `ROW_NUMBER()` gán số thứ tự **1, 2, 3, ...** cho các dòng trong mỗi nhóm, theo thứ tự do `ORDER BY` của cửa sổ xác định.

Cấu trúc:

```sql
ROW_NUMBER() OVER (
    PARTITION BY group_key
    ORDER BY priority_expression_1, priority_expression_2
) AS rn
```

Các phần:

| Thành phần | Ý nghĩa |
|---|---|
| `PARTITION BY customer_id` | Chia dữ liệu thành nhóm theo khách hàng |
| `ORDER BY effective_at DESC` | Dòng mới nhất đứng trước trong mỗi nhóm |
| `, history_id DESC` | Phá hòa khi nhiều dòng có cùng thời điểm |
| `ROW_NUMBER()` | Đánh số 1, 2, 3… trong từng nhóm |
| `WHERE rn = 1` ở truy vấn ngoài | Chọn đúng một dòng đại diện cho mỗi nhóm không rỗng |

### 5.1. Xem thứ tự trước khi lọc

```sql
SELECT
    customer_id,
    history_id,
    status_code,
    is_verified,
    effective_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY effective_at DESC, history_id DESC
    ) AS rn
FROM lesson247_status_history
ORDER BY customer_id, rn;
```

Kết quả đáng chú ý:

| customer_id | history_id | status_code | rn |
|---:|---:|---|---:|
| 1 | 1003 | PENDING | 1 |
| 1 | 1002 | ACTIVE | 2 |
| 1 | 1001 | NEW | 3 |
| 2 | 1005 | ACTIVE | 1 |
| 2 | 1004 | NEW | 2 |
| 3 | 1007 | PENDING | 1 |
| 3 | 1006 | PENDING | 2 |
| 5 | 1010 | ACTIVE | 1 |
| 5 | 1009 | SUSPENDED | 2 |
| 5 | 1008 | ACTIVE | 3 |
| 6 | 1011 | ACTIVE | 1 |

`rn` bắt đầu lại từ 1 cho mỗi `customer_id`.

### 5.2. Chọn rn = 1 bằng CTE

Một cách phổ biến, dễ đọc và dùng được trên nhiều DBMS có hỗ trợ hàm cửa sổ:

```sql
WITH ranked_history AS (
    SELECT
        h.history_id,
        h.customer_id,
        h.status_code,
        h.is_verified,
        h.effective_at,
        h.source_name,
        ROW_NUMBER() OVER (
            PARTITION BY h.customer_id
            ORDER BY h.effective_at DESC, h.history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    customer_id,
    history_id,
    status_code,
    is_verified,
    effective_at,
    source_name
FROM ranked_history
WHERE rn = 1
ORDER BY customer_id;
```

Kết quả gồm năm khách hàng **có lịch sử** với các `history_id`: **1003, 1005, 1007, 1010, 1011**.

**Vì sao lọc ở truy vấn ngoài?** Trong PostgreSQL và nhiều hệ SQL, không thể dùng bí danh `rn` từ hàm cửa sổ trực tiếp trong `WHERE` của chính tầng `SELECT` tính nó. CTE hoặc truy vấn con tạo một tầng để tính `rn`, sau đó tầng ngoài mới lọc `rn = 1`.

### 5.3. Dùng truy vấn con thay cho CTE

```sql
SELECT
    x.customer_id,
    x.history_id,
    x.status_code,
    x.effective_at
FROM (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY h.customer_id
            ORDER BY h.effective_at DESC, h.history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
) AS x
WHERE x.rn = 1
ORDER BY x.customer_id;
```

Kết quả tương đương. Chọn **CTE** khi muốn đặt tên bước và phối hợp nhiều bước; truy vấn con khi logic ngắn hoặc phù hợp cách tổ chức truy vấn.

## 6. Chọn đúng một hàng: cần ORDER BY đủ để phá hòa

Hàm `ROW_NUMBER` **luôn đánh số khác nhau** cho các dòng cùng nhóm, nhưng nếu `ORDER BY` không tạo **thứ tự toàn phần** (có các dòng ngang nhau trên tất cả tiêu chí), việc dòng nào nhận `rn = 1` có thể **không ổn định**.

### 6.1. Thiếu tie-breaker

```sql
-- Nguy cơ không ổn định khi effective_at trùng.
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY effective_at DESC
)
```

Với An, cả dòng 1002 và 1003 có cùng `effective_at`. SQL không được yêu cầu phải chọn một trong hai theo thứ tự xác định, nên `rn = 1` có thể thay đổi tùy kế hoạch thực thi, chỉ mục hoặc cách engine xử lý.

### 6.2. Thêm khóa duy nhất ở cuối

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY effective_at DESC, history_id DESC
)
```

`history_id` là khóa chính nên khi so hết cả hai tiêu chí, hai dòng khác nhau **không thể hòa hoàn toàn**. Việc chọn `rn = 1` vì thế có quy tắc nhất quán.

**Chọn tie-breaker theo nghiệp vụ trước.** Nếu quy tắc yêu cầu nguồn `crm` đáng tin hơn `import` khi đồng thời điểm, hãy xếp nguồn trước `history_id`. Khóa duy nhất nên là **tiêu chí cuối để đảm bảo quyết định tất định**, không thay thế một chính sách ưu tiên chưa được định nghĩa.

### 6.3. Đã có khóa chính thì có phải “mới hơn” không?

Không nhất thiết. Một ID tăng khi **nhập vào hệ thống** có thể khác thứ tự **sự kiện xảy ra**. Dữ liệu nhập trễ có ID lớn nhưng `effective_at` cũ.

Ví dụ yêu cầu “**sự kiện có thời điểm hiệu lực mới nhất**” thì nên xếp theo `effective_at DESC` trước, `history_id DESC` chỉ để phá hòa. Nếu yêu cầu “**bản ghi được nhận vào gần nhất**”, cần cột như `ingested_at` hoặc `received_at` và dùng chính nó.

## 7. Giữ cả thực thể không có bản ghi con

Truy vấn `ranked_history WHERE rn = 1` chỉ trả các khách hàng **có ít nhất một bản ghi lịch sử**. Nhưng báo cáo có thể cần **tất cả khách hàng**, kể cả Dũng.

Nên xếp hạng dữ liệu con trước, rồi `LEFT JOIN` với bảng khách hàng:

```sql
WITH ranked_history AS (
    SELECT
        h.history_id,
        h.customer_id,
        h.status_code,
        h.effective_at,
        ROW_NUMBER() OVER (
            PARTITION BY h.customer_id
            ORDER BY h.effective_at DESC, h.history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    c.customer_id,
    c.customer_name,
    r.history_id,
    r.status_code,
    r.effective_at
FROM lesson247_customers AS c
LEFT JOIN ranked_history AS r
    ON r.customer_id = c.customer_id
   AND r.rn = 1
ORDER BY c.customer_id;
```

Kết quả:

| customer_id | customer_name | history_id | status_code |
|---:|---|---:|---|
| 1 | An | 1003 | PENDING |
| 2 | Bình | 1005 | ACTIVE |
| 3 | Chi | 1007 | PENDING |
| 4 | Dũng | `NULL` | `NULL` |
| 5 | Hà | 1010 | ACTIVE |
| 6 | Lan | 1011 | ACTIVE |

`LEFT JOIN` giữ Dũng với các cột bên phải `NULL`. Điều kiện `r.rn = 1` nằm trong `ON` để **chỉ ghép hàng đại diện** mà vẫn bảo toàn khách hàng không có hàng đại diện.

### 7.1. Cẩn thận với WHERE sau LEFT JOIN

Nếu viết:

```sql
FROM lesson247_customers AS c
LEFT JOIN ranked_history AS r
    ON r.customer_id = c.customer_id
WHERE r.rn = 1
```

thì **Dũng bị loại**: do không có dòng bên phải, `r.rn` là `NULL`; so sánh `NULL = 1` không là TRUE.

Đây là lỗi thường gặp khi lọc bảng phía phải sau `LEFT JOIN`. Nếu yêu cầu giữ đủ khách hàng, lọc `rn` trong `ON` hoặc trong một CTE `chosen_history` trước khi nối.

### 7.2. Một cách khác: tạo CTE chỉ chứa dòng được chọn

```sql
WITH ranked_history AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
),
chosen_history AS (
    SELECT
        history_id,
        customer_id,
        status_code,
        effective_at
    FROM ranked_history
    WHERE rn = 1
)
SELECT
    c.customer_id,
    c.customer_name,
    h.history_id,
    h.status_code
FROM lesson247_customers AS c
LEFT JOIN chosen_history AS h
    ON h.customer_id = c.customer_id
ORDER BY c.customer_id;
```

Cách này tách rõ hai bước: **lựa chọn một dòng trên mỗi khách** rồi **ghép với danh mục đầy đủ**.

## 8. Chính sách chọn đại diện phức tạp: ưu tiên đã xác minh

Giả sử nghiệp vụ không muốn lấy hàng mới nhất một cách máy móc. Quy tắc mới là:

1. Nếu khách có ít nhất một hàng **đã xác minh**, chọn **hàng đã xác minh mới nhất**.
2. Nếu chưa có hàng nào đã xác minh, chọn **hàng mới nhất trong số chưa xác minh**.
3. Khi hòa thời điểm, chọn `history_id` lớn nhất.

Biểu diễn bằng `ORDER BY` đa tiêu chí:

```sql
WITH ranked_history AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY h.customer_id
            ORDER BY
                CASE
                    WHEN h.is_verified = TRUE THEN 0
                    ELSE 1
                END ASC,
                h.effective_at DESC,
                h.history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    customer_id,
    history_id,
    status_code,
    is_verified,
    effective_at
FROM ranked_history
WHERE rn = 1
ORDER BY customer_id;
```

Kết quả:

| customer_id | history_id | status_code | is_verified |
|---:|---:|---|---|
| 1 | **1002** | ACTIVE | TRUE |
| 2 | **1005** | ACTIVE | TRUE |
| 3 | **1007** | PENDING | FALSE |
| 5 | **1010** | ACTIVE | TRUE |
| 6 | **1011** | ACTIVE | TRUE |

Khác biệt đáng chú ý: **An nhận 1002**, không phải 1003. Dòng 1003 có cùng thời điểm và ID lớn hơn, nhưng **chưa xác minh** nên bị xếp sau tất cả các dòng đã xác minh.

**Đổi thứ tự các biểu thức trong `ORDER BY` nghĩa là đổi chính sách.**

- `ORDER BY is_verified DESC, effective_at DESC`: ưu tiên xác minh **trước** tính mới.
- `ORDER BY effective_at DESC, is_verified DESC`: ưu tiên thời điểm **trước**; xác minh chỉ phá hòa thời điểm.
- `ORDER BY effective_at DESC, history_id DESC`: bỏ qua tình trạng xác minh.

Khi kết quả ảnh hưởng đến quyền lợi, giá bán, phân quyền hoặc xử lý khách hàng, thứ tự này cần được quy định và kiểm thử như **logic nghiệp vụ**, không chỉ là chi tiết kỹ thuật.

## 9. Ưu tiên nhiều tiêu chí: nguồn, độ tin cậy, thời gian

Một nguồn dữ liệu có thể đáng tin hơn nguồn khác. Giả sử quy tắc:

1. Ưu tiên bản ghi đã xác minh.
2. Trong cùng trạng thái xác minh, ưu tiên thời điểm hiệu lực mới nhất.
3. Nếu vẫn hòa, ưu tiên nguồn `crm`, rồi `manual`, cuối cùng `import`.
4. Nếu mọi tiêu chí trên hòa, lấy `history_id` lớn nhất.

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY h.customer_id
            ORDER BY
                CASE WHEN h.is_verified THEN 0 ELSE 1 END,
                h.effective_at DESC,
                CASE h.source_name
                    WHEN 'crm' THEN 0
                    WHEN 'manual' THEN 1
                    WHEN 'import' THEN 2
                    ELSE 3
                END,
                h.history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    customer_id,
    history_id,
    status_code,
    source_name
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

Trong dữ liệu mẫu, lựa chọn vẫn là **1002, 1005, 1007, 1010, 1011**. Tuy nhiên, truy vấn đã thể hiện rõ **quy tắc cho trường hợp hòa nguồn** mà dữ liệu thực tế có thể gặp.

### 9.1. Tạo cột điểm ưu tiên trước để dễ đọc

Nếu biểu thức xếp hạng dài, có thể chia thành hai CTE:

```sql
WITH prioritized AS (
    SELECT
        h.*,
        CASE WHEN h.is_verified THEN 0 ELSE 1 END
            AS verification_priority,
        CASE h.source_name
            WHEN 'crm' THEN 0
            WHEN 'manual' THEN 1
            WHEN 'import' THEN 2
            ELSE 3
        END AS source_priority
    FROM lesson247_status_history AS h
),
ranked AS (
    SELECT
        p.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY
                verification_priority,
                effective_at DESC,
                source_priority,
                history_id DESC
        ) AS rn
    FROM prioritized AS p
)
SELECT
    customer_id,
    history_id,
    status_code,
    verification_priority,
    source_priority
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

Tách như vậy cho phép kiểm tra và giải thích các mức ưu tiên riêng biệt. CTE không đảm bảo tự vật hóa hay tăng tốc; giá trị chính ở đây là **khả năng đọc và bảo trì**.

## 10. NULL trong cột sắp xếp: phải định nghĩa “thiếu” đứng đâu

Bảng thực hành dùng `effective_at NOT NULL`. Trong hệ thống khác, thời điểm có thể thiếu.

Giả sử:

```text
customer_id | record_id | updated_at
------------+-----------+-----------
10          | 1         | 2026-11-01
10          | 2         | NULL
```

Muốn “có thời điểm thật thì ưu tiên, thời điểm thiếu để cuối”:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY
        updated_at DESC NULLS LAST,
        record_id DESC
)
```

`NULLS LAST` là cách viết rõ nghĩa trong PostgreSQL và một số DBMS khác.

**Đặc biệt trong PostgreSQL, mặc định của `ORDER BY updated_at DESC` có thể đặt `NULL` trước các giá trị không `NULL`.** Vì vậy không nên bỏ qua chính sách `NULL` khi chọn bản ghi “mới nhất” từ một cột nullable.

### 10.1. Cách biểu đạt ít phụ thuộc cú pháp NULLS LAST

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY
        CASE WHEN updated_at IS NULL THEN 1 ELSE 0 END,
        updated_at DESC,
        record_id DESC
)
```

Biểu thức `CASE` tạo mức ưu tiên:

- `0` cho giá trị thời điểm đã biết.
- `1` cho giá trị thời điểm thiếu.

Những dòng có thời điểm sẽ đứng trước, sau đó mới sắp thời gian giảm dần và phá hòa bằng khóa.

### 10.2. NULL ở khóa nhóm

`PARTITION BY customer_id` thường gom các dòng có `customer_id NULL` vào **cùng một partition**. Nếu nguồn staging cho phép khách chưa định danh, xếp hạng theo `customer_id` có thể vô tình coi tất cả bản ghi không có ID là **cùng một khách hàng**.

Bảng thực hành có khóa ngoại `customer_id NOT NULL` để tránh tình huống đó. Với dữ liệu thiếu khóa, hãy quyết định có **loại, tách nhóm, gán định danh tạm hoặc đưa vào hàng chờ xử lý** thay vì tự chọn một hàng đại diện duy nhất cho toàn bộ bản ghi thiếu ID.

**Đừng thay `NULL` bằng cùng một giá trị giả trong khóa nhóm mà chưa cân nhắc nguy cơ gộp nhầm thực thể.**

## 11. Khi muốn giữ mọi hàng đồng hạng: RANK và DENSE_RANK

`ROW_NUMBER()` gán **số thứ tự khác nhau** cho các dòng trong một nhóm. Nhưng đôi khi nghiệp vụ yêu cầu “nếu nhiều bản ghi cùng thời điểm mới nhất thì **hiển thị tất cả**”.

Khi đó `RANK()` hoặc `DENSE_RANK()` có thể phù hợp hơn.

### 11.1. So sánh trên dữ liệu trùng thời điểm

```sql
SELECT
    customer_id,
    history_id,
    effective_at,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY effective_at DESC
    ) AS row_no,
    RANK() OVER (
        PARTITION BY customer_id
        ORDER BY effective_at DESC
    ) AS rank_no,
    DENSE_RANK() OVER (
        PARTITION BY customer_id
        ORDER BY effective_at DESC
    ) AS dense_rank_no
FROM lesson247_status_history
WHERE customer_id = 1
ORDER BY effective_at DESC, history_id DESC;
```

An có hai dòng ở thời điểm mới nhất (1002, 1003) và một dòng cũ (1001):

| history_id | row_no | rank_no | dense_rank_no |
|---:|---:|---:|---:|
| 1002 hoặc 1003, tùy cách phá hòa không xác định | 1 hoặc 2 | 1 | 1 |
| Dòng còn lại cùng thời điểm | 1 hoặc 2 | 1 | 1 |
| 1001 | 3 | 3 | 2 |

Hai dòng đồng hạng có `rank_no = 1`, `dense_rank_no = 1`. Với `RANK`, hạng kế tiếp nhảy từ 1 lên 3; `DENSE_RANK` tăng từ 1 lên 2.

Nếu thêm `history_id DESC` vào `ORDER BY` của `RANK`/`DENSE_RANK`, các dòng có khóa khác nhau **không còn đồng hạng**. Chỉ thêm tie-breaker khi bạn thật sự muốn **một hàng duy nhất**, không phải khi cần giữ các dòng đồng thời điểm.

### 11.2. Giữ tất cả sự kiện ở thời điểm mới nhất

```sql
WITH ranked AS (
    SELECT
        h.*,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC
        ) AS latest_rank
    FROM lesson247_status_history AS h
)
SELECT
    customer_id,
    history_id,
    status_code,
    effective_at
FROM ranked
WHERE latest_rank = 1
ORDER BY customer_id, history_id;
```

Đối với An, kết quả giữ **1002 và 1003**; đối với Chi giữ **1006 và 1007**; đối với Hà giữ **1009 và 1010**. Truy vấn **không đảm bảo một hàng trên một khách hàng**.

**Chọn đúng kỹ thuật theo yêu cầu:**

- “Đúng một hàng đại diện” → `ROW_NUMBER` với tie-breaker duy nhất.
- “Tất cả hàng cùng giá trị tối đa” → `RANK`, `DENSE_RANK` hoặc JOIN với giá trị `MAX`, chấp nhận nhiều dòng.

## 12. PostgreSQL DISTINCT ON: ngắn gọn cho một hàng mỗi nhóm

PostgreSQL có cú pháp mở rộng:

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    history_id,
    status_code,
    effective_at
FROM lesson247_status_history
ORDER BY
    customer_id,
    effective_at DESC,
    history_id DESC;
```

Kết quả là một dòng trên từng `customer_id`, với các ID **1003, 1005, 1007, 1010, 1011**.

### 12.1. Cách DISTINCT ON chọn dòng

Trong PostgreSQL:

- `DISTINCT ON (customer_id)` giữ **hàng đầu tiên** của mỗi nhóm `customer_id` theo thứ tự của kết quả.
- `ORDER BY customer_id, effective_at DESC, history_id DESC` khiến hàng mong muốn đứng đầu từng nhóm.
- Các biểu thức trong `DISTINCT ON` phải phù hợp với những biểu thức đầu tiên trong `ORDER BY` theo quy tắc cú pháp PostgreSQL.

Nếu bỏ `ORDER BY` phù hợp, không có bảo đảm rằng “hàng đầu tiên” là hàng mới nhất theo nghiệp vụ.

### 12.2. Muốn sắp kết quả cuối theo thời điểm, dùng tầng ngoài

`DISTINCT ON` cần sắp xếp theo `customer_id` ở đầu để xác định đại diện. Nếu báo cáo cuối muốn **đưa khách hàng có trạng thái mới nhất lên trước**, bọc trong CTE:

```sql
WITH chosen AS (
    SELECT DISTINCT ON (customer_id)
        customer_id,
        history_id,
        status_code,
        effective_at
    FROM lesson247_status_history
    ORDER BY
        customer_id,
        effective_at DESC,
        history_id DESC
)
SELECT *
FROM chosen
ORDER BY effective_at DESC, customer_id;
```

Hai `ORDER BY` có **hai vai trò khác nhau**:

1. Bên trong: chọn hàng đại diện.
2. Bên ngoài: hiển thị danh sách đã chọn.

### 12.3. ROW_NUMBER hay DISTINCT ON?

| Tiêu chí | `ROW_NUMBER ... rn=1` | PostgreSQL `DISTINCT ON` |
|---|---|---|
| Mục tiêu | Một hàng theo thứ tự trong mỗi nhóm | Một hàng đầu tiên của mỗi nhóm |
| SQL đa hệ quản trị | Khá rộng trên các DBMS hỗ trợ window function | **Chỉ PostgreSQL** |
| Nhiều tiêu chí ưu tiên | Có | Có |
| Top 2/Top N trong mỗi nhóm | Dễ dùng `rn <= N` | `DISTINCT ON` chỉ chọn một hàng |
| Cần đọc rõ bước đánh số | Có cột `rn` hỗ trợ phân tích | Ngắn gọn hơn |
| Cần giữ mọi hàng đồng hạng | Đổi sang `RANK`/`DENSE_RANK` | Không phù hợp trực tiếp |

Cả hai đều đòi hỏi **thứ tự được định nghĩa đủ rõ** để tránh lựa chọn không ổn định khi có giá trị hòa.

## 13. Phương án LATERAL JOIN: chọn một hàng cho từng khách

PostgreSQL còn có `LATERAL`, cho phép một truy vấn con trong `FROM`/`JOIN` tham chiếu cột từ nguồn đứng trước.

```sql
SELECT
    c.customer_id,
    c.customer_name,
    h.history_id,
    h.status_code,
    h.effective_at
FROM lesson247_customers AS c
LEFT JOIN LATERAL (
    SELECT
        h.history_id,
        h.status_code,
        h.effective_at
    FROM lesson247_status_history AS h
    WHERE h.customer_id = c.customer_id
    ORDER BY
        h.effective_at DESC,
        h.history_id DESC
    LIMIT 1
) AS h
    ON TRUE
ORDER BY c.customer_id;
```

Đây là một mẫu khác để lấy **tối đa một bản ghi con cho mỗi dòng cha**.

- Với mỗi khách `c`, truy vấn con tìm các hàng lịch sử của **chính khách đó**.
- `ORDER BY ... LIMIT 1` chọn dòng ưu tiên nhất.
- `LEFT JOIN LATERAL ... ON TRUE` bảo toàn khách hàng **không có lịch sử**, như Dũng.

Kết quả đúng sáu khách hàng và các ID đại diện theo quy tắc mới nhất: **1003, 1005, 1007, NULL, 1010, 1011**.

### 13.1. Khi nào LATERAL đáng cân nhắc?

Nếu có chỉ mục phù hợp trên `(customer_id, effective_at DESC, history_id DESC)` và danh sách khách hàng cần xử lý nhỏ hoặc đã được lọc, bộ tối ưu hóa có thể có cơ hội tìm nhanh hàng đầu tiên cho mỗi khách.

Nhưng hiệu năng còn phụ thuộc số khách, số dòng lịch sử, thống kê, bộ đệm và kế hoạch thực tế. `LATERAL + LIMIT 1` **không tự động nhanh hơn** `ROW_NUMBER` trên mọi tập dữ liệu.

### 13.2. SQL Server dùng APPLY

SQL Server thường diễn đạt mẫu tương tự bằng `OUTER APPLY`:

```sql
-- T-SQL minh họa; giả định các bảng lesson247_* có sẵn.
SELECT
    c.customer_id,
    c.customer_name,
    h.history_id,
    h.status_code
FROM lesson247_customers AS c
OUTER APPLY (
    SELECT TOP (1)
        sh.history_id,
        sh.status_code
    FROM lesson247_status_history AS sh
    WHERE sh.customer_id = c.customer_id
    ORDER BY
        sh.effective_at DESC,
        sh.history_id DESC
) AS h;
```

`OUTER APPLY` giữ khách hàng không có dòng phù hợp; `CROSS APPLY` chỉ giữ những khách hàng có kết quả truy vấn con. Cú pháp này khác `LATERAL` của PostgreSQL, nhưng mục đích **“top một hàng con theo từng hàng cha”** tương tự.

## 14. Bẫy MAX + JOIN: nhiều hàng cùng giá trị cực đại

Một cách tưởng hợp lý là lấy `MAX(effective_at)` rồi JOIN lại để lấy các cột của dòng tương ứng:

```sql
WITH latest_time AS (
    SELECT
        customer_id,
        MAX(effective_at) AS max_effective_at
    FROM lesson247_status_history
    GROUP BY customer_id
)
SELECT
    h.customer_id,
    h.history_id,
    h.status_code,
    h.effective_at
FROM lesson247_status_history AS h
JOIN latest_time AS t
    ON t.customer_id = h.customer_id
   AND t.max_effective_at = h.effective_at
ORDER BY h.customer_id, h.history_id;
```

Câu này **không sai cú pháp**. Nó trả **mọi dòng có thời điểm mới nhất trong từng nhóm**.

Vì vậy:

- An có **1002 và 1003**.
- Chi có **1006 và 1007**.
- Hà có **1009 và 1010**.

Nếu báo cáo yêu cầu **một dòng duy nhất**, kết quả này **không đạt**.

### 14.1. Không sửa bằng MAX(history_id) tùy tiện

Giả sử bạn viết:

```sql
SELECT
    customer_id,
    MAX(effective_at) AS latest_time,
    MAX(history_id) AS largest_id
FROM lesson247_status_history
GROUP BY customer_id;
```

Hai giá trị `MAX` được tính **độc lập** và về nguyên tắc có thể đến từ **hai dòng khác nhau**. Không có điều kiện nào bảo đảm `largest_id` thuộc dòng có `latest_time`, nhất là trong dữ liệu nhập trễ.

Muốn xếp theo thời điểm trước và ID sau, hãy **xếp hạng toàn bộ dòng theo hai tiêu chí cùng lúc**:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY effective_at DESC, history_id DESC
)
```

Nếu yêu cầu là **giữ mọi dòng cùng thời điểm mới nhất**, mẫu `MAX + JOIN` lại có thể phù hợp. Vấn đề không phải kỹ thuật tốt hay xấu tuyệt đối, mà là **số dòng mong muốn và quy tắc khi hòa**.

## 15. Khử trùng lặp theo khóa ghép hoặc nhiều cấp nhóm

Không phải mọi yêu cầu đều nhóm theo một cột.

### 15.1. Một hàng trên mỗi (khách hàng, trạng thái)

Nếu muốn bản ghi mới nhất **cho từng trạng thái của mỗi khách hàng**, thay `PARTITION BY customer_id` bằng:

```sql
PARTITION BY customer_id, status_code
```

Ví dụ:

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id, status_code
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    customer_id,
    status_code,
    history_id,
    effective_at
FROM ranked
WHERE rn = 1
ORDER BY customer_id, status_code;
```

Đầu ra có **một hàng trên mỗi cặp `(customer_id, status_code)`**, không phải một hàng trên mỗi khách. An có ba trạng thái khác nhau nên có thể xuất hiện ba dòng.

### 15.2. Một hàng trên mỗi khóa nghiệp vụ ghép

Giả sử hóa đơn có mã `invoice_no` được phép lặp qua các cửa hàng. Khóa nghiệp vụ là:

```text
(store_id, invoice_no)
```

Mẫu đúng:

```sql
-- Ví dụ thiết kế; giả định có bảng invoice_imports.
WITH ranked AS (
    SELECT
        i.*,
        ROW_NUMBER() OVER (
            PARTITION BY i.store_id, i.invoice_no
            ORDER BY i.received_at DESC, i.import_id DESC
        ) AS rn
    FROM invoice_imports AS i
)
SELECT *
FROM ranked
WHERE rn = 1;
```

Nếu chỉ `PARTITION BY invoice_no`, bạn có thể gộp hai hóa đơn cùng mã ở hai cửa hàng khác nhau thành một.

**Khóa nhóm phải phản ánh định danh nghiệp vụ thật**, không chỉ là cột ngắn nhất dễ viết.

## 16. Chuẩn hóa khóa trước khi xác định dòng trùng

Trong dữ liệu nhập từ nhiều hệ thống, khóa có thể khác nhau về **chữ hoa, khoảng trắng** hoặc định dạng:

```text
Lan@Example.org
lan@example.org
 lan@example.org 
```

Nếu chính sách của hệ thống xem ba giá trị là cùng một định danh, cần chuẩn hóa trước khi nhóm. Ví dụ dùng CTE độc lập:

```sql
WITH raw_contacts (contact_id, raw_email, updated_at) AS (
    VALUES
        (1, 'Lan@Example.org',
            TIMESTAMPTZ '2026-11-01 09:00:00+07'),
        (2, ' lan@example.org ',
            TIMESTAMPTZ '2026-11-10 09:00:00+07'),
        (3, 'minh@example.org',
            TIMESTAMPTZ '2026-11-09 09:00:00+07'),
        (4, 'MINH@EXAMPLE.ORG',
            TIMESTAMPTZ '2026-11-11 09:00:00+07')
),
normalized AS (
    SELECT
        contact_id,
        raw_email,
        LOWER(BTRIM(raw_email)) AS email_key,
        updated_at
    FROM raw_contacts
),
ranked AS (
    SELECT
        n.*,
        ROW_NUMBER() OVER (
            PARTITION BY email_key
            ORDER BY updated_at DESC, contact_id DESC
        ) AS rn
    FROM normalized AS n
)
SELECT
    email_key,
    contact_id,
    raw_email,
    updated_at
FROM ranked
WHERE rn = 1
ORDER BY email_key;
```

Kết quả có hai dòng:

| email_key | contact_id đại diện |
|---|---:|
| `lan@example.org` | 2 |
| `minh@example.org` | 4 |

`LOWER(BTRIM(raw_email))` chỉ là **một chính sách chuẩn hóa minh họa**. Với email thực tế, cách so sánh chữ hoa/thường, Unicode, tên miền, dấu `+`, alias và đồng nhất định danh có thể phức tạp. Không tự động xóa dấu chấm hoặc phần `+tag` để gộp tài khoản nếu không có quy tắc nghiệp vụ và bảo mật rõ ràng.

### 16.1. Chuỗi rỗng và NULL

Nếu `raw_email` cho phép `NULL` hoặc chuỗi chỉ có khoảng trắng, có thể chuẩn hóa về `NULL`:

```sql
NULLIF(LOWER(BTRIM(raw_email)), '') AS email_key
```

Nhưng `PARTITION BY email_key` sẽ gom mọi dòng có khóa `NULL` vào **cùng một nhóm**. Nếu dữ liệu thiếu email **không thể được coi là một người duy nhất**, không nên chọn một đại diện chung cho tất cả. Có thể tách chúng thành tập cần xử lý thủ công, hoặc dùng định danh khác có độ tin cậy cao hơn.

### 16.2. Chuẩn hóa và bảo tồn dữ liệu gốc

Trong báo cáo, bạn có thể xuất đồng thời:

- `raw_email`: giá trị ban đầu.
- `email_key`: khóa chuẩn hóa dùng để đối chiếu.

Đừng sửa đè trường gốc nếu chưa có kế hoạch xử lý và khả năng khôi phục. Đối với dữ liệu pháp lý hoặc kiểm toán, có thể cần giữ đầy đủ lịch sử các giá trị gốc.

## 17. Chọn một hàng “tại một thời điểm” phải lọc trước khi xếp hạng

Nhiều dữ liệu là **temporal**: một bản ghi chỉ có hiệu lực từ một thời điểm nào đó. Yêu cầu “trạng thái của khách hàng **tính đến đầu ngày 12/11/2026 theo giờ Việt Nam**” khác với “trạng thái mới nhất trên toàn bộ bảng”.

Muốn chọn bản ghi có `effective_at` **trước mốc đánh giá**, lọc trước khi `ROW_NUMBER`:

```sql
WITH eligible_history AS (
    SELECT *
    FROM lesson247_status_history
    WHERE effective_at
          < TIMESTAMPTZ '2026-11-12 00:00:00+07'
),
ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM eligible_history AS h
)
SELECT
    customer_id,
    history_id,
    status_code,
    effective_at
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

Điểm cần nhớ: **lọc tập ứng viên đủ điều kiện trước**, rồi mới chọn đại diện trong tập đó.

Nếu xếp hạng toàn bộ lịch sử trước, lấy `rn = 1`, sau đó mới lọc `effective_at < cutoff`, một khách hàng có bản ghi mới sau cutoff có thể bị loại hoàn toàn dù vẫn có bản ghi cũ hợp lệ. Tức là:

```text
LỌC THEO THỜI ĐIỂM → CHỌN ĐẠI DIỆN
```

không tương đương với:

```text
CHỌN ĐẠI DIỆN TOÀN BỘ → LỌC THEO THỜI ĐIỂM
```

### 17.1. Thời điểm hiệu lực và thời điểm nhập không giống nhau

Một bản ghi có thể mang:

- `effective_at`: thời điểm thay đổi **có hiệu lực**.
- `ingested_at`: thời điểm hệ thống **nhận được**.
- `updated_at`: thời điểm dòng dữ liệu **được sửa**.
- `valid_from` và `valid_to`: khoảng hiệu lực.

“Trạng thái hiện tại theo sự kiện” và “bản ghi nhập gần nhất” có thể dùng các cột khác nhau. Phải chọn **cột sắp xếp phản ánh câu hỏi nghiệp vụ**.

Nếu dữ liệu có cả hai chiều thời gian hiệu lực và ghi nhận (*bitemporal*), việc chọn bản ghi **tại ngày X theo thông tin biết tại thời điểm Y** đòi hỏi lọc cả hai điều kiện thích hợp trước khi xếp hạng; không thể thay bằng `MAX(updated_at)` đơn giản.

## 18. Top N mỗi nhóm: mở rộng từ một đại diện

Khi cần **hai sự kiện mới nhất mỗi khách**, đổi `rn = 1` thành `rn <= 2`:

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    customer_id,
    history_id,
    status_code,
    rn
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
```

Với mỗi khách có đủ lịch sử, đầu ra có **tối đa hai hàng**.

Khi muốn “**hai mốc thời điểm mới nhất và giữ tất cả bản ghi trong từng mốc**”, `ROW_NUMBER() <= 2` không tương đương. Dùng `DENSE_RANK() OVER (PARTITION BY customer_id ORDER BY effective_at DESC) <= 2` sẽ chọn **hai giá trị thời điểm khác nhau cao nhất**, có thể trả hơn hai hàng nếu nhiều bản ghi cùng thời điểm.

Đây là lựa chọn giữa:

- **Số hàng tối đa** trên mỗi nhóm.
- **Số mức xếp hạng** tối đa trên mỗi nhóm.

## 19. Đếm trùng trước khi chọn đại diện

Trước khi lọc bớt dòng, hãy xem nhóm nào có nhiều bản ghi:

```sql
SELECT
    customer_id,
    COUNT(*) AS history_count
FROM lesson247_status_history
GROUP BY customer_id
HAVING COUNT(*) > 1
ORDER BY history_count DESC, customer_id;
```

Kết quả gồm những khách có hơn một bản ghi lịch sử: **An (3), Bình (2), Chi (2), Hà (3)**. Lan có một dòng, Dũng không có lịch sử.

Một truy vấn khác chỉ tìm nhóm có **trùng thời điểm**:

```sql
SELECT
    customer_id,
    effective_at,
    COUNT(*) AS same_time_rows
FROM lesson247_status_history
GROUP BY customer_id, effective_at
HAVING COUNT(*) > 1
ORDER BY customer_id, effective_at;
```

Kết quả phản ánh những cặp cùng thời điểm của **An, Chi và Hà**.

Điều này chỉ chẩn đoán **cùng khóa và thời điểm**, không chứng minh dữ liệu có lỗi. Nếu các dòng có nguồn và trạng thái khác nhau, chúng vẫn có thể là những bản ghi hợp lệ cần giữ để kiểm toán.

### 19.1. Kiểm tra số đại diện dự kiến

Khi chọn một đại diện cho mỗi khách hàng **có lịch sử**, số dòng đầu ra nên bằng:

```sql
SELECT COUNT(DISTINCT customer_id) AS expected_groups
FROM lesson247_status_history;
```

Với bảng mẫu, kết quả là **5**. Truy vấn `ROW_NUMBER ... rn=1` cũng nên trả 5 dòng.

Nếu báo cáo bảo toàn **mọi khách hàng**, số dòng dự kiến là:

```sql
SELECT COUNT(*) AS expected_customers
FROM lesson247_customers;
```

Kết quả là **6**, miễn các JOIN tiếp theo không nhân dòng.

Chỉ so số lượng là chưa đủ để chứng minh quy tắc chọn đúng, nhưng đây là bước kỹ thuật hữu ích để phát hiện việc **chọn nhiều hơn một dòng trên nhóm** hoặc **vô tình loại nhóm**.

## 20. Chọn đại diện trước hay sau JOIN?

Một lỗi thường gặp là `JOIN` bảng có quan hệ một–nhiều rồi chọn hoặc tính tổng mà không xác định **grain**.

Giả sử muốn báo cáo **một dòng trên một khách hàng**, bao gồm trạng thái đại diện và tổng giá trị đơn hàng. Có các nguồn:

- `customers`: một dòng trên khách hàng.
- `status_history`: nhiều dòng trên khách hàng.
- `orders`: nhiều dòng trên khách hàng.

Nếu JOIN trực tiếp hai bảng con, mỗi khách có thể tạo một tích số dòng:

```text
1 khách hàng
   ├── 3 bản ghi trạng thái
   └── 4 đơn hàng
→ JOIN có thể tạo 3 × 4 = 12 dòng cho khách đó.
```

Lúc này `SUM(order_total)` có thể **cộng mỗi đơn nhiều lần**.

### 20.1. Mẫu đúng: chọn đại diện trạng thái và tổng hợp đơn riêng

```sql
-- Ví dụ thiết kế: giả định có orders(order_id, customer_id, order_total).
WITH ranked_status AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY h.customer_id
            ORDER BY h.effective_at DESC, h.history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
),
chosen_status AS (
    SELECT
        customer_id,
        status_code,
        history_id
    FROM ranked_status
    WHERE rn = 1
),
orders_by_customer AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(order_total) AS order_amount
    FROM orders
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.customer_name,
    s.status_code,
    COALESCE(o.order_count, 0) AS order_count,
    COALESCE(o.order_amount, 0) AS order_amount
FROM lesson247_customers AS c
LEFT JOIN chosen_status AS s
    ON s.customer_id = c.customer_id
LEFT JOIN orders_by_customer AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id;
```

**Đây là ví dụ thiết kế**, không chạy trực tiếp chỉ với hai bảng `lesson247_*` vì chưa tạo bảng `orders`.

Mỗi nguồn tham gia JOIN cuối có **tối đa một dòng trên một khách hàng**:

- `chosen_status`: đã chọn một hàng đại diện.
- `orders_by_customer`: đã tổng hợp về một hàng.
- `customers`: khóa chính một hàng.

Nhờ đó báo cáo cuối duy trì **một dòng trên mỗi khách hàng**, không nhân doanh thu.

**Khử trùng lặp ở đúng chỗ không thay thế tổng hợp ở đúng grain.** Nếu một nguồn chứa nhiều sự kiện hợp lệ, chọn một hàng có thể làm mất thông tin cần cho tổng; nguồn đó phải được tổng hợp theo chỉ số nghiệp vụ, không phải xếp hạng bỏ bớt tùy ý.

## 21. Khử trùng lặp trong staging khác với xóa lịch sử

Một truy vấn chỉ chọn đại diện bằng `ROW_NUMBER` là **không phá hủy dữ liệu gốc**. Trái lại, `DELETE` làm thay đổi bảng. Không bao giờ dùng mẫu “xóa mọi dòng có `rn > 1`” lên bảng lịch sử trạng thái `lesson247_status_history` nếu những dòng đó là **sự kiện hợp lệ**.

Để minh họa quy trình làm sạch staging một cách an toàn, tạo **bảng tạm chỉ dùng để luyện tập** trong PostgreSQL:

```sql
CREATE TEMP TABLE lesson247_import_staging (
    src_row_id INTEGER PRIMARY KEY,
    external_key VARCHAR(30) NOT NULL,
    payload VARCHAR(100) NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
);

INSERT INTO lesson247_import_staging (
    src_row_id, external_key, payload, received_at
)
VALUES
    (1, 'A', 'old-A', TIMESTAMPTZ '2026-11-01 09:00:00+07'),
    (2, 'A', 'new-A', TIMESTAMPTZ '2026-11-10 09:00:00+07'),
    (3, 'B', 'old-B', TIMESTAMPTZ '2026-11-09 10:00:00+07'),
    (4, 'B', 'new-B', TIMESTAMPTZ '2026-11-09 10:00:00+07'),
    (5, 'C', 'only-C', TIMESTAMPTZ '2026-11-11 08:00:00+07');
```

Giả định **hợp đồng dữ liệu** của staging quy định:

> Với mỗi `external_key`, chỉ giữ **một ảnh chụp mới nhất**. Nếu cùng `received_at`, giữ `src_row_id` lớn nhất.

Đây là chính sách phù hợp **cho bảng staging mô phỏng này**, không mặc nhiên đúng cho giao dịch, sự kiện tài chính hay lịch sử thay đổi của hệ thống.

### 21.1. Trước tiên chỉ xem các dòng sẽ giữ

```sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY external_key
            ORDER BY received_at DESC, src_row_id DESC
        ) AS rn
    FROM lesson247_import_staging AS s
)
SELECT
    src_row_id,
    external_key,
    payload,
    received_at
FROM ranked
WHERE rn = 1
ORDER BY external_key;
```

Đầu ra giữ các dòng **2 (A)**, **4 (B)** và **5 (C)**.

### 21.2. Xem những dòng bị loại bằng SELECT

```sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY external_key
            ORDER BY received_at DESC, src_row_id DESC
        ) AS rn
    FROM lesson247_import_staging AS s
)
SELECT
    src_row_id,
    external_key,
    payload,
    rn
FROM ranked
WHERE rn > 1
ORDER BY external_key, rn;
```

Các dòng dự kiến bị loại là **1 và 3**. Việc xem trước giúp xác nhận quy tắc với người chịu trách nhiệm dữ liệu.

### 21.3. Thử DELETE trong transaction và ROLLBACK

```sql
BEGIN;

WITH ranked AS (
    SELECT
        src_row_id,
        ROW_NUMBER() OVER (
            PARTITION BY external_key
            ORDER BY received_at DESC, src_row_id DESC
        ) AS rn
    FROM lesson247_import_staging
)
DELETE FROM lesson247_import_staging AS s
USING ranked AS r
WHERE s.src_row_id = r.src_row_id
  AND r.rn > 1
RETURNING
    s.src_row_id,
    s.external_key,
    s.payload;

-- Quan sát tạm thời những dòng còn lại trong transaction.
SELECT *
FROM lesson247_import_staging
ORDER BY external_key;

ROLLBACK;
```

`DELETE ... USING ... RETURNING` ở đây là cú pháp PostgreSQL. Vì có `ROLLBACK`, kết quả xóa trong transaction thực hành không được lưu lâu dài.

Trong môi trường sản xuất, cần thêm quy trình bảo vệ:

- Xác định chuẩn thế nào là **bản ghi nhập trùng**.
- Xem trước toàn bộ tập dòng được giữ và bị loại.
- Lưu lịch sử nguồn hoặc bản sao trước khi xóa nếu chính sách yêu cầu.
- Xét khả năng **nhập thêm dữ liệu đồng thời** và cần khóa giao dịch/mức cô lập thích hợp.
- Có kiểm soát quyền truy cập, giao dịch, giám sát và khả năng khôi phục.

Nếu chỉ cần làm sạch **đầu ra báo cáo**, hãy ưu tiên **`SELECT` chọn đại diện**, không sửa dữ liệu gốc.

## 22. Ngăn phát sinh trùng từ đầu: khóa UNIQUE và UPSERT

Nếu nghiệp vụ quy định một khóa chỉ có đúng một bản ghi **hiện hành**, bạn nên thể hiện ràng buộc đó ở schema.

Ví dụ bảng trạng thái hiện hành, khác với bảng lịch sử:

```sql
CREATE TABLE lesson247_customer_current (
    customer_id INTEGER PRIMARY KEY
        REFERENCES lesson247_customers(customer_id),
    history_id INTEGER NOT NULL
        REFERENCES lesson247_status_history(history_id),
    status_code VARCHAR(20) NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL
);
```

Khóa chính `customer_id` bảo đảm **tối đa một dòng hiện hành trên khách hàng** trong bảng này. Có thể cập nhật nó từ một quy trình lựa chọn sự kiện có chính sách rõ ràng.

Tuy nhiên, bảng hiện hành này **chưa có cơ chế tự động xác nhận `history_id` thực sự thuộc `customer_id` tương ứng** chỉ bằng hai khóa ngoại độc lập ở trên. Một thiết kế sản xuất có thể cần khóa ngoại ghép, ràng buộc bổ sung hoặc logic transaction nhất quán để đảm bảo quan hệ.

### 22.1. UPSERT không tự giải quyết xung đột về thời gian

PostgreSQL cho phép:

```sql
INSERT INTO lesson247_customer_current (
    customer_id,
    history_id,
    status_code,
    effective_at
)
VALUES (
    1,
    1003,
    'PENDING',
    TIMESTAMPTZ '2026-11-09 10:00:00+07'
)
ON CONFLICT (customer_id)
DO UPDATE SET
    history_id = EXCLUDED.history_id,
    status_code = EXCLUDED.status_code,
    effective_at = EXCLUDED.effective_at;
```

Câu này minh họa `ON CONFLICT` nhưng **không an toàn nếu sự kiện được xử lý ngoài thứ tự thời gian**: một sự kiện cũ đến trễ có thể ghi đè trạng thái hiện hành mới hơn.

Nếu chính sách là “chỉ cập nhật khi sự kiện mới có `effective_at` lớn hơn, hoặc cùng thời điểm với `history_id` lớn hơn”, cần điều kiện cập nhật thích hợp, ví dụ:

```sql
-- Mẫu thiết kế minh họa: sử dụng trong transaction phù hợp.
INSERT INTO lesson247_customer_current AS cur (
    customer_id,
    history_id,
    status_code,
    effective_at
)
VALUES (
    1,
    1003,
    'PENDING',
    TIMESTAMPTZ '2026-11-09 10:00:00+07'
)
ON CONFLICT (customer_id)
DO UPDATE SET
    history_id = EXCLUDED.history_id,
    status_code = EXCLUDED.status_code,
    effective_at = EXCLUDED.effective_at
WHERE
    EXCLUDED.effective_at > cur.effective_at
    OR (
        EXCLUDED.effective_at = cur.effective_at
        AND EXCLUDED.history_id > cur.history_id
    );
```

Cách làm phụ thuộc chính sách lựa chọn; nếu ưu tiên **xác minh** trước thời gian, ví dụ trên chưa phản ánh quy tắc đó. Trạng thái hiện hành thường nên được cập nhật bằng **cùng chính sách ưu tiên** với báo cáo, và cần đảm bảo thao tác nhiều bảng nhất quán.

## 23. Hiệu năng: tránh sắp xếp quá nhiều dòng khi chỉ cần một đại diện

### 23.1. Chỉ mục thường hữu ích

Với truy vấn chọn mới nhất theo khách hàng:

```sql
ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY effective_at DESC, history_id DESC
)
```

Một chỉ mục PostgreSQL đáng cân nhắc:

```sql
CREATE INDEX lesson247_history_latest_idx
    ON lesson247_status_history (
        customer_id,
        effective_at DESC,
        history_id DESC
    );
```

Chỉ mục này sắp xếp theo **khóa nhóm** trước rồi **tiêu chí lựa chọn**. Nó có thể hỗ trợ truy vấn phân nhóm, `DISTINCT ON` hoặc tìm hàng mới nhất của một khách qua `LATERAL`.

Không phải DBMS luôn đọc chính chỉ mục này: quyết định còn phụ thuộc kích thước bảng, số nhóm, bộ nhớ, thứ tự vật lý và thống kê. Với bảng 11 dòng trong bài, **quét bảng** có thể tốt hơn dùng chỉ mục.

### 23.2. Lọc sớm khi yêu cầu cụ thể

Nếu chỉ cần khách hàng `customer_id = 1`, đặt điều kiện lọc ở nguồn trước khi xếp hạng:

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
    WHERE h.customer_id = 1
)
SELECT *
FROM ranked
WHERE rn = 1;
```

Đối với một số bộ dữ liệu và chỉ mục, DBMS có thể chỉ cần xử lý phần lịch sử của khách hàng đó thay vì mọi khách hàng.

### 23.3. ROW_NUMBER, DISTINCT ON và LATERAL không có một người thắng tuyệt đối

| Trường hợp | Lựa chọn đáng cân nhắc |
|---|---|
| Cần portable SQL với window functions | `ROW_NUMBER` + CTE |
| PostgreSQL, mỗi nhóm một dòng, cú pháp gọn | `DISTINCT ON` |
| Một tập cha nhỏ, cần tìm hàng con đầu tiên theo chỉ mục | `LEFT JOIN LATERAL ... LIMIT 1` |
| Cần giữ mọi hàng đồng hạng | `RANK` hoặc `MAX` + JOIN |
| Cần top N hàng mỗi nhóm | `ROW_NUMBER <= N` |
| Chỉ cần giá trị cực đại, không cần nguyên hàng | `GROUP BY ... MAX(...)` |

Khi cần so sánh hiệu năng, dùng `EXPLAIN` trên truy vấn thật:

```sql
EXPLAIN
WITH ranked AS (
    SELECT
        h.history_id,
        h.customer_id,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    customer_id,
    history_id
FROM ranked
WHERE rn = 1;
```

PostgreSQL có thể dùng các nút xử lý cửa sổ, sắp xếp hoặc quét chỉ mục. `EXPLAIN ANALYZE` còn **chạy câu truy vấn** để đo thời gian; chỉ sử dụng trong môi trường phù hợp.

## 24. Khác biệt giữa các hệ quản trị SQL

### 24.1. ROW_NUMBER là mẫu tương đối dễ chuyển hệ

`ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` được hỗ trợ trong nhiều DBMS hiện đại, gồm PostgreSQL, SQL Server, Oracle Database, MySQL 8.0+ và SQLite có window functions.

Phần khác nhau thường nằm ở:

- Cách ghi mốc thời gian và kiểu `TIMESTAMP`.
- Cách sắp `NULL`.
- Cú pháp `LIMIT`, `TOP`, `FETCH FIRST`.
- Khả năng lọc trực tiếp bằng `QUALIFY`.
- Chỉ mục, cách thực thi và quy tắc optimizer.

### 24.2. PostgreSQL có DISTINCT ON

`DISTINCT ON (group_key)` là **mở rộng PostgreSQL**, không phải cú pháp chung để chép nguyên sang MySQL, SQL Server hoặc SQLite.

Khi cần SQL dễ chuyển đổi, dùng `ROW_NUMBER` trong CTE/truy vấn con.

### 24.3. SQL Server có TOP và APPLY

T-SQL thường dùng `TOP (1)` cùng `ORDER BY` để lấy một dòng trong truy vấn con, hoặc `OUTER APPLY` để lấy một hàng con cho mỗi hàng cha. Để chọn trên toàn bảng theo nhóm, `ROW_NUMBER()` vẫn rất phổ biến.

### 24.4. Một số DBMS hỗ trợ QUALIFY

Ở một số hệ thống như BigQuery, Snowflake và DuckDB, `QUALIFY` cho phép lọc trực tiếp kết quả window function:

```sql
-- Ví dụ cho DBMS có hỗ trợ QUALIFY;
-- không phải cú pháp PostgreSQL thông dụng.
SELECT
    customer_id,
    history_id,
    status_code
FROM status_history
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY customer_id
    ORDER BY effective_at DESC, history_id DESC
) = 1;
```

`QUALIFY` giúp bỏ một tầng CTE chỉ để lọc `rn`, nhưng khả năng hỗ trợ thay đổi theo DBMS/phiên bản. Không coi nó là cú pháp chung của tất cả SQL.

### 24.5. MySQL 8.0+, Oracle và SQLite

Trên những phiên bản có window functions, dạng sau là hướng tương thích thường dùng:

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM status_history AS h
)
SELECT *
FROM ranked
WHERE rn = 1;
```

Khi đổi sang hệ khác, cần thay tên bảng, cột và kiểu dữ liệu thực tế. Đối với Oracle, MySQL hoặc SQL Server, cách tạo/hiển thị `TIMESTAMPTZ` và giá trị boolean của PostgreSQL trong phần dữ liệu mẫu **không thể sao chép nguyên vẹn**.

## 25. Những lỗi phổ biến

### Lỗi 1. Chỉ viết DISTINCT rồi hy vọng chọn được hàng mới nhất

```sql
SELECT DISTINCT customer_id, status_code
FROM lesson247_status_history;
```

Một khách vẫn có thể có nhiều trạng thái. `DISTINCT` không có tiêu chí mới nhất. Dùng `ROW_NUMBER` hoặc `DISTINCT ON` với `ORDER BY` đúng quy tắc.

### Lỗi 2. Thiếu PARTITION BY

```sql
ROW_NUMBER() OVER (
    ORDER BY effective_at DESC, history_id DESC
)
```

Nếu không có `PARTITION BY customer_id`, số thứ tự chạy trên **toàn bộ bảng**, nên `rn = 1` chỉ chọn **một dòng của cả bảng**, không phải một dòng mỗi khách.

### Lỗi 3. Thiếu ORDER BY để xác định đại diện

Một số DBMS không cho `ROW_NUMBER()` thiếu thứ tự; ở những nơi chấp nhận cách liên quan, không có ý nghĩa “mới nhất” nếu không sắp theo cột thời gian. Quy tắc chọn phải được thể hiện bằng `ORDER BY` trong cửa sổ.

### Lỗi 4. Không phá hòa khi thời điểm trùng

`ORDER BY effective_at DESC` chưa đủ để chọn ổn định nếu nhiều dòng cùng thời điểm. Thêm mức ưu tiên nghiệp vụ, rồi **khóa duy nhất** làm tiêu chí cuối.

### Lỗi 5. Dùng RANK() rồi tưởng chỉ có một dòng mỗi nhóm

`RANK() = 1` giữ **tất cả các dòng cùng hạng 1**. Nếu yêu cầu một đại diện duy nhất, dùng `ROW_NUMBER() = 1` với thứ tự toàn phần.

### Lỗi 6. Xếp đúng hàng rồi LEFT JOIN lọc ở WHERE làm mất thực thể rỗng

`WHERE r.rn = 1` có thể loại khách không có lịch sử sau `LEFT JOIN`. Đặt `r.rn = 1` vào `ON` hoặc lọc CTE `chosen` trước khi nối.

### Lỗi 7. Dùng MAX(timestamp) rồi JOIN lại nhưng không xử lý ties

JOIN theo thời điểm lớn nhất có thể trả **nhiều dòng** trên một khách. Điều đó chỉ phù hợp nếu muốn giữ **tất cả sự kiện đồng thời điểm**.

### Lỗi 8. Dùng MAX(status) thay cho trạng thái của dòng mới nhất

`MAX(status_code)` chọn giá trị chuỗi lớn nhất theo so sánh, không chọn cột từ dòng có thời điểm lớn nhất. Các phép tổng hợp độc lập còn có thể đến từ những dòng khác nhau.

### Lỗi 9. Gom nhóm theo khóa chưa được chuẩn hóa hoặc khóa quá rộng/quá hẹp

Cùng email có thể khác khoảng trắng/chữ hoa, trong khi cùng mã đơn có thể thuộc hai cửa hàng. Xác định chuẩn hóa và khóa ghép theo hợp đồng dữ liệu, không gộp theo cảm tính.

### Lỗi 10. Dùng DISTINCT để giấu JOIN nhân dòng

Nếu một JOIN một–nhiều làm nhân số tiền, thêm `DISTINCT` vào kết quả cuối không sửa được các phép `SUM` đã cộng lặp. Chọn đại diện hoặc tiền tổng hợp theo đúng grain **trước khi JOIN**.

### Lỗi 11. Xóa lịch sử hợp lệ vì rn > 1

Nếu nhiều dòng là sự kiện lịch sử đúng, chỉ nên **chọn hàng đại diện trong báo cáo**. Xóa vật lý chỉ hợp lý khi có chính sách làm sạch dữ liệu, backup, kiểm soát transaction và chứng cứ các dòng khác thật sự cần loại.

### Lỗi 12. Cho rằng khóa ID lớn nhất đồng nghĩa thời điểm mới nhất

Với nhập lại hoặc đồng bộ không theo thứ tự, ID lớn có thể chứa sự kiện cũ. Sắp theo cột **thời điểm nghiệp vụ**, rồi mới phá hòa bằng khóa.

### Lỗi 13. Lọc sau khi xếp hạng thay vì trước khi xếp hạng

“Trạng thái mới nhất **trước ngày X**” cần lọc `effective_at < X` ở nguồn trước khi tính `ROW_NUMBER`. Nếu chọn mới nhất toàn bộ rồi lọc sau, bạn có thể loại cả khách có trạng thái cũ hợp lệ.

### Lỗi 14. Không biết NULL đứng đầu hay cuối

Khi cột thời điểm nullable, `ORDER BY ... DESC` có thể đặt `NULL` khác nhau giữa DBMS. Chỉ định `NULLS LAST` nơi hỗ trợ hoặc dùng `CASE WHEN ... IS NULL THEN 1 ELSE 0 END`.

## 26. Bài tập thực hành có lời giải

Các bài 1–12 dùng `lesson247_customers` và `lesson247_status_history` của phần 2. Các ví dụ có CTE độc lập tự cung cấp dữ liệu.

### Bài 1. Vì sao DISTINCT không chọn một trạng thái mỗi khách?

```sql
SELECT DISTINCT
    customer_id,
    status_code
FROM lesson247_status_history
ORDER BY customer_id, status_code;
```

**Đáp án:** vì một khách có thể có nhiều `status_code`, ví dụ An có `NEW`, `ACTIVE`, `PENDING`. `DISTINCT` chỉ loại các **cặp `(customer_id,status_code)` giống nhau**, không chọn một dòng “tốt nhất”.

### Bài 2. Chọn một dòng mới nhất của mỗi khách có lịch sử

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    customer_id,
    history_id,
    status_code
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

**Đáp án:** năm ID **1003, 1005, 1007, 1010, 1011** theo khách hàng 1, 2, 3, 5, 6. Khách 4 không có lịch sử nên không xuất hiện.

### Bài 3. Giữ đủ sáu khách hàng

**Yêu cầu:** cho khách Dũng hiện `NULL` ở cột lịch sử.

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    c.customer_id,
    c.customer_name,
    r.history_id
FROM lesson247_customers AS c
LEFT JOIN ranked AS r
    ON r.customer_id = c.customer_id
   AND r.rn = 1
ORDER BY c.customer_id;
```

**Đáp án:** **6 dòng**. Khách Dũng có `history_id NULL`.

### Bài 4. Khách An chọn bản ghi nào nếu ưu tiên xác minh?

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY
                CASE WHEN is_verified THEN 0 ELSE 1 END,
                effective_at DESC,
                history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT
    history_id,
    status_code,
    is_verified
FROM ranked
WHERE customer_id = 1
  AND rn = 1;
```

**Đáp án:** **1002, ACTIVE, TRUE**. Dòng 1003 cùng thời điểm nhưng chưa xác minh, nên không được ưu tiên.

### Bài 5. RANK và ROW_NUMBER khác nhau khi cùng thời điểm thế nào?

```sql
WITH ranked AS (
    SELECT
        history_id,
        customer_id,
        effective_at,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC
        ) AS rnk
    FROM lesson247_status_history
)
SELECT history_id
FROM ranked
WHERE customer_id = 1
  AND rnk = 1
ORDER BY history_id;
```

**Đáp án:** **1002 và 1003**. Hai dòng có cùng `effective_at` cao nhất nên `RANK = 1` cho cả hai. Dùng `ROW_NUMBER` với khóa phá hòa nếu chỉ muốn một dòng.

### Bài 6. Chọn mỗi khách hai hàng mới nhất

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT customer_id, history_id, rn
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
```

**Đáp án:** An `1003,1002`; Bình `1005,1004`; Chi `1007,1006`; Hà `1010,1009`; Lan `1011`. Tổng cộng **9 dòng**.

### Bài 7. Viết lại một hàng mỗi khách bằng DISTINCT ON

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    history_id,
    status_code
FROM lesson247_status_history
ORDER BY
    customer_id,
    effective_at DESC,
    history_id DESC;
```

**Đáp án:** cùng năm ID của bài 2: **1003, 1005, 1007, 1010, 1011**. Lưu ý `DISTINCT ON` là cú pháp PostgreSQL.

### Bài 8. Tìm những khách có trùng thời điểm lịch sử

```sql
SELECT
    customer_id,
    effective_at,
    COUNT(*) AS row_count
FROM lesson247_status_history
GROUP BY customer_id, effective_at
HAVING COUNT(*) > 1
ORDER BY customer_id, effective_at;
```

**Đáp án:** các khách **An, Chi, Hà**, mỗi người có một nhóm thời điểm trùng gồm hai dòng. Đây là kết quả **chẩn đoán đồng thời điểm**, chưa phải kết luận dữ liệu sai.

### Bài 9. Trạng thái mới nhất trước mốc đánh giá

**Yêu cầu:** mỗi khách chỉ xét những sự kiện có `effective_at` **trước 12/11/2026 00:00 +07**, rồi chọn đại diện.

```sql
WITH eligible AS (
    SELECT *
    FROM lesson247_status_history
    WHERE effective_at <
          TIMESTAMPTZ '2026-11-12 00:00:00+07'
),
ranked AS (
    SELECT
        e.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM eligible AS e
)
SELECT customer_id, history_id
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

**Đáp án:** khách 1 → **1003**, khách 2 → **1005**, khách 3 → **1007**, khách 5 → **1008**. Khách 6 có bản ghi ngày 12/11 nên chưa có dòng trước cutoff; Dũng không có lịch sử.

### Bài 10. Phát hiện bẫy MAX + JOIN

```sql
WITH mx AS (
    SELECT
        customer_id,
        MAX(effective_at) AS latest_at
    FROM lesson247_status_history
    GROUP BY customer_id
)
SELECT
    h.customer_id,
    h.history_id
FROM lesson247_status_history AS h
JOIN mx
    ON mx.customer_id = h.customer_id
   AND mx.latest_at = h.effective_at
ORDER BY h.customer_id, h.history_id;
```

**Đáp án:** câu này trả **8 dòng**, không phải 5: An có 2, Bình 1, Chi 2, Hà 2, Lan 1. Nó giữ **mọi dòng cùng thời điểm mới nhất**, không chọn một hàng khi hòa. Muốn một hàng, thêm quy tắc phá hòa bằng `ROW_NUMBER` hoặc `DISTINCT ON`.

### Bài 11. Khóa ghép (store_id, invoice_no)

Giả sử dữ liệu:

```sql
WITH invoices (import_id, store_id, invoice_no, received_at) AS (
    VALUES
        (1, 10, 'A', TIMESTAMPTZ '2026-11-01 10:00:00+07'),
        (2, 10, 'A', TIMESTAMPTZ '2026-11-02 10:00:00+07'),
        (3, 20, 'A', TIMESTAMPTZ '2026-11-03 10:00:00+07'),
        (4, 20, 'B', TIMESTAMPTZ '2026-11-01 10:00:00+07')
),
ranked AS (
    SELECT
        i.*,
        ROW_NUMBER() OVER (
            PARTITION BY store_id, invoice_no
            ORDER BY received_at DESC, import_id DESC
        ) AS rn
    FROM invoices AS i
)
SELECT import_id, store_id, invoice_no
FROM ranked
WHERE rn = 1
ORDER BY store_id, invoice_no;
```

**Đáp án:** giữ `import_id = 2, 3, 4`. Hai hóa đơn mã `A` ở cửa hàng 10 và 20 là **hai nhóm khác nhau**. Không được chỉ phân nhóm theo `invoice_no`.

### Bài 12. Vì sao WHERE rn = 1 sau LEFT JOIN làm mất khách?

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY effective_at DESC, history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT c.customer_id, r.history_id
FROM lesson247_customers AS c
LEFT JOIN ranked AS r
    ON r.customer_id = c.customer_id
WHERE r.rn = 1;
```

**Đáp án:** khách **Dũng** bị loại vì `r.rn` là `NULL` trên dòng không có lịch sử, nên `r.rn = 1` không TRUE. Đưa điều kiện vào `ON` hoặc lọc CTE trước `LEFT JOIN`.

### Bài 13. Dữ liệu import nào bị loại theo quy tắc mới nhất?

Bảng `lesson247_import_staging` ở phần 21 có 5 dòng và quy tắc “một dòng mới nhất cho mỗi `external_key`, phá hòa bằng `src_row_id DESC`”.

```sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY external_key
            ORDER BY received_at DESC, src_row_id DESC
        ) AS rn
    FROM lesson247_import_staging AS s
)
SELECT src_row_id, external_key
FROM ranked
WHERE rn > 1
ORDER BY external_key;
```

**Đáp án:** các dòng `src_row_id = 1` và `3` là bản dư theo **hợp đồng staging đã đặt ra**. Đừng mang quy tắc này đi xóa bản ghi lịch sử `lesson247_status_history`.

### Bài 14. Chọn một đại diện theo nguồn ưu tiên

**Yêu cầu:** với mỗi khách hàng, chọn **nguồn `crm` nếu có**, ưu tiên bản ghi `crm` mới nhất; nếu không có `crm` thì chọn từ các nguồn khác theo thời điểm mới nhất. Khi hòa dùng `history_id` giảm dần.

```sql
WITH ranked AS (
    SELECT
        h.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY
                CASE
                    WHEN source_name = 'crm' THEN 0
                    ELSE 1
                END,
                effective_at DESC,
                history_id DESC
        ) AS rn
    FROM lesson247_status_history AS h
)
SELECT customer_id, history_id, source_name
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

**Đáp án:** An → **1002 crm**; Bình → **1005 crm**; Chi → **1007 import**; Hà → **1010 crm**; Lan → **1011 manual**. Khác bài 2 ở An vì **nguồn ưu tiên đứng trước thời gian và ID**.

### Bài 15. Chọn công cụ theo yêu cầu

Xét năm nhiệm vụ:

1. Lấy danh sách mã trạng thái khác nhau.
2. Lấy đúng một trạng thái mới nhất trên mỗi khách hàng, phải hỗ trợ nhiều DBMS.
3. Lấy đúng một trạng thái mới nhất trên mỗi khách hàng trong PostgreSQL bằng SQL ngắn.
4. Giữ tất cả sự kiện cùng thời điểm mới nhất trên mỗi khách.
5. Lấy hai bản ghi mới nhất mỗi khách, tối đa hai dòng mỗi khách.

**Gợi ý đáp án:**

1. `SELECT DISTINCT status_code`.
2. `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY effective_at DESC, history_id DESC)`, lọc `rn=1`.
3. PostgreSQL `DISTINCT ON (customer_id) ... ORDER BY customer_id, effective_at DESC, history_id DESC`.
4. `RANK()`/`DENSE_RANK()` theo `effective_at DESC`, lọc hạng 1, hoặc JOIN với `MAX(effective_at)` và chấp nhận ties.
5. `ROW_NUMBER` và lọc `rn <= 2`.

## 27. Bảng ghi nhớ

| Bạn muốn làm gì? | Kỹ thuật phù hợp | Điểm cần nhớ |
|---|---|---|
| Lấy tổ hợp giá trị không trùng | `SELECT DISTINCT col1, col2` | So toàn bộ cột đang chọn, không chọn hàng “tốt nhất” |
| Đếm số thực thể duy nhất | `COUNT(DISTINCT entity_id)` | Chọn đúng khóa thực thể |
| Tính số dòng/tổng/min/max theo nhóm | `GROUP BY` | Không tự chọn một dòng nguyên vẹn |
| Chọn đúng một hàng đại diện mỗi nhóm | `ROW_NUMBER() OVER (PARTITION BY ... ORDER BY ...)` và `rn=1` | Cần thứ tự ưu tiên đầy đủ |
| Chọn một hàng đại diện gọn trong PostgreSQL | `DISTINCT ON` | `ORDER BY` quyết định hàng đầu tiên |
| Giữ tất cả dòng đồng hạng cao nhất | `RANK() = 1` hoặc `DENSE_RANK() = 1` | Có thể nhiều dòng trên nhóm |
| Lấy N hàng mỗi nhóm | `ROW_NUMBER <= N` | Tối đa N dòng, kể cả có hòa |
| Chọn một hàng con cho từng dòng cha | `LEFT JOIN LATERAL ... ORDER BY ... LIMIT 1` | Giữ được cha không có con |
| Lọc lịch sử tại thời điểm X | Lọc `effective_at < cutoff` **trước** xếp hạng | Thứ tự lọc và chọn đại diện quan trọng |
| Chọn theo nhiều mức ưu tiên | `ORDER BY CASE ..., timestamp DESC, id DESC` | Thứ tự biểu thức là chính sách nghiệp vụ |
| Giữ cả thực thể không có dữ liệu con | `LEFT JOIN` với CTE đã chọn và điều kiện `rn=1` trong `ON` | Tránh lọc mất dòng `NULL` ở `WHERE` |
| Khóa ghép | `PARTITION BY key1, key2` | Không gộp các thực thể khác nhau |
| Khóa chuẩn hóa | Tạo `normalized_key` rồi xếp hạng | Có quy tắc với `NULL` và giá trị thiếu |
| Muốn JOIN nhiều bảng con | Chọn đại diện/tổng hợp mỗi nguồn về grain đúng trước | Tránh nhân dòng và cộng lặp |
| Xử lý staging trùng thật | Xem `rn > 1`, giao dịch/backup, rồi mới cân nhắc xóa | Không xóa lịch sử hợp lệ |
| Đảm bảo một hàng hiện hành trong schema | `PRIMARY KEY`/`UNIQUE` theo khóa nghiệp vụ | Kèm quy tắc cập nhật nhất quán |

## 28. Kết luận

**Khử trùng lặp có quy tắc không đồng nghĩa với thêm `DISTINCT`.** Trước hết bạn phải biết **đang coi những dòng nào là cùng nhóm**, sau đó xác định **thứ tự lựa chọn** và **cách phá hòa**. Chỉ khi đó “một hàng đại diện” mới có ý nghĩa ổn định và giải thích được.

Mẫu nên nhớ:

```sql
WITH ranked AS (
    SELECT
        t.*,
        ROW_NUMBER() OVER (
            PARTITION BY business_key
            ORDER BY
                preferred_condition DESC,
                event_time DESC,
                unique_row_id DESC
        ) AS rn
    FROM source_table AS t
)
SELECT *
FROM ranked
WHERE rn = 1;
```

Đây là **mẫu minh họa** với các tên cột giả định: thay `business_key`, `preferred_condition`, `event_time` và `unique_row_id` bằng đúng cột của mô hình dữ liệu. Nếu `preferred_condition` không phải một cột số/boolean có quy tắc sắp xếp rõ, dùng `CASE` để chuyển thành mức ưu tiên cụ thể.

Khi áp dụng vào báo cáo hoặc làm sạch dữ liệu, luôn phân biệt **chọn một dòng trong kết quả truy vấn** với **xóa những dòng khác khỏi bảng gốc**. Một dòng lịch sử không được chọn làm đại diện vẫn có thể là một sự kiện hợp lệ, cần giữ để kiểm toán hoặc tính toán sau này.

## Tài liệu tham khảo

- [PostgreSQL — Window Functions](https://www.postgresql.org/docs/current/functions-window.html): `ROW_NUMBER`, `RANK`, `DENSE_RANK` và hành vi đánh số/xếp hạng.
- [PostgreSQL — SELECT](https://www.postgresql.org/docs/current/sql-select.html): `DISTINCT`, `DISTINCT ON`, `ORDER BY` và CTE.
- [PostgreSQL — LATERAL Subqueries](https://www.postgresql.org/docs/current/queries-table-expressions.html): truy vấn con tham chiếu nguồn đứng trước.
- [Microsoft Learn — ROW_NUMBER (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/functions/row-number-transact-sql): đánh số trong phân vùng và tính ổn định khi thứ tự có hòa.
- [MySQL Reference Manual — Window Function Descriptions](https://dev.mysql.com/doc/refman/8.4/en/window-function-descriptions.html): `ROW_NUMBER` và các hàm cửa sổ liên quan.
- [SQLite — Window Functions](https://www.sqlite.org/windowfunctions.html): hàm xếp hạng và cú pháp cửa sổ.

