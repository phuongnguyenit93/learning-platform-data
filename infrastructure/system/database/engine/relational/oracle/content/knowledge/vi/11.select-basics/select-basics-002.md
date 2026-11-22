# Chọn cột, biểu thức, bí danh và sử dụng DUAL trong Oracle Database

Lệnh `SELECT` là điểm khởi đầu khi truy vấn dữ liệu từ **Oracle Database**. Ngay trong câu `SELECT` cơ bản, người viết SQL phải phân biệt **chọn cột nào để hiển thị**, **tạo cột kết quả từ biểu thức**, **đặt tên cho cột kết quả bằng bí danh (alias)** và **lấy kết quả của biểu thức không cần một bảng nghiệp vụ**, thường thông qua bảng đặc biệt `DUAL`.

Ví dụ, cùng một bảng nhân viên có các cột `EMP_ID`, `FULL_NAME`, `BASE_SALARY` và `BONUS`, ta có thể:

- Chỉ chọn mã và tên nhân viên.
- Tính lương năm từ lương tháng.
- Gộp hai giá trị số và xử lý `NULL`.
- Đổi tên hiển thị của cột thành `ANNUAL_SALARY` hoặc `"Lương năm"`.
- Thử biểu thức `2 + 3`, `SYSDATE` hoặc hàm chuỗi mà không cần lấy dữ liệu từ bảng nhân viên.

Những kỹ năng này là nền tảng cho báo cáo, truy vấn trong ứng dụng Java/JDBC, các phép tổng hợp, biểu thức điều kiện và truy vấn phức tạp hơn. Bài học tập trung vào **cú pháp và ngữ nghĩa Oracle SQL**, đồng thời cung cấp bài lab để thực hành từ đầu.

## 1. Cấu trúc SELECT cơ bản

Một câu truy vấn Oracle thường có dạng:

~~~sql
SELECT expression_1 [AS alias_1],
       expression_2 [AS alias_2],
       ...
FROM table_or_view
WHERE condition
ORDER BY expression_or_alias;
~~~

Đối với câu đơn giản, phần trọng tâm là:

~~~sql
SELECT column_name
FROM table_name;
~~~

Ý nghĩa:

| Thành phần | Chức năng |
|---|---|
| `SELECT` | Khai báo danh sách giá trị/cột mà câu truy vấn trả về |
| `column_name` | Cột dữ liệu lấy từ bảng/view |
| `expression` | Phép toán, literal, hàm hoặc biểu thức tạo giá trị kết quả |
| `AS alias` | Đặt tên cột trong tập kết quả; từ khóa `AS` có thể bỏ qua đối với **column alias** |
| `FROM` | Xác định nguồn dòng dữ liệu |
| `WHERE` | Lọc những dòng nào đủ điều kiện |
| `ORDER BY` | Yêu cầu thứ tự kết quả |

Trong các câu truy vấn nâng cao còn có `JOIN`, `GROUP BY`, `HAVING`, `FETCH FIRST` và các dạng biểu thức khác. Chưa cần dùng hết để hiểu cách chọn cột và bí danh.

### 1.1 Chọn cột khác lọc dòng

Giả sử bảng `STAFF` có 1.000 dòng và 10 cột.

~~~sql
SELECT emp_id, full_name
FROM staff;
~~~

Câu trên chọn **hai cột** để đưa vào kết quả; nó không yêu cầu chỉ lấy hai dòng. Nếu không có điều kiện khác, truy vấn có thể trả về 1.000 dòng, mỗi dòng có hai giá trị.

~~~sql
SELECT emp_id, full_name
FROM staff
WHERE dept_code = 'IT';
~~~

Câu thứ hai vẫn chỉ đưa ra **hai cột**, nhưng `WHERE` loại những dòng không thuộc phòng IT.

Trong ngôn ngữ quan hệ, thao tác chọn tập thuộc tính được gọi là **projection (chiếu)**, còn việc giữ lại dòng đáp ứng điều kiện thường gọi là **selection/filtering**. Dù tên `SELECT` dễ khiến nhầm lẫn, hai khái niệm không giống nhau:

~~~text
Bảng nguồn: nhiều dòng, nhiều cột
       |
       | WHERE: chọn các dòng phù hợp
       v
Các dòng còn lại
       |
       | SELECT list: xác định cột/biểu thức đầu ra
       v
Tập kết quả cuối cùng
~~~

Đây là sơ đồ ý niệm về kết quả. **Oracle optimizer có thể thực hiện các phép toán vật lý theo thứ tự khác** để tối ưu truy vấn; không nên coi sơ đồ là thứ tự cố định mà engine luôn đọc từng bước.

### 1.2 Câu SELECT trả về những gì?

Một tập kết quả (*result set*) gồm:

- **Số cột**, thứ tự cột và tên/nhãn cột theo danh sách SELECT.
- **Kiểu dữ liệu** của từng biểu thức, ví dụ `NUMBER`, `VARCHAR2`, `DATE` hoặc `TIMESTAMP`.
- **Các dòng** thỏa điều kiện truy vấn.

Các nhãn cột được hiển thị bởi SQL Developer, SQL*Plus, SQLcl hoặc JDBC. Tên hiển thị không nhất thiết giống tên cột vật lý trong bảng, vì biểu thức có thể có alias riêng.

## 2. Chọn một cột hoặc nhiều cột

### 2.1 Một cột

~~~sql
SELECT full_name
FROM staff;
~~~

Kết quả giả định:

| FULL_NAME |
|---|
| An Nguyen |
| Binh Tran |
| Chi Le |

### 2.2 Nhiều cột, phân cách bằng dấu phẩy

~~~sql
SELECT emp_id,
       full_name,
       dept_code,
       base_salary
FROM staff;
~~~

Các biểu thức trong SELECT list được ngăn cách bằng **dấu phẩy**. Thứ tự trong danh sách SELECT quyết định thứ tự các cột được trình bày.

Không thêm dấu phẩy sau cột cuối cùng trước `FROM`:

~~~sql
-- Ví dụ sai cú pháp:
SELECT emp_id,
       full_name,
FROM staff;
~~~

Lỗi kiểu này có thể được Oracle báo là cú pháp SELECT chưa hoàn chỉnh hoặc từ khóa đặt sai chỗ. Cách sửa là bỏ dấu phẩy cuối.

### 2.3 Chọn cùng một cột nhiều lần

Oracle cho phép dùng một cột trong nhiều biểu thức:

~~~sql
SELECT base_salary,
       base_salary AS original_salary,
       base_salary * 12 AS annual_salary
FROM staff;
~~~

Cột vật lý `BASE_SALARY` không được nhân bản trong bảng. Chỉ **tập kết quả** gồm nhiều biểu thức tham chiếu cùng dữ liệu nguồn.

### 2.4 Chọn tất cả cột bằng dấu *

~~~sql
SELECT *
FROM staff;
~~~

`*` là ký hiệu mở rộng các cột của nguồn dữ liệu theo ngữ nghĩa SELECT, không phải phép nhân trong ngữ cảnh này. Trong SQL Developer, câu trên thường tiện khi khám phá bảng.

Tuy nhiên, với truy vấn ứng dụng hoặc báo cáo ổn định, nên liệt kê đúng cột cần:

~~~sql
SELECT emp_id,
       full_name,
       dept_code
FROM staff;
~~~

Lý do:

1. **Dễ đọc hợp đồng dữ liệu:** client biết rõ những cột dự kiến.
2. **Giảm dữ liệu truyền:** tránh lấy cột lớn hoặc nhạy cảm không cần dùng.
3. **Giảm phụ thuộc schema:** khi bảng thêm cột, kết quả của `SELECT *` thay đổi.
4. **Thuận lợi cho một số kế hoạch truy cập:** chỉ lấy các cột trong index có thể giúp optimizer chọn cách truy cập thích hợp.
5. **Tránh phụ thuộc vào thứ tự vật lý:** việc ứng dụng ánh xạ cột theo vị trí với `SELECT *` dễ hỏng khi cấu trúc thay đổi.

Không có nghĩa `SELECT *` luôn kém hiệu quả trong mọi trường hợp; nó phù hợp để xem nhanh dữ liệu hoặc kiểm tra bảng trong môi trường an toàn. Nhưng trong API/DAO và SQL dùng lâu dài, danh sách cột tường minh thường tốt hơn.

## 3. Dùng table alias và tiền tố tên cột

Khi truy vấn nhiều bảng, có thể có các cột trùng tên như `ID`, `NAME` hoặc `CREATED_AT`. Dùng **table alias** giúp SQL rõ ràng hơn:

~~~sql
SELECT s.emp_id,
       s.full_name,
       s.dept_code
FROM staff s;
~~~

`s` là bí danh của bảng `STAFF` trong phạm vi câu truy vấn. Tên `s.emp_id` xác định cột `EMP_ID` từ nguồn `s`.

### 3.1 Chọn tất cả cột của một nguồn

~~~sql
SELECT s.*
FROM staff s;
~~~

`s.*` lấy các cột của nguồn `s`. Trong truy vấn có JOIN, `s.*` và `d.*` giúp phân biệt muốn lấy tất cả cột từ phía nào.

Ví dụ giả định có bảng `DEPARTMENTS`:

~~~sql
SELECT s.emp_id,
       s.full_name,
       d.dept_name
FROM staff s
JOIN departments d
  ON d.dept_code = s.dept_code;
~~~

Ở đây `s` và `d` là **table aliases**, còn `EMP_ID`, `FULL_NAME`, `DEPT_NAME` là **columns**. Nếu hai bảng cùng có `DEPT_CODE` thì cần chỉ rõ `s.dept_code` hay `d.dept_code` trong các vị trí có thể gây mơ hồ.

### 3.2 Phân biệt cú pháp alias cho cột và bảng

Với **column alias**, cả hai cách đều hợp lệ:

~~~sql
SELECT base_salary AS salary
FROM staff;

SELECT base_salary salary
FROM staff;
~~~

Với **table alias** trong Oracle SQL, cách quen thuộc là:

~~~sql
SELECT s.emp_id
FROM staff s;
~~~

Không dùng `FROM staff AS s` theo thói quen ở các hệ quản trị khác khi muốn viết SQL Oracle có tính tương thích rộng. Một số cú pháp/phiên bản có thay đổi theo thời gian; với các phiên bản Oracle truyền thống, đặt table alias **không kèm `AS`** là quy ước an toàn.

## 4. Biểu thức trong SELECT list

Một **biểu thức** (expression) là phép tính hoặc phép tạo giá trị. Không bắt buộc mỗi mục trong SELECT phải là tên cột; nó có thể là:

- Một **literal** như `100` hoặc `'ACTIVE'`.
- Một phép toán `base_salary * 12`.
- Một phép nối chuỗi `'Employee: ' || full_name`.
- Một hàm `UPPER(full_name)`, `ROUND(...)` hoặc `TO_CHAR(...)`.
- Một biểu thức điều kiện `CASE ... END`.
- Một biểu thức kết hợp nhiều cột, hàm và literal.

### 4.1 Literal số và chuỗi

~~~sql
SELECT emp_id,
       'ACTIVE' AS sample_status,
       100 AS sample_score
FROM staff;
~~~

Giá trị `'ACTIVE'` và `100` là hằng trong câu truy vấn, nên mỗi dòng kết quả có cùng các giá trị đó. Đây không phải hai cột mới được thêm vào bảng.

Trong Oracle, literal chuỗi nằm trong **dấu nháy đơn**; nháy kép dùng cho identifier được đặt trong dấu nháy, chẳng hạn tên alias.

Ví dụ:

~~~sql
SELECT 'It''s Oracle SQL' AS message
FROM dual;
~~~

Dùng hai dấu nháy đơn liên tiếp `''` để biểu diễn một dấu apostrophe trong chuỗi.

### 4.2 Biểu thức số học

~~~sql
SELECT emp_id,
       base_salary,
       base_salary * 12 AS annual_base_salary
FROM staff;
~~~

Oracle tính biểu thức tương ứng với mỗi dòng. Một bảng có lương tháng 15.000.000 sẽ đưa ra biểu thức lương năm 180.000.000, nếu giá trị `BASE_SALARY` được hiểu là số tiền theo đúng quy ước dữ liệu.

Một số toán tử thường dùng:

| Toán tử | Ý nghĩa | Ví dụ |
|---|---|---|
| `+` | Cộng | `base_salary + bonus` |
| `-` | Trừ | `base_salary - 100000` |
| `*` | Nhân | `base_salary * 12` |
| `/` | Chia | `base_salary / 12` |
| `( )` | Nhóm/đổi thứ tự tính | `(base_salary + bonus) * 12` |

Ví dụ dễ nhầm về thứ tự phép toán:

~~~sql
SELECT 10 + 2 * 5 AS default_precedence,
       (10 + 2) * 5 AS parenthesized
FROM dual;
~~~

Kết quả lần lượt là `20` và `60`. Phép nhân được ưu tiên hơn phép cộng theo quy tắc toán học thông thường. Khi biểu thức nghiệp vụ dài, dùng ngoặc để tránh hiểu nhầm.

### 4.3 Chia cho 0

Phép chia có mẫu số bằng 0 có thể dẫn đến lỗi `ORA-01476: divisor is equal to zero`. Khi mẫu số đến từ dữ liệu, có thể dùng `NULLIF`:

~~~sql
SELECT sales_amount,
       order_count,
       sales_amount / NULLIF(order_count, 0) AS average_amount
FROM daily_summary;
~~~

Nếu `ORDER_COUNT = 0`, `NULLIF(order_count,0)` trả về NULL và kết quả chia là NULL thay vì chia cho 0. Đây là một **chính sách xử lý**; nếu nghiệp vụ muốn hiển thị 0 hoặc thông báo lỗi, phải quyết định rõ thay vì tự coi mọi phép chia thiếu dữ liệu là 0.

### 4.4 Kết hợp nhiều cột trong một biểu thức

~~~sql
SELECT emp_id,
       base_salary,
       bonus,
       (base_salary + NVL(bonus, 0)) * 12 AS annual_income_estimate
FROM staff;
~~~

Ví dụ coi `BONUS` là khoản hàng tháng và thay NULL bằng 0. Nếu bonus được trả theo năm hoặc theo kỳ khác thì công thức phải đổi. SQL chỉ tính theo biểu thức người viết yêu cầu, không tự hiểu chính sách lương.

## 5. NULL trong biểu thức: không giống số 0

`NULL` biểu thị **không có giá trị được biết/được cung cấp** trong ngữ nghĩa SQL. Nó không đồng nghĩa số 0 hoặc chuỗi rỗng trong mọi ngữ cảnh.

### 5.1 NULL làm thay đổi kết quả phép toán

Giả sử:

~~~text
BASE_SALARY = 15,000,000
BONUS       = NULL
~~~

Với biểu thức:

~~~sql
SELECT base_salary + bonus AS gross_salary
FROM staff;
~~~

Kết quả biểu thức của dòng đó là `NULL` vì một toán hạng không có giá trị số.

Nếu nghiệp vụ xác nhận rằng **bonus không khai báo được coi là 0**, dùng:

~~~sql
SELECT base_salary + NVL(bonus, 0) AS gross_salary
FROM staff;
~~~

`NVL(expr, replacement)` là hàm Oracle thay NULL bằng giá trị dự phòng. Không nên áp dụng `NVL` mù quáng trong mọi trường hợp: thiếu dữ liệu lương có thể cần xử lý ngoại lệ thay vì biến thành 0.

### 5.2 COALESCE

`COALESCE` chọn biểu thức không NULL đầu tiên:

~~~sql
SELECT emp_id,
       COALESCE(bonus, 0) AS bonus_for_calculation
FROM staff;
~~~

Với nhiều nguồn dự phòng:

~~~sql
SELECT COALESCE(preferred_email, work_email, 'not-provided') AS contact_email
FROM contacts;
~~~

Cần xem khả năng chuyển kiểu giữa các đối số. Không nên trộn số, ngày và chuỗi có ý nghĩa khác nhau trong một biểu thức rồi dựa vào ép kiểu ngầm.

### 5.3 So sánh NULL

Không dùng `= NULL` để tìm giá trị thiếu:

~~~sql
-- Không đúng cách kiểm tra NULL:
WHERE bonus = NULL
~~~

Trong logic ba giá trị của SQL, so sánh như vậy không cho TRUE. Dùng:

~~~sql
WHERE bonus IS NULL
~~~

và:

~~~sql
WHERE bonus IS NOT NULL
~~~

### 5.4 Chuỗi rỗng trong Oracle

Oracle hiện có hành vi đặc thù: với kiểu chuỗi ký tự có độ dài 0, `''` thường được xử lý như NULL. Vì vậy đừng dựa vào việc cột `VARCHAR2` luôn phân biệt được **chuỗi rỗng** và **NULL** như một số ngôn ngữ lập trình.

Khi nối chuỗi, Oracle có những quy tắc riêng với NULL và toán tử `||`. Nếu cần hiển thị giá trị dự phòng rõ ràng, dùng `NVL`/`COALESCE` thay vì suy từ hành vi nối NULL của mọi hệ quản trị.

## 6. Nối chuỗi và hàm xử lý văn bản

Oracle dùng toán tử `||` để nối các biểu thức chuỗi:

~~~sql
SELECT 'Employee: ' || full_name AS employee_label
FROM staff;
~~~

Kết quả ví dụ: `Employee: An Nguyen`.

**Đừng dùng dấu `+` để nối chuỗi theo thói quen ở một số ngôn ngữ hoặc hệ quản trị khác.** Trong Oracle, `+` có ngữ nghĩa số học; `||` là toán tử nối chuỗi.

### 6.1 Ghép tên hoặc mã hiển thị

~~~sql
SELECT emp_id,
       full_name || ' (' || dept_code || ')' AS employee_display
FROM staff;
~~~

Một dòng có thể hiển thị:

~~~text
An Nguyen (IT)
~~~

### 6.2 Hàm UPPER, LOWER, INITCAP, TRIM

~~~sql
SELECT full_name,
       UPPER(full_name) AS uppercase_name,
       LOWER(full_name) AS lowercase_name,
       INITCAP(full_name) AS title_like_name,
       TRIM(full_name) AS trimmed_name
FROM staff;
~~~

Các hàm văn bản sử dụng quy tắc chữ và charset/NLS liên quan. `INITCAP` không phải công cụ chuẩn hóa tên người cho mọi ngôn ngữ, và `UPPER` không làm phép so sánh văn bản trở nên đúng với mọi locale nếu hệ thống yêu cầu quy tắc đối chiếu ngôn ngữ đặc thù.

### 6.3 Dùng biểu thức định dạng giá trị

~~~sql
SELECT emp_id,
       'ID=' || TO_CHAR(emp_id) AS employee_key
FROM staff;
~~~

`TO_CHAR` chuyển giá trị sang chuỗi theo định dạng Oracle. Với số và ngày trong ứng dụng đa quốc gia, nên nêu format model/NLS rõ ràng nếu xuất ra hợp đồng văn bản cố định.

## 7. Hàm và biểu thức CASE trong SELECT

Không phải mọi cột kết quả đều tính từ toán tử số học. Ta có thể dùng hàm hoặc `CASE` để hiển thị trạng thái.

### 7.1 ROUND và TRUNC

~~~sql
SELECT 10 / 3 AS raw_value,
       ROUND(10 / 3, 2) AS rounded_value,
       TRUNC(10 / 3, 2) AS truncated_value
FROM dual;
~~~

`ROUND(number, 2)` làm tròn đến hai chữ số thập phân, còn `TRUNC(number, 2)` bỏ các chữ số sau vị trí chỉ định mà không làm tròn.

Ví dụ trên hữu ích vì có thể dùng `DUAL` để kiểm tra phép toán mà không cần dữ liệu bảng nghiệp vụ.

### 7.2 CASE: tạo giá trị tùy điều kiện

~~~sql
SELECT emp_id,
       full_name,
       base_salary,
       CASE
           WHEN base_salary >= 20000000 THEN 'HIGH'
           WHEN base_salary >= 12000000 THEN 'MEDIUM'
           ELSE 'LOW'
       END AS salary_band
FROM staff;
~~~

`CASE ... END` là **biểu thức trả về một giá trị**. Nó không sửa `BASE_SALARY` hay tạo cột `SALARY_BAND` trong bảng.

Điểm cần chú ý:

- Các điều kiện `WHEN` được xét theo thứ tự biểu thức.
- Với mẫu trên, dòng đạt 20 triệu khớp nhánh `HIGH` trước nhánh `MEDIUM`.
- `ELSE` cho giá trị khi không nhánh nào khớp.
- Nếu bỏ `ELSE` và không có nhánh phù hợp, biểu thức có thể trả NULL.

### 7.3 Biểu thức điều kiện cho cột có NULL

~~~sql
SELECT emp_id,
       bonus,
       CASE
           WHEN bonus IS NULL THEN 'NOT_RECORDED'
           WHEN bonus = 0 THEN 'ZERO'
           ELSE 'HAS_BONUS'
       END AS bonus_state
FROM staff;
~~~

Ví dụ này phân biệt **chưa ghi nhận bonus** và **bonus bằng 0**, điều mà dùng `NVL(bonus,0)` có thể che mất nếu nghiệp vụ cần giữ sự khác nhau.

### 7.4 Hàm ngày giờ

~~~sql
SELECT SYSDATE AS database_now,
       SYSTIMESTAMP AS database_timestamp,
       CURRENT_DATE AS session_current_date
FROM dual;
~~~

`SYSDATE` trả về Oracle DATE dựa trên đồng hồ hệ thống database; `SYSTIMESTAMP` có phần giây và thông tin timezone; `CURRENT_DATE` trả về DATE theo session timezone. Đừng giả định những hàm này luôn hiển thị cùng giờ ở môi trường có session timezone khác máy chủ.

## 8. Bí danh cột (column alias)

Column alias là **tên/nhãn của biểu thức trong tập kết quả**. Nó giúp SQL dễ đọc và giúp ứng dụng, báo cáo hoặc màn hình hiển thị cột có ý nghĩa.

### 8.1 Dùng AS

~~~sql
SELECT emp_id AS employee_id,
       full_name AS employee_name,
       base_salary * 12 AS annual_salary
FROM staff;
~~~

Ở đây `EMPLOYEE_ID`, `EMPLOYEE_NAME` và `ANNUAL_SALARY` là **column aliases**, không phải cột mới trong bảng.

### 8.2 Không dùng AS cũng được

~~~sql
SELECT emp_id employee_id,
       full_name employee_name
FROM staff;
~~~

Oracle chấp nhận cách này, nhưng với biểu thức dài, thêm `AS` thường làm ranh giới giữa biểu thức và alias rõ hơn.

### 8.3 Alias với dấu nháy kép

Để nhãn có khoảng trắng, dấu câu hoặc chữ viết thường, dùng **double-quoted identifier**:

~~~sql
SELECT emp_id AS "Mã nhân viên",
       full_name AS "Họ tên",
       base_salary * 12 AS "Lương năm"
FROM staff;
~~~

Khi được hiển thị trong công cụ hỗ trợ Unicode, các tiêu đề có thể là `Mã nhân viên`, `Họ tên` và `Lương năm`.

Quy tắc quan trọng:

- **Dấu nháy đơn `'...'`** biểu diễn **literal chuỗi**.
- **Dấu nháy kép `"..."`** bao quanh **tên identifier**, bao gồm column alias.
- Tên không đặt trong nháy kép thường được Oracle xử lý không phân biệt hoa/thường ở mức identifier.
- Tên đặt trong nháy kép giữ chính xác cách viết và thường cần tham chiếu bằng cách viết tương ứng.

Ví dụ:

~~~sql
SELECT base_salary * 12 AS "Annual Salary"
FROM staff
ORDER BY "Annual Salary" DESC;
~~~

Trong `ORDER BY`, cần viết đúng alias có khoảng trắng và chữ hoa/thường như đã khai báo.

### 8.4 Alias không làm thay đổi schema

~~~sql
SELECT base_salary AS monthly_salary
FROM staff;
~~~

Không đổi tên cột `BASE_SALARY` trong bảng thành `MONTHLY_SALARY`. Một câu khác truy vấn `STAFF` vẫn dùng `BASE_SALARY` như cũ.

Muốn đổi tên cột vật lý là tác vụ DDL riêng, cần quyền và đánh giá tác động đối với các ứng dụng đang sử dụng schema. Không làm DDL chỉ để thay tiêu đề báo cáo.

### 8.5 Alias nên mô tả đơn vị và ý nghĩa

So sánh:

~~~sql
SELECT base_salary * 12 AS x
FROM staff;
~~~

và:

~~~sql
SELECT base_salary * 12 AS annual_base_salary
FROM staff;
~~~

Alias thứ hai rõ hơn: nó là **lương cơ bản năm**, không tự động là thu nhập thực lĩnh hay tổng thu nhập nếu còn thưởng/phụ cấp/khấu trừ. Alias rõ nghĩa giúp giảm lỗi đọc kết quả ở ứng dụng và dashboard.

## 9. Phạm vi sử dụng alias: ORDER BY, WHERE và subquery

Một điểm dễ nhầm là nghĩ alias vừa tạo trong `SELECT` có thể dùng **ở mọi clause** của cùng truy vấn.

### 9.1 ORDER BY có thể dùng column alias

~~~sql
SELECT emp_id,
       full_name,
       base_salary * 12 AS annual_salary
FROM staff
ORDER BY annual_salary DESC;
~~~

`ORDER BY` có thể tham chiếu tên alias `ANNUAL_SALARY` của SELECT list. Trong SQL Developer hoặc SQL*Plus, kết quả sẽ được yêu cầu sắp xếp theo biểu thức lương năm giảm dần.

### 9.2 WHERE không thể dùng SELECT alias cùng query block

Ví dụ **không hợp lệ** trong Oracle:

~~~sql
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM staff
WHERE annual_salary > 150000000;
~~~

`ANNUAL_SALARY` là nhãn được đặt ở SELECT list; `WHERE` cùng query block không thể dùng nó như một cột nguồn. Oracle có thể báo `ORA-00904: invalid identifier`, trừ các tình huống có cột nguồn thật cùng tên gây hiểu nhầm khác.

Cách thứ nhất: lặp biểu thức trong WHERE:

~~~sql
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM staff
WHERE base_salary * 12 > 150000000;
~~~

Cách thứ hai: đưa biểu thức vào **inline view**:

~~~sql
SELECT x.emp_id,
       x.annual_salary
FROM (
    SELECT emp_id,
           base_salary * 12 AS annual_salary
    FROM staff
) x
WHERE x.annual_salary > 150000000;
~~~

Ở query block bên ngoài, `ANNUAL_SALARY` là một cột của kết quả subquery `x`, nên có thể dùng trong WHERE của query block ngoài.

### 9.3 Dùng WITH để tái sử dụng biểu thức

~~~sql
WITH payroll AS (
    SELECT emp_id,
           full_name,
           base_salary * 12 AS annual_salary
    FROM staff
)
SELECT emp_id,
       full_name,
       annual_salary
FROM payroll
WHERE annual_salary > 150000000
ORDER BY annual_salary DESC;
~~~

`WITH` tạo một common table expression (CTE), giúp đặt tên kết quả trung gian. Cách này hữu ích khi biểu thức dài hoặc cần dùng nó ở nhiều chỗ.

Đây là cách tổ chức logic SQL. Không đồng nghĩa Oracle **bắt buộc phải ghi CTE thành một bảng tạm vật lý**: optimizer có thể chọn nhiều chiến lược thực thi.

### 9.4 Alias với GROUP BY và HAVING

Với các phiên bản Oracle truyền thống, không nên giả định alias của SELECT list có thể tham chiếu trực tiếp ở `GROUP BY` hoặc `HAVING` cùng query block. Các bản Oracle mới có hỗ trợ thêm một số cú pháp liên quan aliases, nhưng mức hỗ trợ thay đổi theo release và cấu hình.

Khi cần SQL tương thích rộng, sử dụng biểu thức gốc hoặc đưa phép tính vào inline view/CTE trước:

~~~sql
WITH categorized AS (
    SELECT dept_code,
           CASE
             WHEN base_salary >= 15000000 THEN 'HIGH'
             ELSE 'OTHER'
           END AS salary_band
    FROM staff
)
SELECT dept_code,
       salary_band,
       COUNT(*) AS staff_count
FROM categorized
GROUP BY dept_code, salary_band
ORDER BY dept_code, salary_band;
~~~

Ví dụ preview `GROUP BY`; trọng tâm của bài vẫn là cách định nghĩa biểu thức và alias rồi tham chiếu nó ở query block phù hợp.

### 9.5 ORDER BY theo vị trí cột

Oracle cho phép dùng vị trí trong SELECT list:

~~~sql
SELECT emp_id,
       full_name,
       base_salary
FROM staff
ORDER BY 3 DESC;
~~~

`ORDER BY 3` yêu cầu sắp theo biểu thức thứ ba trong SELECT list, tức `BASE_SALARY`. Dù ngắn, cách này dễ sai khi thêm/đổi thứ tự cột. Trong SQL dùng lâu dài, `ORDER BY base_salary DESC` hoặc alias rõ nghĩa thường dễ bảo trì hơn.

## 10. DISTINCT, ALL và sự khác nhau giữa chọn cột và loại trùng

`SELECT` mặc định có ngữ nghĩa `ALL`: những dòng có cùng giá trị trên các cột được chọn **có thể xuất hiện nhiều lần**.

Giả sử có ba nhân viên cùng `DEPT_CODE = 'IT'`:

~~~sql
SELECT dept_code
FROM staff;
~~~

Giá trị `IT` có thể xuất hiện ba lần.

Muốn danh sách mã phòng ban **không trùng**, dùng:

~~~sql
SELECT DISTINCT dept_code
FROM staff;
~~~

### 10.1 DISTINCT áp dụng cho toàn bộ tổ hợp cột

~~~sql
SELECT DISTINCT dept_code,
       active_flag
FROM staff;
~~~

Oracle loại trùng theo **cặp giá trị** `(DEPT_CODE, ACTIVE_FLAG)`, không chỉ riêng `DEPT_CODE`.

Ví dụ:

~~~text
IT / Y
IT / Y
IT / N
~~~

Sau DISTINCT còn:

~~~text
IT / Y
IT / N
~~~

### 10.2 DISTINCT không thay thế ORDER BY

Kết quả từ `SELECT DISTINCT` không được bảo đảm theo thứ tự mong muốn nếu không có `ORDER BY`.

~~~sql
SELECT DISTINCT dept_code
FROM staff
ORDER BY dept_code;
~~~

### 10.3 Chi phí của DISTINCT

Khi dữ liệu lớn, DISTINCT có thể yêu cầu sort/hash hoặc phương án loại trùng khác. Không dùng DISTINCT chỉ để che lỗi JOIN sai làm nhân bản dòng; cần hiểu nguyên nhân các dòng trùng có xuất hiện hay không.

## 11. DUAL là gì?

**`DUAL`** là bảng đặc biệt có một dòng, được Oracle cung cấp để dễ thực hiện các biểu thức khi không có bảng nghiệp vụ cần đọc. Nó nằm trong schema hệ thống `SYS` và thông thường được truy cập bằng tên `DUAL`.

Một số phiên bản Oracle mới hỗ trợ câu SELECT không có `FROM` trong những ngữ cảnh nhất định, nhưng dùng `FROM DUAL` vẫn là cách thông dụng và có tính tương thích rộng giữa các phiên bản Oracle.

### 11.1 SELECT một hằng số từ DUAL

~~~sql
SELECT 1 AS value_one
FROM dual;
~~~

Kết quả là một dòng, một cột với giá trị `1`.

~~~sql
SELECT 'Hello Oracle' AS message
FROM dual;
~~~

Kết quả là một dòng chứa chuỗi `Hello Oracle`.

### 11.2 Kiểm tra phép tính bằng DUAL

~~~sql
SELECT 7 * 8 AS result
FROM dual;
~~~

Kết quả là `56`.

~~~sql
SELECT 10 + 2 * 5 AS expression_a,
       (10 + 2) * 5 AS expression_b
FROM dual;
~~~

Kết quả là một dòng với hai cột `20` và `60`.

DUAL giúp thử nhanh cú pháp hoặc hàm SQL mà không tạo bảng lab hoặc truy vấn dữ liệu người dùng.

### 11.3 Kiểm tra các hàm hệ thống

~~~sql
SELECT USER AS connected_user,
       SYSDATE AS database_date,
       SYSTIMESTAMP AS database_timestamp
FROM dual;
~~~

`USER` cho biết Oracle user của session hiện tại; `SYSDATE` và `SYSTIMESTAMP` trả thời gian liên quan hệ thống database. DUAL không lưu những thông tin này: chúng do **biểu thức/hàm** được Oracle đánh giá.

Kiểm tra container trong Oracle Multitenant:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS database_name
FROM dual;
~~~

Các giá trị phụ thuộc session và database kết nối. Cú pháp này hữu ích để xác minh đang truy vấn đúng môi trường trước khi thực hiện thao tác khác.

### 11.4 DUAL có cột DUMMY

DUAL truyền thống có một cột tên `DUMMY` với giá trị thường là `X`:

~~~sql
SELECT dummy
FROM dual;
~~~

Vì `DUAL` chỉ cung cấp một dòng, truy vấn trên trả một dòng. Không nên thêm/sửa/xóa dữ liệu trong `SYS.DUAL`: đây là đối tượng hệ thống, không phải bảng thực hành của ứng dụng.

### 11.5 FAST DUAL optimization

Với nhiều biểu thức không cần đọc trực tiếp cột `DUMMY`, Oracle có thể tối ưu thực thi bằng cơ chế thường được gọi là **FAST DUAL**, tránh truy cập dữ liệu bảng DUAL như một bảng nghiệp vụ thông thường.

Ví dụ:

~~~sql
SELECT 100 / 4 AS result
FROM dual;
~~~

Truy vấn này không cần nội dung cột `DUMMY`. Trong execution plan của những phiên bản hỗ trợ, có thể thấy operation liên quan FAST DUAL. Nếu tham chiếu trực tiếp `DUMMY`, plan có thể khác.

Điều quan trọng đối với người mới học là **DUAL trả một dòng cho phép thử biểu thức**, không phải một bảng lớn cần tối ưu index.

### 11.6 DUAL không có nghĩa mọi SELECT đều một dòng

~~~sql
SELECT full_name
FROM staff;
~~~

Trả số dòng tùy bảng STAFF.

~~~sql
SELECT 1
FROM dual;
~~~

Trả một dòng do nguồn dữ liệu là DUAL. Nếu thêm điều kiện không thỏa:

~~~sql
SELECT 1 AS result
FROM dual
WHERE 1 = 0;
~~~

Không có dòng nào được trả về. Như vậy số dòng là kết quả của nguồn và điều kiện, không phải do mọi biểu thức SELECT đều “tự động” sinh một dòng.

### 11.7 Có thể dùng DUAL khi nào?

| Nhu cầu | Có nên dùng DUAL? | Ví dụ |
|---|---|---|
| Tính `2 * 3 + 1` | Có | `SELECT 2 * 3 + 1 FROM dual` |
| Lấy thời gian database | Có | `SELECT SYSTIMESTAMP FROM dual` |
| Kiểm tra `UPPER('oracle')` | Có | `SELECT UPPER('oracle') FROM dual` |
| Kiểm tra phiên/user/container | Có | `SELECT USER FROM dual` |
| Đọc danh sách nhân viên | Không thay thế STAFF | `SELECT full_name FROM staff` |
| Sinh 10.000 dòng dữ liệu mẫu | Cần cơ chế tạo dòng khác | Có thể sử dụng `CONNECT BY LEVEL` hoặc bộ sinh dữ liệu phù hợp, không trông chờ DUAL tự chứa 10.000 dòng |

## 12. Dùng DUAL với literal DATE, TIMESTAMP và hàm chuyển đổi

Với Oracle, DUAL đặc biệt hữu ích để thử kiểu dữ liệu và format model.

### 12.1 DATE literal

~~~sql
SELECT DATE '2026-11-14' AS selected_day
FROM dual;
~~~

Literal DATE kiểu này tạo giá trị ngày có thời gian 00:00:00. Việc hiển thị theo định dạng gì phụ thuộc client/NLS, không có nghĩa nó là kiểu chuỗi.

### 12.2 TIMESTAMP literal

~~~sql
SELECT TIMESTAMP '2026-11-14 09:30:45.123456' AS event_time
FROM dual;
~~~

TIMESTAMP có thể giữ fractional seconds; TIMESTAMP thuần **không tự có timezone**.

### 12.3 TO_DATE và TO_CHAR

~~~sql
SELECT TO_CHAR(
         TO_DATE('2026-11-14 09:30:45',
                 'YYYY-MM-DD HH24:MI:SS'),
         'YYYY-MM-DD HH24:MI:SS'
       ) AS formatted_date
FROM dual;
~~~

`TO_DATE` chuyển chuỗi sang DATE, `TO_CHAR` chuyển giá trị ngày giờ thành **chuỗi** theo format đã chỉ định. Dùng format tường minh giúp ví dụ ổn định khi thay NLS.

### 12.4 TO_TIMESTAMP_TZ

~~~sql
SELECT TO_TIMESTAMP_TZ(
         '2026-11-14 09:30:00 +07:00',
         'YYYY-MM-DD HH24:MI:SS TZH:TZM'
       ) AS timestamp_with_zone
FROM dual;
~~~

Đây là giá trị có thông tin UTC offset. Nếu muốn lấy instant theo UTC:

~~~sql
SELECT SYS_EXTRACT_UTC(
         TO_TIMESTAMP_TZ(
           '2026-11-14 09:30:00 +07:00',
           'YYYY-MM-DD HH24:MI:SS TZH:TZM'
         )
       ) AS utc_timestamp
FROM dual;
~~~

Kết quả là một giá trị TIMESTAMP biểu diễn `2026-11-14 02:30:00` theo UTC. Đây là ví dụ kiểm tra biểu thức, không liên quan bảng nhân viên.

## 13. Biểu thức, kiểu dữ liệu và chuyển đổi ngầm

Mỗi biểu thức SELECT có **kiểu dữ liệu kết quả**. Oracle dùng các quy tắc kiểu và đôi khi ép kiểu ngầm. Để truy vấn ổn định, nên viết chuyển đổi rõ ràng khi các kiểu có thể gây mơ hồ.

### 13.1 Không cộng chuỗi số một cách tùy tiện

~~~sql
-- Tránh phụ thuộc implicit conversion giữa chuỗi và số.
SELECT '100' + 20 AS result
FROM dual;
~~~

Cách này có thể khiến Oracle chuyển chuỗi `'100'` sang NUMBER, nhưng phụ thuộc việc chuỗi có parse hợp lệ và một số cấu hình liên quan. Với đầu vào là chuỗi số, viết chuyển đổi rõ:

~~~sql
SELECT TO_NUMBER('100') + 20 AS result
FROM dual;
~~~

Khi chuyển số có dấu phân cách thập phân/hàng nghìn, phải chú ý format model/NLS, ví dụ dấu phẩy và dấu chấm có ý nghĩa khác giữa vùng.

### 13.2 Format ngày giờ không phải chuỗi để tính toán

~~~sql
SELECT SYSDATE + 1 AS next_day
FROM dual;
~~~

Với DATE, cộng `1` tương ứng cộng một ngày theo phép toán DATE của Oracle. Không cần chuyển DATE thành chuỗi để cộng ngày:

~~~sql
-- Không nên xem chuỗi đã format như giá trị datetime để tính toán.
SELECT TO_CHAR(SYSDATE, 'YYYY-MM-DD') AS today_text
FROM dual;
~~~

`TODAY_TEXT` là chuỗi, thích hợp cho hiển thị, không tự là Oracle DATE để làm phép toán ngày giờ.

### 13.3 Dùng CAST khi muốn chỉ rõ kiểu

~~~sql
SELECT CAST(100 AS NUMBER(10,2)) AS amount,
       CAST('Oracle' AS VARCHAR2(20)) AS text_value
FROM dual;
~~~

`CAST` là phép chuyển kiểu có cú pháp rõ ràng. Các phép chuyển giữa ngày giờ có và không có zone có thể làm mất hoặc thay đổi ngữ nghĩa timezone theo quy tắc Oracle; cần kiểm tra trước khi lưu dữ liệu nghiệp vụ.

### 13.4 Kiểm tra biểu thức trả về NULL

~~~sql
SELECT NULL AS missing_value,
       NVL(CAST(NULL AS NUMBER), 0) AS numeric_default
FROM dual;
~~~

`CAST(NULL AS NUMBER)` đặt rõ kiểu cho biểu thức NULL trong ví dụ này. Khi thiết kế cột kết quả của view/CTE, kiểu của expression quan trọng đối với các công cụ ánh xạ dữ liệu.

## 14. Tên cột, alias và cách dùng trong ứng dụng

Một ứng dụng Java/JDBC có thể truy vấn:

~~~sql
SELECT emp_id AS employee_id,
       full_name AS employee_name,
       base_salary * 12 AS annual_salary
FROM staff
WHERE emp_id = :p_emp_id;
~~~

Khi dùng JDBC `PreparedStatement`, tham số thường viết bằng `?`; cú pháp `:p_emp_id` là bind notation phổ biến trong Oracle SQL tools và một số frameworks. Ví dụ JDBC:

~~~java
String sql = """
    SELECT emp_id AS employee_id,
           full_name AS employee_name,
           base_salary * 12 AS annual_salary
    FROM staff
    WHERE emp_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, requestedId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            long id = rs.getLong("EMPLOYEE_ID");
            String name = rs.getString("EMPLOYEE_NAME");
            java.math.BigDecimal annualSalary =
                rs.getBigDecimal("ANNUAL_SALARY");
        }
    }
}
~~~

Đây là đoạn minh họa nằm trong phương thức có sẵn `connection` và `requestedId`. Cần xử lý `SQLException` theo ứng dụng và kiểm tra trường hợp không có dòng. SQL tính cột `ANNUAL_SALARY`, còn JDBC đọc **label của cột kết quả** từ alias.

### 14.1 Quoted aliases và mapping

Nếu SQL dùng:

~~~sql
SELECT emp_id AS "Employee Id",
       full_name AS "Employee Name"
FROM staff;
~~~

Các labels chứa khoảng trắng và cách viết chính xác. Đây có thể là lựa chọn tốt để hiển thị báo cáo nhưng không phải lúc nào thuận tiện cho mapping API tự động. Trong truy vấn DAO, alias đơn giản, ổn định như `employee_id`, `employee_name` thường dễ dùng hơn.

### 14.2 Column alias không phải bảo mật

~~~sql
SELECT salary AS public_salary
FROM staff;
~~~

Đổi nhãn `SALARY` thành `PUBLIC_SALARY` không biến dữ liệu thành công khai và không hạn chế quyền truy cập. Bảo mật cần dựa trên quyền database, view, chính sách row/column security, role, API authorization và cách chọn cột phù hợp.

### 14.3 Bind variable không giống alias

So sánh:

~~~sql
SELECT base_salary * :p_factor AS adjusted_salary
FROM staff;
~~~

- `:p_factor` là **bind variable** đưa giá trị vào biểu thức.
- `ADJUSTED_SALARY` là **column alias** đặt tên kết quả.

Alias không nhận giá trị thay thế cho tham số; bind variable không đổi nhãn cột. Không ghép giá trị người dùng trực tiếp vào câu SQL để thay cho bind parameter.

## 15. Thứ tự kết quả và SELECT DISTINCT

Không có `ORDER BY`, Oracle **không cam kết thứ tự trả dòng**, ngay cả khi bảng đang có primary key, dữ liệu được insert tăng dần hoặc truy vấn qua một index.

~~~sql
SELECT emp_id, full_name
FROM staff;
~~~

Không bảo đảm hàng có `EMP_ID` nhỏ nhất được trả trước.

~~~sql
SELECT emp_id, full_name
FROM staff
ORDER BY emp_id;
~~~

Yêu cầu sắp xếp tăng dần theo mã.

Khi sắp xếp biểu thức:

~~~sql
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM staff
ORDER BY annual_salary DESC, emp_id ASC;
~~~

Thêm khóa phụ `EMP_ID` giúp kết quả ổn định khi nhiều nhân viên có cùng lương năm.

`DISTINCT` chỉ loại trùng theo cột được chọn, **không** mang nghĩa “sắp xếp”. Nếu cần cả hai mục tiêu:

~~~sql
SELECT DISTINCT dept_code
FROM staff
ORDER BY dept_code;
~~~

## 16. Lab: tạo bảng nhân viên riêng để thực hành

Các ví dụ trong các phần trước dùng tên bảng `STAFF` như một mô hình. Để thực hành đầy đủ mà không cần schema HR mẫu, có thể tạo bảng **`LAB_SELECT_STAFF`** trong **schema thực hành riêng**.

**Chỉ chạy DDL/DML trên tài khoản được phép tạo bảng, có quota thích hợp và không phải schema sản xuất.** Oracle DDL như `CREATE TABLE` có implicit commit; `ROLLBACK` sau đó không tự hủy bảng đã tạo.

### 16.1 Tạo bảng

~~~sql
CREATE TABLE lab_select_staff (
    emp_id       NUMBER PRIMARY KEY,
    full_name    VARCHAR2(100) NOT NULL,
    dept_code    VARCHAR2(20) NOT NULL,
    base_salary  NUMBER(12,2) NOT NULL,
    bonus        NUMBER(12,2),
    hired_on     DATE NOT NULL,
    active_flag  CHAR(1) NOT NULL
);
~~~

Các cột được chọn có chủ đích:

- `EMP_ID`: định danh số.
- `FULL_NAME`: chuỗi tên.
- `DEPT_CODE`: mã phòng ban, sẽ có giá trị lặp để thử DISTINCT.
- `BASE_SALARY`: NUMBER để thử biểu thức nhân/cộng.
- `BONUS`: có thể NULL hoặc 0, phù hợp minh họa cách xử lý NULL.
- `HIRED_ON`: DATE để thử định dạng.
- `ACTIVE_FLAG`: ký tự để dùng CASE.

### 16.2 Nạp dữ liệu

~~~sql
INSERT INTO lab_select_staff VALUES
    (101, 'An Nguyen', 'IT', 15000000, 2000000, DATE '2022-03-15', 'Y');

INSERT INTO lab_select_staff VALUES
    (102, 'Binh Tran', 'IT', 12000000, NULL, DATE '2023-07-01', 'Y');

INSERT INTO lab_select_staff VALUES
    (103, 'Chi Le', 'HR', 11000000, 0, DATE '2021-12-20', 'Y');

INSERT INTO lab_select_staff VALUES
    (104, 'Dung Pham', 'FIN', 22000000, 3500000, DATE '2020-05-10', 'N');

INSERT INTO lab_select_staff VALUES
    (105, 'Ha Vo', 'IT', 18000000, NULL, DATE '2024-01-08', 'Y');

COMMIT;
~~~

Ví dụ nạp năm dòng, trong đó ba nhân viên thuộc IT, một bonus đúng 0 và hai bonus NULL. Điều này giúp quan sát sự khác nhau giữa giá trị 0 và giá trị chưa được ghi.

### 16.3 Chọn hai cột

~~~sql
SELECT emp_id, full_name
FROM lab_select_staff
ORDER BY emp_id;
~~~

Kết quả:

| EMP_ID | FULL_NAME |
|---:|---|
| 101 | An Nguyen |
| 102 | Binh Tran |
| 103 | Chi Le |
| 104 | Dung Pham |
| 105 | Ha Vo |

### 16.4 Tính cột mới bằng biểu thức

~~~sql
SELECT emp_id,
       full_name,
       base_salary,
       base_salary * 12 AS annual_base_salary
FROM lab_select_staff
ORDER BY emp_id;
~~~

Lương cơ bản năm của nhân viên 101 là 180.000.000 theo giả định 12 tháng với lương tháng cố định. Cột này chỉ có trong kết quả, không làm bảng có thêm cột lưu trữ.

### 16.5 Xử lý NULL trong công thức

~~~sql
SELECT emp_id,
       base_salary,
       bonus,
       base_salary + bonus AS naive_total,
       base_salary + NVL(bonus, 0) AS normalized_total
FROM lab_select_staff
ORDER BY emp_id;
~~~

Với nhân viên 102 và 105, `NAIVE_TOTAL` là NULL trong khi `NORMALIZED_TOTAL` bằng lương cơ bản. Với nhân viên 103, bonus là **0** chứ không phải NULL; đó là dữ liệu đã được ghi nhận.

### 16.6 Nối chuỗi và dùng alias có khoảng trắng

~~~sql
SELECT emp_id AS "Mã NV",
       full_name || ' - ' || dept_code AS "Tên và phòng"
FROM lab_select_staff
ORDER BY emp_id;
~~~

Ví dụ dòng đầu: `101 | An Nguyen - IT`.

### 16.7 CASE

~~~sql
SELECT emp_id,
       full_name,
       CASE
           WHEN active_flag = 'Y' THEN 'ACTIVE'
           ELSE 'INACTIVE'
       END AS employment_status
FROM lab_select_staff
ORDER BY emp_id;
~~~

Mỗi dòng có thêm nhãn trạng thái mới. `ACTIVE_FLAG` trong bảng không bị sửa.

### 16.8 DISTINCT

~~~sql
SELECT DISTINCT dept_code
FROM lab_select_staff
ORDER BY dept_code;
~~~

Kết quả gồm ba mã phòng ban: `FIN`, `HR`, `IT`. Mặc dù IT có ba nhân viên, nó xuất hiện một lần.

### 16.9 Lọc theo biểu thức đã được đặt alias

Sai:

~~~sql
-- ORA-00904 hoặc lỗi tham chiếu tương tự vì alias không có scope ở WHERE này.
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM lab_select_staff
WHERE annual_salary >= 180000000;
~~~

Đúng khi lặp biểu thức:

~~~sql
SELECT emp_id,
       base_salary * 12 AS annual_salary
FROM lab_select_staff
WHERE base_salary * 12 >= 180000000
ORDER BY annual_salary DESC;
~~~

Hoặc dùng inline view:

~~~sql
SELECT q.emp_id,
       q.annual_salary
FROM (
    SELECT emp_id,
           base_salary * 12 AS annual_salary
    FROM lab_select_staff
) q
WHERE q.annual_salary >= 180000000
ORDER BY q.annual_salary DESC;
~~~

### 16.10 Định dạng ngày tuyển dụng

~~~sql
SELECT emp_id,
       TO_CHAR(hired_on, 'YYYY-MM-DD') AS hire_date_text
FROM lab_select_staff
ORDER BY emp_id;
~~~

`HIRE_DATE_TEXT` là chuỗi hiển thị ngày. Bản thân `HIRED_ON` vẫn là DATE.

### 16.11 Kiểm tra DUAL song song với bài lab

Không cần bảng nhân viên để chạy:

~~~sql
SELECT 2026 AS report_year,
       UPPER('oracle') AS product_name,
       125 * 4 AS calculated_value,
       SYSDATE AS executed_at
FROM dual;
~~~

Kết quả là một dòng với nhiều biểu thức thuộc những kiểu khác nhau.

### 16.12 Dọn lab

Nếu muốn dọn sau khi thực hành, chỉ xóa **đúng bảng do bạn tạo** trong schema lab theo quy trình quản trị được cho phép. Không đặt lệnh `DROP TABLE` trong script có thể chạy nhầm production, vì DDL có implicit commit và không thể trông chờ `ROLLBACK` để khôi phục toàn bộ.

## 17. Lỗi thường gặp khi chọn cột, biểu thức và alias

| Tình huống | Vấn đề | Cách xử lý |
|---|---|---|
| `SELECT emp_id full_name dept_code FROM staff` | Thiếu dấu phẩy, Oracle có thể diễn giải tên tiếp theo thành alias hoặc báo lỗi | Viết `SELECT emp_id, full_name, dept_code` |
| `SELECT emp_id, FROM staff` | Dấu phẩy thừa trước FROM | Bỏ dấu phẩy cuối |
| `SELECT unknown_column FROM staff` | Không có cột tương ứng hoặc thiếu quyền/phạm vi | Xem metadata bảng và alias của nguồn |
| `SELECT salary * 12 AS annual FROM staff WHERE annual > ...` | Tham chiếu SELECT alias tại WHERE cùng query block | Lặp expression hoặc dùng CTE/inline view |
| `FROM staff AS s` trong Oracle truyền thống | Table alias không dùng cú pháp AS theo dạng phổ biến của Oracle | Viết `FROM staff s` |
| `SELECT 'hello' AS 'Message' FROM dual` | Dùng dấu nháy đơn cho tên alias | Viết `AS "Message"` hoặc `AS message` |
| `SELECT 100 / 0 FROM dual` | Chia cho 0 | Kiểm soát mẫu số, cân nhắc `NULLIF` |
| `base_salary + bonus` trả NULL | BONUS đang là NULL | Xác định nghiệp vụ; có thể `NVL(bonus, 0)` |
| `'A' + 'B'` | Dấu + không phải toán tử nối chuỗi | Dùng `'A' || 'B'` |
| DATE hiển thị thiếu phần giờ | Định dạng NLS/client ẩn giờ | Dùng `TO_CHAR(date_col, 'YYYY-MM-DD HH24:MI:SS')` để quan sát |
| SQL dùng `SELECT *` và mapping cột theo vị trí | Schema thêm cột làm thay đổi shape của result | Chọn tường minh cột và alias ổn định |
| `ORDER BY` không có, kết quả mỗi lần khác | Không có bảo đảm thứ tự | Thêm `ORDER BY` đúng khóa |
| `SELECT DISTINCT` vẫn có nhiều hàng cùng DEPT_CODE | DISTINCT áp dụng tổ hợp toàn bộ biểu thức được chọn | Chọn đúng cột muốn distinct hoặc thiết kế GROUP BY thích hợp |
| `SELECT UPPER(name) FROM dual` | `NAME` không phải cột của DUAL | Dùng literal `UPPER('Oracle')` hoặc FROM bảng có cột NAME |
| `SELECT 1 FROM dual WHERE 1=0` không trả dòng | WHERE loại dòng duy nhất từ DUAL | Kiểm tra điều kiện; DUAL không bỏ qua WHERE |

Khi Oracle báo lỗi, nên đọc toàn bộ thông báo và vị trí lỗi, sau đó tách câu SQL thành những biểu thức nhỏ. Dùng DUAL để thử hàm/toán tử và dùng truy vấn chọn cột tường minh để xác định tên nguồn.

## 18. Tối ưu và thói quen nên hình thành

### 18.1 Chọn đúng cột cần dùng

Nếu giao diện cần tên và mã nhân viên, câu:

~~~sql
SELECT emp_id, full_name
FROM lab_select_staff;
~~~

rõ nghĩa hơn `SELECT *` và tránh tải cả mức lương/bonus khi không cần. Việc hạn chế trường dữ liệu cũng giúp giảm nguy cơ lộ thông tin nhạy cảm tại tầng ứng dụng, nhưng **quyền truy cập vẫn phải được quản lý độc lập**.

### 18.2 Đặt alias ổn định

Với truy vấn phục vụ API, dùng alias không khoảng trắng và có ý nghĩa, ví dụ:

~~~sql
SELECT emp_id AS employee_id,
       full_name AS employee_name,
       base_salary * 12 AS annual_base_salary
FROM lab_select_staff;
~~~

Với báo cáo dành cho người đọc, có thể dùng alias có dấu nháy kép để trình bày tiêu đề đẹp hơn.

### 18.3 Không lạm dụng biểu thức nặng trên từng dòng

Một biểu thức tính toán đơn giản thường hợp lý, nhưng nếu SELECT list gọi hàm phức tạp cho hàng triệu dòng thì chi phí CPU có thể đáng kể. Cũng cần phân biệt việc tính ở SELECT list để **hiển thị** với việc đặt hàm lên cột trong `WHERE`, nơi nó có thể tác động đến khả năng dùng index.

### 18.4 Cẩn thận với implicit conversion

Một phép tính số không nên phụ thuộc vào chuỗi `'100'` có tự chuyển được hay không. Tương tự, biểu thức ngày giờ không nên dựa vào NLS mặc định. Dùng literal và hàm chuyển kiểu phù hợp, và bind đúng kiểu từ JDBC.

### 18.5 Không giả định thứ tự hàng

Nếu báo cáo yêu cầu danh sách tên theo alphabet hoặc lương giảm dần, viết `ORDER BY` tường minh và dùng khóa phụ ổn định khi cần. Alias có thể xuất hiện trong ORDER BY, nhưng không tự biến kết quả thành thứ tự cố định.

## 19. Câu hỏi và bài tập tự luyện

### Bài 1 — DUAL và thứ tự phép toán

Dự đoán hai kết quả:

~~~sql
SELECT 8 + 2 * 5 AS a,
       (8 + 2) * 5 AS b
FROM dual;
~~~

*Gợi ý:* `A = 18`, `B = 50`. Dùng ngoặc để kiểm soát thứ tự tính.

### Bài 2 — Chọn cột và tính lương năm

Viết truy vấn từ `LAB_SELECT_STAFF` trả `EMP_ID`, `FULL_NAME` và lương cơ bản năm với alias `ANNUAL_BASE_SALARY`; sắp xếp lương năm giảm dần.

Một đáp án:

~~~sql
SELECT emp_id,
       full_name,
       base_salary * 12 AS annual_base_salary
FROM lab_select_staff
ORDER BY annual_base_salary DESC, emp_id;
~~~

### Bài 3 — Vì sao NULL xuất hiện?

Hai biểu thức:

~~~sql
SELECT emp_id,
       base_salary + bonus AS total_a,
       base_salary + NVL(bonus, 0) AS total_b
FROM lab_select_staff;
~~~

Với nhân viên 102, `BONUS = NULL`. *Gợi ý:* `TOTAL_A` là NULL, `TOTAL_B` bằng lương cơ bản. Cần quyết định nghiệp vụ trước khi dùng NULL → 0 trong ứng dụng.

### Bài 4 — Alias trong WHERE

Giải thích vì sao truy vấn này sai và sửa lại:

~~~sql
SELECT emp_id, base_salary * 12 AS annual_salary
FROM lab_select_staff
WHERE annual_salary > 200000000;
~~~

*Gợi ý:* SELECT alias không có scope ở WHERE cùng query block. Lặp `base_salary * 12` hoặc dùng inline view/CTE.

### Bài 5 — DISTINCT theo tổ hợp

Dự đoán kết quả:

~~~sql
SELECT DISTINCT dept_code, active_flag
FROM lab_select_staff
ORDER BY dept_code, active_flag;
~~~

*Gợi ý:* `IT/Y` xuất hiện một lần dù có ba nhân viên IT hoạt động, `HR/Y` một lần, `FIN/N` một lần. DISTINCT xét **cặp cột**.

### Bài 6 — Dùng DUAL lấy thông tin session

Viết câu lệnh trả Oracle username và container hiện tại:

~~~sql
SELECT USER AS connected_user,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

Không có bảng ứng dụng nào được đọc trong truy vấn này.

### Bài 7 — Phân biệt nháy đơn và nháy kép

Viết một câu SELECT trả chuỗi `Hello` dưới nhãn có dấu cách `Greeting Text`.

~~~sql
SELECT 'Hello' AS "Greeting Text"
FROM dual;
~~~

`'Hello'` là **literal**, còn `"Greeting Text"` là **quoted column alias**.

### Bài 8 — Dữ liệu báo cáo có tính an toàn

Một API chỉ cần `EMP_ID` và `FULL_NAME` nhưng đang chạy `SELECT * FROM LAB_SELECT_STAFF`. Hãy nêu hai lý do nên đổi thành danh sách cột tường minh.

*Gợi ý:* Giảm cột thừa/nhạy cảm như lương và bonus; ổn định shape và tên cột khi schema đổi; đôi khi giảm I/O/network. Tuy nhiên luôn cần kiểm soát quyền truy cập dữ liệu ở tầng database/ứng dụng.

### Bài 9 — Biểu thức ngày giờ

Thử:

~~~sql
SELECT TO_CHAR(
         DATE '2026-11-14' + 1,
         'YYYY-MM-DD HH24:MI:SS'
       ) AS next_day_text
FROM dual;
~~~

*Gợi ý:* Oracle DATE literal ban đầu là 00:00:00 ngày 14, cộng một ngày thành 00:00:00 ngày 15. `TO_CHAR` chỉ chuyển kết quả thành chuỗi.

### Bài 10 — Bản chất của SELECT alias

Sau khi chạy:

~~~sql
SELECT base_salary AS monthly_pay
FROM lab_select_staff;
~~~

có thể tiếp tục:

~~~sql
SELECT base_salary
FROM lab_select_staff;
~~~

*Gợi ý:* Có. Alias không đổi tên cột vật lý hoặc sửa schema; nó chỉ tồn tại trong ngữ cảnh truy vấn.

## 20. Tổng kết

Trong Oracle Database, phần **SELECT list** quyết định những cột và giá trị nào xuất hiện trong kết quả. Một mục có thể là **cột gốc**, **literal**, **phép tính**, **hàm**, **CASE** hoặc **biểu thức kết hợp**. **Column alias** giúp đặt tên dễ hiểu cho kết quả, nhưng không tạo hoặc đổi tên cột vật lý và không thể được sử dụng tùy ý ở mọi clause của cùng query block.

Các quy tắc thực hành quan trọng:

1. **Chọn tường minh các cột cần thiết** thay vì lạm dụng `SELECT *` trong mã ứng dụng dùng lâu dài.
2. **Dùng alias đúng cú pháp**: `AS annual_salary` hoặc `AS "Lương năm"`; dấu nháy đơn dành cho literal chuỗi.
3. **Nhớ scope của alias**: dùng được trong `ORDER BY`, nhưng `WHERE` cùng query block cần biểu thức gốc hoặc một subquery/CTE.
4. **Viết biểu thức cẩn thận** với precedence, NULL, chuyển kiểu, đơn vị tiền tệ và định dạng ngày giờ.
5. **Dùng DUAL** để thử biểu thức và hàm khi không cần dữ liệu bảng nghiệp vụ; thông thường DUAL có một dòng và là nguồn thuận tiện cho `SELECT 1`, `SYSDATE` hoặc `SYS_CONTEXT`.
6. **Không nhầm projection với filtering hoặc sorting**: danh sách SELECT chọn cột, WHERE chọn dòng, ORDER BY xác định thứ tự, DISTINCT loại trùng theo tổ hợp giá trị được chọn.

Khi đã nắm các khái niệm này, bạn có thể viết SELECT ngắn gọn, chính xác, đặt nhãn cột nhất quán cho báo cáo/JDBC và tự kiểm chứng biểu thức Oracle thông qua DUAL trước khi đưa vào truy vấn thực tế.
