# Xử lý lỗi ràng buộc và tính nguyên tử của câu lệnh

Khi thêm dữ liệu vào cơ sở dữ liệu, câu lệnh `INSERT` có thể bị từ chối vì nhiều lý do: mã bản ghi đã tồn tại, cột bắt buộc nhận `NULL`, khóa ngoại tham chiếu tới bản ghi không có thật, hoặc giá trị không vượt qua điều kiện `CHECK`. Việc hiểu **lỗi ràng buộc** (*constraint violation*) không chỉ giúp sửa một câu SQL; nó còn quyết định cách thiết kế chức năng nhập liệu, API, tác vụ nạp dữ liệu hàng loạt và cách khôi phục sau lỗi.

Một câu hỏi rất thường gặp:

> “Nếu `INSERT` có 100 dòng và dòng thứ 80 bị lỗi, 79 dòng đầu đã được lưu hay chưa?”

Trong **PostgreSQL**, với một câu lệnh `INSERT` thông thường, câu trả lời là **không**: khi lỗi khiến cả câu lệnh thất bại, các thay đổi dữ liệu của **toàn bộ câu lệnh** đều bị hủy. Đó là **tính nguyên tử của câu lệnh** (*statement atomicity*). Tuy nhiên, điều này **không đồng nghĩa** rằng một chuỗi gồm nhiều câu `INSERT` luôn được hoàn tác cùng nhau, và cũng không đồng nghĩa mọi tác động ngoài cơ sở dữ liệu đều có thể hoàn tác.

Bài học thuộc chương **Thêm dữ liệu** của module **Database SQL**. Các ví dụ có thể chạy trong **PostgreSQL** và tập trung vào:

1. Nhận diện lỗi `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, `CHECK` và `FOREIGN KEY`.
2. Phân biệt **một câu lệnh nhiều dòng**, **nhiều câu lệnh**, **giao dịch** và **điểm lưu `SAVEPOINT`**.
3. Xác định khi nào dùng `ON CONFLICT DO NOTHING`/`DO UPDATE`, khi nào phải sửa dữ liệu nguồn.
4. Thiết kế cách nhập dữ liệu an toàn mà không vô tình bỏ qua lỗi, tạo bản ghi nửa vời hoặc hiểu nhầm trạng thái thành công.

## 1. Ràng buộc là lớp bảo vệ cuối cùng của dữ liệu

Một bảng nhân viên có thể có các quy tắc nghiệp vụ:

- Mỗi nhân viên có **một mã duy nhất**.
- Email liên hệ là **bắt buộc** và **không trùng**.
- Nhân viên phải thuộc về một phòng ban đã được khai báo.
- Lương không được âm.
- Trạng thái chỉ thuộc một danh sách giá trị cho phép.

Ta có thể mô tả chúng bằng ràng buộc ngay trong schema:

| Ràng buộc | Câu hỏi được bảo vệ | Ví dụ |
|---|---|---|
| `PRIMARY KEY` | Bản ghi có định danh duy nhất không? | `employee_id` |
| `UNIQUE` | Có trùng giá trị cần duy nhất không? | `email` |
| `NOT NULL` | Có thiếu giá trị bắt buộc không? | `email`, `department_id` |
| `CHECK` | Giá trị có thỏa điều kiện logic không? | `salary >= 0` |
| `FOREIGN KEY` | Giá trị tham chiếu có tồn tại ở bảng cha không? | `department_id` |

Ràng buộc không chỉ là “gợi ý” cho giao diện nhập liệu. Chúng được hệ quản trị kiểm tra tại những thời điểm xác định và có thể **từ chối toàn bộ câu lệnh** khi dữ liệu vi phạm.

### 1.1. Vì sao cần ràng buộc dù ứng dụng đã kiểm tra?

Kiểm tra ở ứng dụng rất có ích để hiển thị thông báo dễ hiểu. Nhưng dữ liệu còn có thể đến từ:

- Script SQL chạy trực tiếp.
- Tác vụ ETL nhập tệp CSV.
- Một ứng dụng khác dùng cùng database.
- Tiến trình đồng thời đang ghi dữ liệu.
- Dữ liệu cũ hoặc API bị gọi ngoài thứ tự dự kiến.

Một phép kiểm tra như “email này đã có chưa?” trong ứng dụng không đủ ngăn **hai yêu cầu đồng thời** cùng chọn một email còn trống. `UNIQUE` trong database mới là cơ chế bảo vệ tính duy nhất khi các giao dịch cạnh tranh.

> **Nguyên tắc:** kiểm tra ở ứng dụng để hỗ trợ người dùng; ràng buộc ở database để giữ bất biến của dữ liệu, kể cả khi một đường ghi nào đó quên kiểm tra.

## 2. Bộ dữ liệu thực hành PostgreSQL

Ta sử dụng hai bảng tạm: `constraint_lab_departments` là danh mục phòng ban; `constraint_lab_employees` là nhân viên, mỗi dòng đại diện cho một nhân viên.

### 2.1. Tạo bảng và ràng buộc

```sql
CREATE TEMP TABLE constraint_lab_departments (
    department_id INTEGER PRIMARY KEY,
    department_name TEXT NOT NULL UNIQUE
);

CREATE TEMP TABLE constraint_lab_employees (
    employee_id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    department_id INTEGER NOT NULL,
    salary NUMERIC(12, 2) NOT NULL,
    employment_status TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_lab_employee_department
        FOREIGN KEY (department_id)
        REFERENCES constraint_lab_departments(department_id),

    CONSTRAINT ck_lab_employee_salary
        CHECK (salary >= 0),

    CONSTRAINT ck_lab_employee_status
        CHECK (employment_status IN ('ACTIVE', 'PAUSED'))
);
```

`TEXT`, `NUMERIC`, `TIMESTAMPTZ`, `CURRENT_TIMESTAMP` và cách khai báo ràng buộc trong ví dụ phù hợp PostgreSQL. Trong hệ quản trị khác, tên kiểu hoặc cú pháp ngày giờ có thể khác.

### 2.2. Chèn dữ liệu gốc hợp lệ

```sql
INSERT INTO constraint_lab_departments
    (department_id, department_name)
VALUES
    (10, 'Engineering'),
    (20, 'Sales');

INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (1, 'an@example.test',   10, 1500.00),
    (2, 'binh@example.test', 20, 1200.00);

SELECT
    employee_id, email, department_id,
    salary, employment_status
FROM constraint_lab_employees
ORDER BY employee_id;
```

Kết quả ban đầu:

| employee_id | email | department_id | salary | employment_status |
|---:|---|---:|---:|---|
| 1 | an@example.test | 10 | 1500.00 | ACTIVE |
| 2 | binh@example.test | 20 | 1200.00 | ACTIVE |

Vì không cung cấp `employment_status` và `created_at`, PostgreSQL dùng **giá trị `DEFAULT`** đã khai báo cho hai cột đó.

**Cách thực hành với lỗi:** những câu SQL ở các mục tiếp theo **cố ý gây lỗi**. Hãy chạy **từng khối riêng**, quan sát mã lỗi rồi tiếp tục; không dán tất cả câu lệnh lỗi vào một transaction đang mở. Nếu đã dùng `BEGIN` và gặp lỗi, phải `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` theo hướng dẫn trước khi tiếp tục. Các ví dụ minh họa thành công có thể làm thay đổi dữ liệu tạm; để có trạng thái ban đầu như bảng trên, mở phiên thực hành mới và chạy lại hai khối tạo bảng/chèn dữ liệu.

## 3. Lỗi `PRIMARY KEY`: trùng định danh

`employee_id` là khóa chính nên mỗi giá trị chỉ được dùng cho **một dòng**:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (1, 'chi@example.test', 10, 1800.00);
```

Trong dữ liệu ban đầu, `employee_id = 1` đã thuộc về An. PostgreSQL sẽ báo một lỗi tương tự:

```text
ERROR: duplicate key value violates unique constraint
DETAIL: Key (employee_id)=(1) already exists.
SQLSTATE: 23505
```

Thông điệp thực tế có thể chứa tên ràng buộc/index do PostgreSQL tạo; đừng phụ thuộc vào chính xác từng chữ của message. **SQLSTATE `23505`** mới là tín hiệu có cấu trúc giúp ứng dụng nhận diện lỗi **vi phạm tính duy nhất**.

### 3.1. `PRIMARY KEY` khác `UNIQUE` ở đâu?

Trong PostgreSQL, khóa chính đồng thời đòi hỏi **duy nhất** và **không `NULL`**. Một bảng có tối đa **một khai báo khóa chính**, nhưng có thể có nhiều ràng buộc `UNIQUE`.

Với ví dụ:

```sql
employee_id INTEGER PRIMARY KEY,
email TEXT NOT NULL UNIQUE
```

cả hai cột đều duy nhất, nhưng `employee_id` là định danh chính thức của mỗi nhân viên. Trùng bất kỳ cột nào trong hai cột đều có thể tạo lỗi `23505`.

### 3.2. Khóa chính tổng hợp

Ở một bảng đăng ký khóa học, định danh có thể là **một cặp**:

```sql
CREATE TEMP TABLE constraint_lab_enrollments (
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, course_id)
);
```

Một sinh viên có thể học nhiều khóa, một khóa có thể có nhiều sinh viên, nhưng **cùng một cặp `(student_id, course_id)` không được chèn hai lần**.

```sql
INSERT INTO constraint_lab_enrollments (student_id, course_id)
VALUES (100, 500), (100, 501);   -- Hợp lệ.

INSERT INTO constraint_lab_enrollments (student_id, course_id)
VALUES (100, 500);               -- Trùng cả cặp, lỗi 23505.
```

Không nên nhầm một khóa tổng hợp với hai ràng buộc `UNIQUE` riêng lẻ: `UNIQUE(student_id, course_id)` cho phép một `student_id` xuất hiện với nhiều `course_id`; `UNIQUE(student_id)` riêng thì không.

## 4. Lỗi `UNIQUE`: trùng email hoặc khóa nghiệp vụ

Khác với mã nhân viên, `email` là khóa nghiệp vụ được yêu cầu duy nhất:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (3, 'an@example.test', 10, 1700.00);
```

ID 3 chưa tồn tại, nhưng email đã được dùng bởi nhân viên 1. Câu lệnh vẫn thất bại với **`SQLSTATE 23505`**, lần này lỗi liên quan đến `UNIQUE(email)`.

### 4.1. Một lỗi có thể thuộc nhiều ràng buộc khác nhau

Mã `23505` không cho biết **cột nào** bị trùng. Ứng dụng nên dựa vào thông tin chẩn đoán có cấu trúc như **tên ràng buộc** (nếu driver cung cấp), thay vì tìm cụm chữ tiếng Anh trong message để quyết định thông báo.

Ví dụ:

- Trùng `employee_id`: “Mã nhân viên đã tồn tại.”
- Trùng `email`: “Email này đã được đăng ký.”

Trong ứng dụng thật, không nên trả ra tùy tiện toàn bộ thông điệp database, giá trị nội bộ hoặc chi tiết định danh nhạy cảm cho người dùng cuối.

### 4.2. `UNIQUE` và `NULL`

Theo cách mặc định thường gặp trong PostgreSQL, một ràng buộc `UNIQUE` có thể cho phép **nhiều giá trị `NULL`**, vì chúng không được coi là trùng nhau theo quy tắc mặc định của ràng buộc. Trong bảng bài học, `email TEXT NOT NULL UNIQUE` đã **không cho `NULL`**, nên không có kẽ hở này.

Các phiên bản PostgreSQL hỗ trợ thêm lựa chọn `NULLS NOT DISTINCT` khi cần xem những giá trị `NULL` là không phân biệt trong ràng buộc duy nhất. Cách hỗ trợ và cú pháp có thể khác giữa các hệ quản trị. Khi một cột vừa bắt buộc vừa duy nhất, cách dễ hiểu nhất vẫn là **`NOT NULL` kết hợp `UNIQUE`**.

### 4.3. Chuẩn hóa khóa trước khi coi là duy nhất

`an@example.test` và `AN@example.test` có thể được so là khác hoặc tương đương tùy kiểu dữ liệu, collation và chính sách của hệ thống. Không nên tự giả định `UNIQUE(email)` luôn không phân biệt chữ hoa/thường.

Nếu quy tắc nghiệp vụ coi email đã chuẩn hóa là cùng một giá trị, hãy thiết kế rõ **hàm chuẩn hóa**, chỉ mục hoặc ràng buộc phù hợp, cùng quy trình hiển thị giữ nguyên/chuẩn hóa. Điều này không làm thay đổi nguyên tắc nguyên tử: khi ràng buộc duy nhất bị vi phạm thì câu lệnh có thể thất bại.

## 5. Lỗi `NOT NULL`: thiếu giá trị bắt buộc

Ví dụ cố tình đưa email `NULL`:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (4, NULL, 10, 1300.00);
```

PostgreSQL từ chối vì `email` khai báo `NOT NULL`:

```text
SQLSTATE: 23502  -- not_null_violation
```

### 5.1. Bỏ cột và truyền `NULL` là hai việc khác nhau

Với cột:

```sql
employment_status TEXT NOT NULL DEFAULT 'ACTIVE'
```

hai cách sau **không tương đương**:

```sql
-- Không cung cấp cột: hệ quản trị dùng DEFAULT 'ACTIVE'.
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (5, 'hoa@example.test', 10, 1400.00);
```

```sql
-- Truyền NULL tường minh: vi phạm NOT NULL.
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary, employment_status)
VALUES
    (6, 'giang@example.test', 10, 1400.00, NULL);
```

Nếu muốn sử dụng mặc định ngay trong danh sách `VALUES`, PostgreSQL cho phép:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary, employment_status)
VALUES
    (7, 'huy@example.test', 10, 1400.00, DEFAULT);
```

**Lưu ý chạy thử:** câu lệnh chèn nhân viên 5 và 7 là ví dụ **thành công**, sẽ thêm dữ liệu vào bảng tạm nếu bạn chạy. Chúng được dùng để minh họa `DEFAULT`, không phải một phần của trạng thái gốc chỉ có nhân viên 1 và 2.

### 5.2. `DEFAULT` cũng có thể không hợp lệ

`DEFAULT` không phải quyền bỏ qua ràng buộc. Nếu một `DEFAULT` được tính ra giá trị vi phạm `CHECK`, `FOREIGN KEY` hoặc quy tắc khác, lệnh chèn vẫn có thể thất bại. Giá trị cuối cùng của dòng sau các quy tắc áp dụng phải đáp ứng ràng buộc.

## 6. Lỗi `CHECK`: dữ liệu không đáp ứng biểu thức

Schema có:

```sql
CONSTRAINT ck_lab_employee_salary CHECK (salary >= 0)
```

Ví dụ:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (8, 'khanh@example.test', 10, -5.00);
```

Lương âm nên `salary >= 0` là `FALSE` và PostgreSQL báo:

```text
SQLSTATE: 23514  -- check_violation
```

Ràng buộc trạng thái cũng có thể thất bại:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary, employment_status)
VALUES
    (9, 'lan@example.test', 20, 2000.00, 'UNKNOWN');
-- 'UNKNOWN' không thuộc ('ACTIVE', 'PAUSED'), lỗi CHECK.
```

### 6.1. Bẫy `CHECK` với `NULL`

Trong PostgreSQL, `CHECK` bác bỏ một dòng khi điều kiện được đánh giá là **`FALSE`**. Nếu biểu thức trả **`TRUE`** hoặc **`UNKNOWN`**, riêng ràng buộc `CHECK` không bác bỏ dòng đó.

```sql
CREATE TEMP TABLE constraint_lab_check_demo (
    amount NUMERIC CHECK (amount > 0)
);

INSERT INTO constraint_lab_check_demo (amount)
VALUES (NULL);
-- Được chấp nhận bởi CHECK ở ví dụ này.
```

Vì phép `NULL > 0` trả `UNKNOWN`, `CHECK(amount > 0)` **không có nghĩa `amount` bắt buộc phải có**. Nếu nghiệp vụ cần cả hai yêu cầu:

```sql
amount NUMERIC NOT NULL CHECK (amount > 0)
```

`NOT NULL` xử lý giá trị thiếu, `CHECK` xử lý miền giá trị hợp lệ.

### 6.2. `CHECK` không phù hợp cho mọi quy tắc liên bảng

Quy tắc “phòng ban này phải tồn tại” cần **`FOREIGN KEY`**, không phải một biểu thức `CHECK` tra cứu tùy ý tới bảng khác. Trong PostgreSQL, `CHECK` không được thiết kế để tham chiếu dữ liệu ở các dòng/bảng khác nhằm duy trì bất biến có thể thay đổi theo thời gian. Chọn đúng loại ràng buộc giúp hệ quản trị kiểm tra trong điều kiện đồng thời.

## 7. Lỗi `FOREIGN KEY`: tham chiếu không tồn tại

`constraint_lab_employees.department_id` phải trỏ tới `constraint_lab_departments.department_id`.

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (10, 'minh@example.test', 999, 1500.00);
```

Không có phòng ban 999, nên PostgreSQL báo:

```text
SQLSTATE: 23503  -- foreign_key_violation
```

### 7.1. Khóa ngoại bảo vệ cả thao tác thêm và sửa/xóa liên quan

Trong câu lệnh `INSERT`, lỗi khóa ngoại thường xảy ra khi **phía con** dùng một khóa cha không tồn tại. Nhưng khóa ngoại cũng có thể ngăn việc **xóa hoặc đổi khóa của dòng cha** khi còn bản ghi con tham chiếu, tùy lựa chọn `ON DELETE` và `ON UPDATE`.

Ví dụ:

```sql
DELETE FROM constraint_lab_departments
WHERE department_id = 10;
```

Nếu có nhân viên tham chiếu phòng 10 và không có quy tắc cho phép cascading, việc xóa phòng này có thể bị từ chối. Đây là cùng nguyên tắc bảo vệ **toàn vẹn tham chiếu**, dù bài học tập trung vào thêm dữ liệu.

### 7.2. Không nên xử lý lỗi bằng cách tạo phòng ban “ma”

Nếu dữ liệu nguồn ghi `department_id = 999` không tồn tại, một cách xử lý nguy hiểm là tự chèn phòng 999 với tên “Unknown” mà không có quy trình nghiệp vụ. Nó làm câu `INSERT` vượt khóa ngoại nhưng có thể tạo dữ liệu sai.

Các cách hợp lý hơn:

- Xác minh lại mã phòng ban từ nguồn.
- Nạp **bảng danh mục cha hợp lệ** trước bảng nhân viên.
- Ghi dòng lỗi vào vùng cách ly để người phụ trách sửa.
- Nếu nghiệp vụ cho phép “chưa xác định phòng”, thiết kế schema cho trạng thái đó một cách có chủ đích (ví dụ khóa tham chiếu nullable, hoặc danh mục mã `UNASSIGNED` thực sự được quản lý).

### 7.3. Ràng buộc có thể được kiểm tra ở thời điểm nào?

Mặc định, trong PostgreSQL những ràng buộc thường dùng được kiểm tra **ngay theo quy tắc thời điểm kiểm tra của loại ràng buộc**. Một số loại như `FOREIGN KEY`, `UNIQUE`, `PRIMARY KEY`, `EXCLUDE` có thể được khai báo **`DEFERRABLE`** để trì hoãn kiểm tra theo thiết kế; `NOT NULL` và `CHECK` của PostgreSQL không sử dụng cơ chế trì hoãn đó như khóa ngoại.

Vì vậy, “một câu INSERT đã kết thúc không báo lỗi” chưa phải lúc nào cũng là bằng chứng mọi ràng buộc **bị trì hoãn tới COMMIT** sẽ thỏa. Mục 13 sẽ minh họa.

## 8. Tính nguyên tử của **một câu lệnh `INSERT` nhiều dòng**

Đây là phần trọng tâm của bài.

Giả sử bảng hiện có hai nhân viên 1 và 2 như dữ liệu gốc. Ta muốn thêm **hai nhân viên trong cùng một câu SQL**:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (11, 'oanh@example.test', 10, 1800.00),  -- Hợp lệ.
    (12, 'phuc@example.test', 20, -10.00);   -- Sai CHECK.
```

Nhân viên 11 hợp lệ, nhân viên 12 có lương âm. Khi câu lệnh này thất bại vì `CHECK`, PostgreSQL **không giữ riêng nhân viên 11**. Tất cả thay đổi dữ liệu của câu `INSERT` bị hoàn tác.

Kiểm tra sau khi chạy lệnh lỗi **ở chế độ autocommit thông thường**, khi không ở trong giao dịch đã bị đánh dấu lỗi:

```sql
SELECT employee_id, email
FROM constraint_lab_employees
WHERE employee_id IN (11, 12)
ORDER BY employee_id;
-- Không có dòng nào.
```

### 8.1. “Tất cả hoặc không có gì” là theo **một câu SQL**

```text
Một INSERT có 2 dòng đề xuất
          │
          ├── Dòng 11 → hợp lệ
          │
          └── Dòng 12 → CHECK thất bại
                        │
                        ▼
               Cả câu INSERT lỗi
                        │
                        ▼
             Không thêm dòng 11, 12
```

Câu lệnh không có chế độ mặc định “chèn các dòng hợp lệ trước, giữ chúng rồi báo lỗi các dòng còn lại”.

Điều này cũng áp dụng về nguyên tắc cho:

```sql
INSERT INTO target_table (...)
SELECT ...
FROM source_table;
```

Nếu một dòng nguồn đưa vào làm câu `INSERT ... SELECT` thất bại, **không chỉ dòng nguồn đó** bị từ chối; câu lệnh chèn đích không hoàn tất một phần.

### 8.2. Ràng buộc trùng bên trong chính một lệnh nhiều dòng

Không cần trùng với dữ liệu đã có: **hai dòng mới** cũng có thể xung đột:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (13, 'duplicate@example.test', 10, 1600),
    (14, 'duplicate@example.test', 20, 1700);
-- Vi phạm UNIQUE(email); cả INSERT thất bại.
```

Điều quan trọng là **trạng thái dữ liệu cuối câu lệnh** phải thỏa các ràng buộc áp dụng. Với trường hợp hai email trùng trong một `INSERT` thông thường, không có quy tắc “dòng đầu được ưu tiên giữ còn dòng sau bị bỏ qua”.

### 8.3. Không phải lỗi nào cũng là lỗi ràng buộc

Một câu `INSERT` cũng có thể thất bại do:

- Chuyển kiểu không hợp lệ, ví dụ ký tự không chuyển được sang số.
- Biểu thức tính toán lỗi, như phép chia cho 0.
- Hàm do ứng dụng tạo phát sinh ngoại lệ.
- Trigger phát sinh lỗi.
- Hệ thống báo lỗi trong quá trình thực thi.

Tính nguyên tử của câu lệnh PostgreSQL không chỉ giới hạn ở mã lỗi nhóm `23` của ràng buộc. Dù nguyên nhân lỗi khác nhau, khi câu lệnh bị hủy theo cơ chế giao dịch, các thay đổi dữ liệu giao dịch của câu lệnh không được giữ lại.

### 8.4. “Các dòng đã được xử lý” khác “các dòng đã được lưu”

Bộ thực thi có thể đã tính toán biểu thức, kiểm tra một số dòng hoặc gọi một số thành phần trước khi phát hiện lỗi. Điều đó **không có nghĩa** các dòng đó đã được **commit** và sẽ tồn tại sau câu lệnh thất bại.

Không nên suy luận từ thứ tự viết `VALUES` rằng một phần đầu của câu lệnh đã được lưu bền vững.

## 9. Tính nguyên tử của câu lệnh khác tính nguyên tử của **giao dịch**

Hãy phân biệt ba cấp:

| Cấp | Ví dụ | Ý nghĩa cần nhớ |
|---|---|---|
| **Một câu lệnh** | Một `INSERT ... VALUES (...), (...)` | Khi câu lệnh bị lỗi, không giữ nửa câu lệnh theo cách chèn thông thường |
| **Một giao dịch** | `BEGIN; INSERT ...; INSERT ...; COMMIT;` | Nhiều câu lệnh được quyết định commit/rollback như một đơn vị |
| **Một quy trình ứng dụng** | Đọc file, gọi API, chèn database, gửi email | Không tự nguyên tử chỉ vì có một câu SQL hoặc transaction |

### 9.1. Hai `INSERT` độc lập với autocommit

Giả sử SQL client đang bật **autocommit**, tức mỗi câu lệnh thành công được commit riêng khi không có transaction tường minh:

```sql
-- Câu 1: thành công và được commit riêng.
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (15, 'quynh@example.test', 10, 1900);

-- Câu 2: thất bại.
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (16, 'son@example.test', 20, -20);
```

Trong autocommit, **nhân viên 15 vẫn tồn tại** sau khi câu thứ hai lỗi. Tính nguyên tử của **câu 2** không tự rollback **câu 1** đã commit.

### 9.2. Hai câu lệnh nằm trong một transaction

Nếu cả hai bước phải cùng thành công hoặc cùng thất bại:

```sql
BEGIN;

INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (17, 'trang@example.test', 10, 1900);

INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (18, 'uyen@example.test', 20, -20);
-- Lỗi CHECK ở câu thứ hai.

ROLLBACK;
```

Sau `ROLLBACK`, **cả nhân viên 17 và 18 đều không tồn tại do giao dịch này**, dù câu chèn 17 đã thành công trước khi câu chèn 18 lỗi.

**Điểm riêng của PostgreSQL:** khi một câu lệnh gây lỗi trong transaction tường minh, transaction thường vào trạng thái **aborted**. Những câu SQL thông thường tiếp theo sẽ bị từ chối cho tới khi `ROLLBACK` hoặc phục hồi về `SAVEPOINT` hợp lệ. Đừng tiếp tục thử các `INSERT` mới trong transaction đã hỏng như thể lỗi tự biến mất.

### 9.3. Không nên chỉ viết `COMMIT` sau lỗi

Trong PostgreSQL, sau khi transaction bị aborted, cố tiếp tục hoặc gửi `COMMIT` **không làm hồi sinh phần đã lỗi**. Cần xử lý trạng thái giao dịch cho đúng; khi không có điểm lưu, hành động an toàn là **`ROLLBACK`**.

Nếu một ứng dụng cần lưu nhiều bước nghiệp vụ như một đơn vị (tạo đơn hàng và tạo các dòng chi tiết), hãy **mở transaction trước bước đầu**, chỉ `COMMIT` sau khi tất cả đều đạt, và `ROLLBACK` khi một bước bắt buộc thất bại.

## 10. Trạng thái transaction sau lỗi trong PostgreSQL

Ví dụ:

```sql
BEGIN;

INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (19, 'viet@example.test', 10, -1);
-- SQLSTATE 23514: check_violation.

SELECT COUNT(*) FROM constraint_lab_employees;
-- Trong transaction đã aborted, PostgreSQL báo lỗi dạng:
-- SQLSTATE 25P02: in_failed_sql_transaction.

ROLLBACK;

SELECT COUNT(*) FROM constraint_lab_employees;
-- Có thể truy vấn bình thường trở lại.
```

### 10.1. Vì sao câu `SELECT` cũng có thể thất bại?

Khi transaction đã gặp lỗi và rơi vào trạng thái aborted, PostgreSQL không tự động cho các câu tiếp theo chạy như không có gì xảy ra. Nó cần biết phạm vi phải hủy hoặc phục hồi.

Trong `psql`, dấu nhắc có thể thay đổi để báo trạng thái transaction lỗi. Trong driver, bạn sẽ nhận lỗi `25P02`. Lúc đó nên kiểm tra **lỗi đầu tiên** (`23514`, `23505`, `23503`...) là nguyên nhân gốc, không chỉ xử lý lỗi `25P02` phát sinh sau.

### 10.2. Autocommit không phải luôn bật ở mọi client

Nhiều SQL client mặc định autocommit mỗi câu lệnh, nhưng driver, framework và cấu hình ứng dụng có thể chủ động dùng transaction. Không được suy luận “câu trước chắc chắn đã commit” nếu không biết chính xác:

- Client có bật autocommit hay không.
- Có `BEGIN`/giao dịch được framework quản lý hay không.
- `COMMIT` đã chạy thành công hay chưa.
- Có ràng buộc trì hoãn kiểm tra tới commit hay không.

**Nên dùng giao dịch tường minh** cho thao tác nghiệp vụ gồm nhiều câu lệnh cần cùng thành công.

## 11. `SAVEPOINT`: phục hồi một phần mà không bỏ toàn bộ transaction

Không phải lỗi nào trong một transaction cũng buộc ứng dụng phải hủy **tất cả** các bước. PostgreSQL hỗ trợ `SAVEPOINT`, cho phép phục hồi về một mốc đã đánh dấu.

Giả sử yêu cầu:

- Thêm nhân viên 20.
- Thử thêm nhân viên 21, nhưng dữ liệu lương không hợp lệ.
- Bỏ qua **nỗ lực 21** sau khi ghi nhận lỗi, rồi thêm nhân viên 22.
- Cuối cùng commit các bước hợp lệ theo chính sách đã định.

```sql
BEGIN;

INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (20, 'worker20@example.test', 10, 2000);

SAVEPOINT before_employee_21;

INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (21, 'worker21@example.test', 20, -50);
-- Lỗi CHECK: transaction cần được phục hồi.

ROLLBACK TO SAVEPOINT before_employee_21;

INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (22, 'worker22@example.test', 20, 1700);

RELEASE SAVEPOINT before_employee_21;
COMMIT;
```

Sau khi `COMMIT` thành công:

- Nhân viên **20** có mặt.
- Nhân viên **22** có mặt.
- Nhân viên **21** không có mặt.

Ở đây `ROLLBACK TO SAVEPOINT` phục hồi **trạng thái transaction về thời điểm tạo điểm lưu**, không phải một dạng “hủy đúng dòng lỗi nhưng giữ các thay đổi khác trong cùng một câu `INSERT`”.

### 11.1. Một transaction vẫn chỉ có một lần commit cuối

`SAVEPOINT` không biến dữ liệu trước điểm lưu thành dữ liệu đã commit. Nếu sau đó transaction chính `ROLLBACK`, **cả nhân viên 20 và 22** cũng bị hoàn tác.

```text
BEGIN
  INSERT 20 thành công          ← chưa commit
  SAVEPOINT
    INSERT 21 lỗi
  ROLLBACK TO SAVEPOINT        ← hủy phần sau điểm lưu
  INSERT 22 thành công         ← chưa commit
COMMIT                         ← 20 và 22 mới được commit
```

### 11.2. Khi nào nên dùng `SAVEPOINT`?

Phù hợp nếu nghiệp vụ **chủ động cho phép xử lý từng mục** trong một đợt nhập, ví dụ:

- Ghi nhận các mục hợp lệ.
- Ghi nhận danh sách mục thất bại để người vận hành sửa.
- Không hủy tất cả những mục đã được duyệt trước đó.

Nhưng nếu yêu cầu là “mỗi batch phải đủ 100/100 bản ghi”, thì **không nên âm thầm dùng `SAVEPOINT` để bỏ qua 1 dòng**. Khi đó nên rollback cả transaction và báo lỗi toàn bộ batch.

### 11.3. Một ví dụ quan trọng: `SAVEPOINT` không cứu được nửa câu `INSERT`

```sql
BEGIN;
SAVEPOINT before_batch;

INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (23, 'worker23@example.test', 10, 2000),
    (24, 'worker24@example.test', 10, -1);
-- Cả INSERT lỗi.

ROLLBACK TO SAVEPOINT before_batch;
COMMIT;
```

Sau ví dụ này, **không có nhân viên 23 hay 24** do câu `INSERT` bị lỗi. `SAVEPOINT` giúp giữ transaction ở trạng thái có thể tiếp tục và phục hồi các thao tác sau mốc; nó **không biến câu lệnh nhiều dòng thành cơ chế bỏ từng dòng sai**.

## 12. `ON CONFLICT`: chủ động định nghĩa cách xử lý trùng

Đôi khi việc chèn trùng không phải một sự cố mà là tình huống **được dự kiến**. Chẳng hạn đồng bộ danh sách từ API có thể gửi lại cùng một email. PostgreSQL hỗ trợ `INSERT ... ON CONFLICT` để xử lý một số **xung đột duy nhất** theo quy tắc đã khai báo.

### 12.1. `ON CONFLICT (email) DO NOTHING`

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (30, 'chi@example.test',  10, 1800),
    (31, 'an@example.test',   10, 1600)
ON CONFLICT (email) DO NOTHING
RETURNING employee_id, email;
```

Với dữ liệu ban đầu:

- Email `chi@example.test` chưa tồn tại nên bản ghi 30 được chèn.
- Email `an@example.test` đã thuộc nhân viên 1 nên bản ghi đề xuất 31 được **bỏ qua**.
- `RETURNING` trả **chỉ dòng thực sự được chèn**, ở đây là nhân viên 30.

**Câu lệnh thành công có chủ đích với một dòng bị bỏ qua**, khác hoàn toàn câu `INSERT` nhiều dòng có **lỗi không được xử lý** làm thất bại toàn bộ câu.

### 12.2. “Bỏ qua xung đột” không phải “bỏ qua mọi lỗi”

`ON CONFLICT (email) DO NOTHING` xử lý **xung đột trên khóa duy nhất email được chỉ định**. Nó không cho phép:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (32, 'new32@example.test', 999, 1500)
ON CONFLICT (email) DO NOTHING;
-- Vẫn lỗi FOREIGN KEY: department_id 999 không tồn tại.
```

Tương tự, một dòng vi phạm `NOT NULL` hoặc `CHECK` vẫn có thể làm **cả câu lệnh thất bại**. Không được xem `ON CONFLICT` như tùy chọn “cứ có lỗi thì bỏ qua”.

**Lưu ý:** trong PostgreSQL, có thể viết `ON CONFLICT DO NOTHING` **không chỉ định cột** để xử lý những xung đột duy nhất phù hợp mà PostgreSQL có thể nhận diện. Nếu chỉ định `(email)`, xung đột **khác email** (ví dụ trùng `employee_id`) không mặc nhiên được xử lý. Luôn biết chính xác **đối tượng xung đột** của câu lệnh.

### 12.3. Vì sao `DO NOTHING` có thể nguy hiểm?

Nếu một file 1000 dòng chỉ chèn thành công 930 dòng vì 70 email đã tồn tại, `INSERT` có thể hoàn thành bình thường. Nếu hệ thống chỉ kiểm tra “lệnh không báo lỗi” rồi ghi “đã nhập 1000 nhân viên”, báo cáo sẽ sai.

Nếu dùng `DO NOTHING`, cần xác định:

- **Bao nhiêu dòng nguồn** được gửi?
- **Bao nhiêu dòng thực sự được chèn**?
- **Bao nhiêu dòng bỏ qua**, và tại sao?
- Bỏ qua là **được phép** hay phải báo người nhập liệu?

`RETURNING` hoặc số dòng ảnh hưởng do driver báo có thể giúp đếm các dòng đã chèn; để giải thích lý do bỏ qua, cần dữ liệu truy vết và quy tắc đối chiếu phù hợp.

## 13. `ON CONFLICT DO UPDATE`: upsert

*Upsert* là ý tưởng “thêm nếu chưa có; cập nhật nếu đã có xung đột trên khóa được chọn”.

Ví dụ: email là định danh nghiệp vụ; khi dữ liệu mới có cùng email, ta **cập nhật lương và phòng ban**, giữ ID nhân viên hiện có.

```sql
INSERT INTO constraint_lab_employees AS dest
    (employee_id, email, department_id, salary)
VALUES
    (33, 'an@example.test', 10, 1750)
ON CONFLICT (email)
DO UPDATE SET
    department_id = EXCLUDED.department_id,
    salary = EXCLUDED.salary
RETURNING
    dest.employee_id,
    dest.email,
    dest.department_id,
    dest.salary;
```

Trong PostgreSQL, `EXCLUDED` biểu diễn **giá trị của dòng đã được đề xuất chèn** trong nhánh xử lý xung đột. Ở ví dụ này email `an@example.test` đã tồn tại, nên:

- Dòng nhân viên 1 được **cập nhật** lương thành `1750`.
- ID 33 của dòng đề xuất **không trở thành ID mới**; chúng ta không cập nhật `employee_id`.
- `RETURNING` trả dòng đã bị cập nhật, có `employee_id = 1`.

### 13.1. `ON CONFLICT` vẫn phải giữ toàn vẹn dữ liệu

Nếu đặt `EXCLUDED.department_id = 999`, nhánh `DO UPDATE` có thể vi phạm **khóa ngoại** và câu lệnh vẫn **thất bại**. `ON CONFLICT` chỉ định cách xử lý xung đột duy nhất; nó không tạm vô hiệu hóa các ràng buộc khác.

### 13.2. Chỉ cập nhật khi dữ liệu thật sự thay đổi

```sql
INSERT INTO constraint_lab_employees AS dest
    (employee_id, email, department_id, salary)
VALUES
    (34, 'an@example.test', 10, 1750)
ON CONFLICT (email)
DO UPDATE SET
    salary = EXCLUDED.salary
WHERE dest.salary IS DISTINCT FROM EXCLUDED.salary
RETURNING dest.employee_id, dest.email, dest.salary;
```

Trong PostgreSQL, `IS DISTINCT FROM` là phép so sánh coi `NULL` là một trường hợp rõ ràng, giúp phát hiện giá trị có khác hay không. Nếu lương hiện tại của An đã là `1750`, điều kiện `WHERE` trong nhánh `DO UPDATE` là sai nên PostgreSQL không thực hiện cập nhật đó; `RETURNING` có thể **không trả dòng nào** trong trường hợp này.

### 13.3. Trùng trong chính danh sách nguồn `DO UPDATE`

PostgreSQL không cho một câu lệnh `ON CONFLICT DO UPDATE` **ảnh hưởng cùng một dòng đích nhiều hơn một lần**. Ví dụ:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (35, 'same@example.test', 10, 1500),
    (36, 'same@example.test', 10, 1600)
ON CONFLICT (email)
DO UPDATE SET salary = EXCLUDED.salary;
```

Có thể gặp lỗi **cardinality violation** (`SQLSTATE 21000`) vì hai dòng đề xuất cùng đụng một khóa email trong một lệnh `DO UPDATE`; PostgreSQL không chọn ngẫu nhiên dòng nào “thắng”. Khi dùng batch upsert, hãy **phát hiện và xử lý khóa trùng trong nguồn trước** theo một chính sách xác định.

### 13.4. Giới hạn của `ON CONFLICT`

- Mục tiêu `DO UPDATE` phải xác định được **khóa/index xung đột phù hợp**; không phải mọi loại ràng buộc đều là mục tiêu upsert.
- Ràng buộc duy nhất được khai báo **`DEFERRABLE`** không thể dùng làm *arbiter* cho `ON CONFLICT` theo cơ chế PostgreSQL.
- `ON CONFLICT` không thay thế `FOREIGN KEY`, `CHECK`, `NOT NULL` hoặc quy trình xác minh dữ liệu.
- Câu lệnh upsert cũng chịu tính nguyên tử: nếu một lỗi không xử lý được khiến câu lệnh thất bại, các thay đổi của câu lệnh không được giữ nửa vời.

## 14. Ràng buộc trì hoãn kiểm tra (*deferrable constraints*)

Một tinh tế quan trọng: tính nguyên tử của câu lệnh không có nghĩa tất cả ràng buộc **bắt buộc phải được kiểm tra xong trước khi câu lệnh kết thúc**. PostgreSQL cho phép một số ràng buộc được khai báo trì hoãn.

### 14.1. Ví dụ khóa ngoại `DEFERRABLE INITIALLY DEFERRED`

```sql
CREATE TEMP TABLE constraint_lab_parent (
    parent_id INTEGER PRIMARY KEY
);

CREATE TEMP TABLE constraint_lab_child (
    child_id INTEGER PRIMARY KEY,
    parent_id INTEGER NOT NULL,
    CONSTRAINT fk_lab_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES constraint_lab_parent(parent_id)
        DEFERRABLE INITIALLY DEFERRED
);
```

Với `INITIALLY DEFERRED`, kiểm tra ràng buộc khóa ngoại được trì hoãn theo mặc định tới **cuối giao dịch**, trừ khi được chuyển về chế độ kiểm tra sớm.

```sql
BEGIN;

INSERT INTO constraint_lab_child (child_id, parent_id)
VALUES (1, 10);
-- Tạm thời parent_id=10 chưa có ở bảng cha.

INSERT INTO constraint_lab_parent (parent_id)
VALUES (10);
-- Sửa trạng thái tham chiếu trước lúc commit.

COMMIT;
-- Thành công vì tới lúc kiểm tra cuối giao dịch, parent 10 đã tồn tại.
```

### 14.2. Khi câu `INSERT` thành công nhưng `COMMIT` thất bại

Nếu làm:

```sql
BEGIN;

INSERT INTO constraint_lab_child (child_id, parent_id)
VALUES (2, 999);
-- Bước INSERT có thể thành công tạm thời do FK deferred.

COMMIT;
-- Lỗi FOREIGN KEY vì tới cuối giao dịch vẫn không có parent 999.
```

Transaction này không được commit; những thay đổi dữ liệu giao dịch trong đó bị rollback khi lỗi tại commit. Ví dụ cho thấy **trạng thái thành công của một câu `INSERT` không đồng nghĩa dữ liệu đã được commit bền vững**.

### 14.3. Dùng `SET CONSTRAINTS` để kiểm tra sớm

Trong một transaction có ràng buộc phù hợp, PostgreSQL cho phép yêu cầu kiểm tra ngay:

```sql
BEGIN;

INSERT INTO constraint_lab_child (child_id, parent_id)
VALUES (3, 999);

SET CONSTRAINTS fk_lab_child_parent IMMEDIATE;
-- Việc chuyển sang IMMEDIATE sẽ kiểm tra các vi phạm đang được trì hoãn
-- và có thể báo lỗi ở đây.

ROLLBACK;
```

Nếu câu `SET CONSTRAINTS` báo lỗi, hãy rollback phù hợp; trong PostgreSQL transaction có thể chuyển sang trạng thái lỗi. Không cố `COMMIT` một giao dịch còn vi phạm.

### 14.4. Trì hoãn ràng buộc không phải cơ chế bỏ qua ràng buộc

Mục tiêu của `DEFERRABLE` là cho phép **thứ tự cập nhật tạm thời** chưa thỏa một số ràng buộc, miễn là **trạng thái cần kiểm tra cuối cùng** thỏa. Nó không “tắt” tính toàn vẹn; chỉ thay đổi **thời điểm đánh giá**.

Trong PostgreSQL, không được tự giả định mọi `CHECK` hoặc `NOT NULL` đều có thể đặt `DEFERRABLE`, và không dùng ràng buộc duy nhất deferred làm trọng tài cho `ON CONFLICT`.

## 15. Một lưu ý quan trọng: rollback không hoàn tác mọi tác động

Khi nói “một câu `INSERT` lỗi được rollback”, ta nói về **các thay đổi dữ liệu mang tính giao dịch của database**. Một số tác động có quy tắc khác.

### 15.1. Giá trị sequence có thể bị tiêu thụ dù transaction bị rollback

Với PostgreSQL, `SERIAL` hoặc cột `GENERATED ... AS IDENTITY` thường dựa trên **sequence** để cấp số. Các lệnh như `nextval()` **không bị rollback theo cách trả lại số đã dùng**.

Ví dụ độc lập:

```sql
CREATE TEMP TABLE constraint_lab_identity_demo (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL UNIQUE
);

INSERT INTO constraint_lab_identity_demo (label)
VALUES ('first');

BEGIN;
INSERT INTO constraint_lab_identity_demo (label)
VALUES ('will_rollback');
ROLLBACK;

INSERT INTO constraint_lab_identity_demo (label)
VALUES ('after_rollback');

SELECT id, label
FROM constraint_lab_identity_demo
ORDER BY id;
```

ID của `after_rollback` **có thể bỏ qua** một giá trị mà lệnh trong giao dịch đã lấy. Điều đó **không có nghĩa** bản ghi `will_rollback` đã được lưu; nó chỉ phản ánh sequence không được thiết kế như dãy số không có khoảng trống.

**Không xây dựng quy tắc nghiệp vụ dựa trên giả định ID auto-increment luôn liên tục.**

### 15.2. Tác động bên ngoài database không tự rollback

Giả sử một trigger hoặc ứng dụng gọi dịch vụ ngoài để gửi email **trước khi transaction commit**. Nếu sau đó transaction rollback, email đã gửi sẽ không tự thu hồi.

Trong PostgreSQL, các **thay đổi bảng bình thường do trigger thực hiện trong cùng transaction** sẽ rollback cùng transaction. Nhưng tác động ngoài transaction như HTTP request, email, ghi file hoặc hệ thống bên ngoài cần thiết kế riêng.

Một phương pháp phổ biến là ghi **sự kiện cần phát** vào bảng outbox **trong cùng transaction**, rồi có một tiến trình độc lập gửi sau khi bản ghi đã commit. Phương pháp này còn cần cơ chế chống gửi lặp/idempotency và xử lý retry; không phải bản thân transaction SQL tự cung cấp giao dịch phân tán với dịch vụ ngoài.

### 15.3. `RETURNING` không phải bằng chứng commit

```sql
BEGIN;

INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (40, 'temp40@example.test', 10, 1800)
RETURNING employee_id, email;

ROLLBACK;
```

`RETURNING` có thể trả `employee_id = 40` trong transaction, nhưng sau `ROLLBACK` bản ghi **không tồn tại**. `RETURNING` cho biết **câu lệnh đã tạo/ảnh hưởng dòng nào tại thời điểm thực thi**, không xác nhận rằng transaction cuối cùng được commit.

## 16. `INSERT ... SELECT` cũng phải tôn trọng ràng buộc và nguyên tử

Trong nhập liệu hàng loạt, ta thường chèn dữ liệu từ một bảng nguồn:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
SELECT
    source_employee_id,
    source_email,
    source_department_id,
    source_salary
FROM another_source_table;
```

Nếu bất kỳ dòng được đề xuất chèn nào gây lỗi ràng buộc chưa được xử lý, cả câu `INSERT ... SELECT` bị từ chối theo cơ chế nguyên tử của PostgreSQL.

### 16.1. Ví dụ `INSERT ... SELECT` từ tập `VALUES`

```sql
WITH incoming(employee_id, email, department_id, salary) AS (
    VALUES
        (41, 'new41@example.test', 10, 1600::numeric),
        (42, 'new42@example.test', 999, 1700::numeric)
)
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
SELECT employee_id, email, department_id, salary
FROM incoming;
-- Lỗi FOREIGN KEY vì department_id=999.
-- Cả dòng hợp lệ 41 cũng không được lưu bởi câu INSERT này.
```

### 16.2. Bộ lọc `WHERE` có thể chọn bỏ dòng nguồn

```sql
WITH incoming(employee_id, email, department_id, salary) AS (
    VALUES
        (43, 'new43@example.test', 10, 1600::numeric),
        (44, 'new44@example.test', 999, 1700::numeric)
)
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
SELECT i.employee_id, i.email, i.department_id, i.salary
FROM incoming AS i
JOIN constraint_lab_departments AS d
    ON d.department_id = i.department_id;
```

Câu trên sẽ chỉ đề xuất chèn những dòng có phòng ban khớp (trong dữ liệu mẫu là dòng 43). Nó **không phải** tính năng “bỏ qua lỗi ràng buộc”, mà là **bộ lọc của truy vấn nguồn**.

Hãy cảnh giác: nếu yêu cầu nhập đủ 2/2 dòng, việc một dòng **bị lọc im lặng** là lỗi nghiệp vụ dù câu `INSERT` thành công. Khi dùng lọc để tiếp nhận một phần, hệ thống phải có báo cáo dòng bị loại và lý do.

### 16.3. Kiểu dữ liệu nguồn cũng là một phần của tính hợp lệ

Nếu dữ liệu CSV chứa `salary = 'abc'`, việc ép kiểu sang `NUMERIC` có thể lỗi **trước cả khi kiểm tra `CHECK(salary >= 0)`**. Không nên coi mọi lỗi nạp dữ liệu đều là `23514`. Trong quy trình nhập thực, tầng staging thường lưu dữ liệu thô và có bước chuyển kiểu/đánh giá hợp lệ với đường xử lý rõ ràng.

## 17. Nhận diện lỗi bằng SQLSTATE

Trong PostgreSQL, mỗi lỗi có **mã SQLSTATE gồm năm ký tự**, phù hợp hơn việc dựa vào thông điệp văn bản có thể thay đổi theo cấu hình, phiên bản hoặc ngôn ngữ.

| SQLSTATE | Tên lỗi PostgreSQL | Tình huống điển hình |
|---|---|---|
| `23505` | `unique_violation` | Trùng khóa chính hoặc `UNIQUE` |
| `23502` | `not_null_violation` | Cột bắt buộc nhận `NULL` |
| `23503` | `foreign_key_violation` | Mã tham chiếu không tồn tại hoặc thao tác làm hỏng tham chiếu |
| `23514` | `check_violation` | Vi phạm biểu thức `CHECK` |
| `23***` | Lớp *integrity constraint violation* | Nhóm lỗi toàn vẹn dữ liệu |
| `25P02` | `in_failed_sql_transaction` | Cố chạy tiếp khi transaction đang lỗi |
| `21000` | `cardinality_violation` | Ví dụ `ON CONFLICT DO UPDATE` tác động cùng dòng đích nhiều lần |
| `40001` | `serialization_failure` | Xung đột đồng thời ở mức isolation đòi retry giao dịch |

`23***` là ký hiệu **mẫu lớp mã bắt đầu bằng `23`**, không phải một mã SQLSTATE cụ thể để so sánh nguyên văn trong chương trình.

### 17.1. Bảng quyết định xử lý theo lỗi

| Lỗi | Hướng xử lý thường phù hợp |
|---|---|
| Trùng khóa chính | Kiểm tra đây là yêu cầu chèn mới, retry trùng hay sai khóa; cân nhắc idempotency/upsert theo đặc tả |
| Trùng email | Yêu cầu người dùng chọn email khác hoặc hợp nhất/cập nhật theo chính sách |
| Thiếu cột bắt buộc | Sửa đầu vào hoặc dùng `DEFAULT` được phép |
| Sai `CHECK` | Sửa giá trị; không tự bỏ quy tắc hợp lệ |
| Sai khóa ngoại | Sửa mã, tạo bản ghi cha hợp lệ trước, hoặc cách ly dòng lỗi |
| Transaction `25P02` | Xác định lỗi gốc; `ROLLBACK` hoặc phục hồi về savepoint |
| Serialization failure | Retry **toàn bộ transaction** theo chính sách backoff/idempotency thích hợp |

Với lỗi ràng buộc, **chạy lại nguyên câu lệnh mà không đổi dữ liệu hoặc chính sách xử lý thường chỉ lặp lại cùng lỗi**. Khác với lỗi transient do đồng thời, `CHECK` sai hoặc FK không tồn tại cần điều chỉnh dữ liệu/luồng nhập.

### 17.2. Không để lỗi SQL rò rỉ chi tiết nhạy cảm

Thông báo lỗi cho người vận hành có thể cần:

```text
Batch B-104: dòng nguồn 18 thất bại
Loại lỗi: FOREIGN_KEY
Trường: department_id
Giá trị gửi: 999
Hành động: kiểm tra danh mục phòng ban
```

Nhưng màn hình công khai không nên hiển thị bừa bãi thông tin nội bộ, SQL thô, schema hoặc giá trị nhạy cảm. Có thể lưu mã kỹ thuật, correlation ID và thông tin phù hợp quyền truy cập để hỗ trợ truy vết.

## 18. Quy trình nhập liệu hàng loạt: chấp nhận toàn bộ hay chấp nhận một phần?

Hai chính sách rất khác nhau:

### 18.1. **All-or-nothing**: cả lô phải hợp lệ

Ví dụ một lần nhập là **bảng kê tài chính phải đủ 100 dòng**. Nếu một dòng sai:

- Từ chối/rollback toàn bộ lô.
- Trả danh sách lỗi có thể sửa.
- Không công bố “nhập thành công” nếu thiếu dòng.

Mẫu:

```sql
BEGIN;

-- Bước 1: ghi thông tin lô (nếu cần).
-- Bước 2: INSERT toàn bộ các dòng đã chuẩn bị.
-- Bước 3: cập nhật trạng thái lô sang COMPLETE.

COMMIT;
```

Ứng dụng phải thực hiện `ROLLBACK` nếu bất kỳ bước bắt buộc nào lỗi. `BEGIN`/`COMMIT` bảo vệ **nhiều câu lệnh**; nếu dùng đúng một `INSERT` nhiều dòng, bản thân câu đó đã mang tính nguyên tử về các thay đổi dữ liệu của nó.

### 18.2. **Partial acceptance**: nhập các dòng hợp lệ, cách ly dòng lỗi

Trong danh sách liên hệ gửi từ nhiều nguồn, chính sách có thể cho phép:

- Lưu các dòng hợp lệ.
- Ghi các dòng sai vào bảng lỗi kèm lý do.
- Báo chính xác bao nhiêu dòng thành công, bao nhiêu dòng cần sửa.

Khi đó có thể sử dụng:

- **Staging table** nhận dữ liệu thô.
- Quy tắc kiểm tra kiểu/ràng buộc nghiệp vụ trước khi ghi bảng chính.
- Tách bản ghi được chấp nhận và từ chối một cách rõ ràng.
- `SAVEPOINT` hoặc các câu lệnh riêng nếu cần xử lý theo từng mục.
- `ON CONFLICT` cho các tình huống trùng **được phép**.

**Không nên gọi một lô partial thành công hoàn toàn.** Báo cáo ít nhất:

```text
source_count = 1000
inserted_count = 920
updated_count = 30
skipped_duplicate_count = 20
rejected_invalid_count = 30
```

Số lượng trong ví dụ chỉ để minh họa cách báo cáo, không phải kết quả từ script thực hành.

### 18.3. Chính sách phải nhất quán với giao dịch

Nếu yêu cầu all-or-nothing nhưng hệ thống tự lặp:

```text
FOR mỗi dòng:
    try INSERT dòng
    nếu lỗi: log rồi tiếp tục
```

với autocommit, kết quả rất có thể là **một phần dòng đã lưu**. Tính nguyên tử của **từng `INSERT`** không biến cả vòng lặp thành một giao dịch duy nhất.

Nếu partial acceptance là yêu cầu có chủ đích, từng dòng hoặc từng nhóm cần được chấp nhận/loại theo một chính sách minh bạch, không phải “SQL tự chọn những dòng chèn được”.

## 19. Mẫu staging để phát hiện dòng không hợp lệ

Một bảng staging có thể giữ **số thứ tự dòng nguồn** và các giá trị cần kiểm tra trước khi chuyển vào bảng chính.

```sql
CREATE TEMP TABLE constraint_lab_stage (
    source_row INTEGER PRIMARY KEY,
    employee_id INTEGER,
    email TEXT,
    department_id INTEGER,
    salary NUMERIC(12, 2)
);

INSERT INTO constraint_lab_stage
    (source_row, employee_id, email, department_id, salary)
VALUES
    (1, 50, 'valid50@example.test', 10, 1600),
    (2, 51, 'wrong51@example.test', 999, 1700),
    (3, 52, 'valid50@example.test', 20, 1800),
    (4, 53, NULL, 10, 1500),
    (5, 54, 'an@example.test', 10, 1450),
    (6, 55, 'negative55@example.test', 20, -15);
```

Staging cố ý **không áp đủ các ràng buộc của bảng đích** để còn có thể ghi nhận dòng chưa hợp lệ. Tuy vậy, vì `salary` đã khai báo `NUMERIC`, nguồn có văn bản không chuyển được sang số sẽ lỗi ngay ở staging; với CSV thật chứa dữ liệu thô, thường cần thêm cột `TEXT` và quy trình parse an toàn.

### 19.1. Tách lỗi theo nguồn

Ta có thể chẩn đoán một số lỗi thường gặp:

```sql
WITH ranked AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY s.email
            ORDER BY s.source_row
        ) AS email_occurrence
    FROM constraint_lab_stage AS s
),
classified AS (
    SELECT
        r.*,
        CASE
            WHEN r.employee_id IS NULL THEN 'MISSING_EMPLOYEE_ID'
            WHEN r.email IS NULL THEN 'MISSING_EMAIL'
            WHEN r.department_id IS NULL THEN 'MISSING_DEPARTMENT'
            WHEN r.salary IS NULL THEN 'MISSING_SALARY'
            WHEN r.salary < 0 THEN 'NEGATIVE_SALARY'
            WHEN NOT EXISTS (
                SELECT 1
                FROM constraint_lab_departments AS d
                WHERE d.department_id = r.department_id
            ) THEN 'UNKNOWN_DEPARTMENT'
            WHEN r.email_occurrence > 1 THEN 'DUPLICATE_EMAIL_IN_STAGE'
            WHEN EXISTS (
                SELECT 1
                FROM constraint_lab_employees AS e
                WHERE e.employee_id = r.employee_id
            ) THEN 'EMPLOYEE_ID_ALREADY_EXISTS'
            WHEN EXISTS (
                SELECT 1
                FROM constraint_lab_employees AS e
                WHERE e.email = r.email
            ) THEN 'EMAIL_ALREADY_EXISTS'
            ELSE NULL
        END AS issue
    FROM ranked AS r
)
SELECT
    source_row, employee_id, email, department_id, salary, issue
FROM classified
ORDER BY source_row;
```

Theo thứ tự `CASE`, dòng 1 hợp lệ; dòng 2 sai phòng ban; dòng 3 trùng email trong staging; dòng 4 thiếu email; dòng 5 trùng email đang có; dòng 6 lương âm. Cột `issue` minh họa **một lý do ưu tiên**; trong thực tế một dòng có thể có nhiều lỗi và cần bảng/chương trình chẩn đoán đầy đủ hơn.

### 19.2. Không coi kiểm tra staging là thay thế ràng buộc

Tại thời điểm truy vấn `classified`, dữ liệu đích có thể chưa có một email. Nhưng **một giao dịch khác có thể chèn email đó** trước khi ta chuyển dữ liệu từ staging vào bảng chính. Đây là lỗi kiểm tra–rồi–hành động (*time-of-check to time-of-use*, TOCTOU).

Do đó, ngay cả khi đã kiểm tra staging:

- Bảng chính vẫn phải có `PRIMARY KEY`, `UNIQUE`, `CHECK`, `FOREIGN KEY`.
- Luồng ghi phải xử lý tình huống xung đột đến muộn.
- Nếu nghiệp vụ cho phép bỏ trùng, dùng `ON CONFLICT` đúng khóa và ghi nhận số dòng.
- Nếu bắt buộc nhập nguyên vẹn, hãy để lỗi khiến transaction rollback, không vô hiệu hóa ràng buộc để “đi cho xong”.

### 19.3. `ROW_NUMBER()` để giải quyết khóa trùng trong staging

Ví dụ hai dòng cùng email trong nguồn, nhưng nghiệp vụ chỉ chấp nhận **dòng xuất hiện đầu tiên** theo `source_row`:

```sql
WITH numbered AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (
            PARTITION BY email
            ORDER BY source_row
        ) AS rn
    FROM constraint_lab_stage AS s
)
SELECT
    source_row, employee_id, email, department_id, salary
FROM numbered
WHERE rn = 1
  AND email IS NOT NULL
ORDER BY source_row;
```

Đây mới chỉ là bước **chọn đại diện** theo một chính sách minh họa, **chưa phải lệnh chèn đã kiểm tra mọi ràng buộc**. Nếu nghiệp vụ muốn **dòng mới nhất**, **dòng có timestamp cập nhật muộn nhất** hoặc **từ chối cả nhóm trùng**, phải đổi quy tắc. Đừng mặc định “dòng đầu trong file là đúng”.

## 20. Đếm dòng được chèn thực sự với `RETURNING`

PostgreSQL có `RETURNING` để lấy thông tin về các dòng **thực sự được chèn hoặc cập nhật bởi câu lệnh**.

Ví dụ trong phiên chỉ có dữ liệu gốc và chưa chạy các lệnh thành công khác:

```sql
WITH inserted AS (
    INSERT INTO constraint_lab_employees
        (employee_id, email, department_id, salary)
    VALUES
        (60, 'valid60@example.test', 10, 1600),
        (61, 'an@example.test', 10, 1800)
    ON CONFLICT (email) DO NOTHING
    RETURNING employee_id, email
)
SELECT COUNT(*) AS inserted_count
FROM inserted;
-- inserted_count = 1.
```

Đây là cú pháp CTE chứa câu `INSERT ... RETURNING` của PostgreSQL. Nếu muốn biết **mã nào được chèn**, thay `SELECT COUNT(*)` bằng:

```sql
-- Đặt trong cùng câu WITH inserted AS (...):
SELECT employee_id, email
FROM inserted
ORDER BY employee_id;
```

Đừng suy luận rằng `RETURNING` là danh sách **mọi dòng nguồn** đã gửi. Với `DO NOTHING`, những dòng bị bỏ qua **không nằm trong kết quả RETURNING**. Với `DO UPDATE`, dòng cập nhật có thể được trả về nhưng cần phân biệt **insert/update** bằng cách được thiết kế rõ trong luồng nghiệp vụ; không tự dựa vào email để đoán loại thao tác.

### 20.1. Khi một câu lệnh không xử lý được lỗi thì sao?

Nếu một dòng khác trong cùng câu vi phạm `CHECK` hoặc `FOREIGN KEY`, `ON CONFLICT (email) DO NOTHING` không cứu được, và **không có tập dòng đã chèn thành công để commit riêng** từ câu lệnh thất bại. Ứng dụng phải nhận lỗi và giải quyết toàn bộ trạng thái transaction.

### 20.2. Đếm dòng nguồn và dòng đích riêng biệt

Trong quy trình nhập thật, nên ghi:

```text
source_rows
accepted_rows
inserted_rows
updated_rows
ignored_duplicate_rows
rejected_rows
```

Tổng các chỉ số cần khớp quy tắc phân loại đã định. Không chỉ đếm số dòng trong bảng đích sau nhập vì bảng đã có dữ liệu từ trước hoặc các giao dịch khác có thể ghi đồng thời.

## 21. Idempotency: retry không được tạo thêm dữ liệu sai

Trong hệ thống phân tán, ứng dụng có thể đã gửi `INSERT`, nhưng kết nối bị ngắt trước khi nhận được phản hồi. Khi đó, ứng dụng **không chắc** câu lệnh đã commit hay chưa.

Nếu retry mù quáng với một khóa mới, có thể tạo **hai bản ghi nghiệp vụ giống nhau**. Đây là vấn đề **idempotency**: thực hiện lại cùng một yêu cầu không được tạo thêm tác động ngoài ý muốn.

### 21.1. Dùng khóa yêu cầu duy nhất

Ví dụ bảng thanh toán có `payment_request_id` là mã duy nhất theo yêu cầu của client:

```sql
CREATE TEMP TABLE constraint_lab_payments (
    payment_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    payment_request_id TEXT NOT NULL UNIQUE,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0)
);
```

Nếu chính sách là **một request ID chỉ được xử lý một lần**:

```sql
INSERT INTO constraint_lab_payments
    (payment_request_id, amount)
VALUES
    ('request-001', 500.00)
ON CONFLICT (payment_request_id) DO NOTHING
RETURNING payment_id, payment_request_id, amount;
```

Khi gửi lại cùng `request-001`, xung đột sẽ không tạo thêm dòng thanh toán.

### 21.2. Không bỏ qua trường hợp khóa trùng nhưng payload khác

Nếu lần retry dùng cùng `payment_request_id` nhưng số tiền **khác**, `DO NOTHING` sẽ bỏ qua và không tự báo rằng payload không nhất quán.

Trong nghiệp vụ tiền tệ, cần kiểm tra thêm **nội dung yêu cầu so với bản ghi đã có**; nếu khác phải trả lỗi xung đột nghiệp vụ, không âm thầm công nhận retry thành công. Có thể lưu hash payload đã chuẩn hóa và thực hiện đối chiếu trong transaction.

### 21.3. Idempotency không thay thế giao dịch

Khóa request duy nhất giúp ngăn nhân bản yêu cầu. Nhưng nếu một thanh toán liên quan tới nhiều bảng (payment, ledger, outbox), vẫn cần transaction để các thay đổi dữ liệu thuộc cùng thao tác nghiệp vụ **cùng commit hoặc rollback**.

## 22. Khóa ngoại, `ON CONFLICT` và thao tác đồng thời

Một mẫu truy vấn có vẻ an toàn:

```sql
-- Cảnh báo: cách kiểm tra riêng này có race condition.
SELECT 1
FROM constraint_lab_employees
WHERE email = 'new@example.test';

-- Nếu không thấy, ứng dụng quyết định INSERT.
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (70, 'new@example.test', 10, 1800);
```

Hai client A và B có thể cùng kiểm tra “chưa có”, rồi cùng chèn. Một client có thể thành công và client còn lại bị `23505`. Điều đó là **hành vi đúng của `UNIQUE`** trong database: ràng buộc cuối cùng chặn việc ghi trùng.

Nếu chính sách nghiệp vụ coi việc nhập trùng là bình thường, có thể dùng một câu:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (71, 'new@example.test', 10, 1800)
ON CONFLICT (email) DO NOTHING;
```

Nhưng phải hiểu:

- `employee_id=71` vẫn có thể trùng khóa chính với một dòng khác và lỗi nếu arbiter chỉ là email.
- `department_id` vẫn phải tồn tại.
- Lương vẫn phải thỏa `CHECK`.
- Nếu bỏ qua do email đã có, không có bản ghi nhân viên 71 mới được tạo.

**Không cần tắt ràng buộc để tránh race condition; cần thiết kế câu lệnh và quy tắc retry phù hợp với ràng buộc.**

### 22.1. Isolation level và lỗi phải retry

Một số giao dịch chạy ở mức cô lập cao có thể nhận lỗi như `serialization_failure` (`SQLSTATE 40001`). Đây không nhất thiết là lỗi dữ liệu đầu vào; ứng dụng có thể cần retry **toàn bộ transaction**, không chỉ chạy lại câu `INSERT` cuối cùng.

Retry phải giới hạn số lần, có cơ chế backoff phù hợp và bảo đảm các tác động bên ngoài không bị nhân đôi. Với `23514` vì lương âm, retry không sửa dữ liệu thường không có ích.

## 23. Ghi log và phản hồi lỗi trong ứng dụng

Một cách xử lý thực tế là phân biệt **lỗi mong đợi có thể giải thích cho người dùng** và **lỗi hệ thống cần vận hành xử lý**.

Ví dụ một service nhập nhân viên theo API:

```text
receive request
    ↓
validate required fields and format
    ↓
BEGIN transaction
    ↓
INSERT or UPSERT with declared conflict policy
    ↓
if all required steps succeed:
    COMMIT
    return confirmed result
else:
    ROLLBACK / ROLLBACK TO SAVEPOINT if allowed
    map SQLSTATE and constraint to safe error
    return validation/conflict/system response
```

### 23.1. Không đánh dấu thành công trước `COMMIT`

Nếu ứng dụng thực hiện `INSERT ... RETURNING`, rồi trả HTTP 200 cho client **trước khi commit** transaction, client có thể tin dữ liệu đã lưu dù commit sau đó thất bại do khóa ngoại deferred hoặc lỗi khác. Chỉ công bố thành công bền vững sau khi biết thao tác commit được hệ thống ghi nhận.

Trong trường hợp mất kết nối ngay khi commit, kết quả có thể **không chắc chắn** từ góc nhìn ứng dụng; dùng idempotency key và truy vấn đối soát thay vì đoán.

### 23.2. Không bỏ qua lỗi chỉ để hết thông báo đỏ

Một đoạn code đại ý:

```text
try:
    INSERT ...
catch:
    ignore
return SUCCESS
```

che khuất mọi loại lỗi: trùng dữ liệu, FK sai, CHECK sai, mất kết nối, timeout... Nó có thể khiến người dùng nghĩ dữ liệu đã lưu, trong khi database đã hủy câu lệnh.

Hãy phân loại lỗi có thể xử lý theo nghiệp vụ và **luôn** ghi nhận trạng thái thật.

### 23.3. Dùng constraint name đúng mục đích

Đặt tên rõ ràng cho các ràng buộc:

```sql
CONSTRAINT ck_lab_employee_salary CHECK (salary >= 0)
```

giúp ứng dụng log lỗi dạng:

```text
SQLSTATE=23514
CONSTRAINT=ck_lab_employee_salary
REQUEST_ID=...
```

Tuy nhiên, tên ràng buộc là chi tiết schema, có thể thay đổi khi migration. Nếu API công khai mã lỗi ổn định, nên có **lớp ánh xạ** giữa constraint name và error code nghiệp vụ.

## 24. Những lỗi hiểu nhầm thường gặp

| Hiểu nhầm | Điều thực sự xảy ra | Cách xử lý |
|---|---|---|
| `INSERT` 100 dòng, dòng 80 lỗi thì 79 dòng đầu còn | Với câu `INSERT` PostgreSQL thông thường, **toàn câu lệnh** bị hủy | Sửa dữ liệu hoặc thiết kế partial acceptance rõ ràng |
| `BEGIN` không cần thiết khi chạy nhiều `INSERT` | Autocommit có thể commit từng câu thành công | Dùng transaction cho thao tác nhiều bước all-or-nothing |
| Lỗi trong transaction xong vẫn chạy SQL tiếp được | PostgreSQL thường đưa transaction về trạng thái aborted | `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` |
| `SAVEPOINT` giữ lại dòng hợp lệ trong **cùng** `INSERT` thất bại | SAVEPOINT phục hồi transaction, không tách nguyên tử từng dòng của câu SQL | Tách câu lệnh khi nghiệp vụ cho phép partial |
| `DEFAULT` được dùng khi truyền `NULL` | `NULL` tường minh không tự chuyển thành `DEFAULT` | Bỏ cột hoặc viết `DEFAULT` |
| `CHECK(x > 0)` cũng buộc x không `NULL` | `CHECK` cho phép `UNKNOWN` | Thêm `NOT NULL` nếu bắt buộc |
| `UNIQUE(email)` luôn không phân biệt hoa/thường | Tùy kiểu/collation/chính sách so sánh | Định nghĩa khóa chuẩn hóa |
| FK lỗi thì cứ thêm mã cha giả | Có thể tạo dữ liệu sai nghiệp vụ | Nạp danh mục cha hợp lệ hoặc sửa nguồn |
| `ON CONFLICT DO NOTHING` bỏ qua tất cả lỗi | Chủ yếu xử lý xung đột duy nhất phù hợp | Vẫn kiểm tra FK, CHECK, NOT NULL và khóa khác |
| `ON CONFLICT` luôn chèn đúng số dòng trong nguồn | `DO NOTHING` có thể bỏ qua dòng | Đếm và đối soát `RETURNING`/trạng thái nhập |
| `DO UPDATE` cho nhiều dòng cùng khóa thì dòng cuối thắng | PostgreSQL có thể báo `21000` | Deduplicate nguồn theo quy tắc |
| `RETURNING` nghĩa là transaction đã commit | Transaction có thể rollback sau `RETURNING` | Chỉ xác nhận bền vững sau commit |
| `ROLLBACK` làm ID sequence quay lại | Sequence PostgreSQL không hoàn nguyên như dữ liệu bảng | Chấp nhận khoảng trống ID |
| Đã validate ở ứng dụng thì không cần constraint | Có race và đường ghi khác | Constraint ở database vẫn cần thiết |
| `23505` tự cho biết cột nào trùng | Cùng mã có thể là PK hoặc các UNIQUE khác | Dùng diagnostics constraint name |
| Dữ liệu thiếu và giá trị 0 giống nhau | Hai ý nghĩa nghiệp vụ khác nhau | Giữ `NULL`/trạng thái rõ ràng |
| Một câu SQL nguyên tử làm cả email/HTTP nguyên tử | Tác động ngoài database không tự rollback | Outbox, idempotency, compensation |
| Một câu `INSERT` chạy xong thì FK chắc đã hợp lệ | FK deferred có thể được kiểm tra tới COMMIT | Hiểu `DEFERRABLE` và xác nhận commit |

## 25. Bộ câu hỏi tự luyện

Các bài bên dưới sử dụng bảng `constraint_lab_departments` và `constraint_lab_employees` như **trạng thái gốc ở mục 2** (chỉ có nhân viên 1 và 2), trừ khi ghi rõ. Mỗi bài gây lỗi nên thử **riêng** trong phiên/transaction phù hợp; để tránh dữ liệu từ bài trước ảnh hưởng bài sau, có thể mở phiên mới và tạo lại bảng tạm.

### Bài 1 — Một câu `INSERT` với hai dòng

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (100, 'first100@example.test', 10, 1800),
    (101, 'second101@example.test', 20, -1);
```

Có bao nhiêu dòng của câu lệnh này được giữ? Loại ràng buộc nào thất bại? Giải thích vì sao `employee_id=100` không được lưu.

### Bài 2 — Trùng khóa chính

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (1, 'other@example.test', 10, 1400);
```

Lỗi nào xảy ra, SQLSTATE bao nhiêu? Phân biệt với trùng email.

### Bài 3 — Trùng email

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (102, 'an@example.test', 20, 1500);
```

Có phải vì mã nhân viên 102 chưa tồn tại nên câu lệnh hợp lệ không? Vì sao?

### Bài 4 — `NOT NULL` và `DEFAULT`

Hai câu sau có cùng kết quả không?

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (103, 'valid103@example.test', 10, 1900);
```

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary, employment_status)
VALUES
    (104, 'invalid104@example.test', 10, 1900, NULL);
```

### Bài 5 — `CHECK` với `NULL`

Một cột có `CHECK(amount > 0)` nhưng không có `NOT NULL`. Có được chèn `amount = NULL` không? Phải khai báo thế nào nếu giá trị vừa bắt buộc vừa phải dương?

### Bài 6 — Khóa ngoại

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (105, 'wrong105@example.test', 999, 2000);
```

Lỗi xảy ra ở đâu? Nêu hai cách xử lý dữ liệu nguồn **không phá vỡ tính toàn vẹn**.

### Bài 7 — Hai câu lệnh autocommit

Client bật autocommit. Câu thứ nhất chèn một dòng hợp lệ và thành công; câu thứ hai chèn một dòng lương âm và thất bại. Dòng thứ nhất có còn tồn tại không? Vì sao câu thứ hai lỗi không hủy câu đầu?

### Bài 8 — Một giao dịch hai bước

Viết `BEGIN`/`COMMIT`/`ROLLBACK` theo yêu cầu: chỉ lưu nhân viên và hồ sơ liên quan nếu **cả hai câu `INSERT`** đều thành công. Nếu câu thứ hai lỗi, điều gì xảy ra với câu thứ nhất?

### Bài 9 — Transaction lỗi và `25P02`

Sau một lỗi `CHECK` trong `BEGIN`, câu `SELECT COUNT(*)` cũng báo `25P02`. Giải thích nguyên nhân và hai cách phục hồi có thể dùng.

### Bài 10 — `SAVEPOINT`

Trong một transaction:

1. Thêm nhân viên 110 hợp lệ.
2. Tạo `SAVEPOINT`.
3. Thử thêm nhân viên 111 với lương âm, gặp lỗi.
4. Phục hồi về savepoint.
5. Thêm nhân viên 112 hợp lệ.
6. `COMMIT`.

Dòng nào được lưu? Nếu thay bước 6 bằng `ROLLBACK` thì kết quả khác thế nào?

### Bài 11 — `ON CONFLICT DO NOTHING`

Dữ liệu ban đầu có `an@example.test`. Viết câu SQL chèn hai dòng: một email mới và một email đó đã tồn tại, dùng `ON CONFLICT (email) DO NOTHING RETURNING employee_id, email`. Dự đoán `RETURNING` trả mấy dòng.

### Bài 12 — `ON CONFLICT` có cứu khóa ngoại không?

Viết `ON CONFLICT (email) DO NOTHING` với email chưa tồn tại nhưng `department_id=999`. Câu lệnh thành công hay thất bại? Vì sao?

### Bài 13 — Upsert

Viết câu SQL cập nhật `salary=2000` cho email `an@example.test` nếu email đã tồn tại; nếu email chưa có thì chèn bản ghi mới. Vì sao cần cẩn thận với `employee_id` được đề xuất chèn khi email đã tồn tại?

### Bài 14 — Trùng khóa trong nguồn upsert

Một lệnh có hai dòng đề xuất cùng email mới `same@example.test` và dùng `ON CONFLICT (email) DO UPDATE`. PostgreSQL có thể báo lỗi nào? Hãy đề xuất một cách xử lý nguồn trước khi upsert.

### Bài 15 — Deferred FK

Trong transaction, ta thêm dòng con tham chiếu `parent_id=999`, khóa ngoại khai báo `DEFERRABLE INITIALLY DEFERRED`, sau đó:

- Trường hợp A: thêm cha `999` rồi `COMMIT`.
- Trường hợp B: không thêm cha mà `COMMIT`.

Khi nào việc thêm con có thể tạm thành công, và khi nào giao dịch cuối cùng không được commit?

### Bài 16 — Sequence và rollback

Một bảng có khóa `IDENTITY`. Sau khi insert một dòng trong transaction rồi rollback, ID tiếp theo có bắt buộc liền kề với ID trước transaction không? Vì sao?

### Bài 17 — Kiểm tra trước rồi chèn

Hai client cùng thấy email chưa tồn tại và cùng chèn. Ràng buộc nào bảo vệ dữ liệu? Ứng dụng nên làm gì khi một client nhận `23505`?

### Bài 18 — All-or-nothing hay partial?

Một file nhập có 200 dòng, 10 dòng sai khóa ngoại. Hãy mô tả hai thiết kế phù hợp cho:

1. Hệ thống bắt buộc **đủ 200/200** mới chấp nhận.
2. Hệ thống cho phép **190 dòng hợp lệ** được nhận, 10 dòng được cách ly để sửa.

Trong mỗi trường hợp, cần báo người dùng điều gì?

<details>
<summary>Gợi ý đáp án</summary>

**Bài 1:** `CHECK(salary >= 0)` thất bại với mã `23514`; **0 dòng** của câu SQL được lưu. PostgreSQL hủy **toàn bộ câu INSERT** thông thường khi một dòng bị lỗi.

**Bài 2:** Trùng `PRIMARY KEY(employee_id)` với ID 1, lỗi `23505`. `23505` cũng dùng cho `UNIQUE(email)` nhưng **ràng buộc bị vi phạm** khác nhau.

**Bài 3:** Không hợp lệ. Email đã có ở nhân viên 1, nên `UNIQUE(email)` lỗi `23505` dù ID 102 là ID mới.

**Bài 4:** Câu đầu thành công, `employment_status` dùng mặc định `'ACTIVE'`. Câu sau truyền `NULL` tường minh vào cột `NOT NULL`, lỗi `23502`.

**Bài 5:** Có thể chèn `NULL` vì `CHECK(amount > 0)` cho `UNKNOWN`, không phải `FALSE`. Muốn bắt buộc và dương: `amount NUMERIC NOT NULL CHECK (amount > 0)`.

**Bài 6:** FK tới `constraint_lab_departments` không tìm thấy ID 999, mã `23503`. Có thể sửa ID theo danh mục hợp lệ hoặc nạp một bản ghi cha **thật sự hợp lệ** trước khi chèn con; nếu chưa thể xác định, cách ly dòng lỗi.

**Bài 7:** Câu đầu đã commit riêng nên vẫn còn. Atomicity của câu thứ hai chỉ hủy **thay đổi của câu thứ hai**, không hồi tố hủy câu trước đã commit.

**Bài 8:** Bọc các bước trong transaction:

```sql
BEGIN;
-- INSERT nhân viên hợp lệ.
-- INSERT hồ sơ liên quan.
-- Chỉ khi tất cả thành công:
COMMIT;
```

Nếu bước bắt buộc lỗi, dùng `ROLLBACK` thay vì `COMMIT`. Trong PostgreSQL, câu lỗi làm transaction aborted và các thay đổi chưa commit trước đó sẽ bị hủy khi rollback.

**Bài 9:** `25P02` báo transaction đã lỗi từ một câu trước. Nếu không có savepoint thích hợp, dùng `ROLLBACK` để hủy transaction. Nếu có `SAVEPOINT` được tạo trước lỗi, dùng `ROLLBACK TO SAVEPOINT` để phục hồi một phần rồi quyết định tiếp tục.

**Bài 10:**

```sql
BEGIN;
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES (110, 'worker110@example.test', 10, 1500);

SAVEPOINT before_bad_row;
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES (111, 'worker111@example.test', 20, -1);
-- Lỗi CHECK.

ROLLBACK TO SAVEPOINT before_bad_row;
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES (112, 'worker112@example.test', 20, 1600);
COMMIT;
```

Sau `COMMIT`, 110 và 112 được lưu, 111 không có. Nếu thay `COMMIT` bằng `ROLLBACK` toàn transaction thì cả 110 và 112 cũng bị hủy.

**Bài 11:**

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (120, 'fresh120@example.test', 10, 1400),
    (121, 'an@example.test', 10, 1500)
ON CONFLICT (email) DO NOTHING
RETURNING employee_id, email;
```

Với dữ liệu gốc, chỉ trả **một dòng** có ID 120; dòng đề xuất 121 bị bỏ qua vì email trùng.

**Bài 12:** Vẫn thất bại với `23503` vì `ON CONFLICT (email)` không xử lý `FOREIGN KEY`. Nó không phải lệnh bỏ qua mọi lỗi.

**Bài 13:** Ví dụ:

```sql
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES (122, 'an@example.test', 10, 2000)
ON CONFLICT (email)
DO UPDATE SET salary = EXCLUDED.salary;
```

Với dữ liệu gốc, dòng nhân viên 1 được cập nhật; dòng ID 122 chỉ là **đề xuất chèn**, không tự thay khóa của nhân viên 1. Nếu email chưa có, ID 122 sẽ được dùng để chèn; ứng dụng phải bảo đảm ID được đề xuất hợp lệ và không gây xung đột khác.

**Bài 14:** Có thể gặp lỗi `21000` do một câu `ON CONFLICT DO UPDATE` tìm cách ảnh hưởng cùng dòng đích nhiều lần. Cần giải quyết khóa trùng trong staging theo chính sách như giữ bản mới nhất, giữ bản đầu tiên, hoặc bác bỏ toàn nhóm trùng trước khi upsert.

**Bài 15:** Với FK deferred, `INSERT` con có thể tạm thành công dù cha chưa có. Trường hợp A thêm cha trước commit nên transaction có thể thành công; trường hợp B không sửa tham chiếu nên **commit bị lỗi FK và transaction không được commit**.

**Bài 16:** Không. Sequence không rollback các số đã phát như dữ liệu bảng; ID có thể có khoảng trống dù không có bản ghi tương ứng. Không dùng ID tự tăng làm số thứ tự nghiệp vụ bắt buộc liên tục.

**Bài 17:** `UNIQUE(email)` bảo vệ dữ liệu dưới ghi đồng thời. Client lỗi cần nhận diện `23505`, kiểm tra đó là retry hợp lệ hay xung đột nghiệp vụ, có thể dùng khóa idempotency/upsert khi đặc tả cho phép.

**Bài 18:** (1) All-or-nothing: transaction bao toàn batch, lỗi 10 dòng khiến **rollback 200 dòng**, báo file chưa được chấp nhận và danh sách lỗi. (2) Partial acceptance: nhập staging, chẩn đoán và cách ly 10 dòng, chỉ đưa 190 dòng hợp lệ vào bảng đích trong các thao tác được kiểm soát, ghi báo cáo `190 accepted / 10 rejected` kèm lý do; database vẫn phải áp các ràng buộc để chống race condition.

</details>

## 26. Mẫu quyết định xử lý khi một `INSERT` bị lỗi

Khi nhận lỗi, hãy trả lời theo thứ tự:

1. **Câu SQL nào đã thất bại?** Một `INSERT` nhiều dòng hay câu thứ N trong transaction?
2. **Lỗi gốc là gì?** `23505`, `23502`, `23503`, `23514`, lỗi chuyển kiểu, hay lỗi đồng thời?
3. **Transaction còn ở trạng thái có thể chạy không?** Trong PostgreSQL, sau lỗi trong `BEGIN` thường phải `ROLLBACK` hoặc quay về `SAVEPOINT`.
4. **Yêu cầu nghiệp vụ là all-or-nothing hay partial?** Không tự bỏ qua lỗi chỉ để câu lệnh thành công.
5. **Xung đột được phép giải quyết bằng `ON CONFLICT` không?** Nó không xử lý tất cả ràng buộc.
6. **Dữ liệu có thể được sửa đúng không?** Chẳng hạn sửa FK, giá trị bắt buộc, số tiền âm hoặc khóa trùng.
7. **Có nguy cơ retry tạo bản ghi trùng không?** Dùng khóa duy nhất/idempotency và phương pháp đối soát phù hợp.
8. **Có bước nào đã phát tác động bên ngoài không?** Gửi email/API không tự rollback; cần outbox hay bù trừ.
9. **Đã thực sự `COMMIT` thành công chưa?** `RETURNING` hay log “INSERT OK” trước commit chưa đủ.
10. **Có đối soát số dòng không?** Với `DO NOTHING` hay lọc staging, câu SQL thành công không đảm bảo mọi dòng nguồn đã được nhận.

Một cấu trúc tư duy:

```text
Một INSERT bị lỗi ràng buộc
              │
              ▼
   Xác định SQLSTATE và phạm vi lỗi
              │
              ├── Một câu INSERT, autocommit?
              │       └── Câu lỗi không commit phần dữ liệu của nó
              │
              ├── Đang trong BEGIN?
              │       ├── Không có SAVEPOINT → ROLLBACK
              │       └── Có SAVEPOINT → ROLLBACK TO nếu được phép tiếp tục
              │
              └── Chính sách nghiệp vụ?
                      ├── All-or-nothing → sửa nguồn, retry cả lô đúng cách
                      └── Partial → báo reject, chỉ chèn mục hợp lệ có chủ đích
```

## 27. Kết luận

**Tính nguyên tử của câu lệnh** trong PostgreSQL bảo đảm một `INSERT` thông thường không để lại **nửa kết quả được commit** khi câu lệnh thất bại: một dòng sai ràng buộc có thể khiến tất cả dòng của câu `INSERT` nhiều dòng bị từ chối. Nhưng **nhiều câu SQL độc lập**, **một transaction**, **một savepoint** và **một quy trình có dịch vụ ngoài** là các phạm vi khác nhau, phải được thiết kế và xử lý riêng.

Ba mẫu cần nhớ:

```sql
-- 1. Nhiều dòng trong một INSERT: nếu một dòng vi phạm CHECK chưa
--    được xử lý, cả câu INSERT bị lỗi, không giữ dòng hợp lệ riêng.
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (130, 'good130@example.test', 10, 1500),
    (131, 'bad131@example.test',  20, -1);
```

```sql
-- 2. Nhiều câu lệnh cần cùng thành công: transaction tường minh.
BEGIN;
-- INSERT vào bảng cha...
-- INSERT vào bảng con...
COMMIT;
-- Nếu bước bắt buộc lỗi: ROLLBACK thay vì COMMIT.
```

```sql
-- 3. Trùng email là trường hợp được phép bỏ qua theo nghiệp vụ:
--    xử lý xung đột duy nhất có chủ đích, không bỏ qua FK/CHECK.
INSERT INTO constraint_lab_employees
    (employee_id, email, department_id, salary)
VALUES
    (132, 'an@example.test', 10, 1500)
ON CONFLICT (email) DO NOTHING
RETURNING employee_id, email;
```

Hãy giữ các **ràng buộc trong database** làm hàng rào bảo vệ cuối cùng, xác định đúng **phạm vi nguyên tử** cần thiết, coi `ON CONFLICT` là một **quyết định nghiệp vụ rõ ràng**, và **chỉ công nhận thành công khi trạng thái dữ liệu thực sự đã được commit như mong đợi**. Khi làm được điều đó, thao tác thêm dữ liệu không chỉ “chạy được”, mà còn có thể **phục hồi, giải thích và đối soát** khi tình huống xấu xảy ra.
