# Thứ tự trigger, đệ quy và vòng lặp tác dụng phụ trong PostgreSQL

## 1. Vì sao hiểu thứ tự trigger quan trọng?

Một bảng có thể được gắn nhiều trigger: chuẩn hóa dữ liệu, kiểm tra điều kiện nghiệp vụ, cập nhật bảng tổng hợp, ghi lịch sử thay đổi, phát thông báo, hoặc đồng bộ trạng thái sang bảng khác. Khi một lệnh `INSERT`, `UPDATE`, `DELETE` hay `TRUNCATE` xảy ra, các trigger không chạy tùy ý; PostgreSQL có những quy tắc về **thời điểm**, **mức kích hoạt**, **thứ tự khi cùng loại**, **giá trị OLD/NEW**, và **giao dịch**.

Nếu một trigger lại chạy SQL thay đổi bảng đang có trigger, một chuỗi gọi lồng nhau có thể hình thành:

~~~text
UPDATE orders
    |
    v
AFTER UPDATE trigger orders
    |
    +--> UPDATE accounts
              |
              v
         AFTER UPDATE trigger accounts
              |
              +--> UPDATE orders
                           |
                           v
                    AFTER UPDATE trigger orders
                           ...
~~~

Đây có thể là một chuỗi nghiệp vụ hợp lệ nếu có điểm dừng, nhưng cũng có thể tạo **đệ quy vô hạn, khóa tranh chấp, nhân bản audit log, lỗi stack-depth, hoặc side effects bị thực thi nhiều lần**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **BEFORE**, **AFTER**, **INSTEAD OF**, **row-level** và **statement-level** triggers.
- Xác định thứ tự kích hoạt khi có nhiều trigger cùng loại; hiểu tên trigger ảnh hưởng thứ tự.
- Biết trigger nào được gọi khi một statement **không ảnh hưởng hàng nào**.
- Hiểu cách các trigger **BEFORE ROW** thay đổi `NEW` và ảnh hưởng trigger kế tiếp; phân biệt `RETURN NEW`, `RETURN OLD` và `RETURN NULL`.
- Giải thích trigger gọi SQL bên trong có thể kích hoạt các trigger khác, kể cả trên cùng bảng.
- Dùng `pg_trigger_depth()` để quan sát call depth nhưng **không lạm dụng nó như cơ chế chống đệ quy duy nhất**.
- Thiết kế các biện pháp chống vòng lặp: điều kiện `WHEN`, `IS DISTINCT FROM`, DML có điều kiện, idempotency, khóa/constraint và giới hạn phạm vi.
- Phân biệt side effects **cùng transaction** với tác động bên ngoài **không rollback được**.
- Hiểu ràng buộc bổ sung của **constraint triggers**, `SET CONSTRAINTS`, `ON CONFLICT DO UPDATE`, partitioned tables, cascading actions và transition tables.
- Đọc `pg_trigger`, `pg_get_triggerdef`, `pg_stat_user_functions` và sử dụng SQL lab để quan sát một cách có kiểm soát.
- Hoàn thành các bài tập tình huống với lời giải.

> **Giới hạn an toàn:** tạo và chạy mọi ví dụ trong database thực hành được phép. Đừng tạo trigger có đệ quy không có điểm dừng trên production chỉ để quan sát lỗi. Các đoạn `DROP`, `ALTER TABLE DISABLE TRIGGER`, gọi HTTP hoặc gửi sự kiện ngoài transaction cần được đánh giá riêng trước khi chạy trong hệ thống thật.

---

## 2. Trigger là gì và có những loại nào?

Trigger là một đối tượng gắn với **bảng**, **view** hoặc trong một số trường hợp **foreign table**, được PostgreSQL tự kích hoạt bởi sự kiện SQL phù hợp. Trigger tham chiếu một function/procedure trigger với cú pháp tương ứng; trong PL/pgSQL, trigger function thường khai báo `RETURNS trigger`.

### 2.1. Ba thời điểm phổ biến

| Thời điểm | Mục đích chính | Đặc điểm đáng nhớ |
|---|---|---|
| **BEFORE** | Chỉnh sửa/kiểm tra hàng trước thao tác | Với row-level trigger, có thể sửa `NEW` hoặc `RETURN NULL` để bỏ hàng |
| **AFTER** | Ghi audit, cập nhật phụ thuộc sau khi thay đổi thành công trong statement | Row đã được xử lý; giá trị trả về trigger function không quyết định hàng được chấp nhận |
| **INSTEAD OF** | Xử lý INSERT/UPDATE/DELETE trên **view** | Thay thao tác trên view bằng logic do trigger function quyết định; dùng ở row-level view |

`AFTER` không đồng nghĩa “sau COMMIT”. Một trigger AFTER thông thường vẫn hoạt động **trong transaction của statement**, trước COMMIT.

### 2.2. Hai mức kích hoạt

- **FOR EACH ROW**: kích hoạt cho từng hàng chịu tác động (với các điều kiện hỗ trợ của event/timing).
- **FOR EACH STATEMENT**: kích hoạt một lần mỗi statement kích hoạt, kể cả statement tác động **0 hàng** trong nhiều trường hợp, nếu trigger đó phù hợp với statement.

### 2.3. Sự kiện

| Event | BEFORE | AFTER | INSTEAD OF |
|---|---|---|---|
| `INSERT` | Bảng, row/statement | Bảng, row/statement | View, row |
| `UPDATE` | Bảng, row/statement | Bảng, row/statement | View, row |
| `DELETE` | Bảng, row/statement | Bảng, row/statement | View, row |
| `TRUNCATE` | Bảng, **statement** | Bảng, **statement** | Không dùng |

Không viết `FOR EACH ROW TRUNCATE` như một trigger hợp lệ. `TRUNCATE` không gọi row-level DELETE triggers.

### 2.4. Mô hình thời gian đơn giản

~~~text
Một UPDATE đơn giản nhắm tới bảng gốc

BEFORE STATEMENT triggers
          |
          v
Cho từng hàng bị UPDATE:
    BEFORE ROW triggers
         |
         +--> có thể sửa NEW hoặc RETURN NULL
         |
         v
    UPDATE hàng nếu không bị bỏ
         |
         v
    AFTER ROW triggers (được kích hoạt theo cơ chế AFTER)
          |
          v
AFTER STATEMENT triggers
          |
          v
Kết thúc statement
          |
          v
COMMIT/ROLLBACK của transaction do caller quyết định
~~~

Đây là sơ đồ khái niệm. Với nhiều rows, hàng bị sửa có thể có thứ tự xử lý phụ thuộc kế hoạch; AFTER ROW triggers được xếp hàng và chạy tại giai đoạn phù hợp, không được dùng để bảo đảm “row A luôn chạy trước row B”. Với **deferred constraint trigger**, thời điểm thực tế còn có thể muộn hơn, tới cuối transaction.

---

## 3. Quy tắc thứ tự quan trọng nhất: trigger cùng loại chạy theo tên

Nếu nhiều triggers có **cùng event, cùng timing và cùng relation** phù hợp với statement, PostgreSQL chạy chúng **theo thứ tự bảng chữ cái của tên trigger** (name ordering), không phải theo thứ tự bạn chạy `CREATE TRIGGER`.

Ví dụ:

~~~sql
CREATE TRIGGER b_10_normalize
BEFORE INSERT ON demo.items
FOR EACH ROW EXECUTE FUNCTION demo.normalize_item();

CREATE TRIGGER b_20_validate
BEFORE INSERT ON demo.items
FOR EACH ROW EXECUTE FUNCTION demo.validate_item();
~~~

Ở một thao tác INSERT có đủ điều kiện, `b_10_normalize` sẽ được gọi trước `b_20_validate`. Đổi thứ tự tạo trigger **không** đổi thứ tự gọi này.

### 3.1. Tên trigger là một phần của thiết kế hành vi

Các tên có prefix dễ đọc:

- `b_10_normalize`: chuẩn hóa input.
- `b_20_validate`: kiểm tra sau chuẩn hóa.
- `a_10_audit`: lưu audit.
- `a_20_derived_data`: cập nhật dữ liệu phụ.

Prefix thể hiện ý định nhưng không biến trigger system thành workflow engine. Các trigger cùng loại vẫn phải được thiết kế để xử lý đúng **trạng thái dữ liệu và giao dịch**.

### 3.2. Thứ tự chỉ có nghĩa khi các trigger cùng được gọi

Không suy rằng mọi trigger trên bảng đều chạy theo một danh sách tên chung. Trước tiên PostgreSQL phân loại theo **timing, event, row/statement, eligibility**; tên được dùng để sắp xếp các trigger cùng nhóm kích hoạt.

Một `BEFORE ROW` không thể chạy sau `AFTER STATEMENT` chỉ vì tên có chữ `z_`.

### 3.3. Cần phân biệt thứ tự trigger với thứ tự hàng

~~~sql
UPDATE demo.items
SET quantity = quantity + 1
WHERE quantity >= 0;
~~~

Với nhiều hàng, SQL **không bảo đảm** hàng có `item_id` nhỏ hơn được xử lý trước. Nếu audit table có sequence ID tăng dần, thứ tự sequence quan sát được có thể phụ thuộc execution plan, trigger scheduling và concurrency; đừng coi đây là thứ tự nghiệp vụ bền vững.

### 3.4. Không dùng đổi tên làm “migration vô hại”

Đổi tên một trigger có thể thay đổi thứ tự nó chạy tương đối với trigger cùng nhóm. Khi một trigger phải nhận `NEW` đã chuẩn hóa từ trigger khác, đổi tên thiếu kiểm soát có thể làm business logic hỏng.

### 3.5. Khi thứ tự phụ thuộc quá chặt, cân nhắc một trigger điều phối

Nếu logic cần đúng thứ tự `normalize → validate → derive fields`, có thể dùng **một BEFORE trigger function** thực thi các bước đó có chủ đích. Cách này thường rõ hơn so với mạng nhiều trigger có thứ tự tên phụ thuộc dài hạn.

---

## 4. OLD, NEW, TG_OP và giá trị trả về

### 4.1. Các biến đặc biệt trong trigger function

| Biến | Ý nghĩa |
|---|---|
| `NEW` | Row mới trong INSERT/UPDATE row trigger, ở những trường hợp phù hợp |
| `OLD` | Row cũ trong UPDATE/DELETE row trigger |
| `TG_OP` | Chuỗi sự kiện `INSERT`, `UPDATE`, `DELETE` hoặc `TRUNCATE` |
| `TG_WHEN` | `BEFORE`, `AFTER`, `INSTEAD OF` |
| `TG_LEVEL` | `ROW` hoặc `STATEMENT` |
| `TG_TABLE_SCHEMA` | Tên schema của relation kích hoạt |
| `TG_TABLE_NAME` | Tên relation kích hoạt |
| `TG_NAME` | Tên trigger đang chạy |
| `TG_ARGV` / `TG_NARGS` | Tham số chuỗi được khai báo cho trigger |

Không truy cập `NEW.col` khi trigger không có `NEW` thích hợp, hoặc `OLD.col` khi trigger chỉ INSERT. Statement-level trigger không có một row OLD/NEW cụ thể để sửa.

### 4.2. BEFORE ROW INSERT/UPDATE: trả NEW để tiếp tục

~~~sql
CREATE FUNCTION demo.normalize_item()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.code := upper(btrim(NEW.code));
    RETURN NEW;
END;
$$;
~~~

Nếu trigger trả `NEW`, PostgreSQL tiếp tục xử lý row được sửa; trigger BEFORE tiếp theo có thể nhìn thấy `NEW.code` đã chuẩn hóa.

### 4.3. BEFORE ROW: RETURN NULL để bỏ thao tác trên hàng đó

~~~sql
IF NEW.quantity < 0 THEN
    RETURN NULL;
END IF;
~~~

`RETURN NULL` trong BEFORE ROW có tác dụng **bỏ thao tác đối với row hiện tại**, và các row-level triggers kế tiếp cho row đó không tiếp tục được kích hoạt theo cách thông thường. Nó **không tự báo exception**; statement có thể kết thúc thành công nhưng tác động ít hàng hơn dự kiến.

Đừng dùng RETURN NULL để lặng lẽ bỏ các hàng vi phạm nguyên tắc dữ liệu nghiêm trọng nếu nghiệp vụ yêu cầu lỗi rõ. Nên cân nhắc `RAISE EXCEPTION` hoặc constraint.

### 4.4. BEFORE DELETE: thường trả OLD

~~~sql
CREATE FUNCTION demo.guard_delete()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.is_protected THEN
        RETURN NULL;
    END IF;
    RETURN OLD;
END;
$$;
~~~

Với DELETE, `OLD` là row trước khi xóa; `NEW` không phù hợp. Giá trị row trả về của BEFORE DELETE chỉ cần non-NULL để cho phép thao tác, thường dùng `RETURN OLD`.

### 4.5. AFTER ROW: return value bị bỏ qua

~~~sql
CREATE FUNCTION demo.audit_after()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO demo.audit_log(...) VALUES (...);
    RETURN NULL;
END;
$$;
~~~

Trên AFTER trigger, giá trị return **không sửa row đã ghi**; quy ước thường `RETURN NULL`. Không cố `NEW.amount := ...; RETURN NEW;` trong AFTER rồi mong bảng gốc tự thay đổi.

### 4.6. INSTEAD OF ROW trigger trên view

INSTEAD OF trigger thay thế thao tác trên view. Trả non-NULL thường báo đã xử lý một row, ảnh hưởng row count của lệnh thông qua view, và trả NULL có thể cho biết row không được xử lý. Code phải thực hiện DML nền phù hợp và trả row đúng theo yêu cầu của thao tác/`RETURNING`; không áp dụng máy móc quy tắc BEFORE/AFTER bảng thường.

---

## 5. Trước khi viết trigger, xác định side effect có transaction hay không

Một side effect có thể là:

- **SQL trong cùng transaction:** ghi audit row, thay đổi bảng tổng hợp, sửa row phụ thuộc.
- **Thao tác ở DB khác hoặc hệ thống ngoài:** HTTP request, message broker, gửi email, API thanh toán.
- **Hoạt động đặc biệt trong PostgreSQL:** `nextval()`, `pg_notify()`, advisory locks, extension functions.

Không phải mọi side effect đều có rollback semantics giống nhau:

| Side effect | Rollback transaction có đảo được không? | Điều cần lưu ý |
|---|---|---|
| INSERT vào audit table cùng transaction | **Có**, nếu transaction rollback | Audit bị mất cùng transaction lỗi |
| UPDATE bảng tổng hợp cùng transaction | **Có** | Có thể gây trigger khác và vòng lặp |
| DELETE row cùng transaction | **Có** | Trigger cascade, FK checks vẫn có thể chạy |
| `nextval()` của sequence | **Không** hồi lại giá trị sequence đã cấp | Sequence IDs có gaps sau rollback |
| `pg_notify()` gọi trong transaction | Notification được gửi sau COMMIT; rollback không phát | Payload/notification không phải durable queue |
| Gửi HTTP/email từ trigger extension/function | Thường **không tự rollback** ở hệ thống ngoài | Retry/rollback có thể gây gửi trùng |
| Ghi file/log ngoài DB | Không bảo đảm rollback được | Không dùng như side effect exactly once |
| Insert vào outbox table cùng transaction | Outbox row rollback được | Worker gửi sự kiện sau commit, cần idempotency |

**Quy tắc:** trigger AFTER chạy trong transaction, không phải “sau commit”. Nếu cần gửi tác vụ ngoài DB sau commit, cân nhắc **transactional outbox + worker** thay vì trực tiếp gọi mạng trong trigger.

---

## 6. SQL lab độc lập

Phần lab dùng schema `trigger_order_lab`. Chỉ tạo trên database thử nghiệm do bạn kiểm soát.

### 6.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA IF NOT EXISTS trigger_order_lab;

CREATE TABLE trigger_order_lab.items (
    item_id bigint PRIMARY KEY,
    code text NOT NULL,
    quantity integer NOT NULL,
    note text NOT NULL DEFAULT '',
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_items_qty_nonnegative CHECK (quantity >= 0)
);

CREATE TABLE trigger_order_lab.fire_log (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trigger_name text NOT NULL,
    timing text NOT NULL,
    operation text NOT NULL,
    item_id bigint,
    observed_code text,
    observed_quantity integer,
    logged_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

`fire_log` là bảng ghi sự kiện **cùng transaction** và dùng identity cho việc quan sát. Gaps trong `log_id` không chứng minh audit row đã commit hay không; identity/sequence có tính chất không rollback giá trị đã cấp.

### 6.2. Trigger function số 1: chuẩn hóa BEFORE ROW

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_normalize_item()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.code := upper(btrim(NEW.code));
    NEW.updated_at := clock_timestamp();

    INSERT INTO trigger_order_lab.fire_log
        (trigger_name, timing, operation, item_id,
         observed_code, observed_quantity)
    VALUES
        (TG_NAME, TG_WHEN, TG_OP, NEW.item_id,
         NEW.code, NEW.quantity);

    RETURN NEW;
END;
$$;
~~~

Hàm chuẩn hóa cả khi INSERT và UPDATE. Nó **không** UPDATE lại `items` bằng câu SQL mới, mà sửa trực tiếp `NEW`, giúp tránh một dạng recursion phổ biến.

### 6.3. Trigger function số 2: kiểm tra BEFORE ROW

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_validate_item()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.code = '' THEN
        RAISE EXCEPTION 'code phải khác rỗng'
            USING ERRCODE = '23514';
    END IF;

    IF NEW.quantity < 0 THEN
        RAISE EXCEPTION 'quantity không được âm'
            USING ERRCODE = '23514';
    END IF;

    INSERT INTO trigger_order_lab.fire_log
        (trigger_name, timing, operation, item_id,
         observed_code, observed_quantity)
    VALUES
        (TG_NAME, TG_WHEN, TG_OP, NEW.item_id,
         NEW.code, NEW.quantity);

    RETURN NEW;
END;
$$;
~~~

Constraint CHECK trên bảng vẫn là lớp đảm bảo dữ liệu; trigger giúp minh họa thứ tự và thông báo. Trong hệ thống thật, tránh lặp cùng một validation ở nhiều nơi nếu không có lý do.

### 6.4. Trigger function số 3: audit AFTER ROW

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_audit_after()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_order_lab.fire_log
        (trigger_name, timing, operation, item_id,
         observed_code, observed_quantity)
    VALUES
        (TG_NAME, TG_WHEN, TG_OP, NEW.item_id,
         NEW.code, NEW.quantity);

    RETURN NULL; -- Return value của AFTER ROW bị bỏ qua.
END;
$$;
~~~

### 6.5. Tạo triggers theo tên có chủ đích

~~~sql
CREATE TRIGGER b_10_normalize
BEFORE INSERT OR UPDATE ON trigger_order_lab.items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_normalize_item();

CREATE TRIGGER b_20_validate
BEFORE INSERT OR UPDATE ON trigger_order_lab.items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_validate_item();

CREATE TRIGGER a_10_audit
AFTER INSERT OR UPDATE ON trigger_order_lab.items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_audit_after();
~~~

### 6.6. Thử INSERT và quan sát

~~~sql
INSERT INTO trigger_order_lab.items
    (item_id, code, quantity, note)
VALUES
    (101, ' alpha ', 3, 'first');

SELECT item_id, code, quantity, note
FROM trigger_order_lab.items
WHERE item_id=101;

SELECT log_id,trigger_name,timing,operation,
       item_id,observed_code
FROM trigger_order_lab.fire_log
WHERE item_id=101
ORDER BY log_id;
~~~

Kỳ vọng item code trở thành `ALPHA` và log theo một INSERT đơn hàng gồm:

1. `b_10_normalize` (BEFORE, quan sát `ALPHA`).
2. `b_20_validate` (BEFORE, quan sát `ALPHA`).
3. `a_10_audit` (AFTER, quan sát `ALPHA`).

Trong ví dụ này, log IDs tăng theo thứ tự gọi trong một session không cạnh tranh; đừng ngoại suy thành một thứ tự audit toàn cục giữa các transactions.

### 6.7. Thử UPDATE

~~~sql
UPDATE trigger_order_lab.items
SET code=' beta ', quantity=5
WHERE item_id=101;

SELECT item_id,code,quantity
FROM trigger_order_lab.items
WHERE item_id=101;

SELECT log_id,trigger_name,operation,observed_code
FROM trigger_order_lab.fire_log
WHERE item_id=101
ORDER BY log_id;
~~~

Update cũng đi qua cả hai BEFORE triggers và một AFTER trigger; code được chuẩn hóa thành `BETA`.

### 6.8. Khi BEFORE validation báo lỗi

~~~sql
-- Chạy riêng để quan sát exception, không gộp vào migration.
UPDATE trigger_order_lab.items
SET code='   '
WHERE item_id=101;
~~~

`b_10_normalize` biến code thành chuỗi rỗng, `b_20_validate` báo exception. Statement lỗi bị rollback, kể cả INSERT vào `fire_log` mà `b_10_normalize` đã làm trong cùng transaction. Nếu statement chạy trong transaction có nhiều việc khác, hành vi cuối cùng phụ thuộc transaction và cách caller bắt exception.

---

## 7. Một trigger có thể quan sát kết quả của trigger trước đó

Hai BEFORE ROW triggers trên cùng row nhận/biến đổi giá trị `NEW` tuần tự.

~~~text
Input: code = " alpha "
       |
       v
b_10_normalize
  NEW.code = "ALPHA"
  RETURN NEW
       |
       v
b_20_validate
  kiểm tra NEW.code = "ALPHA"
  RETURN NEW
       |
       v
Row được INSERT/UPDATE với code="ALPHA"
       |
       v
a_10_audit
  ghi audit của row đã qua các BEFORE triggers
~~~

Nếu đổi tên `b_20_validate` thành `b_05_validate`, validator có thể chạy **trước** normalizer. Điều này làm thay đổi dữ liệu mà validator thấy. Vì vậy:

- Xác định thứ tự có thực sự là dependency không.
- Nếu có, ghi nó trong contract/migration.
- Xem xét một trigger tổng hợp cho pipeline thao tác đơn hàng.
- Dựa vào constraint để đảm bảo invariant cuối cùng.
- Kiểm tra kết quả bằng test, không chỉ bằng việc nhìn tên function.

### 7.1. Cột đã được sửa bởi BEFORE trigger

Nếu BEFORE trigger A gán `NEW.code`, BEFORE trigger B thấy giá trị đã sửa. Một BEFORE trigger tiếp theo cũng có thể gán lại và ghi đè. **Hàng cuối cùng** chỉ được quyết định sau khi các BEFORE triggers cần thiết hoàn thành và không trigger nào return NULL/raise exception.

### 7.2. WHEN của BEFORE ROW nhìn thấy trạng thái lúc trigger được xét

Ví dụ:

~~~sql
CREATE TRIGGER b_30_log_nonempty
BEFORE UPDATE ON trigger_order_lab.items
FOR EACH ROW
WHEN (NEW.code <> '')
EXECUTE FUNCTION trigger_order_lab.fn_validate_item();
~~~

`WHEN` trên BEFORE ROW được xét ngay trước khi function trigger tương ứng thực thi, có thể nhìn thấy `NEW` đã được BEFORE triggers sớm hơn chỉnh sửa. **Mẫu trên chỉ minh họa; không tạo duplicate validation triggers không cần thiết nếu lab đã có `b_20_validate`.**

### 7.3. AFTER ROW không sửa được row bằng return value

Nếu muốn thay đổi giá trị cột của cùng row, hãy làm ở BEFORE trigger bằng `NEW` khi phù hợp. AFTER trigger cần viết `UPDATE items ...` để sửa thật, nhưng chính UPDATE ấy lại có thể kích hoạt triggers mới và gây đệ quy. Đây là lý do thiết kế BEFORE và AFTER khác nhau rất quan trọng.

---

## 8. Statement-level trigger: chạy kể cả khi không có row

### 8.1. Hàm ghi dấu mỗi statement

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_trace_statement()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_order_lab.fire_log
        (trigger_name,timing,operation,item_id,
         observed_code,observed_quantity)
    VALUES
        (TG_NAME,TG_WHEN,TG_OP,NULL,NULL,NULL);

    RETURN NULL;
END;
$$;
~~~

### 8.2. Gắn hai statement triggers

~~~sql
CREATE TRIGGER s_10_before_update
BEFORE UPDATE ON trigger_order_lab.items
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_trace_statement();

CREATE TRIGGER s_90_after_update
AFTER UPDATE ON trigger_order_lab.items
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_trace_statement();
~~~

### 8.3. UPDATE ảnh hưởng 0 row vẫn kích hoạt statement triggers

~~~sql
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id=-999;

SELECT log_id,trigger_name,timing,operation
FROM trigger_order_lab.fire_log
WHERE item_id IS NULL
ORDER BY log_id;
~~~

Khi UPDATE statement được thực thi dù không khớp row nào, `s_10_before_update` và `s_90_after_update` vẫn được kích hoạt theo semantics statement-level.

Nhưng **row-level** update triggers không chạy vì không có row bị cập nhật.

### 8.4. Đọc affected-row count từ ứng dụng vẫn là 0

Statement-level trigger có thể INSERT một row audit hoặc log cho statement không tác động row nào. Điều này **không** làm row count của UPDATE bên ngoài thành 1; DML trong trigger là side effect khác.

### 8.5. Không dùng statement-level trigger để sửa NEW một hàng cụ thể

Vì một statement có thể ảnh hưởng 0, 1 hoặc nhiều rows, statement-level trigger không có một `NEW` record đại diện cho một row. Muốn logic theo từng row, dùng row-level trigger hoặc transition tables đúng loại.

---

## 9. Trigger khi có nhiều rows: tránh giả định order

### 9.1. Một statement tác động nhiều rows

~~~sql
INSERT INTO trigger_order_lab.items
    (item_id,code,quantity,note)
VALUES
    (102,' gamma ',5,'second'),
    (103,' delta ',7,'third'),
    (104,' epsilon ',2,'fourth');
~~~

Mỗi row sẽ đi qua row-level triggers phù hợp. Tuy nhiên **không thiết kế quy tắc nghiệp vụ dựa vào thứ tự** mà PostgreSQL xử lý các rows trong một INSERT ... SELECT hoặc UPDATE ... WHERE nhiều rows.

### 9.2. Sau một UPDATE nhiều rows

~~~sql
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id IN (101,102,103,104);
~~~

Với statement-level triggers UPDATE, ta có:

- BEFORE STATEMENT: một lần.
- BEFORE ROW: cho từng row tác động.
- AFTER ROW: cho từng row được xử lý.
- AFTER STATEMENT: một lần.

**Thứ tự chi tiết giữa các rows không được bảo đảm**. Trigger cùng event/timing trên **một row** vẫn áp dụng name ordering. Không dùng `ORDER BY` trong một subquery để ép thứ tự side effects trigger.

### 9.3. Audit cần thứ tự thời gian?

Nếu cần reconstruct history, ghi **transaction ID, business version, created_at, identity event ID** và thiết kế conflict resolution phù hợp. Sequence/identity cung cấp số tăng theo lần cấp nhưng không chứng minh commit order; timestamp cũng có thể trùng hoặc khác commit order.

### 9.4. Không tính tổng trong từng row trigger nếu statement có thể xử lý nhiều hàng

Một row trigger cập nhật bảng tổng hợp cho mỗi item có thể rất tốn và làm tăng locking. Với batch lớn, cân nhắc **AFTER STATEMENT trigger + transition tables** để tính delta theo tập rows, khi phù hợp PostgreSQL version và loại bảng.

---

## 10. Trigger gọi trigger: đệ quy được hình thành như thế nào?

Một trigger function có thể chạy SQL. SQL đó có thể kích hoạt thêm trigger, dù SQL tác động cùng bảng hay bảng khác.

~~~text
Ứng dụng: UPDATE A
      |
      v
AFTER UPDATE A: trigger ta
      |
      +--> UPDATE B
                |
                v
          AFTER UPDATE B: trigger tb
                |
                +--> UPDATE A
                         |
                         v
                    AFTER UPDATE A: trigger ta
                         ...
~~~

### 10.1. Đệ quy trực tiếp

Một trigger `AFTER UPDATE ON items` thực hiện:

~~~sql
UPDATE trigger_order_lab.items
SET updated_at=clock_timestamp()
WHERE item_id=NEW.item_id;
~~~

Nếu mỗi UPDATE lại kích hoạt trigger đó và trigger không có điều kiện dừng, chain có thể tự gọi mãi. PostgreSQL không mặc định suy luận “đây là update của trigger, hãy bỏ qua trigger” cho bạn.

### 10.2. Đệ quy gián tiếp

Trigger A cập nhật B, trigger B cập nhật C, trigger C lại cập nhật A. Các vòng lặp gián tiếp khó phát hiện hơn vì không có function đơn lẻ tự gọi nó.

### 10.3. Đệ quy hợp lệ

Đệ quy không nhất thiết là lỗi. Ví dụ lan truyền trạng thái lên cây cha–con, sửa dữ liệu phụ thuộc theo nhiều tầng, hoặc xử lý điều kiện đạt điểm cố định. Nhưng cần **chứng minh thuật toán dừng**, tránh lặp bản ghi và đảm bảo complexity không vượt giới hạn production.

### 10.4. Điều gì xảy ra nếu không dừng?

- CPU, I/O và WAL tăng cao.
- Giao dịch giữ row locks lâu, chặn truy vấn khác.
- Có thể gặp lỗi stack depth / quá nhiều tầng lời gọi.
- Một số lỗi có thể dẫn tới rollback toàn statement/transaction.
- Nếu có side effects không rollback được, hệ thống ngoài vẫn có thể đã nhận nhiều yêu cầu.
- Dù bị chặn bởi `statement_timeout`, điều đó không phải là một thiết kế đúng.

Không xem thông số `max_stack_depth` hoặc `statement_timeout` là biện pháp ngăn recursion thay cho logic có điểm dừng.

---

## 11. Phản ví dụ: AFTER UPDATE chỉ sửa updated_at

### 11.1. Mẫu nguy hiểm

~~~sql
-- MINH HỌA SAI, KHÔNG TẠO TRIGGER NÀY.
CREATE FUNCTION bad_fn_touch()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE some_schema.items
       SET updated_at=clock_timestamp()
     WHERE item_id=NEW.item_id;

    RETURN NULL;
END;
$$;

-- Nếu gắn AFTER UPDATE trên chính items không có guard,
-- UPDATE bên trong có thể lại kích hoạt cùng trigger.
~~~

### 11.2. Cách đúng cho timestamp thuộc cùng row: BEFORE UPDATE

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_touch_new()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
~~~

Thay đổi `NEW` trong BEFORE ROW không tạo một lệnh UPDATE thứ hai lên cùng bảng. Trong lab đã có `fn_normalize_item` cập nhật `NEW.updated_at`, vì vậy **không gắn thêm touch trigger trùng công dụng** nếu không muốn nhiều trigger ghi đè cùng một cột.

### 11.3. updated_at chỉ đổi khi dữ liệu nghiệp vụ thay đổi

Nếu muốn tránh đánh dấu thời gian khi `UPDATE SET quantity=quantity` không đổi giá trị:

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_touch_if_changed()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.code IS DISTINCT FROM NEW.code
       OR OLD.quantity IS DISTINCT FROM NEW.quantity
       OR OLD.note IS DISTINCT FROM NEW.note THEN
        NEW.updated_at := clock_timestamp();
    END IF;

    RETURN NEW;
END;
$$;
~~~

Dùng `IS DISTINCT FROM` để so sánh **an toàn khi có NULL**. Không chỉ viết `OLD.col <> NEW.col` nếu cột nullable: `NULL <> 'x'` cho UNKNOWN, khiến IF có thể không chạy.

### 11.4. WHEN có thể tránh gọi function không cần thiết

~~~sql
CREATE TRIGGER b_30_touch_if_changed
BEFORE UPDATE ON trigger_order_lab.items
FOR EACH ROW
WHEN (
    OLD.code IS DISTINCT FROM NEW.code
    OR OLD.quantity IS DISTINCT FROM NEW.quantity
    OR OLD.note IS DISTINCT FROM NEW.note
)
EXECUTE FUNCTION trigger_order_lab.fn_touch_new();
~~~

Đây là **phương án độc lập** cần chọn thay thiết kế timestamp đang có, không phải lệnh khuyến nghị chạy thêm sau lab vì `b_10_normalize` đã gán updated_at. Với nhiều BEFORE triggers, lưu ý `WHEN` kiểm tra trạng thái NEW tại lúc trigger đó được xét và có thể chịu ảnh hưởng của trigger trước.

---

## 12. Một ví dụ đệ quy có điểm dừng trên bảng lab riêng

Ví dụ sau dùng bảng riêng để quan sát độ sâu mà **không tạo vòng lặp vô hạn**.

### 12.1. Tạo bảng

~~~sql
CREATE TABLE trigger_order_lab.chain_counter (
    id integer PRIMARY KEY,
    val integer NOT NULL CHECK (val BETWEEN 0 AND 3)
);

CREATE TABLE trigger_order_lab.depth_log (
    log_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id integer NOT NULL,
    depth integer NOT NULL,
    old_val integer,
    new_val integer
);

INSERT INTO trigger_order_lab.chain_counter(id,val) VALUES (1,0);
~~~

### 12.2. Hàm AFTER UPDATE với điểm dừng

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_increment_to_three()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO trigger_order_lab.depth_log
        (id,depth,old_val,new_val)
    VALUES
        (NEW.id, pg_trigger_depth(), OLD.val, NEW.val);

    IF NEW.val < 3 THEN
        UPDATE trigger_order_lab.chain_counter
           SET val = val+1
         WHERE id=NEW.id
           AND val=NEW.val
           AND val<3;
    END IF;

    RETURN NULL;
END;
$$;
~~~

### 12.3. Gắn trigger

~~~sql
CREATE TRIGGER a_10_increment_to_three
AFTER UPDATE ON trigger_order_lab.chain_counter
FOR EACH ROW
WHEN (OLD.val IS DISTINCT FROM NEW.val)
EXECUTE FUNCTION trigger_order_lab.fn_increment_to_three();
~~~

### 12.4. Chạy trong transaction và ROLLBACK

~~~sql
BEGIN;

UPDATE trigger_order_lab.chain_counter
SET val=1
WHERE id=1 AND val=0;

SELECT id,val FROM trigger_order_lab.chain_counter;

SELECT log_id,id,depth,old_val,new_val
FROM trigger_order_lab.depth_log
ORDER BY log_id;

ROLLBACK;
~~~

Ở tình huống bình thường trong lab mới, update ban đầu từ 0→1 kích hoạt trigger mức 1, trigger chạy UPDATE lên 2 tạo trigger mức 2, rồi lên 3 tạo trigger mức 3. Khi `NEW.val=3`, điều kiện `NEW.val<3` sai nên không có UPDATE tiếp; điểm dừng rõ ràng.

Kỳ vọng giá trị cuối bên trong transaction là **3** và các rows depth_log có depth khoảng **1, 2, 3**, theo đường gọi lồng nhau. Giá trị thực tế phải được quan sát theo query/call stack cụ thể; các triggers khác nếu được thêm vào bảng cũng có thể tác động depth.

### 12.5. Vì sao vẫn không nên áp dụng pattern này vô tội vạ?

- Một UPDATE ban đầu khiến cùng row bị UPDATE nhiều lần.
- Có nhiều row versions, WAL, locks, indexes và trigger calls.
- `UPDATE ... RETURNING` của câu bên ngoài không nhất thiết đại diện cho trạng thái cuối sau các nested updates.
- Nếu nhiều writers đồng thời thay đổi, cần kiểm soát concurrency.
- Ở bài toán đơn giản, một UPDATE trực tiếp `SET val=3` có thể rõ và rẻ hơn.

Mục đích lab là **quan sát recursion có điểm dừng**, không khuyến khích “cứ dùng trigger để lặp đến khi đúng”.

---

## 13. pg_trigger_depth(): đo độ sâu lời gọi trigger

### 13.1. Cú pháp

~~~sql
SELECT pg_trigger_depth();
~~~

Ở ngoài ngữ cảnh trigger, giá trị thường là **0**. Bên trong trigger đầu tiên của một statement, nó thường là **1**; trigger được gọi do SQL bên trong trigger đầu tiên có thể nhìn thấy mức **2**, tiếp tục tăng theo tầng.

### 13.2. Dùng để debug

~~~sql
RAISE NOTICE 'Trigger %, operation %, depth %',
    TG_NAME,TG_OP,pg_trigger_depth();
~~~

Hoặc ghi cột `depth` trong một bảng log transaction giống `trigger_order_lab.depth_log`.

### 13.3. Mẫu guard hay gặp

~~~sql
IF pg_trigger_depth() > 1 THEN
    RETURN NEW;
END IF;
~~~

Mẫu này **có thể hữu ích trong một context rất đặc biệt** nhưng không phải giải pháp chống recursion đáng tin cậy cho mọi hệ thống.

### 13.4. Vì sao guard theo depth không đủ?

Giả sử:

~~~text
UPDATE orders
  -> trigger orders
      -> UPDATE inventory
          -> trigger inventory
~~~

Trigger inventory chạy ở depth 2, nhưng đây có thể là một nghiệp vụ **hợp lệ** cần thực thi. Guard `pg_trigger_depth()>1` sẽ chặn luôn đường cập nhật hợp lệ.

Ngược lại, recursion có thể xảy ra trong nhiều statement/transaction ngoài một call stack, ví dụ worker đọc outbox rồi update bảng gây event mới. `pg_trigger_depth()` chỉ phản ánh **stack trigger hiện tại**, không phải idempotency key xuyên hệ thống.

### 13.5. Không thay việc chứng minh điểm dừng

Dùng `pg_trigger_depth()` chủ yếu cho:

- Debugging nested DML.
- Giới hạn phòng vệ trong một tác vụ đã có contract rõ.
- Logging call paths.

Thiết kế đúng vẫn cần **điều kiện dữ liệu**, **guard predicate**, **idempotency** và **constraint**.

---

## 14. Cách chặn vòng lặp bằng điều kiện thay đổi thực sự

### 14.1. So sánh OLD và NEW

~~~sql
IF OLD.status IS NOT DISTINCT FROM NEW.status THEN
    RETURN NEW;
END IF;
~~~

Đoạn này bỏ công việc phụ khi trạng thái không đổi, nhưng **không hủy UPDATE** của caller. Trong BEFORE trigger nó có nghĩa “không cần sửa thêm, cho phép row update tiếp”.

### 14.2. WHEN ở trigger

~~~sql
CREATE TRIGGER a_20_status_changed
AFTER UPDATE ON some_schema.orders
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION some_schema.fn_after_status_changed();
~~~

Mẫu áp dụng trong schema đã có bảng/function tương ứng; không chạy nguyên trên lab nếu các object chưa tồn tại.

Với AFTER ROW, WHEN có thể tránh **xếp hàng** event cho function khi điều kiện sai, nên thường hiệu quả hơn gọi function cho mọi row rồi IF bỏ qua.

### 14.3. DML có WHERE chặn tự lặp

Trong một AFTER trigger cập nhật bảng phụ:

~~~sql
UPDATE some_schema.account_totals AS t
SET last_status = NEW.status
WHERE t.account_id = NEW.account_id
  AND t.last_status IS DISTINCT FROM NEW.status;
~~~

Mệnh đề `IS DISTINCT FROM` đảm bảo statement chỉ thực sự cập nhật khi giá trị khác. Nó giúp giảm nested triggers vô ích.

### 14.4. Không đủ nếu hai chiều luôn tạo giá trị khác nhau

Nếu A trigger tăng B, B trigger tăng A, thì “chỉ cập nhật khi khác” vẫn luôn đúng. Ví dụ:

~~~text
A.x = A.x + 1  →  B.y = B.y + 1
        ↑                |
        +----------------+
~~~

Cần **loại bỏ một cạnh vòng lặp**, chuyển sang một chiều dữ liệu dẫn xuất, hoặc giới hạn rõ thuật toán.

### 14.5. Idempotency theo business event

Nếu audit/event side effect cần được thực thi tối đa một lần cho cùng một sự kiện, thiết kế:

~~~text
source_event_id (unique)
       |
       v
INSERT INTO processed_events(event_id, ...)
ON CONFLICT(event_id) DO NOTHING
       |
       v
Chỉ thực thi công việc khi INSERT thực sự thành công
~~~

Unique constraint và transaction giúp xử lý retry/concurrency đúng hơn việc chỉ kiểm `pg_trigger_depth()`.

---

## 15. UPDATE OF column và bẫy không có thay đổi giá trị

### 15.1. Chỉ kích hoạt khi cột có trong SET list

~~~sql
CREATE TRIGGER a_30_note_updated
AFTER UPDATE OF note ON trigger_order_lab.items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_audit_after();
~~~

Trigger loại `UPDATE OF note` quan tâm **column được nhắc đến trong SET clause** của UPDATE. Cột có thể được set bằng chính giá trị hiện tại.

### 15.2. Không đồng nghĩa giá trị thay đổi

~~~sql
UPDATE trigger_order_lab.items
SET note=note
WHERE item_id=101;
~~~

Trigger `UPDATE OF note` có thể chạy dù `OLD.note` và `NEW.note` bằng nhau.

### 15.3. BEFORE trigger sửa cột không được nhắc trong SET

Nếu câu UPDATE chỉ nhắc `quantity`, nhưng BEFORE trigger khác sửa `NEW.note`, một trigger khai báo `UPDATE OF note` **không tự được kích hoạt chỉ vì BEFORE trigger đã sửa note**. Trigger column list chủ yếu xét cú pháp columns targeted by the original UPDATE statement.

### 15.4. Cách thể hiện dữ liệu thực sự thay đổi

~~~sql
CREATE TRIGGER a_40_note_value_changed
AFTER UPDATE OF note ON trigger_order_lab.items
FOR EACH ROW
WHEN (OLD.note IS DISTINCT FROM NEW.note)
EXECUTE FUNCTION trigger_order_lab.fn_audit_after();
~~~

Kết hợp `UPDATE OF note` và `WHEN` có thể tránh log khi `SET note=note`, nhưng **vẫn không bắt trường hợp BEFORE trigger âm thầm đổi note dù câu UPDATE không nhắc note**. Nếu cần phát hiện mọi thay đổi cuối cùng của note, dùng `AFTER UPDATE` không column list kèm WHEN.

### 15.5. Không lạm dụng việc “skip UPDATE nếu old=new”

Một BEFORE trigger `RETURN NULL` khi toàn bộ columns không đổi có thể ảnh hưởng:

- Row count của statement.
- AFTER ROW trigger/audit.
- Các tác vụ nghiệp vụ muốn ghi nhận một lệnh UPDATE dù giá trị giống.
- Quan sát concurrency và row versions.

Nếu chỉ muốn bỏ **side effect** không cần thiết, thường dùng `WHEN` hoặc IF trong trigger **AFTER** thay vì hủy row update khi chưa có contract rõ.

---

## 16. Chuỗi side effects hai bảng: cách phân tích vòng lặp

### 16.1. Một lỗi thiết kế điển hình

~~~text
orders AFTER UPDATE
   -> UPDATE customers.total_spent
       -> customers AFTER UPDATE
           -> UPDATE orders.sync_flag
               -> orders AFTER UPDATE
                   -> ...
~~~

Nếu `orders AFTER UPDATE` chạy cho **mọi** cột thay đổi, thao tác `sync_flag` cũng làm trigger orders chạy, kể cả customer totals không còn ý nghĩa thay đổi.

### 16.2. Cách thứ nhất: giảm kích hoạt theo field nghiệp vụ

~~~sql
CREATE TRIGGER a_10_recalc_customer_total
AFTER UPDATE OF amount,status,customer_id ON some_schema.orders
FOR EACH ROW
WHEN (
    OLD.amount IS DISTINCT FROM NEW.amount
    OR OLD.status IS DISTINCT FROM NEW.status
    OR OLD.customer_id IS DISTINCT FROM NEW.customer_id
)
EXECUTE FUNCTION some_schema.fn_recalc_customer_total();
~~~

Đây là **mẫu thiết kế**, không phải DDL chạy trực tiếp trên lab: các objects giả định cần được tạo trước.

Nếu chỉ cập nhật `sync_flag`, trigger không gọi lại recalculation. Điều này loại bỏ một cạnh vòng lặp theo điều kiện nghiệp vụ.

### 16.3. Cách thứ hai: sở hữu dữ liệu dẫn xuất ở một hướng

Thiết kế rõ:

~~~text
orders (nguồn dữ liệu chuẩn)
       |
       v
customer_totals (projection được tính từ orders)
       |
       X không ghi ngược vào orders
~~~

Bảng dẫn xuất có thể được cập nhật trực tiếp bằng một trigger, batch job hoặc materialized view. Tránh cho derived side effects ghi ngược nguồn dữ liệu nếu không có lý do và cơ chế dừng xác định.

### 16.4. Cách thứ ba: command/event thay vì phản xạ qua lại

Các nghiệp vụ phức tạp nên có explicit command handler hoặc outbox event; event được xử lý idempotent, có state machine và condition transition xác định. Không dùng hai triggers ghi qua lại để giả lập workflow không có owner.

### 16.5. SQL có điều kiện bảo vệ lock và write load

Nếu bắt buộc duy trì bảng tổng:

~~~sql
UPDATE some_schema.customer_totals AS t
SET total_amount = v_calculated
WHERE t.customer_id = NEW.customer_id
  AND t.total_amount IS DISTINCT FROM v_calculated;
~~~

Mệnh đề này giảm UPDATE không cần thiết nhưng vẫn cần xem concurrency, FK, và cách `v_calculated` được tính. Nếu tổng được tính từ SELECT trong một snapshot mà nhiều transactions cùng update, có thể cần locking hoặc delta update phù hợp để tránh stale aggregates.

---

## 17. Đồng bộ bảng tổng hợp: vấn đề nhiều rows và cạnh tranh

### 17.1. Row trigger cập nhật tổng từng hàng

Một trigger sau khi INSERT order có thể:

~~~sql
UPDATE some_schema.customer_totals
SET total_amount = total_amount + NEW.amount
WHERE customer_id=NEW.customer_id;
~~~

Đây là delta update có thể hợp lý nếu bảng tổng được khởi tạo đúng và transaction locking đảm bảo update atomic. Nhưng cần xử lý đầy đủ:

- INSERT mới.
- DELETE hoàn tác delta.
- UPDATE amount/status/owner.
- Di chuyển order giữa customers.
- UPDATE từ trạng thái paid→refunded hoặc ngược lại.
- Constraint errors và transaction rollback.
- Bulk DML áp vào hàng triệu rows.

Một logic chỉ cộng khi INSERT sẽ **không giữ đúng tổng** sau DELETE/UPDATE.

### 17.2. Điểm nóng

Nếu nhiều transactions cùng thêm orders cho một customer, mọi trigger cùng UPDATE một `customer_totals` row có thể gây **hot-row contention**. Trigger logic đúng vẫn có thể gây bottleneck hiệu năng.

### 17.3. AFTER STATEMENT + transition tables

Khi một UPDATE batch ảnh hưởng 100.000 rows, có thể dùng transition tables để tính tổng delta **theo tập** thay vì gọi UPDATE tổng 100.000 lần. Phần sau sẽ trình bày chi tiết.

### 17.4. Idempotent reconciliation

Một cách khác: kiểm tra lại bảng tổng bằng query từ source-of-truth theo lịch, phát hiện drift và tái tính. Nếu chỉ dựa vào triggers phức tạp nhiều nhánh mà không có reconciliation tests, sai lệch rất khó phát hiện.

---

## 18. AFTER STATEMENT và transition tables

### 18.1. Transition relation là gì?

Một số AFTER triggers có thể khai báo các **transition tables** chứa tập các rows cũ/mới của statement:

- `OLD TABLE`: dữ liệu row cũ của những rows bị UPDATE/DELETE.
- `NEW TABLE`: dữ liệu row mới của những rows bị INSERT/UPDATE.

Chúng giúp viết SQL set-based bên trong trigger.

### 18.2. Ví dụ đếm những rows thay đổi quantity

~~~sql
CREATE TABLE trigger_order_lab.change_batches (
    batch_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    changed_rows bigint NOT NULL,
    logged_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION trigger_order_lab.fn_count_updated_items()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_changed bigint;
BEGIN
    SELECT COUNT(*)
      INTO v_changed
      FROM old_rows AS o
      JOIN new_rows AS n USING (item_id)
     WHERE o.quantity IS DISTINCT FROM n.quantity;

    INSERT INTO trigger_order_lab.change_batches(changed_rows)
    VALUES (v_changed);

    RETURN NULL;
END;
$$;

CREATE TRIGGER s_80_count_item_changes
AFTER UPDATE ON trigger_order_lab.items
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_count_updated_items();
~~~

Ở đây `old_rows`, `new_rows` là tên transition relations có thể được tham chiếu trong SQL của trigger function. Đây là bảng/tập hàng tạm trong context trigger, không phải các bảng thường tồn tại vĩnh viễn trong schema.

### 18.3. Thử

~~~sql
BEGIN;

UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id IN (101,102,103);

SELECT * FROM trigger_order_lab.change_batches
ORDER BY batch_id DESC LIMIT 1;

ROLLBACK;
~~~

Nếu có ba items ID 101..103 và quantity thật sự đổi, `changed_rows=3`. `s_80_count_item_changes` chỉ chạy một lần cho statement thay vì một lần mỗi row. Nếu UPDATE 0 rows, statement trigger vẫn chạy và `changed_rows=0`.

### 18.4. Giới hạn cần nhớ

Transition tables có những giới hạn cú pháp và khả năng áp dụng:

- Dùng cho AFTER triggers phù hợp trên bảng thường theo version hỗ trợ.
- Không dùng cho constraint triggers.
- Với `UPDATE` có transition tables, không chỉ định column list kiểu `UPDATE OF quantity` trên cùng trigger.
- Quan hệ tham chiếu được khai báo trong `REFERENCING` phải đúng với event.
- Với partitioned tables, multi-stage operations và FK actions, transition relation content/routing có thể cần kiểm thử theo phiên bản.

### 18.5. Không dùng transition table để suy ra thứ tự rows

Transition table thể hiện **tập rows**, không hứa thứ tự xử lý. Nếu cần aggregate, GROUP BY và JOIN theo key là cách đúng; không phụ thuộc identity/log ID để “chọn row đầu tiên” từ transition relation.

---

## 19. Constraint trigger và kích hoạt trì hoãn

### 19.1. Constraint trigger khác trigger thường

Một **constraint trigger** do người dùng tạo là trigger với cú pháp `CREATE CONSTRAINT TRIGGER`, chỉ phù hợp những trường hợp AFTER ROW được hỗ trợ và có thể khai báo `DEFERRABLE`.

Một số kiểm tra toàn vẹn tham chiếu của PostgreSQL cũng được thực thi bằng các trigger nội bộ. Không tự sửa/tắt các internal triggers đó như user audit triggers.

### 19.2. Deferred nghĩa gì?

- `NOT DEFERRABLE`: kiểm tra không bị đẩy tới cuối transaction theo SET CONSTRAINTS.
- `DEFERRABLE INITIALLY IMMEDIATE`: mặc định thực thi sớm, có thể `SET CONSTRAINTS ... DEFERRED` trong transaction.
- `DEFERRABLE INITIALLY DEFERRED`: có thể được xếp để thực thi vào thời điểm deferred, thường trước commit, trừ khi SET CONSTRAINTS làm nó immediate.

**“AFTER” không đồng nghĩa deferred**: một AFTER trigger bình thường và một constraint trigger deferred có thời gian thực thi khác nhau.

### 19.3. Cú pháp mẫu

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_constraint_probe()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE NOTICE
        'Constraint trigger %, item %, depth %',
        TG_NAME, NEW.item_id, pg_trigger_depth();
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER ct_item_probe
AFTER INSERT OR UPDATE ON trigger_order_lab.items
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_constraint_probe();
~~~

Đây là trigger dùng **NOTICE** để minh họa timing, không phải constraint thực sự kiểm tra dữ liệu. Không dùng một “probe” như vậy làm bằng chứng dữ liệu có invariant. Với dữ liệu nhạy cảm, không log row fields tùy tiện.

### 19.4. Thử SET CONSTRAINTS

~~~sql
BEGIN;

INSERT INTO trigger_order_lab.items
    (item_id,code,quantity)
VALUES (190,' deferred ',2);

-- Kiểm tra thời điểm chạy khi chuyển sang IMMEDIATE.
SET CONSTRAINTS ct_item_probe IMMEDIATE;

ROLLBACK;
~~~

Với PostgreSQL, chuyển một constraint deferrable từ deferred sang immediate có thể khiến các sự kiện đang chờ được kiểm tra ngay ở thời điểm `SET CONSTRAINTS`. Nếu không chuyển, các sự kiện deferred thường được xử lý trước commit.

### 19.5. WHEN của constraint trigger được kiểm tra khi nào?

Nếu constraint trigger có `WHEN`, điều kiện **được đánh giá ngay sau thao tác row**, không trì hoãn cùng việc gọi function. Nếu WHEN false, event không được queue. Nếu TRUE, function có thể được thực thi muộn tùy deferral.

### 19.6. Deferred trigger có thể quan sát trạng thái DB khác lúc event phát sinh

Nếu function chạy cuối transaction, các statements khác có thể đã thay đổi rows liên quan. Không giả định SELECT trong deferred trigger chỉ thấy trạng thái đúng ngay sau câu INSERT làm nó được queue. Thiết kế invariant có thể cần kiểm tra lại state hiện tại.

### 19.7. SET CONSTRAINTS không điều khiển mọi trigger

`SET CONSTRAINTS` tác động các **deferrable constraints/constraint triggers** liên quan, không chuyển tất cả ordinary AFTER ROW triggers sang deferred. Không xem nó là “đặt toàn hệ thống trigger chạy sau commit”.

---

## 20. Trigger nội bộ của khóa ngoại và cascading actions

### 20.1. Foreign keys dựa trên cơ chế trigger

PostgreSQL dùng internal constraint triggers để thực hiện kiểm tra và hành động referential integrity trong những trường hợp phù hợp.

Ví dụ:

~~~sql
CREATE TABLE trigger_order_lab.parents (
    parent_id integer PRIMARY KEY
);

CREATE TABLE trigger_order_lab.children (
    child_id integer PRIMARY KEY,
    parent_id integer NOT NULL
      REFERENCES trigger_order_lab.parents(parent_id)
      ON DELETE CASCADE
);
~~~

Khi xóa parent, hành động `ON DELETE CASCADE` có thể DELETE child rows và kích hoạt DELETE triggers trên bảng `children`.

### 20.2. Cascade có thể kéo theo nhiều cấp side effects

~~~text
DELETE parent
      |
      v
FK ON DELETE CASCADE
      |
      v
DELETE child
      |
      +--> child BEFORE DELETE trigger
      |
      +--> child AFTER DELETE trigger
                |
                +--> DML bảng khác
                          |
                          +--> trigger mới...
~~~

Đây là một loại **nested DML** không nhất thiết xuất phát từ SQL viết trực tiếp trong trigger function của bạn.

### 20.3. Đừng guard toàn hệ thống bằng depth>1

Child DELETE trigger có thể chạy ở depth lồng nhau do FK referential action hợp lệ. Nếu bạn viết “bất kỳ pg_trigger_depth()>1 thì RETURN NULL”, bạn có thể bỏ qua audit hoặc điều kiện quan trọng của cascade.

### 20.4. Constraint timing và FK hành động không giống nhau trong mọi trường hợp

Một số kiểm tra FK có thể deferrable; còn referential actions như cascade/set-null có thời điểm thực thi riêng theo quy tắc FK và loại hành động. Không suy rằng chỉ vì FK DEFERRABLE thì mọi cascade side effects luôn chờ tới COMMIT.

### 20.5. Không tắt internal triggers để tránh vòng lặp

`ALTER TABLE ... DISABLE TRIGGER ALL` hoặc `session_replication_role='replica'` có thể ảnh hưởng cả cơ chế toàn vẹn tham chiếu trong những ngữ cảnh đặc biệt. Đây **không phải** biện pháp chuẩn để sửa trigger recursion; có thể tạo orphan data. Sửa graph logic và constraint design thay vì né engine validation.

---

## 21. INSERT ... ON CONFLICT DO UPDATE: có thể kích hoạt cả INSERT và UPDATE triggers

### 21.1. UPSERT không đơn thuần là “INSERT hoặc UPDATE, chỉ một bên”

Một statement:

~~~sql
INSERT INTO trigger_order_lab.items
    (item_id,code,quantity)
VALUES
    (101,' changed ',10)
ON CONFLICT (item_id)
DO UPDATE SET
    code=EXCLUDED.code,
    quantity=EXCLUDED.quantity;
~~~

có thể dẫn đến việc **BEFORE ROW INSERT** và **BEFORE ROW UPDATE** cùng chạy trên một row khi conflict dẫn tới DO UPDATE, ngoài các statement-level triggers theo sự kiện.

### 21.2. Vai trò của EXCLUDED

Các thay đổi của **BEFORE INSERT row triggers** có thể được phản ánh vào các giá trị trong relation `EXCLUDED` mà mệnh đề DO UPDATE sử dụng. Nếu BEFORE INSERT chuẩn hóa `code` thành uppercase, DO UPDATE dùng `EXCLUDED.code` có thể nhận code đã được chuẩn hóa, rồi BEFORE UPDATE trigger có thể chuẩn hóa thêm lần nữa.

Vì vậy tránh các trigger có biến đổi **không idempotent**, như tự thêm prefix mỗi lần gọi:

~~~text
Input: A
BEFORE INSERT -> PREFIX_A
DO UPDATE -> BEFORE UPDATE -> PREFIX_PREFIX_A
~~~

Nếu quy tắc “prefix đúng một lần”, phải có điều kiện/thiết kế bảo đảm không lặp.

### 21.3. Thứ tự statement-level triggers của UPSERT

Với `INSERT ... ON CONFLICT DO UPDATE`, các statement-level triggers có thể được kích hoạt theo trình tự event tổng quát:

1. BEFORE INSERT statement.
2. BEFORE UPDATE statement.
3. AFTER UPDATE statement.
4. AFTER INSERT statement.

Ngay cả khi trong một statement cụ thể không có row nào cuối cùng bị UPDATE, statement-level UPDATE triggers vẫn có thể được kích hoạt vì DO UPDATE clause hiện diện. Do đó trigger statement-level là nơi dễ log nhầm “có update thành công” nếu không quan sát row count/transition relations.

### 21.4. ON CONFLICT DO NOTHING

Khi một row bị bỏ vì conflict DO NOTHING, row-level BEFORE INSERT triggers có thể đã được chạy để xử lý giá trị đề xuất, nhưng không có row insert thực tế và AFTER ROW INSERT không chạy cho row bị bỏ. Nếu BEFORE INSERT trigger đã tạo một side-effect SQL cùng transaction trong bảng log, side effect đó có thể còn lại khi statement kết thúc thành công với DO NOTHING.

**Không đồng nhất "BEFORE INSERT trigger đã chạy" với "row đã được INSERT".**

### 21.5. UPSERT với update condition không thỏa

~~~sql
INSERT INTO trigger_order_lab.items
    (item_id,code,quantity)
VALUES (101,' alpha ',3)
ON CONFLICT (item_id)
DO UPDATE SET quantity=EXCLUDED.quantity
WHERE trigger_order_lab.items.quantity IS DISTINCT FROM EXCLUDED.quantity;
~~~

Nếu quantity hiện tại đã bằng giá trị đề xuất, conflict có thể được xử lý nhưng **không update row** vì WHERE false. Statement-level triggers vẫn chịu semantics của UPSERT; không dùng việc trigger statement chạy để kết luận đã cập nhật hàng.

### 21.6. Không tạo audit 2 lần cho một business event

Nếu bạn có audit trong cả BEFORE INSERT và AFTER UPDATE, một UPSERT có conflict có thể ghi audit ở cả hai nơi. Thiết kế audit nên dựa trên **thay đổi thực sự hoàn tất**, thường bằng AFTER row/statement cùng điều kiện, và event key/idempotency phù hợp.

---

## 22. MERGE và trigger ordering

### 22.1. MERGE có nhiều nhánh thao tác

PostgreSQL 15+ hỗ trợ `MERGE`, cho phép tùy điều kiện thực hiện INSERT/UPDATE/DELETE trên các hàng phù hợp. Trigger semantics của MERGE có chi tiết phụ thuộc sự kiện và phiên bản, nhưng nguyên tắc quan trọng:

- Statement-level triggers có thể kích hoạt cho những action types được nhắc trong MERGE, không nhất thiết chứng minh có row được tác động ở mọi action.
- Row-level triggers được kích hoạt cho những rows thực sự nhận action tương ứng.
- Khi action làm SQL DML khác phát sinh qua trigger, nested triggers có thể được kích hoạt.

### 22.2. Đừng viết một statement-level audit ghi “đã UPDATE N rows” mà không có N

Một trigger AFTER UPDATE FOR EACH STATEMENT có thể chạy dù MERGE nhánh UPDATE không tác động row nào. Để biết số rows thực sự thay đổi theo action, xem cơ chế transition relations/command status/đo lường phù hợp phiên bản; không chỉ dựa trên `TG_OP='UPDATE'` của statement trigger.

### 22.3. MERGE khác UPSERT

Không mặc định lấy thứ tự từng row trong `ON CONFLICT DO UPDATE` áp y hệt cho `MERGE`. Dựa vào semantics event của statement cụ thể và phiên bản PostgreSQL, không dựa vào tên tính năng “upsert-like”.

### 22.4. Khi bài toán phụ thuộc chính xác action count

Thay vì trigger log “MERGE executed”, cân nhắc một cơ chế audit explicit trong workflow/caller hoặc transition-table aggregation phù hợp. Quan trọng là **đếm rows thực sự thay đổi và tránh nhân sự kiện**.

---

## 23. Partitioned tables và trigger không chạy trên cùng physical relation

### 23.1. Parent vs leaf partition

Một bảng phân vùng có parent logic và các leaf partitions chứa rows:

~~~text
events (partitioned parent)
    |
    +-- events_2026_10
    +-- events_2026_11
    +-- events_2026_12
~~~

Khi SQL nhắm tới parent, PostgreSQL route hàng tới leaf. Statement-level trigger trên parent và row-level triggers trên partitions có phạm vi khác nhau.

### 23.2. Row-level trigger của partitioned parent

Khi tạo row-level trigger trên parent partitioned table, PostgreSQL tạo clone triggers trên các partitions tương ứng (theo các điều kiện hỗ trợ/version). Cần lưu ý khi ATTACH/DETACH partition và quản lý tên trigger/clone.

### 23.3. Statement-level trigger trên parent

Nếu statement SQL nhắm tới parent, statement-level triggers của **parent** kích hoạt; statement-level trigger tự gắn trên leaf không tự động được gọi chỉ vì parent statement route hàng vào leaf.

Nếu SQL nhắm trực tiếp một leaf, phạm vi statement-level trigger được xác định bởi relation thực sự là target.

### 23.4. UPDATE đổi partition key có thể thành row movement

Khi UPDATE làm row chuyển partition:

- BEFORE UPDATE row trigger có thể chạy trên **partition nguồn**.
- BEFORE INSERT row trigger có thể chạy trên **partition đích**.
- AFTER ROW thường đi theo cơ chế DELETE ở partition nguồn và INSERT ở đích, thay vì một AFTER UPDATE row trigger đơn giản.

Do đó audit logic “chỉ nghe AFTER UPDATE row trigger” có thể bỏ qua hoặc hiểu sai một row movement. Cần thử trên phiên bản PostgreSQL thực tế và thiết kế audit bao phủ row movement.

### 23.5. Không dùng BEFORE ROW để route sang partition khác tùy tiện

Việc BEFORE ROW sửa partition key dẫn tới row đáng lẽ thuộc partition khác có các hạn chế của declarative partitioning; không mặc định PostgreSQL sẽ re-route khi NEW bị trigger sửa sang một partition khác. Đặt routing key trước khi INSERT, hoặc thiết kế statement/API để route đúng.

### 23.6. Cascade và partitioning làm graph trigger phức tạp hơn

Một DELETE parent có cascade hoặc UPDATE partition key có thể tạo nhiều events trên các physical relations. Vì vậy dùng `TG_TABLE_SCHEMA`, `TG_TABLE_NAME`, event type và business identity để chẩn đoán thay vì chỉ nhìn tên bảng parent trong SQL ban đầu.

---

## 24. INSTEAD OF triggers trên view

### 24.1. View không lưu row theo cách table thường

Một view có thể là projection/join. Khi muốn cho client INSERT/UPDATE/DELETE view mà không tự động updatable, có thể dùng `INSTEAD OF` trigger để định nghĩa thao tác thực sự.

~~~sql
CREATE VIEW trigger_order_lab.v_items AS
SELECT item_id,code,quantity
FROM trigger_order_lab.items;
~~~

Đây là view đơn giản có thể đã tự updatable; ví dụ sau dùng INSTEAD OF để minh họa event interception, không phải yêu cầu bắt buộc cho một view như vậy.

### 24.2. Hàm INSTEAD OF UPDATE

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_update_item_view()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE trigger_order_lab.items AS i
       SET code=NEW.code,
           quantity=NEW.quantity
     WHERE i.item_id=OLD.item_id;

    RETURN NEW;
END;
$$;

CREATE TRIGGER io_10_update_item
INSTEAD OF UPDATE ON trigger_order_lab.v_items
FOR EACH ROW
EXECUTE FUNCTION trigger_order_lab.fn_update_item_view();
~~~

Một UPDATE view lúc này **gọi UPDATE trên base items**. Base table `b_10_normalize`, `b_20_validate`, `a_10_audit` và statement triggers phù hợp có thể chạy **lồng bên trong**.

### 24.3. Không tưởng rằng return NEW tự UPDATE bảng nền

Trong INSTEAD OF trigger, function phải thực hiện thao tác cần thiết. `RETURN NEW` không có nghĩa PostgreSQL tự ghi NEW vào base table như một BEFORE trigger table thường.

### 24.4. Thận trọng với recursion gián tiếp từ view

Một INSTEAD OF trigger cập nhật bảng, bảng có AFTER trigger lại UPDATE view, có thể sinh chu trình view→table→view. Kiểm tra graph phụ thuộc và điều kiện dừng.

### 24.5. VIEW trigger và security

Trigger function có quyền `SECURITY INVOKER/DEFINER` riêng; quyền gọi view không tự cho phép mọi thay đổi bảng nền. Nếu trigger function SECURITY DEFINER, cần harden search_path và quyền theo nguyên tắc least privilege. Đây là một đường nâng quyền tiềm ẩn nếu cấu hình sai.

---

## 25. TRUNCATE không kích hoạt DELETE ROW triggers

### 25.1. Hai lệnh khác nhau

~~~sql
DELETE FROM trigger_order_lab.items;
~~~

và

~~~sql
TRUNCATE TABLE trigger_order_lab.items;
~~~

không có cùng trigger behavior:

- DELETE kích hoạt DELETE ROW và DELETE STATEMENT triggers phù hợp.
- TRUNCATE kích hoạt **TRUNCATE STATEMENT** triggers phù hợp, không gọi từng DELETE ROW trigger cho hàng bị xóa.

### 25.2. Vì sao điều này nguy hiểm với audit?

Nếu hệ thống chỉ audit bằng AFTER DELETE FOR EACH ROW, một thao tác TRUNCATE có thể bỏ qua audit từng hàng. Nếu TRUNCATE được cho phép, cần có cơ chế audit riêng hoặc **không cấp quyền TRUNCATE** cho role nghiệp vụ.

### 25.3. Trigger sự kiện TRUNCATE

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_trace_truncate()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO trigger_order_lab.fire_log
        (trigger_name,timing,operation,item_id)
    VALUES (TG_NAME,TG_WHEN,TG_OP,NULL);
    RETURN NULL;
END;
$$;

CREATE TRIGGER s_10_before_truncate
BEFORE TRUNCATE ON trigger_order_lab.items
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_trace_truncate();
~~~

**Không thực thi TRUNCATE trên lab đang chứa dữ liệu cần giữ** nếu chưa có cách khôi phục. Có thể chạy trong transaction lab với ROLLBACK vì TRUNCATE trong PostgreSQL là transactional về dữ liệu, nhưng vẫn có tác động khóa và caveats snapshot/concurrency.

### 25.4. TRUNCATE CASCADE

`TRUNCATE ... CASCADE` có thể ảnh hưởng nhiều tables do FK dependencies; các TRUNCATE triggers ở các relations chịu tác động có thể chạy. Đừng suy rằng statement chỉ thay bảng được đặt tên đầu tiên.

---

## 26. RETURN NULL và tác dụng phụ đã chạy trước đó

### 26.1. Một BEFORE ROW trigger có thể hủy row

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_skip_zero_quantity()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.quantity=0 THEN
        RETURN NULL;
    END IF;
    RETURN NEW;
END;
$$;
~~~

Nếu gắn BEFORE INSERT, row quantity=0 bị skip. Không có INSERT row, nhưng SQL có thể thành công với `INSERT 0 0` theo command tag.

### 26.2. Log trước RETURN NULL có thể vẫn tồn tại

Giả sử BEFORE trigger `b_10_normalize` đã INSERT fire_log. Một BEFORE trigger sau đó `RETURN NULL` để skip INSERT. Vì không có exception, **các row log được insert trước khi row bị bỏ có thể vẫn tồn tại trong transaction và được commit**, dù item không hề được chèn.

Điều này rất quan trọng: không dùng **BEFORE audit** làm bằng chứng row đã được lưu cuối cùng.

### 26.3. Nếu RAISE EXCEPTION thay vì RETURN NULL

Nếu một trigger báo lỗi và statement bị rollback, các SQL side effects trong transaction của statement cũng bị rollback (trừ các cơ chế không rollback như sequence values). Nếu caller catch exception trong một PL/pgSQL exception block, cơ chế subtransaction quyết định những thay đổi thuộc block bị rollback.

### 26.4. AFTER trigger thích hợp hơn cho audit “row đã qua lệnh DML”

Một AFTER ROW trigger thường chỉ chạy khi row đã được thao tác thành công ở mức statement. Tuy nhiên **AFTER vẫn trước COMMIT**; transaction rollback sau đó sẽ rollback audit row cùng giao dịch. Muốn một bản ghi audit tồn tại dù transaction thất bại, cần thiết kế audit độc lập có xem xét bảo mật và nhất quán, không chỉ dựa vào AFTER trigger.

### 26.5. Ngăn trùng audit bằng event identity

Nếu một UPSERT, nested UPDATE hoặc retry khiến cùng thay đổi nghiệp vụ được xử lý nhiều lần, audit có thể trùng. Thiết kế event key (transaction/request/business event ID) và constraint `UNIQUE` phù hợp nếu contract yêu cầu một dòng/event. Đừng suy luận “trigger AFTER chỉ gọi một lần trong đời một order”.

---

## 27. Transactional outbox: giải pháp cho side effects ngoài DB

### 27.1. Bài toán

Trigger INSERT payment và ngay lập tức gọi HTTP để gửi email. Sau đó một constraint khác làm transaction rollback. Email đã được gửi, nhưng payment không tồn tại.

Hoặc HTTP thành công nhưng response timeout; ứng dụng retry transaction, email được gửi hai lần.

### 27.2. Dùng outbox trong cùng transaction

~~~text
Ứng dụng ghi order/payment
         |
         v
PostgreSQL transaction
   |
   +-- INSERT/UPDATE business table
   |
   +-- INSERT outbox event  <-- trigger hoặc application
   |
   +-- COMMIT
         |
         v
Worker đọc outbox đã commit
         |
         +-- Gửi broker/email/webhook
         |
         +-- Ghi nhận delivered/retry
~~~

Nếu transaction rollback, **business change và outbox row đều rollback**. Worker chỉ thấy outbox đã commit.

### 27.3. Schema outbox minh họa

~~~sql
CREATE TABLE trigger_order_lab.outbox (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id bigint NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    processed_at timestamptz
);

CREATE INDEX idx_outbox_pending
ON trigger_order_lab.outbox(created_at,event_id)
WHERE processed_at IS NULL;
~~~

### 27.4. Trigger AFTER ghi outbox

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_outbox_item_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO trigger_order_lab.outbox
        (aggregate_type,aggregate_id,event_type,payload)
    VALUES
        ('item',NEW.item_id,'quantity_changed',
         jsonb_build_object(
             'old_quantity',OLD.quantity,
             'new_quantity',NEW.quantity
         ));

    RETURN NULL;
END;
$$;

CREATE TRIGGER a_70_outbox_quantity_changed
AFTER UPDATE ON trigger_order_lab.items
FOR EACH ROW
WHEN (OLD.quantity IS DISTINCT FROM NEW.quantity)
EXECUTE FUNCTION trigger_order_lab.fn_outbox_item_change();
~~~

Một UPDATE làm quantity thật sự đổi sẽ ghi outbox row **cùng transaction**. Nếu ROLLBACK, outbox row cũng biến mất.

### 27.5. Worker gửi sự kiện sau COMMIT

Worker ngoài DB đọc các outbox rows chưa processed, claim jobs với locking phù hợp (thường có `FOR UPDATE SKIP LOCKED` khi thích hợp), gửi event, rồi đánh dấu trạng thái.

Bên nhận vẫn nên **idempotent** vì có thể gửi trùng nếu worker crash sau khi gửi nhưng trước khi ghi processed_at. Transactional outbox cải thiện atomicity của *DB state + intent to publish*, không tự tạo exactly-once delivery ngoài hệ thống.

### 27.6. Event payload nên đủ nhưng không quá rộng

Không lưu secret/password/PII không cần thiết vào outbox chỉ vì dễ gọi `row_to_json(NEW)`. Chỉ đặt những fields consumer thực sự cần; mã hóa/quyền truy cập/retention theo chính sách.

---

## 28. PostgreSQL NOTIFY là after-commit delivery, nhưng không phải durable queue

### 28.1. Trigger có thể gọi pg_notify

~~~sql
PERFORM pg_notify(
    'item_change',
    NEW.item_id::text
);
~~~

Khi gọi bên trong transaction, notification chỉ được gửi sau **transaction commit**; rollback không gửi notification đó.

### 28.2. Nhưng NOTIFY không thay message broker bền vững

- Listener không kết nối có thể bỏ lỡ notification.
- Payload có giới hạn và không dùng để chuyển object lớn.
- Có thể có cơ chế hợp nhất những notifications trùng trong một transaction theo rules PostgreSQL.
- Giao tiếp LISTEN/NOTIFY phụ thuộc transaction semantics và client connections.
- Không có durable retry/acknowledgement queue như outbox table.

### 28.3. Kết hợp outbox và NOTIFY

Một kiến trúc phổ biến:

1. Trigger hoặc application ghi outbox row trong transaction.
2. Gọi NOTIFY như **tín hiệu đánh thức** consumer.
3. Sau commit, listener được thông báo.
4. Worker **đọc outbox** là nguồn sự thật bền vững.
5. Nếu mất notification, polling định kỳ vẫn quét outbox.

Mẫu này tránh xem NOTIFY như một queue đảm bảo giao hàng.

### 28.4. Không dùng transaction trigger để gọi API ngoài tùy ý

Việc gọi HTTP trực tiếp trong trigger giữ transaction mở trong lúc chờ mạng, tăng lock duration và coupling. Nếu lỗi/timeout, DB transaction khó điều phối với external operation. Outbox thường là mô hình an toàn hơn.

---

## 29. Sequence, time và side effects không rollback

### 29.1. Sequence values không hồi khi rollback

~~~sql
BEGIN;

INSERT INTO trigger_order_lab.outbox
    (aggregate_type,aggregate_id,event_type,payload)
VALUES
    ('demo',0,'test','{}'::jsonb);

ROLLBACK;
~~~

Row outbox được rollback, nhưng sequence/identity có thể đã cấp một `event_id` và **không giảm lại**. Vì vậy có khoảng trống ID là bình thường.

### 29.2. Không dùng gap sequence làm bằng chứng mất audit row

Audit table có log IDs 1,2,5 không có nghĩa người dùng đã xóa log 3,4; có thể do transaction rollback, sequence cache, conflict hoặc các lý do hợp lệ khác.

### 29.3. Transaction timestamps khác clock timestamps

- `now()`/`transaction_timestamp()` là thời điểm bắt đầu transaction theo semantics PostgreSQL.
- `statement_timestamp()` là thời điểm bắt đầu statement hiện tại.
- `clock_timestamp()` đọc thời gian đồng hồ thực tế, có thể thay đổi giữa lời gọi.

Nếu đo thứ tự trigger trong cùng statement, nhiều rows có thể có cùng transaction/statement timestamp. `clock_timestamp()` có độ phân giải nhưng vẫn không bảo đảm total order xuyên transactions.

### 29.4. Không dùng timestamp thay business version

Nếu yêu cầu “chỉ áp dụng sự kiện mới nhất”, lưu một version/sequence nghiệp vụ được enforce bằng constraint/transaction thay vì so một timestamp có thể bị trùng hoặc không đúng commit order.

---

## 30. Exception handling và rollback trong trigger

### 30.1. Exception được bắt sẽ rollback SQL trong block tương ứng

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_example_exception()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        INSERT INTO trigger_order_lab.fire_log
            (trigger_name,timing,operation,item_id)
        VALUES ('before_error','AFTER',TG_OP,NEW.item_id);

        RAISE EXCEPTION 'demo error';
    EXCEPTION
        WHEN raise_exception THEN
            RAISE NOTICE 'Lỗi được bắt trong nested block';
    END;

    RETURN NULL;
END;
$$;
~~~

Trong subblock có `EXCEPTION`, những row changes thực thi trước exception bị rollback khi lỗi được bắt. `RAISE NOTICE` vẫn có thể quan sát ở client; đừng coi log/notice là bằng chứng commit.

### 30.2. Nuốt exception có thể làm data drift

Nếu trigger audit hoặc cập nhật bảng tổng gặp lỗi nhưng dùng:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RETURN NEW;
~~~

nó có thể để business row được ghi thành công nhưng audit/derived rows không được ghi. Không nuốt mọi lỗi để giữ transaction “thành công” nếu dữ liệu phụ thuộc cần nhất quán.

### 30.3. Khi nào nên fail fast?

Nếu một invariant không thể được duy trì (ví dụ tổng nợ, FK, unique event ID, permission), việc raise exception có thể đúng hơn việc ghi thiếu dữ liệu và hy vọng job sau sửa. Quyết định theo contract và availability yêu cầu.

### 30.4. Side effects ngoài DB không trở lại cùng rollback

Nếu trigger đã gửi HTTP/email trước khi raise exception, rollback PostgreSQL không tự gọi “undo email”. Đây là một lý do khác để dùng outbox/idempotency thay vì external side effect trực tiếp.

### 30.5. Không nhầm subtransaction với nested transaction độc lập

PL/pgSQL `EXCEPTION` block cung cấp cơ chế rollback nội bộ, nhưng không tạo một independent committed transaction cho audit. PostgreSQL không có khái niệm “trigger tự commit một phần thay đổi” trong transaction caller theo cách đó.

---

## 31. Triggers và quy tắc RECURSIVE được xử lý ở đâu?

### 31.1. Trigger không có keyword RECURSIVE cho vòng lặp nghiệp vụ

`WITH RECURSIVE` là một phần của SQL recursive CTE. Một trigger function lặp do chạy SQL kích hoạt trigger mới là **nested trigger execution**, không phải recursive CTE.

### 31.2. Nếu SQL trong trigger dùng CTE đệ quy

Một câu `WITH RECURSIVE` có thể tính tập tổ tiên/con cháu và sau đó UPDATE các rows đó. Những UPDATE này vẫn có thể kích hoạt triggers, nhưng có **hai cơ chế** riêng:

- Recursive query evaluation của CTE.
- Trigger invocation do DML.

Chống cycle của recursive CTE bằng path/cycle detection không tự ngăn cycles trong trigger graph.

### 31.3. Rules là lớp rewrite khác trigger

PostgreSQL còn có `CREATE RULE` (query rewrite rules). Rules có thể viết lại statement trước execution; triggers chạy theo event semantics ở thời điểm thực thi DML. Không áp dụng bảng thứ tự trigger cho những rules chỉ vì cả hai có thể được dùng để đồng bộ dữ liệu.

### 31.4. Không lạm dụng rules để tránh recursion

Đổi một trigger vòng lặp thành rule rewrite chưa chắc giải quyết đúng business semantics; có thể làm hành vi RETURNING, statements nhiều hàng và side effects càng khó suy luận. Chọn công cụ theo mục tiêu và tài liệu của PostgreSQL.

---

## 32. Tra cứu trigger definitions trong system catalog

### 32.1. pg_trigger và pg_get_triggerdef

~~~sql
SELECT
    t.tgname AS trigger_name,
    t.tgrelid::regclass AS relation_name,
    pg_get_triggerdef(t.oid, true) AS definition,
    t.tgenabled AS enabled_state,
    t.tgisinternal AS is_internal
FROM pg_trigger AS t
WHERE t.tgrelid = 'trigger_order_lab.items'::regclass
ORDER BY t.tgname;
~~~

Đây là cách đọc nhanh danh sách triggers trên bảng. `pg_get_triggerdef` giúp thấy timing, events, WHEN và function được gọi mà không phải tự giải mã `tgtype` bitmask.

### 32.2. Giá trị tgenabled

| `tgenabled` | Ý nghĩa khái quát |
|---|---|
| `O` | Enabled trong normal origin/local replication modes |
| `D` | Disabled |
| `R` | Enabled khi replication role là replica |
| `A` | Always enabled |

Trạng thái này tương tác với `session_replication_role`. Không đổi session replication role chỉ để “bỏ qua” một trigger đang gây recursion; có nguy cơ bỏ qua FK/integrity triggers.

### 32.3. pg_trigger.tgisinternal

`tgisinternal=true` đánh dấu internal trigger. Các triggers liên quan FK/constraint hệ thống thường xuất hiện với thuộc tính này. Đừng áp dụng script tự động disable/drop mọi trigger trên bảng chỉ vì thấy không có trong DDL do app tạo.

### 32.4. Xem function trigger trỏ đến

~~~sql
SELECT
    t.tgname,
    t.tgrelid::regclass AS target_relation,
    t.tgfoid::regprocedure AS trigger_function,
    pg_get_functiondef(t.tgfoid) AS function_definition
FROM pg_trigger AS t
WHERE t.tgrelid='trigger_order_lab.items'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

Khi debug vòng lặp, đọc **cả SQL trong function**, vì một trigger có thể UPDATE các bảng khác mà catalog metadata không thể hiện trực tiếp dưới dạng graph.

### 32.5. Liệt kê user triggers trong schema

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    t.tgname AS trigger_name,
    pg_get_triggerdef(t.oid, true) AS definition
FROM pg_trigger AS t
JOIN pg_class AS c ON c.oid=t.tgrelid
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='trigger_order_lab'
  AND NOT t.tgisinternal
ORDER BY c.relname,t.tgname;
~~~

Nếu có partitions, còn phải xét clone triggers và các quan hệ con. Không chỉ xem parent rồi kết luận toàn bộ graph đã được liệt kê.

### 32.6. Xem constraint triggers

~~~sql
SELECT
    conname,
    contype,
    conrelid::regclass AS relation_name,
    confrelid::regclass AS referenced_relation,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE connamespace='trigger_order_lab'::regnamespace
ORDER BY conrelid::regclass::text, conname;
~~~

Catalog `pg_constraint` thể hiện constraints, nhưng **không thay thế pg_trigger** cho toàn bộ internal/user trigger definitions. Khi chẩn đoán FK, kết hợp cả hai.

---

## 33. Debug đệ quy: xác định graph thay vì đoán

### 33.1. Quan sát độ sâu

~~~sql
RAISE NOTICE 'trigger=% table=%.% event=% depth=%',
    TG_NAME,TG_TABLE_SCHEMA,TG_TABLE_NAME,TG_OP,pg_trigger_depth();
~~~

Chỉ bật logging chi tiết trong lab/staging hoặc khi có giới hạn log volume. Một vòng lặp nhanh có thể tạo quá nhiều notices.

### 33.2. Vẽ graph với SQL thực sự được gọi

Ví dụ:

~~~text
orders AFTER UPDATE (status)
  -> UPDATE customer_totals
       -> customer_totals AFTER UPDATE (total_amount)
           -> UPDATE orders (sync_flag)
               -> orders AFTER UPDATE (mọi cột)
                   -> UPDATE customer_totals ...
~~~

Tìm **cạnh đóng vòng**: trigger orders được kích hoạt lại do UPDATE sync_flag dù status không đổi. Điều chỉnh event predicate đúng có thể loại vòng lặp.

### 33.3. Mỗi cạnh cần câu hỏi rõ

Cho mỗi function trigger, ghi:

- Relation và event kích hoạt.
- BEFORE/AFTER, ROW/STATEMENT.
- WHEN có hay không.
- Các tables nó INSERT/UPDATE/DELETE.
- Cột nào thật sự bị thay đổi.
- Điều kiện WHERE khiến DML tác động 0/1/nhiều rows.
- Có gọi HTTP/NOTIFY/sequence không.
- Có thể bị gọi từ FK cascade, UPSERT, partition routing hay trigger khác không.
- Điều kiện dừng được enforce ở đâu.

### 33.4. Không kết luận từ một pg_trigger_depth log duy nhất

Depth cho biết **mức lồng nhau hiện tại**, không biết graph đầy đủ, identity event và commit state. Một trigger ở depth=2 có thể là FK cascade hợp lệ, không phải lỗi. Một vòng lặp cross-transaction có thể luôn xuất hiện depth=1 ở từng giao dịch riêng.

### 33.5. Ghi dấu theo event ID và transaction

Khi audit phức tạp, cân nhắc lưu request/correlation ID và business event ID. `txid_current()` hoặc các hàm liên quan transaction có thể giúp chẩn đoán nội bộ, nhưng không là primary key xuyên hệ thống hoặc commit-order guarantee.

### 33.6. Chụp exception không làm thay đổi contract

Khi loop gây lỗi, đừng catch `WHEN OTHERS THEN RETURN NEW` chỉ để cho request tiếp tục. Lỗi recursion có thể báo một invariant/side effect chưa hoàn tất; nuốt lỗi tạo trạng thái sai khó nhận biết.

---

## 34. EXPLAIN và phép thử có tác dụng phụ

### 34.1. EXPLAIN không ANALYZE

~~~sql
EXPLAIN
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id=101;
~~~

Lệnh này hiển thị **kế hoạch ước lượng**, không thực thi UPDATE. Nó không cho bạn thời gian trigger thực tế.

### 34.2. EXPLAIN ANALYZE thực sự chạy DML và triggers

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id=101;

ROLLBACK;
~~~

Mẫu này rollback **DML cùng transaction**. Nhưng:

- Sequence identities vẫn có thể tiến.
- External network calls, email, file writes có thể không rollback.
- Locks và I/O đã xảy ra trong lúc chạy.
- Với code trigger lỗi, transaction có thể trở thành aborted và cần ROLLBACK.

Chỉ dùng trên lab, không dùng thử tải lớn trên production với dữ liệu nhạy cảm.

### 34.3. Trigger timing trong EXPLAIN

EXPLAIN ANALYZE cho DML có thể hiển thị thông tin về thời gian/số lần gọi trigger thích hợp, ví dụ:

~~~text
Trigger a_10_audit: time=... calls=...
Execution Time: ...
~~~

Chi tiết output phụ thuộc phiên bản, trigger path và cách execution plan được biểu diễn. Một phần chi phí có thể nằm trong nested statements/functions; không lấy một con số rồi kết luận toàn bộ hiệu năng của graph.

### 34.4. pg_stat_user_functions

Nếu PostgreSQL được cấu hình `track_functions` thích hợp, có thể xem thống kê function:

~~~sql
SELECT
    funcid::regprocedure AS function_name,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname='trigger_order_lab'
ORDER BY total_time DESC;
~~~

Counters phụ thuộc cấu hình, thời gian quan sát và việc reset statistics. Nếu tracking disabled, không có dòng không chứng minh trigger chưa từng chạy.

### 34.5. Theo dõi khóa

Một trigger DML nhiều bảng làm transaction dài hơn; có thể xem:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname=current_database()
  AND pid<>pg_backend_pid();
~~~

Quyền xem chi tiết và thông tin query của sessions khác phụ thuộc PostgreSQL privileges. Không dùng query này để tìm “trigger nào sai” chỉ từ một snapshot; kết hợp dependency graph và các plan/logs.

---

## 35. Vì sao không nên DISABLE TRIGGER để sửa lỗi logic?

### 35.1. Khác biệt giữa USER và ALL

~~~sql
-- Ví dụ DDL, KHÔNG thực thi nếu chưa hiểu hệ quả:
ALTER TABLE trigger_order_lab.items DISABLE TRIGGER USER;
ALTER TABLE trigger_order_lab.items ENABLE TRIGGER USER;
~~~

`USER` áp dụng tới user-defined triggers theo ngữ nghĩa PostgreSQL. `ALL` có thể bao gồm những triggers liên quan internal constraints, thường cần quyền rất cao để thao tác và có thể phá toàn vẹn tham chiếu.

### 35.2. Bỏ audit, validation, projection

Tắt trigger có thể:

- Bỏ qua validation trong trigger.
- Bỏ ghi audit.
- Không cập nhật bảng derived/caches.
- Để dữ liệu khác nhau giữa sources và projections.

Ngay cả khi DB CHECK/FK vẫn bảo vệ một số invariant, những invariant chỉ tồn tại trong trigger có thể không còn được enforce.

### 35.3. session_replication_role

`session_replication_role` ảnh hưởng triggers/rules được kích hoạt theo vai trò replication (origin/local/replica). Đổi giá trị này có thể gây hậu quả rất lớn, kể cả bỏ qua FK checks trong tình huống thích hợp. Không đặt nó thành replica trong ứng dụng thường chỉ để ngăn vòng lặp.

### 35.4. Thay thế đúng cách

- Chỉnh trigger function để có điều kiện dừng.
- Giảm trigger event bằng `UPDATE OF`/`WHEN` hợp lý.
- Tạo one-way derived data model.
- Dùng idempotent UPSERT/unique constraints.
- Chuyển external side effects sang outbox.
- Đối chiếu lại data đã bị drift nếu trước đó có thời kỳ trigger bị tắt.

### 35.5. Maintenance đặc biệt

Có những quy trình migration/backfill/replication hợp lệ cần điều khiển trigger firing, nhưng phải có runbook gồm backup, lock budget, quyền, validation sau thao tác và rollback. Không dùng một mẹo chung cho mọi bảng.

---

## 36. Quyền, SECURITY DEFINER và search_path

### 36.1. Trigger function chạy dưới quyền nào?

PL/pgSQL functions mặc định có `SECURITY INVOKER`. Một trigger function có thể được định nghĩa `SECURITY DEFINER`, dùng quyền của function owner khi thực thi.

### 36.2. SECURITY DEFINER là một ranh giới đặc quyền

Ví dụ function dùng quyền owner để ghi audit table mà caller không được INSERT trực tiếp. Đây có thể là thiết kế có chủ đích, nhưng nếu function được viết sai, caller có thể lợi dụng để đọc/ghi dữ liệu vượt quyền.

### 36.3. Harden SECURITY DEFINER

Một pattern minh họa:

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_secure_example()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, trigger_order_lab, pg_temp
AS $$
BEGIN
    -- Dùng schema-qualified references cho relations nhạy cảm.
    INSERT INTO trigger_order_lab.fire_log
      (trigger_name,timing,operation,item_id)
    VALUES
      (TG_NAME,TG_WHEN,TG_OP,NEW.item_id);

    RETURN NEW;
END;
$$;
~~~

Không tự chuyển toàn bộ triggers thành SECURITY DEFINER chỉ vì caller thiếu quyền audit. Cần:

- Owner ít quyền, không superuser nếu không cần.
- Search path an toàn, không cho untrusted schema shadow objects.
- Không ghép dynamic SQL từ input.
- Kiểm tra quyền CREATE/TRIGGER/EXECUTE/ALTER ở thời điểm triển khai.
- Giám sát bypass RLS và quyền bảng nền.
- Chỉ log các fields được phép.
- Review schema/role grants và deployments.

### 36.4. EXECUTE privilege và trigger creation

Để tạo trigger gọi một trigger function, người tạo trigger cần các quyền phù hợp, bao gồm `TRIGGER` privilege trên relation và `EXECUTE` trên function theo quy tắc PostgreSQL. Không giả định một `REVOKE EXECUTE` sau này tự vô hiệu hóa mọi trigger đã tồn tại; cần quản lý đối tượng trigger và quyền trực tiếp.

### 36.5. Trigger không có quyền tự COMMIT một phần

Dù SECURITY DEFINER, trigger function vẫn thuộc transaction context của DML caller. Đặc quyền function không biến INSERT audit thành một transaction độc lập với rollback của caller.

---

## 37. Những lỗi và ngộ nhận phổ biến

| Sai lầm/ngộ nhận | Hậu quả | Hiểu đúng |
|---|---|---|
| Trigger chạy theo thứ tự CREATE | Validator có thể chạy trước normalizer | Cùng timing/event/level sắp theo tên |
| Trigger tên khác luôn có global order | Nhầm giữa BEFORE và AFTER, row và statement | Timing/level/sự kiện quyết định nhóm |
| ORDER BY trong UPDATE ép thứ tự row triggers | Dựa vào row order không được bảo đảm | Thiết kế set-based/khóa |
| AFTER trigger chạy sau COMMIT | Gửi email rồi transaction rollback | AFTER vẫn trong transaction |
| BEFORE trigger RETURN NEW sẽ không qua trigger tiếp theo | Bỏ qua validation/audit | BEFORE sau đó có thể thấy NEW đã sửa |
| BEFORE trigger RETURN NULL là lỗi | Caller không nhận exception dù row bị skip | Nó hủy thao tác trên row |
| AFTER trigger RETURN NEW làm row thay đổi | Dữ liệu không đổi như mong đợi | Return AFTER bị bỏ qua |
| Một BEFORE audit log nghĩa row đã được INSERT | Row có thể bị skip sau đó | Audit ở AFTER/outbox phù hợp |
| UPDATE timestamp trong AFTER trên chính bảng vô hại | Nested UPDATE có thể đệ quy | Sửa NEW trong BEFORE ROW |
| pg_trigger_depth()>1 luôn là recursion lỗi | Bỏ qua FK cascade/nested hợp lệ | Dựa vào business state và event identity |
| pg_trigger_depth()=1 nghĩa không có vòng lặp | Loop có thể qua nhiều transactions | Idempotency/reconciliation |
| OLD <> NEW luôn phát hiện thay đổi nullable | NULL tạo UNKNOWN | IS DISTINCT FROM |
| UPDATE OF cột chỉ chạy khi giá trị khác | SET col=col vẫn kích hoạt | Dùng WHEN OLD IS DISTINCT FROM NEW |
| BEFORE trigger sửa cột làm UPDATE OF cột đó kích hoạt | Column list phản ánh SET clause | Dùng AFTER UPDATE + WHEN nếu cần |
| Statement trigger chỉ chạy khi ảnh hưởng row | UPDATE 0 rows vẫn có statement triggers | Đừng suy success từ trigger firing |
| AFTER ROW triggers cho mọi rows theo PK order | Row processing không có thứ tự ổn định | Không dựa vào row order |
| Constraint AFTER luôn chạy ngay | DEFERRABLE có thể trì hoãn | Đọc DEFERRABLE và SET CONSTRAINTS |
| WHEN của deferred trigger cũng chờ tới commit | WHEN được xét tại event time | Function có thể deferred |
| FK cascade không kích hoạt user triggers | DELETE/UPDATE phụ thuộc có triggers | Xem nested DML graph |
| UPSERT conflict chỉ có UPDATE trigger | BEFORE INSERT cũng có thể chạy | Phân tích ON CONFLICT semantics |
| UPSERT statement UPDATE trigger chứng minh row UPDATE | DO UPDATE có thể tác động 0 row | Đếm rows thực tế |
| TRUNCATE kích hoạt DELETE ROW audit | Audit bị bỏ qua | TRUNCATE STATEMENT riêng |
| Partitioned parent row trigger giống standalone không có clone | Bỏ qua leaf/row movement | Kiểm tra partition semantics |
| RETURN NULL của INSTEAD OF trigger chỉ giống AFTER | Sai row count/handled semantics | INSTEAD OF tự thực hiện DML |
| NOTIFY là queue durable | Mất event nếu client offline | Outbox + optional NOTIFY |
| Sequence ID liên tục là yêu cầu bảo mật | Gaps tự nhiên sau rollback | Không suy từ gaps |
| Email từ trigger sẽ rollback với SQL | Email vẫn đã gửi | Outbox/idempotency |
| AFTER audit tồn tại dù transaction rollback | Audit row rollback | Cùng transaction |
| Disable Trigger ALL là sửa recursion | Bỏ FK/audit/constraints | Sửa logic, không bypass |
| Exception handler WHEN OTHERS RETURN NEW luôn an toàn | Che trạng thái sai | Catch cụ thể hoặc rethrow |
| EXPLAIN ANALYZE UPDATE chỉ giả lập | UPDATE/triggers chạy thật | Transaction test, thận trọng side effects |
| Có index thì trigger UPDATE hàng loạt rẻ | Row-by-row side effects có thể đắt | Đo lock/WAL/timing |
| Audit trigger ghi full NEW luôn đúng | Rò PII, dữ liệu dư thừa | Chỉ lưu fields cần |
| SECURITY DEFINER trigger luôn an toàn | Có thể nâng quyền, search_path attack | Least privilege, hardening |
| Đổi tên trigger là thay đổi chỉ để dễ đọc | Có thể đổi thứ tự gọi | Regression tests |
| Rule và trigger là một cơ chế | Rewrite khác trigger execution | Phân biệt CREATE RULE/CREATE TRIGGER |

---

## 38. Checklist review một trigger có side effects

### 38.1. Sự kiện và thứ tự

- [ ] Relation target và event loại nào?
- [ ] BEFORE/AFTER/INSTEAD OF, ROW/STATEMENT?
- [ ] Có nhiều triggers cùng timing/event không? Đã xem alphabetical order?
- [ ] Trigger có phụ thuộc giá trị NEW do trigger trước sửa không?
- [ ] Có WHEN predicate, UPDATE OF columns, return semantics phù hợp?
- [ ] Có zero-row statements và multi-row DML?

### 38.2. Đệ quy và điều kiện dừng

- [ ] Function chạy INSERT/UPDATE/DELETE trên bảng nào?
- [ ] Có bảng nào chứa trigger viết ngược về source?
- [ ] Có FK cascades, partition movement, UPSERT, MERGE tạo event bất ngờ?
- [ ] Có chứng minh một vòng lặp kết thúc theo dữ liệu/business state?
- [ ] Có dùng `IS DISTINCT FROM` cho nullable fields?
- [ ] Logic có idempotency trước retry không?
- [ ] `pg_trigger_depth()` chỉ để debug hay đang che mất nested valid flows?

### 38.3. Transaction và external side effects

- [ ] Audit/outbox SQL cùng transaction có đúng nhu cầu?
- [ ] Có HTTP/email/extension write nào không rollback được không?
- [ ] NOTIFY có bị coi sai là durable queue không?
- [ ] Có sequence gaps/transaction rollback được hiểu đúng không?
- [ ] Có exception handler nuốt lỗi làm data drift không?
- [ ] Có worker/outbox và duplicate-delivery handling?
- [ ] Có ROLLBACK path cho migration và tests?

### 38.4. Hiệu năng và quyền

- [ ] Batch DML có trigger row-by-row tốn kém không?
- [ ] Có cơ hội dùng transition tables/statement-level aggregation?
- [ ] Có hot-row contention ở bảng tổng?
- [ ] Có index theo các WHERE bên trong trigger?
- [ ] Có thời gian khóa và khả năng deadlock?
- [ ] SECURITY DEFINER/INVOKER và search_path an toàn?
- [ ] Những cột audit/outbox có chứa thông tin nhạy cảm không?
- [ ] Có test dưới role ứng dụng thật không?

### 38.5. Triển khai

- [ ] Có catalog snapshot các triggers hiện có?
- [ ] Migration đổi tên có thay thứ tự execution không?
- [ ] Có tests INSERT/UPDATE/DELETE, UPSERT, zero rows, multi rows?
- [ ] Có tests rollback và failure giữa chừng?
- [ ] Có monitoring WAL/locks/calls/audit drift?
- [ ] Có kế hoạch rollback mà không tắt FK/internal triggers?
- [ ] Có reconciliation job khi derived data có thể sai lệch?

---

## 39. Tình huống 1 — Đơn hàng cập nhật customer totals

### Bối cảnh

Đơn hàng có `status`, `customer_id`, `amount`. Báo cáo cần `customer_totals.total_paid`.

Một hướng naïve: AFTER UPDATE orders tính tổng lại và UPDATE customers; AFTER UPDATE customers cập nhật flag của các orders. Hai trigger có thể hình thành vòng lặp.

### Cách thiết kế tốt hơn

1. **Nguồn dữ liệu chuẩn:** orders.
2. Bảng totals chỉ chứa projection.
3. Chỉ cho một đường đồng bộ **orders → totals**, không ghi ngược orders từ trigger totals.
4. Trigger chỉ chạy khi `status/amount/customer_id` đổi thực sự.
5. Với batch lớn, xét statement-level transition tables và aggregation.
6. Có reconciliation query `SELECT customer_id, SUM(amount) FROM orders WHERE status='paid' GROUP BY customer_id`.
7. Chạy trong transaction và kiểm tra concurrent updates, especially hot customer IDs.

Nếu cần business event “customer reaches VIP threshold”, phát một **outbox event** riêng khi threshold transition xảy ra, không phản xạ cập nhật orders qua nhiều trigger.

---

## 40. Tình huống 2 — Đồng bộ updated_at

### Yêu cầu

Mỗi lần business fields đổi, gán `updated_at`, nhưng không tạo recursion.

### Lựa chọn hợp lý

Một **BEFORE UPDATE FOR EACH ROW** function sửa `NEW.updated_at`, có `WHEN` so sánh những business columns thật sự thay đổi; không chạy UPDATE lại cùng bảng.

~~~sql
-- Dạng khung; chọn columns nghiệp vụ thực của bảng.
IF OLD.name IS DISTINCT FROM NEW.name
   OR OLD.status IS DISTINCT FROM NEW.status THEN
    NEW.updated_at := clock_timestamp();
END IF;

RETURN NEW;
~~~

Không dùng AFTER trigger tự UPDATE row đang xử lý để gán timestamp. Nếu có các BEFORE triggers khác chuẩn hóa dữ liệu, phải kiểm tra **thứ tự trigger** và việc so giá trị trước/sau chuẩn hóa.

---

## 41. Tình huống 3 — Event gửi email sau thanh toán

### Thiết kế nguy hiểm

AFTER UPDATE payments trigger gọi HTTP gửi email. Giao dịch sau đó lỗi và rollback; email vẫn được gửi. Retry còn có thể gửi lần nữa.

### Thiết kế an toàn hơn

- Chỉ phát sự kiện khi payment có **chuyển trạng thái thực sự** sang paid.
- Ghi vào outbox với business event ID độc nhất trong cùng DB transaction.
- Worker đọc các events đã commit, gửi email idempotently.
- Mark processed/attempts; retry nếu lỗi.
- Dùng NOTIFY để đánh thức worker nếu muốn, nhưng không làm nguồn sự thật.
- Giữ thông tin thanh toán nhạy cảm ngoài payload nếu consumer không cần.
- Không phát nhiều events chỉ vì một UPSERT làm cả BEFORE INSERT và AFTER UPDATE triggers chạy.

### SQL predicate cho status transition

~~~sql
-- Áp trên bảng payments khi có schema thực:
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'paid'
)
~~~

`WHEN` có thể tránh queue AFTER ROW event khi trạng thái không đổi. Còn đúng **một business event** vẫn cần idempotency/unique key và cách xử lý retry ngoài DB.

---

## 42. Bài tập thực hành

Các bài dùng `trigger_order_lab` trong tài liệu nếu không nói khác. Một số bài yêu cầu viết DDL **để phân tích**, không nhất thiết chạy ngay: có ví dụ tạo trigger trùng nhiệm vụ của lab, thay đổi audit data hoặc đụng đến thao tác phá hủy. Chỉ chạy trong database thử nghiệm riêng, kiểm tra dependency và dùng transaction có ROLLBACK khi phù hợp. Nếu chạy những phần DML trước đó, trạng thái dữ liệu có thể khác kết quả ban đầu.

### Bài 1 — Thứ tự cùng loại

Bảng có ba BEFORE UPDATE ROW triggers tên `b_50_c`, `b_10_a`, `b_20_b` được tạo theo thứ tự c, a, b. Chúng chạy theo thứ tự nào khi cập nhật một row?

### Bài 2 — Thứ tự khác timing

Bảng có `z_before` BEFORE UPDATE ROW và `a_after` AFTER UPDATE ROW. Tên `a_after` đứng trước theo alphabet, nó có được chạy trước `z_before` không? Vì sao?

### Bài 3 — Statement 0 rows

`UPDATE items SET quantity=quantity+1 WHERE item_id=-99` không khớp row. Những trigger nào trong lab vẫn chạy nếu có statement-level UPDATE triggers? Row-level UPDATE triggers có chạy không?

### Bài 4 — Mỗi row nhiều trigger

Một UPDATE tác động 100 rows, có hai BEFORE ROW, một AFTER ROW, một BEFORE STATEMENT và một AFTER STATEMENT trigger đều phù hợp. Số lời gọi tối đa (không tính nested SQL, row cancel và WHEN) theo từng loại?

### Bài 5 — NEW đi qua nhiều BEFORE triggers

`b_10_normalize` đổi code `' alpha '` thành `'ALPHA'`. `b_20_validate` sẽ thấy string nào? Nếu đổi tên validator thành `b_05_validate`, điều gì có thể khác?

### Bài 6 — RETURN NULL của BEFORE

Một BEFORE INSERT trigger đầu tiên ghi log, trigger thứ hai `RETURN NULL` khi quantity=0. Item có được INSERT không? Log của trigger đầu có thể vẫn còn nếu transaction COMMIT không?

### Bài 7 — AFTER RETURN NEW

Một AFTER UPDATE trigger làm `NEW.quantity := 10; RETURN NEW;`. Điều này có sửa quantity của row đã UPDATE không? Cách nào phù hợp nếu muốn sửa trước khi ghi?

### Bài 8 — BEFORE DELETE

Với DELETE row trigger, dùng `OLD` hay `NEW` để xem hàng bị xóa? Return gì để cho phép DELETE tiếp tục? Return gì để bỏ DELETE row?

### Bài 9 — Trigger function context

Viết PL/pgSQL dùng `TG_NAME`, `TG_WHEN`, `TG_OP`, `TG_TABLE_NAME` và `pg_trigger_depth()` để in một notice chẩn đoán.

### Bài 10 — Timestamp recursion

Vì sao một AFTER UPDATE trigger tự `UPDATE items SET updated_at=clock_timestamp() WHERE id=NEW.id` có thể tạo vòng lặp? Viết pattern không cần UPDATE lần hai.

### Bài 11 — NULL-safe comparison

Viết condition kiểm tra `OLD.note` và `NEW.note` thật sự khác nhau kể cả khi một bên NULL.

### Bài 12 — UPDATE OF

`AFTER UPDATE OF note` có chạy khi `SET note=note` không? Nếu BEFORE trigger đổi note nhưng statement chỉ SET quantity, UPDATE OF note có tự chạy không?

### Bài 13 — WHEN guard

Viết AFTER UPDATE ROW trigger chỉ chạy khi `quantity` thực sự đổi. Chỉ ra khác biệt giữa `UPDATE OF quantity` và `WHEN (OLD.quantity IS DISTINCT FROM NEW.quantity)`.

### Bài 14 — Tên trigger và migration

Vì sao đổi tên một trigger có thể là thay đổi hành vi? Nêu hai biện pháp giảm rủi ro.

### Bài 15 — Quan sát depth

`pg_trigger_depth()` ở ngoài trigger thường bằng bao nhiêu? Ở trigger top-level và trigger chạy do nested UPDATE thường là bao nhiêu?

### Bài 16 — Guard depth>1

Vì sao `IF pg_trigger_depth()>1 THEN RETURN NEW; END IF;` có thể làm mất chức năng hợp lệ của một FK cascade hoặc trigger đồng bộ?

### Bài 17 — Tránh đệ quy với condition

Một trigger orders UPDATE customer_totals, trigger totals UPDATE orders.sync_flag, từ đó orders trigger lại tính totals. Hãy đề xuất một điều kiện hoặc thay đổi graph cắt vòng lặp.

### Bài 18 — Termination proof

Đưa ra một invariant hoặc đại lượng giảm/tăng tới bound để chứng minh một chuỗi nested triggers có điểm dừng, khác với chỉ dựa vào timeout.

### Bài 19 — Row order

Một UPDATE không có ORDER BY tác động 10.000 rows. Có thể dựa vào thứ tự kích hoạt AFTER ROW triggers để gán số thứ tự nghiệp vụ theo primary key không? Vì sao?

### Bài 20 — Transition tables

Viết một AFTER UPDATE FOR EACH STATEMENT trigger dùng `REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows` và đếm rows mà quantity đã thực sự đổi.

### Bài 21 — Hạn chế transition tables

Trigger `AFTER UPDATE OF quantity ... REFERENCING OLD TABLE/NEW TABLE` có hợp lệ như một trigger trên cùng relation không? Tại sao phải bỏ column list trong mẫu này?

### Bài 22 — Constraint trigger deferred

Giải thích khác nhau giữa ordinary AFTER ROW trigger và `CREATE CONSTRAINT TRIGGER ... DEFERRABLE INITIALLY DEFERRED`. Khi nào function của constraint trigger có thể được gọi?

### Bài 23 — WHEN trên deferred trigger

Nếu một deferred constraint trigger có WHEN, điều kiện WHEN được kiểm tra ngay khi event phát sinh hay chờ cuối transaction?

### Bài 24 — SET CONSTRAINTS

Viết một transaction có `SET CONSTRAINTS ct_item_probe IMMEDIATE` và giải thích tác động đến pending trigger events khi chuyển từ deferred sang immediate.

### Bài 25 — FK CASCADE

Parent–child có `ON DELETE CASCADE`, child có AFTER DELETE ROW audit trigger. Khi DELETE parent, audit child có thể chạy không? Lý do?

### Bài 26 — TRUNCATE và DELETE

Vì sao một trigger AFTER DELETE ROW không audit đầy đủ hành động `TRUNCATE TABLE items`? Cần loại trigger nào để bắt sự kiện TRUNCATE?

### Bài 27 — UPSERT trigger paths

Với `INSERT ... ON CONFLICT DO UPDATE`, vì sao một row conflict có thể đi qua BEFORE INSERT và BEFORE UPDATE ROW triggers? Tác động đến chuẩn hóa input và audit?

### Bài 28 — UPSERT không update row

`ON CONFLICT DO UPDATE ... WHERE false` có thể vẫn khiến statement-level UPDATE trigger chạy không? Có thể dựa trên sự kiện đó để xác nhận một row đã được cập nhật không?

### Bài 29 — Partition movement

Một UPDATE đổi partition key và row chuyển từ leaf tháng 10 sang leaf tháng 11. Các row triggers nguồn/đích có thể khác một UPDATE thông thường ở điểm nào?

### Bài 30 — INSTEAD OF VIEW

Một INSTEAD OF UPDATE trigger trên view chỉ `RETURN NEW` và không chạy UPDATE bảng nền. Row có tự được cập nhật không? Nếu function cập nhật bảng nền, có thể phát sinh nested base-table triggers không?

### Bài 31 — External HTTP

AFTER UPDATE trigger gửi email rồi transaction rollback. Email có tự thu hồi không? Đề xuất một kiến trúc giảm inconsistency.

### Bài 32 — pg_notify

`pg_notify()` trong transaction rollback có phát notification không? Vì sao `LISTEN/NOTIFY` không thay durable outbox?

### Bài 33 — Sequence gaps

Một trigger INSERT audit dùng identity, transaction sau đó rollback. Vì sao log_id mới có thể bị nhảy số dù audit row không còn?

### Bài 34 — BEFORE audit và AFTER audit

Khi một BEFORE INSERT trigger ghi audit rồi row bị skip bởi trigger khác RETURN NULL, kết quả audit khác gì so với AFTER INSERT ROW trigger thông thường?

### Bài 35 — Exception handler

Một trigger bắt `WHEN OTHERS` và trả NEW dù INSERT vào bảng tổng thất bại. Dữ liệu nào có thể bị sai lệch? Nên xử lý thế nào nếu bảng tổng phải nhất quán transactionally?

### Bài 36 — Catalog triggers

Viết query liệt kê tên trigger, relation, function và `pg_get_triggerdef` trong schema `trigger_order_lab`, phân biệt internal triggers.

### Bài 37 — tgenabled

Giải thích các giá trị `O`, `D`, `R`, `A` của `pg_trigger.tgenabled`. Vì sao không đặt `session_replication_role='replica'` để né recursion?

### Bài 38 — EXPLAIN ANALYZE

Tại sao `EXPLAIN (ANALYZE, BUFFERS) UPDATE ...` vẫn có side effects? Bọc trong transaction ROLLBACK có khôi phục toàn bộ email/sequence đã cấp không?

### Bài 39 — SECURITY DEFINER

Một trigger function SECURITY DEFINER ghi audit. Nêu ít nhất năm biện pháp hardening trước khi cấp quyền cho ứng dụng không tin cậy.

### Bài 40 — Aggregate contention

Mỗi INSERT order kích hoạt UPDATE cùng một row customer_totals. Với 10.000 orders/giây cho cùng customer, vấn đề gì có thể phát sinh? Nêu hai phương án giảm áp lực.

### Bài 41 — Rule khác trigger

`CREATE RULE` và `CREATE TRIGGER` có cùng thời điểm thực thi và alphabetical order không? Vì sao chuyển một trigger vòng lặp thành rule chưa chắc sửa lỗi?

### Bài 42 — Phân loại giải pháp

Ghép từng vấn đề với hướng xử lý chính:
1. AFTER trigger tự sửa timestamp trên cùng row.
2. Hai tables update qua lại nhưng không đổi business state.
3. Email gửi trước khi transaction commit.
4. Mỗi 1 triệu row UPDATE lại cập nhật bảng tổng một lần.
5. Audit bị ghi trùng khi API retry.

### Bài 43 — Thiết kế full workflow

Hệ thống bán hàng có `orders` và `customer_totals`, cần audit mọi lần chuyển status sang paid và phát webhook cho đối tác. Đề xuất một kiến trúc dùng trigger đúng timing, không tạo vòng lặp, transactionally atomic đối với DB, và chống webhook duplicate.

### Bài 44 — Debug vòng lặp production

Một UPDATE từ API gây CPU/locks tăng đột biến và lỗi stack depth. Trình bày một runbook an toàn để xác định trigger graph, khoanh vùng nguyên nhân, rollback deployment, bảo vệ dữ liệu và xây regression tests. Không tắt constraint triggers để thử.

### Bài 45 — Tổng hợp đặc biệt

Một câu SQL `INSERT ... ON CONFLICT DO UPDATE` nhắm parent partitioned table có triggers ở parent, child, một FK cascade, outbox AFTER ROW và constraint trigger deferrable. Vì sao không thể khẳng định “trigger luôn chạy theo một thứ tự tên duy nhất và sau đó chắc chắn gửi webhook”? Hãy nêu các lớp timing, routing, nested DML, deferral và COMMIT cần xét.

---

## 43. Hướng dẫn lời giải — bài 1 đến 20

### Bài 1 — Thứ tự tên

Ba BEFORE UPDATE ROW triggers cùng điều kiện sẽ chạy theo **b_10_a → b_20_b → b_50_c**, không theo thứ tự CREATE. PostgreSQL sắp tên trong nhóm trigger cùng event/timing/relation.

### Bài 2 — Timing trước tên

Không. `z_before` vẫn là BEFORE ROW, chạy ở giai đoạn trước khi row được UPDATE; `a_after` thuộc AFTER ROW, chạy sau thao tác row theo semantics AFTER. Name ordering không trộn các giai đoạn.

### Bài 3 — UPDATE 0 rows

Các **BEFORE UPDATE FOR EACH STATEMENT** và **AFTER UPDATE FOR EACH STATEMENT** phù hợp vẫn có thể chạy (trong lab có `s_10_before_update`, `s_90_after_update` và các statement triggers thêm sau). Không có row nào bị cập nhật nên row-level UPDATE triggers không có row để gọi.

### Bài 4 — Số lần gọi

Khi không có row skip, nested DML hoặc WHEN false:

- BEFORE STATEMENT: **1**.
- BEFORE ROW: **2 × 100 = 200**.
- AFTER ROW: **1 × 100 = 100**.
- AFTER STATEMENT: **1**.

Tổng là 302 trigger-function invocations theo giả thiết. Nếu BEFORE row RETURN NULL hoặc có triggers khác, con số thay đổi.

### Bài 5 — Dòng NEW

`b_20_validate` nhìn thấy `NEW.code='ALPHA'` do `b_10_normalize` đã sửa. Đổi validator thành `b_05_validate` có thể khiến validator thấy chuỗi gốc `' alpha '` trước khi chuẩn hóa; logic validation có thể khác.

### Bài 6 — Skip row và log

Row quantity=0 bị BEFORE trigger trả NULL nên không INSERT. Nếu trigger đầu đã ghi một row log SQL và sau đó không có exception, log **có thể vẫn được commit** vì RETURN NULL không tự rollback những SQL đã thực hiện. Vì vậy BEFORE audit không phải bằng chứng row được lưu.

### Bài 7 — Return AFTER

Không. Return value của AFTER ROW trigger bị bỏ qua. Để sửa row trước khi được ghi, thay `NEW.quantity` trong BEFORE INSERT/UPDATE ROW và `RETURN NEW`. Nếu phải sửa bằng AFTER UPDATE trên cùng bảng, cần tránh recursive UPDATE có guard, nhưng đa số timestamp/normalize cases phù hợp BEFORE hơn.

### Bài 8 — DELETE

`OLD` chứa row trước DELETE, `NEW` không dùng cho row DELETE thông thường. Với BEFORE DELETE, trả non-NULL (thường `RETURN OLD`) để cho phép xóa, hoặc `RETURN NULL` để bỏ row delete. Nếu muốn báo vi phạm nghiệp vụ, có thể `RAISE EXCEPTION` thay vì im lặng bỏ row.

### Bài 9 — Diagnostic notice

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_log_context()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE NOTICE 'name=%, timing=%, event=%, table=%, depth=%',
        TG_NAME,TG_WHEN,TG_OP,TG_TABLE_NAME,pg_trigger_depth();

    IF TG_OP='DELETE' THEN
        RETURN OLD;
    ELSIF TG_LEVEL='ROW' THEN
        RETURN NEW;
    END IF;

    RETURN NULL;
END;
$$;
~~~

Đây là mẫu function có thể dùng cho các event types; khi tạo trigger cụ thể, xem timing/return semantics để không ghi Notice quá nhiều trên batch production.

### Bài 10 — Timestamp update

AFTER UPDATE trên items tự UPDATE items khiến nested UPDATE có thể lại kích hoạt cùng AFTER trigger, không có điểm dừng. Mẫu đúng:

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_touch_answer()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;
~~~

Gắn BEFORE UPDATE ROW khi phù hợp. Nếu muốn chỉ update timestamp lúc business fields đổi, thêm `WHEN`/IF với `IS DISTINCT FROM`.

### Bài 11 — So sánh NULL-safe

~~~sql
OLD.note IS DISTINCT FROM NEW.note
~~~

Kết quả TRUE khi một bên NULL một bên có giá trị, hoặc hai giá trị khác; FALSE nếu cả hai NULL hoặc bằng nhau. Không dùng `<>` trên nullable fields làm guard duy nhất.

### Bài 12 — UPDATE OF

`UPDATE OF note` có thể chạy khi `SET note=note` vì column được nhắc trong SET clause. Nếu UPDATE chỉ nhắc quantity, BEFORE trigger khác đổi NEW.note thì `UPDATE OF note` **không tự được kích hoạt** chỉ vì thay đổi do trigger tạo.

### Bài 13 — WHEN guard

~~~sql
CREATE TRIGGER a_50_quantity_value_changed
AFTER UPDATE ON trigger_order_lab.items
FOR EACH ROW
WHEN (OLD.quantity IS DISTINCT FROM NEW.quantity)
EXECUTE FUNCTION trigger_order_lab.fn_audit_after();
~~~

`UPDATE OF quantity` dựa trên column có trong SET list; `WHEN` ở đây dựa trên giá trị OLD/NEW thực tế. Có thể kết hợp, nhưng nếu cần bắt mọi thay đổi do BEFORE triggers gây ra kể cả khi column không nằm trong SET, dùng AFTER UPDATE không OF list và WHEN.

### Bài 14 — Đổi tên ảnh hưởng thứ tự

Nếu two BEFORE ROW triggers phụ thuộc nhau, rename có thể thay alphabetical order và dẫn đến validation/normalization khác. Hai biện pháp:

1. Đặt tên có prefix thứ tự và review rename migration như thay đổi logic.
2. Gộp logic phụ thuộc chặt vào một trigger function hoặc viết integration tests khẳng định kết quả.

### Bài 15 — Depth

`pg_trigger_depth()` ở ngoài trigger thường 0; trong trigger trực tiếp từ DML top-level thường 1; trigger được gọi do DML lồng trong trigger khác có thể 2 hoặc cao hơn. Đây là chỉ số call stack hiện tại, không phải thứ tự thời gian giữa transactions.

### Bài 16 — Depth guard có thể chặn nghiệp vụ hợp lệ

Trigger từ FK cascade, partition-related DML hoặc một trigger khác có thể chạy ở depth>1 nhưng vẫn là một event hợp lệ. Guard kiểu `IF depth>1 THEN RETURN NEW` có thể làm mất audit và validation. Với DELETE cần trả OLD nếu muốn cho phép; return NEW có thể không đúng event. Thay vào đó dùng business state/WHEN/idempotency và graph analysis.

### Bài 17 — Cắt vòng lặp orders↔totals

Một phương án: trigger orders chỉ chạy khi `OLD.status IS DISTINCT FROM NEW.status` hoặc các business fields thay đổi, không chạy khi chỉ cập nhật `sync_flag`. Tốt hơn: duy trì totals là projection **một chiều** từ orders, bỏ trigger totals ghi ngược orders. Chỉ UPDATE totals nếu giá trị mới thật sự khác bằng `IS DISTINCT FROM`.

### Bài 18 — Chứng minh kết thúc

Một đại lượng ví dụ: `remaining_steps = 3 - val` luôn giảm mỗi nested UPDATE khi `val<3`; khi val=3, predicate không thực hiện UPDATE nữa. Nếu dữ liệu được bảo vệ bởi constraint 0≤val≤3, chuỗi có tối đa số bước hữu hạn theo bound. Timeout không chứng minh tính đúng; cần guard trên dữ liệu thật.

### Bài 19 — Không có row order ổn định

Không. SQL update nhiều rows không bảo đảm hàng có PK nhỏ hơn được xử lý trước, nên AFTER ROW trigger firing sequence không phải ordering contract. Nếu cần thứ tự nghiệp vụ, dùng version/sequence được cấp theo cơ chế nghiệp vụ riêng, có constraint/locking đảm bảo semantics thích hợp.

### Bài 20 — Transition tables

~~~sql
CREATE OR REPLACE FUNCTION trigger_order_lab.fn_count_quantity_delta()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_changed bigint;
BEGIN
    SELECT count(*) INTO v_changed
    FROM old_rows AS o
    JOIN new_rows AS n USING (item_id)
    WHERE o.quantity IS DISTINCT FROM n.quantity;

    RAISE NOTICE 'changed rows=%',v_changed;
    RETURN NULL;
END;
$$;

CREATE TRIGGER s_75_quantity_batch
AFTER UPDATE ON trigger_order_lab.items
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_count_quantity_delta();
~~~

Một UPDATE statement có thể tác động nhiều hàng; trigger chỉ gọi một lần và đếm changed rows từ transition relations. Khi không có rows, count=0.

---

## 44. Hướng dẫn lời giải — bài 21 đến 45

### Bài 21 — UPDATE OF không kết hợp trực tiếp transition tables

Khi dùng transition tables cho UPDATE trigger theo cấu hình được hỗ trợ, PostgreSQL không cho chỉ định column list `UPDATE OF quantity` trên cùng trigger. Cần:

~~~sql
CREATE TRIGGER s_85_count_quantity
AFTER UPDATE ON trigger_order_lab.items
REFERENCING OLD TABLE AS old_rows NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_count_updated_items();
~~~

Bên trong function, lọc những rows thật sự có `OLD.quantity IS DISTINCT FROM NEW.quantity`. Không nhất thiết mọi row trong transition table đều đổi quantity nếu UPDATE chỉ SET một cột khác.

### Bài 22 — Deferred constraint trigger

Ordinary AFTER ROW trigger được thực thi theo cơ chế AFTER của statement, **không** trở thành deferred chỉ vì có chữ AFTER. Constraint trigger khai báo `DEFERRABLE INITIALLY DEFERRED` có thể được queue để chạy vào thời điểm kiểm tra constraint muộn hơn, thường trước COMMIT, hoặc được kích hoạt sớm khi `SET CONSTRAINTS ... IMMEDIATE` hợp lệ.

### Bài 23 — WHEN được xét ngay

Điều kiện `WHEN` của một deferred constraint trigger được **đánh giá tại lúc row event phát sinh**. Nếu TRUE, event có thể được queue cho thời điểm deferred; nếu FALSE, không queue. Function thực sự chạy có thể nhìn thấy trạng thái DB đã thay đổi thêm so với lúc WHEN được xét.

### Bài 24 — SET CONSTRAINTS

~~~sql
BEGIN;

INSERT INTO trigger_order_lab.items
    (item_id,code,quantity)
VALUES (191,' deferred-check ',1);

SET CONSTRAINTS ct_item_probe IMMEDIATE;

ROLLBACK;
~~~

Nếu `ct_item_probe` tồn tại và đang deferred, đổi sang IMMEDIATE có thể khiến các pending events được xử lý ngay. Không có nghĩa COMMIT đã xảy ra. Việc ROLLBACK vẫn đảo các row changes trong transaction.

### Bài 25 — FK CASCADE gọi child triggers

Có. Khi FK `ON DELETE CASCADE` thực hiện DELETE child rows, nó tạo DML trên bảng child; DELETE triggers phù hợp trên child có thể được kích hoạt. Đây là nested action hợp lệ, nên guard `pg_trigger_depth()>1` có thể chặn audit của child một cách sai.

### Bài 26 — TRUNCATE không phải DELETE ROW

TRUNCATE không gọi DELETE FOR EACH ROW triggers để audit từng hàng. Nếu cần bắt lệnh, tạo:

~~~sql
CREATE TRIGGER s_before_truncate_answer
BEFORE TRUNCATE ON trigger_order_lab.items
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_order_lab.fn_trace_truncate();
~~~

Đây là **một trigger statement-level**, không cho từng row. Chỉ tạo nếu function đã tồn tại và không có trigger tương đương; không chạy TRUNCATE trên data cần giữ.

### Bài 27 — ON CONFLICT DO UPDATE

Một row đề xuất INSERT có thể qua BEFORE INSERT trigger, sau đó conflict được xử lý qua UPDATE và BEFORE UPDATE trigger của row conflict. `EXCLUDED` có thể mang những thay đổi từ BEFORE INSERT. Nếu normalize không idempotent, giá trị có thể bị xử lý hai lần; audit BEFORE INSERT có thể ghi event dù không INSERT row. Nên audit theo **thay đổi thực sự** và thiết kế idempotency cho events.

### Bài 28 — Statement-level UPDATE trigger không chứng minh UPDATE thành công

Có, với `ON CONFLICT DO UPDATE`, statement-level UPDATE trigger có thể chạy dù UPDATE action không thật sự tác động row nào vì điều kiện conflict/update WHERE. Đừng kết luận “đã cập nhật row” chỉ từ việc AFTER UPDATE STATEMENT trigger chạy; cần đo rows thực sự thay đổi và phân biệt các action.

### Bài 29 — Partition movement có event khác

Khi UPDATE làm row chuyển leaf:

- BEFORE UPDATE ROW có thể chạy trên partition nguồn.
- BEFORE INSERT ROW có thể chạy trên partition đích.
- AFTER row events tương ứng có thể là DELETE ở nguồn và INSERT ở đích, thay vì chỉ AFTER UPDATE ở một leaf.

Do đó audit chỉ gắn AFTER UPDATE trên leaf có thể bỏ sót một logical UPDATE dịch partition.

### Bài 30 — INSTEAD OF trigger cần làm công việc thật

Không. `RETURN NEW` của INSTEAD OF trigger không tự UPDATE base table. Function phải chạy DML thích hợp, ví dụ `UPDATE trigger_order_lab.items ... WHERE id=OLD.item_id`. DML bên trong kích hoạt triggers của base table và có thể tạo nested trigger execution. Cần tránh vòng view→base→view.

### Bài 31 — Email không rollback cùng database

Email đã gửi qua SMTP/API không được PostgreSQL tự thu hồi khi rollback. Thiết kế tốt hơn:

1. Trigger/app ghi outbox row trong cùng transaction của order/payment.
2. Worker chỉ đọc outbox đã commit.
3. Worker gửi email/webhook với idempotency key và retry policy.
4. Có bảng processed state/dedup, monitoring và dead-letter/incident handling.

### Bài 32 — NOTIFY và durability

`pg_notify()` gọi trong transaction rollback sẽ không phát notification đó. Nhưng LISTEN/NOTIFY không lưu durable queue đủ bảo đảm cho listener offline/restart và không có ack/retry semantics như broker. Dùng outbox là nguồn sự thật và NOTIFY chỉ là tín hiệu đánh thức worker nếu cần.

### Bài 33 — Sequence gap hợp lệ

`GENERATED AS IDENTITY` dùng sequence. PostgreSQL không rollback những sequence values đã được cấp khi transaction rollback. Log row có thể biến mất còn sequence đã tiến. Do đó `log_id` 1,2,5 không phải bằng chứng chắc chắn ai đó đã xóa logs 3,4.

### Bài 34 — BEFORE vs AFTER audit

BEFORE audit ghi log trước khi row thực sự được chấp nhận. Một BEFORE trigger sau trả NULL có thể skip row nhưng log trước đó vẫn commit nếu transaction thành công. AFTER INSERT ROW trigger không chạy cho row bị skip vì không có INSERT row hoàn tất ở mức statement. Tuy nhiên AFTER audit vẫn rollback nếu transaction bị rollback sau đó.

### Bài 35 — Bắt OTHERS và nuốt lỗi tạo sai lệch

Nếu trigger ghi projection thất bại và `WHEN OTHERS THEN RETURN NEW`, business row có thể được commit trong khi projection/audit thiếu hoặc lỗi logic không được xử lý. Nếu projection là invariant transaction bắt buộc, **đừng nuốt lỗi**: catch những lỗi có thể xử lý an toàn, còn lại `RAISE;` để transaction thất bại và rollback đồng bộ. Nếu projection eventual-consistency được chấp nhận, chuyển sang outbox/worker và có reconciliation.

### Bài 36 — Query catalog

~~~sql
SELECT
    t.tgname,
    t.tgrelid::regclass AS relation_name,
    t.tgfoid::regprocedure AS trigger_function,
    t.tgisinternal AS is_internal,
    t.tgenabled,
    pg_get_triggerdef(t.oid,true) AS definition
FROM pg_trigger AS t
JOIN pg_class AS c ON c.oid=t.tgrelid
JOIN pg_namespace AS n ON n.oid=c.relnamespace
WHERE n.nspname='trigger_order_lab'
ORDER BY relation_name::text,t.tgname;
~~~

Không lọc internal triggers khi mục tiêu là **hiểu FK/cascade graph**; có thể lọc `NOT t.tgisinternal` khi chỉ muốn user-defined triggers của app.

### Bài 37 — tgenabled và replication

- `O`: enabled trong origin/local.
- `D`: disabled.
- `R`: enabled trong replica role.
- `A`: always.

`session_replication_role='replica'` thay đổi rộng logic kích hoạt trigger/rules và có thể bỏ qua kiểm tra FK trong những trường hợp phù hợp; không dùng như mẹo sửa recursion. Phải sửa DML graph và conditions.

### Bài 38 — EXPLAIN ANALYZE UPDATE

EXPLAIN ANALYZE **thực thi** UPDATE và trigger functions. Bọc:

~~~sql
BEGIN;

EXPLAIN (ANALYZE,BUFFERS)
UPDATE trigger_order_lab.items
SET quantity=quantity+1
WHERE item_id=101;

ROLLBACK;
~~~

ROLLBACK đảo DB row changes trong transaction, nhưng **sequence values đã cấp** vẫn có thể có gaps; HTTP/email và side effects ngoài transaction không tự rollback. Không dùng trên production nếu trigger có external calls.

### Bài 39 — SECURITY DEFINER

Ít nhất năm biện pháp:

1. Function owner có ít quyền cần thiết, không superuser nếu tránh được.
2. `SET search_path` an toàn, schema-qualify objects.
3. Không đưa user input vào dynamic SQL không an toàn.
4. Chỉ cấp CREATE/TRIGGER/EXECUTE cho roles cần thiết.
5. Audit mọi bảng/function có thể bị đọc/ghi.
6. Kiểm tra RLS/BYPASSRLS/owner identity và privilege boundary.
7. Không log secret data/tokens qua RAISE hoặc audit.
8. Kiểm thử với caller roles thực; có regression test khi đổi owner/search_path.
9. Không viết function có thể bị dùng làm đường gọi side effects ngoài DB không kiểm soát.

### Bài 40 — Hot-row contention

Nhiều INSERT orders cùng UPDATE một row `customer_totals` khiến transactions tranh nhau row lock, tăng latency, lock waits, WAL và retry risk. Hai phương án:

- Dùng **statement-level transition tables** để gom delta theo customer cho mỗi batch và giảm số lần UPDATE tổng.
- Chuyển sang asynchronous projection/outbox/event processing hoặc sharded counters/bucketization nếu business cho phép eventual consistency.

Còn cần indexes, reconciliation và concurrency control. Không đánh đổi chính xác tổng mà không xác nhận yêu cầu nghiệp vụ.

### Bài 41 — Rules và triggers khác nhau

`CREATE RULE` là cơ chế **query rewrite** trước khi statement thực thi; trigger là cơ chế event-based execution theo thời điểm DML. Rule không tuân thứ tự alphabetical trigger names. Nếu thay vòng lặp trigger bằng rule, behavior có thể khác với DML/RETURNING/multi-row statements, không mặc định giảm rủi ro.

### Bài 42 — Ghép giải pháp

1. AFTER tự sửa timestamp trên cùng row → **BEFORE ROW sửa NEW**.
2. Hai tables update qua lại không đổi business state → **cắt một cạnh graph, WHEN/IS DISTINCT FROM, one-way projection**.
3. Email gửi trước commit → **transactional outbox + idempotent worker**.
4. Một triệu rows cập nhật bảng tổng từng row → **statement-level transition tables + set-based aggregation**, hoặc projection async.
5. Audit duplicate khi API retry → **business event ID + UNIQUE/idempotency**, không chỉ depth guard.

### Bài 43 — Workflow orders + totals + webhook

Một thiết kế minh họa:

~~~text
Ứng dụng UPDATE order.status new -> paid
           |
           v
AFTER UPDATE ROW trigger orders
 WHEN OLD.status IS DISTINCT FROM NEW.status
  AND NEW.status = 'paid'
           |
           +--> Cập nhật customer_totals (một chiều)
           |
           +--> INSERT order_audit (cùng transaction)
           |
           +--> INSERT outbox(event_id unique, order_id, status)
           |
           v
COMMIT thành công
           |
           v
Worker đọc outbox đã commit
           |
           +--> Gửi webhook idempotently
           |
           +--> Mark processed/retry/dead-letter
~~~

Yêu cầu chi tiết:

- Bảng `orders` là source-of-truth.
- Không có trigger totals ghi ngược orders.
- Trigger WHERE/WHEN chỉ cập nhật totals khi status/amount nghiệp vụ có thay đổi.
- Cần xử lý UPDATE amount sau paid, DELETE paid, hủy đơn, đổi customer... hoặc giữ totals theo query reconciliation đúng.
- Audit/outbox nằm trong cùng transaction; nếu lỗi constraint thì rollback cùng business row.
- Outbox có unique event identity; consumer có idempotency key.
- Webhook có thể bị gửi trùng khi worker retry, nên receiver cũng cần dedup.
- Chọn sync totals hay async projection tùy freshness/lock budget.

### Bài 44 — Runbook khi nghi recursion production

1. Ghi lại thời điểm lỗi, statement, role, relation và phiên bản deployment gần nhất; bảo vệ dữ liệu nhạy cảm trong logs.
2. Nếu sự cố đang ảnh hưởng lớn, dùng rollback deployment/feature flag được phê duyệt và kiểm soát traffic; **không tắt FK/internal triggers tùy tiện**.
3. Quan sát active sessions/locks/`pg_stat_activity` và query của backend có sự cố; xử lý cancellation theo quyền/runbook.
4. Đọc `pg_trigger`, `pg_get_triggerdef`, function definitions cho các bảng liên quan, bao gồm internal FK triggers khi cần.
5. Vẽ graph event→trigger→DML→event; xem đường A→B→A và các WHEN/UPDATE OF conditions.
6. Kiểm tra `pg_trigger_depth()` logging trong staging, không bật unlimited notices trên production.
7. Tái hiện trên dữ liệu lab/staging với transaction và timeout hợp lý.
8. Sửa guard theo business fields/`IS DISTINCT FROM`, cắt graph hoặc chuyển side effects sang outbox.
9. Thêm regression tests cho INSERT, UPDATE, DELETE, UPSERT, zero rows, batch, cascade, rollback và concurrency.
10. Triển khai có giám sát: query latency, lock waits, WAL, trigger calls, outbox backlog, audit drift.
11. Nếu trước đó có transaction lỗi, xác minh dữ liệu đã commit và side effects ngoài DB, không suy từ sequence gaps.
12. Đối chiếu totals/audit để phát hiện drift, phục hồi bằng quy trình dữ liệu được phê duyệt.

### Bài 45 — Nhiều lớp thứ tự trong một UPSERT partitioned table

Không thể gom thành “một danh sách trigger chạy theo alphabet” vì:

- **Statement-level** và **row-level** thuộc những pha riêng.
- **BEFORE**, **AFTER** và **constraint deferred** không cùng thời điểm.
- `ON CONFLICT DO UPDATE` có thể kích hoạt INSERT/UPDATE trigger paths khác nhau.
- Partition parent/leaf và row movement ảnh hưởng relation nào nhận row triggers.
- FK actions có thể tạo nested DELETE/UPDATE trên relations khác.
- `pg_trigger_depth()` phản ánh call stack, không phải thứ tự nghiệp vụ toàn cục.
- BEFORE trigger có thể sửa NEW hoặc RETURN NULL; AFTER trigger có thể ghi outbox SQL nhưng transaction vẫn rollback được.
- Constraint trigger deferred có thể được gọi sau nhiều statements, trước commit.
- Outbox row chỉ có giá trị tồn tại sau COMMIT; webhook do worker gửi **sau commit**, cần retry/idempotency.
- Trigger cùng event/timing/relation sẽ có thứ tự tên, nhưng điều này chỉ là **một phần** của toàn bộ execution graph.

---

## 45. Tài liệu tham khảo PostgreSQL

Các tài liệu chính thức nên đọc theo **major version thực tế** của server khi xây dựng thiết kế production:

- [PostgreSQL — Overview of Trigger Behavior](https://www.postgresql.org/docs/current/trigger-definition.html): BEFORE/AFTER, row/statement, transition relations, partitioning và trigger ordering.
- [PostgreSQL — CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): timing, events, `WHEN`, constraint trigger, `REFERENCING` và thứ tự trigger cùng loại.
- [PostgreSQL — PL/pgSQL Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html): `NEW`, `OLD`, `TG_OP`, `TG_WHEN` và return semantics.
- [PostgreSQL — Trigger Procedures](https://www.postgresql.org/docs/current/triggers.html): giải thích trigger functions và cơ chế kết hợp.
- [PostgreSQL — System Catalog pg_trigger](https://www.postgresql.org/docs/current/catalog-pg-trigger.html): `tgenabled`, `tgisinternal`, `tgfoid`, `tgrelid`.
- [PostgreSQL — CREATE TABLE / Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): FOREIGN KEY, CASCADE và constraints.
- [PostgreSQL — SET CONSTRAINTS](https://www.postgresql.org/docs/current/sql-set-constraints.html): thời điểm chuyển từ DEFERRED sang IMMEDIATE.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html): `ON CONFLICT DO UPDATE` và RETURNING.
- [PostgreSQL — MERGE](https://www.postgresql.org/docs/current/sql-merge.html): multi-action DML và trigger effects theo version.
- [PostgreSQL — Table Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html): row routing, partitioned trigger behavior.
- [PostgreSQL — LISTEN / NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html): transaction-aware notifications và giới hạn.
- [PostgreSQL — Sequence Manipulation Functions](https://www.postgresql.org/docs/current/functions-sequence.html): `nextval()` không rollback.
- [PostgreSQL — EXPLAIN](https://www.postgresql.org/docs/current/sql-explain.html): xem plan và đo trigger overhead khi phù hợp.
- [PostgreSQL — Function Security](https://www.postgresql.org/docs/current/perm-functions.html): permission và SECURITY DEFINER hardening.

Các đường dẫn `/current/` theo tài liệu mới nhất có thể không khớp phiên bản PostgreSQL đang chạy. Đặc biệt, MERGE, transition tables, partitioned triggers, các chi tiết concurrency/ON CONFLICT và quyền cần được xác minh trên major version triển khai.

---

## 46. Tổng kết

**Thứ tự trigger, đệ quy và vòng lặp tác dụng phụ là ba mặt của cùng một bài toán: một SQL statement có thể dẫn tới nhiều thao tác hơn những gì câu lệnh bên ngoài thể hiện.** Để thiết kế an toàn, cần phân biệt từng lớp:

1. **Thứ tự theo pha:** BEFORE STATEMENT, BEFORE ROW, thay đổi row, AFTER ROW, AFTER STATEMENT là sơ đồ cơ bản. Deferred constraint triggers còn có thể chạy muộn hơn.
2. **Thứ tự theo tên:** các triggers cùng timing/event/relation áp dụng theo alphabetical trigger-name order; tên trigger có thể ảnh hưởng việc BEFORE trigger sau nhìn thấy NEW thế nào.
3. **Không có thứ tự row nghiệp vụ mặc định:** một statement nhiều hàng không bảo đảm row triggers chạy theo primary key hoặc thứ tự INSERT.
4. **Return semantics:** BEFORE ROW có thể sửa NEW hoặc RETURN NULL để bỏ row; AFTER ROW return value bị bỏ qua; INSTEAD OF view phải thực thi DML thực sự.
5. **Nested DML:** SQL do trigger, FK cascade, UPSERT, partition movement hoặc INSTEAD OF view tạo ra có thể gọi triggers khác và hình thành graph đệ quy.
6. **Đệ quy cần điểm dừng theo dữ liệu:** dùng `IS DISTINCT FROM`, `WHEN`, điều kiện UPDATE, one-way projection và idempotency. `pg_trigger_depth()` hữu ích để quan sát, nhưng không thay business guard.
7. **Update timestamp nên làm ở BEFORE ROW bằng NEW:** không tự UPDATE lại cùng row trong AFTER mà thiếu một thiết kế dừng rõ ràng.
8. **UPDATE OF không phải “chỉ chạy khi giá trị đổi”:** nó phụ thuộc column được nhắc trong SET. Muốn so giá trị, dùng `WHEN OLD.field IS DISTINCT FROM NEW.field`.
9. **Statement-level trigger chạy khi statement tác động 0 row:** không lấy việc trigger được gọi làm bằng chứng INSERT/UPDATE/DELETE thành công.
10. **Transition tables** giúp tính aggregate theo tập rows với AFTER STATEMENT triggers khi được hỗ trợ, giảm row-by-row DML và lock contention.
11. **Constraint triggers deferred** có timing riêng; WHEN được xét ở event time, function có thể được queue tới thời điểm sau.
12. **Audit phải tính transaction boundary:** SQL audit/outbox trong trigger rollback cùng transaction, AFTER không phải after-commit.
13. **External side effects không rollback cùng PostgreSQL:** HTTP/email/webhooks cần transactional outbox, workers, idempotency và retry; NOTIFY chỉ là tín hiệu không bền vững.
14. **Sequence ID gaps là bình thường:** `nextval()` không rollback, không dùng gaps làm bằng chứng mất dữ liệu.
15. **Bảo trì/diagnostics:** đọc `pg_trigger`/`pg_get_triggerdef`, quan sát `pg_trigger_depth()` có giới hạn, đo `EXPLAIN ANALYZE` trong lab và kiểm tra locks, WAL, audit drift.
16. **Không sửa bằng cách tắt mọi triggers:** `DISABLE TRIGGER ALL` hoặc đổi replication role có thể bỏ FK, audit và business invariants.
17. **Quyền và chức năng:** SECURITY DEFINER trigger functions cần hardening; không lạm dụng đặc quyền để né lỗi logic.

Quy trình thiết kế ngắn: **xác định sự kiện/timing → liệt kê triggers theo tên và relation → vẽ mọi cạnh DML lồng nhau → chứng minh điểm dừng → loại SQL UPDATE ngược/không cần thiết → đặt side effects trong transaction hoặc outbox → thiết kế idempotency → kiểm thử 0/1/nhiều rows, UPSERT, FK cascade, partitions, rollback và concurrency → triển khai có catalog snapshot, monitoring và rollback plan**.
