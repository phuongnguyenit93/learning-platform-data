# Thiết kế API cơ sở dữ liệu, ranh giới giao dịch và hợp đồng lỗi

Một API cơ sở dữ liệu là giao diện mà ứng dụng dùng để yêu cầu database thực hiện một nghiệp vụ. Trong Oracle, API này thường được xây dựng bằng package, procedure và function. Một API tốt không chỉ có chữ ký tham số dễ gọi; nó còn phải xác định rõ ai sở hữu transaction, dữ liệu nào được thay đổi, khi nào thay đổi được commit, lỗi nào có thể xuất hiện và caller phải phản ứng ra sao.

Ba quyết định cần thiết kế cùng nhau:

1. **API contract:** tên thao tác, đầu vào, đầu ra, điều kiện hợp lệ và kết quả nghiệp vụ.
2. **Transaction boundary:** transaction bắt đầu và kết thúc ở đâu; procedure có commit/rollback hay để caller quản lý.
3. **Error contract:** lỗi được phát hiện, chuyển đổi, truyền lên và xử lý như thế nào; sau lỗi, dữ liệu đang ở trạng thái nào.

Nếu ba phần này không nhất quán, ứng dụng dễ gặp các vấn đề như procedure con vô tình commit công việc của caller, lỗi bị nuốt khiến caller tưởng thành công, transaction để lại DML một phần, hoặc retry tạo giao dịch trùng. Bài học tập trung vào cách thiết kế package API có thể kết hợp an toàn trong nhiều luồng nghiệp vụ.

## 1. API cơ sở dữ liệu là gì?

Thay vì để mọi ứng dụng tự viết nhiều câu SQL trực tiếp vào các bảng, có thể cung cấp một giao diện nghiệp vụ:

~~~sql
BEGIN
    order_api.create_order(
        p_customer_id => 101,
        p_request_id  => 'REQ-2026-0001',
        p_order_id    => :new_order_id
    );
END;
/
~~~

Ứng dụng gọi thao tác CREATE_ORDER mà không cần biết toàn bộ chi tiết bảng, kiểm tra trạng thái khách hàng, ghi header, ghi detail hay audit.

API cơ sở dữ liệu có thể chịu trách nhiệm:

- Kiểm tra đầu vào và quy tắc nghiệp vụ.
- Đọc và cập nhật các bảng liên quan.
- Bảo đảm các bước của một thao tác được thực hiện nhất quán.
- Trả về định danh hoặc kết quả.
- Phát sinh lỗi có mã ổn định để caller phân loại.
- Ghi nhận thông tin vận hành phù hợp.

### 1.1 Vì sao nên đóng gói SQL trong package?

Package giúp nhóm các thao tác cùng miền nghiệp vụ và kiểm soát phần nào được công khai:

- Package specification là giao diện public.
- Package body chứa implementation nội bộ.
- Private procedure/function hỗ trợ xử lý nhưng caller không gọi trực tiếp.
- Package constants, types và exceptions có thể được dùng chung trong phạm vi API.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE inventory_api AS
    PROCEDURE reserve_stock(
        p_product_id IN products.product_id%TYPE,
        p_quantity   IN NUMBER
    );

    PROCEDURE release_stock(
        p_product_id IN products.product_id%TYPE,
        p_quantity   IN NUMBER
    );
END inventory_api;
/
~~~

Caller chỉ nhìn thấy hai thao tác công khai. Chi tiết SQL, bảng phụ, cách ghi log và quy trình khóa hàng có thể nằm trong package body.

### 1.2 API nên thể hiện nghiệp vụ

Một API như UPDATE_TABLE_ROW nhận tên bảng, tên cột và chuỗi điều kiện thường khó kiểm soát quyền, kiểu dữ liệu và hợp đồng lỗi. Một API nghiệp vụ như APPROVE_ORDER thể hiện rõ ý định và cho phép database thực thi quy tắc nhất quán.

Tên API nên mô tả hành động hoặc truy vấn có ý nghĩa:

- CREATE_ORDER.
- APPROVE_ORDER.
- RESERVE_INVENTORY.
- CANCEL_PAYMENT.
- GET_ACCOUNT_BALANCE.

Tránh để caller phải biết thứ tự gọi nhiều procedure nội bộ chỉ để hoàn thành một thao tác nghiệp vụ đơn giản.

## 2. Thiết kế package specification như một hợp đồng

Package specification là phần caller phụ thuộc. Mọi thay đổi ở đây có thể ảnh hưởng các chương trình phụ thuộc, do đó cần giữ giao diện ổn định và rõ nghĩa.

Một hợp đồng API nên mô tả:

- Tên thao tác và mục đích.
- Tham số IN, OUT, IN OUT.
- Kiểu dữ liệu và miền giá trị.
- Tham số bắt buộc và tùy chọn.
- Quy tắc NULL.
- Điều kiện trước khi gọi (preconditions).
- Kết quả khi thành công (postconditions).
- Lỗi nghiệp vụ và lỗi kỹ thuật có thể phát sinh.
- Quyền sở hữu transaction.
- Hành vi khi exception xảy ra.

Ví dụ package specification:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE create_order(
        p_customer_id IN  customers.customer_id%TYPE,
        p_request_id  IN  VARCHAR2,
        p_order_id    OUT orders.order_id%TYPE
    );

    PROCEDURE approve_order(
        p_order_id IN orders.order_id%TYPE
    );
END order_api;
/
~~~

Caller biết đầu vào, đầu ra và tên thao tác. Phần mô tả API cần bổ sung điều kiện nghiệp vụ và lỗi, vì chữ ký SQL/PLSQL không diễn đạt hết hợp đồng.

### 2.1 Chọn mode tham số

| Mode | Dùng khi | Ví dụ |
|---|---|---|
| IN | Caller cung cấp dữ liệu để xử lý | CUSTOMER_ID, ORDER_ID, AMOUNT |
| OUT | API trả một giá trị do nó tạo ra | ORDER_ID mới |
| IN OUT | API nhận và cập nhật trạng thái dữ liệu trong bộ nhớ | Collection cần biến đổi |

Ưu tiên IN cho đầu vào và OUT cho kết quả riêng. IN OUT chỉ nên dùng khi việc biến đổi giá trị đầu vào là ý nghĩa tự nhiên của API.

### 2.2 Không dùng OUT để che giấu nhiều trạng thái

Nếu một thao tác có thể thành công, bị từ chối theo nghiệp vụ hoặc phát sinh lỗi kỹ thuật, hãy quyết định rõ các trạng thái đó được biểu diễn bằng:

- Giá trị trả về.
- OUT parameter.
- Exception có mã lỗi.

Không nên vừa trả mã lỗi trong OUT parameter vừa phát sinh exception cho cùng một tình huống nếu caller không có quy tắc rõ ràng để ưu tiên một trong hai.

### 2.3 Dùng kiểu dữ liệu ổn định

%TYPE giúp đồng bộ kiểu tham số với cột:

~~~sql
PROCEDURE approve_order(
    p_order_id IN orders.order_id%TYPE
);
~~~

Tuy nhiên, package specification tham chiếu trực tiếp vào cấu trúc bảng sẽ tạo phụ thuộc compile-time. Nếu muốn API ít phụ thuộc schema vật lý hơn, có thể dùng subtype hoặc kiểu public do package định nghĩa:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    SUBTYPE t_order_id IS NUMBER(12);

    PROCEDURE approve_order(
        p_order_id IN t_order_id
    );
END order_api;
/
~~~

Chọn cách nào phụ thuộc quy ước schema và mong muốn quản lý version. Nếu kiểu cột thay đổi, cần kiểm tra package và các dependent object được biên dịch lại.

### 2.4 Không công khai mọi chi tiết nội bộ

Không nên đưa mọi bảng, record nội bộ, cursor và helper function vào package specification. Public API càng rộng thì càng khó thay đổi implementation mà không ảnh hưởng caller.

Chỉ công khai các thao tác caller thực sự cần, kiểu dữ liệu cần để gọi API, exception hoặc error code mà caller cần phân loại, và hằng số có ý nghĩa trong hợp đồng. Đặt helper procedure/function trong package body khi chúng chỉ phục vụ implementation.

## 3. Transaction boundary là gì?

Transaction boundary là ranh giới xác định nhóm thao tác database nào được commit cùng nhau hoặc rollback cùng nhau.

Ví dụ tạo đơn hàng có thể gồm:

1. Kiểm tra khách hàng.
2. Tạo order header.
3. Tạo order detail.
4. Giữ tồn kho.
5. Ghi lịch sử trạng thái.

Nếu các bước này thuộc một nghiệp vụ không thể tách rời, chúng thường phải nằm trong cùng một transaction. Nếu một bước thất bại, không nên để các bước trước đó bị commit riêng lẻ ngoài ý muốn.

### 3.1 Transaction thuộc về session, không thuộc riêng procedure

Oracle quản lý transaction trên session/connection. Nhiều procedure được gọi liên tiếp trên cùng connection có thể tham gia cùng một transaction:

~~~text
Application obtains connection
          |
          v
      API A DML
          |
          v
      API B DML
          |
          v
      API C DML
          |
          v
     Caller COMMIT
          |
          v
   All transaction work commits
~~~

Procedure không sở hữu một transaction độc lập chỉ vì nó là một đơn vị PL/SQL. Một lệnh COMMIT bên trong procedure kết thúc transaction hiện tại của session, bao gồm cả thay đổi do caller hoặc procedure khác thực hiện trước đó.

### 3.2 Ví dụ procedure commit làm ảnh hưởng caller

Giả sử caller:

~~~sql
BEGIN
    UPDATE customer_profile
    SET phone_number = '0900000000'
    WHERE customer_id = 101;

    order_api.create_order(
        p_customer_id => 101,
        p_request_id  => 'REQ-001',
        p_order_id    => :order_id
    );

    ROLLBACK;
END;
/
~~~

Nếu CREATE_ORDER thực hiện COMMIT bên trong, thay đổi PHONE_NUMBER của caller cũng được commit. Lệnh ROLLBACK cuối cùng không thể hoàn tác phần đã commit đó.

Đây là lý do các procedure nghiệp vụ cấp thấp thường không nên tự COMMIT hoặc ROLLBACK toàn transaction.

## 4. Hai mô hình sở hữu transaction

Có hai mô hình chính. Cần chọn một mô hình cho mỗi API và ghi rõ trong hợp đồng.

### 4.1 Caller-managed transaction

Caller chịu trách nhiệm:

- Bắt đầu đơn vị công việc bằng các DML đầu tiên.
- Gọi một hoặc nhiều API.
- Quyết định COMMIT khi toàn bộ nghiệp vụ thành công.
- ROLLBACK khi bất kỳ phần nào của nghiệp vụ thất bại.

Procedure được gọi không COMMIT và không ROLLBACK toàn transaction.

Ví dụ:

~~~sql
BEGIN
    order_api.create_order(
        p_customer_id => 101,
        p_request_id  => 'REQ-002',
        p_order_id    => :order_id
    );

    payment_api.reserve_payment(
        p_order_id => :order_id
    );

    inventory_api.reserve_order(
        p_order_id => :order_id
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Caller có thể kết hợp nhiều package trong một transaction. Đây là mô hình linh hoạt và thường phù hợp với API cần được tái sử dụng trong nhiều luồng nghiệp vụ.

### 4.2 API-owned transaction

Một API cấp cao có thể được thiết kế để tự hoàn tất transaction:

~~~sql
PROCEDURE submit_order(...) AS
BEGIN
    -- Validate, insert order, reserve stock...
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
~~~

Mô hình này chỉ phù hợp khi hợp đồng nói rõ thao tác là một đơn vị độc lập và caller chấp nhận rằng procedure kết thúc transaction của session.

Rủi ro:

- COMMIT sẽ commit cả thay đổi caller đã làm trước khi gọi.
- ROLLBACK sẽ rollback cả thay đổi caller chưa commit.
- Không thể ghép procedure này vào một transaction lớn hơn theo cách caller mong muốn.
- Caller khó phối hợp nhiều API nếu mỗi API tự commit.

Vì vậy, API-owned transaction thường chỉ nên dùng ở entry point cấp cao được gọi độc lập, với connection/session được dành riêng cho đơn vị công việc đó.

### 4.3 Quy tắc thực tế

| Loại procedure | Quy tắc transaction thường phù hợp |
|---|---|
| Helper nội bộ | Không COMMIT/ROLLBACK |
| API thao tác một phần nghiệp vụ, có thể ghép với API khác | Caller quản lý transaction |
| API cấp cao được định nghĩa là toàn bộ use case độc lập | Có thể tự COMMIT/ROLLBACK nếu hợp đồng nói rõ |
| Procedure ghi log/audit độc lập | Chỉ cân nhắc autonomous transaction cho dữ liệu chẩn đoán thực sự độc lập |
| Procedure dùng trong trigger | Không tự COMMIT transaction của caller; transaction thuộc statement/session |

Không dùng COMMIT trong procedure chỉ vì “procedure đã chạy xong”. Hoàn thành một lời gọi không đồng nghĩa hoàn thành transaction nghiệp vụ.

## 5. Tính nguyên tử của một API và SAVEPOINT

Caller-managed transaction không có nghĩa procedure phải để lại DML một phần khi thất bại. Một API có thể bảo đảm tính nguyên tử cho phần việc của chính nó bằng SAVEPOINT.

SAVEPOINT đánh dấu vị trí trong transaction. ROLLBACK TO SAVEPOINT hoàn tác thay đổi sau mốc đó, nhưng không kết thúc toàn transaction và không hoàn tác công việc trước mốc.

### 5.1 Ví dụ dùng savepoint bên trong API

~~~sql
CREATE OR REPLACE PROCEDURE create_order_api (
    p_customer_id IN  customers.customer_id%TYPE,
    p_order_id    OUT orders.order_id%TYPE
) AS
BEGIN
    SAVEPOINT create_order_api_sp;
    p_order_id := NULL;

    INSERT INTO orders(customer_id, status, created_at)
    VALUES (p_customer_id, 'NEW', SYSTIMESTAMP)
    RETURNING order_id INTO p_order_id;

    INSERT INTO order_audit(order_id, action_name, action_time)
    VALUES (p_order_id, 'CREATED', SYSTIMESTAMP);

EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO create_order_api_sp;
        RAISE;
END create_order_api;
/
~~~

Nếu INSERT audit thất bại, phần INSERT order sau savepoint được rollback. Caller vẫn sở hữu transaction và có thể quyết định tiếp tục với công việc trước đó hoặc rollback toàn bộ.

### 5.2 Savepoint không commit

SAVEPOINT không tạo transaction độc lập và không commit dữ liệu. Sau ROLLBACK TO:

- Transaction vẫn còn mở.
- Các thay đổi trước savepoint vẫn còn pending.
- Caller vẫn phải quyết định COMMIT hoặc ROLLBACK toàn transaction.
- Các savepoint được tạo sau savepoint mục tiêu bị xóa.

### 5.3 Tên savepoint và lời gọi lồng nhau

Tên savepoint thuộc phạm vi transaction. Nếu một procedure khác dùng lại cùng tên, savepoint cũ có thể bị thay thế. Điều này dễ xảy ra khi procedure gọi lồng nhau hoặc gọi đệ quy.

Hãy dùng tên savepoint có namespace theo package/thao tác, tránh dùng lại cùng tên trong các lời gọi lồng nhau, ghi rõ helper nào có quyền tạo savepoint, và không để procedure con COMMIT/ROLLBACK toàn transaction vì sẽ làm mất savepoint của caller.

Oracle không có lệnh RELEASE SAVEPOINT riêng. Savepoint còn hiệu lực tới khi transaction kết thúc hoặc bị thay thế/loại bỏ theo quy tắc savepoint.

### 5.4 Khi nào không cần savepoint nội bộ?

Nếu caller luôn rollback toàn transaction khi bất kỳ API nào lỗi, API có thể không cần savepoint riêng. Nhưng hợp đồng phải nói rõ rằng khi exception thoát ra, caller cần rollback toàn transaction trước khi tái sử dụng connection hoặc tiếp tục công việc.

Savepoint hữu ích khi caller muốn giữ lại phần công việc đã thực hiện trước API. Đổi lại, cần quản lý tên savepoint và phạm vi rollback có chủ đích.

### 5.5 Không dùng DDL trong business API

DDL của Oracle thường có implicit COMMIT trước và sau thao tác. Ví dụ CREATE TABLE, ALTER TABLE, DROP TABLE có thể kết thúc transaction của caller.

Vì vậy, tránh chạy DDL trong API nghiệp vụ:

~~~sql
-- Không nên đưa vào procedure xử lý đơn hàng:
EXECUTE IMMEDIATE 'CREATE TABLE temp_order_work (...)';
~~~

Nếu cần bảng tạm, hãy thiết kế object trước và dùng Global Temporary Table hoặc cơ chế staging phù hợp. Không dùng SAVEPOINT để giả định có thể rollback qua DDL.

## 6. Hợp đồng lỗi (error contract)

Error contract xác định caller có thể nhận những lỗi nào và phải diễn giải chúng ra sao.

Một hợp đồng tốt phân biệt:

1. Lỗi đầu vào/validation.
2. Trạng thái nghiệp vụ không cho phép thao tác.
3. Không tìm thấy dữ liệu hoặc dữ liệu không duy nhất.
4. Xung đột dữ liệu/constraint.
5. Lỗi đồng thời có thể retry.
6. Lỗi hạ tầng hoặc lỗi lập trình không dự kiến.

Ví dụ bảng mã lỗi public:

| Mã lỗi ứng dụng | Ý nghĩa | Hành động caller |
|---|---|---|
| -20001 | CUSTOMER_ID không hợp lệ | Sửa đầu vào |
| -20002 | Không tìm thấy khách hàng | Trả lỗi nghiệp vụ |
| -20003 | Khách hàng không hoạt động | Từ chối thao tác |
| -20004 | Đơn hàng không ở trạng thái cho phép | Đọc lại trạng thái hoặc trả conflict |
| -20005 | Request ID đã được sử dụng với nội dung khác | Từ chối request |
| ORA-08177 | Serialization conflict | Rollback và cân nhắc retry toàn transaction |
| ORA-00060 | Deadlock | Xử lý theo chính sách concurrency riêng |
| ORA-00001 | Vi phạm unique constraint | Phân biệt request trùng và dữ liệu lỗi |
| ORA-06502 | Lỗi số/chuỗi hoặc conversion trong PL/SQL | Điều tra dữ liệu và code |

Caller nên phân loại bằng mã lỗi ổn định, không dựa vào việc so khớp thông điệp lỗi tiếng Anh hoặc tiếng địa phương.

## 7. Dùng RAISE_APPLICATION_ERROR cho lỗi nghiệp vụ

PL/SQL cung cấp RAISE_APPLICATION_ERROR để phát sinh lỗi ứng dụng với mã trong khoảng -20000 đến -20999:

~~~sql
RAISE_APPLICATION_ERROR(
    -20002,
    'Customer does not exist'
);
~~~

Lỗi này được gửi về caller như một Oracle exception. Caller có thể đọc SQLCODE và SQLERRM.

### 7.1 Khai báo error code tập trung

Package có thể công khai tên exception và mã lỗi:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    e_customer_not_found EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_customer_not_found, -20002);

    PROCEDURE create_order(
        p_customer_id IN customers.customer_id%TYPE,
        p_order_id OUT orders.order_id%TYPE
    );
END order_api;
/
~~~

Caller có thể bắt exception bằng tên:

~~~sql
BEGIN
    order_api.create_order(999999, :order_id);
EXCEPTION
    WHEN order_api.e_customer_not_found THEN
        DBMS_OUTPUT.PUT_LINE('Customer is not available.');
END;
/
~~~

Việc đặt tên exception giúp code dễ đọc và tránh lặp số mã ở nhiều nơi.

### 7.2 Dùng tham số thứ ba của RAISE_APPLICATION_ERROR

Cú pháp:

~~~sql
RAISE_APPLICATION_ERROR(error_code, message, [keep_errors]);
~~~

Tham số thứ ba mặc định là FALSE. Nếu đặt TRUE, lỗi ứng dụng mới được thêm vào error stack thay vì thay thế stack hiện tại. Điều này hữu ích khi chuyển đổi một lỗi kỹ thuật thành lỗi miền nghiệp vụ nhưng vẫn muốn giữ lỗi gốc trong stack để chẩn đoán.

Ví dụ:

~~~sql
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        RAISE_APPLICATION_ERROR(
            -20005,
            'Request has already been processed',
            TRUE
        );
~~~

Chỉ chuyển đổi lỗi khi hiểu nguyên nhân. Không nên biến mọi DUP_VAL_ON_INDEX thành “request đã xử lý” nếu unique constraint có thể bị vi phạm bởi một cột khác.

## 8. Bảo toàn lỗi gốc và truyền exception

### 8.1 Dùng RAISE để ném lại lỗi hiện tại

Trong exception handler:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        -- Có thể ghi nhận thông tin chẩn đoán.
        RAISE;
END;
~~~

RAISE không có tên exception trong handler sẽ ném lại exception đang được xử lý, giữ nguyên lỗi gốc và backtrace theo cơ chế Oracle.

### 8.2 Không thay lỗi gốc bằng lỗi chung chung

Mẫu dễ gây hại:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE_APPLICATION_ERROR(
            -20099,
            'Operation failed'
        );
END;
~~~

Caller chỉ nhận mã -20099 và khó phân biệt duplicate, timeout, deadlock hay lỗi lập trình. Nếu cần chuẩn hóa lỗi, hãy chuyển đổi có chọn lọc và giữ stack gốc khi cần.

### 8.3 Không nuốt exception

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END;
~~~

Mẫu này khiến caller không biết thao tác thất bại. Nếu procedure đã thực hiện một số DML, caller có thể tiếp tục và commit dữ liệu một phần.

Chỉ bắt lỗi và không ném lại khi API thực sự định nghĩa lỗi đó là kết quả bình thường, đồng thời đã xử lý đầy đủ trạng thái và trả kết quả rõ ràng.

### 8.4 Chỉ bắt lỗi mà API có thể xử lý

Ví dụ:

~~~sql
BEGIN
    SELECT status
    INTO l_status
    FROM orders
    WHERE order_id = p_order_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20004,
            'Order does not exist'
        );
END;
~~~

Nếu chỉ SELECT một bảng và NO_DATA_FOUND có nghĩa rõ là order không tồn tại, việc chuyển đổi này hợp lý. Nếu nhiều SELECT khác nhau trong cùng block có thể phát sinh NO_DATA_FOUND, hãy tách block hoặc xử lý tại vị trí cụ thể để không gán nhầm ý nghĩa cho lỗi.

## 9. Chẩn đoán lỗi và backtrace

Các hàm hữu ích trong PL/SQL:

- SQLCODE: mã của exception đang xử lý.
- SQLERRM: thông điệp lỗi.
- DBMS_UTILITY.FORMAT_ERROR_STACK: toàn bộ error stack.
- DBMS_UTILITY.FORMAT_ERROR_BACKTRACE: vị trí phát sinh exception.
- DBMS_UTILITY.FORMAT_CALL_STACK: call stack tại thời điểm gọi.

Ví dụ:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE('SQLCODE=' || SQLCODE);
        DBMS_OUTPUT.PUT_LINE('SQLERRM=' || SQLERRM);
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_STACK
        );
        DBMS_OUTPUT.PUT_LINE(
            DBMS_UTILITY.FORMAT_ERROR_BACKTRACE
        );
        RAISE;
END;
~~~

DBMS_OUTPUT phù hợp cho ví dụ học tập hoặc debug thủ công. Trong ứng dụng production, dùng cơ chế logging có cấu trúc và không để việc ghi log làm che mất exception gốc.

### 9.1 Ghi nhận context hữu ích

Một log lỗi có thể chứa:

- Tên package/procedure.
- Request ID/correlation ID.
- Mã khách hàng hoặc mã nghiệp vụ cần thiết.
- SQLCODE và error stack.
- Error backtrace.
- Thời điểm, module/action và session context.
- Số lần retry nếu có.

Không ghi password, access token, dữ liệu thẻ hoặc thông tin cá nhân nhạy cảm vào log. Chỉ ghi bind values khi được phép và đã lọc dữ liệu.

### 9.2 Logger có thể phát sinh lỗi

Nếu procedure gọi logger trong exception handler và logger cũng lỗi, exception của logger có thể che exception gốc. Cần quyết định logger có được phép thất bại mà không che lỗi nghiệp vụ không, có dùng autonomous transaction không, và có thể ghi log ở tầng ứng dụng thay vì database không.

Không nên gọi một logger phức tạp trong exception handler nếu chưa hiểu ảnh hưởng transaction và lỗi thứ cấp.

## 10. Autonomous transaction và logging

PRAGMA AUTONOMOUS_TRANSACTION tạo một transaction độc lập với transaction chính. Nó có thể COMMIT hoặc ROLLBACK riêng mà không commit/rollback transaction caller.

Ví dụ minh họa logger độc lập:

~~~sql
CREATE OR REPLACE PROCEDURE write_error_log (
    p_request_id IN VARCHAR2,
    p_error_code IN NUMBER,
    p_message    IN VARCHAR2
) AS
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO application_error_log(
        request_id,
        error_code,
        error_message,
        logged_at
    )
    VALUES (
        p_request_id,
        p_error_code,
        p_message,
        SYSTIMESTAMP
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END write_error_log;
/
~~~

Dùng autonomous transaction có nghĩa log có thể còn lại ngay cả khi transaction nghiệp vụ rollback. Điều này có thể hữu ích cho chẩn đoán lỗi.

### 10.1 Không dùng autonomous transaction cho dữ liệu nghiệp vụ chính

Nếu ghi order detail bằng autonomous transaction rồi transaction tạo order header rollback, có thể để lại detail không có header. Dữ liệu nghiệp vụ cần nhất quán thường phải cùng transaction.

Autonomous transaction chỉ nên dùng cho dữ liệu thực sự độc lập như log chẩn đoán hoặc telemetry được định nghĩa riêng.

### 10.2 Tránh deadlock với transaction chính

Autonomous transaction không chia sẻ transaction lock với transaction chính. Nếu autonomous logger cố truy cập một hàng đang bị transaction chính khóa, nó có thể chờ hoặc deadlock theo tình huống. Logger nên ghi vào bảng độc lập và tránh phụ thuộc vào dữ liệu chưa commit của caller.

## 11. Định nghĩa hợp đồng trạng thái sau lỗi

Caller cần biết sau exception:

- DML của API đã được rollback tới savepoint chưa?
- Transaction của caller còn mở không?
- Caller có phải rollback toàn transaction không?
- Có dữ liệu đầu ra nào đáng tin cậy không?
- Có thể retry ngay không?

Một bảng hợp đồng có thể như sau:

| Kết quả | Trạng thái dữ liệu | Hành động caller |
|---|---|---|
| API return bình thường | Thay đổi của API đang pending trong transaction caller | Tiếp tục nghiệp vụ; COMMIT ở ranh giới tổng |
| Lỗi validation trước DML | Không có thay đổi từ API | Sửa input hoặc trả lỗi |
| Lỗi sau DML, API rollback về savepoint | Phần DML của API được hoàn tác; việc trước savepoint còn pending | Xử lý lỗi; quyết định tiếp tục hoặc rollback toàn transaction |
| Lỗi sau DML, API không có savepoint | Có thể còn DML một phần trong transaction | Caller cần ROLLBACK theo hợp đồng |
| Lỗi serialization | Transaction cần được rollback và chạy lại toàn nghiệp vụ | Retry có giới hạn nếu lỗi được phân loại |
| Lỗi kết nối lúc COMMIT | Kết quả commit có thể không xác định với client | Tra cứu bằng request ID/idempotency key trước khi gửi lại |

Đừng để caller phải đoán trạng thái transaction từ thông điệp lỗi.

## 12. Ví dụ hoàn chỉnh: API tạo đơn hàng

Giả sử có bảng đơn hàng:

~~~sql
CREATE TABLE orders (
    order_id     NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id  NUMBER NOT NULL,
    request_id   VARCHAR2(64) NOT NULL,
    status       VARCHAR2(20) NOT NULL,
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_orders_request UNIQUE (request_id)
);
~~~

Bảng audit:

~~~sql
CREATE TABLE order_audit (
    audit_id    NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id    NUMBER NOT NULL,
    action_name VARCHAR2(30) NOT NULL,
    action_time TIMESTAMP WITH TIME ZONE NOT NULL
);
~~~

Package specification:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    e_customer_not_found EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_customer_not_found, -20002);

    e_request_conflict EXCEPTION;
    PRAGMA EXCEPTION_INIT(e_request_conflict, -20005);

    PROCEDURE create_order(
        p_customer_id IN  customers.customer_id%TYPE,
        p_request_id  IN  orders.request_id%TYPE,
        p_order_id    OUT orders.order_id%TYPE
    );
END order_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE create_order(
        p_customer_id IN  customers.customer_id%TYPE,
        p_request_id  IN  orders.request_id%TYPE,
        p_order_id    OUT orders.order_id%TYPE
    ) AS
        l_customer_status customers.status%TYPE;
    BEGIN
        SAVEPOINT order_api_create_sp;
        p_order_id := NULL;

        IF p_customer_id IS NULL OR p_request_id IS NULL THEN
            RAISE_APPLICATION_ERROR(
                -20001,
                'Customer ID and request ID are required'
            );
        END IF;

        SELECT status
        INTO l_customer_status
        FROM customers
        WHERE customer_id = p_customer_id;

        IF l_customer_status <> 'ACTIVE' THEN
            RAISE_APPLICATION_ERROR(
                -20003,
                'Customer is not active'
            );
        END IF;

        INSERT INTO orders(
            customer_id,
            request_id,
            status,
            created_at
        )
        VALUES (
            p_customer_id,
            p_request_id,
            'NEW',
            SYSTIMESTAMP
        )
        RETURNING order_id INTO p_order_id;

        INSERT INTO order_audit(
            order_id,
            action_name,
            action_time
        )
        VALUES (
            p_order_id,
            'CREATED',
            SYSTIMESTAMP
        );

        -- Không COMMIT: caller sở hữu transaction.

    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            ROLLBACK TO order_api_create_sp;
            RAISE_APPLICATION_ERROR(
                -20002,
                'Customer does not exist'
            );

        WHEN DUP_VAL_ON_INDEX THEN
            ROLLBACK TO order_api_create_sp;
            RAISE_APPLICATION_ERROR(
                -20005,
                'Request ID already exists',
                TRUE
            );

        WHEN OTHERS THEN
            ROLLBACK TO order_api_create_sp;
            RAISE;
    END create_order;
END order_api;
/
~~~

Đây là ví dụ cấu trúc. Trong ứng dụng thật, cần xác định unique constraint nào có thể phát sinh DUP_VAL_ON_INDEX; nếu nhiều unique constraint cùng tồn tại, không thể mặc định mọi duplicate đều là request ID trùng. Cũng cần xác định xử lý NULL của CUSTOMER_STATUS, quyền truy cập, dữ liệu đầu vào và cách trả kết quả request đã tồn tại.

Caller:

~~~sql
DECLARE
    l_order_id orders.order_id%TYPE;
BEGIN
    order_api.create_order(
        p_customer_id => 101,
        p_request_id  => 'REQ-2026-0001',
        p_order_id    => l_order_id
    );

    -- Có thể gọi thêm API khác trong cùng transaction.
    -- payment_api.reserve_payment(l_order_id);

    COMMIT;
    DBMS_OUTPUT.PUT_LINE('Created order ' || l_order_id);
EXCEPTION
    WHEN order_api.e_customer_not_found THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('Customer not found');
    WHEN order_api.e_request_conflict THEN
        ROLLBACK;
        DBMS_OUTPUT.PUT_LINE('Request was already used');
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

API tạo order và audit trong cùng transaction caller. Savepoint giúp hoàn tác phần DML của API nếu có lỗi, còn caller quyết định COMMIT toàn bộ nghiệp vụ.

## 13. Idempotency và retry

Ứng dụng có thể gửi cùng request nhiều lần do timeout, retry HTTP hoặc mất kết nối. API ghi dữ liệu cần có cách nhận diện request đã được xử lý.

### 13.1 Idempotency key

Request ID ổn định cho cùng một yêu cầu và unique constraint:

~~~sql
request_id VARCHAR2(64) NOT NULL
~~~

~~~sql
CONSTRAINT uq_orders_request UNIQUE (request_id)
~~~

giúp database ngăn tạo hai order cùng request ID.

Nhưng unique violation chưa đủ để trả kết quả idempotent. API cần:

1. Xác định request ID đã tồn tại.
2. Kiểm tra payload hiện tại có giống payload đã xử lý không.
3. Nếu giống, trả lại order ID/kết quả đã có.
4. Nếu khác, trả lỗi conflict rõ ràng.

Nếu chỉ bắt DUP_VAL_ON_INDEX rồi trả “request đã tồn tại”, caller không nhận được kết quả order trước đó.

### 13.2 Retry lỗi serialization

Với ORA-08177, thường phải rollback toàn transaction và chạy lại toàn bộ nghiệp vụ trên snapshot mới. Không chỉ chạy lại câu SQL cuối cùng.

Retry nên:

- Chỉ áp dụng với lỗi được phân loại là transient.
- Có giới hạn số lần.
- Dùng exponential backoff và jitter.
- Đọc lại dữ liệu và kiểm tra nghiệp vụ sau mỗi lần bắt đầu transaction mới.
- Dùng request ID/idempotency key để tránh tác động trùng.

### 13.3 Kết quả COMMIT không xác định

Nếu connection mất ngay lúc gửi COMMIT, client có thể không biết transaction đã commit hay chưa. Không nên lập tức tạo request ID mới rồi gửi lại nghiệp vụ. Hãy dùng cùng idempotency key để truy vấn trạng thái và xác định kết quả trước khi tiếp tục.

## 14. Transaction boundary với hệ thống bên ngoài

Một database transaction không thể tự rollback email, HTTP request, message đã gửi sang broker hoặc thao tác trên hệ thống thanh toán bên ngoài.

Ví dụ không an toàn:

~~~text
BEGIN DATABASE TRANSACTION
  Insert order
  Call payment provider
  Send email
  Update inventory
COMMIT
~~~

Nếu bước cuối lỗi, rollback database không thể thu hồi email hoặc payment request đã gửi.

### 14.1 Transactional outbox

Mẫu outbox:

1. Ghi dữ liệu nghiệp vụ và một dòng outbox trong cùng database transaction.
2. COMMIT.
3. Worker riêng đọc outbox và gửi message/email.
4. Worker đánh dấu đã gửi hoặc retry theo idempotency key.

Nhờ đó, sự kiện cần gửi chỉ tồn tại khi thay đổi nghiệp vụ được commit.

### 14.2 Saga và compensation

Với quy trình gồm nhiều hệ thống, có thể dùng saga: mỗi bước có thao tác bù trừ tương ứng. Ví dụ nếu giữ tồn kho thành công nhưng thanh toán thất bại, hệ thống phát lệnh giải phóng tồn kho.

Compensation là thao tác nghiệp vụ mới, không phải database ROLLBACK. Nó có thể thất bại và cần retry/monitoring riêng.

## 15. Quyền thực thi và bảo vệ API

Package API cũng là ranh giới bảo mật.

### 15.1 Definer rights và invoker rights

Stored procedure/package Oracle mặc định thường chạy với quyền của owner (definer rights). Có thể khai báo AUTHID CURRENT_USER để dùng invoker rights:

~~~sql
CREATE OR REPLACE PACKAGE reporting_api
AUTHID CURRENT_USER
AS
    PROCEDURE show_summary;
END reporting_api;
/
~~~

Khái quát:

- Definer rights: code chạy theo quyền của schema định nghĩa chương trình, phù hợp khi muốn cấp quyền EXECUTE trên API thay vì cấp trực tiếp quyền bảng.
- Invoker rights: code chạy theo ngữ cảnh quyền của caller, phù hợp với một số thư viện tiện ích và trường hợp cần quyền caller.

Quyền thực tế còn chịu ảnh hưởng của role, direct grants, object resolution và dynamic SQL. Hãy thiết kế theo nguyên tắc least privilege và kiểm tra trên đúng cấu hình schema.

### 15.2 Không dùng dynamic SQL với tên đối tượng không kiểm soát

Nếu API nhận tên bảng/cột từ caller rồi ghép vào SQL, có thể phát sinh SQL injection hoặc truy cập object ngoài dự kiến.

Khi buộc phải dùng dynamic SQL:

- Bind giá trị dữ liệu bằng bind variables.
- Kiểm tra tên object bằng allowlist hoặc DBMS_ASSERT phù hợp.
- Không ghép trực tiếp input người dùng vào SQL text.
- Giới hạn quyền schema thực thi.

### 15.3 Partition không phải ranh giới bảo mật

Việc mỗi tenant nằm trong một partition không tự ngăn caller đọc tenant khác. API vẫn phải kiểm tra tenant context, authorization và điều kiện dữ liệu theo đúng mô hình bảo mật.

## 16. Versioning và khả năng tương thích API

Package specification là contract công khai. Thay đổi chữ ký có thể làm invalid dependent object hoặc buộc ứng dụng sửa code.

Các nguyên tắc:

- Ưu tiên thêm procedure mới thay vì đổi semantics procedure cũ.
- Không tái sử dụng error code cũ cho ý nghĩa khác.
- Giữ quy tắc NULL và transaction ổn định.
- Thay đổi OUT parameter cần đánh giá caller hiện tại.
- Không đưa cấu trúc bảng nội bộ vào public API nếu không cần.
- Kiểm tra dependent objects sau khi compile package.

Nếu cần thay đổi lớn, có thể tạo package API version mới, ví dụ ORDER_API_V2, và duy trì V1 trong thời gian chuyển đổi.

## 17. Kiểm thử API contract và transaction

Không chỉ kiểm thử trường hợp thành công. Cần kiểm tra cả trạng thái sau lỗi.

### 17.1 Kiểm thử thành công

- Đầu vào hợp lệ.
- Kết quả OUT đúng.
- Các bảng liên quan có dữ liệu pending như hợp đồng.
- Caller COMMIT và session khác nhìn thấy dữ liệu.

### 17.2 Kiểm thử lỗi trước DML

- ID không tồn tại.
- Tham số NULL.
- Trạng thái nghiệp vụ không hợp lệ.
- Caller kiểm tra mã lỗi và trạng thái transaction.

### 17.3 Kiểm thử lỗi sau DML một phần

Tạo lỗi có chủ đích ở bước audit hoặc detail:

- Xác nhận savepoint rollback phần API đã làm.
- Xác nhận dữ liệu caller tạo trước savepoint vẫn còn pending.
- Xác nhận caller có thể chọn COMMIT phần trước đó hoặc ROLLBACK toàn bộ theo nghiệp vụ.

### 17.4 Kiểm thử procedure không commit

1. Caller UPDATE một bảng trước khi gọi API.
2. Gọi API tạo dữ liệu.
3. Gọi ROLLBACK ở caller.
4. Kiểm tra từ session khác rằng cả hai thay đổi đều không còn.

Thử nghiệm này phát hiện procedure có COMMIT ngoài hợp đồng.

### 17.5 Kiểm thử nhiều API trong cùng transaction

Gọi API tạo order, giữ inventory và ghi payment reservation. Cố ý làm bước cuối lỗi. Xác nhận caller rollback toàn bộ và không còn dữ liệu một phần.

### 17.6 Kiểm thử idempotency

Gửi cùng request ID hai lần:

- Cùng payload phải trả cùng kết quả hoặc cùng order ID theo contract.
- Khác payload phải trả conflict.
- Không tạo hai order hoặc trừ tồn kho hai lần.

### 17.7 Kiểm thử quyền

Dùng schema caller chỉ có quyền EXECUTE trên package. Xác nhận caller thực hiện được thao tác hợp lệ và không thể truy cập trực tiếp bảng nếu không được cấp quyền.

## 18. Sơ đồ lựa chọn transaction boundary

~~~mermaid
flowchart TD
    A["Thiết kế procedure/package API"] --> B{"API là một phần của use case lớn?"}
    B -->|Có| C["Caller sở hữu transaction"]
    B -->|Không, API là đơn vị độc lập| D["Có thể chọn API-owned transaction"]
    C --> E{"Cần rollback riêng phần DML của API?"}
    E -->|Có| F["Tạo SAVEPOINT và rollback to savepoint khi lỗi"]
    E -->|Không| G["Quy định caller rollback toàn transaction khi lỗi"]
    F --> H["Không COMMIT trong API"]
    G --> H
    D --> I["Ghi rõ COMMIT/ROLLBACK kết thúc transaction session"]
    H --> J["Chuẩn hóa error contract"]
    I --> J
    J --> K["Kiểm thử trạng thái dữ liệu sau success và exception"]
~~~

## 19. Những lỗi thiết kế thường gặp

| Lỗi thiết kế | Hệ quả | Cách khắc phục |
|---|---|---|
| Procedure con tự COMMIT | Commit luôn công việc caller | Để caller quản lý transaction |
| Procedure con ROLLBACK toàn phần | Mất cả thay đổi caller trước khi gọi | Dùng savepoint nếu cần rollback cục bộ |
| Không nói rõ trạng thái sau exception | Caller không biết có DML một phần không | Định nghĩa error/transaction contract |
| Bắt WHEN OTHERS rồi NULL | Lỗi bị che, caller tưởng thành công | Xử lý cụ thể hoặc RAISE lại |
| Chuyển mọi lỗi thành một mã chung | Mất khả năng phân loại/retry | Dùng error taxonomy ổn định |
| Dùng message để phân loại lỗi | Message có thể thay đổi theo ngôn ngữ/version | Dựa trên SQLCODE/mã ứng dụng |
| Dùng autonomous transaction cho dữ liệu nghiệp vụ | Dữ liệu có thể tồn tại khi transaction chính rollback | Giữ dữ liệu nghiệp vụ trong cùng transaction |
| Gọi API ngoài database trước COMMIT | Side effect không thể rollback | Dùng outbox/saga |
| Retry bằng request ID mới | Có thể tạo tác động trùng | Giữ idempotency key ổn định |
| Dùng SAVEPOINT trùng tên trong lời gọi lồng nhau | Savepoint bên ngoài có thể bị thay thế | Namespace và thiết kế rõ savepoint |
| Chạy DDL trong API nghiệp vụ | Implicit commit phá transaction boundary | Chuẩn bị object trước |
| API public lộ quá nhiều bảng/record nội bộ | Khó thay đổi implementation | Giữ specification nhỏ, ổn định |

## 20. Bài thực hành tự kiểm tra

Các bài tập nên chạy trong schema thử nghiệm, với bảng và package riêng.

### Bài 1 — API caller-managed

Viết procedure INSERT một order và audit, không COMMIT. Gọi từ anonymous block, sau đó ROLLBACK. Kiểm tra từ session khác rằng không có dữ liệu mới.

### Bài 2 — COMMIT trong procedure

Tạo một procedure có COMMIT. Caller UPDATE một bảng trước khi gọi procedure rồi ROLLBACK sau lời gọi. Quan sát thay đổi nào vẫn tồn tại và giải thích transaction thuộc session.

### Bài 3 — Savepoint cục bộ

Viết API tạo header và detail. Cố ý làm INSERT detail lỗi. Dùng SAVEPOINT/ROLLBACK TO để hoàn tác phần API, rồi xác nhận thay đổi caller trước savepoint vẫn còn.

### Bài 4 — Tên savepoint lồng nhau

Viết hai procedure cùng dùng một tên savepoint. Gọi lồng nhau và quan sát ảnh hưởng khi procedure trong rollback tới savepoint. Sửa tên để tránh va chạm và ghi lại hợp đồng.

### Bài 5 — Error code

Khai báo exception public với PRAGMA EXCEPTION_INIT. Dùng RAISE_APPLICATION_ERROR để phát sinh mã lỗi. Caller bắt theo tên exception và phân loại kết quả.

### Bài 6 — Bảo toàn exception

Viết một procedure gây lỗi constraint, bắt WHEN OTHERS và RAISE lại. So sánh SQLCODE/error stack với phiên bản chuyển mọi lỗi thành một mã chung.

### Bài 7 — Error backtrace

Tạo ba tầng procedure A gọi B gọi C. C phát sinh lỗi. Ghi FORMAT_ERROR_BACKTRACE và FORMAT_CALL_STACK. Xác định nơi lỗi ban đầu xảy ra.

### Bài 8 — Autonomous logger

Viết logger autonomous chỉ ghi bảng log độc lập. Gọi logger rồi rollback transaction chính. Xác nhận log vẫn tồn tại và dữ liệu nghiệp vụ bị rollback. Giải thích vì sao không dùng mẫu này cho order detail.

### Bài 9 — Idempotency

Tạo API nhận request ID có unique constraint. Gửi cùng request hai lần và thiết kế để lần thứ hai trả kết quả trước đó. Gửi cùng ID với payload khác và trả conflict.

### Bài 10 — Kết hợp nhiều API

Gọi API order, inventory và payment reservation trong cùng transaction. Cố ý làm bước cuối lỗi rồi rollback. Xác nhận không còn dữ liệu một phần.

### Bài 11 — DDL và implicit commit

Trong schema thử nghiệm, UPDATE một hàng rồi thực hiện DDL. Thử ROLLBACK và quan sát ranh giới transaction. Giải thích vì sao không đưa DDL vào API nghiệp vụ.

### Bài 12 — Kiểm thử quyền package

Tạo schema owner và schema caller. Cấp EXECUTE trên package nhưng không cấp quyền trực tiếp trên bảng. Kiểm tra hành vi với definer rights và thử thiết kế invoker rights riêng.

## 21. Checklist thiết kế API production

**Giao diện**

- Tên procedure/function thể hiện nghiệp vụ?
- IN/OUT/IN OUT được chọn đúng mục đích?
- Kiểu dữ liệu, NULL và miền giá trị được định nghĩa?
- Package specification chỉ công khai phần cần thiết?
- Error code public có ổn định?

**Transaction**

- Ai sở hữu transaction được ghi rõ?
- Procedure có vô tình COMMIT/ROLLBACK toàn session không?
- API có cần savepoint để rollback phần DML riêng?
- Tên savepoint có thể xung đột trong lời gọi lồng nhau không?
- Có DDL hoặc implicit commit trong luồng nghiệp vụ không?
- Caller biết phải COMMIT/ROLLBACK khi thành công/lỗi?

**Lỗi**

- Validation, conflict, not found và technical error được phân biệt?
- Exception gốc được giữ khi cần?
- WHEN OTHERS có RAISE lại hoặc trả kết quả lỗi có chủ đích?
- Error backtrace và request ID có thể được ghi nhận?
- Logger có nguy cơ che exception hoặc gây deadlock không?

**Tính đúng đắn**

- API có thể để lại DML một phần sau exception không?
- OUT parameter có chỉ được sử dụng khi return bình thường?
- Retry có idempotent?
- Kết quả COMMIT không xác định được xử lý ra sao?
- Side effect ngoài database có outbox/saga phù hợp?

**Bảo mật và vận hành**

- Quyền definer/invoker được chọn có chủ đích?
- Dynamic SQL có bind values và kiểm tra object name?
- Log có loại bỏ dữ liệu nhạy cảm?
- Có kiểm thử transaction và exception trên nhiều session?
- Có kế hoạch versioning và compile dependency?

## 22. Ghi nhớ

| Chủ đề | Nguyên tắc |
|---|---|
| Package specification | Hợp đồng public của database API |
| Package body | Implementation và helper nội bộ |
| Transaction | Thuộc session/connection |
| Caller-managed | Caller quyết định COMMIT/ROLLBACK |
| API-owned | Chỉ dùng khi thao tác được định nghĩa là transaction độc lập |
| COMMIT trong procedure | Commit toàn transaction của session |
| ROLLBACK trong procedure | Rollback toàn transaction của session |
| SAVEPOINT | Tạo mốc rollback cục bộ, không commit |
| DDL | Có thể gây implicit commit, tránh trong API nghiệp vụ |
| Error contract | Mã lỗi và trạng thái sau lỗi phải rõ |
| RAISE | Ném lại exception hiện tại |
| RAISE_APPLICATION_ERROR | Phát sinh mã lỗi ứng dụng từ -20000 đến -20999 |
| Autonomous transaction | Dành cho dữ liệu thực sự độc lập như log |
| Idempotency | Cùng request không tạo tác động lặp |
| Outbox/Saga | Xử lý side effect và nhiều hệ thống |
| Definer/Invoker rights | Quyết định ngữ cảnh quyền thực thi |

Một database API đáng tin cậy phải nói rõ nó làm gì, thay đổi dữ liệu nào, transaction thuộc về ai và caller sẽ nhận trạng thái nào khi lỗi. Giữ quyền COMMIT/ROLLBACK ở đúng tầng giúp nhiều API kết hợp được trong cùng use case; dùng SAVEPOINT khi cần nguyên tử cục bộ; giữ nguyên exception gốc hoặc chuyển đổi có chọn lọc; và thiết kế idempotency cho retry. Khi các quy tắc này được ghi thành hợp đồng, ứng dụng có thể xử lý database nhất quán hơn và dễ kiểm thử hơn.
