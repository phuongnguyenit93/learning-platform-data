# Khóa ứng viên, khóa chính, khóa thay thế và khóa ghép trong SQL

Khi thiết kế cơ sở dữ liệu quan hệ, câu hỏi quan trọng không chỉ là “bảng này có những cột gì?” mà còn là **“dựa vào những cột nào có thể xác định chính xác một hàng?”**. Câu trả lời dẫn tới khái niệm *khóa* (key), nền tảng của việc chống trùng dữ liệu, tạo quan hệ giữa các bảng và bảo vệ tính toàn vẹn tham chiếu.

Ví dụ, bảng sinh viên có `student_id` do hệ thống cấp, `student_code` do trường cấp và `school_email` được quản lý theo quy tắc không trùng. Cả ba có thể xác định một sinh viên nếu nghiệp vụ bảo đảm tính duy nhất. Tuy nhiên, bảng chỉ chọn **một khóa chính**; các khóa còn lại vẫn có thể được ràng buộc duy nhất. Khi một sinh viên đăng ký nhiều học phần, một bản ghi đăng ký có thể cần **tổ hợp nhiều cột** để phân biệt.

Bài học phân biệt các khái niệm:

- **Khóa ứng viên (*candidate key*)**: một tập cột tối thiểu có thể xác định duy nhất mỗi hàng.
- **Khóa chính (*primary key*)**: một khóa ứng viên được chọn làm định danh chính thức của bảng.
- **Khóa thay thế**: thuật ngữ tiếng Việt có hai cách dùng cần tách bạch: *alternate key* (khóa ứng viên không được chọn làm khóa chính) và *surrogate key* (khóa nhân tạo do hệ thống sinh). Phần dưới giải thích cả hai và nêu rõ tiếng Anh để tránh nhầm.
- **Khóa ghép (*composite key*)**: khóa gồm từ hai cột trở lên; khóa ghép có thể là khóa ứng viên, khóa chính hoặc khóa thay thế theo nghĩa *alternate key*.

> Ví dụ DDL chủ yếu dùng PostgreSQL và cú pháp SQL phổ biến. Các cơ chế sinh khóa tự động, xử lý `NULL` trong `UNIQUE`, kiểu dữ liệu, collation và cách tạo chỉ mục có thể khác giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite.

## 1. “Xác định duy nhất” phải đúng cho mọi trạng thái dữ liệu hợp lệ

Xét bảng mẫu:

| student_id | student_code | school_email | full_name |
|---:|---|---|---|
| 101 | SV001 | an@school.example | Nguyễn An |
| 102 | SV002 | binh@school.example | Trần Bình |
| 103 | SV003 | chi@school.example | Lê Chi |

Trong dữ liệu hiện tại, các cột `student_id`, `student_code` và `school_email` đều khác nhau. Nhưng **việc dữ liệu mẫu tình cờ không trùng chưa đủ để kết luận một cột là khóa**.

Muốn xác định một khóa hợp lệ, cần có quy tắc bền vững của nghiệp vụ, chẳng hạn:

1. Mỗi sinh viên có đúng một `student_id`, không tái sử dụng cho người khác.
2. Mỗi sinh viên có một `student_code` bắt buộc và duy nhất trong toàn trường.
3. Trường bảo đảm `school_email` là bắt buộc và duy nhất tại cùng thời điểm, không được dùng chung; chính sách tái cấp phát cần được xem xét riêng.
4. `full_name` không duy nhất: hai người có thể cùng họ tên.

Nếu quy tắc 3 không đúng (một số sinh viên chưa có email, hoặc email có thể được cấp lại), `school_email` không còn là lựa chọn khóa ứng viên phù hợp theo ngữ nghĩa mong muốn. Một thuộc tính chỉ được coi là khóa khi **tính duy nhất và tính xác định** là quy tắc của mọi trạng thái hợp lệ, không chỉ của dữ liệu đang thấy.

Trong lý thuyết quan hệ, có thể diễn đạt một tập thuộc tính `K` xác định khóa theo phụ thuộc hàm `K → tất cả các thuộc tính của quan hệ`. Khi nói đến khóa ứng viên, còn cần yêu cầu *tối thiểu*, không chứa cột thừa.

## 2. Từ siêu khóa tới khóa ứng viên

### 2.1. Siêu khóa (*superkey*)

**Siêu khóa** là một tập một hoặc nhiều thuộc tính đủ để nhận diện duy nhất mỗi hàng trong mọi trạng thái hợp lệ của quan hệ.

Nếu `student_id` đã duy nhất thì cả `{student_id}` và `{student_id, full_name}` đều là siêu khóa. Nhưng siêu khóa thứ hai có một thành phần thừa: bỏ `full_name` vẫn đủ phân biệt sinh viên.

Có thể hình dung:

```text
Tất cả tập cột của bảng
    └─ Siêu khóa: xác định duy nhất một hàng
          └─ Khóa ứng viên: siêu khóa tối thiểu
                 └─ Khóa chính: một khóa ứng viên được chọn
```

Cây khái niệm này nói về quan hệ tập hợp giữa các loại khóa, không phải các cấp cấu trúc vật lý trong DBMS.

### 2.2. Khóa ứng viên (*candidate key*)

**Khóa ứng viên là một siêu khóa tối thiểu**: nó đủ để xác định duy nhất hàng và **không có tập con thực sự nào của nó còn là siêu khóa**.

Hai điều kiện cần kiểm tra:

- **Tính duy nhất**: không có hai hàng hợp lệ có cùng giá trị trên toàn bộ các cột của khóa.
- **Tính tối thiểu**: nếu bỏ bất kỳ cột nào, tập cột còn lại không còn bảo đảm xác định duy nhất hàng.

Trong ví dụ sinh viên, với các quy tắc ở phần 1, ba tập `{student_id}`, `{student_code}` và `{school_email}` đều là khóa ứng viên. Tập `{student_id, student_code}` là siêu khóa nhưng **không phải khóa ứng viên**, vì chỉ cần `student_id` là đủ.

**Khóa ứng viên không bắt buộc chỉ có một cột.** Nếu cần hai hoặc ba cột để xác định duy nhất hàng và không thể bỏ bớt cột nào, cả tổ hợp vẫn là một khóa ứng viên.

### 2.3. Ví dụ khóa ứng viên gồm hai cột

Giả sử một hệ thống đào tạo có nhiều cơ sở; mã học viên chỉ duy nhất **trong từng cơ sở**, không duy nhất trên toàn tổ chức:

| campus_id | student_code | full_name |
|---|---|---|
| HN | SV001 | Nguyễn An |
| HN | SV002 | Trần Bình |
| HCM | SV001 | Lê Chi |

- `student_code` không phải khóa: cả hai cơ sở có `SV001`.
- `campus_id` không phải khóa: một cơ sở có nhiều học viên.
- `(campus_id, student_code)` là **khóa ứng viên ghép** nếu nghiệp vụ bảo đảm mỗi cơ sở không cấp trùng mã học viên.

Tính tối thiểu được chứng minh bằng việc bỏ từng cột sẽ làm mất khả năng phân biệt một số hàng hợp lệ. Đó là bản chất của khóa ghép, không đơn thuần là việc ghép cho đủ nhiều cột.

## 3. Khóa chính (*primary key*): chọn một khóa ứng viên

**Khóa chính** là khóa ứng viên được chọn làm định danh chuẩn để nhận diện mỗi hàng trong bảng. Một bảng SQL khai báo **tối đa một ràng buộc `PRIMARY KEY`**, nhưng ràng buộc đó có thể gồm một hoặc nhiều cột.

Trong các DBMS thông dụng, `PRIMARY KEY` bảo đảm:

- Không hai hàng có cùng tổ hợp giá trị khóa.
- Mọi cột thuộc khóa chính đều **`NOT NULL`**.
- Bảng có một điểm tham chiếu rõ ràng cho các khóa ngoại.

Ví dụ PostgreSQL:

```sql
CREATE TABLE students (
    student_id BIGINT GENERATED ALWAYS AS IDENTITY,
    student_code VARCHAR(20) NOT NULL,
    school_email VARCHAR(200) NOT NULL,
    full_name VARCHAR(150) NOT NULL,

    CONSTRAINT pk_students PRIMARY KEY (student_id),
    CONSTRAINT uq_students_code UNIQUE (student_code),
    CONSTRAINT uq_students_email UNIQUE (school_email)
);
```

Ở đây:

- `student_id` là khóa chính.
- `student_code` là khóa ứng viên khác, được bảo vệ bằng `UNIQUE` và `NOT NULL`.
- `school_email` là khóa ứng viên khác nếu nghiệp vụ thực sự bảo đảm tính duy nhất, hiện diện và ổn định theo thời gian.
- `full_name` không phải khóa vì được phép trùng.

Có thể viết ngắn gọn `student_id BIGINT PRIMARY KEY` nếu muốn đặt ràng buộc ngay tại cột. Cú pháp `GENERATED ALWAYS AS IDENTITY` là một cách sinh số do DBMS quản lý; MySQL thường dùng `AUTO_INCREMENT`, SQL Server dùng `IDENTITY`. **Cơ chế sinh ID là cách tạo giá trị, còn `PRIMARY KEY` mới là quy tắc duy nhất và không `NULL`.**

### 3.1. Tiêu chí chọn khóa chính

Khi có nhiều khóa ứng viên, lựa chọn thường dựa trên:

| Tiêu chí | Câu hỏi |
|---|---|
| Ổn định | Giá trị có thường thay đổi khi nghiệp vụ thay đổi hay không? |
| Duy nhất | Có quy tắc rõ ràng ngăn trùng trong đúng phạm vi hay không? |
| Bắt buộc | Giá trị có luôn tồn tại trước khi tạo hàng hay không? |
| Độ dài | Giá trị khóa và các khóa ngoại lặp lại ở nhiều bảng có lớn không? |
| Dễ dùng | Ứng dụng có thể truyền/nhận khóa an toàn và nhất quán không? |
| Phạm vi | Khóa duy nhất toàn hệ thống, theo tổ chức, theo thời gian hay theo tenant? |
| Khả năng tham chiếu | Có nhiều bảng khác cần khóa ngoại tới hàng này không? |

Khóa chính là **lựa chọn thiết kế**, không nhất thiết phải là cột đầu tiên trong bảng hoặc cột có giá trị lớn nhất. Một mã nghiệp vụ ngắn, bất biến có thể là khóa chính tốt; một mã nghiệp vụ dài, dễ đổi có thể phù hợp làm khóa duy nhất bổ sung trong khi dùng khóa nhân tạo làm khóa chính.

### 3.2. Khóa chính và khả năng thay đổi

Giả sử dùng `school_email` làm khóa chính, rồi trường thay đổi tên miền email hoặc cho phép sinh viên đổi tên đăng nhập. Khi email đổi, các bảng tham chiếu tới khóa này có thể cần cập nhật đồng bộ. Các DBMS hỗ trợ hành vi `ON UPDATE` khác nhau và ứng dụng có thể còn lưu email trong cache, log hoặc đường dẫn.

Nếu dùng `student_id` ổn định làm khóa chính, email được cập nhật độc lập. Điều đó không khiến email hết quan trọng: nếu nghiệp vụ yêu cầu không trùng, phải **giữ ràng buộc `UNIQUE`** trên email.

## 4. “Khóa thay thế”: phân biệt *alternate key* và *surrogate key*

Thuật ngữ **khóa thay thế** trong tài liệu tiếng Việt đôi khi được dùng cho hai khái niệm tiếng Anh khác nhau. Chúng cần được phân biệt vì cách thiết kế và chức năng khác hẳn.

### 4.1. *Alternate key*: khóa ứng viên không được chọn làm khóa chính

Trong bộ thuật ngữ *candidate key – primary key – alternate key*, **alternate key** là một **khóa ứng viên còn lại**, sau khi đã chọn một khóa làm `PRIMARY KEY`. Có thể gọi rõ là *khóa ứng viên thay thế* hoặc *khóa phụ duy nhất*.

Ví dụ bảng `students`:

| Tập cột | Loại khóa |
|---|---|
| `{student_id}` | Candidate key được chọn làm primary key |
| `{student_code}` | Candidate key không được chọn → alternate key |
| `{school_email}` | Candidate key không được chọn → alternate key, nếu đảm bảo quy tắc nghiệp vụ |
| `{student_id, student_code}` | Superkey, không tối thiểu → không phải candidate key |

Trong SQL, không có từ khóa ràng buộc chuẩn `ALTERNATE KEY` tương ứng với `PRIMARY KEY`. Ta thường biểu diễn alternate key bằng **`UNIQUE` kết hợp `NOT NULL`** trên các cột cấu thành.

```sql
CREATE TABLE staff (
    staff_id BIGINT PRIMARY KEY,
    employee_code VARCHAR(30) NOT NULL UNIQUE,
    internal_email VARCHAR(200) NOT NULL UNIQUE
);
```

Nếu `staff_id` là khóa chính, cả `employee_code` và `internal_email` đều là alternate key khi được nghiệp vụ công nhận là định danh duy nhất, luôn có giá trị.

**Chú ý `NULL`:** trên PostgreSQL/MySQL/SQLite, `UNIQUE` thường vẫn cho phép nhiều `NULL`, nên một cột `UNIQUE` nhưng cho phép `NULL` không đủ để diễn đạt khóa ứng viên bắt buộc theo lý thuyết quan hệ. Các DBMS có hành vi `NULL` trong `UNIQUE` khác nhau, vì vậy cần xác định `NOT NULL` hoặc chính sách đặc thù tương ứng.

### 4.2. *Surrogate key*: khóa nhân tạo không mang ý nghĩa nghiệp vụ

**Surrogate key** là định danh nhân tạo do ứng dụng/DBMS cấp, ví dụ `BIGINT` tăng dần hoặc UUID được sinh bằng cơ chế phù hợp. Giá trị của nó được dùng để nhận diện hàng, không dùng để mã hóa tên khách hàng, ngày sinh, chi nhánh hay thông tin nghiệp vụ khác.

```sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code VARCHAR(30) NOT NULL UNIQUE,
    display_name VARCHAR(150) NOT NULL
);
```

Ở đây `customer_id` là **surrogate key** và đồng thời là **primary key**. `customer_code` là **natural/business candidate key** được giữ bằng `UNIQUE` và `NOT NULL`, nên là **alternate key** sau khi `customer_id` được chọn.

Có thể hiểu:

```text
customers
├─ customer_id    → surrogate key; đồng thời là primary key
└─ customer_code  → business/natural key; đồng thời là alternate key
```

Hai cách phân loại **không loại trừ nhau**. *Surrogate/natural* nói về **nguồn gốc, ý nghĩa của khóa**; *primary/alternate* nói về **vai trò sau khi lựa chọn từ các khóa ứng viên**.

| Thuật ngữ | Câu hỏi trả lời | Ví dụ |
|---|---|---|
| Candidate key | Tập cột nào xác định duy nhất và tối thiểu? | `student_code` |
| Primary key | Khóa ứng viên nào được chọn làm chuẩn? | `student_id` |
| Alternate key | Khóa ứng viên nào không được chọn? | `school_email` |
| Natural/business key | Khóa bắt nguồn từ quy tắc nghiệp vụ nào? | `customer_code` |
| Surrogate key | Khóa nào được tạo chỉ để định danh hàng? | `customer_id` |
| Composite key | Khóa có bao nhiêu cột? | `(order_id, line_no)` |

### 4.3. Lợi ích và đánh đổi của surrogate key

**Ưu điểm thường gặp:**

- Giá trị có thể giữ ổn định khi mã nghiệp vụ, email hay cấu trúc tổ chức thay đổi.
- `BIGINT` tương đối gọn trong nhiều khóa ngoại/chỉ mục.
- Dễ làm một định danh độc lập để giao tiếp giữa các thành phần.

**Đánh đổi cần hiểu:**

- Surrogate key chỉ chặn trùng **ID**, không tự chặn hai hàng cùng một thực thể nghiệp vụ. Nếu `customer_code` phải duy nhất, vẫn phải khai báo `UNIQUE (customer_code)`.
- Mã tăng tuần tự có thể dễ đoán; không được coi khóa khó đoán là thay thế cho xác thực và phân quyền.
- UUID cho phép phát sinh ID phân tán nhưng kích thước và thứ tự chèn có tác động đến chỉ mục và lưu trữ.
- Nếu tất cả truy vấn đều lọc theo mã nghiệp vụ, vẫn cần chỉ mục thích hợp trên mã đó; có surrogate key không giúp mọi truy vấn tự động nhanh hơn.

Không có quy tắc “bảng nào cũng phải có surrogate key”. Bảng liên kết với khóa ghép ổn định đôi khi không cần thêm ID riêng.

## 5. Khóa ghép (*composite key*): nhiều cột cùng xác định một hàng

**Khóa ghép** là khóa gồm **hai hoặc nhiều cột**. Từng cột riêng lẻ có thể bị trùng, nhưng **tổ hợp** phải duy nhất trong phạm vi cần quản lý.

Ví dụ, một sinh viên có thể đăng ký nhiều môn học; mỗi môn có nhiều sinh viên; cùng một môn có thể mở ở nhiều học kỳ. Giả sử nghiệp vụ chỉ cho phép **một bản ghi đăng ký cho một sinh viên, một môn, một học kỳ**. Khi đó:

```text
(student_id, course_id, semester_code) → một lần đăng ký học
```

Cả ba cột là thành phần cần thiết:

- Chỉ `student_id`: không duy nhất, một sinh viên học nhiều môn.
- Chỉ `course_id`: không duy nhất, một môn có nhiều sinh viên.
- `(student_id, course_id)`: chưa đủ nếu sinh viên đăng ký lại môn ở học kỳ khác.
- `(student_id, course_id, semester_code)`: duy nhất theo quy tắc đã nêu.

### 5.1. Ví dụ khóa chính ghép trong DDL

```sql
CREATE TABLE courses (
    course_id BIGINT PRIMARY KEY,
    course_name VARCHAR(150) NOT NULL
);

CREATE TABLE enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    semester_code VARCHAR(12) NOT NULL,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_enrollments
        PRIMARY KEY (student_id, course_id, semester_code),
    CONSTRAINT fk_enrollments_student
        FOREIGN KEY (student_id) REFERENCES students (student_id),
    CONSTRAINT fk_enrollments_course
        FOREIGN KEY (course_id) REFERENCES courses (course_id)
);
```

Bảng `enrollments` dùng khóa chính ghép; khóa chính này tự cấm `NULL` trên cả ba cột và cấm lặp toàn bộ tổ hợp.

Thử một số thao tác:

```sql
-- Giả sử student_id=101 và course_id=501 đã tồn tại.
INSERT INTO enrollments (student_id, course_id, semester_code)
VALUES (101, 501, '2026-FALL');

-- Được phép nếu có lại môn này trong học kỳ khác.
INSERT INTO enrollments (student_id, course_id, semester_code)
VALUES (101, 501, '2027-SPR');

-- Vi phạm khóa chính ghép vì tổ hợp đã tồn tại.
INSERT INTO enrollments (student_id, course_id, semester_code)
VALUES (101, 501, '2026-FALL');
```

**Quan trọng:** đoạn `INSERT` giả định đã tạo dòng sinh viên 101 và môn 501; nếu chưa có thì khóa ngoại sẽ từ chối trước. SQL thực thi vẫn cần dữ liệu cha hợp lệ. Trong hệ thống có nhiều lớp học phần/mã lớp, khóa có thể còn cần `section_id` hoặc một định danh lớp mở; không được tự gộp các đăng ký có ý nghĩa nghiệp vụ khác nhau.

### 5.2. Khóa ngoại tham chiếu khóa chính ghép

Nếu bảng `enrollment_grades` chứa điểm của từng lần đăng ký, khóa ngoại phải chứa **đủ các thành phần** của khóa được tham chiếu:

```sql
CREATE TABLE enrollment_grades (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    semester_code VARCHAR(12) NOT NULL,
    assessment_code VARCHAR(20) NOT NULL,
    score NUMERIC(5, 2),

    CONSTRAINT pk_enrollment_grades
        PRIMARY KEY (
            student_id,
            course_id,
            semester_code,
            assessment_code
        ),

    CONSTRAINT fk_grades_enrollment
        FOREIGN KEY (student_id, course_id, semester_code)
        REFERENCES enrollments (student_id, course_id, semester_code),

    CONSTRAINT ck_grades_score
        CHECK (score BETWEEN 0 AND 100)
);
```

Một điểm thành phần được nhận diện bằng kỳ đăng ký và `assessment_code`. Khi JOIN, cần nối **đủ toàn bộ khóa**:

```sql
SELECT
    e.student_id,
    e.course_id,
    e.semester_code,
    g.assessment_code,
    g.score
FROM enrollments AS e
JOIN enrollment_grades AS g
  ON g.student_id = e.student_id
 AND g.course_id = e.course_id
 AND g.semester_code = e.semester_code;
```

Nếu chỉ JOIN theo `student_id`, một điểm có thể bị ghép nhầm với nhiều đăng ký của cùng sinh viên, dẫn tới nhân số dòng và tổng hợp sai. **Khóa ghép yêu cầu người viết truy vấn hiểu đúng đơn vị của một hàng.**

### 5.3. Khóa ghép và chỉ mục

Ở nhiều DBMS, tạo `PRIMARY KEY` hoặc `UNIQUE` cũng tạo cấu trúc chỉ mục phục vụ tính duy nhất. Chỉ mục trên bộ cột `(student_id, course_id, semester_code)` thường hữu ích cho truy vấn bắt đầu bằng `student_id` hoặc `(student_id, course_id)`, nhưng một truy vấn chỉ lọc theo `course_id` có thể cần thêm chỉ mục riêng tùy DBMS, kế hoạch thực thi và phân bố dữ liệu.

Thứ tự cột trong chỉ mục ghép có thể ảnh hưởng đến khả năng dùng chỉ mục để lọc/sắp xếp, nhưng **thứ tự khai báo khóa không quyết định ý nghĩa của tính duy nhất của tập giá trị**. Hai tổ hợp `(student_id, course_id)` và `(course_id, student_id)` đều áp đặt cùng quy tắc không trùng về giá trị khi các cột tương ứng được đặt đúng tên; hiệu quả truy vấn và cách tham chiếu có thể khác.

Chọn thứ tự cột theo nhu cầu truy vấn thực tế và kiểm tra bằng công cụ như `EXPLAIN` trên DBMS mục tiêu. Không tạo thêm chỉ mục trùng lặp với chỉ mục đã có chỉ để “tăng tốc” một cách máy móc.

## 6. Khóa ghép cũng có thể là khóa thay thế (*alternate key*)

Không bắt buộc phải chọn khóa ghép làm `PRIMARY KEY`. Trong nhiều hệ thống đa khách thuê (*multi-tenant*), người dùng được nhận diện bằng ID nhân tạo nhưng tên đăng nhập chỉ duy nhất **trong từng tổ chức**:

```sql
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name VARCHAR(120) NOT NULL
);

CREATE TABLE tenant_accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    username VARCHAR(80) NOT NULL,
    display_name VARCHAR(120) NOT NULL,

    CONSTRAINT fk_tenant_accounts_tenant
        FOREIGN KEY (tenant_id) REFERENCES tenants (tenant_id),

    CONSTRAINT uq_tenant_accounts_username
        UNIQUE (tenant_id, username)
);
```

Giả sử:

| account_id | tenant_id | username |
|---:|---:|---|
| 501 | 10 | admin |
| 502 | 20 | admin |
| 503 | 10 | user01 |

- `account_id` là **khóa chính nhân tạo**.
- `(tenant_id, username)` là **khóa ứng viên ghép** nếu hai cột luôn có giá trị và nghiệp vụ cấm trùng trong mỗi tổ chức. Nó là **alternate key** vì không được chọn làm khóa chính.
- `username` một mình không duy nhất toàn hệ thống; hai tenant có thể cùng tên đăng nhập `admin`.
- Nếu thêm `UNIQUE (username)` cho toàn bảng, hệ thống sẽ chặn dữ liệu đúng của nhiều tenant.

Ví dụ truy vấn tìm người dùng phải mang đúng phạm vi:

```sql
SELECT account_id, display_name
FROM tenant_accounts
WHERE tenant_id = 10
  AND username = 'admin';
```

Trong ứng dụng thật, cần đặc biệt chú ý đến chính sách phân biệt chữ hoa/thường của `username`, chuẩn hóa Unicode và collation. Nếu nghiệp vụ coi `Admin` và `admin` là một tên, `UNIQUE (tenant_id, username)` chỉ bảo đảm điều đó khi cách so sánh của DBMS tương ứng với chính sách đã chọn.

## 7. Khóa tự nhiên hay khóa nhân tạo: lựa chọn bằng nghiệp vụ

**Natural key** (khóa tự nhiên) bắt nguồn từ dữ liệu có ý nghĩa bên ngoài DB, ví dụ mã quốc gia theo một tiêu chuẩn cụ thể, mã sản phẩm do doanh nghiệp quản lý hoặc tổ hợp `(tenant_id, username)`. **Surrogate key** được tạo chỉ để định danh hàng. Mỗi hướng đều hợp lý trong điều kiện khác nhau.

| Tiêu chí | Khóa tự nhiên/khóa nghiệp vụ | Khóa nhân tạo |
|---|---|---|
| Ý nghĩa | Có thể hiểu qua quy tắc nghiệp vụ | Không mang ý nghĩa nghiệp vụ trực tiếp |
| Độ ổn định | Phụ thuộc quy định mã hóa, có thể đổi | Có thể giữ bất biến dễ dàng hơn |
| Số cột/độ dài | Có thể dài hoặc ghép nhiều cột | Thường một cột như BIGINT/UUID |
| Tránh trùng nghiệp vụ | Có thể trực tiếp bảo vệ quy tắc | Cần thêm UNIQUE cho khóa nghiệp vụ |
| Khóa ngoại | Có thể phải sao chép nhiều cột | Thường chỉ một ID |
| Tích hợp giữa hệ thống | Tiện nếu chuẩn mã chung thực sự ổn định | Cần cơ chế ánh xạ ID của các hệ thống |
| Nguy cơ hiểu sai | Mã có thể đổi phạm vi hoặc tái sử dụng | ID dễ bị coi nhầm là bí mật/quyền truy cập |

### Ví dụ tình huống

**Mã học phần**: nếu mã `CS101` có thể bị đổi sang `COMP101`, không nên giả định nó bất biến mãi mãi. Có thể dùng `course_id` làm khóa chính và `course_code` làm khóa duy nhất nghiệp vụ.

**Bảng liên kết nhiều-nhiều**: bảng `student_clubs(student_id, club_id)` có thể dùng `PRIMARY KEY (student_id, club_id)` nếu một sinh viên chỉ gia nhập một câu lạc bộ một lần ở trạng thái hiện tại. Nếu cần lưu lịch sử gia nhập nhiều lần, khóa ghép đó không còn phù hợp; có thể thêm `joined_at` nếu đó là thành phần phân biệt đáng tin cậy hoặc tạo `membership_id` và ràng buộc duy nhất theo quy tắc lịch sử.

**Mã chứng từ**: một số doanh nghiệp chỉ bảo đảm duy nhất theo `(branch_id, fiscal_year, document_number)`, không bảo đảm `document_number` toàn công ty. Đây là khóa nghiệp vụ ghép; khi chọn ID nhân tạo làm khóa chính, cần giữ ràng buộc `UNIQUE` trên bộ ba cột nếu quy tắc không trùng vẫn đúng.

## 8. Khóa và ràng buộc SQL: sự khác nhau cần nhớ

| Khái niệm/cú pháp | Đảm bảo chính | Có thể chứa NULL? | Ghi chú |
|---|---|---|---|
| Candidate key (khái niệm) | Duy nhất và tối thiểu theo quy tắc quan hệ | Không theo cách hiểu khóa nhận diện bắt buộc trong mô hình quan hệ truyền thống | Có thể là khóa một cột hoặc khóa ghép |
| `PRIMARY KEY` | Duy nhất, tất cả cột thuộc khóa không NULL | Không | Một ràng buộc PK cho mỗi bảng |
| `UNIQUE` | Không trùng theo ngữ nghĩa DBMS | Phụ thuộc DBMS/chính sách | Không mặc nhiên là khóa ứng viên nếu cột còn có thể NULL |
| `NOT NULL` | Bắt buộc có giá trị xác định | Không | Không ngăn trùng |
| `FOREIGN KEY` | Giá trị tham chiếu phải phù hợp khóa được tham chiếu, theo chính sách NULL và tham chiếu | Có thể, tùy định nghĩa | Không tạo duy nhất ở bảng con |
| Composite key | Tính duy nhất của **tổ hợp** nhiều cột | Phụ thuộc nó là PK hay UNIQUE và chính sách NULL | Không phải một loại ràng buộc SQL riêng |

Hai khác biệt thường bị nhầm:

**1. Khóa ngoại không có nghĩa là khóa chính.** Một cột `department_id` trong bảng nhân viên có thể lặp ở nhiều nhân viên, vẫn là `FOREIGN KEY` tham chiếu bảng phòng ban. Không nên thêm `UNIQUE` vào nó nếu mỗi phòng ban có nhiều nhân viên.

**2. `UNIQUE` không đồng nghĩa một candidate key đã được chứng minh tối thiểu.** Ví dụ `UNIQUE (student_id, school_email)` áp đặt tính duy nhất lên tổ hợp nhưng nếu `student_id` đã là PK, tổ hợp không tối thiểu. Nó là một siêu khóa về mặt logic và thường là ràng buộc dư thừa.

### 8.1. NULL trong khóa duy nhất ghép

Ví dụ PostgreSQL:

```sql
CREATE TABLE external_refs (
    tenant_id BIGINT NOT NULL,
    external_code VARCHAR(30),
    CONSTRAINT uq_external_refs UNIQUE (tenant_id, external_code)
);
```

Nếu thêm hai dòng `(10, NULL)`, PostgreSQL theo hành vi mặc định có thể chấp nhận cả hai; `UNIQUE` không bảo đảm mỗi tenant có tối đa một `external_code` “không biết”. Với cột thuộc candidate key nghiệp vụ, cách rõ ràng thường là `external_code NOT NULL` nếu mã bắt buộc.

PostgreSQL 15+ có tùy chọn `UNIQUE NULLS NOT DISTINCT` để coi các `NULL` không phân biệt khi xét duy nhất; SQL Server và Oracle lại có các quy tắc riêng. **Không suy ra hành vi cho tất cả DBMS chỉ từ một ví dụ PostgreSQL.**

### 8.2. Tham chiếu alternate key bằng khóa ngoại

Một khóa ngoại có thể tham chiếu khóa được bảo đảm duy nhất phù hợp, không nhất thiết bắt buộc tham chiếu khóa chính. Ví dụ:

```sql
CREATE TABLE shipping_labels (
    label_id BIGINT PRIMARY KEY,
    student_code VARCHAR(20) NOT NULL,
    CONSTRAINT fk_labels_student_code
        FOREIGN KEY (student_code)
        REFERENCES students (student_code)
);
```

Vì `students.student_code` có `UNIQUE` nên ví dụ PostgreSQL có thể tham chiếu trực tiếp đến cột đó. Nhưng cần cân nhắc tác động khi `student_code` thay đổi; tham chiếu theo `student_id` thường ổn định hơn khi mã sinh viên có thể sửa.

## 9. Những câu hỏi phải trả lời trước khi chốt khóa

### 9.1. Khóa duy nhất trong phạm vi nào?

Một số mã duy nhất **toàn hệ thống**, một số chỉ duy nhất theo công ty, chi nhánh, năm tài chính hoặc học kỳ. Viết thiếu phạm vi dẫn tới chặn bản ghi hợp lệ hoặc nhận diện nhầm hàng.

Ví dụ:

- `invoice_number` có thể trùng giữa hai chi nhánh.
- `(branch_id, fiscal_year, invoice_number)` có thể là một khóa ứng viên ghép.
- Nếu hai năm có cùng số hóa đơn tại một chi nhánh, `(branch_id, invoice_number)` không còn là khóa.

### 9.2. Một thực thể có thể nhận hai mã ở các thời điểm khác nhau không?

Khóa có thể ổn định trong phạm vi **trạng thái hiện tại** nhưng không ổn định trong lịch sử. Nếu số hợp đồng được phép tái sử dụng sau khi đóng hợp đồng, quy tắc `UNIQUE (contract_number)` toàn bảng có thể không hợp lý với dữ liệu lịch sử. Có thể cần thêm phạm vi hoặc dùng ID nhân tạo và ràng buộc trên các hợp đồng đang hiệu lực theo khả năng DBMS.

### 9.3. Dữ liệu đã tồn tại có bản ghi trùng không?

Trước khi thêm ràng buộc, có thể phát hiện trùng:

```sql
SELECT tenant_id, username, COUNT(*) AS duplicate_count
FROM tenant_accounts
GROUP BY tenant_id, username
HAVING COUNT(*) > 1;
```

Truy vấn này giúp phát hiện dữ liệu vi phạm quy tắc khi chưa có `UNIQUE`. Nếu ràng buộc đã tồn tại và được bảo vệ đầy đủ, truy vấn bình thường sẽ không trả về tổ hợp trùng. Với cột có `NULL`, phải xác định liệu `NULL` có được phép và có tính là trường hợp vi phạm theo nghiệp vụ không.

### 9.4. Cần giữ lịch sử hay chỉ trạng thái hiện tại?

Một khóa phù hợp cho bảng trạng thái hiện tại có thể không phù hợp cho bảng sự kiện lịch sử. Ví dụ `(employee_id, role_id)` đủ cho danh sách vai trò hiện tại, nhưng nhân viên có thể được cấp rồi thu hồi cùng vai trò nhiều lần. Bảng lịch sử cần định danh riêng cho **mỗi lần cấp** hoặc một khóa ghép có thành phần thời điểm/số thứ tự đủ ổn định và duy nhất.

## 10. Những lỗi thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách thiết kế phù hợp |
|---|---|---|
| Xem cột chưa thấy trùng là candidate key | Quy tắc không được bảo vệ khi dữ liệu tăng | Chứng minh quy tắc nghiệp vụ và khai báo ràng buộc |
| Nhầm siêu khóa với khóa ứng viên | Tưởng khóa có cột thừa là tối thiểu | Thử loại từng cột và kiểm tra tính duy nhất về mặt nghiệp vụ |
| Nghĩ bảng phải có nhiều primary key vì có nhiều mã duy nhất | Vi phạm cấu trúc PK, khó xác định định danh chính thức | Một PK; các candidate key khác dùng UNIQUE phù hợp |
| Dùng `UNIQUE` cho cột tùy chọn nhưng xem như khóa bắt buộc | Hành vi NULL phụ thuộc DBMS | Kết hợp NOT NULL khi dữ liệu bắt buộc |
| Chỉ khai báo ID nhân tạo mà bỏ UNIQUE trên mã nghiệp vụ | Dữ liệu trùng khách hàng/mã chứng từ vẫn được ghi | Giữ ràng buộc riêng cho khóa nghiệp vụ |
| Dùng email/tên/điện thoại làm PK khi dễ đổi hoặc không thực sự duy nhất | Cập nhật khóa ngoại, khó duy trì tính ổn định | Đánh giá phạm vi, tính bất biến; cân nhắc surrogate PK |
| Dùng `PRIMARY KEY (student_id, course_id)` khi sinh viên có thể học lại môn | Không lưu được đăng ký học kỳ sau | Thêm thành phần kỳ học hoặc định danh lần đăng ký |
| JOIN chỉ một phần của khóa ghép | Nhân dòng, gán nhầm dữ liệu | JOIN đủ bộ cột hoặc dùng FK/ID đã chuẩn hóa |
| Thêm UNIQUE toàn hệ thống cho `username` đa tenant | Chặn tên hợp lệ ở tenant khác | `UNIQUE (tenant_id, username)` |
| Đặt quá nhiều chỉ mục lặp khóa đã có | Tốn lưu trữ và chi phí ghi | Kiểm tra chỉ mục sinh từ PK/UNIQUE và kế hoạch truy vấn |

## 11. Bài tập thực hành

### Bài 1. Nhận diện khóa ứng viên

Bảng `products` có `product_id`, `sku`, `barcode`, `name`. Quy tắc nghiệp vụ: `product_id` là định danh DB; `sku` bắt buộc và duy nhất; `barcode` có thể vắng mặt và một số sản phẩm dùng chung barcode; `name` có thể trùng.

**Yêu cầu:** xác định các khóa ứng viên và chọn khóa chính hợp lý.

**Gợi ý đáp án:** `{product_id}` và `{sku}` là khóa ứng viên nếu được quản lý duy nhất. `barcode` và `name` không phải khóa. Chọn `product_id` làm PK khi muốn ổn định độc lập với thay đổi SKU; `sku` vẫn cần `UNIQUE NOT NULL`.

### Bài 2. Tìm khóa ghép tối thiểu

Bảng `exam_attempts` lưu `student_id`, `exam_id`, `attempt_no`, `score`. Một sinh viên được thi lại cùng bài; `attempt_no` bắt đầu từ 1 và tăng **trong phạm vi mỗi cặp (student_id, exam_id)**.

**Yêu cầu:** tìm một khóa ứng viên ghép.

**Đáp án:** `(student_id, exam_id, attempt_no)`. Bỏ `student_id` sẽ nhầm các sinh viên; bỏ `exam_id` sẽ nhầm các bài thi; bỏ `attempt_no` sẽ nhầm nhiều lần thi của cùng sinh viên cùng bài. Khi dùng làm PK, cả ba cột đều bắt buộc.

```sql
CREATE TABLE exam_attempts (
    student_id BIGINT NOT NULL,
    exam_id BIGINT NOT NULL,
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    score NUMERIC(5, 2),
    CONSTRAINT pk_exam_attempts
        PRIMARY KEY (student_id, exam_id, attempt_no),
    CONSTRAINT ck_exam_attempts_score
        CHECK (score BETWEEN 0 AND 100)
);
```

Trong ứng dụng thật, cần thêm FK đến bảng sinh viên và kỳ thi nếu các bảng đó tồn tại.

### Bài 3. Khóa thay thế thuộc loại nào?

Bảng `orders` có `order_id BIGINT GENERATED ... PRIMARY KEY` và `(store_id, order_number) UNIQUE NOT NULL` theo đúng quy tắc “số đơn duy nhất trong cửa hàng”.

**Đáp án:** `order_id` là surrogate key đồng thời là primary key; `(store_id, order_number)` là composite candidate key đồng thời là alternate key. Từ “khóa thay thế” cần chỉ rõ muốn nói *alternate* hay *surrogate*.

### Bài 4. Sửa lỗi khóa ngoại tham chiếu thiếu cột

Bảng `enrollments` có PK `(student_id, course_id, semester_code)`. Một bảng chi tiết ghi điểm muốn xác định đăng ký chính xác nhưng chỉ lưu `student_id` và `course_id`.

**Đáp án:** Hai cột không đủ phân biệt đăng ký của cùng môn trong các học kỳ khác nhau. Phải thêm `semester_code` vào bảng chi tiết và khai báo FK trên đủ ba cột, hoặc thiết kế định danh riêng cho từng lần đăng ký rồi tham chiếu đến định danh đó.

### Bài 5. Điều gì xảy ra khi có surrogate key?

Giả sử bảng `customers` có `customer_id` là PK tự sinh, nhưng ứng dụng cho phép ghi hai hàng cùng `customer_code = 'C001'`. DBMS có tự phát hiện hai hàng là một khách hàng không?

**Đáp án:** không. PK chỉ bảo đảm không trùng `customer_id`. Nếu quy tắc nghiệp vụ yêu cầu mỗi `customer_code` xác định một khách hàng, cần ràng buộc `UNIQUE (customer_code)` và `NOT NULL` khi bắt buộc có mã.

## Kết luận

Để hiểu đúng các loại khóa, hãy bắt đầu từ **quy tắc nhận diện một hàng**:

1. Một **siêu khóa** nhận diện duy nhất; **khóa ứng viên** là siêu khóa **tối thiểu**.
2. **Khóa chính** là **một** khóa ứng viên được chọn cho bảng; SQL thực thi bằng `PRIMARY KEY`.
3. **Alternate key** là khóa ứng viên không được chọn làm khóa chính; thường thực thi bằng `UNIQUE` và `NOT NULL` theo đúng ngữ nghĩa.
4. **Surrogate key** là khóa nhân tạo; nó có thể là khóa chính, nhưng không thay thế quy tắc duy nhất của mã nghiệp vụ.
5. **Khóa ghép** chỉ nói về **số lượng cột** của khóa; nó có thể đóng vai trò khóa chính, khóa ứng viên hoặc alternate key.

Thiết kế đúng phải xét cả **tính duy nhất, tính tối thiểu, phạm vi, khả năng thay đổi, `NULL` và cách các bảng tham chiếu nhau**. Khi những điều kiện này rõ ràng, khóa sẽ giúp dữ liệu nhất quán và các truy vấn JOIN, cập nhật hay báo cáo được xây dựng trên đúng định danh của từng thực thể.

