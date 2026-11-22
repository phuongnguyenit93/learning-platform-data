# Database link, fixed/current user và phạm vi quyền truy cập trong Oracle

## 1. Database link dùng để làm gì?

Một hệ thống Oracle có thể tách dữ liệu thành nhiều database: database vận hành, database báo cáo, database kho dữ liệu hoặc database của một đơn vị khác. Khi ứng dụng cần truy vấn dữ liệu ở database khác, Oracle cung cấp **database link** để SQL tại database hiện tại tham chiếu đối tượng từ xa.

Database link là một schema object ở database cục bộ, lưu thông tin cần thiết để kết nối tới database từ xa. Sau khi tạo link, SQL có thể dùng cú pháp:

~~~sql
SELECT employee_id, first_name, last_name
FROM hr.employees@hr_link;
~~~

Trong ví dụ:

- `HR.EMPLOYEES` là bảng ở database từ xa.
- `HR_LINK` là database link được tạo ở database cục bộ.
- Database cục bộ mở kết nối tới database đích bằng thông tin kết nối và danh tính được cấu hình trong link.

Database link thường được dùng để truy vấn dữ liệu từ nhiều database trong một câu SQL, đồng bộ dữ liệu, chạy DML lên bảng từ xa, xây dựng view/synonym cục bộ hoặc kết hợp dữ liệu nghiệp vụ và dữ liệu tham chiếu ở các database khác nhau.

Điểm cần hiểu rõ là database link có hai khía cạnh độc lập:

1. **Phạm vi nhìn thấy link:** private hay public.
2. **Danh tính dùng để đăng nhập database từ xa:** connected user, fixed user hay current user.

Phạm vi nhìn thấy link không tự quyết định quyền trên bảng từ xa. Quyền truy cập dữ liệu từ xa được kiểm tra theo danh tính mà link dùng để kết nối.

> Bài học dùng Oracle Database 19c. Các tên database, user và bảng bên dưới là ví dụ. Chỉ tạo link và cấp quyền trong môi trường lab hoặc theo quy trình quản trị của hệ thống.

## 2. Cấu trúc tên đối tượng qua database link

Một đối tượng từ xa thường được tham chiếu theo dạng:

~~~sql
schema_name.object_name@database_link_name
~~~

Ví dụ:

~~~sql
SELECT *
FROM hr.employees@hr_link;
~~~

Nếu đối tượng nằm trong schema của remote user và tên bảng không cần chỉ rõ schema, có thể dùng:

~~~sql
SELECT *
FROM employees@hr_link;
~~~

Tên schema trước dấu chấm là schema **ở database từ xa**, không phải schema hiện tại ở database cục bộ.

Database link không phải một bảng hoặc schema ở remote database. Nó là đối tượng kết nối được định nghĩa ở local database; phần sau dấu @ chỉ định đường kết nối để Oracle tìm đối tượng ở phía remote.

### 2.1. Kiểm tra kết nối

Sau khi tạo link, thử truy vấn DUAL ở remote:

~~~sql
SELECT *
FROM dual@hr_link;
~~~

Có thể kiểm tra danh tính đăng nhập ở remote:

~~~sql
SELECT USER AS remote_user
FROM dual@hr_link;
~~~

Hoặc:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS remote_session_user
FROM dual@hr_link;
~~~

Kết quả cho biết user của remote session. Đây là cách nhanh để xác nhận link đang sử dụng đúng danh tính mong muốn.

### 2.2. Dùng database link trong DML

Database link không chỉ dùng cho SELECT. Ví dụ:

~~~sql
INSERT INTO hr.remote_audit@hr_link
       (event_id, event_text, created_at)
VALUES (1001, 'LOCAL IMPORT', SYSTIMESTAMP);

UPDATE hr.employees@hr_link
SET    salary = salary * 1.05
WHERE  employee_id = 100;

DELETE FROM hr.expired_sessions@hr_link
WHERE  expires_at < SYSDATE;
~~~

Remote account phải có quyền INSERT, UPDATE hoặc DELETE tương ứng trên đối tượng từ xa. DML qua database link còn liên quan đến transaction phân tán, được trình bày ở phần sau.

## 3. Hai chiều phân loại: private/public và connected/fixed/current

Đây là hai khái niệm khác nhau, không nên gộp thành một.

### 3.1. Phạm vi sử dụng link

| Loại link | Ai có thể tham chiếu? | Ý nghĩa |
| --- | --- | --- |
| Private database link | Schema owner tạo link | Link chỉ thuộc owner schema |
| Public database link | Các user trong local database | Link được công bố ở phạm vi database cục bộ |

### 3.2. Danh tính đăng nhập remote

| Loại xác thực | Cú pháp | User remote được sử dụng |
| --- | --- | --- |
| Connected user | Không có CONNECT TO | User đang kết nối vào local database |
| Fixed user | CONNECT TO user IDENTIFIED BY password | Một remote user cố định được khai báo trong link |
| Current user | CONNECT TO CURRENT_USER | Current user theo ngữ cảnh thực thi, với điều kiện xác thực global user của Oracle |

Ví dụ có thể tạo private fixed-user link, public fixed-user link hoặc private current-user link. Private/public quyết định ai dùng được đối tượng link; connected/fixed/current quyết định remote session đăng nhập bằng danh tính nào.

~~~text
LOCAL DATABASE
  |
  +-- Private link: schema owner sử dụng
  |
  +-- Public link: các local user có thể tham chiếu
           |
           +-- Connected user: danh tính user đang kết nối local
           +-- Fixed user: một remote account đã khai báo
           +-- Current user: current global user theo ngữ cảnh
                    |
                    v
              REMOTE DATABASE
                    |
              Kiểm tra quyền remote
                    |
              Schema / object / DML
~~~

## 4. Connected user database link

### 4.1. Khái niệm

Connected user database link không khai báo user/password trong mệnh đề CONNECT TO. Oracle sử dụng thông tin xác thực của user đang kết nối vào local database để mở session ở remote database.

Điều đó có nghĩa remote database phải nhận diện được cùng username và password (hoặc cơ chế xác thực tương ứng) cho user đó. Nếu local user APP_USER kết nối qua link, remote database cũng cần tài khoản APP_USER có thể đăng nhập và được cấp quyền cần thiết.

### 4.2. Tạo connected user link

~~~sql
CREATE DATABASE LINK hr_connected_link
USING 'HRPDB';
~~~

Không có CONNECT TO, nên link dùng connected user. HRPDB là connect identifier được database server cục bộ phân giải tới dịch vụ Oracle từ xa.

### 4.3. Sử dụng

~~~sql
SELECT employee_id, first_name, last_name
FROM hr.employees@hr_connected_link
WHERE department_id = 50;
~~~

Remote database xác thực bằng danh tính connected user. Remote user đó cần có thể đăng nhập database từ xa, có quyền SELECT trên HR.EMPLOYEES và có các quyền DML khác nếu câu SQL thực hiện INSERT, UPDATE hoặc DELETE.

### 4.4. Khi nào dùng?

Connected user link phù hợp khi các user có tài khoản tương ứng ở cả local và remote database, muốn mỗi người giữ danh tính riêng khi truy cập remote, hoặc chính sách bảo mật yêu cầu quyền remote phụ thuộc user đang đăng nhập local.

### 4.5. Hạn chế vận hành

Nếu user local tồn tại nhưng remote không có cùng tài khoản hoặc thông tin xác thực không khớp, kết nối có thể thất bại. Việc quản lý password và vòng đời tài khoản ở hai database cũng cần đồng bộ.

## 5. Fixed user database link

### 5.1. Khái niệm

Fixed user database link khai báo một remote username/password cụ thể. Bất kỳ local session nào được phép sử dụng link đó đều kết nối remote bằng danh tính cố định này.

Ví dụ:

~~~sql
CREATE DATABASE LINK hr_report_link
CONNECT TO report_reader IDENTIFIED BY "ReplaceWithSecret"
USING 'HRPDB';
~~~

Trong ví dụ, mọi lần sử dụng HR_REPORT_LINK đều đăng nhập remote với user REPORT_READER, bất kể local user nào đang chạy câu SQL (nếu local user đó có quyền dùng link).

### 5.2. Truy vấn qua fixed user link

~~~sql
SELECT employee_id, first_name, salary
FROM hr.employees@hr_report_link
WHERE department_id = 50;
~~~

Remote database kiểm tra quyền của REPORT_READER. Nếu remote user chỉ có SELECT trên HR.EMPLOYEES, câu truy vấn đọc được bảng đó nhưng không thể UPDATE hoặc DELETE bảng.

### 5.3. Cấp quyền ở remote database

Ví dụ chạy tại remote database bằng DBA hoặc owner phù hợp:

~~~sql
CREATE USER report_reader IDENTIFIED BY "ReplaceWithSecret";
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON hr.employees TO report_reader;
~~~

Nếu user đã tồn tại, không tạo lại; chỉ cấp đúng quyền cần thiết:

~~~sql
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON hr.employees TO report_reader;
~~~

Nếu link cần cập nhật dữ liệu, remote account phải được cấp quyền DML tương ứng:

~~~sql
GRANT INSERT, UPDATE, DELETE
ON hr.employee_notes
TO report_writer;
~~~

Không cấp DBA, SELECT ANY TABLE hoặc quyền rộng chỉ để làm một query hoạt động. Dùng remote account chuyên dụng với quyền tối thiểu.

### 5.4. Fixed user link có thể dùng chung danh tính remote

Nếu một fixed-user link được tạo ở dạng private, chỉ schema owner có thể tham chiếu link đó. Nếu link là public, nhiều local user có thể tham chiếu cùng link và tất cả cùng sử dụng remote account cố định.

Đây là khác biệt bảo mật quan trọng:

- Private fixed-user link giới hạn người sử dụng theo schema owner.
- Public fixed-user link mở khả năng sử dụng remote account đó cho nhiều local user.
- Quyền trên remote object vẫn là quyền của fixed remote account, không tự thu hẹp theo local user.

Do đó, public fixed-user link có thể làm nhiều local user chia sẻ một quyền remote rộng hơn mức cần thiết. Chỉ công bố public khi đã đánh giá rõ đối tượng sử dụng và quyền của remote account.

## 6. Current user database link

### 6.1. Khái niệm

Current user database link được tạo bằng:

~~~sql
CREATE DATABASE LINK hr_current_link
CONNECT TO CURRENT_USER
USING 'HRPDB';
~~~

Khi link được sử dụng, Oracle dùng current user trong ngữ cảnh thực thi để xác định danh tính kết nối remote. Khác với fixed user link, link không chỉ định một remote username/password cố định.

Current user database link dành cho mô hình xác thực global user của Oracle. Current user phải là global user được xác thực bằng cơ chế enterprise authentication phù hợp (chẳng hạn directory-based authentication, SSL hoặc Kerberos theo cấu hình hệ thống). Đây không phải cách biến một local database username bất kỳ thành tài khoản remote tự động.

### 6.2. Current user không đồng nghĩa CURRENT_SCHEMA

Oracle có các khái niệm khác nhau:

- SESSION_USER: user đã đăng nhập và tạo database session.
- CURRENT_USER: user có danh tính/privilege context hiện hành; trong PL/SQL có thể thay đổi theo quyền thực thi của program unit.
- CURRENT_SCHEMA: schema được dùng để phân giải tên đối tượng không ghi rõ schema.

ALTER SESSION SET CURRENT_SCHEMA = ... chỉ thay đổi schema mặc định để tìm object không qualify; nó không đăng nhập lại database và không biến user đó thành danh tính xác thực remote.

Vì vậy, current-user database link không nên được hiểu là “lấy schema đang chọn rồi kết nối remote bằng schema đó”.

### 6.3. Current user trong PL/SQL definer-rights và invoker-rights

Quyền thực thi PL/SQL ảnh hưởng current user:

- Program unit mặc định dùng **definer's rights** (AUTHID DEFINER): quyền được đánh giá theo owner/definer của program unit.
- Program unit khai báo **invoker's rights** (AUTHID CURRENT_USER): quyền được đánh giá theo invoker đang gọi program unit.

Ví dụ:

~~~sql
CREATE OR REPLACE PROCEDURE list_remote_employees
AUTHID CURRENT_USER
AS
    l_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM hr.employees@hr_current_link;

    DBMS_OUTPUT.PUT_LINE('Remote employee count: ' || l_count);
END;
/
~~~

Trong invoker-rights routine, current user context của người gọi được dùng theo quy tắc Oracle. Với definer-rights routine, current user context là definer. Khi thiết kế current-user link trong stored code, phải kiểm tra AUTHID, global identity và quyền ở cả hai database.

### 6.4. Khi nào dùng?

Current user link phù hợp khi hệ thống có enterprise/global users được xác thực tập trung, muốn danh tính remote theo người đang gọi thay vì một fixed account chung, cần audit trail remote gắn với người dùng thực và kiến trúc đã thiết lập global authentication cùng mapping user ở các database liên quan.

Nếu hệ thống chỉ dùng local database accounts thông thường, fixed-user hoặc connected-user link có thể phù hợp hơn.

## 7. So sánh connected, fixed và current user

| Tiêu chí | Connected user | Fixed user | Current user |
| --- | --- | --- | --- |
| Khai báo CONNECT TO | Bỏ qua | Username/password cố định | CURRENT_USER |
| Remote identity | User đang kết nối local | Một remote account cấu hình trong link | Current global user theo execution context |
| Remote account cần tồn tại | Cùng user cần đăng nhập được ở remote | Account cố định phải tồn tại ở remote | Global user phải được remote nhận diện |
| Password trong link | Không khai báo | Có thông tin xác thực của fixed user | Không khai báo fixed password |
| Phù hợp | Tài khoản đồng nhất ở hai DB | Ứng dụng dùng account dịch vụ có quyền giới hạn | Enterprise/global identity và quyền theo invoker |
| Rủi ro chính | Quản lý tài khoản/xác thực ở hai DB | Nhiều local user có thể chia sẻ quyền remote nếu link public | Phụ thuộc cấu hình global authentication và execution context |

Không có loại link nào tự động an toàn trong mọi tình huống. Hãy chọn theo mô hình danh tính, yêu cầu audit, cách cấp quyền và phạm vi sử dụng.

## 8. Private và public database link

### 8.1. Private database link

Tạo private link:

~~~sql
CREATE DATABASE LINK hr_private_link
CONNECT TO report_reader IDENTIFIED BY "ReplaceWithSecret"
USING 'HRPDB';
~~~

Link thuộc schema của user tạo nó. User khác không thể tham chiếu trực tiếp private link đó chỉ vì họ có quyền SELECT trên bảng remote.

Private link phù hợp khi một schema ứng dụng cần kết nối tới remote database bằng một identity được quản lý riêng.

### 8.2. Public database link

Tạo public link cần system privilege CREATE PUBLIC DATABASE LINK:

~~~sql
CREATE PUBLIC DATABASE LINK hr_public_link
CONNECT TO report_reader IDENTIFIED BY "ReplaceWithSecret"
USING 'HRPDB';
~~~

Public link được công bố ở phạm vi local database. Các local user có thể tham chiếu tên link mà không cần sở hữu private link.

Public không có nghĩa là remote database mở cho mọi người. Remote database vẫn xác thực theo connected/fixed/current user và kiểm tra quyền của danh tính remote đó.

### 8.3. Phạm vi quyền khi kết hợp public và fixed user

Giả sử HR_PUBLIC_LINK là public fixed-user link kết nối bằng REPORT_READER.

~~~sql
SELECT *
FROM hr.employees@hr_public_link;
~~~

Local user A và local user B có thể cùng chạy câu lệnh. Remote database nhìn cả hai như REPORT_READER, vì link sử dụng fixed user.

Điều đó có nghĩa:

- Remote audit có thể ghi nhận cùng một remote username.
- Remote privilege của REPORT_READER được dùng cho cả hai local user.
- Quyền local trên link không phải bộ lọc quyền trên remote object.
- Nếu REPORT_READER có quyền rộng, nhiều local user có thể khai thác quyền đó thông qua public link.

Với yêu cầu phân quyền theo từng người, cân nhắc connected/current user hoặc các private links được giới hạn trong schema phù hợp.

### 8.4. Có thể GRANT private database link cho user khác không?

Private database link không phải object privilege có thể GRANT giống bảng hoặc view. Nếu user khác cần dùng một kết nối:

- Tạo private link trong schema của user đó.
- Hoặc DBA tạo public link sau khi đánh giá phạm vi và remote identity.
- Hoặc xây dựng API/view/procedure có kiểm soát thay vì để nhiều schema truy cập trực tiếp remote account.

Không cấp quyền rộng chỉ để tránh việc phải quản lý link theo schema.

## 9. Quyền cần có ở local và remote database

Database link liên quan tới hai hệ thống quyền riêng biệt.

### 9.1. Quyền tạo link ở local database

| Mục tiêu | System privilege |
| --- | --- |
| Tạo private database link | CREATE DATABASE LINK |
| Tạo public database link | CREATE PUBLIC DATABASE LINK |
| Xóa public database link | DROP PUBLIC DATABASE LINK |

User thông thường có thể tạo private link nếu được cấp CREATE DATABASE LINK. Tạo public link cần quyền riêng vì link có phạm vi ảnh hưởng rộng hơn.

Ví dụ DBA cấp quyền tạo private link:

~~~sql
GRANT CREATE DATABASE LINK TO app_owner;
~~~

Chỉ cấp quyền tạo public link cho vai trò quản trị phù hợp:

~~~sql
GRANT CREATE PUBLIC DATABASE LINK TO db_admin_role;
~~~

### 9.2. Quyền đăng nhập ở remote database

Remote user cần quyền tạo session:

~~~sql
GRANT CREATE SESSION TO report_reader;
~~~

Sau đó cấp object privileges tối thiểu:

~~~sql
GRANT SELECT ON hr.employees TO report_reader;
GRANT SELECT ON hr.departments TO report_reader;
~~~

Nếu cần DML:

~~~sql
GRANT INSERT, UPDATE ON hr.employee_notes TO report_writer;
~~~

Remote account không cần có quyền DBA. Một remote account chỉ đọc báo cáo nên chỉ nhận CREATE SESSION và SELECT trên các object cần thiết.

### 9.3. Local user không tự nhận quyền remote

Giả sử local user APP_USER có quyền SELECT trên một view local. Nếu view truy cập bảng remote bằng fixed-user link, quyền remote vẫn được đánh giá theo remote identity của link.

Ngược lại, việc local user có quyền SELECT trên bảng remote ở local database không tự động cấp quyền đó cho remote account. Hai hệ thống quyền phải được cấp riêng.

### 9.4. Quyền trong stored program units

Stored procedure, function và package có thể chạy theo definer's rights hoặc invoker's rights. Quyền truy cập local object và remote object cần được thiết kế cùng AUTHID và danh tính link.

Đối với object được gọi trong stored code, nên cấp trực tiếp các object privilege cần thiết cho owner/invoker phù hợp thay vì dựa vào role một cách không kiểm soát. Kiểm tra quy tắc privilege của Oracle cho loại program unit cụ thể trước khi triển khai.

## 10. Tạo database link: quy trình từ local tới remote

### 10.1. Chuẩn bị connect identifier

Mệnh đề USING chỉ định connect string hoặc net service name để local database server tìm remote service.

Ví dụ:

~~~sql
USING 'HRPDB'
~~~

HRPDB phải được cấu hình và phân giải trên máy chủ database cục bộ (ví dụ qua Oracle Net naming/TNS configuration), không chỉ có trong máy client chạy SQL Developer.

Nếu DBA cung cấp connect descriptor đầy đủ, có thể dùng chuỗi kết nối phù hợp thay cho alias:

~~~sql
USING '(DESCRIPTION=
  (ADDRESS=(PROTOCOL=TCP)(HOST=dbhost.example.com)(PORT=1521))
  (CONNECT_DATA=(SERVICE_NAME=hrpdb.example.com))
)'
~~~

Không đưa mật khẩu vào connect descriptor. Thông tin xác thực thuộc mệnh đề CONNECT TO hoặc cơ chế xác thực được cấu hình.

### 10.2. Tạo private fixed-user link

Chạy ở local database bằng schema owner có CREATE DATABASE LINK:

~~~sql
CREATE DATABASE LINK hr_report_link
CONNECT TO report_reader IDENTIFIED BY "ReplaceWithSecret"
USING 'HRPDB';
~~~

Trong môi trường thật, dùng secret do tổ chức quản lý và quy trình triển khai bảo mật. Không lưu mật khẩu thật trong source code, script chia sẻ, ticket hoặc tài liệu học tập.

### 10.3. Kiểm tra

~~~sql
SELECT USER AS remote_user
FROM dual@hr_report_link;

SELECT employee_id, first_name
FROM hr.employees@hr_report_link
WHERE ROWNUM <= 5;
~~~

Nếu kiểm tra danh tính trả REPORT_READER và query remote thành công, link đã kết nối bằng remote identity dự kiến.

### 10.4. Tạo synonym cục bộ (tùy chọn)

Để tránh viết tên link dài ở mọi câu query:

~~~sql
CREATE SYNONYM remote_employees
FOR hr.employees@hr_report_link;
~~~

Sau đó có thể query:

~~~sql
SELECT employee_id, first_name
FROM remote_employees;
~~~

Synonym chỉ là bí danh phân giải tên đối tượng. Nó không thay đổi remote identity và không cấp thêm quyền truy cập.

## 11. Quản lý và kiểm tra database link

Oracle cung cấp các data dictionary views:

| View | Phạm vi |
| --- | --- |
| USER_DB_LINKS | Database links thuộc schema hiện tại |
| ALL_DB_LINKS | Database links mà user hiện tại có thể truy cập theo view |
| DBA_DB_LINKS | Toàn bộ database links trong database; cần quyền phù hợp |

Ví dụ:

~~~sql
SELECT db_link,
       username,
       host,
       created
FROM user_db_links
ORDER BY db_link;
~~~

DBA có thể xem:

~~~sql
SELECT owner,
       db_link,
       username,
       host,
       created
FROM dba_db_links
ORDER BY owner, db_link;
~~~

Các view này cho biết tên link, remote username và thông tin host/connection tương ứng theo quyền hiển thị. Không coi chúng là nơi để lấy hoặc khôi phục mật khẩu.

### 11.1. Xem global name của database

~~~sql
SELECT *
FROM global_name;
~~~

Nếu tham số GLOBAL_NAMES được bật, tên database link phải phù hợp với global database name của database từ xa theo quy tắc Oracle. DBA có thể kiểm tra cấu hình:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'global_names';
~~~

Truy cập V$PARAMETER cần quyền phù hợp. Không thay đổi GLOBAL_NAMES chỉ để làm một link sai tên hoạt động; hãy xác nhận naming convention của hệ thống.

### 11.2. Xóa private link

Owner của private link có thể xóa:

~~~sql
DROP DATABASE LINK hr_report_link;
~~~

### 11.3. Xóa public link

DBA hoặc user có quyền tương ứng có thể xóa public link:

~~~sql
DROP PUBLIC DATABASE LINK hr_public_link;
~~~

Xóa database link không xóa bảng hoặc dữ liệu ở remote database. Nó chỉ xóa đối tượng kết nối ở local database.

### 11.4. Thay đổi password remote

Nếu remote account đổi password, fixed-user database link đang lưu credential cũ có thể không kết nối được nữa. Cần cập nhật hoặc tạo lại link theo quy trình được phép, đồng thời kiểm tra các ứng dụng và stored objects đang phụ thuộc link.

Không gửi password mới qua log hoặc output terminal. Dùng secret management và quy trình rotate credential của tổ chức.

## 12. Phân quyền và ranh giới bảo mật

Database link là một ranh giới bảo mật giữa hai database. Việc cấp quyền cần xét cả local user và remote identity.

### 12.1. Public link không đồng nghĩa public remote data

Một public database link chỉ làm cho tên link có thể được nhiều local user tham chiếu. Remote database vẫn kiểm tra remote username và privilege.

Tuy nhiên, public fixed-user link có thể khiến nhiều local user cùng sử dụng một remote account. Nếu account đó có SELECT trên dữ liệu nhạy cảm, mọi local user dùng được link có thể có đường truy cập tới dữ liệu đó.

### 12.2. Dùng remote account có quyền tối thiểu

Một tài khoản báo cáo chỉ cần đọc hai bảng:

~~~sql
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON hr.employees TO report_reader;
GRANT SELECT ON hr.departments TO report_reader;
~~~

Không cấp thêm quyền trên các bảng lương, thông tin định danh hoặc dữ liệu khác nếu báo cáo không cần.

### 12.3. Không dùng tài khoản quản trị làm fixed user

Không cấu hình link dùng SYS, SYSTEM hoặc tài khoản DBA có quyền rộng. Nếu link bị sử dụng sai, phạm vi ảnh hưởng sẽ rất lớn.

### 12.4. Audit cần phân biệt local user và remote user

Với fixed-user link, remote audit thường thấy fixed account. Nếu cần biết local user nào khởi tạo thao tác, cần bổ sung audit ở local hoặc truyền application context/tag được kiểm soát; không giả định remote database tự nhận diện được local user.

Connected/current user links có thể giữ danh tính cá nhân tốt hơn, nhưng chỉ khi cơ chế xác thực và mapping user được thiết kế đúng.

### 12.5. Bảo vệ đường truyền và thông tin xác thực

- Dùng Oracle Net encryption hoặc TLS theo chính sách hệ thống.
- Giới hạn host/service mà link được phép kết nối.
- Quản lý password và rotation bằng quy trình bảo mật.
- Không để người dùng không tin cậy có quyền tạo public link.
- Theo dõi các database link được tạo, thay đổi và xóa.
- Rà soát remote grants định kỳ.

## 13. Transaction phân tán khi DML qua database link

Một câu SELECT từ remote database là distributed query. Khi transaction cập nhật dữ liệu ở nhiều database, Oracle phải phối hợp transaction phân tán.

Ví dụ:

~~~sql
UPDATE local_orders
SET status = 'SENT'
WHERE order_id = 1001;

INSERT INTO remote_audit@hr_link
       (event_id, event_text)
VALUES (1001, 'ORDER SENT');

COMMIT;
~~~

Transaction trên tác động đến cả local database và remote database. Oracle dùng cơ chế **two-phase commit (2PC)** để phối hợp commit:

1. **Prepare phase:** coordinator yêu cầu các participant chuẩn bị commit và bảo đảm có thể hoàn tất.
2. **Commit phase:** khi các participant đã sẵn sàng, coordinator ra quyết định commit.

Mục tiêu là tránh tình trạng local đã commit nhưng remote lại rollback (hoặc ngược lại) trong một distributed transaction được quản lý đúng.

### 13.1. COMMIT và ROLLBACK

Nếu transaction có DML ở local và remote:

- COMMIT yêu cầu transaction phân tán hoàn tất commit theo protocol.
- ROLLBACK hủy các thay đổi chưa commit trong transaction phân tán.
- Không tự ý commit một phần nếu nghiệp vụ yêu cầu local và remote phải cùng thành công.

### 13.2. In-doubt transaction

Nếu database hoặc network gặp sự cố trong giai đoạn phối hợp commit, có thể xuất hiện distributed transaction ở trạng thái in-doubt. DBA có thể điều tra bằng các view như:

~~~sql
SELECT *
FROM dba_2pc_pending;
~~~

và:

~~~sql
SELECT *
FROM dba_2pc_neighbors;
~~~

Các view quản trị này cần quyền phù hợp. Không tự xóa hoặc force commit/rollback một giao dịch in-doubt khi chưa xác định quyết định của coordinator và các participant; DBA phải xử lý theo quy trình recovery.

### 13.3. Thiết kế ứng dụng khi remote database tạm mất kết nối

Một thao tác qua database link có thể thất bại do remote database dừng, network gián đoạn, listener/service không sẵn sàng, credential hết hạn hoặc bị đổi, remote account bị khóa, hay transaction remote đang chờ khóa.

Ứng dụng cần xác định thao tác có thể retry an toàn hay không. Với DML, hãy thiết kế idempotency key hoặc khóa nghiệp vụ để retry không tạo bản ghi trùng.

## 14. Ví dụ kết hợp dữ liệu local và remote

Giả sử local database lưu đơn hàng, remote database lưu thông tin khách hàng. Ta cần báo cáo tổng tiền theo khách hàng:

~~~sql
SELECT c.customer_id,
       c.customer_name,
       SUM(o.order_total) AS total_amount
FROM crm.customers@crm_link c
JOIN local_orders o
  ON o.customer_id = c.customer_id
WHERE o.order_date >= DATE '2026-01-01'
GROUP BY c.customer_id, c.customer_name
ORDER BY total_amount DESC;
~~~

Query kết hợp dữ liệu từ hai database. Oracle có thể đẩy một phần xử lý sang remote database hoặc lựa chọn cách thực thi khác tùy optimizer, statistics, network và query shape. Không giả định mọi row remote đều được truyền về local trước khi lọc; cũng không giả định optimizer luôn đẩy predicate tối ưu.

Khi dữ liệu remote lớn:

- Lọc sớm ở remote nếu phù hợp.
- Chỉ chọn cột cần thiết.
- Tránh kéo toàn bộ bảng qua network.
- Kiểm tra execution plan và số lượng row truyền qua link.
- Cân nhắc materialized view hoặc ETL nếu truy vấn liên database diễn ra thường xuyên và khối lượng lớn.

### 14.1. View local trên dữ liệu remote

~~~sql
CREATE OR REPLACE VIEW v_remote_employees AS
SELECT employee_id, first_name, department_id
FROM hr.employees@hr_link;
~~~

View giúp đóng gói tên remote và câu query. Tuy nhiên, view không thay đổi remote identity của link; quyền remote vẫn được kiểm tra theo user link; quyền local để query view vẫn cần được cấp; nếu remote schema thay đổi hoặc link lỗi, view phụ thuộc link cũng có thể lỗi.

## 15. GLOBAL_NAMES và tên database link

Oracle có tham số GLOBAL_NAMES để yêu cầu tên database link khớp với global database name của remote database.

Ví dụ:

~~~sql
SELECT *
FROM global_name;
~~~

Giả sử remote global name là:

~~~text
HRPDB.EXAMPLE.COM
~~~

Khi GLOBAL_NAMES = TRUE, tên link cần phù hợp với global name này theo quy tắc naming của Oracle. Nếu link đặt tên không khớp, có thể nhận lỗi:

~~~text
ORA-02085: database link ... connects to ...
~~~

Trong hệ thống có nhiều database, DBA thường quy định cách đặt tên link để dễ xác định đích và domain. Không tắt GLOBAL_NAMES tùy tiện vì đây là một kiểm soát về naming và routing.

## 16. Những lỗi thường gặp

| Lỗi | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-12154 | Không phân giải được connect identifier trong USING | Kiểm tra Oracle Net naming trên máy chủ local database |
| ORA-12514 | Listener không biết service được yêu cầu | Kiểm tra SERVICE_NAME và listener ở remote |
| ORA-01017 | Username/password remote không đúng hoặc xác thực thất bại | Kiểm tra fixed/connected identity và trạng thái tài khoản |
| ORA-02019 | Không tìm thấy connect description cho database link | Kiểm tra link, USING và cấu hình Oracle Net |
| ORA-02085 | Tên link không phù hợp global name khi GLOBAL_NAMES bật | Kiểm tra GLOBAL_NAME và tên database link |
| ORA-00942 | Remote object không tồn tại, sai schema hoặc remote user thiếu quyền | Kiểm tra schema.object và cấp đúng object privilege |
| ORA-01031 | Thiếu quyền tạo link hoặc quyền truy cập remote/local | Kiểm tra system privilege local và privilege remote |
| ORA-02049 | Distributed transaction chờ khóa quá thời gian cho phép | Kiểm tra transaction giữ khóa ở remote và timeout |
| ORA-02068 | Lỗi từ remote database được chuyển tiếp qua database link | Xem lỗi remote tiếp theo trong stack và xử lý tại remote |
| ORA-02055 | Distributed update gặp lỗi và transaction cần rollback | ROLLBACK theo transaction boundary rồi điều tra lỗi gốc |
| Query chậm | Nhiều row truyền qua network hoặc remote plan chưa tối ưu | Lọc dữ liệu, chọn cột cần thiết, kiểm tra execution plan |
| Public link cho quá nhiều người dùng remote identity | Link public dùng fixed account có quyền rộng | Giới hạn link, thu hẹp remote grants, cân nhắc user-specific identity |
| Local user không dùng được private link của schema khác | Private link thuộc schema owner | Tạo link riêng hoặc dùng API/public link được quản trị |

## 17. Bộ thực hành tự chứa

Các bước dưới đây cần hai Oracle database độc lập hoặc hai PDB/service mà bạn có quyền quản trị. Tên LOCALDB, HRPDB, user và password chỉ là ví dụ. Không dùng tài khoản hoặc mật khẩu production.

### Bài A — Tạo remote user và cấp quyền

Ở remote database, bằng DBA hoặc user có quyền:

~~~sql
CREATE USER report_reader IDENTIFIED BY "LabOnlyPassword";
GRANT CREATE SESSION TO report_reader;
GRANT SELECT ON hr.employees TO report_reader;
~~~

Nếu user đã tồn tại, bỏ CREATE USER và chỉ cấp quyền cần thiết.

### Bài B — Tạo private fixed-user link

Ở local database, đăng nhập schema lab:

~~~sql
GRANT CREATE DATABASE LINK TO app_owner;
~~~

Sau đó bằng APP_OWNER:

~~~sql
CREATE DATABASE LINK hr_report_link
CONNECT TO report_reader IDENTIFIED BY "LabOnlyPassword"
USING 'HRPDB';
~~~

Kiểm tra:

~~~sql
SELECT USER FROM dual@hr_report_link;

SELECT COUNT(*)
FROM hr.employees@hr_report_link;
~~~

Remote user dự kiến là REPORT_READER.

### Bài C — So sánh private và public

DBA có thể tạo public fixed-user link trong môi trường lab:

~~~sql
GRANT CREATE PUBLIC DATABASE LINK TO db_admin_role;
~~~

Sau đó:

~~~sql
CREATE PUBLIC DATABASE LINK hr_public_link
CONNECT TO report_reader IDENTIFIED BY "LabOnlyPassword"
USING 'HRPDB';
~~~

Đăng nhập bằng một local user khác và thử:

~~~sql
SELECT USER
FROM dual@hr_public_link;
~~~

Quan sát rằng nhiều local user có thể tham chiếu public link và remote session vẫn dùng REPORT_READER. Xóa public link sau bài thực hành.

### Bài D — Connected user link

Tạo một user cùng tên và thông tin xác thực ở cả local và remote database, cấp CREATE SESSION ở remote và SELECT trên bảng cần đọc. Sau đó ở local user:

~~~sql
CREATE DATABASE LINK hr_connected_link
USING 'HRPDB';

SELECT USER
FROM dual@hr_connected_link;
~~~

Quan sát remote identity là connected user. Nếu user/password không khớp hoặc remote account không tồn tại, link sẽ không xác thực thành công.

### Bài E — Current user link

Chỉ thực hiện khi hệ thống lab đã cấu hình global user và enterprise authentication:

~~~sql
CREATE DATABASE LINK hr_current_link
CONNECT TO CURRENT_USER
USING 'HRPDB';

SELECT USER
FROM dual@hr_current_link;
~~~

Thử trong context PL/SQL definer-rights và invoker-rights nếu môi trường cho phép. So sánh danh tính remote theo current user context. Không thay thế bài này bằng local schema name hoặc ALTER SESSION SET CURRENT_SCHEMA.

### Bài F — Dictionary views

~~~sql
SELECT db_link, username, host, created
FROM user_db_links;
~~~

Nếu có quyền DBA:

~~~sql
SELECT owner, db_link, username, host, created
FROM dba_db_links
ORDER BY owner, db_link;
~~~

Xác định link nào private, link nào public và remote username nào được cấu hình.

### Bài G — DML và transaction phân tán

Trong schema lab, tạo bảng remote audit và cấp quyền INSERT cho remote account. Sau đó thử một transaction có cả DML local và remote:

~~~sql
INSERT INTO local_audit_lab (event_id, event_text)
VALUES (9001, 'LOCAL');

INSERT INTO hr.remote_audit_lab@hr_report_link
       (event_id, event_text)
VALUES (9001, 'REMOTE');

COMMIT;
~~~

Đọc lại cả hai database để đối soát. Sau đó thử ROLLBACK thay cho COMMIT trong một transaction khác và quan sát cả hai phía.

## 18. Checklist thiết kế database link

1. **Remote database/service là gì?** Xác nhận host, port, service name và connect identifier.
2. **Link thuộc schema nào?** Dùng private theo mặc định nếu chỉ một schema cần truy cập.
3. **Có thật sự cần public không?** Public mở khả năng tham chiếu cho nhiều local user.
4. **Remote identity nào phù hợp?** Connected, fixed hay current user.
5. **Remote user có quyền tối thiểu chưa?** Cấp CREATE SESSION và object privileges cần thiết.
6. **Fixed account có bị chia sẻ ngoài ý muốn không?** Đặc biệt kiểm tra public fixed-user link.
7. **Current user có phải global user được xác thực phù hợp không?** Không nhầm với CURRENT_SCHEMA.
8. **Stored code dùng AUTHID nào?** Kiểm tra current user/definer/invoker context.
9. **Có audit được người gọi không?** Fixed user có thể làm remote audit chỉ thấy một account chung.
10. **Có DML trên nhiều database không?** Hiểu transaction phân tán và two-phase commit.
11. **Có cơ chế retry/idempotency không?** Tránh ghi trùng khi network hoặc remote database lỗi.
12. **Có cần synonym/view không?** Chúng giúp đóng gói tên nhưng không cấp thêm quyền.
13. **GLOBAL_NAMES có bật không?** Đặt tên link đúng convention.
14. **Credential được quản lý ra sao?** Không để password trong code hoặc log; có quy trình rotation.
15. **Đã kiểm tra dictionary views và kết nối thực tế chưa?** Test USER@link và object query trước khi đưa vào ứng dụng.

## 19. Câu hỏi tự kiểm tra

**Câu 1.** Database link là object được tạo ở database nào?

**Câu 2.** Cú pháp tham chiếu bảng remote là gì?

**Câu 3.** Private và public database link khác nhau ở khía cạnh nào?

**Câu 4.** Connected user link lấy danh tính remote từ đâu?

**Câu 5.** Fixed user link kết nối bằng user nào?

**Câu 6.** Current user link có dùng CURRENT_SCHEMA để xác định remote identity không?

**Câu 7.** Current user database link yêu cầu mô hình xác thực nào?

**Câu 8.** Nếu public link là fixed-user link, nhiều local user có thể cùng dùng remote account đó không?

**Câu 9.** Public link có tự cấp quyền SELECT trên remote table cho mọi local user không?

**Câu 10.** Quyền CREATE DATABASE LINK được cấp ở local hay remote database?

**Câu 11.** Remote user cần quyền nào để đăng nhập và đọc một bảng?

**Câu 12.** USER_DB_LINKS và DBA_DB_LINKS khác nhau thế nào?

**Câu 13.** Database link có hỗ trợ INSERT/UPDATE/DELETE remote không?

**Câu 14.** Vì sao DML local và remote trong cùng transaction liên quan two-phase commit?

**Câu 15.** Synonym trên bảng remote có thay đổi remote identity không?

<details>
<summary>Gợi ý đáp án</summary>

1. Local database; link được lưu trong schema hoặc phạm vi public của local database.
2. SCHEMA_NAME.OBJECT_NAME@DATABASE_LINK_NAME.
3. Private chỉ thuộc schema owner; public có thể được nhiều local user tham chiếu.
4. User đang kết nối vào local database; remote cần tài khoản/xác thực tương ứng.
5. Remote username được khai báo cố định trong CONNECT TO.
6. Không. CURRENT_SCHEMA chỉ đổi schema mặc định để phân giải tên object local.
7. Global user/enterprise authentication được Oracle hỗ trợ và cấu hình phù hợp.
8. Có. Nếu họ được dùng public link, remote session đều dùng fixed remote identity đó.
9. Không. Remote database vẫn kiểm tra privilege của remote account; public chỉ mở phạm vi sử dụng link.
10. Local database.
11. CREATE SESSION và object privilege như SELECT trên bảng cần đọc.
12. USER_DB_LINKS hiển thị link thuộc schema hiện tại; DBA_DB_LINKS hiển thị toàn database với quyền DBA phù hợp.
13. Có, nếu remote identity có quyền DML và transaction được xử lý đúng.
14. Vì commit phải phối hợp các participant ở nhiều database để giữ tính nhất quán phân tán.
15. Không. Synonym chỉ là bí danh tên object.

</details>

## 20. Tài liệu Oracle chính thức

1. [Oracle Database 19c SQL Language Reference — CREATE DATABASE LINK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-DATABASE-LINK.html): cú pháp tạo private/public link, connected/fixed/current user và connect string.
2. [Oracle Database 19c SQL Language Reference — DROP DATABASE LINK](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DROP-DATABASE-LINK.html): xóa private và public database link.
3. [Oracle Database 19c Administrator's Guide — Managing a Distributed Database](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-a-distributed-database.html): database link, distributed queries, distributed transactions và cấu hình mạng.
4. [Oracle Database 19c Concepts — Distributed Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/distributed-database-concepts.html): kiến trúc và mô hình truy cập database phân tán.
5. [Oracle Database 19c SQL Language Reference — CREATE SYNONYM](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-SYNONYM.html): synonym và tham chiếu object qua database link.
6. [Oracle Database 19c Reference — USER_DB_LINKS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_DB_LINKS.html): dictionary view của database link thuộc user.
7. [Oracle Database 19c Reference — DBA_DB_LINKS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_DB_LINKS.html): dictionary view quản trị database links.
8. [Oracle Database 19c PL/SQL Language Reference — Invoker's Rights and Definer's Rights](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights-authid-property.html): AUTHID, current user và privilege context của stored program units.

**Nguyên tắc cần nhớ:** private/public trả lời câu hỏi ai được tham chiếu database link; connected/fixed/current user trả lời câu hỏi remote database nhìn thấy danh tính nào. Quyền truy cập bảng từ xa được kiểm tra theo remote identity, không tự phát sinh từ việc local user nhìn thấy link. Dùng private link và remote account quyền tối thiểu làm lựa chọn cơ bản; chỉ dùng public fixed-user link khi đã đánh giá tác động chia sẻ credential và privilege. Current-user link dành cho global user authentication và cần hiểu đúng current user trong PL/SQL, không nhầm với CURRENT_SCHEMA. Khi DML qua nhiều database, quản lý transaction phân tán và retry như một phần của thiết kế.
