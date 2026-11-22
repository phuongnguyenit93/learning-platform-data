# Thành phần riêng, trạng thái package và quá trình khởi tạo trong PL/SQL

Package là đơn vị tổ chức mã PL/SQL giúp gom các kiểu dữ liệu, hằng số, biến, cursor, exception, procedure và function có liên quan vào cùng một namespace. Một package thường có hai phần: **package specification** công bố những thành phần mà chương trình khác được phép sử dụng, còn **package body** chứa phần triển khai và các thành phần riêng chỉ dùng bên trong package.

Package còn có thể giữ **trạng thái (package state)** trong bộ nhớ của một database session. Biến package, hằng, cursor và các trạng thái liên quan có thể tồn tại qua nhiều lần gọi procedure trong cùng session. Khi package được tham chiếu lần đầu trong session, Oracle khởi tạo package instance đó; phần initialization trong package body được thực thi theo vòng đời của instance. Hiểu rõ cơ chế này rất quan trọng trong ứng dụng dùng connection pool, bởi nhiều request có thể lần lượt sử dụng cùng một database session.

Bài học thuộc chủ đề **Thủ tục và package** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Vai trò và cấu trúc package specification/package body.
- Thành phần public và private, phạm vi truy cập và đóng gói.
- Package state và lifetime theo database session.
- Thời điểm package được khởi tạo và thứ tự khởi tạo.
- Initialization section trong package body.
- Tác động của connection pool, package invalidation và recompile.
- Package stateless, trạng thái session và SERIALLY_REUSABLE.
- Tra cứu package metadata, xử lý lỗi và bài thực hành SQL.

## 1. Package là gì?

Package là một schema object PL/SQL chứa các thành phần liên quan. Thay vì tạo nhiều procedure/function độc lập ở cấp schema, ta có thể nhóm chúng theo một chủ đề nghiệp vụ.

Ví dụ package quản lý đơn hàng có thể chứa:

- Hằng số biểu diễn trạng thái đơn hàng.
- Kiểu record và collection dùng trong nghiệp vụ.
- Exception riêng của module.
- Procedure tạo đơn, xác nhận đơn hoặc hủy đơn.
- Function tính tổng tiền.
- Biến private dùng lưu cache hoặc cấu hình theo session.

Package tạo ra namespace, giúp lời gọi có cấu trúc như `order_api.create_order` hoặc `order_api.calculate_total`.

### Hai thành phần chính

~~~text
ORDER_API
|
+-- Package specification
|   +-- Public types
|   +-- Public constants and variables
|   +-- Public cursors
|   +-- Public exceptions
|   +-- Procedure/function declarations
|
+-- Package body
    +-- Private types, variables, cursors
    +-- Private procedures/functions
    +-- Implementations of public subprograms
    +-- Optional initialization section
~~~

Package specification là giao diện (interface) của package. Package body là phần triển khai (implementation). Chương trình bên ngoài chỉ được truy cập thành phần được công bố trong specification, với điều kiện có quyền phù hợp.

### Package không phải một transaction

Package state nằm trong bộ nhớ session, không phải một transaction hay bảng lưu trữ bền vững. Gọi procedure trong package không tự tạo transaction độc lập; DML vẫn tham gia transaction hiện tại của session trừ khi code có COMMIT/ROLLBACK hoặc cơ chế riêng. Kết thúc transaction không tự xóa package variables.

## 2. Package specification: giao diện public

Package specification khai báo các thành phần mà caller có thể tham chiếu. Nó không nhất thiết chứa phần thân procedure/function; các chương trình con được khai báo ở đây thường có phần triển khai trong package body.

Cú pháp:

~~~sql
CREATE OR REPLACE PACKAGE package_name AS
    -- Public declarations
END package_name;
/
~~~

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    c_default_currency CONSTANT VARCHAR2(3) := 'VND';

    e_invalid_order EXCEPTION;

    PROCEDURE confirm_order(
        p_order_id IN NUMBER
    );

    FUNCTION order_total(
        p_order_id IN NUMBER
    ) RETURN NUMBER;
END order_api;
/
~~~

Caller có thể tham chiếu thành phần public bằng tên package:

~~~sql
BEGIN
    order_api.confirm_order(1001);
    DBMS_OUTPUT.PUT_LINE(order_api.order_total(1001));
    DBMS_OUTPUT.PUT_LINE(order_api.c_default_currency);
END;
/
~~~

Tên package là qualifier cho public members. Điều này tránh xung đột với tên biến hoặc procedure ở schema khác và thể hiện rõ API mà chương trình đang dùng.

### Những gì có thể khai báo trong specification?

Specification có thể công bố:

- Hằng số và biến public.
- Kiểu dữ liệu PL/SQL như RECORD, TABLE, VARRAY và subtype.
- Cursor specification.
- Exception.
- Procedure và function signatures.
- Pragma hoặc các khai báo được PL/SQL hỗ trợ trong package spec theo phiên bản.

Không đưa chi tiết triển khai không cần thiết vào specification. Mỗi thay đổi public spec có thể ảnh hưởng caller và khiến các object phụ thuộc cần recompile.

### Package specification chỉ chứa dữ liệu công khai

Nếu package chỉ công bố hằng, kiểu hoặc biến mà không có subprogram cần triển khai, có thể không cần package body:

~~~sql
CREATE OR REPLACE PACKAGE app_constants AS
    c_max_attempts CONSTANT PLS_INTEGER := 5;
    c_default_language CONSTANT VARCHAR2(5) := 'vi';
END app_constants;
/
~~~

Package này không có procedure/function body và không có initialization section riêng. Các giá trị hằng được khởi tạo theo khai báo của package.

## 3. Package body: triển khai và thành phần private

Package body chứa phần thân của procedure/function đã công bố, cùng các khai báo chỉ cần bên trong package.

Cú pháp:

~~~sql
CREATE OR REPLACE PACKAGE BODY package_name AS
    -- Private declarations

    -- Public subprogram implementations

    -- Optional initialization section
BEGIN
    -- Initialization statements
END package_name;
/
~~~

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    FUNCTION is_valid_order(p_order_id NUMBER)
        RETURN BOOLEAN
    IS
        l_count PLS_INTEGER;
    BEGIN
        SELECT COUNT(*)
        INTO l_count
        FROM orders
        WHERE order_id = p_order_id;

        RETURN l_count = 1;
    END is_valid_order;

    PROCEDURE confirm_order(p_order_id IN NUMBER) IS
    BEGIN
        IF NOT is_valid_order(p_order_id) THEN
            RAISE e_invalid_order;
        END IF;

        UPDATE orders
        SET status = 'CONFIRMED'
        WHERE order_id = p_order_id;
    END confirm_order;

    FUNCTION order_total(p_order_id IN NUMBER)
        RETURN NUMBER
    IS
        l_total NUMBER;
    BEGIN
        SELECT NVL(SUM(quantity * unit_price), 0)
        INTO l_total
        FROM order_lines
        WHERE order_id = p_order_id;

        RETURN l_total;
    END order_total;
END order_api;
/
~~~

`is_valid_order` chỉ được định nghĩa trong package body, không khai báo ở specification, nên là private helper. Caller không thể gọi `order_api.is_valid_order` trực tiếp. Procedure `confirm_order` có thể gọi helper vì cả hai cùng thuộc package body.

### Public và private khác nhau thế nào?

| Thành phần | Khai báo ở đâu? | Ai truy cập được? |
| --- | --- | --- |
| Public constant/variable/type | Package specification | Caller có quyền truy cập và code bên trong package |
| Public procedure/function | Signature trong specification, body trong package body | Caller có quyền EXECUTE và code bên trong package |
| Private variable/type/cursor | Chỉ package body | Code trong package body |
| Private procedure/function | Chỉ package body | Code trong package body |
| Initialization section | Cuối package body | Oracle chạy khi khởi tạo package instance; caller không gọi trực tiếp |

Private member giúp ẩn chi tiết triển khai và cho phép thay đổi nội bộ mà không làm thay đổi giao diện public. Đây là nguyên tắc encapsulation (đóng gói).

### Không thể gọi private member từ bên ngoài

Giả sử body có:

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE write_internal_log(p_message VARCHAR2) IS
    BEGIN
        INSERT INTO app_log(message, created_at)
        VALUES (p_message, SYSTIMESTAMP);
    END write_internal_log;
END order_api;
/
~~~

Caller không thể thực hiện `order_api.write_internal_log(...)` vì procedure không được công bố trong specification. Nếu cần caller sử dụng chức năng, hãy công bố một public procedure phù hợp và giữ helper private.

## 4. Thứ tự khai báo trong package body

PL/SQL cần biết khai báo trước khi một subprogram gọi tới tên đó, trừ trường hợp dùng forward declaration. Vì vậy, private helper thường được khai báo trước subprogram public sử dụng nó.

~~~sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE write_internal_log(p_message VARCHAR2) IS
    BEGIN
        INSERT INTO app_log(message, created_at)
        VALUES (p_message, SYSTIMESTAMP);
    END write_internal_log;

    PROCEDURE confirm_order(p_order_id IN NUMBER) IS
    BEGIN
        UPDATE orders
        SET status = 'CONFIRMED'
        WHERE order_id = p_order_id;

        write_internal_log('Confirmed order ' || p_order_id);
    END confirm_order;
END order_api;
/
~~~

Nếu hai private subprogram gọi lẫn nhau và không thể sắp xếp theo thứ tự khai báo đơn giản, có thể dùng forward declaration:

~~~sql
CREATE OR REPLACE PACKAGE BODY sample_pkg AS
    PROCEDURE step_b(p_value NUMBER);

    PROCEDURE step_a(p_value NUMBER) IS
    BEGIN
        IF p_value > 0 THEN
            step_b(p_value - 1);
        END IF;
    END step_a;

    PROCEDURE step_b(p_value NUMBER) IS
    BEGIN
        IF p_value > 0 THEN
            step_a(p_value - 1);
        END IF;
    END step_b;
END sample_pkg;
/
~~~

Forward declaration cung cấp chữ ký trước để compiler biết subprogram sẽ được định nghĩa sau đó.

## 5. Package state là gì?

Package state là giá trị runtime của các biến, hằng, cursor và trạng thái liên quan thuộc package instance trong một session. Với package có state, Oracle duy trì trạng thái này qua nhiều lần gọi package trong cùng database session.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE request_counter AS
    PROCEDURE increment;
    FUNCTION current_value RETURN PLS_INTEGER;
END request_counter;
/

CREATE OR REPLACE PACKAGE BODY request_counter AS
    g_count PLS_INTEGER := 0;

    PROCEDURE increment IS
    BEGIN
        g_count := g_count + 1;
    END increment;

    FUNCTION current_value RETURN PLS_INTEGER IS
    BEGIN
        RETURN g_count;
    END current_value;
END request_counter;
/
~~~

G_COUNT là private package variable. Trong cùng session:

~~~sql
BEGIN
    request_counter.increment;
    request_counter.increment;
    DBMS_OUTPUT.PUT_LINE(request_counter.current_value);
END;
/
~~~

Kết quả là 2. Gọi tiếp `request_counter.increment` trong cùng session sẽ làm giá trị tăng tiếp. Nếu một session khác gọi package lần đầu, nó có package state riêng, khởi tạo từ 0.

### Package state không được chia sẻ giữa các session

Giả sử Session A thực hiện hai lần increment, còn Session B thực hiện một lần:

~~~text
Session A                         Session B
-------------------------         -------------------------
request_counter.g_count = 0       request_counter.g_count = 0
increment                         increment
increment
current_value = 2                 current_value = 1
~~~

Hai session không nhìn thấy biến package của nhau. Package variable không phải global variable của toàn database; nó thuộc package instance gắn với session.

### Package state khác dữ liệu trong bảng

- Package variable nằm trong bộ nhớ session, không tự lưu bền vững xuống datafile.
- COMMIT/ROLLBACK không tự đặt lại giá trị package variable.
- Session kết thúc thì package state của session đó bị giải phóng.
- Session khác không tự nhìn thấy package state.
- Muốn chia sẻ dữ liệu bền vững giữa session, dùng bảng hoặc cơ chế lưu trữ phù hợp.

Không dùng package variable làm nơi lưu trạng thái nghiệp vụ cần tồn tại sau khi session kết thúc hoặc cần nhất quán giữa nhiều session.

## 6. Quá trình khởi tạo package

Package có state được khởi tạo khi session lần đầu tham chiếu package đó. Việc tạo package bằng CREATE PACKAGE/CREATE PACKAGE BODY chỉ biên dịch và lưu định nghĩa schema object; nó không chạy initialization section cho mọi session.

Khi một session lần đầu tham chiếu một thành phần package, Oracle tạo package instance cho session đó. Các khai báo biến được khởi tạo theo giá trị mặc định/biểu thức khai báo; sau đó phần initialization tùy chọn ở cuối package body được thực thi. Package state được giữ cho các lần gọi tiếp theo trong cùng session, trừ khi bị giải phóng hoặc invalidated theo cơ chế của Oracle.

### Initialization section

Initialization section là phần BEGIN ... END ở cuối package body, sau tất cả khai báo và định nghĩa subprogram. Nó không phải một procedure public và caller không gọi trực tiếp.

~~~sql
CREATE OR REPLACE PACKAGE session_settings AS
    FUNCTION current_region RETURN VARCHAR2;
    PROCEDURE set_region(p_region IN VARCHAR2);
END session_settings;
/

CREATE OR REPLACE PACKAGE BODY session_settings AS
    g_region VARCHAR2(10) := 'APAC';
    g_initialized_at TIMESTAMP;

    FUNCTION current_region RETURN VARCHAR2 IS
    BEGIN
        RETURN g_region;
    END current_region;

    PROCEDURE set_region(p_region IN VARCHAR2) IS
    BEGIN
        g_region := p_region;
    END set_region;

BEGIN
    g_initialized_at := SYSTIMESTAMP;
    DBMS_OUTPUT.PUT_LINE('session_settings initialized');
END session_settings;
/
~~~

Trong session mới, lần đầu gọi:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(session_settings.current_region);
END;
/
~~~

Oracle khởi tạo package instance và chạy initialization section trước khi thực hiện lời gọi cần package. Những lần gọi tiếp theo trong cùng session không chạy lại initialization section; giá trị g_region giữ trạng thái đã thay đổi.

### Khi nào initialization section chạy?

- Khi session lần đầu tham chiếu package instance, chẳng hạn gọi public procedure/function hoặc tham chiếu public variable.
- Chạy một lần cho package instance trong session đó.
- Không chạy lại sau mỗi lần gọi procedure trong package.
- Không chạy tại thời điểm CREATE/COMPILE package cho tất cả session.
- Một session khác có package instance riêng và sẽ khởi tạo riêng khi lần đầu tham chiếu.

Nếu package state bị invalidated/discarded, session có thể cần tạo lại state và thực hiện initialization khi package được sử dụng lại. Ứng dụng cần xử lý các lỗi invalidation có thể xuất hiện trong quá trình triển khai/recompile.

### Thứ tự khởi tạo

Khi package được instantiate, các biến package được khởi tạo theo khai báo của chúng; phần initialization section chạy sau khi các khai báo package đã được thiết lập. Vì vậy initialization section có thể đọc/ghi biến package:

~~~sql
CREATE OR REPLACE PACKAGE init_demo AS
    FUNCTION effective_count RETURN PLS_INTEGER;
END init_demo;
/

CREATE OR REPLACE PACKAGE BODY init_demo AS
    g_start_count PLS_INTEGER := 10;
    g_effective_count PLS_INTEGER;

    FUNCTION effective_count RETURN PLS_INTEGER IS
    BEGIN
        RETURN g_effective_count;
    END effective_count;
BEGIN
    g_effective_count := g_start_count + 5;
END init_demo;
/
~~~

Sau khi package được khởi tạo, g_effective_count là 15 trong package state của session. Thứ tự giữa các khai báo và phụ thuộc của chúng nên được giữ đơn giản, tránh tạo chuỗi initialization phức tạp giữa nhiều package.

Lần tham chiếu đầu tiên có thể thực hiện qua public function:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(init_demo.effective_count);
END;
/
~~~

### Khởi tạo có thể thực hiện SQL

Initialization section có thể chạy các câu lệnh PL/SQL, bao gồm truy vấn dữ liệu để nạp cấu hình vào package state:

~~~sql
CREATE OR REPLACE PACKAGE runtime_config AS
    FUNCTION tax_rate RETURN NUMBER;
END runtime_config;
/

CREATE OR REPLACE PACKAGE BODY runtime_config AS
    g_tax_rate NUMBER;

    FUNCTION tax_rate RETURN NUMBER IS
    BEGIN
        RETURN g_tax_rate;
    END tax_rate;
BEGIN
    SELECT config_number
    INTO g_tax_rate
    FROM application_config
    WHERE config_key = 'TAX_RATE';
END runtime_config;
/
~~~

Ví dụ này giả định bảng APPLICATION_CONFIG có đúng một hàng cho khóa TAX_RATE. Nếu không có hàng, NO_DATA_FOUND sẽ xảy ra; nếu có nhiều hơn một hàng, TOO_MANY_ROWS xảy ra và việc khởi tạo thất bại. Initialization có thể thêm latency vào request đầu tiên và tạo phụ thuộc vào bảng/configuration; cần cân nhắc cache, giá trị mặc định và cách xử lý lỗi.

Caller kích hoạt initialization khi tham chiếu function public:

~~~sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(runtime_config.tax_rate);
END;
/
~~~

Không nên đặt công việc nặng, gọi dịch vụ ngoài hoặc logic có tác dụng phụ khó kiểm soát trong initialization section. Việc khởi tạo diễn ra ngầm khi package được tham chiếu, nên một lời gọi tưởng như chỉ đọc hằng số cũng có thể kích hoạt phần khởi tạo nếu package body có initialization section.

### Package chỉ có specification

Package chỉ chứa khai báo không cần package body thì không có initialization section. Giá trị khởi tạo của public variables/constants vẫn gắn với package instance theo khai báo, nhưng không có block BEGIN riêng trong body để chạy.

## 7. Package state và connection pool

Package state thuộc database session, trong khi connection pool tái sử dụng session cho nhiều request ứng dụng. Hai khái niệm này tạo ra rủi ro nếu package giữ dữ liệu request mà không được reset.

Ví dụ:

~~~sql
CREATE OR REPLACE PACKAGE request_context AS
    g_user_id NUMBER;
    g_tenant_id NUMBER;

    PROCEDURE set_context(
        p_user_id IN NUMBER,
        p_tenant_id IN NUMBER
    );

    PROCEDURE clear_context;
END request_context;
/

CREATE OR REPLACE PACKAGE BODY request_context AS
    PROCEDURE set_context(
        p_user_id IN NUMBER,
        p_tenant_id IN NUMBER
    ) IS
    BEGIN
        g_user_id := p_user_id;
        g_tenant_id := p_tenant_id;
    END set_context;

    PROCEDURE clear_context IS
    BEGIN
        g_user_id := NULL;
        g_tenant_id := NULL;
    END clear_context;
END request_context;
/
~~~

Giả sử request A mượn connection/session 1, đặt user_id = 100 và tenant_id = 10, rồi trả connection về pool. Nếu request B sau đó nhận đúng session 1 mà không reset package state, B có thể nhìn thấy giá trị của request A. Đây là lỗi rò rỉ trạng thái giữa request.

### Quy tắc khi dùng package state trong pool

- Đặt state ở đầu mỗi request, trước khi gọi logic nghiệp vụ cần nó.
- Reset state trong finally/cleanup path trước khi trả connection về pool.
- Đảm bảo lỗi giữa request không bỏ qua bước reset.
- Không xem việc COMMIT/ROLLBACK là cách xóa package state.
- Nếu có thể, truyền context qua tham số rõ ràng thay vì giữ state ngầm.
- Kiểm tra chính sách pool về session reuse và session reset.

Ví dụ tầng ứng dụng:

~~~java
try (Connection connection = dataSource.getConnection()) {
    try {
        setRequestContext(connection, userId, tenantId);
        processRequest(connection);
        connection.commit();
    } catch (Exception ex) {
        connection.rollback();
        throw ex;
    } finally {
        clearRequestContext(connection);
    }
}
~~~

Đây là mẫu khái niệm; code thực tế cần bảo đảm cleanup được gọi trước khi connection được trả pool và xử lý trường hợp chính thao tác reset cũng lỗi. Không giả định close connection vật lý sẽ xóa state nếu pool chỉ trả session về hàng đợi.

### Package state có thể tồn tại lâu hơn request

Một session trong pool có thể phục vụ hàng trăm request theo thời gian. Do đó package variable có thể tồn tại lâu hơn một request và giữ dữ liệu cũ. Hãy phân biệt:

- Request lifetime: thời gian xử lý một yêu cầu ứng dụng.
- Session lifetime: thời gian database session còn tồn tại trong pool.
- Package state lifetime: gắn với package instance trong session, thường kéo dài qua nhiều request dùng lại session.

Nếu dữ liệu chỉ có ý nghĩa trong một request, ưu tiên tham số hoặc context có cơ chế reset rõ ràng.

## 8. Recompile, invalidation và package state đang tồn tại

Package là schema object có thể bị recompile khi DBA triển khai phiên bản mới, thay đổi specification/body hoặc thay đổi object phụ thuộc. Khi package được thay đổi, package state trong các session đang dùng package có thể bị invalidated/discarded. Điều này đặc biệt quan trọng với package giữ cache hoặc trạng thái request.

Các lỗi Oracle có thể gặp trong quá trình invalidation/recompile gồm:

| Mã lỗi | Ý nghĩa thường gặp |
| --- | --- |
| ORA-04061 | Existing state of package has been invalidated. |
| ORA-04065 | Not executed, altered or dropped stored procedure/package. |
| ORA-04068 | Existing state of packages has been discarded. |
| ORA-06508 | PL/SQL could not find program unit being called. |

Thông báo cụ thể phụ thuộc cách package bị thay đổi, dependency và thời điểm session gọi lại package.

### Vì sao session đang chạy có thể bị ảnh hưởng?

Giả sử session A đã gọi package và package instance giữ giá trị cache. DBA triển khai CREATE OR REPLACE PACKAGE BODY. Định nghĩa trong dictionary thay đổi; trạng thái cũ trong session có thể không còn phù hợp với code mới. Khi session A gọi package tiếp, Oracle có thể báo package state đã bị invalidated/discarded và cần khởi tạo lại.

Không nên coi package state là cache bền vững qua mọi lần triển khai. Nếu dữ liệu cache phải sống qua recompile hoặc cần đồng bộ giữa session, lưu ở một tầng có vòng đời phù hợp hơn.

### Recompile body và specification

- Thay đổi package body thường ảnh hưởng triển khai nội bộ, nhưng vẫn có thể làm package state trong session bị invalidated.
- Thay đổi package specification có thể làm các object phụ thuộc cần recompile vì giao diện public đã thay đổi.
- Thay đổi object mà package phụ thuộc cũng có thể invalidated package.
- Recompile không đồng nghĩa mọi session lập tức chạy lại initialization ngay tại thời điểm DBA thực hiện DDL; việc khởi tạo lại gắn với lần sử dụng sau khi state bị discard.

Hãy triển khai package theo quy trình có kiểm soát, theo dõi invalid objects và chuẩn bị cho ứng dụng xử lý lỗi ở lần gọi sau deploy.

### Retry sau ORA-04068 cần thận trọng

Một số ứng dụng xử lý ORA-04068 bằng cách bỏ trạng thái cũ, lấy lại connection hoặc retry lời gọi. Tuy nhiên, không được tự động replay một request không idempotent nếu chưa xác định DML của lần gọi trước có thể đã thực hiện đến đâu. Phải phân biệt lỗi package state với lỗi transaction và thiết kế retry ở ranh giới nghiệp vụ có thể lặp an toàn.

## 9. Reset package state

Package state thông thường giữ qua nhiều lần gọi trong session. Khi cần xóa trạng thái, có thể thiết kế procedure reset trong package hoặc dùng API quản lý session ở tầng ứng dụng.

Ví dụ procedure reset state:

~~~sql
CREATE OR REPLACE PACKAGE request_context AS
    PROCEDURE set_context(
        p_user_id IN NUMBER,
        p_tenant_id IN NUMBER
    );
    PROCEDURE clear_context;
    FUNCTION current_user_id RETURN NUMBER;
END request_context;
/

CREATE OR REPLACE PACKAGE BODY request_context AS
    g_user_id NUMBER;
    g_tenant_id NUMBER;

    PROCEDURE set_context(
        p_user_id IN NUMBER,
        p_tenant_id IN NUMBER
    ) IS
    BEGIN
        g_user_id := p_user_id;
        g_tenant_id := p_tenant_id;
    END set_context;

    PROCEDURE clear_context IS
    BEGIN
        g_user_id := NULL;
        g_tenant_id := NULL;
    END clear_context;

    FUNCTION current_user_id RETURN NUMBER IS
    BEGIN
        RETURN g_user_id;
    END current_user_id;
END request_context;
/
~~~

Caller gọi CLEAR_CONTEXT trong cleanup path trước khi trả session về pool. Procedure reset chỉ cần xóa các state mà package sở hữu; nó không nhất thiết reset package khác trong session.

### DBMS_SESSION.MODIFY_PACKAGE_STATE

Oracle cung cấp DBMS_SESSION.MODIFY_PACKAGE_STATE để thay đổi cách quản lý package state của session:

- DBMS_SESSION.REINITIALIZE: package state được tái khởi tạo khi package được tham chiếu lại theo cơ chế của API.
- DBMS_SESSION.FREE_ALL_RESOURCES: giải phóng tài nguyên package state; package được khởi tạo lại khi cần dùng.

Ví dụ khái niệm:

~~~sql
BEGIN
    DBMS_SESSION.MODIFY_PACKAGE_STATE(
        DBMS_SESSION.REINITIALIZE
    );
END;
/
~~~

API này ảnh hưởng package state trong session, vì vậy không gọi tùy tiện ở giữa một đơn vị công việc đang cần giữ state. Kiểm tra tài liệu Oracle đúng phiên bản và quy ước của connection pool trước khi áp dụng.

### DBMS_SESSION.RESET_PACKAGE

Một số hệ thống cũ có thể dùng DBMS_SESSION.RESET_PACKAGE để reset package state. Với code mới, nên xem xét DBMS_SESSION.MODIFY_PACKAGE_STATE và API session reset do pool cung cấp. Cả hai đều tác động tới trạng thái package của session; không xem đây là thay thế cho COMMIT/ROLLBACK.

### Reset phải bao phủ mọi đường đi

Nếu chỉ reset state khi request thành công, exception có thể để lại dữ liệu cũ trong session pool. Cleanup cần chạy cả khi thành công lẫn thất bại, và phải được thực hiện trước khi session được cấp cho request khác.

## 10. Package SERIALLY_REUSABLE

Thông thường, package state tồn tại trong session qua nhiều lần gọi. Với package được đánh dấu SERIALLY_REUSABLE, Oracle chỉ giữ trạng thái trong phạm vi một server call; khi server call kết thúc, package work area được giải phóng và có thể được tái sử dụng. Lần gọi sau sẽ tạo/khởi tạo trạng thái mới.

Khai báo pragma trong package specification và package body:

~~~sql
CREATE OR REPLACE PACKAGE batch_helpers AS
    PRAGMA SERIALLY_REUSABLE;
    PROCEDURE increment;
    FUNCTION current_value RETURN PLS_INTEGER;
END batch_helpers;
/

CREATE OR REPLACE PACKAGE BODY batch_helpers AS
    PRAGMA SERIALLY_REUSABLE;

    g_count PLS_INTEGER := 0;

    PROCEDURE increment IS
    BEGIN
        g_count := g_count + 1;
    END increment;

    FUNCTION current_value RETURN PLS_INTEGER IS
    BEGIN
        RETURN g_count;
    END current_value;
END batch_helpers;
/
~~~

Nếu một server call thực hiện:

~~~sql
BEGIN
    batch_helpers.increment;
    batch_helpers.increment;
    DBMS_OUTPUT.PUT_LINE(batch_helpers.current_value);
END;
/
~~~

Giá trị trong call đó là 2. Một server call riêng tiếp theo bắt đầu với package state mới, thay vì tiếp tục từ 2.

### Khi nào cân nhắc SERIALLY_REUSABLE?

- Package giữ dữ liệu tạm chỉ cần trong một server call.
- Ứng dụng có nhiều session đồng thời và package state dài hạn gây áp lực bộ nhớ session.
- Không cần giữ biến package giữa các lần gọi từ client.

Không dùng pragma này nếu logic cần duy trì state giữa nhiều round-trip của client. Ví dụ ứng dụng gọi procedure A ở một call, sau đó gọi procedure B ở call kế tiếp và mong B nhìn thấy biến package do A đặt; với SERIALLY_REUSABLE, giả định đó không còn đúng.

SERIALLY_REUSABLE thay đổi semantics lifetime, không phải một tùy chọn tối ưu vô hại. Kiểm tra phiên bản Oracle, cách ứng dụng gọi server và mọi package phụ thuộc trước khi áp dụng.

## 11. Thiết kế package state an toàn

### Giữ biến thay đổi ở private nếu caller không cần truy cập trực tiếp

Tránh công bố biến mutable chỉ để caller đọc/ghi trực tiếp:

~~~sql
CREATE OR REPLACE PACKAGE app_session AS
    g_current_user_id NUMBER;
END app_session;
/
~~~

Mọi caller có thể thay đổi giá trị theo quyền truy cập package, khiến khó kiểm soát ai đặt state và khi nào state được reset. Thường tốt hơn khi giữ biến private trong body và cung cấp API:

~~~sql
CREATE OR REPLACE PACKAGE app_session AS
    PROCEDURE set_user(p_user_id IN NUMBER);
    FUNCTION current_user RETURN NUMBER;
    PROCEDURE clear_user;
END app_session;
/
~~~

API cho phép kiểm tra đầu vào, ghi log, reset state và thay đổi cách lưu trữ mà không buộc caller phụ thuộc vào biến cụ thể.

### Package state không thay thế tham số

Nếu một giá trị chỉ được dùng trong một lời gọi, truyền nó qua tham số thường rõ ràng hơn:

~~~sql
order_api.confirm_order(
    p_order_id => 1001,
    p_actor_id => 500
);
~~~

Trạng thái ngầm làm procedure phụ thuộc vào thứ tự gọi và state còn sót trong session. Tham số làm dependency hiển thị ngay trong chữ ký chương trình.

### Package initialization không phải nơi lưu cấu hình cần cập nhật tức thời

Nếu initialization section đọc cấu hình từ bảng rồi lưu vào biến package, giá trị đó là một snapshot trong session. Khi DBA cập nhật bảng cấu hình, package state đã khởi tạo ở session khác không tự đổi theo. Cần cơ chế refresh, TTL/cache invalidation hoặc đọc lại từ bảng nếu yêu cầu thay đổi phải có hiệu lực ngay.

### Tránh khởi tạo phụ thuộc vòng tròn giữa các package

Nếu package A initialization gọi B, trong khi B initialization lại tham chiếu A, việc khởi tạo có thể tạo phụ thuộc khó dự đoán và lỗi runtime. Giữ initialization nhẹ, không gọi chéo package không cần thiết; chuyển logic cần phối hợp sang procedure được gọi tường minh sau khi các package đã sẵn sàng.

## 12. Tra cứu package trong data dictionary

Oracle cung cấp các view USER_ để xem package thuộc schema hiện tại.

### Trạng thái PACKAGE và PACKAGE BODY

~~~sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY object_name, object_type;
~~~

STATUS cho biết object VALID hay INVALID. Package specification và package body là hai object metadata riêng.

### Xem lỗi biên dịch

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY name, type, sequence;
~~~

USER_ERRORS hiển thị lỗi/warning biên dịch cho object trong schema hiện tại. Nếu package INVALID, kiểm tra lỗi trước khi thử gọi lại.

### Xem source

~~~sql
SELECT name,
       type,
       line,
       text
FROM user_source
WHERE name = 'REQUEST_COUNTER'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY type, line;
~~~

### Xem dependency

~~~sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type,
       dependency_type
FROM user_dependencies
WHERE name = 'ORDER_API'
ORDER BY referenced_owner, referenced_name;
~~~

Các USER_ views chỉ hiển thị object thuộc schema hiện tại. Dùng ALL_ views để xem object mà user có quyền truy cập hoặc DBA_ views khi có quyền quản trị. Với package ở schema khác, cần qualify owner và có quyền thích hợp.

### Recompile package

Có thể recompile package specification hoặc body:

~~~sql
ALTER PACKAGE request_counter COMPILE;
ALTER PACKAGE request_counter COMPILE BODY;
~~~

Recompile không sửa nội dung source; nó yêu cầu Oracle biên dịch lại object. Nếu dependency chưa hợp lệ hoặc quyền không đủ, object có thể vẫn INVALID. Sau recompile, kiểm tra USER_OBJECTS và USER_ERRORS. Việc recompile package đang có session sử dụng có thể ảnh hưởng package state trong các session đó.

## 13. Xử lý lỗi trong quá trình khởi tạo package

Initialization section chạy ngầm khi package instance được tạo. Nếu một câu lệnh trong phần này thất bại, lời gọi đầu tiên tham chiếu package có thể nhận exception thay vì đi vào procedure/function mà caller mong đợi.

Các nguyên nhân thường gặp:

- Truy vấn cấu hình không trả hàng hoặc trả nhiều hàng.
- Thiếu quyền trên bảng/view mà package đọc.
- Object phụ thuộc chưa tồn tại hoặc đang INVALID.
- Giá trị cấu hình không hợp lệ khiến phép chuyển đổi/khởi tạo biến thất bại.
- Initialization gọi package khác đang có lỗi hoặc phụ thuộc vòng tròn.

### Giữ initialization đơn giản

Một initialization section tốt thường:

- Thiết lập các biến package về trạng thái mặc định rõ ràng.
- Nạp một lượng cấu hình nhỏ, ổn định và có quy tắc khi không tìm thấy.
- Tránh DML hoặc tác dụng phụ không cần thiết.
- Không giữ transaction mở hoặc tự COMMIT chỉ để khởi tạo package.
- Không thực hiện công việc lâu khiến request đầu tiên bị chậm bất ngờ.

Ví dụ có xử lý cấu hình thiếu:

~~~sql
CREATE OR REPLACE PACKAGE runtime_config AS
    FUNCTION tax_rate RETURN NUMBER;
END runtime_config;
/

CREATE OR REPLACE PACKAGE BODY runtime_config AS
    g_tax_rate NUMBER := 0.08;

    FUNCTION tax_rate RETURN NUMBER IS
    BEGIN
        RETURN g_tax_rate;
    END tax_rate;
BEGIN
    BEGIN
        SELECT config_number
        INTO g_tax_rate
        FROM application_config
        WHERE config_key = 'TAX_RATE';
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            NULL; -- Giữ giá trị mặc định đã khai báo.
    END;
END runtime_config;
/
~~~

Ví dụ này vẫn cần package specification được tạo trước và cần quy tắc rõ về giá trị mặc định. Không nên bắt mọi lỗi bằng WHEN OTHERS rồi bỏ qua; lỗi quyền, dữ liệu trùng hoặc lỗi hệ thống phải được thông báo và xử lý đúng.

Khi gọi `runtime_config.tax_rate`, package khởi tạo và nạp cấu hình; nếu không tìm thấy hàng, giá trị mặc định 0.08 được giữ lại.

### Initialization và transaction

Nếu initialization section chạy DML, các thay đổi đó tham gia transaction của session trừ khi code dùng autonomous transaction hoặc cơ chế khác. Package initialization không tự tạo transaction độc lập và không tự commit. Đây là một lý do nữa để tránh DML trong initialization nếu không thực sự cần.

### Initialization không phải constructor được gọi mỗi lần

Không dùng initialization section để thực hiện logic phải chạy cho từng request hoặc từng lần gọi procedure. Nó chạy khi package instance được khởi tạo, không chạy lại mỗi lần public procedure được gọi. Logic cần lặp lại nên được đặt trong procedure/function tường minh.

## 14. Bài thực hành: package private state và initialization

Thực hiện trong schema học tập có quyền CREATE PROCEDURE và quota phù hợp. Các lệnh CREATE OR REPLACE là DDL và có thể implicit commit transaction đang mở.

### Bước 1: tạo package specification

~~~sql
CREATE OR REPLACE PACKAGE lab_session_state AS
    PROCEDURE increment;
    FUNCTION current_count RETURN PLS_INTEGER;
    FUNCTION initialized_at RETURN TIMESTAMP;
    PROCEDURE reset_count;
END lab_session_state;
/
~~~

Specification chỉ công bố API. Người gọi không nhìn thấy trực tiếp biến private.

### Bước 2: tạo package body và initialization section

~~~sql
CREATE OR REPLACE PACKAGE BODY lab_session_state AS
    g_count PLS_INTEGER := 0;
    g_initialized_at TIMESTAMP;

    PROCEDURE increment IS
    BEGIN
        g_count := g_count + 1;
    END increment;

    FUNCTION current_count RETURN PLS_INTEGER IS
    BEGIN
        RETURN g_count;
    END current_count;

    FUNCTION initialized_at RETURN TIMESTAMP IS
    BEGIN
        RETURN g_initialized_at;
    END initialized_at;

    PROCEDURE reset_count IS
    BEGIN
        g_count := 0;
    END reset_count;

BEGIN
    g_initialized_at := SYSTIMESTAMP;
    DBMS_OUTPUT.PUT_LINE('lab_session_state initialized');
END lab_session_state;
/
~~~

Biến G_COUNT và G_INITIALIZED_AT là private vì chỉ khai báo trong body. Initialization section đặt timestamp và in thông báo khi package instance được khởi tạo.

### Bước 3: kiểm tra nhiều lần gọi trong cùng session

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Initial count = ' || lab_session_state.current_count
    );

    lab_session_state.increment;
    lab_session_state.increment;

    DBMS_OUTPUT.PUT_LINE(
        'Current count = ' || lab_session_state.current_count
    );

    DBMS_OUTPUT.PUT_LINE(
        'Initialized at = ' ||
        TO_CHAR(lab_session_state.initialized_at, 'YYYY-MM-DD HH24:MI:SS.FF')
    );
END;
/
~~~

Thông báo initialized xuất hiện ở lần tham chiếu đầu tiên trong session. Giá trị count ban đầu là 0, sau hai lần increment là 2.

Chạy lại block trong cùng session. Initialization section không chạy lại; count vẫn giữ giá trị 2 trước khi block tiếp tục increment.

### Bước 4: thử session thứ hai

Mở một database session khác và chạy:

~~~sql
SET SERVEROUTPUT ON;

BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Session B count = ' || lab_session_state.current_count
    );
    lab_session_state.increment;
    DBMS_OUTPUT.PUT_LINE(
        'Session B count = ' || lab_session_state.current_count
    );
END;
/
~~~

Session B thấy initialization message riêng và count bắt đầu từ 0, dù Session A đã tăng count lên 2 hoặc cao hơn. Điều này chứng minh package state được giữ theo session.

### Bước 5: reset biến package

Trong Session A:

~~~sql
BEGIN
    lab_session_state.reset_count;
    DBMS_OUTPUT.PUT_LINE(lab_session_state.current_count);
END;
/
~~~

Giá trị count trở về 0, nhưng timestamp initialized_at không thay đổi vì reset_count chỉ đặt lại g_count. Reset một biến package không đồng nghĩa khởi tạo lại toàn bộ package instance.

### Bước 6: xem metadata

~~~sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'LAB_SESSION_STATE'
ORDER BY object_type;

SELECT name, type, line, text
FROM user_errors
WHERE name = 'LAB_SESSION_STATE'
ORDER BY type, sequence;
~~~

Hai object PACKAGE và PACKAGE BODY cần ở trạng thái VALID; USER_ERRORS không nên có lỗi biên dịch.

### Bước 7: dọn package

~~~sql
DROP PACKAGE lab_session_state;
~~~

DROP PACKAGE xóa package specification và body. Chỉ chạy sau khi đã hoàn thành lab và không cần giữ object. DDL có implicit commit.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Caller không gọi được helper | Helper chỉ có trong package body | Công bố API public nếu caller thực sự cần chức năng. |
| Package body không biên dịch | Thiếu implementation cho public subprogram hoặc sai signature | Đối chiếu package spec/body và USER_ERRORS. |
| Initialization message xuất hiện ở lần gọi đầu | Package instance vừa được khởi tạo trong session | Đây là hành vi bình thường; không mong nó chạy mỗi lần gọi. |
| Session khác thấy giá trị package khác | Package state riêng theo session | Dùng bảng/context chia sẻ nếu cần dữ liệu chung giữa session. |
| Request sau thấy user/tenant của request trước | Connection pool tái sử dụng session có package state cũ | Set/reset state ở mọi request và cleanup trước khi trả connection. |
| Package state mất sau deploy | Recompile/invalidation đã discard state | Không dùng package state làm cache bền vững; xử lý lỗi invalidation và khởi tạo lại. |
| ORA-04068 sau khi package thay đổi | State package cũ bị discard | Xử lý ở tầng ứng dụng, retry chỉ khi request an toàn/idempotent. |
| Request đầu tiên chậm | Initialization section chạy truy vấn hoặc công việc nặng | Giảm logic khởi tạo, nạp dữ liệu có kiểm soát hoặc lazy-load khi cần. |
| Package không compile do dependency | Object phụ thuộc INVALID hoặc quyền thiếu | Kiểm tra USER_ERRORS, USER_DEPENDENCIES và grants. |
| State mất giữa hai server call với SERIALLY_REUSABLE | Package state chỉ tồn tại trong phạm vi server call | Không dùng pragma nếu cần giữ state giữa round-trip. |
| COMMIT không reset biến package | Transaction và package state có vòng đời riêng | Gọi reset API/procedure hoặc kết thúc session theo thiết kế. |

## 16. Câu hỏi tự kiểm tra

1. **Package có những phần chính nào?** Package specification và package body.
2. **Specification dùng để làm gì?** Công bố giao diện public của package.
3. **Private member được khai báo ở đâu?** Trong package body và không xuất hiện trong specification.
4. **Caller có gọi được private procedure không?** Không; caller chỉ gọi thành phần được công bố và có quyền phù hợp.
5. **Package body có bắt buộc không?** Không phải lúc nào cũng cần; package chỉ có khai báo không cần implementation có thể không có body.
6. **Package state là gì?** Trạng thái runtime của package instance trong một database session.
7. **Package state có chia sẻ giữa các session không?** Không; mỗi session có state riêng.
8. **Package được khởi tạo khi nào?** Khi session lần đầu tham chiếu package instance.
9. **Initialization section chạy khi nào?** Một lần khi package instance được khởi tạo trong session.
10. **Initialization section nằm ở đâu?** Cuối package body, sau phần khai báo và các subprogram.
11. **CREATE PACKAGE có chạy initialization cho mọi session không?** Không; nó tạo/biên dịch object, initialization chạy khi từng session tham chiếu package.
12. **COMMIT có xóa package state không?** Không; transaction và package state độc lập.
13. **Vì sao connection pool có thể gây rò rỉ package state giữa request?** Nhiều request có thể dùng lại cùng session.
14. **Làm sao reset package state cho request?** Gọi procedure reset hoặc API session reset trong cleanup path trước khi trả connection về pool.
15. **ORA-04068 thường liên quan tới điều gì?** Package state đã bị discard, thường sau invalidation/recompile.
16. **SERIALLY_REUSABLE thay đổi điều gì?** Package state chỉ tồn tại trong phạm vi server call thay vì qua nhiều call trong session.
17. **Khi nào nên giữ biến private?** Khi caller không cần đọc/ghi trực tiếp và state thuộc chi tiết triển khai.
18. **Vì sao initialization section nên nhẹ?** Vì nó chạy ngầm ở lần tham chiếu đầu và có thể làm request đầu tiên chậm hoặc thất bại.

Package specification xác định giao diện public; package body giữ phần triển khai và state private. Package instance được khởi tạo khi session lần đầu tham chiếu package, rồi giữ state qua các lần gọi trong session. Initialization section chạy một lần cho instance đó. Vì connection pool tái sử dụng session, ứng dụng phải quản lý state theo request và reset trước khi trả connection. Recompile có thể invalidated package state; SERIALLY_REUSABLE rút ngắn lifetime state xuống một server call và chỉ phù hợp khi logic không cần giữ state giữa các lần gọi.
