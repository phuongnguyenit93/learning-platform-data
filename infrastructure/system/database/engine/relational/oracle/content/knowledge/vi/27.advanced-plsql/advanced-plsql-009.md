# DETERMINISTIC và trách nhiệm bảo đảm tính xác định

Trong PL/SQL, từ khóa **DETERMINISTIC** là một lời cam kết do người viết hàm đưa ra với Oracle Database: với cùng các giá trị đầu vào, function luôn trả về cùng một kết quả và không tạo side effect. Oracle dựa vào lời cam kết này trong những ngữ cảnh tối ưu hóa hoặc lưu trữ kết quả của biểu thức, chẳng hạn function-based index và một số loại materialized view.

Điểm quan trọng nhất là Oracle **không tự chứng minh function thật sự deterministic**. Khi khai báo DETERMINISTIC, lập trình viên chịu trách nhiệm bảo đảm điều đó trong mọi lần gọi hợp lệ. Nếu function đọc trạng thái thay đổi theo thời gian, phụ thuộc session, đọc bảng có thể cập nhật hoặc tạo side effect, lời cam kết có thể sai. Khi đó kết quả truy vấn hoặc dữ liệu được lưu trong index có thể không còn phản ánh logic hiện tại.

Ví dụ function tính một mức phí từ hai tham số:

~~~sql
CREATE OR REPLACE FUNCTION calculate_fee (
    p_amount IN NUMBER,
    p_rate   IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(p_amount * p_rate, 2);
END calculate_fee;
/
~~~

Kết quả chỉ phụ thuộc P_AMOUNT và P_RATE. Nếu cùng hai giá trị đầu vào, function trả cùng một kết quả và không thay đổi trạng thái bên ngoài, lời khai báo DETERMINISTIC phù hợp.

Ngược lại, function dùng SYSDATE, DBMS_RANDOM, sequence NEXTVAL, package variable có thể thay đổi, session context hoặc bảng cấu hình có thể được cập nhật không nên được khai báo DETERMINISTIC nếu những yếu tố đó không được biểu diễn đầy đủ trong đầu vào.

Bài học trình bày ý nghĩa của DETERMINISTIC, ranh giới giữa tính xác định và trạng thái môi trường, cách khai báo function, ứng dụng với function-based index, nguy cơ dữ liệu index cũ khi thay đổi function, sự khác biệt với RESULT_CACHE và cách kiểm chứng lời cam kết.

## 1. Deterministic function là gì?

Một function deterministic phải thỏa hai ý chính:

1. **Cùng đầu vào, cùng kết quả**: nếu function được gọi với cùng các giá trị tham số, kết quả trả về phải giống nhau.
2. **Không có side effect**: việc gọi function không được thay đổi trạng thái bên ngoài theo cách làm ảnh hưởng tới những lần gọi sau hoặc làm thay đổi dữ liệu nghiệp vụ.

Tính xác định cần được xét trên toàn bộ ngữ cảnh thực thi. Không chỉ nhìn các tham số khai báo trong function. Nếu function âm thầm đọc giờ hệ thống, biến package, bảng cấu hình, NLS setting hoặc session context, các giá trị đó cũng ảnh hưởng tới kết quả dù không xuất hiện trong danh sách tham số.

### 1.1. Function thuần theo đầu vào

Ví dụ:

~~~sql
CREATE OR REPLACE FUNCTION normalize_amount (
    p_amount IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(p_amount, 2);
END normalize_amount;
/
~~~

Với cùng P_AMOUNT, phép tính ROUND cho cùng kết quả. Function không đọc bảng, không đọc biến session và không ghi dữ liệu.

Một ví dụ khác:

~~~sql
CREATE OR REPLACE FUNCTION amount_bucket (
    p_amount IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN TRUNC(p_amount / 1000);
END amount_bucket;
/
~~~

Nếu truyền 2500, kết quả luôn là 2. Nếu truyền 3999, kết quả luôn là 3. Logic chỉ phụ thuộc giá trị NUMBER đầu vào.

### 1.2. DETERMINISTIC không phải lời yêu cầu Oracle tự kiểm tra

Khai báo:

~~~sql
RETURN NUMBER DETERMINISTIC
~~~

là một assertion của lập trình viên. Oracle không phân tích toàn bộ thân function để chứng minh mọi nhánh đều trả cùng kết quả cho cùng đầu vào.

Một function có thể được biên dịch dù người viết đã khai báo DETERMINISTIC nhưng thân function lại đọc SYSDATE hoặc một bảng thay đổi. Việc biên dịch thành công không chứng minh lời cam kết đúng.

Nếu khai báo sai, Oracle có thể sử dụng function theo các giả định không còn đúng. Kết quả có thể không xác định hoặc không nhất quán; function-based index và các object phụ thuộc có thể chứa giá trị không phản ánh logic hiện tại.

### 1.3. Tính xác định không đồng nghĩa với việc function chỉ được gọi một lần

DETERMINISTIC không phải cam kết:
- Oracle sẽ gọi function đúng một lần.
- Oracle luôn lưu kết quả vào cache.
- Mỗi tập tham số chỉ được tính một lần trong một câu SELECT.
- Hai câu SQL khác nhau chắc chắn dùng chung kết quả.
- Function sẽ chạy nhanh hơn trong mọi tình huống.

Oracle có thể tận dụng lời khai báo để chọn cách thực thi phù hợp, nhưng số lần gọi thực tế không phải hợp đồng của ứng dụng. Không viết logic nghiệp vụ phụ thuộc vào số lần function được gọi.

## 2. Cú pháp khai báo DETERMINISTIC

DETERMINISTIC được khai báo trong phần heading của function, sau kiểu trả về.

### 2.1. Standalone function

~~~sql
CREATE OR REPLACE FUNCTION calculate_fee (
    p_amount IN NUMBER,
    p_rate   IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(p_amount * p_rate, 2);
END calculate_fee;
/
~~~

Caller có thể dùng function trong PL/SQL:

~~~sql
DECLARE
    l_fee NUMBER;
BEGIN
    l_fee := calculate_fee(100000, 0.05);
    DBMS_OUTPUT.PUT_LINE(l_fee);
END;
/
~~~

Và trong SQL khi function đáp ứng các quy tắc sử dụng function trong SQL:

~~~sql
SELECT calculate_fee(100000, 0.05) AS fee
FROM dual;
~~~

### 2.2. Function trong package

Có thể công bố function deterministic trong package specification:

~~~sql
CREATE OR REPLACE PACKAGE pricing_api AS
    FUNCTION calculate_fee (
        p_amount IN NUMBER,
        p_rate   IN NUMBER
    ) RETURN NUMBER DETERMINISTIC;
END pricing_api;
/
~~~

Package body triển khai function:

~~~sql
CREATE OR REPLACE PACKAGE BODY pricing_api AS

    FUNCTION calculate_fee (
        p_amount IN NUMBER,
        p_rate   IN NUMBER
    ) RETURN NUMBER DETERMINISTIC
    IS
    BEGIN
        RETURN ROUND(p_amount * p_rate, 2);
    END calculate_fee;

END pricing_api;
/
~~~

DETERMINISTIC phải được công bố nhất quán trong khai báo function. Khi function là một phần public API của package, caller và Oracle cần thấy thuộc tính này qua package specification.

### 2.3. DETERMINISTIC chỉ dành cho function

DETERMINISTIC là thuộc tính của function, không phải của procedure. Procedure không trả về một giá trị theo cùng mô hình để Oracle sử dụng như một biểu thức deterministic.

Không dùng từ khóa này để mô tả một procedure không có side effect. Nếu cần bảo đảm một quy trình không thay đổi trạng thái, đó là một hợp đồng thiết kế khác.

### 2.4. Thay đổi thân function không tự động chứng minh lại tính xác định

Khi sửa function, người bảo trì phải đánh giá lại:
- Kết quả có còn chỉ phụ thuộc vào tham số không?
- Có thêm lời gọi tới function không deterministic không?
- Có thêm truy vấn bảng hoặc đọc trạng thái session không?
- Có side effect mới không?
- Có function-based index, materialized view hoặc object khác phụ thuộc không?

Việc giữ nguyên từ khóa DETERMINISTIC khi sửa code không có nghĩa function vẫn đáp ứng cam kết.

## 3. Những nguồn phụ thuộc làm function mất tính xác định

Câu hỏi hữu ích nhất khi xem một function là: **Nếu gọi lại với cùng các tham số, có điều gì bên ngoài function có thể đã thay đổi và làm kết quả khác đi không?**

Nếu câu trả lời là có, function chưa thể được xem là deterministic trừ khi trạng thái đó được cố định hoặc được đưa vào đầu vào một cách đầy đủ.

### 3.1. Thời gian hệ thống

Function sau không deterministic:

~~~sql
CREATE OR REPLACE FUNCTION current_year
RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN EXTRACT(YEAR FROM SYSDATE);
END current_year;
/
~~~

Cùng một lần gọi không có tham số nhưng kết quả có thể khác khi năm thay đổi. SYSDATE là trạng thái thời gian bên ngoài đầu vào.

Nếu nghiệp vụ cần tính năm từ một ngày do caller cung cấp, hãy đưa ngày vào tham số:

~~~sql
CREATE OR REPLACE FUNCTION year_of_date (
    p_date IN DATE
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN EXTRACT(YEAR FROM p_date);
END year_of_date;
/
~~~

Với cùng P_DATE, kết quả năm không phụ thuộc ngày hiện tại của server.

### 3.2. Số ngẫu nhiên

Function sử dụng DBMS_RANDOM không deterministic:

~~~sql
CREATE OR REPLACE FUNCTION random_token
RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN DBMS_RANDOM.VALUE;
END random_token;
/
~~~

Cùng một bộ tham số rỗng nhưng mỗi lần gọi có thể cho một giá trị khác. Không khai báo DETERMINISTIC cho function tạo số ngẫu nhiên, mã token ngẫu nhiên hoặc kết quả phụ thuộc random seed/session.

### 3.3. Sequence

Function đọc sequence NEXTVAL không deterministic:

~~~sql
CREATE OR REPLACE FUNCTION next_business_id
RETURN NUMBER DETERMINISTIC
IS
    l_id NUMBER;
BEGIN
    SELECT business_seq.NEXTVAL
    INTO l_id
    FROM dual;

    RETURN l_id;
END next_business_id;
/
~~~

Mỗi lần gọi có thể lấy một giá trị sequence mới. Function còn có side effect ở cấp database vì NEXTVAL làm sequence tiến lên.

Không dùng function deterministic để tạo ID duy nhất. Dùng sequence trực tiếp hoặc cơ chế sinh khóa phù hợp.

### 3.4. Package variable và trạng thái global

~~~sql
CREATE OR REPLACE PACKAGE runtime_state AS
    g_multiplier NUMBER := 1;
END runtime_state;
/
~~~

~~~sql
CREATE OR REPLACE FUNCTION multiply_by_runtime_setting (
    p_value IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN p_value * runtime_state.g_multiplier;
END multiply_by_runtime_setting;
/
~~~

Nếu G_MULTIPLIER thay đổi trong session hoặc package state được khởi tạo lại, cùng P_VALUE có thể tạo kết quả khác. Tham số nhìn thấy của function không thể hiện toàn bộ dữ liệu quyết định kết quả.

Nếu hệ số là một phần của phép tính, hãy truyền nó như tham số:

~~~sql
CREATE OR REPLACE FUNCTION multiply_value (
    p_value      IN NUMBER,
    p_multiplier IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN p_value * p_multiplier;
END multiply_value;
/
~~~

### 3.5. Session context và người dùng hiện tại

Những giá trị như USER, SYS_CONTEXT, client identifier, application context hoặc thông tin session có thể khác giữa các session. Nếu function dùng chúng để quyết định kết quả, cùng tham số rõ ràng chưa chắc cho cùng kết quả.

Ví dụ:

~~~sql
CREATE OR REPLACE FUNCTION current_user_label (
    p_suffix IN VARCHAR2
) RETURN VARCHAR2 DETERMINISTIC
IS
BEGIN
    RETURN SYS_CONTEXT('USERENV', 'SESSION_USER') || p_suffix;
END current_user_label;
/
~~~

Hai session khác nhau có thể nhận kết quả khác nhau cho cùng P_SUFFIX. Không nên khai báo function này deterministic.

Nếu kết quả cần phụ thuộc user, truyền một định danh user rõ ràng vào function chỉ khi quy tắc tính thực sự thuần theo định danh đó; nếu cần kiểm tra quyền hiện tại, hãy thực hiện kiểm tra trong tầng phù hợp thay vì biến một kiểm tra session thành hàm deterministic.

### 3.6. NLS, timezone và định dạng ngầm định

Một function định dạng ngày hoặc số có thể phụ thuộc NLS setting nếu không chỉ định định dạng và quy tắc chuyển đổi rõ ràng.

Ví dụ, TO_CHAR(date) không có format model có thể phụ thuộc NLS_DATE_FORMAT. Một biểu thức chuyển chuỗi sang ngày mà không có format rõ có thể phụ thuộc NLS_DATE_FORMAT của session.

Để giảm phụ thuộc ngầm, dùng:
- Format model rõ ràng.
- NLS parameter rõ ràng khi hàm cần chúng.
- Datatype DATE/TIMESTAMP thay vì chuỗi định dạng theo session.
- Quy tắc timezone rõ ràng khi xử lý thời gian có múi giờ.

Tuy nhiên, chỉ thêm format model chưa đủ nếu function còn đọc trạng thái session khác.

### 3.7. Đọc bảng có thể thay đổi

Function tra cứu mức giảm giá từ bảng:

~~~sql
CREATE OR REPLACE FUNCTION customer_discount (
    p_customer_id IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
    l_discount NUMBER;
BEGIN
    SELECT discount_rate
    INTO l_discount
    FROM customer_discount_config
    WHERE customer_id = p_customer_id;

    RETURN l_discount;
END customer_discount;
/
~~~

Nếu bảng CUSTOMER_DISCOUNT_CONFIG được cập nhật, cùng P_CUSTOMER_ID có thể trả mức giảm giá khác. Function phụ thuộc database state không được thể hiện trong tham số.

Không khai báo function như vậy deterministic chỉ vì bảng cấu hình thường ít thay đổi. "Ít thay đổi" không đồng nghĩa "không thể thay đổi".

Nếu cần tra cứu cấu hình hiện hành, dùng SQL phù hợp hoặc cân nhắc RESULT_CACHE khi đáp ứng điều kiện và chấp nhận semantics invalidation của cache. Không gắn DETERMINISTIC để che giấu dependency vào bảng.

### 3.8. Function gọi function khác

Một function chỉ deterministic nếu toàn bộ chuỗi lời gọi của nó đáp ứng cùng hợp đồng. Nếu FUNCTION_A gọi FUNCTION_B và B đọc SYSDATE, package variable hoặc bảng mutable, A cũng không deterministic dù thân A chỉ có một dòng RETURN FUNCTION_B(...).

Khi đánh giá, đi theo dependency graph:
- Function trực tiếp gọi.
- Package variable mà function được gọi đọc.
- SQL statement mà function thực hiện.
- Built-in có phụ thuộc session hoặc môi trường.
- External procedure/service được gọi gián tiếp.

Không chỉ kiểm tra vài dòng thân function ở lớp ngoài cùng.

## 4. Side effect và function deterministic

Side effect là thay đổi trạng thái bên ngoài giá trị trả về. Một function được khai báo DETERMINISTIC không được thực hiện side effect.

Ví dụ side effect:
- INSERT, UPDATE hoặc DELETE dữ liệu nghiệp vụ.
- Thay đổi package variable hoặc global state.
- Ghi file hoặc gọi dịch vụ bên ngoài có trạng thái.
- Gửi thông báo.
- Tăng sequence.
- Thay đổi session state.
- Thực hiện autonomous transaction để ghi log.

Không nên khai báo deterministic cho function vừa trả giá trị vừa thay đổi trạng thái.

### 4.1. Không dùng function deterministic để ghi audit

Một function như:

~~~sql
CREATE OR REPLACE FUNCTION audit_and_return (
    p_value IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    INSERT INTO audit_log(value_logged)
    VALUES (p_value);

    RETURN p_value;
END audit_and_return;
/
~~~

không đáp ứng hợp đồng deterministic vì nó ghi dữ liệu. Ngay cả khi giá trị trả về giống nhau, side effect của các lần gọi không giống với một phép tính thuần.

Tách trách nhiệm:
- Function tính toán chỉ trả kết quả.
- Procedure hoặc câu DML riêng thực hiện audit.
- Caller điều phối transaction và logging.

### 4.2. Không dựa vào số lần function được thực thi

Nếu function có side effect, việc Oracle tối ưu hóa, loại bỏ hoặc tái sử dụng một phép tính có thể làm hành vi chương trình khác với kỳ vọng. Một function deterministic phải không phụ thuộc số lần được gọi.

Không dùng function trong biểu thức SQL để gửi email, ghi log hoặc tăng bộ đếm rồi kỳ vọng Oracle gọi đúng một lần cho mỗi hàng.

## 5. DETERMINISTIC và function-based index

Một ứng dụng quan trọng của deterministic function là **function-based index**. Oracle lưu giá trị của biểu thức index để truy cập dữ liệu hiệu quả. Nếu biểu thức dùng user-defined function, function phải được khai báo deterministic và thực sự đáp ứng hợp đồng đó.

Ví dụ function chuẩn hóa mức tiền thành bucket:

~~~sql
CREATE OR REPLACE FUNCTION amount_bucket (
    p_amount IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN TRUNC(p_amount / 1000);
END amount_bucket;
/
~~~

Tạo index:

~~~sql
CREATE INDEX ix_orders_amount_bucket
ON orders (amount_bucket(amount));
~~~

Truy vấn theo cùng biểu thức:

~~~sql
SELECT order_id, amount
FROM orders
WHERE amount_bucket(amount) = 2;
~~~

Optimizer có thể sử dụng function-based index khi biểu thức, predicate, thống kê và chi phí phù hợp.

### 5.1. Index lưu kết quả tính tại thời điểm DML

Khi tạo function-based index, Oracle tính biểu thức cho các hàng hiện có và lưu khóa trong index. Khi INSERT hoặc UPDATE các cột liên quan, Oracle tính lại giá trị index cho hàng bị tác động.

Điều này có nghĩa index chứa kết quả của logic function đã dùng lúc tính khóa. Nếu function phụ thuộc vào dữ liệu mutable bên ngoài hàng, thay đổi dữ liệu đó không nhất thiết làm Oracle tự tính lại tất cả khóa index.

### 5.2. Rủi ro khi function khai báo deterministic nhưng thực tế không deterministic

Giả sử amount_bucket không chỉ chia amount mà còn đọc một bảng cấu hình chứa kích thước bucket. Index được tạo khi bucket size là 1000. Sau đó bảng cấu hình đổi thành 500.

Các khóa đã lưu trong index có thể vẫn được tính theo logic/config cũ trong khi function khi được gọi trực tiếp trả kết quả mới. Truy vấn dựa vào index có nguy cơ trả dữ liệu không nhất quán.

Đây là lý do DETERMINISTIC không thể được dùng cho function phụ thuộc trạng thái thay đổi ngoài tham số.

### 5.3. Thay đổi code function cần đánh giá index phụ thuộc

Nếu sửa logic function dùng trong function-based index, các giá trị đã lưu có thể không còn tương ứng với code mới. Cần xác định tất cả index và object phụ thuộc, sau đó rebuild hoặc refresh theo đúng loại object và quy trình triển khai.

Ví dụ rebuild index:

~~~sql
ALTER INDEX ix_orders_amount_bucket REBUILD;
~~~

Không giả định chỉ CREATE OR REPLACE function là đủ để cập nhật mọi giá trị đã lưu trong index. Kiểm tra trạng thái index và kế hoạch triển khai sau khi thay đổi function.

### 5.4. Predicate cần tương thích với biểu thức index

Nếu index được tạo trên:

~~~sql
amount_bucket(amount)
~~~

truy vấn dùng cùng biểu thức:

~~~sql
WHERE amount_bucket(amount) = :bucket
~~~

là mẫu rõ ràng để optimizer xem xét index.

Nếu truy vấn dùng một phép tính khác hoặc bọc thêm hàm không tương đương, index có thể không được dùng theo cách mong đợi. Kiểm tra execution plan thay vì chỉ nhìn tên function.

### 5.5. Quyền và dependency

Function-based index phụ thuộc function và quyền thực thi function. Khi triển khai trong schema thật, cần:
- Xác định owner của bảng, index và function.
- Cấp quyền cần thiết theo quy tắc Oracle.
- Quản lý dependency khi function được thay đổi hoặc invalid.
- Kiểm tra trạng thái index sau khi compile/recompile.
- Kiểm thử INSERT/UPDATE và truy vấn sử dụng biểu thức.

Không xem DETERMINISTIC là cơ chế phân quyền hay bảo vệ dữ liệu.

## 6. DETERMINISTIC và materialized view

Một số định nghĩa materialized view có thể sử dụng user-defined function. Oracle có các yêu cầu và hạn chế riêng đối với function được dùng trong materialized view, query rewrite và refresh. Tính xác định của function là một yếu tố quan trọng vì dữ liệu materialized được lưu lại để dùng về sau.

Khi function thay đổi hoặc một dependency thay đổi, cần xem xét:
- Materialized view có thể refresh theo phương thức nào.
- Có yêu cầu full refresh thay vì fast refresh không.
- Query rewrite có còn hợp lệ không.
- Dữ liệu materialized có cần tính lại theo logic mới không.
- Các restriction của phiên bản Oracle và loại biểu thức đang sử dụng.

Không suy luận rằng chỉ thêm DETERMINISTIC là mọi materialized view tự động được fast refresh. Khả năng refresh phụ thuộc định nghĩa MV, các biểu thức, log, join, aggregate và những quy tắc riêng của Oracle.

### 6.1. Deterministic không thay thế refresh

Nếu một materialized view lưu kết quả được tính từ function, việc sửa function có thể làm kết quả đã materialize trở nên lỗi thời. DETERMINISTIC không tự chạy refresh và không tự cập nhật dữ liệu cũ.

Khi thay đổi function:
1. Xác định MV phụ thuộc.
2. Kiểm tra định nghĩa và trạng thái.
3. Chọn refresh method hợp lệ.
4. Refresh hoặc recreate theo kế hoạch.
5. Kiểm tra dữ liệu và query rewrite sau triển khai.

## 7. DETERMINISTIC và RESULT_CACHE

Hai tính năng này có liên quan tới việc tái sử dụng kết quả nhưng không đồng nghĩa.

### 7.1. DETERMINISTIC

DETERMINISTIC:
- Là lời cam kết của người viết function.
- Nêu rằng cùng tham số luôn trả cùng kết quả.
- Không tự tạo một cache có thể quản lý.
- Không bảo đảm function chỉ chạy một lần.
- Được Oracle sử dụng trong một số tối ưu hóa/ngữ cảnh yêu cầu function deterministic.
- Người viết chịu trách nhiệm nếu lời cam kết sai.

### 7.2. RESULT_CACHE

Function có thể khai báo RESULT_CACHE:

~~~sql
CREATE OR REPLACE FUNCTION get_tax_rate (
    p_region_code IN VARCHAR2
) RETURN NUMBER RESULT_CACHE
IS
    l_rate NUMBER;
BEGIN
    SELECT tax_rate
    INTO l_rate
    FROM tax_region
    WHERE region_code = p_region_code;

    RETURN l_rate;
END get_tax_rate;
/
~~~

RESULT_CACHE yêu cầu Oracle lưu kết quả function trong result cache theo các tham số và dependency được quản lý. Oracle có thể invalidation cache khi các bảng được function đọc thay đổi, theo cơ chế result cache.

Đây là một cơ chế cache thực sự, khác với DETERMINISTIC. Tuy nhiên, RESULT_CACHE cũng có restriction và điều kiện sử dụng; không phải mọi function hoặc mọi workload đều phù hợp.

### 7.3. So sánh

| Tiêu chí | DETERMINISTIC | RESULT_CACHE |
| --- | --- | --- |
| Bản chất | Cam kết về tính xác định | Cơ chế lưu kết quả trong result cache |
| Người viết bảo đảm cùng input, cùng output | Có | Function vẫn cần semantics phù hợp |
| Tự tạo cache trong SGA | Không | Có |
| Theo dõi dependency table để invalidation cache | Không phải cơ chế của DETERMINISTIC | Có theo cơ chế result cache |
| Dùng cho function-based index | Là khai báo quan trọng khi dùng user-defined function | Không thay thế yêu cầu deterministic |
| Bảo đảm function chỉ chạy một lần | Không | Không; cache hit/miss và invalidation quyết định |
| Có thể thay thế hoàn toàn cho nhau | Không | Không |

### 7.4. Không đánh dấu DETERMINISTIC để mong cache kết quả

Nếu mục tiêu là tái sử dụng kết quả tra cứu từ bảng cấu hình, DETERMINISTIC không phải giải pháp cache. Nếu function phụ thuộc bảng mutable, đánh dấu deterministic có thể làm sai kết quả ở những ngữ cảnh Oracle được phép dựa trên lời cam kết.

Hãy đánh giá RESULT_CACHE nếu dependency và workload phù hợp, hoặc thực hiện JOIN/subquery trực tiếp để optimizer quản lý dữ liệu trong SQL.

## 8. Đưa trạng thái bên ngoài thành tham số

Một cách thiết kế giúp function deterministic là đưa mọi dữ liệu quyết định kết quả vào tham số.

Ví dụ function tính giá sau chiết khấu:

~~~sql
CREATE OR REPLACE FUNCTION discounted_price (
    p_base_price IN NUMBER,
    p_discount_rate IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(
        p_base_price * (1 - p_discount_rate),
        2
    );
END discounted_price;
/
~~~

Cả giá gốc và tỷ lệ giảm giá đều được truyền vào. Nếu cùng hai giá trị, function cho cùng kết quả.

### 8.1. Đừng để function tự tra cứu tỷ lệ hiện hành

Một phiên bản khác:

~~~sql
CREATE OR REPLACE FUNCTION discounted_price_current (
    p_product_id IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
    l_price NUMBER;
    l_rate  NUMBER;
BEGIN
    SELECT price, discount_rate
    INTO l_price, l_rate
    FROM product_pricing
    WHERE product_id = p_product_id;

    RETURN ROUND(l_price * (1 - l_rate), 2);
END discounted_price_current;
/
~~~

Function phụ thuộc bảng PRODUCT_PRICING. Nếu giá hoặc tỷ lệ giảm thay đổi, cùng PRODUCT_ID có thể trả kết quả khác. Không khai báo DETERMINISTIC cho function này chỉ vì bảng được cập nhật không thường xuyên.

Nếu cần function thuần, caller đọc dữ liệu và truyền cả giá lẫn tỷ lệ vào. Nếu cần lookup động, dùng SQL hoặc cơ chế cache có invalidation phù hợp.

### 8.2. Đưa version/config key vào tham số chỉ khi version bất biến

Có thể truyền một CONFIG_VERSION để function xác định quy tắc tính. Nhưng cách này chỉ có ý nghĩa nếu cùng version luôn ánh xạ tới cùng nội dung cấu hình và version cũ không bị sửa lại.

Nếu người quản trị cập nhật dữ liệu của một version đã tồn tại, chỉ thêm version vào tham số vẫn không bảo đảm deterministic. Tính xác định cần được bảo vệ bằng quy tắc dữ liệu bất biến, chẳng hạn version được đóng băng sau khi phát hành.

## 9. Kiểm chứng tính xác định

Vì Oracle không tự chứng minh function deterministic, đội phát triển cần kiểm tra hợp đồng này bằng thiết kế và thử nghiệm.

### 9.1. Kiểm tra cùng đầu vào nhiều lần

~~~sql
SELECT calculate_fee(100000, 0.05) AS result_1
FROM dual;

SELECT calculate_fee(100000, 0.05) AS result_2
FROM dual;
~~~

Hai kết quả phải giống nhau. Đây chỉ là test cơ bản; nó chưa chứng minh function không phụ thuộc session hoặc database state.

### 9.2. Kiểm tra qua nhiều session

Nếu function có thể bị ảnh hưởng bởi:
- NLS_DATE_FORMAT.
- NLS_NUMERIC_CHARACTERS.
- SESSIONTIMEZONE.
- CURRENT_SCHEMA.
- Application context.
- User/session identity.

hãy thử gọi trong các session có cấu hình khác nhau. Nếu cùng tham số tạo kết quả khác nhau, function không deterministic theo hợp đồng đã khai báo.

### 9.3. Kiểm tra sau khi thay đổi database state

Nếu function có bất kỳ truy vấn bảng nào, hãy thử:
1. Gọi function với một bộ tham số.
2. Thay đổi hàng mà function đọc.
3. Gọi lại với cùng tham số.
4. So sánh kết quả.

Nếu kết quả đổi, function phụ thuộc trạng thái bảng. Không khai báo DETERMINISTIC.

### 9.4. Kiểm tra side effect

Đọc source và dependency để tìm:
- DML.
- Sequence NEXTVAL.
- Package variable được gán.
- DBMS_RANDOM.
- DBMS_OUTPUT hoặc logger có side effect quan sát được.
- External procedure hoặc network call.
- Autonomous transaction.
- Session state modification.

Một test chỉ so sánh return value không phát hiện được mọi side effect. Phải xem cả hành vi của function.

### 9.5. Kiểm tra dependency đệ quy

Nếu function gọi package hoặc function khác, kiểm tra tiếp các dependency đó. Một hàm ngoài nhìn có vẻ thuần nhưng có thể gọi helper đọc bảng hoặc trạng thái session.

Ghi lại dependency quan trọng trong tài liệu code để người sửa sau hiểu phạm vi lời cam kết.

## 10. Ví dụ thực hành: function deterministic và function không deterministic

### 10.1. Function deterministic

~~~sql
CREATE OR REPLACE FUNCTION tax_amount (
    p_net_amount IN NUMBER,
    p_tax_rate   IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN ROUND(p_net_amount * p_tax_rate, 2);
END tax_amount;
/
~~~

Thử:

~~~sql
SELECT tax_amount(1000, 0.1) AS tax
FROM dual;
~~~

Kết quả luôn là 100 với cùng hai tham số NUMBER.

### 10.2. Function không deterministic vì dùng thời gian hiện tại

~~~sql
CREATE OR REPLACE FUNCTION is_current_year (
    p_year IN NUMBER
) RETURN NUMBER
IS
BEGIN
    IF p_year = EXTRACT(YEAR FROM SYSDATE) THEN
        RETURN 1;
    END IF;

    RETURN 0;
END is_current_year;
/
~~~

Function không có DETERMINISTIC vì kết quả của cùng P_YEAR có thể thay đổi khi năm hiện tại đổi.

Nếu muốn hàm thuần, truyền cả năm so sánh:

~~~sql
CREATE OR REPLACE FUNCTION is_year_equal (
    p_year_a IN NUMBER,
    p_year_b IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    IF p_year_a = p_year_b THEN
        RETURN 1;
    END IF;

    RETURN 0;
END is_year_equal;
/
~~~

### 10.3. Function-based index với function deterministic

Tạo bảng sandbox:

~~~sql
CREATE TABLE deterministic_demo (
    item_id NUMBER PRIMARY KEY,
    amount  NUMBER NOT NULL
);
~~~

Thêm dữ liệu:

~~~sql
INSERT INTO deterministic_demo VALUES (1, 1200);
INSERT INTO deterministic_demo VALUES (2, 2400);
INSERT INTO deterministic_demo VALUES (3, 3900);
COMMIT;
~~~

Tạo function:

~~~sql
CREATE OR REPLACE FUNCTION demo_amount_bucket (
    p_amount IN NUMBER
) RETURN NUMBER DETERMINISTIC
IS
BEGIN
    RETURN TRUNC(p_amount / 1000);
END demo_amount_bucket;
/
~~~

Tạo index:

~~~sql
CREATE INDEX ix_deterministic_demo_bucket
ON deterministic_demo (demo_amount_bucket(amount));
~~~

Truy vấn:

~~~sql
SELECT item_id, amount
FROM deterministic_demo
WHERE demo_amount_bucket(amount) = 2;
~~~

Optimizer có thể xem xét function-based index này. Bảng nhỏ có thể khiến optimizer chọn full table scan vì chi phí thấp; đó không phải bằng chứng function-based index không hoạt động.

### 10.4. Thử thay đổi function

Nếu sửa DEMO_AMOUNT_BUCKET từ chia 1000 sang chia 500, các giá trị đã lưu trong function-based index có thể không còn đúng với logic mới. Cần rebuild index:

~~~sql
ALTER INDEX ix_deterministic_demo_bucket REBUILD;
~~~

Trong hệ thống thật, trước khi thay đổi function, liệt kê dependency và lên kế hoạch rebuild/refresh mọi object liên quan.

### 10.5. Dọn sandbox

~~~sql
DROP INDEX ix_deterministic_demo_bucket;
DROP FUNCTION demo_amount_bucket;
DROP TABLE deterministic_demo PURGE;
~~~

Chỉ xóa các đối tượng sandbox do bài học tạo khi chắc chắn không cần dữ liệu. DROP là DDL và có implicit commit; thực hiện cleanup riêng.

## 11. DETERMINISTIC trong thiết kế ứng dụng

Một function deterministic tốt thường có các đặc điểm:
- Tham số mô tả đầy đủ dữ liệu quyết định kết quả.
- Không đọc trạng thái session hoặc thời gian hiện tại.
- Không đọc bảng mutable.
- Không thay đổi package/global state.
- Không ghi database hoặc gọi side effect bên ngoài.
- Các function được gọi bên trong cũng có cùng hợp đồng.
- Quy tắc tính được giữ ổn định qua các lần triển khai hoặc có quy trình cập nhật object phụ thuộc.

### 11.1. Dùng cho phép biến đổi dữ liệu thuần

Các trường hợp thường phù hợp:
- Làm tròn số theo quy tắc cố định.
- Chuyển đổi đơn vị với hệ số được truyền vào.
- Tính bucket từ giá trị đầu vào.
- Chuẩn hóa chuỗi theo một quy tắc cố định, không phụ thuộc session.
- Tính checksum/hash từ input với thuật toán cố định và không có random salt ẩn.
- Tính kết quả từ một tập tham số đầy đủ, bất biến.

### 11.2. Không dùng cho tra cứu trạng thái hiện hành

Các trường hợp thường không phù hợp:
- Lấy tỷ giá hiện tại từ bảng.
- Lấy mức thuế đang áp dụng từ bảng cấu hình.
- Kiểm tra trạng thái tài khoản.
- Lấy quyền của user hiện tại.
- Xác định ngày hiện tại hoặc thời gian còn lại.
- Sinh mã ngẫu nhiên hoặc ID.
- Ghi audit hoặc gửi thông báo.

Các nghiệp vụ này phụ thuộc trạng thái thay đổi hoặc tạo side effect. Hãy dùng SQL, procedure hoặc result cache theo đúng semantics.

### 11.3. Đừng nhầm immutable data với dữ liệu ít thay đổi

Một bảng cấu hình có thể chỉ được cập nhật mỗi tháng nhưng vẫn là mutable. Nếu function phụ thuộc bảng đó, cùng tham số có thể trả kết quả khác ở hai thời điểm.

Chỉ khi dữ liệu được bảo đảm bất biến trong toàn bộ vòng đời sử dụng function, và không có dependency ẩn khác, mới có thể xem đó là một phần cố định của hợp đồng. Trong nhiều trường hợp, truyền dữ liệu vào tham số rõ ràng sẽ dễ kiểm soát hơn.

## 12. DETERMINISTIC và thay đổi phiên bản nghiệp vụ

Một function deterministic có thể được dùng trong index hoặc materialized data. Vì vậy, sửa logic function không chỉ là thay code PL/SQL; nó có thể thay đổi ý nghĩa của dữ liệu được tính trước.

Ví dụ function phân loại đơn hàng:

~~~sql
CREATE OR REPLACE FUNCTION order_priority (
    p_amount IN NUMBER
) RETURN VARCHAR2 DETERMINISTIC
IS
BEGIN
    IF p_amount >= 10000000 THEN
        RETURN 'HIGH';
    ELSIF p_amount >= 1000000 THEN
        RETURN 'MEDIUM';
    ELSE
        RETURN 'LOW';
    END IF;
END order_priority;
/
~~~

Nếu chính sách mới thay ngưỡng HIGH thành 20.000.000, những kết quả đã được tính và lưu trong function-based index có thể không còn phù hợp. Khi triển khai:
1. Xác định index/MV/view hoặc code phụ thuộc function.
2. Thống nhất thời điểm chuyển logic.
3. Cập nhật function.
4. Rebuild/refresh object lưu kết quả nếu cần.
5. Kiểm tra query plan và kết quả.
6. Theo dõi lỗi compile và trạng thái object.

Không để code mới chạy cùng dữ liệu index cũ trong một giai đoạn không được kiểm soát.

### 12.1. Có thể version hóa quy tắc tính

Nếu nhiều phiên bản quy tắc phải cùng tồn tại, có thể đưa version vào input:

~~~sql
CREATE OR REPLACE FUNCTION priority_for_version (
    p_amount IN NUMBER,
    p_rule_version IN PLS_INTEGER
) RETURN VARCHAR2 DETERMINISTIC
IS
BEGIN
    IF p_rule_version = 1 THEN
        IF p_amount >= 10000000 THEN
            RETURN 'HIGH';
        END IF;
    ELSIF p_rule_version = 2 THEN
        IF p_amount >= 20000000 THEN
            RETURN 'HIGH';
        END IF;
    ELSE
        RETURN 'UNKNOWN';
    END IF;

    RETURN 'NORMAL';
END priority_for_version;
/
~~~

Cùng P_AMOUNT và P_RULE_VERSION sẽ cho cùng kết quả, miễn logic function và các dependency không thay đổi. Khi sửa chính sách, thêm version mới thay vì sửa ý nghĩa của version cũ có thể giúp giữ kết quả lịch sử ổn định.

Version hóa không tự làm function deterministic nếu function vẫn đọc trạng thái mutable hoặc có side effect.

## 13. Các lỗi và rủi ro thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Đánh dấu function đọc SYSDATE là deterministic | Kết quả phụ thuộc thời điểm gọi | Truyền ngày vào tham số hoặc bỏ DETERMINISTIC |
| Đọc bảng cấu hình trong function deterministic | Bảng có thể thay đổi | Dùng SQL trực tiếp hoặc cache có invalidation |
| Dùng package variable | Kết quả phụ thuộc session/package state | Truyền giá trị thành tham số |
| Dùng DBMS_RANDOM | Cùng input có thể cho kết quả khác | Không khai báo deterministic |
| Dùng sequence NEXTVAL | Giá trị thay đổi và sequence có side effect | Dùng sequence trực tiếp |
| Dùng SYS_CONTEXT/USER | Kết quả phụ thuộc session/user | Không khai báo deterministic hoặc truyền context rõ nếu nghiệp vụ phù hợp |
| Ghi log trong function | Có side effect | Tách logging khỏi function |
| Sửa body function dùng trong index | Giá trị index cũ có thể không còn đúng | Rebuild index và refresh object phụ thuộc |
| Nhầm DETERMINISTIC với RESULT_CACHE | Cho rằng khai báo tạo cache | Dùng RESULT_CACHE khi phù hợp |
| Cho rằng Oracle tự kiểm tra | Biên dịch thành công bị hiểu nhầm là đã xác minh | Review dependency và test hợp đồng |
| Function gọi helper không deterministic | Dependency gián tiếp làm kết quả thay đổi | Kiểm tra toàn bộ call graph |
| Phụ thuộc NLS/timezone ngầm | Cùng input, session khác có thể khác kết quả | Chỉ định format/NLS/timezone rõ hoặc bỏ DETERMINISTIC |

## 14. Quy trình quyết định có nên khai báo DETERMINISTIC

Trước khi thêm từ khóa, hãy trả lời lần lượt:

1. Function có trả về cùng một giá trị khi nhận cùng các tham số không?
2. Có biến package, global hoặc session state nào ảnh hưởng kết quả không?
3. Function có đọc SYSDATE, SYSTIMESTAMP, DBMS_RANDOM hoặc sequence không?
4. Function có đọc bảng có thể thay đổi không?
5. Function có dùng USER, SYS_CONTEXT, NLS hoặc timezone hiện hành không?
6. Function có gọi function khác? Các dependency đó có deterministic không?
7. Function có DML, ghi log, thay đổi session hoặc gọi external service không?
8. Nếu dữ liệu cấu hình đổi, cùng tham số có thể cho kết quả khác không?
9. Function có được dùng trong function-based index, materialized view hoặc object lưu kết quả không?
10. Nếu logic function thay đổi, quy trình rebuild/refresh dependency là gì?
11. Có cần RESULT_CACHE thay vì DETERMINISTIC không?
12. Có thể chuyển trạng thái ẩn thành tham số rõ ràng không?

Nếu không thể bảo đảm cùng input luôn cùng output và không side effect, đừng khai báo DETERMINISTIC.

## 15. Những nhầm lẫn thường gặp

**DETERMINISTIC khiến Oracle tự kiểm tra function.** Không đúng. Đây là lời cam kết của lập trình viên; Oracle không chứng minh toàn bộ logic function.

**DETERMINISTIC tự động cache kết quả.** Không đúng. Nó không phải cơ chế cache như RESULT_CACHE và không bảo đảm số lần function được gọi.

**Function đọc bảng cấu hình vẫn deterministic nếu bảng hiếm khi đổi.** Không đúng. Mutable data vẫn có thể thay đổi; tần suất thấp không biến nó thành bất biến.

**Cùng tham số nghĩa là cùng kết quả dù session khác nhau.** Không đúng nếu function phụ thuộc NLS, timezone, user, application context hoặc session state.

**Function dùng SYSDATE có thể deterministic nếu chỉ trả năm.** Không đúng. Năm hiện tại thay đổi theo thời gian; cùng input vẫn có thể trả kết quả khác.

**Function dùng DBMS_RANDOM có thể deterministic nếu seed thường giống nhau.** Không nên dựa vào trạng thái seed/session; kết quả ngẫu nhiên không đáp ứng hợp đồng cùng input cùng output.

**DETERMINISTIC chỉ liên quan tới hiệu năng.** Không đúng. Nó là một hợp đồng ngữ nghĩa ảnh hưởng tới tính đúng đắn khi Oracle sử dụng function trong các object hoặc tối ưu hóa dựa trên lời cam kết.

**Function-based index tự cập nhật mọi hàng khi function body thay đổi.** Không đúng. Các khóa đã lưu có thể cần rebuild; phải kiểm tra object phụ thuộc.

**Thêm DETERMINISTIC làm materialized view tự fast refresh được.** Không đúng. MV còn có nhiều điều kiện và restriction khác; deterministic không bảo đảm fast refresh.

**RESULT_CACHE và DETERMINISTIC có thể thay thế nhau.** Không đúng. Một cái là cam kết tính xác định; một cái là cơ chế cache có dependency invalidation.

**Một function không có DML thì chắc chắn deterministic.** Không đúng. Nó vẫn có thể đọc giờ, random, session context, package state hoặc bảng mutable.

**Function chỉ gọi một function khác nên chắc chắn deterministic.** Không đúng. Phải xem toàn bộ dependency của function được gọi.

**Thay đổi ngưỡng nghiệp vụ trong function không ảnh hưởng index cũ.** Không đúng. Giá trị index được tính trước có thể phản ánh logic cũ; cần rebuild/refresh object phụ thuộc.

## 16. Bài tập tự luyện

1. Viết function nhận hai NUMBER và trả tổng. Giải thích vì sao có thể khai báo DETERMINISTIC.
2. Viết function tính phí từ số tiền và tỷ lệ được truyền vào.
3. Viết function dùng SYSDATE rồi giải thích vì sao không deterministic.
4. Sửa function ở bài 3 để ngày hiện tại trở thành tham số.
5. Viết function dùng DBMS_RANDOM và xác định vi phạm nào xảy ra.
6. Vì sao function đọc sequence NEXTVAL không deterministic?
7. Viết function đọc một package variable. Phân tích kết quả khi variable thay đổi.
8. Viết function đọc bảng cấu hình chiết khấu và giải thích vì sao không nên khai báo DETERMINISTIC.
9. Phân tích ảnh hưởng của SYS_CONTEXT tới tính xác định.
10. Vì sao NLS_DATE_FORMAT có thể là một dependency ẩn?
11. Tạo standalone function với DETERMINISTIC sau kiểu trả về.
12. Tạo package specification khai báo deterministic function và triển khai trong body.
13. Giải thích vì sao Oracle không chứng minh lời cam kết deterministic.
14. Tạo function-based index trên một function thuần tính bucket từ AMOUNT.
15. Viết truy vấn dùng cùng biểu thức để optimizer có thể xem xét index.
16. Giải thích vì sao bảng cấu hình thay đổi có thể làm index dựa trên function bị lỗi thời.
17. Sửa function được dùng trong function-based index. Nêu các bước triển khai cần làm.
18. Phân biệt DETERMINISTIC và RESULT_CACHE.
19. Một function RESULT_CACHE đọc bảng cấu hình. Cache được quản lý theo dependency khác DETERMINISTIC như thế nào?
20. Vì sao DETERMINISTIC không bảo đảm function chỉ chạy một lần cho mỗi giá trị đầu vào?
21. Một function không có DML nhưng gọi helper đọc SYSDATE. Function ngoài có deterministic không?
22. Thiết kế function chuẩn hóa dữ liệu mà không phụ thuộc session NLS.
23. Thiết kế function tính ưu tiên đơn hàng với rule version là tham số.
24. Vì sao version hóa không đủ nếu dữ liệu của version cũ vẫn có thể bị sửa?
25. Viết checklist dependency cần kiểm tra trước khi khai báo DETERMINISTIC.
26. Đưa ra ví dụ side effect không được phép trong deterministic function.
27. Phân tích cách thay đổi function ảnh hưởng tới materialized view phụ thuộc.
28. Thiết kế quy trình release khi thay đổi function được dùng trong function-based index.
29. Viết test gọi cùng input trong hai session có NLS/timezone khác nhau.
30. Một function tra cứu tỷ giá hiện tại cần tối ưu. Vì sao không nên đánh dấu DETERMINISTIC và những lựa chọn khác là gì?

**DETERMINISTIC là cam kết rằng cùng đầu vào luôn tạo cùng kết quả và function không có side effect.** Oracle dựa vào cam kết đó trong một số tối ưu hóa và object lưu kết quả, nhưng không tự xác minh tính đúng đắn. Hãy kiểm tra mọi dependency trực tiếp và gián tiếp, đưa trạng thái quyết định vào tham số khi phù hợp, phân biệt DETERMINISTIC với RESULT_CACHE và rebuild/refresh các object phụ thuộc khi logic function thay đổi.
