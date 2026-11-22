# Virtual Private Database, application context và DBMS_RLS trong Oracle

## 1. VPD giải quyết bài toán gì?

Trong một database có nhiều đơn vị nghiệp vụ hoặc nhiều khách hàng dùng chung bảng, ứng dụng thường cần giới hạn mỗi người chỉ nhìn thấy những hàng thuộc phạm vi được phép. Ví dụ, người dùng của tenant A chỉ được xem đơn hàng tenant A; nhân viên chi nhánh Bắc chỉ được truy cập dữ liệu chi nhánh Bắc; nhân viên nhân sự chỉ được xem hồ sơ trong phạm vi tổ chức được giao.

Nếu chỉ viết điều kiện lọc trong từng câu SQL, một câu truy vấn bị quên điều kiện có thể làm lộ dữ liệu. **Virtual Private Database (VPD)** đưa điều kiện bảo mật xuống database: Oracle tự bổ sung predicate vào câu SQL khi truy cập object đã gắn policy.

VPD thường được gọi là row-level security hoặc fine-grained access control (FGAC). Thành phần chính:
- **Application context:** giữ các thuộc tính bảo mật của session, chẳng hạn tenant, user, region hoặc role nghiệp vụ.
- **Policy function:** tạo predicate SQL dựa trên context và object đang được truy cập.
- **`DBMS_RLS`:** package quản trị policy, gắn policy vào table/view và điều khiển vòng đời policy.
- **Database optimizer/execution engine:** áp dụng predicate như một phần của câu SQL.

Ví dụ, ứng dụng chạy:

```sql
SELECT order_id, customer_id, amount
FROM app.orders;
```

Nếu policy tạo predicate `tenant_id = ...`, Oracle xử lý truy vấn theo phạm vi tenant hiện tại mà ứng dụng không cần tự nối thêm điều kiện ở từng câu SQL.

VPD là một lớp bảo vệ quan trọng cho dữ liệu dùng chung. Tuy nhiên, policy chỉ an toàn khi context được thiết lập từ danh tính đã xác thực, predicate được thiết kế fail-closed và các tài khoản có quyền bypass được kiểm soát.

Bài học thuộc chương **Bảo mật** trong module **Database Engine Relational Oracle**, tập trung vào Virtual Private Database, application context và `DBMS_RLS`.

## 2. Mô hình dữ liệu nhiều tenant

Giả sử một ứng dụng quản lý đơn hàng dùng chung bảng cho nhiều tenant:

```sql
CREATE TABLE app.orders (
    order_id      NUMBER PRIMARY KEY,
    tenant_id     NUMBER NOT NULL,
    customer_id   NUMBER NOT NULL,
    order_date    DATE NOT NULL,
    status        VARCHAR2(20) NOT NULL,
    amount        NUMBER(12,2) NOT NULL
);
```

Mỗi hàng có `TENANT_ID` để xác định chủ sở hữu dữ liệu. Nếu tenant A có ID 10 và tenant B có ID 20, truy vấn của tenant A chỉ được trả về hàng có `tenant_id = 10`.

Nếu ứng dụng tự viết:

```sql
SELECT order_id, customer_id, amount
FROM app.orders
WHERE tenant_id = :tenant_id;
```

thì mọi đường truy cập phải nhớ truyền đúng bind variable. Một báo cáo, stored procedure hoặc câu SQL mới có thể quên điều kiện. Người dùng có thể thử sửa bind value để đọc tenant khác nếu ứng dụng không kiểm tra quyền.

VPD đặt điều kiện ở database object, nhờ đó policy được áp dụng cho các câu SQL thuộc phạm vi policy, kể cả khi câu SQL không tự viết predicate tenant.

### 2.1. Nguyên tắc tenant isolation

- Mọi hàng phải có tenant key hợp lệ.
- Tenant key không được lấy trực tiếp từ input chưa xác thực.
- Policy phải chặn truy cập khi context thiếu hoặc không hợp lệ.
- Tài khoản ứng dụng không được có quyền bypass policy.
- Mọi đường truy cập tới dữ liệu phải được kiểm tra, kể cả view, procedure, job và báo cáo.
- Có kiểm thử chéo tenant để chứng minh tenant A không thể đọc hoặc sửa dữ liệu tenant B.

VPD không tự tạo tenant model. Nó thực thi quy tắc được thiết kế từ mô hình danh tính và dữ liệu của ứng dụng.

## 3. Cách VPD hoạt động

Khi một session thực thi câu SQL trên object có VPD policy, Oracle gọi policy function theo loại policy và trạng thái cursor/context. Function trả về một chuỗi predicate SQL. Oracle gắn predicate đó vào câu lệnh trước khi tối ưu và thực thi.

Luồng khái quát:

```text
Người dùng đăng nhập
        |
        v
Ứng dụng xác thực danh tính
        |
        v
Trusted package thiết lập application context
        |
        v
Session truy vấn APP.ORDERS
        |
        v
Oracle tìm VPD policy gắn với object
        |
        v
DBMS_RLS policy function đọc context
        |
        v
Trả về predicate, ví dụ tenant_id = ...
        |
        v
Oracle áp dụng predicate vào SQL
        |
        v
Optimizer tạo plan và trả dữ liệu được phép
```

### 3.1. Predicate được áp dụng ở database

Giả sử policy trả về:

```sql
tenant_id = TO_NUMBER(SYS_CONTEXT('APP_CTX', 'TENANT_ID'))
```

Truy vấn ứng dụng:

```sql
SELECT *
FROM app.orders
WHERE status = 'OPEN';
```

được xử lý về mặt logic như có thêm điều kiện tenant:

```sql
SELECT *
FROM app.orders
WHERE status = 'OPEN'
  AND tenant_id = TO_NUMBER(SYS_CONTEXT('APP_CTX', 'TENANT_ID'));
```

Đây là mô tả logic để hiểu policy. Oracle quản lý việc áp predicate trong quá trình parse/optimization; không nên dựa vào việc SQL text mà ứng dụng gửi phải hiện nguyên văn điều kiện được thêm.

### 3.2. VPD áp dụng cho những loại statement nào?

Policy có thể được cấu hình cho các loại statement như:
- `SELECT`
- `INSERT`
- `UPDATE`
- `DELETE`
- Một số thao tác index hoặc statement khác theo release và API hỗ trợ.

Khi tạo policy, khai báo `statement_types` rõ ràng để policy bảo vệ đúng các thao tác cần thiết. Không giả định policy `SELECT` tự động bảo vệ cả DML.

### 3.3. VPD và quyền object là hai lớp khác nhau

VPD lọc những hàng mà user được nhìn thấy hoặc thao tác. Nó không thay thế quyền `SELECT`, `INSERT`, `UPDATE`, `DELETE` trên object.

User phải có quyền object cần thiết trước khi thực thi SQL. Sau đó VPD giới hạn tập hàng trong phạm vi quyền đó.

## 4. Application context là gì?

Application context là tập thuộc tính session được database lưu và truy cập qua `SYS_CONTEXT`. Ví dụ namespace `APP_CTX` có thể chứa:
- `TENANT_ID`
- `APP_USER_ID`
- `REGION_ID`
- `BUSINESS_UNIT`
- `ACCESS_LEVEL`

Đọc context:

```sql
SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID') AS tenant_id
FROM dual;
```

`SYS_CONTEXT` trả về giá trị ký tự. Khi dùng với cột NUMBER, cần chuyển kiểu rõ ràng hoặc bảo đảm phép so sánh có semantics phù hợp.

### 4.1. Namespace và attribute

- **Namespace:** nhóm context, ví dụ `APP_CTX`.
- **Attribute:** tên thuộc tính, ví dụ `TENANT_ID`.
- **Value:** giá trị được thiết lập trong session.

Context là trạng thái session, không phải bảng lưu profile người dùng. Giá trị context có thể được thay đổi trong vòng đời session thông qua package được chỉ định khi tạo secure application context.

### 4.2. Secure application context

Secure application context được tạo bằng `CREATE CONTEXT ... USING package`. Chỉ package tin cậy được chỉ định mới có thể thiết lập thuộc tính context trong namespace đó thông qua `DBMS_SESSION.SET_CONTEXT`.

Ví dụ:

```sql
CREATE CONTEXT app_ctx USING sec.app_context_pkg;
```

`SEC.APP_CONTEXT_PKG` là package được tin cậy để thiết lập context. Việc tạo context cần quyền hệ thống phù hợp, thường do security administrator/DBA thực hiện.

Không dùng context namespace không được bảo vệ cho quyết định phân quyền. Giá trị context chỉ an toàn khi con đường thiết lập giá trị đã được kiểm soát.

## 5. Thiết kế context từ danh tính đã xác thực

Điểm quan trọng nhất của VPD là nguồn gốc context. Nếu người dùng có thể tự đặt `TENANT_ID = 20`, policy sẽ thực thi đúng predicate nhưng bảo vệ sai tenant.

### 5.1. Không tin tenant ID do client gửi

Không nên tạo thủ tục đơn giản như:

```sql
-- Thiết kế không an toàn: caller tự chọn tenant.
PROCEDURE set_tenant(p_tenant_id NUMBER) IS
BEGIN
    DBMS_SESSION.SET_CONTEXT(
        'APP_CTX',
        'TENANT_ID',
        TO_CHAR(p_tenant_id)
    );
END;
```

Nếu ứng dụng có thể gọi thủ tục với bất kỳ số nào, người dùng có thể yêu cầu tenant khác. Secure application context chỉ giới hạn package được quyền set context; nó không tự chứng minh package đã xác thực đúng người dùng.

### 5.2. Mô hình DB principal riêng cho tenant

Một cách đơn giản là mỗi tenant hoặc nhóm tin cậy dùng một database principal riêng và database có bảng ánh xạ principal sang tenant. Ví dụ:

```sql
CREATE TABLE sec.db_principal_tenant (
    db_username VARCHAR2(128) PRIMARY KEY,
    tenant_id   NUMBER NOT NULL
);
```

Package trusted có thể lấy tenant từ principal đã đăng nhập:

```sql
CREATE OR REPLACE PACKAGE sec.app_context_pkg
AUTHID DEFINER
AS
    PROCEDURE set_for_session;
    PROCEDURE clear_for_session;
END;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY sec.app_context_pkg
AS
    PROCEDURE set_for_session
    IS
        l_tenant_id sec.db_principal_tenant.tenant_id%TYPE;
    BEGIN
        SELECT tenant_id
        INTO l_tenant_id
        FROM sec.db_principal_tenant
        WHERE db_username = SYS_CONTEXT('USERENV', 'SESSION_USER');

        DBMS_SESSION.SET_CONTEXT(
            'APP_CTX',
            'TENANT_ID',
            TO_CHAR(l_tenant_id)
        );
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
            RAISE_APPLICATION_ERROR(
                -20001,
                'No tenant mapping for authenticated database principal'
            );
    END set_for_session;

    PROCEDURE clear_for_session
    IS
    BEGIN
        DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
    END clear_for_session;
END;
/
```

Đây là ví dụ cho mô hình database principal có ánh xạ tenant rõ ràng. Tài khoản ứng dụng cần được cấp `EXECUTE` trên package theo đúng phạm vi:

```sql
GRANT EXECUTE ON sec.app_context_pkg TO order_app;
```

Tạo context bằng package tin cậy:

```sql
CREATE CONTEXT app_ctx USING sec.app_context_pkg;
```

### 5.3. Ứng dụng dùng chung một service account

Nhiều hệ thống multi-tenant dùng một database account chung cho tất cả request. Trong trường hợp đó, `SESSION_USER` chỉ nhận diện service account, không phân biệt end user hoặc tenant.

Không thể suy ra tenant an toàn chỉ từ một service account dùng chung. Cần một cơ chế xác thực tin cậy giữa application tier và database, ví dụ:
- Proxy authentication hoặc danh tính kết nối được database xác thực.
- Một assertion/token được ký và xác minh bằng cơ chế tin cậy.
- Một package chỉ chấp nhận danh tính đã được xác thực từ middleware tin cậy, với quyền gọi và đường truyền được kiểm soát.
- Kiến trúc identity riêng cho từng workload/tenant nếu phù hợp.

Không coi `CLIENT_IDENTIFIER` hoặc một giá trị tenant do client tự gửi là bằng chứng xác thực. Các thuộc tính này hữu ích để truy vết, nhưng nếu caller tự đặt được thì không thể dùng một mình làm căn cứ phân quyền.

### 5.4. Fail closed

Nếu không xác định được tenant, package nên không thiết lập context và policy phải trả predicate không cho phép hàng nào, ví dụ `1=0`.

Không trả predicate rỗng, `1=1` hoặc bỏ policy khi context thiếu. Trong bảo mật dữ liệu, lỗi xác thực phải dẫn đến từ chối truy cập.

## 6. Policy function cho VPD

Policy function là function được `DBMS_RLS` gọi để lấy predicate. Signature cơ bản nhận schema và tên object, trả về chuỗi predicate SQL.

Ví dụ:

```sql
CREATE OR REPLACE FUNCTION sec.orders_tenant_predicate(
    object_schema IN VARCHAR2,
    object_name   IN VARCHAR2
)
RETURN VARCHAR2
AUTHID DEFINER
AS
    l_tenant_id VARCHAR2(128);
BEGIN
    l_tenant_id := SYS_CONTEXT('APP_CTX', 'TENANT_ID');

    IF l_tenant_id IS NULL THEN
        RETURN '1=0';
    END IF;

    RETURN
        'tenant_id = TO_NUMBER(SYS_CONTEXT(''APP_CTX'', ''TENANT_ID''))';
END;
/
```

Policy function không cần nối giá trị tenant vào chuỗi predicate. Predicate tham chiếu `SYS_CONTEXT` để lấy giá trị trong session khi câu SQL được xử lý.

### 6.1. Vì sao trả `1=0` khi context thiếu?

Nếu function trả `1=1` khi context null, mọi hàng có thể trở nên nhìn thấy. Nếu function trả chuỗi rỗng hoặc không có predicate, kết quả có thể làm policy mất tác dụng hoặc gây lỗi theo semantics API.

`1=0` là predicate luôn sai, do đó không hàng nào được trả về. Đây là cách fail-closed đơn giản cho ví dụ tenant.

### 6.2. Không nối trực tiếp context vào predicate

Tránh:

```sql
-- Không nên tạo SQL predicate bằng cách nối giá trị không tin cậy.
RETURN 'tenant_id = ' || l_tenant_id;
```

Nếu giá trị có thể bị thao túng, nối chuỗi có thể tạo SQL injection hoặc lỗi chuyển kiểu. Dùng biểu thức `SYS_CONTEXT` trong predicate hoặc chỉ xây dựng predicate từ giá trị đã được xác thực, kiểm tra kiểu và mã hóa đúng.

### 6.3. Policy function cần đơn giản và ổn định

Một policy function tốt:
- Chỉ đọc context và metadata cần thiết.
- Trả predicate ngắn, rõ ràng.
- Không thực hiện DDL hoặc transaction control.
- Tránh truy vấn bảng phức tạp cho mỗi lần parse nếu có thể.
- Không gọi dịch vụ từ xa trong policy function.
- Không ghi secret hoặc dữ liệu nhạy cảm ra log.
- Xử lý context thiếu theo fail-closed.

`object_schema` và `object_name` là tham số do Oracle truyền cho function. Có thể dùng chúng nếu một function phục vụ nhiều object, nhưng không lấy tên object từ input ứng dụng để nối vào SQL.

## 7. Gắn policy bằng DBMS_RLS.ADD_POLICY

`DBMS_RLS` là package PL/SQL dùng để quản lý VPD policy. Ví dụ gắn tenant policy vào bảng `APP.ORDERS`:

```sql
BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema   => 'APP',
        object_name     => 'ORDERS',
        policy_name     => 'ORDERS_TENANT_POLICY',
        function_schema => 'SEC',
        policy_function => 'ORDERS_TENANT_PREDICATE',
        statement_types => 'SELECT,INSERT,UPDATE,DELETE',
        update_check    => TRUE,
        enable          => TRUE
    );
END;
/
```

Câu lệnh được chạy bởi schema/administrator có quyền quản trị policy và object phù hợp. Xác nhận quyền `EXECUTE` trên `DBMS_RLS` và các quyền quản trị cần thiết theo release.

### 7.1. Các tham số quan trọng

| Tham số | Vai trò |
|---|---|
| `object_schema` | Schema sở hữu table/view |
| `object_name` | Tên table/view gắn policy |
| `policy_name` | Tên policy |
| `function_schema` | Schema sở hữu policy function |
| `policy_function` | Function trả predicate |
| `statement_types` | Các loại statement được bảo vệ |
| `update_check` | Kiểm tra giá trị hàng sau INSERT/UPDATE theo predicate |
| `enable` | Bật policy ngay khi tạo |
| `policy_type` | Kiểu đánh giá/caching policy |
| `sec_relevant_cols` | Các cột nhạy cảm cho column-level VPD |
| `sec_relevant_cols_opt` | Tùy chọn xử lý hàng/cột cho column-level policy |

Không cần khai báo mọi tham số cho mọi policy. Chọn cấu hình dựa trên semantics cần bảo vệ và tài liệu Oracle của phiên bản triển khai.

### 7.2. SELECT

Với `SELECT`, predicate giới hạn hàng được trả về:

```sql
SELECT order_id, tenant_id, amount
FROM app.orders;
```

Nếu context có tenant 10, user chỉ thấy các hàng tenant 10 theo policy.

### 7.3. UPDATE và DELETE

Policy predicate giới hạn hàng mà câu lệnh có thể tìm thấy và thay đổi. Một câu:

```sql
UPDATE app.orders
SET status = 'CLOSED'
WHERE order_id = 500;
```

chỉ tác động hàng trong phạm vi tenant hiện tại. Nếu order 500 thuộc tenant khác, câu lệnh không thể cập nhật hàng đó thông qua policy.

### 7.4. INSERT và update_check

`update_check => TRUE` yêu cầu Oracle kiểm tra hàng mới sau `INSERT` hoặc `UPDATE` có thỏa predicate policy hay không. Điều này ngăn ứng dụng tenant 10 chèn một hàng mang `tenant_id = 20` hoặc đổi tenant key sang tenant khác.

Nếu policy chỉ lọc hàng đang tồn tại mà không kiểm tra giá trị mới, user có thể bị giới hạn khi đọc nhưng vẫn tạo dữ liệu ngoài phạm vi được phép. Với tenant isolation, kiểm tra hàng mới là yêu cầu quan trọng.

### 7.5. Cột tenant phải được bảo vệ

Không để ứng dụng tùy ý sửa `TENANT_ID`. Ngoài VPD, cân nhắc:
- Không cấp quyền UPDATE trên tenant key.
- Dùng trigger/constraint hoặc API ghi dữ liệu phù hợp.
- Thiết lập tenant ID từ context trong stored procedure.
- Kiểm thử INSERT/UPDATE với tenant ID giả mạo.

VPD và quyền cột bổ sung cho nhau; không nên dựa duy nhất vào form hoặc UI để khóa tenant key.

## 8. Các loại policy và caching

Policy type quyết định khi nào Oracle gọi policy function và cách predicate được tái sử dụng. Chọn sai loại có thể gây predicate cũ được dùng sau khi context thay đổi.

Các loại thường gặp trong `DBMS_RLS`:

| Policy type | Ý nghĩa khái quát | Khi cân nhắc |
|---|---|---|
| `DYNAMIC` | Đánh giá policy function theo vòng đời parse của statement; là lựa chọn mặc định phổ biến | Khi predicate phụ thuộc session/request và cần ưu tiên tính đúng |
| `STATIC` | Predicate được cache vì policy function luôn trả cùng predicate cho object | Chỉ khi predicate thực sự không phụ thuộc user/session/context |
| `SHARED_STATIC` | Cho phép chia sẻ static policy function/predicate trong các object phù hợp | Khi cùng logic/predicate được dùng rộng rãi và ổn định |
| `CONTEXT_SENSITIVE` | Theo dõi application context được khai báo và làm mới policy khi context liên quan thay đổi | Khi predicate phụ thuộc context session |
| `SHARED_CONTEXT_SENSITIVE` | Chia sẻ policy context-sensitive trong các trường hợp phù hợp | Khi có cùng policy logic/context trên nhiều object |

Chi tiết cache, invalidation và điều kiện hỗ trợ cần xác nhận theo phiên bản Oracle. Nếu không chắc, dùng mặc định `DYNAMIC` trước, đo overhead, sau đó mới tối ưu caching policy.

### 8.1. DYNAMIC

Đây là lựa chọn đơn giản khi policy phụ thuộc context. Function được đánh giá trong quá trình parse theo semantics của dynamic policy. Câu SQL parse lại sẽ nhận predicate dựa trên trạng thái context hiện tại.

Không hiểu “dynamic” là function được chạy lại cho từng hàng. Policy function tạo predicate; predicate được optimizer đưa vào SQL plan.

### 8.2. STATIC

Chỉ dùng khi predicate không thay đổi theo session, user hoặc context. Nếu static policy trả tenant predicate phụ thuộc session, cache predicate có thể làm sai ranh giới dữ liệu.

Static policy cần được refresh khi logic hoặc dữ liệu liên quan thay đổi theo cách Oracle yêu cầu.

### 8.3. CONTEXT_SENSITIVE

Dùng khi predicate phụ thuộc application context. Khi tạo policy, có thể khai báo namespace và attribute mà policy phụ thuộc:

```sql
BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema   => 'APP',
        object_name     => 'ORDERS',
        policy_name     => 'ORDERS_TENANT_CTX_POLICY',
        function_schema => 'SEC',
        policy_function => 'ORDERS_TENANT_PREDICATE',
        statement_types => 'SELECT,INSERT,UPDATE,DELETE',
        update_check    => TRUE,
        enable          => TRUE,
        policy_type     => DBMS_RLS.CONTEXT_SENSITIVE,
        namespace       => 'APP_CTX',
        attribute       => 'TENANT_ID'
    );
END;
/
```

Đây là ví dụ thay thế policy dynamic ở phần trước, không tạo hai policy tenant giống nhau trên cùng bảng. Khi dùng context-sensitive policy, khai báo đúng các context attribute ảnh hưởng predicate và kiểm thử việc thay đổi context trong cùng session.

### 8.4. Refresh và thay đổi policy

Khi thay đổi function hoặc cần làm mới policy cache, DBA có thể dùng các thủ tục quản lý tương ứng như `DBMS_RLS.REFRESH_POLICY`, `ENABLE_POLICY` hoặc `DISABLE_POLICY`. Cú pháp và phạm vi refresh cần kiểm tra theo release.

Không chỉnh policy function rồi giả định mọi cursor đang mở lập tức dùng predicate mới. Có kế hoạch invalidate/refresh phù hợp và kiểm tra session/cursor sau thay đổi.

## 9. Column-level VPD với sec_relevant_cols

VPD có thể giới hạn theo cột nhạy cảm. Ví dụ, một nhân viên có thể xem thông tin chung của mọi nhân viên nhưng chỉ được xem lương của nhóm mình phụ trách.

Khi tạo policy có thể chỉ định:

```sql
sec_relevant_cols => 'SALARY,SSN'
```

Khi query tham chiếu các cột được đánh dấu, policy sẽ được áp dụng theo cấu hình column-level.

### 9.1. Hành vi mặc định

Với column-level VPD, khi câu SQL tham chiếu cột nhạy cảm, predicate có thể lọc hàng để chỉ trả về các hàng thỏa policy. Điều này hữu ích khi việc xem cột đó phải bị hạn chế cả ở cấp hàng.

### 9.2. ALL_ROWS

Tùy chọn `DBMS_RLS.ALL_ROWS` cho phép trả về tất cả hàng, đồng thời các giá trị ở cột nhạy cảm được trả thành NULL cho hàng không thỏa predicate. Ví dụ:

```sql
BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema         => 'HR',
        object_name           => 'EMPLOYEES',
        policy_name           => 'EMP_SALARY_MASK_POLICY',
        function_schema       => 'SEC',
        policy_function       => 'EMP_SALARY_PREDICATE',
        statement_types       => 'SELECT',
        sec_relevant_cols     => 'SALARY',
        sec_relevant_cols_opt => DBMS_RLS.ALL_ROWS
    );
END;
/
```

Ví dụ minh họa: user có thể thấy tên và phòng ban của mọi nhân viên, nhưng `SALARY` chỉ có giá trị đối với các hàng mà predicate cho phép. Cần xác nhận semantics cụ thể trên phiên bản và kiểm tra ứng dụng có xử lý SQL NULL đúng hay không.

### 9.3. Column-level VPD không thay thế Data Redaction

- VPD row-level lọc hàng theo predicate.
- Column-level VPD có thể lọc hàng khi cột nhạy cảm được truy vấn hoặc trả NULL cho cột đó theo `ALL_ROWS`.
- Data Redaction che/mask giá trị cột trong kết quả theo policy.
- Object privileges quyết định user có được truy cập object/cột hay không.

Chọn công nghệ theo yêu cầu. Nếu cần ẩn một phần giá trị thẻ hoặc số định danh trong kết quả, Data Redaction có thể phù hợp hơn; nếu cần tenant isolation, VPD row predicate là trọng tâm.

## 10. Nhiều policy trên cùng object

Một table có thể cần nhiều quy tắc:
- Tenant isolation.
- Region restriction.
- Department restriction.
- Hạn chế truy cập dữ liệu theo trạng thái.
- Điều kiện nghiệp vụ riêng cho nhóm người dùng.

Khi có nhiều policy, phải hiểu cách Oracle kết hợp predicate và policy group theo cấu hình. Thông thường các predicate policy áp dụng trên object được kết hợp theo logic AND. Điều này có nghĩa hàng phải thỏa tất cả điều kiện được áp dụng.

Ví dụ:
- `tenant_id = 10`
- `region_id IN (1,2)`
- `status <> 'RESTRICTED'`

Kết quả chỉ chứa hàng thỏa cả ba predicate.

Nếu nghiệp vụ cần logic OR hoặc policy theo nhóm ứng dụng, thiết kế policy group/driving application context theo tài liệu `DBMS_RLS` thay vì giả định nhiều policy tự động tạo OR.

Không tạo nhiều policy trùng lặp hoặc mâu thuẫn mà không kiểm tra predicate cuối cùng và execution plan.

## 11. Quản lý policy bằng DBMS_RLS

Ngoài `ADD_POLICY`, package có các thủ tục quản lý vòng đời policy. Tên tham số và overload cần đối chiếu tài liệu đúng release.

### 11.1. Tắt policy

```sql
BEGIN
    DBMS_RLS.DISABLE_POLICY(
        object_schema => 'APP',
        object_name   => 'ORDERS',
        policy_name   => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

Tắt policy làm mất lớp lọc VPD tương ứng. Chỉ thực hiện trong change window và có phê duyệt. Không dùng như cách debug tùy tiện trên production.

### 11.2. Bật policy

```sql
BEGIN
    DBMS_RLS.ENABLE_POLICY(
        object_schema => 'APP',
        object_name   => 'ORDERS',
        policy_name   => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

Sau khi bật, xác nhận policy được enable và test bằng user không đặc quyền.

### 11.3. Xóa policy

```sql
BEGIN
    DBMS_RLS.DROP_POLICY(
        object_schema => 'APP',
        object_name   => 'ORDERS',
        policy_name   => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

Xóa policy loại bỏ predicate bảo vệ gắn với object đó. Trước khi drop, cần xác nhận policy thay thế hoặc việc gỡ bỏ là chủ đích được phê duyệt.

### 11.4. Refresh policy

```sql
BEGIN
    DBMS_RLS.REFRESH_POLICY(
        object_schema => 'APP',
        object_name   => 'ORDERS',
        policy_name   => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

Dùng refresh khi cần làm mới policy/predicate cache theo semantics và giới hạn của policy type. Không coi refresh là thay thế cho kiểm thử cursor hoặc session.

## 12. Kiểm tra metadata VPD

### 12.1. DBA_POLICIES

DBA có thể xem policy đã khai báo:

```sql
SELECT object_owner,
       object_name,
       policy_name,
       pf_owner,
       function,
       sel,
       ins,
       upd,
       del,
       enable,
       policy_type
FROM dba_policies
WHERE object_owner = 'APP'
ORDER BY object_name, policy_name;
```

`ALL_POLICIES` hoặc view tương ứng có thể dùng khi không có quyền DBA. Tên cột/khả năng hiển thị phụ thuộc phiên bản và quyền.

### 12.2. Xem predicate đang áp dụng

Trong các phiên bản hỗ trợ, `V$VPD_POLICY` có thể giúp xem policy và predicate được áp dụng cho cursor:

```sql
SELECT sql_id,
       child_number,
       object_owner,
       object_name,
       policy,
       predicate
FROM v$vpd_policy
WHERE object_owner = 'APP';
```

Cần quyền đọc dynamic performance view. Đây là công cụ chẩn đoán hữu ích để xác nhận policy function trả predicate nào; không xuất dữ liệu nhạy cảm từ truy vấn kiểm tra ra log công khai.

### 12.3. Kiểm tra context hiện tại

```sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV', 'CLIENT_IDENTIFIER') AS client_identifier,
       SYS_CONTEXT('APP_CTX', 'TENANT_ID') AS tenant_id
FROM dual;
```

Đây là kiểm tra trạng thái session. `CLIENT_IDENTIFIER` hỗ trợ correlation/audit nhưng không tự chứng minh danh tính tenant.

## 13. Tối ưu hiệu năng cho VPD

VPD thêm predicate vào SQL. Nếu predicate đơn giản và có index phù hợp, overhead có thể nhỏ. Nếu policy function phức tạp hoặc predicate làm mất khả năng dùng index, chi phí có thể đáng kể.

### 13.1. Index theo tenant và workload

Ví dụ truy vấn thường lọc tenant, status và date:

```sql
SELECT order_id, amount
FROM app.orders
WHERE status = 'OPEN'
  AND order_date >= DATE '2026-01-01';
```

Policy thêm tenant predicate. Có thể đánh giá composite index:

```sql
CREATE INDEX app.orders_tenant_status_date_ix
ON app.orders (tenant_id, status, order_date);
```

Thứ tự cột cần dựa trên selectivity, predicate phổ biến, sort, clustering factor và workload DML. Không tạo index chỉ vì VPD predicate có `tenant_id`; phải benchmark trên dữ liệu đại diện.

### 13.2. Predicate nên sargable

Ưu tiên predicate có thể dùng index:

```sql
tenant_id = TO_NUMBER(SYS_CONTEXT('APP_CTX', 'TENANT_ID'))
```

Tránh bọc cột bằng function không cần thiết:

```sql
TO_CHAR(tenant_id) = SYS_CONTEXT('APP_CTX', 'TENANT_ID')
```

Function trên cột có thể làm optimizer khó dùng index B-tree hiện có, trừ khi có function-based index tương ứng.

### 13.3. Tránh policy function truy vấn bảng mỗi lần parse

Nếu function phải truy vấn nhiều bảng để tìm tenant/region, chi phí parse có thể tăng. Có thể:
- Đưa thuộc tính đã xác thực vào secure application context.
- Tối giản policy function.
- Dùng policy type phù hợp với context.
- Cache dữ liệu tham chiếu an toàn ở tầng phù hợp.
- Đo parse rate và shared cursor behavior.

Không cache dữ liệu phân quyền theo cách làm giá trị cũ tiếp tục có hiệu lực sau khi quyền bị thu hồi.

### 13.4. Đo plan và runtime

Sau khi gắn policy, kiểm tra plan:

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

Xem:
- Predicate VPD có xuất hiện đúng không.
- Index access path có được dùng không.
- E-Rows và A-Rows.
- Buffer gets và physical reads.
- Parse time và execution time.
- Số lần policy function được gọi theo policy type.
- Tác động đến các truy vấn khác trên object.

So sánh trước/sau trên cùng dữ liệu và nhóm bind/context.

## 14. Connection pool và nguy cơ rò context giữa request

Ứng dụng Java/JDBC thường tái sử dụng database session thông qua connection pool. Application context thuộc session; khi connection được trả lại pool, context có thể vẫn tồn tại.

Đây là rủi ro nghiêm trọng: request của tenant A dùng connection, đặt `TENANT_ID=10`, sau đó connection được tái sử dụng cho tenant B nhưng context không được reset. Nếu không thiết lập lại đúng, B có thể nhìn thấy dữ liệu A hoặc request có thể thất bại theo trạng thái context cũ.

### 14.1. Quy trình cho mỗi lần checkout

1. Lấy connection từ pool.
2. Xóa context cũ hoặc khởi tạo session theo package tin cậy.
3. Xác thực danh tính request ở application tier.
4. Gọi trusted package để thiết lập context mới.
5. Chỉ sau khi thiết lập thành công mới chạy SQL nghiệp vụ.
6. Nếu thiết lập context thất bại, hủy request và không chạy truy vấn.

### 14.2. Quy trình khi trả connection

- Xóa application context.
- Reset module/action/client identifier nếu dùng.
- Reset session state khác do request thay đổi.
- Nếu không thể xác nhận trạng thái sạch, loại connection khỏi pool thay vì tái sử dụng.

Ví dụ package có thủ tục `clear_for_session` ở phần trước. Ứng dụng nên gọi trong `finally`/cleanup path để xử lý cả khi request phát sinh exception.

### 14.3. Không dựa vào reset chỉ ở đường thành công

Nếu cleanup chỉ chạy khi request thành công, exception hoặc timeout có thể để lại context cũ. Cần bảo đảm cleanup trong mọi nhánh, đồng thời có cơ chế pool validation.

### 14.4. Test context leakage

Kiểm thử tuần tự trên cùng physical connection:
1. Request A thiết lập tenant 10 và đọc dữ liệu.
2. Trả connection về pool.
3. Request B dùng lại connection, thiết lập tenant 20.
4. Xác nhận B chỉ thấy tenant 20.
5. Request tiếp theo không thiết lập context phải bị từ chối/không thấy hàng.
6. Lặp lại khi request A lỗi giữa chừng.

Đây là test bắt buộc cho mô hình session pooling có VPD.

## 15. VPD và các lớp bảo mật Oracle khác

| Cơ chế | Mục tiêu chính | Quan hệ với VPD |
|---|---|---|
| Object privileges | Ai được truy cập object/cột | Lớp quyền cơ bản; VPD không thay thế |
| Views | Cung cấp interface và giới hạn cột/hàng theo định nghĩa | Có thể kết hợp VPD |
| VPD / DBMS_RLS | Lọc hàng bằng predicate động | Phù hợp tenant/row isolation |
| Column-level VPD | Áp dụng chính sách khi truy cập cột nhạy cảm | Một phần của VPD |
| Data Redaction | Mask giá trị cột trong kết quả | Bổ sung cho VPD |
| Oracle Label Security | Phân loại và kiểm soát dữ liệu theo label | Phù hợp mô hình label-based |
| Database Vault | Kiểm soát quyền truy cập đặc quyền và miền bảo vệ | Bổ sung bảo vệ quản trị |
| Real Application Security | Mô hình bảo mật ứng dụng/database sâu hơn theo user/session/role | Có thể là lựa chọn cho kiến trúc cần quản lý danh tính phong phú |

Chọn cơ chế theo yêu cầu. VPD không tự mask dữ liệu; Data Redaction không thay thế tenant row filter; Database Vault tập trung vào kiểm soát đặc quyền và domain.

## 16. Bypass và giới hạn cần hiểu

VPD không phải ranh giới chống lại mọi tài khoản quản trị hoặc mọi đường truy cập vật lý.

### 16.1. EXEMPT ACCESS POLICY

Tài khoản có system privilege `EXEMPT ACCESS POLICY` có thể bỏ qua VPD policy. Quyền này rất nhạy cảm và không nên cấp cho tài khoản ứng dụng hoặc người dùng thông thường.

Kiểm tra quyền:

```sql
SELECT grantee, privilege
FROM dba_sys_privs
WHERE privilege = 'EXEMPT ACCESS POLICY'
ORDER BY grantee;
```

Rà soát cả role được cấp và quyền hiệu lực theo chính sách quản trị. Chỉ giữ ngoại lệ có owner, lý do và audit.

### 16.2. SYS và tài khoản quản trị

Các đường truy cập đặc quyền như SYS/SYSDBA có khả năng vượt qua nhiều cơ chế bảo vệ ở tầng SQL. Không dùng SYS cho ứng dụng. Tách account quản trị, giới hạn đăng nhập, audit và bảo vệ credential.

### 16.3. Đường truy cập ngoài SQL

VPD kiểm soát truy cập qua các SQL operation được hỗ trợ. Nó không thay thế:
- Quyền OS trên datafile/backup.
- Bảo vệ RMAN backup và export.
- Mã hóa dữ liệu at rest/in transit.
- Bảo vệ log, trace và bản sao dữ liệu.
- Kiểm soát người có quyền quản trị database host.

Một DBA có thể truy cập datafile hoặc backup qua các công cụ đặc quyền nếu có quyền hạ tầng phù hợp. Cần kiến trúc bảo vệ nhiều lớp.

### 16.4. Kiểm tra phiên bản và feature

Các tham số, policy type, column-level option, hỗ trợ object và quyền cần được xác nhận theo Oracle Database release/edition. Không sao chép ví dụ từ môi trường khác mà chưa thử trên staging.

## 17. Các lỗi thiết kế thường gặp

| Lỗi | Rủi ro | Cách xử lý |
|---|---|---|
| Lấy tenant ID trực tiếp từ request | Người dùng có thể giả mạo tenant | Xác thực ở trusted tier/package |
| Context null trả `1=1` | Lộ toàn bộ hàng | Fail-closed bằng `1=0` |
| Dùng shared account nhưng tin SESSION_USER phân biệt end user | SESSION_USER chỉ là service account | Dùng identity assertion/proxy auth phù hợp |
| Không reset context trong pool | Rò dữ liệu giữa request | Clear và set context mỗi checkout |
| Chỉ gắn policy SELECT | DML có thể ghi/sửa ngoài phạm vi | Xác định statement_types và update_check |
| Không bật update_check | Có thể chèn/chuyển tenant key trái phép | Kiểm tra hàng mới sau INSERT/UPDATE |
| Policy function nối chuỗi input | SQL injection hoặc lỗi predicate | Dùng SYS_CONTEXT và bind/runtime expression |
| Dùng STATIC cho predicate phụ thuộc session | Predicate cache không đúng user/context | Dùng dynamic/context-sensitive phù hợp |
| Function policy quá phức tạp | Parse overhead tăng | Tối giản logic và đo |
| Không kiểm soát EXEMPT ACCESS POLICY | User bypass VPD | Rà soát quyền đặc biệt |
| Chỉ test qua UI | Đường SQL khác có thể không được bảo vệ | Test trực tiếp bằng SQL nhiều principal |
| Không kiểm tra view/procedure/job | Có thể có đường truy cập ngoài dự kiến | Inventory mọi consumer/object |
| Coi VPD là data masking | Giá trị nhạy cảm vẫn có thể hiển thị ở hàng được phép | Dùng Data Redaction hoặc quyền cột khi cần |

## 18. Kiểm thử VPD có hệ thống

Không chỉ kiểm tra user hợp lệ thấy đúng hàng. Phải kiểm tra cả trường hợp context thiếu, giả mạo, thay đổi và DML.

### 18.1. Kiểm thử positive

- Tenant 10 chỉ thấy hàng tenant 10.
- Tenant 20 chỉ thấy hàng tenant 20.
- Predicate kết hợp với filter ứng dụng cho kết quả đúng.
- Các view và stored procedure vẫn hoạt động đúng.
- Các báo cáo có quyền được xem đúng phạm vi.

### 18.2. Kiểm thử negative

- Context chưa thiết lập: không thấy hàng.
- Context rỗng: không thấy hàng.
- Tenant ID không hợp lệ: bị từ chối hoặc không có hàng.
- User tenant 10 truy cập order tenant 20: không đọc được.
- User tenant 10 UPDATE/DELETE hàng tenant 20: không thay đổi dữ liệu.
- User tenant 10 INSERT hàng với tenant_id 20: bị từ chối khi update_check được cấu hình.
- User thường không thể gọi API để set tenant tùy ý.
- User ứng dụng không có `EXEMPT ACCESS POLICY`.

### 18.3. Kiểm thử connection pool

- Hai tenant dùng lại cùng physical connection.
- Request đầu phát sinh exception trước cleanup.
- Connection bị timeout hoặc bị hủy giữa request.
- Context được thay đổi nhiều lần trong cùng session.
- Cleanup thất bại và connection bị loại khỏi pool.
- Không có context nào bị kế thừa từ request trước.

### 18.4. Kiểm thử performance

Đo:
- Parse time.
- Elapsed và CPU.
- Buffer gets.
- Plan và predicate.
- Số lần gọi policy function.
- Hiệu năng với tenant nhỏ và tenant lớn.
- Hiệu năng khi nhiều session đồng thời.

Một tenant có phần lớn dữ liệu có thể có plan khác tenant nhỏ. Đánh giá data skew và bind/context distribution.

## 19. Triển khai policy theo từng bước

Một trình tự triển khai có kiểm soát:

1. Xác định bảng, view và cột chứa dữ liệu cần bảo vệ.
2. Xác định principal và cách xác thực end user/tenant.
3. Thiết kế namespace/attribute và trusted package.
4. Xây dựng policy function fail-closed.
5. Kiểm tra predicate bằng các context test.
6. Tạo context và cấp quyền package.
7. Gắn policy trên staging.
8. Test SELECT/INSERT/UPDATE/DELETE và pool reuse.
9. Đọc execution plan, đo overhead và tạo index phù hợp.
10. Rà soát quyền bypass và account đặc quyền.
11. Triển khai theo change window, có rollback.
12. Theo dõi lỗi policy, hiệu năng và audit sau deploy.

### 19.1. Rollback cần được thiết kế trước

Nếu cần tắt policy để khôi phục dịch vụ, phải có quy trình được phê duyệt và kiểm soát người thực hiện. Tắt VPD có thể mở rộng quyền đọc/ghi ngay lập tức.

Có thể rollback code policy hoặc thay đổi cấu hình theo phiên bản. Không để policy bị disable ngoài cửa sổ xử lý sự cố; ghi audit và xác nhận enable lại trước khi kết thúc incident.

### 19.2. Triển khai nhiều object

Nếu một tenant key xuất hiện ở nhiều bảng, cần policy cho mọi đường truy cập phù hợp. Một bảng thiếu policy có thể tạo đường join hoặc truy vấn trực tiếp để lộ dữ liệu.

Tạo inventory object, policy name, function owner, statement types và trạng thái enable. Kiểm tra các view/materialized view, synonym và stored procedure theo cách ứng dụng truy cập thực tế.

## 20. Ví dụ lab tổng hợp

Ví dụ dưới đây minh họa ý tưởng với hai tenant và một database principal được ánh xạ tới một tenant. Đây là lab, cần schema/quyền phù hợp và phải điều chỉnh theo phiên bản.

### Bước 1. Tạo bảng dữ liệu

```sql
CREATE TABLE app.orders (
    order_id NUMBER PRIMARY KEY,
    tenant_id NUMBER NOT NULL,
    status VARCHAR2(20) NOT NULL,
    amount NUMBER(12,2) NOT NULL
);

INSERT INTO app.orders VALUES (101, 10, 'OPEN', 250);
INSERT INTO app.orders VALUES (102, 10, 'CLOSED', 400);
INSERT INTO app.orders VALUES (201, 20, 'OPEN', 900);
COMMIT;
```

### Bước 2. Tạo bảng ánh xạ principal

```sql
CREATE TABLE sec.db_principal_tenant (
    db_username VARCHAR2(128) PRIMARY KEY,
    tenant_id NUMBER NOT NULL
);

INSERT INTO sec.db_principal_tenant
VALUES ('ORDER_APP_TENANT10', 10);

COMMIT;
```

Trong lab, mỗi tenant có một database principal riêng. Nếu production dùng chung service account, cần thay cơ chế ánh xạ bằng danh tính/assertion tin cậy như đã giải thích; không dùng tenant ID tùy ý từ client.

### Bước 3. Tạo package context

```sql
CREATE OR REPLACE PACKAGE sec.app_context_pkg
AUTHID DEFINER
AS
    PROCEDURE set_for_session;
    PROCEDURE clear_for_session;
END;
/
```

```sql
CREATE OR REPLACE PACKAGE BODY sec.app_context_pkg
AS
    PROCEDURE set_for_session
    IS
        l_tenant_id sec.db_principal_tenant.tenant_id%TYPE;
    BEGIN
        SELECT tenant_id
        INTO l_tenant_id
        FROM sec.db_principal_tenant
        WHERE db_username = SYS_CONTEXT('USERENV', 'SESSION_USER');

        DBMS_SESSION.SET_CONTEXT(
            'APP_CTX',
            'TENANT_ID',
            TO_CHAR(l_tenant_id)
        );
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
            RAISE_APPLICATION_ERROR(-20001, 'No tenant mapping');
    END;

    PROCEDURE clear_for_session
    IS
    BEGIN
        DBMS_SESSION.CLEAR_CONTEXT('APP_CTX', NULL, NULL);
    END;
END;
/
```

### Bước 4. Tạo secure application context

```sql
CREATE CONTEXT app_ctx USING sec.app_context_pkg;
```

### Bước 5. Tạo policy function

```sql
CREATE OR REPLACE FUNCTION sec.orders_tenant_predicate(
    object_schema IN VARCHAR2,
    object_name IN VARCHAR2
)
RETURN VARCHAR2
AUTHID DEFINER
AS
BEGIN
    IF SYS_CONTEXT('APP_CTX', 'TENANT_ID') IS NULL THEN
        RETURN '1=0';
    END IF;

    RETURN
        'tenant_id = TO_NUMBER(SYS_CONTEXT(''APP_CTX'', ''TENANT_ID''))';
END;
/
```

### Bước 6. Gắn policy

```sql
BEGIN
    DBMS_RLS.ADD_POLICY(
        object_schema   => 'APP',
        object_name     => 'ORDERS',
        policy_name     => 'ORDERS_TENANT_POLICY',
        function_schema => 'SEC',
        policy_function => 'ORDERS_TENANT_PREDICATE',
        statement_types => 'SELECT,INSERT,UPDATE,DELETE',
        update_check    => TRUE,
        enable          => TRUE
    );
END;
/
```

### Bước 7. Cấp quyền package và object theo mô hình lab

```sql
GRANT EXECUTE ON sec.app_context_pkg TO order_app_tenant10;
GRANT SELECT, INSERT, UPDATE, DELETE ON app.orders TO order_app_tenant10;
```

Không cấp `EXEMPT ACCESS POLICY` cho tài khoản ứng dụng.

### Bước 8. Thiết lập context trước khi query

Đăng nhập bằng principal đã được ánh xạ:

```sql
BEGIN
    sec.app_context_pkg.set_for_session;
END;
/
```

Kiểm tra context:

```sql
SELECT SYS_CONTEXT('APP_CTX', 'TENANT_ID')
FROM dual;
```

Truy vấn:

```sql
SELECT order_id, tenant_id, status, amount
FROM app.orders
ORDER BY order_id;
```

Chỉ hàng tenant 10 được trả về qua policy.

### Bước 9. Kiểm thử DML

Thử chèn hàng tenant khác:

```sql
INSERT INTO app.orders (order_id, tenant_id, status, amount)
VALUES (301, 20, 'OPEN', 100);
```

Với policy và update check phù hợp, thao tác phải bị từ chối vì hàng mới không thỏa tenant predicate. Kiểm tra lỗi Oracle thực tế trên release đang dùng.

### Bước 10. Kiểm tra metadata và plan

```sql
SELECT object_owner,
       object_name,
       policy_name,
       enable,
       policy_type
FROM dba_policies
WHERE object_owner = 'APP'
  AND object_name = 'ORDERS';
```

```sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE'
    )
);
```

### Bước 11. Xóa context trước khi trả connection

```sql
BEGIN
    sec.app_context_pkg.clear_for_session;
END;
/
```

Trong ứng dụng pool, gọi cleanup ở mọi đường thoát request và loại connection khỏi pool nếu không xác nhận được trạng thái sạch.

### Bước 12. Dọn lab

Chỉ xóa object do bạn tạo và khi không còn cần:

```sql
BEGIN
    DBMS_RLS.DROP_POLICY(
        object_schema => 'APP',
        object_name => 'ORDERS',
        policy_name => 'ORDERS_TENANT_POLICY'
    );
END;
/
```

Sau đó có thể drop các bảng, function, package và context theo dependency, quyền và chính sách lab. Không chạy DDL dọn dẹp trên object nghiệp vụ.

## 21. Checklist vận hành VPD

### Danh tính và context
- Nguồn tenant/user đã được xác thực.
- Client không thể tự đặt tenant tùy ý.
- Context là secure application context.
- Context thiếu hoặc sai dẫn đến fail-closed.
- Context được thiết lập trước mọi SQL nghiệp vụ.
- Context được xóa/reset trên connection pool.

### Policy
- Đúng object và schema.
- Đúng statement types.
- Có update_check cho DML cần bảo vệ.
- Policy type phù hợp context/caching.
- Policy function đơn giản, không nối input không tin cậy.
- Column-level option được kiểm thử nếu dùng.
- Policy được enable sau triển khai.

### Quyền và bypass
- Application account không có EXEMPT ACCESS POLICY.
- SYS/SYSDBA được tách khỏi workload ứng dụng.
- Quyền object và quyền package tối thiểu.
- Các object/view/procedure/job có đường truy cập đều được rà soát.

### Hiệu năng và giám sát
- Predicate có thể dùng index phù hợp.
- Có baseline trước/sau.
- Đã kiểm tra execution plan và VPD predicate.
- Đã đo tenant lớn/nhỏ và concurrency.
- Có audit/alert cho thay đổi policy và bypass privilege.
- Có rollback được phê duyệt và xác nhận enable lại.

## 22. Câu hỏi tự kiểm tra

**Câu 1.** Virtual Private Database là gì?

**Trả lời:** Cơ chế Oracle tự áp predicate bảo mật vào SQL truy cập object có policy, thường dùng để giới hạn hàng theo user, tenant hoặc context.

**Câu 2.** DBMS_RLS dùng để làm gì?

**Trả lời:** Quản lý VPD policy, gắn policy function vào table/view và điều khiển bật, tắt, refresh hoặc drop policy.

**Câu 3.** Application context là gì?

**Trả lời:** Tập thuộc tính session được lưu theo namespace/attribute và đọc qua `SYS_CONTEXT`.

**Câu 4.** Vì sao dùng secure application context?

**Trả lời:** Chỉ package tin cậy được chỉ định mới có thể set context, giúp kiểm soát nguồn gốc thuộc tính bảo mật.

**Câu 5.** Vì sao không lấy tenant ID trực tiếp từ request?

**Trả lời:** Client có thể giả mạo tenant ID và truy cập dữ liệu ngoài phạm vi nếu package không xác thực danh tính.

**Câu 6.** Policy function trả về gì?

**Trả lời:** Một chuỗi predicate SQL mà Oracle áp dụng cho statement truy cập object.

**Câu 7.** Vì sao context thiếu nên trả `1=0`?

**Trả lời:** Đây là fail-closed: không có context hợp lệ thì không trả hàng nào.

**Câu 8.** `update_check => TRUE` có ý nghĩa gì?

**Trả lời:** Oracle kiểm tra hàng mới sau INSERT/UPDATE có thỏa predicate policy hay không, ngăn ghi dữ liệu ngoài phạm vi.

**Câu 9.** DYNAMIC và STATIC policy khác nhau thế nào?

**Trả lời:** Dynamic đánh giá function theo vòng đời parse; Static cache predicate khi predicate thực sự không phụ thuộc session/context.

**Câu 10.** Khi nào cân nhắc CONTEXT_SENSITIVE?

**Trả lời:** Khi predicate phụ thuộc application context và cần policy được làm mới khi context liên quan thay đổi.

**Câu 11.** `sec_relevant_cols` dùng để làm gì?

**Trả lời:** Chỉ định các cột nhạy cảm để kích hoạt column-level VPD khi statement tham chiếu các cột đó.

**Câu 12.** `DBMS_RLS.ALL_ROWS` có tác dụng gì?

**Trả lời:** Cho phép trả tất cả hàng nhưng giá trị cột nhạy cảm được trả NULL cho các hàng không thỏa predicate theo semantics column-level VPD.

**Câu 13.** VPD có thay thế object privileges không?

**Trả lời:** Không. User vẫn cần quyền truy cập object; VPD giới hạn hàng sau lớp quyền cơ bản.

**Câu 14.** Vì sao connection pool phải reset context?

**Trả lời:** Context thuộc session và có thể tồn tại khi connection được tái sử dụng, gây rò dữ liệu giữa request/tenant.

**Câu 15.** `EXEMPT ACCESS POLICY` có rủi ro gì?

**Trả lời:** Privilege này cho phép bỏ qua VPD policy và phải được giới hạn cho tài khoản đặc quyền có kiểm soát.

**Câu 16.** VPD có phải data masking không?

**Trả lời:** Không. VPD chủ yếu lọc hàng; Data Redaction xử lý việc che giá trị cột trong kết quả.

**Câu 17.** Vì sao cần kiểm thử INSERT/UPDATE ngoài SELECT?

**Trả lời:** Nếu chỉ lọc đọc mà không kiểm tra hàng mới, user có thể ghi hoặc chuyển dữ liệu sang tenant khác.

**Câu 18.** Làm sao xác nhận policy thực sự được áp dụng?

**Trả lời:** Kiểm tra metadata policy, context session, predicate qua view chẩn đoán khi hỗ trợ và execution plan bằng `DBMS_XPLAN`.

## 23. Kết luận

Virtual Private Database cung cấp row-level security ở database bằng cách gắn policy function vào table hoặc view. Application context giữ thuộc tính bảo mật của session; `DBMS_RLS` quản lý policy; Oracle tự áp predicate khi thực thi các statement thuộc phạm vi policy. Cách làm này giúp bảo vệ dữ liệu ngay cả khi nhiều ứng dụng hoặc nhiều đường SQL cùng truy cập một object.

Tính an toàn phụ thuộc vào nguồn gốc context. Context phải được thiết lập bởi package tin cậy sau khi danh tính đã được xác thực; không chấp nhận tenant ID tùy ý từ client. Khi context thiếu, policy phải fail-closed. Với DML, cần khai báo statement types và cân nhắc `update_check` để ngăn chèn hoặc sửa hàng ngoài phạm vi. Column-level VPD có thể hỗ trợ kiểm soát cột nhạy cảm, nhưng cần phân biệt với Data Redaction.

Trong môi trường connection pool, context phải được thiết lập lại cho từng request và xóa trước khi tái sử dụng connection. Policy type, caching, predicate và index cần được đo trên workload thực tế. Rà soát `EXEMPT ACCESS POLICY`, SYS/SYSDBA và mọi đường truy cập đặc quyền vì VPD không thay thế bảo mật hạ tầng. Chỉ triển khai sau khi đã kiểm thử chéo tenant, DML, context leakage, execution plan và quy trình rollback.

