# Dạng chuẩn thứ tư và loại bỏ phụ thuộc đa trị không phù hợp

**Dạng chuẩn thứ tư (Fourth Normal Form, 4NF)** xử lý một kiểu dư thừa mà ngay cả **BCNF** cũng có thể bỏ sót: nhiều tập giá trị **độc lập với nhau** bị ghép chung trong một quan hệ. Khi một thực thể có nhiều ngôn ngữ và nhiều sở thích, lưu mọi cặp ngôn ngữ–sở thích trong cùng một bảng làm số hàng tăng theo tích số phần tử, dù giữa hai tập không có liên hệ nghiệp vụ.

Để nhận diện đúng tình huống này, ta dùng **phụ thuộc đa trị (multivalued dependency, MVD)**, ký hiệu **X ↠ Y** hoặc **X ->> Y**. 4NF yêu cầu: **với mọi phụ thuộc đa trị không tầm thường X ↠ Y, X phải là siêu khóa**. Bài học thuộc chương **Chuẩn hóa** của mô-đun **DATABASE_DATA_MODELING**, giúp chuyển yêu cầu nghiệp vụ thành các quan hệ có khóa và ràng buộc rõ ràng, kiểm chứng phép phân rã và phân biệt tập giá trị độc lập với dữ liệu có quan hệ kết hợp thực sự.

## 1. Tình huống: một học viên có nhiều ngôn ngữ và sở thích

Giả sử ứng dụng hồ sơ học viên quản lý:

- Mỗi học viên được nhận diện bằng **student_id**.
- Mỗi học viên có thể sử dụng **nhiều ngôn ngữ**.
- Mỗi học viên có thể có **nhiều sở thích**.
- Danh sách ngôn ngữ và danh sách sở thích **độc lập**: một ngôn ngữ không gắn với một sở thích cụ thể.
- Học viên có thể chưa khai báo ngôn ngữ, sở thích, hoặc cả hai.

Một bảng ban đầu có ba thuộc tính:

| student_id | language_code | hobby_code |
| --- | --- | --- |
| S01 | EN | CHESS |
| S01 | EN | CYCLING |
| S01 | JA | CHESS |
| S01 | JA | CYCLING |

Với S01, hệ thống chỉ cần biểu diễn **hai sự thật ngôn ngữ** (EN, JA) và **hai sự thật sở thích** (CHESS, CYCLING). Nhưng bảng đang chứa **bốn cặp**:

~~~text
Ngôn ngữ: {EN, JA}       Sở thích: {CHESS, CYCLING}

EN  × CHESS
EN  × CYCLING
JA  × CHESS
JA  × CYCLING
~~~

Khi số phần tử tăng, mức lặp tăng theo tích:

| Số ngôn ngữ (m) | Số sở thích (n) | Bảng ghép: m × n hàng | Hai bảng độc lập: m + n hàng |
| ---: | ---: | ---: | ---: |
| 2 | 2 | 4 | 4 |
| 3 | 4 | 12 | 7 |
| 5 | 8 | 40 | 13 |
| 10 | 10 | 100 | 20 |

Đây là so sánh số **hàng liên kết** cho một học viên có cả hai tập, chưa tính hàng định danh học viên. Chi phí lưu trữ còn tùy kích thước hàng và chỉ mục; điều quan trọng là **tích m × n** so với **tổng m + n**.

### 1.1. Bảng gộp có thể đã ở BCNF

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE student_interests_flat (
    student_id     VARCHAR(10) NOT NULL,
    language_code  VARCHAR(10) NOT NULL,
    hobby_code     VARCHAR(20) NOT NULL,
    PRIMARY KEY (student_id, language_code, hobby_code)
);

INSERT INTO student_interests_flat
    (student_id, language_code, hobby_code)
VALUES
    ('S01', 'EN', 'CHESS'),
    ('S01', 'EN', 'CYCLING'),
    ('S01', 'JA', 'CHESS'),
    ('S01', 'JA', 'CYCLING');
~~~

Trong phạm vi các quy tắc trên, **không có phụ thuộc hàm không tầm thường** như **student_id → language_code**, **student_id → hobby_code**, hoặc **language_code → hobby_code**. Một học viên có nhiều ngôn ngữ và nhiều sở thích.

Với giả định không có phụ thuộc hàm nghiệp vụ bổ sung, bộ ba **(student_id, language_code, hobby_code)** là khóa ứng viên. Vì không có phụ thuộc hàm không tầm thường có vế trái không là siêu khóa, bảng **đạt BCNF**, đồng thời đạt các dạng chuẩn thấp hơn. Tuy nhiên, nó vẫn dư thừa do các **tập giá trị độc lập**. Để đánh giá cần đến 4NF.

## 2. Phụ thuộc đa trị là gì?

### 2.1. Trực giác: một tập Y độc lập với phần còn lại Z

Cho quan hệ **R(X, Y, Z)**, trong đó X, Y, Z là các tập thuộc tính không giao nhau và cùng tạo thành toàn bộ R. Phụ thuộc đa trị:

~~~text
X ->> Y
~~~

diễn tả rằng với một giá trị X cố định, **tập các giá trị Y có thể kết hợp độc lập với tập giá trị Z**. Nếu tồn tại hai bộ cùng X:

~~~text
(x, y1, z1)
(x, y2, z2)
~~~

thì quan hệ cũng phải chứa hai bộ hoán đổi:

~~~text
(x, y1, z2)
(x, y2, z1)
~~~

Với mỗi X, những bộ của quan hệ tạo **tích Descartes** giữa các giá trị Y và Z được ghi nhận cho X.

Với bảng học viên:

~~~text
X = student_id
Y = language_code
Z = hobby_code
~~~

Từ **(S01, EN, CHESS)** và **(S01, JA, CYCLING)**, tính độc lập yêu cầu cả **(S01, EN, CYCLING)** và **(S01, JA, CHESS)**. Bốn hàng mẫu thỏa điều kiện này.

**Lưu ý:** chỉ vì một học viên có “danh sách ngôn ngữ” không đủ để kết luận có MVD. MVD là quy tắc mạnh hơn về **khả năng kết hợp độc lập** giữa Y với các thuộc tính còn lại Z trong **mọi trạng thái hợp lệ**.

### 2.2. Hai phụ thuộc đa trị bổ sung nhau

Từ tính độc lập của ví dụ:

~~~text
student_id ->> language_code
student_id ->> hobby_code
~~~

Hai phụ thuộc liên hệ qua **quy tắc bổ sung (complementation)**: trong quan hệ R, nếu **X ↠ Y** thì có **X ↠ R − (X ∪ Y)**. Với ba cột S, L, H, **S ↠ L** kéo theo **S ↠ H**.

Ngược lại, **student_id → language_code** (phụ thuộc hàm) **không đúng** nếu một học viên có hai ngôn ngữ. MVD không nói X xác định **một** Y; nó nói về tính độc lập của **các giá trị Y** với phần còn lại.

### 2.3. So sánh phụ thuộc hàm và phụ thuộc đa trị

| Tiêu chí | Phụ thuộc hàm **X → Y** | Phụ thuộc đa trị **X ↠ Y** |
| --- | --- | --- |
| Ý nghĩa | Mỗi X có **tối đa một** Y | Các giá trị Y ứng với X kết hợp độc lập với phần còn lại |
| Ví dụ | **department_id → department_name** | **student_id ↠ language_code** trong ví dụ |
| Có thể có nhiều Y cho cùng X? | Không | Có |
| Rủi ro điển hình | Sao chép một giá trị của thực thể khác trên nhiều hàng | Nhân các tổ hợp giữa hai tập độc lập |
| Dạng chuẩn liên quan | 2NF, 3NF, BCNF | 4NF |

**Mọi phụ thuộc hàm X → Y cũng suy ra phụ thuộc đa trị X ↠ Y**, nhưng chiều ngược lại không đúng. Vì thế 4NF còn bao phủ những vấn đề BCNF phát hiện qua phụ thuộc hàm và chặt hơn BCNF.

## 3. Định nghĩa 4NF và điều kiện “không tầm thường”

Một quan hệ **R ở dạng chuẩn thứ tư (4NF)** nếu với **mọi MVD không tầm thường X ↠ Y** đúng trên R, **X là siêu khóa của R**.

Trong đó:

- **Siêu khóa:** tập thuộc tính xác định toàn bộ hàng theo các phụ thuộc hàm của quan hệ; không yêu cầu tối thiểu.
- **Khóa ứng viên:** siêu khóa tối thiểu.
- **MVD tầm thường** nếu **Y ⊆ X** hoặc **X ∪ Y = R** (R được hiểu là tập thuộc tính).
- **MVD không tầm thường** nếu **Y không là tập con của X** và **X ∪ Y chưa chứa hết các thuộc tính của R**.

Phân biệt trong R(S, L, H):

| Phụ thuộc đa trị | Tầm thường? | Giải thích |
| --- | --- | --- |
| **S ↠ S** | Có | Vế phải nằm trong vế trái |
| **S ↠ (L, H)** | Có | Hợp S, L, H là toàn bộ R |
| **S ↠ L** | **Không** | S và L chưa bao gồm H |
| **S ↠ H** | **Không** | S và H chưa bao gồm L |

Trong bảng **student_interests_flat**, **S không là siêu khóa** vì một học viên có nhiều hàng. **S ↠ L** và **S ↠ H** là MVD không tầm thường có vế trái không là siêu khóa. Vì vậy quan hệ **vi phạm 4NF**, dù **đạt BCNF** theo các phụ thuộc hàm đã giả định.

## 4. Bất thường khi ghép hai tập độc lập

### 4.1. Bất thường khi thêm

S01 vừa học thêm **FR**. Do học viên đang có hai sở thích, để dữ liệu vẫn biểu diễn đúng mọi tổ hợp, ứng dụng phải thêm **hai hàng**:

~~~sql
INSERT INTO student_interests_flat
    (student_id, language_code, hobby_code)
VALUES
    ('S01', 'FR', 'CHESS'),
    ('S01', 'FR', 'CYCLING');
~~~

Thêm chỉ một hàng làm bảng thiếu các tổ hợp độc lập theo nghiệp vụ. Nếu học viên **chưa có sở thích**, các cột **NOT NULL** ngăn lưu riêng một ngôn ngữ mà không tạo sở thích giả.

### 4.2. Bất thường khi sửa

Nếu mã sở thích **CYCLING** được chuẩn hóa thành **BIKING** đối với S01, ứng dụng phải sửa mọi hàng có CYCLING của học viên, bất kể ngôn ngữ. Bỏ sót một hàng khiến cùng một mối quan hệ học viên–sở thích được biểu diễn không nhất quán.

### 4.3. Bất thường khi xóa

Nếu S01 chỉ còn sở thích **CHESS** nhưng vẫn biết EN và JA, việc xóa tất cả hàng có **hobby_code = CHESS** sẽ làm mất luôn bằng chứng về hai ngôn ngữ, dù học viên chỉ muốn bỏ sở thích.

Vấn đề là vòng đời của liên kết **học viên–ngôn ngữ** bị buộc đi cùng liên kết **học viên–sở thích**.

## 5. Phân rã thành các quan hệ lưu những sự thật độc lập

Với R(S, L, H) và MVD vi phạm **S ↠ L**, sử dụng phép phân rã:

~~~text
R1 = S ∪ L = (S, L)
R2 = R − (L − S) = (S, H)
~~~

Hai quan hệ mới:

- **student_languages(student_id, language_code)**: mỗi hàng nói học viên sử dụng **một ngôn ngữ**.
- **student_hobbies(student_id, hobby_code)**: mỗi hàng nói học viên có **một sở thích**.

Thêm bảng **students** để lưu học viên độc lập, kể cả khi hai tập đều rỗng.

~~~mermaid
erDiagram
    STUDENTS ||--o{ STUDENT_LANGUAGES : "sử dụng"
    STUDENTS ||--o{ STUDENT_HOBBIES : "có sở thích"
    STUDENTS {
        varchar student_id PK
        varchar student_name
    }
    STUDENT_LANGUAGES {
        varchar student_id PK, FK
        varchar language_code PK
    }
    STUDENT_HOBBIES {
        varchar student_id PK, FK
        varchar hobby_code PK
    }
~~~

### 5.1. Lược đồ SQL

~~~sql
CREATE TABLE students (
    student_id VARCHAR(10) PRIMARY KEY,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE student_languages (
    student_id VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    language_code VARCHAR(10) NOT NULL,
    PRIMARY KEY (student_id, language_code)
);

CREATE TABLE student_hobbies (
    student_id VARCHAR(10) NOT NULL
        REFERENCES students(student_id),
    hobby_code VARCHAR(20) NOT NULL,
    PRIMARY KEY (student_id, hobby_code)
);

INSERT INTO students (student_id, student_name) VALUES
    ('S01', 'An'), ('S02', 'Bình'), ('S03', 'Chi');

INSERT INTO student_languages (student_id, language_code) VALUES
    ('S01', 'EN'), ('S01', 'JA'), ('S02', 'FR');

INSERT INTO student_hobbies (student_id, hobby_code) VALUES
    ('S01', 'CHESS'), ('S01', 'CYCLING'),
    ('S02', 'PIANO'), ('S03', 'DRAWING');
~~~

Mỗi bảng liên kết có **một loại quan hệ một-nhiều**. Khóa chính ghép chặn lặp cùng một phần tử của học viên, khóa ngoại chặn liên kết tới học viên không tồn tại. **S03 có sở thích nhưng chưa khai báo ngôn ngữ** vẫn được lưu hợp lệ.

### 5.2. Thao tác không phải nhân tổ hợp

**Thêm một ngôn ngữ:** chỉ thêm một hàng.

~~~sql
INSERT INTO student_languages (student_id, language_code)
VALUES ('S01', 'FR');
~~~

**Xóa một sở thích:** giữ nguyên danh sách ngôn ngữ.

~~~sql
DELETE FROM student_hobbies
WHERE student_id = 'S01'
  AND hobby_code = 'CYCLING';
~~~

**Đọc từng danh sách độc lập:**

~~~sql
SELECT language_code
FROM student_languages
WHERE student_id = 'S01'
ORDER BY language_code;

SELECT hobby_code
FROM student_hobbies
WHERE student_id = 'S01'
ORDER BY hobby_code;
~~~

Giao diện cần hai danh sách thì không cần nối hai bảng. Nếu thật sự cần mọi tổ hợp:

~~~sql
SELECT
    l.student_id,
    l.language_code,
    h.hobby_code
FROM student_languages AS l
JOIN student_hobbies AS h
    ON h.student_id = l.student_id
WHERE l.student_id = 'S01'
ORDER BY l.language_code, h.hobby_code;
~~~

Truy vấn tạo tổ hợp **khi đọc**, thay vì nhân bản mọi cặp ở nơi lưu trữ.

### 5.3. Đếm phần tử mà không đếm nhầm tổ hợp

~~~sql
SELECT
    s.student_id,
    (SELECT COUNT(*)
     FROM student_languages AS l
     WHERE l.student_id = s.student_id) AS language_count,
    (SELECT COUNT(*)
     FROM student_hobbies AS h
     WHERE h.student_id = s.student_id) AS hobby_count
FROM students AS s
ORDER BY s.student_id;
~~~

Truy vấn con trả về số ngôn ngữ và số sở thích riêng biệt, kể cả **0**. Khi nối đồng thời hai bảng con theo S, số hàng trung gian có thể thành **m × n**; **COUNT(*)** trên phép nối sẽ đếm tổ hợp. Có thể tổng hợp trước khi nối hoặc dùng **COUNT(DISTINCT ...)** nếu thích hợp.

## 6. Vì sao phân rã đúng là không mất thông tin?

**Phân rã nối không mất thông tin (lossless-join decomposition)** nghĩa là có thể khôi phục chính xác quan hệ gốc từ các hình chiếu, đối với mọi trạng thái gốc thỏa phụ thuộc đang xét.

Với R(S,L,H), nếu **S ↠ L** đúng thì:

~~~text
R = π(S,L)(R) ⋈ π(S,H)(R)
~~~

Phép nối theo S tái tạo mọi tổ hợp L–H. Nó **không tạo bộ giả** vì định nghĩa MVD đã yêu cầu **mọi tổ hợp** của từng S đều có trong R gốc; nó cũng không bỏ sót bộ gốc vì mỗi bộ đều đóng góp hai hình chiếu.

Ví dụ:

~~~text
π(S,L):                  π(S,H):
S01, EN                 S01, CHESS
S01, JA                 S01, CYCLING
~~~

Nối hai hình chiếu khôi phục đúng bốn hàng ban đầu.

**Giới hạn:** nếu một cặp L–H là một sự thật kết hợp riêng, không phải mọi tổ hợp đều hợp lệ, phép nối có thể tạo bộ giả. Khi đó MVD giả định **không đúng** và không được phân rã theo nó.

### 6.1. Hai bảng con đạt 4NF theo quy tắc nào?

Theo bài toán:

- **student_languages(S,L)** quản lý một cặp học viên–ngôn ngữ.
- **student_hobbies(S,H)** quản lý một cặp học viên–sở thích.
- Không có phụ thuộc hàm hoặc MVD không tầm thường bổ sung với vế trái không là siêu khóa được nghiệp vụ xác nhận trong từng bảng con.

Do đó, các quan hệ con **đạt 4NF theo các phụ thuộc đã giả định**. Không kết luận một bảng đạt 4NF chỉ vì nó có ít cột; phải xét phụ thuộc có hiệu lực trên chính quan hệ đó.

## 7. Phản ví dụ: nhiều giá trị nhưng không độc lập

Giả sử quản lý **sản phẩm–màu–kích cỡ**, trong đó một sản phẩm chỉ có những biến thể cụ thể:

| product_id | color | size |
| --- | --- | --- |
| P01 | Đỏ | S |
| P01 | Đỏ | M |
| P01 | Xanh | L |

Không có biến thể **(P01, Xanh, S)**, **(P01, Xanh, M)** hoặc **(P01, Đỏ, L)**.

Nếu tách thành hai tập:

~~~text
product_colors:
  (P01, Đỏ)
  (P01, Xanh)

product_sizes:
  (P01, S)
  (P01, M)
  (P01, L)
~~~

rồi nối theo product_id, ta tạo ra **2 × 3 = 6 tổ hợp**, gồm ba biến thể **không tồn tại**.

Nguyên nhân: **màu và kích cỡ không độc lập**, bởi từng cặp là một biến thể có ý nghĩa riêng. Phụ thuộc đa trị **product_id ↠ color không đúng** với quan hệ này: từ hàng **(P01, Đỏ, S)** và **(P01, Xanh, L)**, nếu MVD đúng, các hàng **(P01, Đỏ, L)** và **(P01, Xanh, S)** cũng phải tồn tại.

Thiết kế phù hợp hơn:

~~~text
products(product_id, ...)
product_variants(variant_id, product_id, color, size, ...)
~~~

Trong đó mỗi hàng **product_variants** là một biến thể bán được. Nếu nghiệp vụ bảo đảm mỗi cặp màu–kích cỡ chỉ có một biến thể trên sản phẩm, bổ sung **UNIQUE(product_id, color, size)**. Lược đồ thực tế còn có thể cần SKU, tồn kho và giá theo biến thể.

| Câu hỏi nghiệp vụ | Tập độc lập, có thể tách | Kết hợp có ý nghĩa, cần giữ |
| --- | --- | --- |
| Một ngôn ngữ có gắn với sở thích cụ thể của học viên không? | Không | — |
| Mọi màu đều có đủ mọi cỡ bán được không? | Chỉ nếu nghiệp vụ khẳng định | Nếu không, lưu từng biến thể hợp lệ |
| Học viên sử dụng kỹ năng nào **trong từng dự án**? | Không thể tách chỉ theo học viên nếu kỹ năng phụ thuộc dự án | Lưu **(student_id, project_id, skill_id)** theo từng kết hợp |
| Thêm Y mới có nghĩa nó kết hợp với mọi Z hiện có? | Có, theo ngữ nghĩa MVD | Không, phải chỉ rõ tổ hợp nào hợp lệ |

**Không được suy MVD từ vẻ ngoài của dữ liệu.** Hai cột cùng có nhiều giá trị không đủ để kết luận độc lập. Cần xác nhận quy tắc nghiệp vụ và kiểm tra phép nối có thể tạo kết quả không hợp lệ hay không.

## 8. Liên hệ với BCNF, khóa thay thế và mô hình document

### 8.1. Quan hệ giữa các dạng chuẩn

| Dạng chuẩn | Loại phụ thuộc nổi bật cần kiểm soát | Mức yêu cầu |
| --- | --- | --- |
| **1NF** | Giá trị theo miền dữ liệu, tránh giấu tập phần tử cần quản lý độc lập trong một ô | Nền tảng |
| **2NF** | Phụ thuộc hàm bộ phận của thuộc tính không nguyên tố vào khóa ứng viên | Chặt hơn 1NF |
| **3NF** | Phụ thuộc hàm X → A; cho phép trường hợp A nguyên tố | Chặt hơn 2NF |
| **BCNF** | Mọi phụ thuộc hàm không tầm thường có vế trái là siêu khóa | Chặt hơn 3NF |
| **4NF** | Mọi **phụ thuộc đa trị không tầm thường** có vế trái là siêu khóa | Chặt hơn BCNF |

Một FD cũng suy ra MVD, nên quan hệ đạt 4NF sẽ đạt BCNF. Bảng ở mục 1 là phản ví dụ cho chiều ngược lại: **đạt BCNF không bảo đảm đạt 4NF**.

### 8.2. Thêm ID không giải quyết MVD

Giả sử thêm **id** làm khóa chính vào **student_interests_flat**. Một học viên vẫn có nhiều phần tử trong mỗi tập và ứng dụng vẫn phải lưu mọi tổ hợp. Khóa thay thế chỉ định danh từng hàng; **nó không làm cho ngôn ngữ và sở thích có liên hệ nghiệp vụ**.

Đánh giá 4NF phải bắt đầu từ phụ thuộc hàm, MVD và **grain**. Đổi tên cột, bổ sung chỉ mục hoặc thay khóa chính không làm quy tắc kết hợp thay đổi.

### 8.3. Có phải mọi mảng JSON đều vi phạm 4NF?

**4NF là tiêu chí của mô hình quan hệ**, còn hệ quản trị document có thể biểu diễn hai tập độc lập trong hai mảng:

~~~json
{
  "studentId": "S01",
  "languages": ["EN", "JA"],
  "hobbies": ["CHESS", "CYCLING"]
}
~~~

Cách lưu này có thể phù hợp nếu ứng dụng thường đọc/cập nhật cả hồ sơ và có cơ chế kiểm tra giá trị, phần tử trùng, quyền ghi và cập nhật đồng thời. SQL hiện đại cũng hỗ trợ JSON hoặc ARRAY, nhưng **lưu một mảng trong cột không tự tạo khóa ngoại hoặc ràng buộc duy nhất trên từng phần tử**.

Khi cần tìm kiếm, tham chiếu, kiểm tra và quản lý vòng đời từng ngôn ngữ, sở thích, hai bảng quan hệ thường dễ kiểm chứng hơn. Nếu cần bảng phân tích đã làm phẳng, hãy xác định **nguồn dữ liệu chuẩn**, ngữ nghĩa của từng tổ hợp và cơ chế đồng bộ.

## 9. Quy trình phát hiện và xử lý vi phạm 4NF

1. **Xác định grain.** Mỗi hàng là một cặp độc lập, một bộ ba có kết hợp thực sự, hay một bản ghi sự kiện?
2. **Liệt kê phụ thuộc hàm và khóa ứng viên.** Kiểm tra 1NF đến BCNF trước; bảng đạt BCNF vẫn có thể có MVD vi phạm 4NF.
3. **Tìm các tập nhiều giá trị.** Với cùng X có nhiều Y và nhiều Z không? Hai tập có độc lập hay chỉ một số cặp hợp lệ?
4. **Xác minh MVD theo ngữ nghĩa.** Với hai bộ cùng X, các bộ hoán đổi Y và Z có bắt buộc tồn tại trong mọi trạng thái hợp lệ không?
5. **Kiểm tra tính không tầm thường.** Nếu **Y ⊆ X** hoặc **X ∪ Y = R**, MVD là tầm thường và không tạo vi phạm 4NF.
6. **Kiểm tra siêu khóa.** Dùng bao đóng theo các phụ thuộc hàm để xét X có xác định toàn bộ thuộc tính của R không.
7. **Phân rã khi có vi phạm.** Dùng **R1 = X ∪ Y** và **R2 = R − (Y − X)**; tiếp tục kiểm tra các quan hệ con.
8. **Chứng minh lossless và bảo vệ ràng buộc.** MVD hợp lệ làm phép nối các hình chiếu không mất thông tin; bổ sung khóa, khóa ngoại và các quy tắc về phần tử.
9. **Thử ca biên.** Không có Y, không có Z, một hay nhiều phần tử, thêm phần tử mới, xóa phần tử cuối, và trường hợp một tổ hợp bị cấm.
10. **Tối ưu sau khi mô hình đúng.** Xem xét chỉ mục, phép nối, document hoặc mô hình phân tích theo nhu cầu đọc/ghi thực tế.

Việc kiểm tra các tổ hợp đang có bằng truy vấn chỉ tìm dấu hiệu thiếu bộ hoán đổi, **không chứng minh MVD**: dữ liệu hiện tại có thể tình cờ đầy đủ. Nguồn quyết định phải là **quy tắc nghiệp vụ**, không chỉ là một mẫu dữ liệu.

## 10. Bài tập vận dụng

### Bài 1. Dự án có thành viên và công cụ

Một hệ thống quản lý dự án ghi:

| project_id | member_id | tool_id |
| --- | --- | --- |
| P01 | U01 | T01 |
| P01 | U01 | T02 |
| P01 | U02 | T01 |
| P01 | U02 | T02 |

Quy tắc: việc phân thành viên vào dự án **độc lập** với danh sách công cụ được phê duyệt cho dự án; mọi thành viên dự án đều được phép sử dụng mọi công cụ của dự án. Một dự án có nhiều thành viên và nhiều công cụ; không có phụ thuộc hàm nghiệp vụ không tầm thường nào khác.

**Yêu cầu:**

1. Viết các MVD theo project_id.
2. Tìm khóa ứng viên; đánh giá BCNF và 4NF.
3. Phân rã thành các bảng, chỉ ra khóa chính.
4. Chứng minh phân rã lossless và xem xét dự án chưa được cấp công cụ.

<details>
<summary>Gợi ý lời giải bài 1</summary>

~~~text
project_id ->> member_id
project_id ->> tool_id
~~~

Vì không có FD không tầm thường, khóa ứng viên là **(project_id, member_id, tool_id)**. Bảng đạt **BCNF** nhưng chưa đạt **4NF**: các MVD không tầm thường có project_id không là siêu khóa.

Phân rã thành **project_members(project_id, member_id)** và **project_tools(project_id, tool_id)**, mỗi bảng có khóa chính là cặp thuộc tính tương ứng. Thêm **projects(project_id, ...)** để lưu dự án độc lập, kể cả dự án chưa có công cụ.

Vì mọi tổ hợp thành viên–công cụ đều hợp lệ theo quy tắc, nối hai bảng con theo project_id khôi phục đúng quan hệ gốc khi cả hai tập không rỗng. Dự án chưa có công cụ vẫn lưu được thành viên mà không cần tạo dòng có tool_id giả.

</details>

### Bài 2. Khi MVD không đúng

Một hệ thống thương mại điện tử ghi các biến thể:

~~~text
P01, RED, S
P01, RED, M
P01, BLUE, L
~~~

**Yêu cầu:** kiểm tra **product_id ↠ color**; nếu tách thành hai bảng product_colors và product_sizes rồi nối, các bộ giả nào xuất hiện? Thiết kế lại để lưu đúng các biến thể.

<details>
<summary>Gợi ý lời giải bài 2</summary>

MVD **product_id ↠ color** **không đúng**. Từ **(P01, RED, S)** và **(P01, BLUE, L)**, hoán đổi theo MVD sẽ đòi hỏi **(P01, RED, L)** và **(P01, BLUE, S)**, nhưng hai biến thể này không được phép.

Tách và nối sẽ sinh thêm **(P01, RED, L)**, **(P01, BLUE, S)** và **(P01, BLUE, M)**. Nên giữ **product_variants(product_id, color, size, ...)** cho các tổ hợp thực sự tồn tại và khai báo khóa hoặc **UNIQUE** theo quy tắc nghiệp vụ.

</details>

### Bài 3. Một FD có tạo MVD không?

Cho quan hệ:

~~~text
employees(employee_id, department_id, department_name)
department_id -> department_name
~~~

Hãy xác định có suy ra **department_id ↠ department_name** hay không, nó có không tầm thường không, và quan hệ có thể đạt BCNF/4NF hay không nếu mỗi phòng có nhiều nhân viên.

**Gợi ý:** FD suy ra MVD. MVD đó không tầm thường vì còn **employee_id** ở ngoài hợp của X và Y. Khi phòng có nhiều nhân viên, department_id không là siêu khóa, nên phụ thuộc vi phạm **BCNF** dưới dạng FD và vi phạm **4NF** dưới dạng MVD. Tách bảng **departments(department_id, department_name)** và giữ **department_id** làm khóa ngoại trong **employees**.

## 11. Những sai lầm cần tránh

| Nhận định sai | Cách đánh giá đúng |
| --- | --- |
| “Đạt BCNF thì chắc chắn đạt 4NF.” | BCNF kiểm tra FD; 4NF còn kiểm tra **MVD không tầm thường**. |
| “Hai cột cùng lặp nhiều lần là có MVD.” | Phải chứng minh các tập **kết hợp độc lập** theo nghiệp vụ. |
| “MVD giống FD, mỗi X chỉ có một Y.” | MVD có thể cho **nhiều Y** và ràng buộc tổ hợp với phần còn lại. |
| “Mọi MVD đều vi phạm 4NF.” | Chỉ MVD **không tầm thường** với **X không là siêu khóa** mới vi phạm. |
| “Nối hai bảng con tạo nhiều hàng nghĩa là phân rã bị mất thông tin.” | Với MVD hợp lệ, phép nối đúng bằng quan hệ gốc; các tổ hợp xuất hiện khi đọc. |
| “Tách màu và kích cỡ của mọi sản phẩm đều an toàn.” | Nếu chỉ một số cặp màu–cỡ bán được, phép nối **sinh biến thể giả**. |
| “Thêm surrogate ID làm bảng đạt 4NF.” | ID không thay đổi tính độc lập giữa các tập nhiều giá trị. |
| “Phải JOIN hai bảng con trong mọi truy vấn.” | Nếu cần từng danh sách, truy vấn riêng; chỉ nối khi cần tổ hợp. |

## 12. Ghi nhớ

**4NF yêu cầu vế trái của mọi phụ thuộc đa trị không tầm thường là siêu khóa.** Trong ví dụ học viên, **student_id ↠ language_code** và **student_id ↠ hobby_code** là hai MVD không tầm thường: các ngôn ngữ và sở thích độc lập nhưng bị nhân thành mọi cặp khi gộp trong một bảng. Bảng này có thể đạt BCNF mà vẫn cần phân rã thành **student_languages** và **student_hobbies**.

Quyết định phân rã phải dựa vào **ngữ nghĩa kết hợp**. Khi các tập độc lập, tách theo MVD hợp lệ giúp phép nối không mất thông tin và giảm bất thường thêm, sửa, xóa. Khi từng tổ hợp có ý nghĩa riêng, như màu và kích cỡ của biến thể sản phẩm, tách hai tập có thể tạo dữ liệu sai. Hãy xác nhận quy tắc nghiệp vụ, kiểm tra siêu khóa, chứng minh lossless join rồi mới tối ưu chỉ mục hoặc chọn mô hình quan hệ, document hay phân tích phù hợp.
