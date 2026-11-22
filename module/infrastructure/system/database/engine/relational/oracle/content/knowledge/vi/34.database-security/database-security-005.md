# Profile, password policy và giới hạn tài nguyên phiên

Oracle Database dùng **profile** để gom các quy tắc áp dụng cho database user. Một profile có thể chứa hai nhóm thiết lập: chính sách mật khẩu và giới hạn tài nguyên. Nhờ đó DBA có thể áp dụng cùng một bộ quy tắc cho một nhóm tài khoản như người dùng ứng dụng, tài khoản batch, tài khoản báo cáo hoặc tài khoản quản trị.

Nhóm chính sách mật khẩu kiểm soát số lần đăng nhập sai, thời hạn mật khẩu, thời gian khóa tài khoản, lịch sử mật khẩu, độ phức tạp mật khẩu và thời gian rollover khi đổi mật khẩu cho ứng dụng. Nhóm giới hạn tài nguyên kiểm soát số session đồng thời, CPU, logical reads, thời gian kết nối, thời gian idle và một số tài nguyên khác.

Hai nhóm này có cơ chế thực thi khác nhau. **Password limits luôn được Oracle áp dụng. Resource limits trong profile chỉ được áp dụng khi RESOURCE_LIMIT được bật.** Ngoài ra, Oracle khuyến nghị dùng Database Resource Manager khi cần quản lý tài nguyên linh hoạt hơn. Vì vậy, profile là công cụ quan trọng cho quản trị tài khoản, nhưng không phải giải pháp duy nhất cho workload management.

Bài học thuộc nhóm **Bảo mật** của Database Engine Relational Oracle. Nội dung tập trung vào mô hình profile, password policy, resource limits theo session/call, RESOURCE_LIMIT, Database Resource Manager, quản lý tài khoản ứng dụng, giám sát và quy trình triển khai an toàn.

Sau bài này, bạn có thể:

- Giải thích profile và cách gán profile cho user.
- Phân biệt password parameters với resource parameters.
- Dùng CREATE PROFILE, ALTER PROFILE và DROP PROFILE.
- Hiểu DEFAULT, UNLIMITED và cách kế thừa giới hạn từ profile DEFAULT.
- Cấu hình FAILED_LOGIN_ATTEMPTS và PASSWORD_LOCK_TIME.
- Cấu hình PASSWORD_LIFE_TIME và PASSWORD_GRACE_TIME.
- Hiểu PASSWORD_REUSE_TIME và PASSWORD_REUSE_MAX phải phối hợp với nhau.
- Áp dụng PASSWORD_VERIFY_FUNCTION và kiểm tra password complexity.
- Dùng INACTIVE_ACCOUNT_TIME và PASSWORD_ROLLOVER_TIME.
- Giới hạn session đồng thời, CPU, logical reads, CONNECT_TIME và IDLE_TIME.
- Phân biệt giới hạn ở cấp session và cấp call.
- Bật RESOURCE_LIMIT và kiểm tra trạng thái thực tế.
- Phân biệt profile resource limits với Database Resource Manager.
- Theo dõi DBA_PROFILES, DBA_USERS, DBA_USERS_WITH_DEFPWD và V$SESSION.
- Thiết kế profile phù hợp cho ứng dụng, batch, analyst và service account.

> **Phạm vi ví dụ:** Các ví dụ chủ yếu theo Oracle Database 19c. Giá trị giới hạn trong ví dụ là dữ liệu lab để minh họa, không phải cấu hình production áp dụng cho mọi hệ thống. Cần kiểm tra profile hiện tại, workload thực tế, release/RU, kiến trúc CDB/PDB và chính sách bảo mật của tổ chức trước khi thay đổi.

## 1. Profile là gì?

Profile là một tập hợp các thuộc tính được Oracle gán cho database user. Một profile có thể chứa:

- **Password parameters:** quy tắc xác thực và vòng đời mật khẩu.
- **Resource parameters:** giới hạn tài nguyên mà user/session được phép sử dụng.

Profile giúp DBA quản lý theo nhóm. Ví dụ:

| Nhóm tài khoản | Profile có thể áp dụng |
| --- | --- |
| Ứng dụng giao dịch | Số session phù hợp connection pool, password lifecycle cho service account |
| Người dùng báo cáo | Giới hạn session, CPU/call hoặc logical reads theo workload |
| Tài khoản batch | Giới hạn phù hợp job dài và khung thời gian chạy |
| Developer | Giới hạn số session và tài nguyên trong môi trường dev |
| Tài khoản quản trị | Chính sách xác thực chặt, quản lý riêng theo quy trình DBA |

### 1.1. Một user chỉ có một profile

Mỗi database user được gán một profile tại một thời điểm. Profile được gán trực tiếp cho user, không gán cho role hoặc profile khác.

~~~sql
ALTER USER app_user PROFILE app_runtime_prof;
~~~

Khi đổi profile của user, profile mới áp dụng cho các session được tạo sau đó. Những session đang mở không tự nhận giới hạn mới ngay lập tức.

### 1.2. Profile không thay thế role

Role dùng để gom quyền truy cập object và system privileges. Profile dùng để gom password/resource limits.

| Thành phần | Mục đích |
| --- | --- |
| User | Danh tính database đăng nhập |
| Role | Nhóm quyền truy cập |
| Profile | Nhóm chính sách mật khẩu và giới hạn tài nguyên |
| Database Resource Manager | Điều phối và kiểm soát việc sử dụng tài nguyên theo workload |

Ví dụ, APP_RUNTIME_ROLE có thể cấp quyền SELECT/INSERT trên các bảng ứng dụng, còn APP_RUNTIME_PROF giới hạn số session và password lifecycle của APP_USER.

### 1.3. Profile DEFAULT

User không được gán profile riêng sẽ dùng profile DEFAULT. Nếu một profile cụ thể bỏ qua một parameter hoặc đặt parameter thành DEFAULT, Oracle lấy giá trị tương ứng từ profile DEFAULT.

DEFAULT và UNLIMITED khác nhau:

- DEFAULT: kế thừa giá trị parameter từ profile DEFAULT.
- UNLIMITED: không đặt giới hạn cho parameter đó.

Không giả định profile DEFAULT của database luôn giữ nguyên giá trị ban đầu. DBA có thể đã thay đổi nó. Luôn truy vấn DBA_PROFILES trước khi dựa vào giá trị mặc định.

## 2. Hai nhóm parameter và cơ chế thực thi

| Nhóm | Ví dụ | Cơ chế thực thi |
| --- | --- | --- |
| Password | FAILED_LOGIN_ATTEMPTS, PASSWORD_LIFE_TIME, PASSWORD_VERIFY_FUNCTION | Luôn được quản lý bởi password management; không phụ thuộc RESOURCE_LIMIT |
| Resource | SESSIONS_PER_USER, CPU_PER_CALL, IDLE_TIME, LOGICAL_READS_PER_SESSION | Chỉ được enforce khi RESOURCE_LIMIT = TRUE |

### 2.1. RESOURCE_LIMIT

Kiểm tra giá trị hiện tại:

~~~sql
SHOW PARAMETER resource_limit
~~~

Hoặc:

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'resource_limit';
~~~

Trên Oracle Database 19c, giá trị mặc định được tài liệu hóa là TRUE, nhưng cấu hình thực tế có thể đã được DBA thay đổi. Không suy luận trạng thái từ default value; hãy kiểm tra database đang chạy.

Nếu cần bật:

~~~sql
ALTER SYSTEM SET resource_limit = TRUE;
~~~

RESOURCE_LIMIT có thể thay đổi bằng ALTER SYSTEM. Trong môi trường CDB/PDB, phải thực hiện trong container và phạm vi được phép. Nếu muốn thay đổi persistent qua restart, DBA cần xác định cách cấu hình SPFILE phù hợp với môi trường.

### 2.2. Password parameters không bị RESOURCE_LIMIT chi phối

Ngay cả khi RESOURCE_LIMIT = FALSE, các quy tắc như số lần đăng nhập sai, thời hạn mật khẩu và password verification vẫn được Oracle áp dụng.

Đây là khác biệt quan trọng khi kiểm tra một profile: resource limits có thể đang được khai báo nhưng không được enforce nếu RESOURCE_LIMIT tắt; password limits vẫn có hiệu lực.

## 3. Tạo, sửa, gán và xóa profile

### 3.1. Quyền cần thiết

- CREATE PROFILE: tạo profile.
- ALTER PROFILE: sửa giới hạn trong profile.
- DROP PROFILE: xóa profile.
- ALTER USER: gán profile cho user.
- ALTER SYSTEM: thay đổi RESOURCE_LIMIT.
- ALTER RESOURCE COST: thay đổi trọng số của COMPOSITE_LIMIT.

Các quyền trên cần được cấp theo trách nhiệm DBA/security administrator, không cấp rộng cho application account.

### 3.2. Tạo profile

Cú pháp:

~~~sql
CREATE PROFILE profile_name LIMIT
    parameter value
    parameter value;
~~~

Ví dụ profile ứng dụng:

~~~sql
CREATE PROFILE app_runtime_prof LIMIT
    SESSIONS_PER_USER 8
    CPU_PER_SESSION UNLIMITED
    CPU_PER_CALL 6000
    CONNECT_TIME 480
    IDLE_TIME 30
    LOGICAL_READS_PER_SESSION UNLIMITED
    LOGICAL_READS_PER_CALL 500000
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7;
~~~

Các giá trị trên chỉ là ví dụ. CPU_PER_CALL 6000 tương đương 60 giây CPU vì đơn vị là một phần trăm giây. CONNECT_TIME 480 là 480 phút. IDLE_TIME 30 là 30 phút không có call. Cần benchmark và điều chỉnh theo hành vi ứng dụng.

### 3.3. Gán profile cho user

~~~sql
ALTER USER app_user PROFILE app_runtime_prof;
~~~

Nếu tạo user mới:

~~~sql
CREATE USER app_user
IDENTIFIED BY "Replace_With_Secret"
PROFILE app_runtime_prof;
~~~

Không ghi mật khẩu production thật vào script, repository hoặc log triển khai. Dùng secret manager hoặc cơ chế provisioning an toàn.

### 3.4. Sửa profile

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    SESSIONS_PER_USER 12
    IDLE_TIME 45
    CPU_PER_CALL 9000;
~~~

Thay đổi profile áp dụng cho session mới. Những session đã tồn tại tiếp tục dùng các thuộc tính đã nạp lúc đăng nhập.

### 3.5. Đặt parameter về DEFAULT hoặc UNLIMITED

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    LOGICAL_READS_PER_SESSION DEFAULT
    CONNECT_TIME UNLIMITED;
~~~

DEFAULT kế thừa giá trị từ profile DEFAULT. UNLIMITED bỏ giới hạn parameter đó.

### 3.6. Xóa profile

~~~sql
DROP PROFILE app_runtime_prof;
~~~

Không thể drop profile DEFAULT. Nếu profile đang được gán cho user, cần CASCADE:

~~~sql
DROP PROFILE app_runtime_prof CASCADE;
~~~

Khi drop profile với CASCADE, các user đang dùng profile đó được gán về DEFAULT. Việc drop profile không làm thay đổi session đang hoạt động; session mới dùng profile sau khi việc gán lại có hiệu lực.

## 4. Các password parameters

Oracle profile có các parameter chính sau:

| Parameter | Ý nghĩa |
| --- | --- |
| FAILED_LOGIN_ATTEMPTS | Số lần đăng nhập sai liên tiếp trước khi khóa tài khoản |
| PASSWORD_LOCK_TIME | Thời gian khóa sau khi vượt FAILED_LOGIN_ATTEMPTS |
| PASSWORD_LIFE_TIME | Số ngày mật khẩu được dùng trước khi hết hạn |
| PASSWORD_GRACE_TIME | Thời gian cảnh báo/cho phép đăng nhập để đổi mật khẩu trước khi hết hạn hoàn toàn |
| PASSWORD_REUSE_TIME | Số ngày cần chờ trước khi được dùng lại mật khẩu cũ |
| PASSWORD_REUSE_MAX | Số lần đổi mật khẩu cần đạt trước khi dùng lại mật khẩu cũ |
| PASSWORD_VERIFY_FUNCTION | Hàm kiểm tra độ mạnh/độ phức tạp mật khẩu |
| INACTIVE_ACCOUNT_TIME | Số ngày không đăng nhập thành công trước khi khóa tài khoản |
| PASSWORD_ROLLOVER_TIME | Khoảng thời gian cho phép mật khẩu cũ và mới cùng đăng nhập trong quá trình rollover |

Các parameter thời gian thường tính theo ngày. Có thể dùng phân số của ngày, ví dụ 1 giờ là 1/24 ngày và 1 phút là 1/1440 ngày. FAILED_LOGIN_ATTEMPTS và PASSWORD_REUSE_MAX yêu cầu số nguyên.

## 5. FAILED_LOGIN_ATTEMPTS và PASSWORD_LOCK_TIME

Hai parameter này phối hợp để giới hạn thử đăng nhập sai.

### 5.1. FAILED_LOGIN_ATTEMPTS

FAILED_LOGIN_ATTEMPTS xác định số lần xác thực thất bại liên tiếp trước khi account bị khóa.

~~~sql
CREATE PROFILE login_guard_prof LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1;
~~~

Với ví dụ trên, sau năm lần đăng nhập sai liên tiếp, account bị khóa theo thời gian PASSWORD_LOCK_TIME.

### 5.2. PASSWORD_LOCK_TIME

PASSWORD_LOCK_TIME được tính bằng ngày:

- 1: khóa một ngày.
- 1/24: khóa một giờ.
- UNLIMITED: khóa cho đến khi DBA mở khóa thủ công.

Mở khóa thủ công:

~~~sql
ALTER USER app_user ACCOUNT UNLOCK;
~~~

Đặt PASSWORD_LOCK_TIME quá dài có thể làm tăng gánh nặng hỗ trợ nếu ứng dụng cấu hình sai password và liên tục thử đăng nhập. Đặt quá ngắn có thể giảm hiệu quả chống brute force. Cần kết hợp với monitoring, rate limiting ở tầng kết nối và chính sách bảo vệ tài khoản.

### 5.3. Đếm thất bại và reset

Sau khi user đăng nhập thành công, Oracle reset số lần đăng nhập sai liên tiếp. Trong môi trường proxy authentication hoặc CONNECT THROUGH, cần hiểu account nào đang được tính cho failed login.

### 5.4. Kiểm tra trạng thái account

~~~sql
SELECT
    username,
    account_status,
    lock_date,
    expiry_date,
    profile
FROM dba_users
WHERE username = 'APP_USER';
~~~

ACCOUNT_STATUS có thể thể hiện OPEN, LOCKED, EXPIRED, EXPIRED(GRACE) hoặc trạng thái kết hợp tùy tình huống. Trạng thái hiển thị trong dictionary có thể được cập nhật khi có lần đăng nhập tiếp theo; đối chiếu với sự kiện đăng nhập và thời điểm lock.

## 6. PASSWORD_LIFE_TIME và PASSWORD_GRACE_TIME

### 6.1. PASSWORD_LIFE_TIME

PASSWORD_LIFE_TIME xác định số ngày mật khẩu có thể dùng để xác thực trước khi hết hạn.

~~~sql
CREATE PROFILE human_user_prof LIMIT
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7;
~~~

Ví dụ 90 ngày là chính sách minh họa. Hãy chọn thời hạn theo chính sách bảo mật và loại account. Oracle cảnh báo cần thận trọng khi đặt PASSWORD_LIFE_TIME quá thấp, vì việc đổi mật khẩu thường xuyên có thể tạo gánh nặng vận hành và khuyến khích hành vi chọn mật khẩu dễ đoán.

### 6.2. PASSWORD_GRACE_TIME

Khi mật khẩu hết thời hạn PASSWORD_LIFE_TIME, người dùng bước vào grace period:

1. Đăng nhập bằng mật khẩu hiện tại.
2. Oracle cảnh báo mật khẩu sắp hết hạn.
3. User vẫn được đăng nhập trong grace period để đổi mật khẩu.
4. Nếu grace period kết thúc mà mật khẩu chưa đổi, password hết hạn và user phải đổi trước khi tiếp tục.

Thông báo thường gặp:

- ORA-28002: password sẽ hết hạn trong một số ngày.
- ORA-28001: password đã hết hạn.

### 6.3. Grace period không phải thời hạn mới để giữ mật khẩu mãi mãi

PASSWORD_GRACE_TIME là khoảng chuyển tiếp. Nó giúp ứng dụng/người dùng có thời gian đổi mật khẩu mà không bị ngắt đột ngột tại ngày hết hạn.

### 6.4. Kiểm tra expiry

~~~sql
SELECT
    username,
    account_status,
    expiry_date,
    profile
FROM dba_users
WHERE username IN ('APP_USER', 'REPORT_USER');
~~~

Không chỉ kiểm tra profile definition. DBA_USERS cho biết trạng thái và ngày hết hạn của từng account.

## 7. PASSWORD_REUSE_TIME và PASSWORD_REUSE_MAX

Hai parameter này phải được cấu hình cùng nhau để đặt điều kiện dùng lại mật khẩu.

### 7.1. PASSWORD_REUSE_TIME

Số ngày phải chờ trước khi password cũ được phép dùng lại.

### 7.2. PASSWORD_REUSE_MAX

Số lần thay đổi password phải thực hiện trước khi password cũ được phép dùng lại.

### 7.3. Cả hai điều kiện phải thỏa mãn

~~~sql
CREATE PROFILE password_history_prof LIMIT
    PASSWORD_REUSE_TIME 365
    PASSWORD_REUSE_MAX 10;
~~~

Với ví dụ này, password cũ chỉ có thể được dùng lại khi:

- Đã qua 365 ngày kể từ lần password đó được dùng.
- User đã đổi password ít nhất 10 lần theo quy tắc.

### 7.4. UNLIMITED có semantics dễ nhầm

| PASSWORD_REUSE_TIME | PASSWORD_REUSE_MAX | Kết quả |
| --- | --- | --- |
| Giá trị hữu hạn | Giá trị hữu hạn | Phải thỏa cả điều kiện thời gian và số lần đổi |
| UNLIMITED | Giá trị hữu hạn | Không thể dùng lại password cũ |
| Giá trị hữu hạn | UNLIMITED | Không thể dùng lại password cũ |
| UNLIMITED | UNLIMITED | Oracle bỏ qua cả hai hạn chế; password có thể được dùng lại |

Đây là điểm quan trọng: một parameter UNLIMITED kết hợp với parameter còn lại hữu hạn có nghĩa không bao giờ được reuse; cả hai cùng UNLIMITED thì Oracle bỏ qua cả hai.

### 7.5. DEFAULT và password reuse

Nếu đặt một trong hai parameter thành DEFAULT, Oracle lấy giá trị tương ứng từ profile DEFAULT. Nếu profile DEFAULT vẫn để UNLIMITED, parameter đó được xem là UNLIMITED. Hãy kiểm tra DBA_PROFILES để tránh cấu hình nhầm.

## 8. PASSWORD_VERIFY_FUNCTION

PASSWORD_VERIFY_FUNCTION gắn một PL/SQL function dùng để kiểm tra password khi user đặt hoặc đổi mật khẩu.

### 8.1. Mục đích

Hàm kiểm tra có thể áp dụng các quy tắc như:

- Độ dài tối thiểu.
- Có chữ hoa/chữ thường.
- Có chữ số hoặc ký tự đặc biệt.
- Không chứa username hoặc biến thể dễ đoán.
- Không quá giống password cũ.
- Không nằm trong danh sách password phổ biến.

Độ phức tạp chính xác phụ thuộc function được triển khai.

### 8.2. Oracle supplied verification functions

Oracle cung cấp các password verification scripts/functions cho một số phiên bản và policy. Ví dụ tên function thường gặp trong Oracle 19c là ORA12C_VERIFY_FUNCTION hoặc ORA12C_STRONG_VERIFY_FUNCTION, tùy script và môi trường đã cài đặt.

Trước khi gán, kiểm tra function có tồn tại trong SYS và user thực hiện gán profile có EXECUTE privilege phù hợp.

~~~sql
SELECT owner, object_name, object_type, status
FROM dba_objects
WHERE owner = 'SYS'
  AND object_name IN (
      'ORA12C_VERIFY_FUNCTION',
      'ORA12C_STRONG_VERIFY_FUNCTION'
  )
ORDER BY object_name;
~~~

Nếu function đã được cài và policy cho phép:

~~~sql
ALTER PROFILE human_user_prof LIMIT
    PASSWORD_VERIFY_FUNCTION ORA12C_VERIFY_FUNCTION;
~~~

Không giả định function tồn tại chỉ vì database là 19c. DBA phải xác nhận script đã được cài trong Oracle Home/database và kiểm tra function status.

### 8.3. Function phải thuộc SYS schema

Oracle yêu cầu password verification function nằm trong SYS schema và caller có EXECUTE privilege trên function. Có thể dùng script Oracle cung cấp hoặc function tự viết theo giao diện được tài liệu hóa.

### 8.4. Đặt lại về không kiểm tra

~~~sql
ALTER PROFILE human_user_prof LIMIT
    PASSWORD_VERIFY_FUNCTION NULL;
~~~

NULL có nghĩa không chạy password verification function cho profile đó. Không dùng cấu hình này nếu policy yêu cầu password complexity.

### 8.5. Password complexity không thay thế MFA

Password verification chỉ kiểm tra password theo function. Nó không thay thế:

- Multi-factor authentication.
- Network encryption.
- Account lifecycle management.
- Secret vault và rotation automation.
- Audit và monitoring.
- Privilege separation.

## 9. INACTIVE_ACCOUNT_TIME

INACTIVE_ACCOUNT_TIME tự động khóa account nếu user không đăng nhập thành công trong một khoảng thời gian liên tiếp.

~~~sql
CREATE PROFILE dormant_user_prof LIMIT
    INACTIVE_ACCOUNT_TIME 60;
~~~

Ví dụ account sẽ bị khóa nếu không có login thành công trong 60 ngày.

### 9.1. Giới hạn giá trị

Trong Oracle 19c:

- Đơn vị là ngày nguyên.
- Giá trị nhỏ nhất là 15 ngày.
- Giá trị lớn nhất là 24855 ngày.
- UNLIMITED vô hiệu hóa giới hạn inactivity.

### 9.2. Account nào bị ảnh hưởng?

Parameter này áp dụng cho database-authenticated users; password parameters không có tác dụng với external/global authenticated users. Trong môi trường read-only database, database không thể thực hiện thao tác khóa account như trên primary theo cách thông thường.

### 9.3. Inactivity khác account lock do login sai

INACTIVE_ACCOUNT_TIME theo dõi thời điểm đăng nhập thành công gần nhất. FAILED_LOGIN_ATTEMPTS theo dõi số lần xác thực thất bại liên tiếp. Hai cơ chế có mục tiêu khác nhau.

## 10. PASSWORD_ROLLOVER_TIME

PASSWORD_ROLLOVER_TIME hỗ trợ đổi mật khẩu cho application service account mà không cần cập nhật tất cả client cùng một thời điểm.

### 10.1. Vấn đề của service account

Một ứng dụng có thể chạy trên nhiều node, container hoặc máy chủ. Tất cả kết nối tới database bằng một service account. Khi DBA đổi password, mỗi client cần được cập nhật secret mới. Nếu database từ chối password cũ ngay lập tức, các node chưa nhận secret mới có thể mất kết nối.

### 10.2. Rollover period

Khi profile có PASSWORD_ROLLOVER_TIME khác 0 và DBA đổi password, Oracle cho phép cả password cũ và password mới đăng nhập trong khoảng rollover đã cấu hình.

~~~sql
CREATE PROFILE app_service_prof LIMIT
    PASSWORD_ROLLOVER_TIME 1;
~~~

Giá trị 1 là một ngày. Trong khoảng này, ứng dụng có thể được cập nhật lần lượt sang password mới.

### 10.3. Giới hạn rollover

- Giá trị 0 hoặc NULL: tắt rollover.
- Giá trị dương: bật rollover.
- Thời gian tối thiểu: 1 giờ.
- Thời gian tối đa: 60 ngày hoặc giá trị nhỏ hơn giữa PASSWORD_LIFE_TIME và PASSWORD_GRACE_TIME theo quy tắc Oracle.
- Đơn vị ngày; 1 giờ biểu diễn bằng 1/24.

Ví dụ sáu giờ:

~~~sql
ALTER PROFILE app_service_prof LIMIT
    PASSWORD_ROLLOVER_TIME 6/24;
~~~

### 10.4. Quy trình đổi password không downtime

1. Tạo/điều chỉnh profile với PASSWORD_ROLLOVER_TIME khác 0.
2. Gán profile cho service account.
3. DBA đổi password database account.
4. Trong rollover period, password cũ và mới đều có thể đăng nhập.
5. Cập nhật secret trên từng application node.
6. Xác nhận toàn bộ node dùng password mới.
7. Kết thúc rollover sớm nếu đã hoàn tất.

Kết thúc sớm:

~~~sql
ALTER USER app_service_user
EXPIRE PASSWORD ROLLOVER PERIOD;
~~~

Sau khi rollover kết thúc, chỉ password mới còn được chấp nhận.

### 10.5. Kiểm tra trạng thái

~~~sql
SELECT username, account_status, profile
FROM dba_users
WHERE username = 'APP_SERVICE_USER';
~~~

Trong thời gian rollover, ACCOUNT_STATUS có thể là IN ROLLOVER.

### 10.6. Chỉ dùng cho service accounts

Oracle thiết kế gradual password rollover cho database application clients/service accounts, không phải administrative users. Administrative users bị giới hạn không dùng tính năng này; không cấp administrative privileges cho user có profile bật rollover.

Nếu password bị nghi ngờ compromise, cần đổi/thu hồi ngay theo incident response; không kéo dài rollover chỉ để thuận tiện triển khai.

## 11. Các resource parameters theo session và call

Profile có thể giới hạn tài nguyên ở hai cấp:

- **Session level:** tổng lượng tài nguyên trong suốt một session.
- **Call level:** lượng tài nguyên của một call xử lý SQL, ví dụ parse, execute hoặc fetch.

### 11.1. Bảng resource parameters

| Parameter | Cấp | Đơn vị/ý nghĩa |
| --- | --- | --- |
| SESSIONS_PER_USER | Concurrent sessions | Số session đồng thời tối đa của user |
| CPU_PER_SESSION | Session | CPU time tích lũy, đơn vị 1/100 giây |
| CPU_PER_CALL | Call | CPU time cho một call, đơn vị 1/100 giây |
| CONNECT_TIME | Session | Tổng thời gian kết nối, phút |
| IDLE_TIME | Session | Thời gian liên tục không có call, phút |
| LOGICAL_READS_PER_SESSION | Session | Số data blocks đọc từ memory và disk trong session |
| LOGICAL_READS_PER_CALL | Call | Số data blocks đọc trong một call |
| PRIVATE_SGA | Session | Private SGA memory; chỉ hữu ích với Shared Server |
| COMPOSITE_LIMIT | Session | Tổng chi phí tài nguyên theo service units có trọng số |

### 11.2. SESSIONS_PER_USER

Giới hạn số session đồng thời của một user:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    SESSIONS_PER_USER 8;
~~~

Nếu ứng dụng dùng connection pool, giá trị phải tương thích với:

- Số application instances.
- Pool size tối đa mỗi instance.
- Batch/monitoring connections dùng cùng user.
- Kết nối quản trị hoặc support nếu có.

Đặt thấp hơn tổng số connection hợp lệ có thể làm ứng dụng nhận lỗi khi mở thêm session. Đặt quá cao có thể làm service account tạo nhiều session hơn khả năng hệ thống.

### 11.3. CPU_PER_SESSION

Giới hạn tổng CPU time của một session. Đơn vị là 1/100 giây.

~~~sql
ALTER PROFILE analyst_prof LIMIT
    CPU_PER_SESSION 360000;
~~~

360000 centiseconds tương đương 3600 giây CPU. Đây là CPU time, không phải wall-clock time.

### 11.4. CPU_PER_CALL

Giới hạn CPU time cho một call:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    CPU_PER_CALL 6000;
~~~

6000 centiseconds tương đương 60 giây CPU cho một call. Một query có thể có nhiều call trong quá trình parse/execute/fetch; không đồng nhất CPU_PER_CALL với tổng CPU của toàn session.

### 11.5. LOGICAL_READS_PER_SESSION

Giới hạn tổng logical block reads trong session. Logical reads bao gồm block được đọc từ buffer cache và block được đọc từ disk vào cache.

### 11.6. LOGICAL_READS_PER_CALL

Giới hạn logical reads của một call:

~~~sql
ALTER PROFILE analyst_prof LIMIT
    LOGICAL_READS_PER_CALL 500000;
~~~

Đây là giới hạn số block, không phải số hàng. Một query trả ít hàng vẫn có thể đọc nhiều block nếu predicate không chọn lọc hoặc plan không phù hợp.

### 11.7. CONNECT_TIME

CONNECT_TIME giới hạn tổng elapsed time của session, đơn vị phút:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    CONNECT_TIME 480;
~~~

Giá trị 480 tương đương tám giờ. Khi vượt giới hạn, Oracle rollback transaction hiện tại và kết thúc session. Thời gian được kiểm tra định kỳ nên session có thể tồn tại lâu hơn giới hạn một chút.

CONNECT_TIME khác IDLE_TIME: CONNECT_TIME tính tổng thời gian session tồn tại, bao gồm thời gian session đang làm việc.

### 11.8. IDLE_TIME

IDLE_TIME giới hạn thời gian liên tục session không gọi database:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    IDLE_TIME 30;
~~~

Sau khoảng 30 phút idle, Oracle có thể kết thúc session. Thời gian được kiểm tra định kỳ nên không nhất thiết bị ngắt đúng từng giây tại mốc 30 phút.

**Long-running query không bị tính là idle chỉ vì nó đang chạy lâu.** IDLE_TIME đo khoảng thời gian không có call giữa các lần client gọi database.

Với connection pool, cần đồng bộ IDLE_TIME với pool idle timeout và cơ chế kiểm tra connection. Nếu database kết thúc session trước khi pool loại connection, ứng dụng có thể lấy lại một connection đã chết và nhận lỗi ở lần sử dụng tiếp theo.

### 11.9. PRIVATE_SGA

PRIVATE_SGA giới hạn vùng private memory của session trong SGA. Parameter này chỉ có ý nghĩa khi dùng Shared Server architecture; với Dedicated Server, private SQL/PLSQL areas thường nằm trong PGA.

### 11.10. COMPOSITE_LIMIT

COMPOSITE_LIMIT giới hạn tổng chi phí tài nguyên session theo service units. Oracle tính weighted sum từ:

- CPU_PER_SESSION.
- CONNECT_TIME.
- LOGICAL_READS_PER_SESSION.
- PRIVATE_SGA.

Trọng số được cấu hình bằng ALTER RESOURCE COST. Nếu không đặt trọng số cho một resource, trọng số mặc định là 0.

Ví dụ:

~~~sql
ALTER RESOURCE COST
    CPU_PER_SESSION 100
    CONNECT_TIME 1
    LOGICAL_READS_PER_SESSION 2;
~~~

Với công thức trên, session cost là:

~~~text
cost =
    100 * CPU_PER_SESSION
  +   1 * CONNECT_TIME
  +   2 * LOGICAL_READS_PER_SESSION
~~~

Sau đó profile có thể giới hạn COMPOSITE_LIMIT:

~~~sql
ALTER PROFILE analyst_prof LIMIT
    COMPOSITE_LIMIT 5000000;
~~~

COMPOSITE_LIMIT khó thiết kế hơn các limit riêng lẻ vì DBA phải hiểu workload và chọn trọng số. Không dùng một con số tùy ý mà chưa đo usage.

## 12. Điều gì xảy ra khi vượt resource limit?

Oracle xử lý khác nhau tùy loại giới hạn.

### 12.1. Vượt CONNECT_TIME hoặc IDLE_TIME

Oracle:

1. Rollback transaction hiện tại.
2. Kết thúc session.
3. Thu hồi tài nguyên session.
4. Client thường nhận lỗi khi session thực hiện call tiếp theo.

PMON có thể cần thêm thời gian để dọn dẹp session sau khi bị kết thúc.

### 12.2. Vượt giới hạn session-level khác

Khi vượt một giới hạn session-level như CPU_PER_SESSION hoặc LOGICAL_READS_PER_SESSION, Oracle abort operation/câu lệnh hiện tại và rollback statement. Các statement trước đó trong transaction vẫn còn. User chỉ có thể COMMIT, ROLLBACK hoặc disconnect; không thể tiếp tục công việc bình thường trong session đó.

### 12.3. Vượt giới hạn call-level

Khi vượt CPU_PER_CALL hoặc LOGICAL_READS_PER_CALL:

- Statement hiện tại bị abort và rollback.
- Các statement trước trong transaction vẫn còn.
- Session vẫn kết nối.
- Client có thể xử lý lỗi và tiếp tục session theo quy trình ứng dụng.

### 12.4. Không nhầm rollback statement với rollback transaction

Với call-level limit, statement vượt ngưỡng bị rollback nhưng transaction trước đó không tự động mất. Với CONNECT_TIME/IDLE_TIME, Oracle rollback transaction hiện tại và kết thúc session. Cần hiểu điều này khi thiết kế ứng dụng có nhiều DML trong cùng transaction.

## 13. Bật và kiểm tra resource enforcement

### 13.1. Kiểm tra RESOURCE_LIMIT

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'resource_limit';
~~~

Nếu đang FALSE, resource limits trong profile không được enforce. Password parameters vẫn có hiệu lực.

### 13.2. Bật enforcement

~~~sql
ALTER SYSTEM SET resource_limit = TRUE;
~~~

Thay đổi này ảnh hưởng toàn database hoặc phạm vi container theo nơi thực thi. DBA phải đánh giá tác động đến tất cả account đang dùng resource profiles.

### 13.3. Kiểm tra profile được gán

~~~sql
SELECT username, profile, account_status
FROM dba_users
ORDER BY username;
~~~

### 13.4. Kiểm tra resource limits trong profile

~~~sql
SELECT
    profile,
    resource_name,
    resource_type,
    limit
FROM dba_profiles
WHERE profile IN (
    'APP_RUNTIME_PROF',
    'ANALYST_PROF',
    'DEFAULT'
)
ORDER BY profile, resource_type, resource_name;
~~~

DBA_PROFILES cho biết parameter và giá trị đang được cấu hình. Nếu profile dùng DEFAULT, cần xem tiếp dòng tương ứng của profile DEFAULT để biết giá trị hiệu lực.

## 14. Password defaults trong profile DEFAULT

Oracle Database 19c tài liệu hóa một số giá trị thường gặp của profile DEFAULT:

| Password parameter | Giá trị mặc định được tài liệu hóa |
| --- | --- |
| FAILED_LOGIN_ATTEMPTS | 10 |
| PASSWORD_LIFE_TIME | 180 ngày |
| PASSWORD_GRACE_TIME | 7 ngày |
| PASSWORD_LOCK_TIME | 1 ngày |
| PASSWORD_REUSE_TIME | UNLIMITED |
| PASSWORD_REUSE_MAX | UNLIMITED |
| PASSWORD_VERIFY_FUNCTION | NULL |
| INACTIVE_ACCOUNT_TIME | UNLIMITED |
| PASSWORD_ROLLOVER_TIME | 0 |

Các resource parameters trong profile DEFAULT ban đầu thường là UNLIMITED. Tuy nhiên, DBA có thể sửa profile DEFAULT và các database được tạo bằng phương pháp khác nhau có thể có cấu hình khác. Vì vậy, hãy truy vấn DBA_PROFILES thay vì hard-code giả định vào runbook.

### 14.1. Xem profile DEFAULT

~~~sql
SELECT resource_name, resource_type, limit
FROM dba_profiles
WHERE profile = 'DEFAULT'
ORDER BY resource_type, resource_name;
~~~

### 14.2. DEFAULT password verify function là NULL

Nếu PASSWORD_VERIFY_FUNCTION là NULL, profile không gọi password complexity function. Việc chỉ đặt PASSWORD_LIFE_TIME không tự bảo đảm password đủ mạnh hoặc không trùng password cũ.

## 15. Tạo profile kết hợp password policy và resource limits

Ví dụ dưới đây tạo profile cho ứng dụng giao dịch. Các giá trị chỉ để thực hành.

~~~sql
CREATE PROFILE app_runtime_prof LIMIT
    SESSIONS_PER_USER 12
    CPU_PER_SESSION UNLIMITED
    CPU_PER_CALL 6000
    CONNECT_TIME 480
    IDLE_TIME 30
    LOGICAL_READS_PER_SESSION UNLIMITED
    LOGICAL_READS_PER_CALL 500000
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7
    PASSWORD_REUSE_TIME 365
    PASSWORD_REUSE_MAX 10
    PASSWORD_ROLLOVER_TIME 0;
~~~

Nếu tổ chức yêu cầu password complexity, gán PASSWORD_VERIFY_FUNCTION sau khi xác nhận function có sẵn:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    PASSWORD_VERIFY_FUNCTION ORA12C_VERIFY_FUNCTION;
~~~

Gán profile:

~~~sql
ALTER USER app_service_user PROFILE app_runtime_prof;
~~~

Kiểm tra:

~~~sql
SELECT username, profile, account_status
FROM dba_users
WHERE username = 'APP_SERVICE_USER';

SELECT resource_name, resource_type, limit
FROM dba_profiles
WHERE profile = 'APP_RUNTIME_PROF'
ORDER BY resource_type, resource_name;
~~~

Sau khi thay đổi, mở session mới bằng account để kiểm tra. Session đang mở từ trước không tự nạp lại profile.

## 16. Profile riêng cho service account và gradual rollover

Tài khoản ứng dụng thường có password được lưu trong secret manager và phân phối tới nhiều application nodes. Có thể dùng profile riêng:

~~~sql
CREATE PROFILE app_service_rollover_prof LIMIT
    SESSIONS_PER_USER 20
    IDLE_TIME 60
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 180
    PASSWORD_GRACE_TIME 7
    PASSWORD_ROLLOVER_TIME 1;
~~~

Gán cho service user:

~~~sql
ALTER USER app_service_user
PROFILE app_service_rollover_prof;
~~~

Khi cần đổi password:

~~~sql
ALTER USER app_service_user
IDENTIFIED BY "New_Secret_From_Vault";
~~~

Trong rollover period, cả password cũ và mới có thể được chấp nhận. Cập nhật tất cả application nodes rồi kết thúc sớm:

~~~sql
ALTER USER app_service_user
EXPIRE PASSWORD ROLLOVER PERIOD;
~~~

Kiểm tra account:

~~~sql
SELECT username, account_status, profile
FROM dba_users
WHERE username = 'APP_SERVICE_USER';
~~~

Không cấp administrative privileges cho service account chỉ để tiện triển khai. Password rollover được thiết kế cho application accounts và không áp dụng cho administrative users theo giới hạn của Oracle.

## 17. Profile cho analyst và batch workload

Không phải mọi nhóm user đều cần cùng giới hạn.

### 17.1. Analyst profile

~~~sql
CREATE PROFILE analyst_prof LIMIT
    SESSIONS_PER_USER 3
    CPU_PER_CALL 12000
    CONNECT_TIME 720
    IDLE_TIME 20
    LOGICAL_READS_PER_CALL 1000000
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7;
~~~

Profile này minh họa giới hạn số session, call CPU, thời gian kết nối và idle. Với truy vấn phân tích lớn, giới hạn CPU/logical reads quá thấp có thể làm query hợp lệ thất bại.

### 17.2. Batch profile

~~~sql
CREATE PROFILE batch_prof LIMIT
    SESSIONS_PER_USER 2
    CPU_PER_SESSION UNLIMITED
    CPU_PER_CALL UNLIMITED
    CONNECT_TIME 1440
    IDLE_TIME 60
    LOGICAL_READS_PER_SESSION UNLIMITED
    LOGICAL_READS_PER_CALL UNLIMITED
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24;
~~~

Batch job có thể cần session dài và đọc nhiều block. Profile này minh họa cách tách workload batch khỏi user interactive. Nếu cần điều phối CPU, parallelism, I/O hoặc ưu tiên workload, hãy xem xét Database Resource Manager.

### 17.3. Không dùng profile để che một SQL runaway

Nếu một query chạy quá lâu do plan regression, profile CPU_PER_CALL có thể abort query nhưng không sửa nguyên nhân. Hãy kiểm tra execution plan, statistics, SQL tuning và Resource Manager directive thay vì chỉ hạ ngưỡng.

## 18. Profile và Database Resource Manager

Oracle SQL Language Reference khuyến nghị Database Resource Manager thay vì chỉ dùng profile để thiết lập resource limits khi cần cơ chế quản lý linh hoạt.

### 18.1. Profile resource limits

Profile cung cấp các hard limits như:

- Số session tối đa.
- CPU time per call/session.
- Logical reads per call/session.
- Connect time và idle time.
- Một số giới hạn bộ nhớ/session.

Khi vượt ngưỡng, operation/session có thể bị abort hoặc kết thúc.

### 18.2. Database Resource Manager

Database Resource Manager cho phép DBA định nghĩa resource plan, consumer groups và directive để phân phối tài nguyên giữa workload classes.

Các khả năng có thể gồm:

- Phân bổ CPU theo tỷ lệ/priority.
- Giới hạn hoặc điều phối parallel execution.
- Quản lý active sessions và queueing.
- Ưu tiên workload quan trọng.
- Quản lý I/O và các tài nguyên được hỗ trợ.
- Chuyển consumer group theo mapping rules.

### 18.3. So sánh

| Tiêu chí | Profile | Database Resource Manager |
| --- | --- | --- |
| Gắn với | Database user | Consumer group/workload |
| Session count | Có SESSIONS_PER_USER | Có thể quản lý active sessions theo directive |
| Password policy | Có | Không phải mục tiêu |
| CPU | Hard limits per session/call | Phân phối/điều phối workload linh hoạt |
| Workload priority | Hạn chế | Có resource plans/directives |
| Query queueing | Không phải cơ chế chính | Có thể quản lý queueing theo cấu hình |
| Quản lý theo service/module | Hạn chế | Có thể mapping workload vào consumer group |

### 18.4. Có thể dùng cả hai

Một thiết kế có thể:

- Dùng profile cho password policy và số session tối đa.
- Dùng Resource Manager để ưu tiên OLTP so với batch/reporting.
- Dùng network/application pool limits để kiểm soát connection từ bên ngoài.
- Dùng SQL tuning và plan management để xử lý query regression.

Không xem profile và Resource Manager là hai lựa chọn loại trừ nhau.

## 19. Giám sát profile và session

### 19.1. DBA_PROFILES

~~~sql
SELECT
    profile,
    resource_name,
    resource_type,
    limit
FROM dba_profiles
ORDER BY profile, resource_type, resource_name;
~~~

USER_PROFILES có thể dùng để xem profile settings trong phạm vi user hiện tại theo quyền.

### 19.2. DBA_USERS

~~~sql
SELECT
    username,
    profile,
    account_status,
    lock_date,
    expiry_date,
    authentication_type
FROM dba_users
ORDER BY username;
~~~

Các cột dictionary có thể khác giữa release. Nếu query một cột không tồn tại, đối chiếu DBA_USERS reference của database đang dùng.

### 19.3. Tìm user đang dùng một profile

~~~sql
SELECT username, account_status
FROM dba_users
WHERE profile = 'APP_RUNTIME_PROF'
ORDER BY username;
~~~

### 19.4. Theo dõi session hiện tại

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    profile,
    last_call_et,
    machine,
    program,
    module
FROM v$session
WHERE username = 'APP_SERVICE_USER'
ORDER BY sid;
~~~

LAST_CALL_ET có ý nghĩa theo trạng thái session: với INACTIVE là số giây kể từ khi session trở nên inactive; với ACTIVE là số giây kể từ khi session active. Nó hữu ích để đối chiếu IDLE_TIME nhưng không thay thế cơ chế enforcement.

### 19.5. Theo dõi session statistics

~~~sql
SELECT
    s.sid,
    s.serial#,
    n.name,
    st.value
FROM v$session s
JOIN v$sesstat st
  ON st.sid = s.sid
JOIN v$statname n
  ON n.statistic# = st.statistic#
WHERE s.username = 'APP_SERVICE_USER'
  AND n.name IN (
      'CPU used by this session',
      'session logical reads'
  )
ORDER BY s.sid, n.name;
~~~

Đây là số liệu tích lũy theo session. Dùng delta giữa hai thời điểm hoặc kết hợp monitoring để hiểu tốc độ tiêu thụ, không so sánh số tích lũy giữa các session có tuổi đời khác nhau.

### 19.6. Tìm user dùng password mặc định

~~~sql
SELECT
    d.username,
    u.account_status,
    u.profile
FROM dba_users_with_defpwd d
JOIN dba_users u
  ON u.username = d.username
ORDER BY d.username;
~~~

DBA_USERS_WITH_DEFPWD hỗ trợ tìm account còn dùng default password. Xử lý các account này theo chính sách bảo mật và ownership của hệ thống.

## 20. CDB và PDB: common profile và local profile

Trong multitenant database, profile có thể là common hoặc local:

- Common profile được tạo trong CDB root và có phạm vi các container theo quy tắc common object.
- Local profile được tạo trong PDB và chỉ áp dụng trong PDB đó.

### 20.1. Tên profile common

Common profile thường cần prefix theo COMMON_USER_PREFIX, mặc định là C##. Ví dụ:

~~~sql
CREATE PROFILE c##common_app_prof LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1;
~~~

Thực hiện trong CDB root với quyền thích hợp.

### 20.2. Password/resource profile của common user

Trong CDB, khi common user được gán profile ở root và profile khác trong PDB, Oracle áp dụng password-related settings từ profile ở root; resource-related settings của session trong PDB được lấy từ profile gán trong PDB theo quy tắc multitenant.

Đây là điểm cần chú ý khi cùng một common user đăng nhập nhiều PDB. Không suy luận password policy và resource limits đều đến từ cùng một profile.

### 20.3. Kiểm tra container hiện tại

~~~sql
SHOW CON_NAME
~~~

Hoặc:

~~~sql
SELECT sys_context('USERENV', 'CON_NAME') AS container_name
FROM dual;
~~~

Trước khi CREATE/ALTER PROFILE, xác nhận đang ở root hay PDB và phạm vi thay đổi mong muốn.

## 21. Thay đổi profile có ảnh hưởng session hiện tại không?

Không. Profile changes áp dụng cho các session được tạo sau khi thay đổi.

Ví dụ:

~~~sql
ALTER PROFILE app_runtime_prof LIMIT
    IDLE_TIME 15;
~~~

Session đã đăng nhập trước câu ALTER PROFILE vẫn có giới hạn đã nạp khi kết nối. Session mới sẽ dùng IDLE_TIME 15.

Vì vậy, quy trình triển khai nên:

1. Kiểm tra profile hiện tại.
2. Sửa profile.
3. Xác nhận user được gán đúng profile.
4. Tạo session mới bằng account thử nghiệm.
5. Kiểm tra hành vi.
6. Chỉ sau đó mới áp dụng cho nhóm account production.

Nếu cần xác nhận enforcement, test trong môi trường lab bằng các ngưỡng nhỏ và workload kiểm soát. Không cố tình tạo CPU/IO runaway trên production.

## 22. Tác động đến connection pool và ứng dụng

Profile resource limits có thể tác động trực tiếp tới ứng dụng dùng connection pool.

### 22.1. SESSIONS_PER_USER và pool size

Nếu một service account dùng chung cho nhiều application instances, tổng pool capacity có thể vượt SESSIONS_PER_USER:

~~~text
Node A pool max = 10
Node B pool max = 10
Node C pool max = 10
Total potential sessions = 30
~~~

Nếu profile giới hạn 20, node cuối có thể không mở đủ connection. Cần tính tổng số connection có thể đồng thời mở, kể cả monitoring và batch.

### 22.2. IDLE_TIME và pool validation

Database có thể kết thúc session idle sau timeout. Connection pool cần:

- Idle timeout thấp hơn hoặc phối hợp với database timeout.
- Validate connection trước khi cấp cho request.
- Loại connection bị database đóng.
- Retry kết nối theo chính sách an toàn.

Không chỉ tăng IDLE_TIME vô hạn để tránh lỗi stale connection; cần xem xét session leaks và số lượng connection.

### 22.3. CONNECT_TIME và connection lifetime

CONNECT_TIME giới hạn tổng tuổi đời session. Pool cần biết database có thể kết thúc session theo thời gian và phải tái tạo connection. Nếu profile có CONNECT_TIME ngắn hơn connection lifetime trong pool, ứng dụng có thể gặp lỗi kết nối khi session bị kết thúc.

### 22.4. Password expiration và secret rotation

Khi password của service account hết hạn, ứng dụng có thể mất khả năng tạo connection mới. Vì vậy:

- Đồng bộ password lifecycle với secret manager.
- Có cảnh báo trước expiry.
- Thử rotation trên môi trường staging.
- Dùng PASSWORD_ROLLOVER_TIME nếu phù hợp để cập nhật nhiều client dần dần.
- Không để service account bị khóa bởi failed login do secret cũ.

## 23. Các lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-02391 | Vượt SESSIONS_PER_USER | Kiểm tra pool size, session leak và profile |
| ORA-02393 | Vượt CPU_PER_CALL | Kiểm tra query plan, workload và ngưỡng call |
| ORA-02394 | Vượt CPU_PER_SESSION | Kiểm tra session workload và tổng CPU |
| ORA-02395 | Vượt LOGICAL_READS_PER_SESSION | Kiểm tra logical reads, plan và giới hạn |
| ORA-02396 | Vượt IDLE_TIME | Session idle bị kết thúc; kiểm tra pool timeout |
| ORA-02399 | Vượt CONNECT_TIME | Session quá thời gian; điều chỉnh connection lifecycle |
| ORA-28000 | Account bị khóa | Kiểm tra failed attempts, lock time và unlock policy |
| ORA-28001 | Password hết hạn | Đổi password theo password lifecycle |
| ORA-28002 | Password sắp hết hạn | Đổi password trong grace period |
| ORA-28003 | Password verification function từ chối password | Đọc quy tắc verify function và chọn password đáp ứng |
| Resource limit khai báo nhưng không có tác dụng | RESOURCE_LIMIT đang FALSE | Kiểm tra V$PARAMETER và bật enforcement nếu được duyệt |
| ALTER PROFILE không ảnh hưởng session đang mở | Profile changes áp dụng session mới | Tạo session mới để xác nhận |
| Password verify function invalid | Function chưa cài hoặc compile lỗi | Kiểm tra SYS objects, grants và function status |
| User bị khóa do inactivity | INACTIVE_ACCOUNT_TIME đã vượt | Xác nhận owner rồi unlock theo quy trình |
| Ứng dụng mất connection sau idle | IDLE_TIME thấp hơn pool timeout | Đồng bộ timeout và connection validation |

Mã lỗi có thể phụ thuộc loại resource và thời điểm Oracle trả lỗi. Khi điều tra, đọc error stack đầy đủ và đối chiếu SQL Language Reference của release.

## 24. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Profile là role | Role quản lý privileges; profile quản lý password/resource limits |
| Một user có thể có nhiều profile đồng thời | Một user chỉ được gán một profile tại một thời điểm |
| Profile gán cho role | Profile chỉ gán cho user |
| RESOURCE_LIMIT điều khiển cả password policy | Nó chỉ điều khiển resource limits; password limits luôn được áp dụng |
| Khai báo IDLE_TIME là query dài bị kill | Query đang chạy không bị tính là idle giữa các call |
| CONNECT_TIME giống IDLE_TIME | CONNECT_TIME tính tổng thời gian session; IDLE_TIME tính khoảng không có call |
| CPU_PER_CALL là wall-clock timeout | Nó đo CPU time cho call, không phải elapsed time |
| LOGICAL_READS là số hàng trả về | Nó là số data blocks đọc |
| PRIVATE_SGA áp dụng như nhau cho Dedicated Server | Giới hạn này chỉ quan trọng với Shared Server |
| PASSWORD_REUSE_TIME hữu hạn là đủ | Cần phối hợp PASSWORD_REUSE_MAX |
| Một reuse parameter UNLIMITED luôn cho phép reuse | Một UNLIMITED kết hợp một hữu hạn sẽ cấm reuse |
| Cả hai reuse parameters UNLIMITED nghĩa cấm reuse | Oracle bỏ qua cả hai; password có thể reuse |
| PASSWORD_LIFE_TIME thấp luôn an toàn hơn | Quá thấp có thể tạo gánh nặng và hành vi password yếu |
| Password rollover dùng cho admin accounts | Tính năng thiết kế cho application service accounts; admin users bị giới hạn |
| ALTER PROFILE thay đổi session hiện tại | Chỉ session mới nhận profile changes |
| Profile thay thế Database Resource Manager | Resource Manager linh hoạt hơn cho workload governance |
| DEFAULT giống UNLIMITED | DEFAULT kế thừa giá trị từ profile DEFAULT |

## 25. Checklist thiết kế profile

**Tài khoản và phạm vi**

- User thuộc nhóm ứng dụng, analyst, batch hay admin?
- Có cần profile riêng không?
- User đang ở CDB root hay PDB?
- Profile là common hay local?
- Có bao nhiêu application nodes và connection pools?

**Password policy**

- Số lần đăng nhập sai tối đa là bao nhiêu?
- Lock time có phù hợp quy trình hỗ trợ không?
- Password lifetime và grace period có phù hợp loại account?
- Reuse time và reuse max đã cấu hình đồng thời chưa?
- Password verify function có tồn tại và hoạt động không?
- Inactive account policy có phù hợp không?
- Service account có cần gradual rollover không?

**Resource limits**

- RESOURCE_LIMIT có đang TRUE không?
- SESSIONS_PER_USER có đủ cho tổng pool không?
- CPU_PER_CALL và CPU_PER_SESSION dựa trên workload đo được chưa?
- Logical reads limits có phù hợp query thực tế không?
- IDLE_TIME có xung đột với connection pool không?
- CONNECT_TIME có cắt session dài không mong muốn không?
- Có cần Database Resource Manager thay cho hard limit không?

**Triển khai**

- Đã ghi nhận profile hiện tại chưa?
- Đã thử trên staging/lab chưa?
- Đã test bằng session mới chưa?
- Có rollback profile values không?
- Có cảnh báo account lock/password expiry không?
- Có monitoring sau triển khai không?

## 26. Bài thực hành tổng hợp

Lab này tạo profile riêng cho application account, gán profile, kiểm tra dictionary và thử password/resource parameters. Dùng schema lab và tài khoản không có quyền quản trị.

### Bước 1 — Tạo profile

~~~sql
CREATE PROFILE profile_lab LIMIT
    SESSIONS_PER_USER 3
    CPU_PER_CALL 3000
    CONNECT_TIME 120
    IDLE_TIME 10
    LOGICAL_READS_PER_CALL 100000
    FAILED_LOGIN_ATTEMPTS 4
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7
    PASSWORD_REUSE_TIME 180
    PASSWORD_REUSE_MAX 5;
~~~

### Bước 2 — Gán cho user lab

~~~sql
ALTER USER lab_user PROFILE profile_lab;
~~~

Nếu LAB_USER chưa tồn tại, DBA tạo user trong schema lab với password provisioning an toàn rồi gán profile.

### Bước 3 — Kiểm tra profile

~~~sql
SELECT
    profile,
    resource_name,
    resource_type,
    limit
FROM dba_profiles
WHERE profile = 'PROFILE_LAB'
ORDER BY resource_type, resource_name;
~~~

### Bước 4 — Kiểm tra user assignment

~~~sql
SELECT username, profile, account_status
FROM dba_users
WHERE username = 'LAB_USER';
~~~

### Bước 5 — Kiểm tra RESOURCE_LIMIT

~~~sql
SELECT name, value
FROM v$parameter
WHERE name = 'resource_limit';
~~~

Chỉ bật bằng ALTER SYSTEM khi có quyền và đã được phép:

~~~sql
ALTER SYSTEM SET resource_limit = TRUE;
~~~

### Bước 6 — Kiểm tra password status

~~~sql
SELECT
    username,
    account_status,
    lock_date,
    expiry_date,
    profile
FROM dba_users
WHERE username = 'LAB_USER';
~~~

### Bước 7 — Kiểm tra session

~~~sql
SELECT
    sid,
    serial#,
    username,
    status,
    profile,
    last_call_et
FROM v$session
WHERE username = 'LAB_USER';
~~~

### Bước 8 — Thử ALTER PROFILE

~~~sql
ALTER PROFILE profile_lab LIMIT
    IDLE_TIME 15
    SESSIONS_PER_USER 4;
~~~

Tạo session mới bằng LAB_USER để kiểm tra profile mới. Session đã mở trước thay đổi không tự nhận giá trị mới.

### Bước 9 — Dọn lab (tùy chọn)

~~~sql
ALTER USER lab_user PROFILE DEFAULT;
DROP PROFILE profile_lab;
~~~

Nếu profile vẫn được gán cho user khác, phải xử lý assignment trước hoặc dùng CASCADE theo change process. Chỉ drop object thuộc lab.

## 27. Câu hỏi tự kiểm tra

1. Profile trong Oracle là gì?
2. Profile khác role ở mục đích nào?
3. Một user có thể được gán bao nhiêu profile tại một thời điểm?
4. Password parameters khác resource parameters thế nào?
5. RESOURCE_LIMIT điều khiển điều gì?
6. Password parameters có bị RESOURCE_LIMIT tắt không?
7. DEFAULT khác UNLIMITED thế nào?
8. FAILED_LOGIN_ATTEMPTS và PASSWORD_LOCK_TIME phối hợp ra sao?
9. PASSWORD_LIFE_TIME và PASSWORD_GRACE_TIME khác nhau thế nào?
10. Khi nào xuất hiện ORA-28002 và ORA-28001?
11. PASSWORD_REUSE_TIME và PASSWORD_REUSE_MAX cần cấu hình thế nào?
12. Nếu một reuse parameter là UNLIMITED còn parameter kia hữu hạn thì sao?
13. Nếu cả hai reuse parameters đều UNLIMITED thì sao?
14. PASSWORD_VERIFY_FUNCTION dùng để làm gì?
15. Password verification function phải nằm trong schema nào?
16. INACTIVE_ACCOUNT_TIME đo khoảng thời gian nào?
17. PASSWORD_ROLLOVER_TIME giải quyết vấn đề gì?
18. Trong rollover period, password nào có thể đăng nhập?
19. PASSWORD_ROLLOVER_TIME có dùng cho administrative users không?
20. SESSIONS_PER_USER giới hạn điều gì?
21. CPU_PER_SESSION khác CPU_PER_CALL thế nào?
22. LOGICAL_READS_PER_CALL đo gì?
23. IDLE_TIME có kill query đang chạy lâu không?
24. CONNECT_TIME khác IDLE_TIME thế nào?
25. PRIVATE_SGA quan trọng với kiến trúc nào?
26. COMPOSITE_LIMIT được tính từ những resource nào?
27. Vượt call-level limit khác session-level limit thế nào?
28. Thay đổi profile có áp dụng session đang mở không?
29. Vì sao profile cần phối hợp với connection pool?
30. Khi nào nên dùng Database Resource Manager?

**Gợi ý trả lời:**

1. Tập password/resource limits gán cho database user.
2. Role gom privileges; profile gom password/resource policies.
3. Một.
4. Password parameters luôn được áp dụng; resource limits cần RESOURCE_LIMIT TRUE.
5. Bật/tắt enforcement của resource limits trong profile.
6. Không; password management luôn hoạt động.
7. DEFAULT kế thừa từ profile DEFAULT; UNLIMITED không đặt giới hạn.
8. Sau số lần login sai liên tiếp, account bị khóa trong thời gian PASSWORD_LOCK_TIME.
9. LIFE_TIME là thời hạn mật khẩu; GRACE_TIME là khoảng cảnh báo/cho phép đổi trước khi hết hạn hoàn toàn.
10. ORA-28002 là cảnh báo sắp hết hạn; ORA-28001 là đã hết hạn.
11. Cả hai cần giá trị phù hợp để yêu cầu đồng thời thời gian chờ và số lần đổi.
12. Không thể reuse password cũ.
13. Oracle bỏ qua cả hai giới hạn và password có thể reuse.
14. Kiểm tra độ phức tạp/chất lượng password.
15. SYS.
16. Số ngày liên tiếp không có login thành công.
17. Cho phép ứng dụng chuyển dần từ password cũ sang password mới.
18. Cả password cũ và mới trong khoảng rollover.
19. Không; được thiết kế cho application service accounts.
20. Số session đồng thời của user.
21. Một cái tính tổng CPU trong session; một cái tính CPU cho một call.
22. Số data blocks đọc trong một call.
23. Không; long-running query không bị tính là idle giữa các call.
24. CONNECT_TIME tính tổng thời gian session; IDLE_TIME tính khoảng không có call.
25. Shared Server.
26. CPU_PER_SESSION, CONNECT_TIME, LOGICAL_READS_PER_SESSION và PRIVATE_SGA theo trọng số.
27. Call-level rollback statement và giữ session; session-level limit có thể khiến session không tiếp tục làm việc.
28. Không; session mới nhận thay đổi.
29. Database có thể kết thúc session idle/old khiến pool giữ stale connection hoặc không đủ connection.
30. Khi cần phân phối ưu tiên và quản lý workload linh hoạt hơn các hard limits của profile.

## Tài liệu Oracle tham khảo

- [Oracle Database 19c SQL Language Reference — CREATE PROFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-PROFILE.html): cú pháp và semantics của password/resource parameters.
- [Oracle Database 19c SQL Language Reference — ALTER PROFILE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-PROFILE.html): thay đổi profile và phạm vi áp dụng.
- [Oracle Database 19c SQL Language Reference — ALTER RESOURCE COST](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-RESOURCE-COST.html): trọng số cho COMPOSITE_LIMIT.
- [Oracle Database 19c Database Security Guide — Configuring User Resource Limits](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/configuring-user-resource-limits.html): profile resource limits, RESOURCE_LIMIT và cách thực thi.
- [Oracle Database 19c Database Security Guide — Using a Password Management Policy](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/using-password-management-policy.html): password lifetime, lock, reuse, verify function và inactive account.
- [Oracle Database 19c Database Security Guide — Managing Gradual Database Password Rollover for Applications](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/managing-gradual-database-password-rollover-applications.html): password rollover cho service account.
- [Oracle Database 19c Database Reference — RESOURCE_LIMIT](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/RESOURCE_LIMIT.html): tham số bật/tắt resource enforcement.
- [Oracle Database 19c Database Reference — DBA_PROFILES](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_PROFILES.html): profile parameters hiện hành.
- [Oracle Database 19c Database Reference — DBA_USERS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/DBA_USERS.html): profile assignment, account status và password expiry.
- [Oracle Database 19c Administrator's Guide — Managing Resources with Oracle Database Resource Manager](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/managing-resources-with-oracle-database-resource-manager.html): quản lý workload và tài nguyên nâng cao.

**Nguyên tắc cần nhớ:** Profile gắn password policy và resource limits với database user. Password parameters luôn được áp dụng; resource parameters cần RESOURCE_LIMIT = TRUE. FAILED_LOGIN_ATTEMPTS, PASSWORD_LOCK_TIME, PASSWORD_LIFE_TIME, PASSWORD_GRACE_TIME, PASSWORD_REUSE_TIME, PASSWORD_REUSE_MAX và PASSWORD_VERIFY_FUNCTION tạo nên password lifecycle. SESSIONS_PER_USER, CPU, logical reads, CONNECT_TIME và IDLE_TIME giới hạn việc dùng tài nguyên theo session/call. PASSWORD_ROLLOVER_TIME giúp đổi mật khẩu service account theo từng giai đoạn. Hãy đo workload trước khi đặt ngưỡng, phối hợp profile với connection pool và dùng Database Resource Manager khi cần quản trị workload linh hoạt.
