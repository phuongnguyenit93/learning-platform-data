# Rules, cơ chế viết lại truy vấn và ranh giới sử dụng trong PostgreSQL

## 1. Một câu SQL có thể không phải câu lệnh mà PostgreSQL thực thi trực tiếp

Khi ứng dụng gửi:

```sql
SELECT *
FROM sales.active_products;
```

ta có thể nghĩ PostgreSQL chỉ đọc một bảng tên `active_products`. Nhưng nếu `active_products` là **view**, PostgreSQL có thể mở rộng định nghĩa view thành truy vấn trên một hoặc nhiều bảng gốc. Một phần quan trọng của quá trình này dựa trên **query rewrite rules**.

Tương tự, PostgreSQL cho phép khai báo:

```sql
CREATE RULE ... AS ON INSERT TO ...
DO ALSO ...;
```

hoặc:

```sql
CREATE RULE ... AS ON DELETE TO ...
DO INSTEAD NOTHING;
```

Hai cơ chế trên có thể làm câu lệnh đầu vào được **bổ sung, thay thế hoặc bỏ qua** trước khi chuyển sang bước lập kế hoạch và thực thi.

Nhưng cần nhớ ngay từ đầu:

> **Rule không phải trigger chạy một lần cho từng hàng.** Rule thuộc hệ thống **viết lại cây truy vấn** của PostgreSQL. Khi yêu cầu xử lý hàng mới/hàng cũ, kiểm tra ràng buộc, ghi audit chính xác hoặc phát sự kiện nghiệp vụ, trigger và constraint thường là lựa chọn phù hợp hơn.

Bài này tập trung vào ba câu hỏi:

1. Rule thực chất là gì và PostgreSQL viết lại truy vấn ở giai đoạn nào?
2. `DO ALSO`, `DO INSTEAD`, `DO INSTEAD NOTHING`, `OLD` và `NEW` hoạt động thế nào?
3. Ranh giới nào khiến ta nên dùng **view, trigger, constraint, RLS, transaction hoặc outbox** thay vì tự viết rule?

### Kết quả học tập

Sau khi hoàn thành, bạn có thể:

- Giải thích pipeline parser/analyzer → rewriter → planner → executor.
- Đọc cú pháp `CREATE RULE` và phân biệt sự kiện `SELECT`, `INSERT`, `UPDATE`, `DELETE`.
- Mô tả cách view được thực hiện qua rule `_RETURN`.
- Phân biệt `DO ALSO`, `DO INSTEAD` và `DO INSTEAD NOTHING`.
- Hiểu `OLD`/`NEW` của rules là **pseudo-relations trong query rewrite**, không giống record variables của row-level trigger.
- Đọc một câu SQL gốc và suy ra có những hành động nào được sinh ra sau rewrite.
- Tạo lab an toàn cho rule bổ sung lệnh, thay thế lệnh và chặn lệnh.
- Hiểu vì sao rule trên nhiều hàng, biểu thức volatile và `RETURNING` cần được xử lý cẩn thận.
- Nắm các giới hạn như `INSERT ... ON CONFLICT`, `COPY FROM` và `TRUNCATE`.
- Phân biệt view tự cập nhật được, `INSTEAD OF` trigger và `INSTEAD` rule.
- Kiểm tra rule qua `pg_rewrite`, `pg_rules` và `pg_get_ruledef`.
- Đánh giá tác động về concurrency, performance, bảo mật, audit và migration.
- Chọn đúng công cụ trong những tình huống nghiệp vụ phổ biến.

---

## 2. Rule trong PostgreSQL là gì?

**Rule**, trong phạm vi bài này, là quy tắc thuộc **Query Rewrite System** của PostgreSQL, được khai báo bằng `CREATE RULE`.

Nó liên kết với một **quan hệ đích** (*relation*) và một **loại sự kiện SQL**. Khi PostgreSQL phân tích một câu lệnh có liên quan đến quan hệ đó, hệ thống rewrite có thể biến đổi cây truy vấn trước khi planner và executor làm việc.

Định nghĩa đơn giản:

```text
Câu lệnh SQL đầu vào
       |
       v
Cây truy vấn đã phân tích
       |
       v
Các rewrite rules phù hợp
       |
       v
Một hoặc nhiều cây truy vấn sau rewrite
       |
       v
Planner tối ưu các cây truy vấn đó
       |
       v
Executor thực thi kế hoạch
```

Ví dụ tư duy:

```text
DELETE FROM protected_rows WHERE id = 10
       |
       v
Rule: ON DELETE DO INSTEAD NOTHING
       |
       v
Không còn hành động DELETE tương ứng để thực thi
```

Hoặc:

```text
INSERT INTO orders ...
       |
       v
Rule: ON INSERT DO ALSO INSERT INTO audit ...
       |
       v
Lệnh gốc + lệnh audit do rewriter tạo
```

Hai cách viết này **không tương đương** với việc một trigger procedural được gọi mỗi khi một hàng thay đổi.

### 2.1. Rule có phải SQL chuẩn phổ quát không?

Cú pháp `CREATE RULE` ở đây là tính năng cụ thể của PostgreSQL. Không nên giả định một database engine khác hỗ trợ tương tự hoặc có cùng semantics.

### 2.2. Rule có phải quy tắc nghiệp vụ không?

Tên “rule” rất dễ khiến người mới hiểu nhầm thành “business rule” hay “validation rule”.

Trong PostgreSQL:

- `CREATE RULE`: **biến đổi câu lệnh SQL**.
- `CHECK`, `NOT NULL`, `UNIQUE`, `FOREIGN KEY`: **ràng buộc dữ liệu**.
- `CREATE TRIGGER`: **kích hoạt hành vi** tại thời điểm phù hợp với hoạt động trên bảng/view.
- Row Level Security: **kiểm soát hàng nào một role được phép truy cập hoặc thay đổi**.
- Quy tắc nghiệp vụ ở service: **logic miền nghiệp vụ và giao thức ứng dụng**.

Chúng có thể phối hợp nhưng không nên đánh đồng.

## 3. PostgreSQL xử lý câu SQL qua những giai đoạn nào?

Một mô hình tư duy đủ thực tế:

<escape>1.</escape> **Parse:** nhận văn bản SQL và xây cấu trúc cú pháp.

<escape>2.</escape> **Analyze:** phân giải tên bảng/cột, kiểu dữ liệu, biểu thức, quyền và ngữ nghĩa liên quan để tạo cấu trúc truy vấn phù hợp.

<escape>3.</escape> **Rewrite:** áp dụng các query rewrite rules; view expansion là trường hợp đặc biệt quan trọng.

<escape>4.</escape> **Plan/Optimize:** chọn chiến lược thực thi, thứ tự join, index scan, seq scan, sort, aggregate và các kế hoạch cần thiết.

<escape>5.</escape> **Execute:** thực thi các kế hoạch, đọc/ghi tuple, quản lý MVCC và phát kết quả.

Sơ đồ:

```text
SQL text
   |
   v
Parser
   |
   v
Analyzer / Query Tree
   |
   v
Rewriter <------ pg_rewrite
   |
   +---- SELECT view -> query trên bảng gốc
   |
   +---- DML rule -> bổ sung/thay thế query
   |
   v
Planner
   |
   v
Execution Plan
   |
   v
Executor
   |
   v
Kết quả / thay đổi dữ liệu
```

### 3.1. Rewrite khác optimization

Rewriter điều chỉnh **cấu trúc/ý nghĩa logic của truy vấn theo rules**. Planner chọn **cách thực hiện hiệu quả** những truy vấn sau rewrite.

Một rule không phải câu lệnh hướng dẫn planner “dùng index A”, “join bảng B trước”, hoặc “chạy nhanh hơn”.

### 3.2. Rewrite không phải chạy một vòng lặp trên từng hàng

Với câu:

```sql
UPDATE some_table
SET status = 'ARCHIVED'
WHERE created_at < DATE '2025-01-01';
```

rule được xét trên **câu lệnh và cây truy vấn**. Không thể suy luận:

```text
Cứ mỗi hàng cập nhật
    -> chạy nguyên khối rule một lần
```

Đây là mô hình của một số **row-level trigger**, không phải cơ chế cơ bản của query rewrite rules.

### 3.3. Vì sao khác biệt này quan trọng?

Nếu một ứng dụng cần audit **chính xác mỗi hàng đã thực sự bị INSERT/UPDATE/DELETE**, thì quy tắc theo câu lệnh có thể khiến kỳ vọng sai trong các tình huống:

- Multi-row DML.
- INSERT từ SELECT.
- DEFAULT hoặc biểu thức volatile.
- Statement bị constraint từ chối.
- RETURNING và upsert.
- Dữ liệu bị lọc theo join/condition khi rewrite.

Do đó không chọn `CREATE RULE` cho per-row audit chỉ vì nó có `OLD` và `NEW`.

## 4. Cú pháp CREATE RULE

Cấu trúc khái quát:

```sql
CREATE [ OR REPLACE ] RULE rule_name AS
ON event TO table_name
[ WHERE condition ]
DO [ ALSO | INSTEAD ]
{
    NOTHING
    | command
    | ( command; command; ... )
};
```

Trong đó:

- `rule_name`: tên quy tắc trên quan hệ đích.
- `event`: sự kiện `SELECT`, `INSERT`, `UPDATE` hoặc `DELETE`.
- `table_name`: relation đích của rule.
- `WHERE condition`: điều kiện tùy chọn để áp dụng rule.
- `DO ALSO`: giữ tác vụ gốc và thêm action.
- `DO INSTEAD`: dùng action thay thế tác vụ gốc khi rule phù hợp.
- `DO INSTEAD NOTHING`: thay thế bằng không thực hiện hành động nào.
- `command`: các hành động SQL được phép bởi hệ thống rewrite.

### 4.1. Quy tắc đặt tên

Tên rule nên phản ánh hành vi:

```text
audit_order_insert
prevent_delete
route_insert
_RETURN
```

Tên `_RETURN` có ý nghĩa đặc biệt với rule SELECT của view. Không dùng tên tùy tiện thay `_RETURN` khi tạo SELECT rule dành cho view.

### 4.2. DO ALSO là ngầm định khi không viết ALSO/INSTEAD

Nếu bỏ từ khóa `ALSO`/`INSTEAD`, hành vi mặc định thuộc nhánh `ALSO` trong cú pháp này. Tuy nhiên nên **viết tường minh `DO ALSO`** để người đọc không hiểu nhầm tác vụ gốc bị thay thế.

### 4.3. Rule thuộc về relation nào?

Rule được định nghĩa trên một relation cụ thể. Quyền tạo rule phụ thuộc quyền sở hữu/quyền DDL của đối tượng. Không thể tùy tiện cài rule lên bảng của người khác chỉ vì có quyền SELECT/UPDATE dữ liệu.

## 5. Bốn loại sự kiện: SELECT, INSERT, UPDATE, DELETE

| Event | Vai trò thường gặp | Ghi chú |
|---|---|---|
| `ON SELECT` | Định nghĩa việc đọc qua view | Có những yêu cầu đặc biệt về `_RETURN`, unconditional INSTEAD |
| `ON INSERT` | Viết lại thao tác thêm hàng | Dễ gây tương tác khó với defaults, RETURNING, ON CONFLICT |
| `ON UPDATE` | Viết lại thao tác sửa hàng | `OLD`/`NEW` cần hiểu ở query level |
| `ON DELETE` | Viết lại thao tác xóa hàng | Có thể chặn bằng DO INSTEAD NOTHING nhưng không thay policy/constraints |

### 5.1. Không có ON TRUNCATE rule

Không thể coi `TRUNCATE` là một dạng `DELETE` được rewrite bởi `ON DELETE` rule.

Nếu cần kiểm soát TRUNCATE:

- Thu hồi quyền TRUNCATE đối với role không được phép.
- Dùng chính sách quản trị/DDL.
- Khi cần hành vi trigger theo TRUNCATE, xem loại trigger tương ứng.
- Cân nhắc không cho role ứng dụng thực thi các thao tác phá hủy hàng loạt.

### 5.2. Không có rule dành riêng cho SELECT FOR UPDATE

Một query có thể mang nhiều đặc điểm, nhưng rule event vẫn là những loại được PostgreSQL hỗ trợ. Đừng tạo ý niệm “ON SELECT FOR UPDATE DO...” như một event tùy ý.

## 6. DO ALSO, DO INSTEAD và NOTHING

Hãy so sánh bằng bảng:

| Cú pháp | Tác vụ gốc | Hành động bổ sung/thay thế |
|---|---|---|
| `DO ALSO command` | Giữ lại | Thêm command |
| `DO INSTEAD command` | Bị thay thế theo semantics của rule | Thực thi command thay thế |
| `DO INSTEAD NOTHING` | Bị thay thế | Không thêm command |
| `DO ALSO NOTHING` | Giữ lại | Không có hành động hữu ích bổ sung |

### 6.1. DO ALSO không đồng nghĩa “chạy action sau khi lệnh gốc thành công”

Rule sinh ra **những câu truy vấn ở tầng rewrite**. Nó không phải callback AFTER INSERT/UPDATE/DELETE với một biến OLD/NEW của từng hàng sau khi hàng đã tồn tại ở trạng thái cuối.

Nếu hành động của rule dùng để tạo audit log hoặc gửi thông báo, bạn phải xét thứ tự, dữ liệu thực sự bị thay đổi, tính lặp lại và các giới hạn của hệ thống rewrite. Thông thường **AFTER trigger** phù hợp hơn.

### 6.2. DO INSTEAD không đồng nghĩa “ngăn mọi cách chỉnh dữ liệu”

Ví dụ rule chặn DELETE không ngăn được:

- Role đủ quyền thay/xóa rule.
- Một thao tác `TRUNCATE` được cấp quyền.
- Dữ liệu bị thay đổi qua đường khác hoặc DDL phù hợp.
- Những đường viết khác mà thiết kế không bao phủ.

Nếu đó là yêu cầu bảo vệ dữ liệu quan trọng, cần kết hợp permissions, constraints, RLS, triggers và quy trình vận hành.

## 7. Lab có kiểm soát: tạo schema riêng cho Rules

Toàn bộ ví dụ nhằm minh họa, chỉ chạy trong database thực hành.

```sql
CREATE SCHEMA IF NOT EXISTS rule375;
```

Tạo bảng sản phẩm:

```sql
CREATE TABLE rule375.products (
    product_id integer PRIMARY KEY,
    product_name text NOT NULL,
    category text NOT NULL DEFAULT 'general',
    unit_price numeric(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Chèn dữ liệu:

```sql
INSERT INTO rule375.products(
    product_id,
    product_name,
    category,
    unit_price,
    is_active
)
VALUES
    (101, 'Cà phê rang mộc', 'coffee', 120000, true),
    (102, 'Phin inox', 'equipment', 85000, true),
    (103, 'Máy xay mini', 'equipment', 750000, false),
    (104, 'Giấy lọc', 'accessory', 45000, true),
    (105, 'Hạt thử nghiệm', 'coffee', 90000, false);
```

Kiểm tra:

```sql
SELECT
    product_id,
    product_name,
    category,
    unit_price,
    is_active
FROM rule375.products
ORDER BY product_id;
```

Kỳ vọng: 5 sản phẩm, trong đó 101/102/104 active.

## 8. View: trường hợp sử dụng query rewrite phổ biến nhất

Tạo view chỉ có sản phẩm active:

```sql
CREATE VIEW rule375.active_products AS
SELECT
    product_id,
    product_name,
    category,
    unit_price,
    is_active
FROM rule375.products
WHERE is_active;
```

Truy vấn:

```sql
SELECT
    product_id,
    product_name,
    unit_price
FROM rule375.active_products
WHERE unit_price >= 80000
ORDER BY product_id;
```

Kết quả kỳ vọng:

| product_id | product_name | unit_price |
|---:|---|---:|
| 101 | Cà phê rang mộc | 120000.00 |
| 102 | Phin inox | 85000.00 |

### 8.1. Dữ liệu view ở đâu?

Một view thông thường **không lưu tập hàng riêng**. PostgreSQL lưu định nghĩa truy vấn và mở rộng view thông qua cơ chế rewrite.

Suy nghĩ gần đúng:

```sql
SELECT product_id, product_name, unit_price
FROM (
    SELECT
        product_id,
        product_name,
        category,
        unit_price,
        is_active
    FROM rule375.products
    WHERE is_active
) AS active_products
WHERE unit_price >= 80000
ORDER BY product_id;
```

Đây là **mô hình diễn giải logic**, không phải cam kết PostgreSQL luôn tạo nguyên văn subquery này rồi thực thi nó như một bảng tạm.

Planner có thể gộp/đẩy điều kiện và tối ưu khác tùy ngữ nghĩa view.

### 8.2. View bình thường khác materialized view

- View: thường đọc dữ liệu gốc khi truy vấn, không tự lưu từng hàng kết quả.
- Materialized view: lưu kết quả vật lý khi tạo/refresh, cần cơ chế cập nhật/refresh thích hợp.

Không nhìn từ `SELECT * FROM view` mà tự kết luận dữ liệu đã được cache trên disk.

## 9. Rule _RETURN gắn với view

Khi `CREATE VIEW` một view thông thường, PostgreSQL lưu định nghĩa thông qua một **ON SELECT DO INSTEAD** rewrite rule đặc biệt có tên `_RETURN`.

Ý tưởng:

```text
SELECT FROM rule375.active_products
          |
          v
Rule _RETURN của active_products
          |
          v
Cây query định nghĩa view:
  SELECT ... FROM rule375.products
  WHERE is_active
          |
          v
Planner tối ưu toàn bộ truy vấn sau rewrite
```

### 9.1. Vì sao dùng CREATE VIEW thay vì tự tạo _RETURN?

`CREATE VIEW` diễn đạt trực tiếp ý đồ tạo một giao diện đọc dữ liệu:

- Dễ hiểu.
- Có cú pháp column aliases, security options, CHECK OPTION khi phù hợp.
- Phụ thuộc đối tượng được catalog quản lý.
- Không cần người dùng tự xây SELECT rule đặc biệt.
- Có hành vi tự cập nhật cho một số view đơn giản.

**Thực hành khuyến nghị:** khi mục tiêu là định nghĩa một view, hãy dùng `CREATE VIEW`/`CREATE OR REPLACE VIEW` thay vì tự tạo rule `_RETURN`.

### 9.2. Không tự đặt tên rule SELECT tùy ý

PostgreSQL có yêu cầu đặc biệt cho rules `ON SELECT`: chúng phải có hình thức phù hợp với view rewrite, bao gồm tên đặc biệt `_RETURN` và action/điều kiện được giới hạn. Chúng không phải nơi để cài một “SELECT audit rule” chạy tùy ý mỗi lần có người đọc bảng.

## 10. Xem view definition và rewrite metadata

Có thể xem định nghĩa view:

```sql
SELECT pg_get_viewdef(
    'rule375.active_products'::regclass,
    true
);
```

Hoặc dùng catalog view:

```sql
SELECT
    schemaname,
    viewname,
    definition
FROM pg_views
WHERE schemaname = 'rule375'
  AND viewname = 'active_products';
```

### 10.1. Xem pg_rewrite

`pg_rewrite` là catalog lưu thông tin của query rewrite rules.

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    r.rulename,
    r.ev_type,
    r.is_instead,
    pg_get_ruledef(r.oid, true) AS rule_definition
FROM pg_rewrite AS r
JOIN pg_class AS c
    ON c.oid = r.ev_class
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'rule375'
ORDER BY c.relname, r.rulename;
```

Kỳ vọng thấy rule `_RETURN` gắn với `active_products` cùng những rules khác nếu bạn đã tạo trong lab.

### 10.2. pg_rules là view đọc rule dễ hơn

```sql
SELECT
    schemaname,
    tablename,
    rulename,
    definition
FROM pg_rules
WHERE schemaname = 'rule375'
ORDER BY tablename, rulename;
```

**Lưu ý:** `pg_rules` là một view tiện ích, không nhất thiết liệt kê mọi `_RETURN` rule của views theo cách bạn tưởng. Khi cần xem raw metadata của view rules, tra `pg_rewrite` và `pg_get_viewdef`.

### 10.3. Những tên cột catalog hữu ích

| Catalog field | Vai trò |
|---|---|
| `ev_class` | OID của relation có rule |
| `rulename` | Tên rule |
| `ev_type` | Loại sự kiện |
| `is_instead` | Có phải rule thay thế không |
| `ev_qual` | Biểu thức điều kiện dạng internal representation |
| `ev_action` | Query action dạng internal representation |
| `ev_enabled` | Trạng thái enable theo cơ chế rule |

Để đọc câu SQL dễ hiểu, dùng `pg_get_ruledef` thay vì tự phân tích `pg_node_tree` thành văn bản theo phỏng đoán.

## 11. EXPLAIN cho truy vấn trên view

Truy vấn:

```sql
EXPLAIN (VERBOSE, COSTS OFF)
SELECT
    product_id,
    product_name
FROM rule375.active_products
WHERE unit_price >= 80000;
```

Trong kế hoạch, bạn thường sẽ thấy thao tác đọc dữ liệu trên bảng gốc `rule375.products` và các filter phù hợp.

### 11.1. Có cần nhìn thấy tên _RETURN trong EXPLAIN không?

Không. `EXPLAIN` trình bày **kế hoạch sau rewrite/optimization** chứ không phải một nhật ký đầy đủ liệt kê từng phép rewrite rule.

Nếu plan đọc `products`, đó là điều phù hợp vì view dựa trên bảng `products`. Muốn kiểm tra định nghĩa rule, dùng catalog.

### 11.2. View không mặc nhiên làm query chậm hơn

Một view đơn giản thường được planner tối ưu cùng phần SQL bên ngoài. Không thể kết luận view luôn gây thêm một lần full scan hoặc một bảng tạm.

Tuy nhiên các cấu trúc view phức tạp, bảo mật, aggregate, LIMIT, DISTINCT, window functions và những đặc điểm khác có thể hạn chế khả năng pushdown/flattening. Hãy đo plan thực tế.

## 12. View tự cập nhật được: không nhất thiết cần rule tự viết

Một số view PostgreSQL được **automatically updatable** khi đáp ứng yêu cầu, ví dụ view đơn giản dựa trên một bảng, không có những cấu trúc khiến việc ánh xạ DML trở nên mơ hồ.

Ta có:

```sql
CREATE VIEW rule375.editable_active_products AS
SELECT
    product_id,
    product_name,
    category,
    unit_price,
    is_active
FROM rule375.products
WHERE is_active;
```

Với view này, PostgreSQL có thể tự thực hiện các lệnh INSERT/UPDATE/DELETE hợp lệ bằng cách ánh xạ sang bảng gốc, không cần bạn tự viết một `ON UPDATE DO INSTEAD` rule.

### 12.1. Điều gì xảy ra nếu UPDATE một hàng để nó không còn thỏa view?

Nếu không có `CHECK OPTION`:

```sql
UPDATE rule375.editable_active_products
SET is_active = false
WHERE product_id = 104;
```

Câu lệnh có thể cập nhật hàng gốc 104, và sau đó hàng ấy **biến mất khỏi kết quả view** vì `is_active=false`.

Đây không nhất thiết là lỗi PostgreSQL: view là bộ lọc đọc, không tự động là constraint về những hàng sau UPDATE.

### 12.2. Chọn test riêng hoặc khôi phục fixture

Nếu chạy câu UPDATE trên, muốn các ví dụ sau giữ dữ liệu ban đầu:

```sql
UPDATE rule375.products
SET is_active = true
WHERE product_id = 104;
```

Không chạy lặp lại các lệnh DML tác động dữ liệu lab rồi coi mọi kết quả mẫu vẫn như ban đầu.

## 13. WITH CHECK OPTION cho view tự cập nhật

Nếu muốn những hàng tạo/sửa qua view phải tiếp tục thỏa điều kiện của view, có thể dùng:

```sql
CREATE VIEW rule375.checked_active_products AS
SELECT
    product_id,
    product_name,
    category,
    unit_price,
    is_active
FROM rule375.products
WHERE is_active
WITH LOCAL CHECK OPTION;
```

Giờ thử:

```sql
-- Chủ đích lỗi: hàng sau UPDATE không còn thỏa view.
UPDATE rule375.checked_active_products
SET is_active = false
WHERE product_id = 101;
```

PostgreSQL dự kiến từ chối vì hàng mới không còn thuộc tập mà view cho phép, theo `CHECK OPTION`.

### 13.1. LOCAL và CASCADED

- `LOCAL CHECK OPTION`: kiểm tra điều kiện view hiện tại theo ngữ nghĩa được PostgreSQL quy định.
- `CASCADED CHECK OPTION`: trong những chuỗi view tự cập nhật được, có thể kiểm tra thêm điều kiện của những view nền thích hợp.

Cần xem điều kiện và giới hạn khi một view trong chuỗi được cập nhật qua rule/trigger. Không giả định CHECK OPTION luôn đi qua một `INSTEAD` rule hoặc `INSTEAD OF` trigger như với view tự cập nhật thuần.

### 13.2. CHECK OPTION không thay CHECK constraint trên bảng

Một đường ghi trực tiếp vào `rule375.products` không đi qua view checked. Nếu quy tắc “mọi sản phẩm đều phải active” là invariant toàn bảng, view CHECK OPTION không đủ; phải dùng constraint/mô hình dữ liệu tương ứng.

### 13.3. View tự cập nhật không dành cho mọi SELECT

Nếu view có nhiều join, aggregate, DISTINCT hoặc cấu trúc phức tạp, nó có thể không tự cập nhật được. Khi thực sự cần cho phép ghi qua view, `INSTEAD OF` trigger thường dễ kiểm soát hơn custom DML rule.

## 14. Tạo rule DO ALSO cho một INSERT đơn giản

Để xem cách một rule có thể bổ sung hành động, ta dùng bảng ví dụ tách riêng khỏi sản phẩm.

```sql
CREATE TABLE rule375.requests (
    request_id integer PRIMARY KEY,
    request_title text NOT NULL
);

CREATE TABLE rule375.request_rule_log (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id integer NOT NULL,
    event_name text NOT NULL,
    logged_at timestamptz NOT NULL DEFAULT now()
);
```

Tạo rule:

```sql
CREATE RULE requests_insert_log AS
ON INSERT TO rule375.requests
DO ALSO
    INSERT INTO rule375.request_rule_log(
        request_id,
        event_name
    )
    VALUES (
        NEW.request_id,
        'INSERT'
    );
```

Chạy một lệnh INSERT đơn giản:

```sql
INSERT INTO rule375.requests(request_id, request_title)
VALUES (1, 'Request đầu tiên');
```

Kiểm tra:

```sql
SELECT *
FROM rule375.requests
ORDER BY request_id;

SELECT
    request_id,
    event_name
FROM rule375.request_rule_log
ORDER BY log_id;
```

Trong ví dụ đơn giản này, bạn sẽ thấy bản ghi request và bản ghi log tương ứng nếu transaction thành công.

### 14.1. Đây không phải đề xuất triển khai audit production

Mục tiêu lab là thấy rõ **DO ALSO bổ sung query**.

Đừng sao chép rule này để xây hệ thống audit bắt buộc theo từng hàng khi chưa hiểu:

- Multi-row INSERT.
- `INSERT ... SELECT`.
- Expressions có side effects.
- `RETURNING` và upsert.
- Biểu thức `NEW` được viết lại như thế nào.
- Giao diện lỗi và các đường ghi đặc biệt.
- Những thay đổi DML khác ngoài INSERT.

Đối với audit từng hàng **đã được thay đổi**, trigger thường phù hợp hơn.

## 15. OLD và NEW trong rule là gì?

Rule có thể tham chiếu những pseudo-relations:

```sql
OLD.column_name
NEW.column_name
```

Vai trò tùy sự kiện:

- `INSERT`: có thể tham chiếu `NEW` cho giá trị mới.
- `UPDATE`: có thể tham chiếu `OLD` và `NEW`.
- `DELETE`: có thể tham chiếu `OLD` cho giá trị cũ.

Ví dụ:

```sql
VALUES (NEW.request_id, 'INSERT')
```

trong INSERT rule ở phần trước.

### 15.1. OLD/NEW của rule không phải một biến record trong PL/pgSQL

Trong row-level trigger:

```sql
NEW.request_id
```

là trường của record chứa hàng hiện hành, được truy cập trong function trigger vào thời điểm tương ứng.

Trong rule:

```sql
NEW.request_id
```

là cú pháp được **query rewriter** xử lý trong một cây SQL. Nó không tạo một PL/pgSQL loop chạy trên mọi row và không cung cấp những biến trigger như `TG_OP`, `TG_TABLE_NAME` hay `TG_WHEN`.

### 15.2. Vì sao hai cơ chế có cùng tên OLD/NEW?

Vì cả hai liên quan dữ liệu trước/sau một thao tác. Nhưng **phạm vi, thời điểm và cách đánh giá** của chúng khác nhau.

Đây là một trong những nguyên nhân gây lỗi thiết kế lớn nhất khi người mới chuyển từ trigger sang rule.

## 16. Rule được áp dụng theo câu lệnh, không phải per-row callback

Giả sử một UPDATE sửa 1.000 hàng:

```sql
UPDATE rule375.products
SET unit_price = unit_price * 1.05
WHERE category = 'coffee';
```

Một row-level UPDATE trigger có thể được gọi cho từng hàng bị cập nhật theo quy tắc trigger.

Một rewrite rule `ON UPDATE` làm thay đổi **query tree** cho UPDATE đó. Trong các tình huống phức tạp, rewriter tạo thêm query/action mà planner/executor xử lý trên những tập hàng phù hợp.

Vì vậy không lập luận:

```text
ON UPDATE rule
   = 1000 lần gọi procedure xử lý hàng
```

Cơ chế ấy không đúng.

### 16.1. Multi-row operations là điểm cần thử nghiệm

Một rule nhìn hợp lý với:

```sql
INSERT INTO rule375.requests VALUES (2, 'A');
```

chưa chắc có semantics mong muốn cho:

```sql
INSERT INTO rule375.requests
SELECT ...
FROM another_table;
```

hoặc:

```sql
INSERT INTO rule375.requests
VALUES (3, 'B'), (4, 'C'), (5, 'D');
```

Nhiều thao tác ghi trong SQL là **set-based**; các phép biến đổi biểu thức và hành động bổ sung ở tầng rule có thể khác suy luận “mỗi hàng gọi một lần”.

### 16.2. Không dùng rule để gọi external API một lần trên mỗi hàng

Nếu nhiệm vụ là gửi email, HTTP request hay phát sự kiện đến Kafka khi mỗi hàng được commit, rule không phải một hook ổn định để thực thi side effects ngoài database.

Thiết kế tốt hơn có thể là:

- Trigger ghi bản ghi outbox trong cùng transaction.
- Worker độc lập đọc outbox sau commit.
- Consumer idempotent, retry và xử lý lỗi.

## 17. DO INSTEAD NOTHING: chặn một loại DML trong lab

Tạo bảng riêng:

```sql
CREATE TABLE rule375.protected_notes (
    note_id integer PRIMARY KEY,
    note_text text NOT NULL
);

INSERT INTO rule375.protected_notes(note_id, note_text)
VALUES
    (1, 'Giữ lại tài liệu A'),
    (2, 'Giữ lại tài liệu B');
```

Tạo rule:

```sql
CREATE RULE protected_notes_no_delete AS
ON DELETE TO rule375.protected_notes
DO INSTEAD NOTHING;
```

Thử:

```sql
DELETE FROM rule375.protected_notes
WHERE note_id = 1;
```

Sau đó:

```sql
SELECT note_id, note_text
FROM rule375.protected_notes
ORDER BY note_id;
```

Nếu rule đang được kích hoạt theo điều kiện ví dụ, cả hai hàng vẫn tồn tại.

### 17.1. Một DELETE có thể báo 0 hàng bị tác động

Khi rule thay DELETE bằng NOTHING, executor không thực hiện DELETE gốc. Đừng tin rằng chỉ vì client gửi DELETE và không nhận exception thì dữ liệu đã bị xóa.

Kiểm tra result/command tag hoặc câu SELECT sau đó tùy giao diện driver và tác vụ.

### 17.2. Vì sao rule này không phải “chống xóa tuyệt đối”?

Nó chỉ điều chỉnh **DELETE event** theo cơ chế rule. Các vấn đề còn lại:

- Role có quyền `TRUNCATE` có thể dùng loại thao tác khác.
- Owner/DBA có thể thay hoặc drop rule.
- Có thể có DDL khác làm dữ liệu mất.
- Một luồng UPDATE có thể thay trạng thái nội dung mà vẫn trái chính sách.
- Không thay thế backup, retention, legal hold hoặc audit.

Nếu muốn ngăn DELETE ở mức quyền, thu hồi quyền DELETE thường trực tiếp và dễ hiểu hơn.

### 17.3. Khi cần chặn với thông báo lỗi rõ

`DO INSTEAD NOTHING` là cách **bỏ qua** hành động, không phải cách tự động phát lỗi nghiệp vụ rõ ràng.

Nếu mọi DELETE không được phép phải báo lỗi có SQLSTATE/chi tiết, xem giải pháp privilege hoặc trigger báo lỗi theo thiết kế. Không dùng việc âm thầm không làm gì khi ứng dụng cần biết thao tác đã bị từ chối.

## 18. DO INSTEAD: chuyển lệnh sang bảng khác

Tạo một bảng nhận dữ liệu chuyển hướng:

```sql
CREATE TABLE rule375.inbox (
    request_id integer PRIMARY KEY,
    request_title text NOT NULL,
    accepted_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE rule375.submission_endpoint (
    request_id integer PRIMARY KEY,
    request_title text NOT NULL
);
```

Tạo rule thay thế INSERT:

```sql
CREATE RULE redirect_submission_insert AS
ON INSERT TO rule375.submission_endpoint
DO INSTEAD
    INSERT INTO rule375.inbox(
        request_id,
        request_title
    )
    VALUES (
        NEW.request_id,
        NEW.request_title
    );
```

Chạy:

```sql
INSERT INTO rule375.submission_endpoint(
    request_id,
    request_title
)
VALUES (501, 'Yêu cầu được chuyển hướng');
```

Kiểm tra hai bảng:

```sql
SELECT *
FROM rule375.submission_endpoint;

SELECT request_id, request_title
FROM rule375.inbox
ORDER BY request_id;
```

**Dự kiến theo rule của lab:**

- `submission_endpoint` không có hàng 501 được chèn qua lời gọi ấy.
- `inbox` có hàng 501.

### 18.1. Vẫn không phải một “router” nghiệp vụ hoàn chỉnh

Hệ thống thật cần:

- Đồng bộ constraints giữa endpoint và bảng đích.
- Quyền viết và kiểm tra đầu vào.
- Xử lý RETURNING.
- Xử lý multi-row INSERT.
- Upsert/duplicate IDs.
- Migration và error reporting.
- Quan sát, retry, idempotency.

Trong nhiều trường hợp, một **view có INSTEAD OF trigger** hoặc API/function ghi tường minh rõ ràng hơn rule DML.

### 18.2. Cẩn thận trả về kết quả cho caller

Một client có thể mong:

```sql
INSERT ... RETURNING request_id;
```

trong khi rule DO INSTEAD không có RETURNING action được thiết kế tương ứng. Không mặc định rewrite sẽ tự lấy hàng từ bảng `inbox` và trả về.

## 19. Conditional rule: WHERE của rule không giống WHERE trong action

Cú pháp khái quát:

```sql
CREATE RULE some_rule AS
ON UPDATE TO some_table
WHERE OLD.some_column = 'A'
DO INSTEAD
    ...;
```

Đây là **điều kiện của rule**, không đơn giản là `WHERE` của một row-level trigger function.

PostgreSQL kết hợp điều kiện rule với query tree, các quan hệ `OLD`/`NEW` và WHERE gốc theo semantics rewrite.

### 19.1. Bẫy “chặn một phần hàng”

Giả sử một UPDATE đụng cả hàng thỏa và không thỏa điều kiện của conditional `INSTEAD` rule. Không thể suy luận rằng hệ thống gọi rule cho hàng A, sau đó tự chạy UPDATE gốc cho hàng B y hệt một procedural IF/ELSE theo hàng.

Quy tắc conditional `INSTEAD` có các chi tiết rewrite phức tạp. Nếu cần chặn/đổi cập nhật **theo từng hàng**, một `BEFORE ROW` trigger hoặc câu UPDATE có WHERE/constraint phù hợp thường dễ lập luận hơn.

### 19.2. DO INSTEAD NOTHING có điều kiện dễ bị hiểu sai

Đừng đưa một rule dạng:

```sql
ON UPDATE
WHERE OLD.status = 'LOCKED'
DO INSTEAD NOTHING;
```

vào production rồi coi nó tự động thay thế một chính sách khóa hàng chặt chẽ. Cần kiểm chứng chính xác hành vi với multi-row UPDATE, điều kiện gốc, RETURNING và tất cả đường ghi.

### 19.3. Ranh giới sử dụng

**Rule thích hợp khi muốn biến đổi cấu trúc câu lệnh. Trigger thích hợp khi muốn xử lý dữ liệu hàng tại thời điểm thao tác.**

## 20. Một SELECT rule phải khác DML rule

Với view, `ON SELECT` không được dùng như một cơ chế chung để “trước SELECT hãy ghi audit”.

Lý do:

- SELECT rules có yêu cầu đặc biệt: tên `_RETURN`, unconditional INSTEAD, action SELECT đơn tương ứng.
- Query rewrite không phải cơ chế side-effect tracking theo từng lần row được đọc.
- View expansion có thể xuất hiện nhiều lần do query phức tạp, subquery và optimization.
- Chưa xét quyền xem dữ liệu, ghi log và tính chính xác thống kê.

Nếu cần **audit truy cập dữ liệu**:

- Chọn logging/auditing cơ sở dữ liệu theo yêu cầu.
- Xem khả năng và giới hạn của extension audit phù hợp.
- Ghi sự kiện ở application/API boundary đáng tin.
- Thiết kế quyền và log privacy.
- Không xem rule SELECT như BEFORE SELECT trigger theo hàng.

## 21. Views tự cập nhật, INSTEAD OF trigger và INSTEAD rule

Ba khả năng có thể xuất hiện:

### 21.1. Automatically updatable view

```sql
CREATE VIEW v AS
SELECT id, name, is_active
FROM base_table
WHERE is_active;
```

Nếu view thỏa yêu cầu, PostgreSQL có thể chuyển DML sang base table một cách tự động.

Ưu tiên lựa chọn này khi view đơn giản và update mapping rõ.

### 21.2. INSTEAD OF trigger trên view

Với view phức tạp, có thể cài:

```sql
CREATE TRIGGER ...
INSTEAD OF INSERT OR UPDATE OR DELETE
ON some_view
FOR EACH ROW
EXECUTE FUNCTION ...;
```

Trigger function quyết định mỗi hàng được ghi vào bảng nào và có thể trả `NEW` hoặc `NULL` theo semantics của INSTEAD OF trigger.

Nó phù hợp khi việc ánh xạ DML có logic cụ thể theo từng hàng.

### 21.3. DML rewrite rule trên view

Một rule `ON INSERT/UPDATE/DELETE DO INSTEAD ...` có thể làm view hoặc relation phản ứng với DML qua rewrite. Tuy nhiên:

- Khó lập luận với RETURNING.
- Dễ gây khác biệt giữa multi-row statements và row-by-row expectations.
- Có những giới hạn cụ thể trong kết hợp câu SQL khác.
- Khó kiểm soát lỗi/side effects procedural.

**Thực hành:** ưu tiên automatically updatable view; nếu cần ánh xạ ghi phức tạp, cân nhắc `INSTEAD OF` trigger. Chỉ dùng DML rules khi có lý do kỹ thuật rõ và đã hiểu giới hạn.

## 22. Cần xử lý INSERT ... RETURNING như thế nào?

Ứng dụng thường viết:

```sql
INSERT INTO rule375.requests(request_id, request_title)
VALUES (99, 'Demo')
RETURNING request_id;
```

Với một bảng bình thường, `RETURNING` trả kết quả từ những hàng được INSERT.

Nhưng khi relation có rules viết lại INSERT:

- Action nào được thực thi?
- Nó có hay không có `RETURNING`?
- Có những rule nào cùng event?
- Các câu trả kết quả có cấu trúc nào?
- Rule action là `DO ALSO` hay `DO INSTEAD`?

### 22.1. RETURNING không mặc nhiên hoạt động như trong trigger

PostgreSQL có **hạn chế đặc thù** về RETURNING trong rule actions, đặc biệt sự tương tác giữa `DO ALSO`, `DO INSTEAD` và những lời gọi DML cần RETURNING.

Với một rule redirect:

```sql
CREATE RULE redirect AS
ON INSERT TO endpoint
DO INSTEAD
    INSERT INTO real_table(...)
    VALUES (...);
```

không nên giả định:

```sql
INSERT INTO endpoint(...)
VALUES (...)
RETURNING id;
```

tự trả `id` của hàng ở bảng real_table.

### 22.2. Nếu RETURNING là hợp đồng ứng dụng quan trọng

Một cách thiết kế đơn giản hơn:

- DML trực tiếp trên bảng gốc với `RETURNING`.
- Function ghi dữ liệu và trả kết quả tường minh.
- Automatically updatable view nếu phù hợp.
- `INSTEAD OF` trigger được thiết kế đúng cho view.

Nếu vẫn chọn rule, phải thiết kế và kiểm tra riêng mọi dạng RETURNING caller trên đúng PostgreSQL version.

## 23. Rules và INSERT ... ON CONFLICT

Một tính năng PostgreSQL rất phổ biến:

```sql
INSERT INTO some_table(id, value)
VALUES (1, 'A')
ON CONFLICT (id)
DO UPDATE SET value = EXCLUDED.value;
```

Đối với relation có `ON INSERT` hoặc `ON UPDATE` rules, PostgreSQL áp dụng **giới hạn** cho việc dùng relation ấy làm target của `INSERT ... ON CONFLICT`.

Không nên nghĩ upsert tự kết hợp rule một cách tương đương trigger.

### 23.1. Vì sao liên quan?

Upsert có hai nhánh ngữ nghĩa:

1. Insert hàng mới.
2. Nếu xảy ra conflict phù hợp, thực hiện DO UPDATE hoặc DO NOTHING.

Nếu target còn có query rewrite actions, việc diễn giải đúng bản ghi nào được ghi và câu nào được sinh ra phức tạp hơn. PostgreSQL hạn chế một số kết hợp thay vì hứa một hành vi khó bảo đảm.

### 23.2. Quy tắc thiết kế thực tiễn

Nếu hệ thống cần upsert mạnh:

- Ưu tiên bảng có constraints/unique indexes rõ.
- Dùng row-level triggers khi cần kiểm tra/audit.
- Tránh custom INSERT/UPDATE rules trên target.
- Chạy kiểm thử đặc thù cho `ON CONFLICT DO UPDATE`, `DO NOTHING`, `RETURNING`.

Không thay `ON CONFLICT` bằng một rule “nếu tồn tại thì UPDATE, nếu không thì INSERT” thiếu kiểm soát concurrency. Unique constraint và câu upsert built-in có cơ chế đồng thời chuyên biệt mà việc rewrite thủ công khó tái tạo.

## 24. COPY FROM không kích hoạt rules như INSERT thông thường

PostgreSQL có lệnh bulk load:

```sql
COPY some_table (...) FROM ...;
```

**COPY FROM không áp dụng query rewrite rules cho từng hàng giống một câu INSERT thông thường.**

Điều này quan trọng nếu bạn dự định dùng `ON INSERT DO ALSO` rule để:

- Ghi audit mỗi hàng.
- Bắt buộc tạo bản ghi phụ.
- Chuyển hướng dữ liệu.
- Thực hiện logic validation.

Một pipeline bulk load qua COPY có thể **bỏ qua logic dựa trên rule** theo cơ chế này.

### 24.1. Trigger và constraints có hành vi khác

Trong PostgreSQL, `COPY FROM` có thể kích hoạt triggers và kiểm tra constraints theo các quy tắc tương ứng. Vì thế trigger/constraint thường đáng tin cậy hơn rule cho những yêu cầu phải áp dụng cả trên đường nhập liệu bulk.

### 24.2. Không nói “COPY bỏ qua toàn bộ bảo vệ của PostgreSQL”

Sai. Điểm ở đây là **COPY FROM không kích hoạt rewrite rules** theo cách bạn kỳ vọng từ INSERT SQL. Nó vẫn nằm trong hệ thống transaction/permissions/constraints và có các đặc tính riêng.

## 25. TRUNCATE không phải DELETE

Giả sử đã khai báo:

```sql
CREATE RULE protected_notes_no_delete AS
ON DELETE TO rule375.protected_notes
DO INSTEAD NOTHING;
```

Bạn không thể khẳng định bảng được bảo vệ khỏi mọi hành vi xóa dữ liệu.

```sql
TRUNCATE TABLE rule375.protected_notes;
```

là một lệnh khác. Nó không trở thành các DELETE row events để rule ON DELETE bảo vệ.

### 25.1. Vì sao bảo mật bằng rule DELETE là thiếu?

- Nếu role có quyền TRUNCATE, rule không giải quyết đường ấy.
- Các DDL có thể gây thay đổi khác.
- Một tài khoản owner/DBA có thể đổi cấu hình.
- Các luật pháp lý/retention cần thêm quản trị quyền và log.

### 25.2. Dùng quyền đúng mục tiêu

Nếu chỉ người quản trị mới được xóa:

- Thu hồi DELETE, TRUNCATE đối với role ứng dụng không được phép.
- Đảm bảo ứng dụng không có quyền schema/ownership không cần thiết.
- Cấu hình backup và audit phù hợp.
- Cân nhắc trigger báo lỗi/soft-delete workflow nếu cần logic riêng.

Không dùng rule như tấm chắn duy nhất cho dữ liệu quan trọng.

## 26. Biểu thức VOLATILE và nguy cơ đánh giá nhiều lần

Một biểu thức có side effects hoặc giá trị khác mỗi lần gọi:

```sql
nextval('some_sequence')
random()
clock_timestamp()
```

được gọi là volatile trong ngữ nghĩa PostgreSQL.

Khi câu lệnh chứa biểu thức như vậy và rewrite rules tạo ra thêm query hoặc tham chiếu đến các biểu thức `NEW` theo những cách khác nhau, việc đánh giá có thể không giống suy luận “đã tính một lần thành giá trị NEW rồi phát sang hai hành động”.

### 26.1. Ví dụ tư duy

Ứng dụng dự tính:

```text
INSERT bảng chính dùng giá trị nextval -> id N
DO ALSO action log id N
```

Nếu rule rewrite tham chiếu lại một expression thay vì một hàng đã thực thi, biểu thức volatile có thể bị đánh giá khác số lần/cách mà người viết trực giác kỳ vọng.

### 26.2. Cách tránh

Nếu phải bảo đảm log nhận **giá trị id thực tế của hàng đã được chèn**, AFTER ROW INSERT trigger dùng `NEW.id` thường có hợp đồng đúng hơn.

Nếu phải phát sự kiện sau commit:

- Trigger ghi outbox trong transaction.
- Consumer phát sự kiện ngoài DB.
- Không gửi trực tiếp email/HTTP từ rule action.

### 26.3. Đừng dùng statement_timestamp hay now làm phép thử duy nhất

`now()` có ngữ nghĩa transaction timestamp, nên hai lần đánh giá có thể bằng nhau; điều đó không chứng minh hệ thống chỉ đánh giá một lần. Cần hiểu volatility và cấu trúc rewrite, không dựa vào một timestamp giống nhau để kết luận.

## 27. Rules không phải bảo đảm “side effects đúng một lần”

Một rule `DO ALSO INSERT INTO log...` chỉ mô tả một hành động rewrite bổ sung trong những lệnh phù hợp.

Nó không tự bảo đảm:

- Một log row cho mỗi row đã thực sự được thay đổi.
- Mọi đường nhập liệu đều đi qua rule.
- Không có duplicate khi caller retry.
- Event được publish một lần sau commit.
- Consumer nhận sự kiện theo đúng thứ tự.
- Không có lỗi khi một bảng/constraint liên quan thay đổi.

### 27.1. Exactly-once end-to-end là vấn đề lớn hơn

Ngay cả AFTER trigger và outbox cũng thường cần:

- Unique event ID.
- Idempotent consumer.
- Retry policy.
- Deduplication.
- Out-of-order handling.
- Monitoring và replay.

Rule không giải quyết những vấn đề distributed systems ấy.

## 28. UPDATE rule với OLD/NEW có thể khó suy luận

Một rule `ON UPDATE` có thể tham chiếu:

```sql
OLD.unit_price
NEW.unit_price
```

Nhìn gần giống trigger:

```sql
IF NEW.unit_price <> OLD.unit_price THEN ...
```

Nhưng cơ chế khác hẳn.

### 28.1. Trong trigger

BEFORE/AFTER ROW UPDATE trigger chạy trong ngữ cảnh một hàng và nhìn thấy OLD/NEW records của hàng đó, theo loại trigger và thời điểm thực thi.

### 28.2. Trong rule

`OLD` và `NEW` là những pseudo-relations được dùng để viết lại cây query; chúng không phải biến PL/pgSQL record được cập nhật sau mỗi vòng lặp.

### 28.3. Khi cần ngăn giảm giá quá sâu

Ví dụ nghiệp vụ:

```text
Nếu unit_price mới thấp hơn 50% unit_price cũ,
từ chối UPDATE với lỗi rõ ràng.
```

Đây là kiểm tra **theo từng hàng**, có so OLD và NEW. Thường nên viết một BEFORE ROW trigger:

```sql
CREATE OR REPLACE FUNCTION rule375.guard_price_drop()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.unit_price < OLD.unit_price * 0.5 THEN
        RAISE EXCEPTION
            'New price is less than half the old price'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$;
```

Hàm sẽ được gắn vào bảng ở phần về trigger; ý chính là đây là API PL/pgSQL row-by-row, không phải một rewrite rule.

## 29. Triggers: sự khác biệt quan trọng so với rules

| Tiêu chí | Rewrite rule | Trigger |
|---|---|---|
| Giai đoạn chính | Rewriter, trước planner/executor | Khi executor thực hiện sự kiện DML tương ứng |
| Đơn vị xử lý | Query/query tree | Statement hoặc row tùy `FOR EACH` |
| Truy cập OLD/NEW | Pseudo-relations khi rewrite | OLD/NEW records trong row trigger, transition tables cho một số statement triggers |
| Phát hành action | Sinh/thay thế query | Gọi trigger function |
| Kiểm tra giá trị từng hàng | Dễ gây nhầm, không phải công cụ chính | BEFORE ROW trigger phù hợp |
| Audit từng hàng thực sự thay đổi | Không phải lựa chọn nên ưu tiên | AFTER ROW trigger phù hợp hơn |
| View complex DML | Có thể dùng INSTEAD rules | INSTEAD OF trigger thường rõ |
| SELECT view expansion | Là nền tảng quan trọng | Trigger thông thường không làm nhiệm vụ mở rộng SELECT view |
| DML với COPY FROM | COPY không kích hoạt rules | COPY FROM có thể kích hoạt triggers |
| ON CONFLICT | Có các hạn chế đáng kể khi có DML rules | Có semantics triggers được PostgreSQL quy định |
| RETURNING | Có giới hạn rule đặc thù | Thường tương tác trực tiếp hơn qua DML gốc |
| Tính dễ dự đoán từng hàng | Khó cho người mới | Rõ hơn khi định nghĩa đúng row trigger |

### 29.1. Trigger cũng không tự giải quyết mọi điều kiện

Trigger có thể gây deadlock, hoạt động ngoài ý định, bị retry, ảnh hưởng hiệu năng và có những tương tác riêng với multi-row/partitioning.

Không phải mọi business rule đều cần trigger. Nếu một invariant có thể diễn đạt bằng `CHECK` hoặc `UNIQUE`, constraint có thể là lựa chọn gọn và đáng tin cậy hơn.

### 29.2. Ưu tiên công cụ đúng tầng

- Ràng buộc miền giá trị → CHECK/NOT NULL.
- Tính duy nhất → UNIQUE.
- Tham chiếu → FOREIGN KEY.
- Quyền theo hàng → RLS.
- Logic tác động mỗi hàng → trigger.
- Định nghĩa view → CREATE VIEW.
- Biến đổi cây query chuyên biệt → rule khi thật sự cần.

## 30. Ví dụ thay rule audit bằng AFTER ROW trigger

Trên bảng `rule375.requests` đã tạo rule audit. Để minh họa hướng thay thế, ta tạo một **bảng thực hành khác** nhằm tránh việc rule và trigger cùng ghi log hai lần.

```sql
CREATE TABLE rule375.trigger_requests (
    request_id integer PRIMARY KEY,
    request_title text NOT NULL
);

CREATE TABLE rule375.trigger_request_log (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id integer NOT NULL,
    event_name text NOT NULL,
    logged_at timestamptz NOT NULL DEFAULT now()
);
```

Hàm trigger:

```sql
CREATE OR REPLACE FUNCTION rule375.log_trigger_request_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO rule375.trigger_request_log(
        request_id,
        event_name
    )
    VALUES (
        NEW.request_id,
        'INSERT'
    );

    RETURN NEW;
END;
$$;
```

Tạo trigger:

```sql
CREATE TRIGGER trg_trigger_requests_insert
AFTER INSERT ON rule375.trigger_requests
FOR EACH ROW
EXECUTE FUNCTION rule375.log_trigger_request_insert();
```

Chèn nhiều hàng:

```sql
INSERT INTO rule375.trigger_requests(
    request_id, request_title
)
VALUES
    (201, 'Request A'),
    (202, 'Request B'),
    (203, 'Request C');
```

Kiểm tra:

```sql
SELECT
    request_id,
    event_name
FROM rule375.trigger_request_log
ORDER BY request_id;
```

Kỳ vọng có ba bản ghi audit, tương ứng ba hàng được INSERT thành công trong statement/transaction.

### 30.1. Vì sao AFTER ROW phù hợp?

Trigger chạy gắn với từng hàng thực sự được insert ở event tương ứng. `NEW.request_id` là giá trị của row đã xử lý, không phải một biểu thức `NEW` trong query rewrite.

### 30.2. Có nên ghi log transaction commit thành công ngay trong trigger?

Log được INSERT trong cùng transaction. Nếu transaction rollback, cả bản ghi chính và log cùng rollback. Đây thường là đặc tính mong muốn với transactional audit/outbox.

Nếu muốn lưu lại **cả những attempt bị rollback**, cần một hệ thống logging/audit bên ngoài transaction phù hợp; trigger bình thường không tự bảo đảm lưu vết những transaction thất bại.

### 30.3. RETURN NEW trong AFTER trigger

Trong AFTER ROW trigger, giá trị return của trigger function không quyết định hàng được ghi giống BEFORE ROW trigger, nhưng `RETURN NEW;` là cú pháp hợp lệ, dễ đọc và thống nhất. Không dùng return value để suy ra AFTER trigger có thể sửa tuple sau khi đã ghi bằng cách gán NEW.

## 31. Ràng buộc dữ liệu: dùng constraint thay rule

Giả sử mỗi sản phẩm phải có giá không âm. Ta đã khai báo:

```sql
unit_price numeric(12, 2) NOT NULL
    CHECK (unit_price >= 0)
```

Đây là invariant của **trạng thái dữ liệu**, không phụ thuộc ứng dụng có đi qua một route hay không.

### 31.1. CHECK phù hợp khi quy tắc là một hàng và biểu thức có semantics hợp lệ

Ví dụ:

```sql
CHECK (unit_price >= 0)
```

áp dụng cho INSERT/UPDATE. Rule viết lại truy vấn không cần thiết.

### 31.2. UNIQUE phù hợp khi cần ngăn trùng

```sql
CREATE TABLE rule375.external_ids (
    external_id text PRIMARY KEY,
    description text NOT NULL
);
```

Không viết rule:

```text
Nếu thấy ID trùng thì DO INSTEAD NOTHING
```

để thay thế unique constraint; concurrency có thể khiến kiểm tra chủ quan thất bại, đồng thời caller không hiểu lệnh ghi có xảy ra hay không.

### 31.3. FOREIGN KEY phù hợp cho quan hệ tham chiếu

Một order phải tham chiếu product hợp lệ có thể dùng FOREIGN KEY, không cần một ON INSERT rule để tự kiểm tra qua SELECT rồi quyết định ghi.

### 31.4. Nếu quy tắc phụ thuộc nhiều hàng?

Có thể cần transaction, locking protocol, unique/exclusion constraints hoặc trigger theo thiết kế. Một `CHECK` không tự động đủ cho mọi invariant xuyên bảng; nhưng rule cũng không phải giải pháp mặc định.

## 32. RLS: kiểm soát ai được đọc và ghi những hàng nào

Giả sử mỗi request thuộc một tenant.

Một rule:

```sql
CREATE RULE ...
```

không phải lớp bảo mật hàng phổ quát tương đương **Row Level Security**.

### 32.1. Vì sao rule không phải RLS?

- Rule rewrite có thể bị tác động bởi những dạng câu lệnh/đường nhập dữ liệu khác.
- Không tự xác thực danh tính của caller.
- Không tự bảo vệ quyền trên từng hàng/từng tenant.
- Có thể phức tạp với VIEW, JOIN, RETURNING và DML.
- Có quyền quản trị cần kiểm soát riêng.

### 32.2. Cấu trúc tư duy

```text
Role / authenticated identity
           |
           v
PostgreSQL permissions
           |
           v
Row Level Security policies (khi bật và thích hợp)
           |
           v
Query execution theo quyền
```

### 32.3. Tránh lấy tenant ID từ tham số tùy tiện

Một service nhận `tenant_id` do client tự điền rồi tạo `WHERE tenant_id = p_tenant_id` không tự bảo đảm caller được phép xem tenant ấy.

Cần gắn tenant scope với xác thực/ủy quyền đáng tin và bảo vệ cả quyền trực tiếp trên bảng/view/routines.

## 33. View và security boundary: không đồng nhất đơn giản

View thường dùng để trình bày một tập cột/hàng:

```sql
CREATE VIEW rule375.public_product_catalog AS
SELECT
    product_id,
    product_name,
    category,
    unit_price
FROM rule375.products
WHERE is_active;
```

Người dùng chỉ được cấp SELECT trên view có thể không cần quyền trực tiếp trên bảng gốc tùy cấu hình owner/permission và phiên bản.

Tuy nhiên cách kiểm tra quyền, RLS và quyền truy cập của view chịu semantics của PostgreSQL và tùy chọn cấu hình.

### 33.1. security_barrier

Một số view được dùng để hạn chế thông tin mà caller không được phép thấy. Trong những trường hợp có biểu thức người dùng không đáng tin, thứ tự đánh giá/pushdown có thể quan trọng.

PostgreSQL hỗ trợ tùy chọn view như `security_barrier` để hỗ trợ các mục tiêu bảo mật tương ứng.

Ví dụ cú pháp:

```sql
CREATE VIEW rule375.public_product_catalog_barrier
WITH (security_barrier = true)
AS
SELECT
    product_id,
    product_name,
    unit_price
FROM rule375.products
WHERE is_active;
```

Nhưng `security_barrier` không tự tạo xác thực tenant hoặc che mọi kênh rò rỉ; phải xem cả RLS, quyền, leakproof functions và threat model.

### 33.2. security_invoker

Các phiên bản PostgreSQL hiện đại có hỗ trợ tùy chọn `security_invoker` cho view, làm thay đổi cách kiểm tra quyền đối với những quan hệ gốc theo semantics được quy định.

Nếu cần dùng:

```sql
-- Ví dụ cú pháp cho phiên bản hỗ trợ tính năng:
CREATE VIEW rule375.invoker_catalog
WITH (security_invoker = true)
AS
SELECT product_id, product_name
FROM rule375.products
WHERE is_active;
```

Hãy kiểm tra server version và privileges thực tế. Không mặc định một view luôn có quyền của owner hoặc luôn của invoker trong mọi cấu hình.

### 33.3. Không làm security bằng DO INSTEAD NOTHING

Một DELETE rule âm thầm không làm gì không phải là chính sách ủy quyền đầy đủ. Nếu caller không có quyền xóa, hãy **không cấp DELETE**, hoặc áp RLS/triggers theo yêu cầu.

## 34. Rule và concurrency: phải xét transaction chứ không chỉ cú pháp

Query rewrite diễn ra trước khi executor thực thi. Những action sinh ra vẫn chạy trong ngữ cảnh transaction của câu lệnh/đường gọi tương ứng và chịu kiểm soát MVCC/locking/constraints.

### 34.1. Không có transaction độc lập cho mỗi rule action

Nếu một `DO ALSO` action ghi sang bảng phụ và một action gây lỗi khiến statement thất bại, không nên kỳ vọng PostgreSQL mặc nhiên commit một nửa “log thành công, bảng chính thất bại” như hai transaction độc lập.

Các thay đổi chịu cơ chế transaction/rollback của PostgreSQL.

### 34.2. Nhưng atomicity không đồng nghĩa correctness nghiệp vụ

Việc lệnh gốc và action bổ sung cùng rollback khi lỗi **không chứng minh** bạn đã ghi đúng log per row, đúng thứ tự, hoặc đồng bộ chính xác với hệ thống ngoài.

Cần phân biệt:

- **Atomicity**: thay đổi commit/rollback theo transaction.
- **Correctness**: các hàng và ý nghĩa sự kiện đúng nghiệp vụ.
- **Delivery**: sự kiện được chuyển đi sau commit và xử lý retry.
- **Idempotency**: gọi lặp không tạo hậu quả sai.
- **Isolation**: các transaction đồng thời không vi phạm invariant.

Rule không tự giải quyết năm vấn đề này.

## 35. Multi-row UPDATE/DELETE: hiệu ứng bất ngờ

Một statement:

```sql
UPDATE rule375.products
SET unit_price = unit_price * 1.10
WHERE category = 'coffee';
```

có thể sửa nhiều rows.

Nếu có DML rules tạo thêm truy vấn:

- Rewriter làm việc với câu SQL như một cây query.
- `OLD`/`NEW` được biến đổi theo quan hệ/biểu thức trong query.
- Các query actions có thể có điều kiện và join tới tập row liên quan.
- Caller có thể thêm RETURNING.
- DML có thể gặp constraints và concurrency conflicts.

### 35.1. Kỳ vọng thường sai

```text
Mỗi hàng tăng 10%
  -> gọi rule
     -> INSERT một log record
```

Đừng lập mô hình này cho rules.

### 35.2. Cách thiết kế phù hợp

Nếu cần audit mỗi row thay đổi:

```sql
CREATE TRIGGER trg_price_audit
AFTER UPDATE OF unit_price ON rule375.products
FOR EACH ROW
WHEN (OLD.unit_price IS DISTINCT FROM NEW.unit_price)
EXECUTE FUNCTION rule375.some_audit_trigger_function();
```

Đoạn này là **khuôn mẫu**; `some_audit_trigger_function()` cần được định nghĩa trước mới chạy được. Ý chính là dùng trigger với OLD/NEW records và `IS DISTINCT FROM` khi cần so sánh có NULL.

### 35.3. WHEN của trigger khác WHERE của rule

Trigger WHEN quyết định có kích hoạt trigger cho event/hàng theo semantics trigger.

Rule WHERE là điều kiện của hệ thống rewrite. Không thể thay tên và giữ nguyên hành vi mà không chứng minh.

## 36. Rules và các cú pháp SQL phức tạp

Các câu lệnh có thể tương tác phức tạp với rules gồm:

- `INSERT ... ON CONFLICT`.
- `INSERT ... RETURNING`.
- `UPDATE ... FROM`.
- `DELETE ... USING`.
- `WITH` và data-modifying CTEs.
- `MERGE`, tùy phiên bản và những giới hạn của relation có rules.
- Multi-row `VALUES`, `INSERT ... SELECT`.
- Views tự cập nhật hoặc INSTEAD OF triggers.
- Các câu lệnh ghi trên partitioned tables.

### 36.1. Đừng suy luận một rule làm việc giống nhau cho mọi DML

Một rule chạy trên ví dụ `INSERT VALUES (1, 'A')` chưa chứng minh hợp lệ cho `INSERT ... ON CONFLICT DO UPDATE RETURNING ...`.

Khi ứng dụng cần nhiều dạng DML, thử từng dạng trên đúng PostgreSQL version, cùng quyền và schema thật.

### 36.2. MERGE và rule targets

`MERGE` có các hạn chế/semantics riêng liên quan quan hệ đích có rules trong các phiên bản PostgreSQL hỗ trợ MERGE. Không mặc định mọi rule ON INSERT/UPDATE/DELETE của một relation đều được kết hợp tự nhiên khi relation được dùng trong MERGE.

Cần tham khảo phần `MERGE` và `CREATE RULE` của **phiên bản server cụ thể** trước khi thiết kế.

### 36.3. Partitions không tạo per-row rule semantics

Partitioning làm thay đổi cách route hàng và phạm vi DML, không biến rule thành trigger. Với partitioned tables, ưu tiên các tính năng partitioning, indexes/constraints và triggers được PostgreSQL hỗ trợ thay vì tạo quy tắc viết lại tùy tiện trên mỗi partition.

## 37. Recursive rules và rewrite loops

Một rule có thể tạo action lại tác động tới quan hệ/sự kiện liên quan, dẫn đến vòng viết lại không hữu ích hoặc không được phép.

Mô hình nguy hiểm:

```text
ON INSERT TO A
   DO INSTEAD INSERT INTO B ...

ON INSERT TO B
   DO INSTEAD INSERT INTO A ...
```

Nếu không có cách kết thúc phù hợp, hệ thống rewrite có thể phát hiện vòng lặp hoặc báo lỗi thay vì thực thi mãi theo kỳ vọng của người viết.

### 37.1. Hạn chế self-referencing rule

Một rule trên A lại tạo cùng loại DML vào A có thể dẫn tới recursive rewrite. Đừng dùng rule để mô phỏng loop.

### 37.2. Khi muốn lặp có kiểm soát

- Với xử lý lặp trong database, dùng PL/pgSQL function/procedure và điều kiện kết thúc rõ.
- Với thao tác set-based, dùng SQL trực tiếp.
- Với workflow bất đồng bộ, dùng queue/outbox.
- Với dữ liệu phân cấp, cân nhắc recursive CTE để **truy vấn** thay vì rule tự gọi lại.

## 38. Nhiều rules cho cùng một relation/event

Một relation có thể có nhiều rules. Nếu nhiều rules cùng tác động một loại DML, cần xem:

- Rules có điều kiện hay không.
- DO ALSO hay INSTEAD.
- Các action có chồng lên cùng dữ liệu không.
- Có dùng DEFAULT/volatile expressions không.
- Có RETURNING hay không.
- Các rule có tạo recursive rewrite không.

### 38.1. Không nên dựa vào thứ tự ngẫu nhiên

PostgreSQL có quy tắc xử lý đối với các rules, nhưng không nên thiết kế nghiệp vụ cần “rule A ghi log, rule B cập nhật, rule C gửi kết quả” như một chuỗi callback procedural chỉ vì tên rule sắp xếp đẹp.

### 38.2. Nếu cần thứ tự nghiệp vụ rõ ràng

Một function/procedure hoặc trigger workflow được thiết kế tường minh thường dễ hiểu hơn:

```text
validate
  -> write data
  -> insert outbox
  -> commit
  -> async delivery
```

Cần xác định ranh giới transaction và lỗi cho mỗi bước.

## 39. Rules và audit: chọn trigger, log hoặc outbox

Audit có nhiều loại:

| Nhu cầu | Hướng công cụ phù hợp |
|---|---|
| Biết SQL nào được client gửi | Logging/auditing tại database hoặc application |
| Biết hàng nào được INSERT/UPDATE/DELETE thành công | AFTER ROW trigger hoặc change capture phù hợp |
| Lưu lịch sử giá cũ/mới | Trigger với OLD/NEW records, bảng lịch sử |
| Ghi sự kiện durable để đồng bộ | Transactional outbox / CDC |
| Quan sát truy cập SELECT | Logging/audit cấp statement/API; không dùng SELECT rewrite rule tùy ý |
| Chặn đổi trường bất biến | BEFORE ROW trigger / permissions / constraints |
| Giới hạn người xem bản ghi | RLS và grants |

### 39.1. Ghi audit bằng DO ALSO là bài demo, không phải mặc định production

Người mới dễ thấy:

```sql
CREATE RULE log_change AS
ON UPDATE TO orders
DO ALSO INSERT INTO log ...;
```

rồi tưởng đã giải quyết đầy đủ tracking. Nhưng multi-row DML, old/new binding, volatile expressions và các đường ghi đặc biệt khiến đây là nền tảng không nên ưu tiên cho audit quan trọng.

### 39.2. Nếu cần audit trước và sau

Một AFTER UPDATE row-level trigger thường có sẵn `OLD` và `NEW` trong function, có thể so:

```sql
IF OLD.status IS DISTINCT FROM NEW.status THEN
    ...
END IF;
```

Nó vẫn cần xử lý kiểu dữ liệu, quyền, privacy và transaction; nhưng ngữ nghĩa per-row dễ kiểm chứng hơn.

## 40. Source of truth và transactional outbox

Giả sử ứng dụng tạo đơn hàng rồi muốn đồng bộ ra hệ thống tìm kiếm, phân tích hoặc message broker.

Một cách an toàn về cấu trúc:

```text
Ứng dụng
   |
   v
PostgreSQL transaction
   |
   +-- INSERT order
   |
   +-- INSERT outbox event
   |
   v
COMMIT
   |
   v
Worker đọc outbox
   |
   +-- gửi tới search/queue
   +-- retry/deduplicate
   +-- đánh dấu đã xử lý
```

### 40.1. Vì sao rule không phải phương án chính?

Rule không cung cấp transaction boundary ngoài database, delivery guarantee tới hệ khác, retry hay idempotency.

Một AFTER trigger ghi outbox trong cùng transaction, hoặc application ghi order + outbox trong một transaction tường minh, là hai cách phổ biến hơn.

### 40.2. Đừng gửi external HTTP ngay trong trigger như mặc định

Dù trigger phù hợp hơn rule cho per-row changes, gọi external API ngay khi transaction đang mở có thể:

- Tăng latency và giữ lock lâu.
- Gây lỗi mạng ảnh hưởng transaction.
- Tạo side effect ngoài DB không rollback được nếu DB rollback.
- Phức tạp retry/idempotency.

Outbox giúp tách commit dữ liệu khỏi giao sự kiện ra bên ngoài.

## 41. Performance: rule không phải lối tắt tăng tốc query

Một rewrite rule có thể:

- Tạo thêm queries/actions.
- Làm query tree phức tạp.
- Thêm scans/joins.
- Đẩy chi phí vào các bảng khác.
- Tương tác với planner và caching.
- Tăng số statement logic phải tối ưu/thực thi.

### 41.1. View qua _RETURN có thể được tối ưu tốt

Một view đơn giản nhiều khi gần như “mở rộng SQL” để planner xử lý. Đó là lý do dùng view hợp lý không nhất thiết làm chậm.

### 41.2. DML rules có thể tăng chi phí không rõ ràng

Một câu:

```sql
INSERT INTO endpoint ...
```

có thể sinh ra một hoặc nhiều action khác, nên đo thời gian của một câu INSERT đơn giản trên bảng trống không thể đại diện cho workload với rules.

### 41.3. Đo đủ ảnh hưởng

- EXPLAIN cho SELECT qua view.
- Query latency và p95/p99 ở ứng dụng.
- Số buffer/page reads/writes.
- WAL sinh ra.
- Lượng row changes/logs.
- Lock waits/deadlocks.
- Chi phí query plan.
- Tác động trên multi-row INSERT/UPDATE/DELETE.

Không giả định rule ở giai đoạn trước planner “miễn phí”.

## 42. Materialized view: khi nào cần lưu sẵn kết quả

View thường qua _RETURN dùng dữ liệu nguồn khi truy vấn. Nếu một báo cáo aggregate đắt đỏ và freshness cho phép, có thể xem `MATERIALIZED VIEW`:

```sql
CREATE MATERIALIZED VIEW rule375.category_totals AS
SELECT
    category,
    count(*) AS product_count,
    sum(unit_price) AS total_price
FROM rule375.products
GROUP BY category;
```

Truy vấn:

```sql
SELECT *
FROM rule375.category_totals
ORDER BY category;
```

### 42.1. Materialized view không tự cập nhật theo mỗi INSERT

Sau khi sửa dữ liệu gốc, materialized view thông thường cần refresh:

```sql
REFRESH MATERIALIZED VIEW rule375.category_totals;
```

### 42.2. REFRESH CONCURRENTLY có điều kiện

Không thể tự đặt `CONCURRENTLY` cho mọi materialized view mà không đáp ứng các yêu cầu như unique index phù hợp và trạng thái populate. Phải xem tài liệu PostgreSQL trước khi triển khai.

### 42.3. Khi nào chọn materialized view?

- Báo cáo aggregate lặp lại nhiều.
- Chi phí tính toán cao.
- Có thể chấp nhận dữ liệu trễ theo refresh schedule.
- Có cơ chế giám sát dữ liệu và refresh errors.

Không dùng rule DO ALSO để tự “refresh materialized view mỗi lần insert” như một giải pháp mặc định: dễ tạo chi phí cực lớn và làm chậm OLTP.

## 43. Quản lý rule: DROP và thay đổi định nghĩa

Nếu muốn bỏ rule chặn DELETE trong lab:

```sql
DROP RULE protected_notes_no_delete
ON rule375.protected_notes;
```

Bây giờ DELETE có thể diễn ra theo quyền và constraints bình thường của bảng.

### 43.1. DROP RULE khác DROP TABLE

`DROP RULE ... ON relation` chỉ định rule và relation sở hữu rule. Nó không tự xóa bảng.

### 43.2. CREATE OR REPLACE RULE

PostgreSQL hỗ trợ thay định nghĩa một rule theo cú pháp tương ứng:

```sql
CREATE OR REPLACE RULE rule_name AS
ON ...
DO ...;
```

Nhưng với migration, thay định nghĩa có thể thay semantics các câu SQL đã được caller gửi từ trước. Không coi đó là một sửa đổi nội bộ vô hại.

### 43.3. Rule names gắn với relation

Tên rule được quản lý trong phạm vi relation tương ứng. Vì thế một lệnh drop cần chỉ rõ `ON relation`, tránh nhầm cùng tên rule trên những bảng khác.

### 43.4. Không sửa trực tiếp pg_rewrite

Các catalog PostgreSQL không phải nơi ứng dụng sửa dữ liệu raw để “tắt rule”. Dùng DDL được hỗ trợ và quản lý migration.

## 44. Quan sát trạng thái rule và phụ thuộc

Ngoài định nghĩa rule, có thể quan sát metadata:

```sql
SELECT
    r.oid,
    n.nspname,
    c.relname,
    r.rulename,
    r.ev_type,
    r.ev_enabled,
    r.is_instead
FROM pg_rewrite AS r
JOIN pg_class AS c
    ON c.oid = r.ev_class
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'rule375'
ORDER BY c.relname, r.rulename;
```

### 44.1. Trạng thái enabled và replication roles

PostgreSQL có metadata liên quan trạng thái kích hoạt rules trong những chế độ replication/session tương ứng. Không suy luận chỉ nhìn thấy rule trong catalog là nó chắc chắn áp dụng trong mọi chế độ phiên.

Khi điều tra một hành vi không như mong đợi, cần kiểm tra:

- Rule đang enabled hay không.
- `session_replication_role` nếu có liên quan và bạn được phép quản trị.
- Kiểu câu lệnh thực tế là INSERT, COPY, MERGE, TRUNCATE hay DML qua view.
- Privileges và transaction state.
- Rule có condition hay không.
- Có tác động từ triggers/constraints không.

### 44.2. Không tắt rule để “chạy tạm” trong production

Thay đổi trạng thái rule có thể làm những tác vụ khác đi đường ghi khác, gây dữ liệu lệch. Cần approval, migration plan và rollback rõ ràng.

## 45. Ví dụ một quy trình refactor từ rule DML sang trigger

Giả sử dự án có rule:

```sql
CREATE RULE audit_orders_update AS
ON UPDATE TO orders
DO ALSO INSERT INTO orders_audit ...;
```

Đây là một **khuôn mẫu mô tả**, không phải câu SQL đầy đủ để chạy.

### 45.1. Mục tiêu refactor

- Audit chính xác các hàng đã UPDATE.
- Ghi old/new values theo policy.
- Hỗ trợ multi-row DML.
- Không phá `ON CONFLICT` và các API `RETURNING`.
- Hạn chế rủi ro duplicate.
- Có đường rollback nếu trigger mới lỗi.

### 45.2. Các bước có kiểm soát

1. Đọc toàn bộ rule definition từ `pg_get_ruledef`.
2. Xác định mọi caller DML.
3. Đo trạng thái dữ liệu/audit hiện tại và phát hiện duplicates.
4. Thiết kế bảng audit/outbox với event IDs, timestamps và actor context.
5. Viết trigger function có OLD/NEW rõ ràng.
6. Kiểm thử INSERT/UPDATE/DELETE, multi-row, COPY, upsert và RETURNING theo nghiệp vụ.
7. Thiết kế migration ngăn rule cũ và trigger mới ghi log **đồng thời hai lần**.
8. Chuyển tại thời điểm/transaction thích hợp, kiểm tra quyền.
9. Đối soát log và dữ liệu.
10. Giám sát lỗi và triển khai rollback khả thi.

Không chuyển bằng cách “thêm trigger mới, giữ nguyên rule cũ vài ngày cho an toàn” nếu cả hai ghi cùng một bảng log — như vậy có thể tạo log trùng.

### 45.3. Không dùng TRUNCATE để dọn log trùng

Nếu audit là thông tin cần lưu, không được xóa để che migration error. Cần chính sách reconciliation, retention và audit trail.

## 46. Bảng quyết định: chọn công cụ phù hợp

| Yêu cầu | Ưu tiên | Lý do |
|---|---|---|
| Đọc qua một SELECT cố định | `CREATE VIEW` | View rewrite qua `_RETURN` |
| View đơn giản cần INSERT/UPDATE | Automatically updatable view | Không cần DML rule tự viết |
| Chặn hàng sau khi sửa qua view không còn thỏa điều kiện | `WITH CHECK OPTION` khi hỗ trợ | Hợp đồng view rõ |
| View phức tạp cần ánh xạ từng row INSERT/UPDATE/DELETE | `INSTEAD OF` trigger | Semantics per-row tường minh |
| Giá phải không âm | `CHECK` | Data invariant |
| Không được có hai mã trùng | `UNIQUE` | An toàn hơn tự pre-check |
| Quan hệ cha-con hợp lệ | `FOREIGN KEY` | Referential integrity |
| Chỉ role/tenant được xem hàng | Grants + RLS | Bảo mật truy cập |
| Audit từng row INSERT/UPDATE/DELETE | AFTER ROW trigger | OLD/NEW thực sự của hàng |
| Biến đổi row trước khi ghi | BEFORE ROW trigger | Có thể xử lý NEW theo semantics |
| Đồng bộ sang search/message broker | Outbox/CDC | Durable delivery/replay |
| Trả dataset aggregate đã tính sẵn | Materialized view | Tối ưu đọc, chấp nhận refresh |
| Biến đổi query ở tầng rewrite trong trường hợp đặc thù | Rule | Chỉ khi hiểu rõ giới hạn |
| Ngăn DELETE của role ứng dụng | REVOKE DELETE hoặc RLS/trigger | Không chỉ DO INSTEAD NOTHING |
| Bulk load có logic validation | Constraints/triggers và staging | COPY không kích hoạt rules |
| Upsert hàng theo unique key | `INSERT ... ON CONFLICT` | Không tự mô phỏng bằng rule |

**Quy tắc chung:** đừng chọn rule vì tên nghe giống “luật nghiệp vụ”. Hãy chọn nó khi bạn chủ đích cần **query rewrite**.

## 47. Những hiểu lầm cần tránh

### Hiểu lầm 1 — Rule giống trigger

Không. Rules rewrite câu SQL, triggers gắn với thời điểm thực thi sự kiện.

### Hiểu lầm 2 — OLD và NEW đều là biến PL/pgSQL

Không. Rules dùng OLD/NEW như pseudo-relations trong query tree. Trigger function dùng records tương ứng với ngữ cảnh trigger.

### Hiểu lầm 3 — DO ALSO chắc chắn chạy “sau” lệnh gốc

Không nên thiết kế dựa trên mô hình callback AFTER. Rule tạo action queries ở tầng rewrite.

### Hiểu lầm 4 — DO INSTEAD NOTHING luôn là bảo vệ dữ liệu đầy đủ

Không. Nó không thay permissions, constraints, backup, RLS hay ngăn TRUNCATE.

### Hiểu lầm 5 — Có ON INSERT rule là COPY cũng kích hoạt nó

Không. COPY FROM có quy tắc riêng và không áp dụng rewrite rules như INSERT SQL.

### Hiểu lầm 6 — Rules tương thích tự nhiên với ON CONFLICT

Có những hạn chế cụ thể. Cần tránh DML rules trên targets dùng upsert trừ khi đã kiểm chứng và được hỗ trợ.

### Hiểu lầm 7 — INSERT ... RETURNING luôn lấy kết quả từ bảng được redirect

Không tự động. RETURNING trong rules có semantics và giới hạn riêng.

### Hiểu lầm 8 — Tạo view luôn làm query chậm hơn

View đơn giản có thể được planner tối ưu rất tốt sau rewrite.

### Hiểu lầm 9 — Tạo view tức là dữ liệu được lưu riêng

View thông thường không materialize kết quả; materialized view mới lưu kết quả vật lý theo cơ chế riêng.

### Hiểu lầm 10 — Mọi view đều tự cập nhật

Không. Automatic updatability có yêu cầu về cấu trúc view.

### Hiểu lầm 11 — View CHECK OPTION luôn áp qua custom INSTEAD rule

Không nên suy luận vậy. Các lớp view với rules/triggers có giới hạn và semantics cụ thể.

### Hiểu lầm 12 — Rule WHERE luôn tương đương row-level IF

Không. Đó là điều kiện của rewrite query, không phải một callback per-row.

### Hiểu lầm 13 — Rules là nơi tốt nhất để ghi audit

Không mặc định. Trigger hoặc logging/CDC phù hợp hơn cho nhiều nhu cầu audit.

### Hiểu lầm 14 — DO ALSO tạo log nên đã có exactly-once delivery

Không. Distributed delivery/retry/dedup cần thiết kế riêng.

### Hiểu lầm 15 — Rule có thể tự gọi lại vô hạn

Có nguy cơ recursive rewrite và lỗi; không dùng để xây loop.

### Hiểu lầm 16 — Không thấy _RETURN trong pg_rules tức view không có rewrite

Không nhất thiết. Có thể xem `pg_rewrite` và `pg_get_viewdef`.

### Hiểu lầm 17 — EXPLAIN phải hiện từng rule được áp dụng

EXPLAIN hiển thị kế hoạch sau rewrite/optimization, không phải một bản ghi log quy tắc.

### Hiểu lầm 18 — Rule cải thiện performance một cách mặc định

Nó có thể thêm công việc, tăng queries và chi phí.

### Hiểu lầm 19 — Privileges có thể được thay bằng rule

Không. Quyền và RLS phải thiết kế rõ.

### Hiểu lầm 20 — Thay rule là một thay đổi vô hại

Không. Caller có thể thay đổi hành vi dù câu SQL không thay đổi.

### Hiểu lầm 21 — Có trigger và rule audit cùng lúc thì “bảo vệ kép”

Có thể ghi log trùng, gây khó reconciliation.

### Hiểu lầm 22 — SQL bên trong rule action luôn chạy từng hàng

Không. Rule tạo query ở query level. Multi-row semantics cần hiểu riêng.

### Hiểu lầm 23 — Dùng now() để xác nhận action chỉ chạy một lần

now() có tính chất transaction timestamp, không phải phép đếm evaluation.

### Hiểu lầm 24 — Rule có thể thay một state machine nghiệp vụ

Thông thường nên dùng constraints, triggers, transactional functions/procedures hoặc service workflow được kiểm soát.

### Hiểu lầm 25 — View là security boundary tuyệt đối

Quyền/owner, RLS, security_barrier/security_invoker và threat model vẫn cần đánh giá.

## 48. Bài tập thực hành có lời giải

Các bài liên quan lab `rule375`. Những lệnh cố ý lỗi hoặc tác động dữ liệu phải chạy riêng trong môi trường thực hành.

### Bài 1. Rule thuộc tầng nào?

**Câu hỏi:** CREATE RULE được áp dụng trong parser, rewriter, planner hay executor?

**Đáp án:** chủ yếu ở **query rewriter**, sau giai đoạn phân tích cây truy vấn và trước planner/executor.

### Bài 2. Vì sao rule khác row trigger?

**Đáp án:** rule viết lại query tree theo event; row trigger chạy theo từng row trong executor theo trigger definition.

### Bài 3. Cú pháp tạo view phổ biến

```sql
CREATE VIEW rule375.only_coffee AS
SELECT product_id, product_name, unit_price
FROM rule375.products
WHERE category = 'coffee';
```

**Đáp án:** `CREATE VIEW` là cách đúng để yêu cầu view; PostgreSQL sử dụng rule `_RETURN` trong cơ chế view rewrite.

### Bài 4. View có lưu riêng data không?

**Đáp án:** view thông thường không materialize dữ liệu. Nó dựa trên định nghĩa query và dữ liệu gốc.

### Bài 5. Xem view definition

```sql
SELECT pg_get_viewdef(
    'rule375.active_products'::regclass,
    true
);
```

**Đáp án:** dùng `pg_get_viewdef`.

### Bài 6. Xem raw rewrite rule metadata

**Đáp án:** tra `pg_rewrite`, join `pg_class`/`pg_namespace` và dùng `pg_get_ruledef(r.oid, true)`.

### Bài 7. DO ALSO giữ lệnh gốc không?

**Đáp án:** có, và thêm rule action phù hợp theo rewrite semantics.

### Bài 8. DO INSTEAD giữ lệnh gốc không?

**Đáp án:** thay thế hành động gốc theo rule semantics.

### Bài 9. DO INSTEAD NOTHING là gì?

**Đáp án:** bỏ lệnh gốc trong phạm vi rule, không thực thi action thay thế.

### Bài 10. DELETE trên protected_notes có xóa hàng không?

```sql
DELETE FROM rule375.protected_notes
WHERE note_id = 1;
```

**Đáp án:** khi `protected_notes_no_delete` đang có hiệu lực, DELETE bị rewrite thành không thực hiện thao tác DELETE tương ứng.

### Bài 11. TRUNCATE có bị DELETE rule chặn không?

**Đáp án:** không. TRUNCATE là event khác, không chạy ON DELETE rewrite rule như row DELETE.

### Bài 12. Câu lệnh COPY FROM có áp rules như INSERT thông thường không?

**Đáp án:** không. COPY FROM không kích hoạt query rewrite rules kiểu INSERT; cần xem constraints/triggers riêng.

### Bài 13. OLD/NEW của rule có phải PL/pgSQL records?

**Đáp án:** không. Chúng là pseudo-relations trong query rewrite.

### Bài 14. OLD/NEW của AFTER ROW trigger dùng để làm gì?

**Đáp án:** đọc các trường của hàng cũ/mới trong ngữ cảnh row trigger thích hợp, ví dụ ghi lịch sử thay đổi.

### Bài 15. Multi-row INSERT có bảo đảm rule chạy một lần per row như trigger?

**Đáp án:** không; rule được áp dụng ở query-level.

### Bài 16. Khi cần audit chính xác các hàng cập nhật nên ưu tiên gì?

**Đáp án:** AFTER ROW trigger hoặc CDC/audit mechanism phù hợp, không mặc định DO ALSO rule.

### Bài 17. Tại sao không dùng CREATE RULE để gửi HTTP?

**Đáp án:** không giải quyết commit ordering, transaction rollback, retry, dedup và delivery. Nên dùng outbox/worker.

### Bài 18. View đơn giản có thể UPDATE qua view không?

**Đáp án:** có thể nếu đáp ứng điều kiện automatically updatable của PostgreSQL.

### Bài 19. WITH CHECK OPTION dùng khi nào?

**Đáp án:** trong updatable views phù hợp, để ngăn INSERT/UPDATE qua view tạo hàng không thỏa điều kiện view theo semantics được quy định.

### Bài 20. Cần viết view phức tạp cho phép INSERT theo từng row?

**Đáp án:** cân nhắc `INSTEAD OF` trigger hoặc API/function tường minh, thay vì tự viết DML rule không cần thiết.

### Bài 21. Một ON INSERT DO INSTEAD redirect có tự trả RETURNING từ bảng đích?

**Đáp án:** không mặc định. Cần thiết kế kết quả RETURNING và kiểm tra giới hạn rule cụ thể.

### Bài 22. Vì sao ON CONFLICT cần tránh relation có DML rules?

**Đáp án:** PostgreSQL có giới hạn tương thích với INSERT/UPDATE rules; rewrite có thể làm ngữ nghĩa upsert không được hỗ trợ. Dùng unique constraints và DML/triggers phù hợp.

### Bài 23. CHECK unit_price>=0 thay rule tốt hơn vì sao?

**Đáp án:** CHECK bảo vệ trạng thái dữ liệu, áp dụng nhất quán trong INSERT/UPDATE và không phải thao tác rewrite tùy ý.

### Bài 24. Muốn ngăn trùng external_id?

**Đáp án:** `PRIMARY KEY`/`UNIQUE`, không dùng rule dò tồn tại rồi INSERT có race.

### Bài 25. Muốn tenant 7 không đọc hàng tenant 8?

**Đáp án:** permissions/RLS kết hợp auth context đáng tin; rule không phải substitute.

### Bài 26. EXPLAIN SELECT qua view có thể hiện bảng gốc không?

**Đáp án:** có thể. View expansion diễn ra trước planner nên plan thường thể hiện scan/join trên bảng nguồn.

### Bài 27. Vì sao Seq Scan không chứng minh view kém hiệu năng?

**Đáp án:** planner chọn kế hoạch theo chi phí; với bảng nhỏ Seq Scan có thể rẻ hơn index scan.

### Bài 28. Tạo materialized view thì dữ liệu mới xuất hiện ngay sau INSERT nguồn?

**Đáp án:** không tự động. Cần REFRESH theo cơ chế phù hợp.

### Bài 29. Rule DO ALSO ghi log có bảo đảm log phát cho broker sau commit?

**Đáp án:** không. Cần outbox/CDC và worker với retry.

### Bài 30. Có thể dùng UPDATE rule để chặn giảm giá quá sâu theo từng row dễ dàng không?

**Đáp án:** không nên ưu tiên. Một BEFORE ROW trigger so OLD/NEW và raise exception có semantics dễ kiểm chứng hơn.

### Bài 31. Điều kiện WHERE trong CREATE RULE là WHERE của từng row trigger không?

**Đáp án:** không. Nó thuộc query rewrite semantics.

### Bài 32. Một rule tự INSERT lại bảng đích có rủi ro gì?

**Đáp án:** recursive rewrite/infinite expansion hoặc lỗi vòng lặp; cần thiết kế lại bằng SQL/trigger/procedure phù hợp.

### Bài 33. Có nên ghép nhiều DO ALSO rules như một pipeline có thứ tự cứng?

**Đáp án:** không, nếu logic cần tuần tự per-row chính xác. Dùng cấu trúc transaction/function/trigger rõ hơn.

### Bài 34. Có thể thay rule trong production mà không kiểm tra caller?

**Đáp án:** không. CREATE OR REPLACE RULE thay semantics những SQL gọi sẵn; cần migration/testing/rollback.

### Bài 35. DROP RULE cần chỉ rõ điều gì?

```sql
DROP RULE protected_notes_no_delete
ON rule375.protected_notes;
```

**Đáp án:** chỉ rõ tên rule và relation chủ quản sau `ON`.

### Bài 36. Để xem rule có enabled không?

**Đáp án:** tra `pg_rewrite.ev_enabled` và xem ngữ cảnh replication/session nếu cần.

### Bài 37. Tại sao security_barrier có thể cần?

**Đáp án:** hỗ trợ các kịch bản bảo vệ dữ liệu qua view khi đánh giá biểu thức/pushdown có thể ảnh hưởng ranh giới bảo mật. Vẫn cần quyền/RLS và threat model.

### Bài 38. security_invoker có tác động gì?

**Đáp án:** trong phiên bản hỗ trợ, nó ảnh hưởng cách quyền đối với quan hệ nền được kiểm tra khi gọi view. Cần xác nhận chính xác theo version và grants.

### Bài 39. Trigger outbox đã bảo đảm exactly-once external delivery chưa?

**Đáp án:** chưa. Nó giúp ghi event trong transaction; consumer vẫn cần retry, idempotency và xử lý duplicate/out-of-order.

### Bài 40. Khi nào có thể chủ đích chọn rewrite rule?

**Đáp án:** khi bài toán thực sự cần **query transformation ở tầng rewrite**, các giới hạn đã được hiểu và kiểm thử đầy đủ, thay vì logic row-by-row/validation/audit mà cơ chế khác phù hợp hơn.

## 49. Checklist thực tế trước khi tạo CREATE RULE

| Câu hỏi | Việc cần làm |
|---|---|
| Mục tiêu là view hay DML behavior? | View → CREATE VIEW trước |
| Có thể dùng automatically updatable view không? | Tránh custom DML rules |
| Có cần validate giá trị mỗi row? | CHECK/UNIQUE/FK/triggers |
| Có cần access control theo tenant? | RLS và grants |
| Có cần ghi audit từng row thật sự thay đổi? | AFTER ROW trigger |
| Có cần chuyển event ra hệ khác? | Outbox/CDC |
| Đã phân biệt OLD/NEW của rule và trigger? | Không viết logic theo mô hình sai |
| Rule là DO ALSO hay INSTEAD? | Diễn đạt tác động gốc rõ |
| Có conditional WHERE trong rule? | Xác minh rewrite semantics |
| Có nhiều rules trên cùng event? | Kiểm tra actions, overlap |
| Có nguy cơ recursive rewrite? | Tránh vòng rule tự tham chiếu |
| Có multi-row INSERT/UPDATE/DELETE? | Test bằng dữ liệu đại diện |
| Có INSERT ... SELECT? | Test biểu thức NEW và tập hàng |
| Có volatile expressions/defaults/sequences? | Kiểm tra evaluation semantics |
| Có COPY FROM? | Rules không chạy như INSERT |
| Có TRUNCATE? | Không phụ thuộc DELETE rules |
| Có ON CONFLICT? | Kiểm tra restriction |
| Có MERGE/CTE DML? | Kiểm tra restriction theo server |
| Có RETURNING? | Kiểm tra loại rule và output |
| View có CHECK OPTION? | Xem tính tương thích với INSTEAD rules/triggers |
| Có procedure/function cũng viết vào target? | Test toàn bộ đường ghi |
| View có chứa dữ liệu nhạy cảm? | Grants/RLS/security options |
| Có schema không đáng tin trong search_path? | Qualify tên và quản lý quyền |
| Có workload lớn? | Đo plan, WAL, locks và latency |
| Có kế hoạch migration và rollback? | Tránh đổi semantics đột ngột |
| Đã xem pg_rewrite/pg_get_ruledef? | Biết rules thực sự tồn tại |
| Có monitoring/audit khi thay đổi? | Phát hiện dữ liệu lệch |
| Có test trên PostgreSQL version thật? | Không suy luận qua engines khác |

## 50. Bảng tra cứu nhanh

| Cần làm | Cách tiếp cận |
|---|---|
| Định nghĩa tập đọc từ bảng gốc | `CREATE VIEW` |
| Xem logic của view | `pg_get_viewdef(regclass, true)` |
| Xem rule details | `pg_rewrite`, `pg_get_ruledef(oid, true)` |
| Tạo rule thêm action | `CREATE RULE ... DO ALSO ...` |
| Tạo rule thay action | `CREATE RULE ... DO INSTEAD ...` |
| Chặn một DELETE event bằng rewrite | `ON DELETE ... DO INSTEAD NOTHING` |
| Bỏ rule | `DROP RULE name ON relation` |
| Tự cập nhật view đơn giản | Automatically updatable view |
| Ngăn view DML thoát điều kiện lọc | `WITH CHECK OPTION` khi hỗ trợ |
| View phức tạp cần DML per-row | `INSTEAD OF` trigger |
| Chặn giá âm | `CHECK (price >= 0)` |
| Tránh trùng ID | `UNIQUE`/`PRIMARY KEY` |
| Bảo vệ tenant | Grants + RLS |
| Audit per-row | AFTER ROW trigger |
| Sửa NEW trước ghi | BEFORE ROW trigger |
| Đồng bộ event sau commit | Transactional outbox/CDC |
| Bulk import | `COPY FROM` + constraints/triggers phù hợp |
| Upsert | `INSERT ... ON CONFLICT` trên target phù hợp |
| Báo cáo cần cache vật lý | Materialized view + refresh |
| Tối ưu query view | `EXPLAIN` và indexes trên bảng nguồn |
| Kiểm soát thao tác xóa | Permissions, constraints/triggers và vận hành |
| Rule cho nghiệp vụ phức tạp | Cân nhắc lại; chỉ dùng khi thật sự cần rewrite |

## 51. Tài liệu PostgreSQL để tra cứu

Tất cả ví dụ nên được đối chiếu với **phiên bản PostgreSQL đang chạy**, đặc biệt ở những kết hợp DML rules, MERGE, RETURNING và view security options.

- [The Rule System](https://www.postgresql.org/docs/current/rules.html): giới thiệu query rewrite system.
- [The Query Tree](https://www.postgresql.org/docs/current/querytree.html): cấu trúc truy vấn phục vụ rewrite/planning.
- [Views and the Rule System](https://www.postgresql.org/docs/current/rules-views.html): cơ chế SELECT rules của views.
- [Rules on INSERT, UPDATE and DELETE](https://www.postgresql.org/docs/current/rules-update.html): DO ALSO/INSTEAD, OLD/NEW và rewrite DML.
- [Rules versus Triggers](https://www.postgresql.org/docs/current/rules-triggers.html): ranh giới giữa rewrite rules và triggers.
- [CREATE RULE](https://www.postgresql.org/docs/current/sql-createrule.html): cú pháp, giới hạn và lưu ý về RETURNING, rules và các câu SQL khác.
- [DROP RULE](https://www.postgresql.org/docs/current/sql-droprule.html): loại bỏ rule theo relation.
- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): tự cập nhật, CHECK OPTION và security options.
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): BEFORE/AFTER/INSTEAD OF, ROW/STATEMENT.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): ON CONFLICT/RETURNING.
- [COPY](https://www.postgresql.org/docs/current/sql-copy.html): bulk load và semantics.
- [TRUNCATE](https://www.postgresql.org/docs/current/sql-truncate.html): thao tác khác DELETE.
- [Materialized Views](https://www.postgresql.org/docs/current/rules-materializedviews.html): khác biệt với view thường.
- [pg_rewrite Catalog](https://www.postgresql.org/docs/current/catalog-pg-rewrite.html): metadata của rules.
- [pg_rules View](https://www.postgresql.org/docs/current/view-pg-rules.html): quan sát các rules.
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): bảo vệ quyền theo hàng.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): phân tích kế hoạch sau rewrite.

Các câu SQL của bài là **ví dụ hướng dẫn**, không phải kết quả đã chạy kiểm thử trên một database cụ thể. Khi triển khai thật, phải kiểm chứng theo version, privileges, migration, nghiệp vụ và dữ liệu đại diện.

## 52. Tổng kết

**Rules trong PostgreSQL là cơ chế viết lại truy vấn, không phải một loại trigger khác tên.**

Điểm cốt lõi:

```text
SQL đầu vào
    |
    v
Parse + Analyze
    |
    v
Rewrite rules
    |
    +-- _RETURN mở rộng view
    +-- DO ALSO bổ sung action
    +-- DO INSTEAD thay action
    +-- DO INSTEAD NOTHING loại bỏ action
    |
    v
Planner
    |
    v
Executor
```

Các nguyên tắc nên nhớ:

1. **`CREATE RULE` làm việc ở tầng rewrite**, không phải per-row callback.
2. **View là ứng dụng quan trọng của SELECT rule `_RETURN`**; muốn tạo view, hãy dùng `CREATE VIEW`.
3. **`DO ALSO` giữ hành động gốc và bổ sung action**; `DO INSTEAD` thay thế; `DO INSTEAD NOTHING` bỏ hành động theo rule.
4. **`OLD`/`NEW` trong rules là pseudo-relations của query rewrite**, khác OLD/NEW records của trigger.
5. **DML rules có ranh giới rõ** với multi-row operations, volatile expressions, RETURNING, ON CONFLICT và những cú pháp khác.
6. **`COPY FROM` không kích hoạt INSERT rules như một INSERT bình thường**; `TRUNCATE` không trở thành DELETE rule.
7. **Constraints bảo vệ dữ liệu**, **triggers xử lý row/statement events**, **RLS bảo vệ quyền**; đừng thay chúng bằng DO INSTEAD NOTHING.
8. **Audit chính xác và outbox** nên dùng những cơ chế có semantics transaction/row phù hợp, không mặc định dựa vào DO ALSO.
9. **View tự cập nhật được và INSTEAD OF triggers** thường dễ kiểm soát hơn việc tự thiết kế DML rules cho views.
10. **Rules không tự tăng tốc query**; đo plan sau rewrite và chi phí của các actions phát sinh.
11. **Quan sát rule qua pg_rewrite/pg_get_ruledef**, kiểm tra version và trạng thái enable.
12. **Migration rule là migration hành vi SQL**: có thể ảnh hưởng nhiều caller dù câu SQL gọi không đổi.

### Một câu để nhớ

> **Rule thay đổi câu lệnh mà PostgreSQL sẽ thực thi; trigger phản ứng với thao tác PostgreSQL đang thực thi.** Hãy dùng **view** cho biểu diễn dữ liệu, **constraint/RLS** cho những bất biến và giới hạn truy cập, **trigger** cho hành vi từng hàng, và chỉ chọn **query rewrite rule** khi đó thật sự là tầng biến đổi bạn cần.

