# JSON_OBJECT, JSON_ARRAY và các hàm tổng hợp JSON trong Oracle Database

Oracle cung cấp nhóm hàm SQL/JSON generation để tạo JSON trực tiếp từ dữ liệu quan hệ. Thay vì nối chuỗi thủ công rồi tự escape dấu nháy, dấu gạch chéo và ký tự điều khiển, bạn có thể dùng **JSON_OBJECT**, **JSON_ARRAY**, **JSON_OBJECTAGG** và **JSON_ARRAYAGG** để tạo cấu trúc JSON hợp lệ ngay trong câu SELECT.

Bốn hàm có hai vai trò khác nhau:

- **JSON_OBJECT** tạo một JSON object từ các cặp key/value hoặc các cột của một hàng.
- **JSON_ARRAY** tạo một JSON array từ danh sách biểu thức.
- **JSON_ARRAYAGG** gom kết quả của nhiều hàng thành một JSON array.
- **JSON_OBJECTAGG** gom các cặp key/value từ nhiều hàng thành một JSON object.

Có thể lồng các hàm này để tạo tài liệu phân cấp, ví dụ một phòng ban có danh sách nhân viên, một đơn hàng có danh sách dòng hàng, hoặc một sản phẩm có tập thuộc tính. Trong Oracle 19c, kết quả mặc định là VARCHAR2(4000); khi JSON có thể lớn hơn, cần chọn kiểu trả về phù hợp như CLOB.

Bài học tập trung vào cú pháp và cách sử dụng bốn hàm, chuyển đổi kiểu SQL sang JSON, xử lý NULL, FORMAT JSON, RETURNING, STRICT, WITH UNIQUE KEYS, tổng hợp theo nhóm, thứ tự phần tử, nested JSON, lưu JSON và các lưu ý hiệu năng.

## 1. Tổng quan bốn hàm tạo JSON

### 1.1. Tạo object cho từng hàng

JSON_OBJECT tạo một object cho mỗi hàng mà câu SELECT trả về:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'firstName'  VALUE first_name,
           'salary'     VALUE salary
       ) AS employee_json
FROM   employees;
~~~

Nếu truy vấn trả về 20 hàng, kết quả có 20 giá trị JSON object. Hàm không tự gom 20 hàng thành một array.

### 1.2. Tạo array từ các biểu thức

JSON_ARRAY tạo một array từ các đối số theo đúng thứ tự được viết:

~~~sql
SELECT JSON_ARRAY(
           employee_id,
           first_name,
           salary
       ) AS employee_values
FROM   employees;
~~~

Mỗi hàng tạo một array riêng. Phần tử đầu tiên tương ứng employee_id, phần tử thứ hai là first_name, phần tử thứ ba là salary.

### 1.3. Gom nhiều hàng thành array

JSON_ARRAYAGG là hàm aggregate. Nó biến các giá trị của nhiều hàng thành một JSON array:

~~~sql
SELECT JSON_ARRAYAGG(
           employee_id
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employee_ids
FROM   employees;
~~~

Truy vấn trên trả một giá trị array chứa ID của các nhân viên được chọn.

### 1.4. Gom nhiều hàng thành object

JSON_OBJECTAGG là hàm aggregate tạo một object từ các cặp key/value của nhiều hàng:

~~~sql
SELECT JSON_OBJECTAGG(
           department_name VALUE department_id
           RETURNING CLOB
       ) AS department_map
FROM   departments;
~~~

Mỗi hàng đóng góp một member cho object. Ví dụ department name là key, department ID là value.

### 1.5. Bảng so sánh

| Hàm | Đầu vào chính | Kết quả | Số hàng đầu ra điển hình |
| --- | --- | --- | --- |
| JSON_OBJECT | Cặp key/value hoặc cột | Một JSON object | Một object cho mỗi hàng nguồn |
| JSON_ARRAY | Danh sách biểu thức | Một JSON array | Một array cho mỗi hàng nguồn |
| JSON_ARRAYAGG | Biểu thức từ nhiều hàng | Một JSON array | Một array cho mỗi nhóm |
| JSON_OBJECTAGG | Key/value từ nhiều hàng | Một JSON object | Một object cho mỗi nhóm |

Hai hàm không có hậu tố AGG thường dùng để tạo cấu trúc từ một hàng hoặc một danh sách đối số. Hai hàm có hậu tố AGG gom dữ liệu qua nhiều hàng theo quy tắc aggregate SQL.

## 2. Chuẩn bị dữ liệu thực hành

Các ví dụ tiếp theo dùng hai bảng nhỏ tự tạo, không phụ thuộc schema mẫu HR.

### 2.1. Tạo bảng phòng ban

~~~sql
CREATE TABLE json_demo_dept (
    department_id   NUMBER PRIMARY KEY,
    department_name VARCHAR2(100) NOT NULL,
    location        VARCHAR2(100)
);
~~~

### 2.2. Tạo bảng nhân viên

~~~sql
CREATE TABLE json_demo_emp (
    employee_id   NUMBER PRIMARY KEY,
    department_id NUMBER,
    first_name    VARCHAR2(50) NOT NULL,
    last_name     VARCHAR2(50) NOT NULL,
    salary        NUMBER(10,2),
    commission    NUMBER(5,2),
    hire_date     DATE,
    CONSTRAINT fk_json_demo_emp_dept
        FOREIGN KEY (department_id)
        REFERENCES json_demo_dept(department_id)
);
~~~

### 2.3. Nạp dữ liệu mẫu

~~~sql
INSERT INTO json_demo_dept VALUES (10, 'Engineering', 'Ho Chi Minh City');
INSERT INTO json_demo_dept VALUES (20, 'Finance', 'Ha Noi');
INSERT INTO json_demo_dept VALUES (30, 'Operations', 'Da Nang');
INSERT INTO json_demo_dept VALUES (40, 'Research', NULL);

INSERT INTO json_demo_emp VALUES
    (101, 10, 'An', 'Nguyen', 2500,  NULL, DATE '2022-01-10');

INSERT INTO json_demo_emp VALUES
    (102, 10, 'Binh', 'Tran', 3200, 5, DATE '2021-06-15');

INSERT INTO json_demo_emp VALUES
    (103, 10, 'Chi', 'Le', 2800, NULL, DATE '2023-03-20');

INSERT INTO json_demo_emp VALUES
    (201, 20, 'Dung', 'Pham', 4100, 10, DATE '2020-09-01');

INSERT INTO json_demo_emp VALUES
    (301, 30, 'Giang', 'Vo', 2300, NULL, DATE '2024-02-12');

COMMIT;
~~~

Phòng ban 40 chưa có nhân viên. Dữ liệu này giúp quan sát trường hợp truy vấn con không trả hàng và cách tạo array rỗng.

## 3. JSON_OBJECT — tạo JSON object

### 3.1. Cú pháp key VALUE expression

Cách viết rõ ràng:

~~~sql
SELECT JSON_OBJECT(
           'id'         VALUE employee_id,
           'firstName'  VALUE first_name,
           'lastName'   VALUE last_name,
           'salary'     VALUE salary
       ) AS employee_json
FROM   json_demo_emp
ORDER  BY employee_id;
~~~

Tên key là chuỗi được đặt trong dấu nháy đơn. Từ khóa VALUE phân cách key và biểu thức tạo value.

Có thể dùng dấu hai chấm thay cho từ khóa VALUE:

~~~sql
JSON_OBJECT('id' : employee_id)
~~~

Tuy nhiên, một số client driver quét dấu hai chấm để tìm bind variable và có thể hiểu nhầm dấu phân cách này. Dùng VALUE thường rõ ràng và ít gây nhầm lẫn hơn trong công cụ SQL.

### 3.2. Tên key có phân biệt chữ hoa/thường

Tên key được cung cấp tường minh là tên thuộc tính JSON. Ví dụ:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'EmployeeName' VALUE first_name
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

JSON trả về có đúng hai key employeeId và EmployeeName. Quy ước tên key là một phần của API JSON; nên thống nhất camelCase, snake_case hoặc quy tắc đã chọn.

### 3.3. Dùng tên cột làm key

Có thể đưa tên cột trực tiếp vào JSON_OBJECT:

~~~sql
SELECT JSON_OBJECT(
           first_name,
           last_name,
           salary
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Tên cột được dùng làm tên member và giá trị cột làm value. Cách này ngắn, nhưng tên key phụ thuộc tên cột và cách Oracle diễn giải tên đó. Với API công khai, chỉ định key tường minh thường ổn định hơn.

### 3.4. Dùng wildcard

Oracle hỗ trợ JSON_OBJECT(*) để lấy tất cả cột của hàng:

~~~sql
SELECT JSON_OBJECT(*)
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Các key được tạo từ tên cột, thường là chữ hoa. Có thể dùng alias theo cú pháp được hỗ trợ để giới hạn phạm vi cột.

Wildcard thuận tiện khi thử nghiệm hoặc tạo JSON nội bộ. Với API cần schema ổn định, wildcard có rủi ro: khi thêm cột vào bảng, JSON đầu ra cũng thay đổi mà không cần sửa câu SQL. Ngoài ra, có thể vô tình đưa cột nội bộ hoặc dữ liệu nhạy cảm vào response.

### 3.5. Object lồng object

Có thể gọi JSON_OBJECT bên trong một JSON_OBJECT khác:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE e.employee_id,
           'name' VALUE JSON_OBJECT(
               'first' VALUE e.first_name,
               'last'  VALUE e.last_name
           ),
           'job' VALUE JSON_OBJECT(
               'departmentId' VALUE e.department_id,
               'salary' VALUE e.salary
           )
       ) AS employee_json
FROM   json_demo_emp e
WHERE  e.employee_id = 101;
~~~

Kết quả có cấu trúc object lồng nhau. Oracle nhận diện kết quả từ hàm tạo JSON bên trong là JSON và lồng nó như một object, không tự biến nó thành chuỗi có dấu nháy kép.

### 3.6. Một hàng tạo một object, nhiều hàng tạo nhiều object

~~~sql
SELECT JSON_OBJECT(
           'id' VALUE employee_id,
           'name' VALUE first_name || ' ' || last_name
       ) AS employee_json
FROM   json_demo_emp;
~~~

Mỗi hàng nguồn tạo một object riêng. Nếu cần một tài liệu duy nhất chứa tất cả nhân viên, phải bọc JSON_OBJECT trong JSON_ARRAYAGG.

## 4. JSON_ARRAY — tạo JSON array

### 4.1. Array từ danh sách đối số

~~~sql
SELECT JSON_ARRAY(
           employee_id,
           first_name,
           salary
       ) AS employee_values
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Array giữ thứ tự đối số: ID, tên, lương. Khác object, array không có tên key cho từng phần tử.

### 4.2. Array chứa nhiều kiểu dữ liệu

~~~sql
SELECT JSON_ARRAY(
           101,
           'An Nguyen',
           2500,
           DATE '2022-01-10'
       ) AS sample_json
FROM   dual;
~~~

Oracle chuyển các kiểu SQL sang kiểu JSON tương ứng. NUMBER trở thành JSON number; chuỗi trở thành JSON string; DATE/TIMESTAMP được biểu diễn thành chuỗi ngày giờ theo định dạng ISO 8601.

### 4.3. Array chứa object và array con

~~~sql
SELECT JSON_ARRAY(
           JSON_OBJECT(
               'id' VALUE 101,
               'name' VALUE 'An'
           ),
           JSON_OBJECT(
               'id' VALUE 102,
               'name' VALUE 'Binh'
           )
       ) AS employees_json
FROM   dual;
~~~

Kết quả là array gồm hai object. Có thể lồng nhiều cấp để biểu diễn cấu trúc dữ liệu phức tạp.

### 4.4. Thứ tự phần tử

Với JSON_ARRAY, thứ tự phần tử chính là thứ tự biểu thức trong danh sách đối số:

~~~sql
SELECT JSON_ARRAY('A', 'B', 'C')
FROM dual;
~~~

Kết quả có thứ tự A, B, C. Nếu lấy dữ liệu từ nhiều hàng thì dùng JSON_ARRAYAGG và ORDER BY bên trong hàm.

## 5. Chuyển đổi kiểu SQL thành kiểu JSON

Các hàm generation chuyển giá trị SQL thành JSON value dựa trên kiểu dữ liệu đầu vào.

| Kiểu SQL | Dạng JSON thường tạo |
| --- | --- |
| NUMBER | JSON number, không có dấu nháy |
| VARCHAR2/NVARCHAR2 | JSON string, ký tự đặc biệt được escape |
| DATE/TIMESTAMP | JSON string theo dạng ngày giờ ISO 8601 |
| RAW/BLOB | JSON string biểu diễn byte dạng hexadecimal |
| NULL | JSON null hoặc bị bỏ qua theo NULL clause |
| CLOB | JSON string, trừ khi được đánh dấu FORMAT JSON |

Ví dụ:

~~~sql
SELECT JSON_OBJECT(
           'numberValue' VALUE 125,
           'textValue'   VALUE '125',
           'dateValue'   VALUE DATE '2025-04-30',
           'nullValue'   VALUE CAST(NULL AS VARCHAR2(10))
       )
FROM dual;
~~~

numberValue là số JSON 125, còn textValue là chuỗi JSON "125". Hai giá trị nhìn giống nhau nhưng khác kiểu.

### 5.1. Boolean trong Oracle 19c

Oracle 19c không có kiểu cột SQL BOOLEAN thông thường. Nếu muốn sinh JSON boolean từ điều kiện, có thể tạo literal true hoặc false rồi dùng FORMAT JSON:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'isHighSalary' VALUE
               CASE
                   WHEN salary >= 3000 THEN 'true'
                   ELSE 'false'
               END FORMAT JSON
       )
FROM   json_demo_emp;
~~~

Nếu bỏ FORMAT JSON, hai giá trị text true và false sẽ trở thành JSON string "true" và "false", không phải boolean true và false.

### 5.2. Escape ký tự tự động

Khi value là chuỗi SQL bình thường, Oracle tự escape ký tự cần thiết theo JSON. Ví dụ dấu nháy kép, ký tự xuống dòng và dấu gạch chéo ngược được xử lý để JSON đầu ra hợp lệ.

Không tự nối dấu nháy hoặc tự escape chuỗi trước khi đưa vào JSON_OBJECT/JSON_ARRAY. Escape hai lần có thể làm thay đổi nội dung mà client nhận được.

## 6. NULL ON NULL và ABSENT ON NULL

Hai cách xử lý NULL có ý nghĩa khác nhau:

- **NULL ON NULL:** giữ thuộc tính/phần tử và đưa giá trị JSON null.
- **ABSENT ON NULL:** bỏ thuộc tính hoặc phần tử có giá trị SQL NULL.

### 6.1. Mặc định của JSON_OBJECT

Với JSON_OBJECT và JSON_OBJECTAGG, mặc định là NULL ON NULL.

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'commission' VALUE commission
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Nếu commission là SQL NULL, output vẫn có key commission với value JSON null.

Muốn bỏ key:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'commission' VALUE commission
           ABSENT ON NULL
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Khi commission NULL, member đó không xuất hiện trong object.

### 6.2. Mặc định của JSON_ARRAY

Với JSON_ARRAY và JSON_ARRAYAGG, mặc định là ABSENT ON NULL.

~~~sql
SELECT JSON_ARRAY(
           employee_id,
           commission
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Vì commission NULL, phần tử đó bị bỏ qua theo mặc định. Nếu cần giữ vị trí và thể hiện NULL rõ ràng:

~~~sql
SELECT JSON_ARRAY(
           employee_id,
           commission
           NULL ON NULL
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Kết quả giữ phần tử thứ hai với JSON null.

### 6.3. Khác biệt có thể ảnh hưởng hợp đồng API

Giả sử client mong đợi array luôn có ba phần tử theo thứ tự ID, commission, salary. Nếu dùng mặc định ABSENT ON NULL, một phần tử NULL bị loại bỏ và vị trí phần tử sau đó thay đổi.

Với array có cấu trúc vị trí cố định, cân nhắc NULL ON NULL. Với object, ABSENT ON NULL có thể phù hợp nếu muốn phân biệt thuộc tính không được cung cấp với thuộc tính có giá trị null.

### 6.4. Empty string trong Oracle

Oracle SQL xử lý chuỗi rỗng VARCHAR2 như NULL. Vì vậy, không thể kỳ vọng chuỗi rỗng luôn được serialize thành JSON string rỗng "" khi đầu vào là VARCHAR2. CLOB rỗng được phân biệt với NULL trong một số ngữ cảnh JSON generation. Nếu hợp đồng API cần phân biệt empty string và null, hãy thiết kế kiểu lưu trữ/biểu diễn rõ ràng.

## 7. FORMAT JSON — đưa JSON fragment vào value

### 7.1. Chuỗi JSON bình thường được quote

Nếu đưa chuỗi JSON vào hàm generation mà không có FORMAT JSON, Oracle xem nó là dữ liệu chuỗi:

~~~sql
SELECT JSON_OBJECT(
           'payload' VALUE '{"active":true}'
       )
FROM dual;
~~~

Value payload trở thành JSON string chứa văn bản {"active":true}, không phải object lồng bên trong.

### 7.2. Dùng FORMAT JSON

Nếu chuỗi đầu vào thực sự là JSON hợp lệ và muốn nhúng nó như JSON fragment:

~~~sql
SELECT JSON_OBJECT(
           'payload' VALUE '{"active":true}' FORMAT JSON
       )
FROM dual;
~~~

Lúc này payload là một object JSON.

### 7.3. Không cần FORMAT JSON cho hàm tạo JSON lồng nhau

Khi value expression là JSON_OBJECT, JSON_ARRAY hoặc hàm SQL/JSON trả JSON, Oracle có thể nhận diện nó là JSON:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'profile' VALUE JSON_OBJECT(
               'firstName' VALUE first_name,
               'lastName' VALUE last_name
           )
       )
FROM   json_demo_emp
WHERE  employee_id = 101;
~~~

Không cần thêm FORMAT JSON sau JSON_OBJECT bên trong.

### 7.4. FORMAT JSON là lời cam kết về dữ liệu đầu vào

FORMAT JSON nói với Oracle rằng chuỗi đầu vào đã biểu diễn JSON. Không dùng nó cho text tùy ý từ người dùng hoặc dữ liệu chưa được xác thực.

Nếu cần nhận JSON từ bên ngoài:
- Xác thực dữ liệu bằng điều kiện IS JSON hoặc API validation phù hợp.
- Chỉ đánh dấu FORMAT JSON sau khi biết fragment hợp lệ.
- Dùng STRICT để yêu cầu kiểm tra JSON kết quả cuối.
- Không dùng FORMAT JSON như cách bỏ qua escape.

## 8. RETURNING — kiểm soát kiểu và kích thước đầu ra

### 8.1. Mặc định VARCHAR2(4000)

Trong Oracle 19c, các hàm JSON generation mặc định trả về VARCHAR2(4000). Nếu JSON vượt giới hạn, câu lệnh có thể lỗi vì kết quả quá lớn.

Với tài liệu có nhiều phần tử hoặc nhiều trường text, nên chủ động chỉ định kiểu trả về CLOB.

### 8.2. RETURNING CLOB

Ví dụ JSON_OBJECT:

~~~sql
SELECT JSON_OBJECT(
           'employeeId' VALUE employee_id,
           'firstName' VALUE first_name,
           'lastName' VALUE last_name,
           'salary' VALUE salary
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

Ví dụ JSON_ARRAYAGG:

~~~sql
SELECT JSON_ARRAYAGG(
           JSON_OBJECT(
               'id' VALUE employee_id,
               'name' VALUE first_name || ' ' || last_name
           )
           ORDER BY employee_id
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

CLOB phù hợp với tài liệu JSON lớn hơn giới hạn VARCHAR2 mặc định.

### 8.3. RETURNING VARCHAR2 với kích thước rõ ràng

Nếu biết output nhỏ, có thể chọn kích thước:

~~~sql
SELECT JSON_OBJECT(
           'id' VALUE employee_id,
           'name' VALUE first_name
           RETURNING VARCHAR2(1000)
       )
FROM   json_demo_emp;
~~~

Kích thước được tính theo BYTE hoặc CHAR tùy khai báo. Khi có Unicode, hãy hiểu rõ semantics của length và character set.

### 8.4. RETURNING BLOB

Một số hàm JSON generation hỗ trợ BLOB output, dùng character set AL32UTF8. BLOB hữu ích khi ứng dụng cần JSON ở dạng byte UTF-8 để truyền hoặc ghi file. Kiểm tra cú pháp RETURNING của từng hàm và release cụ thể; không giả định mọi aggregate function có cùng tập kiểu trả về.

### 8.5. Native JSON type và phiên bản

Oracle 19c thường biểu diễn kết quả JSON generation bằng VARCHAR2, CLOB hoặc BLOB. Kiểu dữ liệu JSON native được hỗ trợ ở các release mới hơn và có yêu cầu tương thích riêng. Không dùng RETURNING JSON trong môi trường 19c nếu database chưa hỗ trợ kiểu JSON native.

## 9. STRICT và WITH UNIQUE KEYS

### 9.1. STRICT

STRICT yêu cầu Oracle xác minh kết quả của hàm generation là JSON well-formed. Ví dụ:

~~~sql
SELECT JSON_OBJECT(
           'id' VALUE employee_id,
           'name' VALUE first_name
           RETURNING CLOB
           STRICT
       )
FROM   json_demo_emp;
~~~

Nếu đầu vào được đánh dấu FORMAT JSON nhưng không phải JSON hợp lệ, STRICT giúp phát hiện lỗi trong kết quả cuối.

Các hàm generation vốn được thiết kế để tạo JSON hợp lệ từ giá trị SQL. STRICT đặc biệt hữu ích khi đưa JSON fragment đã có vào kết quả.

### 9.2. WITH UNIQUE KEYS

JSON object nên có key duy nhất. Với object được tạo từ dữ liệu động hoặc JSON_OBJECTAGG, hai hàng có thể tạo cùng key.

Ví dụ mapping tên phòng ban sang ID:

~~~sql
SELECT JSON_OBJECTAGG(
           department_name VALUE department_id
           RETURNING CLOB
           WITH UNIQUE KEYS
       )
FROM   json_demo_dept;
~~~

WITH UNIQUE KEYS yêu cầu các key trong object kết quả là duy nhất. Nếu dữ liệu tạo ra key trùng, Oracle báo lỗi thay vì trả object có key lặp.

### 9.3. Xử lý duplicate key từ dữ liệu

Nếu key không duy nhất, hãy giải quyết trước khi aggregate:
- Chọn một hàng đại diện bằng ROW_NUMBER.
- Tổng hợp dữ liệu theo key trước.
- Dùng một key thực sự duy nhất như mã định danh.
- Tách nhóm dữ liệu thành nhiều object nếu nghiệp vụ cho phép.

Không dựa vào hành vi của client khi đọc JSON có key lặp. Các parser khác nhau có thể giữ key đầu, key cuối hoặc biểu diễn nhiều key.

## 10. JSON_ARRAYAGG — gom nhiều hàng thành array

### 10.1. Cú pháp cơ bản

~~~sql
SELECT JSON_ARRAYAGG(employee_id RETURNING CLOB) AS employee_ids
FROM   json_demo_emp;
~~~

Hàm aggregate lấy giá trị employee_id từ mỗi hàng và tạo một array duy nhất.

### 10.2. Array chứa object

Mẫu phổ biến là tạo một object cho mỗi hàng rồi gom các object thành array:

~~~sql
SELECT JSON_ARRAYAGG(
           JSON_OBJECT(
               'employeeId' VALUE employee_id,
               'firstName' VALUE first_name,
               'lastName' VALUE last_name,
               'salary' VALUE salary
           )
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employees_json
FROM   json_demo_emp;
~~~

Kết quả là một array gồm nhiều employee object.

### 10.3. ORDER BY phải nằm bên trong JSON_ARRAYAGG

Để xác định thứ tự phần tử, đặt ORDER BY trong lời gọi JSON_ARRAYAGG:

~~~sql
SELECT JSON_ARRAYAGG(
           employee_id
           ORDER BY employee_id DESC
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

ORDER BY ở ngoài SELECT không thay thế ORDER BY bên trong aggregate. Với JSON_ARRAYAGG, thứ tự phải tham chiếu cột; không dùng số thứ tự cột như ORDER BY 1 bên trong hàm.

Nếu cột sort không duy nhất, hãy thêm khóa phụ để kết quả ổn định:

~~~sql
JSON_ARRAYAGG(
    employee_id
    ORDER BY department_id, employee_id
    RETURNING CLOB
)
~~~

### 10.4. JSON_ARRAYAGG theo GROUP BY

Mỗi group tạo một array riêng:

~~~sql
SELECT department_id,
       JSON_ARRAYAGG(
           employee_id
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employee_ids
FROM   json_demo_emp
GROUP  BY department_id
ORDER  BY department_id;
~~~

Phòng ban 10, 20 và 30 có các array tương ứng. Phòng ban 40 không xuất hiện vì không có hàng nhân viên trong tập nguồn.

### 10.5. NULL trong JSON_ARRAYAGG

Mặc định ABSENT ON NULL:

~~~sql
SELECT JSON_ARRAYAGG(
           commission
           ORDER BY employee_id
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

Các commission NULL bị bỏ khỏi array. Nếu cần giữ phần tử null:

~~~sql
SELECT JSON_ARRAYAGG(
           commission
           ORDER BY employee_id
           NULL ON NULL
           RETURNING CLOB
       )
FROM   json_demo_emp;
~~~

Hãy chọn hành vi dựa trên hợp đồng dữ liệu của consumer.

### 10.6. Aggregate không có hàng

Nếu không có hàng đầu vào, kết quả aggregate có thể là SQL NULL. Nếu API yêu cầu array rỗng [], có thể dùng COALESCE:

~~~sql
SELECT COALESCE(
           (
               SELECT JSON_ARRAYAGG(
                          employee_id
                          ORDER BY employee_id
                          RETURNING CLOB
                      )
               FROM   json_demo_emp
               WHERE  department_id = -1
           ),
           TO_CLOB('[]')
       ) AS employee_ids
FROM dual;
~~~

Ở đây kết quả rỗng được thay bằng []. Nếu đưa giá trị này vào một JSON_OBJECT lớn hơn, hãy đánh dấu FORMAT JSON để Oracle nhúng nó như array, không phải string.

## 11. JSON_OBJECTAGG — gom nhiều hàng thành object

### 11.1. Cú pháp cơ bản

JSON_OBJECTAGG nhận key/value từ nhiều hàng:

~~~sql
SELECT JSON_OBJECTAGG(
           department_name VALUE department_id
           RETURNING CLOB
       ) AS department_map
FROM   json_demo_dept;
~~~

Kết quả là object có key là tên phòng ban và value là ID.

### 11.2. Dùng KEY để làm rõ ý nghĩa

~~~sql
SELECT JSON_OBJECTAGG(
           KEY department_name VALUE department_id
           RETURNING CLOB
       )
FROM   json_demo_dept;
~~~

KEY là từ khóa tùy chọn giúp câu lệnh dễ đọc hơn.

### 11.3. Object theo từng nhóm

~~~sql
SELECT location,
       JSON_OBJECTAGG(
           department_name VALUE department_id
           RETURNING CLOB
       ) AS departments_by_location
FROM   json_demo_dept
GROUP  BY location;
~~~

Mỗi location tạo một object riêng. Các hàng có location NULL cũng tạo một nhóm NULL theo quy tắc GROUP BY của Oracle.

### 11.4. Key phải có tính duy nhất trong object

Nếu nhiều hàng cùng tạo một key, object có thể chứa key trùng. Điều này gây mơ hồ cho consumer và có thể bị từ chối bởi parser hoặc validator.

Nếu nghiệp vụ cần map key/value, hãy bảo đảm key duy nhất trong mỗi nhóm hoặc dùng WITH UNIQUE KEYS để Oracle kiểm tra.

Ví dụ key dùng department_id:

~~~sql
SELECT JSON_OBJECTAGG(
           TO_CHAR(department_id) VALUE department_name
           RETURNING CLOB
           WITH UNIQUE KEYS
       )
FROM   json_demo_dept;
~~~

Key của JSON object là chuỗi. Với khóa số, dùng biểu diễn text ổn định; tránh format phụ thuộc NLS khi tạo key.

### 11.5. Thứ tự member của object không được bảo đảm

JSON object là tập hợp key/value; không dựa vào thứ tự member trong chuỗi output. Nếu consumer cần thứ tự, hãy dùng array và JSON_ARRAYAGG với ORDER BY.

## 12. Kết hợp các hàm để tạo JSON phân cấp

### 12.1. Một phòng ban và danh sách nhân viên

Có thể dùng subquery tương quan để tạo array nhân viên cho từng phòng ban:

~~~sql
SELECT JSON_OBJECT(
           'departmentId' VALUE d.department_id,
           'departmentName' VALUE d.department_name,
           'location' VALUE d.location,
           'employees' VALUE (
               SELECT JSON_ARRAYAGG(
                          JSON_OBJECT(
                              'employeeId' VALUE e.employee_id,
                              'name' VALUE e.first_name || ' ' || e.last_name,
                              'salary' VALUE e.salary
                          )
                          ORDER BY e.employee_id
                          RETURNING CLOB
                      )
               FROM   json_demo_emp e
               WHERE  e.department_id = d.department_id
           )
           RETURNING CLOB
       ) AS department_json
FROM   json_demo_dept d
ORDER  BY d.department_id;
~~~

Mỗi hàng phòng ban tạo một object. Trường employees là array các employee object. Oracle tối ưu truy vấn SQL/JSON và subquery; cách này thường tránh phải tải dữ liệu quan hệ về ứng dụng rồi tự dựng cấu trúc.

### 12.2. Array rỗng cho phòng ban không có nhân viên

Trong ví dụ trước, phòng ban 40 có subquery aggregate không có hàng, nên giá trị subquery là SQL NULL. Do JSON_OBJECT mặc định NULL ON NULL, trường employees sẽ là JSON null.

Nếu hợp đồng API yêu cầu array rỗng:

~~~sql
SELECT JSON_OBJECT(
           'departmentId' VALUE d.department_id,
           'departmentName' VALUE d.department_name,
           'employees' VALUE
               COALESCE(
                   (
                       SELECT JSON_ARRAYAGG(
                                  JSON_OBJECT(
                                      'employeeId' VALUE e.employee_id,
                                      'name' VALUE e.first_name || ' ' || e.last_name
                                  )
                                  ORDER BY e.employee_id
                                  RETURNING CLOB
                              )
                       FROM json_demo_emp e
                       WHERE e.department_id = d.department_id
                   ),
                   TO_CLOB('[]')
               ) FORMAT JSON
           RETURNING CLOB
       )
FROM   json_demo_dept d
ORDER  BY d.department_id;
~~~

COALESCE trả [] khi không có nhân viên. FORMAT JSON bảo đảm chuỗi [] được nhúng như array. Chỉ dùng FORMAT JSON với fragment được chương trình tạo hoặc đã xác thực.

### 12.3. Toàn bộ danh sách phòng ban thành một tài liệu

~~~sql
SELECT JSON_ARRAYAGG(
           JSON_OBJECT(
               'departmentId' VALUE d.department_id,
               'departmentName' VALUE d.department_name,
               'employeeCount' VALUE (
                   SELECT COUNT(*)
                   FROM json_demo_emp e
                   WHERE e.department_id = d.department_id
               )
           )
           ORDER BY d.department_id
           RETURNING CLOB
       ) AS departments_json
FROM   json_demo_dept d;
~~~

Đây là một JSON array chứa object của từng phòng ban. Scalar subquery cung cấp số nhân viên cho từng object.

### 12.4. Lồng nhiều cấp

Mẫu có thể mở rộng theo cấu trúc:

~~~text
[
  {
    "departmentId": 10,
    "employees": [
      {
        "employeeId": 101,
        "projects": [
          {"projectId": 1},
          {"projectId": 2}
        ]
      }
    ]
  }
]
~~~

Mỗi quan hệ một-nhiều có thể được tạo bằng một subquery aggregate lồng bên trong object của hàng cha. Khi lồng nhiều cấp, chú ý:
- Mỗi subquery phải tương quan bằng khóa đúng.
- Dùng ORDER BY bên trong từng JSON_ARRAYAGG nếu thứ tự quan trọng.
- Xác định chính sách NULL/array rỗng cho mỗi cấp.
- Dùng RETURNING CLOB ở các cấp có khả năng tạo output lớn.
- Tránh tạo bản sao dữ liệu do join nhiều quan hệ một-nhiều cùng lúc.

## 13. GROUP BY, HAVING và aggregate JSON

### 13.1. Một array cho mỗi phòng ban

~~~sql
SELECT department_id,
       JSON_ARRAYAGG(
           JSON_OBJECT(
               'id' VALUE employee_id,
               'name' VALUE first_name || ' ' || last_name
           )
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employees
FROM   json_demo_emp
GROUP  BY department_id;
~~~

GROUP BY quyết định mỗi group có một JSON array riêng.

### 13.2. Chỉ lấy group thỏa điều kiện

~~~sql
SELECT department_id,
       JSON_ARRAYAGG(
           employee_id
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employee_ids
FROM   json_demo_emp
GROUP  BY department_id
HAVING COUNT(*) >= 2;
~~~

HAVING lọc group sau khi aggregate. JSON_ARRAYAGG không thay thế COUNT hoặc các aggregate SQL khác; có thể dùng chung trong cùng SELECT.

### 13.3. Nhiều aggregate trong một truy vấn

~~~sql
SELECT department_id,
       COUNT(*) AS employee_count,
       AVG(salary) AS average_salary,
       JSON_ARRAYAGG(
           JSON_OBJECT(
               'id' VALUE employee_id,
               'salary' VALUE salary
           )
           ORDER BY employee_id
           RETURNING CLOB
       ) AS employees_json
FROM   json_demo_emp
GROUP  BY department_id;
~~~

Có thể trả dữ liệu quan hệ tổng hợp và JSON trong cùng một truy vấn. Hãy xem JSON là một biểu diễn bổ sung cho dữ liệu, không phải lý do để bỏ qua GROUP BY hoặc quy tắc cardinality.

## 14. JSON generation và dữ liệu JSON đã có

### 14.1. Cột VARCHAR2/CLOB chứa JSON

Trong Oracle 19c, ứng dụng thường lưu JSON text trong VARCHAR2, CLOB hoặc BLOB với constraint xác thực JSON:

~~~sql
CREATE TABLE json_demo_payload (
    payload_id NUMBER PRIMARY KEY,
    payload    CLOB,
    CONSTRAINT ck_json_demo_payload
        CHECK (payload IS JSON)
);
~~~

IS JSON kiểm tra nội dung cột theo quy tắc JSON. Có thể dùng STRICT tùy cú pháp và yêu cầu kiểm tra của phiên bản.

### 14.2. Nhúng cột JSON đã lưu

Nếu cột CLOB chứa JSON hợp lệ, có thể dùng FORMAT JSON:

~~~sql
SELECT JSON_OBJECT(
           'id' VALUE payload_id,
           'document' VALUE payload FORMAT JSON
           RETURNING CLOB
       )
FROM   json_demo_payload;
~~~

Nếu không có FORMAT JSON, payload được xem là chuỗi và sẽ được quote như JSON string.

### 14.3. Kết quả SQL/JSON function tự nhận diện

Nếu value expression là JSON_OBJECT, JSON_ARRAY hoặc một số hàm SQL/JSON khác, Oracle có thể nhận diện kết quả là JSON. Không cần gắn FORMAT JSON một cách máy móc sau mọi lời gọi hàm.

### 14.4. JSON_QUERY và FORMAT JSON

JSON_QUERY thường dùng để lấy một object/array từ JSON đã có. Khi đưa kết quả vào JSON_OBJECT hoặc JSON_ARRAY, Oracle có thể nhận diện đó là JSON. Hãy phân biệt:
- JSON_QUERY: truy vấn một fragment từ tài liệu JSON.
- JSON_OBJECT/JSON_ARRAY: tạo cấu trúc JSON mới.
- FORMAT JSON: khai báo một expression text đã là JSON fragment.

## 15. So sánh JSON_ARRAYAGG và JSON_OBJECTAGG

| Tiêu chí | JSON_ARRAYAGG | JSON_OBJECTAGG |
| --- | --- | --- |
| Cấu trúc | Array | Object |
| Đầu vào | Một expression cho mỗi hàng | Một key và một value cho mỗi hàng |
| Thứ tự | Có thể chỉ định ORDER BY trong hàm | Thứ tự member không được bảo đảm |
| NULL mặc định | ABSENT ON NULL | NULL ON NULL |
| Duplicate | Phần tử trùng được giữ | Key trùng cần được kiểm soát |
| Trường hợp dùng | Danh sách, collection, child rows | Map key/value, dictionary, lookup |
| Kết quả theo GROUP BY | Một array mỗi group | Một object mỗi group |

Chọn array khi cần bảo toàn nhiều phần tử, kể cả khi một giá trị lặp. Chọn object khi cần tra cứu theo key và key phải được quản lý duy nhất.

## 16. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Kết quả có dấu nháy kép quanh JSON con | Chuỗi JSON được xem là text thường | Dùng FORMAT JSON sau khi xác thực fragment |
| Output vượt giới hạn | Mặc định VARCHAR2(4000) | Dùng RETURNING CLOB phù hợp |
| Field biến mất khi NULL | ABSENT ON NULL đang áp dụng | Dùng NULL ON NULL nếu cần giữ field |
| Array thiếu phần tử NULL | Mặc định ABSENT ON NULL | Dùng NULL ON NULL để giữ vị trí |
| JSON_ARRAYAGG không đúng thứ tự | ORDER BY đặt ngoài aggregate hoặc thiếu sort | Đặt ORDER BY trong JSON_ARRAYAGG |
| JSON_OBJECTAGG có key lặp | Dữ liệu nguồn không unique theo key | Dedupe/group hoặc WITH UNIQUE KEYS |
| JSON trả về chuỗi "true" | Boolean text không có FORMAT JSON | Dùng literal true/false FORMAT JSON |
| JSON lồng nhau bị escape | Fragment text không được đánh dấu JSON | Dùng FORMAT JSON cho fragment đã validate |
| Không có hàng nhưng API cần [] | Aggregate trả SQL NULL | COALESCE với CLOB chứa [] và FORMAT JSON khi lồng |
| Driver báo bind variable sai | Dùng dấu hai chấm làm key/value separator | Dùng từ khóa VALUE |

### 16.1. JSON output bị quote hai lần

Ví dụ:

~~~sql
SELECT JSON_OBJECT(
           'child' VALUE '{"x":1}'
       )
FROM dual;
~~~

Kết quả là child chứa JSON string. Nếu muốn object con, dùng:

~~~sql
SELECT JSON_OBJECT(
           'child' VALUE '{"x":1}' FORMAT JSON
       )
FROM dual;
~~~

Chỉ dùng cách thứ hai nếu fragment thực sự là JSON hợp lệ.

### 16.2. ORA-40478 hoặc output quá lớn

Nếu kết quả vượt kích thước kiểu trả về, chỉ định CLOB thay cho VARCHAR2 mặc định. Cần kiểm tra kiểu trả về của từng hàm, đặc biệt khi nhiều tầng JSON được lồng nhau.

### 16.3. Duplicate key không rõ ràng

Nếu JSON_OBJECTAGG tạo key từ một cột không unique, hãy truy vấn dữ liệu trùng trước:

~~~sql
SELECT department_name,
       COUNT(*)
FROM   json_demo_dept
GROUP  BY department_name
HAVING COUNT(*) > 1;
~~~

Sửa dữ liệu hoặc định nghĩa key phù hợp trước khi tạo map.

## 17. Hiệu năng và thiết kế API

### 17.1. Tạo JSON trong database

SQL/JSON generation giúp:
- Giảm số lần round-trip giữa ứng dụng và database.
- Tránh tải nhiều result set về application chỉ để dựng cấu trúc JSON.
- Tận dụng optimizer và aggregate SQL.
- Tạo object/array lồng nhau trong một câu truy vấn.

Với cấu trúc parent-child, subquery JSON_ARRAYAGG có thể tạo child collection cho từng parent ngay trong database.

### 17.2. Chọn CLOB có chủ đích

CLOB tránh giới hạn VARCHAR2(4000) mặc định nhưng vẫn có chi phí tạo, truyền và tiêu thụ nội dung lớn. Không mặc định mọi JSON đều cần CLOB. Nếu response nhỏ, VARCHAR2 có thể đơn giản hơn.

### 17.3. Không tạo JSON_OBJECT(*) cho API lâu dài

Wildcard phụ thuộc cấu trúc bảng. Khi DBA thêm cột mới, API có thể thay đổi ngoài ý muốn. Chỉ định các key cần công khai để giữ hợp đồng dữ liệu ổn định và tránh vô tình lộ cột nội bộ.

### 17.4. Đặt ORDER BY đúng chỗ

JSON array có thể là một phần của hợp đồng API. Nếu client dựa vào thứ tự, hãy đặt ORDER BY trong JSON_ARRAYAGG và dùng khóa phụ duy nhất để kết quả ổn định.

### 17.5. Tránh join làm nhân bản hàng

Nếu một parent có nhiều child ở hai quan hệ một-nhiều, join cả hai bảng con cùng lúc có thể tạo tích số hàng và làm các phần tử JSON bị lặp. Hãy tạo từng collection bằng subquery aggregate riêng, hoặc aggregate từng quan hệ trước khi join.

### 17.6. Đừng nối JSON thủ công

Tự nối chuỗi JSON dễ sai khi dữ liệu chứa dấu nháy, newline, ký tự điều khiển hoặc Unicode. Dùng JSON_OBJECT/JSON_ARRAY để Oracle xử lý serialization và escaping.

## 18. Quy trình xây dựng JSON từ dữ liệu quan hệ

1. Xác định schema JSON mong muốn: object, array, key, kiểu value.
2. Xác định cấp dữ liệu: một hàng, nhiều hàng hay một nhóm.
3. Dùng JSON_OBJECT cho object và JSON_ARRAY cho array theo đối số.
4. Dùng JSON_ARRAYAGG hoặc JSON_OBJECTAGG khi gom nhiều hàng.
5. Xác định NULL ON NULL hay ABSENT ON NULL cho từng cấp.
6. Đặt ORDER BY trong JSON_ARRAYAGG nếu thứ tự có ý nghĩa.
7. Dùng FORMAT JSON chỉ với fragment đã là JSON hợp lệ.
8. Chọn RETURNING CLOB nếu kết quả có thể vượt VARCHAR2(4000).
9. Dùng STRICT và WITH UNIQUE KEYS khi cần kiểm tra mạnh hơn.
10. Kiểm tra dữ liệu rỗng, key trùng, NULL, Unicode và payload lớn.
11. Kiểm thử JSON cuối bằng parser/validator phía consumer.
12. Giữ tên key và kiểu dữ liệu ổn định như một hợp đồng API.

## 19. Bài thực hành tổng hợp

Sử dụng hai bảng JSON_DEMO_DEPT và JSON_DEMO_EMP ở mục 2.

### Bài 1 — JSON_OBJECT cơ bản

Tạo object cho mỗi nhân viên gồm employeeId, firstName, lastName và salary. Kiểm tra kiểu JSON của salary.

### Bài 2 — JSON_OBJECT với key tự đặt

Dùng camelCase cho tên key. So sánh với cách truyền tên cột trực tiếp.

### Bài 3 — JSON_OBJECT(*)

Sinh object bằng wildcard. Thêm một cột demo vào bảng và quan sát JSON output thay đổi ra sao.

### Bài 4 — JSON_ARRAY

Tạo array gồm employee ID, tên và lương. Đổi thứ tự đối số và quan sát thứ tự phần tử.

### Bài 5 — Kiểu dữ liệu

Tạo object có NUMBER, VARCHAR2, DATE và NULL. Xác định trường nào là JSON number, JSON string và JSON null.

### Bài 6 — NULL ON NULL và ABSENT ON NULL

Tạo hai object và hai array từ hàng có commission NULL. So sánh số member/phần tử.

### Bài 7 — FORMAT JSON

Đưa chuỗi {"active":true} vào JSON_OBJECT có và không có FORMAT JSON. Giải thích sự khác biệt giữa object con và string.

### Bài 8 — JSON_ARRAYAGG

Tạo array employee ID theo thứ tự tăng dần và giảm dần. Đặt ORDER BY bên trong aggregate.

### Bài 9 — JSON_OBJECTAGG

Tạo map department name sang department ID. Thử dữ liệu key trùng trong bảng test và kiểm tra WITH UNIQUE KEYS.

### Bài 10 — GROUP BY

Tạo một JSON array nhân viên cho mỗi department_id. Dùng HAVING để chỉ lấy phòng ban có từ hai nhân viên.

### Bài 11 — Nested JSON

Tạo object phòng ban có field employees là array object nhân viên. Bảo đảm phòng ban không có nhân viên trả [] thay vì null.

### Bài 12 — RETURNING CLOB

Tạo JSON array lớn bằng nhiều hàng demo. So sánh kiểu trả về mặc định với RETURNING CLOB.

### Bài 13 — STRICT và JSON constraint

Lưu JSON vào cột CLOB có CHECK (payload IS JSON). Thử insert chuỗi JSON hợp lệ và chuỗi sai định dạng.

### Bài 14 — Thiết kế API

Thiết kế JSON response cho đơn hàng gồm orderId, customer, orderDate và items array. Mỗi item có productId, quantity, unitPrice và lineTotal. Xác định chính sách NULL, thứ tự items và kiểu trả về.

## 20. Tài liệu Oracle tham khảo

- [Oracle Database 19c JSON Developer's Guide — Generation of JSON Data](https://docs.oracle.com/en/database/oracle/oracle-database/19/adjsn/generation.html): tổng quan JSON_OBJECT, JSON_ARRAY, JSON_OBJECTAGG, JSON_ARRAYAGG, kiểu đầu vào, NULL handling và nested JSON.
- [Oracle Database 19c SQL Language Reference — JSON_OBJECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_OBJECT.html): cú pháp object, key/value, wildcard, RETURNING, STRICT và unique keys.
- [Oracle Database 19c SQL Language Reference — JSON_ARRAY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_ARRAY.html): cú pháp array và NULL handling.
- [Oracle Database 19c SQL Language Reference — JSON_ARRAYAGG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_ARRAYAGG.html): aggregate array và ORDER BY bên trong hàm.
- [Oracle Database 19c SQL Language Reference — JSON_OBJECTAGG](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/JSON_OBJECTAGG.html): aggregate object, key/value và WITH UNIQUE KEYS.

JSON_OBJECT và JSON_ARRAY tạo cấu trúc từ các biểu thức; JSON_ARRAYAGG và JSON_OBJECTAGG gom dữ liệu từ nhiều hàng. Khi xây JSON phân cấp, hãy lồng các hàm generation và subquery aggregate theo quan hệ cha-con. Xác định rõ NULL handling, dùng ORDER BY bên trong JSON_ARRAYAGG, chọn RETURNING CLOB cho tài liệu lớn, và chỉ dùng FORMAT JSON với fragment đã được xác thực. **Dùng các hàm SQL/JSON để tạo JSON theo cấu trúc dữ liệu, thay vì nối chuỗi thủ công.**
