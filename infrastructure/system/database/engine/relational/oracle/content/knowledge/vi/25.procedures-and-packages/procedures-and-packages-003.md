# Overloading, named notation và positional notation

Trong PL/SQL, **overloading** cho phép nhiều subprogram dùng cùng một tên nhưng có danh sách tham số khác nhau. Khi gọi tên đó, Oracle xác định phiên bản cần thực thi dựa trên số lượng, thứ tự và kiểu dữ liệu của các đối số phù hợp với khai báo.

PL/SQL còn hỗ trợ hai cách truyền đối số:

- **Positional notation**: đối số được ghép với tham số theo vị trí trong khai báo.
- **Named notation**: đối số được ghép với tham số bằng tên hình thức, dùng cú pháp tên tham số => giá trị.
- **Mixed notation**: kết hợp đối số theo vị trí ở đầu lời gọi và đối số có tên ở phần sau.

Các khả năng này thường được dùng trong package để xây dựng API có nhiều cách gọi, hỗ trợ giá trị mặc định và giữ lời gọi dễ đọc khi subprogram có nhiều tham số.

Ví dụ một package có thể cung cấp nhiều cách hiển thị giá trị:

~~~sql
CREATE OR REPLACE PACKAGE display_api AS
    PROCEDURE show_value(p_value IN NUMBER);
    PROCEDURE show_value(p_value IN DATE);
    PROCEDURE show_value(p_value IN VARCHAR2);
END display_api;
/
~~~

Ba procedure có cùng tên SHOW_VALUE nhưng nhận ba kiểu dữ liệu khác nhau. Khi gọi với một NUMBER, DATE hoặc VARCHAR2 rõ ràng, Oracle chọn overload tương ứng.

Bài học trình bày phạm vi overloading, quy tắc phân biệt chữ ký, cách Oracle phân giải lời gọi, positional/named/mixed notation, tham số mặc định, lỗi thường gặp và cách thiết kế package API ổn định.

## 1. Subprogram và chữ ký tham số

Subprogram trong PL/SQL là procedure hoặc function. Một subprogram có:
- Tên.
- Danh sách tham số hình thức (formal parameters), nếu có.
- Kiểu dữ liệu và mode của từng tham số.
- Với function, kiểu dữ liệu trả về.
- Phần thân thực hiện công việc.

Ví dụ:

~~~sql
PROCEDURE calculate_total(
    p_quantity IN NUMBER,
    p_unit_price IN NUMBER,
    p_total OUT NUMBER
);
~~~

Trong khai báo trên:
- CALCULATE_TOTAL là tên procedure.
- P_QUANTITY, P_UNIT_PRICE, P_TOTAL là formal parameters.
- NUMBER là kiểu dữ liệu.
- IN và OUT là parameter modes.

Khi gọi subprogram, các giá trị hoặc biến truyền vào được gọi là actual arguments. Ví dụ:

~~~sql
calculate_total(2, 150, l_total);
~~~

Các actual arguments 2, 150 và L_TOTAL được ghép với ba formal parameters theo thứ tự.

### 1.1. Chữ ký và overloading

Trong ngữ cảnh overloading, Oracle cần phân biệt các khai báo cùng tên bằng đặc điểm của danh sách tham số. Các yếu tố có thể làm chữ ký khác nhau gồm:
- Số lượng tham số.
- Thứ tự tham số khi kiểu dữ liệu ở các vị trí khác nhau.
- Kiểu dữ liệu hoặc họ kiểu dữ liệu của tham số.

Ví dụ:

~~~sql
PROCEDURE find_record(p_id IN NUMBER);
PROCEDURE find_record(p_code IN VARCHAR2);
~~~

Hai procedure cùng tên nhưng khác kiểu tham số nên có thể được overload.

### 1.2. Overloading thường được khai báo trong package

Package là nơi phổ biến để công bố nhiều overload cùng tên:

~~~sql
CREATE OR REPLACE PACKAGE employee_api AS
    PROCEDURE find_employee(p_employee_id IN NUMBER);
    PROCEDURE find_employee(p_employee_code IN VARCHAR2);
END employee_api;
/
~~~

Package specification công bố API cho caller. Package body chứa phần triển khai tương ứng.

Overloading cũng có thể xuất hiện trong các phạm vi PL/SQL phù hợp như subprogram cục bộ và method của object type. Không nên thiết kế nhiều standalone schema-level procedure chỉ khác tham số với kỳ vọng chúng cùng tồn tại dưới một tên; hãy đặt các overload trong package.

### 1.3. Public overload và private overload

- Subprogram khai báo trong package specification là public, caller bên ngoài package có thể gọi.
- Subprogram chỉ khai báo trong package body là private, chỉ dùng nội bộ package.
- Mỗi overload muốn được caller bên ngoài sử dụng phải có khai báo tương ứng trong specification.

Package body phải triển khai các overload public theo đúng danh sách tham số đã công bố.

## 2. Khai báo và triển khai các overload

Ví dụ package cung cấp ba cách hiển thị giá trị tùy theo kiểu dữ liệu:

~~~sql
CREATE OR REPLACE PACKAGE display_api AS
    PROCEDURE show_value(p_value IN NUMBER);
    PROCEDURE show_value(p_value IN DATE);
    PROCEDURE show_value(p_value IN VARCHAR2);
END display_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY display_api AS

    PROCEDURE show_value(p_value IN NUMBER) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'NUMBER: ' || TO_CHAR(p_value)
        );
    END show_value;

    PROCEDURE show_value(p_value IN DATE) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'DATE: ' || TO_CHAR(p_value, 'YYYY-MM-DD')
        );
    END show_value;

    PROCEDURE show_value(p_value IN VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'TEXT: ' || p_value
        );
    END show_value;

END display_api;
/
~~~

Gọi các overload:

~~~sql
BEGIN
    display_api.show_value(125);
    display_api.show_value(DATE '2025-03-08');
    display_api.show_value('Oracle PL/SQL');
END;
/
~~~

Oracle chọn overload tương ứng với kiểu của actual argument.

### 2.1. Overload theo số lượng tham số

~~~sql
CREATE OR REPLACE PACKAGE log_api AS
    PROCEDURE write_log(p_message IN VARCHAR2);

    PROCEDURE write_log(
        p_message IN VARCHAR2,
        p_level IN PLS_INTEGER
    );
END log_api;
/
~~~

Hai khai báo có số lượng tham số khác nhau. Caller có thể ghi log chỉ với nội dung hoặc truyền thêm mức độ:

~~~sql
BEGIN
    log_api.write_log('Started');
    log_api.write_log('Connection failed', 3);
END;
/
~~~

Trong package body, cần triển khai cả hai phiên bản với danh sách tham số khớp specification.

### 2.2. Overload theo thứ tự và kiểu tham số

Có thể có hai overload nhận cùng hai kiểu nhưng theo thứ tự khác nhau:

~~~sql
CREATE OR REPLACE PACKAGE conversion_api AS
    PROCEDURE convert_value(
        p_amount IN NUMBER,
        p_currency IN VARCHAR2
    );

    PROCEDURE convert_value(
        p_currency IN VARCHAR2,
        p_amount IN NUMBER
    );
END conversion_api;
/
~~~

Lời gọi positional phân biệt bằng thứ tự và kiểu actual argument:

~~~sql
BEGIN
    conversion_api.convert_value(100, 'USD');
    conversion_api.convert_value('EUR', 250);
END;
/
~~~

Trong thực tế, hai overload có thứ tự tham số đảo nhau dễ gây nhầm lẫn. Chỉ dùng cách này khi hai dạng gọi có ý nghĩa rõ ràng; nếu có thể, hãy chọn tên subprogram riêng hoặc API có cấu trúc dễ đọc hơn.

### 2.3. Overload function

Function cũng có thể được overload:

~~~sql
CREATE OR REPLACE PACKAGE format_api AS
    FUNCTION format_value(p_value IN NUMBER)
        RETURN VARCHAR2;

    FUNCTION format_value(p_value IN DATE)
        RETURN VARCHAR2;
END format_api;
/
~~~

Caller:

~~~sql
DECLARE
    l_number_text VARCHAR2(100);
    l_date_text   VARCHAR2(100);
BEGIN
    l_number_text := format_api.format_value(1250.5);
    l_date_text := format_api.format_value(DATE '2025-03-08');
END;
/
~~~

Hai function được phân biệt bởi kiểu tham số đầu vào. Kiểu trả về của function không phải yếu tố đủ để tạo một overload mới.

## 3. Những khác biệt không đủ để tạo overload

Không phải mọi khác biệt trong khai báo đều làm hai subprogram trở thành hai overload hợp lệ.

### 3.1. Chỉ khác tên tham số

Không thể tạo hai overload chỉ vì formal parameter có tên khác:

~~~sql
-- Không phải hai overload hợp lệ chỉ nhờ tên tham số.
PROCEDURE process_value(p_number IN NUMBER);
PROCEDURE process_value(p_amount IN NUMBER);
~~~

Cả hai có cùng một tham số NUMBER. Đổi tên P_NUMBER thành P_AMOUNT không tạo chữ ký khác.

### 3.2. Chỉ khác parameter mode

IN, OUT và IN OUT không phải cách để phân biệt hai overload.

~~~sql
-- Không thể overload chỉ bằng IN và OUT.
PROCEDURE get_value(p_value IN NUMBER);
PROCEDURE get_value(p_value OUT NUMBER);
~~~

Mode quy định cách truyền dữ liệu giữa caller và subprogram, không tạo một phiên bản overload độc lập.

### 3.3. Chỉ khác subtype

Các subtype cùng dựa trên một kiểu cơ sở không nhất thiết phân biệt được khi overload.

Ví dụ INTEGER và SMALLINT là các subtype của NUMBER. Không thể chỉ dựa vào khác biệt đó để tạo hai overload tương đương:

~~~sql
-- Không phải hai chữ ký overload phân biệt được.
PROCEDURE process_number(p_value IN INTEGER);
PROCEDURE process_number(p_value IN SMALLINT);
~~~

Tương tự, khai báo một subtype do người dùng định nghĩa trên NUMBER không biến nó thành một họ kiểu dữ liệu độc lập cho mục đích overload.

### 3.4. Chỉ khác kiểu trả về

Không thể tạo hai function cùng tên, cùng danh sách tham số nhưng chỉ khác RETURN type:

~~~sql
-- Không thể overload chỉ bằng RETURN type.
FUNCTION get_value(p_id IN NUMBER) RETURN NUMBER;
FUNCTION get_value(p_id IN NUMBER) RETURN VARCHAR2;
~~~

Khi gọi GET_VALUE(10), Oracle không thể chọn function chỉ dựa trên kiểu biến nhận kết quả. Hãy thay đổi tham số đầu vào theo một cách phân biệt hợp lệ hoặc dùng tên function khác.

### 3.5. Chỉ khác giá trị mặc định

Giá trị DEFAULT không phải yếu tố phân biệt chữ ký:

~~~sql
-- Không tạo được hai overload chỉ nhờ DEFAULT khác nhau.
PROCEDURE search_data(p_status IN VARCHAR2 DEFAULT 'NEW');
PROCEDURE search_data(p_status IN VARCHAR2 DEFAULT 'ALL');
~~~

Hai khai báo vẫn có cùng tên và cùng danh sách tham số về kiểu/số lượng. Hãy dùng một procedure với quy tắc default rõ ràng hoặc tên procedure khác.

## 4. Các kiểu dữ liệu và khả năng phân biệt overload

Oracle cần xác định được một actual argument phù hợp với một overload. Những kiểu dữ liệu thuộc cùng họ hoặc chỉ khác subtype có thể không phân biệt được.

Ví dụ rõ ràng:

~~~sql
PROCEDURE display(p_value IN NUMBER);
PROCEDURE display(p_value IN DATE);
PROCEDURE display(p_value IN VARCHAR2);
~~~

NUMBER, DATE và VARCHAR2 là các kiểu khác nhau đủ để minh họa ba overload.

Không nên cố tạo nhiều overload chỉ khác độ dài VARCHAR2, precision/scale NUMBER hoặc subtype tương đương. Các thuộc tính độ dài/precision không tự động tạo một kiểu độc lập.

### 4.1. Anchored datatype không tự tạo kiểu riêng

~~~sql
PROCEDURE find_employee(
    p_id IN employees.employee_id%TYPE
);
~~~

%TYPE lấy kiểu dữ liệu của cột được tham chiếu. Nếu EMPLOYEE_ID có kiểu NUMBER, tham số này về bản chất vẫn là NUMBER cho mục đích phân giải overload; nó không phải một kiểu mới chỉ vì dùng %TYPE.

Tương tự, hai cột khác bảng nhưng đều khai báo NUMBER không trở thành hai họ kiểu riêng.

### 4.2. Implicit conversion có thể làm lời gọi khó phân giải

Oracle có quy tắc chuyển đổi kiểu ngầm định trong PL/SQL. Khi có nhiều overload và actual argument không có kiểu rõ ràng, chuyển đổi ngầm định có thể làm lời gọi trở nên mơ hồ hoặc không khớp như người viết dự đoán.

Hãy:
- Dùng biến có datatype rõ ràng.
- Dùng literal có kiểu rõ như DATE literal.
- Dùng CAST khi cần xác định kiểu.
- Tránh dựa vào nội dung chuỗi để Oracle đoán ý nghĩa.
- Không tạo overload gần như trùng nhau chỉ để tận dụng implicit conversion.

## 5. Oracle phân giải overload như thế nào?

Khi biên dịch lời gọi PL/SQL, Oracle xem xét các khai báo cùng tên có thể truy cập và tìm subprogram phù hợp với actual arguments.

Các yếu tố chính:
1. Tên subprogram và phạm vi/package.
2. Số lượng actual arguments.
3. Cách ánh xạ đối số theo vị trí hoặc tên.
4. Kiểu dữ liệu của actual argument.
5. Parameter mode và khả năng truyền biến đối với OUT/IN OUT.
6. Giá trị mặc định của các formal parameters bị bỏ qua.
7. Các quy tắc overload và chuyển đổi kiểu của PL/SQL.

Kết quả cần là một overload có thể được chọn rõ ràng. Nếu không có overload phù hợp, lời gọi không hợp lệ. Nếu nhiều overload cùng phù hợp và Oracle không thể phân biệt, lời gọi bị mơ hồ.

### 5.1. Một overload phù hợp duy nhất

Với:

~~~sql
PROCEDURE find_employee(p_id IN NUMBER);
PROCEDURE find_employee(p_code IN VARCHAR2);
~~~

Các lời gọi:

~~~sql
find_employee(101);
find_employee('EMP-101');
~~~

có actual argument với kiểu tương ứng, nên Oracle có thể chọn phiên bản phù hợp.

### 5.2. Không có overload phù hợp

Nếu chỉ có:

~~~sql
PROCEDURE find_employee(p_id IN NUMBER);
~~~

mà caller truyền một record không tương thích hoặc sai số lượng tham số, Oracle không tìm được chữ ký phù hợp. Một lỗi thường gặp là PLS-00306:

~~~text
PLS-00306: wrong number or types of arguments in call
~~~

Hãy kiểm tra số lượng, thứ tự, kiểu dữ liệu, tên tham số và mode của actual arguments.

### 5.3. Có nhiều overload cùng phù hợp

Nếu nhiều khai báo cùng có thể nhận actual arguments, Oracle có thể báo PLS-00307:

~~~text
PLS-00307: too many declarations of ... match this call
~~~

Ví dụ điển hình là truyền untyped NULL vào một tên được overload cho nhiều kiểu:

~~~sql
-- Có thể mơ hồ nếu cả hai overload cùng nhìn thấy.
display_api.show_value(NULL);
~~~

NULL không tự chỉ ra caller muốn NUMBER, DATE hay VARCHAR2. Hãy xác định kiểu rõ ràng:

~~~sql
BEGIN
    display_api.show_value(CAST(NULL AS NUMBER));
    display_api.show_value(CAST(NULL AS VARCHAR2(100)));
END;
/
~~~

Hoặc khai báo biến đúng kiểu:

~~~sql
DECLARE
    l_value NUMBER := NULL;
BEGIN
    display_api.show_value(l_value);
END;
/
~~~

### 5.4. Literal có kiểu giúp lời gọi rõ ràng

DATE literal:

~~~sql
display_api.show_value(DATE '2025-03-08');
~~~

Chuỗi:

~~~sql
display_api.show_value('2025-03-08');
~~~

Hai actual arguments trên có datatype khác nhau. Chuỗi trông giống ngày tháng vẫn là VARCHAR2; Oracle không nên được yêu cầu đoán ý định nghiệp vụ từ nội dung chuỗi.

## 6. Positional notation

Positional notation ghép actual arguments với formal parameters theo đúng thứ tự khai báo.

Giả sử package:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_order_date IN DATE,
        p_status IN VARCHAR2
    );
END order_api;
/
~~~

Lời gọi positional:

~~~sql
BEGIN
    order_api.create_order(
        100,
        DATE '2025-03-08',
        'NEW'
    );
END;
/
~~~

Ánh xạ:

| Vị trí | Formal parameter | Actual argument |
| ---: | --- | --- |
| 1 | P_CUSTOMER_ID | 100 |
| 2 | P_ORDER_DATE | DATE '2025-03-08' |
| 3 | P_STATUS | 'NEW' |

### 6.1. Ưu điểm của positional notation

- Ngắn gọn với procedure có ít tham số.
- Dễ đọc khi thứ tự tham số đơn giản và quen thuộc.
- Phù hợp với các hàm nhỏ, có danh sách tham số ổn định.
- Không phụ thuộc tên formal parameter trong lời gọi.

### 6.2. Rủi ro khi có nhiều tham số cùng kiểu

~~~sql
PROCEDURE transfer(
    p_from_account IN NUMBER,
    p_to_account IN NUMBER,
    p_amount IN NUMBER
);
~~~

Lời gọi:

~~~sql
transfer(100, 200, 500);
~~~

hợp lệ về kiểu nhưng người đọc khó nhận ra 100 là tài khoản nguồn, 200 là tài khoản đích và 500 là số tiền nếu không xem khai báo.

Nếu đổi nhầm hai đối số cùng kiểu:

~~~sql
transfer(200, 100, 500);
~~~

compiler vẫn có thể chấp nhận. Đây là lỗi logic chứ không phải lỗi datatype. Named notation giúp giảm rủi ro này.

### 6.3. Thay đổi thứ tự tham số có thể phá caller

Nếu package API thay đổi thứ tự các tham số cùng kiểu, các lời gọi positional hiện có có thể vẫn compile nhưng mang ý nghĩa khác.

Ví dụ ban đầu:

~~~sql
PROCEDURE transfer(
    p_from_account IN NUMBER,
    p_to_account IN NUMBER,
    p_amount IN NUMBER
);
~~~

Nếu thay đổi thành:

~~~sql
PROCEDURE transfer(
    p_amount IN NUMBER,
    p_from_account IN NUMBER,
    p_to_account IN NUMBER
);
~~~

Một caller cũ truyền ba NUMBER vẫn có thể khớp kiểu nhưng dữ liệu được ánh xạ sai ý nghĩa. Thay đổi thứ tự tham số public là thay đổi API cần được quản lý cẩn thận.

## 7. Named notation

Named notation ghép actual argument với formal parameter bằng tên. Cú pháp:

~~~sql
subprogram_name(
    formal_parameter_name => actual_argument
);
~~~

Ví dụ:

~~~sql
BEGIN
    order_api.create_order(
        p_customer_id => 100,
        p_order_date  => DATE '2025-03-08',
        p_status      => 'NEW'
    );
END;
/
~~~

Thứ tự đối số có tên không cần giống thứ tự khai báo. Oracle ánh xạ theo tên formal parameter.

### 7.1. Đọc lời gọi dễ hơn

Với procedure chuyển tiền:

~~~sql
account_api.transfer(
    p_from_account => 100,
    p_to_account   => 200,
    p_amount       => 500
);
~~~

Người đọc nhìn thấy ngay ý nghĩa từng giá trị. Đây là lợi ích rõ rệt khi có nhiều tham số cùng datatype.

### 7.2. Named notation giúp tránh nhầm tham số cùng kiểu

Giả sử:

~~~sql
PROCEDURE create_range(
    p_start_date IN DATE,
    p_end_date IN DATE
);
~~~

Lời gọi named:

~~~sql
create_range(
    p_end_date => DATE '2025-12-31',
    p_start_date => DATE '2025-01-01'
);
~~~

dễ đọc và không phụ thuộc thứ tự liệt kê trong lời gọi. Nếu truyền nhầm ngày bắt đầu và ngày kết thúc bằng positional notation, compiler không thể phát hiện vì cả hai đều DATE.

### 7.3. Named notation yêu cầu tên chính xác

Tên actual argument phải khớp với formal parameter được khai báo trong subprogram đang được chọn. Tên không phân biệt chữ hoa/chữ thường theo quy tắc identifier thông thường, trừ khi identifier được khai báo có quote và case-sensitive.

Ví dụ nếu formal parameter là P_CUSTOMER_ID, lời gọi dùng P_CUSTOMER_ID => ...; tên không tồn tại có thể làm lời gọi không khớp.

### 7.4. Không truyền cùng tham số hai lần

Một formal parameter không thể được gán hai actual arguments trong cùng lời gọi:

~~~sql
-- Sai: P_CUSTOMER_ID được cung cấp hai lần.
order_api.create_order(
    p_customer_id => 100,
    p_customer_id => 200
);
~~~

Mỗi formal parameter cần được cung cấp tối đa một lần; các tham số bắt buộc phải có actual argument.

## 8. Mixed notation

Mixed notation kết hợp positional và named notation trong cùng lời gọi. Quy tắc: **các đối số positional phải đứng trước các đối số named**.

Ví dụ:

~~~sql
order_api.create_order(
    100,
    p_status => 'NEW',
    p_order_date => DATE '2025-03-08'
);
~~~

Đối số positional đầu tiên được ghép với P_CUSTOMER_ID. Hai đối số sau được ánh xạ theo tên.

### 8.1. Không đặt positional sau named

Lời gọi sau không hợp lệ:

~~~sql
-- Sai: positional argument xuất hiện sau named argument.
order_api.create_order(
    p_customer_id => 100,
    DATE '2025-03-08',
    'NEW'
);
~~~

Một khi đã bắt đầu dùng named notation, các đối số tiếp theo cũng phải dùng tên.

### 8.2. Khi nào dùng mixed notation?

Mixed notation hữu ích khi:
- Các tham số đầu tiên rất rõ và ngắn.
- Những tham số phía sau nhiều hoặc dễ nhầm.
- Muốn giữ một phần lời gọi gọn nhưng vẫn làm rõ các giá trị quan trọng.

Tuy nhiên, với API dài, dùng named notation cho tất cả đối số thường dễ đọc và ít rủi ro hơn.

## 9. Tham số mặc định và cách bỏ qua đối số

PL/SQL cho phép khai báo giá trị mặc định cho tham số IN. Nếu caller không cung cấp actual argument cho tham số có default, subprogram sử dụng giá trị mặc định.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE search_api AS
    PROCEDURE search_orders(
        p_customer_id IN NUMBER,
        p_status IN VARCHAR2 DEFAULT 'NEW',
        p_from_date IN DATE DEFAULT NULL
    );
END search_api;
/
~~~

Có thể gọi với đủ tham số:

~~~sql
search_api.search_orders(
    100,
    'CLOSED',
    DATE '2025-01-01'
);
~~~

Hoặc bỏ các tham số cuối có default bằng positional notation:

~~~sql
search_api.search_orders(100);
~~~

Lời gọi trên dùng CUSTOMER_ID=100, STATUS='NEW' và FROM_DATE=NULL.

### 9.1. Bỏ qua tham số cuối bằng positional notation

Positional notation có thể bỏ qua các tham số default ở cuối danh sách. Caller không thể bỏ một tham số ở giữa rồi truyền một tham số sau nó bằng vị trí mà không cung cấp vị trí bị bỏ.

Giả sử:

~~~sql
PROCEDURE search_orders(
    p_customer_id IN NUMBER,
    p_status IN VARCHAR2 DEFAULT 'NEW',
    p_from_date IN DATE DEFAULT NULL
);
~~~

Không có cách positional đơn giản để bỏ P_STATUS nhưng truyền P_FROM_DATE; nếu truyền hai đối số positional, đối số thứ hai được ánh xạ vào P_STATUS.

### 9.2. Named notation có thể bỏ qua tham số ở giữa

Dùng named notation:

~~~sql
search_api.search_orders(
    p_customer_id => 100,
    p_from_date => DATE '2025-01-01'
);
~~~

P_STATUS không được cung cấp nên dùng default NEW. P_FROM_DATE được cung cấp theo tên.

Đây là một lợi ích quan trọng của named notation đối với subprogram có nhiều tham số tùy chọn.

### 9.3. Chỉ IN parameter có default

Default value được dùng cho tham số IN. Không khai báo default cho OUT hoặc IN OUT parameter. Nếu caller cần nhận giá trị OUT, phải cung cấp một biến phù hợp trong lời gọi.

### 9.4. Default value không phải một phần phân biệt overload

Không dùng hai default khác nhau để cố tạo hai phiên bản cùng chữ ký. Hãy coi default là quy tắc gọi của một khai báo, không phải tiêu chí định danh overload.

### 9.5. Default có thể làm lời gọi overload trở nên mơ hồ

Giả sử package có:

~~~sql
PROCEDURE lookup(p_id IN NUMBER);

PROCEDURE lookup(
    p_id IN NUMBER,
    p_mode IN VARCHAR2 DEFAULT 'FULL'
);
~~~

Cả hai overload đều có thể được xem xét khi caller chỉ truyền một NUMBER:

~~~sql
lookup(100);
~~~

Lời gọi có thể mơ hồ vì overload thứ hai cũng có thể được gọi sau khi dùng default cho P_MODE. Tránh thiết kế các overload chồng lấn như vậy; nếu cần, truyền đủ tham số để phân biệt hoặc đổi tên API.

## 10. Named notation và overloading

Named notation có thể giúp phân biệt các overload đã có chữ ký khác nhau, vì mỗi overload có thể công bố các formal parameter name khác nhau.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE employee_lookup AS
    PROCEDURE find_employee(
        p_employee_id IN NUMBER
    );

    PROCEDURE find_employee(
        p_employee_code IN VARCHAR2
    );
END employee_lookup;
/
~~~

Các lời gọi:

~~~sql
BEGIN
    employee_lookup.find_employee(
        p_employee_id => 101
    );

    employee_lookup.find_employee(
        p_employee_code => 'E-101'
    );
END;
/
~~~

Tên tham số giúp lời gọi biểu đạt rõ dạng tìm kiếm mong muốn.

### 10.1. Tên tham số không tự tạo overload

Hai khai báo cùng tên, cùng kiểu, cùng số lượng không trở thành hai overload hợp lệ chỉ vì formal parameter names khác nhau. Named notation chỉ ánh xạ lời gọi tới một khai báo hợp lệ; nó không thay thế quy tắc chữ ký.

### 10.2. Cùng tên tham số có thể không giúp phân biệt

Nếu hai overload có cùng tên formal parameter nhưng khác thứ tự kiểu, named notation có thể vẫn phù hợp với cả hai tùy ánh xạ. Không mặc định rằng dùng tên tham số sẽ luôn giải quyết ambiguity.

Khi cần phân biệt:
- Dùng actual argument có datatype rõ ràng.
- Dùng tên formal parameter đặc trưng nếu các overload đã khai báo khác tên.
- Thiết kế chữ ký không chồng lấn.
- Dùng tên subprogram khác nếu hai hành vi không thực sự là cùng một API.

### 10.3. Đổi tên formal parameter có thể ảnh hưởng caller

Với positional notation, caller không phụ thuộc tên formal parameter. Với named notation, caller phụ thuộc tên đó.

Ví dụ caller hiện tại:

~~~sql
employee_lookup.find_employee(
    p_employee_code => 'E-101'
);
~~~

Nếu package đổi P_EMPLOYEE_CODE thành P_CODE, caller dùng named notation cũ có thể không còn compile. Vì vậy, tên tham số trong package specification là một phần của public API.

## 11. OUT và IN OUT với hai kiểu notation

Positional và named notation đều có thể truyền tham số OUT/IN OUT. Actual argument tương ứng phải là biến có thể nhận giá trị, không phải literal hoặc biểu thức bất biến.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE calculation_api AS
    PROCEDURE calculate_total(
        p_quantity IN NUMBER,
        p_unit_price IN NUMBER,
        p_total OUT NUMBER
    );
END calculation_api;
/
~~~

Lời gọi positional:

~~~sql
DECLARE
    l_total NUMBER;
BEGIN
    calculation_api.calculate_total(3, 250, l_total);
    DBMS_OUTPUT.PUT_LINE(l_total);
END;
/
~~~

Lời gọi named:

~~~sql
DECLARE
    l_total NUMBER;
BEGIN
    calculation_api.calculate_total(
        p_unit_price => 250,
        p_total => l_total,
        p_quantity => 3
    );
    DBMS_OUTPUT.PUT_LINE(l_total);
END;
/
~~~

Không thể truyền một literal làm OUT actual argument:

~~~sql
-- Sai: literal không phải biến nhận giá trị.
calculation_api.calculate_total(3, 250, 0);
~~~

### 11.1. Mode không dùng để overload

Nếu hai procedure chỉ khác IN và OUT, Oracle không coi đó là hai overload phân biệt. Mode là quy tắc truyền dữ liệu, không phải cách tạo chữ ký riêng.

### 11.2. IN OUT cần biến đầu vào và đầu ra

IN OUT actual argument cung cấp giá trị ban đầu và nhận giá trị sau khi subprogram kết thúc. Caller phải truyền biến có datatype tương thích.

~~~sql
PROCEDURE add_fee(p_amount IN OUT NUMBER);
~~~

Named notation:

~~~sql
add_fee(p_amount => l_amount);
~~~

## 12. Overloading trong package specification và body

Package specification là hợp đồng public. Mỗi overload public phải được khai báo rõ:

~~~sql
CREATE OR REPLACE PACKAGE payment_api AS
    PROCEDURE pay(
        p_order_id IN NUMBER,
        p_amount IN NUMBER
    );

    PROCEDURE pay(
        p_order_code IN VARCHAR2,
        p_amount IN NUMBER
    );

    FUNCTION get_status(
        p_order_id IN NUMBER
    ) RETURN VARCHAR2;

    FUNCTION get_status(
        p_order_code IN VARCHAR2
    ) RETURN VARCHAR2;
END payment_api;
/
~~~

Package body triển khai từng khai báo:

~~~sql
CREATE OR REPLACE PACKAGE BODY payment_api AS

    PROCEDURE pay(
        p_order_id IN NUMBER,
        p_amount IN NUMBER
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Pay by order id: ' || p_order_id ||
            ', amount=' || p_amount
        );
    END pay;

    PROCEDURE pay(
        p_order_code IN VARCHAR2,
        p_amount IN NUMBER
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Pay by order code: ' || p_order_code ||
            ', amount=' || p_amount
        );
    END pay;

    FUNCTION get_status(
        p_order_id IN NUMBER
    ) RETURN VARCHAR2 IS
    BEGIN
        RETURN 'STATUS_BY_ID_' || p_order_id;
    END get_status;

    FUNCTION get_status(
        p_order_code IN VARCHAR2
    ) RETURN VARCHAR2 IS
    BEGIN
        RETURN 'STATUS_BY_CODE_' || p_order_code;
    END get_status;

END payment_api;
/
~~~

Gọi:

~~~sql
BEGIN
    payment_api.pay(1001, 500);
    payment_api.pay('ORD-A100', 500);

    DBMS_OUTPUT.PUT_LINE(payment_api.get_status(1001));
    DBMS_OUTPUT.PUT_LINE(payment_api.get_status('ORD-A100'));
END;
/
~~~

### 12.1. Chữ ký trong body phải khớp specification

Khi định nghĩa overload trong package body, danh sách tham số phải tương ứng với khai báo trong specification về thứ tự, kiểu và mode. Nếu thiếu một implementation hoặc implementation không khớp, package có thể không biên dịch hợp lệ.

Khi thay đổi API:
- Cập nhật specification.
- Cập nhật body tương ứng.
- Biên dịch package.
- Kiểm tra USER_ERRORS hoặc ALL_ERRORS.
- Kiểm tra các caller phụ thuộc package.

### 12.2. Overload private trong package body

Package body có thể khai báo subprogram private để hỗ trợ nội bộ. Caller bên ngoài không thể gọi trực tiếp overload private. Nếu tên nội bộ trùng với public subprogram, cần xem quy tắc phạm vi và phân giải tên; nên dùng tên helper rõ ràng để tránh làm code khó hiểu.

## 13. Lỗi thường gặp khi overload và gọi subprogram

| Lỗi | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| PLS-00306 | Sai số lượng hoặc kiểu actual arguments | Kiểm tra signature, thứ tự, tên và datatype |
| PLS-00307 | Nhiều overload cùng phù hợp | Dùng kiểu rõ ràng, CAST hoặc thiết kế lại chữ ký |
| PLS-00302 | Component không được khai báo trong package/type | Kiểm tra package specification và tên |
| PLS-00323 | Subprogram khai báo trong package spec nhưng chưa được định nghĩa trong body phù hợp | Bổ sung implementation đúng chữ ký |
| PLS-00307 khi truyền NULL | NULL không xác định kiểu mong muốn | CAST NULL hoặc dùng biến typed |
| Lời gọi named không compile | Formal parameter name không khớp | Dùng đúng tên trong specification |
| Lời gọi positional chạy sai ý nghĩa | Các tham số cùng kiểu bị truyền nhầm vị trí | Dùng named notation |
| Overload không compile | Chỉ khác parameter name/mode/subtype/return type | Tạo khác biệt chữ ký hợp lệ |
| Lời gọi một tham số bị mơ hồ | Nhiều overload có default parameter | Tránh chữ ký chồng lấn hoặc truyền thêm đối số phân biệt |
| Package body invalid | Implementation không khớp specification | Đồng bộ thứ tự, kiểu, mode và tên subprogram |

### 13.1. Xem lỗi biên dịch package

Trong schema hiện tại:

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE name = 'PAYMENT_API'
ORDER BY sequence;
~~~

Nếu package thuộc schema khác và có quyền, dùng ALL_ERRORS hoặc DBA_ERRORS phù hợp.

### 13.2. Xem khai báo package

Có thể xem source:

~~~sql
SELECT line, text
FROM user_source
WHERE name = 'PAYMENT_API'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY type, line;
~~~

Đối chiếu specification và body để xác định overload nào đã được công bố và triển khai.

## 14. Thiết kế API package dễ gọi

Overloading giúp caller dùng một tên cho các biến thể cùng mục đích, nhưng quá nhiều overload có thể làm lời gọi khó phân giải.

### 14.1. Chỉ overload khi các biến thể cùng một ý nghĩa

Ví dụ hợp lý:

~~~sql
PROCEDURE find_customer(p_customer_id IN NUMBER);
PROCEDURE find_customer(p_customer_code IN VARCHAR2);
~~~

Cả hai đều là thao tác tìm khách hàng, khác cách định danh.

Ví dụ khó hiểu hơn là dùng cùng tên PROCESS cho những hành vi không liên quan. Nếu caller phải nhớ hàng loạt quy tắc ngầm, tên riêng có thể tốt hơn.

### 14.2. Tránh overload quá giống nhau

Không nên tạo các overload:
- Khác nhau chỉ bằng subtype.
- Khác nhau ở parameter mode.
- Có nhiều default khiến lời gọi một phần mơ hồ.
- Dựa vào implicit conversion để chọn.
- Có nhiều tham số cùng kiểu nhưng thứ tự khác nhau mà ý nghĩa không rõ.

### 14.3. Dùng named notation cho API nhiều tham số

Với procedure:

~~~sql
PROCEDURE create_invoice(
    p_customer_id IN NUMBER,
    p_invoice_date IN DATE,
    p_currency_code IN VARCHAR2,
    p_include_tax IN BOOLEAN DEFAULT TRUE,
    p_note IN VARCHAR2 DEFAULT NULL
);
~~~

Lời gọi:

~~~sql
invoice_api.create_invoice(
    p_customer_id => 100,
    p_invoice_date => DATE '2025-03-08',
    p_currency_code => 'VND',
    p_note => 'March invoice'
);
~~~

P_INCLUDE_TAX dùng default TRUE. Caller không cần điền placeholder cho tham số ở giữa.

### 14.4. Giữ tên tham số ổn định

Nếu package specification là API cho nhiều ứng dụng, hãy xem tên formal parameter như một phần hợp đồng khi caller có thể dùng named notation. Thay tên có thể phá source code của caller dù datatype và thứ tự tham số không đổi.

### 14.5. Tránh overload dựa trên chuỗi có thể chuyển đổi

Nếu một overload nhận NUMBER và overload khác nhận VARCHAR2, hãy yêu cầu caller truyền đúng datatype. Đừng dựa vào việc chuỗi '100' có thể được chuyển thành NUMBER ở một số ngữ cảnh; điều đó làm code phụ thuộc chuyển đổi ngầm và có thể gây lỗi khi NLS hoặc datatype thay đổi.

## 15. Ví dụ tổng hợp: package tra cứu và tạo đơn hàng

Tạo package có hai overload tìm đơn hàng và một procedure tạo đơn với tham số mặc định.

### 15.1. Package specification

~~~sql
CREATE OR REPLACE PACKAGE order_service AS
    PROCEDURE find_order(
        p_order_id IN NUMBER
    );

    PROCEDURE find_order(
        p_order_code IN VARCHAR2
    );

    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_order_date IN DATE,
        p_status IN VARCHAR2 DEFAULT 'NEW'
    );
END order_service;
/
~~~

### 15.2. Package body minh họa

~~~sql
CREATE OR REPLACE PACKAGE BODY order_service AS

    PROCEDURE find_order(
        p_order_id IN NUMBER
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Find by numeric id: ' || p_order_id
        );
    END find_order;

    PROCEDURE find_order(
        p_order_code IN VARCHAR2
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Find by code: ' || p_order_code
        );
    END find_order;

    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_order_date IN DATE,
        p_status IN VARCHAR2 DEFAULT 'NEW'
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Customer=' || p_customer_id ||
            ', date=' || TO_CHAR(p_order_date, 'YYYY-MM-DD') ||
            ', status=' || p_status
        );
    END create_order;

END order_service;
/
~~~

Đây là ví dụ API minh họa; package production sẽ thực hiện SELECT/INSERT thực tế và quản lý transaction theo ranh giới nghiệp vụ.

### 15.3. Gọi overload bằng positional notation

~~~sql
BEGIN
    order_service.find_order(1001);
    order_service.find_order('ORD-2025-001');
END;
/
~~~

### 15.4. Gọi overload bằng named notation

~~~sql
BEGIN
    order_service.find_order(
        p_order_id => 1001
    );

    order_service.find_order(
        p_order_code => 'ORD-2025-001'
    );
END;
/
~~~

### 15.5. Gọi procedure có default bằng positional notation

~~~sql
BEGIN
    order_service.create_order(
        100,
        DATE '2025-03-08'
    );
END;
/
~~~

P_STATUS dùng giá trị mặc định NEW.

### 15.6. Gọi procedure có default bằng named notation

~~~sql
BEGIN
    order_service.create_order(
        p_status => 'PENDING',
        p_customer_id => 100,
        p_order_date => DATE '2025-03-08'
    );
END;
/
~~~

Thứ tự named arguments được tự do thay đổi.

### 15.7. Gọi bằng mixed notation

~~~sql
BEGIN
    order_service.create_order(
        100,
        p_status => 'PENDING',
        p_order_date => DATE '2025-03-08'
    );
END;
/
~~~

Đối số positional đầu tiên ánh xạ tới P_CUSTOMER_ID; các đối số còn lại ánh xạ theo tên.

## 16. Quy trình xử lý lời gọi mơ hồ

Khi gặp PLS-00307 hoặc một lời gọi overload khó đọc:

1. Tìm tất cả overload cùng tên trong package specification và phạm vi hiện tại.
2. Ghi lại số lượng và thứ tự formal parameters.
3. Ghi lại datatype và mode của từng parameter.
4. Kiểm tra actual arguments có literal không định kiểu như NULL hay không.
5. Kiểm tra default parameters có làm nhiều overload cùng phù hợp không.
6. Kiểm tra implicit conversion.
7. Xác định named arguments có khớp formal parameter name của overload dự kiến không.
8. Dùng CAST hoặc biến có datatype rõ để loại bỏ ambiguity.
9. Nếu chữ ký chồng lấn, sửa API để caller có thể phân biệt rõ.
10. Biên dịch lại package và kiểm tra USER_ERRORS.

Ví dụ từ lời gọi mơ hồ:

~~~sql
display_api.show_value(NULL);
~~~

thành lời gọi có kiểu:

~~~sql
display_api.show_value(CAST(NULL AS NUMBER));
~~~

Hoặc dùng biến:

~~~sql
DECLARE
    l_value DATE := NULL;
BEGIN
    display_api.show_value(l_value);
END;
/
~~~

Nếu ambiguity do default parameters, CAST có thể không đủ; hãy truyền thêm đối số hoặc thay đổi thiết kế overload.

## 17. Những nhầm lẫn thường gặp

**Overloading là tạo nhiều procedure cùng tên bất kể tham số.** Không đúng. Các khai báo phải có khác biệt chữ ký mà Oracle có thể phân biệt.

**Chỉ đổi tên formal parameter là tạo được overload mới.** Không đúng. Parameter name không đủ để phân biệt chữ ký.

**IN và OUT tạo hai overload khác nhau.** Không đúng. Parameter mode không phải tiêu chí phân biệt overload.

**INTEGER và SMALLINT luôn là hai kiểu độc lập để overload.** Không đúng. Chúng là subtype thuộc họ NUMBER và không thể chỉ dùng khác biệt subtype để tạo overload.

**Có thể overload function bằng cách đổi RETURN type.** Không đúng. Danh sách tham số phải tạo khác biệt phù hợp.

**DEFAULT khác nhau làm hai khai báo trở thành hai overload.** Không đúng. Default không phải tiêu chí tạo chữ ký mới.

**Positional notation dễ đọc hơn trong mọi trường hợp.** Không đúng. Nhiều tham số cùng kiểu có thể bị truyền nhầm mà compiler không phát hiện.

**Named notation có thể viết đối số theo bất kỳ thứ tự nào và trộn tùy ý.** Named arguments có thể đổi thứ tự, nhưng positional arguments phải đứng trước named arguments.

**Named notation luôn giải quyết được mọi ambiguity.** Không đúng. Nếu nhiều overload vẫn khớp tên và kiểu sau khi ánh xạ, lời gọi có thể còn mơ hồ.

**Có thể bỏ một tham số ở giữa bằng positional notation rồi truyền tham số sau.** Không đúng. Dùng named notation để bỏ qua tham số IN có default.

**OUT parameter có thể nhận literal.** Không đúng. OUT/IN OUT cần actual variable phù hợp.

**NULL luôn chọn overload có kiểu phổ biến nhất.** Không đúng. Untyped NULL có thể khớp nhiều overload; dùng CAST hoặc biến typed.

**Thay tên tham số trong package specification không ảnh hưởng caller.** Không đúng nếu caller dùng named notation.

**Một overload public chỉ cần có trong package body.** Không đúng. Caller bên ngoài chỉ gọi được subprogram được công bố trong package specification.

**Mọi lỗi PLS-00307 đều do thiếu CAST.** Không đúng. Có thể do default parameters, chữ ký chồng lấn hoặc named arguments không đủ phân biệt.

## 18. Bài tập tự luyện

1. Tạo package có procedure SHOW_VALUE nhận NUMBER và VARCHAR2.
2. Thêm overload nhận DATE và gọi cả ba phiên bản.
3. Tạo hai overload FIND_EMPLOYEE nhận EMPLOYEE_ID NUMBER và EMPLOYEE_CODE VARCHAR2.
4. Giải thích vì sao chỉ đổi tên P_ID thành P_CODE không tạo overload mới nếu datatype không đổi.
5. Thử tạo hai overload chỉ khác IN và OUT. Xác định lỗi biên dịch.
6. Vì sao INTEGER và SMALLINT không nên được dùng để tạo hai overload riêng?
7. Viết hai function cùng tên, cùng tham số nhưng khác RETURN type. Giải thích vì sao không hợp lệ.
8. Tạo overload theo số lượng tham số.
9. Tạo overload có hai tham số DATE và NUMBER theo hai thứ tự khác nhau.
10. Gọi hai overload ở bài trước bằng positional notation.
11. Viết lời gọi named notation cho procedure có ba tham số.
12. Viết lời gọi mixed notation với một positional argument đầu tiên và hai named arguments sau.
13. Viết một lời gọi sai có positional argument sau named argument và giải thích.
14. Tạo procedure có hai tham số IN cùng kiểu DATE. Dùng named notation để tránh nhầm ngày bắt đầu/kết thúc.
15. Tạo procedure có tham số P_STATUS mặc định NEW và gọi không truyền tham số đó.
16. Bỏ qua tham số mặc định ở giữa bằng named notation.
17. Vì sao positional notation không thể bỏ qua tham số giữa rồi truyền tham số tiếp theo?
18. Tạo overload một tham số và overload hai tham số có tham số thứ hai DEFAULT. Dự đoán lời gọi một tham số có mơ hồ không.
19. Gọi overload bằng NULL và xử lý PLS-00307 bằng CAST.
20. Khai báo biến DATE NULL và dùng nó để chọn overload DATE.
21. Giải thích vì sao tên formal parameter có thể là một phần của public API.
22. Tạo package specification có hai overload nhưng body chỉ định nghĩa một. Xem lỗi USER_ERRORS.
23. Tạo package có overload public và helper private.
24. Viết function overload NUMBER/DATE trả VARCHAR2 và gọi bằng biến có kiểu rõ.
25. Tạo procedure có OUT parameter và gọi bằng positional notation.
26. Gọi procedure OUT parameter bằng named notation.
27. Vì sao không thể truyền literal cho OUT parameter?
28. Phân biệt PLS-00306 và PLS-00307.
29. Thiết kế package API tìm khách hàng theo ID, email hoặc mã ngoài sao cho lời gọi không mơ hồ.
30. Xem một package có nhiều overload và lập bảng mapping formal/actual arguments cho các lời gọi positional, named và mixed.

**Overloading cho phép một tên subprogram đại diện cho nhiều chữ ký tham số có thể phân biệt; positional notation ghép đối số theo thứ tự, còn named notation ghép theo tên formal parameter và giúp lời gọi nhiều tham số dễ đọc hơn.** Default values cho phép bỏ qua tham số IN, nhưng có thể làm các overload chồng lấn và gây ambiguity. Hãy thiết kế chữ ký rõ ràng, dùng datatype cụ thể khi cần và giữ tên tham số public ổn định để package API dễ gọi, dễ bảo trì.
