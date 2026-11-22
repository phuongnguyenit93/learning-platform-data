# Kiểm tra khóa ngoại, khóa duy nhất và các điểm tranh chấp

Khóa ngoại (*foreign key*, FK) và khóa duy nhất (*unique key*) vừa bảo vệ tính toàn vẹn dữ liệu, vừa tham gia vào cơ chế khóa của InnoDB. Khi một transaction thêm hàng con, MySQL phải xác minh hàng cha được tham chiếu tồn tại. Khi thêm một giá trị vào unique index, InnoDB phải bảo đảm không có transaction khác commit cùng khóa duy nhất. Những kiểm tra này có thể khiến transaction phải chờ, nhận lỗi duplicate key, vi phạm foreign key hoặc rơi vào deadlock.

Vì vậy, điều tra tranh chấp không chỉ là tìm câu `UPDATE` nào đang chờ. Cần biết constraint nào được kiểm tra, index nào được dùng, transaction nào đang giữ record/gap lock và nhiều request có đang tập trung vào cùng một khóa hay không. Cùng một thiết kế constraint có thể bảo vệ dữ liệu chính xác nhưng tạo điểm nóng khi một lượng lớn giao dịch cùng tác động vào một hàng cha hoặc một giá trị duy nhất.

Bài học này thuộc module `DATABASE_MYSQL`, bao gồm thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Mục tiêu là kiểm tra constraint bằng metadata và dữ liệu thực tế, hiểu các lịch chạy đồng thời quanh FK/UNIQUE, rồi chọn cách giảm contention mà vẫn giữ invariant nghiệp vụ.

Sau bài học, bạn có thể:

- Kiểm tra định nghĩa FK và UNIQUE bằng `SHOW CREATE TABLE` và `INFORMATION_SCHEMA`.
- Phát hiện orphan references và duplicate values trước khi thêm constraint.
- Hiểu các yêu cầu về kiểu dữ liệu, index và thứ tự cột của foreign key.
- Giải thích cách InnoDB khóa khi kiểm tra FK và unique index.
- Tái hiện cạnh tranh giữa child insert với parent delete/update.
- Tái hiện hai transaction cùng insert một unique key và dự đoán kết quả khi commit/rollback.
- Nhận diện điểm nóng do parent row, unique key, cascade và thứ tự khóa.
- Quan sát lock wait, deadlock và access path bằng Performance Schema, `sys` và `EXPLAIN`.
- Giảm tranh chấp bằng index phù hợp, transaction ngắn, thứ tự thao tác nhất quán và thiết kế ghi phù hợp.

## 1. Constraint bảo vệ dữ liệu như thế nào?

Hai loại constraint có mục đích khác nhau:

| Constraint | Quy tắc được bảo vệ | Ví dụ |
| --- | --- | --- |
| `FOREIGN KEY` | Giá trị khóa tham chiếu ở bảng con phải trỏ tới hàng hợp lệ ở bảng cha, hoặc là `NULL` nếu cột cho phép | `employees.department_id` phải tham chiếu một `departments.department_id` tồn tại |
| `UNIQUE` | Không cho phép hai hàng có cùng tổ hợp giá trị khóa duy nhất theo quy tắc so sánh của index | Email đăng nhập không được trùng |

FK không tự bảo đảm quan hệ một-một. Nhiều hàng con có thể tham chiếu cùng một hàng cha. Nếu muốn một hàng cha được tham chiếu tối đa một lần, cần thêm unique constraint trên cột FK ở bảng con.

UNIQUE không thay thế FK. Một `department_id` có thể là duy nhất trong bảng con nhưng vẫn trỏ tới phòng ban không tồn tại nếu không có FK.

Trong InnoDB, constraint được kiểm tra trong quá trình thực hiện statement, không phải chỉ khi client gọi `COMMIT`. MySQL không hỗ trợ deferred foreign key constraints kiểu “đợi tới cuối transaction mới kiểm tra”.

## 2. Tạo schema lab có FK và UNIQUE

Chạy phần chuẩn bị một lần trong schema thử nghiệm. Các bảng dùng InnoDB và tên có tiền tố `cc_` để dễ nhận diện.

```sql
DROP TABLE IF EXISTS cc_employees;
DROP TABLE IF EXISTS cc_departments;

CREATE TABLE cc_departments (
    department_id INT UNSIGNED NOT NULL,
    department_code VARCHAR(20) NOT NULL,
    department_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (department_id),
    CONSTRAINT uq_cc_departments_code UNIQUE (department_code)
) ENGINE = InnoDB;

CREATE TABLE cc_employees (
    employee_id BIGINT UNSIGNED NOT NULL,
    department_id INT UNSIGNED NULL,
    email VARCHAR(190) NOT NULL,
    employee_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (employee_id),
    CONSTRAINT uq_cc_employees_email UNIQUE (email),
    KEY idx_cc_employees_department (department_id),
    CONSTRAINT fk_cc_employees_department
        FOREIGN KEY (department_id)
        REFERENCES cc_departments (department_id)
        ON UPDATE RESTRICT
        ON DELETE RESTRICT
) ENGINE = InnoDB;

INSERT INTO cc_departments (department_id, department_code, department_name) VALUES
(10, 'ENG', 'Engineering'),
(20, 'SAL', 'Sales');

INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(1, 10, 'an@example.com', 'An'),
(2, 10, 'binh@example.com', 'Binh'),
(3, 20, 'chi@example.com', 'Chi'),
(4, NULL, 'dung@example.com', 'Dung');
```

Trong fixture:

- `cc_departments.department_id` là khóa cha.
- `cc_departments.department_code` là unique key.
- `cc_employees.department_id` là FK nullable; nhiều nhân viên có thể thuộc cùng phòng ban.
- `cc_employees.email` là unique key và `NOT NULL`.
- Index `idx_cc_employees_department` hỗ trợ tìm hàng con theo FK.

Nếu cần chạy lại script, xóa bảng con trước bảng cha vì FK đang tham chiếu bảng cha.

## 3. Kiểm tra định nghĩa constraint

### 3.1. SHOW CREATE TABLE

Đây là cách nhanh nhất để xem định nghĩa thực tế mà MySQL đang lưu:

```sql
SHOW CREATE TABLE cc_departments;
SHOW CREATE TABLE cc_employees;
```

Kiểm tra:

- Storage engine có phải InnoDB không.
- FK tham chiếu đúng bảng và đúng cột chưa.
- `ON DELETE` và `ON UPDATE` có đúng chính sách nghiệp vụ không.
- Cột FK có nullable hay không.
- Unique key có đúng cột và đúng thứ tự không.
- Index hỗ trợ cột FK có tồn tại không.

Đừng chỉ đọc migration source. Schema thực tế có thể khác do migration cũ, thao tác thủ công hoặc deployment chưa hoàn tất.

### 3.2. Xem constraint qua INFORMATION_SCHEMA

Liệt kê constraint của bảng:

```sql
SELECT
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE,
    tc.TABLE_NAME
FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
  AND tc.TABLE_NAME IN ('cc_departments', 'cc_employees')
ORDER BY tc.TABLE_NAME, tc.CONSTRAINT_TYPE, tc.CONSTRAINT_NAME;
```

Xem các cột FK và cột được tham chiếu:

```sql
SELECT
    kcu.CONSTRAINT_NAME,
    kcu.TABLE_NAME,
    kcu.COLUMN_NAME,
    kcu.ORDINAL_POSITION,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME,
    kcu.POSITION_IN_UNIQUE_CONSTRAINT
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
WHERE kcu.CONSTRAINT_SCHEMA = DATABASE()
  AND kcu.TABLE_NAME = 'cc_employees'
  AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY kcu.CONSTRAINT_NAME, kcu.ORDINAL_POSITION;
```

Xem hành động tham chiếu:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND TABLE_NAME = 'cc_employees';
```

### 3.3. Kiểm tra index và unique index

```sql
SELECT
    TABLE_NAME,
    INDEX_NAME,
    NON_UNIQUE,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    SUB_PART,
    INDEX_TYPE
FROM INFORMATION_SCHEMA.STATISTICS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME IN ('cc_departments', 'cc_employees')
ORDER BY TABLE_NAME, INDEX_NAME, SEQ_IN_INDEX;
```

`NON_UNIQUE = 0` biểu thị index duy nhất. `SEQ_IN_INDEX` cho biết thứ tự cột trong index ghép; `SUB_PART` cho biết index có dùng prefix length hay không. Với unique index ghép, toàn bộ tổ hợp cột mới là khóa được bảo vệ.

## 4. Kiểm tra dữ liệu trước khi thêm FK

Trước khi thêm FK vào bảng đã có dữ liệu, tìm các giá trị con không có hàng cha tương ứng:

```sql
SELECT
    e.employee_id,
    e.department_id
FROM cc_employees AS e
LEFT JOIN cc_departments AS d
    ON d.department_id = e.department_id
WHERE e.department_id IS NOT NULL
  AND d.department_id IS NULL;
```

Kết quả mong đợi là rỗng. Điều kiện `e.department_id IS NOT NULL` loại các hàng không chỉ định quan hệ; FK nullable cho phép các hàng đó.

Nếu kết quả có hàng, hãy phân loại trước khi thêm constraint:

- Mã cha bị thiếu do dữ liệu import: tìm và khôi phục hàng cha đúng.
- Mã con sai: sửa về ID hợp lệ theo mapping đã xác minh.
- Quan hệ thực sự tùy chọn: cho phép `NULL` nếu nghiệp vụ cho phép.
- Dữ liệu không thể sửa tự động: đưa vào quy trình xử lý riêng, không gán đại một parent ID.

Khi chạy `ALTER TABLE ... ADD CONSTRAINT FOREIGN KEY`, InnoDB kiểm tra dữ liệu hiện có. Nếu có orphan reference, thao tác thêm FK thất bại.

### 4.1. Kiểm tra tương thích kiểu dữ liệu

Các cột FK và cột được tham chiếu phải tương thích. Với kiểu số nguyên, kích thước và signedness phải phù hợp; ví dụ `INT UNSIGNED` nên tham chiếu `INT UNSIGNED`, không ghép tùy tiện với `INT` signed. Với kiểu chuỗi, charset và collation cần tương thích.

Với FK ghép, số lượng cột và thứ tự cột ở hai phía phải khớp:

```sql
FOREIGN KEY (tenant_id, department_code)
REFERENCES departments (tenant_id, department_code)
```

Index phía cha phải hỗ trợ đúng thứ tự cột tham chiếu. Trong thiết kế mới, ưu tiên tham chiếu primary key hoặc unique key rõ ràng. InnoDB từng cho phép một số tham chiếu tới index không unique/không đầy đủ theo quy tắc chuẩn, nhưng hành vi không chuẩn này đã bị deprecate và phụ thuộc cấu hình/phiên bản; không dùng làm nền tảng cho schema mới.

InnoDB cần index ở phía con để kiểm tra và tìm hàng tham chiếu. Nếu chưa có index phù hợp, MySQL có thể tự tạo index cần thiết. Dù vậy, nên khai báo và đặt tên index rõ ràng để quản lý schema, tránh index dư thừa và kiểm soát access path.

## 5. Kiểm tra dữ liệu trước khi thêm UNIQUE

Trước khi thêm unique key, tìm các nhóm trùng theo cùng quy tắc so sánh mà index sẽ dùng:

```sql
SELECT
    email,
    COUNT(*) AS duplicate_count
FROM cc_employees
GROUP BY email
HAVING COUNT(*) > 1;
```

Nếu cột chuỗi dùng collation không phân biệt hoa/thường, `GROUP BY` thường áp dụng cùng quy tắc so sánh collation đó. Vì vậy hai chuỗi khác chữ hoa/thường có thể được xem là trùng đối với unique index.

Với unique key ghép:

```sql
SELECT
    tenant_id,
    external_code,
    COUNT(*) AS duplicate_count
FROM imported_records
WHERE tenant_id IS NOT NULL
  AND external_code IS NOT NULL
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

Điều kiện lọc ở đây giả định cả hai cột được phép NULL. MySQL unique index cho phép nhiều hàng có `NULL` ở một hoặc nhiều thành phần khóa; các hàng đó không bị xem là duplicate theo cách so sánh unique thông thường. Nếu các cột là `NOT NULL`, có thể bỏ phần `WHERE`.

### 5.1. NULL trong UNIQUE

MySQL cho phép nhiều `NULL` trong unique index:

```sql
CREATE TABLE cc_optional_codes (
    row_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    external_code VARCHAR(50) NULL,
    UNIQUE KEY uq_cc_optional_codes_external_code (external_code)
) ENGINE = InnoDB;

INSERT INTO cc_optional_codes VALUES
(1, NULL),
(2, NULL),
(3, 'A-100');
```

Hai hàng đầu không vi phạm unique key. Nếu nghiệp vụ yêu cầu mọi hàng phải có mã và mã phải duy nhất, khai báo `NOT NULL` cùng `UNIQUE`.

### 5.2. Collation và ý nghĩa “trùng”

Với chuỗi, unique index áp dụng quy tắc so sánh của collation. Ví dụ một collation `_ci` không phân biệt hoa/thường có thể coi `User@example.com` và `user@example.com` là cùng khóa. Một số collation còn có quy tắc so sánh dấu hoặc ký tự tương đương.

Trước khi thêm unique index trên email, username hoặc mã ngoài hệ thống:

- Kiểm tra charset/collation của cột.
- Xác định nghiệp vụ có phân biệt hoa/thường hay không.
- Chuẩn hóa dữ liệu theo quy tắc đã thống nhất.
- Chạy truy vấn duplicate detection với cùng collation.
- Kiểm tra độ dài index và kiểu dữ liệu được chọn.

Không chuyển sang collation khác chỉ để migration qua được nếu chưa đánh giá tác động đăng nhập, tìm kiếm và dữ liệu hiện có.

## 6. Thêm và thay đổi constraint an toàn

Ví dụ thêm FK sau khi đã xác minh dữ liệu:

```sql
ALTER TABLE cc_employees
ADD CONSTRAINT fk_cc_employees_department
FOREIGN KEY (department_id)
REFERENCES cc_departments (department_id)
ON UPDATE RESTRICT
ON DELETE RESTRICT;
```

Trong fixture phần 2, FK đã được khai báo khi tạo bảng; không chạy lại câu `ALTER` đó trên cùng bảng. Đoạn trên minh họa migration cho bảng chưa có constraint.

Thêm unique index:

```sql
ALTER TABLE cc_employees
ADD CONSTRAINT uq_cc_employees_email UNIQUE (email);
```

Nếu unique key đã tồn tại trong schema lab, không chạy lại. Khi migration production, cần kiểm tra metadata trước khi áp dụng và lên kế hoạch cho thời gian giữ metadata lock, thời gian build index, dung lượng tạm và ảnh hưởng tới DML.

DDL có thể chờ metadata lock nếu transaction khác đang giữ metadata lock trên bảng. “Online DDL” không có nghĩa không có metadata lock ở mọi giai đoạn. Kiểm tra khả năng `ALGORITHM`/`LOCK` được hỗ trợ cho đúng thao tác và phiên bản MySQL; không ép tùy chọn mà engine không hỗ trợ.

## 7. InnoDB khóa khi kiểm tra foreign key

FK không chỉ là kiểm tra logic trong metadata. InnoDB phải bảo vệ quan hệ khỏi thay đổi đồng thời.

### 7.1. Child INSERT kiểm tra parent

Khi transaction chèn một hàng con có FK khác `NULL`, InnoDB phải xác minh hàng cha tương ứng tồn tại. Quá trình kiểm tra FK có thể đặt shared record lock trên bản ghi cha được kiểm tra. Khóa được giữ theo transaction, vì vậy thao tác xóa hoặc sửa khóa cha xung đột có thể phải chờ.

Shared lock trên cùng một hàng cha thường có thể cùng tồn tại với shared lock khác; nó không có nghĩa mọi child insert vào cùng parent đều phải xếp hàng tuần tự. Điểm tranh chấp nổi bật là khi transaction khác muốn xóa/sửa hàng cha hoặc khi child insert đồng thời xung đột trên unique key/index khác.

### 7.2. Parent DELETE/UPDATE kiểm tra child

Khi xóa hàng cha hoặc thay đổi khóa được tham chiếu, InnoDB phải kiểm tra bảng con để bảo đảm hành động FK hợp lệ. Với `RESTRICT`/`NO ACTION`, nếu có hàng con tham chiếu thì thao tác cha bị từ chối. Quá trình kiểm tra có thể khóa các record/index entry liên quan ở bảng con.

Index trên cột FK phía con rất quan trọng để tìm các hàng tham chiếu. InnoDB yêu cầu index hỗ trợ FK; index phù hợp cũng giúp tránh việc kiểm tra phải quét một vùng dữ liệu rộng.

### 7.3. Lịch chạy: child INSERT cạnh tranh với parent DELETE

Dùng schema `cc_departments` và `cc_employees` ở phần 2. Chọn phòng ban 10 chưa bị xóa.

**Session A:**

```sql
START TRANSACTION;

INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(1001, 10, 'new.employee@example.com', 'New Employee');

-- Chưa commit: FK check đã xác minh parent 10.
```

**Session B:**

```sql
START TRANSACTION;

DELETE FROM cc_departments
WHERE department_id = 10;
```

DELETE ở B có thể chờ khóa liên quan tới parent row mà A đang giữ trong quá trình kiểm tra FK. Khi A kết thúc:

**Session A:**

```sql
COMMIT;
```

Sau đó B tiếp tục kiểm tra FK và bị từ chối vì phòng ban 10 hiện có hàng con tham chiếu, theo `ON DELETE RESTRICT`.

Nếu B khóa/xóa parent trước khi A kiểm tra FK, child insert của A có thể phải chờ. Nếu B commit xóa parent, A tiếp tục và nhận lỗi foreign key vì parent không còn tồn tại. Thứ tự transaction quyết định bên nào chờ và statement nào thất bại; constraint bảo đảm không có child reference mồ côi được commit.

Để chạy lại ví dụ, rollback/commit các session đúng cách và xóa employee 1001 nếu đã được commit trước đó.

## 8. ON DELETE và ON UPDATE làm thay đổi phạm vi công việc

Các hành động tham chiếu thường dùng:

| Hành động | Ý nghĩa | Tác động concurrency |
| --- | --- | --- |
| `RESTRICT` | Từ chối xóa/sửa khóa cha nếu còn hàng con tham chiếu | Kiểm tra và khóa các record liên quan; statement có thể chờ hoặc thất bại |
| `NO ACTION` | Trong InnoDB tương đương `RESTRICT`, kiểm tra ngay | Không phải deferred constraint |
| `CASCADE` | Xóa/sửa hàng con theo thay đổi ở hàng cha | Có thể cập nhật/xóa nhiều hàng con và giữ nhiều lock |
| `SET NULL` | Đặt cột FK ở hàng con thành NULL | Cột FK phải cho phép NULL; nhiều hàng con có thể bị cập nhật |

### 8.1. CASCADE có thể khuếch đại một thao tác

Một câu `DELETE` chỉ nhắm tới một hàng cha có thể kích hoạt xóa hàng nghìn hàng con nếu dùng `ON DELETE CASCADE`. Đây là một statement, nhưng phạm vi lock, undo log, redo log và thời gian transaction có thể lớn.

Trước khi dùng cascade ở quan hệ có fan-out cao:

- Ước lượng số hàng con tối đa.
- Bảo đảm index FK phù hợp.
- Đánh giá deadlock với luồng cập nhật bảng con.
- Cân nhắc xóa theo batch ở tầng ứng dụng nếu nghiệp vụ cho phép và cần kiểm soát tải.
- Không tách thao tác cascade thành nhiều transaction nếu điều đó làm lộ trạng thái trung gian không hợp lệ.

### 8.2. SET NULL

Nếu dùng `ON DELETE SET NULL`, cột FK phải nullable. Nếu cột là `NOT NULL`, thiết kế không tương thích. Hãy kiểm tra cả logic ứng dụng vì `NULL` có thể mang ý nghĩa “không gán” thay vì “parent đã bị xóa”.

## 9. InnoDB khóa khi kiểm tra UNIQUE

Unique index là cơ chế cuối cùng bảo vệ tính duy nhất trong môi trường nhiều transaction. Kiểm tra ở ứng dụng kiểu “SELECT trước, nếu chưa có thì INSERT” không đủ vì hai request có thể cùng thấy chưa tồn tại.

Ví dụ:

```sql
SELECT employee_id
FROM cc_employees
WHERE email = 'same@example.com';

-- Nếu chưa có hàng, ứng dụng mới INSERT.
```

Hai transaction có thể cùng chạy SELECT và đều nhận kết quả rỗng. Unique index vẫn phải được khai báo để quyết định một INSERT thắng và INSERT còn lại không thể tạo duplicate.

### 9.1. Lịch chạy: hai transaction cùng INSERT một unique key

Trước khi chạy, xác nhận email `race@example.com` chưa tồn tại.

**Session A:**

```sql
START TRANSACTION;

INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(2001, 10, 'race@example.com', 'Race A');

-- Chưa commit.
```

**Session B:**

```sql
START TRANSACTION;

INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(2002, 10, 'race@example.com', 'Race B');
```

INSERT của B thường phải chờ kết quả transaction A vì unique index không thể quyết định có duplicate cho tới khi A commit hoặc rollback.

Nếu A chạy:

```sql
COMMIT;
```

thì B tiếp tục và nhận lỗi duplicate key. Nếu A chạy `ROLLBACK`, B có thể tiếp tục thành công vì giá trị duy nhất không còn được A giữ.

Constraint bảo đảm không thể có hai hàng cùng email được commit. Kết quả không phụ thuộc vào việc ứng dụng có chạy truy vấn kiểm tra trước đó hay không.

### 9.2. Unique key ghép

Với:

```sql
UNIQUE KEY uq_tenant_external_code (tenant_id, external_code)
```

MySQL bảo đảm tổ hợp `(tenant_id, external_code)` là duy nhất, không phải từng cột riêng lẻ. Hai tenant khác nhau có thể dùng cùng external code. Thứ tự cột trong index ảnh hưởng cả việc xác định khóa duy nhất lẫn khả năng dùng index cho truy vấn.

Nếu có `NULL` ở bất kỳ thành phần nào, unique index cho phép nhiều tổ hợp có NULL theo quy tắc NULL của MySQL. Nếu yêu cầu nghiệp vụ là duy nhất tuyệt đối cho mọi hàng, các thành phần khóa cần `NOT NULL` hoặc có thiết kế chuẩn hóa tương ứng.

### 9.3. Collation, prefix index và functional uniqueness

Unique index trên chuỗi sử dụng collation của cột/index. Một cột không phân biệt hoa/thường có thể xem hai chuỗi chỉ khác chữ hoa/thường là trùng.

Unique prefix index chỉ bảo đảm phần prefix được index là duy nhất. Ví dụ `UNIQUE KEY (code(8))` có thể từ chối hai mã có tám ký tự đầu giống nhau dù phần đuôi khác nhau. Không dùng prefix unique nếu nghiệp vụ yêu cầu duy nhất trên toàn bộ chuỗi.

Với functional index hoặc generated column có unique index, giá trị biểu thức sau khi chuẩn hóa mới là giá trị được bảo vệ. Hãy kiểm tra cùng biểu thức/collation trong bước phát hiện duplicate trước migration.

## 10. Các câu lệnh xử lý duplicate và hệ quả

### 10.1. INSERT thông thường

```sql
INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(3001, 10, 'an@example.com', 'Another An');
```

Vì email đã tồn tại, statement nhận lỗi duplicate key. Trong transaction tường minh, lỗi statement không nhất thiết tự rollback toàn bộ transaction; ứng dụng cần quyết định rollback khi nghiệp vụ không thể tiếp tục.

### 10.2. INSERT ... ON DUPLICATE KEY UPDATE

```sql
INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(3001, 10, 'an@example.com', 'An Updated')
ON DUPLICATE KEY UPDATE
    employee_name = VALUES(employee_name);
```

Cú pháp `VALUES(col)` trong phần update đã deprecated trong các phiên bản MySQL mới; với code mới, dùng row alias theo cú pháp của phiên bản triển khai. Ví dụ MySQL 8.4:

```sql
INSERT INTO cc_employees
    (employee_id, department_id, email, employee_name)
VALUES
(3001, 10, 'an@example.com', 'An Updated') AS incoming
ON DUPLICATE KEY UPDATE
    employee_name = incoming.employee_name;
```

Lệnh có thể kích hoạt nhánh update khi xung đột với bất kỳ PRIMARY KEY hoặc UNIQUE index nào. Nếu bảng có nhiều unique key, đừng giả định chỉ email quyết định hàng được cập nhật. Kiểm tra thiết kế và xác định rõ conflict target theo nghiệp vụ; MySQL không có cú pháp chỉ định một conflict target riêng như một số hệ quản trị khác.

### 10.3. INSERT IGNORE

`INSERT IGNORE` có thể biến một số lỗi thành warning và bỏ qua hàng vi phạm. Điều đó có thể hữu ích cho import có chủ đích, nhưng cũng có thể che dữ liệu lỗi hoặc các vấn đề chuyển đổi khác. Sau khi chạy, phải kiểm tra warning và số hàng thực sự được chèn.

### 10.4. REPLACE

`REPLACE` có ngữ nghĩa xóa hàng xung đột rồi chèn hàng mới trong các trường hợp tương ứng; nó không đơn giản là UPDATE. Hành động này có thể ảnh hưởng tới khóa ngoại, cascade, trigger, auto-increment và các cột không được cung cấp. Không dùng `REPLACE` thay cho update nếu chưa đánh giá đầy đủ hệ quả.

## 11. Nhận diện điểm nóng và kiểu tranh chấp

Không phải mọi độ trễ đều là cùng một loại lock. Cần phân biệt row/index lock, gap/next-key lock, metadata lock và latch nội bộ.

| Điểm nóng | Biểu hiện có thể gặp | Nguyên nhân thường thấy |
| --- | --- | --- |
| Một parent row được nhiều child insert tham chiếu | Parent delete/update chờ; child insert chờ khi parent bị khóa | Nhiều giao dịch cùng kiểm tra một khóa cha hoặc một luồng xóa/sửa parent |
| Một unique value được nhiều request ghi | Duplicate key hoặc lock wait trên cùng unique entry | Request cạnh tranh cùng username, email, external reference hoặc idempotency key |
| Một unique counter/sequence row | Nhiều transaction chờ cùng hàng | Dùng một hàng làm bộ đếm toàn cục |
| Cascade có fan-out lớn | Transaction dài, nhiều row lock, deadlock | Xóa/sửa parent tác động tới lượng lớn child rows |
| FK child index không phù hợp với truy vấn nghiệp vụ | Scan rộng, nhiều record được kiểm tra/khóa | Index thiếu cột đầu, thứ tự cột không phù hợp hoặc predicate không sargable |
| Insert tăng dần vào cùng vùng index | Có thể thấy page/latch contention dù không phải row lock chờ lâu | Nhiều insert tập trung vào trang cuối của B-tree hoặc một index nóng |
| DDL trên bảng đang được dùng | Chờ metadata lock | Transaction dài giữ metadata lock hoặc migration chạy đồng thời với workload |

### 11.1. Nhiều child insert cùng tham chiếu một parent

Các shared record locks phục vụ FK check có thể cùng tồn tại. Vì vậy, không nên kết luận rằng cùng một parent ID tự động tuần tự hóa tất cả child inserts. Tranh chấp thường rõ hơn khi một transaction muốn xóa/sửa parent, hoặc khi các insert còn xung đột trên unique index, auto-increment/index page hay tài nguyên khác.

Nếu parent row là trạng thái dùng chung bị cập nhật thường xuyên, xem xét tách thông tin ít thay đổi của parent khỏi bộ đếm/trạng thái nóng, hoặc cập nhật trạng thái theo một giao thức rõ ràng. Không bỏ FK chỉ để giảm chờ nếu quan hệ vẫn cần được bảo vệ.

### 11.2. Unique key nóng và idempotency key

Một endpoint có thể nhận cùng một idempotency key từ nhiều request retry đồng thời. Unique index là cách phù hợp để chỉ cho phép một request tạo bản ghi đại diện. Request còn lại có thể chờ rồi nhận duplicate; ứng dụng nên đọc lại kết quả đã lưu và trả cùng response nghiệp vụ thay vì coi duplicate luôn là lỗi không thể xử lý.

Nếu hệ thống dùng một hàng duy nhất làm counter cho mọi request, hàng đó có thể thành hotspot. Cân nhắc cấp dải ID, dùng sequence phù hợp, sharding counter theo bucket hoặc để bộ sinh ID chuyên dụng đảm nhận việc này. Không thay unique constraint bằng kiểm tra `SELECT` ở ứng dụng.

### 11.3. Insert-intention lock và gap lock

Khi INSERT vào một vị trí trong index, InnoDB dùng insert-intention lock để báo ý định chèn vào gap tương ứng. Các transaction chèn vào những vị trí khác nhau trong cùng gap thường có thể cùng tiến hành; insert-intention locks không phải cơ chế tuần tự hóa mọi INSERT trong gap. Tuy nhiên, một gap lock hoặc next-key lock do transaction khác giữ có thể khiến INSERT phải chờ.

Ví dụ, Session A chạy locking range read ở `REPEATABLE READ` trên một khoảng index; Session B chèn một giá trị nằm trong gap bị khóa. B có thể chờ dù giá trị mới không trùng một record đã tồn tại. Đây là tranh chấp do bảo vệ khoảng, khác với duplicate-key wait khi hai transaction cùng chèn một unique value.

## 12. Kiểm tra lock wait và deadlock

### 12.1. Performance Schema

MySQL 8.x cung cấp các bảng Performance Schema để quan sát data locks và lock waits:

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
ORDER BY OBJECT_NAME, INDEX_NAME, THREAD_ID;
```

Xem quan hệ giữa transaction đang chờ và transaction đang chặn:

```sql
SELECT
    req.ENGINE_TRANSACTION_ID AS waiting_trx,
    req.OBJECT_SCHEMA,
    req.OBJECT_NAME,
    req.INDEX_NAME,
    req.LOCK_MODE AS waiting_lock_mode,
    req.LOCK_DATA AS waiting_lock_data,
    blk.ENGINE_TRANSACTION_ID AS blocking_trx,
    blk.LOCK_MODE AS blocking_lock_mode,
    blk.LOCK_DATA AS blocking_lock_data
FROM performance_schema.data_lock_waits AS w
JOIN performance_schema.data_locks AS req
    ON req.ENGINE = w.ENGINE
   AND req.ENGINE_LOCK_ID = w.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blk
    ON blk.ENGINE = w.ENGINE
   AND blk.ENGINE_LOCK_ID = w.BLOCKING_ENGINE_LOCK_ID;
```

Các bảng này phản ánh lock hiện đang tồn tại; nếu wait đã kết thúc thì hàng có thể biến mất. Quyền truy cập và mức instrumentation phụ thuộc cấu hình server.

### 12.2. sys schema và InnoDB status

Nếu sys schema có sẵn, view sau cung cấp góc nhìn dễ đọc hơn về lock waits:

```sql
SELECT *
FROM sys.innodb_lock_waits;
```

Thông tin deadlock gần nhất:

```sql
SHOW ENGINE INNODB STATUS;
```

Đọc phần `LATEST DETECTED DEADLOCK` để tìm:

- Transaction nào là nạn nhân.
- Statement nào đang chạy.
- Index/table và lock mode liên quan.
- Thứ tự lấy lock của từng transaction.
- Transaction nào giữ lock và transaction nào chờ.

Deadlock log chỉ mô tả deadlock gần nhất được lưu ở thời điểm truy vấn. Với hệ thống có nhiều deadlock, bật/thu thập log phù hợp và phân tích tần suất, không chỉ dựa vào một snapshot.

### 12.3. Phân biệt row lock với metadata lock và latch

- `performance_schema.data_locks` và `data_lock_waits` quan sát InnoDB data locks.
- `performance_schema.metadata_locks` giúp điều tra metadata lock, thường liên quan DDL và transaction đang dùng bảng.
- Latch/page contention là đồng bộ nội bộ của InnoDB; nó không nhất thiết xuất hiện như một row lock đang chờ. Cần xem wait instrumentation, mutex/rwlock và các chỉ số hiệu năng phù hợp.

Có thể xem metadata lock của các bảng lab bằng:

```sql
SELECT
    OBJECT_TYPE,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    LOCK_TYPE,
    LOCK_DURATION,
    LOCK_STATUS,
    OWNER_THREAD_ID
FROM performance_schema.metadata_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME IN ('cc_departments', 'cc_employees')
ORDER BY OBJECT_NAME, LOCK_STATUS, OWNER_THREAD_ID;
```

Không kết luận “FK gây lock” chỉ từ một request chậm. Đối chiếu thread, transaction, index, SQL và thời điểm wait để tìm nguyên nhân cụ thể.

## 13. EXPLAIN và index cho FK/UNIQUE

Kiểm tra truy vấn tìm child rows trước khi xóa parent:

```sql
EXPLAIN
SELECT employee_id
FROM cc_employees
WHERE department_id = 10;
```

Truy vấn nên dùng index bắt đầu bằng `department_id`. Nếu cần lọc thêm `status`, index ghép có thể cần thứ tự cột phù hợp với workload, ví dụ `(department_id, status)`.

Kiểm tra truy vấn theo unique key:

```sql
EXPLAIN
SELECT employee_id
FROM cc_employees
WHERE email = 'an@example.com';
```

Unique index giúp tìm tối đa một hàng theo khóa đầy đủ. Với composite unique index, truy vấn theo cột đầu có thể dùng leftmost prefix; truy vấn chỉ theo cột sau không tự động có cùng lợi ích.

`EXPLAIN` cho biết access path và ước lượng hàng, không hiển thị đầy đủ lock runtime. Dùng kết hợp `performance_schema.data_locks`, `data_lock_waits`, transaction metadata và deadlock report để điều tra concurrency.

## 14. Giảm tranh chấp mà vẫn giữ toàn vẹn dữ liệu

### 14.1. Giữ transaction ngắn

Không mở transaction rồi gọi HTTP API, chờ người dùng, xử lý file lớn hoặc thực hiện tác vụ không liên quan. Transaction dài giữ lock lâu và làm tăng xác suất xung đột.

### 14.2. Lấy lock theo thứ tự nhất quán

Nếu một nghiệp vụ cập nhật parent rồi child, tất cả code path nên theo cùng thứ tự. Nếu một luồng khóa child trước rồi parent trong khi luồng khác khóa parent trước rồi child, deadlock có thể xảy ra.

Với nhiều parent/child rows, sắp xếp ID và xử lý theo thứ tự ổn định giúp giảm chu trình chờ. Đây là biện pháp giảm xác suất deadlock, không bảo đảm loại bỏ hoàn toàn.

### 14.3. Dùng index phù hợp

- Giữ index trên cột FK phía con.
- Dùng composite index có leftmost prefix phù hợp với predicate thường gặp.
- Tránh chuyển đổi kiểu dữ liệu hoặc bọc cột bằng hàm trong điều kiện join/lọc nếu làm mất khả năng dùng index.
- Kiểm tra index dư thừa; index quá nhiều làm tăng chi phí mỗi INSERT/UPDATE/DELETE.

### 14.4. Xử lý duplicate như một kết quả cạnh tranh hợp lệ

Với đăng ký username/email hoặc idempotency key, thiết kế ứng dụng để xử lý duplicate key có chủ đích. Không chạy `SELECT` rồi tin rằng giá trị sẽ còn trống khi INSERT. Unique index là điểm phân xử nguyên tử.

### 14.5. Không loại bỏ constraint để chữa triệu chứng

Tắt `foreign_key_checks` hoặc bỏ unique index có thể cho phép dữ liệu sai lọt vào và khiến vấn đề khó phục hồi hơn. Chỉ dùng `SET FOREIGN_KEY_CHECKS = 0` trong quy trình import/migration được kiểm soát, có kiểm tra dữ liệu sau đó. Bật lại `FOREIGN_KEY_CHECKS` không tự động quét và xác thực lại toàn bộ dữ liệu đã nạp khi checks bị tắt.

## 15. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ kiểm tra FK trong code ứng dụng | Hai request đồng thời có thể tạo orphan reference | Dùng FK ở database và xử lý lỗi constraint |
| Dùng SELECT trước INSERT để bảo đảm unique | Race condition giữa hai request | Tạo UNIQUE index và xử lý duplicate key |
| Không kiểm tra orphan trước khi thêm FK | Migration thất bại khi validate dữ liệu cũ | Chạy anti-join và sửa dữ liệu có kiểm soát |
| Không kiểm tra duplicate trước khi thêm UNIQUE | Migration thất bại hoặc cần xử lý dữ liệu gấp | GROUP BY/HAVING theo đúng collation và khóa ghép |
| Nghĩ UNIQUE cho phép đúng một NULL | Insert NULL thứ hai bị từ chối sai dự đoán | Nhớ MySQL cho phép nhiều NULL trong unique index |
| Dùng parent key không chuẩn hoặc index sai thứ tự | FK không tạo được hoặc phụ thuộc hành vi không chuẩn | Ưu tiên PK/UNIQUE và đúng thứ tự cột |
| Bỏ index phía child | Tăng chi phí kiểm tra/tìm hàng con và ảnh hưởng lock | Tạo index phù hợp trên FK |
| Nghĩ child inserts cùng parent luôn tuần tự | Chẩn đoán sai điểm nóng | Phân biệt shared FK check locks với xung đột trên parent delete/update hoặc unique key |
| Dùng CASCADE cho quan hệ fan-out lớn mà không đo | Một thao tác gây nhiều lock và transaction dài | Ước lượng fan-out, kiểm tra index và tải |
| Dùng INSERT IGNORE để bỏ qua mọi lỗi | Che dữ liệu lỗi và warning | Kiểm tra warning/affected rows; chỉ dùng khi semantics rõ |
| Dùng REPLACE như UPDATE | Có thể delete+insert, kích hoạt cascade/trigger | Dùng UPDATE hoặc upsert đúng semantics |
| Chỉ xem EXPLAIN để kết luận lock | Không thấy đầy đủ lock runtime | Kết hợp Performance Schema và InnoDB status |

## 16. Bài tập thực hành

1. Tạo schema lab ở phần 2. Chạy `SHOW CREATE TABLE` và truy vấn `INFORMATION_SCHEMA` để liệt kê FK, UNIQUE và index.
2. Thử chèn employee với `department_id = 999`. Ghi nhận lỗi FK; thử `department_id = NULL` và giải thích vì sao hợp lệ.
3. Tạo bảng con tạm chưa có FK, chèn một orphan reference rồi chạy anti-join phát hiện dữ liệu trước khi thêm constraint.
4. Tạo dữ liệu email trùng theo collation hiện tại. Chạy `GROUP BY/HAVING`, sau đó thử thêm unique index trong bảng lab riêng.
5. Thử unique index nullable với nhiều hàng NULL. Đổi cột thành NOT NULL và quan sát khác biệt.
6. Mở hai session, để A insert employee tham chiếu department 10 nhưng chưa commit; cho B xóa department 10. Quan sát lock wait và lỗi sau khi A commit.
7. Mở hai session, cùng insert một email duy nhất. Thử A commit rồi B rollback/nhận duplicate; sau đó lặp lại với A rollback để B thành công.
8. Thử `ON DELETE CASCADE` trên bảng lab có nhiều child rows. Đo thời gian, quan sát lock và số hàng bị tác động.
9. Dùng `performance_schema.data_locks` và `data_lock_waits` khi một session đang chờ. Đối chiếu với `SHOW ENGINE INNODB STATUS`.
10. Chạy `EXPLAIN` cho truy vấn tìm child rows theo FK và truy vấn theo email. So sánh khi có và không có index trong schema thử nghiệm.
11. Thiết kế lại một luồng cập nhật parent/child để mọi code path lấy khóa theo cùng thứ tự; giải thích deadlock có thể giảm như thế nào.

## 17. Checklist trước khi đưa FK/UNIQUE vào production

- [ ] Đã xác nhận engine của các bảng tham gia là InnoDB.
- [ ] Đã xác minh định nghĩa constraint thực tế bằng `SHOW CREATE TABLE`/`INFORMATION_SCHEMA`.
- [ ] Cột FK tương thích kiểu dữ liệu, signedness, charset/collation và thứ tự cột.
- [ ] Parent key là PK/UNIQUE chuẩn; không phụ thuộc nonstandard referenced key.
- [ ] Child FK có index phù hợp với quan hệ và workload.
- [ ] Không có orphan reference trước khi thêm FK.
- [ ] Không có duplicate theo đúng collation và semantics của unique index.
- [ ] Đã quyết định rõ NULL có được phép trong FK/UNIQUE hay không.
- [ ] `ON DELETE`/`ON UPDATE` phản ánh đúng nghiệp vụ và fan-out đã được ước lượng.
- [ ] Ứng dụng xử lý duplicate key và foreign key violation như kết quả có thể xảy ra dưới concurrency.
- [ ] Transaction ngắn, thứ tự khóa nhất quán và retry deadlock có giới hạn.
- [ ] Đã kiểm tra access path bằng `EXPLAIN` và lock runtime bằng Performance Schema khi cần.
- [ ] Migration có kế hoạch metadata lock, thời gian build index và rollback/khôi phục phù hợp.
- [ ] Không tắt constraint checks nếu chưa có quy trình xác minh dữ liệu sau import.

## 18. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể đọc định nghĩa FK/UNIQUE từ schema thật, phát hiện orphan và duplicate trước migration, giải thích các yêu cầu index/kiểu dữ liệu, tái hiện được cạnh tranh child insert với parent delete và hai insert cùng unique key, phân biệt shared FK-check lock với xung đột unique/record/gap lock, đồng thời tìm được transaction chờ và điểm nóng bằng Performance Schema hoặc InnoDB status. Bạn cũng cần đề xuất được cách giảm contention mà không bỏ mất invariant dữ liệu.

## Tài liệu tham khảo

- [MySQL 8.4 Reference Manual — InnoDB and FOREIGN KEY Constraints](https://dev.mysql.com/doc/refman/8.4/en/innodb-foreign-key-constraints.html)
- [MySQL 8.4 Reference Manual — InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
- [MySQL 8.4 Reference Manual — InnoDB Lock and Lock-Wait Information](https://dev.mysql.com/doc/refman/8.4/en/innodb-information-schema-understanding-innodb-locking.html)
- [MySQL 8.4 Reference Manual — The INFORMATION_SCHEMA STATISTICS Table](https://dev.mysql.com/doc/refman/8.4/en/information-schema-statistics-table.html)
- [MySQL 8.4 Reference Manual — Performance Schema data_locks Table](https://dev.mysql.com/doc/refman/8.4/en/performance-schema-data-locks-table.html)
