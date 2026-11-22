# NOT NULL và kiểm soát dữ liệu bắt buộc

Trong một hệ thống đăng ký tài khoản, bản ghi người dùng có thể chưa có ảnh đại diện hoặc số điện thoại, nhưng **không được thiếu tên đăng nhập**. Cơ sở dữ liệu cần thể hiện được sự khác nhau giữa thông tin **bắt buộc** và thông tin **tùy chọn**. Ràng buộc `NOT NULL` là công cụ cơ bản để thực hiện yêu cầu này trên từng cột.

Trong SQL, `NULL` cho biết một giá trị không hiện diện hoặc chưa được biết trong cột tương ứng. Khi khai báo cột `NOT NULL`, cơ sở dữ liệu từ chối các thao tác khiến cột đó mang `NULL`. Tuy nhiên, `NOT NULL` **không tự kiểm tra chuỗi rỗng, khoảng trắng, định dạng email, giá trị số hợp lệ theo nghiệp vụ hay quan hệ giữa nhiều cột**. Muốn kiểm soát dữ liệu bắt buộc một cách đúng đắn, cần hiểu cả phạm vi bảo vệ và giới hạn của ràng buộc này.

Bài này thuộc **Database SQL → Khóa và ràng buộc**, dùng PostgreSQL làm hệ quản trị chính trong ví dụ. Những nguyên tắc chung áp dụng rộng rãi, nhưng cú pháp thay đổi cấu trúc bảng và cách xử lý chuỗi rỗng có thể khác ở MySQL, SQL Server, SQLite hoặc Oracle.

## 1. NULL là gì và tại sao cần NOT NULL?

Giả sử một bảng lưu dữ liệu người dùng:

| username | email | display_name |
| --- | --- | --- |
| `an` | `an@example.test` | `NULL` |
| `binh` | `binh@example.test` | `''` |
| `chi` | `chi@example.test` | `Chi` |

Cột `display_name` cho phép người dùng chưa nhập tên hiển thị, vì vậy hàng của An có thể chứa `NULL`. Nhưng nếu `username` hoặc `email` là dữ liệu bắt buộc, hệ thống phải ngăn trường hợp chúng bị để trống theo nghĩa `NULL`.

Những giá trị sau có ý nghĩa khác nhau:

| Giá trị | Ý nghĩa | `IS NULL` trả về gì? |
| --- | --- | --- |
| `NULL` | Không có giá trị được lưu / giá trị chưa biết | TRUE |
| `''` | Chuỗi có độ dài bằng 0 | FALSE trong PostgreSQL |
| `'   '` | Chuỗi chứa dấu cách | FALSE |
| `0` | Giá trị số bằng không | FALSE |
| `FALSE` | Giá trị Boolean sai | FALSE |
| `'NULL'` | Chuỗi có nội dung là chữ “NULL” | FALSE |

Trong PostgreSQL, `NULL` khác cả chuỗi rỗng và chuỗi có khoảng trắng. Với Oracle Database, chuỗi rỗng thường được xử lý như `NULL` trong các cột chuỗi, nên ví dụ về `''` không thể áp dụng nguyên xi cho Oracle.

Ràng buộc `NOT NULL` giúp cơ sở dữ liệu đảm bảo một **bất biến dữ liệu** (*data invariant*): mọi hàng hợp lệ của bảng phải có giá trị ở cột đó. Quy tắc nằm trong lược đồ và áp dụng cho các thao tác ghi được cơ sở dữ liệu chấp nhận, bất kể thao tác đến từ website, ứng dụng Java, công cụ SQL hay script nhập dữ liệu.

## 2. Khai báo NOT NULL khi tạo bảng

### 2.1. Cú pháp cơ bản

Trong `CREATE TABLE`, đặt `NOT NULL` sau kiểu dữ liệu:

~~~sql
CREATE TABLE ten_bang (
    cot_bat_buoc VARCHAR(100) NOT NULL,
    cot_tuy_chon VARCHAR(100)
);
~~~

Ở đây, `cot_bat_buoc` không thể nhận `NULL`, còn `cot_tuy_chon` mặc định có thể nhận `NULL` trên PostgreSQL. Từ khóa `NULL` ghi tường minh trong khai báo cột đôi khi dùng để nhấn mạnh “cho phép NULL”, nhưng không cần thiết trong ví dụ này.

### 2.2. Bảng mẫu có cả cột bắt buộc và tùy chọn

Hãy tạo bảng sau trong **database PostgreSQL thực hành**, nơi chưa tồn tại bảng `lab_registrations_93`:

~~~sql
CREATE TABLE lab_registrations_93 (
    registration_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(40) NOT NULL,
    email VARCHAR(150) NOT NULL,
    display_name VARCHAR(80),
    status VARCHAR(12) NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_lab_registrations_93_email UNIQUE (email),
    CONSTRAINT ck_lab_registrations_93_status
        CHECK (status IN ('PENDING', 'ACTIVE', 'LOCKED'))
);
~~~

Giải thích:

| Cột | Khai báo quan trọng | Điều được bảo vệ |
| --- | --- | --- |
| `registration_id` | `GENERATED ALWAYS AS IDENTITY PRIMARY KEY` | Có định danh tự sinh và không được `NULL` do khóa chính |
| `username` | `VARCHAR(40) NOT NULL` | Mỗi hàng phải có giá trị khác `NULL` |
| `email` | `VARCHAR(150) NOT NULL` | Bắt buộc có giá trị; `UNIQUE` riêng giúp không trùng email |
| `display_name` | `VARCHAR(80)` | Có thể chưa có tên hiển thị |
| `status` | `NOT NULL DEFAULT 'PENDING'` | Không nhận `NULL`; khi bỏ qua cột có thể dùng trạng thái mặc định |
| `created_at` | `NOT NULL DEFAULT CURRENT_TIMESTAMP` | Khi không cung cấp, máy chủ cấp thời gian tạo; không nhận `NULL` |

`NOT NULL` và `UNIQUE` có nhiệm vụ khác nhau: `NOT NULL` cấm giá trị thiếu; `UNIQUE` kiểm soát sự trùng lặp. PostgreSQL cho phép nhiều giá trị `NULL` trong một cột `UNIQUE` thông thường nếu cột đó không `NOT NULL`, vì vậy khi email vừa bắt buộc vừa cần duy nhất, khai báo **cả hai**.

`PRIMARY KEY` cũng đòi hỏi giá trị khóa không `NULL`, nên không cần lặp lại `NOT NULL` trên cột khóa chính trong ví dụ này. Với khóa chính gồm nhiều cột, **từng cột thành phần** đều phải có giá trị khác `NULL`.

### 2.3. Thêm dữ liệu hợp lệ

Chạy:

~~~sql
INSERT INTO lab_registrations_93
    (username, email, display_name, status)
VALUES
    ('an',   'an@example.test',   NULL, 'ACTIVE'),
    ('binh', 'binh@example.test', '',   'PENDING'),
    ('chi',  'chi@example.test',  'Chi', DEFAULT);
~~~

Trong PostgreSQL, `DEFAULT` ở hàng thứ ba yêu cầu hệ quản trị dùng giá trị mặc định `PENDING`. Mỗi hàng đều có `username` và `email` khác `NULL`; `display_name` được phép là `NULL` hoặc chuỗi rỗng vì không có `NOT NULL` trên cột này.

Quan sát dữ liệu, dùng thứ tự do truy vấn xác định:

~~~sql
SELECT username, email, display_name, status
FROM lab_registrations_93
ORDER BY username;
~~~

| username | email | display_name | status |
| --- | --- | --- | --- |
| an | an@example.test | `NULL` | ACTIVE |
| binh | binh@example.test | `''` | PENDING |
| chi | chi@example.test | Chi | PENDING |

Hai cột `registration_id` và `created_at` được database tự cấp vì câu `INSERT` không liệt kê chúng. Đây là kết quả của `IDENTITY` và `DEFAULT`, **không phải của `NOT NULL` tự động tạo giá trị**.

## 3. NOT NULL hoạt động khi INSERT

### 3.1. Chèn NULL tường minh vào cột bắt buộc

~~~sql
-- SAI: email duoc khai bao NOT NULL.
INSERT INTO lab_registrations_93 (username, email)
VALUES ('dung', NULL);
~~~

PostgreSQL từ chối với thông báo `null value in column ... violates not-null constraint`. Mã SQLSTATE thường là **`23502`**. Câu `INSERT` không thêm hàng mới vào bảng.

Nếu thay bằng giá trị email phù hợp kiểu và các quy tắc hiện có, lệnh mới có thể chạy:

~~~sql
-- Chi chay neu muon them du lieu thuc hanh.
INSERT INTO lab_registrations_93 (username, email)
VALUES ('dung', 'dung@example.test');
~~~

### 3.2. Bỏ qua một cột bắt buộc không có DEFAULT

~~~sql
-- SAI: email bi bo qua va khong co gia tri DEFAULT.
INSERT INTO lab_registrations_93 (username)
VALUES ('em');
~~~

Khi không được cung cấp, cột `email` không có giá trị mặc định phù hợp nên có giá trị `NULL`; `NOT NULL` chặn thao tác. **Không phải cột nào bị bỏ qua cũng được tự điền**: kết quả phụ thuộc khai báo `DEFAULT` hoặc cơ chế tự sinh riêng của cột.

### 3.3. Bỏ qua cột bắt buộc nhưng có DEFAULT

~~~sql
-- HOP LE: status va created_at co DEFAULT.
INSERT INTO lab_registrations_93 (username, email)
VALUES ('ha', 'ha@example.test');
~~~

Nếu chạy câu trên trên dữ liệu mẫu, `status` sẽ là `PENDING` và `created_at` được cấp thời gian. Nhưng lưu ý:

~~~sql
-- SAI: NULL tuong minh KHONG kich hoat DEFAULT.
INSERT INTO lab_registrations_93 (username, email, status)
VALUES ('lan', 'lan@example.test', NULL);
~~~

**Bỏ cột** hoặc viết `DEFAULT` khác với việc gửi **`NULL` tường minh**. PostgreSQL không thay `NULL` tường minh bằng `DEFAULT` khi cột `NOT NULL`. Nếu ứng dụng gửi `NULL` vì quên xử lý trường, database sẽ báo lỗi thay vì tự hiểu “hãy dùng mặc định”.

### 3.4. Dùng DEFAULT tường minh

~~~sql
INSERT INTO lab_registrations_93 (username, email, status)
VALUES ('minh', 'minh@example.test', DEFAULT);
~~~

Lệnh trên hợp lệ nếu không vi phạm ràng buộc khác. Giá trị `status` được lấy từ `DEFAULT 'PENDING'`. Nếu đổi định nghĩa mặc định sau này, kết quả của các lần chèn tiếp theo có thể thay đổi.

**Lưu ý với bài thực hành:** các câu chèn hợp lệ trong mục này là các thao tác thật. Để giữ bảng đúng ba người dùng ban đầu cho những bài sau, chỉ đọc ví dụ hoặc thử trong transaction rồi `ROLLBACK`. Các câu chèn cố tình sai có thể làm PostgreSQL đưa transaction hiện tại vào trạng thái lỗi; cần `ROLLBACK` trước khi thử câu khác trong cùng transaction.

## 4. NOT NULL hoạt động khi UPDATE

Không chỉ `INSERT` mới bị kiểm tra. Bất kỳ thao tác nào định biến cột bắt buộc thành `NULL` cũng bị từ chối.

~~~sql
-- SAI: email NOT NULL.
UPDATE lab_registrations_93
SET email = NULL
WHERE username = 'an';
~~~

`WHERE` đã chọn đúng một bản ghi nhưng câu lệnh vẫn bị từ chối vì **giá trị mới** không đáp ứng cấu trúc bảng. Nếu `UPDATE` không có `WHERE`, nhiều hàng có thể bị ảnh hưởng; ràng buộc vẫn được kiểm tra, nhưng một câu lệnh chạy thành công không đồng nghĩa nó đã cập nhật đúng đối tượng nghiệp vụ.

Ngược lại, cập nhật cột tùy chọn thành `NULL` là hợp lệ:

~~~sql
BEGIN;

UPDATE lab_registrations_93
SET display_name = NULL
WHERE username = 'chi';

SELECT username, display_name
FROM lab_registrations_93
WHERE username = 'chi';

ROLLBACK;
~~~

Ví dụ này chỉ quan sát giá trị tạm thời trong transaction. Sau `ROLLBACK`, bản ghi Chi trở lại như trước. Trong PostgreSQL, transaction gặp lỗi có thể cần rollback trước khi chạy tiếp; không đặt một ví dụ cố ý gây lỗi giữa các lệnh mà bạn mong chạy bình thường.

Khi muốn đặt lại `status` theo giá trị mặc định, PostgreSQL hỗ trợ:

~~~sql
BEGIN;

UPDATE lab_registrations_93
SET status = DEFAULT
WHERE username = 'an';

SELECT username, status
FROM lab_registrations_93
WHERE username = 'an';

ROLLBACK;
~~~

Trong transaction, An nhận `PENDING`; `ROLLBACK` hoàn tác cập nhật. `SET status = DEFAULT` khác `SET status = NULL` vì khai báo mặc định của cột được sử dụng.

## 5. NOT NULL không kiểm tra mọi ý nghĩa của “bắt buộc”

Một cột khác `NULL` vẫn có thể chứa dữ liệu không dùng được. Xét `username VARCHAR(40) NOT NULL`:

~~~sql
-- Co the duoc chap nhan boi schema hien tai:
INSERT INTO lab_registrations_93 (username, email)
VALUES ('', 'empty-username@example.test');
~~~

Với PostgreSQL, `''` là chuỗi rỗng **khác `NULL`**. Vì schema chưa khai báo quy tắc cấm chuỗi rỗng, `NOT NULL` tự nó không từ chối dữ liệu này. Câu sau cũng có thể được chấp nhận:

~~~sql
-- Khoang trang khong phai NULL.
INSERT INTO lab_registrations_93 (username, email)
VALUES ('   ', 'spaces-username@example.test');
~~~

Để phân biệt các cấp kiểm soát:

| Yêu cầu | `NOT NULL` một mình có đủ không? | Quy tắc bổ sung thường cần |
| --- | --- | --- |
| Tên đăng nhập phải có giá trị khác NULL | Có | — |
| Tên đăng nhập không được là chuỗi rỗng | Không | `CHECK (username <> '')` hoặc kiểm tra tương đương |
| Tên đăng nhập không được toàn dấu cách | Không | `CHECK (length(btrim(username)) > 0)` trên PostgreSQL |
| Email phải đúng định dạng | Không | Kiểm tra định dạng theo quy tắc hệ thống |
| Email phải duy nhất | Không | `UNIQUE` |
| Tuổi phải không âm | Không | `CHECK (age >= 0)` |
| Số tiền phải dương | Không | `CHECK (amount > 0)` |
| Đơn hàng phải tham chiếu khách hàng có thật | Không | `FOREIGN KEY` |

### 5.1. NOT NULL kết hợp CHECK để cấm chuỗi trống

Với một bảng **mới** cần tên đăng nhập có nội dung, có thể khai báo:

~~~sql
CREATE TABLE lab_usernames_strict_93 (
    user_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(40) NOT NULL,
    CONSTRAINT ck_lab_usernames_strict_93_nonblank
        CHECK (length(btrim(username)) > 0)
);
~~~

Trong PostgreSQL, `btrim(username)` bỏ khoảng trắng thông thường ở hai đầu; `length(...) > 0` đòi hỏi chuỗi còn ký tự sau khi cắt khoảng trắng. Những dấu cách hoặc ký tự trắng đặc biệt ngoài bộ ký tự mà `btrim` mặc định xử lý có thể cần quy tắc chuẩn hóa riêng.

Hai ràng buộc phối hợp như sau:

- `NOT NULL` chặn giá trị `NULL`.
- `CHECK` chặn chuỗi rỗng và chuỗi chỉ gồm dấu cách được `btrim` xử lý.

Không nên dùng **chỉ** `CHECK (length(btrim(username)) > 0)` để bảo đảm khác `NULL`. Trong logic ba giá trị SQL, `CHECK` chấp nhận điều kiện **TRUE** và thường cũng không từ chối khi điều kiện là **UNKNOWN**. Nếu `username` là `NULL`, phép tính trả về UNKNOWN và có thể lọt qua `CHECK` một mình. Vì vậy cần ràng buộc `NOT NULL`.

### 5.2. Giá trị số 0 và Boolean FALSE là dữ liệu hợp lệ

Một ứng dụng có thể có cột `quantity INTEGER NOT NULL` và `is_active BOOLEAN NOT NULL`. Khi đó `0` và `FALSE` là **giá trị thực sự**, không phải “thiếu dữ liệu”. Nếu nghiệp vụ cấm số lượng âm, thêm `CHECK (quantity >= 0)`. Nếu nghiệp vụ bắt buộc người dùng phải đồng ý với điều khoản, `consent BOOLEAN NOT NULL` vẫn cho phép `FALSE`; cần một quy tắc phù hợp nếu việc đồng ý là điều kiện của thao tác.

Vì vậy, “bắt buộc phải có dữ liệu” không nên bị hiểu thành “mọi dữ liệu khác 0 hoặc FALSE đều đúng”.

## 6. NULL, DEFAULT, PRIMARY KEY, UNIQUE và FOREIGN KEY liên quan thế nào?

Ràng buộc là các lớp quy tắc phối hợp, không thay thế cho nhau.

### 6.1. NOT NULL và DEFAULT

`DEFAULT` trả lời **“nếu không cung cấp giá trị, dùng gì?”**. `NOT NULL` trả lời **“có chấp nhận giá trị NULL không?”**.

~~~sql
status VARCHAR(12) NOT NULL DEFAULT 'PENDING'
~~~

Cho phép bỏ cột `status` trong `INSERT`, đồng thời bảo vệ cột khỏi `NULL` tường minh. Một `DEFAULT NULL` hoặc không có default không tự thỏa `NOT NULL`.

### 6.2. NOT NULL và PRIMARY KEY

Khóa chính bảo đảm mỗi hàng có định danh duy nhất và không `NULL`; nhiều cột có thể cùng tạo thành khóa chính ghép. Ví dụ:

~~~sql
CREATE TABLE lab_enrollments_93 (
    student_id INTEGER,
    course_id INTEGER,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, course_id)
);
~~~

Trong PostgreSQL, cả `student_id` và `course_id` đều không thể nhận `NULL` nhờ `PRIMARY KEY`, dù không viết thêm `NOT NULL` trên từng dòng khai báo. Đây là quy tắc của khóa chính, không phải quy tắc tự động của mọi khóa.

### 6.3. NOT NULL và UNIQUE

`UNIQUE` chủ yếu bảo đảm không có các giá trị trùng theo ngữ nghĩa của hệ quản trị. Trong PostgreSQL, một cột `UNIQUE` **có thể chứa nhiều `NULL`** theo mặc định, trừ khi cấu hình có quy tắc khác (PostgreSQL hỗ trợ tùy chọn `NULLS NOT DISTINCT`). Vì vậy:

~~~sql
email VARCHAR(150) NOT NULL UNIQUE
~~~

là một lựa chọn phù hợp khi email phải có và phải duy nhất. Còn:

~~~sql
email VARCHAR(150) UNIQUE
~~~

cho phép email chưa biết được lưu là `NULL`, phù hợp với bài toán email tùy chọn và duy nhất khi đã cung cấp.

### 6.4. NOT NULL và FOREIGN KEY

Giả sử đơn hàng **bắt buộc** phải có khách hàng:

~~~sql
CREATE TABLE lab_orders_93 (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    CONSTRAINT fk_lab_orders_93_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers_93(customer_id)
);
~~~

Ví dụ trên **giả định đã có bảng** `lab_customers_93` với khóa `customer_id` hợp lệ, nên chỉ dùng như mẫu lược đồ, không chạy riêng khi chưa tạo bảng tham chiếu.

`NOT NULL` bảo đảm mỗi đơn có một giá trị `customer_id`; `FOREIGN KEY` bảo đảm giá trị đó tham chiếu đến khách hàng hợp lệ. Nếu bỏ `NOT NULL`, nhiều hệ quản trị cho phép khóa ngoại một cột mang `NULL` để thể hiện quan hệ tùy chọn. Do vậy, **có khóa ngoại chưa có nghĩa quan hệ là bắt buộc**.

## 7. Kiểm tra cột nào đang bắt buộc trong schema

Không nên chỉ nhìn dữ liệu mẫu rồi đoán thuộc tính cột. Trong PostgreSQL, có thể hỏi metadata chuẩn qua `information_schema.columns`:

~~~sql
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default,
    is_identity
FROM information_schema.columns
WHERE table_schema = current_schema()
  AND table_name = 'lab_registrations_93'
ORDER BY ordinal_position;
~~~

`is_nullable = 'NO'` cho biết cột không cho phép `NULL`; `'YES'` cho biết có thể nhận `NULL` theo metadata của cột. Các trường `column_default` và `is_identity` cho biết khả năng cấp giá trị khi người viết lệnh bỏ qua cột; chúng không đồng nghĩa với tính bắt buộc.

Để quan sát chính xác hàng thiếu hoặc có dữ liệu:

~~~sql
SELECT
    COUNT(*) AS tong_hang,
    COUNT(display_name) AS co_display_name_khac_null,
    COUNT(*) FILTER (WHERE display_name IS NULL) AS thieu_display_name,
    COUNT(*) FILTER (WHERE display_name = '') AS display_name_rong
FROM lab_registrations_93;
~~~

Nếu vẫn giữ đúng ba hàng mẫu ban đầu, kết quả là:

| tong_hang | co_display_name_khac_null | thieu_display_name | display_name_rong |
| ---: | ---: | ---: | ---: |
| 3 | 2 | 1 | 1 |

`COUNT(*)` đếm tất cả hàng; `COUNT(column)` bỏ qua `NULL` nhưng vẫn đếm `''`. Đây là cách hữu ích để phân biệt **thiếu giá trị** và **giá trị có mặt nhưng vô nghĩa về nghiệp vụ**.

## 8. Thêm NOT NULL vào bảng đang có dữ liệu

Trong ứng dụng thực tế, cột ban đầu có thể cho phép `NULL` nhưng sau một thay đổi nghiệp vụ phải trở thành cột bắt buộc. Khi đó không thể chỉ sửa DDL mà bỏ qua các hàng đang tồn tại.

### 8.1. Ví dụ bảng cũ có dữ liệu NULL

Tạo bảng riêng cho tình huống chuyển đổi:

~~~sql
CREATE TABLE lab_tasks_legacy_93 (
    task_id INTEGER PRIMARY KEY,
    title VARCHAR(100) NOT NULL,
    task_status VARCHAR(20)
);

INSERT INTO lab_tasks_legacy_93 (task_id, title, task_status)
VALUES
    (1, 'Viet tai lieu', 'OPEN'),
    (2, 'Kiem thu', NULL),
    (3, 'Trien khai', 'DONE');
~~~

Hiện tại `task_status` cho phép `NULL`. Nếu chạy:

~~~sql
-- SAI khi bang van con task_status NULL.
ALTER TABLE lab_tasks_legacy_93
ALTER COLUMN task_status SET NOT NULL;
~~~

PostgreSQL sẽ từ chối vì ít nhất một hàng đang vi phạm quy tắc mới.

### 8.2. Quy trình chuyển đổi có kiểm soát

**Bước 1 — Thống kê giá trị thiếu:**

~~~sql
SELECT COUNT(*) AS so_hang_null
FROM lab_tasks_legacy_93
WHERE task_status IS NULL;
~~~

Kết quả: **1**.

**Bước 2 — Quyết định cách xử lý hợp lệ theo nghiệp vụ.** Có thể xác minh lại nguồn thông tin, nhờ người quản trị bổ sung, hoặc gán trạng thái mặc định **nếu nghiệp vụ xác nhận điều đó là đúng**. Không tự gán `'DONE'` hoặc `'OPEN'` khi chưa biết tình trạng thật.

Giả sử quy tắc được phê duyệt là “công việc chưa có trạng thái sẽ được coi là `PENDING`”, có thể viết:

~~~sql
UPDATE lab_tasks_legacy_93
SET task_status = 'PENDING'
WHERE task_status IS NULL;
~~~

**Bước 3 — Xác minh không còn hàng vi phạm:**

~~~sql
SELECT COUNT(*) AS so_hang_null
FROM lab_tasks_legacy_93
WHERE task_status IS NULL;
~~~

Kết quả: **0**.

**Bước 4 — Thêm ràng buộc:**

~~~sql
ALTER TABLE lab_tasks_legacy_93
ALTER COLUMN task_status SET NOT NULL;
~~~

**Bước 5 — Nếu cần, định nghĩa DEFAULT cho các lần chèn mới:**

~~~sql
ALTER TABLE lab_tasks_legacy_93
ALTER COLUMN task_status SET DEFAULT 'PENDING';
~~~

Lưu ý rằng `SET DEFAULT` **không tự cập nhật các hàng cũ đã có `NULL`**. Nó chỉ định giá trị khi một thao tác `INSERT`/`UPDATE ... SET column = DEFAULT` sử dụng mặc định ở thời điểm phù hợp.

### 8.3. Bổ sung cột NOT NULL vào bảng đã có hàng

Lệnh sau trong PostgreSQL thường thất bại nếu bảng đã có dữ liệu và cột mới không có cách tạo giá trị:

~~~sql
-- SAI neu bang khong rong va cot moi khong co gia tri mac dinh.
ALTER TABLE lab_tasks_legacy_93
ADD COLUMN source_code VARCHAR(30) NOT NULL;
~~~

Nếu nghiệp vụ cho phép mọi hàng cũ mang nguồn `'LEGACY'`, có thể:

~~~sql
ALTER TABLE lab_tasks_legacy_93
ADD COLUMN source_code VARCHAR(30) NOT NULL DEFAULT 'LEGACY';
~~~

Hoặc triển khai theo nhiều bước: thêm cột nullable, xác minh/bổ sung dữ liệu phù hợp, kiểm tra không còn `NULL`, sau đó `SET NOT NULL`. Cách lựa chọn phụ thuộc dữ liệu lịch sử và khả năng thay đổi schema trong hệ thống đang hoạt động.

**Ảnh hưởng vận hành:** thay đổi ràng buộc trên bảng lớn có thể phải quét dữ liệu, đợi khóa và ảnh hưởng các phiên ghi đồng thời. Với hệ thống sản xuất, cần lập kế hoạch migration, triển khai ứng dụng đã hỗ trợ giá trị bắt buộc, theo dõi lỗi và có phương án vận hành phù hợp. Những ví dụ trên dành cho bảng nhỏ trong môi trường thực hành.

## 9. Khi yêu cầu bắt buộc phụ thuộc vào điều kiện

Đôi khi một cột chỉ phải có giá trị trong một trạng thái nhất định. Ví dụ, **chỉ khi yêu cầu được duyệt (`APPROVED`) thì phải có người duyệt**.

`reviewer` không thể khai báo `NOT NULL` nếu các yêu cầu còn chờ xử lý được phép chưa có người duyệt. Một quy tắc `CHECK` có điều kiện phù hợp hơn:

~~~sql
CREATE TABLE lab_approvals_93 (
    approval_id INTEGER PRIMARY KEY,
    approval_status VARCHAR(12) NOT NULL
        CHECK (approval_status IN ('PENDING', 'APPROVED', 'REJECTED')),
    reviewer VARCHAR(80),
    CONSTRAINT ck_lab_approvals_93_reviewer_required
        CHECK (
            approval_status <> 'APPROVED'
            OR reviewer IS NOT NULL
        )
);
~~~

Khi `approval_status = 'APPROVED'`, biểu thức bên trái `OR` là FALSE; vì vậy `reviewer IS NOT NULL` phải là TRUE. Với trạng thái `PENDING` hoặc `REJECTED`, `reviewer` được phép là `NULL`.

Nếu tên người duyệt phải có nội dung, có thể bổ sung kiểm tra chuỗi rỗng hoặc chuẩn hóa từ ứng dụng. Trường hợp này cho thấy ý nghĩa **bắt buộc** có thể là quy tắc cho toàn bộ cột hoặc chỉ là quy tắc trên **một nhóm hàng**.

## 10. NOT NULL ở database và kiểm tra đầu vào ở ứng dụng

Ví dụ một API nhận yêu cầu tạo người dùng:

~~~json
{
  "username": "an",
  "email": null,
  "displayName": "An"
}
~~~

Ứng dụng có thể kiểm tra sớm và trả thông báo dễ hiểu như “Email là thông tin bắt buộc”. Nhưng nếu lỗi kiểm tra ứng dụng bị bỏ qua, dữ liệu đi từ một script khác hoặc một dịch vụ khác, ràng buộc `NOT NULL` ở database vẫn bảo vệ được bất biến của bảng.

Có thể phân biệt ba lớp:

| Lớp | Vai trò | Ví dụ |
| --- | --- | --- |
| Giao diện người dùng | Hướng dẫn nhập, báo lỗi ngay khi điền form | Trường email có ký hiệu bắt buộc |
| API / nghiệp vụ | Giải thích điều kiện đầu vào và quy tắc theo ngữ cảnh | Tên đăng nhập không được toàn dấu cách |
| Database / schema | Bảo vệ quy tắc dữ liệu cốt lõi trong mọi đường ghi | `email NOT NULL`, `UNIQUE`, `CHECK`, `FOREIGN KEY` |

Thực tế, một trường trong JSON có thể **vắng mặt**, được gửi tường minh là `null` hoặc chứa chuỗi rỗng. Lớp ánh xạ dữ liệu của ứng dụng quyết định cách ba trường hợp đó trở thành giá trị được gửi xuống SQL. Nếu ứng dụng tự chèn chuỗi rỗng thay cho `NULL`, database có thể chấp nhận mặc dù người dùng chưa nhập dữ liệu hữu ích. Nếu ứng dụng luôn liệt kê `status = NULL` trong lệnh chèn, `DEFAULT 'PENDING'` sẽ không được dùng.

Khi bắt gặp lỗi `NOT NULL`, hãy xác định nguồn phát sinh giá trị `NULL` thực tế: client bỏ cột, mapper gán `null`, câu `UPDATE` làm mất giá trị, hay migration chưa chuẩn bị dữ liệu. **Sửa dữ liệu đầu vào và quy tắc ở đúng lớp**, thay vì tự ý bỏ ràng buộc để làm lỗi biến mất.

## 11. Khác biệt giữa một số hệ quản trị SQL

Các hệ quản trị chủ yếu cùng hỗ trợ khái niệm cột `NOT NULL`, nhưng cú pháp thay đổi cột và một số quy tắc giá trị khác nhau.

| Hệ quản trị | Khai báo khi tạo bảng | Cách đổi cột đang có thành NOT NULL (điển hình) | Lưu ý |
| --- | --- | --- | --- |
| PostgreSQL | `name VARCHAR(50) NOT NULL` | `ALTER TABLE t ALTER COLUMN name SET NOT NULL;` | Dữ liệu cũ có NULL phải được xử lý trước; có `information_schema.columns` |
| MySQL | `name VARCHAR(50) NOT NULL` | `ALTER TABLE t MODIFY COLUMN name VARCHAR(50) NOT NULL;` | `MODIFY COLUMN` cần mô tả lại định nghĩa cột phù hợp; hành vi phụ thuộc phiên bản/SQL mode |
| SQL Server | `name VARCHAR(50) NOT NULL` | `ALTER TABLE t ALTER COLUMN name VARCHAR(50) NOT NULL;` | Cần chỉ rõ kiểu cột; dữ liệu NULL có sẵn ngăn chuyển đổi |
| SQLite | `name TEXT NOT NULL` | Thường phải dựng lại bảng để thay đổi ràng buộc của cột cũ | `ALTER TABLE` hỗ trợ một số thao tác giới hạn; quy trình migration cần sao chép và xác minh dữ liệu |
| Oracle | `name VARCHAR2(50) NOT NULL` | `ALTER TABLE t MODIFY (name NOT NULL);` | Chuỗi ký tự rỗng thường được coi là NULL, nên ví dụ về `''` khác PostgreSQL |

Ví dụ các lệnh trong bảng **không phải một script chạy chung**. Chọn cú pháp đúng theo cơ sở dữ liệu và phiên bản đang sử dụng.

Riêng với MySQL, SQL mode và thiết kế mặc định có thể ảnh hưởng việc xử lý một số giá trị thiếu/không hợp lệ. Không dựa vào một cơ chế tự điền giá trị hoặc cảnh báo của chế độ tương thích để thay cho định nghĩa dữ liệu rõ ràng. Với SQLite, ràng buộc `PRIMARY KEY` trên bảng rowid thông thường có một số ngoại lệ lịch sử liên quan `NULL`; nếu cần bảo đảm định danh cấm NULL trong mọi trường hợp, kiểm tra kiểu bảng và khai báo cụ thể.

## 12. Bài tập thực hành và đáp án

Giả sử bảng `lab_registrations_93` vẫn ở trạng thái sau bước khởi tạo với ba người dùng An, Bình và Chi. Hãy dự đoán kết quả **trước khi chạy**, nhất là các câu lệnh có thể thay đổi dữ liệu. Với lệnh thử nghiệm có tác động, có thể dùng database test riêng và `ROLLBACK` khi phù hợp.

### Bài 1 — Phân loại cột bắt buộc

Cho DDL:

~~~sql
CREATE TABLE lab_bookings_93 (
    booking_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    customer_note TEXT,
    seats INTEGER NOT NULL DEFAULT 1
);
~~~

Cột nào không thể nhận `NULL`? `customer_note` có thể nhận `NULL` không? Nếu chỉ chèn `booking_id` và `customer_name`, `seats` nhận giá trị gì?

**Đáp án:** `booking_id` không được `NULL` do khóa chính; `customer_name` và `seats` có `NOT NULL`; `customer_note` có thể `NULL`. Nếu bỏ `seats`, nó nhận `DEFAULT 1`.

### Bài 2 — Vì sao INSERT bị từ chối?

~~~sql
INSERT INTO lab_registrations_93 (username, email, status)
VALUES ('nam', 'nam@example.test', NULL);
~~~

**Đáp án:** cột `status` là `NOT NULL`. Dù có `DEFAULT 'PENDING'`, một giá trị `NULL` **tường minh** vẫn vi phạm ràng buộc. Có thể bỏ cột `status` hoặc viết `DEFAULT` thay cho `NULL`.

### Bài 3 — NULL khác chuỗi rỗng ra sao?

~~~sql
SELECT
    COUNT(*) FILTER (WHERE display_name IS NULL) AS so_null,
    COUNT(*) FILTER (WHERE display_name = '') AS so_rong
FROM lab_registrations_93;
~~~

**Đáp án:** `so_null = 1` (An), `so_rong = 1` (Bình), nếu bảng chưa bị thay đổi. `display_name IS NOT NULL` vẫn chọn cả Bình vì chuỗi rỗng không phải `NULL` trong PostgreSQL.

### Bài 4 — Thêm ràng buộc cho dữ liệu đã tồn tại

Bảng `lab_tasks_legacy_93` có một hàng `task_status IS NULL`. Có thể chạy ngay `ALTER COLUMN task_status SET NOT NULL` không? Nếu nghiệp vụ xác nhận tất cả trạng thái thiếu phải trở thành `PENDING`, cần làm gì?

**Đáp án:** Không thể thêm ràng buộc khi còn hàng vi phạm. Cần kiểm tra các hàng `NULL`, cập nhật đúng quy tắc nghiệp vụ, xác nhận không còn hàng `NULL` rồi chạy `ALTER TABLE ... ALTER COLUMN ... SET NOT NULL`. Tùy nhu cầu mới thêm `DEFAULT 'PENDING'` cho các thao tác tương lai.

### Bài 5 — Chọn ràng buộc theo yêu cầu

Một bảng tài khoản có yêu cầu:

1. `email` luôn phải có giá trị.
2. Hai tài khoản không được dùng cùng email.
3. `age` có thể chưa được biết; khi đã có giá trị thì không được âm.
4. `username` không được chứa toàn dấu cách.

**Đáp án tham khảo (PostgreSQL):**

~~~sql
CREATE TABLE lab_accounts_checked_93 (
    account_id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email VARCHAR(150) NOT NULL UNIQUE,
    age INTEGER CHECK (age >= 0),
    username VARCHAR(40) NOT NULL
        CHECK (length(btrim(username)) > 0)
);
~~~

`age` không `NOT NULL` vì yêu cầu cho phép chưa biết; `CHECK (age >= 0)` kiểm tra những giá trị được cung cấp. `username` cần cả `NOT NULL` và `CHECK` để tránh NULL lẫn chuỗi rỗng/toàn khoảng trắng thông thường.

### Bài 6 — Điều kiện bắt buộc theo trạng thái

Yêu cầu: “Khi `order_status = 'SHIPPED'` thì `shipped_at` phải khác `NULL`; các trạng thái khác được phép chưa có thời gian giao hàng.” Có nên đặt `shipped_at NOT NULL` cho mọi hàng không?

**Đáp án:** Không, vì điều đó sẽ cấm `NULL` ở cả những đơn hàng chưa giao. Có thể đặt `order_status NOT NULL` và viết ràng buộc điều kiện:

~~~sql
CHECK (
    order_status <> 'SHIPPED'
    OR shipped_at IS NOT NULL
)
~~~

Quy tắc này kiểm tra sự có mặt của ngày giao hàng khi trạng thái là `SHIPPED`. Nếu còn yêu cầu về thời gian hoặc các bước chuyển trạng thái, cần bổ sung quy tắc phù hợp.

## 13. Những điểm cần ghi nhớ

- **`NOT NULL` bảo đảm một cột không chứa `NULL`** trong các hàng hợp lệ, áp dụng khi tạo mới và cập nhật dữ liệu.
- **`NULL` khác `''`, `0` và `FALSE`** trong PostgreSQL. Muốn kiểm tra nội dung chuỗi, định dạng hoặc miền giá trị, cần quy tắc riêng như `CHECK` và kiểm tra nghiệp vụ.
- **`DEFAULT` và `NOT NULL` có hai vai trò khác nhau.** Bỏ cột hoặc dùng `DEFAULT` có thể kích hoạt giá trị mặc định; gửi `NULL` tường minh vẫn bị chặn nếu cột `NOT NULL`.
- **`PRIMARY KEY` bao hàm yêu cầu không `NULL`; `UNIQUE` và `FOREIGN KEY` không nhất thiết khiến cột tự trở thành bắt buộc.**
- **Bổ sung `NOT NULL` cho bảng đang có dữ liệu phải xử lý hàng `NULL` trước.** Cần thống nhất ý nghĩa dữ liệu thay thế; không tự điền giá trị giả để vượt ràng buộc.
- **Ứng dụng và database nên cùng thực thi ý nghĩa “bắt buộc” ở các lớp phù hợp.** Ứng dụng đưa ra thông báo gần với người dùng; schema bảo vệ những bất biến cơ bản của dữ liệu.

Khi thiết kế một cột, hãy tự hỏi: **“Giá trị này có thể chưa được biết không? Nếu không thể thiếu, quy tắc chỉ là khác NULL hay còn cần nội dung, phạm vi và quan hệ hợp lệ?”** Trả lời rõ hai phần đó sẽ giúp chọn đúng `NOT NULL` và những ràng buộc đi kèm.
