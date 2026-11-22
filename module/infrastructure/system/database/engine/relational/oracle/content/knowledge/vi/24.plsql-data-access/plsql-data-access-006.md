# REF CURSOR, SYS_REFCURSOR và trả tập kết quả cho ứng dụng

Một procedure PL/SQL có thể trả dữ liệu cho ứng dụng dưới dạng **tập kết quả** thay vì chỉ trả một giá trị scalar hoặc ghi dữ liệu vào bảng trung gian. Oracle thường dùng REF CURSOR cho mục đích này. REF CURSOR là một biến con trỏ trỏ tới vùng làm việc của câu truy vấn đang mở; ứng dụng nhận con trỏ, đọc từng hàng và đóng nó khi hoàn tất.

Trong PL/SQL, REF CURSOR có thể là kiểu mạnh (strong) hoặc kiểu yếu (weak). Oracle cung cấp sẵn kiểu weak REF CURSOR tên là SYS_REFCURSOR, rất thường dùng làm tham số OUT của procedure. Ứng dụng gọi procedure qua driver, lấy cursor trả về và fetch các hàng như một ResultSet hoặc data reader.

Bài học này trình bày:

- REF CURSOR khác explicit cursor và collection như thế nào.
- Strong REF CURSOR, weak REF CURSOR và SYS_REFCURSOR.
- Cách OPEN, FETCH, CLOSE và quản lý vòng đời cursor.
- Trả một hoặc nhiều result set qua tham số OUT.
- Gọi procedure từ SQL*Plus/SQLcl và ứng dụng JDBC.
- Dùng bind variables khi mở cursor bằng dynamic SQL.
- Các vấn đề về NULL, transaction, quyền, tài nguyên và hiệu năng.

Các ví dụ dùng Oracle Database 19c và cú pháp PL/SQL thông dụng. Một số API client phụ thuộc phiên bản driver; luôn đối chiếu tài liệu của driver đang triển khai.

## 1. REF CURSOR là gì?

Khi một câu SELECT được mở, Oracle tạo một cursor gắn với vùng làm việc của câu SQL. REF CURSOR là một biến PL/SQL giữ tham chiếu đến cursor đó. Có thể truyền biến này qua tham số procedure/function để caller đọc kết quả.

~~~text
Application
    |
    | CALL procedure
    v
PL/SQL procedure
    |
    | OPEN ref_cursor FOR SELECT ...
    v
Oracle SQL cursor / result set
    |
    | OUT SYS_REFCURSOR
    v
Application receives cursor handle
    |
    | FETCH rows
    v
Application processes each row
    |
    | CLOSE result set
    v
Cursor resources released
~~~

REF CURSOR không phải bản sao dữ liệu đã được materialize trong một collection. Nó là handle tới một cursor đang mở ở database session. Ứng dụng đọc hàng qua giao thức của driver; dữ liệu không nhất thiết được tải toàn bộ vào bộ nhớ client ngay khi procedure trả về.

### 1.1. REF CURSOR thường dùng khi nào?

- Procedure cần trả nhiều hàng cho Java, .NET, Python hoặc ứng dụng khác.
- Một API cần đóng gói logic truy vấn trong PL/SQL.
- Cần trả nhiều tập kết quả trong cùng một lần gọi.
- Cần mở cursor trên một trong nhiều câu SELECT tùy tham số đầu vào.
- Cần chuyển một cursor giữa các procedure hoặc function PL/SQL.

Nếu chỉ cần một giá trị, dùng tham số OUT scalar. Nếu cần một tập dữ liệu nhỏ đã xử lý trong PL/SQL, collection có thể phù hợp. REF CURSOR phù hợp khi caller cần đọc result set theo kiểu cursor.

## 2. Explicit cursor và REF CURSOR

Hai loại đều cho phép fetch dữ liệu từng hàng, nhưng khác cách xác định câu query.

### 2.1. Explicit cursor

Explicit cursor gắn với câu SELECT được khai báo cố định trong phần khai báo PL/SQL:

~~~sql
DECLARE
    CURSOR c_customers IS
        SELECT customer_id, customer_name
        FROM customers
        WHERE status = 'ACTIVE'
        ORDER BY customer_id;

    v_id   customers.customer_id%TYPE;
    v_name customers.customer_name%TYPE;
BEGIN
    OPEN c_customers;

    LOOP
        FETCH c_customers INTO v_id, v_name;
        EXIT WHEN c_customers%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(v_id || ': ' || v_name);
    END LOOP;

    CLOSE c_customers;
END;
/
~~~

Query được cố định trong khai báo cursor. Có thể dùng cursor parameters để truyền giá trị lọc, nhưng không thể thay query text của explicit cursor sau khi compile.

### 2.2. REF CURSOR

REF CURSOR là một cursor variable. Câu SELECT được gắn vào biến khi chạy bằng OPEN ... FOR:

~~~sql
DECLARE
    TYPE t_customer_cursor IS REF CURSOR;
    v_cursor t_customer_cursor;
    v_id     customers.customer_id%TYPE;
    v_name   customers.customer_name%TYPE;
BEGIN
    OPEN v_cursor FOR
        SELECT customer_id, customer_name
        FROM customers
        WHERE status = 'ACTIVE'
        ORDER BY customer_id;

    LOOP
        FETCH v_cursor INTO v_id, v_name;
        EXIT WHEN v_cursor%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(v_id || ': ' || v_name);
    END LOOP;

    CLOSE v_cursor;
END;
/
~~~

Điểm khác biệt là REF CURSOR có thể được mở với những câu SELECT khác nhau tùy logic runtime, và có thể được truyền qua tham số hoặc trả về caller.

### 2.3. So sánh nhanh

| Tiêu chí | Explicit cursor | REF CURSOR |
| --- | --- | --- |
| Query | Khai báo cố định | Gắn lúc runtime bằng OPEN FOR |
| Loại biến | Cursor đã khai báo | Cursor variable |
| Truyền qua tham số | Có thể truyền cursor parameter trong PL/SQL theo khai báo phù hợp | Là mục đích sử dụng phổ biến |
| Trả result set cho client | Không thuận tiện như API OUT cursor | Rất phù hợp |
| Thay đổi query runtime | Hạn chế | Có thể chọn query hoặc dùng dynamic SQL |
| Fetch/close | OPEN, FETCH, CLOSE | OPEN FOR, FETCH, CLOSE |

## 3. Strong REF CURSOR và weak REF CURSOR

Khi khai báo REF CURSOR type, có thể chỉ định kiểu hàng mà cursor trả về hoặc bỏ qua kiểu hàng.

### 3.1. Strong REF CURSOR

Strong REF CURSOR có mệnh đề RETURN mô tả kiểu hàng:

~~~sql
DECLARE
    TYPE t_customer_cursor IS REF CURSOR
        RETURN customers%ROWTYPE;

    v_cursor t_customer_cursor;
    v_customer customers%ROWTYPE;
BEGIN
    OPEN v_cursor FOR
        SELECT *
        FROM customers
        WHERE customer_id = 101;

    FETCH v_cursor INTO v_customer;
    CLOSE v_cursor;
END;
/
~~~

Query dùng để OPEN phải trả về row shape tương thích với kiểu RETURN đã khai báo. Strong cursor giúp phát hiện sớm lỗi không khớp kiểu hàng khi compile hoặc mở cursor theo quy tắc PL/SQL.

Có thể định nghĩa row type riêng nếu API chỉ trả một nhóm cột:

~~~sql
DECLARE
    TYPE t_customer_row IS RECORD (
        customer_id   customers.customer_id%TYPE,
        customer_name customers.customer_name%TYPE
    );

    TYPE t_customer_cursor IS REF CURSOR
        RETURN t_customer_row;

    v_cursor t_customer_cursor;
    v_row    t_customer_row;
BEGIN
    OPEN v_cursor FOR
        SELECT customer_id, customer_name
        FROM customers
        WHERE status = 'ACTIVE';

    FETCH v_cursor INTO v_row;
    CLOSE v_cursor;
END;
/
~~~

Strong cursor phù hợp khi cấu trúc result set là một phần cố định của contract PL/SQL và muốn compiler hỗ trợ kiểm tra kiểu.

### 3.2. Weak REF CURSOR

Weak REF CURSOR không có mệnh đề RETURN:

~~~sql
DECLARE
    TYPE t_any_cursor IS REF CURSOR;
    v_cursor t_any_cursor;
BEGIN
    OPEN v_cursor FOR
        SELECT customer_id, customer_name
        FROM customers;
    CLOSE v_cursor;
END;
/
~~~

Vì không ràng buộc row shape khi khai báo, weak cursor có thể mở các query trả về cấu trúc cột khác nhau. Caller vẫn phải fetch theo đúng số lượng, thứ tự và kiểu cột của query đang mở; weak không có nghĩa là dữ liệu không cần schema.

### 3.3. SYS_REFCURSOR

Oracle cung cấp sẵn SYS_REFCURSOR như một weak REF CURSOR type chuẩn. Vì vậy không cần tự khai báo type nếu dùng kiểu này:

~~~sql
DECLARE
    v_result SYS_REFCURSOR;
BEGIN
    OPEN v_result FOR
        SELECT customer_id, customer_name
        FROM customers;

    CLOSE v_result;
END;
/
~~~

SYS_REFCURSOR đặc biệt tiện trong public procedure API:

~~~sql
CREATE OR REPLACE PROCEDURE get_customers (
    p_result OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT customer_id, customer_name
        FROM customers
        ORDER BY customer_id;
END;
/
~~~

Tên SYS_REFCURSOR thường được dùng khi client cần một result set linh hoạt. Nếu contract yêu cầu kiểu hàng cố định và cần kiểm tra mạnh hơn trong PL/SQL, có thể khai báo strong REF CURSOR type trong package specification.

## 4. Vòng đời OPEN, FETCH và CLOSE

Một REF CURSOR được dùng theo ba bước:

1. OPEN FOR: gắn query vào cursor variable và mở cursor.
2. FETCH: lấy một hoặc nhiều hàng từ result set.
3. CLOSE: giải phóng cursor sau khi không còn cần đọc.

### 4.1. OPEN FOR

~~~sql
OPEN v_cursor FOR
    SELECT customer_id, customer_name
    FROM customers
    WHERE status = 'ACTIVE';
~~~

Sau OPEN, cursor được mở và sẵn sàng fetch. Một cursor variable đang mở không thể được OPEN lại như thể nó chưa có query; hãy CLOSE trước khi tái sử dụng.

### 4.2. FETCH từng hàng

~~~sql
FETCH v_cursor INTO v_id, v_name;
EXIT WHEN v_cursor%NOTFOUND;
~~~

Fetch gán các cột của hàng kế tiếp vào biến đích theo thứ tự. Số biến và kiểu dữ liệu phải tương thích với select list. Nếu không có hàng tiếp theo, %NOTFOUND là TRUE.

### 4.3. Thuộc tính cursor

Các thuộc tính thường dùng của cursor variable:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| %ISOPEN | TRUE nếu cursor đang mở |
| %FOUND | TRUE nếu FETCH gần nhất lấy được một hàng; NULL trước fetch đầu tiên |
| %NOTFOUND | TRUE nếu FETCH gần nhất không lấy được hàng; NULL trước fetch đầu tiên |
| %ROWCOUNT | Số hàng đã fetch thành công |

Ví dụ:

~~~sql
LOOP
    FETCH v_cursor INTO v_id, v_name;
    EXIT WHEN v_cursor%NOTFOUND;

    DBMS_OUTPUT.PUT_LINE('Fetched rows: ' || v_cursor%ROWCOUNT);
END LOOP;
~~~

Kiểm tra %NOTFOUND ngay sau FETCH. Nếu kiểm tra trước lần FETCH đầu tiên, thuộc tính còn NULL và không thể kết thúc vòng lặp theo cách mong muốn.

### 4.4. CLOSE

~~~sql
IF v_cursor%ISOPEN THEN
    CLOSE v_cursor;
END IF;
~~~

Close cursor giải phóng cursor handle và các tài nguyên liên quan. Đừng để cursor mở lâu hơn cần thiết.

### 4.5. Xử lý exception để luôn đóng cursor

~~~sql
DECLARE
    TYPE t_cursor IS REF CURSOR;
    v_cursor t_cursor;
    v_id NUMBER;
BEGIN
    OPEN v_cursor FOR
        SELECT customer_id
        FROM customers;

    LOOP
        FETCH v_cursor INTO v_id;
        EXIT WHEN v_cursor%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE(v_id);
    END LOOP;

    CLOSE v_cursor;
EXCEPTION
    WHEN OTHERS THEN
        IF v_cursor%ISOPEN THEN
            CLOSE v_cursor;
        END IF;
        RAISE;
END;
/
~~~

Khi viết procedure trả cursor cho client, không đóng cursor trước khi kết thúc procedure. Client cần cursor vẫn mở để fetch; quyền sở hữu việc đọc và đóng được chuyển cho caller sau khi nhận OUT parameter.

## 5. Trả SYS_REFCURSOR qua tham số OUT

Đây là mẫu API thường gặp nhất. Procedure mở cursor và gán handle vào tham số OUT.

### 5.1. Tạo procedure trả danh sách khách hàng

~~~sql
CREATE OR REPLACE PROCEDURE get_active_customers (
    p_min_credit IN NUMBER,
    p_result     OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT
            customer_id,
            customer_name,
            credit_limit
        FROM customers
        WHERE status = 'ACTIVE'
          AND credit_limit >= p_min_credit
        ORDER BY customer_id;
END;
/
~~~

Procedure không fetch các hàng vào biến PL/SQL. Nó chỉ mở cursor và trả cursor handle. Client sẽ đọc dữ liệu.

### 5.2. Gọi từ SQL*Plus hoặc SQLcl

Các client hỗ trợ bind variable kiểu REFCURSOR có thể gọi:

~~~sql
VARIABLE rc REFCURSOR
EXEC get_active_customers(500, :rc);
PRINT rc
~~~

VARIABLE, EXEC và PRINT là lệnh của SQL*Plus/SQLcl, không phải cú pháp SQL thuần có thể chạy ở mọi driver. Trong ứng dụng, hãy dùng API của driver để bind tham số OUT.

### 5.3. Gọi procedure từ PL/SQL khác

PL/SQL caller có thể nhận cursor vào biến REF CURSOR và fetch:

~~~sql
DECLARE
    v_result SYS_REFCURSOR;
    v_id     customers.customer_id%TYPE;
    v_name   customers.customer_name%TYPE;
    v_limit  customers.credit_limit%TYPE;
BEGIN
    get_active_customers(
        p_min_credit => 500,
        p_result     => v_result
    );

    LOOP
        FETCH v_result INTO v_id, v_name, v_limit;
        EXIT WHEN v_result%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(v_id || ' - ' || v_name || ' - ' || v_limit);
    END LOOP;

    CLOSE v_result;
END;
/
~~~

Caller phải biết shape của result set để khai báo đúng biến FETCH. Nếu procedure đổi select list mà caller vẫn dùng cấu trúc cũ, caller có thể lỗi khi fetch hoặc cần cập nhật contract.

## 6. Trả cursor từ function

Function cũng có thể trả REF CURSOR. Function tạo cursor local, OPEN FOR query rồi RETURN cursor variable:

~~~sql
CREATE OR REPLACE FUNCTION open_active_customers (
    p_min_credit IN NUMBER
) RETURN SYS_REFCURSOR
AS
    v_result SYS_REFCURSOR;
BEGIN
    OPEN v_result FOR
        SELECT customer_id, customer_name, credit_limit
        FROM customers
        WHERE status = 'ACTIVE'
          AND credit_limit >= p_min_credit
        ORDER BY customer_id;

    RETURN v_result;
END;
/
~~~

PL/SQL caller:

~~~sql
DECLARE
    v_result SYS_REFCURSOR;
    v_id NUMBER;
    v_name VARCHAR2(100);
    v_limit NUMBER;
BEGIN
    v_result := open_active_customers(500);

    LOOP
        FETCH v_result INTO v_id, v_name, v_limit;
        EXIT WHEN v_result%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE(v_name);
    END LOOP;

    CLOSE v_result;
END;
/
~~~

Procedure với OUT cursor thường dễ dùng cho lời gọi thủ tục từ ứng dụng và có thể trả nhiều cursor. Function trả cursor phù hợp khi API được thiết kế theo dạng hàm trả về một handle. Trong cả hai trường hợp, caller có trách nhiệm đọc và đóng cursor.

## 7. Strong REF CURSOR trong package API

Nếu muốn public API có contract kiểu hàng cụ thể, khai báo REF CURSOR type trong package specification:

~~~sql
CREATE OR REPLACE PACKAGE customer_api AS
    TYPE t_customer_result IS REF CURSOR
        RETURN customers%ROWTYPE;

    PROCEDURE open_customer (
        p_customer_id IN customers.customer_id%TYPE,
        p_result      OUT t_customer_result
    );
END customer_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    PROCEDURE open_customer (
        p_customer_id IN customers.customer_id%TYPE,
        p_result      OUT t_customer_result
    ) AS
    BEGIN
        OPEN p_result FOR
            SELECT *
            FROM customers
            WHERE customer_id = p_customer_id;
    END open_customer;
END customer_api;
/
~~~

Caller có thể fetch vào record %ROWTYPE:

~~~sql
DECLARE
    v_result customer_api.t_customer_result;
    v_customer customers%ROWTYPE;
BEGIN
    customer_api.open_customer(101, v_result);
    FETCH v_result INTO v_customer;

    IF v_result%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(v_customer.customer_name);
    END IF;

    CLOSE v_result;
END;
/
~~~

Strong type giúp định nghĩa rõ hình dạng hàng, nhưng cũng khiến thay đổi cấu trúc hàng trở thành thay đổi contract. Nếu cần API ổn định lâu dài, có thể định nghĩa RECORD type riêng thay vì trả toàn bộ %ROWTYPE, để không vô tình công khai các cột nội bộ mới thêm vào bảng.

## 8. Trả nhiều tập kết quả

Một procedure có thể trả nhiều SYS_REFCURSOR qua nhiều tham số OUT. Mỗi cursor là một result set độc lập.

~~~sql
CREATE OR REPLACE PROCEDURE get_customer_dashboard (
    p_customer_id IN NUMBER,
    p_orders      OUT SYS_REFCURSOR,
    p_summary     OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_orders FOR
        SELECT order_id, order_date, order_status, total_amount
        FROM orders
        WHERE customer_id = p_customer_id
        ORDER BY order_date DESC;

    OPEN p_summary FOR
        SELECT
            COUNT(*) AS order_count,
            NVL(SUM(total_amount), 0) AS total_amount
        FROM orders
        WHERE customer_id = p_customer_id;
END;
/
~~~

Client cần bind cả hai OUT parameter, nhận hai cursor và đọc từng result set. Nếu một cursor không cần dùng, client vẫn phải đóng nó để giải phóng tài nguyên.

### 8.1. Implicit results

Oracle 12c trở lên còn hỗ trợ trả implicit result sets bằng DBMS_SQL.RETURN_RESULT cho client có hỗ trợ. Cách này có thể tránh khai báo nhiều OUT cursor parameter, nhưng khả năng tiêu thụ phụ thuộc driver/client. Với API cần tương thích rõ ràng giữa nhiều loại client, OUT SYS_REFCURSOR thường dễ nhận biết và kiểm soát hơn.

Không trộn implicit results và OUT cursor một cách tùy tiện. Hãy định nghĩa rõ số lượng, thứ tự, schema cột và cách client nhận mỗi result set.

## 9. Dynamic SQL và REF CURSOR

Có trường hợp procedure cần chọn một trong nhiều query theo tham số. Có thể mở weak cursor bằng dynamic SQL:

~~~sql
CREATE OR REPLACE PROCEDURE search_customers (
    p_region IN VARCHAR2,
    p_result OUT SYS_REFCURSOR
) AS
    l_sql VARCHAR2(4000);
BEGIN
    l_sql :=
        'SELECT customer_id, customer_name, region_code ' ||
        'FROM customers WHERE region_code = :region ' ||
        'ORDER BY customer_id';

    OPEN p_result FOR l_sql USING p_region;
END;
/
~~~

Giá trị p_region được truyền qua bind variable. Không nối trực tiếp dữ liệu người dùng vào chuỗi SQL.

### 9.1. Chọn query theo điều kiện

~~~sql
CREATE OR REPLACE PROCEDURE open_customer_search (
    p_mode   IN VARCHAR2,
    p_value  IN VARCHAR2,
    p_result OUT SYS_REFCURSOR
) AS
BEGIN
    IF p_mode = 'NAME' THEN
        OPEN p_result FOR
            SELECT customer_id, customer_name
            FROM customers
            WHERE customer_name LIKE p_value
            ORDER BY customer_name;
    ELSIF p_mode = 'REGION' THEN
        OPEN p_result FOR
            SELECT customer_id, customer_name
            FROM customers
            WHERE region_code = p_value
            ORDER BY customer_id;
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Unsupported search mode');
    END IF;
END;
/
~~~

Hai query có cùng số cột và kiểu tương thích để caller fetch theo một contract. Nếu các mode trả shape khác nhau, caller cần API hoặc result set riêng; đừng bắt client đoán cấu trúc dựa trên dữ liệu.

### 9.2. Bind value, whitelist identifier

Bind variable dùng cho giá trị dữ liệu, không dùng thay tên bảng, tên cột hoặc keyword SQL. Nếu bắt buộc chọn sort column:

- Dùng whitelist ánh xạ giá trị mode sang một trong các tên cột cố định.
- Không nối nguyên văn chuỗi do client gửi.
- Bind các giá trị lọc.
- Có thể dùng DBMS_ASSERT cho một số identifier khi thiết kế phù hợp, nhưng DBMS_ASSERT không thay thế whitelist và phân quyền.

Ví dụ:

~~~sql
IF p_sort = 'NAME' THEN
    l_order_by := 'customer_name';
ELSIF p_sort = 'DATE' THEN
    l_order_by := 'created_at';
ELSE
    RAISE_APPLICATION_ERROR(-20002, 'Invalid sort option');
END IF;
~~~

Chỉ các identifier đã được kiểm soát mới được ghép vào query text. Mọi dữ liệu đầu vào khác nên truyền bằng USING.

## 10. Fetch dữ liệu trong PL/SQL

### 10.1. Fetch từng hàng

~~~sql
DECLARE
    v_result SYS_REFCURSOR;
    v_id NUMBER;
    v_name VARCHAR2(100);
BEGIN
    OPEN v_result FOR
        SELECT customer_id, customer_name
        FROM customers
        ORDER BY customer_id;

    LOOP
        FETCH v_result INTO v_id, v_name;
        EXIT WHEN v_result%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE(v_id || ': ' || v_name);
    END LOOP;

    CLOSE v_result;
END;
/
~~~

Đây là cách dễ hiểu nhưng với số lượng hàng lớn, xử lý từng hàng trong PL/SQL có thể tốn chi phí chuyển đổi giữa SQL engine và PL/SQL engine.

### 10.2. BULK COLLECT

Có thể fetch nhiều hàng vào collection:

~~~sql
DECLARE
    TYPE t_customer_rows IS TABLE OF customers%ROWTYPE;
    v_rows t_customer_rows;
    v_result SYS_REFCURSOR;
BEGIN
    OPEN v_result FOR
        SELECT *
        FROM customers
        ORDER BY customer_id;

    LOOP
        FETCH v_result BULK COLLECT INTO v_rows LIMIT 100;
        EXIT WHEN v_rows.COUNT = 0;

        FOR i IN 1 .. v_rows.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(v_rows(i).customer_id);
        END LOOP;
    END LOOP;

    CLOSE v_result;
END;
/
~~~

LIMIT 100 giới hạn số hàng nạp vào collection mỗi lần fetch, tránh giữ toàn bộ result set lớn trong PGA. Chọn batch size dựa trên độ rộng hàng, bộ nhớ và hiệu năng đo được.

### 10.3. Không fetch quá số cột hoặc sai thứ tự

Weak REF CURSOR cho phép mở query linh hoạt, nhưng FETCH INTO vẫn cần biến phù hợp với select list. Nếu query trả ba cột mà caller chỉ khai báo hai biến, hoặc thứ tự/kiểu dữ liệu không khớp, thao tác fetch sẽ lỗi.

Để API ổn định:

- Liệt kê cột rõ ràng, tránh SELECT * trong public result contract.
- Giữ thứ tự và kiểu cột ổn định.
- Version hóa API nếu thay đổi result schema phá vỡ caller.
- Tài liệu hóa NULLability và ý nghĩa từng cột.

## 11. Nhận REF CURSOR trong ứng dụng Java

Oracle JDBC driver biểu diễn REF CURSOR như một result set. Một cách gọi phổ biến là bind OUT parameter với cursor type, thực thi procedure, rồi lấy ResultSet.

~~~java
import java.math.BigDecimal;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import oracle.jdbc.OracleTypes;

String call = "{call get_active_customers(?, ?)}";

try (CallableStatement stmt = connection.prepareCall(call)) {
    stmt.setBigDecimal(1, new BigDecimal("500"));
    stmt.registerOutParameter(2, OracleTypes.CURSOR);
    stmt.execute();

    try (ResultSet rs = (ResultSet) stmt.getObject(2)) {
        while (rs.next()) {
            long customerId = rs.getLong("CUSTOMER_ID");
            String customerName = rs.getString("CUSTOMER_NAME");
            BigDecimal creditLimit = rs.getBigDecimal("CREDIT_LIMIT");

            System.out.println(
                customerId + " " + customerName + " " + creditLimit
            );
        }
    }
}
~~~

Ví dụ dùng Oracle JDBC extension OracleTypes.CURSOR. Tùy phiên bản driver/JDBC API, có thể có lựa chọn chuẩn Types.REF_CURSOR; hãy kiểm tra hỗ trợ của driver được đóng gói cùng ứng dụng.

### 11.1. Quy tắc quản lý tài nguyên phía Java

- Giữ Connection mở trong khi ResultSet đang được đọc.
- Đóng ResultSet khi hoàn tất, kể cả khi xử lý lỗi.
- Đóng CallableStatement sau khi đã đọc cursor.
- Nếu dùng connection pool, chỉ trả connection về pool sau khi result set/statement liên quan đã đóng.
- Không lưu ResultSet để dùng sau khi connection đã đóng hoặc trả về pool.

Try-with-resources giúp đóng ResultSet và CallableStatement tự động. Connection thường do tầng quản lý transaction/pool sở hữu; không đóng connection ở đây nếu caller còn cần dùng nó.

### 11.2. Xử lý NULL trong JDBC

ResultSet.getLong() trả 0 khi cột SQL NULL; gọi wasNull() ngay sau getter để phân biệt:

~~~java
long creditLimitValue = rs.getLong("CREDIT_LIMIT");
boolean creditLimitIsNull = rs.wasNull();
~~~

Với kiểu tham chiếu như String hoặc BigDecimal, getter thường trả Java null khi SQL NULL. Không được mặc định 0 có nghĩa là giá trị thực nếu cột có thể NULL.

## 12. Nhận REF CURSOR trong ứng dụng .NET

Với Oracle Data Provider for .NET (ODP.NET), tham số OUT dùng kiểu OracleDbType.RefCursor. Client lấy OracleRefCursor và tạo OracleDataReader:

~~~csharp
using Oracle.ManagedDataAccess.Client;
using System.Data;

using (var cmd = connection.CreateCommand())
{
    cmd.CommandText = "GET_ACTIVE_CUSTOMERS";
    cmd.CommandType = CommandType.StoredProcedure;

    cmd.Parameters.Add(
        "p_min_credit",
        OracleDbType.Decimal
    ).Value = 500m;

    var resultParameter = cmd.Parameters.Add(
        "p_result",
        OracleDbType.RefCursor
    );
    resultParameter.Direction = ParameterDirection.Output;

    cmd.ExecuteNonQuery();

    using (var refCursor = (OracleRefCursor)resultParameter.Value)
    using (var reader = refCursor.GetDataReader())
    {
        while (reader.Read())
        {
            var customerId = reader.GetInt32(0);
            var customerName = reader.GetString(1);
        }
    }
}
~~~

Kiểu parameter và API cụ thể có thể khác giữa ODP.NET managed/unmanaged và phiên bản package. Dùng đúng namespace/driver mà ứng dụng đang tham chiếu. Giữ connection mở cho tới khi reader đóng.

## 13. Nhiều cursor và giới hạn tài nguyên

Mỗi cursor mở tiêu thụ tài nguyên session/database. Một procedure trả nhiều cursor, hoặc ứng dụng mở nhiều result set mà không đóng, có thể làm tăng số cursor đang mở và dẫn đến lỗi ORA-01000: maximum open cursors exceeded.

### 13.1. Tránh cursor leak

- Đóng ResultSet/DataReader ở client.
- Đóng statement sau khi đọc xong.
- Không mở cursor mới trên mỗi vòng lặp mà quên đóng cursor cũ.
- Khi exception, vẫn phải giải phóng tài nguyên.
- Với connection pool, reset/đóng mọi cursor trước khi trả connection.

Tăng tham số OPEN_CURSORS không thay thế việc sửa cursor leak. Trước tiên hãy kiểm tra code path và thống kê session đang giữ cursor.

### 13.2. Giới hạn số hàng trả về

API trả toàn bộ bảng lớn có thể tiêu tốn thời gian, network và tài nguyên. Hãy thiết kế:

- Filter bắt buộc hoặc mặc định hợp lý.
- Pagination theo key ổn định.
- Giới hạn số hàng tối đa nếu phù hợp nghiệp vụ.
- Fetch size/prefetch phù hợp driver.
- Sort có index hoặc kế hoạch thực thi được đo.

REF CURSOR không tự tạo pagination. Nếu client cần phân trang, query phải có predicate/keyset hoặc cơ chế offset/fetch được thiết kế rõ.

## 14. Transaction, read consistency và vòng đời kết nối

REF CURSOR được mở trong database session. Client cần giữ kết nối tương ứng để tiếp tục fetch. Nếu connection bị đóng, session kết thúc hoặc cursor bị đóng, client không thể tiếp tục đọc cursor handle đó.

Oracle cung cấp read consistency cho câu query. Cursor đang đọc phản ánh snapshot nhất quán theo thời điểm câu truy vấn được mở/thực thi. Nếu result set được đọc rất lâu trong khi dữ liệu liên tục thay đổi, Oracle có thể cần undo để tái tạo phiên bản nhất quán; thiếu undo cần thiết có thể dẫn tới ORA-01555: snapshot too old.

Vì vậy:

- Không giữ cursor mở trong khi chờ người dùng tương tác.
- Đọc result set và đóng sớm.
- Dùng pagination cho dữ liệu lớn nếu nghiệp vụ cho phép.
- Không commit/rollback tùy tiện giữa quá trình đọc nếu ứng dụng cần giữ transaction semantics nhất quán.
- Thiết kế retry khi connection bị ngắt; cursor cũ không thể tiếp tục sau khi session mất.

## 15. Quyền và bảo mật của procedure trả cursor

Procedure mặc định chạy theo definer rights nếu không khai báo AUTHID CURRENT_USER. Khi procedure mở query, cần hiểu owner của procedure, quyền trên các bảng được tham chiếu và quyền execute mà ứng dụng được cấp.

Ví dụ:

~~~sql
GRANT EXECUTE ON app_owner.get_active_customers TO app_runtime;
~~~

Chỉ cấp EXECUTE trên API cần dùng và quyền dữ liệu tối thiểu. Không cấp quyền truy vấn trực tiếp toàn bộ schema cho ứng dụng nếu API đã được thiết kế để cung cấp đúng tập dữ liệu.

Cursor trả về vẫn có thể chứa dữ liệu nhạy cảm. Hãy giới hạn cột trong SELECT, lọc theo người dùng/tenant, kiểm soát quyền và audit theo chính sách. Không cho phép client truyền tên bảng hoặc SQL tùy ý vào dynamic cursor query.

## 16. Thiết kế contract của result set

REF CURSOR linh hoạt, nhưng sự linh hoạt không nên làm API khó dự đoán. Một contract tốt cần mô tả:

| Thành phần | Điều cần định nghĩa |
| --- | --- |
| Tên procedure/function | Tên ổn định và ý nghĩa |
| Input parameters | Kiểu, NULL có nghĩa gì, giá trị hợp lệ |
| Output cursor | Số lượng cursor và thứ tự tham số |
| Column names | Tên cột ổn định, không dựa vào SELECT * |
| Column types | NUMBER, VARCHAR2, DATE, TIMESTAMP... |
| NULLability | Cột nào có thể NULL và ý nghĩa |
| Ordering | Có bảo đảm thứ tự hay không; nếu cần phải có ORDER BY |
| Volume | Ước lượng số hàng, pagination hoặc giới hạn |
| Error behavior | Exception Oracle nào có thể truyền về client |
| Versioning | Cách thay đổi schema result mà không phá caller |

Không có ORDER BY thì SQL không bảo đảm thứ tự hàng. Nếu client hiển thị hoặc xử lý theo thứ tự, procedure phải khai báo ORDER BY theo khóa có tính xác định.

## 17. Lab hoàn chỉnh: trả result set cho ứng dụng

Thực hành trong schema lab do bạn sở hữu.

### 17.1. Tạo bảng và dữ liệu

~~~sql
CREATE TABLE lab_customers (
    customer_id   NUMBER PRIMARY KEY,
    customer_name VARCHAR2(80) NOT NULL,
    status        VARCHAR2(10) NOT NULL,
    credit_limit  NUMBER(12, 2)
);

INSERT INTO lab_customers VALUES (1, 'An Nguyen', 'ACTIVE', 1200);
INSERT INTO lab_customers VALUES (2, 'Binh Tran', 'ACTIVE', 300);
INSERT INTO lab_customers VALUES (3, 'Chi Le', 'INACTIVE', 900);
INSERT INTO lab_customers VALUES (4, 'Dung Pham', 'ACTIVE', NULL);
COMMIT;
~~~

### 17.2. Tạo procedure OUT SYS_REFCURSOR

~~~sql
CREATE OR REPLACE PROCEDURE lab_get_customers (
    p_status      IN VARCHAR2,
    p_min_credit  IN NUMBER,
    p_result      OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT
            customer_id,
            customer_name,
            status,
            credit_limit
        FROM lab_customers
        WHERE status = p_status
          AND credit_limit >= p_min_credit
        ORDER BY customer_id;
END;
/
~~~

### 17.3. Gọi bằng SQL*Plus/SQLcl

~~~sql
VARIABLE rc REFCURSOR
EXEC lab_get_customers('ACTIVE', 500, :rc);
PRINT rc
~~~

Kết quả có khách hàng ACTIVE đáp ứng credit limit từ 500 trở lên. Hàng có CREDIT_LIMIT NULL không thỏa điều kiện so sánh và không xuất hiện.

### 17.4. Xử lý tham số lọc tùy chọn

Nếu NULL có nghĩa bỏ qua điều kiện tương ứng, thay query trong procedure bằng:

~~~sql
OPEN p_result FOR
    SELECT
        customer_id,
        customer_name,
        status,
        credit_limit
    FROM lab_customers
    WHERE (p_status IS NULL OR status = p_status)
      AND (p_min_credit IS NULL OR credit_limit >= p_min_credit)
    ORDER BY customer_id;
~~~

Khi p_status NULL, query không lọc status. Khi p_min_credit NULL, query không lọc credit limit. Đây là quy tắc API cụ thể; nếu cần tìm các hàng mà một cột có giá trị NULL, cần tham số/cờ riêng để phân biệt bỏ qua filter và lọc NULL.

### 17.5. Trả hai cursor

~~~sql
CREATE OR REPLACE PROCEDURE lab_customer_dashboard (
    p_customer_id IN NUMBER,
    p_profile     OUT SYS_REFCURSOR,
    p_orders      OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_profile FOR
        SELECT customer_id, customer_name, status, credit_limit
        FROM lab_customers
        WHERE customer_id = p_customer_id;

    OPEN p_orders FOR
        SELECT order_id, order_date, total_amount
        FROM lab_orders
        WHERE customer_id = p_customer_id
        ORDER BY order_date DESC;
END;
/
~~~

Đây là ví dụ minh họa cấu trúc nhiều cursor; cần tạo LAB_ORDERS với các cột tương ứng trước khi compile procedure. Ứng dụng bind cả hai OUT cursor và đọc/đóng cả hai.

## 18. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Client nhận cursor nhưng fetch lỗi | Fetch target không khớp số cột/thứ tự/kiểu | Giữ result schema rõ ràng và fetch đúng kiểu |
| SYS_REFCURSOR compile nhưng caller không biết shape | Weak cursor không khai báo row type | Tài liệu hóa select list hoặc dùng strong cursor |
| Cursor không đọc được sau khi connection đóng | Handle gắn với session/database cursor | Giữ connection mở tới khi đọc xong |
| ORA-01000 | Cursor/result set/statement không được đóng | Dùng try-with-resources hoặc using và kiểm tra leak |
| Procedure đóng cursor trước khi trả | Caller nhận handle đã đóng | Không CLOSE OUT cursor trong procedure thành công |
| SELECT INTO dùng thay REF CURSOR nhưng có nhiều hàng | SELECT INTO chỉ nhận đúng một hàng | Trả SYS_REFCURSOR hoặc dùng collection/bulk collect |
| Dynamic SQL bị SQL injection | Nối dữ liệu client vào query text | Dùng bind variables và whitelist identifier |
| Result set đổi cột làm ứng dụng lỗi | Contract không được version hóa | Giữ schema ổn định hoặc tạo API version mới |
| Kết quả trả về không có thứ tự ổn định | Query không có ORDER BY | Thêm ORDER BY với tie-breaker xác định |
| Client không phân biệt 0 và NULL | Getter primitive mặc định trả 0 | Kiểm tra wasNull() hoặc dùng kiểu nullable |
| Fetch từng hàng quá chậm | Chi phí round-trip/fetch lớn | Điều chỉnh fetch size hoặc dùng bulk fetch |
| Cursor giữ lâu và gặp ORA-01555 | Undo không còn đủ cho consistent read | Giảm thời gian mở cursor, phân trang và đánh giá undo |
| Nhiều OUT cursor nhưng chỉ đóng một | Quên giải phóng result set không dùng | Đóng mọi cursor, kể cả cursor không đọc |

## 19. Bài tập thực hành

Sử dụng LAB_CUSTOMERS trong mục 17.

### Bài 1 — Explicit cursor và REF CURSOR

Viết một block đọc danh sách khách hàng bằng explicit cursor. Viết lại bằng weak REF CURSOR. So sánh cách khai báo query và cách OPEN.

### Bài 2 — Strong và weak

Khai báo strong REF CURSOR trả về LAB_CUSTOMERS%ROWTYPE. Thử OPEN bằng SELECT * và sau đó bằng select list chỉ có hai cột. Quan sát khác biệt về kiểm tra kiểu.

### Bài 3 — SYS_REFCURSOR OUT

Tạo procedure trả danh sách khách hàng theo status và credit limit. Gọi bằng SQL*Plus/SQLcl với VARIABLE, EXEC và PRINT.

### Bài 4 — Function trả cursor

Tạo function trả SYS_REFCURSOR. Viết PL/SQL caller fetch từng hàng và đóng cursor.

### Bài 5 — Nhiều result set

Tạo procedure trả profile và danh sách giao dịch bằng hai OUT SYS_REFCURSOR. Gọi từ một client hỗ trợ hai cursor và đọc cả hai.

### Bài 6 — Dynamic SQL

Viết procedure tìm khách hàng theo NAME hoặc REGION. Dùng bind variables cho giá trị và whitelist cho sort column. Thử gửi chuỗi có dấu nháy và xác nhận nó được xử lý như dữ liệu.

### Bài 7 — Fetch bulk

Fetch REF CURSOR bằng BULK COLLECT với LIMIT 50. So sánh số vòng lặp với fetch từng hàng và giải thích vì sao giới hạn batch giúp kiểm soát PGA.

### Bài 8 — Client resource management

Viết một đoạn Java gọi procedure OUT cursor bằng CallableStatement. Dùng try-with-resources cho ResultSet và statement. Thử SQL NULL ở một cột NUMBER và kiểm tra wasNull().

## 20. Dọn dữ liệu lab

Chỉ chạy trong schema lab do bạn tạo, sau khi hoàn thành bài tập:

~~~sql
DROP PROCEDURE lab_customer_dashboard;
DROP PROCEDURE lab_get_customers;
DROP TABLE lab_customers PURGE;
~~~

Nếu đã tạo LAB_ORDERS hoặc các object khác cho bài tập, chỉ xóa đúng object thuộc schema thực hành của mình. DROP procedure trước bảng để giữ thứ tự dọn dẹp dễ hiểu. PURGE bỏ qua recycle bin; không dùng trên dữ liệu nghiệp vụ hoặc dữ liệu cần khôi phục.

## Tổng kết

REF CURSOR là cursor variable trỏ tới một result set đang mở. Strong REF CURSOR khai báo kiểu hàng bằng RETURN; weak REF CURSOR không ràng buộc row shape; SYS_REFCURSOR là weak type có sẵn của Oracle. Mở cursor bằng OPEN ... FOR, đọc bằng FETCH và giải phóng bằng CLOSE.

Để trả tập kết quả cho ứng dụng, procedure thường nhận tham số OUT SYS_REFCURSOR, mở query rồi trả handle cho caller. Client dùng driver để bind OUT parameter, fetch ResultSet/DataReader và đóng mọi tài nguyên trong khi connection vẫn mở. Có thể trả nhiều cursor, trả cursor từ function hoặc dùng implicit results trên phiên bản/client hỗ trợ. Hãy giữ result schema ổn định, bind giá trị trong dynamic SQL, giới hạn lượng dữ liệu, xử lý NULL rõ ràng và đóng cursor đúng vòng đời để tránh rò rỉ tài nguyên.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — Cursor Variables (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursor-variables.html) — REF CURSOR, strong/weak cursor variables và thao tác cursor.
- [Oracle Database PL/SQL Language Reference — OPEN FOR Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/OPEN-FOR-statement.html) — mở cursor variable cho query.
- [Oracle Database PL/SQL Language Reference — FETCH Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/FETCH-statement.html) — đọc hàng từ cursor.
- [Oracle Database PL/SQL Language Reference — Cursor Attributes (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursor-variables.html) — thuộc tính cursor.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_SQL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SQL.html) — implicit result sets và RETURN_RESULT.
- [Oracle JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — gọi stored procedure và nhận REF CURSOR trong JDBC.
- [Oracle Data Provider for .NET Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/odpnt/) — OracleRefCursor và OracleDbType.RefCursor.

Khi triển khai trên Oracle release hoặc client driver khác, hãy đối chiếu PL/SQL Language Reference và tài liệu JDBC/ODP.NET đúng phiên bản, nhất là kiểu bind REF CURSOR, implicit results và vòng đời ResultSet/DataReader.
