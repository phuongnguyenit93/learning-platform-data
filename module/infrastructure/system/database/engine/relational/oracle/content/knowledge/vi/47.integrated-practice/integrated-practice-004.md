# Xây dựng package nghiệp vụ với hợp đồng tham số và xử lý lỗi

Oracle PL/SQL package có thể đóng vai trò API nghiệp vụ ở tầng database. Package gom các procedure, function, type, constant và exception có liên quan vào một đơn vị có tên. Khi Spring Boot hoặc một hệ thống khác gọi package, package specification là hợp đồng công khai: nó định nghĩa routine nào được gọi, tham số có ý nghĩa gì, kiểu dữ liệu nào được trao đổi và lỗi nào có thể phát sinh.

Một package tốt cung cấp cho caller một giao diện nhỏ, ổn định và có thể dự đoán. Caller không cần biết routine đọc những bảng nào, dùng sequence nào hoặc chia logic thành bao nhiêu câu SQL. Để đạt được điều đó, cần thiết kế rõ bốn phần:

- **Hợp đồng tham số**: tên, kiểu, hướng IN/OUT/IN OUT, giá trị mặc định, ý nghĩa NULL, đơn vị đo và quy tắc tương thích.
- **Hành vi nghiệp vụ**: điều kiện đầu vào, trạng thái hợp lệ, side effect và kết quả routine bảo đảm.
- **Hợp đồng lỗi**: mã lỗi, exception, điều kiện phát sinh, thông điệp và cách client xử lý.
- **Ranh giới transaction và quyền**: ai commit/rollback, routine khóa dữ liệu nào, package chạy với quyền definer hay invoker.

Bài học xây dựng một package quản lý đơn hàng làm ví dụ. Trọng tâm là thiết kế API ổn định để PL/SQL caller và Java/JDBC caller sử dụng nhất quán.

## 1. Package là API nghiệp vụ của database

Một package có hai phần:

- **Package specification**: khai báo thành phần công khai. Caller nhìn thấy routine, type, constant và exception được khai báo ở đây.
- **Package body**: triển khai logic. Body có thể chứa private procedure/function và trạng thái nội bộ không được expose ra ngoài.

Ví dụ:

    CREATE OR REPLACE PACKAGE customer_api AS
      PROCEDURE activate_customer(
        p_customer_id IN NUMBER
      );

      FUNCTION is_active(
        p_customer_id IN NUMBER
      ) RETURN BOOLEAN;
    END customer_api;
    /

    CREATE OR REPLACE PACKAGE BODY customer_api AS
      PROCEDURE activate_customer(
        p_customer_id IN NUMBER
      ) IS
      BEGIN
        UPDATE customer
        SET active_flag = 'Y'
        WHERE customer_id = p_customer_id;
      END activate_customer;

      FUNCTION is_active(
        p_customer_id IN NUMBER
      ) RETURN BOOLEAN IS
        l_flag customer.active_flag%TYPE;
      BEGIN
        SELECT active_flag
        INTO l_flag
        FROM customer
        WHERE customer_id = p_customer_id;

        RETURN l_flag = 'Y';
      END is_active;
    END customer_api;
    /

Specification cho caller biết cách gọi package. Body có thể thay đổi thuật toán, thêm helper hoặc tối ưu SQL mà không buộc caller thay đổi, miễn là public contract không đổi.

### 1.1. Vì sao không để ứng dụng gọi trực tiếp mọi bảng?

Nếu ứng dụng tự thực hiện nhiều câu SQL để tạo đơn hàng, logic có thể bị lặp trong nhiều service. Một service kiểm tra customer active, service khác quên kiểm tra; một batch cập nhật inventory mà không khóa hàng; một client khác cập nhật trạng thái theo quy tắc riêng.

Package nghiệp vụ có thể gom quy tắc chung vào một nơi. Ví dụ, CREATE_ORDER luôn xác thực customer, kiểm tra tồn kho, tạo order header/line và trừ inventory trong một transaction.

Tuy nhiên, package không tự động làm hệ thống tốt hơn. Nếu package chỉ bọc một câu INSERT và tạo thêm nhiều lớp gọi không cần thiết, lợi ích thấp. Hãy đặt trong package những hành vi cần tái sử dụng, kiểm soát quyền hoặc thực thi nhất quán gần dữ liệu.

### 1.2. API công khai và chi tiết nội bộ

Chỉ expose routine mà caller thực sự cần. Helper như normalize input, load internal configuration hoặc calculate intermediate value có thể để private trong body.

    CREATE OR REPLACE PACKAGE BODY order_api AS

      FUNCTION normalize_actor(
        p_actor IN VARCHAR2
      ) RETURN VARCHAR2 IS
      BEGIN
        RETURN UPPER(TRIM(p_actor));
      END normalize_actor;

      PROCEDURE write_audit(
        p_order_id IN NUMBER,
        p_actor    IN VARCHAR2
      ) IS
      BEGIN
        INSERT INTO order_audit(order_id, actor, action_time)
        VALUES (p_order_id, p_actor, SYSTIMESTAMP);
      END write_audit;

    END order_api;
    /

Nếu caller không cần gọi normalize_actor hoặc write_audit, không khai báo chúng trong specification. Điều này giữ public API nhỏ và giảm coupling.

## 2. Thiết kế package specification

Specification là phần quan trọng nhất của hợp đồng. Thay đổi ở đây có thể buộc package phụ thuộc, Java code, job và integration client phải compile hoặc triển khai lại.

Một specification nên:

- Dùng tên routine và tham số diễn tả nghiệp vụ.
- Định nghĩa kiểu tham số đủ chính xác và nhất quán.
- Dùng parameter mode đúng với luồng dữ liệu.
- Quy định rõ NULL, default và giá trị hợp lệ.
- Công bố exception/mã lỗi có ý nghĩa.
- Hạn chế expose cấu trúc nội bộ không cần thiết.
- Tránh overload mơ hồ với JDBC hoặc client khác.
- Có comment mô tả contract và transaction semantics.

Ví dụ:

    CREATE OR REPLACE PACKAGE order_api AS

      PROCEDURE create_order(
        p_customer_id IN  order_header.customer_id%TYPE,
        p_product_id  IN  order_line.product_id%TYPE,
        p_quantity    IN  order_line.quantity%TYPE,
        p_actor       IN  order_header.created_by%TYPE,
        p_order_id    OUT order_header.order_id%TYPE
      );

      FUNCTION calculate_total(
        p_order_id IN order_header.order_id%TYPE
      ) RETURN NUMBER;

      PROCEDURE approve_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.approved_by%TYPE
      );

    END order_api;
    /

Caller chỉ cần hiểu ý nghĩa của create_order, calculate_total và approve_order. Các bảng cụ thể vẫn là implementation detail, dù specification có thể dùng %TYPE để giữ tương thích với cột tương ứng.

### 2.1. Tên package và routine

Nên chọn tên theo domain capability, ví dụ ORDER_API, CUSTOMER_API, INVENTORY_API, PAYMENT_API hoặc ACCOUNTING_API. Tránh tên quá chung như UTIL, COMMON hoặc PKG1 cho package nghiệp vụ công khai.

Tên routine nên dùng động từ thể hiện hành động: create_order, approve_order, cancel_order, get_balance. Không expose routine có tên do implementation như update_status_flag nếu caller cần một hành vi nghiệp vụ như approve_order.

### 2.2. Comment hợp đồng

Comment trong specification có thể ghi:

- Ý nghĩa từng tham số.
- Đơn vị đo, ví dụ amount theo currency nào.
- NULL được chấp nhận hay bị từ chối.
- OUT parameter có giá trị trong trường hợp thành công nào.
- Exception/mã lỗi có thể phát sinh.
- Routine có commit hay để caller quản lý transaction.
- Có khóa hàng hoặc có thể chờ lock hay không.
- Idempotency và điều kiện gọi lặp lại.
- Quyền cần có.

Ví dụ:

    /*
      Creates one order line and reserves inventory.
      p_quantity must be greater than zero.
      p_actor is required and is stored for audit.
      p_order_id is populated only after successful creation.
      The procedure does not COMMIT; the caller owns the transaction.
      Business errors use the ORDER_API error range -20001 to -20009.
    */

Comment phải phản ánh đúng implementation. Nếu body thay đổi transaction behavior, cập nhật contract và test tương ứng.

## 3. Chọn kiểu dữ liệu cho tham số

Kiểu dữ liệu là một phần của API. Chọn sai kiểu có thể gây mất precision, cắt chuỗi hoặc tạo conversion phụ thuộc NLS.

### 3.1. Dùng %TYPE khi tham số tương ứng với cột

Nếu customer ID có cùng semantics với cột CUSTOMER_ID, có thể khai báo:

    p_customer_id IN customer.customer_id%TYPE

Lợi ích:

- Giữ kiểu dữ liệu đồng bộ với cột.
- Nếu column datatype thay đổi, package specification có thể được cập nhật qua dependency/recompile.
- Giảm việc lặp lại NUMBER/VARCHAR2 length không cần thiết.
- Thể hiện quan hệ giữa tham số và dữ liệu lưu trữ.

Tuy nhiên, %TYPE không thay thế tài liệu nghiệp vụ. Nếu column là NUMBER(10), caller vẫn cần biết đây là ID chứ không phải số lượng hay số tiền.

### 3.2. Dùng kiểu cụ thể cho API độc lập

Có trường hợp public API không nên phụ thuộc trực tiếp vào một bảng. Khi đó, dùng kiểu rõ ràng như NUMBER, VARCHAR2, DATE hoặc subtype được khai báo trong package.

    SUBTYPE t_order_id IS NUMBER;
    SUBTYPE t_currency_code IS VARCHAR2(3);
    SUBTYPE t_actor IS VARCHAR2(128);

    PROCEDURE approve_order(
      p_order_id IN t_order_id,
      p_actor    IN t_actor
    );

PL/SQL subtype có thể cải thiện cách đọc và tái sử dụng, nhưng không nhất thiết tạo ra một kiểu JDBC mới. Client Java vẫn cần bind theo SQL type thực tế của tham số.

### 3.3. NUMBER và tiền tệ

Dùng NUMBER cho dữ liệu số chính xác. Với amount, xác định precision/scale theo nghiệp vụ và currency. Không dùng BINARY_FLOAT/BINARY_DOUBLE cho phép tính tiền cần decimal exactness nếu không có lý do rõ ràng.

    amount NUMBER(18, 2)

Nhưng không phải mọi currency đều có hai chữ số thập phân. Một số đơn vị tiền tệ có scale khác; hệ thống cần quy tắc currency-aware và rounding rõ ràng.

Ở Java, dùng BigDecimal. Tránh chuyển amount qua double rồi mới tạo BigDecimal vì có thể mang sai số biểu diễn nhị phân vào database.

### 3.4. VARCHAR2 và độ dài

Chọn độ dài theo contract và cột đích. Không dùng VARCHAR2(4000) cho mọi tham số chỉ để tránh suy nghĩ về độ dài. Xác định:

- Độ dài tính theo BYTE hay CHAR.
- Character set database.
- Có cho phép Unicode hay không.
- Chuỗi rỗng được xử lý ra sao.
- Có trim/normalize hay giữ nguyên whitespace.
- Có giới hạn theo domain như actor, code, description.

Oracle thường coi chuỗi rỗng VARCHAR2 là NULL trong nhiều ngữ cảnh. Vì vậy, nếu API cần phân biệt empty string với missing value, phải định nghĩa một biểu diễn khác hoặc quy tắc rõ ràng.

### 3.5. DATE và TIMESTAMP

Oracle DATE chứa ngày và giờ đến giây, không có timezone. TIMESTAMP có fractional seconds nhưng không có timezone. TSTZ và TSLTZ có semantics timezone khác nhau.

Chọn kiểu dựa trên ý nghĩa:

| Ý nghĩa | Kiểu Oracle gợi ý | Ghi chú |
|---|---|---|
| Ngày nghiệp vụ | DATE | Quy ước phần giờ, thường là nửa đêm |
| Ngày giờ địa phương không timezone | TIMESTAMP | Caller phải biết timezone theo contract |
| Event timestamp có offset | TIMESTAMP WITH TIME ZONE | Phù hợp khi cần biểu diễn thời điểm có offset |
| Hiển thị theo session timezone | TIMESTAMP WITH LOCAL TIME ZONE | Kết quả phụ thuộc SESSIONTIMEZONE |

Không nhận timestamp dưới dạng chuỗi tự do rồi parse theo NLS mặc định. Ưu tiên bind typed parameter và xác định timezone ở boundary.

### 3.6. BOOLEAN và khả năng tương thích SQL/JDBC

PL/SQL có BOOLEAN, nhưng SQL type support phụ thuộc phiên bản Oracle. Không giả định mọi JDBC driver hoặc SQL context có thể bind trực tiếp PL/SQL BOOLEAN như một NUMBER/VARCHAR2.

Nếu package cần API tương thích rộng với SQL/JDBC, có thể dùng NUMBER(1) hoặc VARCHAR2(1) với contract rõ ràng, ví dụ 1/0 hoặc Y/N. Với PL/SQL-only API, BOOLEAN có thể tự nhiên hơn nếu phiên bản và caller hỗ trợ.

### 3.7. Collection, record và object type

Package có thể khai báo RECORD và collection type. Chúng hữu ích cho PL/SQL caller, nhưng không phải lúc nào cũng thuận tiện cho JDBC/ORM.

Nếu Java cần truyền danh sách lớn, cân nhắc SQL collection type được tạo ở schema level và Oracle JDBC hỗ trợ, GTT/staging table với request ID, JSON payload đã validate hoặc bulk operation qua staging API.

Chọn cách truyền dữ liệu theo kích thước, transaction semantics, khả năng bind của driver và version compatibility. Không expose PL/SQL-only record type nếu Java client không thể tiêu thụ dễ dàng.

## 4. IN, OUT và IN OUT

PL/SQL hỗ trợ ba parameter mode chính.

| Mode | Caller truyền vào | Routine trả ra | Dùng khi |
|---|---|---|---|
| IN | Có | Không sửa giá trị caller | Dữ liệu đầu vào |
| OUT | Không cần giá trị ban đầu | Có | Trả ID, trạng thái hoặc kết quả bổ sung |
| IN OUT | Có | Có thể thay đổi và trả lại | Chuẩn hóa hoặc cập nhật giá trị caller truyền vào |

### 4.1. IN

IN là mode mặc định. Caller cung cấp giá trị và routine dùng để xử lý. Trong routine, không gán lại giá trị cho tham số IN.

    PROCEDURE approve_order(
      p_order_id IN NUMBER
    );

IN phù hợp với customer ID, quantity, amount, actor và các lựa chọn nghiệp vụ.

### 4.2. OUT

OUT dùng để trả dữ liệu bổ sung ngoài function return. Ví dụ tạo order trả order ID:

    PROCEDURE create_order(
      p_customer_id IN NUMBER,
      p_order_id OUT NUMBER
    );

OUT parameter cần được gán trên mọi đường thành công. Nếu routine phát sinh exception, caller không nên dựa vào giá trị OUT đã gán một phần; contract nên nói rõ chỉ tin giá trị khi routine hoàn tất thành công.

OUT có thể phù hợp với nhiều giá trị trả về, nhưng nếu API trả nhiều dữ liệu phức tạp, cân nhắc một result type/cursor hoặc function trả object phù hợp thay vì quá nhiều OUT parameter.

### 4.3. IN OUT

IN OUT nhận một giá trị và trả giá trị đã được routine thay đổi.

    PROCEDURE normalize_order_code(
      p_code IN OUT VARCHAR2
    );

Ví dụ body:

    PROCEDURE normalize_order_code(
      p_code IN OUT VARCHAR2
    ) IS
    BEGIN
      p_code := UPPER(TRIM(p_code));
    END;

Dùng IN OUT khi caller thực sự cần nhận lại phiên bản đã chuẩn hóa. Nếu routine chỉ trả một kết quả mới, OUT hoặc function return thường làm contract dễ hiểu hơn.

### 4.4. Không dùng OUT để truyền lỗi

Không nên trả status code lỗi qua OUT parameter trong khi routine cũng có thể raise exception mà không có quy tắc thống nhất. Hai kênh báo lỗi khiến caller khó biết phải ưu tiên kết quả nào.

Hãy chọn một mô hình rõ ràng:

- Thành công: return/OUT chứa kết quả.
- Lỗi nghiệp vụ hoặc lỗi kỹ thuật: raise exception với mã có contract.
- Nếu API cần trả nhiều validation errors cùng lúc, thiết kế result structure riêng và mô tả rõ routine không raise cho các lỗi validation đó.

Không trộn mô hình “trả -1” và “raise exception” tùy trường hợp mà không tài liệu hóa.

## 5. Tham số mặc định và notation

PL/SQL cho phép khai báo default value cho tham số IN. Điều này giúp thêm tùy chọn mà caller có thể bỏ qua.

    PROCEDURE search_orders(
      p_customer_id IN NUMBER,
      p_status      IN VARCHAR2 DEFAULT NULL,
      p_from_date   IN DATE DEFAULT NULL
    );

Caller có thể gọi:

    order_api.search_orders(p_customer_id => 7001);

Hoặc:

    order_api.search_orders(
      p_customer_id => 7001,
      p_status => 'NEW'
    );

### 5.1. Positional notation

Positional notation truyền tham số theo đúng thứ tự khai báo:

    order_api.approve_order(900001, 'SERVICE_API');

Cách này ngắn nhưng dễ sai khi có nhiều tham số cùng kiểu. Khi specification thay đổi thứ tự hoặc thêm tham số, caller có thể bị ảnh hưởng.

### 5.2. Named notation

Named notation dùng tên tham số:

    order_api.approve_order(
      p_order_id => 900001,
      p_actor => 'SERVICE_API'
    );

Nó làm lời gọi dễ đọc và giảm nhầm lẫn giữa các giá trị cùng kiểu. Với routine có nhiều tham số, nên ưu tiên named notation trong PL/SQL caller.

JDBC CallableStatement thường bind theo vị trí hoặc tên tùy driver/API hỗ trợ; không giả định named notation của PL/SQL tự động biến thành named bind trong mọi JDBC call. Có thể dùng PL/SQL block với bind placeholders theo vị trí để gọi.

### 5.3. Thêm tham số mặc định có tương thích không?

Thêm tham số cuối cùng có default thường có thể giữ một số caller cũ hoạt động, nhưng không phải mọi trường hợp đều an toàn. Các yếu tố cần kiểm tra:

- Overload resolution.
- Caller dùng positional notation.
- Java/JDBC bind theo số lượng tham số.
- Dynamic SQL hoặc generated client.
- Package dependency và invalidation/recompile.
- Edition-based deployment và phiên bản package đang được dùng.

Không xem default parameter như cam kết backward compatibility tuyệt đối. Test mọi caller quan trọng trước khi thay specification.

### 5.4. Default không thay thế validation

Nếu p_status DEFAULT NULL, routine phải định nghĩa NULL nghĩa là không filter, dùng default status hay input không hợp lệ. Không để NULL có nhiều cách diễn giải giữa các routine.

Với tham số bắt buộc, hãy kiểm tra NULL rõ ràng và phát sinh lỗi contract. Oracle không tự bảo đảm mọi tham số IN là NOT NULL.

## 6. Xác định semantics của NULL và giá trị rỗng

NULL có thể mang nghĩa “không cung cấp”, “không biết”, “không áp dụng” hoặc “xóa giá trị”. Những ý nghĩa này khác nhau và cần được định nghĩa cho từng tham số.

Ví dụ cập nhật địa chỉ:

- NULL nghĩa là giữ địa chỉ cũ?
- NULL nghĩa là xóa địa chỉ?
- NULL bị từ chối?
- Chuỗi rỗng có được coi là NULL?
- Có cần một cờ riêng để phân biệt “không gửi field” và “gửi field với null”?

Với API update, một tham số IN đơn giản thường không đủ để phân biệt “không thay đổi” với “đặt thành NULL”. Có thể dùng thêm cờ, overload, JSON patch model hoặc procedure riêng cho từng thao tác.

Ví dụ:

    PROCEDURE update_customer_email(
      p_customer_id IN NUMBER,
      p_email       IN VARCHAR2,
      p_clear_email IN NUMBER DEFAULT 0
    );

Contract cần nêu:
- p_clear_email = 1: xóa email.
- p_clear_email = 0 và p_email khác NULL: đặt email mới.
- p_clear_email = 0 và p_email NULL: không thay đổi hoặc bị từ chối, tùy lựa chọn được tài liệu hóa.

Không thiết kế API mà caller phải đoán semantics NULL.

## 7. Thiết kế hợp đồng lỗi

Lỗi cần có mã ổn định để caller phân loại. Không nên yêu cầu Java parse chuỗi thông điệp Oracle hoặc phụ thuộc vào ORA message đầy đủ.

Một package có thể định nghĩa dải lỗi ứng dụng trong khoảng -20000 đến -20999 bằng RAISE_APPLICATION_ERROR. Nên dành dải con theo package/domain để tránh trùng mã giữa các module.

Ví dụ:

| Mã lỗi | Tên logic | Điều kiện |
|---:|---|---|
| -20001 | INVALID_INPUT | Tham số bắt buộc thiếu hoặc không hợp lệ |
| -20002 | CUSTOMER_NOT_FOUND | Customer không tồn tại |
| -20003 | CUSTOMER_INACTIVE | Customer không hoạt động |
| -20004 | PRODUCT_NOT_FOUND | Product không tồn tại |
| -20005 | INSUFFICIENT_STOCK | Tồn kho không đủ |
| -20006 | ORDER_NOT_FOUND | Order không tồn tại |
| -20007 | INVALID_ORDER_STATE | Trạng thái không cho phép thao tác |
| -20008 | DUPLICATE_REQUEST | Request đã được xử lý |
| -20009 | INTERNAL_ERROR | Lỗi nội bộ không được phân loại cụ thể |

Tên logic và mã chỉ là ví dụ. Tổ chức cần quản lý registry mã lỗi và không tái sử dụng một mã cho nhiều ý nghĩa.

### 7.1. Khai báo exception công khai

Specification có thể khai báo exception và gắn với mã lỗi:

    CREATE OR REPLACE PACKAGE order_api AS
      e_invalid_input EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_invalid_input, -20001);

      e_customer_not_found EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_customer_not_found, -20002);

      e_insufficient_stock EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_insufficient_stock, -20005);

      PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_product_id  IN NUMBER,
        p_quantity    IN NUMBER,
        p_order_id    OUT NUMBER
      );
    END order_api;
    /

PL/SQL caller có thể bắt exception theo tên package:

    BEGIN
      order_api.create_order(7001, 100, 2, :order_id);
    EXCEPTION
      WHEN order_api.e_insufficient_stock THEN
        -- handle stock conflict
        NULL;
    END;
    /

Java caller thường nhận SQLException với vendor error code tương ứng. Error code là contract ổn định hơn message text.

### 7.2. RAISE_APPLICATION_ERROR

Dùng RAISE_APPLICATION_ERROR để trả lỗi nghiệp vụ có mã trong dải ứng dụng:

    RAISE_APPLICATION_ERROR(
      -20005,
      'Insufficient stock for requested quantity'
    );

Thông điệp nên ngắn, có ý nghĩa và không tiết lộ dữ liệu nhạy cảm. Không đưa password, token, full SQL chứa dữ liệu cá nhân hoặc thông tin nội bộ vào error message trả cho client.

Tham số thứ ba có thể điều khiển việc thêm lỗi vào stack theo semantics của Oracle. Chỉ dùng khi cần giữ error stack và hiểu cách caller/monitoring hiển thị nó.

### 7.3. Validation lỗi đầu vào

Validate ngay ở boundary package để mọi caller nhận cùng hành vi:

    IF p_customer_id IS NULL THEN
      RAISE_APPLICATION_ERROR(
        -20001,
        'Customer ID is required'
      );
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RAISE_APPLICATION_ERROR(
        -20001,
        'Quantity must be greater than zero'
      );
    END IF;

Đừng chỉ dựa vào constraint table để báo lỗi. Constraint vẫn là lớp bảo vệ cuối cùng, nhưng package có thể trả thông điệp nghiệp vụ rõ hơn và tránh thực hiện nhiều bước trước khi phát hiện input sai.

### 7.4. Phân biệt lỗi nghiệp vụ và lỗi kỹ thuật

Lỗi nghiệp vụ là kết quả có thể dự đoán theo contract, ví dụ customer không tồn tại hoặc tồn kho không đủ. Lỗi kỹ thuật là vấn đề ngoài điều kiện nghiệp vụ, ví dụ tablespace đầy, network disconnect, invalid object hoặc lỗi nội bộ không dự kiến.

Không chuyển mọi exception thành một lỗi nghiệp vụ chung. Nếu bắt WHEN OTHERS rồi raise -20001, caller sẽ hiểu nhầm lỗi database thành input sai và có thể retry hoặc trả HTTP code sai.

Một cách phân loại:

- Input invalid: mã lỗi riêng, thường không retry.
- Resource not found: mã lỗi riêng, thường không retry.
- State conflict/insufficient stock: mã lỗi nghiệp vụ, client có thể yêu cầu người dùng xử lý lại.
- Deadlock/transient lock: lỗi kỹ thuật hoặc mã được quy ước để retry có giới hạn.
- Connectivity/storage/internal Oracle error: giữ thông tin gốc cho log/monitoring, trả lỗi an toàn qua API.

## 8. Xử lý exception đúng cách trong package body

Một exception handler tốt phải giữ được nguyên nhân, transaction semantics và thông tin chẩn đoán.

### 8.1. Bắt exception cụ thể

Ví dụ:

    BEGIN
      SELECT active_flag
      INTO l_active_flag
      FROM customer
      WHERE customer_id = p_customer_id;
    EXCEPTION
      WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
          -20002,
          'Customer does not exist'
        );
    END;

Không dùng WHEN OTHERS nếu chỉ cần xử lý NO_DATA_FOUND. Exception cụ thể giữ cho lỗi không dự kiến tiếp tục nổi lên thay vì bị che giấu.

### 8.2. Không nuốt lỗi

Mẫu không nên dùng:

    EXCEPTION
      WHEN OTHERS THEN
        NULL;

Cách này khiến caller tưởng routine thành công dù dữ liệu có thể chưa được cập nhật. Nếu có lỗi, caller phải nhận được exception hoặc một kết quả lỗi được định nghĩa rõ trong contract.

### 8.3. Ghi log rồi raise lại

Nếu cần ghi log, phải bảo đảm lỗi gốc không bị mất. Ví dụ:

    EXCEPTION
      WHEN OTHERS THEN
        error_log_api.write_error(
          p_module => 'ORDER_API',
          p_code   => SQLCODE,
          p_text   => SQLERRM
        );
        RAISE;

RAISE trong exception handler phát lại exception hiện tại. Tránh dùng RAISE_APPLICATION_ERROR với mã mới nếu không có chủ đích ánh xạ lỗi, vì nó có thể làm mất hoặc thay đổi loại lỗi mà caller cần biết.

Nếu logging procedure dùng autonomous transaction để ghi log ngay cả khi transaction caller rollback, cần hiểu rằng log sẽ tồn tại độc lập. Logging phải tránh lỗi phụ làm che lỗi gốc; nếu logger thất bại, không được vô tình thay thế exception ban đầu bằng lỗi logging.

### 8.4. DBMS_UTILITY error stack

Để chẩn đoán, có thể lưu:

    DBMS_UTILITY.FORMAT_ERROR_STACK
    DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
    DBMS_UTILITY.FORMAT_CALL_STACK

Các hàm này giúp ghi nhận stack và vị trí phát sinh lỗi. Chúng phù hợp với log nội bộ, không nên trả nguyên backtrace cho client public.

### 8.5. Giữ mã lỗi ổn định

Nếu Java client phân loại ORA-20005 là insufficient stock, đừng đổi mã đó thành một ý nghĩa khác trong release sau. Có thể bổ sung mã mới nhưng nên giữ mã cũ trong giai đoạn tương thích hoặc version API rõ ràng.

Thông điệp có thể được cải thiện, nhưng client không nên parse message để quyết định business behavior. Hãy dựa vào vendor code và mapping rõ ràng.

## 9. Ranh giới transaction: ai COMMIT và ai ROLLBACK?

Một package nghiệp vụ phải công bố rõ transaction ownership. Đây là phần thường bị bỏ quên nhưng ảnh hưởng trực tiếp tới cách Java/Spring gọi package.

Có hai mô hình phổ biến:

1. **Caller-owned transaction**: package thực hiện DML nhưng không COMMIT/ROLLBACK; ứng dụng hoặc caller quyết định commit/rollback.
2. **Package-owned transaction**: routine tự COMMIT/ROLLBACK theo contract và chịu trách nhiệm hoàn tất thao tác.

Với ứng dụng Spring/JPA/JDBC, caller-owned transaction thường linh hoạt hơn vì Spring transaction manager có thể điều khiển nhiều repository call trong cùng transaction trên một connection.

### 9.1. Caller-owned transaction

Ví dụ package body:

    PROCEDURE create_order(...) IS
    BEGIN
      INSERT INTO order_header(...);
      INSERT INTO order_line(...);
      UPDATE inventory ...;
      -- No COMMIT here.
    END;

Java:

    @Transactional
    public Long createOrder(CreateOrderRequest request) {
        Long orderId = orderRepository.createThroughPackage(request);
        auditRepository.writeCreatedEvent(orderId);
        return orderId;
    }

Nếu package phát sinh exception, transaction manager có thể rollback toàn bộ thay đổi transactional trên cùng connection. Cần bảo đảm package không tự commit hoặc dùng autonomous transaction cho nghiệp vụ chính.

### 9.2. Package tự COMMIT

Nếu package tự commit, nó kết thúc transaction của session. Điều này có thể phá vỡ giả định của caller rằng tất cả thao tác trong @Transactional được commit/rollback cùng nhau.

    @Transactional
    public void process() {
        repository.updateA();
        orderApi.createOrder(); // package COMMITs internally
        repository.updateB();
        throw new RuntimeException();
    }

Khi exception xảy ra, updateA/updateB có thể rollback nhưng thay đổi đã commit trong createOrder vẫn tồn tại. Caller không còn atomicity như mong đợi.

Chỉ dùng package-owned transaction khi đây là contract có chủ đích, ví dụ một API độc lập tự quản lý toàn bộ đơn vị nghiệp vụ. Phải tài liệu hóa rõ và không gọi nó như một phần của transaction lớn mà caller mong đợi rollback toàn bộ.

### 9.3. Không rollback transaction của caller tùy tiện

Một package không nên bắt lỗi rồi gọi ROLLBACK toàn session nếu caller có thể đang thực hiện các thao tác khác trong cùng transaction. ROLLBACK sẽ hủy mọi thay đổi chưa commit của caller, kể cả thay đổi nằm ngoài package.

Nếu package cần hoàn tác phần việc riêng khi lỗi, có thể dùng SAVEPOINT và ROLLBACK TO SAVEPOINT trong phạm vi đã thỏa thuận. Tuy nhiên, savepoint cũng thuộc transaction của session và cần phối hợp với caller; không dùng nếu package contract không cho phép.

### 9.4. Autonomous transaction chỉ dành cho side effect độc lập

PRAGMA AUTONOMOUS_TRANSACTION tạo transaction độc lập. Nó có thể hữu ích cho audit/error log cần tồn tại dù transaction chính rollback, nhưng không nên dùng cho dữ liệu nghiệp vụ cần atomicity với transaction caller.

Ví dụ log lỗi có thể được commit riêng. Nếu package ghi order trong autonomous transaction còn caller rollback phần khác, dữ liệu sẽ lệch. Chỉ dùng autonomous transaction cho side effect thực sự độc lập và được tài liệu hóa.

## 10. Khóa dữ liệu và concurrency trong package nghiệp vụ

Một API nghiệp vụ phải xác định cách xử lý nhiều caller đồng thời. Ví dụ hai request cùng đặt sản phẩm cuối cùng trong kho. Nếu chỉ đọc số lượng rồi update sau, cả hai có thể cùng thấy còn một đơn vị và cùng bán.

### 10.1. SELECT FOR UPDATE

Package có thể khóa hàng inventory trước khi kiểm tra và giảm số lượng:

    SELECT available_qty
    INTO l_available_qty
    FROM inventory
    WHERE product_id = p_product_id
    FOR UPDATE;

    IF l_available_qty < p_quantity THEN
      RAISE_APPLICATION_ERROR(
        -20005,
        'Insufficient stock'
      );
    END IF;

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id;

FOR UPDATE giữ row lock tới khi transaction commit hoặc rollback. Session khác muốn khóa cùng hàng sẽ chờ hoặc nhận lỗi theo NOWAIT/WAIT/SKIP LOCKED semantics nếu được dùng.

### 10.2. Atomic conditional update

Một cách khác là update có điều kiện:

    UPDATE inventory
    SET available_qty = available_qty - p_quantity
    WHERE product_id = p_product_id
      AND available_qty >= p_quantity;

    IF SQL%ROWCOUNT = 0 THEN
      RAISE_APPLICATION_ERROR(
        -20005,
        'Insufficient stock or product not found'
      );
    END IF;

Cách này gộp kiểm tra và thay đổi trong một câu SQL, giảm cửa sổ race. Nếu cần phân biệt product không tồn tại với tồn kho không đủ, thực hiện kiểm tra riêng hoặc dùng RETURNING/logic bổ sung phù hợp.

Chọn phương án theo yêu cầu lock, thông báo lỗi và contention. Đừng đọc quantity ở một câu SELECT bình thường rồi update mà không có cơ chế bảo vệ.

### 10.3. Lock order nhất quán

Nếu một routine khóa nhiều bảng/hàng, xác định thứ tự khóa nhất quán giữa các routine. Ví dụ luôn khóa order header trước rồi inventory theo product_id tăng dần. Thứ tự không nhất quán có thể tạo deadlock.

Deadlock ORA-00060 không phải lúc nào cũng là lỗi logic đơn giản; cần kiểm tra trace để biết hai session đang giữ/chờ lock nào. Caller có thể retry toàn bộ transaction với giới hạn nếu nghiệp vụ idempotent và lỗi phù hợp.

### 10.4. Idempotency và duplicate request

Một client có thể gửi lại request sau timeout dù database đã hoàn tất thao tác. Nếu create_order không có idempotency key, retry có thể tạo hai đơn hàng.

Package có thể nhận p_request_id hoặc p_idempotency_key và lưu trong bảng có unique constraint. Khi request key đã tồn tại, routine trả lại kết quả cũ hoặc raise mã DUPLICATE_REQUEST theo contract.

Đừng dựa vào kiểm tra “đã tồn tại chưa” đơn thuần rồi insert nếu không có unique constraint/locking phù hợp; hai session đồng thời có thể cùng vượt qua kiểm tra.

## 11. Ví dụ hoàn chỉnh: package ORDER_API

Phần này đưa ra một ví dụ minh họa có specification, error contract, validation, locking, DML và transaction ownership. Tên bảng/cột và mã lỗi chỉ là mẫu để giải thích thiết kế; cần điều chỉnh theo schema thực tế.

### 11.1. Schema minh họa

    CREATE TABLE customer (
      customer_id NUMBER(12) PRIMARY KEY,
      active_flag  CHAR(1) NOT NULL
        CHECK (active_flag IN ('Y', 'N'))
    );

    CREATE TABLE product (
      product_id NUMBER(12) PRIMARY KEY,
      active_flag CHAR(1) NOT NULL
        CHECK (active_flag IN ('Y', 'N')),
      unit_price NUMBER(18, 2) NOT NULL
    );

    CREATE TABLE inventory (
      product_id NUMBER(12) PRIMARY KEY
        REFERENCES product(product_id),
      available_qty NUMBER(12) NOT NULL
        CHECK (available_qty >= 0)
    );

    CREATE SEQUENCE order_seq;

    CREATE TABLE order_header (
      order_id NUMBER(18) PRIMARY KEY,
      customer_id NUMBER(12) NOT NULL
        REFERENCES customer(customer_id),
      status VARCHAR2(20) NOT NULL,
      total_amount NUMBER(18, 2) NOT NULL,
      created_by VARCHAR2(128) NOT NULL,
      created_at TIMESTAMP(6) WITH TIME ZONE NOT NULL,
      approved_by VARCHAR2(128),
      approved_at TIMESTAMP(6) WITH TIME ZONE
    );

    CREATE TABLE order_line (
      order_id NUMBER(18) NOT NULL
        REFERENCES order_header(order_id),
      line_no NUMBER(6) NOT NULL,
      product_id NUMBER(12) NOT NULL
        REFERENCES product(product_id),
      quantity NUMBER(12) NOT NULL
        CHECK (quantity > 0),
      unit_price NUMBER(18, 2) NOT NULL,
      line_total NUMBER(18, 2) NOT NULL,
      CONSTRAINT order_line_pk PRIMARY KEY(order_id, line_no)
    );

Trong ví dụ, một order có một line để tập trung vào package contract. Hệ thống thực tế có thể nhận collection nhiều dòng, tính thuế, discount, shipping và currency. Khi mở rộng, hãy xác định transaction, lock order và error behavior cho toàn bộ line items.

### 11.2. Package specification

    CREATE OR REPLACE PACKAGE order_api AS

      c_status_new       CONSTANT VARCHAR2(20) := 'NEW';
      c_status_approved  CONSTANT VARCHAR2(20) := 'APPROVED';
      c_status_cancelled CONSTANT VARCHAR2(20) := 'CANCELLED';

      c_err_invalid_input      CONSTANT PLS_INTEGER := -20001;
      c_err_customer_not_found CONSTANT PLS_INTEGER := -20002;
      c_err_customer_inactive  CONSTANT PLS_INTEGER := -20003;
      c_err_product_not_found  CONSTANT PLS_INTEGER := -20004;
      c_err_insufficient_stock CONSTANT PLS_INTEGER := -20005;
      c_err_order_not_found    CONSTANT PLS_INTEGER := -20006;
      c_err_invalid_state      CONSTANT PLS_INTEGER := -20007;

      e_invalid_input EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_invalid_input, -20001);

      e_customer_not_found EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_customer_not_found, -20002);

      e_customer_inactive EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_customer_inactive, -20003);

      e_product_not_found EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_product_not_found, -20004);

      e_insufficient_stock EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_insufficient_stock, -20005);

      e_order_not_found EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_order_not_found, -20006);

      e_invalid_state EXCEPTION;
      PRAGMA EXCEPTION_INIT(e_invalid_state, -20007);

      /*
        Creates an order with one product line.
        Quantity must be a positive integer.
        p_actor is required.
        p_order_id is set on successful completion.
        The caller owns COMMIT and ROLLBACK.
      */
      PROCEDURE create_order(
        p_customer_id IN  customer.customer_id%TYPE,
        p_product_id  IN  product.product_id%TYPE,
        p_quantity    IN  order_line.quantity%TYPE,
        p_actor       IN  order_header.created_by%TYPE,
        p_order_id    OUT order_header.order_id%TYPE
      );

      FUNCTION calculate_total(
        p_order_id IN order_header.order_id%TYPE
      ) RETURN order_header.total_amount%TYPE;

      PROCEDURE approve_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.approved_by%TYPE
      );

      PROCEDURE cancel_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.created_by%TYPE
      );

    END order_api;
    /

Specification công bố status constant và error code để caller có thể dùng nhất quán. Trong ứng dụng nhiều schema, có thể chọn không expose mọi constant nếu client chỉ cần mã lỗi; tuy nhiên, không để mỗi caller tự hard-code ý nghĩa khác nhau.

### 11.3. Package body: create_order

    CREATE OR REPLACE PACKAGE BODY order_api AS

      PROCEDURE create_order(
        p_customer_id IN  customer.customer_id%TYPE,
        p_product_id  IN  product.product_id%TYPE,
        p_quantity    IN  order_line.quantity%TYPE,
        p_actor       IN  order_header.created_by%TYPE,
        p_order_id    OUT order_header.order_id%TYPE
      ) IS
        l_customer_active customer.active_flag%TYPE;
        l_product_active  product.active_flag%TYPE;
        l_unit_price      product.unit_price%TYPE;
        l_available_qty   inventory.available_qty%TYPE;
        l_order_id        order_header.order_id%TYPE;
        l_actor           order_header.created_by%TYPE;
        l_total           order_header.total_amount%TYPE;
      BEGIN
        p_order_id := NULL;

        IF p_customer_id IS NULL
           OR p_product_id IS NULL
           OR p_quantity IS NULL
           OR p_actor IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Required order input is missing'
          );
        END IF;

        IF p_quantity <= 0 OR p_quantity <> TRUNC(p_quantity) THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Quantity must be a positive integer'
          );
        END IF;

        l_actor := TRIM(p_actor);

        IF l_actor IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Actor must not be blank'
          );
        END IF;

        BEGIN
          SELECT active_flag
          INTO l_customer_active
          FROM customer
          WHERE customer_id = p_customer_id;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_customer_not_found,
              'Customer does not exist'
            );
        END;

        IF l_customer_active <> 'Y' THEN
          RAISE_APPLICATION_ERROR(
            c_err_customer_inactive,
            'Customer is inactive'
          );
        END IF;

        BEGIN
          SELECT active_flag, unit_price
          INTO l_product_active, l_unit_price
          FROM product
          WHERE product_id = p_product_id;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_product_not_found,
              'Product does not exist'
            );
        END;

        IF l_product_active <> 'Y' THEN
          RAISE_APPLICATION_ERROR(
            c_err_product_not_found,
            'Product is not available'
          );
        END IF;

        BEGIN
          SELECT available_qty
          INTO l_available_qty
          FROM inventory
          WHERE product_id = p_product_id
          FOR UPDATE;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_product_not_found,
              'Inventory record does not exist'
            );
        END;

        IF l_available_qty < p_quantity THEN
          RAISE_APPLICATION_ERROR(
            c_err_insufficient_stock,
            'Insufficient stock'
          );
        END IF;

        l_order_id := order_seq.NEXTVAL;
        l_total := l_unit_price * p_quantity;

        INSERT INTO order_header(
          order_id,
          customer_id,
          status,
          total_amount,
          created_by,
          created_at
        )
        VALUES (
          l_order_id,
          p_customer_id,
          c_status_new,
          l_total,
          l_actor,
          SYSTIMESTAMP
        );

        INSERT INTO order_line(
          order_id,
          line_no,
          product_id,
          quantity,
          unit_price,
          line_total
        )
        VALUES (
          l_order_id,
          1,
          p_product_id,
          p_quantity,
          l_unit_price,
          l_total
        );

        UPDATE inventory
        SET available_qty = available_qty - p_quantity
        WHERE product_id = p_product_id;

        p_order_id := l_order_id;
      END create_order;

      FUNCTION calculate_total(
        p_order_id IN order_header.order_id%TYPE
      ) RETURN order_header.total_amount%TYPE IS
        l_total order_header.total_amount%TYPE;
      BEGIN
        IF p_order_id IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Order ID is required'
          );
        END IF;

        BEGIN
          SELECT total_amount
          INTO l_total
          FROM order_header
          WHERE order_id = p_order_id;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_order_not_found,
              'Order does not exist'
            );
        END;

        RETURN l_total;
      END calculate_total;

      PROCEDURE approve_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.approved_by%TYPE
      ) IS
        l_status order_header.status%TYPE;
        l_actor  order_header.approved_by%TYPE;
      BEGIN
        IF p_order_id IS NULL OR p_actor IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Order ID and actor are required'
          );
        END IF;

        l_actor := TRIM(p_actor);

        IF l_actor IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Actor must not be blank'
          );
        END IF;

        BEGIN
          SELECT status
          INTO l_status
          FROM order_header
          WHERE order_id = p_order_id
          FOR UPDATE;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_order_not_found,
              'Order does not exist'
            );
        END;

        IF l_status <> c_status_new THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_state,
            'Only NEW orders can be approved'
          );
        END IF;

        UPDATE order_header
        SET status = c_status_approved,
            approved_by = l_actor,
            approved_at = SYSTIMESTAMP
        WHERE order_id = p_order_id;
      END approve_order;

      PROCEDURE cancel_order(
        p_order_id IN order_header.order_id%TYPE,
        p_actor    IN order_header.created_by%TYPE
      ) IS
        l_status order_header.status%TYPE;
      BEGIN
        IF p_order_id IS NULL OR p_actor IS NULL
           OR TRIM(p_actor) IS NULL THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_input,
            'Order ID and actor are required'
          );
        END IF;

        BEGIN
          SELECT status
          INTO l_status
          FROM order_header
          WHERE order_id = p_order_id
          FOR UPDATE;
        EXCEPTION
          WHEN NO_DATA_FOUND THEN
            RAISE_APPLICATION_ERROR(
              c_err_order_not_found,
              'Order does not exist'
            );
        END;

        IF l_status <> c_status_new THEN
          RAISE_APPLICATION_ERROR(
            c_err_invalid_state,
            'Only NEW orders can be cancelled'
          );
        END IF;

        UPDATE inventory i
        SET available_qty = available_qty + (
          SELECT SUM(ol.quantity)
          FROM order_line ol
          WHERE ol.order_id = p_order_id
            AND ol.product_id = i.product_id
        )
        WHERE EXISTS (
          SELECT 1
          FROM order_line ol
          WHERE ol.order_id = p_order_id
            AND ol.product_id = i.product_id
        );

        UPDATE order_header
        SET status = c_status_cancelled
        WHERE order_id = p_order_id;
      END cancel_order;

    END order_api;
    /

Ví dụ body minh họa contract và transaction boundary. Trước khi dùng trong hệ thống thật, cần bổ sung quy tắc audit, authorization theo actor, currency/rounding, nhiều line, idempotency và chính sách inventory. Routine không COMMIT để caller có thể bao trùm nhiều thao tác trong một transaction.

### 11.4. Gọi package từ PL/SQL

Dùng named notation:

    DECLARE
      l_order_id NUMBER;
      l_total NUMBER;
    BEGIN
      order_api.create_order(
        p_customer_id => 7001,
        p_product_id  => 1001,
        p_quantity    => 2,
        p_actor       => 'ORDER_SERVICE',
        p_order_id    => l_order_id
      );

      l_total := order_api.calculate_total(
        p_order_id => l_order_id
      );

      order_api.approve_order(
        p_order_id => l_order_id,
        p_actor    => 'SUPERVISOR'
      );

      COMMIT;
    EXCEPTION
      WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
    END;
    /

Caller chịu trách nhiệm COMMIT/ROLLBACK. Trong ví dụ này, nếu approve_order lỗi, việc tạo order và trừ inventory cũng được rollback trong cùng transaction.

### 11.5. Gọi procedure từ Java/JDBC

Java gọi procedure có IN và OUT parameter bằng CallableStatement:

    String sql = "{ call order_api.create_order(?, ?, ?, ?, ?) }";

    try (CallableStatement statement =
             connection.prepareCall(sql)) {

        statement.setLong(1, 7001L);
        statement.setLong(2, 1001L);
        statement.setBigDecimal(3, new BigDecimal("2"));
        statement.setString(4, "ORDER_SERVICE");
        statement.registerOutParameter(5, Types.NUMERIC);

        statement.execute();

        BigDecimal orderId = statement.getBigDecimal(5);
    }

Nếu dùng Spring @Transactional, connection lấy từ transaction-managed DataSource cần được sử dụng nhất quán. Không tự mở connection độc lập bên trong cùng nghiệp vụ nếu mong muốn nó tham gia cùng transaction.

### 11.6. Gọi function từ Java/JDBC

Function return value được bind ở vị trí đầu:

    String sql = "{ ? = call order_api.calculate_total(?) }";

    try (CallableStatement statement =
             connection.prepareCall(sql)) {

        statement.registerOutParameter(1, Types.NUMERIC);
        statement.setLong(2, 900001L);
        statement.execute();

        BigDecimal total = statement.getBigDecimal(1);
    }

Kiểm tra error code từ SQLException nếu function phát sinh lỗi nghiệp vụ. Không parse message để xác định loại lỗi.

## 12. Mapping lỗi PL/SQL sang Java và REST API

Java caller nên có một lớp adapter chuyển lỗi Oracle thành exception ở tầng ứng dụng. Không để controller phụ thuộc trực tiếp vào mã ORA rải rác trong code.

Ví dụ:

    try {
        statement.execute();
    } catch (SQLException ex) {
        if (ex.getErrorCode() == 20005) {
            throw new InsufficientStockException(
                "Requested quantity is unavailable", ex
            );
        }
        throw new DatabaseOperationException(
            "Order creation failed", ex
        );
    }

Mã vendor error từ Oracle JDBC thường được trả dưới dạng số dương tương ứng với mã ORA-xxxxx. Hãy xác nhận giá trị thực tế trên driver/version đang dùng bằng integration test.

Tầng REST có thể ánh xạ domain exception:

| Domain exception | HTTP status thường phù hợp |
|---|---:|
| InvalidOrderInputException | 400 |
| CustomerNotFoundException | 404 |
| InsufficientStockException | 409 |
| InvalidOrderStateException | 409 |
| DatabaseUnavailableException | 503 |
| UnexpectedDatabaseException | 500 |

Đây là mapping tham khảo; API contract của tổ chức có thể khác. Không trả raw SQL, schema, stack trace hoặc toàn bộ Oracle message ra client. Ghi chi tiết kỹ thuật vào log có kiểm soát và trả correlation ID.

### 12.1. Không retry mọi lỗi

Lỗi invalid input hoặc customer not found không thể giải quyết bằng retry. Lỗi insufficient stock có thể thay đổi sau khi người dùng cập nhật giỏ hàng, nhưng retry ngay không chắc thành công. Lỗi deadlock hoặc transient connectivity có thể retry với giới hạn nếu toàn bộ operation idempotent.

Trước khi retry:

- Xác định transaction cũ đã commit hay chưa.
- Dùng idempotency key nếu request có thể được gửi lại.
- Chỉ retry mã lỗi được phân loại transient.
- Có backoff và giới hạn số lần.
- Không retry lỗi constraint/business conflict như thể đó là network timeout.

## 13. Quyền thực thi: AUTHID DEFINER và AUTHID CURRENT_USER

Package có thể chạy với quyền của owner (definer rights) hoặc quyền của caller (invoker rights).

### 13.1. AUTHID DEFINER

Đây là mô hình mặc định nếu không khai báo AUTHID khác. Package chạy với quyền của owner trong các điều kiện Oracle quy định. Caller có thể được cấp EXECUTE trên package mà không cần cấp trực tiếp quyền DML trên mọi bảng nội bộ.

    CREATE OR REPLACE PACKAGE order_api
      AUTHID DEFINER
    AS
      PROCEDURE create_order(...);
    END order_api;
    /

Mô hình này phù hợp khi package là API kiểm soát truy cập vào schema. Owner cần được cấp quyền cần thiết trên object phụ thuộc theo đúng quy tắc stored PL/SQL; quyền qua role không được dùng giống cách SQL interactive thông thường trong mọi trường hợp.

### 13.2. AUTHID CURRENT_USER

Invoker rights khiến routine thực thi trong quyền của caller theo semantics Oracle. Nó phù hợp với một số utility cần tuân theo quyền và schema context của người gọi.

    CREATE OR REPLACE PACKAGE report_api
      AUTHID CURRENT_USER
    AS
      PROCEDURE run_report(...);
    END report_api;
    /

Không chọn CURRENT_USER chỉ vì muốn package “an toàn hơn”. Nó thay đổi cách phân giải tên, quyền truy cập và khả năng gọi object. Cần hiểu ảnh hưởng tới current schema, roles và dynamic SQL.

### 13.3. Least privilege

Một application user có thể chỉ cần:

    GRANT EXECUTE ON order_api TO app_user;

Nếu package dùng definer rights, caller không nhất thiết cần quyền INSERT/UPDATE trực tiếp trên bảng nghiệp vụ. Điều này giúp thu hẹp quyền, nhưng package phải validate đầy đủ input và không tạo dynamic SQL nguy hiểm.

Không cấp CREATE ANY PROCEDURE, DBA hoặc quyền DML rộng cho application user chỉ để package chạy được.

## 14. Versioning và thay đổi package contract

Package specification là API. Thay đổi body thường ít ảnh hưởng caller hơn thay đổi specification, nhưng vẫn có thể làm thay đổi behavior, locking hoặc transaction time.

### 14.1. Thay đổi ít rủi ro hơn

- Tối ưu SQL trong body nhưng giữ cùng kết quả.
- Thêm private helper.
- Sửa thuật toán nội bộ không đổi contract.
- Bổ sung logging không làm thay đổi transaction.
- Tối ưu index access path nhưng giữ semantics.

Các thay đổi này vẫn cần regression test vì behavior và performance có thể đổi.

### 14.2. Thay đổi có thể phá caller

- Đổi kiểu tham số hoặc return type.
- Đổi thứ tự tham số khi caller dùng positional notation.
- Đổi IN thành OUT hoặc IN OUT.
- Đổi default/NULL semantics.
- Đổi error code.
- Thêm COMMIT vào routine trước đây caller-owned transaction.
- Thay status hoặc exception behavior.
- Đổi package AUTHID.
- Đổi public record/collection type.
- Thay REF CURSOR column shape.

Trước khi thay đổi, tìm mọi caller trong database và application repositories theo quy trình quản lý mã. Specification change phải được review như một API breaking change.

### 14.3. Overload cần thận trọng

PL/SQL hỗ trợ overload procedure/function cùng tên với signature khác. Overload tiện cho caller PL/SQL nhưng có thể gây mơ hồ với named notation, default parameters, implicit conversion và JDBC metadata.

Nếu Java/JDBC là client quan trọng, tên routine riêng như create_order_v2 hoặc create_order_from_request có thể dễ bind hơn overload phức tạp. Đừng overload chỉ để gom các biến thể không cùng contract.

### 14.4. Expand-and-contract

Khi cần đổi API:

1. Thêm routine hoặc tham số tương thích mới.
2. Triển khai client mới.
3. Theo dõi caller còn dùng API cũ.
4. Chuyển toàn bộ caller.
5. Chỉ loại bỏ API cũ ở release được quản lý.

Có thể giữ wrapper routine cũ gọi routine mới trong giai đoạn migration. Wrapper cần giữ semantics cũ và được đánh dấu deprecated trong tài liệu.

## 15. Dependency, compile và triển khai package

Package phụ thuộc bảng, view, sequence, synonym, type và package khác. Khi object phụ thuộc thay đổi, package có thể INVALID và cần compile lại.

### 15.1. Kiểm tra status

    SELECT
      owner,
      object_name,
      object_type,
      status
    FROM all_objects
    WHERE owner = 'APP_SCHEMA'
      AND object_name = 'ORDER_API'
    ORDER BY object_type;

Kiểm tra lỗi compile:

    SELECT
      name,
      type,
      line,
      position,
      text
    FROM user_errors
    WHERE name = 'ORDER_API'
    ORDER BY sequence;

### 15.2. Compile lại

    ALTER PACKAGE order_api COMPILE;
    ALTER PACKAGE order_api COMPILE BODY;

Nếu specification thay đổi, body có thể cần compile lại. Compile thành công không chứng minh business behavior đúng; cần chạy test.

### 15.3. Deploy specification và body

Trong migration script, tạo specification trước rồi body. Quản lý DDL trong version control, chạy migration theo thứ tự và kiểm tra status sau deploy.

Không chỉnh package trực tiếp ở production mà không cập nhật source/migration repository. Nếu hotfix khẩn cấp được áp dụng, phải đưa thay đổi trở lại source of truth và kiểm thử ở môi trường phù hợp.

## 16. Kiểm thử package contract

Một package nghiệp vụ cần test theo contract, không chỉ chạy một lần thành công.

### 16.1. Kiểm thử tham số

- IN nhận đúng kiểu và giá trị.
- OUT được gán khi thành công.
- IN OUT trả giá trị đã chuẩn hóa đúng.
- Default parameter hoạt động.
- NULL/empty string theo contract.
- Giá trị biên, độ dài, precision và scale.
- Tham số không hợp lệ phát sinh mã lỗi đúng.

### 16.2. Kiểm thử trạng thái nghiệp vụ

- Customer active/inactive.
- Product active/inactive.
- Inventory đủ/thiếu.
- Order NEW/APPROVED/CANCELLED/DELIVERED.
- Request trùng idempotency key.
- Hai session cạnh tranh cập nhật cùng order/inventory.
- Caller không có quyền EXECUTE.

### 16.3. Kiểm thử transaction

- Package không commit nếu contract caller-owned.
- Exception làm caller rollback được toàn bộ thao tác.
- Không có autonomous transaction ngoài mục đích.
- Sequence gap được chấp nhận.
- Trigger/audit side effect được hiểu rõ.
- JDBC và Spring transaction sử dụng cùng connection khi cần atomicity.

### 16.4. Kiểm thử lỗi

- Mã lỗi đúng.
- Message không chứa secret.
- Không nuốt exception.
- Lỗi kỹ thuật được giữ nguyên hoặc ánh xạ đúng.
- Java mapping không phụ thuộc message text.
- REST status code theo API contract.

### 16.5. Kiểm thử quyền

Chạy test dưới application user. Test dưới schema owner không chứng minh caller có quyền đúng. Kiểm tra AUTHID, EXECUTE grant và quyền object phụ thuộc.

## 17. Những lỗi thiết kế thường gặp

### 17.1. Package specification quá lớn

Expose quá nhiều helper và table-oriented routine khiến caller phụ thuộc vào implementation. Giữ API nhỏ, theo domain behavior và private helper trong body.

### 17.2. Tham số không có semantics rõ

Một tham số p_status có thể nhận NULL, empty string, wildcard hoặc giá trị tùy ý mà không được giải thích. Định nghĩa allowed values, case sensitivity, NULL behavior và validation.

### 17.3. Trả mã lỗi bằng số âm hoặc chuỗi tùy tiện

Nếu một routine trả -1, routine khác raise ORA-20001 và routine khác trả OUT status, caller phải viết logic riêng. Chuẩn hóa lỗi qua mã lỗi ứng dụng và exception contract.

### 17.4. Bắt WHEN OTHERS rồi bỏ qua

Lỗi bị nuốt làm caller không biết transaction thất bại. Bắt lỗi cụ thể, log theo chính sách rồi RAISE lại nếu không xử lý được.

### 17.5. Package tự commit ngoài dự kiến

Caller mất khả năng rollback toàn bộ nghiệp vụ. Quy định transaction ownership trong specification và test từ Spring/JDBC.

### 17.6. Dùng dynamic SQL với input chưa kiểm soát

Ghép table/column name hoặc filter từ client vào SQL tạo SQL injection. Dùng bind variables cho value; với identifier phải allowlist và kiểm tra bằng cơ chế phù hợp như DBMS_ASSERT.

### 17.7. Không khóa dữ liệu khi kiểm tra rồi cập nhật

Có thể xảy ra oversell hoặc lost update. Dùng SELECT FOR UPDATE hoặc conditional UPDATE có kiểm tra SQL%ROWCOUNT, kèm unique constraint khi cần.

### 17.8. Dùng overload khó gọi từ JDBC

Overload cùng tên với kiểu tương thích hoặc default có thể làm binding khó hiểu. Tạo routine tên riêng cho API client nếu cần contract ổn định.

### 17.9. Expose PL/SQL type không tương thích client

RECORD/BOOLEAN/collection có thể khó bind qua JDBC. Chọn SQL types hoặc API truyền dữ liệu phù hợp với client và driver version.

## 18. Quy trình xây dựng package nghiệp vụ

Một quy trình có thể áp dụng cho package mới:

1. Xác định capability nghiệp vụ và caller.
2. Liệt kê use case công khai và trạng thái đầu/cuối.
3. Viết package specification trước implementation.
4. Định nghĩa parameter name, mode, datatype, null/default semantics.
5. Xác định error code range và exception mapping.
6. Chọn transaction owner và lock strategy.
7. Xác định AUTHID và least-privilege grants.
8. Viết package body với validation trước DML.
9. Viết test cho success, boundary, failure và concurrency.
10. Kiểm thử bằng PL/SQL và JDBC application user.
11. Deploy qua migration có version control.
12. Kiểm tra invalid object, grants, status và application smoke test.

### 18.1. Mẫu contract table

Trước khi viết package, có thể lập bảng cho từng routine:

| Routine | Input | Output | Lỗi nghiệp vụ | Transaction |
|---|---|---|---|---|
| create_order | customer, product, quantity, actor | order_id | invalid input, customer/product missing, stock insufficient | Caller-owned |
| calculate_total | order_id | total amount | invalid ID, order missing | Read-only |
| approve_order | order_id, actor | none | order missing, invalid state | Caller-owned |
| cancel_order | order_id, actor | none | order missing, invalid state | Caller-owned |

Bảng contract buộc nhóm phát triển thống nhất behavior trước khi viết body. Có thể bổ sung lock behavior, idempotency, authorization và retry classification.

## 19. Checklist review package specification

- Tên package và routine mô tả domain behavior.
- Public API chỉ chứa thành phần caller cần.
- Tên tham số nhất quán và có ý nghĩa.
- Datatype/precision/length phù hợp với dữ liệu.
- IN/OUT/IN OUT được chọn đúng.
- Default và NULL semantics được ghi rõ.
- OUT parameter có quy tắc khi exception.
- Error code có registry và không tái sử dụng.
- Exception message không lộ thông tin nhạy cảm.
- Transaction ownership được công bố.
- Locking/idempotency behavior được mô tả.
- AUTHID và quyền cần thiết được xác định.
- Overload không gây mơ hồ cho JDBC.
- Public types tương thích với client.
- API change có kế hoạch version/migration.

## 20. Checklist triển khai và vận hành

- Specification/body được lưu trong version control.
- Migration tạo package theo thứ tự đúng.
- Package compile VALID.
- Dependency và grant đã tồn tại.
- Application user gọi được package.
- Test PL/SQL và JDBC đều chạy trên Oracle phù hợp.
- Error code mapping ở Java/REST đúng.
- Transaction rollback/commit đúng contract.
- Session state không rò giữa connection pool requests.
- Logging có correlation ID và không chứa secret.
- Performance/locking được đo ở workload đại diện.
- Rollback migration/package version có kế hoạch.

## 21. Nguyên tắc cần nhớ

- Package specification là hợp đồng công khai; body là implementation.
- Chỉ expose routine, type và constant mà caller cần.
- Dùng %TYPE khi tham số phản ánh trực tiếp cột; dùng kiểu cụ thể khi API cần độc lập với bảng.
- Chọn IN, OUT và IN OUT theo hướng dữ liệu; không dùng OUT để mã hóa lỗi tùy tiện.
- Định nghĩa rõ NULL, empty string, default, precision, timezone và đơn vị đo.
- Dùng error code ứng dụng ổn định với RAISE_APPLICATION_ERROR; caller phân loại theo code, không parse message.
- Bắt exception cụ thể; không nuốt WHEN OTHERS; log rồi RAISE khi không xử lý được.
- Công bố transaction ownership; tránh COMMIT/ROLLBACK trong package nếu caller cần kiểm soát transaction.
- Dùng locking/conditional update và idempotency để bảo vệ nghiệp vụ khi có concurrency/retry.
- Chọn AUTHID và grant theo least privilege.
- Xem specification change như API change; kiểm tra caller và JDBC binding.
- Kiểm thử bằng PL/SQL và application user qua JDBC để xác nhận cả logic lẫn contract.

Một package nghiệp vụ tốt cho caller một giao diện nhỏ, dễ hiểu và ổn định. Khi tham số, lỗi, transaction và quyền được định nghĩa trước, package có thể bảo vệ quy tắc dữ liệu ở database mà vẫn cho Spring Boot và các client khác tích hợp một cách dự đoán được.
