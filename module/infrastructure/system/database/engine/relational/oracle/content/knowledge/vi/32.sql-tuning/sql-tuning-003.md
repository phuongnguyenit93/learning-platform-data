# Điều kiện có thể khai thác chỉ mục và tránh hàm bao quanh cột ngoài ý muốn

Một bảng đã có index nhưng truy vấn vẫn chạy FULL TABLE SCAN là tình huống thường gặp khi tối ưu SQL Oracle. Nguyên nhân có thể là predicate không xác định được khoảng khóa trên index, hàm hoặc phép chuyển kiểu được áp trực tiếp lên cột, thứ tự cột trong composite index không phù hợp, hoặc optimizer đánh giá full scan rẻ hơn index access.

Điều kiện có khả năng khai thác index thường được gọi là **sargable predicate** (search-argument-able predicate). Ý tưởng là biểu thức WHERE phải cho optimizer biết có thể tìm các giá trị khóa trong một khoảng xác định. Ví dụ:

~~~sql
WHERE order_date >= :from_date
  AND order_date <  :to_date
~~~

thường cho phép Oracle dùng index trên ORDER_DATE để xác định range. Ngược lại:

~~~sql
WHERE TRUNC(order_date) = :order_day
~~~

đang yêu cầu so sánh kết quả của một hàm trên từng giá trị ORDER_DATE. Index B-tree thông thường được xây trên giá trị ORDER_DATE gốc, nên không trực tiếp lưu thứ tự của TRUNC(ORDER_DATE). Có thể viết lại predicate để so sánh trực tiếp cột, hoặc tạo function-based index nếu truy vấn theo biểu thức đó là nhu cầu ổn định.

Tuy nhiên, sargable không có nghĩa optimizer bắt buộc dùng index. Oracle vẫn cân nhắc selectivity, số block phải đọc, clustering factor, thống kê, kích thước bảng, parallelism và chi phí của các access path khác. Mục tiêu là tạo điều kiện để index có thể được xem xét, rồi xác nhận plan thực tế.

## 1. Sargable predicate là gì?

Một predicate có thể khai thác index khi Oracle có thể dùng điều kiện đó để xác định một hoặc nhiều khoảng khóa trong cấu trúc index. Các phép so sánh trực tiếp thường có khả năng này:

~~~sql
WHERE employee_id = :employee_id
WHERE hire_date >= :start_date
WHERE hire_date < :end_date
WHERE salary BETWEEN :min_salary AND :max_salary
WHERE department_id IN (10, 20, 30)
WHERE email IS NOT NULL
~~~

Với index B-tree trên cột tương ứng, Oracle có thể xem xét INDEX UNIQUE SCAN, INDEX RANGE SCAN hoặc một dạng index access khác tùy điều kiện và chi phí.

### 1.1 Predicate trực tiếp trên cột

Nếu có index:

~~~sql
CREATE INDEX orders_order_date_ix ON orders(order_date);
~~~

thì các điều kiện sau có thể xác định khoảng khóa:

~~~sql
WHERE order_date = :p_date
WHERE order_date >= :p_start
WHERE order_date < :p_end
WHERE order_date BETWEEN :p_start AND :p_end
~~~

Các toán tử =, <, <=, >, >= và BETWEEN là dạng phổ biến. IN-list cũng có thể được xử lý qua nhiều lần tìm kiếm index hoặc cơ chế tương ứng của optimizer.

### 1.2 Hàm bao quanh cột

Ví dụ:

~~~sql
WHERE UPPER(last_name) = 'SMITH'
WHERE TRUNC(order_date) = DATE '2026-11-14'
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
WHERE NVL(status, 'NEW') = 'NEW'
WHERE SUBSTR(account_code, 1, 3) = 'ABC'
~~~

Các biểu thức trên không còn so sánh trực tiếp giá trị gốc của cột. Index B-tree thông thường trên LAST_NAME, ORDER_DATE, CREATED_AT, STATUS hoặc ACCOUNT_CODE không nhất thiết hỗ trợ tìm kiếm theo kết quả hàm.

Oracle có thể dùng function-based index nếu biểu thức được index hóa, hoặc có thể biến đổi một số biểu thức trong quá trình tối ưu. Vì vậy không nên kết luận chỉ dựa trên cú pháp; hãy xem Predicate Information và access path trong execution plan.

### 1.3 Hàm ở phía giá trị so sánh

Thông thường, áp dụng hàm cho bind hoặc literal vẫn giữ cột ở dạng trực tiếp:

~~~sql
WHERE order_date >= TO_DATE(:date_text, 'YYYY-MM-DD')
~~~

Index trên ORDER_DATE vẫn có thể được xem xét vì hàm chuyển đổi được áp dụng cho bind value. Tuy nhiên, ứng dụng nên bind đúng kiểu DATE hoặc TIMESTAMP thay vì gửi chuỗi để database chuyển đổi mỗi lần.

Quy tắc thực hành:

- Giữ cột có index ở dạng nguyên bản trong predicate nếu có thể.
- Chuyển đổi giá trị đầu vào trước khi so sánh.
- Không dựa vào implicit conversion.
- Nếu nghiệp vụ thực sự truy vấn theo một biểu thức, cân nhắc function-based index hoặc virtual column.

## 2. Vì sao hàm trên cột làm index khó sử dụng?

Index B-tree lưu khóa theo giá trị của biểu thức index. Nếu index được tạo trên ORDER_DATE, thứ tự khóa là thứ tự của giá trị ngày giờ gốc. Nó không tự lưu sẵn kết quả TRUNC(ORDER_DATE), TO_CHAR(ORDER_DATE) hoặc UPPER(LAST_NAME).

Ví dụ index:

~~~sql
CREATE INDEX orders_order_date_ix ON orders(order_date);
~~~

Truy vấn:

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
~~~

Oracle cần tìm các hàng mà kết quả TRUNC của từng ORDER_DATE bằng ngày yêu cầu. Index gốc không trực tiếp sắp xếp theo giá trị TRUNC(ORDER_DATE), vì vậy một range scan đơn giản trên index gốc không xác định được toàn bộ các hàng phù hợp.

Nếu đổi predicate thành:

~~~sql
SELECT order_id
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
~~~

thì điều kiện trực tiếp xác định một khoảng thời gian trên ORDER_DATE. Index gốc có thể được dùng để range scan.

### 2.1 Không phải cứ có hàm là mất index

Có các ngoại lệ quan trọng:

- Function-based index lưu kết quả của biểu thức.
- Virtual column có thể định nghĩa biểu thức và được index như cột.
- Optimizer có thể biến đổi một số predicate về dạng tương đương.
- Một số hàm có thể được hỗ trợ bởi index hoặc domain index chuyên biệt.
- Full scan có thể rẻ hơn index scan nếu predicate trả về phần lớn bảng.

Vì vậy, nguyên tắc đúng là tránh làm mất khả năng khai thác index một cách không cần thiết, sau đó xác minh bằng plan thực tế.

## 3. Xử lý điều kiện ngày giờ: tránh TRUNC trên cột

Đây là một trong những trường hợp phổ biến nhất.

### 3.1 Predicate thường gặp nhưng không thân thiện với index

~~~sql
SELECT *
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
~~~

Giả sử ORDER_DATE có index B-tree. Hàm TRUNC được áp lên cột cho mỗi giá trị, nên index trên ORDER_DATE có thể không được dùng làm range access trực tiếp.

### 3.2 Viết lại bằng khoảng nửa mở

~~~sql
SELECT *
FROM orders
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15';
~~~

Khoảng từ đầu ngày đến trước đầu ngày kế tiếp bao gồm toàn bộ thời điểm trong ngày được chọn. Dạng nửa mở [start, next_start) có các ưu điểm:

- Không phụ thuộc vào giả định thời điểm cuối ngày là 23:59:59.
- Bao gồm cả phần giây lẻ nếu cột là TIMESTAMP.
- Không chồng lấn khi truy vấn các ngày liên tiếp.
- Có thể dùng index range scan trên cột gốc.

### 3.3 Dùng bind variable có kiểu dữ liệu đúng

Ứng dụng nên bind hai giá trị DATE:

~~~sql
WHERE order_date >= :p_day_start
  AND order_date <  :p_next_day_start
~~~

Nếu đầu vào là chuỗi:

~~~sql
WHERE order_date >= TO_DATE(:p_day_start_text, 'YYYY-MM-DD')
  AND order_date <  TO_DATE(:p_next_day_text, 'YYYY-MM-DD')
~~~

Hàm chuyển đổi nằm ở phía bind, không bao quanh ORDER_DATE. Dù vậy, bind đúng kiểu DATE vẫn là lựa chọn tốt hơn.

### 3.4 Tránh BETWEEN nếu cần cả ngày có phần thời gian

BETWEEN bao gồm cả hai đầu mút:

~~~sql
WHERE order_date BETWEEN DATE '2026-11-14'
                     AND DATE '2026-11-14'
~~~

Điều kiện trên chỉ khớp đúng thời điểm nửa đêm, không phải mọi thời điểm trong ngày. Nếu muốn truy vấn cả ngày, dùng:

~~~sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
~~~

Không nên đặt upper bound là 23:59:59 vì TIMESTAMP có thể chứa fractional seconds.

### 3.5 TIMESTAMP và múi giờ

Với TIMESTAMP, vẫn dùng khoảng nửa mở nhưng hai bind phải cùng kiểu và biểu diễn đúng múi giờ nghiệp vụ. Nếu cột là TIMESTAMP WITH TIME ZONE, xác định rõ ngày theo múi giờ nào trước khi tính start và next start. Không mặc định một ngày địa phương luôn dài đúng 24 giờ ở nơi có chuyển đổi daylight saving time.

### 3.6 Khi nào nên dùng function-based index trên TRUNC?

Nếu workload thường xuyên lọc theo ngày lịch bằng TRUNC(ORDER_DATE), và không thể thay đổi SQL ở nhiều ứng dụng, có thể tạo:

~~~sql
CREATE INDEX orders_order_day_fbi
    ON orders(TRUNC(order_date));
~~~

Truy vấn dùng cùng biểu thức:

~~~sql
SELECT *
FROM orders
WHERE TRUNC(order_date) = DATE '2026-11-14';
~~~

Optimizer có thể dùng function-based index nếu cost phù hợp. Cần tính đến dung lượng index, chi phí INSERT/UPDATE/DELETE, thống kê index và khả năng biểu thức khớp với truy vấn.

Nếu chỉ có một truy vấn, thường đơn giản hơn khi viết lại thành khoảng trên cột gốc.

## 4. Tránh implicit conversion trên cột

Implicit conversion có thể làm truy vấn khó dự đoán, phụ thuộc NLS và làm mất index access nếu Oracle phải chuyển đổi chính giá trị cột.

### 4.1 So sánh NUMBER với chuỗi

Giả sử:

~~~sql
CREATE TABLE employees_demo (
    employee_id NUMBER,
    employee_code VARCHAR2(20)
);

CREATE INDEX employees_demo_id_ix
    ON employees_demo(employee_id);
~~~

So sánh NUMBER column với chuỗi:

~~~sql
WHERE employee_id = '100'
~~~

Oracle có thể chuyển chuỗi literal/bind sang NUMBER theo quy tắc kiểu dữ liệu. Nhưng ứng dụng nên gửi bind NUMBER và viết:

~~~sql
WHERE employee_id = :p_employee_id
~~~

Trường hợp ngược lại nguy hiểm hơn. Nếu EMPLOYEE_CODE là VARCHAR2 nhưng truy vấn so sánh với NUMBER:

~~~sql
WHERE employee_code = 100
~~~

Oracle cần so sánh giá trị ký tự với số; quy tắc chuyển đổi có thể khiến biểu thức tương đương TO_NUMBER(EMPLOYEE_CODE) = 100. Điều này có thể:

- Ngăn index trên EMPLOYEE_CODE được dùng như mong đợi.
- Gây lỗi ORA-01722 nếu cột chứa chuỗi không phải số.
- Làm kết quả phụ thuộc dữ liệu và conversion rules.

Hãy so sánh đúng kiểu:

~~~sql
WHERE employee_code = '100'
~~~

Nếu mã định danh là chuỗi, luôn bind VARCHAR2 và giữ nguyên semantics chuỗi. Không chuyển nó thành NUMBER chỉ vì hiện tại dữ liệu toàn chữ số.

### 4.2 So sánh DATE với chuỗi

Không nên viết:

~~~sql
WHERE order_date = '14-11-2026'
~~~

Literal chuỗi phải được chuyển sang DATE theo NLS_DATE_FORMAT của session. Kết quả có thể khác giữa môi trường hoặc phát sinh lỗi.

Dùng ANSI DATE literal:

~~~sql
WHERE order_date >= DATE '2026-11-14'
  AND order_date <  DATE '2026-11-15'
~~~

Hoặc chuyển đổi tường minh ở phía giá trị:

~~~sql
WHERE order_date >= TO_DATE(:p_date, 'YYYY-MM-DD')
  AND order_date <  TO_DATE(:p_next_date, 'YYYY-MM-DD')
~~~

### 4.3 Không dùng TO_DATE trên một cột DATE

Ví dụ sai về kiểu dữ liệu:

~~~sql
WHERE TO_DATE(order_date, 'YYYY-MM-DD') = :p_date
~~~

TO_DATE nhận character expression, không phải DATE. Khi truyền DATE, Oracle có thể chuyển DATE thành chuỗi theo NLS_DATE_FORMAT rồi lại parse chuỗi thành DATE. Việc này vừa thừa, vừa có thể làm index trên ORDER_DATE khó sử dụng, vừa tạo lỗi phụ thuộc NLS.

Hãy dùng:

~~~sql
WHERE order_date >= :p_start_date
  AND order_date <  :p_end_date
~~~

### 4.4 Kiểm tra conversion trong execution plan

Predicate Information có thể cho thấy conversion được áp vào cột:

~~~text
filter(TO_NUMBER("EMPLOYEE_CODE")=100)
~~~

hoặc:

~~~text
filter(TO_CHAR("ORDER_DATE")='2026-11-14')
~~~

Nếu thấy TO_NUMBER, TO_CHAR, CAST hoặc hàm chuyển kiểu bao quanh cột được index hóa, hãy kiểm tra kiểu của bind và kiểu cột trong data dictionary.

## 5. Các hàm thường gặp và cách viết lại

### 5.1 UPPER và LOWER

Truy vấn:

~~~sql
WHERE UPPER(last_name) = UPPER(:p_last_name)
~~~

Index thường trên LAST_NAME không được xây theo UPPER(LAST_NAME). Có hai hướng:

**Hướng 1: Function-based index**

~~~sql
CREATE INDEX employees_upper_name_ix
    ON employees(UPPER(last_name));
~~~

Truy vấn:

~~~sql
WHERE UPPER(last_name) = UPPER(:p_last_name)
~~~

Optimizer có thể dùng index biểu thức này.

**Hướng 2: Chuẩn hóa dữ liệu**

Lưu một cột normalized riêng, hoặc dùng collation phù hợp cho so sánh không phân biệt hoa thường. Khi đó truy vấn có thể so sánh trực tiếp cột theo semantics đã thiết kế.

Không nên bỏ UPPER một cách tùy tiện nếu nghiệp vụ yêu cầu case-insensitive matching. Việc thay đổi có thể làm kết quả khác với quy tắc so sánh hiện tại.

### 5.2 TRIM và LTRIM/RTRIM

Ví dụ:

~~~sql
WHERE TRIM(account_code) = :p_code
~~~

Nếu dữ liệu được lưu không nhất quán do khoảng trắng, có thể:

- Chuẩn hóa dữ liệu khi INSERT/UPDATE.
- Dùng cột chuẩn hóa riêng.
- Tạo function-based index trên TRIM(ACCOUNT_CODE).

~~~sql
CREATE INDEX account_code_trim_ix
    ON accounts(TRIM(account_code));
~~~

Không nên thay predicate thành ACCOUNT_CODE = :p_code nếu dữ liệu hiện có có khoảng trắng có ý nghĩa hoặc chưa được làm sạch.

### 5.3 SUBSTR

Ví dụ:

~~~sql
WHERE SUBSTR(account_code, 1, 3) = 'ABC'
~~~

Nếu ý nghĩa là tìm các chuỗi bắt đầu bằng ABC, có thể viết:

~~~sql
WHERE account_code LIKE 'ABC%'
~~~

Index B-tree có thể hỗ trợ prefix LIKE khi pattern bắt đầu bằng ký tự cố định và collation/kiểu so sánh phù hợp. Pattern bắt đầu bằng wildcard như '%ABC' không cho phép range scan thông thường trên B-tree theo cùng cách.

Nếu cần tìm theo một đoạn con ở giữa hoặc suffix, LIKE không có wildcard đầu có thể không tương đương. Khi đó cân nhắc function-based index, Oracle Text hoặc cấu trúc tìm kiếm chuyên biệt.

### 5.4 NVL và COALESCE

Predicate:

~~~sql
WHERE NVL(status, 'NEW') = :p_status
~~~

đang áp NVL lên cột. Nếu cần giữ index thường trên STATUS, có thể viết lại tương đương:

~~~sql
WHERE status = :p_status
   OR (status IS NULL AND :p_status = 'NEW')
~~~

Phép viết lại này giả định NEW là giá trị thay thế đúng theo nghiệp vụ. Nó giữ semantics của NVL: nếu STATUS là NULL thì giá trị so sánh được xem là NEW.

Oracle có thể dùng OR expansion hoặc kết hợp access paths, nhưng không đảm bảo. Kiểm tra plan và số dòng thực tế.

Nếu biểu thức NVL/COALESCE được dùng thường xuyên và ổn định, function-based index có thể phù hợp:

~~~sql
CREATE INDEX orders_status_nvl_ix
    ON orders(NVL(status, 'NEW'));
~~~

### 5.5 CASE trong WHERE

Ví dụ:

~~~sql
WHERE CASE
        WHEN :p_mode = 'A' THEN customer_id
        ELSE account_id
      END = :p_id
~~~

Hàm CASE đặt lên hai cột khác nhau khiến optimizer khó sử dụng trực tiếp index riêng trên CUSTOMER_ID hoặc ACCOUNT_ID. Nếu mode là tham số điều khiển truy vấn, có thể tách thành hai câu SQL hoặc hai nhánh:

~~~sql
WHERE (:p_mode = 'A' AND customer_id = :p_id)
   OR (:p_mode <> 'A' AND account_id = :p_id)
~~~

Tùy workload, hai câu SQL riêng với bind tương ứng có thể cho optimizer plan đơn giản và selectivity rõ hơn. Nếu dùng OR, kiểm tra OR expansion và kết quả plan.

### 5.6 ABS, ROUND và phép toán trên cột

Ví dụ:

~~~sql
WHERE ABS(balance) > :p_limit
WHERE ROUND(amount, 2) = :p_amount
WHERE salary + 100 > :p_min_salary
~~~

Một số phép toán có thể biến đổi đại số để đưa cột về dạng trực tiếp:

~~~sql
WHERE salary > :p_min_salary - 100
~~~

Với ABS:

~~~sql
WHERE balance > :p_limit
   OR balance < -:p_limit
~~~

Phép viết lại cần giữ đúng semantics với NULL, kiểu số, rounding và miền giá trị. Với ROUND(amount, 2) = :p_amount, có thể cân nhắc khoảng số phù hợp nhưng phải xác định quy tắc làm tròn và độ chính xác trước khi viết lại. Không tự thay đổi logic chỉ để tạo predicate trông sargable.

## 6. OR, IN và các điều kiện tùy chọn

OR không tự động làm index mất tác dụng. Oracle có thể dùng OR expansion, bitmap conversion hoặc nhiều index access path, tùy điều kiện và cost.

### 6.1 OR trên cùng cột

~~~sql
WHERE status = 'NEW'
   OR status = 'PENDING'
~~~

Có thể viết:

~~~sql
WHERE status IN ('NEW', 'PENDING')
~~~

IN thường rõ nghĩa hơn, nhưng không đảm bảo plan khác hoặc nhanh hơn trong mọi trường hợp.

### 6.2 OR trên các cột khác nhau

~~~sql
WHERE customer_id = :p_id
   OR account_id = :p_id
~~~

Nếu mỗi cột có index, Oracle có thể cân nhắc OR expansion hoặc bitmap operations. Nếu một nhánh rất chọn lọc còn nhánh kia trả nhiều dòng, optimizer sẽ dựa vào thống kê để chọn plan.

Không tự chia thành UNION ALL nếu hai nhánh có thể cùng trả một row, vì UNION ALL sẽ tạo duplicate mà OR chỉ trả mỗi row một lần. Nếu dùng UNION, cần tính chi phí sort/deduplication. Muốn chia nhánh phải bảo đảm các điều kiện loại trừ nhau hoặc xử lý duplicate có chủ đích.

### 6.3 Optional filter kiểu bind có thể làm plan kém ổn định

Mẫu thường gặp:

~~~sql
WHERE (:p_status IS NULL OR status = :p_status)
~~~

Mẫu này tiện vì một câu SQL phục vụ cả trường hợp có filter và không có filter. Nhưng khi bind NULL, query có thể trả gần như toàn bộ bảng; khi bind một status hiếm, query chỉ trả ít dòng. Một plan duy nhất có thể không tốt cho cả hai tình huống.

Các lựa chọn:

- Dùng hai câu SQL riêng: có filter và không filter.
- Dùng dynamic SQL có bind variables để chỉ thêm predicate cần thiết.
- Kiểm tra adaptive cursor sharing nếu selectivity thay đổi theo bind.
- Đo và xem child cursors thay vì ép index bằng hint.

Dynamic SQL cần bind giá trị, không nối trực tiếp dữ liệu người dùng vào SQL text.

## 7. LIKE và khả năng dùng index

### 7.1 Prefix search

~~~sql
WHERE last_name LIKE 'SMI%'
~~~

Với B-tree index trên LAST_NAME, Oracle có thể dùng range scan để tìm các khóa bắt đầu bằng SMI, tùy collation và optimizer cost.

### 7.2 Leading wildcard

~~~sql
WHERE last_name LIKE '%SMITH'
WHERE last_name LIKE '%MIT%'
~~~

Index B-tree thông thường không thể xác định một khoảng khóa liên tục bắt đầu từ một giá trị cố định vì pattern cho phép mọi prefix. Full scan có thể là lựa chọn phù hợp.

Nếu workload cần tìm kiếm contains hoặc linguistic search, xem Oracle Text hoặc giải pháp search chuyên biệt. Function-based index không tự giải quyết mọi pattern wildcard ở giữa chuỗi.

### 7.3 Case-insensitive prefix

Nếu truy vấn:

~~~sql
WHERE UPPER(last_name) LIKE 'SMI%'
~~~

có thể tạo:

~~~sql
CREATE INDEX employees_upper_last_name_ix
    ON employees(UPPER(last_name));
~~~

Sau đó kiểm tra plan và collation. Với NLS_SORT/NLS_COMP hoặc collation khai báo, biểu thức index có thể phụ thuộc quy tắc sắp xếp; không thay đổi session NLS tùy tiện.

## 8. NULL và index B-tree

Oracle B-tree index không lưu entry khi toàn bộ key columns của một row đều NULL. Đây là điểm quan trọng khi truy vấn:

~~~sql
WHERE nullable_column IS NULL
~~~

Nếu chỉ có index đơn cột trên NULLABLE_COLUMN, index không chứa các row có giá trị NULL cho cột đó. Vì vậy index này không thể trực tiếp tìm toàn bộ các row NULL như một range scan thông thường.

Với composite index, row có thể vẫn có entry nếu ít nhất một key column khác không NULL. Ví dụ index:

~~~sql
CREATE INDEX orders_status_date_ix
    ON orders(status, order_date);
~~~

Một row có STATUS NULL nhưng ORDER_DATE khác NULL vẫn có index entry. Tuy nhiên, việc dùng index cho predicate STATUS IS NULL còn phụ thuộc leading column, điều kiện còn lại và cost.

Nếu cần truy vấn IS NULL thường xuyên, có thể:

- Kết hợp cột khác không NULL vào composite index phù hợp.
- Dùng function-based index có biểu thức thay NULL bằng một sentinel không thể xuất hiện trong dữ liệu hợp lệ.
- Thiết kế lại dữ liệu/nullable semantics nếu phù hợp.

Ví dụ function-based index:

~~~sql
CREATE INDEX orders_status_nvl_ix
    ON orders(NVL(status, '#NULL#'));
~~~

Sentinel phải được bảo đảm không thể là giá trị hợp lệ; truy vấn phải dùng cùng biểu thức. Nếu dữ liệu có thể chứa sentinel, kết quả sẽ sai.

## 9. Composite index và thứ tự cột

Index nhiều cột được sắp xếp theo thứ tự các key expression trong định nghĩa index. Leading column thường quyết định liệu một điều kiện có thể xác định vùng tìm kiếm hiệu quả hay không.

Giả sử:

~~~sql
CREATE INDEX orders_customer_date_ix
    ON orders(customer_id, order_date);
~~~

Predicate:

~~~sql
WHERE customer_id = :p_customer_id
  AND order_date >= :p_start
  AND order_date <  :p_end
~~~

có thể sử dụng hai cột theo thứ tự phù hợp: equality trên CUSTOMER_ID, rồi range trên ORDER_DATE.

### 9.1 Chỉ lọc cột leading

~~~sql
WHERE customer_id = :p_customer_id
~~~

Index có thể được dùng vì CUSTOMER_ID là leading column.

### 9.2 Lọc cột thứ hai nhưng không có leading column

~~~sql
WHERE order_date >= :p_start
  AND order_date < :p_end
~~~

Index trên (CUSTOMER_ID, ORDER_DATE) không thường được dùng như một range scan đơn giản chỉ theo ORDER_DATE, vì các giá trị ORDER_DATE được nhóm bên trong từng CUSTOMER_ID.

Oracle có thể cân nhắc INDEX SKIP SCAN nếu số distinct của leading column thấp và cost phù hợp, nhưng không nên thiết kế index dựa vào kỳ vọng skip scan cho workload chính.

### 9.3 Equality trước, range sau

Với index (A, B, C), dạng predicate thường thuận lợi là:

~~~sql
WHERE A = :a
  AND B = :b
  AND C >= :c1
  AND C < :c2
~~~

Điều kiện equality trên các leading columns giúp định vị vùng khóa, sau đó range trên cột tiếp theo giới hạn phạm vi. Các điều kiện trên cột sau range vẫn có thể được kiểm tra trong index/table nhưng thường không thu hẹp cùng cách như leading equality.

### 9.4 Chọn thứ tự cột theo workload

Không nên chỉ sắp xếp index theo cột có selectivity cao nhất. Cần xét:

- Các predicate thường đi cùng nhau.
- Equality và range predicate.
- ORDER BY/GROUP BY cần hỗ trợ.
- Join columns.
- Số lượng distinct và phân bố dữ liệu.
- Chi phí DML và dung lượng index.
- Các truy vấn khác dùng cùng index.

Index tốt cho một câu SQL có thể làm tăng chi phí INSERT/UPDATE/DELETE và không nhất thiết giúp toàn workload.

## 10. Function-based index

Function-based index lưu kết quả của function hoặc expression trên một hay nhiều cột. Đây là cách phù hợp khi truy vấn theo biểu thức là yêu cầu nghiệp vụ thường xuyên và không thể hoặc không nên viết lại.

### 10.1 Ví dụ UPPER

~~~sql
CREATE INDEX customers_upper_email_ix
    ON customers(UPPER(email));
~~~

Truy vấn:

~~~sql
SELECT customer_id
FROM customers
WHERE UPPER(email) = UPPER(:p_email);
~~~

Optimizer có thể dùng index nếu expression tương thích và cost có lợi.

### 10.2 Ví dụ biểu thức số

~~~sql
CREATE INDEX products_net_price_ix
    ON products(price * (1 - discount_rate));
~~~

Truy vấn:

~~~sql
SELECT product_id
FROM products
WHERE price * (1 - discount_rate) < :p_max_net_price;
~~~

Index lưu giá trị biểu thức đã tính. Điều này hữu ích nếu biểu thức phức tạp và được dùng lặp lại trong nhiều truy vấn.

### 10.3 User-defined function

Nếu expression dùng user-defined PL/SQL function, function phải được khai báo DETERMINISTIC. Đây là cam kết của lập trình viên rằng cùng input luôn trả cùng output; Oracle không tự xác minh logic thực sự deterministic.

Nếu function đọc bảng khác, phụ thuộc session state, SYSDATE, USER, NLS hoặc trạng thái thay đổi khác, việc đánh dấu DETERMINISTIC có thể làm index chứa giá trị cũ hoặc không đúng. Chỉ khai báo DETERMINISTIC khi cam kết đó thực sự đúng.

Khi semantics của function thay đổi, cần đánh giá rebuild function-based index và các dependent objects.

### 10.4 Thu thập statistics sau khi tạo

Sau khi tạo function-based index, thu thập statistics cho index và bảng:

~~~sql
BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'CUSTOMERS',
        cascade => TRUE
    );
END;
/
~~~

Statistics giúp optimizer đánh giá selectivity và chi phí của index biểu thức.

### 10.5 NLS và tính nhất quán biểu thức

Nếu biểu thức index thực hiện implicit conversion sang character hoặc phụ thuộc NLS, thay đổi NLS session có thể ảnh hưởng kết quả. Tránh function-based index dựa trên chuyển đổi ngày/số sang chuỗi không có format rõ ràng. Dùng format model tường minh và hiểu collation của biểu thức.

### 10.6 Xem biểu thức đã được index hóa

~~~sql
SELECT index_name,
       column_position,
       column_expression
FROM user_ind_expressions
WHERE table_name = 'CUSTOMERS'
ORDER BY index_name, column_position;
~~~

So sánh expression trong metadata với expression của truy vấn. Tên hàm, tham số, kiểu dữ liệu và conversion có thể ảnh hưởng việc optimizer nhận diện index.

## 11. Virtual column như một cách đặt tên cho biểu thức

Virtual column định nghĩa một cột dựa trên expression. Giá trị được suy ra từ các cột khác; có thể tạo index và gather statistics trên virtual column.

Ví dụ:

~~~sql
ALTER TABLE customers ADD (
    normalized_email
        GENERATED ALWAYS AS (UPPER(email)) VIRTUAL
);

CREATE INDEX customers_normalized_email_ix
    ON customers(normalized_email);
~~~

Truy vấn:

~~~sql
SELECT customer_id
FROM customers
WHERE normalized_email = UPPER(:p_email);
~~~

Ưu điểm:

- Expression có tên nghiệp vụ rõ ràng.
- Có thể thu thập column statistics.
- Dễ tham chiếu từ nhiều câu SQL.
- Có thể đặt constraint hoặc index phù hợp với virtual column theo quy tắc Oracle.

Virtual column không tự động làm mọi truy vấn tương đương dùng index; predicate cần tham chiếu virtual column hoặc optimizer phải nhận diện expression tương ứng.

## 12. Partition pruning và predicate trên partition key

Nếu bảng partition theo ngày hoặc số, predicate trực tiếp trên partition key thường giúp Oracle loại bỏ partition không liên quan (partition pruning).

Ví dụ bảng partition theo ORDER_DATE:

~~~sql
SELECT *
FROM orders
WHERE order_date >= :p_start
  AND order_date <  :p_end;
~~~

Khoảng trực tiếp trên partition key có thể giúp pruning.

Ngược lại:

~~~sql
WHERE TRUNC(order_date) = :p_day
~~~

có thể làm partition pruning khó hơn nếu partition key là ORDER_DATE gốc. Viết lại bằng khoảng ngày nửa mở thường giúp cả partition pruning và index range access.

Partition pruning không phải index access. Oracle có thể prune partition rồi full scan bên trong partition còn lại; đây vẫn có thể là plan tốt.

Với partition key expression hoặc virtual column, cần kiểm tra partitioning strategy và pruning details trong plan. Không suy luận chỉ từ việc predicate có vẻ tương đương.

## 13. Index access path không được bảo đảm

Ngay cả khi predicate sargable và index phù hợp, Oracle vẫn có thể chọn FULL TABLE SCAN.

### 13.1 Selectivity thấp

Nếu truy vấn trả 60–90% số dòng, dùng index có thể phải đọc nhiều index blocks rồi truy cập nhiều table blocks theo ROWID. Full scan có thể rẻ hơn vì đọc tuần tự và tận dụng multiblock I/O.

### 13.2 Clustering factor

Clustering factor mô tả mức độ tương quan giữa thứ tự index key và vị trí các row trong table blocks. Nếu các row cùng key nằm rải rác trên nhiều block, index range scan có thể gây nhiều random table block reads.

### 13.3 Table nhỏ

Với bảng rất nhỏ, full scan có thể chỉ cần đọc vài block và rẻ hơn đi qua root/branch/leaf của index rồi quay lại table.

### 13.4 Statistics không chính xác

NUM_ROWS, NDV, histogram hoặc index statistics cũ có thể làm optimizer đánh giá sai chi phí. Gather statistics phù hợp trước khi dùng hint ép index.

### 13.5 INDEX FULL SCAN và INDEX FAST FULL SCAN

Oracle có nhiều dạng index access:

| Operation | Ý nghĩa khái quát |
|---|---|
| INDEX UNIQUE SCAN | Tìm một key duy nhất |
| INDEX RANGE SCAN | Quét một khoảng khóa |
| INDEX RANGE SCAN DESCENDING | Quét range theo chiều ngược |
| INDEX SKIP SCAN | Khai thác index composite khi thiếu một số leading key trong điều kiện phù hợp |
| INDEX FULL SCAN | Đọc toàn bộ index theo thứ tự khóa |
| INDEX FAST FULL SCAN | Đọc toàn bộ index như cấu trúc lưu trữ, không bảo đảm thứ tự |

Không phải cứ thấy INDEX trong plan là truy vấn đã dùng một range scan chọn lọc.

## 14. Cách đọc Predicate Information

Predicate Information giúp biết điều kiện được dùng làm access predicate hay chỉ filter sau khi lấy row source.

Ví dụ:

~~~text
Predicate Information (identified by operation id):
---------------------------------------------------
  2 - access("ORDER_DATE">=:B1 AND "ORDER_DATE"<:B2)
  1 - filter("STATUS"='SHIPPED')
~~~

- ACCESS: predicate được dùng để xác định key/range cho access path.
- FILTER: predicate được áp dụng để lọc các dòng sau khi operation lấy được chúng.

FILTER không đồng nghĩa luôn là xấu. Có điều kiện không thể dùng làm index start/stop key nhưng vẫn rẻ để filter sau. Quan trọng là xem số dòng và chi phí ở operation.

### 14.1 Xem plan thực tế

Thực thi câu SQL với runtime statistics:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id,
       order_date
FROM orders
WHERE order_date >= :p_start
  AND order_date <  :p_end;
~~~

Sau khi fetch hết kết quả:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PEEKED_BINDS'
    )
);
~~~

Kiểm tra:

- Operation nào được chọn.
- Index name và access predicate.
- E-Rows so với A-Rows.
- Starts, Buffers, Reads và A-Time.
- Bind values được peek (nếu có).
- Có conversion/hàm nào bao quanh cột trong Predicate Information không.

### 14.2 Không chỉ dùng EXPLAIN PLAN

EXPLAIN PLAN cho biết optimizer tạo plan trong môi trường explain. Plan thực tế có thể khác do bind values, child cursor, adaptive features, session settings hoặc statistics. Khi chẩn đoán production, ưu tiên DISPLAY_CURSOR với SQL_ID và child number của cursor thực tế.

## 15. Ví dụ tổng hợp: từ predicate không thân thiện đến predicate có thể dùng index

Giả sử bảng ORDERS có:

~~~sql
CREATE INDEX orders_date_ix ON orders(order_date);
CREATE INDEX orders_upper_status_ix ON orders(UPPER(status));
~~~

Truy vấn ban đầu:

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(order_date) = TO_DATE(:p_day, 'YYYY-MM-DD')
  AND UPPER(status) = UPPER(:p_status)
  AND TO_CHAR(order_id) = :p_order_id;
~~~

Các vấn đề:

1. TRUNC bao quanh ORDER_DATE, không khớp index gốc ORDER_DATE.
2. UPPER bao quanh STATUS, nhưng đã có function-based index phù hợp.
3. TO_CHAR bao quanh ORDER_ID; nếu ORDER_ID là NUMBER và bind là chuỗi, conversion đang ở phía cột.

Phiên bản viết lại:

~~~sql
SELECT order_id
FROM orders
WHERE order_date >= :p_day_start
  AND order_date <  :p_next_day_start
  AND UPPER(status) = UPPER(:p_status)
  AND order_id = :p_order_id;
~~~

Trong phiên bản này:

- Bind p_day_start và p_next_day_start có kiểu DATE.
- Bind p_order_id có kiểu NUMBER.
- UPPER(STATUS) có function-based index tương ứng.
- ORDER_DATE và ORDER_ID được so sánh trực tiếp với bind cùng kiểu.

Optimizer có thể chọn một trong các index hoặc kết hợp access paths tùy selectivity và cost. Không có cam kết sẽ dùng cả ba index.

## 16. Bài lab: quan sát predicate và index access

Các bước sau tạo bảng lab độc lập. Chạy trong schema thực hành, không dùng tên bảng production.

### 16.1 Tạo bảng

~~~sql
CREATE TABLE sargable_lab (
    id          NUMBER PRIMARY KEY,
    created_at  DATE NOT NULL,
    status      VARCHAR2(20),
    account_code VARCHAR2(30),
    amount      NUMBER
);
~~~

### 16.2 Nạp dữ liệu

~~~sql
INSERT INTO sargable_lab
    (id, created_at, status, account_code, amount)
SELECT level,
       DATE '2026-01-01' + MOD(level, 365)
           + NUMTODSINTERVAL(MOD(level, 86400), 'SECOND'),
       CASE MOD(level, 4)
           WHEN 0 THEN 'NEW'
           WHEN 1 THEN 'PENDING'
           WHEN 2 THEN 'SHIPPED'
           ELSE 'CANCELLED'
       END,
       'AC' || TO_CHAR(MOD(level, 10000), 'FM0000'),
       MOD(level * 17, 100000) / 100
FROM dual
CONNECT BY level <= 200000;

COMMIT;
~~~

### 16.3 Tạo index và gather statistics

~~~sql
CREATE INDEX sargable_lab_date_ix
    ON sargable_lab(created_at);

CREATE INDEX sargable_lab_status_ix
    ON sargable_lab(status);

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SARGABLE_LAB',
        cascade => TRUE
    );
END;
/
~~~

### 16.4 So sánh TRUNC với khoảng ngày

Predicate dùng hàm:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*)
FROM sargable_lab
WHERE TRUNC(created_at) = DATE '2026-03-01';
~~~

Xem plan:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL, NULL, 'ALLSTATS LAST +PREDICATE'
    )
);
~~~

Predicate khoảng:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       COUNT(*)
FROM sargable_lab
WHERE created_at >= DATE '2026-03-01'
  AND created_at <  DATE '2026-03-02';
~~~

Xem plan sau câu lệnh thứ hai. So sánh access predicate, filter predicate, buffers và operation. Với bảng lab, optimizer vẫn có thể chọn full scan nếu số dòng trả về hoặc chi phí làm full scan rẻ hơn; mục tiêu là quan sát sự khác biệt của predicate.

### 16.5 Thử function-based index

~~~sql
CREATE INDEX sargable_lab_trunc_date_ix
    ON sargable_lab(TRUNC(created_at));

BEGIN
    DBMS_STATS.GATHER_TABLE_STATS(
        ownname => USER,
        tabname => 'SARGABLE_LAB',
        cascade => TRUE
    );
END;
/
~~~

Chạy lại truy vấn TRUNC(created_at) và quan sát optimizer có chọn index mới hay không.

### 16.6 Dọn lab

~~~sql
DROP TABLE sargable_lab PURGE;
~~~

Chỉ chạy DROP TABLE nếu đây là bảng lab vừa tạo và không chứa dữ liệu cần giữ.

## 17. Những lỗi thường gặp

| Lỗi | Vì sao bất lợi | Cách xử lý |
|---|---|---|
| TRUNC(date_col) = ngày | Hàm bao quanh cột index | Dùng khoảng ngày nửa mở |
| TO_CHAR(date_col) = chuỗi | Chuyển cột DATE thành text, phụ thuộc NLS nếu thiếu format | So sánh DATE/TIMESTAMP với bind đúng kiểu |
| TO_DATE(date_col, format) | DATE bị chuyển thành text rồi parse lại | Không gọi TO_DATE trên cột DATE |
| TO_NUMBER(varchar_col) = số | Có thể ngăn index và gây ORA-01722 | Bind chuỗi đúng kiểu hoặc chuẩn hóa dữ liệu |
| UPPER(col) nhưng chỉ có index col | Index không chứa giá trị UPPER(col) | Function-based index hoặc normalized column |
| NVL(col, value) = bind | Hàm bao quanh cột | Rewrite bằng OR nếu tương đương hoặc tạo function-based index |
| LIKE '%text' | Wildcard đầu ngăn range scan B-tree thông thường | Oracle Text hoặc mô hình tìm kiếm khác |
| Lọc cột thứ hai của composite index | Không có leading key | Thiết kế index theo predicate workload |
| Chỉ nhìn EXPLAIN PLAN | Không chắc là plan đã chạy | Dùng DBMS_XPLAN.DISPLAY_CURSOR |
| Ép INDEX hint ngay | Có thể ép plan đắt hơn full scan | Sửa predicate/stats rồi đo cost |
| So sánh bind sai kiểu | Có thể gây implicit conversion trên cột | Bind đúng kiểu dữ liệu |
| Dùng sentinel cho NULL nhưng sentinel có thể tồn tại | Va chạm giá trị và sai kết quả | Chọn sentinel được constraint bảo vệ |

## 18. Checklist khi viết predicate

Trước khi hoàn thiện câu SQL, hãy tự hỏi:

1. Cột trong WHERE có index không?
2. Predicate có tham chiếu trực tiếp cột hay bao quanh cột bằng function/expression?
3. Có thể viết lại thành equality hoặc range trên cột gốc mà vẫn giữ semantics không?
4. Với ngày giờ, đã dùng khoảng nửa mở chưa?
5. Bind variable có đúng kiểu với cột không?
6. Có implicit conversion hoặc NLS-dependent conversion không?
7. LIKE pattern có wildcard ở đầu không?
8. OR predicate có thể dùng IN hoặc tách query theo nhánh không?
9. Nếu dùng composite index, predicate có leading columns không?
10. Cần function-based index hay virtual column cho biểu thức ổn định không?
11. Function-based index có phụ thuộc NLS hoặc user-defined function không?
12. Statistics của bảng và index có đủ mới không?
13. Predicate được ghi trong plan là ACCESS hay FILTER?
14. E-Rows và A-Rows có chênh lệch lớn không?
15. Index access có thực sự rẻ hơn full scan với selectivity hiện tại không?
16. Đã đo buffers và elapsed time với bind values đại diện chưa?

## 19. Tổng kết

Để viết predicate có khả năng khai thác index trong Oracle:

- Ưu tiên so sánh trực tiếp cột với literal hoặc bind variable cùng kiểu dữ liệu.
- Tránh đặt TRUNC, TO_CHAR, TO_NUMBER, UPPER, LOWER, NVL, SUBSTR hoặc phép toán không cần thiết lên cột được index hóa.
- Với ngày giờ, dùng khoảng nửa mở: lớn hơn hoặc bằng đầu kỳ và nhỏ hơn đầu kỳ kế tiếp.
- Tránh implicit conversion, đặc biệt khi Oracle phải chuyển đổi chính giá trị cột.
- Dùng prefix LIKE khi cần tìm chuỗi bắt đầu bằng một giá trị cố định; leading wildcard không hỗ trợ range scan B-tree thông thường.
- Thiết kế composite index theo leading columns và predicate thực tế.
- Khi truy vấn theo biểu thức là nhu cầu bền vững, dùng function-based index hoặc virtual column.
- Không mặc định index luôn tốt hơn full scan. Optimizer chọn access path theo cost.
- Xác nhận bằng execution plan thực tế, Predicate Information, E-Rows/A-Rows, Buffers và thời gian chạy.

Một predicate tốt vừa giữ đúng logic nghiệp vụ, vừa cho optimizer thông tin rõ ràng về khoảng dữ liệu cần tìm. Viết lại biểu thức chỉ có ý nghĩa khi kết quả tương đương; sau đó phải đo trên dữ liệu và bind values đại diện để xác nhận lợi ích.

## 20. Tài liệu Oracle tham khảo

- Oracle Database 19c SQL Language Reference, “Data Type Comparison Rules”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Data-Type-Comparison-Rules.html
- Oracle Database 19c SQL Language Reference, “CREATE INDEX”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html
- Oracle Database 19c SQL Tuning Guide, “Optimizer Access Paths”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/optimizer-access-paths.html
- Oracle Database 19c Database Development Guide, “Using Indexes in Database Applications”: https://docs.oracle.com/en/database/oracle/oracle-database/19/adfns/indexes.html
- Oracle Database 19c SQL Tuning Guide, “Generating and Displaying Execution Plans”: https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/generating-and-displaying-execution-plans.html
