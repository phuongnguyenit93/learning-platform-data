# Rà soát quyền định kỳ, tài khoản bỏ quên và truy cập từ PUBLIC

Trong Oracle Database, bảo mật không dừng lại ở việc tạo user và cấp role khi triển khai ứng dụng. Theo thời gian, nhân sự thay đổi, service cũ bị thay thế, dự án kết thúc, quyền tạm thời không được thu hồi và các object mới có thể được cấp quyền cho PUBLIC. Nếu không rà soát, database sẽ tích lũy tài khoản không còn chủ sở hữu, privilege rộng hơn nhu cầu và đường truy cập mà không ai còn nhớ lý do tồn tại.

Một quy trình bảo mật tốt cần rà soát định kỳ **tài khoản**, **role**, **system privilege**, **object privilege**, **quyền được cấp cho PUBLIC**, **tài khoản không còn hoạt động** và **bằng chứng audit**. Mục tiêu là biết danh tính nào có thể truy cập dữ liệu nào, thông qua quyền trực tiếp hay kế thừa, vì sao quyền đó tồn tại và ai chịu trách nhiệm.

Trong Oracle, PUBLIC là một pseudo-role được cấp ngầm cho mọi database user. Vì vậy, quyền được cấp cho PUBLIC có phạm vi ảnh hưởng rất rộng: mọi user hiện tại và user tạo sau này đều có thể thừa hưởng quyền đó. Đây là một trong những phần cần chú ý khi rà soát quyền định kỳ.

## 1. Vì sao phải rà soát quyền định kỳ?

Quyền database thay đổi liên tục theo vòng đời ứng dụng:

- Một developer được cấp quyền hỗ trợ production trong thời gian xử lý sự cố nhưng quyền không được thu hồi.
- Một service cũ đã ngừng chạy nhưng user và password vẫn còn.
- Một tài khoản triển khai được cấp CREATE ANY TABLE hoặc quyền rộng rồi được dùng làm tài khoản runtime.
- Một package hoặc view mới được cấp EXECUTE/SELECT cho PUBLIC để xử lý nhanh lỗi truy cập.
- Một role được cấp cho user khác, sau đó role đó tiếp tục nhận thêm system privilege.
- Một tài khoản của nhân sự đã nghỉ việc vẫn có trạng thái OPEN.
- Một user không đăng nhập trong thời gian dài nhưng vẫn được sử dụng bởi batch job chạy theo lịch.

Nếu chỉ xem danh sách user, DBA sẽ bỏ sót quyền kế thừa qua role, quyền được cấp cho PUBLIC và các session đang dùng tài khoản service. Nếu chỉ xem grant trực tiếp, có thể bỏ sót quyền đến từ role lồng nhau hoặc system privilege có phạm vi ANY.

Rà soát định kỳ giúp:

1. Thu hồi quyền không còn cần thiết.
2. Khóa tài khoản không còn chủ sở hữu hoặc không còn được sử dụng.
3. Phát hiện tài khoản dùng chung hoặc tài khoản đặc quyền không được kiểm soát.
4. Phát hiện object được cấp cho PUBLIC ngoài nhu cầu hợp lệ.
5. Giảm khả năng truy cập trái phép khi credential bị lộ.
6. Có bằng chứng cho kiểm toán và điều tra sự cố.
7. Giữ quyền database phù hợp với kiến trúc ứng dụng hiện tại.

Rà soát cần được thực hiện theo lịch của tổ chức và sau các sự kiện quan trọng như release lớn, thay đổi nhân sự, di chuyển database, kết thúc dự án hoặc phát hiện lộ credential. Không có một chu kỳ cố định phù hợp với mọi hệ thống; tần suất phải dựa trên mức độ nhạy cảm của dữ liệu và chính sách quản trị.

## 2. Hiểu đúng PUBLIC trong Oracle

PUBLIC là pseudo-role đặc biệt được Oracle cấp ngầm cho mọi user. Không cần GRANT PUBLIC TO user; mọi user đều có các privilege được cấp cho PUBLIC.

Ví dụ:

~~~sql
GRANT SELECT ON app_owner.public_reference_codes TO PUBLIC;
~~~

Sau câu lệnh này, mọi database user có thể được hưởng quyền SELECT trên object đó, bao gồm user hiện tại và user được tạo trong tương lai. Quyền này không bị giới hạn theo schema ứng dụng hoặc theo nhóm người dùng.

PUBLIC không phải một database account thông thường:

- Không có mật khẩu để đăng nhập.
- Không sở hữu một session riêng.
- Không đại diện cho một nhóm người dùng được quản lý bằng membership thông thường.
- Quyền được cấp cho PUBLIC có hiệu lực với mọi user theo cơ chế role đặc biệt của Oracle.

### PUBLIC và role thông thường

Role thông thường được tạo và cấp cho user hoặc role khác. Người quản trị có thể chọn default role, bật/tắt role trong session hoặc thu hồi role khỏi một user. PUBLIC khác ở chỗ nó luôn được áp dụng cho mọi user.

Vì vậy, khi một privilege được cấp cho PUBLIC, không thể xử lý bằng cách chỉ thu hồi một user khỏi role. Cần xem xét chính grant có grantee là PUBLIC và thu hồi grant đó nếu không còn lý do hợp lệ.

### PUBLIC grant không đồng nghĩa PUBLIC synonym

PUBLIC synonym và privilege được cấp cho PUBLIC là hai khái niệm khác nhau:

- PUBLIC synonym cung cấp tên gọi chung để tham chiếu đến object.
- Object privilege quyết định user có được đọc, ghi hoặc thực thi object đó hay không.

Tạo PUBLIC synonym không tự cấp quyền truy cập object đích. Ngược lại, cấp SELECT hoặc EXECUTE cho PUBLIC có thể cho mọi user truy cập object ngay cả khi họ dùng tên schema.object thay vì synonym.

Khi rà soát, cần xem cả PUBLIC grants và PUBLIC synonyms, nhưng không được nhầm synonym là một quyền truy cập.

## 3. Những loại quyền cần rà soát

Oracle có nhiều lớp privilege. Một cuộc rà soát đầy đủ cần xem ít nhất:

| Loại | View thường dùng | Nội dung |
|---|---|---|
| System privilege cấp trực tiếp | DBA_SYS_PRIVS | Quyền như CREATE SESSION, SELECT ANY TABLE, ALTER USER |
| Role được cấp cho user/role | DBA_ROLE_PRIVS | Quan hệ giữa grantee và granted_role, ADMIN_OPTION, DEFAULT_ROLE |
| Object privilege | DBA_TAB_PRIVS | SELECT, INSERT, UPDATE, DELETE, EXECUTE và các quyền trên object |
| Column privilege | DBA_COL_PRIVS | Một số quyền được cấp trên từng cột |
| System privilege của role | DBA_SYS_PRIVS | System privilege được cấp cho role |
| Object privilege của role | DBA_TAB_PRIVS | Object privilege được cấp cho role |
| Quyền đang bật trong session | SESSION_PRIVS, SESSION_ROLES | Quyền và role có hiệu lực trong session hiện tại |
| User/account | DBA_USERS | Trạng thái account, profile, ngày tạo và các thuộc tính xác thực |
| Session hiện tại | V$SESSION | User đang kết nối, chương trình, module, trạng thái và thời điểm logon |

Các view DBA_* thường cần quyền quản trị hoặc quyền đọc dictionary phù hợp. Nếu không có quyền, có thể dùng USER_* hoặc ALL_* trong phạm vi được phép, hoặc nhờ DBA chạy truy vấn và cung cấp kết quả.

Không nên kết luận quyền hiệu lực chỉ từ một view. Một user có thể nhận cùng một privilege từ nhiều nguồn: grant trực tiếp, role được cấp trực tiếp, role lồng nhau, PUBLIC hoặc system privilege có phạm vi rộng.

## 4. Kiểm kê user và trạng thái tài khoản

DBA_USERS là điểm bắt đầu để lập danh sách account:

~~~sql
SELECT username,
       account_status,
       created,
       lock_date,
       expiry_date,
       profile,
       authentication_type,
       common,
       oracle_maintained
  FROM dba_users
 ORDER BY username;
~~~

Các cột cần chú ý:

- USERNAME: tên user.
- ACCOUNT_STATUS: trạng thái như OPEN, LOCKED, EXPIRED hoặc các trạng thái kết hợp.
- CREATED: thời điểm tạo account.
- LOCK_DATE: thời điểm khóa nếu có.
- EXPIRY_DATE: ngày hết hạn mật khẩu nếu áp dụng.
- PROFILE: profile gắn với account.
- AUTHENTICATION_TYPE: kiểu xác thực, ví dụ PASSWORD hoặc EXTERNAL tùy cấu hình.
- COMMON: cho biết user là common user hay local user trong môi trường multitenant.
- ORACLE_MAINTAINED: cho biết account do Oracle cung cấp và quản lý trong các phiên bản hỗ trợ cột này.

ORACLE_MAINTAINED và một số cột khác phụ thuộc phiên bản. Nếu database cũ không có cột, điều chỉnh câu SELECT theo data dictionary của release đó.

Để tập trung vào user không do Oracle duy trì trên phiên bản có cột ORACLE_MAINTAINED:

~~~sql
SELECT username,
       account_status,
       created,
       lock_date,
       profile,
       authentication_type
  FROM dba_users
 WHERE oracle_maintained = 'N'
 ORDER BY created;
~~~

Không xóa hoặc khóa hàng loạt account chỉ dựa trên tên user hoặc việc account được tạo từ lâu. Trước hết cần phân loại account do ứng dụng, con người, công cụ, tích hợp, giám sát hay Oracle quản lý.

## 5. Tìm tài khoản không hoạt động

Một tài khoản có ACCOUNT_STATUS = OPEN không có nghĩa nó vẫn cần thiết. Ngược lại, một tài khoản không đăng nhập gần đây chưa chắc đã bỏ quên: batch job có thể chạy theo tháng, service dự phòng có thể chỉ hoạt động khi failover, hoặc account có thể được dùng cho tác vụ cuối kỳ.

### Dùng LAST_LOGIN khi phiên bản hỗ trợ

Một số phiên bản Oracle cung cấp cột LAST_LOGIN trong DBA_USERS để ghi nhận lần đăng nhập gần nhất. Có thể xem:

~~~sql
SELECT username,
       account_status,
       created,
       last_login,
       profile,
       authentication_type
  FROM dba_users
 WHERE oracle_maintained = 'N'
 ORDER BY last_login NULLS FIRST;
~~~

LAST_LOGIN có thể không tồn tại ở các release cũ và không phải mọi kiểu xác thực đều cung cấp thông tin giống nhau. NULL không tự động có nghĩa user chưa từng được dùng hoặc có thể xóa. Cần đối chiếu với audit, session, lịch batch và chủ sở hữu ứng dụng.

### Xem session đang kết nối

V$SESSION giúp xác định account hiện đang có session:

~~~sql
SELECT username,
       status,
       logon_time,
       machine,
       program,
       module,
       service_name,
       sql_id
  FROM v$session
 WHERE username IS NOT NULL
 ORDER BY username, logon_time;
~~~

View này chỉ cho biết session đang tồn tại tại thời điểm truy vấn. Nó không cung cấp lịch sử đầy đủ của account. Một user không có session ngay lúc kiểm tra vẫn có thể được job hoặc ứng dụng sử dụng vào thời điểm khác.

### Kết hợp nhiều nguồn bằng chứng

Trước khi đánh dấu account là không còn sử dụng, hãy kiểm tra:

- LAST_LOGIN nếu có.
- Audit trail trong khoảng thời gian phù hợp.
- Session đang tồn tại và connection pool.
- Scheduler jobs và job class liên quan.
- Database links hoặc external authentication.
- Tài liệu cấu hình ứng dụng, secret manager và pipeline triển khai.
- Chủ sở hữu nghiệp vụ và người quản lý service.
- Lịch batch cuối tháng, cuối quý, cuối năm hoặc tác vụ dự phòng.
- Dependency của package, procedure, view, synonym và integration.

Một account có thể không đăng nhập trực tiếp nhưng vẫn là owner của schema chứa object cần thiết. Khóa hoặc drop owner không đúng cách có thể làm gián đoạn ứng dụng dù account đó không được dùng để kết nối runtime.

## 6. Tìm role và quyền được cấp trực tiếp

### System privilege

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 ORDER BY grantee, privilege;
~~~

Tập trung tìm các privilege có phạm vi rộng:

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 WHERE privilege LIKE '%ANY%'
    OR privilege IN (
         'DBA',
         'ALTER USER',
         'CREATE USER',
         'DROP USER',
         'GRANT ANY PRIVILEGE',
         'GRANT ANY ROLE'
       )
 ORDER BY grantee, privilege;
~~~

Danh sách này là điểm khởi đầu, không phải toàn bộ danh mục quyền nhạy cảm. Cần đối chiếu privilege thực tế theo release và nhiệm vụ của user.

### Role được cấp cho user hoặc role khác

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role
  FROM dba_role_privs
 ORDER BY grantee, granted_role;
~~~

ADMIN_OPTION cho biết grantee có thể cấp tiếp role cho đối tượng khác hay không. DEFAULT_ROLE cho biết role có được bật mặc định khi user đăng nhập hay không. Role được cấp lồng nhau có thể tạo ra một chuỗi quyền nhiều tầng.

### Object privilege

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
  FROM dba_tab_privs
 ORDER BY grantee, owner, table_name, privilege;
~~~

GRANTABLE cho biết người nhận có thể cấp tiếp object privilege theo quyền được cấp hay không.

### Column privilege

~~~sql
SELECT grantee,
       owner,
       table_name,
       column_name,
       privilege,
       grantable
  FROM dba_col_privs
 ORDER BY grantee, owner, table_name, column_name;
~~~

Rà soát column privilege đặc biệt hữu ích khi một user chỉ cần cập nhật một số cột nhạy cảm hoặc chỉ được tham chiếu đến một cột nhất định.

## 7. Tính đến role lồng nhau và quyền hiệu lực

Nếu APP_RUNTIME được cấp APP_RUNTIME_ROLE, và APP_RUNTIME_ROLE lại được cấp DATA_READ_ROLE, các privilege của DATA_READ_ROLE có thể trở thành quyền hiệu lực thông qua chuỗi role, tùy trạng thái role và ngữ cảnh thực thi.

Có thể xem chuỗi role bắt đầu từ một user bằng truy vấn phân cấp:

~~~sql
SELECT grantee,
       granted_role,
       admin_option,
       default_role,
       LEVEL AS role_depth
  FROM dba_role_privs
 START WITH grantee = 'APP_RUNTIME'
 CONNECT BY NOCYCLE PRIOR granted_role = grantee
 ORDER BY role_depth, grantee, granted_role;
~~~

Thay APP_RUNTIME bằng user cần rà soát. Truy vấn này lần theo các role được cấp trực tiếp và các role tiếp tục được cấp cho role cha. PUBLIC là pseudo-role được áp dụng ngầm, nên phải rà soát riêng các grant có grantee là PUBLIC.

Để biết quyền thực tế trong session hiện tại, có thể kiểm tra:

~~~sql
SELECT * FROM session_roles;

SELECT * FROM session_privs;
~~~

Hai view này hữu ích khi đăng nhập bằng chính user cần kiểm tra. Chúng không phải báo cáo tổng hợp mọi quyền có thể được bật hoặc mọi đường cấp quyền trong database.

### Definer-rights PL/SQL là một trường hợp riêng

Trong named definer-rights PL/SQL unit, role thông thường bị vô hiệu hóa theo quy tắc của Oracle. Static SQL trong unit cần privilege trực tiếp cho owner. Vì vậy, khi rà soát quyền của một package owner, cần phân biệt:

- Quyền user có trong session.
- Quyền được cấp qua role.
- Direct grant mà stored unit cần khi compile và chạy.

Không nên cấp thêm quyền rộng chỉ vì một package gặp lỗi insufficient privileges. Hãy xác định object được truy cập và cấp direct grant phù hợp cho owner nếu cần.

## 8. Rà soát quyền cấp cho PUBLIC

Đây là phần trọng tâm vì một grant cho PUBLIC có thể mở quyền cho toàn bộ database user.

### System privilege cấp cho PUBLIC

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 WHERE grantee = 'PUBLIC'
 ORDER BY privilege;
~~~

Mỗi dòng là một system privilege được cấp cho PUBLIC. Hãy xem xét kỹ các quyền cho phép tạo object, truy cập dữ liệu rộng hoặc cấp tiếp quyền. Không nên mặc định mọi grant PUBLIC đều sai; một số grant có thể được Oracle hoặc sản phẩm cài đặt yêu cầu. Cần xác định owner, nguồn gốc, mục đích và tác động trước khi thu hồi.

### Object privilege cấp cho PUBLIC

~~~sql
SELECT owner,
       table_name,
       privilege,
       grantable
  FROM dba_tab_privs
 WHERE grantee = 'PUBLIC'
 ORDER BY owner, table_name, privilege;
~~~

Các object cần chú ý:

- Bảng hoặc view chứa dữ liệu nghiệp vụ.
- Package/function có khả năng đọc file, truy cập mạng, thực thi dynamic SQL hoặc thao tác hệ thống.
- Object thuộc schema ứng dụng hoặc schema tích hợp.
- Directory object và các object có thể truy cập dữ liệu ngoài database.
- Object tự tạo nhưng được cấp cho PUBLIC để tiện gọi.

Một số package do Oracle cung cấp được cấp EXECUTE cho PUBLIC theo thiết kế sản phẩm. Không thu hồi hàng loạt chỉ vì object thuộc SYS hoặc tên package trông nhạy cảm. Việc revoke sai có thể làm hỏng component, công cụ hoặc tính năng database. Cần đối chiếu tài liệu Oracle và kiểm tra dependency.

### Column privilege cấp cho PUBLIC

~~~sql
SELECT owner,
       table_name,
       column_name,
       privilege,
       grantable
  FROM dba_col_privs
 WHERE grantee = 'PUBLIC'
 ORDER BY owner, table_name, column_name, privilege;
~~~

Column privilege cũng cần được xem xét vì một cột có thể chứa thông tin cá nhân, định danh hoặc dữ liệu nhạy cảm. Hãy kiểm tra cả quyền ở cấp bảng và cấp cột.

### Vì sao PUBLIC grant nguy hiểm?

Giả sử một bảng APP_OWNER.PAYROLL chứa lương nhân viên:

~~~sql
GRANT SELECT ON app_owner.payroll TO PUBLIC;
~~~

Mọi user có thể truy cập bảng theo quyền này. Kể cả khi user chỉ được tạo để chạy một batch đơn giản, user đó cũng có thể đọc PAYROLL nếu có khả năng kết nối database.

Nếu một package có quyền thực thi thao tác rộng được cấp cho PUBLIC, mọi user có thể gọi package đó. Vì vậy, việc review PUBLIC cần xem cả privilege trực tiếp và hành vi của object được mở quyền.

## 9. Tìm PUBLIC synonym và database link công khai

PUBLIC synonym làm cho tên object dễ được tham chiếu từ nhiều schema:

~~~sql
SELECT synonym_name,
       table_owner,
       table_name,
       db_link
  FROM dba_synonyms
 WHERE owner = 'PUBLIC'
 ORDER BY synonym_name;
~~~

PUBLIC synonym không tự cấp quyền trên object đích. Tuy nhiên, synonym có thể làm object dễ được phát hiện và sử dụng hơn khi user đã có privilege tương ứng. Hãy xác định synonym nào do ứng dụng tạo, synonym nào do Oracle tạo và synonym nào không còn được dùng.

Database link công khai cần được rà soát riêng:

~~~sql
SELECT owner,
       db_link,
       username,
       host
  FROM dba_db_links
 WHERE owner = 'PUBLIC'
 ORDER BY db_link;
~~~

Một PUBLIC database link có thể được mọi user sử dụng theo quyền và cấu hình của link. Nếu link lưu thông tin xác thực cố định, cần đánh giá remote privilege, credential, host đích và phạm vi dữ liệu có thể truy cập. Không chia sẻ mật khẩu hoặc thông tin nhạy cảm của link trong báo cáo rà soát.

Không drop synonym hoặc database link chỉ dựa trên tên. Kiểm tra dependency trong code, job, view, package và cấu hình ứng dụng trước.

## 10. Phân biệt grant do ứng dụng tạo và grant do Oracle quản lý

Trong database có nhiều object thuộc schema hệ thống và nhiều grant PUBLIC được tạo khi cài đặt hoặc cấu hình component. Một số grant là cần thiết để database hoặc tính năng hoạt động đúng.

Trước khi thu hồi grant:

1. Xác định owner và object.
2. Xác định object có thuộc schema Oracle-maintained hay không.
3. Tìm tài liệu component hoặc tính năng sử dụng object.
4. Kiểm tra dependency của ứng dụng và package.
5. Xác định grant được tạo bởi script cài đặt, ứng dụng hay thay đổi thủ công.
6. Thử trong môi trường test tương ứng.
7. Có kế hoạch rollback và kiểm tra chức năng sau khi revoke.

Trong các release hỗ trợ, DBA_OBJECTS có cột ORACLE_MAINTAINED giúp nhận diện object do Oracle cung cấp. Cột này là một tín hiệu phân loại, không thay thế việc đọc tài liệu và kiểm tra dependency.

Ví dụ xem object được cấp cho PUBLIC cùng thông tin owner:

~~~sql
SELECT p.owner,
       p.table_name,
       p.privilege,
       o.oracle_maintained,
       o.object_type,
       o.status
  FROM dba_tab_privs p
  LEFT JOIN dba_objects o
    ON o.owner = p.owner
   AND o.object_name = p.table_name
 WHERE p.grantee = 'PUBLIC'
 ORDER BY p.owner, p.table_name, p.privilege;
~~~

Một số object privilege có thể áp dụng cho object không xuất hiện tương ứng trong DBA_OBJECTS theo cách join đơn giản này, hoặc metadata phụ thuộc loại object. Dùng truy vấn như một danh sách điều tra ban đầu, không phải bằng chứng đầy đủ về dependency.

## 11. Rà soát quyền rộng và quyền có thể cấp tiếp

Các quyền sau cần được xem xét kỹ:

- SELECT ANY TABLE, READ ANY TABLE.
- INSERT ANY TABLE, UPDATE ANY TABLE, DELETE ANY TABLE.
- EXECUTE ANY PROCEDURE.
- CREATE ANY PROCEDURE, CREATE ANY TABLE.
- ALTER ANY TABLE, DROP ANY TABLE.
- GRANT ANY PRIVILEGE, GRANT ANY ROLE.
- Bất kỳ role quản trị rộng như DBA.
- ADMIN_OPTION trên role hoặc system privilege.
- GRANTABLE trên object privilege.

Truy vấn tìm system privilege có phạm vi rộng:

~~~sql
SELECT grantee,
       privilege,
       admin_option
  FROM dba_sys_privs
 WHERE privilege LIKE '%ANY%'
    OR privilege LIKE 'GRANT ANY%'
 ORDER BY grantee, privilege;
~~~

Truy vấn tìm object grant có thể cấp tiếp:

~~~sql
SELECT grantee,
       owner,
       table_name,
       privilege,
       grantable
  FROM dba_tab_privs
 WHERE grantable = 'YES'
 ORDER BY grantee, owner, table_name;
~~~

GRANTABLE = YES cho biết người nhận object privilege có thể cấp tiếp quyền đó. ADMIN_OPTION = YES trên role hoặc system privilege cũng cho phép cấp tiếp theo phạm vi của privilege. Đây là các điểm cần xem xét trong kiểm soát phân quyền và separation of duties.

## 12. Phát hiện tài khoản bỏ quên: quy trình điều tra

Không nên dùng một tiêu chí duy nhất để kết luận account đã bỏ quên. Hãy kết hợp trạng thái account, login history, session, job, ứng dụng và xác nhận chủ sở hữu.

### Bước 1: lập danh sách account ứng viên

~~~sql
SELECT username,
       account_status,
       created,
       lock_date,
       expiry_date,
       profile,
       authentication_type
  FROM dba_users
 WHERE oracle_maintained = 'N'
 ORDER BY account_status, username;
~~~

Trên release không có ORACLE_MAINTAINED, bỏ điều kiện đó và phân loại user bằng nguồn inventory khác.

### Bước 2: xác định chủ sở hữu

Mỗi account nên có:

- Owner kỹ thuật hoặc nhóm chịu trách nhiệm.
- Ứng dụng/service sử dụng.
- Môi trường và PDB.
- Mục đích đăng nhập.
- Người phê duyệt quyền.
- Ngày review gần nhất.
- Ngày dự kiến hết hạn hoặc ngày đánh giá lại.

Nếu không xác định được owner, đánh dấu account cần điều tra, không tự động drop.

### Bước 3: kiểm tra hoạt động

Đối chiếu LAST_LOGIN nếu có, audit trail, V$SESSION, scheduler jobs, connection pool, DB links và log ứng dụng. Với batch chạy theo tháng hoặc quý, kiểm tra ít nhất một chu kỳ nghiệp vụ đầy đủ trước khi kết luận.

### Bước 4: phân loại

Có thể phân loại:

| Nhóm | Cách xử lý thường gặp |
|---|---|
| Account cá nhân đã nghỉ việc | Khóa hoặc thu hồi theo quy trình offboarding |
| Service account đang hoạt động | Giữ, xác nhận owner và thu hẹp privilege |
| Service account cũ đã thay thế | Xác nhận không còn traffic/job rồi khóa |
| Schema owner | Giữ quyền sở hữu object; khóa login nếu không cần kết nối trực tiếp |
| Account do Oracle duy trì | Không khóa/drop tùy tiện; theo tài liệu Oracle |
| Account không xác định được owner | Điều tra, tìm dependency và chuyển người chịu trách nhiệm |
| Account dự phòng hoặc batch định kỳ | Xác minh lịch hoạt động và quy trình failover trước khi khóa |

### Bước 5: khóa trước khi xóa

Khi đã xác nhận account không còn cần đăng nhập, có thể khóa account để ngăn kết nối mới:

~~~sql
ALTER USER old_service_user ACCOUNT LOCK;
~~~

Khóa account là bước có thể đảo ngược:

~~~sql
ALTER USER old_service_user ACCOUNT UNLOCK;
~~~

Khóa account không đồng nghĩa với việc kết thúc các session đang tồn tại. Nếu cần chấm dứt session, phải kiểm tra session, transaction và tác động ứng dụng trước khi thực hiện thao tác quản trị tương ứng.

### Bước 6: theo dõi trước khi drop

Sau khi khóa, theo dõi lỗi đăng nhập, job thất bại, kết nối ứng dụng và phản hồi của owner trong khoảng thời gian phù hợp với chu kỳ nghiệp vụ. Nếu không phát sinh dependency và đã có phê duyệt, mới xem xét drop account theo quy trình thay đổi.

DROP USER ... CASCADE có thể xóa toàn bộ object thuộc schema của user. Đây là thao tác phá hủy dữ liệu và object; chỉ thực hiện khi đã xác nhận ownership, backup/retention, dependency, export cần giữ và kế hoạch phục hồi.

## 13. Tài khoản bị khóa, hết hạn và tài khoản không đăng nhập

Các trạng thái account có ý nghĩa khác nhau:

- OPEN: account có thể đăng nhập nếu các điều kiện khác cho phép.
- LOCKED: account bị khóa.
- EXPIRED: mật khẩu hết hạn theo profile.
- EXPIRED & LOCKED hoặc các trạng thái kết hợp: account vừa hết hạn vừa bị khóa.
- Các trạng thái khác có thể xuất hiện theo phiên bản, xác thực và chính sách.

Một account LOCKED vẫn có thể sở hữu schema và object đang được ứng dụng khác tham chiếu. Không drop chỉ vì account đã khóa.

Một account EXPIRED có thể là service account đang gặp lỗi rotation. Trước khi reset password, cần xác minh owner và luồng secret manager.

Một account OPEN nhưng không có LAST_LOGIN có thể chưa từng đăng nhập bằng phương thức được ghi nhận, hoặc cột không được hỗ trợ/không có dữ liệu. Cần xem thêm audit và lịch vận hành.

## 14. Audit việc cấp quyền và thay đổi tài khoản

Rà soát định kỳ cần bằng chứng về việc ai tạo user, thay đổi account, cấp quyền hoặc thu hồi quyền. Oracle Unified Auditing có thể ghi nhận các hành động này nếu audit policy phù hợp đã được tạo và bật.

Ví dụ tạo policy audit cho thay đổi user và privilege:

~~~sql
CREATE AUDIT POLICY security_account_changes
  ACTIONS CREATE USER, ALTER USER, DROP USER, GRANT, REVOKE;

AUDIT POLICY security_account_changes;
~~~

Cú pháp action và khả năng audit phụ thuộc phiên bản, chế độ Unified Auditing và quyền thực hiện. Hãy thử policy trong môi trường tương ứng và xác nhận các hành động thực tế xuất hiện trong audit trail.

Xem các sự kiện gần đây:

~~~sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       userhost,
       client_program_name
  FROM unified_audit_trail
 WHERE event_timestamp >= SYSTIMESTAMP - INTERVAL '90' DAY
   AND action_name IN (
         'CREATE USER',
         'ALTER USER',
         'DROP USER',
         'GRANT',
         'REVOKE'
       )
 ORDER BY event_timestamp DESC;
~~~

Khoảng 90 ngày chỉ là ví dụ. Chọn khoảng thời gian theo chính sách retention và yêu cầu điều tra. Các cột, loại action và khả năng ghi nhận phụ thuộc cấu hình. Nếu database đang dùng traditional auditing hoặc chế độ mixed mode, cần xem view audit tương ứng và xác nhận nơi lưu audit record.

### Audit đăng nhập và hoạt động của account

Có thể tạo policy theo dõi logon nếu phù hợp với chính sách:

~~~sql
CREATE AUDIT POLICY user_logon_events
  ACTIONS LOGON;

AUDIT POLICY user_logon_events;
~~~

Audit logon toàn hệ thống có thể tạo lượng dữ liệu lớn. Nên cân nhắc phạm vi user, điều kiện audit, dung lượng, retention và tác động vận hành. Một số môi trường đã có policy mặc định hoặc policy được quản lý tập trung; kiểm tra cấu hình trước khi tạo policy trùng lặp.

### Bảo vệ audit trail

Audit trail chỉ có giá trị khi người bị audit không thể tự ý sửa hoặc xóa bằng quyền thông thường. Hạn chế quyền đọc, export, purge và thay đổi audit policy; lưu trữ theo retention; đồng bộ thời gian; và chuyển dữ liệu quan trọng sang hệ thống giám sát tập trung theo chính sách.

## 15. Rà soát PUBLIC theo cách có kiểm soát

Một quy trình xử lý PUBLIC grant có thể gồm:

1. Xuất danh sách system privilege có grantee PUBLIC.
2. Xuất object privilege và column privilege có grantee PUBLIC.
3. Phân loại object theo owner, loại object và mức độ nhạy cảm.
4. Tìm tài liệu Oracle hoặc tài liệu ứng dụng giải thích grant.
5. Kiểm tra dependency của code, job, synonym và client.
6. Xác định grant có thật sự cần cho mọi user hay chỉ một role/service.
7. Thử thay PUBLIC bằng role chuyên biệt trong môi trường test.
8. Kiểm tra login và nghiệp vụ sau thay đổi.
9. Thu hồi grant PUBLIC nếu đã xác nhận không cần thiết.
10. Lưu kết quả, owner, approver và kế hoạch rollback.

Ví dụ nếu một package chỉ cần cho service ORDER_RUNTIME, có thể thay quyền PUBLIC bằng role riêng:

~~~sql
CREATE ROLE order_api_role;

GRANT EXECUTE ON app_owner.order_api TO order_api_role;
GRANT order_api_role TO order_runtime;

REVOKE EXECUTE ON app_owner.order_api FROM PUBLIC;
~~~

Chỉ chạy REVOKE sau khi đã xác minh không có user khác phụ thuộc vào quyền PUBLIC và role mới đã được cấp cho tất cả service hợp lệ. Nếu package do Oracle quản lý hoặc là thành phần của database, cần theo hướng dẫn Oracle trước khi thay đổi.

### Không thu hồi PUBLIC theo kiểu hàng loạt

Không nên chạy script tự động revoke mọi grant có grantee PUBLIC. Một số quyền là cần thiết cho database component hoặc tính năng đã cài đặt. Việc revoke có thể gây lỗi khó phát hiện, ảnh hưởng công cụ quản trị hoặc làm hỏng quy trình ứng dụng.

Thay vào đó, ưu tiên phân loại:

- Grant do ứng dụng tự tạo.
- Grant do sản phẩm hoặc component Oracle tạo.
- Grant do bên thứ ba tạo.
- Grant không rõ nguồn gốc.

Với grant không rõ nguồn gốc, tìm lịch sử thay đổi, script triển khai, audit trail và owner trước khi quyết định.

## 16. PUBLIC trong môi trường Multitenant

Trong Oracle Multitenant, cần phân biệt CDB root và từng PDB. Một số grant có thể là common hoặc local; phạm vi hiệu lực và metadata được thể hiện qua các cột như COMMON, INHERITED và CON_ID trong các view tương ứng của CDB.

Khi rà soát toàn CDB:

- Kiểm tra grant ở CDB root và từng PDB.
- Phân biệt common grant với local grant.
- Xem CON_ID để biết container liên quan.
- Kiểm tra user common và local.
- Không mặc định một grant nhìn thấy ở root có cùng phạm vi với grant được tạo trong PDB.

Ví dụ xem object privilege cấp cho PUBLIC từ CDB view nếu tài khoản có quyền và đang ở container phù hợp:

~~~sql
SELECT con_id,
       owner,
       table_name,
       privilege,
       grantable,
       common,
       inherited
  FROM cdb_tab_privs
 WHERE grantee = 'PUBLIC'
 ORDER BY con_id, owner, table_name, privilege;
~~~

Tương tự có thể dùng CDB_SYS_PRIVS và CDB_COL_PRIVS để kiểm tra system và column privilege. Cấu hình CONTAINER_DATA và quyền truy cập CDB view có thể giới hạn những container nhìn thấy. Nếu chỉ rà soát trong một PDB, các DBA_* view thường phản ánh metadata của container hiện tại theo ngữ cảnh kết nối.

Không dùng một truy vấn ở PDB để kết luận toàn bộ CDB đã sạch PUBLIC grants. Phải xác định phạm vi container của cuộc rà soát.

## 17. Kiểm tra quyền qua ứng dụng và schema owner

Danh sách grant không cho biết toàn bộ cách ứng dụng sử dụng quyền. Cần đối chiếu với:

- Connection string và service name của từng ứng dụng.
- User trong connection pool.
- Secret manager hoặc wallet.
- Stored procedure, package, trigger và job.
- Database link, directory object và external procedure nếu có.
- Synonym công khai và riêng.
- View có quyền truy cập dữ liệu khác schema.
- Definer-rights và invoker-rights PL/SQL.
- Proxy authentication hoặc external authentication.

Một ứng dụng có thể dùng một runtime account chung cho nhiều service. Khi đó, database khó phân biệt nguồn gọi nếu không gắn module/action hoặc context phù hợp. Tách service account và gắn metadata giúp review và audit dễ hơn.

### Kiểm tra owner không dùng làm runtime

Schema owner có thể cần sở hữu object nhưng không cần đăng nhập thường xuyên. Có thể khóa login của owner sau khi triển khai nếu kiến trúc cho phép:

~~~sql
ALTER USER app_owner ACCOUNT LOCK;
~~~

Trước khi khóa, xác nhận pipeline triển khai, job, công cụ quản trị và quy trình rotation có thể hoạt động theo danh tính khác. Việc khóa owner không làm mất object nhưng có thể làm các tác vụ kết nối bằng owner thất bại.

## 18. Quy trình rà soát định kỳ từ đầu đến cuối

Một đợt access review có thể chia thành các bước sau:

### Bước 1: xác định phạm vi

Ghi rõ database, CDB/PDB, schema, môi trường, nhóm ứng dụng và thời gian review. Xác định dữ liệu nhạy cảm, account đặc quyền và các hệ thống tích hợp liên quan.

### Bước 2: thu thập inventory

Lấy danh sách user, trạng thái, profile, role, system privilege, object privilege, column privilege, PUBLIC grants, synonym và database link.

### Bước 3: lập bản đồ quyền hiệu lực

Lần theo role lồng nhau, system privilege, direct grant và PUBLIC. Với các user quan trọng, đăng nhập bằng đúng account trong môi trường test để xem SESSION_ROLES và SESSION_PRIVS.

### Bước 4: xác minh owner và mục đích

Gửi danh sách account và privilege cho owner kỹ thuật/nghiệp vụ xác nhận. Mỗi account cần mục đích, môi trường, owner và thời điểm review.

### Bước 5: tìm quyền dư và account bỏ quên

Đánh dấu user không rõ owner, account không hoạt động, role quá rộng, ANY privilege, quyền cấp tiếp, PUBLIC grant và quyền không còn khớp với chức năng ứng dụng.

### Bước 6: đánh giá tác động

Kiểm tra code, job, integration, dependency và chu kỳ nghiệp vụ. Không dùng LAST_LOGIN đơn lẻ để kết luận account có thể khóa.

### Bước 7: lập kế hoạch thay đổi

Ưu tiên thay quyền rộng bằng role hẹp, khóa account không cần thiết, thu hồi grant PUBLIC đã xác nhận dư và tách tài khoản theo service. Ghi rõ người phê duyệt, thời gian, bước rollback và cách kiểm tra.

### Bước 8: thử nghiệm

Thử trong development/staging hoặc một môi trường tương đương. Kiểm tra login, API, batch, report, job, failover và các chức năng cuối kỳ.

### Bước 9: triển khai và giám sát

Thực hiện trong cửa sổ thay đổi. Theo dõi lỗi ORA-01031, ORA-01017, job failure, connection failure và các sự kiện audit bất thường.

### Bước 10: lưu bằng chứng

Lưu inventory trước/sau, grant đã thu hồi, account đã khóa, phê duyệt, kết quả kiểm thử, audit event và ngoại lệ được chấp nhận.

## 19. Mẫu bảng theo dõi access review

Một bảng quản lý quyền có thể gồm các cột:

| Trường | Mục đích |
|---|---|
| Database / PDB | Phạm vi container |
| Username / Role | Danh tính hoặc nhóm quyền |
| Account type | Human, service, schema owner, deployment, monitor |
| Owner | Nhóm/người chịu trách nhiệm |
| Account status | OPEN, LOCKED, EXPIRED... |
| Last login / evidence | Dữ liệu hoạt động và nguồn xác minh |
| Granted roles | Role trực tiếp và lồng nhau |
| System privileges | Quyền hệ thống |
| Object privileges | Quyền trên object |
| PUBLIC exposure | Có grant hoặc dependency qua PUBLIC hay không |
| Sensitive privilege | ANY, DBA, ADMIN_OPTION, GRANTABLE |
| Decision | Keep, reduce, lock, revoke, investigate |
| Approver | Người phê duyệt |
| Due date | Hạn xử lý |
| Evidence | Ticket, audit record, test result |

Một account được giữ lại vẫn cần lý do và owner. Một quyền ngoại lệ vẫn cần thời hạn và ngày review lại.

## 20. Xử lý khi phát hiện quyền PUBLIC không mong muốn

Nếu phát hiện bảng nhạy cảm hoặc package ứng dụng được cấp cho PUBLIC:

1. Xác định object và privilege chính xác.
2. Xác định dữ liệu hoặc thao tác mà privilege cho phép.
3. Tìm user/service nào đang phụ thuộc vào quyền đó.
4. Xác định role hẹp hơn hoặc API thay thế.
5. Thử revoke và grant role trong môi trường kiểm thử.
6. Xác nhận mọi ứng dụng hợp lệ vẫn hoạt động.
7. Triển khai thay đổi có phê duyệt.
8. Theo dõi lỗi truy cập và audit sau thay đổi.
9. Ghi nhận ngoại lệ nếu grant cần được giữ lại.

Nếu grant đã bị khai thác hoặc có dấu hiệu truy cập trái phép, chuyển sang quy trình incident response: bảo toàn audit evidence, xác định phạm vi dữ liệu, xử lý credential, khóa đường truy cập cần thiết và thông báo theo chính sách tổ chức.

## 21. Những sai lầm thường gặp

**Khóa user chỉ vì LAST_LOGIN cũ:** có thể làm batch cuối kỳ hoặc service dự phòng thất bại. Xác minh lịch hoạt động và owner trước.

**Drop user để dọn danh sách:** DROP USER ... CASCADE có thể xóa schema object. Khóa trước, đánh giá dependency và backup rồi mới xem xét drop.

**Thu hồi mọi quyền PUBLIC:** có thể phá chức năng Oracle hoặc ứng dụng. Phân loại nguồn gốc và dependency trước.

**Chỉ xem DBA_SYS_PRIVS:** bỏ sót object grants, column grants, role lồng nhau và PUBLIC.

**Chỉ xem quyền trực tiếp của user:** bỏ sót privilege nhận qua role và system privilege có phạm vi ANY.

**Nhầm PUBLIC synonym với PUBLIC privilege:** synonym không tự cấp quyền trên object.

**Coi account OPEN là account đang hoạt động:** OPEN chỉ là trạng thái cho phép đăng nhập; không chứng minh có owner hoặc nhu cầu.

**Coi account LOCKED là schema có thể xóa:** khóa login không xóa object và dependency.

**Bỏ qua common/local trong CDB:** có thể rà soát thiếu container hoặc thu hồi nhầm grant có phạm vi khác.

**Không audit grant/revoke:** sau sự cố không biết ai đã cấp quyền và thay đổi vào lúc nào.

**Không ghi ngoại lệ:** quyền dư được giữ lại mà không có owner hoặc thời hạn sẽ trở thành rủi ro tồn tại lâu dài.

## 22. Checklist thực hiện một đợt rà soát

- [ ] Xác định database, instance, CDB/PDB và môi trường.
- [ ] Lập inventory user, role và trạng thái account.
- [ ] Xác định owner của từng account và service.
- [ ] Kiểm tra LAST_LOGIN nếu release hỗ trợ và đối chiếu audit/session/job.
- [ ] Kiểm tra system privilege và quyền ANY.
- [ ] Lần theo role lồng nhau và quyền cấp tiếp.
- [ ] Kiểm tra object privilege và column privilege.
- [ ] Xuất system, object và column grants có grantee PUBLIC.
- [ ] Kiểm tra PUBLIC synonym và PUBLIC database link.
- [ ] Phân biệt grant của ứng dụng với grant Oracle-managed.
- [ ] Đánh giá account không còn cần đăng nhập; khóa theo giai đoạn.
- [ ] Thử thay PUBLIC bằng role chuyên biệt nếu phù hợp.
- [ ] Kiểm tra Unified Audit policy và audit trail.
- [ ] Kiểm thử ứng dụng, batch, job, failover và nghiệp vụ định kỳ.
- [ ] Lưu bằng chứng, phê duyệt, ngoại lệ và ngày review tiếp theo.

## 23. Kết luận

Rà soát quyền định kỳ giúp database không tích lũy tài khoản bỏ quên, privilege rộng và đường truy cập không còn lý do tồn tại. Hãy kiểm tra user, role lồng nhau, system privilege, object privilege, column privilege, quyền cấp tiếp và session thực tế. Với tài khoản không hoạt động, kết hợp LAST_LOGIN khi có, audit, session, job, secret và xác nhận owner; khóa account trước khi cân nhắc drop.

PUBLIC cần được xem xét riêng vì privilege cấp cho PUBLIC có thể áp dụng cho mọi user. Hãy kiểm tra DBA_SYS_PRIVS, DBA_TAB_PRIVS và DBA_COL_PRIVS với grantee PUBLIC; đồng thời phân biệt PUBLIC synonym với quyền truy cập và kiểm tra PUBLIC database link. Không revoke hàng loạt các grant do Oracle quản lý nếu chưa xác định dependency. Trong môi trường Multitenant, phải phân biệt common và local grant theo từng container.

Một quy trình bền vững cần có inventory, owner, phê duyệt, audit, thử nghiệm, thay đổi có kiểm soát và bằng chứng sau triển khai. Khi đó, quyền database luôn phản ánh nhu cầu thực tế của ứng dụng và người vận hành.
