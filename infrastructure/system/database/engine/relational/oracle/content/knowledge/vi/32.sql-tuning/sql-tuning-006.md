# Tối ưu EXISTS, NOT EXISTS và xử lý quan hệ nhiều-nhiều trong Oracle

## 1. Bài toán tồn tại trong SQL

Nhiều truy vấn nghiệp vụ không cần lấy dữ liệu từ bảng liên quan. Chúng chỉ cần trả lời: khách hàng có đơn hàng chưa thanh toán không, sinh viên đã đăng ký môn học chưa, người dùng không có quyền nào, hay sản phẩm không có dòng tồn kho ở kho đang xét?

SQL cung cấp hai cấu trúc diễn đạt trực tiếp:

- **EXISTS:** đúng khi subquery trả về ít nhất một row.
- **NOT EXISTS:** đúng khi subquery không trả về row nào.

Oracle có thể tối ưu những mẫu này thành **semijoin** hoặc **antijoin**. Các phép nối này chỉ cần xác định outer row có match hay không; chúng không nhân bản outer row theo số lượng match như join thông thường.

Đây là lý do EXISTS và NOT EXISTS hữu ích khi truy vấn quan hệ nhiều-nhiều. Chúng thường diễn tả đúng ý nghĩa nghiệp vụ hơn JOIN kết hợp DISTINCT hoặc GROUP BY, đồng thời tránh lỗi do duplicate và NULL.

> Nội dung tập trung vào Oracle Database 19c. Optimizer có thể biến đổi subquery thành nhiều execution plan khác nhau; không có bảo đảm mọi câu EXISTS sẽ dùng cùng một join method. Hãy xác nhận bằng cursor plan và số liệu thực thi.

## 2. Mô hình quan hệ nhiều-nhiều

Quan hệ nhiều-nhiều (many-to-many, M:N) xảy ra khi một row ở bảng A có thể liên kết với nhiều row ở bảng B, đồng thời một row ở bảng B cũng có thể liên kết với nhiều row ở bảng A.

Ví dụ sinh viên và môn học:

- Một sinh viên đăng ký nhiều môn.
- Một môn có nhiều sinh viên đăng ký.

Ta biểu diễn quan hệ bằng bảng liên kết STUDENT_COURSES:

~~~text
STUDENTS                 STUDENT_COURSES                 COURSES
---------                ----------------                -------
student_id  PK  1 ----<  student_id   FK   >---- 1       course_id PK
name                     course_id    FK                 course_name
                         enrolled_at
                         status

Một sinh viên có nhiều dòng liên kết.
Một môn học có nhiều dòng liên kết.
~~~

### 2.1. Tạo bảng và ràng buộc

~~~sql
CREATE TABLE students (
    student_id NUMBER CONSTRAINT students_pk PRIMARY KEY,
    full_name  VARCHAR2(100) NOT NULL
);

CREATE TABLE courses (
    course_id   NUMBER CONSTRAINT courses_pk PRIMARY KEY,
    course_code VARCHAR2(20) NOT NULL,
    course_name VARCHAR2(200) NOT NULL,
    CONSTRAINT courses_code_uk UNIQUE (course_code)
);

CREATE TABLE student_courses (
    student_id NUMBER NOT NULL,
    course_id  NUMBER NOT NULL,
    enrolled_at DATE DEFAULT SYSDATE NOT NULL,
    status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT student_courses_pk
        PRIMARY KEY (student_id, course_id),
    CONSTRAINT student_courses_student_fk
        FOREIGN KEY (student_id) REFERENCES students(student_id),
    CONSTRAINT student_courses_course_fk
        FOREIGN KEY (course_id) REFERENCES courses(course_id),
    CONSTRAINT student_courses_status_ck
        CHECK (status IN ('ACTIVE', 'CANCELLED', 'COMPLETED'))
);
~~~

Khóa chính ghép (student_id, course_id) bảo đảm một sinh viên chỉ có một quan hệ với một môn tại một thời điểm theo mô hình đơn giản này. Nếu nghiệp vụ cần lưu nhiều lần đăng ký trong các học kỳ khác nhau, khóa phải bao gồm term/attempt hoặc dùng enrollment_id riêng cùng unique constraint phù hợp.

### 2.2. Bảng liên kết có thể chứa thuộc tính nghiệp vụ

Bảng liên kết không chỉ lưu hai foreign key. Nó có thể lưu ngày đăng ký, trạng thái, điểm số, vai trò, thời gian bắt đầu/kết thúc hoặc nguồn tạo quan hệ. Những thuộc tính này thuộc về chính quan hệ M:N, không thuộc riêng STUDENTS hay COURSES.

### 2.3. Tránh lưu danh sách khóa trong một cột

Không nên lưu course_ids = '10,20,30' trong một cột của STUDENTS rồi dùng LIKE hoặc chuỗi để tìm quan hệ. Cách đó làm mất khả năng dùng foreign key, unique constraint, index theo từng khóa và kiểm tra dữ liệu nhất quán.

## 3. EXISTS: kiểm tra ít nhất một quan hệ tồn tại

### 3.1. Cú pháp

~~~sql
SELECT ...
FROM outer_table o
WHERE EXISTS (
    SELECT 1
    FROM related_table r
    WHERE r.key = o.key
);
~~~

Subquery thường có điều kiện tương quan tham chiếu tới row của query bên ngoài. Về mặt logic, EXISTS đúng nếu có ít nhất một row phù hợp.

SELECT 1 là quy ước dễ đọc vì giá trị trong select list không quan trọng; EXISTS chỉ xét subquery có trả row hay không. SELECT * thường có cùng semantics trong trường hợp này, nhưng SELECT 1 làm rõ ý định.

### 3.2. Sinh viên đã đăng ký ít nhất một môn

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

Kết quả chứa mỗi sinh viên có ít nhất một dòng trong STUDENT_COURSES. Một sinh viên đăng ký 1 môn hay 10 môn vẫn chỉ xuất hiện một lần.

### 3.3. Sinh viên đăng ký môn DB101

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c
      ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code = 'DB101'
      AND sc.status = 'ACTIVE'
);
~~~

Truy vấn trả sinh viên có ít nhất một enrollment ACTIVE cho môn DB101. JOIN trong subquery chỉ phục vụ xác định quan hệ phù hợp; outer query vẫn trả mỗi sinh viên tối đa một lần.

### 3.4. EXISTS không cần đếm hết các match

Tránh dùng COUNT(*) chỉ để biết có row hay không:

~~~sql
SELECT s.student_id
FROM students s
WHERE (
    SELECT COUNT(*)
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
) > 0;
~~~

Viết trực tiếp:

~~~sql
SELECT s.student_id
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

COUNT(*) biểu đạt bài toán đếm, còn EXISTS biểu đạt bài toán tồn tại. Oracle có thể tối ưu nhiều biểu thức, nhưng nên viết SQL đúng semantics trước.

### 3.5. Không thêm ROWNUM = 1 vào EXISTS

Không cần thêm ROWNUM = 1. EXISTS vốn chỉ cần biết subquery có row hay không. ROWNUM không làm ý định rõ hơn và có thể cản trở một số transformation tùy cấu trúc.

## 4. NOT EXISTS: tìm row không có quan hệ phù hợp

### 4.1. Cú pháp

~~~sql
SELECT ...
FROM outer_table o
WHERE NOT EXISTS (
    SELECT 1
    FROM related_table r
    WHERE r.key = o.key
);
~~~

NOT EXISTS đúng khi subquery trả empty set.

### 4.2. Sinh viên chưa đăng ký môn nào

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

### 4.3. Sinh viên chưa đăng ký DB101

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c
      ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code = 'DB101'
      AND sc.status = 'ACTIVE'
);
~~~

Đây là câu hỏi “chưa có đăng ký ACTIVE cho DB101”, không nhất thiết là “chưa từng đăng ký DB101”. Nếu muốn tính cả trạng thái CANCELLED hoặc COMPLETED, bỏ điều kiện status hoặc định nghĩa lại predicate theo nghiệp vụ.

### 4.4. Predicate bên trong NOT EXISTS định nghĩa điều gì không tồn tại

So sánh:

~~~sql
-- Không có bất kỳ enrollment nào
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
)
~~~

~~~sql
-- Không có enrollment đang ACTIVE
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.status = 'ACTIVE'
)
~~~

Sinh viên có enrollment CANCELLED bị loại khỏi kết quả thứ nhất nhưng có thể xuất hiện trong kết quả thứ hai. Predicate trong subquery là một phần của định nghĩa nghiệp vụ, không chỉ là chi tiết tối ưu.

## 5. EXISTS và JOIN khác nhau về cardinality

### 5.1. JOIN có thể nhân bản outer row

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id;
~~~

Nếu sinh viên đăng ký 5 môn, query trả 5 row cho sinh viên đó. Nếu mục tiêu chỉ là danh sách sinh viên có đăng ký, đây là kết quả thừa.

Có thể thêm DISTINCT, nhưng DISTINCT có thể cần sort hoặc hash unique để loại duplicate. Query đang tạo duplicate rồi mới loại bỏ.

### 5.2. EXISTS diễn đạt semijoin

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

Semijoin giữ outer row nếu có match, nhưng không nhân bản outer row theo số lượng match. Đây đúng với yêu cầu “có ít nhất một quan hệ”.

### 5.3. Khi nào JOIN là lựa chọn đúng?

Nếu cần hiển thị dữ liệu của từng quan hệ, ví dụ mỗi sinh viên cùng từng môn đã đăng ký, JOIN là lựa chọn tự nhiên:

~~~sql
SELECT s.student_id,
       s.full_name,
       c.course_code,
       c.course_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id
JOIN courses c
  ON c.course_id = sc.course_id;
~~~

Không thay JOIN bằng EXISTS khi kết quả cần cột từ bảng liên quan hoặc cần một row cho mỗi quan hệ. Chọn cấu trúc theo hình dạng kết quả cần trả về.

### 5.4. Tạo cờ tồn tại trong SELECT

~~~sql
SELECT s.student_id,
       s.full_name,
       CASE
           WHEN EXISTS (
               SELECT 1
               FROM student_courses sc
               WHERE sc.student_id = s.student_id
                 AND sc.status = 'ACTIVE'
           )
           THEN 'Y'
           ELSE 'N'
       END AS has_active_course
FROM students s;
~~~

Cách này tạo cờ tồn tại mà không cần join và group dữ liệu liên kết vào outer result.

## 6. Semijoin và antijoin trong Oracle optimizer

### 6.1. Semijoin

Semijoin trả outer row nếu có ít nhất một row từ inner row source thỏa join condition. Nó không trả một outer row cho mỗi inner match.

Các operation có thể thấy:

- NESTED LOOPS SEMI.
- HASH JOIN SEMI.
- MERGE JOIN SEMI.

### 6.2. Antijoin

Antijoin trả outer row nếu không có row nào từ inner row source thỏa join condition. Nó là cách triển khai tự nhiên cho NOT EXISTS.

Các operation có thể thấy:

- NESTED LOOPS ANTI.
- HASH JOIN ANTI.
- MERGE JOIN ANTI.

Tên operation thực tế phụ thuộc plan, query transformation và phiên bản.

### 6.3. Correlated subquery không có nghĩa luôn chạy lặp từng row

Ví dụ:

~~~sql
SELECT s.student_id
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.course_id = 10
);
~~~

Đây là correlated subquery vì nó tham chiếu alias S của query bên ngoài. Nhưng không nên kết luận Oracle bắt buộc thực thi subquery một lần cho mỗi outer row. Optimizer có thể unnest subquery và biến nó thành semijoin/antijoin, hoặc chọn một plan khác.

Với một số query phức tạp, aggregate, ROWNUM, set operator hoặc cấu trúc hạn chế transformation, subquery có thể không được unnest. Khi đó plan có thể dùng FILTER hoặc operation khác.

### 6.4. EXISTS không bảo đảm short-circuit vật lý theo cách người viết nghĩ

Về logic, chỉ cần một match để EXISTS là TRUE. Optimizer và execution engine có thể tận dụng điều đó. Tuy nhiên, không nên giả định mỗi trường hợp luôn dừng sau một phép đọc vật lý duy nhất. Join method, batching, parallel execution và access path quyết định công việc thực tế.

Hãy đọc A-Rows, Starts, Buffers và operation thay vì dựa vào khẩu hiệu “EXISTS luôn nhanh hơn JOIN”.

### 6.5. EXISTS không tự động nhanh hơn mọi cấu trúc tương đương

Optimizer có thể biến đổi EXISTS, IN và một số join pattern về plan tương tự. Hiệu năng phụ thuộc số row outer/inner, selectivity, index, statistics, data skew, join method, khả năng unnesting, bind values và child cursor.

Viết EXISTS khi semantics là existence. Sau đó mới tối ưu dựa trên plan.

## 7. NOT EXISTS và bẫy NULL của NOT IN

Đây là điểm rất quan trọng khi viết anti-join.

### 7.1. NOT IN với subquery chứa NULL

~~~sql
SELECT s.student_id
FROM students s
WHERE s.student_id NOT IN (
    SELECT sc.student_id
    FROM student_courses sc
);
~~~

Nếu subquery trả về dù chỉ một NULL, phép so sánh NOT IN có thể trở thành UNKNOWN đối với các giá trị không match. WHERE chỉ giữ row có điều kiện TRUE, nên kết quả có thể rỗng ngoài mong đợi.

SQL dùng logic ba giá trị:

- TRUE: điều kiện đúng.
- FALSE: điều kiện sai.
- UNKNOWN: thường phát sinh khi so sánh với NULL.

WHERE loại cả FALSE lẫn UNKNOWN.

### 7.2. Ví dụ đơn giản

~~~sql
SELECT 1
FROM dual
WHERE 10 NOT IN (20, NULL);
~~~

Điều kiện tương đương:

~~~text
10 <> 20 AND 10 <> NULL
TRUE AND UNKNOWN = UNKNOWN
~~~

Do đó không có row nào được trả về.

### 7.3. NOT EXISTS không gặp bẫy NULL giống NOT IN

~~~sql
SELECT s.student_id
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
);
~~~

Điều kiện tương quan là equality. Một NULL trong SC.STUDENT_ID không bằng bất kỳ S.STUDENT_ID nào, nên nó không tạo match cho outer row. NULL đó không làm toàn bộ NOT EXISTS trở thành UNKNOWN.

Trong mô hình bảng liên kết chuẩn, STUDENT_ID đã NOT NULL. Dù vậy, NOT EXISTS vẫn là lựa chọn dễ bảo vệ hơn khi subquery có khả năng chứa NULL.

### 7.4. NOT IN có thể dùng khi đảm bảo non-null

Nếu cả outer expression và subquery result đều được bảo đảm NOT NULL, NOT IN có semantics rõ ràng. Tuy nhiên, NOT EXISTS thường diễn tả quan hệ tương quan trực tiếp hơn và không phụ thuộc vào giả định subquery không trả NULL.

### 7.5. NULL ở outer key cũng cần quy định nghiệp vụ

Với:

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM child_table c
    WHERE c.parent_id = p.parent_id
)
~~~

nếu P.PARENT_ID là NULL, equality không tìm được child match, nên NOT EXISTS có thể TRUE. Nếu nghiệp vụ không muốn giữ outer row có key NULL, thêm:

~~~sql
WHERE p.parent_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM child_table c
      WHERE c.parent_id = p.parent_id
  )
~~~

Không coi NULL là một khóa có thể match NULL bằng equality. Nếu nghiệp vụ muốn NULL-null được xem là cùng nhóm, phải diễn tả semantics riêng.

## 8. Thiết kế index cho quan hệ nhiều-nhiều

### 8.1. Primary key ghép hỗ trợ một chiều

Với:

~~~sql
PRIMARY KEY (student_id, course_id)
~~~

Oracle tạo unique index tương ứng theo thứ tự cột đó. Index này phù hợp với lookup bắt đầu từ STUDENT_ID và có thể kiểm tra tiếp COURSE_ID trong cùng index.

### 8.2. Truy cập theo chiều ngược lại

Nếu truy vấn thường bắt đầu từ COURSE_ID để tìm sinh viên, index (student_id, course_id) không có COURSE_ID là leading column. Cân nhắc:

~~~sql
CREATE INDEX student_courses_course_ix
ON student_courses(course_id, student_id);
~~~

Index này hỗ trợ lookup theo COURSE_ID và cung cấp STUDENT_ID ngay trong index entry.

### 8.3. Hai hướng truy cập phổ biến

| Câu hỏi | Index thường hữu ích |
| --- | --- |
| Sinh viên đã đăng ký môn nào? | (student_id, course_id) |
| Môn học có những sinh viên nào? | (course_id, student_id) |
| Sinh viên có đăng ký môn X không? | (student_id, course_id) hoặc index bắt đầu bằng cột lọc thích hợp |
| Môn X có sinh viên S không? | (course_id, student_id) hoặc unique key theo chiều ngược |

Không nhất thiết tạo cả hai index cho mọi bảng. Cần xét tần suất query, kích thước bảng liên kết, chi phí INSERT/DELETE và dung lượng index.

### 8.4. Foreign key không tự tạo index

Oracle không tự động tạo index trên cột foreign key chỉ vì khai báo constraint. Khi bảng cha được DELETE/UPDATE khóa hoặc có workload JOIN/EXISTS từ phía child, index foreign key thường hữu ích để tránh quét toàn bộ bảng con và giảm vấn đề khóa.

Với STUDENT_COURSES:

- Primary key (student_id, course_id) đã có index bắt đầu bằng STUDENT_ID.
- Index (course_id, student_id) hỗ trợ foreign key COURSE_ID và truy vấn ngược.

### 8.5. Thêm trạng thái vào index

Nếu truy vấn phổ biến là tìm enrollment ACTIVE:

~~~sql
WHERE sc.student_id = :student_id
  AND sc.status = 'ACTIVE'
~~~

có thể cân nhắc:

~~~sql
CREATE INDEX student_courses_student_status_ix
ON student_courses(student_id, status, course_id);
~~~

Nếu truy vấn bắt đầu từ course:

~~~sql
CREATE INDEX student_courses_course_status_ix
ON student_courses(course_id, status, student_id);
~~~

Index phải phù hợp với predicate và chiều truy cập. Không thêm STATUS vào mọi index theo thói quen; nếu status chỉ có vài giá trị, selectivity thấp và chi phí index maintenance có thể không đáng.

### 8.6. Unique constraint bảo đảm tính đúng đắn

Nếu nghiệp vụ không cho phép đăng ký trùng, dùng unique constraint/primary key. Không chỉ dựa vào:

~~~sql
IF NOT EXISTS (...) THEN
    INSERT ...
END IF;
~~~

Hai session đồng thời có thể cùng thấy chưa tồn tại rồi cùng INSERT. Unique constraint mới là lớp bảo đảm cuối cùng. Ứng dụng cần xử lý DUP_VAL_ON_INDEX hoặc lỗi tương ứng khi cạnh tranh xảy ra.

### 8.7. Mô hình có lịch sử quan hệ

Nếu cần lưu nhiều lần đăng ký:

~~~sql
CREATE TABLE student_enrollments (
    enrollment_id NUMBER PRIMARY KEY,
    student_id NUMBER NOT NULL,
    course_id NUMBER NOT NULL,
    term_code VARCHAR2(20) NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    status VARCHAR2(20) NOT NULL,
    CONSTRAINT enrollment_student_fk
        FOREIGN KEY (student_id) REFERENCES students(student_id),
    CONSTRAINT enrollment_course_fk
        FOREIGN KEY (course_id) REFERENCES courses(course_id),
    CONSTRAINT enrollment_term_uk
        UNIQUE (student_id, course_id, term_code)
);
~~~

Nếu mỗi sinh viên chỉ có một enrollment cho mỗi course trong một term, unique constraint trên ba cột đó phản ánh quy tắc. Index và EXISTS predicate cần phản ánh định nghĩa quan hệ hiện tại, ví dụ thêm TERM_CODE và STATUS.

## 9. Các mẫu truy vấn M:N thường gặp

### 9.1. Tìm course có ít nhất một sinh viên

~~~sql
SELECT c.course_id,
       c.course_code,
       c.course_name
FROM courses c
WHERE c.course_code = 'DB101'
  AND EXISTS (
      SELECT 1
      FROM student_courses sc
      WHERE sc.course_id = c.course_id
  );
~~~

Nếu cần danh sách sinh viên cho môn đó, dùng JOIN:

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id
JOIN courses c
  ON c.course_id = sc.course_id
WHERE c.course_code = 'DB101';
~~~

### 9.2. Tìm sinh viên không có enrollment ACTIVE

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.status = 'ACTIVE'
);
~~~

### 9.3. Tìm course chưa có sinh viên đăng ký

~~~sql
SELECT c.course_id,
       c.course_code
FROM courses c
WHERE NOT EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.course_id = c.course_id
);
~~~

Truy vấn này thường hưởng lợi từ index bắt đầu bằng COURSE_ID.

### 9.4. Tìm sinh viên đăng ký ít nhất một trong hai môn

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code IN ('DB101', 'DB102')
);
~~~

Một sinh viên đăng ký cả hai môn vẫn chỉ xuất hiện một lần.

### 9.5. Tìm sinh viên đăng ký cả hai môn

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code = 'DB101'
      AND sc.status = 'ACTIVE'
)
AND EXISTS (
    SELECT 1
    FROM student_courses sc
    JOIN courses c ON c.course_id = sc.course_id
    WHERE sc.student_id = s.student_id
      AND c.course_code = 'DB102'
      AND sc.status = 'ACTIVE'
);
~~~

Mỗi EXISTS kiểm tra một quan hệ riêng. Optimizer có thể xử lý hai subquery bằng các access path khác nhau.

### 9.6. Điều kiện phải cùng nằm trên một row liên kết

Giả sử cần tìm sinh viên có một enrollment vừa ACTIVE vừa thuộc term 2025A. Hãy đặt cả hai predicate trong cùng EXISTS:

~~~sql
WHERE EXISTS (
    SELECT 1
    FROM student_enrollments e
    WHERE e.student_id = s.student_id
      AND e.status = 'ACTIVE'
      AND e.term_code = '2025A'
)
~~~

Nếu viết thành hai EXISTS riêng, hai điều kiện có thể được thỏa bởi hai enrollment khác nhau. Chỉ dùng hai EXISTS nếu nghiệp vụ cho phép hai quan hệ riêng biệt.

### 9.7. Tìm sinh viên có đủ tất cả môn bắt buộc

Đây là bài toán relational division. Có thể diễn đạt bằng double NOT EXISTS:

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
WHERE NOT EXISTS (
    SELECT 1
    FROM required_courses rc
    WHERE NOT EXISTS (
        SELECT 1
        FROM student_courses sc
        WHERE sc.student_id = s.student_id
          AND sc.course_id = rc.course_id
          AND sc.status IN ('ACTIVE', 'COMPLETED')
    )
);
~~~

Đọc từ trong ra ngoài:

1. Subquery trong cùng tìm một môn bắt buộc mà sinh viên chưa có enrollment hợp lệ.
2. NOT EXISTS ở giữa xác định môn bắt buộc đó không tồn tại trong các enrollment của sinh viên.
3. NOT EXISTS bên ngoài yêu cầu không có môn bắt buộc nào bị thiếu.
4. Kết quả là sinh viên đã đáp ứng tất cả môn bắt buộc.

Nếu REQUIRED_COURSES rỗng, điều kiện double NOT EXISTS đúng với mọi sinh viên theo logic “không có môn bắt buộc nào bị thiếu”. Nếu nghiệp vụ yêu cầu danh sách môn bắt buộc phải có ít nhất một môn, thêm điều kiện EXISTS trên REQUIRED_COURSES.

### 9.8. Tìm sinh viên có ít nhất N quan hệ

Nếu câu hỏi thực sự cần số lượng, dùng GROUP BY/HAVING:

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
JOIN student_courses sc
  ON sc.student_id = s.student_id
WHERE sc.status = 'ACTIVE'
GROUP BY s.student_id, s.full_name
HAVING COUNT(*) >= 3;
~~~

Đây là bài toán đếm, không phải chỉ kiểm tra tồn tại.

## 10. LEFT JOIN ... IS NULL so với NOT EXISTS

Một cách viết anti-join khác:

~~~sql
SELECT s.student_id,
       s.full_name
FROM students s
LEFT JOIN student_courses sc
  ON sc.student_id = s.student_id
WHERE sc.student_id IS NULL;
~~~

Với điều kiện join và cột kiểm tra được chọn đúng, kết quả có thể tương đương NOT EXISTS.

### 10.1. Đặt predicate đúng vị trí

Muốn tìm sinh viên không có enrollment ACTIVE, điều kiện status phải nằm trong ON:

~~~sql
SELECT s.student_id
FROM students s
LEFT JOIN student_courses sc
  ON sc.student_id = s.student_id
 AND sc.status = 'ACTIVE'
WHERE sc.student_id IS NULL;
~~~

Nếu đặt SC.STATUS = 'ACTIVE' ở WHERE cùng với SC.STUDENT_ID IS NULL, row được outer join bổ sung có STATUS = NULL và không thỏa điều kiện. Query không còn thể hiện đúng mục đích.

### 10.2. Chọn cột NOT NULL để kiểm tra NULL

Trong outer join anti-pattern, cột dùng IS NULL phải không thể NULL trên row match, thường là primary key hoặc cột NOT NULL. Nếu chọn một cột nullable, row có match nhưng cột đó NULL có thể bị nhận nhầm là không match.

### 10.3. Vì sao NOT EXISTS thường rõ hơn?

NOT EXISTS đặt tất cả predicate của quan hệ vào một subquery và diễn tả trực tiếp “không tồn tại row phù hợp”. Nó ít phụ thuộc vào việc chọn cột kiểm tra NULL và giảm nguy cơ đặt điều kiện nhầm giữa ON và WHERE.

Không có quy tắc rằng NOT EXISTS luôn nhanh hơn LEFT JOIN IS NULL. Oracle có thể biến đổi cả hai thành antijoin tương tự. Chọn cách dễ đọc, đúng semantics rồi so sánh plan nếu hiệu năng quan trọng.

## 11. Subquery unnesting và điều kiện ảnh hưởng transformation

### 11.1. Unnesting là gì?

Subquery unnesting là query transformation đưa subquery vào query block bên ngoài để optimizer đánh giá chung. Với EXISTS/NOT EXISTS, transformation có thể tạo semijoin/antijoin.

Ví dụ:

~~~sql
SELECT s.student_id
FROM students s
WHERE EXISTS (
    SELECT 1
    FROM student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.course_id = 10
);
~~~

Optimizer có thể xử lý thành semijoin giữa STUDENTS và STUDENT_COURSES.

### 11.2. Khi nào subquery có thể không được unnest?

Một số cấu trúc có thể hạn chế hoặc ngăn transformation tùy ngữ cảnh:

- ROWNUM trong subquery.
- Một số aggregate hoặc GROUP BY.
- Set operators.
- Subquery chứa cấu trúc phức tạp hoặc có semantics đặc biệt.
- Một số outer references hoặc hàm không phù hợp.

Không nên ghi nhớ một danh sách như luật tuyệt đối cho mọi phiên bản. Hãy kiểm tra SQL Tuning Guide và plan thực tế.

### 11.3. FILTER operation

Nếu subquery không được unnest, plan có thể hiển thị FILTER operation. Điều đó không tự động chứng minh query chậm. Cần xem Starts, A-Rows, buffers và chi phí subquery cho mỗi lần đánh giá.

Nếu outer row source nhỏ và inner lookup có index tốt, FILTER với correlated subquery có thể hiệu quả. Nếu outer source rất lớn và subquery lặp nhiều lần, semijoin/hash-based strategy có thể phù hợp hơn.

### 11.4. Không thêm hint trước khi hiểu plan

Oracle có optimizer hints ảnh hưởng join method hoặc transformation. Không nên thêm hint chỉ vì muốn nhìn thấy HASH JOIN SEMI hoặc NESTED LOOPS SEMI. Hints có thể làm plan kém ổn định khi dữ liệu, statistics hoặc bind values thay đổi.

Trước khi hint, xác nhận SQL đúng semantics, thu thập statistics, xem actual plan/runtime metrics, kiểm tra index và cardinality, rồi mới cân nhắc hint nếu có lý do đo được.

## 12. Chọn index và join method theo quy mô dữ liệu

### 12.1. Nested Loops Semi/Anti

Nested loops thường phù hợp khi outer row source tương đối nhỏ và inner lookup có index hiệu quả. Ví dụ chỉ có 10 course được chọn, cần tìm sinh viên đã đăng ký từng course; Oracle có thể dùng nested loops và index lookup trên STUDENT_COURSES.

### 12.2. Hash Join Semi/Anti

Hash join có thể phù hợp khi cả hai row source lớn và optimizer ước tính cần xử lý nhiều row. Oracle có thể build hash structure từ một phía rồi kiểm tra match ở phía còn lại. Không nhất thiết cần B-tree index để dùng hash semi/anti join.

### 12.3. Merge Join Semi/Anti

Merge join có thể được chọn khi row source đã có thứ tự phù hợp hoặc chi phí sort/merge cạnh tranh. Plan có thể hiển thị MERGE JOIN SEMI hoặc MERGE JOIN ANTI.

### 12.4. Không có join method tốt nhất cho mọi dữ liệu

Một bảng liên kết vài trăm row và một bảng liên kết vài trăm triệu row có đặc điểm khác nhau. Cùng một SQL có thể cần plan khác theo bind value hoặc data distribution. Đừng dùng một hint cố định để thay thế việc đo cardinality, selectivity và I/O.

## 13. Statistics và cardinality cho bảng liên kết

Optimizer cần biết số row trong bảng liên kết, số distinct STUDENT_ID và COURSE_ID, phân bố status, số row trung bình mỗi sinh viên/môn, data skew và tương quan giữa các cột.

Thu thập statistics:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'STUDENT_COURSES',
        cascade => TRUE
    );
END;
/
~~~

Với dữ liệu lệch nhiều, có thể cần histogram cho cột phù hợp. Không tạo histogram trên mọi cột theo thói quen; histogram làm tăng độ phức tạp của plan selection và cần được quản lý theo workload.

### 13.1. E-Rows và A-Rows

Khi xem actual plan:

- E-Rows là cardinality optimizer ước tính.
- A-Rows là số row thực tế operation trả ra.
- Starts cho biết operation được khởi chạy bao nhiêu lần.
- Buffers cho biết logical I/O.

Nếu một FILTER subquery có Starts rất lớn, kiểm tra inner access path và khả năng unnesting. Nếu HASH JOIN SEMI có E-Rows lệch lớn, kiểm tra statistics và data skew.

### 13.2. Correlation giữa các cột

Giả sử COURSE_ID = 10 gần như luôn có STATUS = ACTIVE, nhưng các cột được thống kê độc lập. Optimizer có thể ước tính sai selectivity của hai predicate kết hợp.

Extended statistics có thể hữu ích với một số nhóm cột có tương quan:

~~~sql
SELECT DBMS_STATS.CREATE_EXTENDED_STATS(
           ownname   => USER,
           tabname   => 'STUDENT_COURSES',
           extension => '(COURSE_ID, STATUS)'
       )
FROM dual;
~~~

Sau khi tạo extended statistics, thu thập lại table statistics và kiểm tra plan. Chỉ dùng khi có bằng chứng về tương quan và cardinality estimation error.

## 14. Những lỗi thiết kế và anti-pattern

| Anti-pattern | Vấn đề | Cách cải thiện |
| --- | --- | --- |
| JOIN rồi DISTINCT chỉ để kiểm tra tồn tại | Tạo duplicate rồi loại bỏ | Dùng EXISTS |
| COUNT(*) > 0 | Đếm khi chỉ cần biết có row | Dùng EXISTS |
| NOT IN với nullable subquery | NULL có thể làm điều kiện UNKNOWN | Dùng NOT EXISTS |
| Chỉ có index theo một chiều M:N | Truy vấn chiều ngược có thể quét nhiều row | Đánh giá index đảo thứ tự cột |
| Kiểm tra rồi INSERT không có unique constraint | Race condition giữa các session | Bảo đảm uniqueness bằng constraint |
| Predicate bảng phải đặt nhầm trong WHERE của LEFT JOIN | Làm sai outer join/anti-join | Đặt điều kiện match trong ON |
| Hai EXISTS cho điều kiện phải cùng một row | Hai điều kiện có thể được thỏa bởi hai quan hệ khác nhau | Đặt predicate trong cùng EXISTS |
| Nhầm không có quan hệ với không có quan hệ ACTIVE | Sai semantics nghiệp vụ | Định nghĩa rõ status trong subquery |
| Giả định correlated subquery luôn row-by-row | Bỏ qua subquery unnesting | Đọc actual plan |
| Giả định EXISTS luôn nhanh hơn JOIN | Chọn cú pháp theo khẩu hiệu | Chọn theo semantics và đo plan |

## 15. Lab: tối ưu EXISTS và NOT EXISTS trên quan hệ nhiều-nhiều

Lab tạo schema riêng. Kết quả plan có thể khác giữa các môi trường.

### 15.1. Tạo bảng

~~~sql
CREATE TABLE lab_students (
    student_id NUMBER PRIMARY KEY,
    full_name VARCHAR2(100) NOT NULL
);

CREATE TABLE lab_courses (
    course_id NUMBER PRIMARY KEY,
    course_code VARCHAR2(20) NOT NULL UNIQUE
);

CREATE TABLE lab_student_courses (
    student_id NUMBER NOT NULL,
    course_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    enrolled_at DATE DEFAULT SYSDATE NOT NULL,
    CONSTRAINT lab_sc_pk PRIMARY KEY (student_id, course_id),
    CONSTRAINT lab_sc_student_fk
        FOREIGN KEY (student_id) REFERENCES lab_students(student_id),
    CONSTRAINT lab_sc_course_fk
        FOREIGN KEY (course_id) REFERENCES lab_courses(course_id),
    CONSTRAINT lab_sc_status_ck
        CHECK (status IN ('ACTIVE', 'CANCELLED', 'COMPLETED'))
);

CREATE INDEX lab_sc_course_student_ix
ON lab_student_courses(course_id, student_id);
~~~

### 15.2. Tạo dữ liệu

~~~sql
INSERT INTO lab_students(student_id, full_name)
SELECT LEVEL,
       'Student ' || LEVEL
FROM dual
CONNECT BY LEVEL <= 10000;

INSERT INTO lab_courses(course_id, course_code)
SELECT LEVEL,
       'C' || TO_CHAR(LEVEL, 'FM000')
FROM dual
CONNECT BY LEVEL <= 100;

INSERT INTO lab_student_courses(student_id, course_id, status)
SELECT s.student_id,
       c.course_id,
       CASE
           WHEN MOD(s.student_id + c.course_id, 5) = 0
           THEN 'COMPLETED'
           ELSE 'ACTIVE'
       END
FROM lab_students s
JOIN lab_courses c
  ON c.course_id BETWEEN 1 AND 10
WHERE MOD(s.student_id + c.course_id, 7) = 0;

COMMIT;
~~~

### 15.3. Thu thập statistics

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_STUDENTS',
        cascade => TRUE
    );
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_COURSES',
        cascade => TRUE
    );
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'LAB_STUDENT_COURSES',
        cascade => TRUE
    );
END;
/
~~~

### 15.4. Tìm sinh viên có enrollment ACTIVE

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       s.student_id,
       s.full_name
FROM lab_students s
WHERE EXISTS (
    SELECT 1
    FROM lab_student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.status = 'ACTIVE'
);
~~~

Xem cursor plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +ALIAS'
    )
);
~~~

Quan sát xem Oracle dùng NESTED LOOPS SEMI, HASH JOIN SEMI, FILTER hay operation khác. Kiểm tra index access, E-Rows, A-Rows, Starts và Buffers.

### 15.5. Tìm sinh viên không có enrollment ACTIVE

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       s.student_id,
       s.full_name
FROM lab_students s
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.status = 'ACTIVE'
);
~~~

Đọc plan và tìm operation anti-join nếu subquery được unnest. Nếu có FILTER, xem số Starts và chi phí inner lookup.

### 15.6. So sánh với JOIN DISTINCT

~~~sql
SELECT DISTINCT
       s.student_id,
       s.full_name
FROM lab_students s
JOIN lab_student_courses sc
  ON sc.student_id = s.student_id
WHERE sc.status = 'ACTIVE';
~~~

So sánh kết quả và plan với EXISTS. Kết quả logic cần giống nhau; operation có thể khác. Đừng chỉ so Cost: hãy xem actual rows, buffers và thời gian trên cùng môi trường.

### 15.7. Tìm sinh viên chưa đăng ký course 5

~~~sql
SELECT s.student_id
FROM lab_students s
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_student_courses sc
    WHERE sc.student_id = s.student_id
      AND sc.course_id = 5
);
~~~

Primary key (student_id, course_id) hỗ trợ lookup theo cả hai cột.

### 15.8. Tìm course chưa có enrollment

~~~sql
SELECT c.course_id,
       c.course_code
FROM lab_courses c
WHERE NOT EXISTS (
    SELECT 1
    FROM lab_student_courses sc
    WHERE sc.course_id = c.course_id
);
~~~

Truy vấn bắt đầu từ COURSE_ID, nên index LAB_SC_COURSE_STUDENT_IX hỗ trợ chiều truy cập này.

### 15.9. Thử NOT IN và NULL

~~~sql
SELECT 1
FROM dual
WHERE 10 NOT IN (20, NULL);
~~~

Kết quả không có row. So sánh với:

~~~sql
SELECT 1
FROM dual
WHERE NOT EXISTS (
    SELECT 1
    FROM dual
    WHERE 20 = 10
       OR CAST(NULL AS NUMBER) = 10
);
~~~

NOT EXISTS kiểm tra có row nào thỏa predicate equality hay không. Subquery trên không có row match, nên NOT EXISTS là TRUE.

### 15.10. Dọn lab

~~~sql
DROP TABLE lab_student_courses PURGE;
DROP TABLE lab_courses PURGE;
DROP TABLE lab_students PURGE;
~~~

Chỉ chạy khi đã hoàn thành lab và không cần giữ dữ liệu.

## 16. Quy trình tối ưu EXISTS/NOT EXISTS trong dự án

Khi một query M:N chậm, làm theo trình tự:

1. Xác định câu hỏi nghiệp vụ là existence, non-existence, liệt kê quan hệ hay đếm quan hệ.
2. Viết SQL theo semantics: EXISTS, NOT EXISTS, JOIN hoặc GROUP BY/HAVING tương ứng.
3. Xác định khóa và cardinality của bảng liên kết.
4. Kiểm tra primary key/unique constraint để tránh duplicate relationship.
5. Kiểm tra index theo cả hai hướng của quan hệ M:N.
6. Kiểm tra predicate status/term/tenant có nằm trong index cần thiết không.
7. Thu thập statistics phù hợp.
8. Lấy actual cursor plan bằng DBMS_XPLAN.DISPLAY_CURSOR.
9. Xác định semijoin/antijoin, nested loops/hash/merge hoặc FILTER.
10. So E-Rows với A-Rows, Starts, Buffers và thời gian.
11. Kiểm tra NULL semantics, datatype conversion và predicate placement.
12. Thử thay đổi index/query có kiểm soát và đo lại với nhiều bind values.
13. Kiểm thử concurrency nếu query tồn tại được dùng để quyết định INSERT quan hệ.
14. Ghi lại lý do thiết kế index và ảnh hưởng tới DML.

## 17. Checklist thiết kế và tuning

1. **Đang cần existence hay cần dữ liệu liên quan?** Existence dùng EXISTS; cần từng quan hệ dùng JOIN.
2. **Không tồn tại được định nghĩa ra sao?** Mọi quan hệ hay chỉ quan hệ ACTIVE/trong kỳ hiện tại?
3. **Subquery có correlation predicate đúng không?** Ghép theo khóa của outer row.
4. **Có nguy cơ duplicate không?** Dùng semijoin semantics nếu chỉ cần outer rows.
5. **Có NULL trong subquery của NOT IN không?** Ưu tiên NOT EXISTS khi có khả năng NULL.
6. **Outer key có thể NULL không?** Quy định rõ có giữ row đó hay không.
7. **Bảng liên kết có unique constraint không?** Bảo đảm không tạo quan hệ trùng.
8. **Có index theo chiều truy cập không?** Cân nhắc cả (A_ID, B_ID) và (B_ID, A_ID).
9. **Predicate status/term có được hỗ trợ không?** Đo trước khi thêm composite index.
10. **Statistics có cập nhật không?** Kiểm tra row count, NDV, histogram và skew.
11. **Subquery có được unnest không?** Đọc operation tree, không đoán từ cú pháp.
12. **Join method có hợp cardinality không?** Nested loops, hash hay merge semi/anti.
13. **Có FILTER với Starts lớn không?** Xem inner lookup và khả năng transformation.
14. **Có function/implicit conversion trên key không?** Dùng datatype bind đúng và predicate phù hợp index.
15. **LEFT JOIN IS NULL có đặt predicate đúng ON/WHERE không?** Chọn cột NOT NULL để kiểm tra.
16. **Có cần relational division không?** Double NOT EXISTS có thể biểu đạt “đủ tất cả”.
17. **Có race condition giữa kiểm tra và INSERT không?** Unique constraint là lớp bảo đảm cuối.
18. **Đã đo actual plan chưa?** So A-Rows, Starts, Buffers và thời gian với dữ liệu thực.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** EXISTS trả TRUE trong trường hợp nào?

**Câu 2.** NOT EXISTS trả TRUE trong trường hợp nào?

**Câu 3.** Vì sao SELECT 1 thường được dùng trong EXISTS?

**Câu 4.** Semijoin khác join thông thường ở cardinality đầu ra như thế nào?

**Câu 5.** Antijoin giải quyết loại câu hỏi nào?

**Câu 6.** Vì sao correlated subquery không đồng nghĩa luôn chạy lặp từng outer row?

**Câu 7.** Vì sao JOIN rồi DISTINCT có thể thừa khi chỉ cần kiểm tra tồn tại?

**Câu 8.** Vì sao NOT IN có thể trả kết quả rỗng khi subquery chứa NULL?

**Câu 9.** NOT EXISTS có bị NULL trong inner key làm UNKNOWN toàn bộ điều kiện không?

**Câu 10.** Index (student_id, course_id) hỗ trợ truy vấn nào tốt?

**Câu 11.** Vì sao có thể cần index (course_id, student_id)?

**Câu 12.** Oracle có tự tạo index cho foreign key không?

**Câu 13.** Khi nào nên dùng hai EXISTS riêng và khi nào nên đặt predicate trong cùng một EXISTS?

**Câu 14.** Double NOT EXISTS biểu đạt bài toán gì?

**Câu 15.** Vì sao LEFT JOIN IS NULL phải đặt điều kiện match trong ON?

**Câu 16.** Khi nào nested loops semi/anti có thể phù hợp?

**Câu 17.** Khi nào hash join semi/anti có thể phù hợp?

**Câu 18.** Vì sao không nên thêm hint trước khi đọc actual plan?

**Câu 19.** E-Rows, A-Rows và Starts giúp chẩn đoán điều gì?

**Câu 20.** Vì sao kiểm tra EXISTS rồi INSERT vẫn cần unique constraint?

<details>
<summary>Gợi ý đáp án</summary>

1. Khi subquery trả ít nhất một row.
2. Khi subquery trả không row nào.
3. Vì giá trị select list không quan trọng; SELECT 1 thể hiện rõ chỉ kiểm tra tồn tại.
4. Semijoin giữ outer row tối đa một lần dù inner có nhiều match; join có thể nhân bản theo số match.
5. Tìm outer row không có inner match.
6. Optimizer có thể unnest subquery thành semijoin/antijoin hoặc transformation khác.
7. JOIN tạo duplicate theo số quan hệ rồi DISTINCT mới loại; EXISTS biểu đạt existence trực tiếp.
8. Vì phép so sánh với NULL tạo UNKNOWN và WHERE không giữ UNKNOWN.
9. Không. Equality với NULL không tạo match; NOT EXISTS xét empty result của subquery.
10. Lookup các course của một student và kiểm tra quan hệ theo student.
11. Hỗ trợ lookup sinh viên theo course và truy vấn bắt đầu từ phía course.
12. Không. Cần tạo index tường minh nếu workload và locking/join yêu cầu.
13. Dùng hai EXISTS nếu hai quan hệ độc lập có thể thỏa riêng; dùng một EXISTS nếu điều kiện phải cùng một row liên kết.
14. Tìm outer row thỏa tất cả phần tử trong tập yêu cầu, tức relational division.
15. Để kiểm tra không có row nào thỏa toàn bộ join condition; đặt predicate ở WHERE có thể làm sai outer join.
16. Khi outer row source nhỏ và inner lookup có index hiệu quả.
17. Khi row source lớn và xử lý nhiều row khiến hash strategy cạnh tranh hơn.
18. Vì hint có thể ép plan kém ổn định và che nguyên nhân gốc như statistics/cardinality.
19. Sai lệch ước tính, số lần operation chạy và khối lượng row thực tế.
20. Vì hai session có thể cùng thấy chưa tồn tại rồi cùng INSERT; unique constraint bảo vệ tính đúng đắn dưới concurrency.

</details>

## 19. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Tuning Guide — Joins](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/joins.html): join methods, semijoins, antijoins và cách optimizer xử lý joins.
2. [Oracle Database 19c SQL Tuning Guide — Subquery Unnesting](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/query-transformations.html): query transformations, subquery unnesting và predicate movement.
3. [Oracle Database 19c SQL Language Reference — EXISTS Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/EXISTS-Condition.html): semantics của EXISTS condition.
4. [Oracle Database 19c SQL Language Reference — IN Condition](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/IN-Condition.html): IN/NOT IN và semantics điều kiện.
5. [Oracle Database 19c SQL Tuning Guide — Optimizer Statistics](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-statistics-concepts.html): selectivity, cardinality và thống kê optimizer.
6. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_XPLAN](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_XPLAN.html): hiển thị execution plan và runtime statistics.
7. [Oracle Database 19c SQL Language Reference — CREATE INDEX](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html): tạo B-tree và function-based index.
8. [Oracle Database 19c SQL Language Reference — Constraints](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html): primary key, unique key và foreign key constraints.

**Nguyên tắc cần nhớ:** Dùng EXISTS khi câu hỏi là “có ít nhất một quan hệ phù hợp không?” và NOT EXISTS khi câu hỏi là “không có quan hệ phù hợp nào?”. Chúng biểu đạt semijoin/antijoin và tránh nhân bản outer row. Với quan hệ nhiều-nhiều, bảng liên kết cần khóa và index theo các chiều truy cập thực tế. Đặc biệt chú ý NULL của NOT IN, vị trí predicate trong outer join, điều kiện phải cùng nằm trên một row liên kết, statistics và actual execution plan. Tối ưu đúng bắt đầu từ semantics nghiệp vụ, sau đó mới đến index và join method.
