# Bảng dữ kiện không có số đo để mô tả sự tham gia hoặc sự xuất hiện

**Bảng dữ kiện không có số đo (factless fact table)** là một loại **fact table** trong mô hình dữ liệu phân tích, trong đó **bản thân sự tồn tại của một hàng là sự thật cần ghi nhận**. Bảng có các khóa nối tới dimension và có thể có ngày, mã sự kiện hoặc thuộc tính phục vụ truy vết, nhưng **không cần một cột số đo cộng dồn như doanh thu, số lượng hay chi phí**. Giá trị phân tích đến từ việc **đếm hàng** và, quan trọng hơn, so sánh **những gì được kỳ vọng/có thể xảy ra** với **những gì thực sự được ghi nhận**.

Ví dụ, một bản ghi **(học viên, buổi học)** có thể nói “học viên đã tham gia buổi học này”, chứ không cần ghi thêm **attendance_count = 1**. Một bảng khác ghi “học viên có tên trong danh sách dự kiến của buổi học”. Phân tích sự khác biệt giữa hai bảng giúp biết ai **chưa được ghi nhận tham gia** và tỷ lệ tham gia theo khóa học, buổi học hoặc nhóm đối tượng.

Bài thuộc chương **Bảng dữ kiện** của mô-đun **DATABASE_DATA_MODELING**. Trọng tâm là lựa chọn đúng *grain* (một hàng biểu diễn điều gì), thiết kế dimension và ràng buộc, tính tỷ lệ với mẫu số hợp lệ, tránh nhân hàng khi JOIN, và duy trì ý nghĩa lịch sử khi dữ liệu thay đổi.

## 1. Vì sao một fact table có thể không có số đo?

Một fact table điển hình lưu những sự kiện có số lượng:

~~~text
fact_order_line(
    order_key,
    product_key,
    customer_key,
    date_key,
    quantity,
    sales_amount_vnd
)
~~~

Mỗi hàng là một **dòng bán hàng**, với những số đo có thể tính tổng theo quy tắc phù hợp. Nhưng nhiều câu hỏi không yêu cầu một số tiền hoặc số lượng gốc:

- Ai đã **tham dự** buổi đào tạo nào?
- Khách hàng đã **đến cửa hàng** trong ngày nào?
- Nhân viên đã **được phân công** tham gia dự án nào?
- Sản phẩm nào **được niêm yết** trong chương trình khuyến mại nào?
- Bệnh nhân nào đã **đến lịch hẹn**?
- Những tài khoản nào **được phép nhận** một chiến dịch và tài khoản nào đã phản hồi?

Sự thật chính ở đây là **quan hệ hoặc sự xuất hiện**. Với một grain đã xác định, **có hàng** thường mang nghĩa “có sự kiện/có quan hệ”; **không có hàng** chưa chắc mang nghĩa “không xảy ra”, vì còn có khả năng dữ liệu chưa được nạp, nằm ngoài phạm vi, bị trễ hoặc bị hủy.

### 1.1. Phân biệt measure gốc và measure suy diễn

Một bảng không có cột measure vẫn có thể tạo ra số đo phân tích:

~~~sql
SELECT COUNT(*) AS recorded_participations
FROM fact_attendance;
~~~

**COUNT(*)** là số đo **suy diễn từ số bản ghi**. Không phải cứ viết được COUNT(*) thì bảng trở thành fact table có số đo lưu sẵn. Ngược lại, nếu mỗi hàng là một lần quét thẻ và một người quét ba lần, **COUNT(*) = 3 lần quét**, không phải **3 người tham gia**. Ý nghĩa phép đếm phụ thuộc vào grain.

### 1.2. Factless khác bảng dimension hay bảng nối thông thường thế nào?

| Loại cấu trúc | Grain ví dụ | Mục đích chính |
| --- | --- | --- |
| **Dimension** | Một học viên hoặc một phiên bản lịch sử của học viên | Mô tả thuộc tính dùng để lọc/nhóm như khoa, nhóm, địa điểm |
| **Fact có số đo** | Một dòng đơn hàng | Ghi số lượng, số tiền, thời lượng... |
| **Factless fact sự kiện** | Một học viên thực sự tham dự một buổi | Ghi nhận **sự xuất hiện/tham gia** |
| **Factless fact phạm vi** | Một học viên được kỳ vọng/có quyền tham dự một buổi | Ghi nhận **tập cơ hội hay điều kiện đủ** |
| **Bảng nối OLTP** | Một học viên đăng ký một khóa học | Thực thi quan hệ và ràng buộc giao dịch; có thể là **nguồn** cho fact phân tích |

Một bảng giao dịch hai khóa ngoại **không tự động** là factless fact table. Trong kho phân tích, ta phải xác định **grain, chiều thời gian, mục đích đo lường, quy tắc tải và lịch sử**. Bảng giống nhau về cột nhưng có thể phục vụ những mục đích rất khác nhau.

## 2. Hai kiểu factless fact quan trọng

### 2.1. Event/participation fact: sự kiện đã xảy ra

**Event factless fact** ghi nhận một sự kiện hoặc sự tham gia:

~~~text
fact_attendance(
    student_key,
    session_key
)
~~~

Một hàng nghĩa là “học viên được ghi nhận **đã tham gia** buổi học đó”, với giả định sau khi xử lý nguồn chỉ lưu **một bản ghi xác nhận tham gia cho mỗi cặp**. Bảng có thể hỗ trợ:

- Đếm lượt tham gia theo buổi hoặc theo khóa học.
- Đếm số học viên duy nhất đã tham gia ít nhất một buổi.
- Xem lịch sử buổi học của một học viên.
- Kiểm tra sự tham gia trong một chuỗi hoạt động.

Nếu mục tiêu là ghi **mọi lần quét thẻ**, grain phải là **một sự kiện quét** và cần **scan_event_id** (hoặc khóa sự kiện nguồn), thời gian quét, loại sự kiện; khi ấy không thể dùng cặp student–session làm khóa duy nhất.

### 2.2. Coverage/eligibility fact: điều kiện hoặc cơ hội tồn tại

**Coverage factless fact** mô tả tập mà sự kiện **được kỳ vọng, được phép hoặc có thể xảy ra** theo quy tắc nghiệp vụ:

~~~text
fact_expected_attendance(
    student_key,
    session_key
)
~~~

Một hàng nghĩa là “học viên nằm trong **danh sách dự kiến** của buổi học”. Đây **không phải** bản ghi xác nhận có mặt.

Coverage cho biết **mẫu số (denominator)**:

- Bao nhiêu lượt học viên–buổi học được dự kiến?
- Trong các lượt dự kiến, bao nhiêu lượt đã tham gia?
- Những lượt dự kiến nào **chưa có bản ghi tham gia**?
- Có bản ghi tham gia nào **nằm ngoài danh sách dự kiến** không?

Nếu chỉ có bảng sự kiện, không thể phân biệt một người **không tham gia** với người **không nằm trong danh sách**.

### 2.3. “Event” và “coverage” không phải nhãn thay thế cho nhau

| Câu hỏi | Event fact | Coverage fact |
| --- | --- | --- |
| Có ghi nhận học viên đã đến không? | **Có** | Không |
| Học viên có thuộc danh sách kỳ vọng không? | Không đủ | **Có** |
| Tính số lượt đã ghi nhận | Đếm hàng đúng grain | Không thay thế được |
| Tính tỷ lệ tham gia trong nhóm dự kiến | Cần kết hợp với coverage | Cung cấp mẫu số |
| Xác định người không có sự kiện | Không xác định được tập đối tượng cần xét | Là tập gốc để đối chiếu event |

**Lưu ý ngữ nghĩa:** “được phép”, “được mời”, “đã đăng ký”, “được phân công” và “bắt buộc có mặt” là các quy tắc **khác nhau**. Khi tạo coverage, phải chọn **một** định nghĩa và nêu rõ thời điểm hiệu lực. Không nên dùng tên chung **fact_coverage** rồi mặc nhiên hiểu tất cả người trong đó đều phải tham gia.

## 3. Ví dụ xuyên suốt: lịch dự kiến và tham dự đào tạo

Một trung tâm tổ chức các buổi học. Yêu cầu nghiệp vụ trong ví dụ:

1. Mỗi học viên có mã định danh nghiệp vụ **student_code**.
2. Mỗi buổi học có **session_code**, thuộc một khóa học và có ngày tổ chức.
3. Một học viên có thể nằm trong danh sách dự kiến của nhiều buổi; một buổi có nhiều học viên dự kiến.
4. **Coverage** được chốt trước khi buổi học diễn ra: một hàng cho mỗi cặp **học viên–buổi** thuộc danh sách dự kiến.
5. **Attendance** được xác nhận sau khi nhận dữ liệu điểm danh: **mỗi cặp học viên–buổi chỉ được đếm là một lượt tham gia**, dù nguồn có nhiều lần quét thẻ.
6. Học viên có thể đến ngoài danh sách. Việc ấy được giữ lại trong dữ liệu event để kiểm tra, nhưng **không tự động đưa vào tỷ lệ của tập dự kiến**.
7. Chưa tính trường hợp hủy buổi, chuyển buổi, miễn tham dự, hoặc điểm danh đến trễ. Nếu có, cần bổ sung chính sách và định nghĩa lại phạm vi đo.

### 3.1. Dữ liệu minh họa

**Dimension học viên:**

| student_key | student_code | student_name |
| ---: | --- | --- |
| 1 | S01 | An |
| 2 | S02 | Bình |
| 3 | S03 | Chi |
| 4 | S04 | Dũng |

**Dimension buổi học:**

| session_key | session_code | course_code | session_date |
| ---: | --- | --- | --- |
| 101 | T101 | C10 | 2026-11-19 |
| 102 | T102 | C10 | 2026-11-20 |
| 201 | T201 | C20 | 2026-11-21 |

**Danh sách dự kiến (coverage):**

| student_key | session_key |
| ---: | ---: |
| 1 | 101 |
| 2 | 101 |
| 1 | 102 |
| 2 | 102 |
| 3 | 201 |

**Tham dự đã ghi nhận (event):**

| student_key | session_key |
| ---: | ---: |
| 1 | 101 |
| 2 | 101 |
| 1 | 102 |
| 3 | 201 |

Có **5 lượt dự kiến**, **4 lượt đã ghi nhận**, và cặp **(S02, T102)** chưa có sự kiện tham gia. Học viên **S04** không có hàng ở cả hai fact: **không được tự kết luận S04 vắng mặt**, vì S04 không thuộc danh sách dự kiến trong ví dụ.

### 3.2. Grain là quyết định quan trọng nhất

| Bảng | Một hàng biểu diễn | Khóa tự nhiên tại grain |
| --- | --- | --- |
| **dim_student** | Một học viên theo phạm vi mô hình đơn giản hiện tại | student_code |
| **dim_training_session** | Một buổi học được xác định | session_code |
| **fact_expected_attendance** | Một lượt dự kiến của học viên trong buổi | (student_key, session_key) |
| **fact_attendance** | Một lượt tham gia đã được xác nhận của học viên trong buổi | (student_key, session_key) |

**Grain** cần được chốt **trước** khi chọn khóa chính, JOIN hoặc metric. Trong ví dụ này, cùng một học viên tham dự hai buổi là **hai lượt**, không phải một người duy nhất. Do đó:

~~~text
COUNT(*) trên fact_attendance                    = 4 lượt tham gia
COUNT(DISTINCT student_key) trên fact_attendance  = 3 học viên khác nhau
~~~

Không có phép đếm nào “đúng hơn” nếu chưa biết câu hỏi là **lượt tham gia** hay **số học viên duy nhất**.

### 3.3. Sơ đồ star schema với hai factless fact

~~~mermaid
erDiagram
    DIM_STUDENT ||--o{ FACT_EXPECTED_ATTENDANCE : "được dự kiến"
    DIM_TRAINING_SESSION ||--o{ FACT_EXPECTED_ATTENDANCE : "danh sách buổi"
    DIM_STUDENT ||--o{ FACT_ATTENDANCE : "đã tham gia"
    DIM_TRAINING_SESSION ||--o{ FACT_ATTENDANCE : "được ghi nhận"
    DIM_STUDENT {
        bigint student_key PK
        varchar student_code UK
        varchar student_name
    }
    DIM_TRAINING_SESSION {
        bigint session_key PK
        varchar session_code UK
        varchar course_code
        date session_date
    }
    FACT_EXPECTED_ATTENDANCE {
        bigint student_key PK, FK
        bigint session_key PK, FK
    }
    FACT_ATTENDANCE {
        bigint student_key PK, FK
        bigint session_key PK, FK
    }
~~~

Hai fact sử dụng **dimension chung (conformed dimensions)** với cùng ý nghĩa khóa, giúp so sánh đúng cùng học viên và cùng buổi học. Trong mô hình phân tích lớn hơn, ngày học có thể tham chiếu **dim_date**, khóa học có thể có **dim_course**, và học viên có thể có dimension lịch sử; các mở rộng đó không làm thay đổi grain cơ bản của hai fact trong ví dụ.

## 4. Thiết kế SQL: lưu sự hiện diện của hàng thay vì cột số đo

Ví dụ sau dùng **PostgreSQL** và một schema minh họa đơn giản. Nó sử dụng khóa số làm dimension key để tập trung vào ý nghĩa grain, không ngụ ý mọi hệ thống phải có cấu trúc khóa y hệt.

### 4.1. Tạo dimension và hai fact

~~~sql
CREATE TABLE dim_student (
    student_key BIGINT PRIMARY KEY,
    student_code VARCHAR(20) NOT NULL UNIQUE,
    student_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_training_session (
    session_key BIGINT PRIMARY KEY,
    session_code VARCHAR(20) NOT NULL UNIQUE,
    course_code VARCHAR(20) NOT NULL,
    session_date DATE NOT NULL
);

-- Coverage: một lượt học viên được dự kiến trong buổi.
CREATE TABLE fact_expected_attendance (
    student_key BIGINT NOT NULL
        REFERENCES dim_student(student_key),
    session_key BIGINT NOT NULL
        REFERENCES dim_training_session(session_key),
    PRIMARY KEY (student_key, session_key)
);

-- Event: một lượt tham gia được ghi nhận trong buổi.
CREATE TABLE fact_attendance (
    student_key BIGINT NOT NULL
        REFERENCES dim_student(student_key),
    session_key BIGINT NOT NULL
        REFERENCES dim_training_session(session_key),
    PRIMARY KEY (student_key, session_key)
);
~~~

Trong hai fact, **không có cột attendance_count, eligible_count hoặc amount**. Mỗi hàng ghi nhận một sự thật đúng grain:

- **PRIMARY KEY (student_key, session_key)** ngăn lặp một cặp trong từng fact.
- **FOREIGN KEY** xác nhận các dimension được tham chiếu tồn tại.
- Không đặt **FOREIGN KEY fact_attendance → fact_expected_attendance** trong ví dụ, vì cần **nhìn thấy những lượt tham gia ngoài danh sách** để kiểm tra; nếu nghiệp vụ nghiêm cấm các trường hợp này, ràng buộc và luồng ghi cần thiết kế khác.
- Hai fact **không có quan hệ cha–con**; chúng là hai tập sự thật cần đối chiếu.

### 4.2. Nạp dữ liệu mẫu

~~~sql
INSERT INTO dim_student
    (student_key, student_code, student_name)
VALUES
    (1, 'S01', 'An'),
    (2, 'S02', 'Bình'),
    (3, 'S03', 'Chi'),
    (4, 'S04', 'Dũng');

INSERT INTO dim_training_session
    (session_key, session_code, course_code, session_date)
VALUES
    (101, 'T101', 'C10', DATE '2026-11-19'),
    (102, 'T102', 'C10', DATE '2026-11-20'),
    (201, 'T201', 'C20', DATE '2026-11-21');

INSERT INTO fact_expected_attendance
    (student_key, session_key)
VALUES
    (1, 101),
    (2, 101),
    (1, 102),
    (2, 102),
    (3, 201);

INSERT INTO fact_attendance
    (student_key, session_key)
VALUES
    (1, 101),
    (2, 101),
    (1, 102),
    (3, 201);
~~~

Các truy vấn ở các mục tiếp theo dùng dữ liệu này, giả sử chưa có thay đổi hay bổ sung sự kiện.

## 5. Đếm sự tham gia, đếm người và tính tỷ lệ

### 5.1. Đếm hàng đúng grain

~~~sql
SELECT COUNT(*) AS expected_participations
FROM fact_expected_attendance;
-- 5

SELECT COUNT(*) AS recorded_participations
FROM fact_attendance;
-- 4

SELECT COUNT(DISTINCT student_key) AS distinct_attendees
FROM fact_attendance;
-- 3
~~~

Ba con số trả lời **ba câu hỏi khác nhau**. Có 5 **lượt dự kiến**, 4 **lượt được ghi nhận tham gia** và 3 **học viên khác nhau** đã có ít nhất một lượt tham gia.

**Không** lấy 4 trừ 3 để suy số người vắng mặt. Một học viên có thể tham gia nhiều buổi, còn số người dự kiến duy nhất có thể khác số lượt dự kiến.

### 5.2. Xác định người chưa có bản ghi tham gia: LEFT JOIN

Tập cần xét xuất phát từ **coverage**:

~~~sql
SELECT
    st.student_code,
    st.student_name,
    ts.session_code,
    ts.course_code,
    ts.session_date
FROM fact_expected_attendance AS expected
JOIN dim_student AS st
  ON st.student_key = expected.student_key
JOIN dim_training_session AS ts
  ON ts.session_key = expected.session_key
LEFT JOIN fact_attendance AS attended
  ON attended.student_key = expected.student_key
 AND attended.session_key = expected.session_key
WHERE attended.student_key IS NULL
ORDER BY ts.session_date, st.student_code;
~~~

Kết quả duy nhất của mẫu:

| student_code | session_code | course_code | session_date |
| --- | --- | --- | --- |
| S02 | T102 | C10 | 2026-11-20 |

Đây là **lượt chưa có dữ kiện tham gia**. Chỉ sau khi xác nhận nguồn điểm danh đã nạp đủ, buổi đã kết thúc và chính sách điểm danh được áp dụng, doanh nghiệp mới có thể kết luận người này “vắng mặt” theo định nghĩa chính thức.

Nếu sau này fact_attendance nhận bản ghi điểm danh đến muộn, truy vấn trên tự thay đổi kết quả. Nếu báo cáo cần giữ trạng thái “vắng mặt **theo dữ liệu biết được vào 20:00 ngày 20/11**”, mô hình còn phải quản lý **thời điểm nạp và ảnh chụp báo cáo**.

### 5.3. Biểu diễn tương đương bằng NOT EXISTS

~~~sql
SELECT
    expected.student_key,
    expected.session_key
FROM fact_expected_attendance AS expected
WHERE NOT EXISTS (
    SELECT 1
    FROM fact_attendance AS attended
    WHERE attended.student_key = expected.student_key
      AND attended.session_key = expected.session_key
);
~~~

**NOT EXISTS** biểu diễn rõ phép trừ tập **coverage \ event** và tránh vô tình nhân kết quả do JOIN với nguồn có nhiều bản ghi quét thẻ. Khi bảng event đã được bảo vệ khóa ghép, cả hai cách đều hợp lệ. Chọn cách đọc được, đúng ngữ nghĩa và đo kế hoạch truy vấn trên dữ liệu thật.

### 5.4. Tỷ lệ tham gia phải có mẫu số rõ

Đặt:

~~~text
C = tập các cặp (student_key, session_key) được dự kiến
E = tập các cặp đã có sự kiện tham gia

Tập tham gia trong phạm vi dự kiến: C ∩ E
Tập chưa có sự kiện trong phạm vi dự kiến: C − E
Tập sự kiện ngoài danh sách: E − C

Tỷ lệ tham gia trong danh sách dự kiến =
    |C ∩ E| / |C| × 100%
~~~

Khi **|C| = 0**, tỷ lệ **không được xác định theo công thức này**, chứ không mặc định bằng 0%. Cần quy tắc báo cáo cho tình huống không có mẫu số.

Truy vấn PostgreSQL:

~~~sql
SELECT
    ts.course_code,
    COUNT(*) AS expected_participations,
    COUNT(attended.student_key) AS attended_in_coverage,
    ROUND(
        100.0 * COUNT(attended.student_key)
        / NULLIF(COUNT(*), 0),
        2
    ) AS attendance_rate_pct
FROM fact_expected_attendance AS expected
JOIN dim_training_session AS ts
  ON ts.session_key = expected.session_key
LEFT JOIN fact_attendance AS attended
  ON attended.student_key = expected.student_key
 AND attended.session_key = expected.session_key
GROUP BY ts.course_code
ORDER BY ts.course_code;
~~~

Kết quả:

| course_code | expected_participations | attended_in_coverage | attendance_rate_pct |
| --- | ---: | ---: | ---: |
| C10 | 4 | 3 | 75.00 |
| C20 | 1 | 1 | 100.00 |

Toàn bộ mẫu có **4/5 = 80%** lượt dự kiến đã được ghi nhận tham gia.

Ở đây **COUNT(*)** đúng cho mẫu số vì truy vấn bắt đầu từ các **hàng coverage** và chỉ nối với **dimension có khóa duy nhất**, còn **fact_attendance** cũng có khóa duy nhất theo cùng cặp. **COUNT(attended.student_key)** đếm các hàng event khớp, bỏ qua NULL của LEFT JOIN.

Nếu thay **COUNT(attended.student_key)** bằng **COUNT(*)**, mỗi hàng dự kiến không có event vẫn được đếm một lần và tỷ lệ có thể bị nâng lên **100% giả**.

### 5.5. Muốn hiển thị buổi học chưa có ai dự kiến?

Truy vấn ở trên nhóm từ coverage nên **không hiển thị các buổi hoàn toàn chưa có danh sách dự kiến**. Nếu cần báo cáo mọi buổi (kể cả mẫu số bằng 0), hãy bắt đầu từ **dimension buổi**:

~~~sql
SELECT
    ts.session_code,
    COUNT(expected.student_key) AS expected_count,
    COUNT(attended.student_key) AS attended_in_coverage,
    ROUND(
        100.0 * COUNT(attended.student_key)
        / NULLIF(COUNT(expected.student_key), 0),
        2
    ) AS attendance_rate_pct
FROM dim_training_session AS ts
LEFT JOIN fact_expected_attendance AS expected
  ON expected.session_key = ts.session_key
LEFT JOIN fact_attendance AS attended
  ON attended.student_key = expected.student_key
 AND attended.session_key = expected.session_key
GROUP BY ts.session_code
ORDER BY ts.session_code;
~~~

Với một buổi không có coverage: **expected_count = 0**, **attended_in_coverage = 0**, **attendance_rate_pct = NULL**. Đây là kết quả có chủ đích: không có cơ sở tính tỷ lệ. Muốn báo cáo buổi hủy hoặc buổi chưa đến ngày, phải lọc theo trạng thái/thời gian mà dimension hoặc hệ nguồn cung cấp.

## 6. Ghi nhận sự tham gia ngoài phạm vi dự kiến

Một factless fact sự kiện có thể có những hàng không nằm trong coverage, chẳng hạn học viên đến học thử, điểm danh nhầm lớp, hoặc danh sách dự kiến chưa đồng bộ.

Phép trừ tập **event \ coverage** giúp kiểm tra:

~~~sql
SELECT
    st.student_code,
    ts.session_code
FROM fact_attendance AS attended
JOIN dim_student AS st
  ON st.student_key = attended.student_key
JOIN dim_training_session AS ts
  ON ts.session_key = attended.session_key
LEFT JOIN fact_expected_attendance AS expected
  ON expected.student_key = attended.student_key
 AND expected.session_key = attended.session_key
WHERE expected.student_key IS NULL
ORDER BY ts.session_code, st.student_code;
~~~

Trên dữ liệu mẫu ban đầu, truy vấn không có kết quả. Có thể thử một ca ngoài danh sách rồi hoàn tác:

~~~sql
BEGIN;

INSERT INTO fact_attendance (student_key, session_key)
VALUES (4, 101); -- S04 tham dự T101 nhưng không có trong coverage

-- Chạy lại truy vấn kiểm tra event ngoài danh sách ở trên.
-- Kết quả sẽ có (S04, T101).

ROLLBACK;
~~~

Hàng này **không nên tự động làm tăng tử số** của tỷ lệ “tham gia trong tập dự kiến” nếu mẫu số vẫn là tập cũ. Nếu nghiệp vụ cho phép khách mời, có thể báo cáo riêng **số lượt đến ngoài danh sách**; nếu nghiệp vụ cấm, cần quy trình điều tra/sửa dữ liệu. Việc tự động bổ sung mọi event vào coverage có thể che mất sai lệch đầu vào và làm biến dạng mẫu số.

### 6.1. Phân biệt các chỉ số gần giống nhau

| Chỉ số | Công thức theo tập | Ý nghĩa |
| --- | --- | --- |
| **Số lượt dự kiến** | \(|C|\) | Cơ hội hoặc nghĩa vụ tham gia |
| **Số lượt đã ghi nhận** | \(|E|\) | Event trong toàn phạm vi dữ liệu |
| **Số lượt tham gia thuộc danh sách** | \(|C \cap E|\) | Tử số của tỷ lệ trong tập dự kiến |
| **Số lượt chưa ghi nhận** | \(|C - E|\) | Thiếu sự kiện so với danh sách |
| **Số lượt ngoài danh sách** | \(|E - C|\) | Dữ kiện ngoài phạm vi kỳ vọng |
| **Số học viên đã tham gia ít nhất một buổi** | \(|\pi_{student}(E)|\) | Số người duy nhất, không phải lượt |

Nếu một báo cáo chỉ có tên **attendance_count** mà không nêu grain và tập gốc, người đọc có thể nhầm số lượt, số người hoặc số lần quét thẻ.

## 7. Những phép JOIN dễ làm sai số liệu

### 7.1. CROSS JOIN toàn bộ dimension không phải coverage

Từ bốn học viên và ba buổi học trong ví dụ:

~~~sql
SELECT COUNT(*) AS possible_pairs
FROM dim_student AS st
CROSS JOIN dim_training_session AS ts;
-- 4 × 3 = 12
~~~

Kết quả 12 chỉ là **mọi tổ hợp có thể tạo về mặt toán học**, **không** phải 12 lượt dự kiến. Coverage có **5** lượt theo danh sách nghiệp vụ. Nếu tùy tiện coi 12 tổ hợp là mẫu số, ta sẽ kết luận hàng loạt lượt “vắng mặt” chưa từng được kỳ vọng.

**Chỉ dùng CROSS JOIN** làm cơ sở tạo coverage nếu quy tắc đã được xác nhận: **mọi đối tượng trong tập A đều đủ điều kiện với mọi phần tử trong tập B**, và đã áp dụng đúng phạm vi, thời gian, ngoại lệ. Ví dụ mọi nhân viên toàn thời gian ở một chi nhánh phải tham gia mọi buổi an toàn bắt buộc của chi nhánh trong kỳ — với điều kiện loại trừ nghỉ việc, miễn học, hủy buổi được xử lý.

### 7.2. Nối qua dimension nhiều phiên bản có thể nhân hàng

Giả sử một học viên được lưu trong dimension lịch sử hai phiên bản:

~~~text
student_code = S01, version 1, department = A
student_code = S01, version 2, department = B
~~~

Nếu JOIN fact qua **student_code** với cả hai phiên bản, một lượt tham gia có thể bị nhân thành **hai dòng kết quả**. Cách đúng phải xác định phiên bản dimension nào có hiệu lực theo thời điểm fact, và dùng **surrogate dimension key** hoặc điều kiện khoảng hiệu lực thích hợp.

Trong ví dụ SQL cơ bản, **student_key** là khóa duy nhất ở dim_student nên không có nguy cơ này. Khi chuyển sang **Slowly Changing Dimension (SCD) Type 2**, điều kiện và mapping as-of phải được thiết kế lại; không chỉ thêm các phiên bản mới rồi giữ nguyên ràng buộc **UNIQUE(student_code)**.

### 7.3. Nối trực tiếp hai fact qua mỗi session_key có thể nhân lượt

**Sai:** nối fact_expected_attendance và fact_attendance **chỉ theo session_key**:

~~~sql
-- Minh họa phản mẫu; KHÔNG dùng để tính số lượt.
SELECT
    e.session_key,
    COUNT(*) AS joined_rows
FROM fact_expected_attendance AS e
JOIN fact_attendance AS a
  ON a.session_key = e.session_key
GROUP BY e.session_key;
~~~

Ở buổi T101 có **2 lượt dự kiến** và **2 lượt tham gia**, phép nối chỉ theo session_key tạo **2 × 2 = 4 dòng**, dù chỉ có 2 cặp đúng nhau.

**Đúng:** nối theo **toàn bộ grain (student_key, session_key)** khi so sánh hai fact. Khi fact có nhiều dimension hơn — ví dụ buổi, học viên, nhóm tham dự và lần tổ chức — phải xét đầy đủ khóa ngữ nghĩa, không chỉ một phần khóa trông “giống nhau”.

### 7.4. Tránh dựa vào COUNT(DISTINCT) để che lỗi grain

**COUNT(DISTINCT student_key)** có ích khi hỏi **số học viên duy nhất**, nhưng không phải cách sửa mặc định cho mọi phép JOIN bị nhân hàng. Nếu một người dự kiến 10 buổi, dùng DISTINCT theo student_key sẽ làm 10 lượt thành 1 và phá số liệu tham gia.

Biện pháp đầu tiên là **xác định lại grain và quan hệ JOIN**, sau đó chọn COUNT(*), COUNT(column), COUNT(DISTINCT ...) theo đúng câu hỏi.

## 8. Nạp dữ liệu, khử trùng và bảo vệ ngữ nghĩa sự kiện

### 8.1. Một lần quét thẻ chưa chắc là một lượt tham gia

Nguồn hệ thống điểm danh có thể phát ra:

~~~text
event_001: S01 quét thẻ vào buổi T101 lúc 08:00
event_002: S01 quét lại thẻ ở buổi T101 lúc 08:05
event_003: S02 quét thẻ vào buổi T101 lúc 08:01
event_004: S01 quét thẻ vào buổi T102 lúc 09:00
event_005: S03 quét thẻ vào buổi T201 lúc 14:00
~~~

Có **5 bản ghi quét** nhưng chỉ **4 cặp học viên–buổi khác nhau**. Nếu định nghĩa fact_attendance là **một lượt tham gia đã xác nhận**, phải khử trùng và áp dụng quy tắc nguồn trước khi tải. Nếu muốn phân tích số lần quét, cần **một fact sự kiện khác** với grain từng lần quét.

Một staging table có thể giữ sự kiện nguồn nguyên vẹn:

~~~sql
CREATE TABLE staging_attendance_scan (
    source_event_id VARCHAR(30) PRIMARY KEY,
    student_code VARCHAR(20) NOT NULL,
    session_code VARCHAR(20) NOT NULL,
    scanned_at TIMESTAMPTZ NOT NULL
);

INSERT INTO staging_attendance_scan
    (source_event_id, student_code, session_code, scanned_at)
VALUES
    ('event_001', 'S01', 'T101', TIMESTAMPTZ '2026-11-19 08:00:00+07'),
    ('event_002', 'S01', 'T101', TIMESTAMPTZ '2026-11-19 08:05:00+07'),
    ('event_003', 'S02', 'T101', TIMESTAMPTZ '2026-11-19 08:01:00+07'),
    ('event_004', 'S01', 'T102', TIMESTAMPTZ '2026-11-20 09:00:00+07'),
    ('event_005', 'S03', 'T201', TIMESTAMPTZ '2026-11-21 14:00:00+07');
~~~

Sau khi nghiệp vụ xác nhận các lần quét này là bằng chứng tham dự hợp lệ, tải fact:

~~~sql
INSERT INTO fact_attendance (student_key, session_key)
SELECT DISTINCT
    st.student_key,
    ts.session_key
FROM staging_attendance_scan AS scan
JOIN dim_student AS st
  ON st.student_code = scan.student_code
JOIN dim_training_session AS ts
  ON ts.session_code = scan.session_code
ON CONFLICT (student_key, session_key) DO NOTHING;
~~~

Đoạn SQL sử dụng **DISTINCT** để chuyển từ grain **lần quét** sang grain **lượt tham gia**, còn **ON CONFLICT DO NOTHING** giúp nạp lặp không tự tạo thêm hàng theo khóa ghép. Với dữ liệu mẫu đã nạp ở mục 4, lệnh không tạo thêm lượt; tổng vẫn là 4.

Tuy nhiên, **nạp được không có nghĩa sự kiện hợp lệ**. Hệ thống thật cần kiểm tra thời gian cho phép điểm danh, người có quyền điểm danh, sự kiện hủy, hiệu chỉnh thủ công, thiết bị lỗi và quy tắc tham dự có mặt đủ thời lượng. **DISTINCT** không thay thế những quy tắc này.

### 8.2. Giữ sự kiện nguồn để kiểm tra, không làm mất thông tin

Nếu các lần quét có ý nghĩa kiểm toán hoặc điều tra, không nên xóa staging/raw events sau khi tạo factless fact. Tách:

~~~text
raw_scan_events:
    grain = một sự kiện nguồn (source_event_id)

fact_attendance:
    grain = một cặp học viên–buổi được công nhận có tham gia
~~~

Một lần sửa dữ liệu nguồn có thể khiến kết quả factless fact thay đổi. Cần chiến lược **rebuild/idempotent load**, theo dõi phiên bản quy tắc và nguồn gốc của hàng.

### 8.3. Mã nguồn chưa có trong dimension phải được xử lý

Ví dụ phát hiện scan có **student_code** chưa được ánh xạ:

~~~sql
SELECT scan.source_event_id, scan.student_code
FROM staging_attendance_scan AS scan
LEFT JOIN dim_student AS st
  ON st.student_code = scan.student_code
WHERE st.student_key IS NULL;
~~~

Nếu dimension còn thiếu, JOIN kiểu INNER ở bước nạp sẽ **âm thầm làm mất sự kiện chưa ghép được**. Với kho dữ liệu thực, cần cơ chế **quarantine**, **late-arriving dimension**, hoặc hàng placeholder/unknown theo chính sách; phải bảo đảm sau khi bổ sung dimension có thể đối soát và nạp lại.

Đừng tự ánh xạ mọi mã học viên không nhận diện về một student_key chung rồi dùng **COUNT(DISTINCT student_key)** để đếm người: nhiều người khác nhau sẽ bị gộp thành một. Cần xem lỗi ánh xạ là dữ liệu chất lượng kém và báo cáo rõ.

### 8.4. Coverage cũng cần nguồn và thời điểm chốt

Nguồn coverage có thể là danh sách đăng ký hoặc phân công theo từng buổi. Một việc rất quan trọng là **định nghĩa thời điểm đóng băng danh sách**:

- Danh sách chốt **trước giờ bắt đầu**?
- Danh sách mọi người có quyền tham gia **tại thời điểm kết thúc**?
- Danh sách bất kỳ ai **từng được mời**, kể cả người đã từ chối?
- Danh sách được đối soát **sau buổi** và đã sửa các trường hợp chuyển lớp?

Các lựa chọn có thể cho mẫu số khác nhau. Nếu muốn báo cáo tỷ lệ ở **thời điểm kỳ vọng ban đầu**, không nên âm thầm ghi đè coverage lịch sử theo danh sách đăng ký **hiện tại**.

## 9. Thời gian, Slowly Changing Dimensions và dữ liệu đến trễ

### 9.1. Sự kiện xảy ra khi nào, được ghi nhận khi nào?

Một lượt tham gia thực tế có thể xảy ra ngày 19/11 nhưng log được nạp vào kho ngày 21/11:

| Trường thời gian | Ví dụ | Câu hỏi |
| --- | --- | --- |
| **occurred_at** | 2026-11-19 08:00 +07 | Sự kiện thực tế diễn ra khi nào? |
| **ingested_at** | 2026-11-21 02:00 +07 | Kho dữ liệu biết về sự kiện từ khi nào? |
| **eligibility_as_of** | 2026-11-18 18:00 +07 | Coverage được chốt theo danh sách nào? |

Nếu phân tích “tỷ lệ tham gia của buổi ngày 19/11” sau khi đã hoàn tất đồng bộ, có thể dùng sự kiện theo **occurred_at**. Nếu phân tích “báo cáo được công bố sáng 20/11 đã biết những gì”, còn cần thời gian **ingested_at** hoặc snapshot lịch sử của báo cáo.

Một **factless event** có thể lưu thêm khóa ngày hoặc timestamp phục vụ truy vấn/kiểm toán. Nó vẫn là factless nếu **không có measure số lượng**; thời gian là thông tin ngữ cảnh của sự kiện, không phải số đo như doanh thu.

### 9.2. Coverage dạng ảnh chụp và coverage theo khoảng hiệu lực

Bảng **fact_expected_attendance(student_key, session_key)** ở ví dụ mô tả **một danh sách đã chốt cho buổi học**. Nếu nghiệp vụ yêu cầu biết danh sách dự kiến ở **nhiều thời điểm**, có hai chiến lược khác:

1. **Periodic coverage snapshot:** grain là **(snapshot_date_key, student_key, session_key)**, trong đó mỗi snapshot biểu diễn tập dự kiến tại ngày chụp; chỉ so sánh với event theo đúng snapshot đã chọn.
2. **Coverage theo khoảng hiệu lực:** một bản ghi quan hệ có **valid_from/valid_to** và quy tắc xử lý các khoảng; truy vấn lấy tập hiệu lực **as-of** thời điểm phân tích.

**Không được cộng COUNT(*) của mọi snapshot theo ngày rồi gọi là tổng số người dự kiến**. Một học viên có thể xuất hiện trong 10 snapshot cho cùng một buổi, nhưng chỉ là **một lượt dự kiến** của buổi ấy tại một thời điểm chốt.

### 9.3. Dimension lịch sử cần khóa theo đúng thời điểm

Nếu học viên chuyển khoa giữa hai học kỳ và báo cáo yêu cầu phân tích theo **khoa tại thời điểm tham gia**, dimension SCD Type 2 có thể biểu diễn:

~~~text
student_key | student_code | department | valid_from | valid_to
------------+--------------+------------+------------+----------
1001        | S01          | Khoa A     | ...        | ...
1002        | S01          | Khoa B     | ...        | ...
~~~

Khi nạp fact, ánh xạ **student_code và thời điểm sự kiện/coverage** sang đúng **student_key** lịch sử. Với hai fact cần đối chiếu ở **cùng grain nghiệp vụ**, phải thống nhất quy tắc phiên bản và không để một bên trỏ phiên bản cũ, bên kia trỏ phiên bản mới rồi mất kết quả JOIN.

Trong một hệ thống lớn, có thể cần **student identity key ổn định** để đối chiếu các sự kiện xuyên thời gian, đồng thời dùng **student SCD surrogate key** để phân tích thuộc tính lịch sử. Đây là quyết định mô hình hóa có chủ đích, không phải cứ thay bảng dimension hiện tại bằng SCD Type 2 là các phép nối đang có sẽ tự đúng.

### 9.4. Ngày, múi giờ và trạng thái buổi học

Một buổi học bắt đầu lúc 23:30 UTC có thể thuộc ngày lịch khác ở Việt Nam. Nếu report theo **ngày địa phương**, hãy xác định timezone cho **session_date** và các event. Nếu buổi bị hủy, hoãn hoặc chuyển lớp, coverage đã chốt có thể cần loại khỏi mẫu số hoặc xử lý như tình trạng riêng.

Quy tắc “chưa có event = vắng mặt” chỉ có ý nghĩa khi **buổi đã hoàn tất**, luồng dữ liệu liên quan đã được đồng bộ đủ và đối tượng thực sự thuộc **tập phải điểm danh**.

## 10. Các tình huống áp dụng khác

| Lĩnh vực | Event factless fact | Coverage factless fact | Câu hỏi phân tích |
| --- | --- | --- | --- |
| **Đào tạo** | Học viên có mặt tại buổi | Học viên dự kiến tham dự buổi | Ai chưa được ghi nhận tham gia? |
| **Tiếp thị** | Khách đã nhận/ghi nhận tương tác hợp lệ | Khách thuộc đối tượng của chiến dịch | Bao nhiêu đối tượng mục tiêu có tương tác? |
| **Khuyến mại bán lẻ** | Sản phẩm được mua trong chương trình theo định nghĩa | Cửa hàng–sản phẩm nằm trong phạm vi triển khai khuyến mại | Những kết hợp được triển khai nào không có giao dịch? |
| **Y tế** | Bệnh nhân đến khám theo lịch hẹn | Lịch hẹn đã xác nhận và còn hiệu lực | Tỷ lệ đến khám trong lịch hẹn là bao nhiêu? |
| **Nhân sự** | Nhân viên hoàn thành khóa an toàn | Nhân viên phải tham gia khóa trong kỳ | Ai chưa có bản ghi hoàn thành hợp lệ? |
| **Sản xuất** | Máy đã được kiểm định ở kỳ | Máy có nghĩa vụ kiểm định trong kỳ | Thiết bị nào chưa có bằng chứng kiểm định? |

Trong từng trường hợp, **mỗi hàng thuộc coverage biểu thị một nghĩa vụ/cơ hội khác nhau**. Chẳng hạn, người **nhận email** khác người **được chọn để nhận email**; việc “email đã gửi” cũng khác “người dùng đã mở email”. Phải xác định **event nào** được dùng làm tử số.

### 10.1. Ví dụ khuyến mại: cơ hội bán khác bán thực tế

Giả sử phạm vi khuyến mại được chốt ở grain:

~~~text
(promotion_key, store_key, product_key, date_key)
~~~

Mỗi hàng coverage biểu diễn “sản phẩm này có mặt trong khuyến mại tại cửa hàng trong ngày”. Các giao dịch bán hàng lại có grain **dòng giao dịch**, có thể có **số lượng** và **doanh thu**, tức là **fact có số đo**, không bắt buộc là factless event.

Muốn tìm các tổ hợp khuyến mại **không bán được sản phẩm**, có thể:

1. Lấy coverage làm tập gốc.
2. Đưa giao dịch bán về đúng grain **promotion–store–product–date**, bằng tổng hợp hoặc **EXISTS**.
3. Dùng **NOT EXISTS** để tìm tổ hợp coverage không có giao dịch bán tương ứng.

Không nối trực tiếp hàng coverage với mọi dòng bán rồi dùng **COUNT(*)** để đo cơ hội; một tổ hợp có 20 dòng bán sẽ làm coverage bị nhân lên 20 lần. Và cần xác nhận giao dịch bán có thật sự thuộc khuyến mại đó, thay vì chỉ tình cờ bán cùng sản phẩm/ngày.

### 10.2. Factless fact khác accumulating snapshot

**Accumulating snapshot fact** thường có **một hàng trên một quy trình đang tiến triển**, với các cột mốc thời gian như **ordered_date, shipped_date, delivered_date**, có thể được cập nhật khi các mốc hoàn thành. Nó trả lời **quy trình đang ở bước nào và mất bao lâu**.

**Factless event** ghi sự kiện đã xảy ra ở grain đã chọn. **Coverage fact** ghi phạm vi dự kiến; so sánh hai tập trả lời **đã có bằng chứng xảy ra hay chưa**.

Cần lựa chọn theo câu hỏi:

- “Học viên có tham dự buổi nào?” → factless event.
- “Học viên nào được dự kiến nhưng chưa tham dự?” → coverage kết hợp event.
- “Đơn hàng mất bao lâu từ đặt tới giao?” → accumulating snapshot hoặc fact sự kiện có timestamp, tùy mô hình.
- “Một lượt học kéo dài bao nhiêu phút?” → fact có measure **duration_minutes** hoặc tính khoảng thời gian từ các sự kiện thích hợp.

Không nên nhét mọi mục đích vào một bảng và gọi chung là **fact_events**.

## 11. Kiểm chứng độ đúng dữ liệu trước khi công bố chỉ số

### 11.1. Những bất biến và câu hỏi chất lượng dữ liệu

| Kiểm tra | Quy tắc của ví dụ | Hành động khi có sai lệch |
| --- | --- | --- |
| **Grain coverage** | Tối đa một hàng cho mỗi học viên–buổi đã chốt | Khóa chính chặn trùng; kiểm tra logic danh sách nguồn |
| **Grain attendance** | Tối đa một hàng xác nhận tham dự cho mỗi học viên–buổi | Gộp nhiều scan theo quy tắc xác nhận |
| **Tham chiếu dimension** | student_key và session_key phải tồn tại | Kiểm tra khóa ngoại và mã nguồn chưa ánh xạ |
| **Thời gian điểm danh** | Event phải nằm trong khoảng chấp nhận theo chính sách | Quarantine hoặc xử lý ngoại lệ có phê duyệt |
| **Danh sách ngoài phạm vi** | Event ngoài coverage phải được xác định rõ | Báo cáo riêng, không tự biến thành người dự kiến |
| **Buổi bị hủy** | Không đưa buổi hủy vào mẫu số nếu chính sách loại trừ | Dùng trạng thái buổi và version quy tắc |
| **Dữ liệu đến trễ** | Báo cáo xác định có cho phép cập nhật hồi tố hay không | Ghi thời điểm nạp và cơ chế restatement |
| **Tỷ lệ không vượt 100%** | Tử số phải là **C ∩ E**, mẫu số là C | Không dùng số event toàn cục khi có walk-in |
| **Định nghĩa chưa tham gia** | Chỉ kết luận sau hạn đồng bộ/điểm danh | Phân biệt **chưa ghi nhận** và **vắng mặt đã xác nhận** |

Những ràng buộc này có nhiều dạng. **PRIMARY KEY**, **FOREIGN KEY** ở bảng SQL bảo vệ tính duy nhất và tồn tại của khóa; kiểm tra khoảng thời gian, buổi hủy, ngoại lệ và độ trễ đòi hỏi thêm nghiệp vụ hoặc pipeline. Một schema hợp lệ về SQL không có nghĩa dữ liệu đã sẵn sàng để tính mọi chỉ số.

### 11.2. Kiểm thử các phép đối chiếu bằng SQL

Trên dữ liệu mẫu, các truy vấn kiểm tra sau có kết quả kỳ vọng:

~~~sql
-- 5 lượt nằm trong danh sách dự kiến.
SELECT COUNT(*) FROM fact_expected_attendance;

-- 4 lượt đã ghi nhận.
SELECT COUNT(*) FROM fact_attendance;

-- 1 lượt dự kiến chưa có attendance.
SELECT COUNT(*)
FROM fact_expected_attendance AS expected
WHERE NOT EXISTS (
    SELECT 1
    FROM fact_attendance AS attended
    WHERE attended.student_key = expected.student_key
      AND attended.session_key = expected.session_key
);

-- 0 lượt đã ghi nhận nhưng ở ngoài danh sách dự kiến.
SELECT COUNT(*)
FROM fact_attendance AS attended
WHERE NOT EXISTS (
    SELECT 1
    FROM fact_expected_attendance AS expected
    WHERE expected.student_key = attended.student_key
      AND expected.session_key = attended.session_key
);
~~~

Các kết quả kỳ vọng lần lượt là **5, 4, 1, 0**. Đây chỉ là **đối chiếu cho dữ liệu mẫu**. Với hệ thống thật, cần đặt điều kiện theo khóa học, ngày, trạng thái và phạm vi dữ liệu đã hoàn tất nạp.

### 11.3. Không lấy trung bình đơn giản của các tỷ lệ

Trong mẫu:

~~~text
Khóa C10: 3 / 4 = 75%
Khóa C20: 1 / 1 = 100%
~~~

Trung bình đơn giản **(75% + 100%) / 2 = 87,5%** trả lời câu hỏi “tỷ lệ trung bình giữa hai khóa học khi **mỗi khóa được trọng số như nhau**”. Nó **không** phải tỷ lệ tham gia trên mọi lượt dự kiến.

Tỷ lệ gộp theo lượt dự kiến là:

~~~text
(3 + 1) / (4 + 1) × 100% = 80%
~~~

Muốn tỷ lệ gộp, **cộng tử số và mẫu số rồi mới chia**, không trung bình các tỷ lệ khi mẫu số khác nhau. Cũng cần xem đơn vị báo cáo mong muốn là **lượt**, **người duy nhất**, **buổi**, hay **khóa học**.

### 11.4. Số 0, NULL và thiếu dữ liệu là ba khái niệm khác nhau

- **0 event sau khi đã chốt điểm danh:** có thể là không có tham gia được ghi nhận.
- **NULL tỷ lệ khi không có coverage:** không có mẫu số đủ nghĩa để tính tỷ lệ.
- **Chưa nạp dữ liệu event:** chưa thể kết luận là 0; cần trạng thái pipeline hoặc watermark.
- **Buổi bị hủy:** không mặc định tỷ lệ 0%; thường cần loại khỏi tập dự kiến hoặc báo cáo riêng theo chính sách.

Việc dùng **COALESCE(rate, 0)** trong mọi trường hợp có thể làm báo cáo nhìn dễ đọc nhưng **đánh đồng “không đủ điều kiện tính” với “không ai tham gia”**. Chỉ thay NULL bằng 0 nếu định nghĩa chỉ số thực sự yêu cầu.

## 12. Thiết kế vật lý và khả năng mở rộng

### 12.1. Khóa chính và chỉ mục theo truy vấn

Khóa chính trong ví dụ là **(student_key, session_key)**, thuận lợi khi tìm danh sách buổi của một học viên. Nếu truy vấn phổ biến là “một buổi có bao nhiêu người dự kiến/đã tham gia?”, có thể cân nhắc chỉ mục đảo thứ tự:

~~~sql
CREATE INDEX idx_expected_session_student
ON fact_expected_attendance (session_key, student_key);

CREATE INDEX idx_attendance_session_student
ON fact_attendance (session_key, student_key);
~~~

Hai chỉ mục này giúp các truy vấn lọc theo **session_key** và tra các cặp theo thứ tự **session–student** trong những tình huống thích hợp. Chúng cũng làm tăng dung lượng và chi phí ghi. **Không khẳng định sẽ nhanh hơn** nếu chưa xem phân bố dữ liệu, query plan và workload thực tế.

Nếu thường xuyên lọc theo **course_code**, SQL ở bài dùng **dim_training_session** để xác định buổi thuộc khóa học. Hệ phân tích lớn có thể tách **dim_course**, thêm khóa tham chiếu phù hợp và các chỉ mục; không nên sao chép course_code vào fact một cách máy móc khi chưa có nhu cầu rõ.

### 12.2. Partition, thời gian và ảnh chụp

Khi bảng sự kiện rất lớn, có thể cân nhắc partition theo **event date key** hoặc một ngày được lưu trực tiếp trong fact. Nhưng trong thiết kế ví dụ, ngày chỉ nằm tại **dim_training_session**; một hệ quản trị SQL không thể mặc nhiên partition fact theo một cột ở bảng dimension.

Nếu thêm **event_date_key** vào fact, cần định nghĩa nó là ngày xảy ra sự kiện hay ngày của buổi, ràng buộc tính nhất quán và xem có làm thay đổi grain không. Nếu lưu coverage snapshot hằng ngày, cần **snapshot_date_key** như một thành phần grain chứ không cộng gộp qua các snapshot tùy tiện.

### 12.3. Materialized view và chỉ số tính sẵn

Một dashboard có thể cần tốc độ truy vấn cao hơn việc JOIN hai fact lớn mỗi lần mở trang. Có thể tạo bảng tổng hợp hoặc **materialized view** ở grain **(course_key, reporting_date)** chứa:

~~~text
expected_participations
attended_in_coverage
coverage_outliers
data_as_of_timestamp
~~~

Đây là **bảng dữ kiện tổng hợp có số đo**, được **suy ra** từ hai factless fact nguồn; không làm thay đổi bản chất của hai bảng nguồn. Phải lưu quy tắc tái tính và thời điểm hoàn tất nạp để giải thích tại sao số trên dashboard có thể thay đổi sau khi nhận event đến trễ.

### 12.4. Tránh đếm bằng cách tạo hàng giả

Không cần tạo một hàng với **attendance = 0** cho mọi cặp học viên–buổi không có sự kiện. Việc này có thể làm phình dữ liệu và, nếu phạm vi kỳ vọng không được định nghĩa, tạo ra các “lượt vắng mặt” không có thật.

Mô hình factless thường vận hành tự nhiên:

~~~text
CÓ HÀNG event     -> đã ghi nhận sự kiện theo grain
CÓ HÀNG coverage  -> thuộc tập dự kiến theo grain
CÓ coverage, KHÔNG CÓ event
                   -> chưa ghi nhận sự kiện trong phạm vi dự kiến
KHÔNG CÓ coverage -> không đủ cơ sở kết luận vắng mặt
~~~

Nếu nghiệp vụ cần **kết quả điểm danh ba trạng thái** (có mặt, vắng có phép, vắng không phép) hoặc điểm số, cần mô hình **attendance outcome/status** rõ ràng; không nên ép mọi kết quả vào sự tồn tại/không tồn tại của một hàng event.

## 13. Quy trình thiết kế factless fact từ yêu cầu nghiệp vụ

1. **Xác định câu hỏi phân tích.** Cần đếm lượt tham gia, người duy nhất, hay tìm sự kiện chưa xảy ra trong tập kỳ vọng?
2. **Chốt grain bằng một câu chính xác.** “Một hàng là một học viên được ghi nhận tham dự một buổi” khác “một hàng là một lần quét thẻ”.
3. **Phân biệt event và coverage.** Sự kiện đã có khác tập người được mời, đăng ký, có quyền hoặc bắt buộc tham gia.
4. **Xác nhận thời gian hiệu lực.** Event xảy ra khi nào? Coverage chốt khi nào? Kỳ báo cáo dùng ngày địa phương hay UTC?
5. **Chọn dimension và khóa.** Các dimension có được dùng chung với cùng ý nghĩa và phiên bản lịch sử không? Có degenerate ID cần truy vết không?
6. **Đặt ràng buộc grain.** Bảo vệ uniqueness của tổ hợp khóa ở từng fact; kiểm soát mã chưa có dimension và sự kiện nguồn trùng.
7. **Thiết kế pipeline.** Chọn cơ chế nạp idempotent, khử trùng theo đúng grain và cách xử lý late-arriving facts/dimensions.
8. **Định nghĩa metric.** Nêu rõ tử số, mẫu số, tập lọc, trạng thái hoàn tất, cách xử lý 0/NULL và đối tượng ngoài coverage.
9. **Kiểm thử phản ví dụ.** Học viên không nằm trong danh sách; buổi bị hủy; quét thẻ hai lần; event đến trễ; thay đổi đơn vị học viên.
10. **Tối ưu sau khi đúng.** Đánh giá chỉ mục, partition, aggregate và workload; giữ nguồn fact rõ ràng để tái tính và kiểm toán.

### 13.1. Checklist câu hỏi phải thống nhất trước khi triển khai

| Câu hỏi | Nếu chưa rõ sẽ dẫn đến |
| --- | --- |
| Một hàng biểu diễn sự kiện hay một đối tượng duy nhất? | Đếm nhầm scan, lượt và người |
| Ai được đưa vào coverage, tính tại thời điểm nào? | Sai mẫu số và “vắng mặt” giả |
| Có sự kiện hợp lệ ngoài coverage không? | Tử số vượt mẫu số hoặc bị mất dữ liệu ngoại lệ |
| Nếu buổi bị hủy hoặc chuyển lịch thì xử lý thế nào? | Lưu coverage lỗi thời, tỷ lệ không có ý nghĩa |
| Khi event đến trễ thì báo cáo có được sửa lại không? | Chỉ số thay đổi không giải thích được |
| Dimension có lịch sử nhiều phiên bản không? | JOIN nhân hàng hoặc mất kết quả |
| Dữ liệu nguồn có thể phát nhiều event cho một lượt không? | Nhân số tham gia |
| Có cần phân biệt vắng có phép/vắng không phép không? | Mô hình factless đơn giản không đủ diễn đạt |
| Ai sở hữu định nghĩa “tham gia hợp lệ”? | Bộ phận khác nhau tính chỉ số khác nhau |

## 14. Bài tập thực hành

### Bài 1. Tính chỉ số từ hai tập factless

Giả sử một lớp kỹ năng có danh sách dự kiến và tham gia:

~~~text
Coverage (student, session):
(A, X1), (B, X1), (C, X1), (A, X2), (B, X2)

Event (student, session):
(A, X1), (C, X1), (A, X2), (D, X2)
~~~

**Yêu cầu:**

1. Cho biết số lượt dự kiến, số lượt event, số học viên event duy nhất.
2. Tìm **coverage − event** và **event − coverage**.
3. Tính tỷ lệ tham gia **trong phạm vi coverage**.
4. Giải thích vì sao không dùng **4 / 5 = 80%** làm tỷ lệ tham gia của tập dự kiến.

<details>
<summary>Gợi ý lời giải bài 1</summary>

- Có **5 lượt dự kiến**, **4 lượt event**, **3 học viên event duy nhất** (A, C, D).
- **Coverage − event = {(B,X1), (B,X2)}**: hai lượt chưa ghi nhận.
- **Event − coverage = {(D,X2)}**: một lượt event ngoài danh sách.
- **Coverage ∩ event = {(A,X1), (C,X1), (A,X2)}**, nên tỷ lệ đúng là **3/5 = 60%**.
- Nếu lấy **4/5**, lượt ngoài danh sách **(D,X2)** làm tăng tử số dù không thuộc mẫu số; có thể gây chỉ số sai và che mất vấn đề định nghĩa phạm vi.

</details>

### Bài 2. Một hay hai fact table?

Một hệ thống bắt buộc nhân viên hoàn thành đào tạo an toàn. Có:

~~~text
employee_id
course_id
assigned_at
completion_scan_id
completed_at
~~~

Mỗi nhân viên có thể được phân công một khóa nhưng chưa hoàn thành; nguồn quét hoàn thành có thể gửi hai sự kiện trùng cho cùng một lượt.

**Yêu cầu:** đề xuất grain cho coverage và event, khóa ngăn trùng và cách xác định “chưa hoàn thành”. Nếu phải học lại mỗi năm, cần bổ sung thuộc tính gì vào grain?

<details>
<summary>Gợi ý lời giải bài 2</summary>

Coverage có thể có grain **(employee_id, course_id, required_period_id)**: một nghĩa vụ hoàn thành khóa của nhân viên trong một kỳ. Event có cùng grain khi chỉ cần ghi nhận **đã hoàn thành ít nhất một lần hợp lệ** trong kỳ.

Nguồn scan giữ grain **completion_scan_id**, có thể nhiều hàng cho cùng nghĩa vụ. Sau khi xác nhận event hợp lệ, chỉ nạp một event mỗi khóa grain. **Chưa hoàn thành** là **coverage − event** trong những kỳ đã đến hạn/đủ điều kiện đối soát.

Nếu bắt buộc học lại hằng năm, thêm **năm/kỳ nghĩa vụ** hoặc một **assignment_instance_id** theo định nghĩa nghiệp vụ; không chỉ dùng (employee_id, course_id), nếu không sẽ nhầm lượt hoàn thành của năm trước với nghĩa vụ năm sau.

</details>

### Bài 3. Phát hiện nhân hàng do JOIN sai

Buổi X có 3 học viên dự kiến và 2 học viên đã tham gia, tất cả event đều thuộc coverage. Nhóm triển khai nối hai fact **chỉ qua session_key**, rồi tính COUNT(*).

**Yêu cầu:** dự đoán số dòng JOIN, nêu số lượt đúng và đề xuất cách sửa.

<details>
<summary>Gợi ý lời giải bài 3</summary>

JOIN theo session_key tạo **3 × 2 = 6 hàng**, không phải 2 hàng tham gia. Cần JOIN theo **(student_key, session_key)** để đối chiếu từng lượt, bắt đầu từ coverage và LEFT JOIN event.

Khi hai fact đều bảo vệ uniqueness cặp, **COUNT(attended.student_key) = 2**, **COUNT(expected.student_key) = 3**, tỷ lệ là **2/3 ≈ 66,67%**.

</details>

### Bài 4. Chọn tập kỳ vọng đúng ngữ nghĩa

Một trường có 10.000 học viên, 200 buổi học trong học kỳ, nhưng mỗi học viên chỉ đăng ký một số buổi. Người viết báo cáo dùng **CROSS JOIN dim_student × dim_session** làm tập coverage, sau đó NOT EXISTS với attendance để tìm số người vắng.

**Yêu cầu:** giải thích vì sao sai, đề xuất nguồn coverage hợp lý và cách xử lý sinh viên đăng ký muộn hoặc chuyển buổi.

<details>
<summary>Gợi ý lời giải bài 4</summary>

**CROSS JOIN** tạo 2.000.000 tổ hợp có thể hình thành, nhưng không có quy tắc nghiệp vụ cho rằng mọi học viên phải tham dự mọi buổi. Phần lớn hàng bị kết luận vắng là **tổ hợp không thuộc lịch học**.

Coverage nên xuất phát từ **danh sách học viên được xếp vào từng buổi** theo một mốc chốt và chính sách đăng ký cụ thể. Với đăng ký muộn, chuyển buổi, cần xác nhận báo cáo dùng danh sách **as-of** lúc nào, cách chuyển nguồn tới dimension và lưu lịch sử nếu phải tái tạo chỉ số quá khứ.

</details>

### Bài 5. Dữ liệu đến trễ và kết luận vắng mặt

Điểm danh buổi T101 kết thúc lúc 10:00 ngày 19/11. Lúc 11:00, hệ thống phân tích chưa nhận bản ghi của S02 nên báo cáo cho thấy lượt **(S02,T101)** chưa có event. Ngày 21/11, log của S02 được nạp bù với **occurred_at** ngày 19/11.

**Yêu cầu:** trạng thái nào là đúng tại 11:00 ngày 19/11 và trong báo cáo tái tính ngày 21/11? Cần giữ thêm thông tin nào để giải thích sự thay đổi?

**Hướng giải:** tại 11:00 ngày 19/11, theo dữ liệu đã nạp S02 là **“chưa được ghi nhận”**, chưa chắc vắng thật. Sau khi nạp event hợp lệ xảy ra ngày 19/11, phép đối chiếu mới cho thấy S02 đã tham gia. Cần giữ **occurred_at**, **ingested_at**, thời điểm chốt coverage và trạng thái hoàn tất pipeline hoặc snapshot báo cáo để giải thích vì sao hai báo cáo có kết quả khác nhau.

## 15. Những ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Không có cột measure thì không phải fact table.” | Sự hiện diện của một hàng ở grain xác định chính là dữ kiện; có thể đếm để tạo measure suy diễn. |
| “COUNT(*) luôn bằng số người tham gia.” | Nó đếm **hàng tại grain**, có thể là lượt, scan hoặc quan hệ. |
| “Không có hàng attendance nghĩa là chắc chắn vắng mặt.” | Phải biết đối tượng thuộc coverage, buổi đã diễn ra và dữ liệu đã nạp đủ. |
| “Mọi đối tượng × mọi buổi đều là coverage.” | Chỉ đúng khi nghiệp vụ thật sự yêu cầu **mọi tổ hợp**. |
| “Chỉ cần fact sự kiện để tính tỷ lệ tham gia.” | Cần mẫu số có ý nghĩa, thường đến từ coverage. |
| “Event ngoài coverage tự động không hợp lệ.” | Có thể là khách mời hoặc lỗi danh sách; cần chính sách rõ trước khi chấp nhận hoặc loại. |
| “JOIN hai fact qua cùng ngày/buổi là đủ.” | Phải JOIN theo **đúng toàn bộ grain** để không nhân hàng. |
| “COUNT(DISTINCT) luôn sửa được số đếm sai.” | DISTINCT có thể xóa mất những lượt hợp lệ khác nhau. |
| “Đã có hàng dimension thì phải có hàng fact.” | Dimension mô tả đối tượng; fact chỉ lưu sự thật đã xác định. |
| “Coverage hiện tại dùng được cho mọi báo cáo quá khứ.” | Phạm vi dự kiến có thể thay đổi; cần mốc as-of/snapshot phù hợp. |
| “Đếm NULL như 0 sẽ làm dashboard chính xác hơn.” | NULL có thể nghĩa là **không đủ mẫu số**, không phải tỷ lệ 0%. |
| “Đếm theo khóa học bằng trung bình tỷ lệ từng khóa.” | Muốn tỷ lệ lượt gộp, phải **cộng tử số và mẫu số rồi chia**. |

## 16. Ghi nhớ

**Factless fact table** lưu một sự thật thông qua **sự tồn tại của hàng**, thường không cần measure số. Có hai loại thường gặp:

- **Event/participation fact:** một sự kiện hoặc một lượt tham gia đã được ghi nhận.
- **Coverage/eligibility fact:** một đối tượng thuộc tập được dự kiến, đủ điều kiện hoặc có cơ hội xảy ra sự kiện theo quy tắc cụ thể.

Muốn biết **ai chưa được ghi nhận tham gia**, cần xét **coverage − event**, không phải mọi tổ hợp giữa các dimension. Muốn tính **tỷ lệ tham gia**, tử số là những event **nằm trong coverage**, mẫu số là **số lượt coverage** hợp lệ; hai tập phải cùng grain, thời gian và phạm vi. Bản ghi event đến trễ, thay đổi danh sách, dimension lịch sử và các phép JOIN sai khóa đều có thể làm thay đổi số liệu mà không phát sinh một cột measure nào.

Thiết kế đáng tin cậy bắt đầu bằng **định nghĩa nghiệp vụ → grain → dimension/khóa → event và coverage → pipeline/kiểm chứng → metric → tối ưu vật lý**. Đây là cách dùng factless fact để mô tả sự tham gia hoặc sự xuất hiện **đúng ý nghĩa**, dễ đối soát và có khả năng tiến hóa trong một hệ thống phân tích.
