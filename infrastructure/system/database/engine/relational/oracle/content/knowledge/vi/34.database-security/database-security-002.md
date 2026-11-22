# CREATE USER, xác thực, khóa tài khoản và quản lý vòng đời mật khẩu

Trong Oracle Database, quản lý người dùng là một phần cốt lõi của bảo mật. DBA cần xác định ai được kết nối, Oracle xác thực danh tính đó bằng cách nào, tài khoản được phép làm gì, khi nào tài khoản bị khóa và thông tin xác thực được thay đổi ra sao trong suốt thời gian sử dụng.

Các khái niệm này liên quan chặt chẽ nhưng không đồng nhất:

- **User (người dùng):** danh tính được Oracle quản lý để xác thực và gán quyền.
- **Schema:** không gian tên chứa các đối tượng thuộc sở hữu của user, chẳng hạn bảng, view, sequence, procedure và package. Khi tạo một user thông thường, Oracle đồng thời tạo schema cùng tên; schema không phải là một tài khoản đăng nhập riêng.
- **Authentication (xác thực):** xác minh danh tính người hoặc ứng dụng đang kết nối.
- **Authorization (phân quyền):** quyết định danh tính đã xác thực được phép thực hiện thao tác nào.
- **Account status (trạng thái tài khoản):** cho biết tài khoản đang mở, bị khóa hay cần đổi mật khẩu.

Một user có thể tồn tại nhưng chưa được phép tạo session. Một tài khoản có thể xác thực thành công nhưng vẫn không có quyền đọc một bảng cụ thể. Vì vậy, tạo user, cấp quyền đăng nhập và cấp quyền trên dữ liệu là các bước riêng biệt cần được quản lý có chủ đích.

## 1. Chuẩn bị trước khi tạo user

Trước khi chạy `CREATE USER`, cần xác định mục đích của tài khoản:

| Loại tài khoản | Mục đích | Quyền thường cần |
|---|---|---|
| Schema owner | Sở hữu và triển khai các đối tượng của ứng dụng. | `CREATE SESSION` và một tập quyền tạo đối tượng có giới hạn; quota trên tablespace cần thiết. |
| Application runtime | Được ứng dụng dùng để truy cập dữ liệu khi chạy. | `CREATE SESSION` và quyền đối tượng cụ thể như `SELECT`, `INSERT`, `UPDATE`, `EXECUTE`. |
| Reporting user | Chạy báo cáo hoặc truy vấn đọc. | `CREATE SESSION` và quyền đọc đúng các view hoặc bảng được phê duyệt. |
| DBA hoặc tài khoản vận hành | Quản trị database theo nhiệm vụ. | Các quyền quản trị cần thiết, được cấp riêng và kiểm soát chặt. |

Không nên dùng chung một tài khoản cho người phát triển, ứng dụng runtime và tác vụ quản trị. Khi nhiều thành phần dùng chung danh tính, audit khó xác định ai thực hiện thao tác và việc thu hồi quyền có thể ảnh hưởng đến nhiều hệ thống.

Trước khi tạo user, hãy kiểm tra:

1. Đang kết nối đúng database và đúng pluggable database (PDB).
2. Tên user chưa được sử dụng và phù hợp quy ước đặt tên.
3. Default tablespace, temporary tablespace và quota đã được DBA chuẩn bị.
4. Profile chứa chính sách mật khẩu đã tồn tại nếu user cần dùng profile riêng.
5. Người thực hiện có quyền `CREATE USER` trong phạm vi container phù hợp.

Trong môi trường Oracle multitenant, user tạo trong PDB thường là **local user**, chỉ tồn tại trong PDB đó. Common user được tạo ở CDB root và có phạm vi container rộng hơn; theo cấu hình mặc định, tên common user thường phải có tiền tố `C##`. Trước khi tạo tài khoản, có thể kiểm tra container hiện tại:

```sql
SELECT SYS_CONTEXT('USERENV', 'CON_NAME') AS current_container
FROM dual;
```

Trong SQL*Plus, `SHOW CON_NAME` cũng hiển thị container hiện tại. Tạo nhầm user trong root thay vì PDB ứng dụng có thể làm thay đổi phạm vi và cách quản trị tài khoản, nên phải xác nhận container trước khi thực hiện DDL.

## 2. Tạo user bằng `CREATE USER`

### 2.1. Cú pháp và các thuộc tính chính

Một dạng cú pháp phổ biến khi tạo user xác thực bằng mật khẩu là:

```sql
CREATE USER username
    IDENTIFIED BY password
    DEFAULT TABLESPACE tablespace_name
    TEMPORARY TABLESPACE temp_tablespace_name
    QUOTA quota_size ON tablespace_name
    PROFILE profile_name
    PASSWORD EXPIRE;
```

Đây là các thành phần có thể chọn theo nhu cầu; không phải mọi user đều cần khai báo tất cả.

| Thành phần | Ý nghĩa |
|---|---|
| `username` | Tên danh tính Oracle. Tên không đặt trong dấu ngoặc kép thường được chuẩn hóa thành chữ hoa. |
| `IDENTIFIED BY` | Khai báo mật khẩu dùng cho xác thực database. Mật khẩu phân biệt chữ hoa và chữ thường trong các cấu hình Oracle hiện đại. |
| `DEFAULT TABLESPACE` | Tablespace mặc định cho các segment mà user tạo khi không chỉ định tablespace khác. |
| `TEMPORARY TABLESPACE` | Tablespace dùng cho các thao tác cần vùng tạm như sort hoặc hash khi cần ghi ra TEMP. |
| `QUOTA` | Giới hạn dung lượng user được phép cấp phát trong một tablespace. |
| `PROFILE` | Gán profile quy định chính sách mật khẩu và, nếu được bật, giới hạn tài nguyên. |
| `PASSWORD EXPIRE` | Đánh dấu mật khẩu hết hạn để user phải đổi mật khẩu khi đăng nhập theo cơ chế client hỗ trợ. |

`DEFAULT TABLESPACE` không tự động cấp quyền tạo mọi loại đối tượng và cũng không thay thế quota. Nếu user cần tạo bảng, user phải có system privilege phù hợp và quota trên tablespace, hoặc được cấp `UNLIMITED TABLESPACE` khi thực sự có lý do. Không nên cấp quyền không giới hạn chỉ để tránh lỗi quota.

### 2.2. Ví dụ tạo schema owner

Giả sử database đã có tablespace `APP_DATA`, temporary tablespace `TEMP` và profile `APP_PASSWORD_POLICY`. Một tài khoản sở hữu schema ứng dụng có thể được tạo như sau:

```sql
CREATE USER app_owner
    IDENTIFIED BY "ReplaceWithSecretFromVault"
    DEFAULT TABLESPACE app_data
    TEMPORARY TABLESPACE temp
    QUOTA 500M ON app_data
    PROFILE app_password_policy
    PASSWORD EXPIRE;

GRANT CREATE SESSION TO app_owner;
GRANT CREATE TABLE, CREATE VIEW, CREATE SEQUENCE,
      CREATE PROCEDURE TO app_owner;
```

Chuỗi mật khẩu trong ví dụ chỉ là placeholder để minh họa cú pháp, không phải mật khẩu nên dùng. Khi triển khai thật, hãy tạo mật khẩu ngẫu nhiên duy nhất và đưa vào qua quy trình cấp phát bí mật an toàn. Tránh lưu mật khẩu thật trong file SQL, Git, log triển khai hoặc lệnh có thể xuất hiện trong shell history.

`CREATE USER` tạo danh tính và schema, nhưng **không tự cấp `CREATE SESSION`**. Nếu chưa có quyền này, user không thể mở database session thông thường. Các system privilege như `CREATE TABLE` chỉ cho phép tạo loại đối tượng tương ứng trong schema của user; quota vẫn giới hạn dung lượng segment được cấp phát.

### 2.3. Tách schema owner khỏi tài khoản runtime

Ứng dụng đang chạy thường không cần quyền tạo hoặc thay đổi cấu trúc database. Có thể tạo một user runtime riêng:

```sql
CREATE USER app_runtime
    IDENTIFIED BY "ReplaceWithAnotherSecretFromVault"
    DEFAULT TABLESPACE app_data
    TEMPORARY TABLESPACE temp
    PROFILE app_password_policy;

GRANT CREATE SESSION TO app_runtime;
GRANT SELECT, INSERT, UPDATE
    ON app_owner.orders TO app_runtime;
GRANT SELECT
    ON app_owner.customers TO app_runtime;
```

User `APP_RUNTIME` không cần `CREATE TABLE`, `CREATE USER`, `ALTER SYSTEM` hoặc quyền DBA để thực hiện các thao tác ứng dụng đã nêu. Các quyền trên bảng được cấp trực tiếp trong ví dụ để dễ nhìn; với hệ thống có nhiều tài khoản, có thể gom quyền đối tượng vào role theo chức năng rồi cấp role đó cho runtime user.

Ví dụ:

```sql
CREATE ROLE app_order_reader;
GRANT SELECT ON app_owner.orders TO app_order_reader;
GRANT SELECT ON app_owner.customers TO app_order_reader;
GRANT app_order_reader TO app_reporting;
```

Role giúp quản lý tập quyền theo nhiệm vụ. Cần xem xét quyền thực tế mà user nhận từ role, quyền được cấp trực tiếp và các role lồng nhau; không nên cấp `DBA`, `RESOURCE` hoặc role rộng chỉ vì ứng dụng gặp lỗi thiếu quyền.

## 3. Các phương thức xác thực

Oracle có thể xác thực user bằng mật khẩu database hoặc dựa vào một hệ thống danh tính bên ngoài. Phương thức được chọn ảnh hưởng đến nơi quản lý bí mật, chính sách mật khẩu và cách thu hồi quyền truy cập.

### 3.1. Xác thực bằng mật khẩu database

Đây là cách phổ biến cho user ứng dụng hoặc user đăng nhập trực tiếp:

```sql
CREATE USER app_user
    IDENTIFIED BY "ReplaceWithSecretFromVault";
```

Oracle kiểm tra mật khẩu theo cơ chế xác thực database. Mật khẩu của Oracle phân biệt chữ hoa và chữ thường trong các cấu hình hiện đại. Không nên tắt tính năng phân biệt hoa thường để tương thích với ứng dụng cũ; hãy cập nhật ứng dụng để xử lý mật khẩu đúng cách.

Kết nối thường có dạng:

```text
username/password@service_name
```

Không đưa mật khẩu thật vào command line, chuỗi kết nối được ghi log hoặc file cấu hình không được bảo vệ. Với ứng dụng, hãy lấy bí mật từ secret manager hoặc cơ chế quản lý credential của nền tảng triển khai.

### 3.2. Xác thực bên ngoài (external authentication)

Với external authentication, Oracle dựa vào hệ thống xác thực bên ngoài đã được cấu hình thay vì kiểm tra mật khẩu database của user. Một ví dụ về khai báo user là:

```sql
CREATE USER ops_user IDENTIFIED EXTERNALLY;
```

Trong một số cấu hình, danh tính bên ngoài có thể dựa trên hệ điều hành; cấu hình Oracle Net và các tham số liên quan quyết định cách ánh xạ danh tính. Không nên bật xác thực hệ điều hành từ xa một cách tùy tiện vì mức tin cậy phụ thuộc vào máy khách, hệ điều hành và cấu hình mạng.

### 3.3. Xác thực toàn cục (global authentication)

Trong môi trường tích hợp directory service hoặc enterprise identity, user có thể được ánh xạ với danh tính toàn cục:

```sql
CREATE USER directory_user
    IDENTIFIED GLOBALLY AS 'CN=Directory User,OU=People,DC=example,DC=com';
```

Giá trị định danh trong ví dụ phải khớp cấu trúc directory và cấu hình xác thực của tổ chức. Việc kết nối còn phụ thuộc dịch vụ directory, Oracle Net và cấu hình bảo mật tương ứng.

Kerberos, RADIUS hoặc các cơ chế xác thực mạng khác cũng cần cấu hình ở lớp hạ tầng. Chỉ chạy `CREATE USER` không tự cài đặt hay kích hoạt các dịch vụ xác thực đó.

### 3.4. Xác thực và phân quyền là hai bước khác nhau

Một user xác thực thành công vẫn có thể gặp lỗi khi truy cập dữ liệu vì chưa được cấp quyền. Ví dụ:

```sql
GRANT CREATE SESSION TO app_user;
GRANT SELECT ON app_owner.orders TO app_user;
```

`CREATE SESSION` cho phép mở session; `SELECT` trên `APP_OWNER.ORDERS` cho phép đọc bảng cụ thể. Hai quyền có mục đích khác nhau. Khi điều tra lỗi đăng nhập, hãy kiểm tra xác thực và trạng thái tài khoản trước; khi điều tra lỗi truy cập đối tượng, hãy kiểm tra grants và role.

## 4. Profile và chính sách mật khẩu

Profile là nơi tập trung một số giới hạn áp dụng cho user. Profile có thể quy định số lần đăng nhập sai, thời gian khóa, tuổi thọ mật khẩu, thời gian gia hạn và quy tắc tái sử dụng mật khẩu.

### 4.1. Các giới hạn mật khẩu thường dùng

| Tham số | Tác dụng |
|---|---|
| `FAILED_LOGIN_ATTEMPTS` | Số lần đăng nhập sai liên tiếp trước khi Oracle khóa tài khoản theo profile. |
| `PASSWORD_LOCK_TIME` | Thời gian tài khoản bị khóa sau khi vượt ngưỡng đăng nhập sai; đơn vị là ngày. |
| `PASSWORD_LIFE_TIME` | Số ngày mật khẩu có hiệu lực trước khi hết hạn. |
| `PASSWORD_GRACE_TIME` | Số ngày gia hạn sau khi mật khẩu hết hạn; trong thời gian này user có thể được cảnh báo và yêu cầu đổi mật khẩu. |
| `PASSWORD_REUSE_TIME` | Khoảng thời gian phải chờ trước khi dùng lại mật khẩu cũ. |
| `PASSWORD_REUSE_MAX` | Số lần đổi mật khẩu tối thiểu trước khi có thể dùng lại mật khẩu cũ. |
| `PASSWORD_VERIFY_FUNCTION` | Hàm kiểm tra mật khẩu mới, chẳng hạn độ dài và mức độ khác biệt với mật khẩu cũ. |
| `INACTIVE_ACCOUNT_TIME` | Trên các phiên bản hỗ trợ, khóa user không hoạt động trong khoảng thời gian được cấu hình. Cần xác nhận phiên bản và cách tính hoạt động trước khi áp dụng. |

Giá trị `UNLIMITED` có ý nghĩa riêng theo từng tham số. Với `PASSWORD_REUSE_TIME` và `PASSWORD_REUSE_MAX`, cần cấu hình kết hợp theo tài liệu phiên bản Oracle đang dùng; khi cả hai có giới hạn hữu hạn, điều kiện thời gian và số lần đổi đều có ảnh hưởng đến khả năng tái sử dụng. Không nên đặt một giá trị tùy ý mà không hiểu tác động đến quy trình đổi mật khẩu.

### 4.2. Tạo profile mẫu

Ví dụ sau minh họa một chính sách có ngưỡng đăng nhập sai, thời gian khóa, tuổi thọ mật khẩu và thời gian gia hạn:

```sql
CREATE PROFILE app_password_policy LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7
    PASSWORD_REUSE_TIME 365
    PASSWORD_REUSE_MAX 10
    PASSWORD_VERIFY_FUNCTION ORA12C_STRONG_VERIFY_FUNCTION;
```

Các con số trong ví dụ là giá trị minh họa, không phải chuẩn bắt buộc cho mọi tổ chức. `PASSWORD_LOCK_TIME 1` tương ứng một ngày. Chính sách thực tế phải phù hợp yêu cầu bảo mật, quy định nội bộ, loại tài khoản và cách vận hành ứng dụng.

`ORA12C_STRONG_VERIFY_FUNCTION` là tên hàm kiểm tra mật khẩu được cung cấp trong một số bộ cài Oracle thông qua script quản lý mật khẩu mẫu. Hãy xác nhận hàm tồn tại trong database và phù hợp phiên bản trước khi gán. Nếu tổ chức dùng hàm tùy chỉnh, DBA cần triển khai hàm theo giao diện Oracle yêu cầu và kiểm thử các trường hợp mật khẩu hợp lệ, không hợp lệ, đổi mật khẩu và lỗi thực thi.

Gán profile cho user:

```sql
ALTER USER app_user PROFILE app_password_policy;
```

Profile `DEFAULT` được áp dụng cho user không được gán profile riêng. Không nên mặc định rằng các tham số của profile `DEFAULT` phù hợp với chính sách tổ chức; DBA cần kiểm tra giá trị thực tế trong database.

### 4.3. Kiểm tra và thay đổi profile

Có thể xem giới hạn của profile bằng các view từ điển dữ liệu:

```sql
SELECT profile, resource_name, limit
FROM dba_profiles
WHERE profile = 'APP_PASSWORD_POLICY'
ORDER BY resource_type, resource_name;
```

Để thay đổi giới hạn, dùng `ALTER PROFILE`:

```sql
ALTER PROFILE app_password_policy LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1
    PASSWORD_GRACE_TIME 7;
```

Thay đổi profile có thể ảnh hưởng đến nhiều user đang dùng profile đó. Trước khi sửa, hãy liệt kê các user được gán profile, đánh giá ảnh hưởng đến ứng dụng và thông báo theo quy trình vận hành. Tham số quản lý mật khẩu được Oracle áp dụng theo cơ chế profile; một số giới hạn tài nguyên khác của profile có thể còn phụ thuộc cấu hình `RESOURCE_LIMIT` và phiên bản.

### 4.4. Chính sách mật khẩu cần cân bằng với cách vận hành

Mật khẩu nên đủ dài, duy nhất cho từng tài khoản và được tạo ngẫu nhiên bằng công cụ quản lý bí mật. Hàm kiểm tra mật khẩu có thể ngăn mật khẩu quá ngắn, quá phổ biến hoặc quá giống tên tài khoản. Việc buộc đổi mật khẩu theo chu kỳ quá ngắn có thể khiến người dùng chọn quy luật dễ đoán hoặc tái sử dụng biến thể của mật khẩu cũ.

Tổ chức cần chọn tuổi thọ mật khẩu theo yêu cầu tuân thủ và mô hình rủi ro. Với tài khoản dịch vụ, nên kết hợp secret manager, quyền tối thiểu, giám sát và quy trình xoay vòng có kiểm soát. Không nên đặt `PASSWORD_LIFE_TIME UNLIMITED` chỉ để tránh gián đoạn ứng dụng; nếu có ngoại lệ, cần có lý do, biện pháp bù và thời hạn rà soát rõ ràng.

## 5. Khóa và mở khóa tài khoản

Oracle có thể khóa tài khoản tự động sau nhiều lần đăng nhập sai hoặc DBA khóa thủ công. Hai trường hợp này cần được phân biệt khi xử lý sự cố.

### 5.1. Khóa thủ công

Khi user nghỉ việc, ứng dụng bị dừng, credential có dấu hiệu bị lộ hoặc cần tạm ngừng truy cập, DBA có thể khóa tài khoản:

```sql
ALTER USER app_user ACCOUNT LOCK;
```

Lệnh này ngăn user mở session mới. Khóa tài khoản không đồng nghĩa với việc mọi session đã kết nối bị kết thúc ngay lập tức. Nếu cần ngăn hoạt động đang diễn ra, DBA phải kiểm tra session hiện tại và xử lý theo quy trình vận hành, có cân nhắc giao dịch đang chạy và ảnh hưởng ứng dụng.

### 5.2. Mở khóa

Sau khi xác minh nguyên nhân và được phê duyệt, DBA có thể mở khóa:

```sql
ALTER USER app_user ACCOUNT UNLOCK;
```

Nếu tài khoản bị khóa do hết ngưỡng đăng nhập sai, cần xác định nguồn phát sinh lỗi trước khi mở khóa. Một ứng dụng vẫn giữ mật khẩu cũ trong connection pool có thể tiếp tục đăng nhập sai và khóa tài khoản trở lại.

### 5.3. Khóa tự động theo profile

Ví dụ profile có:

```sql
FAILED_LOGIN_ATTEMPTS 5
PASSWORD_LOCK_TIME 1
```

Khi số lần đăng nhập sai vượt giới hạn, Oracle khóa user theo thời gian đã cấu hình. Với giới hạn thời gian hữu hạn, tài khoản có thể tự mở khóa khi thời gian khóa kết thúc. Với cấu hình khóa không giới hạn, DBA có thể phải mở khóa thủ công. Hành vi và trạng thái cụ thể cần được xác nhận bằng profile và phiên bản đang chạy.

### 5.4. Phân biệt khóa tài khoản và hết hạn mật khẩu

Khóa tài khoản ngăn đăng nhập. Hết hạn mật khẩu yêu cầu đổi mật khẩu theo chính sách. Một user có thể đồng thời có trạng thái khóa và hết hạn; mở khóa không nhất thiết giải quyết yêu cầu đổi mật khẩu.

Các trạng thái thường gặp trong `DBA_USERS.ACCOUNT_STATUS` gồm:

| Trạng thái | Ý nghĩa khái quát |
|---|---|
| `OPEN` | Tài khoản đang mở và không có trạng thái hết hạn hoặc khóa. |
| `LOCKED` | Tài khoản bị khóa thủ công hoặc đang ở trạng thái khóa không tự hết hạn. |
| `LOCKED(TIMED)` | Tài khoản bị khóa theo thời gian, thường liên quan đến số lần đăng nhập sai. |
| `EXPIRED` | Mật khẩu đã hết hạn và cần được đổi. |
| `EXPIRED(GRACE)` | Mật khẩu đã hết hạn nhưng user đang trong thời gian gia hạn. |

Oracle có thể hiển thị trạng thái kết hợp khi user vừa bị khóa vừa hết hạn. Hãy đọc trạng thái thực tế thay vì chỉ dựa trên một cột ngày.

## 6. Đổi mật khẩu và quản lý vòng đời credential

### 6.1. Đổi mật khẩu theo yêu cầu

DBA có thể đặt mật khẩu mới cho user bằng:

```sql
ALTER USER app_user IDENTIFIED BY "NewUniqueSecretFromVault";
```

Người dùng có thể đổi mật khẩu của chính mình bằng công cụ client hỗ trợ. Trong SQL*Plus, lệnh `PASSWORD` mở lời nhắc nhập mật khẩu cũ và mới, giúp tránh ghi trực tiếp mật khẩu vào câu SQL:

```text
SQL> PASSWORD
Changing password for CURRENT_USER
Old password:
New password:
Retype new password:
```

Đây là lệnh của SQL*Plus, không phải câu lệnh SQL dùng trong mọi client. Với công cụ khác, hãy dùng chức năng đổi mật khẩu an toàn tương ứng. Không gửi mật khẩu thật trong ticket, chat, email hoặc log.

### 6.2. Buộc đổi mật khẩu ở lần đăng nhập tiếp theo

Khi cấp tài khoản mới hoặc sau khi DBA đặt lại mật khẩu, có thể yêu cầu user tự đổi mật khẩu ở lần đăng nhập kế tiếp:

```sql
ALTER USER app_user PASSWORD EXPIRE;
```

Tùy client và ứng dụng, user sẽ nhận thông báo mật khẩu hết hạn và được yêu cầu đổi trước khi tiếp tục. Tài khoản dịch vụ không có người tương tác có thể không xử lý được luồng đổi mật khẩu này; cần lập kế hoạch xoay vòng credential qua secret manager và quy trình triển khai ứng dụng.

### 6.3. Vòng đời dành cho tài khoản con người

Một quy trình quản lý user cá nhân có thể gồm:

1. **Cấp phát:** tạo user riêng, xác định phương thức xác thực, gán profile và chỉ cấp role cần thiết.
2. **Kích hoạt:** cấp quyền đăng nhập, chuyển credential qua kênh an toàn và yêu cầu đổi mật khẩu khởi tạo.
3. **Sử dụng:** theo dõi trạng thái, đăng nhập sai, quyền được cấp và hoạt động bất thường.
4. **Đổi hoặc đặt lại:** thay mật khẩu khi đến hạn theo chính sách, khi người dùng quên mật khẩu hoặc khi có dấu hiệu lộ credential.
5. **Tạm ngừng:** khóa tài khoản khi có yêu cầu điều tra hoặc tạm dừng quyền truy cập.
6. **Thu hồi:** khi người dùng rời tổ chức hoặc không còn nhiệm vụ, khóa tài khoản, thu hồi grants/roles và xử lý session còn hoạt động theo quy trình.
7. **Lưu trữ hoặc xóa:** chỉ xóa user sau khi xác nhận quyền sở hữu đối tượng, phụ thuộc ứng dụng, yêu cầu lưu trữ và phê duyệt.

### 6.4. Vòng đời dành cho tài khoản dịch vụ

Tài khoản ứng dụng có vòng đời khác tài khoản con người vì credential thường được lưu trong secret manager hoặc cấu hình triển khai và được dùng bởi connection pool.

- Tạo tài khoản runtime riêng cho từng ứng dụng hoặc từng ranh giới tin cậy cần thiết.
- Cấp quyền trên đúng bảng, view, sequence hoặc package mà ứng dụng sử dụng.
- Lưu credential trong secret manager; tránh hard-code trong source code, image container hoặc file cấu hình công khai.
- Khi xoay vòng, cập nhật secret và cấu hình kết nối theo trình tự có kiểm soát; xác nhận instance mới đã dùng credential mới trước khi thu hồi credential cũ nếu nền tảng hỗ trợ quy trình chuyển tiếp.
- Kiểm tra connection pool, job scheduler, batch process và hệ thống dự phòng để tránh thành phần còn giữ mật khẩu cũ.
- Khi ứng dụng ngừng hoạt động, khóa tài khoản, xác nhận không còn kết nối hoặc job phụ thuộc, rồi thu hồi quyền và xử lý user theo quy trình.

Không nên chia sẻ một tài khoản dịch vụ giữa các ứng dụng không liên quan. Tách biệt danh tính giúp truy vết, giới hạn phạm vi ảnh hưởng khi credential bị lộ và xoay vòng độc lập.

## 7. Kiểm tra user, trạng thái và quyền đã cấp

Các view từ điển dữ liệu giúp DBA kiểm tra cấu hình thực tế. Các view `DBA_` thường yêu cầu quyền quản trị hoặc quyền đọc từ điển dữ liệu phù hợp; user thông thường có thể dùng các view `USER_` và `ALL_` trong phạm vi được phép.

### 7.1. Kiểm tra trạng thái tài khoản

```sql
SELECT
    username,
    account_status,
    authentication_type,
    profile,
    default_tablespace,
    temporary_tablespace,
    expiry_date,
    lock_date
FROM dba_users
WHERE username = UPPER(:username);
```

Các cột hữu ích gồm `ACCOUNT_STATUS`, `PROFILE`, `DEFAULT_TABLESPACE`, `TEMPORARY_TABLESPACE`, `EXPIRY_DATE` và `LOCK_DATE`. `AUTHENTICATION_TYPE` giúp nhận biết loại xác thực được Oracle ghi nhận. Các cột và giá trị có thể khác nhau theo phiên bản; hãy tham khảo data dictionary của phiên bản đang sử dụng.

### 7.2. Kiểm tra profile được gán

```sql
SELECT username, profile, account_status
FROM dba_users
WHERE profile = 'APP_PASSWORD_POLICY'
ORDER BY username;
```

Truy vấn này giúp xác định những user bị ảnh hưởng nếu DBA thay đổi profile. Trước khi chỉnh profile dùng chung, cần kiểm tra toàn bộ danh sách thay vì chỉ nhìn user đang được xử lý.

### 7.3. Kiểm tra system privilege, role và object privilege

```sql
SELECT grantee, privilege, admin_option
FROM dba_sys_privs
WHERE grantee = UPPER(:username)
ORDER BY privilege;

SELECT grantee, granted_role, default_role
FROM dba_role_privs
WHERE grantee = UPPER(:username)
ORDER BY granted_role;

SELECT grantee, owner, table_name, privilege, grantable
FROM dba_tab_privs
WHERE grantee = UPPER(:username)
ORDER BY owner, table_name, privilege;
```

Ba truy vấn cho thấy các system privilege, role và quyền đối tượng được cấp trực tiếp cho user. Để đánh giá quyền hiệu lực, cần xét thêm quyền nhận qua role, role lồng nhau, quyền `PUBLIC`, quyền được cấp thông qua chương trình có quyền định nghĩa và các cơ chế bảo mật khác của database.

## 8. Xử lý một số lỗi thường gặp

| Mã lỗi | Nguyên nhân thường gặp | Hướng kiểm tra |
|---|---|---|
| `ORA-01017` | Tên user hoặc mật khẩu không hợp lệ; đôi khi do kết nối nhầm service hoặc khác biệt cách gửi mật khẩu. | Xác nhận username, service name, kiểu chữ của mật khẩu và nguồn credential của ứng dụng. |
| `ORA-28000` | Tài khoản đang bị khóa. | Xem `DBA_USERS.ACCOUNT_STATUS`, `LOCK_DATE`, profile và nguồn đăng nhập sai trước khi mở khóa. |
| `ORA-28001` | Mật khẩu đã hết hạn. | Đổi mật khẩu theo quy trình; kiểm tra `PASSWORD_LIFE_TIME` và profile. |
| `ORA-28002` | Mật khẩu sắp hết hạn hoặc đang trong thời gian gia hạn theo profile. | Đổi mật khẩu trước khi hết thời gian gia hạn; kiểm tra `PASSWORD_GRACE_TIME`. |
| `ORA-28003` | Mật khẩu mới không vượt qua hàm xác minh. | Kiểm tra yêu cầu của `PASSWORD_VERIFY_FUNCTION` và chọn mật khẩu duy nhất, đủ mạnh. |
| `ORA-28007` | Mật khẩu mới không được phép tái sử dụng theo chính sách. | Kiểm tra `PASSWORD_REUSE_TIME`, `PASSWORD_REUSE_MAX` và chọn mật khẩu mới. |
| `ORA-01045` | User chưa có quyền `CREATE SESSION`. | Kiểm tra và chỉ cấp `GRANT CREATE SESSION` khi user được phép đăng nhập. |
| `ORA-01950` | User không có quota phù hợp trên tablespace khi cần cấp phát segment. | Kiểm tra quota và cấp giới hạn dung lượng cần thiết trên đúng tablespace. |

Không nên giải quyết lỗi bằng cách cấp role DBA hoặc `UNLIMITED TABLESPACE` một cách vội vàng. Hãy xác định quyền tối thiểu hoặc cấu hình cụ thể đang thiếu.

## 9. Thu hồi quyền và kết thúc vòng đời user

Khi một tài khoản không còn cần truy cập, bước đầu tiên thường là khóa user:

```sql
ALTER USER app_user ACCOUNT LOCK;
```

Sau đó kiểm tra session, job, kết nối từ ứng dụng, object ownership và các dependency. Nếu cần kết thúc session đang tồn tại, DBA phải xác định đúng session và dùng cơ chế quản trị session theo quy trình của hệ thống. Không giả định rằng khóa user đã tự ngắt mọi kết nối hiện tại.

Quyền có thể được thu hồi riêng:

```sql
REVOKE app_order_reader FROM app_user;
REVOKE SELECT ON app_owner.orders FROM app_user;
```

Nếu user có nhiều grants, cần rà soát cả quyền trực tiếp và quyền thông qua role. Với user sở hữu schema, việc xóa tài khoản có thể xóa các đối tượng thuộc sở hữu nếu dùng `CASCADE`:

```sql
DROP USER app_user CASCADE;
```

`DROP USER ... CASCADE` là thao tác phá hủy đối tượng trong schema. Chỉ thực hiện sau khi xác nhận backup, yêu cầu lưu trữ, dependency, quyền sở hữu và phê duyệt. Trong nhiều tình huống, khóa user và giữ schema trong thời gian lưu trữ là lựa chọn phù hợp hơn xóa ngay.

## 10. Các nguyên tắc vận hành an toàn

- Dùng tài khoản riêng cho từng người, ứng dụng và nhiệm vụ; tránh tài khoản dùng chung.
- Chỉ cấp `CREATE SESSION` cho user cần đăng nhập và cấp quyền dữ liệu ở phạm vi nhỏ nhất.
- Tách schema owner khỏi runtime user để ứng dụng không có quyền DDL không cần thiết.
- Dùng profile phù hợp cho nhóm tài khoản; rà soát các ngoại lệ, đặc biệt là tài khoản dịch vụ.
- Dùng mật khẩu dài, ngẫu nhiên, duy nhất; lưu trong secret manager và không ghi vào mã nguồn hoặc log.
- Theo dõi đăng nhập sai, tài khoản bị khóa, mật khẩu hết hạn và thay đổi quyền.
- Khi đổi credential dịch vụ, cập nhật mọi consumer và connection pool theo kế hoạch có thể kiểm chứng.
- Khi người dùng hoặc ứng dụng rời hệ thống, khóa tài khoản trước, thu hồi quyền và chỉ xóa schema sau khi đã đánh giá dependency.
- Trong CDB/PDB, luôn xác nhận container trước khi tạo, sửa hoặc khóa user.

## Kết luận

`CREATE USER` tạo danh tính và schema; `CREATE SESSION` cho phép mở kết nối; các system privilege, role và object privilege quyết định user được làm gì sau khi kết nối. Phương thức xác thực xác định nơi kiểm tra danh tính, còn profile kiểm soát nhiều quy tắc mật khẩu và khóa tài khoản. Quản lý vòng đời cần bao quát từ cấp phát, kích hoạt, đổi mật khẩu, khóa tạm thời đến thu hồi quyền và xử lý tài khoản khi không còn sử dụng. Khi kết hợp các bước này với quyền tối thiểu, secret manager, kiểm tra trạng thái và quy trình vận hành rõ ràng, DBA có thể kiểm soát truy cập Oracle an toàn và dễ truy vết hơn.
