# Transition table và xử lý thay đổi theo tập trong PostgreSQL

Khi một câu SQL thay đổi **nhiều hàng**, trigger PostgreSQL có thể cần xử lý **toàn bộ tập hàng vừa bị tác động**, thay vì chạy một lần cho từng hàng. Ví dụ, một câu lệnh:

~~~sql
UPDATE sales
SET status = 'paid'
WHERE status = 'draft';
~~~

có thể cập nhật hàng trăm đơn bán hàng. Một trigger `FOR EACH ROW` chạy nhiều lần và nhìn từng cặp `OLD`/`NEW`. Nhưng nếu nhiệm vụ là tính **tổng chênh lệch doanh thu theo khách hàng**, cách xử lý từng hàng dễ tạo nhiều lần ghi và tăng chi phí.

PostgreSQL cung cấp **transition relations**, thường gọi là **transition tables**, để trigger truy cập một tập các hàng:

- `OLD TABLE`: hình ảnh **trước khi sửa hoặc xóa** của những hàng bị ảnh hưởng.
- `NEW TABLE`: hình ảnh **sau khi chèn hoặc cập nhật** của những hàng bị ảnh hưởng.

Ví dụ:

~~~sql
CREATE TRIGGER sales_after_update
AFTER UPDATE ON sales
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION update_sales_summary();
~~~

Trong trigger function, `old_rows` và `new_rows` có thể được truy vấn bằng SQL như một relation:

~~~sql
SELECT customer_id, SUM(amount)
FROM new_rows
WHERE status = 'paid'
GROUP BY customer_id;
~~~

Bài học **“Transition table và xử lý thay đổi theo tập”**, thuộc chương **Trigger và luật**, module **Database Engine Relational PostgreSQL**, tập trung vào bản chất của transition tables, cú pháp tạo trigger, việc xử lý INSERT/UPDATE/DELETE theo tập, bài thực hành về audit và bảng tổng hợp, hiệu năng, transaction, concurrency, các giới hạn và nguyên tắc vận hành an toàn.

> **Lưu ý:** ví dụ DDL/DML trong bài dành cho database thực hành. Các trigger tự thực thi khi dữ liệu thay đổi và có thể làm tăng công việc của mỗi statement; không bật trên bảng production khi chưa đánh giá phụ thuộc, khối lượng thay đổi, locks và khả năng rollback.

---

## 1. Vì sao trigger theo hàng không đủ cho mọi bài toán?

Một row-level trigger có thể đọc:

~~~text
Lần gọi 1: OLD của sale 1, NEW của sale 1
Lần gọi 2: OLD của sale 2, NEW của sale 2
Lần gọi 3: OLD của sale 3, NEW của sale 3
...
~~~

Nếu mỗi lần gọi cập nhật bảng tổng hợp:

~~~sql
UPDATE customer_summary
SET paid_total = paid_total + change_for_one_row
WHERE customer_id = ...;
~~~

thì một statement cập nhật 10.000 hàng có thể thực hiện rất nhiều thao tác cập nhật bảng tổng hợp, cạnh tranh locks trên cùng một customer và phát sinh WAL không cần thiết.

Transition tables cho phép một statement-level trigger xử lý:

~~~text
UPDATE ảnh hưởng 10.000 hàng
             |
             v
OLD TABLE: 10.000 hình ảnh trước
NEW TABLE: 10.000 hình ảnh sau
             |
             v
GROUP BY customer_id
             |
             v
Một phép UPSERT cho mỗi customer có delta thay đổi
~~~

Trong nhiều tác vụ **tổng hợp, đối soát, audit batch và kiểm tra theo nhóm**, kiểu xử lý theo tập dễ diễn đạt và có khả năng hiệu quả hơn.

Tuy nhiên, không có nghĩa mọi logic row-level phải chuyển sang transition tables. Một ràng buộc riêng từng hàng, chuẩn hóa giá trị trước INSERT hoặc validation đơn giản có thể phù hợp với row-level trigger hoặc table constraint hơn.

## 2. Các khái niệm cốt lõi

| Khái niệm | Ý nghĩa |
|---|---|
| Trigger | Logic tự động được kích hoạt bởi sự kiện trên bảng/view |
| Trigger function | Function, thường `RETURNS trigger`, chứa logic chạy khi trigger kích hoạt |
| `FOR EACH ROW` | Trigger được gọi theo từng hàng phù hợp |
| `FOR EACH STATEMENT` | Trigger được gọi theo một statement |
| Transition table | Tập hàng trước/sau liên quan đến một sự kiện thay đổi |
| `OLD TABLE` | Các hàng cũ của UPDATE/DELETE |
| `NEW TABLE` | Các hàng mới của INSERT/UPDATE |
| `REFERENCING` | Khai báo tên transition relations trong `CREATE TRIGGER` |
| Set-based SQL | Một phép SQL xử lý cả tập, ví dụ `GROUP BY`, `JOIN`, `INSERT ... SELECT` |

Transition tables không phải các bảng nghiệp vụ được tạo vĩnh viễn bằng `CREATE TABLE`. Chúng là **relations tạm theo phạm vi lần kích hoạt** do PostgreSQL cung cấp cho trigger.

## 3. Trước và sau trong một lệnh UPDATE

Giả sử bảng có:

| sale_id | customer_id | status | amount |
|---:|---:|---|---:|
| 10 | 101 | draft | 100.00 |
| 11 | 101 | paid | 200.00 |
| 12 | 102 | paid | 50.00 |

Câu lệnh:

~~~sql
UPDATE sales
SET status = 'paid', amount = amount + 20
WHERE sale_id IN (10, 12);
~~~

Đối với **hai hàng thực sự được UPDATE**, transition tables logic là:

**OLD TABLE**

| sale_id | customer_id | status | amount |
|---:|---:|---|---:|
| 10 | 101 | draft | 100.00 |
| 12 | 102 | paid | 50.00 |

**NEW TABLE**

| sale_id | customer_id | status | amount |
|---:|---:|---|---:|
| 10 | 101 | paid | 120.00 |
| 12 | 102 | paid | 70.00 |

Hàng `sale_id=11` không nằm trong hai transition tables vì câu UPDATE không tác động tới nó.

**Quan trọng:** transition table thể hiện những hàng liên quan đến **statement được kích hoạt**, không phải snapshot đầy đủ của toàn bảng.

## 4. Transition tables khác biến OLD và NEW

Trong một trigger `FOR EACH ROW`:

~~~sql
OLD.amount
NEW.amount
~~~

là các **bản ghi đơn** cho hàng hiện tại.

Trong trigger statement-level dùng:

~~~sql
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
~~~

thì:

~~~sql
SELECT SUM(amount) FROM old_rows;
SELECT SUM(amount) FROM new_rows;
~~~

là các **truy vấn trên tập hàng**.

Không dùng:

~~~sql
-- Sai nếu mong OLD là một bảng:
SELECT * FROM OLD;
~~~

hoặc:

~~~sql
-- Trong statement-level trigger không có OLD.amount
-- của một hàng duy nhất:
v_old_amount := OLD.amount;
~~~

Ở trigger statement-level, các biến record `OLD`/`NEW` không đại diện cho từng hàng như row-level trigger. Dùng transition relations đã đặt tên.

## 5. Một số giới hạn quan trọng

Transition relations được thiết kế cho các **AFTER triggers** phù hợp trên bảng PostgreSQL, không phải mọi trigger đều dùng được.

Các quy tắc cần nhớ:

1. Sự kiện chính là `INSERT`, `UPDATE` hoặc `DELETE`.
2. Không dùng transition tables trong `BEFORE` trigger.
3. Không dùng transition tables cho `INSTEAD OF` trigger của view.
4. Không dùng chúng với `TRUNCATE` trigger.
5. Trigger có transition relations **không được là constraint trigger**.
6. Với `UPDATE` có transition relations, không được khai báo danh sách cột kiểu `UPDATE OF column_name`.
7. Transition relations có thể được dùng ở những dạng **AFTER ROW** và **AFTER STATEMENT** đáp ứng điều kiện; xử lý cả tập thường dùng `FOR EACH STATEMENT`.
8. Với foreign tables, các giới hạn hỗ trợ trigger khác bảng thường; không mặc định transition tables dùng được như bảng local.
9. Một số hành vi với partitioning, inheritance, UPSERT và MERGE phụ thuộc cách lệnh được thực thi và phiên bản PostgreSQL.

Không suy rằng vì có `REFERENCING` thì mọi tổ hợp `CREATE TRIGGER` đều hợp lệ. Cần chọn đúng event, timing, level và loại bảng.

## 6. Cú pháp CREATE TRIGGER với REFERENCING

**INSERT:**

~~~sql
CREATE TRIGGER name_after_insert
AFTER INSERT ON schema_name.table_name
REFERENCING NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.trigger_function();
~~~

**DELETE:**

~~~sql
CREATE TRIGGER name_after_delete
AFTER DELETE ON schema_name.table_name
REFERENCING OLD TABLE AS deleted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.trigger_function();
~~~

**UPDATE:**

~~~sql
CREATE TRIGGER name_after_update
AFTER UPDATE ON schema_name.table_name
REFERENCING OLD TABLE AS deleted_rows
            NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.trigger_function();
~~~

Các tên `inserted_rows`, `deleted_rows` chỉ là **alias**. Chúng không phải tên bảng cố định hoặc từ khóa đặc biệt. Có thể dùng `old_rows` và `new_rows` để dễ nhận biết.

### 6.1. Không dùng UPDATE OF cùng transition relations

Ví dụ **không hợp lệ**:

~~~sql
-- Không chạy; minh họa tổ hợp bị cấm:
CREATE TRIGGER bad_trigger
AFTER UPDATE OF amount ON some_table
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION some_trigger_function();
~~~

Nếu cần xử lý khi cột `amount` thực sự đổi, hãy dùng `AFTER UPDATE` không liệt kê cột và lọc thay đổi trong trigger function, chẳng hạn `IS DISTINCT FROM`.

### 6.2. Tên transition relation không được xem như schema table

`old_rows`/`new_rows` là tên relation cục bộ trong ngữ cảnh trigger, không phải `public.old_rows`. Không tạo một bảng thật tên đó để “truy cập transition table”.

## 7. Thời điểm AFTER nghĩa là gì?

Một `AFTER` trigger chạy sau khi sự kiện thay đổi dữ liệu tương ứng đã diễn ra theo quy tắc PostgreSQL. Nhờ vậy, transition table `NEW TABLE` phản ánh hình ảnh **sau** những biến đổi liên quan của câu lệnh, bao gồm các kết quả đã được chấp nhận bởi quá trình thực thi.

Nhưng **AFTER không có nghĩa đã COMMIT**:

- Trigger vẫn chạy trong transaction của statement/caller.
- Trigger có thể thấy các thay đổi theo quy tắc visibility phù hợp.
- Nếu trigger báo lỗi, statement/transaction có thể bị rollback.
- Nếu caller cuối cùng ROLLBACK, dữ liệu được ghi bởi trigger cũng bị rollback.

Vì vậy ghi bảng audit bằng transition table **không phải** gửi dữ liệu ra ngoài transaction. Nó là một phần công việc transactional của PostgreSQL.

## 8. Tạo schema lab

Trong database thực hành trống:

~~~sql
CREATE SCHEMA tt_lab;

CREATE TABLE tt_lab.sales (
    sale_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'paid', 'cancelled')),
    amount NUMERIC(12, 2) NOT NULL
        CHECK (amount >= 0),
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE tt_lab.statement_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation TEXT NOT NULL
        CHECK (operation IN ('INSERT','UPDATE','DELETE')),
    affected_rows BIGINT NOT NULL CHECK (affected_rows > 0),
    paid_amount_delta NUMERIC(18, 2) NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE tt_lab.customer_summary (
    customer_id BIGINT PRIMARY KEY,
    sale_count BIGINT NOT NULL CHECK (sale_count >= 0),
    paid_total NUMERIC(18, 2) NOT NULL
        CHECK (paid_total >= 0)
);
~~~

Ý nghĩa:

- `sales` lưu dữ liệu nghiệp vụ.
- `statement_audit` lưu thống kê cho từng **statement có ảnh hưởng ít nhất một hàng**.
- `customer_summary` lưu số lượng sale rows và tổng tiền của các sale có trạng thái `paid` theo khách.

**Chưa INSERT dữ liệu `sales` vội**: ta sẽ tạo các triggers trước để mọi thay đổi trong bài đều được theo dõi nhất quán.

### 8.1. Vì sao summary chứa cả sale_count và paid_total?

Một câu UPDATE có thể:

- Thay `amount` nhưng không đổi customer.
- Thay `status` từ draft sang paid.
- Thay `customer_id`, khiến số hàng theo khách cũ giảm và khách mới tăng.
- Đổi cả customer và amount cùng lúc.

Chỉ cộng hoặc trừ amount của một hàng có thể không bao quát mọi tình huống. Ta cần **delta theo cả tập**, từ ảnh cũ và ảnh mới.

## 9. Trigger function trả RETURNS trigger

Một trigger function thường khai báo:

~~~sql
CREATE FUNCTION tt_lab.example_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- Logic trigger.
    RETURN NULL;
END;
$$;
~~~

Đối với `AFTER STATEMENT` trigger, giá trị trả về bị PostgreSQL bỏ qua trong ngữ cảnh trigger này; `RETURN NULL` là cách viết dễ hiểu.

Đừng khai báo trigger function thông thường như một function `RETURNS INTEGER` rồi kỳ vọng `EXECUTE FUNCTION` chấp nhận.

### 9.1. Metadata bên trong trigger

PL/pgSQL trigger function có thể sử dụng:

- `TG_OP`: tên operation, ví dụ `INSERT`/`UPDATE`/`DELETE`.
- `TG_LEVEL`: `ROW` hay `STATEMENT`.
- `TG_TABLE_NAME`: tên bảng kích hoạt.
- `TG_TABLE_SCHEMA`: schema.
- `TG_NAME`: tên trigger.
- `TG_ARGV`/`TG_NARGS`: arguments khai báo khi tạo trigger.

Những biến metadata giúp một function có thể phục vụ nhiều triggers với logic phân nhánh rõ ràng.

## 10. Nhật ký cấp statement: ý tưởng

Ta muốn ghi **một hàng audit cho một SQL statement có tác động dữ liệu**, gồm:

- Loại câu lệnh `INSERT`, `UPDATE` hoặc `DELETE`.
- Số sale rows bị tác động.
- Chênh lệch tổng paid amount do statement tạo ra.

Ví dụ:

~~~text
UPDATE:
  old paid_total = 250
  new paid_total = 390
  delta = +140

INSERT:
  old = 0
  new paid_total = 75
  delta = +75

DELETE:
  old paid_total = 120
  new = 0
  delta = -120
~~~

Với một statement tác động 1000 rows, chỉ cần **một lần tính tổng trên tập chuyển tiếp** thay vì INSERT 1000 audit rows nếu yêu cầu chỉ là audit dạng tổng hợp.

## 11. Tạo function audit theo tập

~~~sql
CREATE FUNCTION tt_lab.audit_sales_statement()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows BIGINT := 0;
    v_paid_delta NUMERIC(18, 2) := 0;
BEGIN
    IF TG_OP = 'INSERT' THEN
        SELECT
            COUNT(*),
            COALESCE(
                SUM(amount) FILTER (WHERE status = 'paid'),
                0::NUMERIC
            )
        INTO v_rows, v_paid_delta
        FROM new_rows;

    ELSIF TG_OP = 'DELETE' THEN
        SELECT
            COUNT(*),
            -COALESCE(
                SUM(amount) FILTER (WHERE status = 'paid'),
                0::NUMERIC
            )
        INTO v_rows, v_paid_delta
        FROM old_rows;

    ELSIF TG_OP = 'UPDATE' THEN
        SELECT
            COUNT(*),
            COALESCE(
                SUM(amount) FILTER (WHERE status = 'paid'),
                0::NUMERIC
            )
        INTO v_rows, v_paid_delta
        FROM new_rows;

        SELECT
            v_paid_delta - COALESCE(
                SUM(amount) FILTER (WHERE status = 'paid'),
                0::NUMERIC
            )
        INTO v_paid_delta
        FROM old_rows;
    END IF;

    IF v_rows > 0 THEN
        INSERT INTO tt_lab.statement_audit (
            operation,
            affected_rows,
            paid_amount_delta
        )
        VALUES (TG_OP, v_rows, v_paid_delta);
    END IF;

    RETURN NULL;
END;
$$;
~~~

### 11.1. Vì sao dùng FILTER?

`SUM(amount) FILTER (WHERE status='paid')` chỉ tính những sale rows đã thanh toán. `COUNT(*)` đếm **mọi** sale rows bị tác động, kể cả draft/cancelled.

### 11.2. Vì sao COALESCE?

`SUM` trên một tập rỗng hoặc không có row phù hợp trả SQL NULL. `COALESCE(..., 0::NUMERIC)` biến nó thành 0 cho phép tính delta.

### 11.3. Điều kiện v_rows > 0 để làm gì?

PostgreSQL có thể kích hoạt `FOR EACH STATEMENT` trigger ngay cả khi câu DML không tác động hàng nào. Quy tắc lab là **chỉ ghi audit khi có ít nhất một hàng**, nên function bỏ qua tập rỗng.

### 11.4. Dùng một function cho ba sự kiện được không?

Được, với ba trigger riêng và các alias transition relations nhất quán. PL/pgSQL thực thi nhánh ứng với `TG_OP`, nên chỉ truy vấn transition relations tồn tại cho event tương ứng.

## 12. Gắn ba AFTER STATEMENT triggers

~~~sql
CREATE TRIGGER sales_stmt_audit_insert
AFTER INSERT ON tt_lab.sales
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.audit_sales_statement();

CREATE TRIGGER sales_stmt_audit_delete
AFTER DELETE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.audit_sales_statement();

CREATE TRIGGER sales_stmt_audit_update
AFTER UPDATE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.audit_sales_statement();
~~~

Ba triggers dùng cùng function nhưng mỗi event có **transition relation đúng với loại thay đổi**.

### 12.1. Một trigger AFTER UPDATE có cả OLD TABLE và NEW TABLE

Đây là cấu trúc quan trọng nhất khi cần tính **net delta**:

~~~text
UPDATE statement
       |
       +--> old_rows: before images
       |
       +--> new_rows: after images
       |
       +--> SUM(new paid) - SUM(old paid)
~~~

Không phải JOIN từng hàng old/new mới tính được tổng chênh lệch. Khi chỉ cần tổng theo nhóm, aggregate cũ/mới độc lập thường rõ và xử lý cả key thay đổi.

## 13. Tại sao cần thêm bảng tổng hợp?

Giả sử API thường hỏi:

~~~sql
SELECT
    customer_id,
    COUNT(*) AS sale_count,
    COALESCE(
        SUM(amount) FILTER (WHERE status='paid'),
        0
    ) AS paid_total
FROM tt_lab.sales
GROUP BY customer_id;
~~~

Query trực tiếp này là **nguồn sự thật**, dễ kiểm chứng và thường là lựa chọn mặc định tốt nếu dữ liệu/khối lượng truy vấn không lớn.

Nhưng nếu bảng rất lớn và hệ thống cần tra tổng theo khách liên tục, có thể lưu một **bảng tổng hợp được cập nhật tăng dần**:

~~~text
sales (source of truth)
     |
     v
Transition tables
     |
     v
GROUP BY customer_id trên phần thay đổi
     |
     v
customer_summary
~~~

Đây là một cơ chế **incremental maintenance** viết bằng trigger, không phải materialized view tự động refresh.

### 13.1. Đừng tạo summary trigger trước khi hiểu cost

Bảng tổng hợp có chi phí ghi bổ sung, contention và rủi ro logic sai. Nếu một query GROUP BY trực tiếp đủ nhanh, không nên tạo hạ tầng trigger phức tạp chỉ vì có thể làm được.

## 14. Tính delta cho INSERT

Với INSERT, mỗi hàng mới làm:

- `sale_count` của customer tăng 1.
- `paid_total` tăng `amount` nếu `status='paid'`, còn không tăng 0.

Theo tập:

~~~sql
SELECT
    customer_id,
    COUNT(*)::BIGINT AS sale_delta,
    COALESCE(
        SUM(amount) FILTER (WHERE status = 'paid'),
        0::NUMERIC
    ) AS paid_delta
FROM new_rows
GROUP BY customer_id;
~~~

Sau đó UPSERT các delta theo customer_id.

Quan trọng: **GROUP BY trước khi ON CONFLICT**. Nếu một statement INSERT có nhiều rows cùng customer_id và ta đưa từng hàng thẳng vào UPSERT, một target row có thể bị cố UPDATE nhiều lần trong một statement, gây lỗi hoặc semantics không mong muốn. Aggregate trước khiến mỗi customer chỉ xuất hiện một lần.

## 15. Tính delta cho DELETE

Với DELETE, những hàng cũ bị bỏ đi:

~~~sql
SELECT
    customer_id,
    -COUNT(*)::BIGINT AS sale_delta,
    -COALESCE(
        SUM(amount) FILTER (WHERE status = 'paid'),
        0::NUMERIC
    ) AS paid_delta
FROM old_rows
GROUP BY customer_id;
~~~

Khi áp dụng vào bảng tổng hợp, các delta có dấu âm sẽ trừ giá trị đang lưu.

Nếu một DELETE cố làm bảng tổng hợp âm do dữ liệu bị lệch, `CHECK` ở `customer_summary` có thể chặn transaction. Đây là tín hiệu phải kiểm tra tính nhất quán nguồn/summary, không nên âm thầm bỏ constraint để “làm cho DELETE chạy được”.

## 16. Tính delta cho UPDATE

UPDATE có cả trước và sau:

~~~text
delta(customer)
  = contribution(NEW rows theo customer)
  - contribution(OLD rows theo customer)
~~~

Ví dụ một sale:

~~~text
OLD: customer 101, paid, amount=100
NEW: customer 102, paid, amount=150
~~~

Kết quả:

| customer_id | sale_count_delta | paid_total_delta |
|---:|---:|---:|
| 101 | -1 | -100 |
| 102 | +1 | +150 |

Nếu chỉ tính `NEW.amount - OLD.amount = 50` cho một customer, ta sẽ **bỏ sót việc chuyển sale giữa hai khách**.

Cách an toàn: aggregate hai tập riêng, nối bằng `UNION ALL`, sau đó `GROUP BY customer_id` một lần nữa để lấy net delta.

## 17. Tạo trigger function duy trì customer_summary

~~~sql
CREATE FUNCTION tt_lab.maintain_customer_summary()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN

        INSERT INTO tt_lab.customer_summary AS s (
            customer_id, sale_count, paid_total
        )
        SELECT
            customer_id,
            COUNT(*)::BIGINT,
            COALESCE(
                SUM(amount) FILTER (WHERE status='paid'),
                0::NUMERIC
            )
        FROM new_rows
        GROUP BY customer_id
        ON CONFLICT (customer_id) DO UPDATE
        SET sale_count = s.sale_count + EXCLUDED.sale_count,
            paid_total = s.paid_total + EXCLUDED.paid_total;

    ELSIF TG_OP = 'DELETE' THEN

        INSERT INTO tt_lab.customer_summary AS s (
            customer_id, sale_count, paid_total
        )
        SELECT
            customer_id,
            -COUNT(*)::BIGINT,
            -COALESCE(
                SUM(amount) FILTER (WHERE status='paid'),
                0::NUMERIC
            )
        FROM old_rows
        GROUP BY customer_id
        ON CONFLICT (customer_id) DO UPDATE
        SET sale_count = s.sale_count + EXCLUDED.sale_count,
            paid_total = s.paid_total + EXCLUDED.paid_total;

    ELSIF TG_OP = 'UPDATE' THEN

        WITH contributions AS (
            SELECT
                customer_id,
                COUNT(*)::BIGINT AS sale_delta,
                COALESCE(
                    SUM(amount) FILTER (WHERE status='paid'),
                    0::NUMERIC
                ) AS paid_delta
            FROM new_rows
            GROUP BY customer_id

            UNION ALL

            SELECT
                customer_id,
                -COUNT(*)::BIGINT AS sale_delta,
                -COALESCE(
                    SUM(amount) FILTER (WHERE status='paid'),
                    0::NUMERIC
                ) AS paid_delta
            FROM old_rows
            GROUP BY customer_id
        ),
        net AS (
            SELECT
                customer_id,
                SUM(sale_delta)::BIGINT AS sale_delta,
                SUM(paid_delta) AS paid_delta
            FROM contributions
            GROUP BY customer_id
        )
        INSERT INTO tt_lab.customer_summary AS s (
            customer_id, sale_count, paid_total
        )
        SELECT
            customer_id,
            sale_delta,
            paid_delta
        FROM net
        WHERE sale_delta <> 0
           OR paid_delta <> 0
        ON CONFLICT (customer_id) DO UPDATE
        SET sale_count = s.sale_count + EXCLUDED.sale_count,
            paid_total = s.paid_total + EXCLUDED.paid_total;

    END IF;

    RETURN NULL;
END;
$$;
~~~

**Đây là một chức năng minh họa đầy đủ ba event.** Function cố ý dùng các tên `old_rows` và `new_rows` nhất quán; với trigger event tương ứng, PostgreSQL cung cấp đúng relation đó trong phạm vi function.

### 17.1. Vì sao UPDATE cần tổng hợp hai lần?

`contributions` chứa delta dương của NEW và âm của OLD. `net` gom các đóng góp có cùng customer_id để tránh upsert một target row nhiều lần.

### 17.2. Vì sao lọc net = 0?

UPDATE có thể chỉ đổi `updated_at`, không đổi customer_id/status/amount. Không cần ghi bảng summary nếu delta theo cả hai metric bằng 0. Điều kiện lọc giúp giảm UPDATE vô ích cho những event như vậy.

### 17.3. Bảng summary có thể giữ hàng bằng 0

Khi xóa sale cuối của một khách, `sale_count=0` và `paid_total=0` vẫn có thể tồn tại. Đây là lựa chọn mô hình dữ liệu có chủ đích; nếu cần xóa summary rows bằng 0, phải thiết kế chính sách phù hợp với concurrency và báo cáo lịch sử.

### 17.4. Điều kiện tiên quyết: summary đã đồng bộ

Cơ chế delta giả định `customer_summary` đã đúng với `sales` trước khi bắt đầu bảo trì tăng dần. Nếu có dữ liệu nguồn tồn tại nhưng summary rỗng, DELETE/UPDATE có thể khiến delta âm và bị CHECK từ chối. Cần xây baseline nhất quán rồi mới dùng incremental maintenance.

## 18. Gắn triggers tổng hợp

~~~sql
CREATE TRIGGER sales_summary_insert
AFTER INSERT ON tt_lab.sales
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.maintain_customer_summary();

CREATE TRIGGER sales_summary_delete
AFTER DELETE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.maintain_customer_summary();

CREATE TRIGGER sales_summary_update
AFTER UPDATE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.maintain_customer_summary();
~~~

Mỗi event của bảng nguồn giờ có hai AFTER STATEMENT triggers:

1. Ghi `statement_audit`.
2. Duy trì `customer_summary`.

Các trigger cùng loại event thường được kích hoạt theo thứ tự tên trigger theo quy tắc PostgreSQL. **Không dựa vào thứ tự đó để che dependencies chức năng**; thiết kế sao cho logic audit và summary hoạt động độc lập khi có thể.

## 19. INSERT nhiều hàng và quan sát hai bảng đích

Chỉ **sau khi tạo triggers**, chèn dữ liệu mẫu:

~~~sql
INSERT INTO tt_lab.sales (
    sale_id, customer_id, status, amount
)
VALUES
    (10, 101, 'draft', 100.00),
    (11, 101, 'paid', 200.00),
    (12, 102, 'paid', 50.00),
    (13, 102, 'cancelled', 60.00),
    (14, 103, 'paid', 75.00);
~~~

Đây là **một INSERT statement với 5 rows**, không phải 5 statements riêng biệt.

Xem tổng hợp:

~~~sql
SELECT *
FROM tt_lab.customer_summary
ORDER BY customer_id;
~~~

Kỳ vọng:

| customer_id | sale_count | paid_total |
|---:|---:|---:|
| 101 | 2 | 200.00 |
| 102 | 2 | 50.00 |
| 103 | 1 | 75.00 |

Và audit:

~~~sql
SELECT operation, affected_rows, paid_amount_delta
FROM tt_lab.statement_audit
ORDER BY audit_id;
~~~

Kỳ vọng có **một audit row** cho INSERT 5 sale rows, với paid delta:

\[
200 + 50 + 75 = 325
\]

### 19.1. Tại sao chỉ có một audit row?

Vì trigger khai báo `FOR EACH STATEMENT` và function ghi một audit row sau khi lấy aggregate của toàn bộ transition relation.

### 19.2. Nếu dùng FOR EACH ROW thì sao?

Một trigger riêng từng hàng có thể ghi 5 audit rows. Điều này không tự sai; nó phục vụ mục tiêu **chi tiết từng hàng** khác với audit tổng hợp theo statement.

## 20. UPDATE nhiều hàng: quan sát OLD/NEW delta

~~~sql
UPDATE tt_lab.sales
SET
    amount = amount + 20,
    status = 'paid',
    updated_at = statement_timestamp()
WHERE sale_id IN (10, 12);
~~~

Hệ quả:

- Sale 10: draft 100 → paid 120, đóng góp paid tăng 120.
- Sale 12: paid 50 → paid 70, đóng góp paid tăng 20.
- Tổng paid delta: +140.
- Số sale rows theo customer không đổi.

Xem:

~~~sql
SELECT *
FROM tt_lab.customer_summary
ORDER BY customer_id;
~~~

Kỳ vọng:

| customer_id | sale_count | paid_total |
|---:|---:|---:|
| 101 | 2 | 320.00 |
| 102 | 2 | 70.00 |
| 103 | 1 | 75.00 |

Audit ghi một sự kiện UPDATE với `affected_rows=2` và `paid_amount_delta=140.00`.

## 21. UPDATE chuyển một sale sang customer khác

~~~sql
UPDATE tt_lab.sales
SET customer_id = 103,
    updated_at = statement_timestamp()
WHERE sale_id = 11;
~~~

Sale 11 hiện có `status='paid'` và `amount=200`.

Kết quả net:

| customer_id | sale_count_delta | paid_total_delta |
|---:|---:|---:|
| 101 | -1 | -200 |
| 103 | +1 | +200 |

Bảng summary trở thành:

| customer_id | sale_count | paid_total |
|---:|---:|---:|
| 101 | 1 | 120.00 |
| 102 | 2 | 70.00 |
| 103 | 2 | 275.00 |

Một trigger dùng `NEW.customer_id` rồi cộng chênh lệch amount bằng 0 sẽ **sai** trong tình huống chuyển khóa nhóm. Chính vì thế cần tách OLD và NEW contributions.

### 21.1. Statement audit có delta tổng = 0

Ở event này, **tổng paid amount toàn bảng không đổi**, nên `paid_amount_delta=0` trong audit cấp statement. Tuy nhiên, hai customer summaries có thay đổi.

Một con số tổng audit không thay thế báo cáo chi tiết về thay đổi phân phối giữa các nhóm.

## 22. DELETE nhiều hàng

~~~sql
DELETE FROM tt_lab.sales
WHERE sale_id IN (12, 13);
~~~

- Sale 12: customer 102, paid 70 → trừ 70 paid.
- Sale 13: customer 102, cancelled 60 → không đóng góp paid.
- Sale count của customer 102 giảm 2.

Summary của customer 102 trở thành `sale_count=0`, `paid_total=0`.

Audit cấp statement ghi:

- `operation='DELETE'`.
- `affected_rows=2`.
- `paid_amount_delta=-70.00`.

### 22.1. DELETE không cần NEW TABLE

DELETE không tạo ảnh hàng mới trong bảng nguồn. Chỉ dùng `OLD TABLE`.

### 22.2. INSERT không cần OLD TABLE

INSERT không có ảnh hàng cũ của hàng được tạo. Chỉ dùng `NEW TABLE`.

### 22.3. UPDATE có cả hai

UPDATE cần cả OLD/NEW nếu phải so sánh trạng thái hoặc tính chênh lệch.

## 23. Một statement không tác động hàng nào

~~~sql
UPDATE tt_lab.sales
SET amount = amount + 1
WHERE sale_id = -999;
~~~

`AFTER STATEMENT` trigger vẫn có thể được gọi theo event dù **0 rows** phù hợp điều kiện. Khi đó transition table tương ứng rỗng.

Trong lab:

- `audit_sales_statement` chỉ INSERT audit nếu `v_rows>0`.
- `maintain_customer_summary` không có grouped delta nào để UPSERT.
- Không có thay đổi ở bảng summary.

Vì vậy một statement-level trigger **không có nghĩa** một audit row chắc chắn được ghi. Việc ghi hay không phụ thuộc logic trigger.

### 23.1. COUNT(*) và SUM khác nhau trên tập rỗng

~~~sql
SELECT
    COUNT(*) AS row_count,
    SUM(amount) AS total
FROM new_rows;
~~~

Trên transition relation rỗng, `COUNT(*)=0`, còn `SUM(amount)` là SQL NULL. Dùng `COALESCE` nếu yêu cầu số 0.

## 24. Update chạm hàng nhưng giá trị không đổi

~~~sql
UPDATE tt_lab.sales
SET amount = amount
WHERE sale_id = 10;
~~~

Statement vẫn là một UPDATE tác động một hàng theo điều kiện.

- Transition relations có thể chứa trước/sau tương ứng.
- `affected_rows` là 1, không tự bằng 0 vì amount không thay.
- Net delta của paid_total và sale_count là 0.
- Audit cấp statement trong lab có thể ghi UPDATE với delta 0.
- Summary function có điều kiện lọc net delta, nên không UPDATE summary một cách vô ích.

**“Hàng bị UPDATE”** và **“giá trị business thật sự khác nhau”** là hai khái niệm khác.

## 25. So sánh old/new bằng IS DISTINCT FROM

Khi cần biết một field đã đổi thực sự:

~~~sql
SELECT
    o.sale_id,
    o.status AS old_status,
    n.status AS new_status
FROM old_rows AS o
JOIN new_rows AS n
    ON n.sale_id = o.sale_id
WHERE o.status IS DISTINCT FROM n.status;
~~~

`IS DISTINCT FROM` là phép so sánh có semantics rõ với SQL NULL, khác `<>` vốn có thể cho kết quả NULL nếu một phía NULL.

### 25.1. Kết hợp nhiều trường

~~~sql
WHERE ROW(
    o.customer_id,
    o.status,
    o.amount
) IS DISTINCT FROM ROW(
    n.customer_id,
    n.status,
    n.amount
)
~~~

Dùng khi chỉ muốn audit những thay đổi business đáng kể, bỏ qua sự thay đổi của `updated_at`.

### 25.2. Điều kiện để JOIN từng cặp OLD/NEW đúng

JOIN trên `sale_id` giả định **khóa này không đổi trong UPDATE**. Nếu một UPDATE thay cả khóa dùng để ghép cặp, JOIN cũ/mới theo khóa có thể không tìm thấy cặp tương ứng.

Với việc cần audit từng hàng và cho phép đổi primary key, phải xác định **identity ổn định** hoặc chọn cơ chế khác như row-level trigger; không suy rằng transition tables tự chứa một mã liên kết ẩn giữa hai tập old/new.

## 26. Audit từng hàng bằng transition tables

Transition tables không chỉ dùng cho aggregate. Có thể dùng set-based `INSERT ... SELECT` tạo nhiều bản ghi chi tiết trong **một statement**.

Tạo bảng audit JSONB:

~~~sql
CREATE TABLE tt_lab.sale_change_audit (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_id BIGINT NOT NULL,
    before_row JSONB,
    after_row JSONB,
    recorded_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);
~~~

Tạo function dành riêng cho UPDATE với giả định sale_id không thay đổi:

~~~sql
CREATE FUNCTION tt_lab.audit_sale_row_changes()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO tt_lab.sale_change_audit (
        sale_id, before_row, after_row
    )
    SELECT
        n.sale_id,
        to_jsonb(o),
        to_jsonb(n)
    FROM old_rows AS o
    JOIN new_rows AS n
        ON n.sale_id = o.sale_id
    WHERE ROW(o.customer_id, o.status, o.amount)
          IS DISTINCT FROM
          ROW(n.customer_id, n.status, n.amount);

    RETURN NULL;
END;
$$;

CREATE TRIGGER sales_row_audit_update
AFTER UPDATE ON tt_lab.sales
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION tt_lab.audit_sale_row_changes();
~~~

Mặc dù kết quả audit có thể có **một row mỗi sale thực sự đổi**, trigger function chỉ được gọi **một lần cho statement**.

### 26.1. Không chứa dữ liệu nhạy cảm tùy tiện trong audit JSONB

`to_jsonb(o)`/`to_jsonb(n)` ghi tất cả các cột đã chọn từ row. Trong production, không nên tự ghi PII, token, secrets hoặc payload lớn vào audit. Có thể dùng `jsonb_build_object` để whitelist fields và có retention/access policies.

## 27. Không JOIN OLD/NEW nếu chỉ cần tổng delta

Để cập nhật bảng tổng hợp theo customer, ta không cần xác định từng cặp sale old/new.

Tính:

~~~sql
SELECT customer_id, COUNT(*), SUM(amount)
FROM new_rows
GROUP BY customer_id;
~~~

và:

~~~sql
SELECT customer_id, COUNT(*), SUM(amount)
FROM old_rows
GROUP BY customer_id;
~~~

rồi ghép các contributions bằng `UNION ALL`. Cách này vẫn chính xác nếu `customer_id` thay đổi, miễn mỗi đóng góp trước/sau được tính đúng.

**Nguyên tắc:** nếu bài toán là **net delta của tập**, hãy làm việc với old-set và new-set như hai relations; chỉ JOIN từng hàng khi nghiệp vụ cần mapping old/new theo identity.

## 28. Transition table và AFTER ROW trigger

Một `AFTER ROW` trigger đủ điều kiện cũng có thể khai báo transition relations, bên cạnh `OLD`/`NEW` của riêng hàng đang kích hoạt.

Tuy nhiên, nếu nó được gọi N lần cho N hàng và mỗi lần lại scan toàn bộ transition table, công việc có thể trở thành xấp xỉ N lần scan tập N hàng, rất tốn kém.

Khi mục tiêu là aggregate trên cả statement:

~~~sql
FOR EACH STATEMENT
~~~

thường là lựa chọn hợp lý hơn.

### 28.1. Khi AFTER ROW phù hợp

- Cần hành động theo identity một hàng.
- Cần dùng `OLD`/`NEW` cho điều kiện hoặc dữ liệu riêng.
- Không cần aggregate toàn bộ tập.
- Một constraint hoặc audit row-level được thiết kế có chủ đích.

Không chuyển tất cả triggers sang statement-level chỉ vì nghe “set-based luôn nhanh”.

## 29. BEFORE ROW trigger và dữ liệu NEW TABLE

`BEFORE ROW` trigger có thể:

- Thay đổi các giá trị ở `NEW`.
- Từ chối/skip một hàng theo semantics trigger.
- Áp logic chuẩn hóa trước khi INSERT/UPDATE.

Transition `NEW TABLE` của một AFTER trigger phản ánh **các hàng sau xử lý statement tương ứng**, không phải chỉ văn bản giá trị được gửi ban đầu từ client.

Ví dụ: nếu BEFORE INSERT trigger biến status đầu vào từ `'PAID'` thành `'paid'` hợp lệ, AFTER INSERT transition table dùng giá trị đã được chấp nhận trong hàng mới.

### 29.1. Không dùng transition tables để thay thế BEFORE validation

Transition tables chỉ có ở AFTER trigger phù hợp. Nếu yêu cầu sửa/từ chối một giá trị trước khi lưu, table constraints hoặc BEFORE ROW trigger có thể đúng vị trí hơn.

## 30. Constraint triggers khác transition-table triggers

**Constraint trigger** có các đặc điểm riêng về thời điểm kiểm tra và khả năng deferrable trong những ngữ cảnh PostgreSQL hỗ trợ.

Transition relations **không dùng trong constraint trigger**. Vì vậy nếu cần quy tắc phải hoãn tới transaction end bằng một cơ chế constraint trigger, không thể đơn giản thêm `REFERENCING OLD TABLE/NEW TABLE` vào constraint trigger đó.

Nếu cần kiểm tra bất biến xuyên nhiều hàng:

- Ưu tiên thiết kế constraint/unique/exclusion/FK nếu có thể.
- Xem xét statement-level AFTER trigger với transition table khi việc kiểm tra ngay sau statement là phù hợp.
- Thiết kế transaction isolation/locking rõ để tránh race conditions.
- Không mặc định kiểm tra aggregate ở READ COMMITTED tự trở thành một constraint toàn cục an toàn với concurrency.

## 31. Transition table không dùng cho TRUNCATE

`TRUNCATE` là sự kiện khác `DELETE`:

~~~sql
TRUNCATE TABLE tt_lab.sales;
~~~

Nó không được xử lý bằng `AFTER DELETE ... REFERENCING OLD TABLE` như một DELETE từng hàng, và transition tables không dùng với TRUNCATE.

**Không chạy TRUNCATE trên lab** nếu muốn giữ dữ liệu/trạng thái triggers trong những bước sau.

### 31.1. Nếu summary phụ thuộc nguồn, TRUNCATE là nguy cơ

Nếu một ứng dụng có quyền TRUNCATE bảng nguồn nhưng summary chỉ được bảo trì qua INSERT/UPDATE/DELETE transition triggers, bảng tổng hợp có thể bị lệch.

Giải pháp tùy hệ thống:

- Hạn chế quyền TRUNCATE.
- Dùng quy trình reset cả nguồn và summary trong transaction an toàn.
- Có statement-level TRUNCATE trigger riêng để xử lý theo chính sách.
- Tái tạo summary từ nguồn sau bulk operations theo kế hoạch.

Không dùng giả định “mọi dạng xóa bảng đều qua DELETE trigger”.

## 32. Cẩn thận với INSERT ... ON CONFLICT DO UPDATE

Lệnh UPSERT:

~~~sql
INSERT INTO tt_lab.sales (
    sale_id, customer_id, status, amount
)
VALUES
    (10, 101, 'paid', 130.00),
    (20, 104, 'paid', 45.00)
ON CONFLICT (sale_id) DO UPDATE
SET
    customer_id = EXCLUDED.customer_id,
    status = EXCLUDED.status,
    amount = EXCLUDED.amount,
    updated_at = statement_timestamp();
~~~

Trong một statement:

- Hàng `sale_id=20` có thể được INSERT.
- Hàng `sale_id=10` có thể đi qua nhánh UPDATE nếu đã tồn tại.

PostgreSQL có các quy tắc kích hoạt statement-level INSERT/UPDATE triggers cho `INSERT ... ON CONFLICT DO UPDATE`. Do đó không giả định chỉ có một loại event trong logic audit/summary của toàn câu lệnh.

**Transition tables của từng event phản ánh tập hàng tương ứng event đó**; summary cần ghi nhận cả inserts lẫn updates khi cả hai thực sự xảy ra.

### 32.1. Chỉ ghi một audit row cho toàn bộ SQL text?

Ba triggers ở lab ghi audit theo **event**, không nhất thiết đúng một row cho toàn bộ lệnh SQL UPSERT khi có nhiều nhánh event. Nếu contract audit cần một correlation ID và một row cho toàn bộ request, phải thiết kế aggregation/correlation ở cấp phù hợp; transition tables riêng theo event không tự hợp nhất thành một object duy nhất.

### 32.2. Zero-row UPDATE event

Một event-level statement trigger có thể chạy với transition relation rỗng. Trong lab, `v_rows>0` tránh ghi audit 0 rows.

## 33. MERGE và transition relations

PostgreSQL hỗ trợ `MERGE` trong các phiên bản hiện đại, với các nhánh INSERT/UPDATE/DELETE tùy điều kiện.

Khi dùng triggers:

- Xác định phiên bản PostgreSQL đang chạy.
- Phân biệt những row thực sự được INSERT, UPDATE, DELETE.
- Hiểu rằng các statement-level triggers của các event liên quan có quy tắc kích hoạt riêng.
- Không giả định một MERGE tạo đúng một transition table chung gồm mọi hành động.

Với bài toán summary, kiến trúc delta theo **từng event** có thể áp dụng khi trigger event đó được PostgreSQL kích hoạt hợp lệ. Nhưng trước khi dùng trong production, cần thử trên cùng phiên bản server và dữ liệu đặc trưng cho các nhánh MERGE.

### 33.1. Đừng dựa trên cú pháp MERGE của hệ DB khác

SQL Server, Oracle và PostgreSQL có chi tiết trigger/MERGE khác nhau. Không suy ra trigger transition behavior của PostgreSQL chỉ từ kinh nghiệm hệ khác.

## 34. Partitioned tables và transition relations

Bảng partitioned đưa thêm nhiều yếu tố:

- Statement được nhắm vào parent table hay một partition cụ thể?
- Row-level triggers có thể được áp dụng trên các partitions theo cơ chế PostgreSQL.
- Statement-level triggers thường gắn với quan hệ được chỉ định trong statement.
- Transition relations có thể tổng hợp hàng từ những partitions bị tác động trong những trường hợp PostgreSQL hỗ trợ.
- Di chuyển hàng giữa partitions do UPDATE có thể có chi tiết row-level trigger khác với trực giác “chỉ UPDATE”.

Không viết business logic dựa trên giả định “mọi partition đều có một statement trigger giống nhau”. Với bảng partitioned, xác minh trên phiên bản PostgreSQL mục tiêu và thử INSERT/UPDATE/DELETE cả trực tiếp vào partition lẫn qua parent khi mô hình cho phép.

### 34.1. UPDATE chuyển partition cần thận trọng

Nếu thay partition key làm row di chuyển giữa partitions, PostgreSQL có thể dùng hành vi DELETE/INSERT ở mức row triggers nhưng vẫn liên quan một UPDATE ở mức statement. Cần kiểm tra transition relations và nguồn trigger tại parent/partition để tránh **tính delta hai lần**.

## 35. Inheritance và bảng con

PostgreSQL hỗ trợ table inheritance và partitioning, nhưng chúng không đồng nhất về mọi quy tắc trigger và schema.

Khi UPDATE một bảng cha có bao gồm các hàng của bảng con, phạm vi statement trigger và transition relations phụ thuộc vào quan hệ target và cách PostgreSQL thực thi lệnh. Không mặc định trigger trên cha luôn tương đương trigger được tạo riêng trên từng bảng con.

Một thiết kế tổng hợp nhiều bảng phải rõ:

- Source of truth gồm những bảng nào?
- Statement có thể chạy trực tiếp trên child không?
- Trigger cần đặt ở đâu?
- Có nguy cơ bỏ sót hoặc đếm lặp sự kiện?

## 36. Foreign tables và remote changes

Foreign tables dùng FDW để đại diện dữ liệu ngoài PostgreSQL server hoặc ở nguồn khác. Quy tắc hỗ trợ triggers/transition tables khác regular local tables.

Không coi `REFERENCING OLD TABLE/NEW TABLE` là cơ chế CDC tổng quát cho mọi nguồn từ xa. Nếu cần đồng bộ remote changes, có thể xem:

- FDW features đúng với adapter/version.
- Logical decoding/CDC ở nguồn phù hợp.
- Ingestion pipeline với event identifiers.
- Transaction/outbox patterns.

Transition tables của regular table phục vụ một statement PostgreSQL, **không tự giám sát mọi thay đổi bên ngoài**.

## 37. Transition table không phải logical replication stream

Một transition table:

- Tồn tại trong ngữ cảnh trigger đang chạy.
- Chỉ biểu diễn những rows thuộc event/statement liên quan.
- Không phải một bảng tồn tại giữa các sessions.
- Không thay WAL-based logical decoding.
- Không tự lưu một lịch sử bền vững sau statement.

Nếu cần truy vết dài hạn, trigger phải **ghi dữ liệu chọn lọc** vào bảng audit hoặc hệ thống outbox trong transaction.

Nếu cần CDC xuyên nhiều databases/services, logical replication/CDC và application idempotency có thể phù hợp hơn.

## 38. Chuyển đổi từ row-by-row trigger sang statement-level

Giả sử row-level trigger cũ thực hiện:

~~~text
Mỗi UPDATE sale:
    đọc OLD/NEW
    tính delta
    UPDATE customer_summary
~~~

Khi chuyển sang transition table:

~~~text
Một UPDATE nhiều sales:
    old_rows/new_rows
    GROUP BY customer_id
    tính net delta
    UPSERT customer_summary theo tập
~~~

Các bước migration:

1. Hiểu chính xác semantics trigger cũ.
2. Kiểm kê các loại statement có thể tác động nguồn.
3. Tạo hàm mới và test ở database riêng.
4. Đối chiếu summary với `GROUP BY` trực tiếp.
5. Bảo đảm không bật song song hai hệ trigger cùng cộng delta.
6. Triển khai trong transaction DDL phù hợp.
7. Theo dõi sai lệch, contention và regression.

### 38.1. Nguy cơ double-count trong migration

Nếu row-level trigger cũ và statement-level transition trigger mới cùng hoạt động, một INSERT có thể bị cộng vào summary **hai lần**.

Phải có cutover rõ ràng, không chỉ thêm trigger rồi “để đó quan sát” trên cùng summary production.

## 39. Đối soát summary với nguồn sự thật

Sau các INSERT/UPDATE/DELETE ở lab:

~~~sql
WITH expected AS (
    SELECT
        customer_id,
        COUNT(*)::BIGINT AS sale_count,
        COALESCE(
            SUM(amount) FILTER (WHERE status = 'paid'),
            0::NUMERIC
        ) AS paid_total
    FROM tt_lab.sales
    GROUP BY customer_id
)
SELECT
    COALESCE(e.customer_id, s.customer_id)
        AS customer_id,
    e.sale_count AS expected_count,
    s.sale_count AS stored_count,
    e.paid_total AS expected_paid_total,
    s.paid_total AS stored_paid_total
FROM expected AS e
FULL JOIN tt_lab.customer_summary AS s
    USING (customer_id)
WHERE e.sale_count IS DISTINCT FROM s.sale_count
   OR e.paid_total IS DISTINCT FROM s.paid_total
ORDER BY customer_id;
~~~

**Lưu ý:** khách có summary 0/0 sau khi sale cuối bị xóa sẽ xuất hiện như một “khác biệt” vì expected không có hàng customer đó. Điều này có thể là **khác biệt hình dạng được cho phép theo policy**, không nhất thiết là sai số học.

### 39.1. Một đối soát xử lý zero-summary rows

Nếu thiết kế cho phép summary rows 0/0, có thể so theo `COALESCE`:

~~~sql
WITH expected AS (
    SELECT customer_id,
           COUNT(*)::BIGINT AS sale_count,
           COALESCE(
               SUM(amount) FILTER (WHERE status='paid'),
               0::NUMERIC
           ) AS paid_total
    FROM tt_lab.sales
    GROUP BY customer_id
),
actual AS (
    SELECT customer_id, sale_count, paid_total
    FROM tt_lab.customer_summary
)
SELECT
    COALESCE(e.customer_id, a.customer_id) AS customer_id,
    COALESCE(e.sale_count, 0) AS expected_count,
    COALESCE(a.sale_count, 0) AS actual_count,
    COALESCE(e.paid_total, 0) AS expected_paid,
    COALESCE(a.paid_total, 0) AS actual_paid
FROM expected e
FULL JOIN actual a USING (customer_id)
WHERE COALESCE(e.sale_count, 0)
      IS DISTINCT FROM COALESCE(a.sale_count, 0)
   OR COALESCE(e.paid_total, 0)
      IS DISTINCT FROM COALESCE(a.paid_total, 0)
ORDER BY customer_id;
~~~

Kết quả rỗng nghĩa là **không có sai lệch theo hai metric** đã so, trong snapshot của câu query. Nó không chứng minh mọi trường khác hoặc audit history đều đúng.

## 40. Thứ tự trong transition relations không được bảo đảm

Transition tables là **relations**. Truy vấn:

~~~sql
SELECT * FROM new_rows;
~~~

không bảo đảm thứ tự rows như mệnh đề `VALUES` hoặc thứ tự nhập của client.

Nếu cần sắp theo ID:

~~~sql
SELECT *
FROM new_rows
ORDER BY sale_id;
~~~

Tương tự, `jsonb_agg` hoặc `array_agg` dùng trong trigger phải có `ORDER BY` bên trong aggregate nếu thứ tự array là business requirement.

### 40.1. Đừng nhầm với event order

Trong một statement cập nhật nhiều rows, “hàng nào được xử lý trước” không nên trở thành contract nghiệp vụ nếu SQL không quy định. Nếu cần thứ tự thao tác/bản ghi bền vững, tạo sequence/key logic riêng theo mô hình được kiểm soát.

## 41. Có thể JOIN transition tables với bảng khác

Transition relations dùng trong query như relations khác:

~~~sql
SELECT
    n.customer_id,
    COUNT(*) AS updated_rows
FROM new_rows AS n
JOIN (
    SELECT DISTINCT customer_id
    FROM tt_lab.sales
) AS c
    ON c.customer_id = n.customer_id
GROUP BY n.customer_id;
~~~

Đây là ví dụ query hình dạng chung bên trong trigger phù hợp, không phải câu SQL chạy ngoài trigger (vì `new_rows` không tồn tại ở ngoài ngữ cảnh đó).

### 41.1. Chú ý JOIN gây nhân bản

Nếu JOIN với bảng một-nhiều, số rows có thể tăng. Để tính đúng `COUNT(*)` hoặc `SUM(amount)` của transition table, phải bảo đảm JOIN không nhân bản contributions, hoặc aggregate nguồn trước.

### 41.2. Khi chỉ cần dữ liệu từ transition relation

Không cần JOIN lại bảng nguồn để lấy chính những cột đã có trong `new_rows`. Điều đó tăng I/O và có thể gặp những vấn đề visibility/locking không cần thiết.

## 42. Cập nhật bảng tổng hợp bằng UPSERT

Trong lab:

~~~sql
INSERT INTO tt_lab.customer_summary AS s (
    customer_id, sale_count, paid_total
)
SELECT
    customer_id,
    COUNT(*)::BIGINT,
    COALESCE(
        SUM(amount) FILTER (WHERE status='paid'),
        0::NUMERIC
    )
FROM new_rows
GROUP BY customer_id
ON CONFLICT (customer_id) DO UPDATE
SET sale_count = s.sale_count + EXCLUDED.sale_count,
    paid_total = s.paid_total + EXCLUDED.paid_total;
~~~

Ý nghĩa:

1. Aggregate transition rows theo customer.
2. Nếu customer chưa có summary, tạo hàng.
3. Nếu đã có, cộng delta vào giá trị hiện tại.
4. PostgreSQL thực hiện các kiểm tra khóa/ràng buộc thích hợp.

**Không làm:**

~~~sql
-- Mẫu dễ sai nếu nhiều NEW rows cùng customer_id:
INSERT INTO summary
SELECT customer_id, 1, amount
FROM new_rows
ON CONFLICT (customer_id) DO UPDATE ...;
~~~

Một command `INSERT ... ON CONFLICT DO UPDATE` không được tùy ý tác động cùng target row nhiều lần; duplicate keys trong nguồn cần được nhóm trước.

## 43. Concurrency và tính nhất quán transactional

Giả sử hai transactions cùng INSERT những sale rows khác nhau cho customer 101. Nếu mỗi transaction tính delta trên transition rows của mình rồi UPSERT:

~~~sql
paid_total = paid_total + EXCLUDED.paid_total
~~~

PostgreSQL dùng cơ chế locking/concurrency của UPSERT và phép cập nhật trên hàng hiện tại, giúp tránh một số dạng **lost update** do tự đọc rồi ghi giá trị tuyệt đối bằng hai câu không phối hợp.

Tuy nhiên, không vì vậy mà kết luận mọi invariant đồng thời đều được đảm bảo.

### 43.1. Tránh kiểu đọc summary rồi ghi lại

Một pattern kém an toàn:

~~~text
SELECT paid_total FROM customer_summary
Tính v_new_total ở application
UPDATE customer_summary SET paid_total = v_new_total
~~~

Nếu hai transactions cùng đọc giá trị cũ, một update có thể ghi đè kết quả của transaction khác nếu không có locking/version checks.

Pattern cộng delta ngay trong `ON CONFLICT DO UPDATE` thường phù hợp hơn cho accumulator.

### 43.2. Deadlocks vẫn có thể xảy ra

Nếu một statement tác động nhiều customer summaries, hai transactions có thể khóa các customer rows theo thứ tự khác nhau và xảy ra deadlock. Nên:

- Cân nhắc ordering đầu vào theo customer_id khi thiết kế UPSERT.
- Giữ transaction ngắn.
- Tránh nhiều trigger cập nhật cùng tập bảng theo thứ tự không nhất quán.
- Có retry cho transaction khi gặp deadlock hoặc serialization failures theo policy.
- Đo dưới concurrency.

## 44. CHECK constraint trên summary không thay toàn bộ đối soát

Trong lab:

~~~sql
sale_count BIGINT CHECK (sale_count >= 0)
paid_total NUMERIC CHECK (paid_total >= 0)
~~~

ngăn giá trị âm. Nhưng một summary bị cộng thừa 100 vẫn không âm và CHECK không nhận ra sai lệch.

Vì vậy cần:

- Constraints bảo vệ phạm vi giá trị.
- Trigger delta chính xác.
- Dữ liệu baseline chính xác.
- Query đối soát định kỳ hoặc theo batch.
- Quy trình khôi phục summary từ bảng nguồn nếu có sai lệch.

**Constraint và audit là các lớp bảo vệ bổ sung, không thay thế cho phép đối chiếu với nguồn sự thật.**

## 45. Statement-level trigger có thể xử lý 0 rows

Một điểm rất dễ bỏ quên: statement-level triggers kích hoạt theo **statement**, chứ không đòi ít nhất một row đã thay đổi.

Ví dụ:

~~~sql
DELETE FROM tt_lab.sales
WHERE sale_id = -100;
~~~

Trigger AFTER DELETE có thể chạy và `old_rows` rỗng.

Hậu quả nếu không xử lý:

- `SUM` trả NULL.
- `INSERT ... SELECT GROUP BY` có thể không trả hàng.
- Một lệnh `INSERT audit VALUES (...)` không có guard có thể tạo audit row 0.
- Nếu code assume một hàng tồn tại rồi `SELECT INTO STRICT`, có thể phát sinh exception.

Hãy quyết định policy với no-op statements và viết rõ `COUNT(*)`/`IF v_rows>0` như bài lab.

## 46. Statement trigger không chứng minh request đã thành công ngoài DB

Một trigger có thể INSERT audit log trong transaction. Nếu caller sau đó ROLLBACK:

- Thay đổi bảng `sales` được rollback.
- Bảng summary được rollback.
- Audit rows được rollback.
- Identity sequence counters có thể không quay lại đúng như trước.

Vì vậy một audit row còn tồn tại thường đại diện cho transaction đã commit theo quy tắc dữ liệu transactional, nhưng `audit_id` không phải bằng chứng thứ tự commit toàn cục.

Nếu cần gửi message ra ngoài sau commit, cân nhắc **transactional outbox** kết hợp background publisher thay vì gọi external service trực tiếp trong trigger.

## 47. Một outbox dạng statement-level

Ví dụ khái niệm:

~~~sql
CREATE TABLE tt_lab.outbox_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp(),
    published_at TIMESTAMPTZ
);
~~~

Trong trigger function có thể ghi:

~~~sql
INSERT INTO tt_lab.outbox_events (
    event_type, payload
)
SELECT
    'sales_batch_inserted',
    jsonb_build_object(
        'sale_ids',
        COALESCE(
            jsonb_agg(sale_id ORDER BY sale_id),
            '[]'::jsonb
        )
    )
FROM new_rows
HAVING COUNT(*) > 0;
~~~

Đoạn `INSERT ... SELECT` này là **mẫu chạy bên trong AFTER INSERT trigger function có NEW TABLE AS new_rows**, không chạy độc lập ở SQL client.

### 47.1. Outbox không tự gửi message

Một publisher riêng cần đọc, xuất bản và đánh dấu events; nó phải giải quyết retries/idempotency và tránh mất thông điệp khi publish/ack bị lỗi. Transition table chỉ giúp thu thập event payload theo tập trong cùng transaction.

### 47.2. Không gom array quá lớn

Một statement INSERT hàng triệu rows có thể tạo JSONB payload quá lớn, gây memory và kích thước object không phù hợp. Với bulk changes, outbox nên chứa batch ID, phạm vi khóa hoặc các thông điệp chia lô theo yêu cầu.

## 48. Transition tables và materialized view khác nhau

Transition tables:

- Tồn tại tạm trong trigger.
- Chứa những hàng bị ảnh hưởng của statement/event.
- Hữu ích để tính delta.

Materialized view:

- Là đối tượng lưu kết quả truy vấn.
- Có lệnh `REFRESH MATERIALIZED VIEW`.
- Không tự được cập nhật incremental chỉ vì có transition table ở bảng nguồn.

Bảng `customer_summary` trong lab là một **bảng thường được trigger bảo trì**. Nó không phải PostgreSQL materialized view và không có `REFRESH MATERIALIZED VIEW` tương ứng.

### 48.1. Khi nào dùng query trực tiếp hoặc materialized view?

- Query trực tiếp: logic đơn giản, kết quả cần đúng theo dữ liệu hiện tại và chi phí chấp nhận được.
- Materialized view: phù hợp báo cáo được phép stale theo chu kỳ refresh.
- Summary table + transition triggers: phù hợp nhu cầu cập nhật gần transaction thời gian thực, nhưng phải chịu chi phí ghi và bảo trì logic.

## 49. Cảnh báo về thay đổi schema nguồn

Nếu `tt_lab.sales` thêm cột mới:

~~~sql
ALTER TABLE tt_lab.sales
ADD COLUMN channel TEXT;
~~~

transition relations sẽ có cấu trúc phù hợp với bảng và thao tác. Các truy vấn chỉ chọn `customer_id`, `status`, `amount` vẫn hoạt động khi cột mới không ảnh hưởng business rule.

Nhưng nếu đổi tên/kiểu cột mà trigger function dùng, câu SQL bên trong routine có thể lỗi hoặc thay semantics.

### 49.1. Ưu tiên chọn cột tường minh

Đối với audit:

~~~sql
SELECT to_jsonb(n)
FROM new_rows AS n;
~~~

sẽ có thể phản ánh thêm trường mới của bảng; điều này không phải luôn được mong muốn.

Để giữ event contract ổn định:

~~~sql
SELECT jsonb_build_object(
    'sale_id', n.sale_id,
    'customer_id', n.customer_id,
    'status', n.status,
    'amount', n.amount
)
FROM new_rows AS n;
~~~

Việc whitelist fields giúp tránh vô tình xuất thêm dữ liệu riêng tư sau schema migration.

## 50. Quan sát triggers trong catalog

PostgreSQL có `pg_trigger` và metadata kết hợp với `pg_class`/`pg_namespace`.

Ví dụ:

~~~sql
SELECT
    n.nspname AS table_schema,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled AS enabled_state,
    pg_get_triggerdef(t.oid, TRUE) AS definition
FROM pg_trigger AS t
JOIN pg_class AS c
    ON c.oid = t.tgrelid
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE n.nspname = 'tt_lab'
  AND c.relname = 'sales'
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

`pg_get_triggerdef` cho phép xem định nghĩa SQL đã được PostgreSQL tái dựng, bao gồm `REFERENCING` khi thích hợp.

### 50.1. psql meta-command

~~~text
\d+ tt_lab.sales
~~~

giúp quan sát bảng/triggers trong psql. Đây không phải SQL để gửi qua JDBC.

### 50.2. Xem trigger functions

~~~sql
SELECT pg_get_functiondef(
    'tt_lab.maintain_customer_summary()'::regprocedure
);
~~~

Giúp xác minh body function thực tế trên server. Kết quả được tái dựng từ catalog, không nhất thiết giữ nguyên formatting của file migration.

## 51. Enable/disable trigger: rủi ro lệch summary

Có thể dùng:

~~~sql
ALTER TABLE tt_lab.sales
DISABLE TRIGGER sales_summary_insert;
~~~

hoặc:

~~~sql
ALTER TABLE tt_lab.sales
ENABLE TRIGGER sales_summary_insert;
~~~

**Đừng chạy các lệnh này trên production mà chưa có kế hoạch.** Nếu INSERT diễn ra trong khi summary trigger bị disable, bảng nguồn sẽ thay đổi nhưng summary không được bảo trì.

### 51.1. Khi nào cần rebuild?

Nếu cần import một lượng lớn dữ liệu và chủ động tắt trigger bảo trì, phải có quy trình:

1. Khóa/quản lý writes hoặc bảo đảm snapshot phù hợp.
2. Import dữ liệu.
3. Rebuild summary từ source of truth.
4. Đối soát metrics.
5. Bật lại triggers.
6. Mở writes theo kế hoạch.

**Không chỉ bật lại trigger rồi cho rằng những thay đổi bị bỏ qua trước đó sẽ tự được phát lại.**

## 52. Rebuild summary từ nguồn

Trong một tình huống lab cô lập, sau khi xác nhận quyền và chặn writers thích hợp, một cách rebuild là:

~~~sql
BEGIN;

LOCK TABLE tt_lab.sales IN SHARE MODE;

DELETE FROM tt_lab.customer_summary;

INSERT INTO tt_lab.customer_summary (
    customer_id, sale_count, paid_total
)
SELECT
    customer_id,
    COUNT(*)::BIGINT,
    COALESCE(
        SUM(amount) FILTER (WHERE status='paid'),
        0::NUMERIC
    )
FROM tt_lab.sales
GROUP BY customer_id;

COMMIT;
~~~

Đây là **mẫu vận hành cần xem xét kỹ**, không phải quy trình production hoàn chỉnh. Loại lock, isolation, writers, partitions, timeouts và data size phải được đánh giá thực tế.

### 52.1. Vì sao cần nhất quán snapshot và writes?

Nếu có writers sửa `sales` trong lúc summary bị DELETE/rebuild mà trigger cũng đang cộng delta, có nguy cơ tính thiếu hoặc tính trùng.

Thiết kế rebuild production phải rõ ai được ghi trong suốt window và cách đồng bộ catch-up.

### 52.2. Zero-summary rows sau rebuild

Cách rebuild trên chỉ tạo summary cho customers đang có sale rows. Những khách đã xóa hết sale trước đó sẽ không còn summary rows 0/0. Điều này không đổi tổng tiền nếu API coi thiếu hàng bằng 0, nhưng có thể đổi contract nếu API yêu cầu giữ mọi customer keys.

## 53. Performance của transition tables

Chi phí cần xét:

- PostgreSQL phải thu thập/cung cấp các hàng trước/sau liên quan.
- Đọc một tập transition rows cho aggregate/group.
- Memory/temp I/O nếu tập thay đổi rất lớn.
- Index/constraints/WAL cho bảng audit và summary.
- Locks và contention trên summary keys.
- Số lượng triggers và SQL bên trong.
- Chi phí lập kế hoạch/thực thi các statements trong PL/pgSQL.
- Khối lượng rows thực sự bị sửa trong một statement.

Với UPDATE 5 hàng, một row-level trigger đơn giản có thể đã đủ nhanh. Với UPDATE 100.000 hàng cùng customer, aggregate một lần theo customer có thể giảm nhiều thao tác ghi summary, dù vẫn có chi phí dựng transition relations.

**Không tuyên bố transition table nhanh hơn trong mọi tình huống**; phải benchmark với workload tương ứng.

## 54. EXPLAIN và đo nội bộ triggers

Có thể quan sát DML:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE tt_lab.sales
SET amount = amount + 1
WHERE sale_id BETWEEN 10 AND 14;

ROLLBACK;
~~~

`EXPLAIN ANALYZE` **thực thi UPDATE**, nên ví dụ dùng transaction lab để rollback các thay đổi transactional.

Tùy loại plan và phiên bản PostgreSQL, output có thể cung cấp thông tin thời gian trigger/constraint triggers; nhưng không nhất thiết hiển thị mọi SQL statement bên trong PL/pgSQL trigger function như một plan phân cấp đầy đủ.

### 54.1. Những chỉ số nên đo

- Tổng thời gian statement có và không có trigger.
- Số rows bị thay đổi.
- Số distinct customer_id trong transition relations.
- Số summary rows được UPSERT.
- WAL volume.
- Buffer hits/reads/writes.
- Temporary files, memory.
- Lock waits/deadlocks.
- p95/p99 latency dưới concurrency.
- Độ đúng của kết quả summary sau mỗi loại event.

### 54.2. Đo baseline trước khi tối ưu

Một trigger giảm 10.000 updates xuống 20 group updates có thể cải thiện workload, nhưng cũng có thể làm tăng memory trong batch rất lớn. Đo trước/sau cùng khối lượng dữ liệu và kiểu phân bố customer_id.

## 55. Điều kiện business phức tạp và group expressions

Tổng hợp trong trigger không nhất thiết chỉ dùng `customer_id`. Có thể gom theo:

- Customer.
- Product.
- Day/month.
- Region.
- Currency.
- Tổ hợp nhiều dimension.

Ví dụ ý tưởng:

~~~sql
SELECT
    customer_id,
    DATE(updated_at) AS change_date,
    COUNT(*) AS changed_rows
FROM new_rows
GROUP BY customer_id, DATE(updated_at);
~~~

**Lưu ý về thời gian:** `updated_at` của hàng không nhất thiết là thời điểm business event hoặc thời điểm commit. Nếu tổng hợp theo ngày kế toán, định nghĩa rõ timezone/business timestamp và quy tắc của nghiệp vụ.

### 55.1. Cẩn thận với group key thay đổi

Nếu một UPDATE có thể đổi `region` hoặc `customer_id`, phải trừ đóng góp theo **old group key** và cộng theo **new group key**, không chỉ cập nhật group mới.

### 55.2. Aggregate theo nhiều dimension có thể tăng contention

Nếu một key nóng được cập nhật liên tục bởi nhiều transactions, bảng tổng hợp có thể trở thành nút thắt lock. Cân nhắc shards, batching, asynchronous aggregation hoặc thiết kế dữ liệu khác nếu cần throughput cao.

## 56. Không làm tròn sai khi tính delta

Trong bài, `amount NUMERIC(12,2)` và `paid_total NUMERIC(18,2)` nhằm mô phỏng tiền cần độ chính xác thập phân.

Nếu dùng `DOUBLE PRECISION` cho tiền, phép cộng/trừ floating point có thể có sai số làm summary lệch khi đối soát exact equality.

Quy tắc:

- Chọn `NUMERIC` hoặc đơn vị nguyên nhỏ nhất theo business contract.
- Xác định scale/rounding nhất quán tại chỗ tạo amount.
- Với nhiều currency, **group theo currency** chứ không cộng trực tiếp số tiền khác đơn vị.
- Cẩn thận về overflow của kiểu số và giới hạn precision.

## 57. Triggers có thể gọi DML và gây recursion

Một trigger trên `sales` có thể INSERT vào `statement_audit` và UPSERT `customer_summary`. Trong lab, hai bảng đích **không có trigger cập nhật lại `sales`**, nên không hình thành vòng gọi đệ quy.

Trong hệ thống thực:

~~~text
Trigger sales
   |
   v
UPDATE summary
   |
   v
Trigger summary
   |
   v
UPDATE sales
   |
   v
Trigger sales ...
~~~

có nguy cơ recursion không mong muốn.

### 57.1. pg_trigger_depth không thay thiết kế tốt

PostgreSQL có `pg_trigger_depth()` để quan sát độ sâu trigger hiện tại, nhưng chỉ dựa vào điều kiện depth để vô hiệu hóa logic có thể che lỗi nghiệp vụ.

Nên thiết kế luồng ghi một chiều, tách responsibilities rõ và thử các thay đổi có thể kích hoạt nhiều triggers.

## 58. Vì sao không dùng một statement trigger để “chặn” mọi sai dữ liệu?

Transition tables được cung cấp ở AFTER triggers. Nếu phát hiện một bất biến sai trong AFTER trigger, có thể `RAISE EXCEPTION` để làm statement lỗi và rollback transactional changes.

Nhưng điều đó có thể tạo công việc vô ích trước khi kiểm tra xong, và trong môi trường nhiều transactions, một query aggregate không locking phù hợp chưa chắc là constraint an toàn toàn cục.

Ưu tiên khi có thể:

- `NOT NULL`, `CHECK`.
- `UNIQUE`, `EXCLUDE`.
- `FOREIGN KEY`.
- Schema constraints phù hợp.
- Row-Level Security/authorization.
- Serializable transactions/explicit locking cho những bất biến xuyên hàng phức tạp.

Transition tables phù hợp để **đối chiếu tập hàng thay đổi**, không tự thay mọi cơ chế integrity của database.

## 59. Bảo mật trigger functions

Trigger function có thể chạy với quyền của role tương ứng theo chế độ `SECURITY INVOKER`/`SECURITY DEFINER` và quy tắc ownership.

Không cấp quyền quá rộng chỉ để trigger có thể ghi bảng audit.

Nếu dùng `SECURITY DEFINER`:

~~~sql
CREATE FUNCTION tt_lab.some_privileged_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = tt_lab, pg_temp
AS $$
BEGIN
    -- Tham chiếu đối tượng theo schema đầy đủ.
    RETURN NULL;
END;
$$;
~~~

thì cần:

- Owner tin cậy với ít đặc quyền nhất.
- `search_path` an toàn; không chứa schema nơi user không tin cậy có thể tạo object.
- Tên bảng/function schema-qualified trong thân.
- Kiểm soát quyền sửa function/schema.
- Không nhận raw dynamic identifiers từ dữ liệu người dùng.
- Tránh đưa dữ liệu bí mật vào exception/audit.

### 59.1. Trigger không tự thay RLS policy

Nếu cần tenant isolation, phải kiểm tra RLS, quyền ghi/read và đường truy cập bảng nguồn/summary. Đừng cho rằng chỉ vì summary được ghi trong trigger thì mọi dữ liệu trả từ summary đã được filter đúng tenant.

## 60. Quyền tạo trigger và quyền đọc bảng đích

Để tạo/đính trigger, role cần các quyền thích hợp trên bảng nguồn và quyền sử dụng trigger function theo quy định PostgreSQL. Quyền thao tác trên những bảng được truy vấn/ghi bên trong trigger function còn tùy execution security context.

Trong hệ thống có nhiều roles:

- Migration role tạo tables/triggers/functions.
- Application role thực hiện DML theo quyền được cấp.
- Audit/reporting roles có quyền đọc dữ liệu phù hợp.
- Owner SECURITY DEFINER (nếu cần) có đặc quyền được giới hạn.

Không giải quyết một lỗi permission bằng cách cấp superuser cho ứng dụng.

## 61. Trigger và row-level security

RLS có thể ảnh hưởng những hàng caller được sửa và những hàng trigger function có thể đọc theo security context, tùy owner, policies và loại thao tác.

Nếu một transaction sửa 10 hàng, transition table chỉ biểu diễn những rows thực sự bị event tác động trong phạm vi đó, chứ không tự cấp quyền xem toàn bộ dữ liệu của mọi tenant.

Bảng tổng hợp có thể gây lộ số liệu khi chứa nhiều tenants. Một summary key chỉ theo customer_id nhưng customer_id không unique toàn hệ thống có thể tạo trộn dữ liệu; khi thiết kế multi-tenant, group key thường phải chứa tenant_id hoặc đảm bảo tính duy nhất toàn cục theo contract.

## 62. Transition tables và audit chính xác từng thay đổi

Nếu yêu cầu audit có:

- Ai sửa?
- Giá trị trước/sau của từng hàng?
- Correlation/request ID?
- Lý do business?
- Thời gian commit?
- Tác động tới bảng khác?

transition tables có thể cung cấp **old/new row values** trong phạm vi event, nhưng không tự cung cấp tất cả context này một cách an toàn và bền vững.

Cần thiết kế:

- Context từ application (role/request ID theo cơ chế tin cậy).
- Bảng audit có schema ổn định.
- Permissions/retention.
- Idempotency.
- Correlation giữa nhiều statements trong một transaction.
- Thời gian statement/transaction/commit được hiểu đúng.

Không gọi `statement_timestamp()` là “commit timestamp”; đây là hai mốc thời gian khác nhau.

## 63. Một row có thể bị thay bởi nhiều statements trong transaction

Ví dụ:

~~~sql
BEGIN;

UPDATE tt_lab.sales
SET amount = amount + 10
WHERE sale_id = 10;

UPDATE tt_lab.sales
SET status = 'paid'
WHERE sale_id = 10;

COMMIT;
~~~

Hai UPDATE statements có thể tạo **hai lần AFTER UPDATE statement trigger**, mỗi lần có transition relations riêng, dù cùng một sale_id và cùng transaction.

Do đó:

- Transition table **không** tổng hợp toàn bộ những thay đổi của một transaction.
- Audit cấp statement khác audit cấp transaction/request.
- Nếu cần đối soát “net delta của transaction”, phải thiết kế tầng aggregation/correlation khác.

## 64. Trigger có thể bị kích hoạt bởi SQL bên trong trigger

Một trigger function có thể thực hiện DML trên bảng khác, làm trigger trên bảng khác tiếp tục chạy. Tác động này vẫn nằm trong transaction liên quan.

Vì thế khi vẽ dependency graph, cần xem:

~~~text
source DML
   |
   +--> trigger A -> audit table INSERT
   |
   +--> trigger B -> summary UPSERT
                          |
                          +--> summary triggers (nếu có)
~~~

Không xét riêng từng trigger khi có chain lớn; còn phải đánh giá deadlock order, recursion, failure propagation và chi phí.

## 65. DML có RETURNING: khi nào không cần trigger?

Nếu chỉ cần application biết những hàng vừa thay đổi, PostgreSQL có `RETURNING`:

~~~sql
UPDATE tt_lab.sales
SET status = 'paid'
WHERE sale_id = 10
RETURNING sale_id, customer_id, status, amount;
~~~

Ứng dụng nhận rows đó trong response của statement mà không cần tạo trigger chỉ để đọc những giá trị mới.

Tuy nhiên `RETURNING`:

- Gắn với chính câu DML do caller thực hiện.
- Không tự bảo đảm mọi code path đều ghi audit/summary.
- Không thay thế old/new transition table đầy đủ trong mọi phiên bản/cú pháp.
- Không tự xử lý phụ thuộc khi nhiều writers không dùng cùng API.

### 65.1. Khi nào chọn trigger?

Khi một invariant/audit/summary cần áp dụng **tập trung** cho những thay đổi qua nhiều writer paths và không muốn mỗi ứng dụng phải tự nhớ cập nhật bảng phụ.

### 65.2. Khi nào chọn application logic?

Khi nghiệp vụ cần phối hợp nhiều services hoặc có context không sẵn trong DB, và transaction/outbox design do application kiểm soát. Cần tránh ghi cùng một summary ở cả trigger và application dẫn tới double-count.

## 66. MERGE, UPSERT và COPY với lượng dữ liệu lớn

Khi dùng bulk ingestion:

- `INSERT ... VALUES (...), (...)` có thể cung cấp nhiều rows cho một statement.
- `INSERT ... SELECT` có thể tác động tập lớn.
- `COPY FROM` có semantics INSERT/triggers theo cơ chế PostgreSQL, cần hiểu với dataset lớn.
- `INSERT ... ON CONFLICT DO UPDATE` có thể tác động nhiều nhánh event.
- `MERGE` có semantics event/trigger phụ thuộc phiên bản và action branches.

Transition tables phục vụ việc **xử lý đúng những rows của event**, nhưng tập chuyển tiếp lớn có thể làm tăng memory/temp I/O. Nếu bulk load hàng triệu rows, cân nhắc import chunks, summary rebuild theo batch và monitoring thay vì mặc định trigger incremental luôn nhanh nhất.

## 67. Test với nhiều kiểu thay đổi

Một kịch bản kiểm thử đầy đủ trên lab nên bao gồm:

1. INSERT một row draft.
2. INSERT nhiều rows paid/draft của cùng customer.
3. UPDATE amount của paid sale.
4. UPDATE draft → paid.
5. UPDATE paid → cancelled.
6. UPDATE customer_id.
7. UPDATE status và amount cùng lúc.
8. UPDATE một field không liên quan metric.
9. UPDATE 0 rows.
10. DELETE một paid row.
11. DELETE một cancelled row.
12. DELETE 0 rows.
13. INSERT ON CONFLICT DO UPDATE có cả insert/update.
14. Hai transactions cùng cập nhật summary key.
15. ROLLBACK sau DML.
16. Batch quá lớn hoặc gây contention.
17. TRUNCATE theo chính sách đã xác định.
18. Thay đổi schema nguồn và audit output contract.

Đối soát sau mỗi nhóm event bằng phép tổng hợp nguồn; không chỉ nhìn rằng trigger không báo lỗi.

## 68. Checklist thiết kế transition-table trigger

**Về semantics:**

- Sự kiện là INSERT, UPDATE hay DELETE?
- Cần OLD, NEW hay cả hai?
- Có cần tổng theo statement hay audit mỗi hàng?
- Có cần ghép OLD–NEW từng hàng không?
- Khóa ghép có bất biến khi UPDATE không?
- Có thể thay group key không?
- Có thể có 0 rows?
- Bản ghi NULL và các giá trị status được xử lý đúng?
- Có cần thứ tự? Nếu có, đã ORDER BY?

**Về schema và DDL:**

- Trigger là AFTER đúng loại bảng?
- Không dùng constraint trigger?
- Không dùng UPDATE OF với transition relations?
- Đã đặt aliases trùng với function body?
- DML từ UPSERT/MERGE/partition path được xét?
- TRUNCATE được xử lý hoặc giới hạn?
- Source và summary baseline có nhất quán?

**Về vận hành:**

- Có quyền và security context đúng?
- Có cơ chế ngăn double-count?
- UPSERT đã aggregate trước?
- Có concurrency/deadlock retry policy?
- Có đối soát metrics định kỳ?
- Đã đo latency/WAL/locks?
- Có kế hoạch rebuild/rollback?
- Đã kiểm soát kích thước batch và audit retention?

## 69. Các lỗi thường gặp

### Lỗi 1 — Dùng OLD TABLE trong BEFORE trigger

Transition relations dành cho AFTER triggers phù hợp.

### Lỗi 2 — Dùng UPDATE OF amount kèm REFERENCING

Không được kết hợp column-specific UPDATE trigger với transition relations.

### Lỗi 3 — Nhầm OLD/NEW record với old_rows/new_rows

`OLD.amount` dùng trong row-level trigger; `SELECT ... FROM old_rows` dùng transition relation.

### Lỗi 4 — Coi transition table là một bảng thật

Nó chỉ có phạm vi kích hoạt trigger, không truy cập như bảng lâu dài sau statement.

### Lỗi 5 — Coi nó chứa toàn bộ bảng nguồn

Nó chứa những hàng liên quan event của statement, không phải mọi rows hiện có.

### Lỗi 6 — UPDATE chỉ nhìn NEW

Bỏ sót contribution cũ, nhất là khi đổi status hoặc customer_id.

### Lỗi 7 — JOIN OLD/NEW bằng key có thể đổi

Mapping có thể sai hoặc mất hàng. Dùng identity ổn định hoặc aggregate hai tập độc lập.

### Lỗi 8 — Dùng SUM mà quên COALESCE

SUM trên tập rỗng trả NULL.

### Lỗi 9 — Statement 0 rows nhưng vẫn INSERT audit rỗng

Cần quyết định chính sách và kiểm tra COUNT(*).

### Lỗi 10 — ON CONFLICT với nhiều input rows cùng group key

Phải aggregate/deduplicate trước khi UPSERT vào cùng target key.

### Lỗi 11 — Bật cả row trigger cũ và statement trigger mới

Có thể double-count summary.

### Lỗi 12 — Bỏ qua TRUNCATE

TRUNCATE không kích hoạt DELETE transition-table trigger tương đương.

### Lỗi 13 — Giả định UPSERT chỉ có INSERT event

`ON CONFLICT DO UPDATE` có thể kích hoạt logic UPDATE event theo quy tắc.

### Lỗi 14 — Giả định partition triggers giống bảng thường

Phải kiểm tra parent/partition/row movement theo phiên bản.

### Lỗi 15 — Giả định AFTER nghĩa là đã commit

Trigger vẫn thuộc transaction, có thể rollback.

### Lỗi 16 — Ghi external side effect trong trigger và mong rollback được

External service không tự rollback cùng PostgreSQL; dùng outbox/idempotency.

### Lỗi 17 — Audit tất cả cột bằng to_jsonb mà không xét PII

Có thể lộ dữ liệu nhạy cảm hoặc tăng lưu trữ.

### Lỗi 18 — Bỏ qua concurrency trên summary keys nóng

Nhiều writers có thể lock wait/deadlock.

### Lỗi 19 — So sánh tổng tiền FLOAT exact equality

Có thể sai số; nên dùng kiểu tiền phù hợp như NUMERIC.

### Lỗi 20 — Coi bảng summary là nguồn sự thật duy nhất

Cần đối soát với bảng sales và rebuild khi sai lệch.

### Lỗi 21 — DISABLE TRIGGER rồi quên rebuild

Các thay đổi bị bỏ qua không tự replay sau ENABLE.

### Lỗi 22 — Tưởng transition relation có thứ tự

Relations không có order mặc định; phải ORDER BY khi cần.

### Lỗi 23 — Mở ra một JSONB array khổng lồ

Có thể gây chi phí memory/network và giới hạn kích thước.

### Lỗi 24 — Không giới hạn EXECUTE quyền của trigger function

Cần security context an toàn và least privilege.

### Lỗi 25 — Dùng transition trigger cho cross-row constraint không locking

Một query aggregate trong AFTER trigger chưa chắc an toàn dưới mọi mức concurrency.

### Lỗi 26 — Chỉ benchmark UPDATE 1 hàng

Cần workload phản ánh batch size, số distinct grouping keys và concurrency thực tế.

## 70. Bài tập thực hành

### Bài 1 — Khái niệm

Transition table có phải một persistent table chứa toàn bộ dữ liệu nguồn không?

**Gợi ý:** không, là tập rows liên quan statement/event trong trigger.

### Bài 2 — INSERT

Viết AFTER INSERT trigger có `REFERENCING NEW TABLE AS new_rows`.

**Gợi ý:** `FOR EACH STATEMENT EXECUTE FUNCTION ...`.

### Bài 3 — DELETE

Viết AFTER DELETE trigger tham chiếu `OLD TABLE`.

**Gợi ý:** `REFERENCING OLD TABLE AS old_rows`.

### Bài 4 — UPDATE

Một AFTER UPDATE trigger muốn tính delta theo customer cần mấy transition relations?

**Gợi ý:** OLD và NEW.

### Bài 5 — OLD vs old_rows

Khác nhau giữa `OLD.amount` và `SELECT SUM(amount) FROM old_rows`?

**Gợi ý:** một row record so với set relation.

### Bài 6 — AFTER

Vì sao không dùng BEFORE trigger với transition tables?

**Gợi ý:** giới hạn cú pháp/thời điểm hỗ trợ.

### Bài 7 — Constraint trigger

Có thêm REFERENCING transition tables vào constraint trigger được không?

**Gợi ý:** không.

### Bài 8 — UPDATE OF

`AFTER UPDATE OF status ... REFERENCING OLD TABLE ...` có hợp lệ không?

**Gợi ý:** không; dùng AFTER UPDATE rồi lọc thay đổi.

### Bài 9 — INSERT 100 rows

FOR EACH STATEMENT trigger được gọi bao nhiêu lần cho một INSERT VALUES chứa 100 rows?

**Gợi ý:** một lần cho event statement tương ứng, không phải 100 lần.

### Bài 10 — UPDATE 0 rows

AFTER STATEMENT trigger có thể chạy không?

**Gợi ý:** có, transition relation rỗng.

### Bài 11 — COUNT và SUM

COUNT(*) và SUM(amount) trên transition table rỗng trả gì?

**Gợi ý:** 0 và NULL.

### Bài 12 — Paid delta cho INSERT

Viết GROUP BY customer_id trên new_rows với `SUM(amount) FILTER (WHERE status='paid')`.

**Gợi ý:** COALESCE để được 0.

### Bài 13 — Paid delta cho DELETE

Giá trị contribution cũ phải mang dấu gì?

**Gợi ý:** âm.

### Bài 14 — Chuyển customer

OLD customer 101 paid 100, NEW customer 102 paid 150. Tính delta hai nhóm.

**Gợi ý:** 101: -1/-100; 102: +1/+150.

### Bài 15 — UNION ALL

Vì sao dùng UNION ALL old/new contributions rồi GROUP BY lần nữa?

**Gợi ý:** tạo net delta theo mỗi group key, kể cả khi key thay đổi.

### Bài 16 — Duplicate upsert source

Tại sao phải GROUP BY trước `ON CONFLICT DO UPDATE`?

**Gợi ý:** tránh tác động một target row nhiều lần trong một command.

### Bài 17 — Không đổi business fields

UPDATE chỉ thay updated_at có làm paid delta khác 0 không?

**Gợi ý:** không.

### Bài 18 — IS DISTINCT FROM

Tại sao phép này phù hợp khi field nullable?

**Gợi ý:** xử lý NULL một cách xác định.

### Bài 19 — Ghép old/new

Khi nào JOIN old_rows với new_rows bằng sale_id không an toàn?

**Gợi ý:** sale_id có thể bị UPDATE.

### Bài 20 — Audit từng hàng

Dùng `INSERT INTO audit SELECT ... FROM old_rows JOIN new_rows ...` để ghi nhiều audit records trong một lần trigger.

**Gợi ý:** whitelist fields và stable key.

### Bài 21 — Transaction

Nếu caller ROLLBACK, bảng summary được trigger UPDATE có rollback không?

**Gợi ý:** có nếu là DML transactional trong cùng transaction.

### Bài 22 — Commit timestamp

`statement_timestamp()` có phải commit timestamp không?

**Gợi ý:** không.

### Bài 23 — TRUNCATE

TRUNCATE có kích hoạt AFTER DELETE transition trigger như DELETE không?

**Gợi ý:** không.

### Bài 24 — UPSERT

Một INSERT ON CONFLICT DO UPDATE có thể đi qua những event nào?

**Gợi ý:** INSERT và UPDATE theo các nhánh/hành vi trigger phù hợp.

### Bài 25 — MERGE

Vì sao cần xác minh semantics trên version PostgreSQL mục tiêu?

**Gợi ý:** nhiều action branches, event triggers và transition sets.

### Bài 26 — Partitioned table

Vì sao không nên tạo trigger cả parent và partitions theo giả định đơn giản?

**Gợi ý:** nguy cơ đếm lặp/bỏ sót do event semantics.

### Bài 27 — Foreign table

Có thể coi transition tables là cơ chế bắt mọi thay đổi ở remote DB không?

**Gợi ý:** không.

### Bài 28 — CDC

Transition table có thay logical replication/WAL decoding không?

**Gợi ý:** không, nó chỉ theo event/statement scope.

### Bài 29 — Materialized view

Summary table được trigger duy trì có phải materialized view không?

**Gợi ý:** không.

### Bài 30 — Baseline

Nếu bảng sales đã có dữ liệu nhưng summary trống, làm sao bắt đầu incremental maintenance?

**Gợi ý:** rebuild baseline nhất quán trước.

### Bài 31 — Đối soát

Viết SELECT GROUP BY customer_id để so với customer_summary.

**Gợi ý:** COUNT và SUM FILTER paid.

### Bài 32 — Zero-summary rows

Nếu customer có summary 0/0 nhưng không còn sales, đó nhất thiết là lỗi?

**Gợi ý:** tùy contract; so COALESCE nếu được phép.

### Bài 33 — Lock contention

Nhiều transactions cùng UPSERT customer 101 có rủi ro gì?

**Gợi ý:** lock waits, deadlocks và throughput thấp.

### Bài 34 — Lost update

Vì sao `SET paid_total=s.paid_total+EXCLUDED.paid_total` tốt hơn đọc total ngoài rồi ghi đè?

**Gợi ý:** cộng delta trên row state dưới cơ chế khóa của UPSERT.

### Bài 35 — Outbox

Vì sao trigger không nên tự gọi external API để gửi event?

**Gợi ý:** external action không rollback cùng DB.

### Bài 36 — JSONB payload lớn

Nếu một statement ảnh hưởng 2 triệu sale rows, có nên jsonb_agg mọi row vào một outbox event không?

**Gợi ý:** thường không; dùng batches/IDs.

### Bài 37 — Security

SECURITY DEFINER trigger function cần bảo vệ gì?

**Gợi ý:** owner, search_path, grants, schema qualification, authorization.

### Bài 38 — RLS

Một bảng summary không chứa tenant_id có thể gây điều gì khi IDs không unique toàn hệ thống?

**Gợi ý:** gộp nhầm và lộ dữ liệu tenant.

### Bài 39 — Trigger disable

Tắt summary trigger để bulk load rồi bật lại có tự tái xử lý các changes đã bỏ không?

**Gợi ý:** không; phải rebuild/catch up.

### Bài 40 — pg_get_triggerdef

Viết query xem định nghĩa triggers trên tt_lab.sales.

**Gợi ý:** `pg_trigger` kết hợp `pg_get_triggerdef`.

### Bài 41 — DML EXPLAIN

Vì sao `EXPLAIN ANALYZE UPDATE` nên chạy trong lab transaction?

**Gợi ý:** nó thực thi DML thật.

### Bài 42 — Row trigger vs statement trigger

Khi nào row-level trigger hợp lý hơn transition table?

**Gợi ý:** validation/thao tác gắn với từng row và OLD/NEW.

### Bài 43 — GROUP BY dimensions

Khi group key region/currency thay đổi, cần xử lý old/new thế nào?

**Gợi ý:** trừ old group, cộng new group.

### Bài 44 — Race

Một trigger kiểm tổng across rows không locking có đảm bảo invariant trong mọi concurrent transactions?

**Gợi ý:** không; cần constraints/locking/isolation.

### Bài 45 — Double count

Nếu cả row trigger cũ và transition trigger mới cùng cập nhật một summary, lỗi gì xảy ra?

**Gợi ý:** cộng delta hai lần.

## 71. Câu hỏi thường gặp

### Transition table có phải một bảng tạm do tôi CREATE không?

Không. PostgreSQL tự cung cấp transition relation cho trigger phù hợp; bạn đặt alias qua `REFERENCING`. Nó không phải một bảng persistent để query ngoài trigger.

### OLD TABLE có bao gồm tất cả các hàng cũ trong bảng không?

Không. Nó chỉ biểu diễn những hàng liên quan event của câu DML đã kích hoạt trigger, không phải snapshot toàn bảng.

### Có thể tạo transition table trong BEFORE trigger không?

Không theo cơ chế transition relations dành cho AFTER triggers phù hợp.

### Có cần FOR EACH STATEMENT mới dùng transition tables không?

Đây là cách thường dùng khi muốn aggregate cả tập. Một số AFTER ROW triggers phù hợp cũng có thể tham chiếu transition relations, nhưng scan cả tập trong mỗi row trigger có thể tốn kém.

### UPDATE trigger có thể dùng cả OLD TABLE và NEW TABLE không?

Có, với một AFTER UPDATE trigger phù hợp và không khai báo `UPDATE OF column_list`.

### UPDATE 0 rows có kích hoạt statement trigger không?

Có thể có; statement-level trigger kích hoạt theo event statement. Transition relation rỗng, nên cần xử lý COUNT/SUM phù hợp.

### Tại sao UPDATE customer_id cần aggregate hai tập?

Vì một row có thể rời group cũ và vào group mới. Chỉ tính amount difference ở group mới sẽ sai.

### Vì sao không JOIN old_rows/new_rows bằng một khóa có thể đổi?

Nếu key đổi, cặp old/new có thể không còn match. Với tổng hợp, aggregate mỗi tập riêng; với audit từng hàng, cần identity ổn định hoặc cơ chế khác.

### Transition trigger có thay constraint không?

Không. Nó hữu ích cho logic theo tập, nhưng các bất biến integrity nên dùng database constraints hoặc cơ chế concurrency thích hợp khi có thể.

### Có thể dùng transition tables với TRUNCATE không?

Không. TRUNCATE có hành vi trigger riêng, không tương đương DELETE old transition rows.

### UPSERT có chỉ kích hoạt INSERT trigger không?

Không mặc định. Với `ON CONFLICT DO UPDATE`, trigger semantics liên quan cả INSERT và UPDATE paths. Phải thiết kế đúng từng event.

### Transition tables có giữ thứ tự các rows bị thay đổi không?

Không có bảo đảm thứ tự truy vấn SQL nếu thiếu ORDER BY.

### Trigger chạy sau UPDATE có nghĩa thay đổi đã COMMIT?

Không. AFTER trigger chạy trong transaction; thay đổi dữ liệu/audit/summary vẫn có thể rollback.

### Có nên tạo transition-trigger summary cho mọi báo cáo không?

Không. Trước hết thử query trực tiếp hoặc materialized view theo yêu cầu freshness. Trigger summary cần thêm ghi/locks và bảo trì logic.

### Có thể dùng transition tables làm event sourcing/CDC đầy đủ không?

Không. Chúng chỉ cung cấp tập rows trong ngữ cảnh trigger. Muốn lịch sử bền vững cần ghi audit/outbox; muốn CDC toàn hệ thống cần thiết kế pipeline thích hợp.

## 72. Tổng kết

Các cú pháp lõi:

~~~sql
-- Chèn: có ảnh NEW.
CREATE TRIGGER trg_insert
AFTER INSERT ON schema_name.table_name
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.handler();

-- Xóa: có ảnh OLD.
CREATE TRIGGER trg_delete
AFTER DELETE ON schema_name.table_name
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.handler();

-- Cập nhật: có cả OLD và NEW.
CREATE TRIGGER trg_update
AFTER UPDATE ON schema_name.table_name
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION schema_name.handler();
~~~

Những nguyên tắc chính:

1. **Transition tables cung cấp tập các hàng trước/sau của một DML event**, không phải snapshot toàn bảng.
2. `REFERENCING NEW TABLE` dùng cho INSERT/UPDATE; `REFERENCING OLD TABLE` dùng cho DELETE/UPDATE.
3. Chúng thuộc các **AFTER triggers phù hợp** và có những giới hạn: không dùng với BEFORE/INSTEAD OF/TRUNCATE, constraint trigger hoặc `UPDATE OF`.
4. **Statement-level trigger có thể chạy ngay cả khi 0 rows bị ảnh hưởng**; handle empty sets.
5. Một transition-table trigger có thể dùng `SELECT ... GROUP BY`, `INSERT ... SELECT` và `ON CONFLICT` để xử lý hàng loạt, giảm thao tác per-row.
6. Với UPDATE, tính **new contributions trừ old contributions**; group key có thể thay đổi.
7. **Aggregate source theo key trước UPSERT** để tránh nhiều source rows cùng target key trong một command.
8. Nếu cần ghép từng cặp old/new, phải có **khóa identity ổn định**; transition table không tự tạo row-pairing ID.
9. `AFTER` **không có nghĩa đã COMMIT**; thay đổi từ trigger nằm trong transaction caller.
10. UPSERT/MERGE, partitions, cascading actions và trigger chains có semantics cần kiểm tra trên PostgreSQL version/schema thực tế.
11. TRUNCATE hoặc tắt trigger có thể làm summary lệch nếu thiếu quy trình rebuild.
12. **Tổng hợp theo trigger không tự thay mọi constraints**; cần kiểm tra concurrency, locking, idempotency và RLS.
13. Dùng `NUMERIC` và dimension keys đúng nghiệp vụ khi tổng hợp tiền.
14. Audit/outbox cần schema và retention, không gom payload JSONB khổng lồ hoặc đưa thông tin nhạy cảm tùy tiện.
15. **Đối soát với bảng nguồn và đo hiệu năng** là phần không thể thiếu của bảng tổng hợp incremental.

Sơ đồ tư duy:

~~~text
INSERT / UPDATE / DELETE statement
                  |
                  v
        AFTER trigger phù hợp
                  |
                  v
       REFERENCING transition relations
              /              \
             /                \
        OLD TABLE           NEW TABLE
             \                /
              \              /
               v            v
        Tính contributions theo tập
                       |
                       v
          GROUP BY business key
                       |
                       v
               Net delta
                       |
              +--------+--------+
              |                 |
              v                 v
       Statement audit   Summary UPSERT
              |                 |
              +--------+--------+
                       |
                       v
           Cùng transaction nguồn
                       |
             COMMIT hoặc ROLLBACK
~~~

Điểm cốt lõi: **khi nghiệp vụ cần xem và xử lý toàn bộ nhóm hàng vừa thay đổi, hãy nghĩ tới transition tables cùng SQL set-based**. Chúng giúp tập trung logic của một statement và giảm nhiều thao tác per-row, nhưng chỉ phát huy giá trị khi xác định đúng sự kiện, transaction, group delta, concurrency và phạm vi dữ liệu mà trigger thực sự nhìn thấy.
