# Phân biệt 3NF với BCNF bằng ví dụ có nhiều khóa ứng viên

Một quan hệ có thể **đạt dạng chuẩn thứ ba (Third Normal Form, 3NF)** nhưng **chưa đạt dạng chuẩn Boyce–Codd (Boyce–Codd Normal Form, BCNF)**. Điểm khác biệt thường lộ rõ khi quan hệ có **nhiều khóa ứng viên** và có phụ thuộc hàm mà vế phải là thuộc tính thuộc một khóa ứng viên, dù vế trái không phải siêu khóa.

Trong chương **Chuẩn hóa** của mô-đun **DATABASE_DATA_MODELING**, việc phân biệt hai dạng chuẩn giúp chuyển yêu cầu nghiệp vụ thành khóa, phụ thuộc hàm và ràng buộc có thể kiểm chứng. Bài này tập trung vào **đối chiếu trực tiếp 3NF và BCNF bằng các ví dụ nhiều khóa ứng viên**, giải thích cách tính bao đóng, cách phân rã và vì sao lựa chọn dạng chuẩn còn liên quan đến khả năng bảo toàn quy tắc nghiệp vụ.

## 1. Điểm khác biệt chỉ nằm ở một điều kiện, nhưng hậu quả thiết kế đáng kể

Giả sử **R** là một quan hệ và **X → A** là một phụ thuộc hàm **không tầm thường** (A không thuộc X).

| Dạng chuẩn | Điều kiện phải đúng với **mọi X → A không tầm thường** | Câu hỏi thực hành |
| --- | --- | --- |
| **3NF** | **X là siêu khóa, hoặc A là thuộc tính nguyên tố** | Nếu X không là siêu khóa, A có thuộc ít nhất một khóa ứng viên không? |
| **BCNF** | **X phải là siêu khóa** | X có xác định được toàn bộ hàng không? |

Các khái niệm trong điều kiện:

- **Phụ thuộc hàm X → A:** trong mọi trạng thái hợp lệ, hai hàng có cùng X phải có cùng A; đây là quy tắc nghiệp vụ, không phải trùng hợp ở dữ liệu mẫu.
- **Siêu khóa (superkey):** tập thuộc tính xác định duy nhất toàn bộ hàng.
- **Khóa ứng viên (candidate key):** siêu khóa tối thiểu, bỏ bất kỳ thành phần nào đều không còn là siêu khóa.
- **Thuộc tính nguyên tố (prime attribute):** thuộc **ít nhất một** khóa ứng viên, kể cả khóa không được chọn làm khóa chính.
- **Thuộc tính không nguyên tố (non-prime attribute):** không thuộc bất kỳ khóa ứng viên nào.

Từ định nghĩa, **BCNF mạnh hơn 3NF**: quan hệ đạt BCNF thì đạt 3NF, nhưng chiều ngược lại có ngoại lệ. Điều kiện của 3NF chấp nhận một phụ thuộc với vế trái **không** là siêu khóa nếu **thuộc tính vế phải là nguyên tố**; BCNF không chấp nhận ngoại lệ đó.

> Điều cần tránh: “thuộc tính nguyên tố” **không đồng nghĩa** “thuộc khóa chính”. Một bảng có thể có vài khóa ứng viên; việc chọn một khóa làm PRIMARY KEY không làm các khóa ứng viên khác biến mất.

## 2. Ví dụ nghiệp vụ: học viên, môn học và người hướng dẫn

Trong một chương trình đào tạo **ở một học kỳ cố định**, hệ thống ghi nhận học viên được một người hướng dẫn phụ trách môn học:

| student_id | course_id | mentor_id |
| --- | --- | --- |
| S01 | C10 | M01 |
| S02 | C10 | M01 |
| S03 | C10 | M02 |
| S01 | C20 | M03 |

**Grain**: một lượt ghép **học viên – môn học – người hướng dẫn** ở học kỳ đang xét. Để xác định khóa và dạng chuẩn, nghiệp vụ xác nhận:

1. Mỗi học viên chỉ được chọn **một người hướng dẫn cho một môn** trong học kỳ.
2. Mỗi người hướng dẫn chỉ phụ trách **một môn** trong học kỳ, nhưng có thể hướng dẫn nhiều học viên.
3. Một môn có thể có nhiều người hướng dẫn.
4. Một học viên có thể học nhiều môn.

Đặt ký hiệu **S = student_id**, **C = course_id**, **M = mentor_id**. Ta có:

~~~text
R(S, C, M)

F1: (S, C) -> M   -- học viên + môn xác định người hướng dẫn
F2: M      -> C   -- người hướng dẫn xác định môn phụ trách
~~~

Không được tự thêm **C → M**: một môn có thể có M01 và M02. Không có **S → C** hay **S → M** vì một học viên có thể học nhiều môn với nhiều người hướng dẫn.

### 2.1. Tìm tất cả khóa ứng viên bằng bao đóng

**Bao đóng X⁺** là tập thuộc tính suy ra được từ X bằng các phụ thuộc hàm. X là **siêu khóa** nếu X⁺ chứa tất cả thuộc tính của R. Trong ví dụ:

| X | Diễn giải tính bao đóng | X⁺ | Siêu khóa? |
| --- | --- | --- | --- |
| **S** | Không có phụ thuộc nào dùng S một mình làm vế trái | {S} | Không |
| **C** | Không có phụ thuộc nào dùng C một mình làm vế trái | {C} | Không |
| **M** | Từ M → C, thêm C | {M, C} | Không, thiếu S |
| **(S, C)** | Từ SC → M, thêm M | {S, C, M} | Có |
| **(S, M)** | Từ M → C, thêm C | {S, M, C} | Có |
| **(C, M)** | Từ M → C chỉ có lại C | {C, M} | Không, thiếu S |

**S phải có trong mọi khóa ứng viên**, bởi S không xuất hiện ở vế phải phụ thuộc nào nên không thể suy ra S từ C hay M. Ghép S với C hoặc M đều đủ xác định toàn bộ hàng. Cả hai cặp đều tối thiểu vì từng thuộc tính đơn lẻ không đủ.

Vậy **toàn bộ khóa ứng viên** là:

~~~text
K1 = (S, C)
K2 = (S, M)
~~~

Các thuộc tính nguyên tố:

~~~text
S: nguyên tố vì thuộc K1 và K2
C: nguyên tố vì thuộc K1
M: nguyên tố vì thuộc K2
~~~

**Tất cả thuộc tính của R đều là nguyên tố**. Kết quả này có ý nghĩa quyết định khi xét 3NF. Nếu hệ thống chọn **(S, M)** làm khóa chính, C **vẫn** là thuộc tính nguyên tố vì thuộc khóa ứng viên **(S, C)**.

### 2.2. Kiểm tra từng phụ thuộc theo 3NF

Với **SC → M**, SC là khóa ứng viên nên thỏa điều kiện 3NF.

Với **M → C**:

- Đây là phụ thuộc **không tầm thường**, vì C không nằm trong M.
- M **không** là siêu khóa: **M⁺ = {M, C}**, thiếu S.
- C **là thuộc tính nguyên tố**, vì nằm trong khóa ứng viên SC.

Do vế phải nguyên tố, **M → C được phép ở 3NF**. Những phụ thuộc không tầm thường suy ra từ F1 và F2 cũng thỏa điều kiện 3NF; quan hệ **R đạt 3NF** theo tập quy tắc đã cho.

### 2.3. Kiểm tra cùng phụ thuộc theo BCNF

BCNF chỉ chấp nhận vế trái là siêu khóa:

| Phụ thuộc | Vế trái là siêu khóa? | 3NF | BCNF |
| --- | --- | --- | --- |
| **SC → M** | Có, SC là khóa ứng viên | Đạt | Đạt |
| **M → C** | **Không**, M⁺ thiếu S | **Đạt**, vì C nguyên tố | **Vi phạm** |

**Kết luận cho ví dụ:** R đạt **3NF nhưng không đạt BCNF**. Chỉ một phụ thuộc không tầm thường có vế trái không là siêu khóa cũng đủ làm quan hệ không đạt BCNF.

~~~mermaid
flowchart TD
    START["Phụ thuộc hàm X → A không tầm thường"]
    SUPER{"X là siêu khóa?"}
    PRIME{"A thuộc ít nhất một khóa ứng viên?"}
    BOTH["Thỏa cả 3NF và BCNF"]
    ONLY["Thỏa 3NF; vi phạm BCNF"]
    NONE["Vi phạm cả 3NF và BCNF"]
    START --> SUPER
    SUPER -->|"Có"| BOTH
    SUPER -->|"Không"| PRIME
    PRIME -->|"Có"| ONLY
    PRIME -->|"Không"| NONE
~~~

Sơ đồ trên áp dụng **cho từng phụ thuộc**; dạng chuẩn của toàn quan hệ được xác định sau khi kiểm tra **mọi phụ thuộc không tầm thường**. Một phụ thuộc đúng điều kiện không chứng minh toàn quan hệ đạt dạng chuẩn.

## 3. Vì sao nhiều khóa ứng viên làm người học dễ kết luận sai?

### 3.1. Chọn PRIMARY KEY không thay đổi phụ thuộc hàm

Giả sử một bảng được khai báo:

~~~sql
CREATE TABLE registrations_flat (
    student_id VARCHAR(10) NOT NULL,
    course_id  VARCHAR(10) NOT NULL,
    mentor_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (student_id, mentor_id),
    UNIQUE (student_id, course_id)
);
~~~

**PRIMARY KEY (student_id, mentor_id)** và **UNIQUE (student_id, course_id)** cùng các cột **NOT NULL** bảo vệ tính duy nhất của hai cặp, nhưng không làm mất quy tắc **M → C**. Đồng thời, hai ràng buộc riêng ấy **chưa thực thi được** M → C: cùng M vẫn có thể xuất hiện với C khác ở hai học viên khác nhau.

Ví dụ nếu bảng ban đầu có **(S01, C10, M01)**, lệnh sau có thể được chấp nhận bởi những ràng buộc đã khai báo:

~~~sql
-- Vi phạm quy tắc nghiệp vụ M -> C, nhưng không vi phạm
-- PRIMARY KEY (student_id, mentor_id) hoặc UNIQUE (student_id, course_id).
INSERT INTO registrations_flat (student_id, course_id, mentor_id)
VALUES ('S02', 'C20', 'M01');
~~~

Muốn bảo vệ M → C cần đặt quy tắc này vào cấu trúc có thể ràng buộc hoặc bổ sung kiểm soát ghi phù hợp. **Khóa chính là một lựa chọn khóa để định danh hàng; BCNF được xét theo tất cả phụ thuộc hàm có hiệu lực, không theo duy nhất khóa chính.**

### 3.2. Thêm ID thay thế không tự giải quyết vấn đề

Nếu bảng dùng **registration_id** làm khóa chính, nhưng vẫn bảo vệ **UNIQUE(S, C)** và **UNIQUE(S, M)** và giữ quy tắc **M → C**, thì M vẫn không xác định duy nhất toàn bộ hàng. Phụ thuộc M → C vẫn vi phạm BCNF.

Còn một hệ quả quan trọng: khi thêm một ID thay thế duy nhất, ba thuộc tính S, C, M có thể đều trở thành **không nguyên tố** vì chỉ còn các khóa ứng viên được khai báo lại theo ràng buộc và quy tắc nghiệp vụ; phải tìm **lại toàn bộ khóa ứng viên thực sự** của quan hệ mở rộng để kết luận 3NF. Không thể tự động chuyển kết quả 3NF của R(S,C,M) sang một quan hệ R(registration_id,S,C,M) mà không đánh giá lại.

Với các ràng buộc vẫn giữ **(S, C)** và **(S, M)** làm khóa ứng viên, C và M vẫn nguyên tố; nếu bỏ những quy tắc duy nhất nghiệp vụ và chỉ giữ ID, đó là **một mô hình và tập ràng buộc khác**, có thể gây bất thường lớn hơn.

## 4. Đối chiếu bằng các quan hệ trừu tượng có nhiều khóa ứng viên

Ví dụ nghiệp vụ giúp hiểu ý nghĩa; ví dụ đại số giúp kiểm chứng kết luận không dựa vào tên cột. Ta xét ba trường hợp trên các quan hệ chỉ có thuộc tính A, B, C.

### 4.1. Trường hợp A: đạt 3NF, không đạt BCNF

~~~text
R(A, B, C)
F = { AB -> C, C -> B }
~~~

Tính bao đóng:

~~~text
A+  = {A}
B+  = {B}
C+  = {C, B}
AB+ = {A, B, C}
AC+ = {A, C, B}
~~~

**AB** và **AC** là khóa ứng viên; mọi thuộc tính đều nguyên tố. Phụ thuộc **C → B** có vế trái **C không là siêu khóa**, nhưng B nguyên tố do thuộc AB. Vì vậy:

**3NF: đạt. BCNF: không đạt.**

Đây là cùng một cấu trúc phụ thuộc với ví dụ học viên nếu đặt **A = S, B = C, C = M**. Giá trị của ví dụ là có thể giải bằng bao đóng, không cần giả định “cột này quan trọng hơn cột kia”.

### 4.2. Trường hợp B: nhiều khóa ứng viên nhưng vẫn đạt BCNF

~~~text
R(A, B, C)
F = { A -> B, A -> C, BC -> A }
~~~

**A⁺ = {A, B, C}** và **(BC)⁺ = {B, C, A}**, nên các khóa ứng viên là **A** và **BC**. Không có thuộc tính B hay C đơn lẻ nào xác định cả quan hệ. Với các phụ thuộc đã cho:

- **A → B**: A là khóa ứng viên, hợp lệ ở BCNF.
- **A → C**: A là khóa ứng viên, hợp lệ ở BCNF.
- **BC → A**: BC là khóa ứng viên, hợp lệ ở BCNF.

Các phụ thuộc không tầm thường suy ra từ tập F này cũng có vế trái là siêu khóa. Vì vậy:

**3NF: đạt. BCNF: đạt.**

Ví dụ này bác bỏ nhận định **“cứ có nhiều khóa ứng viên thì sẽ vi phạm BCNF”**. Vấn đề là **có hay không một yếu tố xác định không phải siêu khóa**, chứ không phải số lượng khóa.

### 4.3. Trường hợp C: chưa đạt 3NF nên cũng chưa đạt BCNF

~~~text
R(A, B, C)
F = { A -> B, B -> C }
~~~

Theo F, **A** là khóa ứng viên duy nhất; B và C không nguyên tố. Với **B → C**, B không là siêu khóa và C không nguyên tố:

**3NF: không đạt. BCNF: không đạt.**

Đây là kiểu phụ thuộc bắc cầu quen thuộc. Không cần đợi đến BCNF mới phát hiện vấn đề.

| Trường hợp | Khóa ứng viên | Phụ thuộc quyết định | 3NF | BCNF |
| --- | --- | --- | --- | --- |
| A: **AB → C; C → B** | AB, AC | C → B; C không siêu khóa, B nguyên tố | Đạt | Không đạt |
| B: **A → BC; BC → A** | A, BC | Mọi yếu tố xác định có ý nghĩa đều là siêu khóa | Đạt | Đạt |
| C: **A → B; B → C** | A | B → C; B không siêu khóa, C không nguyên tố | Không đạt | Không đạt |

## 5. Phân rã ví dụ học viên để đạt BCNF

Quay lại **R(S, C, M)**, phụ thuộc **M → C** vi phạm BCNF. Ta phân rã:

~~~text
R1(M, C)  -- mỗi người hướng dẫn phụ trách một môn
R2(S, M)  -- một học viên được hướng dẫn bởi người nào
~~~

Đối chiếu:

| Bảng con | Phụ thuộc hàm chính được chiếu xuống | Khóa ứng viên | BCNF? |
| --- | --- | --- | --- |
| **mentor_courses(M, C)** | M → C | M | Đạt: M là siêu khóa |
| **student_mentors(S, M)** | Không có phụ thuộc không tầm thường từ F gốc trong bảng hai cột này | (S, M) | Đạt |

### 5.1. Kiểm tra phép nối không mất thông tin

Giao của hai tập thuộc tính là **{M}**. Do **M → C**, M xác định **toàn bộ R1(M, C)**. Theo điều kiện phân rã nhị phân, phép phân rã là **lossless join** đối với dữ liệu gốc thỏa F:

~~~text
R(S, C, M)
   -> R1(M, C)
      R2(S, M)

R1 ∩ R2 = {M}
M -> C
=> Nối tự nhiên R1 và R2 khôi phục đúng R gốc hợp lệ.
~~~

Hệ quả thực tế: một người hướng dẫn chỉ có một môn ở **mentor_courses**, nên khi nối bảng đăng ký theo M sẽ không tạo nhiều bản sao với các môn khác nhau.

### 5.2. Lược đồ PostgreSQL có thể thực hành

~~~sql
CREATE TABLE students (
    student_id VARCHAR(10) PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE courses (
    course_id VARCHAR(10) PRIMARY KEY,
    course_title VARCHAR(100) NOT NULL
);

CREATE TABLE mentor_courses (
    mentor_id VARCHAR(10) PRIMARY KEY,
    course_id VARCHAR(10) NOT NULL
        REFERENCES courses(course_id)
);

CREATE TABLE student_mentors (
    student_id VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    mentor_id VARCHAR(10) NOT NULL
        REFERENCES mentor_courses(mentor_id),
    PRIMARY KEY (student_id, mentor_id)
);

INSERT INTO students (student_id, student_name) VALUES
    ('S01', 'An'), ('S02', 'Bình'), ('S03', 'Chi');

INSERT INTO courses (course_id, course_title) VALUES
    ('C10', 'Cơ sở dữ liệu'), ('C20', 'Java');

INSERT INTO mentor_courses (mentor_id, course_id) VALUES
    ('M01', 'C10'), ('M02', 'C10'), ('M03', 'C20');

INSERT INTO student_mentors (student_id, mentor_id) VALUES
    ('S01', 'M01'), ('S02', 'M01'), ('S03', 'M02'), ('S01', 'M03');

-- Tái tạo các bộ (S, C, M).
SELECT sm.student_id, mc.course_id, sm.mentor_id
FROM student_mentors AS sm
JOIN mentor_courses AS mc
  ON mc.mentor_id = sm.mentor_id
ORDER BY sm.student_id, mc.course_id;
~~~

Các bảng **students** và **courses** quản lý thông tin danh mục độc lập. Phép phân rã BCNF cốt lõi ở đây là hai quan hệ **mentor_courses(M,C)** và **student_mentors(S,M)**.

### 5.3. Nối không mất thông tin vẫn có thể không bảo toàn phụ thuộc

Phân rã giữ được **M → C** trong bảng **mentor_courses**, nhưng **(S, C) → M** không thể được kiểm tra từ một bảng thành phần riêng lẻ:

- **student_mentors** chỉ biết S và M.
- **mentor_courses** chỉ biết M và C.
- Muốn biết một học viên có hai người hướng dẫn trong cùng môn hay không, phải kết hợp thông tin cả hai bảng.

Đây là sự khác biệt giữa:

**Lossless join:** ghép các hình chiếu của một quan hệ gốc hợp lệ sẽ khôi phục được quan hệ gốc.

**Dependency preservation:** các phụ thuộc gốc có thể được suy ra từ tập phụ thuộc trên các quan hệ con, không cần kiểm tra qua phép nối.

Phân rã này **lossless nhưng không bảo toàn phụ thuộc SC → M**.

### 5.4. Phản ví dụ cụ thể cho việc mất ràng buộc

Trong mẫu dữ liệu, M01 và M02 đều dạy C10, còn S01 đang học C10 với M01. Khóa chính của **student_mentors** vẫn cho phép thêm:

~~~sql
INSERT INTO student_mentors (student_id, mentor_id)
VALUES ('S01', 'M02');
~~~

Kết quả nối lúc này chứa hai hàng:

~~~text
student_id | course_id | mentor_id
-----------+-----------+----------
S01        | C10       | M01
S01        | C10       | M02
~~~

Điều này **vi phạm SC → M** trong quan hệ gốc, mặc dù khóa chính và khóa ngoại của hai bảng con đều được thỏa mãn. Phép nối không trở thành “lossy”; vấn đề là **lược đồ sau phân rã cho phép một trạng thái dữ liệu không thỏa quy tắc nghiệp vụ cũ**.

Truy vấn phát hiện:

~~~sql
SELECT
    sm.student_id,
    mc.course_id,
    COUNT(DISTINCT sm.mentor_id) AS mentor_count
FROM student_mentors AS sm
JOIN mentor_courses AS mc
  ON mc.mentor_id = sm.mentor_id
GROUP BY sm.student_id, mc.course_id
HAVING COUNT(DISTINCT sm.mentor_id) > 1;
~~~

Truy vấn trên chỉ **phát hiện** vi phạm, không tự chặn ghi. Nếu muốn giữ lược đồ BCNF, có thể cần cơ chế ràng buộc ở mức nghiệp vụ, trigger hoặc giao dịch được thiết kế để xử lý cả cạnh tranh ghi; không nên dựa chỉ vào thao tác “kiểm tra trước rồi INSERT” thiếu bảo vệ đồng thời.

## 6. Giữ 3NF để bảo toàn các quy tắc dễ hơn khi nào?

Một lựa chọn là giữ quan hệ đăng ký có đủ **S, C, M**, khai báo các khóa ứng viên và xây dựng cơ chế thực thi phụ thuộc **M → C**. Quan hệ đăng ký vẫn **3NF** theo các phụ thuộc nghiệp vụ đã cho, vì tất cả thuộc tính đều nguyên tố; nó **chưa đạt BCNF** do M không là siêu khóa.

Ví dụ thực thi trong PostgreSQL với một bảng danh mục phân công người hướng dẫn:

~~~sql
CREATE TABLE mentor_course_catalog (
    mentor_id VARCHAR(10) PRIMARY KEY,
    course_id VARCHAR(10) NOT NULL,
    UNIQUE (mentor_id, course_id)
);

CREATE TABLE student_course_mentor_3nf (
    student_id VARCHAR(10) NOT NULL,
    course_id  VARCHAR(10) NOT NULL,
    mentor_id  VARCHAR(10) NOT NULL,
    PRIMARY KEY (student_id, course_id),
    UNIQUE (student_id, mentor_id),
    FOREIGN KEY (mentor_id, course_id)
        REFERENCES mentor_course_catalog(mentor_id, course_id)
);
~~~

Giải thích các bất biến được bảo vệ:

- **PRIMARY KEY (student_id, course_id)**: bảo vệ **SC → M**, tức mỗi học viên–môn chỉ có một người hướng dẫn.
- **UNIQUE (student_id, mentor_id)**: thể hiện khóa ứng viên **SM** trong mô hình, với các thuộc tính không NULL.
- **PRIMARY KEY (mentor_id)** trong danh mục cùng **FOREIGN KEY (mentor_id, course_id)** ở bảng đăng ký: giữ mọi hàng có cùng mentor_id dùng đúng course_id theo danh mục; tức bảo vệ **M → C** xuyên hai bảng.
- **UNIQUE (mentor_id, course_id)** trong danh mục: hỗ trợ khóa được tham chiếu bởi khóa ngoại ghép trong PostgreSQL; không có nghĩa một mentor có nhiều môn, vì **mentor_id** đã là khóa chính.

Lựa chọn này có thêm **course_id** trong bảng đăng ký bên cạnh thông tin phân công, nên phải quản lý đồng bộ khi thay đổi môn của người hướng dẫn. Bù lại, các ràng buộc độc lập dễ biểu diễn bằng khóa chính, khóa duy nhất và khóa ngoại. Đây là một **thiết kế lưu trữ cụ thể**, không nên nhầm với kết luận lý thuyết “3NF tự thực thi mọi phụ thuộc”.

Điểm đánh đổi:

| Tiêu chí | Giữ quan hệ đăng ký 3NF có S,C,M | Phân rã lõi BCNF thành (M,C) và (S,M) |
| --- | --- | --- |
| Phụ thuộc **SC → M** | Đặt được trực tiếp bằng khóa trên S,C | Cần kiểm soát qua hai bảng |
| Phụ thuộc **M → C** | Cần cơ chế bảo vệ bổ sung, chẳng hạn danh mục + FK ghép | Bảo vệ trực tiếp bằng khóa M của bảng M,C |
| Dư thừa **course_id** theo mentor | Có thể lặp ở bảng đăng ký | Không lặp trong bảng S,M |
| Phép nối khi truy vấn môn của học viên | Có S,C,M sẵn trong bản ghi đăng ký | Phải nối bảng S,M với M,C |
| Khả năng diễn đạt toàn bộ quy tắc trong một ràng buộc SQL đơn giản | Thuận hơn cho SC → M, nhưng M → C vẫn cần xử lý | Thuận hơn cho M → C, nhưng SC → M cần xử lý |

Trong lý thuyết chuẩn hóa, thuật toán **tổng hợp 3NF** có thể cho phân rã vừa **nối không mất thông tin** vừa **bảo toàn các phụ thuộc hàm**. Ngược lại, **không phải mọi tập phụ thuộc** có phân rã đạt BCNF đồng thời giữ được cả hai tính chất đó. Vì vậy, chọn BCNF hay một giải pháp 3NF có kiểm soát phải dựa vào yêu cầu thực thi ràng buộc, không chỉ vào tên dạng chuẩn.

## 7. Quy trình phân biệt 3NF và BCNF trong một bài toán mới

1. **Chốt grain và thời gian hiệu lực.** Một hàng biểu diễn đăng ký học trong kỳ, đăng ký một buổi, hay toàn bộ lịch sử? Phụ thuộc hàm thay đổi nếu bối cảnh thay đổi.
2. **Thu thập phụ thuộc hàm đúng nghiệp vụ.** Hỏi mỗi vế trái có thể dẫn đến nhiều giá trị vế phải hay không; tránh suy từ vài hàng mẫu.
3. **Tính bao đóng để tìm mọi khóa ứng viên.** Bắt đầu từ những thuộc tính không xuất hiện ở vế phải của bất kỳ phụ thuộc nào, rồi thử bổ sung thành phần cần thiết và loại thành phần dư.
4. **Đánh dấu thuộc tính nguyên tố.** Thuộc tính nằm trong **bất kỳ** khóa ứng viên nào đều là nguyên tố, dù không thuộc khóa chính đã chọn.
5. **Kiểm tra 3NF.** Với mỗi phụ thuộc không tầm thường X → A, nếu X không là siêu khóa thì A có phải nguyên tố không?
6. **Kiểm tra BCNF.** Với chính phụ thuộc đó, X phải là siêu khóa; không có ngoại lệ cho A nguyên tố.
7. **Nếu phân rã, kiểm tra lossless join.** Với hai quan hệ con, phần thuộc tính giao phải xác định toàn bộ ít nhất một bên; không tách bảng chỉ vì tên cột giống nhau.
8. **Kiểm tra bảo toàn phụ thuộc và cách thực thi.** Thử thêm các hàng hợp lệ về khóa chính/khóa ngoại nhưng vi phạm quy tắc nghiệp vụ cũ; xem cần ràng buộc, giao dịch hay thay đổi mô hình.
9. **Đánh giá vật lý sau cùng.** Xác định chỉ mục, phép nối, khối lượng đọc/ghi và các bản sao dữ liệu dành cho báo cáo hoặc document. Nếu phi chuẩn hóa có chủ đích, ghi rõ nguồn dữ liệu chuẩn và quy tắc đồng bộ.

### Không được bỏ qua yếu tố thời gian

Phụ thuộc **mentor_id → course_id** chỉ đúng theo ví dụ **một học kỳ cố định**. Nếu hệ thống lưu nhiều học kỳ, một người có thể dạy C10 ở kỳ trước và C20 ở kỳ sau. Khi đó quy tắc có thể trở thành:

~~~text
(mentor_id, term_id) -> course_id
~~~

Nếu một người dạy nhiều môn trong một kỳ, phụ thuộc mới cũng chưa đủ; phải mô hình hóa **lớp học phần**, **phân công**, hoặc **lần đăng ký** theo đúng nghiệp vụ. Không thể kết luận một bảng vi phạm BCNF từ một phụ thuộc hàm **không còn đúng**.

Tương tự, trong mô hình quan hệ, document, đồ thị hay phân tích, các giá trị lặp có thể là dữ liệu lịch sử tại các thời điểm khác nhau hoặc bản sao dành cho truy vấn. Muốn đánh giá đúng cần phân biệt **bản sao của cùng sự thật hiện hành** với **những sự thật khác nhau theo thời gian**.

## 8. Bài tập kiểm chứng

### Bài 1. Tính khóa và dạng chuẩn

Cho **R(A, B, C, D)** cùng các phụ thuộc hàm:

~~~text
AB -> C
C  -> B
AB -> D
~~~

Giả định không có phụ thuộc nghiệp vụ bổ sung ngoài các hệ quả suy ra từ tập trên.

**Yêu cầu:**

1. Tìm mọi khóa ứng viên và xác định các thuộc tính nguyên tố.
2. R có đạt 3NF không? R có đạt BCNF không?
3. Thuộc tính D có ảnh hưởng đến kết luận “C → B được phép trong 3NF” không?
4. Nếu phân rã theo C → B, hãy đề xuất R1 và R2 và kiểm tra điều kiện lossless.

<details>
<summary>Gợi ý lời giải bài 1</summary>

Vì **A** không xuất hiện ở vế phải nào, mọi khóa phải chứa A. Ta có:

~~~text
AB+ = {A, B, C, D}
AC+ = {A, C, B, D}
C+  = {C, B}
~~~

Khóa ứng viên là **AB** và **AC**. Các thuộc tính **A, B, C** là nguyên tố; **D** không nguyên tố.

**AB → C** và **AB → D** có vế trái là khóa. **C → B** có C không là siêu khóa, nhưng B là nguyên tố, nên **R đạt 3NF**, trong khi **R không đạt BCNF**. Thêm D không làm mất tính nguyên tố của B; D được xác định bởi khóa AB, không tạo vi phạm 3NF mới.

Phân rã theo **C → B** thành **R1(C, B)** và **R2(A, C, D)**. Giao là {C}, và **C → B** nên phân rã lossless. Phải kiểm tra tiếp các phụ thuộc chiếu xuống từng bảng và xem **AB → D** có còn được bảo toàn hay không.

</details>

### Bài 2. So sánh hai thiết kế có cùng ba cột

Cho hai bảng cùng tập thuộc tính **R(P, Q, R)**:

~~~text
Thiết kế X: { PQ -> R, R -> Q }
Thiết kế Y: { P -> Q, P -> R, QR -> P }
~~~

Với mỗi thiết kế, hãy tính khóa ứng viên, kiểm tra 3NF và BCNF. Giải thích vì sao câu “nhiều khóa ứng viên là nguyên nhân vi phạm BCNF” là không chính xác.

<details>
<summary>Gợi ý lời giải bài 2</summary>

- **Thiết kế X:** các khóa ứng viên là **PQ** và **PR**. Phụ thuộc **R → Q** có R không là siêu khóa nhưng Q nguyên tố. Bảng đạt **3NF**, chưa đạt **BCNF**.
- **Thiết kế Y:** các khóa ứng viên là **P** và **QR**. Mọi phụ thuộc không tầm thường có ý nghĩa đều có vế trái là siêu khóa. Bảng đạt **BCNF**, và do đó đạt **3NF**.

Cả hai có nhiều khóa ứng viên; chỉ X có phụ thuộc vi phạm BCNF.

</details>

### Bài 3. Phản ví dụ sau phân rã

Với hai bảng **mentor_courses(M,C)** và **student_mentors(S,M)**:

- Viết hai hàng **student_mentors** và các hàng **mentor_courses** làm cho phép nối vi phạm **SC → M** nhưng vẫn thỏa các khóa của hai bảng.
- Giải thích vì sao truy vấn **COUNT(DISTINCT mentor_id) > 1** theo cặp **(student_id, course_id)** phát hiện lỗi nhưng chưa phải ràng buộc ngăn lỗi.
- Đề xuất cách xử lý nếu yêu cầu “một học viên chỉ chọn một người hướng dẫn cho mỗi môn” là bất biến quan trọng không được vi phạm, kể cả khi có hai luồng ghi đồng thời.

**Hướng giải:** dùng cùng S với hai M khác nhau, cả hai M ánh xạ cùng C. Muốn ngăn lỗi, cần mô hình giữ khóa duy nhất theo S,C, hoặc một cơ chế ghi/ràng buộc có khả năng khóa đúng phạm vi cạnh tranh; chỉ kiểm tra trước bằng một câu SELECT ở lớp ứng dụng không đủ bảo đảm khi ghi đồng thời.

## 9. Những nhầm lẫn thường gặp

| Nhận định sai | Điều cần kiểm tra |
| --- | --- |
| “3NF và BCNF đều chỉ yêu cầu mọi vế trái là khóa.” | 3NF có thêm trường hợp **vế phải là thuộc tính nguyên tố**. |
| “Thuộc tính không thuộc PRIMARY KEY thì không nguyên tố.” | Phải xét **tất cả khóa ứng viên**, kể cả khóa chưa được chọn làm PRIMARY KEY. |
| “Có hai khóa ứng viên thì chắc chắn không BCNF.” | Có nhiều khóa vẫn đạt BCNF nếu mọi yếu tố xác định không tầm thường đều là siêu khóa. |
| “Thêm ID làm PRIMARY KEY sẽ loại bỏ vi phạm BCNF.” | ID không xóa những phụ thuộc hàm do nghiệp vụ quyết định. |
| “Tách theo một phụ thuộc vi phạm luôn giải quyết mọi ràng buộc.” | Cần kiểm tra **lossless**, dạng chuẩn của bảng con và **dependency preservation**. |
| “Lossless nghĩa là sau phân rã không thể chèn dữ liệu sai.” | Lossless xét khôi phục quan hệ gốc hợp lệ; còn quy tắc ghi có thể không được bảo toàn. |
| “Ràng buộc UNIQUE(M) trong bảng đăng ký giải quyết M → C.” | Nó còn cấm nhiều học viên cùng người hướng dẫn, trái nghiệp vụ; phải chọn cấu trúc đúng. |
| “Một ví dụ có 4 hàng đủ để xác nhận phụ thuộc hàm.” | Phải lấy quy tắc từ nghiệp vụ và xét mọi trạng thái hợp lệ. |

## 10. Ghi nhớ

Để phân biệt 3NF với BCNF, đừng bắt đầu từ khóa chính; hãy **tìm toàn bộ khóa ứng viên**, xác định **thuộc tính nguyên tố**, rồi xét **từng phụ thuộc hàm không tầm thường X → A**. Nếu X là siêu khóa, phụ thuộc đạt cả 3NF lẫn BCNF. Nếu X không là siêu khóa nhưng A nguyên tố, phụ thuộc **được phép ở 3NF nhưng vi phạm BCNF**. Nếu cả hai điều kiện đều sai, phụ thuộc vi phạm cả hai dạng chuẩn.

Ví dụ **SC → M** và **M → C** cho hai khóa ứng viên **SC**, **SM**; tất cả thuộc tính đều nguyên tố nên quan hệ đạt **3NF**, nhưng **M → C** vi phạm **BCNF**. Phân rã có thể loại bỏ sự lặp lại về người hướng dẫn–môn học, đồng thời làm khó việc bảo vệ **SC → M**. Vì vậy, quyết định mô hình cuối cùng phải kiểm chứng **phụ thuộc hàm, tính nối không mất thông tin, khả năng bảo toàn ràng buộc và cách ghi dữ liệu thực tế**.
