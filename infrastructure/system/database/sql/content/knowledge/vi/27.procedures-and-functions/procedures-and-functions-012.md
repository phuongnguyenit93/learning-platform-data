# Thay xử lý từng hàng bằng phép toán tập hợp khi phù hợp

Trong nhiều ứng dụng, cùng một yêu cầu nghiệp vụ có thể được triển khai theo hai cách rất khác nhau:

- **Xử lý từng hàng (row-by-row):** đọc một bản ghi, tính toán, cập nhật bản ghi đó, rồi lặp lại với bản ghi tiếp theo. Cách này thường xuất hiện trong cursor, vòng lặp thủ tục, hàm PL/pgSQL/T-SQL hoặc code ứng dụng gọi SQL liên tục.
- **Xử lý theo tập hợp (set-based):** diễn tả một quy tắc áp dụng cho **tập hàng thỏa điều kiện**, rồi để hệ quản trị quan hệ lựa chọn kế hoạch JOIN, tổng hợp, sắp xếp và cập nhật phù hợp.

Ví dụ, thay vì mở cursor đi qua hàng nghìn đơn để tính lại tổng tiền, một câu `UPDATE ... FROM` kết hợp `GROUP BY` có thể tính và cập nhật hàng loạt. Thay vì gọi một `SELECT SUM(...)` cho từng khách, một lần `GROUP BY customer_id` có thể trả kết quả cho mọi khách trong phạm vi cần thiết.

Nhưng **set-based không có nghĩa mọi vòng lặp đều sai**, và **một statement không mặc nhiên chạy nhanh hơn mọi cách phân lô**. Nếu nghiệp vụ cần gọi hệ thống bên ngoài, có phụ thuộc thứ tự từng bước, yêu cầu log và xử lý lỗi độc lập theo hàng, hoặc một transaction khổng lồ sẽ giữ khóa quá lâu, một giải pháp kết hợp **set-based bên trong từng batch** và **điều phối thủ tục ở bên ngoài** có thể hợp lý hơn.

> **Nguyên tắc:** ưu tiên mô tả biến đổi dữ liệu ở cấp tập hợp khi các hàng có thể xử lý theo cùng quy tắc; giữ logic từng bước hoặc từng hàng **chỉ khi nó diễn đạt một ràng buộc thực sự**. Trước và sau khi viết lại, luôn kiểm tra cùng dữ liệu, cùng phạm vi và cùng kết quả nghiệp vụ rồi mới đánh giá execution plan.

Bài học thuộc **Database SQL → Thủ tục và hàm**. Phần chính minh họa với **PostgreSQL** và dữ liệu tự chứa; phần sau đối chiếu SQL Server, MySQL, Oracle và SQLite, bàn về cursor, stored procedure, UDF, window function, transaction, đồng thời và các trường hợp không nên gộp mọi thao tác thành một lệnh duy nhất.

## 1. Vì sao xử lý từng hàng thường xuất hiện?

Một lập trình viên quen cách viết ngôn ngữ mệnh lệnh có thể bắt đầu từ:

```text
for each order in orders:
    items = SELECT lines for that order
    gross = sum(items.quantity * items.price)
    discount = lookup customer tier
    net = round(gross * (1 - discount), 2)
    UPDATE order with net
```

Thao tác trên dễ đọc theo nghĩa “một đơn một lần”, nhưng có thể phát sinh:

1. Một lần đọc danh sách đơn.
2. **N lần** đọc chi tiết đơn.
3. Có thể **N lần** đọc khách/chiết khấu.
4. **N lần** UPDATE đơn.
5. Hàng trăm hoặc hàng nghìn lần truyền tham số, gọi hàm, mở cursor, chuyển ngữ cảnh giữa tầng thủ tục và SQL engine.

Mẫu này thường được gọi không chính thức là **RBAR — Row By Agonizing Row**. Chi phí không chỉ ở CPU xử lý từng hàng mà còn ở **round trip giữa ứng dụng và database**, số statement phải parse/execute, khóa, log, truy cập index lặp đi lặp lại và việc optimizer không thấy đầy đủ bài toán tập hợp để tối ưu hóa.

### 1.1. “Có vòng lặp” không đồng nghĩa “chắc chậm”

Một loop xử lý 10 bản ghi, mỗi bước gọi API riêng hoặc có quy tắc phê duyệt tuần tự, có thể hoàn toàn hợp lý. Một statement update 100 triệu hàng trong một transaction cũng có thể gây áp lực transaction log, lock, replication và I/O nghiêm trọng.

Vấn đề không phải đếm số từ khóa `FOR`, `WHILE`, `LOOP` hay `CURSOR`. Vấn đề là **liệu công việc ở từng hàng có thể được diễn đạt như một phép biến đổi dữ liệu chung**, để DBMS lựa chọn cách thực thi hiệu quả và giữ đúng tính nhất quán không.

### 1.2. Ba lớp cần phân biệt

| Lớp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Mô tả logic** | `UPDATE orders SET ... WHERE ...` | Quy tắc biến đổi trên tập bản ghi |
| **Thủ tục điều phối** | `FOR`, `WHILE`, cursor, service loop | Cách điều khiển từng bước |
| **Kế hoạch vật lý** | Seq Scan, Index Scan, Hash Join, Sort, Aggregate | Cách DBMS thực thi dưới bề mặt |

Một statement SQL **theo tập hợp** vẫn có thể được engine thực thi bằng nested loops hoặc xử lý từng tuple ở mức vật lý. Nó không đảm bảo CPU của máy chủ chỉ chạm vào dữ liệu một lần. Khác biệt là SQL **không ép tầng ứng dụng tự lần lượt điều khiển từng hàng** khi quy tắc có thể biểu diễn trên cả tập.

## 2. Tư duy biến đổi từ loop sang SQL tập hợp

Trước khi viết lại, hãy đặt năm câu hỏi:

1. **Tập đầu vào là gì?** Ví dụ mọi đơn PAID, chưa xử lý, thuộc khách active trong tenant 10.
2. **Mỗi hàng đầu ra biểu diễn gì?** Một hàng/đơn, một hàng/khách, hay một hàng/dòng chi tiết?
3. **Quy tắc có giống nhau cho mọi hàng không?** Ví dụ chiết khấu dựa trên tier của khách.
4. **Những hàng có cần phụ thuộc thứ tự xử lý nhau không?** Nếu không, có thể xử lý cùng một phép biến đổi.
5. **Khi có lỗi hoặc nhiều phiên đồng thời, ranh giới transaction và idempotency là gì?**

Từ đó ánh xạ:

| Logic thủ tục | Công cụ SQL tập hợp thường phù hợp |
| --- | --- |
| Lặp qua hàng để lọc | `WHERE`, `EXISTS`, `JOIN` |
| Tra cứu dữ liệu liên quan mỗi hàng | `JOIN`, CTE, subquery có kế hoạch phù hợp |
| Cộng dồn theo nhóm | `GROUP BY` và aggregate |
| Cộng có điều kiện | `SUM(CASE...)` hoặc `FILTER` theo dialect |
| Chọn hàng mới nhất mỗi nhóm | `ROW_NUMBER() OVER (...)` |
| Tính tổng tích lũy | `SUM(...) OVER (PARTITION BY ... ORDER BY ...)` |
| Cập nhật nhiều hàng theo bảng quy tắc | `UPDATE ... FROM`, `MERGE` theo DBMS |
| Tạo bản ghi từ kết quả SELECT | `INSERT INTO ... SELECT` |
| Xóa các hàng thỏa quan hệ | `DELETE ... WHERE EXISTS`/`NOT EXISTS` hoặc `DELETE USING` |
| Hợp nhất dữ liệu đến và hiện có | `UPSERT`/`MERGE` có kiểm tra khóa và conflict |
| Xử lý khối dữ liệu lớn | **Batch** theo khóa, nhưng dùng SQL tập hợp **trong mỗi batch** |

**Không áp dụng rewrite khi chưa hiểu tính tương đương**, đặc biệt với NULL, thứ tự, duplicate, LEFT JOIN, trigger, lỗi từng hàng và side effect.

## 3. Bộ dữ liệu PostgreSQL tự chứa

Ta mô phỏng một cửa hàng có khách hàng, đơn hàng và dòng chi tiết. Yêu cầu: **tính lại số tiền ròng của các đơn PAID chưa xử lý, thuộc khách active của tenant 10**.

Chạy các lệnh sau trong **cùng một session PostgreSQL**. Các bảng là `TEMP` để không cần schema production.

```sql
CREATE TEMP TABLE demo_set_customers (
    customer_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    full_name TEXT NOT NULL,
    tier TEXT NOT NULL CHECK (
        tier IN ('GOLD', 'SILVER', 'STANDARD')
    ),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    UNIQUE (tenant_id, customer_id)
);

CREATE TEMP TABLE demo_set_orders (
    order_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('PAID', 'PENDING', 'CANCELED')
    ),
    created_at TIMESTAMPTZ NOT NULL,
    net_amount NUMERIC(14, 2),
    processed_at TIMESTAMPTZ,
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES demo_set_customers (tenant_id, customer_id)
);

CREATE TEMP TABLE demo_set_order_items (
    order_id INTEGER NOT NULL
        REFERENCES demo_set_orders (order_id),
    line_no INTEGER NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);

INSERT INTO demo_set_customers
    (customer_id, tenant_id, full_name, tier, is_active)
VALUES
    (1, 10, 'An',     'GOLD',     TRUE),
    (2, 10, 'Bình',   'SILVER',   TRUE),
    (3, 10, 'Chi',    'STANDARD', TRUE),
    (4, 10, 'Dũng',   'GOLD',     FALSE),
    (5, 10, 'Hà',     'SILVER',   TRUE),
    (6, 20, 'Khách tenant khác', 'GOLD', TRUE);

INSERT INTO demo_set_orders
    (order_id, tenant_id, customer_id, status, created_at)
VALUES
    (101, 10, 1, 'PAID',     '2026-11-01 08:00:00+07'),
    (102, 10, 1, 'PENDING',  '2026-11-01 09:00:00+07'),
    (103, 10, 2, 'PAID',     '2026-11-02 08:00:00+07'),
    (104, 10, 3, 'PAID',     '2026-11-02 09:00:00+07'),
    (105, 10, 4, 'PAID',     '2026-11-03 08:00:00+07'),
    (106, 10, 5, 'PENDING',  '2026-11-03 09:00:00+07'),
    (107, 10, 5, 'PAID',     '2026-11-04 08:00:00+07'),
    (108, 20, 6, 'PAID',     '2026-11-04 09:00:00+07'),
    (109, 10, 2, 'PAID',     '2026-11-05 08:00:00+07'),
    (110, 10, 3, 'CANCELED', '2026-11-05 09:00:00+07');

INSERT INTO demo_set_order_items
    (order_id, line_no, sku, quantity, unit_price)
VALUES
    (101, 1, 'PEN', 2, 100.00),
    (101, 2, 'PAD', 1,  50.00),
    (102, 1, 'BOX', 1,  80.00),
    (103, 1, 'BOX', 2,  60.00),
    (104, 1, 'BAG', 1, 100.00),
    (104, 2, 'TAG', 2,  25.00),
    (105, 1, 'PEN', 1, 200.00),
    (107, 1, 'BOX', 1, 100.00),
    (107, 2, 'PEN', 1,  40.00),
    (108, 1, 'BAG', 1, 500.00),
    (109, 1, 'PAD', 1,  50.00),
    (110, 1, 'BOX', 1,  60.00);
```

Đơn 106 là đơn PENDING **không có dòng chi tiết**. Có hai tenant; khách 4 bị vô hiệu hóa; đơn 110 đã hủy. Chúng giúp phát hiện trường hợp UPDATE quá rộng hoặc gộp sai theo JOIN.

### 3.1. Hợp đồng tính tiền ròng

Chiết khấu:

| Tier | Tỷ lệ giảm | Hệ số sau giảm |
| --- | ---: | ---: |
| GOLD | 10% | 0.90 |
| SILVER | 5% | 0.95 |
| STANDARD | 0% | 1.00 |

Với một đơn đủ điều kiện:

```text
gross = SUM(quantity * unit_price) của các dòng chi tiết đơn
factor = 0.90/0.95/1.00 theo tier
net_amount = ROUND(gross * factor, 2)
```

Tập **đủ điều kiện** phải thỏa đồng thời:

- `o.tenant_id = 10`.
- `o.status = 'PAID'`.
- `o.processed_at IS NULL`.
- Khách của đơn `c.is_active = TRUE` và cùng tenant.
- Đơn có dòng chi tiết (trong ví dụ mẫu, mọi đơn đủ điều kiện đều có item).

Các đơn mục tiêu là **101, 103, 104, 107, 109**.

| order_id | Gross | Tier | Net kỳ vọng |
| ---: | ---: | --- | ---: |
| 101 | 250.00 | GOLD | **225.00** |
| 103 | 120.00 | SILVER | **114.00** |
| 104 | 150.00 | STANDARD | **150.00** |
| 107 | 140.00 | SILVER | **133.00** |
| 109 | 50.00 | SILVER | **47.50** |
| **Tổng** | 710.00 | | **669.50** |

Mọi ví dụ UPDATE có thể được chạy trong transaction `BEGIN ... ROLLBACK` để dữ liệu mẫu không bị thay đổi. Nếu chọn COMMIT, các điều kiện `processed_at IS NULL` sẽ khiến những đơn vừa xử lý không còn thuộc batch lần sau; điều này là mục tiêu idempotency nhưng sẽ làm kết quả của ví dụ kế tiếp thay đổi.

## 4. Cách làm từng hàng bằng vòng lặp PL/pgSQL

Đầu tiên xem một cách dễ hiểu về mặt thủ tục. Trong một vòng lặp, lấy từng đơn, đọc gross từ bảng item, áp dụng discount, rồi UPDATE đơn:

```sql
BEGIN;

DO $$
DECLARE
    r RECORD;
    v_gross NUMERIC(14, 2);
    v_factor NUMERIC(4, 2);
BEGIN
    FOR r IN
        SELECT
            o.order_id,
            c.tier
        FROM demo_set_orders AS o
        JOIN demo_set_customers AS c
          ON c.customer_id = o.customer_id
         AND c.tenant_id = o.tenant_id
        WHERE o.tenant_id = 10
          AND o.status = 'PAID'
          AND o.processed_at IS NULL
          AND c.is_active = TRUE
        ORDER BY o.order_id
    LOOP
        SELECT SUM(i.quantity * i.unit_price)
        INTO v_gross
        FROM demo_set_order_items AS i
        WHERE i.order_id = r.order_id;

        IF v_gross IS NOT NULL THEN
            v_factor := CASE r.tier
                WHEN 'GOLD' THEN 0.90
                WHEN 'SILVER' THEN 0.95
                ELSE 1.00
            END;

            UPDATE demo_set_orders
            SET net_amount = ROUND(v_gross * v_factor, 2),
                processed_at = CURRENT_TIMESTAMP
            WHERE order_id = r.order_id
              AND tenant_id = 10
              AND processed_at IS NULL;
        END IF;
    END LOOP;
END;
$$;

SELECT order_id, net_amount
FROM demo_set_orders
WHERE order_id IN (101, 103, 104, 107, 109)
ORDER BY order_id;

ROLLBACK;
```

Mã trên diễn đạt mục đích, nhưng bên trong vòng lặp có **một SELECT SUM và một UPDATE cho từng order**. Với N đơn, ít nhất sẽ có nhiều lần chuyển giữa PL/pgSQL interpreter và SQL executor. Nếu vòng lặp nằm ở ứng dụng thay vì stored procedure, còn cộng thêm **round trip qua mạng** cho từng câu SQL.

### 4.1. Vì sao vẫn cần nhìn phiên bản loop?

Chỉ khi hiểu công việc thật của vòng lặp mới thay đúng bằng set-based:

- Vòng lặp đang chọn **đơn đủ điều kiện**, không phải mọi đơn.
- Gross là **SUM theo order_id**, không phải theo customer_id.
- Chiết khấu lấy từ tier của **đúng customer thuộc cùng tenant**.
- Khi không có dòng item, loop **bỏ qua** đơn vì `v_gross IS NULL`.
- Điều kiện `processed_at IS NULL` ở UPDATE tránh ghi lại đơn đã xử lý.
- Thời điểm `CURRENT_TIMESTAMP` của PostgreSQL ổn định trong transaction; nếu nghiệp vụ dùng một hàm thời gian khác, ngữ nghĩa có thể thay đổi.

Một rewrite gộp tất cả vào một câu lệnh nhưng làm mất một điều kiện vẫn là **tối ưu sai**.

### 4.2. “Vòng lặp trong stored procedure” có thể nhanh hơn “vòng lặp trong app”

Stored procedure chạy gần dữ liệu nên giảm round trips qua mạng, nhưng nếu nó vẫn thực thi N truy vấn riêng có điều kiện giống nhau, nó vẫn có overhead từng statement, có thể bỏ lỡ cơ hội tối ưu theo nhóm. Không nên xem “đưa loop vào database” và “đổi sang phép toán tập hợp” là một việc.

## 5. Viết lại bằng GROUP BY, CASE và UPDATE ... FROM

Thay vì đọc item từng đơn, ta tính gross cho **mọi order** bằng một phép GROUP BY; sau đó JOIN với customer để biết discount, rồi UPDATE các order mục tiêu.

```sql
BEGIN;

WITH gross_per_order AS (
    SELECT
        i.order_id,
        SUM(i.quantity * i.unit_price) AS gross_amount
    FROM demo_set_order_items AS i
    GROUP BY i.order_id
),
eligible AS (
    SELECT
        o.order_id,
        ROUND(
            g.gross_amount *
            CASE c.tier
                WHEN 'GOLD' THEN 0.90
                WHEN 'SILVER' THEN 0.95
                ELSE 1.00
            END,
            2
        ) AS new_net_amount
    FROM demo_set_orders AS o
    JOIN demo_set_customers AS c
      ON c.customer_id = o.customer_id
     AND c.tenant_id = o.tenant_id
    JOIN gross_per_order AS g
      ON g.order_id = o.order_id
    WHERE o.tenant_id = 10
      AND o.status = 'PAID'
      AND o.processed_at IS NULL
      AND c.is_active = TRUE
)
UPDATE demo_set_orders AS target
SET net_amount = e.new_net_amount,
    processed_at = CURRENT_TIMESTAMP
FROM eligible AS e
WHERE target.order_id = e.order_id
  AND target.tenant_id = 10
  AND target.processed_at IS NULL
RETURNING target.order_id, target.net_amount;

-- Có thể đối soát 5 hàng, tổng net 669.50 trong transaction.
ROLLBACK;
```

Ở đây **không có loop thủ tục trên từng order**. SQL mô tả một tập `gross_per_order` rồi nối với tập `eligible` và áp dụng UPDATE hàng loạt.

### 5.1. Cơ chế từng bước

1. **`gross_per_order`:** một hàng/đơn, vì `GROUP BY i.order_id`.
2. **`eligible`:** JOIN order với customer, chỉ chọn tenant 10, PAID, chưa processed, customer active.
3. **CASE:** biến tier thành hệ số giảm.
4. **ROUND:** làm tròn tại **cấp đơn** tới hai chữ số thập phân.
5. **UPDATE ... FROM:** cập nhật từng target order bằng `new_net_amount` của source.
6. **RETURNING:** cho phép kiểm số hàng và giá trị đã thay đổi.
7. **ROLLBACK:** hủy cập nhật trong ví dụ học tập.

### 5.2. Đảm bảo nguồn JOIN chỉ một hàng cho mỗi target

Trong PostgreSQL, `UPDATE ... FROM` có thể cho kết quả không được xác định theo ý người viết nếu **một target khớp nhiều source row**, vì database không có nghĩa vụ chọn source row theo thứ tự mong muốn.

Ở đây:

- `gross_per_order` có tối đa một hàng mỗi `order_id`.
- `demo_set_orders.order_id` là PRIMARY KEY.
- `demo_set_customers.customer_id` là PRIMARY KEY.
- JOIN và các khóa hỗ trợ chứng minh một source row cho mỗi order.

Đừng bỏ GROUP BY rồi JOIN trực tiếp item với order trong UPDATE:

```sql
-- Không dùng để tính toàn bộ net: mỗi order có thể khớp nhiều item.
UPDATE demo_set_orders AS o
SET net_amount = i.quantity * i.unit_price
FROM demo_set_order_items AS i
WHERE i.order_id = o.order_id;
```

Với order 101 có hai item, không có bảo đảm biểu thức lấy đúng tổng 250. Đây là **sai tính tương đương**, không phải tối ưu.

### 5.3. CTE có phải luôn được materialize?

Không. Với PostgreSQL hiện đại, tùy cấu trúc và phiên bản, CTE có thể được inline/được tối ưu cùng query hoặc materialize theo điều kiện/hint. CTE trong bài này chủ yếu để làm rõ **mức chi tiết của nguồn**. Đừng mặc định “viết WITH chắc chắn tạo bảng tạm” hoặc “WITH luôn nhanh hơn subquery”; kiểm tra execution plan thực tế.

### 5.4. Tính trước toàn bộ items hay chỉ items đủ điều kiện?

CTE `gross_per_order` ở trên nhóm tất cả items, rồi `eligible` chọn các đơn cần update. Trên tập dữ liệu lớn, có thể giảm công việc bằng cách **lọc order cần xử lý trước**, sau đó mới JOIN items của những order đó. Đó là một rewrite set-based khác. Tuy nhiên, trước khi đo plan, phải giữ đúng điều kiện và tính một gross trên mỗi order.

## 6. Phiên bản tối ưu logic: lọc mục tiêu trước khi tổng hợp

Truy vấn sau tạo tập `target_orders` rồi tính tổng theo chính tập này:

```sql
WITH target_orders AS (
    SELECT
        o.order_id,
        c.tier
    FROM demo_set_orders AS o
    JOIN demo_set_customers AS c
      ON c.customer_id = o.customer_id
     AND c.tenant_id = o.tenant_id
    WHERE o.tenant_id = 10
      AND o.status = 'PAID'
      AND o.processed_at IS NULL
      AND c.is_active = TRUE
),
computed AS (
    SELECT
        t.order_id,
        ROUND(
            SUM(i.quantity * i.unit_price) *
            CASE t.tier
                WHEN 'GOLD' THEN 0.90
                WHEN 'SILVER' THEN 0.95
                ELSE 1.00
            END,
            2
        ) AS new_net_amount
    FROM target_orders AS t
    JOIN demo_set_order_items AS i
      ON i.order_id = t.order_id
    GROUP BY t.order_id, t.tier
)
SELECT order_id, new_net_amount
FROM computed
ORDER BY order_id;
```

Kỳ vọng năm hàng với số net như mục 3.1. Câu này chỉ **SELECT**, giúp kiểm công thức trước khi cho phép cập nhật.

### 6.1. Vì sao không dùng SELECT * từ CTE để cập nhật bừa?

Một CTE có nhiều cột có thể vô tình mang theo duplicate. Cần định nghĩa **khóa của mỗi hàng** và chọn những cột thật sự dùng để UPDATE. Mỗi `order_id` trong `computed` phải có **một giá trị new_net_amount**.

### 6.2. Điều kiện JOIN item ảnh hưởng các đơn không có item

Trong phiên bản này, INNER JOIN với items làm những order không có item **không xuất hiện** trong `computed`. Nó tương đương với loop mục 4 vốn bỏ qua `v_gross IS NULL`. Nhưng nếu nghiệp vụ đổi thành “đơn không có item có gross=0” thì cần dùng LEFT JOIN và `COALESCE`, đồng thời thiết kế rõ trường hợp zero-item có hợp lệ hay không.

### 6.3. Giữ phạm vi tenant qua mọi khóa cần thiết

Ở mẫu lab, order_id là PRIMARY KEY toàn cục nên `i.order_id = t.order_id` không mơ hồ. Trong hệ thật, nếu `order_id` chỉ unique **bên trong tenant**, các JOIN phải mang theo `tenant_id` và schema item cũng phải có tenant hoặc khóa toàn cục phù hợp. Không được đổi JOIN chỉ dựa vào dữ liệu mẫu nhỏ.

## 7. Từ SELECT đã kiểm đến UPDATE tập hợp

Khi một SELECT đã trả kết quả đúng, có thể biến thành nguồn UPDATE:

```sql
BEGIN;

WITH target_orders AS (
    SELECT o.order_id, c.tier
    FROM demo_set_orders AS o
    JOIN demo_set_customers AS c
      ON c.customer_id = o.customer_id
     AND c.tenant_id = o.tenant_id
    WHERE o.tenant_id = 10
      AND o.status = 'PAID'
      AND o.processed_at IS NULL
      AND c.is_active = TRUE
),
computed AS (
    SELECT
        t.order_id,
        ROUND(
            SUM(i.quantity * i.unit_price) *
            CASE t.tier
                WHEN 'GOLD' THEN 0.90
                WHEN 'SILVER' THEN 0.95
                ELSE 1.00
            END, 2
        ) AS new_net
    FROM target_orders AS t
    JOIN demo_set_order_items AS i
      ON i.order_id = t.order_id
    GROUP BY t.order_id, t.tier
)
UPDATE demo_set_orders AS o
SET net_amount = c.new_net,
    processed_at = CURRENT_TIMESTAMP
FROM computed AS c
WHERE o.order_id = c.order_id
  AND o.tenant_id = 10
  AND o.processed_at IS NULL
RETURNING o.order_id, o.net_amount, o.processed_at;

-- Trong transaction: kỳ vọng 5 hàng.
SELECT COUNT(*) AS processed_orders,
       SUM(net_amount) AS total_net
FROM demo_set_orders
WHERE tenant_id = 10
  AND processed_at IS NOT NULL;

ROLLBACK;
```

Từ dữ liệu ban đầu: `processed_orders = 5` và `total_net = 669.50`.

**Cần nhớ:** kiểm số hàng tác động là một phần hợp đồng, không phải chỉ kiểm lệnh không có lỗi. Nếu yêu cầu phải xử lý đúng năm đơn nhưng UPDATE trả ba hàng vì một transaction khác đã xử lý hai đơn, ứng dụng phải xác định đây là tình trạng bình thường do cạnh tranh hay lỗi cần thông báo.

## 8. Phải xác minh tính tương đương trước khi đo tốc độ

Một truy vấn chạy 20 ms nhưng nhân bản doanh thu là **sai**. Trước khi so sánh plan của loop và set-based, cần kiểm:

1. Tập đối tượng được chọn giống nhau: tenant, status, active, processed.
2. Mỗi order xuất hiện **đúng một lần** ở đầu ra.
3. Giá trị net giống nhau tới quy tắc làm tròn đã thỏa thuận.
4. Cả hai bỏ qua hoặc xử lý giống nhau các đơn không có item.
5. NULL/0/âm/bản ghi hỏng được xử lý giống yêu cầu.
6. Các tác dụng của trigger, audit, constraint và lỗi được định nghĩa rõ.
7. Khi chạy song song, có transaction/isolation/idempotency thích hợp.

### 8.1. So sánh hai cách tính ở cấp SELECT

Để tránh thực thi UPDATE khi đối chiếu, tạo **hai kết quả SELECT**: một dùng subquery theo order, một dùng GROUP BY set-based.

```sql
WITH
eligible AS (
    SELECT o.order_id, c.tier
    FROM demo_set_orders AS o
    JOIN demo_set_customers AS c
      ON c.customer_id = o.customer_id
     AND c.tenant_id = o.tenant_id
    WHERE o.tenant_id = 10
      AND o.status = 'PAID'
      AND o.processed_at IS NULL
      AND c.is_active = TRUE
),
per_order_query AS (
    SELECT
        e.order_id,
        ROUND(
            (SELECT SUM(i.quantity * i.unit_price)
             FROM demo_set_order_items AS i
             WHERE i.order_id = e.order_id) *
            CASE e.tier
                WHEN 'GOLD' THEN 0.90
                WHEN 'SILVER' THEN 0.95
                ELSE 1.00
            END, 2
        ) AS new_net
    FROM eligible AS e
),
grouped_query AS (
    SELECT
        e.order_id,
        ROUND(
            SUM(i.quantity * i.unit_price) *
            CASE e.tier
                WHEN 'GOLD' THEN 0.90
                WHEN 'SILVER' THEN 0.95
                ELSE 1.00
            END, 2
        ) AS new_net
    FROM eligible AS e
    LEFT JOIN demo_set_order_items AS i
      ON i.order_id = e.order_id
    GROUP BY e.order_id, e.tier
),
a_minus_b AS (
    SELECT * FROM per_order_query
    EXCEPT ALL
    SELECT * FROM grouped_query
),
b_minus_a AS (
    SELECT * FROM grouped_query
    EXCEPT ALL
    SELECT * FROM per_order_query
)
SELECT 'PER_ORDER_ONLY' AS side, *
FROM a_minus_b
UNION ALL
SELECT 'GROUPED_ONLY' AS side, *
FROM b_minus_a;
```

Kỳ vọng **0 hàng** trong dữ liệu mẫu. `EXCEPT ALL` phát hiện cả khác biệt về **số lần xuất hiện của hàng trùng**, khác với `EXCEPT` mặc định theo set.

**Lưu ý:** phép đối chiếu SELECT này xác minh công thức trên snapshot hiện tại; nó không tự chứng minh mọi hành vi UPDATE/trigger/concurrency tương đương. Việc chứng minh cho mọi dữ liệu hợp lệ còn cần giả thiết schema và test biên.

### 8.2. Vì sao dùng LEFT JOIN trong grouped_query?

Subquery `SUM` trên tập không có item trả NULL. Nếu `grouped_query` dùng INNER JOIN, một order không có item **biến mất khỏi kết quả**, khiến hai SELECT khác số hàng. LEFT JOIN giữ order, `SUM(i.quantity * i.unit_price)` vẫn là NULL cho order không có item, nên gần với semantics subquery.

Hai phiên bản **UPDATE** ở mục 4–7 đều bỏ qua order không có item. So sánh hai SELECT có thể giữ các order ấy với net NULL để phát hiện khác biệt về công thức, còn trước khi UPDATE phải xác định rõ quy tắc có xử lý hay không. Đó là lý do **so sánh đúng phạm vi** luôn quan trọng.

### 8.3. Rounding: cùng số tiền chưa chắc cùng cách tính

Hai công thức:

```sql
ROUND(SUM(quantity * unit_price) * factor, 2)
```

và:

```sql
SUM(ROUND(quantity * unit_price * factor, 2))
```

không luôn bằng nhau khi có nhiều dòng lẻ xu. Ví dụ hai dòng cùng giá trị nhỏ có thể khiến làm tròn mỗi dòng khác làm tròn tổng. Bài này chọn **làm tròn ở cấp order**; không tự tối ưu bằng cách đẩy `ROUND` xuống từng item nếu hợp đồng không cho phép.

## 9. Thay N lần SELECT aggregate bằng một GROUP BY

Một ứng dụng có thể chạy:

```text
for customer in customers:
    SELECT COUNT(*) FROM orders WHERE customer_id = customer.id
    SELECT SUM(...) FROM orders WHERE customer_id = customer.id
```

Với N khách, có thể tạo 2N câu SELECT và nhiều round trips.

Thay bằng:

```sql
SELECT
    o.customer_id,
    COUNT(*) AS order_count,
    COUNT(*) FILTER (WHERE o.status = 'PAID') AS paid_count
FROM demo_set_orders AS o
WHERE o.tenant_id = 10
GROUP BY o.customer_id
ORDER BY o.customer_id;
```

Câu lệnh này tổng hợp các đơn tenant 10 theo customer trong một truy vấn. Cần bảo đảm chỉ số nghiệp vụ muốn tính **tất cả đơn** hay chỉ các đơn PAID/chưa xóa mềm.

### 9.1. Giữ khách chưa có đơn bằng LEFT JOIN

Nếu hợp đồng là “hiện mọi khách active, kể cả khách 0 đơn”:

```sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(
        SUM(o.net_amount) FILTER (WHERE o.status = 'PAID'),
        0
    ) AS paid_net_total
FROM demo_set_customers AS c
LEFT JOIN demo_set_orders AS o
  ON o.customer_id = c.customer_id
 AND o.tenant_id = c.tenant_id
 AND o.status = 'PAID'
WHERE c.tenant_id = 10
  AND c.is_active = TRUE
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
```

Điều kiện `o.status='PAID'` nằm trong `ON` để giữ cả những khách chưa có đơn PAID. Vì net_amount của bảng demo ban đầu là NULL, `SUM(o.net_amount)` sẽ là NULL và `COALESCE` trả 0; sau khi thực sự COMMIT bước tính net thì các tổng mới có ý nghĩa.

### 9.2. COUNT(*) sau LEFT JOIN là bẫy

Một khách không có order PAID vẫn có **một hàng NULL-extended** sau LEFT JOIN. `COUNT(*)` có thể là 1, còn `COUNT(o.order_id)` bằng 0. Đừng chuyển qua COUNT(*) chỉ vì nghe nói “nhanh hơn”.

### 9.3. Aggregate có điều kiện bằng CASE

Với DBMS không có cú pháp `FILTER`:

```sql
SUM(CASE WHEN status = 'PAID' THEN 1 ELSE 0 END)
```

thường có thể thay `COUNT(*) FILTER (WHERE status = 'PAID')` khi nhóm có hàng phù hợp về cấu trúc. Nhưng `SUM(CASE ... THEN 1 END)` có thể trả NULL cho nhóm không có match, không phải 0. Giữ đúng NULL semantics khi rewrite.

## 10. Thay vòng lặp INSERT bằng INSERT ... SELECT

Một bài toán thường gặp: tạo snapshot/tổng hợp cho nhiều khách. Thay vì:

```text
for each customer:
    calculate totals
    INSERT summary row
```

có thể dùng một `INSERT INTO ... SELECT`.

Tạo bảng tạm chứa snapshot:

```sql
CREATE TEMP TABLE demo_set_customer_summary (
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    paid_order_count BIGINT NOT NULL,
    paid_gross NUMERIC(14, 2) NOT NULL,
    calculated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, customer_id)
);
```

Một lần tạo snapshot từ đơn/chi tiết:

```sql
BEGIN;

WITH order_gross AS (
    SELECT
        o.order_id,
        o.tenant_id,
        o.customer_id,
        o.status,
        COALESCE(SUM(i.quantity * i.unit_price), 0) AS gross
    FROM demo_set_orders AS o
    LEFT JOIN demo_set_order_items AS i
      ON i.order_id = o.order_id
    WHERE o.tenant_id = 10
    GROUP BY o.order_id, o.tenant_id, o.customer_id, o.status
)
INSERT INTO demo_set_customer_summary (
    tenant_id, customer_id,
    paid_order_count, paid_gross, calculated_at
)
SELECT
    c.tenant_id,
    c.customer_id,
    COUNT(g.order_id) FILTER (WHERE g.status = 'PAID'),
    COALESCE(
        SUM(g.gross) FILTER (WHERE g.status = 'PAID'),
        0
    ),
    CURRENT_TIMESTAMP
FROM demo_set_customers AS c
LEFT JOIN order_gross AS g
  ON g.customer_id = c.customer_id
 AND g.tenant_id = c.tenant_id
WHERE c.tenant_id = 10
  AND c.is_active = TRUE
GROUP BY c.tenant_id, c.customer_id;

SELECT *
FROM demo_set_customer_summary
ORDER BY customer_id;

ROLLBACK;
```

Trong ví dụ, snapshot được tạo **một hàng mỗi khách active**, kể cả khách chưa có đơn. Phép tính gross được nhóm về order trước rồi mới nhóm theo customer, tránh nhân bản khi order có nhiều items.

### 10.1. INSERT SELECT và tính nguyên tử

Trong PostgreSQL, một statement INSERT SELECT chạy theo transaction semantics của engine. Nếu muốn tạo snapshot và cập nhật các bảng khác **cùng commit**, đặt chúng trong một transaction rõ. Nhưng một statement khổng lồ không tự bảo đảm mọi thao tác downstream ngoài DB cùng atomic.

### 10.2. Khi chạy lại snapshot

Vì bảng có PRIMARY KEY, chạy INSERT nguyên dạng lần hai sau COMMIT có thể gặp lỗi unique. Nếu muốn chạy lại, cần quyết định:

- Xóa/refresh toàn bộ snapshot trong một transaction phù hợp.
- Dùng `INSERT ... ON CONFLICT DO UPDATE` theo các khóa unique.
- Dùng mô hình snapshot có `snapshot_date` trong khóa.
- Chỉ insert những khách chưa có, dùng anti-join và kiểm soát concurrency.

Không ngầm cho rằng “chạy lại lần nào cũng được” nếu chưa thiết kế idempotency.

## 11. UPSERT tập hợp thay loop kiểm tra tồn tại rồi INSERT/UPDATE

Một pattern thủ tục:

```text
for each summary:
    SELECT exists?
    if exists:
        UPDATE
    else:
        INSERT
```

không chỉ nhiều statement mà còn có **race** giữa SELECT và INSERT khi hai job chạy đồng thời.

PostgreSQL hỗ trợ `INSERT ... ON CONFLICT ... DO UPDATE`:

```sql
INSERT INTO demo_set_customer_summary (
    tenant_id, customer_id,
    paid_order_count, paid_gross, calculated_at
)
SELECT
    c.tenant_id,
    c.customer_id,
    COUNT(o.order_id) FILTER (WHERE o.status = 'PAID'),
    COALESCE(
        SUM(
            CASE
                WHEN o.status = 'PAID'
                THEN o.net_amount
            END
        ),
        0
    ),
    CURRENT_TIMESTAMP
FROM demo_set_customers AS c
LEFT JOIN demo_set_orders AS o
  ON o.customer_id = c.customer_id
 AND o.tenant_id = c.tenant_id
WHERE c.tenant_id = 10
  AND c.is_active = TRUE
GROUP BY c.tenant_id, c.customer_id
ON CONFLICT (tenant_id, customer_id)
DO UPDATE SET
    paid_order_count = EXCLUDED.paid_order_count,
    paid_gross = EXCLUDED.paid_gross,
    calculated_at = EXCLUDED.calculated_at;
```

**Lưu ý về ngữ nghĩa:** ví dụ trên tổng hợp **net_amount đã được xử lý**. Nếu chưa COMMIT bước tính net, net_amount NULL và các tổng có thể là 0. Nó minh họa cú pháp UPSERT, không thay thế công thức gross dùng items ở mục trước.

### 11.1. Phải có khóa duy nhất thật

`ON CONFLICT (tenant_id, customer_id)` dựa vào UNIQUE/PRIMARY KEY tương ứng ở database. Việc kiểm tra tồn tại qua SELECT trước không thay thế constraint chống hai transaction tạo cùng summary.

### 11.2. UPSERT không tự xóa bản ghi đã lỗi thời

UPSERT cập nhật/thêm những khóa xuất hiện trong nguồn. Nếu trước đây một khách active có summary, sau đó khách inactive không còn xuất hiện trong SELECT, hàng summary cũ vẫn tồn tại trừ khi có bước xử lý riêng (delete/mark stale/refresh toàn bộ). **Đồng bộ đầy đủ** khác với “chỉ upsert các khóa hiện tại”.

### 11.3. Nguồn phải không chứa khóa duplicate

Một set-based UPSERT với nhiều nguồn trùng cùng conflict key có thể lỗi hoặc hoạt động khác mong muốn theo DBMS. Trước khi UPSERT, nhóm/khử trùng **theo đúng khóa đích** và định nghĩa quy tắc xử lý duplicate. Đừng tùy tiện dùng DISTINCT trên toàn bộ hàng khi giá trị khác nhau.

## 12. Thay vòng lặp DELETE bằng DELETE ... WHERE EXISTS

Giả sử cần xóa **các dòng summary không còn tương ứng khách active**. Một cách vòng lặp đọc từng summary rồi tra customer. Có thể diễn tả theo tập:

```sql
DELETE FROM demo_set_customer_summary AS s
WHERE s.tenant_id = 10
  AND NOT EXISTS (
      SELECT 1
      FROM demo_set_customers AS c
      WHERE c.tenant_id = s.tenant_id
        AND c.customer_id = s.customer_id
        AND c.is_active = TRUE
  );
```

Đây là một phép **anti-semi join** về mặt ý tưởng: loại summary nếu không có customer active tương ứng.

### 12.1. NOT EXISTS thường dễ kiểm soát NULL hơn NOT IN

Một rewrite:

```sql
WHERE customer_id NOT IN (SELECT customer_id FROM ...)
```

có thể cho kết quả khó đoán nếu subquery trả NULL, vì SQL dùng logic ba giá trị. `NOT EXISTS` với điều kiện liên hệ rõ thường phù hợp hơn để biểu đạt “không tồn tại bản ghi hợp lệ”.

### 12.2. DELETE USING trong PostgreSQL

Khi yêu cầu xóa những hàng **có bản ghi khớp** ở bảng nguồn:

```sql
DELETE FROM target_table AS t
USING source_table AS s
WHERE t.business_key = s.business_key
  AND s.should_delete = TRUE;
```

Đây là ví dụ cú pháp trên bảng giả định. Cần kiểm soát điều kiện và phạm vi tenant. `DELETE USING` không thay thế `NOT EXISTS` trực tiếp trong mọi bài toán: một cái thường xử lý match, một cái có thể mô tả không có match.

### 12.3. Xóa hàng loạt cũng cần kế hoạch vận hành

Một DELETE 10 triệu hàng trong một transaction có thể làm phình log/WAL, giữ khóa, tăng replication lag và tạo áp lực VACUUM. Set-based là cách diễn đạt tốt, nhưng **batch theo khóa và commit có kiểm soát** có thể là chiến lược vận hành tốt hơn.

## 13. Thay loop cập nhật theo bảng quy tắc bằng UPDATE JOIN

Giả sử hệ thống nhận bảng staging của mức giá mới:

```sql
CREATE TEMP TABLE demo_set_catalog (
    sku TEXT PRIMARY KEY,
    current_price NUMERIC(12, 2) NOT NULL CHECK (current_price >= 0)
);

CREATE TEMP TABLE demo_set_price_stage (
    batch_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    new_price NUMERIC(12, 2) NOT NULL CHECK (new_price >= 0),
    PRIMARY KEY (batch_id, sku)
);

INSERT INTO demo_set_catalog VALUES
    ('PEN', 95.00),
    ('PAD', 45.00),
    ('BOX', 65.00),
    ('BAG', 110.00);

INSERT INTO demo_set_price_stage VALUES
    ('batch-1', 'PEN', 100.00),
    ('batch-1', 'PAD',  50.00),
    ('batch-1', 'BOX',  60.00);
```

Thay vì lặp qua từng SKU:

```sql
BEGIN;

UPDATE demo_set_catalog AS p
SET current_price = s.new_price
FROM demo_set_price_stage AS s
WHERE s.batch_id = 'batch-1'
  AND s.sku = p.sku
RETURNING p.sku, p.current_price;

ROLLBACK;
```

Một UPDATE có thể sửa nhiều sản phẩm dựa trên bảng nguồn. `PRIMARY KEY (batch_id, sku)` giữ **một giá mới mỗi SKU trong batch**, loại mơ hồ “nhiều dòng nguồn khớp một target”.

### 13.1. Nếu staging chứa duplicate theo khóa

Nếu staging cho phép nhiều hàng cùng SKU nhưng khác giá, một UPDATE FROM không biết bạn muốn lấy giá nào. Cần định nghĩa:

- Reject duplicate ngay tại bước validation.
- Chọn bản ghi có `effective_at` mới nhất với tie-breaker xác định.
- Tổng hợp/merge theo quy tắc nghiệp vụ rõ.
- Ghi audit cho xung đột và loại dữ liệu bẩn.

Không dùng `LIMIT 1` trong subquery không có ORDER BY đủ xác định để che lỗi duplicate.

### 13.2. Không tự hồi tố đơn hàng

Tăng giá catalogue hôm nay **không nhất thiết** có nghĩa tính lại giá những đơn đã thanh toán hôm qua. Bảng `demo_set_order_items.unit_price` là giá tại thời điểm ghi nhận đơn trong mô hình minh họa. Trước khi bulk UPDATE một cột liên quan tiền, phải xác định **dữ liệu lịch sử có bất biến hay không**.

## 14. Window functions thay một số vòng lặp trạng thái

Một loop thường dùng để tìm **đơn mới nhất của mỗi khách**:

```text
for each customer:
    SELECT latest order ORDER BY created_at DESC LIMIT 1
```

Trong PostgreSQL có thể:

```sql
SELECT customer_id, order_id, created_at
FROM (
    SELECT
        o.customer_id,
        o.order_id,
        o.created_at,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.order_id DESC
        ) AS rn
    FROM demo_set_orders AS o
    WHERE o.tenant_id = 10
) AS ranked
WHERE rn = 1
ORDER BY customer_id;
```

Mỗi nhóm customer có row number riêng. `ORDER BY created_at DESC, order_id DESC` có **tie-breaker** bằng khóa duy nhất.

### 14.1. ROW_NUMBER khác RANK

Nếu hai đơn cùng timestamp:

- `ROW_NUMBER() = 1` chọn đúng một hàng theo thứ tự đã khai báo.
- `RANK() = 1` có thể chọn **nhiều hàng đồng hạng**.

Thay `ROW_NUMBER` bằng `RANK` để “tối ưu” có thể đổi số hàng, không tương đương. Nếu thiếu tie-breaker, lựa chọn row_number trong các hàng tie có thể không ổn định.

### 14.2. Tổng tích lũy bằng SUM OVER

Thay vòng lặp “cộng dồn số tiền theo thời gian”:

```sql
SELECT
    o.customer_id,
    o.order_id,
    o.created_at,
    COALESCE(o.net_amount, 0) AS net_amount,
    SUM(COALESCE(o.net_amount, 0)) OVER (
        PARTITION BY o.customer_id
        ORDER BY o.created_at, o.order_id
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS running_net
FROM demo_set_orders AS o
WHERE o.tenant_id = 10
ORDER BY o.customer_id, o.created_at, o.order_id;
```

Chọn rõ `ROWS BETWEEN ...` để tổng tích lũy theo **số hàng** đã sắp xếp, thay vì vô tình dùng frame mặc định có thể xử lý peers cùng sort key theo cách khác. Trong dữ liệu gốc, net_amount NULL nên được coi 0 trong ví dụ; sau COMMIT bước tính tiền thì mới phản ánh giá trị tính được.

### 14.3. Window function không phá vỡ grain

Các giá trị window được tính trên hàng kết quả theo partition mà không tự thu gọn mọi khách về một hàng như GROUP BY. Khi cần **một hàng mỗi khách**, còn phải lọc row_number hoặc aggregate. Đừng thay GROUP BY bằng window rồi quên chọn đúng số hàng.

## 15. Dùng CASE thay IF từng hàng khi quy tắc có thể diễn đạt bằng SQL

Một loop kiểu:

```text
if tier == GOLD: factor = .90
else if tier == SILVER: factor = .95
else factor = 1
```

có thể viết:

```sql
CASE tier
    WHEN 'GOLD' THEN 0.90
    WHEN 'SILVER' THEN 0.95
    ELSE 1.00
END
```

Một `CASE` có thể nằm trong SELECT, UPDATE, ORDER BY hay aggregate. Nhưng cần nắm:

- `CASE` là **biểu thức chọn giá trị**, không phải vòng lặp hoặc lệnh điều khiển transaction.
- Nếu tier có NULL hoặc giá trị lạ, nhánh `ELSE` xác định hành vi. Trong bảng mẫu có CHECK hạn chế tier; nếu dữ liệu thật không có constraint ấy, ELSE 1 có thể che giá trị sai nghiệp vụ.
- Biểu thức có phép chia cho 0, cast sai hoặc hàm đặc biệt không nhất thiết được đánh giá theo mô hình lazy branching đơn giản trong mọi hoàn cảnh optimizer. Không dùng CASE làm thay thế duy nhất cho validation kiểu dữ liệu và invariant.

### 15.1. Quy tắc phức tạp nên ở bảng dữ liệu

Nếu có 100 tier/chiến dịch thay đổi thường xuyên, một CASE khổng lồ có thể khó quản trị. Có thể tạo bảng `discount_rules` với khóa duy nhất theo tier, hiệu lực theo thời gian và JOIN tới đúng quy tắc.

Lúc ấy cần đảm bảo **mỗi order chỉ khớp một quy tắc có hiệu lực**. Nếu các khoảng thời gian giảm giá chồng nhau, JOIN có thể nhân hàng và tạo giá trị mơ hồ.

## 16. Hàm thủ tục gọi cho từng hàng: cân nhắc thay bằng biểu thức tập hợp

Một biểu thức:

```sql
SELECT
    order_id,
    calculate_net_amount(order_id)
FROM orders;
```

có thể trông gọn, nhưng nếu `calculate_net_amount` (hàm giả định) chạy SELECT items cho mỗi order, bạn vẫn đang **lặp công việc từng hàng** bên trong function. DBMS có thể không nhìn xuyên qua thân hàm để tối ưu toàn cục, tùy loại hàm và engine.

### 16.1. Hàm SQL đơn giản khác hàm truy vấn phụ theo hàng

Ví dụ một hàm thuần giá trị:

```sql
CREATE OR REPLACE FUNCTION pg_temp.demo_discount_factor(p_tier TEXT)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE p_tier
        WHEN 'GOLD' THEN 0.90::NUMERIC
        WHEN 'SILVER' THEN 0.95::NUMERIC
        ELSE 1.00::NUMERIC
    END
$$;
```

Hàm này nhận một giá trị tier và trả một hệ số, không truy vấn bảng khác. Có thể:

```sql
SELECT customer_id, tier,
       pg_temp.demo_discount_factor(tier) AS factor
FROM demo_set_customers
WHERE tenant_id = 10;
```

Việc dùng function hay CASE trực tiếp tốt hơn về plan phụ thuộc loại hàm, khả năng inline và phiên bản PostgreSQL. **Không kết luận mọi UDF đều chậm**. Điều cần tránh là gọi truy vấn tốn kém một lần cho **mỗi hàng ngoài** khi có phép JOIN/GROUP BY một lần tương đương.

### 16.2. Hàm có side effect không được “vector hóa” mù quáng

Nếu một function gửi event, tăng sequence, ghi audit riêng hoặc gọi dịch vụ ngoài, việc gộp/đổi thứ tự gọi có thể đổi **số lần và thời điểm side effect**. Chỉ rewrite như hàm thuần khi có hợp đồng rõ về tính deterministic/volatility và quyền.

### 16.3. Stored procedure vẫn hữu ích

Một stored procedure có thể bao gồm **một số ít statement tập hợp** cùng transaction và điều khiển lỗi:

```text
BEGIN nghiệp vụ
    validate batch bằng SELECT tập hợp
    UPDATE ... FROM set
    INSERT ... SELECT audit/outbox
    verify row count
COMMIT / ROLLBACK
```

Đó là thiết kế kết hợp hợp lý: dùng thủ tục để **điều phối bước nghiệp vụ**, nhưng tránh loop từng hàng khi không cần.

## 17. Một statement lớn hay nhiều batch set-based?

Thay cursor N lần bằng một UPDATE 50 triệu hàng có thể giảm overhead từng statement nhưng mang những rủi ro:

- Transaction log/WAL rất lớn.
- Lock và row versions kéo dài.
- Replication lag tăng.
- Bản sao/CDC phát nhiều thay đổi trong thời gian ngắn.
- Autovacuum/purge theo engine chịu áp lực.
- ROLLBACK tốn thời gian và tài nguyên.
- Memory hoặc sort/hash spill khi aggregate lớn.
- Timeout và chiếm connection kéo dài.

Vì vậy, lựa chọn thực tế có thể là **lặp theo batch**, mỗi batch dùng **một hoặc vài SQL set-based**.

### 17.1. Phân biệt hai loại vòng lặp

```text
RBAR:
  for mỗi order:
      SELECT items
      UPDATE order

SET-BASED BATCHING:
  for mỗi batch của nhiều order:
      SELECT/GROUP BY chung
      UPDATE tất cả order thuộc batch
      COMMIT batch
```

Batching vẫn có loop ở **cấp batch**, nhưng không xử lý N hàng bằng N chuỗi SQL riêng.

### 17.2. Chọn batch size theo đo đạc

Không có con số batch “tốt nhất” cho mọi DB. Có thể thử vài trăm, vài nghìn hoặc hơn tùy kích thước bản ghi, index, trigger, WAL, replication, timeout và SLA. Bắt đầu với kích thước vừa phải, đo số hàng/giây, độ dài transaction, lock waits, latency của workload khác và thay đổi theo kết quả.

### 17.3. Keyset thay OFFSET để chia batch

Khi xử lý nhiều order theo khóa tăng dần, có thể:

```sql
SELECT order_id
FROM demo_set_orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND processed_at IS NULL
  AND order_id > :last_order_id
ORDER BY order_id
LIMIT :batch_size;
```

Trong một công cụ dùng bind parameters, `:last_order_id` và `:batch_size` là placeholder khái niệm, không phải cú pháp trực tiếp của psql. Lấy khóa ở một batch và dùng tập khóa ấy cho UPDATE, sau đó cập nhật checkpoint theo **những khóa đã xử lý thành công**.

`OFFSET` trên tập đang bị UPDATE/DELETE có thể khiến các hàng “dịch trang” và bị bỏ qua. Batching dựa trên khóa ổn định thường dễ reasoning hơn.

### 17.4. Checkpoint không có nghĩa transaction dài xuyên mọi batch

Nếu mỗi batch COMMIT riêng, toàn job **không còn atomic all-or-nothing**. Cần idempotency, checkpoint bền vững, trạng thái batch và khả năng chạy lại sau crash. Nếu yêu cầu nghiệp vụ thật sự là “toàn bộ 50 triệu hàng phải xác nhận cùng lúc”, việc chia commit tùy tiện sẽ thay hợp đồng.

## 18. Nhiều worker cùng xử lý: FOR UPDATE SKIP LOCKED

PostgreSQL có `FOR UPDATE SKIP LOCKED`, hữu ích trong một số hàng đợi tác vụ mà nhiều worker lấy các hàng **chưa bị khóa**.

Mẫu chọn khóa theo batch:

```sql
BEGIN;

WITH next_batch AS (
    SELECT order_id
    FROM demo_set_orders
    WHERE tenant_id = 10
      AND status = 'PAID'
      AND processed_at IS NULL
    ORDER BY order_id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
SELECT order_id
FROM next_batch
ORDER BY order_id;

-- Trong ứng dụng thực, các bước cập nhật batch phải diễn ra
-- trên cùng transaction/connection đang giữ lock.
ROLLBACK;
```

Ở mẫu này, `FOR UPDATE` nhằm khóa hàng chọn; `SKIP LOCKED` bỏ qua những hàng đang bị khóa bởi transaction khác. Nó cho phép nhiều worker giảm việc chờ nhau.

### 18.1. Giới hạn của SKIP LOCKED

- Nó cung cấp một góc nhìn **không nhất quán theo thời điểm khóa**, phù hợp với một số kiểu queue, không phải thay thế SELECT cho báo cáo tài chính.
- Hàng bị khóa lâu có thể bị skip nhiều lần, cần giám sát fairness/starvation.
- Phải xác định logic claim/processed state/idempotency thật, tránh xử lý lặp sau crash.
- Nếu chỉ SELECT khóa rồi ROLLBACK như ví dụ, **không có job nào được đánh dấu xong**.
- Điều kiện JOIN/tính tiền phải bảo đảm một kết quả cho mỗi target; chọn batch không sửa được lỗi fanout.

### 18.2. UPDATE từ batch đã khóa

Trong thực tế có thể đưa `next_batch` vào cùng một CTE update, sau đó `RETURNING` các hàng đã nhận; hoặc giữ transaction mở một thời gian ngắn, tính/ghi batch và COMMIT. Không để khóa mở trong lúc gọi API chậm hoặc đợi người dùng.

### 18.3. Ít round trips không đồng nghĩa giữ lock tùy ý

Một batch set-based và một transaction ngắn là lợi thế. Nhưng nếu một câu update kéo dài phút/giờ, cần quan sát tác động đồng thời, phân vùng/ràng buộc và chính sách retry.

## 19. Transaction và tính nguyên tử khi thay loop bằng set-based

Xét hai cách:

```text
Loop có COMMIT sau mỗi hàng:
    UPDATE 101; COMMIT
    UPDATE 103; COMMIT
    UPDATE 104; lỗi
    -> 101, 103 đã được xác nhận

Một UPDATE tập hợp trong transaction:
    BEGIN
    UPDATE cả 101,103,104
    -> một lỗi constraint
    ROLLBACK
    -> không giữ những cập nhật chưa commit
```

Hai cách có **ngữ nghĩa lỗi và phạm vi commit khác nhau**. Nếu yêu cầu là toàn bộ batch phải thành công hoặc thất bại, một transaction là phù hợp. Nếu yêu cầu chấp nhận hàng tốt và báo hàng xấu, cần thiết kế staging/reject/batch riêng.

### 19.1. Có một lỗi không có nghĩa chỉ hàng đó bị bỏ qua

Trong PostgreSQL, một statement UPDATE tập hợp vi phạm constraint có thể làm cả statement thất bại, và transaction ngoài có thể ở trạng thái aborted. Không thể mặc định “database bỏ qua hàng lỗi rồi tiếp tục các hàng tốt”. Nếu cần tiếp tục sau lỗi, thiết kế validation trước, staging, `SAVEPOINT` có kiểm soát hoặc batch nhỏ theo chính sách.

### 19.2. Chạy nhiều statement set-based trong một transaction

Một nghiệp vụ có thể cần:

```text
BEGIN
  UPDATE orders ... FROM computed
  INSERT audit ... SELECT ...
  INSERT outbox ...
COMMIT
```

Mỗi statement xử lý tập hợp, và transaction xác nhận chúng như một đơn vị. Nếu audit/event phải phản ánh chính xác các hàng UPDATE, cần dùng `RETURNING` và cơ chế truyền kết quả phù hợp trong PostgreSQL, hoặc staging khóa đã xử lý, thay vì SELECT lại một tập đã có thể biến động theo logic khác.

### 19.3. PostgreSQL RETURNING là nguồn để ghi audit

Ví dụ chỉ minh họa nguyên tắc:

```sql
WITH changed AS (
    UPDATE demo_set_catalog AS p
    SET current_price = s.new_price
    FROM demo_set_price_stage AS s
    WHERE s.batch_id = 'batch-1'
      AND s.sku = p.sku
    RETURNING p.sku, p.current_price
)
SELECT COUNT(*) AS affected_products
FROM changed;
```

Ví dụ này **thực hiện UPDATE và giữ kết quả** nếu chạy ngoài BEGIN/ROLLBACK. Khi chỉ muốn thử, nên:

```text
BEGIN;
... câu UPDATE có RETURNING ...
ROLLBACK;
```

Ở PostgreSQL, `RETURNING` trả các hàng thực sự bị UPDATE/INSERT/DELETE, hữu ích để audit và đối chiếu số hàng. Tuy nhiên, cách lấy **giá trị cũ và mới** cần xét cú pháp phiên bản và mô hình staging; không tự suy diễn `RETURNING current_price` vừa chứa cả before/after.

## 20. Concurrency: set-based không tự ngăn mọi race

Ví dụ hai worker cùng chọn `processed_at IS NULL`. Khi cùng UPDATE:

- Database có row locks và cơ chế isolation riêng.
- Một worker có thể chờ worker kia.
- Sau khi chờ, điều kiện cần được đánh giá lại theo quy tắc DBMS/isolation.
- Có thể phát sinh deadlock/serialization failure, cần retry phù hợp.

### 20.1. Điều kiện trạng thái nằm ngay trong UPDATE

```sql
UPDATE demo_set_orders
SET processed_at = CURRENT_TIMESTAMP
WHERE tenant_id = 10
  AND status = 'PAID'
  AND processed_at IS NULL
RETURNING order_id;
```

So với kiểu “SELECT đơn chưa xử lý, lâu sau mới UPDATE mọi ID”, điều kiện trong UPDATE giúp database kiểm tra trạng thái tại thao tác ghi. Nhưng nếu phép tính phụ thuộc cả các bảng khác có thể thay đổi đồng thời, cần xác định snapshot, locks và invariant tương ứng.

### 20.2. Idempotency

`processed_at IS NULL` có thể giảm cập nhật lại cùng đơn, nhưng chưa đủ cho workflow phức tạp:

- Điều gì nếu job đã cập nhật net_amount nhưng crash trước khi gửi message?
- Nếu processed_at được đặt trước khi ghi ledger, có thể mất nghiệp vụ?
- Nếu job chạy lại với công thức/tier khác, có được tính lại?

Hãy định nghĩa **operation_id/batch_id**, trạng thái xử lý, nguồn dữ liệu tính toán và audit. Nếu cần gửi event, cân nhắc transactional outbox trong cùng commit.

### 20.3. Không update dựa trên dữ liệu cũ mà quên version

Hai request cùng đọc balance=100 rồi lần lượt ghi balance=90 và 80 có thể làm mất update theo cơ chế/concurrency cụ thể. Một `UPDATE balance = balance - 10 WHERE balance >= 10` biểu đạt phép cập nhật tương đối với điều kiện tại lúc ghi tốt hơn mẫu đọc ở app rồi gửi số balance mới. Với tình huống phức tạp, dùng row lock hoặc optimistic `version`.

### 20.4. Deadlocks và isolation

Một UPDATE tập hợp có thể khóa nhiều hàng. Nếu hai transaction sửa những tập giao nhau với thứ tự khóa khác nhau, deadlock vẫn xảy ra. Chọn thứ tự khóa/khóa chính phù hợp, transaction ngắn và retry có giới hạn; không hứa rằng “một statement duy nhất” loại bỏ mọi deadlock.

## 21. Index và execution plan: đo sau khi đã đúng

Set-based SQL giúp optimizer có không gian lựa chọn:

- Seq Scan / Index Scan / Bitmap Scan.
- Hash Join / Merge Join / Nested Loop.
- HashAggregate / GroupAggregate.
- Sort, window aggregation, parallel execution tùy engine/query.

Nhưng chọn plan nào phụ thuộc dữ liệu, thống kê, version, index, tham số, cấu hình và mức độ chọn lọc. Không phải `GROUP BY` luôn nhanh hơn subquery; optimizer đôi khi **decorrelate** subquery và biến nó thành plan tương tự.

### 21.1. Chỉ mục phục vụ lọc đơn và JOIN

Với PostgreSQL lab, có thể thử:

```sql
CREATE INDEX idx_demo_set_orders_pending_paid
ON demo_set_orders (tenant_id, order_id)
WHERE status = 'PAID'
  AND processed_at IS NULL;

CREATE INDEX idx_demo_set_items_order
ON demo_set_order_items (order_id);
```

Index đầu hỗ trợ truy vấn lọc đơn PAID chưa xử lý theo tenant; index thứ hai phục vụ lookup items theo order_id. Bảng demo chỉ 10 đơn nên planner có thể vẫn thích Seq Scan; điều đó không chứng minh index không hữu ích khi dữ liệu thật lớn.

### 21.2. EXPLAIN cho query SELECT tính net

```sql
EXPLAIN
SELECT
    i.order_id,
    SUM(i.quantity * i.unit_price) AS gross
FROM demo_set_order_items AS i
GROUP BY i.order_id;
```

`EXPLAIN` không ANALYZE chỉ cho **ước tính kế hoạch**. Có thể dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    i.order_id,
    SUM(i.quantity * i.unit_price) AS gross
FROM demo_set_order_items AS i
GROUP BY i.order_id;
```

để thấy execution time, actual rows/loops và buffers trong PostgreSQL. Đo trên dữ liệu đại diện, không suy diễn hiệu năng production từ bảng tạm vài hàng.

### 21.3. EXPLAIN ANALYZE thực sự chạy DML

```sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE demo_set_orders
SET ...;
```

nếu viết một lệnh UPDATE hợp lệ, PostgreSQL sẽ **thực hiện thay đổi** để đo, không chỉ vẽ plan. Muốn đo DML trên dữ liệu test mà không giữ thay đổi:

```text
BEGIN;
EXPLAIN (ANALYZE, BUFFERS) UPDATE ...;
ROLLBACK;
```

Tuy nhiên, ROLLBACK không đảo những side effect ngoài database hoặc mọi sequence/log. Không chạy bừa lệnh UPDATE/DELETE phân tích trên production.

### 21.4. Đo những gì?

| Chỉ số | Ý nghĩa |
| --- | --- |
| Tổng thời gian end-to-end | Gồm round trips từ ứng dụng khi có loop |
| Số statement và round trips | Phát hiện N+1 query |
| Actual rows và loops | Có phép lặp nhiều lần không? |
| Estimated vs actual rows | Planner có ước lượng sai cardinality? |
| Buffers/I/O | Query đọc/ghi dữ liệu bao nhiêu |
| Sort/hash spill, temp files | Có thiếu memory cho aggregate/sort? |
| WAL/transaction log và replication lag | Chi phí ghi tập hợp lớn |
| Lock wait, deadlock, timeout | Tác động concurrency |
| CPU/database time | Có cải thiện thật trong workload? |
| Số hàng thay đổi và các chỉ số nghiệp vụ | Có giữ đúng kết quả? |

### 21.5. N+1 có thể ẩn trong code ứng dụng

ORM thường lazy-load order_items khi loop qua orders:

```text
SELECT orders ...        -- 1 lần
for order:
    order.items          -- N truy vấn SELECT khác
```

Có thể giải bằng eager/batch loading, JOIN phù hợp hoặc một aggregate SQL. Nhưng eager JOIN một-nhiều có thể nhân bản dữ liệu và ảnh hưởng pagination; cần thiết kế theo **hợp đồng dữ liệu** chứ không thêm JOIN mọi nơi.

## 22. Cạm bẫy tính tương đương khi rewrite thủ tục thành tập hợp

### 22.1. Thứ tự cập nhật có thể quan trọng

Nếu logic từng hàng nói:

```text
Hàng 2 phải tính từ kết quả cập nhật của hàng 1
Hàng 3 phải tính từ kết quả của hàng 2
```

thì không thể mặc định một UPDATE tập hợp biểu diễn cùng trình tự ấy. Ví dụ, thuật toán phân bổ từng đồng theo thứ tự ưu tiên có giới hạn tổng, hoặc một workflow duyệt cây cần phát sinh trạng thái trung gian.

Có thể dùng window function/recursive CTE hoặc nhiều bước SQL tập hợp để giữ semantics, nhưng phải chứng minh đúng. Một số bài toán thực sự cần vòng lặp hoặc thuật toán thủ tục.

### 22.2. Trigger chạy theo hàng

Một UPDATE tập hợp sửa 10.000 hàng **không có nghĩa tất cả trigger chỉ chạy một lần**. Trong PostgreSQL, row-level trigger có thể chạy cho mỗi hàng; statement-level trigger có phạm vi khác. Nếu trigger làm công việc đắt tiền, chuyển loop thành một UPDATE có thể giảm round trips nhưng **vẫn giữ chi phí trigger per-row**.

Ngoài ra, bulk DML có thể kích hoạt trigger/callback khác với ORM cập nhật từng entity, tùy framework. Phải xét audit, business validation và side effect.

### 22.3. Thứ tự của các hàng trong UPDATE không được cam kết

Một câu:

```sql
UPDATE table_name
SET sequence_like_value = some_function(...)
WHERE ...;
```

không nên dựa vào “hàng ID nhỏ được update trước”. SQL không cam kết thứ tự áp dụng các phép gán cho các hàng chỉ vì có index hay vì SELECT nguồn từng dùng ORDER BY. Nếu kết quả phụ thuộc thứ tự, cần biểu diễn rõ bằng window/rank hoặc thuật toán có kiểm soát.

### 22.4. NULL và aggregate

`SUM(x)` bỏ qua NULL, `COUNT(*)` đếm mọi hàng, `COUNT(x)` chỉ đếm x không NULL. Một loop cộng theo mặc định 0 có thể khác `SUM` trả NULL khi không có hàng. Phải chọn `COALESCE` và quy tắc zero-item đúng hợp đồng.

### 22.5. LEFT JOIN và WHERE

Trong LEFT JOIN, điều kiện bảng con đặt ở `WHERE` có thể loại hàng cha không có con:

```sql
SELECT c.customer_id, COUNT(o.order_id)
FROM demo_set_customers AS c
LEFT JOIN demo_set_orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id;
```

Nếu mục tiêu giữ mọi khách, nên đặt `o.status='PAID'` trong `ON` và lọc tenant đúng. Không tự đổi LEFT JOIN thành INNER JOIN khi khách 0 đơn vẫn cần xuất hiện.

### 22.6. DISTINCT và fanout

Một JOIN order–items có thể nhân một order thành nhiều hàng. `SUM(DISTINCT amount)` không phải cách chữa tổng quát: hai order khác nhau có thể cùng amount. Phải tổng hợp về **đúng khóa cấp order** trước khi tính tổng tiền.

### 22.7. Lỗi theo từng hàng so với lỗi cả statement

Một cursor có thể catch exception cho một hàng rồi tiếp tục hàng khác. Một UPDATE tập hợp thường không tự có “try/catch per-row” theo mong muốn. Nếu workflow cho phép một số hàng thất bại, phải thiết kế staging/reject table và batch logic; không âm thầm thay toàn bộ hành vi bằng all-or-nothing.

### 22.8. Loại bỏ side effect không phù hợp

Loop có thể gửi email cho từng hàng, ghi file hoặc gọi HTTP. Không thể thay những tác vụ ngoài DB bằng UPDATE set-based thuần mà bảo toàn side effect. Có thể dùng outbox: SQL chọn tập hàng đã xử lý và ghi event rows cùng transaction, sau đó worker gửi bên ngoài theo cơ chế idempotent.

## 23. Những tình huống nên giữ thủ tục hoặc dùng chiến lược kết hợp

| Tình huống | Vì sao loop/điều phối có thể phù hợp? | Cách giảm rủi ro |
| --- | --- | --- |
| Gọi API ngoài cho mỗi đối tượng | Không thể vector hóa thành SQL thuần | Chia batch, retry/idempotency, outbox |
| Cần thứ tự phụ thuộc thật | Hàng sau phụ thuộc kết quả hàng trước | Window/recursive CTE nếu tương đương; nếu không, thuật toán thủ tục |
| Logic duyệt cây/đồ thị đặc biệt | Có điều kiện dừng và nhánh tùy trạng thái | Recursive CTE hoặc vòng lặp có giới hạn |
| Luồng nhiều bước cần kiểm tra/rollback | Cần quyết định nghiệp vụ giữa các bước | Stored procedure điều phối vài statement set-based |
| Mỗi hàng có lỗi cần báo riêng | Không chấp nhận abort cả batch | Staging, reject records, savepoint/batches |
| Hàng triệu bản ghi, SLA ghi hạn chế | Một transaction lớn giữ lock/WAL dài | Set-based theo batch khóa ổn định |
| Tác vụ phải gửi message ra ngoài DB | COMMIT SQL không tự gửi/rollback message | Outbox/inbox, worker ngoài transaction |
| Cần tính toán procedural khó biểu diễn trong SQL | SQL set-based có thể rất khó đọc hoặc tối ưu | Đo thực tế, giữ thủ tục khi có lý do |
| Phụ thuộc thứ tự quyền/phê duyệt | Không thể commit tất cả tức thì | Workflow trạng thái và audit |

### 23.1. “Set-based khi phù hợp” là yêu cầu thiết kế, không phải khẩu hiệu

Một hệ thống tốt có thể dùng:

```text
Stored procedure / service:
   validate batch
   INSERT ... SELECT staging
   UPDATE ... FROM computed
   INSERT ... SELECT audit/outbox
   COMMIT

Background worker:
   gửi event từng batch với retry/idempotency
```

Tầng thủ tục **quản lý workflow**, còn SQL **xử lý dữ liệu quan hệ theo tập**. Đó thường là sự kết hợp cân bằng.

## 24. Đối chiếu theo hệ quản trị

Mục tiêu logic là như nhau, nhưng cú pháp và giới hạn UPDATE JOIN, MERGE, RETURNING/OUTPUT, stored procedure và transaction khác nhau.

| Nhu cầu | PostgreSQL | SQL Server | MySQL 8.x | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Bulk update có join | `UPDATE ... FROM` | `UPDATE alias ... FROM ... JOIN` | `UPDATE ... JOIN ... SET` | `MERGE`/subquery/update theo phiên bản | `UPDATE ... FROM` ở phiên bản hỗ trợ |
| Bulk insert từ SELECT | `INSERT ... SELECT` | `INSERT ... SELECT` | `INSERT ... SELECT` | `INSERT ... SELECT` | `INSERT ... SELECT` |
| UPSERT/MERGE | `ON CONFLICT DO UPDATE`, `MERGE` ở phiên bản hỗ trợ | `MERGE` hoặc pattern UPSERT có kiểm soát | `ON DUPLICATE KEY UPDATE` | `MERGE` | `ON CONFLICT DO UPDATE` ở phiên bản hỗ trợ |
| Kết quả DML | `RETURNING` | `OUTPUT INSERTED/DELETED` | Hỗ trợ khác nhau; thường dùng row count | `RETURNING INTO`/cơ chế phiên bản | `RETURNING` ở phiên bản hỗ trợ |
| Tổng hợp có điều kiện | `FILTER` hoặc `CASE` | `CASE` | `CASE` | `CASE`, tính năng khác theo phiên bản | `FILTER` ở phiên bản hỗ trợ |
| Thủ tục/vòng lặp | PL/pgSQL | T-SQL | Stored programs | PL/SQL | Thường do host application điều phối |
| Xem plan | `EXPLAIN (ANALYZE, BUFFERS)` | Actual Execution Plan | `EXPLAIN`/`EXPLAIN ANALYZE` tùy phiên bản | `DBMS_XPLAN`/execution statistics | `EXPLAIN QUERY PLAN` |

Bảng là định hướng; không có nghĩa mọi phiên bản đều hỗ trợ từng cú pháp/khả năng với ngữ nghĩa giống nhau. Cần đọc tài liệu của DBMS **đang dùng** trước khi chuyển code giữa các dialect.

### 24.1. SQL Server: UPDATE FROM

Trên bảng giả định `dbo.Catalog` và `dbo.PriceStage`:

```sql
UPDATE p
SET p.CurrentPrice = s.NewPrice
FROM dbo.Catalog AS p
JOIN dbo.PriceStage AS s
  ON s.Sku = p.Sku
WHERE s.BatchId = @BatchId;
```

Đây là **T-SQL**, không phải cú pháp PostgreSQL. SQL Server có `OUTPUT INSERTED...` và `DELETED...` để ghi nhận hàng thay đổi theo cú pháp T-SQL. Nếu nguồn join có nhiều hàng một SKU, giá chọn vẫn có thể không xác định như mong muốn; hãy kiểm nguồn unique.

Với SQL Server `MERGE`, có các lưu ý về correctness/concurrency, trigger và các vấn đề phiên bản. Không mặc định MERGE là lựa chọn an toàn hơn UPDATE/INSERT riêng chỉ vì ngắn; cần thử trên phiên bản và workload thật.

### 24.2. MySQL: UPDATE JOIN

```sql
UPDATE catalog AS p
JOIN price_stage AS s
  ON s.sku = p.sku
SET p.current_price = s.new_price
WHERE s.batch_id = ?;
```

Placeholder `?` là dạng thông dụng của prepared statement qua driver. Với MySQL, storage engine như InnoDB có hỗ trợ transaction, nhưng nhiều DDL gây implicit commit; không coi ROLLBACK có thể hủy mọi loại thao tác trên mọi engine.

### 24.3. Oracle: MERGE

```sql
MERGE INTO catalog p
USING (
    SELECT sku, new_price
    FROM price_stage
    WHERE batch_id = :batch_id
) s
ON (p.sku = s.sku)
WHEN MATCHED THEN UPDATE SET
    p.current_price = s.new_price;
```

Đây là mẫu Oracle, yêu cầu nguồn có quy tắc duy nhất theo SKU. Nếu nhiều source rows khớp một target, MERGE có thể gây lỗi hoặc hành vi không mong muốn; không dùng nó để che dữ liệu staging trùng.

### 24.4. SQLite và UPDATE FROM

SQLite hiện đại có `UPDATE ... FROM` trong các phiên bản hỗ trợ, nhưng cú pháp `RETURNING`, constraints, locking và cơ chế transaction có khác biệt so với PostgreSQL. Đặc biệt, SQLite có mô hình concurrency writer khác hệ client–server. Khi ứng dụng cần cập nhật hàng loạt, SQL tập hợp vẫn có giá trị, nhưng phải đo trong ngữ cảnh engine.

### 24.5. PostgreSQL: hàm và procedure

Trong PostgreSQL, `FUNCTION` và `PROCEDURE` không hoàn toàn đồng nhất về cách gọi, transaction control và ngữ cảnh. Function PL/pgSQL thường không tự COMMIT một transaction bao ngoài tùy ý; procedure được gọi trong ngữ cảnh cho phép có các quy tắc transaction control riêng. Thiết kế stored logic nên giữ **ranh giới transaction rõ**, không đặt COMMIT trong vòng lặp từng hàng mà chưa xác định yêu cầu atomicity.

## 25. Các lỗi thường gặp khi thay row-by-row bằng set-based

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Chỉ đổi loop thành UPDATE mà không giữ WHERE | Update sai tenant/status/khách inactive | Ghi hợp đồng tập đích trước |
| UPDATE FROM có nhiều source rows cho một target | Giá trị được chọn không đáng tin | Unique/group nguồn theo khóa đích |
| JOIN order-items rồi SUM order amount | Fanout làm tăng tổng tiền | Tổng hợp item về một hàng/order |
| Dùng SUM(DISTINCT amount) để chữa fanout | Bỏ đơn có cùng amount hợp lệ | Dedup theo khóa order |
| GROUP BY sai grain | Một hàng/customer thay vì order | Xác định khóa mức chi tiết |
| INNER JOIN làm mất hàng không có con | Kết quả thiếu nhóm 0 | LEFT JOIN + xử lý NULL đúng |
| WHERE trên bảng con của LEFT JOIN | Chuyển logic thành inner-like | Đặt predicate con ở ON khi cần giữ cha |
| COUNT(*) thay COUNT(child_id) | Đếm hàng NULL-extended | Chọn biểu thức COUNT đúng |
| SUM/AVG không xét NULL | Sai số 0 và mẫu số | Quy định NULL/COALESCE rõ |
| ROUND ở từng item thay vì order | Tổng net lệch cent | Giữ đúng cấp làm tròn |
| UPDATE nhiều hàng rồi COMMIT mà không kiểm số | Thực thi không đủ/ quá nhiều | RETURNING và row count |
| Loop commit từng hàng đổi thành all-or-nothing | Ngữ nghĩa lỗi/khôi phục thay đổi | Chọn transaction/batch theo hợp đồng |
| Bulk UPDATE quá lớn | WAL/lock/replication lag tăng | Set-based từng batch |
| OFFSET trên tập đang thay đổi | Bỏ sót hàng/đếm lại | Keyset/checkpoint |
| Nhiều worker chọn cùng hàng không claim | Xử lý trùng | Lock, trạng thái, idempotency |
| Dùng SKIP LOCKED cho báo cáo nhất quán | Bỏ hàng đang khóa | Chỉ dùng cho workload kiểu queue phù hợp |
| Thay UDF có side effect thành biểu thức khác | Đổi số lần gọi/trình tự | Giữ hợp đồng side effect |
| Dùng hàm truy vấn bảng cho từng order | N+1 bên trong DB | JOIN/GROUP BY chung |
| Bỏ qua trigger row-level | Vẫn trả giá per-row và audit khác | Kiểm trigger/ORM hooks |
| Giả định UPDATE xử lý theo order_id | Phụ thuộc thứ tự không được cam kết | Window/rank hoặc thủ tục có thứ tự |
| Chạy EXPLAIN ANALYZE UPDATE trên production | Thực thi thay đổi thật | Đo test/transaction phù hợp |
| Thấy thời gian giảm là chấp nhận | Có thể sai kết quả | So sánh trước, benchmark sau |
| Dùng SQL Server/MySQL cú pháp như PostgreSQL | Lỗi cú pháp hoặc semantics | Đối chiếu dialect/version |
| Upsert nhưng không xóa summary stale | Dữ liệu cũ còn lại | Thiết kế full refresh/reconcile |
| Tính lại đơn lịch sử khi đổi giá catalog | Sai chứng từ | Phân biệt giá tại thời điểm bán |
| Bỏ kiểm số hàng và lỗi từng record | Âm thầm chấp nhận dữ liệu hỏng | Validation và reject/staging |

## 26. Bài tập thực hành theo mức độ

Các bài dùng bảng TEMP ở mục 3, có thể chạy trong cùng session PostgreSQL. Với bài sửa dữ liệu, nên bao bằng `BEGIN ... ROLLBACK` để các bài tiếp theo vẫn có dữ liệu ban đầu.

### Bài 1 — Nhận diện RBAR

Một script ứng dụng đọc 10.000 khách, với mỗi khách chạy hai câu SQL để đếm đơn và tính SUM tiền. Nếu bỏ qua query đọc danh sách, khoảng bao nhiêu câu SQL được gửi? Vì sao số round trips tăng đáng kể? Hãy viết một `GROUP BY customer_id` thay thế.

### Bài 2 — Định nghĩa tập đích

Từ dữ liệu lab, viết SELECT liệt kê order_id đủ điều kiện tính net: tenant 10, PAID, chưa processed, khách active. Kỳ vọng những ID nào? Vì sao order 105 và 108 không được xử lý?

### Bài 3 — Tổng hợp cấp order

Viết SELECT `SUM(quantity * unit_price) GROUP BY order_id`. Order 101 và 104 có gross bao nhiêu? Điều gì xảy ra với order không có item?

### Bài 4 — CASE chiết khấu

JOIN orders với customers và gross, dùng CASE tier để tính net. Đối chiếu năm giá trị 225, 114, 150, 133 và 47.50. Vì sao cần ROUND ở cấp order?

### Bài 5 — So sánh loop với set-based

Chạy khối PL/pgSQL ở mục 4 trong BEGIN/ROLLBACK. Sau đó chạy UPDATE FROM ở mục 5 với transaction khác, quan sát RETURNING. Hai cách phải trả cùng năm order và net như nhau trên dữ liệu mẫu chưa thay đổi.

### Bài 6 — EXCEPT ALL

Viết hai CTE tính net bằng subquery per-order và GROUP BY. Dùng `EXCEPT ALL` hai chiều để tìm chênh lệch. Vì sao chỉ so sánh COUNT(*) hoặc SUM(net) là chưa đủ?

### Bài 7 — Bỏ GROUP BY gây fanout

Thử SELECT order JOIN items, không UPDATE. Order 101 xuất hiện bao nhiêu hàng? Nếu trực tiếp dùng dòng item làm source UPDATE FROM, vấn đề gì xảy ra?

### Bài 8 — NULL của SUM

Xét order 106 không có item. `SUM(...)` trả gì khi không có hàng? `COALESCE(SUM(...),0)` khác thế nào? Khi nào zero-item cần coi là lỗi thay vì tổng 0?

### Bài 9 — Thay INSERT loop

Tạo bảng summary rồi `INSERT ... SELECT` từ JOIN/aggregate để sinh một hàng mỗi customer active. Làm sao giữ khách không có đơn? Phân biệt `COUNT(*)` và `COUNT(o.order_id)` sau LEFT JOIN.

### Bài 10 — UPSERT

Chạy INSERT SELECT tạo summary, rồi thử chạy lần nữa. Nếu trùng khóa, điều gì xảy ra? Viết `ON CONFLICT (tenant_id,customer_id) DO UPDATE`. Một khách sau đó inactive sẽ được tự xóa khỏi summary không?

### Bài 11 — DELETE NOT EXISTS

Viết câu DELETE để loại summary không còn khách active. Vì sao `NOT EXISTS` thường an toàn hơn `NOT IN` nếu subquery có khả năng trả NULL?

### Bài 12 — Cập nhật catalog từ staging

Tạo `demo_set_catalog` và `demo_set_price_stage`. Dùng một UPDATE FROM cho cả batch-1. Nếu staging có hai giá mới cho cùng SKU, cần làm gì trước khi cập nhật?

### Bài 13 — Window function

Viết ROW_NUMBER để lấy order mới nhất mỗi customer theo `created_at DESC, order_id DESC`. Vì sao thiếu order_id tie-breaker có thể khiến lựa chọn không ổn định?

### Bài 14 — Running total

Dùng `SUM(net_amount) OVER (PARTITION BY customer_id ORDER BY created_at, order_id ROWS...)` để tính tổng tích lũy. Khác gì với GROUP BY chỉ trả một hàng/customer?

### Bài 15 — Hàm per-row

Hãy phân tích trường hợp `calculate_net(order_id)` thực thi SELECT SUM(items) mỗi khi được gọi trong SELECT của 100.000 orders. Vì sao nó vẫn có thể là N+1 trong database dù không có vòng lặp ở application?

### Bài 16 — Batch theo khóa

Nếu có một triệu order cần cập nhật, hãy thiết kế batch theo `order_id > last_id`. Vì sao OFFSET trên tập đang thay đổi có thể bỏ sót hàng? Checkpoint cần được lưu lúc nào?

### Bài 17 — SKIP LOCKED

Hai worker cùng lấy order PAID chưa processed. `FOR UPDATE SKIP LOCKED` giúp gì? Vì sao nó không phù hợp để lấy một báo cáo tổng đơn nhất quán theo thời điểm?

### Bài 18 — Transaction và lỗi hàng

Một UPDATE tập hợp 1000 hàng có một hàng vi phạm CHECK. Điều gì có thể xảy ra với statement và transaction PostgreSQL? Nếu nghiệp vụ muốn giữ 999 hàng tốt và báo một hàng xấu, hãy đề xuất staging/reject.

### Bài 19 — Audit và outbox

Khi tính net cho nhiều đơn, yêu cầu ghi một event cho mỗi đơn thực sự thay đổi. Làm sao dùng RETURNING/staging và INSERT SELECT trong cùng transaction để audit không nhầm tập hàng?

### Bài 20 — Deadlock

Hai transaction cùng update những order giao nhau. Vì sao set-based vẫn có deadlock? Đề xuất cách giảm khả năng bằng batch nhỏ, khóa nhất quán, index và retry có giới hạn.

### Bài 21 — Hiệu năng

Giải thích vì sao một bảng 10 hàng có thể không dùng index mới, nhưng 10 triệu hàng lại có thể dùng. Khi đo EXPLAIN ANALYZE cần xem actual rows, loops, buffers, sort spill và những metric nào ngoài database?

### Bài 22 — Dialect

Viết lại UPDATE catalog từ staging cho PostgreSQL, SQL Server T-SQL, MySQL UPDATE JOIN và Oracle MERGE. Những điều kiện unique nguồn và transaction nào giữ nguyên giữa các dialect?

### Bài 23 — Quy tắc tuần tự

Một workflow yêu cầu “xử lý đơn thứ hai dựa trên tồn kho còn lại sau khi đơn thứ nhất được duyệt”. Có thể dùng một UPDATE set-based đơn giản không? Thảo luận window/recursive/ordered allocation hoặc thủ tục nếu thứ tự là một phần của quy tắc.

### Bài 24 — Side effect ngoài DB

Một vòng lặp cũ vừa UPDATE mỗi order vừa gửi email. Nếu đổi thành UPDATE set-based một lần, email được gửi ở đâu? Hãy phác thảo transactional outbox và consumer idempotent.

### Bài 25 — Bài thiết kế tổng hợp

Bạn được giao thay một stored procedure xử lý 500.000 order/ngày, hiện đang dùng cursor, commit từng order và gọi thêm một UDF đọc bảng items. Hãy trình bày:

1. Hợp đồng kết quả, tập đích, grain order và các giả thiết về khóa.
2. CTE tính gross/set-based UPDATE, kiểm uniqueness nguồn.
3. Cách xử lý order thiếu items, NULL và công thức rounding.
4. Kế hoạch đối chiếu loop với set-based trên cùng snapshot bằng keys và EXCEPT ALL.
5. Staging validation, reject và cơ chế lỗi theo batch.
6. Chia batch, checkpoint, transaction, concurrency và idempotency.
7. Outbox/audit và giới hạn side effect ngoài database.
8. EXPLAIN, chỉ mục, buffers, WAL, replication lag, latency và rollout có khả năng quay lại.

## 27. Checklist quyết định có nên dùng phép toán tập hợp

### Đúng nghiệp vụ

- [ ] Đã viết rõ **một hàng đầu ra đại diện điều gì**?
- [ ] Đã xác định tập đích: tenant, status, active, thời gian?
- [ ] Source của UPDATE JOIN có **tối đa một hàng mỗi target**?
- [ ] NULL, zero-item, duplicate, rounding, DISTINCT và OUTER JOIN đúng?
- [ ] Có phụ thuộc thứ tự từng bước hoặc side effect per-row không?
- [ ] Có so sánh hai cách trên cùng trạng thái dữ liệu?

### Đúng transaction

- [ ] Các statement bắt buộc cùng commit có chung transaction?
- [ ] Khi một hàng lỗi, muốn abort toàn batch hay cho partial success?
- [ ] Có CHECK/FK/UNIQUE và row-count validation?
- [ ] Có cơ chế tránh xử lý lại khi retry?
- [ ] Nếu nhiều worker, có lock/claim/idempotency thích hợp?

### Đủ hiệu năng

- [ ] Số SQL statements và round trips có giảm?
- [ ] Có EXPLAIN/ANALYZE trên workload đại diện?
- [ ] Có xem actual rows, loops, buffers, sort/temp spill?
- [ ] Có đo WAL, lock time, replication và ảnh hưởng workload khác?
- [ ] Một transaction có quá lớn không; có cần batch set-based?

### Dễ vận hành

- [ ] Có RETURNING/OUTPUT hoặc row counts để đối soát?
- [ ] Có ghi audit/outbox đúng những hàng đã thay đổi?
- [ ] Có checkpoint, retry và xử lý batch thất bại?
- [ ] Có công cụ rollback/correction khi đã COMMIT?
- [ ] Có thể tái hiện và bảo trì logic trên đúng DBMS/version không?

## 28. Sơ đồ lựa chọn chiến lược

```text
                   YÊU CẦU XỬ LÝ N HÀNG
                              |
                              v
                Các hàng theo cùng quy tắc?
                       /             \
                     Có              Không
                     |                 |
                     v                 v
           Xác định key và grain   Có phụ thuộc thứ tự/
           JOIN, CASE, aggregate  side effect ngoài DB?
                     |                 |
                     v                 v
           SELECT tập hợp tính thử   Procedure/workflow
                     |              + set-based từng bước
                     v
          Đối chiếu loop và set-based
          NULL, duplicate, rounding
                     |
           +---------+----------+
           |                    |
         Khác                 Tương đương
           |                    |
           v                    v
       Sửa logic          EXPLAIN / benchmark
                                |
                                v
                  Batch/transaction cần thiết?
                           /        \
                         Có          Không
                         |             |
                         v             v
                   Set-based per    Set-based trong
                   batch + commit   transaction phù hợp
                         \             /
                          v           v
                       Row counts + audit
                       + idempotency + monitor
```

## 29. Tổng kết

**Thay xử lý từng hàng bằng phép toán tập hợp khi phù hợp** là một trong những kỹ thuật quan trọng nhất để tối ưu logic trong stored procedure, hàm và ứng dụng dùng SQL. Thay vì buộc hệ thống lặp `SELECT/UPDATE` cho từng bản ghi, hãy mô tả tập đích, quy tắc JOIN, phép tổng hợp và phép cập nhật bằng `GROUP BY`, `CASE`, `UPDATE ... FROM`, `INSERT ... SELECT`, `DELETE ... EXISTS`, window functions hoặc UPSERT/MERGE theo dialect.

Hiệu quả đến từ việc **giảm nhiều statement và round trips**, đồng thời trao cho DBMS cơ hội chọn execution plan phù hợp. Tuy nhiên, truy vấn nhanh hơn chỉ hữu ích khi **giữ đúng grain, multiplicity, NULL, rounding, điều kiện lọc, quyền truy cập và transaction semantics**. Một source JOIN không duy nhất, một INNER JOIN làm mất hàng không có con, hay một thay đổi từ commit từng hàng sang all-or-nothing đều có thể làm kết quả khác đi.

Với workload rất lớn hoặc nhiều worker, giải pháp tốt có thể là **SQL tập hợp trong từng batch ngắn**, kèm khóa, checkpoint, kiểm tra số hàng, idempotency và đối soát. Với API ngoài DB, side effect, thuật toán có phụ thuộc thứ tự và xử lý lỗi riêng từng bản ghi, giữ một lớp điều phối thủ tục có thể hoàn toàn hợp lý. Kỹ năng quan trọng nhất không phải xóa hết vòng lặp, mà là **biết phần nào nên xử lý theo tập hợp, phần nào cần điều phối theo bước, và chứng minh cả tính đúng lẫn hiệu năng trên dữ liệu thực tế**.
