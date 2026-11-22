# Khi nên dùng constraint, mã ứng dụng hoặc trigger trong Oracle

Khi thiết kế một quy tắc dữ liệu, Oracle Database cung cấp nhiều nơi để thực thi: **constraint** ở schema, **mã ứng dụng** ở tầng service/client và **trigger** chạy tự động khi một sự kiện database xảy ra. Cả ba đều có thể kiểm tra hoặc thay đổi dữ liệu, nhưng phạm vi bảo đảm và thời điểm thực thi rất khác nhau.

Một quy tắc như “mỗi email chỉ được xuất hiện một lần” cần được bảo vệ cho mọi session và mọi ứng dụng ghi vào bảng. UNIQUE constraint là lựa chọn tự nhiên vì Oracle kiểm tra tính duy nhất ngay cả khi nhiều transaction ghi đồng thời. Ứng dụng vẫn nên kiểm tra sớm để hiển thị thông báo thân thiện, nhưng truy vấn kiểm tra trước khi INSERT không thể thay thế constraint trong tình huống cạnh tranh. Trigger hữu ích khi cần phản ứng với sự kiện DML, ghi audit hoặc áp dụng logic không thể biểu diễn bằng constraint, nhưng trigger cũng làm hành vi ghi dữ liệu trở nên ngầm định và khó theo dõi hơn.

Bài học thuộc chủ đề **Lỗi và trigger** của *Database Engine Relational Oracle*. Nội dung tập trung vào:

- Vai trò và giới hạn của constraint, application validation và trigger.
- Cách chọn đúng nơi thực thi quy tắc toàn vẹn.
- Các constraint Oracle: NOT NULL, CHECK, UNIQUE, PRIMARY KEY và FOREIGN KEY.
- Tính toàn vẹn dưới concurrency và transaction.
- Trường hợp nên dùng mã ứng dụng cho validation và workflow.
- Trường hợp trigger có ích, cùng các rủi ro và giới hạn.
- Cách kết hợp nhiều tầng, xử lý lỗi và chẩn đoán.
- Bài thực hành SQL để so sánh ba cách triển khai.

## 1. Ba nơi có thể thực thi quy tắc dữ liệu

### Constraint: quy tắc được database bảo đảm

Constraint là khai báo trong schema, mô tả điều kiện dữ liệu phải tuân theo. Oracle kiểm tra constraint khi INSERT/UPDATE và trong các thời điểm được quy định bởi trạng thái/thuộc tính constraint. Vì quy tắc nằm ngay tại database, mọi ứng dụng, batch job, script hoặc người dùng có quyền DML đều chịu cùng một quy tắc.

Ví dụ:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER
        CONSTRAINT pk_customers PRIMARY KEY,
    email VARCHAR2(320)
        CONSTRAINT nn_customers_email NOT NULL,
    status VARCHAR2(20)
        CONSTRAINT ck_customers_status
        CHECK (status IN ('ACTIVE', 'INACTIVE'))
);
~~~

Database bảo đảm customer_id duy nhất và không NULL, email không NULL, status nằm trong tập giá trị cho phép. Caller không thể bỏ qua các quy tắc này chỉ bằng cách dùng một ứng dụng khác.

### Mã ứng dụng: validation và quy tắc theo use case

Mã ứng dụng có thể kiểm tra đầu vào trước khi gửi DML tới Oracle. Nó hiểu ngữ cảnh giao diện, người dùng, request, quy trình phê duyệt và có thể trả thông báo dễ hiểu.

Ví dụ, service có thể kiểm tra:

- Email có định dạng hợp lệ theo quy tắc sản phẩm.
- Ngày giao hàng có nằm trong khoảng người dùng được chọn.
- Người dùng có quyền tạo đơn trong tenant hiện tại.
- Một thao tác có được phép ở trạng thái workflow hiện tại.
- Các trường liên quan có được cung cấp cùng nhau hay không.

Mã ứng dụng là nơi phù hợp cho logic phụ thuộc vào request hoặc trải nghiệm người dùng. Tuy nhiên, nếu cùng dữ liệu có thể được ghi từ nhiều ứng dụng, batch hoặc script, validation chỉ ở một client không phải là bảo đảm toàn vẹn chung.

### Trigger: phản ứng tự động với sự kiện database

Trigger là chương trình PL/SQL được database tự động chạy khi một sự kiện được chỉ định xảy ra, chẳng hạn INSERT, UPDATE, DELETE trên bảng, sự kiện DDL hoặc sự kiện database. Trigger không được gọi trực tiếp như một procedure thông thường; Oracle kích hoạt nó theo event và timing đã khai báo.

Ví dụ trigger audit:

~~~sql
CREATE OR REPLACE TRIGGER trg_customers_status_audit
AFTER UPDATE OF status ON customers
FOR EACH ROW
BEGIN
    INSERT INTO customer_status_audit (
        customer_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        :NEW.customer_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END;
/
~~~

Mỗi lần status được cập nhật, trigger ghi lại giá trị cũ/mới trong cùng transaction. Trigger có thể đảm bảo hành vi chạy cho mọi DML trên bảng, kể cả DML không đi qua ứng dụng chính.

## 2. Nguyên tắc chọn nơi thực thi

Trước khi viết code, hãy xác định quy tắc thuộc loại nào:

1. **Bất biến dữ liệu (data invariant):** mọi hàng phải thỏa điều kiện bất kể ai ghi dữ liệu. Ưu tiên constraint.
2. **Validation của request:** cần kiểm tra sớm, đưa lỗi dễ hiểu hoặc cần ngữ cảnh người dùng. Đặt ở ứng dụng, đồng thời vẫn dùng constraint cho invariant có thể khai báo.
3. **Phản ứng với sự kiện database:** cần ghi audit, duy trì hành vi chung cho mọi DML hoặc tương thích với schema/view legacy. Cân nhắc trigger nếu không có cơ chế rõ ràng hơn.
4. **Quy trình nghiệp vụ nhiều bước:** cần gọi service, gửi thông báo, phê duyệt hoặc tích hợp hệ thống ngoài. Đặt ở application/service layer hoặc hệ thống event/outbox; không biến trigger thành workflow engine.

### Bảng quyết định nhanh

| Nhu cầu | Lựa chọn ưu tiên | Lý do |
| --- | --- | --- |
| Cột bắt buộc có giá trị | NOT NULL constraint | Quy tắc đơn giản, database bảo đảm. |
| Giá trị phải nằm trong miền hợp lệ | CHECK constraint | Khai báo rõ ràng, áp dụng cho mọi DML. |
| Khóa không được trùng | UNIQUE/PRIMARY KEY constraint | Oracle xử lý cạnh tranh giữa transaction. |
| Khóa ngoại phải tham chiếu hàng cha | FOREIGN KEY constraint | Bảo vệ quan hệ giữa bảng. |
| Hiển thị lỗi thân thiện trước khi submit | Application validation | Gần giao diện và request context. |
| Quyền thao tác theo người dùng/tenant | Application authorization và kiểm soát database phù hợp | Cần danh tính và ngữ cảnh bảo mật. |
| Ghi nhận thay đổi từ mọi nguồn DML | Audit trigger hoặc cơ chế auditing phù hợp | Tự động chạy ở database. |
| Chuẩn hóa giá trị đầu vào | Thường ở application; có thể dùng virtual column/index/trigger tùy yêu cầu | Chọn nơi có thể duy trì một quy tắc duy nhất. |
| Gửi email hoặc gọi API ngoài sau khi lưu | Application/outbox | Tránh tác dụng phụ ngoài transaction của trigger. |
| Quy tắc cần truy vấn nhiều hàng để kiểm tra | Thiết kế lại schema/constraint phù hợp hoặc transaction service; trigger chỉ khi hiểu rõ concurrency | SELECT kiểm tra đơn giản có thể race và row trigger có thể gặp mutating table. |

### Câu hỏi trước khi quyết định

- Quy tắc phải áp dụng cho tất cả nguồn ghi dữ liệu hay chỉ một use case?
- Oracle có thể diễn đạt quy tắc bằng constraint hay index không?
- Hai transaction đồng thời có thể cùng vượt qua bước validation không?
- Quy tắc có cần thông tin người dùng, request hoặc dịch vụ ngoài không?
- Cần hành vi tự động cho mỗi row, mỗi statement hay cho DDL/database event?
- Ai sẽ hiểu, kiểm thử và vận hành logic khi nó nằm trong trigger?
- Có thể ghi rõ logic trong một câu SQL hoặc API tường minh thay vì tạo tác dụng phụ ngầm không?

## 3. Constraint: lựa chọn đầu tiên cho data integrity

Constraint là cách khai báo rõ nhất cho nhiều quy tắc toàn vẹn phổ biến. Oracle có thể dùng metadata constraint để kiểm tra dữ liệu và hỗ trợ optimizer trong một số trường hợp.

### NOT NULL

Dùng khi cột bắt buộc phải có giá trị:

~~~sql
CREATE TABLE products (
    product_id NUMBER PRIMARY KEY,
    product_name VARCHAR2(200) NOT NULL
);
~~~

Application vẫn nên báo “Tên sản phẩm là bắt buộc” trước khi submit. Nhưng NOT NULL bảo đảm một batch job hoặc script khác không thể ghi NULL vào cột.

### CHECK

Dùng cho điều kiện trên một hàng:

~~~sql
CREATE TABLE employees (
    employee_id NUMBER PRIMARY KEY,
    salary NUMBER(12,2)
        CONSTRAINT ck_employees_salary
        CHECK (salary >= 0),
    status VARCHAR2(20)
        CONSTRAINT ck_employees_status
        CHECK (status IN ('ACTIVE', 'INACTIVE', 'LEFT'))
);
~~~

CHECK constraint cho phép biểu thức có kết quả TRUE hoặc UNKNOWN; hàng có giá trị NULL có thể không bị loại chỉ bởi CHECK. Nếu cột cũng bắt buộc có giá trị, khai báo NOT NULL riêng.

CHECK constraint không phải công cụ tổng quát để truy vấn bảng khác, kiểm tra aggregate trên nhiều hàng hoặc gọi API. Hãy giữ biểu thức CHECK ở phạm vi hàng và điều kiện mà Oracle hỗ trợ.

### UNIQUE và PRIMARY KEY

~~~sql
CREATE TABLE app_users (
    user_id NUMBER
        CONSTRAINT pk_app_users PRIMARY KEY,
    email VARCHAR2(320)
        CONSTRAINT uq_app_users_email UNIQUE
);
~~~

PRIMARY KEY xác định hàng và không cho phép NULL trên các cột khóa. UNIQUE bảo đảm khóa duy nhất theo semantics Oracle, nhưng cột nullable có thể cho phép NULL. Nếu email bắt buộc, kết hợp NOT NULL.

Oracle thường dùng unique index để thực thi PK/UNIQUE constraint không trì hoãn; với constraint DEFERRABLE, cơ chế index có thể khác. Index độc lập không tự tạo ra constraint trong metadata.

### FOREIGN KEY

~~~sql
CREATE TABLE orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

FOREIGN KEY bảo đảm customer_id khác NULL phải tham chiếu khóa hợp lệ ở bảng cha. Nếu bắt buộc phải có khách hàng, thêm NOT NULL trên customer_id. Oracle không tự động tạo index trên cột FK ở bảng con; cân nhắc index theo workload truy vấn và thao tác xóa/cập nhật parent key.

### Constraint cho quy tắc nhiều cột

~~~sql
CREATE TABLE booking_slots (
    booking_id NUMBER PRIMARY KEY,
    room_id NUMBER NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    CONSTRAINT ck_booking_time
        CHECK (end_time > start_time)
);
~~~

CHECK có thể kiểm tra quan hệ giữa các cột cùng hàng. Quy tắc “không có hai booking chồng thời gian trong cùng phòng” liên quan nhiều hàng nên không thể biểu diễn bằng CHECK thông thường; cần thiết kế khóa/slot, transaction serialization, application logic có khóa hoặc giải pháp khác phù hợp.

## 4. Mã ứng dụng: validation, workflow và authorization

Application validation chạy gần request và có thể đưa phản hồi sớm trước khi database thực hiện DML. Đây là nơi phù hợp cho những quy tắc cần ngữ cảnh mà schema không có, chẳng hạn người dùng hiện tại, tenant, quyền trên tài nguyên, nội dung màn hình hoặc trạng thái của một quy trình.

### Validation đầu vào

Ví dụ service nhận yêu cầu tạo tài khoản:

~~~text
Request
  |
  v
Validate required fields and format
  |
  v
Check business rules and caller permissions
  |
  v
Attempt INSERT
  |
  v
Database constraints are final integrity guard
~~~

Ứng dụng có thể kiểm tra email có định dạng hợp lệ, độ dài tên, ngày sinh, trạng thái người dùng hoặc các trường bắt buộc. Cùng lúc, database vẫn nên có NOT NULL, CHECK, UNIQUE hoặc FK tương ứng khi quy tắc là invariant của dữ liệu.

Validation sớm giúp người dùng sửa lỗi dễ dàng. Constraint bảo đảm dữ liệu không bị sai nếu có một đường ghi khác hoặc hai request chạy đồng thời.

### Application code phù hợp với quy tắc phụ thuộc ngữ cảnh

Ví dụ:

- Người dùng chỉ được cập nhật đơn hàng do chính họ tạo.
- Chỉ trưởng nhóm mới được duyệt yêu cầu trong team của mình.
- Một đơn hàng chỉ được xác nhận khi payment service trả trạng thái hợp lệ.
- Ngày giao hàng phải phù hợp lịch vận hành theo vùng.
- Mỗi khách hàng chỉ được tạo tối đa một yêu cầu đang chờ trong một workflow cụ thể.

Những quy tắc này có thể cần identity, tenant, quyền, dữ liệu dịch vụ ngoài hoặc nhiều bước. Chúng thường phù hợp với service layer, nhưng nếu quy tắc cuối cùng còn có thể biểu diễn bằng constraint thì vẫn nên khai báo constraint để bảo vệ dữ liệu.

### Kiểm tra trước rồi INSERT có race condition

Một lỗi phổ biến là kiểm tra email đã tồn tại chưa rồi mới INSERT:

~~~sql
SELECT COUNT(*)
INTO l_count
FROM app_users
WHERE email = p_email;

IF l_count = 0 THEN
    INSERT INTO app_users(email)
    VALUES (p_email);
END IF;
~~~

Hai session có thể cùng chạy SELECT trước khi session nào INSERT:

~~~text
Session A                    Session B
------------------------     ------------------------
SELECT email -> no row
                             SELECT email -> no row
INSERT email
                             INSERT same email
COMMIT
                             COMMIT
~~~

Nếu không có UNIQUE constraint, cả hai hàng có thể được chèn. Nếu có UNIQUE constraint, một transaction sẽ thắng và transaction còn lại bị từ chối khi Oracle phát hiện xung đột. Vì vậy application pre-check chỉ phục vụ thông báo sớm; nó không thể thay thế unique constraint.

### Xử lý lỗi constraint ở application

Ứng dụng nên bắt lỗi Oracle tương ứng và ánh xạ sang thông báo nghiệp vụ. Ví dụ ORA-00001 báo vi phạm unique constraint/index; ORA-01400 báo insert NULL vào cột NOT NULL; ORA-02291 báo vi phạm parent key khi ghi FK; ORA-02292 báo parent key đang được tham chiếu khi xóa/cập nhật.

Không nên chỉ bắt mọi exception rồi trả về “dữ liệu không hợp lệ”. Hãy phân biệt lỗi validation, lỗi xung đột đồng thời, lỗi kết nối và lỗi hệ thống để quyết định thông báo hoặc retry phù hợp.

### Application code và transaction

Khi quy tắc cần đọc rồi ghi nhiều bảng, ứng dụng có thể thực hiện toàn bộ bước trong một transaction. Nhưng transaction một mình không tự ngăn mọi race condition ở mức READ COMMITTED. Cần xác định invariant và chọn cơ chế đồng bộ phù hợp:

- Constraint/index để database giải quyết uniqueness và referential integrity.
- SELECT FOR UPDATE để khóa hàng đại diện khi mọi transaction tuân theo cùng quy tắc.
- Khóa advisory/application lock hoặc DBMS_LOCK khi có lý do rõ ràng và quản lý lock đúng cách.
- Isolation level phù hợp nếu nghiệp vụ yêu cầu; hiểu tác động serialization/ORA-08177 ở SERIALIZABLE.
- Thiết kế schema để biểu diễn invariant bằng unique key hoặc row đại diện thay vì kiểm tra aggregate dễ race.

### Authorization không giống constraint

Constraint bảo vệ tính hợp lệ của dữ liệu, không thay thế kiểm tra quyền của người dùng. Ví dụ CHECK status IN ('ACTIVE','DISABLED') chỉ giới hạn miền giá trị; nó không xác định ai được phép chuyển ACTIVE sang DISABLED. Quyền theo user/tenant thường được kiểm tra ở application hoặc security policy phù hợp trong database như VPD/RLS tùy kiến trúc.

Không dùng trigger để đoán người dùng ứng dụng nếu kết nối dùng chung schema account và không truyền identity một cách đáng tin cậy. Context người dùng phải được thiết lập và bảo vệ đúng cách.

## 5. Trigger: loại, timing và phạm vi

Trigger được gắn với một event. Với DML trigger trên bảng, các lựa chọn quan trọng gồm:

- BEFORE hoặc AFTER: chạy trước hoặc sau statement/row event tương ứng.
- Statement-level hoặc row-level: chạy một lần cho statement hoặc một lần cho mỗi hàng bị tác động.
- INSERT, UPDATE, DELETE: chọn loại DML kích hoạt.
- UPDATE OF column: chỉ kích hoạt khi câu UPDATE có đề cập cột được liệt kê; không đồng nghĩa giá trị thực sự thay đổi.

### Statement-level trigger

Statement-level trigger chạy một lần cho toàn bộ câu DML, không có một hàng hiện tại nên không dùng :OLD/:NEW:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_after_stmt
AFTER INSERT OR UPDATE OR DELETE ON orders
BEGIN
    DBMS_OUTPUT.PUT_LINE('DML statement affected orders');
END;
/
~~~

Trigger này chạy một lần cho statement, kể cả statement tác động 0 hàng.

### Row-level trigger

Row-level trigger có FOR EACH ROW và chạy một lần cho mỗi hàng bị tác động. Có thể dùng :OLD và :NEW để đọc giá trị trước/sau:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_status
BEFORE UPDATE OF status ON orders
FOR EACH ROW
BEGIN
    IF :NEW.status IS NULL THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Order status cannot be NULL'
        );
    END IF;
END;
/
~~~

Trong row trigger:

- INSERT: :NEW có giá trị hàng mới; :OLD không có hàng trước đó.
- UPDATE: :OLD là giá trị trước update; :NEW là giá trị sau update.
- DELETE: :OLD là hàng bị xóa; :NEW không có hàng mới.
- Không gán trực tiếp vào :OLD.
- Trong BEFORE EACH ROW, có thể gán :NEW.column để thiết lập giá trị trước khi lưu; AFTER EACH ROW chỉ đọc :NEW/:OLD.

Trigger trên chỉ minh họa kiểm tra; nếu status phải khác NULL, NOT NULL constraint là cách khai báo trực tiếp và đáng tin cậy hơn.

### BEFORE trigger và AFTER trigger

| Timing | Công dụng thường gặp |
| --- | --- |
| BEFORE EACH ROW | Chuẩn hóa hoặc gán giá trị :NEW; kiểm tra thuộc tính hàng; thiết lập audit context. |
| AFTER EACH ROW | Ghi audit/side table dựa trên giá trị đã được xác định; cập nhật logic phụ thuộc hàng. |
| BEFORE STATEMENT | Chuẩn bị trạng thái cho statement, kiểm tra điều kiện tổng quát. |
| AFTER STATEMENT | Thực hiện việc cần biết statement đã hoàn tất phần row processing. |

Chọn timing theo dữ liệu cần đọc và tác dụng mong muốn. Trigger AFTER không thể sửa :NEW; trigger BEFORE EACH ROW có thể gán giá trị cho :NEW nhưng không nên thay thế DEFAULT hoặc biểu thức SQL đơn giản nếu các cơ chế đó đủ dùng.

## 6. Trường hợp trigger có ích

Trigger phù hợp khi hành vi cần được thực thi tự động cho mọi DML phát sinh trên object, kể cả khi nguồn ghi không phải ứng dụng chính. Tuy nhiên, trước khi tạo trigger, hãy kiểm tra xem DEFAULT, identity column, constraint, virtual column, view hoặc API PL/SQL tường minh có đáp ứng yêu cầu đơn giản hơn không.

### Audit thay đổi

Trigger có thể ghi lại ai/thời điểm/giá trị cũ và mới khi một hàng thay đổi:

~~~sql
CREATE TABLE customer_audit (
    audit_id NUMBER GENERATED ALWAYS AS IDENTITY,
    customer_id NUMBER,
    old_status VARCHAR2(20),
    new_status VARCHAR2(20),
    changed_by VARCHAR2(128),
    changed_at TIMESTAMP
);

CREATE OR REPLACE TRIGGER trg_customer_status_audit
AFTER UPDATE OF status ON customers
FOR EACH ROW
WHEN (OLD.status <> NEW.status)
BEGIN
    INSERT INTO customer_audit (
        customer_id,
        old_status,
        new_status,
        changed_by,
        changed_at
    )
    VALUES (
        :NEW.customer_id,
        :OLD.status,
        :NEW.status,
        SYS_CONTEXT('USERENV', 'SESSION_USER'),
        SYSTIMESTAMP
    );
END;
/
~~~

Điều kiện WHEN trong ví dụ chỉ minh họa thay đổi giữa hai giá trị khác NULL. Nếu OLD.status hoặc NEW.status có thể NULL, phép so sánh <> cho kết quả UNKNOWN; hãy viết điều kiện null-safe phù hợp với quy tắc nghiệp vụ, chẳng hạn dùng DECODE hoặc biểu thức so sánh có xử lý NULL.

Trigger audit chạy cho mọi DML thay đổi status trên bảng, kể cả script/batch. Bản ghi audit nằm trong cùng transaction nên sẽ rollback nếu transaction cập nhật khách hàng rollback. Đây thường là điều đúng nếu audit phản ánh thay đổi đã commit.

### Gán giá trị mặc định hoặc chuẩn hóa trước khi lưu

Trigger BEFORE EACH ROW có thể gán :NEW:

~~~sql
CREATE OR REPLACE TRIGGER trg_customers_normalize
BEFORE INSERT OR UPDATE OF email ON customers
FOR EACH ROW
BEGIN
    :NEW.email := LOWER(TRIM(:NEW.email));
END;
/
~~~

Chỉ dùng trigger nếu mọi nguồn ghi đều phải áp dụng cùng chuẩn hóa và không có cơ chế khai báo phù hợp hơn. Với quy tắc đơn giản, có thể chuẩn hóa trong application, dùng cột chuẩn hóa riêng, virtual column hoặc function-based index. Nếu chỉ cần giá trị mặc định khi không truyền cột, DEFAULT/identity thường rõ ràng hơn.

### Tương thích với view phức tạp

INSTEAD OF trigger có thể cho phép INSERT/UPDATE/DELETE qua một view mà Oracle không thể tự cập nhật:

~~~sql
CREATE OR REPLACE TRIGGER trg_v_employee_dept_ins
INSTEAD OF INSERT ON v_employee_department
FOR EACH ROW
BEGIN
    INSERT INTO employees (
        employee_id,
        last_name,
        department_id
    )
    VALUES (
        :NEW.employee_id,
        :NEW.last_name,
        :NEW.department_id
    );
END;
/
~~~

Ví dụ cần view và bảng nền tương ứng; mục đích là minh họa trigger chuyển thao tác trên view thành DML trên bảng nền. INSTEAD OF trigger chạy thay cho thao tác DML trên view và thường được dùng để hỗ trợ view join hoặc view có cấu trúc phức tạp.

### Database/DDL event trigger

Oracle còn hỗ trợ DDL trigger và database event trigger cho các sự kiện như CREATE, ALTER, DROP, LOGON hoặc LOGOFF (tùy phạm vi và loại trigger). Chúng phù hợp cho một số yêu cầu quản trị, kiểm toán hoặc thiết lập session. Đây là nhóm trigger có tác động rộng; cần quyền phù hợp, kiểm thử kỹ và tránh làm các thao tác quản trị thông thường thất bại vì logic phụ.

### Thực thi logic dùng chung cho mọi nguồn DML

Nếu nhiều hệ thống ghi cùng một bảng và phải duy trì một side effect trong database, trigger có thể bảo đảm side effect được chạy dù caller không biết trigger tồn tại. Nhưng logic càng quan trọng thì càng cần tài liệu hóa rõ, đặt tên dễ tìm, theo dõi lỗi và cung cấp đường gọi kiểm thử. Nếu side effect là nghiệp vụ quan trọng, một API PL/SQL tường minh có thể dễ kiểm soát hơn trigger ngầm.

## 7. Khi không nên dùng trigger

### Không dùng trigger để thay constraint đơn giản

Không viết trigger SELECT COUNT rồi từ chối duplicate nếu có thể dùng UNIQUE constraint. Trigger row-level kiểm tra bảng có thể gặp mutating-table error; trigger tự viết cũng dễ mắc race condition nếu không khóa và điều phối transaction đúng cách. Unique index/constraint là cơ chế database được thiết kế cho uniqueness đồng thời.

### Không dùng trigger làm nơi chứa workflow dài

Trigger không phù hợp để:

- Gửi email hoặc SMS trực tiếp.
- Gọi HTTP API tới hệ thống khác.
- Chờ người dùng phê duyệt.
- Chạy quy trình nhiều bước kéo dài.
- Thực hiện tác vụ nặng theo từng hàng trong một bulk load lớn.

Trigger chạy trong đường thực thi DML của session. Nếu trigger gọi dịch vụ ngoài chậm hoặc lỗi, thao tác ghi có thể bị chậm hoặc thất bại. Với tích hợp ngoài, thường dùng transactional outbox: ghi sự kiện vào bảng trong cùng transaction, sau đó worker/application đọc và gửi tới hệ thống ngoài.

### Không dùng trigger chỉ để sao chép dữ liệu nếu SQL có thể làm rõ hơn

Nếu cần cập nhật cột dẫn xuất trong cùng bảng, xem xét biểu thức SQL, virtual column hoặc thiết kế lại mô hình. Nếu cần đồng bộ bảng tổng hợp, materialized view hoặc job rõ ràng có thể phù hợp hơn. Trigger tạo phụ thuộc ngầm và có thể khiến một câu UPDATE đơn giản cập nhật thêm nhiều bảng mà caller không biết.

### Không đặt COMMIT/ROLLBACK thông thường trong trigger

Trigger chạy trong transaction của statement kích hoạt. Trigger thông thường không thể COMMIT/ROLLBACK transaction của caller; transaction control trong trigger bị hạn chế. Nếu trigger cần ghi log độc lập với transaction chính, có thể dùng autonomous transaction trong trường hợp đặc biệt, nhưng phải hiểu rõ audit độc lập có thể tồn tại ngay cả khi DML gốc rollback. Không dùng autonomous transaction để né constraint hoặc tạo side effect không nhất quán.

### Không dùng trigger để ẩn quyền truy cập

Trigger không thay thế authorization. Nếu người dùng ứng dụng kết nối bằng một schema chung, SESSION_USER thường chỉ cho biết database account chung đó, không tự xác định end-user. Muốn audit end-user, phải thiết lập application context một cách đáng tin cậy và bảo vệ quyền thiết lập context; không tin giá trị client tùy ý gửi nếu không xác thực.

## 8. Những rủi ro kỹ thuật khi dùng trigger

### Mutating table: ORA-04091

Row-level trigger không được truy vấn hoặc thay đổi chính bảng đang bị statement làm thay đổi trong những ngữ cảnh Oracle coi bảng là mutating. Ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_check
AFTER INSERT OR UPDATE ON orders
FOR EACH ROW
DECLARE
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM orders
    WHERE customer_id = :NEW.customer_id;
END;
/
~~~

Trigger này truy vấn ORDERS ngay trong row-level trigger của ORDERS và có thể phát sinh ORA-04091 (table is mutating). Tại thời điểm trigger xử lý từng hàng, Oracle không cho phép truy vấn bảng đang thay đổi theo cách có thể quan sát trạng thái chưa hoàn chỉnh.

Không chữa lỗi bằng cách chuyển tùy tiện sang autonomous transaction hoặc tắt trigger. Trước hết xác định invariant; nếu có thể, dùng UNIQUE/CHECK/FK constraint hoặc viết lại DML set-based.

### Compound trigger

Compound DML trigger có nhiều timing section chia sẻ trạng thái chung trong phạm vi một statement. Nó có thể thu thập thông tin ở BEFORE/AFTER EACH ROW và thực hiện truy vấn bảng sau khi statement kết thúc ở AFTER STATEMENT, khi bảng không còn mutating đối với statement đó.

Khung minh họa:

~~~sql
CREATE OR REPLACE TRIGGER trg_orders_compound
FOR INSERT OR UPDATE ON orders
COMPOUND TRIGGER
    TYPE t_customer_ids IS TABLE OF orders.customer_id%TYPE
        INDEX BY PLS_INTEGER;
    g_customer_ids t_customer_ids;
    g_count PLS_INTEGER := 0;

    AFTER EACH ROW IS
    BEGIN
        g_count := g_count + 1;
        g_customer_ids(g_count) := :NEW.customer_id;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        FOR i IN 1 .. g_count LOOP
            -- Có thể truy vấn bảng ORDERS ở đây sau khi statement hoàn tất.
            NULL;
        END LOOP;
    END AFTER STATEMENT;
END trg_orders_compound;
/
~~~

Compound trigger có thể giải quyết một số tình huống mutating-table bằng cách trì hoãn công việc cần truy vấn bảng tới AFTER STATEMENT. Nó không tự làm cho một quy tắc nhiều hàng trở nên an toàn dưới concurrency; vẫn phải thiết kế khóa/transaction và tránh kiểm tra aggregate theo cách race-prone.

### Trigger chạy theo từng hàng có thể tốn chi phí

Nếu một UPDATE tác động một triệu hàng, row-level trigger có thể chạy một triệu lần. Nếu mỗi lần lại SELECT/INSERT/UPDATE thêm nhiều bảng, chi phí có thể tăng mạnh. Hãy cân nhắc statement-level hoặc compound trigger, set-based SQL, bulk processing và giới hạn side effect.

### Thứ tự trigger

Một bảng có thể có nhiều trigger cùng timing/event. Nếu logic phụ thuộc thứ tự, hãy thiết kế để tránh phụ thuộc ngầm hoặc dùng các cơ chế ordering Oracle hỗ trợ như FOLLOWS/PRECEDES trong phạm vi được hỗ trợ và đúng loại trigger. Không giả định thứ tự giữa các trigger nếu không được khai báo/đảm bảo.

### Trigger có thể gây đệ quy hoặc chuỗi DML

Trigger cập nhật bảng khác có thể kích hoạt trigger trên bảng đó; chuỗi trigger có thể tạo nhiều tầng DML, lỗi đệ quy hoặc khó truy vết. Tránh trigger gọi vòng lại chính bảng/chuỗi bảng, hoặc thiết kế cờ/context kiểm soát cẩn thận. Không dùng biến package làm cờ toàn cục tùy tiện vì state theo session và có thể ảnh hưởng request sau.

### Trigger có thể làm lỗi DML khó nhìn thấy

Caller có thể chỉ thấy INSERT vào bảng chính nhưng không biết trigger còn INSERT/UPDATE bảng khác. Khi trigger lỗi, statement kích hoạt có thể thất bại. Vì vậy cần tài liệu hóa trigger, kiểm tra USER_TRIGGERS, USER_ERRORS, và ghi nhận lỗi có ý nghĩa. Không bắt WHEN OTHERS rồi bỏ qua lỗi trừ khi có quy tắc xử lý lỗi rõ ràng.

## 9. Kết hợp constraint, application code và trigger

Trong hệ thống thực tế, ba cơ chế thường phối hợp thay vì loại trừ nhau. Một cách thiết kế tốt là đặt mỗi quy tắc ở tầng có thể bảo đảm nó, đồng thời tránh triển khai cùng một logic phức tạp nhiều lần.

### Ví dụ: đăng ký tài khoản với email duy nhất

**Database:**

~~~sql
CREATE TABLE app_users (
    user_id NUMBER GENERATED ALWAYS AS IDENTITY,
    email VARCHAR2(320) NOT NULL,
    display_name VARCHAR2(100) NOT NULL,
    status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
    CONSTRAINT pk_app_users PRIMARY KEY(user_id),
    CONSTRAINT uq_app_users_email UNIQUE(email),
    CONSTRAINT ck_app_users_status
        CHECK (status IN ('ACTIVE', 'DISABLED'))
);
~~~

**Application:**

1. Kiểm tra email và display name có được cung cấp.
2. Chuẩn hóa email theo quy tắc sản phẩm.
3. Có thể kiểm tra email tồn tại để đưa thông báo sớm.
4. Thực hiện INSERT.
5. Bắt ORA-00001 nếu có request khác tạo cùng email đồng thời và trả thông báo phù hợp.

**Trigger:** chỉ thêm nếu có yêu cầu audit hoặc hành vi database-wide không được bảo đảm bởi cơ chế khác. Không cần trigger để kiểm tra email trùng vì UNIQUE constraint đã làm việc đó.

### Ví dụ: ghi audit mọi thay đổi trạng thái

- Constraint bảo vệ miền status hợp lệ.
- Application kiểm tra người dùng có quyền thay đổi trạng thái và workflow có cho phép chuyển trạng thái đó.
- Trigger ghi OLD/NEW status cho mọi DML, nếu audit phải bao gồm cả script và batch.

~~~sql
ALTER TABLE app_users
ADD CONSTRAINT ck_app_users_status
CHECK (status IN ('ACTIVE', 'DISABLED', 'PENDING'));
~~~

Nếu cần audit bất biến và yêu cầu kiểm soát chặt, đánh giá thêm Oracle Unified Auditing hoặc giải pháp audit chuyên dụng thay vì mặc định viết trigger.

### Ví dụ: giá trị dẫn xuất

Nếu cần lưu tổng tiền đơn hàng:

- Nếu chỉ để hiển thị, có thể tính bằng query/view.
- Nếu dùng generated expression trên cùng hàng, cân nhắc virtual column.
- Nếu cần bảng tổng hợp cập nhật theo nhiều dòng chi tiết, cân nhắc materialized view, job hoặc event/outbox.
- Trigger có thể cập nhật tổng theo từng thay đổi order line, nhưng phải xử lý concurrency, bulk DML, delete/update và hiệu năng.

Đừng chọn trigger chỉ vì nó chạy tự động. Hãy chọn cơ chế có semantics rõ ràng và dễ tái tạo khi rebuild dữ liệu.

## 10. Constraint DEFERRABLE và quy tắc cần kiểm tra cuối transaction

Một số PRIMARY KEY/UNIQUE/FOREIGN KEY constraint có thể khai báo DEFERRABLE để trì hoãn kiểm tra tới thời điểm được yêu cầu, thường là COMMIT. Điều này hữu ích cho transaction cần trạng thái trung gian tạm thời vi phạm uniqueness nhưng cuối transaction phải hợp lệ.

~~~sql
CREATE TABLE lab_priority (
    item_id NUMBER PRIMARY KEY,
    priority_no NUMBER,
    CONSTRAINT uq_lab_priority UNIQUE(priority_no)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

Trong transaction, có thể tạm đổi chỗ hai giá trị priority rồi xác nhận cuối transaction:

~~~sql
SET CONSTRAINTS uq_lab_priority DEFERRED;

UPDATE lab_priority
SET priority_no = 20
WHERE item_id = 1;

UPDATE lab_priority
SET priority_no = 10
WHERE item_id = 2;

COMMIT;
~~~

Constraint deferred vẫn là quy tắc của database. Nó chỉ thay đổi thời điểm kiểm tra. Application phải xử lý lỗi khi SET CONSTRAINTS IMMEDIATE hoặc COMMIT phát hiện vi phạm.

### Không dùng trigger để tự mô phỏng constraint deferred

Nếu yêu cầu là uniqueness/referential integrity, hãy xem constraint DEFERRABLE trước khi nghĩ tới trigger kiểm tra trạng thái cuối. Trigger không tự có khái niệm constraint validation timing tương đương và có thể tạo lỗi concurrency khó xử lý.

## 11. Chọn cơ chế cho quy tắc nhiều hàng hoặc nhiều bảng

Không phải mọi quy tắc đều là CHECK trên một hàng. Ví dụ:

- Tổng hạn mức sử dụng của một khách hàng không được vượt ngân sách.
- Không có hai lịch đặt phòng chồng thời gian.
- Mỗi khách hàng chỉ có một đơn đang ở trạng thái OPEN.
- Số lượng hàng tồn không được âm sau nhiều giao dịch đồng thời.

Các quy tắc này cần thiết kế kỹ vì một SELECT kiểm tra rồi INSERT/UPDATE không tự an toàn dưới concurrency.

### Biểu diễn quy tắc thành constraint/index khi có thể

Ví dụ “mỗi customer chỉ có một order OPEN” có thể dùng function-based unique index:

~~~sql
CREATE UNIQUE INDEX ux_one_open_order_per_customer
ON orders (
    CASE WHEN status = 'OPEN' THEN customer_id END
);
~~~

Điều này bảo đảm tối đa một hàng có status OPEN cho mỗi customer_id khác NULL. Nếu customer_id bắt buộc, khai báo NOT NULL. Đây là unique index có điều kiện, không phải UNIQUE constraint thông thường có predicate.

### Dùng khóa để tuần tự hóa khi invariant phụ thuộc tổng hợp

Ví dụ kiểm soát ngân sách có thể khóa hàng CUSTOMER_BUDGET đại diện cho khách hàng trước khi đọc tổng và ghi khoản mới:

~~~sql
SELECT remaining_amount
INTO l_remaining
FROM customer_budget
WHERE customer_id = p_customer_id
FOR UPDATE;

IF l_remaining < p_amount THEN
    RAISE_APPLICATION_ERROR(-20020, 'Budget exceeded');
END IF;

UPDATE customer_budget
SET remaining_amount = remaining_amount - p_amount
WHERE customer_id = p_customer_id;
~~~

Mọi transaction thay đổi ngân sách của customer đó phải tuân theo cùng giao thức khóa. Nếu có đường ghi bỏ qua khóa đại diện, invariant không còn được bảo vệ. Thực hiện thao tác trong cùng transaction và không COMMIT giữa bước kiểm tra và cập nhật.

### Trigger có thể tham gia nhưng không tự giải quyết concurrency

Đặt đoạn SELECT tổng vào row trigger không làm nó an toàn. Trigger vẫn chạy trong transaction của DML và có thể gặp mutating table, race condition hoặc deadlock. Nếu trigger thực hiện khóa đại diện, mọi đường DML cần hiểu thứ tự khóa và lỗi có thể phát sinh.

### Application validation cho quy tắc nhiều bảng

Application/service thường điều phối quy trình, khóa và transaction; database constraint vẫn bảo vệ các phần có thể khai báo. Nếu cần đảm bảo ở database cho nhiều ứng dụng cùng ghi, cân nhắc stored procedure/API duy nhất, quyền DML hạn chế trên bảng nền và buộc caller đi qua API. Thiết kế này cần đánh giá quyền, transaction và đường quản trị.

## 12. Chẩn đoán constraint và trigger trong Oracle

Khi DML thất bại hoặc trigger chạy ngoài dự kiến, hãy kiểm tra metadata thay vì chỉ nhìn source code ứng dụng.

### Xem constraint của bảng

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       validated,
       deferrable,
       deferred,
       search_condition
FROM user_constraints
WHERE table_name = 'APP_USERS'
ORDER BY constraint_type, constraint_name;
~~~

CONSTRAINT_TYPE thường là P (primary key), U (unique), R (foreign key), C (check/not null). Các view dictionary có thể biểu diễn NOT NULL dưới dạng constraint type C.

### Xem các cột thuộc constraint

~~~sql
SELECT constraint_name,
       table_name,
       column_name,
       position
FROM user_cons_columns
WHERE table_name = 'APP_USERS'
ORDER BY constraint_name, position;
~~~

### Xem trigger của bảng

~~~sql
SELECT trigger_name,
       triggering_event,
       trigger_type,
       status,
       when_clause
FROM user_triggers
WHERE table_name = 'APP_USERS'
ORDER BY trigger_name;
~~~

### Xem source và lỗi biên dịch trigger

~~~sql
SELECT name, type, line, text
FROM user_source
WHERE type = 'TRIGGER'
  AND name = 'TRG_CUSTOMERS_STATUS_AUDIT'
ORDER BY line;

SELECT name, type, line, position, text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
~~~

### Xem trigger đang ENABLE hay DISABLE

~~~sql
ALTER TRIGGER trg_customers_status_audit DISABLE;
ALTER TRIGGER trg_customers_status_audit ENABLE;
~~~

Không disable trigger trong production chỉ để làm DML chạy qua mà chưa hiểu side effect. Khi disable, hành vi audit/logic tự động có thể bị bỏ qua; dữ liệu tạo trong khoảng đó có thể không được đồng bộ. Nếu cần maintenance, lập kế hoạch catch-up và kiểm tra tính toàn vẹn sau khi bật lại.

## 13. Ánh xạ lỗi Oracle sang lỗi nghiệp vụ

Constraint thường trả về mã lỗi Oracle chuẩn. Application/service nên nhận diện đúng lỗi và chuyển thành phản hồi có ý nghĩa, thay vì phụ thuộc vào việc pre-check có thể thành công hay không.

| Mã lỗi | Nguyên nhân thường gặp | Phản hồi ứng dụng gợi ý |
| --- | --- | --- |
| ORA-00001 | Vi phạm unique constraint hoặc unique index | Email/mã định danh đã được sử dụng; yêu cầu chọn giá trị khác. |
| ORA-01400 | Insert NULL vào cột NOT NULL | Thiếu trường bắt buộc. |
| ORA-02290 | Vi phạm CHECK constraint | Một giá trị không thỏa miền/điều kiện được phép. |
| ORA-02291 | Vi phạm parent key của FOREIGN KEY | Bản ghi cha không tồn tại hoặc tham chiếu không hợp lệ. |
| ORA-02292 | Parent key đang được hàng con tham chiếu | Không thể xóa/cập nhật bản ghi đang được sử dụng. |
| ORA-04091 | Mutating table trong trigger | Sửa thiết kế trigger/logic; không lặp lại DML vô hạn. |
| ORA-04098 | Trigger invalid và không thể revalidate khi chạy | Kiểm tra source, USER_ERRORS và dependency. |

Tên constraint có thể xuất hiện trong thông báo ORA-00001/ORA-02290; ứng dụng có thể dùng tên đó để phân biệt lỗi cụ thể. Không nên phụ thuộc vào việc parse toàn bộ message text nếu driver cung cấp vendor error code/constraint name riêng.

### Không retry mọi lỗi constraint

ORA-00001 thường không được giải quyết bằng retry cùng dữ liệu; cần báo conflict hoặc chạy logic idempotency phù hợp. Lỗi kết nối/timeout có thể cần retry có kiểm soát. Phân loại lỗi trước khi retry để tránh tạo duplicate hoặc lặp tác dụng phụ.

### Constraint deferred có thể lỗi tại COMMIT

Nếu constraint DEFERRABLE INITIALLY DEFERRED, statement DML có thể thành công nhưng COMMIT mới phát hiện vi phạm. Application phải bao quanh cả DML và COMMIT trong cùng luồng xử lý lỗi, không chỉ bắt exception ngay tại INSERT/UPDATE.

## 14. Bài thực hành: constraint, application validation và trigger

Thực hiện trong schema học tập có quyền CREATE TABLE, CREATE SEQUENCE và CREATE TRIGGER. DDL có implicit commit trong Oracle; không chạy trên bảng nghiệp vụ thật.

### Bước 1: tạo bảng và constraint

~~~sql
CREATE TABLE lab_users (
    user_id NUMBER
        CONSTRAINT pk_lab_users PRIMARY KEY,
    email VARCHAR2(200) NOT NULL,
    status VARCHAR2(20) DEFAULT 'ACTIVE' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT uq_lab_users_email UNIQUE(email),
    CONSTRAINT ck_lab_users_status
        CHECK (status IN ('ACTIVE', 'DISABLED'))
);
~~~

Thử chèn dữ liệu hợp lệ:

~~~sql
INSERT INTO lab_users(user_id, email, status)
VALUES (1, 'mai@example.com', 'ACTIVE');

INSERT INTO lab_users(user_id, email, status)
VALUES (2, 'an@example.com', 'ACTIVE');

COMMIT;
~~~

Thử từng lệnh riêng để quan sát lỗi:

~~~sql
-- Vi phạm NOT NULL:
INSERT INTO lab_users(user_id, email)
VALUES (3, NULL);

-- Vi phạm CHECK:
INSERT INTO lab_users(user_id, email, status)
VALUES (4, 'bad@example.com', 'UNKNOWN');

-- Vi phạm UNIQUE:
INSERT INTO lab_users(user_id, email, status)
VALUES (5, 'mai@example.com', 'ACTIVE');
~~~

Mỗi câu lệnh vi phạm sẽ bị Oracle từ chối. Nếu chạy trong script client tự dừng sau lỗi, thực hiện từng câu riêng.

### Bước 2: mô phỏng application validation

Ứng dụng có thể kiểm tra sớm trước khi INSERT:

~~~sql
DECLARE
    l_email lab_users.email%TYPE := 'mai@example.com';
    l_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM lab_users
    WHERE email = l_email;

    IF l_count > 0 THEN
        DBMS_OUTPUT.PUT_LINE('Email already exists');
    ELSE
        INSERT INTO lab_users(user_id, email)
        VALUES (10, l_email);
    END IF;
END;
/
~~~

Đoạn này cho thông báo sớm nếu email đã tồn tại. Nhưng hãy nhớ hai session có thể cùng kiểm tra khi chưa có hàng và cùng cố INSERT; UNIQUE constraint mới là lớp bảo vệ cuối cùng. Để kiểm tra race condition, mở hai session và thực hiện SELECT trước khi session nào INSERT, sau đó INSERT cùng email. Một transaction sẽ gặp unique conflict khi transaction còn lại commit.

### Bước 3: tạo bảng audit và sequence

~~~sql
CREATE TABLE lab_user_audit (
    audit_id NUMBER PRIMARY KEY,
    user_id NUMBER NOT NULL,
    old_status VARCHAR2(20),
    new_status VARCHAR2(20),
    changed_at TIMESTAMP NOT NULL
);

CREATE SEQUENCE seq_lab_user_audit START WITH 1 INCREMENT BY 1;
~~~

### Bước 4: tạo trigger audit

~~~sql
CREATE OR REPLACE TRIGGER trg_lab_user_status_audit
AFTER UPDATE OF status ON lab_users
FOR EACH ROW
WHEN (OLD.status <> NEW.status)
BEGIN
    INSERT INTO lab_user_audit (
        audit_id,
        user_id,
        old_status,
        new_status,
        changed_at
    )
    VALUES (
        seq_lab_user_audit.NEXTVAL,
        :NEW.user_id,
        :OLD.status,
        :NEW.status,
        SYSTIMESTAMP
    );
END;
/
~~~

### Bước 5: quan sát trigger

~~~sql
UPDATE lab_users
SET status = 'DISABLED'
WHERE user_id = 1;

SELECT user_id, email, status
FROM lab_users
WHERE user_id = 1;

SELECT user_id, old_status, new_status, changed_at
FROM lab_user_audit
WHERE user_id = 1;

COMMIT;
~~~

Trigger ghi audit trong cùng transaction. Thử ROLLBACK thay vì COMMIT trong một lần chạy riêng: cả thay đổi status và audit row đều bị rollback. Sequence NEXTVAL không bị rollback; sequence có thể có gap và không phải bộ đếm transaction.

### Bước 6: xem metadata

~~~sql
SELECT constraint_name, constraint_type, status, validated
FROM user_constraints
WHERE table_name = 'LAB_USERS'
ORDER BY constraint_type, constraint_name;

SELECT trigger_name, triggering_event, trigger_type, status
FROM user_triggers
WHERE table_name = 'LAB_USERS';

SELECT name, type, line, text
FROM user_errors
WHERE name = 'TRG_LAB_USER_STATUS_AUDIT'
ORDER BY sequence;
~~~

### Bước 7: dọn dữ liệu

~~~sql
DROP TRIGGER trg_lab_user_status_audit;
DROP SEQUENCE seq_lab_user_audit;
DROP TABLE lab_user_audit PURGE;
DROP TABLE lab_users PURGE;
~~~

Chỉ chạy sau khi hoàn thành lab và không cần giữ dữ liệu. DROP là DDL và có implicit commit.

## 15. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Ứng dụng kiểm tra không có duplicate nhưng INSERT vẫn lỗi ORA-00001 | Transaction khác INSERT cùng key sau bước pre-check | Giữ UNIQUE constraint và xử lý conflict khi DML. |
| Batch job ghi dữ liệu sai quy tắc | Validation chỉ có ở một application client | Đưa invariant vào constraint hoặc API database được kiểm soát. |
| Trigger audit không chạy | Trigger DISABLED, sai event hoặc câu DML không thỏa điều kiện WHEN | Kiểm tra USER_TRIGGERS, triggering_event, status và WHEN clause. |
| Trigger lỗi làm INSERT/UPDATE thất bại | Exception trong trigger làm statement kích hoạt lỗi | Kiểm tra USER_ERRORS/source và xử lý nguyên nhân; không nuốt lỗi tùy tiện. |
| ORA-04091 | Row-level trigger truy vấn bảng đang mutating | Dùng constraint/set-based SQL hoặc compound trigger/thiết kế transaction phù hợp. |
| Audit row biến mất khi rollback | Audit insert cùng transaction với DML chính | Đây là hành vi nhất quán nếu audit chỉ phản ánh thay đổi commit; dùng autonomous audit chỉ khi yêu cầu độc lập rõ ràng. |
| Trigger gọi API ngoài làm DML chậm | Trigger đồng bộ gọi dịch vụ ngoài | Dùng outbox và worker bất đồng bộ. |
| Dữ liệu bị cập nhật nhiều lần ngoài dự kiến | Trigger tạo chuỗi DML/đệ quy | Vẽ lại dependency, loại vòng lặp và dùng API tường minh. |
| Trigger row-level làm bulk DML chậm | Trigger chạy một lần mỗi hàng và làm thêm nhiều SQL | Giảm công việc, dùng compound/statement-level hoặc set-based logic. |
| Trigger không ghi đúng end-user | SESSION_USER là schema account dùng chung | Thiết lập application context an toàn hoặc audit tại tầng nhận diện user. |
| Constraint lỗi khi COMMIT | Constraint DEFERRABLE được kiểm tra cuối transaction | Bắt lỗi ở transaction boundary và xác định dữ liệu vi phạm. |

## 16. Câu hỏi tự kiểm tra

1. **Constraint phù hợp nhất với loại quy tắc nào?** Invariant dữ liệu phải được database bảo đảm cho mọi nguồn DML.
2. **Application validation phù hợp khi nào?** Khi cần ngữ cảnh request, quyền, workflow hoặc phản hồi thân thiện cho người dùng.
3. **Trigger phù hợp khi nào?** Khi cần phản ứng tự động với sự kiện database cho mọi nguồn DML hoặc xử lý view/event đặc biệt.
4. **Vì sao SELECT kiểm tra duplicate không thay UNIQUE constraint?** Vì hai transaction có thể cùng kiểm tra trước khi một transaction INSERT.
5. **CHECK constraint có tự cấm NULL không?** Không; UNKNOWN không bị loại theo cách như FALSE, nên thêm NOT NULL nếu cần.
6. **FOREIGN KEY có tự tạo index ở bảng con không?** Không; cân nhắc index theo workload.
7. **Trigger BEFORE EACH ROW có thể làm gì với :NEW?** Có thể gán giá trị :NEW trước khi row được ghi.
8. **Trigger AFTER EACH ROW có thể gán :NEW không?** Không; chỉ đọc OLD/NEW.
9. **Statement-level trigger chạy mấy lần?** Một lần cho statement, kể cả khi statement tác động 0 hàng.
10. **Row-level trigger chạy mấy lần?** Một lần cho mỗi hàng bị tác động.
11. **Mutating-table error là gì?** ORA-04091 khi row trigger truy vấn/thay đổi bảng đang bị statement làm mutating trong ngữ cảnh bị cấm.
12. **Compound trigger có ích gì?** Chia sẻ trạng thái qua timing sections và trì hoãn việc cần truy vấn bảng tới AFTER STATEMENT.
13. **Trigger có thể COMMIT transaction caller không?** Trigger thông thường không thể điều khiển transaction của caller.
14. **Vì sao không gửi email trực tiếp từ trigger?** Dịch vụ ngoài có thể chậm/lỗi và không cùng transaction; nên dùng outbox/worker.
15. **Audit trigger thông thường có rollback theo DML không?** Có, vì audit insert cùng transaction.
16. **Khi nào cân nhắc autonomous transaction cho audit?** Chỉ khi audit phải tồn tại độc lập với rollback và hệ thống chấp nhận semantics đó.
17. **Trigger có thay authorization không?** Không; trigger không tự biết end-user khi session dùng chung schema account.
18. **ORA-00001 nên xử lý thế nào?** Nhận diện conflict, trả lỗi nghiệp vụ hoặc xử lý idempotency; không retry mù quáng.
19. **Khi constraint deferred có thể phát sinh lỗi lúc nào?** Khi chuyển sang IMMEDIATE hoặc COMMIT kiểm tra constraint.
20. **Trước khi viết trigger nên kiểm tra gì?** Constraint, DEFAULT, identity, virtual column, view, SQL set-based, package/API tường minh và cơ chế audit sẵn có.

Hãy dùng constraint cho các invariant dữ liệu mà Oracle có thể khai báo, application code cho validation theo request, quyền và workflow, còn trigger cho hành vi gắn với sự kiện database mà cần chạy tự động cho mọi nguồn DML. Có thể phối hợp cả ba: ứng dụng kiểm tra sớm, constraint bảo vệ dữ liệu dưới concurrency, trigger ghi audit hoặc hỗ trợ view. Trước khi thêm trigger, hãy cân nhắc tác dụng phụ ngầm, mutating-table, transaction, hiệu năng và khả năng vận hành; logic quan trọng cần được tài liệu hóa và có cách chẩn đoán rõ ràng.
