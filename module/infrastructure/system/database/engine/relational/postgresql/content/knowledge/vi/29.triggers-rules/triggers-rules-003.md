# Trigger theo hàng và theo câu lệnh trong PostgreSQL

Trong PostgreSQL, **trigger** là cơ chế tự động gọi một hàm khi một sự kiện dữ liệu hoặc lược đồ phù hợp xảy ra. Với các trigger DML trên bảng, một lựa chọn ảnh hưởng trực tiếp tới tính đúng và hiệu năng là:

- **`FOR EACH ROW` — trigger theo hàng:** được kích hoạt cho từng hàng liên quan đến thao tác.
- **`FOR EACH STATEMENT` — trigger theo câu lệnh:** được kích hoạt một lần cho mỗi câu lệnh SQL phù hợp, ngay cả khi câu lệnh không tác động hàng nào.

Ví dụ:

~~~sql
UPDATE products
SET price = price * 1.10
WHERE category = 'office';
~~~

Nếu có 20.000 hàng thỏa điều kiện, trigger `FOR EACH ROW` phù hợp có thể được thực thi **20.000 lần**, còn trigger `FOR EACH STATEMENT` phù hợp chỉ được thực thi **một lần cho câu lệnh UPDATE ấy**. Tuy nhiên, nếu cần biết chính xác giá trị **`OLD.price` và `NEW.price` của mỗi sản phẩm**, trigger theo hàng tiện lợi hơn. Nếu cần tổng hợp tất cả các hàng đã sửa một lần, trigger theo câu lệnh kết hợp **transition tables** thường phù hợp hơn.

~~~text
                 Một câu lệnh UPDATE
                         |
                BEFORE STATEMENT
                         |
                  Chọn các hàng
                         |
              +----------+----------+
              |          |          |
              v          v          v
           Hàng A     Hàng B     Hàng C ...
              |          |          |
           BEFORE ROW trigger (mỗi hàng)
              |          |          |
                Thực hiện thay đổi
              |          |          |
            AFTER ROW trigger (mỗi hàng)
                         |
                AFTER STATEMENT
                         |
                   Kết thúc lệnh
~~~

Sơ đồ cho thấy **các tầng logic**, không mô tả chính xác mọi chi tiết thứ tự vật lý của PostgreSQL: đặc biệt, các sự kiện `AFTER ROW` được xếp hàng và xử lý vào giai đoạn cuối câu lệnh, trước `AFTER STATEMENT` tương ứng. Ngoài ra, các trigger cùng loại được sắp theo tên, có thể có trigger của ràng buộc nội bộ, và một số thao tác như `ON CONFLICT`, `MERGE` hoặc partition routing có quy tắc riêng.

Đây là bài học tự chứa về **trigger theo hàng và theo câu lệnh**, trong chương *Trigger và luật*: cú pháp, ngữ nghĩa `OLD`/`NEW`/giá trị `RETURN`, thứ tự `BEFORE`/`AFTER`, `WHEN`, transition tables, `TRUNCATE`, view triggers, tính nguyên tử, hiệu năng, bảo mật, catalog và các bài thực hành có lời giải.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt số lần kích hoạt `FOR EACH ROW` với `FOR EACH STATEMENT`.
2. Giải thích vì sao statement-level trigger vẫn chạy khi tác động **0 hàng**.
3. Tạo hàm `RETURNS trigger` bằng PL/pgSQL, sử dụng `TG_OP`, `TG_WHEN` và `TG_LEVEL`.
4. Sử dụng `NEW` và `OLD` đúng với `INSERT`, `UPDATE`, `DELETE`.
5. Phân biệt ý nghĩa `RETURN NEW`, `RETURN OLD`, `RETURN NULL` trong trigger `BEFORE ROW` với trigger `AFTER` hoặc `STATEMENT`.
6. Áp dụng `BEFORE ROW` để chuẩn hóa/kiểm tra dữ liệu trước khi ghi.
7. Áp dụng `AFTER ROW` để ghi audit cho từng thay đổi đã thực hiện.
8. Áp dụng `AFTER STATEMENT` để ghi nhận một lần thực thi câu lệnh.
9. Dùng `REFERENCING OLD TABLE/NEW TABLE` để đọc tập hàng bị ảnh hưởng theo lô.
10. Hiểu phạm vi của `WHEN` và `UPDATE OF column`.
11. Giải thích trigger đối với `TRUNCATE`, `INSTEAD OF` trên view, constraint triggers và bảng phân vùng.
12. Đánh giá ảnh hưởng transaction, lỗi và rollback tới dữ liệu mà trigger ghi.
13. Tránh lặp truy vấn N+1, vòng lặp trigger và những cập nhật đệ quy.
14. Xem metadata bằng `pg_trigger` và `pg_get_triggerdef`, quản lý enable/disable và migration.

## 2. Trigger là gì, khác gọi hàm thủ công ở đâu?

Hàm thông thường được gọi tường minh:

~~~sql
SELECT calculate_total(1001);
~~~

Trigger function được PostgreSQL gọi tự động khi điều kiện trên một đối tượng và sự kiện thỏa:

~~~sql
CREATE TRIGGER trigger_name
BEFORE INSERT OR UPDATE
ON schema.table_name
FOR EACH ROW
EXECUTE FUNCTION schema.trigger_function();
~~~

Một trigger bao gồm **hai đối tượng/khái niệm**:

1. **Trigger function:** mã xử lý viết bằng ngôn ngữ hỗ trợ trigger, thông thường `plpgsql`, trả kiểu đặc biệt `trigger`.
2. **Trigger definition:** liên kết hàm với bảng/view, sự kiện, thời điểm và mức thực thi.

### 2.1. Trigger không phải một cron job

Trigger không chạy theo lịch. Nó chạy vì một câu lệnh/sự kiện cụ thể được PostgreSQL thực thi trên đối tượng đã gắn trigger. Nếu cần tổng hợp dữ liệu mỗi đêm, scheduling thường phù hợp hơn trigger ghi lặp theo từng hàng.

### 2.2. Trigger không thay thế mọi ràng buộc

`NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` và các kiểu dữ liệu nên là công cụ ưu tiên cho những bất biến đơn giản, được PostgreSQL hỗ trợ trực tiếp. Trigger hữu ích khi logic cần `OLD`/`NEW`, nhật ký thay đổi, xử lý quan hệ liên bảng hoặc hành vi không biểu diễn được rõ ràng bằng constraint.

### 2.3. Mỗi câu SQL có thể ảnh hưởng nhiều hàng

~~~sql
UPDATE inventory SET quantity = quantity + 1;
~~~

Đây vẫn là **một statement**, dù có hàng triệu rows. Đừng đồng nhất số câu lệnh với số hàng được sửa.

## 3. Cú pháp CREATE TRIGGER tổng quát

~~~sql
CREATE TRIGGER trigger_name
    { BEFORE | AFTER | INSTEAD OF }
    { INSERT | UPDATE [ OF column_name [, ...] ] | DELETE | TRUNCATE }
    ON schema.table_name
    [ REFERENCING
        { OLD TABLE AS old_alias | NEW TABLE AS new_alias } ... ]
    [ FOR [ EACH ] { ROW | STATEMENT } ]
    [ WHEN (condition) ]
    EXECUTE FUNCTION schema.trigger_function(arguments);
~~~

Đây là **mẫu đọc cú pháp**, không phải một câu lệnh thực thi nguyên dạng: các tổ hợp lựa chọn có ràng buộc riêng. Ví dụ, `TRUNCATE` chỉ dùng statement-level; `INSTEAD OF` chỉ dùng row-level trên view; transition relations chỉ áp dụng cho những dạng `AFTER` phù hợp.

### 3.1. Mức trigger

~~~sql
FOR EACH ROW
~~~

và:

~~~sql
FOR EACH STATEMENT
~~~

chỉ định trigger chạy theo từng hàng hay theo toàn bộ câu SQL.

### 3.2. Mặc định là statement-level

Nếu bỏ hẳn mệnh đề `FOR EACH ...`, PostgreSQL mặc định tạo **statement-level trigger**. Để tránh người đọc hiểu nhầm, nên ghi rõ mức trong DDL.

### 3.3. Sự kiện DML

- `INSERT`: thêm hàng.
- `UPDATE`: cập nhật hàng.
- `DELETE`: xóa hàng.
- `TRUNCATE`: làm rỗng nhanh một hoặc nhiều bảng, khác `DELETE FROM ...`.

### 3.4. Thời điểm

- `BEFORE`: trước thao tác tương ứng.
- `AFTER`: sau thao tác tương ứng theo cơ chế trigger.
- `INSTEAD OF`: thay thế thao tác trên view bằng logic trigger.

## 4. Bảng đối chiếu: ROW với STATEMENT

| Tiêu chí | `FOR EACH ROW` | `FOR EACH STATEMENT` |
| --- | --- | --- |
| Số lần gọi cho UPDATE 100 hàng | 100 lần (nếu các hàng đủ điều kiện) | 1 lần |
| Số lần gọi cho UPDATE 0 hàng | 0 | 1 |
| Truy cập `NEW` / `OLD` của từng hàng | Có khi sự kiện phù hợp | Không có row `NEW`/`OLD` trực tiếp |
| `BEFORE` có thể sửa `NEW` | Có với INSERT/UPDATE trên bảng phù hợp | Không |
| `RETURN NULL` có thể bỏ qua thao tác trên một hàng | Có với `BEFORE ROW` | Không |
| Phù hợp audit một bản ghi | Có | Cần transition table nếu muốn chi tiết nhiều hàng |
| Phù hợp log một câu lệnh | Có thể nhưng ghi trùng nhiều lần | Rất phù hợp |
| Tính tổng lô 10.000 hàng | Dễ thành N+1/10.000 lệnh | Có thể set-based với transition tables |
| `TRUNCATE` | Không hỗ trợ | Có |
| `INSTEAD OF` trên view | Có | Không |
| `WHEN` trong trigger thông thường | Hỗ trợ với điều kiện phù hợp | Không hỗ trợ |

**Điểm ghi nhớ:** statement trigger không tự biết “những hàng nào đã thay đổi” chỉ nhờ `TG_OP`. Muốn dữ liệu tập hợp, dùng transition relations hoặc một thiết kế nguồn riêng; không tham chiếu `NEW.price` như trong row trigger.

## 5. BEFORE ROW, AFTER ROW và BEFORE/AFTER STATEMENT

Các mức và thời điểm phục vụ những mục đích khác nhau.

### 5.1. BEFORE ROW

Thường dùng để:

- Chuẩn hóa chuỗi đầu vào trước khi lưu.
- Điền `updated_at` hoặc một thuộc tính dẫn xuất.
- Chặn thay đổi bằng `RAISE EXCEPTION`.
- Bỏ qua một hàng bằng `RETURN NULL` nếu thực sự được thiết kế như vậy.

Ví dụ:

~~~sql
CREATE TRIGGER trg_before_write
BEFORE INSERT OR UPDATE
ON schema.table_name
FOR EACH ROW
EXECUTE FUNCTION schema.prepare_row();
~~~

### 5.2. AFTER ROW

Thường dùng khi cần:

- Audit giá trị đã được chấp nhận.
- Đồng bộ một hàng sang bảng phụ **trong cùng transaction**.
- Tính tác động liên quan đến từng hàng đã ghi.

### 5.3. BEFORE STATEMENT

Thường dùng để ghi log mở đầu của một batch statement, thiết lập kiểm tra cấp statement phù hợp, hoặc chặn cả câu lệnh trước khi thay đổi dữ liệu.

### 5.4. AFTER STATEMENT

Thường dùng để tổng kết kết quả của một câu DML, ghi số hàng ảnh hưởng, hoặc xử lý một tập thay đổi qua transition relations.

### 5.5. Không gắn nhãn AFTER = “đã commit”

`AFTER` nghĩa là sau thao tác theo ngữ nghĩa trigger, **không phải transaction đã COMMIT**. Nếu một lỗi xảy ra sau đó và transaction rollback, các thay đổi database do trigger tạo cũng rollback.

## 6. Trigger function và các biến ngữ cảnh TG_*

Trigger functions trong PL/pgSQL có thể dùng các biến đặc biệt:

| Biến | Nội dung |
| --- | --- |
| `TG_OP` | `INSERT`, `UPDATE`, `DELETE` hoặc `TRUNCATE` |
| `TG_WHEN` | `BEFORE`, `AFTER` hoặc `INSTEAD OF` |
| `TG_LEVEL` | `ROW` hoặc `STATEMENT` |
| `TG_NAME` | Tên trigger đang gọi hàm |
| `TG_TABLE_NAME` | Tên bảng/view gắn trigger |
| `TG_TABLE_SCHEMA` | Schema của bảng/view |
| `TG_RELID` | OID của quan hệ liên quan |
| `TG_NARGS` | Số đối số của trigger definition |
| `TG_ARGV[index]` | Đối số trigger; index bắt đầu từ 0 |
| `NEW` | Bản ghi mới khi sự kiện row phù hợp |
| `OLD` | Bản ghi cũ khi sự kiện row phù hợp |

Ví dụ kiểm tra ngữ cảnh:

~~~sql
CREATE FUNCTION trigger_lab.describe_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE
        'Trigger %, level %, timing %, op %, table %.%',
        TG_NAME, TG_LEVEL, TG_WHEN, TG_OP,
        TG_TABLE_SCHEMA, TG_TABLE_NAME;

    RETURN NULL;
END;
$$;
~~~

Hàm này phù hợp để quan sát **statement-level hoặc AFTER** trong lab, nơi giá trị trả về bị bỏ qua. Không đem gắn làm `BEFORE ROW` trên bảng và trả `NULL` nếu không muốn **hủy thao tác từng hàng**.

### 6.1. TG_ARGV là chuỗi

~~~sql
EXECUTE FUNCTION schema.fn('audit', 'critical');
~~~

Trong PL/pgSQL, `TG_ARGV[0]` là text `audit`. Nếu muốn số, phải parse/cast và kiểm tra giá trị phù hợp.

### 6.2. TG_* khác biến của hàm bình thường

`TG_OP` không có ý nghĩa ngoài ngữ cảnh trigger function. Trigger function được PostgreSQL gọi với ngữ cảnh hệ thống; ứng dụng không gọi nó như `SELECT fn(...)` thông thường.

## 7. OLD và NEW theo sự kiện

| Sự kiện row | `OLD` | `NEW` |
| --- | --- | --- |
| `INSERT` | Không có hàng cũ | Bản ghi được chèn |
| `UPDATE` | Bản ghi trước sửa | Bản ghi sau sửa |
| `DELETE` | Bản ghi trước xóa | Không có bản ghi mới |
| `TRUNCATE` | Không có row trigger | Không có row trigger |

### 7.1. INSERT

~~~sql
IF TG_OP = 'INSERT' THEN
    RAISE NOTICE 'new id=%', NEW.product_id;
END IF;
~~~

### 7.2. UPDATE

~~~sql
IF TG_OP = 'UPDATE' THEN
    RAISE NOTICE 'price: % -> %',
        OLD.price, NEW.price;
END IF;
~~~

### 7.3. DELETE

~~~sql
IF TG_OP = 'DELETE' THEN
    RAISE NOTICE 'deleting id=%',
        OLD.product_id;
END IF;
~~~

### 7.4. Không dùng OLD/NEW cấp statement như một hàng ảo

Trong statement trigger không có một `NEW` cụ thể đại diện cho cả 10.000 hàng. Nếu cần danh sách, xem `REFERENCING NEW TABLE AS ...` ở phần transition tables.

## 8. Giá trị RETURN quyết định gì?

Đây là một khác biệt rất dễ gây lỗi.

### 8.1. BEFORE INSERT/UPDATE FOR EACH ROW

- `RETURN NEW`: cho phép PostgreSQL tiếp tục ghi hàng; có thể ghi giá trị `NEW` đã chỉnh.
- `RETURN NULL`: bỏ qua thao tác đối với **hàng hiện tại**, kéo theo các row triggers sau của hàng đó không chạy theo thông thường.
- Có thể trả một row khác với cấu trúc phù hợp, nhưng thay `NEW` có chủ đích thường rõ ràng hơn.

### 8.2. BEFORE DELETE FOR EACH ROW

- `RETURN OLD`: cho phép tiếp tục xóa hàng.
- `RETURN NULL`: bỏ qua xóa **hàng hiện tại**.

### 8.3. AFTER ROW

Giá trị trả về bị **bỏ qua**; hàm vẫn phải kết thúc đúng kiểu `trigger`, nhưng `RETURN NULL` không có nghĩa hủy một thay đổi đã xảy ra. Muốn từ chối thay đổi, dùng `RAISE EXCEPTION` để làm lỗi statement/transaction theo quy tắc.

### 8.4. BEFORE/AFTER STATEMENT

Giá trị trả về cũng bị bỏ qua. Với statement trigger, `RETURN NULL` thường là cách kết thúc đơn giản và **không có tác dụng bỏ qua cả lệnh SQL**.

### 8.5. INSTEAD OF ROW trên view

Giá trị trả về có ý nghĩa riêng: nếu trigger thực hiện thao tác tương ứng, trả `NEW` đối với INSERT/UPDATE hoặc `OLD` đối với DELETE; `RETURN NULL` cho biết bỏ qua thao tác của hàng đó, ảnh hưởng row count/`RETURNING`. Sẽ có ví dụ riêng.

## 9. Chuẩn bị lab: bảng sản phẩm và hai cấp audit

Để so sánh một cách trực tiếp, ta tạo:

~~~text
trigger_lab.products
       |
       +--- BEFORE ROW: chuẩn hóa sku và updated_at
       |
       +--- AFTER ROW: ghi từng hàng vào product_row_audit
       |
       +--- AFTER STATEMENT: ghi số hàng trong product_statement_audit
~~~

### 9.1. Tạo schema

~~~sql
CREATE SCHEMA trigger_lab;
~~~

Chỉ chạy trên database thử nghiệm; nếu schema đã tồn tại, hãy chọn một schema lab khác hoặc dọn môi trường có chủ đích trước khi thực hiện.

### 9.2. Bảng nguồn

~~~sql
CREATE TABLE trigger_lab.products (
    product_id bigint PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    price numeric(12,2) NOT NULL CHECK (price >= 0),
    stock integer NOT NULL CHECK (stock >= 0),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 9.3. Audit theo từng hàng

~~~sql
CREATE TABLE trigger_lab.product_row_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL,
    operation text NOT NULL,
    before_row jsonb,
    after_row jsonb,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    actor_name text NOT NULL DEFAULT current_user
);
~~~

Không đặt foreign key từ audit tới products: nếu xóa sản phẩm, audit vẫn cần ghi được ID của hàng đã xóa và lưu snapshot. Quyết định retention/bảo mật cho audit cần được thiết kế riêng.

### 9.4. Audit theo câu lệnh

~~~sql
CREATE TABLE trigger_lab.product_statement_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation text NOT NULL,
    rows_affected bigint NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    source_table text NOT NULL
);
~~~

Bảng này lưu **một dòng cho một trigger invocation theo statement**, thay vì một dòng cho mỗi sản phẩm.

## 10. Hàm BEFORE ROW chuẩn hóa giá trị

~~~sql
CREATE FUNCTION trigger_lab.prepare_product_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.sku := upper(btrim(NEW.sku));
    NEW.updated_at := clock_timestamp();

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_10_prepare_product
BEFORE INSERT OR UPDATE
ON trigger_lab.products
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.prepare_product_row();
~~~

### 10.1. Điều gì được sửa?

Với `sku=' ab-01 '`, trigger đặt lại `NEW.sku='AB-01'` trước khi hàng được ghi.

### 10.2. Vì sao phải RETURN NEW?

Nếu function trả `NULL` trong `BEFORE ROW`, thao tác trên hàng bị bỏ qua. Trả `NEW` cho phép hệ thống tiếp tục xử lý với giá trị đã chuẩn hóa.

### 10.3. updated_at và thời gian

`clock_timestamp()` lấy thời gian thực tại lúc gọi. Nó có thể khác nhau giữa các hàng trong một statement nhiều hàng; nếu nghiệp vụ muốn mọi hàng trong statement dùng một mốc ổn định, có thể thiết kế dùng `statement_timestamp()` hoặc một timestamp được cung cấp rõ từ ứng dụng.

### 10.4. Không tự cập nhật cùng bảng bằng UPDATE

Trong `BEFORE ROW`, việc gán `NEW.sku := ...` thường tốt hơn chạy:

~~~sql
UPDATE trigger_lab.products
SET sku = ...
WHERE product_id = NEW.product_id;
~~~

Câu `UPDATE` lồng có thể tạo trigger recursion, lock và overhead. Với cột của chính hàng đang xử lý, hãy sửa `NEW`.

## 11. Hàm AFTER ROW ghi lịch sử từng hàng

~~~sql
CREATE FUNCTION trigger_lab.audit_product_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO trigger_lab.product_row_audit (
            product_id, operation, before_row, after_row
        ) VALUES (
            NEW.product_id, TG_OP, NULL, to_jsonb(NEW)
        );
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO trigger_lab.product_row_audit (
            product_id, operation, before_row, after_row
        ) VALUES (
            NEW.product_id, TG_OP,
            to_jsonb(OLD), to_jsonb(NEW)
        );
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO trigger_lab.product_row_audit (
            product_id, operation, before_row, after_row
        ) VALUES (
            OLD.product_id, TG_OP, to_jsonb(OLD), NULL
        );
        RETURN OLD;
    END IF;

    RAISE EXCEPTION 'Unexpected trigger operation %', TG_OP;
END;
$$;

CREATE TRIGGER trg_20_audit_product_row
AFTER INSERT OR UPDATE OR DELETE
ON trigger_lab.products
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.audit_product_row();
~~~

### 11.1. Vì sao dùng AFTER?

Ở thời điểm AFTER, trigger quan sát giá trị hàng đã qua các bước xử lý `BEFORE` liên quan, nên audit có thể ghi dữ liệu thực tế đã được đưa qua thao tác, chẳng hạn `sku='AB-01'` sau chuẩn hóa.

### 11.2. Lưu JSONB snapshot

`to_jsonb(OLD)` và `to_jsonb(NEW)` lưu biểu diễn dữ liệu của hàng trước/sau. Điều này tiện cho audit, nhưng có thể tốn dung lượng khi hàng rất rộng, có trường nhạy cảm hoặc JSONB lớn.

### 11.3. Audit là dữ liệu giao dịch

Lệnh ghi vào `product_row_audit` nằm trong **cùng transaction** với DML gốc. Nếu transaction rollback, audit row này cũng rollback. Nó không phải nhật ký bất biến vượt qua mọi rollback hoặc một audit log bên ngoài database.

### 11.4. RETURN trong AFTER ROW

Hàm trả `NEW`/`OLD` để rõ ràng, nhưng ở `AFTER ROW` giá trị return không quyết định hàng gốc được ghi hay không. Không dùng `RETURN NULL` ở AFTER để hy vọng hủy INSERT.

## 12. Hàm AFTER STATEMENT sử dụng transition tables

Ta muốn ghi một dòng tổng hợp cho mỗi câu `INSERT`, `UPDATE` hoặc `DELETE`; không chạy một `COUNT(*)` trên toàn bảng nguồn vì cách đó không biết số hàng **của chính câu lệnh vừa xảy ra**.

PostgreSQL cung cấp **transition relations** khi tạo trigger phù hợp:

~~~sql
CREATE FUNCTION trigger_lab.audit_product_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_rows bigint;
BEGIN
    IF TG_OP = 'DELETE' THEN
        SELECT count(*)
        INTO v_rows
        FROM old_rows;
    ELSE
        SELECT count(*)
        INTO v_rows
        FROM new_rows;
    END IF;

    INSERT INTO trigger_lab.product_statement_audit (
        operation, rows_affected, source_table
    ) VALUES (
        TG_OP, v_rows, TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
    );

    RETURN NULL;
END;
$$;
~~~

`old_rows` và `new_rows` ở đây **không phải bảng thường**. Chúng là tên được trigger definition cấp cho tập hàng thay đổi khi statement chạy. Chỉ nhánh thích hợp truy cập transition table hiện diện cho loại sự kiện.

### 12.1. Trigger cho INSERT

~~~sql
CREATE TRIGGER trg_30_products_insert_stmt
AFTER INSERT
ON trigger_lab.products
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();
~~~

### 12.2. Trigger cho UPDATE

~~~sql
CREATE TRIGGER trg_31_products_update_stmt
AFTER UPDATE
ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();
~~~

### 12.3. Trigger cho DELETE

~~~sql
CREATE TRIGGER trg_32_products_delete_stmt
AFTER DELETE
ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();
~~~

### 12.4. Vì sao tách ba CREATE TRIGGER?

Khi dùng transition tables, PostgreSQL có những ràng buộc cho event và trigger definition. Chia riêng theo `INSERT`, `UPDATE`, `DELETE` làm rõ tập `OLD TABLE`/`NEW TABLE` được cấp và tránh dùng một định nghĩa nhiều event không hợp lệ với transition relations.

### 12.5. RETURN NULL của AFTER STATEMENT

Đây là giá trị trả về hợp lệ và bị bỏ qua, không có nghĩa SQL statement vừa thực thi bị hủy.

## 13. Chạy INSERT nhiều hàng: so sánh số lần gọi

~~~sql
INSERT INTO trigger_lab.products (
    product_id, sku, price, stock
) VALUES
    (1, ' ab-01 ', 10.00, 5),
    (2, ' kb-02',  20.00, 10),
    (3, 'mi-03 ',  30.00, 0);
~~~

Đây là **một câu INSERT** tạo ba rows.

### 13.1. Kết quả từ BEFORE ROW

~~~sql
SELECT
    product_id, sku, price, stock, updated_at
FROM trigger_lab.products
ORDER BY product_id;
~~~

Các SKU được chuẩn hóa:

~~~text
1  AB-01  10.00   5
2  KB-02  20.00  10
3  MI-03  30.00   0
~~~

### 13.2. Kết quả audit row

~~~sql
SELECT audit_id, operation, product_id,
       after_row ->> 'sku' AS sku
FROM trigger_lab.product_row_audit
ORDER BY audit_id;
~~~

Có **3 dòng INSERT** trong `product_row_audit` vì trigger `AFTER ROW` chạy cho ba sản phẩm.

### 13.3. Kết quả audit statement

~~~sql
SELECT operation, rows_affected, source_table
FROM trigger_lab.product_statement_audit
ORDER BY audit_id;
~~~

Có **1 dòng INSERT**, `rows_affected=3`. Transition table `new_rows` chứa ba hàng của câu INSERT, dù bảng gốc có thể chứa nhiều hàng hơn sau này.

### 13.4. Số dòng audit không phải tổng số statements hệ thống

Trong bài, log chỉ được tạo khi thao tác trên `trigger_lab.products` kích hoạt trigger. Các câu `SELECT` không kích hoạt trigger DML này; những thao tác trên bảng audit cũng không tự đi qua trigger của products.

## 14. UPDATE nhiều hàng: ROW chạy nhiều lần

~~~sql
UPDATE trigger_lab.products
SET price = price + 5
WHERE product_id IN (1, 2);
~~~

Kết quả:

- Sản phẩm 1: giá `10.00 → 15.00`.
- Sản phẩm 2: giá `20.00 → 25.00`.
- Có **2 lần** chạy `BEFORE ROW`.
- Có **2 lần** chạy `AFTER ROW` ghi audit.
- Có **1 lần** chạy `AFTER STATEMENT`, ghi `rows_affected=2`.

### 14.1. Kiểm tra sự khác nhau trước/sau

~~~sql
SELECT
    product_id,
    before_row ->> 'price' AS old_price,
    after_row ->> 'price' AS new_price
FROM trigger_lab.product_row_audit
WHERE operation = 'UPDATE'
ORDER BY audit_id;
~~~

### 14.2. UPDATE số lượng hàng lớn

Với 100.000 hàng, row audit tạo 100.000 INSERT vào bảng audit, có thể làm WAL, storage và transaction latency tăng mạnh. Statement audit chỉ tạo một dòng, nhưng chi phí đọc transition table (nếu dùng) vẫn phụ thuộc số hàng thay đổi.

### 14.3. Không tự xem UPDATE là một “thay đổi giá trị”

PostgreSQL có thể xử lý `UPDATE products SET stock = stock` như một thao tác UPDATE trên hàng, dù `stock` không đổi. Row trigger `UPDATE` vẫn có thể chạy; nếu chỉ muốn audit thay đổi thực sự ở một field, cần `WHEN (OLD.field IS DISTINCT FROM NEW.field)` hoặc điều kiện khác.

## 15. UPDATE không khớp hàng: STATEMENT vẫn chạy

~~~sql
UPDATE trigger_lab.products
SET stock = 999
WHERE product_id < 0;
~~~

Với dữ liệu lab, không có sản phẩm ID âm.

### 15.1. Kết quả

- Không có hàng nào thực sự UPDATE.
- Không có row-level UPDATE trigger invocation.
- Statement-level UPDATE trigger vẫn được gọi **một lần**.
- Transition table `new_rows` rỗng.
- `product_statement_audit` nhận một dòng `UPDATE, rows_affected=0`.

### 15.2. Đây là đặc tính có ích cho log lệnh

Nếu mục tiêu là biết ứng dụng vừa **cố thực hiện một lệnh UPDATE**, statement trigger đáp ứng ngay cả khi không có hàng khớp.

### 15.3. Nhưng đừng nhầm với log mọi câu SQL

Statement trigger DML không quan sát `SELECT` và không ghi log các câu lệnh vào một bảng khác. Nó gắn với các sự kiện được khai báo trên quan hệ cụ thể.

### 15.4. Câu lệnh thất bại có ghi audit bền vững không?

Nếu statement gây exception rồi transaction rollback, bản ghi statement audit cũng không được commit. Muốn ghi nhật ký các lệnh **thất bại** không mất theo rollback, phải thiết kế logging/observability riêng ngoài transaction phù hợp.

## 16. DELETE nhiều hàng và OLD

~~~sql
DELETE FROM trigger_lab.products
WHERE product_id = 3;
~~~

### 16.1. BEFORE/AFTER ROW cho DELETE

Chỉ `OLD` có bản ghi sản phẩm bị xóa. Audit row lưu `before_row=to_jsonb(OLD)`, `after_row=NULL`.

### 16.2. Transition OLD TABLE

Statement-level DELETE trigger đọc `old_rows` để biết **tập hàng đã xóa** và đếm số hàng, không phải đọc `products` sau khi xóa (vì hàng đã không còn).

### 16.3. Kết quả lab

~~~sql
SELECT operation, rows_affected
FROM trigger_lab.product_statement_audit
ORDER BY audit_id;
~~~

Theo thứ tự các thao tác đã thực hiện, những dòng statement audit tương ứng:

| operation | rows_affected |
| --- | ---: |
| INSERT | 3 |
| UPDATE | 2 |
| UPDATE | 0 |
| DELETE | 1 |

Audit theo hàng có 3 INSERT, 2 UPDATE và 1 DELETE — tổng 6 dòng ở ví dụ cơ bản.

## 17. Kiểm chứng tính nguyên tử bằng ROLLBACK

Chạy một thay đổi tạm thời:

~~~sql
BEGIN;

UPDATE trigger_lab.products
SET price = price + 100
WHERE product_id = 1;

SELECT price
FROM trigger_lab.products
WHERE product_id = 1;

SELECT operation, product_id
FROM trigger_lab.product_row_audit
ORDER BY audit_id DESC
LIMIT 1;

ROLLBACK;
~~~

### 17.1. Điều gì xảy ra?

Trong transaction trước rollback, SELECT có thể nhìn thấy giá sản phẩm đã tăng và audit được ghi bởi trigger trong cùng transaction.

Sau `ROLLBACK`, cập nhật sản phẩm **và** dòng audit tương ứng đều không còn hiệu lực.

### 17.2. Identity sequence có thể vẫn có khoảng trống

PostgreSQL sequences không có cùng semantics rollback như bản ghi bảng. Sau một transaction rollback, `audit_id` có thể bị nhảy số. Không suy có lỗi audit chỉ vì các ID không liên tục.

### 17.3. Tác động bên ngoài không tự rollback

Nếu trigger gọi một extension có side effect bên ngoài, gửi email hoặc HTTP request không đồng bộ với transaction, tác động ấy có thể không được hoàn tác khi database rollback. Với integration đáng tin cậy, cần thiết kế **transactional outbox** hoặc kiến trúc xử lý sau commit.

## 18. WHEN trong row trigger

Khi chỉ quan tâm sự thay đổi thực của giá, có thể thêm điều kiện:

~~~sql
CREATE TABLE trigger_lab.price_change_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL,
    old_price numeric(12,2) NOT NULL,
    new_price numeric(12,2) NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE FUNCTION trigger_lab.log_price_change_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_lab.price_change_log (
        product_id, old_price, new_price
    ) VALUES (
        NEW.product_id, OLD.price, NEW.price
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_40_price_changed
AFTER UPDATE
ON trigger_lab.products
FOR EACH ROW
WHEN (OLD.price IS DISTINCT FROM NEW.price)
EXECUTE FUNCTION trigger_lab.log_price_change_row();
~~~

### 18.1. IS DISTINCT FROM tốt hơn <> khi có NULL

`IS DISTINCT FROM` là phép so sánh xử lý SQL `NULL` một cách rõ ràng. Ở lab giá đã `NOT NULL`, nhưng ví dụ này hữu ích khi chuyển sang các cột nullable.

### 18.2. Test giá không đổi

~~~sql
UPDATE trigger_lab.products
SET price = price
WHERE product_id = 1;
~~~

Các trigger UPDATE thông thường vẫn có thể chạy trên hàng; nhưng `trg_40_price_changed` không ghi log mới vì `OLD.price` và `NEW.price` không khác.

### 18.3. Test giá đổi

~~~sql
UPDATE trigger_lab.products
SET price = 17.50
WHERE product_id = 1;
~~~

Lúc này trigger có `WHEN` được kích hoạt để ghi một dòng audit chuyên biệt về giá.

### 18.4. WHEN không phải WHERE của câu lệnh nguồn

`WHERE product_id = 1` chọn các hàng để UPDATE; `WHEN (OLD.price IS DISTINCT FROM NEW.price)` chỉ quyết định **một row trigger có gọi function hay không** sau khi một hàng liên quan đã được xác định.

## 19. WHEN với BEFORE và AFTER

Với `BEFORE ROW`, biểu thức `WHEN` được đánh giá trước khi gọi trigger function tương ứng. Với `AFTER ROW`, điều kiện có thể được đánh giá ngay sau thao tác hàng để tránh xếp hàng những event trigger không cần thiết.

### 19.1. Mức statement không dùng WHEN thông thường

Không viết:

~~~sql
-- Không hợp lệ cho statement trigger thông thường:
-- CREATE TRIGGER ...
-- AFTER UPDATE ON ...
-- FOR EACH STATEMENT
-- WHEN (NEW.price > 0)
-- EXECUTE FUNCTION ...;
~~~

Không có `NEW` của một hàng ở cấp statement. Điều kiện cho toàn tập dữ liệu cần đặt trong function, có thể đọc transition table.

### 19.2. WHEN không chứa subquery tùy ý

Predicate trong `WHEN` có giới hạn cú pháp, đặc biệt không hỗ trợ subqueries trực tiếp. Nếu logic cần tra cứu bảng khác, đưa vào trigger function với quy tắc transaction/locking rõ ràng thay vì cố viết một `SELECT` trong `WHEN`.

### 19.3. Không chọn WHEN chỉ để giảm tên hàm

Nếu business rule cực phức tạp, viết function có nhánh điều kiện được test rõ ràng có thể dễ bảo trì hơn một mệnh đề WHEN dài. Sự đánh đổi là chi phí gọi function khi không thỏa.

## 20. UPDATE OF column: cột được nhắc, không hẳn giá trị đổi

Cú pháp:

~~~sql
CREATE TRIGGER trg_update_price_listed
AFTER UPDATE OF price
ON trigger_lab.products
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.log_price_change_row();
~~~

**Đây là ví dụ minh họa về tiêu chí chọn event**; nếu chạy thêm trên lab, hãy lưu ý nó sẽ ghi price log trên mỗi UPDATE có `price` trong danh sách `SET`, kể cả khi giá không đổi.

### 20.1. UPDATE OF price

Nó chủ yếu quan tâm câu lệnh `UPDATE` có nhắc tới `price` trong phần cập nhật (theo quy tắc PostgreSQL), **không bảo đảm giá thực sự thay đổi**.

### 20.2. So với WHEN

~~~sql
UPDATE trigger_lab.products
SET price = price
WHERE product_id = 1;
~~~

Ở đây `UPDATE OF price` phù hợp vì cột price được liệt kê, nhưng `WHEN (OLD.price IS DISTINCT FROM NEW.price)` là false.

### 20.3. BEFORE triggers có thể sửa thêm cột

Nếu một `BEFORE UPDATE` trigger tự sửa `NEW.price` dù câu lệnh gốc không liệt kê price trong `SET`, điều đó không tự khiến một trigger `UPDATE OF price` được chọn. Đây là lý do **sự kiện theo cột** và **so sánh OLD/NEW** khác nhau.

### 20.4. Không kết hợp UPDATE OF với transition tables tùy tiện

Với PostgreSQL transition relations, `UPDATE` trigger dùng `REFERENCING OLD TABLE/NEW TABLE` **không được có danh sách `UPDATE OF column`**. Trong lab, trigger statement dùng `AFTER UPDATE` không gắn `OF price`.

## 21. Transition tables: tập OLD và NEW theo câu lệnh

Đây là công cụ giúp statement trigger không chỉ biết `TG_OP` mà còn biết **các hàng thực sự thay đổi**.

| DML | Transition relation thường dùng | Chứa gì? |
| --- | --- | --- |
| INSERT | `REFERENCING NEW TABLE AS new_rows` | Hàng đã chèn |
| UPDATE | `OLD TABLE AS old_rows` và `NEW TABLE AS new_rows` | Trước và sau cập nhật |
| DELETE | `REFERENCING OLD TABLE AS old_rows` | Hàng đã xóa |
| TRUNCATE | Không có row transition tables | Không có tập row-level tương ứng |

### 21.1. Quan hệ chuyển tiếp chỉ tồn tại trong trigger execution

Không thể gọi:

~~~sql
SELECT * FROM new_rows;
~~~

từ một session SQL bình thường rồi mong thấy transition table của trigger trước. `new_rows` chỉ có ý nghĩa ở ngữ cảnh trigger được định nghĩa với `REFERENCING NEW TABLE AS new_rows`.

### 21.2. Khác OLD và NEW của từng row

`OLD` và `NEW` trong row trigger là **một record**. `old_rows` và `new_rows` trong transition table là **tập hàng**, có thể đọc bằng SQL set-based.

### 21.3. AFTER triggers là phạm vi chính

Transition relations dành cho các loại `AFTER` trigger được PostgreSQL hỗ trợ trên quan hệ phù hợp. Chúng không phải một tùy chọn chung để biến mọi `BEFORE STATEMENT` thành trigger biết toàn bộ hàng sẽ thay đổi.

### 21.4. Cột tên alias do DDL đặt

Tên `old_rows` và `new_rows` không cố định. Bạn có thể chọn tên khác:

~~~sql
REFERENCING OLD TABLE AS previous_rows
            NEW TABLE AS current_rows
~~~

Khi đó function phải đọc đúng alias ấy.

## 22. Tổng hợp set-based với transition tables

Giả sử muốn tính **tổng chênh lệch giá** của một câu `UPDATE`, nhưng không ghi một row log cho mỗi sản phẩm.

### 22.1. Tạo bảng log lô

~~~sql
CREATE TABLE trigger_lab.price_batch_audit (
    batch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    changed_products bigint NOT NULL,
    total_price_delta numeric(14,2) NOT NULL,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 22.2. Hàm AFTER STATEMENT

~~~sql
CREATE FUNCTION trigger_lab.log_price_batch()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_count bigint;
    v_delta numeric(14,2);
BEGIN
    SELECT
        count(*),
        coalesce(sum(n.price - o.price), 0)
    INTO v_count, v_delta
    FROM old_rows AS o
    JOIN new_rows AS n
      ON n.product_id = o.product_id
    WHERE o.price IS DISTINCT FROM n.price;

    INSERT INTO trigger_lab.price_batch_audit (
        changed_products,
        total_price_delta
    ) VALUES (
        v_count, v_delta
    );

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_50_price_batch
AFTER UPDATE
ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.log_price_batch();
~~~

### 22.3. Chạy UPDATE có vài hàng

~~~sql
UPDATE trigger_lab.products
SET price = price + 2
WHERE product_id IN (1, 2);
~~~

Trigger tính các chênh lệch bằng **một SELECT** trên hai transition tables thay vì gọi truy vấn tổng hợp riêng trong từng row trigger.

### 22.4. Giới hạn của JOIN theo khóa

Ví dụ ghép `old_rows`/`new_rows` theo `product_id` vì lab **không thay primary key**. Nếu statement UPDATE có thể đổi chính cột khóa ghép, các hàng trước/sau có thể không ghép được bằng cùng giá trị cũ/mới. Cần thiết kế một identifier ổn định hoặc cơ chế pairing phù hợp.

### 22.5. Không coi mỗi UPDATE đều đổi price

Điều kiện `o.price IS DISTINCT FROM n.price` bảo đảm chỉ đếm những sản phẩm có chênh lệch giá thực sự. Một UPDATE chỉ thay `stock` sẽ vẫn gọi statement trigger, nhưng dòng batch có thể có `changed_products=0` và `total_price_delta=0`.

### 22.6. Set-based không miễn phí

PostgreSQL vẫn cần hình thành/duyệt tập transition rows. Với UPDATE hàng triệu rows, chi phí có thể cao, nhưng thường tránh được nhiều round trips SQL nội bộ và log từng row không cần thiết.

## 23. Không nhầm statement trigger với transaction trigger

Một transaction có thể chứa nhiều câu SQL:

~~~sql
BEGIN;

UPDATE trigger_lab.products
SET stock = stock + 1
WHERE product_id = 1;

UPDATE trigger_lab.products
SET stock = stock + 1
WHERE product_id = 2;

COMMIT;
~~~

`AFTER UPDATE FOR EACH STATEMENT` sẽ được gọi **hai lần** trong ví dụ này, không phải một lần cho toàn transaction.

### 23.1. Một statement có nhiều hàng

Một câu:

~~~sql
UPDATE trigger_lab.products
SET stock = stock + 1
WHERE product_id IN (1, 2);
~~~

lại gọi statement trigger **một lần**, dù hai rows thay đổi.

### 23.2. Muốn audit “một lần mỗi transaction”?

Không thể đơn giản thêm `FOR EACH TRANSACTION` vào `CREATE TRIGGER` DML: PostgreSQL không có lựa chọn trigger DML đó theo cùng mô hình. Có thể thiết kế transaction ID/outbox/collector tùy bài toán, nhưng phải xét retry, savepoint và nhiều câu lệnh trong một transaction.

### 23.3. Transaction ID không luôn là “request ID”

Một HTTP request có thể dùng nhiều transactions; nhiều thao tác trong một transaction cũng không tự mang chung một business request ID. Nếu cần trace nghiệp vụ, nên truyền correlation ID theo mô hình ứng dụng hoặc session metadata được quản lý đúng.

## 24. TRUNCATE: chỉ statement-level

`TRUNCATE` không thực hiện từng hàng theo cách `DELETE` làm, nên **không kích hoạt row-level DELETE triggers**.

### 24.1. Tạo trigger TRUNCATE

~~~sql
CREATE FUNCTION trigger_lab.audit_product_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_lab.product_statement_audit (
        operation, rows_affected, source_table
    ) VALUES (
        TG_OP,
        0,
        TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
    );

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_60_products_truncate_stmt
AFTER TRUNCATE
ON trigger_lab.products
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_truncate();
~~~

### 24.2. Ý nghĩa rows_affected=0 trong ví dụ

Đây là **giá trị minh họa/sentinel** vì trigger TRUNCATE không có transition table các hàng bị xóa. Nó **không tuyên bố TRUNCATE đã xóa đúng 0 hàng**. Trên hệ thống thật, nên đặt một cột nullable hoặc trường thông tin `count_known=false` thay vì ghi số 0 gây hiểu lầm.

### 24.3. Thử trong transaction rồi rollback

~~~sql
BEGIN;

TRUNCATE TABLE trigger_lab.products;

SELECT count(*) FROM trigger_lab.products;

ROLLBACK;
~~~

Sau rollback, dữ liệu bảng và bản ghi audit TRUNCATE của transaction ấy được khôi phục theo semantics giao dịch. Lưu ý `TRUNCATE` có hành vi locking mạnh và các lưu ý MVCC riêng; chỉ thử trong lab.

### 24.4. DELETE khác TRUNCATE

~~~sql
DELETE FROM trigger_lab.products;
~~~

có thể gọi DELETE row trigger cho từng sản phẩm cùng DELETE statement trigger. Ngược lại, `TRUNCATE` chỉ gọi các trigger `ON TRUNCATE` tương ứng, không gọi DELETE row audit.

### 24.5. Quyền và FK

`TRUNCATE` cần quyền thích hợp và có ràng buộc với foreign keys; không phải một cách để bỏ qua logic toàn vẹn tham chiếu trong mọi tình huống.

## 25. INSTEAD OF trigger trên VIEW

Một view đôi khi cần hành vi ghi tùy chỉnh thay vì cập nhật bảng nền theo đường mặc định.

### 25.1. Tạo view đơn giản

~~~sql
CREATE VIEW trigger_lab.v_catalog AS
SELECT
    product_id, sku, price, stock
FROM trigger_lab.products;
~~~

### 25.2. Tạo hàm INSTEAD OF INSERT

~~~sql
CREATE FUNCTION trigger_lab.insert_catalog_row()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_lab.products (
        product_id, sku, price, stock
    ) VALUES (
        NEW.product_id, NEW.sku, NEW.price, NEW.stock
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_insert_catalog
INSTEAD OF INSERT
ON trigger_lab.v_catalog
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.insert_catalog_row();
~~~

### 25.3. INSERT qua view

~~~sql
INSERT INTO trigger_lab.v_catalog (
    product_id, sku, price, stock
) VALUES (
    4, 'ca-04 ', 15.00, 7
);

SELECT product_id, sku
FROM trigger_lab.products
WHERE product_id = 4;
~~~

Trong bảng nguồn, `sku` được chuẩn hóa bởi `BEFORE INSERT ROW` của `products`, nên kết quả được lưu là `CA-04`.

### 25.4. INSTEAD OF chỉ có mức ROW

Không có `INSTEAD OF ... FOR EACH STATEMENT` tương đương. Nếu cần một statement-level trigger trên view, PostgreSQL có mô hình `BEFORE/AFTER STATEMENT` phù hợp, nhưng `INSTEAD OF` để thay từng thao tác view là row-level.

### 25.5. RETURNING và NEW

`RETURN NEW` cho biết trigger đã thực hiện thao tác cho hàng, nhưng giá trị trả ra cho một `INSERT ... RETURNING` trên view phụ thuộc row mà trigger trả lại. Nếu bảng nền chuẩn hóa SKU, `RETURN NEW` từ view có thể vẫn mang SKU đầu vào chưa chuẩn hóa. Nếu API cần giá trị đã lưu chính xác, trigger/view phải thiết kế đường trả giá trị phù hợp thay vì mặc nhiên xem `NEW` của view là bản ghi cuối cùng trong bảng nền.

### 25.6. Không dùng INSTEAD OF trên bảng thường

`INSTEAD OF` dành cho view với cơ chế được hỗ trợ; với bảng, dùng `BEFORE`/`AFTER` hoặc các cấu trúc SQL phù hợp.

## 26. Trigger trên bảng phân vùng

Partitioning làm cho quan hệ giữa row-level và statement-level triggers cần được hiểu rõ.

### 26.1. Statement trigger gắn trên bảng cha

Khi một câu DML nhắm vào partitioned parent, statement-level trigger trên **bảng cha** được kích hoạt theo câu lệnh mục tiêu; statement-level triggers riêng trên các partition con không tự chạy chỉ vì hàng được route xuống chúng trong cùng lệnh.

### 26.2. Row trigger gắn ở nơi hàng được thao tác

Các row-level triggers của partitioned table có thể được sao chép/duy trì trên partitions theo cơ chế PostgreSQL và phiên bản sử dụng. Hàng được route tới partition nào thì trigger hàng tương ứng có thể thực thi trên partition thực tế ấy.

### 26.3. Câu SQL nhắm trực tiếp partition con

Nếu ứng dụng gửi `INSERT/UPDATE/DELETE` trực tiếp đến partition con thay vì parent, trigger statement-level của quan hệ là **partition con được nhắm** chứ không đương nhiên là parent.

### 26.4. UPDATE di chuyển hàng giữa partitions

Khi đổi partition key khiến hàng chuyển partition, PostgreSQL có thể xử lý thao tác mức hàng theo luồng DELETE ở partition nguồn và INSERT ở partition đích, có các quy tắc trigger riêng cho việc di chuyển hàng. Không xây audit đơn giản dựa trên giả định “mọi partition move chỉ tạo đúng một UPDATE ROW event”.

### 26.5. Transition relations trên parent

Trong các phiên bản hỗ trợ, transition tables của statement trigger trên partitioned parent có thể biểu diễn các hàng bị tác động qua partitions theo ngữ nghĩa của lệnh. Kiểm tra ví dụ thực tế với phiên bản PostgreSQL đang triển khai, đặc biệt khi có partition movement.

### 26.6. Không thay partition key từ BEFORE ROW để route tùy ý

PostgreSQL có các giới hạn trong việc sửa partition key bằng BEFORE ROW trigger khiến hàng phải đi sang một partition khác. Nếu cần routing phức tạp, hãy thiết kế giá trị partition key ở ứng dụng/truy vấn hoặc cơ chế phù hợp thay vì kỳ vọng BEFORE trigger luôn có thể thay đích.

## 27. Thứ tự nhiều trigger cùng loại

Trên một bảng, có thể có nhiều trigger có cùng event, timing và level.

### 27.1. PostgreSQL sắp theo tên trigger

Những trigger cùng kind và cùng điều kiện sự kiện được PostgreSQL kích hoạt theo **thứ tự tên**. Vì vậy quy ước tên như:

~~~text
trg_10_normalize
trg_20_validate
trg_30_audit
~~~

có thể giúp biểu diễn thứ tự mong muốn trong một nhóm trigger cùng tầng.

### 27.2. Tác động của BEFORE ROW

Một `BEFORE ROW` trigger có thể trả `NEW` đã sửa, và trigger `BEFORE ROW` sau đó có thể quan sát giá trị đã sửa ấy. Nếu trigger trước trả `NULL`, các bước xử lý theo hàng tiếp theo của hàng đó bị bỏ qua.

### 27.3. AFTER ROW không sửa NEW để ghi lại

AFTER ROW function nhận `NEW` nhưng việc sửa record `NEW` rồi trả lại không thay đổi hàng đã lưu. Nếu cần chuẩn hóa cột của hàng gốc, dùng `BEFORE ROW` hoặc thay đổi câu SQL nguồn.

### 27.4. Đừng dựa vào alphabet giữa các nhóm khác timing

Thứ tự `BEFORE`/`AFTER` và row/statement có semantics riêng. Không viết logic chỉ hoạt động nếu một AFTER STATEMENT chạy trước một BEFORE ROW vì tên của nó đứng trước.

## 28. ON CONFLICT và hai loại trigger của INSERT/UPDATE

~~~sql
INSERT INTO trigger_lab.products (
    product_id, sku, price, stock
) VALUES (
    1, 'AB-01', 99.00, 1
)
ON CONFLICT (product_id)
DO UPDATE SET price = EXCLUDED.price;
~~~

Trong một lệnh `INSERT ... ON CONFLICT DO UPDATE`, PostgreSQL có thể kích hoạt cả các trigger theo đường INSERT và UPDATE theo quy tắc chi tiết.

### 28.1. Statement-level triggers

Với `ON CONFLICT DO UPDATE`, các statement-level triggers của INSERT và UPDATE có thể được kích hoạt **dù nhánh UPDATE thực sự không tác động hàng nào**, theo quy tắc thứ tự của PostgreSQL.

### 28.2. Row-level BEFORE events

Trên hàng gặp conflict, các hiệu ứng của `BEFORE INSERT ROW` và `BEFORE UPDATE ROW` có thể cùng có vai trò khi thực hiện đường cập nhật. Nếu logic normalization không idempotent, kết quả dễ bất ngờ.

### 28.3. Không cộng statement counts như một đếm đơn hàng

Nếu một lệnh UPSERT gọi cả INSERT và UPDATE statement triggers, không thể cộng số lần gọi statement-level trigger để suy số sản phẩm được chèn hay sửa. Cần đọc transition tables hoặc kết quả DML thực tế theo từng sự kiện.

### 28.4. ON CONFLICT DO NOTHING

Một INSERT bị conflict và chọn `DO NOTHING` vẫn là câu INSERT; statement-level INSERT trigger phù hợp vẫn có thể chạy, trong khi không có hàng mới để kích hoạt AFTER INSERT ROW.

### 28.5. MERGE

Các phiên bản PostgreSQL có `MERGE` áp các quy tắc trigger theo những hành động `INSERT`/`UPDATE`/`DELETE` đã xác định trong statement và những hàng thực sự đi qua từng nhánh. Đừng giả định một câu MERGE chỉ tương đương một trigger event chung; xem semantics của phiên bản và kiểm tra plan/test trường hợp.

## 29. Constraint triggers và thời điểm trì hoãn

PostgreSQL còn có **constraint trigger** để thực thi những kiểm tra liên quan tới tính toàn vẹn có thể trì hoãn theo transaction.

### 29.1. Khác trigger DML thông thường

Constraint trigger do người dùng tạo bằng `CREATE CONSTRAINT TRIGGER` có những giới hạn: nó là **AFTER ROW trigger** trên quan hệ được hỗ trợ, có thể khai báo `DEFERRABLE` và `INITIALLY DEFERRED`.

### 29.2. Ví dụ cú pháp minh họa

~~~sql
-- Minh họa mẫu; cần định nghĩa function enforce_rule()
-- đúng với một invariant trước khi thực thi.
--
-- CREATE CONSTRAINT TRIGGER trg_business_rule
-- AFTER INSERT OR UPDATE
-- ON trigger_lab.products
-- DEFERRABLE INITIALLY DEFERRED
-- FOR EACH ROW
-- EXECUTE FUNCTION trigger_lab.enforce_rule();
~~~

### 29.3. SET CONSTRAINTS

Với constraint trigger thích hợp, `SET CONSTRAINTS ... IMMEDIATE/DEFERRED` có thể thay đổi thời điểm kiểm tra trong transaction theo quy tắc PostgreSQL.

### 29.4. WHEN có thời điểm riêng

Với constraint trigger có `WHEN`, điều kiện của sự kiện hàng được xét **ngay khi hàng thay đổi**, không hoãn tới cuối transaction như phần gọi hàm có thể được hoãn. Điều này có thể ảnh hưởng việc sự kiện được đưa vào hàng đợi.

### 29.5. Không thay FK/UNIQUE đơn giản bằng trigger

PostgreSQL có constraint machinery chuyên biệt cho `FOREIGN KEY`, `UNIQUE`, `CHECK`. Khi business rule được diễn đạt bằng constraint chuẩn, sử dụng constraint thường dễ đúng và dễ tối ưu hơn tự xây cơ chế khóa/kiểm tra trong trigger.

## 30. Giao dịch đồng thời và tính đúng

Trigger function chạy trong **transaction của câu DML gốc**, nhưng điều đó không tự khiến mọi phép kiểm tra liên bảng trở nên không có race condition.

### 30.1. Ví dụ kiểm tra tồn kho

Giả sử hai transactions cùng định mua 5 sản phẩm cuối cùng, cả hai trigger đều:

~~~sql
SELECT stock
FROM trigger_lab.products
WHERE product_id = 1;
~~~

Nếu cả hai kiểm tra một số lượng tồn mà không khóa/cập nhật atomically phù hợp, cả hai có thể cùng nghĩ mình đủ hàng và dẫn tới bán vượt tồn.

### 30.2. Ưu tiên cập nhật có điều kiện

Một mẫu thường rõ hơn:

~~~sql
UPDATE trigger_lab.products
SET stock = stock - 5
WHERE product_id = 1
  AND stock >= 5
RETURNING product_id, stock;
~~~

Ứng dụng xem có hàng nào được trả về; PostgreSQL dùng row locks/recheck thích hợp để xử lý tranh chấp trên hàng. Cần kết hợp transaction và quy tắc nghiệp vụ đúng.

### 30.3. Isolation level vẫn quan trọng

`READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE` có semantics khác nhau. Trigger không vượt qua MVCC hoặc tự tạo serializable business invariants. Nếu kiểm tra liên bảng phức tạp, cần xem khóa, constraint, isolation và retry.

### 30.4. Không gửi hành động bên ngoài trước COMMIT

Một trigger gọi API thanh toán/email bên ngoài có thể tạo side effect dù DB rollback. Thiết kế outbox trong transaction và worker xử lý sau khi commit thường phù hợp hơn cho tích hợp hệ thống.

## 31. Lỗi trong trigger và transaction rollback

~~~sql
CREATE FUNCTION trigger_lab.reject_negative_stock()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.stock < 0 THEN
        RAISE EXCEPTION
            'Stock cannot be negative for product %',
            NEW.product_id
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
~~~

Có thể gắn function thành `BEFORE INSERT OR UPDATE FOR EACH ROW`, nhưng lab đã có `CHECK (stock >= 0)` — đây là ví dụ minh họa để phân biệt cơ chế, **không cần tạo trigger thừa**.

### 31.1. RAISE EXCEPTION

Exception không được xử lý sẽ làm thất bại statement; những thay đổi DML và audit do các trigger liên quan tạo trong statement sẽ không được commit theo hành vi giao dịch.

### 31.2. Không nhầm với RETURN NULL

`RETURN NULL` trong BEFORE ROW thường chỉ bỏ qua **một hàng**, không báo lỗi cho caller theo cùng cách `RAISE EXCEPTION`. Nếu vi phạm dữ liệu cần fail rõ ràng, exception hoặc constraint phù hợp hơn.

### 31.3. Try/catch trong PL/pgSQL

PL/pgSQL có `EXCEPTION WHEN ...` và subtransaction semantics trong các block xử lý lỗi. Nhưng bắt mọi exception và bỏ qua có thể làm caller tin câu DML thành công dù business rule thất bại. Chỉ bắt lỗi được hiểu rõ và giữ contract tường minh.

### 31.4. Statement trigger có chạy sau khi statement thất bại?

Không nên dựa vào AFTER STATEMENT trigger để ghi một bản audit thành công cho một lệnh đã lỗi; exception làm flow statement/giao dịch rollback theo quy tắc. Log thất bại cần cơ chế riêng.

## 32. Tác động hiệu năng: O(số hàng) và N+1

Một row trigger thực thi 10.000 lần có thể rất tốn chi phí nếu mỗi lần:

~~~sql
SELECT sum(...)
FROM some_large_table
WHERE ...;
~~~

### 32.1. N+1 từ database-side

Một SQL UPDATE lớn có thể phát sinh N lần query phụ từ trigger, dù ứng dụng chỉ gửi **một SQL**. Đây là lỗi hiệu năng thường bị bỏ sót vì nhìn SQL ở application thấy ít round trips.

### 32.2. Chuyển sang statement trigger với transition table

Thay vì:

~~~text
10000 row trigger calls
    -> 10000 SELECT
    -> 10000 INSERT audit rows
~~~

có thể cân nhắc:

~~~text
1 statement trigger
    -> 1 SELECT set-based trên NEW TABLE/OLD TABLE
    -> 1 INSERT tổng hợp hoặc INSERT SELECT theo lô
~~~

### 32.3. Không phải lúc nào statement trigger cũng tốt hơn

Nếu cần audit **đầy đủ OLD/NEW của từng hàng**, một row trigger đơn giản và index/partition audit hợp lý có thể dễ đúng hơn. Transition table vẫn cần duyệt các hàng khi ghi chi tiết.

### 32.4. Đo cả write latency

Đánh giá trigger bằng:

- Thời gian INSERT/UPDATE/DELETE.
- WAL volume và kích thước audit.
- Lock wait/deadlock.
- CPU, buffer accesses, temporary files.
- Autovacuum và retention của bảng audit.

### 32.5. Gợi ý đo

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE trigger_lab.products
SET price = price
WHERE product_id = 1;
~~~

**Lưu ý:** `EXPLAIN ANALYZE` thực sự thực thi câu DML; nếu chỉ muốn đo, bọc trong transaction lab rồi `ROLLBACK`, hiểu rằng sequence values có thể không rollback. Với nhiều dạng plan, PostgreSQL có thể hiển thị thống kê thời gian trigger theo tên.

## 33. Audit table: dung lượng và retention

Lưu cả `before_row` và `after_row` dạng JSONB rất thuận tiện nhưng có chi phí.

### 33.1. Không sao chép PII không cần thiết

Nếu sản phẩm có metadata nhạy cảm, audit có thể lưu dữ liệu đó thêm một lần. Cần chính sách masking, quyền truy cập, encryption/retention tương ứng.

### 33.2. Chỉ lưu field cần thiết

Đôi khi chỉ cần:

~~~text
product_id
old_price
new_price
changed_at
actor
~~~

thay vì snapshot toàn bộ hàng.

### 33.3. Dọn audit theo chính sách

Audit tăng theo số thay đổi. Có thể phân vùng theo thời gian, archive hoặc xóa theo retention đã được phê duyệt; không để một trigger audit nhẹ trở thành bảng hàng tỷ dòng không được quản trị.

### 33.4. Trigger audit không phải event bus tuyệt đối

Hàng audit được ghi trong transaction và có thể rollback. Nó chỉ phản ánh các đường DML đã đi qua trigger được bật trên những bảng phù hợp. Nếu muốn phát sự kiện ra hệ thống khác sau commit, cân nhắc outbox/CDC.

## 34. Đệ quy và trigger tự kích hoạt

Một function gắn trên `products` chạy:

~~~sql
UPDATE trigger_lab.products
SET stock = stock + 1
WHERE product_id = NEW.product_id;
~~~

khi chính nó đang xử lý UPDATE trên `products` có thể gọi lại trigger và gây vòng lặp.

### 34.1. Dùng NEW trong BEFORE ROW nếu sửa cùng hàng

~~~sql
NEW.stock := NEW.stock + 1;
RETURN NEW;
~~~

là cách sửa cột của chính hàng đang được xử lý mà không gửi một UPDATE mới.

### 34.2. pg_trigger_depth()

PostgreSQL có `pg_trigger_depth()` cho biết độ sâu trigger hiện tại:

~~~sql
SELECT pg_trigger_depth();
~~~

Ở ngoài trigger thông thường, giá trị thường là 0. Bên trong chuỗi trigger, giá trị tăng theo độ sâu.

### 34.3. Không dùng depth guard để che logic sai

Một điều kiện:

~~~sql
IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
END IF;
~~~

có thể chặn recursion trong vài trường hợp, nhưng đồng thời **bỏ qua hành vi cần thiết** khi thao tác được tạo hợp lệ bởi trigger khác. Ưu tiên thiết kế tránh vòng lặp, điều kiện idempotent và tách trách nhiệm rõ ràng.

### 34.4. Deadlock có thể do nhiều trigger ghi chéo

Nếu bảng A trigger cập nhật B còn bảng B trigger cập nhật A, hai transactions thao tác theo thứ tự khác nhau có thể deadlock. Chuẩn hóa thứ tự khóa và cân nhắc giảm side effects trong triggers.

## 35. Trigger và tham chiếu khóa ngoại

PostgreSQL dùng các cơ chế trigger nội bộ cho một số ràng buộc như foreign key.

### 35.1. Không tự xóa trigger nội bộ

Một phần trigger hiện trong `pg_trigger` có `tgisinternal=true`; chúng không tương đương trigger audit do ứng dụng viết. Tắt/xóa chúng có thể phá toàn vẹn dữ liệu.

### 35.2. Thứ tự và cascade

Hành vi `ON DELETE CASCADE` hoặc `ON UPDATE CASCADE` của foreign key có thể thực thi thay đổi trên bảng khác, nơi các trigger tương ứng được kích hoạt theo quy tắc PostgreSQL. Không chỉ tính trigger của câu SQL đầu tiên khi đánh giá tổng số side effects.

### 35.3. Không viết trigger thay FK theo kiểu “SELECT EXISTS” tùy ý

Một kiểm tra `SELECT EXISTS(...)` trong row trigger có thể có race condition với transactions đồng thời nếu không có khóa/isolation phù hợp. FK chuẩn có cơ chế kiểm tra toàn vẹn tham chiếu được tích hợp.

## 36. Xem trigger bằng pg_trigger

~~~sql
SELECT
    t.tgname AS trigger_name,
    c.oid::regclass AS table_name,
    t.tgenabled,
    t.tgisinternal,
    pg_get_triggerdef(t.oid, true) AS definition
FROM pg_trigger AS t
JOIN pg_class AS c
  ON c.oid = t.tgrelid
JOIN pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'trigger_lab'
ORDER BY c.relname, t.tgname;
~~~

### 36.1. tgenabled

Cho biết trạng thái kích hoạt của trigger theo ngữ cảnh session replication role. Các giá trị liên quan gồm những trạng thái kích hoạt thông thường, replica-only, always hoặc disabled.

### 36.2. tgisinternal

Giúp phân biệt triggers do hệ thống tạo (chẳng hạn liên quan constraint) với triggers do người dùng định nghĩa.

### 36.3. pg_get_triggerdef

Trả DDL dạng văn bản, giúp biết sự kiện, timing, level, `WHEN`, transition tables và function được gọi mà không phải tự giải mã bitmask `tgtype`.

### 36.4. Đọc function body

~~~sql
SELECT pg_get_functiondef(
    'trigger_lab.audit_product_row()'::regprocedure
);
~~~

Trigger definition và function body là **hai phần khác nhau**; xem cả hai khi điều tra một hành vi bất ngờ.

## 37. Enable, disable và drop trigger

### 37.1. Tắt một trigger do ứng dụng quản lý

~~~sql
ALTER TABLE trigger_lab.products
DISABLE TRIGGER trg_20_audit_product_row;
~~~

### 37.2. Bật lại

~~~sql
ALTER TABLE trigger_lab.products
ENABLE TRIGGER trg_20_audit_product_row;
~~~

### 37.3. Không bật/tắt tùy tiện trên production

Trong thời gian audit trigger bị tắt, những UPDATE/DELETE vẫn có thể xảy ra mà không có row audit. Khi bật lại, PostgreSQL **không tự truy tạo các dòng audit đã bỏ lỡ**.

### 37.4. DISABLE TRIGGER USER và ALL

`ALTER TABLE ... DISABLE TRIGGER USER` nhắm các user triggers, trong khi `ALL` có thể liên quan cả triggers phục vụ ràng buộc nội bộ và có hạn chế quyền cao. Không dùng `DISABLE TRIGGER ALL` làm phương án tăng tốc import tùy tiện vì có thể phá integrity.

### 37.5. Drop có định danh bảng

~~~sql
DROP TRIGGER IF EXISTS trg_20_audit_product_row
ON trigger_lab.products;
~~~

Lệnh xóa **trigger definition**, không mặc nhiên xóa function `trigger_lab.audit_product_row()` nếu function còn được dùng nơi khác.

### 37.6. Không nhầm function và trigger

~~~sql
DROP FUNCTION trigger_lab.audit_product_row();
~~~

có thể bị chặn nếu trigger vẫn phụ thuộc function; không dùng `CASCADE` để vượt dependency nếu chưa nắm tác động.

## 38. session_replication_role và môi trường replication

PostgreSQL có tham số `session_replication_role` liên quan đến việc firing một số triggers và rules trong những chế độ replication.

### 38.1. Đây không phải “nút tắt trigger để làm nhanh”

Thay `session_replication_role` có thể ảnh hưởng việc enforcement của một số constraints/triggers quan trọng. Chỉ dùng theo quy trình DBA có kiểm soát, đặc biệt trong replication/restore.

### 38.2. Phân biệt ENABLE ALWAYS / ENABLE REPLICA

PostgreSQL có những trạng thái trigger dùng để quyết định khi nào trigger chạy trong các replication roles. Nếu hệ thống dùng logical replication, cần hiểu tác động tới audit và integrity ở phía subscriber.

### 38.3. Audit chỉ ở primary?

Không tự suy audit triggers trên subscriber được chạy giống primary cho mọi thay đổi được replicate. Cần kiểm tra cấu hình replication, trạng thái trigger và nơi dữ liệu được ghi.

## 39. Quyền và SECURITY DEFINER

Trigger function có thể được khai báo `SECURITY INVOKER` hoặc `SECURITY DEFINER` theo mô hình routine của PostgreSQL.

### 39.1. Ưu tiên quyền tối thiểu

Nếu một user được phép UPDATE sản phẩm nhưng không có quyền INSERT trực tiếp audit, bạn có thể cân nhắc một trigger function `SECURITY DEFINER` do role tin cậy sở hữu để audit chạy với quyền phù hợp.

### 39.2. Rủi ro search_path

Nếu dùng `SECURITY DEFINER`, cần khóa `search_path` về schema tin cậy và `pg_temp` theo mẫu phòng vệ, đồng thời dùng schema-qualified object names:

~~~sql
-- Minh họa phần khai báo function.
-- SECURITY DEFINER
-- SET search_path = pg_catalog, trigger_lab, pg_temp
~~~

### 39.3. Actor audit cần được hiểu đúng

`current_user` có thể phản ánh role thực thi theo ngữ cảnh security; với SECURITY DEFINER có thể là function owner, không phải danh tính end user của ứng dụng. Nếu cần “ai thật sự yêu cầu thay đổi”, hệ thống phải thiết kế cách truyền actor/correlation ID an toàn, không tin mù quáng một session variable client có thể tự đặt.

### 39.4. Không tạo security bypass

Hàm SECURITY DEFINER có thể đọc/ghi vượt quyền caller theo owner. Cần giới hạn những thao tác cho phép, validate inputs, quản lý EXECUTE/owner và kiểm tra RLS/security model.

## 40. Trigger và RULE: khác cơ chế

PostgreSQL còn có **rule system** để rewrite truy vấn:

~~~sql
CREATE RULE ...
~~~

### 40.1. Rule là cơ chế rewrite

Rule có thể thay/biến đổi query trong giai đoạn rewrite, không phải “một hàm được gọi sau mỗi hàng” như row trigger.

### 40.2. Trigger là event-driven execution

Trigger chạy theo event, timing và level đã định nghĩa, có `TG_OP`/`OLD`/`NEW` trong ngữ cảnh phù hợp.

### 40.3. Đừng dùng rule để mô phỏng mọi kiểm tra theo hàng

Rule rewrite có thể có hành vi khác dự đoán khi query nhiều hàng hoặc `RETURNING`. Với audit/validation side effects, trigger thường là lựa chọn trực tiếp hơn, còn constraint vẫn là ưu tiên khi áp dụng được.

### 40.4. View có nhiều cơ chế updatability

View có thể tự động updatable trong một số trường hợp, dùng `INSTEAD OF` trigger hoặc dùng rules tùy thiết kế. Không coi chúng là ba cách hoàn toàn tương đương về row counts, `RETURNING` và xử lý nhiều hàng.

## 41. Chọn ROW hay STATEMENT theo use case

| Yêu cầu | Hướng nên cân nhắc |
| --- | --- |
| Chuẩn hóa SKU trước INSERT | `BEFORE INSERT FOR EACH ROW`, sửa `NEW` |
| Đặt updated_at mỗi hàng | `BEFORE UPDATE FOR EACH ROW` |
| Ghi OLD/NEW của mỗi order | `AFTER UPDATE FOR EACH ROW` |
| Chặn một giá trị bất hợp lệ | Constraint hoặc `BEFORE ROW` với exception |
| Ghi mỗi lần UPDATE chạy, kể cả 0 hàng | `AFTER UPDATE FOR EACH STATEMENT` |
| Tổng hợp mọi hàng UPDATE một lần | `AFTER STATEMENT` + transition tables |
| Ghi toàn bộ DELETE của một statement theo lô | `AFTER DELETE` + `OLD TABLE` |
| Theo dõi TRUNCATE | Statement-level TRUNCATE trigger |
| Ghi dữ liệu qua một view đặc biệt | `INSTEAD OF FOR EACH ROW` |
| Kiểm tra constraint có thể deferrable | Constraint trigger nếu thực sự cần |
| Tính toán nặng trên triệu hàng | SQL set-based, batch job hoặc statement transition table |
| Gửi event ra hệ thống khác sau COMMIT | Transactional outbox/CDC/worker |

### 41.1. Một bảng có thể có cả hai loại

Lab chứng minh `BEFORE ROW` chuẩn hóa, `AFTER ROW` audit và `AFTER STATEMENT` đếm số hàng hoàn toàn có thể cùng tồn tại trên một bảng.

### 41.2. Không làm thêm công việc chỉ vì trigger đã sẵn

Nếu một phép biến đổi đơn giản có thể giải quyết bằng generated column/constraint/statement SQL, trigger tăng độ phức tạp debug và migration không cần thiết.

## 42. Debug trigger đúng cách

Khi thấy một UPDATE gây thêm log, thứ tự kiểm tra nên là:

1. Câu SQL nào được thực thi, nhắm vào bảng/partition nào?
2. Trigger nào được gắn trên quan hệ đó?
3. `TG_OP`, timing và level là gì?
4. Có nhiều triggers cùng event được gọi theo thứ tự tên không?
5. `BEFORE ROW` có sửa `NEW` hay `RETURN NULL` không?
6. Có `WHEN` hoặc `UPDATE OF` thay đổi điều kiện firing không?
7. Có statement trigger chạy kể cả khi 0 hàng không?
8. Có `ON CONFLICT`/`MERGE`/FK cascade/partition move ảnh hưởng event không?
9. Có trigger recursion hoặc side-effect DML sang bảng khác không?
10. Có transaction rollback khiến audit “mất” dù đã thấy trước rollback không?

### 42.1. RAISE NOTICE trong lab

~~~sql
RAISE NOTICE 'trigger=%, op=%, level=%',
    TG_NAME, TG_OP, TG_LEVEL;
~~~

Là công cụ quan sát đơn giản. Với sản xuất, không nên log mỗi row của batch triệu hàng vì lượng log sẽ khổng lồ.

### 42.2. pg_get_triggerdef và pg_get_functiondef

Một trigger có thể gắn tới một function đã được `CREATE OR REPLACE` sau đó. Phải xem định nghĩa hiện tại của **cả trigger lẫn function**.

### 42.3. Test 0, 1 và N hàng

Đây là bộ test tối thiểu cho sự khác nhau giữa row và statement triggers. Một trigger chạy đúng với một hàng có thể bị lỗi performance/logic với nhiều hàng, hoặc bỏ sót log khi 0 hàng.

## 43. Bài tập thực hành

Các bài dùng schema `trigger_lab`. Với bài tạo thêm trigger minh họa, có thể trả lời bằng SQL mà không nhất thiết tạo trực tiếp trên bảng lab để tránh phát sinh log trùng. Không chạy thao tác dọn/xóa dữ liệu thật trên production.

### Bài 1. Số lần gọi

Một câu `UPDATE` ảnh hưởng 500 hàng. `AFTER UPDATE FOR EACH ROW` và `AFTER UPDATE FOR EACH STATEMENT` chạy bao nhiêu lần?

### Bài 2. Không có hàng

Một `DELETE` không khớp hàng nào. Hai loại trigger `AFTER DELETE` chạy bao nhiêu lần?

### Bài 3. Mặc định

Nếu bỏ `FOR EACH ...` trong `CREATE TRIGGER` thì PostgreSQL chọn mức nào?

### Bài 4. TG_OP

Viết trigger function log `TG_OP`, `TG_NAME` và `TG_LEVEL` bằng `RAISE NOTICE`.

### Bài 5. NEW và OLD

Trong trigger `UPDATE ROW`, lấy giá trị price trước và sau thay đổi như thế nào?

### Bài 6. BEFORE INSERT chuẩn hóa

Viết function dùng `upper(btrim(...))` để chuẩn hóa `NEW.sku` và vẫn cho phép INSERT.

### Bài 7. RETURN NULL

Điều gì xảy ra nếu `BEFORE INSERT FOR EACH ROW` trả `NULL`?

### Bài 8. AFTER RETURN NULL

`AFTER INSERT FOR EACH ROW` trả `NULL` có hủy hàng đã chèn không?

### Bài 9. Audit từng hàng

Viết câu `CREATE TRIGGER` gắn function `audit_product_row` vào cả INSERT/UPDATE/DELETE ở mức ROW.

### Bài 10. Statement audit

Viết câu `CREATE TRIGGER` gọi `audit_product_statement` sau INSERT và dùng `NEW TABLE AS new_rows`.

### Bài 11. Transition OLD TABLE

Viết câu `CREATE TRIGGER` sau DELETE với `OLD TABLE AS old_rows`.

### Bài 12. UPDATE transition tables

Viết câu `CREATE TRIGGER` sau UPDATE để có cả tập OLD/NEW.

### Bài 13. Số hàng INSERT

Một INSERT thêm 3 sản phẩm. Bảng audit row và audit statement nhận lần lượt bao nhiêu dòng theo lab cơ bản?

### Bài 14. UPDATE 0 hàng

Viết câu UPDATE không khớp ID nào và giải thích kết quả `rows_affected` trong statement audit.

### Bài 15. ROLLBACK

Trong một transaction có UPDATE sản phẩm và audit trigger chạy, sau `ROLLBACK` audit có còn không? Vì sao `audit_id` có thể không liên tục?

### Bài 16. WHEN

Viết mệnh đề WHEN cho trigger UPDATE chỉ ghi log khi `OLD.price` và `NEW.price` khác nhau, kể cả khi có NULL.

### Bài 17. UPDATE OF price

`UPDATE products SET price = price` có kích hoạt trigger `UPDATE OF price` không? Có nhất thiết giá thực thay đổi?

### Bài 18. Thay đổi bởi BEFORE trigger

Nếu câu UPDATE chỉ SET stock nhưng BEFORE trigger sửa NEW.price, một trigger `UPDATE OF price` có chắc chạy không?

### Bài 19. Tổng hợp chênh giá

Viết SELECT từ `old_rows` JOIN `new_rows` để tính tổng `new.price - old.price` cho các hàng có giá thay đổi, giả sử product_id không đổi.

### Bài 20. Statement vs transaction

Một transaction gồm hai câu UPDATE độc lập. Statement-level UPDATE trigger chạy bao nhiêu lần?

### Bài 21. TRUNCATE

TRUNCATE kích hoạt DELETE row trigger không? Viết trigger theo statement để ghi sự kiện TRUNCATE.

### Bài 22. INSTEAD OF

INSTEAD OF trigger gắn vào bảng thường hay view? Nó có thể dùng FOR EACH STATEMENT không?

### Bài 23. View ghi qua trigger

Viết trigger function cho phép INSERT một hàng vào `v_catalog` và chuyển dữ liệu sang `products`.

### Bài 24. Thứ tự

Nếu có hai BEFORE UPDATE ROW triggers tên `trg_a` và `trg_b`, trigger nào được gọi trước khi cùng điều kiện phù hợp?

### Bài 25. Recursion

Vì sao một BEFORE UPDATE trigger lại chạy `UPDATE products SET ...` trên cùng hàng dễ gây vòng lặp? Nên sửa thế nào?

### Bài 26. Constraint trigger

Constraint trigger deferrable có thể là statement-level không? Mô tả điểm khác với row trigger thường.

### Bài 27. ON CONFLICT

Tại sao không cộng số lần gọi statement trigger INSERT/UPDATE để suy số hàng UPSERT thành công?

### Bài 28. Bảng phân vùng

Nếu câu UPDATE nhắm parent partitioned table, statement trigger trên từng partition có mặc nhiên chạy không?

### Bài 29. pg_trigger

Viết query xem tên, trạng thái enable và DDL của triggers trên bảng products.

### Bài 30. Disable trigger

Viết DDL tắt/bật riêng `trg_20_audit_product_row`. Nêu nguy cơ khi tắt audit trigger trong production.

### Bài 31. Audit actor

Vì sao `current_user` không luôn là end-user khi trigger function dùng `SECURITY DEFINER`?

### Bài 32. Business invariant

Giả sử hai transactions cùng mua 5 món cuối, vì sao SELECT stock trong trigger chưa chắc bảo đảm không oversell? Đề xuất một câu UPDATE có điều kiện.

### Bài 33. Hiệu năng

Một UPDATE sửa 100.000 rows, row trigger mỗi lần SELECT một bảng lớn. Vấn đề gì xảy ra? Giải pháp nào tận dụng transition tables?

### Bài 34. pg_trigger_depth

Giải thích `pg_trigger_depth()` và vì sao không nên coi `IF depth>1 THEN RETURN` là giải pháp mặc định.

### Bài 35. Trigger và RULE

Khác nhau cơ bản giữa query rewrite rule và DML trigger là gì?

### Bài 36. Transactional outbox

Vì sao gửi HTTP request trực tiếp từ trigger không bảo đảm rollback đồng nhất với database? Outbox giúp gì?

### Bài 37. Audit dữ liệu cũ

Nếu trigger audit bị disable một ngày rồi enable lại, có tự có log cho các thay đổi đã bỏ qua không?

### Bài 38. EXPLAIN ANALYZE

`EXPLAIN (ANALYZE, BUFFERS) UPDATE ...` có thực sự thực hiện UPDATE và kích hoạt trigger không? Cần thử thế nào an toàn?

### Bài 39. TRUNCATE count

Vì sao một TRUNCATE statement trigger không thể tự đếm row qua `OLD TABLE` như DELETE?

### Bài 40. Chọn công cụ

Chọn giữa `CHECK`, BEFORE ROW trigger, AFTER ROW trigger, AFTER STATEMENT trigger cho bốn mục tiêu: stock không âm; chuẩn hóa SKU; audit OLD/NEW giá; ghi một dòng log mỗi câu UPDATE kể cả 0 hàng.

## 44. Gợi ý lời giải

### Bài 1–3. Tần suất

UPDATE 500 hàng: ROW 500 lần, STATEMENT 1 lần nếu không có lọc WHEN hoặc hành vi bỏ qua theo hàng. DELETE 0 hàng: ROW 0, STATEMENT 1. Không khai báo `FOR EACH ...` thì mặc định là STATEMENT.

### Bài 4. TG_*

~~~sql
CREATE FUNCTION trigger_lab.log_trigger_context()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'name %, op %, level %',
        TG_NAME, TG_OP, TG_LEVEL;
    RETURN NULL;
END;
$$;
~~~

Chỉ gắn vào loại trigger mà `RETURN NULL` không bỏ qua row gốc (ví dụ AFTER STATEMENT).

### Bài 5. OLD/NEW

~~~sql
RAISE NOTICE '% -> %', OLD.price, NEW.price;
~~~

### Bài 6. Chuẩn hóa

~~~sql
CREATE FUNCTION trigger_lab.normalize_sku_answer()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.sku := upper(btrim(NEW.sku));
    RETURN NEW;
END;
$$;
~~~

Gắn với `BEFORE INSERT FOR EACH ROW` trên bảng thích hợp.

### Bài 7–8. RETURN

`BEFORE ROW RETURN NULL` bỏ qua thao tác trên hàng hiện tại. `AFTER ROW RETURN NULL` bị bỏ qua và **không** hủy thao tác đã ghi.

### Bài 9. Row audit

~~~sql
CREATE TRIGGER trg_product_audit_answer
AFTER INSERT OR UPDATE OR DELETE
ON trigger_lab.products
FOR EACH ROW
EXECUTE FUNCTION trigger_lab.audit_product_row();
~~~

Không cần tạo thật nếu lab đã có trigger cùng mục đích, vì sẽ làm log trùng.

### Bài 10–12. Transition table triggers

~~~sql
CREATE TRIGGER trg_insert_answer
AFTER INSERT ON trigger_lab.products
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();

CREATE TRIGGER trg_delete_answer
AFTER DELETE ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();

CREATE TRIGGER trg_update_answer
AFTER UPDATE ON trigger_lab.products
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_statement();
~~~

Đây là DDL đáp án; không chạy trùng với những trigger lab đã tạo nếu chỉ cần thực hành phân tích cú pháp.

### Bài 13–14. Row count

Một INSERT 3 hàng tạo 3 dòng row audit, 1 dòng statement audit có `rows_affected=3`. UPDATE không khớp rows vẫn có một invocation statement trigger; `rows_affected=0` và không tạo row audit.

~~~sql
UPDATE trigger_lab.products
SET stock = 1
WHERE product_id < 0;
~~~

### Bài 15. Transaction

Update và audit row ghi cùng transaction nên đều rollback. Sequence/identity cấp ID thường không rollback số đã cấp, nên có thể có khoảng trống ID.

### Bài 16–18. WHEN vs UPDATE OF

~~~sql
WHEN (OLD.price IS DISTINCT FROM NEW.price)
~~~

`UPDATE OF price` được xét theo cột nêu trong statement; `SET price=price` vẫn có thể kích hoạt dù giá không đổi. Việc BEFORE trigger đổi thêm price không tự làm trigger `UPDATE OF price` được chọn khi price không ở danh sách cập nhật gốc.

### Bài 19. Set-based delta

~~~sql
SELECT
    count(*) AS changed_products,
    coalesce(sum(n.price - o.price), 0) AS total_delta
FROM old_rows AS o
JOIN new_rows AS n
  ON n.product_id = o.product_id
WHERE n.price IS DISTINCT FROM o.price;
~~~

Chỉ thực thi trong trigger có các transition aliases ấy.

### Bài 20. Per statement

Hai UPDATE statements trong một transaction làm statement-level UPDATE trigger được gọi hai lần.

### Bài 21. TRUNCATE

TRUNCATE không gọi DELETE row triggers. Ví dụ:

~~~sql
CREATE TRIGGER trg_truncate_answer
AFTER TRUNCATE
ON trigger_lab.products
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_lab.audit_product_truncate();
~~~

### Bài 22–23. View trigger

`INSTEAD OF` gắn trên view và chỉ dùng `FOR EACH ROW`.

~~~sql
CREATE FUNCTION trigger_lab.insert_catalog_answer()
RETURNS trigger LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_lab.products (
        product_id, sku, price, stock
    ) VALUES (
        NEW.product_id, NEW.sku, NEW.price, NEW.stock
    );
    RETURN NEW;
END;
$$;
~~~

Gắn bằng `CREATE TRIGGER ... INSTEAD OF INSERT ON trigger_lab.v_catalog FOR EACH ROW ...`.

### Bài 24–25. Thứ tự và recursion

Với cùng loại/timing/event, trigger tên `trg_a` chạy trước `trg_b`. Gửi `UPDATE` mới lên cùng bảng trong BEFORE ROW có thể kích hoạt lại trigger và vòng lặp; ưu tiên sửa `NEW.column` rồi `RETURN NEW`.

### Bài 26. Constraint trigger

Constraint trigger deferrable được tạo dạng `AFTER ROW` trên đối tượng phù hợp, không phải statement-level trigger thông thường. Nó có thể được trì hoãn kiểm tra bằng cơ chế constraint.

### Bài 27. ON CONFLICT

UPSERT có thể kích hoạt cả INSERT/UPDATE statement triggers theo quy tắc, kể cả nhánh không đổi hàng. Đếm invocations không đồng nghĩa đếm inserted/updated rows.

### Bài 28. Partition

Không mặc nhiên. Khi statement nhắm parent, statement trigger trên parent được kích hoạt; statement triggers trên từng child không tự chạy do routing. Row triggers và partition movement có quy tắc riêng.

### Bài 29. Catalog

~~~sql
SELECT
    tgname,
    tgenabled,
    pg_get_triggerdef(oid, true)
FROM pg_trigger
WHERE tgrelid = 'trigger_lab.products'::regclass
ORDER BY tgname;
~~~

### Bài 30. Tắt/bật

~~~sql
ALTER TABLE trigger_lab.products
DISABLE TRIGGER trg_20_audit_product_row;

ALTER TABLE trigger_lab.products
ENABLE TRIGGER trg_20_audit_product_row;
~~~

Việc tắt trigger làm thiếu audit trong khoảng ấy; bật lại không sinh log bù.

### Bài 31. Actor

Trong SECURITY DEFINER, `current_user` có thể phản ánh function owner thay vì end-user. Cần cơ chế actor identity được ứng dụng cung cấp và xác thực an toàn.

### Bài 32. Stock concurrency

~~~sql
UPDATE trigger_lab.products
SET stock = stock - 5
WHERE product_id = 1
  AND stock >= 5
RETURNING product_id, stock;
~~~

Kiểm tra số hàng được cập nhật và transaction outcome. Không chỉ đọc stock rồi quyết định trên một snapshot cũ.

### Bài 33. Performance

Row trigger chạy 100.000 lần và mỗi lần query lớn tạo N+1, I/O và lock overhead cao. Chuyển logic tổng hợp sang AFTER STATEMENT đọc transition table set-based, hoặc batch ngoài trigger nếu nghiệp vụ cho phép.

### Bài 34. Depth

`pg_trigger_depth()` đo độ sâu của trigger đang thực thi, nhưng chặn mọi lời gọi depth>1 có thể bỏ luôn thay đổi hợp lệ do một trigger khác gây ra. Tách trách nhiệm và thiết kế idempotent tốt hơn.

### Bài 35. RULE

Rule biến đổi truy vấn ở giai đoạn rewrite; DML trigger chạy function theo event/timing/level với OLD/NEW/TG context phù hợp.

### Bài 36. Outbox

Side effect HTTP bên ngoài không tự được database rollback khi transaction lỗi. Transactional outbox ghi event vào bảng cùng transaction; worker chỉ xử lý những event đã commit theo cơ chế delivery/retry/idempotency được thiết kế.

### Bài 37. Missing audits

Không. Trigger đã tắt không ghi những thay đổi đó. Cần reconcile/backfill từ nguồn khác nếu nghiệp vụ yêu cầu.

### Bài 38. EXPLAIN

`EXPLAIN ANALYZE` chạy statement thật và kích hoạt trigger phù hợp. Chỉ đo trong lab, có thể:

~~~sql
BEGIN;
EXPLAIN (ANALYZE, BUFFERS)
UPDATE trigger_lab.products
SET stock = stock
WHERE product_id = 1;
ROLLBACK;
~~~

### Bài 39. TRUNCATE count

TRUNCATE không cung cấp OLD TABLE như DELETE transition relation, và không kích hoạt row DELETE. Nếu cần biết chính xác số hàng trước TRUNCATE, cần một cơ chế đo/thiết kế riêng và hiểu locking/consistency.

### Bài 40. Chọn công cụ

| Mục tiêu | Giải pháp |
| --- | --- |
| Stock không âm | `CHECK (stock >= 0)` |
| Chuẩn hóa SKU | `BEFORE INSERT/UPDATE FOR EACH ROW` |
| Audit OLD/NEW giá | `AFTER UPDATE FOR EACH ROW` với WHEN |
| Một log mỗi UPDATE kể cả 0 hàng | `AFTER UPDATE FOR EACH STATEMENT` |

## 45. Bảng tra cứu nhanh

| Câu hỏi | Công cụ/điểm nhớ |
| --- | --- |
| Chạy mỗi hàng? | `FOR EACH ROW` |
| Chạy mỗi câu SQL? | `FOR EACH STATEMENT` |
| Mặc định nếu không ghi mức? | `FOR EACH STATEMENT` |
| UPDATE 0 hàng? | Statement trigger vẫn chạy; row trigger không |
| Sửa giá trị trước khi ghi? | `BEFORE ROW`, sửa `NEW`, `RETURN NEW` |
| Bỏ qua một hàng trước khi ghi? | `BEFORE ROW RETURN NULL` |
| Chặn bằng lỗi? | `RAISE EXCEPTION` / constraint |
| Log row đã cập nhật? | `AFTER UPDATE FOR EACH ROW` |
| Xác định loại event? | `TG_OP` |
| Kiểm tra mức/timing? | `TG_LEVEL`, `TG_WHEN` |
| Đọc OLD/NEW trên UPDATE ROW? | `OLD.column`, `NEW.column` |
| Đọc cả batch INSERT? | `REFERENCING NEW TABLE AS new_rows` |
| Đọc cả batch DELETE? | `REFERENCING OLD TABLE AS old_rows` |
| Đọc trước/sau batch UPDATE? | `OLD TABLE` + `NEW TABLE` |
| Chỉ khi giá thực sự đổi? | `WHEN (OLD.price IS DISTINCT FROM NEW.price)` |
| Khi cột nằm trong UPDATE SET? | `UPDATE OF price` |
| TRUNCATE? | Statement-level TRUNCATE trigger |
| View write handler? | `INSTEAD OF ... FOR EACH ROW` |
| Nhiều triggers cùng loại? | Thứ tự tên trigger |
| ROLLBACK có xóa audit trong DB? | Có, nếu audit ghi trong cùng transaction |
| Side effect HTTP được rollback? | Không tự động; cân nhắc outbox |
| Hàm trigger trả kiểu? | `RETURNS trigger` |
| Xem trigger definitions? | `pg_trigger`, `pg_get_triggerdef` |
| Xem function body? | `pg_get_functiondef` |
| Tắt/bật một trigger? | `ALTER TABLE ... DISABLE/ENABLE TRIGGER ...` |
| Tránh trigger recursion? | Sửa `NEW`, tách luồng DML/idempotency |
| Kiểm tra độ sâu? | `pg_trigger_depth()` |
| Đo chi phí? | `EXPLAIN (ANALYZE, BUFFERS)` trong lab |

## 46. Checklist trước khi đưa trigger vào production

1. Trigger thực sự cần thiết hay có thể dùng constraint, generated column, SQL statement hoặc batch?
2. Yêu cầu là **từng hàng** hay **một lần mỗi câu lệnh**?
3. Đã test trường hợp 0, 1 và hàng nghìn hàng chưa?
4. Hàm có dùng `NEW`/`OLD` đúng event không?
5. `BEFORE ROW` có vô ý `RETURN NULL` làm mất hàng không?
6. Trigger `AFTER` có bị hiểu nhầm là “sau COMMIT” không?
7. `WHEN` hoặc `UPDATE OF` có đúng điều kiện nghiệp vụ không?
8. Nếu cần biết cả batch, transition tables có hỗ trợ event/quan hệ hiện tại không?
9. Có UPDATE làm thay đổi primary key khiến JOIN OLD/NEW khó ghép không?
10. Có `INSERT ... ON CONFLICT` hoặc `MERGE` ảnh hưởng đếm event không?
11. Có partition routing/movement hoặc FK cascade tạo thêm trigger events?
12. Có trigger recursion hoặc chuỗi cập nhật chéo dẫn tới deadlock không?
13. Row trigger có chạy SQL truy vấn lớn N lần không?
14. Audit table có schema/index/retention và kiểm soát PII phù hợp không?
15. Exception có rollback side effects như mong muốn không?
16. Có tác động ngoài DB cần transactional outbox/CDC không?
17. SECURITY DEFINER có owner và `search_path` an toàn không?
18. Có cơ chế actor/correlation ID đúng, không chỉ tin current_user không?
19. Có ai có thể disable trigger hoặc thay `session_replication_role` không?
20. Có kiểm tra behavior trên replication subscriber không?
21. DDL trigger/function đã được version control và migration phù hợp chưa?
22. Có xem `pg_trigger`/`pg_get_triggerdef` trước khi thay đổi không?
23. Có đo write latency/WAL/lock wait khi dữ liệu đủ lớn không?
24. Có kiểm thử transaction rollback và retry/deadlock không?
25. Có kế hoạch disable/recover/backfill nếu trigger gây sự cố không?

## 47. Tổng kết

Hai mức trigger giải quyết **hai phạm vi khác nhau** của DML:

- **`FOR EACH ROW`** thực thi logic cho từng hàng bị ảnh hưởng; với `BEFORE ROW`, function có thể kiểm tra và chỉnh `NEW` hoặc bỏ qua hàng bằng `RETURN NULL`. Với `AFTER ROW`, nó phù hợp để audit những giá trị `OLD`/`NEW` của mỗi hàng.
- **`FOR EACH STATEMENT`** thực thi một lần cho cả câu SQL, **kể cả khi 0 hàng được tác động**. Nó phù hợp để ghi nhận lệnh/batch, và khi dùng `AFTER` cùng `REFERENCING OLD TABLE/NEW TABLE`, có thể tổng hợp dữ liệu thay đổi theo tập thay vì lặp từng hàng.

Những điểm dễ nhầm nhất là **statement không phải transaction**, **AFTER không phải after COMMIT**, **`RETURN NULL` chỉ bỏ qua hàng trong ngữ cảnh BEFORE ROW thích hợp**, **`UPDATE OF` không đồng nghĩa giá trị cột thực đổi**, và **`TRUNCATE` không kích hoạt DELETE ROW triggers**. Ngoài ra, `INSTEAD OF` trên view, constraint triggers, bảng phân vùng và `ON CONFLICT` có những quy tắc cần hiểu riêng.

Nếu một trigger làm chậm hệ thống, đừng vội tắt nó: hãy kiểm tra logic có đang chạy theo từng hàng nhưng thực chất chỉ cần xử lý một lần theo statement hay không; cân nhắc transition tables, SQL set-based, outbox hoặc background jobs. Đồng thời đo tác động ghi và bảo đảm tính toàn vẹn, quyền, audit/rollback và khả năng triển khai an toàn.

**Nguyên tắc thực hành:** dùng **constraint** cho bất biến đơn giản; **BEFORE ROW** khi cần chuẩn hóa một hàng; **AFTER ROW** khi cần lịch sử từng thay đổi; **AFTER STATEMENT + transition tables** khi cần xử lý cả lô. Thiết kế theo đúng phạm vi sự kiện trước, rồi mới tối ưu hiệu năng.
