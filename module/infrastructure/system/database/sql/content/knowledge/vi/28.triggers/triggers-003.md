# BEFORE, AFTER và INSTEAD OF theo hệ quản trị

**Trigger** là đoạn logic được hệ quản trị cơ sở dữ liệu kích hoạt tự động khi một sự kiện đã định xảy ra trên bảng, view hoặc đối tượng được hỗ trợ. Đối với DML, ba kiểu thời điểm thường gặp là **BEFORE**, **AFTER** và **INSTEAD OF**:

- **BEFORE**: chạy trước thao tác ghi tương ứng, thích hợp với những hệ cho phép chuẩn hóa/kiểm tra giá trị `NEW` trước khi hàng được ghi.
- **AFTER**: chạy sau khi thao tác ghi tương ứng đã được thực hiện trong ngữ cảnh của câu lệnh và giao dịch, thường dùng để ghi audit hoặc duy trì dữ liệu phụ thuộc.
- **INSTEAD OF**: chạy **thay cho thao tác DML trực tiếp** trên đối tượng được định nghĩa, rất hữu ích khi cần định nghĩa cách ghi thông qua một view phức tạp.

Một khác biệt nền tảng: **không phải hệ quản trị nào cũng có cả ba kiểu hoặc cùng cấp kích hoạt**. PostgreSQL hỗ trợ `BEFORE`/`AFTER` theo hàng hoặc theo câu lệnh trên bảng và `INSTEAD OF` theo hàng trên view; SQL Server chủ yếu có trigger DML `AFTER` và `INSTEAD OF` cấp câu lệnh; MySQL có `BEFORE` và `AFTER` theo hàng trên bảng, không có `INSTEAD OF`; Oracle và SQLite lại có những lựa chọn và giới hạn riêng.

Bài học thuộc **Database SQL → Trigger → BEFORE, AFTER và INSTEAD OF theo hệ quản trị**. Mục tiêu là hiểu đúng thời điểm, phạm vi, dữ liệu cũ/mới, tác động của transaction và cách triển khai theo từng DBMS, thay vì cố dùng một mẫu trigger cho mọi sản phẩm.

## 1. Ví dụ trực giác: ba điểm can thiệp

Giả sử có bảng nhân viên:

```text
staff_id | email                 | monthly_salary
---------+-----------------------+---------------
101      | An@Example.Test       | 1000.00
102      | Binh@Example.Test     | 1500.00
```

Ứng dụng thực hiện:

```sql
UPDATE staff
SET monthly_salary = 1200.00
WHERE staff_id = 101;
```

Một trigger có thể tham gia ở các giai đoạn khác nhau:

```text
Ứng dụng gửi UPDATE
        │
        ▼
  BEFORE trigger
  - kiểm tra hạn mức/lương
  - chuẩn hóa cột mới nếu DBMS cho phép
        │
        ▼
  Thao tác UPDATE trên bảng
  - kiểm tra các ràng buộc liên quan
  - ghi phiên bản/giá trị theo cơ chế DBMS
        │
        ▼
  AFTER trigger
  - ghi bản ghi audit
  - cập nhật dữ liệu phụ thuộc
        │
        ▼
  Kết thúc statement và transaction
  - COMMIT hoặc ROLLBACK
```

Nếu ứng dụng cập nhật thông qua một **view**, `INSTEAD OF` có thể thay thế thao tác ghi mặc định:

```text
Ứng dụng: UPDATE v_staff_directory
        │
        ▼
INSTEAD OF UPDATE trên view
        │
        ├─ xác định hàng bảng gốc tương ứng
        ├─ kiểm tra cột nào được phép sửa
        └─ chạy UPDATE trên bảng gốc
                 │
                 ├─ BEFORE UPDATE trên bảng gốc
                 └─ AFTER UPDATE trên bảng gốc
```

Sơ đồ chỉ mô tả luồng ý tưởng. DBMS cụ thể có quy tắc riêng về hàng/câu lệnh, thời điểm AFTER được xử lý, ràng buộc và các trigger lồng nhau.

## 2. Ba câu hỏi phải trả lời trước khi viết trigger

Một định nghĩa trigger đầy đủ cần xác định ít nhất:

1. **Sự kiện gì?** `INSERT`, `UPDATE`, `DELETE` hoặc sự kiện khác do DBMS hỗ trợ.
2. **Thời điểm nào?** `BEFORE`, `AFTER` hay `INSTEAD OF`.
3. **Mức nào?** **Mỗi hàng** (`FOR EACH ROW`) hay **mỗi câu lệnh** (`FOR EACH STATEMENT`/mô hình set-based).

Ví dụ PostgreSQL:

```sql
CREATE TRIGGER trg_staff_before
BEFORE INSERT OR UPDATE ON staff
FOR EACH ROW
EXECUTE FUNCTION normalize_staff();
```

Ở đây:

- Thao tác liên quan là `INSERT` hoặc `UPDATE`.
- Chạy trước khi hàng được ghi.
- Chạy một lần cho **mỗi hàng chịu tác động**, không chỉ một lần cho toàn bộ câu lệnh.

Đừng đọc riêng từ `BEFORE` và tự cho rằng nó có cùng ngữ nghĩa trên SQL Server. SQL Server không có DML trigger `BEFORE` theo cú pháp này.

## 3. Bảng đối chiếu nhanh theo hệ quản trị

| Hệ quản trị | BEFORE DML | AFTER DML | INSTEAD OF DML | Cấp kích hoạt đáng chú ý |
| --- | --- | --- | --- | --- |
| **PostgreSQL** | Có trên bảng, theo hàng/câu lệnh | Có trên bảng, theo hàng/câu lệnh | Có trên view, **theo hàng** | Có `NEW`/`OLD`, trigger function; có transition tables cho những AFTER trigger |
| **SQL Server** | **Không** có DML BEFORE trigger thông thường | Có trên bảng | Có trên **bảng hoặc view** | DML trigger là **cấp câu lệnh**, dùng `inserted`/`deleted` là các tập hàng |
| **MySQL** | Có trên bảng | Có trên bảng | **Không** | Chỉ **FOR EACH ROW** cho DML trigger |
| **Oracle Database** | Có trên bảng, theo hàng/câu lệnh | Có trên bảng, theo hàng/câu lệnh | Có trên view theo cơ chế được hỗ trợ | Có `:NEW`/`:OLD`, compound triggers, mutating-table restrictions |
| **SQLite** | Có, trên bảng | Có, trên bảng | Có, trên view | Trigger DML **theo từng hàng**, không có statement-level DML trigger |
| **MariaDB** | Có, trên bảng | Có, trên bảng | **Không** theo cơ chế MySQL/MariaDB phổ biến | Row-level; chi tiết cú pháp/phân quyền theo phiên bản |

Bảng nêu các khả năng DML chủ đạo. Một số sản phẩm còn hỗ trợ **DDL trigger**, trigger cấp database/logon, constraint trigger, trigger trên đối tượng đặc biệt hoặc cơ chế thay thế. Không nên lấy khả năng của các loại trigger khác để suy ra cú pháp DML `BEFORE`/`AFTER`/`INSTEAD OF`.

## 4. BEFORE: kiểm tra hoặc biến đổi trước khi ghi

Với trigger `BEFORE ... FOR EACH ROW` của PostgreSQL, một hàm trigger có thể nhận giá trị mới của hàng qua `NEW`, sửa chúng, rồi trả `NEW` để tiếp tục thao tác.

Ví dụ nghiệp vụ:

- Chuẩn hóa email về chữ thường và bỏ khoảng trắng ở đầu/cuối.
- Điền thời điểm cập nhật khi ghi.
- Kiểm tra dữ liệu mới và từ chối nếu không hợp lệ.
- Áp dụng một phép biến đổi nhất quán trước khi dữ liệu đi vào bảng.

Tuy nhiên, **trigger không phải cách thay thế mặc định cho ràng buộc**. Các điều kiện đơn giản như `salary >= 0` nên có `CHECK` hoặc cấu trúc schema phù hợp; trigger chỉ nên bổ sung logic mà ràng buộc trực tiếp không thể diễn đạt thuận tiện.

### BEFORE không đồng nghĩa “chưa bắt đầu transaction”

Trigger được thực thi trong ngữ cảnh statement/transaction của lệnh phát sinh. Nó không chạy bên ngoài giao dịch chỉ vì mang tên BEFORE.

Nếu transaction sau đó `ROLLBACK`, những thay đổi database do BEFORE trigger thực hiện cũng thường bị rollback theo tính nguyên tử của hệ lưu trữ giao dịch.

### BEFORE không nhất thiết là một bản ghi cuối cùng đã hợp lệ

Các cơ chế khác như DEFAULT, generated columns, các trigger BEFORE khác, ràng buộc hoặc thay đổi do DBMS có thể ảnh hưởng thứ tự xử lý. Không nên giả định có thể kiểm tra mọi trạng thái cuối cùng chỉ bằng một BEFORE trigger mà bỏ qua constraint và khả năng tương tác.

## 5. AFTER: ghi nhận điều đã diễn ra, nhưng chưa có nghĩa đã COMMIT

`AFTER` thường dùng khi cần phản ứng với một thay đổi đã được thực hiện ở cấp xử lý tương ứng của DBMS:

- Ghi audit trong database.
- Cập nhật bảng tổng hợp hoặc quan hệ phụ thuộc.
- Ghi một sự kiện vào **outbox table** cho ứng dụng gửi sau commit.
- Kiểm tra điều kiện tổng hợp khi DBMS và thiết kế trigger cho phép.
- Đồng bộ metadata hoặc bảng con theo một quy tắc rõ ràng.

Điểm cực kỳ quan trọng:

**AFTER trigger không phải “AFTER COMMIT trigger”.**

Ví dụ:

```text
BEGIN
  UPDATE staff SET monthly_salary = 1200 WHERE staff_id = 101
    └─ AFTER UPDATE trigger chèn bản ghi audit
ROLLBACK
```

Nếu cả bảng staff và audit nằm trong cùng database/transaction phù hợp, rollback sẽ hoàn tác cả sửa lương và bản ghi audit.

Một audit dùng để truy vết **các thay đổi đã commit** có thể dựa vào việc rollback nhất quán này. Nhưng nếu muốn ghi mọi **lần thử thất bại** hoặc mọi thao tác bị rollback, audit transaction thông thường **không tự đáp ứng mục tiêu đó**; cần cơ chế log phù hợp, độc lập với rollback và được thiết kế cẩn trọng.

### AFTER không cho quyền sửa tùy ý NEW

Ở PostgreSQL, giá trị trả về từ hàm trigger `AFTER ROW` bị bỏ qua về mục đích thay đổi hàng; nó không phải nơi để sửa `NEW` như BEFORE ROW. Trong Oracle, `:NEW` trong AFTER ROW không được gán như trong BEFORE ROW. Các hệ có quy tắc tương ứng khác nhau.

Nếu cần chuẩn hóa dữ liệu **trước khi lưu**, hãy dùng BEFORE ở DBMS hỗ trợ, hoặc thiết kế cập nhật tường minh ở phía ứng dụng/lớp ghi.

## 6. INSTEAD OF: định nghĩa cách thực hiện DML thay cho đối tượng được ghi

`INSTEAD OF` có vai trò rất khác: nó không đơn thuần chạy sớm hơn AFTER, mà **thay cho hành động DML thông thường trên đối tượng gắn trigger**.

Giả sử một view kết hợp nhân viên và phòng ban:

```sql
CREATE VIEW staff_directory AS
SELECT s.staff_id, s.email, s.monthly_salary, d.department_name
FROM staff AS s
JOIN departments AS d
  ON d.department_id = s.department_id;
```

Ứng dụng muốn:

```sql
UPDATE staff_directory
SET monthly_salary = 1200
WHERE staff_id = 101;
```

Một join view thường không tự có quy tắc rõ ràng để thay đổi tất cả cột đến từ nhiều bảng. `INSTEAD OF UPDATE` có thể định nghĩa:

1. Bảng nguồn nào được phép cập nhật.
2. Khóa nào xác định đúng một nhân viên.
3. Cột nào trên view là chỉ đọc.
4. Điều kiện từ chối một cập nhật không hợp lệ.
5. Cách phản hồi số hàng được xử lý.

Nếu trigger không tự thực hiện thao tác cập nhật cần thiết, **DBMS không mặc định tự thực hiện phần UPDATE bảng gốc thay cho bạn** chỉ vì trigger đã chạy.

### INSTEAD OF không tương đương BEFORE

Một `BEFORE` trên bảng thường tham gia vào đường ghi mặc định. Một `INSTEAD OF` nhận trách nhiệm **thực hiện thay** phần việc mà DML định làm. Vì vậy, định nghĩa sai có thể khiến câu lệnh “thành công” nhưng không có dữ liệu bảng gốc nào thay đổi.

---

## 7. Row-level và statement-level: hai chiều độc lập với timing

Một câu lệnh:

```sql
UPDATE staff
SET monthly_salary = monthly_salary * 1.05
WHERE department_id = 10;
```

có thể sửa **500 hàng**.

### Row-level

Trigger `FOR EACH ROW` có thể được kích hoạt **500 lần** cho 500 hàng đó. Mỗi lần có ngữ cảnh hàng tương ứng như `OLD` và `NEW`, tùy sự kiện/DBMS.

### Statement-level

Trigger theo câu lệnh được kích hoạt **một lần** cho statement đó, không phải 500 lần. Nếu cần xử lý các hàng chịu tác động, hệ như SQL Server cung cấp `inserted`/`deleted`, còn PostgreSQL có **transition tables** cho một số AFTER triggers.

| Tình huống | Row-level | Statement-level |
| --- | --- | --- |
| UPDATE tác động 500 hàng | Có thể chạy 500 lần | Chạy một lần cho câu UPDATE |
| UPDATE tác động 0 hàng | Không có hàng để kích hoạt row trigger | Statement trigger vẫn có thể chạy theo ngữ nghĩa của DBMS |
| Chuẩn hóa riêng từng email | Thường hợp với BEFORE ROW | Cần thiết kế set-based hoặc logic khác |
| Ghi một bản audit cho toàn batch | Có thể tạo 500 bản ghi nếu không kiểm soát | Có thể gom batch nếu hệ hỗ trợ truy cập tập hàng |
| SQL Server | Không có DML row-level trigger | Có DML statement-level triggers |

**Một trigger `AFTER` không tự nói nó là theo hàng hay theo câu lệnh.** Phải kiểm tra cú pháp và DBMS.

## 8. OLD, NEW và bảng tạm logic của trigger

Để biết giá trị trước/sau, mỗi hệ có cơ chế riêng:

| Sản phẩm/ngữ cảnh | Hàng cũ | Hàng mới |
| --- | --- | --- |
| PostgreSQL ROW | `OLD.column` | `NEW.column` |
| Oracle ROW | `:OLD.column` | `:NEW.column` |
| MySQL ROW | `OLD.column` | `NEW.column` |
| SQLite ROW | `OLD.column` | `NEW.column` |
| SQL Server DML | Bảng logic `deleted` | Bảng logic `inserted` |

### Quan hệ với thao tác DML

| Thao tác | Dữ liệu cũ | Dữ liệu mới |
| --- | --- | --- |
| `INSERT` | Không có hàng cũ cho hàng mới | Có hàng mới |
| `UPDATE` | Có hàng trước sửa | Có hàng sau sửa |
| `DELETE` | Có hàng bị xóa | Không có hàng mới |

Đừng cố truy cập `OLD` như một hàng có ý nghĩa trong `INSERT` hoặc `NEW` như hàng có ý nghĩa trong `DELETE`.

Đối với SQL Server, `inserted` và `deleted` là **các tập hàng**, không phải hai biến vô hướng. Một câu lệnh có thể làm thay đổi nhiều hàng hoặc không hàng nào.

### Giá trị của một cột có thật sự thay đổi không?

`UPDATE salary = salary` vẫn là một câu UPDATE. Một trigger có thể chạy dù giá trị được gán bằng giá trị cũ.

Để chỉ hành động khi dữ liệu khác thật, cần so sánh cũ/mới. PostgreSQL có:

```sql
OLD.monthly_salary IS DISTINCT FROM NEW.monthly_salary
```

Cách này xử lý `NULL` rõ hơn `OLD.value <> NEW.value`. Ngôn ngữ và cách so sánh NULL khác nhau theo DBMS.

---

## 9. Thực hành PostgreSQL: chuẩn bị bảng và dữ liệu

Các ví dụ ở các mục 9–20 dùng **PostgreSQL**. Chạy trong một **schema/database lab riêng**, không dùng trên bảng sản xuất.

Để quan sát trigger, chúng ta tạo:

- `lab_departments_351`: phòng ban.
- `lab_staff_351`: nhân viên.
- `lab_staff_audit_351`: nhật ký dữ liệu.
- Một **BEFORE ROW trigger** chuẩn hóa email và cập nhật timestamp.
- Một **AFTER ROW trigger** ghi audit.
- Một **INSTEAD OF UPDATE trigger** trên join view.

Tạo bảng:

```sql
CREATE TABLE lab_departments_351 (
    department_id   INTEGER PRIMARY KEY,
    department_name TEXT NOT NULL UNIQUE
);

CREATE TABLE lab_staff_351 (
    staff_id       INTEGER PRIMARY KEY,
    department_id  INTEGER NOT NULL
                   REFERENCES lab_departments_351(department_id),
    email          TEXT NOT NULL UNIQUE,
    monthly_salary NUMERIC(12, 2) NOT NULL
                   CHECK (monthly_salary >= 0),
    active         BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE lab_staff_audit_351 (
    audit_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    staff_id    INTEGER NOT NULL,
    operation   TEXT NOT NULL,
    old_salary  NUMERIC(12, 2),
    new_salary  NUMERIC(12, 2),
    changed_at  TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO lab_departments_351 (
    department_id, department_name
)
VALUES
    (10, 'Engineering'),
    (20, 'Operations');
```

Bảng audit **không có foreign key buộc `staff_id` còn tồn tại**. Đây là chủ ý của ví dụ: bản audit về nhân viên đã bị xóa vẫn có thể được giữ theo chính sách retention. Trong hệ thật, phải xác định trách nhiệm bảo mật và lưu giữ các dữ liệu này.

## 10. PostgreSQL BEFORE INSERT OR UPDATE FOR EACH ROW

Hàm trigger viết bằng PL/pgSQL:

```sql
CREATE OR REPLACE FUNCTION lab_staff_normalize_fn_351()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.email := lower(btrim(NEW.email));

    IF NEW.email = '' THEN
        RAISE EXCEPTION
            'Email không được để trống sau chuẩn hóa';
    END IF;

    NEW.updated_at := clock_timestamp();

    RETURN NEW;
END;
$$;
```

Định nghĩa trigger:

```sql
CREATE TRIGGER lab_staff_before_write_351
BEFORE INSERT OR UPDATE ON lab_staff_351
FOR EACH ROW
EXECUTE FUNCTION lab_staff_normalize_fn_351();
```

### Giải thích

- `BEFORE INSERT OR UPDATE`: chạy trước thao tác chèn hoặc sửa.
- `FOR EACH ROW`: mỗi hàng chịu tác động gọi hàm riêng.
- `NEW.email`: giá trị email mà hàng sắp có.
- `lower(btrim(...))`: chuyển chữ thường và bỏ khoảng trắng hai đầu.
- `NEW.updated_at`: ghi thời điểm thực thi trigger.
- `RETURN NEW`: cho PostgreSQL tiếp tục xử lý hàng với các giá trị đã sửa.

### RETURN NEW, OLD hoặc NULL có ý nghĩa gì?

Trong PostgreSQL, ở **BEFORE ROW trigger** đối với `INSERT`/`UPDATE`, `RETURN NEW` thường là lựa chọn đúng để tiếp tục thao tác đã sửa.

Trả `NULL` từ một BEFORE ROW trigger có thể **bỏ qua thao tác trên hàng đó**. Đây là hành vi mạnh, có thể làm số hàng cập nhật thấp hơn dự kiến và ảnh hưởng các trigger sau.

Đối với BEFORE DELETE, hàm thường trả `OLD` để tiếp tục xóa, hoặc `NULL` để bỏ qua hàng. Không dùng `RETURN NEW` như một mẫu chung cho mọi event mà không xét `TG_OP`.

### Khi nào nên từ chối bằng RAISE?

Một `RAISE EXCEPTION` làm câu lệnh lỗi và giao dịch đi vào trạng thái lỗi theo quy tắc PostgreSQL (cần rollback hoặc rollback tới savepoint phù hợp). Nó khác **`RETURN NULL`**, vốn bỏ qua hàng theo cơ chế trigger mà không phải là một ngoại lệ cùng kiểu.

Nếu một giá trị bắt buộc phải hợp lệ, **constraint hoặc ngoại lệ** thường minh bạch hơn việc lặng lẽ bỏ qua hàng sai.

---

## 11. PostgreSQL AFTER INSERT/UPDATE/DELETE FOR EACH ROW

Tạo hàm ghi audit:

```sql
CREATE OR REPLACE FUNCTION lab_staff_audit_fn_351()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO lab_staff_audit_351 (
            staff_id, operation, old_salary, new_salary
        )
        VALUES (
            NEW.staff_id, 'INSERT', NULL, NEW.monthly_salary
        );

    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO lab_staff_audit_351 (
            staff_id, operation, old_salary, new_salary
        )
        VALUES (
            NEW.staff_id, 'UPDATE',
            OLD.monthly_salary, NEW.monthly_salary
        );

    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO lab_staff_audit_351 (
            staff_id, operation, old_salary, new_salary
        )
        VALUES (
            OLD.staff_id, 'DELETE', OLD.monthly_salary, NULL
        );
    END IF;

    -- Với AFTER ROW trigger của PostgreSQL,
    -- giá trị trả về không dùng để thay hàng đích.
    RETURN NULL;
END;
$$;
```

Đăng ký trigger:

```sql
CREATE TRIGGER lab_staff_after_write_351
AFTER INSERT OR UPDATE OR DELETE ON lab_staff_351
FOR EACH ROW
EXECUTE FUNCTION lab_staff_audit_fn_351();
```

### TG_OP là gì?

Trong hàm trigger PostgreSQL, `TG_OP` biểu thị thao tác kích hoạt: `INSERT`, `UPDATE`, `DELETE` hoặc `TRUNCATE` trong ngữ cảnh thích hợp.

Bằng cách phân nhánh, ta tránh truy cập `OLD` trong `INSERT` hoặc `NEW` trong `DELETE`.

### AFTER có nghĩa giá trị đã được chuẩn hóa

Một hàng INSERT vào `lab_staff_351` sẽ đi qua BEFORE trigger chuẩn hóa email, sau đó được ghi; AFTER trigger thấy trạng thái mới trong ngữ cảnh xử lý tương ứng.

Tuy nhiên, một AFTER trigger không phải bằng chứng transaction đã commit. Nếu giao dịch rollback, bản ghi audit cùng transaction cũng rollback.

### Audit cho mọi UPDATE hay chỉ UPDATE lương?

Hàm trên ghi audit **mỗi UPDATE hàng**, kể cả chỉ đổi `active` hoặc gán lại cùng `monthly_salary`. Nếu nghiệp vụ chỉ muốn audit những lần lương thực sự đổi, có thể tạo **một trigger khác** hoặc thêm điều kiện:

```sql
WHEN (OLD.monthly_salary IS DISTINCT FROM NEW.monthly_salary)
```

Ví dụ:

```sql
-- Mẫu minh họa, không tạo thêm trigger trùng chức năng
-- trên bảng lab đang dùng.
CREATE TRIGGER salary_change_only
AFTER UPDATE ON some_staff_table
FOR EACH ROW
WHEN (OLD.monthly_salary IS DISTINCT FROM NEW.monthly_salary)
EXECUTE FUNCTION some_salary_audit_function();
```

Phải phân biệt **sự kiện UPDATE đã chạy** với **giá trị cột thật sự đổi**.

---

## 12. Thực thi INSERT và UPDATE trong lab PostgreSQL

Tạo hai nhân viên sau khi đã đăng ký BEFORE/AFTER triggers:

```sql
INSERT INTO lab_staff_351 (
    staff_id, department_id, email, monthly_salary, active
)
VALUES
    (101, 10, '  AN@EXAMPLE.TEST  ', 1000.00, TRUE),
    (102, 20, 'Binh@Example.Test', 1500.00, TRUE);
```

Đọc bảng:

```sql
SELECT staff_id, department_id, email,
       monthly_salary, active, updated_at
FROM lab_staff_351
ORDER BY staff_id;
```

Email của nhân viên 101 trở thành `an@example.test` và 102 thành `binh@example.test`.

Kiểm tra audit:

```sql
SELECT staff_id, operation, old_salary, new_salary
FROM lab_staff_audit_351
ORDER BY audit_id;
```

Vì có hai INSERT, bảng audit có hai hàng `INSERT` nếu không có thao tác nào khác.

### UPDATE trong transaction thử nghiệm

```sql
BEGIN;

UPDATE lab_staff_351
SET monthly_salary = 1200.00
WHERE staff_id = 101;

SELECT staff_id, email, monthly_salary
FROM lab_staff_351
WHERE staff_id = 101;

SELECT staff_id, operation, old_salary, new_salary
FROM lab_staff_audit_351
ORDER BY audit_id;

ROLLBACK;
```

Trong transaction, audit có thêm hàng `UPDATE` cho 101, `old_salary=1000` và `new_salary=1200`. Sau `ROLLBACK`, cả sửa lương lẫn bản audit phát sinh bởi UPDATE đều được hoàn tác.

### Kiểm tra ràng buộc

```sql
-- KHÔNG chạy trong transaction có công việc khác chưa commit:
-- Câu này có chủ đích gây lỗi CHECK.
--
-- INSERT INTO lab_staff_351
--     (staff_id, department_id, email, monthly_salary)
-- VALUES
--     (103, 10, 'bad@example.test', -5);
```

`CHECK (monthly_salary >= 0)` bảo vệ dữ liệu dù logic kiểm tra tương đương không có trong BEFORE trigger.

---

## 13. PostgreSQL INSTEAD OF UPDATE trên join view

Join view thường không tự có quy tắc cập nhật các bảng gốc trong mọi trường hợp. Ta sẽ định nghĩa chính sách rõ ràng:

- Cho phép đổi `email`, `monthly_salary`, `active`.
- Không cho đổi `staff_id`, `department_id` hoặc `department_name` qua view.
- Tìm nhân viên bằng `OLD.staff_id`.
- Gọi UPDATE bảng gốc, nhờ đó các BEFORE/AFTER triggers của **bảng gốc** vẫn được kích hoạt.

Tạo view:

```sql
CREATE VIEW lab_staff_directory_351 AS
SELECT
    s.staff_id,
    s.department_id,
    d.department_name,
    s.email,
    s.monthly_salary,
    s.active
FROM lab_staff_351 AS s
JOIN lab_departments_351 AS d
  ON d.department_id = s.department_id;
```

Tạo hàm INSTEAD OF:

```sql
CREATE OR REPLACE FUNCTION lab_staff_directory_update_fn_351()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.staff_id IS DISTINCT FROM OLD.staff_id
       OR NEW.department_id IS DISTINCT FROM OLD.department_id
       OR NEW.department_name IS DISTINCT FROM OLD.department_name
    THEN
        RAISE EXCEPTION
            'Không cho đổi khóa nhân viên/phòng ban qua view';
    END IF;

    UPDATE lab_staff_351 AS s
    SET email          = NEW.email,
        monthly_salary = NEW.monthly_salary,
        active         = NEW.active
    WHERE s.staff_id = OLD.staff_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    RETURN NEW;
END;
$$;
```

Gắn trigger trên **view**:

```sql
CREATE TRIGGER lab_staff_directory_instead_update_351
INSTEAD OF UPDATE ON lab_staff_directory_351
FOR EACH ROW
EXECUTE FUNCTION lab_staff_directory_update_fn_351();
```

### Chạy thử

```sql
BEGIN;

UPDATE lab_staff_directory_351
SET email = '  AN.NEW@EXAMPLE.TEST  ',
    monthly_salary = 1250.00
WHERE staff_id = 101;

SELECT staff_id, email, monthly_salary
FROM lab_staff_351
WHERE staff_id = 101;

SELECT staff_id, operation, old_salary, new_salary
FROM lab_staff_audit_351
WHERE staff_id = 101
ORDER BY audit_id;

ROLLBACK;
```

Trong transaction:

1. UPDATE trên view kích hoạt `INSTEAD OF UPDATE`.
2. Hàm thực hiện UPDATE trên `lab_staff_351`.
3. BEFORE trigger của **bảng** chuẩn hóa email thành `an.new@example.test`.
4. AFTER trigger của **bảng** ghi một hàng audit cho 101.
5. `ROLLBACK` hoàn tác thay đổi bảng gốc và audit.

### Giá trị RETURN NEW của INSTEAD OF trong PostgreSQL

Đối với `INSTEAD OF ROW`, trả một hàng khác `NULL` (thường là `NEW` khi INSERT/UPDATE; `OLD` khi DELETE) báo rằng hàng đã được xử lý, ảnh hưởng số hàng được tính và một số hành vi `RETURNING`. Trả `NULL` biểu thị không thực hiện thao tác cho hàng view đó.

**Lưu ý:** `RETURN NEW` từ hàm view không nhất thiết đã mang mọi giá trị chuẩn hóa cuối cùng mà BEFORE trigger trên bảng gốc thay đổi. Nếu cần trả chính xác giá trị thực đã lưu, phải thiết kế logic `RETURNING`/đọc lại dữ liệu phù hợp, không mặc định dữ liệu trả về từ view luôn là bản mới nhất đã chuẩn hóa.

### Vì sao phải ngăn sửa department_name?

`department_name` đến từ bảng `lab_departments_351`. Cho phép một lệnh đổi tên phòng ban thông qua một hàng nhân viên có thể vô tình đổi tên phòng ban cho **mọi nhân viên thuộc phòng đó**. Trigger phải chỉ rõ các cột có thể sửa và định danh bảng gốc phù hợp.

---

## 14. PostgreSQL: BEFORE/AFTER theo câu lệnh

PostgreSQL hỗ trợ **statement-level trigger**. Ví dụ ta muốn ghi thông báo mỗi khi có một statement UPDATE trên `lab_staff_351`, kể cả khi câu lệnh không khớp hàng nào.

```sql
CREATE OR REPLACE FUNCTION lab_staff_update_statement_fn_351()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE
        'Câu UPDATE đã được thực thi trên %',
        TG_TABLE_NAME;

    RETURN NULL;
END;
$$;

CREATE TRIGGER lab_staff_after_update_stmt_351
AFTER UPDATE ON lab_staff_351
FOR EACH STATEMENT
EXECUTE FUNCTION lab_staff_update_statement_fn_351();
```

Thử:

```sql
UPDATE lab_staff_351
SET monthly_salary = monthly_salary
WHERE staff_id = -1;
```

Không có nhân viên `-1`, nên:

- **Row-level UPDATE** triggers trên staff không chạy cho hàng nào.
- **Statement-level AFTER UPDATE** trigger vẫn chạy theo sự kiện statement.

Điều này quan trọng khi trigger dùng để gửi tín hiệu “đã có thay đổi” hay kiểm soát batch: **một statement UPDATE không đồng nghĩa đã sửa ít nhất một hàng**.

### Không dùng statement trigger để đo số hàng bằng TG_OP

`TG_OP = 'UPDATE'` chỉ cho biết loại thao tác, **không cho biết có bao nhiêu hàng**.

Nếu muốn xử lý tập hàng đã thay đổi, PostgreSQL có **transition relations** cho một số AFTER triggers, được giải thích ở mục tiếp theo.

---

## 15. PostgreSQL transition tables cho AFTER triggers

Với những trường hợp được PostgreSQL hỗ trợ, `REFERENCING OLD TABLE` hoặc `NEW TABLE` cho phép một **AFTER trigger** truy cập **tập các hàng** cũ/mới của statement, thay vì tự truy vấn lại bảng nguồn một cách mơ hồ.

Ví dụ với UPDATE:

```sql
CREATE OR REPLACE FUNCTION lab_staff_update_batch_fn_351()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    updated_count BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO updated_count
    FROM new_rows;

    RAISE NOTICE
        'Số hàng nhân viên trong transition table: %',
        updated_count;

    RETURN NULL;
END;
$$;

CREATE TRIGGER lab_staff_after_update_batch_351
AFTER UPDATE ON lab_staff_351
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION lab_staff_update_batch_fn_351();
```

Nếu UPDATE tác động 20 hàng, `new_rows` đại diện tập hàng mới liên quan tới statement đó.

### Lưu ý về giới hạn

- Transition tables chỉ có trong những loại AFTER trigger và đối tượng đủ điều kiện theo PostgreSQL.
- Đối với `UPDATE` dùng transition relations, không viết thêm danh sách cột `UPDATE OF col1,...` trên chính trigger đó theo các giới hạn PostgreSQL.
- Không áp dụng mẫu này cho mọi loại constraint trigger/view/foreign table.
- Các kiểu trigger khác và phiên bản khác có giới hạn cụ thể.

### Có cần cả hai statement trigger ở mục 14–15?

Không. Chúng được tạo riêng để minh họa hai mục đích. Trên hệ thống thật, tránh gắn nhiều trigger chỉ để cùng báo một sự kiện mà không có nhu cầu rõ ràng.

---

## 16. PostgreSQL: nhiều trigger cùng loại và thứ tự thực thi

Nếu nhiều trigger PostgreSQL **cùng loại, cùng event** trên một đối tượng, PostgreSQL thực hiện chúng **theo thứ tự tên trigger** theo quy tắc của hệ.

Ví dụ:

```text
BEFORE UPDATE:
  a_normalize_email
  b_set_updated_at
  c_validate_business_rule
```

Người viết có thể nhận thấy thứ tự tên đó ảnh hưởng logic khi một trigger biến đổi `NEW` và trigger khác kiểm tra `NEW`.

Tuy vậy, dựa vào thứ tự tên trigger để thực hiện một chuỗi nghiệp vụ phức tạp thường tạo ra sự phụ thuộc giòn. Khi logic phải đi liền nhau và thứ tự là yêu cầu nghiệp vụ, cân nhắc **gộp vào một hàm có các bước minh bạch**, hoặc thiết kế luồng ghi ở tầng ứng dụng/transaction.

**Không đem quy tắc sắp thứ tự theo tên của PostgreSQL sang MySQL, Oracle hoặc SQL Server.** Các hệ có cơ chế và tùy chọn quản lý thứ tự trigger riêng; một số hỗ trợ `FOLLOWS`/`PRECEDES` hoặc “first/last”, với giới hạn tương ứng.

## 17. PostgreSQL constraint trigger và thời điểm hoãn

PostgreSQL có **constraint trigger** trong những trường hợp được hỗ trợ. Đây là một dạng đặc biệt:

- Là `AFTER ROW` trigger trên bảng.
- Có thể được thiết lập **DEFERRABLE** để hoãn thời điểm thực thi tới cuối transaction hoặc lúc chuyển chế độ constraint.
- Phù hợp một số kiểm tra ràng buộc phức tạp cần nhìn trạng thái rộng hơn.

Nó khác trigger `AFTER` thông thường, vốn không nên bị hiểu thành “trigger luôn chạy khi COMMIT”.

Ví dụ khái niệm:

```sql
-- Cú pháp minh họa PostgreSQL, hàm trigger phải tồn tại:
--
-- CREATE CONSTRAINT TRIGGER check_business_rule
-- AFTER INSERT OR UPDATE ON some_table
-- DEFERRABLE INITIALLY DEFERRED
-- FOR EACH ROW
-- EXECUTE FUNCTION validate_cross_row_rule();
```

Không phải mọi kiểm tra logic nhiều bảng đều có thể được triển khai an toàn bằng một constraint trigger tự viết; cần xét concurrency và isolation. Nếu có thể diễn đạt bằng **FOREIGN KEY, UNIQUE, CHECK, EXCLUDE** hoặc ràng buộc cơ sở dữ liệu khác, thường nên ưu tiên cơ chế khai báo.

---

## 18. SQL Server: không có BEFORE DML trigger, có AFTER và INSTEAD OF

Trong SQL Server, cú pháp DML trigger thường có dạng:

```sql
CREATE TRIGGER trigger_name
ON schema_name.table_name
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    -- logic set-based
END;
```

hoặc:

```sql
CREATE TRIGGER trigger_name
ON schema_name.view_or_table_name
INSTEAD OF UPDATE
AS
BEGIN
    -- tự thực hiện thao tác thay thế
END;
```

**SQL Server không có cú pháp `BEFORE INSERT/UPDATE/DELETE` DML trigger tương ứng với PostgreSQL/MySQL.**

Nếu cần kiểm tra giá trị trước khi dữ liệu được lưu, lựa chọn có thể là:

- `CHECK`, `UNIQUE`, `FOREIGN KEY` và kiểu dữ liệu.
- Validation tại ứng dụng hoặc stored procedure ghi dữ liệu.
- `INSTEAD OF` trigger, khi thật sự muốn chặn đường DML mặc định rồi tự điều khiển việc ghi.
- Thiết kế bảng và quyền ghi đảm bảo mọi đường thay đổi đều đi qua quy tắc được phép.

Đừng mặc định `INSTEAD OF` là một bản dịch không có khác biệt của `BEFORE`: nó thay đổi trách nhiệm thực thi DML.

## 19. SQL Server inserted và deleted là **tập hàng**

Giả sử bảng SQL Server:

```sql
-- SQL Server: chạy trong database thử nghiệm.
CREATE TABLE dbo.lab_staff_351 (
    staff_id INT NOT NULL PRIMARY KEY,
    email NVARCHAR(320) NOT NULL UNIQUE,
    monthly_salary DECIMAL(12, 2) NOT NULL
);
GO

CREATE TABLE dbo.lab_staff_audit_351 (
    audit_id BIGINT IDENTITY(1, 1) NOT NULL PRIMARY KEY,
    staff_id INT NOT NULL,
    operation NVARCHAR(10) NOT NULL,
    old_salary DECIMAL(12, 2) NULL,
    new_salary DECIMAL(12, 2) NULL
);
GO
```

Tạo AFTER trigger xử lý nhiều hàng cùng lúc:

```sql
CREATE OR ALTER TRIGGER dbo.lab_staff_after_351
ON dbo.lab_staff_351
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.lab_staff_audit_351 (
        staff_id, operation, old_salary, new_salary
    )
    SELECT
        COALESCE(i.staff_id, d.staff_id),
        CASE
            WHEN i.staff_id IS NOT NULL
             AND d.staff_id IS NOT NULL THEN N'UPDATE'
            WHEN i.staff_id IS NOT NULL THEN N'INSERT'
            ELSE N'DELETE'
        END,
        d.monthly_salary,
        i.monthly_salary
    FROM inserted AS i
    FULL OUTER JOIN deleted AS d
      ON i.staff_id = d.staff_id;
END;
GO
```

### Ý nghĩa của các bảng logic

- Với `INSERT`: `inserted` chứa các hàng mới, `deleted` rỗng.
- Với `DELETE`: `deleted` chứa các hàng cũ, `inserted` rỗng.
- Với `UPDATE`: `deleted` chứa hình ảnh hàng trước sửa, `inserted` chứa hình ảnh sau sửa.

Trong ví dụ, `staff_id` được giả định **không thay đổi**. Nếu ứng dụng cho phép UPDATE khóa định danh, việc nối old/new theo chính khóa đang thay đổi không còn là cách chung an toàn; cần thiết kế audit và quy tắc cập nhật khóa riêng.

### Vì sao không viết SELECT vào biến vô hướng?

Một cách viết không an toàn:

```sql
-- KHÔNG dùng làm audit nhiều hàng:
-- DECLARE @staff_id INT;
-- SELECT @staff_id = staff_id FROM inserted;
-- INSERT INTO audit (...) VALUES (@staff_id, ...);
```

Khi câu `UPDATE` tác động 500 nhân viên, `inserted` có thể có 500 hàng. Gán vào biến như trên không xử lý đúng từng hàng; nó dễ bỏ sót dữ liệu.

**DML trigger SQL Server chạy ở cấp statement.** Viết logic **set-based**, luôn nghĩ `inserted`/`deleted` có thể chứa 0, 1 hoặc nhiều hàng.

### UPDATE tác động 0 hàng

SQL Server DML trigger có thể được kích hoạt bởi statement dù không sửa hàng nào. Trong trường hợp đó, `inserted` và `deleted` rỗng; câu `INSERT ... SELECT` ở ví dụ thêm 0 audit rows.

Nếu trigger có việc khác tốn kém, có thể kiểm tra không có hàng:

```sql
IF NOT EXISTS (SELECT 1 FROM inserted)
   AND NOT EXISTS (SELECT 1 FROM deleted)
    RETURN;
```

Đừng xem sự kiện trigger được gọi là bằng chứng chắc chắn đã thay đổi dữ liệu.

---

## 20. SQL Server INSTEAD OF trên view và table

SQL Server cho phép `INSTEAD OF` DML trigger trên **view và table**, không chỉ trên view như cơ chế PostgreSQL được dùng trong bài.

Ví dụ view trên bảng demo:

```sql
CREATE VIEW dbo.lab_staff_public_351
AS
SELECT staff_id, email, monthly_salary
FROM dbo.lab_staff_351;
GO
```

Tạo INSTEAD OF UPDATE:

```sql
CREATE OR ALTER TRIGGER dbo.lab_staff_public_update_351
ON dbo.lab_staff_public_351
INSTEAD OF UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF UPDATE(staff_id)
        THROW 50001, 'Không cho cập nhật staff_id qua view', 1;

    UPDATE s
    SET s.email = i.email,
        s.monthly_salary = i.monthly_salary
    FROM dbo.lab_staff_351 AS s
    JOIN inserted AS i
      ON i.staff_id = s.staff_id;
END;
GO
```

Các điểm cần nhớ:

- `inserted` đại diện tập giá trị đề xuất cho **toàn statement**.
- `UPDATE(staff_id)` kiểm tra cột có được **đề cập trong SET** hay không, **không bảo đảm giá trị đã thật sự khác**.
- Trigger tự chạy UPDATE trên bảng gốc; nếu không có câu đó, không có cập nhật bảng gốc mặc định tương đương.
- Các quy tắc về trigger nesting, recursion, constraint, hành vi DML thông qua view phụ thuộc SQL Server và cần được xem xét khi triển khai.

Ví dụ dùng một view đơn giản cho dễ thấy bản chất `INSTEAD OF`. Với view join phức tạp, cần xác định đầy đủ đường ánh xạ các cột về bảng gốc và quan hệ một-nhiều trước khi thực thi update.

### SQL Server AFTER trên view?

Trong SQL Server, **AFTER DML trigger không được dùng trên view** như trên bảng; với view, hướng thường gặp là `INSTEAD OF`.

Vì vậy, câu “tạo `AFTER UPDATE ON view`” là một lỗi khi chuyển từ một mô hình trigger tưởng tượng sang SQL Server.

---

## 21. MySQL: BEFORE/AFTER FOR EACH ROW, không có INSTEAD OF

MySQL hỗ trợ trigger DML trên bảng theo thời điểm `BEFORE` hoặc `AFTER`, và chỉ có mức **`FOR EACH ROW`**.

Ví dụ MySQL với bảng thử nghiệm:

```sql
CREATE TABLE lab_staff_mysql_351 (
    staff_id INT NOT NULL PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    monthly_salary DECIMAL(12, 2) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE lab_staff_audit_mysql_351 (
    audit_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    staff_id INT NOT NULL,
    operation VARCHAR(10) NOT NULL,
    old_salary DECIMAL(12, 2) NULL,
    new_salary DECIMAL(12, 2) NULL
) ENGINE = InnoDB;
```

### MySQL BEFORE INSERT: gán NEW

Trong MySQL CLI hoặc công cụ hỗ trợ `DELIMITER`:

```sql
DELIMITER $$

CREATE TRIGGER lab_staff_before_insert_mysql_351
BEFORE INSERT ON lab_staff_mysql_351
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));

    IF NEW.monthly_salary < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Lương không được âm';
    END IF;
END$$

DELIMITER ;
```

`DELIMITER` là **lệnh của client** để đổi ký hiệu kết thúc statement khi nhập trigger nhiều câu, không phải một phần của SQL được server thực thi như câu DML thông thường. API/driver có thể gửi toàn bộ định nghĩa trigger mà không cần lệnh client này.

Ở BEFORE trigger MySQL, có thể gán `NEW.email` theo quy tắc của sản phẩm; `OLD` là giá trị cũ ở UPDATE/DELETE và không được sửa theo cách tương đương.

### MySQL AFTER INSERT: ghi audit

```sql
DELIMITER $$

CREATE TRIGGER lab_staff_after_insert_mysql_351
AFTER INSERT ON lab_staff_mysql_351
FOR EACH ROW
BEGIN
    INSERT INTO lab_staff_audit_mysql_351 (
        staff_id, operation, old_salary, new_salary
    )
    VALUES (
        NEW.staff_id, 'INSERT', NULL, NEW.monthly_salary
    );
END$$

DELIMITER ;
```

Thử:

```sql
INSERT INTO lab_staff_mysql_351 (
    staff_id, email, monthly_salary
)
VALUES (
    101, '  AN@EXAMPLE.TEST  ', 1000.00
);

SELECT * FROM lab_staff_mysql_351;
SELECT * FROM lab_staff_audit_mysql_351;
```

Email được chuẩn hóa trước khi chèn; audit có một dòng INSERT nếu lệnh thành công.

### UPDATE cần trigger tương ứng

Định nghĩa `BEFORE INSERT` **không tự chạy khi UPDATE**. Muốn chuẩn hóa email trong UPDATE, phải tạo trigger `BEFORE UPDATE` riêng hoặc dùng một quy tắc ghi khác.

### MySQL không có INSTEAD OF cho view

MySQL hỗ trợ **updatable views** trong những trường hợp đủ điều kiện theo quy tắc riêng của MySQL, nhưng **không có DML INSTEAD OF trigger** để tự cài đặt hành vi cập nhật một join view phức tạp giống PostgreSQL/SQL Server.

Nếu cần ghi dữ liệu qua view phức tạp, có thể thiết kế stored procedure/API hoặc đường ghi vào bảng gốc được kiểm soát, thay vì cố sao chép `INSTEAD OF UPDATE ON view`.

---

## 22. MySQL: một số giới hạn trigger quan trọng

### 22.1. Không có statement-level DML trigger

Câu:

```sql
UPDATE lab_staff_mysql_351
SET monthly_salary = monthly_salary + 100;
```

nếu sửa 100 hàng, trigger `BEFORE/AFTER UPDATE FOR EACH ROW` có thể chạy cho từng hàng; không có cú pháp tương đương `FOR EACH STATEMENT` cho DML trigger MySQL.

### 22.2. Không nên cập nhật lại chính bảng đang kích hoạt

MySQL có hạn chế với việc trigger hoặc stored function sửa bảng đang được câu lệnh gọi dùng, và có thể báo lỗi kiểu không thể cập nhật bảng đã được sử dụng bởi statement. Ví dụ ý tưởng:

```sql
-- Không làm theo mẫu này trong AFTER UPDATE trên staff:
-- UPDATE staff SET ... WHERE staff_id = NEW.staff_id;
```

Nếu chỉ muốn thay đổi giá trị hàng đang INSERT/UPDATE, `BEFORE ROW` với `SET NEW.col = ...` thường là hướng phù hợp hơn.

### 22.3. Trigger và transaction

Với bảng InnoDB, DML của trigger tham gia giao dịch tương ứng; lỗi trong trigger có thể làm statement thất bại. MySQL trigger cũng có giới hạn đối với các thao tác quản lý transaction như `COMMIT`/`ROLLBACK` bên trong trigger.

Không nên viết trigger phát email trực tiếp rồi kỳ vọng hành động ngoài database sẽ tự rollback nếu statement thất bại.

### 22.4. INSERT ... ON DUPLICATE KEY UPDATE

Với MySQL upsert, các giai đoạn BEFORE INSERT và nhánh xử lý xung đột UPDATE có thể làm các trigger tương ứng tham gia theo quy tắc sản phẩm. Không nên giả định một câu upsert là **hoặc chỉ INSERT trigger hoặc chỉ UPDATE trigger** ở mọi thời điểm.

Đặc biệt khi trigger ghi audit hoặc thay đổi dữ liệu, hãy kiểm tra diễn biến **upsert xung đột khóa**, kể cả batch nhiều hàng, thay vì chỉ thử INSERT và UPDATE độc lập.

### 22.5. TRUNCATE không phải DELETE từng hàng

`TRUNCATE TABLE` trong MySQL là thao tác có ngữ nghĩa khác `DELETE FROM table`, và **không kích hoạt DELETE triggers như một câu DELETE từng hàng**. Nếu audit phụ thuộc DELETE trigger, phải xác định rõ chính sách với TRUNCATE.

---

## 23. MariaDB: tương tự MySQL nhưng kiểm tra phiên bản

MariaDB hỗ trợ `BEFORE` và `AFTER` DML row-level triggers trên bảng, có `OLD`/`NEW` theo thao tác. Trong các phiên bản phổ biến, MariaDB không cung cấp `INSTEAD OF` DML trigger như PostgreSQL/SQL Server.

Tuy nhiên, MariaDB và MySQL là **hai sản phẩm tách biệt**. Những chi tiết như:

- Tạo nhiều trigger cùng thời điểm/sự kiện.
- Tùy chọn `FOLLOWS`/`PRECEDES`.
- DDL, quyền DEFINER và metadata.
- Cú pháp, thứ tự thực thi và tác động của các câu UPSERT/REPLACE.

cần được kiểm tra trên phiên bản đang triển khai. Không suy rằng “cùng dùng cú pháp MySQL” là mọi trigger đều có hành vi giống nhau.

---

## 24. Oracle: BEFORE và AFTER theo hàng hoặc câu lệnh

Oracle Database hỗ trợ trigger DML `BEFORE` và `AFTER` ở **statement level** hoặc **row level**. Cú pháp `FOR EACH ROW` quyết định row-level.

Ví dụ Oracle với bảng `staff` đã tồn tại:

```sql
CREATE OR REPLACE TRIGGER staff_normalize_351
BEFORE INSERT OR UPDATE ON staff
FOR EACH ROW
BEGIN
    :NEW.email := LOWER(TRIM(:NEW.email));

    IF :NEW.monthly_salary < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Lương không được âm'
        );
    END IF;
END;
/
```

Trong Oracle:

- `:NEW.email` và `:OLD.email` là các **correlation pseudorecord fields** cho row trigger.
- Có thể thay đổi giá trị `:NEW` trong **BEFORE ROW** đối với những trường hợp cho phép.
- Các toán tử PL/SQL, cách phát lỗi và dấu `/` để thực thi trong một số client khác PostgreSQL.

### Oracle AFTER ROW audit

```sql
CREATE OR REPLACE TRIGGER staff_audit_351
AFTER INSERT OR UPDATE OR DELETE ON staff
FOR EACH ROW
BEGIN
    IF INSERTING THEN
        INSERT INTO staff_audit (
            staff_id, operation, old_salary, new_salary
        )
        VALUES (
            :NEW.staff_id, 'INSERT', NULL, :NEW.monthly_salary
        );

    ELSIF UPDATING THEN
        INSERT INTO staff_audit (
            staff_id, operation, old_salary, new_salary
        )
        VALUES (
            :NEW.staff_id, 'UPDATE',
            :OLD.monthly_salary, :NEW.monthly_salary
        );

    ELSIF DELETING THEN
        INSERT INTO staff_audit (
            staff_id, operation, old_salary, new_salary
        )
        VALUES (
            :OLD.staff_id, 'DELETE', :OLD.monthly_salary, NULL
        );
    END IF;
END;
/
```

Bảng `staff` và `staff_audit` ở đây là đối tượng Oracle **giả định** có các cột phù hợp; ví dụ Oracle không được chạy trực tiếp vào schema PostgreSQL đã tạo ở mục 9.

### Statement trigger Oracle

Nếu bỏ `FOR EACH ROW`, một trigger DML có thể chạy ở cấp statement. Trong ngữ cảnh statement-level, không dùng `:NEW.column`/`:OLD.column` như một hàng riêng lẻ; cần thiết kế cơ chế xử lý khác.

---

## 25. Oracle: INSTEAD OF trigger trên view

Với view phức tạp, Oracle có `INSTEAD OF` trigger theo hàng để định nghĩa DML.

Ví dụ schema Oracle giả định có:

```sql
CREATE OR REPLACE VIEW v_staff_directory_351 AS
SELECT
    s.staff_id,
    s.email,
    s.monthly_salary,
    d.department_name
FROM staff s
JOIN departments d
  ON d.department_id = s.department_id;
```

Định nghĩa cách update chỉ các cột nhân viên:

```sql
CREATE OR REPLACE TRIGGER v_staff_directory_update_351
INSTEAD OF UPDATE ON v_staff_directory_351
FOR EACH ROW
BEGIN
    UPDATE staff
    SET email = :NEW.email,
        monthly_salary = :NEW.monthly_salary
    WHERE staff_id = :OLD.staff_id;
END;
/
```

Trong hệ thống thật, trigger cần thêm validation để từ chối sửa `staff_id` hoặc `department_name` qua view, kiểm tra số hàng nguồn thực sự khớp và xử lý quyền truy cập. Ví dụ tối giản để nhấn mạnh cú pháp và chức năng thay thế.

### INSTEAD OF không tự chuyển thành BEFORE trên bảng gốc

Trigger trên view là đường nhận DML. Câu UPDATE bảng `staff` được chạy **bên trong trigger** mới làm phát sinh các trigger DML của chính bảng `staff`.

Oracle có các quy tắc riêng đối với loại view, editioning views và tính đủ điều kiện của INSTEAD OF trigger. Không khái quát rằng mọi view Oracle đều cho định nghĩa mọi loại trigger theo cùng một cú pháp.

---

## 26. Oracle mutating table và compound trigger

Một rủi ro Oracle quan trọng là **mutating-table error**, thường gặp dưới dạng `ORA-04091`.

Ví dụ ý tưởng: một row trigger trên `staff` cố truy vấn chính `staff` để tính tổng lương của toàn phòng trong lúc câu UPDATE nhiều hàng đang chạy:

```sql
-- Ý tưởng dễ gặp vấn đề trong Oracle row trigger:
-- SELECT SUM(monthly_salary)
-- INTO some_total
-- FROM staff
-- WHERE department_id = :NEW.department_id;
```

Tùy loại thao tác và cơ chế Oracle, việc đọc/sửa lại bảng đang bị statement thay đổi trong row trigger có thể bị từ chối để tránh nhìn trạng thái không nhất quán.

Oracle có **compound trigger**, cho phép kết hợp các phần như:

- `BEFORE STATEMENT`
- `BEFORE EACH ROW`
- `AFTER EACH ROW`
- `AFTER STATEMENT`

trong một định nghĩa trigger có trạng thái chung của statement, khi điều kiện hỗ trợ cho phép.

### Compound trigger giải quyết điều gì?

Một mẫu thường dùng là:

1. Thu thập các khóa chịu tác động tại phần row-level.
2. Sau khi statement kết thúc phần sửa hàng, xử lý tập khóa tại `AFTER STATEMENT`.
3. Tránh đọc lại bảng đang mutating ở ngay row-level theo cách không hợp lệ.

Nhưng compound trigger không tự giải quyết mọi vấn đề về race condition, hiệu năng hoặc ràng buộc nghiệp vụ. Nếu nhiệm vụ chỉ là kiểm tra đơn giản từng hàng, `CHECK` hoặc BEFORE ROW trigger có thể ít phức tạp hơn.

---

## 27. SQLite: BEFORE, AFTER và INSTEAD OF nhưng chỉ row-level

SQLite hỗ trợ các loại DML trigger theo thời điểm `BEFORE`, `AFTER` và `INSTEAD OF`. Tuy nhiên, SQLite hỗ trợ **FOR EACH ROW**, không có DML statement-level trigger tổng quát như PostgreSQL hoặc Oracle.

Ví dụ SQLite:

```sql
CREATE TABLE lab_staff_sqlite_351 (
    staff_id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    monthly_salary NUMERIC NOT NULL
);

CREATE TABLE lab_staff_audit_sqlite_351 (
    staff_id INTEGER NOT NULL,
    operation TEXT NOT NULL,
    old_salary NUMERIC,
    new_salary NUMERIC
);

CREATE TRIGGER lab_staff_after_insert_sqlite_351
AFTER INSERT ON lab_staff_sqlite_351
FOR EACH ROW
BEGIN
    INSERT INTO lab_staff_audit_sqlite_351 (
        staff_id, operation, old_salary, new_salary
    )
    VALUES (
        NEW.staff_id, 'INSERT', NULL, NEW.monthly_salary
    );
END;
```

### SQLite INSTEAD OF trên view

```sql
CREATE VIEW lab_staff_public_sqlite_351 AS
SELECT staff_id, email
FROM lab_staff_sqlite_351;

CREATE TRIGGER lab_staff_public_insert_sqlite_351
INSTEAD OF INSERT ON lab_staff_public_sqlite_351
FOR EACH ROW
BEGIN
    INSERT INTO lab_staff_sqlite_351 (
        staff_id, email, monthly_salary
    )
    VALUES (
        NEW.staff_id,
        lower(trim(NEW.email)),
        0
    );
END;
```

Thử:

```sql
INSERT INTO lab_staff_public_sqlite_351 (
    staff_id, email
)
VALUES (
    101, '  AN@EXAMPLE.TEST  '
);

SELECT staff_id, email, monthly_salary
FROM lab_staff_sqlite_351
WHERE staff_id = 101;
```

Kết quả: hàng được chèn vào **bảng gốc**, với email thường và lương mặc định theo quy tắc trigger là 0.

### SQLite BEFORE không có cách gán NEW như PostgreSQL/MySQL

SQLite cung cấp `NEW.column`/`OLD.column` để **đọc giá trị** trong biểu thức trigger, nhưng không hỗ trợ cú pháp `SET NEW.email = ...` như MySQL hoặc `NEW.email := ...` như PL/pgSQL.

Nếu cần tự động biến đổi giá trị mới, cân nhắc:

- Default/generated column khi đủ yêu cầu.
- Validation bằng `CHECK` hoặc trigger `RAISE()`.
- Quy định ứng dụng phải đưa giá trị đã chuẩn hóa.
- `INSTEAD OF` trigger trên view ghi vào bảng gốc theo dữ liệu đã chuyển đổi.
- Một mô hình ghi tường minh khác.

SQLite còn cảnh báo về hành vi không xác định trong một số trường hợp BEFORE trigger **tự sửa/xóa chính hàng** mà statement gốc đang định sửa. Theo hướng dẫn SQLite, thường nên ưu tiên AFTER khi không cần thực sự chặn trước thao tác.

---

## 28. SQLite: từ chối dữ liệu với RAISE

Ví dụ BEFORE INSERT kiểm tra lương:

```sql
CREATE TRIGGER lab_staff_salary_check_sqlite_351
BEFORE INSERT ON lab_staff_sqlite_351
FOR EACH ROW
WHEN NEW.monthly_salary < 0
BEGIN
    SELECT RAISE(ABORT, 'Lương không được âm');
END;
```

Nếu một INSERT gửi lương âm, trigger làm statement lỗi theo quy tắc `RAISE(ABORT, ...)`.

Tuy nhiên, trong schema thật nên cân nhắc khai báo:

```sql
monthly_salary NUMERIC NOT NULL CHECK (monthly_salary >= 0)
```

để bảo vệ giá trị bất kể đường ghi. Trigger hữu ích hơn khi có logic theo ngữ cảnh hoặc tác vụ không diễn đạt được gọn bằng CHECK.

### SQLite và số hàng bị ảnh hưởng

Với `INSTEAD OF` trigger trên view, cách API SQLite báo số hàng thay đổi có những đặc điểm riêng; không nên dùng `sqlite3_changes()`/`changes()` một cách ngây thơ để kết luận hàng view đã được lưu vào bảng gốc như thế nào.

Đối với hệ thống cần audit, nên quan sát thay đổi bảng gốc và tự thiết kế kết quả nghiệp vụ rõ ràng.

---

## 29. So sánh ví dụ “chuẩn hóa email” theo hệ quản trị

Cùng yêu cầu: khi ghi nhân viên, email được trim và chuyển thường.

| DBMS | Cách tiếp cận phù hợp | Lưu ý |
| --- | --- | --- |
| PostgreSQL | `BEFORE INSERT OR UPDATE FOR EACH ROW`, sửa `NEW.email` và trả `NEW` | Dùng trigger function PL/pgSQL |
| MySQL | `BEFORE INSERT` và `BEFORE UPDATE FOR EACH ROW`, `SET NEW.email = ...` | Mỗi event cần định nghĩa trigger tương ứng; không có INSTEAD OF view |
| Oracle | `BEFORE INSERT OR UPDATE FOR EACH ROW`, gán `:NEW.email := ...` | Dùng PL/SQL và correlation fields |
| SQLite | Ứng dụng hoặc view `INSTEAD OF`, generated/constraint theo yêu cầu; BEFORE có thể từ chối | Không dùng cú pháp gán `NEW` của MySQL |
| SQL Server | Validation/normalization ở lớp ghi hoặc `INSTEAD OF` trigger/set-based logic | Không có DML BEFORE trigger; `inserted` là nhiều hàng |

**Không có một đoạn SQL "dùng được ở mọi DBMS" cho BEFORE trigger.** Phải chọn đúng ngữ nghĩa và công cụ của hệ đích.

---

## 30. Một trigger có thể kích hoạt nhiều trigger khác

Ví dụ PostgreSQL:

```text
UPDATE view
  └─ INSTEAD OF UPDATE ON view
       └─ UPDATE staff
            ├─ BEFORE UPDATE ON staff
            └─ AFTER UPDATE ON staff
                 └─ INSERT staff_audit
                      └─ AFTER INSERT ON staff_audit (nếu có)
```

Đây là **chuỗi trigger lồng nhau**. Nếu logic vòng lại bảng ban đầu mà không có điểm dừng, có thể tạo **đệ quy**, chồng nhiều thao tác hoặc gây lỗi.

### Những nguy cơ

- Trigger A cập nhật bảng B; trigger B cập nhật ngược A.
- Một UPDATE đơn lẻ biến thành nhiều đợt UPDATE lặp.
- Audit trigger cũng bị audit bởi trigger khác.
- Deadlock vì hai transaction kích hoạt chuỗi khóa theo thứ tự khác nhau.
- Một nhánh trigger dựa trên dữ liệu tạm chưa commit hoặc kiểm tra thiếu khóa.
- Thời gian transaction tăng vì quá nhiều tác vụ đồng bộ.

### Hướng xử lý

- Tránh làm các bước cập nhật đệ quy khi có thể.
- Thiết kế rõ **hướng phụ thuộc** giữa bảng nghiệp vụ và bảng audit/outbox.
- Dùng khóa xác định và điều kiện ngăn xử lý lặp theo nghiệp vụ.
- Giữ trigger ngắn, có thể dự đoán và có đường xử lý lỗi rõ.
- Nếu DBMS có tùy chọn bật/tắt recursive triggers, chỉ sử dụng sau khi hiểu hệ quả của toàn bộ luồng ghi.

Không nên chỉ kiểm tra "trigger này chạy đúng một lần trên một hàng" rồi bỏ qua tác dụng khi có trigger khác hoặc một câu DML nhiều hàng.

---

## 31. Trigger và transaction: cùng một câu lệnh không phải sau commit

Một lời giải thích nhất quán cho nhiều DBMS giao dịch:

```text
Transaction T
  BEGIN
    UPDATE staff
      BEFORE / thao tác ghi / AFTER
      INSERT outbox_event (từ trigger)
  ...
  COMMIT hoặc ROLLBACK
```

Nếu UPDATE và INSERT outbox thuộc cùng transaction, chúng cùng thành công hoặc cùng rollback theo khả năng của database/storage engine.

### Vì sao không gửi email ngay trong AFTER trigger?

Nếu một trigger gọi dịch vụ ngoài để gửi email hoặc HTTP request trước COMMIT:

1. Dịch vụ bên ngoài có thể đã nhận/sent thành công.
2. Transaction database sau đó có thể rollback.
3. Email vẫn đã gửi, nhưng thay đổi dữ liệu không tồn tại.

Database không tự rollback một email hoặc HTTP response.

### Transactional outbox

Một thiết kế phổ biến:

1. AFTER trigger hoặc code ứng dụng chèn một **outbox event** trong cùng transaction với thay đổi.
2. Transaction COMMIT.
3. Worker độc lập đọc event đã commit và gửi tới hệ thống ngoài.
4. Worker đánh dấu xử lý, có retry và **idempotency key**.

Cách này tránh việc gửi thông báo ngoài transaction từ trigger và giúp hệ thống xử lý lỗi, dù vẫn phải giải quyết việc gửi trùng do retry.

### Audit của thao tác thất bại

Nếu yêu cầu ghi nhận **lệnh bị từ chối** (ví dụ cố sửa lương âm), audit trong trigger cùng transaction có thể cũng rollback. Khi đó cần chiến lược **security/application logging** phù hợp, không chỉ một AFTER DML trigger.

---

## 32. BEFORE, AFTER và ràng buộc dữ liệu

Một câu hỏi quan trọng: “Nên dùng trigger hay constraint?”

| Yêu cầu | Công cụ thường nên ưu tiên |
| --- | --- |
| Mã nhân viên duy nhất | `PRIMARY KEY`/`UNIQUE` |
| Lương không âm | `CHECK` và `NOT NULL` nếu phù hợp |
| Phòng ban phải tồn tại | `FOREIGN KEY` |
| Email không rỗng | `NOT NULL` cùng CHECK/validation phù hợp |
| Chuẩn hóa email khi ghi | Lớp ghi/BEFORE trigger nếu DBMS hỗ trợ |
| Ghi old/new salary khi đổi | AFTER audit trigger hoặc cơ chế audit chuyên dụng |
| DML vào join view với chính sách riêng | INSTEAD OF trigger ở DBMS hỗ trợ |
| Một invariant phức tạp nhiều hàng | Thiết kế transaction, constraint phù hợp, isolation/locking; trigger có thể tham gia |

### Tại sao CHECK thường tốt hơn trigger cho điều kiện đơn giản?

- Được engine quản lý như một phần schema.
- Khó bỏ sót một nhánh INSERT/UPDATE riêng.
- Mô tả yêu cầu dữ liệu một cách khai báo.
- Ít có logic ẩn gây bất ngờ cho ứng dụng.

Tuy nhiên, ràng buộc khai báo cũng có giới hạn. Một `CHECK` trong nhiều hệ quản trị không được dùng để tùy ý truy vấn tổng của bảng khác; đó là vấn đề thiết kế invariant và concurrency rộng hơn.

### Không được để trigger "chữa" dữ liệu sai một cách im lặng

Ví dụ: lương âm được tự đổi thành 0 mà không thông báo. Điều này có thể làm hệ thống báo thành công dù dữ liệu gửi bị lỗi. Trong những nghiệp vụ nghiêm ngặt, nên **từ chối** giá trị sai và trả lỗi rõ ràng.

---

## 33. Khi trigger chạy với INSERT, UPDATE, DELETE nhiều hàng

Một statement SQL thường thay đổi nhiều hàng, không phải một:

```sql
UPDATE lab_staff_351
SET monthly_salary = monthly_salary * 1.10
WHERE department_id = 10;
```

### PostgreSQL/MySQL/Oracle/SQLite ROW trigger

Mỗi hàng bị tác động có thể tạo một lần gọi trigger theo quy tắc của hệ. Nếu statement sửa 10.000 hàng, logic trigger có thể làm việc 10.000 lần.

Nếu mỗi trigger row lại thực hiện:

```sql
SELECT SUM(monthly_salary) FROM staff;
```

thì chi phí có thể cực lớn. Ở Oracle còn có rủi ro mutating table.

### SQL Server

Một statement kích hoạt trigger một lần với `inserted`/`deleted` chứa **10.000 hàng**. Một SQL trigger viết chỉ xử lý một dòng từ `inserted` sẽ bỏ sót hàng loạt thay đổi.

### PostgreSQL AFTER transition table

Có thể xử lý tập hàng tại AFTER statement trong những trường hợp đủ điều kiện, giúp giảm thao tác theo từng hàng.

### Bảng chi phí ý tưởng

| Khối lượng UPDATE | Row-level trigger | Statement-level/set-based trigger |
| ---: | --- | --- |
| 1 hàng | Thường đơn giản | Tương đối đơn giản |
| 100 hàng | 100 lần gọi logic từng hàng | Một lần xử lý tập dữ liệu |
| 100.000 hàng | Dễ tạo chi phí lặp rất lớn | Có thể xử lý set-based, nhưng vẫn cần index, memory, transaction sizing |
| 0 hàng | Không có row trigger | Statement trigger có thể vẫn chạy |

**Set-based không có nghĩa tự động nhanh trong mọi trường hợp**; nó mở cơ hội viết các phép tổng hợp/ghi hàng loạt hiệu quả hơn, nhưng cần kế hoạch thực thi và ngữ nghĩa đúng.

---

## 34. Trigger, audit và tính truy vết

Một bảng audit có thể ghi:

```text
audit_id | operation | staff_id | old_salary | new_salary | changed_at
---------+-----------+----------+------------+------------+----------------
1        | INSERT    | 101      | NULL       | 1000       | ...
2        | UPDATE    | 101      | 1000       | 1200       | ...
3        | DELETE    | 102      | 1500       | NULL       | ...
```

Nhưng audit đáng tin cậy còn cần nhiều quyết định:

- Ghi **ai thực hiện**: database role, application user, request ID?
- Giữ **transaction ID hoặc correlation ID** nào?
- Ghi **giá trị nào**: trước/sau, trường thay đổi, version?
- Có dữ liệu nhạy cảm không? Có cần mã hóa hoặc hạn chế quyền?
- Audit có phải giữ cả thao tác rollback hay chỉ thay đổi đã commit?
- Quyền sửa/xóa bản audit được giới hạn thế nào?
- Nếu trigger bị disable hoặc DML đi qua một thao tác đặc biệt, audit có bị bỏ qua không?
- Khi schema thêm cột, audit có được cập nhật phù hợp không?

Một AFTER trigger ghi audit là khởi điểm tốt cho thay đổi đã commit **trong một đường ghi cụ thể**, nhưng không phải toàn bộ hệ thống kiểm toán theo yêu cầu pháp lý.

### Không chỉ dựa vào thời gian hệ thống để xác định thứ tự tuyệt đối

Hai bản audit có timestamp rất gần nhau; một transaction có thể bắt đầu trước nhưng commit sau. Nếu cần thứ tự commit đáng tin cậy, phải thiết kế theo metadata/commit log hoặc cơ chế thích hợp, không suy trực tiếp từ `clock_timestamp()` hoặc một ID sequence.

---

## 35. Trigger và các thao tác đặc biệt: UPSERT, MERGE, TRUNCATE

### UPSERT

PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` hoặc MySQL `INSERT ... ON DUPLICATE KEY UPDATE` có thể làm phát sinh **kết hợp các giai đoạn trigger INSERT/UPDATE** theo ngữ nghĩa sản phẩm. Đừng nghĩ rằng chỉ vì kết quả cuối là UPDATE thì **không có BEFORE INSERT trigger nào đã chạy**.

Với PostgreSQL, logic `BEFORE INSERT ROW` có thể ảnh hưởng giá trị `EXCLUDED` sử dụng trong nhánh conflict. Còn statement-level triggers trên INSERT/UPDATE có quy tắc kích hoạt riêng.

### MERGE

`MERGE` có thể xử lý nhiều loại thao tác trên cùng một nguồn/đích theo điều kiện. Từng DBMS có quy tắc trigger khác nhau. Trong SQL Server, không nên giả định thứ tự kích hoạt các AFTER triggers cho nhiều action trong `MERGE` là một thứ tự nghiệp vụ cố định.

Nếu audit dựa trên triggers, hãy kiểm tra riêng **các nhánh INSERT/UPDATE/DELETE của MERGE**, tập hàng và thứ tự xử lý.

### TRUNCATE

`TRUNCATE` không phải `DELETE` từng hàng. Trong PostgreSQL có **TRUNCATE statement-level trigger** riêng (`BEFORE/AFTER TRUNCATE`), chứ không nên mong nó chạy mọi DELETE ROW trigger.

Trong MySQL và SQL Server, `TRUNCATE TABLE` không kích hoạt DELETE trigger như một `DELETE` thông thường. Trên các DBMS khác cần kiểm tra quy tắc tương ứng.

Nếu audit, replication hoặc business rules cần ghi nhận việc xóa toàn bộ bảng, phải quy định rõ **có cho phép TRUNCATE hay không**, và xử lý quyền/đường ghi riêng.

---

## 36. Trigger và thứ tự nhiều thao tác bên trong một statement

Một câu UPDATE nhiều hàng không bảo đảm xử lý hàng theo `staff_id ASC` chỉ vì index đang sắp như vậy. Vì thế:

- Không ghi logic trigger ROW phụ thuộc vào “nhân viên 101 sẽ được xử lý trước 102”.
- Không dùng `MAX(audit_id)` để suy rằng một cập nhật nhiều hàng có một thứ tự nghiệp vụ được định trước.
- Nếu cần xử lý các hàng theo thứ tự cụ thể, phải xây dựng quy trình có tính thứ tự và transaction phù hợp ngoài việc dựa vào thứ tự scan.
- Statement-level trigger có tập dữ liệu, nhưng **tập hàng không tự có thứ tự** nếu không có `ORDER BY` ở câu truy vấn đọc tập đó theo cách được hỗ trợ.
- Nhiều trigger cùng event có quy tắc thứ tự riêng theo DBMS; đừng phụ thuộc ngầm nếu có thể tránh.

### Trường hợp cần đánh số sự kiện

Nếu ứng dụng cần thứ tự sự kiện, nên dùng một cơ chế cấp sequence/version có hợp đồng rõ và hiểu khác biệt giữa **thứ tự cấp ID** và **thứ tự commit**. Sequence tăng không nhất thiết phản ánh commit order.

---

## 37. Trigger và vấn đề đồng thời

Giả sử AFTER trigger duy trì bảng tổng lương theo phòng ban:

```text
department_id | total_salary
--------------+-------------
10            | 100000
```

Khi 100 nhân viên được cập nhật đồng thời, mọi transaction có thể phải khóa **cùng một hàng tổng hợp** cho department 10. Điều này tạo **hot row contention**, dù thao tác cập nhật từng nhân viên trên các hàng khác nhau.

### Rủi ro

- Tăng lock wait và transaction duration.
- Deadlock khi trigger chạm nhiều bảng theo thứ tự khác nhau.
- Tăng WAL/redo và số lượng cập nhật.
- Kết quả tổng hợp sai nếu logic delta không xử lý đúng UPDATE/DELETE/đổi department.
- Retry làm lặp tác động nếu ứng dụng có tác dụng phụ ngoài transaction.

### Các hướng thiết kế

- Chỉ dùng trigger để duy trì tổng khi yêu cầu đồng bộ mạnh và chi phí chấp nhận được.
- Tính delta **old → new** đúng với mọi thao tác.
- Dùng câu UPDATE tổng hợp nguyên tử và transaction đồng bộ.
- Phân vùng/điều tiết hot keys nếu cần.
- Với báo cáo chấp nhận trễ, xem xét materialized view hoặc pipeline tổng hợp theo batch.
- Đo p95/p99 latency ghi, lock waits, deadlocks và chi phí trigger.

Trigger không thể tự sửa thiếu sót về mức cô lập hoặc ràng buộc doanh nghiệp. Nó chỉ là một điểm thực thi SQL tự động.

---

## 38. Tránh thay đổi ẩn và vấn đề bảo trì

Trigger có ưu điểm **áp dụng logic tại database**, kể cả khi nhiều ứng dụng khác nhau cùng ghi. Nhưng nó cũng làm luồng ghi khó nhìn thấy từ phía application code.

Một developer có thể nhìn thấy:

```sql
INSERT INTO staff (staff_id, email, monthly_salary)
VALUES (101, 'An@Example.Test', 1000);
```

nhưng không thấy ngay:

- Email bị chuẩn hóa.
- Thời điểm cập nhật được ghi đè.
- Một hàng audit được tạo.
- Một bảng summary được cập nhật.
- Một trigger khác gọi tiếp UPDATE.
- Có thể bị từ chối bởi một quy tắc SQL/PLSQL ẩn.

### Để trigger dễ bảo trì

1. Đặt tên theo **bảng + timing + event + mục đích**, ví dụ `trg_staff_bi_normalize_email`.
2. Lưu định nghĩa trigger trong migration/version control của hệ thống.
3. Mô tả bảng nào bị ghi và điều kiện nào phát lỗi.
4. Ghi rõ xử lý nhiều hàng, `NULL` và rollback.
5. Giữ logic ngắn, tránh gọi ra mạng và xử lý kéo dài.
6. Có báo cáo/metrics cho lỗi trigger và latency ghi.
7. Không dựa vào hành vi thứ tự không được bảo đảm.
8. Xem xét quyền chạy function/trigger và nguy cơ privilege escalation.

### PostgreSQL SECURITY DEFINER

Hàm trigger PostgreSQL có thể được khai báo `SECURITY DEFINER` để thực thi với quyền của owner. Điều này hữu ích trong một số cơ chế kiểm soát, nhưng cũng có rủi ro bảo mật nếu `search_path` không được cố định an toàn hoặc function truy cập đối tượng ngoài ý định.

Không bật `SECURITY DEFINER` chỉ để “trigger hết lỗi permission” khi chưa thiết kế quyền và phân quyền rõ ràng.

---

## 39. Những câu hỏi khi chuyển trigger từ DBMS này sang DBMS khác

Một định nghĩa trong PostgreSQL:

```sql
CREATE TRIGGER trg_normalize
BEFORE INSERT OR UPDATE ON staff
FOR EACH ROW
EXECUTE FUNCTION normalize_staff();
```

không thể copy sang SQL Server. Muốn chuyển đúng phải hỏi:

- **Có BEFORE không?** SQL Server: không có DML BEFORE trigger.
- **Có row-level không?** SQL Server: DML trigger chạy một lần theo statement, phải xử lý `inserted`/`deleted` set-based.
- **Có sửa trực tiếp NEW không?** PostgreSQL/MySQL/Oracle có cách thích hợp với BEFORE ROW; SQLite/SQL Server không giống.
- **View có INSTEAD OF không?** PostgreSQL, Oracle, SQL Server, SQLite có nhưng mức và đối tượng khác nhau; MySQL không.
- **AFTER khi nào chạy và đã commit chưa?** Không đồng nhất với COMMIT; cần hiểu transaction và các deferred mechanisms.
- **Constraint, trigger nesting, recursion và privileges khác nhau thế nào?**
- **UPSERT/MERGE/TRUNCATE có tác động trigger ra sao?**
- **Có phải mỗi statement chỉ sửa một hàng không?** Đây thường là giả định nguy hiểm nhất khi chuyển mã sang SQL Server.

Cách chuyển đúng là chuyển **hợp đồng nghiệp vụ và dữ liệu**, không phải dịch từng từ khóa.

---

## 40. Bảng tổng hợp lựa chọn timing theo mục tiêu

| Mục tiêu | Timing thường hợp lý | Vì sao |
| --- | --- | --- |
| Chuẩn hóa `NEW.email` trước khi ghi | **BEFORE ROW**, nếu DBMS hỗ trợ sửa NEW | Giữ dữ liệu cuối cùng nhất quán trước DML |
| Từ chối giá trị vi phạm quy tắc đơn giản | **Constraint**; BEFORE/INSTEAD OF nếu cần logic bổ sung | Constraint là hợp đồng dữ liệu khai báo |
| Ghi audit old/new sau thay đổi | **AFTER** trên bảng | Lấy hình ảnh cũ/mới theo trigger context |
| Duy trì bảng tổng hợp theo mỗi statement lớn | **AFTER statement/transition table**, nếu hỗ trợ, hoặc thiết kế batch | Hạn chế logic lặp theo từng hàng |
| Cập nhật join view bằng quy tắc riêng | **INSTEAD OF** trên view ở DBMS hỗ trợ | DML mặc định chưa thể suy ra đường ghi mong muốn |
| Chặn một đường ghi trước rồi tự làm nhiều bước | **INSTEAD OF** trên bảng/view nếu sản phẩm hỗ trợ và có lý do | Cần tự đảm nhận thao tác ghi |
| Gửi email **sau commit** | **Outbox + worker** hoặc cơ chế sau commit chuyên biệt | AFTER DML không đồng nghĩa đã COMMIT |
| Kiểm tra invariant nhiều bảng cuối transaction | Ràng buộc/transaction/isolation, có thể constraint trigger | Không thể chỉ đổi timing là đủ |
| Audit cả các lần thử bị rollback | Cơ chế logging riêng được thiết kế | Audit cùng transaction thường rollback theo |
| Tăng tốc thao tác ghi có trigger nặng | Đánh giá logic trigger, batch/kiến trúc | Timing không tự làm trigger chạy nhanh |

---

## 41. Những lỗi thường gặp

| Lỗi | Giải thích | Hướng khắc phục |
| --- | --- | --- |
| Viết `BEFORE UPDATE` trên SQL Server | SQL Server không có DML BEFORE trigger | Constraint, đường ghi hoặc INSTEAD OF có chủ đích |
| Viết `INSTEAD OF UPDATE ON view` trong MySQL | MySQL không hỗ trợ trigger INSTEAD OF trên view | Stored procedure/API hoặc updatable view đủ điều kiện |
| Cho rằng SQL Server `inserted` có một hàng | DML trigger theo statement | Viết set-based cho 0/1/nhiều hàng |
| Dùng `NEW.email := ...` trong SQLite | SQLite không hỗ trợ gán NEW kiểu PL/pgSQL | Validation/ứng dụng/INSTEAD OF view |
| Dùng `SET NEW.email=...` trong PostgreSQL | Cú pháp MySQL không phải PL/pgSQL | `NEW.email := ...; RETURN NEW` |
| Dùng `:OLD` trong INSERT Oracle | Hàng cũ không có ý nghĩa cho INSERT | Phân nhánh `INSERTING/UPDATING/DELETING` |
| Dùng `NEW` trong DELETE PostgreSQL | Không có hàng mới cho DELETE | Dùng `OLD` |
| Trả `NULL` trong BEFORE PostgreSQL ngoài ý muốn | Có thể bỏ qua xử lý hàng | Trả `NEW`/`OLD` phù hợp hoặc phát lỗi rõ |
| Tưởng AFTER nghĩa đã commit | AFTER DML còn trong transaction | Outbox hoặc cơ chế sau commit riêng |
| AFTER trigger tự sửa NEW để thay hàng | AFTER ROW không phải điểm sửa NEW theo PG/Oracle | Dùng BEFORE ROW hoặc câu UPDATE được thiết kế |
| Trigger ghi audit nhưng rollback vẫn mất audit | Audit tham gia transaction | Phân biệt audit committed và attempt logging |
| UPDATE 0 hàng vẫn phát sinh log “có sửa” | Statement-level trigger vẫn có thể chạy | Kiểm tra tập affected rows |
| UPDATE 500 hàng chỉ ghi một audit | Xử lý một biến từ `inserted` SQL Server | INSERT...SELECT set-based |
| Trigger tổng hợp quét lại bảng mỗi hàng | N×chi phí truy vấn lớn; Oracle có thể mutating | Transition table/compound trigger/batch |
| INSTEAD OF trên view chạy nhưng dữ liệu không đổi | Trigger không thực hiện DML bảng gốc | Viết đường UPDATE/INSERT/DELETE rõ |
| View cho sửa department_name làm đổi cả phòng ban | Không xác định cột read-only/grain | Từ chối thay đổi không được phép |
| Trigger A gọi B rồi B gọi lại A | Đệ quy/chuỗi ghi lồng | Thiết kế dependency và điểm dừng |
| Dùng TRUNCATE kỳ vọng DELETE ROW audit | TRUNCATE có cơ chế khác | Chính sách TRUNCATE và logging riêng |
| UPSERT gây audit trùng hoặc khác dự đoán | Trigger semantics theo nhánh INSERT/UPDATE | Kiểm tra cụ thể UPSERT từng hệ |
| Tạo trigger thay cho UNIQUE/CHECK | Logic thừa, nguy cơ race/không đầy đủ | Ưu tiên ràng buộc khai báo |
| Trigger làm transaction ghi chậm | Thêm I/O, lock và số DML | Đo, đơn giản hóa, chuyển bất đồng bộ khi phù hợp |
| Chuyển mã trigger giữa hệ mà giữ nguyên ngữ nghĩa | Cấp kích hoạt và OLD/NEW khác | Dịch hợp đồng nghiệp vụ, không dịch từ khóa |

---

## 42. Bài tập thực hành

Các bài 1–13 dùng bộ dữ liệu PostgreSQL ở mục 9–15. Các bài còn lại yêu cầu phân biệt theo hệ quản trị. Hãy dự đoán số lần kích hoạt, giá trị cũ/mới và dữ liệu audit trước khi xem lời giải.

### Bài 1. Nhận diện BEFORE

Một bảng PostgreSQL có trigger `BEFORE INSERT FOR EACH ROW`, gán `NEW.email := lower(btrim(NEW.email))` rồi `RETURN NEW`. Với input `'  AN@EXAMPLE.TEST  '`, email được lưu là gì?

### Bài 2. Tác dụng của RETURN NULL

Một hàm `BEFORE INSERT ROW` PostgreSQL trả `NULL` thay vì `NEW` và không phát ngoại lệ. Thao tác với hàng đó diễn ra thế nào? Vì sao đây không phải cách kiểm tra lỗi mặc định tốt?

### Bài 3. AFTER chưa COMMIT

Trong transaction, PostgreSQL UPDATE nhân viên 101 từ lương 1000 lên 1200; AFTER ROW trigger ghi một bản audit. Sau đó transaction ROLLBACK. Bảng staff và audit giữ kết quả nào?

### Bài 4. OLD/NEW

Viết các giá trị `OLD.monthly_salary` và `NEW.monthly_salary` trong AFTER UPDATE cho nhân viên 101 khi sửa lương 1000 thành 1200. Với DELETE thì nên đọc nhân viên từ OLD hay NEW?

### Bài 5. Trigger chỉ ghi thay đổi thật

Đề xuất điều kiện `WHEN` cho PostgreSQL AFTER UPDATE ROW để chỉ ghi audit khi lương thực sự thay đổi, kể cả khi một phía là NULL trong schema khác.

### Bài 6. Row hay statement?

`UPDATE lab_staff_351 SET active = FALSE WHERE department_id=10` tác động 500 hàng giả định. Một BEFORE ROW và một AFTER STATEMENT trigger chạy bao nhiêu lần?

### Bài 7. UPDATE không khớp hàng

Trong PostgreSQL, `UPDATE ... WHERE staff_id=-1` ảnh hưởng 0 hàng. Những trigger ROW/STATEMENT nào có thể được gọi?

### Bài 8. INSTEAD OF view

Vì sao `UPDATE lab_staff_directory_351` cần ánh xạ về `lab_staff_351`? Điều gì xảy ra nếu INSTEAD OF function chỉ `RETURN NEW` mà không chạy UPDATE bảng gốc?

### Bài 9. Từ view sang bảng gốc

Lập thứ tự các giai đoạn khi `INSTEAD OF UPDATE` trên view PostgreSQL chạy `UPDATE lab_staff_351`, bảng gốc có BEFORE UPDATE và AFTER UPDATE triggers.

### Bài 10. Viết trigger BEFORE PostgreSQL

Viết hàm và trigger chuẩn hóa email trong PostgreSQL, dùng `LOWER(BTRIM(...))` và `RETURN NEW`.

### Bài 11. Audit khi DELETE

Viết nhánh `TG_OP='DELETE'` cho hàm audit PostgreSQL lưu `staff_id`, `operation='DELETE'` và lương cũ.

### Bài 12. Transition table

Trong PostgreSQL, muốn đếm toàn bộ hàng mới của một câu UPDATE trong một AFTER STATEMENT trigger, cần khai báo `REFERENCING` nào? Tại sao không dùng `TG_OP` để suy ra số hàng?

### Bài 13. Trigger và constraint

Nếu yêu cầu `monthly_salary >= 0`, vì sao nên có `CHECK` dù đã có BEFORE trigger?

### Bài 14. SQL Server không có BEFORE

Một ứng dụng SQL Server muốn tự động chuẩn hóa email trước khi ghi. Nêu ít nhất hai hướng hợp lệ thay vì dùng `BEFORE INSERT`.

### Bài 15. SQL Server inserted/deleted

Một câu `UPDATE staff SET monthly_salary=monthly_salary+100` sửa 200 hàng. Trong SQL Server, trigger AFTER UPDATE chạy mấy lần và các bảng `inserted`/`deleted` có bao nhiêu hàng?

### Bài 16. Sửa audit SQL Server sai

Đoạn `SELECT @id = staff_id FROM inserted` rồi ghi một audit đang thiếu sót gì? Viết ý tưởng truy vấn set-based thay thế.

### Bài 17. MySQL BEFORE ROW

Viết trigger MySQL `BEFORE INSERT` chuyển email mới thành chữ thường, bỏ khoảng trắng. Vì sao cần `BEFORE UPDATE` khác nếu email được sửa sau đó?

### Bài 18. MySQL và SQLite INSTEAD OF

Trong hai hệ MySQL và SQLite, hệ nào có `INSTEAD OF INSERT` trên view? Minh họa cách tạo hàng bảng gốc qua view ở hệ hỗ trợ.

### Bài 19. Oracle :NEW và compound trigger

Trong Oracle, `:NEW.monthly_salary := ...` thích hợp ở BEFORE ROW hay AFTER ROW? Vì sao query lại chính bảng đang UPDATE từ row trigger có thể dẫn tới `ORA-04091`?

### Bài 20. Trigger vs outbox

Một AFTER UPDATE trigger cố gửi email ngay cho khách khi đơn đổi trạng thái. Sau trigger, transaction rollback. Rủi ro gì và thiết kế nào an toàn hơn?

### Bài 21. TRUNCATE và DELETE

Tại sao không được mong `TRUNCATE TABLE` chạy tất cả `AFTER DELETE FOR EACH ROW` triggers? PostgreSQL có loại trigger nào để phản ứng riêng với TRUNCATE?

### Bài 22. UPSERT và kích hoạt trigger

Ứng dụng MySQL dùng `INSERT ... ON DUPLICATE KEY UPDATE`. Có an toàn không nếu audit giả định câu này chỉ gọi một loại trigger INSERT hoặc UPDATE? Giải thích.

### Bài 23. Hiệu năng trigger

Một trigger row-level mỗi lần UPDATE một nhân viên lại tính `SUM(monthly_salary)` của toàn bảng 1 triệu hàng. Khi UPDATE 10.000 nhân viên, rủi ro gì? Đề xuất hai hướng thay thế.

### Bài 24. Phân quyền

Một hàm trigger PostgreSQL được đặt `SECURITY DEFINER`, đọc bảng nhạy cảm và ghi audit. Hãy nêu hai nhóm rủi ro cần được xem xét.

### Bài 25. Chuyển hệ

Đọc yêu cầu: “Chuẩn hóa email trước khi lưu, ghi audit sau khi lưu, cho phép UPDATE qua join view”. Lập bảng ngắn cho PostgreSQL, SQL Server, MySQL, Oracle, SQLite: tính năng nào có sẵn, tính năng nào cần cách khác.

---

## 43. Gợi ý lời giải

### Bài 1

Email được lưu thành **`an@example.test`**. `BTRIM` bỏ khoảng trắng hai đầu và `LOWER` chuyển chữ thường; `RETURN NEW` tiếp tục ghi hàng mới với giá trị đã thay đổi.

### Bài 2

Trong PostgreSQL BEFORE ROW, `RETURN NULL` làm **bỏ qua thao tác với hàng đó**. Nếu đây là dữ liệu sai bắt buộc bị từ chối, việc im lặng bỏ hàng có thể khiến ứng dụng tưởng câu lệnh xử lý thành công; nên dùng constraint hoặc `RAISE EXCEPTION` với thông báo rõ.

### Bài 3

Nếu hai bảng ghi nằm trong cùng transaction PostgreSQL, `ROLLBACK` hoàn tác cả UPDATE lương và audit INSERT do trigger tạo. Nhân viên 101 vẫn có lương **1000**, và bản audit của lần UPDATE bị rollback không còn; những audit đã commit trước transaction vẫn còn.

### Bài 4

`OLD.monthly_salary=1000`, `NEW.monthly_salary=1200`. Với DELETE, dùng `OLD.staff_id` và `OLD.monthly_salary`; không dựa vào `NEW` cho hàng đã xóa.

### Bài 5

```sql
CREATE TRIGGER lab_salary_changed_example
AFTER UPDATE ON some_staff_table
FOR EACH ROW
WHEN (OLD.monthly_salary IS DISTINCT FROM NEW.monthly_salary)
EXECUTE FUNCTION some_audit_function();
```

`IS DISTINCT FROM` cho phép so sánh có ý nghĩa cả khi một phía `NULL`.

### Bài 6

Nếu tác động 500 hàng:

- BEFORE ROW: **500 lần**.
- AFTER STATEMENT: **1 lần** cho statement đó.

Số lần này giả định không có trigger khác gây ra những statement lồng nhau bổ sung.

### Bài 7

Không có hàng chịu tác động nên **không có row-level UPDATE trigger** cho hàng. Statement-level UPDATE trigger vẫn có thể được gọi theo ngữ nghĩa PostgreSQL.

### Bài 8

Join view có các cột từ `staff` và `departments`; không có quy tắc tổng quát để suy ra cột nào được phép ghi và ghi bảng nào. INSTEAD OF function phải tự UPDATE bảng gốc. Nếu chỉ `RETURN NEW` mà không thực hiện DML, thao tác trên view có thể được báo là đã xử lý về mặt trigger, nhưng **bảng gốc không đổi**.

### Bài 9

Thứ tự logic:

1. DML trên view kích hoạt **INSTEAD OF UPDATE** của view.
2. Hàm view thực hiện **UPDATE bảng `lab_staff_351`**.
3. Trên bảng gốc, **BEFORE UPDATE ROW** xử lý `NEW`.
4. Database thực hiện cập nhật bảng gốc.
5. **AFTER UPDATE ROW** trên bảng gốc ghi audit trong ngữ cảnh statement/transaction.
6. Transaction có thể COMMIT hoặc ROLLBACK.

Không nên hiểu AFTER là đã COMMIT.

### Bài 10

```sql
CREATE OR REPLACE FUNCTION normalize_email_example()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.email := LOWER(BTRIM(NEW.email));
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_normalize_email_example
BEFORE INSERT OR UPDATE ON some_staff_table
FOR EACH ROW
EXECUTE FUNCTION normalize_email_example();
```

Đây là mẫu PostgreSQL; `some_staff_table` cần tồn tại với cột email thích hợp.

### Bài 11

```sql
IF TG_OP = 'DELETE' THEN
    INSERT INTO lab_staff_audit_351 (
        staff_id, operation, old_salary, new_salary
    )
    VALUES (
        OLD.staff_id, 'DELETE', OLD.monthly_salary, NULL
    );
END IF;
```

Hàm phải là trigger function được gọi ở ngữ cảnh phù hợp.

### Bài 12

```sql
CREATE TRIGGER update_batch_example
AFTER UPDATE ON some_staff_table
REFERENCING NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION some_batch_function();
```

Trong function, dùng `SELECT COUNT(*) FROM new_rows`. `TG_OP='UPDATE'` chỉ cho biết loại statement, không đếm các hàng.

### Bài 13

`CHECK (monthly_salary >= 0)` là ràng buộc khai báo giúp bảo vệ dữ liệu cho mọi đường INSERT/UPDATE theo cơ chế DBMS, không cần lặp kiểm tra trong từng nhánh trigger. Trigger có thể thêm kiểm tra nghiệp vụ riêng nhưng không nên thay CHECK đơn giản.

### Bài 14

Các hướng:

- Chuẩn hóa trong ứng dụng/stored procedure kiểm soát đường ghi.
- Dùng `INSTEAD OF INSERT/UPDATE` trên table/view với logic set-based và tự thực hiện DML.
- Kết hợp constraint và schema phù hợp cho validation.

SQL Server không có DML `BEFORE INSERT` tương đương PostgreSQL/MySQL.

### Bài 15

SQL Server DML trigger **AFTER UPDATE chạy một lần cho statement**. Trong tình huống UPDATE 200 hàng, `inserted` có 200 hình ảnh mới và `deleted` có 200 hình ảnh cũ.

### Bài 16

Nó xử lý một biến cho cả tập `inserted`, có nguy cơ chỉ ghi một nhân viên trong 200 người. Hướng đúng:

```sql
INSERT INTO staff_audit (
    staff_id, old_salary, new_salary
)
SELECT i.staff_id,
       d.monthly_salary,
       i.monthly_salary
FROM inserted AS i
JOIN deleted AS d
  ON d.staff_id = i.staff_id;
```

Ví dụ giả định khóa `staff_id` không đổi và các tên bảng/cột phù hợp với SQL Server.

### Bài 17

```sql
DELIMITER $$

CREATE TRIGGER trg_staff_before_insert_example
BEFORE INSERT ON staff
FOR EACH ROW
BEGIN
    SET NEW.email = LOWER(TRIM(NEW.email));
END$$

DELIMITER ;
```

Trigger chỉ nhận event INSERT. Nếu UPDATE đổi email, phải có `BEFORE UPDATE` tương ứng hoặc một đường normalization khác.

### Bài 18

**SQLite** hỗ trợ `INSTEAD OF INSERT` trên view; **MySQL không**.

```sql
-- SQLite
CREATE TRIGGER insert_staff_through_view
INSTEAD OF INSERT ON staff_public_view
FOR EACH ROW
BEGIN
    INSERT INTO staff (staff_id, email)
    VALUES (NEW.staff_id, lower(trim(NEW.email)));
END;
```

Ví dụ giả định `staff_public_view` và `staff` có schema thích hợp.

### Bài 19

Trong Oracle, phép gán `:NEW.monthly_salary := ...` thuộc **BEFORE ROW** trong tình huống cho phép sửa cột mới. AFTER ROW không phải điểm để thay `:NEW`. Row trigger đọc chính bảng đang bị statement sửa có thể gặp **mutating-table restriction**, ví dụ `ORA-04091`. Có thể cân nhắc compound trigger với xử lý sau statement hoặc thiết kế khác.

### Bài 20

Email có thể đã được gửi **trước khi transaction rollback**, tạo thông báo về một thay đổi không tồn tại. Giải pháp thường phù hợp là **transactional outbox**: ghi event trong cùng transaction, COMMIT rồi worker gửi, kèm retry và idempotency.

### Bài 21

`TRUNCATE` là thao tác khác `DELETE` theo từng hàng, nên không thể dựa vào nó để gọi `AFTER DELETE FOR EACH ROW`. PostgreSQL có `BEFORE TRUNCATE` hoặc `AFTER TRUNCATE` **statement-level trigger** cho đối tượng phù hợp.

### Bài 22

Không. MySQL upsert có thể đi qua **BEFORE INSERT** rồi nhánh UPDATE tùy xung đột khóa, với quy tắc kích hoạt trigger tương ứng. Phải kiểm tra luồng cụ thể, đặc biệt khi audit, normalize hoặc tính aggregate.

### Bài 23

Rủi ro: **10.000 lần quét** bảng triệu hàng, tăng CPU/I/O, transaction kéo dài, contention. Trên Oracle còn có thể liên quan mutating table.

Hai hướng:

- Dùng **AFTER STATEMENT/transition tables** (ở DBMS hỗ trợ) hoặc compound trigger Oracle để xử lý set-based.
- Tính delta old/new hoặc chuyển sang bảng tổng hợp/batch pipeline nếu nghiệp vụ cho phép, tránh SUM toàn bảng sau từng hàng.

### Bài 24

Cần đánh giá:

- **Quyền và truy cập dữ liệu nhạy cảm:** function owner có thể có quyền nhiều hơn caller; giới hạn đối tượng được phép đọc/ghi, audit logs và quyền execute.
- **SQL object resolution/search_path:** tránh hijacking qua tên đối tượng không đủ schema hoặc search path thiếu an toàn; review function và cấp quyền.

Cần xét thêm transaction, rò rỉ dữ liệu qua lỗi/log và quyền sửa bảng audit.

### Bài 25

| DBMS | Chuẩn hóa trước ghi | Audit sau thay đổi | UPDATE qua join view |
| --- | --- | --- | --- |
| PostgreSQL | BEFORE ROW sửa NEW | AFTER ROW/STATEMENT | INSTEAD OF ROW view |
| SQL Server | Validation/INSTEAD OF set-based, không có BEFORE | AFTER statement dùng inserted/deleted | INSTEAD OF trên view |
| MySQL | BEFORE ROW sửa NEW | AFTER ROW | Không có INSTEAD OF view; dùng đường ghi khác |
| Oracle | BEFORE ROW sửa :NEW | AFTER ROW/statement | INSTEAD OF ROW view khi đủ điều kiện |
| SQLite | Validation/ứng dụng/INSTEAD OF view, không gán NEW kiểu MySQL | AFTER ROW | INSTEAD OF ROW view |

Phải xác định **cách trigger xử lý hàng/câu lệnh** và ràng buộc của DBMS cụ thể trước khi chuyển mã.

---

## 44. Quy trình lựa chọn trigger khi triển khai hệ thống thật

Trước khi viết một trigger, trả lời lần lượt:

1. **Có thật sự cần trigger không?** Một constraint, generated column hoặc code ghi tường minh có thể đơn giản và dễ kiểm soát hơn không?
2. **Sự kiện nào cần bắt?** INSERT, UPDATE, DELETE, UPSERT, MERGE, TRUNCATE; các trường hợp nào không được bao phủ?
3. **Timing có ý nghĩa gì?** BEFORE để đổi/kiểm tra NEW, AFTER để ghi nhận dữ liệu đã thao tác, INSTEAD OF để thay đường DML?
4. **DBMS có hỗ trợ không?** SQL Server không có DML BEFORE; MySQL không có INSTEAD OF; SQLite không có statement-level.
5. **Mỗi hàng hay mỗi câu lệnh?** DML có thể sửa 0/1/nhiều hàng.
6. **OLD/NEW được truy cập như thế nào?** PostgreSQL `NEW`/`OLD`, Oracle `:NEW`/`:OLD`, SQL Server `inserted`/`deleted`.
7. **Có được sửa NEW không?** Không suy từ khả năng đọc NEW rằng có thể gán vào nó ở mọi hệ/timing.
8. **Trigger thực hiện DML vào những bảng nào?** Có gây chuỗi trigger hoặc đệ quy không?
9. **Rollback có nhất quán không?** Audit/outbox có thuộc cùng transaction? Có tác dụng phụ bên ngoài không?
10. **Có sử dụng constraint để bảo vệ bất biến không?** Trigger không thay thế mặc định cho PK/UNIQUE/FK/CHECK.
11. **Thứ tự xử lý có phải một phần nghiệp vụ không?** Đừng phụ thuộc thứ tự hàng hoặc tên trigger không được quy định chung.
12. **Hiệu năng dưới batch lớn ra sao?** Trigger row-level có thể tạo N lần truy vấn đắt đỏ.
13. **Có rủi ro lock, deadlock, mutating table hoặc privilege escalation không?**
14. **Có chính sách audit và retention không?** Ai được xem, sửa, xóa bản ghi audit?
15. **Khi chuyển DBMS có cần viết lại logic không?** Phải chuyển theo hợp đồng dữ liệu chứ không dịch từ khóa.

## 45. Tổng kết

Ba timing không thể hiểu tách khỏi **hệ quản trị và mức kích hoạt**:

- **BEFORE** tham gia trước thao tác ghi; trong PostgreSQL, MySQL và Oracle, BEFORE ROW có cơ chế biến đổi giá trị mới theo cú pháp riêng. SQLite không cho gán NEW theo cách đó, còn SQL Server không có DML BEFORE trigger thông thường.
- **AFTER** phục vụ ghi nhận hoặc cập nhật phụ thuộc sau thao tác DML, nhưng **chưa có nghĩa transaction đã COMMIT**. PostgreSQL/Oracle có biến thể row/statement, SQL Server dùng các tập `inserted`/`deleted` cấp statement, MySQL/SQLite chủ yếu row-level.
- **INSTEAD OF** tự định nghĩa cách thực hiện DML thay cho đối tượng gắn trigger; đặc biệt hữu ích với **view phức tạp**. PostgreSQL, Oracle và SQLite hỗ trợ theo hàng trên view; SQL Server hỗ trợ trên bảng/view ở cấp statement; MySQL không có INSTEAD OF theo cú pháp này.

Khi chọn trigger, luôn gắn câu hỏi **“chạy lúc nào?”** với **“chạy bao nhiêu lần?”, “có thể đọc/sửa dữ liệu nào?”, “có tự thực hiện DML không?” và “rollback có ảnh hưởng gì?”**. Hiểu bốn khía cạnh đó giúp thiết kế trigger chính xác, tránh lỗi khi thao tác nhiều hàng và chuyển đổi ứng dụng an toàn giữa các hệ quản trị SQL.
