# Viết hàm bằng SQL và khả năng được tối ưu hóa trong PostgreSQL

Trong PostgreSQL, **hàm do người dùng định nghĩa** (*user-defined function*, UDF) cho phép đặt tên một phép tính hoặc một truy vấn để nhiều câu SQL có thể dùng lại. Khi logic chủ yếu là một biểu thức hoặc một câu `SELECT`, ngôn ngữ `SQL` thường là lựa chọn gọn và tự nhiên hơn việc chuyển ngay sang `PL/pgSQL`.

Ví dụ, hệ thống cần tính giá trị sau thuế theo một quy tắc đã thống nhất:

```sql
CREATE FUNCTION public.amount_with_tax(
    p_amount NUMERIC,
    p_rate_percent NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT ROUND(
        p_amount * (1 + p_rate_percent / 100),
        2
    );
$$;
```

Thay vì lặp công thức khắp ứng dụng:

```sql
SELECT
    order_id,
    public.amount_with_tax(amount, 8) AS total_after_tax
FROM orders;
```

Điểm thú vị là PostgreSQL **có thể tối ưu một số SQL-language function bằng cách đưa logic hàm vào câu truy vấn gọi nó**, một kỹ thuật thường được gọi là **SQL function inlining**. Khi có thể inline, planner nhìn thấy biểu thức hoặc truy vấn nền để cân nhắc index, bộ lọc, join order và chi phí thực thi.

Nhưng không phải mọi SQL function đều được inline. Các yếu tố như cấu trúc body, kiểu kết quả, tính biến động (*volatility*), `STRICT`, bảo mật, cấu hình `SET` của hàm và cách gọi đều có thể ảnh hưởng. Đôi khi hàm vẫn chạy đúng nhưng làm câu truy vấn khó tối ưu; đôi khi một hàm rất ngắn vẫn tạo overhead gọi lặp qua hàng triệu dòng.

Bài học này giải thích cách **viết hàm bằng SQL** và hiểu đúng **khả năng được tối ưu hóa** của PostgreSQL, từ cú pháp đến `EXPLAIN`, đánh đổi giữa tái sử dụng và hiệu năng, bảo mật, độ đúng ngữ nghĩa và chiến lược triển khai.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Viết SQL-language function bằng `CREATE FUNCTION ... LANGUAGE SQL`, tham số và kiểu trả về tường minh.
2. Phân biệt hàm trả **một giá trị** (*scalar*) với hàm trả **nhiều hàng** (*set-returning function*, SRF).
3. Tạo hàm `RETURNS TABLE`, `RETURNS SETOF`, `RETURNS void` và sử dụng kiểu kết quả phù hợp.
4. Hiểu cách truyền đối số vị trí, đối số đặt tên và tham số mặc định.
5. Phân biệt `IMMUTABLE`, `STABLE` và `VOLATILE`; hiểu ảnh hưởng đến tính đúng và optimizer.
6. Giải thích `STRICT`/`RETURNS NULL ON NULL INPUT` và hậu quả với NULL trong phép tính.
7. Hiểu `PARALLEL SAFE`, `PARALLEL RESTRICTED` và `PARALLEL UNSAFE`.
8. Giải thích **scalar inlining** và **table-function inlining** là gì, vì sao chúng hữu ích và tại sao không được đảm bảo.
9. Nhận biết những cấu hình/cấu trúc có thể ngăn inlining, nhất là `SECURITY DEFINER` hoặc `SET` trong function.
10. Dùng `EXPLAIN (ANALYZE, BUFFERS, VERBOSE)` để xem việc thực thi hàm qua dữ liệu nền.
11. Đánh giá `COST` và `ROWS` như những **ước lượng cho planner**, không phải cam kết thời gian chạy.
12. Sử dụng hàm SQL trong `SELECT`, `WHERE`, `JOIN LATERAL` và các truy vấn báo cáo.
13. Biết khi nào một wrapper làm giảm cơ hội dùng index hoặc khiến function được gọi quá nhiều lần.
14. Phân biệt function với `PROCEDURE` và `PL/pgSQL`.
15. Thiết kế quyền truy cập, `search_path`, overloading và thay đổi chữ ký hàm an toàn.
16. Kiểm thử kết quả, tính năng NULL, quyền và kế hoạch thực thi của hàm trước khi dùng production.

**Phạm vi:** PostgreSQL hiện đại. Các quy tắc inlining là những tối ưu phụ thuộc phiên bản và cấu trúc truy vấn, **không phải giao kèo SQL bắt buộc**. Phần lab sử dụng schema riêng, chỉ chạy trên database được phép tạo/xóa dữ liệu. STEP 4 tập trung viết nội dung bài; các bước kiểm thử nội dung trên dự án thực tế thuộc quy trình khác.

---

## 2. Tại sao dùng SQL function?

Có ba lý do chính.

### 2.1. Tránh lặp công thức

Nếu mười báo cáo cùng tính:

```sql
ROUND(amount * (1 + tax_rate / 100), 2)
```

thì một hàm có tên rõ ràng giúp mọi nơi dùng cùng cách tính.

### 2.2. Tạo giao diện truy vấn có tham số

Một hệ thống cần trả danh sách đơn của một tenant trong một khoảng thời gian:

```sql
SELECT *
FROM application.orders
WHERE tenant_id = 10
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+00';
```

Một SQL function có thể đóng gói truy vấn theo ba tham số `tenant_id`, `from_time` và `to_time`. Khác view thông thường, function có **danh sách tham số** do người gọi cung cấp.

### 2.3. Làm rõ ngữ nghĩa nghiệp vụ

Tên như `net_payment_amount`, `orders_in_period` hoặc `normalize_label` có thể thể hiện mục đích hơn một chuỗi biểu thức dài.

Tuy nhiên, tên hàm không làm logic tự đúng: một hàm `calculate_revenue` vẫn có thể sai nếu định nghĩa nhầm “giá trị đơn” với “tiền đã thu”.

### 2.4. Tái sử dụng không được đánh đổi với khả năng tối ưu một cách mù quáng

Một wrapper có thể giúp developer nhưng làm planner khó nhận ra predicate hoặc làm lặp hàng triệu lời gọi. Vì thế với function nằm trên đường truy vấn nóng, cần xem **cả hợp đồng dữ liệu lẫn kế hoạch thực thi**.

---

## 3. SQL function là gì? So với PL/pgSQL và procedure

Trong PostgreSQL, một hàm có thể được viết bằng nhiều ngôn ngữ, trong đó có `LANGUAGE SQL` và `LANGUAGE plpgsql`.

| Đặc điểm | SQL function | PL/pgSQL function | Procedure |
| --- | --- | --- | --- |
| Khai báo bằng | `CREATE FUNCTION` | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Ngôn ngữ | `LANGUAGE SQL` | `LANGUAGE plpgsql` | SQL hoặc ngôn ngữ phù hợp |
| Gọi thông thường | `SELECT f(...)` hoặc dùng trong biểu thức | `SELECT f(...)` | `CALL p(...)` |
| Phù hợp với | Biểu thức, một truy vấn, giao diện SELECT | Rẽ nhánh, vòng lặp, xử lý thủ tục | Tác vụ thủ tục, điều phối nhiều bước |
| Khả năng SQL function inlining | Một số trường hợp | Không theo cơ chế inline SQL-body tương tự | Không áp dụng như function trong biểu thức |
| Có thể làm side effects | Có, với logic và khai báo thích hợp | Có | Có |
| Transaction control | Không tự `COMMIT`/`ROLLBACK` như procedure | Không tự điều khiển transaction trong function | Một số trường hợp `CALL` cho phép điều khiển transaction theo giới hạn PostgreSQL |

**Không đồng nhất SQL function với stored procedure.** Trong PostgreSQL, `FUNCTION` được dùng trong biểu thức truy vấn và có kiểu trả về; `PROCEDURE` được gọi bằng `CALL` và có hợp đồng riêng.

### 3.1. SQL function không phải một “macro” luôn được thay văn bản

PostgreSQL lưu định nghĩa function và có thể:

- Inline một số function đủ điều kiện.
- Thực thi function theo cơ chế gọi thông thường.
- Dùng những metadata như volatility, COST, ROWS để xây plan.
- Áp dụng các tối ưu khác tùy query.

Vì thế dùng `LANGUAGE SQL` **tạo cơ hội** cho inlining, không đảm bảo function luôn được mở rộng.

### 3.2. Khi chọn PL/pgSQL

Nếu logic cần nhiều nhánh `IF`, vòng lặp, xử lý ngoại lệ, dynamic SQL hoặc workflow nhiều bước, PL/pgSQL thường hợp hơn.

Không cố ép một quy trình phức tạp vào một biểu thức SQL dài chỉ để hy vọng inline, vì readability và tính đúng vẫn là mục tiêu quan trọng.

---

## 4. Lab PostgreSQL: customers và orders

Ta xây dựng một bộ dữ liệu đủ để minh họa function scalar, function trả bảng, thống kê và kế hoạch truy vấn.

> **Cảnh báo:** Lệnh `DROP SCHEMA ... CASCADE` sẽ xóa mọi đối tượng trong schema lab cùng tên. Chỉ chạy trên **database thực hành được phép reset**, không chạy trên production hay schema chứa dữ liệu thật.

### 4.1. Tạo schema

```sql
DROP SCHEMA IF EXISTS sqlfn_lab CASCADE;
CREATE SCHEMA sqlfn_lab;
```

### 4.2. Bảng khách hàng

```sql
CREATE TABLE sqlfn_lab.customers (
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    display_name TEXT NOT NULL,
    segment TEXT NOT NULL
        CHECK (segment IN ('STANDARD', 'PREMIUM')),
    PRIMARY KEY (tenant_id, customer_id)
);
```

### 4.3. Bảng đơn hàng

```sql
CREATE TABLE sqlfn_lab.orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    customer_id INTEGER NOT NULL,
    ordered_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELED', 'REFUNDED')),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount >= 0),
    PRIMARY KEY (tenant_id, order_id),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES sqlfn_lab.customers(tenant_id, customer_id)
);
```

**Grain:** một hàng ở `orders` tương ứng một đơn trong một tenant. Trong mọi truy vấn JOIN cần giữ `tenant_id` để không ghép nhầm khách giữa tenants.

### 4.4. Tạo 600 khách hàng

```sql
INSERT INTO sqlfn_lab.customers (
    tenant_id, customer_id, display_name, segment
)
SELECT
    t.tenant_id,
    g.n,
    'Customer ' || t.tenant_id || '-' || g.n,
    CASE WHEN g.n % 5 = 0
         THEN 'PREMIUM'
         ELSE 'STANDARD'
    END
FROM (VALUES (10), (20)) AS t(tenant_id)
CROSS JOIN generate_series(1, 300) AS g(n);
```

### 4.5. Tạo 60.000 đơn

```sql
INSERT INTO sqlfn_lab.orders (
    tenant_id, order_id, customer_id,
    ordered_at, status, amount
)
SELECT
    CASE WHEN g.n % 2 = 0 THEN 10 ELSE 20 END,
    g.n::BIGINT,
    (g.n % 300) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 120) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second',
    CASE
        WHEN g.n % 10 = 0 THEN 'CANCELED'
        WHEN g.n % 10 = 1 THEN 'PENDING'
        WHEN g.n % 10 = 2 THEN 'REFUNDED'
        ELSE 'PAID'
    END,
    ROUND(
        10::NUMERIC + (g.n % 5000)::NUMERIC / 100,
        2
    )
FROM generate_series(1, 60000) AS g(n);
```

Tập dữ liệu có hai tenant, nhiều customer, nhiều trạng thái đơn và khoảng thời gian từ đầu tháng Một tới cuối tháng Tư 2026 theo UTC.

### 4.6. Tạo index phục vụ bộ lọc và JOIN

```sql
CREATE INDEX idx_sqlfn_orders_tenant_time
ON sqlfn_lab.orders (tenant_id, ordered_at);

CREATE INDEX idx_sqlfn_orders_tenant_status_time
ON sqlfn_lab.orders (tenant_id, status, ordered_at);

CREATE INDEX idx_sqlfn_orders_tenant_customer
ON sqlfn_lab.orders (tenant_id, customer_id);

ANALYZE sqlfn_lab.orders;
ANALYZE sqlfn_lab.customers;
```

Những index này là **ứng viên minh họa**. Trên hệ thống thực, không tạo nhiều index trùng mục đích mà chưa so chi phí đọc, ghi và dung lượng.

### 4.7. Kiểm tra dữ liệu gốc

```sql
SELECT
    tenant_id,
    COUNT(*) AS order_count,
    COUNT(*) FILTER (WHERE status = 'PAID') AS paid_count,
    SUM(amount) FILTER (WHERE status = 'PAID')
        AS paid_order_value
FROM sqlfn_lab.orders
GROUP BY tenant_id
ORDER BY tenant_id;
```

Ta có 60.000 đơn phân bố đều theo parity: **mỗi tenant 30.000 đơn**. Các số về trạng thái phụ thuộc công thức sinh dữ liệu đã nêu.

---

## 5. Cú pháp CREATE FUNCTION cơ bản

Một SQL function thường có cấu trúc:

```sql
CREATE FUNCTION schema_name.function_name(
    parameter_name parameter_type,
    ...
)
RETURNS return_type
LANGUAGE SQL
[volatility / null handling / parallel / cost options]
AS $$
    SELECT expression_or_query;
$$;
```

Các phần quan trọng:

- **Tên hàm và schema:** xác định đối tượng được gọi.
- **Tham số:** tên, kiểu, mode và giá trị mặc định nếu có.
- **RETURNS:** kết quả scalar, record, table hoặc set.
- **LANGUAGE SQL:** body được viết bằng ngôn ngữ SQL.
- **Thuộc tính:** `IMMUTABLE/STABLE/VOLATILE`, `STRICT`, `PARALLEL ...`, `COST`, `ROWS` và thuộc tính quyền.
- **Body:** truy vấn hoặc chuỗi câu lệnh SQL theo dạng cú pháp PostgreSQL hỗ trợ.

### 5.1. Hàm cộng đơn giản

```sql
CREATE FUNCTION sqlfn_lab.add_integers(
    p_a INTEGER,
    p_b INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_a + p_b;
$$;
```

Gọi:

```sql
SELECT sqlfn_lab.add_integers(5, 7) AS result;
```

Kết quả là `12`.

### 5.2. Tham số có thể tham chiếu bằng tên

Trong SQL function dạng string body, tham số được dùng qua tên khai báo:

```sql
SELECT p_a + p_b;
```

hoặc qua vị trí:

```sql
SELECT $1 + $2;
```

**Khuyến nghị:** đặt tên rõ ràng như `p_amount`, `p_rate` để tránh nhầm với tên cột trong query phức tạp. Khi tham số và tên cột trùng nhau, PostgreSQL có các quy tắc phân giải tên; không nên viết truy vấn mơ hồ.

### 5.3. Dùng dollar quoting

```sql
AS $$
    SELECT p_a + p_b;
$$;
```

Dollar-quoted string giúp tránh nhiều tầng escape dấu nháy đơn, nhất là body có chuỗi text. Có thể dùng tag như `$body$...$body$` khi cần lồng nhiều đoạn.

Dollar quotes là delimiter của định nghĩa, **không phải cách tham số hóa dữ liệu từ người dùng**. Lúc gọi function qua Java vẫn phải bind parameters.

---

## 6. Hàm scalar tính giá trị sau thuế

Ví dụ hàm chỉ làm phép tính:

```sql
CREATE FUNCTION sqlfn_lab.amount_with_tax(
    p_amount NUMERIC,
    p_rate_percent NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT ROUND(
        p_amount * (1 + p_rate_percent / 100),
        2
    );
$$;
```

### 6.1. Gọi trực tiếp

```sql
SELECT
    sqlfn_lab.amount_with_tax(100.00, 8) AS gross_value,
    sqlfn_lab.amount_with_tax(100.00, 0) AS no_tax;
```

Kết quả:

| gross_value | no_tax |
| ---: | ---: |
| 108.00 | 100.00 |

### 6.2. Gọi trong SELECT trên bảng

```sql
SELECT
    tenant_id,
    order_id,
    amount,
    sqlfn_lab.amount_with_tax(amount, 8)
        AS total_after_tax
FROM sqlfn_lab.orders
WHERE tenant_id = 10
ORDER BY ordered_at DESC, order_id DESC
LIMIT 10;
```

### 6.3. Vì sao IMMUTABLE ở đây hợp lý?

Với cùng hai số đầu vào, hàm chỉ áp dụng toán học thập phân và làm tròn. Nó không đọc bảng, thời gian hiện tại hay trạng thái session có thể thay đổi kết quả.

**Tuy nhiên:** một công thức về thuế theo năm, quốc gia hay luật hiện hành mà kết quả phụ thuộc bảng cấu hình không còn là hàm thuần tương tự. Không đánh dấu `IMMUTABLE` chỉ vì chức năng có tên “calculate tax”.

### 6.4. Vì sao STRICT?

Nếu `p_amount` hoặc `p_rate_percent` là NULL, việc tính số tiền sau thuế chưa xác định. `STRICT` cho PostgreSQL biết hàm trả NULL ngay khi có bất kỳ đối số NULL nào; body không cần được gọi trong trường hợp đó.

### 6.5. Rounding là một phần contract

`ROUND(...,2)` là chính sách làm tròn tại đây. Nếu nghiệp vụ phải làm tròn từng dòng đơn trước khi tổng hợp, kết quả có thể khác với tổng trước rồi làm tròn. Function tái sử dụng giúp thống nhất chính sách, nhưng không tự quyết định chính sách đúng.

---

## 7. RETURNS NULL ON NULL INPUT và CALLED ON NULL INPUT

PostgreSQL cho phép khai báo cách hàm xử lý đầu vào NULL.

### 7.1. STRICT

Hai dạng dưới đây tương đương về thuộc tính xử lý NULL:

```sql
STRICT
```

và:

```sql
RETURNS NULL ON NULL INPUT
```

Khi một đối số là NULL, PostgreSQL trả NULL mà không chạy body theo cách thông thường.

Ví dụ:

```sql
SELECT sqlfn_lab.amount_with_tax(
    NULL::NUMERIC,
    8::NUMERIC
);
```

Kết quả `NULL`.

### 7.2. CALLED ON NULL INPUT

Đây là hành vi mặc định nếu không khai báo STRICT. Body vẫn được gọi để tự quyết định NULL semantics.

Ví dụ hàm chấp nhận NULL như 0:

```sql
CREATE FUNCTION sqlfn_lab.null_to_zero(
    p_value NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
CALLED ON NULL INPUT
PARALLEL SAFE
AS $$
    SELECT COALESCE(p_value, 0::NUMERIC);
$$;
```

```sql
SELECT
    sqlfn_lab.null_to_zero(NULL::NUMERIC) AS a,
    sqlfn_lab.null_to_zero(15::NUMERIC) AS b;
```

Kết quả `a=0`, `b=15`.

### 7.3. Đánh dấu STRICT sai có thể đổi kết quả

Nếu hàm `null_to_zero` bị đánh dấu STRICT, `null_to_zero(NULL)` sẽ trả NULL trước khi chạy `COALESCE`, trái với ý nghĩa “NULL thành 0”.

**Thuộc tính function là một phần semantics**, không phải chỉ là metadata để tăng tốc.

---

## 8. Tham số mặc định và gọi bằng tên

SQL function có thể nhận tham số mặc định:

```sql
CREATE FUNCTION sqlfn_lab.add_percent(
    p_amount NUMERIC,
    p_percent NUMERIC DEFAULT 10
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_amount * (1 + p_percent / 100);
$$;
```

Gọi theo vị trí:

```sql
SELECT
    sqlfn_lab.add_percent(100) AS default_ten_percent,
    sqlfn_lab.add_percent(100, 5) AS five_percent;
```

Gọi bằng tên:

```sql
SELECT sqlfn_lab.add_percent(
    p_percent => 12,
    p_amount => 100
) AS twelve_percent;
```

### 8.1. Lưu ý overload và DEFAULT

PostgreSQL hỗ trợ **function overloading**: nhiều hàm cùng tên nhưng khác kiểu/danh sách tham số đầu vào.

Khi kết hợp overload với default arguments và implicit casts, lời gọi có thể trở nên mơ hồ hoặc chọn một overload không mong đợi.

Không tạo hàng loạt biến thể trùng tên/kiểu gần giống rồi kỳ vọng PostgreSQL luôn chọn đúng theo trực giác.

### 8.2. DEFAULT khác NULL

Nếu người gọi bỏ p_percent, DEFAULT 10 được dùng. Nhưng nếu người gọi **truyền NULL**, đó vẫn là một đối số NULL, và function STRICT trả NULL.

```sql
SELECT
    sqlfn_lab.add_percent(100) AS omitted,
    sqlfn_lab.add_percent(100, NULL::NUMERIC)
        AS explicit_null;
```

Hai kết quả lần lượt là 110 và NULL.

---

## 9. SQL function có thể trả nhiều hàng

Để tái sử dụng một truy vấn có tham số, dùng `RETURNS TABLE`.

```sql
CREATE FUNCTION sqlfn_lab.orders_in_period(
    p_tenant_id INTEGER,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ
)
RETURNS TABLE (
    tenant_id INTEGER,
    order_id BIGINT,
    ordered_at TIMESTAMPTZ,
    status TEXT,
    amount NUMERIC
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
ROWS 100
AS $$
    SELECT
        o.tenant_id,
        o.order_id,
        o.ordered_at,
        o.status,
        o.amount
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.ordered_at >= p_from
      AND o.ordered_at < p_to;
$$;
```

### 9.1. Gọi hàm trả bảng trong FROM

```sql
SELECT *
FROM sqlfn_lab.orders_in_period(
    10,
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
)
ORDER BY ordered_at, order_id
LIMIT 20;
```

Function trả nhiều hàng được dùng như một nguồn dữ liệu trong `FROM`.

### 9.2. RETURNS TABLE là một hợp đồng cột

Ở đây caller được hứa các cột:

```text
tenant_id    INTEGER
order_id     BIGINT
ordered_at   TIMESTAMPTZ
status       TEXT
amount       NUMERIC
```

Thứ tự, tên và kiểu của cột quan trọng cho code nhận dữ liệu. Nếu body đổi thứ tự cột hoặc trả kiểu không khớp, PostgreSQL có thể báo lỗi khi tạo hoặc khi thực thi, tùy dạng body và cách kiểm tra.

### 9.3. Vì sao STABLE?

Hàm đọc bảng `orders` theo một truy vấn SELECT. Kết quả phụ thuộc dữ liệu trong database và có thể thay đổi giữa các statement/transaction. Vì thế **không nên đánh dấu IMMUTABLE**.

`STABLE` diễn đạt lời hứa phù hợp cho một hàm chỉ đọc bảng và quan sát snapshot nhất quán theo quy tắc PostgreSQL dành cho STABLE function. Nhưng tính đúng còn phụ thuộc body thực tế và các hàm mà body gọi.

### 9.4. Vì sao không ORDER BY trong function?

Trật tự hiển thị là trách nhiệm caller khi cần một hợp đồng sắp xếp:

```sql
ORDER BY ordered_at DESC, order_id DESC
```

Một hàm trả tập hợp không nên khiến client phụ thuộc vào thứ tự tình cờ của plan. Nếu dùng LIMIT, hãy gắn với ORDER BY xác định trong cùng truy vấn mà cần lấy top-N.

### 9.5. Vì sao khai báo ROWS 100?

`ROWS` là **ước lượng số hàng trả về** cho planner đối với set-returning function, không phải giới hạn. Nếu kỳ này có 10.000 đơn phù hợp, function vẫn có thể trả 10.000; `ROWS 100` chỉ làm cost estimates giả định theo giá trị đã khai báo khi áp dụng.

---

## 10. RETURNS SETOF: một cách khác trả tập hợp

Một hàm có thể trả nhiều giá trị cùng một kiểu:

```sql
CREATE FUNCTION sqlfn_lab.recent_tenant_order_ids(
    p_tenant_id INTEGER,
    p_limit INTEGER DEFAULT 10
)
RETURNS SETOF BIGINT
LANGUAGE SQL
STABLE
ROWS 10
AS $$
    SELECT o.order_id
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT GREATEST(p_limit, 0);
$$;
```

Gọi:

```sql
SELECT order_id
FROM sqlfn_lab.recent_tenant_order_ids(10, 5)
    AS result(order_id);
```

### 10.1. SETOF khác scalar

- `RETURNS BIGINT`: một giá trị BIGINT (hoặc NULL).
- `RETURNS SETOF BIGINT`: không, một hoặc nhiều giá trị BIGINT.
- `RETURNS TABLE (...)`: không, một hoặc nhiều hàng có nhiều cột xác định.

### 10.2. LIMIT là một phần semantics

Hàm này cố ý giới hạn kết quả và có ORDER BY trong SELECT gốc để chọn top-N. Nhưng caller vẫn nên đặt ORDER BY ngoài cùng nếu cần thứ tự trình bày được bảo đảm ở kết quả cuối cùng.

### 10.3. ROWS không đồng nghĩa LIMIT

`ROWS 10` là planner hint, còn `LIMIT GREATEST(p_limit,0)` thực sự giới hạn số hàng. Không nhầm hai cấu trúc.

### 10.4. RETURNS void

Hàm SQL cũng có thể trả `void`. Loại này phù hợp với một số thao tác không cần kết quả, nhưng nếu mục đích chính là nhiều bước vận hành, có side effects và cần điều khiển transaction, hãy so với procedure/PL/pgSQL thay vì lạm dụng SQL function chỉ vì nó có thể dùng `RETURNS void`.

---

## 11. Một hàm tổng hợp báo cáo với RETURNS TABLE

Ví dụ báo cáo số đơn PAID và tổng giá trị đơn theo ngày UTC trong một khoảng thời gian cho một tenant:

```sql
CREATE FUNCTION sqlfn_lab.daily_paid_order_value(
    p_tenant_id INTEGER,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ
)
RETURNS TABLE (
    day_utc DATE,
    paid_order_count BIGINT,
    paid_order_value NUMERIC
)
LANGUAGE SQL
STABLE
PARALLEL SAFE
ROWS 120
AS $$
    SELECT
        (o.ordered_at AT TIME ZONE 'UTC')::DATE
            AS day_utc,
        COUNT(*) AS paid_order_count,
        SUM(o.amount) AS paid_order_value
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.status = 'PAID'
      AND o.ordered_at >= p_from
      AND o.ordered_at < p_to
    GROUP BY
        (o.ordered_at AT TIME ZONE 'UTC')::DATE;
$$;
```

Gọi:

```sql
SELECT
    day_utc,
    paid_order_count,
    paid_order_value
FROM sqlfn_lab.daily_paid_order_value(
    10,
    TIMESTAMPTZ '2026-01-01 00:00:00+00',
    TIMESTAMPTZ '2026-02-01 00:00:00+00'
)
ORDER BY day_utc;
```

### 11.1. Vì sao COUNT(*) trả BIGINT?

Trong PostgreSQL, `COUNT(*)` trả `BIGINT`. Vì thế cột `paid_order_count BIGINT` khớp kiểu kết quả.

### 11.2. Vì sao SUM(amount) trả NUMERIC?

`amount` là `NUMERIC` nên tổng cũng là `NUMERIC`. Nếu hàm khai báo `INTEGER` hoặc `BIGINT` không phù hợp, có thể phải ép kiểu hoặc thay thiết kế.

### 11.3. Kết quả không có hàng

Khi khoảng ngày không có đơn PAID, query `GROUP BY day_utc` không tạo nhóm. Function `RETURNS TABLE` này trả **0 hàng** chứ không phải một hàng tổng bằng 0.

Nếu dashboard cần đủ mọi ngày kể cả ngày không có đơn, cần dùng `generate_series` làm calendar dimension rồi LEFT JOIN kết quả theo ngày, hoặc thiết kế function có contract tạo dãy ngày.

### 11.4. Ngữ nghĩa doanh thu

`paid_order_value` trong ví dụ chỉ là SUM amount của những đơn **đang có status PAID**, nhóm theo **ngày đặt đơn UTC**. Nó không phải dòng tiền thực nhận, không tính thời điểm thanh toán và hoàn tiền. Tên hàm/README phải thể hiện chính xác quy tắc.

---

## 12. SQL function sử dụng trong JOIN LATERAL

Một function trả bảng nhận tham số từ hàng phía ngoài có thể được gọi bằng `LATERAL`.

Ví dụ: mỗi khách của tenant 10 cần tối đa ba ID đơn mới nhất.

```sql
CREATE FUNCTION sqlfn_lab.latest_order_ids_for_customer(
    p_tenant_id INTEGER,
    p_customer_id INTEGER,
    p_limit INTEGER DEFAULT 3
)
RETURNS TABLE (
    order_id BIGINT,
    ordered_at TIMESTAMPTZ
)
LANGUAGE SQL
STABLE
ROWS 3
AS $$
    SELECT o.order_id, o.ordered_at
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.customer_id = p_customer_id
    ORDER BY o.ordered_at DESC, o.order_id DESC
    LIMIT GREATEST(p_limit, 0);
$$;
```

Gọi:

```sql
SELECT
    c.customer_id,
    c.display_name,
    x.order_id,
    x.ordered_at
FROM sqlfn_lab.customers AS c
LEFT JOIN LATERAL
    sqlfn_lab.latest_order_ids_for_customer(
        c.tenant_id, c.customer_id, 3
    ) AS x ON TRUE
WHERE c.tenant_id = 10
  AND c.customer_id IN (1, 2, 3)
ORDER BY c.customer_id, x.ordered_at DESC NULLS LAST;
```

### 12.1. LATERAL để tham chiếu dữ liệu phía ngoài

Function nhận `c.tenant_id`, `c.customer_id` của từng khách hiện tại. `LEFT JOIN LATERAL` giữ khách kể cả khi function trả 0 hàng.

### 12.2. Không mặc định đây là tối ưu nhất cho mọi customer

Với ba khách, truy cập qua index có thể phù hợp. Với hàng triệu khách, repeated function scans có thể đắt. Cần so sánh với:

- `ROW_NUMBER() OVER (PARTITION BY customer_id ...)`.
- `DISTINCT ON` khi chỉ cần top-1.
- Query JOIN trực tiếp và planner tối ưu.
- Pre-aggregation hoặc read model khi báo cáo lặp nhiều.

**LATERAL và SQL function mang ý nghĩa tái sử dụng, không tự là “một scan duy nhất”.**

### 12.3. Index cần phù hợp

Một ứng viên cho truy vấn top-N per customer:

```sql
CREATE INDEX idx_sqlfn_orders_customer_latest
ON sqlfn_lab.orders (
    tenant_id, customer_id,
    ordered_at DESC, order_id DESC
);
```

Index này có thể giúp tìm nhanh nhóm một khách theo thứ tự ngày giảm dần. Tuy nhiên, thêm index có chi phí INSERT/UPDATE/DELETE và dung lượng; cần đo workload thật.

---

## 13. Volatility: IMMUTABLE, STABLE và VOLATILE

PostgreSQL dùng metadata **function volatility** để biết giới hạn của việc tái sử dụng kết quả, tối ưu biểu thức và quan sát snapshot.

| Thuộc tính | Lời hứa cơ bản | Ví dụ phù hợp |
| --- | --- | --- |
| `IMMUTABLE` | Cùng input luôn cho cùng output trong mọi lần gọi theo ngữ nghĩa ổn định | Cộng số, đổi đơn vị thuần túy |
| `STABLE` | Cùng input cho cùng kết quả trong phạm vi một statement theo contract; không sửa database | Đọc cấu hình/bảng theo snapshot, hàm dựa trạng thái ổn định trong statement |
| `VOLATILE` | Có thể thay kết quả hoặc side effects giữa các lần gọi; cần bảo toàn semantics | `random()`, `clock_timestamp()`, thao tác DML |
 
**Mặc định:** nếu không khai báo volatility, PostgreSQL coi hàm là `VOLATILE`.

### 13.1. IMMUTABLE

Ví dụ:

```sql
CREATE FUNCTION sqlfn_lab.percent_of(
    p_part NUMERIC,
    p_whole NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT 100::NUMERIC
           * p_part
           / NULLIF(p_whole, 0);
$$;
```

Với cùng hai input số, kết quả tính toán không phụ thuộc vào dữ liệu bảng hoặc thời gian.

Lưu ý: nếu p_whole=0, hàm trả NULL do `NULLIF`; không nên tự hứa kết quả luôn là một số.

### 13.2. STABLE

Ví dụ function đọc đơn:

```sql
CREATE FUNCTION sqlfn_lab.tenant_order_count(
    p_tenant_id INTEGER
)
RETURNS BIGINT
LANGUAGE SQL
STABLE
AS $$
    SELECT COUNT(*)
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id;
$$;
```

Kết quả phụ thuộc nội dung bảng nên **không IMMUTABLE**. Với STABLE, PostgreSQL có các quy tắc snapshot ổn định phù hợp cho truy vấn đọc.

### 13.3. VOLATILE

Ví dụ:

```sql
CREATE FUNCTION sqlfn_lab.current_wall_clock()
RETURNS TIMESTAMPTZ
LANGUAGE SQL
VOLATILE
AS $$
    SELECT clock_timestamp();
$$;
```

`clock_timestamp()` có thể thay đổi ngay trong một statement. Không đánh dấu IMMUTABLE hoặc STABLE cho một wrapper muốn bảo toàn giá trị đồng hồ thực mỗi lần đánh giá.

### 13.4. CURRENT_TIMESTAMP, now() và clock_timestamp()

Trong PostgreSQL:

- `CURRENT_TIMESTAMP` và `now()` thể hiện thời điểm bắt đầu transaction theo semantics tương ứng, có thể dùng phù hợp với tính ổn định trong transaction.
- `statement_timestamp()` cho thời điểm bắt đầu statement.
- `clock_timestamp()` đọc đồng hồ thực và có thể thay đổi giữa các lời gọi.

Không đánh dấu wrapper gọi thời gian hiện tại là `IMMUTABLE`. Với `clock_timestamp()`, mô tả đúng thường là `VOLATILE`.

### 13.5. Không đánh dấu đọc bảng là IMMUTABLE

Sai về lời hứa:

```sql
-- KHÔNG làm theo:
-- CREATE FUNCTION current_tax_rate()
-- RETURNS numeric IMMUTABLE
-- AS $$ SELECT rate FROM tax_rates ... $$ LANGUAGE SQL;
```

Bảng thuế thay đổi thì cùng input có thể cho kết quả khác. Nếu khai báo IMMUTABLE, PostgreSQL có thể áp dụng constant folding, cache assumptions hoặc index expression theo giả định không đúng, dẫn đến dữ liệu/kế hoạch sai.

### 13.6. Volatility là cam kết của tác giả

PostgreSQL không thể tự kiểm chứng toàn bộ mọi logic/side effects của hàm hoặc hàm con, đặc biệt khi có dynamic behaviors. Người viết phải phân loại trung thực; việc khai báo sai có thể nguy hiểm hơn một chút overhead.

---

## 14. Volatility và snapshot visibility

Thuộc tính volatility không chỉ ảnh hưởng hiệu năng; nó còn ảnh hưởng cách SQL function nhìn các thay đổi database.

### 14.1. STABLE và IMMUTABLE

SQL statements bên trong function được mô tả theo cơ chế snapshot ổn định phù hợp với statement gọi, giúp kết quả trong phạm vi statement nhất quán theo contract.

### 14.2. VOLATILE

VOLATILE function có semantics cho phép nhìn các thay đổi mới khi thực thi các câu lệnh SQL bên trong theo quy tắc PostgreSQL. Đây là một khác biệt thực tế với STABLE, không chỉ một hint để planner.

### 14.3. Hàm gọi hàm khác phải có volatility đúng

Nếu wrapper gọi một hàm VOLATILE, không nên dán nhãn STABLE/IMMUTABLE chỉ để mong được inline.

Ví dụ:

```sql
-- Không khai báo IMMUTABLE cho hàm dựa trên random().
SELECT random();
```

### 14.4. Khi nào phải có VOLATILE?

Nếu function cần thay đổi database hoặc gọi hoạt động có side effects và hành vi phụ thuộc mỗi lần thực thi, VOLATILE là phân loại phù hợp trong những giới hạn PostgreSQL.

### 14.5. Volatility không làm query tự động thread-safe

Một function STABLE/IMMUTABLE không thay thế transaction isolation, khóa hoặc unique constraints. Nó chỉ mô tả đặc tính kết quả/side effects để optimizer và executor có thể xử lý thích hợp.

---

## 15. PostgreSQL có thể inline function theo cách nào?

**Inlining** là tối ưu nơi planner thay một lời gọi SQL function đủ điều kiện bằng biểu thức hoặc cấu trúc truy vấn body để tối ưu chung với câu gọi.

Hai nhóm thường được nhắc đến:

1. **Scalar SQL function inlining:** hàm trả một giá trị được mở rộng như biểu thức.
2. **Table SQL function inlining:** một function trả tập hợp có body SELECT được xem như một subquery trong câu gọi.

Ví dụ scalar:

```text
SELECT amount_with_tax(amount, 8)
                 |
                 | có thể inline
                 v
SELECT ROUND(amount * (1 + 8 / 100), 2)
```

Ví dụ table function:

```text
SELECT *
FROM orders_in_period(10, from_t, to_t)
WHERE status = 'PAID'
                  |
                  | có thể inline trong điều kiện phù hợp
                  v
SELECT ...
FROM orders
WHERE tenant_id = 10
  AND ordered_at >= from_t
  AND ordered_at < to_t
  AND status = 'PAID'
```

Đây là **mô hình tư duy**, không phải cam kết plan/exact SQL text mà PostgreSQL buộc phải tạo.

### 15.1. Lợi ích của scalar inlining

- Giảm overhead gọi function trên nhiều hàng trong trường hợp thích hợp.
- Planner thấy biểu thức thật để áp dụng các phép biến đổi an toàn.
- Có thể tận dụng expression matching cho index hoặc thống kê khi phù hợp.
- Một số biểu thức hằng có thể được rút gọn theo quy tắc volatility.

### 15.2. Lợi ích của table-function inlining

- Có thêm cơ hội đẩy predicate bên ngoài vào bảng nền.
- Có thêm thông tin về relation và index cho planner.
- Có thể phối hợp JOIN order và estimate tốt hơn.
- Tránh phải xem function như một black-box chỉ có COST/ROWS.

### 15.3. Quan trọng nhất: “có thể”

Có nhiều điều kiện về:

- SQL-language body.
- Một hoặc nhiều câu lệnh.
- Loại kết quả.
- Volatility.
- STRICT.
- SECURITY DEFINER/SECURITY INVOKER.
- Cấu hình SET của function.
- Đặc điểm tham số/thân hàm.
- Kết cấu ORDER BY/LIMIT, CTE, side effects và điều kiện an toàn.
- Phiên bản PostgreSQL và planner implementation.

Không viết quy tắc máy móc “LANGUAGE SQL + STABLE = luôn inline”. Phải **quan sát plan của truy vấn thật**.

---

## 16. Scalar inlining: ví dụ hàm biểu thức

Xét function:

```sql
CREATE FUNCTION sqlfn_lab.plus_one(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_value + 1;
$$;
```

Truy vấn:

```sql
EXPLAIN (VERBOSE)
SELECT sqlfn_lab.plus_one(10) AS result;
```

Với phiên bản và điều kiện phù hợp, planner có thể rút gọn lời gọi thành một biểu thức/hằng thay vì thực thi function như black box mỗi khi dùng.

### 16.1. Hằng hóa không chứng minh mọi lời gọi đều inline

Nếu EXPLAIN với tham số hằng trả một giá trị đã được rút gọn, điều đó không chứng minh cùng function sẽ inline cho mọi cách gọi, nhất là khi body phức tạp, có security settings hoặc lời gọi chứa biểu thức volatile.

### 16.2. Inlining và STRICT

`STRICT` có lợi trong nhiều tình huống, nhưng **không phải mọi SQL function STRICT đều đủ điều kiện scalar inlining**. Planner cần bảo đảm ngữ nghĩa NULL được giữ nguyên; các biểu thức/body phải thỏa các điều kiện an toàn tương ứng.

Ví dụ:

```sql
CREATE FUNCTION sqlfn_lab.maybe_zero(
    p_value NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
CALLED ON NULL INPUT
IMMUTABLE
AS $$
    SELECT COALESCE(p_value, 0);
$$;
```

Function này cố ý không STRICT. Nếu đánh dấu STRICT, kết quả trên NULL đổi nghĩa. Một function không STRICT vẫn có thể được inline trong trường hợp phù hợp; metadata và logic phải khớp.

### 16.3. Scalar function có nhiều SELECT không tương đương một expression

Một SQL function có thể chứa nhiều statement trong body theo cú pháp hỗ trợ. Nhưng không suy ra nó có thể inline như một biểu thức scalar đơn giản.

Khi function chỉ tính một giá trị, viết **một SELECT biểu thức** thường dễ đọc và mở ra cơ hội tối ưu hơn.

---

## 17. Table-function inlining và predicate pushdown

Truy vấn trực tiếp trên function:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    order_id,
    ordered_at,
    amount
FROM sqlfn_lab.orders_in_period(
    10,
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
)
WHERE status = 'PAID'
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
```

### 17.1. Khi được inline

Planner có thể thấy bảng `sqlfn_lab.orders` và kết hợp:

```sql
o.tenant_id = 10
AND o.ordered_at >= ...
AND o.ordered_at < ...
AND o.status = 'PAID'
```

Từ đó index `(tenant_id, status, ordered_at)` trở thành ứng viên hữu ích.

### 17.2. Khi không được inline

Một dạng plan có thể chứa node:

```text
Function Scan on sqlfn_lab.orders_in_period ...
    Filter: (status = 'PAID')
```

Tức phía ngoài phải đọc kết quả function rồi mới áp dụng một phần điều kiện, không tận dụng được khả năng planner xuyên qua body như tình huống inline.

### 17.3. Không coi “Function Scan” là lỗi SQL

Function Scan là một cơ chế thực thi hợp lệ. Với tập kết quả nhỏ hoặc logic thực sự phải đóng thành black box, nó có thể chấp nhận được.

Vấn đề cần điều tra là: **chi phí và tính đúng** có đạt mục tiêu không, và có một cách viết khác dễ tối ưu hơn hay không?

### 17.4. Đọc EXPLAIN để biết điều kiện được áp dụng ở đâu

Quan sát:

- `Index Cond` trên bảng nền.
- `Filter` ở node bảng nền hay node Function Scan.
- Số hàng thực tế.
- Buffers hit/read.
- Thời gian tổng và số lần function được gọi.
- Có Sort hay Materialize trung gian không.

Đừng chỉ nhìn chữ `Function Scan` rồi quyết định toàn bộ truy vấn chậm; cũng đừng nhìn một lần `Index Scan` rồi kết luận function luôn nhanh trong production.

---

## 18. Những yếu tố thường hạn chế SQL function inlining

Các quy tắc cụ thể của PostgreSQL có tính kỹ thuật và có thể thay đổi theo phiên bản. Tuy nhiên, những yếu tố sau rất đáng kiểm tra.

### 18.1. SECURITY DEFINER

Một function `SECURITY DEFINER` chạy bằng quyền của owner theo contract bảo mật. Planner không thể tùy tiện thay body vào query của caller nếu việc đó làm mất ranh giới quyền.

Vì vậy **SECURITY DEFINER thường ngăn các kiểu SQL function inlining liên quan**. Đây là sự đánh đổi bảo mật có chủ đích.

### 18.2. Function có SET configuration

Ví dụ:

```sql
CREATE FUNCTION sqlfn_lab.plus_one_with_setting(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
SET search_path = pg_catalog, sqlfn_lab
AS $$
    SELECT p_value + 1;
$$;
```

Thuộc tính `SET` tạo ngữ cảnh cấu hình khi thực thi function; điều này thường không tương thích với việc inline như một biểu thức ngoài ngữ cảnh function.

Không xóa `SET search_path` khỏi một SECURITY DEFINER function chỉ để ép inlining nếu nó cần thiết cho an toàn.

### 18.3. Volatility/side effects

Nếu function được đánh dấu `VOLATILE` hoặc body chứa yếu tố không an toàn cho việc thay thế, planner phải giữ nguyên semantics số lần và thứ tự đánh giá thích hợp.

### 18.4. Multiple statements hoặc cấu trúc phức tạp

Một body nhiều statements không đơn giản tương đương một biểu thức hay một SELECT table function. Điều kiện inline sẽ khắt khe hơn hoặc không áp dụng.

### 18.5. STRICT và NULL semantics

Với scalar function, planner phải chứng minh việc mở rộng giữ được kết quả khi đối số NULL. Một số body không đáp ứng điều kiện này, dù function được khai báo STRICT.

Ngược lại, set-returning table functions thường có những điều kiện khác, và việc khai báo STRICT có thể ảnh hưởng khả năng inline theo cơ chế riêng.

### 18.6. Các thuộc tính bảo mật hoặc biểu thức bất thường

Set-returning expressions, tham số chứa volatile expressions, security barriers, kiểu trả về phức tạp và các ngữ nghĩa cần bảo toàn có thể hạn chế inlining.

### 18.7. Cách thực hành đúng

Đừng tự tạo một danh sách điều kiện rồi xem nó là định lý đủ. Dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT ...
FROM your_function(...);
```

và so với truy vấn trực tiếp tương đương. Chỉ đánh giá trên dữ liệu và phiên bản thực tế.

---

## 19. Predicate pushdown: điều kiện nên ở trong hay ngoài function?

Giả sử function trả **mọi đơn trong một khoảng ngày** và caller lọc PAID:

```sql
SELECT *
FROM sqlfn_lab.orders_in_period(
    10,
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
)
WHERE status = 'PAID';
```

Nếu function inline và planner đẩy status predicate vào bảng orders, chi phí có thể tốt. Nhưng nếu function được thực thi tách rời, nó có thể trả nhiều hàng rồi mới lọc.

### 19.1. Một function hẹp hơn theo use case

Khi workload luôn cần PAID, có thể công bố một function riêng:

```sql
CREATE FUNCTION sqlfn_lab.paid_orders_in_period(
    p_tenant_id INTEGER,
    p_from TIMESTAMPTZ,
    p_to TIMESTAMPTZ
)
RETURNS TABLE (
    tenant_id INTEGER,
    order_id BIGINT,
    ordered_at TIMESTAMPTZ,
    amount NUMERIC
)
LANGUAGE SQL
STABLE
ROWS 100
AS $$
    SELECT
        o.tenant_id,
        o.order_id,
        o.ordered_at,
        o.amount
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id
      AND o.status = 'PAID'
      AND o.ordered_at >= p_from
      AND o.ordered_at < p_to;
$$;
```

Ngay cả khi không inline, bản thân truy vấn trong function đã có filter status.

### 19.2. Không tạo một function cho mọi tổ hợp filter

Một giao diện có 15 điều kiện tùy chọn có thể bùng nổ số biến thể function. Cần cân nhắc:

- SQL query có bind parameters.
- Function nhận những tham số ổn định quan trọng.
- View + WHERE ở caller.
- Dynamic SQL trong tầng ứng dụng hoặc PL/pgSQL nếu cần.
- Một số read models chuyên cho hot paths.

### 19.3. Hợp đồng kết quả vẫn quan trọng hơn độ ngắn

Một function trả một tập rộng rồi caller lọc có thể là API linh hoạt, nhưng trên bảng rất lớn phải đo. Một function trả tập hẹp có thể nhanh hơn cho use case cố định, nhưng làm hợp đồng ít tái sử dụng hơn.

---

## 20. Hàm bọc cột và index: hiểu sargability

Ví dụ ứng dụng lưu nhãn dạng TEXT, muốn so sánh bỏ khoảng trắng và chuyển chữ thường.

### 20.1. Hàm chuẩn hóa thuần túy

```sql
CREATE FUNCTION sqlfn_lab.normalize_label(
    p_text TEXT
)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT LOWER(BTRIM(p_text));
$$;
```

Trong điều kiện collation và môi trường xác định, `LOWER/BTRIM` có thể dùng để chuẩn hóa label. Trong thực tế, nếu collation/locale hoặc chính sách Unicode thay đổi, cần quản lý index/normalization tương ứng; không coi việc nâng cấp môi trường luôn không ảnh hưởng giá trị được tính.

### 20.2. Biểu thức lọc trên cột

```sql
WHERE sqlfn_lab.normalize_label(label) = 'postgresql'
```

Nếu bảng có index B-tree **chỉ trên label gốc**, index đó không mặc nhiên giúp so sánh trên biểu thức `LOWER(BTRIM(label))`.

### 20.3. Expression index phù hợp

Ví dụ bảng lab mở rộng:

```sql
CREATE TABLE sqlfn_lab.catalog_items (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL
);

INSERT INTO sqlfn_lab.catalog_items (label)
VALUES (' PostgreSQL '), ('postgresql'), ('JAVA'), (' SQL ');

CREATE INDEX idx_catalog_normalized_label
ON sqlfn_lab.catalog_items (
    sqlfn_lab.normalize_label(label)
);
```

Truy vấn:

```sql
SELECT item_id, label
FROM sqlfn_lab.catalog_items
WHERE sqlfn_lab.normalize_label(label) = 'postgresql';
```

có expression index phù hợp để planner cân nhắc.

### 20.4. Inlining có thể giúp matching biểu thức

Nếu planner inline `normalize_label(label)` thành `LOWER(BTRIM(label))`, các biểu thức có thể được tối ưu theo hình dạng tương ứng. Nhưng không nên dựa vào inlining vô điều kiện khi thiết kế một index thiết yếu.

Nếu index và câu WHERE đều dùng **cùng function** với chữ ký rõ ràng, planner thường có một biểu thức index nhất quán để xem xét, dù trường hợp tối ưu phụ thuộc dữ liệu và metadata.

### 20.5. Đánh dấu IMMUTABLE để tạo index cần sự thật

PostgreSQL yêu cầu expression index dựa trên các biểu thức/hàm có độ bất biến thích hợp. Đừng gắn nhãn IMMUTABLE sai cho function đọc bảng hoặc thời gian chỉ để “được CREATE INDEX”.

**Index sai vì metadata giả là nguy cơ correctness**, không chỉ lựa chọn hiệu năng kém.

---

## 21. Hàm trên cột thời gian và nguy cơ mất index range

Một ví dụ hay gặp:

```sql
CREATE FUNCTION sqlfn_lab.utc_day(
    p_time TIMESTAMPTZ
)
RETURNS DATE
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT (p_time AT TIME ZONE 'UTC')::DATE;
$$;
```

Dùng để hiển thị nhóm theo ngày UTC:

```sql
SELECT sqlfn_lab.utc_day(ordered_at) AS day_utc,
       COUNT(*)
FROM sqlfn_lab.orders
GROUP BY day_utc
ORDER BY day_utc;
```

Nhưng nếu muốn lọc ngày:

```sql
WHERE sqlfn_lab.utc_day(ordered_at) = DATE '2026-02-01'
```

có thể không tận dụng B-tree thường trên `ordered_at` để tìm khoảng thời gian như mong muốn, vì điều kiện đang so sánh biểu thức trên cột.

### 21.1. Viết range trực tiếp trên timestamp

```sql
WHERE ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND ordered_at <  TIMESTAMPTZ '2026-02-02 00:00:00+00'
```

Dạng half-open range thường phù hợp B-tree trên raw timestamp hơn và có thể hỗ trợ partition pruning nếu bảng phân vùng theo thời gian.

### 21.2. Chức năng hiển thị khác chức năng tìm kiếm

Hàm `utc_day` có thể rất tiện cho SELECT/GROUP BY, nhưng không vì vậy mà dùng nó trong mọi WHERE. **Tách biểu thức trình bày với điều kiện tìm kiếm** khi access path cần B-tree range.

### 21.3. Expression index là lựa chọn khác, không phải mặc định tốt nhất

Nếu workload thường xuyên truy vấn trực tiếp ngày đã chuẩn hóa, expression index trên `utc_day(ordered_at)` có thể phù hợp. Cần đánh đổi storage/maintenance và xác nhận semantics timezone.

---

## 22. Hàm IMMUTABLE và index/generation: cảnh báo nâng cao

Một số cơ chế phụ thuộc vào tính bất biến của expression:

- Expression indexes.
- Một số điều kiện index/constraint.
- Stored generated columns trong những trường hợp phù hợp.
- Constant folding/caching assumptions.

### 22.1. Khai báo sai làm kết quả khó lường

Ví dụ một function đọc tỷ giá đang lưu ở bảng nền:

```sql
-- Phản ví dụ: không thực thi.
--
-- CREATE FUNCTION convert_currency(p_amount numeric)
-- RETURNS numeric
-- LANGUAGE SQL IMMUTABLE
-- AS $$
--   SELECT p_amount * (
--       SELECT current_rate FROM rates LIMIT 1
--   );
-- $$;
```

Tỷ giá có thể đổi sau mỗi giao dịch, nên khai báo IMMUTABLE là sai. PostgreSQL có thể dùng giả định cũ trong plan hoặc dữ liệu index, gây sai số liệu.

### 22.2. Tính bất biến phải bao gồm mọi phụ thuộc

Không chỉ nhìn SQL body có tên hàm `round` hay `lower`. Nếu kết quả phụ thuộc cấu hình timezone, collation, bảng tra cứu, environment hoặc hàm con có volatility cao hơn, cần xem xét toàn bộ chuỗi phụ thuộc.

### 22.3. Đừng “tối ưu” bằng cách nói dối planner

Một benchmark với function bị gắn IMMUTABLE sai có thể có vẻ nhanh hơn, nhưng không còn đảm bảo kết quả đúng khi dữ liệu/config đổi.

Mục tiêu là tối ưu **trong những biến đổi bảo toàn semantics**, không lừa planner.

---

## 23. PARALLEL SAFE, RESTRICTED và UNSAFE

PostgreSQL có metadata về an toàn khi function được gọi trong một parallel query.

| Thuộc tính | Ý nghĩa thực hành |
| --- | --- |
| `PARALLEL SAFE` | Tác giả cam kết function có thể chạy trong parallel workers theo giới hạn PostgreSQL |
| `PARALLEL RESTRICTED` | Function chỉ chạy ở leader trong những kế hoạch thích hợp |
| `PARALLEL UNSAFE` | Function không an toàn cho parallel mode; có thể ngăn parallel plan |

**Mặc định** của user-defined functions thường là `PARALLEL UNSAFE` nếu không được khai báo phù hợp.

### 23.1. Ví dụ thuần toán học

```sql
CREATE FUNCTION sqlfn_lab.double_amount(
    p_amount NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_amount * 2;
$$;
```

Phép nhân số không đọc/ghi trạng thái session hoặc database, nên PARALLEL SAFE là một lời hứa hợp lý.

### 23.2. Không gắn PARALLEL SAFE bừa bãi

Nếu function sửa dữ liệu, dùng thông tin trạng thái không thích hợp trong worker, quản lý transaction, sequence, temporary table hoặc gọi hàm không parallel-safe, khai báo SAFE có thể sai.

Tác giả cần hiểu **toàn bộ operations** và restrictions trong phiên bản PostgreSQL, không chỉ body nhìn “có một SELECT”.

### 23.3. Parallel metadata không bảo đảm query chạy song song

Ngay cả khi function PARALLEL SAFE, planner vẫn có thể chọn kế hoạch serial vì:

- Bảng nhỏ.
- Chi phí khởi tạo worker lớn.
- Bộ lọc quá chọn lọc.
- Query có node/aggregate khác không phù hợp parallel.
- Cấu hình và tải hệ thống.

### 23.4. Cân nhắc concurrency

Một query chạy nhanh với bốn workers không có nghĩa 30 query đồng thời mỗi query bốn workers đều tối ưu. Đo CPU, I/O và throughput tổng khi triển khai.

---

## 24. COST và ROWS: tác động tới cost model

PostgreSQL cho phép khai báo:

```sql
COST 100
ROWS 1000
```

trong function definition theo loại hàm.

### 24.1. COST là ước lượng chi phí của lời gọi

COST là **đơn vị ước lượng tương đối của planner**, không phải milliseconds và không phải thời gian CPU chính xác.

Với function trả scalar, COST ảnh hưởng ước tính chi phí lời gọi. Với set-returning function, cách tính cost theo tài liệu PostgreSQL áp dụng cho việc trả tập kết quả; không diễn giải máy móc “mỗi row tốn đúng 100 ms”.

### 24.2. ROWS chỉ áp dụng cho set-returning function

Một function:

```sql
RETURNS TABLE (...)
ROWS 100
```

dùng ROWS để nói số hàng dự kiến. Đó không phải một kiểm tra/cắt output.

### 24.3. Vì sao ước lượng sai có thể hại plan?

Nếu function thực trả 100.000 hàng nhưng được ước lượng 10, planner có thể chọn một Nested Loop hoặc join order kém phù hợp, đặc biệt nếu function không inline để planner nhìn được bảng nền.

### 24.4. Chỉ sửa ROWS sau khi có dữ liệu đo

Dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM sqlfn_lab.orders_in_period(...);
```

so `rows` ước lượng và `actual rows`. Nếu ước lượng lệch lớn trong workload lặp lại, cân nhắc cập nhật metadata hoặc viết lại query, nhưng đừng tùy tiện đặt ROWS theo một ví dụ một tenant.

### 24.5. Inlining có thể làm COST/ROWS ít trực tiếp hơn

Khi function được inline, planner có thể tối ưu dựa trên bảng nền và thống kê thay vì chỉ dựa trên các hint black-box. Vì vậy việc thay COST/ROWS có thể không tạo tác động như kỳ vọng ở mọi query.

---

## 25. Hàm SQL với nhiều statements: có thể, nhưng cần biết giới hạn

SQL-language functions không bị giới hạn tuyệt đối ở một SELECT trong mọi hình thức. Trong dạng body chuỗi, PostgreSQL hỗ trợ nhiều SQL statements hợp lệ và kết quả thường dựa trên statement cuối theo hợp đồng kiểu trả về.

Ví dụ mang tính minh họa:

```sql
CREATE FUNCTION sqlfn_lab.two_step_value(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT p_value;
    SELECT p_value + 2;
$$;
```

Kết quả scalar trả từ statement cuối, với điều kiện các câu và kiểu kết quả phù hợp.

### 25.1. Tại sao không khuyến khích khi chỉ tính một số?

Hàm trên có thể viết đơn giản:

```sql
SELECT p_value + 2;
```

Multiple statements không cần thiết có thể làm người đọc khó hiểu và giảm cơ hội inline.

### 25.2. SQL function không cung cấp biến và flow control như PL/pgSQL

Nếu cần lưu giá trị tạm, `IF/ELSE`, vòng lặp hoặc exception block, hãy xem PL/pgSQL. Một loạt `SELECT` trong SQL function không tương đương với flow control của procedural language.

### 25.3. DML trong function

SQL-language function có thể thực hiện một số DML theo kiểu chức năng/hạn chế phù hợp, nhưng cần `VOLATILE` và quyền thích hợp khi có side effects. Không được gọi một hàm làm thay đổi trạng thái là IMMUTABLE/STABLE để kiếm lợi tối ưu.

### 25.4. Function không tự có COMMIT/ROLLBACK độc lập

Function chạy trong ngữ cảnh transaction của caller. Nếu cần transaction control trong thủ tục được gọi ở những hoàn cảnh cho phép, cần nghiên cứu `CREATE PROCEDURE`/`CALL` và các giới hạn PostgreSQL, không cố đưa `COMMIT` vào SQL function thông thường.

---

## 26. SQL-standard function body: RETURN và BEGIN ATOMIC

Ngoài dạng:

```sql
LANGUAGE SQL
AS $$ SELECT ...; $$
```

các phiên bản PostgreSQL hỗ trợ SQL-standard function body cho phép cú pháp như:

```sql
CREATE FUNCTION sqlfn_lab.triple_integer(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
RETURN p_value * 3;
```

Ví dụ với block:

```sql
CREATE FUNCTION sqlfn_lab.add_five(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
BEGIN ATOMIC
    SELECT p_value + 5;
END;
```

### 26.1. Không nhầm BEGIN ATOMIC với BEGIN transaction

`BEGIN ATOMIC ... END` ở đây là **cú pháp thân hàm SQL-standard** trong phiên bản hỗ trợ, không phải một transaction `BEGIN; COMMIT;` do ứng dụng điều khiển.

### 26.2. Khác biệt về thời điểm phân tích định nghĩa

Với SQL-standard body, PostgreSQL phân tích cú pháp/tham chiếu tại thời điểm định nghĩa theo cơ chế tương ứng, có thể ghi nhận dependency rõ hơn.

Với string-literal body, thời điểm kiểm tra/phân tích và dependency tracking có thể khác, tùy dạng body, cấu hình function body checks và tình huống.

### 26.3. Không sao chép cú pháp mới sang phiên bản cũ

SQL-standard bodies được hỗ trợ trên các phiên bản PostgreSQL hiện đại từ PostgreSQL 14. Nếu dự án đang dùng phiên bản cũ, cần dùng dạng `AS $$...$$` và kiểm tra khả năng tương thích.

### 26.4. Không dùng cách này để né quyền

Kiểu body không tự khiến function an toàn hoặc parallel-safe. Các nguyên tắc volatility, quyền và thiết kế query vẫn giữ nguyên.

---

## 27. Khi gọi scalar function trong WHERE, vì sao có thể chậm?

Ví dụ:

```sql
SELECT order_id
FROM sqlfn_lab.orders
WHERE sqlfn_lab.amount_with_tax(amount, 8) > 100;
```

Nếu condition phụ thuộc `amount` và query phải đọc nhiều hàng, function có thể được đánh giá trên rất nhiều tuples. Nếu không có index phù hợp, SQL có thể cần scan lớn.

### 27.1. Function thuần toán học có thể biến đổi điều kiện không?

Về toán học:

```text
ROUND(amount * 1.08, 2) > 100
```

không hoàn toàn giống một phép đảo bất kỳ nếu có rounding, kiểu số, overflow hoặc chính sách precision. Không tự thay bằng:

```sql
amount > 100 / 1.08
```

mà chưa chứng minh semantics của mọi giá trị.

### 27.2. Khi có thể viết điều kiện trực tiếp, hãy ưu tiên hình dạng sargable

Ví dụ truy vấn muốn `amount >= 100` thì viết đúng:

```sql
WHERE amount >= 100
```

Nếu có B-tree index trên amount và điều kiện chọn lọc, planner có thể khai thác trực tiếp.

### 27.3. Expression index nếu đúng workload

Nếu filter theo `amount_with_tax(amount,8)` rất thường xuyên và biểu thức có tính bất biến phù hợp, có thể nghiên cứu expression index tương ứng. Nhưng mỗi index thêm tăng write/disk overhead và chỉ hữu ích cho pattern được thiết kế.

### 27.4. Đừng biến mọi thao tác nhỏ thành lời gọi đắt

Function đơn giản có thể inline, nhưng một function gọi nhiều subqueries hoặc xử lý nặng trên mỗi row có thể gây chi phí lớn. Nếu dữ liệu trả 1 triệu rows, mọi overhead nhỏ đều có thể nhân lên.

---

## 28. Scalar SQL function vs biểu thức trực tiếp: benchmark

Hai câu query có thể so sánh:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT SUM(
    sqlfn_lab.amount_with_tax(amount, 8)
)
FROM sqlfn_lab.orders
WHERE tenant_id = 10;
```

và:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT SUM(
    ROUND(amount * (1 + 8::NUMERIC / 100), 2)
)
FROM sqlfn_lab.orders
WHERE tenant_id = 10;
```

### 28.1. Cần so cùng semantics

Hai biểu thức phải:

- Cùng kiểu NUMERIC.
- Cùng điều kiện WHERE.
- Cùng cách round.
- Cùng handling NULL.
- Cùng data snapshot theo thực tế thử nghiệm.

Nếu một query dùng `FLOAT` còn query kia dùng `NUMERIC`, không thể xem chênh lệch là chỉ do inlining.

### 28.2. Dữ liệu nhỏ có thể gây nhiễu

60.000 orders là đủ để học `EXPLAIN` nhưng chưa đại diện workload nhiều trăm triệu rows. Query cache nóng/lạnh, CPU, concurrent activity và sự chênh lệch plan có thể ảnh hưởng số đo.

### 28.3. Đọc gì trong VERBOSE?

`EXPLAIN (VERBOSE)` có thể hiển thị biểu thức output. Một số trường hợp scalar inlining có thể được nhận ra qua biểu thức đã mở rộng thay vì giữ tên function, nhưng không có một thông báo chuẩn “inlining=true” được đảm bảo trong mọi plan.

Đọc plan của cả hai câu và xem chi phí, nodes, thời gian; nếu cần, kiểm tra PostgreSQL version và môi trường.

### 28.4. Không kết luận từ một lần chạy

Benchmark cần:

1. Warm-up.
2. Nhiều lần chạy.
3. Số đo ổn định.
4. Dữ liệu có distribution đại diện.
5. Đọc Planning Time, Execution Time và BUFFERS.
6. Xem concurrency nếu endpoint thường bị gọi đồng thời.

---

## 29. Table function vs truy vấn SQL trực tiếp: benchmark

Hàm:

```sql
SELECT *
FROM sqlfn_lab.orders_in_period(
    10,
    TIMESTAMPTZ '2026-02-01 00:00:00+00',
    TIMESTAMPTZ '2026-03-01 00:00:00+00'
)
WHERE status = 'PAID';
```

Truy vấn trực tiếp tương ứng:

```sql
SELECT
    o.tenant_id,
    o.order_id,
    o.ordered_at,
    o.status,
    o.amount
FROM sqlfn_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.ordered_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND o.ordered_at <  TIMESTAMPTZ '2026-03-01 00:00:00+00'
  AND o.status = 'PAID';
```

### 29.1. Có thể thu được plan gần nhau

Nếu function inline và optimizer nhìn thấy cùng điều kiện nền, hai plan có thể tương tự. Nhưng metadata/hình dạng query/parameter vẫn có thể làm khác plan.

### 29.2. Nếu Function Scan trả rất nhiều hàng rồi mới lọc

Đó là dấu hiệu hàm chưa được đưa vào plan chung theo hướng mong muốn. Có thể xem:

- Chuyển filter quan trọng vào function body.
- Đơn giản hóa body.
- Xem thuộc tính volatility, STRICT, SET, security.
- Dùng truy vấn trực tiếp cho hot path.
- Giữ function làm abstraction ở nơi lợi ích lớn hơn overhead.

### 29.3. Không xóa SECURITY DEFINER chỉ để nhanh hơn

Nếu function cần quyền đặc biệt, việc bỏ SECURITY DEFINER để inline có thể gây lỗi quyền hoặc thay đổi access control. Giải pháp tối ưu hóa phải **bảo toàn semantics bảo mật**.

### 29.4. Đọc ROWS estimate

Nếu Function Scan có `rows=100` theo hint nhưng thực tế `actual rows=5000`, planner có thể ước lượng JOIN sai. Dữ liệu đo giúp quyết định cần thay ROWS hay query shape.

---

## 30. Security: SECURITY INVOKER và SECURITY DEFINER

Function có thể được gọi dưới quyền người gọi hoặc quyền owner theo khai báo.

### 30.1. SECURITY INVOKER — mặc định

```sql
CREATE FUNCTION sqlfn_lab.identity_integer(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
SECURITY INVOKER
AS $$
    SELECT p_value;
$$;
```

Với SECURITY INVOKER, quyền truy cập đến đối tượng nền khi function chạy được xét trong ngữ cảnh người gọi theo quy tắc PostgreSQL.

### 30.2. SECURITY DEFINER

```sql
CREATE FUNCTION sqlfn_lab.tenant_order_count_definer(
    p_tenant_id INTEGER
)
RETURNS BIGINT
LANGUAGE SQL
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, sqlfn_lab, pg_temp
AS $body$
    SELECT COUNT(*)
    FROM sqlfn_lab.orders AS o
    WHERE o.tenant_id = p_tenant_id;
$body$;
```

Đây là ví dụ cú pháp; **không nên cấp quyền EXECUTE cho người dùng không tin cậy** chỉ vì function trả COUNT. Nếu không có kiểm tra tenant đáng tin cậy, caller có thể truyền bất kỳ tenant_id và suy ra thông tin của tenant khác.

### 30.3. Vì sao SECURITY DEFINER hạn chế inlining?

Inlining không được làm mất ranh giới quyền owner. Do đó cần hiểu rằng đổi từ invoker sang definer có thể ảnh hưởng cả **security semantics và kế hoạch tối ưu**.

### 30.4. search_path trong definer function

Với function có quyền nâng cao, các đối tượng không schema-qualified và một schema mà người dùng không tin cậy có thể tạo objects có tên trùng gây nguy cơ resolution/hijacking.

Một nguyên tắc:

- Dùng schema-qualified names với các bảng/hàm quan trọng.
- Đặt `search_path` chỉ gồm schema đáng tin, với `pg_temp` ở vị trí phù hợp theo tài liệu security.
- Không để schema cho user không tin cậy có quyền CREATE nằm trước schema được tin cậy.
- Không cho caller tùy ý sửa đường tìm kiếm làm đổi đối tượng function thực thi.
- Xem xét cách PostgreSQL xử lý function/operator name resolution khi có overloads.

### 30.5. Đánh đổi bảo mật–hiệu năng

Một hàm cần SECURITY DEFINER vì quyền là **yêu cầu chính**. Nếu nó chậm do không inline, có thể tối ưu query bên trong, index hoặc giảm số lần gọi; không được phá ranh giới quyền để đổi lấy tốc độ.

---

## 31. EXECUTE privilege và mặc định PUBLIC

Trong PostgreSQL, function có ACL và quyền `EXECUTE`.

### 31.1. Thử cấu hình quyền ở môi trường lab

Ví dụ minh họa khi có quyền tạo role:

```sql
CREATE ROLE sqlfn_lab_reader NOLOGIN;

GRANT USAGE ON SCHEMA sqlfn_lab
TO sqlfn_lab_reader;

GRANT EXECUTE ON FUNCTION sqlfn_lab.amount_with_tax(
    NUMERIC, NUMERIC
)
TO sqlfn_lab_reader;
```

### 31.2. Function mới có thể được EXECUTE bởi PUBLIC mặc định

Trong nhiều cấu hình PostgreSQL, quyền EXECUTE trên function mới được cấp cho `PUBLIC` theo default privileges. Điều này quan trọng với SECURITY DEFINER.

Nếu muốn chỉ cho một role cụ thể gọi một function nhạy cảm, cần:

```sql
REVOKE ALL ON FUNCTION
    sqlfn_lab.tenant_order_count_definer(INTEGER)
FROM PUBLIC;
```

rồi GRANT cho các role cần thiết. Với triển khai nhạy cảm, nên thực hiện CREATE/REVOKE/GRANT trong một transaction phù hợp để tránh cửa sổ quyền ngoài ý muốn.

### 31.3. Schema USAGE và object permissions

Role cần có những quyền phù hợp để resolve và gọi function, bao gồm quyền sử dụng schema và quyền EXECUTE. Việc có EXECUTE function không có nghĩa tự có quyền SELECT mọi bảng nền khi function INVOKER.

### 31.4. RLS và tenant identity

Nếu function nhận `p_tenant_id` từ caller mà caller có thể truyền ID khác, function không tự là boundary bảo mật. Đặc biệt với SECURITY DEFINER, phải kiểm tra identity trusted và policies để không vô tình xuất dữ liệu của tenant khác.

### 31.5. Test bằng role thật

Một function chạy thành công dưới superuser không chứng minh user role production sẽ đọc/ghi đúng quyền hoặc chịu RLS như dự kiến. Cần kiểm thử nhiều role, nhiều tenant và đường gọi thực.

---

## 32. SQL function, RLS và đặc quyền trên bảng

Một function đọc bảng `orders` có thể được áp dụng Row-Level Security theo quyền và owner semantics.

### 32.1. SECURITY INVOKER

Với SECURITY INVOKER, quyền nền và RLS thường được xét theo caller, phù hợp nếu bạn muốn mỗi role chỉ đọc phạm vi mà role đó được phép.

### 32.2. SECURITY DEFINER

Với SECURITY DEFINER, role owner có thể có quyền đặc biệt và có thể ảnh hưởng chính sách RLS, nhất là nếu owner bảng có bypass hoặc `BYPASSRLS`. Đây là lý do phải kiểm tra thật.

### 32.3. Trusted tenant context

Một mẫu như:

```sql
WHERE tenant_id = current_setting('app.tenant_id')::INTEGER
```

chỉ an toàn nếu tenant context được thiết lập qua kênh đáng tin cậy, caller không tự giả mạo và connection pool không làm rò dữ liệu giữa requests.

Không dùng một session setting tự do làm chứng cứ quyền truy cập nếu client SQL không tin cậy có thể tự `SET` nó.

### 32.4. Chỉ cấp EXECUTE không tương đương cấp quyền dữ liệu phù hợp

Một function SECURITY DEFINER có thể mở ra một đường truy cập mới tới dữ liệu nền. Phải xem các hàm như một phần của **permission surface**, không chỉ utility code.

---

## 33. LEAKPROOF và security_barrier: không tự bật

PostgreSQL có khái niệm `LEAKPROOF` trong metadata một số hàm/toán tử, liên quan việc optimizer có thể an toàn dịch chuyển biểu thức qua ranh giới security/RLS.

**Không đánh dấu một function do người dùng viết là LEAKPROOF** để ép predicate pushdown nếu chưa đáp ứng điều kiện bảo mật nghiêm ngặt. Việc đánh dấu LEAKPROOF chỉ cho superuser thực hiện theo cơ chế PostgreSQL và yêu cầu hiểu chính xác hàm không tiết lộ thông tin qua thông báo lỗi hay side effects.

### 33.1. Vì sao liên quan tối ưu?

Với security-barrier view hoặc RLS, PostgreSQL có thể giới hạn một số predicate pushdown để tránh rò rỉ dữ liệu. Một function không leakproof có thể không được đẩy qua hàng rào dù có vẻ giúp hiệu năng.

### 33.2. Không hy sinh bảo mật để sửa plan

Nếu query trên dữ liệu nhạy cảm chậm, ưu tiên:

- Index trên cột dùng để lọc an toàn.
- Thiết kế policy/filter rõ.
- Summary phù hợp quyền.
- Giảm dữ liệu phải xử lý.
- Benchmark từ role thật.

Đừng thay đổi nhãn LEAKPROOF/SECURITY chỉ để “optimizer nhìn thấy hết”.

---

## 34. Function overloading và tên schema

PostgreSQL phân biệt function theo tên và kiểu đối số đầu vào, cho phép overload.

### 34.1. Ví dụ overload

```sql
CREATE FUNCTION sqlfn_lab.double_value(
    p_value INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT p_value * 2;
$$;

CREATE FUNCTION sqlfn_lab.double_value(
    p_value NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT p_value * 2;
$$;
```

Gọi rõ kiểu:

```sql
SELECT
    sqlfn_lab.double_value(5::INTEGER),
    sqlfn_lab.double_value(5.5::NUMERIC);
```

### 34.2. Vì sao implicit casts có thể gây nhầm?

Nếu lời gọi có literal chưa rõ kiểu hoặc default arguments, PostgreSQL áp dụng quy tắc resolve candidates. Có thể báo ambiguous function hoặc chọn kiểu khác dự đoán.

Với API lâu dài, cân nhắc ít overload và dùng casts rõ khi nhiều kiểu có thể phù hợp.

### 34.3. Schema qualification

```sql
SELECT sqlfn_lab.double_value(5);
```

giúp xác định schema đích. Đặc biệt trong security-sensitive code, không dựa vào search_path tùy biến của caller để resolve các hàm có cùng tên.

### 34.4. Named arguments là một phần contract

Nếu client gọi `p_value => ...`, đổi tên tham số có thể là breaking change ngay cả khi kiểu tham số không đổi. Đặt tên tham số ổn định và có chiến lược versioning nếu được công bố công khai.

---

## 35. CREATE OR REPLACE FUNCTION và thay đổi chữ ký

Một function đang được consumer dùng là một API của database.

### 35.1. Thay body khi chữ ký tương thích

```sql
CREATE OR REPLACE FUNCTION sqlfn_lab.add_integers(
    p_a INTEGER,
    p_b INTEGER
)
RETURNS INTEGER
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_a + p_b;
$$;
```

Lệnh này cập nhật định nghĩa nếu chữ ký/kiểu trả về tương thích theo quy tắc PostgreSQL.

### 35.2. Không tùy tiện đổi RETURNS

PostgreSQL không cho `CREATE OR REPLACE FUNCTION` đổi kiểu trả về của function hiện có theo cách tùy ý. Thường cần versioning hoặc DROP/CREATE với quản lý dependencies.

### 35.3. Thêm tham số có thể tạo overload mới

Nếu từ:

```sql
f(p_tenant_id INTEGER)
```

đổi thành:

```sql
f(p_tenant_id INTEGER, p_from TIMESTAMPTZ)
```

đây có thể là **một function identity khác** trong PostgreSQL, không đơn giản thay body của function cũ. Hậu quả:

- Hai overload cùng tồn tại.
- Quyền EXECUTE khác nhau.
- Consumer cũ tiếp tục gọi bản cũ.
- Calls dùng DEFAULT/implicit casts có thể mơ hồ.

### 35.4. DROP FUNCTION cần xác định đúng chữ ký

```sql
DROP FUNCTION sqlfn_lab.double_value(INTEGER);
```

có thể bỏ overload INTEGER mà không bỏ overload NUMERIC. Nhưng trước khi DROP trên production phải kiểm tra dependencies và quyền.

### 35.5. Không dùng CASCADE theo thói quen

`DROP FUNCTION ... CASCADE` có thể xóa các view/function/objects phụ thuộc. Cần migration plan, kiểm tra consumer và đường rollback.

---

## 36. SQL function và dependency management

Một function có thể tham chiếu bảng, kiểu, toán tử hoặc function khác.

### 36.1. Xem function definition

```sql
SELECT pg_get_functiondef(
    'sqlfn_lab.orders_in_period(
       INTEGER, TIMESTAMPTZ, TIMESTAMPTZ
     )'::REGPROCEDURE
);
```

Với các schema và chữ ký có overload, `REGPROCEDURE` giúp chỉ rõ function identity.

### 36.2. Xem catalog function

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    p.provolatile,
    p.proparallel,
    p.prosecdef
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'sqlfn_lab'
ORDER BY p.proname, identity_arguments;
```

Một số mã metadata:

- `provolatile`: `i` immutable, `s` stable, `v` volatile.
- `proparallel`: `s` safe, `r` restricted, `u` unsafe.
- `prosecdef`: thuộc tính SECURITY DEFINER.

### 36.3. \df trong psql

Trong `psql`:

```text
\df sqlfn_lab.*
\df+ sqlfn_lab.orders_in_period
```

Đây là meta-command của psql, không phải SQL cho JDBC.

### 36.4. Dependency khác nhau giữa các body forms

SQL-standard body có thể được phân tích và ghi nhận dependency ngay khi CREATE hơn so với string body, theo quy tắc PostgreSQL. Không giả định mọi string-body function đều ngăn DROP table được tham chiếu theo cùng cách một view làm.

Với migration, cần test dependency thực tế và không xem chỉ `pg_depend` là danh sách toàn bộ consumers ở application layer.

---

## 37. Truy vấn có tham số và prepared plan

Một SQL function thường được gọi từ câu SQL có bind parameters:

```sql
SELECT *
FROM sqlfn_lab.orders_in_period(
    $1::INTEGER,
    $2::TIMESTAMPTZ,
    $3::TIMESTAMPTZ
);
```

PostgreSQL có thể cân nhắc **custom plan** và **generic plan** theo cơ chế prepared statements.

### 37.1. Điều kiện tham số ảnh hưởng selectivity

Tenant A có 100 đơn, tenant B có 10 triệu đơn thì cùng một query có thể cần access paths khác nhau. Một generic plan tối ưu trung bình có thể không tốt cho cả hai.

### 37.2. Không gán mọi lỗi plan cho function

Cần phân biệt:

- Function không inline.
- Index không phù hợp.
- Stats thiếu/cũ.
- Prepared statement generic plan.
- Điều kiện thời gian không chọn lọc.
- Partition pruning theo parameter.

Những yếu tố này có thể kết hợp.

### 37.3. Xem EXPLAIN với giá trị thực

Khi đo production-like workload, dùng các nhóm tham số đại diện: tenant nhỏ, tenant lớn, ngày hẹp, ngày dài. Tránh chỉ đo một giá trị rồi kết luận toàn bộ API tốt.

---

## 38. Java/JDBC gọi SQL function

Vì function là đối tượng PostgreSQL, Java có thể gọi qua `PreparedStatement` bình thường.

### 38.1. Gọi scalar function

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

BigDecimal amount = new BigDecimal("100.00");
BigDecimal rate = new BigDecimal("8.0");

String sql = """
    SELECT sqlfn_lab.amount_with_tax(?, ?) AS total
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, amount);
    ps.setBigDecimal(2, rate);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal total = rs.getBigDecimal("total");
            // Xử lý kết quả.
        }
    }
}
```

### 38.2. Gọi table function

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Timestamp;
import java.time.Instant;

String sql = """
    SELECT order_id, ordered_at, status, amount
    FROM sqlfn_lab.orders_in_period(?, ?, ?)
    WHERE status = 'PAID'
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 100
    """;

Instant from = Instant.parse("2026-02-01T00:00:00Z");
Instant to = Instant.parse("2026-03-01T00:00:00Z");

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, 10);
    ps.setTimestamp(2, Timestamp.from(from));
    ps.setTimestamp(3, Timestamp.from(to));

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            // Đọc các cột còn lại.
        }
    }
}
```

### 38.3. Truyền tenant_id an toàn

`tenant_id=10` ở ví dụ phải được xác định qua authentication/authorization của ứng dụng, không tin input tự do. PreparedStatement chống SQL injection theo cách bind giá trị, **không tự xác thực quyền đọc tenant khác**.

### 38.4. Tránh ghép chuỗi SQL từ input

Không viết:

```java
// Không dùng.
String sql = "SELECT * FROM sqlfn_lab.orders_in_period("
        + userTenantId + ", '" + userFrom + "', '" + userTo + "')";
```

Bind parameters giữ đúng kiểu và giảm nguy cơ injection.

### 38.5. Kiểm tra kiểu timestamp

Hàm nhận `TIMESTAMPTZ`; khi Java chuyển thời gian, nên thống nhất mốc tuyệt đối UTC hoặc timezone contract. Không lấy chuỗi ngày địa phương rồi mặc định nó có cùng ý nghĩa với UTC.

---

## 39. Các tình huống tối ưu điển hình

### Tình huống A — Hàm tính giá trị đơn trên 10 triệu rows

**Bối cảnh:** `amount_with_tax(amount,8)` được gọi trong SUM của bảng rất lớn.

Điều tra:

1. Hàm có thật sự thuần toán học và đúng volatility không?
2. Function có một SELECT expression đơn giản không?
3. Có attributes ngăn inline không?
4. EXPLAIN có cho thấy expression đã mở rộng không?
5. Query vẫn cần scan bao nhiêu rows?
6. Có thể lọc sớm hoặc aggregate ở grain phù hợp không?
7. So với biểu thức trực tiếp trên cùng snapshot.

Không tăng COST hoặc đổi function sang PL/pgSQL mà không có bằng chứng.

### Tình huống B — Table function quét toàn bộ dữ liệu rồi mới lọc

**Bối cảnh:** Consumer gọi function trả đơn trong một năm, sau đó WHERE tenant/status/time bổ sung.

Điều tra:

1. Xem Function Scan và Rows Removed by Filter.
2. Kiểm tra khả năng table function inlining.
3. Nếu không inline, đẩy điều kiện chọn lọc vào body có tham số.
4. Tạo index trên bảng nền dựa theo filter thực tế.
5. Đo lại buffers và actual rows.
6. Bảo toàn mọi điều kiện quyền/tenant.

### Tình huống C — Người viết đánh dấu IMMUTABLE cho hàm đọc bảng

**Bối cảnh:** Function trả tỷ giá hiện hành, kết quả cũ xuất hiện sau khi bảng rate thay đổi.

Đây là **lỗi volatility contract**, không phải lỗi cache “ngẫu nhiên”. Phải sửa metadata và xem các đối tượng dùng function (index/generated values/plans) có cần được xử lý lại hay không.

### Tình huống D — SECURITY DEFINER function chậm

**Bối cảnh:** Hàm bảo mật không inline và caller chạy lặp cho nhiều rows.

Không bỏ SECURITY DEFINER một cách tùy tiện. Có thể:

- Giảm số lần gọi bằng tập hợp hóa.
- Thêm index thích hợp trong query nền.
- Tính kết quả một lần trong một truy vấn an toàn nếu hợp đồng cho phép.
- Tạo các API read models khác nhau theo quyền.
- Tối ưu body, COST/ROWS và quan sát EXPLAIN.

### Tình huống E — Hàm LATERAL mỗi customer làm nghẽn truy vấn

**Bối cảnh:** 1 triệu customers, mỗi customer gọi một function SELECT top-3 orders.

So sánh với một query window function/dedup tổng thể và index `(tenant_id,customer_id,ordered_at DESC)`. Kế hoạch tối ưu phụ thuộc số khách chọn và phân bố đơn; không có cách đúng cho mọi trường hợp.

---

## 40. Những lỗi và hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| “LANGUAGE SQL luôn inline.” | Inlining chỉ xảy ra khi đủ điều kiện và planner chọn |
| “Hàm SQL chỉ là text replacement.” | Function có metadata, quyền, kiểu trả về, runtime semantics |
| “Viết PL/pgSQL hay SQL giống nhau về optimization.” | SQL function có cơ hội inlining riêng |
| “Function luôn nhanh hơn expression trực tiếp.” | Cần benchmark, có thể có call overhead |
| “IMMUTABLE chỉ là hint tăng tốc.” | Lời hứa quan trọng cho correctness/plans/indexes |
| “Đọc bảng nhưng đánh dấu IMMUTABLE không sao.” | Kết quả có thể sai sau khi dữ liệu đổi |
| “STABLE nghĩa là dữ liệu không đổi trong cả ngày.” | Liên quan semantics trong statement/snapshot, không phải TTL |
| “VOLATILE chỉ cần cho random.” | Cả side effects/thay đổi DB và hành vi không ổn định |
| “STRICT chỉ ảnh hưởng hiệu năng.” | Đổi kết quả trên NULL; body có thể không được gọi |
| “NULL truyền vào dùng DEFAULT.” | DEFAULT chỉ khi đối số bị bỏ; NULL là giá trị đã truyền |
| “COST là thời gian tính bằng ms.” | Đơn vị cost model tương đối |
| “ROWS 100 giới hạn function tối đa 100 hàng.” | Chỉ là ước lượng cho planner |
| “PARALLEL SAFE buộc query chạy parallel.” | Planner còn nhiều tiêu chí |
| “Function mặc định PARALLEL SAFE.” | User function thường mặc định UNSAFE |
| “Có RETURN TABLE là tự index kết quả.” | Table function không tự vật hóa kết quả hay index |
| “Function Scan nghĩa PostgreSQL bị lỗi.” | Một access path hợp lệ, đôi khi cần |
| “Không thấy Function Scan chắc chắn hàm inline.” | Phải đọc plan/biểu thức và trường hợp tương ứng |
| “Predicate ngoài table function luôn được push xuống.” | Phụ thuộc inlining/query shape |
| “SECURITY DEFINER chỉ là GRANT nhanh hơn.” | Đổi quyền thực thi, rất quan trọng cho bảo mật |
| “Bỏ SET search_path giúp nhanh nên luôn nên bỏ.” | Có thể mở nguy cơ name resolution/hijacking |
| “Invoker có thể đọc bảng không có quyền SELECT.” | Caller cần quyền nền phù hợp |
| “Chỉ có EXECUTE là đủ quyền tenant.” | Identity/authorization/RLS vẫn cần |
| “Đặt tên hàm calculate_revenue nghĩa báo cáo đúng.” | Phải định nghĩa metric/source/timezone |
| “Function có ORDER BY luôn bảo đảm output caller.” | Caller nên ORDER BY khi cần thứ tự |
| “RETURNS SETOF tự có LIMIT.” | Không; SETOF chỉ nói có nhiều hàng |
| “SQL function có thể COMMIT tùy ý.” | Function không điều khiển transaction như procedure |
| “BEGIN ATOMIC nghĩa bắt đầu transaction.” | Là cú pháp SQL-standard function body |
| “CREATE OR REPLACE đổi RETURNS tùy ý.” | Kiểu trả về bị giới hạn |
| “Thêm parameter luôn thay function cũ.” | Có thể tạo overload mới |
| “Tên tham số không ảnh hưởng client.” | Named-argument callers có thể vỡ |
| “Đổi SQL body là đủ để sửa expression index sai volatility.” | Có thể cần xem index/rebuild và kế hoạch |
| “Function trên cột thời gian luôn dùng index raw timestamp.” | Dạng biểu thức có thể cản range index |
| “Expression index nào cũng rẻ.” | Có write/storage/maintenance cost |
| “Hàm đọc 10 rows ở lab nhanh thì production chắc nhanh.” | Dataset, cache, concurrency khác |
| “Có index thì planner phải dùng.” | Seq Scan có thể tốt hơn |
| “Sửa COST/ROWS là thay optimizer statistics.” | Hint chỉ là một phần cost model |
| “VIEW và table function luôn giống nhau.” | Function có params và metadata/rules riêng |
| “CTE luôn là cách thay SQL function tốt hơn.” | CTE chỉ tồn tại trong statement; tradeoff khác |
| “Dynamic SQL thuộc LANGUAGE SQL function như PL/pgSQL.” | Cần ngôn ngữ/cơ chế phù hợp cho dynamic execution |
| “Chạy bằng superuser thành công nghĩa quyền đúng.” | Phải test từ role thật |
| “Function được inline là tự sửa lỗi JOIN fan-out.” | Logic sai vẫn sai |
| “SET search_path trong SECURITY DEFINER không ảnh hưởng tối ưu.” | Có thể làm mất cơ hội inline nhưng là yêu cầu bảo mật |
| “Mọi function có thể được gọi ở mọi vị trí SQL.” | Scalar và set-returning functions có hình dạng/giới hạn khác |

---

## 41. Bài tập thực hành

### Bài 1 — Hàm scalar đơn giản

Tạo function `add_integers(integer,integer) RETURNS integer` bằng `LANGUAGE SQL`. Gọi với hai số dương và một giá trị âm.

### Bài 2 — Tham số có tên

Viết lại body bằng `p_a` và `p_b`, sau đó viết lại bằng `$1`, `$2`. Vì sao tên tham số có thể dễ bảo trì hơn?

### Bài 3 — IMMUTABLE và phép toán

Tạo hàm tính `p_amount * p_multiplier`. Giải thích khi nào có thể đánh dấu IMMUTABLE và PARALLEL SAFE.

### Bài 4 — NULL/STRICT

Tạo hai hàm: một STRICT và một CALLED ON NULL INPUT có COALESCE. Gọi mỗi hàm với NULL và giải thích kết quả khác nhau.

### Bài 5 — DEFAULT

Tạo function với tham số thuế mặc định 10%. So sánh lời gọi bỏ tham số với lời gọi truyền NULL tường minh.

### Bài 6 — Named arguments

Gọi hàm có tên tham số bằng ký hiệu `p_rate => 8, p_amount => 100`. Vì sao đổi tên tham số có thể phá API?

### Bài 7 — Hàm trả bảng

Tạo `orders_in_period` với RETURNS TABLE, ba tham số tenant/from/to, lọc theo half-open interval.

### Bài 8 — Kiểu trả về

Tạo hàm aggregate theo tenant trả COUNT và SUM. Vì sao COUNT(*) phù hợp BIGINT còn SUM(NUMERIC) phù hợp NUMERIC?

### Bài 9 — RETURNS SETOF

Viết hàm trả các order_id của tenant. So sánh số rows trả về với function scalar BIGINT.

### Bài 10 — ROWS không giới hạn

Đặt `ROWS 5` cho function trả hàng. Gọi với khoảng thời gian thực có hàng trăm orders. Vì sao function không tự cắt xuống 5?

### Bài 11 — Thứ tự đầu ra

Tạo function trả các đơn trong khoảng ngày. Vì sao caller cần `ORDER BY ordered_at DESC, order_id DESC` khi phân trang?

### Bài 12 — LIMIT có ngữ nghĩa

Thiết kế hàm top-3 order IDs cho một customer. Vì sao LIMIT nằm trong function thay đổi tập kết quả, không chỉ tăng tốc?

### Bài 13 — LATERAL

LEFT JOIN LATERAL function lấy ba đơn mới nhất cho từng customer thuộc một tập nhỏ. Tại sao LEFT JOIN giữ khách không có đơn?

### Bài 14 — Correlated function calls

Giải thích vì sao function LATERAL chạy theo hàng ngoài có thể đắt nếu áp dụng cho 1 triệu customers.

### Bài 15 — STABLE đọc bảng

Tạo function `tenant_order_count` đọc orders. Vì sao IMMUTABLE là lời hứa sai khi đơn có thể được thêm/xóa?

### Bài 16 — VOLATILE và thời gian

Viết function wrapper gọi `clock_timestamp()`. Vì sao không đánh dấu STABLE/IMMUTABLE nếu yêu cầu giờ tường thực tế?

### Bài 17 — CURRENT_TIMESTAMP vs clock_timestamp

So sánh hai giá trị thời gian trong transaction có nhiều statements. Giải thích semantics và volatility phù hợp.

### Bài 18 — Mã volatility catalog

Truy vấn `pg_proc` để xem mã `i/s/v` của những function đã tạo. Kiểm tra có hàm nào chưa khai báo volatility và đang dùng mặc định VOLATILE.

### Bài 19 — Scalar inlining

Chạy `EXPLAIN (VERBOSE) SELECT plus_one(10)`. Dự đoán optimizer có thể làm gì và vì sao không được kết luận mọi lời gọi đều inline.

### Bài 20 — Table-function inlining

So sánh EXPLAIN của `orders_in_period(...) WHERE status='PAID'` với query trực tiếp tương đương. Quan sát có Function Scan hay scan bảng nền.

### Bài 21 — Predicate pushdown

Viết hai biến thể function: một chỉ lọc tenant/ngày, một lọc thêm status PAID. Nếu function không inline, cách nào có thể tránh đọc nhiều hàng thừa hơn?

### Bài 22 — SECURITY DEFINER và tối ưu

Tạo một function SECURITY DEFINER trên lab nếu có quyền thích hợp, kiểm tra EXPLAIN và giải thích vì sao ranh giới quyền thường hạn chế inlining.

### Bài 23 — SET search_path

Tạo function có SET search_path. Vì sao SET có thể ngăn inlining và vì sao không nên bỏ cấu hình này tùy tiện ở SECURITY DEFINER?

### Bài 24 — Expression index

Tạo `normalize_label(TEXT)` và expression index trên function; đo EXPLAIN cho WHERE dùng function. Vì sao index thường trên cột gốc không chắc hỗ trợ LOWER/BTRIM?

### Bài 25 — Bộ lọc ngày

Viết function `utc_day(timestamptz)`, so sánh WHERE `utc_day(ordered_at)=date` với half-open range trên ordered_at. Khi nào range dễ dùng B-tree hơn?

### Bài 26 — IMMUTABLE sai và index

Giả sử một function đọc bảng tax_rates nhưng được gắn IMMUTABLE để làm index. Mô tả rủi ro sau khi rate thay đổi và những đối tượng cần điều tra.

### Bài 27 — PARALLEL SAFE

Viết một function thuần toán học PARALLEL SAFE. Vì sao planner vẫn có thể chạy serial trên bảng nhỏ?

### Bài 28 — PARALLEL UNSAFE

Một function cập nhật bảng log mỗi lần gọi có nên được đánh dấu PARALLEL SAFE không? Vì sao khai báo sai nguy hiểm?

### Bài 29 — COST/ROWS

Một function `RETURNS TABLE` thực trả 100.000 rows nhưng khai báo ROWS 10. Ảnh hưởng đến ước lượng JOIN có thể ra sao?

### Bài 30 — Volatility và kết quả rỗng

Hàm `daily_paid_order_value` với GROUP BY trả gì nếu tháng không có đơn PAID? So với hàm scalar `COUNT(*)` không có GROUP BY.

### Bài 31 — SQL-standard body

Viết hai hàm tương đương: dạng `AS $$ SELECT ... $$` và dạng `LANGUAGE SQL RETURN expression`. Nêu yêu cầu phiên bản của dạng SQL-standard.

### Bài 32 — BEGIN ATOMIC

Tạo SQL-standard function dùng `BEGIN ATOMIC SELECT ...; END`. Vì sao đây không phải mở transaction tự chủ?

### Bài 33 — SQL vs PL/pgSQL

Một tác vụ cần vòng lặp, catch exception và dynamic SQL. Vì sao PL/pgSQL thường rõ hơn SQL function chỉ có body SELECT?

### Bài 34 — Function vs procedure

So sánh `SELECT f(...)` với `CALL p(...)`. Trong trường hợp nào procedure hỗ trợ transaction control với các hạn chế phù hợp?

### Bài 35 — JDBC function scalar

Viết PreparedStatement gọi `amount_with_tax(?,?)` với BigDecimal. Vì sao không nối chuỗi số tiền từ input vào SQL?

### Bài 36 — JDBC function table

Viết PreparedStatement gọi `orders_in_period(?,?,?)` với Timestamp từ Instant, ORDER BY và LIMIT. Giải thích cách xác định tenant từ context được xác thực.

### Bài 37 — Function overloading

Tạo hai overload `double_value(integer)` và `double_value(numeric)`. Gọi với casts rõ và một literal kiểu mơ hồ để quan sát resolution.

### Bài 38 — CREATE OR REPLACE

Thay body của một function cùng chữ ký. Thử đổi RETURNS từ INTEGER sang TEXT và giải thích hạn chế. Không phá dữ liệu lab cần giữ.

### Bài 39 — Permission

Trên database lab có quyền tạo role, cấp chỉ EXECUTE trên function và USAGE schema. So sánh cách SECURITY INVOKER và SECURITY DEFINER ảnh hưởng quyền bảng nền.

### Bài 40 — RLS và SECURITY DEFINER

Mô tả trường hợp function nhận p_tenant_id tự do và chạy dưới owner có quyền rộng. Nếu caller truyền tenant khác, có thể xảy ra rò dữ liệu nào? Thiết kế authorization phù hợp.

### Bài 41 — pg_get_functiondef

Lấy định nghĩa function bằng `pg_get_functiondef('schema.fn(args)'::regprocedure)`. Vì sao overload cần chỉ rõ kiểu đầu vào?

### Bài 42 — Tối ưu benchmark

Chạy ba nhóm truy vấn: scalar function vs expression, table function vs trực tiếp, LATERAL function vs window query. Đo Planning Time, Execution Time, BUFFERS, actual rows và số lần chạy.

### Bài 43 — Tối ưu có bảo toàn semantics?

Một developer thay `ROUND(amount * 1.08,2)>100` bằng `amount>100/1.08`. Hãy kiểm tra liệu mọi boundary cases có cùng kết quả hay không trước khi gọi đây là optimization.

### Bài 44 — Thiết kế production

Một hệ thống nhiều tenant có 400 triệu orders, cần function đọc trong 30 ngày, tính metric hàng ngày, quyền truy cập hạn chế, dashboard chạy hàng trăm lần/giờ. Hãy đề xuất SQL functions, indexes, security policy, cách đo inlining, phân biệt view/materialized view, và chiến lược versioning/migration.

---

## 42. Checklist trước khi đưa SQL function lên production

| Câu hỏi | Cách đánh giá |
| --- | --- |
| Function thực sự cần được tái sử dụng? | Nhiều consumer hoặc semantics rõ |
| SQL hay PL/pgSQL? | SELECT/expression so với control flow |
| Function hay procedure? | Hợp đồng SELECT/RETURN và transaction control |
| Tên và schema rõ? | Schema-qualified và naming convention |
| Chữ ký có overload không? | Tránh implicit cast/default ambiguity |
| Kiểu trả về đúng? | Scalar/SETOF/TABLE, BIGINT/NUMERIC |
| Tham số có tên ổn định? | Named arguments là API |
| Có NULL input? | STRICT hay CALLED ON NULL INPUT |
| Mặc định của tham số có đúng? | Omitted khác explicit NULL |
| IMMUTABLE có thật? | Không đọc bảng/time/session mutable |
| STABLE có đúng? | Chỉ đọc, statement-level semantics |
| Có side effects? | VOLATILE và quyền |
| Gọi function con có volatility cao hơn? | Phân loại bảo toàn cả dependency |
| PARALLEL SAFE có chứng minh được? | Không DML/unsafe operations |
| COST/ROWS có hợp lý? | Ước lượng theo dữ liệu thực |
| Body có một expression/SELECT? | Cơ hội inline rõ hơn |
| Có SECURITY DEFINER? | Ranh giới quyền và non-inline tradeoff |
| Có SET search_path? | Bảo mật và tác động inlining |
| Có thể bị SQL injection? | Bind parameters, không nối input |
| Có implicit search_path resolution? | Schema qualify trong code nhạy cảm |
| Caller có quyền EXECUTE? | Grants theo role |
| PUBLIC có quyền không mong muốn? | REVOKE/GRANT chính xác |
| Role gọi có quyền bảng nền? | Invoker vs definer semantics |
| RLS/tenant permission có đúng? | Test role/tenant thật |
| Giao diện trả đúng grain? | Không nhân hàng qua JOIN |
| Table function có trả tập quá lớn? | Số hàng thực, filter/limit |
| WHERE ngoài function có push xuống? | EXPLAIN và node Filter |
| Có Function Scan không? | Nếu có, đánh giá cost/ROWS |
| Scalar function có inline? | EXPLAIN VERBOSE/so query trực tiếp |
| Hàm trên cột có cản index? | Sargability/expression index |
| Time filter có half-open range? | Timestamp trực tiếp, timezone đúng |
| Index nằm ở bảng nền phù hợp? | EXPLAIN BUFFERS |
| Có LATERAL gọi quá nhiều lần? | Loops và số outer rows |
| Có ORDER BY deterministic? | Không dựa thứ tự tình cờ |
| Có materialized view khi cần? | Read frequency và freshness |
| Có phép thử NULL/0 hàng? | COUNT vs SUM và RETURNS TABLE |
| Có thử stale data/config? | IMMUTABLE đúng hay sai |
| Có SQL-standard body support? | Phiên bản PostgreSQL |
| Có dependency migration? | CREATE OR REPLACE/return type |
| Có versioning cho breaking changes? | Consumer rollout |
| Có kiểm thử quyền và concurrency? | Nhiều role/transactions |
| Có benchmark nhiều lượt? | Planning/Execution/Buffers/P95 |
| Có giám sát query cost? | pg_stat_statements khi khả dụng |
| Có tài liệu hợp đồng? | Semantics, NULL, timezone, type |
| Có phương án rollback? | Tránh DROP CASCADE vô ý |

## Kết luận

Viết hàm bằng `LANGUAGE SQL` trong PostgreSQL là một cách hiệu quả để **tái sử dụng phép tính và truy vấn có tham số**, đặc biệt khi hàm là một expression ngắn hoặc một SELECT trả tập hợp. Ưu điểm quan trọng là PostgreSQL **có thể inline một số SQL function**, tạo điều kiện để optimizer nhìn thấy biểu thức, bảng nền, bộ lọc và các đường truy cập.

Những nguyên tắc cần ghi nhớ:

1. **SQL function không phải “macro chắc chắn được inline”.** Inlining phụ thuộc body, kiểu trả về, volatility, bảo mật, cấu hình và phiên bản PostgreSQL.
2. **Chọn hợp đồng return rõ ràng.** `RETURNS type`, `RETURNS SETOF type` và `RETURNS TABLE(...)` phục vụ các kiểu giao diện khác nhau.
3. **Khai báo volatility trung thực.** `IMMUTABLE` cho tính toán độc lập trạng thái; `STABLE` cho đọc dữ liệu ổn định theo statement; `VOLATILE` khi có side effects hoặc giá trị thay đổi trong quá trình thực thi.
4. **STRICT có ngữ nghĩa NULL cụ thể.** Nó không chỉ tối ưu; nó có thể đổi kết quả nếu body cố xử lý NULL.
5. **COST/ROWS là ước lượng, không phải giới hạn hay milliseconds.** Dùng khi cần cải thiện estimate của planner, đặc biệt nếu function không inline.
6. **Tối ưu truy vấn dựa trên plan thật.** So `Function Scan` với scan bảng nền, xem predicate pushdown, indexes, actual rows, loops, buffers và execution time.
7. **Hàm trên cột có thể làm điều kiện khó tận dụng index.** Dùng raw range predicates hoặc expression index thích hợp khi có bằng chứng.
8. **Bảo mật đứng trước inlining.** `SECURITY DEFINER`, `SET search_path`, quyền EXECUTE và RLS có thể thay đổi ranh giới quyền; không được bỏ chúng chỉ để có plan nhanh hơn.
9. **Set-returning function và LATERAL có thể lặp nhiều lần.** Số outer rows và index phía trong quyết định chi phí thực tế.
10. **Quản lý function như API database.** Kiểu/ tên tham số, chữ ký, permissions, dependency và migration đều có thể ảnh hưởng consumer.
11. **Không đánh đổi tính đúng để tối ưu.** Một function đánh dấu IMMUTABLE sai hoặc một câu WHERE biến đổi không bảo toàn rounding có thể cho kết quả nhanh nhưng không đúng.
12. **Giữ thiết kế đơn giản.** Khi một SELECT/CTE/view trực tiếp dễ hiểu và tối ưu hơn, không cần tạo function chỉ vì có thể.

Một SQL function PostgreSQL tốt cần đồng thời đạt ba mục tiêu: **diễn đạt chính xác nghiệp vụ**, **có giao diện và quyền rõ ràng**, và **cho planner đủ cơ hội tối ưu hoặc có chi phí thực thi đã được đo**. Khi nắm được giới hạn của inlining và cách dùng EXPLAIN, bạn có thể tận dụng SQL functions mà không biến logic tái sử dụng thành một điểm nghẽn khó quan sát.
