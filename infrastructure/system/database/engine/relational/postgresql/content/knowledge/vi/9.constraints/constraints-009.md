# Ràng buộc trì hoãn được và SET CONSTRAINTS trong PostgreSQL

Ràng buộc (*constraint*) là một trong những cơ chế quan trọng giúp PostgreSQL giữ dữ liệu đúng: `PRIMARY KEY` bảo đảm danh tính hàng, `UNIQUE` ngăn giá trị trùng, `FOREIGN KEY` bảo vệ quan hệ tham chiếu và `CHECK` giới hạn miền giá trị. Thông thường, khi một câu lệnh làm dữ liệu vi phạm ràng buộc, PostgreSQL báo lỗi ngay thay vì để trạng thái sai tiếp tục tồn tại.

Tuy nhiên, có những nghiệp vụ cần thực hiện **nhiều bước trong cùng một giao dịch**. Sau bước đầu tiên, dữ liệu có thể tạm thời không thỏa một ràng buộc, nhưng khi bước cuối cùng hoàn tất thì toàn bộ dữ liệu lại hợp lệ.

Ví dụ:

- Hoán đổi hai mã duy nhất giữa hai bản ghi.
- Chèn bản ghi con trước bản ghi cha, nhưng bảo đảm cả hai được tạo trước khi commit.
- Xây dựng hai hàng có quan hệ tham chiếu vòng trong một giao dịch.
- Tạm thời di chuyển các đối tượng trong một sơ đồ quan hệ, rồi hoàn tất các liên kết mới trước khi giao dịch kết thúc.

PostgreSQL hỗ trợ những trường hợp này bằng **ràng buộc trì hoãn được** (*deferrable constraints*) cùng câu lệnh **`SET CONSTRAINTS`**. Khi được cấu hình và sử dụng đúng, chúng cho phép chuyển một số phép kiểm tra từ **thời điểm thực thi câu SQL** sang **mốc kết thúc giao dịch**, mà vẫn bảo đảm dữ liệu cuối cùng không vi phạm ràng buộc khi commit thành công.

Bài học dùng PostgreSQL hiện đại với những ví dụ đầy đủ về `UNIQUE`, `FOREIGN KEY`, `NO ACTION`, `RESTRICT`, `SET CONSTRAINTS ... DEFERRED/IMMEDIATE`, cách quan sát qua `pg_constraint` và các lưu ý cho transaction, migration và ứng dụng Java/JDBC.

## 1. Nhìn bài toán qua một giao dịch nhiều bước

Giả sử bảng quản lý nhân viên có hai người dùng mã thẻ:

| employee_id | badge_code |
| ---: | --- |
| 1 | A |
| 2 | B |

Do luân chuyển vị trí, hai người cần **đổi mã thẻ cho nhau**:

~~~text
Ban đầu:  nhân viên 1 = A; nhân viên 2 = B
Đích:     nhân viên 1 = B; nhân viên 2 = A
~~~

Nếu `badge_code` có ràng buộc `UNIQUE` được kiểm tra ngay, phép cập nhật đầu tiên:

~~~sql
UPDATE employees
SET badge_code = 'B'
WHERE employee_id = 1;
~~~

có thể bị từ chối vì nhân viên 2 **đang** giữ mã `B`. Nhưng nếu xét **sau cả hai cập nhật**, mỗi mã vẫn xuất hiện đúng một lần.

Với một ràng buộc `UNIQUE DEFERRABLE`, ta có thể tổ chức:

~~~text
BEGIN
  |
  +-- SET CONSTRAINTS ... DEFERRED
  |
  +-- employee 1: A -> B     [tạm thời trùng B]
  |
  +-- employee 2: B -> A     [không còn trùng]
  |
  +-- COMMIT
        |
        +-- PostgreSQL kiểm tra ràng buộc còn trì hoãn
        +-- Dữ liệu cuối hợp lệ -> COMMIT thành công
~~~

Nếu cuối giao dịch vẫn còn hai người cùng mã `B`, `COMMIT` thất bại. **Trì hoãn không có nghĩa bỏ qua kiểm tra.**

### Điều gì làm nên một “trạng thái tạm thời”?

Trong PostgreSQL, transaction bao gồm nhiều câu SQL được thực hiện như một đơn vị:

~~~sql
BEGIN;

-- Bước 1
-- Bước 2
-- ...

COMMIT;
~~~

Những thay đổi chưa commit chưa trở thành dữ liệu đã commit cho các transaction khác theo cơ chế MVCC. Việc PostgreSQL cho phép **chính transaction đang chạy** tạm thấy trạng thái vi phạm ràng buộc trì hoãn không đồng nghĩa các session khác được tự do đọc dữ liệu chưa commit ấy.

Mấu chốt là phải **sửa hết vi phạm trước khi PostgreSQL kiểm tra ràng buộc** tại `COMMIT` hoặc tại một lệnh `SET CONSTRAINTS ... IMMEDIATE` thích hợp.

## 2. Ba khái niệm cần phân biệt

Khi tạo một ràng buộc thuộc loại có hỗ trợ trì hoãn, PostgreSQL cho phép khai báo:

~~~sql
CONSTRAINT ten_rang_buoc
    UNIQUE (cot)
    DEFERRABLE INITIALLY IMMEDIATE
~~~

hoặc:

~~~sql
CONSTRAINT ten_rang_buoc
    UNIQUE (cot)
    DEFERRABLE INITIALLY DEFERRED
~~~

### 2.1. NOT DEFERRABLE

**`NOT DEFERRABLE`** có nghĩa ràng buộc không thể được chuyển sang chế độ trì hoãn bằng `SET CONSTRAINTS`.

~~~sql
CONSTRAINT uq_email UNIQUE (email) NOT DEFERRABLE
~~~

Đây là trạng thái mặc định của các ràng buộc tương ứng khi không khai báo `DEFERRABLE`. Với kiểu này, lệnh `SET CONSTRAINTS ALL DEFERRED` không biến nó thành một ràng buộc trì hoãn được.

### 2.2. DEFERRABLE

**`DEFERRABLE`** có nghĩa ràng buộc **có khả năng chuyển đổi** giữa:

- **`IMMEDIATE`:** kiểm tra theo thời điểm thông thường của ràng buộc; không để một vi phạm tồn tại qua các câu lệnh như khi deferred.
- **`DEFERRED`:** trì hoãn phép kiểm tra thích hợp tới cuối transaction, trừ khi được yêu cầu kiểm tra sớm.

Từ khóa `DEFERRABLE` **chỉ nói về khả năng**, chưa khẳng định giao dịch mới sẽ bắt đầu ở chế độ nào.

### 2.3. INITIALLY IMMEDIATE và INITIALLY DEFERRED

Đây là **chế độ mặc định của ràng buộc ở thời điểm bắt đầu mỗi transaction**:

| Khai báo | Có thể chuyển sang DEFERRED? | Chế độ ban đầu mỗi transaction |
| --- | --- | --- |
| `NOT DEFERRABLE` | Không | Kiểm tra không trì hoãn |
| `DEFERRABLE INITIALLY IMMEDIATE` | Có | `IMMEDIATE` |
| `DEFERRABLE INITIALLY DEFERRED` | Có | `DEFERRED` |

Nếu chỉ viết `DEFERRABLE` mà không ghi `INITIALLY ...`, mặc định là **`INITIALLY IMMEDIATE`**.

Một cách ghi nhớ:

~~~text
DEFERRABLE       = có được quyền trì hoãn hay không?
INITIALLY ...    = ban đầu kiểm tra lúc nào?
SET CONSTRAINTS  = muốn đổi chế độ cho transaction hiện tại?
~~~

### Ví dụ ba khai báo tương phản

~~~sql
CREATE TABLE example_nondef (
    code text UNIQUE NOT DEFERRABLE
);

CREATE TABLE example_def_imm (
    code text UNIQUE DEFERRABLE INITIALLY IMMEDIATE
);

CREATE TABLE example_def_def (
    code text UNIQUE DEFERRABLE INITIALLY DEFERRED
);
~~~

Ba bảng dùng chung kiểu `text` nhưng **khác thời điểm kiểm tra uniqueness** khi có nhiều câu lệnh trong một transaction.

## 3. Loại ràng buộc nào có thể trì hoãn?

Trong PostgreSQL, những loại ràng buộc thông thường có hỗ trợ `DEFERRABLE` gồm:

- `UNIQUE`.
- `PRIMARY KEY`.
- `FOREIGN KEY`.
- `EXCLUDE`.
- Các **constraint trigger** được khai báo phù hợp.

Không áp dụng cơ chế trì hoãn của `SET CONSTRAINTS` cho:

- `NOT NULL`.
- `CHECK` thông thường.

### Bảng tổng hợp

| Loại | Có hỗ trợ trì hoãn? | Ví dụ tình huống |
| --- | --- | --- |
| `UNIQUE` | Có | Hoán đổi hai giá trị duy nhất |
| `PRIMARY KEY` | Có | Điều chỉnh khóa qua nhiều bước trong một transaction |
| `FOREIGN KEY` | Có | Tạo bản ghi tham chiếu trước bản ghi được tham chiếu |
| `EXCLUDE` | Có | Tạm sắp xếp lại các khoảng/ràng buộc loại trừ |
| `CHECK` | Không theo cơ chế này | Điều kiện số lượng dương vẫn được kiểm tra theo hành vi thông thường |
| `NOT NULL` | Không | Không thể để null ở cột bắt buộc rồi chờ COMMIT mới sửa |
| `CONSTRAINT TRIGGER` | Có nếu khai báo `DEFERRABLE` phù hợp | Kiểm tra quy tắc cần chạy cuối giao dịch |

Ví dụ bảng:

~~~sql
CREATE TABLE example_rules (
    id integer PRIMARY KEY DEFERRABLE,
    name text NOT NULL,
    quantity integer CHECK (quantity > 0),
    CONSTRAINT uq_name UNIQUE (name)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Ngay cả khi `uq_name` được trì hoãn, việc ghi `name = NULL` vẫn vi phạm `NOT NULL` theo thời điểm kiểm tra bình thường, và `quantity = -1` vẫn vi phạm `CHECK`. **Không có lệnh `SET CONSTRAINTS ALL DEFERRED` nào biến hai quy tắc đó thành kiểm tra ở cuối transaction.**

### Phân biệt default “không trì hoãn” và “ban đầu kiểm tra ngay”

Hai khai báo:

~~~sql
UNIQUE (code) NOT DEFERRABLE
~~~

và:

~~~sql
UNIQUE (code) DEFERRABLE INITIALLY IMMEDIATE
~~~

đều thường từ chối trạng thái trùng nếu thực hiện một loạt thao tác mà không đổi chế độ, nhưng khác căn bản: **chỉ ràng buộc thứ hai có thể được chuyển sang `DEFERRED`** trong transaction.

Đây là khác biệt cần quyết định ngay từ thiết kế, vì cách thay đổi thuộc tính trì hoãn sau khi constraint đã tồn tại không giống nhau giữa các loại constraint.

## 4. Lệnh SET CONSTRAINTS hoạt động thế nào?

Cú pháp:

~~~sql
SET CONSTRAINTS { ALL | ten_constraint [, ...] }
    { DEFERRED | IMMEDIATE };
~~~

Ví dụ:

~~~sql
BEGIN;

SET CONSTRAINTS ALL DEFERRED;

-- Thực hiện các thay đổi có liên quan.

SET CONSTRAINTS ALL IMMEDIATE;

COMMIT;
~~~

### 4.1. Chỉ có ý nghĩa trong transaction hiện tại

`SET CONSTRAINTS` dùng để thay đổi chế độ kiểm tra trong **transaction đang chạy**. Chế độ đó không tự trở thành cấu hình mặc định cho mọi transaction tiếp theo.

~~~sql
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
-- Các câu SQL.
COMMIT;

-- Transaction mới quay về INITIALLY ... của từng constraint.
BEGIN;
-- Không tự kế thừa SET CONSTRAINTS từ transaction trước.
COMMIT;
~~~

Nếu chạy `SET CONSTRAINTS` **ngoài transaction block**, PostgreSQL có thể phát cảnh báo và không đạt hiệu quả thay đổi chế độ mà bạn mong muốn. Vì thế khi cần trì hoãn, hãy đặt nó sau `BEGIN` và trước thao tác tạo vi phạm tạm thời.

### 4.2. ALL không có nghĩa tất cả constraint đều trì hoãn được

~~~sql
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
~~~

Lệnh này tác động tới **các ràng buộc có khả năng trì hoãn** trong phạm vi transaction; nó không thay đổi `NOT DEFERRABLE`, `NOT NULL` hoặc `CHECK`.

Do vậy, câu lệnh:

~~~sql
INSERT INTO some_table (required_name) VALUES (NULL);
~~~

vẫn thất bại khi `required_name` là cột `NOT NULL`, dù trước đó đã gọi `SET CONSTRAINTS ALL DEFERRED`.

### 4.3. Chọn một hoặc nhiều constraint cụ thể

Nếu chỉ muốn trì hoãn duy nhất một ràng buộc:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

-- Những constraint khác vẫn giữ chế độ riêng.

COMMIT;
~~~

Tên constraint có thể được viết kèm schema, và PostgreSQL có quy tắc tra cứu tên constraint theo schema/search path. **Tên constraint không nhất thiết duy nhất trên toàn database**; nếu nhiều ràng buộc trùng tên nằm trong phạm vi tra cứu, lệnh có thể áp dụng tới nhiều ràng buộc phù hợp.

Trong code migration, đặt **tên constraint có chủ đích** và schema rõ ràng giúp giảm nhầm lẫn. Khi cần chắc chắn một lệnh `SET CONSTRAINTS` tác động đúng đối tượng, hãy kiểm tra danh sách constraint trong catalog trước.

### 4.4. Chuyển từ DEFERRED về IMMEDIATE sẽ kiểm tra ngay

Đây là quy tắc quan trọng nhất khi dùng lệnh:

~~~sql
SET CONSTRAINTS def_lab.uq_badge_code IMMEDIATE;
~~~

Nếu ràng buộc đang `DEFERRED`, PostgreSQL sẽ **kiểm tra hồi tố những vi phạm còn đang chờ** trong lúc xử lý lệnh chuyển sang `IMMEDIATE`.

Nếu có vi phạm, lệnh `SET CONSTRAINTS ... IMMEDIATE` **thất bại**, và chế độ không được chuyển thành công. Trong transaction thông thường, lỗi này khiến transaction rơi vào trạng thái aborted cho tới khi rollback hoặc xử lý savepoint phù hợp.

Vì thế `SET CONSTRAINTS ... IMMEDIATE` có thể dùng làm **điểm xác minh sớm** trước `COMMIT`, nhưng chỉ khi ứng dụng biết cách xử lý lỗi.

## 5. Thực hành 1: hoán đổi hai giá trị UNIQUE

Đây là ví dụ rõ nhất để thấy lý do cần deferrable uniqueness.

### 5.1. Tạo schema và bảng

Chạy trong database lab có quyền tạo schema:

~~~sql
CREATE SCHEMA def_lab;

CREATE TABLE def_lab.employees (
    employee_id integer PRIMARY KEY,
    full_name text NOT NULL,
    badge_code text NOT NULL,
    CONSTRAINT uq_badge_code
        UNIQUE (badge_code)
        DEFERRABLE INITIALLY IMMEDIATE
);

INSERT INTO def_lab.employees
    (employee_id, full_name, badge_code)
VALUES
    (1, 'Lan', 'A'),
    (2, 'Minh', 'B');
~~~

Kiểm tra:

~~~sql
SELECT employee_id, full_name, badge_code
FROM def_lab.employees
ORDER BY employee_id;
~~~

Kết quả ban đầu:

~~~text
 employee_id | full_name | badge_code
-------------+-----------+-----------
           1 | Lan       | A
           2 | Minh      | B
~~~

`employee_id` là `PRIMARY KEY` thông thường, còn `badge_code` được bảo vệ bởi **`UNIQUE DEFERRABLE INITIALLY IMMEDIATE`**. Hai ràng buộc này có thể có chế độ kiểm tra khác nhau.

### 5.2. Thử đổi trực tiếp khi chưa trì hoãn

~~~sql
BEGIN;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

-- Dự kiến lỗi: B đang được nhân viên 2 sử dụng.
ROLLBACK;
~~~

Lệnh `UPDATE` bị từ chối vì `uq_badge_code` đang `IMMEDIATE` theo mặc định. `ROLLBACK` giải phóng transaction lỗi và giữ nguyên hai mã ban đầu.

Không sửa bằng cách tạm xóa `UNIQUE` rồi thêm lại nếu mục tiêu chỉ là một giao dịch hoán đổi. Việc bỏ constraint có thể cho phép những transaction khác ghi dữ liệu trùng không mong muốn và tạo thêm vấn đề concurrency.

### 5.3. Trì hoãn đúng một UNIQUE constraint

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

-- Đến đây chính transaction tạm thấy hai mã B.

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 2;

-- Không còn mã trùng.
COMMIT;
~~~

Sau `COMMIT`:

~~~sql
SELECT employee_id, badge_code
FROM def_lab.employees
ORDER BY employee_id;
~~~

Kết quả:

~~~text
 employee_id | badge_code
-------------+-----------
           1 | B
           2 | A
~~~

Điểm then chốt:

1. Cả hai lệnh `UPDATE` ở **cùng một transaction**.
2. `SET CONSTRAINTS` chạy **trước bước tạo trùng tạm thời**.
3. Ràng buộc đã được khai báo **`DEFERRABLE`**, nên lệnh đổi chế độ hợp lệ.
4. Đến `COMMIT`, dữ liệu cuối thỏa `UNIQUE`, nên transaction thành công.

### 5.4. Khôi phục dữ liệu lab để thử lại

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 1;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 2;

COMMIT;
~~~

Kết quả lại là `(1, A)` và `(2, B)`. Chỉ thực hiện trên bảng lab đã tạo ở mục này.

## 6. Nếu đến COMMIT vẫn vi phạm UNIQUE thì sao?

Trì hoãn không bỏ kiểm tra:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

-- Không sửa mã B của nhân viên 2.
COMMIT;
~~~

Lần này **`COMMIT` thất bại** vì hai hàng có `badge_code = 'B'`. Transaction không được commit; kết quả dữ liệu đã commit trước đó được giữ nguyên.

Trong log/driver, lỗi sẽ xuất hiện **ở thời điểm commit**, chứ không nhất thiết ở câu `UPDATE` gây ra trạng thái trùng.

Điều này có hệ quả cho code:

- Không thể kết luận toàn bộ nghiệp vụ đã thành công chỉ vì mọi lệnh `UPDATE` trả thành công.
- Phải xử lý lỗi khi `COMMIT`, không chỉ xử lý lỗi khi chạy từng statement.
- Nếu commit thất bại, không được tiếp tục giả định transaction đã lưu thành công.
- Với JDBC hoặc framework giao dịch, cần xem rõ ngoại lệ phát sinh lúc `connection.commit()` hoặc lúc kết thúc transaction do framework quản lý.

Nếu dùng cơ chế retry, phải phân loại đúng lỗi và bảo đảm thao tác lặp có tính idempotent; **vi phạm unique do dữ liệu cuối thực sự trùng** thường không biến mất chỉ bằng retry y hệt.

## 7. Thử kiểm tra sớm bằng SET CONSTRAINTS ... IMMEDIATE

Ta có thể yêu cầu PostgreSQL xác minh giữa transaction trước khi commit:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

-- Lúc này vẫn còn giá trị B bị trùng.
SET CONSTRAINTS def_lab.uq_badge_code IMMEDIATE;

-- Lệnh trên dự kiến thất bại.
ROLLBACK;
~~~

Đây là ví dụ **cố ý gây lỗi**. Nếu chạy trong `psql`, bạn sẽ thấy thông báo trùng unique **tại lệnh `SET CONSTRAINTS ... IMMEDIATE`**.

Phiên bản thành công:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 2;

-- Kiểm tra ngay, không đợi COMMIT.
SET CONSTRAINTS def_lab.uq_badge_code IMMEDIATE;

-- Bây giờ uniqueness đã được kiểm tra thành công.
COMMIT;
~~~

Sau bước này, dữ liệu lại ở trạng thái hai mã đổi chỗ. Nếu muốn quay về bộ dữ liệu ban đầu, dùng transaction khôi phục như mục 5.4.

### Vì sao nên dùng bước xác minh sớm?

Trong nghiệp vụ phức tạp, một transaction có nhiều bước:

~~~text
1. Dời các mã định danh
2. Kiểm tra ràng buộc trì hoãn được
3. Tính những kết quả phụ trợ
4. Ghi log nghiệp vụ trong cùng transaction
5. COMMIT
~~~

Kiểm tra ở bước 2 giúp phát hiện sai sót trước khi thực hiện thêm nhiều công việc. Nhưng nếu bước 2 thất bại, transaction phải được rollback hoặc khôi phục về savepoint hợp lệ; không được chỉ bỏ qua lỗi rồi gọi `COMMIT`.

## 8. Thực hành 2: FOREIGN KEY trì hoãn được

Ngoài unique, trường hợp thường gặp là **bản ghi con được tạo trước bản ghi cha trong cùng transaction**.

### 8.1. Tạo hai bảng có khóa ngoại DEFERRABLE

~~~sql
CREATE TABLE def_lab.departments (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL
);

CREATE TABLE def_lab.staff (
    staff_id integer PRIMARY KEY,
    department_id integer NOT NULL,
    staff_name text NOT NULL,
    CONSTRAINT fk_staff_department
        FOREIGN KEY (department_id)
        REFERENCES def_lab.departments (department_id)
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Giải thích:

- `departments.department_id` là khóa chính được tham chiếu.
- `staff.department_id` là cột khóa ngoại của bảng con.
- `ON DELETE NO ACTION` là hành vi tham chiếu cần phân biệt với `RESTRICT` khi nói về trì hoãn.
- `DEFERRABLE INITIALLY IMMEDIATE` cho phép chuyển thời điểm kiểm tra FK bằng `SET CONSTRAINTS`.

### 8.2. Thử tạo staff trước department khi chưa trì hoãn

~~~sql
BEGIN;

INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES
    (1001, 10, 'An');

-- Lỗi: department_id=10 chưa tồn tại.
ROLLBACK;
~~~

Khi kiểm tra ngay, PostgreSQL từ chối bản ghi con tham chiếu hàng cha không có thật.

### 8.3. Trì hoãn FK và hoàn tất cả hai bảng trong một transaction

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.fk_staff_department DEFERRED;

INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES
    (1001, 10, 'An');

INSERT INTO def_lab.departments
    (department_id, department_name)
VALUES
    (10, 'Engineering');

COMMIT;
~~~

Transaction hợp lệ khi commit vì tại thời điểm cuối, `staff.department_id=10` đã có hàng `departments.department_id=10` tương ứng.

Kiểm tra:

~~~sql
SELECT
    s.staff_id,
    s.staff_name,
    d.department_name
FROM def_lab.staff AS s
JOIN def_lab.departments AS d
    ON d.department_id = s.department_id
ORDER BY s.staff_id;
~~~

Kết quả dự kiến có nhân viên `An` thuộc `Engineering`.

**Không kết luận** rằng ứng dụng nên thường xuyên chèn con trước cha. Trong đa số đường ghi thông thường, tạo hàng cha rồi tạo hàng con dễ hiểu hơn. Trì hoãn hữu ích khi có một lý do thiết kế rõ ràng như nhập dữ liệu phụ thuộc lẫn nhau, chuyển đổi khóa hoặc xử lý tham chiếu vòng.

### 8.4. Vi phạm FK cuối transaction vẫn thất bại

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.fk_staff_department DEFERRED;

INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES
    (2002, 999, 'Binh');

-- Không tạo department 999.
COMMIT;
~~~

`COMMIT` dự kiến lỗi vì thiếu hàng cha. Hàng `staff_id=2002` không được commit thành công.

Ràng buộc trì hoãn **bảo vệ tính toàn vẹn tại thời điểm kiểm tra**, không cho phép lưu vĩnh viễn tham chiếu mồ côi.

## 9. NO ACTION và RESTRICT trong FOREIGN KEY

Đây là điểm rất dễ nhầm vì cả hai thường **đều ngăn xóa hàng cha khi còn hàng con**.

Ví dụ:

~~~sql
FOREIGN KEY (department_id)
REFERENCES def_lab.departments(department_id)
ON DELETE NO ACTION
DEFERRABLE INITIALLY DEFERRED
~~~

so với:

~~~sql
FOREIGN KEY (department_id)
REFERENCES def_lab.departments(department_id)
ON DELETE RESTRICT
DEFERRABLE INITIALLY DEFERRED
~~~

### 9.1. NO ACTION cho phép trì hoãn phép kiểm tra tham chiếu

Với `NO ACTION` và FK deferrable, PostgreSQL có thể cho phép tạm xóa cha trước, miễn là **xử lý hết hàng con trước thời điểm kiểm tra**.

Đang có:

~~~text
departments:  department_id = 10
staff:        staff_id = 1001, department_id = 10
~~~

Thử trong transaction và rollback:

~~~sql
BEGIN;

SET CONSTRAINTS def_lab.fk_staff_department DEFERRED;

DELETE FROM def_lab.departments
WHERE department_id = 10;

DELETE FROM def_lab.staff
WHERE staff_id = 1001;

-- Không còn hàng con tham chiếu department 10.
SET CONSTRAINTS def_lab.fk_staff_department IMMEDIATE;

-- Không muốn xóa dữ liệu lab thật:
ROLLBACK;
~~~

Nếu constraint đang trì hoãn và dữ liệu cuối sau hai lệnh `DELETE` không còn vi phạm, phép kiểm tra có thể thành công.

### 9.2. RESTRICT không chờ tới cuối transaction cho hành động xóa

`ON DELETE RESTRICT` có ý nghĩa **không cho thao tác xóa cha thực hiện khi vẫn còn hàng con tham chiếu**, ngay cả khi ràng buộc FK được khai báo `DEFERRABLE` trong những khía cạnh khác.

Nói cách khác:

> **`RESTRICT` là hành vi của referential action không thể trì hoãn cho thao tác tương ứng; `NO ACTION` là phép kiểm tra có thể được trì hoãn nếu constraint đã khai báo deferrable và chuyển sang DEFERRED.**

Nếu nghiệp vụ cần “xóa cha tạm thời, xử lý con sau trong cùng transaction”, hãy thiết kế với `NO ACTION DEFERRABLE` và thử nghiệm, thay vì coi `RESTRICT` như một từ đồng nghĩa hoàn toàn.

### 9.3. CASCADE, SET NULL và SET DEFAULT cũng khác

Các hành vi:

~~~sql
ON DELETE CASCADE
ON DELETE SET NULL
ON DELETE SET DEFAULT
~~~

mô tả **hành động PostgreSQL thực hiện trên hàng con** khi hàng cha bị xóa. Đây không chỉ là một phép kiểm tra trì hoãn giống `NO ACTION`; hành động tham chiếu như xóa con hoặc đặt null/default xảy ra theo quy tắc tương ứng với thao tác DML, không đơn giản bị giữ lại đến `COMMIT` vì constraint được khai báo deferrable.

| Referential action | Khi cha bị xóa và còn hàng con | Có thể dựa vào trì hoãn để tạm để lại hàng con? |
| --- | --- | --- |
| `NO ACTION` | Kiểm tra quan hệ; có thể lỗi nếu còn tham chiếu | **Có**, nếu FK deferrable và chế độ deferred |
| `RESTRICT` | Từ chối thao tác xóa cha khi còn tham chiếu | **Không** cho hành vi RESTRICT |
| `CASCADE` | Xóa các hàng con theo quy tắc FK | Không phải mô hình “đợi rồi mới cascade” |
| `SET NULL` | Đặt khóa ngoại bên con thành null | Không; còn phải thỏa `NOT NULL`/các constraint khác |
| `SET DEFAULT` | Đặt khóa ngoại bên con theo default | Không; default mới cũng phải đáp ứng tính hợp lệ cuối cùng |

Không nhầm `ON DELETE CASCADE` trong FK với `DROP TABLE ... CASCADE` của DDL: một cái xử lý **hàng dữ liệu**, cái kia xử lý **đối tượng schema**.

## 10. Thực hành 3: tham chiếu vòng giữa hai bảng

Một số mô hình có quan hệ vòng, chẳng hạn mỗi phòng ban có trưởng phòng là nhân viên của phòng ban ấy, trong khi mỗi nhân viên lại bắt buộc thuộc một phòng ban.

~~~text
departments
    department_id ──────────────────┐
    leader_staff_id ──────┐         |
                         |         |
                         v         v
                       staff
                       staff_id
                       department_id
~~~

Nếu cả hai cột FK đều bắt buộc, việc tạo dữ liệu ban đầu khó theo thứ tự thông thường: chưa có nhân viên thì chưa lập được phòng ban với trưởng phòng; chưa có phòng ban thì chưa lập được nhân viên.

### 10.1. Tạo hai bảng cùng FK trì hoãn

Để tránh ảnh hưởng bảng ở mục trước, dùng các tên mới:

~~~sql
CREATE TABLE def_lab.teams (
    team_id integer PRIMARY KEY,
    team_name text NOT NULL,
    leader_id integer NOT NULL
);

CREATE TABLE def_lab.team_members (
    member_id integer PRIMARY KEY,
    team_id integer NOT NULL,
    member_name text NOT NULL,
    CONSTRAINT fk_member_team
        FOREIGN KEY (team_id)
        REFERENCES def_lab.teams(team_id)
        DEFERRABLE INITIALLY DEFERRED
);

ALTER TABLE def_lab.teams
ADD CONSTRAINT fk_team_leader
FOREIGN KEY (leader_id)
REFERENCES def_lab.team_members(member_id)
DEFERRABLE INITIALLY DEFERRED;
~~~

Hai FK được kiểm tra ở cuối transaction theo chế độ mặc định.

### 10.2. Tạo hai hàng liên quan trong cùng transaction

~~~sql
BEGIN;

INSERT INTO def_lab.teams
    (team_id, team_name, leader_id)
VALUES
    (100, 'Payments', 1000);

INSERT INTO def_lab.team_members
    (member_id, team_id, member_name)
VALUES
    (1000, 100, 'Chi');

COMMIT;
~~~

Sau khi cả hai insert hoàn tất, các quan hệ tham chiếu tồn tại:

~~~sql
SELECT
    t.team_id,
    t.team_name,
    m.member_name AS leader_name
FROM def_lab.teams AS t
JOIN def_lab.team_members AS m
    ON m.member_id = t.leader_id;
~~~

### Giới hạn của ví dụ tham chiếu vòng

Hai FK đã định nghĩa bảo đảm:

- `teams.leader_id` tham chiếu **một nhân viên tồn tại**.
- `team_members.team_id` tham chiếu **một team tồn tại**.

Tuy nhiên, chúng **chưa bảo đảm trưởng phòng thuộc chính team đó**. Để ràng buộc chính xác quy tắc ấy, cần thiết kế thêm khóa ghép/unique và FK tương ứng hoặc cơ chế dữ liệu thích hợp.

Điều này cho thấy trì hoãn là công cụ về **thời điểm kiểm tra**, không tự làm mạnh hơn nội dung logic của một ràng buộc.

### Có nên tạo tham chiếu vòng ở mọi hệ thống?

Không. Quan hệ vòng có thể tăng độ khó khi import, xóa dữ liệu, thay đổi FK và migration. Đôi khi phương án:

1. Tạo phòng ban chưa có trưởng phòng, nếu nghiệp vụ cho phép.
2. Tạo nhân viên thuộc phòng ban.
3. Gán trưởng phòng trong transaction.

với `leader_id` có thể null trong giai đoạn khởi tạo sẽ đơn giản hơn. Chỉ dùng vòng FK deferrable khi đó là mô hình phù hợp và không thể/không nên nới quy tắc khác.

## 11. UNIQUE DEFERRABLE và INSERT ... ON CONFLICT

Một đánh đổi quan trọng: PostgreSQL dùng một unique index/constraint phù hợp làm **bộ phân xử xung đột** (*conflict arbiter*) cho:

~~~sql
INSERT INTO some_table (...)
VALUES (...)
ON CONFLICT (...) DO UPDATE ...;
~~~

Nhưng **deferrable unique constraint không được dùng làm arbiter cho `ON CONFLICT`** theo quy tắc PostgreSQL.

Ví dụ:

~~~sql
CREATE TABLE def_lab.promo_codes (
    promo_id integer PRIMARY KEY,
    code text NOT NULL,
    CONSTRAINT uq_promo_code
        UNIQUE (code)
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Lệnh dưới đây **không phải một mẫu upsert hợp lệ dựa trên constraint deferrable**:

~~~sql
-- Minh họa tình huống KHÔNG sử dụng trực tiếp:
INSERT INTO def_lab.promo_codes (promo_id, code)
VALUES (1, 'SAVE10')
ON CONFLICT ON CONSTRAINT uq_promo_code
DO UPDATE SET code = EXCLUDED.code;
~~~

PostgreSQL không thể dùng `uq_promo_code` làm arbiter vì nó là deferrable uniqueness.

### Tại sao điều này quan trọng?

Nếu ứng dụng thường xuyên dùng `INSERT ... ON CONFLICT (code) DO UPDATE`, việc chuyển constraint `UNIQUE(code)` từ nondeferrable sang deferrable để hỗ trợ một migration có thể **làm hỏng đường ghi hiện tại**.

Trước khi chọn deferrable uniqueness, hãy hỏi:

- Ứng dụng có dùng UPSERT dựa trên cột này không?
- Có thể dùng một khóa khác có unique index nondeferrable phù hợp làm arbiter không?
- Chỉ có một tình huống hoán đổi hiếm gặp, hay đây là thao tác chính?
- Có thể thiết kế lại quy trình đổi mã để không cần trạng thái trùng tạm thời không?

Một số hệ thống nên giữ **unique constraint thông thường** cho khóa dùng `ON CONFLICT`, thay vì đánh đổi quá nhiều để có khả năng trì hoãn.

### CREATE UNIQUE INDEX không có tùy chọn DEFERRABLE

Deferrability là thuộc tính của **constraint** khi được khai báo theo cú pháp hỗ trợ, không phải một tùy chọn bất kỳ trên `CREATE UNIQUE INDEX`.

Đúng hướng:

~~~sql
ALTER TABLE def_lab.some_table
ADD CONSTRAINT uq_some_code
UNIQUE (code)
DEFERRABLE INITIALLY IMMEDIATE;
~~~

Ví dụ chỉ hợp lệ khi bảng `some_table` và cột `code` tồn tại. Không dùng `CREATE UNIQUE INDEX ... DEFERRABLE` vì đó không phải cú pháp tạo unique index của PostgreSQL.

## 12. DEFERRABLE PRIMARY KEY và EXCLUDE constraint

### 12.1. PRIMARY KEY có thể trì hoãn

~~~sql
CREATE TABLE def_lab.legacy_keys (
    old_key text NOT NULL,
    description text NOT NULL,
    CONSTRAINT pk_legacy_keys
        PRIMARY KEY (old_key)
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

`PRIMARY KEY` vẫn đòi khóa không null và duy nhất. Khả năng trì hoãn chỉ ảnh hưởng **phần kiểm tra uniqueness phù hợp**; nó không cho phép lưu null ở cột PK rồi sửa sau bằng `SET CONSTRAINTS ALL DEFERRED`.

Khi thiết kế khóa chính, cần xét các FK tham chiếu, phương án UPSERT và quy tắc PostgreSQL liên quan tới unique arbiter/target key. Không nên tự động đặt mọi PK thành deferrable.

### 12.2. EXCLUDE dùng cho những quy tắc loại trừ

`EXCLUDE` là constraint mạnh của PostgreSQL dùng để ngăn những cặp hàng thỏa đồng thời các phép so sánh bị loại trừ. Nó thường được dùng trong bài toán đặt lịch, dải thời gian hoặc phạm vi địa lý.

Ví dụ với một phòng không được có hai cuộc họp chồng thời gian, cần extension `btree_gist` để có operator class GiST phù hợp cho kiểu integer:

~~~sql
-- Chỉ thực hiện trên database lab khi có quyền cài extension.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE def_lab.meeting_rooms (
    booking_id integer PRIMARY KEY,
    room_id integer NOT NULL,
    during tstzrange NOT NULL,
    CONSTRAINT ex_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            during WITH &&
        )
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

Ở đây:

- `tstzrange` mô tả một khoảng thời gian có timezone.
- Toán tử `&&` kiểm tra hai khoảng có giao nhau không.
- `EXCLUDE` ngăn hai hàng **cùng phòng** có các khoảng thời gian chồng nhau.
- `DEFERRABLE` cho phép một số thao tác sắp lịch nhiều bước trong cùng transaction.

Ví dụ chèn thử:

~~~sql
INSERT INTO def_lab.meeting_rooms
    (booking_id, room_id, during)
VALUES
    (
        1, 10,
        tstzrange(
            '2026-11-16 09:00:00+07',
            '2026-11-16 10:00:00+07',
            '[)'
        )
    );
~~~

Nếu thêm cuộc họp thứ hai cùng phòng, giao nhau với khoảng trên, phép kiểm tra sẽ lỗi trừ khi transaction đang dùng chế độ trì hoãn hợp lệ và đã giải quyết hết giao nhau trước khi kiểm tra.

**Đừng coi ví dụ này là tính năng có sẵn mà không cần điều kiện:** extension, operator class, quyền cài đặt và index cần tương thích với phiên bản PostgreSQL thực tế.

## 13. Constraint trigger và SET CONSTRAINTS

Ngoài constraint khai báo trực tiếp, PostgreSQL có **constraint trigger** với cơ chế `DEFERRABLE`. Đây là dạng trigger đặc biệt có thể được lên lịch kiểm tra theo chế độ immediate/deferred.

Ví dụ cấu trúc cú pháp:

~~~sql
CREATE CONSTRAINT TRIGGER trigger_name
AFTER INSERT OR UPDATE ON some_table
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION some_trigger_function();
~~~

Trong đó:

- Đây là **`AFTER ROW` trigger** theo các giới hạn của constraint trigger.
- Hàm trigger phải tồn tại, có kiểu trả về `trigger` và triển khai logic kiểm tra/raise exception đúng.
- `SET CONSTRAINTS` có thể tác động tới thời điểm kích hoạt của constraint trigger được khai báo phù hợp.
- Một trigger thông thường được tạo bằng `CREATE TRIGGER` không tự trở thành constraint trigger có thể trì hoãn.

### Khi nào cân nhắc constraint trigger?

Ví dụ quy tắc khó biểu diễn bằng một `CHECK` một hàng:

~~~text
Một batch chuyển tiền phải cân bằng tổng ghi nợ và ghi có
trước khi COMMIT, dù giữa transaction có nhiều dòng mới.
~~~

Một constraint trigger được thiết kế phù hợp có thể kiểm tra một số quy tắc nghiệp vụ tại thời điểm trì hoãn. Tuy nhiên, concurrency, snapshot, khóa và các transaction khác có thể khiến triển khai **không đơn giản như một phép SUM ở cuối giao dịch**.

Nếu có thể dùng `FOREIGN KEY`, `UNIQUE`, `EXCLUDE` hoặc schema tốt hơn, thường nên ưu tiên constraint khai báo trực tiếp. Constraint trigger phù hợp cho yêu cầu thật sự cần logic riêng và phải được kiểm thử với nhiều session đồng thời.

## 14. Xác định ràng buộc có DEFERRABLE hay không qua catalog

PostgreSQL lưu thông tin trong `pg_constraint`. Hai cột đặc biệt hữu ích:

- `condeferrable`: constraint **có thể trì hoãn** hay không.
- `condeferred`: constraint **được khai báo ban đầu ở chế độ DEFERRED** hay không.

### 14.1. Liệt kê constraint của các bảng lab

~~~sql
SELECT
    n.nspname AS schema_name,
    c.conrelid::regclass AS table_name,
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    c.condeferrable AS is_deferrable,
    c.condeferred AS initially_deferred,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint AS c
JOIN pg_namespace AS n
    ON n.oid = c.connamespace
WHERE n.nspname = 'def_lab'
ORDER BY c.conrelid::regclass::text, c.conname;
~~~

Một số giá trị `contype` thường gặp:

| `contype` | Loại constraint |
| --- | --- |
| `p` | Primary key |
| `u` | Unique |
| `f` | Foreign key |
| `x` | Exclusion |
| `c` | Check |

`pg_get_constraintdef` trả về định nghĩa constraint dễ đọc hơn việc chỉ nhìn các cờ.

### 14.2. Lọc riêng các constraint có thể trì hoãn

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE connamespace = 'def_lab'::regnamespace
  AND condeferrable
ORDER BY conrelid::regclass::text, conname;
~~~

Đây là cách nhanh để rà soát một schema trước khi viết `SET CONSTRAINTS`. Nó cho thấy **định nghĩa đã lưu**, không phải tất cả chi tiết chế độ tạm thời đã được thay đổi trong transaction hiện tại.

### 14.3. Xem FOREIGN KEY và hành vi xóa/cập nhật

~~~sql
SELECT
    conname,
    conrelid::regclass AS child_table,
    confrelid::regclass AS parent_table,
    condeferrable,
    condeferred,
    confdeltype,
    confupdtype,
    pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE connamespace = 'def_lab'::regnamespace
  AND contype = 'f'
ORDER BY conname;
~~~

Thay vì tự giải mã tất cả ký tự `confdeltype` và `confupdtype`, hãy xem `pg_get_constraintdef` để đọc rõ `ON DELETE NO ACTION`, `RESTRICT` hay `CASCADE`.

### 14.4. \d trong psql

Trong `psql`:

~~~text
\d+ def_lab.employees
\d+ def_lab.staff
\d+ def_lab.teams
~~~

Đây là meta-command `psql`, giúp xem constraint và phần khai báo phù hợp với phiên bản công cụ. Các câu SQL ở trên thích hợp hơn khi muốn trích xuất thông tin theo cấu trúc cho một báo cáo kiểm kê.

## 15. Chuyển một constraint đã tồn tại sang DEFERRABLE

Không phải mọi constraint đều có cùng cách đổi deferrability sau khi tạo.

### 15.1. ALTER CONSTRAINT đối với FOREIGN KEY

PostgreSQL hỗ trợ chỉnh thuộc tính deferrability của FK đã tồn tại bằng:

~~~sql
ALTER TABLE def_lab.staff
ALTER CONSTRAINT fk_staff_department
DEFERRABLE INITIALLY DEFERRED;
~~~

Hoặc chuyển về:

~~~sql
ALTER TABLE def_lab.staff
ALTER CONSTRAINT fk_staff_department
DEFERRABLE INITIALLY IMMEDIATE;
~~~

Khi áp dụng, cần quyền sở hữu phù hợp và lập kế hoạch lock/DDL trên bảng thật.

### 15.2. Với UNIQUE/PRIMARY KEY/EXCLUDE phải xem chiến lược khác

`ALTER TABLE ... ALTER CONSTRAINT ... DEFERRABLE` trong PostgreSQL hiện đại **không hỗ trợ thay đổi mọi loại constraint giống nhau**; cú pháp chỉnh thuộc tính này hiện chủ yếu áp dụng cho **foreign key constraint**.

Nếu cần chuyển một `UNIQUE NOT DEFERRABLE` đang tồn tại thành deferrable, thường phải **lập kế hoạch tái tạo constraint** phù hợp, đồng thời xem:

- Các foreign key hoặc đối tượng khác phụ thuộc vào constraint/index cũ.
- Đường ghi đang dùng `INSERT ... ON CONFLICT`.
- Thời lượng lock và thời gian xây dựng index.
- Dữ liệu hiện tại có còn duy nhất không.
- Phương án rollback hoặc tạo một cấu trúc thay thế an toàn.

Không tự làm:

~~~sql
ALTER TABLE real_orders
DROP CONSTRAINT uq_order_code;
~~~

trên production chỉ để tạo lại constraint mà chưa kiểm tra phụ thuộc và tính nhất quán. Trong khoảng bỏ unique, các giao dịch khác có thể ghi dữ liệu không mong muốn nếu kế hoạch DDL không bảo đảm kiểm soát truy cập thích hợp.

## 16. Tác động đến transaction và isolation

Ràng buộc trì hoãn là một **quy tắc kiểm tra**, không phải một isolation level mới.

Một transaction có thể tạm vi phạm unique hoặc FK ở chế độ deferred, nhưng:

- Transaction khác không tự thấy các thay đổi chưa commit theo cách bình thường.
- PostgreSQL vẫn sử dụng MVCC và khóa để điều phối truy cập đồng thời.
- Những vi phạm cuối cùng vẫn được phát hiện tại điểm kiểm tra.
- Lỗi ràng buộc có thể phát sinh muộn, kể cả khi ứng dụng đã chạy nhiều bước thành công.

### 16.1. Trì hoãn không làm mọi tình huống ghi đồng thời hợp lệ

Giả sử hai session cùng cố đặt mã `PROMO-1` cho hai hàng khác nhau. Dù ràng buộc unique là deferrable, **không thể commit thành công hai trạng thái cuối cùng cùng chứa mã đó**.

Trong thực tế, một transaction có thể phải chờ transaction khác, gặp lỗi unique hoặc có kết quả chịu ảnh hưởng của cách PostgreSQL điều phối cạnh tranh. Không sử dụng `SET CONSTRAINTS ALL DEFERRED` như cách bỏ qua khóa hoặc bảo đảm tất cả giao dịch sẽ commit.

### 16.2. Trì hoãn không thay thế khóa cho nghiệp vụ phức tạp

Những quy tắc như:

~~~text
Tổng số vé đã bán không vượt quá số ghế.
Số dư tài khoản không âm sau chuyển khoản.
Mỗi team có đúng một leader đang hoạt động.
~~~

có thể cần constraint phù hợp, transaction, khóa hàng, isolation hoặc chiến lược xử lý cạnh tranh riêng. `DEFERRABLE` chỉ thay đổi **thời điểm kiểm tra các constraint hỗ trợ**; nó không tạo cơ chế kiểm tra tùy ý cho mọi điều kiện nhiều hàng.

### 16.3. Không kéo dài transaction vô cớ

Vì lỗi có thể xuất hiện muộn, có thể có xu hướng giữ transaction rất lâu để giải quyết nhiều bước. Đó thường không phải lựa chọn tốt:

- Transaction dài có thể giữ khóa lâu.
- Ảnh hưởng vacuum và vòng đời các phiên bản hàng.
- Làm nhiều công việc phải rollback nếu constraint cuối thất bại.
- Tăng độ khó tái thử và xác định nguyên nhân lỗi.

Hãy dùng transaction đủ ngắn để bảo vệ đúng đơn vị nghiệp vụ, kết hợp các bước xác minh ở `SET CONSTRAINTS ... IMMEDIATE` khi phù hợp.

## 17. SET CONSTRAINTS trong Java/JDBC

Ứng dụng Java dùng JDBC cần một **transaction thực sự** để điều khiển chế độ constraint.

Mẫu mã giả lập có thể viết:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Statement;

public class DeferredConstraintExample {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:postgresql://127.0.0.1:5432/lab_db";
        String user = System.getenv("PG_LAB_USER");
        String password = System.getenv("PG_LAB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {

            connection.setAutoCommit(false);

            try {
                try (Statement statement = connection.createStatement()) {
                    statement.execute(
                        "SET CONSTRAINTS def_lab.uq_badge_code DEFERRED"
                    );
                }

                try (PreparedStatement update =
                         connection.prepareStatement(
                             "UPDATE def_lab.employees "
                             + "SET badge_code = ? "
                             + "WHERE employee_id = ?")) {

                    update.setString(1, "B");
                    update.setInt(2, 1);
                    update.executeUpdate();

                    update.setString(1, "A");
                    update.setInt(2, 2);
                    update.executeUpdate();
                }

                // Tùy chọn: yêu cầu kiểm tra ngay tại đây.
                try (Statement statement = connection.createStatement()) {
                    statement.execute(
                        "SET CONSTRAINTS def_lab.uq_badge_code IMMEDIATE"
                    );
                }

                connection.commit();
            } catch (SQLException failure) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackError) {
                    failure.addSuppressed(rollbackError);
                }
                throw failure;
            }
        }
    }
}
~~~

Ví dụ giả định:

- Bảng `def_lab.employees` đã tồn tại.
- Bộ dữ liệu ban đầu là `(1,A)` và `(2,B)`.
- PostgreSQL JDBC driver đã có trong classpath.
- Các biến môi trường chứa thông tin đăng nhập hợp lệ.
- Tài khoản có quyền cập nhật những hàng đó.

Nếu chạy lại sau khi hai mã đã đổi chỗ, thứ tự cập nhật trên có thể dẫn tới trạng thái khác mong muốn hoặc tạo trùng cuối transaction. Hãy kiểm tra trạng thái đầu vào và tính **idempotent** của nghiệp vụ thực tế.

### 17.1. Vì sao setAutoCommit(false) quan trọng?

Nếu Java chạy từng câu ở chế độ autocommit, mỗi câu statement có thể thuộc một transaction riêng. Khi đó không có một transaction dài đủ để chứa cả:

~~~text
SET CONSTRAINTS DEFERRED
UPDATE bước 1
UPDATE bước 2
COMMIT
~~~

Mục tiêu là **cả ba câu đầu chạy trên cùng một JDBC Connection và cùng một transaction**.

### 17.2. Lỗi có thể xuất hiện lúc commit

Trong code, bắt ngoại lệ chỉ quanh `executeUpdate()` là chưa đủ. `connection.commit()` cũng có thể ném `SQLException` vì ràng buộc trì hoãn còn vi phạm.

Ứng dụng nên phân loại lỗi theo SQLSTATE/exception phù hợp, log thông tin đủ để chẩn đoán nhưng không làm lộ dữ liệu nhạy cảm, rollback transaction khi thất bại và không báo thành công cho người dùng trước khi commit thực sự hoàn tất.

### 17.3. Connection pool

Với HikariCP hoặc pool tương đương, `Connection.close()` trong code thường trả connection về pool. Mỗi request vẫn phải commit hoặc rollback trước khi trả kết nối và không dựa vào trạng thái transaction còn sót từ request trước.

`SET CONSTRAINTS` không phải cấu hình session vĩnh viễn; sau khi kết thúc transaction, transaction tiếp theo lấy lại chế độ **INITIALLY ...** của constraint. Nhưng transaction bị bỏ dở trong pool vẫn nguy hiểm với dữ liệu, khóa và tính đúng của request sau.

## 18. Lỗi thường gặp và cách xác định nguyên nhân

### 18.1. SET CONSTRAINTS không có tác dụng

Một số nguyên nhân:

1. Lệnh chạy ngoài `BEGIN ... COMMIT`, không có phạm vi transaction kéo dài.
2. Constraint thực tế là `NOT DEFERRABLE`.
3. Tên constraint được truyền không đúng hoặc không thuộc schema kỳ vọng.
4. Dữ liệu vi phạm `NOT NULL` hoặc `CHECK`, vốn không thể trì hoãn.
5. Ứng dụng đang dùng nhiều connection khác nhau cho các bước tưởng thuộc cùng transaction.

Kiểm tra:

~~~sql
SELECT
    conname,
    conrelid::regclass AS table_name,
    condeferrable,
    condeferred,
    pg_get_constraintdef(oid)
FROM pg_constraint
WHERE connamespace = 'def_lab'::regnamespace
ORDER BY conname;
~~~

### 18.2. Vẫn lỗi khi dùng ON DELETE RESTRICT

`RESTRICT` không phải tham chiếu kiểm tra có thể để tới cuối transaction như `NO ACTION DEFERRABLE`. Nếu workflow cần tạm thời xóa cha trước khi xử lý hàng con, cần xem lại hành vi referential action và mô hình quan hệ.

### 18.3. COMMIT thất bại dù mọi UPDATE thành công

Điều này thường đúng với bản chất **deferred checking**: trước khi commit, dữ liệu cuối vẫn vi phạm một constraint. Kiểm tra các hàng liên quan trong transaction và xem thông báo constraint name ở lỗi, không chỉ rà soát câu SQL cuối cùng.

### 18.4. SET CONSTRAINTS ... IMMEDIATE phát lỗi

Thay đổi từ deferred về immediate buộc PostgreSQL kiểm tra những vi phạm chờ xử lý. Nếu chưa sửa hết trạng thái tạm thời, lệnh kiểm tra sớm thất bại. Thường cần rollback giao dịch hoặc xử lý savepoint nếu ứng dụng có chủ đích sử dụng chúng.

### 18.5. ON CONFLICT không sử dụng được UNIQUE deferrable

`ON CONFLICT` cần arbiter phù hợp, trong khi deferrable unique/exclusion constraint không dùng làm arbiter theo cơ chế này. Xem lại thiết kế constraint hoặc chọn đường ghi không phụ thuộc vào deferrable constraint làm arbiter.

### 18.6. ALTER CONSTRAINT không đổi được UNIQUE

`ALTER TABLE ... ALTER CONSTRAINT ... DEFERRABLE` không hỗ trợ mọi loại constraint như nhau. Nếu đây là unique/PK, cần thiết kế migration phù hợp thay vì suy từ cú pháp dành cho FK.

### 18.7. Một transaction giữ trạng thái vi phạm quá lâu

Không nên lạm dụng deferrable để tích lũy hàng nghìn thao tác không liên quan. Nếu transaction chết giữa chừng, nhiều công việc phải rollback; nếu chạy lâu, khóa và chi phí MVCC có thể ảnh hưởng hệ thống.

### 18.8. Tên constraint trùng nhau

Trong PostgreSQL, tên constraint có thể không duy nhất trên toàn database, và `SET CONSTRAINTS` có quy tắc chọn theo schema. Hãy đặt tên rõ ràng, truy vấn `pg_constraint` trước khi chạy migration và dùng schema-qualified constraint name khi thích hợp.

## 19. Quy trình quyết định có dùng DEFERRABLE không

~~~text
                Có yêu cầu thay đổi nhiều bước?
                             |
                   +---------+---------+
                   |                   |
                  Không                Có
                   |                   |
       Dùng constraint thông     Trạng thái giữa các bước
       thường khi đủ             có thể vi phạm constraint?
                                       |
                              +--------+--------+
                              |                 |
                             Không               Có
                              |                 |
                  Không cần trì hoãn    Constraint thuộc loại
                                       được DEFERRABLE?
                                             |
                                    +--------+--------+
                                    |                 |
                                   Không               Có
                                    |                 |
                           Đổi thiết kế/transaction  Có ảnh hưởng
                           hoặc logic kiểm tra       ON CONFLICT / FK
                                                    / concurrency?
                                                        |
                                                        v
                                                Thử với workload thật
                                                và xử lý lỗi COMMIT
~~~

Một số câu hỏi nên tự trả lời:

- **Có thật sự phải để dữ liệu tạm sai?** Hay có thể đổi thứ tự cập nhật để không bao giờ vi phạm?
- **Loại constraint có được phép trì hoãn?** Không áp dụng cho `CHECK`/`NOT NULL`.
- **Điều kiện hợp lệ cuối cùng là gì?** Cần xác minh tại commit hoặc trước đó.
- **Ứng dụng có dùng `ON CONFLICT` hay FK đòi khóa mục tiêu phù hợp?** Đây là quyết định kiến trúc.
- **Mức độ cạnh tranh giữa các transaction thế nào?** Deferral không thay thế concurrency control.
- **Có đường ghi từ nhiều service không?** Một constraint được thiết kế tốt phải giữ được tính đúng kể cả khi ứng dụng mới xuất hiện.

## 20. Thực hành kết hợp: cập nhật nhiều đối tượng an toàn

Một migration có thể cần đổi mã nhân viên và chuyển quan hệ nhân viên sang phòng ban mới trong cùng transaction.

Giả sử:

- `def_lab.employees` có `uq_badge_code DEFERRABLE`.
- `def_lab.staff` có `fk_staff_department DEFERRABLE`.
- Những bảng thuộc lab riêng và đã có dữ liệu mẫu.

Một mẫu transaction:

~~~sql
BEGIN;

SET CONSTRAINTS
    def_lab.uq_badge_code,
    def_lab.fk_staff_department
DEFERRED;

-- Hoán đổi hai mã thẻ.
UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 2;

-- Tạo nhân viên tham chiếu phòng ban sẽ tạo ngay sau đó.
INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES
    (3003, 30, 'Dung');

INSERT INTO def_lab.departments
    (department_id, department_name)
VALUES
    (30, 'Analytics');

-- Kiểm tra trước khi commit.
SET CONSTRAINTS
    def_lab.uq_badge_code,
    def_lab.fk_staff_department
IMMEDIATE;

COMMIT;
~~~

Ví dụ này **không idempotent**: chạy nhiều lần với cùng mã ID có thể vi phạm primary key. Nó nhằm minh họa cách nhóm nhiều ràng buộc trong một transaction. Trong migration thật, phải kiểm tra trạng thái đầu vào, thiết kế xử lý trường hợp chạy lại, khóa cần thiết và phương án rollback.

Thành công của `SET CONSTRAINTS ... IMMEDIATE` xác nhận những ràng buộc đã được yêu cầu kiểm tra tại mốc đó theo quy tắc PostgreSQL. Nó **không chứng minh mọi quy tắc nghiệp vụ ngoài database** đều đúng.

## 21. Bài tập thực hành

Thực hiện trên schema `def_lab` hoặc dự đoán kết quả trước. Những ví dụ cố ý gây lỗi nên chạy riêng và kết thúc bằng `ROLLBACK` khi cần.

### Bài 1. Phân biệt ba khai báo

Cho:

~~~sql
UNIQUE (code) NOT DEFERRABLE

UNIQUE (code) DEFERRABLE INITIALLY IMMEDIATE

UNIQUE (code) DEFERRABLE INITIALLY DEFERRED
~~~

Hãy xác định constraint nào có thể chuyển sang `DEFERRED` và constraint nào sẽ bắt đầu transaction ở chế độ `DEFERRED`.

### Bài 2. Hoán đổi mã duy nhất

Hai hàng có mã `A` và `B`. Viết một transaction dùng `SET CONSTRAINTS` để hoán đổi mã, vẫn giữ `UNIQUE` ở cuối giao dịch.

### Bài 3. COMMIT vẫn thất bại

Một transaction với unique deferred sửa hàng thứ nhất thành mã của hàng thứ hai nhưng không sửa hàng thứ hai. Vì sao các lệnh `UPDATE` có thể thành công mà `COMMIT` lại lỗi?

### Bài 4. Kiểm tra sớm

Trong một transaction có constraint deferred, chạy `SET CONSTRAINTS ... IMMEDIATE` khi vẫn còn vi phạm unique. Lệnh nào phát lỗi? Vì sao?

### Bài 5. Chèn con trước cha

Cho `staff.department_id` tham chiếu `departments.department_id` bằng FK `DEFERRABLE INITIALLY IMMEDIATE`. Viết transaction chèn staff trước department mà vẫn có thể commit thành công.

### Bài 6. RESTRICT và NO ACTION

Khác biệt cốt lõi giữa `ON DELETE RESTRICT` và `ON DELETE NO ACTION` là gì khi constraint FK được khai báo `DEFERRABLE`?

### Bài 7. Những constraint không thể trì hoãn

Sau:

~~~sql
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
~~~

cột `quantity integer NOT NULL CHECK (quantity > 0)` có chấp nhận `quantity = NULL` hoặc `quantity = -5` tạm thời tới commit không?

### Bài 8. SET CONSTRAINTS ngoài transaction

Ứng dụng gửi `SET CONSTRAINTS ALL DEFERRED` khi mỗi lệnh đang autocommit riêng. Vì sao thao tác sau đó vẫn không được trì hoãn như mong muốn?

### Bài 9. Metadata

Viết truy vấn từ `pg_constraint` liệt kê tên constraint, bảng, `condeferrable` và `condeferred` trong schema `def_lab`.

### Bài 10. UPSERT và deferrable uniqueness

Vì sao một cột được bảo vệ chỉ bởi `UNIQUE DEFERRABLE` có thể không phù hợp khi ứng dụng dùng `INSERT ... ON CONFLICT (code) DO UPDATE`?

### Bài 11. ALTER CONSTRAINT

Giả sử một FK đang `NOT DEFERRABLE`. Viết câu SQL chuyển nó sang `DEFERRABLE INITIALLY DEFERRED`. Có áp dụng cùng một cú pháp thay đổi đó cho mọi unique constraint không?

### Bài 12. Transaction và isolation

Deferrable constraint có khiến dữ liệu chưa commit của transaction A tự hiện ra trong transaction B không? Có bảo đảm hai transaction đồng thời đặt cùng mã unique đều commit được không?

### Bài 13. Thiết kế vòng

Nếu bảng `teams` yêu cầu `leader_id` không null, còn `team_members` yêu cầu `team_id` không null, có thể tạo hai hàng tham chiếu nhau theo cách nào? Ràng buộc FK cơ bản có tự bảo đảm leader thuộc đúng team không?

### Bài 14. Xử lý lỗi JDBC

Ứng dụng chỉ bắt lỗi quanh `executeUpdate()` mà không bắt lỗi `connection.commit()`. Rủi ro gì phát sinh khi có constraint `INITIALLY DEFERRED`?

### Bài 15. Chọn chiến lược

Một dịch vụ thương mại dùng `ON CONFLICT` để upsert mã coupon trong hầu hết giao dịch. Một tác vụ hiếm muốn tạm trùng mã để hoán đổi coupon. Có nên đổi unique constraint hiện tại sang deferrable ngay không? Nêu các yếu tố cần xem trước quyết định.

### Gợi ý đáp án

**Bài 1:** `NOT DEFERRABLE` không thể chuyển; hai khai báo `DEFERRABLE` đều có thể chuyển. Chỉ `INITIALLY DEFERRED` bắt đầu transaction ở chế độ deferred.

**Bài 2:**

~~~sql
BEGIN;
SET CONSTRAINTS def_lab.uq_badge_code DEFERRED;

UPDATE def_lab.employees
SET badge_code = 'B'
WHERE employee_id = 1;

UPDATE def_lab.employees
SET badge_code = 'A'
WHERE employee_id = 2;

COMMIT;
~~~

**Bài 3:** khi deferred, PostgreSQL có thể cho phép vi phạm tạm thời nhưng sẽ từ chối transaction nếu cuối cùng vẫn còn mã trùng.

**Bài 4:** `SET CONSTRAINTS ... IMMEDIATE` sẽ kiểm tra hồi tố và báo lỗi ngay nếu vi phạm đang chờ chưa được sửa.

**Bài 5:**

~~~sql
BEGIN;
SET CONSTRAINTS def_lab.fk_staff_department DEFERRED;

INSERT INTO def_lab.staff
    (staff_id, department_id, staff_name)
VALUES (4004, 40, 'Mai');

INSERT INTO def_lab.departments
    (department_id, department_name)
VALUES (40, 'Operations');

COMMIT;
~~~

**Bài 6:** `NO ACTION` là phép kiểm tra có thể trì hoãn nếu FK deferrable và đang deferred; `RESTRICT` ngăn thao tác xóa/cập nhật cha ở thời điểm tham chiếu đang tồn tại theo quy tắc hành vi RESTRICT.

**Bài 7:** không. `NOT NULL` và `CHECK` không chịu cơ chế trì hoãn từ `SET CONSTRAINTS`.

**Bài 8:** `SET CONSTRAINTS` cần chạy trong transaction bao trùm các thao tác liên quan; autocommit từng lệnh không giữ cùng phạm vi trì hoãn.

**Bài 9:**

~~~sql
SELECT
    conrelid::regclass AS table_name,
    conname,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE connamespace = 'def_lab'::regnamespace
ORDER BY conrelid::regclass::text, conname;
~~~

**Bài 10:** PostgreSQL không dùng deferrable unique constraint làm arbiter của `ON CONFLICT`. Cần chiến lược constraint hoặc upsert khác.

**Bài 11:**

~~~sql
ALTER TABLE def_lab.staff
ALTER CONSTRAINT fk_staff_department
DEFERRABLE INITIALLY DEFERRED;
~~~

Cú pháp thay đổi deferrability bằng `ALTER CONSTRAINT` không áp dụng chung cho mọi unique/PK/exclusion constraint.

**Bài 12:** không. MVCC và isolation vẫn hoạt động. Hai transaction không thể cùng commit trạng thái cuối vi phạm uniqueness của cùng một constraint.

**Bài 13:** tạo hai FK `DEFERRABLE INITIALLY DEFERRED`, chèn cả hai hàng trong cùng transaction rồi commit. Muốn bảo đảm leader thuộc chính team, phải thiết kế thêm ràng buộc phù hợp.

**Bài 14:** lỗi có thể xuất hiện tại `commit()`, ứng dụng dễ báo thành công sai hoặc bỏ qua việc rollback/xử lý ngoại lệ.

**Bài 15:** chưa nên đổi ngay. Cần xem tác động lên `ON CONFLICT`, các đường ghi hiện tại, concurrency, cách hoán đổi không tạo trùng tạm, migration và khả năng rollback.

## 22. Danh sách kiểm tra trước khi áp dụng trong hệ thống thật

| Nhóm | Câu hỏi cần trả lời |
| --- | --- |
| Loại constraint | Là `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY`, `EXCLUDE` hay constraint trigger? |
| Khả năng trì hoãn | `pg_constraint.condeferrable` có đúng là `true` không? |
| Chế độ mặc định | `INITIALLY IMMEDIATE` hay `INITIALLY DEFERRED`? |
| Phạm vi transaction | Mọi thao tác liên quan có nằm trên cùng connection và cùng transaction không? |
| Kiểm tra sớm | Có cần `SET CONSTRAINTS ... IMMEDIATE` trước những bước tốn kém không? |
| Referential action | FK dùng `NO ACTION`, `RESTRICT` hay một hành động khác? |
| Dữ liệu cuối | Đã xác định rõ trạng thái phải hợp lệ tại commit? |
| UPSERT | Có đường ghi `ON CONFLICT` phụ thuộc unique constraint này không? |
| Concurrency | Đã thử cạnh tranh giữa nhiều transaction và xử lý deadlock/constraint error? |
| Exception handling | Ứng dụng bắt lỗi cả ở statement và `COMMIT` chưa? |
| Catalog | Có kiểm kê dependency, constraint names và thuộc tính qua `pg_constraint` không? |
| Vận hành | Có migration staging, backup, rollback và đo lock/độ trễ không? |

## 23. Bảng cú pháp tra cứu nhanh

| Mục tiêu | Cú pháp |
| --- | --- |
| UNIQUE có thể trì hoãn, mặc định kiểm tra ngay | `UNIQUE (code) DEFERRABLE INITIALLY IMMEDIATE` |
| UNIQUE mặc định trì hoãn | `UNIQUE (code) DEFERRABLE INITIALLY DEFERRED` |
| FK có thể trì hoãn | `FOREIGN KEY (parent_id) REFERENCES parent(id) DEFERRABLE` |
| Chỉ trì hoãn FK có tên | `SET CONSTRAINTS schema.fk_name DEFERRED;` |
| Trì hoãn mọi constraint hỗ trợ | `SET CONSTRAINTS ALL DEFERRED;` |
| Kiểm tra ngay những constraint đang deferred | `SET CONSTRAINTS ALL IMMEDIATE;` |
| Chỉnh deferrability của FK | `ALTER TABLE child ALTER CONSTRAINT fk_name DEFERRABLE INITIALLY DEFERRED;` |
| Kiểm tra metadata deferrability | `SELECT conname, condeferrable, condeferred FROM pg_constraint;` |
| Kết thúc transaction hợp lệ | `COMMIT;` |
| Hủy transaction thử nghiệm | `ROLLBACK;` |

## 24. Tổng kết

**`DEFERRABLE` là khả năng trì hoãn, `INITIALLY ...` là chế độ khởi đầu và `SET CONSTRAINTS` là công cụ thay đổi chế độ trong transaction hiện tại.** Với những loại constraint được hỗ trợ, PostgreSQL có thể cho phép một trạng thái vi phạm tồn tại giữa các câu SQL, nhưng transaction chỉ commit thành công nếu dữ liệu đáp ứng ràng buộc tại thời điểm kiểm tra.

Ba ý cần nhớ:

1. **Không phải mọi constraint đều trì hoãn được.** `UNIQUE`, `PRIMARY KEY`, `FOREIGN KEY` và `EXCLUDE` có cơ chế phù hợp; `CHECK` và `NOT NULL` không được chuyển sang deferred bằng `SET CONSTRAINTS`.
2. **`NO ACTION` khác `RESTRICT` ở thời điểm kiểm tra FK.** Khi workflow cần xử lý tạm quan hệ tham chiếu qua nhiều bước, sự khác biệt này quyết định thiết kế có hoạt động hay không.
3. **Ứng dụng phải xử lý lỗi ở `COMMIT`.** Việc mọi câu `UPDATE` hoặc `INSERT` đã trả thành công không chứng minh transaction có dữ liệu hợp lệ cuối cùng.

Sử dụng ràng buộc trì hoãn khi **bài toán cần một trạng thái trung gian tạm thời** trong giao dịch ngắn, có kiểm soát và có kết quả cuối hợp lệ. Nếu một quy trình thường xuyên phải trì hoãn gần như mọi ràng buộc, đó cũng là tín hiệu nên xem lại thứ tự thao tác, mô hình dữ liệu hoặc ranh giới transaction trước khi tiếp tục mở rộng thiết kế.
