# ORA-01017, ORA-28000 và lỗi xác thực hoặc tài khoản bị khóa

Khi ứng dụng hoặc DBA kết nối Oracle Database, hai lỗi thường gặp là **ORA-01017: invalid username/password; logon denied** và **ORA-28000: the account is locked**. Cả hai đều xuất hiện ở bước đăng nhập, nhưng nguyên nhân và cách xử lý khác nhau:

- ORA-01017 cho biết Oracle không chấp nhận thông tin xác thực được gửi đến. Có thể sai username, password, cách truyền credential, hoặc đang kết nối đến database/PDB khác với dự kiến.
- ORA-28000 cho biết account đích đang ở trạng thái locked. Cần xác định vì sao account bị khóa và mở khóa đúng container, đồng thời xử lý nguồn đăng nhập sai để account không bị khóa lại.

Không nên thử password liên tục hoặc chỉ mở khóa rồi để ứng dụng tiếp tục dùng credential cũ. Một service, connection pool, job hoặc health check có thể đang gửi password sai lặp đi lặp lại và khóa account ngay sau khi DBA unlock.

## 1. Phân biệt lỗi xác thực và lỗi kết nối

Đầu tiên, phân biệt lỗi ở tầng network/listener với lỗi xác thực database.

| Mã lỗi | Ý nghĩa thường gặp | Tầng cần kiểm tra |
|---|---|---|
| ORA-01017 | Username/password không được chấp nhận | Credential, account, service/PDB |
| ORA-28000 | Account đang bị khóa | Account status, profile, failed login source |
| ORA-28001 | Password đã hết hạn | Password lifecycle và quy trình đổi password |
| ORA-28002 | Password sắp hết hạn, đang trong grace period | Profile và kế hoạch đổi password |
| ORA-28003 | Password không đạt password verification function | Password policy |
| ORA-28007 | Password không thể được sử dụng lại theo policy | Password reuse policy |
| ORA-01045 | User chưa có quyền CREATE SESSION | Privilege đăng nhập |
| ORA-28009 | SYS phải kết nối với AS SYSDBA hoặc AS SYSOPER | Kiểu kết nối SYS |
| ORA-28040 | Không có authentication protocol phù hợp | JDBC/Oracle client version và server policy |
| ORA-12154 | Không phân giải được connect identifier | Oracle Net naming/TNS |
| ORA-12514 | Listener không biết service được yêu cầu | Service registration và connect string |
| ORA-12541 | Không có listener tại endpoint | Host, port, listener và network |

ORA-12154, ORA-12514 và ORA-12541 không phải lỗi password. Khi gặp chúng, chưa nên reset password hoặc unlock account; hãy xử lý kết nối và service trước.

## 2. ORA-01017 là gì?

ORA-01017 xuất hiện khi Oracle từ chối thông tin xác thực được gửi trong quá trình đăng nhập. Thông báo phổ biến:

~~~text
ORA-01017: invalid username/password; logon denied
~~~

Các nguyên nhân có thể gồm:

- Nhập sai username hoặc password.
- Ứng dụng đang dùng secret cũ sau khi password được thay đổi.
- Password có ký tự đặc biệt bị shell, YAML, URL hoặc script diễn giải sai.
- Username được tạo bằng quoted identifier nên có phân biệt hoa/thường.
- Kết nối nhầm service, database hoặc PDB.
- Account không tồn tại trong container đích.
- Password được thay đổi ở PDB khác hoặc trên database khác.
- Oracle client/JDBC driver không tương thích với authentication protocol của server.
- Một số cơ chế xác thực ngoài database không được cấu hình đúng.

ORA-01017 không chứng minh password người vận hành vừa nhập là sai ở mọi nơi. Nó chỉ cho biết thông tin được gửi đến endpoint cụ thể không được chấp nhận ở đó.

## 3. Kiểm tra đúng database, service và PDB

Một nguyên nhân dễ bỏ sót là ứng dụng kết nối nhầm database hoặc PDB. Cùng một username có thể tồn tại ở nhiều PDB nhưng có password, trạng thái và quyền khác nhau.

Trước khi điều tra account, xác định endpoint:

- Hostname hoặc SCAN name.
- Listener port.
- Service name.
- PDB mà service dẫn đến.
- Môi trường: development, test, staging, production hay DR.

JDBC URL dạng service name:

~~~text
jdbc:oracle:thin:@//dbhost.example.com:1521/APP_SERVICE
~~~

Không nhầm SID với service name. Với multitenant, ứng dụng thường nên kết nối qua service được cấu hình cho PDB cần dùng, thay vì kết nối vào CDB root rồi giả định local user của PDB sẽ đăng nhập được.

Nếu đã kết nối được bằng một tài khoản quản trị phù hợp, kiểm tra container:

~~~sql
SHOW CON_NAME;

SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name
  FROM dual;
~~~

Nếu client không hỗ trợ lệnh SHOW, truy vấn SYS_CONTEXT vẫn có thể dùng trong SQL worksheet.

Trong CDB root, xem các user theo container:

~~~sql
SELECT con_id,
       username,
       common,
       account_status,
       profile,
       lock_date,
       expiry_date
  FROM cdb_users
 WHERE username = UPPER('APP_RUNTIME')
 ORDER BY con_id;
~~~

Truy vấn CDB_USERS cần quyền đọc dictionary phù hợp. Nếu đang kết nối trực tiếp vào PDB, DBA_USERS thường là view phù hợp:

~~~sql
SELECT username,
       account_status,
       profile,
       lock_date,
       expiry_date
  FROM dba_users
 WHERE username = UPPER('APP_RUNTIME');
~~~

Nếu account chỉ tồn tại trong PDB SALES nhưng ứng dụng lại kết nối service của PDB REPORTING, đăng nhập có thể thất bại dù username/password đúng trong SALES. Hãy xác nhận service trước khi đổi credential.

## 4. Username và password phân biệt hoa/thường

Oracle chuẩn hóa username không đặt trong dấu nháy kép thành chữ hoa. Ví dụ:

~~~sql
CREATE USER app_runtime IDENTIFIED BY "Example-Secret";
~~~

Username thông thường được lưu là APP_RUNTIME. Tuy nhiên, nếu tạo quoted username:

~~~sql
CREATE USER "appRuntime" IDENTIFIED BY "Example-Secret";
~~~

thì tên user có phân biệt hoa/thường và cần được tham chiếu đúng chính tả.

Password của Oracle phân biệt hoa/thường theo cơ chế password case sensitivity hiện đại. Các chuỗi sau là các password khác nhau:

~~~text
Example-Secret
example-secret
EXAMPLE-SECRET
~~~

Không nên tắt password case sensitivity để chữa lỗi ORA-01017. Hãy sửa credential được gửi từ client.

Nếu nghi ngờ username được tạo có dấu nháy kép, DBA có thể xem chính xác tên trong DBA_USERS/CDB_USERS. Không suy đoán từ tên hiển thị trong cấu hình ứng dụng.

## 5. Password có ký tự đặc biệt

Password chứa dấu nháy, dấu $, dấu &, dấu !, dấu #, dấu ;, dấu @, dấu : hoặc khoảng trắng có thể bị diễn giải khác nhau bởi:

- Shell hoặc PowerShell.
- File YAML/properties.
- Docker Compose hoặc manifest Kubernetes.
- JDBC URL.
- Script SQL*Plus.
- CI/CD variable substitution.
- Công cụ secret injection.

Ví dụ cấu hình Spring Boot:

~~~yaml
spring:
  datasource:
    username: APP_RUNTIME
    password: DB_PASSWORD_FROM_SECRET
~~~

DB_PASSWORD_FROM_SECRET là placeholder minh họa cho giá trị được inject từ environment/property source hoặc secret manager; không thay nó bằng password thật trong repository.

Không nhúng password vào JDBC URL nếu có thể truyền riêng bằng property username/password. Dùng secret manager hoặc cơ chế quản lý credential của nền tảng. Khi cần kiểm tra, xác nhận secret được inject đúng và không in giá trị ra log.

Với SQL*Plus, cách nhập password an toàn hơn là để client hỏi password thay vì đặt password thật trực tiếp trong command line:

~~~text
sqlplus /nolog
SQL> CONNECT APP_RUNTIME@//dbhost.example.com:1521/APP_SERVICE
Enter password:
~~~

Không chụp màn hình hoặc gửi log chứa password. Nếu cần minh họa password có ký tự đặc biệt trong câu lệnh SQL, dùng giá trị giả và kiểm tra quy tắc quoting của SQL client/version đang dùng.

## 6. Xác minh account tồn tại và trạng thái

Sau khi xác định đúng database/PDB, DBA kiểm tra account:

~~~sql
SELECT username,
       account_status,
       lock_date,
       expiry_date,
       profile,
       authentication_type,
       common
  FROM dba_users
 WHERE username = UPPER('APP_RUNTIME');
~~~

Các cột hữu ích:

- USERNAME: tên account.
- ACCOUNT_STATUS: trạng thái account.
- LOCK_DATE: thời điểm khóa nếu có.
- EXPIRY_DATE: ngày password hết hạn theo metadata.
- PROFILE: profile áp dụng cho user.
- AUTHENTICATION_TYPE: kiểu xác thực, nếu view/version cung cấp cột này.
- COMMON: cho biết common user hay local user trong môi trường multitenant, nếu có.

Một số trạng thái thường gặp:

| ACCOUNT_STATUS | Diễn giải |
|---|---|
| OPEN | Account mở |
| LOCKED | Account bị khóa |
| LOCKED(TIMED) | Account bị khóa theo thời gian |
| EXPIRED | Password đã hết hạn |
| EXPIRED(GRACE) | Password ở thời gian grace |
| EXPIRED & LOCKED | Password hết hạn và account đang khóa |
| EXPIRED(GRACE) & LOCKED | Trạng thái kết hợp tùy version/chính sách |

Trạng thái chính xác và cách hiển thị có thể khác theo phiên bản. Đừng chỉ nhìn một cột rồi kết luận; kiểm tra profile, thời điểm khóa và lịch sử xác thực.

## 7. ORA-28000 là gì?

ORA-28000 cho biết account đang bị khóa:

~~~text
ORA-28000: The account is locked
~~~

Account có thể bị khóa vì:

1. Số lần đăng nhập sai vượt quá giới hạn FAILED_LOGIN_ATTEMPTS trong profile.
2. DBA hoặc quy trình quản trị đã chạy ALTER USER ... ACCOUNT LOCK.
3. Một policy bảo mật hoặc quy trình tự động khóa account.
4. Account bị khóa kết hợp với trạng thái password hết hạn.

Không mặc định mọi ORA-28000 đều do password sai. Kiểm tra audit, ticket thay đổi và trạng thái profile để phân biệt khóa thủ công với khóa do failed login.

## 8. FAILED_LOGIN_ATTEMPTS và PASSWORD_LOCK_TIME

Oracle profile có thể giới hạn số lần đăng nhập sai trước khi account bị khóa.

- FAILED_LOGIN_ATTEMPTS: số lần đăng nhập sai được phép trước khi khóa account theo profile.
- PASSWORD_LOCK_TIME: thời gian account tiếp tục bị khóa sau khi đạt giới hạn; giá trị được biểu diễn theo ngày trong profile.

Kiểm tra profile của user:

~~~sql
SELECT username,
       profile
  FROM dba_users
 WHERE username = UPPER('APP_RUNTIME');
~~~

Sau đó kiểm tra các giới hạn:

~~~sql
SELECT profile,
       resource_name,
       limit
  FROM dba_profiles
 WHERE profile = 'APP_PROFILE'
   AND resource_name IN (
     'FAILED_LOGIN_ATTEMPTS',
     'PASSWORD_LOCK_TIME',
     'PASSWORD_LIFE_TIME',
     'PASSWORD_GRACE_TIME',
     'PASSWORD_REUSE_TIME',
     'PASSWORD_REUSE_MAX'
   )
 ORDER BY resource_name;
~~~

Thay APP_PROFILE bằng profile thật lấy từ DBA_USERS. Không giả định user luôn dùng DEFAULT profile.

### Ý nghĩa của giới hạn

Ví dụ, profile có:

~~~text
FAILED_LOGIN_ATTEMPTS = 5
PASSWORD_LOCK_TIME    = 1/24
~~~

thì sau năm lần đăng nhập sai liên tiếp, account bị khóa theo thời gian cấu hình; 1/24 ngày tương đương khoảng một giờ. Ví dụ chỉ để giải thích cách tính, không phải khuyến nghị dùng một giá trị cụ thể.

Nếu PASSWORD_LOCK_TIME được đặt UNLIMITED, account có thể cần DBA unlock thủ công. Nếu đặt một khoảng thời gian hữu hạn, account có thể tự được mở khi thời gian khóa kết thúc theo policy. Hãy đọc giá trị thực tế và version thay vì dựa vào mặc định.

Không nới FAILED_LOGIN_ATTEMPTS thành UNLIMITED chỉ để tránh ORA-28000. Điều đó làm giảm khả năng chống password guessing. Nếu cần thay đổi policy, phải đánh giá bảo mật và phê duyệt ở cấp hệ thống.

## 9. Mở khóa account đúng cách

Chỉ mở khóa sau khi xác nhận đúng database/PDB, đúng user và đã xác định hoặc xử lý nguồn đăng nhập sai.

Trong PDB chứa local user, DBA có thể chạy:

~~~sql
ALTER USER app_runtime ACCOUNT UNLOCK;
~~~

Kiểm tra lại:

~~~sql
SELECT username,
       account_status,
       lock_date
  FROM dba_users
 WHERE username = 'APP_RUNTIME';
~~~

Nếu account bị khóa do thời gian, DBA vẫn có thể unlock thủ công khi được phép. Nếu ứng dụng tiếp tục gửi password sai, account có thể bị khóa lại ngay.

### Common user trong CDB

Common user được quản lý ở CDB root và có phạm vi trên nhiều container tùy cấu hình. Khi cần thay đổi common user, thực hiện trong đúng container và chỉ dùng phạm vi CONTAINER=ALL khi thực sự muốn tác động toàn bộ container được áp dụng.

Ví dụ minh họa:

~~~sql
ALTER USER c##integration ACCOUNT UNLOCK CONTAINER=ALL;
~~~

Không dùng lệnh này cho local user. Local user phải được quản lý trong PDB tương ứng. Cú pháp và phạm vi container cần đối chiếu theo Oracle release và loại account.

### Unlock không đồng nghĩa reset password

Nếu password hiện tại vẫn đúng và chỉ account bị khóa, unlock có thể đủ. Nếu secret trong ứng dụng đã cũ, cần cập nhật password/secret theo quy trình và triển khai credential mới.

Khi thay password, dùng quy trình an toàn để tránh ghi secret vào script, shell history, ticket hoặc log. Sau thay đổi, xác nhận ứng dụng, job và integration client đều dùng credential mới.

## 10. Đổi password và mở khóa trong cùng thao tác

Khi cần đặt password mới và mở khóa, DBA có thể dùng:

~~~sql
ALTER USER app_runtime
  IDENTIFIED BY "New-Secret-Value"
  ACCOUNT UNLOCK;
~~~

Chuỗi trong ví dụ chỉ là placeholder. Không sử dụng password mẫu trong production và không commit câu lệnh có secret thật.

Nếu password verification function được gắn với profile, password mới phải đáp ứng chính sách. Nếu không đáp ứng, Oracle có thể trả ORA-28003 hoặc lỗi liên quan. Hãy kiểm tra policy thay vì bỏ password verification function để lệnh thành công.

Với account ứng dụng, nên phối hợp thứ tự:

1. Xác định service/PDB và account.
2. Xác định nguồn dùng credential cũ.
3. Tạo/đặt secret mới theo quy trình bảo mật.
4. Cập nhật secret store và cấu hình deployment.
5. Unlock account ở đúng container.
6. Rollout ứng dụng để pool tạo connection bằng secret mới.
7. Xác nhận đăng nhập và theo dõi account không bị khóa lại.

Thứ tự cụ thể có thể thay đổi theo hệ thống quản lý secret và cách triển khai, nhưng phải tránh khoảng thời gian nhiều client tiếp tục gửi password cũ.

## 11. ORA-01017 dẫn đến ORA-28000 như thế nào?

Một kịch bản phổ biến:

1. DBA đổi password của APP_RUNTIME.
2. Secret store đã cập nhật nhưng một số pod vẫn chạy cấu hình cũ.
3. HikariCP/UCP hoặc ứng dụng tạo connection mới bằng password cũ.
4. Các lần login thất bại tăng lên.
5. FAILED_LOGIN_ATTEMPTS đạt giới hạn.
6. Oracle khóa account.
7. Các pod khác bắt đầu nhận ORA-28000.
8. DBA unlock nhưng pod cũ tiếp tục thử password sai.
9. Account bị khóa lại.

Do đó, xử lý ORA-28000 cần điều tra cả client source và credential rollout. Chỉ chạy ALTER USER ACCOUNT UNLOCK mà không xử lý client sai có thể tạo vòng lặp sự cố.

## 12. Tìm nguồn đăng nhập sai

Mục tiêu là xác định host, chương trình, thời điểm và account tạo ra failed login. Không phải mọi nguồn audit đều được bật sẵn; khả năng truy vấn phụ thuộc Unified Auditing, traditional auditing, cấu hình listener và quyền DBA.

### Kiểm tra Unified Audit Trail

Nếu hệ thống dùng Unified Auditing và policy ghi nhận logon failure, có thể kiểm tra:

~~~sql
SELECT event_timestamp,
       dbusername,
       userhost,
       client_program_name,
       action_name,
       return_code
  FROM unified_audit_trail
 WHERE dbusername = 'APP_RUNTIME'
   AND action_name = 'LOGON'
   AND return_code <> 0
 ORDER BY event_timestamp DESC;
~~~

Tên cột và dữ liệu có thể khác theo release/audit configuration. Một số trường có thể null nếu client không gửi thông tin tương ứng. Cần kiểm tra dictionary của phiên bản và policy đang bật.

### Traditional audit

Trong môi trường dùng traditional auditing, DBA có thể xem DBA_AUDIT_SESSION:

~~~sql
SELECT username,
       userhost,
       terminal,
       timestamp,
       returncode,
       action_name
  FROM dba_audit_session
 WHERE username = 'APP_RUNTIME'
 ORDER BY timestamp DESC;
~~~

View này chỉ có dữ liệu nếu audit tương ứng được cấu hình và được lưu theo chính sách. Không bật audit rộng trên production một cách tùy tiện vì có thể tăng dung lượng và chứa thông tin nhạy cảm.

### Listener log và ứng dụng

Khi database audit không đủ thông tin, phối hợp:

- Listener log trên máy Oracle để xem thời điểm và client endpoint của kết nối.
- Log ứng dụng để xác định pod, hostname, module và thời điểm retry.
- Log Kubernetes/VM/service manager để tìm rollout hoặc secret rotation.
- Scheduler/job log để tìm batch hoặc script dùng credential cũ.
- Secret manager audit để xác định lần thay đổi và version secret.

Không đưa password vào log để xác định client. Dùng username, source host, client program, connection ID và timestamp.

## 13. Kiểm tra account bị khóa thủ công hay do failed login

DBA_USERS cho biết trạng thái hiện tại và LOCK_DATE, nhưng không phải lúc nào cũng giải thích đầy đủ nguyên nhân. Kết hợp:

1. Audit logon failure nếu có.
2. Audit/DDL history cho ALTER USER ACCOUNT LOCK.
3. Change ticket và automation log.
4. Scheduler, batch và application deployment.
5. Profile của user.

Nếu account được khóa chủ động theo chính sách, không unlock chỉ vì một ứng dụng báo lỗi. Xác nhận owner, lý do khóa và phê duyệt trước khi mở lại.

## 14. Password hết hạn khác với account bị khóa

ORA-28001 cho biết password đã hết hạn. ORA-28002 thường cảnh báo password sắp hết hạn và user đang ở grace period. Đây không giống ORA-28000.

Kiểm tra:

~~~sql
SELECT username,
       account_status,
       expiry_date,
       profile
  FROM dba_users
 WHERE username = 'APP_RUNTIME';
~~~

Kiểm tra profile:

~~~sql
SELECT profile,
       resource_name,
       limit
  FROM dba_profiles
 WHERE profile = 'APP_PROFILE'
   AND resource_name IN (
     'PASSWORD_LIFE_TIME',
     'PASSWORD_GRACE_TIME',
     'PASSWORD_REUSE_TIME',
     'PASSWORD_REUSE_MAX',
     'PASSWORD_VERIFY_FUNCTION'
   )
 ORDER BY resource_name;
~~~

Nếu password hết hạn, cần đổi password theo quy trình được duyệt. Unlock account không tự làm password hết hạn trở nên hợp lệ. Nếu account vừa expired vừa locked, xử lý cả hai điều kiện theo thứ tự phù hợp.

Với service account, cần có kế hoạch rotation trước ngày hết hạn. Đừng đặt PASSWORD_LIFE_TIME thành UNLIMITED chỉ để tránh gián đoạn nếu chính sách bảo mật không cho phép.

## 15. Password verification function

Profile có thể gắn PASSWORD_VERIFY_FUNCTION để kiểm tra password mới. Function có thể yêu cầu:

- Độ dài tối thiểu.
- Chữ hoa/chữ thường.
- Chữ số và ký tự đặc biệt.
- Không chứa username.
- Không trùng password cũ theo policy.
- Không quá giống password trước đó.

Kiểm tra:

~~~sql
SELECT profile,
       resource_name,
       limit
  FROM dba_profiles
 WHERE resource_name = 'PASSWORD_VERIFY_FUNCTION'
 ORDER BY profile;
~~~

Nếu ALTER USER trả lỗi ORA-28003, xem function được gắn với profile và policy cụ thể. Không bỏ verification function chỉ để đặt một password yếu hoặc lặp lại password cũ.

## 16. Lỗi ORA-28040 và authentication protocol

ORA-28040 thường xuất hiện khi Oracle client và server không có authentication protocol chung được chấp nhận. Lỗi có thể xuất hiện sau khi nâng cấp database, thay đổi sqlnet.ora hoặc dùng JDBC driver/client quá cũ.

Hướng điều tra:

- Xác định Oracle Database release và patch level.
- Xác định JDBC driver version thực tế của ứng dụng.
- Xác định Oracle Client/SQL*Plus version nếu dùng thick client.
- Kiểm tra SQLNET.ALLOWED_LOGON_VERSION_SERVER và các setting liên quan theo release.
- Đọc tài liệu nâng cấp và authentication compatibility của Oracle.
- Nâng driver/client lên version được hỗ trợ trước khi nới server security policy.

Không hạ authentication protocol xuống mức yếu chỉ để client cũ kết nối được. Cách đúng thường là nâng client/driver, sau đó kiểm thử các ứng dụng phụ thuộc.

## 17. ORA-01045 và quyền CREATE SESSION

Nếu username/password hợp lệ nhưng user không có quyền đăng nhập, Oracle có thể trả:

~~~text
ORA-01045: user APP_RUNTIME lacks CREATE SESSION privilege; logon denied
~~~

Kiểm tra quyền:

~~~sql
SELECT grantee,
       privilege
  FROM dba_sys_privs
 WHERE grantee = 'APP_RUNTIME'
   AND privilege = 'CREATE SESSION';
~~~

Nếu policy cho phép, DBA có thể cấp:

~~~sql
GRANT CREATE SESSION TO app_runtime;
~~~

Không cấp DBA chỉ để sửa ORA-01045. User runtime thường chỉ cần CREATE SESSION và quyền object nghiệp vụ.

## 18. ORA-28009 khi kết nối bằng SYS

SYS là tài khoản quản trị đặc biệt. Khi kết nối bằng SYS, client phải chỉ định privilege phù hợp, ví dụ AS SYSDBA hoặc AS SYSOPER:

~~~text
sqlplus sys@//dbhost.example.com:1521/APP_SERVICE AS SYSDBA
~~~

Sau đó client hỏi password. Không dùng SYS trong datasource ứng dụng. Tạo user ứng dụng riêng với quyền tối thiểu.

## 19. Kiểm tra credential từ JDBC và Spring Boot

Khi SQL*Plus đăng nhập được nhưng Spring Boot nhận ORA-01017, tập trung kiểm tra:

- Ứng dụng có dùng đúng profile Spring không?
- Environment variable/secret có được inject vào process không?
- Có pod nào vẫn dùng secret version cũ không?
- JDBC URL có đúng host, port và service không?
- Username có bị thêm dấu cách hoặc ký tự xuống dòng không?
- Password có bị YAML, shell hoặc CI variable thay đổi không?
- Có nhiều DataSource và một datasource vẫn dùng credential cũ không?
- Pool có đang tạo connection mới bằng cấu hình cũ không?

Không in password để so sánh. Có thể so sánh secret version, secret reference, thời điểm cập nhật và checksum được tạo theo quy trình nội bộ không thể đảo ngược, nếu chính sách cho phép.

### Kiểm tra database product/service khi kết nối thành công

Một endpoint health check có thể xác nhận database/service:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name,
       SYS_CONTEXT('USERENV', 'CON_NAME') AS con_name,
       SYS_CONTEXT('USERENV', 'SERVICE_NAME') AS service_name,
       USER AS connected_user
  FROM dual;
~~~

Không để health check đăng nhập liên tục với password sai. Health check phải dùng cùng secret lifecycle với datasource chính hoặc chỉ kiểm tra process/network ở lớp không cần xác thực database.

## 20. Connection pool sau khi đổi password

HikariCP và UCP giữ các JDBC connection vật lý đã tạo. Sau khi password của database user thay đổi:

- Connection vật lý đã xác thực có thể tiếp tục hoạt động cho đến khi bị đóng/invalidated.
- Khi pool cần tạo connection mới, nó dùng credential đang cấu hình trong pool.
- Nếu pool chưa nhận secret mới, connection mới có thể nhận ORA-01017.
- Nếu nhiều instance còn credential cũ, account có thể tiếp tục bị khóa.

Vì vậy, sau password rotation:

1. Cập nhật secret store.
2. Cập nhật deployment/configuration reference.
3. Rollout hoặc refresh DataSource/pool theo cách được hỗ trợ.
4. Xác nhận tất cả replica đã dùng secret mới.
5. Theo dõi failed login và account status.

Không restart toàn bộ hệ thống một cách mù quáng khi chưa xác định client nào gây lỗi. Rollout có kiểm soát và theo dõi log giúp tránh tạo thêm login storm.

## 21. Quy trình xử lý ORA-01017

### Bước 1: ghi nhận bối cảnh

Thu thập:

- Timestamp và timezone.
- Username (không thu thập password).
- Host/port/service.
- PDB/database đích.
- Client: SQL*Plus, SQLcl, JDBC, Spring Boot, job hay tool.
- Hostname/pod/program name.
- Lỗi đầu tiên và số lần retry.

### Bước 2: xác minh endpoint

Kiểm tra DNS, listener, service name và PDB. Nếu lỗi là ORA-12154/12514/12541, xử lý kết nối trước.

### Bước 3: kiểm tra user ở đúng container

DBA_USERS hoặc CDB_USERS xác nhận account tồn tại, đúng common/local user và trạng thái.

### Bước 4: xác minh credential bằng client an toàn

Dùng SQL*Plus/SQLcl hoặc một công cụ được phê duyệt, để client hỏi password. Không gửi password qua ticket/chat và không đặt vào command line.

### Bước 5: kiểm tra case, special characters và secret version

So sánh username, secret reference, secret version và cấu hình client. Không in password.

### Bước 6: kiểm tra driver/authentication protocol

Nếu credential và endpoint đã đúng, kiểm tra JDBC/client version và ORA-28040 hoặc lỗi authentication liên quan.

### Bước 7: kiểm tra audit và nguồn login

Nếu lỗi xảy ra lặp lại, xác định pod, job hoặc host gây failed login trước khi thay password hoặc mở khóa.

## 22. Quy trình xử lý ORA-28000

### Bước 1: không tiếp tục thử login

Tạm dừng retry hoặc job đang dùng credential nghi sai theo runbook. Việc tiếp tục thử có thể làm tình trạng khó kiểm soát hơn.

### Bước 2: xác nhận đúng account/container

Kiểm tra DB_NAME, CON_NAME, SERVICE_NAME và DBA_USERS/CDB_USERS. Tránh unlock user cùng tên ở sai PDB.

### Bước 3: xác định trạng thái và profile

Xem ACCOUNT_STATUS, LOCK_DATE, EXPIRY_DATE, PROFILE, FAILED_LOGIN_ATTEMPTS và PASSWORD_LOCK_TIME.

### Bước 4: tìm nguồn failed login

Đối chiếu Unified Audit Trail/traditional audit, listener log, application log, scheduler và secret rotation history.

### Bước 5: sửa nguyên nhân

Ví dụ:

- Cập nhật secret cũ ở pod.
- Sửa service name đang trỏ sai PDB.
- Sửa username case.
- Sửa quoting khi password có ký tự đặc biệt.
- Nâng JDBC driver nếu authentication protocol không tương thích.
- Dừng job cũ đang dùng credential đã thu hồi.

### Bước 6: unlock hoặc đổi password

Chỉ thực hiện sau khi nguồn login sai đã được xử lý và có phê duyệt. Dùng ALTER USER trong đúng PDB hoặc đúng CDB scope.

### Bước 7: xác nhận và theo dõi

Kiểm tra account OPEN, đăng nhập thành công, application pool tạo connection mới và không có failed login lặp lại.

## 23. Một số truy vấn DBA hữu ích

### Account và trạng thái

~~~sql
SELECT username,
       account_status,
       lock_date,
       expiry_date,
       profile
  FROM dba_users
 WHERE username = UPPER('APP_RUNTIME');
~~~

### Profile limits

~~~sql
SELECT profile,
       resource_name,
       limit
  FROM dba_profiles
 WHERE profile = 'APP_PROFILE'
   AND resource_name IN (
     'FAILED_LOGIN_ATTEMPTS',
     'PASSWORD_LOCK_TIME',
     'PASSWORD_LIFE_TIME',
     'PASSWORD_GRACE_TIME',
     'PASSWORD_REUSE_TIME',
     'PASSWORD_REUSE_MAX',
     'PASSWORD_VERIFY_FUNCTION'
   )
 ORDER BY resource_name;
~~~

### User trong các PDB

~~~sql
SELECT con_id,
       username,
       common,
       account_status,
       profile,
       lock_date,
       expiry_date
  FROM cdb_users
 WHERE username = UPPER('APP_RUNTIME')
 ORDER BY con_id;
~~~

### Quyền đăng nhập

~~~sql
SELECT grantee,
       privilege
  FROM dba_sys_privs
 WHERE grantee = 'APP_RUNTIME'
 ORDER BY privilege;
~~~

### Audit logon failure

~~~sql
SELECT event_timestamp,
       dbusername,
       userhost,
       client_program_name,
       action_name,
       return_code
  FROM unified_audit_trail
 WHERE dbusername = 'APP_RUNTIME'
   AND action_name = 'LOGON'
   AND return_code <> 0
 ORDER BY event_timestamp DESC;
~~~

Các view DBA_/CDB_ và Unified Audit Trail cần quyền đọc tương ứng. Chỉ cấp quyền audit/diagnostic cho DBA hoặc monitoring role được phê duyệt; không cấp SELECT ANY DICTIONARY cho ứng dụng runtime để tiện điều tra.

## 24. Bảo vệ account ứng dụng

Một account ứng dụng nên có:

- Một owner nghiệp vụ và technical owner.
- Quyền CREATE SESSION và object privilege tối thiểu.
- Profile phù hợp với chính sách password.
- Credential được quản lý tập trung.
- Quy trình rotation và rollout.
- Monitoring cho failed login và account lock.
- Kế hoạch xử lý khi secret bị lộ.
- Tài khoản riêng cho từng môi trường hoặc service khi cần.

Không chia sẻ một account DBA giữa nhiều ứng dụng. Nếu một credential dùng chung cho nhiều service, khi bị khóa hoặc rotation sẽ ảnh hưởng nhiều hệ thống và khó truy nguồn.

### Account runtime và account migration

Nên cân nhắc tách:

- Owner schema sở hữu object.
- Migration user chạy DDL trong deployment.
- Runtime user chạy DML/EXECUTE.
- Read-only user cho báo cáo/tích hợp.

Runtime user không nên có CREATE USER, ALTER USER, DROP ANY TABLE hoặc DBA role. Việc tách này giảm tác động khi credential runtime bị lộ.

## 25. Giảm nguy cơ account bị khóa lặp lại

Các biện pháp thực tế:

1. Dùng secret manager và một nguồn credential chuẩn.
2. Có rollout đồng bộ khi password thay đổi.
3. Kiểm tra tất cả replica, batch job và scheduled task.
4. Tránh health check retry login liên tục.
5. Dùng exponential backoff và circuit breaker cho lỗi xác thực.
6. Cảnh báo khi failed login tăng bất thường.
7. Phân biệt lỗi password với lỗi network/service.
8. Không dùng một account cho quá nhiều client không liên quan.
9. Có runbook unlock và rotation.
10. Ghi lại thời điểm, owner và phạm vi mỗi lần thay đổi account.

Không nên tăng FAILED_LOGIN_ATTEMPTS quá cao để che một secret stale. Hãy sửa vòng đời credential và retry behavior.

## 26. Audit, monitoring và cảnh báo

Monitoring nên phát hiện sớm:

- Số lượng logon failure tăng theo user hoặc host.
- Account chuyển sang LOCKED hoặc LOCKED(TIMED).
- Password sắp hết hạn.
- Nhiều pod cùng nhận ORA-01017.
- Một client cũ vẫn cố kết nối sau rotation.
- Failed login đến từ host ngoài danh sách dự kiến.

Các cảnh báo cần gắn với owner:

| Tín hiệu | Hành động |
|---|---|
| Một vài lần ORA-01017 từ máy DBA | Xác minh nhập liệu và endpoint |
| ORA-01017 lặp lại từ một pod | Kiểm tra secret/config/pool của pod |
| Nhiều host cùng fail | Kiểm tra rotation, service hoặc auth protocol |
| ORA-28000 | Dừng nguồn retry sai, kiểm tra profile/audit và unlock theo phê duyệt |
| ORA-28001/28002 | Lập kế hoạch đổi password và cập nhật secret |
| ORA-28040 sau upgrade | Kiểm tra client/JDBC compatibility |

Audit log có thể chứa hostname, username, chương trình và thông tin vận hành. Áp dụng retention, access control và data handling theo chính sách.

## 27. Những cách xử lý sai cần tránh

**Thử password liên tục:** làm tăng failed login và có thể khóa account. Dừng thử, xác minh nguồn credential.

**Unlock ngay mà không tìm client gây lỗi:** ứng dụng có thể khóa lại account trong vài giây.

**Reset password trong sai PDB:** account cùng tên ở PDB khác không phải account ứng dụng đang dùng.

**Tắt password case sensitivity:** làm yếu chính sách xác thực và không xử lý secret sai.

**Đặt FAILED_LOGIN_ATTEMPTS thành UNLIMITED:** giảm bảo vệ trước password guessing.

**Đặt PASSWORD_LIFE_TIME thành UNLIMITED để tránh expired:** cần quyết định theo security policy và compliance của tổ chức, không phải workaround tùy tiện.

**Cấp DBA cho runtime user:** không cần thiết để đăng nhập hoặc chạy nghiệp vụ thông thường.

**Ghi password vào log/ticket/chat:** tạo thêm nơi lưu credential nhạy cảm.

**Dùng SYS trong datasource ứng dụng:** tăng rủi ro và không đúng ranh giới quyền.

**Restart tất cả ứng dụng trước khi sửa secret:** có thể tạo thêm login storm với credential sai.

**Cho rằng ORA-01017 luôn là password sai:** có thể là username, quoted identifier, service/PDB hoặc protocol mismatch.

**Dùng tnsping để xác nhận password:** tnsping kiểm tra Oracle Net naming/listener reachability, không xác thực database user.

## 28. Checklist xử lý sự cố

- [ ] Ghi lại mã lỗi chính xác và timestamp.
- [ ] Xác định host, port, service name và PDB.
- [ ] Xác định client, pod, job hoặc chương trình đăng nhập.
- [ ] Xác nhận username và account tồn tại ở đúng container.
- [ ] Kiểm tra ACCOUNT_STATUS, LOCK_DATE, EXPIRY_DATE và PROFILE.
- [ ] Kiểm tra FAILED_LOGIN_ATTEMPTS và PASSWORD_LOCK_TIME.
- [ ] Xác minh secret version mà client đang dùng, không in password.
- [ ] Kiểm tra username case và password special-character handling.
- [ ] Kiểm tra JDBC/Oracle client version nếu có ORA-28040.
- [ ] Đọc audit/listener/application logs để tìm nguồn login failure.
- [ ] Dừng retry sai trước khi unlock.
- [ ] Đổi password nếu cần và cập nhật toàn bộ client.
- [ ] Unlock đúng local/common user trong đúng container.
- [ ] Rollout connection pool để tạo connection bằng credential mới.
- [ ] Xác nhận account không bị khóa lại.
- [ ] Ghi lại nguyên nhân gốc và biện pháp phòng ngừa.

## 29. Ví dụ sự cố thực tế: account khóa sau password rotation

Giả sử DBA đổi password APP_RUNTIME lúc 10:00. Một deployment mới đã nhận secret version mới, nhưng một batch worker cũ vẫn chạy với secret cũ.

Biểu hiện:

- API mới kết nối thành công.
- Batch worker nhận ORA-01017.
- Sau nhiều lần retry, account nhận ORA-28000.
- API mới cũng bắt đầu lỗi vì account đã bị khóa.

Quy trình xử lý:

1. Tạm dừng batch worker cũ hoặc ngăn retry login.
2. Kiểm tra audit/listener log để xác nhận host và chương trình gây failed login.
3. Xác nhận account APP_RUNTIME trong đúng PDB.
4. Xác nhận secret version ở API và batch worker.
5. Cập nhật batch worker dùng secret mới.
6. Unlock account theo phê duyệt.
7. Restart/refresh pool của batch worker theo rollout có kiểm soát.
8. Xác nhận API và batch worker tạo connection mới thành công.
9. Theo dõi audit để bảo đảm không còn failed login.
10. Ghi lại root cause và thêm kiểm tra secret version vào deployment process.

Nếu chỉ unlock ở bước 6 mà bỏ qua worker cũ, account có thể bị khóa lại ngay.

## 30. Kết luận

ORA-01017 là lỗi Oracle từ chối thông tin xác thực được gửi đến; ORA-28000 là account đang bị khóa. Khi xử lý, cần xác nhận đúng database, service và PDB trước, sau đó kiểm tra username, password case sensitivity, secret handling, account status và profile. Password có thể hết hạn hoặc authentication protocol không tương thích, đây là các tình huống khác với account lock.

Đối với ORA-28000, hãy xác định failed login source bằng audit, listener và application logs trước khi unlock. Nếu một pod, batch job hoặc connection pool còn dùng secret cũ, account sẽ bị khóa lại sau khi mở. Sau password rotation, cập nhật tất cả client, rollout pool có kiểm soát và theo dõi trạng thái account.

Giữ quyền runtime ở mức tối thiểu, bảo vệ credential, theo dõi failed login và có quy trình rotation/unlock rõ ràng. Không dùng cách tắt password policy, tăng vô hạn số lần đăng nhập sai hoặc cấp DBA để che nguyên nhân gốc.
