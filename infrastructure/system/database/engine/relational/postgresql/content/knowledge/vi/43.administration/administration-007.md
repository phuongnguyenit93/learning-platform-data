# Quản lý thông tin bí mật và thay đổi mật khẩu

PostgreSQL xác thực người dùng bằng database roles. Một role có thuộc tính LOGIN có thể kết nối vào database; nếu dùng password authentication, PostgreSQL kiểm tra password do client cung cấp với password verifier được lưu trong catalog. Quản lý credentials vì thế bao gồm nhiều việc: chọn cơ chế xác thực, tạo password đủ mạnh, bảo vệ secret khi lưu/truyền, phân phối tới ứng dụng, xoay vòng định kỳ hoặc khi có sự cố, và thu hồi quyền truy cập cũ.

Trong production, đổi một password không chỉ là chạy một lệnh SQL. Ứng dụng có thể có hàng chục instances, connection pools, PgBouncer, background workers, replication standbys, migration jobs và monitoring agents. Một password mới có thể khiến các kết nối mới thất bại nếu secret chưa được cập nhật đồng bộ; ngược lại, các session đã xác thực thường vẫn tồn tại sau khi password thay đổi. Rotation cần có kế hoạch cho cả credentials và connections.

Bài học này trình bày PostgreSQL role/password model, SCRAM-SHA-256, cấu hình pg_hba.conf, thao tác đổi password an toàn, secret files và secret managers, staged rotation, connection pool refresh, replication credentials, expiration/revocation, auditing và runbooks. Các ví dụ giả định PostgreSQL trên môi trường production có ứng dụng kết nối qua mạng; chính sách cụ thể cần phù hợp với phiên bản, driver, proxy và nền tảng vận hành.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt database role, login role, group role và password credential.
2. Giải thích password verifier và cách PostgreSQL lưu thông tin xác thực.
3. Chọn SCRAM-SHA-256 thay cho cơ chế MD5 cũ.
4. Cấu hình password_encryption và pg_hba.conf.
5. Đổi password bằng psql an toàn, tránh lộ secret trong history/log.
6. Bảo vệ credentials trong .pgpass, service files, secret managers và containers.
7. Thiết kế password rotation cho ứng dụng nhiều instances.
8. Dùng login roles riêng và group roles để staged rotation không gián đoạn.
9. Làm mới connection pools, PgBouncer và background workers sau rotation.
10. Xoay vòng replication credentials và kiểm tra WAL receiver.
11. Hiểu password expiry, NOLOGIN, revocation và session termination.
12. Phân biệt password rotation với TLS certificate rotation.
13. Audit role changes, giới hạn quyền và bảo vệ break-glass accounts.
14. Xây dựng runbooks và kiểm thử quy trình rotation.

## 2. Role và password trong PostgreSQL

PostgreSQL dùng role để quản lý danh tính và quyền. Role có thể:

- Có LOGIN để kết nối.
- Có NOLOGIN để làm group role hoặc role giữ quyền.
- Có thuộc tính SUPERUSER, CREATEDB, CREATEROLE, REPLICATION và các thuộc tính khác.
- Là thành viên của một hoặc nhiều roles khác.
- Có password verifier nếu dùng password authentication.

Kiểm tra roles bằng psql:

```sql
\du
```

Hoặc query catalog:

```sql
SELECT
    rolname,
    rolcanlogin,
    rolsuper,
    rolcreatedb,
    rolcreaterole,
    rolreplication,
    rolvaliduntil
FROM pg_catalog.pg_roles
ORDER BY rolname;
```

### Login role và group role

Một thiết kế tốt tách danh tính đăng nhập khỏi quyền nghiệp vụ:

- Login role đại diện cho service/user và sở hữu credential.
- Group role NOLOGIN chứa quyền SELECT/INSERT/UPDATE/EXECUTE cần thiết.
- Login role được cấp membership vào group role.

Cách này cho phép tạo credential mới mà không phải cấp lại mọi quyền object cho từng danh tính.

## 3. Password verifier không phải plaintext password

PostgreSQL không cần lưu password plaintext để xác thực password-based login. Catalog nội bộ pg_authid chứa password verifier, ví dụ dạng SCRAM-SHA-256 hoặc MD5 cũ.

Verifier vẫn là dữ liệu nhạy cảm:

- Người có verifier có thể thử đoán password offline.
- Password yếu dễ bị brute-force/dictionary attack nếu verifier bị lộ.
- Backup/global-role dumps có thể chứa verifier.
- Quyền đọc pg_authid phải được giới hạn nghiêm ngặt.

View pg_roles che trường password để người dùng thông thường không đọc được verifier. Không cấp quyền rộng trên pg_authid và không xuất verifier ra log, ticket hay chat.

### Kiểm tra loại verifier

DBA có thể cần kiểm kê thuật toán verifier mà không hiển thị giá trị hash. Truy vấn pg_authid đòi hỏi quyền rất cao; chỉ chạy trong phiên quản trị được kiểm soát:

```sql
SELECT
    rolname,
    CASE
      WHEN rolpassword LIKE 'SCRAM-SHA-256$%' THEN 'scram-sha-256'
      WHEN rolpassword LIKE 'md5%' THEN 'md5'
      WHEN rolpassword IS NULL THEN 'no password'
      ELSE 'other'
    END AS verifier_type
FROM pg_catalog.pg_authid
ORDER BY rolname;
```

Không SELECT rolpassword trực tiếp để đưa vào báo cáo. Báo cáo chỉ cần tên role và loại verifier.

## 4. Password authentication và pg_hba.conf

pg_hba.conf quy định client nào được kết nối, tới database/user nào, từ địa chỉ nào và dùng phương thức xác thực gì. PostgreSQL đọc file theo thứ tự; dòng đầu tiên khớp với connection request sẽ quyết định phương thức. Nếu xác thực thất bại, server không thử tiếp các dòng sau.

Một dòng có dạng:

```text
TYPE  DATABASE  USER  ADDRESS  METHOD
```

Ví dụ:

```conf
hostssl  appdb  app_login  10.20.0.0/16  scram-sha-256
```

Dòng này yêu cầu TLS và SCRAM password authentication cho role/database/address đã nêu.

### Các authentication methods thường gặp

| Method | Cách hoạt động khái quát | Trường hợp thường dùng |
|---|---|---|
| scram-sha-256 | Challenge-response dựa trên SCRAM verifier | Password authentication hiện đại |
| md5 | Cơ chế password cũ | Tương thích legacy trong lúc migration |
| peer | Xác thực local bằng OS user mapping | Local Unix socket |
| cert | Xác thực bằng client TLS certificate | Certificate-based identity |
| trust | Không yêu cầu password | Chỉ môi trường cô lập/test rất đặc biệt |
| reject | Từ chối connection | Chặn một nhóm client |

Tránh dùng trust cho production network connections. Peer authentication cũng cần mapping/policy đúng; nó không có nghĩa mọi local user đều được quyền đăng nhập.

## 5. SCRAM-SHA-256

SCRAM là cơ chế challenge-response. Client và server dùng thông tin password-derived để chứng minh cả hai phía biết credential mà không gửi plaintext password như một giá trị SQL qua wire.

Ưu điểm so với MD5:

- Dùng password verifier có salt và cơ chế derivation phù hợp hơn.
- Chống một số kiểu tấn công offline tốt hơn MD5 cũ.
- Hỗ trợ channel binding trong các client/server tương thích, giúp liên kết authentication với TLS channel.
- Là lựa chọn password authentication được khuyến nghị cho triển khai mới.

SCRAM không thay thế TLS. TLS vẫn cần để bảo vệ dữ liệu phiên, query results, credentials khác và xác minh server identity.

### Client compatibility

Driver PostgreSQL cũ có thể chưa hỗ trợ SCRAM. Trước khi chuyển production, xác minh phiên bản driver, pooler, proxy, migration tool, backup tool và monitoring client.

## 6. password_encryption

Setting password_encryption quyết định thuật toán PostgreSQL dùng khi tạo password verifier mới:

```sql
SHOW password_encryption;
```

Đặt cho session quản trị trước khi tạo/đổi password:

```sql
SET password_encryption = 'scram-sha-256';
```

Hoặc cấu hình trong postgresql.conf:

```ini
password_encryption = 'scram-sha-256'
```

Setting này không tự chuyển verifier hiện có từ MD5 sang SCRAM. Cần đặt lại password cho từng role để tạo verifier mới.

### Thời điểm áp dụng

Verifier được tạo theo password_encryption tại thời điểm password được đặt. Nếu sau đó đổi setting, các verifier đã lưu không tự thay đổi.

## 7. Cấu hình pg_hba.conf cho SCRAM

Ví dụ:

```conf
# Require TLS and SCRAM for application network access
hostssl  appdb  app_login  10.20.0.0/16  scram-sha-256

# Reject non-TLS connections from the application network
hostnossl  appdb  app_login  10.20.0.0/16  reject
```

Thứ tự rules quan trọng. Rule reject phải được đặt sau các rule hostssl phù hợp; nếu đặt trước, nó có thể chặn cả kết nối mong muốn tùy điều kiện match.

### Kiểm tra cấu hình

```sql
SELECT
    line_number,
    type,
    database,
    user_name,
    address,
    auth_method,
    error
FROM pg_catalog.pg_hba_file_rules
ORDER BY line_number;
```

View này giúp phát hiện lỗi parse và xem các rules đã đọc. Nó không chứng minh một client cụ thể khớp rule nào nếu chưa xét toàn bộ connection attributes và thứ tự.

Sau khi chỉnh file:

```sql
SELECT pg_catalog.pg_reload_conf();
```

Reload HBA không ngắt các session đã kết nối. Kiểm tra log để xác nhận cấu hình được nạp và không có parse errors.

## 8. Đổi password an toàn bằng psql

Không viết password thật trực tiếp trong câu lệnh SQL, shell command, script được lưu vào history hoặc CI logs. Cách tương tác an toàn hơn trong psql là meta-command:

```text
\password app_login
```

psql yêu cầu nhập password mới hai lần và xử lý mã hóa trước khi gửi lệnh thay đổi. Cách này tránh đưa password plaintext vào command history hoặc server statement log như khi gõ trực tiếp trong ALTER ROLE.

### Đổi password cho role hiện tại

```text
\password
```

### Đổi password cho role khác

Người chạy cần quyền phù hợp. Không chia sẻ terminal recording hoặc output chứa secret trong quá trình thao tác.

## 9. ALTER ROLE và rủi ro lộ password

Cú pháp SQL:

```sql
ALTER ROLE app_login PASSWORD 'new-secret';
```

Không dùng ví dụ literal như trên với secret production. Password có thể bị lộ trong:

- Shell/psql history nếu câu lệnh được nhập tương tác.
- SQL statement logs hoặc error logs tùy logging configuration.
- Audit trail, query capture, tracing.
- CI output, terminal transcript và screen recording.
- Source code hoặc migration files.

Nếu automation cần đổi password, dùng API/secret injection được thiết kế để tránh log và truyền secret qua cơ chế bảo mật. Không tự nối password vào SQL string trong script.

## 10. Tạo role theo least privilege

Ví dụ tạo group role giữ quyền:

```sql
CREATE ROLE app_readwrite NOLOGIN;

GRANT CONNECT ON DATABASE appdb TO app_readwrite;
GRANT USAGE ON SCHEMA app TO app_readwrite;
GRANT SELECT, INSERT, UPDATE, DELETE
ON ALL TABLES IN SCHEMA app
TO app_readwrite;
GRANT USAGE, SELECT, UPDATE
ON ALL SEQUENCES IN SCHEMA app
TO app_readwrite;
```

Quyền cho objects tạo trong tương lai cần default privileges được cấu hình bởi role tạo objects:

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE app_owner IN SCHEMA app
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES
TO app_readwrite;
```

Tạo login role riêng:

```sql
CREATE ROLE app_login_v1 LOGIN INHERIT;
GRANT app_readwrite TO app_login_v1;
```

Đặt password tương tác bằng psql:

```text
\password app_login_v1
```

Không cấp SUPERUSER cho application role. Role sở hữu objects nên tách khỏi role runtime nếu ứng dụng không cần DDL.

## 11. Password strength và generation

Password database nên được tạo ngẫu nhiên bằng password manager hoặc secret manager có bộ sinh mật khẩu an toàn. Không dùng tên service, hostname, môi trường, ngày tháng hoặc password pattern dễ đoán.

Nguyên tắc:

- Độ dài đủ lớn và entropy cao.
- Dùng secret riêng cho từng service/environment.
- Không tái sử dụng password giữa production, staging và development.
- Không chia sẻ password giữa nhiều ứng dụng không liên quan.
- Không lưu password trong source control.
- Hạn chế người có thể đọc/rotate secret.
- Ưu tiên secret manager tạo và lưu secret ngẫu nhiên.

PostgreSQL core không cung cấp đầy đủ hệ thống password policy, password history và workflow approval như một IAM platform. Dùng policy/secret manager phù hợp và không giả định server tự kiểm tra mọi yêu cầu về độ mạnh.

## 12. Quản lý password expiration

Có thể đặt thời điểm hết hạn password bằng VALID UNTIL:

```sql
ALTER ROLE app_login_v1
VALID UNTIL '2027-01-01 00:00:00+00';
```

Hoặc bỏ thời hạn:

```sql
ALTER ROLE app_login_v1 VALID UNTIL 'infinity';
```

### Ý nghĩa

VALID UNTIL kiểm soát thời hạn password authentication. Nó không tự kết thúc các session đã kết nối, không thay thế disable role và không phải cơ chế thu hồi tức thì mọi phương thức authentication.

### Chọn expiration policy

Không đặt expiration ngắn đến mức gây outage định kỳ nếu hệ thống không có quy trình tự động rotation đáng tin cậy. Với credentials rủi ro cao hoặc policy bắt buộc, phối hợp expiry với secret distribution, pool refresh và owner notification.

## 13. Xem role nào có password expiration

```sql
SELECT
    rolname,
    rolcanlogin,
    rolvaliduntil
FROM pg_catalog.pg_roles
WHERE rolcanlogin
ORDER BY rolvaliduntil NULLS LAST, rolname;
```

Giá trị NULL hoặc infinity có nghĩa không có expiration timestamp theo catalog. Cần phân biệt role không có password với role có password không hết hạn; pg_roles không tiết lộ verifier.

## 14. Chuyển từ MD5 sang SCRAM

Migration nên thực hiện theo từng nhóm clients để tránh làm toàn bộ ứng dụng mất khả năng đăng nhập.

Quy trình:

1. Kiểm kê roles đang dùng password authentication.
2. Kiểm kê client drivers, PgBouncer, proxies và automation tools.
3. Nâng cấp clients không hỗ trợ SCRAM.
4. Đặt password_encryption thành scram-sha-256.
5. Đặt lại password cho từng login role để tạo SCRAM verifier.
6. Kiểm tra HBA rules và chuyển method sang scram-sha-256.
7. Reload HBA.
8. Test kết nối mới từ từng client type.
9. Theo dõi authentication failures.
10. Gỡ bỏ MD5 rules sau khi không còn dependency.

PostgreSQL có thể tự chọn SCRAM khi HBA rule ghi md5 nhưng role đã có SCRAM verifier ở các phiên bản hỗ trợ hành vi này. Dù vậy, mục tiêu cuối nên là HBA ghi rõ scram-sha-256 để policy dễ đọc và kiểm soát.

## 15. Kiểm tra SCRAM compatibility

Trước migration, lập inventory:

| Client | Cần kiểm tra |
|---|---|
| Java JDBC driver | Phiên bản hỗ trợ SCRAM và TLS |
| .NET Npgsql | Phiên bản driver và auth negotiation |
| Go pgx/libpq | Phiên bản thư viện và connection mode |
| Python psycopg | Phiên bản psycopg/libpq |
| PgBouncer | SCRAM frontend/backend compatibility và auth_file |
| Backup/restore tools | Kết nối sau khi HBA đổi |
| Monitoring/exporters | Credentials và driver version |
| Replication standby | primary_conninfo/passfile và HBA |

Không chỉ test psql mới nhất. Một client cũ có thể tiếp tục chạy lâu trong background worker hoặc job scheduler và chỉ thất bại khi cần reconnect.

## 16. Bảo vệ password trong .pgpass

libpq hỗ trợ password file để ứng dụng/CLI không phải nhúng password vào connection string. Trên Unix-like systems, file mặc định là .pgpass trong home directory; có thể chỉ định qua PGPASSFILE.

Format:

```text
hostname:port:database:username:password
```

Ví dụ minh họa không chứa secret thật:

```text
pg-primary.internal:5432:appdb:backup_user:REPLACE_WITH_SECRET
```

### File permissions

Trên Unix, .pgpass phải có quyền hạn chế, thường là 0600; nếu permissions quá rộng, libpq có thể bỏ qua file. Trên Windows, file mặc định nằm dưới %APPDATA%\postgresql\pgpass.conf.

### Escaping

Dấu colon và backslash trong fields cần được escape theo quy tắc pgpass. Dòng đầu tiên khớp connection parameters sẽ được dùng; thứ tự entries có ý nghĩa.

Không commit .pgpass vào repository và không đặt nó trong thư mục được phục vụ qua web.

## 17. PGPASSWORD và environment variables

libpq có biến môi trường PGPASSWORD, nhưng không nên dùng làm cách lưu secret lâu dài trong production. Environment variables có thể bị lộ qua process inspection, diagnostics, crash dumps, orchestration metadata hoặc debugging tools tùy hệ điều hành/quyền.

Ưu tiên:

- Secret manager/short-lived secret injection.
- Password file với permissions phù hợp.
- Mounted secret file trong container.
- Driver secret provider tích hợp vault.

Nếu buộc dùng environment variable trong CI/job ngắn hạn, giới hạn scope/lifetime, mask logs và bảo đảm runner không chia sẻ với untrusted workloads.

## 18. Service connection files

libpq hỗ trợ service files như pg_service.conf để lưu host, port, database, user và các connection options. Có thể kết hợp service file với password file:

```ini
[app-write]
host=pg-primary.internal
port=5432
dbname=appdb
user=app_login_v1
sslmode=verify-full
passfile=/run/secrets/pgpass
application_name=orders-api-write
```

Kết nối:

```sh
psql "service=app-write"
```

Service file không nhất thiết chứa password. Giữ file config và secret file với quyền truy cập khác nhau; không đưa secret vào URI vì URI dễ xuất hiện trong process lists/logs.

## 19. Secret manager

Secret manager là hệ thống lưu trữ, phân phối, versioning và kiểm soát truy cập credentials. Ví dụ có thể là cloud secret manager, HashiCorp Vault hoặc secret platform nội bộ.

Các tính năng nên có:

- Encryption at rest và in transit.
- IAM/RBAC và least privilege.
- Audit log ai đọc/rotate secret.
- Versioning và rollback có kiểm soát.
- Secret generation an toàn.
- TTL/lease cho dynamic credentials nếu được hỗ trợ.
- Rotation event hoặc notification.
- Access policy theo service identity/environment.

### PostgreSQL không tự đồng bộ secret manager

Secret manager lưu password mới không tự đổi PostgreSQL role password. Ngược lại, ALTER ROLE đổi password không tự cập nhật secret manager. Rotation workflow phải cập nhật cả hai phía theo thứ tự có kiểm soát.

## 20. Secrets trong Docker và Kubernetes

Không bake database password vào container image hoặc Dockerfile. Không ghi secret trực tiếp trong Kubernetes manifest được commit vào source control.

### Kubernetes Secret

Kubernetes Secret thường được biểu diễn bằng base64 trong manifest/API. Base64 không phải encryption. Cần:

- Bật encryption at rest cho etcd theo platform policy.
- Giới hạn RBAC read/update secrets.
- Tránh mount secret vào containers không cần.
- Không log environment/secret contents.
- Dùng external secret manager integration khi phù hợp.
- Rotate và thu hồi service account access.

### Mounted file và environment

Secret volume có thể cập nhật file khi secret object đổi theo semantics của Kubernetes; biến môi trường trong container không tự đổi trong process đang chạy. Ứng dụng cần hỗ trợ reread/reload hoặc pod rollout. Connection pools vẫn cần mở connections mới bằng credential mới.

## 21. Phân biệt password rotation và connection refresh

Khi PostgreSQL xác thực một connection thành công, session đó không kiểm tra lại password ở mỗi query. Vì vậy:

- Đổi password làm credential cũ không còn hợp lệ cho các lần authentication mới.
- Các session đã mở thường vẫn hoạt động.
- Pool có thể tiếp tục dùng idle connections đã authenticated bằng password cũ.
- Khi pool cần tạo connection mới, nó phải có password mới.
- Nếu role bị NOLOGIN hoặc session bị terminate, tác động khác với chỉ đổi password.

Đây là lý do rotation cần kế hoạch refresh pool, chứ không chỉ cập nhật secret value.

## 22. Một role chỉ có một password verifier tại một thời điểm

PostgreSQL role thông thường có một password verifier hiện hành. Đổi password của cùng role thay thế verifier cũ; không có cơ chế native để một role đồng thời chấp nhận hai password độc lập trong một khoảng overlap.

Điều này gây khó cho rolling deployment nếu nhiều application instances cập nhật secret ở thời điểm khác nhau.

### Giải pháp staged rotation

Dùng login role mới cho credential mới, cả hai login roles cùng là member của một group role chứa permissions:

```sql
CREATE ROLE app_login_v2 LOGIN INHERIT;
GRANT app_readwrite TO app_login_v2;
```

Đặt password cho role mới bằng psql:

```text
\password app_login_v2
```

Ứng dụng dần chuyển sang app_login_v2. Khi mọi clients đã dùng role mới, disable role cũ và xử lý các sessions còn lại.

## 23. Staged password rotation cho ứng dụng

Một quy trình zero/low-downtime tham khảo:

1. Xác nhận group role và quyền runtime đã tách khỏi login role.
2. Tạo login role version mới.
3. Cấp membership của group role cho login role mới.
4. Đặt password mới bằng secure interactive/automation flow.
5. Lưu secret version mới trong secret manager.
6. Test login từ một canary instance.
7. Rollout secret mới theo từng batch.
8. Mở connections mới và xác nhận authentication thành công.
9. Theo dõi connection distribution theo application_name/user.
10. Khi mọi clients chuyển xong, disable login role cũ.
11. Terminate old sessions theo change plan nếu cần.
12. Xóa role cũ sau khi xử lý grants/ownership/dependencies.

### Vì sao cần canary?

Canary kiểm tra password, HBA rule, TLS, role membership, database CONNECT và object privileges trước khi rollout toàn bộ. Một lần psql login thành công không đủ nếu application dùng driver/pooler khác.

## 24. Rotation cùng một role khi không thể tạo role mới

Một số managed services hoặc ứng dụng legacy không dễ hỗ trợ dual login roles. Khi đó phải phối hợp cutover:

1. Chuẩn bị secret mới và xác nhận rollout path.
2. Chọn change window hoặc cơ chế đồng bộ nhanh.
3. Đổi password role trên PostgreSQL bằng secure flow.
4. Cập nhật secret manager/config ngay sau đó.
5. Reload/restart/recreate pools theo platform.
6. Kiểm tra mọi instances tạo được connection mới.
7. Giữ rollback procedure có giới hạn và audit.

Vì verifier cũ bị thay ngay, clients chưa nhận secret mới có thể fail khi reconnect. Đánh giá downtime risk trước khi chọn phương án này.

## 25. Disable role cũ

Sau staged rotation:

```sql
ALTER ROLE app_login_v1 NOLOGIN;
```

NOLOGIN ngăn các lần đăng nhập mới bằng role đó. Nó không tự kết thúc sessions đã tồn tại.

Kiểm tra sessions:

```sql
SELECT
    pid,
    usename,
    application_name,
    client_addr,
    state,
    backend_start
FROM pg_catalog.pg_stat_activity
WHERE usename = 'app_login_v1'
ORDER BY backend_start;
```

Nếu policy yêu cầu thu hồi ngay, cần đánh giá và terminate sessions còn lại bằng quyền quản trị phù hợp.

## 26. Terminate sessions cũ

Có thể dùng pg_terminate_backend sau khi xác định đúng sessions:

```sql
SELECT pg_terminate_backend(pid)
FROM pg_catalog.pg_stat_activity
WHERE usename = 'app_login_v1'
  AND pid <> pg_backend_pid();
```

Không chạy hàng loạt mà không đánh giá transaction đang thực hiện. Termination có thể rollback transaction, làm job thất bại hoặc để client ở trạng thái không biết transaction đã commit hay chưa.

### Termination và pool behavior

Pooler/application có thể tự reconnect. Nếu role cũ vẫn được phép login, connections có thể xuất hiện lại. Disable login hoặc đổi credential trước khi terminate để tránh vòng lặp reconnect bằng secret cũ.

## 27. Thu hồi password và login capability

Có thể:

- Đặt role NOLOGIN để ngăn login mới.
- Đổi password sang giá trị ngẫu nhiên không được phân phối.
- Đặt password NULL để không có password verifier.
- Sửa pg_hba.conf để reject một nguồn/role.
- REVOKE CONNECT theo database.
- Terminate sessions hiện hữu.

Các cách này có semantics khác nhau. Ví dụ REVOKE CONNECT không tự đóng sessions đã mở; NOLOGIN cũng không terminate backend hiện tại. Chọn phương án theo mục tiêu thu hồi.

## 28. Password NULL và role NOLOGIN

Đặt password NULL:

```sql
ALTER ROLE app_login_v1 PASSWORD NULL;
```

Điều này loại bỏ password verifier cho role; password authentication không thể dùng password để đăng nhập role đó. Các authentication methods khác như certificate/peer có policy riêng và cần xem HBA.

NOLOGIN:

```sql
ALTER ROLE app_login_v1 NOLOGIN;
```

NOLOGIN ngăn role tạo connection mới bất kể method authentication. Đây thường là biện pháp rõ hơn khi muốn disable toàn bộ login capability của role.

## 29. REVOKE CONNECT và quyền database

Có thể giới hạn quyền CONNECT:

```sql
REVOKE CONNECT ON DATABASE appdb FROM app_login_v1;
```

Nhưng lưu ý:

- CONNECT có thể được cấp qua PUBLIC hoặc role membership khác.
- Role có thể có quyền CONNECT qua một grant khác.
- REVOKE không chấm dứt sessions đang tồn tại.
- HBA rules có thể chặn connection trước khi privilege check.

Kiểm tra ACL và role membership trước khi coi REVOKE là biện pháp thu hồi hoàn chỉnh.

## 30. Password rotation cho PgBouncer

PgBouncer có thể xác thực client và mở backend connections tới PostgreSQL. Cần phân biệt:

- Frontend authentication: ứng dụng đăng nhập vào PgBouncer.
- Backend authentication: PgBouncer đăng nhập vào PostgreSQL.

Credentials/verification data có thể được lấy từ auth_file hoặc auth_query tùy cấu hình. Khi đổi password:

1. Xác định client auth và backend auth dùng role/secret nào.
2. Cập nhật secret/auth source.
3. Kiểm tra SCRAM compatibility theo PgBouncer version.
4. Reload config/auth file nếu cần.
5. Tạo backend connection mới để xác nhận.
6. Reconnect/drain old server connections theo maintenance plan.
7. Kiểm tra SHOW CLIENTS, SHOW SERVERS và logs.

Reload auth file không tự bảo đảm mọi server connection cũ đã được thay. Xác nhận backend connections và client reconnect behavior riêng.

## 31. PgBouncer auth_file và SCRAM

Auth file có thể chứa password verifier thay vì plaintext trong một số cấu hình/phiên bản. Khả năng dùng SCRAM verifier làm frontend hoặc backend credential phụ thuộc PgBouncer version và cách cấu hình userlist/auth_query.

### Bảo vệ auth file

- Quyền file chỉ cho service account đọc.
- Không commit file vào repository.
- Không đính kèm file vào ticket/log.
- Có owner, version và rotation process.
- Reload có kiểm soát và verify.

Nếu dùng auth_query, role được dùng để truy vấn verifier phải có quyền tối thiểu theo hướng dẫn PgBouncer; không cấp quyền đọc rộng pg_authid cho application roles.

## 32. Rotation cho replication user

Physical standby dùng credentials trong primary_conninfo để kết nối tới primary. Ví dụ cấu hình có thể tham chiếu password file:

```text
primary_conninfo = 'host=pg-primary.internal port=5432 user=replicator application_name=standby_a passfile=/run/secrets/replication.pgpass'
```

Tạo role replication với quyền tối thiểu:

```sql
CREATE ROLE replicator LOGIN REPLICATION;
```

Đặt password qua psql:

```text
\password replicator
```

Rotation cần cập nhật secret trên mọi standbys, xác nhận HBA cho replication connection, rồi buộc WAL receiver reconnect khi thích hợp. Nếu đổi password cùng role, các standby chưa cập nhật sẽ thất bại khi reconnect.

## 33. Xoay vòng replication credentials theo staged roles

Để tránh đổi cùng lúc một credential dùng bởi nhiều standbys:

1. Tạo replication role mới với LOGIN REPLICATION.
2. Đặt password mới qua secure flow.
3. Cấp HBA rule phù hợp cho standby addresses.
4. Cập nhật primary_conninfo/passfile từng standby.
5. Reload/reconnect WAL receiver và xác nhận streaming.
6. Theo dõi pg_stat_replication trên primary.
7. Khi tất cả standbys dùng role mới, disable role cũ.
8. Thu hồi role cũ sau khi kiểm tra không còn consumer.

Role mới cần quyền REPLICATION và CONNECT cần thiết, không cần SUPERUSER. Hạn chế source addresses trong pg_hba.conf.

## 34. Kiểm tra replication sau rotation

Trên primary:

```sql
SELECT
    application_name,
    usename,
    client_addr,
    state,
    sync_state,
    sent_lsn,
    write_lsn,
    flush_lsn,
    replay_lsn
FROM pg_catalog.pg_stat_replication
ORDER BY application_name;
```

Trên standby:

```sql
SELECT
    status,
    sender_host,
    sender_port,
    slot_name,
    written_lsn,
    latest_end_lsn,
    latest_end_time
FROM pg_catalog.pg_stat_wal_receiver;
```

Tên/cột view có thể khác theo PostgreSQL version. Xác nhận trạng thái streaming và lag sau khi rotation.

## 35. Rotation cho logical replication và CDC

Logical replication subscription lưu connection information trong catalog subscription. Các credentials của subscription cần được quản lý như secret có quyền truy cập rất hạn chế.

Kiểm tra subscription metadata bằng các views/catalog phù hợp với version; không in connection string chứa password vào output hoặc ticket.

Khi rotate:

1. Xác định publisher role và từng subscription consumer.
2. Tạo login role mới với quyền replication/select cần thiết.
3. Cập nhật credential an toàn cho subscription theo cơ chế được PostgreSQL version hỗ trợ.
4. Xác minh connection và apply workers.
5. Disable role cũ sau khi mọi subscribers chuyển.
6. Theo dõi replication lag và worker errors.

Không copy connection string chứa password vào shell command history hoặc log.

## 36. Credentials cho backup, monitoring và migrations

Không dùng chung application superuser hoặc một password cho mọi automation. Tạo role riêng theo nhiệm vụ:

| Role | Quyền cần thiết |
|---|---|
| backup role | Quyền backup phù hợp với backup tool/version |
| monitoring role | Đọc metrics/catalog cần thiết |
| migration role | DDL trong phạm vi schema được quản lý |
| application role | DML tối thiểu cho runtime |
| replication role | REPLICATION và kết nối replication |
| break-glass role | Quyền quản trị khẩn cấp, kiểm soát chặt |

Mỗi role cần owner, purpose, secret location, rotation cadence/event và consumer inventory.

## 37. Credential inventory

Một inventory nên ghi:

- Role name và owner.
- Purpose/service/environment.
- Database/cluster scope.
- Authentication method.
- Secret manager path/version reference, không ghi secret value.
- Consumer instances/jobs.
- Rotation date/expiry.
- Last successful rotation.
- Revocation procedure.
- Break-glass dependency nếu có.

Không lưu password plaintext trong inventory. Chỉ lưu reference tới secret object và metadata cần vận hành.

## 38. Secret rotation triggers

Rotation có thể được kích hoạt bởi:

- Lịch rotation theo policy.
- Nhân sự rời tổ chức hoặc thay đổi quyền truy cập.
- Secret nghi bị lộ trong source/log/ticket.
- Compromise hoặc suspicious login.
- Vendor/secret manager yêu cầu rotate.
- Certificate/identity policy thay đổi.
- Chuyển service ownership hoặc môi trường.

Nếu secret bị lộ, coi đó là incident: revoke/rotate ngay theo containment plan, kiểm tra audit logs và xác định phạm vi exposure. Không chờ tới rotation window tiếp theo.

## 39. Rotation cadence và password expiry

Không có một chu kỳ duy nhất phù hợp cho mọi credential. Chọn cadence dựa trên:

- Mức privilege.
- Exposure surface.
- Secret lifetime/lease.
- Khả năng tự động rotate.
- Impact nếu credential bị lộ.
- Khả năng đồng bộ mọi consumers.

Credentials có quyền cao hoặc external exposure cần kiểm soát chặt hơn. Dynamic short-lived credentials có thể giảm thời gian tồn tại của secret, nhưng chỉ khi ứng dụng/pooler xử lý renew/reconnect đúng.

## 40. Dynamic credentials

Một số secret managers có thể tạo credentials tạm thời bằng cách tạo PostgreSQL roles với TTL và tự thu hồi khi lease hết hạn.

Lợi ích:

- Giảm password dùng lâu dài.
- Mỗi service/instance có thể có identity riêng.
- Audit dễ truy vết consumer.
- Thu hồi theo lease.

Rủi ro:

- Hệ thống phải renew lease trước expiry.
- Pool cần mở connections mới bằng credential mới.
- Role lifecycle và grants phải được tự động hóa an toàn.
- Secret manager outage có thể ảnh hưởng reconnect.
- Existing sessions có thể tiếp tục sau lease revocation tùy cơ chế; cần hiểu termination policy.

Dynamic credentials không tự giải quyết connection lifecycle hoặc authorization design.

## 41. TLS và password là hai lớp bảo vệ khác nhau

Password xác thực user/role. TLS bảo vệ channel và có thể xác minh server identity. Password mạnh không ngăn MITM nếu client không xác minh server certificate.

Connection string minh họa:

```text
host=pg-primary.internal
dbname=appdb
user=app_login_v2
sslmode=verify-full
```

verify-full yêu cầu TLS và xác minh certificate chain/hostname theo trust configuration của client. sslmode=require mã hóa channel nhưng không có cùng mức xác minh hostname.

### hostssl trong HBA

Dùng hostssl cho network connections cần TLS. Kết hợp server certificate/private key permissions và client trust store. Không tắt certificate verification chỉ để làm connection thành công.

## 42. Client certificate authentication

PostgreSQL có thể dùng certificate authentication với HBA method cert. Đây là cơ chế xác thực dựa trên client certificate và mapping tới database role.

Ví dụ:

```conf
hostssl  appdb  app_cert_user  10.20.0.0/16  cert
```

Certificate auth cần client certificate, private key, CA trust và certificate-to-role mapping nếu tên certificate khác role. Bảo vệ private key như password secret; certificate hết hạn/revocation cần rotation workflow.

### Certificate không tự cấp quyền object

Authentication xác định role. Authorization vẫn do PostgreSQL privileges, ownership và role memberships quyết định.

## 43. Role membership và quyền sau rotation

Login role mới cần nhận đúng group role memberships. Kiểm tra:

```sql
SELECT
    member.rolname AS member_role,
    parent.rolname AS granted_role
FROM pg_catalog.pg_auth_members AS m
JOIN pg_catalog.pg_roles AS member
  ON member.oid = m.member
JOIN pg_catalog.pg_roles AS parent
  ON parent.oid = m.roleid
ORDER BY member_role, granted_role;
```

PostgreSQL versions mới có membership options như INHERIT/SET/ADMIN theo grant. Xác minh behavior theo version và đảm bảo role mới thực sự có quyền cần thiết nhưng không vượt quá.

## 44. Ownership và cleanup login role cũ

Không nên để application login role sở hữu database/schema/table nếu có thể tách role owner riêng. Khi drop role cũ, PostgreSQL có thể từ chối nếu role còn sở hữu objects hoặc grants/dependencies.

Kiểm tra ownership và privileges trước khi drop. Trong môi trường có ownership cũ, có thể cần:

```sql
REASSIGN OWNED BY app_login_v1 TO app_owner;
DROP OWNED BY app_login_v1;
```

Các lệnh này có phạm vi ảnh hưởng rộng trong database hiện tại và có thể revoke/drop grants. Chỉ chạy sau khi review dependencies và đúng database; không dùng như cleanup mặc định cho mọi rotation.

## 45. Audit role/password changes

Cần biết:

- Ai tạo/đổi/disable role?
- Khi nào thay đổi?
- Change ticket/approval nào liên quan?
- Role nào được cấp membership?
- HBA rules nào thay đổi?
- Secret manager version nào được rollout?
- Consumer nào đã reconnect?

PostgreSQL logs, configuration management, audit extensions và secret manager audit logs có thể bổ sung cho nhau. Không ghi password plaintext hoặc verifier vào audit event.

### log_connections và log_disconnections

Có thể bật logging connections/disconnections để hỗ trợ điều tra. Cân nhắc volume, privacy và log retention. Những logs này không thay thế audit role DDL hoặc secret manager audit trail.

## 46. Kiểm tra đăng nhập bất thường

Theo dõi:

- Authentication failures tăng đột biến.
- Role đăng nhập từ source IP/region bất thường.
- SUPERUSER hoặc CREATEROLE usage không theo change plan.
- Login role cũ tiếp tục tạo sessions sau cutover.
- Service account hoạt động ngoài expected schedule.
- Secret manager reads bất thường.

Kết hợp PostgreSQL logs, network identity, cloud IAM và application telemetry. Không chỉ dựa vào client_addr nếu traffic đi qua NAT/proxy.

## 47. Break-glass credentials

Break-glass account là credential quản trị khẩn cấp khi hệ thống IAM/secret manager chính gặp sự cố.

Policy nên có:

- Không dùng hằng ngày.
- Quyền lưu trữ và retrieval được kiểm soát.
- MFA/approval theo nền tảng quản trị nếu có.
- Audit mọi lần truy cập.
- Kiểm tra định kỳ khả năng sử dụng.
- Rotation sau mỗi lần dùng.
- Có ít nhất một quy trình khôi phục nếu secret manager outage.

Không chia sẻ break-glass password trong tài liệu runbook hoặc chat.

## 48. Managed PostgreSQL services

Managed database services có thể giới hạn quyền SUPERUSER, file access, HBA editing hoặc role attributes. Cách rotate master/admin password và certificate có thể do control plane của nhà cung cấp quản lý.

Trước khi áp dụng SQL:

- Kiểm tra role restrictions của service.
- Xác định secret source of truth.
- Xem cách provider cập nhật connection endpoint/certificates.
- Xác nhận behavior khi rotate admin password.
- Kiểm tra maintenance/restart implications.

Không giả định mọi file path và system commands của self-managed Linux đều truy cập được trong managed service.

## 49. Connection pools sau password rotation

Sau khi secret mới được rollout:

- Idle connections đã authenticated có thể vẫn dùng được.
- Connections đang chạy không tự đổi credential.
- Pool tạo connection mới cần đọc secret mới.
- Một số pool chỉ đọc environment/config lúc khởi tạo.
- Một số pool hỗ trợ secret provider/reload callback.

Thiết kế pool lifecycle rõ:

1. Update secret reference.
2. Reload/recreate pool hoặc soft-evict idle connections.
3. Mở canary connection.
4. Xác minh auth và database role.
5. Drain old connections.
6. Đếm sessions còn dùng login role cũ.

## 50. Kubernetes secret update và application reload

Secret được mount dạng file có thể cập nhật nội dung theo cơ chế projected volume, nhưng process cần reread file. Environment variables được inject lúc container start thường không tự thay đổi trong process.

Vì vậy:

- Dùng file watcher/reload hook nếu ứng dụng hỗ trợ.
- Hoặc rolling restart có kiểm soát.
- Cấu hình readiness để chỉ nhận traffic khi pool mới healthy.
- Giới hạn surge replicas để không vượt connection budget.
- Xác nhận mọi pod đã dùng secret version mới.

Không xóa secret cũ khỏi secret manager trước khi xác nhận toàn bộ consumers đã chuyển.

## 51. Rotation trong CI/CD và migration jobs

CI/CD credentials thường tồn tại trong runner, pipeline variables, deployment agents và migration tools.

Biện pháp:

- Dùng short-lived credentials nếu platform hỗ trợ.
- Mask secret output.
- Không bật shell tracing khi xử lý secret.
- Không đưa password vào command-line arguments.
- Tách migration role khỏi runtime application role.
- Hạn chế runner network access.
- Xóa temporary files an toàn và giới hạn permissions.
- Audit pipeline identity và secret reads.

Migration job có thể chạy sau deploy nhiều giờ; inventory tất cả scheduled jobs trước khi revoke login role cũ.

## 52. Rotation và failover

Không nên thực hiện password rotation đồng thời với failover nếu có thể tránh, vì hai thay đổi cùng lúc làm khó phân biệt lỗi authentication với lỗi topology.

Nếu bắt buộc:

1. Xác định primary hiện tại qua HA control plane.
2. Xác nhận standby/replication state.
3. Chọn một role/credential path và test trên primary mới.
4. Cập nhật tất cả consumers/standbys.
5. Verify reconnect và replication.
6. Chỉ thu hồi credential cũ khi topology ổn định.

Credentials phải hoạt động trên node mới sau promotion và không phụ thuộc một host/IP đã cũ.

## 53. Xử lý credential bị lộ

Khi phát hiện password trong source code, log, ticket hoặc terminal transcript:

1. Xác định role, cluster, scope và thời gian exposure.
2. Hạn chế quyền truy cập artifact chứa secret.
3. Rotate hoặc disable credential theo containment plan.
4. Chuyển consumers sang credential mới.
5. Terminate sessions cũ nếu cần.
6. Kiểm tra login/audit logs và hành vi bất thường.
7. Xác định secret có bị tái sử dụng ở hệ thống khác không.
8. Thu hồi bản sao ở repo/log/ticket theo retention policy.
9. Ghi incident timeline và evidence.
10. Sửa quy trình khiến secret bị lộ.

Không chỉ xóa secret khỏi file hiện tại; lịch sử Git, CI artifacts, backups và logs có thể vẫn chứa bản cũ.

## 54. Troubleshooting: password authentication failed

Thông báo authentication failed có thể do:

- Sai username/password.
- Password mới chưa được rollout tới instance.
- Role không LOGIN hoặc hết hạn.
- HBA rule chọn method/address/database khác dự kiến.
- Client không hỗ trợ SCRAM.
- Pooler dùng credential frontend/backend khác nhau.
- Secret file sai permissions/format hoặc entry không match.
- Kết nối tới cluster/endpoint khác.

Quy trình:

1. Ghi lại client, host, database, role và thời điểm.
2. Xác định server/cluster thực tế.
3. Kiểm tra HBA rule match và server logs.
4. Kiểm tra role LOGIN/VALID UNTIL.
5. Kiểm tra verifier type mà không xuất hash.
6. Kiểm tra secret version và file permissions.
7. Test một connection mới từ cùng client runtime.
8. Kiểm tra driver SCRAM support.

Không yêu cầu người dùng gửi password vào ticket/chat để debug.

## 55. Troubleshooting: SCRAM migration làm client lỗi

1. Xác định client type/driver version.
2. Kiểm tra lỗi SCRAM negotiation trong client/server logs.
3. Kiểm tra role đã có SCRAM verifier chưa.
4. Kiểm tra password_encryption trước lần reset gần nhất.
5. Kiểm tra HBA rule và thứ tự rules.
6. Nâng cấp driver/pooler/tool không hỗ trợ SCRAM.
7. Reset password bằng secure flow để tạo verifier SCRAM.
8. Test canary trước rollout toàn bộ.
9. Theo dõi auth failure rate.

Không quay về trust hoặc tắt password auth để né lỗi compatibility.

## 56. Troubleshooting: ứng dụng vẫn dùng credential cũ

1. Kiểm tra secret manager version trên từng instance.
2. Kiểm tra environment/file mount đã cập nhật chưa.
3. Kiểm tra process có reload secret không.
4. Kiểm tra application pool có connections idle cũ không.
5. Kiểm tra PgBouncer auth source/backend connections.
6. Kiểm tra jobs/worker/scheduled tasks ngoài API fleet.
7. Recreate/soft-evict pools theo rollout plan.
8. Disable role cũ và theo dõi reconnect attempts.

## 57. Troubleshooting: standby ngừng streaming sau rotation

1. Xác định standby và thời điểm WAL receiver dừng.
2. Kiểm tra PostgreSQL standby logs.
3. Xác định primary endpoint/role hiện tại.
4. Kiểm tra primary_conninfo và passfile path/permissions.
5. Kiểm tra pg_hba replication rule và source address.
6. Xác nhận role có LOGIN và REPLICATION.
7. Test authentication bằng client phù hợp.
8. Cập nhật secret/reload/reconnect theo quy trình.
9. Xác nhận pg_stat_wal_receiver streaming.
10. Theo dõi replay lag và retained WAL.

## 58. Runbook: staged rotation cho application login

1. Lập inventory mọi consumers của login role cũ.
2. Xác nhận group role chứa đủ quyền runtime.
3. Tạo login role mới với least privilege.
4. Grant group role cho login role mới.
5. Đặt password mới qua psql hoặc automation an toàn.
6. Tạo secret version mới.
7. Test canary connection bằng driver production.
8. Rollout theo batches và theo dõi auth errors.
9. Xác minh mọi app instances, workers và jobs dùng role mới.
10. Disable login role cũ.
11. Terminate old sessions theo change plan.
12. Revoke/drop role cũ sau khi xử lý dependencies.
13. Audit rotation và cập nhật inventory.

## 59. Runbook: emergency credential compromise

1. Mở incident và xác định owner/commander.
2. Xác định role, privileges, consumers và exposure scope.
3. Quyết định disable ngay hay staged replacement dựa trên impact.
4. Tạo credential/role thay thế trong secret manager.
5. Cập nhật PostgreSQL auth và consumers.
6. Chặn login mới bằng credential bị lộ.
7. Terminate sessions còn lại nếu containment yêu cầu.
8. Kiểm tra logs, source IPs và privileged operations.
9. Thu hồi artifact copies và kiểm tra secret reuse.
10. Xác nhận service hoạt động bằng credential mới.
11. Lưu evidence và post-incident actions.

## 60. Runbook: SCRAM migration

1. Kiểm kê roles dùng password authentication.
2. Kiểm kê mọi client libraries và tools.
3. Nâng cấp client không hỗ trợ SCRAM.
4. Set password_encryption=scram-sha-256.
5. Reset password theo từng role bằng secure method.
6. Xác minh verifier algorithm không lộ hash.
7. Cập nhật HBA method sang scram-sha-256 theo nhóm.
8. Reload HBA và kiểm tra pg_hba_file_rules.
9. Test kết nối mới từ mọi client class.
10. Loại MD5 rules sau khi hoàn tất.
11. Theo dõi auth failures và cập nhật documentation.

## 61. Runbook: rotate replication credentials

1. Inventory tất cả physical/logical replication consumers.
2. Tạo replication login role mới và password.
3. Cập nhật HBA rule giới hạn đúng addresses.
4. Cập nhật passfile/primary_conninfo/subscription credentials.
5. Reload/reconnect từng consumer theo thứ tự.
6. Xác minh WAL receiver/pg_stat_replication.
7. Theo dõi lag và apply errors.
8. Xác nhận không còn consumer dùng role cũ.
9. NOLOGIN role cũ.
10. Thu hồi role cũ sau khi topology ổn định.

## 62. Checklist quản lý secrets và password

### Identity và privileges

- Mỗi service có login role riêng.
- Quyền runtime nằm trong group role NOLOGIN.
- Không dùng SUPERUSER cho ứng dụng.
- Replication, backup, monitoring và migration roles tách biệt.
- Role có owner và purpose rõ ràng.

### Password và authentication

- Dùng SCRAM-SHA-256 cho password auth.
- Client drivers/poolers hỗ trợ SCRAM.
- Password được generate ngẫu nhiên và riêng theo service.
- Không ghi plaintext password vào SQL history/log/source.
- pg_hba.conf giới hạn database/user/address và ưu tiên TLS.
- Password verifier/catalog backups được bảo vệ.

### Secret distribution

- Secret manager là source of truth.
- RBAC/audit/versioning được bật.
- Không bake secret vào image/manifests.
- .pgpass/passfiles có permissions phù hợp.
- Không log environment variables hoặc connection URIs chứa secret.
- Container/pod chỉ mount secret cần thiết.

### Rotation và revocation

- Inventory đầy đủ consumers.
- Có staged rotation hoặc cutover plan.
- Connection pools/PgBouncer được refresh.
- Replication/backup/monitoring jobs đã test.
- Role cũ bị disable sau cutover.
- Existing sessions được xử lý theo policy.
- Expiry/revocation và rollback được ghi lại.

### Audit và incident response

- Role changes/secret reads có audit.
- Break-glass account được kiểm soát.
- Credential compromise có runbook.
- Có kiểm tra auth failures sau rotation.
- Không gửi password qua chat/ticket.

## 63. Các sai lầm thường gặp

**Dùng chung một role/password cho mọi service.** Khó thu hồi một consumer mà không ảnh hưởng phần còn lại.

**Lưu password plaintext trong ALTER ROLE command.** Secret có thể xuất hiện trong history hoặc logs.

**Đổi password rồi nghĩ mọi session cũ bị ngắt.** Existing sessions thường vẫn hoạt động cho tới khi đóng/terminate.

**Cập nhật secret manager nhưng không refresh pool.** Pool có thể tiếp tục cấp idle connections cũ và chỉ lỗi khi reconnect.

**Rotate một role duy nhất trong rolling deployment mà không có overlap.** Instances chưa cập nhật sẽ fail khi tạo connection mới.

**Cho application role SUPERUSER.** Credential bị lộ có thể ảnh hưởng toàn cluster.

**Coi Kubernetes Secret base64 là encryption.** Cần encryption at rest, RBAC và secret lifecycle.

**Dùng PGPASSWORD dài hạn.** Environment variables có thể lộ qua process/debugging surfaces.

**Đổi password nhưng quên replication, PgBouncer, backup và scheduled jobs.** Những consumers ít chạy có thể chỉ thất bại nhiều ngày sau.

**Dùng trust để né SCRAM compatibility.** Điều này làm suy yếu authentication policy.

**Xóa role cũ ngay sau rollout đầu tiên.** Cần xác nhận toàn bộ consumers, sessions và dependencies đã được xử lý.

## 64. Bài tập thực hành

### Bài 1 — PostgreSQL roles

Phân biệt LOGIN role, NOLOGIN group role và role owner. Thiết kế roles cho một orders service.

### Bài 2 — Password verifier

Vì sao password verifier vẫn là dữ liệu nhạy cảm dù không phải plaintext? Những nơi nào có thể chứa verifier?

### Bài 3 — SCRAM

Giải thích challenge-response của SCRAM-SHA-256 và vì sao TLS vẫn cần thiết.

### Bài 4 — password_encryption

Đặt password_encryption thành scram-sha-256. Vì sao các roles có verifier MD5 không tự được chuyển đổi?

### Bài 5 — pg_hba.conf

Viết rule hostssl cho appdb/app_login từ subnet 10.20.0.0/16 dùng scram-sha-256. Giải thích thứ tự rules.

### Bài 6 — psql password change

Dùng psql \password để đổi password. Vì sao cách này an toàn hơn viết ALTER ROLE PASSWORD literal trong terminal?

### Bài 7 — Least privilege

Tạo group role NOLOGIN có quyền DML trong schema app và login role riêng được grant membership.

### Bài 8 — Default privileges

Thiết kế default privileges để bảng mới do app_owner tạo có quyền phù hợp cho app_readwrite.

### Bài 9 — Password strength

Đề xuất policy generate password ngẫu nhiên cho service accounts. Vì sao không nên tái sử dụng secret giữa staging và production?

### Bài 10 — VALID UNTIL

Đặt password expiration cho role và giải thích vì sao existing sessions không bị ngắt khi password hết hạn.

### Bài 11 — MD5 migration

Thiết kế migration từ MD5 sang SCRAM cho 20 application services và 5 automation clients.

### Bài 12 — Client compatibility

Một Java driver cũ không hỗ trợ SCRAM. Lập inventory và rollout kế hoạch nâng cấp trước khi đổi HBA.

### Bài 13 — .pgpass

Giải thích format .pgpass, file permissions và escaping cho colon/backslash.

### Bài 14 — PGPASSWORD

Vì sao environment variable PGPASSWORD có thể bị lộ? Đề xuất các phương án thay thế.

### Bài 15 — Service file

Viết pg_service.conf entry dùng sslmode=verify-full và passfile riêng.

### Bài 16 — Secret manager

Liệt kê các tính năng secret manager cần có cho PostgreSQL production credentials.

### Bài 17 — Kubernetes Secret

Vì sao base64 không phải encryption? Nêu RBAC, encryption at rest và mount policy cần thiết.

### Bài 18 — Existing sessions

Một role password đã đổi nhưng query trên session cũ vẫn chạy. Giải thích behavior và tác động tới connection pools.

### Bài 19 — Dual login roles

Thiết kế app_login_v1 và app_login_v2 cùng kế thừa app_readwrite để rotation không gián đoạn.

### Bài 20 — Single-role rotation

Một ứng dụng legacy không hỗ trợ hai login roles. Thiết kế cutover plan và đánh giá downtime risk.

### Bài 21 — NOLOGIN

Đặt role cũ NOLOGIN. Vì sao cần kiểm tra và xử lý existing sessions riêng?

### Bài 22 — pg_terminate_backend

Viết query liệt kê sessions theo usename/application_name và mô tả rủi ro khi terminate transaction đang chạy.

### Bài 23 — PASSWORD NULL

So sánh PASSWORD NULL với NOLOGIN. Khi nào nên disable toàn bộ login capability?

### Bài 24 — REVOKE CONNECT

Vì sao REVOKE CONNECT không đủ để đóng sessions đang hoạt động? Những nguồn grant nào cần kiểm tra?

### Bài 25 — PgBouncer

Phân biệt frontend authentication và backend authentication. Thiết kế rotation cho cả hai phía.

### Bài 26 — SCRAM auth_file

Vì sao PgBouncer version và auth_query/auth_file configuration ảnh hưởng cách lưu verifier? Cần bảo vệ file thế nào?

### Bài 27 — Physical replication

Tạo role REPLICATION riêng và thiết kế rotation cho primary_conninfo/passfile trên ba standbys.

### Bài 28 — Replication verification

Viết query kiểm tra pg_stat_replication và pg_stat_wal_receiver sau khi đổi replication password.

### Bài 29 — Logical replication

Thiết kế rotation credentials cho publisher role và nhiều subscriptions mà không lộ connection strings.

### Bài 30 — Backup/monitoring roles

Thiết kế roles riêng cho backup, monitoring, migration và runtime. Giải thích quyền tối thiểu.

### Bài 31 — Credential inventory

Thiết kế inventory không chứa secret plaintext nhưng vẫn giúp biết owner, consumers, secret reference, expiry và revoke procedure.

### Bài 32 — Rotation trigger

Một password production bị paste vào ticket. Xây dựng incident response và containment steps.

### Bài 33 — Dynamic credentials

Giải thích lợi ích/rủi ro của short-lived PostgreSQL credentials và cách pool renew/reconnect.

### Bài 34 — TLS

Phân biệt password authentication với TLS server verification. Vì sao sslmode=require khác verify-full?

### Bài 35 — Certificate auth

Thiết kế client certificate authentication bằng HBA cert. Những private key/CA materials nào cần rotation?

### Bài 36 — Role memberships

Viết query liệt kê member role và granted role. Vì sao cần xác minh membership options theo PostgreSQL version?

### Bài 37 — Ownership cleanup

Một login role cũ đang sở hữu objects. Vì sao DROP ROLE bị từ chối và tại sao REASSIGN OWNED/DROP OWNED cần review kỹ?

### Bài 38 — Audit

Thiết kế audit trail cho role changes, secret manager reads, pool refresh và successful cutover mà không ghi password/verifier.

### Bài 39 — SCRAM failure

Sau khi chuyển HBA sang SCRAM, một exporter không kết nối được. Viết quy trình xác định driver, verifier, HBA và secret file issues.

### Bài 40 — Rotation end-to-end

Một hệ thống có:

- PostgreSQL primary và hai physical standbys.
- 30 instances của orders API qua PgBouncer.
- Một logical replication subscriber cho analytics.
- Backup jobs chạy mỗi 6 giờ.
- Monitoring exporter và migration runner.
- Tất cả hiện dùng chung một login role với password lâu năm.
- Chính sách yêu cầu rotate ngay khi secret nghi bị lộ.
- Ứng dụng hỗ trợ rolling deployment nhưng một số batch jobs chạy hàng ngày.

Hãy thiết kế:

1. Role model mới với group roles và login roles riêng.
2. SCRAM migration và client compatibility plan.
3. Secret manager inventory cho từng consumer.
4. Staged rotation bằng login role mới.
5. PgBouncer frontend/backend authentication refresh.
6. Physical/logical replication credential updates.
7. Backup, monitoring và migration job cutover.
8. Session draining, NOLOGIN và old-role cleanup.
9. Audit, emergency revocation và rollback plan.
10. Tests/metrics chứng minh không còn consumer dùng credential cũ.

## Kết luận

**Quản lý password PostgreSQL là quản lý cả danh tính, verifier, quyền, secret distribution và connection lifecycle.** Dùng SCRAM-SHA-256 cho password authentication, bảo vệ verifier/catalog backups, yêu cầu TLS cho network connections và tránh đưa plaintext secrets vào SQL history, source code, command line hoặc logs. Tách login roles khỏi group roles để quyền runtime có thể tái sử dụng mà credentials vẫn riêng biệt.

Rotation cùng một role thay thế password verifier hiện hành; PostgreSQL không cung cấp hai password song song cho cùng role. Với rolling deployment, staged rotation bằng login role mới kế thừa group role thường giảm rủi ro. Sau cutover, disable role cũ, xử lý sessions còn tồn tại và chỉ drop role khi dependencies/ownership đã được giải quyết.

Đừng quên PgBouncer, connection pools, physical/logical replication, backup, monitoring và scheduled jobs. Password change không tự ngắt session cũ; secret manager update không tự refresh connections; NOLOGIN không terminate backends đang chạy. Hãy xác minh từng consumer bằng connection mới, audit rotation, và giữ runbook cho compromise/revocation.

**Một quy trình rotation đáng tin cậy có inventory đầy đủ, secret được bảo vệ, rollout có kiểm soát, connection refresh được xác nhận và credential cũ được thu hồi rõ ràng.**
