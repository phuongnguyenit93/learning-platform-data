# Dạng chuẩn Boyce–Codd (BCNF) và vai trò của siêu khóa

**Dạng chuẩn Boyce–Codd (Boyce–Codd Normal Form, BCNF)** đặt một điều kiện chặt hơn dạng chuẩn thứ ba (3NF): **trong mọi phụ thuộc hàm không tầm thường, vế trái phải là siêu khóa**. Quy tắc ngắn gọn này giúp phát hiện một số cấu trúc vẫn cho phép dư thừa dữ liệu dù đã đạt 3NF, nhất là các bảng có nhiều khóa ứng viên chồng lấn.

Trong chương **Chuẩn hóa** của mô-đun **DATABASE_DATA_MODELING**, mục đích không chỉ là nhớ tên dạng chuẩn. Người thiết kế cần dịch quy tắc nghiệp vụ thành phụ thuộc hàm, tìm khóa ứng viên, quyết định thực thể nào sở hữu từng thông tin, phân rã bảng mà không tạo kết quả giả và kiểm tra khả năng bảo vệ các ràng buộc sau phân rã. BCNF là công cụ để làm rõ những quyết định đó; nó cần được cân nhắc cùng yêu cầu cập nhật, truy vấn, khóa ngoại, chỉ mục và khả năng tiến hóa của lược đồ.

## 1. Đặt vấn đề: một bảng đã ở 3NF nhưng vẫn lặp thông tin

Giả sử hệ thống đào tạo quản lý việc học viên học với giảng viên trong **một học kỳ đang xét**, với các quy tắc:

1. Mỗi **giảng viên** chỉ dạy **một môn** trong học kỳ này.
2. Một môn có thể có **nhiều giảng viên**.
3. Mỗi học viên chọn **tối đa một giảng viên cho mỗi môn**.
4. Một giảng viên có thể hướng dẫn nhiều học viên, và một học viên có thể học nhiều môn.

Bảng ban đầu lưu mỗi hàng là một đăng ký học với một giảng viên:

| student_id | course_id | instructor_id |
| --- | --- | --- |
| S01 | C10 | I01 |
| S02 | C10 | I01 |
| S03 | C10 | I02 |
| S01 | C20 | I03 |

Ở dữ liệu trên, **I01** dạy **C10** xuất hiện hai lần. Nếu giảng viên I01 chuyển sang dạy môn khác, thông tin môn của I01 cần được sửa ở tất cả các đăng ký. Cập nhật thiếu một hàng khiến cùng giảng viên có thể được gán hai môn. Nếu xóa đăng ký cuối cùng của I02, hệ thống cũng mất dấu giảng viên I02 dạy môn C10, dù việc phân công giảng viên vẫn còn hiệu lực.

Đây là tình huống hữu ích để học BCNF vì **mọi thuộc tính đều thuộc ít nhất một khóa ứng viên**; theo định nghĩa hình thức, bảng có thể đạt 3NF nhưng chưa đạt BCNF.

> **Giới hạn nghiệp vụ của ví dụ:** giả định “mỗi giảng viên dạy một môn” chỉ đúng **trong học kỳ đang xét**. Nếu quản lý nhiều học kỳ hoặc một giảng viên có thể dạy nhiều môn, phải đổi các phụ thuộc hàm và có thể cần thêm **term_id**, **section_id** hoặc thực thể phân công giảng dạy.

## 2. Các khái niệm cần phân biệt trước khi xét BCNF

### 2.1. Phụ thuộc hàm là quy tắc, không phải sự trùng hợp

Viết **X → Y** khi trong mọi trạng thái dữ liệu hợp lệ, hai hàng có cùng giá trị X phải có cùng giá trị Y. X và Y có thể là các tập thuộc tính.

Trong ví dụ:

~~~text
(student_id, course_id) -> instructor_id
instructor_id             -> course_id
~~~

Phụ thuộc thứ nhất đến từ quy tắc mỗi học viên có tối đa một giảng viên cho một môn. Phụ thuộc thứ hai đến từ quy tắc mỗi giảng viên chỉ dạy một môn. **Không có** phụ thuộc **course_id → instructor_id** vì một môn có thể có nhiều giảng viên.

Một vài dòng dữ liệu không đủ chứng minh phụ thuộc hàm: cần xác nhận với nghiệp vụ rằng quy tắc vẫn đúng trong các tình huống hợp lệ khác.

### 2.2. Siêu khóa và khóa ứng viên khác nhau ở tính tối thiểu

- **Siêu khóa (superkey):** tập thuộc tính có thể xác định toàn bộ thuộc tính của một hàng; không bắt buộc tối thiểu.
- **Khóa ứng viên (candidate key):** **siêu khóa tối thiểu**, nghĩa là bỏ bất kỳ thuộc tính nào cũng không còn xác định được cả hàng.
- **Khóa chính (primary key):** một khóa ứng viên được chọn làm định danh chính trong lược đồ SQL.
- **Thuộc tính nguyên tố (prime attribute):** thuộc ít nhất một khóa ứng viên; các thuộc tính còn lại là **không nguyên tố (non-prime)**.

Ví dụ, nếu **(student_id, course_id)** là khóa ứng viên thì **(student_id, course_id, instructor_id)** vẫn là siêu khóa, nhưng không phải khóa ứng viên vì có một thành phần thừa.

Điều kiện BCNF đòi hỏi **siêu khóa**, không đòi hỏi vế trái chính xác là một khóa ứng viên. Mọi siêu khóa đều đủ, kể cả siêu khóa có thêm thuộc tính.

### 2.3. Tìm khóa bằng bao đóng thuộc tính

**Bao đóng của X**, ký hiệu **X⁺**, là tập thuộc tính có thể suy ra từ X qua các phụ thuộc hàm. Tập X là siêu khóa nếu **X⁺** bao gồm mọi thuộc tính của quan hệ.

Đặt tên ngắn cho ba thuộc tính:

~~~text
S = student_id
C = course_id
I = instructor_id

R(S, C, I)
F = { SC -> I, I -> C }
~~~

Ta có:

| Tập thuộc tính X | Bao đóng X⁺ | Là siêu khóa? |
| --- | --- | --- |
| {S} | {S} | Không |
| {C} | {C} | Không |
| {I} | {I, C} | Không: thiếu S |
| {S, C} | {S, C, I} | Có |
| {S, I} | {S, I, C} | Có |

**SC** và **SI** đều là siêu khóa tối thiểu nên là **hai khóa ứng viên**. Chúng chồng lấn ở thuộc tính S. Cả S, C, I đều là **thuộc tính nguyên tố** vì mỗi thuộc tính xuất hiện trong ít nhất một khóa ứng viên.

Lưu ý **I → C** là một phụ thuộc hàm hợp lệ nhưng **I không phải siêu khóa**: một giảng viên có thể dạy nhiều học viên, nên cùng I có thể xuất hiện ở nhiều hàng với những S khác nhau.

## 3. Định nghĩa hình thức của BCNF

Một quan hệ **R ở BCNF** khi với **mọi phụ thuộc hàm không tầm thường X → A** đúng trên R, trong đó A là một thuộc tính, **X là siêu khóa của R**.

- **Không tầm thường** nghĩa là **A không thuộc X**. Ví dụ, **(S, C) → S** là phụ thuộc tầm thường và không phải điều cần kiểm tra.
- Nếu vế phải có nhiều thuộc tính, có thể tách thành các phụ thuộc với từng thuộc tính ở vế phải để kiểm tra.
- “Mọi phụ thuộc” bao gồm cả phụ thuộc **suy diễn** từ các quy tắc nghiệp vụ, không chỉ các phụ thuộc được liệt kê ban đầu.
- Khái niệm **siêu khóa của R** luôn phải xét theo **quan hệ đang kiểm tra**, vì khi phân rã thành các quan hệ con, tập thuộc tính và các khóa có thể thay đổi.

Một cách phát biểu tương đương: **mọi yếu tố xác định (determinant) của một phụ thuộc hàm không tầm thường phải là siêu khóa**.

Trong bảng đăng ký:

| Phụ thuộc | Vế trái là siêu khóa? | Kết quả BCNF |
| --- | --- | --- |
| **(S, C) → I** | Có, SC là khóa ứng viên | Đạt yêu cầu |
| **I → C** | Không, I⁺ = {I, C} thiếu S | **Vi phạm BCNF** |

**Một phụ thuộc vi phạm cũng đủ để kết luận cả quan hệ chưa ở BCNF.**

## 4. Vì sao 3NF cho phép trường hợp mà BCNF không cho phép?

Định nghĩa hình thức của **3NF**: với mỗi phụ thuộc hàm không tầm thường **X → A**, ít nhất một điều kiện đúng:

1. X là **siêu khóa**; **hoặc**
2. A là **thuộc tính nguyên tố**.

**BCNF chỉ giữ điều kiện thứ nhất.**

Ở quan hệ R(S, C, I):

- **SC → I** hợp lệ ở cả 3NF lẫn BCNF vì SC là siêu khóa.
- **I → C** hợp lệ ở **3NF** vì C thuộc khóa ứng viên SC và là thuộc tính nguyên tố, **dù I không là siêu khóa**.
- **I → C** vi phạm **BCNF** vì BCNF không có ngoại lệ “vế phải là thuộc tính nguyên tố”.

| Dạng chuẩn | Tiêu chí cốt lõi | Đánh giá R(S, C, I) |
| --- | --- | --- |
| **1NF** | Mỗi thuộc tính biểu diễn giá trị phù hợp miền dữ liệu, không giấu nhóm lặp cần quản lý riêng | Có thể thỏa |
| **2NF** | Thuộc tính không nguyên tố phụ thuộc đầy đủ vào mọi khóa ứng viên | Thỏa: mọi thuộc tính đều nguyên tố |
| **3NF** | Với X → A không tầm thường: X là siêu khóa **hoặc** A nguyên tố | **Thỏa** |
| **BCNF** | Với X → A không tầm thường: **X phải là siêu khóa** | **Không thỏa**, do I → C |

Như vậy, **BCNF nghiêm ngặt hơn 3NF**. Mỗi quan hệ ở BCNF đều thỏa 3NF; điều ngược lại không luôn đúng. Đừng chỉ ghi nhớ câu “3NF loại bỏ phụ thuộc bắc cầu”: trong quan hệ có nhiều khóa ứng viên, cách diễn giải đó không đủ chính xác để kết luận.

## 5. Phân rã quan hệ thành các bảng đạt BCNF

Với một phụ thuộc **X → Y** vi phạm BCNF, một cách phân rã nhị phân thường dùng là:

~~~text
R1 = X ∪ Y
R2 = R − (Y − X)
~~~

Áp dụng với **I → C** trong R(S, C, I):

~~~text
R1(I, C)     -- phân công một môn cho giảng viên
R2(S, I)     -- học viên đăng ký học với giảng viên
~~~

Sơ đồ quan hệ sau phân rã:

~~~mermaid
erDiagram
    COURSES ||--o{ INSTRUCTORS : "được giảng dạy bởi"
    INSTRUCTORS ||--o{ STUDENT_INSTRUCTORS : "hướng dẫn"
    STUDENTS ||--o{ STUDENT_INSTRUCTORS : "đăng ký"
    COURSES {
        varchar course_id PK
        varchar course_title
    }
    INSTRUCTORS {
        varchar instructor_id PK
        varchar course_id FK
    }
    STUDENTS {
        varchar student_id PK
        varchar student_name
    }
    STUDENT_INSTRUCTORS {
        varchar student_id PK, FK
        varchar instructor_id PK, FK
    }
~~~

Trong phần lõi của phép phân rã:

- **R1(I, C)** có phụ thuộc **I → C**, trong đó I là khóa ứng viên của R1. R1 đạt BCNF.
- **R2(S, I)** không có phụ thuộc hàm không tầm thường nào với vế trái không là siêu khóa theo tập quy tắc đã cho; cặp **(S, I)** là khóa ứng viên. R2 đạt BCNF.

Việc thêm bảng danh mục **STUDENTS** và **COURSES** trong triển khai SQL giúp quản lý thực thể độc lập. Chúng không làm thay đổi lập luận phân rã đối với ba thuộc tính R(S, C, I).

### 5.1. Ví dụ SQL triển khai quan hệ sau phân rã

Ví dụ sau dùng cú pháp PostgreSQL; các bảng có thể được tạo và nạp lần lượt:

~~~sql
CREATE TABLE students (
    student_id   VARCHAR(10) PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE courses (
    course_id    VARCHAR(10) PRIMARY KEY,
    course_title VARCHAR(100) NOT NULL
);

CREATE TABLE instructors (
    instructor_id VARCHAR(10) PRIMARY KEY,
    course_id     VARCHAR(10) NOT NULL
        REFERENCES courses(course_id)
);

CREATE TABLE student_instructors (
    student_id    VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    instructor_id VARCHAR(10) NOT NULL
        REFERENCES instructors(instructor_id),
    PRIMARY KEY (student_id, instructor_id)
);

INSERT INTO students (student_id, student_name) VALUES
    ('S01', 'An'),
    ('S02', 'Bình'),
    ('S03', 'Chi');

INSERT INTO courses (course_id, course_title) VALUES
    ('C10', 'Cơ sở dữ liệu'),
    ('C20', 'Lập trình Java');

INSERT INTO instructors (instructor_id, course_id) VALUES
    ('I01', 'C10'),
    ('I02', 'C10'),
    ('I03', 'C20');

INSERT INTO student_instructors (student_id, instructor_id) VALUES
    ('S01', 'I01'),
    ('S02', 'I01'),
    ('S03', 'I02'),
    ('S01', 'I03');
~~~

Khi cần xem các đăng ký ở dạng R(S, C, I), nối theo **instructor_id**:

~~~sql
SELECT
    e.student_id,
    i.course_id,
    e.instructor_id
FROM student_instructors AS e
JOIN instructors AS i
    ON i.instructor_id = e.instructor_id
ORDER BY e.student_id, i.course_id;
~~~

Thông tin **giảng viên nào dạy môn nào** được lưu một lần trong bảng **instructors**. Sửa phân công chỉ cần cập nhật một hàng; có thể lưu giảng viên chưa có đăng ký nào.

### 5.2. Kiểm tra tính nối không mất thông tin

Phân rã **R(S, C, I) → R1(I, C), R2(S, I)** có phần giao:

~~~text
R1 ∩ R2 = {I}
~~~

Vì **I → C**, tập giao **{I}** xác định tất cả thuộc tính của **R1(I, C)**. Theo điều kiện phân rã nhị phân, đây là phép phân rã **nối không mất thông tin (lossless join)** đối với mọi quan hệ gốc hợp lệ thỏa các phụ thuộc đã cho.

Với dữ liệu ban đầu, mỗi hàng **(S, I)** khớp một hàng **(I, C)** để khôi phục đúng **(S, C, I)**. Không có chuyện một giảng viên dạy hai môn khiến phép nối nhân đôi hàng, bởi **I** là khóa của R1.

**Lossless join** trả lời câu hỏi “có thể tái tạo quan hệ gốc chính xác từ phép phân rã hợp lệ hay không?”. Nó **không tự bảo đảm** rằng mọi trạng thái ghi được vào các bảng mới đều vẫn thỏa toàn bộ quy tắc nghiệp vụ ban đầu.

## 6. Đánh đổi quan trọng: BCNF có thể không bảo toàn phụ thuộc hàm

Sau phân rã, phụ thuộc **I → C** nằm trọn trong **instructors(I, C)** và được bảo vệ bởi khóa chính **instructor_id**.

Nhưng phụ thuộc ban đầu **(S, C) → I** không nằm nguyên vẹn trong bảng nào:

~~~text
instructors(I, C):          I -> C
student_instructors(S, I):  (S, I) là khóa
~~~

Từ các phụ thuộc riêng của hai bảng, không thể suy ra rằng một học viên chỉ có **một** giảng viên cho mỗi môn. Đây là ví dụ về phân rã **lossless nhưng không bảo toàn tất cả phụ thuộc hàm (not dependency-preserving)**.

### 6.1. Phản ví dụ cụ thể

Giả sử trong dữ liệu mẫu, **I01** và **I02** cùng dạy môn **C10**. Thực hiện:

~~~sql
-- Hai giảng viên khác nhau, cùng môn C10.
-- Khóa chính (student_id, instructor_id) vẫn cho phép hàng mới.
INSERT INTO student_instructors (student_id, instructor_id)
VALUES ('S01', 'I02');
~~~

Bây giờ phép nối trả về:

| student_id | course_id | instructor_id |
| --- | --- | --- |
| S01 | C10 | I01 |
| S01 | C10 | I02 |

Hai hàng này vi phạm **(student_id, course_id) → instructor_id**. Chúng không vi phạm khóa chính, khóa ngoại nào trong lược đồ BCNF ở mục 5.1. Điều đó không phủ định tính *lossless* của phép phân rã: dữ liệu **sau lần thêm** đã vi phạm một quy tắc nghiệp vụ của R gốc mà các ràng buộc tại từng bảng con chưa chặn được.

Có thể phát hiện các trường hợp vi phạm bằng truy vấn:

~~~sql
SELECT
    e.student_id,
    i.course_id,
    COUNT(DISTINCT e.instructor_id) AS instructor_count
FROM student_instructors AS e
JOIN instructors AS i
    ON i.instructor_id = e.instructor_id
GROUP BY e.student_id, i.course_id
HAVING COUNT(DISTINCT e.instructor_id) > 1;
~~~

Truy vấn chỉ **phát hiện** dữ liệu sai. Để **ngăn** dữ liệu sai, cần thêm cơ chế kiểm soát quy tắc **(student_id, course_id) → instructor_id**, ví dụ một thiết kế khác cho phép ràng buộc bằng khóa duy nhất, hoặc logic ghi có bảo đảm tính đồng thời bằng ràng buộc/trigger/giao dịch thích hợp. Kiểm tra trước bằng ứng dụng mà không bảo vệ cạnh tranh ghi có thể vẫn bị *race condition*.

### 6.2. Khi nào ưu tiên 3NF?

Đối với một tập phụ thuộc hàm, có thuật toán **tổng hợp 3NF** tạo phân rã **nối không mất thông tin** và **bảo toàn phụ thuộc hàm**. Ngược lại, không phải mọi quan hệ đều có một phân rã BCNF vừa lossless vừa bảo toàn toàn bộ phụ thuộc.

| Mục tiêu | 3NF | BCNF |
| --- | --- | --- |
| Hạn chế phụ thuộc gây dư thừa | Tốt; cho phép ngoại lệ nếu vế phải nguyên tố | Chặt hơn: mọi yếu tố xác định phải là siêu khóa |
| Phân rã lossless | Có thể đạt bằng thuật toán chuẩn | Có thể đạt bằng thuật toán phân rã chuẩn |
| Bảo toàn mọi phụ thuộc hàm | Có thể bảo đảm bằng thuật toán tổng hợp 3NF | **Không luôn bảo đảm** |
| Chi phí kiểm tra ràng buộc | Thường thuận lợi hơn nếu các phụ thuộc được bảo toàn | Một số phụ thuộc có thể cần kiểm tra qua nhiều bảng hoặc tái thiết kế |

**Lưu ý:** *bảo toàn phụ thuộc hàm* là tính chất hình thức của phép phân rã, **không đồng nghĩa** mọi phụ thuộc đều có thể được biểu diễn bằng một lệnh **PRIMARY KEY**, **UNIQUE** hoặc **CHECK** đơn giản trong một hệ SQL. Chẳng hạn, trong bảng gộp có nhiều học viên cùng một giảng viên, ràng buộc **I → C** không thể được mô tả chỉ bằng **UNIQUE(I)**, vì như vậy sẽ cấm một giảng viên xuất hiện ở nhiều đăng ký. Việc thực thi cụ thể vẫn cần thiết kế ràng buộc hoặc quy trình ghi phù hợp.

## 7. Khi nào BCNF cần thiết, khi nào cần thêm phân tích?

### 7.1. Bảng đã đạt 3NF nhưng vi phạm BCNF

Tập trung vào những quan hệ có **nhiều khóa ứng viên chồng lấn** hoặc các phụ thuộc có **vế phải là thuộc tính nguyên tố**. Đây là nơi ngoại lệ của 3NF có thể che đi rủi ro dư thừa.

Hãy liệt kê mọi phụ thuộc hàm không tầm thường và tính bao đóng vế trái. Nếu một vế trái không xác định được toàn bộ thuộc tính của quan hệ, phụ thuộc đó vi phạm BCNF.

### 7.2. Bảng chưa đạt 3NF

Ví dụ bảng:

~~~text
employees(employee_id, employee_name, department_id, department_name)

employee_id  -> employee_name, department_id
department_id -> department_name
~~~

Nếu **employee_id** là khóa ứng viên duy nhất, **department_id → department_name** vi phạm **cả 3NF lẫn BCNF**: department_id không là siêu khóa và department_name không nguyên tố. Tách bảng **departments(department_id, department_name)** và **employees(employee_id, employee_name, department_id)** là hướng sửa trực tiếp.

BCNF bao hàm việc xử lý các trường hợp chưa đạt 3NF, nhưng điểm mới của BCNF là loại bỏ **cả những phụ thuộc mà 3NF cho phép do vế phải là thuộc tính nguyên tố**.

### 7.3. Khóa thay thế không làm biến mất phụ thuộc nghiệp vụ

Nếu thêm **registration_id** làm khóa chính vào bảng R(S, C, I), các quy tắc **SC → I** và **I → C** vẫn còn. Khóa đơn **registration_id** không tự bảo đảm mọi phụ thuộc có vế trái là siêu khóa.

Hơn nữa, nếu thêm **UNIQUE(student_id, course_id)** với cả hai cột **NOT NULL**, cặp **(S, C)** vẫn là khóa ứng viên bên cạnh **registration_id**. Cần xét **tất cả khóa ứng viên và mọi phụ thuộc hàm**, không chỉ tên cột đặt trong **PRIMARY KEY**.

### 7.4. Thay đổi bối cảnh làm thay đổi phụ thuộc

Quy tắc **I → C** có thể đúng trong một học kỳ nhưng sai khi quản lý lịch sử nhiều kỳ. Nếu một giảng viên dạy môn khác ở kỳ tiếp theo, phụ thuộc có thể trở thành:

~~~text
(instructor_id, term_id) -> course_id
~~~

Nếu một giảng viên dạy nhiều lớp của nhiều môn trong cùng kỳ, phụ thuộc lại có thể cần **section_id**, hoặc không tồn tại dưới dạng trên. Cần làm rõ grain và chiều thời gian trước khi gắn nhãn “vi phạm BCNF”, tránh phân rã theo một quy tắc không đúng nghiệp vụ.

## 8. Quy trình đánh giá và phân rã BCNF

1. **Xác nhận grain và miền giá trị.** Một hàng tương ứng với một đăng ký, một phân công, một lần học hay một kết quả thi? Xác định các thuộc tính thuộc mỗi sự thật.
2. **Thu thập phụ thuộc hàm.** Dựa trên quy tắc nghiệp vụ ổn định trong phạm vi và thời gian đang mô hình hóa, không dựa chỉ vào dữ liệu mẫu.
3. **Tìm khóa ứng viên bằng bao đóng.** Từ các phụ thuộc, tìm những tập thuộc tính tối thiểu xác định toàn bộ bảng.
4. **Kiểm tra BCNF.** Với mỗi **X → A** không tầm thường, tính **X⁺**. Nếu X⁺ không bao gồm toàn bộ thuộc tính của quan hệ, ghi nhận vi phạm.
5. **Phân rã theo phụ thuộc vi phạm.** Dùng **R1 = X ∪ Y** và **R2 = R − (Y − X)**, sau đó tiếp tục kiểm tra BCNF của từng quan hệ con.
6. **Xác minh lossless join.** Với phân rã nhị phân, kiểm tra phần giao xác định được toàn bộ một trong hai quan hệ con; với phân rã nhiều bước, bảo đảm từng bước nối không mất thông tin.
7. **Đánh giá bảo toàn phụ thuộc.** Liệt kê lại các phụ thuộc gốc và xem chúng có được kiểm soát chỉ qua bảng con hay cần kiểm tra qua phép nối.
8. **Hoàn thiện khóa và cơ chế ghi.** Bổ sung **PRIMARY KEY**, **FOREIGN KEY**, **UNIQUE**, **CHECK**, giao dịch hoặc các ràng buộc nâng cao phù hợp; kiểm thử cả tình huống ghi đồng thời.
9. **Đánh giá chi phí truy vấn và tiến hóa.** Phân tích phép nối, chỉ mục và khối lượng dữ liệu. Nếu cần mô hình đọc phi chuẩn hóa hoặc document, làm rõ nguồn dữ liệu chuẩn, quy tắc đồng bộ và các bất biến cần bảo vệ.

Không có quy tắc “số bảng càng nhiều càng tốt”. Một phân rã đạt BCNF mà làm mất khả năng thực thi quy tắc quan trọng có thể cần cơ chế bổ sung hoặc lựa chọn thiết kế khác, kể cả 3NF. Quyết định phải gắn với yêu cầu kiểm chứng và vận hành của hệ thống.

## 9. Bài tập thực hành

### Bài 1. Tìm khóa và dạng chuẩn

Cho quan hệ **R(A, B, C)** và các phụ thuộc hàm:

~~~text
AB -> C
C  -> B
~~~

Giả định mọi bộ phận khác của lược đồ không tạo thêm phụ thuộc hàm ngoài hệ quả của hai quy tắc trên.

**Yêu cầu:**

1. Tính **A⁺**, **C⁺**, **(AB)⁺** và **(AC)⁺**.
2. Tìm toàn bộ khóa ứng viên.
3. Xác định R đạt **3NF** và **BCNF** hay không.
4. Phân rã R thành các quan hệ đạt BCNF; chứng minh nối không mất thông tin.
5. Kiểm tra phụ thuộc **AB → C** có được bảo toàn qua các quan hệ con không.

<details>
<summary>Gợi ý lời giải bài 1</summary>

~~~text
A+  = {A}
C+  = {C, B}
AB+ = {A, B, C}
AC+ = {A, C, B}
~~~

Khóa ứng viên là **AB** và **AC**; cả A, B, C đều là thuộc tính nguyên tố. **AB → C** thỏa 3NF/BCNF vì AB là siêu khóa. **C → B** thỏa 3NF do B nguyên tố, nhưng vi phạm BCNF do C không là siêu khóa.

Phân rã thành **R1(C, B)** và **R2(A, C)**. Giao hai quan hệ là **C**, và **C → B**, nên phân rã lossless. Hai quan hệ con đạt BCNF theo các phụ thuộc được chiếu xuống chúng.

Phụ thuộc **AB → C** không được bảo toàn bởi các phụ thuộc cục bộ **C → B** trong R1 và các phụ thuộc tầm thường trong R2. Cần cơ chế bổ sung nếu muốn bảo đảm phụ thuộc này khi ghi trên các bảng mới.

</details>

### Bài 2. Kiểm tra một yêu cầu thay đổi

Trong hệ thống đào tạo ở đầu bài, nhóm nghiệp vụ bổ sung yêu cầu **mỗi giảng viên có thể dạy nhiều môn, nhưng mỗi giảng viên chỉ phụ trách một lớp cho mỗi môn trong một học kỳ**.

Hãy trả lời:

- Phụ thuộc **instructor_id → course_id** còn đúng không?
- Cần hỏi thêm thông tin nào về **học kỳ**, **lớp học phần**, **lần đăng ký** trước khi định nghĩa khóa?
- Có thể tiếp tục kết luận quan hệ **(student_id, course_id, instructor_id)** chưa đạt BCNF chỉ dựa trên quy tắc cũ không?

**Gợi ý:** phụ thuộc **I → C** không còn đúng khi giảng viên được phép dạy nhiều môn. Cần mô hình rõ **term_id**, **section_id** và ràng buộc mỗi học viên có thể chọn bao nhiêu lớp hoặc giảng viên cho mỗi môn. Không được kết luận vi phạm BCNF bằng phụ thuộc đã bị nghiệp vụ loại bỏ.

## 10. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Chỉ cần vế trái là khóa chính.” | BCNF chấp nhận **mọi siêu khóa**, kể cả khóa ứng viên khác và siêu khóa không tối thiểu. |
| “Đạt 3NF thì đương nhiên đạt BCNF.” | 3NF cho phép **X → A** nếu A là thuộc tính nguyên tố dù X không phải siêu khóa; BCNF không cho phép ngoại lệ đó. |
| “Có cột ID làm khóa chính thì bảng đạt BCNF.” | Phải xét **mọi phụ thuộc hàm nghiệp vụ**; thêm ID không xóa các phụ thuộc cũ. |
| “Bảng có nhiều hàng cùng course_id là sai.” | Giá trị khóa ngoại hoặc mã môn lặp là bình thường; vấn đề là phụ thuộc nào buộc một thông tin khác phải được sao chép. |
| “Phân rã lossless có nghĩa mọi ràng buộc đều được bảo toàn.” | Lossless và dependency preservation là **hai tính chất khác nhau**. |
| “BCNF luôn tốt hơn 3NF trong mọi dự án.” | BCNF giảm một nhóm dư thừa nhưng có thể làm ràng buộc khó thực thi hơn; phải xét nghiệp vụ và toàn vẹn dữ liệu. |
| “Không có dữ liệu trùng nghĩa là đạt BCNF.” | Dạng chuẩn được xác định theo **phụ thuộc hàm hợp lệ**, không theo trạng thái dữ liệu mẫu. |
| “Một giảng viên luôn dạy đúng một môn.” | Đây là giả định theo bối cảnh; lịch sử và nhiều lớp học phần có thể thay đổi phụ thuộc. |

## 11. Ghi nhớ

BCNF yêu cầu: **với mọi phụ thuộc hàm không tầm thường X → A, X phải là siêu khóa**. Để đánh giá, phải tìm **mọi khóa ứng viên**, dùng **bao đóng thuộc tính** để kiểm tra vế trái và dựa trên phụ thuộc hàm do nghiệp vụ xác nhận. Đây là cách BCNF loại bỏ những phụ thuộc mà 3NF vẫn có thể cho phép khi vế phải là thuộc tính nguyên tố.

Phân rã theo phụ thuộc vi phạm có thể đem lại lược đồ BCNF **nối không mất thông tin**, song **không luôn bảo toàn được mọi phụ thuộc hàm**. Khi thiết kế hệ thống thực tế, phải kiểm tra các quy tắc ghi còn thực thi được hay không, hoàn thiện khóa và ràng buộc, rồi cân nhắc chi phí truy vấn, chỉ mục và nhu cầu lịch sử. Chọn BCNF hay một thiết kế 3NF được kiểm soát là quyết định dựa trên tính đúng đắn và khả năng vận hành, không đơn thuần là chạy theo dạng chuẩn cao nhất.
