# Tối ưu truy vấn tham số hóa khi dữ liệu phân bố lệch trong PostgreSQL

## 1. Một câu SQL, hai giá trị tham số, hai nhu cầu thực thi rất khác nhau

Giả sử ứng dụng SaaS phục vụ nhiều khách hàng (*tenant*) bằng một bảng đơn hàng chung:

```sql
SELECT order_id, tenant_id, status, amount, payload
FROM orders
WHERE tenant_id = $1;
```

Lệnh SQL không đổi; ứng dụng chỉ thay tham số `$1`.

- Với `$1 = 1`, tenant lớn nhất có **225.000 đơn hàng**, chiếm khoảng **90%** bảng.
- Với `$1 = 999`, một tenant nhỏ chỉ có khoảng **25 đơn hàng**, chiếm khoảng **0,01%** bảng.

Nếu query phải lấy phần lớn bảng cho tenant 1, **sequential scan** có thể tiết kiệm hơn hàng trăm nghìn lượt đọc heap thông qua index. Nhưng với tenant 999, **index scan** có thể tốt hơn rất nhiều so với quét 250.000 hàng.

Điều gì xảy ra khi ứng dụng dùng **prepared statement** hoặc JDBC parameter binding? PostgreSQL có thể lựa chọn giữa:

- **Custom plan**: lập kế hoạch có xét **giá trị tham số của lần thực thi**.
- **Generic plan**: một kế hoạch có thể dùng lại cho **nhiều giá trị tham số**, không được tối ưu riêng cho giá trị cụ thể ở lần thực thi đó.

Khi dữ liệu phân bố rất lệch (*skewed distribution*), generic plan có thể hợp lý cho tenant nhỏ nhưng bất lợi với tenant lớn, hoặc ngược lại.

```text
                    Cùng câu SQL có $1
                             |
                  +----------+----------+
                  |                     |
             $1 = 1 (HOT)          $1 = 999 (COLD)
             ~90% bảng             ~0,01% bảng
                  |                     |
            Seq Scan có thể       Index Scan có thể
            hợp lý               hợp lý
                  |                     |
                  +----------+----------+
                             |
                  Generic plan dùng chung
                     có thể khó tối ưu
                        cho cả hai
```

**Chủ đề của bài:** cách nhận diện, đo lường và tối ưu truy vấn tham số hóa trong PostgreSQL **khi giá trị tham số có mức độ phổ biến rất khác nhau**.

> **Thông điệp quan trọng:** “SQL đã có index” và “SQL đã dùng bind parameter” đều không bảo đảm hiệu năng ổn định. Phải hiểu **giá trị tham số, thống kê phân bố, custom/generic plan và cách ứng dụng thực thi prepared statements**.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao **data skew** khiến các lần thực thi cùng một SQL có thể cần access path khác nhau.
2. Phân biệt **parameter binding**, **server-side prepared statement**, **custom plan** và **generic plan**.
3. Hiểu PostgreSQL cân nhắc dùng generic hay custom plan với `plan_cache_mode = auto`.
4. Dùng `PREPARE` / `EXECUTE` và `EXPLAIN (ANALYZE, BUFFERS) EXECUTE` để tái hiện vấn đề.
5. Dùng `plan_cache_mode = force_custom_plan` và `force_generic_plan` để so sánh có kiểm soát.
6. Quan sát các bộ đếm `generic_plans` / `custom_plans` trong `pg_prepared_statements` khi phiên bản hỗ trợ.
7. Đọc thống kê `pg_stats`: most common values, tần suất, histogram, `n_distinct` và correlation.
8. Cải thiện ước lượng bằng `ANALYZE`, statistics target và extended statistics trong những trường hợp phù hợp.
9. Phân tích vai trò của index thường, composite index, partial index và covering index đối với truy vấn tham số hóa.
10. Hiểu vì sao generic plan có thể **không dùng được partial index** khi predicate phụ thuộc một tham số chưa biết.
11. Xử lý các kiểu điều kiện tùy chọn: `OR $1 IS NULL`, `IN`, `ANY`, khoảng thời gian và `LIMIT`.
12. Thiết kế và đo kiểm ứng dụng Java/JDBC mà không hy sinh parameter binding và an toàn SQL.
13. Nhận biết giới hạn của partition pruning, `pg_stat_statements` và các cách ép kế hoạch.
14. Chọn giải pháp thực tế dựa trên đo lường thay vì áp dụng một mẹo cho toàn database.

## 3. Bốn khái niệm dễ nhầm: SQL parameter, PREPARE, custom plan, generic plan

### 3.1. Truy vấn tham số hóa

Truy vấn có **placeholder**:

```sql
SELECT *
FROM app.orders
WHERE tenant_id = $1;
```

`$1` biểu thị một giá trị được truyền riêng khỏi câu SQL. Khi viết trong ứng dụng Java, thường dùng placeholder dấu hỏi `?` của JDBC:

```java
PreparedStatement ps = connection.prepareStatement(
    "SELECT order_id, amount FROM app.orders WHERE tenant_id = ?"
);
ps.setInt(1, tenantId);
```

Driver PostgreSQL sẽ gửi truy vấn và giá trị theo giao thức thích hợp. Đây là cách tốt để:

- Tách dữ liệu khỏi cú pháp SQL.
- Giảm rủi ro SQL injection so với ghép chuỗi dữ liệu người dùng.
- Truyền kiểu dữ liệu rõ hơn.
- Cho phép reuse một dạng câu SQL.
- Tận dụng cơ chế prepared execution trong những điều kiện phù hợp.

**Parameterization không đồng nghĩa chắc chắn chỉ có một kế hoạch đã cache.** Cách driver và server thực thi quyết định có dùng prepared statement trên server và có generic/custom plan hay không.

### 3.2. SQL-level `PREPARE` của PostgreSQL

```sql
PREPARE find_orders(integer) AS
SELECT order_id, amount
FROM app.orders
WHERE tenant_id = $1;
```

Sau đó:

```sql
EXECUTE find_orders(1);
EXECUTE find_orders(999);
DEALLOCATE find_orders;
```

`PREPARE` khai báo một prepared statement **trong session PostgreSQL hiện tại**. Nó không tạo một query toàn cục dùng chung xuyên mọi session/database.

### 3.3. Custom plan

Một **custom plan** được lập cho một lần thực thi với giá trị tham số cụ thể.

Ví dụ:

```text
EXECUTE find_orders(1)
  -> planner biết tenant_id=1 khi chọn access path
  -> có thể ước lượng ~225.000 hàng

EXECUTE find_orders(999)
  -> planner biết tenant_id=999
  -> có thể ước lượng ~25 hàng
```

Custom plan có thể tận dụng sự chênh lệch phân bố của tham số, nhưng phải trả chi phí lập kế hoạch cho từng lần thực thi theo cơ chế tương ứng.

### 3.4. Generic plan

Một **generic plan** không được chọn dựa trên giá trị cụ thể của từng lần `EXECUTE`.

```text
PREPARE find_orders(integer)

Generic plan:
  WHERE tenant_id = $1
  dựa trên ước lượng chung cho tham số

EXECUTE find_orders(1)   -> dùng cùng dạng kế hoạch
EXECUTE find_orders(999) -> dùng cùng dạng kế hoạch
```

Generic plan có thể giảm planning overhead khi SQL được gọi rất nhiều lần, nhưng nếu thông số phân bố lệch mạnh thì **một access path khó tối ưu đồng thời cho mọi giá trị**.

### 3.5. Generic plan không có nghĩa PostgreSQL bỏ qua mọi tham số

Tham số vẫn được truyền và so sánh đúng khi thực thi. Generic plan không hề biến:

```sql
WHERE tenant_id = $1
```

thành bỏ WHERE.

Điểm khác nhau là **lựa chọn shape của kế hoạch ở planning time**, không phải việc thực thi SQL có áp dụng điều kiện hay không.

## 4. Phân bố lệch (*skew*) là gì?

Một cột được gọi là có phân bố lệch khi tần suất các giá trị **khác nhau lớn**.

Ví dụ:

| tenant_id | Số đơn hàng | Tỷ lệ bảng |
| ---: | ---: | ---: |
| 1 | 225.000 | 90% |
| 2 | Khoảng 25 | Khoảng 0,01% |
| 3 | Khoảng 25 | Khoảng 0,01% |
| 999 | Khoảng 25 | Khoảng 0,01% |
| Các tenant còn lại | Khoảng 25 mỗi tenant | Phần còn lại |

Nếu chỉ biết “có 1001 tenant” và ngầm ước lượng mỗi tenant có khoảng 250 đơn thì sẽ sai rất lớn:

- Tenant 1: thực tế 225.000, gấp khoảng **900 lần** số trung bình 250.
- Tenant nhỏ: thực tế khoảng 25, ít hơn số trung bình 250 khoảng **10 lần**.

Độ lệch này ảnh hưởng:

- `WHERE tenant_id = ?`.
- Joins giữa bảng tenant và orders.
- `ORDER BY ... LIMIT` theo tenant.
- Các truy vấn `COUNT`/`SUM`.
- Batch cập nhật theo tenant.
- Index scan so với bitmap/seq scan.
- Mức độ sử dụng cache và CPU.
- Tài nguyên trả về qua mạng cho ứng dụng.

### 4.1. Tần suất khác nhau không phải sai dữ liệu

Skew thường là hệ quả nghiệp vụ tự nhiên:

- Một người bán có hàng triệu sản phẩm, phần lớn người bán có vài chục.
- Một trạng thái `ACTIVE` chiếm 99%, `FAILED` chiếm 1%.
- Một khu vực có phần lớn đơn hàng.
- Một tenant doanh nghiệp có lượng sự kiện gấp nhiều lần tenant cá nhân.
- Một ngày gần đây có lượng log cao hơn những ngày lịch sử.

Vì vậy, giải pháp không phải “làm dữ liệu đều hơn” bằng một thao tác tùy tiện, mà là **thiết kế access path, thống kê và cách lập kế hoạch phù hợp với phân bố thực tế**.

### 4.2. Skew có thể thay đổi theo thời gian

Tenant đang nhỏ có thể tăng đột biến. Một chiến dịch bán hàng có thể khiến `status = 'PENDING'` tăng từ 2% lên 70%.

Phải xem statistics và performance theo từng giai đoạn; kết luận dựa trên phân bố cũ có thể không còn đúng.

## 5. Dựng bộ dữ liệu thực hành 250.000 hàng

Toàn bộ ví dụ SQL dùng schema `skew_lab` trong **database thực hành**. Không chạy lệnh tạo/nạp dữ liệu trên production.

### 5.1. Tạo schema và bảng

```sql
CREATE SCHEMA IF NOT EXISTS skew_lab;

CREATE TABLE skew_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id integer NOT NULL,
    status text NOT NULL
        CHECK (status IN ('DONE', 'PENDING', 'FAILED')),
    created_at timestamptz NOT NULL,
    amount numeric(12,2) NOT NULL,
    payload text NOT NULL
);
```

Lựa chọn:

- `tenant_id` thể hiện tenant.
- `status` có phân bố **liên quan** tới tenant, giúp nghiên cứu statistics nhiều cột.
- `created_at` dùng trong bài toán lấy đơn gần nhất.
- `payload` làm tăng chi phí đọc heap khi query trả nhiều cột.
- `order_id` tự có B-tree PRIMARY KEY index.

### 5.2. Sinh dữ liệu lệch mạnh

```sql
INSERT INTO skew_lab.orders
    (tenant_id, status, created_at, amount, payload)
SELECT
    CASE
        WHEN g <= 225000 THEN 1
        ELSE 2 + ((g - 225001) % 1000)
    END AS tenant_id,
    CASE
        WHEN g <= 225000 THEN
            CASE
                WHEN g % 100 = 0 THEN 'FAILED'
                WHEN g % 50  = 0 THEN 'PENDING'
                ELSE 'DONE'
            END
        ELSE
            CASE
                WHEN g % 7 = 0 THEN 'FAILED'
                WHEN g % 3 = 0 THEN 'DONE'
                ELSE 'PENDING'
            END
    END AS status,
    timestamptz '2025-01-01 00:00:00+00'
        + g * interval '1 minute' AS created_at,
    ((g * 17) % 100000)::numeric / 100 AS amount,
    repeat('order-payload-', 8) || lpad(g::text, 7, '0')
FROM generate_series(1, 250000) AS s(g);
```

Tổng dữ liệu:

- 225.000 hàng đầu thuộc tenant 1.
- 25.000 hàng còn lại phân đều cho 1.000 tenant từ `2` tới `1001`, mỗi tenant **đúng 25 hàng**.
- Trong tenant 1, `DONE` rất phổ biến.
- Ở các tenant nhỏ, `PENDING` tương đối phổ biến hơn.

Ví dụ này cố ý làm phân bố rất khác nhau để người học dễ quan sát ảnh hưởng đến planner.

### 5.3. Cập nhật thống kê

```sql
ANALYZE skew_lab.orders;
```

Nếu không có thống kê đủ mới, so sánh custom/generic plan có thể nhiễu vì planner ước lượng chưa đúng tình trạng bảng.

### 5.4. Kiểm tra phân bố

```sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE tenant_id = 1) AS hot_orders,
    COUNT(*) FILTER (WHERE tenant_id = 999) AS cold_orders,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE tenant_id = 1)
        / NULLIF(COUNT(*), 0),
        2
    ) AS hot_percent
FROM skew_lab.orders;
```

Kết quả dự kiến:

| all_orders | hot_orders | cold_orders | hot_percent |
| ---: | ---: | ---: | ---: |
| 250000 | 225000 | 25 | 90.00 |

Phân bố status:

```sql
SELECT
    tenant_id,
    status,
    COUNT(*) AS order_count
FROM skew_lab.orders
WHERE tenant_id IN (1, 2, 999)
GROUP BY tenant_id, status
ORDER BY tenant_id, status;
```

Đây là tập dữ liệu dùng để lý giải **skew theo một cột** và **tương quan nhiều cột**.

### 5.5. Tạo index cho tenant_id

```sql
CREATE INDEX orders_tenant_idx
ON skew_lab.orders (tenant_id);

ANALYZE skew_lab.orders;
```

Chỉ mục này là điểm xuất phát để planner cân nhắc giữa:

- `Seq Scan`.
- `Index Scan`.
- `Bitmap Index Scan + Bitmap Heap Scan`.

## 6. Thử với hai literal trước khi xét parameter

Cùng dạng truy vấn, nhưng ở bước này ghi giá trị **trực tiếp trong SQL lab** để planner có cơ hội ước lượng theo giá trị cụ thể.

### 6.1. Tenant nóng

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, tenant_id, status, amount, payload
FROM skew_lab.orders
WHERE tenant_id = 1;
```

Vì khoảng 90% bảng phù hợp, một kế hoạch minh họa có thể là:

```text
Seq Scan on orders
  Filter: (tenant_id = 1)
  Rows Removed by Filter: ...
  Buffers: shared hit=... read=...
```

Đọc lần lượt phần lớn heap có thể rẻ hơn hàng trăm nghìn index lookups kèm heap fetch.

### 6.2. Tenant lạnh

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, tenant_id, status, amount, payload
FROM skew_lab.orders
WHERE tenant_id = 999;
```

Một kế hoạch minh họa:

```text
Index Scan using orders_tenant_idx on orders
  Index Cond: (tenant_id = 999)
  Buffers: shared hit=... read=...
```

Chỉ khoảng 25 hàng cần đọc từ 250.000 hàng, nên index có thể tiết kiệm I/O.

### 6.3. Đây là minh họa, không phải kết quả được hứa hẹn

PostgreSQL **có thể chọn plan khác** tùy:

- Phiên bản.
- Cache và storage.
- Số trang/độ rộng tuple.
- Thống kê và correlation.
- Các indexes tồn tại.
- Tham số chi phí.
- Trạng thái visibility.
- Các điều kiện của SELECT.

Một kế hoạch `Bitmap Heap Scan` cho một trong hai query cũng có thể hợp lý ở một số cấu hình.

Quan trọng là phân tích **vì sao** planner đánh giá path đó rẻ, không phải ép output phải khớp hình mẫu.

## 7. Parameter binding không đồng nghĩa ép dùng generic plan

Đây là điểm dễ hiểu nhầm trong ứng dụng.

Truy vấn Java:

```java
String sql = """
    SELECT order_id, tenant_id, status, amount, payload
    FROM skew_lab.orders
    WHERE tenant_id = ?
    """;

PreparedStatement ps = connection.prepareStatement(sql);
ps.setInt(1, tenantId);
```

Khi thấy lớp `PreparedStatement`, không được tự kết luận rằng:

1. PostgreSQL chắc chắn đã tạo **server-side named prepared statement**.
2. Server chắc chắn đang dùng **generic plan**.
3. Mọi lần thực thi chắc chắn tái sử dụng một plan đã lập từ lần đầu.
4. Giá trị tham số hoàn toàn không ảnh hưởng planner.

JDBC là API parameter binding; pgJDBC driver có các cơ chế chuẩn bị và cache riêng. Hành vi server-side prepare phụ thuộc cấu hình/phiên bản driver và cách thực thi.

### 7.1. Tách ba tầng

```text
Tầng ứng dụng Java
  PreparedStatement + setInt(...)

Tầng driver / PostgreSQL wire protocol
  Bind parameters
  Có thể dùng unnamed/named statements theo cấu hình

Tầng PostgreSQL planner
  Custom plan theo lần thực thi
  hoặc Generic plan dùng lại theo quyết định của server
```

Để chẩn đoán chính xác, cần biết **câu lệnh có thật sự được prepare trên server và đang dùng loại plan nào**.

### 7.2. Đừng bỏ bind parameter để tránh generic plan

Một cách sửa sai phổ biến là ghép chuỗi:

```java
// KHÔNG KHUYẾN NGHỊ:
String sql = "SELECT * FROM skew_lab.orders " +
             "WHERE tenant_id = " + userSuppliedValue;
```

Nó làm tăng rủi ro injection, lỗi type/escaping, log query khác nhau và chi phí parse. Giải pháp đúng là **giữ parameterization**, sau đó thay đổi cách lập kế hoạch, cấu trúc truy vấn hoặc index dựa trên bằng chứng.

## 8. `PREPARE` / `EXECUTE` trong PostgreSQL

Để nghiên cứu custom/generic plan độc lập với JDBC, dùng SQL-level PREPARE.

### 8.1. Chuẩn bị câu lệnh

```sql
PREPARE orders_by_tenant(integer) AS
SELECT order_id, tenant_id, status, amount, payload
FROM skew_lab.orders
WHERE tenant_id = $1;
```

Tham số `$1` được khai báo kiểu `integer`, phù hợp với cột `tenant_id`.

### 8.2. Thực thi với hai giá trị

```sql
EXECUTE orders_by_tenant(1);
EXECUTE orders_by_tenant(999);
```

Hai câu này trả tập dữ liệu rất khác về quy mô:

- Tenant 1: 225.000 hàng.
- Tenant 999: 25 hàng.

Khi chạy thủ công trên client, việc xuất ra 225.000 hàng có thể tốn mạng/giao diện. Trong thực hành phân tích plan, nên dùng `EXPLAIN (ANALYZE, BUFFERS) EXECUTE` để server chạy query và đo mà không cần đẩy toàn bộ tập kết quả chi tiết về client.

### 8.3. Xem kế hoạch với tham số thật

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_by_tenant(999);
```

Cú pháp đúng là **EXPLAIN EXECUTE prepared_statement(arguments)**.

Không viết:

```sql
-- Không đúng cho việc chạy parameter $1 trong psql thông thường:
EXPLAIN
SELECT *
FROM skew_lab.orders
WHERE tenant_id = $1;
```

khi chưa có ngữ cảnh prepared statement/binding tương ứng.

### 8.4. Giải phóng prepared statement

```sql
DEALLOCATE orders_by_tenant;
```

Prepared statement SQL-level thuộc session, không phải file hoặc table. Khi session kết thúc, prepared statement của session đó cũng không còn.

## 9. Generic plan và custom plan được chọn như thế nào?

PostgreSQL có cấu hình:

```sql
SHOW plan_cache_mode;
```

Các chế độ thường có:

| Giá trị | Ý nghĩa |
| --- | --- |
| `auto` | Server tự quyết định giữa custom và generic theo cơ chế ước lượng |
| `force_custom_plan` | Ưu tiên custom plan cho các lần thực thi liên quan |
| `force_generic_plan` | Ưu tiên generic plan cho các lần thực thi liên quan |

### 9.1. Cơ chế auto không đơn giản là “lần 6 luôn dùng generic”

Với prepared statement có tham số, PostgreSQL thường thử **một số lần custom plan ban đầu** (thường khoảng năm lần) để ước lượng chi phí lập kế hoạch và thực thi. Sau đó nó có thể cân nhắc generic plan với chi phí trung bình đã quan sát/ước lượng.

Nhưng quy tắc chính xác phụ thuộc loại statement và cơ chế caching. Không được kết luận:

> Cứ gọi đúng năm lần là đến lần thứ sáu bắt buộc trở thành generic plan.

Với dữ liệu rất lệch, hoặc generic plan có cost ước lượng không cạnh tranh, PostgreSQL có thể tiếp tục custom. Một số trường hợp không cần custom vì statement không có tham số, hoặc những chi tiết khác chi phối quyết định.

### 9.2. Vì sao PostgreSQL cân nhắc generic?

Lập custom plan có chi phí **planning**. Với câu SQL được thực thi hàng triệu lần, giảm planning overhead có thể có lợi.

Nếu các giá trị tham số đều có cùng selectivity và cùng access path tối ưu, generic plan thường là một lựa chọn hợp lý.

### 9.3. Vì sao generic có thể kém trên dữ liệu lệch?

Một generic plan cần đáp ứng cả:

```text
tenant_id=1    -> ~225.000 rows
tenant_id=999  -> 25 rows
```

Giả sử generic plan chọn index scan:

- Với tenant nhỏ, chỉ vài chục heap accesses.
- Với tenant lớn, có thể hàng trăm nghìn heap accesses và lượng dữ liệu trả về rất lớn.

Giả sử generic plan chọn seq scan:

- Với tenant lớn, có thể hợp lý.
- Với tenant nhỏ, phải quét toàn bộ bảng để trả 25 hàng.

Vì vậy, chi phí thực tế có thể thay đổi mạnh theo **giá trị tham số**, dù generic plan không đổi.

### 9.4. Không phải lúc nào custom cũng nhanh hơn

Custom plan có planning cost và không nhất thiết tốt hơn generic đối với mọi giá trị. Khi query rất nhỏ, planning time có thể chiếm phần đáng kể.

Hãy so **thời gian tổng thể, số buffer touches, tần suất và các nhóm parameter quan trọng**, không chỉ nhìn execution time của một lần gọi.

## 10. So sánh custom và generic bằng `plan_cache_mode`

Đây là thí nghiệm cốt lõi của bài. Chạy trong **cùng session** sau khi `orders_by_tenant` đã được PREPARE.

### 10.1. Ép custom plan trong phạm vi thử nghiệm

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(999);

ROLLBACK;
```

`SET LOCAL` chỉ có hiệu lực trong transaction, giúp tránh vô tình giữ setting này cho các lần dùng connection sau.

Với custom plan, query nóng và lạnh có cơ hội chọn access path khác nhau.

### 10.2. Ép generic plan trong phạm vi thử nghiệm

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(999);

ROLLBACK;
```

Generic plan thường có cùng **shape** cho hai lần thực thi. Nhưng số hàng, thời gian và buffers **có thể khác xa**.

### 10.3. Cách quan sát plan minh họa

Một custom plan cho tenant 1 có thể hiện:

```text
Seq Scan on orders
  Filter: (tenant_id = 1)
```

Custom plan cho tenant 999 có thể hiện:

```text
Index Scan using orders_tenant_idx on orders
  Index Cond: (tenant_id = 999)
```

Generic plan có thể hiện:

```text
Index Scan using orders_tenant_idx on orders
  Index Cond: (tenant_id = $1)
```

**Đây chỉ là ví dụ cấu trúc**, không phải output đo được hoặc kế hoạch bắt buộc. Khi EXPLAIN hiển thị tham số `$1` thay vì giá trị cụ thể, đó là một dấu hiệu thường thấy của generic plan. Nên kết hợp với `plan_cache_mode` và các bộ đếm để xác minh.

### 10.4. So sánh những gì?

Với cả bốn lượt đo (hot/cold × custom/generic), ghi:

| Yếu tố | Cần quan sát |
| --- | --- |
| Plan nodes | Seq Scan / Index Scan / Bitmap Heap Scan |
| `rows` ước lượng | Generic có dự đoán khác custom không? |
| `actual rows` | Thực tế 225.000 hay 25? |
| `Buffers: shared hit/read` | Số trang được chạm và cache ảnh hưởng ra sao? |
| `Execution Time` | Chi phí thực thi |
| `Planning Time` | Chi phí lập kế hoạch |
| `loops` | Node có bị thực thi nhiều lần không? |
| `Index Cond` / `Filter` | Điều kiện nằm ở đâu? |
| `SETTINGS` | Có hiển thị plan_cache_mode đang đặt không? |

### 10.5. Sau thực hành

```sql
DEALLOCATE orders_by_tenant;
```

Nếu bạn dùng một tên PREPARE khác, DEALLOCATE đúng tên đã tạo. Không cần restart server.

## 11. Nhìn thấy prepared statement và số lần dùng plan

PostgreSQL cung cấp view:

```sql
SELECT
    name,
    statement,
    parameter_types,
    from_sql,
    generic_plans,
    custom_plans
FROM pg_prepared_statements;
```

Trên các phiên bản hiện đại hỗ trợ các cột `generic_plans` và `custom_plans`, chúng giúp quan sát **số lần** generic/custom plan được chọn cho prepared statements của **session hiện tại**.

### 11.1. Bộ đếm là theo session

Nếu bạn mở hai cửa sổ `psql`:

- Session A PREPARE `orders_by_tenant`.
- Session B SELECT từ `pg_prepared_statements`.

Session B có thể **không nhìn thấy statement của A**, vì view mô tả prepared statements khả dụng trong session hiện tại. Không dùng nó để kết luận “toàn hệ thống chưa có statement prepared”.

### 11.2. `from_sql`

`from_sql` cho biết prepared statement được tạo qua SQL `PREPARE` hay qua cơ chế giao thức khác theo PostgreSQL.

Trong ứng dụng pgJDBC, named prepared statements có thể được quản lý qua protocol thay vì SQL text `PREPARE`, tùy driver và cấu hình.

### 11.3. Bộ đếm không phải số người dùng bị chậm

Nếu `generic_plans = 100`, điều đó không nói 100 lần là tenant lớn hay nhỏ; view không lưu lịch sử giá trị từng tham số.

Cần đo theo những nhóm giá trị cụ thể và kết hợp metrics ứng dụng.

### 11.4. Kết quả có thể khác sau reconnect

Prepared statements theo session không sống xuyên một lần disconnect/reconnect thông thường. Với connection pool, mỗi physical backend có thể giữ trạng thái prepare riêng.

Do đó, một application có thể có **nhiều physical connections**, mỗi connection ở giai đoạn khác nhau của cơ chế custom/generic plan.

## 12. `pg_stats`: planner biết giá trị nào “hot” bằng cách nào?

PostgreSQL thu thập statistics qua `ANALYZE`. Một trong các nguồn chính của ước lượng equality predicate là **Most Common Values (MCV)**.

### 12.1. Xem thống kê tenant_id

```sql
SELECT
    schemaname,
    tablename,
    attname,
    null_frac,
    n_distinct,
    most_common_vals,
    most_common_freqs,
    histogram_bounds,
    correlation
FROM pg_stats
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
  AND attname = 'tenant_id';
```

Các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `null_frac` | Tỷ lệ NULL trong mẫu thống kê |
| `n_distinct` | Ước lượng số distinct values |
| `most_common_vals` | Những giá trị xuất hiện nhiều nhất được thống kê |
| `most_common_freqs` | Tần suất tương ứng với các MCV |
| `histogram_bounds` | Biên histogram cho phần phân bố phù hợp |
| `correlation` | Mức tương quan giữa thứ tự giá trị và thứ tự vật lý của hàng |

### 12.2. Tại sao MCV quan trọng?

Tenant 1 chiếm 90% bảng. Nếu statistics nhận ra tenant 1 là MCV với tần suất khoảng 0,9, planner lập custom plan cho:

```sql
WHERE tenant_id = 1
```

có thể ước lượng lượng hàng gần đúng hàng trăm nghìn.

Với một tenant khác không nằm trong MCV, planner sẽ dùng các thành phần thống kê còn lại để suy luận tần suất trung bình cho các giá trị không phổ biến.

### 12.3. Histogram không giống danh sách MCV

MCV đặc biệt hữu ích cho những điều kiện equality với giá trị phổ biến. Histogram có vai trò trong ước lượng phân bố và range predicates như:

```sql
WHERE created_at >= $1
  AND created_at < $2
```

Không nên hiểu mọi giá trị equality đều có một ô histogram riêng chính xác như bảng đếm toàn phần.

### 12.4. Statistics là ước lượng dựa trên mẫu

`ANALYZE` thường dùng sampling, không chạy `GROUP BY` chính xác toàn bảng cho mọi cột. Kết quả có thể biến đổi khi dữ liệu và sample thay đổi.

Thậm chí khi statistics mô tả tenant 1 rất tốt, **generic plan vẫn không được tối ưu theo chính giá trị `$1=1`** như custom plan.

### 12.5. Bảng skew thay đổi nhanh cần statistics mới

Nếu tenant 1 tăng gấp đôi dữ liệu trong một đợt import nhưng statistics chưa cập nhật, cả custom plan cũng có thể ước lượng chưa chính xác.

Vì vậy, cần phân biệt hai loại vấn đề:

- **Thiếu statistics / statistics stale**.
- **Generic plan không thể dùng đúng giá trị tham số**, dù statistics tốt.

Giải pháp khác nhau.

## 13. Tăng độ chi tiết thống kê khi cần

PostgreSQL cho phép đặt **statistics target** riêng cho cột.

```sql
ALTER TABLE skew_lab.orders
ALTER COLUMN tenant_id
SET STATISTICS 1000;

ANALYZE skew_lab.orders;
```

### 13.1. Khi nào hữu ích?

Khi cột có:

- Phân bố rất phức tạp.
- Nhiều giá trị phổ biến cần nhận diện.
- Histogram hiện tại không đủ chi tiết cho range queries.
- Query ước lượng sai nhiều dù stats tương đối mới.
- Workload nặng và thêm chi phí ANALYZE là chấp nhận được.

### 13.2. Khi nào không hữu ích?

Nếu tenant 1 đã hiện trong MCV với tần suất gần 0,9, tăng statistics target từ một giá trị bình thường lên 1000 **không đảm bảo generic plan trở nên nhạy với tenant 1**.

Lý do: giới hạn chính có thể là **đến planning time chưa biết giá trị `$1` cụ thể**, không phải thiếu kiến thức về phân bố của cột.

### 13.3. Đánh đổi

Statistics target cao có thể tăng:

- Chi phí và thời gian ANALYZE.
- Kích thước lưu trữ statistics.
- Chi phí planner với những truy vấn liên quan.

Đây là thông số cần điều chỉnh theo vấn đề đã đo, không phải một cài đặt “càng cao càng tốt” cho mọi cột.

### 13.4. Không quên ANALYZE sau khi đổi target

`ALTER COLUMN ... SET STATISTICS` thay đổi cách lấy statistics cho lần thống kê tiếp theo. Muốn planner hưởng lợi, thực hiện `ANALYZE` phù hợp.

## 14. Phân bố lệch nhiều cột: tenant_id và status có liên quan nhau

Trong bộ dữ liệu lab:

- Tenant 1 đa phần là `DONE`.
- Các tenant nhỏ có tỷ lệ `PENDING` cao hơn.

Nên hai predicate không hoàn toàn độc lập:

```sql
WHERE tenant_id = $1
  AND status = $2
```

### 14.1. Vấn đề giả định độc lập

Nếu planner suy luận đơn giản:

```text
P(tenant=1 AND status=PENDING)
  ≈ P(tenant=1) × P(status=PENDING)
```

ước lượng có thể khác đáng kể so với phân bố thực tế của từng tenant, vì tỷ lệ PENDING phụ thuộc tenant.

### 14.2. Kiểm tra bằng query dữ liệu lab

```sql
SELECT
    tenant_id,
    COUNT(*) AS total,
    COUNT(*) FILTER (
        WHERE status = 'PENDING'
    ) AS pending,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'PENDING')::numeric
        / NULLIF(COUNT(*), 0),
        4
    ) AS pending_ratio
FROM skew_lab.orders
WHERE tenant_id IN (1, 2, 999)
GROUP BY tenant_id
ORDER BY tenant_id;
```

Kết quả cho thấy tỷ lệ PENDING giữa tenant 1 và các tenant nhỏ rất khác nhau.

### 14.3. Extended statistics

Có thể tạo statistics nhiều cột:

```sql
CREATE STATISTICS orders_tenant_status_stats
    (mcv, dependencies)
ON tenant_id, status
FROM skew_lab.orders;

ANALYZE skew_lab.orders;
```

Thông tin MCV nhiều cột có thể giúp planner hiểu những cặp giá trị xuất hiện thường xuyên/hiếm.

### 14.4. Quan sát extended statistics

```sql
SELECT
    schemaname,
    tablename,
    statistics_name,
    attnames,
    kinds
FROM pg_stats_ext
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
ORDER BY statistics_name;
```

Cấu trúc view, mức thông tin chi tiết và khả năng dùng cho các loại predicate phụ thuộc phiên bản PostgreSQL.

### 14.5. Extended statistics không tự chữa mọi generic plan

Extended statistics giúp **ước lượng** khi planner có đủ thông tin predicate phù hợp. Nhưng với một generic plan:

```sql
WHERE tenant_id = $1
  AND status = $2
```

giá trị cụ thể của `$1`/`$2` không nhất thiết sẵn có để tận dụng MCV **theo cặp giá trị** như một custom plan.

Vì thế, cần kiểm tra **custom vs generic** cùng với extended statistics; tạo statistics không thay thế phân tích loại plan.

## 15. Index thường: cần đúng điều kiện và đúng quy mô

Ta đã có:

```sql
CREATE INDEX orders_tenant_idx
ON skew_lab.orders (tenant_id);
```

### 15.1. Tenant lạnh thường hưởng lợi

```sql
SELECT order_id, amount, payload
FROM skew_lab.orders
WHERE tenant_id = 999;
```

Index giúp PostgreSQL tìm khoảng 25 hàng thay vì đọc 250.000 hàng.

### 15.2. Tenant nóng có thể không

```sql
SELECT order_id, amount, payload
FROM skew_lab.orders
WHERE tenant_id = 1;
```

Khi phải trả 225.000 hàng với payload, việc duyệt index rồi heap có thể đắt. Seq Scan hoặc một path khác có thể hợp lý.

### 15.3. Tạo index không buộc generic/custom plan giống nhau

Dù index tồn tại, generic plan phải chọn một access path có chi phí kỳ vọng hợp lý cho **các giá trị tham số mà nó có thể gặp**.

Một index có thể làm truy vấn tenant lạnh rất nhanh khi custom, nhưng generic vẫn có thể chọn kế hoạch kém cho một nhóm giá trị.

### 15.4. Không tạo index trùng lặp

Nếu `orders_tenant_idx` đã có:

```sql
CREATE INDEX orders_tenant_idx
ON skew_lab.orders (tenant_id);
```

thì chạy lại sẽ lỗi tên index trùng. Và tạo index tên khác nhưng cùng định nghĩa thường chỉ tăng write overhead mà không tạo lợi ích đáng kể.

Trong lab, chỉ chạy mỗi `CREATE INDEX` một lần, hoặc dùng môi trường/schema mới nếu muốn so sánh trước và sau.

## 16. Composite index cho truy vấn phổ biến

Giả sử ứng dụng thường lọc:

```sql
WHERE tenant_id = $1
  AND status = $2
```

Có thể tạo:

```sql
CREATE INDEX orders_tenant_status_idx
ON skew_lab.orders (tenant_id, status);

ANALYZE skew_lab.orders;
```

### 16.1. Composite index giúp gì?

B-tree trên `(tenant_id, status)` có thể hỗ trợ trực tiếp các điều kiện equality trên hai cột, thường hiệu quả hơn tìm theo tenant rồi Filter trạng thái nếu query rất phổ biến và đủ selective.

### 16.2. So với hai index đơn

Nếu có hai index riêng:

```sql
CREATE INDEX orders_status_idx
ON skew_lab.orders (status);
```

PostgreSQL có thể cân nhắc:

- Index Scan theo tenant.
- Index Scan theo status.
- BitmapAnd kết hợp hai index.
- Composite index.
- Seq Scan.

Composite index có lợi thế khi truy vấn điển hình dùng cả hai cột, nhưng index đơn có thể tốt hơn cho những truy vấn chỉ lọc theo một cột.

### 16.3. Index không thay thế cập nhật statistics

Nếu planner ước lượng sai tần suất `(tenant_id, status)`, nó có thể chọn path chưa phù hợp dù có composite index. Extended statistics có thể giúp trong trường hợp tương ứng.

### 16.4. Thứ tự cột quan trọng

Index:

```sql
(tenant_id, status)
```

không giống hoàn toàn:

```sql
(status, tenant_id)
```

về cách hỗ trợ các predicate đơn cột, range, ORDER BY và scan bounds.

Chọn thứ tự dựa trên **tập query chính**, không theo thói quen “cột ít distinct phải đứng trước” hay “cột nhiều distinct luôn đứng trước” trong mọi bài toán.

### 16.5. Quá nhiều indexes cũng làm ghi chậm

Mỗi index tăng:

- Chi phí INSERT/UPDATE/DELETE.
- WAL.
- Dung lượng lưu trữ.
- Chi phí VACUUM/maintenance.
- Khả năng giảm hiệu quả HOT updates trong những trường hợp liên quan.

Không tạo một index mới chỉ vì có thể; cần đo hiệu quả tổng thể.

## 17. Partial index: điểm đặc biệt khi predicate có tham số

Partial index chỉ lưu những hàng thỏa một điều kiện cố định.

### 17.1. Tạo partial index cho đơn PENDING

```sql
CREATE INDEX orders_pending_tenant_time_idx
ON skew_lab.orders (tenant_id, created_at DESC)
WHERE status = 'PENDING';

ANALYZE skew_lab.orders;
```

Index này chỉ chứa các hàng có `status = 'PENDING'`. Nó có thể nhỏ hơn full index nếu số hàng PENDING tương đối ít.

### 17.2. Query có hằng predicate

```sql
SELECT order_id, tenant_id, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = 999
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 20;
```

Planner có thể chứng minh WHERE của query **suy ra** predicate của partial index, nên index là candidate hợp lệ.

### 17.3. Query tham số hóa cả status

```sql
PREPARE pending_or_done(integer, text) AS
SELECT order_id, tenant_id, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = $1
  AND status = $2
ORDER BY created_at DESC
LIMIT 20;
```

Với **generic plan**, PostgreSQL không được giả định rằng `$2 = 'PENDING'` cho mọi lần thực thi. Do đó, không thể mặc định dùng partial index `WHERE status = 'PENDING'` như thể predicate luôn đúng.

Với **custom plan** khi `$2 = 'PENDING'`, planner có thể cân nhắc partial index nếu chứng minh được predicate theo giá trị cụ thể và các điều kiện khác phù hợp.

### 17.4. Không nên hiểu là mọi query param đều không dùng được partial index

Mẫu sau khác:

```sql
PREPARE pending_for_tenant(integer) AS
SELECT order_id, tenant_id, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = $1
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 20;
```

Ở đây **status là hằng theo nghiệp vụ**, chỉ tenant_id mới là tham số. Cả generic và custom plan đều có thể nhận ra query chỉ xét hàng PENDING và cân nhắc partial index.

Bài học không phải “bỏ bind parameters”, mà là:

> Nếu một điều kiện là **hằng nghiệp vụ thật sự** của một dạng query, có thể biểu diễn nó thành hằng SQL để planner nhận ra partial index, trong khi **giá trị đầu vào người dùng** vẫn truyền bằng parameters.

### 17.5. Không hardcode input không tin cậy

Đừng thay `$2` bằng cách nối chuỗi trực tiếp từ HTTP request:

```java
// Không an toàn:
String sql = "SELECT * FROM skew_lab.orders WHERE status = '"
           + userStatus
           + "'";
```

Nếu ứng dụng cần hỗ trợ nhiều status, hãy dùng query variants được khai báo sẵn, hoặc giữ parameter binding và chọn giải pháp index/plan khác. Không hy sinh an toàn SQL để cố làm planner dùng partial index.

### 17.6. Dọn prepared statements của ví dụ

```sql
DEALLOCATE pending_or_done;
DEALLOCATE pending_for_tenant;
```

## 18. Bài toán `ORDER BY ... LIMIT` làm thay đổi lựa chọn plan

Không phải mọi truy vấn tenant nóng đều cần 225.000 hàng.

Ví dụ giao diện “20 đơn mới nhất”:

```sql
SELECT order_id, created_at, amount, status
FROM skew_lab.orders
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 20;
```

Nếu có index:

```sql
CREATE INDEX orders_tenant_time_idx
ON skew_lab.orders (tenant_id, created_at DESC);
```

B-tree có thể tìm các hàng thuộc tenant theo thứ tự thời gian và **dừng khi lấy đủ 20 hàng**.

### 18.1. Vì sao hot tenant cũng có thể hợp Index Scan?

Không cần trả 225.000 hàng. Query chỉ cần 20 hàng đầu theo một thứ tự cụ thể.

Index có thể tránh:

- Quét phần lớn bảng.
- Sort hàng trăm nghìn kết quả.
- Đọc quá nhiều heap pages.

### 18.2. Giải thích bằng EXPLAIN

```sql
PREPARE recent_orders(integer) AS
SELECT order_id, created_at, amount, status
FROM skew_lab.orders
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 20;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE recent_orders(1);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE recent_orders(999);

DEALLOCATE recent_orders;
```

Dù hai tenant có số hàng khác nhau rất lớn, một index path theo thứ tự có thể tốt cho cả hai vì **LIMIT**.

### 18.3. Đây là lý do không tối ưu chỉ theo tỷ lệ match

Cùng `tenant_id = 1` nhưng:

```sql
SELECT * FROM skew_lab.orders
WHERE tenant_id = 1;
```

khác đáng kể với:

```sql
SELECT order_id, created_at
FROM skew_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 20;
```

Planner cần xét **toàn truy vấn**, bao gồm cột trả về và thứ tự/giới hạn.

### 18.4. OFFSET sâu có thể làm mất lợi ích

```sql
SELECT order_id, created_at
FROM skew_lab.orders
WHERE tenant_id = 1
ORDER BY created_at DESC
LIMIT 20 OFFSET 200000;
```

Executor có thể phải xử lý lượng lớn index entries trước khi trả 20 hàng ở sâu. Khi cần pagination lớn, cân nhắc **keyset pagination** bằng tuple key ổn định, chẳng hạn `(created_at, order_id)`, nếu index tương thích và nghiệp vụ cho phép.

## 19. Covering index và Index Only Scan

Một kế hoạch `Index Only Scan` có thể giảm heap fetch khi:

1. Query cần các cột nằm trong index.
2. Access method/index hỗ trợ.
3. Heap visibility map cho phép xác nhận các tuple đủ điều kiện mà ít phải về heap.

### 19.1. Tạo covering index theo query

```sql
CREATE INDEX orders_tenant_time_cover_idx
ON skew_lab.orders (tenant_id, created_at DESC)
INCLUDE (status, amount);
```

Query:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT tenant_id, created_at, status, amount
FROM skew_lab.orders
WHERE tenant_id = 999
ORDER BY created_at DESC
LIMIT 20;
```

Planner có thể chọn Index Only Scan nếu phù hợp.

### 19.2. `Heap Fetches` không nhất thiết bằng 0

Ngay khi tất cả cột được bao phủ, PostgreSQL có thể phải về heap kiểm tra MVCC nếu heap pages chưa `all-visible`.

`EXPLAIN ANALYZE` có thể hiển thị:

```text
Index Only Scan using orders_tenant_time_cover_idx
  Index Cond: (tenant_id = 999)
  Heap Fetches: ...
```

`Heap Fetches = 0` là kết quả thuận lợi khi visibility map hỗ trợ đủ, không phải cam kết cho mọi bảng.

### 19.3. VACUUM trong lab

```sql
VACUUM (ANALYZE) skew_lab.orders;
```

VACUUM có thể cập nhật visibility map và giúp Index Only Scan tránh nhiều heap fetch trong một bảng ít thay đổi. Lệnh `VACUUM` thường không được đặt trong transaction block tường minh.

### 19.4. Đừng INCLUDE payload lớn tùy tiện

Đưa thêm `payload` vào index có thể làm index rất lớn, tăng write cost và thậm chí gặp giới hạn kích thước index tuple tùy dữ liệu.

Một covering index tối ưu cho báo cáo ít cột có thể hợp lý hơn một index chứa toàn bộ các cột văn bản.

### 19.5. Generic vs custom vẫn là vấn đề riêng

Ngay cả khi có covering index, generic plan có thể không phải lựa chọn tối ưu cho một query **trả phần lớn bảng**. Covering index giúp một số tình huống, nhưng không tự xóa mọi sự khác biệt cost do skew.

## 20. Điều kiện tùy chọn `$1 IS NULL OR col = $1`

Một mẫu API phổ biến cho ô lọc tùy chọn:

```sql
WHERE ($1 IS NULL OR tenant_id = $1)
```

Ý tưởng:

- `$1 = NULL`: lấy mọi tenant.
- `$1 = 999`: chỉ lấy tenant 999.

### 20.1. Vấn đề với generic plan

```sql
PREPARE orders_optional_tenant(integer) AS
SELECT order_id, tenant_id, status, amount
FROM skew_lab.orders
WHERE ($1 IS NULL OR tenant_id = $1);
```

Generic plan phải đúng cho **cả NULL và non-NULL**. Khi chưa biết `$1`, planner không thể đơn giản giả định điều kiện `tenant_id = $1` luôn có hiệu lực và dùng một access path chỉ đọc 25 rows.

Một custom plan có thể đơn giản hóa predicate theo giá trị thực tế:

- Với NULL: điều kiện có thể trở thành true, quét nhiều hàng.
- Với 999: điều kiện có thể trở thành equality chọn lọc.

### 20.2. So sánh trong lab

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_optional_tenant(NULL);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_optional_tenant(999);

ROLLBACK;
```

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_optional_tenant(NULL);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_optional_tenant(999);

ROLLBACK;
```

Kết thúc:

```sql
DEALLOCATE orders_optional_tenant;
```

### 20.3. Một giải pháp tốt: hai dạng query được khai báo trước

Nếu API thực sự có hai chế độ nghiệp vụ, có thể viết **hai câu SQL riêng**:

```sql
-- Chế độ xem toàn hệ thống, không có tenant filter:
SELECT order_id, tenant_id, status, amount
FROM skew_lab.orders;

-- Chế độ một tenant:
SELECT order_id, tenant_id, status, amount
FROM skew_lab.orders
WHERE tenant_id = $1;
```

Phân nhánh ở ứng dụng dựa trên tham số có/không, nhưng **vẫn bind các giá trị**.

Điều này giúp planner tối ưu hai dạng truy vấn khác nhau và thường rõ nghĩa hơn một predicate OR có nhiều nhánh khó dự đoán.

### 20.4. Không đồng nhất tách query với ghép chuỗi nguy hiểm

Tách query variants là:

```java
if (tenantId == null) {
    sql = "SELECT ... FROM skew_lab.orders";
} else {
    sql = "SELECT ... FROM skew_lab.orders WHERE tenant_id = ?";
}
```

Ứng dụng vẫn dùng `PreparedStatement` và `setInt` khi có parameter.

Không chèn trực tiếp giá trị người dùng vào SQL text.

## 21. Predicate `COALESCE` cũng có thể gây khó cho planner

Một biến thể thường thấy:

```sql
WHERE tenant_id = COALESCE($1, tenant_id)
```

Nếu muốn `$1 = NULL` nghĩa là “không lọc tenant”, pattern này có nhiều vấn đề:

- Là một biểu thức không đơn giản bằng equality predicate cố định.
- Khả năng sử dụng index phụ thuộc plan và cách rút gọn biểu thức.
- Với cột nullable, semantics `tenant_id = tenant_id` không tương đương “mọi hàng”, vì NULL không bằng NULL trong SQL.
- Generic plan có thể không tận dụng một index path tốt cho những giá trị rất chọn lọc.

Với ví dụ `tenant_id NOT NULL` trong lab, ý nghĩa NULL optional có thể gần mong muốn, nhưng **không đồng nghĩa tối ưu**.

**Khuyến nghị:** khi số kiểu lọc ít và rõ, chọn những query variants được parameterize riêng. Khi cần hỗ trợ nhiều combination filters, xây dựng SQL theo danh sách predicate đã được kiểm soát ở ứng dụng, giữ giá trị bằng bind params.

## 22. `IN`, `ANY` và tham số danh sách dài/ngắn

Một API có thể lọc nhiều tenants:

```sql
WHERE tenant_id = ANY($1::integer[])
```

Nhưng kích thước và nội dung mảng có thể thay đổi mạnh:

- Mảng một tenant nhỏ.
- Mảng chứa tenant lớn.
- Mảng hàng trăm tenant.
- Mảng rỗng.
- Mảng hàng nghìn giá trị.

### 22.1. Prepared statement dùng mảng

```sql
PREPARE orders_for_tenants(integer[]) AS
SELECT order_id, tenant_id, amount
FROM skew_lab.orders
WHERE tenant_id = ANY($1);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_for_tenants(ARRAY[999]::integer[]);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_for_tenants(ARRAY[1]::integer[]);

EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_for_tenants(ARRAY[1, 999]::integer[]);

DEALLOCATE orders_for_tenants;
```

### 22.2. Khó khăn với generic plan

Một generic plan không được chuyên biệt hóa theo **tập giá trị và chiều dài mảng** cụ thể của từng EXECUTE như custom plan. Nó phải chọn phương án dựa trên mô hình ước lượng chung phù hợp.

Vì thế, cùng dạng SQL với mảng 1 phần tử và mảng hàng nghìn phần tử có thể có hiệu năng rất khác.

### 22.3. Mảng rỗng có ý nghĩa rõ

```sql
WHERE tenant_id = ANY(ARRAY[]::integer[])
```

không match bất kỳ tenant nào với predicate equality thông thường.

Ứng dụng không nên mặc định “mảng rỗng nghĩa là toàn bộ tenant” nếu chưa định nghĩa riêng quy tắc nghiệp vụ.

### 22.4. Danh sách cực lớn nên đánh giá thiết kế khác

Khi một request gửi hàng nghìn/hàng chục nghìn ID, có thể xem xét:

- Temporary table chứa danh sách ID, có statistics thích hợp.
- `VALUES` relation để join.
- Batch processing theo nhóm.
- Join với một bảng có khóa/relationship thật.
- Giới hạn kích thước request ở tầng API.

Một mảng rất lớn có thể làm planning/execution khác hoàn toàn mảng ngắn. Chọn thiết kế dựa trên **quy mô dữ liệu thực tế**, không giữ một pattern mặc định cho mọi kích thước.

### 22.5. Cẩn thận với connection pool và temp tables

Temporary table thường gắn với session, nên cách dùng phụ thuộc connection pooling mode. Với transaction pooling, session state và temp table lifecycle có thể không phù hợp nếu thiết kế thiếu kiểm soát.

Đừng chuyển sang temp table để “chữa generic plan” mà bỏ qua kiến trúc connection.

## 23. Range predicates và skew theo thời gian

Không chỉ equality trên tenant có thể lệch. Dữ liệu thời gian thường dồn vào khoảng gần hiện tại.

Ví dụ:

```sql
SELECT order_id, created_at, amount
FROM skew_lab.orders
WHERE created_at >= $1
  AND created_at < $2;
```

Một lần chạy chọn 10 phút; lần khác chọn 18 tháng.

### 23.1. Hai khoảng thời gian khác quy mô

```sql
PREPARE orders_in_period(timestamptz, timestamptz) AS
SELECT order_id, created_at, amount, payload
FROM skew_lab.orders
WHERE created_at >= $1
  AND created_at < $2;
```

Query 1: khoảng một giờ.

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_in_period(
    timestamptz '2025-01-02 00:00:00+00',
    timestamptz '2025-01-02 01:00:00+00'
);
```

Query 2: khoảng rất dài.

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE orders_in_period(
    timestamptz '2025-01-01 00:00:00+00',
    timestamptz '2026-01-01 00:00:00+00'
);
```

Kết thúc:

```sql
DEALLOCATE orders_in_period;
```

Chưa có index trên `created_at`, nên hai query có thể đều Seq Scan. Muốn thử tác dụng index:

```sql
CREATE INDEX orders_created_idx
ON skew_lab.orders (created_at);

ANALYZE skew_lab.orders;
```

### 23.2. Một range rất ngắn có thể phù hợp Index Scan

Nếu chỉ match vài chục hàng, index range scan có thể lợi.

### 23.3. Một range rộng có thể phù hợp Seq Scan

Nếu chọn hầu hết bảng, quét tuần tự có thể rẻ hơn dùng index rồi đọc nhiều heap pages.

### 23.4. Generic plan khó tối ưu đồng thời hai range

Khi bounds là tham số, generic plan không được thiết kế riêng theo **độ rộng khoảng** của từng lần gọi. Custom plan có thể dùng bounds thật để ước lượng chọn lọc.

### 23.5. Histogram đặc biệt quan trọng

Với range predicate, `histogram_bounds` và các statistics liên quan phân bố thời gian là đầu vào quan trọng của planner.

Nếu dữ liệu mới được chèn gần đây mà statistics không theo kịp, query thời gian gần nhất có thể bị ước lượng sai. `ANALYZE` là bước kiểm tra hợp lý khi dữ liệu thay đổi lớn.

## 24. Range + tenant: skew nhiều chiều

Một query SaaS thực tế có thể là:

```sql
SELECT order_id, tenant_id, status, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = $1
  AND created_at >= $2
  AND created_at < $3
ORDER BY created_at DESC
LIMIT 50;
```

Tối ưu query này phụ thuộc đồng thời:

1. Tenant lớn hay nhỏ.
2. Khoảng thời gian ngắn hay dài.
3. Số hàng sau lọc.
4. Index có hỗ trợ thứ tự `ORDER BY` không.
5. `LIMIT 50` có giúp dừng sớm không.
6. Data correlation theo thời gian/tenant.
7. Generic hay custom plan.

### 24.1. Composite index thường đáng thử

```sql
CREATE INDEX orders_tenant_created_idx
ON skew_lab.orders (tenant_id, created_at DESC);
```

B-tree có thể tận dụng equality tenant rồi điều kiện range/thứ tự thời gian.

### 24.2. Một index phù hợp có thể giảm nhạy cảm skew

Với `ORDER BY created_at DESC LIMIT 50`, cùng một index composite có thể hoạt động tốt cho cả hot/cold tenant, vì query chỉ cần lấy tối đa 50 hàng.

Đây là ví dụ **sửa thiết kế index/query** có thể hiệu quả hơn ép custom plan trên toàn hệ thống.

### 24.3. Index không đảm bảo nhanh khi chưa có đủ hàng

Nếu một tenant có ít đơn trong khoảng thời gian đã chọn, executor có thể vẫn cần xét nhiều index entries tương ứng với khoảng và visibility để tìm đủ 50 hàng, hoặc kết thúc khi không còn.

Phải dùng `EXPLAIN ANALYZE` với cả hot/cold và cả range ngắn/dài, không chỉ một trường hợp đẹp nhất.

### 24.4. Thứ tự index keys phải theo query workload

Có các truy vấn chỉ theo thời gian toàn hệ thống và các truy vấn theo tenant + thời gian. Có thể cần index riêng, nhưng không nhất thiết tạo mọi tổ hợp. Đo và chọn ít index có tác động lớn.

## 25. Partitioning có giải quyết generic plan không?

Partitioning có thể giúp giới hạn tập dữ liệu phải xử lý, nhưng **không tự làm mọi generic plan trở thành custom**.

### 25.1. Ví dụ thiết kế chia tenant nóng

Một cách minh họa:

```sql
CREATE TABLE skew_lab.partitioned_orders_demo (
    order_id bigint NOT NULL,
    tenant_id integer NOT NULL,
    amount numeric(12,2) NOT NULL
) PARTITION BY LIST (tenant_id);

CREATE TABLE skew_lab.partitioned_orders_hot
PARTITION OF skew_lab.partitioned_orders_demo
FOR VALUES IN (1);

CREATE TABLE skew_lab.partitioned_orders_other
PARTITION OF skew_lab.partitioned_orders_demo
DEFAULT;
```

Đây là **bảng minh họa riêng**, không tự chứa dữ liệu của `skew_lab.orders`. Nó chỉ cho thấy kiểu thiết kế partition by tenant.

### 25.2. Planner và executor pruning

Với câu lệnh:

```sql
WHERE tenant_id = $1
```

PostgreSQL có thể loại những partitions không phù hợp theo:

- Giá trị đã biết ở planning time, hoặc
- Giá trị tham số được biết ở execution time trong những kế hoạch hỗ trợ **execution-time partition pruning**.

Do đó, một generic plan **vẫn có thể** hưởng lợi từ partition pruning trong những điều kiện tương ứng.

### 25.3. Nhưng partition pruning không giải quyết hết skew

Ngay cả khi chỉ còn một partition:

- Tenant nóng có thể vẫn có rất nhiều hàng.
- Một partition có thể vẫn cần Seq Scan/Bitmap/Index.
- Query không lọc theo partition key có thể đọc nhiều partitions.
- Quá nhiều partitions tăng overhead lập kế hoạch/vận hành.
- Indexes và statistics vẫn cần phù hợp.

### 25.4. Partitioning không phải biện pháp đầu tiên cho một query chậm

Trước khi chia bảng:

1. Kiểm tra query pattern.
2. Đọc EXPLAIN và actual rows.
3. Kiểm tra stats và indexes.
4. So generic/custom.
5. Tối ưu LIMIT/filter/output.
6. Đánh giá chi phí partition management.

Chỉ dùng partitioning khi workload, vòng đời dữ liệu, quy mô và lợi ích pruning xứng đáng.

## 26. Generic plan vẫn có thể phù hợp cho workload phân bố tương đối đều

Đừng đưa ra quy tắc “parameterized SQL thì luôn force_custom_plan”.

Ví dụ cột `order_id` là khóa chính:

```sql
PREPARE one_order(bigint) AS
SELECT order_id, tenant_id, status
FROM skew_lab.orders
WHERE order_id = $1;
```

Hầu hết lần gọi tìm tối đa một hàng. Một generic plan dùng primary key index thường hợp lý với mọi tham số.

### 26.1. Khi custom plan chỉ tăng planning cost

Nếu mọi giá trị parameter đều chọn đường truy cập tương tự và lượng hàng thực tế xấp xỉ nhau, lập custom plan mỗi lần có thể không tạo đủ lợi ích so với generic.

### 26.2. Cân nhắc số lần gọi

Một câu SQL chỉ chạy vài lần mỗi ngày không giống câu SQL chạy hàng trăm nghìn lần mỗi phút. Với query rất ngắn, planning cost có thể là tỷ trọng đáng kể.

### 26.3. Đánh giá bằng số liệu tổng

Một quyết định nên xem:

```text
Total latency
  ≈ planning overhead
    + execution cost
    + waiting / I/O
    + network and application overhead
```

Đây là công thức **định tính**, không phải mô hình thời gian chính xác theo từng phần từ EXPLAIN.

Cải thiện 20% execution time nhưng tăng đáng kể planning overhead ở workload cực nhiều request có thể không đáng. Cần đo trên workload thật.

## 27. `plan_cache_mode`: chọn phạm vi điều chỉnh phù hợp

Một phản ứng thường gặp khi thấy generic plan kém:

```sql
SET plan_cache_mode = force_custom_plan;
```

Lệnh này ảnh hưởng session theo phạm vi đặt config. Với connection pool, setting cấp session có thể tiếp tục tồn tại khi connection được tái sử dụng.

### 27.1. Ưu tiên `SET LOCAL` khi thử nghiệm

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

-- Thực thi những statement cần đo trên connection này.

COMMIT;
```

`SET LOCAL` có hiệu lực trong transaction và được reset khi transaction kết thúc theo cơ chế PostgreSQL.

### 27.2. Không có ý nghĩa mong muốn nếu autocommit tách statement

Sai kỳ vọng:

```sql
-- Khi mỗi statement chạy trong autocommit riêng:
SET LOCAL plan_cache_mode = force_custom_plan;

-- Statement sau có thể không chịu cấu hình local mong muốn:
EXECUTE orders_by_tenant(1);
```

Muốn `SET LOCAL` bao đúng statement, cần một transaction rõ ràng hoặc dùng cấu hình theo scope phù hợp.

### 27.3. Có thể đặt theo session nhưng phải cleanup

```sql
SET plan_cache_mode = force_custom_plan;

-- Các lệnh trong session này...

RESET plan_cache_mode;
```

Cách này có thể dùng trong lab, nhưng với pool phải đảm bảo reset trong mọi đường xử lý, kể cả exception. Nếu một request quên reset, request khác có thể chịu setting không mong muốn.

### 27.4. Điều chỉnh toàn server cần bằng chứng mạnh

Ép custom plan toàn bộ workload có thể làm những query đơn giản mất lợi ích generic reuse.

Ép generic plan toàn bộ workload có thể làm các truy vấn nhạy theo parameter chậm nghiêm trọng.

**Mặc định auto thường là điểm xuất phát tốt**. Điều chỉnh scope nhỏ cho những query cụ thể, được đo là có vấn đề.

### 27.5. `plan_cache_mode` không thay thế index

Nếu không có index phù hợp với predicate, cả custom plan và generic plan có thể chỉ còn Seq Scan hoặc các path khác. Ép custom không tự tạo một access path mới.

## 28. JDBC: tham số hóa đúng kiểu và quản lý prepared statements

Java backend thường truy vấn PostgreSQL bằng `PreparedStatement`.

### 28.1. Ví dụ an toàn với bind parameter

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class OrderQueryService {
    private final DataSource dataSource;

    public OrderQueryService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void printRecentOrders(int tenantId) throws SQLException {
        String sql = """
            SELECT order_id, created_at, status, amount
            FROM skew_lab.orders
            WHERE tenant_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """;

        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {

            ps.setInt(1, tenantId);
            ps.setInt(2, 20);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    long id = rs.getLong("order_id");
                    String status = rs.getString("status");
                    System.out.println(id + " : " + status);
                }
            }
        }
    }
}
```

Điểm chính:

- Bind `tenantId` bằng `setInt` đúng kiểu `integer`.
- Không ghép tenant ID vào SQL text.
- `LIMIT` cũng có thể là parameter ở PostgreSQL/JDBC khi driver truyền hợp lệ.
- Query trả tối đa 20 hàng nên tránh trả 225.000 hàng của tenant nóng chỉ để dựng một trang UI.
- `PreparedStatement` và `ResultSet` được đóng bằng try-with-resources.

### 28.2. Kiểu tham số ảnh hưởng planning và semantics

Trong PostgreSQL, kiểu parameter xác định operator/type resolution và có thể ảnh hưởng khả năng dùng index.

Ví dụ cột `tenant_id integer`:

- `setInt(1, tenantId)` thường rõ ràng.
- Truyền mọi thứ thành chuỗi hoặc cast tùy tiện có thể gây lỗi type hoặc tạo predicate khó tối ưu.
- `WHERE tenant_id::text = ?` thường khác với `WHERE tenant_id = ?` về index applicability.

Nên bind đúng kiểu SQL, tránh ép cột sang text chỉ để hợp với input UI.

### 28.3. Server-side prepare của pgJDBC không phải tính năng mặc định bất biến

pgJDBC có các lựa chọn liên quan **server-side prepare**, statement caching và ngưỡng chuẩn bị (thường được nhắc với cấu hình `prepareThreshold`). Hành vi chính xác phụ thuộc **phiên bản và cấu hình driver**, nên không suy từ tên Java class rằng server chắc chắn đã chuyển qua generic plan ở lần gọi thứ N.

Muốn xác minh:

- Đọc cấu hình pgJDBC đang triển khai.
- Quan sát prepared statement trong session khi có thể.
- So plan custom/generic bằng SQL trên cùng phiên bản PostgreSQL.
- Kiểm tra loại truy vấn và điều kiện driver có thể prepare trên server.
- Đo hiệu năng sau một số lần thực thi đại diện, không chỉ lần đầu.

### 28.4. Connection pool tạo nhiều cache contexts

Mỗi physical PostgreSQL backend có thể có prepared statements riêng. Nếu pool có 20 connections, không phải một lần chuẩn bị trên connection A tự áp dụng cho connection B.

Một hiện tượng “request đầu nhanh, sau đó chậm” có thể diễn ra không đồng đều vì:

- Mỗi connection đạt trạng thái prepared/cache ở thời điểm khác nhau.
- Những giá trị tham số khác nhau đi qua các connection.
- Generic/custom selection khác nhau theo history.
- Pool reset/đóng connection.
- Workload, cache và autovacuum thay đổi.

Chẩn đoán cần quan sát theo đúng **physical connection/session** khi có thể.

## 29. Ép custom plan cho một transaction trong JDBC

Ví dụ giáo dục về cách giới hạn `plan_cache_mode` trong một transaction:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import javax.sql.DataSource;

public final class SkewAwareQuery {
    private final DataSource dataSource;

    public SkewAwareQuery(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public long countTenantOrders(int tenantId) throws SQLException {
        try (Connection conn = dataSource.getConnection()) {
            conn.setAutoCommit(false);

            try {
                try (Statement setting = conn.createStatement()) {
                    setting.execute(
                        "SET LOCAL plan_cache_mode = force_custom_plan"
                    );
                }

                long count;
                try (PreparedStatement ps = conn.prepareStatement(
                        "SELECT COUNT(*) " +
                        "FROM skew_lab.orders " +
                        "WHERE tenant_id = ?"
                )) {
                    ps.setInt(1, tenantId);
                    try (ResultSet rs = ps.executeQuery()) {
                        rs.next();
                        count = rs.getLong(1);
                    }
                }

                conn.commit();
                return count;
            } catch (SQLException | RuntimeException ex) {
                try {
                    conn.rollback();
                } catch (SQLException rollbackError) {
                    ex.addSuppressed(rollbackError);
                }
                throw ex;
            }
        }
    }
}
```

Ví dụ trên có mục đích thể hiện scope:

1. `setAutoCommit(false)` mở transaction do code quản lý.
2. `SET LOCAL` đặt setting trong cùng transaction.
3. Câu prepared SQL được thực thi trên **cùng connection**.
4. `COMMIT` kết thúc transaction và reset setting local.
5. Lỗi thì `ROLLBACK`.

### 29.1. Vì sao không áp dụng mẫu này cho mọi request ngay?

Vì nó tạo transaction tường minh và ép custom planning cho một query mà chưa có số liệu chứng minh cần làm vậy. Với `COUNT(*) WHERE tenant_id=?`, chi phí lập kế hoạch có thể không đáng kể hoặc cũng có thể là yếu tố quan trọng khi gọi cực nhiều lần.

Chỉ áp dụng cho những statement/workload đã được xác định có vấn đề generic plan.

### 29.2. Chú ý framework transaction manager

Nếu ứng dụng dùng framework quản lý transaction, không nên tự gọi `setAutoCommit`/`commit` trên connection mà framework đang quản lý.

Hãy dùng cách cấu hình transaction hoặc session settings tương thích framework, đảm bảo SQL thực thi trên đúng connection/transaction.

### 29.3. `SET LOCAL` không thể “sửa” một query đã chạy trước đó

Nó ảnh hưởng việc chọn kế hoạch ở những lần thực thi thuộc phạm vi setting về sau. Không thay đổi plan hoặc kết quả của một statement đã chạy xong.

### 29.4. Đừng đổi sang giao thức simple query chỉ để lẩn tránh plan cache

Thay đổi mode của driver có thể ảnh hưởng nhiều hành vi: server-side preparation, binding, dữ liệu nhị phân/text, streaming hoặc pooling. Nếu cân nhắc, đo/kiểm thử theo tài liệu driver và workload, không dùng như mẹo tổng quát.

## 30. Một chiến lược ứng dụng: phân loại query thay vì phân loại người dùng bằng tên

Một giải pháp tốt thường là **chọn query shape theo mục đích**:

- Truy vấn chi tiết một tenant.
- Truy vấn tổng quan toàn hệ thống.
- Truy vấn các đơn PENDING.
- Truy vấn báo cáo theo range dài.
- Truy vấn 20 đơn mới nhất.

### 30.1. Tránh “một SQL khổng lồ làm mọi thứ”

Mẫu khó tối ưu:

```sql
SELECT order_id, tenant_id, status, created_at, amount
FROM skew_lab.orders
WHERE ($1 IS NULL OR tenant_id = $1)
  AND ($2 IS NULL OR status = $2)
  AND ($3 IS NULL OR created_at >= $3)
  AND ($4 IS NULL OR created_at < $4)
ORDER BY created_at DESC
LIMIT $5;
```

Nếu mọi tham số đều optional, generic plan phải phù hợp với rất nhiều trường hợp khác nhau về selectivity.

### 30.2. Tách những use cases có semantics rõ ràng

Ví dụ:

```sql
-- API lấy 20 đơn mới nhất của một tenant:
SELECT order_id, created_at, status, amount
FROM skew_lab.orders
WHERE tenant_id = $1
ORDER BY created_at DESC
LIMIT 20;

-- API lấy 20 đơn PENDING mới nhất của một tenant:
SELECT order_id, created_at, amount
FROM skew_lab.orders
WHERE tenant_id = $1
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 20;

-- Báo cáo tổng hệ thống theo thời gian:
SELECT status, COUNT(*), SUM(amount)
FROM skew_lab.orders
WHERE created_at >= $1
  AND created_at < $2
GROUP BY status;
```

Ba câu SQL có access patterns rõ ràng hơn. Tenant ID và date bounds vẫn được bind.

### 30.3. Có cần tách hot và cold tenant thành hai statements?

Đôi khi có thể. Nhưng trước đó nên thử:

- Một index tốt cho cả hai trường hợp.
- Thêm LIMIT/order thích hợp.
- Custom planning ở scope hẹp.
- Thống kê và query shape.

Nếu thật sự cần hai đường xử lý khác nhau, nên quản lý phân loại bằng **metadata có cập nhật**, thay vì hardcode “tenant 1 luôn nóng”. Data skew thay đổi theo thời gian.

### 30.4. Tránh làm lộ sự phân loại tenant thành quyền truy cập

Tối ưu hot/cold chỉ là vấn đề hiệu năng. Nó không thay thế kiểm tra quyền truy cập tenant.

Dù query plan nào được chọn, ứng dụng vẫn phải bảo vệ tenant isolation qua authorization và các cơ chế schema/RLS phù hợp nếu triển khai.

## 31. Row-Level Security (RLS) và truy vấn tham số hóa

Trong hệ thống đa tenant, một số triển khai dùng Row-Level Security.

Ví dụ mô tả ý tưởng:

```text
Ứng dụng xác thực tenant.
RLS policy giới hạn những hàng mà role được phép thấy.
Query vẫn có tenant_id = $1 hoặc một điều kiện nghiệp vụ khác.
```

### 31.1. RLS không tự giải quyết generic plan

RLS thêm những điều kiện bảo mật/visibility vào truy vấn theo cơ chế PostgreSQL, nhưng planner vẫn phải lựa chọn access paths trong các ràng buộc hợp lệ.

Nếu dữ liệu lệch mạnh, custom/generic và thống kê vẫn là những yếu tố cần đo.

### 31.2. Không bỏ WHERE để “tăng tốc” nếu WHERE là một phần của bảo vệ

Thay đổi SQL hoặc tạo query variants phải giữ nguyên authorization semantics.

Đừng đổi từ:

```sql
WHERE tenant_id = $1
```

sang một query không lọc tenant chỉ vì Seq Scan có vẻ nhanh hơn trên tenant nóng, nếu request đó chỉ có quyền truy cập một tenant.

### 31.3. Thống kê có thể chịu ràng buộc bảo mật

Việc đọc một số statistics hay plan details có thể chịu quyền, và dữ liệu thống kê có thể chứa thông tin nhạy cảm của phân bố. Chỉ dùng công cụ giám sát với role có quyền phù hợp.

## 32. Generic plan “đẹp” trong EXPLAIN có thể rất chậm với tenant nóng

Ví dụ plan giả định:

```text
Index Scan using orders_tenant_idx on orders
  (cost=0.42..350.00 rows=250 width=180)
  Index Cond: (tenant_id = $1)
```

Nếu thực tế `$1 = 1`:

```text
actual rows=225000
Buffers: shared hit=... read=...
Execution Time: ...
```

Planner đã ước lượng generic khoảng 250 hàng nhưng executor phải xử lý 225.000 hàng.

**Không nên lấy số 250 và 225.000 trong đoạn này làm số đo từ PostgreSQL.** Đây là ví dụ minh họa kiểu chênh lệch phổ biến giữa generic estimate và actual rows trong skew dataset.

### 32.1. Vì sao index path có thể đắt ở hot tenant?

- Rất nhiều index entries được đọc.
- Rất nhiều tuple cần đọc tại heap.
- Heap pages có thể nằm rải rác.
- Payload được truy xuất nhiều.
- Có thể tăng cache churn, I/O, CPU.

### 32.2. Nhưng cũng có khi index path vẫn tốt cho hot tenant

Nếu:

- Index access có correlation cao.
- Query chỉ cần các cột đã cover.
- `ORDER BY LIMIT` dừng sớm.
- Nhiều heap pages nằm trong cache.
- Query trả nhiều hàng nhưng index-only có Heap Fetches rất ít.

Do đó, không được lập quy tắc “hot tenant phải dùng Seq Scan”. **Phải đo kế hoạch thực**.

### 32.3. So sánh cost và actual time

`cost` là **đơn vị ước lượng**, không phải milliseconds. Một generic plan có estimated total cost thấp vẫn có thể có actual runtime cao với một parameter hiếm gặp theo thống kê chung.

Để chọn giải pháp, xem cả:

- Estimated rows vs actual rows.
- Buffers.
- Execution Time.
- Planning Time.
- Tổng request latency.
- Tỷ lệ hot/cold calls trong workload.

## 33. Quan sát từ ứng dụng: đừng đo một giá trị tham số

Nếu performance test chỉ dùng tenant 999, rất dễ kết luận:

```text
Query nhanh ~ vài ms -> Không vấn đề
```

Trong khi production tenant 1 có thể dùng cùng SQL nhưng trả 225.000 hàng và chậm hơn nhiều.

### 33.1. Xây bộ test theo phân vị dữ liệu

Nên kiểm tra tối thiểu:

| Nhóm parameter | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Hot | tenant_id = 1 | Giá trị chiếm phần lớn bảng |
| Cold | tenant_id = 999 | Giá trị rất ít hàng |
| Không tồn tại | tenant_id = 2000 | Trả 0 hàng |
| Status phổ biến | status = DONE | Nhiều match |
| Status ít phổ biến | status = FAILED | Ít match |
| Tenant + status correlated | 1/PENDING, 999/PENDING | Multi-column skew |
| Range ngắn | Vài phút/giờ | Index-selective |
| Range dài | Nhiều tháng | Scan nhiều hàng |
| Không filter | Tham số optional NULL | Có thể scan toàn bộ |
| Mảng nhỏ/lớn | ANY([999]) vs ANY([...]) | Parameter cardinality |

### 33.2. Test warmup và cache

Lần đầu query có thể chậm vì cache chưa nóng hoặc server chưa chuyển sang generic plan.

Cần:

- Đo sau một số lần warmup thích hợp.
- Ghi rõ trạng thái plan/cache.
- Chạy lặp và xem phân bố latency.
- Không chỉ chọn “lần nhanh nhất”.
- Theo dõi concurrency và tải của database.

### 33.3. Đo p95/p99, không chỉ mean

Một generic plan có thể tốt cho 99% tenant nhỏ nhưng rất kém với tenant lớn. Nếu tenant lớn là khách hàng quan trọng, p99 latency hoặc SLA riêng của tenant có thể bị vi phạm dù mean latency chung vẫn tốt.

### 33.4. Đo tổng dữ liệu trả về

Query trả 225.000 hàng tốn mạng và thời gian xử lý object phía ứng dụng, ngay cả khi server-side plan tốt.

Đừng cố tối ưu planner để che vấn đề API không phân trang, không giới hạn output hoặc truy vấn quá nhiều cột.

## 34. `pg_stat_statements`: phát hiện query chậm nhưng có giới hạn

Nếu extension `pg_stat_statements` được cài và cấu hình đúng, có thể quan sát thống kê query theo dạng normalized.

Ví dụ trong một môi trường đã enable extension:

```sql
SELECT
    query,
    calls,
    total_exec_time,
    mean_exec_time,
    rows
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 20;
```

Cột và khả năng truy cập phụ thuộc phiên bản extension/role. Không giả định extension này đã được cài ở mọi database.

### 34.1. Vì sao pg_stat_statements có thể che data skew?

Một statement normalized dạng:

```sql
SELECT ... WHERE tenant_id = $1
```

có thể tổng hợp nhiều lần gọi với:

- Tenant 1: 225.000 hàng.
- Tenant 999: 25 hàng.
- Tenant 2: 25 hàng.

Thống kê aggregate **không lưu sẵn từng giá trị tham số của mọi lần gọi** để bạn tách ngay bằng một SELECT đơn giản.

### 34.2. Mean latency có thể gây hiểu nhầm

Nếu tenant nhỏ gọi rất nhiều, mean execution time có thể thấp, còn tenant lớn rất chậm nhưng số lần gọi ít hơn.

Để chẩn đoán skew cần thêm:

- Application metrics phân nhóm hot/cold.
- Trace/log tham số đã được **ẩn dữ liệu nhạy cảm** hoặc phân nhóm selectivity.
- Sample EXPLAIN cho giá trị đại diện.
- Generic/custom counters theo session khi cần.
- Khả năng quan sát các query variants.

### 34.3. Theo dõi planning time

Một số cấu hình/phiên bản `pg_stat_statements` có thể theo dõi thời gian planning khi tính năng phù hợp được bật. Không tự suy từ một bảng có `mean_exec_time` rằng nó bao gồm planning time.

Khi cân nhắc force custom, planning overhead là một phần của quyết định.

### 34.4. Đừng tự động log toàn bộ PII parameter values

Tenant IDs, email, tokens hoặc thông số kinh doanh có thể nhạy cảm. Metrics có thể chỉ cần phân lớp:

```text
hot tenant
medium tenant
cold tenant
large range
short range
```

thay vì log mọi parameter value nguyên văn.

## 35. Dùng EXPLAIN có hệ thống

Lệnh quan trọng nhất trong bài:

```sql
EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE orders_by_tenant(1);
```

Nó thực thi prepared query và thu số liệu.

### 35.1. Các trường cần đọc

| Trường | Câu hỏi |
| --- | --- |
| Scan node | Seq Scan, Index Scan, Bitmap Heap Scan hay Index Only Scan? |
| `Index Cond` | Index được dùng để giới hạn hàng như thế nào? |
| `Filter` | Predicate nào vẫn phải lọc sau khi truy cập? |
| `Rows Removed by Filter` | Bao nhiêu hàng bị loại sau scan? |
| `cost` | Planner ước lượng chi phí ra sao? |
| `rows` | Planner dự đoán bao nhiêu hàng? |
| `actual rows` | Bao nhiêu hàng thực sự đi qua node? |
| `loops` | Node thực thi mấy lần? |
| `Buffers` | Bao nhiêu blocks hit/read/dirtied/written? |
| `Heap Fetches` | Index Only Scan có cần về heap không? |
| `Planning Time` | Chi phí lập kế hoạch |
| `Execution Time` | Thời gian thực thi theo EXPLAIN |
| `Settings` | Những cấu hình kế hoạch khác default nào được hiển thị? |

### 35.2. Buffers không đơn giản bằng số lần đọc physical disk

`shared read` biểu thị block được đọc vào shared buffers. Hệ điều hành có thể phục vụ lần đọc đó từ filesystem cache.

So sánh các lượt chạy cần xét trạng thái cache, concurrency và tính lặp.

### 35.3. Chỉ nhìn node scan là chưa đủ

Một Index Scan có thể được gọi 100.000 lần bên trong Nested Loop. Một Seq Scan có thể là phương án tốt của Hash Join khi cần phần lớn bảng.

Để tối ưu query nhiều bảng, xem **toàn cây kế hoạch**, đặc biệt `loops`, join selectivity và những node Sort/Hash/Aggregate.

### 35.4. EXPLAIN ANALYZE có overhead

`ANALYZE` thêm instrumenting để đo thời gian/số hàng. Thời gian đo có thể khác execution thông thường, nhất là query rất ngắn.

`TIMING OFF` có thể giảm overhead thu thời gian từng node:

```sql
EXPLAIN (ANALYZE, BUFFERS, TIMING OFF)
EXECUTE orders_by_tenant(999);
```

### 35.5. EXPLAIN ANALYZE trên DML sẽ thực thi DML

Nếu prepared statement là `UPDATE`, `EXPLAIN ANALYZE EXECUTE` **thực sự sửa dữ liệu**.

Trong database lab, có thể bọc transaction và rollback dữ liệu transactional, nhưng cần hiểu side effects ngoài database và sequence/nontransactional effects. Không thử lệnh DML nguy hiểm chỉ vì định “xem plan”.

## 36. Một checklist chẩn đoán khi một query thỉnh thoảng rất chậm

Khi cùng câu SQL có lúc nhanh, có lúc chậm:

1. **Lấy SQL và parameter values đại diện**, ít nhất một hot và một cold.
2. **Kiểm tra kết quả trả về**, số hàng của mỗi loại.
3. **Xác minh schema/indexes** và đúng database.
4. **Kiểm tra thống kê** `pg_stats` của cột lệch.
5. **Kiểm tra loại prepared execution** qua driver/config và session.
6. **So custom/generic** bằng `plan_cache_mode` trong lab.
7. **Đọc EXPLAIN ANALYZE BUFFERS** cho hot/cold.
8. **Kiểm tra optional filters**, OR/COALESCE và mảng/range.
9. **Kiểm tra LIMIT/ORDER BY**, có thể tạo index hiệu quả cho cả hai loại.
10. **Kiểm tra partial index** nếu query cố định một status.
11. **Xem composite/covering index** nếu nhiều predicate thường đi cùng.
12. **Đối chiếu extended stats** khi có nhiều cột phụ thuộc nhau.
13. **Đo planning overhead** trước khi ép custom lâu dài.
14. **Đo trên workload đủ đồng thời** và lặp nhiều lần.
15. **Chọn scope thay đổi nhỏ nhất**: query rewrite, index, thống kê hay custom plan cho một transaction.
16. **Xem rủi ro hồi quy** cho nhóm parameter khác.
17. **Đo cả write cost** sau khi thêm index.
18. **Giữ parameter binding** và kiểm soát authorization.
19. **Theo dõi sau triển khai** khi phân bố dữ liệu thay đổi.
20. **Ghi lại giả thuyết và số liệu**, tránh chọn giải pháp chỉ vì một plan screenshot.

## 37. Những ngộ nhận thường gặp

| Ngộ nhận | Thực tế |
| --- | --- |
| Bind parameter luôn sinh một generic plan | Có thể custom hoặc generic tùy đường thực thi/caching |
| JDBC PreparedStatement chắc chắn đã PREPARE trên server ngay lần đầu | Phụ thuộc driver và cấu hình |
| Lần thực thi thứ sáu luôn generic | PostgreSQL cân nhắc cost; không có cam kết đơn giản như vậy |
| Generic plan bỏ qua WHERE vì không biết giá trị | Executor vẫn áp dụng parameter đúng |
| Custom plan luôn nhanh hơn | Planning overhead và workload có thể làm generic hợp lý |
| Query hot phải luôn Seq Scan | LIMIT, covering index, correlation có thể làm index tốt |
| Query cold phải luôn Index Scan | Bảng nhỏ hoặc index không phù hợp có thể khiến Seq Scan hợp lý |
| Có index thì generic plan sẽ chọn index | Planner chọn theo cost, không theo sự tồn tại index đơn thuần |
| `ANALYZE` sẽ chữa mọi generic plan | Statistics không tự cung cấp giá trị parameter lúc lập generic |
| Tăng statistics target là luôn nhanh hơn | Có overhead và không khắc phục mọi nguyên nhân |
| Histogram cho biết chính xác mọi equality value | MCV/histogram có vai trò khác nhau |
| Extended statistics tự tạo composite index | Chỉ giúp estimates trong các trường hợp hỗ trợ |
| Tạo partial index cho status=PENDING thì generic status=$1 sẽ luôn dùng | Generic không được giả định $1 luôn PENDING |
| Phải nối status vào SQL để dùng partial index | Có thể tạo query variant với hằng nghiệp vụ và bind input |
| `OR $1 IS NULL` luôn tối ưu như equality | Generic plan phải hỗ trợ cả NULL và non-NULL |
| `COALESCE` luôn tương đương optional filter an toàn | NULL semantics và indexability có thể khác |
| Một ANY array có 1 và 1000 phần tử có chi phí giống nhau | Cardinality và giá trị mảng ảnh hưởng rất mạnh |
| Một index trên tenant_id đủ cho mọi query tenant | ORDER BY, status, time range, payload vẫn quan trọng |
| INCLUDE mọi cột sẽ luôn tốt | Tăng kích thước index/write cost, chưa chắc index-only |
| Partitioning tự giải quyết plan cache | Có pruning trong điều kiện phù hợp nhưng không hết skew |
| `force_custom_plan` phải bật toàn database | Nên cân nhắc scope hẹp theo evidence |
| `SET LOCAL` ngoài transaction riêng luôn còn hiệu lực cho query sau | Không; cần transaction bao đúng statement |
| Prepared statements được chia sẻ toàn pool | Mỗi backend/session có state riêng |
| `pg_prepared_statements` xem mọi session | Chủ yếu cho session hiện tại |
| `pg_stat_statements` tách sẵn latency theo từng tenant | Thường tổng hợp normalized query, không lưu mọi parameter |
| EXPLAIN cost là milliseconds | Là đơn vị ước lượng của planner |
| EXPLAIN ANALYZE không chạy query | Nó thực thi; DML có thể thay dữ liệu |
| Query thực thi nhanh là API luôn nhanh | Còn network, serialization, số hàng trả, application |
| Test tenant nhỏ đủ đại diện cho toàn hệ thống | Skew yêu cầu test hot, cold và edge cases |
| Tối ưu planner quan trọng hơn phân trang | Trả 225.000 hàng vẫn có chi phí rất lớn |
| Bỏ tenant filter để nhanh hơn là chấp nhận được | Có thể phá vỡ authorization và bảo mật dữ liệu |
| Một lần benchmark đủ để quyết định | Cache, planning, load và variability ảnh hưởng mạnh |

## 38. Bài tập thực hành có đáp án

Dùng schema `skew_lab` đã chuẩn bị. Với các bài so kế hoạch, hãy ghi lại **plan thật trên máy của bạn**; PostgreSQL có thể chọn một path khác với ví dụ khi cost/phiên bản/cấu hình thay đổi.

### Bài 1. Phân biệt hot và cold tenant

```sql
SELECT tenant_id, COUNT(*) AS order_count
FROM skew_lab.orders
WHERE tenant_id IN (1, 999)
GROUP BY tenant_id
ORDER BY tenant_id;
```

**Đáp án:** tenant 1 có 225.000 đơn; tenant 999 có 25 đơn. Đây là phân bố lệch rất mạnh.

### Bài 2. Vì sao một generic plan có thể kém?

**Đáp án:** planner không chuyên biệt hóa theo giá trị từng lần thực thi. Kế hoạch phù hợp khi trả 25 hàng có thể không phù hợp khi trả 225.000 hàng.

### Bài 3. Parameter binding có bảo đảm generic plan không?

**Đáp án:** không. Driver và server có thể dùng custom/generic tùy cơ chế chuẩn bị và caching.

### Bài 4. Tại sao không nên nối tenant ID vào SQL text?

**Đáp án:** có rủi ro SQL injection với dữ liệu người dùng, lỗi escaping/type và mất lợi ích query reuse. Giữ bind parameters.

### Bài 5. PREPARE một câu query theo tenant

```sql
PREPARE q1(integer) AS
SELECT order_id, amount
FROM skew_lab.orders
WHERE tenant_id = $1;
```

**Đáp án:** `q1` là prepared statement session-level với một tham số integer. Dùng `EXECUTE q1(1)` hoặc `EXECUTE q1(999)`.

### Bài 6. Xem plan của một prepared execution

```sql
EXPLAIN (ANALYZE, BUFFERS)
EXECUTE q1(999);
```

**Đáp án:** EXPLAIN EXECUTE là cách đo đúng một prepared statement đã tồn tại trong session. Xong bài nhớ `DEALLOCATE q1`.

### Bài 7. Force custom plan trong một transaction

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;
EXPLAIN EXECUTE q1(1);
EXPLAIN EXECUTE q1(999);
ROLLBACK;
```

**Đáp án:** hai lần lập custom có thể dùng giá trị parameter cụ thể, cho phép planner chọn paths khác nhau.

### Bài 8. Force generic plan trong một transaction

```sql
BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;
EXPLAIN EXECUTE q1(1);
EXPLAIN EXECUTE q1(999);
ROLLBACK;
```

**Đáp án:** generic plan không tối ưu riêng theo từng giá trị; plan shape có thể giống nhau, actual workload vẫn khác.

### Bài 9. `plan_cache_mode = auto` nghĩa gì?

**Đáp án:** PostgreSQL tự lựa chọn giữa custom/generic theo cost heuristic; không đồng nghĩa lần thứ sáu chắc chắn generic.

### Bài 10. Tại sao generic có thể giảm latency?

**Đáp án:** tránh một phần planning overhead khi được tái sử dụng, đặc biệt query đơn giản thực thi nhiều lần và mọi parameter có access path tương tự.

### Bài 11. Tìm MCV của tenant_id

```sql
SELECT most_common_vals, most_common_freqs
FROM pg_stats
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
  AND attname = 'tenant_id';
```

**Đáp án:** tenant 1 có thể xuất hiện là MCV với frequency gần 0,9 sau ANALYZE.

### Bài 12. Generic plan có dùng MCV 0,9 để biết `$1` luôn là 1 không?

**Đáp án:** không. Nó biết phân bố nói chung nhưng không được giả định giá trị `$1` cụ thể cho mọi EXECUTE.

### Bài 13. Khi nào nên chạy ANALYZE?

**Đáp án:** khi dữ liệu thay đổi đáng kể hoặc stats stale/estimates sai; ANALYZE cập nhật thông tin giúp planner. Nó không ép một plan cụ thể.

### Bài 14. Statistics target cao có phải luôn tốt?

**Đáp án:** không. Nó tăng chi phí statistics và không giải quyết việc generic plan thiếu giá trị tham số cụ thể khi planning.

### Bài 15. Vì sao tenant và status là hai cột phụ thuộc nhau?

**Đáp án:** trong dataset, tỷ lệ DONE/PENDING khác nhau giữa tenant nóng và tenant nhỏ, nên ước lượng hai điều kiện bằng giả định độc lập có thể sai.

### Bài 16. Tạo extended statistics

```sql
CREATE STATISTICS orders_tenant_status_more
    (mcv, dependencies)
ON tenant_id, status
FROM skew_lab.orders;

ANALYZE skew_lab.orders;
```

**Đáp án:** giúp thống kê những kết hợp giá trị trong trường hợp planner hỗ trợ; không tự tạo index. Nếu đã có object tương tự, không cần tạo bản trùng trong lab.

### Bài 17. Composite index nào phù hợp `tenant_id = ? AND status = ?`?

**Đáp án gợi ý:** B-tree `(tenant_id, status)` là một lựa chọn tốt để thử, sau đó so EXPLAIN với index đơn/BitmapAnd.

### Bài 18. Vì sao partial index có thể không dùng với generic status=$2?

**Đáp án:** generic plan không biết `$2` luôn bằng `'PENDING'`, nên không thể mặc định predicate partial index được thỏa.

### Bài 19. Viết query variant dùng partial index mà vẫn parameterize tenant

```sql
SELECT order_id, created_at
FROM skew_lab.orders
WHERE tenant_id = $1
  AND status = 'PENDING'
ORDER BY created_at DESC
LIMIT 20;
```

**Đáp án:** status là hằng nghiệp vụ của endpoint; tenant_id vẫn được bind. Planner có thể cân nhắc partial index cho PENDING.

### Bài 20. Tại sao generic plan có thể khó dùng index với `OR $1 IS NULL`?

**Đáp án:** nó phải hỗ trợ trường hợp NULL lấy mọi hàng lẫn non-NULL lọc ít hàng. Hai trường hợp có access path tối ưu rất khác nhau.

### Bài 21. Nên tách query optional filter thế nào?

**Đáp án:** một SQL riêng cho “mọi tenant”, một SQL có `tenant_id = ?` cho một tenant. Không ghép giá trị người dùng vào SQL text.

### Bài 22. `tenant_id = COALESCE($1,tenant_id)` có gì cần chú ý?

**Đáp án:** expression có thể khó dùng index, generic plan khó chuyên biệt, và với cột nullable semantics NULL không như “mọi hàng”.

### Bài 23. Một ANY array chứa tenant nóng có thể khác array chỉ chứa tenant lạnh như thế nào?

**Đáp án:** số hàng match và chi phí thực tế rất khác; generic plan không được chuyên biệt hóa theo tập giá trị mảng của từng lần gọi như custom.

### Bài 24. Vì sao mảng rất lớn có thể cần thiết kế khác?

**Đáp án:** nhiều giá trị khiến chi phí planner/executor cao; có thể dùng bảng tạm/VALUES relation/join/batch tùy scale và connection pool.

### Bài 25. Range ngắn/dài có khác plan không?

**Đáp án:** có thể. Range ngắn phù hợp index, range rộng có thể dùng Seq Scan. Custom plan có thể ước lượng theo bounds thật.

### Bài 26. Tại sao histogram hữu ích cho range queries?

**Đáp án:** nó mô tả phân bố giá trị theo khoảng, giúp ước lượng tỷ lệ hàng nằm giữa các bounds.

### Bài 27. Truy vấn hot tenant nhưng LIMIT 20 có thể dùng index không?

**Đáp án:** có. Index `(tenant_id, created_at DESC)` có thể giúp trả 20 đơn mới nhất mà không cần quét/sort tất cả 225.000 hàng.

### Bài 28. Vì sao Index Only Scan có Heap Fetches?

**Đáp án:** vì cần xác minh MVCC visibility khi heap pages chưa all-visible; index chứa đủ cột không tự đảm bảo không đọc heap.

### Bài 29. Vì sao không INCLUDE payload lớn vào mọi index?

**Đáp án:** làm index phình to và tăng chi phí ghi/maintenance, không nhất thiết mang lại lợi ích tương xứng.

### Bài 30. Một generic plan có thể tận dụng partition pruning không?

**Đáp án:** có thể, nhờ execution-time pruning trong các trường hợp PostgreSQL hỗ trợ. Tuy vậy, partitioning không tự loại bỏ skew hay nhu cầu index/stats.

### Bài 31. Có nên bật force_custom_plan toàn server?

**Đáp án:** không mặc định. Nó có thể tăng planning overhead cho những query đã chạy tốt bằng generic plan; chỉ cân nhắc phạm vi hẹp với bằng chứng.

### Bài 32. `SET LOCAL` cần được dùng thế nào trong pool?

**Đáp án:** trong transaction chứa câu query cần tác động, trên đúng connection. Setting reset khi transaction kết thúc; không dùng ngoài transaction rồi kỳ vọng nó còn cho statement sau.

### Bài 33. Vì sao hai physical connections có thể có generic/custom behavior khác nhau?

**Đáp án:** prepared statement và cache state thường thuộc session/backend; mỗi connection có lịch sử thực thi riêng.

### Bài 34. Có thể xem prepared statements toàn hệ thống qua `pg_prepared_statements` của một connection không?

**Đáp án:** không. View phản ánh prepared statements của session hiện tại, không phải danh sách toàn bộ các session.

### Bài 35. Vì sao `pg_stat_statements` không đủ để xác định tenant nóng?

**Đáp án:** nó tổng hợp các lần gọi normalized SQL, không tự lưu một bảng latency theo từng giá trị tham số của mọi request. Cần thêm metrics hoặc sample theo nhóm parameter.

### Bài 36. Khi xem `rows` vs `actual rows` khác nhau 1000 lần, bạn làm gì?

**Đáp án:** xác định loại plan, parameter hot/cold, stats freshness, MCV/extended stats, generic/custom và các điều kiện khác trước khi sửa index/cost.

### Bài 37. Một Seq Scan trên tenant nóng có chắc là bug không?

**Đáp án:** không. Nếu query trả 90% bảng, quét tuần tự có thể rẻ nhất.

### Bài 38. Một Index Scan trên tenant nóng có chắc là bug không?

**Đáp án:** cũng không. Nếu query dùng ORDER BY/LIMIT hay covering index, index path vẫn có thể tốt; cần xem EXPLAIN thực tế.

### Bài 39. EXPLAIN ANALYZE trên UPDATE có thực hiện UPDATE không?

**Đáp án:** có. Dùng trên lab và hiểu rollback/side effects; không chạy DML nguy hiểm trên production chỉ để xem plan.

### Bài 40. Lập kế hoạch tối ưu cho một endpoint nhiều tenant

**Đáp án gợi ý:**

1. Thu thập tần suất hot/cold tenant.
2. Đo cùng SQL với cả hot/cold, trước và sau warmup.
3. So force_generic vs force_custom trong lab.
4. Đọc MCV/stats; ANALYZE khi stale.
5. Xem query shape, WHERE, ORDER BY, LIMIT.
6. Tạo/điều chỉnh index dựa theo workload.
7. Xét query variants/partial index nếu hợp lý.
8. Giữ bind parameter và tenant authorization.
9. Chọn scope nhỏ cho plan_cache_mode nếu thật cần.
10. Đo p95/p99, planning overhead và write cost sau triển khai.

## 39. Quy trình lab tổng hợp: tái hiện, đo, sửa

Dưới đây là một kịch bản tổng hợp để bạn tự thực hành trên database lab.

### Bước 1. Xác nhận data skew

```sql
SELECT
    tenant_id,
    COUNT(*) AS n
FROM skew_lab.orders
WHERE tenant_id IN (1, 999)
GROUP BY tenant_id
ORDER BY tenant_id;
```

### Bước 2. Kiểm tra indexes và thống kê

```sql
SELECT
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
ORDER BY indexname;

SELECT
    most_common_vals,
    most_common_freqs,
    n_distinct
FROM pg_stats
WHERE schemaname = 'skew_lab'
  AND tablename = 'orders'
  AND attname = 'tenant_id';
```

### Bước 3. Chuẩn bị truy vấn

```sql
PREPARE skew_check(integer) AS
SELECT order_id, tenant_id, status, amount, payload
FROM skew_lab.orders
WHERE tenant_id = $1;
```

### Bước 4. So custom

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_custom_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE skew_check(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE skew_check(999);

ROLLBACK;
```

### Bước 5. So generic

```sql
BEGIN;

SET LOCAL plan_cache_mode = force_generic_plan;

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE skew_check(1);

EXPLAIN (ANALYZE, BUFFERS, SETTINGS)
EXECUTE skew_check(999);

ROLLBACK;
```

### Bước 6. Xem bộ đếm prepared plans

```sql
SELECT
    name,
    generic_plans,
    custom_plans
FROM pg_prepared_statements
WHERE name = 'skew_check';
```

### Bước 7. Đặt lại setting và cleanup

```sql
DEALLOCATE skew_check;
```

`SET LOCAL` đã tự hết hiệu lực khi transaction kết thúc. Nếu trước đó bạn đã dùng `SET` ở scope session ngoài lab này, hãy `RESET plan_cache_mode` trong đúng session đó.

### Bước 8. Ghi nhận kết quả

Lập bảng so:

| Parameter | Plan mode | Scan node | Estimated rows | Actual rows | Shared reads/hits | Planning time | Execution time |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| Hot: 1 | Custom | Tự đo | Tự đo | 225000 | Tự đo | Tự đo | Tự đo |
| Cold: 999 | Custom | Tự đo | Tự đo | 25 | Tự đo | Tự đo | Tự đo |
| Hot: 1 | Generic | Tự đo | Tự đo | 225000 | Tự đo | Tự đo | Tự đo |
| Cold: 999 | Generic | Tự đo | Tự đo | 25 | Tự đo | Tự đo | Tự đo |

Nếu kết quả của bạn không xuất hiện sự khác biệt đáng kể, điều đó vẫn có ý nghĩa: **một index, locality, cache hoặc cost model có thể làm generic đủ tốt** trên phần workload cụ thể. Đừng cố tạo kết quả “generic phải chậm” bằng cách ép config production.

## 40. Checklist trước khi triển khai thay đổi

| Câu hỏi | Cần xác minh |
| --- | --- |
| Giá trị tham số nào hot/cold? | Distribution thực và tỷ lệ calls |
| Query có thay đổi khi tenant lớn? | Số hàng, payload, pagination |
| Query được prepare ở server không? | Driver/config/session thực tế |
| Generic hay custom đang dùng? | EXPLAIN, plan_cache_mode, session counters |
| Có MCV cho giá trị hot không? | `pg_stats` sau ANALYZE |
| Statistics có stale không? | Bulk load/update/autovacuum |
| Có phụ thuộc giữa nhiều cột? | Extended stats phù hợp |
| Predicate có dễ dùng index? | Tránh cast/expression làm mất path |
| Có composite index cho query chính? | Tenant + status/time theo workload |
| Partial index có predicate phù hợp generic? | Hằng nghiệp vụ hay tham số chưa biết |
| Có optional filter với OR/COALESCE? | Thử query variants |
| Có ANY array size rất khác nhau? | Test mảng nhỏ/lớn/đầy hot IDs |
| Range thời gian có độ rộng khác nhau? | Test ngắn/dài |
| Có ORDER BY + LIMIT? | B-tree theo thứ tự phù hợp |
| Có Index Only Scan với Heap Fetches cao? | Visibility/VACUUM |
| Có partitioning/pruning không? | Plan-time vs execution-time |
| Có query trả quá nhiều hàng? | Pagination/aggregation/streaming |
| Có khác biệt p95/p99 giữa tenant groups? | Metrics app |
| `pg_stat_statements` có che tham số? | Phân nhóm workload |
| Đã so planning time chưa? | Tránh force custom không đáng |
| Có index thêm làm write chậm? | Đo DML/WAL/storage |
| Có connection pool/session state? | Không rò `SET`/PREPARE |
| Có dùng SET LOCAL đúng transaction? | Không lệch scope |
| Có test JDBC driver version/config? | Không dựa vào giả định threshold |
| Có rủi ro SQL injection? | Giữ binds |
| Tenant authorization còn đúng? | Không bỏ lọc bảo mật |
| Có kế hoạch đo lại sau deploy? | Theo dõi latency/plan regression |
| Có rollback cấu hình/index change? | Vận hành có kiểm soát |
| Có đo concurrency thật? | Tránh kết luận từ một kết nối |
| Có ghi rõ nguồn dữ liệu đo? | Phiên bản, schema, index, buffer state |

## 41. Tổng kết

**Truy vấn tham số hóa** là cách thiết kế ứng dụng tốt, nhưng khi dữ liệu phân bố lệch mạnh, một câu SQL với cùng cấu trúc có thể cần **những kế hoạch rất khác nhau** cho các giá trị tham số.

Các điểm quan trọng:

1. **Data skew:** một giá trị có thể match 90% bảng, trong khi giá trị khác match 0,01%. Một index scan không tự tốt cho cả hai.
2. **Parameter binding khác plan caching:** JDBC `PreparedStatement` không đồng nghĩa server chắc chắn dùng generic plan.
3. **Custom plan:** có thể xét giá trị tham số của lần thực thi, giúp chọn access path theo selectivity cụ thể; đổi lại có planning overhead.
4. **Generic plan:** tái sử dụng một dạng plan cho nhiều giá trị, giúp giảm planning overhead nhưng có thể kém khi parameter selectivity lệch mạnh.
5. **`plan_cache_mode`:** dùng `auto` làm điểm xuất phát; `force_custom_plan` và `force_generic_plan` là công cụ so sánh/điều chỉnh có kiểm soát.
6. **`PREPARE/EXECUTE` + `EXPLAIN ANALYZE BUFFERS`:** cách chuẩn để tái hiện vấn đề trên database lab với parameter hot/cold.
7. **`pg_prepared_statements`:** giúp quan sát prepared statement và counters generic/custom trong session hiện tại; không phải view toàn hệ thống.
8. **`ANALYZE` / `pg_stats`:** MCV, frequencies, histogram và correlation giúp planner ước lượng phân bố. Stats tốt không làm generic plan biết `$1` ở lần thực thi.
9. **Extended statistics:** hữu ích khi predicates nhiều cột có quan hệ phụ thuộc, nhưng không thay thế hiểu custom/generic.
10. **Index design:** index thường, composite, partial và covering indexes giải quyết những query patterns khác nhau; không có một index tốt nhất cho mọi trường hợp.
11. **Partial index:** generic query có tham số ở predicate quyết định membership có thể không sử dụng được partial index. Một **query variant với hằng nghiệp vụ** vẫn có thể bind những dữ liệu đầu vào khác.
12. **Optional filters và arrays:** một SQL quá đa dụng dễ khiến generic plan khó tối ưu. Khi hợp lý, tách query shapes với binding an toàn.
13. **ORDER BY LIMIT:** có thể làm một index plan tốt cho cả tenant nóng và lạnh dù số hàng tổng rất khác nhau.
14. **Partitioning:** có thể giúp pruning nhưng không tự xóa mọi chi phí do skew hoặc generic planning.
15. **Đo lường:** phải xem estimate/actual rows, buffers, planning/execution time, p95/p99, số lượng rows trả về và workload theo nhóm tham số.
16. **Ứng dụng:** luôn giữ parameter binding, kiểm soát connection pool/session state và bảo vệ quyền truy cập tenant.

Mẫu thực hành cốt lõi:

```sql
PREPARE q(integer) AS
SELECT order_id, amount, payload
FROM skew_lab.orders
WHERE tenant_id = $1;

BEGIN;
SET LOCAL plan_cache_mode = force_custom_plan;
EXPLAIN (ANALYZE, BUFFERS) EXECUTE q(1);
EXPLAIN (ANALYZE, BUFFERS) EXECUTE q(999);
ROLLBACK;

BEGIN;
SET LOCAL plan_cache_mode = force_generic_plan;
EXPLAIN (ANALYZE, BUFFERS) EXECUTE q(1);
EXPLAIN (ANALYZE, BUFFERS) EXECUTE q(999);
ROLLBACK;

DEALLOCATE q;
```

**Quy tắc cốt lõi:** khi một truy vấn tham số hóa “lúc nhanh lúc chậm”, đừng chỉ hỏi **“SQL có index chưa?”**. Hãy hỏi thêm **“những giá trị nào phổ biến, planner đã biết phân bố đến đâu, đang dùng custom hay generic plan, và kế hoạch nào phù hợp với từng nhóm parameter?”**. Đó là nền tảng để tối ưu truy vấn tham số hóa an toàn, có thể đo lường và bền vững trong PostgreSQL.
