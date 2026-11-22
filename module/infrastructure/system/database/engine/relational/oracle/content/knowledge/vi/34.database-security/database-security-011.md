# Unified Auditing, audit policy và tra cứu dấu vết thao tác trong Oracle Database

Unified Auditing là cơ chế kiểm toán tập trung của Oracle Database. Thay vì chỉ bật một loại audit rời rạc cho từng câu lệnh, DBA có thể định nghĩa **audit policy** mô tả hành động, quyền hoặc đối tượng cần theo dõi, sau đó bật policy cho toàn hệ thống hoặc một nhóm user. Các sự kiện được ghi vào unified audit trail để phục vụ điều tra bảo mật, theo dõi thay đổi và chứng minh tuân thủ.

Một quy trình audit có ích phải trả lời được bốn câu hỏi:

1. **Ai** thực hiện hành động? Database user, proxy user, OS user hoặc client identity nào?
2. **Làm gì**? Đăng nhập, đọc bảng, cập nhật dữ liệu, thay đổi cấu hình hay sử dụng system privilege?
3. **Ở đâu và khi nào**? Object nào, thời điểm nào, client/host nào, trong container nào?
4. **Kết quả ra sao**? Thành công hay thất bại, return code nào, câu SQL nào được thực thi?

Bài học lấy Oracle Database 19c làm mốc. Nội dung đi từ kiến trúc Unified Auditing, trạng thái mixed/pure mode, cách tạo và bật audit policy, các policy có sẵn, truy vấn UNIFIED_AUDIT_TRAIL, phân quyền người xem audit, Fine-Grained Auditing, quản lý vòng đời audit trail và quy trình điều tra một sự kiện.

## 1. Audit trong database có mục tiêu gì?

### 1.1. Kiểm toán là bằng chứng về hoạt động

Audit trail ghi lại các sự kiện đã được cấu hình để theo dõi. Nó hỗ trợ:

- Điều tra truy cập trái phép hoặc hành vi bất thường.
- Theo dõi việc sử dụng quyền mạnh như CREATE ANY TABLE hoặc ALTER SYSTEM.
- Biết ai đã đọc hoặc thay đổi một bảng nhạy cảm.
- Theo dõi đăng nhập thành công/thất bại.
- Kiểm tra các thay đổi về user, role, privilege và cấu hình.
- Hỗ trợ yêu cầu tuân thủ, kiểm toán nội bộ và quy trình ứng cứu sự cố.

Audit trail là nguồn bằng chứng kỹ thuật. Nó không tự chứng minh động cơ của người dùng, cũng không thay thế application log, hệ điều hành log, network log hoặc quy trình quản lý danh tính.

### 1.2. Audit khác logging ứng dụng

Application log thường mô tả nghiệp vụ như “người dùng tạo đơn hàng” hoặc “request hoàn tất”. Database audit ghi nhận hoạt động ở tầng database như user nào thực hiện SELECT, UPDATE, DDL hoặc sử dụng privilege.

Hai nguồn bổ trợ nhau:

| Nguồn | Thường trả lời |
| --- | --- |
| Unified audit trail | Database account nào thực hiện hành động gì trên database/object |
| Application log | Người dùng nghiệp vụ, request ID và quy trình ứng dụng |
| OS/security log | Process, host, đăng nhập hệ điều hành và sự kiện máy chủ |
| Network/security gateway | Kết nối, nguồn mạng và lưu lượng |
| Identity provider | Danh tính đã xác thực, MFA và vòng đời tài khoản |

Để truy vết end-to-end, ứng dụng nên thiết lập client identifier và module/action phù hợp để liên kết hoạt động database với request nghiệp vụ.

### 1.3. Audit policy cần có mục đích rõ ràng

Không nên bật audit mọi SELECT trên mọi bảng chỉ vì có thể làm được. Audit quá rộng có thể:
- Tăng dung lượng audit trail nhanh.
- Tạo thêm I/O và chi phí xử lý.
- Làm truy vấn điều tra khó vì quá nhiều bản ghi.
- Ghi lại SQL hoặc thông tin nhạy cảm cần được bảo vệ.
- Tăng gánh nặng lưu trữ, archive và retention.

Bắt đầu từ rủi ro cần kiểm soát: privileged action, dữ liệu nhạy cảm, đăng nhập thất bại, DDL quan trọng hoặc thay đổi tài khoản. Sau đó chọn policy hẹp, đo volume và mở rộng khi có lý do.

## 2. Unified Auditing là gì?

### 2.1. Mô hình audit thống nhất

Unified Auditing cung cấp một framework để định nghĩa audit policy và lưu audit record trong unified audit trail. Một policy có thể bao gồm:
- SQL actions, ví dụ SELECT trên một object.
- System privileges, ví dụ CREATE ANY TABLE.
- Roles.
- Actions thuộc các thành phần database hỗ trợ unified auditing.
- Điều kiện ghi nhận thành công/thất bại ở thời điểm bật policy.

Các bản ghi được xem qua view UNIFIED_AUDIT_TRAIL. Oracle quản lý bảng audit nội bộ trong schema AUDSYS; ứng dụng và DBA nên dùng view/package được hỗ trợ, không thao tác trực tiếp lên bảng nội bộ.

### 2.2. Mixed mode và pure unified auditing

Trong Oracle 19c cần phân biệt hai chế độ triển khai:

- **Mixed mode:** unified auditing và traditional auditing cùng tồn tại. Các unified audit policy hoạt động, trong khi một số cấu hình traditional audit cũ vẫn có thể ghi vào audit destination truyền thống.
- **Pure unified auditing:** database chạy hoàn toàn theo unified auditing; các cơ chế traditional auditing cũ không còn là cơ chế audit độc lập theo cách mixed mode sử dụng.

Kiểm tra trạng thái tùy môi trường:

~~~sql
SELECT parameter,
       value
FROM   v$option
WHERE  parameter = 'Unified Auditing';
~~~

Giá trị TRUE cho biết pure unified auditing đã được bật trong Oracle home/database tương ứng. FALSE không có nghĩa không thể sử dụng unified audit policy; mixed mode vẫn hỗ trợ Unified Auditing.

Việc chuyển sang pure mode liên quan Oracle home/binary và quy trình khởi động database. Đây là thay đổi do DBA thực hiện theo hướng dẫn đúng nền tảng và phiên bản; không tự relink hoặc restart production chỉ để thử một policy.

### 2.3. Traditional auditing và Unified Auditing

Traditional auditing dùng các câu lệnh audit kiểu cũ và các audit destination/parameter tương ứng. Unified Auditing dùng CREATE AUDIT POLICY, AUDIT POLICY và NOAUDIT POLICY.

Trong mixed mode, hai cơ chế có thể cùng tồn tại, vì vậy khi điều tra hệ thống cũ không nên chỉ đọc một view rồi kết luận toàn bộ audit đã được thu thập. Có thể cần xem cả:
- UNIFIED_AUDIT_TRAIL cho các unified audit records.
- DBA_AUDIT_TRAIL hoặc các view traditional tương ứng nếu traditional auditing vẫn được sử dụng.
- DBA_FGA_AUDIT_TRAIL hoặc unified trail cho Fine-Grained Auditing, tùy cấu hình và mục đích tương thích.

Tham số AUDIT_TRAIL của traditional auditing không phải công tắc bật/tắt các unified audit policy. Hãy kiểm tra riêng chế độ audit và cấu hình thực tế.

### 2.4. Kiểm tra policy đang bật

View AUDIT_UNIFIED_ENABLED_POLICIES cho biết policy đã được bật, phạm vi user/entity và điều kiện success/failure. Ví dụ:

~~~sql
SELECT user_name,
       policy_name,
       enabled_option,
       entity_name,
       success,
       failure
FROM   audit_unified_enabled_policies
ORDER  BY policy_name, user_name;
~~~

Nếu cần kiểm tra các cột cụ thể theo release, dùng DESC AUDIT_UNIFIED_ENABLED_POLICIES hoặc tra Oracle Database Reference. View này mô tả cấu hình policy; nó không phải danh sách các audit event đã phát sinh.

## 3. Quyền quản trị và quyền xem audit

### 3.1. AUDIT_ADMIN

AUDIT_ADMIN là role quản trị các hoạt động audit được hỗ trợ, như tạo/quản lý audit policy và quản lý audit trail qua các API phù hợp.

Ví dụ DBA cấp role cho tài khoản quản trị bảo mật:

~~~sql
GRANT AUDIT_ADMIN TO audit_admin_user;
~~~

Chỉ cấp role này cho tài khoản có trách nhiệm quản lý audit. Không dùng chung tài khoản quản trị audit cho ứng dụng.

### 3.2. AUDIT_VIEWER

AUDIT_VIEWER dành cho người dùng cần xem dữ liệu audit mà không cần toàn quyền quản trị policy.

~~~sql
GRANT AUDIT_VIEWER TO security_reader;
~~~

Tách người tạo/bật policy khỏi người đọc audit giúp áp dụng least privilege. Người xem audit vẫn có thể tiếp cận SQL text, user identity, object name và thông tin nhạy cảm; quyền đọc audit cần được bảo vệ.

### 3.3. Kiểm tra quyền

Có thể xem role đã cấp cho user:

~~~sql
SELECT grantee,
       granted_role,
       default_role
FROM   dba_role_privs
WHERE  grantee IN ('AUDIT_ADMIN_USER', 'SECURITY_READER')
ORDER  BY grantee, granted_role;
~~~

Tên view và quyền đọc phụ thuộc schema/quyền DBA. Trong môi trường học tập, DBA có thể cấp role phù hợp; không cấp SELECT ANY TABLE hoặc quyền rộng khác chỉ để đọc audit trail.

### 3.4. Nguyên tắc tách nhiệm vụ

- Audit administrator tạo và duy trì policy.
- Security auditor tra cứu, phân tích và xuất báo cáo.
- Application account chỉ có quyền nghiệp vụ cần thiết.
- Tài khoản SYS/DBA được kiểm soát riêng và có quy trình break-glass.
- Audit trail được lưu ở vị trí có kiểm soát truy cập và retention độc lập.

## 4. Tạo audit policy cho object

### 4.1. Audit SELECT trên bảng nhạy cảm

Giả sử bảng HR.EMPLOYEES chứa dữ liệu nhân sự. Tạo policy:

~~~sql
CREATE AUDIT POLICY audit_employee_reads
    ACTIONS SELECT ON hr.employees;
~~~

Bật policy:

~~~sql
AUDIT POLICY audit_employee_reads;
~~~

Policy này ghi nhận hành động SELECT trên object được chỉ định. Nếu cần giới hạn user, có thể bật cho một database user:

~~~sql
AUDIT POLICY audit_employee_reads
    BY app_user;
~~~

Tên schema, bảng và user phải tồn tại trong môi trường thực tế. Người thực hiện cần quyền quản lý audit policy phù hợp.

### 4.2. Audit cả SELECT và UPDATE

~~~sql
CREATE AUDIT POLICY audit_employee_access
    ACTIONS SELECT ON hr.employees,
            UPDATE ON hr.employees;

AUDIT POLICY audit_employee_access BY app_user;
~~~

Một policy có thể gom nhiều action trên object. Tạo policy theo nhóm hành vi giúp quản trị rõ ràng hơn, nhưng đừng gộp các sự kiện có retention hoặc owner khác nhau nếu chính sách bảo mật cần phân biệt.

### 4.3. Chỉ audit thao tác thành công hoặc thất bại

Có thể giới hạn điều kiện khi bật policy:

~~~sql
AUDIT POLICY audit_employee_access
    BY app_user
    WHENEVER SUCCESSFUL;
~~~

Hoặc chỉ ghi nhận các lần thất bại:

~~~sql
AUDIT POLICY audit_employee_access
    BY app_user
    WHENEVER NOT SUCCESSFUL;
~~~

Nếu bật policy mà không giới hạn WHENEVER, hành vi mặc định là audit cả thành công và thất bại. Xác định mục tiêu điều tra trước khi chọn điều kiện.

### 4.4. Audit DDL

Có thể tạo policy theo dõi các hành động DDL quan trọng:

~~~sql
CREATE AUDIT POLICY audit_schema_ddl
    ACTIONS CREATE TABLE,
            ALTER TABLE,
            DROP TABLE,
            CREATE USER,
            ALTER USER,
            DROP USER;

AUDIT POLICY audit_schema_ddl;
~~~

DDL có thể ảnh hưởng cấu trúc, dữ liệu và quyền truy cập. Với production, nên audit các hành động có rủi ro cao và xác định user/role nào được phép thực hiện.

### 4.5. Audit việc sử dụng system privilege

Nếu muốn biết khi nào các quyền mạnh được sử dụng:

~~~sql
CREATE AUDIT POLICY audit_powerful_privileges
    PRIVILEGES CREATE ANY TABLE,
               DROP ANY TABLE,
               ALTER SYSTEM;

AUDIT POLICY audit_powerful_privileges;
~~~

Audit privilege usage giúp theo dõi việc dùng quyền, kể cả khi hành động không nhắm tới một object cụ thể trong policy. Hãy kiểm tra danh sách privilege được hỗ trợ và cách policy được áp dụng trong phiên bản đang chạy.

### 4.6. Xem định nghĩa policy

~~~sql
SELECT policy_name,
       audit_option,
       object_schema,
       object_name,
       object_type
FROM   audit_unified_policies
WHERE  policy_name IN (
           'AUDIT_EMPLOYEE_READS',
           'AUDIT_EMPLOYEE_ACCESS',
           'AUDIT_SCHEMA_DDL',
           'AUDIT_POWERFUL_PRIVILEGES'
       )
ORDER  BY policy_name, audit_option;
~~~

AUDIT_UNIFIED_POLICIES mô tả các audit option được khai báo trong policy. Một policy có thể có nhiều dòng vì mỗi action/object option được lưu thành một dòng metadata.

## 5. Bật, tắt và xóa audit policy

### 5.1. Bật policy cho toàn bộ user

~~~sql
AUDIT POLICY audit_employee_reads;
~~~

Khi không chỉ định user, policy được bật theo phạm vi mặc định của câu lệnh. Trước khi áp dụng rộng, xem policy đang audit action nào và dự kiến volume.

### 5.2. Bật policy cho một user

~~~sql
AUDIT POLICY audit_employee_reads BY app_user;
~~~

Có thể dùng phạm vi user khi chỉ một account hoặc một nhóm account cần được theo dõi. Với nhiều user, quản lý danh sách theo quy trình cấp quyền và review định kỳ.

### 5.3. Tắt policy

~~~sql
NOAUDIT POLICY audit_employee_reads;
~~~

Tắt policy dừng việc ghi các sự kiện do policy đó tạo ra sau thời điểm áp dụng. Các record đã được ghi vẫn còn trong audit trail theo retention policy.

Nếu policy chỉ được bật cho một user, câu lệnh NOAUDIT có thể giới hạn theo user tương ứng:

~~~sql
NOAUDIT POLICY audit_employee_reads BY app_user;
~~~

### 5.4. Xóa policy

Sau khi policy không còn được sử dụng, tắt policy trước rồi mới xóa định nghĩa:

~~~sql
NOAUDIT POLICY audit_employee_reads;
DROP AUDIT POLICY audit_employee_reads;
~~~

Không xóa policy chỉ để che giấu lịch sử. Việc thay đổi hoặc gỡ policy cần được ghi nhận trong quy trình quản trị bảo mật.

### 5.5. Kiểm tra trạng thái sau thay đổi

~~~sql
SELECT user_name,
       policy_name,
       enabled_option,
       entity_name,
       success,
       failure
FROM   audit_unified_enabled_policies
WHERE  policy_name = 'AUDIT_EMPLOYEE_READS';
~~~

Nếu không có dòng, policy có thể chưa được bật hoặc không áp dụng trong container/user đang xem. Kiểm tra đúng database, PDB và quyền truy vấn.

## 6. Các unified audit policy có sẵn

Oracle cung cấp một số predefined unified audit policy cho các nhóm hoạt động bảo mật phổ biến. Tên policy và trạng thái mặc định phụ thuộc release, cấu hình database và quá trình tạo database; hãy kiểm tra trước khi bật hoặc tắt.

Một số tên thường gặp trong Oracle 19c:

| Policy | Mục tiêu khái quát |
| --- | --- |
| ORA_SECURECONFIG | Theo dõi một số hành động cấu hình bảo mật quan trọng |
| ORA_LOGON_FAILURES | Theo dõi đăng nhập thất bại |
| ORA_ACCOUNT_MGMT | Theo dõi hoạt động quản lý account |
| ORA_DATABASE_PARAMETER | Theo dõi thay đổi tham số database |
| ORA_CIS_RECOMMENDATIONS | Các khuyến nghị audit liên quan CIS |

Kiểm tra định nghĩa:

~~~sql
SELECT policy_name,
       audit_option,
       object_schema,
       object_name,
       object_type
FROM   audit_unified_policies
WHERE  policy_name LIKE 'ORA_%'
ORDER  BY policy_name, audit_option;
~~~

Kiểm tra policy đã bật:

~~~sql
SELECT policy_name,
       enabled_option,
       entity_name,
       success,
       failure
FROM   audit_unified_enabled_policies
WHERE  policy_name LIKE 'ORA_%'
ORDER  BY policy_name;
~~~

Nếu policy có sẵn chưa được bật và phù hợp baseline bảo mật, có thể bật:

~~~sql
AUDIT POLICY ORA_LOGON_FAILURES;
~~~

Không mặc định tất cả policy ORA_* đều đang bật hoặc đều phù hợp với mọi môi trường. Review phạm vi, volume và chính sách nội bộ trước khi thay đổi.

## 7. Unified audit trail — nơi tra cứu dấu vết

### 7.1. View UNIFIED_AUDIT_TRAIL

UNIFIED_AUDIT_TRAIL là view chính để truy vấn unified audit records. Các trường thường dùng gồm:
- EVENT_TIMESTAMP: thời điểm sự kiện.
- DBUSERNAME: database user thực hiện hành động.
- OS_USERNAME: OS user do client/database ghi nhận.
- USERHOST: host nguồn.
- CLIENT_PROGRAM_NAME: chương trình client.
- CLIENT_IDENTIFIER: định danh client nếu ứng dụng thiết lập.
- ACTION_NAME: tên hành động.
- OBJECT_SCHEMA, OBJECT_NAME: object liên quan.
- RETURN_CODE: mã kết quả.
- UNIFIED_AUDIT_POLICIES: policy đã tạo record.
- SQL_TEXT, SQL_BINDS: câu SQL và thông tin bind khi có.
- SYSTEM_PRIVILEGE_USED: system privilege liên quan nếu có.

Không phải mọi cột đều có giá trị trong mọi record. Một event đăng nhập, DDL, SELECT trên object và sự kiện component có thể có các trường khác nhau.

### 7.2. Tra cứu sự kiện gần đây

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies,
       userhost,
       client_program_name
FROM   unified_audit_trail
WHERE  event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER  BY event_timestamp DESC
FETCH FIRST 100 ROWS ONLY;
~~~

Khoảng thời gian được giới hạn để tránh quét và hiển thị quá nhiều record. Trong hệ thống nhiều audit, nên dùng khoảng thời gian, user hoặc object cụ thể.

### 7.3. Tra cứu theo database user

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies,
       userhost,
       client_program_name
FROM   unified_audit_trail
WHERE  dbusername = 'APP_USER'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY event_timestamp DESC;
~~~

Tên user trong dictionary thường được lưu ở dạng uppercase nếu được tạo không dùng quoted identifier. Hãy kiểm tra đúng cách viết username trong môi trường thực tế.

### 7.4. Tra cứu theo object

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies,
       userhost
FROM   unified_audit_trail
WHERE  object_schema = 'HR'
AND    object_name = 'EMPLOYEES'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '30' DAY
ORDER  BY event_timestamp DESC;
~~~

Cách này hữu ích khi điều tra một bảng nhạy cảm. Một số action không gắn object nên object_schema/object_name có thể NULL.

### 7.5. Phân biệt thành công và thất bại

RETURN_CODE bằng 0 thường biểu thị thao tác thành công; giá trị khác 0 thường là Oracle error code của thao tác thất bại.

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       userhost,
       client_program_name
FROM   unified_audit_trail
WHERE  return_code <> 0
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '24' HOUR
ORDER  BY event_timestamp DESC;
~~~

Không suy ra mọi lỗi database đều được audit. Chỉ các action được policy hoặc audit source tương ứng ghi nhận mới xuất hiện.

### 7.6. Tra cứu đăng nhập thất bại

~~~sql
SELECT event_timestamp,
       dbusername,
       os_username,
       userhost,
       client_program_name,
       action_name,
       return_code,
       unified_audit_policies
FROM   unified_audit_trail
WHERE  action_name = 'LOGON'
AND    return_code <> 0
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY event_timestamp DESC;
~~~

Policy ORA_LOGON_FAILURES thường được dùng để theo dõi logon failure. Xác minh policy đã bật trong đúng container và khoảng thời gian cần điều tra.

### 7.7. Tra cứu thay đổi tài khoản và privilege

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       system_privilege_used,
       return_code,
       unified_audit_policies,
       userhost
FROM   unified_audit_trail
WHERE  action_name IN (
           'CREATE USER',
           'ALTER USER',
           'DROP USER',
           'GRANT',
           'REVOKE'
       )
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '30' DAY
ORDER  BY event_timestamp DESC;
~~~

Tên action có thể được biểu diễn theo ACTION_NAME của record cụ thể. Khi điều tra, trước tiên truy vấn các action gần thời điểm sự kiện rồi dùng giá trị thực tế để tinh chỉnh bộ lọc.

### 7.8. Đọc SQL_TEXT và SQL_BINDS

SQL_TEXT và SQL_BINDS có thể chứa nội dung dài. Dùng DBMS_LOB.SUBSTR để lấy một đoạn khi client không hiển thị CLOB thuận tiện:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       DBMS_LOB.SUBSTR(sql_text, 1000, 1) AS sql_text_sample,
       DBMS_LOB.SUBSTR(sql_binds, 1000, 1) AS sql_binds_sample
FROM   unified_audit_trail
WHERE  sql_text IS NOT NULL
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER  BY event_timestamp DESC;
~~~

SQL_TEXT/SQL_BINDS có thể NULL tùy loại record, policy và cách sự kiện được tạo. Bind capture không phải lúc nào cũng chứa mọi bind value. Các giá trị này có thể nhạy cảm; chỉ truy cập khi có thẩm quyền và che dữ liệu trước khi chia sẻ báo cáo.

### 7.9. Nhóm audit theo user và action

~~~sql
SELECT dbusername,
       action_name,
       COUNT(*) AS event_count,
       MIN(event_timestamp) AS first_event,
       MAX(event_timestamp) AS last_event
FROM   unified_audit_trail
WHERE  event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
GROUP  BY dbusername, action_name
ORDER  BY event_count DESC;
~~~

Tổng hợp giúp nhận diện account hoặc action tạo nhiều audit record. Số lượng lớn có thể là workload bình thường; cần đối chiếu application traffic và policy scope.

## 8. Tra cứu policy và audit configuration

### 8.1. Danh sách policy

~~~sql
SELECT DISTINCT policy_name
FROM   audit_unified_policies
ORDER  BY policy_name;
~~~

### 8.2. Các action/object trong một policy

~~~sql
SELECT policy_name,
       audit_option,
       object_schema,
       object_name,
       object_type
FROM   audit_unified_policies
WHERE  policy_name = 'AUDIT_EMPLOYEE_ACCESS'
ORDER  BY audit_option, object_schema, object_name;
~~~

### 8.3. Policy đã bật và đối tượng áp dụng

~~~sql
SELECT user_name,
       policy_name,
       enabled_option,
       entity_name,
       success,
       failure
FROM   audit_unified_enabled_policies
ORDER  BY policy_name, entity_name;
~~~

Đọc cả định nghĩa và trạng thái enabled. Policy tồn tại trong AUDIT_UNIFIED_POLICIES chưa chắc đã được bật.

### 8.4. Kiểm tra audit trail có record

~~~sql
SELECT audit_type,
       COUNT(*) AS record_count,
       MIN(event_timestamp) AS oldest_event,
       MAX(event_timestamp) AS newest_event
FROM   unified_audit_trail
GROUP  BY audit_type
ORDER  BY record_count DESC;
~~~

AUDIT_TYPE giúp phân biệt nguồn audit. Các loại record xuất hiện tùy component và cấu hình. Dùng kết quả này để hiểu dữ liệu hiện có, không giả định tất cả audit source đều đang được bật.

## 9. Fine-Grained Auditing và Unified Auditing

### 9.1. Khi nào cần Fine-Grained Auditing?

Unified audit policy phù hợp với nhiều action, privilege và object. Fine-Grained Auditing (FGA) dùng khi cần điều kiện chi tiết hơn, chẳng hạn chỉ audit truy cập một cột nhạy cảm hoặc chỉ khi một điều kiện dữ liệu được thỏa mãn.

FGA được quản lý qua DBMS_FGA. Trong các phiên bản hỗ trợ Unified Auditing, FGA audit records có thể được tra cứu trong unified audit trail; các view tương thích truyền thống vẫn có thể tồn tại tùy mode.

### 9.2. Tạo FGA policy theo cột và điều kiện

Ví dụ chỉ theo dõi SELECT vào cột SALARY khi giá trị thỏa điều kiện:

~~~sql
BEGIN
    DBMS_FGA.ADD_POLICY(
        object_schema   => 'HR',
        object_name     => 'EMPLOYEES',
        policy_name     => 'FGA_HIGH_SALARY_READ',
        audit_condition => 'SALARY >= 10000',
        audit_column    => 'SALARY',
        statement_types => 'SELECT'
    );
END;
/
~~~

Điều kiện audit phải là biểu thức SQL hợp lệ theo giới hạn DBMS_FGA; không xem đây là nơi chạy subquery tùy ý. Tài khoản thực hiện cần quyền phù hợp trên object và package.

### 9.3. Kiểm tra FGA policy

~~~sql
SELECT object_schema,
       object_name,
       policy_name,
       enabled,
       sel,
       ins,
       upd,
       del,
       audit_column
FROM   dba_audit_policies
WHERE  policy_name = 'FGA_HIGH_SALARY_READ';
~~~

Các cột hiển thị tùy view và release. Có thể dùng ALL_AUDIT_POLICIES hoặc USER_AUDIT_POLICIES theo phạm vi quyền.

### 9.4. Tắt hoặc xóa FGA policy

~~~sql
BEGIN
    DBMS_FGA.DISABLE_POLICY(
        object_schema => 'HR',
        object_name   => 'EMPLOYEES',
        policy_name   => 'FGA_HIGH_SALARY_READ'
    );
END;
/
~~~

Xóa policy khi không còn cần:

~~~sql
BEGIN
    DBMS_FGA.DROP_POLICY(
        object_schema => 'HR',
        object_name   => 'EMPLOYEES',
        policy_name   => 'FGA_HIGH_SALARY_READ'
    );
END;
/
~~~

Unified audit policy và FGA policy là hai cơ chế cấu hình khác nhau. Chọn cơ chế theo yêu cầu kiểm toán và tránh bật hai policy trùng phạm vi nếu không cần thiết.

## 10. Client identity và khả năng truy vết

### 10.1. Database user không luôn là người dùng nghiệp vụ

Trong connection pool, hàng trăm người dùng ứng dụng có thể dùng chung một database account như APP_USER. Nếu chỉ audit DBUSERNAME, mọi hoạt động có thể trông như cùng một account.

Ứng dụng nên thiết lập client identifier sau khi xác thực người dùng:

~~~sql
BEGIN
    DBMS_SESSION.SET_IDENTIFIER('user-7421');
END;
/
~~~

Client identifier được gắn vào session và có thể xuất hiện trong audit context khi record hỗ trợ trường này. Dùng giá trị không chứa secret và tuân theo quy tắc bảo vệ dữ liệu cá nhân.

### 10.2. Ghi module và action

Ứng dụng có thể đặt module/action:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'OrderService',
        action_name => 'ReadCustomerProfile'
    );
END;
/
~~~

Module/action giúp phân tích session và SQL qua các công cụ giám sát phù hợp. Audit trail có thể ghi một số client context tùy trường; nếu cần liên kết chắc chắn, dùng CLIENT_IDENTIFIER và correlation ID do ứng dụng quản lý.

### 10.3. Xóa context khi trả connection về pool

Connection pool tái sử dụng session. Sau khi xử lý request, ứng dụng phải reset client identifier/module/action hoặc thiết lập giá trị mới trước request tiếp theo. Nếu không, audit record có thể gắn nhầm identity từ request trước.

### 10.4. Không dùng client identifier như bằng chứng xác thực độc lập

CLIENT_IDENTIFIER do client/ứng dụng thiết lập. Nó hữu ích để liên kết request nhưng không tự chứng minh người dùng đã xác thực đúng. Kết hợp với application authentication log, proxy identity hoặc identity provider khi điều tra.

## 11. Unified audit trong CDB và PDB

### 11.1. Container context

Trong multitenant database, policy và audit record có thể gắn với CDB root hoặc PDB. Khi điều tra:
- Xác định container đang kết nối.
- Xem policy là common hay local.
- Xem user là common user hay local user.
- Phân biệt record của root và PDB.
- Sử dụng view CDB phù hợp nếu cần tổng hợp nhiều container và có quyền.

### 11.2. Xem container hiện tại

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS con_name,
       sys_context('USERENV', 'CON_ID') AS con_id
FROM   dual;
~~~

Khi chạy CREATE AUDIT POLICY hoặc AUDIT POLICY, hãy thực hiện trong đúng container theo thiết kế quản trị. Không giả định policy tạo ở PDB tự động áp dụng toàn CDB hoặc ngược lại.

### 11.3. Audit trail nhiều container

Trong CDB, DBA có thể dùng các CDB-level audit views tương ứng để xem dữ liệu nhiều container, với quyền và container visibility phù hợp. Khi xuất báo cáo, luôn giữ thông tin CON_ID/container để không gộp hai PDB có cùng tên schema/object thành một nguồn sự kiện.

### 11.4. Policy common và local

Policy common phục vụ cấu hình được quản lý từ root theo phạm vi được hỗ trợ; policy local chỉ áp dụng trong container tương ứng. Thiết kế common policy cần review tác động trên mọi PDB, volume audit và quyền quản trị.

Cú pháp CONTAINER và các quy tắc common/local phụ thuộc loại policy và release. Hãy tham khảo SQL Language Reference 19c trước khi triển khai ở CDB production.

## 12. Lưu trữ, flush và quản lý dung lượng audit trail

### 12.1. Audit trail là dữ liệu bảo mật quan trọng

Unified audit trail được Oracle lưu trong vùng quản lý nội bộ của AUDSYS. Không sửa hoặc xóa trực tiếp các bảng nội bộ. Dùng UNIFIED_AUDIT_TRAIL để đọc và DBMS_AUDIT_MGMT để quản lý cleanup theo hướng dẫn Oracle.

Audit record có thể chứa SQL text, object name, user identity và context. Bảo vệ audit trail khỏi:
- User không có thẩm quyền.
- Xóa hoặc sửa ngoài quy trình.
- Storage đầy.
- Retention ngắn hơn yêu cầu.
- Mất đồng bộ thời gian giữa database và hệ thống liên quan.

### 12.2. Flush unified audit trail

Trong một số cấu hình, audit records có thể được queue trước khi được ghi xuống audit table. Có thể yêu cầu flush bằng package quản trị:

~~~sql
BEGIN
    DBMS_AUDIT_MGMT.FLUSH_UNIFIED_AUDIT_TRAIL;
END;
/
~~~

Thao tác này hữu ích khi cần đồng bộ record đang chờ trước khi đối chiếu. Nó không thay thế việc kiểm tra policy đã bật hoặc xác nhận sự kiện có thuộc phạm vi audit.

### 12.3. Kiểm tra dung lượng tablespace

Có thể kiểm tra segment và tablespace liên quan theo quyền DBA:

~~~sql
SELECT owner,
       segment_name,
       segment_type,
       tablespace_name,
       bytes / 1024 / 1024 AS size_mb
FROM   dba_segments
WHERE  owner = 'AUDSYS'
ORDER  BY bytes DESC;
~~~

AUDSYS là schema nội bộ. Chỉ quan sát metadata; không DROP, MOVE hoặc sửa segment audit nội bộ bằng thao tác không được Oracle hỗ trợ.

### 12.4. Archive trước khi purge

Một chính sách retention nên xác định:
- Thời gian lưu online để tra cứu nhanh.
- Nơi archive lâu dài.
- Quyền truy cập archive.
- Mã hóa và tính toàn vẹn.
- Quy trình legal hold hoặc investigation hold.
- Ai được phê duyệt cleanup.
- Cách kiểm chứng bản archive có thể đọc lại.

Chỉ đánh dấu last archive timestamp sau khi record đến thời điểm đó đã thực sự được archive an toàn theo quy trình.

### 12.5. Khởi tạo cleanup management

Ví dụ DBA khởi tạo cleanup management cho unified audit trail:

~~~sql
BEGIN
    DBMS_AUDIT_MGMT.INIT_CLEANUP(
        audit_trail_type        => DBMS_AUDIT_MGMT.AUDIT_TRAIL_UNIFIED,
        default_cleanup_interval => 24
    );
END;
/
~~~

Tên constant và yêu cầu quyền cần xác nhận theo package reference của release. Thao tác này khởi tạo cơ chế cleanup; nó không tự xóa record ngay lập tức.

### 12.6. Đánh dấu thời điểm đã archive

Sau khi đã export/archive record cũ và xác nhận archive thành công, DBA có thể cập nhật last archive timestamp:

~~~sql
BEGIN
    DBMS_AUDIT_MGMT.SET_LAST_ARCHIVE_TIMESTAMP(
        audit_trail_type => DBMS_AUDIT_MGMT.AUDIT_TRAIL_UNIFIED,
        last_archive_time => SYSTIMESTAMP - INTERVAL '90' DAY
    );
END;
/
~~~

Mốc 90 ngày chỉ là ví dụ minh họa. Trong production, timestamp phải phản ánh đúng dữ liệu đã archive, không phải retention mong muốn trên giấy.

### 12.7. Cleanup record đã archive

~~~sql
BEGIN
    DBMS_AUDIT_MGMT.CLEAN_AUDIT_TRAIL(
        audit_trail_type         => DBMS_AUDIT_MGMT.AUDIT_TRAIL_UNIFIED,
        use_last_arch_timestamp  => TRUE
    );
END;
/
~~~

Câu lệnh trên minh họa cleanup theo last archive timestamp. Chỉ chạy sau khi kiểm tra retention, archive, quyền, legal hold và phê duyệt. Không dùng cleanup để xóa dấu vết của một sự kiện đang được điều tra.

### 12.8. Theo dõi volume audit

~~~sql
SELECT TRUNC(event_timestamp) AS audit_day,
       audit_type,
       COUNT(*) AS record_count
FROM   unified_audit_trail
WHERE  event_timestamp >= SYSTIMESTAMP - INTERVAL '30' DAY
GROUP  BY TRUNC(event_timestamp), audit_type
ORDER  BY audit_day DESC, audit_type;
~~~

Volume theo ngày giúp phát hiện policy ghi quá rộng hoặc đột ngột tăng record. Kết hợp với số request, batch job và thay đổi cấu hình để tìm nguyên nhân.

## 13. Bảo vệ audit trail và vận hành an toàn

### 13.1. Least privilege

Chỉ AUDIT_ADMIN hoặc tài khoản quản trị được ủy quyền mới được tạo/tắt policy và quản lý cleanup. Chỉ nhóm kiểm toán cần thiết có AUDIT_VIEWER. Application user không nên đọc audit trail.

### 13.2. Audit trail phải được bảo vệ độc lập

- Hạn chế quyền SYSDBA và quyền quản trị AUDSYS.
- Giám sát thay đổi policy.
- Archive ra nơi có kiểm soát truy cập.
- Bảo vệ archive khỏi sửa/xóa trái phép.
- Dùng mã hóa và checksum theo chính sách.
- Đồng bộ thời gian database, OS, application và identity provider.
- Ghi lại ai đã export, purge hoặc thay đổi retention.

### 13.3. Không audit dữ liệu nhạy cảm quá mức

SQL_TEXT/SQL_BINDS và application context có thể chứa dữ liệu nhạy cảm. Xác định có cần ghi SQL binds không, ai được xem và thời gian giữ. Không đưa password, token hoặc secret vào client identifier, module/action hay SQL comments.

### 13.4. Audit chính thao tác quản trị

Các hành động tạo, bật, tắt và thay đổi audit policy là hoạt động bảo mật quan trọng. Dùng policy bảo vệ thay đổi cấu hình và review định kỳ danh sách policy đang bật để phát hiện việc giảm phạm vi audit trái phép.

### 13.5. Đồng bộ thời gian

Timestamp chỉ hữu ích khi so sánh được với application log và OS log. Dùng NTP/time synchronization cho database host, app host và hệ thống liên quan. Khi phân tích, chú ý EVENT_TIMESTAMP, timezone và cách công cụ hiển thị timestamp.

## 14. Quy trình điều tra một sự kiện bảo mật

### Bước 1 — Xác định câu hỏi

Ví dụ:
- Ai đọc bảng HR.EMPLOYEES hôm qua?
- User nào đăng nhập thất bại nhiều lần?
- Ai đã cấp quyền CREATE ANY TABLE?
- Khi nào một policy bị tắt?
- Client nào thực hiện UPDATE dữ liệu nhạy cảm?

Câu hỏi rõ giúp chọn bộ lọc audit trail phù hợp.

### Bước 2 — Xác nhận policy bao phủ sự kiện

Kiểm tra AUDIT_UNIFIED_POLICIES và AUDIT_UNIFIED_ENABLED_POLICIES. Xác định policy đã tồn tại và bật trong đúng user/container, có audit success/failure đúng yêu cầu hay không.

Nếu policy chưa bật tại thời điểm sự kiện, audit trail có thể không có record. Không thể khôi phục audit record đã không được ghi chỉ bằng cách bật policy sau đó.

### Bước 3 — Chọn cửa sổ thời gian

Dùng timestamp có timezone phù hợp và mở rộng khoảng tìm kiếm nếu có chênh lệch đồng hồ. Bắt đầu bằng một khoảng ngắn rồi mở rộng theo bằng chứng.

### Bước 4 — Lọc theo user, action và object

Dùng DBUSERNAME, ACTION_NAME, OBJECT_SCHEMA, OBJECT_NAME, RETURN_CODE và UNIFIED_AUDIT_POLICIES. Giữ lại USERHOST, CLIENT_PROGRAM_NAME và CLIENT_IDENTIFIER để liên kết nguồn.

### Bước 5 — Xem SQL và context

Nếu có SQL_TEXT/SQL_BINDS, chỉ xem phần cần thiết và bảo vệ thông tin nhạy cảm. Đối chiếu application request ID, client identifier, session và log ứng dụng.

### Bước 6 — Phân biệt hành động thành công/thất bại

RETURN_CODE và loại action cho biết kết quả database. Một lần đăng nhập thất bại có thể phản ánh password sai, user không tồn tại hoặc một lỗi kết nối; cần đối chiếu error code và identity log.

### Bước 7 — Bảo toàn bằng chứng

Export record theo quy trình đã được phê duyệt, giữ timestamp/timezone, SQL_ID hoặc transaction context khi có, nguồn truy vấn, người thực hiện export và checksum/archive metadata. Hạn chế thay đổi retention hoặc policy trong lúc investigation đang mở.

### Bước 8 — Báo cáo kết luận có giới hạn

Báo cáo nên phân biệt:
- Điều audit trail chứng minh trực tiếp.
- Điều được suy luận từ client/application context.
- Dữ liệu không được audit hoặc không có trong record.
- Khoảng thời gian, container và policy coverage.
- Những nguồn log khác cần đối chiếu.

Không kết luận “không có hành động” chỉ vì không tìm thấy record nếu policy không bao phủ action hoặc audit trail đã bị purge.

## 15. Truy vấn mẫu cho các tình huống thường gặp

### 15.1. Ai đọc bảng nhạy cảm?

~~~sql
SELECT event_timestamp,
       dbusername,
       userhost,
       client_program_name,
       client_identifier,
       action_name,
       return_code,
       unified_audit_policies
FROM   unified_audit_trail
WHERE  object_schema = 'HR'
AND    object_name = 'EMPLOYEES'
AND    action_name = 'SELECT'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER  BY event_timestamp DESC;
~~~

### 15.2. Ai thay đổi bảng?

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       userhost,
       client_program_name
FROM   unified_audit_trail
WHERE  object_schema = 'HR'
AND    object_name = 'EMPLOYEES'
AND    action_name IN ('INSERT', 'UPDATE', 'DELETE')
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY event_timestamp DESC;
~~~

Tên ACTION_NAME có thể cần điều chỉnh theo giá trị record được ghi trong môi trường. Truy vấn rộng trước để xác nhận cách Oracle biểu diễn action.

### 15.3. Tìm thay đổi quyền

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       system_privilege_used,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies
FROM   unified_audit_trail
WHERE  action_name IN ('GRANT', 'REVOKE')
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '30' DAY
ORDER  BY event_timestamp DESC;
~~~

Để phân tích chi tiết, đối chiếu SQL_TEXT và các record liên quan cùng transaction/time window.

### 15.4. Tìm hoạt động từ một host

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       client_program_name
FROM   unified_audit_trail
WHERE  userhost = 'APPHOST01'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '24' HOUR
ORDER  BY event_timestamp DESC;
~~~

USERHOST là thông tin do kết nối/client cung cấp theo cơ chế Oracle; xác minh với network/host log nếu cần bằng chứng nguồn mạnh hơn.

### 15.5. Tìm event do policy cụ thể tạo

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       unified_audit_policies
FROM   unified_audit_trail
WHERE  unified_audit_policies LIKE '%AUDIT_EMPLOYEE_ACCESS%'
AND    event_timestamp >= SYSTIMESTAMP - INTERVAL '7' DAY
ORDER  BY event_timestamp DESC;
~~~

UNIFIED_AUDIT_POLICIES có thể chứa nhiều policy name. Với hệ thống có nhiều policy, lọc theo khoảng thời gian và xác nhận giá trị thực tế của cột trước khi dùng LIKE.

## 16. Lỗi và hiểu nhầm thường gặp

**“Có Unified Auditing nghĩa là mọi hành động đã được ghi.”** Không. Chỉ các action nằm trong audit policy hoặc audit source được cấu hình mới được ghi.

**“UNIFIED_AUDIT_TRAIL luôn chứa toàn bộ traditional audit records.”** Không nên giả định như vậy trong mixed mode. Kiểm tra các traditional audit view/destination nếu hệ thống vẫn dùng cơ chế cũ.

**“Policy tồn tại nghĩa là đã bật.”** Không. Xem AUDIT_UNIFIED_ENABLED_POLICIES để xác nhận trạng thái.

**“AUDIT_TRAIL=DB bật Unified Auditing.”** Không. Tham số đó thuộc traditional auditing; unified policy được quản lý bằng AUDIT POLICY.

**“Không có record chứng minh không có hành động.”** Không. Có thể policy chưa bật, action không nằm trong scope, record chưa được flush hoặc đã bị purge.

**“RETURN_CODE khác 0 luôn là đăng nhập thất bại.”** Không. Nó có thể là lỗi của bất kỳ action nào được audit.

**“DBUSERNAME luôn là người dùng cuối.”** Không. Connection pool có thể dùng chung database account. Dùng CLIENT_IDENTIFIER và application log để liên kết user nghiệp vụ.

**“FGA thay thế toàn bộ Unified Auditing.”** Không. FGA bổ sung điều kiện audit chi tiết cho object/cột; unified policy vẫn phù hợp cho action, privilege và nhiều sự kiện khác.

**“Tăng retention là đủ.”** Không. Cần archive, dung lượng, quyền truy cập, legal hold và cleanup procedure.

**“Có thể xóa record bằng DELETE từ AUDSYS.”** Không. Dùng DBMS_AUDIT_MGMT và quy trình được hỗ trợ.

**“Audit tất cả SELECT luôn tốt hơn.”** Không. Audit rộng có thể tạo volume lớn, ảnh hưởng vận hành và tăng dữ liệu nhạy cảm cần bảo vệ.

**“AUDIT_ADMIN nên được cấp cho ứng dụng.”** Không. Đây là role quản trị audit; ứng dụng không cần quyền đó.

## 17. Bài thực hành

Các bài tập cần chạy trong database test hoặc PDB được cấp quyền. Không tạo policy rộng trên production chỉ để thử.

### Bài 1 — Kiểm tra Unified Auditing mode

Truy vấn V$OPTION và xác định database đang ở pure hay mixed mode. Giải thích vì sao FALSE không có nghĩa unified policy không sử dụng được.

### Bài 2 — Xem predefined policies

Truy vấn AUDIT_UNIFIED_POLICIES và AUDIT_UNIFIED_ENABLED_POLICIES. Ghi lại policy ORA_* nào tồn tại và policy nào đang bật.

### Bài 3 — Audit SELECT trên object

Tạo bảng test có dữ liệu không nhạy cảm. Tạo policy SELECT, bật cho user test, thực hiện truy vấn và tìm record trong UNIFIED_AUDIT_TRAIL.

### Bài 4 — Audit thành công/thất bại

Bật policy cho WHENEVER SUCCESSFUL, sau đó thực hiện hành động hợp lệ và không hợp lệ trong môi trường test. So sánh RETURN_CODE và record.

### Bài 5 — Audit DDL

Tạo policy theo dõi CREATE TABLE, ALTER TABLE và DROP TABLE. Thực hiện từng action bằng user test và tra cứu ACTION_NAME.

### Bài 6 — Audit system privilege

Tạo policy cho một system privilege được cấp trong schema test. Sử dụng privilege đó và xem record liên quan.

### Bài 7 — Bật/tắt policy theo user

Bật policy cho một user cụ thể, thực hiện action bằng hai user khác nhau và so sánh record. Tắt policy sau khi hoàn thành.

### Bài 8 — Truy vấn theo object và time window

Viết truy vấn lấy lịch sử SELECT/UPDATE trên một bảng test trong 24 giờ. Thêm userhost, client program và return code.

### Bài 9 — Đọc SQL_TEXT

Tạo một câu SQL có audit, đọc SQL_TEXT bằng DBMS_LOB.SUBSTR. Kiểm tra quyền truy cập và xử lý thông tin nhạy cảm.

### Bài 10 — FGA theo cột

Tạo FGA policy trên cột test, thực hiện SELECT có và không truy cập cột được audit. So sánh record và tắt policy.

### Bài 11 — Client identifier

Dùng DBMS_SESSION.SET_IDENTIFIER để gắn request identity. Tạo audit record và kiểm tra CLIENT_IDENTIFIER khi field được ghi.

### Bài 12 — Multitenant

Tạo hoặc xem policy trong PDB test. Xác định container của session và record; so sánh local/common scope theo quyền được cấp.

### Bài 13 — Volume audit

Tổng hợp record theo ngày, policy và action. Xác định policy nào tạo volume lớn nhất và đề xuất scope phù hợp hơn.

### Bài 14 — Archive và cleanup

Trong môi trường test, thực hiện quy trình export/archive được phê duyệt, thiết lập last archive timestamp và chạy cleanup bằng DBMS_AUDIT_MGMT. Xác nhận record mới hơn mốc vẫn còn và archive cũ có thể đọc lại.

## 18. Tài liệu Oracle tham khảo

- [Oracle Database 19c Security Guide — Auditing Database Activity](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/introduction-to-auditing.html): khái niệm audit, unified auditing và cách xây dựng chính sách.
- [Oracle Database 19c Security Guide — Configuring and Administering Unified Auditing](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-audit-policies.html): tạo, bật, tắt và quản lý unified audit policy.
- [Oracle Database 19c SQL Language Reference — CREATE AUDIT POLICY](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-AUDIT-POLICY.html): cú pháp định nghĩa policy.
- [Oracle Database 19c SQL Language Reference — AUDIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/AUDIT.html): bật audit policy.
- [Oracle Database 19c SQL Language Reference — NOAUDIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NOAUDIT.html): tắt audit policy.
- [Oracle Database Reference — UNIFIED_AUDIT_TRAIL](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/UNIFIED_AUDIT_TRAIL.html): các cột và record trong unified audit trail.
- [Oracle Database Reference — AUDIT_UNIFIED_ENABLED_POLICIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/AUDIT_UNIFIED_ENABLED_POLICIES.html): trạng thái policy đang bật.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_AUDIT_MGMT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_AUDIT_MGMT.html): flush, archive timestamp và cleanup audit trail.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_FGA](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_FGA.html): Fine-Grained Auditing.
- [Oracle Database Reference — AUDIT_UNIFIED_POLICIES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/AUDIT_UNIFIED_POLICIES.html): metadata của unified audit policy.

Unified Auditing cung cấp một cách quản lý audit tập trung thông qua policy và unified audit trail. Hãy định nghĩa rõ action, object, user và success/failure cần theo dõi; bật policy đúng phạm vi; truy vấn record theo thời gian, user, action và object; rồi liên kết database identity với client/application context. Audit trail cần được phân quyền, archive, giữ đúng retention và cleanup theo quy trình có phê duyệt. **Một hệ thống audit tốt phải ghi đúng sự kiện cần điều tra, bảo vệ được bằng chứng và cho phép truy vết mà không tạo volume ngoài khả năng vận hành.**
