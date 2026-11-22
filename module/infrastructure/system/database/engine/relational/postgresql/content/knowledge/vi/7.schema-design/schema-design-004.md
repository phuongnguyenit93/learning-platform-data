# Chuẩn hóa dữ liệu và nhận diện phụ thuộc hàm trong PostgreSQL

## 1. Mục tiêu và bài toán thiết kế

Một cơ sở dữ liệu có thể lưu trữ dữ liệu và trả lời đúng các câu `SELECT` ở thời điểm hiện tại nhưng vẫn được thiết kế chưa tốt. Khi dữ liệu thay đổi, ứng dụng bắt đầu gặp những tình huống như:

- Cập nhật tên giảng viên ở một dòng nhưng quên cập nhật hàng trăm dòng khác.
- Không thể thêm môn học mới cho đến khi có sinh viên đăng ký.
- Xóa lượt đăng ký cuối cùng khiến thông tin môn học biến mất.
- Hai dòng mang cùng mã môn học nhưng tên môn khác nhau.
- Không biết nên khai báo `PRIMARY KEY`, `UNIQUE` và `FOREIGN KEY` trên những cột nào.

**Chuẩn hóa dữ liệu (normalization)** giúp phân tích những sự thật mà mỗi bảng phải biểu diễn, xác định các quy tắc phụ thuộc giữa thuộc tính và tách dữ liệu thành những quan hệ nhất quán. Một công cụ quan trọng là **phụ thuộc hàm (functional dependency, FD)**.

Bài học giải thích từ cách nhận diện FD, tìm khóa, tính tập thuộc tính đóng đến **1NF, 2NF, 3NF, BCNF**, sau đó hiện thực các bảng bằng PostgreSQL và kiểm tra việc chuyển đổi.

Sau khi hoàn thành, bạn có thể:

1. Phân biệt FD do nghiệp vụ xác định với sự trùng hợp trong dữ liệu hiện có.
2. Tìm superkey, candidate key, primary key và attribute closure.
3. Nhận diện phụ thuộc bộ phận, phụ thuộc bắc cầu và bất thường khi thêm/sửa/xóa.
4. Phân rã quan hệ mà vẫn xem xét **lossless join** và **dependency preservation**.
5. Sử dụng ràng buộc PostgreSQL để bảo vệ những quy tắc nghiệp vụ đã xác định.
6. Phân tích các trường hợp đặc biệt: dữ liệu lịch sử, `NULL`, khóa thay thế và phi chuẩn hóa có chủ đích.

Các lệnh `CREATE`, `INSERT`, `UPDATE` chỉ dành cho một **database thực hành** có quyền phù hợp. Không chạy lệnh thay đổi schema trên production nếu chưa có kế hoạch migration, kiểm thử và phương án quay lui.

## 2. Một bảng đang gộp quá nhiều sự thật

Giả sử một trung tâm đào tạo lưu tất cả đăng ký học trong bảng `registrations_raw`:

| student_id | student_name | course_id | course_title | instructor_id | instructor_name | grade |
|---|---|---|---|---|---|---|
| 1 | Nguyễn An | 101 | Cơ sở dữ liệu | 9 | Cô Lan | 8.50 |
| 2 | Trần Bình | 101 | Cơ sở dữ liệu | 9 | Cô Lan | 7.50 |
| 1 | Nguyễn An | 102 | Thuật toán | 10 | Thầy Minh | 9.00 |
| 2 | Trần Bình | 102 | Thuật toán | 10 | Thầy Minh | *chưa có điểm* |

Một hàng chứa thông tin của **bốn loại sự thật khác nhau**:

- Sinh viên: mã và tên.
- Môn học: mã và tên.
- Giảng viên: mã và tên.
- Lượt đăng ký: sinh viên nào học môn nào và điểm tương ứng.

Quy tắc của ví dụ:

1. Mỗi mã sinh viên xác định một sinh viên và tên hiện tại.
2. Mỗi mã môn xác định một tên môn và một giảng viên hiện phụ trách.
3. Mỗi mã giảng viên xác định tên hiện tại của họ.
4. Một sinh viên học nhiều môn; một môn có nhiều sinh viên.
5. Trong phạm vi mô hình đơn giản, mỗi cặp sinh viên–môn chỉ có một lượt đăng ký và tối đa một điểm.

Đây là **giả định nghiệp vụ của bài học**, không đúng cho mọi hệ thống giáo dục. Nếu có nhiều lớp, nhiều giảng viên, các học kỳ hoặc lần học lại, khóa và FD phải thay đổi cho đúng.

### 2.1. Update anomaly

Tên giảng viên mã 9 thay đổi. Nếu tên ấy được lặp ở 500 dòng đăng ký, cần sửa cả 500 dòng. Sửa thiếu một dòng tạo mâu thuẫn:

```text
course_id = 101, instructor_id = 9, instructor_name = "Cô Lan"
course_id = 101, instructor_id = 9, instructor_name = "Nguyễn Thị Lan"
```

Khi ấy bảng không còn một sự thật thống nhất về tên giảng viên.

### 2.2. Insertion anomaly

Trung tâm muốn tạo môn 103 trước khi có sinh viên nào đăng ký. Nếu thiết kế chỉ có bảng đăng ký bắt buộc `student_id`, không có nơi độc lập để lưu môn mới mà không tạo hàng giả.

### 2.3. Deletion anomaly

Sinh viên cuối cùng hủy môn 102, ứng dụng xóa dòng đăng ký cuối. Nếu đó là nơi duy nhất lưu thông tin môn, tên môn và giảng viên phụ trách cũng vô tình bị mất.

Chuẩn hóa nhằm giảm những bất thường xuất phát từ việc **một thuộc tính bị đặt sai nơi chịu trách nhiệm**.

## 3. Phụ thuộc hàm là gì?

### 3.1. Định nghĩa

Cho quan hệ `R`, một tập thuộc tính `X` **xác định hàm** tập thuộc tính `Y` nếu trong **mọi trạng thái dữ liệu hợp lệ**, hai bộ có giá trị giống nhau trên tất cả thuộc tính `X` thì phải giống nhau trên tất cả thuộc tính `Y`.

Ký hiệu:

```text
X → Y
```

Ví dụ theo các giả định ở phần 2:

```text
student_id → student_name

course_id → course_title
course_id → instructor_id

instructor_id → instructor_name

(student_id, course_id) → grade
```

Mỗi `student_id` ứng với một tên hiện tại; mỗi `course_id` ứng với tên môn và giảng viên hiện phụ trách; điểm thuộc về **cặp sinh viên–môn**.

Viết bằng tập:

```text
{student_id, course_id} → {grade}
```

có cùng ý nghĩa với cách viết dùng ngoặc ở trên.

### 3.2. Điều FD không nói

Nếu `student_id → student_name`, hai sinh viên có **khác ID vẫn có thể cùng tên**. FD không đòi chiều ngược:

```text
student_name → student_id
```

Tương tự:

```text
course_id → course_title
```

không tự chứng minh `course_title → course_id`, vì có thể tồn tại hai mã môn có tiêu đề trùng nhau.

Một phụ thuộc `X → Y` không có nghĩa `X` **gây ra** `Y`. Đây là ràng buộc về **khả năng xác định duy nhất giá trị**, không phải một khẳng định nhân quả.

### 3.3. Một số FD không hợp lý

Các FD sau **không đúng** theo bài toán:

```text
student_id → grade
course_id → grade
grade → student_id
instructor_name → instructor_id
```

Một sinh viên có nhiều điểm; một môn có nhiều sinh viên với những điểm khác nhau; nhiều người có thể cùng điểm hoặc cùng tên.

### 3.4. FD là quy tắc cho dữ liệu hợp lệ, không phải quan sát thống kê

Giả sử hiện tại chỉ có một sinh viên đăng ký môn 101. Khi ấy dữ liệu mẫu chưa bác bỏ:

```text
course_id → grade
```

Nhưng FD đó vẫn sai theo nghiệp vụ vì sau này nhiều sinh viên có thể học cùng môn với điểm khác nhau.

Có thể dùng SQL tìm vi phạm FD **trên dữ liệu hiện tại**, nhưng không thể suy ra mọi FD đúng cho tương lai chỉ bằng một tập dữ liệu hữu hạn. FD phải được xác nhận từ nghiệp vụ, mô hình thời gian và ràng buộc thiết kế.

### 3.5. FD và chiều thời gian

Trong bảng chỉ chứa **phân công hiện tại**, `course_id → instructor_id` có thể đúng. Nhưng trong bảng lưu lịch sử nhiều học kỳ, môn 101 có thể do nhiều giảng viên phụ trách vào các kỳ khác nhau.

Khi đó một FD phù hợp hơn có thể là:

```text
(course_id, term_id) → instructor_id
```

Nếu có nhiều lớp trong cùng kỳ:

```text
(course_id, term_id, section_id) → instructor_id
```

Nếu một sinh viên được học lại môn:

```text
(student_id, course_id, term_id, attempt_no) → grade
```

Việc chọn đúng **grain** (một hàng biểu diễn một sự kiện/thực thể gì) và phạm vi thời gian là điều kiện tiên quyết để viết FD chính xác.

## 4. Nhận diện FD từ quy tắc nghiệp vụ

Hãy đặt câu hỏi: **“Nếu hai dòng có cùng X, mọi dữ liệu hợp lệ có bắt buộc cùng Y không?”**

| Giả thuyết | Câu hỏi cần hỏi nghiệp vụ | Theo mô hình hiện tại |
|---|---|---|
| `student_id → student_name` | Mỗi mã sinh viên có một tên hiện tại? | Có |
| `student_name → student_id` | Hai sinh viên được phép cùng tên? | Không thể suy ra |
| `course_id → course_title` | Mã môn có xác định tên môn? | Có |
| `course_id → instructor_id` | Có nhiều lớp/giảng viên cho một mã môn? | Có trong mô hình đơn giản |
| `instructor_id → instructor_name` | Mã giảng viên xác định tên hiện tại? | Có |
| `instructor_id → course_id` | Giảng viên chỉ có thể dạy một môn? | Không |
| `(student_id, course_id) → grade` | Một sinh viên có thể học lại cùng môn? | Có trong mô hình đơn giản |
| `email → student_id` | Email luôn duy nhất và không tái sử dụng? | Chưa đủ thông tin |

Cách làm thực tế:

1. Liệt kê thực thể: Sinh viên, Môn học, Giảng viên, Đăng ký.
2. Liệt kê các thuộc tính của từng thực thể.
3. Tìm các mã định danh tự nhiên hoặc nhân tạo.
4. Xác định những thuộc tính chỉ có ý nghĩa với một **mối quan hệ** (ví dụ điểm của đăng ký).
5. Kiểm tra ngoại lệ: đổi tên, học lại, phân công nhiều giảng viên, dữ liệu lịch sử.
6. Viết danh sách FD có thể được bảo vệ bằng một cấu trúc bảng hoặc constraint.

Không chọn một FD chỉ vì tên cột nghe có vẻ “khóa”. `postal_code`, `full_name`, `product_name` hoặc `phone_number` có thể không duy nhất và có thể thay đổi theo thời gian.

## 5. Superkey, candidate key và primary key

### 5.1. Superkey

Một tập thuộc tính `K` là **superkey** của quan hệ `R` nếu nó xác định được **mọi thuộc tính của R**.

```text
K → R
```

Với bảng đăng ký:

```text
(student_id, course_id)
```

xác định được tên sinh viên, tên môn, giảng viên, tên giảng viên và điểm theo tập FD đã giả định.

Tập:

```text
(student_id, course_id, student_name)
```

cũng là superkey, nhưng chứa thuộc tính thừa.

### 5.2. Candidate key

Một **candidate key** là superkey **tối thiểu**: bỏ bất kỳ thuộc tính nào khỏi nó thì không còn xác định được mọi thuộc tính.

Trong ví dụ:

```text
Candidate key: (student_id, course_id)
```

Chỉ `student_id` không biết môn và điểm; chỉ `course_id` không biết sinh viên và điểm. Cần cả hai.

Một quan hệ có thể có **nhiều candidate keys**. Vì thế không nên chỉ kiểm tra primary key được chọn trong SQL mà bỏ qua các khóa ứng viên khác.

### 5.3. Primary key và alternate key

**Primary key** là candidate key được chọn làm khóa chính trong lược đồ. Các candidate keys còn lại có thể được biểu diễn bằng `UNIQUE` và yêu cầu không NULL theo đúng nghiệp vụ.

```sql
CREATE TABLE example_students (
    student_id BIGINT PRIMARY KEY,
    student_code TEXT NOT NULL UNIQUE,
    student_name TEXT NOT NULL
);
```

Nếu cả `student_id` và `student_code` đều là định danh thực sự không trùng, bảng trên thể hiện hai khóa ứng viên; `student_id` được chọn làm primary key.

### 5.4. Prime và non-prime attribute

Một **prime attribute** xuất hiện trong **ít nhất một candidate key**. Một **non-prime attribute** không xuất hiện trong khóa ứng viên nào.

Trong quan hệ đăng ký:

```text
Prime:
  student_id, course_id

Non-prime:
  student_name, course_title,
  instructor_id, instructor_name, grade
```

Khái niệm prime rất quan trọng trong định nghĩa hình thức của **3NF**, nhất là khi quan hệ có nhiều candidate keys chồng lấn.

## 6. Attribute closure: tìm những thuộc tính được suy ra

### 6.1. Định nghĩa

**Tập thuộc tính đóng** của `X`, ký hiệu `X⁺`, là tập tất cả thuộc tính có thể suy ra từ `X` theo tập FD `F`.

Thuật toán:

```text
closure := X

repeat:
    for each FD (A → B):
        if A là tập con của closure:
            thêm các thuộc tính B vào closure
until không còn thuộc tính nào được thêm

return closure
```

Đây là thuật toán **suy luận trên tập quy tắc FD**, không phải câu SQL tự động khám phá quy tắc nghiệp vụ.

### 6.2. Tính closure của khóa ghép

Cho:

```text
F1: student_id → student_name
F2: course_id → course_title
F3: course_id → instructor_id
F4: instructor_id → instructor_name
F5: (student_id, course_id) → grade
```

Bắt đầu:

```text
X = {student_id, course_id}
```

| Bước | FD áp dụng | Thuộc tính được bổ sung |
|---|---|---|
| 0 | Khởi đầu | `student_id`, `course_id` |
| 1 | F1 | `student_name` |
| 2 | F2 | `course_title` |
| 3 | F3 | `instructor_id` |
| 4 | F4 | `instructor_name` |
| 5 | F5 | `grade` |

Kết quả:

```text
{student_id, course_id}⁺
 = {student_id, student_name,
    course_id, course_title,
    instructor_id, instructor_name, grade}
```

Tập này chứa toàn bộ thuộc tính của quan hệ, nên `(student_id, course_id)` là superkey.

Tiếp tục:

```text
{student_id}⁺
 = {student_id, student_name}

{course_id}⁺
 = {course_id, course_title,
    instructor_id, instructor_name}
```

Không tập con nào là superkey, nên cặp là **candidate key**.

### 6.3. Dùng closure để kiểm tra FD suy ra

Muốn biết `course_id → instructor_name` có được suy ra không, tính:

```text
{course_id}⁺
 = {course_id, course_title, instructor_id, instructor_name}
```

Vì chứa `instructor_name`, ta suy ra:

```text
course_id → instructor_name
```

dù FD này không xuất hiện như một dòng trong danh sách ban đầu.

## 7. Các quy tắc suy diễn FD

Các **tiên đề Armstrong** là nền tảng của việc suy luận FD.

### 7.1. Phản xạ (reflexivity)

Nếu `Y ⊆ X` thì `X → Y`.

```text
(student_id, course_id) → student_id
```

Đây là FD **tầm thường (trivial)**: vế phải đã nằm trong vế trái.

### 7.2. Gia tăng (augmentation)

Nếu `X → Y` thì `XZ → YZ`.

```text
student_id → student_name
```

suy ra:

```text
(student_id, course_id)
    → (student_name, course_id)
```

### 7.3. Bắc cầu (transitivity)

Nếu `X → Y` và `Y → Z` thì `X → Z`.

```text
course_id → instructor_id
instructor_id → instructor_name
```

suy ra:

```text
course_id → instructor_name
```

### 7.4. Một số luật suy ra khác

- **Union:** `X → Y` và `X → Z` suy ra `X → YZ`.
- **Decomposition:** `X → YZ` suy ra `X → Y` và `X → Z`.
- **Pseudotransitivity:** `X → Y` và `WY → Z` suy ra `WX → Z`.

Những quy tắc này giúp kiểm tra phụ thuộc gián tiếp, tìm khóa và nhận diện những FD thừa.

### 7.5. Minimal cover

Một **minimal/canonical cover** là cách viết gọn tập FD mà vẫn giữ khả năng suy ra cùng các phụ thuộc.

Các bước thực hành phổ biến:

1. Tách FD có nhiều thuộc tính ở vế phải thành các FD với **một thuộc tính** vế phải.
2. Loại thuộc tính thừa ở vế trái.
3. Loại các FD có thể suy ra từ các FD còn lại.

Ví dụ:

```text
course_id → course_title, instructor_id
```

được viết:

```text
course_id → course_title
course_id → instructor_id
```

Minimal cover giúp các thuật toán tổng hợp lược đồ 3NF dễ làm việc hơn; nó có thể có nhiều cách biểu diễn tương đương.

## 8. 1NF: hiểu đúng tính đơn trị của thuộc tính

**First Normal Form (1NF)** trong mô hình quan hệ cổ điển yêu cầu giá trị thuộc tính được xem là một giá trị của miền kiểu dữ liệu phù hợp, không thay thế quan hệ nghiệp vụ độc lập bằng một chuỗi danh sách khó ràng buộc.

Ví dụ:

| student_id | student_name | course_ids |
|---|---|---|
| 1 | Nguyễn An | `101,102,103` |
| 2 | Trần Bình | `101,102` |

Nếu lưu các mã môn trong một chuỗi phân cách bằng dấu phẩy:

- Khó tạo FK đến từng mã môn.
- Khó gán điểm/ngày đăng ký riêng cho mỗi môn.
- Khó tìm kiếm chính xác mã `10` mà không khớp nhầm `101`.
- Khó ngăn trùng mã trong cùng một danh sách.

Nên có:

```text
Students(student_id, student_name)
Enrollments(student_id, course_id)
```

| student_id | course_id |
|---|---|
| 1 | 101 |
| 1 | 102 |
| 1 | 103 |
| 2 | 101 |
| 2 | 102 |

### 8.1. PostgreSQL ARRAY/JSONB và 1NF

PostgreSQL có `integer[]`, `text[]`, `jsonb` và các kiểu phức hợp hợp lệ. Không nên đơn giản tuyên bố **mọi array hoặc JSON đều sai**.

Câu hỏi quan trọng là: những phần tử có cần **định danh, ràng buộc, cập nhật, JOIN và vòng đời độc lập** không?

- Danh sách môn đăng ký có điểm và FK riêng: thường dùng bảng nối.
- Metadata linh hoạt, không cần mỗi key là một quan hệ nghiệp vụ: JSONB có thể phù hợp.
- Tập tag độc lập có các rule của riêng nó: cân nhắc bảng quan hệ thay vì chỉ array.

Một bảng đạt 1NF vẫn có thể chứa **dư thừa gây bất thường**. Bảng `registrations_raw` ở phần 2 có một giá trị đơn cho mỗi ô nhưng chưa đạt những dạng chuẩn cao hơn.

## 9. 2NF: loại phụ thuộc vào một phần khóa ghép

Một quan hệ ở **2NF** khi:

1. Nó ở 1NF.
2. Mỗi **non-prime attribute** phụ thuộc đầy đủ vào các candidate keys, không phụ thuộc vào **tập con thực sự** của một candidate key.

Một **partial dependency** xuất hiện khi `X → A`, với `X` là tập con thực sự của một candidate key và `A` là non-prime attribute.

Trong `registrations_raw`, khóa ứng viên:

```text
(student_id, course_id)
```

Nhưng:

```text
student_id → student_name

course_id → course_title
course_id → instructor_id
```

Mỗi FD trên dùng **chỉ một phần** khóa ghép để xác định một thuộc tính không khóa. Đó là dấu hiệu vi phạm 2NF.

### 9.1. Phân rã để đạt 2NF

Tách thành:

```text
Students(student_id, student_name)

Courses(
    course_id,
    course_title,
    instructor_id,
    instructor_name
)

Enrollments(student_id, course_id, grade)
```

Ở `Enrollments`, điểm phụ thuộc vào cả cặp sinh viên–môn. Thông tin sinh viên và môn không còn bị lặp trong mỗi dòng đăng ký.

Nhưng `Courses` vẫn có:

```text
course_id → instructor_id
instructor_id → instructor_name
```

Đây là **phụ thuộc bắc cầu** cần xử lý tiếp ở 3NF.

### 9.2. Khóa chính đơn không tự giải quyết mọi vấn đề

Thêm cột:

```sql
registration_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
```

vào bảng gộp không làm mất việc `course_id → course_title` hoặc `instructor_id → instructor_name`. ID nhân tạo giúp định danh dòng nhưng **không xóa sự dư thừa nghiệp vụ**.

Việc xét 2NF/3NF phải dựa trên **toàn bộ FD có ý nghĩa**, không chỉ một PK mà người thiết kế chọn cho ORM.

## 10. 3NF: loại các phụ thuộc không phù hợp với khóa

### 10.1. Cách hiểu trực quan

3NF thường được tóm tắt:

> Thuộc tính không khóa phụ thuộc vào khóa, toàn bộ khóa, không phụ thuộc bắc cầu vào một thuộc tính không khóa khác.

Đây là cách nhớ hữu ích với quan hệ có một khóa ứng viên đơn giản, nhưng cần định nghĩa hình thức để xử lý các quan hệ có nhiều candidate keys.

### 10.2. Định nghĩa hình thức

Một quan hệ đạt **3NF** nếu với mọi FD **không tầm thường** `X → A` (vế phải là một thuộc tính), ít nhất một điều kiện đúng:

1. `X` là **superkey**; hoặc
2. `A` là **prime attribute** (nằm trong ít nhất một candidate key).

Định nghĩa này quan trọng vì 3NF có một ngoại lệ dành cho thuộc tính khóa mà BCNF không có.

### 10.3. Vi phạm trong Courses

Xét:

```text
Courses(
    course_id,
    course_title,
    instructor_id,
    instructor_name
)
```

Ta có:

```text
course_id → course_title
course_id → instructor_id
instructor_id → instructor_name
```

Vì một giảng viên có thể dạy **nhiều môn**, `instructor_id` không phải superkey của `Courses`; `instructor_name` cũng không phải prime attribute. FD:

```text
instructor_id → instructor_name
```

vi phạm 3NF.

Mỗi lần đổi tên giảng viên phải sửa ở nhiều dòng môn học. Cách giải quyết là tách giảng viên thành thực thể riêng.

### 10.4. Lược đồ 3NF sau phân rã

```text
Students(
    student_id PK,
    student_name
)

Instructors(
    instructor_id PK,
    instructor_name
)

Courses(
    course_id PK,
    course_title,
    instructor_id FK → Instructors
)

Enrollments(
    student_id FK → Students,
    course_id FK → Courses,
    grade,
    PK(student_id, course_id)
)
```

Sơ đồ:

~~~mermaid
erDiagram
    STUDENTS ||--o{ ENROLLMENTS : registers
    COURSES ||--o{ ENROLLMENTS : contains
    INSTRUCTORS ||--o{ COURSES : teaches
    STUDENTS {
        bigint student_id PK
        text student_name
    }
    INSTRUCTORS {
        bigint instructor_id PK
        text instructor_name
    }
    COURSES {
        bigint course_id PK
        text course_title
        bigint instructor_id FK
    }
    ENROLLMENTS {
        bigint student_id PK
        bigint course_id PK
        numeric grade
    }
~~~

Mỗi bảng có **một phạm vi sự thật rõ ràng**:

- Đổi tên sinh viên: sửa `Students`.
- Đổi tên giảng viên: sửa `Instructors`.
- Đổi môn–giảng viên phụ trách: sửa `Courses`.
- Đổi điểm sinh viên: sửa `Enrollments`.

Thêm môn chưa có sinh viên giờ có thể thực hiện mà không tạo dòng đăng ký giả. Xóa một đăng ký không xóa môn và giảng viên.

## 11. BCNF: khi mỗi determinant phải là superkey

### 11.1. Định nghĩa

**Boyce–Codd Normal Form (BCNF)** yêu cầu:

> Với mọi FD không tầm thường `X → Y`, vế trái `X` phải là **superkey**.

BCNF **mạnh hơn** 3NF:

```text
BCNF ⇒ 3NF
```

nhưng quan hệ ở 3NF chưa chắc ở BCNF.

### 11.2. Ví dụ 3NF nhưng không BCNF

Quan hệ:

```text
Teaching(student_id, course_id, instructor_id)
```

Giả định trong phạm vi mô hình:

- Một sinh viên học một môn với **tối đa một giảng viên**.
- Một giảng viên chỉ dạy **một môn**, nhưng cùng môn có thể có nhiều giảng viên.
- Một giảng viên có thể dạy nhiều sinh viên.

FD:

```text
(student_id, course_id) → instructor_id
instructor_id → course_id
```

Từ closure tìm được hai candidate keys:

```text
(student_id, course_id)
(student_id, instructor_id)
```

Cả `student_id`, `course_id`, `instructor_id` đều là **prime attributes**.

FD:

```text
instructor_id → course_id
```

không vi phạm 3NF vì `course_id` là prime. Nhưng `instructor_id` **không** là superkey (một giảng viên dạy nhiều sinh viên), nên vi phạm BCNF.

### 11.3. Phân rã và sự đánh đổi

Có thể tách:

```text
InstructorCourse(instructor_id, course_id)

StudentInstructor(student_id, instructor_id)
```

`instructor_id` là khóa của `InstructorCourse`; cặp `(student_id, instructor_id)` là khóa của `StudentInstructor`.

Phép phân rã này có thể tái dựng `Teaching` bằng JOIN qua `instructor_id` và **lossless** theo FD đã cho.

Tuy nhiên, FD gốc:

```text
(student_id, course_id) → instructor_id
```

có thể **không còn được bảo toàn bằng constraints cục bộ** của hai bảng. Nếu một sinh viên đăng ký hai giảng viên khác nhau cùng dạy môn 101, từng bảng có thể vẫn hợp lệ, nhưng JOIN tạo hai giảng viên cho cùng cặp sinh viên–môn.

Đây là ví dụ vì sao trong thiết kế thật đôi khi lựa chọn **3NF bảo toàn phụ thuộc** dễ quản lý hơn việc ép mọi quan hệ lên BCNF mà phải thêm những kiểm tra xuyên bảng phức tạp.

## 12. Phân rã nối không mất mát (lossless join)

### 12.1. Ý nghĩa

Một phép phân rã từ `R` thành các quan hệ con là **lossless** theo tập FD nếu JOIN các projection của **mọi trạng thái R hợp lệ** khôi phục đúng R, **không làm mất hoặc sinh bộ giả**.

Không được chia bảng chỉ vì “nhìn gọn hơn”.

### 12.2. Ví dụ phân rã có bộ giả

Cho:

| A | B | C |
|---|---|---|
| a1 | b1 | c1 |
| a2 | b1 | c2 |

Tách:

```text
R1(A, B)
R2(B, C)
```

R1:

| A | B |
|---|---|
| a1 | b1 |
| a2 | b1 |

R2:

| B | C |
|---|---|
| b1 | c1 |
| b1 | c2 |

JOIN trên B sinh:

```text
(a1, b1, c1)
(a1, b1, c2)  <-- bộ giả
(a2, b1, c1)  <-- bộ giả
(a2, b1, c2)
```

Hai bộ ở giữa không thuộc dữ liệu gốc. Nếu B không xác định đủ thông tin phía nào thì phép phân rã này **có thể lossy**.

### 12.3. Điều kiện kiểm tra cho phân rã nhị phân

Với hai quan hệ con `R1`, `R2`, phép phân rã là lossless theo FD nếu ít nhất một FD được suy ra:

```text
(R1 ∩ R2) → R1
```

hoặc:

```text
(R1 ∩ R2) → R2
```

Ví dụ:

```text
Courses(course_id, course_title, instructor_id, instructor_name)

R1(course_id, course_title, instructor_id)
R2(instructor_id, instructor_name)
```

Giao:

```text
R1 ∩ R2 = {instructor_id}
```

Vì `instructor_id → instructor_name`, giao xác định toàn bộ `R2`: phép phân rã **lossless** theo FD giả định.

Đây là điều kiện dựa trên **quy tắc FD**, không phải chỉ kiểm tra xem JOIN dữ liệu thử nghiệm một lần có bằng số hàng cũ hay không.

## 13. Bảo toàn phụ thuộc (dependency preservation)

### 13.1. Hai mục tiêu khác nhau

**Lossless join:** JOIN các bảng con có tái tạo đúng quan hệ cũ không?

**Dependency preservation:** các FD của quan hệ cũ có thể được bảo vệ bằng những FD/ràng buộc **trên từng bảng con**, không phải JOIN nhiều bảng mới kiểm tra được không?

Trong lược đồ 3NF của ví dụ:

| Phụ thuộc | Bảng bảo vệ |
|---|---|
| `student_id → student_name` | `Students` |
| `instructor_id → instructor_name` | `Instructors` |
| `course_id → course_title, instructor_id` | `Courses` |
| `(student_id, course_id) → grade` | `Enrollments` |

Mỗi phụ thuộc có một nơi lưu sự thật thích hợp.

### 13.2. Quan hệ giữa 3NF và BCNF

- Thuật toán tổng hợp **3NF** từ một minimal cover có thể tạo phân rã **lossless** và **dependency preserving** đối với FD.
- Phân rã **BCNF** có thể được thiết kế lossless nhưng **không bảo đảm** bảo toàn tất cả FD bằng ràng buộc trên từng bảng.
- Một thiết kế tốt không chỉ chọn tên dạng chuẩn cao nhất; nó phải cân nhắc **khả năng thực thi các bất biến dữ liệu**.

PostgreSQL không có cú pháp SQL tổng quát kiểu `ASSERT FUNCTIONAL DEPENDENCY X -> Y` để tự áp dụng mọi FD xuyên nhiều bảng. Cần biểu diễn qua PK/UNIQUE/FK, hoặc thiết kế bổ sung nếu có quy tắc phức tạp.

## 14. Tạo schema PostgreSQL theo thiết kế chuẩn hóa

Chỉ chạy trong **database lab**, không dùng schema production.

### 14.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS normalization_lab;
```

Nếu schema/bảng đã tồn tại từ lần thực hành trước, tạo database lab sạch hoặc xử lý theo quy trình của bạn; không xóa dữ liệu chưa biết nguồn gốc.

### 14.2. Bảng Students và Instructors

```sql
CREATE TABLE normalization_lab.students (
    student_id BIGINT PRIMARY KEY,
    student_name TEXT NOT NULL
);

CREATE TABLE normalization_lab.instructors (
    instructor_id BIGINT PRIMARY KEY,
    instructor_name TEXT NOT NULL
);
```

Các PK bảo đảm cùng một ID không thể có hai hàng với hai tên khác nhau.

Điều này **không cấm** hai sinh viên có tên trùng nhau. Nếu trường có mã sinh viên do tổ chức cấp, có thể khai báo thêm `UNIQUE` trên mã đó khi có quy tắc nghiệp vụ rõ ràng.

### 14.3. Bảng Courses

```sql
CREATE TABLE normalization_lab.courses (
    course_id BIGINT PRIMARY KEY,
    course_title TEXT NOT NULL,
    instructor_id BIGINT NOT NULL,
    CONSTRAINT fk_courses_instructors
        FOREIGN KEY (instructor_id)
        REFERENCES normalization_lab.instructors(instructor_id)
);
```

Một hàng `courses` chứa mã môn, tên môn và **tham chiếu** đến giảng viên. Không cần sao chép `instructor_name`: khi cần có thể JOIN đến bảng `instructors`.

### 14.4. Bảng Enrollments

```sql
CREATE TABLE normalization_lab.enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    grade NUMERIC(4,2),

    CONSTRAINT pk_enrollments
        PRIMARY KEY (student_id, course_id),

    CONSTRAINT fk_enrollments_students
        FOREIGN KEY (student_id)
        REFERENCES normalization_lab.students(student_id),

    CONSTRAINT fk_enrollments_courses
        FOREIGN KEY (course_id)
        REFERENCES normalization_lab.courses(course_id),

    CONSTRAINT chk_enrollments_grade
        CHECK (grade BETWEEN 0 AND 10)
);
```

Khóa `(student_id, course_id)` đảm bảo mỗi cặp chỉ có **tối đa một dòng đăng ký**. Hai FK bảo đảm có sinh viên và môn học tương ứng.

`grade` cho phép `NULL` để biểu diễn **chưa có điểm**. Trong PostgreSQL, điều kiện `CHECK` cho kết quả `TRUE` hoặc `UNKNOWN` đều không bị xem là vi phạm, nên `NULL` vẫn được phép nếu không có `NOT NULL`.

### 14.5. Nạp dữ liệu mẫu

```sql
INSERT INTO normalization_lab.students
    (student_id, student_name)
VALUES
    (1, 'Nguyễn An'),
    (2, 'Trần Bình');

INSERT INTO normalization_lab.instructors
    (instructor_id, instructor_name)
VALUES
    (9, 'Cô Lan'),
    (10, 'Thầy Minh');

INSERT INTO normalization_lab.courses
    (course_id, course_title, instructor_id)
VALUES
    (101, 'Cơ sở dữ liệu', 9),
    (102, 'Thuật toán', 10);

INSERT INTO normalization_lab.enrollments
    (student_id, course_id, grade)
VALUES
    (1, 101, 8.50),
    (2, 101, 7.50),
    (1, 102, 9.00),
    (2, 102, NULL);
```

Các câu `INSERT` chỉ chạy **một lần** trên những bảng trống của lab. Không chạy lại nguyên khối nếu đã có ID tương ứng.

### 14.6. JOIN để tái dựng cách nhìn cũ

```sql
SELECT
    s.student_id,
    s.student_name,
    c.course_id,
    c.course_title,
    i.instructor_id,
    i.instructor_name,
    e.grade
FROM normalization_lab.enrollments AS e
JOIN normalization_lab.students AS s
  ON s.student_id = e.student_id
JOIN normalization_lab.courses AS c
  ON c.course_id = e.course_id
JOIN normalization_lab.instructors AS i
  ON i.instructor_id = c.instructor_id
ORDER BY s.student_id, c.course_id;
```

Kết quả tương ứng bốn dòng của bảng lớn ban đầu, nhưng thông tin sinh viên/môn/giảng viên hiện chỉ được lưu **một nơi**.

## 15. Thử nghiệm bất thường đã được xử lý

### 15.1. Đổi tên giảng viên một lần

```sql
BEGIN;

UPDATE normalization_lab.instructors
SET instructor_name = 'Nguyễn Thị Lan'
WHERE instructor_id = 9;

SELECT
    c.course_id,
    c.course_title,
    i.instructor_name
FROM normalization_lab.courses AS c
JOIN normalization_lab.instructors AS i
  ON i.instructor_id = c.instructor_id
WHERE i.instructor_id = 9;

ROLLBACK;
```

Tên hiển thị mới đến từ một bản ghi `instructors`, không cần sửa mọi dòng đăng ký. `ROLLBACK` giúp giữ dữ liệu thực hành ổn định cho bài tiếp theo.

### 15.2. Thêm môn học không cần đăng ký giả

```sql
BEGIN;

INSERT INTO normalization_lab.courses
    (course_id, course_title, instructor_id)
VALUES
    (103, 'Mạng máy tính', 9);

SELECT course_id, course_title
FROM normalization_lab.courses
WHERE course_id = 103;

ROLLBACK;
```

Môn 103 có thể tồn tại trước khi có sinh viên học. Điều này giải quyết insertion anomaly.

### 15.3. Xóa đăng ký không xóa môn

```sql
BEGIN;

DELETE FROM normalization_lab.enrollments
WHERE student_id = 2 AND course_id = 102;

SELECT course_id, course_title
FROM normalization_lab.courses
WHERE course_id = 102;

ROLLBACK;
```

Môn 102 còn nguyên trong `courses` vì là một thực thể độc lập với lần đăng ký bị xóa.

### 15.4. Ngăn trùng khóa nghiệp vụ

Khi cặp `(1,101)` đã có, câu:

```sql
INSERT INTO normalization_lab.enrollments
    (student_id, course_id, grade)
VALUES (1, 101, 10.00);
```

sẽ vi phạm primary key. Đó là ràng buộc có hiệu lực khi nhiều kết nối cùng ghi, không chỉ là câu `SELECT COUNT(*)` ở ứng dụng dễ gặp race condition.

Nếu thực sự cần sửa điểm, hãy dùng `UPDATE` có điều kiện hoặc một chính sách upsert **được định nghĩa rõ**, không `ON CONFLICT DO NOTHING` để âm thầm bỏ qua thông tin quan trọng.

## 16. PostgreSQL constraints và phụ thuộc hàm

### 16.1. PRIMARY KEY

`PRIMARY KEY` kết hợp tính **duy nhất** và **không NULL**. Khi `student_id` là PK của `students`, hai dòng cùng ID không thể tồn tại với hai tên khác nhau, nên quy tắc:

```text
student_id → student_name
```

được hỗ trợ bởi schema.

### 16.2. UNIQUE và NULL

Trong PostgreSQL, `UNIQUE` mặc định cho phép **nhiều NULL** theo ngữ nghĩa của ràng buộc. Ví dụ:

```sql
CREATE TABLE example_contacts (
    contact_id BIGINT PRIMARY KEY,
    email TEXT UNIQUE
);
```

vẫn có thể có nhiều dòng `email IS NULL`. Nếu email là định danh bắt buộc, nên dùng:

```sql
CREATE TABLE required_emails (
    contact_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);
```

Ở PostgreSQL 15+, còn có:

```sql
CREATE TABLE example_nulls_not_distinct (
    id BIGINT PRIMARY KEY,
    external_code TEXT,
    CONSTRAINT uq_external_code
        UNIQUE NULLS NOT DISTINCT (external_code)
);
```

Ràng buộc này coi NULL **không phân biệt** cho mục đích uniqueness, nên chỉ cho phép tối đa một NULL ở cột tương ứng. Nhưng nếu mọi dòng bắt buộc có mã, vẫn nên thêm `NOT NULL`.

### 16.3. FOREIGN KEY

Một FK:

```sql
FOREIGN KEY (instructor_id)
REFERENCES normalization_lab.instructors(instructor_id)
```

bảo vệ sự tồn tại của thực thể được tham chiếu. Nó **không yêu cầu** tên giảng viên nằm ở bảng `courses`.

Nếu bảng cũ vẫn sao chép `instructor_name` bên cạnh `instructor_id`, thêm FK không tự đảm bảo tên sao chép luôn đúng với bảng master. Chuẩn hóa loại cột dư thừa hoặc xác định rõ nó là **snapshot lịch sử có chủ đích**.

### 16.4. CHECK

```sql
CHECK (grade BETWEEN 0 AND 10)
```

kiểm tra biểu thức trên hàng, nhưng không phải cơ chế tổng quát để kiểm tra FD xuyên nhiều hàng/bảng. PostgreSQL không tự tái kiểm tra các hàng cũ mỗi khi một hàng khác thay đổi chỉ vì một hàm truy vấn bảng khác được nhúng vào `CHECK`.

Cần ưu tiên PK/UNIQUE/FK, mô hình schema đúng và cơ chế transactional có kiểm soát khi một invariant phức tạp hơn.

### 16.5. Alternate key và expression index

Giả sử quy tắc nghiệp vụ coi email không phân biệt chữ hoa/thường:

```sql
CREATE UNIQUE INDEX uq_students_email_normalized
ON normalization_lab.students (lower(email));
```

Đây là ví dụ **unique expression index**, chỉ có nghĩa khi bảng đã có cột `email`. Không nên chạy trước khi thêm cột đó. Nó khác ràng buộc `UNIQUE` cột thông thường và có những giới hạn khi muốn dùng làm khóa FK.

Quy tắc chuẩn hóa email, khoảng trắng, collation và tái sử dụng email phải được xác định trước. Không thể tự khẳng định `lower(email)` là định danh đúng cho mọi nghiệp vụ.

### 16.6. Surrogate key không thay thế business key

Một bảng có thể thêm `registration_id BIGINT GENERATED ... AS IDENTITY` để tiện tham chiếu, nhưng nếu nghiệp vụ vẫn yêu cầu mỗi cặp sinh viên–môn có một đăng ký thì **vẫn cần**:

```sql
UNIQUE (student_id, course_id)
```

Khóa nhân tạo không xóa quy tắc FD, và cũng không tự sửa update anomaly nếu dữ liệu mô tả bị sao chép.

## 17. Chuẩn bị bảng nguồn để luyện migration

Để khảo sát dữ liệu cũ, tạo bảng raw riêng trên lab:

```sql
CREATE TABLE normalization_lab.registration_raw (
    student_id BIGINT NOT NULL,
    student_name TEXT NOT NULL,
    course_id BIGINT NOT NULL,
    course_title TEXT NOT NULL,
    instructor_id BIGINT NOT NULL,
    instructor_name TEXT NOT NULL,
    grade NUMERIC(4,2)
);

INSERT INTO normalization_lab.registration_raw VALUES
    (1, 'Nguyễn An', 101, 'Cơ sở dữ liệu', 9, 'Cô Lan', 8.50),
    (2, 'Trần Bình', 101, 'Cơ sở dữ liệu', 9, 'Cô Lan', 7.50),
    (1, 'Nguyễn An', 102, 'Thuật toán', 10, 'Thầy Minh', 9.00),
    (2, 'Trần Bình', 102, 'Thuật toán', 10, 'Thầy Minh', NULL);
```

Trong hệ thống thật, nguồn có thể đã chứa mâu thuẫn; **phải phát hiện trước khi đặt khóa mới**. Không lấy dữ liệu sạch của bài tập để giả định mọi database production đều hợp lệ.

## 18. Phát hiện vi phạm FD bằng SQL

### 18.1. student_id → student_name

```sql
SELECT student_id,
       COUNT(DISTINCT student_name) AS name_variations
FROM normalization_lab.registration_raw
GROUP BY student_id
HAVING COUNT(DISTINCT student_name) > 1;
```

Nếu trả dòng, cùng mã sinh viên gắn với nhiều tên. Cần xác định tên đúng, thời điểm hiệu lực và nguồn dữ liệu.

`COUNT(DISTINCT ...)` **bỏ qua SQL NULL**. Bộ dữ liệu lab dùng `student_name NOT NULL`; ở nguồn nullable cần bổ sung chính sách kiểm tra và biểu diễn dữ liệu thiếu, không xem số đếm bằng 1 là bằng chứng tuyệt đối.

### 18.2. course_id → course_title, instructor_id

```sql
SELECT
    course_id,
    COUNT(DISTINCT course_title) AS title_variations,
    COUNT(DISTINCT instructor_id) AS instructor_variations
FROM normalization_lab.registration_raw
GROUP BY course_id
HAVING COUNT(DISTINCT course_title) > 1
    OR COUNT(DISTINCT instructor_id) > 1;
```

Nếu một môn có nhiều giảng viên, trước hết hỏi liệu **mô hình thiếu học kỳ/lớp** hay dữ liệu thật sự bị nhập sai. Không chọn tùy ý `MAX(instructor_id)` để che lỗi.

### 18.3. instructor_id → instructor_name

```sql
SELECT instructor_id,
       COUNT(DISTINCT instructor_name) AS name_variations
FROM normalization_lab.registration_raw
GROUP BY instructor_id
HAVING COUNT(DISTINCT instructor_name) > 1;
```

Nếu tên đổi theo thời gian, có thể cần danh mục tên hiện tại và bảng lịch sử thay đổi tên, thay vì quy định tên bất biến mãi mãi.

### 18.4. Trùng candidate key

```sql
SELECT student_id, course_id,
       COUNT(*) AS duplicate_rows
FROM normalization_lab.registration_raw
GROUP BY student_id, course_id
HAVING COUNT(*) > 1;
```

Cặp trùng có thể là bản ghi kỹ thuật lặp, hoặc **lần học lại hợp lệ**. Cần hiểu nguyên nhân trước khi áp đặt `PRIMARY KEY (student_id, course_id)`.

### 18.5. Kết luận từ truy vấn kiểm tra

Những truy vấn trên có thể **bác bỏ** một FD nếu tìm thấy vi phạm thực tế, nhưng không chứng minh FD đúng cho **mọi trạng thái tương lai** nếu không có ràng buộc và xác nhận nghiệp vụ.

## 19. Migration từ raw sang các bảng chuẩn hóa

Giả sử dữ liệu nguồn đã được làm sạch, FD đã được xác nhận, và bảng đích **chưa có dữ liệu**. Khi đó có thể nạp theo thứ tự:

```sql
-- Bảng sinh viên.
INSERT INTO normalization_lab.students
    (student_id, student_name)
SELECT DISTINCT student_id, student_name
FROM normalization_lab.registration_raw;

-- Bảng giảng viên.
INSERT INTO normalization_lab.instructors
    (instructor_id, instructor_name)
SELECT DISTINCT instructor_id, instructor_name
FROM normalization_lab.registration_raw;

-- Bảng môn học.
INSERT INTO normalization_lab.courses
    (course_id, course_title, instructor_id)
SELECT DISTINCT course_id, course_title, instructor_id
FROM normalization_lab.registration_raw;

-- Bảng đăng ký.
INSERT INTO normalization_lab.enrollments
    (student_id, course_id, grade)
SELECT student_id, course_id, grade
FROM normalization_lab.registration_raw;
```

**Không chạy khối nạp này trên cùng bộ bảng đã chứa các dòng demo của phần 14.5.** Đây là **phương án nạp thay thế** trên schema lab sạch. Chạy chồng lên sẽ gây lỗi duplicate key.

Với một migration có tính nhất quán, nên dùng transaction và công cụ migration phù hợp, xử lý lỗi, kiểm tra tập dữ liệu và kế hoạch chuyển ghi. Đừng thêm `ON CONFLICT DO NOTHING` chỉ để tất cả câu SQL “chạy qua” trong khi có thể đang bỏ mất dữ liệu mâu thuẫn.

### 19.1. Thứ tự cha → con

- `Students` và `Instructors` không phụ thuộc FK vào các bảng khác trong mô hình.
- `Courses` cần giảng viên đã tồn tại.
- `Enrollments` cần sinh viên và môn đã tồn tại.

Do đó nạp bảng cha trước bảng con giúp ràng buộc FK có hiệu lực trong quá trình chuyển đổi.

### 19.2. Kiểm tra số dòng

```sql
SELECT COUNT(*) AS raw_count
FROM normalization_lab.registration_raw;
```

Và:

```sql
SELECT COUNT(*) AS reconstructed_count
FROM normalization_lab.enrollments AS e
JOIN normalization_lab.students AS s
  ON s.student_id = e.student_id
JOIN normalization_lab.courses AS c
  ON c.course_id = e.course_id
JOIN normalization_lab.instructors AS i
  ON i.instructor_id = c.instructor_id;
```

Trong dữ liệu mẫu không có duplicate, hai số nên bằng nhau. Nhưng **số dòng bằng nhau chưa đủ chứng minh dữ liệu giống nhau**: có thể một dòng bị thay bằng dòng khác.

### 19.3. Đối soát bằng EXCEPT

Khi hai phía thuộc **cùng mốc dữ liệu**:

```sql
WITH reconstructed AS (
    SELECT
        s.student_id, s.student_name,
        c.course_id, c.course_title,
        i.instructor_id, i.instructor_name,
        e.grade
    FROM normalization_lab.enrollments AS e
    JOIN normalization_lab.students AS s
      ON s.student_id = e.student_id
    JOIN normalization_lab.courses AS c
      ON c.course_id = e.course_id
    JOIN normalization_lab.instructors AS i
      ON i.instructor_id = c.instructor_id
)
SELECT *
FROM normalization_lab.registration_raw
EXCEPT
SELECT *
FROM reconstructed;
```

Và chiều ngược:

```sql
WITH reconstructed AS (
    SELECT
        s.student_id, s.student_name,
        c.course_id, c.course_title,
        i.instructor_id, i.instructor_name,
        e.grade
    FROM normalization_lab.enrollments AS e
    JOIN normalization_lab.students AS s
      ON s.student_id = e.student_id
    JOIN normalization_lab.courses AS c
      ON c.course_id = e.course_id
    JOIN normalization_lab.instructors AS i
      ON i.instructor_id = c.instructor_id
)
SELECT *
FROM reconstructed
EXCEPT
SELECT *
FROM normalization_lab.registration_raw;
```

Hai hướng không có kết quả là bằng chứng rằng **tập các bộ** tương đương trong snapshot đang so. Nhưng `EXCEPT` mặc định dùng ngữ nghĩa tập hợp và có thể **bỏ qua sự khác biệt về số lần xuất hiện của các dòng trùng hệt**. Khi cần bảo toàn multiplicity, dùng các kiểm tra nhóm/đếm và cân nhắc `EXCEPT ALL`.

Trong quy trình thật, nếu raw và target vẫn tiếp tục ghi, phải có snapshot hoặc cutover chốt mốc nhất quán, nếu không có thể thấy khác biệt do thời gian chứ chưa chắc do lỗi tách bảng.

## 20. Chuyển ứng dụng sang schema mới

Trước khi tách bảng, ứng dụng có thể chỉ đọc:

```sql
SELECT *
FROM normalization_lab.registration_raw
WHERE student_id = 1;
```

Sau chuẩn hóa, cần các câu JOIN phù hợp hoặc một view tương thích:

```sql
CREATE VIEW normalization_lab.v_registration_detail AS
SELECT
    e.student_id,
    s.student_name,
    e.course_id,
    c.course_title,
    c.instructor_id,
    i.instructor_name,
    e.grade
FROM normalization_lab.enrollments AS e
JOIN normalization_lab.students AS s
  ON s.student_id = e.student_id
JOIN normalization_lab.courses AS c
  ON c.course_id = e.course_id
JOIN normalization_lab.instructors AS i
  ON i.instructor_id = c.instructor_id;
```

View thuận tiện cho các truy vấn đọc nhưng **không tự giải quyết cách ghi** vào nhiều bảng mới. Ứng dụng phải biết thao tác với đúng thực thể và transaction.

### 20.1. Những bước migration production

Một quy trình có thể gồm:

1. Lưu backup và kiểm tra khả năng khôi phục.
2. Xác định source of truth, FD và những phụ thuộc ứng dụng.
3. Chạy các kiểm tra mâu thuẫn, xác nhận cách làm sạch.
4. Tạo bảng mới và constraints theo migration script có version.
5. Backfill trên snapshot/điểm dữ liệu được kiểm soát.
6. Đối soát dữ liệu hai chiều, row count, tổng hợp và FK.
7. Chuyển ứng dụng đọc/ghi trong cửa sổ thay đổi phù hợp.
8. Xử lý những ghi phát sinh trong giai đoạn backfill/cutover.
9. Theo dõi lỗi, độ trễ, khóa và tính đúng đắn sau chuyển đổi.
10. Chỉ ngừng dùng schema cũ khi đã có bằng chứng thành công và phương án quay lui phù hợp.

Nếu có **dual-write**, có thể xảy ra ghi thành công vào bảng cũ nhưng lỗi ở bảng mới. Cần cơ chế transaction, idempotency, đồng bộ/đối soát và xử lý lỗi được thiết kế trước.

PostgreSQL có transaction cho nhiều thao tác DDL, nhưng thay PK/FK/INDEX trên bảng lớn có thể tốn thời gian và tạo lock. `CREATE INDEX CONCURRENTLY` hữu ích trong một số tình huống nhưng **không được chạy trong transaction block** thông thường; triển khai thực tế cần runbook phù hợp.

## 21. Chuẩn hóa và dữ liệu lịch sử

### 21.1. Khóa có thể phải thêm chiều thời gian

Mô hình đăng ký ban đầu dùng:

```text
(student_id, course_id) → grade
```

Nếu có học kỳ và học lại, một thiết kế mới có thể là:

```sql
CREATE TABLE normalization_lab.enrollment_attempts (
    enrollment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    student_id BIGINT NOT NULL
        REFERENCES normalization_lab.students(student_id),
    course_id BIGINT NOT NULL
        REFERENCES normalization_lab.courses(course_id),
    term_code TEXT NOT NULL,
    attempt_no INTEGER NOT NULL CHECK (attempt_no >= 1),
    grade NUMERIC(4,2) CHECK (grade BETWEEN 0 AND 10),
    CONSTRAINT uq_enrollment_attempt
        UNIQUE (student_id, course_id, term_code, attempt_no)
);
```

Từ đó:

```text
(student_id, course_id, term_code, attempt_no) → grade
```

là một FD có thể đúng theo quy tắc mới. Nhưng nếu khóa nghiệp vụ thực sự khác, phải sửa thiết kế cho phù hợp.

### 21.2. Giá hiện tại và giá tại thời điểm giao dịch

Trong thương mại điện tử:

```text
product_id → current_price
```

có thể đúng ở **catalog hiện hành**. Nhưng giá của dòng đơn hàng cần giữ lại **tại thời điểm đặt hàng**, nên:

```text
(order_id, line_no) → unit_price_at_purchase
```

là một sự thật khác. Lưu `unit_price_at_purchase` trong `order_items` không phải mặc nhiên là dư thừa sai; đó là dữ liệu lịch sử độc lập với giá hiện tại.

Tương tự, tên người nhận, địa chỉ giao hàng và thuế suất trên hóa đơn có thể phải giữ snapshot tại lúc phát sinh chứng từ.

### 21.3. Đừng để thay đổi hiện tại làm viết lại lịch sử không chủ ý

Nếu báo cáo tháng trước phải hiển thị **tên/nhóm khách tại thời điểm mua**, JOIN đơn lịch sử với bản ghi khách **hiện tại** có thể làm thay đổi báo cáo sau khi khách đổi tên/segment.

Cần quy định rõ báo cáo yêu cầu dữ liệu **hiện tại** hay **as-of**. Một số hệ thống dùng bảng lịch sử có thời gian hiệu lực, event log hoặc slowly changing dimensions để giải quyết.

## 22. Nhiều-nhiều và phụ thuộc đa trị

### 22.1. Bảng nối là cách biểu diễn quan hệ N–N

Sinh viên có nhiều môn và môn có nhiều sinh viên. Bảng `enrollments` diễn đạt **mỗi quan hệ đăng ký là một hàng** và chứa các thuộc tính của mối quan hệ như `grade`.

Không nên đặt danh sách môn trong cột `students.course_ids` nếu mỗi đăng ký cần FK, điểm và trạng thái riêng.

### 22.2. Phụ thuộc đa trị và 4NF

Giả sử:

```text
PersonSkillsLanguages(person_id, skill, language)
```

Một người có hai kỹ năng `{Java, SQL}` và hai ngôn ngữ `{Vietnamese, English}` độc lập. Nếu lưu chung trong một bảng, có thể xuất hiện tích kết hợp:

| person_id | skill | language |
|---|---|---|
| 1 | Java | Vietnamese |
| 1 | Java | English |
| 1 | SQL | Vietnamese |
| 1 | SQL | English |

Đây là ví dụ cho **phụ thuộc đa trị (multivalued dependency, MVD)**:

```text
person_id ↠ skill
person_id ↠ language
```

Nếu các tập hoàn toàn độc lập, nên tách:

```text
PersonSkills(person_id, skill)
PersonLanguages(person_id, language)
```

Đó là trực giác của **4NF**: xử lý những MVD độc lập không thể giải thích đầy đủ chỉ bằng FD.

Nếu mỗi cặp kỹ năng–ngôn ngữ lại có một **ý nghĩa nghiệp vụ thực** (ví dụ giảng viên dạy kỹ năng nào bằng ngôn ngữ nào), tách như trên có thể làm mất liên hệ đúng. Một lần nữa, **ngữ nghĩa** quyết định cấu trúc.

## 23. Phi chuẩn hóa có chủ đích

**Phi chuẩn hóa (denormalization)** là lưu thêm dữ liệu hoặc kết quả tổng hợp để giảm chi phí đọc. Nó không phải mặc định sai, nhưng mang theo trách nhiệm giữ dữ liệu nhất quán.

Ví dụ một dashboard tính thống kê số sinh viên theo môn và ngày có thể dùng bảng tổng hợp:

```sql
CREATE TABLE normalization_lab.daily_course_stats (
    course_id BIGINT NOT NULL
        REFERENCES normalization_lab.courses(course_id),
    report_day DATE NOT NULL,
    enrollment_count BIGINT NOT NULL CHECK (enrollment_count >= 0),
    PRIMARY KEY (course_id, report_day)
);
```

Nếu bảng tổng hợp được duy trì từ `enrollments`, cần có:

- Quy tắc chính xác cho chỉ số.
- Cơ chế cập nhật/recompute khi dữ liệu nguồn đổi.
- Đối soát và xử lý ghi trễ hoặc lỗi.
- Độ mới tối đa được chấp nhận.
- Kế hoạch rebuild khi mất đồng bộ.

PostgreSQL cũng có **materialized view** lưu kết quả đã tính, nhưng materialized view trong PostgreSQL core **không tự động incremental refresh** mỗi khi bảng nguồn thay đổi.

### 23.1. Đừng phi chuẩn hóa chỉ vì JOIN

Các JOIN qua PK/FK được index phù hợp thường rất hiệu quả. Sao chép `instructor_name` vào hàng triệu dòng đăng ký có thể khiến mỗi lần đổi tên cần cập nhật lượng dữ liệu lớn.

Trước khi đưa dữ liệu lặp vào nhiều nơi, hãy dùng `EXPLAIN` và thử tải thực tế để biết điểm nghẽn có thật không.

### 23.2. Khi snapshot là dữ liệu đúng

Tên sản phẩm **trên hóa đơn đã chốt**, địa chỉ nhận hàng **tại lúc giao**, giá bán **tại thời điểm mua** là dữ liệu lịch sử. Chúng có thể cố tình khác thông tin catalog/master hiện tại và có ngữ nghĩa rõ ràng.

Chuẩn hóa không đòi xóa những snapshot hợp lệ; nó đòi xác định **chúng phụ thuộc vào khóa nghiệp vụ và thời điểm nào**.

## 24. Quy trình quyết định chuẩn hóa

~~~mermaid
flowchart TD
    A["Thu thập các sự thật nghiệp vụ"] --> B["Xác định một hàng biểu diễn điều gì"]
    B --> C["Liệt kê FD, ngoại lệ và chiều thời gian"]
    C --> D["Tính closure, tìm candidate keys"]
    D --> E["Kiểm tra 1NF / phụ thuộc bộ phận"]
    E --> F["Kiểm tra phụ thuộc bắc cầu / 3NF"]
    F --> G{"Cần BCNF không?"}
    G -- "Có" --> H["Đánh giá determinant và phân rã"]
    G -- "Không" --> I["Giữ thiết kế 3NF"]
    H --> J["Kiểm tra lossless và preservation"]
    I --> J
    J --> K["Thiết kế PK/UNIQUE/FK/CHECK"]
    K --> L["Kiểm tra dữ liệu nguồn, backfill và đối soát"]
    L --> M["Đo workload và triển khai có kiểm soát"]
~~~

Các câu hỏi cần trả lời:

1. Mỗi hàng thuộc **thực thể** hay **quan hệ** nào?
2. Thuộc tính nào xác định duy nhất thuộc tính khác?
3. FD có đúng khi đổi tên, đổi giảng viên, học lại hoặc lưu lịch sử không?
4. Tập thuộc tính nào là candidate key, đã kiểm tra tính tối thiểu chưa?
5. Có update/insertion/deletion anomalies không?
6. Tách bảng có lossless không?
7. FD quan trọng có bảo vệ bằng constraint ở bảng con được không?
8. Lược đồ mới có phù hợp cách ứng dụng đọc và ghi không?
9. Có bằng chứng hiệu năng trước khi chủ động phi chuẩn hóa không?

## 25. Các sai lầm thường gặp

### 25.1. Suy ra FD từ tập mẫu nhỏ

Một thuộc tính tình cờ chỉ có một giá trị hôm nay không có nghĩa nó được xác định trong mọi trạng thái hợp lệ. Hỏi nghiệp vụ trước, dùng dữ liệu để tìm **phản ví dụ**, không để thay thế định nghĩa.

### 25.2. Dùng tên hoặc mô tả làm khóa

Hai người có thể trùng tên, hai sản phẩm có thể trùng mô tả. Chọn khóa dựa trên quy tắc duy nhất thực sự và các ràng buộc ứng dụng.

### 25.3. Chỉ xét primary key, bỏ qua alternate key

Một quan hệ có nhiều candidate keys. 2NF/3NF hình thức xét **các candidate keys**, không chỉ PK mà DBA chọn.

### 25.4. Thêm ID tự tăng rồi coi là 3NF

ID nhân tạo tiện cho tham chiếu nhưng không xóa việc `course_id` xác định tên môn và giảng viên. Bất thường cập nhật vẫn tồn tại nếu tên bị sao chép.

### 25.5. Quên NULL trong ràng buộc UNIQUE

`email TEXT UNIQUE` mặc định cho phép nhiều NULL. Nếu cột bắt buộc có giá trị, thêm `NOT NULL`.

### 25.6. Dùng DISTINCT để che dữ liệu không nhất quán

`SELECT DISTINCT student_id, student_name` không xử lý được khi cùng ID xuất hiện với hai tên. Cần tìm nguyên nhân và chính sách làm sạch.

### 25.7. Tách bảng nhưng JOIN tạo bộ giả

Không phải mọi phân rã đều lossless. Phải phân tích giao thuộc tính và FD, rồi kiểm thử các trường hợp dữ liệu thực tế.

### 25.8. Đạt BCNF nhưng mất bảo toàn phụ thuộc

Một FD không còn bảo vệ được bằng constraint cục bộ có thể trở nên khó thực thi khi ghi đồng thời. Chọn thiết kế có khả năng duy trì quy tắc thật.

### 25.9. Quên chiều thời gian

`course_id → instructor_id` có thể đúng cho hiện tại nhưng sai cho toàn lịch sử. Khóa phải phản ánh học kỳ, lớp hoặc version khi cần.

### 25.10. Xóa giá lịch sử vì giống giá catalog

Giá bán trên chứng từ phụ thuộc đơn hàng/lượt mua, không phải nhất thiết phụ thuộc giá sản phẩm hiện tại. Tách đúng sự thật lịch sử khỏi dữ liệu master.

### 25.11. Phi chuẩn hóa không có cơ chế đồng bộ

Nếu sao chép một tên hoặc tổng tiền để tăng tốc, phải có người/cơ chế chịu trách nhiệm cập nhật, khôi phục, đối soát và theo dõi độ trễ.

### 25.12. Coi số dòng bằng nhau là migration thành công

Hai tập dữ liệu có cùng số dòng vẫn có thể khác nội dung. Cần so bộ hai chiều, số lần xuất hiện, ràng buộc và kết quả nghiệp vụ trên cùng mốc.

## 26. Bài tập thực hành

### Bài 1 — Xác định FD trong thư viện

Cho:

```text
Borrow(
    borrower_id, borrower_name,
    book_copy_id, book_title,
    borrow_date, due_date
)
```

Giả định mỗi bản sao sách có một tiêu đề hiện hành; một người có thể mượn lại cùng bản sao vào những ngày khác nhau. Hãy viết các FD hợp lý và giải thích vì sao `(borrower_id, book_copy_id)` chưa chắc là candidate key của lịch sử mượn.

### Bài 2 — Tính closure

Cho quan hệ `R(A,B,C,D,E)` và:

```text
A → B
C → D
D → E
(A,C) → E
```

Tính `{A,C}⁺`, `{A}⁺`, `{C}⁺`; xác định candidate key và một FD có thể dư thừa.

### Bài 3 — 1NF và danh sách số điện thoại

Bảng `employees(employee_id, name, phones)` chứa `phones = '090...,091...'`. Thiết kế bảng điện thoại riêng có khóa ngăn một nhân viên lưu trùng cùng số.

### Bài 4 — 2NF

`order_items(order_id, product_id, product_name, quantity, unit_price_at_order)` có candidate key `(order_id, product_id)`. Giả định `product_id → product_name`. Thuộc tính nào phụ thuộc bộ phận? Tách thế nào?

### Bài 5 — 3NF

Với `Courses(course_id, course_title, instructor_id, instructor_name)`, chỉ ra FD vi phạm 3NF và thiết kế bảng giảng viên riêng.

### Bài 6 — 3NF và BCNF

Với:

```text
Teaching(student_id, course_id, instructor_id)

(student_id, course_id) → instructor_id
instructor_id → course_id
```

Tìm các candidate keys; giải thích 3NF nhưng không BCNF; chỉ ra FD có thể bị mất preservation sau phân rã BCNF.

### Bài 7 — Lossless join

Quan hệ `R(A,B,C)` tách thành `R1(A,B)`, `R2(B,C)`. Nếu có `B → C`, phép phân rã lossless không? Nếu không có FD nào đảm bảo, tạo hai dòng làm JOIN sinh bộ giả.

### Bài 8 — SQL kiểm tra FD

Viết SQL tìm các `course_id` có nhiều `course_title` trong bảng raw. Nếu không có kết quả, đã chứng minh FD đúng cho tương lai chưa?

### Bài 9 — UNIQUE và NULL

Vì sao `email TEXT UNIQUE` không có nghĩa email là alternate key bắt buộc trong PostgreSQL? Viết DDL cho email không NULL và duy nhất.

### Bài 10 — Bốn bảng chuẩn hóa

Viết DDL cho `students`, `instructors`, `courses`, `enrollments`, có PK/FK và điểm từ 0 đến 10 hoặc chưa có điểm.

### Bài 11 — Học lại môn

Nếu sinh viên có thể học cùng môn ở hai học kỳ, vì sao `PRIMARY KEY(student_id,course_id)` không đủ? Đề xuất một khóa hoặc ràng buộc nghiệp vụ mới.

### Bài 12 — Kiểm chứng migration

Hai phía raw và JOIN bảng mới có cùng 10.000 hàng. Liệt kê ít nhất bốn kiểm tra bổ sung để tránh bỏ sót dòng sai, duplicate hoặc dữ liệu thay đổi trong khi chuyển đổi.

### Bài 13 — Phi chuẩn hóa

Dashboard thường xuyên tính số lượt đăng ký và điểm trung bình theo giảng viên trên dữ liệu rất lớn. Có nên sao chép tên giảng viên vào mọi dòng đăng ký để tránh JOIN? Đề xuất giải pháp dựa trên cả hiệu năng và tính đúng đắn.

## 27. Gợi ý lời giải

### Bài 1

Có thể xác lập:

```text
borrower_id → borrower_name
book_copy_id → book_title
(borrower_id, book_copy_id, borrow_date) → due_date
```

FD cuối chỉ đúng nếu mỗi người mượn một bản sao tối đa một lần trong một ngày. Nếu có nhiều lượt cùng ngày, cần `borrow_id` hoặc `attempt_no`. Cặp `(borrower_id,book_copy_id)` không đủ nếu có mượn lại ở ngày khác.

### Bài 2

```text
{A,C}⁺ = {A,B,C,D,E}
{A}⁺   = {A,B}
{C}⁺   = {C,D,E}
```

`(A,C)` là candidate key. FD `(A,C) → E` dư thừa vì `C → D` và `D → E` suy ra `C → E`, rồi suy ra `(A,C) → E`.

### Bài 3

```sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    employee_name TEXT NOT NULL
);

CREATE TABLE employee_phones (
    employee_id BIGINT NOT NULL REFERENCES employees(employee_id),
    phone_number TEXT NOT NULL,
    PRIMARY KEY (employee_id, phone_number)
);
```

PK chặn **một nhân viên có cùng số hai lần**. Nếu một số không được thuộc hai nhân viên, thêm `UNIQUE(phone_number)` là quy tắc riêng phải xác nhận.

### Bài 4

`product_id → product_name` là phụ thuộc bộ phận của khóa ghép. Tách:

```text
Products(product_id, product_name)
OrderItems(order_id, product_id, quantity, unit_price_at_order)
```

`unit_price_at_order` là giá chốt cho dòng đơn, không tự đồng bộ theo giá catalog hiện hành.

### Bài 5

FD `instructor_id → instructor_name` có determinant không phải superkey của `Courses` và vế phải không là prime. Tách:

```text
Instructors(instructor_id PK, instructor_name)
Courses(course_id PK, course_title, instructor_id FK)
```

### Bài 6

Candidate keys: `(student_id,course_id)` và `(student_id,instructor_id)`. `course_id` là prime; `instructor_id → course_id` được 3NF cho phép nhưng vi phạm BCNF do `instructor_id` không là superkey. Sau tách `InstructorCourse` và `StudentInstructor`, FD `(student_id,course_id) → instructor_id` có thể không kiểm tra cục bộ được.

### Bài 7

Nếu `B → C`, giao `R1 ∩ R2 = {B}` xác định toàn bộ `R2` nên phân rã lossless. Không có FD phù hợp, lấy `(a1,b1,c1)`, `(a2,b1,c2)`; JOIN hai projection sinh thêm `(a1,b1,c2)` và `(a2,b1,c1)`.

### Bài 8

```sql
SELECT course_id, COUNT(DISTINCT course_title) AS title_count
FROM normalization_lab.registration_raw
GROUP BY course_id
HAVING COUNT(DISTINCT course_title) > 1;
```

Không có kết quả chỉ nói rằng **chưa phát hiện vi phạm** trong dữ liệu quan sát (với giả định NULL hợp lý); FD vẫn cần nghiệp vụ xác nhận và schema bảo vệ.

### Bài 9

```sql
CREATE TABLE contacts (
    contact_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);
```

`NOT NULL` loại giá trị thiếu, `UNIQUE` bảo vệ tính duy nhất theo quy tắc so sánh của cột. Nếu cần không phân biệt hoa/thường, phải thêm thiết kế phù hợp.

### Bài 10

Một đáp án là bốn bảng ở mục 14, đặc biệt:

```sql
CREATE TABLE normalization_lab.enrollments (
    student_id BIGINT NOT NULL
        REFERENCES normalization_lab.students(student_id),
    course_id BIGINT NOT NULL
        REFERENCES normalization_lab.courses(course_id),
    grade NUMERIC(4,2) CHECK (grade BETWEEN 0 AND 10),
    PRIMARY KEY (student_id, course_id)
);
```

Không đặt `NOT NULL` cho `grade` khi muốn biểu diễn chưa có điểm.

### Bài 11

Một khóa có thể là `(student_id, course_id, term_id)` nếu mỗi học kỳ chỉ có một lần học. Nếu có nhiều lần trong cùng kỳ, thêm `attempt_no` hoặc một `enrollment_id` và unique constraint nghiệp vụ phù hợp.

### Bài 12

Cần: `EXCEPT` hai chiều để so các bộ; `EXCEPT ALL` hoặc nhóm/đếm để kiểm tra multiplicity; kiểm tra FK/UNIQUE/NULL; so aggregate nghiệp vụ; kiểm tra cùng snapshot/mốc dữ liệu; smoke test ứng dụng mới và theo dõi những ghi phát sinh trong giai đoạn chuyển.

### Bài 13

Không nên mặc định lặp `instructor_name` chỉ để tránh JOIN. Trước hết dùng PK/FK, index và `EXPLAIN` để đo. Nếu truy vấn tổng hợp rất nặng, cân nhắc bảng aggregate/materialized view với chính sách refresh và đối soát. Nếu tên phải là tên **tại thời điểm giảng dạy**, lưu snapshot có ý nghĩa lịch sử rõ ràng.

## 28. Kết luận

**Phụ thuộc hàm** diễn đạt quy tắc `X → Y` cho mọi trạng thái dữ liệu hợp lệ. Từ đó ta tính **attribute closure**, tìm **candidate keys** và phát hiện những cột đang được đặt sai nơi chịu trách nhiệm.

**1NF** xác định cách biểu diễn giá trị hợp lý; **2NF** xử lý phụ thuộc bộ phận; **3NF** xử lý các FD không phù hợp với khóa, có ngoại lệ hình thức đối với prime attribute; **BCNF** yêu cầu mỗi determinant của FD không tầm thường là superkey. Một phép phân rã phải cân nhắc **lossless join** và **dependency preservation**, không chỉ số bảng sinh ra.

Trong PostgreSQL, `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, `FOREIGN KEY` và `CHECK` giúp bảo vệ mô hình. Nhưng không constraint nào có thể thay cho việc hiểu **phạm vi nghiệp vụ, chiều thời gian và ý nghĩa của mỗi hàng**. Thêm ID tự tăng hay gọi `SELECT DISTINCT` không tự sửa được các phụ thuộc bị hiểu sai.

Quy trình có thể áp dụng lâu dài là: **xác định sự thật và FD → tìm khóa → chuẩn hóa → thực thi constraints → kiểm tra dữ liệu nguồn → migration có đối soát → đo workload → phi chuẩn hóa có chủ đích khi thật sự cần**.
