# Quản lý bí mật, luân chuyển mật khẩu và tránh ghi dữ liệu nhạy cảm vào log trong Oracle

## 1. Vì sao quản lý bí mật là một phần của bảo mật database?

Một hệ thống Oracle có nhiều loại bí mật (secrets) ngoài mật khẩu của user database:
- Mật khẩu tài khoản ứng dụng, tài khoản tích hợp và tài khoản quản trị.
- Credential dùng cho database link, scheduler job, external job và công cụ backup.
- Mật khẩu hoặc khóa mở TDE keystore.
- Private key và certificate dùng cho TLS.
- API key, token và thông tin xác thực của dịch vụ cloud.
- Credential dùng bởi connection pool, ETL, monitoring và hệ thống triển khai.

Nếu bí mật bị lưu trong source code, file cấu hình, script, ticket hoặc log, người không có quyền truy cập database vẫn có thể lấy được thông tin để đăng nhập. Việc thay mật khẩu cũng không đơn giản là chạy `ALTER USER`: mọi ứng dụng, connection pool, job và tích hợp đang dùng credential đó phải được cập nhật đúng thời điểm.

Bài học thuộc chương **Bảo mật** của module **Database Engine Relational Oracle**. Nội dung tập trung vào ba năng lực:

1. **Quản lý bí mật:** xác định, lưu trữ, phân quyền, theo dõi và thu hồi credential/keys.
2. **Luân chuyển mật khẩu:** thay credential theo quy trình có kiểm soát, cập nhật tất cả consumer và xác nhận hoạt động.
3. **Bảo vệ log:** ghi đủ thông tin để điều tra nhưng không làm lộ mật khẩu, token, khóa hoặc dữ liệu nhạy cảm.

Mục tiêu không phải ghi mọi thứ để tiện debug. Mục tiêu là có thể truy vết ai làm gì, khi nào, ở đâu và kết quả ra sao mà không cần lưu giá trị bí mật.

## 2. Phân biệt secret, configuration và dữ liệu nghiệp vụ

Không phải mọi giá trị cấu hình đều là bí mật.

| Loại | Ví dụ | Cách xử lý |
|---|---|---|
| Secret | Password, API token, private key, TDE keystore password | Secret manager, wallet/keystore, quyền tối thiểu |
| Configuration | Hostname, port, service name, schema name | Configuration management; vẫn kiểm soát thay đổi |
| Identifier | Username, client ID, wallet alias | Có thể cần bảo vệ theo ngữ cảnh, không nhất thiết là secret |
| Sensitive data | Số định danh, thông tin tài chính, dữ liệu cá nhân | Phân loại, giảm thu thập, masking và access control |
| Public data | Tên service công khai, mã release | Có thể ghi log nếu cần |

Một connection string có thể chứa cả configuration và secret. Ví dụ, `host`, `port` và `service_name` thường không phải mật khẩu, nhưng phần username/password hoặc token trong URI là bí mật. Không log nguyên connection string khi không chắc nội dung.

### 2.1. Bí mật cần bảo vệ ở mọi trạng thái

Secret có thể xuất hiện:
- Khi tạo hoặc cấp phát.
- Khi truyền từ secret manager đến ứng dụng.
- Trong bộ nhớ của process.
- Trong file cấu hình hoặc cache.
- Trong câu SQL, bind variable hoặc command line.
- Trong log, trace, dump và bản backup.
- Trong quá trình rotation và thu hồi.

Mã hóa khi lưu trữ chỉ bảo vệ một phần vòng đời. Nếu ứng dụng ghi password ra log hoặc truyền qua kết nối không bảo vệ, encryption at rest không giải quyết được vấn đề đó.

### 2.2. Phân loại theo mức độ tác động

Một cách phân loại thực tế:
- **Critical:** SYS, SYSDBA, TDE master key, private key CA, credential có quyền quản trị toàn hệ thống.
- **High:** service account có quyền đọc/ghi dữ liệu nhạy cảm, credential của backup/replication.
- **Moderate:** tài khoản ứng dụng có quyền giới hạn trong một schema.
- **Low:** credential dùng cho môi trường lab hoặc dữ liệu giả lập.

Mức độ phân loại quyết định người được phép truy cập, thời gian lưu, quy trình phê duyệt, tần suất kiểm tra và cách xử lý khi bị lộ.

## 3. Nguyên tắc quản lý secret

### 3.1. Một danh tính cho một workload

Không dùng chung một tài khoản database cho nhiều ứng dụng hoặc nhiều môi trường nếu có thể tránh.

Ví dụ:
- `ORDER_API_USER`: chỉ truy cập các object cần cho API đơn hàng.
- `REPORTING_USER`: chỉ đọc các view/bảng được cấp.
- `ETL_LOADER`: quyền ghi vào vùng staging và chạy tác vụ ETL cần thiết.
- `MONITOR_USER`: chỉ có quyền giám sát đã được phê duyệt.

Khi mỗi workload có identity riêng, có thể thu hồi hoặc rotation một credential mà không làm gián đoạn mọi hệ thống khác.

### 3.2. Least privilege

Cấp đúng quyền cần thiết:
- Không dùng SYS/SYSTEM cho ứng dụng.
- Không cấp DBA chỉ để ứng dụng chạy được.
- Hạn chế `ANY` privileges.
- Tách quyền đọc, ghi, vận hành và quản trị khóa.
- Dùng role phù hợp cho công việc tương tác; đánh giá quyền trực tiếp khi ứng dụng cần quyền trong stored procedure theo semantics của Oracle.
- Kiểm tra quyền kế thừa và quyền được cấp qua role.

Credential mạnh nhưng có quyền quá rộng vẫn tạo rủi ro lớn.

### 3.3. Secret không được đưa vào source code

Không commit password, token, wallet password, private key hoặc file wallet vào Git.

Không dùng:
- Chuỗi password cố định trong Java, Python hoặc PL/SQL.
- File `.env` có secret rồi đưa vào repository.
- Password trong Docker image hoặc build artifact.
- Secret trong command line argument.
- Secret trong SQL comment hoặc tên object.
- Giá trị bí mật trong mẫu cấu hình được chia sẻ.

Mẫu cấu hình chỉ nên chứa tên biến hoặc alias, ví dụ `DB_CREDENTIAL_ALIAS=orders-prod`, không chứa password thật.

### 3.4. Cấp phát ngắn hạn khi có thể

Với workload hỗ trợ, ưu tiên token hoặc credential ngắn hạn thay cho password tĩnh tồn tại lâu. Secret manager có thể cấp credential theo workload identity và thu hồi khi không còn cần.

Oracle database authentication, wallet, Kerberos, TLS certificate, OCI IAM hoặc các cơ chế external authentication có điều kiện triển khai riêng. Chọn cơ chế theo kiến trúc và phiên bản thực tế.

## 4. Lưu trữ credential an toàn cho ứng dụng Oracle

### 4.1. Oracle Wallet và Secure External Password Store

Oracle Wallet có thể lưu credential để client kết nối database mà không phải đặt username/password trực tiếp trong command hoặc source code. Secure External Password Store (SEPS) cho phép client dùng connect identifier/alias đã cấu hình.

Sau khi wallet được cấu hình đúng, client có thể kết nối bằng external password store, ví dụ:

```text
sqlplus /@orders_prod
```

`orders_prod` là alias kết nối được cấu hình trong Oracle Net. Câu lệnh không chứa username/password.

Các điểm cần quản lý:
- Wallet directory chỉ cho đúng OS account hoặc service account đọc.
- Quyền filesystem không cho user không liên quan truy cập.
- Bảo vệ wallet password và file auto-login wallet.
- Có backup được bảo vệ và quy trình restore đã thử.
- Có quy trình rotation credential bên trong wallet.
- Không đưa wallet hoặc file `cwallet.sso` vào source control.
- Hạn chế copy wallet sang máy hoặc môi trường khác.

Auto-login wallet thuận tiện cho service tự khởi động, nhưng file auto-login bị sao chép có thể làm giảm bảo vệ nếu ACL và quyền host không chặt. Cân nhắc local auto-login wallet khi phù hợp với môi trường.

### 4.2. Cấu hình Oracle Net

Client wallet cần được cấu hình theo hướng dẫn Oracle Net đúng phiên bản. Cấu hình có thể chỉ ra vị trí wallet và các tùy chọn external password store trong `sqlnet.ora`.

Không ghi password vào `tnsnames.ora` hoặc URL kết nối. File `tnsnames.ora` nên giữ thông tin endpoint/service; wallet giữ credential.

### 4.3. Không truyền password qua command line

Một lệnh tiện dụng có thể vô tình để password trong:
- Shell history.
- Process list.
- Log của hệ thống orchestration.
- Build output.
- Telemetry của terminal.

Khi dùng công cụ quản lý wallet, không đặt password thật trực tiếp trong câu lệnh được lưu hoặc chia sẻ. Dùng prompt bảo mật, API/secret provider hoặc cơ chế nhập liệu được công cụ hỗ trợ. Không dùng giá trị minh họa trong tài liệu làm password triển khai.

### 4.4. Dùng password prompt trong SQL*Plus

Đối với thao tác tương tác, SQL*Plus có lệnh `PASSWORD` để yêu cầu nhập mật khẩu qua prompt:

```sql
PASSWORD app_user
```

Client sẽ yêu cầu nhập giá trị theo quy trình của lệnh. Đây thường an toàn hơn việc gõ password vào câu lệnh `CONNECT user/password` hoặc lưu câu `ALTER USER` có secret thật trong script.

Với tài khoản hiện tại, có thể dùng:

```sql
PASSWORD
```

Hành vi prompt cụ thể phụ thuộc client và cách xác thực. Không bật echo hoặc ghi lại nội dung nhập vào trong terminal transcript.

## 5. Quản lý user và password policy trong Oracle

### 5.1. Dùng profile để áp dụng chính sách

Oracle Database Profile có thể đặt giới hạn password và một số giới hạn tài nguyên cho user. Các tham số password thường gặp:

| Profile parameter | Mục đích |
|---|---|
| `FAILED_LOGIN_ATTEMPTS` | Số lần đăng nhập sai trước khi khóa tài khoản theo chính sách |
| `PASSWORD_LOCK_TIME` | Thời gian khóa tài khoản |
| `PASSWORD_LIFE_TIME` | Thời hạn password |
| `PASSWORD_GRACE_TIME` | Khoảng thời gian cảnh báo sau khi password hết hạn |
| `PASSWORD_REUSE_TIME` | Khoảng thời gian trước khi được dùng lại password cũ |
| `PASSWORD_REUSE_MAX` | Số lần đổi password trước khi được dùng lại |
| `PASSWORD_VERIFY_FUNCTION` | Hàm kiểm tra độ mạnh password |
| `INACTIVE_ACCOUNT_TIME` | Khóa account không hoạt động nếu phiên bản hỗ trợ |

Không áp dụng một bộ giá trị cho mọi user. Service account, tài khoản người dùng và tài khoản quản trị có yêu cầu khác nhau. Các giá trị phải theo chính sách bảo mật của tổ chức và khả năng của release Oracle.

### 5.2. Ví dụ tạo profile

Ví dụ minh họa, cần điều chỉnh theo policy và xác nhận hàm verify đã được cài:

```sql
CREATE PROFILE app_password_policy LIMIT
    FAILED_LOGIN_ATTEMPTS 5
    PASSWORD_LOCK_TIME 1/24
    PASSWORD_LIFE_TIME 90
    PASSWORD_GRACE_TIME 7
    PASSWORD_REUSE_MAX 10
    PASSWORD_REUSE_TIME 365
    PASSWORD_VERIFY_FUNCTION ORA12C_VERIFY_FUNCTION;
```

`ORA12C_VERIFY_FUNCTION` phải tồn tại trong database. Oracle cung cấp script mẫu để cài một số password verification function; DBA cần xem nội dung và điều chỉnh trước khi sử dụng. Không giả định mọi database đều đã cài sẵn hàm này.

`PASSWORD_REUSE_TIME` và `PASSWORD_REUSE_MAX` cần được cấu hình theo cặp nếu muốn thực thi quy tắc tái sử dụng. Kiểm tra tài liệu đúng release về semantics khi một giá trị là `UNLIMITED`.

### 5.3. Gán profile cho user

```sql
ALTER USER app_user PROFILE app_password_policy;
```

Kiểm tra profile và trạng thái account:

```sql
SELECT username,
       account_status,
       profile,
       expiry_date,
       authentication_type,
       password_versions
FROM dba_users
WHERE username = 'APP_USER';
```

Cần quyền xem `DBA_USERS`; trong schema giới hạn có thể dùng view phù hợp như `USER_USERS`. Không truy vấn hoặc xuất password hash ra log/ticket. `PASSWORD_VERSIONS` là metadata về phiên bản verifier, không phải password plaintext.

### 5.4. Kiểm tra profile đang áp dụng

```sql
SELECT profile,
       resource_name,
       limit
FROM dba_profiles
WHERE profile = 'APP_PASSWORD_POLICY'
  AND resource_type = 'PASSWORD'
ORDER BY resource_name;
```

Profile chỉ có hiệu lực khi được gán cho user. Thay đổi profile có thể ảnh hưởng nhiều account cùng sử dụng; kiểm tra danh sách user trước khi thay đổi.

### 5.5. Password expiration không thay thế rotation có kế hoạch

`PASSWORD_LIFE_TIME` là cơ chế hết hạn theo profile. Với service account, nếu password hết hạn mà chưa cập nhật consumer, ứng dụng có thể mất kết nối đột ngột. Hãy phối hợp expiration với rotation tự động, theo dõi expiry date và kế hoạch triển khai credential mới.

Tần suất đổi password cần theo threat model và policy. Đổi quá thường xuyên mà không có automation có thể làm tăng lỗi vận hành và khiến người dùng chọn password yếu hoặc lưu password không an toàn. Khi có dấu hiệu lộ credential, phải rotate/revoke ngay theo quy trình incident, không chờ lịch hết hạn.

## 6. Luân chuyển mật khẩu user database

Password rotation là quy trình thay một credential đang được sử dụng bằng credential mới, cập nhật mọi consumer và thu hồi giá trị cũ đúng thời điểm.

### 6.1. Lập inventory trước khi đổi

Xác định mọi nơi dùng account:
- Ứng dụng và connection pool.
- Batch/ETL và scheduler jobs.
- Database links.
- Monitoring, backup và deployment tools.
- Script vận hành.
- Stored procedure hoặc integration bên ngoài.
- Các môi trường standby, DR hoặc node khác nếu có credential phụ thuộc.

Không giả định chỉ ứng dụng chính dùng account. Một tài khoản dùng chung có thể được nhúng trong nhiều job ít được biết đến.

### 6.2. Quy trình rotation có kiểm soát

Một quy trình phổ biến:

1. **Xác định owner:** ai chịu trách nhiệm credential và từng consumer.
2. **Lập thời gian:** chọn cửa sổ thay đổi và thông báo nhóm liên quan.
3. **Chuẩn bị credential mới:** sinh giá trị ngẫu nhiên mạnh qua secret manager hoặc công cụ được phê duyệt.
4. **Kiểm tra consumer:** xác nhận ứng dụng hỗ trợ reload secret hoặc tạo pool mới.
5. **Thay password tại Oracle:** dùng kênh quản trị an toàn.
6. **Cập nhật secret store:** ghi credential mới vào wallet/secret manager với quyền phù hợp.
7. **Khởi tạo kết nối mới:** kiểm tra login từ từng consumer.
8. **Làm mới pool/job:** loại bỏ connection cũ và bảo đảm kết nối mới sử dụng credential mới.
9. **Theo dõi lỗi:** logon failure, invalid credential, job failure và retry.
10. **Thu hồi giá trị cũ:** khi xác nhận không còn consumer cần giá trị cũ.
11. **Ghi nhận kết quả:** thời gian, owner, account, consumer đã cập nhật và bằng chứng thành công; không ghi secret.

### 6.3. Đổi password bằng DBA command

Cú pháp quản trị tổng quát:

```sql
ALTER USER app_user IDENTIFIED BY "<NEW_SECRET>";
```

`<NEW_SECRET>` chỉ là placeholder, không phải password dùng thật. Câu lệnh có thể xuất hiện trong SQL history, audit, trace hoặc công cụ quản trị tùy cách thực thi và cấu hình. Không đặt giá trị bí mật thật trong script dùng chung, source control, ticket hoặc terminal command history.

Với thao tác tương tác, ưu tiên password prompt phù hợp của SQL*Plus/client. Với automation, lấy secret trực tiếp từ secret manager và dùng cơ chế bảo mật được hỗ trợ; kiểm soát quyền đọc output và lịch sử thực thi.

### 6.4. Xác minh sau khi đổi

Không chỉ kiểm tra câu lệnh `ALTER USER` thành công. Cần xác minh:
- Đăng nhập mới bằng credential mới.
- Kết nối qua đúng service name.
- Ứng dụng tạo được connection mới.
- Connection pool không tiếp tục dùng connection cũ vô thời hạn.
- Job và batch chạy thành công.
- Không còn consumer nào dùng credential cũ.
- Account không bị khóa hoặc hết hạn ngoài dự kiến.

Các session đã kết nối trước khi đổi password thường không tự động bị ngắt chỉ vì password đổi. Vì vậy cần chủ động làm mới pool/session theo kế hoạch; nếu nghi credential đã bị lộ, có thể phải thu hồi session hoặc khóa account theo incident response.

## 7. Gradual password rollover

Một số release Oracle hỗ trợ **gradual password rollover**, cho phép duy trì một khoảng chuyển tiếp để ứng dụng đổi password mà không phải cập nhật tất cả consumer trong cùng một thời điểm.

Profile parameter liên quan là `PASSWORD_ROLLOVER_TIME`. Ví dụ:

```sql
ALTER PROFILE app_password_policy
LIMIT PASSWORD_ROLLOVER_TIME 7;
```

Trong khoảng rollover được cấu hình, database có thể chấp nhận password cũ và mới theo semantics của feature. Điều này hỗ trợ triển khai credential mới theo từng nhóm ứng dụng.

### 7.1. Điều kiện và giới hạn

- Kiểm tra release và Release Update có hỗ trợ feature.
- Kiểm tra loại user/authentication và điều kiện áp dụng.
- Xác nhận profile đang gán cho account.
- Đọc đúng tài liệu Oracle về thời gian rollover và hành vi khi kết thúc.
- Kiểm thử trên staging với ứng dụng và connection pool thực tế.

Không giả định mọi account, external authentication hoặc mọi phiên bản đều hỗ trợ rollover giống nhau.

### 7.2. Quy trình dùng rollover

Một trình tự khái quát:
1. Gán profile có thời gian rollover phù hợp.
2. Đổi password theo quy trình Oracle.
3. Phân phối credential mới qua secret manager.
4. Cập nhật từng consumer và xác nhận kết nối mới.
5. Theo dõi consumer vẫn dùng credential cũ.
6. Kết thúc thời gian rollover, xác nhận chỉ credential mới còn hợp lệ.
7. Thu hồi và xóa bản lưu credential cũ theo chính sách.

Rollover là khoảng chuyển tiếp có giới hạn, không phải lý do để giữ password cũ vô thời hạn. Cần có owner và deadline cho từng consumer.

## 8. Luân chuyển credential trong connection pool

Ứng dụng Java hoặc middleware thường giữ connection pool. Khi password thay đổi, pool có thể vẫn chứa các connection đã mở trước đó. Khi connection bị đóng và pool tạo connection mới, credential cũ có thể được dùng lại nếu secret chưa được reload.

### 8.1. Các bước cập nhật pool

- Secret manager cung cấp credential mới cho workload.
- Cấu hình datasource nhận giá trị mới.
- Tạo pool mới hoặc reload cấu hình theo khả năng framework.
- Health check bằng một kết nối mới.
- Chuyển traffic sang pool mới.
- Drain và đóng pool cũ.
- Theo dõi lỗi authentication và connection churn.
- Thu hồi password cũ sau khi mọi pool đã chuyển.

Không chỉ sửa file cấu hình trên disk rồi cho rằng process đã nhận giá trị mới. Nhiều ứng dụng chỉ đọc secret lúc khởi động.

### 8.2. Blue/green connection pool

Có thể dùng hai pool:
- Pool xanh dùng credential cũ.
- Pool mới dùng credential mới.

Sau khi pool mới health check thành công, chuyển request sang pool mới rồi drain pool cũ. Cách này giảm downtime nhưng cần hạ tầng và ứng dụng hỗ trợ hai datasource tạm thời.

### 8.3. Giới hạn retry

Nếu credential sai, retry liên tục có thể làm tăng `FAILED_LOGIN_ATTEMPTS` và khóa account. Dùng backoff, circuit breaker và cảnh báo khi có lỗi xác thực lặp lại. Không retry vô hạn với password cũ.

## 9. Các credential Oracle đặc biệt cần inventory riêng

### 9.1. Database link

Database link dùng credential để kết nối database từ xa. Với fixed-user database link, thông tin xác thực được lưu trong metadata của database theo cơ chế Oracle; không nên tìm cách đọc lại password plaintext.

Khi password remote user đổi, cần cập nhật/recreate database link theo quy trình được hỗ trợ và kiểm tra các truy vấn sử dụng link. DDL tạo link có thể chứa password trong câu lệnh, do đó phải bảo vệ lịch sử SQL, audit và công cụ triển khai.

Nếu kiến trúc hỗ trợ current-user database link hoặc external authentication, có thể đánh giá để giảm credential tĩnh. Không phải mọi mô hình database link đều dùng được cùng một cơ chế.

### 9.2. DBMS_SCHEDULER credentials

External jobs hoặc một số loại job cần credential object. Oracle cung cấp API trong `DBMS_CREDENTIAL`/`DBMS_SCHEDULER` theo phiên bản.

Credential của job cần:
- Owner rõ ràng.
- Quyền sử dụng giới hạn.
- Rotation đồng bộ với account hệ điều hành hoặc dịch vụ đích.
- Kiểm tra job sau khi đổi.
- Không truyền password qua script/log công khai.

Khi thay credential, kiểm tra job đang chạy, job schedule tiếp theo và quyền execute credential.

### 9.3. Password file và tài khoản quản trị

Các quyền như `SYSDBA`, `SYSOPER`, `SYSBACKUP`, `SYSDG` hoặc `SYSKM` có thể liên quan password file và cơ chế xác thực quản trị riêng.

Quản lý password file cần xem:
- Database version và định dạng password file.
- RAC và vị trí lưu trong ASM hoặc filesystem.
- Data Guard primary/standby.
- Các node và công cụ quản trị sử dụng file.
- Quy trình đồng bộ và kiểm tra sau rotation.

Không coi password file quản trị giống một user ứng dụng thông thường. Làm theo tài liệu `orapwd`, `ALTER USER` và hướng dẫn Data Guard/RAC đúng release. Bảo vệ quyền đọc file và không sao chép file ra nơi không kiểm soát.

### 9.4. Tài khoản ngoài database

Tài khoản OS, cloud, backup agent, monitoring và middleware không được quản lý đầy đủ chỉ bằng Oracle profile. Chúng cần owner, secret store, lịch rotation và quy trình revoke riêng. Inventory nên chỉ ra hệ thống nào là nguồn xác thực có thẩm quyền.

## 10. TDE keystore, TLS và key rotation

Password database và encryption key là hai loại secret khác nhau. Đổi password user không đồng nghĩa rotate TDE master key; rotate master key cũng không tự thay password ứng dụng.

### 10.1. TDE keystore

Transparent Data Encryption (TDE) dùng keystore/wallet để bảo vệ master encryption key. Quy trình vận hành cần:
- Bảo vệ keystore password.
- Giới hạn người được mở/quản trị keystore.
- Backup keystore theo hướng dẫn Oracle.
- Bảo đảm backup và disaster recovery có key phù hợp.
- Thử restore và mở dữ liệu mã hóa.
- Ghi nhận lịch sử key rotation mà không ghi secret.

### 10.2. Rotate TDE master key

TDE master key rotation là hoạt động quản trị riêng. Cú pháp `ADMINISTER KEY MANAGEMENT` thay đổi theo release, CDB/PDB và trạng thái keystore. Ví dụ dạng lệnh khái quát:

```sql
ADMINISTER KEY MANAGEMENT SET KEY
IDENTIFIED BY "<KEYSTORE_PASSWORD>"
WITH BACKUP USING 'before_key_rotation';
```

Placeholder không phải password thật. Trước khi thực hiện, xác nhận:
- Keystore đang ở trạng thái phù hợp.
- Đúng container/PDB và key scope.
- Có backup keystore an toàn.
- Có kế hoạch đồng bộ RAC/standby và backup.
- Có kiểm thử restore.
- Người thực hiện có quyền quản trị TDE.

Không xóa key cũ hoặc keystore backup khi còn backup datafile cần key đó để khôi phục.

### 10.3. TLS certificate và private key

TLS certificate có thời hạn và cần renewal/rotation. Theo dõi:
- Certificate chain và CA.
- Hostname/SAN.
- Expiry date.
- Trust store của client.
- Private key permissions.
- Listener/client wallet configuration.
- Thời điểm triển khai để tránh client trust mismatch.

Không gửi private key qua email hoặc ticket. Không ghi private key hay keystore password vào log khởi động ứng dụng.

## 11. Log có thể làm lộ dữ liệu nhạy cảm như thế nào?

### 11.1. SQL text

Nếu ứng dụng nối password hoặc token trực tiếp vào SQL literal, giá trị có thể xuất hiện trong SQL text, shared pool, audit hoặc trace tùy cơ chế thu thập.

Không đưa secret vào SQL statement. Dùng bind variable cho dữ liệu nghiệp vụ; với password và credential, dùng cơ chế xác thực/quản lý secret phù hợp thay vì truyền chúng như tham số SQL thông thường.

### 11.2. Bind values

Bind variables giúp tránh literal trong SQL text, nhưng bind capture hoặc SQL trace có thể ghi lại giá trị bind. Nếu bind là số tài khoản, token hoặc dữ liệu cá nhân, log/trace vẫn có thể chứa thông tin nhạy cảm.

Không bật bind capture/trace rộng rãi trên production nếu chưa đánh giá dữ liệu có thể bị ghi. Giới hạn session, thời gian, quyền truy cập và retention.

### 11.3. Connection string và exception

Các nơi dễ vô tình ghi credential:
- JDBC URL có embedded password.
- Object cấu hình datasource được serialize.
- Exception in ra toàn bộ connection properties.
- HTTP Authorization header hoặc bearer token.
- Request body chứa credential.
- Environment dump và diagnostic bundle.
- Startup script echo biến môi trường.
- Command line chứa password.
- SQL Developer/SQLcl history hoặc terminal transcript.

Chỉ log mã lỗi và ngữ cảnh cần thiết; không log toàn bộ cấu hình xác thực.

### 11.4. Trace và performance repository

SQL Trace, TKPROF, `V$SQL`, bind capture, AWR/ASH hoặc SQL Monitor có thể chứa SQL text, bind metadata hoặc dữ liệu nhạy cảm tùy cách cấu hình và loại câu lệnh.

Các file trace và repository phải được phân quyền, mã hóa theo policy, có retention và quy trình xóa. Không gửi file trace thô vào ticket công khai hoặc repository.

## 12. Thiết kế log an toàn

### 12.1. Ghi metadata thay vì secret

Một log hữu ích thường có:
- Timestamp có timezone hoặc chuẩn thời gian hệ thống.
- Application/service/module/action.
- Request ID hoặc correlation ID.
- Database username hoặc service identity theo policy.
- SQL_ID hoặc mã operation.
- Object/function liên quan.
- Kết quả thành công/thất bại.
- Error code.
- Duration và số hàng xử lý nếu phù hợp.
- Client/service context cần cho điều tra.

Không cần ghi password, token, private key, wallet content hoặc toàn bộ request body để điều tra một lỗi đăng nhập.

### 12.2. Allowlist field

Thiết kế logger theo allowlist: chỉ cho phép các trường đã được phê duyệt. Không serialize toàn bộ object request, datasource properties, environment hoặc exception context một cách tự động.

### 12.3. Masking và redaction

Nếu cần ghi một định danh, chỉ ghi phần tối thiểu, ví dụ bốn ký tự cuối khi nghiệp vụ cho phép. Với token, không log prefix/suffix nếu vẫn có thể hỗ trợ khôi phục hoặc đoán secret. Với password và private key, không log bất kỳ phần nào.

Redaction phải xảy ra trước khi ghi log. Xóa log sau khi đã phát tán không bảo đảm loại bỏ mọi bản sao.

### 12.4. Phân quyền và retention

Log cũng là tài sản cần bảo vệ:
- Chỉ nhóm vận hành/bảo mật phù hợp được đọc.
- Tách quyền ghi log khỏi quyền sửa/xóa log.
- Dùng central logging có TLS và kiểm soát truy cập.
- Bảo vệ archive và backup.
- Đặt retention theo yêu cầu pháp lý/nghiệp vụ.
- Theo dõi truy cập log.
- Có quy trình xử lý khi log chứa secret ngoài ý muốn.

Không lưu log vô thời hạn nếu không có mục tiêu rõ ràng.

## 13. Audit trong Oracle: truy vết mà không thu thập secret

Audit giúp trả lời ai thực hiện hành động nào, trên object nào, khi nào và kết quả ra sao. Audit policy cần được thiết kế theo mục tiêu bảo mật và khối lượng dữ liệu.

### 13.1. Unified Auditing

Unified Auditing cung cấp một nơi tập trung để xem các audit record được cấu hình. Một truy vấn minh họa:

```sql
SELECT event_timestamp,
       dbusername,
       action_name,
       object_schema,
       object_name,
       return_code,
       client_program_name,
       module,
       action
FROM unified_audit_trail
WHERE event_timestamp >= SYSTIMESTAMP - INTERVAL '1' DAY
ORDER BY event_timestamp DESC;
```

View và cột cần xác nhận theo phiên bản, quyền và cấu hình auditing. Truy vấn này chọn metadata phục vụ điều tra, không lấy `SQL_TEXT` hoặc `SQL_BINDS`.

### 13.2. Audit các sự kiện quan trọng

Tùy chính sách, xem xét audit:
- Logon thành công và thất bại.
- Tạo, sửa, khóa, mở khóa hoặc xóa user.
- Thay đổi role và system privilege.
- Thay đổi profile.
- DDL trên object nhạy cảm.
- Truy cập bảng dữ liệu nhạy cảm.
- Hoạt động quản trị TDE/keystore.
- Thay đổi audit policy.
- Thao tác với database link hoặc credential object nếu cần theo dõi.

Chọn policy theo nguyên tắc cần biết. Audit quá rộng có thể tăng volume, làm khó điều tra và thu thập nhiều SQL text/bind không cần thiết.

### 13.3. Unified Audit và SQL text/binds

Một số audit record có thể lưu SQL text hoặc bind information tùy loại policy, phiên bản và cấu hình. Trước khi bật audit rộng, kiểm tra trường nào được thu thập và liệu có thể chứa secret hay dữ liệu cá nhân không.

Nếu cần audit hành động thay đổi mật khẩu, ưu tiên ghi nhận principal, thời gian, kết quả và nguồn thực hiện; không ghi giá trị password mới/cũ.

### 13.4. Fine-Grained Auditing

Fine-Grained Auditing (FGA) có thể theo dõi truy cập cụ thể trên object/cột theo điều kiện. FGA phù hợp khi cần audit truy cập dữ liệu nhạy cảm có phạm vi hẹp.

FGA không phải cơ chế lưu password an toàn hoặc che secret khỏi application log. Hãy thiết kế audit condition, handler và retention sao cho không đưa giá trị nhạy cảm vào nội dung audit message.

## 14. SQL Trace và bind capture an toàn

SQL Trace hữu ích khi phân tích hiệu năng, nhưng phải xác định có cần bind values hay không.

Ví dụ bật trace cho một session với waits nhưng không yêu cầu ghi bind:

```sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_ENABLE(
        session_id => 123,
        serial_num => 456,
        waits      => TRUE,
        binds      => FALSE
    );
END;
/
```

Tắt trace sau khi thu thập:

```sql
BEGIN
    DBMS_MONITOR.SESSION_TRACE_DISABLE(
        session_id => 123,
        serial_num => 456
    );
END;
/
```

SID và serial number chỉ là ví dụ. DBA cần xác định đúng session và có quyền phù hợp.

### 14.1. Quy tắc khi trace

- Chỉ trace session/request cần điều tra.
- Đặt thời gian thu thập ngắn.
- Tắt trace ngay khi đủ dữ liệu.
- Tránh bind capture nếu bind có thể chứa secret hoặc dữ liệu nhạy cảm.
- Bảo vệ trace file và báo cáo TKPROF.
- Xóa/retire file theo retention.
- Không gửi trace thô qua kênh không được bảo vệ.

Ngay cả khi `binds => FALSE`, SQL text vẫn có thể chứa literal nếu ứng dụng nối giá trị vào câu SQL. Thiết kế SQL không đưa secret vào text ngay từ đầu.

## 15. Bảo vệ log ở tầng ứng dụng

### 15.1. Java/JDBC

Các ứng dụng Java có thể ghi SQL, bind parameters hoặc datasource configuration qua logger của framework/driver. Ví dụ:
- ORM SQL logger.
- Bind parameter logger.
- Connection pool debug.
- HTTP client request/response logger.
- Exception handler.

Trong production:
- Không bật debug bind logging mặc định.
- Không log datasource password.
- Không in `Properties` chứa credential.
- Không ghi Authorization header.
- Không serialize toàn bộ request object.
- Tách log debug có thời hạn khỏi log audit.
- Có test tự động xác nhận secret mẫu không xuất hiện trong log.

### 15.2. PL/SQL

Không đưa secret vào:
- `DBMS_OUTPUT.PUT_LINE`.
- `RAISE_APPLICATION_ERROR` message.
- Custom audit table không bảo vệ.
- Dynamic SQL text.
- Exception wrapper.
- Debug table.

Nếu procedure nhận secret làm tham số, không ghi giá trị tham số. Chỉ ghi tên operation, caller, kết quả và correlation ID.

### 15.3. Shell và CI/CD

Không bật echo khi script xử lý secret. Không đặt secret trong argument list hoặc câu lệnh được in ra build log. Dùng secret store của CI/CD, protected variable hoặc cơ chế cấp phát ngắn hạn; giới hạn job và runner được quyền đọc.

Không lưu secret trong artifact, cache, crash dump hoặc output của `set -x`/verbose mode.

### 15.4. Kiểm tra log bằng secret giả

Trong môi trường test, dùng marker không có giá trị thực, ví dụ `TEST_SECRET_467_DO_NOT_LOG`. Thực hiện đăng nhập/thất bại có kiểm soát rồi tìm marker trong:
- Application log.
- SQL trace.
- Audit output.
- CI build log.
- Shell transcript.
- Error reporting.

Nếu marker xuất hiện, sửa logger và lặp lại kiểm thử. Không dùng password thật làm dữ liệu kiểm tra.

## 16. Tìm và kiểm tra account có nguy cơ

### 16.1. Tài khoản hết hạn hoặc bị khóa

```sql
SELECT username,
       account_status,
       lock_date,
       expiry_date,
       profile,
       authentication_type
FROM dba_users
ORDER BY account_status, username;
```

Cần quyền DBA. Phân biệt account bị khóa theo policy, password hết hạn và account external/global authentication.

### 16.2. Tìm account dùng profile mặc định

```sql
SELECT username, profile, account_status
FROM dba_users
WHERE profile = 'DEFAULT'
ORDER BY username;
```

Đây là danh sách để rà soát, không phải kết luận mọi user dùng DEFAULT đều sai. Xem profile thực tế và chính sách tổ chức.

### 16.3. Kiểm tra profile password

```sql
SELECT profile,
       resource_name,
       limit
FROM dba_profiles
WHERE resource_type = 'PASSWORD'
ORDER BY profile, resource_name;
```

Không xuất thông tin bí mật. Báo cáo kiểm tra nên tập trung vào trạng thái policy và ngoại lệ cần xử lý.

### 16.4. Kiểm tra quyền user service

Rà soát:
- System privileges.
- Object privileges.
- Roles.
- Proxy authentication.
- Grants có `ANY`.
- Quyền quản trị không cần thiết.
- Account không còn owner hoặc workload.

Các view như `DBA_SYS_PRIVS`, `DBA_ROLE_PRIVS`, `DBA_TAB_PRIVS` hỗ trợ kiểm tra khi có quyền. Thu hồi quyền cần xác minh dependency và quy trình change management.

## 17. Khi secret bị lộ: incident response

Giả sử password xuất hiện trong log hoặc commit Git. Xóa dòng log là chưa đủ vì có thể còn bản sao trong archive, SIEM, backup, ticket hoặc Git history.

Quy trình xử lý:
1. **Xác định phạm vi:** loại secret, account, quyền, môi trường và nơi đã phát tán.
2. **Đánh giá mức độ:** secret còn hiệu lực không, có quyền gì, có dấu hiệu sử dụng trái phép không.
3. **Cô lập:** hạn chế quyền truy cập log/repository hoặc tạm khóa account nếu cần.
4. **Rotate/revoke:** đổi password, thu hồi token, thay certificate/key theo quy trình tương ứng.
5. **Cập nhật consumer:** bảo đảm workload hợp lệ dùng secret mới.
6. **Điều tra:** xem audit, logon failure/success, source IP, module/action và hoạt động sau thời điểm lộ.
7. **Xử lý bản sao:** loại bỏ secret khỏi log/archive/ticket và Git history theo chính sách; kiểm soát backup.
8. **Khôi phục dịch vụ:** xác nhận kết nối và nghiệp vụ.
9. **Rút kinh nghiệm:** sửa nguồn log, CI rule, secret scanning và quy trình rotation.

Nếu secret đã bị commit, hãy coi nó đã bị lộ ngay cả khi repository private. Xóa commit hoặc rewrite history không làm secret cũ an toàn trở lại; rotate/revoke trước, sau đó mới xử lý lịch sử và bản sao.

## 18. Quy trình vòng đời secret

Một secret có owner và vòng đời rõ ràng:

```text
Create / provision
        |
        v
Store in wallet or secret manager
        |
        v
Grant access to one workload identity
        |
        v
Use without logging the value
        |
        v
Monitor usage and expiry
        |
        v
Rotate or renew
        |
        v
Verify consumers and revoke old value
        |
        v
Retire secret and protected backups by policy
```

### 18.1. Inventory

Mỗi record inventory nên có:
- Secret ID hoặc alias (không chứa giá trị secret).
- Loại secret.
- Owner kỹ thuật và owner nghiệp vụ.
- Workload/consumer.
- Môi trường.
- Nguồn lưu trữ.
- Ngày tạo và hạn/rotation due date.
- Mức quyền.
- Phụ thuộc và quy trình khôi phục.

### 18.2. Access review

Định kỳ xem:
- Ai có thể đọc secret?
- Workload nào đang dùng?
- Có tài khoản cũ không?
- Có secret không có owner?
- Có quyền đọc wallet quá rộng?
- Có bản copy trong backup hoặc máy cá nhân?
- Credential đã quá hạn hoặc không còn sử dụng?

### 18.3. Rotation tự động

Rotation tự động cần:
- API cấp credential mới.
- Cơ chế cập nhật password ở Oracle.
- Cập nhật secret store.
- Reload ứng dụng/pool.
- Health check.
- Rollback hoặc retry có kiểm soát.
- Audit không ghi giá trị bí mật.

Tự động hóa không có nghĩa bỏ qua dependency. Nếu đổi password database nhưng secret manager không cập nhật hoặc connection pool không reload, service vẫn có thể mất kết nối.

## 19. Bảng kiểm cho một đợt password rotation

| Giai đoạn | Việc cần xác nhận |
|---|---|
| Trước rotation | Owner, account, quyền, mọi consumer và thời điểm đã rõ |
| Chuẩn bị | Secret mới được sinh và lưu trong secret manager |
| Database | Password được đổi qua kênh quản trị an toàn |
| Secret store | Phiên bản secret mới đã được publish |
| Application | Pool/process đã reload và tạo kết nối mới |
| Integration | Job, DB link, ETL, backup, monitoring đã được kiểm tra |
| Security | Log không chứa password/token; audit có metadata cần thiết |
| Kết thúc | Credential cũ bị thu hồi khi không còn consumer |
| Theo dõi | Authentication failure, lock, timeout và service health bình thường |
| Hồ sơ | Ghi người thực hiện, thời gian, kết quả; không ghi secret |

## 20. Ví dụ tình huống: rotate password của ORDER_API_USER

Giả sử ứng dụng `ORDER_API` kết nối Oracle bằng account `ORDER_API_USER`.

### Bước 1. Inventory

Ghi lại các consumer:
- Hai instance API.
- Một batch reconciliation.
- Dashboard monitoring.
- Secret alias `orders-prod-db`.

Không ghi password hiện tại vào inventory.

### Bước 2. Kiểm tra account

```sql
SELECT username,
       account_status,
       profile,
       expiry_date,
       authentication_type
FROM dba_users
WHERE username = 'ORDER_API_USER';
```

Xác nhận profile và trạng thái account.

### Bước 3. Chuẩn bị secret mới

Sinh password ngẫu nhiên theo policy bằng secret manager. Phân quyền đọc secret cho đúng service identity. Không copy giá trị vào ticket hoặc chat.

### Bước 4. Thực hiện rotation

DBA đổi password qua client quản trị bảo mật, dùng password prompt hoặc automation đã được phê duyệt. Không ghi password thật trong script minh họa.

Nếu release/profile hỗ trợ gradual password rollover, đánh giá thời gian chuyển tiếp để hai instance và batch chuyển lần lượt.

### Bước 5. Cập nhật secret store

Publish version mới cho alias. Xác nhận mỗi instance có thể lấy đúng version và không log nội dung secret.

### Bước 6. Reload pool

Tạo pool mới hoặc refresh datasource theo cơ chế ứng dụng. Health check kết nối mới, sau đó chuyển traffic và drain pool cũ.

### Bước 7. Kiểm tra batch và monitoring

Chạy kiểm tra kết nối/health check cho batch, dashboard và các integration khác. Quan sát authentication failure và account lock.

### Bước 8. Kết thúc

Khi tất cả consumer dùng secret mới và không còn phụ thuộc cũ, kết thúc rollover hoặc thu hồi credential cũ theo feature/policy. Cập nhật inventory và ghi kết quả rotation không chứa secret.

## 21. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế |
|---|---|
| Chỉ cần mã hóa password trong file cấu hình | Ứng dụng vẫn phải giải mã; quyền đọc và key quản lý mới quyết định an toàn |
| Private Git repo an toàn để lưu secret | Người có quyền repo, backup hoặc fork vẫn có thể lấy secret |
| Đổi password trong database là xong | Consumer, pool, job, DB link và integration cần cập nhật |
| Connection cũ sẽ bị ngắt ngay khi password đổi | Session đã xác thực có thể còn tồn tại; cần quản lý pool/session |
| Bind variable bảo đảm giá trị không vào log | Bind capture và SQL trace có thể ghi bind values |
| Tắt bind logging là log đã an toàn | SQL text, exception, connection string hoặc request body vẫn có thể lộ |
| Audit phải lưu password để chứng minh rotation | Audit chỉ cần principal, action, time, outcome và context phù hợp |
| TDE thay thế secret manager | TDE bảo vệ dữ liệu at rest; không quản lý password ứng dụng |
| Wallet có thể copy tùy ý | Wallet và auto-login file cần ACL, backup và owner chặt |
| Password expiration tự cập nhật ứng dụng | Expiry có thể làm service mất kết nối nếu consumer chưa rotation |
| Xóa secret khỏi Git history là đủ | Credential đã lộ phải rotate/revoke; history rewrite chỉ xử lý bản sao |
| Dùng chung account giúp vận hành đơn giản | Khó truy vết, rotation và thu hồi riêng từng workload |
| Tăng log level luôn giúp điều tra | Debug log có thể làm lộ bind, token, connection properties |
| Data Redaction che được secret trong mọi log | Data Redaction kiểm soát dữ liệu trả về qua database, không thay thế log sanitization |

## 22. Checklist bảo mật cuối cùng

### Quản lý secret
- Mọi credential có owner và consumer inventory.
- Không có secret trong source code hoặc Git.
- Wallet/secret manager được bảo vệ bằng ACL.
- Tài khoản có quyền tối thiểu.
- Có backup và restore test cho keystore.
- Có lịch rotation và quy trình revoke.

### Password rotation
- Đã xác định mọi consumer.
- Có kế hoạch reload connection pool.
- Đã xem xét gradual rollover nếu release hỗ trợ.
- Đã kiểm tra DB link, Scheduler, password file và integration liên quan.
- Đã xác minh kết nối mới.
- Đã thu hồi credential cũ đúng thời điểm.

### Logging và auditing
- Không log password, token, private key hoặc wallet contents.
- Không log connection string có credential.
- Bind capture/trace được giới hạn và đánh giá.
- Audit ghi actor, action, object, time và outcome.
- Log có ACL, retention và giám sát truy cập.
- Có test dùng marker giả để phát hiện secret leakage.

### Incident response
- Có quy trình rotate/revoke khi secret lộ.
- Có khả năng xác định nơi secret đã xuất hiện.
- Có người phụ trách và kênh escalation.
- Có quy trình xử lý Git history, archive, backup và ticket.
- Có theo dõi hoạt động bất thường sau rotation.

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Secret khác configuration như thế nào?

**Trả lời:** Secret là giá trị cho phép xác thực hoặc giải mã, như password, token và private key. Configuration thường là endpoint, port hoặc service name; một file cấu hình vẫn có thể chứa secret cần bảo vệ.

**Câu 2.** Vì sao không nên dùng chung một database account cho nhiều ứng dụng?

**Trả lời:** Dùng identity riêng giúp truy vết, giới hạn quyền, rotation và thu hồi credential theo từng workload.

**Câu 3.** Oracle Wallet/SEPS giúp gì?

**Trả lời:** Lưu credential bên ngoài source/command để client kết nối bằng alias mà không phải đặt username/password trực tiếp trong lệnh kết nối.

**Câu 4.** Vì sao không truyền password qua command line?

**Trả lời:** Giá trị có thể xuất hiện trong shell history, process list, build log hoặc telemetry.

**Câu 5.** Profile Oracle quản lý những gì?

**Trả lời:** Profile có thể đặt giới hạn đăng nhập sai, khóa account, tuổi thọ password, grace period, reuse và password verification function.

**Câu 6.** Vì sao cần inventory consumer trước khi rotation?

**Trả lời:** Một account có thể được nhiều ứng dụng, pool, job và integration sử dụng; bỏ sót consumer có thể gây gián đoạn sau khi đổi password.

**Câu 7.** Password đổi có ngắt session đang kết nối không?

**Trả lời:** Không nên giả định như vậy. Session đã xác thực có thể còn hoạt động; cần làm mới pool/session theo kế hoạch.

**Câu 8.** Gradual password rollover dùng để làm gì?

**Trả lời:** Cho phép khoảng chuyển tiếp để consumer cập nhật password mới theo từng bước trong release và account được hỗ trợ.

**Câu 9.** Database link có thể đọc lại password plaintext không?

**Trả lời:** Không nên thiết kế vận hành dựa trên việc đọc lại plaintext; cần rotation/recreate link theo cơ chế Oracle hỗ trợ.

**Câu 10.** Password file khác database user thông thường thế nào?

**Trả lời:** Password file phục vụ một số quyền xác thực quản trị như SYSDBA/SYSOPER và cần quy trình quản lý riêng cho RAC/standby.

**Câu 11.** TDE master key rotation có giống user password rotation không?

**Trả lời:** Không. Đây là quy trình quản trị khóa mã hóa riêng, có yêu cầu backup/restore và đồng bộ keystore.

**Câu 12.** Vì sao bind variable vẫn có thể làm lộ dữ liệu?

**Trả lời:** Một số cơ chế bind capture, trace hoặc audit có thể lưu giá trị bind.

**Câu 13.** Log an toàn nên lưu những gì?

**Trả lời:** Timestamp, principal, action, object, request ID, kết quả và error code phù hợp; không cần secret value.

**Câu 14.** Unified Auditing có thay thế application log không?

**Trả lời:** Không. Database audit ghi hoạt động database; application log cung cấp ngữ cảnh request và nghiệp vụ. Hai nguồn bổ sung nhau.

**Câu 15.** Nếu password đã vào Git thì chỉ xóa commit có đủ không?

**Trả lời:** Không. Phải coi credential đã lộ và rotate/revoke; sau đó xử lý history và các bản sao theo policy.

**Câu 16.** Data Redaction có thay thế log sanitization không?

**Trả lời:** Không. Data Redaction kiểm soát một số dữ liệu trả về từ database, không bảo đảm các logger khác không ghi secret.

## 24. Kết luận

Quản lý bí mật trong Oracle là một quy trình xuyên suốt vòng đời credential và key: xác định owner, inventory consumer, lưu trong wallet hoặc secret manager, cấp quyền tối thiểu, giám sát, rotation và thu hồi. Oracle Wallet/Secure External Password Store giúp tách credential khỏi command và source code; profile giúp áp dụng password policy; gradual password rollover có thể hỗ trợ chuyển đổi theo từng bước khi release và account đáp ứng điều kiện. Database link, Scheduler credential, password file, TDE keystore và TLS private key cần được đưa vào inventory riêng vì mỗi loại có quy trình vận hành khác nhau.

Password rotation chỉ hoàn tất khi password đã được đổi, secret store đã cập nhật, connection pool/job/integration đã chuyển sang credential mới, kết nối mới hoạt động và giá trị cũ được thu hồi đúng thời điểm. Đổi password trong database mà bỏ quên consumer có thể làm gián đoạn dịch vụ.

Log cần hỗ trợ điều tra nhưng không chứa secret. Hãy ghi principal, action, timestamp, object, request ID và kết quả; kiểm soát SQL text, bind capture, trace, connection string, exception và debug output. Unified Auditing và application logging có thể bổ sung cho nhau, nhưng cần giới hạn trường được thu thập, quyền truy cập và retention. Nếu secret đã bị lộ, rotate/revoke ngay theo incident response rồi xử lý các bản sao. Một hệ thống an toàn phải vừa truy vết được hành động, vừa bảo đảm log và công cụ vận hành không trở thành nơi phát tán credential.

