# Tạo, vô hiệu hóa, xóa và kiểm thử trigger theo hệ quản trị SQL

**Trigger** là đoạn logic do hệ quản trị cơ sở dữ liệu tự kích hoạt khi một sự kiện phù hợp xảy ra trên bảng, view hoặc đối tượng được hỗ trợ. Chúng có thể ghi nhật ký thay đổi, đồng bộ dữ liệu phụ trợ, xác nhận quy tắc nghiệp vụ khó thể hiện bằng ràng buộc đơn giản hoặc thay thế cách thao tác với một view.

Điểm khó không chỉ nằm ở câu `CREATE TRIGGER`. Một trigger đã triển khai có thể:

- Chạy **một lần cho mỗi dòng** hoặc **một lần cho mỗi câu lệnh**, tùy DBMS và định nghĩa.
- Kích hoạt ở **BEFORE**, **AFTER** hoặc **INSTEAD OF**, nếu hệ quản trị hỗ trợ.
- Đọc giá trị cũ/mới bằng `OLD`, `NEW`, `:OLD`/`:NEW` hoặc các bảng ảo `inserted`/`deleted`.
- Được **vô hiệu hóa** bằng DDL ở hệ này nhưng **không có lệnh ENABLE/DISABLE native** ở hệ khác.
- Ghi dữ liệu trong cùng transaction với câu lệnh kích hoạt, nên có thể bị rollback cùng.
- Bị bỏ qua ở một số luồng như `TRUNCATE`, replication hoặc thao tác nội bộ, tùy hệ quản trị.
- Gây lỗi, chặn DML, làm chậm batch hoặc tạo vòng kích hoạt đệ quy.

Bài thuộc module **Database SQL**, chương **Trigger**, với chủ đề trực tiếp **“Tạo, vô hiệu hóa, xóa và kiểm thử trigger theo hệ quản trị”**. Ta sẽ dùng ví dụ theo dõi **thay đổi đơn giá sản phẩm** để đi qua trọn vòng đời trigger trên **PostgreSQL, MySQL, SQL Server, Oracle Database và SQLite**.

> Mục tiêu chính: biết **tạo đúng**, **quan sát được**, **kiểm thử được**, **tạm ngưng và khôi phục có kiểm soát**, rồi **xóa đúng đối tượng** mà không vô tình bỏ qua quy tắc toàn vẹn dữ liệu.

Các đoạn SQL được ghi rõ DBMS. Chỉ chạy trên **database học tập** hoặc môi trường kiểm thử; không sao chép nguyên cú pháp của DBMS này sang DBMS khác.

## 1. Trigger là gì và khi nào nên dùng?

Một hệ thống bán hàng lưu:

```text
products
  product_id | sku   | unit_price | stock_qty
           1 | A-001 |     100.00 |        10
           2 | A-002 |     200.00 |        20
           3 | A-003 |     300.00 |        30

price_audit
  audit_id | product_id | old_price | new_price | changed_at
```

Yêu cầu: khi `unit_price` của sản phẩm **thực sự thay đổi**, tự thêm một bản ghi vào `price_audit`.

Nếu chỉ để ứng dụng tự ghi audit:

```text
Application:
    UPDATE products
    INSERT price_audit
```

thì một đường truy cập khác (script bảo trì, ứng dụng thứ hai, ETL) có thể sửa giá mà quên ghi audit.

Một trigger gắn với bảng giúp logic được thực hiện trên **những đường ghi DML mà trigger thực sự được kích hoạt** theo quy tắc DBMS.

Sơ đồ:

```text
UPDATE products SET unit_price = ...
                │
                ▼
       DBMS kiểm tra trigger
                │
          AFTER UPDATE
                │
       so sánh OLD và NEW
                │
        nếu giá thay đổi
                ▼
       INSERT price_audit
                │
                ▼
    transaction tiếp tục / kết thúc
```

Nhưng trigger **không nên thay mọi ràng buộc**. Các quy tắc đơn giản như giá không âm, mã hàng duy nhất, khóa ngoại nên ưu tiên:

- `CHECK` cho `unit_price >= 0`.
- `UNIQUE` cho mã sản phẩm.
- `FOREIGN KEY` cho quan hệ giữa bảng.
- `NOT NULL` cho dữ liệu bắt buộc.

Trigger phù hợp hơn với **hành động phụ liên quan thay đổi** hoặc quy tắc phức tạp mà constraint thông thường không biểu đạt trực tiếp.

## 2. Sáu câu hỏi cần trả lời trước khi CREATE TRIGGER

| Câu hỏi | Ví dụ cần quyết định |
|---|---|
| Sự kiện kích hoạt? | `INSERT`, `UPDATE`, `DELETE` hay `TRUNCATE` nếu có |
| Thời điểm kích hoạt? | `BEFORE`, `AFTER`, `INSTEAD OF` |
| Cấp kích hoạt? | Mỗi **dòng** hay mỗi **statement** |
| Điều kiện chạy? | Chỉ khi giá trị thật sự đổi hay bất kỳ `UPDATE` nào? |
| Dữ liệu cũ/mới? | `OLD`/`NEW` hoặc `deleted`/`inserted` |
| Phạm vi transaction? | Các thay đổi audit có rollback cùng DML gốc không? |

### 2.1. BEFORE, AFTER và INSTEAD OF

- **BEFORE:** trước khi thao tác trên dòng/bảng diễn ra, thường dùng chuẩn hóa `NEW` hoặc từ chối thao tác ở những DBMS có hỗ trợ.
- **AFTER:** sau thao tác DML tương ứng trong ngữ cảnh statement/transaction, thường dùng ghi audit hoặc cập nhật dữ liệu phụ.
- **INSTEAD OF:** thay thế thao tác gốc, đặc biệt hữu ích với một số view; phải tự thực hiện những thay đổi cần thiết.

Không phải mọi DBMS đều hỗ trợ cả ba loại trên cùng loại đối tượng. Ví dụ **MySQL** chủ yếu có `BEFORE`/`AFTER` row trigger trên bảng; **SQL Server** có `AFTER`/`INSTEAD OF` DML trigger theo statement; **SQLite** có `INSTEAD OF` trên view.

### 2.2. FOR EACH ROW và FOR EACH STATEMENT

Giả sử câu SQL:

```sql
UPDATE products
SET unit_price = unit_price * 1.1
WHERE category_id = 5;
```

nếu sửa 100 dòng:

- **Row-level trigger:** thường chạy 100 lần, mỗi lần xử lý cặp giá trị của một dòng.
- **Statement-level trigger:** thường chạy một lần cho câu lệnh, dù câu lệnh ảnh hưởng nhiều dòng, và cần xử lý cả tập dữ liệu.

PostgreSQL hỗ trợ cả hai cấp. MySQL, Oracle row trigger thông thường và SQLite có `FOR EACH ROW` (Oracle còn hỗ trợ statement trigger); SQL Server DML trigger được gọi **theo statement** và cung cấp bảng ảo chứa **tập nhiều dòng**.

**Không viết SQL Server trigger như thể `inserted` luôn có một dòng.**

### 2.3. Giá trị cũ và mới

Ví dụ cập nhật giá 100 lên 120:

| Loại thao tác | Dữ liệu có thể tham chiếu |
|---|---|
| INSERT | Dòng mới (`NEW`/`inserted`) |
| UPDATE | Dòng trước và sau (`OLD`, `NEW` hoặc `deleted`, `inserted`) |
| DELETE | Dòng cũ (`OLD`/`deleted`) |

Đây là mô hình chung; cú pháp và thời điểm được phép sửa `NEW` là **đặc thù DBMS**.

### 2.4. “UPDATE cột” không đồng nghĩa “giá trị đã đổi”

Nếu ứng dụng chạy:

```sql
UPDATE products
SET unit_price = unit_price
WHERE product_id = 1;
```

một trigger được định nghĩa cho sự kiện `UPDATE` có thể vẫn được kích hoạt, dù giá trước và sau **bằng nhau**.

Với yêu cầu ghi **lịch sử thay đổi thực**, phải thêm điều kiện so sánh hai giá trị, xử lý `NULL` nếu cột có thể nullable.

### 2.5. Trigger không phải job chạy nền

Trigger DML thường thực thi **đồng bộ trong ngữ cảnh câu SQL** và transaction của nó; ghi audit có thể tăng thời gian của câu UPDATE. Đừng dùng trigger để gọi dịch vụ mạng chậm hoặc công việc kéo dài khi có cách tách sang outbox/hàng đợi an toàn hơn.

### 2.6. Trigger disabled khác trigger dropped

- **Disabled:** định nghĩa còn tồn tại nhưng không kích hoạt trong phạm vi bị vô hiệu hóa.
- **Dropped:** định nghĩa trigger được xóa khỏi schema; muốn hoạt động lại phải tạo lại hoặc chạy migration.
- **Bị lỗi/invalid:** trigger có thể vẫn được đánh dấu enabled nhưng không thực thi thành công do định nghĩa/phụ thuộc không hợp lệ.

Ba trạng thái này khác nhau, đặc biệt khi kiểm tra sự cố sau deploy.

## 3. Ma trận cú pháp tổng quan giữa năm DBMS

| Hệ quản trị | Tạo | Vô hiệu hóa / kích hoạt lại | Xóa |
|---|---|---|---|
| **PostgreSQL** | `CREATE FUNCTION ... RETURNS trigger` rồi `CREATE TRIGGER` | `ALTER TABLE table DISABLE TRIGGER name` / `ENABLE TRIGGER name` | `DROP TRIGGER name ON table` |
| **MySQL 8.x / InnoDB** | `CREATE TRIGGER ... BEFORE/AFTER ... FOR EACH ROW` | **Không có lệnh native `DISABLE TRIGGER`** cho DML trigger kiểu này; thiết kế/migration riêng | `DROP TRIGGER [IF EXISTS] name` |
| **SQL Server** | `CREATE OR ALTER TRIGGER ... ON table AFTER/INSTEAD OF ...` | `DISABLE TRIGGER name ON table` / `ENABLE TRIGGER name ON table` | `DROP TRIGGER [IF EXISTS] name` |
| **Oracle Database** | `CREATE OR REPLACE TRIGGER ... BEFORE/AFTER ...` | `ALTER TRIGGER name DISABLE` / `ENABLE` | `DROP TRIGGER name` |
| **SQLite** | `CREATE TRIGGER ... BEGIN ... END` | **Không có ENABLE/DISABLE native**; thường cần drop/recreate hoặc điều kiện do ứng dụng thiết kế | `DROP TRIGGER [IF EXISTS] name` |

Đây là **bảng định hướng**, không phải cú pháp chạy xuyên DBMS. Những chi tiết về quyền hạn, phiên bản và loại trigger cần được kiểm tra theo môi trường thật.

---

## 4. PostgreSQL — chuẩn bị bảng để học vòng đời trigger

Các ví dụ PostgreSQL bên dưới dùng hai bảng có tiền tố `lesson358_` nhằm tránh nhầm với bảng ứng dụng.

### 4.1. Bảng sản phẩm

```sql
CREATE TABLE lesson358_products (
    product_id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL
        CHECK (stock_qty >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO lesson358_products (
    product_id, sku, unit_price, stock_qty
)
VALUES
    (1, 'A-001', 100.00, 10),
    (2, 'A-002', 200.00, 20),
    (3, 'A-003', 300.00, 30);
```

Quy tắc dữ liệu:

- Mã `sku` không trùng.
- Giá và số tồn kho không âm.
- Giá bắt buộc có giá trị vì cột `unit_price NOT NULL`.

Các constraint đã bảo vệ những quy tắc này **không phụ thuộc audit trigger**.

### 4.2. Bảng ghi lịch sử giá

```sql
CREATE TABLE lesson358_price_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id INTEGER NOT NULL,
    old_price NUMERIC(12, 2) NOT NULL,
    new_price NUMERIC(12, 2) NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by TEXT NOT NULL
);
```

Ở đây cố ý **không đặt FK** tới `products` để minh họa một kiểu audit vẫn giữ được lịch sử sau khi sản phẩm gốc bị xóa; trong ứng dụng thật cần thống nhất chính sách giữ/xóa audit, dữ liệu nhạy cảm và yêu cầu pháp lý.

### 4.3. Xác minh dữ liệu ban đầu

```sql
SELECT product_id, sku, unit_price, stock_qty
FROM lesson358_products
ORDER BY product_id;

SELECT COUNT(*) AS audit_rows
FROM lesson358_price_audit;
```

Ngay sau lần khởi tạo đầu tiên, bảng có ba sản phẩm và audit có **0 dòng**.

Nếu đã chạy bài trước đó hoặc chạy lại nhiều lần, số audit có thể khác; khi so kết quả hãy bắt đầu từ database thử nghiệm sạch hoặc kiểm tra thay đổi **trước/sau trong chính transaction**.

## 5. PostgreSQL — viết trigger function

Với PostgreSQL, cách thông dụng là tạo **function trả `trigger`** rồi gắn function đó vào bảng bằng `CREATE TRIGGER`.

```sql
CREATE OR REPLACE FUNCTION lesson358_log_price_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson358_price_audit (
        product_id,
        old_price,
        new_price,
        changed_at,
        changed_by
    )
    VALUES (
        NEW.product_id,
        OLD.unit_price,
        NEW.unit_price,
        CURRENT_TIMESTAMP,
        CURRENT_USER
    );

    -- Giá trị trả về của AFTER ROW trigger bị bỏ qua
    -- cho thao tác gốc, nhưng RETURN NEW vẫn là quy ước rõ.
    RETURN NEW;
END;
$$;
```

Giải thích:

- `RETURNS trigger`: function dùng làm thân trigger.
- `NEW`: dòng sau cập nhật.
- `OLD`: dòng trước cập nhật.
- `CURRENT_TIMESTAMP`: thời điểm theo ngữ nghĩa transaction timestamp của PostgreSQL.
- `CURRENT_USER`: danh tính database được dùng theo ngữ nghĩa thực thi; **không nhất thiết là người dùng cuối của ứng dụng**.
- `RETURN NEW`: cần trả một giá trị phù hợp từ function; với **AFTER row trigger**, giá trị trả về không dùng để thay đổi dòng gốc.

### 5.1. BEFORE ROW trigger có ý nghĩa RETURN khác

Trong PostgreSQL:

- `BEFORE INSERT/UPDATE` row trigger có thể sửa các trường của `NEW` rồi `RETURN NEW`.
- `RETURN NULL` từ một **BEFORE ROW trigger** có thể bỏ qua thao tác đối với dòng đó theo quy tắc PostgreSQL.
- `BEFORE DELETE` thường `RETURN OLD` khi cho phép xóa.
- Trong `AFTER ROW` trigger, giá trị return không điều khiển lại thao tác DML đã thực hiện.
- Với statement trigger, giá trị trả về cũng không có ý nghĩa thay đổi dòng.

Vì thế, **không sao chép cùng một ý nghĩa của `RETURN NEW` cho mọi loại trigger**.

### 5.2. Trigger function có thể xử lý nhiều loại sự kiện

Trong PL/pgSQL có các biến như `TG_OP`, `TG_TABLE_NAME`, `TG_WHEN`, `TG_LEVEL` để function phân nhánh theo sự kiện/cấp kích hoạt.

Ví dụ ý tưởng:

```sql
IF TG_OP = 'INSERT' THEN
    -- Xử lý thêm mới.
ELSIF TG_OP = 'UPDATE' THEN
    -- Xử lý cập nhật.
ELSIF TG_OP = 'DELETE' THEN
    -- Xử lý xóa.
END IF;
```

Trong bài này, ta **chỉ gắn function cho UPDATE**, tránh tạo logic quá tổng quát khi chưa cần.

## 6. PostgreSQL — CREATE TRIGGER với điều kiện giá thực sự đổi

```sql
CREATE TRIGGER lesson358_products_price_audit_trg
AFTER UPDATE OF unit_price
ON lesson358_products
FOR EACH ROW
WHEN (
    OLD.unit_price IS DISTINCT FROM NEW.unit_price
)
EXECUTE FUNCTION lesson358_log_price_change();
```

Ý nghĩa từng phần:

| Thành phần | Ý nghĩa |
|---|---|
| `CREATE TRIGGER ...` | Tạo đối tượng trigger với tên đã chọn |
| `AFTER UPDATE OF unit_price` | Sự kiện UPDATE có **cột unit_price được nhắm trong SET** |
| `ON lesson358_products` | Bảng được gắn trigger |
| `FOR EACH ROW` | Mỗi dòng bị cập nhật phù hợp có thể kích hoạt |
| `WHEN (...)` | Chỉ chạy thân trigger khi giá trước/sau thực sự khác |
| `EXECUTE FUNCTION` | Gọi trigger function đã tạo |

### 6.1. Tại sao dùng IS DISTINCT FROM?

Trong SQL, toán tử `<>` có thể trả `UNKNOWN` khi một bên là `NULL`. PostgreSQL `IS DISTINCT FROM` xử lý so sánh bao gồm `NULL` theo nghĩa hai giá trị khác nhau:

| OLD | NEW | `OLD IS DISTINCT FROM NEW` |
|---|---|---|
| 100 | 120 | TRUE |
| 100 | 100 | FALSE |
| NULL | 100 | TRUE |
| NULL | NULL | FALSE |

Bảng mẫu `unit_price NOT NULL` nên không có NULL, nhưng cú pháp vẫn giúp biểu đạt chính xác mục tiêu **“giá trị thực sự thay đổi”**.

### 6.2. UPDATE OF dựa trên cột trong lệnh

`AFTER UPDATE OF unit_price` không có nghĩa bộ máy tự kiểm tra giá trước/sau đã khác. Nó xét việc cột có được nhắm bởi lệnh UPDATE theo quy tắc PostgreSQL.

Vì thế cả hai phần đều có vai trò:

- `UPDATE OF unit_price` thu hẹp sự kiện.
- `WHEN (OLD.unit_price IS DISTINCT FROM NEW.unit_price)` lọc cập nhật không thay đổi giá.

Đặc biệt, `UPDATE OF` có những sắc thái khi **BEFORE trigger khác sửa giá gián tiếp** mà cột giá không được liệt kê trong `SET`; không mặc định trigger `UPDATE OF` luôn phát hiện mọi thay đổi gián tiếp.

### 6.3. Tên trigger và thứ tự kích hoạt

Nếu có nhiều trigger cùng loại trên cùng bảng, PostgreSQL áp dụng quy tắc thứ tự của mình (thường theo tên trigger đối với cùng loại sự kiện). Không đặt logic phụ thuộc vào thứ tự ngầm nếu có thể viết rõ quy tắc và thiết kế bớt phụ thuộc.

Tên nên mô tả bảng, thời điểm và mục đích, ví dụ:

```text
lesson358_products_price_audit_trg
```

Đặt tên nhất quán giúp dễ quản lý migration và quan sát trạng thái.

## 7. PostgreSQL — kiểm thử trigger được kích hoạt

### 7.1. Test A: cập nhật giá và xem audit trong cùng transaction

```sql
BEGIN;

UPDATE lesson358_products
SET unit_price = 120.00,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = 1;

SELECT
    product_id,
    old_price,
    new_price,
    changed_by
FROM lesson358_price_audit
WHERE product_id = 1
ORDER BY audit_id DESC;

ROLLBACK;
```

Nếu giá ban đầu của sản phẩm 1 là `100.00` và trước đó chưa có audit, bên trong transaction bạn thấy một dòng mới:

| product_id | old_price | new_price |
|---:|---:|---:|
| 1 | 100.00 | 120.00 |

Sau `ROLLBACK`, **cả UPDATE sản phẩm và INSERT audit chưa commit đều bị hoàn tác**.

### 7.2. Test B: sau rollback, dữ liệu không đổi

```sql
SELECT product_id, unit_price
FROM lesson358_products
WHERE product_id = 1;

SELECT COUNT(*) AS audit_rows
FROM lesson358_price_audit
WHERE product_id = 1;
```

Trên bộ dữ liệu thử nghiệm sạch, giá trở lại `100.00` và audit sản phẩm 1 có `0` dòng.

**Đừng dựa vào `audit_id` liên tiếp để chứng minh rollback:** sequence/identity ở PostgreSQL có thể đã cấp giá trị dù transaction rollback, tạo khoảng trống ID.

### 7.3. Test C: commit khiến audit tồn tại

```sql
BEGIN;

UPDATE lesson358_products
SET unit_price = 120.00
WHERE product_id = 1;

COMMIT;

SELECT product_id, unit_price
FROM lesson358_products
WHERE product_id = 1;

SELECT product_id, old_price, new_price
FROM lesson358_price_audit
WHERE product_id = 1
ORDER BY audit_id;
```

Nếu trước khi chạy giá là 100 và audit rỗng, kết quả sau commit:

- Sản phẩm 1 có giá `120.00`.
- Một dòng audit biểu thị `100.00 → 120.00`.

Để chạy lại bài khác từ giá 100, có thể thực hiện reset có kiểm soát **chỉ trong database luyện tập**. Một lần UPDATE để reset giá **cũng kích hoạt trigger** nếu nó đang enabled, nên đừng xóa lịch sử audit ngoài ý muốn khi quan sát.

### 7.4. Test D: đặt giá bằng đúng giá hiện tại

```sql
BEGIN;

UPDATE lesson358_products
SET unit_price = unit_price
WHERE product_id = 1;

SELECT COUNT(*) AS audit_rows_now
FROM lesson358_price_audit
WHERE product_id = 1;

ROLLBACK;
```

Do điều kiện `WHEN` là FALSE khi giá không đổi, **không phát sinh audit mới** từ UPDATE này.

Nếu bảng đã có audit trước test, số đếm tổng **không bằng 0**; hãy so chênh lệch trước/sau hoặc lọc đúng sự kiện thay vì kết luận chỉ từ COUNT tổng.

### 7.5. Test E: UPDATE một cột khác

```sql
BEGIN;

UPDATE lesson358_products
SET stock_qty = stock_qty + 1
WHERE product_id = 1;

-- Trigger AFTER UPDATE OF unit_price không được kích hoạt
-- chỉ vì stock_qty thay đổi.
ROLLBACK;
```

Truy vấn điều kiện chỉ nhắm `stock_qty` nên không kích hoạt trigger giá theo khai báo trên.

### 7.6. Test F: một UPDATE thay đổi nhiều dòng

```sql
BEGIN;

UPDATE lesson358_products
SET unit_price = unit_price + 10
WHERE product_id IN (1, 2);

SELECT product_id, old_price, new_price
FROM lesson358_price_audit
WHERE product_id IN (1, 2)
ORDER BY audit_id DESC;

ROLLBACK;
```

Nếu cả hai dòng thực sự đổi giá, **row trigger chạy cho hai dòng**, tạo hai bản ghi audit mới trong transaction.

**Kiểm thử nhiều dòng là bắt buộc về mặt tư duy**, vì nhiều trigger viết sai khi chỉ thử `WHERE product_id = 1`.

## 8. PostgreSQL — xem trigger đang tồn tại và trạng thái

### 8.1. Tra pg_trigger

```sql
SELECT
    t.tgname,
    t.tgenabled,
    t.tgisinternal,
    pg_get_triggerdef(t.oid, TRUE) AS definition
FROM pg_trigger AS t
WHERE t.tgrelid = 'lesson358_products'::regclass
ORDER BY t.tgname;
```

Các trường quan trọng:

- `tgname`: tên trigger.
- `tgenabled`: trạng thái kích hoạt.
- `tgisinternal`: phân biệt trigger do hệ thống tạo với trigger do người dùng tạo.
- `pg_get_triggerdef`: SQL mô tả định nghĩa trigger.

### 8.2. Hiểu tgenabled

Trong PostgreSQL, giá trị `tgenabled` thường là:

| Giá trị | Nghĩa |
|---|---|
| `O` | Enabled ở chế độ origin/local thông thường |
| `D` | Disabled |
| `R` | Enabled ở chế độ replica |
| `A` | Enabled always |

Các chế độ nâng cao liên quan tới `session_replication_role`, sao chép dữ liệu và luồng áp dụng thay đổi. Không tự đổi sang `REPLICA`/`ALWAYS` khi chưa hiểu ảnh hưởng tới replication, ứng dụng và constraint triggers.

### 8.3. Chỉ xem trigger người dùng

```sql
SELECT
    t.tgname,
    t.tgenabled,
    pg_get_triggerdef(t.oid, TRUE) AS definition
FROM pg_trigger AS t
WHERE t.tgrelid = 'lesson358_products'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
```

Cách lọc này giúp tránh nhầm các trigger hệ thống phục vụ ràng buộc với audit trigger do ứng dụng tạo.

## 9. PostgreSQL — vô hiệu hóa và kích hoạt lại trigger

### 9.1. Tắt đúng một trigger

```sql
ALTER TABLE lesson358_products
DISABLE TRIGGER lesson358_products_price_audit_trg;
```

Sau đó, một UPDATE giá phù hợp **không gọi audit trigger này**.

### 9.2. Kích hoạt lại

```sql
ALTER TABLE lesson358_products
ENABLE TRIGGER lesson358_products_price_audit_trg;
```

Sau khi enabled, các UPDATE tiếp theo đủ điều kiện lại được ghi audit. **Những cập nhật xảy ra trong lúc disabled không tự được ghi bù**.

### 9.3. Kiểm thử tắt trigger mà không để lại trạng thái xấu

PostgreSQL hỗ trợ DDL transactional trong trường hợp `ALTER TABLE ... DISABLE TRIGGER` thông thường. Vì vậy, trong database thử nghiệm ta có thể dùng một giao dịch:

```sql
BEGIN;

ALTER TABLE lesson358_products
DISABLE TRIGGER lesson358_products_price_audit_trg;

UPDATE lesson358_products
SET unit_price = unit_price + 50
WHERE product_id = 1;

SELECT
    t.tgname,
    t.tgenabled
FROM pg_trigger AS t
WHERE t.tgrelid = 'lesson358_products'::regclass
  AND t.tgname = 'lesson358_products_price_audit_trg';

-- Dòng audit không tăng vì trigger bị disabled
-- trong transaction hiện tại.

ROLLBACK;
```

Sau rollback:

- UPDATE giá được hoàn tác.
- Thay đổi trạng thái DISABLE TRIGGER cũng được hoàn tác.
- Trigger trở về trạng thái trước khi bắt đầu transaction, nếu không có thay đổi khác.

**Không suy rộng mẫu này sang Oracle hoặc MySQL**, nơi các câu DDL liên quan có ngữ nghĩa implicit commit khác.

### 9.4. DISABLE TRIGGER USER và ALL

PostgreSQL có:

```sql
ALTER TABLE lesson358_products
DISABLE TRIGGER USER;
```

để tắt các trigger người dùng trên bảng, và:

```sql
ALTER TABLE lesson358_products
ENABLE TRIGGER USER;
```

để bật lại các trigger người dùng.

Có thể gặp:

```sql
ALTER TABLE lesson358_products
DISABLE TRIGGER ALL;
```

Nhưng `ALL` có thể đụng đến **trigger triển khai ràng buộc**, trong đó có cơ chế khóa ngoại, và một số hành động yêu cầu quyền đặc biệt. Việc tắt trigger constraint có thể để dữ liệu rơi vào trạng thái không hợp lệ.

**Chỉ tắt trigger cụ thể cần bảo trì, đừng dùng DISABLE TRIGGER ALL như mẹo “tăng tốc nhập liệu” khi chưa kiểm soát toàn vẹn.**

### 9.5. Vô hiệu hóa là thay đổi schema, không phải công tắc riêng một query

`ALTER TABLE ... DISABLE TRIGGER` thay đổi metadata của bảng và có cơ chế khóa DDL. Khi commit, trạng thái disabled có thể ảnh hưởng **các session khác**, không chỉ câu lệnh của người đang thao tác.

Vì vậy quy trình bảo trì cần:

1. Xác định đúng bảng và trigger.
2. Thông báo/phối hợp các writer khác.
3. Có biện pháp dừng hoặc kiểm soát luồng ghi.
4. Có kế hoạch bù dữ liệu bỏ sót.
5. Bật lại và xác minh trạng thái trước khi kết thúc.

Không coi lệnh disabled là một `SET LOCAL` tạm thời cho session riêng.

## 10. PostgreSQL — xóa trigger và function

### 10.1. DROP TRIGGER chỉ bỏ mối gắn với bảng

```sql
DROP TRIGGER IF EXISTS
    lesson358_products_price_audit_trg
ON lesson358_products;
```

Câu này xóa trigger khỏi bảng. Function `lesson358_log_price_change()` **vẫn tồn tại**, trừ khi bị xóa riêng hoặc tác động bởi một thao tác dependency khác.

### 10.2. Chỉ xóa function khi không còn cần

```sql
DROP FUNCTION IF EXISTS lesson358_log_price_change();
```

Nếu function còn được một trigger hoặc đối tượng khác sử dụng, PostgreSQL có thể từ chối drop theo cơ chế phụ thuộc.

**Không vội thêm `CASCADE`** để bỏ qua lỗi dependency, vì nó có thể xóa các đối tượng phụ thuộc khác mà bạn không muốn mất.

### 10.3. Tạo lại trigger

Sau khi đã drop đúng trigger nhưng giữ function:

```sql
CREATE TRIGGER lesson358_products_price_audit_trg
AFTER UPDATE OF unit_price
ON lesson358_products
FOR EACH ROW
WHEN (OLD.unit_price IS DISTINCT FROM NEW.unit_price)
EXECUTE FUNCTION lesson358_log_price_change();
```

Lưu ý các đoạn DROP/CREATE là bước độc lập của vòng đời, **không chạy liên tục nếu đang cần giữ trigger trong phần kiểm thử phía trên**.

### 10.4. Thay đổi logic không nhất thiết phải DROP trigger

Nếu chỉ sửa code trong function, có thể dùng:

```sql
CREATE OR REPLACE FUNCTION lesson358_log_price_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO lesson358_price_audit (
        product_id, old_price, new_price,
        changed_at, changed_by
    )
    VALUES (
        NEW.product_id, OLD.unit_price, NEW.unit_price,
        CURRENT_TIMESTAMP, CURRENT_USER
    );

    RETURN NEW;
END;
$$;
```

Định nghĩa trigger gắn với function vẫn có thể tiếp tục dùng function mới. Khi thay đổi chữ ký/kiểu và dependency, cần xử lý theo quy tắc tương ứng.

### 10.5. Đừng dùng DROP và CREATE không kiểm soát trên bảng đang ghi liên tục

Nếu DROP trigger, commit, rồi nhiều phút sau mới CREATE lại, các writer có thể thay đổi giá trong “khoảng trống” mà không sinh audit.

Ở PostgreSQL có thể đặt nhiều bước DDL và thao tác cần thiết trong một migration transaction phù hợp để giảm rủi ro trạng thái trung gian; vẫn phải cân nhắc khóa, quyền và ảnh hưởng đến hệ thống đang chạy.

---

## 11. MySQL — CREATE TRIGGER bằng BEFORE/AFTER FOR EACH ROW

MySQL có cú pháp trigger khác PostgreSQL: **thân trigger được khai báo trực tiếp**, không cần một function trả `trigger`.

Ví dụ dành cho MySQL 8.x với bảng InnoDB:

```sql
CREATE TABLE lesson358_mysql_products (
    product_id INT PRIMARY KEY,
    unit_price DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE lesson358_mysql_price_audit (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    old_price DECIMAL(12, 2) NOT NULL,
    new_price DECIMAL(12, 2) NOT NULL,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;

INSERT INTO lesson358_mysql_products (
    product_id, unit_price
)
VALUES (1, 100.00), (2, 200.00);
```

### 11.1. Tạo trigger AFTER UPDATE

Trong MySQL CLI/Workbench, có thể dùng `DELIMITER` để client không kết thúc định nghĩa khi thấy dấu chấm phẩy bên trong thân trigger:

```sql
DELIMITER //

CREATE TRIGGER lesson358_mysql_price_audit_trg
AFTER UPDATE ON lesson358_mysql_products
FOR EACH ROW
BEGIN
    IF NOT (OLD.unit_price <=> NEW.unit_price) THEN
        INSERT INTO lesson358_mysql_price_audit (
            product_id,
            old_price,
            new_price
        )
        VALUES (
            NEW.product_id,
            OLD.unit_price,
            NEW.unit_price
        );
    END IF;
END //

DELIMITER ;
```

Giải thích:

- MySQL trigger DML trong dạng này chạy **FOR EACH ROW**.
- `OLD.column` và `NEW.column` tham chiếu dòng trước/sau.
- `<=>` là phép **so sánh bằng an toàn với NULL** của MySQL.
- `NOT (OLD.unit_price <=> NEW.unit_price)` chỉ TRUE khi hai giá khác nhau.
- `DELIMITER` là chỉ thị phía client, **không phải statement DML hoặc transaction của server**.

Trong bài này giá `NOT NULL`, nên cũng có thể so `OLD.unit_price <> NEW.unit_price`. Dùng `<=>` minh họa cách xử lý giá trị thiếu trong các cột nullable.

### 11.2. Kiểm thử trigger MySQL trong transaction

```sql
START TRANSACTION;

UPDATE lesson358_mysql_products
SET unit_price = 120.00
WHERE product_id = 1;

SELECT product_id, old_price, new_price
FROM lesson358_mysql_price_audit;

ROLLBACK;
```

Với bảng InnoDB, audit insert do trigger thực hiện là thay đổi transactional và rollback cùng UPDATE của transaction gốc.

**Không áp dụng kết luận này cho mọi storage engine**. Phải kiểm tra bảng được dùng có transaction support, đặc biệt khi di chuyển từ hệ thống cũ.

### 11.3. Kiểm thử cập nhật nhiều dòng

```sql
START TRANSACTION;

UPDATE lesson358_mysql_products
SET unit_price = unit_price + 10
WHERE product_id IN (1, 2);

SELECT product_id, old_price, new_price
FROM lesson358_mysql_price_audit
ORDER BY audit_id;

ROLLBACK;
```

Nếu giá hai dòng đổi, MySQL gọi row trigger cho từng dòng và phát sinh hai bản ghi audit mới.

### 11.4. Quan sát trigger trong MySQL

```sql
SHOW TRIGGERS LIKE 'lesson358_mysql_products';
```

hoặc:

```sql
SHOW CREATE TRIGGER lesson358_mysql_price_audit_trg;
```

hoặc truy vấn metadata:

```sql
SELECT
    TRIGGER_NAME,
    EVENT_MANIPULATION,
    ACTION_TIMING,
    EVENT_OBJECT_TABLE,
    ACTION_STATEMENT
FROM information_schema.TRIGGERS
WHERE TRIGGER_SCHEMA = DATABASE()
  AND EVENT_OBJECT_TABLE = 'lesson358_mysql_products';
```

Kết quả hiển thị có thể phụ thuộc quyền truy cập và cách client trình bày.

## 12. MySQL — không có lệnh DISABLE TRIGGER trực tiếp

Khác PostgreSQL, SQL Server và Oracle, MySQL **không cung cấp cú pháp DML trigger native phổ quát** như:

```sql
-- KHÔNG phải cú pháp MySQL hợp lệ:
-- ALTER TRIGGER lesson358_mysql_price_audit_trg DISABLE;
-- DISABLE TRIGGER lesson358_mysql_price_audit_trg;
```

Muốn ngừng logic trigger, các phương án cần được thiết kế rõ:

1. **DROP TRIGGER**, rồi tạo lại sau bảo trì.
2. Dùng **điều kiện được định nghĩa trước** bên trong trigger để bỏ qua một số tình huống nghiệp vụ, nếu được phê duyệt.
3. Thực hiện migration dưới chế độ bảo trì hoặc kiểm soát luồng ghi, và có kế hoạch audit/backfill.

### 12.1. DROP TRIGGER MySQL

```sql
DROP TRIGGER IF EXISTS lesson358_mysql_price_audit_trg;
```

Sau khi drop, những câu UPDATE tiếp theo không gọi trigger này. Để hoạt động lại, phải chạy **CREATE TRIGGER** đầy đủ.

### 12.2. Cảnh báo về khoảng hở khi DROP/CREATE

Trong MySQL, nhiều thao tác DDL gây **implicit commit** và không hành xử như một transaction DML thông thường có thể rollback trọn vẹn. Không nên cho rằng:

```sql
START TRANSACTION;
DROP TRIGGER ...;
-- UPDATE hàng loạt...
CREATE TRIGGER ...;
ROLLBACK;
```

sẽ đưa toàn bộ schema/dữ liệu về trạng thái cũ.

Khi trigger audit bị drop, các thay đổi trong thời gian đó **không tự có audit**. Cần ngăn writer cạnh tranh hoặc thiết kế nguồn dữ liệu có thể đối soát.

### 12.3. Cờ “bỏ qua trigger” cần được kiểm soát

Một số hệ thống xây trigger kiểm tra cấu hình hoặc biến session để bỏ qua audit. Cách này có rủi ro:

- Lập trình viên hoặc tài khoản có quyền có thể bỏ qua audit.
- Connection pool tái sử dụng connection có thể giữ biến session không được reset.
- Luồng replication hoặc batch khác có thể có bối cảnh session khác.
- Ràng buộc nghiệp vụ có thể bị vô hiệu hóa ngoài ý muốn.

**Không coi cờ bỏ qua audit là giải pháp an toàn mặc định**, đặc biệt với thanh toán, tồn kho và yêu cầu kiểm toán.

### 12.4. Trigger MySQL không được tự COMMIT/ROLLBACK

MySQL hạn chế transaction control trong stored function và trigger. Thân trigger không được dùng các câu transaction control theo kiểu tự mở/đóng transaction độc lập.

Nếu cần log phải tồn tại dù DML gốc rollback, đó là một yêu cầu kiến trúc khác; không giải quyết bằng cách cố `COMMIT` trong trigger.

---

## 13. SQL Server — trigger chạy theo statement và dùng inserted/deleted

SQL Server khác biệt quan trọng: DML trigger trên bảng thường chạy **một lần cho một statement** chứ không phải một lần cho mỗi dòng.

Khi một UPDATE sửa 100 dòng, trigger nhận **hai tập dữ liệu**:

- `deleted`: hình ảnh cũ của các dòng.
- `inserted`: hình ảnh mới của các dòng.

Cần viết logic **set-based** để xử lý toàn bộ tập.

### 13.1. Tạo bảng thực hành T-SQL

```sql
CREATE TABLE dbo.lesson358_products (
    product_id INT PRIMARY KEY,
    unit_price DECIMAL(12, 2) NOT NULL
);

CREATE TABLE dbo.lesson358_price_audit (
    audit_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    product_id INT NOT NULL,
    old_price DECIMAL(12, 2) NOT NULL,
    new_price DECIMAL(12, 2) NOT NULL,
    changed_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO

INSERT INTO dbo.lesson358_products (
    product_id, unit_price
)
VALUES (1, 100.00), (2, 200.00), (3, 300.00);
GO
```

`GO` là dấu tách batch của những công cụ như SSMS/sqlcmd, **không phải câu lệnh SQL Server gửi vào engine như INSERT hoặc COMMIT**.

### 13.2. CREATE OR ALTER TRIGGER

```sql
CREATE OR ALTER TRIGGER dbo.lesson358_price_audit_trg
ON dbo.lesson358_products
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.lesson358_price_audit (
        product_id,
        old_price,
        new_price
    )
    SELECT
        i.product_id,
        d.unit_price,
        i.unit_price
    FROM inserted AS i
    INNER JOIN deleted AS d
        ON d.product_id = i.product_id
    WHERE i.unit_price <> d.unit_price;
END;
GO
```

Vì giá mẫu `NOT NULL`, phép `<>` đủ để tìm giá khác nhau. Nếu cột nullable, cần điều kiện so sánh phù hợp xử lý NULL.

### 13.3. Vì sao phải JOIN inserted và deleted?

`inserted` chứa dòng mới, `deleted` chứa dòng cũ. Ghép theo khóa ổn định `product_id` cho phép so từng cặp.

Một trigger sai phổ biến:

```sql
-- KHÔNG dùng làm xử lý multi-row:
-- SELECT @id = product_id FROM inserted;
-- INSERT audit cho riêng @id;
```

Dạng đó có thể chỉ xử lý một trong nhiều dòng được cập nhật, dẫn đến **mất audit**.

### 13.4. Test SQL Server với transaction

```sql
BEGIN TRANSACTION;

UPDATE dbo.lesson358_products
SET unit_price = unit_price + 10
WHERE product_id IN (1, 2);

SELECT
    product_id, old_price, new_price
FROM dbo.lesson358_price_audit
ORDER BY audit_id;

ROLLBACK TRANSACTION;
```

Trong transaction, bạn có thể thấy **hai dòng audit** mới. Khi rollback, cả UPDATE và insert audit do trigger thực hiện đều được hoàn tác theo transaction thông thường.

### 13.5. UPDATE(column) không đồng nghĩa giá đã đổi

Trong SQL Server trigger có thể dùng hàm:

```sql
IF UPDATE(unit_price)
BEGIN
    -- Cột xuất hiện trong thao tác cập nhật.
END
```

Nhưng `UPDATE(unit_price)` có thể TRUE **ngay cả khi giá vẫn bằng trước** và còn có sắc thái với INSERT tùy kiểu trigger. Nó không thay thế kiểm tra khác biệt giữa `inserted` và `deleted`.

Trong mẫu trên, so `i.unit_price <> d.unit_price` mới quyết định ghi audit thực tế.

## 14. SQL Server — DISABLE, ENABLE, DROP và quan sát trạng thái

### 14.1. Vô hiệu hóa trigger trên bảng

```sql
DISABLE TRIGGER dbo.lesson358_price_audit_trg
ON dbo.lesson358_products;
```

### 14.2. Bật lại

```sql
ENABLE TRIGGER dbo.lesson358_price_audit_trg
ON dbo.lesson358_products;
```

### 14.3. Xóa trigger

```sql
DROP TRIGGER IF EXISTS dbo.lesson358_price_audit_trg;
```

### 14.4. Xem trạng thái

```sql
SELECT
    t.name,
    t.is_disabled,
    t.parent_id,
    OBJECT_DEFINITION(t.object_id) AS definition
FROM sys.triggers AS t
WHERE t.parent_id = OBJECT_ID(N'dbo.lesson358_products');
```

- `is_disabled = 0`: trigger đang enabled.
- `is_disabled = 1`: trigger đang disabled.

Khi dùng `DROP TRIGGER`, dòng metadata cho trigger ấy không còn.

### 14.5. DISABLE TRIGGER ALL cũng có rủi ro

SQL Server có khả năng disable nhiều trigger cùng lúc trên đối tượng. Điều đó có thể làm mất các hoạt động audit/kiểm tra tự động khác ngoài trigger bạn muốn tắt.

Thay vì lệnh rộng như `DISABLE TRIGGER ALL ON ...`, nên xác định chính xác tên và lý do vô hiệu hóa, chuẩn bị kế hoạch tái kích hoạt và giám sát.

### 14.6. AFTER và INSTEAD OF trigger

- `AFTER UPDATE`: xử lý sau thao tác UPDATE trong ngữ nghĩa transaction của statement.
- `INSTEAD OF UPDATE`: thay thế thao tác UPDATE gốc, cần code rõ để thực hiện hiệu ứng mong muốn.

Không chuyển trigger audit `AFTER UPDATE` sang `INSTEAD OF` mà giữ nguyên code INSERT audit: làm vậy có thể khiến **bảng sản phẩm không được UPDATE** nếu trigger không thực hiện cập nhật thay thế.

### 14.7. TRUNCATE không kích hoạt DELETE trigger

Trong SQL Server, `TRUNCATE TABLE` không kích hoạt DML `DELETE` trigger như một câu `DELETE FROM` thông thường.

Vì vậy một trigger audit DELETE không phải bằng chứng rằng mọi cách xóa dữ liệu đều có dòng lịch sử. Quy trình vận hành cần giới hạn các con đường bypass phù hợp.

---

## 15. Oracle Database — CREATE OR REPLACE TRIGGER

Oracle thường dùng PL/SQL để viết thân trigger. Với row trigger, giá trị cũ/mới tham chiếu bằng `:OLD` và `:NEW`.

### 15.1. Chuẩn bị dữ liệu

```sql
CREATE TABLE lesson358_ora_products (
    product_id NUMBER PRIMARY KEY,
    unit_price NUMBER(12, 2) NOT NULL
);

CREATE TABLE lesson358_ora_price_audit (
    audit_id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id NUMBER NOT NULL,
    old_price NUMBER(12, 2) NOT NULL,
    new_price NUMBER(12, 2) NOT NULL,
    changed_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);

INSERT INTO lesson358_ora_products (
    product_id, unit_price
)
VALUES (1, 100.00);

INSERT INTO lesson358_ora_products (
    product_id, unit_price
)
VALUES (2, 200.00);

COMMIT;
```

### 15.2. Tạo trigger AFTER UPDATE OF

```sql
CREATE OR REPLACE TRIGGER lesson358_ora_price_audit_trg
AFTER UPDATE OF unit_price
ON lesson358_ora_products
FOR EACH ROW
BEGIN
    IF :OLD.unit_price <> :NEW.unit_price THEN
        INSERT INTO lesson358_ora_price_audit (
            product_id,
            old_price,
            new_price
        )
        VALUES (
            :NEW.product_id,
            :OLD.unit_price,
            :NEW.unit_price
        );
    END IF;
END;
/
```

Dấu `/` thường là lệnh gửi khối đã nhập của công cụ Oracle như SQL*Plus/SQLcl; **không phải một phần của PL/SQL body** và không tự `COMMIT`.

Giải thích:

- `:OLD.unit_price`: giá trước.
- `:NEW.unit_price`: giá sau.
- `FOR EACH ROW`: xử lý từng dòng.
- `IF ... THEN`: không tạo audit khi giá không đổi.
- `CREATE OR REPLACE`: thay thế định nghĩa trigger hiện có theo cú pháp Oracle.

### 15.3. Test rollback ở Oracle

```sql
UPDATE lesson358_ora_products
SET unit_price = 120.00
WHERE product_id = 1;

SELECT product_id, old_price, new_price
FROM lesson358_ora_price_audit
WHERE product_id = 1;

ROLLBACK;
```

Nếu chưa có thay đổi khác, audit insert và thay đổi giá của UPDATE được rollback cùng transaction của session.

**Chú ý:** điều này nói về **DML của trigger thông thường**. Nếu trigger được triển khai với `PRAGMA AUTONOMOUS_TRANSACTION` và tự commit, ý nghĩa rollback khác hẳn.

## 16. Oracle — ALTER TRIGGER DISABLE/ENABLE và DROP

### 16.1. Vô hiệu hóa

```sql
ALTER TRIGGER lesson358_ora_price_audit_trg DISABLE;
```

### 16.2. Kích hoạt lại

```sql
ALTER TRIGGER lesson358_ora_price_audit_trg ENABLE;
```

### 16.3. Xóa

```sql
DROP TRIGGER lesson358_ora_price_audit_trg;
```

### 16.4. Xem metadata

```sql
SELECT
    trigger_name,
    status,
    triggering_event,
    trigger_type,
    table_name
FROM user_triggers
WHERE table_name = 'LESSON358_ORA_PRODUCTS'
ORDER BY trigger_name;
```

Oracle thường lưu tên đối tượng không đặt trong dấu nháy kép theo chữ hoa trong data dictionary.

`STATUS` có thể cho biết enabled/disabled; đừng nhầm trạng thái enabled với việc trigger **compile thành công**.

### 16.5. Enabled nhưng trigger invalid

Một trigger Oracle có thể invalid vì lỗi compile hoặc phụ thuộc schema. Việc enabled không đảm bảo mọi câu DML qua trigger sẽ chạy thành công.

Có thể xem thông tin lỗi biên dịch qua `USER_ERRORS`:

```sql
SELECT
    name,
    type,
    line,
    position,
    text
FROM user_errors
WHERE name = 'LESSON358_ORA_PRICE_AUDIT_TRG'
ORDER BY sequence;
```

Sau khi sửa lỗi, có thể cần biên dịch lại hoặc thay thế định nghĩa theo công cụ/quy trình phù hợp.

### 16.6. Cảnh báo quan trọng: Oracle DDL gây implicit commit

Các lệnh `CREATE TRIGGER`, `ALTER TRIGGER`, `DROP TRIGGER` là **DDL**. Trong Oracle, nhiều DDL dẫn đến implicit commit, bao gồm phần transaction đang mở trước chúng theo quy tắc DBMS.

Vì thế **không** mong đoạn:

```sql
-- Cảnh báo: không dùng để giả định undo tất cả thay đổi.
UPDATE lesson358_ora_products
SET unit_price = 500.00
WHERE product_id = 1;

ALTER TRIGGER lesson358_ora_price_audit_trg DISABLE;

ROLLBACK;
```

sẽ đưa mọi thứ về trạng thái trước UPDATE. `ALTER TRIGGER` có thể đã commit transaction trước đó.

**Hành vi này khác PostgreSQL**: ở PostgreSQL, `ALTER TABLE ... DISABLE TRIGGER` thông thường có thể rollback như DDL transactional trong ví dụ học tập.

### 16.7. Autonomous transaction trong trigger Oracle

Oracle hỗ trợ `PRAGMA AUTONOMOUS_TRANSACTION` trong một số ngữ cảnh PL/SQL, cho phép một phần công việc dùng transaction riêng.

Tuy nhiên, với audit giá, autonomous transaction có thể ghi nhận một thay đổi **đã bị caller rollback**, khiến log không mô tả đúng dữ liệu cuối cùng. Còn có rủi ro khóa và tính nhất quán khi truy cập dữ liệu mà caller đang sửa.

Không thêm autonomous transaction chỉ để “giữ audit bằng mọi giá”; phải làm rõ đó là log **attempt** hay log **thay đổi đã commit**.

---

## 17. SQLite — CREATE TRIGGER và kiểm thử

SQLite có cú pháp trigger tích hợp trong SQL engine, nhưng không cung cấp stored procedure như PostgreSQL/Oracle.

### 17.1. Bảng thực hành

```sql
CREATE TABLE lesson358_sqlite_products (
    product_id INTEGER PRIMARY KEY,
    unit_price NUMERIC NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE lesson358_sqlite_price_audit (
    audit_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    old_price NUMERIC NOT NULL,
    new_price NUMERIC NOT NULL,
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO lesson358_sqlite_products (
    product_id, unit_price
)
VALUES (1, 100), (2, 200);
```

### 17.2. Tạo trigger AFTER UPDATE OF

```sql
CREATE TRIGGER lesson358_sqlite_price_audit_trg
AFTER UPDATE OF unit_price
ON lesson358_sqlite_products
FOR EACH ROW
WHEN OLD.unit_price IS NOT NEW.unit_price
BEGIN
    INSERT INTO lesson358_sqlite_price_audit (
        product_id,
        old_price,
        new_price
    )
    VALUES (
        NEW.product_id,
        OLD.unit_price,
        NEW.unit_price
    );
END;
```

`OLD.unit_price IS NOT NEW.unit_price` dùng cú pháp so sánh của SQLite, có thể phân biệt khác biệt kể cả với NULL theo quy tắc `IS NOT`. Với cột `NOT NULL` của bài, giá trị khác nhau thông thường cũng được phát hiện.

### 17.3. Test transaction và rollback

```sql
BEGIN;

UPDATE lesson358_sqlite_products
SET unit_price = 120
WHERE product_id = 1;

SELECT product_id, old_price, new_price
FROM lesson358_sqlite_price_audit;

ROLLBACK;
```

Trong SQLite transactional thông thường, insert audit do trigger thực hiện rollback cùng UPDATE.

### 17.4. Kiểm thử cập nhật nhiều dòng

```sql
BEGIN;

UPDATE lesson358_sqlite_products
SET unit_price = unit_price + 10
WHERE product_id IN (1, 2);

SELECT product_id, old_price, new_price
FROM lesson358_sqlite_price_audit
ORDER BY audit_id;

ROLLBACK;
```

SQLite trigger của bài hoạt động cho từng dòng. Khi cả hai giá đổi, có hai audit records mới trong transaction.

## 18. SQLite — không có ALTER TRIGGER ENABLE/DISABLE native

SQLite core không có câu `ALTER TRIGGER ... DISABLE` hay `ENABLE TRIGGER ...` như Oracle.

### 18.1. Xem trigger

```sql
SELECT
    name,
    tbl_name,
    sql
FROM sqlite_schema
WHERE type = 'trigger'
  AND tbl_name = 'lesson358_sqlite_products'
ORDER BY name;
```

### 18.2. DROP TRIGGER

```sql
DROP TRIGGER IF EXISTS lesson358_sqlite_price_audit_trg;
```

Khi đã drop, muốn hoạt động lại phải chạy `CREATE TRIGGER` với định nghĩa đầy đủ.

### 18.3. Thử DROP và rollback schema trong SQLite

SQLite hỗ trợ DDL transactional trong một transaction thích hợp. Trong database thử nghiệm, có thể dùng:

```sql
BEGIN;

DROP TRIGGER IF EXISTS lesson358_sqlite_price_audit_trg;

UPDATE lesson358_sqlite_products
SET unit_price = unit_price + 1
WHERE product_id = 1;

ROLLBACK;
```

Trong trường hợp DDL và UPDATE này thuộc cùng transaction hợp lệ, rollback có thể khôi phục cả định nghĩa trigger và dữ liệu theo trạng thái trước transaction.

**Không suy rằng điều đó tương tự MySQL hoặc Oracle**, nơi implicit commit của DDL có thể đổi hoàn toàn kết quả.

### 18.4. PRAGMA recursive_triggers không phải công tắc tắt mọi trigger

SQLite có `PRAGMA recursive_triggers` liên quan đến **recursive trigger invocation**. Nó **không phải** lệnh thay thế chung cho `DISABLE TRIGGER`.

Đổi cấu hình recursion có thể ảnh hưởng một số vòng kích hoạt, nhưng không tắt mọi BEFORE/AFTER trigger của bảng.

### 18.5. INSTEAD OF trigger trên view

SQLite có thể dùng `INSTEAD OF INSERT/UPDATE/DELETE` cho view để triển khai thao tác tương ứng.

Không coi trigger trên view và AFTER trigger trên bảng là cùng một loại hành vi. Với `INSTEAD OF`, thân trigger cần tự thực hiện logic ghi thích hợp.

### 18.6. Cảnh báo UPDATE OF với tên cột

SQLite có một đặc điểm lịch sử: trong danh sách `UPDATE OF column_name`, tên cột không hợp lệ có thể bị bỏ qua âm thầm thay vì báo lỗi ở một số tình huống.

Vì vậy khi tạo SQLite trigger:

- Xác minh tên cột theo schema thật.
- Có bài test update đúng cột.
- Có bài test update cột khác.
- Kiểm tra `sqlite_schema.sql` và dữ liệu sau test.

Đừng chỉ dựa vào việc câu `CREATE TRIGGER` chạy thành công để kết luận trigger bắt đúng cột.

## 19. Kiểm thử đầy đủ vòng đời trigger theo một ma trận

Một trigger audit tốt cần được kiểm thử bằng **các trạng thái dữ liệu**, không chỉ bằng việc câu `CREATE TRIGGER` báo thành công.

| Tình huống | Kết quả mong đợi nếu trigger enabled và định nghĩa đúng |
|---|---|
| UPDATE giá 100 → 120 | Một audit record cho mỗi dòng thay đổi |
| UPDATE giá 100 → 100 | Không phát sinh audit mới khi có điều kiện so sánh |
| UPDATE chỉ `stock_qty` | Không phát sinh audit giá nếu event chỉ là UPDATE OF unit_price |
| UPDATE 100 dòng thay đổi giá | Đủ 100 audit records theo ngữ nghĩa row/set |
| UPDATE `WHERE` không khớp dòng nào | Không có audit giá mới |
| Transaction UPDATE rồi ROLLBACK | Giá và audit transactional cùng rollback |
| Transaction UPDATE rồi COMMIT | Giá và audit được giữ |
| Trigger disabled | Không có audit do trigger này trong thời gian disabled |
| Trigger re-enabled | Các thay đổi mới lại phát audit |
| Trigger dropped | Trigger không còn trong metadata và không chạy |
| Trigger recreated | Định nghĩa xuất hiện và các test phù hợp chạy lại |
| UPDATE lỗi constraint | Không để lại audit transactional của statement không thành công |
| Concurrent UPDATE | Không mất/đếm đôi audit ngoài quy tắc concurrency và transaction |
| DML qua đường ghi khác | Vẫn xử lý nếu thuộc loại thao tác kích hoạt trigger và không bị bypass |
| Bulk load/TRUNCATE/cascade | Xác minh hành vi **theo DBMS**, không mặc định |

### 19.1. Đếm chênh lệch thay vì đếm tổng

Bảng audit có thể đã tồn tại nhiều bản ghi từ các test trước. Mẫu kiểm tra tốt là:

1. Ghi nhận số bản ghi audit phù hợp **trước** phép thử.
2. Thực hiện thao tác.
3. Ghi nhận số bản ghi audit **sau** phép thử.
4. So **delta** với số dòng thực sự thay đổi.

Ví dụ:

```sql
-- PostgreSQL, đọc trước.
SELECT COUNT(*) AS before_count
FROM lesson358_price_audit
WHERE product_id = 1;

-- Thực hiện UPDATE trong transaction theo test.

-- Đọc sau, rồi so chênh lệch thay vì đòi COUNT=1.
SELECT COUNT(*) AS after_count
FROM lesson358_price_audit
WHERE product_id = 1;
```

### 19.2. Không đo bằng số audit_id liên tiếp

Identity/sequence/auto-increment không hứa rằng các ID là chuỗi không có khoảng trống. Rollback, lỗi hoặc caching có thể tạo gap.

Kiểm thử **số dòng và nội dung OLD/NEW**, không dùng việc số ID bị nhảy để kết luận trigger lỗi.

### 19.3. Test dựa vào transaction phải hiểu DDL của DBMS

- PostgreSQL: một số DDL đổi trạng thái trigger có thể rollback trong transaction phù hợp.
- MySQL/Oracle: DDL có thể implicit commit; không bao DROP/ALTER trong BEGIN rồi tin ROLLBACK khôi phục mọi thứ.
- SQL Server: nên tách logic kiểm thử DML với thay đổi trạng thái trigger, và đảm bảo không để schema disabled.
- SQLite: DDL transactional khi trong explicit transaction phù hợp, nhưng vẫn phải kiểm soát lock và connection.

## 20. Test những trường hợp dễ gây nhầm lẫn

### 20.1. Cập nhật cùng giá trị

```sql
UPDATE lesson358_products
SET unit_price = unit_price
WHERE product_id = 1;
```

Trigger `AFTER UPDATE OF unit_price` đủ điều kiện về **cột được nhắm**, nhưng `WHEN OLD.unit_price IS DISTINCT FROM NEW.unit_price` chặn việc ghi audit.

Nếu bỏ `WHEN`, có nguy cơ ghi lịch sử “100 → 100” gây nhiễu.

### 20.2. Một câu tác động nhiều dòng

```sql
UPDATE lesson358_products
SET unit_price = unit_price + 5
WHERE product_id IN (1, 2, 3);
```

Với PostgreSQL row trigger: 3 dòng thay đổi → 3 lần thân trigger.

Với SQL Server statement trigger: **một lần thực thi trigger**, nhưng `inserted`/`deleted` chứa 3 dòng → câu INSERT set-based tạo 3 audit records.

**Kết quả audit giống nhau không có nghĩa mô hình kích hoạt giống nhau.**

### 20.3. Không dòng nào thỏa WHERE

```sql
UPDATE lesson358_products
SET unit_price = 999.00
WHERE product_id = -1;
```

Với PostgreSQL `FOR EACH ROW` trigger, không có dòng → không có lần kích hoạt row trigger.

Một statement-level trigger, khi DBMS hỗ trợ và định nghĩa tương ứng, **vẫn có thể được gọi cho statement ảnh hưởng 0 dòng**. Đừng áp dụng giả định row trigger cho statement trigger.

### 20.4. Một UPDATE bị lỗi CHECK

```sql
-- PostgreSQL, giá không âm theo CHECK.
BEGIN;

UPDATE lesson358_products
SET unit_price = -10
WHERE product_id = 1;

ROLLBACK;
```

Statement bị từ chối vì `CHECK (unit_price >= 0)`. Không được để lại bản ghi audit transactional của một thay đổi giá **không commit**.

Vì PostgreSQL transaction vào trạng thái lỗi sau statement thất bại, cần `ROLLBACK`, không cố chạy truy vấn khác bên trong transaction đã aborted.

### 20.5. Trigger ghi sang cùng bảng và đệ quy

Nếu trigger `AFTER UPDATE ON products` lại chạy:

```sql
UPDATE products SET ... WHERE product_id = ...;
```

nó có thể kích hoạt lại chính trigger hoặc trigger khác và tạo vòng lặp, lỗi hoặc cập nhật ngoài ý muốn, tùy DBMS và cấu hình recursion.

Ưu tiên:

- Với PostgreSQL BEFORE ROW trigger, sửa trực tiếp `NEW` khi phù hợp, thay vì UPDATE lại cùng dòng.
- Xác định điều kiện dừng.
- Tránh gọi DML tạo cùng sự kiện trên cùng bảng trừ khi có thiết kế rõ.
- Kiểm thử recursion/nesting của hệ quản trị thực tế.

### 20.6. Trigger audit làm thay đổi dữ liệu khác

Nếu trigger ngoài việc INSERT audit còn sửa bảng tồn kho/đơn hàng, phép thử cần kiểm tra **cả tác dụng phụ**, không chỉ audit.

Một trigger có thể “ghi audit đúng” nhưng làm thay đổi quy tắc nghiệp vụ khác, gây deadlock hoặc làm tăng thời gian transaction.

## 21. TRUNCATE, replication và luồng nhập dữ liệu đặc biệt

### 21.1. TRUNCATE không tự tương đương DELETE

Nhiều DBMS xử lý `TRUNCATE` như thao tác riêng, không kích hoạt row-level `DELETE` trigger:

- PostgreSQL có **statement-level TRUNCATE trigger** nếu được định nghĩa cho sự kiện đó; không dùng row DELETE trigger để bắt từng dòng TRUNCATE.
- SQL Server không kích hoạt `DELETE` trigger chỉ vì `TRUNCATE TABLE`.
- MySQL `TRUNCATE` không đi qua các row DELETE trigger như xóa từng dòng.
- Oracle `TRUNCATE` là DDL có quy tắc riêng, không được dùng để giả định row DELETE trigger chạy.
- SQLite không có câu `TRUNCATE TABLE` native; thao tác xóa dùng `DELETE` theo ngữ nghĩa SQLite.

Nếu yêu cầu “mọi việc loại bỏ dữ liệu đều phải có lịch sử”, cần **chặn hoặc kiểm soát thao tác có thể bypass**, không chỉ dựa vào DELETE trigger.

### 21.2. Foreign key cascade không có hành vi trigger giống nhau mọi hệ

Những dòng bị xóa/cập nhật do `ON DELETE CASCADE` hoặc `ON UPDATE CASCADE` có thể có cách kích hoạt trigger khác nhau giữa các DBMS.

Ví dụ MySQL có những hạn chế riêng về việc foreign-key cascaded actions không kích hoạt trigger tương ứng theo cơ chế trigger của nó. Không ngoại suy kết quả của một DBMS cho hệ khác.

Khi audit dữ liệu có quan hệ cha-con, phải thử:

- DELETE trực tiếp bảng con.
- DELETE bảng cha dẫn đến CASCADE.
- UPDATE khóa liên quan nếu có cascade.
- ROLLBACK/COMMIT những thao tác đó.

### 21.3. Bulk load, replication và tùy chọn nạp dữ liệu

Một số hệ thống hỗ trợ tắt trigger trong bulk load hoặc có cơ chế replication áp dụng thay đổi khác với DML thông thường.

Ví dụ PostgreSQL có trạng thái `ENABLE REPLICA/ALWAYS TRIGGER` và `session_replication_role`; SQL Server có các tùy chọn liên quan đến trigger trong một số luồng replication/bulk.

**Audit trigger không phải cơ chế bảo đảm tuyệt đối mọi thay đổi dù hệ thống dùng chế độ đặc biệt.** Với yêu cầu kiểm toán nghiêm ngặt, cần chính sách quyền, logging/CDC và các đường ghi được kiểm soát.

### 21.4. ON CONFLICT, MERGE và các nhánh DML

Một lệnh UPSERT hoặc MERGE có thể thực thi nhánh INSERT hay UPDATE, và các loại trigger có thể tương tác theo thứ tự/điều kiện phức tạp.

Không cho rằng:

```sql
INSERT ... ON CONFLICT DO UPDATE ...
```

luôn chỉ kích hoạt một kiểu trigger giống lệnh INSERT đơn giản. Hãy kiểm thử đúng nhánh thao tác trong DBMS đang dùng.

## 22. An toàn giao dịch và audit trigger

### 22.1. Audit transactional được rollback cùng dữ liệu

Trong PostgreSQL, SQL Server, MySQL InnoDB, Oracle trigger thông thường và SQLite, nếu audit insert nằm trong cùng transaction DML:

```text
BEGIN
  UPDATE products
    └── trigger INSERT audit
ROLLBACK
```

thì cả thay đổi giá và audit transactional thường cùng bị hoàn tác.

Đây là ưu điểm về nhất quán, nhưng cũng có nghĩa audit kiểu này **không ghi lại những lần thử đã rollback**.

### 22.2. Log mọi attempt và log thay đổi đã commit là hai yêu cầu khác nhau

- **Audit thay đổi đã commit:** hợp lý khi nằm cùng transaction với thay đổi nghiệp vụ.
- **Log mọi attempt kể cả thất bại/rollback:** có thể cần hệ thống log riêng hoặc cơ chế khác, nhưng phải định nghĩa rõ ý nghĩa và khả năng phát sinh tác dụng phụ ngoài DB.

Đừng đánh đồng hai loại bằng cách thêm autonomous transaction hoặc gọi API mạng từ trigger.

### 22.3. Trigger lỗi có thể làm DML gốc thất bại

Nếu trigger INSERT vào bảng audit bị lỗi ràng buộc, thiếu quyền hoặc dữ liệu không hợp lệ, câu UPDATE sản phẩm có thể bị từ chối/rollback theo quy tắc DBMS.

Đó có thể là hành vi mong muốn khi “không được thay đổi giá nếu không ghi được audit”; nhưng cũng có thể làm hệ thống phụ thuộc mạnh vào audit.

Cần quyết định rõ:

> Audit là một phần **bắt buộc** của tính nhất quán nghiệp vụ, hay là hệ thống quan sát không nên chặn giao dịch chính?

Phương án phù hợp sẽ khác nhau theo yêu cầu sản phẩm và tuân thủ.

### 22.4. Hiệu năng và contention

Trigger chạy thêm câu SQL có thể:

- Tăng số thao tác ghi/WAL/redo.
- Tăng thời gian giữ khóa.
- Tăng index maintenance của bảng audit.
- Gây deadlock nếu các trigger truy cập các bảng theo thứ tự khóa khác nhau.
- Khiến DML hàng loạt chậm hơn dự kiến.

Kiểm thử không chỉ số audit đúng mà còn **độ trễ và tài nguyên** với khối lượng phù hợp. Không dùng trigger để thay hệ thống xử lý batch phân tán không có thiết kế.

## 23. Vô hiệu hóa trigger trong bảo trì: quy trình có kiểm soát

Một quy trình đề xuất cho hệ quản trị có hỗ trợ DISABLE/ENABLE:

1. **Xác định phạm vi:** tên trigger, bảng, nguyên nhân cần tắt và người chịu trách nhiệm.
2. **Kiểm tra phụ thuộc:** trigger có kiểm tra invariant hoặc FK không? Có trigger khác cùng sự kiện không?
3. **Xác định tác động:** những DML nào có thể chạy khi tắt? Có mất audit hay bỏ qua đồng bộ không?
4. **Dừng hoặc phối hợp writer** nếu trạng thái disabled mang tính toàn hệ thống.
5. **Ghi lại định nghĩa/trạng thái trước thao tác** để khôi phục chính xác.
6. **Disable đúng trigger**, tránh dùng `ALL` nếu không cần.
7. **Thực hiện bảo trì** với transaction và giới hạn tương ứng DBMS.
8. **Bật lại ngay**, không đợi tới cuối đợt xử lý thủ công không được quản lý.
9. **Xác minh metadata** cho biết enabled.
10. **Thực hiện một test DML có rollback** để xác nhận trigger lại chạy.
11. **Backfill/reconcile** các bản ghi audit hoặc dữ liệu phụ đã bị bỏ sót nếu yêu cầu.
12. **Ghi nhận thời điểm và kết quả** theo quy trình vận hành.

### 23.1. Không được lẫn “tắt trong session” với “tắt trên bảng”

Ở PostgreSQL, `ALTER TABLE ... DISABLE TRIGGER` là thay đổi catalog; SQL Server và Oracle cũng có lệnh thay đổi trạng thái trigger. Hãy giả định nó có thể tác động nhiều connection khi được commit, trừ khi đã xác minh cơ chế cụ thể.

### 23.2. Nếu hệ quản trị không có DISABLE TRIGGER

MySQL/SQLite không có câu bật/tắt native tương ứng cho trigger DML trong cách dùng ở đây. Drop/recreate là **schema migration**, không phải thao tác tạm an toàn tuyệt đối.

Cần:

- Lưu định nghĩa trigger.
- Chỉ thực hiện khi không có writer không kiểm soát.
- Có kế hoạch tạo lại và xác minh.
- Bổ sung reconciliation cho khoảng thời gian thiếu trigger.
- Hiểu DDL có transactional hay implicit commit theo DBMS.

### 23.3. Không tắt trigger để che lỗi thiết kế

Nếu trigger gây chậm hoặc deadlock, tắt để “chữa tạm” có thể làm dữ liệu không còn đúng.

Cần xác định xem nên:

- Thêm/chỉnh index.
- Thay logic row-by-row bằng set-based ở SQL Server.
- Giảm cập nhật không cần thiết.
- Chuyển công việc nặng sang outbox.
- Sắp xếp thứ tự khóa.
- Điều chỉnh schema/ràng buộc đúng yêu cầu.

## 24. Quản lý phiên bản và migration của trigger

Trigger cũng là **đối tượng schema**, nên thay đổi nó cần quy trình tương tự table/index/function.

### 24.1. Kế hoạch đổi logic trigger

Một migration có thể cần:

1. Tạo hoặc cập nhật bảng audit.
2. Tạo/sửa function hỗ trợ (PostgreSQL).
3. Tạo hoặc thay đổi trigger.
4. Xem định nghĩa đang tồn tại.
5. Chạy kịch bản test chính.
6. Giám sát lỗi của DML sau triển khai.

Trong PostgreSQL, sửa function và trigger có dependency; trong Oracle/MySQL, cú pháp replace/drop khác nhau. Không dùng script “một phiên bản cho mọi DBMS”.

### 24.2. Tên ổn định và tính lặp lại

- PostgreSQL: `CREATE OR REPLACE FUNCTION` cho body; `DROP TRIGGER IF EXISTS ... ON ...` khi cần tạo lại, hoặc cú pháp thay thế nếu phiên bản hỗ trợ và migration chọn dùng.
- MySQL: `DROP TRIGGER IF EXISTS` rồi `CREATE TRIGGER` khi cần đổi định nghĩa theo quy trình, vì không có lệnh thay body đơn giản tương tự `CREATE OR ALTER`.
- SQL Server: `CREATE OR ALTER TRIGGER` giúp giảm nhu cầu DROP/CREATE trong nhiều môi trường.
- Oracle: `CREATE OR REPLACE TRIGGER` cập nhật thân.
- SQLite: thường `DROP TRIGGER IF EXISTS` rồi `CREATE TRIGGER`.

Một script “idempotent migration” không được hiểu là bất kể chạy khi nào cũng không gây tác dụng phụ. DROP/CREATE có thể tạo **khoảng hở kích hoạt** hoặc khóa schema.

### 24.3. Kiểm tra định nghĩa sau deployment

Đừng chỉ xem tên trigger tồn tại. Cần xác nhận:

- Đúng bảng và sự kiện.
- Đúng BEFORE/AFTER/INSTEAD OF.
- Đúng row/statement.
- Enabled theo trạng thái mong đợi.
- Body đúng phiên bản.
- Dependencies còn hợp lệ.
- Tài khoản thực thi có quyền.
- Các tình huống không có dòng và multi-row đã được xét.

### 24.4. Quyền hạn

Tạo, sửa, disable, drop trigger thường đòi quyền nhất định trên schema/bảng. Tài khoản ứng dụng thông thường **không nên có quyền vô hiệu hóa audit trigger** nếu không cần.

Với SQL Server, Oracle, PostgreSQL, MySQL và SQLite, cơ chế phân quyền khác nhau; trên SQLite, kiểm soát chủ yếu qua quyền truy cập file/connection/application. Không suy từ mô hình GRANT của một DBMS sang DBMS khác.

## 25. Các lỗi phổ biến khi tạo và kiểm thử trigger

### Lỗi 1. Tạo trigger nhưng quên tạo function PostgreSQL

Trong PostgreSQL, `EXECUTE FUNCTION` cần một trigger function phù hợp. Không thể gắn một hàm thường trả `integer` thay vì `trigger` cho row trigger theo cú pháp trong bài.

### Lỗi 2. Nhầm OLD/NEW của các DBMS

- PostgreSQL: `OLD.column`, `NEW.column` trong PL/pgSQL.
- MySQL: `OLD.column`, `NEW.column`.
- Oracle: `:OLD.column`, `:NEW.column` trong body PL/SQL.
- SQL Server: tập `deleted`/`inserted`.
- SQLite: `OLD.column`/`NEW.column`.

Cú pháp gần giống không đồng nghĩa mọi quy tắc giống nhau.

### Lỗi 3. Ghi audit dù giá không đổi

`AFTER UPDATE` không tự chứng minh giá trị đổi. Cần so OLD/NEW hoặc inserted/deleted.

### Lỗi 4. SQL Server trigger chỉ xử lý một dòng inserted

Một UPDATE có thể sửa nhiều dòng; trigger phải set-based, không lấy tùy tiện một giá trị đơn lẻ từ `inserted`.

### Lỗi 5. Tưởng MySQL có ALTER TRIGGER DISABLE

MySQL không có cơ chế DML trigger native tương ứng. Cần migration/thiết kế riêng.

### Lỗi 6. Tưởng SQLite PRAGMA recursive_triggers tắt mọi trigger

Đó là cấu hình recursion, không phải công tắc disable chung.

### Lỗi 7. PostgreSQL DISABLE TRIGGER ALL không xét FK

Các trigger ràng buộc có thể bị ảnh hưởng và yêu cầu quyền cao. Tắt sai có thể phá toàn vẹn.

### Lỗi 8. Oracle ALTER TRIGGER rồi ROLLBACK để “khôi phục mọi thứ”

DDL Oracle có implicit commit. Không giả định rollback cuối phục hồi cả trạng thái trigger và DML trước đó.

### Lỗi 9. DROP trigger rồi quên function PostgreSQL

`DROP TRIGGER` không tự xóa function hỗ trợ. Cần quản lý dependency riêng.

### Lỗi 10. DROP function với CASCADE không xét đối tượng phụ thuộc

`CASCADE` có thể xóa nhiều đối tượng khác; không dùng để bỏ qua lỗi dependency mà không hiểu hậu quả.

### Lỗi 11. Trigger enabled nhưng invalid

Đặc biệt ở Oracle, metadata enabled và trạng thái biên dịch là hai khía cạnh. Kiểm tra lỗi compile và kịch bản DML.

### Lỗi 12. Chỉ test UPDATE một dòng

Không phát hiện SQL Server trigger giả định một dòng, hoặc các vấn đề khi có 0 dòng và hàng loạt dòng.

### Lỗi 13. Chỉ xem COUNT tổng audit

Có thể có audit cũ. Cần đo delta theo transaction hoặc xác định đúng sự kiện.

### Lỗi 14. Dựa vào audit_id liên tục

Sequence/identity/auto-increment có thể tạo gap, kể cả rollback. Không dùng gap làm phép kiểm tra tính đúng đắn.

### Lỗi 15. Trigger tự UPDATE lại cùng bảng không có điều kiện dừng

Có thể dẫn tới recursion, vòng trigger hoặc cập nhật dư. Cân nhắc BEFORE trigger sửa NEW hoặc thiết kế không đệ quy.

### Lỗi 16. Tưởng TRUNCATE kích hoạt DELETE row trigger

Nhiều DBMS phân biệt TRUNCATE và DELETE. Cần kiểm tra riêng từng đường xóa dữ liệu.

### Lỗi 17. Tưởng FK CASCADE luôn kích hoạt trigger như DELETE trực tiếp

Hành vi khác nhau theo DBMS. Không dùng giả định xuyên hệ.

### Lỗi 18. Trigger ghi audit trong transaction nhưng mong audit sống sau ROLLBACK

Trong mô hình audit transactional, rollback hoàn tác audit cùng thay đổi. Log mọi attempt là yêu cầu khác.

### Lỗi 19. Vô hiệu hóa trigger để bulk load rồi không bật lại

Có thể làm mất audit/invariant cho mọi writer sau đó. Quy trình cần kiểm tra trạng thái và backfill.

### Lỗi 20. Gọi API mạng từ trigger

Có thể gây transaction dài, retry lặp tác dụng phụ và lỗi khó rollback. Đánh giá outbox hoặc cơ chế tích hợp thích hợp.

### Lỗi 21. Không xem hiệu năng

Trigger đúng chức năng vẫn có thể khiến DML chậm hoặc deadlock do thêm thao tác ghi/khóa.

### Lỗi 22. Cho ứng dụng quyền drop/disable audit trigger

Quyền không cần thiết làm tăng rủi ro mất theo dõi dữ liệu. Dùng phân quyền tối thiểu và migration account phù hợp.

## 26. Bài tập có đáp án

Các bài tập sử dụng bảng học tập đã định nghĩa; đoạn mã mỗi DBMS chỉ chạy trên hệ tương ứng. Bài có thao tác thay đổi schema nên thực hiện trong **database thử nghiệm độc lập**.

### Bài 1. Trigger nào phù hợp ghi audit giá sau cập nhật?

**Câu hỏi:** trong PostgreSQL, chọn `BEFORE INSERT`, `AFTER UPDATE OF unit_price` hay `AFTER DELETE`?

**Đáp án:** `AFTER UPDATE OF unit_price` kết hợp `WHEN OLD.unit_price IS DISTINCT FROM NEW.unit_price` khi yêu cầu là audit sự thay đổi giá.

### Bài 2. PostgreSQL cần tạo mấy đối tượng?

**Đáp án:** với ví dụ PL/pgSQL, cần một function `RETURNS trigger` và một đối tượng `CREATE TRIGGER` gắn function với bảng.

### Bài 3. Vì sao dùng IS DISTINCT FROM?

**Đáp án:** so sánh cũ/mới kể cả trường hợp NULL mà không bị `UNKNOWN` như `<>`. Với giá NOT NULL vẫn dùng được và diễn đạt rõ ý “thực sự khác”.

### Bài 4. UPDATE giá bằng chính giá cũ có được audit không?

```sql
UPDATE lesson358_products
SET unit_price = unit_price
WHERE product_id = 1;
```

**Đáp án:** với trigger PostgreSQL của bài, không phát sinh audit mới vì `WHEN` là FALSE.

### Bài 5. UPDATE chỉ stock_qty?

```sql
UPDATE lesson358_products
SET stock_qty = stock_qty + 1
WHERE product_id = 1;
```

**Đáp án:** trigger `AFTER UPDATE OF unit_price` không chạy do câu lệnh không nhắm cột `unit_price`.

### Bài 6. Một UPDATE đổi giá ba sản phẩm PostgreSQL

**Đáp án:** row trigger được kích hoạt cho ba dòng phù hợp; kỳ vọng ba audit records mới nếu giá của cả ba thực sự đổi.

### Bài 7. UPDATE 0 dòng và statement trigger

**Đáp án:** row trigger không chạy khi không có dòng tương ứng; một statement trigger trên DBMS hỗ trợ vẫn có thể kích hoạt một lần dù tác động 0 dòng.

### Bài 8. Kiểm thử rollback PostgreSQL

```sql
BEGIN;
UPDATE lesson358_products
SET unit_price = unit_price + 1
WHERE product_id = 1;
ROLLBACK;
```

**Đáp án:** giá và audit transactional do trigger tạo được rollback cùng nhau. Không dùng khoảng trống `audit_id` để kết luận.

### Bài 9. Tắt đúng một PostgreSQL trigger

```sql
ALTER TABLE lesson358_products
DISABLE TRIGGER lesson358_products_price_audit_trg;
```

**Đáp án:** đúng cú pháp cho bảng/trigger bài học. Cần `ENABLE TRIGGER` để khôi phục và kiểm tra các dòng bỏ sót trong thời gian tắt.

### Bài 10. ENABLE PostgreSQL trigger

```sql
ALTER TABLE lesson358_products
ENABLE TRIGGER lesson358_products_price_audit_trg;
```

**Đáp án:** kích hoạt lại trigger được nêu; không tự sinh audit cho những UPDATE đã diễn ra trước đó.

### Bài 11. Vì sao không nên DISABLE TRIGGER ALL?

**Đáp án:** có thể ảnh hưởng những trigger khác hoặc trigger nội bộ thực thi constraint, làm mất toàn vẹn dữ liệu và chức năng ngoài chủ đích.

### Bài 12. DROP TRIGGER có xóa PostgreSQL function không?

**Đáp án:** không tự xóa function thường dùng của trigger. `DROP TRIGGER ... ON table` và `DROP FUNCTION ...` là hai thao tác khác nhau.

### Bài 13. MySQL so giá có NULL

**Đáp án:** có thể dùng `NOT (OLD.unit_price <=> NEW.unit_price)` để nhận diện hai giá khác nhau kể cả NULL theo cú pháp MySQL.

### Bài 14. Vô hiệu hóa trigger MySQL bằng ALTER?

**Đáp án:** không có `ALTER TRIGGER ... DISABLE` native theo kiểu Oracle. Cần drop/recreate hoặc cơ chế được thiết kế từ trước, có kế hoạch bảo trì an toàn.

### Bài 15. MySQL trigger có thể COMMIT riêng không?

**Đáp án:** không dùng COMMIT/ROLLBACK để tự kết thúc transaction trong trigger theo cách bị DBMS cấm. Audit InnoDB thông thường nằm trong transaction của DML gốc.

### Bài 16. SQL Server UPDATE 100 dòng, trigger chạy mấy lần?

**Đáp án:** DML trigger theo statement thường chạy **một lần**, nhưng `inserted`/`deleted` có thể chứa **100 dòng**. Câu INSERT audit phải set-based để ghi đủ các thay đổi.

### Bài 17. SQL Server dùng OLD/NEW kiểu PostgreSQL được không?

**Đáp án:** không. SQL Server DML trigger dùng `inserted` và `deleted` để lấy tập giá trị mới/cũ.

### Bài 18. Vô hiệu hóa SQL Server trigger

```sql
DISABLE TRIGGER dbo.lesson358_price_audit_trg
ON dbo.lesson358_products;
```

**Đáp án:** đúng cho trigger mẫu; bật lại bằng `ENABLE TRIGGER ... ON dbo.lesson358_products`.

### Bài 19. Metadata SQL Server cho trạng thái?

**Đáp án:** `sys.triggers.is_disabled`, với `0` là enabled và `1` là disabled.

### Bài 20. Oracle dùng :OLD hay OLD?

**Đáp án:** trong thân row trigger PL/SQL của bài, tham chiếu bằng `:OLD.unit_price` và `:NEW.unit_price`.

### Bài 21. Oracle ALTER TRIGGER DISABLE có rollback như PostgreSQL?

**Đáp án:** không được giả định. Oracle DDL thường implicit commit; cần tách DML test và DDL quản lý trạng thái.

### Bài 22. Oracle autonomous audit sống sau outer ROLLBACK?

**Đáp án:** có thể, nếu autonomous transaction tự commit. Nhưng audit có thể không phản ánh thay đổi nghiệp vụ đã commit, nên cần xét mục tiêu của log.

### Bài 23. SQLite dùng lệnh nào để xem định nghĩa trigger?

```sql
SELECT name, tbl_name, sql
FROM sqlite_schema
WHERE type = 'trigger';
```

**Đáp án:** truy vấn metadata trong `sqlite_schema`. Lọc `tbl_name` để chọn đúng bảng.

### Bài 24. SQLite PRAGMA recursive_triggers có tắt audit trigger không?

**Đáp án:** không phải công tắc tắt mọi trigger. Nó điều khiển recursion, không thay cho `ENABLE/DISABLE` native.

### Bài 25. TRUNCATE có thay cho DELETE trigger test không?

**Đáp án:** không. Nhiều DBMS không kích hoạt row DELETE trigger khi `TRUNCATE`; PostgreSQL có loại statement TRUNCATE trigger riêng. Cần kiểm thử theo hệ quản trị.

### Bài 26. Vì sao kiểm thử nhiều dòng quan trọng?

**Đáp án:** nó phát hiện các trigger viết theo giả định chỉ một dòng, đặc biệt SQL Server; đồng thời xác minh số audit mới tương ứng số dòng thực sự thay đổi.

### Bài 27. Có nên đo số audit_id liên tiếp không?

**Đáp án:** không. Sequence/identity có thể bị cấp giá trị mà rollback không hoàn tác. Kiểm tra nội dung và số dòng phù hợp.

### Bài 28. Trigger ghi audit bị lỗi INSERT audit

**Đáp án:** thao tác DML gốc có thể thất bại/rollback cùng theo ngữ nghĩa transaction. Cần quyết định có yêu cầu “không audit được thì không cho sửa giá” hay không.

### Bài 29. Tắt trigger để nạp dữ liệu, rồi bật lại có đủ chưa?

**Đáp án:** chưa. Các thao tác trong lúc disabled không tự được audit bù; cần đối soát/backfill nếu nghiệp vụ yêu cầu.

### Bài 30. Chọn giải pháp cho từng DBMS

| Hệ quản trị | Lệnh/mô hình chính |
|---|---|
| PostgreSQL | `CREATE FUNCTION` + `CREATE TRIGGER`; `ALTER TABLE DISABLE/ENABLE TRIGGER` |
| MySQL | `CREATE TRIGGER`; không có DISABLE native; `DROP TRIGGER` |
| SQL Server | `CREATE OR ALTER TRIGGER`; `DISABLE/ENABLE TRIGGER ... ON table` |
| Oracle | `CREATE OR REPLACE TRIGGER`; `ALTER TRIGGER DISABLE/ENABLE` |
| SQLite | `CREATE TRIGGER`, `DROP TRIGGER`; không có ENABLE/DISABLE native |

**Đáp án:** đúng theo bảng, với điều kiện dùng đúng phiên bản và đối tượng của hệ quản trị.

## 27. Checklist thực hành trước khi triển khai trigger

Checklist dưới đây phục vụ người học tự tổ chức thao tác. Nó **không thay thế kiểm thử của dự án**.

- [ ] Xác định đúng bảng/view và DBMS.
- [ ] Chọn đúng sự kiện INSERT/UPDATE/DELETE và thời điểm BEFORE/AFTER/INSTEAD OF.
- [ ] Phân biệt row trigger với statement trigger.
- [ ] Xử lý đúng OLD/NEW hoặc inserted/deleted.
- [ ] Không ghi audit khi dữ liệu thực sự không đổi, nếu đó là yêu cầu.
- [ ] Thử một dòng, nhiều dòng và 0 dòng.
- [ ] Thử transaction COMMIT và ROLLBACK.
- [ ] Thử lỗi constraint để xem tính nguyên tử.
- [ ] Kiểm tra metadata sau CREATE.
- [ ] Kiểm tra trạng thái disabled/enabled theo đúng DBMS.
- [ ] Không dùng DISABLE ALL nếu có rủi ro constraint hoặc trigger khác.
- [ ] Biết DDL có transactional/implicit commit hay không.
- [ ] Có cách khôi phục nhanh nếu migration thất bại.
- [ ] Có kế hoạch backfill khi trigger audit từng bị tắt.
- [ ] Thử đường ghi bulk/cascade/UPSERT nếu ứng dụng có dùng.
- [ ] Quan sát hiệu năng và recursion.
- [ ] Phân quyền tối thiểu để hạn chế việc vô tình drop/disable.
- [ ] Ghi rõ hợp đồng trigger, tác dụng phụ và giới hạn dữ liệu.

## 28. Bảng ghi nhớ nhanh

| Khái niệm | Điều cần nhớ |
|---|---|
| Trigger | Logic do DBMS kích hoạt theo sự kiện phù hợp |
| `BEFORE` | Có thể kiểm tra/sửa giá trị trước khi DML, tùy DBMS |
| `AFTER` | Thường dùng audit sau thao tác DML tương ứng |
| `INSTEAD OF` | Thay thế thao tác gốc, cần tự thực thi logic |
| Row trigger | Xử lý mỗi dòng thay đổi |
| Statement trigger | Xử lý mỗi statement, có thể chứa nhiều dòng |
| PostgreSQL `RETURNS trigger` | Function riêng để gắn vào trigger |
| PostgreSQL `WHEN` | Lọc điều kiện kích hoạt ở mức trigger |
| PostgreSQL `IS DISTINCT FROM` | So giá trị cũ/mới kể cả NULL |
| PostgreSQL disabled | `ALTER TABLE ... DISABLE TRIGGER name` |
| PostgreSQL enabled | `ALTER TABLE ... ENABLE TRIGGER name` |
| PostgreSQL drop | `DROP TRIGGER name ON table` |
| PostgreSQL metadata | `pg_trigger.tgenabled` |
| MySQL tạo | `CREATE TRIGGER ... FOR EACH ROW` |
| MySQL NULL-safe compare | `OLD.x <=> NEW.x` |
| MySQL tắt | Không có `DISABLE TRIGGER` native tương ứng |
| MySQL drop | `DROP TRIGGER name` |
| SQL Server dữ liệu cũ/mới | `deleted` / `inserted` |
| SQL Server multi-row | Viết set-based, không giả định một dòng |
| SQL Server tắt/bật | `DISABLE/ENABLE TRIGGER ... ON table` |
| SQL Server metadata | `sys.triggers.is_disabled` |
| Oracle OLD/NEW | `:OLD` / `:NEW` trong row trigger |
| Oracle tắt/bật | `ALTER TRIGGER name DISABLE/ENABLE` |
| Oracle DDL | Thường implicit commit, thận trọng rollback |
| SQLite trigger | `CREATE TRIGGER ... BEGIN ... END` |
| SQLite disable | Không có lệnh native chung |
| SQLite metadata | `sqlite_schema` |
| `TRUNCATE` | Không tự tương đương DELETE row trigger |
| Trigger transactional | Audit thường rollback cùng DML gốc |
| Tắt audit | Các thay đổi bỏ sót không tự backfill |
| Kiểm thử đúng | Một dòng, nhiều dòng, không đổi, rollback, disable/re-enable |
| Triển khai an toàn | Migration có thể khôi phục, phân quyền và giám sát |

## 29. Kết luận

Tạo trigger chỉ là bước đầu. Một trigger đáng tin phải được **xác định đúng sự kiện, viết đúng kiểu row/statement, kiểm thử cả dữ liệu cũ và mới, và quản lý vòng đời có kiểm soát**.

Các khác biệt quan trọng nhất giữa các hệ quản trị:

1. **PostgreSQL** tách trigger function và đối tượng trigger; có `ALTER TABLE ... DISABLE/ENABLE TRIGGER`, với nhiều thay đổi schema có thể rollback trong transaction phù hợp.
2. **MySQL** khai báo trực tiếp thân trigger row-level; không có cú pháp disable/enable native tương đương, nên dừng trigger đòi hỏi thiết kế/migration đặc biệt.
3. **SQL Server** chạy DML trigger theo statement và cung cấp tập `inserted`/`deleted`; xử lý nhiều dòng đúng là yêu cầu bắt buộc.
4. **Oracle** dùng `:OLD`/`:NEW` trong row trigger, hỗ trợ `ALTER TRIGGER DISABLE/ENABLE` nhưng DDL có thể implicit commit.
5. **SQLite** có CREATE/DROP trigger và kiểm thử trong transaction, nhưng không có ENABLE/DISABLE trigger native; `PRAGMA recursive_triggers` không phải công tắc thay thế.

Dù ở hệ nào, hãy luôn hỏi: **“Nếu trigger bị tắt, nếu transaction rollback, nếu một statement sửa 10.000 dòng hoặc nếu ứng dụng dùng đường ghi khác, dữ liệu cuối cùng có còn đúng không?”**

Nếu câu trả lời chưa rõ, chưa nên coi trigger đã sẵn sàng cho môi trường vận hành.

## Tài liệu tham khảo

- [PostgreSQL — CREATE TRIGGER](https://www.postgresql.org/docs/current/sql-createtrigger.html): event, timing, level, `WHEN` và `EXECUTE FUNCTION`.
- [PostgreSQL — Trigger Functions](https://www.postgresql.org/docs/current/plpgsql-trigger.html): `OLD`, `NEW`, `TG_OP` và giá trị trả về.
- [PostgreSQL — ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html): `ENABLE/DISABLE TRIGGER` và các chế độ trigger.
- [PostgreSQL — DROP TRIGGER](https://www.postgresql.org/docs/current/sql-droptrigger.html): xóa trigger gắn với bảng.
- [MySQL — CREATE TRIGGER](https://dev.mysql.com/doc/refman/8.4/en/create-trigger.html): cú pháp và các hạn chế trigger.
- [MySQL — DROP TRIGGER](https://dev.mysql.com/doc/refman/8.4/en/drop-trigger.html): xóa trigger.
- [MySQL — Stored Program Restrictions](https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html): các hạn chế transaction và thao tác từ trigger.
- [Microsoft Learn — CREATE TRIGGER (Transact-SQL)](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-trigger-transact-sql): DML trigger, `inserted` và `deleted`.
- [Microsoft Learn — DISABLE TRIGGER](https://learn.microsoft.com/en-us/sql/t-sql/statements/disable-trigger-transact-sql): vô hiệu hóa trigger SQL Server.
- [Microsoft Learn — ENABLE TRIGGER](https://learn.microsoft.com/en-us/sql/t-sql/statements/enable-trigger-transact-sql): kích hoạt lại.
- [Oracle Database — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html): khai báo DML trigger.
- [Oracle Database — ALTER TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TRIGGER.html): enable/disable và compile.
- [Oracle Database — DROP TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DROP-TRIGGER.html): xóa trigger.
- [SQLite — CREATE TRIGGER](https://www.sqlite.org/lang_createtrigger.html): cú pháp, `OLD`/`NEW` và `WHEN`.
- [SQLite — DROP TRIGGER](https://www.sqlite.org/lang_droptrigger.html): xóa trigger trong SQLite.
- [SQLite — Transactions](https://www.sqlite.org/lang_transaction.html): `BEGIN`, `COMMIT` và `ROLLBACK`.

