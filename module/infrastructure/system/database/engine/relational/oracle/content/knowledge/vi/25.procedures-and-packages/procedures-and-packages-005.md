# Package specification, package body và giao diện công khai trong PL/SQL

## 1. Package là gì và vì sao cần tách specification với body?

Trong PL/SQL, package là một schema object dùng để gom các thành phần có liên quan thành một đơn vị: procedure, function, cursor, type, exception, constant và biến. Thay vì tạo hàng chục procedure rời rạc, ta có thể nhóm chúng theo một miền nghiệp vụ như đơn hàng, khách hàng, thanh toán hoặc báo cáo.

Một package thường có hai phần:

- **Package specification:** công bố giao diện mà code bên ngoài được phép sử dụng.
- **Package body:** triển khai các procedure/function đã công bố và chứa các thành phần nội bộ chỉ package mới nhìn thấy.

Ví dụ:

~~~text
ORDER_API
  |
  +-- PACKAGE SPECIFICATION
  |      +-- approve_order(...)
  |      +-- cancel_order(...)
  |      +-- get_order_total(...)
  |
  +-- PACKAGE BODY
         +-- implementation của approve_order
         +-- implementation của cancel_order
         +-- implementation của get_order_total
         +-- validate_order_state       (private)
         +-- write_audit                (private)
         +-- package initialization
~~~

Người gọi chỉ cần biết tên package, tên routine, parameter, kiểu dữ liệu, mode và kết quả. Họ không cần biết routine đọc bao nhiêu bảng, dùng cursor nào hoặc gọi helper nội bộ nào.

Sự tách biệt này tạo ra một **public interface** ổn định. Nhóm phát triển có thể thay đổi thuật toán bên trong package body mà caller không cần sửa, miễn là hợp đồng công khai vẫn tương thích.

## 2. Package specification: hợp đồng công khai

Package specification là phần khai báo các thành phần có thể được tham chiếu từ bên ngoài package, tùy theo quyền truy cập và phạm vi visibility.

Một specification có thể công bố:

- Constant và variable ở cấp package.
- Type và subtype.
- Exception.
- Cursor specification.
- Procedure và function declaration.
- Các pragma hoặc thuộc tính được phép trong specification.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    c_status_pending  CONSTANT VARCHAR2(20) := 'PENDING';
    c_status_approved CONSTANT VARCHAR2(20) := 'APPROVED';

    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    );

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN orders.total_amount%TYPE;
END order_api;
/
~~~

Code khác trong schema có thể tham chiếu:

~~~sql
BEGIN
    order_api.approve_order(
        p_order_id => 1001,
        p_user_id  => 501
    );
END;
/
~~~

Nếu caller có quyền EXECUTE trên package, nó có thể gọi routine công khai theo các quy tắc PL/SQL. Tên routine không cần được khai báo lại trong caller.

### 2.1. Specification không phải nơi đặt thuật toán

Specification nên tập trung vào hợp đồng:

- Routine làm gì?
- Caller phải truyền tham số nào?
- Parameter là IN, OUT hay IN OUT?
- Function trả về kiểu gì?
- Có exception nghiệp vụ nào được công bố?
- Có type nào caller cần dùng để truyền/nhận dữ liệu?

Không đưa truy vấn phức tạp, vòng lặp hoặc quy trình nhiều bước vào specification. Những phần triển khai thuộc package body.

### 2.2. Chỉ công bố những gì caller cần

Nếu helper chỉ phục vụ một routine trong package, để helper ở body:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    );
END order_api;
/
~~~

Caller chỉ thấy APPROVE_ORDER. Các bước validate, ghi audit hoặc tính toán có thể là private subprogram trong body.

Một public API nhỏ thường dễ học, kiểm thử, phân quyền và giữ tương thích hơn một specification phơi bày mọi helper.

## 3. Package body: nơi triển khai và giữ thành phần private

Package body chứa phần định nghĩa thực tế cho những subprogram được khai báo trong specification. Body cũng có thể khai báo các biến, type, cursor, exception và helper chỉ sử dụng nội bộ.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE validate_order_state (
        p_order_id IN orders.order_id%TYPE
    ) IS
        l_status orders.status%TYPE;
    BEGIN
        SELECT status
        INTO l_status
        FROM orders
        WHERE order_id = p_order_id;

        IF l_status <> c_status_pending THEN
            RAISE_APPLICATION_ERROR(-20001, 'Order is not pending');
        END IF;
    END validate_order_state;

    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE,
        p_user_id  IN orders.approved_by%TYPE
    ) IS
    BEGIN
        validate_order_state(p_order_id);

        UPDATE orders
        SET status = c_status_approved,
            approved_by = p_user_id,
            approved_at = SYSTIMESTAMP
        WHERE order_id = p_order_id;
    END approve_order;

    FUNCTION get_order_total (
        p_order_id IN orders.order_id%TYPE
    ) RETURN orders.total_amount%TYPE IS
        l_total orders.total_amount%TYPE;
    BEGIN
        SELECT total_amount
        INTO l_total
        FROM orders
        WHERE order_id = p_order_id;

        RETURN l_total;
    END get_order_total;
END order_api;
/
~~~

Trong ví dụ:

- APPROVE_ORDER và GET_ORDER_TOTAL được công bố trong specification.
- VALIDATE_ORDER_STATE chỉ xuất hiện trong body, nên caller không thể gọi trực tiếp bằng ORDER_API.VALIDATE_ORDER_STATE.
- Body có thể dùng constant công khai từ specification.
- Caller không biết cách kiểm tra trạng thái hay cách đọc tổng tiền.

### 3.1. Package body là nơi đặt helper private

Private helper phù hợp với:

- Validate điều kiện đầu vào dùng chung trong package.
- Chuyển đổi hoặc chuẩn hóa dữ liệu nội bộ.
- Thực hiện một bước SQL được nhiều routine công khai dùng.
- Ghi log/audit theo một quy tắc chung.
- Tách đoạn code dài để routine công khai dễ đọc.

Không tạo helper chỉ để đổi tên một câu lệnh rất ngắn nếu nó không làm rõ trách nhiệm hoặc không có khả năng tái sử dụng.

### 3.2. Body có thể chứa biến và type riêng

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    c_max_attempts CONSTANT PLS_INTEGER := 3;

    TYPE t_validation_result IS RECORD (
        is_valid BOOLEAN,
        reason   VARCHAR2(200)
    );

    l_last_processed_order_id NUMBER;

    ...
END order_api;
/
~~~

Các khai báo này chỉ được package body sử dụng. Caller không thể tham chiếu trực tiếp tới chúng.

### 3.3. Package body có bắt buộc không?

Package cần body khi specification khai báo các subprogram cần triển khai hoặc cursor cần định nghĩa. Nếu package chỉ công bố các thành phần khai báo không cần phần triển khai, body có thể không cần thiết.

Trong thực tế, package API có procedure/function thường có body. Nếu body bị thiếu hoặc một routine công khai không được định nghĩa, package không thể hoạt động như dự kiến và sẽ có lỗi compile/invalid.

## 4. So sánh specification và body

| Nội dung | Specification | Body |
| --- | --- | --- |
| Vai trò | Công bố API | Triển khai API |
| Caller truy cập trực tiếp | Có, với quyền phù hợp | Không |
| Procedure/function | Khai báo signature | Viết implementation |
| Private helper | Không đặt ở đây | Có |
| Biến nội bộ | Không | Có |
| Constant công khai | Có thể khai báo | Có thể dùng |
| Constant riêng | Không | Có |
| SQL nghiệp vụ | Không nên đặt | Đặt ở đây |
| Package initialization | Không | Có |
| Thay đổi implementation | Không cần đổi nếu API giữ nguyên | Thường chỉ compile lại body |

Một cách nhớ:

- Specification trả lời: “Package cung cấp những gì?”
- Body trả lời: “Package thực hiện những điều đó như thế nào?”

## 5. Cú pháp đầy đủ của package

### 5.1. Package specification

~~~sql
CREATE [OR REPLACE] PACKAGE package_name
    [AUTHID {DEFINER | CURRENT_USER}]
    [ACCESSIBLE BY (...)]
AS
    -- Public declarations
END [package_name];
/
~~~

Các mệnh đề tùy chọn tùy thuộc phiên bản và tính năng sử dụng. AUTHID xác định quyền thực thi của package. ACCESSIBLE BY là cơ chế giới hạn đơn vị chương trình được phép truy cập trong những trường hợp Oracle hỗ trợ; nó không thay thế GRANT EXECUTE.

### 5.2. Package body

~~~sql
CREATE [OR REPLACE] PACKAGE BODY package_name AS
    -- Private declarations

    -- Public subprogram implementations

BEGIN
    -- Optional package initialization section
END [package_name];
/
~~~

Phần BEGIN cuối body là initialization section. Nó khác BEGIN bên trong từng procedure/function: initialization section chạy khi package được khởi tạo trong một session, theo vòng đời package state.

### 5.3. Không đặt BEGIN cuối specification

Specification chỉ khai báo giao diện, không có phần thực thi và không có initialization section. Nếu cần câu lệnh chạy khi package được khởi tạo, đặt ở cuối package body.

## 6. Khai báo routine trong specification và định nghĩa trong body

Signature trong body phải tương ứng với declaration trong specification. Tên parameter có thể được xem là một phần quan trọng của interface khi caller dùng named notation; hãy giữ nhất quán cả tên và mode.

Specification:

~~~sql
CREATE OR REPLACE PACKAGE customer_api AS
    PROCEDURE change_email (
        p_customer_id IN customers.customer_id%TYPE,
        p_new_email   IN customers.email%TYPE
    );
END customer_api;
/
~~~

Body:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    PROCEDURE change_email (
        p_customer_id IN customers.customer_id%TYPE,
        p_new_email   IN customers.email%TYPE
    ) IS
    BEGIN
        UPDATE customers
        SET email = p_new_email
        WHERE customer_id = p_customer_id;
    END change_email;
END customer_api;
/
~~~

Caller:

~~~sql
BEGIN
    customer_api.change_email(
        p_customer_id => 200,
        p_new_email   => 'new@example.com'
    );
END;
/
~~~

Named notation làm call site tự mô tả hơn và giảm rủi ro đảo vị trí khi nhiều parameter cùng kiểu dữ liệu.

### 6.1. Không khai báo public routine nhưng quên định nghĩa

Nếu specification công bố một procedure nhưng body không có implementation tương ứng, package không thể được sử dụng bình thường. Khi hoàn thiện package, cần bảo đảm mọi subprogram cần body đều có định nghĩa phù hợp.

### 6.2. Không khai báo implementation public chỉ trong body

Nếu procedure chỉ được định nghĩa trong body mà không khai báo trong specification, nó là private. Caller không thể gọi qua package name.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    PROCEDURE normalize_email (
        p_email IN VARCHAR2
    ) IS
    BEGIN
        NULL;
    END normalize_email;
END customer_api;
/
~~~

NORMALIZE_EMAIL là helper private nếu không được khai báo trong specification.

## 7. Public interface và nguyên tắc thiết kế API

Package specification là hợp đồng giữa package và caller. Khi nhiều ứng dụng phụ thuộc vào package, mỗi thay đổi specification có thể ảnh hưởng nhiều module.

Một public interface tốt nên:

- Có số routine vừa đủ cho use case thật sự.
- Dùng tên mô tả hành động hoặc kết quả.
- Có parameter rõ ràng và kiểu dữ liệu ổn định.
- Xác định rõ side effects.
- Xác định transaction ownership.
- Mô tả exception có thể phát sinh.
- Tránh phơi bày cấu trúc nội bộ không cần thiết.
- Có thể mở rộng mà không làm hỏng caller hiện tại.

### 7.1. Đừng biến package thành một bảng API

Không nên công bố procedure cho từng câu SQL nhỏ nếu caller không cần truy cập các thao tác đó. Public API nên thể hiện use case hoặc năng lực nghiệp vụ.

Ví dụ, thay vì công bố:

~~~sql
PROCEDURE update_order_status(...);
PROCEDURE update_order_user(...);
PROCEDURE update_order_timestamp(...);
~~~

có thể công bố một thao tác nghiệp vụ:

~~~sql
PROCEDURE approve_order (
    p_order_id IN orders.order_id%TYPE,
    p_user_id  IN orders.approved_by%TYPE
);
~~~

Body quyết định các cột cần cập nhật cùng nhau. Caller không phải biết các bước lưu trữ chi tiết.

### 7.2. Công bố kiểu dữ liệu khi caller cần dùng

Nếu caller cần truyền/nhận collection hoặc record, package có thể công bố type:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    TYPE t_order_id_list IS TABLE OF orders.order_id%TYPE;

    PROCEDURE close_orders (
        p_order_ids IN t_order_id_list
    );
END order_api;
/
~~~

Caller có thể dùng type thông qua tên package:

~~~sql
DECLARE
    l_order_ids order_api.t_order_id_list :=
        order_api.t_order_id_list(100, 101, 102);
BEGIN
    order_api.close_orders(l_order_ids);
END;
/
~~~

Nếu type chỉ cần dùng bên trong body, hãy khai báo ở body để không mở rộng API không cần thiết.

### 7.3. Công bố exception nghiệp vụ

Package có thể công bố exception để caller bắt theo tên:

~~~sql
CREATE OR REPLACE PACKAGE payment_api AS
    e_payment_declined EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_payment_declined, -20071);

    PROCEDURE charge (...);
END payment_api;
/
~~~

Caller:

~~~sql
BEGIN
    payment_api.charge(...);
EXCEPTION
    WHEN payment_api.e_payment_declined THEN
        -- Xử lý từ chối thanh toán
        NULL;
END;
/
~~~

Với API công khai, mã lỗi và ý nghĩa exception cần ổn định. Nếu thay đổi mã hoặc tên exception, caller phụ thuộc có thể phải sửa.

## 8. Parameter modes, default values và named notation

### 8.1. IN

IN truyền dữ liệu vào routine. Đây là mode mặc định:

~~~sql
PROCEDURE find_order (
    p_order_id IN orders.order_id%TYPE
);
~~~

Không nên thay đổi parameter IN trong routine để caller dựa vào thay đổi đó; hãy dùng OUT hoặc IN OUT khi hợp đồng yêu cầu trả dữ liệu.

### 8.2. OUT

OUT trả dữ liệu cho caller:

~~~sql
PROCEDURE get_order_summary (
    p_order_id IN  orders.order_id%TYPE,
    p_total    OUT orders.total_amount%TYPE,
    p_status   OUT orders.status%TYPE
);
~~~

OUT phù hợp khi routine cần trả nhiều giá trị. Nếu kết quả là một giá trị đơn, function có thể dễ sử dụng hơn. Với OUT parameter, caller nên xem giá trị đầu ra chỉ đáng tin khi routine hoàn tất thành công theo hợp đồng.

### 8.3. IN OUT

IN OUT nhận giá trị ban đầu và trả giá trị sau xử lý:

~~~sql
PROCEDURE normalize_code (
    p_code IN OUT VARCHAR2
);
~~~

IN OUT có thể hữu ích cho một số API biến đổi dữ liệu, nhưng làm call site ít rõ hơn so với input/output tách biệt. Dùng khi semantics thực sự là “đưa giá trị vào rồi nhận lại giá trị đã biến đổi”.

### 8.4. Default parameter

Có thể khai báo default:

~~~sql
PROCEDURE search_orders (
    p_status IN orders.status%TYPE DEFAULT 'OPEN',
    p_limit  IN PLS_INTEGER DEFAULT 100
);
~~~

Caller có thể bỏ qua parameter có default:

~~~sql
BEGIN
    order_api.search_orders;
END;
/
~~~

Hoặc truyền named notation:

~~~sql
BEGIN
    order_api.search_orders(
        p_limit => 50
    );
END;
/
~~~

Default giúp API tiện dùng, nhưng thay đổi default có thể thay đổi hành vi của caller hiện có mà không cần sửa source code của caller. Hãy xem default là một phần của contract.

### 8.5. Thứ tự parameter và compatibility

Với positional notation, thứ tự parameter là quan trọng:

~~~sql
order_api.create_order(100, 'OPEN', 500);
~~~

Nếu thêm parameter vào giữa danh sách, caller positional có thể bị lỗi hoặc truyền sai ý nghĩa. Named notation giảm rủi ro:

~~~sql
order_api.create_order(
    p_customer_id => 100,
    p_status      => 'OPEN',
    p_amount      => 500
);
~~~

Khi thiết kế package dùng rộng rãi, ưu tiên named notation trong code nội bộ và cân nhắc thêm parameter ở cuối với default khi cần mở rộng API tương thích.

## 9. Overloading trong package

PL/SQL cho phép nhiều subprogram cùng tên nếu signature phân biệt được theo quy tắc overload.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE report_api AS
    PROCEDURE print_summary (
        p_department_id IN NUMBER
    );

    PROCEDURE print_summary (
        p_department_code IN VARCHAR2
    );
END report_api;
/
~~~

Caller:

~~~sql
BEGIN
    report_api.print_summary(p_department_id => 10);
    report_api.print_summary(p_department_code => 'SALES');
END;
/
~~~

### 9.1. Khi nào overload hữu ích?

- Cùng một hành động hỗ trợ nhiều kiểu dữ liệu đầu vào.
- Cùng một API có phiên bản nhận record hoặc scalar.
- Caller có thể chọn cách truyền dữ liệu tự nhiên theo use case.

### 9.2. Khi nào overload gây mơ hồ?

Nếu các overload chỉ khác nhau ở kiểu dữ liệu dễ chuyển đổi ngầm, literal NULL hoặc positional call có thể khiến việc phân giải không rõ ràng.

Ví dụ:

~~~sql
report_api.print_summary(NULL);
~~~

Oracle có thể không xác định được overload mong muốn nếu nhiều signature phù hợp. Dùng biến có kiểu rõ ràng hoặc named notation, hoặc đổi tên routine nếu hai hành vi khác nhau về ý nghĩa.

### 9.3. Những signature không thể overload tùy ý

Không thể phân biệt overload chỉ bằng return type của function. Hai function cùng tên, cùng parameter types nhưng khác kiểu trả về không tạo được overload hợp lệ.

Các khác biệt về parameter mode hoặc tên parameter không phải lúc nào cũng đủ để tạo overload riêng. Hãy tuân theo quy tắc overload của PL/SQL và tránh thiết kế API phụ thuộc vào sự khác biệt quá nhỏ.

## 10. Thành phần public và private: phạm vi truy cập

### 10.1. Public

Thành phần khai báo trong specification là public đối với người có thể truy cập package:

~~~sql
CREATE OR REPLACE PACKAGE customer_api AS
    c_active_status CONSTANT VARCHAR2(20) := 'ACTIVE';

    PROCEDURE activate_customer (
        p_customer_id IN customers.customer_id%TYPE
    );
END customer_api;
/
~~~

Caller có thể dùng:

~~~sql
BEGIN
    customer_api.activate_customer(100);
END;
/
~~~

Caller cũng có thể tham chiếu constant public nếu có quyền phù hợp:

~~~sql
IF l_status = customer_api.c_active_status THEN
    ...
END IF;
~~~

### 10.2. Private

Thành phần chỉ khai báo trong body là private:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    c_inactive_status CONSTANT VARCHAR2(20) := 'INACTIVE';

    PROCEDURE validate_customer (
        p_customer_id IN customers.customer_id%TYPE
    ) IS
    BEGIN
        ...
    END validate_customer;

    PROCEDURE activate_customer (
        p_customer_id IN customers.customer_id%TYPE
    ) IS
    BEGIN
        validate_customer(p_customer_id);
        ...
    END activate_customer;
END customer_api;
/
~~~

Caller không thể gọi CUSTOMER_API.VALIDATE_CUSTOMER hoặc đọc CUSTOMER_API.C_INACTIVE_STATUS.

### 10.3. Không thể truy cập private helper từ package khác

Nếu package khác cần dùng cùng logic, có ba lựa chọn:

- Đưa routine thành public API nếu đó thực sự là năng lực dùng chung.
- Đưa logic vào một package service chung có interface được thiết kế rõ.
- Tạo một schema-level routine riêng nếu đó là API độc lập.

Không tìm cách truy cập private routine bằng dynamic SQL hoặc thủ thuật phụ thuộc implementation.

## 11. Package initialization và package state

### 11.1. Initialization section

Package body có thể có phần BEGIN cuối cùng:

~~~sql
CREATE OR REPLACE PACKAGE session_context_api AS
    FUNCTION get_start_time RETURN TIMESTAMP;
END session_context_api;
/

CREATE OR REPLACE PACKAGE BODY session_context_api AS
    g_start_time TIMESTAMP;

    FUNCTION get_start_time RETURN TIMESTAMP IS
    BEGIN
        RETURN g_start_time;
    END get_start_time;

BEGIN
    g_start_time := SYSTIMESTAMP;
END session_context_api;
/
~~~

Initialization section chạy khi package được khởi tạo trong session. Nó thường được thực thi một lần cho mỗi instance package state của session, sau khi package được load/instantiate.

### 11.2. Package state sống theo session

Biến package không phải biến toàn cục dùng chung cho mọi session. Mỗi database session có package state riêng:

~~~text
Session A                     Session B
---------                     ---------
ORDER_API.g_count = 2         ORDER_API.g_count = 0
ORDER_API.g_mode = 'BATCH'    ORDER_API.g_mode = 'ONLINE'
~~~

Hai session không chia sẻ cùng giá trị package variable. Đây là điểm quan trọng khi ứng dụng dùng connection pool: nhiều request khác nhau có thể lần lượt sử dụng cùng một database session và nhìn thấy package state còn sót lại.

### 11.3. Rủi ro state tồn tại lâu

Nếu package giữ:

- Customer ID của request trước.
- Cờ debug đã bật.
- Danh sách quyền đã cache.
- Giá trị filter hoặc tenant context.

thì request sau dùng lại session có thể bị ảnh hưởng nếu state không reset đúng cách.

Ưu tiên parameter và dữ liệu có phạm vi rõ ràng. Nếu package state là chủ ý, phải có API reset/init và kiểm tra cách connection pool trả session về pool.

### 11.4. Package initialization không phải nơi làm công việc nặng

Tránh chạy query lớn, cập nhật dữ liệu hoặc gọi dịch vụ ngoài trong initialization section. Việc khởi tạo package xảy ra khi session lần đầu chạm package; nó có thể làm request đầu tiên chậm hoặc thất bại do phụ thuộc bên ngoài.

Initialization section nên ngắn, xác định và ít side effect. Nếu cần tải dữ liệu cấu hình, cân nhắc routine init tường minh có xử lý lỗi và cache policy.

### 11.5. Package state bị invalidation

Khi package hoặc dependency bị recompile/invalidate, session đang dùng package có thể gặp lỗi như ORA-04068 báo package state đã bị discarded. Ứng dụng có thể cần xử lý retry ở ranh giới request phù hợp, nhưng phải bảo đảm thao tác nghiệp vụ có thể retry an toàn.

Không retry mù một transaction đã thực hiện side effect hoặc đã commit một phần. Phải thiết kế idempotency và transaction boundary.

## 12. PRAGMA SERIALLY_REUSABLE

Package state thông thường tồn tại trong session. Oracle có cơ chế SERIALLY_REUSABLE để dùng package state theo từng server call thay vì giữ state xuyên suốt session như package thông thường.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE batch_scratch
IS
    PRAGMA SERIALLY_REUSABLE;
    g_counter PLS_INTEGER := 0;
    PROCEDURE increment_counter;
END batch_scratch;
/

CREATE OR REPLACE PACKAGE BODY batch_scratch
IS
    PRAGMA SERIALLY_REUSABLE;

    PROCEDURE increment_counter IS
    BEGIN
        g_counter := g_counter + 1;
    END increment_counter;
END batch_scratch;
/
~~~

SERIALLY_REUSABLE thay đổi vòng đời state và cách package được khởi tạo/tái sử dụng. Nó không phải mẹo chung để sửa mọi lỗi connection pool; caller không được dựa vào package state tồn tại qua các server call.

Package specification và body phải khai báo pragma tương ứng theo yêu cầu Oracle. Cũng cần xem các giới hạn khi package được gọi từ SQL hoặc kết hợp với các cấu trúc khác. Dùng khi đã hiểu rõ semantics và đo lường được lợi ích bộ nhớ.

## 13. AUTHID: quyền thực thi của package

Package có thể chạy theo definer's rights hoặc invoker's rights.

### 13.1. AUTHID DEFINER

Đây là mặc định nếu không chỉ định AUTHID. Code chạy với quyền của owner/definer theo quy tắc definer's rights.

~~~sql
CREATE OR REPLACE PACKAGE payroll_api
AUTHID DEFINER
AS
    PROCEDURE calculate_payroll;
END payroll_api;
/
~~~

Definer's rights hữu ích khi package cung cấp một API có kiểm soát tới dữ liệu mà caller không trực tiếp có quyền truy cập. Owner cần được cấp trực tiếp các privilege cần thiết cho stored code theo quy tắc Oracle.

### 13.2. AUTHID CURRENT_USER

Invoker's rights làm thay đổi privilege context theo người gọi:

~~~sql
CREATE OR REPLACE PACKAGE reporting_api
AUTHID CURRENT_USER
AS
    PROCEDURE show_accessible_orders;
END reporting_api;
/
~~~

Package chạy theo quyền của invoker trong các ngữ cảnh Oracle quy định. Điều này hữu ích khi cùng một logic cần áp dụng quyền của từng caller.

### 13.3. AUTHID là một phần của interface

AUTHID được khai báo ở package specification và ảnh hưởng cách package hoạt động. Đổi từ DEFINER sang CURRENT_USER có thể thay đổi quyền truy cập object, tên được phân giải, hành vi dynamic SQL và khả năng chạy của caller.

Không thay đổi AUTHID chỉ để xử lý lỗi ORA-01031 mà chưa phân tích security model. Đây là quyết định bảo mật và tương thích.

### 13.4. Definer's rights không có nghĩa caller có quyền DBA

Package definer's rights chỉ sử dụng quyền của owner theo quy tắc stored PL/SQL; nó không tự cấp toàn bộ quyền của owner cho caller ngoài phạm vi thực thi package. Thiết kế API vẫn phải giới hạn operation và validate input để tránh biến package thành privilege escalation path.

### 13.5. Quyền qua role và direct grants

Stored PL/SQL definer-rights thường cần object/system privileges được cấp trực tiếp cho owner thay vì chỉ có qua role, theo quy tắc privilege resolution của Oracle. Hãy kiểm tra grants và compile errors khi package tham chiếu object khác schema.

## 14. EXECUTE privilege và phạm vi sử dụng package

Package không tự động công khai cho mọi user. Owner có thể cấp EXECUTE:

~~~sql
GRANT EXECUTE ON order_api TO app_user;
~~~

Caller sau đó có thể:

~~~sql
BEGIN
    owner_name.order_api.approve_order(
        p_order_id => 1001,
        p_user_id  => 501
    );
END;
/
~~~

DBA hoặc owner có thể thu hồi:

~~~sql
REVOKE EXECUTE ON order_api FROM app_user;
~~~

### 14.1. EXECUTE trên package khác với quyền trực tiếp trên bảng

Nếu package dùng definer's rights, caller có thể thực hiện các thao tác được package cho phép mà không cần được cấp trực tiếp mọi object privilege trên bảng bên dưới, theo mô hình definer-rights và quyền cần thiết.

Điều này khiến public API trở thành ranh giới bảo mật. Không công bố procedure có thể sửa tùy ý dữ liệu hoặc nhận identifier tùy ý mà không validation.

### 14.2. PUBLIC grant

Có thể GRANT EXECUTE cho PUBLIC, nhưng điều đó làm mọi user có khả năng gọi package nếu các điều kiện khác đáp ứng:

~~~sql
GRANT EXECUTE ON utility_api TO PUBLIC;
~~~

Chỉ dùng khi package thật sự là API chung và đã đánh giá nội dung, quyền definer và rủi ro. Không grant PUBLIC chỉ để tránh quản lý quyền theo role/user.

## 15. Dependency và tác động khi thay đổi specification

### 15.1. Caller phụ thuộc specification

Một package khác hoặc stored procedure gọi ORDER_API.APPROVE_ORDER phụ thuộc vào specification của ORDER_API.

Nếu chỉ thay đổi package body nhưng giữ specification tương thích, dependency của caller thường không cần thay đổi theo cách như khi thay public signature.

Nếu thay đổi specification, Oracle có thể invalidate các dependent objects và cần compile lại. Ứng dụng có thể gặp lỗi khi object chưa được recompile hoặc khi interface mới không tương thích.

### 15.2. Thay đổi body thường ít ảnh hưởng hơn

Ví dụ, đổi cách tính tổng tiền bên trong GET_ORDER_TOTAL nhưng giữ nguyên:

- Tên routine.
- Parameter list.
- Parameter modes.
- Return type.
- Các kiểu public phụ thuộc.

Caller vẫn dùng cùng cách gọi.

### 15.3. Thay đổi specification cần quản lý version

Các thay đổi có thể phá vỡ caller:

- Đổi tên public procedure/function.
- Xóa parameter.
- Đổi kiểu dữ liệu hoặc mode.
- Đổi return type.
- Đổi public type/record/collection.
- Đổi tên parameter khi caller dùng named notation.
- Đổi default làm thay đổi hành vi.
- Thay đổi AUTHID.

Trước khi thay đổi, tìm dependent objects và các ứng dụng gọi package. Có thể thêm overload mới hoặc routine mới thay vì sửa signature cũ ngay lập tức.

### 15.4. Xem dependency và status

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE referenced_name = 'ORDER_API'
ORDER BY name, type;
~~~

Kiểm tra object invalid:

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE status = 'INVALID'
ORDER BY object_type, object_name;
~~~

Với quyền DBA, có thể dùng DBA_DEPENDENCIES và DBA_OBJECTS để xem rộng hơn.

## 16. Compile, replace và quản lý source

### 16.1. Tạo hoặc thay thế specification

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE
    );
END order_api;
/
~~~

CREATE OR REPLACE thay definition hiện có. Thay đổi specification có thể ảnh hưởng dependent objects; không coi nó như cập nhật body thông thường.

### 16.2. Thay package body

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE approve_order (
        p_order_id IN orders.order_id%TYPE
    ) IS
    BEGIN
        UPDATE orders
        SET status = 'APPROVED'
        WHERE order_id = p_order_id;
    END approve_order;
END order_api;
/
~~~

Nếu specification không đổi, chỉ thay body thường giúp giữ API ổn định hơn.

### 16.3. Xem lỗi compile

~~~sql
SHOW ERRORS PACKAGE order_api;
SHOW ERRORS PACKAGE BODY order_api;
~~~

Hoặc:

~~~sql
SELECT type, line, position, text
FROM user_errors
WHERE name = 'ORDER_API'
ORDER BY type, sequence;
~~~

### 16.4. Xem trạng thái package

~~~sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_name = 'ORDER_API'
  AND object_type IN ('PACKAGE', 'PACKAGE BODY');
~~~

Package specification và package body là hai dictionary objects riêng. Cả hai cần ở trạng thái hợp lệ để package hoạt động bình thường.

### 16.5. Recompile

~~~sql
ALTER PACKAGE order_api COMPILE;
ALTER PACKAGE order_api COMPILE BODY;
~~~

Recompile không sửa lỗi logic. Nếu dependency hoặc source không hợp lệ, cần đọc USER_ERRORS và sửa nguyên nhân.

## 17. Xóa package và thay đổi API

Xóa package:

~~~sql
DROP PACKAGE order_api;
~~~

Lệnh DROP PACKAGE xóa package specification và body. Nó không phải cách chỉ xóa body. Nếu muốn bỏ implementation mà giữ API, không dùng DROP PACKAGE; thay body hoặc xử lý theo yêu cầu triển khai.

Có thể xóa riêng body:

~~~sql
DROP PACKAGE BODY order_api;
~~~

Specification còn lại nhưng package có thể không hoạt động nếu các public subprogram cần body không còn implementation. Chỉ dùng khi có chủ đích quản trị hoặc triển khai.

Không xóa package dùng chung trước khi kiểm tra dependencies, grants, jobs và ứng dụng gọi nó.

## 18. Package và bảo mật dữ liệu

Package có thể làm lớp API để kiểm soát truy cập:

~~~text
Application User
      |
      | EXECUTE
      v
ORDER_API (definer rights)
      |
      +-- validate order ID
      +-- validate state
      +-- update allowed columns
      +-- write audit
      |
      v
ORDERS / ORDER_AUDIT
~~~

Caller có thể không có quyền UPDATE trực tiếp trên ORDERS nhưng được cấp EXECUTE trên ORDER_API. Package chỉ cung cấp các thao tác được cho phép.

Để ranh giới này an toàn:

- Validate mọi input.
- Không nối input vào dynamic SQL không kiểm soát.
- Không nhận tên bảng tùy ý rồi thực thi với quyền definer.
- Không công bố helper nguy hiểm không cần thiết.
- Không trả dữ liệu nhạy cảm vượt quá nhu cầu.
- Ghi audit theo chính sách.
- Review AUTHID và direct grants.

Package definer-rights với API quá rộng có thể tạo đường nâng quyền. Thiết kế public interface là một phần của security design.

## 19. Kiểm thử package

Package specification và body nên được kiểm thử qua public API, vì đó là cách caller sử dụng thật.

### 19.1. Kiểm thử success path

- Gọi routine với dữ liệu hợp lệ.
- Xác nhận row thay đổi đúng.
- Xác nhận giá trị trả về.
- Kiểm tra transaction có được giữ cho caller commit hay không.

### 19.2. Kiểm thử failure path

- Input NULL hoặc ngoài miền hợp lệ.
- Không tìm thấy row.
- Vi phạm unique constraint.
- Trạng thái nghiệp vụ không hợp lệ.
- Thiếu quyền hoặc dependency không sẵn sàng.
- Lỗi khi gọi helper private.

### 19.3. Kiểm thử API compatibility

Khi thay package specification:

- Compile caller phụ thuộc.
- Kiểm tra positional và named notation.
- Kiểm tra overload resolution.
- Kiểm tra default parameter.
- Kiểm tra public types và exception.
- Kiểm tra grants EXECUTE.

### 19.4. Kiểm thử state theo session

Nếu package có package variable:

1. Mở session A và gọi routine thay đổi state.
2. Mở session B và đọc state.
3. Xác nhận state không bị chia sẻ giữa hai session.
4. Gọi nhiều request trên cùng session/connection pool.
5. Kiểm tra state có được reset đúng không.

### 19.5. Dùng test framework

Có thể dùng utPLSQL hoặc framework test PL/SQL của dự án để kiểm thử procedure/function, setup/teardown dữ liệu và kiểm tra exception. Test phải gọi public interface giống ứng dụng; helper private chỉ nên được kiểm tra gián tiếp qua hành vi công khai trừ khi có chiến lược test riêng.

## 20. Ví dụ hoàn chỉnh: API khách hàng với public và private routines

Ví dụ này minh họa package có một public procedure, một public function, constant công khai và helper private.

### 20.1. Giả định bảng

~~~sql
CREATE TABLE customers_pkg_lab (
    customer_id NUMBER PRIMARY KEY,
    email       VARCHAR2(320 CHAR) NOT NULL,
    status      VARCHAR2(20 CHAR) NOT NULL,
    updated_at  TIMESTAMP
);
~~~

### 20.2. Package specification

~~~sql
CREATE OR REPLACE PACKAGE customer_api_lab AS
    c_status_active CONSTANT VARCHAR2(20) := 'ACTIVE';

    PROCEDURE activate_customer (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    );

    FUNCTION is_active (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    ) RETURN BOOLEAN;
END customer_api_lab;
/
~~~

### 20.3. Package body

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api_lab AS
    PROCEDURE ensure_customer_exists (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    ) IS
        l_count PLS_INTEGER;
    BEGIN
        SELECT COUNT(*)
        INTO l_count
        FROM customers_pkg_lab
        WHERE customer_id = p_customer_id;

        IF l_count = 0 THEN
            RAISE_APPLICATION_ERROR(-20080, 'Customer not found');
        END IF;
    END ensure_customer_exists;

    PROCEDURE activate_customer (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    ) IS
    BEGIN
        ensure_customer_exists(p_customer_id);

        UPDATE customers_pkg_lab
        SET status = c_status_active,
            updated_at = SYSTIMESTAMP
        WHERE customer_id = p_customer_id;
    END activate_customer;

    FUNCTION is_active (
        p_customer_id IN customers_pkg_lab.customer_id%TYPE
    ) RETURN BOOLEAN IS
        l_status customers_pkg_lab.status%TYPE;
    BEGIN
        SELECT status
        INTO l_status
        FROM customers_pkg_lab
        WHERE customer_id = p_customer_id;

        RETURN l_status = c_status_active;
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RETURN FALSE;
    END is_active;
END customer_api_lab;
/
~~~

### 20.4. Gọi public API

~~~sql
BEGIN
    customer_api_lab.activate_customer(100);
    COMMIT;
END;
/
~~~

PL/SQL BOOLEAN không phải kiểu SQL scalar có thể được chọn trực tiếp trong SQL thông thường ở Oracle 19c. Vì vậy function IS_ACTIVE trả BOOLEAN phù hợp với caller PL/SQL:

~~~sql
DECLARE
    l_active BOOLEAN;
BEGIN
    l_active := customer_api_lab.is_active(100);

    IF l_active THEN
        DBMS_OUTPUT.PUT_LINE('Active');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not active');
    END IF;
END;
/
~~~

Nếu cần gọi từ SQL hoặc JDBC theo kiểu scalar, hãy công bố một function trả NUMBER/CHAR theo quy ước rõ ràng thay vì BOOLEAN trong môi trường Oracle 19c.

### 20.5. Helper private không gọi trực tiếp được

Lệnh sau không hợp lệ vì ENSURE_CUSTOMER_EXISTS chỉ có trong body:

~~~sql
BEGIN
    customer_api_lab.ensure_customer_exists(100);
END;
/
~~~

Đây là chủ đích: caller chỉ dùng các thao tác được package công bố.

## 21. Các lỗi và tình huống thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| PLS-00302: component must be declared | Caller gọi routine/variable không có trong specification hoặc sai tên | Kiểm tra public declarations và package qualifier |
| PLS-00323 | Subprogram được khai báo trong specification nhưng body không định nghĩa đúng | Đối chiếu signature trong spec và body |
| ORA-04063 | Package có lỗi hoặc invalid | Xem USER_ERRORS, compile lại sau khi sửa |
| ORA-04068 | Existing state of packages has been discarded | Package/dependency bị recompile hoặc invalidation; xử lý session/retry an toàn |
| ORA-06508 | Program unit không tìm thấy/không hợp lệ khi gọi | Kiểm tra object status và dependency |
| ORA-06550 | Lỗi compile/parse trong PL/SQL block hoặc call | Xem PLS-xxxxx đi kèm và USER_ERRORS |
| ORA-01031 | Thiếu privilege cần thiết | Kiểm tra AUTHID, direct grants, EXECUTE và object privilege |
| Caller không thấy helper | Helper chỉ khai báo trong body | Đưa vào spec chỉ khi muốn công khai API |
| Thay body làm caller không compile | Có thể spec/dependency cũng đã đổi hoặc object invalid | So sánh signature và compile dependencies |
| State từ request trước còn lại | Package variable sống theo session | Reset state, dùng parameter hoặc thiết kế lại |
| Overload call mơ hồ | Signature gần nhau hoặc literal NULL | Dùng kiểu rõ, named notation hoặc tên routine khác |
| Caller mất quyền sau deploy | GRANT bị thay đổi hoặc object được tạo lại theo quy trình khác | Kiểm tra grants sau deployment |

## 22. Checklist thiết kế package API

1. **Package có cohesion không?** Các routine có cùng miền nghiệp vụ và lý do thay đổi không?
2. **Specification chỉ công bố phần cần thiết chưa?** Giữ helper nội bộ trong body.
3. **Signature có rõ không?** Tên, kiểu, mode và default parameter cần được tài liệu hóa.
4. **Caller có thể dùng named notation không?** Giữ tên parameter ổn định.
5. **Overload có dễ phân giải không?** Tránh signature mơ hồ với NULL hoặc implicit conversion.
6. **Public type/exception có cần thiết không?** Đừng phơi bày type nội bộ.
7. **Transaction ownership rõ chưa?** Nêu package có COMMIT hay để caller quản lý.
8. **AUTHID đã đúng chưa?** Xem xét definer/invoker rights như quyết định bảo mật.
9. **EXECUTE grants đúng đối tượng chưa?** Tránh PUBLIC grant nếu không cần.
10. **Package state có cần không?** Nếu có, định nghĩa vòng đời và reset.
11. **Initialization section có side effect không?** Giữ ngắn và xác định.
12. **Dependency có được kiểm tra không?** Tìm caller trước khi đổi specification.
13. **Body có compile sạch không?** Kiểm tra USER_ERRORS và object status.
14. **Có test success/failure và API compatibility không?** Test theo cách caller thực sự sử dụng.
15. **Deployment có giữ grants và source version không?** Kiểm tra sau khi replace/compile.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Package specification và package body khác nhau ở nhiệm vụ nào?

**Câu 2.** Những thành phần nào thường được khai báo trong specification?

**Câu 3.** Private helper được khai báo ở đâu?

**Câu 4.** Caller có gọi trực tiếp procedure chỉ định nghĩa trong body không?

**Câu 5.** Khi nào package body có thể không cần thiết?

**Câu 6.** Vì sao specification được xem là public contract?

**Câu 7.** Thay body nhưng giữ signature có thường ít ảnh hưởng caller hơn thay specification không?

**Câu 8.** IN, OUT và IN OUT có vai trò gì trong public interface?

**Câu 9.** Default parameter có thể thay đổi hành vi caller hiện có như thế nào?

**Câu 10.** Overload chỉ khác return type có hợp lệ không?

**Câu 11.** Package initialization section nằm ở đâu và chạy khi nào?

**Câu 12.** Package variable có được chia sẻ giữa mọi database session không?

**Câu 13.** Vì sao package state cần được kiểm soát khi dùng connection pool?

**Câu 14.** AUTHID DEFINER khác AUTHID CURRENT_USER như thế nào?

**Câu 15.** EXECUTE trên package có đồng nghĩa caller được UPDATE trực tiếp bảng bên dưới không?

**Câu 16.** Vì sao đổi specification có thể invalidate dependent objects?

**Câu 17.** ORA-04068 thường liên quan tới điều gì?

**Câu 18.** Vì sao public interface là một phần của security design?

<details>
<summary>Gợi ý đáp án</summary>

1. Specification công bố interface; body triển khai và giữ helper private.
2. Public subprogram declarations, types, constants, variables, exceptions và cursor declarations mà caller cần dùng.
3. Trong package body, không khai báo trong specification.
4. Không. Routine không được công bố là private.
5. Khi package chỉ có declarations không cần implementation body; package có subprogram cần triển khai thì cần body.
6. Vì caller compile và sử dụng theo các tên, kiểu, mode và semantics được công bố.
7. Có. Nếu public contract không đổi, caller thường không cần sửa call site.
8. IN nhận input, OUT trả output, IN OUT nhận và trả giá trị.
9. Caller bỏ qua parameter có thể nhận hành vi mới khi default thay đổi mà không sửa source.
10. Không. Return type riêng không đủ để overload hai function có cùng parameter signature.
11. Ở cuối package body; chạy khi package được khởi tạo trong session.
12. Không. Mỗi session có package state riêng.
13. Vì request sau có thể dùng lại session và nhìn thấy state từ request trước.
14. DEFINER dùng quyền của owner theo quy tắc Oracle; CURRENT_USER dùng privilege context của invoker.
15. Không. EXECUTE cho phép gọi package; quyền trực tiếp trên bảng là một vấn đề riêng.
16. Vì caller phụ thuộc signature/type công khai và cần kiểm tra lại khi contract đổi.
17. Package state của session hiện tại đã bị discard do package/dependency invalidation hoặc recompile.
18. Vì package có thể thực thi với quyền definer và expose dữ liệu/thao tác cho caller; API cần giới hạn và validate.

</details>

## 24. Tài liệu Oracle chính thức

1. [Oracle Database 19c PL/SQL Language Reference — PL/SQL Packages](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-packages.html): cấu trúc package, specification, body, public/private declarations và package state.
2. [Oracle Database 19c PL/SQL Language Reference — Package Specification](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/package-specification.html): cú pháp và thành phần công khai.
3. [Oracle Database 19c PL/SQL Language Reference — Package Body](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/package-body.html): implementation, private declarations và initialization section.
4. [Oracle Database 19c PL/SQL Language Reference — Package State](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/package-state.html): package state, session lifetime và invalidation.
5. [Oracle Database 19c PL/SQL Language Reference — Invoker's Rights and Definer's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html): AUTHID và privilege context.
6. [Oracle Database 19c PL/SQL Language Reference — Overloaded Subprograms](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/overloaded-subprograms.html): quy tắc overload và phân giải lời gọi.
7. [Oracle Database 19c SQL Language Reference — CREATE PACKAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-PACKAGE.html): tạo package specification và package body.
8. [Oracle Database 19c SQL Language Reference — ALTER PACKAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-PACKAGE.html): compile và quản lý package.
9. [Oracle Database 19c SQL Language Reference — DROP PACKAGE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DROP-PACKAGE.html): xóa package.
10. [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_SESSION](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SESSION.html): reset package state và quản lý session.
11. [Oracle Database 19c Database Error Messages — ORA-04068](https://docs.oracle.com/en/error-help/db/ora-04068/): package state đã bị discard.
12. [Oracle Database 19c Database Error Messages — ORA-06508](https://docs.oracle.com/en/error-help/db/ora-06508/): program unit không tìm thấy hoặc không hợp lệ.

**Nguyên tắc cần nhớ:** Specification là hợp đồng công khai, body là nơi triển khai và giữ helper private. Giữ API nhỏ, signature rõ và transaction ownership minh bạch; thay body khi cần đổi implementation, chỉ đổi specification khi thật sự cần thay hợp đồng. Package state tồn tại theo session, AUTHID quyết định privilege context và EXECUTE grant quyết định ai được gọi API. Mỗi thay đổi specification cần được đánh giá dependency, compatibility, grants và test trước khi triển khai.
