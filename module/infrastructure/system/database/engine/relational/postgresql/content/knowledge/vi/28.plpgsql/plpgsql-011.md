# Xử lý theo tập thay cho vòng lặp khi phù hợp trong PL/pgSQL

Khi mới học PL/pgSQL, lập trình viên Java hoặc Python thường mang thói quen duyệt từng phần tử vào PostgreSQL: lấy danh sách đơn hàng, viết `FOR ... LOOP`, kiểm tra từng đơn rồi chạy một câu `UPDATE` cho từng hàng. Cách viết ấy có thể tạo ra hàng nghìn, hàng triệu lượt thực thi SQL từ phía PL/pgSQL dù bài toán thực chất chỉ là **một phép biến đổi dữ liệu theo tập**.

Ví dụ yêu cầu: “Giảm 10% số tiền phải thanh toán của tất cả đơn hàng đang ở trạng thái pending trước ngày 01/11/2026”. Cách viết từng hàng:

```sql
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM orders
        WHERE status = 'pending'
          AND ordered_at < DATE '2026-11-01'
    LOOP
        UPDATE orders
        SET amount = amount * 0.90
        WHERE order_id = r.order_id;
    END LOOP;
END;
$$;
```

Trong nhiều trường hợp, có thể thay toàn bộ vòng lặp bằng:

```sql
UPDATE orders
SET amount = amount * 0.90
WHERE status = 'pending'
  AND ordered_at < DATE '2026-11-01';
```

Câu lệnh thứ hai diễn đạt **mục tiêu ở cấp tập hàng**: PostgreSQL tự chọn kế hoạch tìm hàng, áp dụng điều kiện lọc và cập nhật những hàng phù hợp. Ta không cần yêu cầu máy chủ chạy lại một lệnh UPDATE cho từng mã đơn.

Đây là tư duy **set-based processing**: mô tả *tập dữ liệu đầu vào* và *quy tắc biến đổi đầu ra*, để SQL planner/executor thực thi thay vì chủ động điều khiển từng hàng bằng vòng lặp PL/pgSQL. Nó không có nghĩa SQL không duyệt hàng bên trong — executor vẫn xử lý tuples và indexes. Lợi ích là giảm thao tác SQL lặp, tận dụng các tối ưu của PostgreSQL và làm rõ ý định nghiệp vụ.

Bài học phân tích khi nào nên chuyển từ vòng lặp sang SQL, các mẫu thay thế thường gặp, chi phí thực và tính nhất quán giao dịch, rủi ro khi gom quá nhiều thao tác, cùng những tình huống **vòng lặp vẫn là lựa chọn đúng**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt xử lý từng hàng (*row-by-row*, đôi khi gọi RBAR — *Row By Agonizing Row*) với xử lý theo tập.
2. Giải thích vì sao một SQL statement thường tốt hơn hàng nghìn statement giống nhau chạy trong `FOR LOOP`.
3. Viết lại vòng lặp thành `INSERT ... SELECT`, `UPDATE ... FROM`, `DELETE ... USING` và `INSERT ... ON CONFLICT` khi ngữ nghĩa tương đương.
4. Dùng `CASE`, `COALESCE`, `FILTER`, window functions, `DISTINCT ON`, `LATERAL` và CTE để mô tả các biến đổi trước đây thực hiện bằng biến tạm/vòng lặp.
5. Hiểu tương tác giữa SQL set-based, MVCC, locks, trigger, constraint và statement atomicity.
6. Tránh các lỗi khi chuyển đổi: UPDATE ... FROM có nhiều source rows, nhân bản do JOIN, chọn top-N không xác định, suy luận thứ tự cập nhật không có bảo đảm.
7. Đọc `EXPLAIN (ANALYZE, BUFFERS)` và đo tốc độ thực tế mà không so sánh thiếu công bằng.
8. Biết khi nào vẫn cần PL/pgSQL: điều khiển luồng, batch có kiểm soát, gọi logic phụ thuộc thứ tự, retry với transaction phù hợp và những thuật toán có trạng thái.
9. Thiết kế batch lớn để tránh transaction quá dài, WAL bùng nổ và lock contention.
10. Tổ chức code PostgreSQL dễ đọc, đúng nghiệp vụ và có khả năng kiểm thử.

## 2. Vì sao PL/pgSQL có LOOP nhưng không nên lạm dụng?

PL/pgSQL là ngôn ngữ thủ tục cho phép khai báo biến, `IF`, `CASE`, `LOOP`, `FOR`, `WHILE`, exceptions và lời gọi SQL. Nó rất hữu ích khi một quy trình cần điều khiển luồng ngoài một câu SQL.

Tuy nhiên dữ liệu quan hệ thường có dạng tập. Ví dụ “đổi trạng thái tất cả đơn cũ chưa thanh toán” là phép chọn tập hàng qua `WHERE` và cập nhật trường `status`, không cần mỗi hàng đi qua một vòng lặp nghiệp vụ riêng biệt.

### 2.1. Hai tầng thực thi

```text
FOR r IN SELECT ... LOOP
    UPDATE ... WHERE id = r.id;
END LOOP;

Tầng PL/pgSQL:        chọn một row -> chuyển vào biến r
                     -> phát lệnh UPDATE -> tiếp tục vòng lặp

Tầng SQL executor:    lên kế hoạch/thực thi UPDATE,
                     tìm bản ghi, kiểm tra locks/constraints
                     -> trả quyền điều khiển lại PL/pgSQL
                     -> lặp lại cho row kế tiếp.
```

So với:

```text
UPDATE table SET ... WHERE ...;

Tầng SQL:             biểu diễn toàn bộ tập hàng
                     -> planner chọn scan/join
                     -> executor cập nhật theo kế hoạch
                     -> statement hoàn thành.
```

Trong PL/pgSQL có cache plan và nhiều tối ưu giảm chi phí phát lệnh; **không** nên nói mỗi vòng lặp luôn phải parse/plan lại toàn bộ SQL từ đầu. Dù vậy, số lượt chuyển điều khiển và số statement thực thi vẫn có thể rất lớn.

### 2.2. Ba loại vòng lặp khác nhau

1. **Vòng lặp qua hàng để gọi SQL từng hàng:** ví dụ `FOR r IN SELECT ... LOOP UPDATE ... WHERE id=r.id`. Đây là ứng viên hàng đầu để chuyển thành set-based.
2. **Vòng lặp tính toán trên dữ liệu trong bộ nhớ:** ví dụ xử lý mảng/giải thuật trạng thái; có thể hợp lý nếu SQL hóa quá phức tạp.
3. **Vòng lặp qua batch hoặc job đơn vị lớn:** ví dụ xử lý 10.000 IDs mỗi lần, commit/giám sát giữa các batch trong môi trường cho phép. Đây không phải RBAR theo từng row và có thể phù hợp vận hành.

Không phán xét mọi `LOOP` là xấu. Hỏi **mỗi vòng lặp làm bao nhiêu công việc và có thực sự cần thứ tự/điều khiển thủ tục hay không**.

## 3. Bộ dữ liệu thực hành

Tạo một schema riêng để mọi ví dụ có thể chạy trong database lab. Không chạy trên bảng dữ liệu thật.

### 3.1. Các bảng khách hàng và đơn hàng

```sql
CREATE SCHEMA IF NOT EXISTS set_lab;

CREATE TABLE set_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    tier text NOT NULL
        CHECK (tier IN ('gold', 'silver', 'bronze'))
);

CREATE TABLE set_lab.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES set_lab.customers(customer_id),
    ordered_at date NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    discount numeric(12, 2) NOT NULL DEFAULT 0
        CHECK (discount >= 0)
);

CREATE TABLE set_lab.customer_totals (
    customer_id integer PRIMARY KEY
        REFERENCES set_lab.customers(customer_id),
    total_paid numeric(14, 2) NOT NULL DEFAULT 0,
    paid_orders bigint NOT NULL DEFAULT 0,
    calculated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE set_lab.audit_notes (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    note text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
```

### 3.2. Dữ liệu khách hàng

```sql
INSERT INTO set_lab.customers (
    customer_id, full_name, tier
)
VALUES
    (1, 'Lan',  'gold'),
    (2, 'Minh', 'silver'),
    (3, 'Hoa',  'bronze'),
    (4, 'An',   'gold');
```

### 3.3. Dữ liệu đơn hàng

```sql
INSERT INTO set_lab.orders (
    customer_id, ordered_at, status, amount
)
VALUES
    (1, DATE '2026-11-01', 'paid',      100.00),
    (1, DATE '2026-11-02', 'paid',       80.00),
    (1, DATE '2026-11-03', 'pending',    50.00),
    (2, DATE '2026-11-01', 'paid',      200.00),
    (2, DATE '2026-11-02', 'cancelled',  70.00),
    (3, DATE '2026-11-02', 'paid',       40.00),
    (4, DATE '2026-11-01', 'paid',      150.00),
    (4, DATE '2026-11-04', 'pending',   120.00);
```

Chạy các INSERT này **một lần trên bảng trống**. Nếu chạy lại `orders`, identity sinh ID mới và tạo thêm đơn hàng, làm sai những kết quả đếm ở các ví dụ. Với bài tập có UPDATE/DELETE, ưu tiên `BEGIN; ...; ROLLBACK;` để phục hồi dataset.

### 3.4. Kiểm tra tập mẫu

```sql
SELECT
    status,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM set_lab.orders
GROUP BY status
ORDER BY status;
```

Kết quả từ dữ liệu ban đầu:

| status | order_count | total_amount |
| --- | ---: | ---: |
| cancelled | 1 | 70.00 |
| paid | 5 | 570.00 |
| pending | 2 | 170.00 |

Tổng số đơn là **8**, tổng amount là **810.00**. Đây là dữ liệu nhỏ để hiểu cú pháp và ngữ nghĩa, không phải một benchmark đủ lớn để đo lợi ích hiệu năng.

### 3.5. Dữ liệu quan hệ chỉ có thứ tự khi ORDER BY

Mặc dù identity thường được tạo theo thứ tự chèn, không coi `SELECT * FROM set_lab.orders` luôn trả hàng theo `order_id`. Mọi bài tập yêu cầu “đầu tiên/cuối cùng” đều dùng `ORDER BY` rõ ràng với tie-breaker.

## 4. Mẫu 1: nhiều UPDATE nhỏ thành một UPDATE có WHERE

**Yêu cầu:** đặt discount = 5.00 cho mọi đơn pending, không cần đọc từng đơn để ra quyết định.

### 4.1. Cách vòng lặp

```sql
BEGIN;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM set_lab.orders
        WHERE status = 'pending'
    LOOP
        UPDATE set_lab.orders
        SET discount = 5.00
        WHERE order_id = r.order_id;
    END LOOP;
END;
$$;

ROLLBACK;
```

Đoạn trên cho kết quả mong đợi trong lab, nhưng với một triệu đơn pending sẽ có thể phát ra một triệu statement UPDATE nội bộ.

### 4.2. Cách xử lý theo tập

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';

SELECT order_id, status, amount, discount
FROM set_lab.orders
WHERE status = 'pending'
ORDER BY order_id;

ROLLBACK;
```

Một `UPDATE` mô tả tất cả các hàng cần thay đổi. PostgreSQL có thể dùng seq scan, index scan, bitmap path hoặc cách truy cập khác tùy thống kê và kích thước.

### 4.3. Dùng RETURNING để thấy hàng được cập nhật

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending'
RETURNING order_id, customer_id, amount, discount;

ROLLBACK;
```

`RETURNING` cho biết những hàng thực sự được UPDATE mà không cần một vòng lặp SELECT lại theo từng order ID. **Thứ tự hàng RETURNING không được bảo đảm nếu không có truy vấn sắp xếp bên ngoài**.

### 4.4. Không giả định UPDATE tiết kiệm WAL tuyệt đối

Một UPDATE theo tập vẫn phải tạo row versions theo MVCC, duy trì indexes/triggers, ghi WAL và lấy row locks đối với các hàng cần thay đổi. Lợi ích chủ yếu là **tối ưu hóa công việc tổng thể và giảm số lần gọi statement**, không phải bỏ qua cơ chế transactional của PostgreSQL.

## 5. Mẫu 2: IF/ELSE từng hàng thành CASE trong UPDATE

**Yêu cầu:** áp dụng tỷ lệ discount cho các đơn paid theo hạng khách hàng:

- Gold: 10%.
- Silver: 5%.
- Bronze: 0%.

### 5.1. Một vòng lặp quen thuộc

```sql
BEGIN;

DO $$
DECLARE
    r record;
    v_rate numeric;
BEGIN
    FOR r IN
        SELECT o.order_id, o.amount, c.tier
        FROM set_lab.orders AS o
        JOIN set_lab.customers AS c
          ON c.customer_id = o.customer_id
        WHERE o.status = 'paid'
    LOOP
        IF r.tier = 'gold' THEN
            v_rate := 0.10;
        ELSIF r.tier = 'silver' THEN
            v_rate := 0.05;
        ELSE
            v_rate := 0;
        END IF;

        UPDATE set_lab.orders
        SET discount = round(r.amount * v_rate, 2)
        WHERE order_id = r.order_id;
    END LOOP;
END;
$$;

ROLLBACK;
```

### 5.2. SQL theo tập dùng CASE và UPDATE FROM

```sql
BEGIN;

UPDATE set_lab.orders AS o
SET discount = round(
    o.amount *
      CASE c.tier
        WHEN 'gold' THEN 0.10
        WHEN 'silver' THEN 0.05
        ELSE 0
      END,
    2
)
FROM set_lab.customers AS c
WHERE c.customer_id = o.customer_id
  AND o.status = 'paid'
RETURNING o.order_id, o.customer_id, o.amount, o.discount;

ROLLBACK;
```

Cả điều kiện JOIN và bảng hạng khách hàng đều được đưa vào **một kế hoạch SQL**.

### 5.3. Kết quả logic

Trên năm đơn paid ban đầu:

| customer_id | amount | tier | discount |
| ---: | ---: | --- | ---: |
| 1 | 100.00 | gold | 10.00 |
| 1 | 80.00 | gold | 8.00 |
| 2 | 200.00 | silver | 10.00 |
| 3 | 40.00 | bronze | 0.00 |
| 4 | 150.00 | gold | 15.00 |

Tổng discount là **43.00**. Thứ tự dòng `RETURNING` có thể khác; bảng chỉ minh họa tập kết quả.

### 5.4. Khi logic nhiều nhánh

Một `CASE` dài hàng trăm nhánh có thể khó bảo trì; nếu tỷ lệ discount là quy tắc dữ liệu, nên lưu bảng mapping `tier → rate` có constraint phù hợp rồi JOIN. Set-based không có nghĩa nhồi toàn bộ business logic vào một biểu thức khó đọc.

## 6. Mẫu 3: INSERT từng hàng thành INSERT ... SELECT

**Yêu cầu:** ghi một bản audit note cho mọi đơn paid.

### 6.1. Vòng lặp chèn từng bản ghi

```sql
BEGIN;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM set_lab.orders
        WHERE status = 'paid'
    LOOP
        INSERT INTO set_lab.audit_notes(order_id, note)
        VALUES (r.order_id, 'Đơn đã thanh toán');
    END LOOP;
END;
$$;

ROLLBACK;
```

### 6.2. Một câu INSERT ... SELECT

```sql
BEGIN;

INSERT INTO set_lab.audit_notes (order_id, note)
SELECT
    o.order_id,
    'Đơn đã thanh toán'
FROM set_lab.orders AS o
WHERE o.status = 'paid'
RETURNING audit_id, order_id, note;

ROLLBACK;
```

Trong tập mẫu, câu `INSERT ... SELECT` sinh **5 audit rows**. Nó đặc biệt hữu ích cho:

- Di chuyển dữ liệu sang bảng staging.
- Nhân bản dữ liệu theo quy tắc.
- Tạo hàng loạt thông báo nội bộ.
- Xây bảng kết quả từ SELECT/JOIN.

### 6.3. Idempotency không tự xuất hiện

Nếu chạy lại cùng `INSERT ... SELECT` mà không có ràng buộc/chính sách xử lý trùng lặp, bảng audit sẽ có **thêm năm bản ghi tương đương**. Set-based không đồng nghĩa tự idempotent.

Với hệ thống yêu cầu tối đa một audit note loại `paid` trên mỗi order, có thể thiết kế khóa nghiệp vụ riêng, ví dụ `(order_id, event_type)`, rồi dùng `ON CONFLICT DO NOTHING`; không dùng nội dung text không chuẩn hóa làm unique key tùy tiện.

### 6.4. Không nhầm với COPY

`INSERT ... SELECT` là phép chuyển đổi/chèn từ query SQL. Để nhập dữ liệu rất lớn từ tệp/luồng bên ngoài, PostgreSQL `COPY` thường là một lựa chọn cần benchmark. Cả hai đều tránh gửi từng lệnh INSERT cho mỗi row từ client, nhưng phục vụ ngữ cảnh khác nhau.

## 7. Mẫu 4: Tổng hợp theo nhóm thay vòng lặp cộng dồn

**Yêu cầu:** tính tổng số tiền và số đơn paid cho từng khách hàng.

### 7.1. Cách thủ tục nhiều truy vấn

Một cách dễ viết nhưng có overhead:

```sql
DO $$
DECLARE
    r record;
    v_total numeric;
    v_count bigint;
BEGIN
    FOR r IN
        SELECT customer_id FROM set_lab.customers
    LOOP
        SELECT
            COALESCE(SUM(amount), 0),
            COUNT(*)
        INTO v_total, v_count
        FROM set_lab.orders
        WHERE customer_id = r.customer_id
          AND status = 'paid';

        RAISE NOTICE
            'customer %, revenue %, count %',
            r.customer_id, v_total, v_count;
    END LOOP;
END;
$$;
```

Với 100.000 khách hàng, ví dụ có thể thực thi một truy vấn tổng hợp cho mỗi khách hàng. Nếu thiếu index phù hợp, mỗi vòng còn có thể quét bảng orders đáng kể.

### 7.2. Một GROUP BY trên toàn tập

```sql
SELECT
    customer_id,
    SUM(amount) AS total_paid,
    COUNT(*) AS paid_orders
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
ORDER BY customer_id;
```

Kết quả:

| customer_id | total_paid | paid_orders |
| ---: | ---: | ---: |
| 1 | 180.00 | 2 |
| 2 | 200.00 | 1 |
| 3 | 40.00 | 1 |
| 4 | 150.00 | 1 |

PostgreSQL có thể chọn `HashAggregate`, `GroupAggregate`, sort hoặc phương án kết hợp tùy bảng, thống kê và index. Người viết chỉ cần khai báo phép tổng hợp.

### 7.3. Bao gồm khách chưa có đơn paid

`GROUP BY` trên bảng orders chỉ trả khách hàng có ít nhất một row paid. Muốn **tất cả khách**, kể cả không có đơn, dùng `LEFT JOIN` cùng điều kiện lọc hợp lý:

```sql
SELECT
    c.customer_id,
    c.full_name,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ), 0
    ) AS total_paid,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
```

**Không** chuyển điều kiện `o.status='paid'` vào `WHERE` một cách tùy tiện nếu cần giữ khách không có đơn. Một predicate trên bảng phải của LEFT JOIN trong WHERE có thể loại các hàng không match và làm mất mục tiêu “gồm tất cả khách”.

### 7.4. FILTER thay nhiều IF khi thống kê

```sql
SELECT
    customer_id,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'pending'
    ) AS pending_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS revenue
FROM set_lab.orders
GROUP BY customer_id
ORDER BY customer_id;
```

Một lần mô tả aggregation có thể tính nhiều chỉ số. Nếu nhóm không có row paid, `SUM(...) FILTER (...)` có thể trả SQL NULL; dùng `COALESCE(...,0)` khi contract muốn số 0.

## 8. Mẫu 5: UPSERT hàng loạt thay SELECT/IF/UPDATE từng khóa

**Yêu cầu:** làm mới bảng `customer_totals` bằng doanh thu paid hiện tại.

### 8.1. Vòng lặp theo customer

```sql
BEGIN;

DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT
            customer_id,
            SUM(amount) AS total_paid,
            COUNT(*) AS paid_orders
        FROM set_lab.orders
        WHERE status = 'paid'
        GROUP BY customer_id
    LOOP
        INSERT INTO set_lab.customer_totals (
            customer_id, total_paid, paid_orders
        )
        VALUES (
            r.customer_id, r.total_paid, r.paid_orders
        )
        ON CONFLICT (customer_id) DO UPDATE
            SET total_paid = EXCLUDED.total_paid,
                paid_orders = EXCLUDED.paid_orders,
                calculated_at = clock_timestamp();
    END LOOP;
END;
$$;

ROLLBACK;
```

### 8.2. Một lệnh INSERT ... SELECT ... ON CONFLICT

```sql
BEGIN;

INSERT INTO set_lab.customer_totals AS t (
    customer_id,
    total_paid,
    paid_orders
)
SELECT
    customer_id,
    SUM(amount),
    COUNT(*)
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
ON CONFLICT (customer_id)
DO UPDATE SET
    total_paid = EXCLUDED.total_paid,
    paid_orders = EXCLUDED.paid_orders,
    calculated_at = clock_timestamp()
RETURNING
    customer_id, total_paid, paid_orders;

ROLLBACK;
```

Trong `ON CONFLICT`, `EXCLUDED` là giá trị dự định chèn nhưng bị trùng khóa; đây là cú pháp PostgreSQL cho UPSERT.

### 8.3. Tránh cập nhật nhiều lần cùng một target row

`INSERT ... ON CONFLICT DO UPDATE` không cho phép một command ảnh hưởng **cùng một existing row nhiều hơn một lần** theo cách không xác định. Nếu input `SELECT` sinh hai rows có cùng conflict key, PostgreSQL có thể báo cardinality violation. Vì vậy phải xử lý duplicate inputs trước, ví dụ `GROUP BY customer_id` ở ví dụ trên.

### 8.4. Vấn đề nhóm biến mất

Nếu một khách **không còn đơn paid nào**, SELECT tổng hợp chỉ từ orders paid không sinh row cho khách đó. UPSERT trong 8.2 sẽ **không tự đặt total_paid=0** ở hàng customer_totals cũ. Đó là khác biệt giữa “upsert các nhóm đang có” và “đồng bộ toàn bộ trạng thái”.

Muốn bao gồm tất cả khách, sử dụng LEFT JOIN:

```sql
BEGIN;

INSERT INTO set_lab.customer_totals AS t (
    customer_id, total_paid, paid_orders
)
SELECT
    c.customer_id,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ), 0
    ),
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    )
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ON CONFLICT (customer_id)
DO UPDATE SET
    total_paid = EXCLUDED.total_paid,
    paid_orders = EXCLUDED.paid_orders,
    calculated_at = clock_timestamp();

SELECT * FROM set_lab.customer_totals
ORDER BY customer_id;

ROLLBACK;
```

Cách này xử lý những khách không còn đơn paid bằng `(0,0)`. Nếu khách bị xóa hoàn toàn khỏi `customers` mà bảng tổng hợp vẫn còn hàng cũ, cần có chính sách FK/cascade/cleanup riêng.

### 8.5. UPSERT không luôn là lựa chọn nhanh nhất

Khi mọi row của bảng tổng hợp cần làm lại và có thể khóa/gián đoạn đọc, `TRUNCATE + INSERT` trong một transaction hoặc thay bảng theo phiên bản có thể phù hợp hơn. Với live readers, cần tính locks, consistency và chi phí riêng. Không mặc định UPSERT cho mọi lần rebuild bảng có hàng trăm triệu rows.

## 9. Mẫu 6: DELETE theo điều kiện/quan hệ thay vòng lặp

**Yêu cầu:** xóa audit notes của những đơn đã bị cancelled.

### 9.1. Vòng lặp xóa từng order

```sql
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM set_lab.orders
        WHERE status = 'cancelled'
    LOOP
        DELETE FROM set_lab.audit_notes
        WHERE order_id = r.order_id;
    END LOOP;
END;
$$;
```

### 9.2. DELETE USING

```sql
BEGIN;

DELETE FROM set_lab.audit_notes AS a
USING set_lab.orders AS o
WHERE a.order_id = o.order_id
  AND o.status = 'cancelled'
RETURNING a.audit_id, a.order_id, a.note;

ROLLBACK;
```

Đây là một statement DELETE với join condition. Nếu chưa có audit notes tương ứng trong lab, kết quả DELETE **0 rows** là đúng.

### 9.3. DELETE WHERE EXISTS

Một dạng tương đương về ý nghĩa:

```sql
BEGIN;

DELETE FROM set_lab.audit_notes AS a
WHERE EXISTS (
    SELECT 1
    FROM set_lab.orders AS o
    WHERE o.order_id = a.order_id
      AND o.status = 'cancelled'
);

ROLLBACK;
```

`EXISTS` mô tả sự tồn tại của ít nhất một row khớp, không yêu cầu join result trả một row duy nhất. PostgreSQL có thể tối ưu thành semijoin hoặc access path phù hợp.

### 9.4. Cẩn thận quy tắc xóa nghiệp vụ

Một DELETE theo tập có thể xóa rất nhiều rows trong một transaction, tạo WAL, dead tuples và lock contention. Đừng thay vòng lặp bằng một DELETE toàn bảng trước khi kiểm tra retention, FK, trigger, audit và khối lượng cần tác động.

## 10. Mẫu 7: UPDATE ... FROM với source là một tập kết quả

Trong SQL, `UPDATE ... FROM` cho phép cập nhật target dựa trên một source relation hoặc subquery:

```sql
UPDATE target AS t
SET target_column = s.computed_value
FROM (
    SELECT key, expression AS computed_value
    FROM source
) AS s
WHERE t.key = s.key;
```

Điểm quan trọng nhất là **mỗi target row nên khớp tối đa một source row**.

### 10.1. Ví dụ đúng: map customer_id đến tier

```sql
BEGIN;

UPDATE set_lab.orders AS o
SET discount = CASE c.tier
    WHEN 'gold' THEN round(o.amount * 0.10, 2)
    WHEN 'silver' THEN round(o.amount * 0.05, 2)
    ELSE 0
END
FROM set_lab.customers AS c
WHERE c.customer_id = o.customer_id
  AND o.status = 'paid';

ROLLBACK;
```

`customers.customer_id` là PRIMARY KEY, nên join trên cột đó khớp tối đa một customer row cho mỗi order.

### 10.2. Ví dụ nguy hiểm: source nhiều rows cùng key

```sql
-- Sai về mặt ý nghĩa nếu muốn tổng amount từng customer:
-- UPDATE set_lab.customer_totals AS t
-- SET total_paid = o.amount
-- FROM set_lab.orders AS o
-- WHERE t.customer_id = o.customer_id;
```

Một khách có nhiều đơn: một target row ở `customer_totals` có thể match nhiều rows ở `orders`. PostgreSQL sẽ cập nhật target theo **một row nguồn trong các matches**, nhưng **không được bảo đảm đó là row nào**. Đừng dựa vào thứ tự SELECT, heap hoặc ORDER BY để định nghĩa hành vi.

### 10.3. Cách sửa: tổng hợp trước khi UPDATE

```sql
BEGIN;

INSERT INTO set_lab.customer_totals (
    customer_id, total_paid, paid_orders
)
SELECT
    customer_id, 0, 0
FROM set_lab.customers
ON CONFLICT (customer_id) DO NOTHING;

UPDATE set_lab.customer_totals AS t
SET
    total_paid = s.total_paid,
    paid_orders = s.paid_orders,
    calculated_at = clock_timestamp()
FROM (
    SELECT
        customer_id,
        SUM(amount) AS total_paid,
        COUNT(*) AS paid_orders
    FROM set_lab.orders
    WHERE status = 'paid'
    GROUP BY customer_id
) AS s
WHERE t.customer_id = s.customer_id;

SELECT * FROM set_lab.customer_totals
ORDER BY customer_id;

ROLLBACK;
```

`GROUP BY customer_id` tạo tối đa một row nguồn cho mỗi target key, nên phép cập nhật có ý nghĩa xác định hơn. Trường hợp khách không có đơn paid vẫn phải xử lý riêng nếu cần đặt về 0; `GROUP BY` trên orders paid không sinh họ.

### 10.4. JOIN nhân bản dữ liệu trong phép tính

Nếu JOIN `orders` với `order_items` (một đơn nhiều sản phẩm), việc `SUM(o.amount)` sau JOIN có thể nhân số amount của đơn theo số item. Đây là lỗi số liệu thường gặp khi chuyển các vòng lặp sang một query lớn.

Giải pháp thường là tổng hợp ở **đúng granularity** trước khi JOIN, hoặc dùng số liệu item thật nếu đó là ý định. Không cứu bằng `SUM(DISTINCT o.amount)` nếu hai đơn hợp lệ có cùng amount.

## 11. Mẫu 8: running total và so sánh hàng trước bằng window functions

Một lý do thường gặp để viết vòng lặp là “mỗi hàng cần biết tổng của các hàng trước”. Trong nhiều trường hợp, SQL window functions biểu diễn trực tiếp điều đó.

### 11.1. Tổng lũy kế theo khách

```sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_paid_total
FROM set_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at, order_id;
```

Giải thích:

- `PARTITION BY customer_id` tạo nhóm cửa sổ logic cho từng khách.
- `ORDER BY ordered_at, order_id` định nghĩa thứ tự trong nhóm.
- `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` lấy tất cả hàng từ đầu nhóm đến hàng hiện tại.
- `SUM(amount) OVER (...)` tính tổng lũy kế mà không cần vòng lặp cùng biến `v_sum`.

Trên khách 1, hai đơn paid 100 và 80 có running totals **100** và **180**.

### 11.2. LAG để lấy giá trị hàng trước

```sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_paid_amount
FROM set_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at, order_id;
```

`LAG` trả SQL NULL khi không có hàng trước trong partition. Có thể dùng `COALESCE` nếu nghiệp vụ muốn giá trị thay thế, nhưng phải phân biệt “không có hàng trước” với giá trị 0 thật.

### 11.3. ROWS vs RANGE trong window frame

Không coi `ROWS` và `RANGE` tương đương nếu nhiều hàng có cùng giá trị ORDER BY. Với running totals theo từng đơn, `ROWS` và một tie-breaker `order_id` thường dễ kiểm soát hơn.

### 11.4. Khi vẫn cần thuật toán có trạng thái phức tạp

Nếu mỗi bước thay đổi trạng thái theo kết quả của bước trước một cách không thể diễn đạt hợp lý bằng window, recursive CTE hay các phép SQL khác, một thuật toán thủ tục có thể thích hợp. Nhưng hãy kiểm tra window functions trước khi tự viết vòng lặp cộng dồn hoặc tìm “đơn trước đó”.

## 12. Mẫu 9: chọn hàng mới nhất của mỗi nhóm mà không lặp

**Yêu cầu:** tìm đơn hàng gần nhất của mỗi khách.

### 12.1. Cách vòng lặp

```sql
DO $$
DECLARE
    r record;
    v_order record;
BEGIN
    FOR r IN SELECT customer_id FROM set_lab.customers
    LOOP
        SELECT order_id, ordered_at, status
        INTO v_order
        FROM set_lab.orders
        WHERE customer_id = r.customer_id
        ORDER BY ordered_at DESC, order_id DESC
        LIMIT 1;

        RAISE NOTICE 'customer %, order %',
            r.customer_id, v_order.order_id;
    END LOOP;
END;
$$;
```

Đây là N truy vấn riêng cho N khách. Với số lượng lớn, có nhiều cách set-based.

### 12.2. PostgreSQL DISTINCT ON

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    status
FROM set_lab.orders
ORDER BY
    customer_id,
    ordered_at DESC,
    order_id DESC;
```

`DISTINCT ON (customer_id)` giữ một hàng đại diện của mỗi nhóm. `ORDER BY` có tiền tố tương ứng, sau đó sắp mới nhất trước; `order_id DESC` là tie-breaker nếu hai đơn cùng ngày.

Đây là tính năng tiện lợi của PostgreSQL, không phải cú pháp `DISTINCT ON` phổ biến ở mọi RDBMS.

### 12.3. ROW_NUMBER theo nhóm

```sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        status,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM set_lab.orders
)
SELECT customer_id, order_id, ordered_at, status
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
```

Đây là cách SQL chuẩn hơn về mặt tính di động. `ROW_NUMBER` cũng hỗ trợ top-N theo nhóm với `WHERE rn <= N`.

### 12.4. LATERAL khi mỗi nhóm cần một truy vấn con tối ưu

```sql
SELECT
    c.customer_id,
    o.order_id,
    o.ordered_at,
    o.status
FROM set_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id, ordered_at, status
    FROM set_lab.orders
    WHERE customer_id = c.customer_id
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 1
) AS o ON TRUE
ORDER BY c.customer_id;
```

`LATERAL` cho phép subquery tham chiếu `c.customer_id`. Nó vẫn có thể tương ứng nhiều index lookups bên trong execution plan, nhưng **không cần chuyển từng row qua PL/pgSQL**. Với index như `(customer_id, ordered_at DESC, order_id DESC)` và nhiều khách, nó có thể phù hợp; điều kiện cụ thể do planner và workload quyết định.

### 12.5. Đừng thay loop bằng query set-based không có thứ tự xác định

`DISTINCT ON` hoặc `ROW_NUMBER` dùng `ORDER BY ordered_at DESC` mà bỏ tie-breaker có thể chọn không xác định giữa hai đơn cùng ngày. Logic thủ tục cũ cũng có thể sai nếu chỉ `LIMIT 1` mà không sắp xếp rõ. Khi chuyển đổi, đảm bảo **ý nghĩa “mới nhất” được định nghĩa đầy đủ**.

## 13. Mẫu 10: chuyển các vòng lặp sinh ngày/số thành generate_series

PL/pgSQL thường dùng vòng lặp để sinh các kỳ báo cáo:

```sql
DO $$
DECLARE
    v_day date := DATE '2026-11-01';
BEGIN
    WHILE v_day <= DATE '2026-11-07' LOOP
        RAISE NOTICE '%', v_day;
        v_day := v_day + 1;
    END LOOP;
END;
$$;
```

Khi mục tiêu là tạo **tập các ngày** để JOIN, PostgreSQL có `generate_series`:

```sql
SELECT g.day_ts::date AS sale_date
FROM generate_series(
    TIMESTAMP '2026-11-01',
    TIMESTAMP '2026-11-07',
    INTERVAL '1 day'
) AS g(day_ts)
ORDER BY sale_date;
```

### 13.1. Tạo bảng lịch cùng doanh thu từng ngày

```sql
WITH days AS (
    SELECT g.day_ts::date AS sale_date
    FROM generate_series(
        TIMESTAMP '2026-11-01',
        TIMESTAMP '2026-11-07',
        INTERVAL '1 day'
    ) AS g(day_ts)
),
revenue AS (
    SELECT
        ordered_at AS sale_date,
        SUM(amount) AS revenue
    FROM set_lab.orders
    WHERE status = 'paid'
    GROUP BY ordered_at
)
SELECT
    d.sale_date,
    COALESCE(r.revenue, 0) AS revenue
FROM days AS d
LEFT JOIN revenue AS r
  ON r.sale_date = d.sale_date
ORDER BY d.sale_date;
```

Những ngày không có đơn paid vẫn xuất hiện với revenue 0. Không cần một vòng lặp INSERT/SELECT cho từng ngày.

### 13.2. generate_series không chỉ sinh ngày

```sql
SELECT n
FROM generate_series(1, 10) AS s(n);
```

Nhưng đừng sinh hàng tỷ giá trị rồi giữ toàn bộ trong một CTE chỉ để thay thế một vòng lặp vốn có thể được tổ chức theo batch. Cần xét cardinality, output size và mục tiêu thật.

## 14. Mẫu 11: duyệt array bằng UNNEST hoặc = ANY

Một PL/pgSQL function nhận `integer[]` chứa customer IDs, rồi duyệt:

```sql
DO $$
DECLARE
    v_ids integer[] := ARRAY[1, 2, 4];
    v_id integer;
BEGIN
    FOREACH v_id IN ARRAY v_ids LOOP
        RAISE NOTICE 'customer ID %', v_id;
    END LOOP;
END;
$$;
```

Nếu mục tiêu là lọc dữ liệu, không cần duyệt.

### 14.1. ANY với mảng parameter

```sql
SELECT
    order_id, customer_id, amount, status
FROM set_lab.orders
WHERE customer_id = ANY(ARRAY[1, 2, 4]::integer[])
ORDER BY customer_id, order_id;
```

Với parameter `$1::integer[]` trong prepared query, cùng biểu thức có thể nhận toàn bộ danh sách từ client. Planner chọn cách truy cập dữ liệu theo cardinality và statistics.

### 14.2. UNNEST để tạo relation từ array

```sql
SELECT
    ids.customer_id,
    c.full_name
FROM unnest(ARRAY[1, 2, 4]::integer[])
    AS ids(customer_id)
JOIN set_lab.customers AS c
  ON c.customer_id = ids.customer_id
ORDER BY ids.customer_id;
```

`UNNEST` hữu ích khi cần JOIN hoặc dùng danh sách input như một bảng. Với input mảng có duplicate IDs, `UNNEST` giữ duplicates; JOIN có thể nhân bản rows nếu không xử lý. `= ANY(...)` kiểm tra membership không tự nhân rows theo số phần tử giống nhau trong array.

### 14.3. Mảng có NULL

`customer_id = ANY(ARRAY[NULL::integer])` có thể trả SQL UNKNOWN thay vì FALSE. Nếu cần logic membership không NULL, chuẩn hóa input hoặc thiết kế rõ cách xử lý NULL, tránh suy diễn ba giá trị SQL sai.

### 14.4. Danh sách cực lớn

Với hàng triệu IDs, một array quá lớn có thể tốn memory/transfer; nhập vào staging/temporary table, lập index hoặc `ANALYZE` khi phù hợp có thể tốt hơn. Set-based không đồng nghĩa phải truyền mọi dữ liệu vào **một biểu thức array khổng lồ**.

## 15. Mẫu 12: JSONB arrays và việc mở rộng tập hàng

Một JSON payload chứa nhiều mục:

```json
{"items":[{"sku":"A","qty":2},{"sku":"B","qty":1}]}
```

Thay vì parse từng object trong vòng lặp SQL/PLpgSQL, có thể dùng `jsonb_array_elements` để biến JSON array thành nhiều hàng:

```sql
SELECT
    item ->> 'sku' AS sku,
    (item ->> 'qty')::integer AS qty
FROM jsonb_array_elements(
    '[
        {"sku":"A","qty":2},
        {"sku":"B","qty":1}
    ]'::jsonb
) AS i(item);
```

### 15.1. Dùng jsonb_to_recordset khi schema biết trước

```sql
SELECT sku, qty
FROM jsonb_to_recordset(
    '[
        {"sku":"A","qty":2},
        {"sku":"B","qty":1}
    ]'::jsonb
) AS x(sku text, qty integer);
```

Đầu ra là một relation có cột typed, có thể JOIN để validate SKU trước khi INSERT.

### 15.2. Validate đầu vào trước khi cast

Các hàm recordset/cast có thể lỗi nếu `qty` không phải số hợp lệ hoặc JSON không có cấu trúc array phù hợp. Với dữ liệu người dùng, cần xử lý validation: phần tử thiếu key, JSON null, số âm, duplicate SKU và giới hạn số phần tử.

Set-based giúp loại bỏ vòng lặp nhập hàng, nhưng không tự tạo schema contract hay authorization.

### 15.3. INSERT hàng loạt từ JSON

```sql
CREATE TABLE set_lab.order_item_staging (
    sku text NOT NULL,
    qty integer NOT NULL CHECK (qty > 0)
);

INSERT INTO set_lab.order_item_staging (sku, qty)
SELECT sku, qty
FROM jsonb_to_recordset(
    '[{"sku":"A","qty":2},{"sku":"B","qty":1}]'::jsonb
) AS x(sku text, qty integer);
```

Đây là ví dụ nhỏ cho việc chuyển JSON array thành một tập rows. Khi nhập dữ liệu thật, staging cần key/batch ID, kiểm tra duplicates, và quy trình commit/rollback/cleanup.

## 16. Dùng CTE để chia bài toán thành các tập trung gian

Khi phép biến đổi phức tạp, không nhất thiết chuyển một vòng lặp thành một SQL statement dày đặc khó hiểu. **Common Table Expressions (CTE)** cho phép đặt tên các tập trung gian trong một statement.

### 16.1. Ví dụ nhiều bước: xác định doanh thu, xếp hạng, lọc khách hàng

```sql
WITH revenue_by_customer AS (
    SELECT
        customer_id,
        SUM(amount) AS revenue
    FROM set_lab.orders
    WHERE status = 'paid'
    GROUP BY customer_id
),
ranked AS (
    SELECT
        customer_id,
        revenue,
        DENSE_RANK() OVER (
            ORDER BY revenue DESC
        ) AS revenue_rank
    FROM revenue_by_customer
)
SELECT
    c.customer_id,
    c.full_name,
    r.revenue,
    r.revenue_rank
FROM ranked AS r
JOIN set_lab.customers AS c
  ON c.customer_id = r.customer_id
WHERE r.revenue_rank <= 3
ORDER BY r.revenue_rank, r.customer_id;
```

Trong lab, doanh thu theo khách hàng là 200, 180, 150, 40. Ba vị trí đầu thuộc khách 2, 1, 4.

### 16.2. CTE không phải biến PL/pgSQL

Một CTE là biểu thức quan hệ trong câu SQL; nó không tự duy trì dữ liệu qua nhiều statements như temporary table, không tự COMMIT từng bước và không bảo đảm bạn có thể tham chiếu tên CTE ở câu SQL kế tiếp.

### 16.3. Planner có thể inline CTE

Trong các PostgreSQL major hiện đại, CTE không-recursive, không side-effect và đủ điều kiện có thể được planner gộp vào parent query thay vì luôn materialize; `MATERIALIZED` và `NOT MATERIALIZED` có thể ảnh hưởng lựa chọn khi áp dụng đúng điều kiện.

Vì vậy không nên nói “WITH luôn tạo một bảng tạm trước rồi mới chạy bước sau”. Dùng `EXPLAIN` để quan sát kế hoạch thay vì suy đoán cơ chế.

### 16.4. CTE có thao tác ghi

PostgreSQL cho phép các *data-modifying CTE* trong những điều kiện cú pháp phù hợp, dùng `RETURNING` để truyền dữ liệu kết quả sang statement chính:

```sql
BEGIN;

WITH changed AS (
    UPDATE set_lab.orders
    SET discount = 2.00
    WHERE status = 'pending'
    RETURNING order_id, discount
)
INSERT INTO set_lab.audit_notes(order_id, note)
SELECT
    order_id,
    'Discount changed to ' || discount::text
FROM changed
RETURNING audit_id, order_id, note;

ROLLBACK;
```

**Mục tiêu:** tập hàng thực sự được UPDATE được đưa trực tiếp vào INSERT audit, không phải truy vấn lại bảng theo từng order ID.

### 16.5. Tránh phụ thuộc thứ tự không bảo đảm của DML CTE

Nếu một statement chứa nhiều data-modifying CTE, không được giả định chúng chạy tuần tự đúng theo thứ tự chữ viết và có thể đọc thay đổi của nhau tùy ý. PostgreSQL quy định chúng chạy trên cùng snapshot và thứ tự thực thi không đoán trước; dùng `RETURNING` để truyền kết quả thay vì đọc lại target và kỳ vọng nhìn thấy thay đổi của CTE khác.

Đừng cố cập nhật cùng một target row hai lần trong một statement phức tạp rồi dựa vào thứ tự CTE để chọn kết quả cuối.

## 17. SQL theo tập và tính nhất quán giao dịch

Vòng lặp:

```sql
FOR r IN SELECT ... LOOP
    UPDATE ... WHERE id = r.id;
END LOOP;
```

và một `UPDATE ... WHERE ...` có thể khác nhau về **khoảng thời gian, snapshot và khả năng nhìn thấy thay đổi đồng thời**, không chỉ hiệu năng.

### 17.1. Một statement có tính atomicity

Một statement UPDATE thông thường là một phần của transaction. Nếu câu lệnh bị lỗi và transaction rollback, PostgreSQL không commit “một nửa những row đầu” của statement ấy. Những thay đổi đã thực hiện nhưng chưa commit bị hoàn tác theo ngữ nghĩa transaction.

### 17.2. Vòng lặp trong một transaction cũng có atomicity

Nếu toàn bộ `DO$$ ... LOOP ... $$` chạy trong một transaction, không có exception handler giữ lại từng lỗi, PostgreSQL cũng không tự COMMIT từng vòng. Vì vậy **không đúng** khi nói vòng lặp mặc định làm hàng trước commit còn hàng sau thất bại.

Khác biệt chủ yếu có thể nằm ở số lần thực thi statements, locks đã giữ, cách nhìn dữ liệu và cách lỗi được xử lý.

### 17.3. Read Committed có nhiều command snapshots

Ở isolation level mặc định `READ COMMITTED`, các SQL commands nối tiếp có thể có snapshots khác nhau. Nếu vòng lặp phát một UPDATE mới cho mỗi row, dữ liệu từ transaction khác có thể COMMIT giữa các lần ấy; kết quả thực tế có thể phụ thuộc diễn biến concurrency.

Một statement UPDATE theo tập có semantics của **một command** và xử lý concurrent updates theo quy tắc MVCC/locking riêng. Khi chuyển đổi, cần xác định nghiệp vụ muốn “chốt tập rows tại một thời điểm” hay “liên tục thấy mọi thay đổi mới giữa các bước”.

### 17.4. Một UPDATE lớn không ngăn transactions khác hoàn toàn

Nó lấy table-level lock phù hợp và row-level locks đối với hàng cần thay đổi. Readers thông thường vẫn có thể SELECT theo snapshot MVCC, nhưng các writers khác chạm những hàng trùng có thể chờ hoặc cạnh tranh.

Đừng hiểu set-based là “không có locks”.

### 17.5. Các lệnh sau UPDATE trong cùng transaction

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';

SELECT COUNT(*)
FROM set_lab.orders
WHERE status = 'pending'
  AND discount = 5.00;

ROLLBACK;
```

SELECT sau trong cùng transaction thấy các thay đổi của transaction mình theo quy tắc PostgreSQL. Session khác không được thấy thay đổi chưa commit.

### 17.6. Khi cần khóa hàng trước quyết định

Một số nghiệp vụ, ví dụ phân bổ đơn hàng cho worker, cần chọn hàng chưa xử lý và **chiếm quyền xử lý** tránh hai workers nhận cùng một item. Set-based có thể phối hợp `SELECT ... FOR UPDATE SKIP LOCKED`, nhưng phải xem xét tính công bằng, retry và những hàng bị skip.

Không dùng `SKIP LOCKED` như một cách tăng tốc SELECT báo cáo chung: nó cố tình cho cái nhìn không đầy đủ khi gặp hàng bị khóa.

## 18. Rủi ro khi gom quá lớn vào một câu lệnh

Một SQL statement có thể tác động mười triệu hàng. Nó loại bớt overhead của vòng lặp nhưng có thể làm tăng áp lực vận hành:

- Transaction giữ row locks lâu.
- WAL generation và replication lag.
- Dead tuple versions/áp lực autovacuum khi UPDATE/DELETE lớn.
- Temp files vì sort/hash.
- Khả năng rollback lớn khi statement lỗi.
- Contention với các transaction giao dịch.
- Độ trễ đọc/ghi khi I/O bị bão hòa.

### 18.1. Set-based không có nghĩa mọi lúc phải “một lệnh duy nhất”

Khi cần sửa 100 triệu hàng trong production, có thể chia thành **nhiều batch** với mỗi batch dùng một SQL set-based statement. Ví dụ mỗi batch xử lý 5.000–50.000 rows theo khóa ổn định, commit ở ranh giới do orchestrator hoặc procedure được phép làm.

### 18.2. Quy tắc chọn batch size

Không có số “5.000 là tối ưu” cho mọi hệ thống. Cần đo:

- Số hàng và số bytes mỗi batch.
- Thời gian lock và transaction.
- Độ lớn WAL/temp.
- Thông lượng trong giờ cao điểm.
- Tốc độ autovacuum và replication.
- SLA của các writers khác.

Kích thước batch là **đặc tính vận hành cần benchmark**, không chỉ tham số code.

## 19. Batch UPDATE bằng tập ID có giới hạn

PostgreSQL không có cú pháp chuẩn `UPDATE ... LIMIT N` trực tiếp giống một số hệ quản trị khác. Một mẫu thường gặp là chọn trước tập ID có thứ tự rồi UPDATE theo tập:

```sql
BEGIN;

WITH batch AS (
    SELECT order_id
    FROM set_lab.orders
    WHERE status = 'pending'
      AND discount = 0
    ORDER BY order_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE set_lab.orders AS o
SET discount = 5.00
FROM batch AS b
WHERE o.order_id = b.order_id
RETURNING o.order_id, o.discount;

ROLLBACK;
```

### 19.1. Vì sao dùng key xác định?

`ORDER BY order_id` giúp batch chọn một tập có thứ tự dự kiến. `order_id` là PRIMARY KEY nên tránh việc một target row join nhiều source rows.

`FOR UPDATE SKIP LOCKED` khóa những rows được chọn và bỏ qua hàng đang bị transaction khác giữ lock, hữu ích cho **queue-like worker patterns**. Nhưng nó có thể bỏ một số hàng hợp lệ tại lần chạy hiện tại; cần quét lại trong lần sau.

### 19.2. Batch không phải pagination OFFSET

Một vòng:

```sql
-- Khái niệm sai với dataset đang thay đổi:
-- OFFSET 0 LIMIT 100
-- OFFSET 100 LIMIT 100
-- OFFSET 200 LIMIT 100
```

có thể bỏ qua/đếm trùng khi các hàng được cập nhật khiến điều kiện WHERE hoặc thứ tự thay đổi. Với job chuyển `discount=0` thành 5, mỗi batch nên tiếp tục chọn **những hàng còn discount=0** thay vì dịch OFFSET.

### 19.3. Ai điều khiển nhiều batch?

Một orchestrator ngoài DB hoặc PostgreSQL procedure phù hợp có thể:

1. Chạy một batch UPDATE theo tập.
2. Đọc số rows cập nhật.
3. COMMIT.
4. Kiểm tra thời gian và trạng thái hệ thống.
5. Lặp đến khi không còn hàng phù hợp — kèm chính sách retry những hàng bị SKIP LOCKED.

**Không** dùng một transaction bao trùm tất cả batch rồi kỳ vọng locks/WAL/rollback footprint giống nhiều transaction nhỏ.

### 19.4. Khi SKIP LOCKED không phù hợp

Nếu batch là một phép báo cáo hoặc một việc bắt buộc phải xử lý mọi row ngay trong một snapshot nhất quán, bỏ qua hàng đang khóa có thể làm kết quả thiếu. Với nghiệp vụ đúng đầy đủ, cần chiến lược chờ/retry/quiesce khác.

## 20. PL/pgSQL PROCEDURE và COMMIT theo batch

PostgreSQL phân biệt:

- **Function** được gọi bằng `SELECT function(...)`; không được tùy ý COMMIT trong function.
- **Procedure** được gọi bằng `CALL procedure(...)`; trong những ngữ cảnh được phép, có thể có điều khiển transaction.
- **DO block** có thể có transaction control trong những điều kiện gọi phù hợp, nhưng có ràng buộc, đặc biệt khi được đặt bên trong transaction block tường minh.

### 20.1. Không COMMIT trong mọi vòng lặp tùy ý

Không viết:

```sql
-- Mẫu không hợp lệ nếu nằm trong PL/pgSQL FUNCTION:
-- LOOP
--     UPDATE ...;
--     COMMIT;
-- END LOOP;
```

Transaction control trong PostgreSQL có điều kiện theo môi trường gọi và call stack, không phải mọi function/procedure/DO đều COMMIT được.

### 20.2. Chia batch vẫn ưu tiên SQL set-based

Trong procedure batch, phần cập nhật mỗi lần vẫn nên là:

```sql
WITH batch AS (
    SELECT id FROM work_queue
    WHERE status = 'ready'
    ORDER BY id
    LIMIT 5000
    FOR UPDATE SKIP LOCKED
)
UPDATE work_queue AS q
SET status = 'processing'
FROM batch AS b
WHERE q.id = b.id;
```

Đây là **mẫu thuật toán**, bảng `work_queue` không thuộc schema lab. Nó minh họa: **vòng lặp ở cấp batch, SQL ở cấp tập hàng**, không dùng loop 5.000 lần để phát 5.000 UPDATE.

### 20.3. Điều kiện transaction control

Các thủ tục được gọi bằng top-level `CALL` hoặc các chuỗi CALL/DO phù hợp có thể dùng COMMIT/ROLLBACK, với những hạn chế như không ở trong transaction block tường minh theo trường hợp PostgreSQL mô tả. Một `CALL` từ trong JDBC transaction do framework mở sẵn có thể **không cho phép** COMMIT bên trong procedure.

Cần đọc tài liệu **đúng PostgreSQL major** và thiết kế luồng commit rõ ràng; không chuyển bừa một loop từ function sang procedure chỉ để thêm COMMIT.

### 20.4. Exception block ảnh hưởng transaction control

Một PL/pgSQL block có `EXCEPTION` sử dụng cơ chế subtransaction cho phần block, và không thể chấm dứt transaction bên trong block có exception handler theo các hạn chế của PostgreSQL. Nếu batch cần commit từng lần và bắt lỗi riêng, cấu trúc procedure/job orchestration phải tương thích cơ chế này.

### 20.5. Khi cần checkpoint/retry chính xác

Với migration lớn, job runner bên ngoài DB có thể dễ giám sát hơn: lưu last successful key/range, transaction riêng từng batch, retry idempotent và alert. Procedure batch có thể phù hợp nhưng phải có logging/timeout và khôi phục khi session bị ngắt.

## 21. Trigger: một UPDATE theo tập vẫn có thể kích hoạt logic từng hàng

Một nhầm lẫn phổ biến là “đổi vòng lặp thành UPDATE duy nhất sẽ bỏ qua triggers”. Trong PostgreSQL, nếu bảng có **row-level trigger**, một statement UPDATE tác động 10.000 rows vẫn có thể kích hoạt trigger **cho mỗi row** theo định nghĩa.

### 21.1. Row trigger làm việc gì?

```text
UPDATE orders SET discount = ... WHERE ...
        |
        +--> row 1: BEFORE/AFTER ROW trigger
        +--> row 2: BEFORE/AFTER ROW trigger
        +--> ...
        +--> row N: BEFORE/AFTER ROW trigger
```

Chỉ vì SQL có một statement không có nghĩa mỗi business row không còn được xử lý bởi constraint, trigger hay index maintenance. Nếu trigger tự thực thi SQL nặng cho từng row, nó có thể trở thành bottleneck mới sau khi thay loop ở bên ngoài.

### 21.2. Statement-level trigger

PostgreSQL còn có trigger `FOR EACH STATEMENT`. Nó được gọi ở mức statement, không gọi một lần mỗi row theo cách row trigger.

Với các phiên bản/tình huống hỗ trợ **transition relations**, một statement-level AFTER trigger có thể truy cập tập OLD/NEW rows để xử lý nhiều hàng cùng lúc.

Ví dụ minh họa độc lập dưới đây, **chỉ nên tạo ở cuối bài lab** vì nó thay đổi hành vi các UPDATE sau:

```sql
CREATE OR REPLACE FUNCTION
    set_lab.audit_discount_changes_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO set_lab.audit_notes(order_id, note)
    SELECT
        n.order_id,
        'Discount: '
        || o.discount::text
        || ' -> '
        || n.discount::text
    FROM new_rows AS n
    JOIN old_rows AS o USING (order_id)
    WHERE o.discount IS DISTINCT FROM n.discount;

    RETURN NULL;
END;
$$;

CREATE TRIGGER tr_audit_discount_statement
AFTER UPDATE ON set_lab.orders
REFERENCING
    OLD TABLE AS old_rows
    NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION
    set_lab.audit_discount_changes_statement();
```

Thử:

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 9.00
WHERE status = 'pending';

SELECT order_id, note
FROM set_lab.audit_notes
ORDER BY audit_id;

ROLLBACK;
```

Trong transaction, trigger có thể chèn audit notes cho **những hàng thực sự đổi discount**, dùng một `INSERT ... SELECT` trên transition tables. `ROLLBACK` hoàn tác audit/UPDATE của lần thử nhưng không xóa định nghĩa trigger đã tạo.

### 21.3. Giới hạn của transition tables

Không phải mọi trigger đều có thể dùng transition tables. Chúng có điều kiện về event, timing, relation và cú pháp; ví dụ chúng được dùng trong những AFTER triggers phù hợp, không tự chuyển nguyên một trigger BEFORE ROW thành AFTER STATEMENT mà giữ mọi semantics.

Nếu nghiệp vụ phải kiểm tra/sửa **từng NEW row trước khi ghi**, BEFORE ROW trigger có thể là cần thiết. Statement trigger không tự có quyền sửa NEW row từng phần như BEFORE ROW trigger.

### 21.4. Trigger side effects có thể làm đổi ngữ nghĩa

Chuyển từ nhiều UPDATE statements sang một UPDATE statement có thể thay:

- Số lần statement-level trigger kích hoạt.
- Số rows ở transition tables.
- Thứ tự/timing của audit, thông báo và validation.
- Các effects của `statement_timestamp()`, `clock_timestamp()` hoặc volatile functions.

Vì vậy một phép rewrite SQL cần bảo đảm **kết quả nghiệp vụ** tương đương, không chỉ các cột cuối cùng giống nhau.

## 22. Vòng lặp với EXCEPTION từng hàng: khi chuyển theo tập có thể đổi hành vi lỗi

Một quy trình import đôi khi cố ý bỏ qua row xấu để tiếp tục xử lý các rows còn lại:

```sql
DO $$
DECLARE
    r record;
BEGIN
    FOR r IN SELECT ... LOOP
        BEGIN
            -- Xử lý một bản ghi.
        EXCEPTION WHEN unique_violation THEN
            -- Ghi lại lỗi/trùng và tiếp tục.
            NULL;
        END;
    END LOOP;
END;
$$;
```

Đây là mẫu cấu trúc, không chạy trực tiếp vì `SELECT ...` chỉ là placeholder.

### 22.1. Một INSERT theo tập có thể fail toàn statement

Nếu đổi thành:

```sql
INSERT INTO target (...)
SELECT ...
FROM import_staging;
```

và một row vi phạm constraint, **cả statement** có thể lỗi và rollback các thay đổi của statement. Điều này khác cách loop có `EXCEPTION` giữ lại những rows đã thành công trong cùng transaction theo các subtransactions.

### 22.2. Set-based vẫn có thể phân loại trước

Giải pháp tốt thường là:

1. Nạp vào **staging table** với kiểu dữ liệu raw phù hợp.
2. Dùng SQL set-based phân loại valid/invalid rows.
3. Ghi những rows invalid vào bảng lỗi hoặc báo cáo.
4. INSERT những rows valid vào bảng đích.
5. Dùng `ON CONFLICT` cho duplicate key theo đúng policy.

Không cần tạo một subtransaction cho mỗi row chỉ để phát hiện những lỗi schema có thể được dự đoán bằng validation query.

### 22.3. Xử lý lỗi định dạng số bằng staging

```sql
CREATE TABLE set_lab.raw_amounts (
    source_id text PRIMARY KEY,
    amount_text text
);

INSERT INTO set_lab.raw_amounts (source_id, amount_text)
VALUES
    ('A', '100.50'),
    ('B', 'bad'),
    ('C', NULL),
    ('D', '0'),
    ('E', '19.123');
```

Phân loại và cast có điều kiện:

```sql
SELECT
    source_id,
    amount_text,
    CASE
        WHEN amount_text ~
            '^[0-9]+([.][0-9]{1,2})?$'
        THEN amount_text::numeric(12,2)
        ELSE NULL
    END AS amount_value,
    CASE
        WHEN amount_text IS NULL
            THEN 'MISSING'
        WHEN amount_text ~
            '^[0-9]+([.][0-9]{1,2})?$'
            THEN 'VALID_FORMAT'
        ELSE 'INVALID_FORMAT'
    END AS validation_status
FROM set_lab.raw_amounts
ORDER BY source_id;
```

Ở dữ liệu này, A và D có định dạng hợp lệ; B và E bị từ chối; C thiếu giá trị. Một regex/format check **chưa đủ** đảm bảo mọi số cực lớn đều cast được vào `numeric(12,2)`, vì còn giới hạn độ chính xác/miền giá trị; trong production cần kiểm tra cả range/overflow và lỗi do input.

### 22.4. Khi exception per row vẫn cần

Một số logic dùng extension hoặc function có thể lỗi theo cách khó biểu diễn thành predicate SQL an toàn. Khi bắt lỗi từng row là yêu cầu nghiệp vụ, một vòng lặp có `EXCEPTION` có thể đúng, nhưng cần nhận thức rằng mỗi exception block liên quan subtransaction và có chi phí đáng kể.

Không biến toàn bộ errors thành “bỏ qua” chỉ để job chạy tiếp. Cần audit, retry policy và giới hạn lỗi.

## 23. Set-based với logic phụ thuộc thứ tự: chỗ nào không tương đương?

Giả sử một chuỗi thao tác có trạng thái:

```text
balance ban đầu = 100
giao dịch 1: trừ 60
giao dịch 2: trừ 60 nếu còn đủ
```

Nếu xử lý đúng thứ tự:

1. Giao dịch 1 thành công, balance còn 40.
2. Giao dịch 2 thất bại do không đủ tiền.

Không thể thay bằng `SUM(-60-60)` rồi chỉ kiểm tra balance cuối mà mặc định mọi nghiệp vụ đều giống nhau. Nó có thể bỏ qua điều kiện “kiểm tra ở mỗi bước”, thứ tự và kết quả chấp nhận từng giao dịch.

### 23.1. Vòng lặp phù hợp khi mỗi bước thay đổi điều kiện của bước sau

Các ví dụ:

- Tính số dư tuần tự với quy tắc chặn âm ở mỗi giao dịch.
- Thuật toán giải đồ thị có trạng thái khó biểu diễn an toàn bằng SQL.
- Gọi một function phụ thuộc vào kết quả lần gọi trước.
- Tiến trình workflow với I/O ngoài database, retry riêng cho từng bước.

### 23.2. Vẫn cân nhắc window/recursive CTE trước

Nếu chỉ cần **phân tích** tổng lũy kế và đánh dấu những điểm vượt ngưỡng, window functions có thể đủ:

```sql
WITH payments AS (
    SELECT 1 AS seq, -60 AS delta
    UNION ALL
    SELECT 2 AS seq, -60 AS delta
)
SELECT
    seq,
    delta,
    100 + SUM(delta) OVER (
        ORDER BY seq
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS hypothetical_balance
FROM payments
ORDER BY seq;
```

Kết quả hypothetical balances 40 và -20. Nó giúp **phát hiện vấn đề**, nhưng **không tự thực hiện chính xác nghiệp vụ chấp nhận/từ chối giao dịch thứ hai và điều chỉnh các bước sau**. Khi có quyết định phụ thuộc trạng thái đã chấp nhận, cần thiết kế thuật toán riêng.

### 23.3. Recursive CTE cho dạng đệ quy có quy tắc rõ

```sql
WITH RECURSIVE sequence(n) AS (
    VALUES (1)
    UNION ALL
    SELECT n + 1
    FROM sequence
    WHERE n < 7
)
SELECT n
FROM sequence
ORDER BY n;
```

Đây là ví dụ số đơn giản; `generate_series(1,7)` dễ hơn. Với cấu trúc cây, quan hệ cha-con và một số bước lặp dữ liệu, recursive CTE có thể thay vòng lặp thủ tục.

Tuy nhiên recursion cần điều kiện kết thúc, tránh vòng lặp vô hạn và kiểm soát độ lớn tập trung gian; không ép một workflow I/O/transaction nhiều bước vào một recursive CTE chỉ để tránh keyword LOOP.

## 24. Tối ưu cho dữ liệu lớn: index và thống kê vẫn cần

Set-based SQL chỉ là một mô hình mô tả dữ liệu. Muốn chạy nhanh, PostgreSQL vẫn cần access path phù hợp:

```sql
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending'
  AND ordered_at < DATE '2026-11-10';
```

Nếu bảng có 500 triệu hàng và chỉ 0,1% rows pending, một index phù hợp có thể giảm phạm vi đọc:

```sql
CREATE INDEX idx_orders_pending_date
ON set_lab.orders (ordered_at, order_id)
WHERE status = 'pending';
```

Index partial chỉ chứa rows pending, có thể hữu ích cho các query có predicate tương thích. Nhưng khi `status` chuyển khỏi pending, index cũng cần bảo trì. Không tạo index mà không đo workload.

### 24.1. Index có thể không được dùng

Với lab tám đơn, PostgreSQL có thể chọn Seq Scan ngay cả khi có index vì quét toàn bảng quá rẻ. Đừng chỉ dựa vào việc thấy Seq Scan để kết luận SQL theo tập bị chậm.

### 24.2. ANALYZE và ước lượng cardinality

```sql
ANALYZE set_lab.orders;
```

Statistics giúp planner dự báo số rows ở `WHERE` và quyết định scan/join. Sau bulk load hoặc biến động phân bố lớn, statistics cũ có thể khiến plan chưa tối ưu.

### 24.3. Composite index phải theo access pattern

Nếu hot query theo `customer_id=?` và `ordered_at`, index `(customer_id,ordered_at)` có thể phù hợp. Nhưng một `UPDATE` quét hầu hết bảng để thay trạng thái có thể không hưởng lợi từ index ấy. Thêm index để tối ưu đúng query, không chọn theo tên cột ngẫu nhiên.

### 24.4. Nhiều indexes làm tăng chi phí ghi

Mỗi INSERT/UPDATE/DELETE có thể phải duy trì index. Nếu một rewrite set-based cập nhật hàng triệu rows, chi phí index maintenance có thể chiếm phần lớn thời gian. Không chỉ tối ưu SELECT mà quên write amplification.

## 25. Đọc EXPLAIN để so sánh thay vì đoán

PostgreSQL cung cấp:

```sql
EXPLAIN
SELECT *
FROM set_lab.orders
WHERE status = 'pending';
```

`EXPLAIN` không có `ANALYZE` chỉ tạo plan ước lượng. Với `ANALYZE`, PostgreSQL thực thi câu SQL và trả số liệu thực.

### 25.1. Benchmark UPDATE an toàn trên lab

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';

ROLLBACK;
```

**Quan trọng:** `EXPLAIN (ANALYZE) UPDATE` thực sự cập nhật rows khi chạy. `ROLLBACK` trong lab chỉ để hoàn tác thay đổi sau khi đo. Không chạy phép đo ghi trên production nếu chưa có kế hoạch.

### 25.2. Đo loop bằng clock_timestamp

```sql
BEGIN;

DO $$
DECLARE
    v_started timestamptz := clock_timestamp();
    r record;
BEGIN
    FOR r IN
        SELECT order_id
        FROM set_lab.orders
        WHERE status = 'pending'
    LOOP
        UPDATE set_lab.orders
        SET discount = 5.00
        WHERE order_id = r.order_id;
    END LOOP;

    RAISE NOTICE 'Loop elapsed ms: %',
        1000 * EXTRACT(
            EPOCH FROM clock_timestamp() - v_started
        );
END;
$$;

ROLLBACK;
```

Đây là thời gian nội bộ mẫu; số liệu trên tám rows không nói nhiều về hiệu năng. Nếu muốn so sánh có ý nghĩa, tạo dataset đủ lớn trong một lab riêng và đo nhiều lần với cùng điều kiện/index/transaction.

### 25.3. Những chỉ số cần xem

| Chỉ số | Ý nghĩa khi tối ưu set-based |
| --- | --- |
| Actual rows / loops | Có quét/cập nhật bao nhiêu rows thực tế? |
| Buffers hit/read | Có nhiều page accesses và đọc đĩa không? |
| Planning Time | Chi phí lập plan của SQL lớn. |
| Execution Time | Thời gian thực thi statement trong lần đo. |
| Sort/Hash memory/disk | Có spill ra temp disk không? |
| Rows Removed by Filter | Predicate có chọn lọc như mong đợi không? |
| Trigger time | Row trigger có chiếm phần lớn chi phí DML không? |
| WAL/disk metrics ngoài plan | Có tác động write load/replication lớn không? |

`EXPLAIN (ANALYZE, BUFFERS)` hiển thị một phần các thông số nói trên tùy query và PostgreSQL major; số liệu WAL có thể yêu cầu tùy chọn `WAL`/công cụ đo tương ứng, không được coi cột WAL luôn tự xuất hiện.

### 25.4. So sánh phải công bằng

Để so:

1. Loop và set-based làm **cùng công việc nghiệp vụ**.
2. Dữ liệu, indexes và điều kiện phân bố giống nhau.
3. Có đủ số rows để thấy overhead.
4. Cả hai được chạy từ trạng thái tương đương, mỗi lần rollback/reset phù hợp.
5. Đo nhiều lần để giảm nhiễu cache/CPU/I/O.
6. Xem cả lock contention và WAL chứ không chỉ time một lần.

Không lấy loop thực hiện 100 rows so với SQL cập nhật 1 triệu rows rồi kết luận hướng nào nhanh hơn.

## 26. PL/pgSQL RETURN NEXT so với RETURN QUERY

Một PL/pgSQL function trả một tập hàng có thể dùng vòng lặp:

```sql
CREATE OR REPLACE FUNCTION
    set_lab.list_paid_orders_loop()
RETURNS TABLE (
    order_id bigint,
    customer_id integer,
    amount numeric
)
LANGUAGE plpgsql
AS $$
DECLARE
    r record;
BEGIN
    FOR r IN
        SELECT
            o.order_id, o.customer_id, o.amount
        FROM set_lab.orders AS o
        WHERE o.status = 'paid'
    LOOP
        order_id := r.order_id;
        customer_id := r.customer_id;
        amount := r.amount;
        RETURN NEXT;
    END LOOP;
END;
$$;
```

Nếu không có xử lý per-row thực sự cần thiết, dùng `RETURN QUERY`:

```sql
CREATE OR REPLACE FUNCTION
    set_lab.list_paid_orders_set()
RETURNS TABLE (
    order_id bigint,
    customer_id integer,
    amount numeric
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        o.order_id, o.customer_id, o.amount
    FROM set_lab.orders AS o
    WHERE o.status = 'paid';
END;
$$;
```

Thử:

```sql
SELECT *
FROM set_lab.list_paid_orders_set()
ORDER BY customer_id, order_id;
```

### 26.1. Lợi ích

`RETURN QUERY` cho phép viết kết quả như một SQL query, không phải chuyển từng tuple vào các biến output rồi gọi `RETURN NEXT` lặp đi lặp lại.

### 26.2. Trả kết quả không bảo đảm streaming row-by-row

Các hàm PL/pgSQL trả tập bằng `RETURN NEXT` hoặc `RETURN QUERY` hiện có cơ chế **tích lũy tập kết quả**; với tập rất lớn, có thể dùng bộ nhớ và disk theo `work_mem`, không nên mặc định chúng streaming row cho client ngay khi gọi `RETURN NEXT`.

Nếu chỉ cần trả SELECT và không cần PL/pgSQL, một **SQL function** hoặc query/view trực tiếp có thể đơn giản và giúp planner tối ưu theo các quy tắc phù hợp:

```sql
CREATE OR REPLACE FUNCTION
    set_lab.list_paid_orders_sql()
RETURNS TABLE (
    order_id bigint,
    customer_id integer,
    amount numeric
)
LANGUAGE sql
STABLE
AS $$
    SELECT o.order_id, o.customer_id, o.amount
    FROM set_lab.orders AS o
    WHERE o.status = 'paid';
$$;
```

Không gắn nhãn `IMMUTABLE` cho function đọc bảng có dữ liệu thay đổi: tính ổn định theo transaction/statement và cơ chế volatility phải được khai báo đúng.

## 27. PL/pgSQL SELECT INTO, PERFORM và số lượt gọi SQL

Trong PL/pgSQL:

```sql
SELECT COUNT(*)
INTO v_count
FROM set_lab.orders
WHERE status = 'paid';
```

là một câu SQL trả scalar vào biến PL/pgSQL — hoàn toàn hợp lý. Set-based không nghĩa cấm `SELECT INTO` hay `PERFORM`.

### 27.1. Chỉ nên nghi ngờ khi đặt trong loop không cần thiết

Đoạn:

```sql
FOR r IN SELECT customer_id FROM set_lab.customers LOOP
    SELECT COUNT(*)
    INTO v_count
    FROM set_lab.orders
    WHERE customer_id = r.customer_id;
END LOOP;
```

có thể làm một aggregation/lookup cho mỗi khách. Nếu chỉ cần counts cho tất cả khách, `GROUP BY` hoặc `LEFT JOIN + FILTER` rõ hơn.

### 27.2. GET DIAGNOSTICS ROW_COUNT

Sau một SQL UPDATE/DELETE, PL/pgSQL có thể lấy số rows bị lệnh xử lý mà không duyệt `RETURNING` từng hàng:

```sql
DO $$
DECLARE
    v_affected bigint;
BEGIN
    UPDATE set_lab.orders
    SET discount = 5.00
    WHERE status = 'pending';

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    RAISE NOTICE 'Rows processed by UPDATE: %',
        v_affected;
END;
$$;
```

Đây là ví dụ có thay đổi dữ liệu; nếu muốn chỉ thử mà không lưu:

```sql
BEGIN;

DO $$
DECLARE
    v_affected bigint;
BEGIN
    UPDATE set_lab.orders
    SET discount = 5.00
    WHERE status = 'pending';

    GET DIAGNOSTICS v_affected = ROW_COUNT;
    RAISE NOTICE 'Affected rows: %', v_affected;
END;
$$;

ROLLBACK;
```

`ROW_COUNT` đếm số rows được lệnh SQL xử lý theo semantics của command; không nên suy ra chắc chắn mọi giá trị cột đã thay đổi vật lý hay mọi trigger đều không can thiệp.

### 27.3. FOUND

`FOUND` là biến đặc biệt trong PL/pgSQL, có thể cho biết một câu lệnh nhất định vừa ảnh hưởng/trả ít nhất một row tùy loại command. Với yêu cầu biết **chính xác số rows**, dùng `GET DIAGNOSTICS ... ROW_COUNT` sau lệnh thích hợp rõ hơn.

### 27.4. PERFORM không cứu một N+1 query

`PERFORM some_function(...)` gọi biểu thức/SELECT rồi bỏ kết quả trong PL/pgSQL. Nó không tự biến các lần gọi trong vòng lặp thành một lần thực thi theo tập. Nếu function có side effects, phải xem từng lần gọi có cần thiết hay không.

## 28. Đổi từng lời gọi SQL từ Java/JDBC thành một tập thao tác

Không chỉ PL/pgSQL mới có vấn đề RBAR. Java có thể tạo vòng lặp ở application:

```java
for (Long orderId : orderIds) {
    // Mỗi lượt gọi database một lần:
    jdbcTemplate.update(
        "UPDATE set_lab.orders " +
        "SET discount = 5 WHERE order_id = ?",
        orderId
    );
}
```

Mẫu này có thể tạo N round trips từ application tới PostgreSQL, thêm latency mạng/connection overhead ngoài số SQL statements.

### 28.1. Nếu cùng điều kiện nghiệp vụ, chuyển thành UPDATE theo tập

```sql
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';
```

Không phải gửi một danh sách hàng từ Java nếu PostgreSQL có thể xác định tập đó bằng predicate. Việc lọc nên thực hiện gần dữ liệu, tận dụng SQL planner và indexes.

### 28.2. Nếu ứng dụng đã có một tập ID

Một truy vấn parameterized:

```sql
UPDATE set_lab.orders
SET discount = 5.00
WHERE order_id = ANY($1::bigint[]);
```

Tập ID có thể được bind thành PostgreSQL array. Trên Java JDBC:

```java
import java.sql.Array;
import java.sql.Connection;
import java.sql.PreparedStatement;

Long[] ids = {1L, 3L, 8L};

try (Connection conn = dataSource.getConnection()) {
    Array idArray = conn.createArrayOf("int8", ids);

    try (PreparedStatement ps = conn.prepareStatement(
        "UPDATE set_lab.orders " +
        "SET discount = 5.00 " +
        "WHERE order_id = ANY(?::bigint[])"
    )) {
        ps.setArray(1, idArray);
        ps.executeUpdate();
    } finally {
        idArray.free();
    }
}
```

Ví dụ giả định `dataSource` hợp lệ, driver PostgreSQL hỗ trợ binding type `int8`; xử lý exception/transaction ở tầng service. Trong thực tế nên thêm điều kiện tenant/authorization và kiểm tra các order IDs được phép cập nhật.

### 28.3. JDBC batch khác SQL set-based

`PreparedStatement.addBatch()`/`executeBatch()` có thể giảm round trips và tăng hiệu quả truyền lệnh; nhưng nó vẫn biểu diễn nhiều parameter sets cho một câu SQL DML được thực thi nhiều lần, **không hoàn toàn tương đương một UPDATE ... WHERE hoặc INSERT ... SELECT**.

Đây là lựa chọn tốt nếu mỗi row có giá trị khác nhau và khó mô tả bằng SQL quan hệ, nhưng nếu tất cả rows có thể được xử lý bằng một predicate, set-based SQL có thể rõ hơn.

### 28.4. Temporary table cho một tập ID lớn

Với hàng triệu IDs, thay vì truyền một mảng khổng lồ:

```sql
CREATE TEMP TABLE tmp_order_ids (
    order_id bigint PRIMARY KEY
) ON COMMIT DROP;

-- Ứng dụng bulk load ID vào tmp_order_ids
-- bằng COPY hoặc kỹ thuật thích hợp.

UPDATE set_lab.orders AS o
SET discount = 5.00
FROM tmp_order_ids AS x
WHERE o.order_id = x.order_id;
```

Ví dụ trên là **khung thao tác**, không chạy nguyên mẫu mà bỏ bước load vì lúc đó bảng tạm rỗng; cũng phải chú ý `ON COMMIT DROP` sẽ xóa bảng tạm khi transaction COMMIT, nên client cần lập transaction bao trùm tạo/load/update.

Nếu dữ liệu staging lớn, `ANALYZE tmp_order_ids` có thể giúp planner và index trên key join phù hợp.

### 28.5. N+1 SELECT của ORM

Một ứng dụng tải danh sách customers rồi truy vấn orders cho từng customer có thể có N+1 problem. Đôi khi giải pháp là `JOIN`, projection hoặc batch fetching ở ORM; không nhất thiết phải viết PL/pgSQL function. Mục tiêu là giảm những truy vấn không cần thiết và tối ưu **tập dữ liệu được chuyển qua network**.

### 28.6. Không tạo chuỗi SQL từ IDs tùy tiện

Sai:

```java
// Không nên nối input không tin cậy vào SQL:
String sql =
    "SELECT * FROM set_lab.orders WHERE order_id IN (" +
    untrustedIds + ")";
```

Nên dùng bind parameters, PostgreSQL array, staging table hoặc query builder parameterized, không hy sinh SQL injection safety để đạt số lượt gọi ít hơn.

## 29. Set-based có thể giữ logic điều kiện nhiều cột

**Yêu cầu:** pending discount 0, paid discount theo tier, cancelled discount 0. Viết theo tập:

```sql
BEGIN;

UPDATE set_lab.orders AS o
SET discount =
    CASE
        WHEN o.status = 'paid' THEN
            round(
                o.amount
                * CASE c.tier
                    WHEN 'gold' THEN 0.10
                    WHEN 'silver' THEN 0.05
                    ELSE 0
                  END,
                2
            )
        ELSE 0
    END
FROM set_lab.customers AS c
WHERE c.customer_id = o.customer_id
RETURNING o.order_id, o.status, o.amount, o.discount;

ROLLBACK;
```

Tất cả rows được xem xét trong một UPDATE. Tuy nhiên một update “đặt lại cùng giá trị” vẫn có thể tạo row version/triggers theo cách PostgreSQL UPDATE hoạt động. Nếu chỉ muốn thay những rows có giá trị thực sự khác, thêm predicate phù hợp.

### 29.1. Tránh UPDATE không cần thiết bằng IS DISTINCT FROM

Ví dụ chỉ cập nhật pending rows nếu discount không phải 5:

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending'
  AND discount IS DISTINCT FROM 5.00;

ROLLBACK;
```

`IS DISTINCT FROM` xử lý SQL NULL khác với `<>`, cho boolean xác định. Trong schema lab discount `NOT NULL`, `<>` cũng đủ cho trường hợp cụ thể, nhưng pattern NULL-safe hữu ích khi cột nullable.

### 29.2. Không giả định SET expressions chạy tuần tự

Một câu:

```sql
-- Ví dụ ý tưởng:
-- UPDATE t SET a = a + 1, b = a * 2;
```

không nên được hiểu như Java:

```java
a = a + 1;
b = a * 2; // a mới
```

Trong PostgreSQL, biểu thức `SET` tham chiếu giá trị của row nguồn theo ngữ nghĩa UPDATE, không thực thi lần lượt từ trái sang phải như phép gán tuần tự trong Java. Nếu `b` cần giá trị `a` mới, hãy viết biểu thức của giá trị mới một cách rõ ràng hoặc tổ chức subquery phù hợp.

### 29.3. Vì sao không nên nhét ngoại lệ vào một CASE quá dài?

Khi rule có hàng trăm nhánh và mỗi nhánh thay đổi theo cấu hình, một bảng quy tắc có primary key/range constraints và JOIN có thể dễ hiểu, dễ test hơn. Set-based chú trọng **mô hình quan hệ**, không cổ vũ biểu thức không thể bảo trì.

## 30. Idempotency và uniqueness khi xử lý theo tập

Một job định kỳ có thể chạy lại sau crash. Cần biết nếu chạy hai lần thì dữ liệu có thay đổi sai không.

### 30.1. Lệnh set giá trị cố định

```sql
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';
```

Chạy hai lần cho kết quả giá trị cột discount giống nhau (bỏ qua các side effects như triggers, updated_at, WAL). Đây có tính idempotent ở **giá trị cuối** của cột.

### 30.2. Lệnh cộng dồn không tự idempotent

```sql
UPDATE set_lab.orders
SET discount = discount + 5.00
WHERE status = 'pending';
```

Chạy hai lần tạo discount tăng thêm 10 thay vì 5. Cùng là một SQL statement set-based, nhưng nghiệp vụ không idempotent.

### 30.3. INSERT ... SELECT có thể ghi trùng

Nếu job tạo audit notes chạy lại, có thể tạo duplicate events. Với một bảng event có `UNIQUE(order_id, event_type)` phù hợp, có thể dùng:

```sql
-- Mẫu minh họa trên bảng có constraint tương ứng:
-- INSERT INTO order_events(order_id, event_type)
-- SELECT order_id, 'paid'
-- FROM orders WHERE status='paid'
-- ON CONFLICT (order_id,event_type) DO NOTHING;
```

Không thêm `ON CONFLICT DO NOTHING` chỉ để che lỗi uniqueness bất ngờ; conflict target phải phản ánh rule nghiệp vụ.

### 30.4. Idempotency và đồng thời

Hai workers cùng chạy một job set-based có thể cạnh tranh trên cùng target, chờ row locks hoặc tạo lỗi duplicate depending constraints. Dùng uniqueness, transaction isolation, advisory locks/worker coordination hoặc hàng đợi có trạng thái rõ. Không thay loop bằng một query rồi giả định concurrency đã được xử lý.

## 31. Bảo mật và multi-tenant trong SQL set-based

Một nguy cơ khi gom nhiều thao tác là **quên predicate tenant_id**. Thay vì chỉ một hàng bị cập nhật nhầm, một UPDATE thiếu điều kiện có thể tác động mọi tenant.

Ví dụ cần cập nhật đơn pending của tenant:

```sql
-- Schema lab dùng customer_id như một khóa phân nhóm,
-- không phải tenant_id production:
UPDATE set_lab.orders
SET discount = 5.00
WHERE customer_id = 1
  AND status = 'pending';
```

Khi áp dụng mô hình multi-tenant thật:

- Thêm tenant scope từ identity đã được xác thực.
- Dùng bind parameter, không nối input trực tiếp.
- Áp Row Level Security đúng yêu cầu nếu có.
- Có giới hạn quyền cho role chạy batch.
- Dùng `RETURNING`/ROW_COUNT/audit để quan sát số rows ảnh hưởng.
- Với destructive statements, có thể chạy SELECT COUNT(*) bằng cùng filter trước khi được phép thực thi.

Đừng dùng “set-based” làm lý do bỏ authorization check hoặc chạy mọi batch dưới superuser.

## 32. Query plan tốt vẫn quan trọng hơn cú pháp “ngắn”

Một SQL có vẻ set-based nhưng không có index hoặc viết JOIN sai có thể chậm hơn một batch loop được thiết kế tốt.

### 32.1. Correlated subquery có thể được tối ưu — hoặc không

```sql
SELECT
    c.customer_id,
    (
        SELECT COUNT(*)
        FROM set_lab.orders AS o
        WHERE o.customer_id = c.customer_id
    ) AS total_orders
FROM set_lab.customers AS c;
```

Đây chỉ là một SQL statement, nhưng có thể chứa **correlated subplan** được thực thi nhiều lần. PostgreSQL có thể chọn kế hoạch phù hợp, song không được suy ra mọi “một SQL statement” đều hiệu quả hơn JOIN + GROUP BY.

Một dạng tương đương:

```sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS total_orders
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Nên dùng `EXPLAIN` trên dataset đại diện để chọn phương án, không chỉ đếm số dòng SQL.

### 32.2. Cẩn thận Cartesian product

Nếu quên điều kiện JOIN:

```sql
-- Sai vì tạo tích Descartes nếu không có ON phù hợp:
-- SELECT * FROM customers CROSS JOIN orders;
```

Một query set-based có thể nhân số rows cực lớn và dẫn đến UPDATE duplicate matches/sai totals. Rõ khóa JOIN, cardinality và kết quả expected là điều kiện tiên quyết.

### 32.3. Không biến mọi SQL thành một CTE khổng lồ

Nhiều CTE phức tạp không được dùng chỉ vì chúng trông “theo tập”. Nếu business process có các checkpoint, lỗi độc lập, retries và external side effects, nhiều SQL statements **mỗi statement xử lý một tập** có thể rõ và an toàn hơn một câu SQL khổng lồ.

## 33. Tư duy chọn giải pháp: bảng quyết định

| Yêu cầu | Ưu tiên thử trước | Khi LOOP có thể hợp lý |
| --- | --- | --- |
| UPDATE mọi row thỏa predicate | Một `UPDATE ... WHERE`. | Mỗi row cần tương tác ngoài DB hoặc phải ghi nhận lỗi độc lập. |
| UPDATE từ bảng mapping | `UPDATE ... FROM` trên khóa duy nhất. | Logic chuỗi bước phụ thuộc kết quả các vòng trước. |
| INSERT nhiều rows từ dữ liệu SQL | `INSERT ... SELECT`. | Mỗi row có tác dụng ngoài transaction không thể gom. |
| Tổng hợp theo khách hàng/ngày | `GROUP BY` + `FILTER`. | Cần algorithm trạng thái khó biểu diễn bằng aggregate. |
| Top-N mỗi nhóm | `DISTINCT ON`, `ROW_NUMBER`, `LATERAL`. | Mỗi nhóm cần workflow riêng không gói trong SQL. |
| Running total | `SUM(...) OVER (...)`. | Có điều kiện chấp nhận giao dịch phụ thuộc từng bước. |
| Nạp JSON array | `jsonb_to_recordset`, `jsonb_array_elements`. | Dữ liệu cần validation bằng service ngoài DB từng phần tử. |
| Sinh lịch/ngày/số | `generate_series`. | Sinh chuỗi phụ thuộc trạng thái ngoài SQL. |
| Chuyển quan hệ theo IDs | `JOIN`, `ANY`, `UNNEST`, temp table. | Gọi API khác cho từng ID hoặc orchestration có retries. |
| Xóa row theo quan hệ | `DELETE ... USING/EXISTS`. | Xóa phải theo từng đơn vị audit/approval độc lập. |
| Duy trì tổng hợp theo PK | `INSERT ... SELECT ON CONFLICT`. | Không có key đủ rõ hoặc cần điều phối transaction phức tạp. |
| Cập nhật hàng trăm triệu rows | Nhiều batch set-based nhỏ. | LOOP cấp batch, không LOOP mỗi row. |
| Import có lỗi vài rows | Staging, classify, insert valid rows. | Bắt exception từng row nếu thực sự không thể validate trước. |
| Mỗi row cần logic trigger | Cân nhắc statement trigger/transition table. | BEFORE ROW trigger có ý nghĩa riêng cần thiết. |

### 33.1. Bốn câu hỏi trước khi viết LOOP

1. **Có phải quyết định áp dụng cho mọi row chỉ phụ thuộc dữ liệu đang có trong bảng không?** Nếu có, thường diễn đạt bằng `WHERE`/`CASE`/`JOIN`.
2. **Có cần giá trị của hàng trước để quyết định xử lý hàng sau không?** Nếu chỉ cần running total/previous row, thử window functions. Nếu có workflow state thật, có thể cần thủ tục.
3. **Có cần từng lỗi/commit độc lập không?** Nếu có, cân nhắc staging và batch; đôi khi xử lý từng đơn vị vẫn phù hợp.
4. **Có tác dụng ngoài DB hoặc semantics trigger/ordering không?** Không được xóa bỏ side effects chỉ để SQL ngắn hơn.

## 34. Case study A: tính hoa hồng cho hàng triệu đơn

**Bối cảnh:** hệ thống có 5 triệu đơn paid, mỗi khách thuộc một tier, cần tính lại discount/commission cho toàn bộ kỳ.

### 34.1. Thiết kế vòng lặp

Một `FOR r IN SELECT orders JOIN customers LOOP UPDATE orders ...` phải phát một UPDATE theo mỗi order. Nếu dữ liệu lớn, số statements phát ra là rất nhiều, thời gian khóa/SQL executor lặp đáng kể.

### 34.2. Thiết kế set-based

```sql
UPDATE set_lab.orders AS o
SET discount = round(
    o.amount *
        CASE c.tier
            WHEN 'gold' THEN 0.10
            WHEN 'silver' THEN 0.05
            ELSE 0
        END,
    2
)
FROM set_lab.customers AS c
WHERE c.customer_id = o.customer_id
  AND o.status = 'paid';
```

### 34.3. Cần đánh giá

- `customers.customer_id` có unique/PK không? Nếu không, UPDATE FROM có thể không xác định.
- Tier thay đổi theo thời gian hay dùng tier hiện tại để tính lại kỳ cũ?
- Có `BEFORE/AFTER UPDATE` triggers không?
- Hệ thống cần snapshot bảng tier theo thời điểm nào?
- Tác động hàng triệu rows có thể batch theo ngày/ID không?
- Có index phù hợp với paid/ordered_at và FK join không?

### 34.4. Kết luận

Set-based là giải pháp trực tiếp ở mức thuật toán. Nhưng nếu số rows quá lớn, dùng nhiều batch set-based và quy trình versioning/transaction phù hợp thay vì một transaction khổng lồ.

## 35. Case study B: đồng bộ số liệu theo khách

**Bối cảnh:** mỗi giờ hệ thống tính total_paid và paid_orders cho tất cả khách để API đọc nhanh.

### 35.1. Tránh loop qua từng khách

Không dùng 100.000 `SELECT SUM` độc lập rồi 100.000 UPSERT nếu một `GROUP BY` đã cho toàn bộ số liệu.

### 35.2. Một câu UPSERT theo tập

```sql
INSERT INTO set_lab.customer_totals AS t (
    customer_id, total_paid, paid_orders
)
SELECT
    c.customer_id,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ), 0
    ),
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    )
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ON CONFLICT (customer_id)
DO UPDATE SET
    total_paid = EXCLUDED.total_paid,
    paid_orders = EXCLUDED.paid_orders,
    calculated_at = clock_timestamp();
```

### 35.3. Giới hạn

- Đây là rebuild aggregate từ dữ liệu nguồn, **không phải incremental update** theo từng đơn.
- Khách đã bị xóa khỏi source customers có thể cần cleanup tùy FK/cascade.
- Nếu có nhiều dòng dữ liệu từ JOIN không đúng key, SUM sai dù SQL chạy nhanh.
- Hai jobs chạy đồng thời có thể tranh locks, cần scheduling/idempotency.

## 36. Case study C: import 200.000 bản ghi nhưng 2% sai định dạng

**Bối cảnh:** người dùng tải file CSV, cần xử lý các rows hợp lệ, ghi lỗi của rows không hợp lệ.

### 36.1. Cách naive

Đọc từng CSV row trong PL/pgSQL, `BEGIN ... EXCEPTION` per row rồi INSERT. Có thể xử lý được nhưng số statement/subtransaction lớn.

### 36.2. Cách theo tập

```text
COPY -> staging raw text
        |
        v
SQL validation (format/key/range/duplicates)
        |
        +--> invalid rows -> error table
        |
        v
valid rows -> INSERT ... SELECT / ON CONFLICT
        |
        v
batch result counts + audit
```

Validation SQL có thể dùng typed columns, `CASE`, `JOIN` vào reference tables và uniqueness constraints. Với các row errors không dự đoán được, vẫn có thể cần cơ chế riêng để cô lập lỗi nhưng không mặc định exception per row trước khi thử staging.

### 36.3. Kết luận

Đa số import nghiệp vụ thường có thể tận dụng xử lý theo **cả file hoặc một batch lớn**, đồng thời giữ báo cáo chi tiết rows lỗi. Đảm bảo dữ liệu không hợp lệ không lách qua bằng việc coi lỗi NULL/0 hoặc bỏ kiểm tra business key.

## 37. Case study D: nhiều worker nhận việc từ hàng đợi

**Bối cảnh:** hàng đợi `work_queue` có 100.000 jobs, mười workers xử lý đồng thời, mỗi worker cần claim tối đa 100 rows.

### 37.1. Không SELECT rồi UPDATE từng row mà không khóa

Nếu worker A và B cùng SELECT các ID `status='ready'` trước khi UPDATE, họ có thể chọn trùng work items. Điều này là race condition, không chỉ vấn đề hiệu năng.

### 37.2. Mẫu claim theo tập

```sql
-- Pseudocode trên bảng work_queue có PK(id):
WITH claimed AS (
    SELECT id
    FROM work_queue
    WHERE status = 'ready'
    ORDER BY id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE work_queue AS w
SET status = 'processing'
FROM claimed AS c
WHERE w.id = c.id
RETURNING w.id;
```

Mẫu trên làm việc claim trong một statement, tránh cửa sổ SELECT không khóa → UPDATE có cạnh tranh.

### 37.3. Xử lý tiếp theo ngoài transaction

Claim ID rồi COMMIT. Worker xử lý task ở application, cập nhật success/failure với lease/timeout/retry phù hợp. Nếu một worker crash sau claim, phải có cơ chế reclaim. `SKIP LOCKED` không tự cung cấp exactly-once delivery, job timeout hoặc idempotency.

### 37.4. Kết luận

Khi có concurrency, set-based có thể phối hợp row locks để xử lý **một batch nhiều hàng**. Vẫn cần hiểu queue semantics và sự thiếu công bằng/không đầy đủ của SKIP LOCKED.

## 38. Case study E: cập nhật từng bước có ràng buộc thứ tự

**Bối cảnh:** giao dịch tài chính được áp dụng theo thứ tự thời gian, kiểm tra số dư trước từng lần thanh toán, có thể từ chối một bước nhưng chấp nhận bước trước.

### 38.1. Có nên thay bằng SUM tất cả delta?

Không nếu business rule phụ thuộc intermediate balances/acceptance. Một phép SUM có thể che việc một lệnh phải bị từ chối.

### 38.2. Chọn công cụ thích hợp

Có thể dùng:

- Transactional function/procedure với row locks và logic trạng thái có thứ tự.
- Recursive CTE chỉ khi semantics đã được chứng minh rõ và an toàn cho workload.
- SQL transaction riêng cho từng bước được điều phối theo thứ tự đúng.
- Data structures/ledger chuyên biệt nếu hệ thống yêu cầu audit/consistency chặt.

### 38.3. Kết luận

**Mục tiêu không phải xóa mọi vòng lặp bằng mọi giá.** Mục tiêu là giữ tính đúng đắn, giảm overhead nơi công việc thực sự mang tính tập hợp.

## 39. Case study F: cập nhật dữ liệu lịch sử không gây gián đoạn

**Bối cảnh:** cập nhật một cột ước lượng cho 30 triệu records trong giờ có nhiều giao dịch.

### 39.1. Một UPDATE lớn có thể gây vấn đề

Một câu UPDATE toàn bộ 30 triệu records có thể tạo transaction kéo dài, WAL và bloat, gây contention với các tác vụ khác.

### 39.2. Phương án tốt hơn

- Xác định predicate, range và khóa chính phù hợp.
- Chạy nhiều batch `UPDATE ... FROM batch`, mỗi batch là một câu SQL set-based.
- Mỗi batch commit riêng do orchestrator/procedure trong ngữ cảnh hợp lệ.
- Monitor elapsed time, locks, WAL và replication lag.
- Dùng `WHERE old_value IS DISTINCT FROM new_value` để bỏ rows không cần sửa.
- Lưu checkpoint/retry logic và giới hạn throughput.

### 39.3. Kết luận

Trong bài toán này, **set-based theo batch** tối ưu hơn cả hai cực đoan: loop một UPDATE cho mỗi row và một UPDATE khổng lồ giữ locks quá lâu.

## 40. Những sai lầm thường gặp khi chuyển LOOP sang SQL

### Sai lầm 1. Đếm số câu SQL thay vì đảm bảo ngữ nghĩa

Một SQL ngắn có thể đổi quy tắc concurrency/ordering, bỏ mất audit hoặc cập nhật nhầm tenant. Hiệu năng không bù được lỗi nghiệp vụ.

### Sai lầm 2. UPDATE FROM với nhiều source rows

Một target row join nhiều rows nguồn có thể nhận một source row không xác định. Phải làm source unique theo target key trước.

### Sai lầm 3. INSERT SELECT không xử lý duplicate input

Nếu target có UNIQUE constraint và input nhiều rows cùng key, lệnh có thể lỗi; `ON CONFLICT DO UPDATE` còn có thể báo cardinality violation. Dedupe/aggregate trước.

### Sai lầm 4. LEFT JOIN rồi lọc bảng phải ở WHERE

Khi muốn giữ tất cả left rows, đặt điều kiện trên right relation không đúng vị trí có thể khiến unmatched rows bị loại. Dùng `FILTER` hoặc điều kiện JOIN phù hợp.

### Sai lầm 5. Tính SUM sai do JOIN one-to-many

Nhân bản các rows trước aggregate có thể làm doanh thu tăng giả. Tổng hợp ở cấp hạt đúng trước khi JOIN.

### Sai lầm 6. Không định nghĩa thứ tự của top-N

`LIMIT 1` không có ORDER BY/tie-breaker không xác định “mới nhất”; `DISTINCT ON` cũng cần ORDER BY phù hợp.

### Sai lầm 7. Cho rằng SQL theo tập không dùng loop bên trong

Planner/executor vẫn phải xử lý tuples. Lợi ích là mô hình truy vấn tập và cơ hội tối ưu hóa, không phải bỏ qua mọi thao tác trên hàng.

### Sai lầm 8. Cho rằng CTE luôn materialize

PostgreSQL có thể inline một số CTE; data-modifying CTE và recursive CTE có semantics khác. Dùng EXPLAIN, đừng đoán.

### Sai lầm 9. Đọc RETURNING theo thứ tự ngẫu nhiên

`RETURNING` không bảo đảm thứ tự theo ý nghiệp vụ. Nếu cần có thứ tự khi trình bày, truy vấn/sắp kết quả trong lớp thích hợp.

### Sai lầm 10. Bỏ qua row-level triggers

Một UPDATE cho 100.000 hàng vẫn có thể kích hoạt 100.000 row triggers. Đo trigger time và cân nhắc transition tables nếu phù hợp.

### Sai lầm 11. Nhầm số statements với số transactions

Một vòng lặp PL/pgSQL chạy trong một transaction không tự COMMIT mỗi row. Chuyển sang UPDATE duy nhất thay số statements nhưng không xóa bản chất transaction.

### Sai lầm 12. Dùng EXPLAIN ANALYZE UPDATE mà không hiểu có side effects

`EXPLAIN (ANALYZE)` thực thi UPDATE thật. Trong lab, bọc transaction rồi ROLLBACK; trên production cần kế hoạch riêng.

### Sai lầm 13. Dùng một transaction khổng lồ

Gom 100 triệu rows vào một UPDATE không tự thành tối ưu. WAL, locks, rollback và autovacuum có thể khiến chia batch tốt hơn.

### Sai lầm 14. Dùng OFFSET để phân batch dataset đang thay đổi

Các rows được update/xóa giữa những lần đọc có thể làm OFFSET bỏ qua hoặc lặp rows. Dùng khóa ổn định/remaining predicate và cơ chế claim phù hợp.

### Sai lầm 15. SKIP LOCKED như một query báo cáo

SKIP LOCKED cố tình bỏ hàng đang bị khóa, không cung cấp một snapshot đầy đủ cho báo cáo cần tính chính xác.

### Sai lầm 16. Dùng WHERE NOT IN khi input có NULL mà không xét logic SQL

`NOT IN` và SQL NULL có thể tạo UNKNOWN làm kết quả khác mong đợi. Với anti-join, `NOT EXISTS` thường dễ kiểm soát hơn khi input nullable, kèm keys và constraints rõ.

### Sai lầm 17. Giả định batch UPDATE tự idempotent

`SET amount = amount + x` lặp hai lần sẽ cộng hai lần. Cần job ID/checkpoint, constraint hoặc thiết kế SET giá trị tính từ source ổn định.

### Sai lầm 18. Nối dữ liệu vào SQL text để truyền danh sách IDs

Dynamic string dễ gây SQL injection, lỗi quoting và plan inefficiency. Dùng parameters, arrays hoặc temp table.

### Sai lầm 19. Xử lý exception từng hàng nhưng không báo lỗi

Một loop có `EXCEPTION WHEN OTHERS THEN NULL` có thể âm thầm bỏ qua dữ liệu lỗi. Staging + classification/audit thường tốt hơn; không swallow errors vô điều kiện.

### Sai lầm 20. Bỏ qua plan và statistics

Một câu SQL theo tập với filter/join không index và ước lượng lệch có thể vẫn chạy lâu. Tối ưu set-based cần EXPLAIN, ANALYZE và thiết kế indexes.

### Sai lầm 21. Dùng function VOLATILE với giả định một lần gọi

Một biểu thức function có side effects trong SELECT/UPDATE có thể được gọi cho nhiều rows, không tự biến thành một lần gọi cho cả tập. Phải hiểu volatility và semantics của function.

### Sai lầm 22. Đồng nhất SQL function và PL/pgSQL RETURN QUERY

Chúng có cơ chế planner/result handling khác nhau; khi chỉ cần SELECT, SQL function hoặc query/view có thể đơn giản hơn. Dùng PL/pgSQL khi cần điều khiển thủ tục thật.

### Sai lầm 23. Quên kiểm tra quyền và tenant

Một UPDATE thiếu predicate scope có thể sửa mọi khách hàng. Luôn gắn authorization/tenant filter phù hợp và giám sát row count.

### Sai lầm 24. Giả định JDBC batch giống một UPDATE theo tập

JDBC batch giảm round trips nhưng thường vẫn thực thi nhiều parameter sets. Một `UPDATE ... WHERE ...` hoặc `INSERT ... SELECT` là mô hình khác; chọn theo thực tế.

### Sai lầm 25. Coi vòng lặp là luôn sai

Các thuật toán có trạng thái, transaction boundaries và external side effects đôi khi cần loop. Điều cần tránh là **lặp statement trên từng hàng khi SQL đã mô tả được tập một cách rõ ràng và đúng nghĩa**.

## 41. MERGE: một lựa chọn set-based khác cho đồng bộ

Từ PostgreSQL 15, lệnh `MERGE` cho phép mô tả hành động khi source row **khớp** hoặc **không khớp** target theo điều kiện join, hỗ trợ một số dạng cập nhật/chèn/xóa có điều kiện tùy major.

### 41.1. Ví dụ MERGE vào bảng tổng hợp

```sql
BEGIN;

MERGE INTO set_lab.customer_totals AS t
USING (
    SELECT
        customer_id,
        SUM(amount) AS revenue,
        COUNT(*) AS paid_orders
    FROM set_lab.orders
    WHERE status = 'paid'
    GROUP BY customer_id
) AS s
ON t.customer_id = s.customer_id
WHEN MATCHED THEN
    UPDATE SET
        total_paid = s.revenue,
        paid_orders = s.paid_orders,
        calculated_at = clock_timestamp()
WHEN NOT MATCHED THEN
    INSERT (
        customer_id,
        total_paid,
        paid_orders
    )
    VALUES (
        s.customer_id,
        s.revenue,
        s.paid_orders
    );

SELECT *
FROM set_lab.customer_totals
ORDER BY customer_id;

ROLLBACK;
```

### 41.2. Vì sao MERGE chưa phải thay thế mọi UPSERT?

- `MERGE` và `INSERT ... ON CONFLICT` có **quy tắc concurrency và xử lý xung đột khác nhau**. Đừng giả định MERGE tự động retry khi một transaction khác chèn trùng unique key giữa lúc xét source/target; tình huống có thể báo lỗi unique.
- Nếu một target row match nhiều source rows, có thể phát sinh cardinality violation hoặc hành vi không mong đợi. Cần chuẩn bị source theo khóa duy nhất.
- `MERGE` không tự giải quyết nhóm cũ biến mất khỏi source; phải thiết kế chính sách delete/zero riêng.
- `MERGE` là tính năng từ PostgreSQL 15, không thể đưa vào môi trường major cũ mà không kiểm tra hỗ trợ.

### 41.3. Khi nào MERGE phù hợp?

Khi quy trình đồng bộ cần nhiều nhánh matched/not matched trong một statement và ngữ nghĩa concurrency đã được đánh giá. Với tình huống atomic insert-or-update theo unique conflict, `INSERT ... ON CONFLICT` vẫn thường là lựa chọn quen thuộc và có cơ chế phù hợp riêng.

Không viết một vòng lặp `IF EXISTS THEN UPDATE ELSE INSERT` khi chỉ cần một UPSERT/MERGE có khóa và yêu cầu rõ.

## 42. Bài tập thực hành

Các bài sử dụng bảng `set_lab.customers`, `set_lab.orders`, `set_lab.customer_totals` và `set_lab.audit_notes` trong phần 3. Khi đề có DML ghi dữ liệu, hãy thử trong **transaction lab** rồi `ROLLBACK` để không làm thay đổi bộ dữ liệu cho bài sau. Những bảng giả định như `work_queue` được ghi chú là pseudocode, không phải object đã được tạo trong schema mẫu.

### Bài 1. Nhận diện RBAR

Giải thích vì sao vòng lặp `FOR r IN SELECT order_id ... LOOP UPDATE ... WHERE order_id=r.order_id` thường có overhead cao hơn một UPDATE với `WHERE` tương đương.

### Bài 2. Chuyển UPDATE từng hàng

Viết một câu SQL đặt `discount=7.50` cho mọi đơn pending, dùng `RETURNING` để biết các đơn đã được xử lý.

### Bài 3. CASE theo hạng khách hàng

Viết UPDATE tính discount cho các đơn paid: gold 10%, silver 5%, bronze 0%, làm tròn 2 chữ số thập phân.

### Bài 4. Kết quả cụ thể

Với bộ dữ liệu lab, tổng discount của năm đơn paid khi áp tỷ lệ ở Bài 3 bằng bao nhiêu?

### Bài 5. INSERT ... SELECT

Viết một câu chèn audit note `'Đã thanh toán'` cho mọi đơn paid, không dùng loop.

### Bài 6. Vì sao job không idempotent?

Nếu job ở Bài 5 chạy hai lần và bảng audit không có uniqueness business phù hợp, điều gì có thể xảy ra?

### Bài 7. Tổng hợp theo khách hàng

Viết SELECT tính total_paid và paid_orders cho từng khách có ít nhất một đơn paid.

### Bài 8. Bao gồm cả khách không có paid orders

Viết query trả **mọi khách** và doanh thu paid, kể cả khách không có paid orders thì trả 0.

### Bài 9. FILTER

Trong một query, tính số đơn paid và pending theo từng khách hàng.

### Bài 10. UPSERT theo tập

Viết INSERT SELECT ON CONFLICT cập nhật `customer_totals` từ các đơn paid theo customer_id.

### Bài 11. Nhóm không còn dữ liệu

Sau khi toàn bộ paid orders của một khách bị cancelled, UPSERT chỉ dựa `orders WHERE status='paid' GROUP BY customer_id` có tự cập nhật total về 0 không?

### Bài 12. UNIQUE conflict input

Tại sao một `INSERT ... ON CONFLICT DO UPDATE` dùng source hai rows cùng customer_id có thể lỗi? Nêu cách xử lý trước.

### Bài 13. DELETE USING

Viết DELETE các audit notes thuộc những đơn cancelled bằng JOIN với orders.

### Bài 14. UPDATE FROM không duy nhất

Một target row `customer_totals(customer_id=1)` match hai đơn paid của khách 1. Vì sao `SET total_paid=o.amount FROM orders o` là sai nếu muốn tổng?

### Bài 15. Tập nguồn unique

Viết subquery dùng `GROUP BY` sinh đúng một row source/customer_id để dùng trong UPDATE FROM.

### Bài 16. Tổng lũy kế

Viết SELECT cho mỗi đơn paid kèm tổng amount lũy kế trong khách hàng đó theo `ordered_at,order_id`.

### Bài 17. Hàng trước

Viết query dùng `LAG` lấy số tiền của đơn paid trước trong mỗi khách hàng.

### Bài 18. Đơn gần nhất mỗi khách

Viết query PostgreSQL `DISTINCT ON` lấy đơn mới nhất của mỗi khách, giải quyết trường hợp cùng ngày.

### Bài 19. ROW_NUMBER

Viết query lấy **hai đơn mới nhất mỗi khách** bằng window function.

### Bài 20. LATERAL

Viết query trả một dòng cho mọi khách cùng ID đơn mới nhất nếu tồn tại; nếu khách chưa có đơn, vẫn giữ khách.

### Bài 21. generate_series

Sinh các ngày từ 01/11 đến 07/11/2026 bằng SQL, không dùng WHILE.

### Bài 22. ARRAY membership

Lấy tất cả đơn của các khách có ID trong `ARRAY[1,2,4]` không dùng vòng lặp.

### Bài 23. UNNEST và duplicate IDs

`unnest(ARRAY[1,1,2]) JOIN customers` và `WHERE customer_id=ANY(ARRAY[1,1,2])` có thể khác nhau như thế nào về số rows kết quả?

### Bài 24. JSON recordset

Chuyển `'[{"sku":"A","qty":2},{"sku":"B","qty":1}]'::jsonb` thành hai rows có cột `sku text, qty integer`.

### Bài 25. Data-modifying CTE

Viết một statement UPDATE discount cho đơn pending rồi INSERT audit notes chỉ cho đúng những rows vừa UPDATE, sử dụng `RETURNING`.

### Bài 26. CTE materialization

Có đúng là mọi CTE trong PostgreSQL luôn tạo bảng vật lý tạm trước khi parent query chạy không? Vì sao?

### Bài 27. READ COMMITTED và snapshot

Vì sao nhiều UPDATE statements bên trong loop có thể khác một UPDATE statement về khả năng quan sát commit của transaction khác?

### Bài 28. Locks và WAL

Một UPDATE set-based 10 triệu rows có tránh được row locks/MVCC/WAL/autovacuum không? Khi nào nên batch?

### Bài 29. Batch claim

Viết mẫu CTE chọn tối đa 100 rows pending có `ORDER BY order_id FOR UPDATE SKIP LOCKED` rồi UPDATE discount trong một statement.

### Bài 30. OFFSET trong batch

Vì sao dùng OFFSET 0, OFFSET 100, OFFSET 200 khi mỗi batch thay đổi predicate WHERE có thể bỏ qua rows?

### Bài 31. PROCEDURE và COMMIT

Có được dùng COMMIT tùy ý trong PL/pgSQL function không? Vì sao một procedure `CALL` trong transaction do Java/Spring mở sẵn có thể không COMMIT bên trong như mong đợi?

### Bài 32. EXCEPTION per row

Một import có 2% rows sai định dạng. Đề xuất quy trình set-based giúp xử lý rows hợp lệ và lưu rows lỗi thay vì exception block cho từng row.

### Bài 33. Trigger per row

Một UPDATE theo tập tác động 50.000 rows có row-level AFTER UPDATE trigger. Trigger chạy bao nhiêu lần và có cách thiết kế statement-level cho một số nghiệp vụ không?

### Bài 34. EXPLAIN ANALYZE UPDATE

Điều gì xảy ra khi dùng `EXPLAIN (ANALYZE, BUFFERS) UPDATE ...`? Viết cách thử an toàn trong lab.

### Bài 35. JDBC batch

`PreparedStatement.executeBatch()` có giống một SQL `UPDATE ... WHERE ...` theo tập không? Khi đã có tập IDs từ Java, nên cân nhắc những lựa chọn nào?

### Bài 36. RETURN QUERY

Trong function PL/pgSQL trả nhiều rows, khi nào `RETURN QUERY SELECT ...` có thể dễ hiểu hơn vòng lặp `RETURN NEXT`? Nó có streaming row-by-row chắc chắn không?

### Bài 37. Idempotency

So sánh chạy hai lần `SET discount=5` và `SET discount=discount+5`.

### Bài 38. Thuật toán có trạng thái

Số dư ban đầu 100, hai giao dịch trừ 60 lần lượt nếu còn đủ. Vì sao chỉ lấy SUM(-120) không tương đương xử lý từng giao dịch theo thứ tự?

### Bài 39. MERGE

Từ PostgreSQL major nào có MERGE? Vì sao MERGE không thể mặc nhiên được coi là giống hệt `INSERT ... ON CONFLICT` về concurrency?

### Bài 40. Chọn phương án

Một bảng có 30 triệu rows cần cập nhật vào giờ cao điểm, trong đó chỉ 3 triệu rows thỏa điều kiện. Chọn vòng lặp từng row, một UPDATE duy nhất, hay nhiều batch set-based; cần đo những tiêu chí gì?

## 43. Gợi ý lời giải

### Đáp án 1. RBAR

Vòng lặp duyệt một tập order IDs rồi thực hiện một UPDATE cho mỗi ID. Dù PL/pgSQL có plan caching, N SQL statements có thêm số lượt gọi executor, tìm row/khóa/index lặp lại. Một UPDATE có WHERE mô tả tập target trực tiếp, giúp PostgreSQL tối ưu scan và thực hiện trong một statement. Với dữ liệu nhỏ, chênh lệch có thể không đáng kể; cần benchmark.

### Đáp án 2. UPDATE pending

```sql
BEGIN;

UPDATE set_lab.orders
SET discount = 7.50
WHERE status = 'pending'
RETURNING order_id, amount, discount;

ROLLBACK;
```

Trong lab ban đầu, lệnh xử lý hai đơn pending. RETURNING không tự bảo đảm thứ tự.

### Đáp án 3. CASE và JOIN

```sql
BEGIN;

UPDATE set_lab.orders AS o
SET discount = round(
    o.amount *
        CASE c.tier
            WHEN 'gold' THEN 0.10
            WHEN 'silver' THEN 0.05
            ELSE 0
        END,
    2
)
FROM set_lab.customers AS c
WHERE o.customer_id = c.customer_id
  AND o.status = 'paid';

ROLLBACK;
```

`customers.customer_id` là PRIMARY KEY, mỗi order có tối đa một customer row tương ứng.

### Đáp án 4. Tổng discount

Các khoản 10, 8, 10, 0 và 15; tổng là **43.00**. Số liệu chỉ đúng với dataset ban đầu và không có các lần thử UPDATE/INSERT đã COMMIT ngoài ý muốn.

### Đáp án 5. INSERT SELECT

```sql
BEGIN;

INSERT INTO set_lab.audit_notes (order_id, note)
SELECT order_id, 'Đã thanh toán'
FROM set_lab.orders
WHERE status = 'paid'
RETURNING audit_id, order_id, note;

ROLLBACK;
```

Sinh năm audit rows trên dữ liệu mẫu.

### Đáp án 6. INSERT trùng

Mỗi lần chạy có thể thêm năm audit notes, nên sau hai lần có 10 notes tương đương. Muốn idempotent theo nghiệp vụ cần một identity/unique constraint thích hợp và chính sách conflict, không chỉ đổi loop thành một SQL statement.

### Đáp án 7. GROUP BY

```sql
SELECT
    customer_id,
    SUM(amount) AS total_paid,
    COUNT(*) AS paid_orders
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
ORDER BY customer_id;
```

Kết quả customer 1→180/2; 2→200/1; 3→40/1; 4→150/1.

### Đáp án 8. LEFT JOIN và FILTER

```sql
SELECT
    c.customer_id,
    COALESCE(
        SUM(o.amount) FILTER (
            WHERE o.status = 'paid'
        ), 0
    ) AS total_paid,
    COUNT(o.order_id) FILTER (
        WHERE o.status = 'paid'
    ) AS paid_orders
FROM set_lab.customers AS c
LEFT JOIN set_lab.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Những khách không có paid orders vẫn hiện với 0/0. `COUNT(o.order_id)` không đếm row đệm NULL của LEFT JOIN.

### Đáp án 9. Nhiều aggregates trong một SELECT

```sql
SELECT
    customer_id,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'pending'
    ) AS pending_orders
FROM set_lab.orders
GROUP BY customer_id
ORDER BY customer_id;
```

Không cần đếm paid riêng, đếm pending riêng trong vòng lặp per customer.

### Đáp án 10. UPSERT theo tập

```sql
BEGIN;

INSERT INTO set_lab.customer_totals AS t (
    customer_id, total_paid, paid_orders
)
SELECT
    customer_id,
    SUM(amount),
    COUNT(*)
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id
ON CONFLICT (customer_id)
DO UPDATE SET
    total_paid = EXCLUDED.total_paid,
    paid_orders = EXCLUDED.paid_orders,
    calculated_at = clock_timestamp();

ROLLBACK;
```

Đầu vào đã GROUP BY nên tối đa một row/conflict key. Nếu cần mọi khách kể cả chưa có paid orders, xem đáp án tiếp theo.

### Đáp án 11. Nhóm biến mất

Không. Nếu không có paid orders cho một customer, nguồn SELECT `WHERE status='paid'` không sinh row customer ấy; UPSERT không cập nhật row cũ về 0. Cách xử lý: xây source từ tất cả `customers LEFT JOIN orders` với `FILTER` và `COALESCE`, hoặc một bước riêng cập nhật/cleanup cho các nhóm bị mất tùy contract.

### Đáp án 12. Duplicate conflict keys

`INSERT ... ON CONFLICT DO UPDATE` có thể cố ảnh hưởng một existing target row nhiều lần trong cùng command và báo lỗi cardinality. Dùng `GROUP BY key`, `DISTINCT ON` với thứ tự xác định, hoặc staging UNIQUE key/validation để đảm bảo **một row nguồn mỗi conflict key**.

### Đáp án 13. DELETE USING

```sql
BEGIN;

DELETE FROM set_lab.audit_notes AS a
USING set_lab.orders AS o
WHERE a.order_id = o.order_id
  AND o.status = 'cancelled'
RETURNING a.audit_id, a.order_id;

ROLLBACK;
```

Không có audit notes trong lab mới thì DELETE 0 rows.

### Đáp án 14. Source không duy nhất

Khách 1 có hai paid orders 100 và 80. `UPDATE customer_totals SET total_paid=o.amount FROM orders o` sẽ không tự tổng 180; một target row có thể match nhiều source rows, và không bảo đảm được row nguồn nào cung cấp giá trị. Cần aggregate trước thành `SUM(amount)` theo customer_id.

### Đáp án 15. GROUP BY unique

```sql
SELECT
    customer_id,
    SUM(amount) AS total_paid,
    COUNT(*) AS paid_orders
FROM set_lab.orders
WHERE status = 'paid'
GROUP BY customer_id;
```

Đây là source có tối đa một row/customer_id cho UPDATE FROM; nhóm không tồn tại cần xử lý riêng.

### Đáp án 16. Window running total

```sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    SUM(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND CURRENT ROW
    ) AS running_total
FROM set_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at, order_id;
```

Khách 1 có hai running totals 100 và 180. Tie-breaker order_id giúp thứ tự xác định nếu cùng ordered_at.

### Đáp án 17. LAG

```sql
SELECT
    customer_id,
    order_id,
    amount,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_paid_amount
FROM set_lab.orders
WHERE status = 'paid'
ORDER BY customer_id, ordered_at, order_id;
```

Đơn đầu của mỗi khách có `previous_paid_amount` là SQL NULL vì không có hàng trước.

### Đáp án 18. DISTINCT ON

```sql
SELECT DISTINCT ON (customer_id)
    customer_id,
    order_id,
    ordered_at,
    status
FROM set_lab.orders
ORDER BY
    customer_id,
    ordered_at DESC,
    order_id DESC;
```

`DISTINCT ON` giữ row đầu tiên của mỗi customer group theo ORDER BY. `order_id DESC` xử lý khi hai đơn cùng ngày.

### Đáp án 19. Top 2 theo nhóm

```sql
WITH ranked AS (
    SELECT
        customer_id,
        order_id,
        ordered_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM set_lab.orders
)
SELECT customer_id, order_id, ordered_at
FROM ranked
WHERE rn <= 2
ORDER BY customer_id, rn;
```

Không cần một SELECT LIMIT 2 riêng cho mỗi customer.

### Đáp án 20. LEFT JOIN LATERAL

```sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.ordered_at
FROM set_lab.customers AS c
LEFT JOIN LATERAL (
    SELECT order_id, ordered_at
    FROM set_lab.orders
    WHERE customer_id = c.customer_id
    ORDER BY ordered_at DESC, order_id DESC
    LIMIT 1
) AS o ON TRUE
ORDER BY c.customer_id;
```

`LEFT JOIN LATERAL` giữ khách không có đơn và cho phép subquery tham chiếu customer_id phía ngoài. Nó vẫn có thể thực hiện lookups theo từng customer ở tầng execution plan, nhưng không cần vòng lặp PL/pgSQL.

### Đáp án 21. generate_series

```sql
SELECT x.day_ts::date AS day
FROM generate_series(
    TIMESTAMP '2026-11-01',
    TIMESTAMP '2026-11-07',
    INTERVAL '1 day'
) AS x(day_ts)
ORDER BY day;
```

Trả bảy ngày liên tiếp, bao gồm hai đầu mút. Không cần tăng biến `date` trong WHILE.

### Đáp án 22. ANY

```sql
SELECT order_id, customer_id, status, amount
FROM set_lab.orders
WHERE customer_id =
    ANY(ARRAY[1,2,4]::integer[])
ORDER BY customer_id, order_id;
```

Nếu danh sách đến từ Java/JDBC, nên bind parameter thay vì nối chuỗi SQL.

### Đáp án 23. UNNEST và duplicates

`UNNEST(ARRAY[1,1,2])` trả ba rows, gồm ID 1 hai lần; khi JOIN vào customers, khách 1 có thể xuất hiện hai lần. Predicate `customer_id=ANY(ARRAY[1,1,2])` trả kết quả membership (TRUE/FALSE/UNKNOWN theo SQL), không nhân bản customer row vì input array có ID trùng.

Nếu muốn một relation IDs duy nhất từ UNNEST:

```sql
SELECT DISTINCT customer_id
FROM unnest(ARRAY[1,1,2]::integer[])
    AS ids(customer_id);
```

### Đáp án 24. JSON recordset

```sql
SELECT sku, qty
FROM jsonb_to_recordset(
    '[{"sku":"A","qty":2},{"sku":"B","qty":1}]'::jsonb
) AS x(sku text, qty integer);
```

Kết quả hai rows A/2 và B/1; schema contract cần validate đủ trường và kiểu khi dữ liệu từ client.

### Đáp án 25. CTE UPDATE RETURNING

```sql
BEGIN;

WITH changed AS (
    UPDATE set_lab.orders
    SET discount = 5.00
    WHERE status = 'pending'
    RETURNING order_id, discount
)
INSERT INTO set_lab.audit_notes(order_id, note)
SELECT
    order_id,
    'Discount set to ' || discount::text
FROM changed;

ROLLBACK;
```

`RETURNING` cung cấp những rows UPDATE xử lý, không cần `SELECT` riêng từng order ID. Chỉ khi nghiệp vụ muốn audit đúng giá trị thực sự đổi mới cần thêm predicate `IS DISTINCT FROM` vào UPDATE.

### Đáp án 26. CTE không luôn materialize

Sai. PostgreSQL hiện đại có thể inline/fold các CTE không-recursive, side-effect-free trong những trường hợp phù hợp; `MATERIALIZED`/`NOT MATERIALIZED` ảnh hưởng một số lựa chọn. Data-modifying CTE và recursive CTE có semantics riêng. Dùng EXPLAIN để thấy plan.

### Đáp án 27. READ COMMITTED

Ở READ COMMITTED, nhiều SQL commands liên tiếp có thể lấy snapshots khác nhau; transaction khác có thể COMMIT giữa các lần lặp. Một UPDATE đơn lẻ làm việc trong ngữ nghĩa snapshot/locking của một command. Vì vậy rewrite cần xem concurrency requirements, không chỉ cùng WHERE.

### Đáp án 28. UPDATE lớn

Không. DML vẫn có row locks, MVCC versions, WAL, index maintenance và ảnh hưởng vacuum. Khi số rows lớn và transaction giữ locks quá lâu hoặc tăng WAL/replication lag, có thể chia nhiều batches set-based với mỗi batch commit có kiểm soát.

### Đáp án 29. CTE batch claim

```sql
BEGIN;

WITH batch AS (
    SELECT order_id
    FROM set_lab.orders
    WHERE status = 'pending'
      AND discount = 0
    ORDER BY order_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE set_lab.orders AS o
SET discount = 5.00
FROM batch AS b
WHERE b.order_id = o.order_id
RETURNING o.order_id, o.discount;

ROLLBACK;
```

Đây là một statement cập nhật tối đa 100 rows được claim, không phải 100 UPDATE. Với dataset ban đầu, chỉ có hai đơn pending. Những row bị SKIP LOCKED cần cơ chế retry.

### Đáp án 30. OFFSET không ổn khi tập thay đổi

Sau batch đầu, những rows `discount=0` chuyển thành 5 sẽ không còn trong WHERE của batch sau. Nếu vẫn OFFSET 100, bạn có thể **bỏ qua 100 rows tiếp theo** trong tập đã thu hẹp. Hãy liên tục chọn `LIMIT N` trên điều kiện remaining hoặc dùng keyset/checkpoint với khóa ổn định.

### Đáp án 31. Function vs procedure COMMIT

PL/pgSQL function không thể tùy ý COMMIT. Procedure qua CALL hoặc DO có transaction control trong ngữ cảnh phù hợp, nhưng nếu đã nằm bên trong một transaction block tường minh do Spring/JDBC mở, COMMIT nội bộ có thể bị PostgreSQL từ chối. Cần tách orchestration transaction hoặc thiết kế procedure theo đúng hạn chế của major/call stack.

### Đáp án 32. Import với dữ liệu lỗi

Một quy trình:

```text
CSV -> staging raw text
    -> SQL validate (regex, NULL, key, range, references)
    -> INSERT invalid rows vào error table
    -> INSERT valid rows vào target
    -> ghi batch counts
```

Nếu chọn cast trong SQL, phải đảm bảo dữ liệu hợp lệ trước/qua CASE guards, tránh một giá trị lỗi làm hỏng toàn statement. `EXCEPTION` per row chỉ nên dùng khi logic lỗi thực sự không thể dự đoán/validate theo tập.

### Đáp án 33. Row trigger và statement trigger

Một row-level AFTER UPDATE trigger có thể được gọi **50.000 lần** khi UPDATE 50.000 rows. Một AFTER STATEMENT trigger có thể dùng transition tables để đọc tập old/new rows và ghi audit bằng một `INSERT ... SELECT` trong các trường hợp được hỗ trợ. Nhưng không chuyển đổi mù quáng vì timing/semantics của BEFORE ROW triggers khác.

### Đáp án 34. EXPLAIN ANALYZE UPDATE

Nó **thực sự chạy UPDATE**. Thử an toàn trên lab:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE set_lab.orders
SET discount = 5.00
WHERE status = 'pending';

ROLLBACK;
```

Không dùng trên production nếu chưa được phép thực thi write. `EXPLAIN` không có `ANALYZE` chỉ lập plan.

### Đáp án 35. JDBC batch và set-based

Không hoàn toàn giống. JDBC batch gửi nhiều parameter sets có thể giảm round trips nhưng database thường vẫn xử lý nhiều statement executions. Khi có IDs từ Java:

- Dùng `WHERE id = ANY($1::bigint[])` cho một tập vừa phải.
- Dùng `UNNEST`/JOIN nếu cần transform input theo relation.
- Dùng temp/staging table + bulk load cho tập rất lớn.
- Nếu điều kiện chọn có sẵn trong DB, dùng một UPDATE WHERE trực tiếp.

Cần bind parameters an toàn và đo hiệu năng.

### Đáp án 36. RETURN QUERY

Nếu function chỉ muốn trả kết quả SELECT và không cần xử lý per-row, `RETURN QUERY SELECT ...` rõ hơn `FOR r ... RETURN NEXT`. Nó **không bảo đảm streaming row-by-row** ngay khi gọi RETURN QUERY; PL/pgSQL set-returning functions có cơ chế tích lũy kết quả, với tập lớn có thể tốn memory/disk.

### Đáp án 37. Idempotency

`SET discount=5` chạy hai lần vẫn để giá trị discount=5 (chưa tính triggers/audit metadata khác). `SET discount=discount+5` chạy hai lần làm tăng tổng 10, không idempotent. Cần job identity, deduplication hoặc nguồn giá trị ổn định nếu retry.

### Đáp án 38. Thuật toán có thứ tự

Theo rule mỗi giao dịch chỉ chấp nhận khi đủ số dư: giao dịch trừ 60 đầu thành công, số dư còn 40; giao dịch thứ hai bị từ chối. `SUM(-120)` cho ra -20, không biểu diễn kết quả xử lý tuần tự có nhánh accept/reject. Cần thủ tục hoặc thuật toán set-based được chứng minh tương đương với state transitions.

### Đáp án 39. MERGE

PostgreSQL có `MERGE` từ **major 15**. Nó cho phép các nhánh matched/not matched nhưng concurrency semantics khác `INSERT ... ON CONFLICT`: chẳng hạn khi transaction khác đồng thời chèn trùng key, không được mặc định MERGE sẽ xử lý conflict giống UPSERT và tự thử lại. Cần kiểm tra unique constraints và concurrency tests.

### Đáp án 40. Lựa chọn cho 3 triệu rows

Một hướng hợp lý là **nhiều batch set-based** nếu benchmark cho thấy một UPDATE lớn gây lock/WAL/replication contention quá mức; với khối lượng vừa và maintenance window có thể chọn một UPDATE duy nhất. Loop từng row thường là phương án kém hấp dẫn nếu công thức cập nhật chung và không cần transaction per-row.

Đo: rows/batch, elapsed time, p95 latency giao dịch khác, row lock waits, disk/I/O, WAL, replication lag, bloat/autovacuum, index maintenance, error/rollback footprint và khả năng restart.

## 44. Checklist chuyển đổi PL/pgSQL vòng lặp sang SQL theo tập

Trước khi đổi code thủ tục thành câu SQL, hãy xác nhận đầy đủ các yếu tố sau.

### 44.1. Tính đúng đắn nghiệp vụ

1. **Mục tiêu:** một tập rows thỏa điều kiện hay một chuỗi bước có trạng thái?
2. **Phạm vi:** predicate WHERE/tenant/authorization có đủ chặt không?
3. **Đầu vào:** source có thể có NULL/duplicate keys không?
4. **Join cardinality:** mỗi target row có đúng một source row không?
5. **Aggregation grain:** SUM/COUNT có tính trên đúng đơn vị nghiệp vụ không?
6. **Missing groups:** nếu nhóm không có rows, cần giữ ở 0, giữ giá trị cũ hay xóa?
7. **Ordering:** có logic “hàng đầu/cuối/đầu tiên” cần tie-breaker không?
8. **SQL type:** `numeric`, rounding, date/timezone và NULL semantics có đúng không?
9. **Idempotency:** job có thể chạy lại sau lỗi mà không nhân giá trị/ghi trùng không?
10. **Audit:** row-level/statement-level triggers và external side effects có thay đổi không?

### 44.2. Transaction và concurrency

11. Một statement hay nhiều statements có snapshots khác nhau trong READ COMMITTED?
12. Có cần `SELECT FOR UPDATE` để khóa đối tượng trước khi quyết định không?
13. Có writers cạnh tranh trên cùng rows không?
14. Isolation level có đủ bảo vệ invariant không?
15. Có nguy cơ deadlock và phải retry transaction theo SQLSTATE phù hợp không?
16. Có workflow trước đây commit hoặc bắt lỗi từng row, nay thay đổi atomicity không?
17. Có constraint/triggers khiến một row lỗi làm cả statement thất bại không?
18. Nếu có `SKIP LOCKED`, job có đảm bảo quét lại các rows bị skip không?

### 44.3. Hiệu năng và vận hành

19. Có indexes phù hợp với filter/join/sort không?
20. Planner statistics có đại diện cho dữ liệu thật không?
21. Có đo `EXPLAIN (ANALYZE, BUFFERS)` trên dataset tương đương không?
22. Có xem số rows thực, loops, buffers và trigger time không?
23. Có cần chia batch để hạn chế transaction duration/WAL không?
24. Có đo ảnh hưởng reader/writer latency, replication lag và bloat không?
25. Có benchmark trên nhiều runs thay vì một lần với tám rows mẫu không?
26. Có rollback/checkpoint/retry plan khi job dừng giữa chừng không?

### 44.4. Kiến trúc và bảo trì

27. Có thể dùng `INSERT ... SELECT`/`UPDATE ... FROM`/`DELETE USING` thay vòng lặp không?
28. Có thể dùng `GROUP BY`, `FILTER`, `WINDOW`, `DISTINCT ON` hoặc `LATERAL` không?
29. Với input arrays/JSON, có dùng `UNNEST`/`jsonb_to_recordset` được không?
30. Với multi-step SQL, CTE/`RETURNING` có diễn đạt luồng dữ liệu rõ không?
31. Với batch, vòng lặp ở mức batch hay vẫn duyệt từng row?
32. Có cần SQL function/view thay cho PL/pgSQL chỉ để trả SELECT không?
33. Nếu dùng MERGE, PostgreSQL major và concurrency semantics đã được đánh giá chưa?
34. Source có được bind parameters an toàn từ JDBC/ORM thay vì SQL text nối chuỗi không?
35. Code mới có dễ test và dễ hiểu hơn code cũ không?
36. Nếu chọn giữ LOOP, có lý do nghiệp vụ/transaction cụ thể được ghi rõ không?

## 45. Tổng kết

**Xử lý theo tập là tư duy mặc định phù hợp với dữ liệu quan hệ.** Khi bài toán là “mọi hàng thỏa một điều kiện phải được biến đổi theo cùng một quy tắc”, hãy thử biểu diễn trực tiếp bằng SQL thay vì phát một SQL statement cho từng row trong PL/pgSQL.

Các mẫu quan trọng:

- **`UPDATE ... WHERE`** thay vòng lặp UPDATE từng khóa.
- **`UPDATE ... FROM`** khi cần giá trị từ bảng mapping; bảo đảm source key không nhân target rows.
- **`INSERT ... SELECT`** để chèn dữ liệu từ query; thiết kế idempotency nếu job có thể chạy lại.
- **`DELETE ... USING`** hoặc **`DELETE ... WHERE EXISTS`** thay loop xóa theo quan hệ.
- **`GROUP BY`, `FILTER`** thay vòng lặp cộng/đếm theo nhóm.
- **`WINDOW functions`** như `SUM OVER`, `LAG`, `ROW_NUMBER` thay nhiều vòng lặp tính thứ tự/lũy kế.
- **`DISTINCT ON` hoặc `LATERAL`** cho bài toán lấy hàng mới nhất/top-N theo nhóm.
- **`generate_series`, `UNNEST`, `jsonb_to_recordset`** biến lịch/array/JSON thành dữ liệu quan hệ để xử lý bằng SQL.
- **CTE và `RETURNING`** giúp nối các tập kết quả trung gian, tránh SELECT rồi xử lý lại từng hàng.
- **`ON CONFLICT` và `MERGE`** xử lý những dạng đồng bộ nhiều khóa, nhưng phải hiểu uniqueness và concurrency.

Những giới hạn cũng quan trọng:

- Set-based **không miễn** MVCC, row locks, WAL, trigger hoặc constraint.
- Một UPDATE lớn có thể cần **batch set-based** thay vì transaction khổng lồ.
- `UPDATE ... FROM` không được dùng nguồn một-nhiều rồi kỳ vọng chọn một row nhất định.
- Query SQL một statement **không tự chắc nhanh**; planner, indexes, statistics và JOIN cardinality vẫn quyết định.
- Chuyển từ loop có exception từng hàng sang một SQL có thể đổi **cách xử lý lỗi**.
- Các thuật toán có trạng thái và phụ thuộc thứ tự đôi khi **phải dùng vòng lặp/procedure** hoặc giải pháp transactional chuyên biệt.
- `EXPLAIN (ANALYZE)` trên DML **thực thi DML**, nên phải kiểm soát trên lab.
- Code Java/JDBC có thể gặp cùng vấn đề N+1; JDBC batching và SQL set-based là hai mức tối ưu khác nhau.

Nguyên tắc dễ nhớ:

> **Hãy để PostgreSQL xử lý cả tập hàng khi quy tắc là quan hệ. Dùng PL/pgSQL để điều phối khi thật sự cần thủ tục, và nếu phải lặp thì ưu tiên lặp theo batch thay vì lặp từng row.**

Đích đến không phải có ít dòng code hay xóa tất cả keyword LOOP; đích đến là một thiết kế **đúng ngữ nghĩa, rõ ràng, có khả năng tối ưu và vận hành được dưới tải thực tế**.

## 46. Tài liệu tham khảo

Tài liệu PostgreSQL chính thức (nên chọn đúng major đang sử dụng):

- [PL/pgSQL Control Structures](https://www.postgresql.org/docs/current/plpgsql-control-structures.html): `LOOP`, `FOR`, `FOREACH`, `RETURN QUERY`, exceptions và hành vi điều khiển luồng.
- [PL/pgSQL Statements](https://www.postgresql.org/docs/current/plpgsql-statements.html): SQL trong PL/pgSQL, `SELECT INTO`, `PERFORM`, `EXECUTE` và `GET DIAGNOSTICS`.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `INSERT ... SELECT`, `ON CONFLICT`, `RETURNING`.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html): `UPDATE ... FROM`, join cardinality và `RETURNING`.
- [DELETE](https://www.postgresql.org/docs/current/sql-delete.html): `DELETE ... USING`, `RETURNING`.
- [MERGE](https://www.postgresql.org/docs/current/sql-merge.html): cú pháp và những nhánh điều kiện theo major.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): `DISTINCT ON`, `LATERAL`, `GROUP BY`, `WINDOW`.
- [Window Functions](https://www.postgresql.org/docs/current/tutorial-window.html): window definitions, `PARTITION BY` và ordering.
- [WITH Queries (Common Table Expressions)](https://www.postgresql.org/docs/current/queries-with.html): CTE, recursion, materialization và data-modifying statements.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row/table locks và sự phối hợp transactions.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshots, READ COMMITTED và concurrency semantics.
- [PL/pgSQL Transaction Management](https://www.postgresql.org/docs/current/plpgsql-transactions.html): giới hạn transaction control trong procedures và DO.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): thực thi `EXPLAIN ANALYZE` và đọc query plan.
- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): row/statement triggers và transition relations.











