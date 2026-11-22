# Trigger BEFORE, AFTER, INSTEAD OF và thời điểm thực thi trong PostgreSQL

Giả sử một hệ thống bán hàng lưu các đơn đặt hàng trong PostgreSQL. Khi thêm đơn, ứng dụng cần chuẩn hóa tên khách hàng; khi sửa đơn, cần ghi lịch sử thay đổi; còn một giao diện quản trị thao tác qua **view** thay vì truy cập trực tiếp bảng. Ba nhu cầu này có thể dùng ba loại trigger với **thời điểm thực thi** khác nhau:

- **`BEFORE`:** chạy trước thao tác `INSERT`, `UPDATE` hoặc `DELETE` tương ứng, có thể kiểm tra và thay đổi `NEW` trong row-level trigger hoặc bỏ qua một hàng.
- **`AFTER`:** chạy sau khi thao tác đã được áp dụng cho hàng hoặc statement tương ứng, phù hợp ghi audit, cập nhật các bảng phụ thuộc hoặc xử lý theo tập hàng đã thay đổi.
- **`INSTEAD OF`:** chỉ dùng cho **row-level trigger trên view**, thực hiện hành động thay cho thao tác DML mà người dùng gửi tới view.

Điểm dễ gây nhầm lẫn là **thời điểm trigger** (`BEFORE`/`AFTER`/`INSTEAD OF`) và **cấp độ trigger** (`FOR EACH ROW`/`FOR EACH STATEMENT`) là hai chiều khác nhau. Một statement thay đổi 0 hàng vẫn có thể kích hoạt statement-level triggers, trong khi row-level triggers chỉ chạy cho những hàng tương ứng. Ngoài ra, mọi thao tác của trigger vẫn nằm trong các quy tắc transaction/MVCC của PostgreSQL: **`AFTER` không có nghĩa “sau `COMMIT`”**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả trigger, trigger function và các sự kiện `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`.
2. Phân biệt **timing** với **granularity**, xác định tổ hợp nào hỗ trợ trên bảng và view.
3. Giải thích chính xác khi nào `BEFORE ROW`, `AFTER ROW`, `BEFORE STATEMENT` và `AFTER STATEMENT` được kích hoạt.
4. Sử dụng `NEW` và `OLD` theo từng loại sự kiện, cùng với `TG_OP`, `TG_WHEN`, `TG_LEVEL`.
5. Viết trigger function `RETURNS trigger` bằng PL/pgSQL và đăng ký bằng `CREATE TRIGGER`.
6. Biết khi nào trả `NEW`, `OLD` hoặc `NULL` trong `BEFORE ROW` và `INSTEAD OF ROW`.
7. Giải thích tại sao giá trị trả về của `AFTER` trigger và statement-level trigger bị bỏ qua.
8. Dùng `BEFORE` để chuẩn hóa dữ liệu nhưng vẫn giữ CHECK/FK/NOT NULL constraints là nguồn bảo vệ chính.
9. Dùng `AFTER` để ghi audit có thể rollback cùng transaction.
10. Dùng **transition tables** (`OLD TABLE`, `NEW TABLE`) cho trigger tổng hợp theo statement.
11. Tạo `INSTEAD OF` trigger để thực hiện `INSERT`/`UPDATE`/`DELETE` thông qua view.
12. Hiểu thứ tự chạy khi có nhiều triggers cùng loại và ảnh hưởng của `WHEN`, `UPDATE OF`.
13. Nhận diện `AFTER ROW` **constraint triggers** có thể được trì hoãn, khác với AFTER thường.
14. Dự đoán tình huống `ON CONFLICT DO UPDATE`, `TRUNCATE`, cascading FK và partition row movement.
15. Tránh trigger đệ quy, writes ngoài ý muốn, chi phí N+1, rủi ro bảo mật và khó gỡ lỗi.
16. Kiểm tra metadata, log/EXPLAIN và sự thay đổi dữ liệu trong transaction.

## 2. Trigger là gì?

**Trigger** là một cơ chế để PostgreSQL tự động gọi một hàm/thủ tục thực thi theo sự kiện liên quan tới bảng hoặc view. Trong cách làm thông dụng với PostgreSQL, chúng ta:

1. Tạo một **trigger function** bằng `CREATE FUNCTION ... RETURNS trigger`.
2. Gắn nó vào bảng/view qua `CREATE TRIGGER ... EXECUTE FUNCTION ...`.
3. Chạy lệnh DML; PostgreSQL gọi trigger function khi sự kiện và điều kiện khớp.

Ví dụ:

~~~sql
CREATE FUNCTION public.demo_before_insert()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_demo_before_insert
BEFORE INSERT ON public.demo_orders
FOR EACH ROW
EXECUTE FUNCTION public.demo_before_insert();
~~~

Đây chỉ là **mẫu cú pháp**; `public.demo_orders` là bảng giả định. Phần lab bên dưới sẽ tạo một bảng thực tế trong schema riêng.

### 2.1. Trigger khác với DEFAULT và CHECK

| Công cụ | Nhu cầu điển hình | Đặc trưng |
| --- | --- | --- |
| `DEFAULT` | Giá trị ban đầu nếu INSERT không cung cấp cột | Không cần trigger function |
| `GENERATED` column | Giá trị suy ra từ biểu thức | Do database tính theo quy tắc cột |
| `NOT NULL`/`CHECK` | Bảo vệ dữ liệu hợp lệ | Ràng buộc schema, nên ưu tiên cho bất biến đơn giản |
| `FOREIGN KEY` | Bảo toàn tham chiếu | Database bảo vệ mối quan hệ |
| `BEFORE` trigger | Chuẩn hóa, kiểm tra nghiệp vụ phức tạp, chỉnh `NEW` | Có thể thay đổi hàng trước khi ghi |
| `AFTER` trigger | Audit, side-table update, kiểm soát theo hàng/tập | Nhìn thấy hiệu ứng của DML |
| `INSTEAD OF` trigger | DML qua view không tự sửa được hoặc cần logic riêng | Thực hiện thay hành động trên view |

**Không nên biến mọi quy tắc dữ liệu thành trigger.** Khi một `CHECK` hoặc `UNIQUE` diễn đạt được bất biến, constraint thường minh bạch và dễ kiểm chứng hơn.

### 2.2. Trigger không đồng nghĩa với luật RULE

PostgreSQL còn có cơ chế **rule system** (`CREATE RULE`), dùng để **rewrite truy vấn** trước execution. Trigger chạy trong quá trình thực thi DML. Cả hai có thể phục vụ cập nhật qua view nhưng **không phải hai cú pháp đồng nghĩa**.

### 2.3. Trigger không phải callback sau COMMIT

~~~text
BEGIN
  UPDATE bảng chính
     └── AFTER ROW trigger ghi audit
  ... các lệnh khác ...
ROLLBACK
~~~

Nếu transaction rollback, **dữ liệu bảng chính lẫn bản ghi audit được tạo trong cùng transaction đều rollback**. Dòng chữ `AFTER` mô tả thời điểm tương đối với thao tác DML, **không** phải thời điểm sau khi transaction commit bền vững.

## 3. Hai chiều cần phân biệt: timing và level

### 3.1. Timing

| Timing | Ý nghĩa |
| --- | --- |
| `BEFORE` | Trước thao tác row hoặc statement tương ứng |
| `AFTER` | Sau thao tác row hoặc statement tương ứng |
| `INSTEAD OF` | Thực thi **thay** thao tác trên view; chỉ row-level |

### 3.2. Level

| Level | Ý nghĩa |
| --- | --- |
| `FOR EACH ROW` | Một lần cho mỗi hàng bị thao tác liên quan, theo semantics từng sự kiện |
| `FOR EACH STATEMENT` | Một lần cho statement có sự kiện tương ứng, kể cả khi nó thay đổi 0 hàng |

### 3.3. Ma trận hỗ trợ quan trọng

| Đối tượng | `BEFORE ROW` | `AFTER ROW` | `BEFORE STATEMENT` | `AFTER STATEMENT` | `INSTEAD OF ROW` |
| --- | --- | --- | --- | --- | --- |
| Bảng thông thường | Có cho INSERT/UPDATE/DELETE | Có cho INSERT/UPDATE/DELETE | Có | Có | **Không** |
| View | **Không** | **Không** | Có | Có | Có cho INSERT/UPDATE/DELETE |
| Foreign table | Hỗ trợ BEFORE ROW trong những trường hợp tương ứng | Cần xem giới hạn foreign-table trigger theo phiên bản/FDW | Cần xem hỗ trợ của version | Cần xem hỗ trợ của version | **Không**, vì không phải view |

**Đối với `TRUNCATE`:** chỉ **statement-level BEFORE/AFTER triggers**; không tồn tại row-level `TRUNCATE` trigger. Không có `INSTEAD OF TRUNCATE`.

**Đối với view:** `INSTEAD OF` chỉ có `FOR EACH ROW`; `BEFORE`/`AFTER` triggers trên view phải là **statement-level**. Nếu view tự cập nhật được, PostgreSQL còn có cơ chế tự động cập nhật; `INSTEAD OF` chỉ cần khi muốn kiểm soát logic hoặc view không tự updatable.

### 3.4. Cú pháp CREATE TRIGGER phổ biến

~~~sql
CREATE TRIGGER trigger_name
BEFORE INSERT OR UPDATE OR DELETE
ON schema_name.table_name
FOR EACH ROW
EXECUTE FUNCTION schema_name.trigger_function();
~~~

Với `UPDATE` theo cột:

~~~sql
CREATE TRIGGER trg_amount_changed
AFTER UPDATE OF amount ON schema_name.orders
FOR EACH ROW
WHEN (OLD.amount IS DISTINCT FROM NEW.amount)
EXECUTE FUNCTION schema_name.audit_amount_change();
~~~

`UPDATE OF amount` xem xét **cột được nêu trong SET list**; `WHEN (OLD.amount IS DISTINCT FROM NEW.amount)` kiểm tra **giá trị thực sự có khác nhau không**, kể cả với NULL. Hai ý nghĩa này sẽ được phân tích kỹ ở phần sau.

## 4. Thời điểm chạy trong một statement

Một cách hình dung với `UPDATE` nhiều hàng trên bảng thông thường:

~~~text
Client gửi UPDATE
  |
  +-- BEFORE STATEMENT triggers
  |
  +-- Với từng hàng phù hợp:
  |     +-- BEFORE ROW triggers: xem OLD/NEW, có thể đổi NEW hoặc bỏ qua hàng
  |     +-- PostgreSQL thực hiện thay đổi hàng nếu không bị bỏ qua
  |     +-- Row-level AFTER events được lên lịch
  |
  +-- AFTER ROW triggers được xử lý theo semantics PostgreSQL
  |
  +-- AFTER STATEMENT triggers
  |
  +-- Statement kết thúc hoặc phát sinh lỗi
  |
  +-- COMMIT/ROLLBACK do transaction của caller quyết định
~~~

Đây là **mô hình tư duy** chứ không phải cam kết một thứ tự nội bộ cho mọi tối ưu hay mọi loại trigger. Các constraint triggers trì hoãn, cascading FK, partition row movement và statement có nhiều hành động như `ON CONFLICT DO UPDATE` có thêm chi tiết.

### 4.1. BEFORE STATEMENT

Chạy **trước** khi PostgreSQL xử lý các thay đổi hàng tương ứng của statement. Không có `NEW`/`OLD` là row cụ thể để đọc hoặc chỉnh trong statement trigger.

### 4.2. BEFORE ROW

Chạy trên từng hàng được thao tác trước khi row change được áp dụng. Thường dùng `NEW` (INSERT/UPDATE), `OLD` (UPDATE/DELETE), và giá trị trả về có thể quyết định hàng tiếp tục được xử lý hay bị bỏ qua.

### 4.3. AFTER ROW

Chạy sau thay đổi của hàng tương ứng đã xảy ra. Phù hợp cho side effects *trong database* và audit. **Không thể đổi hàng đang được ghi chỉ bằng gán `NEW.foo := ...` và `RETURN NEW` trong AFTER trigger**, vì giá trị trả về của AFTER trigger bị bỏ qua.

### 4.4. AFTER STATEMENT

Chạy sau các row operations của statement. Một `AFTER STATEMENT` trigger có thể dùng transition tables để quan sát **tập hàng** vừa bị ảnh hưởng, thay vì thực thi từng hàng.

### 4.5. INSTEAD OF ROW

Chỉ áp dụng cho view. Khi client gửi `INSERT`/`UPDATE`/`DELETE` tới view, trigger thực hiện thao tác vào underlying base tables hoặc logic phù hợp **thay cho hành động mặc định**. Nó trả hàng không NULL nếu muốn báo đã xử lý một row, và NULL nếu không xử lý.

### 4.6. AFTER không có nghĩa “dữ liệu đã commit”

Một statement có thể chạy nhiều AFTER triggers, rồi sau đó gặp exception và bị rollback. Các rows đã ghi trong AFTER trigger **vẫn nằm trong cùng transaction**, nên bị rollback cùng statement/transaction theo quy tắc PostgreSQL.

## 5. Trigger function RETURNS trigger

Trigger function PL/pgSQL thông thường được khai báo:

~~~sql
CREATE FUNCTION schema_name.function_name()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    -- NEW, OLD, TG_OP, TG_WHEN, TG_LEVEL...
    RETURN NEW;
END;
$$;
~~~

### 5.1. Các biến đặc biệt

| Biến | Ý nghĩa |
| --- | --- |
| `NEW` | Hàng mới đối với INSERT/UPDATE row-level trigger |
| `OLD` | Hàng trước thay đổi đối với UPDATE/DELETE row-level trigger |
| `TG_OP` | `INSERT`, `UPDATE`, `DELETE` hoặc `TRUNCATE` |
| `TG_WHEN` | `BEFORE`, `AFTER`, `INSTEAD OF` |
| `TG_LEVEL` | `ROW` hoặc `STATEMENT` |
| `TG_TABLE_NAME` | Tên bảng/view gắn trigger |
| `TG_TABLE_SCHEMA` | Schema bảng/view |
| `TG_RELID` | OID relation gắn trigger |
| `TG_NAME` | Tên trigger |
| `TG_NARGS` | Số tham số được truyền cho trigger |
| `TG_ARGV[n]` | Tham số trigger dạng text, chỉ số **bắt đầu từ 0** |

**`NEW` không khả dụng cho DELETE và `OLD` không khả dụng cho INSERT.** Với statement-level trigger, không có một row cụ thể để gán vào `NEW`/`OLD`.

### 5.2. Dùng TG_OP để chia nhánh

~~~sql
CREATE FUNCTION public.example_trigger_function()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        RAISE NOTICE 'Inserted by trigger %', TG_NAME;
        RETURN NEW;
    ELSIF TG_OP = 'UPDATE' THEN
        RAISE NOTICE 'Updated row';
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        RAISE NOTICE 'Deleting row';
        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;
~~~

Đây là function minh họa nhiều event **row-level**. Khi dùng cho statement-level hoặc `INSTEAD OF`, quy tắc return khác và phải xét loại relation.

### 5.3. Parameter của trigger function

Trigger function không khai báo tham số SQL thông thường trong signature để nhận `TG_ARGV`:

~~~sql
CREATE TRIGGER trg_audit_named
AFTER INSERT ON some_schema.some_table
FOR EACH ROW
EXECUTE FUNCTION some_schema.audit_function('orders', 'important');
~~~

Ở runtime, hàm đọc `TG_ARGV[0]` là `orders`, `TG_ARGV[1]` là `important`. Các chuỗi này là **trigger arguments**, khác với tham số của function được gọi bình thường.

## 6. Giá trị trả về: NEW, OLD và NULL

Đây là quy tắc quan trọng nhất khi viết row-level triggers.

| Trigger | `RETURN NEW` | `RETURN OLD` | `RETURN NULL` |
| --- | --- | --- | --- |
| `BEFORE INSERT ROW` | Cho hàng tiếp tục, có thể dùng `NEW` đã chỉnh | Không phù hợp vì không có `OLD` | **Bỏ qua** insert cho hàng này |
| `BEFORE UPDATE ROW` | Cho UPDATE tiếp tục với `NEW` đã chỉnh | Có thể tạo kết quả không mong muốn nếu thay row mới bằng row cũ | **Bỏ qua** UPDATE hàng này |
| `BEFORE DELETE ROW` | Không có `NEW` | Cho DELETE tiếp tục | **Bỏ qua** DELETE hàng này |
| `AFTER ROW` | Return bị bỏ qua | Return bị bỏ qua | Return bị bỏ qua |
| `BEFORE/AFTER STATEMENT` | Return bị bỏ qua | Return bị bỏ qua | Return bị bỏ qua |
| `INSTEAD OF INSERT/UPDATE ROW` | Báo đã xử lý row, có thể cung cấp row cho RETURNING | Không phù hợp khi không có OLD | Báo không xử lý row |
| `INSTEAD OF DELETE ROW` | Không có NEW | Báo đã xử lý DELETE | Báo không xử lý row |

### 6.1. Một row-level BEFORE trigger trả NULL

Khi `BEFORE ROW` trả NULL:

- PostgreSQL **bỏ qua hành động row** tương ứng.
- Các row-level triggers tiếp theo của thao tác ấy không được chạy cho row bị bỏ qua.
- Hàng không góp vào `RETURNING` như một hàng vừa thay đổi.
- Statement-level triggers vẫn có thể chạy vì statement được phát ra.

Trả NULL để “âm thầm bỏ hàng không hợp lệ” thường không tốt cho tính minh bạch nghiệp vụ. Nếu input sai, thường **`RAISE EXCEPTION` hoặc constraint** hợp lý hơn để caller biết thất bại.

### 6.2. BEFORE UPDATE trả OLD: có hợp lệ về kỹ thuật, nhưng dễ gây hiểu nhầm

Một row-level BEFORE UPDATE trigger có thể trả row value khác `NEW`, nhưng cần hết sức thận trọng: `RETURN OLD` không được hiểu là “bỏ qua UPDATE như `RETURN NULL`”. Nó có thể khiến giá trị cũ được sử dụng cho row operation, tạo hiệu ứng khác mong đợi và khiến row vẫn được coi là đã xử lý. Với UPDATE thường chỉ nên `RETURN NEW` hoặc `RETURN NULL` theo yêu cầu đã xác định.

### 6.3. AFTER trigger không sửa được row bằng return

~~~sql
-- Sai mục tiêu:
-- CREATE FUNCTION ... RETURNS trigger AS $$
-- BEGIN
--   NEW.amount := 0;
--   RETURN NEW;
-- END; $$ LANGUAGE plpgsql;
-- Gắn AFTER UPDATE sẽ KHÔNG làm amount của row vừa update thành 0.
~~~

Nếu cần chỉnh giá trị của **chính hàng đang INSERT/UPDATE**, thường hãy dùng `BEFORE ROW`. Nếu cần cập nhật một hàng khác sau sự kiện, `AFTER` có thể thực thi `UPDATE` riêng nhưng phải chú ý **trigger recursion và lock/concurrency**.

### 6.4. INSTEAD OF trigger và RETURNING

Một `INSTEAD OF ROW` trigger trên view thường nên trả row thích hợp khi thao tác đã được thực hiện. PostgreSQL dùng return value để xác định số rows bị ảnh hưởng và có thể tạo output cho `INSERT/UPDATE/DELETE ... RETURNING` trên view. `RETURN NULL` nghĩa row không được xử lý, **không chỉ là “không có gì để trả”**.

## 7. Bộ dữ liệu lab: bảng đơn hàng và lịch sử

Các ví dụ tạo **schema riêng** `trg_lab_367`. Chỉ chạy DDL và DML này trong database lab được phép, không dán vào schema production chứa dữ liệu thật. Bài minh họa trên PostgreSQL hiện đại với `plpgsql`.

### 7.1. Tạo schema

~~~sql
CREATE SCHEMA trg_lab_367;
~~~

Nếu schema đã tồn tại từ lượt thực hành trước, hãy chọn tên lab khác hoặc chủ động reset sau khi xác nhận dữ liệu có thể xóa. **Không dùng `DROP SCHEMA ... CASCADE` trên một schema chưa rõ nguồn gốc.**

### 7.2. Bảng orders

~~~sql
CREATE TABLE trg_lab_367.orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    status text NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'paid', 'cancelled')),
    note text,
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 7.3. Bảng audit

~~~sql
CREATE TABLE trg_lab_367.order_audit (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint,
    action text NOT NULL,
    old_data jsonb,
    new_data jsonb,
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    changed_by name NOT NULL DEFAULT current_user
);
~~~

Không thêm FK audit → orders trong lab để **audit DELETE** vẫn lưu được order_id khi row gốc bị xóa. Trong production có thể chọn chính sách lưu lịch sử, retention và quyền PII phù hợp.

### 7.4. Bảng trace để quan sát timing

~~~sql
CREATE TABLE trg_lab_367.trigger_trace (
    trace_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name text NOT NULL,
    timing text NOT NULL,
    trigger_level text NOT NULL,
    order_id bigint,
    detail text,
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

`trigger_trace` phục vụ **quan sát trong transaction**; các ghi vào bảng này cũng rollback nếu transaction chứa DML chính rollback. Không dùng nó như external tamper-proof audit log.

### 7.5. Lệnh kiểm tra khởi tạo

~~~sql
SELECT
    table_schema,
    table_name
FROM information_schema.tables
WHERE table_schema = 'trg_lab_367'
ORDER BY table_name;
~~~

Khi lab chưa có orders nào, `SELECT COUNT(*) FROM trg_lab_367.orders` trả 0. Chúng ta sẽ tạo trigger trước khi nạp dữ liệu để thấy tác dụng của cả `BEFORE` và `AFTER` từ hàng đầu tiên.

## 8. BEFORE ROW: chuẩn hóa và kiểm tra trước khi ghi

Ví dụ muốn xóa khoảng trắng ở hai đầu tên khách hàng, từ chối tên chỉ chứa dấu cách và tự cập nhật thời điểm `updated_at`.

### 8.1. Tạo trigger function

~~~sql
CREATE FUNCTION trg_lab_367.normalize_order_before()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.customer_name IS NULL
       OR btrim(NEW.customer_name) = '' THEN
        RAISE EXCEPTION
            'customer_name must not be blank'
            USING ERRCODE = 'check_violation';
    END IF;

    NEW.customer_name := btrim(NEW.customer_name);
    NEW.updated_at := clock_timestamp();

    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, order_id, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        NEW.order_id,
        'name normalized before the row is stored'
    );

    RETURN NEW;
END;
$$;
~~~

### 8.2. Gắn vào bảng

~~~sql
CREATE TRIGGER trg_10_normalize_order
BEFORE INSERT OR UPDATE
ON trg_lab_367.orders
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.normalize_order_before();
~~~

`BEFORE INSERT OR UPDATE` nghĩa trigger chạy trước cả hai loại thao tác. `FOR EACH ROW` nghĩa một lần trên mỗi hàng tương ứng, không phải một lần cho cả statement.

### 8.3. Thứ tự trong function

1. Đọc dữ liệu mới từ `NEW`.
2. Kiểm tra tên trước khi ghi.
3. Chỉnh `NEW.customer_name`.
4. Chỉnh `NEW.updated_at`.
5. Ghi một record trace thuộc cùng transaction.
6. `RETURN NEW` để PostgreSQL dùng phiên bản hàng đã chỉnh.

### 8.4. Cảnh báo về việc tự động cập nhật cột

Nếu tên là bắt buộc, constraint `NOT NULL` đã bảo đảm không nhận SQL NULL, nhưng không bảo đảm text khác chuỗi rỗng hay toàn dấu cách. Trigger trên đây thêm chính sách chuỗi rỗng. Có thể dùng `CHECK (btrim(customer_name) <> '')` để bảo vệ điều kiện đơn giản; trigger hữu ích khi thực sự cần **chỉnh dữ liệu** trước ghi.

### 8.5. Trigger không tự sửa mọi dữ liệu cũ

`CREATE TRIGGER` không chạy lại `BEFORE INSERT/UPDATE` cho các rows đang nằm sẵn trong bảng. Khi thêm trigger chuẩn hóa vào hệ thống cũ, phải có kế hoạch backfill, kiểm tra input lịch sử và index/constraint tương ứng.

## 9. BEFORE STATEMENT: sự kiện trước một câu lệnh

Statement-level trigger không có một row cụ thể; dùng nó cho logging sự kiện, khởi tạo trạng thái tổng hợp hoặc chính sách liên quan tới **toàn statement**.

### 9.1. Trigger function

~~~sql
CREATE FUNCTION trg_lab_367.trace_before_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        'statement started'
    );

    RETURN NULL;
END;
$$;
~~~

### 9.2. Đăng ký cho ba sự kiện

~~~sql
CREATE TRIGGER trg_01_before_statement
BEFORE INSERT OR UPDATE OR DELETE
ON trg_lab_367.orders
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.trace_before_statement();
~~~

`RETURN NULL` ở statement-level trigger **không bỏ qua statement**. Giá trị trả về của statement-level triggers bị PostgreSQL bỏ qua; đây là khác biệt quan trọng so với `BEFORE ROW`.

### 9.3. Không đọc NEW hoặc OLD của một hàng

~~~sql
-- Không phù hợp trong statement-level trigger:
-- RAISE NOTICE '%', NEW.customer_name;
~~~

Với `FOR EACH STATEMENT`, `NEW`/`OLD` không đại diện cho một bản ghi. Nếu muốn đọc nhiều rows vừa bị thay đổi, cân nhắc **AFTER statement trigger với transition tables** (phần sau), không cố ép statement-level trigger nhìn như một row trigger.

## 10. AFTER ROW: ghi audit sau khi hàng được thay đổi

Ta muốn biết nội dung trước/sau thao tác. Một `AFTER ROW` trigger có thể ghi vào bảng audit sau khi PostgreSQL đã áp dụng thay đổi tương ứng.

### 10.1. Tạo audit trigger function

~~~sql
CREATE FUNCTION trg_lab_367.audit_order_after()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id bigint;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_order_id := NEW.order_id;

        INSERT INTO trg_lab_367.order_audit(
            order_id, action, old_data, new_data
        )
        VALUES (
            v_order_id, 'INSERT', NULL, to_jsonb(NEW)
        );

    ELSIF TG_OP = 'UPDATE' THEN
        v_order_id := NEW.order_id;

        INSERT INTO trg_lab_367.order_audit(
            order_id, action, old_data, new_data
        )
        VALUES (
            v_order_id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW)
        );

    ELSIF TG_OP = 'DELETE' THEN
        v_order_id := OLD.order_id;

        INSERT INTO trg_lab_367.order_audit(
            order_id, action, old_data, new_data
        )
        VALUES (
            v_order_id, 'DELETE', to_jsonb(OLD), NULL
        );
    END IF;

    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, order_id, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        v_order_id,
        'row change audited'
    );

    RETURN NULL;  -- Hợp lệ: giá trị trả về AFTER ROW bị bỏ qua.
END;
$$;
~~~

### 10.2. Gắn AFTER trigger

~~~sql
CREATE TRIGGER trg_90_audit_order
AFTER INSERT OR UPDATE OR DELETE
ON trg_lab_367.orders
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.audit_order_after();
~~~

### 10.3. Vì sao AFTER phù hợp với audit?

Trong một row-level `AFTER` trigger, PostgreSQL đã áp dụng hành động đối với hàng tương ứng. Với `UPDATE`, `NEW` phản ánh dữ liệu mới thực sự được thao tác, bao gồm những chỉnh sửa từ `BEFORE ROW` triggers trước đó.

`BEFORE` cũng có thể ghi audit, nhưng khi còn các triggers khác có thể sửa tiếp `NEW`, bản ghi audit ở `BEFORE` có nguy cơ không phản ánh phiên bản cuối của hàng. **AFTER** là lựa chọn thường tự nhiên hơn khi cần ảnh chụp trước/sau.

### 10.4. Audit ở cùng transaction

Nếu một trigger audit phát sinh lỗi, statement DML chứa nó có thể thất bại và rollback. Nếu caller rollback cả transaction sau khi audit đã chạy, record audit thuộc transaction ấy cũng biến mất. **Bảng audit bằng trigger không tự là một hệ thống lưu nhật ký bất biến vượt transaction rollback.**

### 10.5. Cân nhắc quyền và dữ liệu nhạy cảm

`to_jsonb(NEW)` sao chép **toàn bộ các cột** của hàng sang audit. Trong production, bảng có thể chứa địa chỉ, thông tin riêng tư hoặc thông tin thanh toán. Cần quy tắc chọn field, masking/encryption, retention và phân quyền; không sao chép tất cả cột mà không có chính sách dữ liệu.

## 11. AFTER STATEMENT: thời điểm kết thúc statement

Tạo trigger ghi một sự kiện khi statement hoàn tất xử lý thao tác trên bảng:

~~~sql
CREATE FUNCTION trg_lab_367.trace_after_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        'statement finished its row operations'
    );

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_99_after_statement
AFTER INSERT OR UPDATE OR DELETE
ON trg_lab_367.orders
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.trace_after_statement();
~~~

### 11.1. Sơ đồ ba loại trigger trong lab

~~~mermaid
flowchart TD
    A["INSERT / UPDATE / DELETE"] --> B["BEFORE STATEMENT: trace_before_statement"]
    B --> C["Với từng row liên quan"]
    C --> D["BEFORE ROW: normalize_order_before (INSERT/UPDATE)"]
    D --> E["DML row operation"]
    E --> F["AFTER ROW: audit_order_after"]
    F --> G["AFTER STATEMENT: trace_after_statement"]
    G --> H["Statement kết thúc; transaction còn do caller kiểm soát"]
~~~

Với `DELETE`, không có `normalize_order_before` vì trigger đó chỉ đăng ký cho `INSERT OR UPDATE`. Với một statement ảnh hưởng 0 hàng, chỉ các statement-level triggers tương ứng chạy.

### 11.2. Statement-level trigger chạy khi không hàng nào khớp

~~~sql
UPDATE trg_lab_367.orders
SET status = 'paid'
WHERE order_id = -999999;
~~~

Trong lab, câu này không cập nhật hàng nào, nhưng **BEFORE STATEMENT** và **AFTER STATEMENT** UPDATE triggers vẫn chạy. **BEFORE ROW** và **AFTER ROW** không có row để xử lý.

### 11.3. Một statement thay đổi 1.000 rows

- `BEFORE STATEMENT`: thường một lần.
- `BEFORE ROW`: theo từng hàng thực sự được trigger xử lý.
- `AFTER ROW`: theo từng hàng thay đổi (trừ những hàng bị bỏ qua hoặc tình huống đặc biệt).
- `AFTER STATEMENT`: một lần.

Đây là lý do logic kiểm tra/ghi audit theo từng row có thể rất tốn chi phí khi làm bulk UPDATE. Với bài toán tổng hợp, transition tables có thể giảm số câu SQL riêng lẻ.

## 12. Nạp dữ liệu và quan sát BEFORE/AFTER

Sau khi đã tạo các triggers, chạy:

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status, note
)
VALUES
    ('  An  ', 120000, 'new', 'first order'),
    (' Bình ', 95000, 'new', 'second order'),
    ('Chi', 0, 'new', 'gift order')
RETURNING order_id, customer_name, amount, updated_at;
~~~

### 12.1. Kết quả mong đợi

`customer_name` được bỏ khoảng trắng đầu/cuối:

| Tên input | Tên lưu |
| --- | --- |
| `'  An  '` | `An` |
| `' Bình '` | `Bình` |
| `'Chi'` | `Chi` |

Mỗi hàng INSERT có một bản ghi audit chứa `new_data` đã chuẩn hóa. `RETURNING` cũng thấy kết quả của các `BEFORE` row triggers.

### 12.2. Kiểm tra bảng chính

~~~sql
SELECT
    order_id,
    customer_name,
    amount,
    status,
    updated_at
FROM trg_lab_367.orders
ORDER BY order_id;
~~~

### 12.3. Kiểm tra audit

~~~sql
SELECT
    audit_id,
    order_id,
    action,
    old_data,
    new_data
FROM trg_lab_367.order_audit
ORDER BY audit_id;
~~~

Có ba bản ghi `INSERT` cho ba rows. `old_data` là SQL NULL; `new_data` là JSONB ảnh chụp hàng sau khi `BEFORE ROW` đã chuẩn hóa.

### 12.4. Kiểm tra trace

~~~sql
SELECT
    trace_id,
    event_name,
    timing,
    trigger_level,
    order_id,
    detail
FROM trg_lab_367.trigger_trace
ORDER BY trace_id;
~~~

Trong một `INSERT` ba rows bình thường, trace có một lần `BEFORE STATEMENT`, ba lần `BEFORE ROW`, ba lần `AFTER ROW` và một lần `AFTER STATEMENT`, tức **tám** trace records do bốn trigger functions trong lab tạo.

Không nên suy ra thứ tự vật lý xử lý mọi hàng chỉ từ thứ tự `trace_id` khi câu SQL có nhiều nguồn rows, parallel execution hoặc trigger phụ khác; test lab giúp thấy **loại thời điểm**, không phải hợp đồng về row ordering ngoài `ORDER BY` ở query đọc.

### 12.5. UPDATE một hàng

~~~sql
UPDATE trg_lab_367.orders
SET customer_name = '  An Nguyễn  ',
    amount = 125000
WHERE customer_name = 'An'
RETURNING order_id, customer_name, amount, updated_at;
~~~

`BEFORE ROW` đổi tên thành `An Nguyễn` và cập nhật timestamp; `AFTER ROW` ghi `old_data`/`new_data`. Statement-level triggers chỉ chạy một lần cho cả UPDATE.

### 12.6. DELETE một hàng

~~~sql
DELETE FROM trg_lab_367.orders
WHERE customer_name = 'Chi'
RETURNING order_id, customer_name, amount;
~~~

Với DELETE, không có `NEW`. `AFTER ROW` audit dùng `OLD` để giữ snapshot hàng đã xóa. `RETURNING` của DELETE lấy dữ liệu thích hợp từ hàng bị xóa theo semantics PostgreSQL.

### 12.7. Trigger trace cũng rollback

~~~sql
BEGIN;

UPDATE trg_lab_367.orders
SET status = 'paid'
WHERE customer_name = 'Bình';

-- Có thể quan sát trace/audit thay đổi ngay trong transaction này.
ROLLBACK;
~~~

Sau `ROLLBACK`, các thay đổi hàng và những audit/trace records phát sinh bởi UPDATE không còn tồn tại như thay đổi đã commit. Nếu cần lưu chứng cứ về **những câu SQL thất bại hoặc bị rollback**, cần logging/audit bên ngoài transaction hoặc cơ chế quan sát phù hợp, không chỉ bảng trigger audit.

## 13. BEFORE ROW: trả NULL để bỏ qua một hàng

Để không ảnh hưởng tới dữ liệu đơn hàng chính, ta tạo bảng lab phụ:

~~~sql
CREATE TABLE trg_lab_367.import_queue (
    import_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_value text NOT NULL
);
~~~

### 13.1. Chỉ giữ chuỗi khác rỗng

~~~sql
CREATE FUNCTION trg_lab_367.skip_blank_import()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF btrim(NEW.source_value) = '' THEN
        RETURN NULL; -- Bỏ qua đúng hàng INSERT này.
    END IF;

    NEW.source_value := btrim(NEW.source_value);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_skip_blank_import
BEFORE INSERT ON trg_lab_367.import_queue
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.skip_blank_import();
~~~

### 13.2. INSERT nhiều hàng

~~~sql
INSERT INTO trg_lab_367.import_queue(source_value)
VALUES ('  accepted  '), ('   '), ('second')
RETURNING import_id, source_value;
~~~

Kết quả chỉ có **hai** hàng `accepted` và `second`. Hàng input toàn khoảng trắng không được insert. Nó không xuất hiện trong `RETURNING` và không làm phát sinh một row-level `AFTER INSERT` event trên bảng này.

### 13.3. Vấn đề của việc âm thầm bỏ hàng

Nếu file import có 1.000 dòng nhưng statement xử lý được 998 mà không báo lỗi, hệ thống cần biết **hai dòng bị bỏ và lý do**. `RETURN NULL` thường chỉ thích hợp khi nghiệp vụ chấp nhận skip có chủ đích; nếu giá trị sai cần lỗi rõ, nên dùng `RAISE EXCEPTION` hoặc lưu các dòng lỗi ở luồng import riêng.

### 13.4. Cột identity có thể bị khuyết số

Sequence dùng cho identity values có thể đã cấp số trước khi row bị bỏ qua hoặc transaction rollback. Vì thế `import_id` không nhất thiết liên tục. **Không dùng khoảng trống ID làm bằng chứng một row bị xóa hay một transaction đã commit.**

## 14. BEFORE DELETE: kiểm soát thao tác xóa

Một `BEFORE DELETE` trigger có thể trả `OLD` để cho xóa tiếp hoặc `NULL` để bỏ qua hàng.

~~~sql
CREATE FUNCTION trg_lab_367.protect_paid_order()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.status = 'paid' THEN
        RAISE EXCEPTION
            'Paid order % cannot be deleted', OLD.order_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN OLD;
END;
$$;

CREATE TRIGGER trg_20_protect_paid_order
BEFORE DELETE ON trg_lab_367.orders
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.protect_paid_order();
~~~

### 14.1. Vì sao RAISE EXCEPTION thay vì RETURN NULL?

Nếu quy tắc “không được xóa đơn đã thanh toán” là một **bất biến nghiệp vụ**, báo lỗi rõ là lựa chọn thường tốt hơn bỏ qua im lặng. `RETURN NULL` sẽ khiến thao tác DELETE với hàng đó không ảnh hưởng row, nhưng client có thể tưởng DELETE thành công nếu không kiểm tra row count.

### 14.2. Xóa nhiều rows và một row bị cấm

~~~sql
DELETE FROM trg_lab_367.orders
WHERE status IN ('new', 'paid');
~~~

Nếu trong tập có một đơn `paid` và trigger ném exception, statement DELETE thất bại. Những thay đổi đã thực hiện trong **cùng statement** được rollback theo quy tắc atomicity của statement/transaction; không giữ các DELETE của những rows trước đó trong cùng statement như kết quả thành công riêng lẻ.

### 14.3. Trigger không thay quyền DELETE

Kiểm soát quyền bằng `GRANT`, Row-Level Security (khi phù hợp), API authorization và dữ liệu trạng thái. Trigger có thể bổ sung ràng buộc, nhưng không nên coi nó là thay thế duy nhất cho chính sách quyền truy cập.

## 15. UPDATE OF column: cột được nhắc trong SET hay giá trị thực sự đổi?

PostgreSQL cho phép trigger chỉ chạy trên những UPDATE có nhắc tới cột cụ thể:

~~~sql
CREATE TRIGGER trg_amount_update
AFTER UPDATE OF amount
ON trg_lab_367.orders
FOR EACH ROW
EXECUTE FUNCTION some_schema.some_trigger_function();
~~~

**Điều kiện `UPDATE OF amount` chủ yếu xét cột `amount` có được liệt kê là target của câu lệnh UPDATE hay không**, chứ không kiểm tra giá trị trước và sau khác nhau.

### 15.1. Hai câu UPDATE có cùng giá trị nhưng hành vi trigger khác

~~~sql
-- Có nhắc amount trong SET:
UPDATE trg_lab_367.orders
SET amount = amount
WHERE order_id = 1;

-- Không nhắc amount trong SET:
UPDATE trg_lab_367.orders
SET note = 'metadata only'
WHERE order_id = 1;
~~~

Nếu chỉ dùng `AFTER UPDATE OF amount` mà không thêm `WHEN`:

- Câu thứ nhất có thể kích hoạt trigger dù `amount` không đổi.
- Câu thứ hai không kích hoạt trigger cột amount, kể cả khi một `BEFORE UPDATE` trigger khác tình cờ chỉnh `NEW.amount`.

Đó là khác biệt giữa **cột được chỉ định cập nhật** và **thay đổi thực tế của giá trị**.

### 15.2. Tạo bảng riêng để ghi thay đổi amount thực sự

~~~sql
CREATE TABLE trg_lab_367.amount_change_log (
    change_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    old_amount numeric(12,2),
    new_amount numeric(12,2),
    changed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 15.3. Hàm ghi amount

~~~sql
CREATE FUNCTION trg_lab_367.log_amount_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.amount_change_log(
        order_id, old_amount, new_amount
    )
    VALUES (NEW.order_id, OLD.amount, NEW.amount);

    RETURN NULL; -- AFTER: return bị bỏ qua.
END;
$$;
~~~

### 15.4. Gắn UPDATE OF kết hợp WHEN

~~~sql
CREATE TRIGGER trg_80_amount_changed
AFTER UPDATE OF amount
ON trg_lab_367.orders
FOR EACH ROW
WHEN (OLD.amount IS DISTINCT FROM NEW.amount)
EXECUTE FUNCTION trg_lab_367.log_amount_change();
~~~

Điều kiện `WHEN` lọc những lần giá trị `amount` trước/sau khác nhau. Với `AFTER ROW` trigger, PostgreSQL có thể **kiểm tra WHEN tại thời điểm row operation** và chỉ queue trigger event khi điều kiện đúng, giảm việc phải gọi trigger function cho những rows không đổi.

### 15.5. Vì sao IS DISTINCT FROM hữu ích?

~~~sql
SELECT
    (NULL::integer = NULL::integer) AS equal_with_null,
    (NULL::integer IS DISTINCT FROM NULL::integer) AS distinct_with_null,
    (NULL::integer IS DISTINCT FROM 10) AS distinct_from_ten;
~~~

`=` có thể trả SQL NULL khi một trong hai vế là NULL; `IS DISTINCT FROM` cho kết quả boolean rõ ràng trong trường hợp NULL. Cột `amount` của lab có `NOT NULL` nhưng mẫu này cũng áp dụng cho các cột nullable.

### 15.6. So sánh ba tình huống

| UPDATE statement | `UPDATE OF amount`? | `WHEN OLD.amount IS DISTINCT FROM NEW.amount`? | Hàm log được gọi? |
| --- | --- | --- | --- |
| `SET amount = amount` | Có | Không | Không |
| `SET amount = amount + 100` | Có | Có (nếu khác thật) | Có |
| `SET note = 'new'` | Không | Không cần xét | Không |

Nếu business phải log **mọi thay đổi thực sự của amount**, kể cả khi trigger khác đổi amount dù column không nằm trong SET list, có thể dùng `AFTER UPDATE ON ... WHEN (...)` **không dùng `OF amount`**. Quy tắc thiết kế phụ thuộc chính xác điều gì cần ghi nhận.

### 15.7. UPDATE OF không đồng nghĩa giá trị sau cùng

Một `BEFORE UPDATE` trigger khác có thể thay đổi `NEW.amount`. `UPDATE OF amount` vẫn dựa vào target list của SQL statement chứ không tự dựa vào các chỉnh sửa của BEFORE trigger. Đừng dựa vào `UPDATE OF` như công cụ duy nhất xác định row đã đổi cột.

## 16. WHEN clause: điều kiện trước khi gọi trigger function

`CREATE TRIGGER` có thể có `WHEN (condition)` nhằm giới hạn những trường hợp cần kích hoạt trigger.

### 16.1. BEFORE ROW WHEN

~~~sql
-- Ví dụ chỉ chuẩn hóa khi client cung cấp tên khác tên trước:
CREATE TRIGGER trg_example_name_change
BEFORE UPDATE ON trg_lab_367.orders
FOR EACH ROW
WHEN (OLD.customer_name IS DISTINCT FROM NEW.customer_name)
EXECUTE FUNCTION trg_lab_367.normalize_order_before();
~~~

Trong ví dụ này, function `normalize_order_before` còn cập nhật `updated_at`. Nếu dùng trigger này **thay** trigger normalize hiện có, nó chỉ cập nhật timestamp khi tên khác, không phải trên mọi UPDATE. Hãy chọn đúng contract; không áp dụng vô tình trên production.

Đối với lab thực tế đã có `trg_10_normalize_order`, **không cần tạo thêm trigger ví dụ này** nếu chưa muốn thay đổi hành vi; đoạn trên minh họa cú pháp/ý nghĩa `WHEN`.

### 16.2. AFTER ROW WHEN

~~~sql
WHEN (OLD.status IS DISTINCT FROM NEW.status)
~~~

phù hợp để chỉ ghi event khi trạng thái đơn thật sự đổi. Lưu ý với `INSERT` không có `OLD`; với `DELETE` không có `NEW`. Không dùng một WHEN expression truy cập biến không hiện diện ở event đó.

### 16.3. INSTEAD OF không nhận WHEN

`INSTEAD OF` triggers trên view **không được khai báo `WHEN`**. Nếu cần điều kiện bỏ qua/chuyển hướng thao tác trên view, viết logic `IF ... THEN` trong trigger function và trả row hoặc NULL theo quy tắc.

### 16.4. WHEN không được chứa subquery

Trong cú pháp CREATE TRIGGER, biểu thức `WHEN` có các giới hạn, trong đó không được chứa subquery SQL. Nếu logic điều kiện phức tạp cần truy vấn dữ liệu bên ngoài, thực hiện trong trigger function với nhận thức về transaction, locks và chi phí.

### 16.5. WHEN của constraint trigger trì hoãn

Với constraint trigger có thể deferred, biểu thức `WHEN` vẫn được xét **ngay sau thay đổi hàng**, quyết định có queue trigger event hay không. Đừng mặc định WHEN sẽ được đánh giá lại vào cuối transaction khi event deferred được thực thi.

## 17. Nhiều triggers cùng thời điểm: thứ tự tên alphabet

PostgreSQL quy định khi có **nhiều triggers cùng loại** trên cùng sự kiện/timing/level cho một relation, chúng được thực thi theo **thứ tự tên (alphabetical)**.

Ví dụ:

~~~text
BEFORE UPDATE ROW trên orders:
  trg_10_normalize_order
  trg_20_check_something
  trg_30_add_metadata
~~~

Nếu cả ba cùng áp dụng, thứ tự tên giúp dự đoán việc một trigger nhìn thấy `NEW` do trigger trước chỉnh.

### 17.1. Lưu ý tương tác của return value

~~~text
trg_10 → sửa NEW, RETURN NEW
trg_20 → nhận row đã được sửa, RETURN NEW
trg_30 → RETURN NULL
        → bỏ qua row operation; các row triggers sau không chạy.
~~~

Nếu đổi tên trigger khiến thứ tự thay đổi, kết quả có thể đổi. Tuy nhiên, **không nên xây luồng nghiệp vụ quá phụ thuộc vào nhiều triggers tương tác**; một trigger function rõ trách nhiệm đôi khi dễ kiểm soát hơn.

### 17.2. Thứ tự tên không vượt qua timing

Tên `zzz_before_row` không khiến nó chạy sau `aaa_after_row`: **timing và level** vẫn xác định giai đoạn hoạt động. Quy tắc alphabet áp dụng giữa những triggers cùng loại.

### 17.3. Không dùng tên như cách thay transaction boundary

Các trigger trong cùng statement vẫn không tự commit độc lập; việc đặt tên theo thứ tự không tạo một transaction mới.

### 17.4. Đọc tên triggers hiện tại

~~~sql
SELECT
    tgname,
    tgenabled,
    pg_catalog.pg_get_triggerdef(oid) AS definition
FROM pg_catalog.pg_trigger
WHERE tgrelid = 'trg_lab_367.orders'::regclass
  AND NOT tgisinternal
ORDER BY tgname;
~~~

Đây là truy vấn metadata đọc-only, hữu ích để nhận diện triggers có tên gần giống hoặc được tạo bởi migration cũ.

## 18. Transition tables: nhìn cả tập hàng đã thay đổi

Khi làm bulk DML, muốn thống kê `COUNT(*)` hoặc `SUM(amount)` của **những rows vừa INSERT**, thực hiện SELECT riêng trong từng AFTER ROW trigger sẽ rất tốn chi phí. PostgreSQL cho phép **transition relations**:

- `REFERENCING NEW TABLE AS ...`: tập rows mới của statement.
- `REFERENCING OLD TABLE AS ...`: tập rows cũ trước UPDATE/DELETE.

Transition tables được dùng với **AFTER triggers** trên bảng thông thường (theo các giới hạn của `CREATE TRIGGER`), không dùng cho `BEFORE` hoặc `INSTEAD OF`. Đặc biệt, `UPDATE` trigger có transition tables **không được chỉ định `UPDATE OF column_name`**.

### 18.1. Tạo bảng tổng hợp theo statement

~~~sql
CREATE TABLE trg_lab_367.statement_summary (
    summary_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_name text NOT NULL,
    changed_rows bigint NOT NULL,
    amount_delta numeric(14,2),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

### 18.2. AFTER INSERT STATEMENT với NEW TABLE

~~~sql
CREATE FUNCTION trg_lab_367.summarize_insert_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.statement_summary(
        event_name, changed_rows, amount_delta
    )
    SELECT
        'INSERT',
        COUNT(*),
        COALESCE(SUM(amount), 0)
    FROM inserted_orders;

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_95_summarize_insert
AFTER INSERT ON trg_lab_367.orders
REFERENCING NEW TABLE AS inserted_orders
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.summarize_insert_statement();
~~~

Tên `inserted_orders` là **transition relation** được khai báo ở trigger, dùng như một bảng tạm chỉ có trong phạm vi ngữ cảnh sự kiện trigger; không cần tạo `CREATE TEMP TABLE inserted_orders`.

### 18.3. Test INSERT nhiều rows trong một statement

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES
    ('Dũng', 10000, 'new'),
    ('Em', 20000, 'new');

SELECT
    event_name,
    changed_rows,
    amount_delta
FROM trg_lab_367.statement_summary
ORDER BY summary_id;
~~~

Trong ví dụ INSERT hai rows này, summary mới có `changed_rows=2`, `amount_delta=30000`. Nó không đếm tất cả rows của bảng, mà chỉ **những rows thuộc sự kiện INSERT hiện tại**.

### 18.4. INSERT không thêm rows vẫn có statement trigger

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
SELECT
    'Nothing',
    0,
    'new'
WHERE FALSE;
~~~

Statement-level AFTER INSERT trigger vẫn chạy; transition relation `inserted_orders` rỗng nên summary có `changed_rows=0` và `amount_delta=0`. Điều này minh họa trực tiếp khác biệt **statement trigger** so với row trigger.

### 18.5. AFTER UPDATE STATEMENT với OLD và NEW TABLE

~~~sql
CREATE FUNCTION trg_lab_367.summarize_update_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.statement_summary(
        event_name, changed_rows, amount_delta
    )
    SELECT
        'UPDATE',
        COUNT(*),
        COALESCE(SUM(n.amount - o.amount), 0)
    FROM new_orders AS n
    JOIN old_orders AS o USING (order_id);

    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_96_summarize_update
AFTER UPDATE ON trg_lab_367.orders
REFERENCING
    OLD TABLE AS old_orders
    NEW TABLE AS new_orders
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.summarize_update_statement();
~~~

Trong lab, `order_id` là khóa chính và các ví dụ không thay khóa chính nên có thể join `OLD`/`NEW` bằng `order_id`. Trong nghiệp vụ **cho phép UPDATE khóa chính**, join bằng key đã đổi có thể không còn đúng; cần chiến lược đối sánh khác hoặc cấm thay khóa bằng constraint/thiết kế.

### 18.6. Test UPDATE tập hàng

~~~sql
UPDATE trg_lab_367.orders
SET amount = amount + 1000
WHERE status = 'new';

SELECT
    summary_id,
    event_name,
    changed_rows,
    amount_delta
FROM trg_lab_367.statement_summary
ORDER BY summary_id;
~~~

Nếu có ba orders `new` tại thời điểm chạy, summary UPDATE mới có `changed_rows=3` và `amount_delta=3000`. Thực tế số rows phụ thuộc những ví dụ DELETE/UPDATE bạn đã chạy trong lab.

### 18.7. Transition tables khác với NEW/OLD row

| Row-level trigger | Statement-level với transition relation |
| --- | --- |
| `NEW.amount` của một row | `SELECT SUM(amount) FROM new_orders` |
| `OLD.status` của một row | `SELECT ... FROM old_orders` |
| Thực thi theo từng hàng | Một lần cho statement (theo event/các giới hạn đặc biệt) |
| Không nhất thiết lý tưởng cho bulk aggregate | Thường hiệu quả hơn cho aggregate theo tập |

### 18.8. UPDATE OF và transition tables

Không viết:

~~~sql
-- Cú pháp không được hỗ trợ cùng transition tables:
-- CREATE TRIGGER ...
-- AFTER UPDATE OF amount ON ...
-- REFERENCING OLD TABLE AS ... NEW TABLE AS ...
~~~

Nếu cần chỉ quan tâm thay đổi amount, hãy tạo `AFTER UPDATE` (không `OF amount`) có transition tables, rồi so sánh `old_rows.amount` và `new_rows.amount` trong function/SQL của transition relation.

### 18.9. Transition relation không phải snapshot toàn bảng

`NEW TABLE`/`OLD TABLE` gồm những rows liên quan đến statement, không phải toàn bộ relation. Không dùng nó để suy ra tổng doanh thu/số đơn của toàn hệ thống mà không tính cả những rows không bị thay đổi.

### 18.10. Khi có partitioning hoặc FK cascade

Trong một số trường hợp đặc biệt, một statement được chia thành nhiều tập sự kiện/transition relations do trigger semantics. Hãy kiểm tra tài liệu phiên bản đang chạy và chạy test trước khi giả định “luôn đúng một transition table cho mọi thao tác logic phức tạp”.

## 19. INSTEAD OF: trigger đặc biệt trên view

Khi ứng dụng thao tác qua một view, có hai trường hợp:

- View **tự cập nhật được** (*automatically updatable view*), PostgreSQL có thể ánh xạ INSERT/UPDATE/DELETE trực tiếp xuống base table theo các điều kiện hỗ trợ.
- View chứa join, aggregate, biểu thức tính toán hoặc logic phức tạp và **không tự cập nhật được**; hoặc ta muốn kiểm soát DML theo chính sách riêng. Lúc đó có thể dùng **`INSTEAD OF` trigger**.

`INSTEAD OF` trigger là **row-level trigger**, chạy thay hành động `INSERT`, `UPDATE` hoặc `DELETE` trên view, không áp dụng cho base table như một `BEFORE`/`AFTER` trigger bình thường.

### 19.1. Tạo view có cột tính toán

~~~sql
CREATE VIEW trg_lab_367.v_order_editor AS
SELECT
    order_id,
    customer_name,
    amount,
    status,
    note,
    amount * 1.05 AS gross_estimate
FROM trg_lab_367.orders
WHERE status <> 'cancelled';
~~~

`gross_estimate` là một biểu thức tính toán, khiến view này **không tự động đáp ứng đầy đủ điều kiện của một simple automatically updatable view**. Ta chủ động dùng `INSTEAD OF` để định nghĩa cách ghi tới base table, đồng thời không cho client trực tiếp gán cột tính toán.

### 19.2. Thiết kế hợp đồng cho view

| Thao tác gửi tới view | Hành động bên trong trigger |
| --- | --- |
| `INSERT` | Thêm vào `orders`; base-table BEFORE trigger chuẩn hóa tên |
| `UPDATE` | Sửa row nền theo `OLD.order_id`; trả row sau chỉnh sửa |
| `DELETE` | Xóa row nền; base-table BEFORE DELETE có thể từ chối đơn đã thanh toán |
| `RETURNING` | Trả row view tương ứng nếu thao tác đã được thực hiện |
| Gán `gross_estimate` | Không cho phép coi là field ghi độc lập; tính lại từ amount |

### 19.3. Viết một trigger function xử lý cả ba thao tác

~~~sql
CREATE FUNCTION trg_lab_367.edit_order_view()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_base trg_lab_367.orders%ROWTYPE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.order_id IS NOT NULL THEN
            RAISE EXCEPTION
                'order_id is generated by the database';
        END IF;

        IF NEW.status = 'cancelled' THEN
            RAISE EXCEPTION
                'Cancelled orders are not writable through this view';
        END IF;

        INSERT INTO trg_lab_367.orders(
            customer_name, amount, status, note
        )
        VALUES (
            NEW.customer_name,
            NEW.amount,
            COALESCE(NEW.status, 'new'),
            NEW.note
        )
        RETURNING * INTO v_base;

        NEW.order_id := v_base.order_id;
        NEW.customer_name := v_base.customer_name;
        NEW.amount := v_base.amount;
        NEW.status := v_base.status;
        NEW.note := v_base.note;
        NEW.gross_estimate := v_base.amount * 1.05;

        RETURN NEW;

    ELSIF TG_OP = 'UPDATE' THEN
        IF NEW.order_id IS DISTINCT FROM OLD.order_id THEN
            RAISE EXCEPTION
                'order_id cannot change through this view';
        END IF;

        IF NEW.status = 'cancelled' THEN
            RAISE EXCEPTION
                'Cannot move a row outside this view by UPDATE';
        END IF;

        UPDATE trg_lab_367.orders AS o
        SET customer_name = NEW.customer_name,
            amount = NEW.amount,
            status = NEW.status,
            note = NEW.note
        WHERE o.order_id = OLD.order_id
        RETURNING * INTO v_base;

        IF NOT FOUND THEN
            RETURN NULL;
        END IF;

        NEW.customer_name := v_base.customer_name;
        NEW.amount := v_base.amount;
        NEW.status := v_base.status;
        NEW.note := v_base.note;
        NEW.gross_estimate := v_base.amount * 1.05;

        RETURN NEW;

    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM trg_lab_367.orders AS o
        WHERE o.order_id = OLD.order_id
        RETURNING * INTO v_base;

        IF NOT FOUND THEN
            RETURN NULL;
        END IF;

        RETURN OLD;
    END IF;

    RETURN NULL;
END;
$$;
~~~

**Phạm vi ví dụ:** function giả định rows của view không bị thay đổi ngoài ý muốn bởi concurrent client trong lúc đang xử lý. Câu `UPDATE/DELETE` dùng row key, không truy cập bằng `customer_name` để tránh tên trùng. Trong production cần review thêm quyền, concurrency, chính sách soft delete và việc expose cột tính toán.

### 19.4. Gắn trigger vào view

~~~sql
CREATE TRIGGER trg_v_order_editor
INSTEAD OF INSERT OR UPDATE OR DELETE
ON trg_lab_367.v_order_editor
FOR EACH ROW
EXECUTE FUNCTION trg_lab_367.edit_order_view();
~~~

Không viết `FOR EACH STATEMENT` cho `INSTEAD OF`. Trigger function ở đây dùng `NEW`/`OLD` là **row shape của view**, khác row shape của base table nếu view có thêm hoặc bớt cột.

### 19.5. INSERT qua view

~~~sql
INSERT INTO trg_lab_367.v_order_editor(
    customer_name, amount, status, note
)
VALUES (
    '  Hà  ',
    23000,
    'new',
    'inserted through view'
)
RETURNING order_id, customer_name, amount, gross_estimate;
~~~

Luồng xử lý:

1. View `INSTEAD OF INSERT` trigger được gọi với `NEW`.
2. Trigger thực thi `INSERT` xuống base table `orders`.
3. Các `BEFORE INSERT` và `AFTER INSERT` triggers **trên base table** chạy như bình thường.
4. Giá trị `customer_name` ở base table được chuẩn hóa thành `Hà`.
5. Trigger view lấy row đã ghi và trả lại `NEW` của view để `RETURNING` nhìn thấy order_id/name/gross_estimate thích hợp.

Giá trị `gross_estimate = 23000 * 1.05 = 24150` theo ví dụ. Đây chỉ là **giá trị minh họa**; không dùng phép nhân đơn giản này làm mô hình thuế/giá thực tế nếu nghiệp vụ có rounding, currency hay chính sách thuế phức tạp.

### 19.6. UPDATE qua view

~~~sql
UPDATE trg_lab_367.v_order_editor
SET customer_name = ' Hà Nguyễn ',
    amount = 26000
WHERE note = 'inserted through view'
RETURNING
    order_id,
    customer_name,
    amount,
    gross_estimate;
~~~

Trigger view thực thi một `UPDATE` riêng trên bảng nền và trả về phiên bản row sau khi base-table BEFORE trigger đã chỉnh tên. `AFTER UPDATE` triggers trên base table cũng chạy, nên audit sẽ có một record `UPDATE`.

### 19.7. DELETE qua view

~~~sql
DELETE FROM trg_lab_367.v_order_editor
WHERE note = 'inserted through view'
RETURNING order_id, customer_name, amount;
~~~

Trigger view xóa base row, tạo audit DELETE qua base-table AFTER trigger, rồi trả `OLD` của view. Nếu hàng nền không tồn tại tại thời điểm DELETE, function trả NULL để báo không xử lý hàng.

### 19.8. RETURN NULL trong INSTEAD OF làm gì?

Với `INSTEAD OF` row trigger:

- `RETURN NULL` nghĩa **hàng không được xử lý**: không tính như row được thực hiện, không xuất hiện như row đã xử lý trong `RETURNING`.
- `RETURN NEW` (INSERT/UPDATE) hoặc `RETURN OLD` (DELETE) theo thiết kế thể hiện row đã được xử lý.
- Return value không tự ghi vào base table. Chính **các lệnh INSERT/UPDATE/DELETE trong trigger function** thực hiện thao tác.

Đây là khác biệt căn bản với `BEFORE ROW` trên base table, nơi trả `NEW` để PostgreSQL tiếp tục chính DML row operation ban đầu.

### 19.9. View INSTEAD OF không tạo transaction mới

`INSERT INTO view`, thao tác base-table từ trigger và audit rows thuộc cùng transaction theo semantics PostgreSQL. Nếu bất kỳ bước nào ném exception làm statement thất bại, những thay đổi trong statement đó bị rollback, trừ những side effects ngoài transactional database nằm ngoài phạm vi kiểm soát.

### 19.10. Không xử lý DML bằng dynamic SQL tùy tiện

Tên relation/field trong trigger function nên schema-qualify và xác định rõ. Nếu bắt buộc dynamic SQL, cần phân biệt identifier quoting và value parameterization (`format('%I', ...)`, `USING`) để tránh injection. Đừng coi quyền truy cập view tự động thay mọi bảo vệ ở base table.

## 20. INSTEAD OF so với automatically updatable view

Một simple view:

~~~sql
CREATE VIEW trg_lab_367.v_simple_orders AS
SELECT
    order_id,
    customer_name,
    amount,
    status
FROM trg_lab_367.orders
WHERE status <> 'cancelled';
~~~

có thể **tự cập nhật** theo các điều kiện mà PostgreSQL hỗ trợ, không nhất thiết cần `INSTEAD OF` trigger.

### 20.1. Khi nào không cần INSTEAD OF?

- View lấy từ một bảng đơn giản;
- Không có những constructs làm mất điều kiện auto-updatability;
- Quy tắc cập nhật base row rõ ràng;
- `WITH CHECK OPTION` có thể giúp kiểm soát việc row còn nằm trong điều kiện view khi phù hợp.

### 20.2. Khi nào nên cân nhắc INSTEAD OF?

- View là phép join/biểu thức không tự updatable;
- Cần phân phối một thao tác view vào nhiều base tables;
- Cần logic ánh xạ/validation đặc biệt;
- Muốn kiểm soát rõ output của `RETURNING`/row count;
- Không muốn đưa toàn bộ cấu trúc base table ra API.

### 20.3. Khi nào không nên dùng INSTEAD OF?

- Logic quá phức tạp làm view khó dự đoán;
- Một thao tác UPDATE qua view tạo nhiều side effects ngoài ý muốn;
- Performance kém vì một row view dẫn đến nhiều DML lặp;
- Có thể dùng một API explicit hoặc procedure với transaction contract rõ hơn;
- Mô hình bảo mật không được review kỹ.

### 20.4. Không nhầm VIEW trigger với trigger trên bảng nền

Trong ví dụ:

~~~text
INSERT INTO v_order_editor
       |
       +-- INSTEAD OF INSERT ROW trên view
               |
               +-- INSERT INTO orders
                       |
                       +-- BEFORE INSERT triggers trên orders
                       +-- Ghi orders
                       +-- AFTER INSERT triggers trên orders
~~~

View trigger không thay thế các constraint/triggers gắn với base table khi nó thực hiện SQL vào base table. Các base triggers vẫn có thể báo lỗi và rollback toàn statement.

## 21. AFTER constraint trigger: có thể trì hoãn khác AFTER thường

Không phải mọi `AFTER` đều nhất thiết được thực thi ngay tại cuối statement. PostgreSQL hỗ trợ **constraint trigger** dạng:

~~~sql
CREATE CONSTRAINT TRIGGER trigger_name
AFTER INSERT OR UPDATE OR DELETE
ON table_name
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION trigger_function();
~~~

Loại trigger này thường dùng kiểm tra ràng buộc nghiệp vụ liên hàng/bảng cần xét ở **cuối transaction**, có thể điều chỉnh bằng `SET CONSTRAINTS`.

### 21.1. Các điểm cần nhớ

- Constraint trigger dùng **AFTER ROW**, không phải BEFORE/INSTEAD OF.
- Có thể khai báo `DEFERRABLE`, `INITIALLY IMMEDIATE` hoặc `INITIALLY DEFERRED`.
- Trigger có thể được thực thi **tại cuối transaction** nếu đang deferred.
- `SET CONSTRAINTS ... IMMEDIATE` có thể khiến các pending deferred trigger events được thực thi ngay tại thời điểm chuyển mode.
- Đây là cơ chế khác với `AFTER ROW` trigger thông thường chạy ở thời điểm statement.

### 21.2. Ví dụ nghiệp vụ: đơn paid phải có amount dương

Quy tắc `status='paid'` chỉ hợp lệ khi `amount > 0` thực tế được diễn đạt **tốt hơn** bằng CHECK:

~~~sql
-- Ví dụ constraint đơn giản nên được ưu tiên:
-- CHECK (status <> 'paid' OR amount > 0)
~~~

Nhưng để học cơ chế **deferred constraint trigger**, ta cố ý mô phỏng một rule theo dữ liệu **cuối transaction**.

### 21.3. Tạo hàm kiểm tra trạng thái cuối

~~~sql
CREATE FUNCTION trg_lab_367.check_paid_order_deferred()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_status text;
    v_amount numeric(12,2);
BEGIN
    -- Đọc trạng thái HIỆN TẠI của row, không chỉ tin snapshot NEW
    -- được capture tại thời điểm event được queue.
    SELECT
        o.status,
        o.amount
    INTO v_status, v_amount
    FROM trg_lab_367.orders AS o
    WHERE o.order_id = NEW.order_id;

    IF FOUND
       AND v_status = 'paid'
       AND v_amount <= 0 THEN
        RAISE EXCEPTION
            'Paid order % must have positive amount',
            NEW.order_id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NULL;
END;
$$;
~~~

### 21.4. Đăng ký deferred constraint trigger

~~~sql
CREATE CONSTRAINT TRIGGER trg_paid_amount_deferred
AFTER INSERT OR UPDATE
ON trg_lab_367.orders
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
WHEN (NEW.status = 'paid')
EXECUTE FUNCTION trg_lab_367.check_paid_order_deferred();
~~~

`WHEN (NEW.status='paid')` được kiểm tra **ngay lúc row event hình thành**, và quyết định có queue event không. Hàm lại **đọc trạng thái hiện tại của row khi thực sự chạy**, để xem thay đổi sau đó trong cùng transaction đã sửa rule hay chưa.

### 21.5. Hai bước trong cùng transaction

Giả sử tạo một đơn thử nghiệm:

~~~sql
INSERT INTO trg_lab_367.orders(customer_name, amount, status)
VALUES ('Demo deferred', 0, 'new')
RETURNING order_id;
~~~

Ghi lại `order_id` trả về, giả sử `:test_id` là biến/placeholder do client cung cấp. Sau đó:

~~~sql
BEGIN;

UPDATE trg_lab_367.orders
SET status = 'paid'
WHERE order_id = :test_id;

-- Tạm thời status='paid', amount=0 trong transaction.

UPDATE trg_lab_367.orders
SET amount = 50000
WHERE order_id = :test_id;

COMMIT;
~~~

Nếu trigger đang deferred và không có constraint khác ngăn trạng thái trung gian, sự kiểm tra có thể xảy ra tại commit, thấy giá trị cuối là `paid` với `amount=50000` và cho phép transaction.

**`:test_id` là placeholder minh họa, không phải cú pháp PostgreSQL SQL chung**. Trong psql có thể dùng substitution variables; trong JDBC dùng `?`. Không dán nguyên văn `:test_id` vào SQL client không hỗ trợ.

### 21.6. Nếu không sửa amount trước commit

~~~sql
BEGIN;

UPDATE trg_lab_367.orders
SET status = 'paid', amount = 0
WHERE order_id = :test_id;

COMMIT; -- có thể bị constraint trigger trì hoãn báo lỗi
~~~

Khi commit kích hoạt deferred trigger và rule sai, transaction không được commit thành công. PostgreSQL đảm bảo transaction atomicity; cần xử lý lỗi ở client và kiểm tra trạng thái session.

### 21.7. SET CONSTRAINTS IMMEDIATE

~~~sql
BEGIN;

SET CONSTRAINTS trg_paid_amount_deferred IMMEDIATE;

-- Từ đây, các events áp dụng trigger này được xử lý
-- theo chế độ immediate; có thể kiểm tra pending events tại đây.

ROLLBACK;
~~~

Tên constraint trigger có thể cần schema qualification khi có trùng tên. `SET CONSTRAINTS` áp dụng các ràng buộc có khả năng deferred; nó không biến mọi AFTER trigger thường thành deferred trigger.

### 21.8. Hạn chế thực tế

Một deferred trigger dựa vào `SELECT` đọc lại row ở thời điểm kiểm tra phải được thiết kế kỹ cho concurrency, deletion và invariants nhiều bảng. Với điều kiện đơn giản như `amount>0`, **CHECK constraint thường rõ và mạnh hơn**. Không dùng deferred trigger chỉ để trì hoãn một lỗi đơn giản mà không có lý do nghiệp vụ thật.

### 21.9. AFTER không luôn đồng nghĩa chạy sau mọi constraint

Các constraints như CHECK/NOT NULL, FK actions, immediate/deferred constraint triggers có semantics riêng. Một `AFTER ROW` trigger thường nhìn thấy hàng đã được thao tác, nhưng **không tự bảo đảm mọi deferred constraint trong transaction đã được kiểm tra**. Phân biệt "sau thay đổi hàng" và "sau transaction kiểm tra xong tất cả ràng buộc".

## 22. TRUNCATE: chỉ statement-level trigger

`TRUNCATE` loại bỏ các rows khỏi bảng bằng cơ chế khác `DELETE`. PostgreSQL hỗ trợ:

~~~sql
CREATE TRIGGER trg_before_truncate
BEFORE TRUNCATE ON some_schema.some_table
FOR EACH STATEMENT
EXECUTE FUNCTION some_schema.trigger_function();
~~~

Và `AFTER TRUNCATE FOR EACH STATEMENT`. **Không có `FOR EACH ROW` trigger cho TRUNCATE**, bởi PostgreSQL không xử lý từng hàng theo cách kích hoạt DELETE row triggers.

### 22.1. Tạo bảng lab phụ

~~~sql
CREATE TABLE trg_lab_367.temp_items (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label text NOT NULL
);

INSERT INTO trg_lab_367.temp_items(label)
VALUES ('A'), ('B'), ('C');
~~~

### 22.2. Trigger BEFORE TRUNCATE

~~~sql
CREATE FUNCTION trg_lab_367.trace_truncate()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trg_lab_367.trigger_trace(
        event_name, timing, trigger_level, detail
    )
    VALUES (
        TG_OP,
        TG_WHEN,
        TG_LEVEL,
        'truncate event'
    );

    RETURN NULL; -- Statement trigger: giá trị trả về bị bỏ qua.
END;
$$;

CREATE TRIGGER trg_before_truncate_items
BEFORE TRUNCATE ON trg_lab_367.temp_items
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.trace_truncate();

CREATE TRIGGER trg_after_truncate_items
AFTER TRUNCATE ON trg_lab_367.temp_items
FOR EACH STATEMENT
EXECUTE FUNCTION trg_lab_367.trace_truncate();
~~~

### 22.3. Thử trong transaction rồi rollback

~~~sql
BEGIN;

TRUNCATE trg_lab_367.temp_items;

SELECT COUNT(*) AS rows_after_truncate
FROM trg_lab_367.temp_items;

ROLLBACK;

SELECT COUNT(*) AS rows_after_rollback
FROM trg_lab_367.temp_items;
~~~

Trong transaction, bảng bị truncate và `rows_after_truncate=0`. Sau `ROLLBACK`, những rows ban đầu vẫn có thể được khôi phục bởi tính transaction-safe của `TRUNCATE` trong PostgreSQL. Các records trace về TRUNCATE thuộc cùng transaction bị rollback nên cũng không được commit.

### 22.4. Khác biệt DELETE và TRUNCATE

| Tiêu chí | DELETE | TRUNCATE |
| --- | --- | --- |
| Xử lý row-by-row triggers | Có thể kích hoạt row-level DELETE triggers | **Không** |
| Statement triggers | BEFORE/AFTER DELETE STATEMENT | BEFORE/AFTER TRUNCATE STATEMENT |
| WHERE predicate | Có | Không |
| RETURNING rows | Có | Không |
| Semantics MVCC/lock | Theo DELETE | TRUNCATE có các hiệu ứng lock/visibility đặc biệt |
| Có thể rollback trong transaction | Có | Có với PostgreSQL thông thường |

**Đừng dùng TRUNCATE để "xóa nhanh" một bảng có BEFORE/AFTER DELETE row triggers kỳ vọng phải chạy để bảo toàn nghiệp vụ.** Các FK và quyền thao tác cũng có quy tắc riêng cần kiểm tra.

## 23. INSERT ... ON CONFLICT DO UPDATE: hai loại trigger có thể cùng tham gia

Trong PostgreSQL, UPSERT:

~~~sql
INSERT INTO some_table(...)
VALUES (...)
ON CONFLICT (unique_key)
DO UPDATE SET ...;
~~~

có semantics trigger phức tạp hơn một INSERT hoặc UPDATE thông thường.

### 23.1. Row-level BEFORE INSERT và BEFORE UPDATE

Trong trường hợp **có conflict và chuyển sang DO UPDATE**, PostgreSQL có thể thực thi:

1. `BEFORE INSERT ROW` triggers trên row được đề xuất INSERT;
2. Phát hiện unique conflict;
3. `BEFORE UPDATE ROW` triggers trên row hiện có;
4. Update row nếu điều kiện `ON CONFLICT DO UPDATE ... WHERE` cho phép;
5. Các `AFTER UPDATE ROW` triggers tương ứng.

Những thay đổi của `BEFORE INSERT` trên `NEW` có thể ảnh hưởng tới `EXCLUDED` values dùng trong `DO UPDATE`. Vì vậy **cùng một câu SQL có thể đi qua cả hai giai đoạn BEFORE INSERT và BEFORE UPDATE**.

### 23.2. Statement-level triggers của cả INSERT và UPDATE

Khi statement chứa `ON CONFLICT DO UPDATE`, PostgreSQL có thể kích hoạt **statement-level INSERT và UPDATE triggers** theo quy tắc đã định, kể cả khi tập row thực sự conflict/update là rỗng. Thứ tự statement-level quan trọng:

~~~text
BEFORE INSERT statement
BEFORE UPDATE statement
... row-level actions ...
AFTER UPDATE statement
AFTER INSERT statement
~~~

Không suy ra từ việc "0 rows updated" rằng `AFTER UPDATE STATEMENT` sẽ không chạy; **statement-level triggers không phụ thuộc đơn thuần vào row count**.

### 23.3. Tạo bảng riêng cho demo

~~~sql
CREATE TABLE trg_lab_367.upsert_demo (
    demo_key text PRIMARY KEY,
    value_text text NOT NULL
);
~~~

Chúng ta không cần lắp toàn bộ trigger vào bảng demo để thấy điều kiện; có thể dùng `CREATE TRIGGER` tương tự trên bảng thật khi làm lab nâng cao.

~~~sql
INSERT INTO trg_lab_367.upsert_demo(demo_key, value_text)
VALUES ('A', 'first')
ON CONFLICT (demo_key)
DO UPDATE SET value_text = EXCLUDED.value_text;

INSERT INTO trg_lab_367.upsert_demo(demo_key, value_text)
VALUES ('A', 'second')
ON CONFLICT (demo_key)
DO UPDATE SET value_text = EXCLUDED.value_text;
~~~

Thao tác thứ nhất INSERT; thao tác thứ hai UPDATE row có `demo_key='A'`. Khi gắn triggers vào bảng, phải thiết kế không để các `BEFORE INSERT` và `BEFORE UPDATE` cùng sửa trường dẫn đến normalization lặp hay side effects không mong muốn.

### 23.4. ON CONFLICT DO NOTHING

Với `DO NOTHING`, row bị conflict không được insert, nên không có `AFTER INSERT ROW` cho row không được thêm. Tuy nhiên, **BEFORE INSERT ROW** triggers có thể đã được gọi trong quá trình chuẩn bị row, và **INSERT STATEMENT triggers** vẫn theo semantics của statement. Không suy ra “DO NOTHING nghĩa không có trigger nào chạy”.

### 23.5. Tránh side effects không thể rollback trong BEFORE INSERT

Nếu `BEFORE INSERT` gửi external webhook rồi UPSERT rơi vào `DO NOTHING` hoặc transaction rollback, webhook có thể vẫn đã được gửi mà không có row mới. **Không thực hiện network side effects bên trong trigger**; dùng outbox và dispatcher độc lập sau commit.

## 24. MERGE: sự kiện INSERT/UPDATE/DELETE kết hợp

PostgreSQL hỗ trợ `MERGE` trong các phiên bản hiện đại (từ PostgreSQL 15). Đây là statement có thể quy định nhiều nhánh hành động:

~~~sql
MERGE INTO target_table AS t
USING source_table AS s
ON t.id = s.id
WHEN MATCHED THEN
    UPDATE SET value_text = s.value_text
WHEN NOT MATCHED THEN
    INSERT (id, value_text)
    VALUES (s.id, s.value_text);
~~~

### 24.1. Không có sự kiện trigger "MERGE"

PostgreSQL triggers cho `MERGE` gắn với những sự kiện **INSERT/UPDATE/DELETE** tương ứng, không tạo một `TG_OP='MERGE'` riêng như một DML event chung.

### 24.2. Statement-level triggers

Nếu một `MERGE` có các nhánh `INSERT`/`UPDATE`/`DELETE`, statement-level triggers của những loại hành động được quy định có thể chạy **kể cả khi nhánh cụ thể không được áp dụng cho hàng nào**. Row-level triggers chỉ tương ứng với những row actions thực sự được thực hiện, theo semantics của từng nhánh.

### 24.3. Vì sao cần thử nghiệm?

Khi một procedure dựa vào statement-level audit để đếm rows, nó không thể coi "trigger fired" là bằng chứng ít nhất một row đã INSERT/UPDATE/DELETE. Cần row counts/transition relations và hiểu behavior của major version đang chạy.

### 24.4. Phân biệt MERGE với ON CONFLICT

`MERGE` và `INSERT ON CONFLICT` đều có thể dẫn tới nhiều loại row actions nhưng có khác biệt quan trọng về semantics và trigger firing. **Đừng copy logic trigger-timing từ UPSERT sang MERGE mà không kiểm tra tài liệu tương ứng.**

## 25. FOREIGN KEY cascading actions và triggers

PostgreSQL triển khai những phần của foreign key referential actions qua cơ chế trigger nội bộ. Khi dùng:

~~~sql
CREATE TABLE parent_table (
    id bigint PRIMARY KEY
);

CREATE TABLE child_table (
    id bigint PRIMARY KEY,
    parent_id bigint NOT NULL
        REFERENCES parent_table(id)
        ON DELETE CASCADE
);
~~~

thì DELETE parent có thể kéo theo DELETE các child rows.

### 25.1. Child row triggers có thể chạy

Nếu child table có `AFTER DELETE ROW` audit trigger, thao tác xóa child do `ON DELETE CASCADE` cũng có thể kích hoạt nó theo trigger semantics. Không giả định chỉ những lệnh DELETE viết trực tiếp lên child mới tạo audit.

### 25.2. Không đơn giản là một transaction ngoài trigger

Cascading actions diễn ra **trong transaction của statement gốc**; nếu một trigger con lỗi, transaction/statement có thể rollback. Không xem cascade như một asynchronous job đã commit riêng.

### 25.3. Vấn đề khi có nhiều bảng liên quan

Một DELETE parent có thể ảnh hưởng nhiều child/grandchild tables, mỗi bảng có row/statement triggers riêng. Một nghiệp vụ dựa vào **thứ tự tương tác toàn cục** giữa các triggers ở nhiều relations cần được mô hình hóa và test cẩn thận, không dựa vào thứ tự tên trigger của một bảng để suy ra toàn bộ thứ tự cascade.

### 25.4. Trigger nội bộ khác trigger người dùng

Trong `pg_trigger`, `tgisinternal` giúp phân biệt nhiều triggers do cơ chế constraint tạo ra. Không tự disable/internal edit những triggers phục vụ FK chỉ để làm một migration nhanh; điều đó có thể phá referential integrity.

### 25.5. Dùng trigger cho audit FK changes

Nếu cần biết child rows nào bị xóa gián tiếp, gắn audit trên child có thể giúp lưu thông tin trong cùng transaction. Nhưng một audit record sẽ rollback nếu transaction DELETE parent rollback. Với audit pháp lý yêu cầu ghi cả attempts thất bại, cần hệ thống logging phù hợp.

## 26. Partitioned tables: trigger khi UPDATE làm row chuyển partition

PostgreSQL cho phép row-level triggers trên partitioned tables trong những phiên bản hiện đại theo các quy tắc riêng; khi tạo row-level trigger trên partitioned parent, hệ thống có thể tạo/duy trì **clone triggers** ở partitions.

### 26.1. UPDATE làm chuyển partition

Ví dụ một bảng partition theo ngày/tháng, UPDATE đổi giá trị partition key khiến row phải đi từ partition A sang partition B.

Trong PostgreSQL, **row movement** thường được thực thi giống một **DELETE ở partition cũ + INSERT ở partition mới**, chứ không phải một UPDATE đơn giản nằm yên ở một heap relation.

### 26.2. Những sự kiện row-level đáng nhớ

Khi UPDATE làm di chuyển row:

- `BEFORE UPDATE ROW` và `BEFORE DELETE ROW` có thể chạy trên partition nguồn.
- `BEFORE INSERT ROW` chạy trên partition đích.
- `AFTER DELETE ROW` và `AFTER INSERT ROW` có thể được kích hoạt cho row movement.
- **`AFTER UPDATE ROW` không được kích hoạt như một UPDATE ROW thông thường** cho row đã chuyển partition, vì thao tác đã trở thành delete/insert.

### 26.3. Statement-level triggers vẫn theo UPDATE

Statement-level triggers gắn với thao tác SQL ban đầu **UPDATE** có semantics riêng; không tự giả định statement-level INSERT/DELETE triggers đều chạy chỉ vì row movement dùng delete/insert ở cấp row.

### 26.4. Hệ quả đối với audit

Nếu audit logic chỉ gắn `AFTER UPDATE ROW`, nó có thể **bỏ sót những thay đổi partition key gây row movement**. Cần tính đến DELETE+INSERT events hoặc thiết kế audit ở cấp statement, rồi kiểm thử với chính partitioned schema của hệ thống.

### 26.5. Version và thiết kế

Các chi tiết trigger trên partitioned tables thay đổi giữa PostgreSQL major versions; khi triển khai production, đọc phần `Partitioning` và `Trigger Behavior` đúng version. Không áp dụng suy luận trên một bảng thường nguyên vẹn cho mọi partition moves.

## 27. COPY FROM cũng kích hoạt INSERT triggers

Khi nạp dữ liệu bằng:

~~~sql
COPY trg_lab_367.orders (
    customer_name, amount, status
)
FROM STDIN WITH (FORMAT csv);
~~~

`COPY FROM` thực hiện việc nhập rows vào bảng và **có kích hoạt các INSERT triggers** theo semantics PostgreSQL. Điều này có nghĩa:

- `BEFORE INSERT ROW` có thể chuẩn hóa từng row;
- `AFTER INSERT ROW` có thể ghi audit cho từng row;
- Statement-level INSERT triggers có thể chạy cho thao tác COPY;
- Một import rất lớn có thể trở nên chậm vì trigger thực hiện nhiều SQL phụ.

### 27.1. Không disable triggers để nhập nhanh mà thiếu kiểm soát

Một số bulk-load procedures cân nhắc disable user triggers hoặc dùng staging table, nhưng việc tắt triggers không đúng quy trình có thể bỏ qua validation/audit và gây dữ liệu không hợp lệ. Đặc biệt không sửa các cài đặt ảnh hưởng FK/replication-trigger behavior như một mẹo tốc độ tùy tiện.

### 27.2. Mẫu staging an toàn hơn

~~~text
COPY vào staging table
    |
    +-- Validate/normalize và lưu rejected rows
    |
    +-- INSERT ... SELECT từ staging sang bảng chính
            |
            +-- BEFORE/AFTER triggers + constraints
~~~

Khi đó có thể kiểm soát chất lượng input và đo số hàng rejected, thay vì dùng `RETURN NULL` âm thầm bỏ dữ liệu xấu giữa import.

## 28. GENERATED columns và thời điểm BEFORE/AFTER

PostgreSQL hỗ trợ generated columns, ví dụ:

~~~sql
CREATE TABLE trg_lab_367.generated_demo (
    item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity integer NOT NULL,
    unit_price numeric(12,2) NOT NULL,
    line_total numeric(14,2)
        GENERATED ALWAYS AS (quantity * unit_price) STORED
);
~~~

### 28.1. Thời điểm tính stored generated columns

Với **stored generated column**, PostgreSQL tính giá trị từ biểu thức **sau `BEFORE ROW` triggers và trước khi `AFTER ROW` triggers xử lý giá trị hàng đã ghi**.

Điều này nghĩa:

- `BEFORE ROW` trigger có thể chỉnh `NEW.quantity`/`NEW.unit_price`.
- `line_total` được tính từ những giá trị cơ sở cuối cùng theo quy tắc generated column.
- `AFTER ROW` trigger có thể đọc giá trị generated column đã được xác định.
- Không nên dựa vào `NEW.line_total` trong `BEFORE ROW` trigger như thể nó là một giá trị cuối cùng đã tính xong.

### 28.2. Không dùng trigger để tự tính lại một generated column

~~~sql
-- Không nên:
-- NEW.line_total := NEW.quantity * NEW.unit_price;
~~~

`line_total` là generated column do PostgreSQL kiểm soát. Nếu bài toán chỉ là biểu thức số học đơn giản từ những cột khác, generated column có thể phù hợp hơn trigger thủ công.

### 28.3. UPDATE đầu vào được tính lại

~~~sql
INSERT INTO trg_lab_367.generated_demo(
    quantity, unit_price
)
VALUES (2, 10000)
RETURNING item_id, quantity, unit_price, line_total;
~~~

`line_total` là 20000. Nếu UPDATE quantity lên 3, generated value sẽ phản ánh thay đổi tương ứng.

### 28.4. Phiên bản PostgreSQL

Các tính năng generated columns (STORED/VIRTUAL) và giới hạn đi kèm có thay đổi theo major version. Mẫu này sử dụng **STORED** để minh họa thứ tự tính toán. Khi dùng một server cũ hoặc chọn virtual generated columns trên server mới, cần đọc tài liệu version tương ứng.

## 29. Constraints và timing: BEFORE không vượt rào NOT NULL/CHECK/FK

Một row-level `BEFORE` trigger có thể chỉnh `NEW` nhưng **không có quyền làm cho constraint sai vẫn được commit**.

### 29.1. Bảng có CHECK amount >= 0

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES ('Invalid', -10, 'new');
~~~

Trigger normalize có thể chạy, nhưng sau đó constraint `CHECK (amount >= 0)` chặn row không hợp lệ. Cả row và những inserts do trigger thực hiện cùng statement cũng không được commit thành công.

### 29.2. Thứ tự không nên hiểu quá đơn giản

PostgreSQL có các quy tắc timing về BEFORE triggers, generated columns, constraints, AFTER triggers và deferred constraint triggers. Một số kiểm tra có thể trì hoãn, một số không; foreign key enforcement còn có triggers nội bộ.

**Không xây chương trình bằng cách giả định tất cả constraints nhất định chạy trước tất cả AFTER triggers hoặc ngược lại theo một danh sách cứng áp dụng mọi phiên bản.** Điều quan trọng là các constraints không deferred phải được bảo toàn theo semantics của statement, còn deferred constraints có thể kiểm tra đến cuối transaction.

### 29.3. Không che lỗi bằng RETURN NULL

Nếu `BEFORE INSERT` trả NULL, row bị bỏ qua và constraint cho row đó có thể không được kiểm tra theo cách một INSERT bình thường sẽ được kiểm tra, vì row không thực sự được insert. Đừng dùng `RETURN NULL` để thay cho một `CHECK`/validation bắt buộc mà caller phải biết lỗi.

### 29.4. Trigger không là cột UNIQUE

Muốn email hoặc mã đơn là duy nhất, dùng `UNIQUE` constraint/index, không viết trigger:

~~~sql
-- Dễ race condition nếu chỉ dùng trigger:
-- IF EXISTS(SELECT 1 FROM orders WHERE code = NEW.code) THEN
--     RAISE EXCEPTION ...;
-- END IF;
~~~

Hai transactions đồng thời có thể cùng không thấy row của nhau và tạo dữ liệu trùng nếu không có unique constraint/locking đúng. Trigger chỉ là lớp hỗ trợ, không mặc nhiên thay concurrency-safe constraint.

## 30. Trigger và transaction: tất cả DML vẫn có thể rollback

Các effects trong trigger function là một phần của statement/transaction chứa DML gốc, không tự có transaction độc lập.

### 30.1. Ví dụ rollback audit

~~~sql
BEGIN;

INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES ('Rollback Demo', 1000, 'new');

-- Trong transaction này có thể thấy hàng và audit/trace mới.

ROLLBACK;
~~~

Sau rollback, không còn row mới, audit và trace tương ứng. Nhưng các giá trị sequence/identity đã cấp có thể vẫn bị tiêu thụ.

### 30.2. BEFORE và AFTER không thể tự COMMIT

Trigger function PL/pgSQL là **function**, không phải procedure được gọi top-level bằng `CALL`. Không đặt `COMMIT`/`ROLLBACK` trong trigger function để mong audit sống sót sau transaction rollback.

Ngay cả khi trigger function gọi một procedure có `COMMIT` nội bộ, call context của trigger function cũng không trở thành top-level `CALL` đủ điều kiện transaction control. Nếu cần ghi log độc lập với transaction chính, thiết kế logging/streaming ở ngoài transaction phù hợp.

### 30.3. Exception trong trigger

~~~sql
RAISE EXCEPTION
    'order % cannot be updated', NEW.order_id;
~~~

Thông thường làm statement gặp lỗi. Nếu caller đang có explicit transaction và không bắt lỗi tại một subtransaction context phù hợp, transaction có thể đi vào trạng thái aborted và cần `ROLLBACK`.

### 30.4. EXCEPTION block trong trigger

PL/pgSQL cho phép `BEGIN ... EXCEPTION ... END` để xử lý một số lỗi có thể phục hồi. Block có exception handler được hỗ trợ bởi subtransaction; thay đổi SQL của phần block lỗi bị rollback. Dùng thận trọng, không nuốt lỗi cốt lõi rồi tiếp tục âm thầm.

### 30.5. External side effects

Gửi email, gọi API thanh toán hoặc HTTP webhook trực tiếp trong trigger không nằm dưới cơ chế rollback ACID của PostgreSQL. Nếu transaction rollback, email/webhook có thể vẫn xảy ra. Dùng **transactional outbox** hoặc event pipeline được thiết kế cho after-commit delivery, có idempotency.

## 31. Trigger recursion: khi trigger ghi lại chính bảng đang kích hoạt nó

Một lỗi phổ biến:

~~~sql
-- Minh họa cấu trúc gây đệ quy:
CREATE FUNCTION public.bad_after_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE public.some_table
    SET updated_at = clock_timestamp()
    WHERE id = NEW.id;

    RETURN NULL;
END;
$$;
~~~

Nếu function này được gắn `AFTER UPDATE` trên **`public.some_table`**, UPDATE bên trong có thể kích hoạt chính trigger một lần nữa:

~~~text
UPDATE row
  → AFTER UPDATE trigger
      → UPDATE same row
          → AFTER UPDATE trigger
              → UPDATE same row
                  → ...
~~~

Kết quả có thể gây vòng lặp, stack depth exceeded, lock contention hoặc chi phí lớn.

### 31.1. Cách tự nhiên hơn: BEFORE UPDATE sửa NEW

~~~sql
CREATE FUNCTION public.set_timestamp_before()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
~~~

`BEFORE ROW` có thể chỉnh `NEW` **mà không phát thêm một UPDATE SQL vào chính bảng**, tránh vòng lặp do AFTER trigger tự cập nhật row.

### 31.2. pg_trigger_depth()

PostgreSQL cung cấp:

~~~sql
SELECT pg_trigger_depth();
~~~

Hàm này cho biết số mức trigger execution đang lồng nhau. Nó có thể dùng như **tín hiệu chẩn đoán**, không phải giải pháp thiết kế để bảo đảm invariant. Dùng `IF pg_trigger_depth() > 1 THEN RETURN NEW; END IF;` có thể che đi những tác vụ hợp lệ do triggers khác gây ra và phụ thuộc call context.

### 31.3. Các chiến lược tránh recursion

- Chọn `BEFORE ROW` để chỉnh **cùng row**.
- Nếu `AFTER` cần ghi bảng khác, đảm bảo bảng ấy không gọi vòng về bảng gốc.
- Giữ logic trigger đơn giản và phân chia trách nhiệm rõ.
- Chỉ UPDATE khi giá trị thực sự thay đổi.
- Dùng `WHEN (OLD.x IS DISTINCT FROM NEW.x)` khi phù hợp.
- Thiết kế idempotency cho side-table events.
- Test nested DML, cascades, UPSERT và concurrent transactions.

### 31.4. Recursion không chỉ qua cùng bảng

~~~text
orders AFTER UPDATE → UPDATE customers
customers AFTER UPDATE → UPDATE orders
orders AFTER UPDATE → ...
~~~

Đây là **cross-table recursion**, cần vẽ dependency graph và bỏ vòng phụ thuộc thay vì cố chữa bằng threshold depth tùy tiện.

## 32. Hiệu năng: row-level trigger có thể tạo hiệu ứng N+1

Giả sử một câu UPDATE thay đổi 100.000 rows và `AFTER ROW` trigger mỗi hàng thực hiện thêm một `SELECT` và một `INSERT` audit. Tổng số statement nội bộ có thể trở thành rất lớn.

### 32.1. Row vs statement

| Thiết kế | Với 100.000 rows |
| --- | --- |
| `BEFORE ROW` chuẩn hóa một field | ~100.000 invocations trigger function |
| `AFTER ROW` audit mỗi row | ~100.000 invocations + inserts audit |
| `AFTER STATEMENT` không transition table | 1 invocation, nhưng không có tập rows thay đổi nếu không dùng cơ chế khác |
| `AFTER STATEMENT` + transition table | 1 invocation và có thể xử lý 100.000 rows bằng SQL set-based |

Các con số là ví dụ khái niệm; khi có partitioning/foreign key transition sets hoặc nhiều statements nội bộ, số invocations cụ thể có thể khác.

### 32.2. Ưu tiên thao tác set-based

Nếu chỉ cần thống kê **số rows/amount delta của cả statement**, `AFTER STATEMENT` với transition table có thể giảm số SQL calls so với `AFTER ROW`.

Nếu cần **lịch sử chi tiết từng row**, row-level audit vẫn phù hợp, nhưng có thể cân nhắc transition table rồi `INSERT INTO audit SELECT ... FROM changed_rows` theo tập khi semantics hỗ trợ.

### 32.3. Chi phí trong transaction

Audit writes tăng WAL/index updates/lock footprint. Nếu trigger function gọi nhiều bảng, một UPDATE đơn giản của ứng dụng có thể trở thành transaction phức tạp. Khi phát hiện statement chậm, phải tính cả trigger work chứ không chỉ plan của DML gốc.

### 32.4. Kiểm tra trigger timings trong EXPLAIN ANALYZE

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
UPDATE trg_lab_367.orders
SET note = 'performance demo'
WHERE status = 'new';
~~~

Trên nhiều phiên bản PostgreSQL, `EXPLAIN ANALYZE` có thể hiển thị số lần gọi và thời gian thực thi triggers, cùng plan của UPDATE. **Lệnh trên thực sự UPDATE dữ liệu**; chỉ chạy trên lab hoặc bọc transaction rồi ROLLBACK nếu có kiểm soát tác động.

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE trg_lab_367.orders
SET note = 'temporary benchmark'
WHERE status = 'new';

ROLLBACK;
~~~

### 32.5. Không hiểu ROLLBACK là không có tác động vận hành

Một lần `EXPLAIN ANALYZE` + ROLLBACK vẫn đã tiêu thụ CPU, I/O, WAL và locks trong lúc chạy, có thể gây tác động tới hệ thống. Trên production, cần kế hoạch benchmark phù hợp chứ không dựa vào rollback như phép bảo vệ hoàn toàn.

### 32.6. Kiểm tra index trên audit

Audit table có thể lớn nhanh hơn bảng chính nếu mỗi UPDATE ghi một record. Cân nhắc indexes theo truy vấn tra cứu lịch sử, retention/partitioning và quyền dữ liệu thay vì lập index cho mọi cột JSONB.

### 32.7. Không gọi network trong trigger mỗi row

Ngay cả khi SQL DML chỉ 100ms, trigger gọi 100 API requests nối tiếp có thể biến statement thành một request dài nhiều giây, giữ transaction locks trong lúc chờ network. Đẩy external processing sang outbox/worker độc lập.

## 33. Bảo mật trigger function: INVOKER, DEFINER và search_path

Trigger function bình thường thực thi theo quyền của **caller** (`SECURITY INVOKER` mặc định). Trong một số mô hình, cần trigger function được định nghĩa `SECURITY DEFINER` để ghi audit table mà role ứng dụng không được phép INSERT trực tiếp.

### 33.1. Rủi ro của SECURITY DEFINER

Một function chạy với quyền owner có thể bị khai thác nếu:

- Dùng tên bảng/hàm không schema-qualified trong schema kẻ tấn công có thể tạo object;
- Dùng dynamic SQL ghép input không quote/bind an toàn;
- Owner có quyền quá rộng;
- Role không đáng tin được quyền thay đổi trigger function;
- Quyền `EXECUTE` trên function bị cấp rộng ngoài ý định.

### 33.2. Mẫu định hướng

~~~sql
CREATE FUNCTION trg_lab_367.secure_audit_example()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, trg_lab_367, pg_temp
AS $$
DECLARE
    v_order_id bigint;
    v_old jsonb;
    v_new jsonb;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_order_id := NEW.order_id;
        v_old := NULL;
        v_new := to_jsonb(NEW);
    ELSIF TG_OP = 'UPDATE' THEN
        v_order_id := NEW.order_id;
        v_old := to_jsonb(OLD);
        v_new := to_jsonb(NEW);
    ELSIF TG_OP = 'DELETE' THEN
        v_order_id := OLD.order_id;
        v_old := to_jsonb(OLD);
        v_new := NULL;
    ELSE
        RAISE EXCEPTION 'Unsupported trigger operation %', TG_OP;
    END IF;

    INSERT INTO trg_lab_367.order_audit(
        order_id, action, old_data, new_data
    )
    VALUES (
        v_order_id, TG_OP, v_old, v_new
    );

    RETURN NULL;
END;
$$;
~~~

Đây là **mẫu minh họa về quyền và search_path**, không phải lời khuyên tự động chuyển mọi audit trigger thành `SECURITY DEFINER`. Việc phân nhánh `TG_OP` tránh truy cập field của `NEW` trong DELETE hoặc `OLD` trong INSERT. Nếu dùng trong production, phải kiểm tra quyền owner, GRANT EXECUTE, khả năng truy cập audit và khả năng bị kích hoạt đệ quy; chỉ cài function này nếu thật sự cần mô hình quyền đó.

### 33.3. Không biến trigger thành đường vượt quyền

Một role có quyền UPDATE bảng chính nhưng không có quyền xem thông tin nhạy cảm không nên có thể dùng trigger hoặc view để rò rỉ dữ liệu của người khác. Cần xem Row-Level Security, view privileges, ownership, `SECURITY DEFINER` và quyền đọc audit.

### 33.4. Trigger arguments không phải nguồn tin cậy tuyệt đối

`TG_ARGV[]` là dữ liệu cấu hình của trigger khi tạo. Nếu người có quyền thay trigger thay được arguments, chức năng trigger sẽ thay đổi. Tách rõ migration/owner privileges và dữ liệu nghiệp vụ do client gửi qua row.

### 33.5. Không tự động disable triggers để sửa dữ liệu

~~~sql
-- Lệnh nguy hiểm nếu áp dụng thiếu kiểm soát:
-- ALTER TABLE trg_lab_367.orders DISABLE TRIGGER USER;
~~~

Khi disable user triggers, logic normalize/audit/validation có thể không chạy. `DISABLE TRIGGER ALL` và những thao tác liên quan system constraint triggers có ảnh hưởng lớn hơn, có thể cần quyền cao và làm hỏng integrity nếu dùng sai.

Mọi thay đổi trạng thái trigger cần migration/owner, khoảng bảo trì, kiểm tra dữ liệu và bật lại đúng cách; không sử dụng làm “mẹo” để bỏ qua trigger khó hiểu.

## 34. Quyền quản lý trigger và vòng đời migration

Trigger definition gắn với relation. Khi deploy thay đổi:

1. Thiết kế trigger function có version/contract rõ ràng.
2. Kiểm tra dependency nếu có nhiều triggers cùng gọi một function.
3. Cân nhắc `CREATE OR REPLACE FUNCTION` thay đổi logic của **mọi trigger đang trỏ tới function đó**.
4. Dùng migration có version, kiểm tra schema qualification/search_path.
5. Thử INSERT/UPDATE/DELETE/ROLLBACK/cascades theo môi trường lab.
6. Đo chi phí khi bulk DML và concurrency.
7. Có kế hoạch rollback hoặc fix-forward.

### 34.1. Đổi tên trigger có thể đổi thứ tự

Nếu cùng loại trigger được chạy theo thứ tự alphabet, rename trigger có thể thay đổi behavior khi chúng tương tác trên `NEW`. Không xem rename là thay đổi thuần thẩm mỹ nếu nghiệp vụ phụ thuộc ordering.

### 34.2. DROP TRIGGER không xóa function

~~~sql
DROP TRIGGER IF EXISTS trg_10_normalize_order
ON trg_lab_367.orders;
~~~

Lệnh trên gỡ trigger khỏi bảng, **không tự xóa trigger function** `trg_lab_367.normalize_order_before()` nếu không có lệnh riêng. Trong lab hiện tại, không chạy lệnh này nếu còn muốn quan sát normalize behavior ở các bài sau.

### 34.3. CREATE OR REPLACE FUNCTION

~~~sql
CREATE OR REPLACE FUNCTION trg_lab_367.some_trigger_function()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN NEW;
END;
$$;
~~~

Đây là mẫu minh họa cách cập nhật thân function; trong production phải kiểm tra cả signature, volatility/security/search_path, dependencies và transaction timing. Không đổi một function được nhiều triggers sử dụng mà không biết ảnh hưởng.

### 34.4. Kiểm tra trigger enabled mode

~~~sql
SELECT
    t.tgname,
    t.tgenabled,
    t.tgisinternal,
    c.relname AS relation_name,
    n.nspname AS schema_name,
    pg_catalog.pg_get_triggerdef(t.oid) AS definition
FROM pg_catalog.pg_trigger AS t
JOIN pg_catalog.pg_class AS c ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'trg_lab_367'
ORDER BY c.relname, t.tgname;
~~~

`tgenabled` có nhiều trạng thái liên quan tới replication role, không chỉ boolean đơn giản. Khi thấy một trigger "enabled" trong metadata nhưng không chạy, kiểm tra thêm session replication mode và nguồn phát DML theo quy tắc vận hành.

### 34.5. Đừng chỉnh session_replication_role tùy tiện

`session_replication_role` ảnh hưởng cơ chế kích hoạt triggers/rules, kể cả những cơ chế bảo vệ tham chiếu; thay đổi có thể dẫn tới dữ liệu không được ràng buộc như mong muốn. Không dùng công tắc này như cách nhập dữ liệu nhanh trong hệ thống production mà thiếu thiết kế và kiểm soát quyền.

## 35. Quan sát trigger thực tế: truy vấn metadata

Các câu SQL dưới đây chủ yếu **đọc metadata**, giúp xác định trigger nào đang gắn vào relation và function nào được gọi. Không thực hiện `ALTER TABLE DISABLE TRIGGER` hay `DROP TRIGGER` khi chưa biết dependencies.

### 35.1. Liệt kê trigger và function

~~~sql
SELECT
    n.nspname AS table_schema,
    c.relname AS table_name,
    t.tgname AS trigger_name,
    t.tgenabled AS enabled_mode,
    p.oid::regprocedure AS function_signature,
    pg_catalog.pg_get_triggerdef(t.oid) AS definition
FROM pg_catalog.pg_trigger AS t
JOIN pg_catalog.pg_class AS c
    ON c.oid = t.tgrelid
JOIN pg_catalog.pg_namespace AS n
    ON n.oid = c.relnamespace
JOIN pg_catalog.pg_proc AS p
    ON p.oid = t.tgfoid
WHERE n.nspname = 'trg_lab_367'
ORDER BY n.nspname, c.relname, t.tgname;
~~~

### 35.2. Chỉ user-defined triggers

~~~sql
SELECT
    t.tgname,
    pg_catalog.pg_get_triggerdef(t.oid)
FROM pg_catalog.pg_trigger AS t
WHERE t.tgrelid = 'trg_lab_367.orders'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

Trong bảng có FK, system/internal triggers có thể đóng vai trò referential integrity; đừng nhầm chúng với business triggers do ứng dụng tự viết.

### 35.3. information_schema.triggers

~~~sql
SELECT
    trigger_schema,
    trigger_name,
    event_manipulation,
    event_object_schema,
    event_object_table,
    action_timing,
    action_orientation
FROM information_schema.triggers
WHERE event_object_schema = 'trg_lab_367'
ORDER BY event_object_table, trigger_name;
~~~

`information_schema` cung cấp cách nhìn portable về trigger metadata, nhưng một số thông tin chuyên sâu PostgreSQL như enabled mode, constraint deferral, internal triggers hoặc transition relation definitions cần xem `pg_catalog` và `pg_get_triggerdef`.

### 35.4. Xem định nghĩa function

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.prosecdef AS security_definer,
    p.proconfig,
    pg_catalog.pg_get_functiondef(p.oid) AS function_definition
FROM pg_catalog.pg_proc AS p
WHERE p.pronamespace = 'trg_lab_367'::regnamespace
  AND p.prorettype = 'pg_catalog.trigger'::regtype
ORDER BY p.oid::regprocedure::text;
~~~

Đặc biệt chú ý function `SECURITY DEFINER`, các lệnh cập nhật bảng phụ, dynamic SQL, `RAISE EXCEPTION` và các nhánh `TG_OP`.

### 35.5. Quan sát trace/audit

~~~sql
SELECT
    event_name,
    timing,
    trigger_level,
    COUNT(*) AS invocations_recorded
FROM trg_lab_367.trigger_trace
GROUP BY event_name, timing, trigger_level
ORDER BY event_name, timing, trigger_level;
~~~

Đếm trace chỉ đúng với những triggers ghi trace trong lab. Nó **không** đếm mọi trigger invocation nếu function nào đó không ghi log, khi statement bị rollback hoặc khi nhiều lệnh khác ghi vào bảng trace.

## 36. Runbook xử lý sự cố trigger

### Giai đoạn A — Xác định sự kiện và timing

Thu thập:

1. DML gốc là `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`, `COPY`, `MERGE` hay UPSERT?
2. Statement ảnh hưởng bao nhiêu rows?
3. Có row-level/statement-level triggers nào gắn vào relation?
4. Có BEFORE, AFTER, INSTEAD OF hay constraint trigger deferred?
5. Có view/partition/foreign key cascade không?
6. Session đang ở transaction nào và đã commit/rollback chưa?

### Giai đoạn B — Xem hành vi bất thường

| Dấu hiệu | Câu hỏi chẩn đoán |
| --- | --- |
| INSERT trả 0 rows dù gửi một row | Có `BEFORE INSERT ROW RETURN NULL` hoặc `INSTEAD OF ... RETURN NULL`? |
| UPDATE thay đổi cột sai | Có nhiều BEFORE UPDATE triggers cùng sửa `NEW` theo tên alphabet? |
| AFTER UPDATE sửa `NEW` không có hiệu lực | Có dùng `RETURN NEW` để mong thay hàng sau UPDATE? |
| Chỉ 0 rows bị ảnh hưởng mà log statement vẫn có | Statement-level trigger vẫn chạy khi 0 rows |
| UPDATE giá trị bằng chính nó vẫn audit | `UPDATE OF` chỉ xét SET list; thiếu `WHEN IS DISTINCT FROM` |
| View INSERT không ghi vào base table | INSTEAD OF trigger có thực thi INSERT thật không? |
| View RETURNING trả 0 rows | INSTEAD OF trigger có trả NULL thay vì row được xử lý? |
| Audit có lúc thiếu | Transaction rollback? Trigger disabled? Firing event không tương ứng? |
| Audit ghi nhiều hơn dự kiến | Cascade FK, UPSERT, MERGE, trigger trên nhiều relations? |
| Trigger chạy sau commit như mong muốn? | Thực tế AFTER thường chạy trong transaction, không phải after-commit |
| DELETE hàng paid báo lỗi | BEFORE DELETE guard/constraint đang ngăn |
| TRUNCATE bỏ qua audit DELETE | Không có row-level TRUNCATE triggers |
| UPDATE partition key không vào AFTER UPDATE ROW | Row movement thành DELETE+INSERT |
| Timeout/CPU cao khi bulk update | N+1 SQL trong row triggers hoặc recursion |
| Stack depth exceeded | Trigger cập nhật cùng bảng/vòng cross-table? |
| Constraint chỉ lỗi ở COMMIT | Constraint trigger deferred hoặc FK deferred? |
| Trigger không được gọi ở replication flow | Enabled mode/session_replication_role? |

### Giai đoạn C — Tái hiện an toàn

Trong schema lab hoặc một môi trường kiểm thử đại diện:

~~~sql
BEGIN;

UPDATE trg_lab_367.orders
SET note = 'test run'
WHERE order_id = 1;

SELECT *
FROM trg_lab_367.trigger_trace
ORDER BY trace_id DESC
LIMIT 10;

SELECT *
FROM trg_lab_367.order_audit
ORDER BY audit_id DESC
LIMIT 10;

ROLLBACK;
~~~

Test này giúp quan sát trigger writes **trong transaction hiện tại** và rollback lab changes. Lưu ý: vẫn có chi phí I/O, WAL/locks trong lúc chạy; không phải một phép thử không có tác động vận hành.

### Giai đoạn D — Chẩn đoán hiệu năng

Chạy `EXPLAIN (ANALYZE, BUFFERS)` trên câu DML lab hoặc benchmark không ảnh hưởng production, đọc:

- Plan thao tác trên bảng chính;
- Trigger time/calls nếu được hiển thị;
- Buffer hits/reads và WAL hoạt động theo metric có sẵn;
- Số rows, lock waits;
- Các queries phụ được gọi từ trigger;
- Tốc độ tăng audit/side tables.

`EXPLAIN ANALYZE` **thực thi DML**. Đừng chạy trên production với giả định nó chỉ hiển thị plan.

### Giai đoạn E — Đề xuất sửa tối thiểu

- Cần chỉnh chính hàng: dùng `BEFORE ROW RETURN NEW`, không AFTER tự UPDATE row.
- Cần audit: `AFTER ROW` hoặc AFTER statement + transition tables.
- Cần bảng tổng hợp: ưu tiên set-based, tránh N+1 queries.
- Cần DML qua view: xác định view tự updatable hay cần INSTEAD OF.
- Cần invariant: ưu tiên constraint nếu đủ; dùng constraint trigger deferred chỉ khi thực sự cần.
- Cần thông báo ngoài DB: dùng outbox, không gọi network trong trigger.
- Cần phân biệt giá trị đổi: dùng `IS DISTINCT FROM`.
- Cần nhiều triggers: xem thứ tự tên và cân nhắc gộp logic phụ thuộc.

### Giai đoạn F — Triển khai có giám sát

Ghi lại owner của trigger, SQL function definition trước/sau, migration version, plan rollback, dữ liệu backfill, metric về latency/locks và chính sách quyền. Không disable triggers để giải quyết một lỗi performance mà chưa hiểu rủi ro integrity.

## 37. Quy tắc chọn loại trigger

| Nhu cầu | Loại ưu tiên | Vì sao |
| --- | --- | --- |
| Trim tên khách trước INSERT | `BEFORE INSERT FOR EACH ROW` | Sửa `NEW` ngay trước khi ghi |
| Cập nhật `updated_at` của row | `BEFORE UPDATE FOR EACH ROW` | Tránh UPDATE lại chính row trong AFTER |
| Từ chối DELETE đơn paid | `BEFORE DELETE FOR EACH ROW` + exception | Chặn thay đổi rõ ràng |
| Audit OLD/NEW sau UPDATE | `AFTER UPDATE FOR EACH ROW` | Đã có row sau các BEFORE changes |
| Tóm tắt 10.000 rows INSERT cùng statement | `AFTER INSERT FOR EACH STATEMENT REFERENCING NEW TABLE` | Xử lý tập hàng đã insert |
| Thống kê sự kiện dù 0 rows | `BEFORE/AFTER ... FOR EACH STATEMENT` | Chạy theo statement |
| Viết qua join/calculated view | `INSTEAD OF ... FOR EACH ROW` | Tự ánh xạ DML xuống base tables |
| Chặn TRUNCATE | `BEFORE TRUNCATE FOR EACH STATEMENT` hoặc quyền TRUNCATE | Không có row-level TRUNCATE |
| Ràng buộc liên hàng cần kiểm tra cuối transaction | Deferred `AFTER ROW CONSTRAINT TRIGGER` | Có thể trì hoãn khi được định nghĩa |
| Duy nhất customer code | `UNIQUE` constraint | Có bảo vệ concurrency chuẩn |
| Hợp lệ kiểu/cột đơn giản | `CHECK`/`NOT NULL` | Minh bạch, dễ dự đoán |
| FK tham chiếu | `FOREIGN KEY` | Không tự viết trigger chống race |
| Gửi email sau ghi DB thành công | Outbox + worker sau commit | Không gọi external API trong trigger |

### 37.1. Chọn level dựa trên bản chất logic

Nếu logic cần xem/sửa **một hàng**, chọn row-level. Nếu logic cần tính **tổng một statement**, chọn statement-level cùng transition tables khi hỗ trợ. Đừng dùng statement-level rồi cố lấy `NEW.amount` như một row cụ thể; ngược lại, đừng dùng row-level để chạy lại một aggregate toàn bảng mỗi hàng.

### 37.2. Chọn timing dựa trên mục đích

**BEFORE** cho tiền xử lý row và chặn. **AFTER** cho ghi nhận sau thay đổi và tập row. **INSTEAD OF** cho view DML mapping. Đây là nguyên tắc thiết kế hữu ích, nhưng mỗi business requirement còn phải xem transaction, constraints, security và performance.

### 37.3. Khi không nên dùng trigger

- Logic rất khó gỡ lỗi, tác động qua nhiều bảng và external services;
- API cần kết quả/luồng lỗi rõ ràng hơn một implicit side effect;
- Có thể dùng constraint/generation/default trực tiếp;
- Triggers tạo dependency vòng;
- DML bulk có latency không chấp nhận được;
- Nhiều đội thay đổi schema nhưng thiếu quy trình migration/test triggers.

Trong những tình huống ấy, function/procedure explicit, service layer, outbox, constraints hoặc pipeline dữ liệu có thể dễ kiểm soát hơn.

## 38. Bài tập thực hành — phần cơ bản và thời điểm chạy

Các bài tập sử dụng schema `trg_lab_367` và các trigger đã tạo trong bài. Do nhiều ví dụ thay đổi dữ liệu, **kết quả row count thực tế phụ thuộc thứ tự bạn đã chạy**; khi cần, tạo dữ liệu lab mới với key/tên khác thay vì giả định `order_id` luôn bằng một số cụ thể. Không chạy những ví dụ cố ý gây lỗi hoặc DROP/TRUNCATE trên môi trường production.

### Bài 1 — Nhận diện ba timing

Một bảng orders cần: (a) chuẩn hóa tên trước khi lưu; (b) ghi audit sau khi thay đổi; (c) cập nhật qua view có cột tính toán.

**Câu hỏi:** chọn `BEFORE`, `AFTER` hay `INSTEAD OF` cho từng nhu cầu?

**Đáp án định hướng:** (a) BEFORE ROW; (b) AFTER ROW hoặc AFTER STATEMENT + transition table tùy granularity; (c) INSTEAD OF ROW trên view.

### Bài 2 — Timing khác level

Phân tích bốn trigger:

~~~sql
BEFORE UPDATE FOR EACH ROW
BEFORE UPDATE FOR EACH STATEMENT
AFTER UPDATE FOR EACH ROW
AFTER UPDATE FOR EACH STATEMENT
~~~

**Câu hỏi:** với UPDATE tác động đúng 5 hàng, số lần gọi mỗi loại thường là bao nhiêu?

**Đáp án:** 5, 1, 5, 1 trong trường hợp đơn giản không có hàng bị bỏ qua hoặc cơ chế đặc biệt.

### Bài 3 — Statement ảnh hưởng 0 hàng

~~~sql
UPDATE trg_lab_367.orders
SET note = 'nothing'
WHERE order_id = -999999;
~~~

**Câu hỏi:** statement-level triggers còn chạy không? Row-level triggers chạy bao nhiêu lần?

**Đáp án:** statement-level BEFORE/AFTER vẫn chạy; row-level 0 lần.

### Bài 4 — Dự đoán TG_OP

Một trigger function được gắn với `AFTER INSERT OR UPDATE OR DELETE`.

**Câu hỏi:** `TG_OP` có thể là những chuỗi nào? Có thể là `'AFTER'` không?

**Đáp án:** `'INSERT'`, `'UPDATE'`, `'DELETE'`; timing `'AFTER'` nằm ở `TG_WHEN`.

### Bài 5 — NEW và OLD

Hoàn thành bảng:

| DML | Có NEW row? | Có OLD row? |
| --- | --- | --- |
| INSERT | ? | ? |
| UPDATE | ? | ? |
| DELETE | ? | ? |

**Đáp án:** INSERT có NEW; UPDATE có cả; DELETE có OLD.

### Bài 6 — TG_LEVEL

`TG_LEVEL` của một trigger `AFTER UPDATE ... FOR EACH STATEMENT` là gì? Giá trị trả về của function có quyết định UPDATE được chạy không?

**Đáp án:** `STATEMENT`; return value bị bỏ qua.

### Bài 7 — BEFORE INSERT chuẩn hóa

Chạy:

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES ('  Thảo  ', 45000, 'new')
RETURNING customer_name;
~~~

**Câu hỏi:** giá trị nào được lưu và `RETURNING` hiển thị?

**Đáp án:** `Thảo`, vì trigger `BEFORE INSERT ROW` sửa `NEW` rồi trả `NEW`.

### Bài 8 — Tên rỗng

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
VALUES ('   ', 1000, 'new');
~~~

**Câu hỏi:** trigger normalize nên trả NULL im lặng hay `RAISE EXCEPTION`? Tác động tới caller?

**Đáp án định hướng:** lab dùng exception để caller biết input sai; statement không commit row.

### Bài 9 — Trả NULL trong BEFORE INSERT

~~~sql
INSERT INTO trg_lab_367.import_queue(source_value)
VALUES ('valid'), ('   ');
~~~

**Câu hỏi:** bảng có bao nhiêu hàng mới, khi input thứ hai bị `BEFORE ROW RETURN NULL`?

**Đáp án:** một hàng `valid`; giá trị trống bị bỏ qua.

### Bài 10 — RETURN NULL ở statement-level

Một `BEFORE UPDATE FOR EACH STATEMENT` trigger function luôn `RETURN NULL`.

**Câu hỏi:** nó có làm PostgreSQL bỏ qua cả UPDATE không?

**Đáp án:** không, return value của statement-level trigger bị bỏ qua.

### Bài 11 — RETURN NULL ở AFTER ROW

Function `audit_order_after()` trả NULL. Vì sao row gốc vẫn được INSERT/UPDATE/DELETE?

**Đáp án:** return value của AFTER trigger bị bỏ qua; row operation đã được thực hiện theo semantics trigger.

### Bài 12 — AFTER ROW sửa NEW

Một developer gán `NEW.amount := 0` và `RETURN NEW` trong `AFTER UPDATE` để giảm giá đơn.

**Câu hỏi:** giá trị của hàng có thực sự bị thay không?

**Đáp án:** không theo cách đó. Phải dùng BEFORE UPDATE để sửa `NEW`, hoặc SQL UPDATE riêng có kiểm soát và tránh recursion nếu thật cần.

### Bài 13 — DELETE trên đơn paid

Sau khi chuyển một order sang `paid`, thử DELETE.

**Câu hỏi:** trigger nào ngăn thao tác? Vì sao `RAISE EXCEPTION` thường rõ hơn `RETURN NULL` khi business không cho xóa?

### Bài 14 — AFTER là sau COMMIT?

~~~sql
BEGIN;
UPDATE trg_lab_367.orders
SET note = 'temporary'
WHERE order_id = 1;
ROLLBACK;
~~~

**Câu hỏi:** audit/trace vừa được tạo có tồn tại sau rollback không?

**Đáp án:** không, nếu thuộc cùng transaction và không có external side effects.

### Bài 15 — Đọc OLD/NEW của UPDATE

Viết query đọc `order_audit` cho những actions `UPDATE`, lấy:

~~~sql
old_data ->> 'customer_name'
new_data ->> 'customer_name'
~~~

**Câu hỏi:** AFTER trigger đã đọc tên trước hay sau khi BEFORE normalize?

### Bài 16 — CHECK và BEFORE trigger

INSERT order có `amount=-100`, `customer_name=' Valid '`.

**Câu hỏi:** dù BEFORE trigger chuẩn hóa tên, CHECK constraint làm gì với transaction?

**Đáp án:** chặn row không hợp lệ; thay đổi của statement không được commit.

### Bài 17 — UPDATE OF amount

~~~sql
UPDATE trg_lab_367.orders
SET amount = amount
WHERE order_id = 1;
~~~

**Câu hỏi:** `UPDATE OF amount` trigger được xét hay không? Nếu có `WHEN OLD.amount IS DISTINCT FROM NEW.amount`, function log amount có chạy không?

**Đáp án:** target column được chỉ định; WHEN false nếu giá trị không đổi nên function không chạy.

### Bài 18 — IS DISTINCT FROM

Giải thích khác biệt:

~~~sql
OLD.note <> NEW.note
OLD.note IS DISTINCT FROM NEW.note
~~~

**Câu hỏi:** nếu một bên `NULL`, cách nào trả boolean rõ ràng?

### Bài 19 — BEFORE trigger đổi cột không có trong UPDATE SET

Một SQL `UPDATE orders SET note='x'` nhưng một BEFORE trigger tự đổi `NEW.amount`.

**Câu hỏi:** `AFTER UPDATE OF amount` có tự biết amount đã đổi không?

**Đáp án:** không phải lúc nào; `UPDATE OF` dựa vào target list của SQL. Dùng `AFTER UPDATE ... WHEN OLD.amount IS DISTINCT FROM NEW.amount` khi cần bắt mọi thay đổi thực tế.

### Bài 20 — WHEN của INSTEAD OF

Một developer muốn viết `INSTEAD OF INSERT ON view ... WHEN (...)`.

**Câu hỏi:** PostgreSQL có hỗ trợ WHEN cho INSTEAD OF trigger không? Đưa điều kiện vào đâu?

**Đáp án:** không; viết `IF` trong trigger function.

### Bài 21 — Nhiều triggers cùng loại

Hai BEFORE UPDATE triggers có tên `trg_b_trim` và `trg_a_uppercase` cùng sửa `NEW.customer_name`.

**Câu hỏi:** trigger nào chạy trước và vì sao thứ tự đó quan trọng?

**Đáp án:** cùng loại chạy theo thứ tự tên alphabet; `trg_a_uppercase` trước `trg_b_trim`.

### Bài 22 — WHEN trong AFTER ROW

Thêm trigger `AFTER UPDATE ... WHEN (OLD.status IS DISTINCT FROM NEW.status)`.

**Câu hỏi:** nó có cần gọi function cho các rows không đổi status không? Vì sao WHEN giúp giảm overhead?

### Bài 23 — Row-level audit vs statement aggregate

Một statement INSERT 10.000 rows, cần audit từng row và báo tổng amount của cả statement.

**Bài tập:** chọn trigger timing/level cho hai yêu cầu, giải thích lợi ích của transition tables.

### Bài 24 — NEW TABLE

Tạo `AFTER INSERT ... REFERENCING NEW TABLE AS inserted_rows`, dùng:

~~~sql
SELECT COUNT(*), SUM(amount) FROM inserted_rows;
~~~

**Câu hỏi:** tập inserted_rows là toàn bộ bảng hay chỉ rows của statement?

**Đáp án:** chỉ những rows mới của sự kiện INSERT hiện tại.

### Bài 25 — INSERT 0 hàng

~~~sql
INSERT INTO trg_lab_367.orders(
    customer_name, amount, status
)
SELECT 'Nobody', 0, 'new'
WHERE FALSE;
~~~

**Câu hỏi:** AFTER STATEMENT trigger vẫn chạy không? Transition NEW TABLE có bao nhiêu rows?

**Đáp án:** trigger chạy, transition relation rỗng.

### Bài 26 — OLD TABLE và NEW TABLE của UPDATE

Viết `AFTER UPDATE FOR EACH STATEMENT` trigger có:

~~~sql
REFERENCING OLD TABLE AS old_orders
            NEW TABLE AS new_orders
~~~

**Bài tập:** tính tổng `new.amount - old.amount` theo cùng khóa chính trong lab; khi nào join khóa chính có thể sai nếu khóa được UPDATE?

### Bài 27 — UPDATE OF kết hợp transition relation

**Câu hỏi:** vì sao PostgreSQL không cho `AFTER UPDATE OF amount ... REFERENCING ...`?

**Gợi ý:** dùng `AFTER UPDATE` không có column list, sau đó so old/new sets trong function.

### Bài 28 — NEW trong statement trigger

Trong `AFTER UPDATE FOR EACH STATEMENT`, một developer viết `NEW.amount`.

**Câu hỏi:** tại sao không có một NEW row đại diện? Nên dùng gì nếu cần nhiều rows vừa update?

### Bài 29 — INSTEAD OF INSERT

~~~sql
INSERT INTO trg_lab_367.v_order_editor(
    customer_name, amount, status
)
VALUES ('  My  ', 10000, 'new')
RETURNING order_id, customer_name, gross_estimate;
~~~

**Câu hỏi:** thao tác nào thật sự INSERT xuống base table? Vì sao `RETURNING` có thể hiển thị customer_name đã chuẩn hóa?

### Bài 30 — INSTEAD OF DELETE và OLD

Viết nhánh `TG_OP='DELETE'` xóa base row theo `OLD.order_id` và trả `OLD` khi đã xử lý.

**Câu hỏi:** `RETURN NULL` sẽ tác động thế nào đến row count/RETURNING của view?

### Bài 31 — View đã tự updatable

Tạo một view chỉ SELECT các cột từ một bảng, không join/aggregate/expression phức tạp.

**Câu hỏi:** có luôn cần INSTEAD OF trigger không? Hãy nêu điều kiện để simple view tự updatable, và khi nào `WITH CHECK OPTION` có ý nghĩa.

### Bài 32 — View có cột tính toán

View `v_order_editor` có `gross_estimate = amount * 1.05`.

**Câu hỏi:** tại sao trigger view phải tự tính lại `gross_estimate` khi trả `RETURNING`? Vì sao không nên coi nó là một field độc lập để khách hàng cập nhật?

### Bài 33 — AFTER ROW ở base table khi ghi từ view

Gọi `INSERT INTO trg_lab_367.v_order_editor(...)`.

**Bài tập:** vẽ chuỗi `INSTEAD OF INSERT ROW trên view → INSERT bảng orders → BEFORE INSERT ROW → AFTER INSERT ROW`. Những audit records được ghi vào bảng nào?

### Bài 34 — Deferred constraint trigger

Tạo một constraint trigger `AFTER INSERT OR UPDATE DEFERRABLE INITIALLY DEFERRED`.

**Câu hỏi:** lúc nào nó có thể chạy? Khác gì với AFTER ROW trigger thông thường?

### Bài 35 — WHEN của constraint trigger

Một UPDATE trong transaction tạm biến order thành `paid` với `amount=0`, sau đó UPDATE lên `amount=50000`.

**Câu hỏi:** `WHEN (NEW.status='paid')` được đánh giá lúc nào? Tại sao trigger function deferred nên đọc **trạng thái cuối** thay vì chỉ kiểm tra captured NEW của event trước?

### Bài 36 — SET CONSTRAINTS

Trong transaction:

~~~sql
SET CONSTRAINTS trg_paid_amount_deferred IMMEDIATE;
~~~

**Câu hỏi:** điều này ảnh hưởng gì đến pending constraint-trigger events? Có biến mọi AFTER ROW trigger thành deferred/immediate constraint trigger không?

### Bài 37 — TRUNCATE

Gắn một `BEFORE DELETE ROW` audit trigger vào bảng `temp_items` rồi chạy `TRUNCATE`.

**Câu hỏi:** trigger DELETE ROW có chạy không? Loại trigger nào có thể chạy cho sự kiện TRUNCATE?

**Đáp án:** DELETE ROW không chạy; `BEFORE/AFTER TRUNCATE FOR EACH STATEMENT`.

### Bài 38 — TRUNCATE rollback

~~~sql
BEGIN;
TRUNCATE trg_lab_367.temp_items;
ROLLBACK;
~~~

**Câu hỏi:** các rows có được khôi phục không? Bản ghi do trigger TRUNCATE ghi trong transaction có tồn tại sau rollback không?

### Bài 39 — UPSERT trên conflict

Một bảng có `BEFORE INSERT` normalize `NEW.name` và `BEFORE UPDATE` gán `NEW.updated_at`.

**Câu hỏi:** khi `INSERT ... ON CONFLICT DO UPDATE` gặp conflict, tại sao cả hai loại BEFORE ROW triggers có thể tham gia? Điều gì xảy ra với giá trị `EXCLUDED`?

### Bài 40 — Statement triggers trong UPSERT

Statement dùng `ON CONFLICT DO UPDATE` nhưng thực tế không có conflict nào.

**Câu hỏi:** statement-level UPDATE trigger có thể vẫn chạy không? Vì sao statement-level trigger không đồng nghĩa ít nhất một row được thay đổi?

### Bài 41 — ON CONFLICT DO NOTHING

Một `BEFORE INSERT ROW` trigger ghi dấu thời điểm, nhưng INSERT bị unique conflict và rơi vào `DO NOTHING`.

**Câu hỏi:** có thể đã chạy BEFORE INSERT ROW không? AFTER INSERT ROW có áp dụng cho row bị bỏ qua không?

### Bài 42 — MERGE

Một `MERGE` có hai nhánh INSERT và UPDATE.

**Bài tập:** phân biệt statement-level events được xét và row-level events thực tế, giải thích vì sao không có trigger operation `TG_OP='MERGE'`.

### Bài 43 — FK ON DELETE CASCADE

Parent có child FK `ON DELETE CASCADE`. Bảng child có `AFTER DELETE ROW` audit trigger.

**Câu hỏi:** khi DELETE parent làm child bị xóa, audit trigger trên child có thể chạy không? Có phải transaction khác không?

### Bài 44 — Partition movement

UPDATE một partition key chuyển row từ partition tháng 1 sang tháng 2.

**Bài tập:** nêu vì sao `AFTER UPDATE ROW` có thể không chạy cho row movement, còn `AFTER DELETE ROW` và `AFTER INSERT ROW` trên các partitions có thể chạy.

### Bài 45 — Generated column

`line_total GENERATED ALWAYS AS (quantity * unit_price) STORED`.

**Câu hỏi:** BEFORE trigger có thể thay quantity trước khi generated value được tính không? AFTER trigger thấy line_total nào?

### Bài 46 — Trigger recursion

Một AFTER UPDATE trigger tự chạy `UPDATE orders SET updated_at=... WHERE order_id=NEW.order_id`.

**Bài tập:** vẽ vòng lặp và sửa bằng `BEFORE UPDATE ... NEW.updated_at := clock_timestamp(); RETURN NEW;`.

### Bài 47 — Bulk UPDATE chậm

Một `UPDATE` thay 200.000 rows; AFTER ROW trigger mỗi row gọi thêm ba SQL queries.

**Bài tập:** tính gần đúng số trigger calls, mô tả N+1 overhead và đề xuất set-based transition table nếu business chỉ cần tổng hợp.

### Bài 48 — SECURITY DEFINER

Một audit trigger function cần ghi bảng riêng mà application không có quyền INSERT.

**Câu hỏi:** khi dùng `SECURITY DEFINER`, cần kiểm soát owner, `search_path`, dynamic SQL và quyền EXECUTE như thế nào?

### Bài 49 — EXPLAIN ANALYZE trên DML

Một developer chạy `EXPLAIN (ANALYZE) DELETE FROM orders` trên production vì tưởng nó chỉ in kế hoạch.

**Câu hỏi:** rủi ro là gì? Tại sao bọc transaction rồi rollback trên lab vẫn có chi phí locks/WAL?

### Bài 50 — Capstone: nghiệp vụ bán hàng

Thiết kế schema gồm:

- Bảng `orders` có amount, status, customer_name và updated_at.
- View quản trị có cột calculated display total.
- Bảng audit OLD/NEW cho mọi INSERT/UPDATE/DELETE.
- Báo cáo mỗi statement có bao nhiêu đơn mới và tổng amount.
- Không cho xóa đơn đã paid.
- Cho phép copy import hàng loạt nhưng không âm thầm bỏ input sai.
- Có trạng thái transaction commit/rollback rõ ràng.
- Có cơ chế external notification sau commit qua outbox.

**Yêu cầu nộp:**

1. Chọn `BEFORE`/`AFTER`/`INSTEAD OF` và row/statement level cho từng thao tác.
2. Viết ít nhất ba trigger functions PL/pgSQL và các `CREATE TRIGGER` tương ứng.
3. Giải thích `NEW`/`OLD` và return value trong từng function.
4. Dùng `WHEN`/`IS DISTINCT FROM` cho một field cần audit chỉ khi đổi.
5. Dùng transition relation cho tổng theo statement.
6. Mô tả hợp đồng `RETURNING` của view.
7. Tạo một test `UPDATE ... WHERE FALSE` để chứng minh statement trigger vẫn chạy.
8. Tạo một test `BEGIN; DML; ROLLBACK;` để chứng minh AFTER audit rollback.
9. Kiểm tra UPSERT, DELETE cascade và partition row movement nếu mô hình thực tế có dùng.
10. Chỉ ra ít nhất ba rủi ro hiệu năng, hai rủi ro bảo mật và một phương án rollback migration.

**Tiêu chí tự giải thích:** Người học phải nêu được **khi nào trigger chạy, nó nhìn thấy dữ liệu nào, việc trả NEW/OLD/NULL có ý nghĩa gì, và thao tác của trigger có commit độc lập hay không**. Không chỉ trình bày cú pháp CREATE TRIGGER.

## 39. Checklist thiết kế và triển khai trigger

### 39.1. Ngữ nghĩa

- [ ] Đã xác định event `INSERT`, `UPDATE`, `DELETE` hay `TRUNCATE`.
- [ ] Đã chọn timing `BEFORE`/`AFTER`/`INSTEAD OF` đúng mục đích.
- [ ] Đã chọn level `ROW`/`STATEMENT` đúng granularity.
- [ ] Không tạo row-level TRUNCATE trigger.
- [ ] Không tạo INSTEAD OF trigger trên base table hoặc statement-level trên view.
- [ ] Không truy cập `NEW` với DELETE hoặc `OLD` với INSERT.
- [ ] Row-level BEFORE trả `NEW`/`OLD` đúng event hoặc `NULL` khi cố ý skip.
- [ ] AFTER/statement-level không dùng return value để sửa/bỏ qua DML.
- [ ] INSTEAD OF thực thi SQL base-table thật và trả row thích hợp cho affected rows/RETURNING.
- [ ] Không coi AFTER là “sau COMMIT”.
- [ ] Không coi statement trigger chạy nghĩa có ít nhất một row được thay đổi.

### 39.2. Tính đúng

- [ ] Có constraints cho các bất biến simple, không lạm dụng trigger.
- [ ] Có `CHECK`/`UNIQUE`/`FOREIGN KEY` nơi thích hợp.
- [ ] Đã phân biệt `UPDATE OF` target list với thay đổi giá trị thật.
- [ ] Có `IS DISTINCT FROM` cho so sánh nullable fields.
- [ ] Đã xem thứ tự nhiều triggers cùng loại theo tên.
- [ ] Đã kiểm tra các interactions giữa nhiều BEFORE triggers.
- [ ] Khi có generated column, biết thời điểm tính toán.
- [ ] Khi có deferred constraint trigger, biết WHEN được kiểm tra lúc nào.
- [ ] Không lầm subtransaction/AFTER trigger với transaction độc lập.
- [ ] Có test rollback và exception handling.

### 39.3. View và thao tác phức tạp

- [ ] Đã kiểm tra view có tự updatable không trước khi thêm INSTEAD OF.
- [ ] Có mapping rõ giữa view row và base-table DML.
- [ ] Có test INSERT/UPDATE/DELETE ... RETURNING qua view.
- [ ] Không quên base-table triggers vẫn có thể chạy từ DML trong view trigger.
- [ ] Có test UPSERT và các hành động statement-level liên quan.
- [ ] Có test TRUNCATE không kích hoạt DELETE row triggers.
- [ ] Có test FK cascade với audit ở child.
- [ ] Có test partition row movement nếu dùng partitioning.
- [ ] Có test COPY/bulk import.

### 39.4. Hiệu năng và vận hành

- [ ] Không tạo N+1 queries không cần thiết trong row trigger.
- [ ] Dùng transition tables/set-based logic cho tổng hợp theo statement khi có thể.
- [ ] Không gọi network/external API trong transaction trigger.
- [ ] Có guard tránh trigger recursion hoặc cross-table cycles.
- [ ] Đã đo bằng dữ liệu/row count đại diện và xem EXPLAIN nếu cần.
- [ ] Có quan sát locks/WAL/latency và tốc độ tăng audit table.
- [ ] Có chiến lược retention/partitioning cho audit lớn.
- [ ] Không disable user/system triggers thiếu kiểm soát.
- [ ] Có migration và rollback plan.
- [ ] Không coi sequence gaps là bằng chứng về rollback hoặc thiếu audit.

### 39.5. Bảo mật

- [ ] Dùng schema-qualified names trong trigger function.
- [ ] Nếu dùng SECURITY DEFINER, có search_path an toàn và owner quyền tối thiểu.
- [ ] Không ghép SQL động từ dữ liệu không đáng tin nếu chưa quote/bind đúng.
- [ ] Kiểm soát quyền EXECUTE trên function, quyền trigger/table và quyền đọc audit.
- [ ] Có chính sách masking/retention dữ liệu nhạy cảm trong OLD/NEW snapshots.
- [ ] Đã kiểm tra Row-Level Security/views/roles nếu hệ thống multi-tenant.
- [ ] Không dùng trigger như cơ chế xác thực hoặc phân quyền duy nhất.

## 40. Câu hỏi thường gặp

### 40.1. Có phải BEFORE luôn chạy trước mọi ràng buộc?

`BEFORE ROW` chạy trước khi row change được áp dụng và thường có thể chỉnh `NEW` trước khi các giá trị cuối được kiểm tra/lưu. Nhưng hệ thống constraints có các pha immediate/deferred và trigger nội bộ riêng. Khi cần bảo đảm một invariant đơn giản, dùng constraint thay vì dựa vào thứ tự một chuỗi triggers phức tạp.

### 40.2. Tại sao AFTER không sửa được NEW?

PostgreSQL bỏ qua **return value** của `AFTER ROW` trigger; row đã được thao tác. Muốn chỉnh giá trị của hàng được ghi, `BEFORE ROW` là thời điểm phù hợp. AFTER có thể chạy SQL phụ nhưng làm vậy trên chính bảng dễ gây recursion.

### 40.3. Tại sao DELETE 0 rows vẫn ghi một trace?

Vì statement-level trigger được gọi cho SQL statement, không yêu cầu một row phải khớp. Row-level DELETE triggers không có row nên không chạy.

### 40.4. Lệnh INSTEAD OF có thể gắn vào bảng không?

Không. PostgreSQL định nghĩa `INSTEAD OF` cho **row-level triggers trên view**. Trên bảng dùng BEFORE/AFTER theo sự kiện và level hỗ trợ.

### 40.5. Tôi có thể sửa một view có join bằng INSTEAD OF trigger không?

Có thể, nếu bạn xây được mapping DML rõ ràng xuống base tables. Nhưng phải xử lý row identity, concurrency, permissions, constraints, RETURNING và partial failure; không có phép ánh xạ mặc định đúng cho mọi join.

### 40.6. Khi AFTER trigger ghi audit, transaction rollback thì audit còn không?

Không, nếu audit INSERT thuộc cùng transaction. Muốn ghi lại cả những thao tác bị rollback hoặc thất bại, cần hệ thống logging/audit **ngoài transaction** được thiết kế phù hợp.

### 40.7. Cách biết amount thực sự đổi?

Với UPDATE row-level:

~~~sql
OLD.amount IS DISTINCT FROM NEW.amount
~~~

không chỉ dựa vào `UPDATE OF amount`, vì cột được ghi trong SET list có thể giữ nguyên giá trị.

### 40.8. Có thể dùng RETURN NULL để chặn DELETE không?

Có, từ `BEFORE DELETE ROW`. Nhưng nếu business cần báo lỗi khi cố xóa đơn paid, `RAISE EXCEPTION` thường rõ hơn bỏ qua im lặng.

### 40.9. Tại sao trigger chạy nhiều lần khi INSERT chỉ có một câu lệnh?

Vì row-level trigger chạy theo **số rows**, không theo số statements. Ngoài ra UPSERT, FK cascades, view trigger DML xuống base tables hoặc partitioning có thể làm phát sinh những sự kiện trigger khác.

### 40.10. AFTER STATEMENT có thể truy cập tất cả rows vừa INSERT không?

Có thể dùng **`REFERENCING NEW TABLE AS ...`** khi trigger/event/relation thỏa điều kiện hỗ trợ. Không có transition table thì statement trigger không tự có biến `NEW` là tập rows.

### 40.11. Constraint trigger deferred có thể chạy sau COMMIT không?

Nó có thể được **trì hoãn tới giai đoạn kết thúc transaction**, trước khi transaction được chấp nhận commit thành công. Không nên hiểu như một callback asynchronous bên ngoài transaction sau khi commit đã hoàn tất.

### 40.12. Vì sao trigger ngày càng chậm trên bảng lớn?

Có thể row-level function làm N+1 SQL calls, audit table tăng nhanh, nhiều indexes/WAL, recursion, lock waits, hoặc query phụ thiếu index. Dùng EXPLAIN/metrics và cân nhắc transition tables hoặc refactor logic ngoài trigger.

### 40.13. Trigger có thể gửi email sau khi INSERT không?

Về mặt kỹ thuật có thể có extensions/UDFs gọi external systems, nhưng điều này **không transactionally rollback được external side effects**, và có thể giữ locks trong khi chờ network. Nên dùng outbox + worker độc lập.

### 40.14. Có nên disable triggers trong bulk import để tăng tốc không?

Không nên làm tùy tiện. Việc disable có thể bỏ qua validation/audit, và thay đổi system triggers có thể ảnh hưởng FK integrity. Cân nhắc staging, set-based transformations, batch sizing, index maintenance và migration có kiểm soát.

### 40.15. Trigger và rule cái nào nên dùng để sửa view?

Đầu tiên kiểm tra **automatically updatable view**. Khi cần custom per-row mapping, `INSTEAD OF` trigger thường dễ viết và dễ theo dõi DML thực thi hơn một số dạng query-rewrite rule. Nhưng lựa chọn vẫn phụ thuộc mô hình view, hiệu năng và yêu cầu nghiệp vụ.

## 41. Tài liệu PostgreSQL chính thức

Các liên kết sau trỏ tới tài liệu PostgreSQL hiện hành. Khi áp dụng cho production, hãy mở đúng **major version PostgreSQL** đang vận hành (đặc biệt với partition triggers, MERGE, generated columns và transition relations):

- [CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): cú pháp timing, `FOR EACH ROW/STATEMENT`, `WHEN`, `UPDATE OF`, `REFERENCING` và constraint triggers.
- [Trigger Behavior](https://www.postgresql.org/docs/current/trigger-definition.html): thời điểm/level, thứ tự trigger, row changes và các sự kiện phức tạp.
- [Overview of Trigger Behavior](https://www.postgresql.org/docs/current/triggers.html): tổng quan về trigger hoạt động trong PostgreSQL.
- [PL/pgSQL Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html): `RETURNS trigger`, `NEW`, `OLD`, `TG_OP`, `TG_WHEN`, `TG_LEVEL`, `TG_ARGV` và return values.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): khai báo trigger function và ngữ nghĩa `SECURITY DEFINER`.
- [INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT` và `RETURNING`.
- [UPDATE](https://www.postgresql.org/docs/current/sql-update.html): cập nhật hàng, `RETURNING` và các trường hợp partition row movement.
- [DELETE](https://www.postgresql.org/docs/current/sql-delete.html): DELETE và `RETURNING`.
- [TRUNCATE](https://www.postgresql.org/docs/current/sql-truncate.html): khác biệt với DELETE, triggers và transaction behavior.
- [MERGE](https://www.postgresql.org/docs/current/sql-merge.html): những hành động INSERT/UPDATE/DELETE trong một statement.
- [COPY](https://www.postgresql.org/docs/current/sql-copy.html): tải dữ liệu và các tác động lên triggers.
- [CREATE VIEW](https://www.postgresql.org/docs/current/sql-createview.html): updatable views và view options.
- [Updatable Views](https://www.postgresql.org/docs/current/rules-views.html): cơ chế cập nhật view, rule rewriting và lựa chọn dùng triggers.
- [CREATE RULE](https://www.postgresql.org/docs/current/sql-createrule.html): query rewrite rules, khác triggers.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): thời điểm tính giá trị từ base columns so với BEFORE/AFTER triggers.
- [Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): row movement và những giới hạn trigger trên partitions.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, NOT NULL, UNIQUE, FOREIGN KEY và deferred checks.
- [SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): chuyển immediate/deferred constraint behavior.
- [PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): `RAISE`, SQLSTATE và error handling.
- [PL/pgSQL Error Trapping](https://www.postgresql.org/docs/current/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING): exception blocks/subtransaction semantics.
- [Security-Definer Functions](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY): các lưu ý search_path và quyền.
- [EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): tác động thực thi của `ANALYZE` và thông tin timing.
- [System Catalog pg_trigger](https://www.postgresql.org/docs/current/catalog-pg-trigger.html): metadata, enabled mode và internal triggers.
- [Information Schema triggers](https://www.postgresql.org/docs/current/infoschema-triggers.html): metadata portable của triggers.

## 42. Tổng kết

**BEFORE, AFTER và INSTEAD OF là ba thời điểm thực thi với mục đích khác nhau**, không phải ba cách viết thay thế hoàn toàn:

| Timing | Từ khóa nhớ | Trường hợp tiêu biểu |
| --- | --- | --- |
| **`BEFORE`** | **Trước khi hàng/statement được thực hiện** | Chuẩn hóa `NEW`, kiểm tra, có thể skip row hoặc báo lỗi |
| **`AFTER`** | **Sau row operation/statement** | Audit, xử lý dữ liệu đã thay đổi, transition tables, constraint triggers |
| **`INSTEAD OF`** | **Thay thao tác gửi tới view** | DML vào base tables qua một view có mapping riêng |

Đừng quên chiều thứ hai: **row-level** chạy theo từng hàng, **statement-level** chạy theo statement, **kể cả khi 0 hàng bị ảnh hưởng**. Với `BEFORE ROW`, `RETURN NEW`/`RETURN OLD` có thể quyết định hàng được tiếp tục, còn `RETURN NULL` bỏ qua hàng. Với `AFTER ROW` và statement-level, return value bị bỏ qua. Với `INSTEAD OF ROW`, return value cho PostgreSQL biết row đã được xử lý và có thể dùng cho `RETURNING`/affected-row count.

Khi làm việc với UPDATE, `UPDATE OF col` chỉ nói cột được chỉ định trong SET list, **không chứng minh giá trị thực tế thay đổi**; dùng `OLD.col IS DISTINCT FROM NEW.col` khi cần. Với bulk DML, `AFTER STATEMENT` và `REFERENCING OLD/NEW TABLE` cho phép xử lý tập hàng thay vì chạy aggregate trong mỗi row trigger.

**AFTER không phải sau COMMIT.** Các thay đổi của trigger — kể cả audit INSERT — vẫn thuộc transaction và sẽ rollback khi transaction lỗi/hủy. Riêng constraint triggers có thể được **deferred** tới giai đoạn kết thúc transaction, trong khi TRUNCATE không có row-level triggers, UPSERT/MERGE có thể sinh nhiều loại events, và UPDATE chuyển partition có thể trở thành DELETE+INSERT ở cấp row.

Một thiết kế trigger tốt phải trả lời bốn câu hỏi rõ ràng: **nó chạy khi nào; nó nhìn thấy NEW/OLD hay tập hàng nào; nó có thể chỉnh/bỏ qua gì; và thay đổi đó nằm trong transaction nào?** Sau đó mới xét constraints, hiệu năng N+1, recursion, quyền SECURITY DEFINER, transition tables, transaction rollback và kiểm thử các thao tác đặc biệt. Trigger có thể giúp bảo toàn quy tắc gần dữ liệu, nhưng chỉ an toàn và dễ bảo trì khi timing, level, side effects và quyền sở hữu đều minh bạch.
