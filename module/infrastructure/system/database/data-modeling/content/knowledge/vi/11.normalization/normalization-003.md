# Dạng chuẩn thứ hai và loại bỏ phụ thuộc bộ phận vào khóa ứng viên

**Dạng chuẩn thứ hai (Second Normal Form, 2NF)** giúp loại bỏ một nguồn dư thừa điển hình trong mô hình quan hệ: thuộc tính mô tả **chỉ một phần của khóa ứng viên** nhưng lại được lưu trên mọi hàng có khóa đầy đủ. Khi dữ liệu phát triển, thiết kế như vậy buộc ứng dụng cập nhật nhiều bản sao của cùng một sự thật và có thể gây bất thường khi thêm, sửa hoặc xóa.

Trong quy trình chuyển yêu cầu nghiệp vụ thành mô hình dữ liệu, 2NF hướng người thiết kế trả lời hai câu hỏi: **điều gì xác định duy nhất một bản ghi** và **thuộc tính này thật sự mô tả toàn bộ bản ghi hay chỉ một thực thể tham gia vào bản ghi**? Bài học này trình bày cách xác định khóa ứng viên, nhận diện phụ thuộc bộ phận, phân rã bảng có thể kiểm chứng và phân biệt 2NF với các dạng chuẩn cao hơn.

## 1. Tình huống: một hàng đăng ký học chứa thông tin của ba đối tượng

Một hệ thống đào tạo có các quy tắc nghiệp vụ:

- Mỗi học viên có một **student_id** ổn định và tên hiện hành.
- Mỗi khóa học có một **course_id** ổn định và tên khóa học hiện hành.
- Một học viên có thể đăng ký nhiều khóa; một khóa có nhiều học viên.
- Trong ví dụ này, một học viên đăng ký một khóa **tối đa một lần**.
- Điểm số thuộc về **lần đăng ký của một học viên vào một khóa**, có thể chưa được chấm.
- Học viên và khóa học có thể được tạo trước khi có đăng ký.

Thiết kế ban đầu đặt mọi thông tin trong bảng **enrollments_flat**:

| student_id | student_name | course_id | course_title | score |
| --- | --- | --- | --- | ---: |
| S01 | An | C10 | SQL căn bản | 9 |
| S01 | An | C20 | Java căn bản | 8 |
| S02 | Bình | C10 | SQL căn bản | 7 |
| S03 | Chi | C30 | Thiết kế dữ liệu | 9 |

**Grain** của bảng là *một cặp học viên–khóa học*. Khóa ứng viên tự nhiên là **(student_id, course_id)** vì một cặp chỉ xuất hiện tối đa một lần, còn riêng **student_id** hoặc **course_id** có thể xuất hiện nhiều lần.

Một lược đồ minh họa (PostgreSQL):

~~~sql
CREATE TABLE enrollments_flat (
    student_id    VARCHAR(10) NOT NULL,
    student_name  VARCHAR(100) NOT NULL,
    course_id     VARCHAR(10) NOT NULL,
    course_title  VARCHAR(150) NOT NULL,
    score         NUMERIC(4, 2)
                  CHECK (score BETWEEN 0 AND 10),
    PRIMARY KEY (student_id, course_id)
);

INSERT INTO enrollments_flat
    (student_id, student_name, course_id, course_title, score)
VALUES
    ('S01', 'An',   'C10', 'SQL căn bản',       9),
    ('S01', 'An',   'C20', 'Java căn bản',      8),
    ('S02', 'Bình', 'C10', 'SQL căn bản',       7),
    ('S03', 'Chi',  'C30', 'Thiết kế dữ liệu',  9);
~~~

Các ô đều chứa giá trị đơn lẻ, có khóa chính và không có danh sách nhét trong một ô. Bảng có thể đáp ứng cách thực hành **1NF** nhưng vẫn chưa đạt **2NF** vì thông tin học viên và khóa học được chép lại theo từng đăng ký.

## 2. Khóa ứng viên, thuộc tính nguyên tố và phụ thuộc hàm

Để đánh giá 2NF chính xác, cần phân biệt các khái niệm sau.

| Khái niệm | Ý nghĩa | Ví dụ ở bảng đăng ký |
| --- | --- | --- |
| **Siêu khóa (superkey)** | Tập thuộc tính đủ để xác định duy nhất một hàng | **(student_id, course_id)** hoặc tập lớn hơn có thêm **score** |
| **Khóa ứng viên (candidate key)** | Siêu khóa **tối thiểu**: bỏ bất kỳ thuộc tính nào khỏi khóa đều mất khả năng định danh duy nhất | **(student_id, course_id)** |
| **Khóa chính (primary key)** | Một khóa ứng viên được chọn làm định danh chính trong lược đồ | **PRIMARY KEY (student_id, course_id)** |
| **Thuộc tính nguyên tố (prime attribute)** | Thuộc **ít nhất một** khóa ứng viên | **student_id**, **course_id** |
| **Thuộc tính không nguyên tố (non-prime attribute)** | Không thuộc **bất kỳ** khóa ứng viên nào | **student_name**, **course_title**, **score** |
| **Phụ thuộc hàm X → Y** | Mỗi giá trị X xác định tối đa một giá trị Y trong mọi trạng thái hợp lệ của quan hệ | **student_id → student_name** |

Khóa ứng viên phải được suy ra từ **quy tắc nghiệp vụ**, không chỉ từ việc các dòng dữ liệu hiện tại tình cờ khác nhau. Ví dụ, nếu hệ thống cho phép học viên học lại cùng khóa nhiều lần, **(student_id, course_id)** không còn đủ định danh đăng ký; khi đó có thể cần **attempt_no**, **enrollment_id** hoặc một khái niệm lần học khác trong khóa.

### 2.1. Những phụ thuộc hàm trong ví dụ

Theo yêu cầu nghiệp vụ:

~~~text
student_id                  -> student_name
course_id                   -> course_title
(student_id, course_id)     -> score
~~~

Hình dung:

~~~mermaid
flowchart TD
    K["Khóa ứng viên: (student_id, course_id)"]
    S["student_id"]
    C["course_id"]
    N["student_name"]
    T["course_title"]
    G["score"]
    K --> S
    K --> C
    K --> G
    S --> N
    C --> T
~~~

**score** là thuộc tính của lần đăng ký: không thể biết điểm chỉ từ học viên hoặc chỉ từ khóa học. Ngược lại, **student_name** được xác định bởi **student_id** mà không cần **course_id**; **course_title** được xác định bởi **course_id** mà không cần **student_id**.

Đây chính là dấu hiệu của **phụ thuộc bộ phận**.

### 2.2. Phụ thuộc đầy đủ và phụ thuộc bộ phận

Giả sử **K** là một khóa ứng viên và **A** là thuộc tính không nguyên tố.

- **A phụ thuộc hàm đầy đủ vào K** nếu **K → A** và **không có tập con thực sự nào của K** cũng xác định A.
- **A phụ thuộc hàm bộ phận vào K** nếu tồn tại tập con thực sự **X ⊂ K** sao cho **X → A**.

Với khóa **K = (student_id, course_id)**:

| Thuộc tính | Phụ thuộc quan sát theo quy tắc nghiệp vụ | Kết luận |
| --- | --- | --- |
| **student_name** | **student_id → student_name** | Phụ thuộc bộ phận vào K |
| **course_title** | **course_id → course_title** | Phụ thuộc bộ phận vào K |
| **score** | Cần cả **student_id** lẫn **course_id** để xác định | Phụ thuộc đầy đủ vào K |

Không đủ để nói “khóa đầy đủ xác định mọi cột”, vì tính chất đó vốn đúng đối với khóa. Cần thử **bỏ lần lượt các thành phần của khóa** và xem phần còn lại có tiếp tục xác định thuộc tính đang xét hay không.

## 3. Định nghĩa 2NF và điều kiện áp dụng

Một quan hệ ở **2NF** khi:

1. Quan hệ ở **dạng chuẩn thứ nhất (1NF)**.
2. **Mọi thuộc tính không nguyên tố phụ thuộc hàm đầy đủ vào mọi khóa ứng viên**; nói cách khác, không có thuộc tính không nguyên tố nào phụ thuộc hàm vào **một tập con thực sự** của một khóa ứng viên.

Cụm **mọi khóa ứng viên** rất quan trọng. Đánh giá chỉ dựa vào khóa chính có thể bỏ sót một khóa ứng viên khác. Tương tự, 2NF nói cụ thể về **thuộc tính không nguyên tố**: không phải mọi phụ thuộc giữa các thuộc tính nguyên tố đều tự động là vi phạm 2NF.

### 3.1. Vì sao bảng có khóa ghép thường cần được xem xét kỹ?

Nếu một quan hệ chỉ có các khóa ứng viên **đơn thuộc tính**, không có tập con thực sự **không rỗng** của khóa để tạo phụ thuộc bộ phận thông thường; quan hệ đã ở 1NF sẽ thỏa 2NF theo cách đánh giá phổ biến. Những trường hợp có phụ thuộc từ tập rỗng (thuộc tính hằng) cần được xét theo định nghĩa hình thức riêng, nhưng không phải tình huống nghiệp vụ thường gặp.

Với khóa ghép, dữ liệu trong bảng có thể đang mô tả **từng phía của quan hệ** cùng lúc với **bản thân mối quan hệ**. Khi đó nên kiểm tra các thuộc tính thuộc về từng thực thể.

**Lưu ý:** khóa chính một cột **không đủ** để kết luận 2NF nếu bảng còn một **khóa ứng viên ghép khác**. Phần 6 sẽ minh họa.

### 3.2. Ba bất thường do phụ thuộc bộ phận

Trong **enrollments_flat**, thử ba thay đổi nghiệp vụ:

**Sửa tên học viên:** An đổi tên hiển thị thành An Nguyễn. Nếu chỉ cập nhật hàng của khóa C10, cùng **student_id = S01** tồn tại hai tên khác nhau.

~~~sql
BEGIN;

UPDATE enrollments_flat
SET student_name = 'An Nguyễn'
WHERE student_id = 'S01' AND course_id = 'C10';

SELECT student_id, course_id, student_name
FROM enrollments_flat
WHERE student_id = 'S01'
ORDER BY course_id;

ROLLBACK;
~~~

**Thêm khóa học chưa có học viên:** không có cách thêm thông tin **C40 – Phân tích dữ liệu** mà không tạo hàng đăng ký giả, vì bảng bắt buộc có **student_id**.

**Xóa đăng ký cuối cùng:** khi xóa hàng **(S03, C30)**, hệ thống mất luôn thông tin tên khóa **C30 – Thiết kế dữ liệu** nếu không có bản sao bên ngoài bảng.

Vấn đề không nằm ở tên cột hoặc việc viết câu SQL ngắn hay dài. **Một sự thật thuộc học viên hoặc khóa học đang phụ thuộc vào vòng đời của bản ghi đăng ký**, khiến cập nhật và xóa có thể tác động ngoài ý muốn.

## 4. Phân rã để loại bỏ phụ thuộc bộ phận

Cách khắc phục là đưa từng sự thật về bảng mang **đúng grain**:

- **students**: một hàng cho mỗi học viên, sở hữu **student_name**.
- **courses**: một hàng cho mỗi khóa học, sở hữu **course_title**.
- **enrollments**: một hàng cho mỗi cặp học viên–khóa học, sở hữu **score**.

~~~mermaid
erDiagram
    STUDENTS ||--o{ ENROLLMENTS : "đăng ký"
    COURSES  ||--o{ ENROLLMENTS : "có học viên"
    STUDENTS {
        varchar student_id PK
        varchar student_name
    }
    COURSES {
        varchar course_id PK
        varchar course_title
    }
    ENROLLMENTS {
        varchar student_id PK, FK
        varchar course_id PK, FK
        numeric score
    }
~~~

### 4.1. Lược đồ quan hệ

~~~sql
CREATE TABLE students (
    student_id   VARCHAR(10) PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE courses (
    course_id    VARCHAR(10) PRIMARY KEY,
    course_title VARCHAR(150) NOT NULL
);

CREATE TABLE enrollments (
    student_id VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    course_id VARCHAR(10) NOT NULL
        REFERENCES courses(course_id),
    score NUMERIC(4, 2)
        CHECK (score BETWEEN 0 AND 10),
    PRIMARY KEY (student_id, course_id)
);

INSERT INTO students (student_id, student_name) VALUES
    ('S01', 'An'),
    ('S02', 'Bình'),
    ('S03', 'Chi');

INSERT INTO courses (course_id, course_title) VALUES
    ('C10', 'SQL căn bản'),
    ('C20', 'Java căn bản'),
    ('C30', 'Thiết kế dữ liệu');

INSERT INTO enrollments (student_id, course_id, score) VALUES
    ('S01', 'C10', 9),
    ('S01', 'C20', 8),
    ('S02', 'C10', 7),
    ('S03', 'C30', 9);
~~~

**Khóa chính ghép** bảo đảm mỗi học viên chỉ đăng ký một lần vào cùng khóa theo giả định của ví dụ. **Khóa ngoại** ngăn tạo đăng ký cho học viên hoặc khóa học chưa tồn tại. Cột **score** được phép **NULL** để biểu diễn đăng ký chưa có điểm; **CHECK** chặn điểm ngoài khoảng khi một giá trị điểm được cung cấp.

### 4.2. Các thao tác nghiệp vụ sau phân rã

**Sửa tên học viên đúng một nơi:**

~~~sql
UPDATE students
SET student_name = 'An Nguyễn'
WHERE student_id = 'S01';
~~~

**Tạo khóa mới chưa có học viên:**

~~~sql
INSERT INTO courses (course_id, course_title)
VALUES ('C40', 'Phân tích dữ liệu');
~~~

**Xóa một đăng ký, vẫn giữ khóa học:**

~~~sql
DELETE FROM enrollments
WHERE student_id = 'S03' AND course_id = 'C30';

SELECT course_id, course_title
FROM courses
WHERE course_id = 'C30';
-- C30 vẫn tồn tại, dù không còn đăng ký.
~~~

**Đọc lại thông tin theo dạng bảng gộp cho giao diện:**

~~~sql
SELECT
    e.student_id,
    s.student_name,
    e.course_id,
    c.course_title,
    e.score
FROM enrollments AS e
JOIN students AS s
    ON s.student_id = e.student_id
JOIN courses AS c
    ON c.course_id = e.course_id
ORDER BY e.student_id, e.course_id;
~~~

Trong hệ thống thật, ứng dụng có thể cần các chỉ mục theo truy vấn. Ví dụ, **PRIMARY KEY (student_id, course_id)** hỗ trợ tốt việc tìm các đăng ký của một học viên. Nếu thường xuyên lấy danh sách học viên theo khóa, có thể cân nhắc:

~~~sql
CREATE INDEX idx_enrollments_course
ON enrollments (course_id, student_id);
~~~

Chỉ mục là quyết định **mô hình vật lý và hiệu năng** sau khi xác định đúng các quan hệ và ràng buộc; bản thân chỉ mục không sửa được một phụ thuộc bộ phận.

### 4.3. Vì sao phép phân rã này bảo toàn ý nghĩa?

Ba bảng lưu ba loại sự thật ở ba grain rõ ràng. Với các ràng buộc khóa ở trên, khi nối **enrollments → students** theo **student_id**, mỗi hàng đăng ký khớp đúng một học viên; khi nối tiếp **courses** theo **course_id**, mỗi hàng khớp đúng một khóa học. Vì vậy, với các đăng ký hợp lệ, phép nối tái tạo được thông tin của từng hàng đăng ký ban đầu mà không tự sinh thêm cặp đăng ký.

Các phụ thuộc hàm được bảo vệ trực tiếp:

~~~text
students:
    student_id -> student_name

courses:
    course_id -> course_title

enrollments:
    (student_id, course_id) -> score
~~~

Việc tách bảng cũng giữ được thông tin học viên hoặc khóa học chưa có đăng ký, một trạng thái mà bảng gộp không thể biểu diễn. Khi truy vấn muốn lấy **cả khóa chưa có học viên**, xuất phát từ **courses** và dùng **LEFT JOIN**:

~~~sql
SELECT
    c.course_id,
    c.course_title,
    COUNT(e.student_id) AS enrollment_count
FROM courses AS c
LEFT JOIN enrollments AS e
    ON e.course_id = c.course_id
GROUP BY c.course_id, c.course_title
ORDER BY c.course_id;
~~~

Kết quả có **C40** với **enrollment_count = 0**. Không được dùng **COUNT(*)** trong ví dụ này để đếm đăng ký vì phép **LEFT JOIN** vẫn tạo một hàng kết quả cho khóa chưa có đăng ký.

## 5. Nhận diện phụ thuộc bộ phận bằng quy tắc và dữ liệu

Nên bắt đầu bằng **mô tả nghiệp vụ**, sau đó mới xác nhận trên dữ liệu:

1. **Xác định grain:** một hàng trong bảng là một học viên, một khóa học, một cặp đăng ký hay một lần thi?
2. **Liệt kê khóa ứng viên:** các tập thuộc tính tối thiểu nào xác định duy nhất một hàng **trong mọi trạng thái hợp lệ**?
3. **Đánh dấu thuộc tính không nguyên tố:** cột nào không nằm trong bất kỳ khóa ứng viên nào?
4. **Viết phụ thuộc hàm:** ví dụ **student_id → student_name**, **course_id → course_title**.
5. **Thử tập con thực sự của mỗi khóa ứng viên:** chỉ dùng một phần khóa đã xác định được thuộc tính không nguyên tố chưa?
6. **Thiết kế bảng sở hữu thông tin:** giữ thuộc tính của từng thực thể trong bảng thực thể, giữ thuộc tính của mối quan hệ trong bảng liên kết.
7. **Kiểm tra ràng buộc và phép nối:** mỗi bảng có khóa, liên kết có khóa ngoại, các câu truy vấn nghiệp vụ vẫn đúng sau phân rã.

Có thể tìm **dấu hiệu bất nhất** trong bảng cũ:

~~~sql
-- Một student_id xuất hiện với nhiều student_name.
SELECT student_id, COUNT(DISTINCT student_name) AS name_count
FROM enrollments_flat
GROUP BY student_id
HAVING COUNT(DISTINCT student_name) > 1;

-- Một course_id xuất hiện với nhiều course_title.
SELECT course_id, COUNT(DISTINCT course_title) AS title_count
FROM enrollments_flat
GROUP BY course_id
HAVING COUNT(DISTINCT course_title) > 1;
~~~

Những truy vấn này tìm các trường hợp dữ liệu đã mâu thuẫn với phụ thuộc hàm dự kiến. **Không có hàng kết quả không chứng minh đạt 2NF**: một bảng có thể đang nhất quán tình cờ, nhưng cấu trúc vẫn cho phép phát sinh sai lệch khi nghiệp vụ thay đổi.

## 6. Bẫy thường gặp: chỉ xem khóa chính và bỏ sót khóa ứng viên

Giả sử nhóm phát triển thay khóa chính ghép bằng **enrollment_id** và thêm ràng buộc duy nhất cho cặp học viên–khóa học:

~~~sql
CREATE TABLE enrollments_with_id_flat (
    enrollment_id BIGINT PRIMARY KEY,
    student_id VARCHAR(10) NOT NULL,
    student_name VARCHAR(100) NOT NULL,
    course_id VARCHAR(10) NOT NULL,
    course_title VARCHAR(150) NOT NULL,
    score NUMERIC(4, 2),
    UNIQUE (student_id, course_id)
);
~~~

Theo giả định mỗi cặp học viên–khóa học chỉ đăng ký một lần, bảng này có **hai khóa ứng viên**:

- **(enrollment_id)**, khóa ứng viên đơn thuộc tính được chọn làm khóa chính.
- **(student_id, course_id)**, khóa ứng viên ghép được bảo vệ bằng **UNIQUE** và **NOT NULL**.

**student_name** vẫn phụ thuộc vào **student_id**; **course_title** vẫn phụ thuộc vào **course_id**. Đây là các phụ thuộc bộ phận của khóa ứng viên ghép **(student_id, course_id)**, nên bảng **chưa đạt 2NF** dù khóa chính là một cột.

Điều kiện **NOT NULL** rất quan trọng khi suy luận về khóa ứng viên từ **UNIQUE** trong SQL: một số hệ quản trị cho phép nhiều hàng có **NULL** ở những cột được khai báo **UNIQUE**; một ràng buộc như vậy không tương đương khóa ứng viên đầy đủ nếu chưa xử lý tính bắt buộc.

Việc thêm khóa thay thế (**surrogate key**) có ích cho định danh và tham chiếu, nhưng **không tự xóa các phụ thuộc nghiệp vụ**. Cần rà soát mọi khóa ứng viên, kể cả khóa tự nhiên được bảo vệ bởi các ràng buộc duy nhất.

## 7. Phân biệt 2NF với 1NF và 3NF

| Dạng chuẩn | Câu hỏi chính | Ví dụ vấn đề còn tồn tại |
| --- | --- | --- |
| **1NF** | Các giá trị có được biểu diễn đúng theo miền, tránh giấu tập phần tử cần quản lý độc lập trong một ô? | Bảng đăng ký có các giá trị scalar nhưng lặp **student_name** theo nhiều khóa |
| **2NF** | Mỗi thuộc tính **không nguyên tố** có phụ thuộc **đầy đủ vào mọi khóa ứng viên**? | Bảng đăng ký vi phạm do **student_id → student_name** và **course_id → course_title** |
| **3NF** | Còn phụ thuộc hàm làm thuộc tính không khóa phụ thuộc qua thuộc tính không khóa khác, hoặc các vi phạm điều kiện 3NF hình thức? | Bảng nhân viên có **employee_id → department_id → department_name** |

Ví dụ sau có khóa ứng viên một cột và, theo các quy tắc thông thường, đã ở **2NF** nhưng vẫn có phụ thuộc bắc cầu gây dư thừa:

~~~text
employees(
    employee_id PRIMARY KEY,
    employee_name,
    department_id,
    department_name
)

employee_id  -> employee_name, department_id
department_id -> department_name
~~~

**department_name** phụ thuộc vào **department_id**, không phải thông tin riêng của nhân viên. Việc lưu tên phòng ban ở từng hàng nhân viên có thể gây bất thường khi cập nhật. Tuy nhiên, **department_id** không phải tập con của khóa ứng viên **(employee_id)**; vì vậy đây không phải ví dụ về phụ thuộc **bộ phận vào khóa** mà là vấn đề được xét ở 3NF.

Nói chính xác hơn, dạng chuẩn 3NF đặt điều kiện trên các phụ thuộc hàm **X → A** không tầm thường: **X** phải là siêu khóa **hoặc** **A** là thuộc tính nguyên tố. Trong nhiều bài toán có khóa ứng viên đơn giản, điều đó thường được giảng dạy qua việc loại bỏ phụ thuộc bắc cầu giữa các thuộc tính không khóa.

### Dữ liệu lịch sử không nhất thiết là dữ liệu dư thừa sai

Giả sử mỗi dòng hàng của đơn bán có **unit_price_at_order**. Giá này thuộc về **thời điểm chốt đơn**, có thể khác giá sản phẩm đang niêm yết. Không được mặc định có phụ thuộc **product_id → unit_price_at_order** chỉ vì nhiều dòng bán cùng sản phẩm. Nếu giá tại giao dịch thay đổi theo khách hàng, chương trình ưu đãi hoặc thời điểm, đó là một sự thật của **dòng hàng**.

Tương tự, khi thiết kế document hoặc bảng phân tích đã làm phẳng, hệ thống có thể chủ động nhân bản dữ liệu để phục vụ truy vấn. Khi đó phải nêu **nguồn dữ liệu chuẩn, ý nghĩa thời gian và cách đồng bộ**. 2NF là tiêu chí đánh giá cấu trúc quan hệ theo phụ thuộc hàm, không phải lệnh cấm tuyệt đối mọi dữ liệu giống nhau hoặc mọi mô hình nhúng.

## 8. Bài tập áp dụng: chi tiết đơn hàng

Một hệ thống bán hàng lưu:

| order_id | order_date | product_id | product_name | quantity |
| --- | --- | --- | --- | ---: |
| O01 | 2026-11-22 | P10 | Bàn phím | 2 |
| O01 | 2026-11-22 | P20 | Chuột | 1 |
| O02 | 2026-11-22 | P10 | Bàn phím | 1 |

Giả định mỗi đơn có nhiều sản phẩm, mỗi sản phẩm xuất hiện **tối đa một lần trong một đơn**, **order_id** xác định ngày đặt và **product_id** xác định tên sản phẩm hiện hành.

**Câu hỏi:**

1. Grain của bảng là gì? Khóa ứng viên nào phù hợp?
2. Viết các phụ thuộc hàm quan trọng cho **order_date**, **product_name**, **quantity**.
3. Thuộc tính nào phụ thuộc bộ phận và vì sao?
4. Đề xuất các bảng để đạt 2NF, nêu khóa chính và khóa ngoại.
5. Nếu thêm khóa **order_item_id** làm khóa chính nhưng vẫn có **UNIQUE(order_id, product_id)**, có thể giữ **order_date** và **product_name** trong bảng gộp mà tự động đạt 2NF không?

<details>
<summary>Gợi ý lời giải</summary>

**Grain:** một sản phẩm trong một đơn hàng. Khóa ứng viên **(order_id, product_id)** với giả định mỗi sản phẩm chỉ xuất hiện một lần trong đơn.

~~~text
order_id                 -> order_date
product_id               -> product_name
(order_id, product_id)   -> quantity
~~~

**order_date** phụ thuộc riêng vào **order_id**, **product_name** phụ thuộc riêng vào **product_id**; cả hai là thuộc tính không nguyên tố và vi phạm 2NF. **quantity** phụ thuộc vào toàn bộ cặp khóa theo các giả định đã cho.

Có thể phân rã thành:

~~~text
orders(
    order_id PRIMARY KEY,
    order_date
)

products(
    product_id PRIMARY KEY,
    product_name
)

order_items(
    order_id REFERENCES orders(order_id),
    product_id REFERENCES products(product_id),
    quantity CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id)
)
~~~

Khóa **order_item_id** không tự giải quyết vi phạm nếu **(order_id, product_id)** vẫn là khóa ứng viên ghép. Cần phân rã các thuộc tính thuộc về đơn hàng và sản phẩm. Nếu nghiệp vụ cho phép lặp cùng sản phẩm nhiều dòng trong một đơn, cần sửa lại giả định định danh và cân nhắc **line_no** hoặc **order_item_id**.

</details>

## 9. Các lỗi tư duy cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Có **PRIMARY KEY** thì tự động đạt 2NF.” | Khóa chỉ bảo vệ định danh; phải xét các phụ thuộc hàm của thuộc tính không nguyên tố. |
| “Chỉ cần xét khóa chính.” | Định nghĩa 2NF xét **tất cả khóa ứng viên**, gồm cả khóa tự nhiên khác khóa chính. |
| “Mọi bảng có khóa ghép đều sai 2NF.” | Khóa ghép là bình thường; bảng có thể đạt 2NF khi thuộc tính không nguyên tố chỉ được xác định bởi **toàn bộ khóa**. |
| “Một thuộc tính được khóa đầy đủ xác định là đủ.” | Cần bảo đảm **không tập con thực sự nào của khóa** cũng xác định được thuộc tính ấy. |
| “Bảng có khóa đơn thì không thể gặp bất thường.” | Bảng có thể đạt 2NF nhưng vẫn gặp phụ thuộc bắc cầu, vấn đề 3NF hoặc ràng buộc khác. |
| “Chia bảng xong không cần khóa ngoại.” | Phân rã tạo các quan hệ cần được bảo vệ bằng khóa và ràng buộc tham chiếu. |
| “Kiểm tra vài dòng không có giá trị mâu thuẫn chứng minh đã chuẩn hóa.” | Phụ thuộc hàm phải được suy từ **quy tắc của mọi trạng thái hợp lệ**, không phải mẫu dữ liệu hiện tại. |

## 10. Kết luận

**2NF yêu cầu các thuộc tính không nguyên tố phụ thuộc đầy đủ vào mọi khóa ứng viên**. Nếu một thuộc tính chỉ được xác định bởi một phần của khóa ứng viên ghép, nó thường mô tả một thực thể hoặc khái niệm có vòng đời riêng. Chuyển thuộc tính đó sang bảng phù hợp giúp giảm bản sao, ngăn bất thường thêm/sửa/xóa và cho phép ràng buộc nghiệp vụ trực tiếp bằng khóa chính, khóa ngoại và kiểm tra miền giá trị.

Khi áp dụng vào thiết kế dữ liệu, hãy bắt đầu từ **grain, mọi khóa ứng viên và các phụ thuộc hàm**, rồi mới quyết định phân rã và tối ưu vật lý. Đạt 2NF giải quyết nhóm phụ thuộc bộ phận; vẫn cần tiếp tục xem xét **3NF, BCNF**, lịch sử dữ liệu và yêu cầu truy vấn để chọn cấu trúc có thể tiến hóa và kiểm chứng.
