# CONCAT, phép nối chuỗi và hành vi khi gặp NULL

Trong SQL, **nối chuỗi** (*string concatenation*) là thao tác ghép các đoạn văn bản thành một giá trị văn bản mới. Ví dụ, từ họ **Nguyễn**, tên đệm **Văn** và tên **An**, ta có thể ghép thành **Nguyễn Văn An**. Tương tự, một truy vấn báo cáo có thể ghép mã đơn, trạng thái, địa chỉ, số lượng hay thông báo thành chuỗi dễ đọc.

Vấn đề xuất hiện khi **một trong các thành phần bị thiếu (NULL)**. Một số phép nối chuỗi biến cả kết quả thành NULL; một số hàm **bỏ qua thành phần NULL** và vẫn giữ các phần còn lại. Hơn nữa, một **chuỗi rỗng** không nhất thiết có nghĩa giống NULL. Cách xử lý này còn **khác nhau theo hệ quản trị SQL**, nên cùng một từ khóa **CONCAT** hoặc toán tử nối chuỗi có thể cho kết quả khác nhau.

Bài học nằm trong chương **Biểu thức và hàm** của module **Database SQL**. Phần thực hành chính dùng **PostgreSQL 15 trở lên** với bảng tạm độc lập. Phần đối chiếu giới thiệu hành vi tiêu biểu của **MySQL 8.0**, **SQL Server**, **SQLite** và **Oracle Database** để bạn biết khi nào cần đổi cách viết.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **NULL**, **chuỗi rỗng** và **chuỗi chỉ chứa khoảng trắng**.
2. Nối chuỗi bằng toán tử **||** và hàm **CONCAT** trong PostgreSQL.
3. Dự đoán kết quả khi các đối số có NULL và giải thích sự khác nhau giữa các hệ quản trị.
4. Dùng **CONCAT_WS** để nối nhiều thành phần với một dấu phân cách.
5. Kết hợp **COALESCE**, **NULLIF** và **TRIM** để xử lý dữ liệu thiếu và khoảng trắng.
6. Tạo tên đầy đủ, địa chỉ, nhãn hiển thị và thông điệp có quy tắc NULL rõ ràng.
7. Nhận biết các tác động tới **WHERE**, **COUNT**, **GROUP BY**, chỉ mục và việc chuyển đổi phương ngữ.
8. Tránh những lỗi như ghép khóa nhiều cột thành chuỗi mơ hồ hoặc dùng phép nối chuỗi để tự xây dựng SQL từ dữ liệu đầu vào.

## 2. NULL, chuỗi rỗng và khoảng trắng: ba tình huống khác nhau

Trước khi dùng CONCAT, cần phân biệt dữ liệu đầu vào:

| Giá trị | Ý nghĩa | Trong PostgreSQL |
| --- | --- | --- |
| **NULL** | Không có giá trị hoặc chưa biết giá trị | Không bằng một chuỗi thông thường |
| **''** | Chuỗi văn bản có độ dài 0 | Một giá trị văn bản hợp lệ, khác NULL |
| **' '** | Chuỗi có một dấu cách | Độ dài 1, khác chuỗi rỗng |
| **'NULL'** | Bốn chữ cái N, U, L, L | Một chuỗi văn bản, không phải SQL NULL |

Chạy trong PostgreSQL:

~~~sql
SELECT
    NULL::TEXT IS NULL            AS missing_value,
    ''::TEXT IS NULL              AS empty_is_null,
    LENGTH(''::TEXT)              AS empty_length,
    LENGTH(' '::TEXT)             AS one_space_length,
    'NULL'::TEXT IS NULL          AS literal_null_is_missing;
~~~

Kết quả lần lượt là **TRUE**, **FALSE**, **0**, **1**, **FALSE**.

Hai câu điều kiện dưới đây **không tương đương**:

~~~sql
WHERE middle_name IS NULL
~~~

~~~sql
WHERE middle_name = ''
~~~

Câu thứ nhất tìm **giá trị thiếu**; câu thứ hai tìm **chuỗi tồn tại nhưng không có ký tự**. Muốn tìm cả hai trường hợp, có thể viết:

~~~sql
WHERE middle_name IS NULL OR middle_name = ''
~~~

Nếu dữ liệu có chuỗi chỉ chứa dấu cách như **'   '**, có thể chuẩn hóa trước bằng **TRIM**. Tuy nhiên, lựa chọn xem dấu cách là “thiếu dữ liệu” hay là nội dung hợp lệ phải theo yêu cầu của ứng dụng.

> Lưu ý về phương ngữ: **Oracle Database** có quy tắc khác đối với chuỗi rỗng của kiểu chuỗi văn bản thông dụng: chuỗi có độ dài 0 hiện thường được coi là NULL. Vì vậy, đừng lấy kết quả phân biệt NULL và '' của PostgreSQL rồi áp dụng nguyên văn cho Oracle.

## 3. Chuẩn bị dữ liệu thực hành

Tạo bảng tạm **concat_demo_people** trong một phiên PostgreSQL. Một số người thiếu họ hoặc tên đệm, có giá trị tên đệm rỗng, hoặc thiếu toàn bộ tên. Các trường hợp này giúp chúng ta quan sát kết quả nối chuỗi.

~~~sql
CREATE TEMP TABLE concat_demo_people (
    person_id   INTEGER PRIMARY KEY,
    family_name TEXT,
    middle_name TEXT,
    given_name  TEXT,
    city        TEXT,
    district    TEXT,
    phone       TEXT
);

INSERT INTO concat_demo_people
    (person_id, family_name, middle_name, given_name,
     city, district, phone)
VALUES
    (1, 'Nguyễn', NULL,  'An',   'Hà Nội',          'Ba Đình',  '0900000001'),
    (2, 'Trần',   'Văn', 'Bình', 'Đà Nẵng',         NULL,       NULL),
    (3, NULL,     NULL,  'Chi',  'Huế',             'Phú Hội',  NULL),
    (4, 'Phạm',   '',    'Mai',  NULL,              'Quận 1',  ''),
    (5, NULL,     NULL,  NULL,   NULL,              NULL,      NULL),
    (6, 'Đỗ',    'Thị', 'Linh', 'TP. Hồ Chí Minh', 'Quận 3',  NULL),
    (7, 'Võ',     NULL,  'Hải',  'Huế',             '',         ' ');
~~~

Kiểm tra đầu vào:

~~~sql
SELECT person_id, family_name, middle_name, given_name,
       city, district, phone
FROM concat_demo_people
ORDER BY person_id;
~~~

Các trường hợp cần chú ý:

- **Người 1** thiếu tên đệm, nhưng có họ và tên.
- **Người 3** thiếu họ và tên đệm.
- **Người 4** có middle_name = **''** và city = NULL.
- **Người 5** thiếu toàn bộ các thành phần tên.
- **Người 7** có district = **''** và phone chỉ chứa một dấu cách.

**Bảng tạm** chỉ tồn tại trong phiên kết nối hiện tại; khi đóng phiên, bảng sẽ biến mất. Nếu chạy lại phần CREATE TABLE trong cùng phiên, PostgreSQL báo bảng đã tồn tại. Hãy dùng phiên mới hoặc chủ động xóa riêng bảng tạm của bài trước khi tạo lại.

## 4. Nối chuỗi bằng toán tử ||

Trong PostgreSQL, toán tử **||** nối hai chuỗi:

~~~sql
SELECT 'Database' || ' ' || 'SQL' AS course_name;
~~~

Kết quả:

~~~text
Database SQL
~~~

Toán tử được dùng nhiều lần để nối nhiều phần. Dấu cách ở ví dụ trên là một **đối số chuỗi riêng**; SQL không tự thêm khoảng trắng.

### 4.1. Khi gặp NULL, toán tử || cho NULL

~~~sql
SELECT
    'Xin chào ' || 'An'::TEXT          AS complete_text,
    'Xin chào ' || NULL::TEXT          AS missing_name,
    NULL::TEXT || ' Nguyễn'           AS missing_prefix;
~~~

Trong PostgreSQL, **complete_text = 'Xin chào An'**; hai biểu thức còn lại là **NULL**.

Nếu bất kỳ thành phần nào của chuỗi nối bằng **||** là NULL, kết quả của toàn bộ chuỗi nối cũng thành NULL:

~~~sql
SELECT
    family_name || ' ' || middle_name || ' ' || given_name
        AS full_name
FROM concat_demo_people
ORDER BY person_id;
~~~

Đối với **người 1**, middle_name = NULL nên full_name = NULL, dù cả họ và tên đều có dữ liệu. Điều này thường **không phù hợp** nếu mục đích chỉ là hiển thị tên đầy đủ có thể có.

Mặt khác, việc cho NULL có thể **đúng theo nghiệp vụ**. Ví dụ, nếu một mã hợp lệ bắt buộc phải có cả mã vùng và số thuê bao, hai cột thiếu một phần thì kết quả chung cũng nên được xem là thiếu, thay vì tạo ra một mã có vẻ hợp lệ nhưng không đủ thông tin.

### 4.2. Có thể sử dụng COALESCE với ||

**COALESCE(expression, fallback)** trả về đối số đầu tiên không NULL. Có thể biến thành phần thiếu thành chuỗi rỗng:

~~~sql
SELECT
    person_id,
    COALESCE(family_name, '')
        || ' '
        || COALESCE(middle_name, '')
        || ' '
        || COALESCE(given_name, '') AS full_name
FROM concat_demo_people
ORDER BY person_id;
~~~

Kết quả **không còn NULL do các tên bị thiếu**, nhưng dễ thừa khoảng trắng:

- Người 1: **'Nguyễn  An'** — hai dấu cách giữa họ và tên.
- Người 3: **'  Chi'** — hai dấu cách đứng đầu.
- Người 5: **'  '** — chỉ có hai dấu cách, dù không có tên nào.

Việc thay NULL bằng '' là một bước xử lý có chủ đích, nhưng **không giải quyết tự động vấn đề dấu phân cách**. Phần tiếp theo sẽ dùng CONCAT và CONCAT_WS để cải thiện.

## 5. Hàm CONCAT trong PostgreSQL

Trong PostgreSQL, **CONCAT(value1, value2, ...)** ghép các đối số theo thứ tự, **bỏ qua đối số NULL** và chuyển các đối số không phải chuỗi sang dạng văn bản khi có thể.

~~~sql
SELECT
    CONCAT('Database', ' ', 'SQL')        AS example_one,
    CONCAT('Xin chào ', NULL::TEXT)      AS example_two,
    CONCAT('A', NULL::TEXT, 'B')          AS example_three,
    CONCAT(NULL::TEXT, NULL::TEXT)       AS example_four;
~~~

Kết quả PostgreSQL:

| Biểu thức | Kết quả |
| --- | --- |
| CONCAT('Database', ' ', 'SQL') | **'Database SQL'** |
| CONCAT('Xin chào ', NULL) | **'Xin chào '** |
| CONCAT('A', NULL, 'B') | **'AB'** |
| CONCAT(NULL, NULL) | **''** — chuỗi rỗng |

Đây là điểm quan trọng: **CONCAT của PostgreSQL xử lý NULL khác với toán tử ||**.

~~~sql
SELECT
    CONCAT('A', NULL::TEXT, 'B') AS with_concat,
    'A' || NULL::TEXT || 'B'     AS with_operator;
~~~

Kết quả là **'AB'** và **NULL**. Cùng đầu vào nhưng **khác ngữ nghĩa NULL**.

### 5.1. CONCAT không tự thêm dấu cách hoặc dấu phẩy

~~~sql
SELECT CONCAT('Nguyễn', 'Văn', 'An') AS full_name;
~~~

Kết quả **'NguyễnVănAn'**. Muốn có dấu cách, phải cung cấp nó:

~~~sql
SELECT CONCAT('Nguyễn', ' ', 'Văn', ' ', 'An') AS full_name;
~~~

Tuy nhiên, khi tên đệm NULL, các dấu cách được ghi **tường minh** vẫn còn:

~~~sql
SELECT CONCAT('Nguyễn', ' ', NULL::TEXT, ' ', 'An') AS full_name;
~~~

Kết quả **'Nguyễn  An'** có hai dấu cách. Hàm CONCAT đã bỏ qua **đối số NULL**, nhưng **không bỏ qua hai đối số ' '** ở hai bên.

### 5.2. Nối dữ liệu không phải chuỗi

Trong PostgreSQL, CONCAT có thể chuyển số và nhiều kiểu giá trị khác sang văn bản:

~~~sql
SELECT
    CONCAT('Đơn #', 1001) AS order_label,
    CONCAT('Số lượng: ', 3) AS quantity_label;
~~~

Kết quả **'Đơn #1001'** và **'Số lượng: 3'**.

Với **toán tử ||**, nên chú ý kiểu dữ liệu và có thể chuyển kiểu tường minh:

~~~sql
SELECT 'Đơn #' || 1001::TEXT AS order_label;
~~~

Khi muốn hiển thị số tiền, thời gian hoặc ngày tháng theo định dạng ổn định, hãy dùng **hàm định dạng hoặc CAST** thích hợp. Đừng phụ thuộc hoàn toàn vào biểu diễn ngầm định vì cách hiển thị có thể thay đổi theo kiểu dữ liệu, thiết lập phiên và phương ngữ.

## 6. CONCAT_WS: nối chuỗi với dấu phân cách

Tên **CONCAT_WS** là viết tắt của **CONCAT With Separator**. Cú pháp PostgreSQL:

~~~sql
CONCAT_WS(separator, value1, value2, ...)
~~~

Trong đó:

- **separator** là chuỗi phân cách được chèn **giữa các đối số được giữ lại**.
- Các **value** bằng NULL được bỏ qua.
- Chuỗi rỗng **'' vẫn được giữ**, trừ khi bạn chủ động biến nó thành NULL.
- Nếu chính **separator = NULL**, kết quả PostgreSQL là **NULL**.

Ví dụ:

~~~sql
SELECT
    CONCAT_WS(' ', 'Nguyễn', 'Văn', 'An') AS full_one,
    CONCAT_WS(' ', 'Nguyễn', NULL::TEXT, 'An') AS full_two,
    CONCAT_WS(' / ', 'A', NULL::TEXT, 'C') AS joined_three;
~~~

Kết quả:

| full_one | full_two | joined_three |
| --- | --- | --- |
| Nguyễn Văn An | Nguyễn An | A / C |

### 6.1. CONCAT_WS tránh dấu phân cách dư do NULL

Áp dụng vào bảng:

~~~sql
SELECT
    person_id,
    CONCAT_WS(' ', family_name, middle_name, given_name) AS full_name
FROM concat_demo_people
ORDER BY person_id;
~~~

Kết quả dự kiến:

| person_id | full_name |
| ---: | --- |
| 1 | Nguyễn An |
| 2 | Trần Văn Bình |
| 3 | Chi |
| 4 | Phạm  Mai |
| 5 | '' (chuỗi rỗng) |
| 6 | Đỗ Thị Linh |
| 7 | Võ Hải |

Đã giải quyết NULL ở người 1 và 3, nhưng **người 4 vẫn có hai dấu cách**, vì middle_name của người đó là **''**, không phải NULL. Còn người 5 không có phần tử nào để nối nên CONCAT_WS trả về chuỗi rỗng.

### 6.2. CONCAT_WS không tự loại chuỗi rỗng

~~~sql
SELECT
    CONCAT_WS(' | ', 'A', NULL::TEXT, 'C') AS skip_null,
    CONCAT_WS(' | ', 'A', ''::TEXT, 'C')   AS keep_empty,
    CONCAT_WS(' | ', NULL::TEXT, NULL::TEXT) AS all_missing,
    CONCAT_WS(NULL::TEXT, 'A', 'C') AS missing_separator;
~~~

Trong PostgreSQL:

| Biểu thức | Kết quả |
| --- | --- |
| CONCAT_WS(' | ', 'A', NULL, 'C') | **'A | C'** |
| CONCAT_WS(' | ', 'A', '', 'C') | **'A |  | C'** |
| CONCAT_WS(' | ', NULL, NULL) | **''** |
| CONCAT_WS(NULL, 'A', 'C') | **NULL** |

Phân biệt **NULL của thành phần** và **NULL của separator** là điều cần nhớ khi truyền dấu phân cách từ biến hoặc cột dữ liệu.

## 7. Kết hợp TRIM và NULLIF để làm sạch thành phần

Trong dữ liệu thật, một trường “không có tên đệm” có thể được lưu dưới dạng NULL, '', hoặc '   '. Nếu yêu cầu hiển thị xem **chuỗi rỗng và toàn dấu cách** như không có thành phần, có thể chuẩn hóa:

~~~sql
NULLIF(TRIM(middle_name), '')
~~~

Ý nghĩa theo thứ tự:

1. **TRIM(middle_name)** bỏ các dấu cách ở đầu và cuối theo quy tắc mặc định của PostgreSQL.
2. Nếu sau khi TRIM chuỗi trở thành **''**, **NULLIF(..., '')** trả về **NULL**.
3. Nếu là NULL ngay từ đầu, TRIM và NULLIF tiếp tục cho NULL.
4. CONCAT_WS sẽ **bỏ qua** thành phần NULL đó khi đặt dấu phân cách.

Ví dụ:

~~~sql
SELECT
    NULLIF(TRIM(' Văn '), '') AS cleaned_name,
    NULLIF(TRIM('   '), '')   AS cleaned_spaces,
    NULLIF(TRIM(''), '')      AS cleaned_empty;
~~~

Kết quả là **'Văn'**, **NULL**, **NULL**.

### 7.1. Công thức tên đầy đủ tránh dư khoảng trắng

~~~sql
SELECT
    person_id,
    CONCAT_WS(
        ' ',
        NULLIF(TRIM(family_name), ''),
        NULLIF(TRIM(middle_name), ''),
        NULLIF(TRIM(given_name), '')
    ) AS full_name
FROM concat_demo_people
ORDER BY person_id;
~~~

Kết quả:

| person_id | full_name đã chuẩn hóa |
| ---: | --- |
| 1 | Nguyễn An |
| 2 | Trần Văn Bình |
| 3 | Chi |
| 4 | Phạm Mai |
| 5 | '' (chuỗi rỗng) |
| 6 | Đỗ Thị Linh |
| 7 | Võ Hải |

Nếu muốn người 5 có **full_name = NULL** thay vì '', bọc kết quả cuối bằng NULLIF:

~~~sql
SELECT
    person_id,
    NULLIF(
        CONCAT_WS(
            ' ',
            NULLIF(TRIM(family_name), ''),
            NULLIF(TRIM(middle_name), ''),
            NULLIF(TRIM(given_name), '')
        ),
        ''
    ) AS full_name
FROM concat_demo_people
ORDER BY person_id;
~~~

Trong cách này, người 5 nhận **NULL**; các tên còn lại giữ nguyên. Mỗi thao tác xử lý NULL cần gắn với một quy tắc rõ ràng: **bỏ phần tên thiếu**, **loại khoảng trắng không có ý nghĩa**, và **coi toàn bộ tên thiếu là NULL**.

> TRIM mặc định không phải công cụ chuẩn hóa tất cả các ký tự khoảng trắng Unicode, chẳng hạn mọi kiểu dấu cách không ngắt dòng. Nếu dữ liệu có ký tự đặc biệt, cần quy định phương pháp làm sạch phù hợp với hệ quản trị và ứng dụng.

## 8. Hiển thị giá trị thiếu: bỏ qua, thay thế hay giữ NULL?

Một trường thiếu dữ liệu không phải lúc nào cũng cần bị bỏ qua. Chọn một trong các chính sách sau:

| Nhu cầu | Công thức gợi ý PostgreSQL | Nếu thành phần NULL |
| --- | --- | --- |
| Ghép phần có sẵn | CONCAT('Họ: ', family_name) | Giữ tiền tố, bỏ phần tên |
| Bắt buộc đầy đủ mọi phần | family_name || ' ' || given_name | Toàn bộ kết quả NULL |
| Có dấu phân cách, bỏ thành phần thiếu | CONCAT_WS(' ', family_name, given_name) | Giữ phần còn lại, không thêm dấu cách dư do NULL |
| Thay thiếu bằng nhãn dễ hiểu | CONCAT('SĐT: ', COALESCE(phone, '(chưa có)')) | Hiển thị '(chưa có)' |
| Chỉ hiển thị nhãn nếu có dữ liệu | CASE WHEN phone IS NULL THEN NULL ELSE CONCAT('SĐT: ', phone) END | Trả NULL |
| Coi chuỗi rỗng là thiếu | NULLIF(TRIM(phone), '') | NULL khi trống hoặc chỉ toàn dấu cách |

### 8.1. Ví dụ nhãn điện thoại

~~~sql
SELECT
    person_id,
    CONCAT(
        'SĐT: ',
        COALESCE(NULLIF(TRIM(phone), ''), '(chưa cung cấp)')
    ) AS phone_label
FROM concat_demo_people
ORDER BY person_id;
~~~

Với người 2, 3, 5, 6 và 7, nhãn hiển thị **'SĐT: (chưa cung cấp)'**. Người 4 có phone = '' cũng nhận nhãn này. Người 1 có số điện thoại thật nên nhãn hiển thị số ấy.

Lưu ý: **COALESCE** không tự loại chuỗi rỗng. Nếu chỉ viết **COALESCE(phone, '(chưa cung cấp)')**, người 4 có phone = '' vẫn được coi là đã có giá trị; kết quả chỉ là 'SĐT: '.

### 8.2. Tránh nhãn không có nội dung

Trong PostgreSQL, **CONCAT('SĐT: ', NULL)** cho kết quả **'SĐT: '**. Đây có thể là cách hiển thị không mong muốn. Nếu chỉ muốn hiển thị nhãn khi có số điện thoại:

~~~sql
SELECT
    person_id,
    CASE
        WHEN NULLIF(TRIM(phone), '') IS NULL THEN NULL
        ELSE CONCAT('SĐT: ', TRIM(phone))
    END AS phone_label
FROM concat_demo_people
ORDER BY person_id;
~~~

Khi phone thiếu hoặc trống, **phone_label = NULL**, còn người 1 sẽ có giá trị dạng **'SĐT: 0900000001'**. Cách viết bằng **CASE** phù hợp khi chính sách hiển thị phức tạp hơn việc nối các thành phần đơn thuần.

## 9. Nối địa chỉ nhiều thành phần

Giả sử một địa chỉ rút gọn gồm **district** và **city**. Ta muốn có dấu phẩy và dấu cách **chỉ khi cả hai thành phần có dữ liệu**.

~~~sql
SELECT
    person_id,
    CONCAT_WS(
        ', ',
        NULLIF(TRIM(district), ''),
        NULLIF(TRIM(city), '')
    ) AS short_address
FROM concat_demo_people
ORDER BY person_id;
~~~

Kết quả tiêu biểu:

| person_id | short_address |
| ---: | --- |
| 1 | Ba Đình, Hà Nội |
| 2 | Đà Nẵng |
| 3 | Phú Hội, Huế |
| 4 | Quận 1 |
| 5 | '' |
| 6 | Quận 3, TP. Hồ Chí Minh |
| 7 | Huế |

Trường hợp người 4 có city = NULL, nhưng district = 'Quận 1', nên kết quả chỉ là **'Quận 1'**, không có dấu phẩy thừa. Người 7 có district = '', được chuẩn hóa thành NULL nên chỉ còn **'Huế'**.

Nếu quy trình giao hàng yêu cầu bắt buộc cả quận và thành phố, không nên dùng kết quả nối chuỗi này để mặc định rằng địa chỉ đã **đủ điều kiện giao**. Có thể kiểm tra độc lập:

~~~sql
SELECT person_id
FROM concat_demo_people
WHERE NULLIF(TRIM(district), '') IS NOT NULL
  AND NULLIF(TRIM(city), '') IS NOT NULL
ORDER BY person_id;
~~~

Truy vấn trên chỉ chọn những người có **cả hai thành phần**. **Chuỗi hiển thị dễ đọc** và **dữ liệu đủ để xử lý nghiệp vụ** là hai yêu cầu khác nhau.

## 10. Nối số, ngày tháng và giá trị có định dạng

Trong báo cáo, chúng ta thường ghép chữ với mã đơn, số lượng, số tiền hoặc ngày. Cần quan tâm đến cách chuyển các kiểu dữ liệu sang văn bản.

### 10.1. Nối mã và số lượng

~~~sql
SELECT
    CONCAT('Khách hàng #', person_id) AS customer_label
FROM concat_demo_people
ORDER BY person_id;
~~~

Kết quả dạng **'Khách hàng #1'**, **'Khách hàng #2'**, ... Trong PostgreSQL, CONCAT có thể chuyển giá trị số sang văn bản.

Để rõ kiểu khi dùng ||:

~~~sql
SELECT
    'Khách hàng #' || person_id::TEXT AS customer_label
FROM concat_demo_people
ORDER BY person_id;
~~~

Khi chuyển mã số sang văn bản, nên bảo đảm **mã định danh không có số 0 đầu bị mất do từng lưu bằng kiểu số**. Ví dụ mã '0012' và số 12 có thể không tương đương về nghiệp vụ; nếu số 0 đầu là quan trọng, hãy thiết kế dữ liệu mã dưới dạng chuỗi từ đầu.

### 10.2. Định dạng ngày

Trong PostgreSQL:

~~~sql
SELECT CONCAT(
    'Ngày đặt: ',
    TO_CHAR(DATE '2026-05-20', 'DD/MM/YYYY')
) AS order_date_label;
~~~

Kết quả **'Ngày đặt: 20/05/2026'**.

Nếu chỉ dùng CONCAT với DATE và phụ thuộc vào chuyển kiểu mặc định, biểu diễn có thể khác kỳ vọng của người dùng hoặc phụ thuộc cấu hình. **TO_CHAR** thể hiện rõ định dạng mong muốn trong PostgreSQL; hệ khác có hàm và cú pháp khác.

### 10.3. Định dạng tiền

~~~sql
SELECT
    CONCAT(
        'Thành tiền: ',
        TO_CHAR(250000::NUMERIC, 'FM999,999,999'),
        ' VND'
    ) AS amount_label;
~~~

Trong thiết lập định dạng theo ví dụ này, kết quả dự kiến là **'Thành tiền: 250,000 VND'**. Ký hiệu phân tách và thiết lập vùng có thể ảnh hưởng cách hiển thị số ở các hệ khác; ứng dụng quốc tế hóa thường định dạng tiền ở tầng trình bày.

**Không nên lưu số tiền dưới dạng chuỗi đã ghép kèm đơn vị** nếu còn cần SUM, AVG, ORDER BY số học. Hãy giữ dữ liệu tiền ở cột **NUMERIC/DECIMAL**, rồi tạo nhãn hiển thị khi truy vấn hoặc trong ứng dụng.

## 11. So sánh CONCAT và phép nối chuỗi theo phương ngữ SQL

Cùng một câu SQL có thể cho kết quả khác nhau tùy **hệ quản trị**. Đây là bảng đối chiếu quan trọng:

| Hệ quản trị | Phép nối chuỗi thường dùng | CONCAT('A', NULL, 'B') | Nối với NULL bằng toán tử | Hàm ghép có separator |
| --- | --- | --- | --- | --- |
| **PostgreSQL 15+** | **||**, CONCAT | **'AB'**; bỏ qua NULL | **||** cho NULL | **CONCAT_WS** bỏ thành phần NULL |
| **MySQL 8.0** | **CONCAT** | **NULL** nếu có đối số NULL | **||** mặc định thường là OR logic, không phải toán tử nối chuỗi | **CONCAT_WS** bỏ thành phần NULL |
| **SQL Server (hiện đại)** | **CONCAT**, toán tử **+** | **'AB'**; xem NULL như chuỗi rỗng | **+** cho NULL khi nối với NULL theo quy tắc hiện đại | **CONCAT_WS** có từ SQL Server 2017 |
| **SQLite 3.44+** | **||**, CONCAT | **'AB'**; bỏ qua NULL | **||** cho NULL | **CONCAT_WS** ở phiên bản hỗ trợ |
| **Oracle Database** | **||**, CONCAT hai đối số | **Không hợp lệ** với ba đối số CONCAT | **||** có ngữ nghĩa NULL đặc thù: nối giá trị có thật với NULL vẫn có thể giữ phần có thật | Không giả định có CONCAT_WS giống PostgreSQL |

**Lưu ý về phiên bản:** SQLite có **concat()** và **concat_ws()** ở các phiên bản mới, từ **3.44.0**; các phiên bản trước chủ yếu dùng **||**, **COALESCE** hoặc hàm mở rộng. MySQL có chế độ SQL đặc biệt **PIPES_AS_CONCAT** có thể làm **||** mang nghĩa nối chuỗi; không nên phụ thuộc vào chế độ này khi viết SQL chạy ở nhiều nơi. Với SQL Server, cú pháp và hành vi nối chuỗi cũng cần đối chiếu phiên bản thực tế, nhất là khi chuyển mã cũ sử dụng toán tử **+**.

### 11.1. PostgreSQL: CONCAT bỏ qua NULL, || lan truyền NULL

~~~sql
SELECT
    CONCAT('A', NULL::TEXT, 'B') AS via_function,
    'A' || NULL::TEXT || 'B'     AS via_operator;
~~~

Kết quả: **via_function = 'AB'**, **via_operator = NULL**.

### 11.2. MySQL 8.0: CONCAT trả NULL nếu một đối số NULL

~~~sql
SELECT
    CONCAT('A', NULL, 'B') AS via_function,
    CONCAT_WS('-', 'A', NULL, 'B') AS via_separator;
~~~

Kết quả MySQL: **via_function = NULL**, **via_separator = 'A-B'**.

Để chủ động thay NULL bằng chuỗi rỗng:

~~~sql
SELECT CONCAT('A', COALESCE(NULL, ''), 'B') AS text_value;
~~~

Kết quả **'AB'**. Đây là một lý do khi chuyển truy vấn từ PostgreSQL sang MySQL, cần xem lại mọi vị trí sử dụng **CONCAT** với cột nullable.

### 11.3. SQL Server: CONCAT và toán tử +

~~~sql
SELECT
    CONCAT('A', CAST(NULL AS VARCHAR(20)), 'B') AS via_function,
    'A' + CAST(NULL AS VARCHAR(20)) + 'B'       AS via_operator,
    CONCAT_WS('-', 'A', CAST(NULL AS VARCHAR(20)), 'B')
        AS via_separator;
~~~

Với SQL Server hiện đại, kết quả tương ứng **'AB'**, **NULL**, **'A-B'**. Toán tử **+** có thể dùng để nối chuỗi nhưng cũng là toán tử cộng số học; cần chú ý **kiểu dữ liệu**, tránh vô tình làm phát sinh cộng số hoặc lỗi chuyển kiểu.

Trong SQL Server 2017 trở lên, thiết lập **CONCAT_NULL_YIELDS_NULL** luôn được bật theo hành vi được hỗ trợ; không nên thiết kế câu lệnh mới dựa vào khả năng tắt thiết lập này như một số mã rất cũ.

### 11.4. SQLite: || và CONCAT khác nhau

Với SQLite **3.44.0 trở lên**:

~~~sql
SELECT
    concat('A', NULL, 'B') AS via_function,
    'A' || NULL || 'B'     AS via_operator,
    concat_ws('-', 'A', NULL, 'B') AS via_separator;
~~~

Kết quả lần lượt **'AB'**, **NULL**, **'A-B'**.

Nếu dùng SQLite cũ chưa có hàm concat, có thể dùng:

~~~sql
SELECT 'A' || COALESCE(NULL, '') || 'B' AS text_value;
~~~

Tuy nhiên, cách nối dấu phân cách tùy chọn sẽ phức tạp hơn so với CONCAT_WS; thường cần CASE hoặc chuẩn hóa dữ liệu.

### 11.5. Oracle: chuỗi rỗng và NULL có quy tắc riêng

Trong Oracle Database, hàm **CONCAT** thông dụng nhận **hai đối số**:

~~~sql
SELECT CONCAT('A', 'B') AS text_value
FROM dual;
~~~

Muốn ghép nhiều thành phần, thường dùng **||**:

~~~sql
SELECT 'A' || NULL || 'B' AS text_value
FROM dual;
~~~

Trong hành vi Oracle hiện hành, kết quả là **'AB'**; một NULL ở một phía không nhất thiết làm cả phép nối || thành NULL như PostgreSQL. Ngoài ra, Oracle thường coi chuỗi rỗng **''** là **NULL** trong dữ liệu chuỗi thông dụng. Đây là khác biệt rất lớn khi di chuyển truy vấn dùng CONCAT/||, COALESCE hoặc kiểm tra chuỗi rỗng.

### Không có một quy tắc CONCAT duy nhất cho mọi SQL

Vì vậy, khi đọc câu lệnh từ một dự án khác, hãy xác định **tên hệ quản trị và phiên bản** trước khi dự đoán kết quả:

~~~sql
CONCAT('A', nullable_column, 'B')
~~~

Trên PostgreSQL, kết quả thường vẫn có hai phần A và B khi nullable_column là NULL. Trên MySQL, toàn bộ kết quả có thể thành NULL. Hành vi không thể suy ra chỉ từ tên hàm.

## 12. CONCAT và điều kiện WHERE

Phép nối chuỗi không chỉ dùng để hiển thị; đôi khi người viết dùng kết quả để lọc hoặc so sánh. Khi đó, **chính sách NULL trở thành một phần của điều kiện WHERE**.

Ví dụ PostgreSQL:

~~~sql
SELECT person_id
FROM concat_demo_people
WHERE family_name || ' ' || given_name = 'Nguyễn An';
~~~

Truy vấn chọn **người 1** vì family_name và given_name đều có giá trị. Nhưng:

~~~sql
SELECT person_id
FROM concat_demo_people
WHERE family_name || ' ' || middle_name || ' ' || given_name
      = 'Nguyễn An';
~~~

không chọn người 1 do middle_name = NULL làm cả biểu thức **||** thành NULL, phép so sánh với 'Nguyễn An' thành UNKNOWN, và WHERE chỉ giữ TRUE.

Nếu muốn bỏ thành phần thiếu:

~~~sql
SELECT person_id
FROM concat_demo_people
WHERE CONCAT_WS(
    ' ',
    NULLIF(TRIM(family_name), ''),
    NULLIF(TRIM(middle_name), ''),
    NULLIF(TRIM(given_name), '')
) = 'Nguyễn An';
~~~

Truy vấn này chọn người 1.

**Tuy nhiên, khi mục đích là tìm theo một trường riêng**, chẳng hạn family_name = 'Nguyễn', nên ưu tiên so sánh **chính cột nguồn** nếu có thể. Một hàm bọc quanh cột trong WHERE có thể khiến chỉ mục thông thường trên cột đó không được dùng theo cách tối ưu.

### 12.1. CONCAT có thể tạo chuỗi rỗng khi mọi cột NULL

~~~sql
SELECT person_id
FROM concat_demo_people
WHERE CONCAT_WS(' ', family_name, middle_name, given_name) = '';
~~~

Trong PostgreSQL, kết quả có thể bao gồm **người 5**, dù không có bất kỳ thành phần tên nào. Nếu ứng dụng coi chuỗi rỗng là “không có tên”, cần làm rõ bằng NULLIF:

~~~sql
SELECT person_id
FROM concat_demo_people
WHERE NULLIF(
    CONCAT_WS(' ', family_name, middle_name, given_name),
    ''
) IS NULL;
~~~

Điều này giúp bạn không nhầm một chuỗi được hàm tạo ra với dữ liệu tên thật.

## 13. Nối chuỗi và COUNT, GROUP BY, DISTINCT

Các hàm tổng hợp và phép loại trùng có cách xử lý NULL riêng. Khi một biểu thức nối chuỗi **biến NULL thành chuỗi rỗng**, kết quả đếm và nhóm có thể thay đổi.

Trong PostgreSQL:

~~~sql
SELECT
    COUNT(*) AS all_people,
    COUNT(family_name) AS known_family_names,
    COUNT(CONCAT(family_name, given_name)) AS concat_count,
    COUNT(family_name || given_name) AS operator_count
FROM concat_demo_people;
~~~

Với bảng mẫu:

| all_people | known_family_names | concat_count | operator_count |
| ---: | ---: | ---: | ---: |
| 7 | 5 | 7 | 5 |

Giải thích:

- **COUNT(*)** đếm cả bảy người.
- **COUNT(family_name)** bỏ hai hàng family_name = NULL (người 3 và 5), còn **5**.
- **COUNT(CONCAT(family_name, given_name)) = 7** vì CONCAT của PostgreSQL trả chuỗi rỗng (không phải NULL) ngay cả khi mọi đối số đều NULL.
- **COUNT(family_name || given_name) = 5** vì kết quả là NULL khi một trong hai thành phần thiếu.

Nếu chỉ muốn đếm những người có **tên hiển thị không rỗng**, có thể kết hợp NULLIF:

~~~sql
SELECT COUNT(
    NULLIF(
        CONCAT_WS(
            ' ',
            NULLIF(TRIM(family_name), ''),
            NULLIF(TRIM(middle_name), ''),
            NULLIF(TRIM(given_name), '')
        ),
        ''
    )
) AS people_with_display_name
FROM concat_demo_people;
~~~

Kết quả **6**, vì người 5 không có thành phần tên.

### 13.1. GROUP BY theo chuỗi nối có thể gộp nhiều tình huống

~~~sql
SELECT
    CONCAT_WS(', ',
        NULLIF(TRIM(district), ''),
        NULLIF(TRIM(city), '')
    ) AS short_address,
    COUNT(*) AS people_count
FROM concat_demo_people
GROUP BY 1
ORDER BY people_count DESC, short_address;
~~~

Những hàng có các thành phần khác nhau nhưng ghép thành **cùng chuỗi hiển thị** sẽ thuộc cùng nhóm. Điều đó có thể hữu ích cho báo cáo hiển thị, nhưng cũng có thể làm mất sự phân biệt giữa các trường hợp dữ liệu khác nhau.

**Không dùng tên ghép hoặc địa chỉ ghép như khóa định danh** nếu các thành phần gốc có thể trùng hoặc thiếu.

## 14. STRING_AGG khác CONCAT

**CONCAT** và **CONCAT_WS** nối các giá trị **trong cùng một hàng hoặc cùng một biểu thức**. Nếu cần nối dữ liệu **từ nhiều hàng** thành một chuỗi, PostgreSQL cung cấp **STRING_AGG**.

Ví dụ nối tên hiển thị của tất cả người có tên:

~~~sql
WITH names AS (
    SELECT
        person_id,
        NULLIF(
            CONCAT_WS(
                ' ',
                NULLIF(TRIM(family_name), ''),
                NULLIF(TRIM(middle_name), ''),
                NULLIF(TRIM(given_name), '')
            ),
            ''
        ) AS full_name
    FROM concat_demo_people
)
SELECT STRING_AGG(full_name, '; ' ORDER BY person_id) AS name_list
FROM names;
~~~

Trong PostgreSQL, **STRING_AGG** bỏ qua các giá trị đầu vào NULL; vì thế người 5 không góp chuỗi rỗng vào danh sách. Danh sách kết quả theo thứ tự gồm:

~~~text
Nguyễn An; Trần Văn Bình; Chi; Phạm Mai; Đỗ Thị Linh; Võ Hải
~~~

**STRING_AGG** là hàm tổng hợp nhiều hàng, còn **CONCAT_WS** là hàm ghép nhiều đối số. Những hệ quản trị khác có thể dùng tên như **GROUP_CONCAT** hoặc **LISTAGG** với cú pháp và quy tắc sắp xếp riêng. Không dùng CONCAT để thay thế việc tổng hợp nhiều hàng.

## 15. Tránh ghép khóa nhiều cột thành chuỗi mơ hồ

Một sai lầm nguy hiểm là tạo “khóa ghép” bằng cách nối các giá trị mà không có mã hóa hoặc cấu trúc đủ rõ:

~~~sql
SELECT
    CONCAT('ab', 'c') AS key_one,
    CONCAT('a', 'bc') AS key_two;
~~~

Cả hai đều cho **'abc'**, dù hai cặp gốc khác nhau. Thêm dấu phân cách không luôn giải quyết hoàn toàn:

~~~sql
SELECT
    CONCAT_WS('|', 'a|b', 'c') AS key_one,
    CONCAT_WS('|', 'a', 'b|c') AS key_two;
~~~

Cả hai có thể thành **'a|b|c'** vì chính dữ liệu chứa ký tự phân cách. NULL và '' cũng có thể bị đồng nhất nếu dùng CONCAT bỏ qua NULL.

Khi cần xác định duy nhất **cặp (customer_id, order_date)** hay **(order_id, product_id)**, hãy dùng các cột gốc:

~~~sql
-- Minh họa cách so sánh khóa ghép trên hệ hỗ trợ row values:
WHERE (order_id, product_id) = (1001, 102)
~~~

Hoặc dùng:

~~~sql
WHERE order_id = 1001 AND product_id = 102
~~~

Và khi thiết kế bảng, dùng **PRIMARY KEY (order_id, product_id)** hoặc **UNIQUE** trên đúng tổ hợp cột. Chỉ sử dụng mã chuỗi dẫn xuất nếu đã có cơ chế mã hóa không nhập nhằng, quy tắc xử lý NULL và kiểm soát tính duy nhất thích hợp.

## 16. Hiệu năng và khả năng đánh chỉ mục

Hàm nối chuỗi có thể được tính trên mỗi hàng khi chạy SELECT, WHERE hoặc ORDER BY. Với số lượng nhỏ, chi phí thường không đáng kể; với bảng lớn hoặc biểu thức lặp lại nhiều lần, cần cân nhắc.

### 16.1. Lọc theo cột nguồn khi có thể

Nếu muốn tìm người có họ Nguyễn:

~~~sql
SELECT person_id
FROM concat_demo_people
WHERE family_name = 'Nguyễn';
~~~

Điều kiện này biểu diễn đúng trường cần tìm và có thể được hỗ trợ bởi chỉ mục thích hợp trên **family_name**. Còn điều kiện:

~~~sql
WHERE CONCAT_WS(' ', family_name, given_name) = 'Nguyễn An'
~~~

phải xét giá trị của **biểu thức ghép**, có thể không tận dụng trực tiếp chỉ mục thông thường trên family_name. Nếu ứng dụng thường xuyên tìm theo tên ghép, có thể cân nhắc **chỉ mục theo biểu thức**, cột chuẩn hóa hoặc chiến lược tìm kiếm văn bản, tùy hệ quản trị.

### 16.2. Không phải mọi biểu thức đều dùng được cho generated column hoặc expression index

Trong PostgreSQL, biểu thức của **generated column** và **expression index** có quy định về **tính bất biến (IMMUTABLE)** của hàm. Hàm **CONCAT/CONCAT_WS** trong PostgreSQL không được đánh dấu IMMUTABLE, vì cách chuyển một số kiểu dữ liệu thành văn bản có thể phụ thuộc thiết lập; do đó **không thể mặc định dùng trực tiếp chúng** trong biểu thức đòi IMMUTABLE.

Với nhu cầu tạo trường tìm kiếm trong lược đồ, hãy kiểm tra **kiểu cột nguồn, hàm được dùng và quy tắc của phiên bản PostgreSQL**. Một công thức thuần văn bản dùng các toán tử và hàm phù hợp có thể là phương án khác, hoặc có thể lưu trường chuẩn hóa bằng quy trình cập nhật của ứng dụng khi nghiệp vụ yêu cầu.

### 16.3. Tính di động và việc kiểm tra kế hoạch thực thi

Ở MySQL, SQL Server, SQLite, PostgreSQL, chỉ mục trên biểu thức hoặc cột tính toán có cú pháp và điều kiện khác nhau. Không thể quyết định cách tối ưu chỉ từ tên hàm CONCAT. Với truy vấn quan trọng, xem **EXPLAIN** hoặc kế hoạch thực thi tương ứng trên **dữ liệu và hệ quản trị thực tế**.

## 17. Không dùng CONCAT để lắp ghép câu SQL từ dữ liệu người dùng

CONCAT chỉ tạo ra **giá trị văn bản**. Nếu dùng nó để tạo câu SQL động từ dữ liệu không tin cậy, có thể làm phát sinh lỗi trích dẫn hoặc nguy cơ **SQL injection**.

Ví dụ ý tưởng **không nên dùng** trong ứng dụng:

~~~text
sql = "SELECT * FROM customers WHERE email = '" + userInput + "'"
~~~

Thay vì tự nối đầu vào vào chuỗi truy vấn, ứng dụng nên dùng **prepared statement / truy vấn tham số hóa**:

~~~sql
SELECT *
FROM customers
WHERE email = ?;
~~~

Dấu **?** là kiểu placeholder thường thấy trong JDBC và nhiều thư viện; PostgreSQL qua những giao diện khác có thể dùng **$1** hoặc cú pháp binding của framework. Mục tiêu là để **driver truyền giá trị tách biệt với cấu trúc SQL**, không tự tạo dấu nháy và ghép chuỗi.

Điều này không ngăn bạn dùng CONCAT **bên trong một truy vấn hợp lệ** để tạo nhãn hiển thị. Chỉ cần không nhầm “nối dữ liệu” với “xây dựng mã SQL thực thi”.

## 18. Lỗi thường gặp

| Hiện tượng hoặc hiểu nhầm | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Nối tên bằng || rồi bị NULL dù còn họ và tên | Một thành phần giữa chuỗi là NULL | Dùng CONCAT_WS hoặc COALESCE theo quy tắc hiển thị |
| CONCAT tạo hai dấu cách liên tiếp | Đã thêm dấu cách cố định xung quanh thành phần NULL | Dùng CONCAT_WS để chỉ phân cách các phần được giữ |
| CONCAT_WS vẫn tạo dấu phân cách dư | Thành phần là '' chứ không phải NULL | Dùng NULLIF(TRIM(col), '') trước khi nối |
| CONCAT_WS trả '' khi mọi giá trị đều NULL | Hàm bỏ qua toàn bộ thành phần NULL | Bọc kết quả bằng NULLIF(..., '') nếu cần NULL |
| CONCAT cho NULL trên MySQL dù PostgreSQL cho chữ | Hành vi NULL khác theo phương ngữ | Dùng CONCAT_WS hoặc COALESCE, kiểm tra hệ thực tế |
| Dùng || trong MySQL nhưng không nối được chuỗi | || thường mang nghĩa OR logic ở chế độ mặc định | Dùng CONCAT/CONCAT_WS |
| Dùng + trong PostgreSQL để nối chữ | PostgreSQL dùng || cho phép nối chuỗi | Dùng || hoặc CONCAT |
| COUNT(CONCAT(...)) cao bất ngờ | Hàm có thể tạo '' thay vì NULL | Xác định thế nào là “có giá trị”; cân nhắc NULLIF |
| Kết quả chỉ là 'SĐT: ' | CONCAT bỏ qua phone NULL nhưng giữ tiền tố | Dùng CASE hoặc COALESCE với nhãn thiếu |
| Nối ngày tháng nhưng hiển thị sai định dạng | Chuyển kiểu ngày thành chuỗi theo định dạng mặc định | Dùng hàm định dạng của phương ngữ |
| Hai cặp khóa khác nhau tạo cùng một chuỗi | Nối không mã hóa, dấu phân cách không an toàn | Giữ khóa ghép theo các cột gốc |
| Truy vấn tìm kiếm theo chuỗi ghép chậm | Biểu thức trong WHERE có thể không tận dụng chỉ mục cột | Lọc theo cột nguồn, cân nhắc index chuyên dụng |
| Cố dùng CONCAT_WS trong generated column PostgreSQL | Hàm không thỏa yêu cầu IMMUTABLE của biểu thức | Thiết kế công thức phù hợp hoặc dùng giải pháp khác |
| Ghép dữ liệu người dùng vào SQL động | Nguy cơ sai cú pháp và SQL injection | Dùng truy vấn có tham số |

## 19. Bài tập thực hành

Dùng bảng tạm **concat_demo_people** đã tạo ở phần 3 và PostgreSQL:

1. Dự đoán kết quả của **'A' || NULL::TEXT || 'B'**, **CONCAT('A', NULL::TEXT, 'B')** và **CONCAT_WS('-', 'A', NULL::TEXT, 'B')**, rồi chạy SELECT kiểm tra.
2. Dùng toán tử **||** để ghép family_name, middle_name, given_name với dấu cách. Người nào nhận NULL, và vì sao?
3. Viết lại bài 2 bằng **CONCAT** nhưng vẫn đưa dấu cách như đối số. Người 1 và 3 có hiện tượng gì?
4. Dùng **CONCAT_WS(' ', ...)** để ghép tên. Giải thích vì sao người 4 có thể xuất hiện hai dấu cách.
5. Kết hợp **NULLIF(TRIM(col), '')** với CONCAT_WS để tạo tên không dư dấu cách. Đối với người 5, hãy quyết định kết quả nên là NULL hay '', rồi viết công thức phù hợp.
6. Tạo cột kết quả **phone_label** hiển thị số điện thoại nếu có; nếu thiếu hoặc chỉ có khoảng trắng thì hiển thị **'(chưa cung cấp)'**.
7. Tạo **short_address** từ district và city, phân cách bằng **', '**; tránh dấu phẩy dư khi một phần không có.
8. Đếm số người có **ít nhất một thành phần tên thực sự có nội dung**. Không đếm người 5.
9. Dùng **STRING_AGG** tạo danh sách tên đầy đủ đã chuẩn hóa, cách nhau bằng dấu chấm phẩy và một dấu cách, sắp theo person_id.
10. Tự so sánh kết quả khi **CONCAT(NULL, NULL)** với **NULL::TEXT || NULL::TEXT** trong PostgreSQL.
11. Viết câu lệnh nối chữ với số khách hàng để có dạng **'Khách hàng #7'**. Thực hiện bằng CONCAT và bằng || có chuyển kiểu tường minh.
12. Cho hai cặp **('ab','c')** và **('a','bc')**. Chứng minh CONCAT không an toàn để tạo khóa ghép duy nhất, rồi đề xuất cách kiểm tra hai cột đúng.
13. Viết một truy vấn dùng **CASE**: nếu phone thiếu hoặc rỗng, phone_label = NULL; nếu có thì phone_label bắt đầu bằng **'SĐT: '**.
14. Chuyển biểu thức **CONCAT('A', nullable_col, 'B')** từ PostgreSQL sang MySQL để có thể **giữ A và B khi nullable_col NULL**.
15. Với SQL Server, so sánh **CONCAT('A', NULL, 'B')** và **'A' + CAST(NULL AS VARCHAR(10)) + 'B'**.
16. Tra cứu phiên bản SQLite bạn đang dùng và chọn cách nối chuỗi khi có NULL: **concat()** nếu được hỗ trợ, hoặc **|| + COALESCE** nếu dùng phiên bản cũ.
17. Giải thích vì sao **COALESCE(phone, 'N/A')** chưa xử lý được phone = '', và vì sao **NULLIF(TRIM(phone), '')** hữu ích.

## 20. Câu hỏi tự kiểm tra

**Câu 1:** Trong PostgreSQL, kết quả của **CONCAT('A', NULL, 'B')** và **'A' || NULL || 'B'** có giống nhau không?

**Trả lời:** **Không.** CONCAT bỏ qua NULL và trả **'AB'**; toán tử || làm cả chuỗi thành **NULL**.

**Câu 2:** CONCAT_WS có bỏ qua chuỗi rỗng không?

**Trả lời:** **Không.** Nó bỏ qua **NULL**, còn **''** vẫn tham gia phép nối và có thể tạo dấu phân cách liên tiếp. Có thể dùng **NULLIF(TRIM(x), '')** nếu muốn coi chuỗi rỗng là thiếu.

**Câu 3:** Trong PostgreSQL, CONCAT(NULL, NULL) trả về gì?

**Trả lời:** **Chuỗi rỗng ''**, không phải NULL.

**Câu 4:** Hai tên có đầy đủ các thành phần nhưng khoảng trắng dư có nên được sửa bằng TRIM ở cuối chuỗi ghép không?

**Trả lời:** TRIM bên ngoài chỉ bỏ khoảng trắng **đầu và cuối**, thường không giải quyết khoảng trắng dư **ở giữa**. Nên xử lý từng thành phần rồi dùng CONCAT_WS để ghép.

**Câu 5:** Vì sao dùng CONCAT(a, b) làm khóa ghép có thể không an toàn?

**Trả lời:** Hai tổ hợp khác nhau như **('ab','c')** và **('a','bc')** đều thành **'abc'**, gây nhầm lẫn. Hãy giữ hai cột làm khóa ghép.

**Câu 6:** MySQL 8.0 có nhất thiết cho cùng kết quả với PostgreSQL khi chạy CONCAT('A', NULL, 'B') không?

**Trả lời:** **Không.** MySQL thường trả **NULL** nếu bất kỳ đối số CONCAT nào NULL, còn PostgreSQL bỏ qua NULL.

**Câu 7:** Khi cần nối các giá trị của nhiều hàng vào một chuỗi, nên dùng CONCAT hay STRING_AGG trong PostgreSQL?

**Trả lời:** **STRING_AGG** để tổng hợp nhiều hàng; CONCAT để ghép nhiều đối số thành một biểu thức trên từng hàng.

## 21. Ghi nhớ cốt lõi

**CONCAT và phép nối chuỗi không có một quy tắc NULL giống nhau trên mọi hệ SQL.** Trong PostgreSQL, **CONCAT bỏ qua NULL**, còn **|| truyền NULL sang toàn bộ kết quả**. **CONCAT_WS** giúp thêm dấu phân cách đúng giữa những thành phần không NULL, nhưng **không tự bỏ chuỗi rỗng**. Kết hợp **TRIM**, **NULLIF** và **COALESCE** cho phép kiểm soát cả dữ liệu thiếu, dấu cách dư và nhãn thay thế.

Khi dùng SQL trên nhiều hệ quản trị, hãy kiểm tra **phương ngữ và phiên bản** trước khi chuyển câu lệnh: **MySQL CONCAT** có thể trả NULL khi bất kỳ đối số nào NULL; **SQL Server CONCAT** bỏ qua NULL nhưng toán tử **+** có quy tắc riêng; **SQLite** phụ thuộc phiên bản hỗ trợ các hàm; **Oracle** có hành vi đặc biệt với chuỗi rỗng và NULL.

Cuối cùng, hãy giữ các dữ liệu có cấu trúc ở **đúng cột và đúng kiểu**. Nối chuỗi rất hữu ích cho **hiển thị**, nhưng không thay thế khóa ghép, phép kiểm tra dữ liệu gốc hay truy vấn tham số hóa.
