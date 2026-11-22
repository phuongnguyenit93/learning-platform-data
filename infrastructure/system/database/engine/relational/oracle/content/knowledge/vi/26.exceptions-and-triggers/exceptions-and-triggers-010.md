# DDL/database event trigger và ranh giới quyền quản trị trong Oracle

Trong Oracle Database, trigger không chỉ chạy khi một hàng được INSERT, UPDATE hoặc DELETE. Database còn hỗ trợ trigger phản ứng với các sự kiện DDL như CREATE, ALTER, DROP, TRUNCATE, cũng như các sự kiện ở cấp database/session như LOGON, LOGOFF, STARTUP, SHUTDOWN và SERVERERROR. Các trigger này thường được dùng để ghi nhận thay đổi schema, áp dụng quy tắc quản trị, ghi dấu phiên đăng nhập hoặc thực hiện một số hành động vận hành có kiểm soát.

Khả năng chạy ở phạm vi toàn schema hoặc toàn database đồng nghĩa với rủi ro lớn hơn trigger DML thông thường. Một DDL trigger viết sai có thể chặn thao tác triển khai; một LOGON trigger lỗi có thể khiến người dùng không đăng nhập được; một trigger ghi audit có thể tạo tải hoặc phát sinh lỗi ngay trong quá trình quản trị. Vì vậy, cần hiểu rõ **phạm vi sự kiện**, **quyền tạo trigger**, **quyền mà trigger sử dụng khi chạy** và **ranh giới giữa trigger tùy biến với cơ chế bảo mật/audit của Oracle**.

Bài học thuộc nhóm **Lỗi và trigger** của Database Engine Relational Oracle. Nội dung tập trung vào DDL trigger cấp schema/database, database event trigger, các hàm ORA_* cung cấp ngữ cảnh sự kiện, quyền CREATE TRIGGER và ADMINISTER DATABASE TRIGGER, quyền trực tiếp trong trigger body, cách ghi audit/chặn DDL, giới hạn vận hành và chẩn đoán.

Sau bài này, bạn có thể:

- Phân biệt DML trigger, DDL trigger và database event trigger.
- Chọn ON SCHEMA hay ON DATABASE theo phạm vi cần giám sát.
- Nhận diện các sự kiện CREATE, ALTER, DROP, TRUNCATE, LOGON, LOGOFF, STARTUP, SHUTDOWN và SERVERERROR.
- Dùng ORA_SYSEVENT, ORA_DICT_OBJ_NAME, ORA_DICT_OBJ_OWNER, ORA_LOGIN_USER và các event attributes phù hợp.
- Viết trigger ghi nhận DDL hoặc ngăn một số thao tác schema theo policy.
- Phân biệt CREATE TRIGGER, CREATE ANY TRIGGER và ADMINISTER DATABASE TRIGGER.
- Hiểu trigger chạy với quyền của owner và yêu cầu direct grants cho stored code.
- Nhận diện rủi ro khi trigger ảnh hưởng login, DDL deployment và transaction.
- Kiểm tra trigger, trạng thái, dependency và lỗi compile bằng data dictionary.
- Phân biệt trigger audit tùy biến với Oracle Unified Auditing.
- Xây dựng quy trình triển khai, thử nghiệm và vô hiệu hóa trigger an toàn.

> **Phạm vi ví dụ:** Cú pháp minh họa theo Oracle Database 19c. Các object có hậu tố _LAB dành cho schema thực hành. Trigger ON DATABASE có phạm vi rộng và cần quyền quản trị phù hợp; chỉ thử trong database lab hoặc môi trường được DBA phê duyệt.

## 1. Các loại trigger và phạm vi hoạt động

Oracle có nhiều loại trigger, phân biệt theo sự kiện làm chúng chạy.

| Loại trigger | Sự kiện kích hoạt | Phạm vi |
| --- | --- | --- |
| DML trigger | INSERT, UPDATE, DELETE | Bảng hoặc view |
| DDL trigger | CREATE, ALTER, DROP, TRUNCATE và các DDL event được hỗ trợ | Schema hoặc database |
| Database event trigger | LOGON, LOGOFF, STARTUP, SHUTDOWN, SERVERERROR, SUSPEND và event được hỗ trợ | Database |
| INSTEAD OF trigger | DML trên view không thể cập nhật trực tiếp | View |

### 1.1. DML trigger

DML trigger phản ứng với thay đổi dữ liệu:

~~~sql
CREATE OR REPLACE TRIGGER trg_employee_dml_lab
BEFORE UPDATE OF monthly_salary
ON employee_data_lab
FOR EACH ROW
BEGIN
    IF :NEW.monthly_salary < 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Salary cannot be negative');
    END IF;
END;
/
~~~

Trigger này gắn với bảng và chạy khi DML phù hợp xảy ra. FOR EACH ROW khiến trigger chạy cho từng hàng được tác động.

### 1.2. DDL trigger

DDL trigger chạy khi có DDL event trong phạm vi schema/database:

~~~sql
CREATE OR REPLACE TRIGGER trg_ddl_audit_lab
AFTER DDL ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        SYSTIMESTAMP
    );
END;
/
~~~

Đây là schema-level DDL trigger. Nó phản ứng với DDL thuộc schema chứa trigger.

### 1.3. Database event trigger

Database event trigger chạy theo sự kiện của database hoặc session, ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER trg_logon_audit_lab
AFTER LOGON ON DATABASE
BEGIN
    NULL;
END;
/
~~~

ON DATABASE thể hiện phạm vi database. Trigger có thể được kích hoạt khi session đăng nhập, thay vì khi một bảng cụ thể bị thay đổi.

### 1.4. DDL trigger không phải row trigger

DDL trigger chạy theo DDL statement/event, không có :OLD và :NEW như row-level DML trigger. Không khai báo FOR EACH ROW cho DDL trigger. Một câu ALTER TABLE là một sự kiện DDL; trigger không chạy một lần cho mỗi hàng trong bảng.

## 2. DDL trigger: ON SCHEMA và ON DATABASE

Hai phạm vi phổ biến:

### 2.1. ON SCHEMA

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_owner_lab
AFTER DDL ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        SYSTIMESTAMP
    );
END;
/
~~~

Trigger này chỉ giám sát DDL trong schema sở hữu trigger. Nó phù hợp khi một schema ứng dụng muốn theo dõi thay đổi object của chính mình mà không cần giám sát toàn database.

### 2.2. ON DATABASE

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_database_lab
AFTER DDL ON DATABASE
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        SYSTIMESTAMP
    );
END;
/
~~~

Database-level DDL trigger có thể quan sát DDL ở phạm vi rộng hơn, bao gồm nhiều schema. Đây là trigger quản trị có ảnh hưởng lớn; chỉ DBA hoặc owner được cấp quyền phù hợp mới nên tạo và quản lý.

### 2.3. So sánh phạm vi

| Tiêu chí | ON SCHEMA | ON DATABASE |
| --- | --- | --- |
| Phạm vi | Schema chứa trigger | Toàn database theo event được đăng ký |
| Quyền tạo | CREATE TRIGGER trong schema của mình, theo quy tắc object | ADMINISTER DATABASE TRIGGER và các điều kiện liên quan |
| Mục đích | Kiểm soát/audit thay đổi của ứng dụng | Chính sách/audit quản trị ở phạm vi database |
| Rủi ro | Ảnh hưởng một schema | Có thể ảnh hưởng nhiều schema và hoạt động database |
| Vận hành | Thường do owner ứng dụng phối hợp DBA | Cần quy trình DBA và review quyền chặt chẽ |

### 2.4. ON SCHEMA không bắt được DDL của schema khác

Nếu trigger thuộc APP_OWNER, DDL do DATA_OWNER thực hiện trong DATA_OWNER không nằm trong phạm vi ON SCHEMA của APP_OWNER. Nếu yêu cầu là giám sát nhiều schema, cần cân nhắc database-level DDL trigger hoặc cơ chế auditing phù hợp.

Không tạo một trigger trong schema ứng dụng rồi giả định nó là audit toàn database.

## 3. Các DDL event thường gặp

DDL trigger có thể đăng ký một hoặc nhiều event mà Oracle hỗ trợ.

| Event | Ví dụ thao tác |
| --- | --- |
| CREATE | CREATE TABLE, CREATE VIEW, CREATE PROCEDURE |
| ALTER | ALTER TABLE, ALTER INDEX, ALTER PACKAGE |
| DROP | DROP TABLE, DROP VIEW, DROP PROCEDURE |
| TRUNCATE | TRUNCATE TABLE hoặc partition |
| RENAME | RENAME object |
| COMMENT | COMMENT ON TABLE/COLUMN |
| GRANT | GRANT privilege hoặc role |
| REVOKE | REVOKE privilege hoặc role |
| ANALYZE | ANALYZE object theo cú pháp được hỗ trợ |

Danh sách event và cú pháp đăng ký phải đối chiếu SQL Language Reference của release. Một trigger có thể bắt một event:

~~~sql
CREATE OR REPLACE TRIGGER audit_drop_lab
AFTER DROP ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name, object_type, object_name,
        object_owner, login_user, event_time
    )
    VALUES (
        ORA_SYSEVENT, ORA_DICT_OBJ_TYPE, ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER, ORA_LOGIN_USER, SYSTIMESTAMP
    );
END;
/
~~~

Hoặc nhiều event:

~~~sql
CREATE OR REPLACE TRIGGER audit_schema_ddl_lab
AFTER CREATE OR ALTER OR DROP OR TRUNCATE ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name, object_type, object_name,
        object_owner, login_user, event_time
    )
    VALUES (
        ORA_SYSEVENT, ORA_DICT_OBJ_TYPE, ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER, ORA_LOGIN_USER, SYSTIMESTAMP
    );
END;
/
~~~

Một số thao tác DDL liên quan nhiều bước hoặc object đặc biệt có thể tạo các event theo semantics riêng. Nếu policy phụ thuộc chính xác vào một thao tác, hãy thử trên đúng release và xác nhận event trigger nhận được.

## 4. BEFORE DDL và AFTER DDL

### 4.1. BEFORE DDL

BEFORE DDL trigger chạy trước khi database thực hiện DDL event. Nó hữu ích khi cần kiểm tra policy và từ chối thao tác:

~~~sql
CREATE OR REPLACE TRIGGER protect_table_drop_lab
BEFORE DROP ON SCHEMA
BEGIN
    IF ORA_DICT_OBJ_TYPE = 'TABLE'
       AND ORA_DICT_OBJ_NAME IN ('CUSTOMER', 'ORDERS')
    THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Dropping protected tables is not allowed'
        );
    END IF;
END;
/
~~~

Nếu thao tác DROP thuộc điều kiện bị chặn, trigger phát sinh lỗi và DDL không được tiếp tục theo quy trình bình thường.

### 4.2. AFTER DDL

AFTER DDL trigger chạy sau khi DDL event đã được thực hiện theo semantics Oracle. Nó thường được dùng để ghi nhận sự kiện hoặc thực hiện xử lý hậu sự kiện:

~~~sql
CREATE OR REPLACE TRIGGER record_table_create_lab
AFTER CREATE ON SCHEMA
WHEN (ORA_DICT_OBJ_TYPE = 'TABLE')
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name, object_type, object_name,
        object_owner, login_user, event_time
    )
    VALUES (
        ORA_SYSEVENT, ORA_DICT_OBJ_TYPE, ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER, ORA_LOGIN_USER, SYSTIMESTAMP
    );
END;
/
~~~

WHEN trong DDL trigger là điều kiện trigger-level; các event attributes có thể được dùng trong điều kiện phù hợp. Nếu biểu thức điều kiện phức tạp hoặc cần xử lý nhiều nhánh, đặt logic trong thân trigger.

### 4.3. Chọn BEFORE hay AFTER

| Nhu cầu | Lựa chọn |
| --- | --- |
| Chặn DROP/ALTER không được phép | BEFORE DDL |
| Ghi nhận DDL đã xảy ra | AFTER DDL |
| Kiểm tra metadata trước thao tác | BEFORE DDL |
| Ghi lại kết quả/sự kiện sau thao tác | AFTER DDL |

Không dùng AFTER trigger để ngăn thao tác vốn đã thực hiện. Ngược lại, BEFORE trigger không nên ghi log với thông điệp “DDL thành công” vì thao tác có thể còn thất bại sau đó.

## 5. Event attributes: đọc ngữ cảnh sự kiện

Oracle cung cấp các hàm/attribute có tiền tố ORA_ để trigger biết sự kiện nào vừa xảy ra và object nào liên quan.

### 5.1. Các thuộc tính DDL thường dùng

| Attribute | Ý nghĩa |
| --- | --- |
| ORA_SYSEVENT | Tên sự kiện, ví dụ CREATE, ALTER, DROP |
| ORA_DICT_OBJ_TYPE | Loại object bị tác động, ví dụ TABLE, VIEW, PROCEDURE |
| ORA_DICT_OBJ_NAME | Tên object |
| ORA_DICT_OBJ_OWNER | Owner của object |
| ORA_LOGIN_USER | User đăng nhập thực hiện sự kiện |
| ORA_DATABASE_NAME | Tên database |
| ORA_INSTANCE_NUM | Số instance hiện tại |
| ORA_CLIENT_IP_ADDRESS | Địa chỉ IP client nếu có |
| ORA_IS_ALTER_COLUMN | Thông tin liên quan ALTER COLUMN trong ngữ cảnh được hỗ trợ |

Không phải mọi attribute đều có ý nghĩa cho mọi event. Với LOGON trigger, thông tin object DDL như ORA_DICT_OBJ_NAME không phải trọng tâm; hãy dùng attribute phù hợp với loại event.

### 5.2. ORA_SYSEVENT

ORA_SYSEVENT trả về event hiện tại:

~~~sql
IF ORA_SYSEVENT = 'DROP' THEN
    ...
END IF;
~~~

Nó giúp một trigger xử lý nhiều event bằng các nhánh khác nhau. Tuy nhiên, nếu mỗi event có logic rất khác, tách trigger theo event có thể dễ review hơn.

### 5.3. ORA_DICT_OBJ_NAME và ORA_DICT_OBJ_OWNER

Hai thuộc tính này giúp xác định object bị tác động:

~~~sql
DBMS_OUTPUT.PUT_LINE(
    ORA_DICT_OBJ_OWNER || '.' ||
    ORA_DICT_OBJ_NAME || ' (' ||
    ORA_DICT_OBJ_TYPE || ')'
);
~~~

Đối với event không gắn với một object cụ thể, các thuộc tính object có thể không có giá trị hữu ích. Không giả định chúng luôn khác NULL.

### 5.4. ORA_LOGIN_USER

ORA_LOGIN_USER cho biết database user đăng nhập gắn với event. Đây là thông tin audit hữu ích, nhưng không đồng nghĩa với danh tính con người cuối cùng trong mọi ứng dụng. Nhiều ứng dụng dùng một database service account cho nhiều end users; nếu cần end-user identity, ứng dụng phải truyền/ghi nhận context tin cậy theo cơ chế được quản lý.

### 5.5. ORA_CLIENT_IP_ADDRESS

Có thể ghi địa chỉ IP client nếu môi trường cung cấp. Không coi IP là danh tính xác thực đầy đủ. NAT, proxy, connection pool và middle tier có thể khiến IP chỉ là địa chỉ của máy chủ ứng dụng.

### 5.6. ORA_SQL_TXT

Trong DDL trigger, ORA_SQL_TXT có thể cung cấp các mảnh văn bản của câu SQL kích hoạt event. Đây là dữ liệu hữu ích cho điều tra nhưng cần ghép các mảnh đúng cách, xử lý độ dài và giới hạn kiểu dữ liệu. Không dùng chuỗi SQL ghi nhận được để thực thi lại.

Ví dụ khái niệm:

~~~sql
DECLARE
    l_sql_parts ORA_NAME_LIST_T;
    l_part_count PLS_INTEGER;
    l_sql_text CLOB;
BEGIN
    l_part_count := ORA_SQL_TXT(l_sql_parts);

    FOR i IN 1 .. l_part_count LOOP
        l_sql_text := l_sql_text || l_sql_parts(i);
    END LOOP;

    -- Ghi l_sql_text vao bang audit neu policy cho phep.
END;
/
~~~

Hãy xác nhận datatype và giới hạn của ORA_NAME_LIST_T/ORA_SQL_TXT trong tài liệu đúng release. Câu SQL có thể chứa literal nhạy cảm; cân nhắc masking và quyền truy cập audit log trước khi lưu toàn văn.

## 6. Tạo bảng audit và DDL trigger

Ví dụ sau minh họa audit DDL trong schema lab.

### 6.1. Tạo bảng audit

~~~sql
CREATE TABLE ddl_audit_lab (
    audit_id       NUMBER GENERATED BY DEFAULT AS IDENTITY,
    event_name     VARCHAR2(30),
    object_type    VARCHAR2(30),
    object_name    VARCHAR2(128),
    object_owner   VARCHAR2(128),
    login_user     VARCHAR2(128),
    database_name  VARCHAR2(128),
    client_ip      VARCHAR2(64),
    event_time     TIMESTAMP WITH TIME ZONE,
    CONSTRAINT pk_ddl_audit_lab PRIMARY KEY (audit_id)
);
~~~

Identity column được hỗ trợ trong các release hiện đại; nếu database mục tiêu cũ hơn, dùng sequence và cơ chế sinh khóa tương ứng.

### 6.2. Tạo schema-level DDL audit trigger

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_schema_lab
AFTER DDL ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        database_name,
        client_ip,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        ORA_DATABASE_NAME,
        ORA_CLIENT_IP_ADDRESS,
        SYSTIMESTAMP
    );
END;
/
~~~

Trigger thuộc schema chứa bảng audit. Khi owner thực hiện DDL trong schema đó, trigger ghi lại event và object metadata.

### 6.3. Thử nghiệm

~~~sql
CREATE TABLE ddl_probe_lab (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);

ALTER TABLE ddl_probe_lab ADD created_at TIMESTAMP;

CREATE INDEX ix_ddl_probe_lab ON ddl_probe_lab(id);

SELECT
    audit_id,
    event_name,
    object_type,
    object_name,
    object_owner,
    login_user,
    event_time
FROM ddl_audit_lab
ORDER BY audit_id;
~~~

Có thể thấy các event CREATE/ALTER tương ứng. Event cụ thể được ghi phụ thuộc các DDL thực sự chạy và loại trigger đăng ký.

### 6.4. DDL trigger tự ghi audit cũng là dependency

Trigger phụ thuộc bảng DDL_AUDIT_LAB. Nếu bảng audit bị DROP/ALTER không tương thích hoặc quyền INSERT bị thu hồi, trigger có thể INVALID hoặc thất bại khi chạy. Khi đó một DDL mới trong schema có thể bị ảnh hưởng bởi trigger audit.

Hãy bảo vệ bảng audit, kiểm tra trigger status và có kế hoạch vô hiệu hóa/khôi phục trigger trong migration khi cần.

## 7. Database-level DDL trigger

Khi cần theo dõi DDL trên nhiều schema, database-level trigger có thể là lựa chọn:

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_database_lab
AFTER DDL ON DATABASE
BEGIN
    INSERT INTO audit_owner.ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        database_name,
        client_ip,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        ORA_DATABASE_NAME,
        ORA_CLIENT_IP_ADDRESS,
        SYSTIMESTAMP
    );
END;
/
~~~

Ví dụ này giả định trigger owner được cấp trực tiếp quyền INSERT trên AUDIT_OWNER.DDL_AUDIT_LAB. Tên schema và quyền phải được thay theo môi trường thật.

### 7.1. Tách owner trigger và owner audit

~~~text
SECURITY_ADMIN
  - owns database DDL trigger
  - receives ADMINISTER DATABASE TRIGGER
  - receives direct INSERT on AUDIT_OWNER.DDL_AUDIT

AUDIT_OWNER
  - owns audit table
  - controls retention and read access

APPLICATION_OWNER
  - owns application objects
  - does not need database-wide trigger privilege
~~~

Mô hình này tách trách nhiệm quản trị trigger, sở hữu dữ liệu audit và phát triển ứng dụng. Hãy cấp quyền tối thiểu cần thiết, không dùng SYS hoặc DBA account làm owner ứng dụng chỉ để tạo trigger.

### 7.2. Kiểm soát phạm vi database-level

Database-level DDL trigger có thể chạy cho thao tác từ nhiều schema. Vì vậy:

- Chỉ ghi các metadata thật sự cần.
- Tránh gọi nhiều package nghiệp vụ trong trigger.
- Không thực hiện xử lý nặng hoặc truy vấn sâu dictionary cho mỗi DDL.
- Có kế hoạch khi bảng audit hoặc tablespace audit gặp lỗi.
- Kiểm thử các thao tác quản trị, deploy, patch và maintenance.

### 7.3. Trigger database-wide có thể trở thành điểm lỗi chung

Nếu trigger database-wide lỗi với mọi DDL, nhiều nhóm ứng dụng có thể không triển khai được object. Nếu trigger LOGON lỗi, nhiều user có thể không đăng nhập được. Đây là lý do quyền tạo và quản trị trigger cấp database phải được giới hạn và có runbook phục hồi.

## 8. Database event trigger

Database event trigger phản ứng với sự kiện ở cấp database hoặc session. Cú pháp khái quát:

~~~sql
CREATE OR REPLACE TRIGGER trigger_name
{BEFORE | AFTER} event_name
ON DATABASE
BEGIN
    ...
END;
/
~~~

Các event thường gặp gồm:

| Event | Timing thường dùng | Mục đích minh họa |
| --- | --- | --- |
| LOGON | AFTER LOGON | Ghi nhận session đăng nhập, thiết lập context |
| LOGOFF | BEFORE LOGOFF | Ghi nhận session sắp kết thúc |
| STARTUP | AFTER STARTUP | Ghi nhận database vừa mở/khởi động theo event |
| SHUTDOWN | BEFORE SHUTDOWN | Ghi nhận hoạt động trước khi database shutdown |
| SERVERERROR | AFTER SERVERERROR | Theo dõi một số server errors |
| SUSPEND | AFTER SUSPEND | Xử lý thông tin khi resumable statement bị suspend |

Tính khả dụng và timing của từng event cần đối chiếu SQL Language Reference. Không dùng một timing cho mọi event.

## 9. LOGON trigger

### 9.1. Ghi nhận đăng nhập

Tạo bảng audit session:

~~~sql
CREATE TABLE logon_audit_lab (
    audit_id NUMBER GENERATED BY DEFAULT AS IDENTITY,
    login_user VARCHAR2(128),
    event_time TIMESTAMP WITH TIME ZONE,
    client_ip VARCHAR2(64),
    database_name VARCHAR2(128)
);
~~~

Trigger:

~~~sql
CREATE OR REPLACE TRIGGER audit_logon_lab
AFTER LOGON ON DATABASE
BEGIN
    INSERT INTO logon_audit_lab (
        login_user,
        event_time,
        client_ip,
        database_name
    )
    VALUES (
        ORA_LOGIN_USER,
        SYSTIMESTAMP,
        ORA_CLIENT_IP_ADDRESS,
        ORA_DATABASE_NAME
    );
END;
/
~~~

Đây là ví dụ khái niệm. Trigger owner phải có quyền INSERT trực tiếp trên bảng audit nếu bảng thuộc schema khác.

### 9.2. Rủi ro của LOGON trigger

LOGON trigger nằm trên đường đăng nhập. Nếu nó:

- Gọi object INVALID.
- INSERT vào bảng không truy cập được.
- Gọi network service bị timeout.
- Gặp lỗi quota/tablespace.
- Phát sinh exception không xử lý.

thì login có thể thất bại. Không đặt truy vấn nặng, remote call hoặc logic nghiệp vụ phức tạp vào LOGON trigger.

### 9.3. LOGON trigger và application user

Một database user có thể phục vụ hàng nghìn end users qua connection pool. ORA_LOGIN_USER chỉ cho biết database account. Nếu cần end-user identity, dùng cơ chế application context được thiết lập an toàn sau authentication; không tin một giá trị client có thể tùy ý đặt.

### 9.4. Thiết lập session context

LOGON trigger đôi khi được dùng để thiết lập session-level defaults hoặc context. Hãy bảo đảm:

- Giá trị thiết lập không phụ thuộc dữ liệu không đáng tin.
- Không để context từ session pool cũ rò sang request mới.
- Reset context khi trả connection về pool.
- Không dùng trigger để cấp quyền vượt qua authorization của ứng dụng.

## 10. LOGOFF trigger

LOGOFF trigger có thể dùng để ghi nhận session kết thúc:

~~~sql
CREATE OR REPLACE TRIGGER audit_logoff_lab
BEFORE LOGOFF ON DATABASE
BEGIN
    NULL;
END;
/
~~~

Trong thực tế, logoff trigger cần rất thận trọng:

- Session có thể kết thúc trong điều kiện lỗi hoặc mạng bị ngắt.
- Không nên phụ thuộc vào việc trigger luôn chạy để ghi nhận mọi disconnect.
- Không thực hiện công việc kéo dài trong đường logoff.
- Dùng audit/session monitoring chuyên dụng nếu cần độ bao phủ vận hành cao.

Logoff trigger không thay thế việc theo dõi session, client disconnect hoặc Unified Auditing.

## 11. STARTUP và SHUTDOWN trigger

### 11.1. AFTER STARTUP

Ví dụ:

~~~sql
CREATE OR REPLACE TRIGGER record_startup_lab
AFTER STARTUP ON DATABASE
BEGIN
    INSERT INTO database_event_audit_lab (
        event_name,
        event_time,
        login_user
    )
    VALUES (
        'STARTUP',
        SYSTIMESTAMP,
        ORA_LOGIN_USER
    );
END;
/
~~~

AFTER STARTUP được kích hoạt theo event startup ở timing Oracle hỗ trợ. Trigger nên làm công việc ngắn và phụ thuộc tối thiểu vào các object đã sẵn sàng.

### 11.2. BEFORE SHUTDOWN

~~~sql
CREATE OR REPLACE TRIGGER record_shutdown_lab
BEFORE SHUTDOWN ON DATABASE
BEGIN
    NULL;
END;
/
~~~

Không dùng SHUTDOWN trigger để thực hiện backup lớn, gọi remote service hoặc chạy quy trình cần nhiều phút. Hoạt động shutdown cần có tính dự đoán; trigger phức tạp có thể làm quy trình vận hành khó kiểm soát.

### 11.3. Startup/shutdown không phải scheduler

Trigger startup/shutdown không nên được dùng làm bộ lập lịch công việc tổng quát. Nếu cần chạy batch định kỳ, dùng Oracle Scheduler hoặc hệ thống orchestration phù hợp. Event trigger chỉ nên xử lý hành động gắn trực tiếp với lifecycle event và phải rất ngắn.

## 12. SERVERERROR trigger

### 12.1. Theo dõi một nhóm lỗi

~~~sql
CREATE OR REPLACE TRIGGER audit_server_error_lab
AFTER SERVERERROR ON DATABASE
BEGIN
    IF ORA_IS_SERVERERROR(942) THEN
        INSERT INTO database_error_audit_lab (
            login_user,
            error_code,
            event_time
        )
        VALUES (
            ORA_LOGIN_USER,
            ORA_SERVER_ERROR(1),
            SYSTIMESTAMP
        );
    END IF;
END;
/
~~~

Ví dụ lọc ORA-00942 (table or view does not exist). ORA_IS_SERVERERROR kiểm tra mã lỗi có nằm trong stack hiện tại hay không; ORA_SERVER_ERROR(n) đọc mã lỗi tại vị trí tương ứng theo API Oracle.

### 12.2. Không ghi lại mọi lỗi một cách tùy tiện

SERVERERROR trigger có thể được kích hoạt bởi lỗi do chính trigger hoặc logic audit gây ra, tạo vòng lặp hoặc lỗi phụ. Hãy:

- Lọc một tập mã lỗi có ý nghĩa.
- Không thực hiện truy vấn phức tạp.
- Không gọi lại object dễ gây cùng lỗi.
- Không để bảng audit trở thành dependency không ổn định.
- Kiểm thử trường hợp audit table không truy cập được.

### 12.3. SERVERERROR không thay thế application error handling

Trigger này không cung cấp đầy đủ request context của ứng dụng và không thay thế exception handling tại API/service. Hãy xử lý lỗi ở nơi có thông tin nghiệp vụ, đồng thời dùng auditing/monitoring cho điều tra database-wide.

## 13. SUSPEND event và resumable space allocation

Oracle hỗ trợ AFTER SUSPEND event trigger cho tình huống resumable statement bị suspend, thường liên quan không gian hoặc tài nguyên cần thiết cho thao tác. Đây là tính năng quản trị chuyên biệt, không phải trigger thông thường cho mọi lỗi SQL.

~~~sql
CREATE OR REPLACE TRIGGER audit_suspend_lab
AFTER SUSPEND ON DATABASE
BEGIN
    NULL;
END;
/
~~~

Khi sử dụng event này, cần tìm hiểu resumable space allocation, timeout và các hàm cung cấp thông tin lỗi/segment như tài liệu Oracle của release. Không đặt logic tự động cấp phát storage không giới hạn hoặc thay đổi cấu hình hệ thống trong trigger.

## 14. Quyền tạo trigger: CREATE TRIGGER, ANY và ADMINISTER DATABASE TRIGGER

Đây là ranh giới quyền quan trọng nhất của bài học.

### 14.1. CREATE TRIGGER

CREATE TRIGGER cho phép user tạo trigger trong schema của chính mình theo quy tắc Oracle. Ví dụ APP_OWNER có thể tạo DML trigger trên bảng của mình hoặc schema-level DDL trigger:

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_lab
AFTER DDL ON SCHEMA
BEGIN
    NULL;
END;
/
~~~

Quyền này không tự cho phép tạo trigger trong schema người khác hoặc tạo trigger database-wide.

### 14.2. CREATE ANY TRIGGER

CREATE ANY TRIGGER là system privilege rộng hơn, cho phép tạo trigger trong schema của user khác theo quy tắc Oracle. Đây là quyền mạnh vì trigger có thể chạy trong luồng DML/DDL của schema đích.

Không cấp CREATE ANY TRIGGER cho developer thông thường chỉ để họ tiện triển khai một trigger ở schema ứng dụng. Hãy để owner schema tạo object của mình hoặc dùng deployment identity được quản lý.

### 14.3. ADMINISTER DATABASE TRIGGER

ADMINISTER DATABASE TRIGGER là system privilege liên quan đến việc tạo/quản trị database-level triggers. Nó cho phép tạo trigger ở phạm vi database cho các DDL/database events được hỗ trợ.

Quyền này có phạm vi ảnh hưởng lớn: người được cấp có thể tạo trigger tác động tới hoạt động nhiều schema hoặc session. Chỉ cấp cho DBA/security administrator đáng tin cậy và theo quy trình change management.

### 14.4. Không nhầm ba quyền

| Quyền | Phạm vi chính | Mức ảnh hưởng |
| --- | --- | --- |
| CREATE TRIGGER | Tạo trigger trong schema của mình | Schema owner |
| CREATE ANY TRIGGER | Tạo trigger trong schema khác | Rộng, tác động schema khác |
| ADMINISTER DATABASE TRIGGER | Tạo/quản trị database-level trigger | Toàn database |

Tên quyền và điều kiện cụ thể cần đối chiếu tài liệu SQL Language Reference/Administrator's Guide của release. Cấp quyền không nên dựa trên suy đoán từ tên.

### 14.5. ALTER ANY TRIGGER và DROP ANY TRIGGER

Để quản trị trigger thuộc schema khác, có thể cần quyền hệ thống tương ứng như ALTER ANY TRIGGER hoặc DROP ANY TRIGGER, tùy thao tác. Các quyền ANY cũng có phạm vi rộng và cần hạn chế.

Owner trigger thường quản lý trigger của mình; DBA có thể dùng quyền quản trị phù hợp. Hãy tách quyền tạo, sửa, enable/disable và drop theo nguyên tắc least privilege nếu quy trình tổ chức yêu cầu.

## 15. Quyền khi trigger chạy: definer rights và direct grants

Quyền tạo trigger và quyền mà trigger sử dụng khi chạy là hai vấn đề khác nhau.

### 15.1. Trigger chạy theo quyền của owner

Trigger PL/SQL chạy với quyền của schema sở hữu trigger theo mô hình definer-rights; trigger không có mệnh đề AUTHID CURRENT_USER như procedure/package. Vì vậy, các object được tham chiếu trong trigger body cần quyền phù hợp cho owner.

### 15.2. Direct grant cho object khác schema

Giả sử AUDIT_OWNER sở hữu bảng:

~~~sql
CREATE TABLE ddl_audit_lab (
    event_name VARCHAR2(30),
    object_name VARCHAR2(128),
    event_time TIMESTAMP
);
~~~

SECURITY_ADMIN sở hữu database trigger và cần ghi vào bảng audit:

~~~sql
GRANT INSERT ON audit_owner.ddl_audit_lab TO security_admin;
~~~

Trigger body:

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_db_lab
AFTER DDL ON DATABASE
BEGIN
    INSERT INTO audit_owner.ddl_audit_lab (
        event_name,
        object_name,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_NAME,
        SYSTIMESTAMP
    );
END;
/
~~~

Quyền INSERT được cấp trực tiếp cho SECURITY_ADMIN. Một role có quyền INSERT không thay thế direct object grant trong stored definer-rights code cần compile static SQL.

### 15.3. Trigger không tự có quyền SYS

Tạo database-level trigger không biến trigger owner thành SYS và không cấp mọi quyền quản trị database cho trigger body. Trigger chạy theo quyền của owner và các quyền được cấp hợp lệ. Không dùng ADMINISTER DATABASE TRIGGER như lý do để cấp thêm DBA/SYSDBA cho owner.

### 15.4. Least privilege cho trigger owner

Một schema chuyên trách có thể chỉ cần:

- Quyền tạo/quản trị database trigger theo yêu cầu.
- INSERT trực tiếp vào bảng audit.
- EXECUTE trên package tiện ích thật sự cần.
- SELECT trên metadata/object cần thiết nếu được phép.

Tránh cấp DBA, SELECT ANY TABLE, EXECUTE ANY PROCEDURE hoặc quyền rộng khác nếu trigger chỉ cần ghi vài cột audit.

## 16. Ranh giới quản trị: trigger không thay thế quyền object

### 16.1. Trigger policy không phải lớp authorization duy nhất

Một BEFORE DROP trigger có thể chặn một số thao tác theo tên object, nhưng không thay thế:

- Object privileges.
- System privileges.
- Role design.
- Schema ownership.
- Separation of duties.
- Oracle auditing.
- Quy trình change management.

Trigger có thể bị owner/quản trị viên đủ quyền disable hoặc drop. Người có quyền quản trị cao có thể có cách vận hành ngoài policy trigger. Do đó, trigger chỉ là lớp kiểm soát bổ sung.

### 16.2. Bảo vệ object bằng privilege trước

Nếu developer không được phép DROP một bảng production, đừng cấp quyền DROP/ALTER không cần thiết rồi hy vọng DDL trigger sẽ ngăn họ. Hãy kiểm soát quyền object/schema và dùng account deployment có phạm vi được phê duyệt.

### 16.3. Database-level trigger là quyền nhạy cảm

Một trigger LOGON có thể tác động mọi lần đăng nhập; một DDL trigger có thể ảnh hưởng nhiều schema. Quyền tạo database trigger nên được quản lý như quyền quản trị hệ thống, có phê duyệt, review code, test và rollback plan.

## 17. DDL transaction semantics và trigger side effects

### 17.1. DDL có implicit commit

Oracle DDL thường có implicit commit trước khi thực hiện và commit sau khi DDL thành công theo quy tắc transaction của Oracle. Vì vậy, không coi DDL như một câu UPDATE có thể ROLLBACK trong cùng transaction.

Nếu ứng dụng có:

~~~sql
UPDATE business_table SET status = 'READY';
CREATE TABLE new_table (...);
ROLLBACK;
~~~

thì UPDATE có thể đã được commit trước khi DDL chạy. ROLLBACK sau đó không hoàn tác phần đã commit bởi implicit commit.

### 17.2. Trigger body không phải nơi quản lý transaction

Không gọi COMMIT hoặc ROLLBACK tùy tiện trong trigger. Trigger thông thường chạy trong transaction context của statement kích hoạt; lỗi trigger có thể ảnh hưởng statement. Nếu cần ghi audit độc lập với transaction chính, phải thiết kế autonomous transaction có chủ đích và hiểu rằng audit record có thể tồn tại dù thao tác nghiệp vụ/DDL không hoàn tất.

### 17.3. Autonomous transaction chỉ dùng khi có yêu cầu rõ

Ví dụ khái niệm:

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_autonomous_lab
AFTER DDL ON SCHEMA
DECLARE
    PRAGMA AUTONOMOUS_TRANSACTION;
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name, object_type, object_name,
        object_owner, login_user, event_time
    )
    VALUES (
        ORA_SYSEVENT, ORA_DICT_OBJ_TYPE, ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER, ORA_LOGIN_USER, SYSTIMESTAMP
    );

    COMMIT;
END;
/
~~~

Đây là mẫu kỹ thuật, không phải mặc định nên áp dụng. Autonomous transaction có thể ghi audit ngay cả khi DDL phía ngoài thất bại hoặc bị hủy. Điều đó có thể hữu ích để lưu dấu attempt, nhưng cần phân biệt rõ trạng thái ATTEMPTED và SUCCEEDED; không ghi audit với ý nghĩa DDL chắc chắn thành công nếu chỉ biết trigger đã chạy.

### 17.4. Tránh DDL lồng trong DDL trigger

Không thiết kế DDL trigger để tự tạo/drop/alter nhiều object mỗi khi một DDL khác xảy ra. Cách làm này dễ tạo đệ quy, dependency khó quản lý, implicit commit khó dự đoán và có thể gặp các hạn chế của system trigger. Dùng deployment tool hoặc Oracle Scheduler/job có kiểm soát cho migration thay vì biến DDL trigger thành engine tự thay đổi schema.

## 18. Chặn DDL theo policy

Một trường hợp dùng BEFORE DDL là chặn DROP một số bảng quan trọng trong schema:

~~~sql
CREATE OR REPLACE TRIGGER protect_core_tables_lab
BEFORE DROP ON SCHEMA
BEGIN
    IF ORA_DICT_OBJ_TYPE = 'TABLE'
       AND ORA_DICT_OBJ_NAME IN (
           'CUSTOMER',
           'ORDERS',
           'PAYMENT'
       )
    THEN
        RAISE_APPLICATION_ERROR(
            -20030,
            'Core table cannot be dropped by this schema policy'
        );
    END IF;
END;
/
~~~

### 18.1. Dùng allowlist/denylist có kiểm soát

Policy có thể kiểm tra:

- Event CREATE/ALTER/DROP.
- Object type.
- Object name/owner.
- Login user.
- Thời điểm hoặc change window.

Tránh hard-code quá nhiều quy tắc trong trigger nếu policy thay đổi thường xuyên. Có thể lưu policy trong bảng cấu hình được bảo vệ, nhưng việc đọc bảng cấu hình phải ngắn và có kế hoạch khi bảng không truy cập được.

### 18.2. Không dùng tên object đơn lẻ làm ranh giới bảo mật

Object name có thể trùng giữa schema. Với database-level trigger, phải xét cả ORA_DICT_OBJ_OWNER và ORA_DICT_OBJ_NAME. Tên object được chuẩn hóa theo quy tắc identifier Oracle; quoted identifiers có semantics khác chữ hoa mặc định.

### 18.3. Policy trigger cần cơ chế break-glass

Nếu trigger chặn nhầm DDL cần thiết, DBA cần quy trình phục hồi:

1. Xác định trigger và lỗi.
2. Dùng account có quyền quản trị đã được phê duyệt.
3. Disable trigger tạm thời nếu chính sách cho phép.
4. Thực hiện DDL được phê duyệt.
5. Enable lại trigger.
6. Xác nhận status và ghi audit/change record.

Không tạo trigger policy mà không có cách xử lý khi chính trigger bị lỗi.

## 19. Dữ liệu audit, Unified Auditing và giới hạn của trigger

### 19.1. Trigger audit là cơ chế tùy biến

DDL trigger có thể ghi metadata theo định dạng ứng dụng cần, ví dụ batch ID, module, owner, object type hoặc thông tin deployment. Nó hữu ích cho workflow nội bộ nhưng có một số giới hạn:

- Trigger có thể bị disable/drop bởi người đủ quyền.
- Trigger có thể INVALID hoặc lỗi vì dependency.
- Trigger có thể làm DDL thất bại nếu audit insert lỗi.
- Trigger chỉ ghi những event và ngữ cảnh mà code được thiết kế để xử lý.
- Dynamic SQL/application identity có thể không được phản ánh đầy đủ.

### 19.2. Unified Auditing

Oracle Unified Auditing là cơ chế auditing của database, có policy và audit trail riêng. Với yêu cầu bảo mật/compliance, hãy đánh giá Unified Auditing và các audit policies phù hợp thay vì tự xây trigger cho mọi loại audit.

Ví dụ một câu lệnh tạo audit policy cần được xác định theo action/object cần theo dõi và release:

~~~sql
CREATE AUDIT POLICY audit_ddl_policy_lab
    ACTIONS CREATE TABLE, ALTER TABLE, DROP TABLE;

AUDIT POLICY audit_ddl_policy_lab;
~~~

Cú pháp và tập action hỗ trợ cần đối chiếu SQL Language Reference/Licensing/Administrator's Guide của release. Việc dùng Unified Auditing có cấu hình, retention và quyền truy cập audit trail riêng.

### 19.3. Không lưu dữ liệu nhạy cảm không cần thiết

ORA_SQL_TXT có thể chứa literal trong DDL. Logon/servererror metadata cũng có thể nhạy cảm. Hãy:

- Chỉ ghi trường cần thiết.
- Mask literal/secret nếu có.
- Giới hạn quyền SELECT trên bảng audit.
- Đặt retention và archive policy.
- Bảo vệ tablespace và backup audit.
- Tránh ghi password/token/credential vào log.

### 19.4. Audit trigger không phải bằng chứng đầy đủ duy nhất

Nếu yêu cầu là điều tra ai thực hiện DDL, thời điểm, kết quả và nguồn truy cập, hãy kết hợp Unified Auditing, database logs, deployment pipeline, application identity và change-management records. Trigger audit có thể là một nguồn bổ sung.

## 20. Enable, disable và quản lý trigger

### 20.1. Xem trigger

~~~sql
SELECT
    trigger_name,
    trigger_type,
    triggering_event,
    base_object_type,
    table_name,
    status
FROM user_triggers
ORDER BY trigger_name;
~~~

USER_TRIGGERS hiển thị trigger thuộc schema hiện tại. ALL_TRIGGERS và DBA_TRIGGERS mở rộng phạm vi theo quyền.

### 20.2. Xem trigger database-level

Trong view phù hợp, kiểm tra BASE_OBJECT_TYPE và TRIGGERING_EVENT để phân biệt trigger gắn với bảng, schema hay database. Với database-level trigger, TABLE_NAME có thể không áp dụng như table trigger.

### 20.3. Enable/disable

~~~sql
ALTER TRIGGER audit_ddl_schema_lab DISABLE;

ALTER TRIGGER audit_ddl_schema_lab ENABLE;
~~~

Disable trigger là thay đổi vận hành quan trọng. Khi disable, event sẽ không được trigger ghi nhận/chặn theo logic đó. Cần audit cả hành động disable/enable bằng cơ chế phù hợp.

### 20.4. Kiểm tra lỗi compile

~~~sql
SELECT name, type, line, position, text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
~~~

Trigger INVALID có thể làm event xử lý lỗi khi kích hoạt. Luôn compile/test trước khi enable ở production.

### 20.5. Drop trigger

~~~sql
DROP TRIGGER audit_ddl_schema_lab;
~~~

Chỉ owner hoặc user có quyền phù hợp mới được drop trigger. Với database-level trigger, tuân theo quyền quản trị database trigger và change process.

## 21. Kiểm tra quyền và dependency

### 21.1. Quyền hệ thống của user hiện tại

~~~sql
SELECT privilege
FROM user_sys_privs
ORDER BY privilege;
~~~

SESSION_PRIVS cho biết system privileges hiện có trong session:

~~~sql
SELECT privilege
FROM session_privs
ORDER BY privilege;
~~~

Để xem quyền user khác, DBA có thể dùng DBA_SYS_PRIVS/DBA_ROLE_PRIVS theo quyền được cấp.

### 21.2. Direct object grants

~~~sql
SELECT
    owner,
    table_name,
    grantee,
    privilege,
    grantable
FROM all_tab_privs
WHERE grantee = USER
ORDER BY owner, table_name, privilege;
~~~

Đây là một cách kiểm tra object privileges mà session có thể nhìn thấy. Với stored trigger, xác nhận quyền trực tiếp cho trigger owner; không chỉ kiểm tra role membership.

### 21.3. Dependency của trigger

~~~sql
SELECT
    name,
    type,
    referenced_owner,
    referenced_name,
    referenced_type
FROM user_dependencies
WHERE type = 'TRIGGER'
ORDER BY name, referenced_owner, referenced_name;
~~~

Dependency giúp tìm bảng/package/type mà trigger tham chiếu. Dynamic SQL có thể không được thể hiện đầy đủ.

### 21.4. Object status

~~~sql
SELECT object_name, object_type, status, last_ddl_time
FROM user_objects
WHERE object_type = 'TRIGGER'
ORDER BY object_name;
~~~

Trước khi enable trigger, xác nhận status VALID và không còn lỗi trong USER_ERRORS.

## 22. Rủi ro vận hành và cách giảm thiểu

### 22.1. Trigger làm DDL deployment thất bại

Một DDL trigger audit phụ thuộc bảng audit. Nếu tablespace đầy, bảng audit unavailable hoặc quyền INSERT bị thu hồi, DDL trong phạm vi trigger có thể thất bại. Hãy xác định policy:

- Fail closed: không cho DDL chạy nếu audit không ghi được.
- Fail open: cho phép DDL nhưng ghi lỗi audit qua kênh khác.

Đây là quyết định quản trị/bảo mật. Không tự chọn fail open cho audit bắt buộc hoặc fail closed cho mọi DDL mà chưa đánh giá tác động.

### 22.2. LOGON trigger chặn login

Giữ logic ngắn, tránh remote calls và dependency phức tạp. Luôn có DBA recovery path để disable trigger nếu lỗi khiến không thể đăng nhập bằng user thông thường.

### 22.3. SERVERERROR trigger tạo lỗi lặp

Nếu trigger ghi audit gặp lỗi và chính lỗi đó kích hoạt SERVERERROR trigger lần nữa, có thể tạo chuỗi lỗi. Lọc event, tránh truy vấn phụ thuộc và thử tình huống audit table unavailable.

### 22.4. Database-level trigger làm tăng coupling

Một trigger database-wide có thể ràng buộc nhiều schema vào một bảng audit/package chung. Nếu owner audit thay đổi cấu trúc hoặc package invalid, nhiều hoạt động database có thể bị ảnh hưởng. Tách dependency, kiểm thử và quản lý version cẩn thận.

### 22.5. Dùng Scheduler cho công việc dài

Trigger nên phản ứng nhanh. Nếu cần gửi email, gọi service, xử lý file hoặc chạy báo cáo dài, ghi một event/job vào queue hoặc bảng điều phối rồi để Oracle Scheduler/application worker xử lý sau. Không kéo dài thời gian DDL/login bằng công việc không đồng bộ.

## 23. Bài thực hành tổng hợp

Lab này dùng schema riêng và chỉ tạo schema-level DDL trigger để không cần quyền database-wide.

### Bước 1 — Tạo bảng audit

~~~sql
CREATE TABLE ddl_audit_lab (
    audit_id NUMBER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    event_name VARCHAR2(30),
    object_type VARCHAR2(30),
    object_name VARCHAR2(128),
    object_owner VARCHAR2(128),
    login_user VARCHAR2(128),
    event_time TIMESTAMP WITH TIME ZONE
);
~~~

### Bước 2 — Tạo DDL trigger

~~~sql
CREATE OR REPLACE TRIGGER audit_ddl_lab
AFTER DDL ON SCHEMA
BEGIN
    INSERT INTO ddl_audit_lab (
        event_name,
        object_type,
        object_name,
        object_owner,
        login_user,
        event_time
    )
    VALUES (
        ORA_SYSEVENT,
        ORA_DICT_OBJ_TYPE,
        ORA_DICT_OBJ_NAME,
        ORA_DICT_OBJ_OWNER,
        ORA_LOGIN_USER,
        SYSTIMESTAMP
    );
END;
/
~~~

### Bước 3 — Tạo và sửa object thử nghiệm

~~~sql
CREATE TABLE ddl_probe_lab (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);

ALTER TABLE ddl_probe_lab ADD created_at TIMESTAMP;

CREATE INDEX ix_ddl_probe_lab ON ddl_probe_lab(id);
~~~

### Bước 4 — Xem audit

~~~sql
SELECT
    audit_id,
    event_name,
    object_type,
    object_name,
    object_owner,
    login_user,
    event_time
FROM ddl_audit_lab
ORDER BY audit_id;
~~~

### Bước 5 — Tạo trigger chặn DROP bảng được bảo vệ

~~~sql
CREATE OR REPLACE TRIGGER protect_ddl_probe_lab
BEFORE DROP ON SCHEMA
BEGIN
    IF ORA_DICT_OBJ_TYPE = 'TABLE'
       AND ORA_DICT_OBJ_NAME = 'DDL_PROBE_LAB'
    THEN
        RAISE_APPLICATION_ERROR(
            -20031,
            'DDL_PROBE_LAB is protected'
        );
    END IF;
END;
/
~~~

Thử:

~~~sql
DROP TABLE ddl_probe_lab;
~~~

Lệnh DROP sẽ bị trigger policy chặn. Sau đó có thể disable trigger trong lab để dọn:

~~~sql
ALTER TRIGGER protect_ddl_probe_lab DISABLE;
DROP TABLE ddl_probe_lab PURGE;
~~~

### Bước 6 — Kiểm tra trigger và dependency

~~~sql
SELECT trigger_name, triggering_event, base_object_type, status
FROM user_triggers
ORDER BY trigger_name;

SELECT name, type, referenced_name, referenced_type
FROM user_dependencies
WHERE type = 'TRIGGER'
ORDER BY name, referenced_name;

SELECT name, type, line, position, text
FROM user_errors
WHERE type = 'TRIGGER'
ORDER BY name, sequence;
~~~

### Bước 7 — Dọn lab

~~~sql
DROP TRIGGER audit_ddl_lab;
DROP TRIGGER protect_ddl_probe_lab;
DROP TABLE ddl_audit_lab PURGE;
~~~

Chỉ chạy lệnh dọn khi chắc chắn object thuộc lab. DROP là DDL có implicit commit.

## 24. Checklist thiết kế và triển khai

**Phạm vi**

- Đây là DDL event hay database event?
- Chỉ cần ON SCHEMA hay thật sự cần ON DATABASE?
- Có những event nào cần bắt?
- Trigger chạy BEFORE hay AFTER?
- Event attributes nào hợp lệ và cần thiết?

**Quyền**

- Owner trigger là ai?
- User có CREATE TRIGGER, CREATE ANY TRIGGER hay ADMINISTER DATABASE TRIGGER phù hợp chưa?
- Trigger có cần ALTER/DROP privilege rộng không?
- Các object khác schema đã có direct grants chưa?
- Có đang cấp DBA/SYSDBA quá mức không?

**Logic**

- Trigger có làm ít công việc nhất có thể không?
- Có nguy cơ đệ quy hoặc gọi lại object đang lỗi không?
- Có exception handling phù hợp không?
- DDL policy có allowlist/denylist và owner qualification không?
- Có cần lưu full SQL text hay chỉ metadata?

**Vận hành**

- Đã thử trong database cùng release/edition chưa?
- LOGON/DDL/ERROR trigger lỗi sẽ ảnh hưởng thế nào?
- Có break-glass procedure để disable/repair không?
- Có theo dõi trigger INVALID và audit table health không?
- Công việc dài đã chuyển sang Scheduler/queue chưa?
- Audit tùy biến có đang bị dùng thay Unified Auditing không?

## 25. Câu hỏi tự kiểm tra

1. DDL trigger khác DML trigger ở sự kiện kích hoạt nào?
2. DDL trigger có thể dùng FOR EACH ROW không?
3. ON SCHEMA khác ON DATABASE thế nào?
4. Vì sao ON SCHEMA không audit được DDL của schema khác?
5. BEFORE DDL và AFTER DDL khác nhau ở thời điểm nào?
6. ORA_SYSEVENT trả về gì?
7. ORA_DICT_OBJ_NAME và ORA_DICT_OBJ_OWNER dùng để làm gì?
8. ORA_LOGIN_USER có luôn là end-user của ứng dụng không?
9. ORA_SQL_TXT có thể dùng để làm gì và có rủi ro nào?
10. Những database events nào thường được dùng?
11. Vì sao LOGON trigger cần logic tối giản?
12. SERVERERROR trigger có nguy cơ gì nếu audit code cũng phát sinh lỗi?
13. CREATE TRIGGER và CREATE ANY TRIGGER khác nhau thế nào?
14. ADMINISTER DATABASE TRIGGER dùng cho phạm vi nào?
15. Vì sao không nên cấp quyền database trigger cho developer thông thường?
16. Trigger chạy theo quyền của ai?
17. Vì sao direct grants quan trọng với stored trigger?
18. Trigger audit có thay thế object privileges không?
19. DDL implicit commit ảnh hưởng trigger thế nào?
20. Khi nào cân nhắc autonomous transaction cho audit?
21. Vì sao không nên thực hiện DDL lồng trong DDL trigger?
22. Unified Auditing khác trigger audit ở vai trò nào?
23. USER_TRIGGERS và USER_ERRORS dùng để kiểm tra gì?
24. Khi nào nên dùng Oracle Scheduler thay cho trigger?
25. Cần có quy trình nào nếu LOGON trigger khiến user không đăng nhập được?

**Gợi ý trả lời:**

1. DDL trigger chạy theo CREATE/ALTER/DROP...; DML trigger chạy theo INSERT/UPDATE/DELETE.
2. Không; DDL trigger là statement/event-level, không phải row-level.
3. ON SCHEMA giới hạn schema owner; ON DATABASE áp dụng phạm vi database.
4. Vì trigger chỉ nhận DDL thuộc schema chứa nó.
5. BEFORE chạy trước DDL; AFTER chạy sau event theo semantics Oracle.
6. Tên sự kiện hiện tại.
7. Xác định object bị tác động và schema sở hữu object.
8. Không; ứng dụng có thể dùng shared service account.
9. Ghi nhận SQL text để điều tra; cần xử lý độ dài và dữ liệu nhạy cảm.
10. LOGON, LOGOFF, STARTUP, SHUTDOWN, SERVERERROR, SUSPEND.
11. Vì lỗi trigger có thể chặn login.
12. Lỗi lặp/đệ quy và làm tăng sự cố.
13. CREATE TRIGGER tạo trong schema mình; CREATE ANY TRIGGER tạo ở schema khác.
14. Tạo/quản trị database-level triggers theo quyền Oracle.
15. Vì trigger có thể tác động nhiều schema và hoạt động toàn database.
16. Owner trigger theo mô hình definer-rights.
17. Stored code không dựa vào role grants như quyền compile static SQL; cần direct grants phù hợp.
18. Không; trigger policy là lớp bổ sung, không thay privilege model.
19. DDL có implicit commit; không coi trigger DML như một phần rollbackable của transaction ứng dụng.
20. Khi cần ghi audit độc lập, hiểu rõ record có thể tồn tại dù DDL thất bại.
21. Dễ đệ quy, dependency khó quản lý và transaction behavior khó dự đoán.
22. Unified Auditing là cơ chế audit database; trigger audit là logic tùy biến.
23. USER_TRIGGERS xem định nghĩa/trạng thái; USER_ERRORS xem compile errors.
24. Khi cần công việc dài/định kỳ/async thay vì phản ứng đồng bộ trong trigger.
25. DBA recovery path để xác định và disable/repair trigger bằng account được phê duyệt.

## Tài liệu Oracle tham khảo

- [Oracle Database PL/SQL Language Reference — DDL Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/ddl-triggers.html): DDL trigger, schema/database scope và event attributes.
- [Oracle Database PL/SQL Language Reference — System Triggers](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/system-triggers.html): database event triggers và timing.
- [Oracle Database SQL Language Reference — CREATE TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TRIGGER.html): cú pháp tạo trigger và privilege liên quan.
- [Oracle Database SQL Language Reference — ALTER TRIGGER](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TRIGGER.html): enable, disable và compile trigger.
- [Oracle Database Reference — USER_TRIGGERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_TRIGGERS.html): metadata trigger trong schema.
- [Oracle Database Reference — USER_ERRORS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_ERRORS.html): lỗi biên dịch trigger và stored objects.
- [Oracle Database Security Guide — Configuring Auditing](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-audit-policies.html): audit policies và Unified Auditing.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): quản trị database và quyền hệ thống.

**Nguyên tắc cần nhớ:** DDL trigger và database event trigger có thể tác động tới schema hoặc toàn database, vì vậy quyền tạo trigger phải tương xứng với phạm vi. CREATE TRIGGER dành cho schema owner; CREATE ANY TRIGGER mở rộng sang schema khác; ADMINISTER DATABASE TRIGGER cho phép quản trị trigger cấp database theo quy tắc Oracle. Trigger chạy theo quyền owner và cần direct grants cho dependency. Hãy giữ logic ngắn, có recovery path, dùng privilege model và Unified Auditing làm nền tảng quản trị; coi trigger tùy biến là lớp hỗ trợ có kiểm soát.
